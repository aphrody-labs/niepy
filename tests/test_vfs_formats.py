"""Unit tests for Python VFS format consumer and standardized format descriptors."""

import pytest
from niepy import (
    VfsFormatConsumer,
    VfsFormatDescriptor,
    VfsFormatId,
    detect_format,
    get_format_descriptor,
    list_vfs_formats,
    validate_format,
)


def test_vfs_format_id_enum():
    """VfsFormatId enum has all 28 canonical members."""
    assert VfsFormatId.G4TX == 1
    assert VfsFormatId.G4MD == 2
    assert VfsFormatId.OBJB == 9
    assert VfsFormatId.CFGBIN == 11
    assert VfsFormatId.CPK == 14
    assert VfsFormatId.LIVE == 28


def test_list_vfs_formats():
    """list_vfs_formats returns 28 standardized descriptors."""
    formats = list_vfs_formats()
    assert len(formats) >= 28

    ids = [fmt.id for fmt in formats]
    for i in range(1, 29):
        assert i in ids

    # Check G4TX descriptor
    g4tx = next(f for f in formats if f.id == 1)
    assert g4tx.name == "G4TX"
    assert g4tx.extension == ".g4tx"
    assert g4tx.mime_type == "image/x-level5-g4tx"
    assert g4tx.category == "texture"
    assert not g4tx.is_big_endian

    # Check CPK descriptor
    cpk = next(f for f in formats if f.id == 14)
    assert cpk.name == "CPK"
    assert cpk.extension == ".cpk"
    assert cpk.category == "container"
    assert cpk.is_big_endian
    assert cpk.encryption_supported


def test_get_format_descriptor():
    """get_format_descriptor returns proper descriptor by format ID."""
    desc = get_format_descriptor(VfsFormatId.G4TX)
    assert desc.id == 1
    assert desc.name == "G4TX"

    desc_live = get_format_descriptor(28)
    assert desc_live.id == 28
    assert desc_live.name == "LIVE"
    assert desc_live.extension == ".live"
    assert desc_live.encryption_supported


def test_detect_format():
    """detect_format detects headers accurately."""
    # G4TX header
    g4tx_header = b"G4TX" + b"\x00" * 28
    fmt_g4tx = detect_format(g4tx_header)
    assert fmt_g4tx.id == VfsFormatId.G4TX
    assert fmt_g4tx.name == "G4TX"

    # CPK header
    cpk_header = b"CPK " + b"\x00" * 28
    fmt_cpk = detect_format(cpk_header)
    assert fmt_cpk.id == VfsFormatId.CPK
    assert fmt_cpk.name == "CPK"

    # RDBN header
    rdbn_header = b"RDBN" + b"\x00" * 28
    fmt_rdbn = detect_format(rdbn_header)
    assert fmt_rdbn.id == VfsFormatId.CFGBIN
    assert fmt_rdbn.name == "cfg.bin"

    # LIVE header (0x9DCE66C3 LE)
    live_header = bytes([0xC3, 0x66, 0xCE, 0x9D]) + b"\x00" * 28
    fmt_live = detect_format(live_header)
    assert fmt_live.id == VfsFormatId.LIVE
    assert fmt_live.name == "LIVE"

    # Unknown data
    unk = detect_format(b"\x00\x00\x00\x00")
    assert unk.id == 0


def test_validate_format():
    """validate_format checks against expected ID."""
    g4tx_header = b"G4TX\x00\x00\x00\x00"
    assert validate_format(VfsFormatId.G4TX, g4tx_header)
    assert not validate_format(VfsFormatId.CPK, g4tx_header)


def test_vfs_format_consumer_facade():
    """VfsFormatConsumer static facade delegates properly."""
    assert VfsFormatConsumer.get(VfsFormatId.G4TX).name == "G4TX"
    assert len(VfsFormatConsumer.list_all()) >= 28
    assert VfsFormatConsumer.validate(14, b"CPK \x00\x00\x00\x00")
    assert VfsFormatConsumer.detect(b"G4TX\x00\x00\x00\x00").id == 1
