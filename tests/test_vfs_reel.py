"""Tests adossés au VRAI jeu — sautés, bruyamment, quand les données sont absentes.

Un test qui se saute en silence est un faux vert : la raison du saut est donc toujours dite.
"""

from __future__ import annotations

import pytest

pytest.importorskip("niepy")

from niepy import Vfs, decoder, detecter, nom_format, racine_jeu  # noqa: E402
from niepy.__main__ import FAMILLES  # noqa: E402


def _vfs_ou_saut() -> Vfs:
    """Monte le VFS, ou saute le test en disant pourquoi."""
    try:
        return Vfs()
    except FileNotFoundError as erreur:
        pytest.skip(f"jeu absent de cette machine — {erreur}")
    except RuntimeError as erreur:
        pytest.skip(f"VFS non montable — {erreur}")


def test_racine_du_jeu_resolue() -> None:
    try:
        racine = racine_jeu()
    except FileNotFoundError as erreur:
        pytest.skip(f"jeu absent — {erreur}")
    assert racine.is_dir()


def test_index_non_vide() -> None:
    with _vfs_ou_saut() as vfs:
        assert len(vfs) > 100_000, "l'index complet compte des centaines de milliers d'entrées"


def test_tranches_de_lindex() -> None:
    """`entrees` rend bien une tranche, et deux tranches consécutives ne se recouvrent pas."""
    with _vfs_ou_saut() as vfs:
        premiere = vfs.entrees(0, 10)
        seconde = vfs.entrees(10, 10)
        assert len(premiere) == 10
        assert len(seconde) == 10
        assert {e["path"] for e in premiere}.isdisjoint({e["path"] for e in seconde})
        assert all({"path", "size"} <= set(e) for e in premiere)


def test_chaque_famille_exportable_existe() -> None:
    """Chaque dossier déclaré dans `FAMILLES` porte au moins un `.cfg.bin` dans ce jeu.

    C'est le test qui attrape un chemin VFS inventé : les noms de fichiers du jeu portent un
    numéro de version (`chara_base_1.03.98.00.cfg.bin`), donc seul le DOSSIER est stable.
    """
    with _vfs_ou_saut() as vfs:
        prefixes = {famille: 0 for famille in FAMILLES}
        for entree in vfs.parcourir():
            chemin = entree.get("path", "")
            if not chemin.endswith(".cfg.bin"):
                continue
            for famille, prefixe in FAMILLES.items():
                if chemin.startswith(prefixe):
                    prefixes[famille] += 1

    vides = [famille for famille, n in prefixes.items() if n == 0]
    assert not vides, f"famille(s) sans aucun fichier : {vides} (chemin VFS faux ?)"


def test_lecture_et_decodage_dun_cfgbin() -> None:
    """Un `.cfg.bin` du jeu se lit et se décode en structure Python."""
    with _vfs_ou_saut() as vfs:
        chemin = None
        for entree in vfs.parcourir():
            candidat = entree.get("path", "")
            if candidat.startswith(FAMILLES["objets"]) and candidat.endswith(".cfg.bin"):
                chemin = candidat
                break
        if chemin is None:
            pytest.skip("aucun cfg.bin d'objets dans cette installation")

        brut = vfs.lire(chemin)
        assert brut, "fichier non vide"
        assert nom_format(detecter(brut)) != "inconnu", "format reconnu"

        decode = decoder(brut)
        assert isinstance(decode, (dict, list)), "le décodage rend une structure"


def test_fichier_absent_leve_proprement() -> None:
    with _vfs_ou_saut() as vfs:
        with pytest.raises(FileNotFoundError):
            vfs.lire("data/ceci/n/existe/pas.cfg.bin")


# ── Cache de paquets CPK ─────────────────────────────────────────────────────


def test_le_cache_est_mesurable_reglable_et_videable() -> None:
    """Un hôte qui embarque niepy doit pouvoir voir et borner ce que le VFS retient.

    Le défaut de la bibliothèque native est de 16 Gio : dimensionné pour un traitement par
    lots, pas pour un jeu. Sans ces trois méthodes, un projet Ren'Py ne pourrait que le subir.
    """
    with _vfs_ou_saut() as vfs:
        depart = vfs.stats_cache()
        assert set(depart) == {"octets", "entrees", "budget"}
        assert depart["budget"] > 0

        chemin = None
        for entree in vfs.parcourir():
            candidat = entree.get("path", "")
            if candidat.endswith(".cfg.bin"):
                chemin = candidat
                break
        if chemin is None:
            pytest.skip("aucun .cfg.bin dans cette installation")

        vfs.lire(chemin)
        apres = vfs.stats_cache()
        assert apres["octets"] > 0, "la lecture a chargé un paquet en cache"

        # Abaisser le budget évince tout de suite, mais garde toujours un paquet : évincer
        # celui qu'on vient de demander ferait relire le disque en boucle.
        vfs.regler_budget_cache(1)
        serre = vfs.stats_cache()
        assert serre["budget"] == 1
        assert serre["entrees"] >= 1

        libere = vfs.vider_cache()
        assert libere == serre["octets"]
        assert vfs.stats_cache()["octets"] == 0

        vfs.lire(chemin)
        assert vfs.stats_cache()["octets"] > 0, "le cache se remplit de nouveau"


