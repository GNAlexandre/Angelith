# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Balayage d'un tome scanné : analyse, lecture, assemblage.

Deux passes, et non une boucle unique par page — pour une raison de reproductibilité. La
reconnaissance d'une page de TITRE compare son pas au pas médian du tome ; en une seule
passe, ce médian ne serait connu que des pages déjà vues, et le verdict d'une page
dépendrait de l'ordre dans lequel on l'a atteinte. Relancer avec `--page 12` ne donnerait
alors pas le même résultat qu'un tome entier.

L'analyse coûte ~0,1 s par page (dont 63 ms de balayage de seuil) contre ~30 s de lecture :
la faire d'abord en entier ne coûte rien et rend le verdict déterministe.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from core import control
from core.reporter import Reporter

from . import assemblage, checkpoints, grille, pages, report_scan

DEFAUTS = {
    "seuil_encre": None,               # None = balayage (cf. `grille.choisir_seuil`)
    "caracteres_par_tranche": grille.CARACTERES_PAR_TRANCHE,
    "lot_ocr": 16,
    "ruby": assemblage.RUBY_IGNORER,
    "illustration_encre_max": grille.ENCRE_MAX,
    "titre_pas_min": grille.TITRE_PAS_MIN,
    "colonnes_min": grille.COLONNES_MIN_TEXTE,
    "ocr": {},
}


def config_scan(config: dict) -> dict:
    brut = (config or {}).get("scan") or {}
    fusion = {**DEFAUTS, **{k: v for k, v in brut.items() if k != "ocr"}}
    fusion["ocr"] = {**DEFAUTS["ocr"], **(brut.get("ocr") or {})}
    return fusion


def build_dir_de(config: dict, projet: str, tome: str) -> Path:
    return Path(config["chemins"]["build"]) / projet / tome / "ocr"


def _nom_media(chemin: Path, index: int) -> str:
    return f"page_{index:04d}{chemin.suffix.lower()}"


def process_volume(projet: str, tome: str, config: dict, *, reporter: Reporter | None = None,
                   page: int | None = None, force: bool = False, depuis: str | None = None,
                   langue: str | None = None, lecteur=None) -> dict:
    """Traite un tome. Renvoie un récapitulatif, aussi utilisé par le rapport.

    `lecteur` permet d'injecter un double : c'est ce qui rend toute la brique testable sans
    charger 424 Mo de modèle."""
    dire = reporter or Reporter()
    cfg = config_scan(config)
    from PIL import Image

    vol_dir = Path(config["chemins"]["sources"]) / projet / tome
    build_dir = build_dir_de(config, projet, tome)
    build_dir.mkdir(parents=True, exist_ok=True)
    plan_tome = pages.scan_volume(vol_dir, build_dir, config, langue=langue)

    dire.info(f"=== {projet} / {tome} === {len(plan_tome.pages)} page(s) dans "
              f"{plan_tome.dossier.name} → {plan_tome.sortie.name}")
    for avertissement in plan_tome.avertissements:
        dire.warn(avertissement)

    control.clear_stop(build_dir)
    control.install_sigint(dire)
    indices = range(len(plan_tome.pages))
    cibles = [page] if page is not None else list(indices)
    arrete = False

    # ------------------------------------------------------------------ #
    #  Passe 1 — analyse (géométrique, sans modèle)
    # ------------------------------------------------------------------ #
    dire.stage("analyse")
    plans: dict[int, grille.PlanPage] = {}
    debut = time.time()
    for i in cibles:
        if control.should_stop(build_dir):
            arrete = True
            break
        chemin = plan_tome.pages[i]
        ckpt = checkpoints.page_checkpoint_dir(build_dir, i)
        etapes = checkpoints.etapes_a_refaire(ckpt, force=force, depuis=depuis)
        plan = None if "analyse" in etapes else checkpoints.load_plan(ckpt)
        if plan is None:
            with Image.open(chemin) as image:
                plan = grille.analyser(
                    image, seuil=cfg["seuil_encre"],
                    caracteres_par_tranche=int(cfg["caracteres_par_tranche"]),
                    encre_max=float(cfg["illustration_encre_max"]),
                    colonnes_min=int(cfg["colonnes_min"]))
            checkpoints.save_plan(ckpt, plan)
        plans[i] = plan
    dire.verbose(f"analyse : {len(plans)} page(s) en {time.time() - debut:.1f}s")

    # Pas médian du tome, puis reclassement des pages de titre. Il n'y a rien à recalculer :
    # le verdict `titre` est une comparaison, pas une analyse.
    pas_tome = report_scan.pas_median(plans.values())
    if pas_tome:
        for i, plan in plans.items():
            if grille.reclasser(plan, pas_tome, seuil=float(cfg["titre_pas_min"])):
                checkpoints.save_plan(checkpoints.page_checkpoint_dir(build_dir, i), plan)

    # ------------------------------------------------------------------ #
    #  Passe 2 — lecture (OCR)
    # ------------------------------------------------------------------ #
    a_lire = [i for i in plans
              if plans[i].verdict != grille.ILLUSTRATION
              and "lecture" in checkpoints.etapes_a_refaire(
                  checkpoints.page_checkpoint_dir(build_dir, i), force=force, depuis=depuis)]
    if a_lire and not arrete:
        dire.stage(f"lecture ({len(a_lire)} page(s) à lire)")
        if lecteur is None:
            from .lecture import Lecteur
            lecteur = Lecteur(cfg["ocr"], lot=int(cfg["lot_ocr"]), dire=dire.info)
        from . import lecture as module_lecture

        for rang, i in enumerate(a_lire, 1):
            if control.should_stop(build_dir):
                arrete = True
                break
            plan = plans[i]
            debut = time.time()
            with Image.open(plan_tome.pages[i]) as image:
                image.load()
                encre, _seuil, _note = grille.choisir_seuil(image)
                resultats = module_lecture.lire_page(
                    lecteur, image, plan, encre=encre,
                    caracteres_par_tranche=int(cfg["caracteres_par_tranche"]))
            checkpoints.save_texte(checkpoints.page_checkpoint_dir(build_dir, i),
                                   [r.en_dict() for r in resultats])
            duree = time.time() - debut
            caracteres = sum(len(r.texte) for r in resultats)
            suspectes = sum(1 for r in resultats if r.suspecte)
            dire.block(rang, len(a_lire))
            dire.verbose(
                f"page {i:04d} : {len(plan.corps)} colonnes · "
                f"{sum(len(c.tranches()) for c in plan.corps)} tranches · {duree:.1f}s · "
                f"{caracteres} car." + (f" · {suspectes} suspecte(s)" if suspectes else ""))

    # ------------------------------------------------------------------ #
    #  Passe 3 — assemblage du document
    # ------------------------------------------------------------------ #
    complet = page is None and not arrete
    recap = report_scan.recapituler(build_dir, plan_tome, plans, pas_tome)
    if complet and not recap["manquantes"]:
        ecrire_document(plan_tome, plans, build_dir, ruby=str(cfg["ruby"]), dire=dire)
        recap["document"] = str(plan_tome.sortie)
    elif complet:
        dire.warn(f"{len(recap['manquantes'])} page(s) sans lecture : le document n'est pas "
                  f"écrit. Relance sans --page, ou avec --from lecture.")
    elif page is not None:
        dire.info("Page isolée : le document du tome n'est pas réécrit.")

    rapport = report_scan.ecrire_rapport(build_dir, plan_tome, recap)
    if arrete:
        dire.warn("Arrêt demandé — reprise possible avec la même commande.")
        control.clear_stop(build_dir)
        lues = len(plans) - len(recap["manquantes"])
        dire.stopped(lues, len(plan_tome.pages))
    else:
        # `finish` attend la liste des fichiers produits : c'est le contrat du protocole
        # `Reporter`, partagé avec les deux autres briques.
        dire.finish([str(rapport)] + ([recap["document"]] if recap.get("document") else []))
    return recap


