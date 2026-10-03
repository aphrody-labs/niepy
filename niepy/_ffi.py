"""Chargement de la bibliothèque native `nie_ffi` et déclaration des signatures C.

Ce module est le **seul** endroit de `niepy` qui connaît `ctypes`. Tout le reste de la
bibliothèque manipule des objets Python.

Deux pièges de ce dépôt sont traités ici, et pas ailleurs :

- **Sur Windows, rustc produit `iecode.dll`, sans préfixe `lib`.** Chercher `libiecode.dll`
  échoue silencieusement puis casse au premier appel, avec une erreur qui accuse l'appel et
  non la résolution du chemin.
- **Une signature `ctypes` non déclarée est un bug qui ne se voit qu'à l'exécution**, et
  souvent loin de sa cause : sans `restype`, `ctypes` suppose `int` (32 bits) et tronque tout
  pointeur rendu par la lib. Chaque symbole utilisé ici est donc déclaré explicitement.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

__all__ = [
    "NieBall",
    "NieBytes",
    "NieCacheStats",
    "NiePlayer",
    "bibliotheque",
    "chemin_bibliotheque",
]


class NieBytes(ctypes.Structure):
    """Tampon d'octets possédé par Rust — miroir exact de `NieBytes` côté `nie-ffi`.

    Le contrat de propriété est strict : tout `NieBytes` non vide rendu par la lib doit être
    libéré **exactement une fois**. `niepy` s'en charge dans `formats.prendre_octets`.
    """

    _fields_ = [
        ("ptr", ctypes.POINTER(ctypes.c_ubyte)),
        ("len", ctypes.c_size_t),
        ("cap", ctypes.c_size_t),
    ]


class NieCacheStats(ctypes.Structure):
    """Occupation du cache CPK — miroir de `NieCacheStats` côté `nie-ffi`.

    Le VFS garde les octets **bruts** de chaque paquet ouvert. Quelques lectures dans des
    paquets différents suffisent à retenir plusieurs centaines de mégaoctets, et le budget par
    défaut est dimensionné pour un traitement par lots (16 Gio), pas pour un jeu.
    """

    _fields_ = [
        ("octets", ctypes.c_uint64),
        ("entrees", ctypes.c_uint64),
        ("budget", ctypes.c_uint64),
    ]


class NiePlayer(ctypes.Structure):
    """Un joueur du match — miroir de `NiePlayer` côté `nie-ffi`."""

    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("vx", ctypes.c_float),
        ("vy", ctypes.c_float),
        ("team", ctypes.c_ubyte),
        ("role", ctypes.c_ubyte),
    ]


class NieBall(ctypes.Structure):
    """Le ballon — miroir de `NieBall` côté `nie-ffi`. `z` est la hauteur."""

    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
        ("vx", ctypes.c_float),
        ("vy", ctypes.c_float),
        ("vz", ctypes.c_float),
    ]


def _noms_possibles() -> list[str]:
    """Noms de fichier de la lib native, par plateforme.

    Sur Windows on cherche `iecode.dll` : c'est le nom commun de la bibliothèque.
    """
    if sys.platform == "win32":
        return ["iecode.dll", "libiecode.dll"]
    if sys.platform == "darwin":
        return ["libiecode.dylib", "iecode.dylib"]
    return ["libiecode.so", "iecode.so"]


def _racine_depot() -> Path | None:
    """Remonte les ancêtres jusqu'à un répertoire portant `Cargo.toml` et `crates/`.

    Aucun chemin de machine n'est écrit en dur — même règle que
    `nie_formats::vfs::resolve_game_dir` côté Rust.
    """
    for base in (Path(__file__).resolve(), Path.cwd().resolve()):
        for ancetre in (base, *base.parents):
            if (ancetre / "Cargo.toml").is_file() and (ancetre / "crates").is_dir():
                return ancetre
    return None


def _installed_library_candidates(names: list[str]) -> list[Path]:
    """Resolve the common user installation directory, then nonempty PATH entries."""
    directories = [Path.home() / ".local" / "bin"]
    directories.extend(
        Path(entry).expanduser() for entry in os.environ.get("PATH", "").split(os.pathsep) if entry
    )
    return [directory / name for directory in dict.fromkeys(directories) for name in names]


def chemin_bibliotheque() -> Path:
    """Résout le chemin de la lib native, ou lève `FileNotFoundError` en disant où chercher.

    Ordre : `NIE_FFI_PATH`, user install / PATH, puis `target/release` et `target/debug`
    sous la racine du dépôt.
    """
    force = os.environ.get("NIE_FFI_PATH", "").strip()
    if force:
        chemin = Path(force)
        if not chemin.is_file():
            raise FileNotFoundError(f"NIE_FFI_PATH pointe vers {chemin}, qui n'est pas un fichier.")
        return chemin

    racine = _racine_depot()
    candidats = _installed_library_candidates(_noms_possibles())
    if racine is not None:
        for profil in ("release", "debug"):
            candidats.extend(racine / "target" / profil / nom for nom in _noms_possibles())

    for candidat in candidats:
        if candidat.is_file():
            return candidat

    cherches = "\n  ".join(str(c) for c in candidats) or "  (racine du dépôt introuvable)"
    raise FileNotFoundError(
        "Bibliothèque native nie_ffi introuvable. Construis-la avec :\n"
        "    cargo build -p aphrody-nie-ffi --release\n"
        "puis relance. Chemins essayés :\n  " + cherches + "\n"
        "Tu peux aussi forcer NIE_FFI_PATH vers le fichier."
    )


_CACHE: ctypes.CDLL | None = None


def bibliotheque() -> ctypes.CDLL:
    """Charge la lib native une seule fois et déclare toutes les signatures utilisées.

    Le chargement est mémoïsé : `ctypes.CDLL` re-`dlopen` sinon à chaque appel.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    lib = ctypes.CDLL(str(chemin_bibliotheque()))
    _declarer(lib)
    _CACHE = lib
    return lib


