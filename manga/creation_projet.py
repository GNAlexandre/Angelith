# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Créer un tome sous `sources/` — le geste que seul l'explorateur de fichiers savait faire.

## Le constat que ce module ferme

Le pipeline sait lire un dossier d'images, un `.cbz` et un `.cbr` depuis la 1.0.0. Ce qui
manquait n'était pas la lecture : c'était le **geste**. Un premier lancement affichait deux
listes vides et une ligne de journal expliquant comment fabriquer `sources/<Projet>/<Tome>/`
à la main, dans un autre logiciel. Ce module est ce que cette phrase décrivait.

Aucun Qt ici, et c'est la raison pour laquelle il vit dans `manga/` : la copie d'une archive de
400 Mo doit pouvoir tourner sur le fil de travail, et la validation d'un nom de dossier doit
se tester sans écran.

## Copier, et le dire

Les fichiers sont **copiés** dans `sources/`, jamais référencés. Un projet qui pointerait vers
un `.cbz` resté sur une clé USB casserait au premier débranchement, et toute l'arborescence du
pipeline — `resoudre_source`, `scan_volume`, `_est_tome_manga` — suppose que les planches sont
sous `sources/<Projet>/<Tome>/`. Un lien symbolique demanderait les droits administrateur sous
Windows, ce que rien d'autre dans ce dépôt n'exige.

Le coût est réel et se dit : `estimer_poids()` rend le total en octets avant de commencer, et
l'appelant l'annonce.

## La langue et le format

`<Tome>/<format>/<LANGUE>/` est l'arborescence complète que `sources_manga.resoudre_source`
accepte ; `<Tome>/<format>/` en est le repli, et c'est celui qu'on écrit par défaut — poser un
dossier `JAP/` alors que `manga.langue_source` vaut déjà `jp` n'apporte rien et ajoute un cran
à la profondeur. Le dossier de langue n'est créé que si on le demande explicitement, ce que
fait la boîte « Nouveau projet » quand la source n'est pas japonaise.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from core import config as core_config
from manga.ingest import IMG_EXTS
from manga.sources_manga import FORMATS

#: Archives reconnues comme un tome. Le même triplet que `manga.ingest.list_source_files`.
ARCHIVES: tuple[str, ...] = (".cbz", ".cbr", ".zip")

#: Noms de fichiers réservés par Windows, quelle que soit l'extension. Un dossier `CON` ne
#: peut PAS être créé, et l'erreur que l'OS rend (« paramètre incorrect ») n'apprend rien.
_RESERVES = frozenset({"con", "prn", "aux", "nul",
                       *(f"com{n}" for n in range(1, 10)),
                       *(f"lpt{n}" for n in range(1, 10))})

#: Caractères qu'aucun des deux systèmes de fichiers visés n'accepte dans un nom.
_INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ErreurCreation(Exception):
    """Un nom refusé ou une arborescence impossible. Porte un message destiné à être AFFICHÉ
    tel quel : c'est le seul retour que l'utilisateur aura."""


@dataclass
class Creation:
    """Ce qui a été écrit. `dossier` est celui où le pipeline ira lire les planches.

    `projet` et `tome` sont PORTÉS, pas redérivés du chemin : la profondeur varie selon qu'un
    dossier de langue a été demandé, et une remontée de deux ou trois crans selon le cas est
    exactement le genre de calcul qui finit par se tromper d'un."""

    projet: str
    tome: str
    dossier: Path
    fichiers: list[Path] = field(default_factory=list)
    octets: int = 0


def valider_nom(nom: str, quoi: str = "nom") -> str:
    """Rend le nom nettoyé, ou lève `ErreurCreation` avec la raison.

    ⚠ On refuse plutôt qu'on ne corrige. Remplacer silencieusement `Vol/1` par `Vol_1` créerait
    un tome que l'utilisateur ne retrouverait pas sous le nom qu'il a tapé — et le nom d'un
    tome finit dans `RAPPORT.md`, dans les métadonnées du CBZ et dans le nom du PDF."""
    propre = (nom or "").strip()
    if not propre:
        raise ErreurCreation(f"Le {quoi} ne peut pas être vide.")
    if _INTERDITS.search(propre):
        raise ErreurCreation(
            f"Le {quoi} « {nom} » contient un caractère interdit dans un nom de dossier "
            f"(< > : \" / \\ | ? *).")
    if propre != propre.rstrip(". "):
        raise ErreurCreation(f"Un {quoi} ne peut pas finir par un point ni une espace — "
                             f"Windows refuse de créer le dossier.")
    if propre.split(".", 1)[0].lower() in _RESERVES:
        raise ErreurCreation(f"« {propre} » est un nom réservé par Windows. Choisis-en un "
                             f"autre.")
    if len(propre) > 100:
        raise ErreurCreation(f"Le {quoi} dépasse 100 caractères — les chemins de checkpoints "
                             f"deviendraient trop longs pour Windows.")
    return propre


