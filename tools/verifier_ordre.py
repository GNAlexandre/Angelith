#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Contrôle que l'ordre de lecture PERSISTÉ correspond au sens déclaré. N'écrit jamais rien.

    python tools/verifier_ordre.py "Mon Webtoon" Chap.11
    python tools/verifier_ordre.py "Mon Oeuvre" --all

## Le défaut que cet outil débusque

`manga/document.py:poser_regions` appelait `reading_order()` **sans le sens de lecture**, donc
toujours droite→gauche. Sur un webtoon (`gauche_droite`), la moindre édition de zone depuis
l'interface graphique re-triait donc TOUTE la planche en ordre manga.

Le défaut est silencieux à trois titres : le nombre de bulles reste juste, `regions.json`
continue d'annoncer le bon `sens` (`save_regions` préserve le champ), et les textes ont bien
suivi leurs bulles — c'est l'ORDRE des bulles entre elles qui est faux. Rien, dans le rapport
ni dans l'interface, ne le signale.

## La mesure

Pour chaque planche : relire `regions.json`, recalculer `reading_order(regions, sens_déclaré)`
et comparer à l'ordre stocké. Une divergence signe une planche re-triée dans le mauvais sens.

⚠ Une planche dont les bulles sont **empilées verticalement** sort identique dans les deux
sens — l'outil la déclare donc saine, et elle l'est : son ordre est le même quel qu'ait été le
tri. Seules les planches portant des bulles côte à côte peuvent diverger.

## Le second ordre, celui des zones HORS BULLE (lot 13)

Le même défaut existait une seconde fois, ailleurs, et cet outil ne le voyait pas : il ne
regardait que les bulles. `text_detection.hors_des_bulles` triait ses zones **en dur** en
droite→gauche, sans paramètre `sens` — le seul endroit du pipeline à ignorer le sens de lecture
du format. Sur un webtoon, les bulles sortaient donc correctement ordonnées et **les onomatopées
numérotées à l'envers**, ce qui suffisait à rendre l'outil rassurant et faux.

Les zones hors bulle sont donc vérifiées ici aussi, contre le même sens déclaré. ⚠ **Sans
`--corriger`** : contrairement aux bulles, une zone hors bulle n'est pas indexée par un état de
planche que l'on sait permuter d'un bloc (`sfx.json`, `sfx_traduction.json` et les drapeaux de
mobilier le sont chacun de leur côté). La réparation est de relancer la passe, qui ne coûte
aucun appel LLM de traduction de bulle.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from core.cli import charger_config, configurer_stdout     # noqa: E402
from manga import checkpoints, document, serie             # noqa: E402
from manga import ocr as ocr_mod                           # noqa: E402
from tools import _banc_commun                             # noqa: E402


def verifier_planche(ckpt_dir: Path) -> dict | None:
    """`None` si la planche n'a pas de cache exploitable, sinon son verdict."""
    regions = checkpoints.load_regions(ckpt_dir)
    if not regions:
        return None
    sens = checkpoints.sens_enregistre(ckpt_dir)
    attendu = ocr_mod.reading_order(list(regions), sens)
    positions = {id(r): i for i, r in enumerate(regions)}
    perm = [positions[id(r)] for r in attendu]
    deplacees = [i for i, p in enumerate(perm) if i != p]
    # Une planche identique dans les DEUX sens ne prouve rien : son ordre ne dépend pas du
    # tri (bulles empilées). On le dit, pour ne pas laisser croire à un contrôle plus fort
    # qu'il n'est.
    autre = "droite_gauche" if sens == "gauche_droite" else "gauche_droite"
    ambigue = [id(r) for r in ocr_mod.reading_order(list(regions), autre)] == \
              [id(r) for r in attendu]
    return {"sens": sens, "bulles": len(regions), "perm": perm,
            "deplacees": deplacees, "ambigue": ambigue}


def verifier_sfx(ckpt_dir: Path, sens: str) -> dict | None:
    """Même contrôle, pour les zones de texte hors bulle. `None` si la passe n'a pas tourné.

    Volontairement séparé de `verifier_planche` : les deux ordres sont persistés dans deux
    fichiers distincts, écrits par deux étapes distinctes, et une planche peut très bien avoir
    des bulles dans le bon ordre et des onomatopées dans le mauvais — c'était même le cas
    NOMINAL sur webtoon avant le lot 13."""
    charge = checkpoints.load_sfx_complet(ckpt_dir)
    if not charge or not charge.get("regions"):
        return None
    zones = charge["regions"]
    attendu = ocr_mod.reading_order(list(zones), sens)
    positions = {id(r): i for i, r in enumerate(zones)}
    perm = [positions[id(r)] for r in attendu]
    return {"zones": len(zones), "perm": perm,
            "deplacees": [i for i, q in enumerate(perm) if i != q]}


