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

from ._ffi import _racine_depot

__all__ = [
    "IecodeBridge",
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

    racine = _racine_depot()
    if racine is None:
        return None

    candidats: list[Path] = []
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
                "    dotnet publish src/IECODE/Ffi/IECODE.Ffi.csproj -c Release /p:PublishAot=true\n"
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
            return bytes(ctypes.cast(out_ptr, ctypes.POINTER(ctypes.c_ubyte * out_len.value)).contents)
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
            return bytes(ctypes.cast(out_ptr, ctypes.POINTER(ctypes.c_ubyte * out_len.value)).contents)
        finally:
            b.lib.iecode_bytes_free(out_ptr)

    @classmethod
    def est_rdbn_valide(cls, donnees: bytes) -> bool:
        """Vérifie si le tampon commence par un en-tête RDBN valide."""
        b = cls._obtenir_bindings()
        buf = (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)
        return bool(b.lib.iecode_rdbn_is_valid(buf, len(donnees)))
