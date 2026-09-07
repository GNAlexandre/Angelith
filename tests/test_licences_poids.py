# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Une seule source de vérité pour les licences de poids — lot 38.

## Le défaut que ce fichier ferme, et il était affiché à l'utilisateur

Le dépôt disait **trois choses différentes** sur le détecteur de BULLES, relevé le 2026-09-06 :

| Source | Ce qu'elle disait |
|---|---|
| `manga_models/README.md` | GPL-3.0, déclarée sur la page du modèle (relevé le 2026-08-25) |
| `manga/reparations.py` | AGPL-3.0 (export YOLOv8-seg ; Ultralytics YOLOv8 est AGPL-3.0) |
| `gui/sondes.py`, `manga/doctor.py` | **GPL-3.0 + Manga109-s** |

La troisième était **fausse** : Manga109-s concerne le détecteur de **texte sur le dessin**
(`mayocream/comic-text-detector`), pas celui des bulles (`kitsumed/yolov8m_seg-speech-bubble`).
Les deux premières ne se contredisent pas — elles ne répondent pas à la même question — mais
aucune ne portait sa date à l'écran.

C'est plus grave qu'une incohérence de commentaire : ces phrases sont **affichées à quelqu'un
qui s'apprête à télécharger un fichier sous une licence qui n'est pas celle du projet**, et à
qui l'on demande ensuite de ne pas rediffuser ses planches sans vérifier. Une licence fausse
affichée est pire qu'une licence absente.

⚠ **Ce fichier ne vérifie pas que les licences sont JUSTES** — aucun test ne peut lire une page
Hugging Face. Il vérifie qu'elles sont **dites à un seul endroit**, et que le mot « Manga109 »
ne réapparaît pas à côté du détecteur de bulles.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from manga import models

RACINE = Path(__file__).resolve().parent.parent

#: Les modules qui AFFICHENT une licence de poids à l'utilisateur. Ils doivent la lire, pas la
#: réécrire. ⚠ `manga_models/README.md` n'y est pas : c'est un document de référence daté, qui
#: explique d'où vient la mesure — pas un texte d'interface.
MODULES_QUI_AFFICHENT = (
    "manga/reparations.py",
    "gui/sondes.py",
    "gui/dialogues.py",
    "manga/doctor.py",
)


def _source(relatif: str) -> str:
    return (RACINE / relatif).read_text(encoding="utf-8")


def _code_seul(relatif: str) -> str:
    """Le code du module, **docstrings et commentaires exclus**.

    ⚠ Indispensable, et c'est la règle §5 bis qui l'impose : ces modules DOIVENT porter un bloc
    daté qui lève l'ancienne affirmation — « la phrase qui était ici disait *le détecteur en
    place est GPL-3.0 + Manga109-s*, c'était faux ». Un test qui lirait le texte brut échouerait
    sur l'explication du correctif, c'est-à-dire punirait d'avoir écrit pourquoi. Même remède
    que `tests/test_installation_chemins.py`, et pour la même raison.

    `ast.unparse` d'un arbre privé de ses docstrings ne rend que des instructions : les
    commentaires ne survivent pas à l'analyse, les docstrings sont retirées à la main."""
    arbre = ast.parse(_source(relatif))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)) and ast.get_docstring(noeud):
            noeud.body = noeud.body[1:] or [ast.Pass()]
    return ast.unparse(arbre)


# --------------------------------------------------------------------------- #
#  La source unique
# --------------------------------------------------------------------------- #

def test_manga_models_porte_les_trois_licences():
    for nom in ("DETECTEUR_LICENCE", "TEXTE_LICENCE", "OCR_LICENCE"):
        valeur = getattr(models, nom, "")
        assert valeur and isinstance(valeur, str), nom


def test_chaque_licence_porte_sa_source_ou_sa_date():
    """Règle des chiffres, appliquée à une licence : « une affirmation sans sa source et sa
    date n'est pas une licence, c'est une impression »."""
    for nom in ("DETECTEUR_LICENCE", "TEXTE_LICENCE"):
        valeur = getattr(models, nom)
        assert re.search(r"relevé le \d{4}-\d{2}-\d{2}", valeur), (nom, valeur)


