"""Accès au système de fichiers virtuel du jeu (packs CPK ou arborescence extraite).

Le VFS n'est pas sur le disque : parcourir `data/` avec `os.walk` ne voit pas l'intérieur des
CPK. Tout passe par `nie-formats` côté Rust.
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from types import TracebackType
from typing import Any, Iterator

from ._ffi import NieBytes, NieCacheStats, bibliotheque
from .formats import decoder, prendre_octets

__all__ = ["Vfs", "racine_jeu"]


def racine_jeu(explicite: str | os.PathLike[str] | None = None) -> Path:
    """Résout la racine du jeu, sans jamais coder un chemin de machine en dur.

    Ordre : argument explicite, `NIE_GAME_DIR`, puis remontée des ancêtres du répertoire
    courant à la recherche de `data/cpk_list.cfg.bin`.

    Une variable d'environnement **posée mais vide** est ignorée : une chaîne vide n'est pas
    une racine, et la traiter comme telle donne un chemin où rien n'est jamais trouvé.
    """
    if explicite is not None:
        return Path(explicite)

    depuis_env = os.environ.get("NIE_GAME_DIR", "").strip()
    if depuis_env:
        return Path(depuis_env)

    courant = Path.cwd().resolve()
    for ancetre in (courant, *courant.parents):
        if (ancetre / "data" / "cpk_list.cfg.bin").is_file():
            return ancetre

    raise FileNotFoundError(
        "Racine du jeu introuvable. Pose NIE_GAME_DIR vers l'installation "
        "(le dossier qui contient data/cpk_list.cfg.bin), ou passe-la en argument."
    )


class Vfs:
    """Un montage du VFS. À utiliser comme gestionnaire de contexte.

        with Vfs() as vfs:
            octets = vfs.lire("data/common/…")

    Le handle natif est libéré à la sortie du bloc. Une instance fermée lève `RuntimeError`
    plutôt que de déréférencer un pointeur mort.
    """

    def __init__(self, racine: str | os.PathLike[str] | None = None) -> None:
        """Monte le VFS. `racine` par défaut : voir `racine_jeu`."""
        self._racine = racine_jeu(racine)
        # `Vfs::init` attend `<racine>/data`, pas la racine : lui passer la racine donne
        # « impossible d'ouvrir cpk_list.cfg.bin », une erreur qui accuse le fichier.
        dossier = self._racine / "data"
        handle = bibliotheque().nie_vfs_open(str(dossier).encode("utf-8"))
        if not handle:
            raise RuntimeError(f"montage du VFS impossible depuis {dossier}")
        self._handle: int | None = handle

    @property
    def racine(self) -> Path:
        """Racine du jeu utilisée pour ce montage."""
        return self._racine

    def _vivant(self) -> int:
        if self._handle is None:
            raise RuntimeError("ce Vfs est fermé")
        return self._handle

    def __len__(self) -> int:
        """Nombre d'entrées indexées."""
        return int(bibliotheque().nie_vfs_count(self._vivant()))

    def lire(self, chemin: str) -> bytes:
        """Lit un fichier virtuel. Lève `FileNotFoundError` s'il est absent."""
        sortie = NieBytes()
        bibliotheque().nie_vfs_read_out(
            self._vivant(), chemin.encode("utf-8"), ctypes.byref(sortie)
        )
        donnees = prendre_octets(sortie)
        if not donnees:
            raise FileNotFoundError(f"absent du VFS (ou vide) : {chemin}")
        return donnees

    def existe(self, chemin: str) -> bool:
        """Dit si `chemin` est servable, **sans extraire son contenu**.

        À employer partout où seule la présence importe — un menu qui décide s'il peut
        afficher un visage, par exemple. L'alternative naturelle, `lire()` dans un
        `try`, extrait le paquet CPK entier pour répondre par oui ou par non et le
        garde en cache : mesuré à 4,9 Go retenus pour soixante vérifications de
        textures dispersées.

        Être dans l'index ne suffit pas : `cpk_list.cfg.bin` déclare des fichiers
        « loose » qui n'existent pas forcément sur une installation donnée. Ce test
        vérifie la présence du conteneur, jamais le contenu.
        """
        return bool(
            bibliotheque().nie_vfs_is_readable(self._vivant(), chemin.encode("utf-8"))
        )

    def __contains__(self, chemin: object) -> bool:
        """`"data/…" in vfs` — même test que `existe`, sans jamais lever."""
        return isinstance(chemin, str) and self.existe(chemin)

    def charger(self, chemin: str) -> Any:
        """Lit un fichier virtuel **et** le décode selon son format détecté."""
        return decoder(self.lire(chemin))

    def entrees(self, offset: int = 0, limite: int = 5000) -> list[dict[str, Any]]:
        """Rend une tranche de l'index, sous forme `[{path, cpk, size}]`."""
        sortie = NieBytes()
        bibliotheque().nie_vfs_list_range_json_out(
            self._vivant(), offset, limite, ctypes.byref(sortie)
        )
        brut = prendre_octets(sortie)
        return json.loads(brut) if brut else []

    def parcourir(self, par: int = 5000) -> Iterator[dict[str, Any]]:
        """Itère sur tout l'index, par tranches — sans charger 255 000 entrées d'un coup."""
        offset = 0
        while True:
            lot = self.entrees(offset, par)
            if not lot:
                return
            yield from lot
            offset += len(lot)

    def chercher(self, motif: str, limite: int = 200) -> list[str]:
        """Chemins contenant `motif` (sans casse). Coupe à `limite` résultats.

        Le premier appel construit l'index, ce qui prend un temps notable sur un montage
        « dump » (255 000 entrées sur NTFS) : c'est l'énumération qui coûte, pas la recherche.
        """
        motif = motif.casefold()
        trouves: list[str] = []
        for entree in self.parcourir():
            chemin = entree.get("path", "")
            if motif in chemin.casefold():
                trouves.append(chemin)
                if len(trouves) >= limite:
                    break
        return trouves

    # ── Mémoire ──────────────────────────────────────────────────────────────

    def stats_cache(self) -> dict[str, int]:
        """Occupation du cache de paquets CPK : `{octets, entrees, budget}`.

        Le VFS garde les octets **bruts** de chaque paquet ouvert pour éviter de le relire.
        Quelques lectures dans des paquets différents suffisent donc à retenir plusieurs
        centaines de mégaoctets, sans que rien ne le signale.
        """
        brut = NieCacheStats()
        bibliotheque().nie_vfs_cache_stats(self._vivant(), ctypes.byref(brut))
        return {"octets": brut.octets, "entrees": brut.entrees, "budget": brut.budget}

    def vider_cache(self) -> int:
        """Vide le cache de paquets et rend les octets libérés.

        Sans danger pour une lecture en cours : elle détient sa donnée jusqu'au bout. Les
        lectures suivantes relisent le paquet depuis le disque — c'est le prix, assumé, de
        rendre la mémoire.
        """
        return int(bibliotheque().nie_vfs_cache_vider(self._vivant()))

    def regler_budget_cache(self, octets: int) -> int:
        """Change le plafond du cache et évince immédiatement ce qui dépasse.

        **Le défaut de la bibliothèque native est de 16 Gio**, dimensionné pour un traitement
        par lots qui a la machine pour lui. Un jeu qui embarque `niepy` — un projet Ren'Py, par
        exemple — a tout intérêt à poser un plafond bien plus bas dès le démarrage :

            vfs.regler_budget_cache(256 * 1024 * 1024)   # 256 Mio

        L'éviction garde toujours un paquet : évincer celui qu'on vient de demander ferait
        relire le disque à l'appel suivant, en boucle.

        Rend les octets libérés par l'éviction déclenchée.
        """
        if octets < 0:
            raise ValueError("le budget ne peut pas être négatif")
        return int(bibliotheque().nie_vfs_cache_budget(self._vivant(), octets))

    def fermer(self) -> None:
        """Libère le handle natif. Idempotent."""
        if self._handle is not None:
            bibliotheque().nie_vfs_free(self._handle)
            self._handle = None

    def __enter__(self) -> "Vfs":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.fermer()

    def __del__(self) -> None:
        # Filet de sécurité : un Vfs abandonné sans `with` ne doit pas fuir le handle.
        try:
            self.fermer()
        except Exception:
            pass

    # ── Copie et sérialisation ───────────────────────────────────────────────
    #
    # `_handle` est un pointeur natif rendu par `nie_vfs_open`. Trois opérations
    # Python le dupliquent ou le transportent sans rien y comprendre, et chacune
    # a été vue faire du dégât :
    #
    #   `pickle.dumps(vfs)`     produisait 183 octets EN SILENCE, pointeur compris.
    #                           Rechargés dans un autre processus, la première
    #                           `.lire()` fait avorter le processus (exit 127) :
    #                           l'adresse ne veut plus rien dire. C'est le piège
    #                           d'un moteur de jeu qui sérialise son état — Ren'Py
    #                           sauvegarde son store à chaque partie enregistrée.
    #   `copy.deepcopy(vfs)`    donnait deux objets portant le MÊME pointeur ; les
    #                           deux `__del__` appelaient `nie_vfs_free` dessus.
    #                           Double libération, plantage différé et sans rapport
    #                           visible avec sa cause.
    #   `copy.copy(vfs)`        même chose.
    #
    # On ne « répare » pas en remontant le VFS à la volée : un remontage coûte près
    # d'une seconde et échoue si le jeu n'est pas installé sur la machine qui
    # recharge. Une sauvegarde ne doit pas dépendre de ça. On refuse donc,
    # bruyamment et à l'endroit de l'erreur, plutôt que de planter trois écrans
    # plus loin.

    def __reduce__(self) -> Any:
        raise TypeError(
            "un Vfs ne se sérialise pas : il porte un pointeur natif qui n'a de sens "
            "que dans le processus qui l'a ouvert. Remonte-le après chargement "
            "(`Vfs(racine)`), ou garde-le hors de ce qui est sauvegardé."
        )

    def __deepcopy__(self, memo: dict[int, Any]) -> "Vfs":
        # Un montage est une ressource partagée, pas une valeur. Le copier
        # dupliquerait le pointeur et ferait libérer deux fois.
        return self

    def __copy__(self) -> "Vfs":
        return self