def ecrire_document(plan_tome: pages.PlanScan, plans: dict, build_dir: Path, *,
                    ruby: str, dire: Reporter) -> Path:
    """Écrit le `.md` **dans le dossier de langue**, et y copie les illustrations.

    C'est la seule écriture du dépôt sous `sources/`, et elle est délibérée : c'est le seul
    endroit où `pipeline/sources.py` regarde, le fichier se corrige à la main, et il survit
    à un vidage de `build/` — ce qui n'est pas un détail quand il représente deux heures
    d'OCR."""
    lues: list[assemblage.PageLue] = []
    n_media = 0
    for i in sorted(plans):
        plan = plans[i]
        if plan.verdict == grille.ILLUSTRATION:
            plan_tome.media.mkdir(parents=True, exist_ok=True)
            source = plan_tome.pages[i]
            nom = _nom_media(source, i)
            cible = plan_tome.media / nom
            if not cible.exists() or cible.stat().st_mtime < source.stat().st_mtime:
                shutil.copy2(source, cible)
            n_media += 1
            lues.append(assemblage.PageLue(index=i, verdict=plan.verdict,
                                           media=f"{pages.MEDIA}/{nom}"))
            continue

        cache = checkpoints.load_texte(checkpoints.page_checkpoint_dir(build_dir, i)) or []
        colonnes = plan.corps
        avance = plan.pas or 1.0
        lectures = []
        for j, col in enumerate(colonnes):
            brut = cache[j] if j < len(cache) else {}
            lectures.append([
                (assemblage.position_de_ruby(boite, col.y0, avance), texte)
                for boite, texte in zip(col.ruby, brut.get("ruby", []))
            ])
        lues.append(assemblage.PageLue(
            index=i, verdict=plan.verdict,
            textes=[(cache[j].get("texte", "") if j < len(cache) else "")
                    for j in range(len(colonnes))],
            indentations=[c.indentee for c in colonnes],
            lectures=lectures))

    texte = assemblage.assembler(lues, ruby=ruby)
    plan_tome.sortie.parent.mkdir(parents=True, exist_ok=True)
    plan_tome.sortie.write_text(texte, encoding="utf-8")
    # ⚠ L'espace fine des milliers se pose sur le NOMBRE seul : un `.replace(",", " ")` sur
    # toute la phrase emportait aussi la virgule qui sépare les deux faits.
    compte = f"{len(texte):,}".replace(",", " ")
    dire.info(f"Document écrit : {plan_tome.sortie} "
              f"({compte} caractères, {n_media} illustration(s))")
    return plan_tome.sortie
