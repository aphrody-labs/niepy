"""L'index des scènes.

La logique d'appairage est testée sur un VFS synthétique — c'est ce qui permet de vérifier
des cas que le vrai jeu ne présente pas forcément (une scène sans texte, une langue absente).
Les cas adossés au vrai jeu vérifient que la structure supposée est bien celle du jeu, et
annoncent leur saut quand les données manquent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("niepy")

from niepy.scenes import (  # noqa: E402
    LANGUES,
    LANGUES_DOUBLEES,
    MOTIF_CLE,
    Scenario,
    Scene,
    lignes_de,
)


class VfsFactice:
    """Un VFS minimal : juste `parcourir`, ce dont `Scenario.indexer` a besoin."""

    def __init__(self, chemins: list[str]) -> None:
        self.chemins = chemins

    def parcourir(self, par: int = 5000):  # noqa: ANN201
        for chemin in self.chemins:
            yield {"path": chemin, "size": 1}


CHEMINS = [
    "data/common/text/fr/event/ev01_01700.cfg.bin",
    "data/common/text/en/event/ev01_01700.cfg.bin",
    "data/common/text/ja/event/ev01_01700.cfg.bin",
    "data/common/gamedata/event/subtitle/fr/Subtitle_ev01_01700.cfg.bin",
    "data/common/sound/ja/ev01_01700_010_020.p3lip",
    "data/common/sound/ja/ev01_01700_010_010.p3lip",
    "data/common/sound/en/ev01_01700_010_010.p3lip",
    # Une deuxième scène, non doublée et traduite dans une seule langue.
    "data/common/text/fr/event/ev02_00100.cfg.bin",
    # Table de correspondance SANS segment de langue : ne doit PAS compter comme du texte.
    "data/common/text/event/ev01_01700_map.cfg.bin",
    # Bruit : ne porte aucune clé de scène.
    "data/common/chr/c01000010/c01000010.g4md",
]


@pytest.fixture()
def scenario() -> Scenario:
    return Scenario.indexer(VfsFactice(CHEMINS))


def test_motif_de_cle() -> None:
    assert MOTIF_CLE.search("data/common/text/fr/event/ev01_01700.cfg.bin")
    assert MOTIF_CLE.search("ev40_11230").group(1) == "ev40_11230"
    assert MOTIF_CLE.search("data/common/chr/c01000010/x.g4md") is None


def test_appairage(scenario: Scenario) -> None:
    assert len(scenario) == 2
    scene = scenario.scene("ev01_01700")
    assert scene is not None
    assert scene.langues_texte == ["ja", "en", "fr"], "ordre de LANGUES, pas d'insertion"
    assert set(scene.sous_titres) == {"fr"}
    assert scene.repliques_doublees("ja") == 2
    assert scene.repliques_doublees("en") == 1
    assert scene.repliques_doublees("fr") == 0


def test_les_tables_de_correspondance_ne_sont_pas_du_texte(scenario: Scenario) -> None:
    """`data/common/text/event/…` n'a pas de segment de langue : ce n'est pas du dialogue."""
    scene = scenario.scene("ev01_01700")
    assert scene is not None
    assert "event" not in scene.textes


def test_lipsync_trie(scenario: Scenario) -> None:
    """L'ordre des répliques est celui du fichier, pas celui du parcours du VFS."""
    scene = scenario.scene("ev01_01700")
    assert scene is not None
    assert scene.lipsync["ja"] == sorted(scene.lipsync["ja"])


def test_scene_non_doublee(scenario: Scenario) -> None:
    scene = scenario.scene("ev02_00100")
    assert scene is not None
    assert not scene.est_doublee
    assert scene.langues_texte == ["fr"]


def test_chapitres(scenario: Scenario) -> None:
    assert scenario.chapitres() == {"ev01": 1, "ev02": 1}
    assert [s.cle for s in scenario.du_chapitre("ev01")] == ["ev01_01700"]


def test_filtres(scenario: Scenario) -> None:
    assert [s.cle for s in scenario.doublees()] == ["ev01_01700"]
    assert [s.cle for s in scenario.doublees("en")] == ["ev01_01700"]
    assert scenario.doublees("fr") == [], "le français n'est pas doublé"
    assert len(scenario.traduites("fr")) == 2
    assert len(scenario.traduites("de")) == 0


