"""Le moteur de match, vu depuis Python.

Ces tests ne touchent **pas** au VFS : ils tournent sans les données du jeu, et prouvent que
la frontière FFI transporte correctement l'état de la simulation.
"""

from __future__ import annotations

import pytest

niepy = pytest.importorskip("niepy")

from niepy import Match  # noqa: E402
from niepy._ffi import chemin_bibliotheque  # noqa: E402


def test_bibliotheque_resolue() -> None:
    """La lib native est trouvée — sinon tout le reste échouerait sans dire pourquoi."""
    assert chemin_bibliotheque().is_file()


def test_coup_denvoi_pose_22_joueurs_et_un_ballon() -> None:
    with Match() as m:
        assert len(m) == 22, "11 v 11"
        assert m.score == (0, 0)
        assert m.tick == 0

        # Un gardien par camp, exactement.
        gardiens = [j for j in m.joueurs() if j.role == "GK"]
        assert len(gardiens) == 2
        assert {g.team for g in gardiens} == {0, 1}

        # Le ballon commence au centre, au sol.
        ballon = m.ballon
        assert ballon.x == pytest.approx(0.0, abs=1e-3)
        assert ballon.y == pytest.approx(0.0, abs=1e-3)


def test_le_temps_avance_avec_les_ticks() -> None:
    with Match() as m:
        m.avancer(1.0)
        assert m.tick == 60, "60 Hz par défaut"
        assert m.temps == pytest.approx(1.0, abs=1e-3)


def test_la_simulation_est_deterministe() -> None:
    """Deux matchs menés identiquement donnent le même état — le contrat du moteur.

    C'est ce qui permet à un visual novel de rejouer une action à l'identique.
    """
    instantanes = []
    for _ in range(2):
        with Match() as m:
            m.avancer(5.0)
            instantanes.append(m.instantane())

    assert instantanes[0] == instantanes[1]


def test_instantane_et_accesseurs_concordent() -> None:
    """Le JSON d'instantané et les accesseurs champ à champ décrivent le même monde."""
    with Match() as m:
        m.avancer(2.0)
        snap = m.instantane()

        assert snap["tick"] == m.tick
        assert tuple(snap["score"]) == m.score
        assert len(snap["players"]) == len(m)
        assert snap["ball"]["x"] == pytest.approx(m.ballon.x, abs=1e-5)

        premier = m.joueur(0)
        assert snap["players"][0]["team"] == premier.team
        assert snap["players"][0]["role"] == premier.role


def test_les_joueurs_bougent() -> None:
    """Après quelques secondes, le monde n'est plus dans sa position de départ."""
    with Match() as m:
        depart = [(j.x, j.y) for j in m.joueurs()]
        m.avancer(3.0)
        arrivee = [(j.x, j.y) for j in m.joueurs()]

    assert depart != arrivee, "la simulation doit faire quelque chose"


def test_commander_accepte_une_direction() -> None:
    """Poser une entrée ne casse pas la simulation et reste sans effet sur le compteur."""
    with Match() as m:
        m.commander(dx=1.0, dy=0.0, tirer=False)
        m.avancer(0.5)
        assert m.tick == 30


def test_coup_denvoi_remet_le_monde_a_zero() -> None:
    with Match() as m:
        m.avancer(10.0)
        assert m.tick > 0
        m.coup_denvoi()
        assert m.tick == 0
        assert m.temps == pytest.approx(0.0, abs=1e-6)


def test_indice_de_joueur_hors_bornes() -> None:
    with Match() as m:
        with pytest.raises(IndexError):
            m.joueur(999)


def test_un_match_termine_refuse_de_servir() -> None:
    """Utiliser un handle libéré lève une erreur claire, au lieu de déréférencer un pointeur mort."""
    m = Match()
    m.terminer()
    m.terminer()  # idempotent
    with pytest.raises(RuntimeError):
        _ = m.tick


def test_avancer_refuse_un_pas_nul() -> None:
    with Match() as m:
        with pytest.raises(ValueError):
            m.avancer(1.0, dt=0.0)


# ── La simulation à graine ───────────────────────────────────────────────────
#
# `Match` fait tourner un match jouable mais n'accepte aucune graine, et son onze
# est le sien. `simuler_match` tranche une rencontre à partir des statistiques et
# d'une graine : c'est ce qu'un récit demande pour un match hors écran.


def test_la_graine_rejoue_le_meme_match() -> None:
    stats = dict.fromkeys(niepy.STATS, 150)
    premier = niepy.simuler_match(("A", stats), ("B", stats), graine=42)
    second = niepy.simuler_match(("A", stats), ("B", stats), graine=42)
    assert premier == second
    assert premier["final_clock"] == 900_000  # 90 minutes


def test_des_graines_differentes_donnent_des_matchs_differents() -> None:
    stats = dict.fromkeys(niepy.STATS, 150)
    scores = {
        (r["home_score"], r["away_score"])
        for r in (niepy.simuler_match(("A", stats), ("B", stats), graine=g) for g in range(20))
    }
    assert len(scores) > 1, "la graine ne change rien — la variété ne peut pas venir du moteur"


def test_la_force_des_effectifs_decide() -> None:
    """Le différentiel doit suivre l'écart de statistiques, pas le hasard seul."""
    fort = dict(zip(niepy.STATS, (207, 216, 218, 235, 242, 210, 261)))
    faible = dict.fromkeys(niepy.STATS, 80)

    def differentiel(a: dict[str, int], b: dict[str, int]) -> float:
        matchs = [niepy.simuler_match(("A", a), ("B", b), graine=g) for g in range(40)]
        return sum(m["home_score"] - m["away_score"] for m in matchs) / len(matchs)

    assert differentiel(fort, faible) > differentiel(fort, fort)
    assert differentiel(fort, faible) > 0.5


def test_les_buts_sont_datables() -> None:
    """Un récit but par but a besoin de la minute et du camp."""
    fort = dict(zip(niepy.STATS, (207, 216, 218, 235, 242, 210, 261)))
    for graine in range(30):
        issue = niepy.simuler_match(("A", fort), ("B", fort), graine=graine)
        buts = [e["Goal"] for e in issue["events"] if isinstance(e, dict) and "Goal" in e]
        if not buts:
            continue
        assert len(buts) == issue["home_score"] + issue["away_score"]
        for but in buts:
            assert 1 <= but["minute"] <= 90
            assert isinstance(but["is_home"], bool)
        return
    pytest.fail("aucun but sur trente graines — le modèle ne marque jamais")


def test_une_entree_invalide_leve_plutot_que_de_mentir() -> None:
    with pytest.raises(ValueError, match="simulation refusée"):
        niepy.simuler_match({"name": "sans stats"}, ("B", dict.fromkeys(niepy.STATS, 100)))
