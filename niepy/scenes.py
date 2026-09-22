"""Les scènes du jeu — ce dont un visual novel a réellement besoin.

Le jeu porte **5 173 scènes** identifiées par une clé `evNN_NNNNN`, et cette clé appaire des
ressources dispersées dans quatre endroits du VFS :

| Ressource | Emplacement | Volume |
|---|---|---|
| Texte des dialogues | `data/common/text/<langue>/event/<clé>.cfg.bin` | 44 241 fichiers |
| Sous-titres | `data/common/gamedata/event/subtitle/<langue>/Subtitle_<clé>.cfg.bin` | ~1 400 |
| Lipsync | `data/common/sound/<langue>/<clé>_*.p3lip` | 21 047 |
| Scripts de scène | `data/common/event/` | 56 450 |

**Le texte existe en neuf langues, le doublage en deux seulement** (`ja`, `en`). Un VN qui
suppose que toute langue jouable est doublée se trompera sur sept langues sur neuf — d'où
`Scene.est_doublee` et `LANGUES_DOUBLEES`.

    from niepy import Scenario, Vfs

    with Vfs() as vfs:
        scenario = Scenario.indexer(vfs)
        scene = scenario.scene("ev01_01700")
        lignes = scenario.lignes(scene, "fr")
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

from .formats import decoder

__all__ = [
    "LANGUES",
    "LANGUES_DOUBLEES",
    "Scenario",
    "Scene",
    "lignes_de",
]

#: Les neuf langues dans lesquelles le texte du jeu existe.
LANGUES: tuple[str, ...] = (
    "ja",
    "en",
    "fr",
    "de",
    "es",
    "it",
    "pt",
    "zh_hans",
    "zh_hant",
)

#: Les seules langues effectivement doublées. Mesuré : 15 788 lipsync `ja`, 5 259 `en`, 0 ailleurs.
LANGUES_DOUBLEES: tuple[str, ...] = ("ja", "en")

#: Clé d'une scène : `ev` + deux chiffres de chapitre + quatre ou cinq chiffres de séquence.
MOTIF_CLE = re.compile(r"(ev\d{2}_\d{4,5})")

_PREFIXE_TEXTE = "data/common/text/"
_PREFIXE_SOUS_TITRE = "data/common/gamedata/event/subtitle/"
_PREFIXE_SON = "data/common/sound/"


@dataclass(slots=True)
class Scene:
    """Une scène du jeu et toutes ses ressources, appairées par sa clé."""

    cle: str
    #: langue → chemin VFS du fichier de texte.
    textes: dict[str, str] = field(default_factory=dict)
    #: langue → chemin VFS du fichier de sous-titres.
    sous_titres: dict[str, str] = field(default_factory=dict)
    #: langue → chemins VFS des `.p3lip`, triés.
    lipsync: dict[str, list[str]] = field(default_factory=dict)

    @property
    def chapitre(self) -> str:
        """Le segment `evNN` — le chapitre auquel la scène appartient."""
        return self.cle.split("_", 1)[0]

    @property
    def langues_texte(self) -> list[str]:
        """Langues dans lesquelles le texte de cette scène existe, dans l'ordre de `LANGUES`."""
        return [lg for lg in LANGUES if lg in self.textes]

    @property
    def est_doublee(self) -> bool:
        """`True` si la scène porte au moins un lipsync — donc au moins une voix."""
        return any(self.lipsync.values())

    def repliques_doublees(self, langue: str) -> int:
        """Nombre de répliques doublées dans une langue (mesuré sur les `.p3lip`)."""
        return len(self.lipsync.get(langue, ()))

    def vers_dict(self) -> dict[str, Any]:
        """Forme sérialisable, pour le cache d'index."""
        return {
            "cle": self.cle,
            "textes": self.textes,
            "sous_titres": self.sous_titres,
            "lipsync": self.lipsync,
        }

    @classmethod
    def depuis_dict(cls, brut: dict[str, Any]) -> "Scene":
        """Reconstruit une scène depuis le cache d'index."""
        return cls(
            cle=str(brut["cle"]),
            textes=dict(brut.get("textes", {})),
            sous_titres=dict(brut.get("sous_titres", {})),
            lipsync={k: list(v) for k, v in (brut.get("lipsync") or {}).items()},
        )


