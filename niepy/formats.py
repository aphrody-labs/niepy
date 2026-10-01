"""Décodage des formats du jeu : détection, `cfg.bin` → dict, G4TX → PNG.

Le travail réel est fait par `nie-formats` en Rust. Ce module ne fait que traverser la
frontière FFI et rendre des objets Python.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import IntEnum
import json
from typing import Any

from ._ffi import NieBytes, bibliotheque

__all__ = [
    "VfsFormatConsumer",
    "VfsFormatDescriptor",
    "VfsFormatId",
    "decoder",
    "detect_format",
    "detecter",
    "g4tx_vers_png",
    "get_format_descriptor",
    "list_vfs_formats",
    "nom_format",
    "prendre_octets",
    "validate_format",
    "version",
]


class VfsFormatId(IntEnum):
    """Canonical VFS format discriminants matching the 28-format registry."""

    UNKNOWN = 0
    G4TX = 1
    G4MD = 2
    G4MG = 3
    G4MT = 4
    G4SK = 5
    G4PK = 6
    G4RA = 7
    AGI = 8
    OBJB = 9
    COL = 10
    CFGBIN = 11
    MEVS = 12
    G4CM = 13
    CPK = 14
    AWB = 15
    UTF = 16
    DDS = 17
    PNG = 18
    RIFF = 19
    XPCK = 20
    XFSA = 21
    CRILAYLA = 22
    ACB = 23
    USM = 24
    G4NV = 25
    COL_MESH = 26
    COLS = 27
    LIVE = 28


@dataclass(frozen=True)
class VfsFormatDescriptor:
    """Strongly-typed VFS format descriptor."""

    id: int
    name: str
    extension: str
    mime_type: str
    category: str
    is_big_endian: bool
    encryption_supported: bool
    compression_supported: bool
    description: str = ""


def prendre_octets(tampon: NieBytes) -> bytes:
    """Copie un `NieBytes` en `bytes` Python **et libère la mémoire Rust**.

    C'est le seul point de la bibliothèque qui libère un tampon natif. Il est appelé
    exactement une fois par tampon, y compris quand celui-ci est vide : la lib traite le
    pointeur null comme un no-op, mais la copie doit quand même rendre `b""`.
    """
    if not tampon.ptr:
        return b""
    try:
        return bytes(ctypes.cast(tampon.ptr, ctypes.POINTER(ctypes.c_ubyte * tampon.len)).contents)
    finally:
        bibliotheque().nie_bytes_free_fields(tampon.ptr, tampon.len, tampon.cap)


def _vue(donnees: bytes):
    """Rend un pointeur `c_ubyte*` sur un `bytes` Python, sans copie."""
    return (ctypes.c_ubyte * len(donnees)).from_buffer_copy(donnees)


def version() -> str:
    """Version du crate `nie-ffi` chargé."""
    brut = bibliotheque().nie_version()
    return brut.decode("utf-8") if brut else "?"


def detecter(donnees: bytes) -> int:
    """Discriminant numérique stable du format d'un tampon."""
    tampon = _vue(donnees)
    return int(bibliotheque().nie_detect(tampon, len(donnees)))


def nom_format(discriminant: int) -> str:
    """Nom court d'un format, depuis son discriminant."""
    brut = bibliotheque().nie_format_name(discriminant)
    return brut.decode("utf-8") if brut else "inconnu"


def decoder(donnees: bytes) -> Any:
    """Décode un tampon par auto-détection et rend la structure Python correspondante.

    Lève `ValueError` quand le format n'est pas géré — la lib rend alors un tampon vide,
    qu'il serait trompeur de confondre avec un document vide légitime.
    """
    tampon = _vue(donnees)
    sortie = NieBytes()
    bibliotheque().nie_decode_json_out(tampon, len(donnees), ctypes.byref(sortie))
    brut = prendre_octets(sortie)
    if not brut:
        nom = nom_format(detecter(donnees))
        raise ValueError(f"format non décodable en JSON (détecté : {nom})")
    return json.loads(brut)


