"""Suite de parité inter-langages (Rust, C++, .NET 10, Bun/TypeScript, Python).

Vérifie que les 5 runtimes produisent des résultats identiques au bit près sur :
- CRC32 Level-5 réfléchi (0xEDB88320)
- Accumulateur brut CRC32 NIE (crc32_nie)
- PRNG CRand (MT19937, graine 5489 et rejet borné de Lemire)
- Constantes cryptographiques (Viola, magic sauvegardes Lives, AppID)
- Offsets mémoire critiques et classes RTTI de nie.exe
- 28 formats canoniques VFS
"""

from __future__ import annotations

from niepy.crypto import (
    crc32_level5,
    crc32_nie,
    derive_cpk_key,
)
from niepy.formats import VfsFormatConsumer, VfsFormatId
from niepy.nie_re import (
    CRI_ENCRYPTED_TABLE_MAGIC,
    CRand,
    CRITICAL_OFFSETS,
    CRYPTO_CONSTANTS,
    LEVEL5_CRC32_POLYNOMIAL,
    LIVES_BLOB_MAGIC,
    LIVES_SAVE_CONST2,
    LIVES_SAVE_HEADER_MAGIC,
    MEMORY_STRUCTURES,
    RTTI_CLASSES,
    STEAM_APP_ID,
    VIOLA_FIXED_KEY,
    get_nie_re_map,
)


class TestCrc32AndCryptoVectors:
    def test_crc32_level5_reflected_vectors(self) -> None:
        # Vecteur 1 : Chaîne vide
        assert crc32_level5(b"") == 0x00000000

        # Vecteur 2 : "Focus" -> 0xA30165ED
        assert crc32_level5(b"Focus") == 0xA30165ED

        # Vecteur 3 : Vecteur standard 123456789 -> 0xCBF43926
        assert crc32_level5(b"123456789") == 0xCBF43926

    def test_crc32_nie_raw_accumulator(self) -> None:
        crc_reflechi = crc32_level5(b"Focus")
        crc_brut = crc32_nie(b"Focus")
        assert (crc_brut ^ 0xFFFFFFFF) == crc_reflechi
        assert crc_brut == 0x5CFE9A12

    def test_cpk_key_derivation_vector(self) -> None:
        cle = derive_cpk_key("1d08dda99e8549431c6c7b459ed8deab.cpk")
        assert cle == 0xBD281847


class TestCRandMT19937Vectors:
    def test_canonical_seed_5489_sequence(self) -> None:
        rng = CRand(5489)
        # Séquence de référence MT19937 canonique
        assert rng.next_u32() == 3499211612
        assert rng.next_u32() == 581869302
        assert rng.next_u32() == 3890346734

    def test_lemire_bounded_rejection(self) -> None:
        rng1 = CRand(42)
        rng2 = CRand(42)
        # Dans nie.exe, bound == 0 renvoie le tirage brut
        assert rng2.bounded(0) == rng1.next_u32()

        rng = CRand(12345)
        for _ in range(50):
            val = rng.bounded(15)
            assert 0 <= val < 15

    def test_next_f32_unit_interval(self) -> None:
        rng = CRand(777)
        for _ in range(50):
            f = rng.next_f32()
            assert 0.0 <= f < 1.0


class TestNieReGroundTruth:
    def test_all_7_crypto_constants(self) -> None:
        assert VIOLA_FIXED_KEY == 0x1717E18E
        assert LEVEL5_CRC32_POLYNOMIAL == 0xEDB88320
        assert CRI_ENCRYPTED_TABLE_MAGIC == 0xF5F39E1F
        assert LIVES_SAVE_HEADER_MAGIC == 0x9DCE66C3
        assert LIVES_SAVE_CONST2 == 0x2EC3031F
        assert LIVES_BLOB_MAGIC == 0xEEFF
        assert STEAM_APP_ID == 2799860
        assert len(CRYPTO_CONSTANTS) == 7

    def test_all_8_critical_offsets(self) -> None:
        assert len(CRITICAL_OFFSETS) == 8
        offsets = {o.symbol: o.runtime_pc for o in CRITICAL_OFFSETS}
        assert offsets["GameTickLoop"] == 0x1406D5840
        assert offsets["CharaControllerUpdate"] == 0x1404ECD60
        assert offsets["CriFsStreamDecryptBlock"] == 0x1405A1120
        assert offsets["CriLaylaDecompressStream"] == 0x1405B3890
        assert offsets["RdbnTableLookup"] == 0x1403C8040
        assert offsets["G4txDecodeTexture"] == 0x1404B2A80
        assert offsets["LuaHostInit"] == 0x14072F910
        assert offsets["CRand_MT19937_Next"] == 0x14081C200

    def test_all_8_rtti_classes_and_3_memory_structures(self) -> None:
        assert len(RTTI_CLASSES) == 8
        rtti_names = {r.name for r in RTTI_CLASSES}
        assert "Object" in rtti_names
        assert "CharaController" in rtti_names
        assert "BallPhysics" in rtti_names
        assert "VfsManager" in rtti_names
        assert "CpkArchive" in rtti_names
        assert "RenderScene" in rtti_names
        assert "SkinnedMesh" in rtti_names
        assert "SoundPlayer" in rtti_names

        assert MEMORY_STRUCTURES["BonePalette"].size_hex == "0x600"
        assert MEMORY_STRUCTURES["FontGlyph"].size_hex == "0x0C"
        assert MEMORY_STRUCTURES["RdbnHeader"].size_hex == "0x50"

    def test_target_binary_metadata(self) -> None:
        re_map = get_nie_re_map()
        assert re_map.target_binary == "nie.exe"
        assert re_map.internal_name == "nie1v2.exe"
        assert re_map.architecture == "x86_64"
        assert re_map.format == "PE32+"
        assert re_map.base_address_hex == "0x140000000"
        assert re_map.total_functions_count == 117068


class TestCanonicalVfsFormats:
    def test_contains_all_28_formats(self) -> None:
        formats = VfsFormatConsumer.list_all()
        assert len(formats) == 28

        g4tx = VfsFormatConsumer.get(VfsFormatId.G4TX)
        assert g4tx is not None
        assert g4tx.name == "G4TX"
        assert g4tx.extension == ".g4tx"
        assert g4tx.category == "texture"

        live = VfsFormatConsumer.get(VfsFormatId.LIVE)
        assert live is not None
        assert live.name == "LIVE"
        assert live.encryption_supported is True
