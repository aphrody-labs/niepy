"""Tests exhaustifs de la cryptographie, compression et analyseurs de formats (CRI / Level-5)."""

from __future__ import annotations

import struct
import pytest

from niepy.crypto import (
    compress_crilayla,
    crc32_level5,
    crc32_nie,
    decompress_crilayla,
    decrypt_cpk_block,
    derive_cpk_key,
    is_crilayla,
)
from niepy.parsers import (
    is_cpk,
    is_g4tx,
    is_live_save,
    is_rdbn,
    is_t2b,
    parse_cpk_header,
    parse_g4tx_header,
    parse_rdbn_header,
)


def test_crc32_level5_standard_vectors() -> None:
    # Vecteurs de test canoniques IEEE 802.3 / Level-5
    assert crc32_level5(b"Focus") == 0xA30165ED
    assert crc32_level5(b"") == 0x00000000
    assert crc32_level5(b"123456789") == 0xCBF43926


def test_crc32_nie_raw_accumulator() -> None:
    # CRC32 NIE (sans inversion finale ~crc)
    assert crc32_nie(b"") == 0xFFFFFFFF
    val = crc32_nie(b"Focus")
    assert val == (0xA30165ED ^ 0xFFFFFFFF)


def test_derive_cpk_key() -> None:
    # Clé fixe Viola pour cpk_list.cfg.bin
    assert derive_cpk_key("cpk_list.cfg.bin") == 0x1717E18E
    assert derive_cpk_key("data/cpk_list.cfg.bin") == 0x1717E18E
    assert derive_cpk_key("C:\\Games\\Inazuma\\data\\cpk_list.cfg.bin") == 0x1717E18E

    # Clé dérivée pour les autres fichiers (CRC32 réfléchi standard)
    k_common = derive_cpk_key("common.cpk")
    assert k_common == crc32_level5(b"common.cpk")


def test_decrypt_cpk_block_involution() -> None:
    key = 0x1717E18E
    cleartext = b"Level-5 CRI Middleware Position-XOR Involution Test Pattern 1234567890"

    # Chiffrement
    encrypted = decrypt_cpk_block(cleartext, key=key, file_offset=0)
    assert encrypted != cleartext

    # Déchiffrement avec la même clé et même offset -> texte en clair exact
    decrypted = decrypt_cpk_block(encrypted, key=key, file_offset=0)
    assert decrypted == cleartext


def test_decrypt_cpk_block_unaligned_offsets() -> None:
    key = 0xEDB88320
    payload = b"UnalignedOffsetTestPayload" * 4

    for offset in [1, 2, 3, 5, 7, 13]:
        enc = decrypt_cpk_block(payload, key=key, file_offset=offset)
        dec = decrypt_cpk_block(enc, key=key, file_offset=offset)
        assert dec == payload


def test_crilayla_roundtrip() -> None:
    original = b"CRILAYLA test buffer payload " * 15 + b"\x00\xff\xaa\x55" * 20
    compressed = compress_crilayla(original)

    assert is_crilayla(compressed)
    decompressed = decompress_crilayla(compressed)
    assert decompressed == original


def test_crilayla_invalid_buffer() -> None:
    with pytest.raises(ValueError, match="trop court"):
        decompress_crilayla(b"SHORT")

    with pytest.raises(ValueError, match="Magic"):
        decompress_crilayla(b"\x00" * 300)


def test_rdbn_header_parser() -> None:
    # Construit un faux en-tête RDBN de 80 octets valide
    magic = 0x4E424452  # 'RDBN'
    header_size = 0x50
    version = 1
    data_offset_words = 0x20  # * 4 = 128
    data_size = 4096

    buf = bytearray(0x50)
    struct.pack_into("<IHI", buf, 0x00, magic, header_size, version)
    struct.pack_into("<HI", buf, 0x0A, data_offset_words, data_size)
    struct.pack_into("<HH", buf, 0x24, 0x10, 5)  # type_offset (16*4=64), type_count = 5
    struct.pack_into("<HH", buf, 0x28, 0x18, 12)  # field_offset (24*4=96), field_count = 12

    assert is_rdbn(buf)
    info = parse_rdbn_header(buf)
    assert info.magic == magic
    assert info.version == 1
    assert info.header_size == 0x50
    assert info.data_offset == 128
    assert info.data_size == 4096
    assert info.type_count == 5
    assert info.field_count == 12


def test_rdbn_header_invalid() -> None:
    with pytest.raises(ValueError, match="trop court"):
        parse_rdbn_header(b"SMALL")

    with pytest.raises(ValueError, match="Magic RDBN invalide"):
        parse_rdbn_header(b"\x00" * 0x50)


def test_g4tx_header_parser() -> None:
    magic = 0x58543447  # 'G4TX'
    header_size = 0x60
    file_type = 1
    table_size = 0x200
    texture_count = 3
    total_count = 10
    sub_texture_count = 7
    texture_data_size = 65536

    buf = bytearray(0x60)
    struct.pack_into(
        "<IIIIIIII",
        buf,
        0,
        magic,
        header_size,
        file_type,
        table_size,
        texture_count,
        total_count,
        sub_texture_count,
        texture_data_size,
    )

    assert is_g4tx(buf)
    hdr = parse_g4tx_header(buf)
    assert hdr.magic == magic
    assert hdr.texture_count == 3
    assert hdr.sub_texture_count == 7
    assert hdr.entry_offset == 0x60
    # sub_entry_offset = 0x60 + 3 * 0x30 = 0x60 + 0x90 = 0xF0 (240)
    assert hdr.sub_entry_offset == 0x60 + 3 * 0x30


def test_cpk_header_parser() -> None:
    # Header CPK de 16 octets suivi d'un magic @UTF
    magic = 0x204B5043  # 'CPK '
    utf_magic = 0x00465455  # '@UTF' (BE)

    buf = bytearray(32)
    struct.pack_into("<I", buf, 0, magic)
    struct.pack_into(">I", buf, 16, utf_magic)

    assert is_cpk(buf)
    hdr = parse_cpk_header(buf)
    assert hdr.is_valid
    assert hdr.sector_size == 0x800
    assert hdr.utf_offset == 16


def test_is_live_save() -> None:
    # 0x9DCE66C3 à offset 0, 0x2EC3031F à offset 8
    buf = bytearray(16)
    struct.pack_into("<I", buf, 0, 0x9DCE66C3)
    struct.pack_into("<I", buf, 8, 0x2EC3031F)
    assert is_live_save(buf)

    corrupt = bytearray(16)
    assert not is_live_save(corrupt)
