# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

r"""Les six motifs de `core/glossary_build.py` réécrits contre leur forme d'origine.

## Pourquoi ce fichier existe

Les motifs lisaient la sortie d'un LLM en la rognant EN CHEMIN — `(.+?)\s*`, `(.{1,60}?)\s+`.
Cette écriture fait de `.` et de `\s` deux façons d'absorber le même espace : le moteur doit
essayer chaque partage avant de conclure, d'où un coût plus que linéaire en la longueur de la
ligne (`python:S8786`) — sur un texte dont rien ne borne la longueur.

Le rognage est passé en Python. Mais réécrire six expressions régulières « à l'œil » sur un
analyseur qui, lui, décide du contenu d'un glossaire, c'est exactement le genre de
changement qui se croit neutre. Ce fichier le PROUVE : chaque forme neuve est comparée à la
forme d'origine sur un corpus qui contient les cas réellement observés en production (ceux
que les commentaires du module citent) et leurs déformations — espaces multiples, tag absent,
flèche de chaque graphie, ligne vide, ligne géante.

⚠ Les motifs d'ORIGINE sont recopiés ici. C'est volontaire et ce n'est pas de la duplication :
ils sont la référence de comparaison, et les garder sous les yeux dit ce que la réécriture
devait préserver.
"""
from __future__ import annotations

import re

import pytest

from core import glossary_build as gb

# --- les formes d'ORIGINE, telles qu'elles étaient avant la réécriture ------------

_HEADER_AVANT = re.compile(r"^\s*#{1,6}\s*(.+?)\s*$")
_ANGL_SEP_AVANT = re.compile(r"\s*(?:→|=>|➔|⇒|->)\s*")
_ARROW_INTERDIT_AVANT = re.compile(
    r"^(.*?)\s*(?:→|=>|➔|⇒|->)\s*interdits?\s*:\s*(.*)$", re.I)
_NOM_TIRET_AVANT = re.compile(r"^(.{1,60}?)\s+[—–]\s+(.+)$")
_RENAME_ARROW_AVANT = re.compile(
    r"^(.+?)\s*(?:→|=>|➔|⇒|->)\s*(.+?)\s*(?:[\[\(]\s*([^\]\)]+?)\s*[\]\)])?\s*$")
_TAG_ONLY_AVANT = re.compile(r"^(.+?)\s*[\[\(]\s*([^\]\)]+?)\s*[\]\)]\s*$")

#: Lignes réellement rencontrées (citées par les commentaires du module) et leurs
#: déformations. Le corpus est commun aux six motifs : un motif doit se comporter
#: identiquement sur les lignes qui ne le concernent pas, pas seulement sur les siennes.
CORPUS = [
    "",
    "   ",
    "# Personnages",
    "###   Lieux et objets   ",
    "#Termes",
    "###### x",
    "Diablotin → diablotin [NE PAS TRADUIRE]",
    "Croyance → La Onzième Bête",
    "Homme-Bête [masculin]",
    "Gremian [masculin]",
    "Gremian (masculin)",
    "Leprechaun → interdits: lutin, farfadet",
    "Leprechaun→interdits:lutin",
    "Leprechaun   →   INTERDIT :   lutin ,  farfadet  ",
    "Roi-démon — Souverain des armées du gouffre",
    "Roi-démon   —   Souverain des armées du gouffre",
    "Kataphrakto – engin de guerre",
    "Feodor Jessman / Féodor",
    "vo => fr",
    "vo -> fr",
    "vo ➔ fr",
    "vo ⇒ fr",
    "un nom beaucoup trop long pour être un nom, qui dépasse largement les soixante "
    "caractères autorisés — et une description derrière",
    "A" * 300,
    "A" * 300 + " — " + "B" * 300,
    "Nom [tag] — description",
    "Nom (tag) → autre [masculin]",
    "Nom sans rien de particulier",
    "  Nom précédé d'espaces  ",
    "→ flèche en tête",
    "flèche en queue →",
    "[seulement un tag]",
    "(seulement un tag)",
    "Nom [tag non fermé",
    "Nom ] tag inversé [",
    "1972... et la suite",
    "Nom — ",
    " — description seule",
]


def _groupes(motif: re.Pattern, ligne: str):
    m = motif.match(ligne)
    return None if m is None else m.groups()


