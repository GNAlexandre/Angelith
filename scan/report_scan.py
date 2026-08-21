# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`RAPPORT.md` du tome scanné — ce qu'on lit AVANT de lancer la traduction.

Un OCR ne se relit pas page à page : 270 pages de japonais vertical, personne ne les
vérifiera à l'œil. Le rapport doit donc dire où regarder, et il ne peut le dire que parce
que la grille prédit ce que la lecture devrait rendre (cf. `scan/lecture.est_suspecte`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import checkpoints, grille

RAPPORT = "RAPPORT.md"


def pas_median(plans) -> float:
    """Pas médian du tome, sur les seules pages de texte. Zéro s'il n'y en a aucune."""
    valeurs = [p.pas for p in plans
               if p.verdict != grille.ILLUSTRATION and p.pas and p.corps]
    return float(np.median(valeurs)) if valeurs else 0.0


def recapituler(build_dir, plan_tome, plans: dict, pas_tome: float) -> dict:
    """Compte ce qui a été produit, et surtout ce qui manque ou détonne."""
    lignes = []
    manquantes: list[int] = []
    for i in sorted(plans):
        plan = plans[i]
        cache = checkpoints.load_texte(checkpoints.page_checkpoint_dir(build_dir, i))
        if plan.verdict != grille.ILLUSTRATION and cache is None:
            manquantes.append(i)
        colonnes = cache or []
        lignes.append({
            "page": i,
            "fichier": plan_tome.pages[i].name if i < len(plan_tome.pages) else "",
            "verdict": plan.verdict,
            "motif": plan.motif,
            "seuil": plan.seuil,
            "pas": plan.pas,
            "colonnes": len(plan.corps),
            "mobilier": len(plan.mobilier),
            "tranches": sum(len(c.tranches()) for c in plan.corps),
            "caracteres": sum(len(c.get("texte", "")) for c in colonnes),
            "suspectes": sum(1 for c in colonnes if c.get("suspecte")),
            "relues": sum(1 for c in colonnes if c.get("relue")),
            "forcees": sum(1 for c in plan.corps if c.coupe_forcee),
            "lue": cache is not None,
        })

    par_verdict = {v: sum(1 for l in lignes if l["verdict"] == v)
                   for v in (grille.TEXTE, grille.TITRE, grille.ILLUSTRATION)}
    return {
        "projet": plan_tome.projet,
        "tome": plan_tome.tome,
        "dossier": str(plan_tome.dossier),
        "sortie": str(plan_tome.sortie),
        "pas_tome": pas_tome,
        "pages": lignes,
        "par_verdict": par_verdict,
        "manquantes": manquantes,
        "caracteres": sum(l["caracteres"] for l in lignes),
        "suspectes": sum(l["suspectes"] for l in lignes),
        "document": None,
    }


def _douteuses(recap: dict) -> list[dict]:
    """Pages à regarder en premier. L'ordre est celui du doute, pas celui du tome."""
    doute = []
    for l in recap["pages"]:
        raisons = []
        if not l["lue"] and l["verdict"] != grille.ILLUSTRATION:
            raisons.append("non lue")
        if l["verdict"] == grille.ILLUSTRATION and l["motif"]:
            pass          # une illustration reconnue n'est pas un doute
        if l["suspectes"]:
            raisons.append(f"{l['suspectes']} colonne(s) suspecte(s)")
        if l["forcees"]:
            raisons.append(f"{l['forcees']} coupe(s) sans gouttière")
        if l["verdict"] == grille.TEXTE and l["colonnes"] and l["caracteres"] == 0:
            raisons.append("aucun caractère lu")
        if raisons:
            doute.append({**l, "raisons": ", ".join(raisons)})
    doute.sort(key=lambda l: (-l["suspectes"], -l["forcees"], l["page"]))
    return doute


def rendre(recap: dict) -> str:
    v = recap["par_verdict"]
    total = len(recap["pages"])
    lignes = [
        f"# Rapport d'OCR — {recap['projet']} / {recap['tome']}",
        "",
        f"- **{total}** page(s) : {v.get(grille.TEXTE, 0)} de texte, "
        f"{v.get(grille.TITRE, 0)} de titre, {v.get(grille.ILLUSTRATION, 0)} d'illustration",
        f"- pas médian du tome : **{recap['pas_tome']:.0f} px**",
        f"- **{recap['caracteres']:,}** caractères lus".replace(",", " "),
        f"- source : `{recap['dossier']}`",
        f"- document : `{recap['sortie']}`" + ("" if recap.get("document") else
                                               "  ⚠ *non écrit à ce run*"),
        "",
    ]

    doute = _douteuses(recap)
    lignes += ["## Pages à vérifier", ""]
    if not doute:
        lignes += ["Aucune. La grille et la lecture concordent sur toutes les pages.", ""]
    else:
        lignes += [
            "La grille prédit combien de caractères une colonne contient ; une lecture qui "
            "s'en écarte franchement est le signe d'une hallucination du modèle. Les pages "
            "sont classées par gravité.",
            "",
            "| page | fichier | verdict | colonnes | caractères | pourquoi |",
            "|-----:|---------|---------|---------:|-----------:|----------|",
        ]
        for l in doute[:60]:
            lignes.append(f"| {l['page']:04d} | `{l['fichier']}` | {l['verdict']} | "
                          f"{l['colonnes']} | {l['caracteres']} | {l['raisons']} |")
        if len(doute) > 60:
            lignes.append(f"| … | | | | | et {len(doute) - 60} autre(s) |")
        lignes.append("")

    lignes += ["## Toutes les pages", "",
               "| page | fichier | verdict | seuil | pas | colonnes | tranches | caractères |",
               "|-----:|---------|---------|------:|----:|---------:|---------:|-----------:|"]
    for l in recap["pages"]:
        lignes.append(
            f"| {l['page']:04d} | `{l['fichier']}` | {l['verdict']}"
            f"{(' — ' + l['motif']) if l['motif'] else ''} | {l['seuil']} | "
            f"{l['pas']:.0f} | {l['colonnes']} | {l['tranches']} | {l['caracteres']} |")
    lignes.append("")
    return "\n".join(lignes)


def ecrire_rapport(build_dir, plan_tome, recap: dict) -> Path:
    chemin = Path(build_dir) / RAPPORT
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(rendre(recap), encoding="utf-8")
    return chemin
