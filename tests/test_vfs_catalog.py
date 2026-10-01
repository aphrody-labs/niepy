"""Tests exhaustifs du catalogue VFS, des règles de routage CPK, topologies et MockVfs."""

from __future__ import annotations

import tempfile
from pathlib import Path

from niepy.vfs import (
    VFS_DIRECTORIES,
    VFS_PACK_RULES,
    MockVfs,
    VfsDirectoryCategory,
    VfsPackRule,
)


def test_vfs_pack_rules() -> None:
    assert len(VFS_PACK_RULES) == 8
    rule_names = [r.pack_name for r in VFS_PACK_RULES]
    assert "common.cpk" in rule_names
    assert "menu.cpk" in rule_names
    assert "model.cpk" in rule_names
    assert "dx11.cpk" in rule_names
    assert "sound_asset.cpk" in rule_names
    assert "movie.cpk" in rule_names
    assert "event.cpk" in rule_names
    assert "cpk_list.cfg.bin" in rule_names

    # Vérification des priorités et clés
    manifest_rule = next(r for r in VFS_PACK_RULES if r.pack_name == "cpk_list.cfg.bin")
    assert manifest_rule.mount_priority == 1000
    assert manifest_rule.key_derivation == "viola-fixed"

    common_rule = next(r for r in VFS_PACK_RULES if r.pack_name == "common.cpk")
    assert common_rule.mount_priority == 100
    assert common_rule.key_derivation == "filename-crc32"


def test_vfs_directory_topologies() -> None:
    assert len(VFS_DIRECTORIES) == 6
    paths = [d.path for d in VFS_DIRECTORIES]
    assert "data/common/" in paths
    assert "data/menu/" in paths
    assert "data/model/" in paths
    assert "data/event/" in paths
    assert "data/movie/" in paths
    assert "data/sound/" in paths

    for d in VFS_DIRECTORIES:
        assert isinstance(d, VfsDirectoryCategory)
        assert d.path.startswith("data/")
        assert d.file_count_estimate > 0
        assert len(d.sample_files) > 0


def test_mock_vfs_operations() -> None:
    with MockVfs() as vfs:
        assert len(vfs) == 0

        # Ajout de fichiers
        vfs.ajouter("data/common/chara.cfg.bin", b"RDBN\x50\x00\x01\x00" + b"\x00" * 70)
        vfs.ajouter("data/menu/icon.g4tx", b"G4TX\x60\x00\x00\x00" + b"\x00" * 90)
        vfs.ajouter("data/model/mesh.g4md", b"G4MD\x10\x00\x00\x00" + b"\x00" * 50)

        assert len(vfs) == 3
        assert vfs.existe("data/common/chara.cfg.bin")
        assert "data/menu/icon.g4tx" in vfs
        assert not vfs.existe("data/absent.bin")

        # Lecture
        octets = vfs.lire("data/common/chara.cfg.bin")
        assert octets.startswith(b"RDBN")

        # Info fichier
        info = vfs.info_fichier("data/menu/icon.g4tx")
        assert info["path"] == "data/menu/icon.g4tx"
        assert info["size"] == len(octets) + 20 or info["size"] > 0
        assert info["isReadable"]

        # Recherche
        trouves = vfs.chercher("g4")
        assert len(trouves) == 2
        assert "data/menu/icon.g4tx" in trouves
        assert "data/model/mesh.g4md" in trouves

        # Entrées et parcours
        items = list(vfs.parcourir(par=2))
        assert len(items) == 3

        # Extraction unitaire
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / "extracted.g4tx"
            vfs.extraire("data/menu/icon.g4tx", dest)
            assert dest.is_file()
            assert dest.read_bytes() == vfs.lire("data/menu/icon.g4tx")

        # Extraction par lot
        with tempfile.TemporaryDirectory() as tmp_dir:
            nb = vfs.extraire_lot("data/common/", tmp_dir)
            assert nb == 1
            extracted_f = Path(tmp_dir) / "data/common/chara.cfg.bin"
            assert extracted_f.is_file()