def corriger_planche(ckpt_dir: Path, perm: list[int]) -> None:
    """Remet les bulles dans l'ordre, en emportant TOUT ce qui est indexé par bulle.

    ⚠ C'est une PERMUTATION, pas une re-détection. Les régions, les masques, l'OCR, les
    traductions, les corrections écrites à la main et les mises en page sont tous conservés :
    seul leur ordre change. Conseiller `--from detection` à la place jetterait les bulles
    ajoutées à la main dans l'éditeur — c'est-à-dire précisément le travail qu'on cherche à
    sauver.

    `perm[i]` = index ANCIEN de la région qui doit occuper la position `i`."""
    etat = document.lire_etat(ckpt_dir)
    if sorted(perm) != list(range(len(etat.regions))):
        raise ValueError("permutation invalide")
    neuf = document.EtatPlanche(
        regions=[etat.regions[p] for p in perm],
        ocr=[etat.ocr[p] for p in perm],
        traduction=[etat.traduction[p] for p in perm],
        # Les dicts sont CREUX et indexés par bulle : on les reconstruit par la permutation
        # inverse plutôt que de les recopier, sinon une correction manuelle pointerait la
        # mauvaise réplique — le défaut même qu'on répare.
        manuelles={i: etat.manuelles[p] for i, p in enumerate(perm) if p in etat.manuelles},
        origines={i: etat.origines[p] for i, p in enumerate(perm) if p in etat.origines},
        mises_en_page={i: dict(etat.mises_en_page[p]) for i, p in enumerate(perm)
                       if p in etat.mises_en_page},
        taille=etat.taille, sens=etat.sens)
    document.ecrire_etat(ckpt_dir, neuf, motif="correction_ordre")


def _tomes(args, config) -> list[str]:
    """Les chapitres à vérifier. Sans `--all`, celui qu'on a nommé.

    ⚠ `--all` énumère `sources/`, et non `build/` comme le fait `tools/banc.py` : cet outil
    peut CORRIGER un ordre, et une correction porte sur une œuvre qu'on possède. Le banc, lui,
    ne fait que lire, et doit fonctionner sur une machine dont le corpus a été purgé."""
    if args.tome:
        return [args.tome]
    return serie.lister_chapitres(_banc_commun.racine_sources(config), args.projet)


def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Vérifie que l'ordre de lecture persisté suit le sens déclaré.")
    ap.add_argument("projet")
    ap.add_argument("tome", nargs="?", default=None)
    ap.add_argument("--all", action="store_true", help="tous les chapitres de l'œuvre")
    ap.add_argument("--corriger", action="store_true",
                    help="remet les bulles dans l'ordre (permutation SEULE : rien n'est "
                         "re-détecté, re-lu ni retraduit — les bulles ajoutées à la main "
                         "sont conservées). Le rendu est à refaire ensuite : "
                         "`run_manga.py <projet> <tome> --from rendu`")
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()
    if not (args.tome or args.all):
        ap.error("indique un tome, ou --all pour toute l'œuvre.")

    config = charger_config(args.config)
    build_root = _banc_commun.racine_build(config)

    total_fautives = 0
    for tome in _tomes(args, config):
        build_dir = serie.build_dir_de(build_root, args.projet, tome)
        racine = build_dir / ".checkpoints"
        if not racine.is_dir():
            continue
        fautives, ambigues, saines = [], 0, 0
        sfx_fautives, sfx_planches = [], 0
        numeros = _banc_commun.numeros_de_planches(build_dir)
        sens_tome = ""
        for n in numeros:
            ckpt = checkpoints.page_checkpoint_dir(build_dir, n)
            verdict = verifier_planche(ckpt)
            if verdict is None:
                continue
            sens_tome = verdict["sens"]
            if verdict["deplacees"]:
                fautives.append((n, verdict))
            elif verdict["ambigue"]:
                ambigues += 1
            else:
                saines += 1
            v_sfx = verifier_sfx(ckpt, sens_tome)
            if v_sfx is not None:
                sfx_planches += 1
                if v_sfx["deplacees"]:
                    sfx_fautives.append((n, v_sfx))

        print(f"\n— {args.projet} / {tome} — sens déclaré : {sens_tome or '?'} —")
        if not numeros:
            print("  (aucune planche en cache)")
            continue
        print(f"  {saines} planche(s) conforme(s) · {ambigues} indifférente(s) au sens "
              f"(bulles empilées) · {len(fautives)} À REPRENDRE")
        for n, v in fautives:
            print(f"  ⚠ page {n} : {v['bulles']} bulles, {len(v['deplacees'])} mal placée(s) "
                  f"— ordre stocké {list(range(v['bulles']))} vs attendu {v['perm']}")
        if fautives and args.corriger:
            for n, v in fautives:
                corriger_planche(checkpoints.page_checkpoint_dir(build_dir, n), v["perm"])
                print(f"  ✓ page {n} remise dans l'ordre (textes et corrections conservés)")
            print(f"  → relettrer : python run_manga.py \"{args.projet}\" {tome} --from rendu")
        elif fautives:
            print(f"  → corriger : python tools/verifier_ordre.py \"{args.projet}\" {tome} "
                  f"--corriger    (permutation seule, aucun appel LLM)")

        if sfx_planches:
            print(f"  texte hors bulle : {sfx_planches - len(sfx_fautives)}/{sfx_planches} "
                  f"planche(s) dans l'ordre du format · {len(sfx_fautives)} À REPRENDRE")
            for n, v in sfx_fautives[:10]:
                print(f"  ⚠ page {n} : {v['zones']} zone(s), {len(v['deplacees'])} mal "
                      f"placée(s) — attendu {v['perm']}")
            if sfx_fautives:
                # Pas de `--corriger` ici, et le message le dit : trois fichiers indexés
                # séparément, contre un seul état de planche du côté des bulles.
                print(f"  → relancer la passe : supprimer les `sfx.json` du tome puis "
                      f"`python run_manga.py \"{args.projet}\" {tome} --from rendu` "
                      f"(aucune bulle n'est retraduite)")
        total_fautives += len(fautives) + len(sfx_fautives)

    print(f"\nTotal : {total_fautives} planche(s) à reprendre.")
    return 1 if total_fautives else 0


if __name__ == "__main__":
    raise SystemExit(main())
