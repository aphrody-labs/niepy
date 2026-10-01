"""Tests exhaustifs de la détection et des métadonnées des 28 formats canoniques du VFS."""

from __future__ import annotations

from niepy.formats import (
    FORMAT_CATALOG_STATIC,
    VfsFormatConsumer,
    VfsFormatDescriptor,
    VfsFormatId,
    detect_format_pure,
    detecter_pur,
    list_vfs_formats,
    nom_format,
    validate_format,
)

ALL_28_TEST_MAGICS: list[tuple[int, str, bytes, str, str]] = [
    (1, "G4TX", b"G4TX\x60\x00\x00\x00", ".g4tx", "texture"),
    (2, "G4MD", b"G4MD\x10\x00\x00\x00", ".g4md", "model"),
    (3, "G4MG", b"G4MG\x20\x00\x00\x00", ".g4mg", "model"),
    (4, "G4MT", b"G4MT\x00\x00\x00\x00", ".g4mt", "model"),
    (5, "G4SK", b"G4SK\x00\x00\x00\x00", ".g4sk", "model"),
    (6, "G4PK", b"G4PK\x80\x00\x00\x00", ".g4pk", "container"),
    (7, "G4RA", b"G4RA\x00\x00\x00\x00", ".g4ra", "container"),
    (8, "AGI", b"AGI \x00\x00\x00\x00", ".agi", "model"),
    (9, "OBJB", b"OBJB\x00\x00\x00\x00", ".objb", "config"),
    (10, "PXCL", b"PXCL\x00\x00\x00\x00", ".pxcl", "system"),
    (11, "RDBN", b"RDBN\x50\x00\x01\x00", ".cfg.bin", "config"),
    (12, "MEVS", b"MEVS\x00\x00\x00\x00", ".mevbin", "script"),
    (13, "G4CM", b"G4CM\x00\x00\x00\x00", ".g4cm", "script"),
    (14, "CPK", b"CPK \x00\x08\x00\x00", ".cpk", "container"),
    (15, "AFS2", b"AFS2\x01\x02\x00\x00", ".afs2", "audio"),
    (16, "@UTF", b"@UTF\x00\x20\x00\x00", ".utf", "container"),
    (17, "DDS", b"DDS \x7c\x00\x00\x00", ".dds", "texture"),
    (18, "PNG", b"\x89PNG\r\n\x1a\n\x00\x00", ".png", "texture"),
    (19, "RIFF", b"RIFF\x24\x00\x00\x00WAVE", ".wav", "audio"),
    (20, "XPCK", b"XPCK\x00\x00\x00\x00", ".xpck", "container"),
    (21, "XFSA", b"XFSA\x00\x00\x00\x00", ".xfsa", "container"),
    (22, "CRILAYLA", b"CRILAYLA\x00\x01\x00\x00", ".crilayla", "container"),
    (23, "@ACB", b"@ACB\x00\x00\x00\x00", ".acb", "audio"),
    (24, "CRID", b"CRID\x00\x00\x00\x00", ".usm", "video"),
    (25, "G4NV", b"G4NV\x00\x00\x00\x00", ".g4nv", "system"),
    (26, "COL", b"COL\x00\x00\x00\x00\x00", ".col", "system"),
    (27, "COLS", b"COLS\x00\x00\x00\x00", ".cols", "system"),
    (28, "LIVE", b"\xc3\x66\xce\x9d\x00\x00\x00\x00", ".live", "system"),
]


def test_format_catalog_static_count_and_completeness() -> None:
    assert len(FORMAT_CATALOG_STATIC) == 28
    for i in range(1, 29):
        assert i in FORMAT_CATALOG_STATIC
        desc = FORMAT_CATALOG_STATIC[i]
        assert isinstance(desc, VfsFormatDescriptor)
        assert desc.id == i
        assert len(desc.name) > 0
        assert desc.extension.startswith(".")
        assert "/" in desc.mime_type


def test_detect_all_28_formats_pure() -> None:
    for expected_id, expected_name, magic, expected_ext, expected_cat in ALL_28_TEST_MAGICS:
        fid = detecter_pur(magic)
        assert fid == expected_id, (
            f"Échec détection {expected_name}: attendu {expected_id}, reçu {fid}"
        )

        desc = detect_format_pure(magic)
        assert desc.id == expected_id
        assert desc.name == expected_name
        assert desc.extension == expected_ext
        assert desc.category == expected_cat


def test_vfs_format_consumer_facade() -> None:
    all_formats = VfsFormatConsumer.list_all()
    assert len(all_formats) == 28

    # Test Consumer get
    g4tx = VfsFormatConsumer.get(1)
    assert g4tx.name == "G4TX"
    assert g4tx.extension == ".g4tx"

    live = VfsFormatConsumer.get(28)
    assert live.name == "LIVE"
    assert live.encryption_supported

    # Test Consumer detect_pure
    probe = VfsFormatConsumer.detect_pure(b"CPK \x00\x08\x00\x00")
    assert probe.id == VfsFormatId.CPK
    assert probe.name == "CPK"


def test_validate_format() -> None:
    data = b"RDBN\x50\x00\x01\x00"
    assert validate_format(VfsFormatId.CFGBIN, data)
    assert not validate_format(VfsFormatId.G4TX, data)
