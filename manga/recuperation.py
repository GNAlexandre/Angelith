# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Brouillons d'édition sur disque — le filet contre un plantage. **Sans Qt.**

## Le trou que ce module bouche

Rien n'est écrit avant `Ctrl+S`, et c'est délibéré : on essaie, on revient en arrière, on ne
valide qu'à la fin. Mais la 1.5.0 a fait passer l'éditeur d'**une** planche ouverte à **N**,
et il devient donc normal d'accumuler trente planches corrigées en mémoire pendant une heure.
Une coupure de courant, un plantage de PySide6, une session Windows fermée : tout part.

## Pourquoi un dossier à part, et non les checkpoints

La solution évidente — écrire chaque planche dans ses checkpoints dès qu'elle est modifiée —
a été écartée, et pas pour une raison de goût : `traduction_manuelle.json` et
`mise_en_page.json` sont exactement les fichiers qui **périment un rendu**
(cf. `etat_planches.SOURCES_DE_PEREMPTION`). Les écrire au fil de la frappe ferait passer une
planche en « à relettrer » à chaque caractère tapé, ferait gonfler le récapitulatif
d'« Enregistrer le projet » de planches qu'on n'a pas fini de corriger, et ferait avertir
`assemble_outputs` sur du travail en cours. C'est le relettrage permanent que la 1.5.0 vient
justement de supprimer.

⚠ **Ce dossier ne périme rien et n'est lu par personne d'autre que l'interface.** Il vit sous
`build/<…>/manga/.recuperation/`, hors de `.checkpoints/` que `etat_planches._indices`
parcourt, et le pipeline l'ignore de bout en bout. C'est l'invariant du module, et le test qui
le vérifie est le plus important du fichier.

## Le format est celui d'un checkpoint, exprès

`document.ecrire_etat` / `lire_etat` prennent déjà un dossier quelconque. On les réutilise
tels quels plutôt que d'inventer un format de brouillon : deux sérialisations de la même
chose finiraient par diverger, et c'est le brouillon — celui qu'on ne relit qu'après un
incident, donc celui qu'on ne teste jamais à la main — qui divergerait en silence.

État **complet**, régions comprises. Mesuré sur *manga A* Vol.1 : **13 à 41 ms et 2 à
11 Ko** par planche, `masks.png` inclus. À ce prix-là, économiser le PNG ne valait pas un
brouillon qui ne se relit qu'à moitié.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import document

#: Caché, comme `.vignettes/` : rien là-dedans n'est fait pour être ouvert à la main.
DOSSIER = ".recuperation"

#: Horodatage de la session. Sans lui, on ne pourrait pas dire à l'utilisateur QUAND le
#: travail retrouvé a été fait — et reprendre un brouillon sans savoir son âge est un pari.
MARQUEUR = "session.json"


def dossier(build_dir) -> Path:
    return Path(build_dir) / DOSSIER


def dossier_planche(build_dir, index: int) -> Path:
    return dossier(build_dir) / f"page_{int(index):04d}"


def empreinte(etat) -> tuple:
    """Ce qui, dans un état, distingue un brouillon d'un autre.

    ⚠ Sur le **contenu**, pas sur un `mtime` : un état vit en mémoire, il n'a pas de date.
    C'est la seule différence de nature avec `etat_planches.signature`, qui interroge le
    disque ; le parti est le même — *la clé est l'état*, donc il n'y a aucune invalidation
    explicite à écrire, donc aucune à oublier.

    Les **masques** n'entrent pas dans l'empreinte : ce sont des tableaux de plusieurs
    mégaoctets, les hacher coûterait plus cher que la réécriture qu'on cherche à éviter. On
    prend leurs boîtes englobantes, qui changent dès qu'une zone est ajoutée, déplacée,
    redimensionnée ou supprimée — c'est-à-dire à chaque geste que l'éditeur sait faire sur
    une région."""
    regions = etat.regions or []
    return (
        tuple(etat.traduction or ()),
        tuple(sorted((int(k), v) for k, v in (etat.manuelles or {}).items())),
        tuple(sorted((int(k), repr(v)) for k, v in (etat.mises_en_page or {}).items())),
        tuple(etat.ocr or ()),
        tuple(sorted((int(k), v) for k, v in (etat.origines or {}).items())),
        tuple(tuple(getattr(r, "bbox", ()) or ()) for r in regions),
    )


def ecrire(build_dir, index: int, etat) -> None:
    """Recopie l'état en mémoire d'une planche dans le miroir.

    `motif="brouillon"` marque la détection : si ce dossier était un jour relu par erreur
    comme un checkpoint, la trace dirait d'où il vient."""
    cible = dossier_planche(build_dir, index)
    cible.mkdir(parents=True, exist_ok=True)
    document.ecrire_etat(cible, etat, motif="brouillon", regions_changees=True)
    _marquer(build_dir)


def _marquer(build_dir) -> None:
    racine = dossier(build_dir)
    racine.mkdir(parents=True, exist_ok=True)
    (racine / MARQUEUR).write_text(
        json.dumps({"date": time.time()}, ensure_ascii=False), encoding="utf-8")


def lire(build_dir, index: int):
    """L'état sauvegardé d'une planche, ou `None`.

    Tolérant par construction : un miroir écrit au moment exact du plantage peut être
    tronqué. Rendre `None` fait retomber sur le disque, ce qui est le pire cas acceptable —
    lever ferait échouer l'ouverture du tome entier, donc punirait l'incident deux fois."""
    cible = dossier_planche(build_dir, index)
    if not cible.is_dir():
        return None
    try:
        return document.lire_etat(cible)
    except Exception:                                   # noqa: BLE001 — cf. docstring
        return None


def planches(build_dir) -> list[int]:
    """Les planches dont un brouillon attend, triées."""
    racine = dossier(build_dir)
    if not racine.is_dir():
        return []
    return sorted(int(d.name.removeprefix("page_")) for d in racine.iterdir()
                  if d.is_dir() and d.name.startswith("page_")
                  and d.name.removeprefix("page_").isdigit())


def date(build_dir) -> float | None:
    """Quand la dernière sauvegarde a eu lieu — `None` s'il n'y en a pas."""
    marqueur = dossier(build_dir) / MARQUEUR
    try:
        return float(json.loads(marqueur.read_text(encoding="utf-8"))["date"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def effacer(build_dir, index: int | None = None) -> None:
    """Efface le miroir d'une planche, ou tout le dossier.

    Appelé après un enregistrement réussi (le disque fait désormais foi) et quand
    l'utilisateur refuse une reprise. Ne jamais l'appeler « pour faire propre » à
    l'ouverture : c'est précisément là que le brouillon sert."""
    if index is None:
        shutil.rmtree(dossier(build_dir), ignore_errors=True)
        return
    shutil.rmtree(dossier_planche(build_dir, index), ignore_errors=True)
    # Le dossier ne garde pas un marqueur seul : il annoncerait une reprise vide.
    if not planches(build_dir):
        shutil.rmtree(dossier(build_dir), ignore_errors=True)


def resume(build_dir) -> dict:
    """Ce qu'une boîte de reprise doit annoncer : quelles planches, et de quand."""
    numeros = planches(build_dir)
    return {"planches": numeros, "date": date(build_dir), "existe": bool(numeros)}
