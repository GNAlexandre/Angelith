# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Aucun cache du corpus n'est invalidé — `PLAN-35` critère 7, interdit 1 du contexte agent.

## Pourquoi ce fichier existe

« Ne pas invalider un cache sans le vouloir » est le premier des sept interdits du dépôt, et
il a un chiffre : une relance de tome coûte des heures de GPU.
`manga.checkpoints.FORMAT_VERSION` encode le contrat de *nombre et d'ordre* auquel `ocr.json`
et `traduction.json` s'alignent **par position** ; `load_regions` rend `None` sur écart de
version, ce qui déclenche `downstream("detection")` sur tous les projets.

Jusqu'ici, chaque lot le vérifiait à la main. Ce fichier le vérifie **à chaque exécution**,
et sur les caches RÉELS quand ils sont là.

## ⚠ Sur des COPIES, jamais sur l'original

C'est la formulation du critère 7 du `PLAN-35` et du point 7 de la définition de « terminé ».
Un test de non-régression qui écrirait dans `build/` pour prouver qu'il n'y touche pas serait
sa propre contradiction — et les caches du corpus représentent des heures de GPU qui ne se
refont pas.

## Ce que ce fichier ne dit pas

- **Rien en CI.** `build/` n'existe pas sur le runner : les tests qui lisent le corpus se
  sautent, en le disant. Ce qui reste couvert partout est la constante et le tome synthétique
  fabriqué à la volée.
- **Rien des tomes qu'il ne tire pas.** L'échantillon est le PREMIER tome par ordre
  alphabétique qui porte des checkpoints, pas un tirage aléatoire : un test dont l'ensemble
  change d'une exécution à l'autre ne dit pas ce qu'il a vérifié.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from manga import checkpoints, document, recuperation

RACINE = Path(__file__).resolve().parent.parent


def test_la_version_de_format_n_a_pas_bouge():
    """**Le garde-fou le moins cher du dépôt.** Il ne prouve pas qu'aucun cache n'est
    invalidé — un changement de sémantique à version constante le ferait tout autant — mais
    il attrape le cas de loin le plus probable : quelqu'un qui incrémente « pour être sûr ».

    L'interdit 1 le dit en toutes lettres : « un champ de provenance ne touche pas à ce
    contrat — **ne l'incrémentez pas pour ça** »."""
    assert checkpoints.FORMAT_VERSION == 3


def _tomes_du_corpus() -> list[Path]:
    """Les dossiers de build qui portent des checkpoints, triés. Vide hors poste de travail."""
    build = RACINE / "build"
    if not build.is_dir():
        return []
    return sorted(p.parent for p in build.glob("*/*/manga/.checkpoints") if p.is_dir())


@pytest.fixture
def copie_de_cache(tmp_path):
    """Une copie d'un cache RÉEL, ou un `skip` qui dit pourquoi.

    ⚠ `copytree` du dossier `.checkpoints` seul : recopier le tome entier emporterait les
    rendus, soit plusieurs centaines de mégaoctets, pour une vérification qui ne lit que les
    checkpoints."""
    tomes = _tomes_du_corpus()
    if not tomes:
        pytest.skip("aucun cache réel sous build/ — c'est le cas en CI, et c'est normal")
    source = tomes[0] / ".checkpoints"
    cible = tmp_path / ".checkpoints"
    shutil.copytree(source, cible)
    return cible


def test_un_cache_reel_se_relit_apres_le_lot(copie_de_cache):
    """Sur une COPIE d'un cache du corpus : chaque planche rend encore ses régions.

    `load_regions` renvoyant `None` est **exactement** le symptôme d'une invalidation :
    c'est lui qui déclenche `downstream("detection")`, donc la relance de tout le tome."""
    pages = sorted(p for p in copie_de_cache.iterdir()
                   if p.is_dir() and p.name.startswith("page_"))
    if not pages:
        pytest.skip("le cache trouvé ne porte aucune page")
    lues = 0
    for page in pages:
        if not (page / "regions.json").is_file():
            continue
        regions = checkpoints.load_regions(page)
        assert regions is not None, f"{page.name} : cache invalidé par le lot"
        lues += 1
    assert lues, "aucune page exploitable dans la copie — le test ne prouverait rien"


def test_un_etat_reel_se_charge_encore(copie_de_cache):
    """Le contrat d'ALIGNEMENT, pas seulement la lecture : `lire_etat` recolle `ocr.json` et
    `traduction.json` sur les régions **par position**, et c'est ce que
    `FORMAT_VERSION` protège."""
    for page in sorted(copie_de_cache.iterdir()):
        if not (page.is_dir() and (page / "regions.json").is_file()):
            continue
        etat = document.lire_etat(page)
        assert len(etat.ocr) == len(etat.regions)
        assert len(etat.traduction) == len(etat.regions)
        return
    pytest.skip("le cache trouvé ne porte aucune page détectée")


def test_le_lot_35_ne_jette_aucun_miroir_de_recuperation(tmp_path):
    """`recuperation.planches` est plus stricte depuis le lot 35 : elle **ignore** un dossier
    vide. Elle ne doit rien ignorer d'autre.

    ⚠ Le mode de panne à éviter n'est pas symétrique : ne pas annoncer un brouillon lisible
    perdrait du travail, alors qu'annoncer un dossier vide ne coûtait qu'un message
    « illisible ». Ce test garde le côté cher."""
    build = tmp_path / "build"
    complet = recuperation.dossier_planche(build, 4)
    complet.mkdir(parents=True)
    for nom in recuperation.INDISPENSABLES:
        (complet / nom).write_bytes(b"x")
    recuperation.dossier_planche(build, 9).mkdir(parents=True)
    # Un dossier à moitié écrit : `regions.json` sans son `masks.png`, ce que
    # `checkpoints.load_regions` refuse de lire.
    partiel = recuperation.dossier_planche(build, 12)
    partiel.mkdir(parents=True)
    (partiel / "regions.json").write_bytes(b"x")
    assert recuperation.planches(build) == [4]
