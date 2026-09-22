"""Le mode histoire : cinématiques, cartes et progression.

Trois systèmes, indexés depuis le VFS et rendus exploitables par un jeu tiers.

**Cinématiques** — `data/common/event/<evNN>/<clé>/` porte 56 448 fichiers. Le liant n'est
pas l'acteur ni la prise, mais le **plan** : le suffixe `_cNNNN` est le seul élément
quasi universel du nommage. Mesuré sur le corpus complet, la forme
`<clé>_<acteur>_sNN_pNN_cNNNN` ne couvre que **52,4 %** des noms ; le reste se répartit en
`_camera` (1 214), `_point_sNN_cNNNN`, `_point_eff_cNNNN`, `EventMap_fix_cNNNN` et
`chr<id>_cNNNN`. Un parseur qui n'accepterait que la première forme perdrait la moitié du
corpus, dont **toutes** les caméras.

Deuxième irrégularité, celle-là dans l'arborescence : sous `data/common/event/<evNN>/`, le
dossier suivant n'est pas toujours une clé de scène — c'est parfois un identifiant d'acteur
(`c000301`, `c11010020`). Ces dossiers-là ne sont pas des cinématiques et sont ignorés, d'où
la lecture de la clé dans le CHEMIN et non dans le nom de fichier.

Les scripts `.mevbin` sont **rares dans les cinématiques** : sur les 328 que porte le jeu,
213 sont attachés aux personnages (`data/common/chr/`), 20 aux effets, et les 95 restants se
concentrent presque tous sur une seule scène. Une cinématique sans script est donc la norme,
pas une anomalie d'indexation.

**Cartes** — `data/common/map/<zone>/<id>/` sur neuf zones, plus neuf tables globales
(`map_data`, `map_minimap`, `map_light_set`…). Chaque carte porte ses modèles, parfois un
navmesh `.g4nv`, et des fichiers de `config/` (placement, points de fonction, tags).

**Progression** — `gamedata/phase/` (déclencheurs de chapitre) et `gamedata/quest/`, chacun
en deux moitiés : une table `.cfg.bin` lisible et un `.lua.bin` compilé qui, lui, ne l'est
pas. Ce module indexe les deux et dit lequel est exploitable.

    from niepy import StoryMode, Vfs

    with Vfs() as vfs:
        story = StoryMode.indexer(vfs)
        cine = story.cinematique("ev60_01560")
        print(cine.plans, cine.acteurs)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

__all__ = [
    "Carte",
    "Cinematique",
    "MOTIF_ACTEUR",
    "MOTIF_PLAN",
    "StoryMode",
    "Trigger",
    "ZONES",
]

#: Le numéro de plan (« cut ») : le seul invariant du nommage des fichiers d'événement.
MOTIF_PLAN = re.compile(r"_c(\d{4})(?:_|$)")

#: Un acteur : `c000401` (personnage), `b000001` (ballon/objet), `i000001` (item)…
#: 479 identifiants distincts sur le corpus, dominés par les quatre protagonistes.
MOTIF_ACTEUR = re.compile(r"_((?:c|b|i)\d{6,})(?:_|$)")

#: Clé de scène, identique à celle de `niepy.scenes`.
MOTIF_CLE = re.compile(r"(ev\d{2}_\d{4,5})")

#: Les neuf zones de carte, avec leur volume mesuré.
ZONES: dict[str, str] = {
    "s": "stades et terrains",
    "w": "monde / villes",
    "ar": "arènes",
    "_light": "données d'éclairage",
    "k": "intérieurs",
    "b": "bâtiments",
    "e": "évènementiel",
    "sky": "ciels",
    "gi": "éclairage global",
}

_PREFIXE_EVENT = "data/common/event/"
_PREFIXE_MAP = "data/common/map/"
_PREFIXE_PHASE = "data/common/gamedata/phase/"
_PREFIXE_QUEST = "data/common/gamedata/quest/"


@dataclass(slots=True)
class Cinematique:
    """Une cinématique, découpée en plans.

    `plans` associe un numéro de plan (`"0200"`) aux chemins VFS qui le composent. C'est la
    granularité utile pour rejouer une scène : un plan = une unité de mise en scène.
    """

    cle: str
    #: Numéro de plan → chemins VFS, triés.
    plans: dict[str, list[str]] = field(default_factory=dict)
    #: Identifiants d'acteurs apparaissant dans la scène.
    acteurs: set[str] = field(default_factory=set)
    #: Fichiers de caméra `.g4cm`.
    cameras: list[str] = field(default_factory=list)
    #: Scripts `.mevbin` — décodables en arbre.
    scripts: list[str] = field(default_factory=list)
    #: Archives d'animation `.g4pk`.
    packs: list[str] = field(default_factory=list)
    #: Tables `EventMap_fix_*` — le décor par plan.
    decors: list[str] = field(default_factory=list)

    @property
    def chapitre(self) -> str:
        """Le segment `evNN`."""
        return self.cle.split("_", 1)[0]

    @property
    def nb_plans(self) -> int:
        """Nombre de plans distincts."""
        return len(self.plans)

    @property
    def a_camera(self) -> bool:
        """`True` si la scène porte au moins un fichier de caméra."""
        return bool(self.cameras)

    def vers_dict(self) -> dict[str, Any]:
        """Forme sérialisable pour le cache."""
        return {
            "cle": self.cle,
            "plans": {n: sorted(c) for n, c in self.plans.items()},
            "acteurs": sorted(self.acteurs),
            "cameras": sorted(self.cameras),
            "scripts": sorted(self.scripts),
            "packs": sorted(self.packs),
            "decors": sorted(self.decors),
        }

    @classmethod
    def depuis_dict(cls, brut: dict[str, Any]) -> "Cinematique":
        """Reconstruit depuis le cache."""
        return cls(
            cle=str(brut["cle"]),
            plans={str(k): list(v) for k, v in (brut.get("plans") or {}).items()},
            acteurs=set(brut.get("acteurs") or ()),
            cameras=list(brut.get("cameras") or ()),
            scripts=list(brut.get("scripts") or ()),
            packs=list(brut.get("packs") or ()),
            decors=list(brut.get("decors") or ()),
        )


@dataclass(slots=True)
class Carte:
    """Une carte du jeu : ses modèles, son navmesh, ses fichiers de configuration."""

    identifiant: str
    zone: str
    modeles: list[str] = field(default_factory=list)
    navmesh: list[str] = field(default_factory=list)
    #: Nom court du fichier de config (`placement`, `funcpt`…) → chemin VFS.
    config: dict[str, str] = field(default_factory=dict)

    @property
    def zone_libelle(self) -> str:
        """Libellé lisible de la zone."""
        return ZONES.get(self.zone, self.zone)

    @property
    def a_navmesh(self) -> bool:
        """`True` si la carte porte un maillage de navigation."""
        return bool(self.navmesh)

    def vers_dict(self) -> dict[str, Any]:
        """Forme sérialisable pour le cache."""
        return {
            "identifiant": self.identifiant,
            "zone": self.zone,
            "modeles": sorted(self.modeles),
            "navmesh": sorted(self.navmesh),
            "config": dict(sorted(self.config.items())),
        }

    @classmethod
    def depuis_dict(cls, brut: dict[str, Any]) -> "Carte":
        """Reconstruit depuis le cache."""
        return cls(
            identifiant=str(brut["identifiant"]),
            zone=str(brut.get("zone", "")),
            modeles=list(brut.get("modeles") or ()),
            navmesh=list(brut.get("navmesh") or ()),
            config=dict(brut.get("config") or {}),
        )


@dataclass(slots=True)
class Trigger:
    """Un déclencheur de progression : chapitre (`phase`) ou quête (`quest`).

    Chaque déclencheur vient en deux moitiés. La table `.cfg.bin` se décode ; le `.lua.bin`
    est du Lua compilé, que ce module n'essaie pas d'interpréter — il signale seulement sa
    présence, pour qu'un appelant sache qu'une logique lui échappe.
    """

    identifiant: str
    genre: str
    table: str | None = None
    lua: str | None = None

    @property
    def exploitable(self) -> bool:
        """`True` si la table décodable est présente."""
        return self.table is not None

    def vers_dict(self) -> dict[str, Any]:
        """Forme sérialisable pour le cache."""
        return {
            "identifiant": self.identifiant,
            "genre": self.genre,
            "table": self.table,
            "lua": self.lua,
        }

    @classmethod
    def depuis_dict(cls, brut: dict[str, Any]) -> "Trigger":
        """Reconstruit depuis le cache."""
        return cls(
            identifiant=str(brut["identifiant"]),
            genre=str(brut.get("genre", "")),
            table=brut.get("table"),
            lua=brut.get("lua"),
        )


class StoryMode:
    """L'index du mode histoire : cinématiques, cartes et déclencheurs."""

    def __init__(
        self,
        cinematiques: dict[str, Cinematique] | None = None,
        cartes: dict[str, Carte] | None = None,
        triggers: dict[str, Trigger] | None = None,
        tables_map: list[str] | None = None,
    ) -> None:
        """Construit un index, vide par défaut. Voir `indexer`."""
        self.cinematiques = cinematiques or {}
        self.cartes = cartes or {}
        self.triggers = triggers or {}
        #: Tables globales de `data/common/map/` (`map_data`, `map_minimap`…).
        self.tables_map = tables_map or []

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def indexer(cls, vfs: Any) -> "StoryMode":
        """Parcourt le VFS une fois et range tout le mode histoire."""
        cines: dict[str, Cinematique] = {}
        cartes: dict[str, Carte] = {}
        triggers: dict[str, Trigger] = {}
        tables: list[str] = []

        for entree in vfs.parcourir():
            chemin = str(entree.get("path", ""))
            if chemin.startswith(_PREFIXE_EVENT):
                cls._ranger_event(chemin, cines)
            elif chemin.startswith(_PREFIXE_MAP):
                cls._ranger_map(chemin, cartes, tables)
            elif chemin.startswith((_PREFIXE_PHASE, _PREFIXE_QUEST)):
                cls._ranger_trigger(chemin, triggers)

        for cine in cines.values():
            for fichiers in cine.plans.values():
                fichiers.sort()
        return cls(cines, cartes, triggers, sorted(tables))

    @staticmethod
    def _ranger_event(chemin: str, cines: dict[str, Cinematique]) -> None:
        """Range un fichier d'événement, quelle que soit la forme de son nom."""
        morceaux = chemin.split("/")
        if len(morceaux) < 5:
            return
        # Le dossier porte la clé de façon fiable ; le nom de fichier, non (`EventMap_fix_*`,
        # `chr<id>_*` n'en portent aucune). On lit donc la clé du CHEMIN.
        trouve = MOTIF_CLE.search(morceaux[4])
        if not trouve:
            return
        cle = trouve.group(1)
        cine = cines.setdefault(cle, Cinematique(cle=cle))

        nom = morceaux[-1]
        tige = nom.split(".", 1)[0]

        if plan := MOTIF_PLAN.search(tige):
            cine.plans.setdefault(plan.group(1), []).append(chemin)
        if acteur := MOTIF_ACTEUR.search("_" + tige):
            cine.acteurs.add(acteur.group(1))

        if nom.endswith(".g4cm"):
            cine.cameras.append(chemin)
        elif nom.endswith(".mevbin"):
            cine.scripts.append(chemin)
        elif nom.endswith(".g4pk"):
            cine.packs.append(chemin)
        elif tige.startswith("EventMap"):
            cine.decors.append(chemin)

    @staticmethod
    def _ranger_map(chemin: str, cartes: dict[str, Carte], tables: list[str]) -> None:
        """Range un fichier de carte, ou la retient comme table globale."""
        morceaux = chemin.split("/")
        if len(morceaux) < 4:
            return
        # `data/common/map/<table>.cfg.bin` : une table globale, pas une carte.
        if morceaux[3].endswith(".cfg.bin"):
            tables.append(chemin)
            return
        if len(morceaux) < 5:
            return

        zone = morceaux[3]
        identifiant = morceaux[4]
        carte = cartes.setdefault(identifiant, Carte(identifiant=identifiant, zone=zone))

        nom = morceaux[-1]
        if nom.endswith(".g4nv"):
            carte.navmesh.append(chemin)
        elif nom.endswith((".g4mg", ".g4pkm", ".objbin", ".g4md", ".g4sk")):
            carte.modeles.append(chemin)
        elif "/config/" in chemin and nom.endswith(".cfg.bin"):
            court = nom.split(".", 1)[0]
            court = court[len(identifiant) + 1 :] if court.startswith(identifiant + "_") else court
            carte.config[court] = chemin

    @staticmethod
    def _ranger_trigger(chemin: str, triggers: dict[str, Trigger]) -> None:
        """Range un déclencheur, en appariant sa table et son Lua compilé."""
        nom = chemin.split("/")[-1]
        genre = "phase" if chemin.startswith(_PREFIXE_PHASE) else "quest"
        # `c01_trigger_0.04.78.cfg.bin` / `.lua.bin` → identifiant `c01_trigger`.
        identifiant = nom.split(".", 1)[0]
        trigger = triggers.setdefault(
            identifiant, Trigger(identifiant=identifiant, genre=genre)
        )
        if nom.endswith(".lua.bin"):
            trigger.lua = chemin
        elif nom.endswith(".cfg.bin"):
            trigger.table = chemin

    # ── Cache ────────────────────────────────────────────────────────────────

    def sauver(self, chemin: str | os.PathLike[str]) -> Path:
        """Écrit l'index en JSON, pour ne pas reparcourir le VFS au prochain lancement."""
        cible = Path(chemin)
        cible.parent.mkdir(parents=True, exist_ok=True)
        charge = {
            "version": 1,
            "cinematiques": [c.vers_dict() for c in self.trier_cinematiques()],
            "cartes": [c.vers_dict() for c in self.trier_cartes()],
            "triggers": [t.vers_dict() for t in self.trier_triggers()],
            "tables_map": self.tables_map,
        }
        cible.write_text(json.dumps(charge, ensure_ascii=False), encoding="utf-8")
        return cible

    @classmethod
    def charger(cls, chemin: str | os.PathLike[str]) -> "StoryMode":
        """Relit un index sauvegardé."""
        source = Path(chemin)
        if not source.is_file():
            raise FileNotFoundError(
                f"{source} est absent. Produis-le avec :\n"
                f"    uv run python -m niepy story --index {source}"
            )
        charge = json.loads(source.read_text(encoding="utf-8"))
        return cls(
            {
                str(b["cle"]): Cinematique.depuis_dict(b)
                for b in charge.get("cinematiques", [])
            },
            {str(b["identifiant"]): Carte.depuis_dict(b) for b in charge.get("cartes", [])},
            {str(b["identifiant"]): Trigger.depuis_dict(b) for b in charge.get("triggers", [])},
            list(charge.get("tables_map") or ()),
        )

    # ── Consultation ─────────────────────────────────────────────────────────

    def trier_cinematiques(self) -> list[Cinematique]:
        """Les cinématiques dans l'ordre du scénario."""
        return [self.cinematiques[k] for k in sorted(self.cinematiques)]

    def trier_cartes(self) -> list[Carte]:
        """Les cartes, par identifiant."""
        return [self.cartes[k] for k in sorted(self.cartes)]

    def trier_triggers(self) -> list[Trigger]:
        """Les déclencheurs, par identifiant."""
        return [self.triggers[k] for k in sorted(self.triggers)]

    def __iter__(self) -> Iterator[Cinematique]:
        return iter(self.trier_cinematiques())

    def cinematique(self, cle: str) -> Cinematique | None:
        """Une cinématique par sa clé de scène."""
        return self.cinematiques.get(cle)

    def carte(self, identifiant: str) -> Carte | None:
        """Une carte par son identifiant."""
        return self.cartes.get(identifiant)

    def trigger(self, identifiant: str) -> Trigger | None:
        """Un déclencheur par son identifiant."""
        return self.triggers.get(identifiant)

    def cartes_de(self, zone: str) -> list[Carte]:
        """Les cartes d'une zone."""
        return [c for c in self.trier_cartes() if c.zone == zone]

    def cinematiques_du_chapitre(self, chapitre: str) -> list[Cinematique]:
        """Les cinématiques d'un chapitre (`ev60`)."""
        return [c for c in self.trier_cinematiques() if c.chapitre == chapitre]

    def acteurs_frequents(self, combien: int = 10) -> list[tuple[str, int]]:
        """Les acteurs les plus présents, par nombre de cinématiques."""
        compte: dict[str, int] = {}
        for cine in self.cinematiques.values():
            for acteur in cine.acteurs:
                compte[acteur] = compte.get(acteur, 0) + 1
        return sorted(compte.items(), key=lambda kv: (-kv[1], kv[0]))[:combien]

    def resume(self) -> dict[str, Any]:
        """Chiffres d'ensemble."""
        plans = sum(c.nb_plans for c in self.cinematiques.values())
        return {
            "cinematiques": len(self.cinematiques),
            "plans": plans,
            "avec_camera": sum(1 for c in self.cinematiques.values() if c.a_camera),
            "avec_script": sum(1 for c in self.cinematiques.values() if c.scripts),
            "acteurs": len({a for c in self.cinematiques.values() for a in c.acteurs}),
            "cartes": len(self.cartes),
            "cartes_par_zone": {
                z: len(self.cartes_de(z)) for z in ZONES if self.cartes_de(z)
            },
            "cartes_avec_navmesh": sum(1 for c in self.cartes.values() if c.a_navmesh),
            "tables_map": len(self.tables_map),
            "triggers": len(self.triggers),
            "triggers_exploitables": sum(1 for t in self.triggers.values() if t.exploitable),
        }
