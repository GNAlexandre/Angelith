# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Fusion d'un bloc de configuration avec ses défauts — **un seul point**, pour la brique.

## Le défaut que ce module corrige

Sept endroits de `manga/` écrivaient la même ligne :

    c = {**_DEFAUTS, **(cfg or {})}

Elle a un trou : `**cfg` recouvre les défauts **par toutes les clés présentes**, y compris
celles dont la valeur est `None`. Or `None` est la façon normale d'écrire « laisse le défaut »
en YAML — `fenetre_hauteur:` seul, ou `fenetre_hauteur: null`, produisent exactement ça. Le
défaut est alors remplacé par `None`, et le premier `int()` lève :

    manga.detection.fenetre_hauteur: null   →  TypeError: int() argument must be… not 'NoneType'

Ce n'est pas théorique : c'est la seule syntaxe qu'un utilisateur peut deviner pour neutraliser
une clé, et elle plante le run à la première planche allongée.

## Pourquoi la double garde, et pas seulement le filtre `None`

Deux motifs corrects existaient déjà dans la brique, et **ils ne sont pas équivalents** :

· `bubbles_split._cfg` — `if cle in out and val is not None` : clé connue **et** valeur non
  nulle ;
· `clean._cfg` — `if v is not None` seul, sans filtre de clé.

C'est le plus strict qui est généralisé ici. Le filtre de clé n'est pas de la coquetterie :
`BubbleDetector` passe le bloc `manga.detection` **entier** à `fenetres()` (cf. `fenetrage`),
qui n'en connaît que trois clés. Sans filtre, `c` transporte `model_path`, `providers` et le
reste — inoffensif tant qu'on ne lit que ce qu'on connaît, et un piège dès qu'on itère.

⚠ **Une clé inconnue est ignorée en silence, et c'est voulu.** La validation du schéma est
l'affaire de `core/config_schema.py`, qui signale les clés inconnues **une fois, au démarrage**,
avec leur chemin complet. La refaire ici la ferait crier sept fois par planche.
"""
from __future__ import annotations


def fusion(defauts: dict, cfg: dict | None) -> dict:
    """Les `defauts`, recouverts par `cfg` — **clés connues et valeurs non nulles seulement**.

    `cfg=None`, `cfg={}`, `{clé: None}` et `{clé_inconnue: …}` rendent tous les défauts
    intacts. C'est la propriété qui compte : rien de ce qu'un fichier de configuration peut
    contenir ne doit pouvoir faire disparaître un défaut sans le remplacer.

    Les défauts ne sont jamais mutés — l'appelant en garde souvent un module-level."""
    out = dict(defauts)
    for cle, val in (cfg or {}).items():
        if cle in out and val is not None:
            out[cle] = val
    return out
