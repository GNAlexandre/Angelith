# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que la bibliothèque des œuvres AFFICHE — les décisions, **sans Qt**.

Le pendant exact de `gui/pellicule.py` pour la destination « Œuvres » : les colonnes, les
filtres, les pastilles, la légende. `gui/oeuvres.py` ne fait que poser tout cela dans des
widgets.

## Pourquoi cette séparation existe, et ce qu'elle a corrigé

⚠ Elle n'est pas cosmétique. Ces fonctions étaient d'abord écrites dans `gui/oeuvres.py`, et
leurs tests — qui n'ont besoin d'aucun écran — étaient alors **impossibles à collecter** dans
le job de CI qui n'installe pas PySide6 : importer le module de test importait le panneau, donc
Qt. Mesuré le 2026-09-05 : la collecte s'arrêtait en erreur sur ce seul fichier.

C'est la règle de couche du dépôt, et la table de `gui/__init__.py` la nomme : « les tables »
et « les décisions » se testent sans qu'une dépendance graphique soit installée.

## Ce qui décide ici

- `COLONNES` — le tableau du `PLAN-34` L34.2, avec l'aide de chaque en-tête ;
- `FILTRES_BRIQUE` / `FILTRES_STATUT` — dans le vocabulaire de `manga/serie.py`, celui que
  `run_manga.py --list` imprime déjà ;
- `pastilles` et `detail_avancement` — **un CARACTÈRE par étape, et l'infobulle qui la nomme**.
  L'état ne se dit jamais par la couleur seule (`PLAN-34` critère 10, lot 19) ;
- `retenu` — le triple filtre.
"""
from __future__ import annotations

import time

import bibliotheque as biblio

#: Colonnes, dans l'ordre. Le tableau du `PLAN-34` L34.2, moins « Gestes » — les gestes sont
#: des boutons sous la liste plutôt que dans chaque ligne : dix-huit lignes × quatre boutons
#: seraient soixante-douze cibles de clic pour un panneau qu'on lit d'abord.
COLONNES: tuple[tuple[str, str], ...] = (
    ("Œuvre / Tome", "Le dossier de sources/, puis ses tomes dans l'ordre de lecture."),
    ("Brique", "Manga · Webtoon · Light novel · Scan (bêta), déduite de l'arborescence. "
               "Un tome peut en porter deux."),
    ("Unités", "Planches, bandes, chapitres ou pages — l'unité dépend de la brique, et la "
               "colonne la nomme. « ? » = non dénombrable sans extraction."),
    ("Avancement", "Une pastille par étape, dans l'ordre d'exécution. Voir la légende."),
    ("Sorties", "Les formats PRÉSENTS SUR LE DISQUE. Ce qui n'est pas là n'est pas listé."),
    ("Glossaire", "Entrées du glossaire de l'ŒUVRE — partagé par tous ses tomes."),
    ("Dernier run", "Date de la dernière écriture vue dans le cache du tome."),
)

#: Filtres de brique proposés. « Toutes » d'abord : c'est l'état d'ouverture.
FILTRES_BRIQUE: tuple[tuple[str, str], ...] = (
    ("", "Toutes les briques"),
    *((code, biblio.LIBELLES_BRIQUE[code]) for code in biblio.BRIQUES),
)

#: Filtres d'état, exprimés dans le vocabulaire de `manga/serie.py` — le même que celui de
#: `run_manga.py --list`, pour qu'un utilisateur qui connaît la console retrouve ses mots.
FILTRES_STATUT: tuple[tuple[str, str], ...] = (
    ("", "Tous les états"),
    ("a_faire", "À traiter (non traité ou partiel)"),
    ("a_relettrer", "À relettrer (rendu périmé)"),
    ("termine", "Terminés"),
    ("sans_source", "Sans source"),
)


def symbole(etat: str) -> str:
    for code, marque, _ in biblio.LEGENDE_ETATS:
        if code == etat:
            return marque
    return "?"


def pastilles(info) -> str:
    """« ●●●●●●● » — une pastille par étape, dans l'ordre d'exécution de la brique."""
    return "".join(symbole(info.etapes.get(etape, biblio.ABSENTE))
                   for etape in biblio.etapes_de_brique(info.brique))


def detail_avancement(info) -> str:
    """L'infobulle d'une ligne : chaque étape NOMMÉE avec son état, en toutes lettres.

    ⚠ C'est ce qui rend les pastilles lisibles sans la couleur ET sans la légende — un lecteur
    d'écran lit cette chaîne, pas la suite de ronds."""
    lignes = [f"{info.projet} / {info.tome} — {info.libelle_brique}", info.compte, ""]
    lignes += [f"{etape} : {info.etapes.get(etape, biblio.ABSENTE)}"
               for etape in biblio.etapes_de_brique(info.brique)]
    if info.perimees:
        lignes += ["", f"{len(info.perimees)} planche(s) à relettrer : "
                       + ", ".join(str(n) for n in info.perimees[:12])
                       + (" …" if len(info.perimees) > 12 else "")]
    if info.detail:
        lignes += ["", info.detail]
    return "\n".join(lignes)


def texte_legende() -> str:
    """La légende, en toutes lettres. Sans Qt : la console la dit avec les mêmes mots."""
    return "   ".join(f"{marque} {code} — {sens}" for code, marque, sens
                      in biblio.LEGENDE_ETATS)


def retenu(info, brique: str, statut: str, recherche: str) -> bool:
    """Le triple filtre, **en Python nu** : c'est une décision, donc ça se teste sans écran.

    ⚠ Le filtre de brique regarde `briques`, pas `brique` : un tome qui porte à la fois du
    manga et du scan doit apparaître sous les deux, sans quoi filtrer sur « Scan » ferait
    disparaître le seul tome du corpus qui en porte un aux côtés de ses planches."""
    if brique and brique not in (info.briques or (info.brique,)):
        return False
    if statut == "a_faire" and info.statut not in ("non_traite", "partiel"):
        return False
    if statut and statut != "a_faire" and info.statut != statut:
        return False
    if recherche:
        cible = f"{info.projet} {info.tome}".lower()
        if recherche.lower() not in cible:
            return False
    return True


def date_lisible(valeur: float | None) -> str:
    """Un `mtime` en date lisible, ou « — ». **Jamais une heure** : la colonne dit quand le
    tome a bougé pour la dernière fois, pas à quelle minute."""
    return time.strftime("%Y-%m-%d", time.localtime(valeur)) if valeur else "—"
