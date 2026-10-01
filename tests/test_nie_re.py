"""Tests exhaustifs des spécifications de rétro-ingénierie de nie.exe et du PRNG CRand."""

from __future__ import annotations

import json
from niepy.nie_re import (
    CRI_ENCRYPTED_TABLE_MAGIC,
    CRand,
    CRITICAL_OFFSETS,
    CRYPTO_CONSTANTS,
    IMAGE_BASE,
    LEVEL5_CRC32_POLYNOMIAL,
    LIVES_BLOB_MAGIC,
    LIVES_SAVE_CONST2,
    LIVES_SAVE_HEADER_MAGIC,
    MEMORY_STRUCTURES,
    RTTI_CLASSES,
    STEAM_APP_ID,
    TARGET_BINARY,
    TOTAL_FUNCTIONS_COUNT,
    VIOLA_FIXED_KEY,
    get_nie_re_map,
)


def test_nie_re_binary_characteristics() -> None:
    re_map = get_nie_re_map()
    assert re_map.target_binary == "nie.exe"
    assert re_map.internal_name == "nie1v2.exe"
    assert re_map.architecture == "x86_64"
    assert re_map.format == "PE32+"
    assert re_map.base_address_hex == "0x140000000"
    assert re_map.total_functions_count == 117068
    assert IMAGE_BASE == 0x140000000
    assert TOTAL_FUNCTIONS_COUNT == 117068


def test_nie_re_crypto_constants() -> None:
    assert VIOLA_FIXED_KEY == 0x1717E18E
    assert LEVEL5_CRC32_POLYNOMIAL == 0xEDB88320
    assert CRI_ENCRYPTED_TABLE_MAGIC == 0xF5F39E1F
    assert LIVES_SAVE_HEADER_MAGIC == 0x9DCE66C3
    assert LIVES_SAVE_CONST2 == 0x2EC3031F
    assert LIVES_BLOB_MAGIC == 0xEEFF
    assert STEAM_APP_ID == 2799860

    names = {c.name for c in CRYPTO_CONSTANTS}
    assert "VIOLA_FIXED_KEY" in names
    assert "LEVEL5_CRC32_POLYNOMIAL" in names
    assert "STEAM_APP_ID" in names
    assert "LIVES_SAVE_HEADER_MAGIC" in names


def test_nie_re_critical_offsets() -> None:
    assert len(CRITICAL_OFFSETS) == 8
    symbols = {o.symbol: o for o in CRITICAL_OFFSETS}
    assert "GameTickLoop" in symbols
    assert symbols["GameTickLoop"].runtime_pc == 0x1406D5840
    assert symbols["CharaControllerUpdate"].runtime_pc == 0x1404ECD60
    assert symbols["CriFsStreamDecryptBlock"].runtime_pc == 0x1405A1120
    assert symbols["CriLaylaDecompressStream"].runtime_pc == 0x1405B3890
    assert symbols["RdbnTableLookup"].runtime_pc == 0x1403C8040
    assert symbols["G4txDecodeTexture"].runtime_pc == 0x1404B2A80
    assert symbols["LuaHostInit"].runtime_pc == 0x14072F910
    assert symbols["CRand_MT19937_Next"].runtime_pc == 0x14081C200


def test_nie_re_rtti_classes() -> None:
    assert len(RTTI_CLASSES) == 8
    names = {r.name: r for r in RTTI_CLASSES}
    assert "Object" in names
    assert names["Object"].vtable_offset_hex == "0x140AC4000"
    assert "CharaController" in names
    assert "BallPhysics" in names
    assert "VfsManager" in names
    assert "CpkArchive" in names
    assert "RenderScene" in names
    assert "SkinnedMesh" in names
    assert "SoundPlayer" in names


def test_nie_re_memory_structures() -> None:
    assert "BonePalette" in MEMORY_STRUCTURES
    assert MEMORY_STRUCTURES["BonePalette"].size_hex == "0x600"
    assert "FontGlyph" in MEMORY_STRUCTURES
    assert MEMORY_STRUCTURES["FontGlyph"].size_hex == "0x0C"
    assert "RdbnHeader" in MEMORY_STRUCTURES
    assert MEMORY_STRUCTURES["RdbnHeader"].size_hex == "0x50"


def test_nie_re_map_serialization() -> None:
    re_map = get_nie_re_map()
    d = re_map.to_dict()
    assert isinstance(d, dict)
    encoded = json.dumps(d)
    decoded = json.loads(encoded)
    assert decoded["target_binary"] == "nie.exe"
    assert len(decoded["crypto_constants"]) == 7
    assert len(decoded["critical_offsets"]) == 8


def test_crand_canonical_mt19937_vectors() -> None:
    # Graine 5489 — vecteur canonique MT19937
    with CRand(seed=5489, use_native=False) as rand:
        v1 = rand.next_u32()
        v2 = rand.next_u32()
        v3 = rand.next_u32()
        assert v1 == 3499211612
        assert v2 == 581869302
        assert v3 == 3890346734


def test_crand_native_or_pure_parity() -> None:
    with CRand(seed=5489) as rand:
        vals = [rand.next_u32() for _ in range(5)]
        assert vals[:3] == [3499211612, 581869302, 3890346734]


def test_crand_bounded() -> None:
    with CRand(seed=1234) as rand:
        for _ in range(50):
            b = rand.bounded(10)
            assert 0 <= b < 10

        # bound == 0 retourne le tirage brut
        raw = rand.bounded(0)
        assert isinstance(raw, int)


def test_crand_float() -> None:
    with CRand(seed=42) as rand:
        for _ in range(50):
            f = rand.next_f32()
            assert 0.0 <= f < 1.0


def test_crand_from_u64() -> None:
    seed64 = (0x12345678 << 32) | 0x9ABCDEF0
    rand = CRand.from_u64(seed64)
    val = rand.next_u32()
    assert isinstance(val, int)
    rand.close()
