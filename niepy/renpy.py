"""Pont entre le catalogue exporté par `nie vn export` et un projet Ren'Py.

Ce module ne dépend **pas** de Ren'Py : il se contente de lire `catalogue.json` et de rendre
des objets Python et des chaînes de script. On peut donc le tester hors moteur, ce qui est le
seul moyen d'attraper une erreur de chemin d'asset avant de lancer le jeu.

Utilisation typique, dans un bloc `init python:` d'un projet Ren'Py :

    from niepy.renpy import Catalogue
    catalogue = Catalogue.charger(config.gamedir + "/nie")

Puis, côté script, les images et les voix sont adressées par les chemins que rend le
catalogue (`portrait_de`, `voix_de`), relatifs au dossier `game/`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

__all__ = ["Catalogue", "Personnage", "Piste", "Replique", "Texture", "Voix"]


def _identifiant_sur(code: str) -> str:
    """Rend un identifiant Python/Ren'Py valide à partir d'un code interne.

    Les codes du jeu (`c01000010`) commencent par une lettre, mais rien ne le garantit pour
    tout le corpus : un identifiant qui commencerait par un chiffre produirait un `.rpy`
    syntaxiquement invalide, et l'erreur ne se verrait qu'au lancement de Ren'Py.
    """
    propre = "".join(c if c.isalnum() or c == "_" else "_" for c in code)
    return propre if propre[:1].isalpha() or propre[:1] == "_" else f"n_{propre}"


@dataclass(frozen=True, slots=True)
class Voix:
    """Une réplique doublée, extraite d'une banque ACB/AWB."""

    cue: str
    fichier: str
    ms: int = 0

    @property
    def secondes(self) -> float:
        """Durée de la réplique, en secondes."""
        return self.ms / 1000.0


@dataclass(frozen=True, slots=True)
class Texture:
    """Une planche d'images ou une feuille d'expressions."""

    fichier: str
    role: str = "planche"
    source: str = ""

    @property
    def expressions(self) -> bool:
        """`True` s'il s'agit d'une feuille de visages (`_face`), pas d'une planche entière."""
        return self.role == "expressions"


@dataclass(frozen=True, slots=True)
class Replique:
    """Une ligne de dialogue relevée dans les données d'évènement du jeu."""

    evenement: str
    #: Identifiant de la réplique, pas un numéro : `ev01_01200_010_010`. C'est la chaîne
    #: que porte la commande `OP_REPLIQUE` du script d'évènement, et par le `crc32` de
    #: laquelle le texte est indexé (voir `relever_dialogues` dans `nie-cli/src/vn_cmd.rs`).
    #: Le typer `int` faisait échouer `Catalogue.charger` sur tout catalogue réel portant
    #: des dialogues — le catalogue synthétique des tests, lui, ne le montrait pas.
    ligne: str
    texte: str


@dataclass(frozen=True, slots=True)
class Piste:
    """Une piste de musique extraite de `bgm.acb`."""

    cue: str
    fichier: str
    ms: int = 0


@dataclass(slots=True)
class Personnage:
    """Un personnage jouable côté visual novel, avec ses assets et ses répliques."""

    code: str
    nom: str | None = None
    genre: str | None = None
    voix: list[Voix] = field(default_factory=list)
    textures: list[Texture] = field(default_factory=list)
    dialogues: list[Replique] = field(default_factory=list)

    @property
    def identifiant(self) -> str:
        """Identifiant Ren'Py stable pour ce personnage (dérivé du code interne)."""
        return _identifiant_sur(self.code)

    @property
    def affichage(self) -> str:
        """Nom à afficher : le nom résolu s'il existe, sinon le code interne."""
        return self.nom or self.code

    @property
    def portrait(self) -> str | None:
        """Chemin de la meilleure image de portrait, ou `None` si le personnage n'en a pas.

        Une feuille d'expressions est préférée à une planche : c'est elle qui porte les
        visages utilisables tels quels dans une scène de dialogue.
        """
        for texture in self.textures:
            if texture.expressions:
                return texture.fichier
        return self.textures[0].fichier if self.textures else None

    def declaration_renpy(self, prefixe: str = "nie") -> str:
        """Rend la ligne `define` qui déclare ce personnage dans Ren'Py."""
        nom = self.affichage.replace('"', '\\"')
        return f'define {prefixe}_{self.identifiant} = Character("{nom}")'


