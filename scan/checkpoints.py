# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Points de reprise **par page** pour un tome scanné.

Un tome de 270 pages coûte ~2 h d'OCR. Reprendre au tome serait donc inutilisable : l'unité
de cache est la page, comme dans `manga/checkpoints.py`, et pour la même raison.

Structure sous `build/<Projet>/<Tome>/ocr/` :

    .checkpoints/page_XXXX/
        plan.json     — la grille : verdict, colonnes, coupes, ruby (étape `analyse`)
        texte.json    — ce que l'OCR a lu, colonne par colonne (étape `lecture`)

Deux étapes seulement, et une VRAIE chaîne cette fois — contrairement au manga, où les
étapes forment un graphe : on ne peut pas lire des tranches sans savoir où couper. Refaire
l'analyse périme donc toujours la lecture.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .grille import Colonne, PlanPage

STAGES = ["analyse", "lecture"]

PLAN_FILENAME = "plan.json"
TEXTE_FILENAME = "texte.json"

# Le plan porte des tuples et des dataclasses ; il n'a pas vocation à être relu par autre
# chose que ce module. Le numéro de format existe pour qu'un changement de structure invalide
# les caches au lieu de les lire de travers.
FORMAT_VERSION = 1


def stage_index(nom: str) -> int:
    return STAGES.index(nom)


def page_checkpoint_dir(build_dir, index: int) -> Path:
    return Path(build_dir) / ".checkpoints" / f"page_{index:04d}"


# --------------------------------------------------------------------------- #
#  Plan de page
# --------------------------------------------------------------------------- #

def save_plan(ckpt_dir, plan: PlanPage) -> None:
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    charge = {
        "format": FORMAT_VERSION,
        "verdict": plan.verdict,
        "pas": plan.pas,
        "taille": list(plan.taille),
        "part_encre": plan.part_encre,
        "seuil": plan.seuil,
        "motif": plan.motif,
        "colonnes": [{**asdict(c), "ruby": [list(r) for r in c.ruby]} for c in plan.colonnes],
    }
    (ckpt_dir / PLAN_FILENAME).write_text(
        json.dumps(charge, ensure_ascii=False, indent=1), encoding="utf-8")


def load_plan(ckpt_dir) -> PlanPage | None:
    """Le plan en cache, ou `None` s'il est absent, illisible ou d'un format périmé.

    Tolérant à un fichier abîmé plutôt que fatal : un cache est une optimisation, et une
    interruption au mauvais moment ne doit pas condamner le tome — elle doit faire refaire
    la page."""
    fichier = Path(ckpt_dir) / PLAN_FILENAME
    if not fichier.exists():
        return None
    try:
        charge = json.loads(fichier.read_text(encoding="utf-8"))
        if int(charge.get("format", 0)) != FORMAT_VERSION:
            return None
        colonnes = [
            Colonne(x0=int(c["x0"]), x1=int(c["x1"]), y0=int(c["y0"]), y1=int(c["y1"]),
                    genre=c.get("genre", "corps"), indentee=bool(c.get("indentee", False)),
                    cases=int(c.get("cases", 0)),
                    coupes=[int(v) for v in c.get("coupes", [])],
                    ruby=[tuple(int(v) for v in r) for r in c.get("ruby", [])],
                    coupe_forcee=bool(c.get("coupe_forcee", False)))
            for c in charge.get("colonnes", [])
        ]
        return PlanPage(
            verdict=charge["verdict"], colonnes=colonnes, pas=float(charge.get("pas", 0.0)),
            taille=tuple(charge.get("taille", (0, 0))),
            part_encre=float(charge.get("part_encre", 0.0)),
            seuil=int(charge.get("seuil", 0)), motif=charge.get("motif", ""))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Texte lu
# --------------------------------------------------------------------------- #

def save_texte(ckpt_dir, colonnes: list[dict]) -> None:
    """`colonnes` : une entrée par colonne de corps, dans l'ordre de lecture —
    `{"texte": str, "tranches": [str, …], "ruby": [str, …], "suspecte": bool}`."""
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    (ckpt_dir / TEXTE_FILENAME).write_text(
        json.dumps({"format": FORMAT_VERSION, "colonnes": colonnes},
                   ensure_ascii=False, indent=1), encoding="utf-8")


def load_texte(ckpt_dir) -> list[dict] | None:
    fichier = Path(ckpt_dir) / TEXTE_FILENAME
    if not fichier.exists():
        return None
    try:
        charge = json.loads(fichier.read_text(encoding="utf-8"))
        if int(charge.get("format", 0)) != FORMAT_VERSION:
            return None
        return list(charge.get("colonnes", []))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Quelles étapes refaire
# --------------------------------------------------------------------------- #

def etapes_a_refaire(ckpt_dir, *, force: bool = False,
                     depuis: str | None = None) -> set[str]:
    """Étapes à (re)jouer pour cette page.

    `force` refait tout ; `depuis` refait l'étape nommée et **tout ce qui en découle** — ici
    la chaîne est linéaire, donc « tout ce qui suit ». Une étape dont le cache manque est
    refaite, ainsi que ses suivantes : lire des tranches suppose de savoir où couper."""
    if force:
        return set(STAGES)
    a_refaire: set[str] = set()
    if depuis:
        a_refaire.update(STAGES[stage_index(depuis):])
    present = {
        "analyse": load_plan(ckpt_dir) is not None,
        "lecture": load_texte(ckpt_dir) is not None,
    }
    for i, etape in enumerate(STAGES):
        if not present[etape]:
            a_refaire.update(STAGES[i:])
    return a_refaire
