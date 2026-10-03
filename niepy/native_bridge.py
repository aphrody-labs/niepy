"""Pont natif unifié IECODE : interopérabilité directe avec IECODE.Core (.NET 10 NativeAOT) et aphrody-nie-ffi (Rust).

Permet d'exécuter l'ensemble des algorithmes de bas niveau (Level-5 CRC32, CRILAYLA,
détection de formats, déchiffrement CPK) directement en mémoire native sans passer
par un sous-processus.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Any

from ._ffi import _installed_library_candidates, _racine_depot

__all__ = [
    "IecodeBridge",
    "NieFfiPure",
    "chemin_iecode_ffi",
]


def _noms_iecode_possibles() -> list[str]:
    """Noms de fichiers possibles pour IECODE.Ffi selon la plateforme."""
    if sys.platform == "win32":
        return ["IECODE.Ffi.dll", "iecode_ffi.dll"]
    if sys.platform == "darwin":
        return ["IECODE.Ffi.dylib", "libIECODE.Ffi.dylib"]
    return ["IECODE.Ffi.so", "libIECODE.Ffi.so"]


def chemin_iecode_ffi() -> Path | None:
    """Résout le chemin de la bibliothèque native IECODE.Ffi (NativeAOT C#)."""
    force = os.environ.get("IECODE_FFI_PATH", "").strip()
    if force:
        p = Path(force)
        if p.is_file():
            return p

    candidats = _installed_library_candidates(_noms_iecode_possibles())
    for candidate in candidats:
        if candidate.is_file():
            return candidate

    racine = _racine_depot()
    if racine is None:
        return None
    # Chemins NativeAOT sous src/IECODE/Ffi/bin
    for profil in ("Release", "Debug"):
        for sub in ("publish", "native", ""):
            for arch in ("linux-x64", "win-x64", "osx-x64", ""):
                base = racine / "src" / "IECODE" / "Ffi" / "bin" / profil / "net10.0"
                if arch:
                    base = base / arch
                if sub:
                    base = base / sub
                for nom in _noms_iecode_possibles():
                    candidats.append(base / nom)

    for c in candidats:
        if c.is_file():
            return c
    return None


class _IecodeFfiBindings:
    """Chargement et typage strict des symboles exportés par IECODE.Ffi."""

    def __init__(self, path: Path) -> None:
        self.lib = ctypes.CDLL(str(path))
        self._declarer()

    def _declarer(self) -> None:
        p_ubyte = ctypes.POINTER(ctypes.c_ubyte)
        pp_ubyte = ctypes.POINTER(p_ubyte)
        p_int = ctypes.POINTER(ctypes.c_int)

        self.lib.iecode_core_version.argtypes = []
        self.lib.iecode_core_version.restype = ctypes.c_char_p

        self.lib.iecode_ffi_schema.argtypes = []
        self.lib.iecode_ffi_schema.restype = ctypes.c_char_p

        self.lib.iecode_status.argtypes = []
        self.lib.iecode_status.restype = ctypes.c_int

        self.lib.iecode_level5_crc32.argtypes = [p_ubyte, ctypes.c_int]
        self.lib.iecode_level5_crc32.restype = ctypes.c_uint32

        self.lib.iecode_format_detect.argtypes = [p_ubyte, ctypes.c_int]
        self.lib.iecode_format_detect.restype = ctypes.c_int

        self.lib.iecode_cpk_decrypt_block.argtypes = [
            p_ubyte,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_uint64,
        ]
        self.lib.iecode_cpk_decrypt_block.restype = ctypes.c_int

        self.lib.iecode_crilayla_decompress.argtypes = [
            p_ubyte,
            ctypes.c_int,
            pp_ubyte,
            p_int,
        ]
        self.lib.iecode_crilayla_decompress.restype = ctypes.c_int

        self.lib.iecode_crilayla_compress.argtypes = [
            p_ubyte,
            ctypes.c_int,
            pp_ubyte,
            p_int,
        ]
        self.lib.iecode_crilayla_compress.restype = ctypes.c_int

        self.lib.iecode_rdbn_is_valid.argtypes = [p_ubyte, ctypes.c_int]
        self.lib.iecode_rdbn_is_valid.restype = ctypes.c_int

        self.lib.iecode_bytes_free.argtypes = [p_ubyte]
        self.lib.iecode_bytes_free.restype = None


class IecodeBridge:
    """Interface unifiée Python vers les algorithmes natifs de IECODE.Core."""

    _instance: _IecodeFfiBindings | None = None

    @classmethod
    def est_disponible(cls) -> bool:
        """Vérifie si le module natif IECODE.Ffi est disponible."""
        if cls._instance is not None:
            return True
        p = chemin_iecode_ffi()
        return p is not None and p.is_file()

    @classmethod
    def _obtenir_bindings(cls) -> _IecodeFfiBindings:
        if cls._instance is not None:
            return cls._instance
        p = chemin_iecode_ffi()
        if p is None:
            raise FileNotFoundError(
                "Bibliothèque IECODE.Ffi introuvable. Construisez-la avec :\n"
                "    dotnet publish src/IECODE/Ffi/IECODE.Ffi.csproj -c Release -r linux-x64 -p:PublishAot=true -p:NativeLib=Shared\n"
                "ou définissez la variable d'environnement IECODE_FFI_PATH."
            )
        cls._instance = _IecodeFfiBindings(p)
        return cls._instance

    @classmethod
    def version(cls) -> str:
        """Version de IECODE.Core exposée par FFI."""
        b = cls._obtenir_bindings()
        v = b.lib.iecode_core_version()
        return v.decode("utf-8") if v else ""

    @classmethod
    def schema(cls) -> str:
        """Schéma FFI de IECODE.Core."""
        b = cls._obtenir_bindings()
        s = b.lib.iecode_ffi_schema()
        return s.decode("utf-8") if s else ""

    @classmethod
    def crc32(cls, donnees: bytes) -> int:
        """Calcule le CRC32 Level-5 (ISO 3309 reflected, poly 0xEDB88320)."""
        b = cls._obtenir_bindings()
        buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
        return int(b.lib.iecode_level5_crc32(buf, len(donnees)))

    @classmethod
    def detecter_format(cls, donnees: bytes) -> int:
        """Détecte l'identifiant numérique de format via FormatDetector de IECODE.Core."""
        b = cls._obtenir_bindings()
        buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
        return int(b.lib.iecode_format_detect(buf, len(donnees)))

    @classmethod
    def dechiffrer_bloc_cpk(cls, donnees: bytes, cle: int = 0, offset: int = 0) -> bytes:
        """Déchiffre un bloc CRI position-XOR in-place ou sur une copie."""
        b = cls._obtenir_bindings()
        buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
        ret = b.lib.iecode_cpk_decrypt_block(buf, len(donnees), cle, offset)
        if ret != 0:
            raise RuntimeError(f"Échec déchiffrement bloc CPK (code {ret})")
        return bytes(buf)

    @classmethod
    def decompresser_crilayla(cls, donnees: bytes) -> bytes:
        """Décompresse un flux CRILAYLA via CriLayla de IECODE.Core."""
        b = cls._obtenir_bindings()
        in_buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
        out_ptr = ctypes.POINTER(ctypes.c_ubyte)()
        out_len = ctypes.c_int(0)

        ret = b.lib.iecode_crilayla_decompress(
            in_buf, len(donnees), ctypes.byref(out_ptr), ctypes.byref(out_len)
        )
        if ret != 0 or not out_ptr:
            raise ValueError(f"Échec de décompression CRILAYLA (code d'erreur {ret})")

        try:
            return bytes(
                ctypes.cast(out_ptr, ctypes.POINTER(ctypes.c_ubyte * out_len.value)).contents
            )
        finally:
            b.lib.iecode_bytes_free(out_ptr)

    @classmethod
    def compresser_crilayla(cls, donnees: bytes) -> bytes:
        """Compresse un flux brut en conteneur CRILAYLA."""
        b = cls._obtenir_bindings()
        in_buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
        out_ptr = ctypes.POINTER(ctypes.c_ubyte)()
        out_len = ctypes.c_int(0)

        ret = b.lib.iecode_crilayla_compress(
            in_buf, len(donnees), ctypes.byref(out_ptr), ctypes.byref(out_len)
        )
        if ret != 0 or not out_ptr:
            raise ValueError(f"Échec de compression CRILAYLA (code d'erreur {ret})")

        try:
            return bytes(
                ctypes.cast(out_ptr, ctypes.POINTER(ctypes.c_ubyte * out_len.value)).contents
            )
        finally:
            b.lib.iecode_bytes_free(out_ptr)

    @classmethod
    def est_rdbn_valide(cls, donnees: bytes) -> bool:
        """Vérifie si le tampon commence par un en-tête RDBN valide."""
        b = cls._obtenir_bindings()
        buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
        return bool(b.lib.iecode_rdbn_is_valid(buf, len(donnees)))


class NieFfiPure:
    """Interface pure et complète vers les fonctionnalités natives de aphrody-nie-ffi (Rust)."""

    @classmethod
    def version(cls) -> str:
        """Version du crate native nie_ffi."""
        from .formats import version

        return version()

    @classmethod
    def info_build(cls) -> dict[str, Any]:
        """Informations de build et capacités du moteur Rust."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import json

        lib = bibliotheque()
        if hasattr(lib, "nie_build_info_json_out"):
            out = NieBytes()
            lib.nie_build_info_json_out(ctypes.byref(out))
            b = prendre_octets(out)
            return json.loads(b) if b else {}
        return {}

    @classmethod
    def deriver_cle_cpk(cls, nom_fichier: str) -> int:
        """Dérive la clé CPK depuis le nom de fichier."""
        from ._ffi import bibliotheque

        lib = bibliotheque()
        if hasattr(lib, "nie_cpk_key_from_filename"):
            return int(lib.nie_cpk_key_from_filename(nom_fichier.encode("utf-8")))
        return 0

    @classmethod
    def sonder_cpk(cls, donnees: bytes) -> bool:
        """Vérifie si le tampon est une archive CPK."""
        from ._ffi import bibliotheque

        lib = bibliotheque()
        if hasattr(lib, "nie_cpk_probe"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            return bool(lib.nie_cpk_probe(buf, len(donnees)))
        return donnees.startswith(b"CPK ")

    @classmethod
    def sonder_cfgbin(cls, donnees: bytes) -> int:
        """Détecte le sous-type d'un cfg.bin (1 = RDBN, 2 = T2B, 0 = Inconnu)."""
        from ._ffi import bibliotheque

        lib = bibliotheque()
        if hasattr(lib, "nie_cfgbin_probe"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            return int(lib.nie_cfgbin_probe(buf, len(donnees)))
        return 1 if donnees.startswith(b"RDBN") else 0

    @classmethod
    def info_g4tx(cls, donnees: bytes) -> dict[str, Any]:
        """Extrait la structure et les sous-textures d'un fichier G4TX."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import json

        lib = bibliotheque()
        if hasattr(lib, "nie_g4tx_info_json_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_g4tx_info_json_out(buf, len(donnees), ctypes.byref(out))
            b = prendre_octets(out)
            return json.loads(b) if b else {}
        return {}

    @classmethod
    def crc32_nie(cls, donnees: bytes) -> int:
        """Calcule l'accumulateur brut CRC32 sans inversion (poly 0xEDB88320)."""
        from ._ffi import bibliotheque

        lib = bibliotheque()
        if hasattr(lib, "nie_crc32_nie"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            return int(lib.nie_crc32_nie(buf, len(donnees)))
        from .crypto import crc32_nie

        return crc32_nie(donnees)

    @classmethod
    def cpk_lister(cls, donnees: bytes, nom_fichier: str = "") -> dict[str, Any]:
        """Liste l'ensemble des entrées d'un conteneur CPK."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import json

        lib = bibliotheque()
        if hasattr(lib, "nie_cpk_list_json_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_cpk_list_json_out(
                buf, len(donnees), nom_fichier.encode("utf-8"), ctypes.byref(out)
            )
            b = prendre_octets(out)
            return json.loads(b) if b else {}
        return {}

    @classmethod
    def cpk_extraire_entree(cls, donnees: bytes, nom_fichier: str, index: int) -> bytes:
        """Extrait une entrée CPK par son indice ordinal."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets

        lib = bibliotheque()
        if hasattr(lib, "nie_cpk_extract_entry_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_cpk_extract_entry_out(
                buf, len(donnees), nom_fichier.encode("utf-8"), index, ctypes.byref(out)
            )
            return prendre_octets(out)
        return b""

    @classmethod
    def cpk_extraire_par_nom(cls, donnees: bytes, nom_fichier: str, nom_entree: str) -> bytes:
        """Extrait une entrée CPK par son nom interne."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets

        lib = bibliotheque()
        if hasattr(lib, "nie_cpk_extract_by_name_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_cpk_extract_by_name_out(
                buf,
                len(donnees),
                nom_fichier.encode("utf-8"),
                nom_entree.encode("utf-8"),
                ctypes.byref(out),
            )
            return prendre_octets(out)
        return b""

    @classmethod
    def cfgbin_vers_json(cls, donnees: bytes) -> dict[str, Any]:
        """Convertit un fichier RDBN / T2B en JSON canonique."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import json

        lib = bibliotheque()
        if hasattr(lib, "nie_cfgbin_to_json_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_cfgbin_to_json_out(buf, len(donnees), ctypes.byref(out))
            b = prendre_octets(out)
            return json.loads(b) if b else {}
        return {}

    @classmethod
    def rdbn_requete_table(cls, donnees: bytes, nom_table: str) -> dict[str, Any] | None:
        """Extrait une table nommée d'un fichier RDBN."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import json

        lib = bibliotheque()
        if hasattr(lib, "nie_rdbn_entry_query_json_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_rdbn_entry_query_json_out(
                buf, len(donnees), nom_table.encode("utf-8"), ctypes.byref(out)
            )
            b = prendre_octets(out)
            return json.loads(b) if b else None
        return None

    @classmethod
    def g4tx_sonder(cls, donnees: bytes) -> bool:
        """Vérifie si le tampon est un conteneur G4TX."""
        from ._ffi import bibliotheque

        lib = bibliotheque()
        if hasattr(lib, "nie_g4tx_probe"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            return bool(lib.nie_g4tx_probe(buf, len(donnees)))
        return donnees.startswith(b"G4TX")

    @classmethod
    def g4tx_sous_texture_vers_png(cls, donnees: bytes, nom_sous_texture: str) -> bytes:
        """Décode une sous-texture nommée en PNG."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets

        lib = bibliotheque()
        if hasattr(lib, "nie_g4tx_subtexture_to_png_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_g4tx_subtexture_to_png_out(
                buf, len(donnees), nom_sous_texture.encode("utf-8"), ctypes.byref(out)
            )
            return prendre_octets(out)
        return b""

    @classmethod
    def vfs_info_fichier(cls, handle_vfs: int, chemin_interne: str) -> dict[str, Any]:
        """Retourne les métadonnées d'un fichier virtuel."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import json

        lib = bibliotheque()
        if hasattr(lib, "nie_vfs_file_info_json_out"):
            out = NieBytes()
            lib.nie_vfs_file_info_json_out(
                handle_vfs, chemin_interne.encode("utf-8"), ctypes.byref(out)
            )
            b = prendre_octets(out)
            return json.loads(b) if b else {}
        return {}

    @classmethod
    def save_sonder(cls, donnees: bytes, nom_fichier: str) -> bool:
        """Vérifie si le tampon est une sauvegarde Lives valide."""
        from ._ffi import bibliotheque

        lib = bibliotheque()
        if hasattr(lib, "nie_save_probe"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            return bool(lib.nie_save_probe(buf, len(donnees), nom_fichier.encode("utf-8")))
        return False

    @classmethod
    def save_resume(cls, donnees: bytes, nom_fichier: str) -> dict[str, Any]:
        """Déchiffre et résume une sauvegarde Lives."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import json

        lib = bibliotheque()
        if hasattr(lib, "nie_save_summary_json_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_save_summary_json_out(
                buf, len(donnees), nom_fichier.encode("utf-8"), ctypes.byref(out)
            )
            b = prendre_octets(out)
            return json.loads(b) if b else {}
        return {}

    @classmethod
    def save_extraire_blob(cls, donnees: bytes, nom_fichier: str, index_blob: int) -> bytes:
        """Extrait un blob déchiffré d'une sauvegarde Lives."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets

        lib = bibliotheque()
        if hasattr(lib, "nie_save_extract_blob_out"):
            buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
            out = NieBytes()
            lib.nie_save_extract_blob_out(
                buf, len(donnees), nom_fichier.encode("utf-8"), index_blob, ctypes.byref(out)
            )
            return prendre_octets(out)
        return b""

    @classmethod
    def emu_registre(cls) -> dict[str, Any]:
        """Retourne la matrice backend/capability de l'émulateur."""
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import json

        lib = bibliotheque()
        if hasattr(lib, "nie_emu_registry_json_out"):
            out = NieBytes()
            lib.nie_emu_registry_json_out(ctypes.byref(out))
            b = prendre_octets(out)
            return json.loads(b) if b else {}
        return {}