def g4tx_vers_png(donnees: bytes) -> bytes:
    """Décode la première texture d'un G4TX et rend les octets PNG.

    Lève `ValueError` si le tampon n'est pas un G4TX exploitable.
    """
    tampon = _vue(donnees)
    sortie = NieBytes()
    bibliotheque().nie_g4tx_to_png_out(tampon, len(donnees), ctypes.byref(sortie))
    png = prendre_octets(sortie)
    if not png:
        raise ValueError("G4TX non décodable en PNG")
    return png


def get_format_descriptor(fmt_id: int) -> VfsFormatDescriptor:
    """Returns the strongly-typed descriptor for a format ID."""
    lib = bibliotheque()
    name = nom_format(fmt_id)
    if not hasattr(lib, "nie_format_extension") or fmt_id <= 0:
        return VfsFormatDescriptor(
            id=fmt_id,
            name=name,
            extension=".bin",
            mime_type="application/octet-stream",
            category="system",
            is_big_endian=False,
            encryption_supported=False,
            compression_supported=False,
            description="Unknown format",
        )

    ext = (
        lib.nie_format_extension(fmt_id).decode("utf-8")
        if lib.nie_format_extension(fmt_id)
        else ".bin"
    )
    mime = (
        lib.nie_format_mime_type(fmt_id).decode("utf-8")
        if lib.nie_format_mime_type(fmt_id)
        else "application/octet-stream"
    )
    cat = (
        lib.nie_format_category(fmt_id).decode("utf-8")
        if lib.nie_format_category(fmt_id)
        else "system"
    )
    is_be = bool(lib.nie_format_is_big_endian(fmt_id))
    enc = bool(lib.nie_format_supports_encryption(fmt_id))
    comp = bool(lib.nie_format_supports_compression(fmt_id))

    return VfsFormatDescriptor(
        id=fmt_id,
        name=name,
        extension=ext,
        mime_type=mime,
        category=cat,
        is_big_endian=is_be,
        encryption_supported=enc,
        compression_supported=comp,
    )


def detect_format(data: bytes) -> VfsFormatDescriptor:
    """Detects and returns the format descriptor from byte content."""
    fmt_id = detecter(data)
    return get_format_descriptor(fmt_id)


def list_vfs_formats() -> list[VfsFormatDescriptor]:
    """Returns all 28 canonical VFS format descriptors."""
    lib = bibliotheque()
    if hasattr(lib, "nie_format_catalog_json_out"):
        sortie = NieBytes()
        lib.nie_format_catalog_json_out(ctypes.byref(sortie))
        raw = prendre_octets(sortie)
        if raw:
            items = json.loads(raw)
            return [
                VfsFormatDescriptor(
                    id=item["id"],
                    name=item["name"],
                    extension=item["extension"],
                    mime_type=item["mime_type"],
                    category=item["category"],
                    is_big_endian=item["is_big_endian"],
                    encryption_supported=item["encryption_supported"],
                    compression_supported=item["compression_supported"],
                    description=item.get("description", ""),
                )
                for item in items
            ]
    return [get_format_descriptor(i) for i in range(1, 29)]


def validate_format(expected_id: int, data: bytes) -> bool:
    """Checks whether the data starts with the expected format header."""
    return detecter(data) == expected_id


class VfsFormatConsumer:
    """Universal VFS Format Consumer in Python."""

    @staticmethod
    def detect(data: bytes) -> VfsFormatDescriptor:
        return detect_format(data)

    @staticmethod
    def get(fmt_id: int) -> VfsFormatDescriptor:
        return get_format_descriptor(fmt_id)

    @staticmethod
    def list_all() -> list[VfsFormatDescriptor]:
        return list_vfs_formats()

    @staticmethod
    def validate(fmt_id: int, data: bytes) -> bool:
        return validate_format(fmt_id, data)
