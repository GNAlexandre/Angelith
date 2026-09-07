# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Glossaire MULTI-CIBLES : un même terme source, un rendu par langue de sortie.

## Le problème

Le schéma du glossaire n'a qu'UN emplacement pour le rendu — `nom` — et rien n'y dit dans
quelle langue il est écrit. Tant que le projet ne produisait que du français, c'était sans
conséquence. Depuis les packs de langue cible, deux tomes de la même œuvre traduits vers deux
langues se disputent le même champ : le second écrase le premier, en silence.

## La forme sur disque

    personnages:
      - termes_source: [魔王]
        description: Souverain des armées du gouffre.
        cibles:
          fr: {nom: Roi-démon, pluriel: Rois-démons, genre: masculin, force: true}
          en: {nom: Demon King, genre: '?'}

Ce qui vit sous `cibles.<code>` est ce qui **décrit le rendu** : `nom`, `pluriel`, `genre`,
`variantes`, `interdits`, `force`. Un « genre masculin » ne dit rien de l'anglais, et une
forme interdite en français n'est pas interdite en anglais.

Ce qui reste au niveau de l'entrée décrit **l'entité elle-même**, indépendamment de la langue :
`termes_source` (la graphie d'origine), `traduire`, `role`, `description`, `a_romaniser`.

⚠ `description` est partagée alors qu'elle est rédigée en français. C'est un choix : la
dupliquer par langue ferait démarrer chaque nouvelle cible avec **zéro** description, et une
description française est plus utile au modèle qu'une absence.

## Pourquoi la conversion se fait dans `load` / `save`, et nulle part ailleurs

71 endroits du dépôt lisent `e["nom"]`, `e["genre"]`, `e["variantes"]`… Les réécrire serait un
diff énorme pour un gain nul, et surtout une occasion de se tromper 71 fois.

`load(path, cible)` rend donc la forme **PLATE** — exactement l'ancienne — pour la cible
demandée, et `save(glossaire, path, cible)` la refond dans le fichier multi-cibles **sans
toucher aux autres langues**. Le reste du code ne voit jamais `cibles`.

C'est aussi ce qui rend la migration sûre : elle n'a qu'un point d'entrée.
"""
from __future__ import annotations

#: Champs qui décrivent le RENDU, donc propres à une langue cible.
CHAMPS_CIBLE = ("nom", "pluriel", "genre", "variantes", "interdits", "force")

#: Champs qui décrivent l'ENTITÉ, partagés par toutes les cibles.
CHAMPS_PARTAGES = ("termes_source", "traduire", "role", "description", "a_romaniser")

#: Clé du bloc multi-cibles dans une entrée.
#:
#: ⚠ C'est le SEUL marqueur de format, et il est structurel : aucun numéro de version n'est
#: écrit dans le fichier. Un fichier converti se reconnaît à ses entrées qui portent `cibles`,
#: rien d'autre — cf. `est_multi`.
CLE_CIBLES = "cibles"


def est_multi(entree: dict) -> bool:
    """L'entrée est-elle déjà au format multi-cibles ?"""
    return isinstance(entree, dict) and isinstance(entree.get(CLE_CIBLES), dict)


def aplatir(entree: dict, cible: str) -> dict:
    """Vue PLATE d'une entrée pour une cible — la forme que tout le dépôt attend.

    Une entrée qui n'a pas de rendu dans cette cible rend quand même ses champs partagés et
    un `nom` VIDE. C'est délibéré : la faire disparaître priverait le terminologue de la
    graphie source déjà relevée, et il la re-relèverait au tome suivant.
    """
    if not est_multi(entree):
        return dict(entree)
    plat = {k: v for k, v in entree.items() if k != CLE_CIBLES}
    rendu = entree[CLE_CIBLES].get(cible) or {}
    plat.update({k: v for k, v in rendu.items() if k in CHAMPS_CIBLE})
    plat.setdefault("nom", "")
    return plat


def fusionner(entree_disque: dict | None, plate: dict, cible: str) -> dict:
    """Refond une entrée plate dans sa forme multi-cibles, **sans toucher aux autres langues**.

    ⚠ C'est l'invariant qui fait tout tenir : traduire un tome vers l'anglais ne doit pas
    effacer le travail fait en français. `entree_disque` est ce que le fichier portait ; seul
    le sous-arbre `cibles[cible]` est réécrit."""
    base = dict(entree_disque) if est_multi(entree_disque) else {}
    cibles = dict(base.get(CLE_CIBLES) or {})

    partages = {k: plate[k] for k in CHAMPS_PARTAGES if k in plate}
    rendu = {k: plate[k] for k in CHAMPS_CIBLE if k in plate}

    # Une entrée sans aucun rendu dans cette cible ne crée pas un bloc vide : elle
    # attendrait alors une traduction qui n'a jamais été demandée.
    if any(rendu.get(k) for k in ("nom", "pluriel", "variantes", "interdits")):
        cibles[cible] = rendu
    elif cible in cibles:
        cibles[cible] = rendu

    sortie = {k: v for k, v in base.items() if k not in (CLE_CIBLES,)}
    sortie.update(partages)
    sortie[CLE_CIBLES] = cibles
    return sortie


def migrer_entree(entree: dict, cible: str) -> dict:
    """Une entrée PLATE de l'ancien format → multi-cibles, sous `cible`.

    Aucune perte : les champs de rendu descendent sous `cibles[cible]`, les autres restent où
    ils sont. Idempotente — une entrée déjà migrée est rendue telle quelle."""
    if est_multi(entree):
        return dict(entree)
    return fusionner(None, entree, cible)


def migrer(glossaire: dict, cible: str) -> tuple[dict, int]:
    """Migre tout un glossaire. Rend `(glossaire, nombre d'entrées migrées)`.

    Les catégories sans entités (`anglicismes`, `groupes`) ne portent pas de rendu par langue
    et sont laissées intactes."""
    from .glossary import ENTITY_CATS

    sortie, n = {}, 0
    for cat, entrees in (glossaire or {}).items():
        if cat not in ENTITY_CATS or not isinstance(entrees, list):
            sortie[cat] = entrees
            continue
        migrees = []
        for e in entrees:
            if isinstance(e, dict) and not est_multi(e):
                n += 1
                migrees.append(migrer_entree(e, cible))
            else:
                migrees.append(e)
        sortie[cat] = migrees
    return sortie, n


def besoin_de_migration(glossaire: dict) -> bool:
    """Le fichier porte-t-il au moins une entrée à l'ancien format ?"""
    from .glossary import ENTITY_CATS

    for cat, entrees in (glossaire or {}).items():
        if cat not in ENTITY_CATS or not isinstance(entrees, list):
            continue
        if any(isinstance(e, dict) and not est_multi(e) for e in entrees):
            return True
    return False


def cibles_presentes(glossaire: dict) -> list[str]:
    """Codes de langue pour lesquels ce glossaire porte au moins un rendu."""
    from .glossary import ENTITY_CATS

    vues: set[str] = set()
    for cat, entrees in (glossaire or {}).items():
        if cat not in ENTITY_CATS or not isinstance(entrees, list):
            continue
        for e in entrees:
            if est_multi(e):
                vues.update(k for k, v in e[CLE_CIBLES].items() if v)
    return sorted(vues)