def lignes_de(document: Any) -> list[str]:
    """Extrait les chaînes d'un document `cfg.bin` décodé, dans l'ordre de l'arbre.

    Un `cfg.bin` T2B est un arbre `{name, variables, children}` où les valeurs vivent dans
    `variables`, chacune sous la forme `{"String": …}`, `{"Int": …}` ou `{"Float": …}`. Seules
    les `String` nous intéressent ; les `name` sont des identifiants de structure, pas du
    texte affichable, et les inclure noierait les répliques sous des étiquettes techniques.
    """
    trouvees: list[str] = []

    def descendre(noeud: Any) -> None:
        if isinstance(noeud, dict):
            for variable in noeud.get("variables") or ():
                if isinstance(variable, dict):
                    valeur = variable.get("String")
                    if isinstance(valeur, str) and valeur:
                        trouvees.append(valeur)
            for enfant in noeud.get("children") or ():
                descendre(enfant)
            # `entries` n'existe qu'à la racine, mais le traiter ici rend la fonction
            # utilisable aussi bien sur le document entier que sur un sous-arbre.
            for entree in noeud.get("entries") or ():
                descendre(entree)
        elif isinstance(noeud, list):
            for element in noeud:
                descendre(element)

    descendre(document)
    return trouvees


class Scenario:
    """L'index des scènes du jeu.

    La construction parcourt tout l'index du VFS (255 308 entrées) : c'est l'opération
    coûteuse, à faire une fois. `sauver`/`charger` évitent de la refaire à chaque lancement,
    ce qui compte dans un jeu qui doit démarrer vite.
    """

    def __init__(self, scenes: dict[str, Scene] | None = None) -> None:
        """Construit un scénario, vide par défaut. Voir `indexer` pour le remplir."""
        self.scenes: dict[str, Scene] = scenes or {}

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def indexer(cls, vfs: Any) -> "Scenario":
        """Parcourt le VFS et appaire toutes les ressources par clé de scène."""
        scenes: dict[str, Scene] = {}

        def scene_de(cle: str) -> Scene:
            if cle not in scenes:
                scenes[cle] = Scene(cle=cle)
            return scenes[cle]

        for entree in vfs.parcourir():
            chemin = str(entree.get("path", ""))
            trouve = MOTIF_CLE.search(chemin)
            if not trouve:
                continue
            cle = trouve.group(1)
            morceaux = chemin.split("/")

            if chemin.startswith(_PREFIXE_TEXTE) and "/event/" in chemin and len(morceaux) >= 5:
                langue = morceaux[3]
                # `data/common/text/event/…` n'a pas de segment de langue : ce sont les tables
                # de correspondance, pas du texte affichable. On les écarte.
                if langue in LANGUES:
                    scene_de(cle).textes[langue] = chemin

            elif chemin.startswith(_PREFIXE_SOUS_TITRE) and len(morceaux) >= 6:
                langue = morceaux[5]
                if langue in LANGUES:
                    scene_de(cle).sous_titres[langue] = chemin

            elif chemin.startswith(_PREFIXE_SON) and chemin.endswith(".p3lip") and len(morceaux) >= 5:
                langue = morceaux[3]
                scene_de(cle).lipsync.setdefault(langue, []).append(chemin)

        for scene in scenes.values():
            for pistes in scene.lipsync.values():
                pistes.sort()

        return cls(scenes)

    # ── Cache ────────────────────────────────────────────────────────────────

    def sauver(self, chemin: str | os.PathLike[str]) -> Path:
        """Écrit l'index en JSON, pour éviter de reparcourir le VFS au prochain lancement."""
        cible = Path(chemin)
        cible.parent.mkdir(parents=True, exist_ok=True)
        charge = {
            "version": 1,
            "scenes": [scene.vers_dict() for scene in self.trier()],
        }
        cible.write_text(json.dumps(charge, ensure_ascii=False), encoding="utf-8")
        return cible

    @classmethod
    def charger(cls, chemin: str | os.PathLike[str]) -> "Scenario":
        """Relit un index sauvegardé. Lève `FileNotFoundError` en disant quoi lancer."""
        source = Path(chemin)
        if not source.is_file():
            raise FileNotFoundError(
                f"{source} est absent. Produis-le avec :\n"
                f"    uv run python -m niepy scenes --index {source}"
            )
        charge = json.loads(source.read_text(encoding="utf-8"))
        scenes = {
            str(brut["cle"]): Scene.depuis_dict(brut) for brut in charge.get("scenes", [])
        }
        return cls(scenes)

    # ── Consultation ─────────────────────────────────────────────────────────

    def __len__(self) -> int:
        """Nombre de scènes indexées."""
        return len(self.scenes)

    def __iter__(self) -> Iterator[Scene]:
        return iter(self.trier())

    def __contains__(self, cle: object) -> bool:
        return cle in self.scenes

    def trier(self) -> list[Scene]:
        """Les scènes, dans l'ordre naturel de leur clé — donc l'ordre du scénario."""
        return [self.scenes[cle] for cle in sorted(self.scenes)]

    def scene(self, cle: str) -> Scene | None:
        """Une scène par sa clé exacte."""
        return self.scenes.get(cle)

    def chapitres(self) -> dict[str, int]:
        """Nombre de scènes par chapitre (`ev00`, `ev01`, …), dans l'ordre."""
        compte: dict[str, int] = {}
        for scene in self.trier():
            compte[scene.chapitre] = compte.get(scene.chapitre, 0) + 1
        return compte

    def du_chapitre(self, chapitre: str) -> list[Scene]:
        """Les scènes d'un chapitre, dans l'ordre."""
        return [s for s in self.trier() if s.chapitre == chapitre]

    def doublees(self, langue: str | None = None) -> list[Scene]:
        """Scènes portant au moins une voix, éventuellement dans une langue donnée."""
        if langue is None:
            return [s for s in self.trier() if s.est_doublee]
        return [s for s in self.trier() if s.repliques_doublees(langue)]

    def traduites(self, langue: str) -> list[Scene]:
        """Scènes dont le texte existe dans une langue donnée."""
        return [s for s in self.trier() if langue in s.textes]

    # ── Lecture du contenu ───────────────────────────────────────────────────

    def lignes(self, scene: Scene | str, langue: str, vfs: Any) -> list[str]:
        """Répliques d'une scène dans une langue, dans l'ordre du fichier.

        Rend une liste vide quand la scène n'existe pas dans cette langue — c'est un cas
        courant et normal, pas une erreur : voir `Scene.langues_texte`.
        """
        cible = self.scene(scene) if isinstance(scene, str) else scene
        if cible is None:
            return []
        chemin = cible.textes.get(langue)
        if chemin is None:
            return []
        return lignes_de(decoder(vfs.lire(chemin)))

    def lignes_sous_titres(self, scene: Scene | str, langue: str, vfs: Any) -> list[str]:
        """Sous-titres d'une scène dans une langue, dans l'ordre."""
        cible = self.scene(scene) if isinstance(scene, str) else scene
        if cible is None:
            return []
        chemin = cible.sous_titres.get(langue)
        if chemin is None:
            return []
        return lignes_de(decoder(vfs.lire(chemin)))

    # ── Statistiques ─────────────────────────────────────────────────────────

    def resume(self) -> dict[str, Any]:
        """Chiffres d'ensemble — ce qu'un export doit annoncer avant de démarrer."""
        par_langue = {lg: len(self.traduites(lg)) for lg in LANGUES}
        doublees = {lg: len(self.doublees(lg)) for lg in LANGUES_DOUBLEES}
        return {
            "scenes": len(self),
            "chapitres": len(self.chapitres()),
            "texte_par_langue": {lg: n for lg, n in par_langue.items() if n},
            "doublage_par_langue": doublees,
            "avec_sous_titres": sum(1 for s in self.trier() if s.sous_titres),
        }


def langues_disponibles(scenario: Scenario) -> Sequence[str]:
    """Langues effectivement présentes dans cet index, dans l'ordre de `LANGUES`."""
    presentes = {lg for scene in scenario for lg in scene.textes}
    return [lg for lg in LANGUES if lg in presentes]
