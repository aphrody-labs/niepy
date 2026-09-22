"""Ligne de commande de `niepy` — `uv run python -m niepy <commande>`.

Ce point d'entrée ne double pas `nie` : il couvre ce qui appartient au monde Python, à
savoir la génération de script Ren'Py et l'export de données vers un projet Python. Les
assets (voix, portraits, musique) restent produits par `nie vn export`, qui sait lire les
CPK.

    uv run python -m niepy renpy --out <projet>/game/nie
    uv run python -m niepy data  --out <projet>/game/nie/data
    uv run python -m niepy info
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .renpy import Catalogue
from .scenes import LANGUES as LANGUES_CLI

#: Familles de données du jeu exportées par `data`, et leur **dossier** dans le VFS.
#:
#: Ce sont des dossiers, pas des fichiers, et c'est délibéré : les noms de fichiers du jeu
#: portent un numéro de version (`chara_base_1.03.98.00.cfg.bin`, `item_config_7.00.25.00…`)
#: qui change d'un patch à l'autre. Un chemin de fichier en dur casserait à la mise à jour
#: suivante ; le dossier, lui, est stable.
#:
#: La liste est volontairement courte : un export « tout le VFS » produirait des dizaines de
#: gigaoctets, dont l'essentiel n'a aucun sens dans un visual novel.
#: Les tailles en commentaire sont MESURÉES sur l'installation de référence, pas estimées.
#: Elles expliquent l'ordre : `menu` et `map` dominent en nombre, `event` en volume, et les
#: familles « évidentes » d'un jeu de rôle (`item`, `team`) sont marginales — 5 et 6 fichiers.
FAMILLES: dict[str, str] = {
    "evenements": "data/common/gamedata/event/",  # 1 438 fichiers, 14,7 Mo — le plus gros
    "menus": "data/common/gamedata/menu/",  # 3 866 fichiers
    "cartes": "data/common/gamedata/map/",  # 3 115
    "football": "data/common/gamedata/soccer/",  # 873
    "quetes": "data/common/gamedata/quest/",  # 131
    "phases": "data/common/gamedata/phase/",  # 88
    "personnages": "data/common/gamedata/character/",  # 46, mais 6,6 Mo
    "systeme": "data/common/gamedata/system/",  # 29
    "techniques": "data/common/gamedata/skill/",  # 23
    "equipes": "data/common/gamedata/team/",  # 6
    "objets": "data/common/gamedata/item/",  # 5
    "formations": "data/common/gamedata/formation/",  # 3
    "boutiques": "data/common/gamedata/shop/",  # 1
}


def _cmd_renpy(args: argparse.Namespace) -> int:
    """Génère le `.rpy` qui déclare personnages, portraits et musique."""
    dossier = Path(args.out)
    try:
        catalogue = Catalogue.charger(dossier)
    except FileNotFoundError as erreur:
        print(erreur, file=sys.stderr)
        return 1

    cible = dossier.parent / args.nom if args.nom else dossier.parent / "nie_catalogue.rpy"
    ecrit = catalogue.ecrire_script(cible, prefixe=args.prefixe)
    doubles = len(catalogue.doubles())
    print(
        f"{ecrit}  —  {len(catalogue)} personnage(s) dont {doubles} doublé(s), "
        f"{len(catalogue.musique)} piste(s)"
    )
    return 0


def _cmd_data(args: argparse.Namespace) -> int:
    """Exporte les familles de données du jeu en JSON, lisibles depuis un projet Python."""
    # Import tardif : `renpy` et `info` doivent marcher sans que le VFS soit montable.
    from .vfs import Vfs

    sortie = Path(args.out)
    sortie.mkdir(parents=True, exist_ok=True)

    demandees = args.familles.split(",") if args.familles else list(FAMILLES)
    inconnues = [f for f in demandees if f not in FAMILLES]
    if inconnues:
        print(
            f"famille(s) inconnue(s) : {', '.join(inconnues)}. "
            f"Connues : {', '.join(FAMILLES)}",
            file=sys.stderr,
        )
        return 2

    try:
        vfs = Vfs(args.racine)
    except (FileNotFoundError, RuntimeError) as erreur:
        print(erreur, file=sys.stderr)
        return 1

    ecrits, echecs = 0, 0
    with vfs:
        # Un SEUL parcours de l'index pour toutes les familles : l'énumération est ce qui
        # coûte (255 000 entrées), pas le filtrage. Une passe par famille multiplierait ce
        # coût par le nombre de familles demandées.
        a_traiter: list[tuple[str, str]] = []
        for entree in vfs.parcourir():
            chemin = entree.get("path", "")
            if not chemin.endswith(".cfg.bin"):
                continue
            for famille in demandees:
                if chemin.startswith(FAMILLES[famille]):
                    a_traiter.append((famille, chemin))
                    break

        for famille, chemin in a_traiter:
            dossier = sortie / famille
            dossier.mkdir(parents=True, exist_ok=True)
            nom = Path(chemin).name.removesuffix(".cfg.bin")
            try:
                donnees: Any = vfs.charger(chemin)
            except (FileNotFoundError, ValueError) as erreur:
                # Un fichier illisible n'arrête pas l'export : le corpus est hétérogène et un
                # export partiel reste utilisable. Mais il est signalé, jamais avalé.
                print(f"  ⚠ {famille}/{nom} — {erreur}", file=sys.stderr)
                echecs += 1
                continue

            (dossier / f"{nom}.json").write_text(
                json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            ecrits += 1

        for famille in demandees:
            n = sum(1 for f, _ in a_traiter if f == famille)
            print(f"  {famille:14} {n:4} fichier(s)")

    print(f"{ecrits} fichier(s) exporté(s) vers {sortie}", end="")
    print(f", {echecs} en échec" if echecs else "")
    return 0 if ecrits else 1


def _cmd_scenes(args: argparse.Namespace) -> int:
    """Indexe les scènes du jeu, et exporte au besoin leurs répliques dans une langue."""
    from .scenes import LANGUES, Scenario
    from .vfs import Vfs

    if args.langue and args.langue not in LANGUES:
        print(
            f"langue inconnue : {args.langue}. Connues : {', '.join(LANGUES)}", file=sys.stderr
        )
        return 2

    try:
        vfs = Vfs(args.racine)
    except (FileNotFoundError, RuntimeError) as erreur:
        print(erreur, file=sys.stderr)
        return 1

    with vfs:
        print("indexation du VFS…", file=sys.stderr)
        scenario = Scenario.indexer(vfs)
        resume = scenario.resume()

        print(f"{resume['scenes']} scène(s), {resume['chapitres']} chapitre(s)")
        print("  texte par langue :")
        for langue, n in resume["texte_par_langue"].items():
            print(f"    {langue:8} {n:5}")
        print("  doublage :")
        for langue, n in resume["doublage_par_langue"].items():
            print(f"    {langue:8} {n:5}")
        print(f"  avec sous-titres : {resume['avec_sous_titres']}")

        if args.index:
            chemin = scenario.sauver(args.index)
            print(f"index → {chemin}")

        if not args.out:
            return 0

        # Export des répliques : un JSON par scène, sous le chapitre.
        langue = args.langue or "fr"
        sortie = Path(args.out)
        a_traiter = scenario.traduites(langue)
        if args.chapitre:
            a_traiter = [s for s in a_traiter if s.chapitre == args.chapitre]
        if args.limite:
            a_traiter = a_traiter[: args.limite]

        ecrits, vides = 0, 0
        for scene in a_traiter:
            lignes = scenario.lignes(scene, langue, vfs)
            if not lignes:
                vides += 1
                continue
            dossier = sortie / langue / scene.chapitre
            dossier.mkdir(parents=True, exist_ok=True)
            charge = {
                "cle": scene.cle,
                "chapitre": scene.chapitre,
                "langue": langue,
                "doublee": scene.est_doublee,
                "repliques_doublees": scene.repliques_doublees(langue),
                "lignes": lignes,
            }
            (dossier / f"{scene.cle}.json").write_text(
                json.dumps(charge, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            ecrits += 1

        print(f"{ecrits} scène(s) exportée(s) en « {langue} » vers {sortie}", end="")
        print(f", {vides} sans réplique" if vides else "")
        return 0 if ecrits else 1


def _cmd_story(args: argparse.Namespace) -> int:
    """Indexe le mode histoire — cinématiques, cartes, déclencheurs — et l'exporte."""
    from .story import StoryMode
    from .vfs import Vfs

    try:
        vfs = Vfs(args.racine)
    except (FileNotFoundError, RuntimeError) as erreur:
        print(erreur, file=sys.stderr)
        return 1

    with vfs:
        print("indexation du mode histoire…", file=sys.stderr)
        story = StoryMode.indexer(vfs)
        r = story.resume()

        print(f"cinématiques  {r['cinematiques']:6}  ({r['plans']} plans, {r['acteurs']} acteurs)")
        print(f"  avec caméra {r['avec_camera']:6}")
        print(f"  avec script {r['avec_script']:6}")
        print(f"cartes        {r['cartes']:6}  (dont {r['cartes_avec_navmesh']} avec navmesh)")
        for zone, n in r["cartes_par_zone"].items():
            print(f"    {zone:8} {n:5}")
        print(f"tables map    {r['tables_map']:6}")
        print(f"déclencheurs  {r['triggers']:6}  (dont {r['triggers_exploitables']} avec table)")

        if args.acteurs:
            print("\nacteurs les plus présents :")
            for acteur, n in story.acteurs_frequents(args.acteurs):
                print(f"    {acteur:14} {n:5} cinématique(s)")

        if args.cle:
            cine = story.cinematique(args.cle)
            if cine is None:
                print(f"cinématique inconnue : {args.cle}", file=sys.stderr)
                return 2
            print(f"\n{cine.cle} — {cine.nb_plans} plan(s), {len(cine.acteurs)} acteur(s)")
            print(f"  caméras {len(cine.cameras)}, scripts {len(cine.scripts)}, "
                  f"packs {len(cine.packs)}, décors {len(cine.decors)}")
            for plan in sorted(cine.plans):
                print(f"    plan {plan} : {len(cine.plans[plan])} fichier(s)")

        if args.index:
            print(f"\nindex → {story.sauver(args.index)}")

        if not args.out:
            return 0

        # Export : une fiche JSON par cinématique, plus les cartes et les déclencheurs.
        sortie = Path(args.out)
        cines = story.trier_cinematiques()
        if args.chapitre:
            cines = [c for c in cines if c.chapitre == args.chapitre]
        if args.limite:
            cines = cines[: args.limite]

        dossier_cine = sortie / "cinematiques"
        dossier_cine.mkdir(parents=True, exist_ok=True)
        for cine in cines:
            (dossier_cine / f"{cine.cle}.json").write_text(
                json.dumps(cine.vers_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )

        (sortie / "cartes.json").write_text(
            json.dumps(
                [c.vers_dict() for c in story.trier_cartes()], ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        (sortie / "triggers.json").write_text(
            json.dumps(
                [t.vers_dict() for t in story.trier_triggers()], ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )

        print(
            f"{len(cines)} cinématique(s), {len(story.cartes)} carte(s) et "
            f"{len(story.triggers)} déclencheur(s) → {sortie}"
        )
        return 0


def _cmd_info(_args: argparse.Namespace) -> int:
    """Dit ce que `niepy` voit : lib native, version, VFS."""
    from . import __version__
    from ._ffi import chemin_bibliotheque

    print(f"niepy        {__version__}")
    try:
        chemin = chemin_bibliotheque()
        print(f"nie_ffi      {chemin}")
    except FileNotFoundError as erreur:
        print(f"nie_ffi      ABSENTE — {erreur}", file=sys.stderr)
        return 1

    from .formats import version

    print(f"crate        {version()}")

    try:
        from .vfs import Vfs

        with Vfs() as vfs:
            print(f"vfs          {len(vfs)} entrées — {vfs.racine}")
    except (FileNotFoundError, RuntimeError) as erreur:
        print(f"vfs          indisponible — {erreur}")
    return 0


def construire_parseur() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments."""
    parseur = argparse.ArgumentParser(
        prog="niepy", description="Pont Python vers le moteur et les données de nie."
    )
    sous = parseur.add_subparsers(dest="commande", required=True)

    p_renpy = sous.add_parser("renpy", help="génère le .rpy depuis un catalogue exporté")
    p_renpy.add_argument("--out", required=True, help="dossier d'export (contient catalogue.json)")
    p_renpy.add_argument("--prefixe", default="nie", help="préfixe des identifiants (défaut : nie)")
    p_renpy.add_argument("--nom", default="", help="nom du fichier .rpy produit")
    p_renpy.set_defaults(fonction=_cmd_renpy)

    p_data = sous.add_parser("data", help="exporte les familles de données du jeu en JSON")
    p_data.add_argument("--out", required=True, help="dossier de sortie")
    p_data.add_argument("--racine", default=None, help="racine du jeu (défaut : NIE_GAME_DIR)")
    p_data.add_argument(
        "--familles", default="", help=f"liste séparée par des virgules ({', '.join(FAMILLES)})"
    )
    p_data.set_defaults(fonction=_cmd_data)

    p_scenes = sous.add_parser("scenes", help="indexe et exporte les scènes (dialogues)")
    p_scenes.add_argument("--racine", default=None, help="racine du jeu (défaut : NIE_GAME_DIR)")
    p_scenes.add_argument("--index", default="", help="écrit l'index des scènes à ce chemin")
    p_scenes.add_argument("--out", default="", help="exporte les répliques dans ce dossier")
    p_scenes.add_argument("--langue", default="", help=f"langue ({', '.join(LANGUES_CLI)})")
    p_scenes.add_argument("--chapitre", default="", help="ne garde qu'un chapitre (ex. ev01)")
    p_scenes.add_argument("--limite", type=int, default=0, help="nombre maximal de scènes")
    p_scenes.set_defaults(fonction=_cmd_scenes)

    p_story = sous.add_parser("story", help="cinématiques, cartes et progression du mode histoire")
    p_story.add_argument("--racine", default=None, help="racine du jeu (défaut : NIE_GAME_DIR)")
    p_story.add_argument("--index", default="", help="écrit l'index du mode histoire ici")
    p_story.add_argument("--out", default="", help="exporte les fiches JSON dans ce dossier")
    p_story.add_argument("--cle", default="", help="détaille une cinématique (ex. ev60_01560)")
    p_story.add_argument("--chapitre", default="", help="ne garde qu'un chapitre (ex. ev60)")
    p_story.add_argument("--limite", type=int, default=0, help="nombre maximal de cinématiques")
    p_story.add_argument(
        "--acteurs", type=int, default=0, help="affiche les N acteurs les plus présents"
    )
    p_story.set_defaults(fonction=_cmd_story)

    p_info = sous.add_parser("info", help="état de la lib native et du VFS")
    p_info.set_defaults(fonction=_cmd_info)

    return parseur


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée. Rend le code de sortie du processus."""
    # La console Windows est en cp1252 par défaut : sans cela, « exporté » sort en « export? ».
    # `errors="replace"` évite qu'un nom d'asset exotique fasse planter l'affichage.
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")

    args = construire_parseur().parse_args(argv)
    resultat: int = args.fonction(args)
    return resultat


if __name__ == "__main__":
    raise SystemExit(main())
