#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Prévisualise ce que donnerait une relance de détection sur UNE planche — sans rien écrire.

    python tools/apercu_detection.py "manga A" Vol.1 --page 147 --balayage
    python tools/apercu_detection.py "…" Vol.1 --page 147 --conf 0.25 --iou 0.60
    python tools/apercu_detection.py "…" Vol.1 --page 147 --conf 0.25 --vignette apercu.png

## Pourquoi c'est presque gratuit

`conf_threshold` et `iou_threshold` ne servent **qu'au post-traitement** : le réseau ne les
voit jamais (cf. `manga/detection.py`, `inferer()` / `regions_de()`). Balayer douze réglages
sur une planche coûte donc **une inférence et douze post-traitements**, soit quelques secondes
— alors qu'une relance réelle invaliderait l'OCR et la traduction de la page, donc un appel
LLM.

## Pourquoi un aperçu AVANT le chemin d'écriture

Baisser `conf` fait toujours apparaître des régions ; la question est lesquelles. Sur le tome
de référence, deux détections basses étaient du dessin (un gratte-ciel, une trame). L'outil
affiche donc, pour chaque réglage, ce que l'**arbitre** (`manga/detection_retry.py`) en
conclurait — y compris son véto sur les régions que le nettoyage refuserait de toucher.

⚠ L'outil ne réécrit **jamais** le cache. Il charge le modèle (contrairement à
`tools/mesurer_bulles.py`) et exige `--page` : un balayage de tome n'aurait pas de sens, les
seuils du tome vivent dans `config.yaml`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from core import config as core_config                     # noqa: E402
from core.cli import charger_config, configurer_stdout     # noqa: E402
from manga import (checkpoints, clean,                     # noqa: E402
                   detection_retry, sources_manga)
from manga.detection import (CONF_THRESHOLD,               # noqa: E402
                             IOU_THRESHOLD, BubbleDetector)
from manga.geometry import remplissage                     # noqa: E402

# Balayage par défaut : `conf` domine largement le résultat (c'est elle qui décide ce qui
# existe), `iou` ne fait que fusionner ou séparer des boîtes déjà retenues. D'où plus de pas
# sur la première, et de part et d'autre du défaut du tome (0,35) — la MONTER est un geste
# légitime, c'est ainsi qu'on écarte un faux positif sur du dessin.
#
# Les bornes viennent de la mesure : les scores du tome sont bimodaux (une poignée sous 0,40,
# le reste au-dessus de 0,88). Descendre sous 0,10 ne fait donc apparaître que du bruit, et
# monter au-delà de 0,80 commence à couper de vraies bulles.
_BALAYAGE_CONF = (0.10, 0.20, 0.30, 0.35, 0.45, 0.60, 0.75)
_BALAYAGE_IOU = (0.30, 0.45, 0.60)

# Couleurs de la vignette. Deux faux positifs sur du dessin se voient d'un coup d'œil et se
# lisent très mal dans une colonne de chiffres.
_COULEURS = {"conservee": (90, 160, 255), "gagnee": (60, 200, 90), "perdue": (235, 70, 70)}


def _page_source(vol_dir: Path, build_dir: Path, page: int) -> Path | None:
    """Planche d'origine, résolue par le MÊME `scan_volume` que l'orchestrateur.

    Lire `pages_src/` directement ne marcherait pas : ce dossier n'est peuplé que lorsque la
    source est une archive. Un tome livré en images libres est lu depuis `sources/`, et
    l'aperçu doit voir exactement la planche que la détection verrait."""
    pages = sources_manga.scan_volume(vol_dir, build_dir).pages
    return pages[page - 1] if 0 < page <= len(pages) else None


def _uniformites(image: Image.Image, regions, cfg_nettoyage) -> dict[int, float]:
    """Uniformité mesurée par le NETTOYEUR pour chaque région candidate.

    C'est la mesure qui décide du véto : une région dont l'uniformité tombe sous
    `seuil_abandon` ne serait pas nettoyée, donc ne doit pas être détectée."""
    styles = clean.analyze_regions(image, regions, cfg_nettoyage)
    return {i: float(getattr(s, "uniformity", 0.0)) for i, s in enumerate(styles)}


