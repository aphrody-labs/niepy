# `niepy` — nie vu depuis Python

La porte d'entrée Python vers le moteur et les données de *nie*. C'est ce qui permet à un
visual novel Ren'Py d'utiliser le vrai moteur et les vrais assets, sans réimplémenter quoi que
ce soit.

Trois usages, du plus simple au plus engageant :

| Usage | Objet | Ce que ça fait |
|---|---|---|
| Lire le jeu | `Vfs`, `decoder`, `g4tx_vers_png` | Le VFS (packs CPK ou dump) et les décodeurs de formats |
| Faire tourner le jeu | `Match` | La simulation 11 v 11 déterministe, tick par tick |
| Rendre les assets | `Rendu` | `nie-game` en sous-processus : textures et écrans composés → PNG |
| Lire les scènes | `Scenario`, `Scene` | Les 5 173 scènes du jeu, leurs dialogues et leurs voix |
| Le mode histoire | `StoryMode` | 1 735 cinématiques, 889 cartes, 115 déclencheurs |
| Alimenter un VN | `renpy.Catalogue` | Le catalogue d'assets exporté, et la génération de `.rpy` |

## Prérequis

Tout passe par `nie_ffi`, la bibliothèque native construite depuis les crates Rust. Il faut
l'avoir construite au moins une fois :

```bash
cargo build -p nie-ffi --release
```

`niepy` la résout seule : `NIE_FFI_PATH` si elle est posée, sinon `target/release`, sinon
`target/debug`, en remontant les ancêtres jusqu'à la racine du dépôt. **Aucun chemin de
machine n'est écrit en dur.**

> Sur Windows, rustc produit `iecode.dll`, **sans** préfixe `lib`. Chercher `libiecode.dll`
> échoue silencieusement puis casse au premier appel, avec une erreur qui accuse l'appel et
> non la résolution du chemin.

## Faire tourner un match

```python
from niepy import Match

with Match() as m:
    m.avancer(90.0)          # 90 secondes de temps de jeu, à 60 Hz
    print(m.score)           # (domicile, extérieur)
    print(m.porteur)         # indice du joueur qui a le ballon, ou None
```

La simulation est **déterministe** : à `dt` et entrées identiques, deux exécutions donnent la
même suite d'états. C'est ce qui permet à un visual novel de rejouer une action à l'identique,
ou de calculer une issue de match hors écran puis de la raconter.

`m.instantane()` rend l'état complet en dictionnaire, en une seule traversée de frontière —
préférable à une boucle sur `m.joueur(i)` quand on veut tout.

## Lire les données du jeu

```python
from niepy import Vfs

with Vfs() as vfs:
    print(len(vfs), "entrées indexées")
    donnees = vfs.charger("data/common/…")   # lit ET décode selon le format détecté
```

La racine du jeu se résout à l'exécution : argument explicite, puis `NIE_GAME_DIR`, puis
remontée des ancêtres à la recherche de `data/cpk_list.cfg.bin`.

`decoder()` sert **tous** les formats du dispatch partagé, sans une ligne de code par format
dans `niepy` — y compris les trois du mode histoire, qui ne rendaient qu'un en-tête jusqu'à
récemment :

| Format | Ce que `decoder()` rend |
|---|---|
| `.g4cm` | Caméra de cinématique : `clips`, `names`, `objects`, `channels`, `times` |
| `.g4nv` | Navmesh : `vertices`, `polygons`, `edges`, `corners` |
| `.lua.bin` | Bytecode Lua 5.2 : en-tête et prototypes imbriqués (`main.code`, `constants`, `protos`) |

## Borner la mémoire

Le VFS garde les octets **bruts** de chaque paquet CPK ouvert, pour éviter de le relire.
Quelques lectures dans des paquets différents suffisent donc à retenir plusieurs centaines de
mégaoctets — et **le budget par défaut de la bibliothèque native est de 16 Gio**, dimensionné
pour un traitement par lots qui a la machine pour lui.

Un jeu n'est pas dans ce cas. Posez votre plafond au démarrage :

```python
with Vfs() as vfs:
    vfs.regler_budget_cache(256 * 1024 * 1024)   # 256 Mio
    ...
    print(vfs.stats_cache())    # {'octets': …, 'entrees': …, 'budget': …}
    vfs.vider_cache()           # rend la RAM immédiatement
```

Vider est sans danger pour une lecture en cours : elle détient sa donnée jusqu'au bout. Les
lectures suivantes relisent depuis le disque — c'est le prix, assumé, de rendre la mémoire.

> `Vfs` prend la **racine**, et passe `<racine>/data` à la couche native. Lui donner
> directement le dossier `data` donne « impossible d'ouvrir cpk_list.cfg.bin », une erreur qui
> accuse le fichier.

Le montage « dump » n'indexe rien tant qu'on ne l'énumère pas : `lire()` résout par chemin,
mais `chercher()` et `parcourir()` construisent l'index — des minutes sur 255 000 entrées.

## Rendre les vrais assets

```python
from niepy import Rendu

r = Rendu()
r.capturer("data/common/…/menu.g4tx", "game/nie/images/menu.png")
r.capturer_region("atlas.g4tx", "icone_01", "game/nie/images/icone_01.png")
```

`nie-game` est atteint en **sous-processus**, jamais en process, et c'est délibéré : il n'a
pas de `lib.rs`, c'est un hôte wgpu. Charger un contexte GPU dans une bibliothèque elle-même
chargée par le Python de Ren'Py est une bonne façon d'obtenir des plantages illisibles. Le
dépôt applique déjà cette règle à la CLI Rust `nie`, pour la même raison.

