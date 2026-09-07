# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc de détection en CI, sur le corpus synthétique SEUL.

## Ce que ce fichier achète

Une régression de détection est attrapée par un `git push`, pas par un tome raté trois
semaines plus tard. C'est le bénéfice quotidien du lot 10, et probablement le plus important à
long terme.

## Pourquoi le corpus synthétique et lui seul

Il est redistribuable sans réserve (généré par `tools/corpus_synthetique.py`, aucune œuvre
tierce), donc **commitable**. Un corpus réel ne l'est pas : les œuvres commerciales ont été
purgées du dépôt et Manga109-s est sous conditions d'usage académique. Un banc de CI qui
exigerait un corpus non redistribuable ne tournerait que sur la machine de son auteur.

## Le contrat

Le test **casse le build si le rappel baisse ou si les faux positifs montent** — les deux, et
pas seulement le premier. Un lot qui gagne des bulles en gagnant autant de fausses détections
n'améliore rien, et un seuil sur le seul rappel le laisserait passer en affichant un succès.

⚠ La ligne de base vit dans `tests/corpus/synthetique/reference.json`. **Elle se recalibre à
la main, jamais automatiquement** : un banc qui réécrit sa propre référence à chaque run ne
mesure plus rien. Pour la (re)calibrer, avec les poids en place :

    python tools/banc.py --corpus tests/corpus/synthetique --json \\
        > tests/corpus/synthetique/reference.json

et le diff de ce fichier est ce qu'on relit en revue.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

pytest.importorskip("onnxruntime")

MODELE = RACINE / "manga_models" / "bubble_detector.onnx"
CORPUS = RACINE / "tests" / "corpus" / "synthetique"
REFERENCE = CORPUS / "reference.json"

pytestmark = [
    pytest.mark.modeles,
    pytest.mark.lent,
    pytest.mark.skipif(not MODELE.exists(),
                       reason="modèle de détection non téléchargé (voir manga_models/README.md)"),
]

#: Tolérance sur le rappel. Le post-traitement du détecteur n'est pas bit-à-bit reproductible
#: d'une version d'onnxruntime à l'autre ; 2 points absolus absorbent cette dérive sans rien
#: cacher — sur 22 bulles annotées, c'est moins d'une demi-bulle.
TOLERANCE_RAPPEL = 0.02

#: Les fausses détections, elles, ne bénéficient d'aucune tolérance à la hausse au-delà d'une
#: demi-détection par planche. C'est le sens même du garde-fou : gagner des bulles en gagnant
#: des faux positifs n'est pas un gain.
TOLERANCE_FAUSSES = 0.5


@pytest.fixture(scope="module")
def bilan() -> dict:
    """Le banc, joué une fois pour tout le fichier : le détecteur coûte 104 Mo à charger."""
    from tools import _banc_detection as mesure
    resultat = mesure.mesurer_corpus(CORPUS)
    assert resultat is not None, f"corpus annoté introuvable sous {CORPUS}"
    return resultat


@pytest.fixture(scope="module")
def reference() -> dict:
    if not REFERENCE.exists():
        pytest.fail(
            "Ligne de base absente. Le banc ne peut pas détecter de régression sans elle, et "
            "il ne la fabrique pas tout seul — un banc qui réécrit sa référence ne mesure "
            "plus rien.\n"
            "Calibre-la et relis le diff :\n"
            "    python tools/banc.py --corpus tests/corpus/synthetique --json "
            f"> {REFERENCE.relative_to(RACINE)}")
    return json.loads(REFERENCE.read_text(encoding="utf-8"))["global"]


def test_le_rappel_ne_baisse_pas(bilan, reference):
    attendu = float(reference["rappel"])
    obtenu = float(bilan["global"]["rappel"])
    assert obtenu >= attendu - TOLERANCE_RAPPEL, (
        f"rappel {obtenu:.3f} contre {attendu:.3f} en référence — "
        f"des bulles annotées ne sont plus détectées")


def test_les_fausses_detections_ne_montent_pas(bilan, reference):
    attendu = float(reference["fausses/planche"])
    obtenu = float(bilan["global"]["fausses/planche"])
    assert obtenu <= attendu + TOLERANCE_FAUSSES, (
        f"{obtenu:.2f} fausse(s) détection(s) par planche contre {attendu:.2f} en référence — "
        f"un gain de bulles payé en faux positifs n'est pas un gain")


def test_aucune_planche_ne_tombe_a_zero_bulle(bilan, reference):
    """La métrique qui décide. Une planche à zéro produit une page ENTIÈREMENT non traduite,
    que ni le rapport ni le relecteur ne voient passer."""
    obtenu = int(bilan["global"]["zéro alors que texte"])
    assert obtenu <= int(reference["zéro alors que texte"]), (
        f"{obtenu} planche(s) annotée(s) rendent zéro bulle, contre "
        f"{reference['zéro alors que texte']} en référence")


def test_la_bande_longue_est_mesuree_a_part(bilan):
    """Deux régimes, deux tableaux. Une moyenne unique masquerait exactement l'écart que le
    webtoon a révélé : de 0 % à 22 % de zones restaurées selon le format."""
    assert "webtoon" in bilan["par_regime"]
    assert bilan["par_regime"]["webtoon"]["planches"] == 1
    assert bilan["par_regime"]["webtoon"]["bulles annotées"] == 8


def test_la_bande_longue_est_bien_DECOUPEE(bilan):
    """⚠ Le garde-fou du garde-fou. Le lot 14 a remplacé la falaise de ratio par un critère de
    détectabilité (`detection.OCCUPATION_MIN`) : si la substitution cessait un jour de découper
    la bande, **rien d'autre dans cette suite ne le verrait**. Le rappel du régime webtoon
    s'effondrerait, mais il s'effondrerait aussi pour dix autres raisons.

    Ce test-ci nomme la cause. La bande de 1080×10 000 du corpus synthétique occupe 69 px du
    canevas de 640 — très en dessous du seuil de 213,3 — et doit donc produire 8 fenêtres."""
    from manga import detection

    largeur, hauteur = 1080, 10_000
    assert detection.occupation(largeur, hauteur, detection.INPUT_SIZE) < detection.OCCUPATION_MIN
    assert len(detection.fenetres(largeur, hauteur,
                                  input_size=detection.INPUT_SIZE)) == 8

