"""Cryptographie et compression CRI Middleware et Level-5.

Fournit des implémentations pures et byte-exactes pour :
- Le CRC32 Level-5 (ISO 3309 reflected, poly 0xEDB88320) et l'accumulateur brut NIE.
- Le chiffrement de flux CRI position-XOR (involutif).
- La dérivation de clé de déchiffrement CPK depuis le nom de fichier.
- La décompression CRILAYLA par flux de bits inversé (LZSS).
"""

from __future__ import annotations

import struct
from typing import Sequence

from .nie_re import LEVEL5_CRC32_POLYNOMIAL, VIOLA_FIXED_KEY

__all__ = [
    "CRC32_TABLE",
    "CRILAYLA_MIN_FILE_SIZE",
    "CRILAYLA_PREFIX",
    "CRILAYLA_RAW_HEADER_SIZE",
    "compress_crilayla",
    "crc32_level5",
    "crc32_nie",
    "decompress_crilayla",
    "decrypt_cpk_block",
    "derive_cpk_key",
    "is_crilayla",
]

CRILAYLA_PREFIX = b"CRILAYLA"
CRILAYLA_RAW_HEADER_SIZE = 0x100
CRILAYLA_MIN_FILE_SIZE = 0x110  # 16 bytes header + 256 bytes raw header


def _build_crc32_table() -> list[int]:
    """Construit la table de consultation CRC32 IEEE 802.3 reflétée."""
    table: list[int] = []
    for i in range(256):
        c = i
        for _ in range(8):
            if c & 1:
                c = (c >> 1) ^ LEVEL5_CRC32_POLYNOMIAL
            else:
                c >>= 1
        table.append(c & 0xFFFFFFFF)
    return table


CRC32_TABLE: list[int] = _build_crc32_table()


def crc32_level5(data: bytes | bytearray | memoryview) -> int:
    """Calcule le CRC32 Level-5 (IEEE 802.3 / ISO 3309).

    Init 0xFFFFFFFF, poly 0xEDB88320, XOR final 0xFFFFFFFF.
    """
    crc = 0xFFFFFFFF
    for b in data:
        idx = (crc ^ b) & 0xFF
        crc = (crc >> 8) ^ CRC32_TABLE[idx]
    return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF


def crc32_nie(data: bytes | bytearray | memoryview) -> int:
    """Calcule l'accumulateur brut CRC32 sans le XOR final ~crc.

    Identique à `aphrody_nie_formats::cpk::crc32_nie`.
    """
    if len(data) == 0:
        return 0xFFFFFFFF
    crc = 0xFFFFFFFF
    for b in data:
        idx = (crc ^ b) & 0xFF
        crc = (crc >> 8) ^ CRC32_TABLE[idx]
    return crc & 0xFFFFFFFF