Seuls les modes **hors-écran** sont exposés. `--window` et `--play` ouvrent une fenêtre et ne
rendent la main qu'à sa fermeture : les appeler depuis un jeu déjà lancé le bloquerait.

Le binaire se construit à part :

```bash
cargo build -p nie-game --release
```

## Lire les scènes — ce dont un VN a réellement besoin

Le jeu porte **5 173 scènes** réparties sur 45 chapitres, identifiées par une clé
`evNN_NNNNN`. Cette clé appaire des ressources dispersées dans quatre endroits du VFS :

| Ressource | Emplacement | Volume |
|---|---|---|
| Texte des dialogues | `data/common/text/<langue>/event/` | 44 241 fichiers |
| Scripts de scène | `data/common/event/` | 56 450 |
| Lipsync | `data/common/sound/<langue>/*.p3lip` | 21 047 |
| Sous-titres | `gamedata/event/subtitle/<langue>/` | ~1 400 |

```python
from niepy import Scenario, Vfs

with Vfs() as vfs:
    scenario = Scenario.indexer(vfs)     # parcourt le VFS une fois
    scenario.sauver("game/nie/scenes.json")   # …et ne le refait plus

    scene = scenario.scene("ev01_01700")
    lignes = scenario.lignes(scene, "fr", vfs)
```

> **Le texte existe en neuf langues, le doublage en deux.** Mesuré sur l'installation de
> référence : 3 973 scènes traduites en français, mais **zéro** doublée ; le japonais en
> double 2 989, l'anglais 538. Un VN qui suppose que toute langue jouable est doublée se
> trompera sur sept langues sur neuf — d'où `Scene.est_doublee` et `LANGUES_DOUBLEES`.

En ligne de commande :

```bash
uv run python -m niepy scenes --index game/nie/scenes.json          # index + chiffres
uv run python -m niepy scenes --out game/nie/scenes --langue fr     # export des répliques
uv run python -m niepy scenes --out … --chapitre ev01 --limite 50   # un chapitre seulement
```

## Le mode histoire — cinématiques, cartes, progression

```bash
uv run python -m niepy story --index game/nie/story.json   # index + chiffres
uv run python -m niepy story --cle ev60_01560              # détail d'une cinématique
uv run python -m niepy story --acteurs 10                  # les acteurs les plus présents
uv run python -m niepy story --out game/nie/story          # fiches JSON
```

Mesuré sur l'installation de référence : **1 735 cinématiques** (7 808 plans, 132 acteurs,
1 214 avec caméra), **889 cartes** (dont 153 avec navmesh) sur neuf zones, 9 tables globales
et **115 déclencheurs**, tous porteurs d'une table décodable.

Le liant d'une cinématique n'est ni l'acteur ni la prise, mais le **plan** — le suffixe
`_cNNNN`, seul élément quasi universel du nommage. La forme `<clé>_<acteur>_sNN_pNN_cNNNN`
ne couvre que **52,4 %** des noms ; s'y limiter perdrait la moitié du corpus, dont *toutes*
les caméras, qui ne portent ni acteur ni numéro de plan.

> **Deux limites à connaître.** Les `.g4cm` (caméras) et `.g4nv` (navmesh) sont indexés et
> localisés, mais leur décodage ne rend pour l'instant que l'en-tête — pas les trajectoires
> ni les polygones. Les `.lua.bin` des déclencheurs sont du Lua compilé, non décodé ; leur
> table `.cfg.bin` jumelle, elle, se lit (`Trigger.exploitable`).

## Alimenter un projet Ren'Py

D'abord produire les assets, depuis la CLI Rust :

```bash
# Les assets : voix, portraits, musique + catalogue.json. En Rust, car il faut lire les CPK.
nie vn export --out <projet-renpy>/game/nie

# Le .rpy qui les déclare, et les données du jeu en JSON. En Python, car c'est un artefact
# du monde Ren'Py.
uv run python -m niepy renpy --out <projet-renpy>/game/nie
uv run python -m niepy data  --out <projet-renpy>/game/nie/data
```

Les treize familles de `data` visent des **dossiers** du VFS, jamais des fichiers : les noms
du jeu portent un numéro de version (`chara_base_1.03.98.00.cfg.bin`) qui change à chaque
patch. Leur poids réel surprend — `menu` compte 3 866 fichiers et `event` pèse 14,7 Mo, quand
`item` et `team` en comptent 5 et 6. `--familles evenements,personnages` restreint l'export.

Puis, dans un `init python:` du projet :

```python
from niepy.renpy import Catalogue

catalogue = Catalogue.charger(config.gamedir + "/nie")
perso = catalogue.par_code("c01000010")
```

Le `.rpy` généré est **régénérable** : il ne contient aucune écriture à la main et peut être
réécrit à chaque export sans rien perdre.

## Tests

```bash
uv run --with pytest pytest -q tests/
```

Les tests du moteur ne touchent pas au VFS : ils tournent sans les données du jeu. Ceux du
pont Ren'Py travaillent sur un catalogue synthétique, hors moteur Ren'Py — c'est le seul moyen
d'attraper une erreur de chemin d'asset avant de lancer le jeu.

## Pourquoi `ctypes` et aucune dépendance

Ren'Py embarque son propre Python, où installer des roues tierces est une source d'ennuis sans
fin. `niepy` n'utilise donc que la bibliothèque standard : tout le travail réel est fait par la
couche Rust.

## RE anchors

Knowledge base (`var/nie.sqlite`) tables:
- `function` — 117 068 functions of `nie.exe`
- `coverage` — binary coverage rates
- `hash_name` — VFS and UI CRC32 name entries
- `pdata_func` — `.pdata` function entry boundaries

Key binary addresses:
- `0x1404ecd60` — Core character controller
- `0x1406d5840` — Core game tick loop
