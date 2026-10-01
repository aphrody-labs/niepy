"""Analyseurs et décodeurs de structures binaires du VFS et de `nie.exe`.

Couvre RDBN (cfg.bin / T2B), G4TX (textures DDS & sous-textures atlas),
CRI CPK (en-têtes & extraction), et sauvegardes Lives (002AB8F4-*).
"""

from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass
import json
import struct
from typing import Any

from ._ffi import NieBytes, bibliotheque
from .crypto import (
    CRILAYLA_RAW_HEADER_SIZE,
    decompress_crilayla,
    is_crilayla,
)
from .formats import prendre_octets
from .nie_re import (
    CRI_ENCRYPTED_TABLE_MAGIC,
    LIVES_BLOB_MAGIC,
    LIVES_SAVE_CONST2,
    LIVES_SAVE_HEADER_MAGIC,
)

__all__ = [
    "CpkHeaderInfo",
    "G4txHeaderInfo",
    "G4txSubTexture",
    "G4txTexture",
    "RdbnHeaderInfo",
    "cpk_extract_by_name",
    "cpk_extract_entry",
    "cpk_info",
    "cpk_list_entries",
    "g4tx_info",
    "g4tx_subtexture_to_png",
    "is_cpk",
    "is_g4tx",
    "is_live_save",
    "is_rdbn",
    "is_t2b",
    "parse_cpk_header",
    "parse_g4tx_header",
    "parse_rdbn_header",
    "rdbn_query_table",
    "rdbn_to_json",
    "save_extract_blob",
    "save_summary",
]

RDBN_MAGIC = 0x4E424452  # 'RDBN'
G4TX_MAGIC = 0x58543447  # 'G4TX'
CPK_MAGIC = 0x204B5043  # 'CPK '
UTF_MAGIC = 0x00465455  # '@UTF' (BE)


def _align(offset: int, boundary: int) -> int:
    return (offset + (boundary - 1)) & ~(boundary - 1)


# ─────────────────────────────────────────────────────────────────────────────
# RDBN / cfg.bin
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RdbnHeaderInfo:
    magic: int
    header_size: int
    version: int
    data_offset: int
    data_size: int
    type_offset: int
    type_count: int
    field_offset: int
    field_count: int
    root_offset: int
    root_count: int
    string_hash_offset: int
    string_offsets_offset: int
    hash_count: int
    value_offset: int
    string_offset: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_rdbn(data: bytes | bytearray | memoryview) -> bool:
    """Dit si le tampon débute par un magic RDBN valide."""
    if len(data) < 8:
        return False
    magic = struct.unpack_from("<I", data, 0)[0]
    return magic == RDBN_MAGIC


def is_t2b(data: bytes | bytearray | memoryview) -> bool:
    """Dit si le tampon est un binaire T2B (magic T2B ou format tabulaire L5)."""
    if len(data) < 4:
        return False
    return bytes(data[:4]) in (b"T2B\x00", b"T2B ", b"\x00B2T")


def parse_rdbn_header(data: bytes | bytearray | memoryview) -> RdbnHeaderInfo:
    """Lit et valide l'en-tête de 80 octets d'un fichier RDBN (cfg.bin)."""
    b = bytes(data)
    if len(b) < 0x50:
        raise ValueError(f"Tampon RDBN trop court : >= 0x50 attendu, reçu {len(b)}")

    magic, header_size, version = struct.unpack_from("<IHI", b, 0x00)
    if magic != RDBN_MAGIC:
        raise ValueError(f"Magic RDBN invalide : 0x{magic:08X} au lieu de 0x{RDBN_MAGIC:08X}")

    data_offset = struct.unpack_from("<H", b, 0x0A)[0] * 4
    data_size = struct.unpack_from("<I", b, 0x0C)[0]
    type_offset = struct.unpack_from("<H", b, 0x24)[0] * 4
    type_count = struct.unpack_from("<H", b, 0x26)[0]
    field_offset = struct.unpack_from("<H", b, 0x28)[0] * 4
    field_count = struct.unpack_from("<H", b, 0x2A)[0]
    root_offset = struct.unpack_from("<H", b, 0x2C)[0] * 4
    root_count = struct.unpack_from("<H", b, 0x2E)[0]
    string_hash_offset = struct.unpack_from("<H", b, 0x30)[0] * 4
    string_offsets_offset = struct.unpack_from("<H", b, 0x32)[0] * 4
    hash_count = struct.unpack_from("<H", b, 0x34)[0]
    value_offset = struct.unpack_from("<H", b, 0x36)[0] * 4
    string_offset = struct.unpack_from("<I", b, 0x38)[0]

    return RdbnHeaderInfo(
        magic=magic,
        header_size=header_size,
        version=version,
        data_offset=data_offset,
        data_size=data_size,
        type_offset=type_offset,
        type_count=type_count,
        field_offset=field_offset,
        field_count=field_count,
        root_offset=root_offset,
        root_count=root_count,
        string_hash_offset=string_hash_offset,
        string_offsets_offset=string_offsets_offset,
        hash_count=hash_count,
        value_offset=value_offset,
        string_offset=string_offset,
    )


