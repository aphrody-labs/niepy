"""Le pont Ren'Py, testé hors moteur.

Ren'Py ne se lance pas dans une suite de tests. Ces cas vérifient donc ce qui casse en
pratique : les chemins d'assets et la validité syntaxique du `.rpy` généré.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("niepy")

from niepy.renpy import Catalogue  # noqa: E402

# Catalogue minimal, de forme identique à celui qu'écrit `nie vn export`.
CATALOGUE = {
    "version": 1,
    "langue": "fr",
    "personnages": [
        {
            "code": "c01000010",
            "nom": "Personnage A",
            "genre": "m",
            "voix": [{"cue": "v001", "fichier": "voix/c01000010/v001.wav", "ms": 1500}],
            "textures": [
                {"source": "…/planche.g4tx", "fichier": "images/c01000010/planche.png", "role": "planche"},
                {"source": "…/_face/x.g4tx", "fichier": "images/c01000010/face.png", "role": "expressions"},
            ],
            # `ligne` est un IDENTIFIANT, pas un numéro : c'est la forme que produit
            # réellement `nie vn export`. Un entier ici — ce qu'il y avait — laissait
            # passer un `int()` qui casse sur tout catalogue réel.
            "dialogues": [
                {"evenement": "ev01_01200", "ligne": "ev01_01200_010_010", "texte": "…"}
            ],
        },
        {"code": "c02000020", "nom": None, "genre": None, "voix": [], "textures": [], "dialogues": []},
    ],
    "musique": [{"cue": "bgm_01", "fichier": "musique/bgm_01.wav", "ms": 60000}],
}


@pytest.fixture()
def catalogue(tmp_path: Path) -> Catalogue:
    dossier = tmp_path / "nie"
    dossier.mkdir()
    (dossier / "catalogue.json").write_text(json.dumps(CATALOGUE), encoding="utf-8")
    return Catalogue.charger(dossier)


def test_chargement(catalogue: Catalogue) -> None:
    assert catalogue.version == 1
    assert catalogue.langue == "fr"
    assert len(catalogue) == 2


def test_identifiant_de_replique_reste_une_chaine(catalogue: Catalogue) -> None:
    """`ligne` porte `ev01_01200_010_010`, jamais un numéro.

    Régression : le champ était converti en `int`, ce qui faisait échouer le chargement
    de tout catalogue réel comportant des dialogues — la forme du producteur est une
    chaîne (`relever_dialogues`, `nie-cli/src/vn_cmd.rs`).
    """
    replique = catalogue.par_code("c01000010").dialogues[0]
    assert replique.ligne == "ev01_01200_010_010"
    assert replique.evenement == "ev01_01200"


def test_catalogue_absent_dit_quoi_lancer(tmp_path: Path) -> None:
    """L'erreur porte la commande à lancer — une trace nue n'aide personne dans un init python."""
    with pytest.raises(FileNotFoundError, match="nie vn export"):
        Catalogue.charger(tmp_path / "vide")


def test_recherche(catalogue: Catalogue) -> None:
    assert catalogue.par_code("c01000010") is not None
    assert catalogue.par_code("inexistant") is None
    assert len(catalogue.par_nom("personnage")) == 1, "recherche insensible à la casse"
    assert len(catalogue.doubles()) == 1


def test_portrait_prefere_les_expressions(catalogue: Catalogue) -> None:
    """Une feuille de visages est plus utile qu'une planche entière dans une scène de dialogue."""
    assert catalogue.portrait_de("c01000010") == "images/c01000010/face.png"


def test_personnage_sans_asset(catalogue: Catalogue) -> None:
    muet = catalogue.par_code("c02000020")
    assert muet is not None
    assert muet.portrait is None
    assert muet.affichage == "c02000020", "sans nom résolu, on affiche le code"


def test_script_genere_est_du_python_valide(catalogue: Catalogue) -> None:
    """Le `.rpy` généré doit au moins être syntaxiquement valide côté déclarations.

    Les lignes `define …` sont du Python ; `image …` est propre à Ren'Py. On compile donc
    les premières, ce qui attrape la faute la plus courante : un nom mal échappé.
    """
    script = catalogue.script_renpy()
    definitions = [
        ligne.removeprefix("define ")
        for ligne in script.splitlines()
        if ligne.startswith("define ") and "Character(" in ligne
    ]
    assert definitions, "au moins un personnage déclaré"
    for definition in definitions:
        nom, _, expression = definition.partition(" = ")
        assert nom.isidentifier(), f"identifiant Ren'Py invalide : {nom}"
        compile(expression, "<test>", "eval")


def test_chemins_dassets_en_slash(catalogue: Catalogue) -> None:
    """Ren'Py ne résout pas les antislashes de Windows."""
    script = catalogue.script_renpy()
    for ligne in script.splitlines():
        if ligne.startswith(("image ", "define nie_bgm_")):
            assert "\\" not in ligne, f"antislash dans un chemin d'asset : {ligne}"


def test_ecriture_du_script(catalogue: Catalogue, tmp_path: Path) -> None:
    cible = tmp_path / "game" / "nie_catalogue.rpy"
    ecrit = catalogue.ecrire_script(cible)
    assert ecrit.is_file()
    contenu = ecrit.read_text(encoding="utf-8")
    assert "NE PAS ÉDITER" in contenu, "le fichier est régénérable, il doit le dire"
    assert "nie_bgm_bgm_01" in contenu
