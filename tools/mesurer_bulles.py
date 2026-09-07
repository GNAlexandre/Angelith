# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Mesure la GÉOMÉTRIE des bulles d'un tome manga — instrument de contrôle du lot 4.2.

Pourquoi un outil séparé plutôt qu'une ligne de plus dans `RAPPORT.md` : le rapport dit ce qui
va mal, cet outil dit **la distribution**. C'est elle qui a permis de fixer les seuils de
`manga/bubbles_split.py` sur des chiffres — 797 bulles passées, 40 découpages candidats
inspectés un par un — et c'est elle qu'il faut relire pour vérifier qu'un changement de seuil
n'a pas ouvert la porte aux faux positifs.

La métrique centrale est le **remplissage** : la fraction de sa boîte englobante qu'un masque
occupe réellement. Un ballon, même dentelé, remplit sa boîte (médiane 0,89 sur le tome de
référence). Deux ballons que le détecteur a fusionnés tombent à 0,60 : deux lobes en diagonale
ne peuvent pas remplir leur boîte commune.

    python tools/mesurer_bulles.py "manga A" Vol.1
    python tools/mesurer_bulles.py "manga A" Vol.1 --scindables
    python tools/mesurer_bulles.py "manga A" Vol.1 --page 142

⚠ L'outil lit UNIQUEMENT le cache (`.checkpoints/`) : il ne charge aucun modèle, ne réécrit
rien, et se lance donc pendant qu'un run tourne.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from core.cli import charger_config, configurer_stdout     # noqa: E402
from manga import bubbles_split, checkpoints               # noqa: E402
from manga.detection import BubbleRegion                   # noqa: E402
from manga.geometry import remplissage                     # noqa: E402
from tools import _banc_commun                             # noqa: E402


def _build_dir(config: dict, projet: str, tome: str) -> Path:
    return _banc_commun.build_dir_de(_banc_commun.racine_build(config), projet, tome)


def _regions_de(ckpt_dir: Path) -> list[BubbleRegion]:
    """Régions d'une planche, **quel que soit le format** du cache : on veut pouvoir mesurer un
    tome AVANT sa migration aussi bien qu'après.

    Déléguée à `_banc_commun.charger_regions` depuis le lot 10 : `tools/banc.py` posait la
    même question, et deux lectures de cache divergent toujours."""
    return _banc_commun.charger_regions(ckpt_dir)


def _percentiles(valeurs: list[float]) -> str:
    if not valeurs:
        return "(aucune)"
    a = np.asarray(sorted(valeurs))
    q = [float(np.percentile(a, p)) for p in (1, 5, 25, 50, 75, 95)]
    return (f"min {a[0]:.3f} · p1 {q[0]:.3f} · p5 {q[1]:.3f} · p25 {q[2]:.3f} · "
            f"médiane {q[3]:.3f} · p75 {q[4]:.3f} · p95 {q[5]:.3f} · max {a[-1]:.3f}")


def main() -> int:
    # Sans ça, une console Windows en cp1252 lève `UnicodeEncodeError` sur la première flèche
    # ou le premier titre japonais — après avoir affiché la moitié du résultat.
    configurer_stdout()
    ap = argparse.ArgumentParser(description="Distribution géométrique des bulles d'un tome.")
    ap.add_argument("projet")
    ap.add_argument("tome")
    ap.add_argument("--page", type=int, default=None,
                    help="ne mesurer qu'une planche (1-indexée)")
    ap.add_argument("--scindables", action="store_true",
                    help="tenter la scission et lister ce qu'elle donnerait, sans rien écrire")
    ap.add_argument("--aire-min", type=int, default=2000,
                    help="ignorer les régions plus petites (px², défaut 2000)")
    args = ap.parse_args()

    config = charger_config(str(RACINE / "config.yaml"))
    build_dir = _build_dir(config, args.projet, args.tome)
    if not build_dir.exists():
        print(f"❌ Aucun build ici : {build_dir}")
        return 1
    scission_cfg = (config["manga"]["detection"].get("scission") or {})

    remplissages: list[float] = []
    polices: list[int] = []
    n_pages = n_regions = n_deja_scindees = 0
    suspectes: list[tuple] = []
    scindables: list[tuple] = []

    for page in _banc_commun.numeros_de_planches(build_dir):
        if args.page is not None and page != args.page:
            continue
        d = checkpoints.page_checkpoint_dir(build_dir, page)
        regions = _regions_de(d)
        if not regions:
            continue
        n_pages += 1
        donnees = _banc_commun.charger_json(d / checkpoints.QA_FILENAME) or {}
        taille = {b["index"]: b.get("taille_police")
                  for b in (donnees.get("bulles") or []) if "index" in b}

        for i, r in enumerate(regions):
            if r.mask is None or int(r.mask.sum()) < args.aire_min:
                continue
            n_regions += 1
            if r.scindee:
                n_deja_scindees += 1
            f = remplissage(r.mask)
            remplissages.append(f)
            px = taille.get(i)
            if px:
                polices.append(px)
            if f < float(scission_cfg.get("seuil_suspect", bubbles_split.SEUIL_SUSPECT)) \
                    and not r.scindee:
                suspectes.append((page, i + 1, int(r.mask.sum()), f, px))

        if args.scindables:
            sortie, diag = bubbles_split.scinder_regions(regions, scission_cfg)
            for e in diag:
                if e["type"] == "scindee":
                    scindables.append((page, e["index"] + 1, e["remplissage"],
                                       e["remplissages_lobes"], taille.get(e["index"])))

    print(f"— {build_dir} —")
    print(f"planches avec bulles : {n_pages} · régions mesurées : {n_regions} "
          f"(dont {n_deja_scindees} issue(s) d'une scission)")
    print(f"remplissage du masque : {_percentiles(remplissages)}")
    if polices:
        print(f"taille de police      : {_percentiles([float(p) for p in polices])}")
    seuil_sus = float(scission_cfg.get("seuil_suspect", bubbles_split.SEUIL_SUSPECT))
    print(f"\nrégions sous le seuil de suspicion ({seuil_sus:.2f}) et non scindées : "
          f"{len(suspectes)}")
    for page, num, aire, f, px in sorted(suspectes, key=lambda t: t[3])[:30]:
        print(f"   page {page:>3} bulle {num:>2} — remplissage {f:.3f}, aire {aire:>7}, "
              f"police {px} px")

    if args.scindables:
        print(f"\nscissions que la configuration actuelle appliquerait : {len(scindables)}")
        for page, num, f, lobes, px in scindables:
            print(f"   page {page:>3} bulle {num:>2} — {f:.3f} → "
                  + ", ".join(f"{x:.3f}" for x in lobes) + f" (police actuelle {px} px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