def racine_sources(config: dict) -> Path:
    """`sources/` tel que la section manga le déclare."""
    return Path(core_config.section(config, "manga", "chemins")["sources"])


def dossier_cible(config: dict, projet: str, tome: str, *, format: str = "manga",
                  langue: str | None = None) -> Path:
    """Où les planches seront écrites. Ne crée rien, ne valide rien : `preparer` fait les deux."""
    if format not in FORMATS:
        raise ErreurCreation(f"Format inconnu : « {format} ». Formats reconnus : "
                             f"{', '.join(FORMATS)}.")
    cible = racine_sources(config) / projet / tome / format
    return cible / langue.upper() if langue else cible


def lister_sources(chemins) -> list[Path]:
    """Les fichiers à copier, dans l'ordre de lecture, depuis ce qu'on a désigné.

    Accepte un mélange de dossiers, d'images et d'archives — c'est ce qu'un glisser-déposer
    produit. Un dossier est parcouru sur UN cran : `Tome/` et `Tome/manga/` sont les deux
    dispositions qu'on rencontre, descendre plus loin ramasserait des vignettes."""
    retenus: list[Path] = []
    for brut in chemins:
        chemin = Path(brut)
        if chemin.is_file():
            if _est_exploitable(chemin):
                retenus.append(chemin)
        elif chemin.is_dir():
            retenus.extend(_fichiers_du_dossier(chemin))
    return _sans_doublons(retenus)


def _est_exploitable(chemin: Path) -> bool:
    """Une image ou une archive — ce qu'un tome peut réellement ingérer."""
    return chemin.suffix.lower() in (*IMG_EXTS, *ARCHIVES)


def _fichiers_du_dossier(dossier: Path) -> list[Path]:
    """Le contenu exploitable d'un dossier, sur UN cran de profondeur.

    `Tome/` et `Tome/manga/` sont les deux dispositions qu'on rencontre. Le cran d'après
    n'est visité que si le dossier lui-même est vide de fichiers exploitables : descendre
    systématiquement ramasserait les vignettes que certaines archives déposent à côté."""
    from manga.ingest import natural_key

    def _tries(fichiers) -> list[Path]:
        return sorted((p for p in fichiers if p.is_file() and _est_exploitable(p)),
                      key=lambda p: natural_key(p.stem))

    plats = _tries(dossier.iterdir())
    if plats:
        return plats
    profonds: list[Path] = []
    for sous in sorted(p for p in dossier.iterdir() if p.is_dir()):
        profonds.extend(_tries(sous.iterdir()))
    return profonds


def _sans_doublons(chemins: list[Path]) -> list[Path]:
    """Dédoublonnage en gardant l'ordre : deux dossiers imbriqués lâchés ensemble
    ramèneraient deux fois les mêmes images, et le tome aurait 300 planches au lieu de 150."""
    vus, uniques = set(), []
    for chemin in chemins:
        cle = chemin.resolve()
        if cle not in vus:
            vus.add(cle)
            uniques.append(chemin)
    return uniques


def estimer_poids(fichiers) -> int:
    """Total en octets. Ce qu'on annonce AVANT de copier — une archive de webtoon pèse
    couramment plusieurs centaines de mégaoctets, et une copie muette de cette taille passe
    pour un gel."""
    total = 0
    for chemin in fichiers:
        try:
            total += Path(chemin).stat().st_size
        except OSError:
            continue
    return total


def poids_lisible(octets: int) -> str:
    """« 412 Mo ». Pour une boîte de dialogue, pas pour un rapport."""
    for seuil, unite in ((1 << 30, "Go"), (1 << 20, "Mo"), (1 << 10, "ko")):
        if octets >= seuil:
            return f"{octets / seuil:.1f} {unite}".replace(".0 ", " ")
    return f"{octets} o"