@pytest.mark.parametrize("ligne", CORPUS)
def test_le_motif_d_entete_est_inchange(ligne):
    """`_HEADER` ne rogne plus lui-même : `_header_to_cat` cherche des sous-chaînes dans une
    version minuscule, un espace en fin n'y change rien."""
    avant, apres = _groupes(_HEADER_AVANT, ligne), _groupes(gb._HEADER, ligne)
    if avant is None or apres is None:
        assert avant is None and apres is None, ligne
    else:
        assert [g.strip() for g in avant] == [g.strip() for g in apres], ligne


@pytest.mark.parametrize("ligne", CORPUS)
def test_le_decoupage_des_anglicismes_est_inchange(ligne):
    """`_ANGL_SEP` ne mange plus les espaces autour de la flèche ; les morceaux passent de
    toute façon par `_clean`, qui les rogne."""
    avant = [p.strip() for p in _ANGL_SEP_AVANT.split(ligne, maxsplit=1)]
    apres = [p.strip() for p in gb._ANGL_SEP.split(ligne, maxsplit=1)]
    assert avant == apres, ligne


@pytest.mark.parametrize("ligne", CORPUS)
def test_le_garde_fou_interdits_est_inchange(ligne):
    avant, apres = _groupes(_ARROW_INTERDIT_AVANT, ligne), _groupes(gb._ARROW_INTERDIT, ligne)
    if avant is None or apres is None:
        assert avant is None and apres is None, ligne
    else:
        assert [g.strip() for g in avant] == [g.strip() for g in apres], ligne


@pytest.mark.parametrize("ligne", CORPUS)
def test_le_garde_fou_nom_tiret_est_inchange(ligne):
    """`_NOM_TIRET` est devenu `_nom_et_description` : une recherche du séparateur, puis la
    borne de longueur vérifiée en Python."""
    m = _NOM_TIRET_AVANT.match(ligne)
    avant = (m.group(1).strip(), m.group(2).strip()) if m else None
    assert avant == gb._nom_et_description(ligne), ligne


@pytest.mark.parametrize("ligne", CORPUS)
def test_le_garde_fou_de_renommage_est_inchange(ligne):
    avant, apres = _groupes(_RENAME_ARROW_AVANT, ligne), _groupes(gb._RENAME_ARROW, ligne)
    if avant is None or apres is None:
        assert avant is None and apres is None, ligne
    else:
        assert [(g or "").strip() for g in avant] == [(g or "").strip() for g in apres], ligne


@pytest.mark.parametrize("ligne", CORPUS)
def test_le_retrait_de_tag_final_est_inchange(ligne):
    avant, apres = _groupes(_TAG_ONLY_AVANT, ligne), _groupes(gb._TAG_ONLY, ligne)
    if avant is None or apres is None:
        assert avant is None and apres is None, ligne
    else:
        assert [(g or "").strip() for g in avant] == [(g or "").strip() for g in apres], ligne


# --- la propriété que la réécriture achète ---------------------------------------

def test_aucun_motif_ne_rogne_plus_a_cote_d_un_quantificateur_sur_point():
    r"""LE garde-fou du lot. `(.+?)\s*`, `(.*?)\s*` et `(.{1,60}?)\s+` sont les trois formes
    qui faisaient concourir `.` et `\s` pour le même espace. Qu'aucune ne revienne."""
    interdits = re.compile(r"\((?:\.[+*]\?|\.\{\d+,\d+\}\?)\)\\s[*+]")
    for nom in ("_HEADER", "_ARROW_INTERDIT", "_RENAME_ARROW", "_TAG_ONLY", "_ANGL_SEP"):
        motif = getattr(gb, nom).pattern
        assert not interdits.search(motif), f"{nom} : {motif}"


def test_une_ligne_geante_sans_appariement_ne_part_pas_en_explosion():
    """La ligne pathologique : longue, pleine d'espaces, et qui n'appariera jamais. C'est
    exactement l'entrée sur laquelle la forme d'origine payait son partage."""
    import time
    ligne = "a " * 4000
    debut = time.perf_counter()
    for motif in (gb._HEADER, gb._ARROW_INTERDIT, gb._RENAME_ARROW, gb._TAG_ONLY):
        motif.match(ligne)
    gb._nom_et_description(ligne)
    assert time.perf_counter() - debut < 1.0
