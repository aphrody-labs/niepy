"""Décodage et détection des 28 formats du Virtual File System (VFS).

Prend en charge la totalité des 28 formats canoniques (G4TX, G4MD, G4MG, G4MT,
G4SK, G4PK, G4RA, AGI, OBJB, PXCL, RDBN, MEVS, G4CM, CPK, AFS2, @UTF, DDS, PNG,
RIFF, XPCK, XFSA, CRILAYLA, @ACB, CRID, G4NV, COL, COLS, LIVE).

Fonctionne de manière hybride :
- Utilise en priorité `aphrody-nie-ffi` (Rust) pour la vitesse native.
- Dispose d'un moteur autonome 100 % pur Python pour la détection et les métadonnées
  lorsque la bibliothèque native n'est pas chargée.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import IntEnum
import json
from typing import Any

from ._ffi import NieBytes, bibliotheque

__all__ = [
    "FORMAT_CATALOG_STATIC",
    "VfsFormatConsumer",
    "VfsFormatDescriptor",
    "VfsFormatId",
    "decoder",
    "detect_format",
    "detect_format_pure",
    "detecter",
    "detecter_pur",
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


#: Catalogue statique des 28 formats VFS autorisés
FORMAT_CATALOG_STATIC: dict[int, VfsFormatDescriptor] = {
    1: VfsFormatDescriptor(
        id=1,
        name="G4TX",
        extension=".g4tx",
        mime_type="image/x-g4tx",
        category="texture",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 Texture Container (main DDS BCn textures + atlas sprite subregions)",
    ),
    2: VfsFormatDescriptor(
        id=2,
        name="G4MD",
        extension=".g4md",
        mime_type="model/x-g4md",
        category="model",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 3D Model Data (meshes, bone indices, vertex buffers, materials)",
    ),
    3: VfsFormatDescriptor(
        id=3,
        name="G4MG",
        extension=".g4mg",
        mime_type="model/x-g4mg",
        category="model",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 Model Group (collection of submeshes and LOD levels)",
    ),
    4: VfsFormatDescriptor(
        id=4,
        name="G4MT",
        extension=".g4mt",
        mime_type="model/x-g4mt",
        category="model",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Level-5 Material Properties (shaders, blend modes, diffuse/specular colors)",
    ),
    5: VfsFormatDescriptor(
        id=5,
        name="G4SK",
        extension=".g4sk",
        mime_type="model/x-g4sk",
        category="model",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Level-5 Skeleton & Bone Hierarchy (quaternions, bind poses, transform trees)",
    ),
    6: VfsFormatDescriptor(
        id=6,
        name="G4PK",
        extension=".g4pk",
        mime_type="application/x-g4pk",
        category="container",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 Package Container (multi-resource bundle for characters and stadiums)",
    ),
    7: VfsFormatDescriptor(
        id=7,
        name="G4RA",
        extension=".g4ra",
        mime_type="application/x-g4ra",
        category="container",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 Resource Archive (compact asset bundle indexed in nie.exe)",
    ),
    8: VfsFormatDescriptor(
        id=8,
        name="AGI",
        extension=".agi",
        mime_type="model/x-agi",
        category="model",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 Animation Graphic Interface (timeline tracks, animation nodes)",
    ),
    9: VfsFormatDescriptor(
        id=9,
        name="OBJB",
        extension=".objb",
        mime_type="application/x-objb",
        category="config",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 Object Binary (scene layout descriptors, actor placements)",
    ),
    10: VfsFormatDescriptor(
        id=10,
        name="PXCL",
        extension=".pxcl",
        mime_type="application/x-pxcl",
        category="system",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Level-5 Pixel Collision & Physics Hull (hitboxes, boundary colliders)",
    ),
    11: VfsFormatDescriptor(
        id=11,
        name="RDBN",
        extension=".cfg.bin",
        mime_type="application/x-rdbn",
        category="config",
        is_big_endian=False,
        encryption_supported=True,
        compression_supported=True,
        description="Level-5 Relational Database Binary (T2B structured binary data sheets)",
    ),
    12: VfsFormatDescriptor(
        id=12,
        name="MEVS",
        extension=".mevbin",
        mime_type="application/x-mevs",
        category="script",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 Motion Event Script (choreographed cutscenes, camera paths, audio cues)",
    ),
    13: VfsFormatDescriptor(
        id=13,
        name="G4CM",
        extension=".g4cm",
        mime_type="application/x-g4cm",
        category="script",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Level-5 Camera Track & Spline Path (cinematic parameters, FOV transitions)",
    ),
    14: VfsFormatDescriptor(
        id=14,
        name="CPK",
        extension=".cpk",
        mime_type="application/x-cpk",
        category="container",
        is_big_endian=True,
        encryption_supported=True,
        compression_supported=True,
        description="CRI Middleware File Package (TOC, ITOC, ETOC, @UTF directory descriptors)",
    ),
    15: VfsFormatDescriptor(
        id=15,
        name="AFS2",
        extension=".afs2",
        mime_type="audio/x-afs2",
        category="audio",
        is_big_endian=False,
        encryption_supported=True,
        compression_supported=False,
        description="Criware Audio Archive (AWB wavebank containers)",
    ),
    16: VfsFormatDescriptor(
        id=16,
        name="@UTF",
        extension=".utf",
        mime_type="application/x-cri-utf",
        category="container",
        is_big_endian=True,
        encryption_supported=True,
        compression_supported=False,
        description="CRI Universal Table Format (schema, column flags, string pools, row vectors)",
    ),
    17: VfsFormatDescriptor(
        id=17,
        name="DDS",
        extension=".dds",
        mime_type="image/vnd-ms.dds",
        category="texture",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="DirectDraw Surface (raw BC1/BC2/BC3/BC4/BC5/BC7 compressed texture payload)",
    ),
    18: VfsFormatDescriptor(
        id=18,
        name="PNG",
        extension=".png",
        mime_type="image/png",
        category="texture",
        is_big_endian=True,
        encryption_supported=False,
        compression_supported=True,
        description="Portable Network Graphics (decoded atlas glyphs, UI elements, web exports)",
    ),
    19: VfsFormatDescriptor(
        id=19,
        name="RIFF",
        extension=".wav",
        mime_type="audio/wav",
        category="audio",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Resource Interchange File Format (PCM and ADPCM audio tracks)",
    ),
    20: VfsFormatDescriptor(
        id=20,
        name="XPCK",
        extension=".xpck",
        mime_type="application/x-xpck",
        category="container",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 XPCK Package (legacy DS/3DS/Switch container format)",
    ),
    21: VfsFormatDescriptor(
        id=21,
        name="XFSA",
        extension=".xfsa",
        mime_type="application/x-xfsa",
        category="container",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="Level-5 XFSA Archive (file system archive with hash-addressed records)",
    ),
    22: VfsFormatDescriptor(
        id=22,
        name="CRILAYLA",
        extension=".crilayla",
        mime_type="application/x-crilayla",
        category="container",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=True,
        description="CRI Layla Reverse-Bitstream LZSS Compressed Container (16-byte header + bitstream + 0x100 raw)",
    ),
    23: VfsFormatDescriptor(
        id=23,
        name="@ACB",
        extension=".acb",
        mime_type="audio/x-acb",
        category="audio",
        is_big_endian=True,
        encryption_supported=True,
        compression_supported=False,
        description="Criware Audio Cue Sheet (cue mappings, sound triggers, DSP effects)",
    ),
    24: VfsFormatDescriptor(
        id=24,
        name="CRID",
        extension=".usm",
        mime_type="video/x-usm",
        category="video",
        is_big_endian=True,
        encryption_supported=True,
        compression_supported=False,
        description="CRI Movie 2 Container (video stream, multi-track audio, subtitle packets)",
    ),
    25: VfsFormatDescriptor(
        id=25,
        name="G4NV",
        extension=".g4nv",
        mime_type="application/x-g4nv",
        category="system",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Level-5 Navigation Mesh (stadium and field locomotion polygons)",
    ),
    26: VfsFormatDescriptor(
        id=26,
        name="COL",
        extension=".col",
        mime_type="application/x-col",
        category="system",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Level-5 Collision mesh data",
    ),
    27: VfsFormatDescriptor(
        id=27,
        name="COLS",
        extension=".cols",
        mime_type="application/x-cols",
        category="system",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Level-5 Collision Set (stadium boundaries, goal posts, ball bouncing volumes)",
    ),
    28: VfsFormatDescriptor(
        id=28,
        name="LIVE",
        extension=".live",
        mime_type="application/x-nie-live",
        category="system",
        is_big_endian=False,
        encryption_supported=True,
        compression_supported=False,
        description="Level-5 Lives Save Container (002AB8F4-* CRC32-keyed XOR stream cipher, 0xEEFF blobs)",
    ),
}


def prendre_octets(tampon: NieBytes) -> bytes:
    """Copie un `NieBytes` en `bytes` Python et libère la mémoire Rust."""
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
    try:
        brut = bibliotheque().nie_version()
        return brut.decode("utf-8") if brut else "?"
    except Exception:
        return "pur-python-0.1.0"


def detecter_pur(donnees: bytes) -> int:
    """Détection 100 % pure Python des 28 formats autorisés par leurs magic bytes."""
    if len(donnees) < 4:
        return VfsFormatId.UNKNOWN

    # Discriminants little-endian Level-5 G4*
    if donnees.startswith(b"G4TX"):
        return VfsFormatId.G4TX
    if donnees.startswith(b"G4MD"):
        return VfsFormatId.G4MD
    if donnees.startswith(b"G4MG"):
        return VfsFormatId.G4MG
    if donnees.startswith(b"G4MT"):
        return VfsFormatId.G4MT
    if donnees.startswith(b"G4SK"):
        return VfsFormatId.G4SK
    if donnees.startswith(b"G4PK"):
        return VfsFormatId.G4PK
    if donnees.startswith(b"G4RA"):
        return VfsFormatId.G4RA
    if donnees.startswith(b"AGI "):
        return VfsFormatId.AGI
    if donnees.startswith(b"OBJB"):
        return VfsFormatId.OBJB
    if donnees.startswith(b"PXCL"):
        return VfsFormatId.COL
    if donnees.startswith(b"RDBN") or donnees.startswith(b"T2B\x00") or donnees.startswith(b"T2B "):
        return VfsFormatId.CFGBIN
    if donnees.startswith(b"MEVS"):
        return VfsFormatId.MEVS
    if donnees.startswith(b"G4CM"):
        return VfsFormatId.G4CM
    if donnees.startswith(b"CPK "):
        return VfsFormatId.CPK
    if donnees.startswith(b"AFS2"):
        return VfsFormatId.AWB
    if donnees.startswith(b"@UTF"):
        return VfsFormatId.UTF
    if donnees.startswith(b"DDS "):
        return VfsFormatId.DDS
    if donnees.startswith(b"\x89PNG\r\n\x1a\n"):
        return VfsFormatId.PNG
    if donnees.startswith(b"RIFF"):
        return VfsFormatId.RIFF
    if donnees.startswith(b"XPCK"):
        return VfsFormatId.XPCK
    if donnees.startswith(b"XFSA"):
        return VfsFormatId.XFSA
    if donnees.startswith(b"CRILAYLA") or donnees.startswith(b"LAYL"):
        return VfsFormatId.CRILAYLA
    if donnees.startswith(b"@ACB"):
        return VfsFormatId.ACB
    if donnees.startswith(b"CRID"):
        return VfsFormatId.USM
    if donnees.startswith(b"G4NV"):
        return VfsFormatId.G4NV
    if donnees.startswith(b"COL\x00"):
        return VfsFormatId.COL_MESH
    if donnees.startswith(b"COLS"):
        return VfsFormatId.COLS
    # LIVE: 0x9DCE66C3 (LE = C3 66 CE 9D)
    if donnees[:4] == b"\xc3\x66\xce\x9d":
        return VfsFormatId.LIVE

    return VfsFormatId.UNKNOWN


def detecter(donnees: bytes) -> int:
    """Discriminant numérique stable du format d'un tampon."""
    try:
        tampon = _vue(donnees)
        d = int(bibliotheque().nie_detect(tampon, len(donnees)))
        if d != 0:
            return d
    except Exception:
        pass
    return detecter_pur(donnees)


