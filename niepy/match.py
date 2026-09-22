"""Le moteur de match : une simulation 11 v 11 déterministe, avancée tick par tick.

C'est la partie qui **tourne**, par opposition au reste de `niepy` qui lit des assets. Le
déterminisme est le contrat : à `dt` et entrées identiques, deux exécutions donnent la même
suite d'états — ce qui permet à un visual novel de rejouer une action à l'identique, ou de
calculer une issue de match hors écran puis de la raconter.

    with Match() as m:
        m.avancer(90.0)
        print(m.score)
"""

from __future__ import annotations

import ctypes
import json
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from ._ffi import NieBall, NieBytes, NiePlayer, bibliotheque
from .formats import prendre_octets

__all__ = ["Ballon", "Joueur", "Match", "PAS_PAR_DEFAUT", "ROLES", "STATS", "simuler_match"]

#: Pas de simulation par défaut (secondes) — 60 Hz, la cadence à laquelle le moteur est réglé.
PAS_PAR_DEFAUT = 1.0 / 60.0

#: Rôles, dans l'ordre du discriminant rendu par la couche native.
ROLES = ("GK", "DF", "MF", "FW")

#: Les sept statistiques d'un joueur IEVR, dans l'ordre du jeu. Noms confirmés
#: par `inagle`, validés sur dump réel.
STATS = ("kc", "cr", "tc", "pr", "ps", "ag", "it")


def simuler_match(
    nous: dict[str, Any] | tuple[str, dict[str, int]],
    eux: dict[str, Any] | tuple[str, dict[str, int]],
    graine: int = 0,
) -> dict[str, Any]:
    """Tranche une rencontre d'un bloc, à partir des STATISTIQUES et d'une GRAINE.

    C'est le complément de [`Match`], et il répond à un autre besoin.

    [`Match`] fait TOURNER un match jouable : on lui pousse des entrées et on
    l'avance pas à pas. Il n'accepte **aucune graine** et son onze est le sien —
    deux matchs laissés à eux-mêmes rendent le même score, et rien n'y distingue
    les joueurs d'un camp de ceux de l'autre. Pour raconter une rencontre que le
    joueur ne dispute pas, c'est le mauvais outil : on ne peut ni la faire
    dépendre de la force des effectifs, ni la rejouer à l'identique.

    Cette fonction fait l'inverse. Elle appelle `nie_core::match_sim::simulate_match`,
    un modèle minute par minute où la probabilité de but de chaque camp sort du
    rapport entre son `kc` et le `ps` de l'autre, et où la graine fixe tout le
    reste. Deux appels de même graine rendent le même match.

        >>> issue = simuler_match(
        ...     ("Raimon", {"kc": 207, "cr": 216, "tc": 218,
        ...                 "pr": 235, "ps": 242, "ag": 210, "it": 261}),
        ...     ("Zeus", dict.fromkeys(STATS, 120)),
        ...     graine=42,
        ... )
        >>> issue["home_score"], issue["away_score"]        # doctest: +SKIP
        (3, 1)

    Chaque camp se donne soit en `(nom, stats)`, soit en `TeamSetup` complet
    (`{"name", "aggregate_stats", "placements"}`). Les statistiques absentes
    valent 0 ; un `dict.fromkeys(STATS, n)` donne une équipe uniforme de niveau `n`.

    Rend le `MatchResult` : `home_score`, `away_score`, `final_clock`
    (`minutes * 10_000 + secondes`) et la séquence complète d'`events`.

    Lève `ValueError` si la couche native refuse l'entrée.
    """

    def equipe(valeur: Any) -> dict[str, Any]:
        if isinstance(valeur, tuple):
            nom, stats = valeur
            return {
                "name": str(nom),
                "aggregate_stats": {cle: int(stats.get(cle, 0)) for cle in STATS},
                "placements": None,
            }
        # Un TeamSetup déjà formé : on complète seulement ce qui manque, pour que
        # `placements` reste optionnel côté appelant.
        forme = dict(valeur)
        forme.setdefault("placements", None)
        return forme

    brut = NieBytes()
    bibliotheque().nie_match_simulate_json_out(
        json.dumps(equipe(nous)).encode("utf-8"),
        json.dumps(equipe(eux)).encode("utf-8"),
        ctypes.c_uint64(int(graine) & 0xFFFFFFFFFFFFFFFF),
        ctypes.byref(brut),
    )
    octets = prendre_octets(brut)
    if not octets:
        raise ValueError(
            "simulation refusée : vérifie que chaque camp porte un `name` et les "
            "sept statistiques " + ", ".join(STATS)
        )
    return json.loads(octets.decode("utf-8"))


@dataclass(frozen=True, slots=True)
class Joueur:
    """Un joueur à un instant donné. Positions en mètres, origine au centre du terrain."""

    x: float
    y: float
    vx: float
    vy: float
    team: int
    role: str

    @property
    def domicile(self) -> bool:
        """`True` si le joueur est de l'équipe qui attaque vers les `x` positifs."""
        return self.team == 0