def test_budget_negatif_refuse() -> None:
    with _vfs_ou_saut() as vfs:
        with pytest.raises(ValueError):
            vfs.regler_budget_cache(-1)


# ── Les trois formats du mode histoire ───────────────────────────────────────


def test_camera_navmesh_et_lua_se_decodent() -> None:
    """G4CM, G4NV et le bytecode Lua remontent par le dispatch partagé.

    Ces trois-là ne rendaient qu'un en-tête auparavant. Ils passent par `nie_decode_json`,
    donc `decoder()` les sert sans que `niepy` ait une ligne de code par format — c'est tout
    l'intérêt d'une table de dispatch unique.
    """
    cibles = {
        "g4cm": ("data/common/event/ev60/ev60_01930/ev60_01930_camera.g4cm", "channels"),
        "g4nv": ("data/common/map/s/s27g001b/s27g001b.g4nv", "vertices"),
        "lua": ("data/common/gamedata/phase/phase_set_c21_0.00.00.lua.bin", "main"),
    }
    with _vfs_ou_saut() as vfs:
        vus = 0
        for etiquette, (chemin, cle_attendue) in cibles.items():
            try:
                brut = vfs.lire(chemin)
            except FileNotFoundError:
                continue
            decode = decoder(brut)
            assert isinstance(decode, dict), f"{etiquette} : structure attendue"
            assert cle_attendue in decode, f"{etiquette} : « {cle_attendue} » manquant"
            vus += 1
        if vus == 0:
            pytest.skip("aucun des trois fichiers de référence dans cette installation")


# ── Le handle natif ne doit ni voyager ni se dupliquer ───────────────────────
#
# Ces trois tests couvrent un défaut mesuré, pas une précaution théorique :
# `pickle.dumps(vfs)` rendait 183 octets EN SILENCE, pointeur natif compris, et
# rechargé dans un autre processus le premier `.lire()` faisait avorter le
# processus (exit 127). Un moteur de jeu qui sauvegarde son store — Ren'Py, par
# exemple — tombe dessus tout seul.


def test_le_vfs_refuse_de_se_serialiser() -> None:
    """Sérialiser un montage doit lever ICI, pas planter le processus qui recharge."""
    import pickle

    with _vfs_ou_saut() as vfs:
        with pytest.raises(TypeError, match="pointeur natif"):
            pickle.dumps(vfs)


def test_la_copie_profonde_ne_duplique_pas_le_handle() -> None:
    """Deux objets portant le même pointeur le libéreraient deux fois."""
    import copy

    with _vfs_ou_saut() as vfs:
        assert copy.deepcopy(vfs) is vfs
        assert copy.copy(vfs) is vfs


def test_le_budget_de_cache_borne_vraiment_la_memoire() -> None:
    """Le défaut natif est de 16 Gio : sans plafond, quelques lectures retiennent des gigaoctets."""
    with _vfs_ou_saut() as vfs:
        textures = [e["path"] for e in vfs.entrees(0, 20000) if str(e["path"]).endswith(".g4tx")][:40]
        if len(textures) < 10:
            pytest.skip("pas assez de textures dans la première tranche de l'index")

        for chemin in textures:
            vfs.lire(str(chemin))
        sans_plafond = vfs.stats_cache()["octets"]

        vfs.vider_cache()
        vfs.regler_budget_cache(64 * 1024 * 1024)
        for chemin in textures:
            vfs.lire(str(chemin))
        avec_plafond = vfs.stats_cache()

        assert avec_plafond["budget"] == 64 * 1024 * 1024
        # Le plafond garde toujours le dernier paquet, qui peut à lui seul le dépasser :
        # on n'exige donc pas de descendre SOUS le budget, seulement de ne plus croître.
        assert avec_plafond["entrees"] <= 2
        assert avec_plafond["octets"] <= max(sans_plafond, 1)


def test_existe_ne_lit_pas_le_contenu() -> None:
    """La présence doit se trancher sans remplir le cache de paquets.

    C'est la raison d'être de `nie_vfs_is_readable` : tester la présence en
    appelant `lire()` dans un `try` extrait le CPK entier — mesuré à 4,9 Go
    retenus pour soixante vérifications de textures dispersées.
    """
    with _vfs_ou_saut() as vfs:
        chemins = [str(e["path"]) for e in vfs.entrees(0, 500)]
        if not chemins:
            pytest.skip("index vide")

        vfs.vider_cache()
        avant = vfs.stats_cache()["octets"]

        for chemin in chemins:
            assert vfs.existe(chemin), f"{chemin} est dans l'index mais dit absent"
            assert chemin in vfs

        assert vfs.stats_cache()["octets"] == avant, (
            "tester la présence a chargé des paquets — le test n'est pas gratuit"
        )

        assert not vfs.existe("data/ceci/nexiste/pas.g4tx")
        assert "data/ceci/nexiste/pas.g4tx" not in vfs
        assert 42 not in vfs  # type: ignore[operator]
