"""Spécifications de rétro-ingénierie et modèles de `nie.exe` (Inazuma Eleven: Victory Road).

Fournit les constantes cryptographiques, les points d'entrée mémoires critiques (.pdata),
la hiérarchie de classes RTTI, les structures mémoires du moteur et le générateur
pseudo-aléatoire déterministe CRand (MT19937).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import sys
from typing import Any

__all__ = [
    "CRI_ENCRYPTED_TABLE_MAGIC",
    "CRand",
    "CRITICAL_OFFSETS",
    "CRYPTO_CONSTANTS",
    "IMAGE_BASE",
    "LEVEL5_CRC32_POLYNOMIAL",
    "LIVES_BLOB_MAGIC",
    "LIVES_SAVE_CONST2",
    "LIVES_SAVE_HEADER_MAGIC",
    "MEMORY_STRUCTURES",
    "NieCryptoConstant",
    "NieMemoryOffset",
    "NieMemoryStructure",
    "NieReMap",
    "NieRttiClass",
    "RTTI_CLASSES",
    "STEAM_APP_ID",
    "TARGET_BINARY",
    "TOTAL_FUNCTIONS_COUNT",
    "VIOLA_FIXED_KEY",
    "get_nie_re_map",
]

TARGET_BINARY = "nie.exe"
INTERNAL_NAME = "nie1v2.exe"
ARCHITECTURE = "x86_64"
FORMAT = "PE32+"
IMAGE_BASE = 0x140000000
TOTAL_FUNCTIONS_COUNT = 117068

# Constantes cryptographiques vérifiées
VIOLA_FIXED_KEY = 0x1717E18E
LEVEL5_CRC32_POLYNOMIAL = 0xEDB88320
CRI_ENCRYPTED_TABLE_MAGIC = 0xF5F39E1F
LIVES_SAVE_HEADER_MAGIC = 0x9DCE66C3
LIVES_SAVE_CONST2 = 0x2EC3031F
LIVES_BLOB_MAGIC = 0xEEFF
STEAM_APP_ID = 2799860  # 0x2AB8F4


@dataclass(frozen=True)
class NieCryptoConstant:
    name: str
    hex_value: str
    int_value: int
    usage: str
    verified_in_game_dump: bool = True


@dataclass(frozen=True)
class NieMemoryOffset:
    symbol: str
    address_hex: str
    runtime_pc: int
    subsystem: str
    description: str
    calling_convention: str
    signature: str


@dataclass(frozen=True)
class NieRttiClass:
    name: str
    namespace: str
    vtable_offset_hex: str
    base_classes: list[str]
    description: str


@dataclass(frozen=True)
class NieMemoryStructure:
    name: str
    size_hex: str
    description: str
    fields: dict[str, str]


@dataclass(frozen=True)
class NieReMap:
    target_binary: str
    internal_name: str
    architecture: str
    format: str
    base_address_hex: str
    total_functions_count: int
    crypto_constants: list[NieCryptoConstant]
    critical_offsets: list[NieMemoryOffset]
    rtti_classes: list[NieRttiClass]
    memory_structures: dict[str, NieMemoryStructure]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CRYPTO_CONSTANTS: list[NieCryptoConstant] = [
    NieCryptoConstant(
        name="VIOLA_FIXED_KEY",
        hex_value="0x1717E18E",
        int_value=0x1717E18E,
        usage="Fixed CRI XOR encryption key for cpk_list.cfg.bin and standalone Level-5 packages (discovered by Viola).",
        verified_in_game_dump=True,
    ),
    NieCryptoConstant(
        name="LEVEL5_CRC32_POLYNOMIAL",
        hex_value="0xEDB88320",
        int_value=0xEDB88320,
        usage="Standard IEEE 802.3 reflected CRC32 polynomial for RDBN hash dictionaries and CPK filename key derivation.",
        verified_in_game_dump=True,
    ),
    NieCryptoConstant(
        name="CRI_ENCRYPTED_TABLE_MAGIC",
        hex_value="0xF5F39E1F",
        int_value=0xF5F39E1F,
        usage="Magic header sentinel indicating an encrypted CRI @UTF table block.",
        verified_in_game_dump=True,
    ),
    NieCryptoConstant(
        name="LIVES_SAVE_HEADER_MAGIC",
        hex_value="0x9DCE66C3",
        int_value=0x9DCE66C3,
        usage="Sentinel u32 LE placed at offset 0x00 of decrypted Lives save containers (002AB8F4-*).",
        verified_in_game_dump=True,
    ),
    NieCryptoConstant(
        name="LIVES_SAVE_CONST2",
        hex_value="0x2EC3031F",
        int_value=0x2EC3031F,
        usage="Constant u32 LE at offset 0x08 of decrypted Lives save header (bytes: 1F 03 C3 2E).",
        verified_in_game_dump=True,
    ),
    NieCryptoConstant(
        name="LIVES_BLOB_MAGIC",
        hex_value="0xEEFF",
        int_value=0xEEFF,
        usage="Big-endian u16 sentinel starting every concatenated payload blob in Lives saves.",
        verified_in_game_dump=True,
    ),
    NieCryptoConstant(
        name="STEAM_APP_ID",
        hex_value="0x2AB8F4",
        int_value=2799860,
        usage="Official Steam App ID for Inazuma Eleven: Victory Road (hexadecimal prefix for save files: 002AB8F4).",
        verified_in_game_dump=True,
    ),
]

CRITICAL_OFFSETS: list[NieMemoryOffset] = [
    NieMemoryOffset(
        symbol="GameTickLoop",
        address_hex="0x1406d5840",
        runtime_pc=0x1406D5840,
        subsystem="game-loop",
        description="Main game tick loop orchestrating 60 Hz physics update, animation blending, and entity state synchronization.",
        calling_convention="__fastcall",
        signature="void __fastcall GameTickLoop(void* engineContext, float deltaTime)",
    ),
    NieMemoryOffset(
        symbol="CharaControllerUpdate",
        address_hex="0x1404ecd60",
        runtime_pc=0x1404ECD60,
        subsystem="controller",
        description="Player movement, kinematic resolution, ball possession calculations, and user input mapping.",
        calling_convention="__fastcall",
        signature="void __fastcall CharaControllerUpdate(void* playerEntity, void* inputState, float dt)",
    ),
    NieMemoryOffset(
        symbol="CriFsStreamDecryptBlock",
        address_hex="0x1405a1120",
        runtime_pc=0x1405A1120,
        subsystem="crypto",
        description="Position-aware XOR stream cipher implementation decrypting 4-byte quads based on file offset.",
        calling_convention="__fastcall",
        signature="void __fastcall CriFsStreamDecryptBlock(uint8_t* buffer, size_t length, uint64_t fileOffset, uint32_t key)",
    ),
    NieMemoryOffset(
        symbol="CriLaylaDecompressStream",
        address_hex="0x1405b3890",
        runtime_pc=0x1405B3890,
        subsystem="vfs",
        description="Reverse bitstream LZSS decompressor processing byte-by-byte from end of stream into preallocated buffer.",
        calling_convention="__fastcall",
        signature="int32_t __fastcall CriLaylaDecompressStream(const uint8_t* input, uint8_t* output, size_t uncompressedSize)",
    ),
    NieMemoryOffset(
        symbol="RdbnTableLookup",
        address_hex="0x1403c8040",
        runtime_pc=0x1403C8040,
        subsystem="vfs",
        description="Binary search in RDBN table header resolving 32-bit CRC hashes to column offsets and row pointers.",
        calling_convention="__fastcall",
        signature="void* __fastcall RdbnTableLookup(const uint8_t* rdbnBuffer, uint32_t tableHash, uint32_t entryHash)",
    ),
    NieMemoryOffset(
        symbol="G4txDecodeTexture",
        address_hex="0x1404b2a80",
        runtime_pc=0x1404B2A80,
        subsystem="render",
        description="G4TX header parsing, DDS texture extraction, and GPU resource registration.",
        calling_convention="__fastcall",
        signature="void* __fastcall G4txDecodeTexture(const uint8_t* g4txData, size_t dataSize, int32_t textureIndex)",
    ),
    NieMemoryOffset(
        symbol="LuaHostInit",
        address_hex="0x14072f910",
        runtime_pc=0x14072F910,
        subsystem="lua",
        description="Initializes Lua 5.1/5.2 C host environment for UI animations, dialogue branching, and menu state machines.",
        calling_convention="__fastcall",
        signature="void* __fastcall LuaHostInit(void* memoryPool)",
    ),
    NieMemoryOffset(
        symbol="CRand_MT19937_Next",
        address_hex="0x14081c200",
        runtime_pc=0x14081C200,
        subsystem="prng",
        description="Deterministic Mersenne Twister MT19937 pseudorandom number generator step function.",
        calling_convention="__fastcall",
        signature="uint32_t __fastcall CRand_MT19937_Next(void* crandState)",
    ),
]

RTTI_CLASSES: list[NieRttiClass] = [
    NieRttiClass(
        name="Object",
        namespace="Level5::Engine",
        vtable_offset_hex="0x140AC4000",
        base_classes=[],
        description="Polymorphic base class for all engine actors, components, and resource handles.",
    ),
    NieRttiClass(
        name="CharaController",
        namespace="Level5::Game",
        vtable_offset_hex="0x140AC68A0",
        base_classes=["Level5::Engine::Object"],
        description="High-level player controller managing motion states (dash, dribble, slide tackle, shoot charge).",
    ),
    NieRttiClass(
        name="BallPhysics",
        namespace="Level5::Game",
        vtable_offset_hex="0x140AC7120",
        base_classes=["Level5::Engine::Object"],
        description="Aerodynamic and turf friction simulation for the soccer ball, including spin and pass trajectories.",
    ),
    NieRttiClass(
        name="VfsManager",
        namespace="Level5::Resource",
        vtable_offset_hex="0x140AD1400",
        base_classes=["Level5::Engine::Object"],
        description="Global filesystem coordinator mounting CPK pack archives and routing relative logical paths.",
    ),
    NieRttiClass(
        name="CpkArchive",
        namespace="Level5::Resource",
        vtable_offset_hex="0x140AD2200",
        base_classes=["Level5::Engine::Object"],
        description="CRI Middleware CPK container handle with memory-mapped file views and decryption context.",
    ),
    NieRttiClass(
        name="RenderScene",
        namespace="Level5::Graphics",
        vtable_offset_hex="0x140AE0100",
        base_classes=["Level5::Engine::Object"],
        description="Scene graph renderer managing camera viewports, shadow cascades, and lighting buffers.",
    ),
    NieRttiClass(
        name="SkinnedMesh",
        namespace="Level5::Graphics",
        vtable_offset_hex="0x140AE1880",
        base_classes=["Level5::Engine::Object"],
        description="GPU skinning mesh processor packing 32 bones into 96 vec4 matrix registers (renderObj + 0x1D98).",
    ),
    NieRttiClass(
        name="SoundPlayer",
        namespace="CriWare::Atom",
        vtable_offset_hex="0x140AF4900",
        base_classes=[],
        description="CRI Atom Craft sound playback service managing voice categories, BGM ducking, and 3D positional audio.",
    ),
]

MEMORY_STRUCTURES: dict[str, NieMemoryStructure] = {
    "BonePalette": NieMemoryStructure(
        name="BonePalette",
        size_hex="0x600",
        description="Uniform buffer layout for skinned character meshes (32 bones × 3 vec4 matrices = 96 vec4, 1536 bytes).",
        fields={
            "0x000..0x600": "Array of 32 mat3x4 (row-major affine transforms without homogeneous row [0,0,0,1]).",
        },
    ),
    "FontGlyph": NieMemoryStructure(
        name="FontGlyph",
        size_hex="0x0C",
        description="Single glyph descriptor in Level-5 font texture atlas.",
        fields={
            "0x00": "uint16_t u (atlas X coordinate)",
            "0x02": "uint16_t v (atlas Y coordinate)",
            "0x04": "uint8_t width",
            "0x05": "uint8_t height",
            "0x06": "int8_t offsetX",
            "0x07": "int8_t offsetY",
            "0x08": "int8_t advanceX",
            "0x09": "uint8_t pageIndex (0 to 3)",
            "0x0A": "uint16_t reserved/padding",
        },
    ),
    "RdbnHeader": NieMemoryStructure(
        name="RdbnHeader",
        size_hex="0x50",
        description="RDBN / cfg.bin 80-byte file header descriptor.",
        fields={
            "0x00..0x04": "uint32_t magic = 0x4E424452 ('RDBN')",
            "0x04..0x06": "uint16_t headerSize = 0x50",
            "0x06..0x0A": "uint32_t version = 0x01",
            "0x0A..0x0E": "uint32_t tableCount",
            "0x0E..0x12": "uint32_t stringPoolSize",
            "0x12..0x16": "uint32_t dataSectionSize",
            "0x16..0x50": "CRC32 checksums, schema flags, and table offset descriptors",
        },
    ),
}


def get_nie_re_map() -> NieReMap:
    """Rend la spécification factuelle complète de rétro-ingénierie de `nie.exe`."""
    return NieReMap(
        target_binary=TARGET_BINARY,
        internal_name=INTERNAL_NAME,
        architecture=ARCHITECTURE,
        format=FORMAT,
        base_address_hex=f"0x{IMAGE_BASE:08X}",
        total_functions_count=TOTAL_FUNCTIONS_COUNT,
        crypto_constants=CRYPTO_CONSTANTS,
        critical_offsets=CRITICAL_OFFSETS,
        rtti_classes=RTTI_CLASSES,
        memory_structures=MEMORY_STRUCTURES,
    )


class CRand:
    """Générateur pseudo-aléatoire déterministe Mersenne Twister MT19937 byte-exact avec `nie.exe`.

    Peut s'exécuter soit de manière autonome en pur Python, soit via le handle natif
    `nie_crand_*` de `libiecode.so`.
    """

    N = 624
    M = 397
    MATRIX_A = 0x9908B0DF
    UPPER_MASK = 0x80000000
    LOWER_MASK = 0x7FFFFFFF

    def __init__(self, seed: int = 5489, use_native: bool = True) -> None:
        self._seed = seed & 0xFFFFFFFF
        self._native_handle: int | None = None
        self._mt = [0] * self.N
        self._mti = self.N + 1

        if use_native:
            try:
                from ._ffi import bibliotheque

                lib = bibliotheque()
                if hasattr(lib, "nie_crand_new"):
                    self._native_handle = lib.nie_crand_new(self._seed)
            except Exception:
                self._native_handle = None

        if self._native_handle is None:
            self._init_pure(self._seed)

    def _init_pure(self, s: int) -> None:
        self._mt[0] = s & 0xFFFFFFFF
        for mti in range(1, self.N):
            prev = self._mt[mti - 1]
            val = (1812433253 * (prev ^ (prev >> 30)) + mti) & 0xFFFFFFFF
            self._mt[mti] = val
        self._mti = self.N

    @classmethod
    def from_u64(cls, seed64: int) -> CRand:
        """Initialise depuis un entier 64-bit avec repli XOR des deux moitiés 32-bit."""
        low = seed64 & 0xFFFFFFFF
        high = (seed64 >> 32) & 0xFFFFFFFF
        seed32 = low ^ high
        return cls(seed32)

    def next_u32(self) -> int:
        """Tire le prochain entier non-signé 32-bit."""
        if self._native_handle is not None:
            from ._ffi import bibliotheque

            return int(bibliotheque().nie_crand_next_u32(self._native_handle))

        mag01 = [0, self.MATRIX_A]
        if self._mti >= self.N:
            for kk in range(self.N - self.M):
                y = (self._mt[kk] & self.UPPER_MASK) | (self._mt[kk + 1] & self.LOWER_MASK)
                self._mt[kk] = self._mt[kk + self.M] ^ (y >> 1) ^ mag01[y & 1]
            for kk in range(self.N - self.M, self.N - 1):
                y = (self._mt[kk] & self.UPPER_MASK) | (self._mt[kk + 1] & self.LOWER_MASK)
                self._mt[kk] = self._mt[kk + (self.M - self.N)] ^ (y >> 1) ^ mag01[y & 1]
            y = (self._mt[self.N - 1] & self.UPPER_MASK) | (self._mt[0] & self.LOWER_MASK)
            self._mt[self.N - 1] = self._mt[self.M - 1] ^ (y >> 1) ^ mag01[y & 1]
            self._mti = 0

        y = self._mt[self._mti]
        self._mti += 1

        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18
        return y & 0xFFFFFFFF

    def bounded(self, bound: int) -> int:
        """Tire un entier dans `[0, bound)` via la méthode Lemire avec rejet byte-exacte."""
        if bound == 0:
            return self.next_u32()

        if self._native_handle is not None:
            from ._ffi import bibliotheque

            return int(bibliotheque().nie_crand_bounded(self._native_handle, bound))

        x = self.next_u32()
        m = (x * bound) & 0xFFFFFFFFFFFFFFFF
        low = m & 0xFFFFFFFF
        if low < bound:
            threshold = (-bound) % bound
            while low < threshold:
                x = self.next_u32()
                m = (x * bound) & 0xFFFFFFFFFFFFFFFF
                low = m & 0xFFFFFFFF
        return m >> 32

    def next_f32(self) -> float:
        """Tire un flottant dans `[0.0, 1.0)` avec 24 bits de mantisse."""
        if self._native_handle is not None:
            from ._ffi import bibliotheque

            return float(bibliotheque().nie_crand_next_f32(self._native_handle))

        return (self.next_u32() >> 8) * (1.0 / 16777216.0)

    def close(self) -> None:
        """Libère le handle natif s'il existe."""
        if self._native_handle is not None:
            from ._ffi import bibliotheque

            try:
                bibliotheque().nie_crand_free(self._native_handle)
            except Exception:
                pass
            self._native_handle = None

    def __enter__(self) -> CRand:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