def test_resume(scenario: Scenario) -> None:
    resume = scenario.resume()
    assert resume["scenes"] == 2
    assert resume["chapitres"] == 2
    assert resume["texte_par_langue"]["fr"] == 2
    assert resume["doublage_par_langue"]["ja"] == 1
    assert resume["avec_sous_titres"] == 1


def test_cache_aller_retour(scenario: Scenario, tmp_path: Path) -> None:
    chemin = scenario.sauver(tmp_path / "index.json")
    relu = Scenario.charger(chemin)
    assert len(relu) == len(scenario)
    original = scenario.scene("ev01_01700")
    copie = relu.scene("ev01_01700")
    assert original is not None and copie is not None
    assert copie.textes == original.textes
    assert copie.lipsync == original.lipsync
    assert copie.sous_titres == original.sous_titres


def test_cache_absent_dit_quoi_lancer(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="niepy scenes"):
        Scenario.charger(tmp_path / "jamais-ecrit.json")


def test_langues_doublees_est_un_sous_ensemble() -> None:
    assert set(LANGUES_DOUBLEES) <= set(LANGUES)


# ── Extraction du texte ──────────────────────────────────────────────────────


def test_lignes_de_extrait_les_chaines_dans_lordre() -> None:
    """Seules les `String` des `variables` sont du texte ; les `name` sont des étiquettes."""
    document = {
        "format": "T2B",
        "entries": [
            {
                "name": "ETIQUETTE_A_IGNORER",
                "variables": [{"Int": 3}, {"String": "premiere"}],
                "children": [
                    {
                        "name": "AUSSI_A_IGNORER",
                        "variables": [{"String": "deuxieme"}, {"Float": 1.5}],
                        "children": [],
                    },
                    {"name": "x", "variables": [{"String": "troisieme"}], "children": []},
                ],
            }
        ],
    }
    assert lignes_de(document) == ["premiere", "deuxieme", "troisieme"]


def test_lignes_de_ignore_les_chaines_vides() -> None:
    document = {"entries": [{"name": "n", "variables": [{"String": ""}], "children": []}]}
    assert lignes_de(document) == []


def test_lignes_de_supporte_un_document_vide() -> None:
    assert lignes_de({}) == []
    assert lignes_de([]) == []
    assert lignes_de({"entries": []}) == []


def test_lignes_dune_scene_absente(scenario: Scenario) -> None:
    """Une langue absente rend une liste vide — cas normal, pas une erreur."""
    assert scenario.lignes("ev02_00100", "de", vfs=None) == []
    assert scenario.lignes("inexistante", "fr", vfs=None) == []


# ── Adossé au vrai jeu ───────────────────────────────────────────────────────


def _scenario_reel():  # noqa: ANN202
    from niepy import Vfs

    try:
        vfs = Vfs()
    except (FileNotFoundError, RuntimeError) as erreur:
        pytest.skip(f"jeu absent — {erreur}")
    return vfs


def test_le_jeu_porte_bien_des_milliers_de_scenes() -> None:
    """La structure supposée par ce module est-elle celle du jeu installé ?"""
    with _scenario_reel() as vfs:
        scenario = Scenario.indexer(vfs)
        resume = scenario.resume()

    assert resume["scenes"] > 1000, "le corpus de scènes est massif"
    # Le texte existe dans bien plus de langues que le doublage : c'est LE piège à ne pas
    # reproduire dans un VN, et ce test le fige.
    assert len(resume["texte_par_langue"]) > len(resume["doublage_par_langue"])
    assert set(resume["doublage_par_langue"]) == set(LANGUES_DOUBLEES)


def test_une_scene_reelle_rend_des_repliques() -> None:
    with _scenario_reel() as vfs:
        scenario = Scenario.indexer(vfs)
        candidates = scenario.traduites("fr")
        if not candidates:
            pytest.skip("aucune scène en français dans cette installation")

        for scene in candidates[:20]:
            lignes = scenario.lignes(scene, "fr", vfs)
            if lignes:
                assert all(isinstance(x, str) for x in lignes)
                return
        pytest.fail("aucune des 20 premières scènes françaises ne rend de réplique")
