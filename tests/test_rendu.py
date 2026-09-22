"""Le pont vers `nie-game`.

Le rendu réel exige un GPU et l'installation du jeu : ces cas-là sautent en le disant. Ce qui
est testé sans condition, c'est la construction des commandes — la source d'erreur la plus
fréquente d'un pont par sous-processus, et la moins visible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("niepy")

from niepy.rendu import ErreurRendu, Rendu, chemin_nie_game  # noqa: E402


class RenduEspion(Rendu):
    """Un `Rendu` qui n'exécute rien et retient la dernière commande construite."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(binaire=Path("nie-game"), **kwargs)  # type: ignore[arg-type]
        self.commandes: list[list[str]] = []

    def _lancer(self, arguments):  # type: ignore[no-untyped-def]
        commande = [str(self.binaire)]
        if self.racine_jeu is not None:
            commande += ["--game-dir", str(self.racine_jeu)]
        commande += list(arguments)
        self.commandes.append(commande)
        return ""


def test_capturer_construit_la_bonne_commande(tmp_path: Path) -> None:
    espion = RenduEspion()
    cible = tmp_path / "sous" / "dossier" / "menu.png"
    with pytest.raises(ErreurRendu, match="n'a pas été écrit"):
        # Rien n'est exécuté, donc rien n'est écrit : l'erreur attendue prouve que le pont
        # VÉRIFIE la présence du fichier au lieu de croire le code de sortie sur parole.
        espion.capturer("data/common/x.g4tx", cible)

    assert espion.commandes[-1] == [
        "nie-game",
        "--g4tx",
        "data/common/x.g4tx",
        "--capture",
        str(cible),
    ]
    assert cible.parent.is_dir(), "le dossier de sortie est créé"


def test_racine_du_jeu_est_transmise(tmp_path: Path) -> None:
    espion = RenduEspion(racine_jeu=tmp_path)
    espion.lister(5)
    assert espion.commandes[-1][1:3] == ["--game-dir", str(tmp_path)]
    assert espion.commandes[-1][-2:] == ["--list", "5"]


def test_capturer_region(tmp_path: Path) -> None:
    espion = RenduEspion()
    with pytest.raises(ErreurRendu):
        espion.capturer_region("atlas.g4tx", "icone_01", tmp_path / "i.png")
    assert "--g4tx-region" in espion.commandes[-1]
    assert "icone_01" in espion.commandes[-1]


def test_composer_empile_les_layouts(tmp_path: Path) -> None:
    espion = RenduEspion()
    espion.composer(["a.json", "b.json"], tmp_path / "ecran.png")
    commande = espion.commandes[-1]
    assert commande.count("--compose-layout") == 2, "un drapeau par calque"
    assert commande.index("a.json") < commande.index("b.json"), "l'ordre décide du dessin"


def test_composer_refuse_une_liste_vide(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RenduEspion().composer([], tmp_path / "x.png")


def test_binaire_absent_dit_quoi_construire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIE_GAME_BIN", str(Path("nulle-part") / "nie-game.exe"))
    with pytest.raises(FileNotFoundError, match="NIE_GAME_BIN"):
        chemin_nie_game()


def test_binaire_resolu_sur_cette_machine() -> None:
    """Si `nie-game` est construit ici, le pont doit le trouver."""
    try:
        chemin = chemin_nie_game()
    except FileNotFoundError as erreur:
        pytest.skip(f"nie-game non construit — {erreur}")
    assert chemin.is_file()