def rdbn_to_json(data: bytes) -> dict[str, Any]:
    """Convertit un fichier RDBN / cfg.bin en dictionnaire JSON."""
    lib = bibliotheque()
    if hasattr(lib, "nie_cfgbin_to_json_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_cfgbin_to_json_out(buf, len(data), ctypes.byref(out))
        raw = prendre_octets(out)
        if raw:
            return json.loads(raw)
    hdr = parse_rdbn_header(data)
    return {"rdbn_header": hdr.to_dict()}


def rdbn_query_table(data: bytes, table_name: str) -> dict[str, Any] | None:
    """Interroge une table nommée dans un conteneur RDBN."""
    lib = bibliotheque()
    if hasattr(lib, "nie_rdbn_entry_query_json_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_rdbn_entry_query_json_out(
            buf, len(data), table_name.encode("utf-8"), ctypes.byref(out)
        )
        raw = prendre_octets(out)
        if raw:
            return json.loads(raw)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# G4TX Textures & Atlases
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class G4txSubTexture:
    id: int
    name: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class G4txTexture:
    id: int
    name: str
    width: int
    height: int
    is_dds: bool
    data_offset: int
    data_size: int
    sub_texture_count: int
    sub_textures: list[G4txSubTexture]


@dataclass(frozen=True)
class G4txHeaderInfo:
    magic: int
    header_size: int
    file_type: int
    table_size: int
    texture_count: int
    total_count: int
    sub_texture_count: int
    texture_data_size: int
    entry_offset: int
    sub_entry_offset: int
    hash_offset: int
    id_offset: int
    string_offset: int
    nxtch_base: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_g4tx(data: bytes | bytearray | memoryview) -> bool:
    """Dit si le tampon débute par un magic G4TX valide."""
    if len(data) < 12:
        return False
    magic = struct.unpack_from("<I", data, 0)[0]
    return magic == G4TX_MAGIC


def parse_g4tx_header(data: bytes | bytearray | memoryview) -> G4txHeaderInfo:
    """Lit l'en-tête G4TX et calcule les offsets précis selon aphrody-nie-formats::g4tx."""
    b = bytes(data)
    if len(b) < 0x60:
        raise ValueError(f"Tampon G4TX trop court : >= 0x60 attendu, reçu {len(b)}")

    (
        magic,
        header_size,
        file_type,
        table_size,
        texture_count,
        total_count,
        sub_texture_count,
        texture_data_size,
    ) = struct.unpack_from("<IIIIIIII", b, 0x00)

    if magic != G4TX_MAGIC:
        raise ValueError(f"Magic G4TX invalide : 0x{magic:08X} au lieu de 0x{G4TX_MAGIC:08X}")

    entry_offset = 0x60
    sub_entry_offset = entry_offset + texture_count * 0x30
    hash_offset = _align(sub_entry_offset + sub_texture_count * 0x18, 16)
    id_offset = hash_offset + total_count * 4
    string_offset = _align(id_offset + total_count, 4)
    nxtch_base = _align(header_size + table_size, 16)

    return G4txHeaderInfo(
        magic=magic,
        header_size=header_size,
        file_type=file_type,
        table_size=table_size,
        texture_count=texture_count,
        total_count=total_count,
        sub_texture_count=sub_texture_count,
        texture_data_size=texture_data_size,
        entry_offset=entry_offset,
        sub_entry_offset=sub_entry_offset,
        hash_offset=hash_offset,
        id_offset=id_offset,
        string_offset=string_offset,
        nxtch_base=nxtch_base,
    )


def g4tx_info(data: bytes) -> dict[str, Any]:
    """Extrait les métadonnées complètes d'un G4TX (textures, DDS, sous-textures)."""
    lib = bibliotheque()
    if hasattr(lib, "nie_g4tx_info_json_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_g4tx_info_json_out(buf, len(data), ctypes.byref(out))
        raw = prendre_octets(out)
        if raw:
            return json.loads(raw)
    hdr = parse_g4tx_header(data)
    return {"header": hdr.to_dict(), "textures": []}


def g4tx_subtexture_to_png(data: bytes, sub_name: str) -> bytes:
    """Découpe et décode une sous-texture nommée de l'atlas G4TX en PNG."""
    lib = bibliotheque()
    if hasattr(lib, "nie_g4tx_subtexture_to_png_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_g4tx_subtexture_to_png_out(
            buf, len(data), sub_name.encode("utf-8"), ctypes.byref(out)
        )
        png = prendre_octets(out)
        if png:
            return png
    raise ValueError(f"Impossible de décoder la sous-texture '{sub_name}' en PNG")


# ─────────────────────────────────────────────────────────────────────────────
# CRI CPK
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CpkHeaderInfo:
    magic: int
    sector_size: int
    utf_offset: int
    is_valid: bool


def is_cpk(data: bytes | bytearray | memoryview) -> bool:
    """Dit si le tampon commence par le magic CPK."""
    if len(data) < 4:
        return False
    magic = struct.unpack_from("<I", data, 0)[0]
    return magic == CPK_MAGIC


def parse_cpk_header(data: bytes | bytearray | memoryview) -> CpkHeaderInfo:
    """Vérifie et analyse l'en-tête d'une archive CRI CPK."""
    b = bytes(data)
    if len(b) < 16:
        return CpkHeaderInfo(magic=0, sector_size=0x800, utf_offset=0, is_valid=False)

    magic = struct.unpack_from("<I", b, 0)[0]
    is_valid = magic == CPK_MAGIC

    utf_offset = 16
    has_utf = False
    if len(b) >= utf_offset + 4:
        utf_magic = struct.unpack_from(">I", b, utf_offset)[0]
        if utf_magic in (UTF_MAGIC, CRI_ENCRYPTED_TABLE_MAGIC):
            has_utf = True

    return CpkHeaderInfo(
        magic=magic,
        sector_size=0x800,
        utf_offset=utf_offset if has_utf else 0,
        is_valid=is_valid,
    )


def cpk_info(data: bytes, filename: str = "") -> dict[str, Any]:
    """Lit l'en-tête général d'un fichier CPK en JSON."""
    lib = bibliotheque()
    if hasattr(lib, "nie_cpk_header_json_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_cpk_header_json_out(buf, len(data), filename.encode("utf-8"), ctypes.byref(out))
        raw = prendre_octets(out)
        if raw:
            return json.loads(raw)
    hdr = parse_cpk_header(data)
    return {"isValid": hdr.is_valid, "sectorSize": hdr.sector_size, "utfOffset": hdr.utf_offset}


def cpk_list_entries(data: bytes, filename: str = "") -> list[dict[str, Any]]:
    """Liste l'ensemble des entrées d'un conteneur CPK."""
    lib = bibliotheque()
    if hasattr(lib, "nie_cpk_list_json_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_cpk_list_json_out(buf, len(data), filename.encode("utf-8"), ctypes.byref(out))
        raw = prendre_octets(out)
        if raw:
            res = json.loads(raw)
            return res.get("entries", [])
    return []


def cpk_extract_entry(data: bytes, filename: str, entry_index: int) -> bytes:
    """Extrait le contenu d'un fichier depuis un conteneur CPK par son indice ordinal."""
    lib = bibliotheque()
    if hasattr(lib, "nie_cpk_extract_entry_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_cpk_extract_entry_out(
            buf, len(data), filename.encode("utf-8"), entry_index, ctypes.byref(out)
        )
        extracted = prendre_octets(out)
        if extracted:
            return extracted
    raise ValueError(f"Échec de l'extraction de l'entrée {entry_index} du CPK")


def cpk_extract_by_name(data: bytes, filename: str, entry_name: str) -> bytes:
    """Extrait le contenu d'un fichier depuis un conteneur CPK par son chemin interne."""
    lib = bibliotheque()
    if hasattr(lib, "nie_cpk_extract_by_name_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_cpk_extract_by_name_out(
            buf,
            len(data),
            filename.encode("utf-8"),
            entry_name.encode("utf-8"),
            ctypes.byref(out),
        )
        extracted = prendre_octets(out)
        if extracted:
            return extracted
    raise ValueError(f"Fichier '{entry_name}' introuvable dans le CPK")


# ─────────────────────────────────────────────────────────────────────────────
# Sauvegardes Lives (002AB8F4-*)
# ─────────────────────────────────────────────────────────────────────────────


def is_live_save(data: bytes | bytearray | memoryview, filename: str = "") -> bool:
    """Dit si le tampon est une sauvegarde Lives valide."""
    lib = bibliotheque()
    if hasattr(lib, "nie_save_probe") and filename:
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(bytes(data))
        return bool(lib.nie_save_probe(buf, len(data), filename.encode("utf-8")))

    if len(data) >= 12:
        m1 = struct.unpack_from("<I", data, 0)[0]
        c2 = struct.unpack_from("<I", data, 8)[0]
        if m1 == LIVES_SAVE_HEADER_MAGIC and c2 == LIVES_SAVE_CONST2:
            return True
    return False


def save_summary(data: bytes, filename: str = "") -> dict[str, Any]:
    """Déchiffre et analyse le résumé d'une sauvegarde Lives."""
    lib = bibliotheque()
    if hasattr(lib, "nie_save_summary_json_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_save_summary_json_out(buf, len(data), filename.encode("utf-8"), ctypes.byref(out))
        raw = prendre_octets(out)
        if raw:
            return json.loads(raw)
    return {}


def save_extract_blob(data: bytes, filename: str, blob_index: int) -> bytes:
    """Extrait un blob déchiffré d'un conteneur de sauvegarde Lives."""
    lib = bibliotheque()
    if hasattr(lib, "nie_save_extract_blob_out"):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        out = NieBytes()
        lib.nie_save_extract_blob_out(
            buf, len(data), filename.encode("utf-8"), blob_index, ctypes.byref(out)
        )
        extracted = prendre_octets(out)
        if extracted:
            return extracted
    raise ValueError(f"Échec de l'extraction du blob {blob_index} de la sauvegarde")