def _declarer(lib: ctypes.CDLL) -> None:
    """Déclare `argtypes`/`restype` de chaque symbole. Sans cela, ctypes tronque les pointeurs."""
    p_ubyte = ctypes.POINTER(ctypes.c_ubyte)
    p_bytes = ctypes.POINTER(NieBytes)

    # ── Généralités ──────────────────────────────────────────────────────────
    lib.nie_version.argtypes = []
    lib.nie_version.restype = ctypes.c_char_p

    lib.nie_crc32.argtypes = [p_ubyte, ctypes.c_size_t]
    lib.nie_crc32.restype = ctypes.c_uint32

    # ── Mémoire ──────────────────────────────────────────────────────────────
    lib.nie_bytes_free_fields.argtypes = [p_ubyte, ctypes.c_size_t, ctypes.c_size_t]
    lib.nie_bytes_free_fields.restype = None

    # ── Formats ──────────────────────────────────────────────────────────────
    lib.nie_detect.argtypes = [p_ubyte, ctypes.c_size_t]
    lib.nie_detect.restype = ctypes.c_uint32

    lib.nie_format_name.argtypes = [ctypes.c_uint32]
    lib.nie_format_name.restype = ctypes.c_char_p

    if hasattr(lib, "nie_format_extension"):
        lib.nie_format_extension.argtypes = [ctypes.c_uint32]
        lib.nie_format_extension.restype = ctypes.c_char_p

        lib.nie_format_mime_type.argtypes = [ctypes.c_uint32]
        lib.nie_format_mime_type.restype = ctypes.c_char_p

        lib.nie_format_category.argtypes = [ctypes.c_uint32]
        lib.nie_format_category.restype = ctypes.c_char_p

        lib.nie_format_is_big_endian.argtypes = [ctypes.c_uint32]
        lib.nie_format_is_big_endian.restype = ctypes.c_bool

        lib.nie_format_supports_encryption.argtypes = [ctypes.c_uint32]
        lib.nie_format_supports_encryption.restype = ctypes.c_bool

        lib.nie_format_supports_compression.argtypes = [ctypes.c_uint32]
        lib.nie_format_supports_compression.restype = ctypes.c_bool

        lib.nie_format_count.argtypes = []
        lib.nie_format_count.restype = ctypes.c_uint32

        lib.nie_format_id_by_index.argtypes = [ctypes.c_uint32]
        lib.nie_format_id_by_index.restype = ctypes.c_uint32

        lib.nie_format_catalog_json_out.argtypes = [p_bytes]
        lib.nie_format_catalog_json_out.restype = None

    lib.nie_decode_json_out.argtypes = [p_ubyte, ctypes.c_size_t, p_bytes]
    lib.nie_decode_json_out.restype = None

    lib.nie_g4tx_to_png_out.argtypes = [p_ubyte, ctypes.c_size_t, p_bytes]
    lib.nie_g4tx_to_png_out.restype = None

    # ── VFS ──────────────────────────────────────────────────────────────────
    lib.nie_vfs_open.argtypes = [ctypes.c_char_p]
    lib.nie_vfs_open.restype = ctypes.c_void_p

    lib.nie_vfs_read_out.argtypes = [ctypes.c_void_p, ctypes.c_char_p, p_bytes]
    lib.nie_vfs_read_out.restype = None

    lib.nie_vfs_count.argtypes = [ctypes.c_void_p]
    lib.nie_vfs_count.restype = ctypes.c_size_t

    lib.nie_vfs_is_readable.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.nie_vfs_is_readable.restype = ctypes.c_uint32

    lib.nie_match_simulate_json_out.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_uint64,
        p_bytes,
    ]
    lib.nie_match_simulate_json_out.restype = None

    lib.nie_vfs_list_range_json_out.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_size_t,
        p_bytes,
    ]
    lib.nie_vfs_list_range_json_out.restype = None

    lib.nie_vfs_cache_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(NieCacheStats)]
    lib.nie_vfs_cache_stats.restype = None

    lib.nie_vfs_cache_vider.argtypes = [ctypes.c_void_p]
    lib.nie_vfs_cache_vider.restype = ctypes.c_uint64

    lib.nie_vfs_cache_budget.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.nie_vfs_cache_budget.restype = ctypes.c_uint64

    lib.nie_vfs_free.argtypes = [ctypes.c_void_p]
    lib.nie_vfs_free.restype = None

    # ── Moteur de match ──────────────────────────────────────────────────────
    lib.nie_world_new.argtypes = []
    lib.nie_world_new.restype = ctypes.c_void_p

    lib.nie_world_kickoff.argtypes = [ctypes.c_void_p]
    lib.nie_world_kickoff.restype = None

    lib.nie_world_step.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.nie_world_step.restype = None

    lib.nie_world_set_input.argtypes = [
        ctypes.c_void_p,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_bool,
    ]
    lib.nie_world_set_input.restype = None

    lib.nie_world_player_count.argtypes = [ctypes.c_void_p]
    lib.nie_world_player_count.restype = ctypes.c_size_t

    lib.nie_world_player.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(NiePlayer)]
    lib.nie_world_player.restype = ctypes.c_bool

    lib.nie_world_ball.argtypes = [ctypes.c_void_p, ctypes.POINTER(NieBall)]
    lib.nie_world_ball.restype = None

    lib.nie_world_score.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.nie_world_score.restype = None

    lib.nie_world_time.argtypes = [ctypes.c_void_p]
    lib.nie_world_time.restype = ctypes.c_float

    lib.nie_world_tick.argtypes = [ctypes.c_void_p]
    lib.nie_world_tick.restype = ctypes.c_uint64

    lib.nie_world_possessor.argtypes = [ctypes.c_void_p]
    lib.nie_world_possessor.restype = ctypes.c_ssize_t

    lib.nie_world_snapshot_json_out.argtypes = [ctypes.c_void_p, p_bytes]
    lib.nie_world_snapshot_json_out.restype = None

    lib.nie_world_free.argtypes = [ctypes.c_void_p]
    lib.nie_world_free.restype = None

    # ── Diagnostics & Métadonnées ────────────────────────────────────────────
    if hasattr(lib, "nie_last_error_out"):
        lib.nie_last_error_out.argtypes = [p_bytes]
        lib.nie_last_error_out.restype = None

    if hasattr(lib, "nie_build_info_json_out"):
        lib.nie_build_info_json_out.argtypes = [p_bytes]
        lib.nie_build_info_json_out.restype = None

    # ── CPK & CRILAYLA (Rust natif) ──────────────────────────────────────────
    if hasattr(lib, "nie_cpk_key_from_filename"):
        lib.nie_cpk_key_from_filename.argtypes = [ctypes.c_char_p]
        lib.nie_cpk_key_from_filename.restype = ctypes.c_uint32

    if hasattr(lib, "nie_cpk_decrypt_block"):
        lib.nie_cpk_decrypt_block.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_uint64,
            ctypes.c_uint32,
        ]
        lib.nie_cpk_decrypt_block.restype = None

    if hasattr(lib, "nie_crilayla_is_compressed"):
        lib.nie_crilayla_is_compressed.argtypes = [p_ubyte, ctypes.c_size_t]
        lib.nie_crilayla_is_compressed.restype = ctypes.c_uint32

    if hasattr(lib, "nie_crilayla_decompress_out"):
        lib.nie_crilayla_decompress_out.argtypes = [p_ubyte, ctypes.c_size_t, p_bytes]
        lib.nie_crilayla_decompress_out.restype = None

    if hasattr(lib, "nie_crilayla_compress_out"):
        lib.nie_crilayla_compress_out.argtypes = [p_ubyte, ctypes.c_size_t, p_bytes]
        lib.nie_crilayla_compress_out.restype = None

    if hasattr(lib, "nie_cpk_probe"):
        lib.nie_cpk_probe.argtypes = [p_ubyte, ctypes.c_size_t]
        lib.nie_cpk_probe.restype = ctypes.c_uint32

    if hasattr(lib, "nie_cpk_header_json_out"):
        lib.nie_cpk_header_json_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
            p_bytes,
        ]
        lib.nie_cpk_header_json_out.restype = None

    # ── G4TX & CFGBIN ────────────────────────────────────────────────────────
    if hasattr(lib, "nie_g4tx_info_json_out"):
        lib.nie_g4tx_info_json_out.argtypes = [p_ubyte, ctypes.c_size_t, p_bytes]
        lib.nie_g4tx_info_json_out.restype = None

    if hasattr(lib, "nie_cfgbin_probe"):
        lib.nie_cfgbin_probe.argtypes = [p_ubyte, ctypes.c_size_t]
        lib.nie_cfgbin_probe.restype = ctypes.c_uint32

    if hasattr(lib, "nie_cfgbin_to_json_out"):
        lib.nie_cfgbin_to_json_out.argtypes = [p_ubyte, ctypes.c_size_t, p_bytes]
        lib.nie_cfgbin_to_json_out.restype = None

    # ── CPK Extraction & Queries ─────────────────────────────────────────────
    if hasattr(lib, "nie_cpk_list_json_out"):
        lib.nie_cpk_list_json_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
            p_bytes,
        ]
        lib.nie_cpk_list_json_out.restype = None

    if hasattr(lib, "nie_cpk_extract_entry_out"):
        lib.nie_cpk_extract_entry_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_size_t,
            p_bytes,
        ]
        lib.nie_cpk_extract_entry_out.restype = None

    if hasattr(lib, "nie_cpk_extract_by_name_out"):
        lib.nie_cpk_extract_by_name_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_char_p,
            p_bytes,
        ]
        lib.nie_cpk_extract_by_name_out.restype = None

    if hasattr(lib, "nie_rdbn_entry_query_json_out"):
        lib.nie_rdbn_entry_query_json_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
            p_bytes,
        ]
        lib.nie_rdbn_entry_query_json_out.restype = None

    # ── G4TX Subtextures & Probe ────────────────────────────────────────────
    if hasattr(lib, "nie_g4tx_probe"):
        lib.nie_g4tx_probe.argtypes = [p_ubyte, ctypes.c_size_t]
        lib.nie_g4tx_probe.restype = ctypes.c_uint32

    if hasattr(lib, "nie_g4tx_to_rgba_out"):
        lib.nie_g4tx_to_rgba_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            p_bytes,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        lib.nie_g4tx_to_rgba_out.restype = ctypes.c_uint32

    if hasattr(lib, "nie_g4tx_subtexture_to_png_out"):
        lib.nie_g4tx_subtexture_to_png_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
            p_bytes,
        ]
        lib.nie_g4tx_subtexture_to_png_out.restype = None

    # ── VFS File Info ────────────────────────────────────────────────────────
    if hasattr(lib, "nie_vfs_file_info_json_out"):
        lib.nie_vfs_file_info_json_out.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            p_bytes,
        ]
        lib.nie_vfs_file_info_json_out.restype = None

    # ── Sauvegardes Lives (002AB8F4-*) ───────────────────────────────────────
    if hasattr(lib, "nie_save_probe"):
        lib.nie_save_probe.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
        ]
        lib.nie_save_probe.restype = ctypes.c_uint32

    if hasattr(lib, "nie_save_summary_json_out"):
        lib.nie_save_summary_json_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
            p_bytes,
        ]
        lib.nie_save_summary_json_out.restype = None

    if hasattr(lib, "nie_save_extract_blob_out"):
        lib.nie_save_extract_blob_out.argtypes = [
            p_ubyte,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_size_t,
            p_bytes,
        ]
        lib.nie_save_extract_blob_out.restype = None

    # ── CRand (Mersenne Twister MT19937) ────────────────────────────────────
    if hasattr(lib, "nie_crc32_nie"):
        lib.nie_crc32_nie.argtypes = [p_ubyte, ctypes.c_size_t]
        lib.nie_crc32_nie.restype = ctypes.c_uint32

    if hasattr(lib, "nie_crand_new"):
        lib.nie_crand_new.argtypes = [ctypes.c_uint32]
        lib.nie_crand_new.restype = ctypes.c_void_p

    if hasattr(lib, "nie_crand_from_u64"):
        lib.nie_crand_from_u64.argtypes = [ctypes.c_uint64]
        lib.nie_crand_from_u64.restype = ctypes.c_void_p

    if hasattr(lib, "nie_crand_next_u32"):
        lib.nie_crand_next_u32.argtypes = [ctypes.c_void_p]
        lib.nie_crand_next_u32.restype = ctypes.c_uint32

    if hasattr(lib, "nie_crand_bounded"):
        lib.nie_crand_bounded.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        lib.nie_crand_bounded.restype = ctypes.c_uint32

    if hasattr(lib, "nie_crand_next_f32"):
        lib.nie_crand_next_f32.argtypes = [ctypes.c_void_p]
        lib.nie_crand_next_f32.restype = ctypes.c_float

    if hasattr(lib, "nie_crand_free"):
        lib.nie_crand_free.argtypes = [ctypes.c_void_p]
        lib.nie_crand_free.restype = None

    # ── Émulateur & Registre ─────────────────────────────────────────────────
    if hasattr(lib, "nie_emu_registry_json_out"):
        lib.nie_emu_registry_json_out.argtypes = [p_bytes]
        lib.nie_emu_registry_json_out.restype = None
