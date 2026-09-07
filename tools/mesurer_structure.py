#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Republie la distribution du classifieur de STRUCTURE de planche — instrument du lot 15.

    python tools/mesurer_structure.py "Mon Œuvre" Vol.1
    python tools/mesurer_structure.py --tous
    python tools/mesurer_structure.py "Mon Œuvre" Vol.1 --profils   # les mesures brutes

## Pourquoi un outil séparé

`RAPPORT.md` dit ce qui va mal, `tools/banc.py` compare deux runs. Celui-ci dit **la
distribution**, et c'est elle qui décide si les seuils de `manga.planche.DEFAUTS` tiennent :

> Un classifieur qui type tout est un classifieur suspect.

Le taux d'« indéterminé » est donc le chiffre à regarder en premier, et il doit rester
MAJORITAIRE. Sur tout `build/` au moment du lot 15 — **7 862 bulles, dix volumes** — il
valait **86,2 %**, avec dialogue 6,9 %, récitatif 5,4 %, pensée 0,9 % et cri 0,6 %. Les seuils,
eux, avaient été calibrés sur un sous-ensemble de 2 534 bulles : les 5 328 autres n'ont donc
pas servi au réglage.

⚠ Comme `tools/mesurer_bulles.py` et `tools/banc.py` : **aucun modèle chargé, rien de
réécrit**, et se lance pendant qu'un run tourne. Il lit `regions.json` + `masks.png`, et
recalcule la structure — il ne dépend donc pas de `structure.json`, ce qui lui permet de
mesurer un tome traité AVANT ce lot, et de rejouer un changement de seuil sans relancer quoi
que ce soit.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from core.cli import charger_config, configurer_stdout     # noqa: E402
from manga import geometry, planche                        # noqa: E402
from tools import _banc_commun as banc                     # noqa: E402


def mesurer_volume(volume) -> dict:
    """Un relevé par volume, lu dans son seul cache."""
    structures: list[planche.Structure] = []
    profils: list[geometry.ProfilForme] = []
    for p in banc.planches(volume):
        if not p.a_des_regions:
            continue
        regions = banc.charger_regions(p.ckpt)
        if not regions:
            continue
        taille = tuple(p.image_size or (1125, 1600))
        structures.append(planche.analyser(regions, taille, sens=p.sens or "droite_gauche"))
        profils += [geometry.profil_de_forme(r.mask) for r in regions
                    if getattr(r, "mask", None) is not None]
    releve = planche.taux(structures)
    releve["volume"] = volume.nom
    releve["profils"] = profils
    return releve


def _ligne_taux(nom: str, n: int, total: int) -> str:
    return f"   {nom:14s} {n:6d}   {100 * n / total if total else 0:5.1f} %"


def publier(releve: dict, *, profils: bool = False) -> None:
    total = releve["bulles"]
    print(f"== {releve['volume']} — {total} bulles, "
          f"{releve['planches_annotees']} planche(s) annotée(s)")
    for nom in planche.TYPES:
        print(_ligne_taux(nom, releve["types"].get(nom, 0), total))
    print(_ligne_taux("étiquetées", releve["etiquetees"], total))
    groupes = releve["groupes_par_planche"]
    if groupes:
        print(f"   groupes/planche : médiane {statistics.median(groupes):.0f}, "
              f"max {max(groupes)}, un seul groupe sur "
              f"{sum(1 for g in groupes if g == 1)} planche(s)")
    print(f"   ordre par repli diagonal : {releve['planches_repli']} planche(s)")
    if profils and releve["profils"]:
        _publier_profils(releve["profils"])


def _publier_profils(profils: list[geometry.ProfilForme]) -> None:
    """Les mesures brutes, pour REFIXER un seuil sur des chiffres plutôt qu'au jugé.

    C'est exactement ce qui a servi à écrire `planche.DEFAUTS`, et à en RETIRER une mesure :
    le 94ᵉ centile du relief est atteint par les masques les plus bruités du tome, pas par les
    ballons en étoile. C'est `harmonique` — la périodicité, pas l'amplitude — qui les
    sépare."""
    import numpy as np
    colonnes = {
        "remplissage_corps": [p.remplissage_corps for p in profils],
        "rectangularite": [p.rectangularite for p in profils],
        "ondulation": [p.ondulation for p in profils],
        "relief": [p.relief for p in profils],
        "harmonique": [p.harmonique for p in profils],
        "pointes": [float(p.pointes) for p in profils],
    }
    print("   — profils bruts —")
    for nom, valeurs in colonnes.items():
        a = np.asarray(valeurs, dtype=float)
        print(f"   {nom:18s} " + "  ".join(f"p{q}={np.percentile(a, q):.4f}"
                                            for q in (10, 50, 75, 90, 95, 99)))
    avec = sum(1 for p in profils if p.queue is not None)
    print(f"   queue lisible      {avec} / {len(profils)} "
          f"({100 * avec / max(1, len(profils)):.1f} %)")


def main(argv=None) -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("projet", nargs="?")
    ap.add_argument("tome", nargs="?")
    ap.add_argument("--tous", action="store_true", help="tous les volumes de build/")
    ap.add_argument("--profils", action="store_true",
                    help="publie aussi les mesures brutes (centiles)")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args(argv)

    config = charger_config(args.config)
    racine = banc.racine_build(config)
    if args.tous:
        volumes = banc.enumerer_volumes(racine)
    elif args.projet and args.tome:
        volumes = [v for v in banc.enumerer_volumes(racine)
                   if v.projet == args.projet and v.tome == args.tome]
    else:
        ap.error("donne « projet tome », ou --tous")
        return 2
    if not volumes:
        print("Aucun volume trouvé sous " + str(racine))
        return 1

    cumul: Counter = Counter()
    total = 0
    for v in volumes:
        releve = mesurer_volume(v)
        publier(releve, profils=args.profils)
        cumul.update(releve["types"])
        total += releve["bulles"]
    if len(volumes) > 1 and total:
        print(f"== TOUS — {total} bulles")
        for nom in planche.TYPES:
            print(_ligne_taux(nom, cumul.get(nom, 0), total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