def test_chaque_licence_a_son_url():
    for nom in ("DETECTEUR_LICENCE_URL", "TEXTE_LICENCE_URL", "OCR_LICENCE_URL"):
        assert getattr(models, nom, "").startswith("https://"), nom


# --------------------------------------------------------------------------- #
#  ⚠ LE test du lot : Manga109-s n'est pas au détecteur de bulles
# --------------------------------------------------------------------------- #

def test_manga109_n_est_pas_dans_la_licence_du_detecteur_de_bulles():
    """L'affirmation qui était fausse, refusée à la source."""
    for nom in ("DETECTEUR_LICENCE", "DETECTEUR_LICENCE_NOTE"):
        assert "manga109" not in getattr(models, nom).lower(), nom


def test_manga109_est_bien_dans_la_licence_du_detecteur_de_texte():
    """Le test miroir. Sans lui, supprimer Manga109-s partout ferait passer le précédent au
    vert sur un dépôt qui aurait cessé de dire une condition d'usage réelle."""
    assert "manga109" in models.TEXTE_LICENCE.lower()


@pytest.mark.parametrize("relatif", MODULES_QUI_AFFICHENT)
def test_aucun_module_d_affichage_ne_reecrit_manga109(relatif):
    """⚠ Le mot ne doit plus apparaître dans le CODE de ces modules — c'est-à-dire dans une
    chaîne que quelqu'un finira par lire à l'écran.

    Les docstrings et les commentaires sont exemptés, et ce n'est pas une échappatoire : la
    règle §5 bis EXIGE qu'un bloc daté y explique ce qui a été corrigé. Cf. `_code_seul`."""
    lignes = [ln for ln in _code_seul(relatif).splitlines() if "manga109" in ln.lower()]
    assert not lignes, (relatif, lignes)


@pytest.mark.parametrize("relatif", MODULES_QUI_AFFICHENT)
def test_aucun_module_d_affichage_ne_reecrit_une_licence_en_dur(relatif):
    """Une licence recopiée est une licence qui divergera. Ces quatre modules doivent la LIRE.

    ⚠ Ce test aurait échoué avant le lot : `manga/reparations.py` portait quatre chaînes
    `licence=` littérales, et `gui/dialogues.py` récitait la liste des trois poids à la main."""
    corps = _code_seul(relatif)
    # Les licences des POIDS, pas celle du programme : `AGPL-3.0-or-later` est la licence
    # d'Angelith lui-même et se dit légitimement en clair dans « À propos ».
    interdits = [ln for ln in corps.splitlines()
                 if re.search(r'"[^"]*\b(GPL-3\.0|Apache-2\.0)\b', ln)
                 and "AGPL-3.0-or-later" not in ln]
    assert not interdits, (relatif, interdits)


def test_le_catalogue_de_reparations_lit_bien_les_constantes():
    """Bout en bout : ce que l'utilisateur verra avant de cliquer est ce que `models` déclare."""
    from core import reparations as rep
    from manga import reparations as _manga  # noqa: F401 — enregistre le catalogue

    assert rep.par_identifiant("poids_detection").licence == models.DETECTEUR_LICENCE
    assert rep.par_identifiant("poids_texte").licence == models.TEXTE_LICENCE
    assert rep.par_identifiant("modele_ocr").licence == models.OCR_LICENCE


def test_la_page_a_propos_lit_les_memes_constantes():
    pytest.importorskip("PySide6")
    from gui.dialogues import texte_a_propos

    texte = texte_a_propos({})
    assert models.DETECTEUR_LICENCE in texte
    assert models.TEXTE_LICENCE in texte
    # ⚠ Et la note du détecteur de bulles aussi : c'est elle qui dit qu'Ultralytics YOLOv8 est
    # AGPL-3.0, c'est-à-dire la seconde moitié de la vérité sur ce poids.
    assert models.DETECTEUR_LICENCE_NOTE in texte