def preparer(config: dict, projet: str, tome: str, *, format: str = "manga",
             langue: str | None = None, ecraser: bool = False) -> Path:
    """Valide les noms, refuse d'écraser un tome existant, crée l'arborescence, rend le
    dossier de planches.

    ⚠ `ecraser=False` par défaut, et le refus est **explicite**. Créer « Vol.1 » sur un
    « Vol.1 » déjà traité mélangerait deux tomes dans le même `build/` sans que rien ne le
    dise : les checkpoints de l'ancien resteraient et l'aval s'alignerait par position sur des
    planches qui ne sont plus les mêmes. C'est exactement le mode de panne que
    `checkpoints.FORMAT_VERSION` existe pour éviter ailleurs."""
    projet = valider_nom(projet, "nom de projet")
    tome = valider_nom(tome, "nom de tome")
    cible = dossier_cible(config, projet, tome, format=format, langue=langue)
    if cible.exists() and not ecraser:
        existants = [p for p in cible.iterdir()
                     if p.is_file() and p.suffix.lower() in (*IMG_EXTS, *ARCHIVES)]
        if existants:
            raise ErreurCreation(
                f"{cible} contient déjà {len(existants)} planche(s) ou archive(s). "
                f"Choisis un autre nom de tome, ou vide ce dossier d'abord.")
    cible.mkdir(parents=True, exist_ok=True)
    return cible


def copier(fichiers, cible: Path, *, projet: str = "", tome: str = "",
           progres=None, deplacer: bool = False) -> Creation:
    """Copie les fichiers dans `cible`. **Appelée depuis le fil de travail, jamais l'affichage.**

    `progres(fait, total, nom)` est rappelé après chaque fichier — c'est ce qui distingue une
    copie de 400 Mo d'un gel.

    Les collisions de nom sont résolues par un suffixe numéroté plutôt que par un écrasement :
    deux dossiers sources peuvent tous deux porter `page_0001.png`, et perdre l'un des deux
    ferait un tome à trous que rien ne signalerait.

    ⚠ `deplacer=True` **vide le dossier d'origine**, et le défaut est `False` pour cette
    seule raison. Un import est le geste le plus facile à déclencher par accident de toute
    l'interface — un fichier lâché sur la fenêtre — et le rendre irréversible par défaut
    serait le pire choix possible. Le déplacement existe parce qu'un `.cbz` de 400 Mo recopié
    est 400 Mo de disque pour rien ; il ne s'obtient que par une case cochée à la main
    (`gui/depot_guide.py`)."""
    cible = Path(cible)
    cible.mkdir(parents=True, exist_ok=True)
    sources = [Path(f) for f in fichiers]
    total = len(sources)
    ecrits: list[Path] = []
    octets = 0
    for rang, source in enumerate(sources, 1):
        destination = cible / source.name
        suffixe = 1
        while destination.exists():
            destination = cible / f"{source.stem}_{suffixe}{source.suffix}"
            suffixe += 1
        if deplacer:
            # ⚠ `shutil.move` et non `Path.rename` : la source peut être sur un AUTRE volume
            # (une clé USB, un disque externe), où `rename` lève `OSError`. `move` retombe
            # alors sur une copie suivie d'une suppression, ce qui est le comportement
            # attendu et le seul qui marche.
            shutil.move(str(source), str(destination))
        else:
            shutil.copy2(source, destination)
        ecrits.append(destination)
        try:
            octets += destination.stat().st_size
        except OSError:
            pass
        if progres is not None:
            progres(rang, total, source.name)
    return Creation(projet=projet, tome=tome, dossier=cible, fichiers=ecrits, octets=octets)


def creer(config: dict, projet: str, tome: str, chemins, *, format: str = "manga",
          langue: str | None = None, progres=None,
          deplacer: bool = False) -> Creation:
    """Le geste complet : valider, préparer, copier. Rend ce qui a été écrit.

    Lève `ErreurCreation` si les noms sont refusés, si le tome existe déjà, ou si rien de
    lisible n'a été désigné — ce dernier cas est le plus fréquent en pratique (un dossier de
    `.psd`, un `.pdf`) et mérite un message plutôt qu'un tome vide."""
    fichiers = lister_sources(chemins)
    if not fichiers:
        raise ErreurCreation(
            "Aucune image ni archive lisible dans ce qui a été choisi. Attendu : des "
            f"{', '.join(IMG_EXTS)} ou un {', '.join(ARCHIVES)}.")
    projet = valider_nom(projet, "nom de projet")
    tome = valider_nom(tome, "nom de tome")
    cible = preparer(config, projet, tome, format=format, langue=langue)
    return copier(fichiers, cible, projet=projet, tome=tome, progres=progres,
                  deplacer=deplacer)
