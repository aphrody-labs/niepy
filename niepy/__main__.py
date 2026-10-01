"""Ligne de commande de `niepy` — `uv run python -m niepy <commande>`.

Point d'entrée universel pour l'inspection, l'extraction, la détection des formats,
le décodage VFS / CPK, la rétro-ingénierie de `nie.exe` et la génération d'assets.

Commandes disponibles :
    uv run python -m niepy info
    uv run python -m niepy re [--json]
    uv run python -m niepy formats [--list] [--probe <fichier>] [--json]
    uv run python -m niepy vfs (rules | topology | list | search | info | extract)
    uv run python -m niepy cpk (info | list | extract | decrypt)
    uv run python -m niepy crilayla (decompress | compress)
    uv run python -m niepy rdbn (probe | dump)
    uv run python -m niepy g4tx (info | extract)
    uv run python -m niepy save (probe | summary | extract)
    uv run python -m niepy crand [--seed <n>] [--count <n>] [--bound <n>]
    uv run python -m niepy renpy --out <projet>/game/nie
    uv run python -m niepy data --out <projet>/game/nie/data
    uv run python -m niepy scenes --racine <dir> [--langue <lg>]
    uv run python -m niepy story --racine <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .renpy import Catalogue
from .scenes import LANGUES as LANGUES_CLI

FAMILLES: dict[str, str] = {
    "evenements": "data/common/gamedata/event/",
    "menus": "data/common/gamedata/menu/",
    "cartes": "data/common/gamedata/map/",
    "football": "data/common/gamedata/soccer/",
    "quetes": "data/common/gamedata/quest/",
    "phases": "data/common/gamedata/phase/",
    "personnages": "data/common/gamedata/character/",
    "systeme": "data/common/gamedata/system/",
    "techniques": "data/common/gamedata/skill/",
    "equipes": "data/common/gamedata/team/",
    "objets": "data/common/gamedata/item/",
    "formations": "data/common/gamedata/formation/",
    "boutiques": "data/common/gamedata/shop/",
}


# ── Rétro-ingénierie & Informations ──────────────────────────────────────────


def _cmd_info(_args: argparse.Namespace) -> int:
    """Dit ce que `niepy` voit : lib native, version, VFS et statut RE."""
    from . import __version__
    from ._ffi import chemin_bibliotheque
    from .formats import list_vfs_formats, version
    from .native_bridge import IecodeBridge, chemin_iecode_ffi
    from .nie_re import CRITICAL_OFFSETS, CRYPTO_CONSTANTS, RTTI_CLASSES, TARGET_BINARY

    print(f"niepy        v{__version__}")

    p_iecode = chemin_iecode_ffi()
    if p_iecode and IecodeBridge.est_disponible():
        print(f"iecode_ffi   {p_iecode} (v{IecodeBridge.version()} - {IecodeBridge.schema()})")
    else:
        print("iecode_ffi   non disponible (construire via dotnet publish src/IECODE/Ffi)")

    try:
        chemin = chemin_bibliotheque()
        print(f"nie_ffi      {chemin}")
    except FileNotFoundError as erreur:
        print(f"nie_ffi      ABSENTE — {erreur}", file=sys.stderr)
        return 1

    print(f"crate        v{version()}")

    try:
        from .vfs import Vfs

        with Vfs() as vfs:
            print(f"vfs          {len(vfs)} entrées — {vfs.racine}")
    except (FileNotFoundError, RuntimeError) as erreur:
        print(f"vfs          indisponible — {erreur}")

    print(
        f"re_map       {TARGET_BINARY} (117 068 fonctions, {len(CRYPTO_CONSTANTS)} constantes, "
        f"{len(CRITICAL_OFFSETS)} offsets, {len(RTTI_CLASSES)} classes RTTI, {len(list_vfs_formats())} formats)"
    )
    return 0


def _cmd_re(args: argparse.Namespace) -> int:
    """Affiche la spécification factuelle de rétro-ingénierie de nie.exe."""
    from .nie_re import get_nie_re_map

    re_map = get_nie_re_map()
    if args.json:
        print(json.dumps(re_map.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print("=" * 80)
    print(f"Spécification Rétro-Ingénierie : {re_map.target_binary} ({re_map.internal_name})")
    print(
        f"Format: {re_map.format} | Arch: {re_map.architecture} | Base: {re_map.base_address_hex}"
    )
    print(f"Total Fonctions (.pdata) : {re_map.total_functions_count:,}")
    print("=" * 80)

    print("\n[Constantes Cryptographiques]")
    print(f"{'Nom':<28} {'Hex':<14} {'Valeur':<12} {'Description'}")
    print("-" * 80)
    for c in re_map.crypto_constants:
        print(f"{c.name:<28} {c.hex_value:<14} {c.int_value:<12} {c.usage[:30]}...")

    print("\n[Offsets Fonctions Critiques]")
    print(f"{'Symbole':<28} {'Adresse Hex':<16} {'Sous-système':<14} {'Signature'}")
    print("-" * 80)
    for o in re_map.critical_offsets:
        print(f"{o.symbol:<28} {o.address_hex:<16} {o.subsystem:<14} {o.signature[:30]}...")

    print("\n[Hiérarchie Classes RTTI]")
    for r in re_map.rtti_classes:
        bases = ", ".join(r.base_classes) if r.base_classes else "racine"
        print(f"  {r.namespace}::{r.name} (vtable {r.vtable_offset_hex}) -> {bases}")

    return 0


# ── Formats VFS ──────────────────────────────────────────────────────────────


def _cmd_formats(args: argparse.Namespace) -> int:
    """Inspecte ou liste les 28 formats canoniques du VFS."""
    from .formats import detect_format, list_vfs_formats

    if args.probe:
        chemin = Path(args.probe)
        if not chemin.is_file():
            print(f"Fichier introuvable : {chemin}", file=sys.stderr)
            return 1
        octets = chemin.read_bytes()
        desc = detect_format(octets)
        if args.json:
            print(
                json.dumps(
                    {
                        "file": str(chemin),
                        "id": desc.id,
                        "name": desc.name,
                        "extension": desc.extension,
                        "mimeType": desc.mime_type,
                        "category": desc.category,
                        "isBigEndian": desc.is_big_endian,
                        "supportsEncryption": desc.encryption_supported,
                        "supportsCompression": desc.compression_supported,
                        "description": desc.description,
                    },
                    indent=2,
                )
            )
        else:
            print(f"{chemin.name}: {desc.name} (ID {desc.id})")
            print(f"  Extension : {desc.extension}")
            print(f"  MIME      : {desc.mime_type}")
            print(f"  Catégorie : {desc.category}")
            print(f"  Endian    : {'Big-Endian' if desc.is_big_endian else 'Little-Endian'}")
            print(
                f"  Flags     : chiffrement={desc.encryption_supported}, compression={desc.compression_supported}"
            )
            if desc.description:
                print(f"  Rôle      : {desc.description}")
        return 0

    formats = list_vfs_formats()
    if args.json:
        data = [
            {
                "id": f.id,
                "name": f.name,
                "extension": f.extension,
                "mimeType": f.mime_type,
                "category": f.category,
                "isBigEndian": f.is_big_endian,
                "supportsEncryption": f.encryption_supported,
                "supportsCompression": f.compression_supported,
                "description": f.description,
            }
            for f in formats
        ]
        print(json.dumps(data, indent=2))
        return 0

    print("=" * 80)
    print(f"Catalogue des {len(formats)} Formats Canoniques du VFS")
    print("=" * 80)
    print(f"{'ID':<4} {'Nom':<10} {'Ext':<10} {'Catégorie':<12} {'MIME Type':<26} {'Chiffré'}")
    print("-" * 80)
    for f in formats:
        enc_str = "Oui" if f.encryption_supported else "Non"
        print(
            f"{f.id:<4} {f.name:<10} {f.extension:<10} {f.category:<12} {f.mime_type:<26} {enc_str}"
        )
    return 0


# ── VFS Subcommands ──────────────────────────────────────────────────────────


def _cmd_vfs(args: argparse.Namespace) -> int:
    """Commandes liées au Virtual File System."""
    from .vfs import VFS_DIRECTORIES, VFS_PACK_RULES, Vfs

    action = args.vfs_action

    if action == "rules":
        print("=" * 80)
        print("Règles de Routage des Paquets CPK (data/packs/)")
        print("=" * 80)
        print(f"{'Paquet':<20} {'Masque':<16} {'Priorité':<10} {'Dérivation Clé'}")
        print("-" * 80)
        for r in VFS_PACK_RULES:
            print(
                f"{r.pack_name:<20} {r.filename_mask:<16} {r.mount_priority:<10} {r.key_derivation}"
            )
        return 0

    if action == "topology":
        print("=" * 80)
        print("Topologie des Répertoires du VFS")
        print("=" * 80)
        print(f"{'Répertoire':<24} {'Ext.':<10} {'Fichiers Estimés':<18} {'Description'}")
        print("-" * 80)
        for d in VFS_DIRECTORIES:
            print(
                f"{d.path:<24} {d.primary_extension:<10} {d.file_count_estimate:<18} {d.description[:35]}..."
            )
        return 0

    try:
        vfs = Vfs(args.racine)
    except (FileNotFoundError, RuntimeError) as erreur:
        print(f"Erreur VFS : {erreur}", file=sys.stderr)
        return 1

    with vfs:
        if action == "list":
            limite = args.limite or 50
            offset = args.offset or 0
            items = vfs.entrees(offset=offset, limite=limite)
            print(
                f"Index VFS : {len(items)} entrée(s) affichée(s) (offset {offset}, total {len(vfs)})"
            )
            for e in items:
                print(f"  {e.get('path')} ({e.get('size', 0):,} octets, pack: {e.get('cpk')})")
            return 0

        if action == "search":
            motif = args.motif or ""
            trouves = vfs.chercher(motif, limite=args.limite or 100)
            print(f"Recherche '{motif}' : {len(trouves)} résultat(s)")
            for t in trouves:
                print(f"  {t}")
            return 0

        if action == "info":
            chemin_v = args.path
            info = vfs.info_fichier(chemin_v)
            print(json.dumps(info, indent=2))
            return 0

        if action == "extract":
            chemin_v = args.path
            sortie = Path(args.out)
            vfs.extraire(chemin_v, sortie)
            print(f"Extrait : {chemin_v} -> {sortie}")
            return 0

    return 0


# ── CRI CPK Management ───────────────────────────────────────────────────────


def _cmd_cpk(args: argparse.Namespace) -> int:
    """Gestion des conteneurs CRI CPK."""
    from .crypto import decrypt_cpk_block, derive_cpk_key
    from .parsers import cpk_extract_by_name, cpk_extract_entry, cpk_info, cpk_list_entries

    action = args.cpk_action
    fichier = Path(args.fichier)
    if not fichier.is_file():
        print(f"Fichier CPK introuvable : {fichier}", file=sys.stderr)
        return 1

    donnees = fichier.read_bytes()

    if action == "info":
        info = cpk_info(donnees, filename=fichier.name)
        print(json.dumps(info, indent=2))
        return 0

    if action == "list":
        entries = cpk_list_entries(donnees, filename=fichier.name)
        print(f"CPK '{fichier.name}' : {len(entries)} fichier(s)")
        print(f"{'Idx':<6} {'Taille':<12} {'Décompressé':<14} {'Nom'}")
        print("-" * 60)
        for e in entries[:100]:
            print(
                f"{e.get('index', 0):<6} {e.get('size', 0):<12} {e.get('extractSize', 0):<14} {e.get('name')}"
            )
        if len(entries) > 100:
            print(f"... et {len(entries) - 100} autres fichiers")
        return 0

    if action == "extract":
        sortie = Path(args.out)
        if args.name:
            octets = cpk_extract_by_name(donnees, filename=fichier.name, entry_name=args.name)
        elif args.entry is not None:
            octets = cpk_extract_entry(donnees, filename=fichier.name, entry_index=args.entry)
        else:
            print("Spécifiez --name ou --entry pour l'extraction", file=sys.stderr)
            return 2
        sortie.parent.mkdir(parents=True, exist_ok=True)
        sortie.write_bytes(octets)
        print(f"Extrait : {len(octets)} octets vers {sortie}")
        return 0

    if action == "decrypt":
        key = int(args.key, 16) if args.key.startswith("0x") else int(args.key)
        dec = decrypt_cpk_block(donnees, key=key)
        sortie = Path(args.out)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        sortie.write_bytes(dec)
        print(f"Déchiffré avec la clé 0x{key:08X} -> {sortie}")
        return 0

    return 0


# ── CRILAYLA Compression ─────────────────────────────────────────────────────


def _cmd_crilayla(args: argparse.Namespace) -> int:
    """Compression et décompression CRILAYLA."""
    from .crypto import compress_crilayla, decompress_crilayla

    action = args.crilayla_action
    fichier = Path(args.fichier)
    if not fichier.is_file():
        print(f"Fichier introuvable : {fichier}", file=sys.stderr)
        return 1

    donnees = fichier.read_bytes()
    sortie = Path(args.out)
    sortie.parent.mkdir(parents=True, exist_ok=True)

    if action == "decompress":
        res = decompress_crilayla(donnees)
        sortie.write_bytes(res)
        print(f"Décompressé : {len(donnees)} -> {len(res)} octets ({sortie})")
        return 0

    if action == "compress":
        res = compress_crilayla(donnees)
        sortie.write_bytes(res)
        print(f"Compressé : {len(donnees)} -> {len(res)} octets ({sortie})")
        return 0

    return 0


# ── RDBN Data Tables ─────────────────────────────────────────────────────────


def _cmd_rdbn(args: argparse.Namespace) -> int:
    """Inspection et extraction de tables RDBN / cfg.bin."""
    from .parsers import is_rdbn, is_t2b, parse_rdbn_header, rdbn_query_table, rdbn_to_json

    action = args.rdbn_action
    fichier = Path(args.fichier)
    if not fichier.is_file():
        print(f"Fichier introuvable : {fichier}", file=sys.stderr)
        return 1

    donnees = fichier.read_bytes()

    if action == "probe":
        rdbn = is_rdbn(donnees)
        t2b = is_t2b(donnees)
        print(f"{fichier.name}: RDBN={rdbn}, T2B={t2b}")
        if rdbn:
            hdr = parse_rdbn_header(donnees)
            print(f"  Version     : {hdr.version}")
            print(f"  Types       : {hdr.type_count} (offset 0x{hdr.type_offset:X})")
            print(f"  Champs      : {hdr.field_count} (offset 0x{hdr.field_offset:X})")
            print(f"  Données     : {hdr.data_size} octets (offset 0x{hdr.data_offset:X})")
        return 0

    if action == "dump":
        sortie = Path(args.out) if args.out else None
        if args.table:
            res = rdbn_query_table(donnees, args.table)
            if not res:
                print(f"Table '{args.table}' introuvable dans {fichier.name}", file=sys.stderr)
                return 1
        else:
            res = rdbn_to_json(donnees)

        json_str = json.dumps(res, ensure_ascii=False, indent=2)
        if sortie:
            sortie.parent.mkdir(parents=True, exist_ok=True)
            sortie.write_text(json_str, encoding="utf-8")
            print(f"Dump JSON écrit vers {sortie}")
        else:
            print(json_str)
        return 0

    return 0


# ── G4TX Textures ────────────────────────────────────────────────────────────


def _cmd_g4tx(args: argparse.Namespace) -> int:
    """Inspection et décodage de textures G4TX."""
    from .formats import g4tx_vers_png
    from .parsers import g4tx_info, g4tx_subtexture_to_png, is_g4tx

    action = args.g4tx_action
    fichier = Path(args.fichier)
    if not fichier.is_file():
        print(f"Fichier introuvable : {fichier}", file=sys.stderr)
        return 1

    donnees = fichier.read_bytes()

    if action == "info":
        if not is_g4tx(donnees):
            print(f"{fichier.name} n'est pas un fichier G4TX valide", file=sys.stderr)
            return 1
        info = g4tx_info(donnees)
        print(json.dumps(info, indent=2))
        return 0

    if action == "extract":
        sortie = Path(args.out)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        if args.sub:
            png = g4tx_subtexture_to_png(donnees, args.sub)
            sortie.write_bytes(png)
            print(f"Sous-texture '{args.sub}' exportée en PNG -> {sortie}")
        else:
            png = g4tx_vers_png(donnees)
            sortie.write_bytes(png)
            print(f"Texture principale G4TX exportée en PNG -> {sortie}")
        return 0

    return 0


# ── Sauvegardes Lives (002AB8F4-*) ───────────────────────────────────────────


def _cmd_save(args: argparse.Namespace) -> int:
    """Inspection et extraction de sauvegardes Lives."""
    from .parsers import is_live_save, save_extract_blob, save_summary

    action = args.save_action
    fichier = Path(args.fichier)
    if not fichier.is_file():
        print(f"Fichier introuvable : {fichier}", file=sys.stderr)
        return 1

    donnees = fichier.read_bytes()

    if action == "probe":
        valide = is_live_save(donnees, filename=fichier.name)
        print(f"{fichier.name}: Sauvegarde Lives valide = {valide}")
        return 0 if valide else 1

    if action == "summary":
        res = save_summary(donnees, filename=fichier.name)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if action == "extract":
        if args.blob is None:
            print("Indice de blob --blob requis", file=sys.stderr)
            return 2
        sortie = Path(args.out)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        blob = save_extract_blob(donnees, filename=fichier.name, blob_index=args.blob)
        sortie.write_bytes(blob)
        print(f"Blob {args.blob} extrait ({len(blob)} octets) -> {sortie}")
        return 0

    return 0


# ── PRNG CRand (MT19937) ─────────────────────────────────────────────────────


def _cmd_crand(args: argparse.Namespace) -> int:
    """Génération pseudo-aléatoire déterministe MT19937."""
    from .nie_re import CRand

    seed = args.seed if args.seed is not None else 5489
    count = args.count or 10
    bound = args.bound

    with CRand(seed=seed) as rand:
        print(f"CRand MT19937 (graine: {seed}, {count} tirages) :")
        for i in range(count):
            if args.flottant:
                val: Any = rand.next_f32()
            elif bound is not None:
                val = rand.bounded(bound)
            else:
                val = rand.next_u32()
            print(f"  [{i:2d}] {val}")
    return 0


# ── Export Ren'Py, Data, Scènes et Story ─────────────────────────────────────


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
    from .vfs import Vfs

    sortie = Path(args.out)
    sortie.mkdir(parents=True, exist_ok=True)

    demandees = args.familles.split(",") if args.familles else list(FAMILLES)
    inconnues = [f for f in demandees if f not in FAMILLES]
    if inconnues:
        print(
            f"famille(s) inconnue(s) : {', '.join(inconnues)}. Connues : {', '.join(FAMILLES)}",
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
        print(f"langue inconnue : {args.langue}. Connues : {', '.join(LANGUES)}", file=sys.stderr)
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
            print(
                f"  caméras {len(cine.cameras)}, scripts {len(cine.scripts)}, "
                f"packs {len(cine.packs)}, décors {len(cine.decors)}"
            )
            for plan in sorted(cine.plans):
                print(f"    plan {plan} : {len(cine.plans[plan])} fichier(s)")

        if args.index:
            print(f"\nindex → {story.sauver(args.index)}")

        if not args.out:
            return 0

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
            json.dumps([c.vers_dict() for c in story.trier_cartes()], ensure_ascii=False, indent=2),
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


# ── Construction du Parseur ──────────────────────────────────────────────────


def construire_parseur() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments."""
    parseur = argparse.ArgumentParser(
        prog="niepy",
        description="Suite complète Python pour le VFS, les formats et nie.exe.",
    )
    sous = parseur.add_subparsers(dest="commande", required=True)

    # 1. info
    p_info = sous.add_parser("info", help="état de la lib native, du VFS et résumé RE")
    p_info.set_defaults(fonction=_cmd_info)

    # 2. re
    p_re = sous.add_parser("re", help="spécification de rétro-ingénierie de nie.exe")
    p_re.add_argument("--json", action="store_true", help="rend le modèle au format JSON")
    p_re.set_defaults(fonction=_cmd_re)

    # 3. formats
    p_formats = sous.add_parser("formats", help="catalogue des 28 formats et sonde de fichiers")
    p_formats.add_argument("--list", action="store_true", help="liste les 28 formats VFS")
    p_formats.add_argument("--probe", default="", help="sonde le format d'un fichier donné")
    p_formats.add_argument("--json", action="store_true", help="sortie JSON")
    p_formats.set_defaults(fonction=_cmd_formats)

    # 4. vfs
    p_vfs = sous.add_parser("vfs", help="opérations sur le Virtual File System")
    vfs_sub = p_vfs.add_subparsers(dest="vfs_action", required=True)

    p_vfs_rules = vfs_sub.add_parser("rules", help="affiche les règles de routage CPK")
    p_vfs_rules.set_defaults(fonction=_cmd_vfs)

    p_vfs_topo = vfs_sub.add_parser("topology", help="affiche la topologie des répertoires VFS")
    p_vfs_topo.set_defaults(fonction=_cmd_vfs)

    p_vfs_list = vfs_sub.add_parser("list", help="liste les entrées de l'index VFS")
    p_vfs_list.add_argument("--racine", default=None, help="racine du jeu")
    p_vfs_list.add_argument("--offset", type=int, default=0, help="offset dans l'index")
    p_vfs_list.add_argument("--limite", type=int, default=50, help="nombre maximal d'entrées")
    p_vfs_list.set_defaults(fonction=_cmd_vfs)

    p_vfs_search = vfs_sub.add_parser("search", help="recherche un motif dans le VFS")
    p_vfs_search.add_argument("motif", help="motif de recherche")
    p_vfs_search.add_argument("--racine", default=None, help="racine du jeu")
    p_vfs_search.add_argument("--limite", type=int, default=100, help="limite de résultats")
    p_vfs_search.set_defaults(fonction=_cmd_vfs)

    p_vfs_info = vfs_sub.add_parser("info", help="métadonnées d'un fichier virtuel")
    p_vfs_info.add_argument("path", help="chemin interne dans le VFS")
    p_vfs_info.add_argument("--racine", default=None, help="racine du jeu")
    p_vfs_info.set_defaults(fonction=_cmd_vfs)

    p_vfs_extract = vfs_sub.add_parser("extract", help="extrait un fichier virtuel vers le disque")
    p_vfs_extract.add_argument("path", help="chemin interne dans le VFS")
    p_vfs_extract.add_argument("--out", required=True, help="chemin de destination")
    p_vfs_extract.add_argument("--racine", default=None, help="racine du jeu")
    p_vfs_extract.set_defaults(fonction=_cmd_vfs)

    # 5. cpk
    p_cpk = sous.add_parser("cpk", help="gestion des conteneurs CRI CPK")
    cpk_sub = p_cpk.add_subparsers(dest="cpk_action", required=True)

    p_cpk_info = cpk_sub.add_parser("info", help="en-tête et métadonnées CPK")
    p_cpk_info.add_argument("fichier", help="fichier .cpk")
    p_cpk_info.set_defaults(fonction=_cmd_cpk)

    p_cpk_list = cpk_sub.add_parser("list", help="liste les fichiers d'une archive CPK")
    p_cpk_list.add_argument("fichier", help="fichier .cpk")
    p_cpk_list.set_defaults(fonction=_cmd_cpk)

    p_cpk_extract = cpk_sub.add_parser("extract", help="extrait une entrée d'un CPK")
    p_cpk_extract.add_argument("fichier", help="fichier .cpk")
    p_cpk_extract.add_argument("--name", default="", help="nom interne du fichier")
    p_cpk_extract.add_argument("--entry", type=int, default=None, help="indice ordinal")
    p_cpk_extract.add_argument("--out", required=True, help="fichier cible")
    p_cpk_extract.set_defaults(fonction=_cmd_cpk)

    p_cpk_dec = cpk_sub.add_parser("decrypt", help="déchiffre un bloc CRI position-XOR")
    p_cpk_dec.add_argument("fichier", help="fichier chiffré")
    p_cpk_dec.add_argument("--key", required=True, help="clé hex (0x1717E18E) ou décimale")
    p_cpk_dec.add_argument("--out", required=True, help="fichier clair cible")
    p_cpk_dec.set_defaults(fonction=_cmd_cpk)

    # 6. crilayla
    p_crilayla = sous.add_parser("crilayla", help="compression/décompression CRI Layla")
    crilayla_sub = p_crilayla.add_subparsers(dest="crilayla_action", required=True)

    p_crilayla_dec = crilayla_sub.add_parser("decompress", help="décompresse un fichier CRILAYLA")
    p_crilayla_dec.add_argument("fichier", help="fichier compressé")
    p_crilayla_dec.add_argument("--out", required=True, help="fichier décompressé")
    p_crilayla_dec.set_defaults(fonction=_cmd_crilayla)

    p_crilayla_comp = crilayla_sub.add_parser("compress", help="compresse un fichier en CRILAYLA")
    p_crilayla_comp.add_argument("fichier", help="fichier brut")
    p_crilayla_comp.add_argument("--out", required=True, help="fichier compressé cible")
    p_crilayla_comp.set_defaults(fonction=_cmd_crilayla)

    # 7. rdbn
    p_rdbn = sous.add_parser("rdbn", help="inspection et dump de tables RDBN / cfg.bin")
    rdbn_sub = p_rdbn.add_subparsers(dest="rdbn_action", required=True)

    p_rdbn_probe = rdbn_sub.add_parser("probe", help="sonde un fichier cfg.bin")
    p_rdbn_probe.add_argument("fichier", help="fichier .cfg.bin")
    p_rdbn_probe.set_defaults(fonction=_cmd_rdbn)

    p_rdbn_dump = rdbn_sub.add_parser("dump", help="dump les données RDBN en JSON")
    p_rdbn_dump.add_argument("fichier", help="fichier .cfg.bin")
    p_rdbn_dump.add_argument("--table", default="", help="nom de la table spécifique")
    p_rdbn_dump.add_argument("--out", default="", help="fichier JSON de sortie (stdout sinon)")
    p_rdbn_dump.set_defaults(fonction=_cmd_rdbn)

    # 8. g4tx
    p_g4tx = sous.add_parser("g4tx", help="inspection et extraction de textures G4TX")
    g4tx_sub = p_g4tx.add_subparsers(dest="g4tx_action", required=True)

    p_g4tx_info = g4tx_sub.add_parser("info", help="affiche les textures et sous-textures G4TX")
    p_g4tx_info.add_argument("fichier", help="fichier .g4tx")
    p_g4tx_info.set_defaults(fonction=_cmd_g4tx)

    p_g4tx_extract = g4tx_sub.add_parser("extract", help="exporte une texture G4TX en PNG")
    p_g4tx_extract.add_argument("fichier", help="fichier .g4tx")
    p_g4tx_extract.add_argument("--sub", default="", help="nom de la sous-texture (atlas)")
    p_g4tx_extract.add_argument("--out", required=True, help="fichier image PNG cible")
    p_g4tx_extract.set_defaults(fonction=_cmd_g4tx)

    # 9. save
    p_save = sous.add_parser("save", help="gestion des conteneurs de sauvegarde Lives (002AB8F4-*)")
    save_sub = p_save.add_subparsers(dest="save_action", required=True)

    p_save_probe = save_sub.add_parser("probe", help="vérifie si le fichier est une sauvegarde")
    p_save_probe.add_argument("fichier", help="fichier de sauvegarde")
    p_save_probe.set_defaults(fonction=_cmd_save)

    p_save_summary = save_sub.add_parser("summary", help="affiche le résumé JSON de la sauvegarde")
    p_save_summary.add_argument("fichier", help="fichier de sauvegarde")
    p_save_summary.set_defaults(fonction=_cmd_save)

    p_save_extract = save_sub.add_parser("extract", help="extrait un payload blob déchiffré")
    p_save_extract.add_argument("fichier", help="fichier de sauvegarde")
    p_save_extract.add_argument("--blob", type=int, required=True, help="indice ordinal du blob")
    p_save_extract.add_argument("--out", required=True, help="fichier cible")
    p_save_extract.set_defaults(fonction=_cmd_save)

    # 10. crand
    p_crand = sous.add_parser("crand", help="générateur pseudo-aléatoire déterministe MT19937")
    p_crand.add_argument("--seed", type=int, default=5489, help="graine 32-bit (défaut : 5489)")
    p_crand.add_argument("--count", type=int, default=10, help="nombre de tirages")
    p_crand.add_argument(
        "--bound", type=int, default=None, help="borne supérieure exclusive [0, bound)"
    )
    p_crand.add_argument("--flottant", action="store_true", help="tire des réels dans [0.0, 1.0)")
    p_crand.set_defaults(fonction=_cmd_crand)

    # 11. renpy
    p_renpy = sous.add_parser("renpy", help="génère le .rpy depuis un catalogue exporté")
    p_renpy.add_argument("--out", required=True, help="dossier d'export (contient catalogue.json)")
    p_renpy.add_argument("--prefixe", default="nie", help="préfixe des identifiants (défaut : nie)")
    p_renpy.add_argument("--nom", default="", help="nom du fichier .rpy produit")
    p_renpy.set_defaults(fonction=_cmd_renpy)

    # 12. data
    p_data = sous.add_parser("data", help="exporte les familles de données du jeu en JSON")
    p_data.add_argument("--out", required=True, help="dossier de sortie")
    p_data.add_argument("--racine", default=None, help="racine du jeu (défaut : NIE_GAME_DIR)")
    p_data.add_argument(
        "--familles", default="", help=f"liste séparée par des virgules ({', '.join(FAMILLES)})"
    )
    p_data.set_defaults(fonction=_cmd_data)

    # 13. scenes
    p_scenes = sous.add_parser("scenes", help="indexe et exporte les scènes (dialogues)")
    p_scenes.add_argument("--racine", default=None, help="racine du jeu (défaut : NIE_GAME_DIR)")
    p_scenes.add_argument("--index", default="", help="écrit l'index des scènes à ce chemin")
    p_scenes.add_argument("--out", default="", help="exporte les répliques dans ce dossier")
    p_scenes.add_argument("--langue", default="", help=f"langue ({', '.join(LANGUES_CLI)})")
    p_scenes.add_argument("--chapitre", default="", help="ne garde qu'un chapitre (ex. ev01)")
    p_scenes.add_argument("--limite", type=int, default=0, help="nombre maximal de scènes")
    p_scenes.set_defaults(fonction=_cmd_scenes)

    # 14. story
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

    return parseur


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée. Rend le code de sortie du processus."""
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")

    args = construire_parseur().parse_args(argv)
    resultat: int = args.fonction(args)
    return resultat


if __name__ == "__main__":
    raise SystemExit(main())