class Catalogue:
    """Le catalogue complet exporté par `nie vn export`."""

    def __init__(self, donnees: dict[str, Any], racine: Path) -> None:
        """Construit le catalogue depuis le JSON déjà chargé et sa racine sur disque."""
        self.racine = racine
        self.version = int(donnees.get("version", 0))
        self.langue = str(donnees.get("langue", ""))
        self.personnages: list[Personnage] = [
            _personnage_depuis(brut) for brut in donnees.get("personnages", [])
        ]
        self.musique: list[Piste] = [
            Piste(cue=str(m.get("cue", "")), fichier=str(m.get("fichier", "")), ms=int(m.get("ms", 0)))
            for m in donnees.get("musique", [])
        ]

    @classmethod
    def charger(cls, dossier: str | os.PathLike[str]) -> "Catalogue":
        """Charge `catalogue.json` depuis le dossier d'export.

        Lève `FileNotFoundError` avec la commande à lancer plutôt qu'une erreur de chemin
        nue : dans un `init python:` de Ren'Py, la trace seule n'aide personne.
        """
        racine = Path(dossier)
        chemin = racine / "catalogue.json"
        if not chemin.is_file():
            raise FileNotFoundError(
                f"{chemin} est absent. Produis-le avec :\n"
                f"    nie vn export --out {racine}"
            )
        with chemin.open("r", encoding="utf-8") as flux:
            return cls(json.load(flux), racine)

    def __len__(self) -> int:
        """Nombre de personnages du catalogue."""
        return len(self.personnages)

    def __iter__(self) -> Iterator[Personnage]:
        return iter(self.personnages)

    def par_code(self, code: str) -> Personnage | None:
        """Retrouve un personnage par son code interne exact."""
        for personnage in self.personnages:
            if personnage.code == code:
                return personnage
        return None

    def par_nom(self, motif: str) -> list[Personnage]:
        """Personnages dont le nom résolu contient `motif`, sans tenir compte de la casse."""
        motif = motif.casefold()
        return [p for p in self.personnages if p.nom and motif in p.nom.casefold()]

    def doubles(self) -> list[Personnage]:
        """Personnages qui ont au moins une réplique doublée."""
        return [p for p in self.personnages if p.voix]

    def portrait_de(self, code: str) -> str | None:
        """Chemin du portrait d'un personnage, ou `None`."""
        personnage = self.par_code(code)
        return personnage.portrait if personnage else None

    def voix_de(self, code: str) -> list[Voix]:
        """Répliques doublées d'un personnage."""
        personnage = self.par_code(code)
        return personnage.voix if personnage else []

    # ── Génération de script ─────────────────────────────────────────────────

    def script_renpy(self, prefixe: str = "nie") -> str:
        """Rend un fichier `.rpy` complet : personnages, images et musique déclarés.

        Le fichier est **régénérable** : il ne contient aucune écriture à la main, et peut
        donc être réécrit à chaque export sans rien perdre.
        """
        lignes: list[str] = [
            "# Généré par niepy — NE PAS ÉDITER À LA MAIN.",
            "# Régénérer avec : uv run python -m niepy renpy --out <dossier>",
            f"# Catalogue version {self.version}, langue « {self.langue} ».",
            "",
        ]

        lignes.append("# ── Personnages ──────────────────────────────────────────────")
        for personnage in self.personnages:
            lignes.append(personnage.declaration_renpy(prefixe))
        lignes.append("")

        lignes.append("# ── Portraits ────────────────────────────────────────────────")
        for personnage in self.personnages:
            portrait = personnage.portrait
            if portrait:
                lignes.append(
                    f'image {prefixe} {personnage.identifiant} = "{_pose(self.racine, portrait)}"'
                )
        lignes.append("")

        lignes.append("# ── Musique ──────────────────────────────────────────────────")
        for piste in self.musique:
            nom = _identifiant_sur(piste.cue or Path(piste.fichier).stem)
            lignes.append(
                f'define {prefixe}_bgm_{nom} = "{_pose(self.racine, piste.fichier)}"'
            )
        lignes.append("")

        return "\n".join(lignes)

    def ecrire_script(self, destination: str | os.PathLike[str], prefixe: str = "nie") -> Path:
        """Écrit le `.rpy` généré et rend son chemin."""
        chemin = Path(destination)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(self.script_renpy(prefixe), encoding="utf-8")
        return chemin


def _pose(racine: Path, relatif: str) -> str:
    """Rend un chemin d'asset tel que Ren'Py l'attend : relatif à `game/`, en séparateurs `/`.

    Sur Windows, un chemin construit avec `os.path.join` porte des antislashes, que Ren'Py
    ne résout pas. La conversion est donc faite ici une fois pour toutes.
    """
    return f"{racine.name}/{relatif}".replace("\\", "/")


def _personnage_depuis(brut: dict[str, Any]) -> Personnage:
    """Construit un `Personnage` depuis une entrée brute du catalogue."""
    return Personnage(
        code=str(brut.get("code", "")),
        nom=brut.get("nom"),
        genre=brut.get("genre"),
        voix=[
            Voix(cue=str(v.get("cue", "")), fichier=str(v.get("fichier", "")), ms=int(v.get("ms", 0)))
            for v in brut.get("voix", []) or []
        ],
        textures=[
            Texture(
                fichier=str(t.get("fichier", "")),
                role=str(t.get("role", "planche")),
                source=str(t.get("source", "")),
            )
            for t in brut.get("textures", []) or []
        ],
        dialogues=[
            Replique(
                evenement=str(d.get("evenement", "")),
                ligne=str(d.get("ligne", "")),
                texte=str(d.get("texte", "")),
            )
            for d in brut.get("dialogues", []) or []
        ],
    )
