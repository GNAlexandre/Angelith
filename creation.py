# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Créer un projet — **pour les trois dispositions du dépôt**, pas seulement le manga.

## Le manque que ce module ferme

`manga/creation_projet.py` est le seul module du dépôt qui écrive sous `sources/`, et il ne
connaît que `manga` et `webtoon` (`manga/sources_manga.py:FORMATS`). **Aucune fonction, nulle
part, ne savait créer l'arborescence d'un light novel** — `sources/<Projet>/<Tome>/<LANGUE>/` —
alors que c'est la brique historique du projet. `app.py` se contentait de dire à l'utilisateur
de faire le dossier à la main :

    console.print(f"Crée un dossier sous [cyan]{src}/[/] (ex. {src}/Mon LN/Vol.1/ENG/…)")

C'est exactement le « geste manquant » que `manga/creation_projet.py` avait comblé pour le
manga, et qui restait béant pour le roman.

## ⚠ Pourquoi ce module vit à la RACINE

Même précédent que `bibliotheque.py`, et pour la même raison mesurée au lot 34 : **l'agrégateur
de plusieurs briques vit au-dessus d'elles, pas dans `core/`**. Deux tests l'interdisent
(`tests/test_imports_briques.py`) — `core` n'importe aucune brique, sous peine de cycle.

`manga/creation_projet.py` **reste** et continue de fonctionner : ce module-ci s'appuie sur ses
primitives (validation des noms, préparation, copie hors fil d'affichage, refus d'écrasement)
plutôt que de les réécrire. Rien de ce qui l'importe ne bouge.

## Les deux dispositions, et pourquoi elles diffèrent

| Disposition | Arborescence | Ce qu'elle accepte |
|---|---|---|
| `manga`, `webtoon` | `<Tome>/<format>[/<LANGUE>]` | images, `.cbz`, `.cbr`, `.zip` |
| `light_novel` | `<Tome>/<LANGUE>` — **sans le cran `<format>`** | `.docx`, `.pdf`, `.epub`, `.txt`, `.md` |

⚠ **Le light novel n'a pas de cran de format**, et ce n'est pas un oubli de symétrie :
`pipeline/sources.py` documente `sources/<Projet>/<Tome>/<ENG|JAP|ESP|CHINOIS|FR>/` et son
`_langues_presentes()` fait un `iterdir()` sur le dossier du tome. Y insérer un `light_novel/`
rendrait le tome invisible au pipeline qui doit le lire.

⚠ **Et la langue y est OBLIGATOIRE**, alors qu'elle est facultative pour le manga. Un tome de
roman sans dossier de langue n'est lisible par personne : `scan_volume` cherche des langues, pas
des fichiers à plat.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core import config as core_config
from manga.creation_projet import (Creation, ErreurCreation, copier, estimer_poids,
                                   poids_lisible, valider_nom)
from manga.creation_projet import lister_sources as _lister_manga

#: Les codes de langue que `pipeline/sources.py` reconnaît, dans l'ordre où l'interface les
#: propose. ⚠ Ce sont des NOMS DE DOSSIER, pas des codes ISO : c'est ce que le dépôt écrit
#: depuis toujours, et les renommer invaliderait tout le corpus.
LANGUES_LN: tuple[str, ...] = ("JAP", "ENG", "CHINOIS", "ESP", "FR")

#: Ce qu'un tome de light novel peut réellement ingérer — `pipeline/sources.py:127`.
EXTENSIONS_LN: tuple[str, ...] = (".docx", ".pdf", ".epub", ".txt", ".md")

#: Les identifiants de disposition. ⚠ `manga` et `webtoon` sont des FORMATS de la brique manga
#: (`--format webtoon` du même orchestrateur) ; `light_novel` est une brique. Le mot
#: « disposition » désigne ce qu'ils ont en commun — une façon de ranger des fichiers — sans
#: prétendre qu'ils sont de même nature.
MANGA = "manga"
WEBTOON = "webtoon"
LIGHT_NOVEL = "light_novel"

#: Les dispositions qui acceptent des PLANCHES. ⚠ C'est ce que le dépôt guidé propose : un
#: lâcher d'images ou d'archive ne peut pas être un roman, et lui offrir « Light novel »
#: serait proposer une impasse. `gui/depot.py` classe d'ailleurs les deux familles séparément.
FORMATS_PLANCHES: tuple[str, ...] = (MANGA, WEBTOON)


@dataclass(frozen=True)
class Disposition:
    """Comment une brique range ses sources, et ce qu'elle accepte.

    `cran_de_format` — le nom du dossier inséré entre le tome et la langue. Vide pour le light
    novel, dont `pipeline/sources.py` lit les langues **directement** sous le tome.
    `langue_obligatoire` — un tome de roman sans dossier de langue n'est lisible par personne.
    """

    identifiant: str
    libelle: str
    cran_de_format: str
    extensions: tuple[str, ...]
    langue_obligatoire: bool = False
    langues: tuple[str, ...] = ()

    def cible(self, racine: Path, projet: str, tome: str, langue: str | None) -> Path:
        chemin = racine / projet / tome
        if self.cran_de_format:
            chemin = chemin / self.cran_de_format
        return chemin / langue.upper() if langue else chemin


DISPOSITIONS: dict[str, Disposition] = {
    MANGA: Disposition(
        MANGA, "Manga (planches paginées)", MANGA,
        (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".cbz", ".cbr", ".zip")),
    WEBTOON: Disposition(
        WEBTOON, "Webtoon (bandes verticales)", WEBTOON,
        (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".cbz", ".cbr", ".zip")),
    LIGHT_NOVEL: Disposition(
        LIGHT_NOVEL, "Light novel (roman)", "", EXTENSIONS_LN,
        langue_obligatoire=True, langues=LANGUES_LN),
}


