"""Pont vers `nie-game` — le rendu des vrais assets, en PNG utilisables par Ren'Py.

`nie-game` est atteint en **sous-processus**, jamais en process, et c'est délibéré : il n'a
pas de `lib.rs`, c'est un hôte wgpu. Charger un contexte GPU dans une bibliothèque elle-même
chargée par le Python de Ren'Py est une bonne façon d'obtenir des plantages illisibles. Le
dépôt applique déjà cette règle à la CLI Rust `nie`, pour la même raison.

Le pont n'expose donc que les modes **hors-écran**, qui rendent un fichier et se terminent.
Les modes fenêtrés (`--window`, `--play`) ouvrent une fenêtre et rendent la main quand
l'utilisateur la ferme : les appeler depuis un jeu déjà lancé bloquerait ce jeu.

    from niepy.rendu import Rendu

    r = Rendu()
    r.capturer("data/common/…/menu.g4tx", "game/nie/images/menu.png")
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from ._ffi import _racine_depot

__all__ = ["ErreurRendu", "Rendu", "chemin_nie_game"]

#: Délai au-delà duquel un rendu est considéré perdu (secondes).
#:
#: Un rendu hors-écran prend quelques secondes ; au-delà, c'est que le processus attend
#: quelque chose qui ne viendra pas (pilote GPU, fenêtre). Mieux vaut échouer que pendre.
DELAI_DEFAUT = 180.0


class ErreurRendu(RuntimeError):
    """`nie-game` a échoué. Porte son code de sortie et sa sortie d'erreur."""

    def __init__(self, code: int, sortie: str, commande: Sequence[str]) -> None:
        self.code = code
        self.sortie = sortie
        self.commande = list(commande)
        super().__init__(
            f"nie-game a échoué (code {code}) : {' '.join(self.commande)}\n{sortie.strip()}"
        )


def chemin_nie_game() -> Path:
    """Résout le binaire `nie-game`, ou dit comment le construire.

    Ordre : `NIE_GAME_BIN`, puis `target/release`, puis `target/debug`. Le `release` est
    préféré : le rendu hors-écran y est nettement plus rapide.
    """
    force = os.environ.get("NIE_GAME_BIN", "").strip()
    if force:
        chemin = Path(force)
        if not chemin.is_file():
            raise FileNotFoundError(f"NIE_GAME_BIN pointe vers {chemin}, qui n'est pas un fichier.")
        return chemin

    nom = "nie-game.exe" if sys.platform == "win32" else "nie-game"
    racine = _racine_depot()
    candidats = (
        [racine / "target" / profil / nom for profil in ("release", "debug")] if racine else []
    )
    for candidat in candidats:
        if candidat.is_file():
            return candidat

    cherches = "\n  ".join(str(c) for c in candidats) or "  (racine du dépôt introuvable)"
    raise FileNotFoundError(
        "Binaire nie-game introuvable. Construis-le avec :\n"
        "    cargo build -p nie-game --release\n"
        "Chemins essayés :\n  " + cherches
    )


class Rendu:
    """Appelle `nie-game` en sous-processus pour produire des images."""

    def __init__(
        self,
        binaire: str | os.PathLike[str] | None = None,
        racine_jeu: str | os.PathLike[str] | None = None,
        delai: float = DELAI_DEFAUT,
    ) -> None:
        """Prépare le pont. `racine_jeu` est passée en `--game-dir` si elle est fournie."""
        self.binaire = Path(binaire) if binaire else chemin_nie_game()
        self.racine_jeu = Path(racine_jeu) if racine_jeu else None
        self.delai = delai

    def _lancer(self, arguments: Sequence[str]) -> str:
        """Lance `nie-game` et rend sa sortie standard. Lève `ErreurRendu` en cas d'échec."""
        commande = [str(self.binaire)]
        if self.racine_jeu is not None:
            commande += ["--game-dir", str(self.racine_jeu)]
        commande += list(arguments)

        try:
            fini = subprocess.run(
                commande,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.delai,
                check=False,
            )
        except subprocess.TimeoutExpired as expire:
            raise ErreurRendu(-1, f"délai de {self.delai}s dépassé", commande) from expire

        if fini.returncode != 0:
            raise ErreurRendu(fini.returncode, fini.stderr or fini.stdout, commande)
        return fini.stdout

    # ── Rendu ────────────────────────────────────────────────────────────────

    def capturer(self, g4tx: str, sortie: str | os.PathLike[str]) -> Path:
        """Rend une texture `.g4tx` du VFS en PNG hors-écran, et rend son chemin."""
        cible = Path(sortie)
        cible.parent.mkdir(parents=True, exist_ok=True)
        self._lancer(["--g4tx", g4tx, "--capture", str(cible)])
        if not cible.is_file():
            raise ErreurRendu(0, f"{cible} n'a pas été écrit", [str(self.binaire)])
        return cible

    def capturer_region(
        self, g4tx: str, region: str, sortie: str | os.PathLike[str]
    ) -> Path:
        """Rogne une région d'atlas nommée et écrit ses pixels réels en PNG.

        C'est ce qui produit un sprite exact (une icône, un visage) plutôt que la planche
        entière — la forme utile dans un visual novel.
        """
        cible = Path(sortie)
        cible.parent.mkdir(parents=True, exist_ok=True)
        self._lancer(["--g4tx", g4tx, "--g4tx-region", region, "--capture", str(cible)])
        if not cible.is_file():
            raise ErreurRendu(0, f"{cible} n'a pas été écrit", [str(self.binaire)])
        return cible

    def composer(
        self, layouts: Sequence[str | os.PathLike[str]], sortie: str | os.PathLike[str]
    ) -> Path:
        """Compose un ou plusieurs layouts JSON en une image unique.

        Un écran du jeu empile plusieurs calques ; l'ordre des layouts décide à priorité
        de dessin égale.
        """
        if not layouts:
            raise ValueError("au moins un layout est requis")
        cible = Path(sortie)
        cible.parent.mkdir(parents=True, exist_ok=True)
        arguments: list[str] = []
        for layout in layouts:
            arguments += ["--compose-layout", str(layout)]
        arguments += ["--capture", str(cible)]
        self._lancer(arguments)
        return cible

    # ── Découverte ───────────────────────────────────────────────────────────

    def lister(self, combien: int = 20) -> str:
        """Liste les premières textures `.g4tx` du VFS, avec leurs dimensions."""
        return self._lancer(["--list", str(combien)])

    def regions(self, g4tx: str) -> str:
        """Liste les régions d'atlas d'une texture (nom + rectangle)."""
        return self._lancer(["--g4tx", g4tx, "--g4tx-regions"])

    def index_regions(self, sortie: str | os.PathLike[str]) -> dict[str, Any]:
        """Construit l'index `nom-de-région → chemin g4tx` et rend son contenu."""
        cible = Path(sortie)
        cible.parent.mkdir(parents=True, exist_ok=True)
        self._lancer(["--build-region-index", str(cible)])
        with cible.open("r", encoding="utf-8") as flux:
            resultat: dict[str, Any] = json.load(flux)
            return resultat