def nom_format(discriminant: int) -> str:
    """Nom court d'un format, depuis son discriminant."""
    try:
        brut = bibliotheque().nie_format_name(discriminant)
        if brut:
            return brut.decode("utf-8")
    except Exception:
        pass
    desc = FORMAT_CATALOG_STATIC.get(discriminant)
    return desc.name if desc else "inconnu"


def decoder(donnees: bytes) -> Any:
    """Décode un tampon par auto-détection et rend la structure Python correspondante."""
    try:
        tampon = _vue(donnees)
        sortie = NieBytes()
        bibliotheque().nie_decode_json_out(tampon, len(donnees), ctypes.byref(sortie))
        brut = prendre_octets(sortie)
        if brut:
            return json.loads(brut)
    except Exception:
        pass

    # Décodage pur Python pour RDBN ou G4TX
    fmt = detecter(donnees)
    if fmt == VfsFormatId.CFGBIN:
        from .parsers import rdbn_to_json

        return rdbn_to_json(donnees)
    if fmt == VfsFormatId.G4TX:
        from .parsers import g4tx_info

        return g4tx_info(donnees)
    if fmt == VfsFormatId.CPK:
        from .parsers import cpk_info

        return cpk_info(donnees)

    nom = nom_format(fmt)
    raise ValueError(f"format non décodable en JSON (détecté : {nom})")