def derive_cpk_key(filename: str) -> int:
    """Dérive la clé de déchiffrement 32-bit CRI CPK depuis le nom de fichier."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if base == "cpk_list.cfg.bin":
        return VIOLA_FIXED_KEY
    if not base:
        return 0
    return crc32_level5(base.encode("utf-8"))


def _update_crc_state(seed: int, k: Sequence[int]) -> int:
    crc = (~seed) & 0xFFFFFFFF
    for i in range(4):
        idx = ((crc & 0xFF) ^ k[i]) & 0xFF
        crc = ((crc >> 8) ^ CRC32_TABLE[idx]) & 0xFFFFFFFF
    return (~crc) & 0xFFFFFFFF


def _compute_xor_byte(crc: int, position: int) -> int:
    base_shift = position * 2
    r8 = (crc >> (base_shift + 8)) & 3
    r8 |= ((crc >> base_shift) & 0xFF) << 2
    r8 &= 0xFF
    r8 = ((r8 << 2) & 0xFF) | ((crc >> (base_shift + 16)) & 3)
    r8 = ((r8 << 2) & 0xFF) | ((crc >> (base_shift + 24)) & 3)
    return r8 & 0xFF


def decrypt_cpk_block(
    buffer: bytes | bytearray | memoryview, key: int, file_offset: int = 0
) -> bytes:
    """Déchiffre (ou chiffre) un bloc de données CRI position-XOR.

    L'algorithme est involutif : appliqué deux fois avec la même clé,
    il restitue le texte en clair exact.
    """
    if len(buffer) == 0:
        return b""

    out = bytearray(buffer)
    k = [
        key & 0xFF,
        (key >> 8) & 0xFF,
        (key >> 16) & 0xFF,
        (key >> 24) & 0xFF,
    ]

    length = len(out)
    i = 0

    align_offset = file_offset & 3
    if align_offset != 0:
        current_crc = _update_crc_state(file_offset & ~3, k)
        align_count = min(4 - align_offset, length)
        for _ in range(align_count):
            pos = (file_offset + i) & 3
            out[i] ^= _compute_xor_byte(current_crc, pos)
            i += 1

    base_offset = file_offset + i
    while i + 4 <= length:
        crc = _update_crc_state(base_offset, k)
        out[i] ^= _compute_xor_byte(crc, 0)
        out[i + 1] ^= _compute_xor_byte(crc, 1)
        out[i + 2] ^= _compute_xor_byte(crc, 2)
        out[i + 3] ^= _compute_xor_byte(crc, 3)
        i += 4
        base_offset += 4

    if i < length:
        crc = _update_crc_state(base_offset, k)
        pos = 0
        while i < length:
            out[i] ^= _compute_xor_byte(crc, pos)
            i += 1
            pos += 1

    return bytes(out)


def is_crilayla(data: bytes | bytearray | memoryview) -> bool:
    """Vérifie si les données débutent par le magic CRILAYLA."""
    if len(data) < 8:
        return False
    return bytes(data[:8]) == CRILAYLA_PREFIX or bytes(data[:4]) == b"LAYL"


class _CrilaylaBitReader:
    def __init__(self, raw_block_start: int) -> None:
        self.ptr = raw_block_start
        self.bits_left = 0

    def get_next_bit(self, input_bytes: Sequence[int]) -> int:
        if self.bits_left == 0:
            if self.ptr == 0x10:
                raise ValueError("CRILAYLA: bitstream épuisé (get_next_bit)")
            self.ptr -= 1
            self.bits_left = 7
        else:
            self.bits_left -= 1
        return (input_bytes[self.ptr] >> self.bits_left) & 1

    def read8(self, input_bytes: Sequence[int]) -> int:
        if self.ptr == 0x10:
            raise ValueError("CRILAYLA: bitstream épuisé (read8)")
        self.ptr -= 1
        if self.bits_left != 0:
            extra = 8 - self.bits_left
            high = input_bytes[self.ptr + 1] & ((1 << self.bits_left) - 1)
            low = (input_bytes[self.ptr] >> self.bits_left) & ((1 << extra) - 1)
            return ((high << extra) | low) & 0xFF
        return input_bytes[self.ptr]

    def read_max8(self, bit_count: int, input_bytes: Sequence[int]) -> int:
        if self.bits_left == 0:
            if self.ptr == 0x10:
                raise ValueError("CRILAYLA: bitstream épuisé (read_max8)")
            self.ptr -= 1
            self.bits_left = 8

        take1 = min(self.bits_left, bit_count)
        self.bits_left -= take1
        result = (input_bytes[self.ptr] >> self.bits_left) & ((1 << take1) - 1)
        remaining = bit_count - take1

        if remaining == 0:
            return result

        if self.ptr == 0x10:
            raise ValueError("CRILAYLA: bitstream épuisé (read_max8 cross)")
        self.ptr -= 1
        self.bits_left = 8

        take2 = remaining
        self.bits_left -= take2
        low = (input_bytes[self.ptr] >> self.bits_left) & ((1 << take2) - 1)
        return ((result << take2) | low) & 0xFF

    def read13(self, input_bytes: Sequence[int]) -> int:
        bit_count = 13
        if self.bits_left == 0:
            if self.ptr == 0x10:
                raise ValueError("CRILAYLA: bitstream épuisé (read13 init)")
            self.ptr -= 1
            self.bits_left = 8

        take1 = min(self.bits_left, bit_count)
        mask1 = 0xFF if take1 >= 8 else (1 << take1) - 1
        result1 = (input_bytes[self.ptr] >> (self.bits_left - take1)) & mask1
        bit_count -= take1

        self.bits_left = 8
        if self.ptr == 0x10:
            raise ValueError("CRILAYLA: bitstream épuisé (read13 octet 2)")
        self.ptr -= 1

        take2 = min(self.bits_left, bit_count)
        mask2 = 0xFF if take2 >= 8 else (1 << take2) - 1
        result2 = (input_bytes[self.ptr] >> (self.bits_left - take2)) & mask2
        bit_count -= take2

        result = (result1 << take2) | result2
        if bit_count == 0:
            self.bits_left -= take2
            return result

        self.bits_left = 8
        if self.ptr == 0x10:
            raise ValueError("CRILAYLA: bitstream épuisé (read13 octet 3)")
        self.ptr -= 1

        take3 = bit_count
        mask3 = 0xFFFF if take3 >= 16 else (1 << take3) - 1
        result = (result << take3) | ((input_bytes[self.ptr] >> (self.bits_left - take3)) & mask3)
        self.bits_left -= take3
        return result


def decompress_crilayla(data: bytes | bytearray | memoryview) -> bytes:
    """Décompresse un conteneur CRILAYLA et rend les octets décompressés.

    Byte-exacte avec aphrody-nie-formats::crilayla et CriLayla.cs.
    """
    input_bytes = bytes(data)
    if len(input_bytes) < CRILAYLA_MIN_FILE_SIZE:
        raise ValueError(
            f"Tampon CRILAYLA trop court : >= {CRILAYLA_MIN_FILE_SIZE} attendu, reçu {len(input_bytes)}"
        )
    if not is_crilayla(input_bytes):
        raise ValueError("Magic CRILAYLA invalide")

    uncompressed_size = struct.unpack_from("<I", input_bytes, 8)[0]
    header_offset = struct.unpack_from("<I", input_bytes, 12)[0]

    raw_block_start = 0x10 + header_offset
    raw_block_end = raw_block_start + CRILAYLA_RAW_HEADER_SIZE
    if raw_block_end > len(input_bytes):
        raise ValueError("Bloc brut CRILAYLA hors limites")

    total_size = CRILAYLA_RAW_HEADER_SIZE + uncompressed_size
    if total_size > 256 * 1024 * 1024:
        raise ValueError("CRILAYLA: decoded size exceeds 256 MiB budget")
    try:
        output = bytearray(total_size)
    except MemoryError as error:
        raise ValueError("CRILAYLA: output allocation failed") from error
    output[0:CRILAYLA_RAW_HEADER_SIZE] = input_bytes[raw_block_start:raw_block_end]

    if uncompressed_size == 0:
        return bytes(output)

    br = _CrilaylaBitReader(raw_block_start)
    write_pos = total_size
    min_copy_len = 3

    while write_pos > CRILAYLA_RAW_HEADER_SIZE:
        flag = br.get_next_bit(input_bytes)
        if flag == 0:
            b = br.read8(input_bytes)
            write_pos -= 1
            output[write_pos] = b
        else:
            raw_offset = br.read13(input_bytes)
            offset = raw_offset + min_copy_len

            length = min_copy_len
            lvl2 = br.read_max8(2, input_bytes)
            length += lvl2
            if lvl2 == (1 << 2) - 1:
                lvl3 = br.read_max8(3, input_bytes)
                length += lvl3
                if lvl3 == (1 << 3) - 1:
                    lvl5 = br.read_max8(5, input_bytes)
                    length += lvl5
                    if lvl5 == (1 << 5) - 1:
                        while True:
                            lvl8 = br.read8(input_bytes)
                            length += lvl8
                            if lvl8 != 0xFF:
                                break

            if length > write_pos - CRILAYLA_RAW_HEADER_SIZE:
                raise ValueError("CRILAYLA : référence arrière dépasse le début du flux")

            dst_start = write_pos - length
            src_end = write_pos + offset
            if src_end > total_size:
                raise ValueError("CRILAYLA : source de référence arrière hors limites")

            if offset >= length:
                output[dst_start:write_pos] = output[src_end - length : src_end]
            else:
                for i in range(write_pos - 1, dst_start - 1, -1):
                    output[i] = output[i + offset]
            write_pos = dst_start

    return bytes(output)


def compress_crilayla(data: bytes | bytearray | memoryview) -> bytes:
    """Compresse des données brutes en conteneur CRILAYLA.

    Utilise en priorité le pont natif (C# NativeAOT / Rust), ou un conteneur
    littéral purement valide.
    """
    b_data = bytes(data)
    # Essai 1 : pont IecodeBridge (C# NativeAOT CriLayla)
    try:
        from .native_bridge import IecodeBridge

        if IecodeBridge.est_disponible():
            return IecodeBridge.compresser_crilayla(b_data)
    except Exception:
        pass

    # Essai 2 : pont Rust aphrody-nie-ffi
    try:
        from ._ffi import NieBytes, bibliotheque
        from .formats import prendre_octets
        import ctypes

        lib = bibliotheque()
        if hasattr(lib, "nie_crilayla_compress_out"):
            p_buf = (ctypes.c_ubyte * len(b_data)).from_buffer_copy(b_data)
            out = NieBytes()
            lib.nie_crilayla_compress_out(p_buf, len(b_data), ctypes.byref(out))
            compressed = prendre_octets(out)
            if compressed:
                return compressed
    except Exception:
        pass

    # Repli autonome : conteneur de données littérales valide
    # Découpage : 256 octets bruts en queue, bitstream composé uniquement de bits 0 + octet
    raw_size = min(len(b_data), CRILAYLA_RAW_HEADER_SIZE)
    raw_header = b_data[:raw_size].ljust(CRILAYLA_RAW_HEADER_SIZE, b"\x00")
    uncompressed_body = b_data[raw_size:]

    # Encodage littéral inversé : un bit 0 puis 8 bits de valeur
    # Pour un octet, 9 bits sont écrits en flux inversé
    bits: list[int] = []
    for b in reversed(uncompressed_body):
        bits.append(0)  # flag = 0 (literal)
        for bit_idx in range(7, -1, -1):
            bits.append((b >> bit_idx) & 1)

    # Complète à un octet
    rem = len(bits) % 8
    if rem != 0:
        bits.extend([0] * (8 - rem))

    bitstream = bytearray()
    for i in range(0, len(bits), 8):
        byte_val = 0
        for b_idx in range(8):
            byte_val = (byte_val << 1) | bits[i + b_idx]
        bitstream.append(byte_val)

    # Inversion du flux de bits car le lecteur lit de la fin vers le début
    bitstream.reverse()

    header_offset = len(bitstream)
    uncompressed_len = len(uncompressed_body)

    header = struct.pack(
        "<8sII",
        CRILAYLA_PREFIX,
        uncompressed_len,
        header_offset,
    )
    return header + bitstream + raw_header
