"""Tests exhaustifs de l'ensemble des commandes CLI niepy (émulation nie.exe, formats, vfs, crypto)."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from niepy.__main__ import main


def test_cli_info() -> None:
    code = main(["info"])
    assert code == 0


def test_cli_re_plain_and_json(capsys) -> None:
    code = main(["re"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Spécification Rétro-Ingénierie" in captured.out
    assert "VIOLA_FIXED_KEY" in captured.out
    assert "GameTickLoop" in captured.out

    code_json = main(["re", "--json"])
    assert code_json == 0
    captured_json = capsys.readouterr()
    data = json.loads(captured_json.out)
    assert data["target_binary"] == "nie.exe"
    assert len(data["crypto_constants"]) == 7


def test_cli_formats_list_and_probe(capsys) -> None:
    code = main(["formats"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Catalogue des 28 Formats" in captured.out

    code_json = main(["formats", "--json"])
    assert code_json == 0
    captured_json = capsys.readouterr()
    formats_list = json.loads(captured_json.out)
    assert len(formats_list) == 28

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "sample.g4tx"
        test_file.write_bytes(b"G4TX\x60\x00\x00\x00" + b"\x00" * 90)

        code_probe = main(["formats", "--probe", str(test_file)])
        assert code_probe == 0
        cap_probe = capsys.readouterr()
        assert "G4TX" in cap_probe.out

        code_probe_json = main(["formats", "--probe", str(test_file), "--json"])
        assert code_probe_json == 0
        cap_probe_json = capsys.readouterr()
        probe_data = json.loads(cap_probe_json.out)
        assert probe_data["id"] == 1
        assert probe_data["name"] == "G4TX"


def test_cli_vfs_rules_and_topology(capsys) -> None:
    code_rules = main(["vfs", "rules"])
    assert code_rules == 0
    cap_rules = capsys.readouterr()
    assert "common.cpk" in cap_rules.out
    assert "cpk_list.cfg.bin" in cap_rules.out

    code_topo = main(["vfs", "topology"])
    assert code_topo == 0
    cap_topo = capsys.readouterr()
    assert "data/common/" in cap_topo.out
    assert "data/menu/" in cap_topo.out


def test_cli_crand(capsys) -> None:
    code = main(["crand", "--seed", "5489", "--count", "3"])
    assert code == 0
    cap = capsys.readouterr()
    assert "3499211612" in cap.out

    code_bound = main(["crand", "--seed", "1234", "--count", "5", "--bound", "20"])
    assert code_bound == 0

    code_float = main(["crand", "--seed", "1234", "--count", "5", "--flottant"])
    assert code_float == 0


def test_cli_crilayla_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        raw_f = Path(tmp_dir) / "raw.bin"
        comp_f = Path(tmp_dir) / "compressed.crilayla"
        decomp_f = Path(tmp_dir) / "decompressed.bin"

        content = b"CLI Roundtrip Payload Data For CRILAYLA Stream Testing " * 10
        raw_f.write_bytes(content)

        # Compression via CLI
        code_comp = main(["crilayla", "compress", str(raw_f), "--out", str(comp_f)])
        assert code_comp == 0
        assert comp_f.is_file()

        # Décompression via CLI
        code_decomp = main(["crilayla", "decompress", str(comp_f), "--out", str(decomp_f)])
        assert code_decomp == 0
        assert decomp_f.is_file()
        assert decomp_f.read_bytes() == content


def test_cli_rdbn_probe(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        rdbn_f = Path(tmp_dir) / "test.cfg.bin"
        rdbn_f.write_bytes(b"RDBN\x50\x00\x01\x00" + b"\x00" * 80)

        code = main(["rdbn", "probe", str(rdbn_f)])
        assert code == 0
        cap = capsys.readouterr()
        assert "RDBN=True" in cap.out
        assert "Version     : 1" in cap.out


def test_cli_cpk_info(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        cpk_f = Path(tmp_dir) / "test.cpk"
        cpk_f.write_bytes(b"CPK \x00\x08\x00\x00" + b"\x00" * 30)

        code = main(["cpk", "info", str(cpk_f)])
        assert code == 0
        cap = capsys.readouterr()
        info = json.loads(cap.out)
        assert info.get("isValid") or "sectorSize" in info