def g4tx_vers_png(donnees: bytes) -> bytes:
    """Décode la première texture d'un G4TX et rend les octets PNG."""
    tampon = _vue(donnees)
    sortie = NieBytes()
    bibliotheque().nie_g4tx_to_png_out(tampon, len(donnees), ctypes.byref(sortie))
    png = prendre_octets(sortie)
    if not png:
        raise ValueError("G4TX non décodable en PNG")
    return png


def get_format_descriptor(fmt_id: int) -> VfsFormatDescriptor:
    """Returns the strongly-typed descriptor for a format ID."""
    try:
        lib = bibliotheque()
        if hasattr(lib, "nie_format_extension") and fmt_id > 0:
            ext_b = lib.nie_format_extension(fmt_id)
            if ext_b:
                ext = ext_b.decode("utf-8")
                mime = lib.nie_format_mime_type(fmt_id).decode("utf-8")
                cat = lib.nie_format_category(fmt_id).decode("utf-8")
                is_be = bool(lib.nie_format_is_big_endian(fmt_id))
                enc = bool(lib.nie_format_supports_encryption(fmt_id))
                comp = bool(lib.nie_format_supports_compression(fmt_id))
                name = nom_format(fmt_id)
                static_desc = FORMAT_CATALOG_STATIC.get(fmt_id)
                return VfsFormatDescriptor(
                    id=fmt_id,
                    name=name,
                    extension=ext,
                    mime_type=mime,
                    category=cat,
                    is_big_endian=is_be,
                    encryption_supported=enc,
                    compression_supported=comp,
                    description=static_desc.description if static_desc else "",
                )
    except Exception:
        pass

    if fmt_id in FORMAT_CATALOG_STATIC:
        return FORMAT_CATALOG_STATIC[fmt_id]

    return VfsFormatDescriptor(
        id=fmt_id,
        name=nom_format(fmt_id),
        extension=".bin",
        mime_type="application/octet-stream",
        category="system",
        is_big_endian=False,
        encryption_supported=False,
        compression_supported=False,
        description="Unknown format",
    )