def disposition(identifiant: str) -> Disposition:
    if identifiant not in DISPOSITIONS:
        raise ErreurCreation(
            f"Disposition inconnue : « {identifiant} ». Connues : "
            f"{', '.join(DISPOSITIONS)}.")
    return DISPOSITIONS[identifiant]


def racine_sources(config: dict, quelle: str) -> Path:
    """`sources/` tel que la brique concernée le déclare.

    ⚠ Le light novel lit `chemins.sources` à la RACINE de `config.yaml` ; le manga lit
    `manga.chemins.sources`, qui en hérite profondément. Les confondre ferait écrire le roman
    dans le dossier du manga sur une installation qui les a séparés."""
    if quelle == LIGHT_NOVEL:
        return Path((config.get("chemins") or {})["sources"])
    return Path(core_config.section(config, "manga", "chemins")["sources"])


def lister_sources(chemins, quelle: str) -> list[Path]:
    """Les fichiers à copier, filtrés par ce que la disposition accepte.

    ⚠ Pour le manga, on délègue à `manga.creation_projet.lister_sources` **sans le
    réimplémenter** : il sait descendre d'un cran, dédoublonner et trier dans l'ordre de
    lecture, et son comportement est gelé par des tests depuis le lot 18."""
    if quelle != LIGHT_NOVEL:
        return _lister_manga(chemins)
    extensions = disposition(quelle).extensions
    retenus: list[Path] = []
    for brut in chemins:
        chemin = Path(brut)
        if chemin.is_file() and chemin.suffix.lower() in extensions:
            retenus.append(chemin)
        elif chemin.is_dir():
            # Un cran, comme pour le manga : `Tome/` et `Tome/ENG/` sont les deux dispositions
            # qu'on rencontre. Descendre plus loin ramasserait des sauvegardes.
            retenus.extend(sorted(p for p in chemin.iterdir()
                                  if p.is_file() and p.suffix.lower() in extensions))
            for sous in sorted(p for p in chemin.iterdir() if p.is_dir()):
                retenus.extend(sorted(p for p in sous.iterdir()
                                      if p.is_file() and p.suffix.lower() in extensions))
    vus: set[Path] = set()
    uniques: list[Path] = []
    for chemin in retenus:
        resolu = chemin.resolve()
        if resolu not in vus:
            vus.add(resolu)
            uniques.append(chemin)
    return uniques


def dossier_cible(config: dict, projet: str, tome: str, *, quelle: str = MANGA,
                  langue: str | None = None) -> Path:
    """Où les fichiers seront écrits. Ne crée rien, ne valide rien — `preparer` fait les deux."""
    dispo = disposition(quelle)
    if dispo.langue_obligatoire and not langue:
        raise ErreurCreation(
            f"{dispo.libelle} : une langue source est obligatoire. Un tome de roman sans "
            f"dossier de langue n'est lisible par aucune brique — `pipeline/sources.py` "
            f"cherche des dossiers de langue directement sous le tome. "
            f"Langues reconnues : {', '.join(dispo.langues)}.")
    return dispo.cible(racine_sources(config, quelle), projet, tome, langue)


def preparer(config: dict, projet: str, tome: str, *, quelle: str = MANGA,
             langue: str | None = None, ecraser: bool = False) -> Path:
    """Valide les noms, refuse d'écraser, crée le dossier. Rend la cible.

    ⚠ **Le refus d'écrasement est le garde-fou qui compte** : un tome existant porte
    potentiellement des heures de travail, et une création qui l'écraserait silencieusement
    serait irréversible."""
    projet = valider_nom(projet, "nom de projet")
    tome = valider_nom(tome, "nom de tome")
    if langue:
        valider_nom(langue, "langue source")
    cible = dossier_cible(config, projet, tome, quelle=quelle, langue=langue)
    if cible.exists() and any(cible.iterdir()) and not ecraser:
        raise ErreurCreation(
            f"{cible} existe déjà et n'est pas vide. Choisis un autre nom de tome, ou "
            f"ajoute les fichiers à la main : rien n'est écrasé ici.")
    cible.mkdir(parents=True, exist_ok=True)
    return cible


def creer(config: dict, projet: str, tome: str, chemins, *, quelle: str = MANGA,
          langue: str | None = None, progres=None, deplacer: bool = False) -> Creation:
    """Le geste complet : valider, préparer, copier. Rend ce qui a été écrit.

    ⚠ Le message d'échec nomme ce qui était attendu. Le cas le plus fréquent n'est pas un nom
    refusé, c'est un dossier qui ne contient rien de lisible — un `.psd` pour du manga, un
    `.jpg` pour un roman — et « aucun fichier lisible » sans dire lesquels oblige à deviner."""
    dispo = disposition(quelle)
    fichiers = lister_sources(chemins, quelle)
    if not fichiers:
        raise ErreurCreation(
            f"Aucun fichier lisible pour « {dispo.libelle} » dans ce qui a été choisi. "
            f"Attendu : {', '.join(dispo.extensions)}.")
    cible = preparer(config, projet, tome, quelle=quelle, langue=langue)
    return copier(fichiers, cible, projet=valider_nom(projet, "nom de projet"),
                  tome=valider_nom(tome, "nom de tome"), progres=progres, deplacer=deplacer)


__all__ = ["DISPOSITIONS", "EXTENSIONS_LN", "FORMATS_PLANCHES", "LANGUES_LN", "LIGHT_NOVEL", "MANGA", "WEBTOON",
           "Creation", "Disposition", "ErreurCreation", "copier", "creer", "disposition",
           "dossier_cible", "estimer_poids", "lister_sources", "poids_lisible", "preparer",
           "racine_sources", "valider_nom"]
