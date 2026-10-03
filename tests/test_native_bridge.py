"""Tests unitaires du pont natif IECODE.Ffi vers IECODE.Core (C# NativeAOT)."""

import re

import pytest
from niepy.native_bridge import IecodeBridge, chemin_iecode_ffi


def test_iecode_ffi_presence():
    """Le binaire IECODE.Ffi est résolu et disponible."""
    p = chemin_iecode_ffi()
    assert p is not None
    assert p.is_file()
    assert IecodeBridge.est_disponible()


def test_iecode_version_et_schema():
    """La version et le schéma retournés correspondent aux contrats IECODE.Core."""
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", IecodeBridge.version())
    assert IecodeBridge.schema() == "iecode.ffi/v1"


def test_iecode_crc32():
    """Le CRC32 Level-5 correspond aux vecteurs connus."""
    assert IecodeBridge.crc32(b"Focus") == 0xA30165ED
    assert IecodeBridge.crc32(b"") == 0


def test_iecode_crilayla_roundtrip():
    """Compression et décompression CRILAYLA conservent les données."""
    payload = b"Inazuma Eleven Victory Road IECODE Native Bridge"
    comp = IecodeBridge.compresser_crilayla(payload)
    assert len(comp) > 16
    assert comp[:8] == b"CRILAYLA"

    decomp = IecodeBridge.decompresser_crilayla(comp)
    assert decomp.startswith(payload)


def test_nie_ffi_pure():
    """Vérifie l'exposition pure des capacités du crate Rust aphrody-nie-ffi."""
    from niepy.native_bridge import NieFfiPure

    v = NieFfiPure.version()
    assert v != "?" and len(v) > 0

    info = NieFfiPure.info_build()
    if info:
        assert info.get("product") == "iecode"
        assert "capabilities" in info

    assert not NieFfiPure.sonder_cpk(b"NOT_A_CPK")
    assert NieFfiPure.sonder_cpk(b"CPK \x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")


def test_libraries_resolve_from_path_without_checkout(tmp_path, monkeypatch):
    import niepy._ffi as rust_ffi
    import niepy.native_bridge as managed_ffi

    monkeypatch.delenv("NIE_FFI_PATH", raising=False)
    monkeypatch.delenv("IECODE_FFI_PATH", raising=False)
    monkeypatch.setattr(rust_ffi.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(rust_ffi, "_racine_depot", lambda: None)
    monkeypatch.setattr(managed_ffi, "_racine_depot", lambda: None)
    destination = tmp_path / "bin"
    destination.mkdir()
    rust = destination / rust_ffi._noms_possibles()[0]
    managed = destination / managed_ffi._noms_iecode_possibles()[0]
    rust.touch()
    managed.touch()
    assert rust_ffi.chemin_bibliotheque() == rust
    assert managed_ffi.chemin_iecode_ffi() == managed

    override = tmp_path / "override.so"
    override.touch()
    monkeypatch.setenv("NIE_FFI_PATH", str(override))
    monkeypatch.setenv("IECODE_FFI_PATH", str(override))
    assert rust_ffi.chemin_bibliotheque() == override
    assert managed_ffi.chemin_iecode_ffi() == override