def detect_format(data: bytes) -> VfsFormatDescriptor:
    """Detects and returns the format descriptor from byte content."""
    fmt_id = detecter(data)
    return get_format_descriptor(fmt_id)


def detect_format_pure(data: bytes) -> VfsFormatDescriptor:
    """Detects and returns format descriptor strictly in pure Python."""
    fmt_id = detecter_pur(data)
    return FORMAT_CATALOG_STATIC.get(
        fmt_id,
        VfsFormatDescriptor(
            id=0,
            name="inconnu",
            extension=".bin",
            mime_type="application/octet-stream",
            category="system",
            is_big_endian=False,
            encryption_supported=False,
            compression_supported=False,
        ),
    )


def list_vfs_formats() -> list[VfsFormatDescriptor]:
    """Returns all 28 canonical VFS format descriptors."""
    try:
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
                        description=item.get(
                            "description", FORMAT_CATALOG_STATIC.get(item["id"], {}).description
                        ),
                    )
                    for item in items
                ]
    except Exception:
        pass
    return [FORMAT_CATALOG_STATIC[i] for i in range(1, 29)]


def validate_format(expected_id: int, data: bytes) -> bool:
    """Checks whether the data starts with the expected format header."""
    return detecter(data) == expected_id


class VfsFormatConsumer:
    """Universal VFS Format Consumer in Python."""

    @staticmethod
    def detect(data: bytes) -> VfsFormatDescriptor:
        return detect_format(data)

    @staticmethod
    def detect_pure(data: bytes) -> VfsFormatDescriptor:
        return detect_format_pure(data)

    @staticmethod
    def get(fmt_id: int) -> VfsFormatDescriptor:
        return get_format_descriptor(fmt_id)

    @staticmethod
    def list_all() -> list[VfsFormatDescriptor]:
        return list_vfs_formats()

    @staticmethod
    def validate(fmt_id: int, data: bytes) -> bool:
        return validate_format(fmt_id, data)
