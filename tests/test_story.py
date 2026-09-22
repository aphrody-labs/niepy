"""Le mode histoire : cinématiques, cartes et déclencheurs.

La grammaire des noms de fichiers d'événement est irrégulière — 52,4 % seulement suivent la
forme `<clé>_<acteur>_sNN_pNN_cNNNN`. Ces tests figent les formes réellement observées, y
compris celles qui ne portent ni acteur ni clé dans leur nom.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("niepy")

from niepy.story import (  # noqa: E402
    MOTIF_ACTEUR,
    MOTIF_PLAN,
    ZONES,
    StoryMode,
)


class VfsFactice:
    """Un VFS minimal : juste `parcourir`."""

    def __init__(self, chemins: list[str]) -> None:
        self.chemins = chemins

    def parcourir(self, par: int = 5000):  # noqa: ANN201
        for chemin in self.chemins:
            yield {"path": chemin, "size": 1}


CHEMINS = [
    # Forme majoritaire : acteur + prise + partie + plan.
    "data/common/event/ev60/ev60_01560/ev60_01560_c000401_s01_p00_c0200.g4pk",
    "data/common/event/ev60/ev60_01560/ev60_01560_c000201_s00_p00_c0200.g4pk",
    "data/common/event/ev60/ev60_01560/ev60_01560_b000001_s00_p00_c0300.g4pk",
    # La caméra : ne porte NI acteur NI numéro de plan.
    "data/common/event/ev60/ev60_01560/ev60_01560_camera.g4cm",
    # Un script d'événement.
    "data/common/event/ev60/ev60_01560/ev60_01560_c000401_s00_p00_c0600.mevbin",
    # Le décor : son nom ne porte PAS la clé — elle n'est que dans le chemin.
    "data/common/event/ev60/ev60_01560/EventMap_fix_c0200.cfg.bin",
    # Points et effets.
    "data/common/event/ev60/ev60_01560/ev60_01560_point_eff_c0100.g4pk",
    # Une autre cinématique.
    "data/common/event/ev61/ev61_00180/ev61_00180_c000101_s00_p00_c0100.g4pk",
    # Cartes.
    "data/common/map/s/s62g001/s62g001.g4mg",
    "data/common/map/s/s62g001/config/s62g001_placement.cfg.bin",
    "data/common/map/s/s62g001/s62g001.g4nv",
    "data/common/map/w/w10i000/w10i000.objbin",
    "data/common/map/w/w10i000/config/w10i000_placement.cfg.bin",
    # Table globale : à la racine de map/, ce n'est PAS une carte.
    "data/common/map/map_data_1.03.91.cfg.bin",
    "data/common/map/map_minimap_1.04.17.01.cfg.bin",
    # Déclencheurs : deux moitiés par identifiant.
    "data/common/gamedata/phase/c01_trigger_0.04.78.cfg.bin",
    "data/common/gamedata/phase/c01_trigger_0.04.78.lua.bin",
    "data/common/gamedata/quest/qsa000000_trigger_0.04.78.cfg.bin",
    "data/common/gamedata/quest/qsa000000_trigger_0.04.78.lua.bin",
    # Bruit.
    "data/common/chr/c01000010/c01000010.g4md",
]


@pytest.fixture()
def story() -> StoryMode:
    return StoryMode.indexer(VfsFactice(CHEMINS))


# ── Motifs ───────────────────────────────────────────────────────────────────


def test_motif_de_plan() -> None:
    assert MOTIF_PLAN.search("ev60_01560_c000401_s01_p00_c0200").group(1) == "0200"
    assert MOTIF_PLAN.search("EventMap_fix_c0010").group(1) == "0010"
    assert MOTIF_PLAN.search("ev60_01560_camera") is None, "la caméra n'a pas de plan"


def test_motif_dacteur() -> None:
    assert MOTIF_ACTEUR.search("_ev60_01560_c000401_s01_p00_c0200").group(1) == "c000401"
    assert MOTIF_ACTEUR.search("_ev60_01560_b000001_s00_p00_c0300").group(1) == "b000001"
    assert MOTIF_ACTEUR.search("_ev60_01560_camera") is None


# ── Cinématiques ─────────────────────────────────────────────────────────────


def test_indexation_des_cinematiques(story: StoryMode) -> None:
    assert len(story.cinematiques) == 2
    cine = story.cinematique("ev60_01560")
    assert cine is not None
    assert cine.chapitre == "ev60"


def test_la_camera_est_rattachee_malgre_labsence_de_plan(story: StoryMode) -> None:
    """Le `.g4cm` ne porte ni acteur ni plan : sans lecture du CHEMIN, il serait perdu."""
    cine = story.cinematique("ev60_01560")
    assert cine is not None
    assert cine.a_camera
    assert len(cine.cameras) == 1


def test_le_decor_est_rattache_malgre_un_nom_sans_cle(story: StoryMode) -> None:
    """`EventMap_fix_c0200.cfg.bin` ne porte PAS la clé — elle vient du dossier."""
    cine = story.cinematique("ev60_01560")
    assert cine is not None
    assert len(cine.decors) == 1
    assert "0200" in cine.plans, "le décor alimente quand même son plan"


def test_plans_et_acteurs(story: StoryMode) -> None:
    cine = story.cinematique("ev60_01560")
    assert cine is not None
    assert sorted(cine.plans) == ["0100", "0200", "0300", "0600"]
    assert cine.acteurs == {"c000401", "c000201", "b000001"}
    assert cine.nb_plans == 4


def test_tri_des_ressources_par_type(story: StoryMode) -> None:
    cine = story.cinematique("ev60_01560")
    assert cine is not None
    assert len(cine.scripts) == 1, "le .mevbin"
    assert len(cine.packs) == 4, "les .g4pk, effets compris"


def test_acteurs_frequents(story: StoryMode) -> None:
    frequents = dict(story.acteurs_frequents(10))
    assert frequents["c000401"] == 1
    assert frequents["c000101"] == 1


def test_cinematiques_par_chapitre(story: StoryMode) -> None:
    assert [c.cle for c in story.cinematiques_du_chapitre("ev61")] == ["ev61_00180"]


# ── Cartes ───────────────────────────────────────────────────────────────────


def test_indexation_des_cartes(story: StoryMode) -> None:
    assert len(story.cartes) == 2
    carte = story.carte("s62g001")
    assert carte is not None
    assert carte.zone == "s"
    assert carte.zone_libelle == ZONES["s"]
    assert carte.a_navmesh
    assert "placement" in carte.config, "le préfixe d'identifiant est retiré du nom court"


def test_les_tables_globales_ne_sont_pas_des_cartes(story: StoryMode) -> None:
    """`data/common/map/map_data_*.cfg.bin` est une table, pas une carte."""
    assert len(story.tables_map) == 2
    assert story.carte("map_data_1.03.91.cfg.bin") is None


def test_cartes_par_zone(story: StoryMode) -> None:
    assert [c.identifiant for c in story.cartes_de("w")] == ["w10i000"]
    assert story.cartes_de("k") == []


def test_carte_sans_navmesh(story: StoryMode) -> None:
    carte = story.carte("w10i000")
    assert carte is not None
    assert not carte.a_navmesh
    assert carte.modeles


# ── Déclencheurs ─────────────────────────────────────────────────────────────


def test_les_deux_moities_dun_trigger_sont_appariees(story: StoryMode) -> None:
    """Table `.cfg.bin` et `.lua.bin` compilé partagent un identifiant."""
    assert len(story.triggers) == 2
    trigger = story.trigger("c01_trigger_0")
    assert trigger is not None
    assert trigger.genre == "phase"
    assert trigger.table is not None and trigger.lua is not None
    assert trigger.exploitable, "la table est décodable, le Lua non"


def test_genre_de_quete(story: StoryMode) -> None:
    quete = story.trigger("qsa000000_trigger_0")
    assert quete is not None
    assert quete.genre == "quest"


# ── Résumé et cache ──────────────────────────────────────────────────────────


def test_resume(story: StoryMode) -> None:
    r = story.resume()
    assert r["cinematiques"] == 2
    assert r["avec_camera"] == 1
    assert r["avec_script"] == 1
    assert r["cartes"] == 2
    assert r["cartes_avec_navmesh"] == 1
    assert r["tables_map"] == 2
    assert r["triggers"] == 2
    assert r["triggers_exploitables"] == 2


def test_cache_aller_retour(story: StoryMode, tmp_path: Path) -> None:
    chemin = story.sauver(tmp_path / "story.json")
    relu = StoryMode.charger(chemin)

    assert relu.resume() == story.resume()
    original = story.cinematique("ev60_01560")
    copie = relu.cinematique("ev60_01560")
    assert original is not None and copie is not None
    assert copie.acteurs == original.acteurs
    assert copie.plans == {k: sorted(v) for k, v in original.plans.items()}


def test_cache_absent_dit_quoi_lancer(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="niepy story"):
        StoryMode.charger(tmp_path / "jamais.json")


# ── Adossé au vrai jeu ───────────────────────────────────────────────────────


def _vfs_reel():  # noqa: ANN202
    from niepy import Vfs

    try:
        return Vfs()
    except (FileNotFoundError, RuntimeError) as erreur:
        pytest.skip(f"jeu absent — {erreur}")


def test_le_jeu_porte_un_mode_histoire_massif() -> None:
    """La structure supposée est-elle celle du jeu installé ?"""
    with _vfs_reel() as vfs:
        story = StoryMode.indexer(vfs)
        r = story.resume()

    assert r["cinematiques"] > 500
    assert r["avec_camera"] > 100, "les .g4cm doivent être rattachés"
    assert r["cartes"] > 100
    assert r["triggers"] > 10
    # Toutes les zones observées doivent être connues de ZONES : une zone inconnue
    # signalerait que le jeu a changé de structure.
    assert set(r["cartes_par_zone"]) <= set(ZONES)