@dataclass(frozen=True, slots=True)
class Ballon:
    """Le ballon à un instant donné. `z` est la hauteur au-dessus du sol."""

    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float


class Match:
    """Une partie en cours. À utiliser comme gestionnaire de contexte."""

    def __init__(self) -> None:
        """Crée un match au coup d'envoi."""
        handle = bibliotheque().nie_world_new()
        if not handle:
            raise RuntimeError("création du monde de match impossible")
        self._handle: int | None = handle

    def _vivant(self) -> int:
        if self._handle is None:
            raise RuntimeError("ce Match est terminé (handle libéré)")
        return self._handle

    # ── Pilotage ─────────────────────────────────────────────────────────────

    def coup_denvoi(self) -> None:
        """Remet le match au coup d'envoi, score et chronomètre compris."""
        bibliotheque().nie_world_kickoff(self._vivant())

    def pas(self, dt: float = PAS_PAR_DEFAUT) -> None:
        """Avance la simulation d'un pas de `dt` secondes."""
        bibliotheque().nie_world_step(self._vivant(), ctypes.c_float(dt))

    def avancer(self, secondes: float, dt: float = PAS_PAR_DEFAUT) -> None:
        """Avance de `secondes` de temps de jeu, par pas de `dt`.

        Le nombre de pas est calculé une fois, pour que deux appels de même durée fassent
        exactement le même nombre d'itérations — sinon le déterminisme est perdu par une
        accumulation de flottants.
        """
        if dt <= 0.0:
            raise ValueError("dt doit être strictement positif")
        for _ in range(int(round(secondes / dt))):
            self.pas(dt)

    def commander(self, dx: float = 0.0, dy: float = 0.0, tirer: bool = False) -> None:
        """Pose l'entrée du joueur contrôlé : direction souhaitée et ordre de frappe."""
        bibliotheque().nie_world_set_input(
            self._vivant(), ctypes.c_float(dx), ctypes.c_float(dy), ctypes.c_bool(tirer)
        )

    # ── Lecture d'état ───────────────────────────────────────────────────────

    @property
    def temps(self) -> float:
        """Temps de jeu écoulé, en secondes."""
        return float(bibliotheque().nie_world_time(self._vivant()))

    @property
    def tick(self) -> int:
        """Numéro du tick courant — le compteur qui atteste du déterminisme."""
        return int(bibliotheque().nie_world_tick(self._vivant()))

    @property
    def score(self) -> tuple[int, int]:
        """Score `(domicile, extérieur)`."""
        domicile = ctypes.c_uint32()
        exterieur = ctypes.c_uint32()
        bibliotheque().nie_world_score(
            self._vivant(), ctypes.byref(domicile), ctypes.byref(exterieur)
        )
        return domicile.value, exterieur.value

    @property
    def porteur(self) -> int | None:
        """Indice du joueur qui possède le ballon, ou `None` si le ballon est libre."""
        i = int(bibliotheque().nie_world_possessor(self._vivant()))
        return None if i < 0 else i

    @property
    def ballon(self) -> Ballon:
        """État du ballon."""
        brut = NieBall()
        bibliotheque().nie_world_ball(self._vivant(), ctypes.byref(brut))
        return Ballon(brut.x, brut.y, brut.z, brut.vx, brut.vy, brut.vz)

    def __len__(self) -> int:
        """Nombre de joueurs sur le terrain."""
        return int(bibliotheque().nie_world_player_count(self._vivant()))

    def joueur(self, i: int) -> Joueur:
        """Joueur d'indice `i`. Lève `IndexError` hors bornes."""
        brut = NiePlayer()
        if not bibliotheque().nie_world_player(self._vivant(), i, ctypes.byref(brut)):
            raise IndexError(f"aucun joueur d'indice {i}")
        role = ROLES[brut.role] if brut.role < len(ROLES) else "?"
        return Joueur(brut.x, brut.y, brut.vx, brut.vy, brut.team, role)

    def joueurs(self) -> list[Joueur]:
        """Tous les joueurs, dans l'ordre du moteur."""
        return [self.joueur(i) for i in range(len(self))]

    def instantane(self) -> dict[str, Any]:
        """État complet en dictionnaire — la voie pratique pour journaliser ou rejouer.

        Passe par le JSON de la couche native : une seule traversée de frontière au lieu
        d'une par joueur.
        """
        sortie = NieBytes()
        bibliotheque().nie_world_snapshot_json_out(self._vivant(), ctypes.byref(sortie))
        brut = prendre_octets(sortie)
        if not brut:
            raise RuntimeError("instantané du match indisponible")
        return json.loads(brut)

    # ── Cycle de vie ─────────────────────────────────────────────────────────

    def terminer(self) -> None:
        """Libère le handle natif. Idempotent."""
        if self._handle is not None:
            bibliotheque().nie_world_free(self._handle)
            self._handle = None

    def __enter__(self) -> "Match":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.terminer()

    def __del__(self) -> None:
        try:
            self.terminer()
        except Exception:
            pass