def _ligne(conf: float, iou: float, verdict, regions, uniformites, seuil_abandon) -> str:
    scores = sorted(float(r.score) for r in regions)
    mediane = scores[len(scores) // 2] if scores else 0.0
    refusees = sum(1 for i in range(len(regions))
                   if uniformites.get(i, 1.0) < seuil_abandon)
    px = sum(int(r.mask.sum()) for r in regions)
    etat = "✓" if verdict.accepte else "·"
    return (f"  {etat} conf {conf:.2f} iou {iou:.2f} │ {len(regions):>3} bulles "
            f"│ +{len(verdict.gagnees):<2} −{len(verdict.perdues):<2} "
            f"={verdict.conservees:<3} │ score méd. {mediane:.2f} "
            f"│ {refusees} non nettoyable(s)"
            + (f" │ {len(verdict.faux_positifs_ecartes)} écarté(s)"
               if verdict.faux_positifs_ecartes else " │            ")
            + f" │ {px / 1000:>7.1f} kpx │ "
            + ("ACCEPTÉ" if verdict.accepte else detection_retry.LIBELLES.get(
                verdict.motif, verdict.motif)))


def _vignette(image: Image.Image, reference, candidates, verdict, chemin: Path) -> None:
    """Trace gagnées / perdues / conservées en couleurs sur la planche."""
    vue = image.convert("RGB").copy()
    dessin = ImageDraw.Draw(vue)
    apparie = detection_retry.apparier(reference, candidates)
    for i, j in enumerate(apparie):
        couleur = _COULEURS["perdue"] if j is None else _COULEURS["conservee"]
        dessin.rectangle(list(reference[i].bbox), outline=couleur, width=4)
    for j in verdict.gagnees:
        dessin.rectangle(list(candidates[j].bbox), outline=_COULEURS["gagnee"], width=4)
    vue.save(chemin)


def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Prévisualise une relance de détection sur une planche (n'écrit rien).")
    ap.add_argument("projet")
    ap.add_argument("tome")
    ap.add_argument("--page", type=int, required=True, help="planche à examiner (1-indexée)")
    ap.add_argument("--conf", type=float, default=None, help="seuil de confiance à essayer")
    ap.add_argument("--iou", type=float, default=None, help="seuil de NMS à essayer")
    ap.add_argument("--balayage", action="store_true",
                    help="essayer une grille de réglages (une seule inférence)")
    ap.add_argument("--vignette", metavar="FICHIER", default=None,
                    help="écrire une image annotée (gagnées/perdues/conservées)")
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    config = charger_config(args.config)
    chemins = core_config.section(config, "manga", "chemins")
    build_dir = Path(chemins["build"]) / args.projet / args.tome / "manga"
    vol_dir = Path(chemins["sources"]) / args.projet / args.tome
    if not build_dir.exists():
        print(f"❌ Aucun build ici : {build_dir}")
        return 1

    ckpt = checkpoints.page_checkpoint_dir(build_dir, args.page)
    reference = checkpoints.load_regions(ckpt) or []
    chemin_page = _page_source(vol_dir, build_dir, args.page)
    if chemin_page is None:
        print(f"❌ La planche {args.page} n'existe pas dans {vol_dir}.")
        return 1

    det_cfg = config["manga"]["detection"]
    nett_cfg = config["manga"].get("nettoyage") or {}
    seuil_abandon = float(nett_cfg.get("seuil_abandon", 0.35))
    image = Image.open(chemin_page).convert("RGB")
    # L'uniformité des régions EN PLACE : sans elle, l'arbitre ne peut pas distinguer la perte
    # d'une vraie bulle de l'abandon d'un faux positif sur du dessin.
    unis_reference = _uniformites(image, reference, nett_cfg) if reference else {}

    detecteur = BubbleDetector(det_cfg["model_path"], providers=det_cfg.get("providers"),
                               conf_threshold=float(
                                   det_cfg.get("conf_threshold", CONF_THRESHOLD)),
                               iou_threshold=float(
                                   det_cfg.get("iou_threshold", IOU_THRESHOLD)),
                               model_url=det_cfg.get("model_url") or None,
                               telechargement_auto=bool(
                                   det_cfg.get("telechargement_auto", True)),
                               dire=print)
    # ⚠ UNE seule inférence, quel que soit le nombre de réglages essayés.
    inference = detecteur.inferer(image)

    print(f"— {args.projet} / {args.tome}, planche {args.page} ({chemin_page.name}) —")
    print(f"référence en cache : {len(reference)} bulle(s)"
          + (f" · remplissage moyen {np.mean([remplissage(r.mask) for r in reference]):.3f}"
             if reference else ""))
    provenance = checkpoints.load_detection_meta(ckpt)
    if provenance:
        print(f"détection déjà relancée : {provenance}")
    print(f"seuils du tome : conf {detecteur.conf_threshold:.2f} · "
          f"iou {detecteur.iou_threshold:.2f}\n")

    if args.balayage:
        reglages = [(c, i) for c in _BALAYAGE_CONF for i in _BALAYAGE_IOU]
    elif args.conf is not None or args.iou is not None:
        reglages = [(args.conf if args.conf is not None else detecteur.conf_threshold,
                     args.iou if args.iou is not None else detecteur.iou_threshold)]
    else:
        reglages = [(detecteur.conf_threshold, detecteur.iou_threshold)]

    print("      réglage        │ bulles │  gagnées/perdues/gardées │ qualité")
    meilleur = None
    for conf, iou in reglages:
        candidates = detecteur.regions_de(inference, conf_threshold=conf, iou_threshold=iou)
        unis = _uniformites(image, candidates, nett_cfg)
        verdict = detection_retry.arbitrer(reference, candidates, unis,
                                           seuil_abandon=seuil_abandon,
                                           uniformites_reference=unis_reference)
        print(_ligne(conf, iou, verdict, candidates, unis, seuil_abandon))
        # « Meilleur » = le plus d'améliorations réelles (bulles gagnées + faux positifs
        # écartés), et à égalité le réglage le plus PROCHE du défaut du tome : moins on
        # s'éloigne des seuils déjà validés sur 150 planches, mieux c'est.
        if verdict.accepte:
            note = (len(verdict.gagnees) + len(verdict.faux_positifs_ecartes),
                    -abs(conf - detecteur.conf_threshold))
            if meilleur is None or note > meilleur[0]:
                meilleur = (note, conf, iou, candidates, verdict)

    if meilleur is not None:
        _note, conf, iou, candidates, verdict = meilleur
        print(f"\nMeilleur réglage retenu : conf {conf:.2f} · iou {iou:.2f} — {verdict}")
        print(f"Pour l'appliquer (invalide l'OCR et la traduction de CETTE planche) :\n"
              f"  python run_manga.py \"{args.projet}\" {args.tome} --page {args.page} "
              f"--conf {conf} --iou {iou}")
    else:
        print("\nAucun réglage n'améliore la détection en place — le doute lui profite.")

    if args.vignette:
        _n, conf, iou, candidates, verdict = (
            meilleur if meilleur is not None
            else (None, reglages[0][0], reglages[0][1], [], None))
        if verdict is None:
            candidates = detecteur.regions_de(inference, conf_threshold=conf, iou_threshold=iou)
            verdict = detection_retry.arbitrer(
                reference, candidates, _uniformites(image, candidates, nett_cfg),
                seuil_abandon=seuil_abandon, uniformites_reference=unis_reference)
        _vignette(image, reference, candidates, verdict, Path(args.vignette))
        print(f"Vignette écrite : {args.vignette} "
              f"(bleu = conservée, vert = gagnée, rouge = perdue)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
