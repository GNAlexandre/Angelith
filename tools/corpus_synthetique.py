#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Corpus de mesure SYNTHÉTIQUE : des planches fabriquées, donc parfaitement annotées.

    python tools/corpus_synthetique.py --sortie tests/corpus/synthetique
    python tools/corpus_synthetique.py --sortie /tmp/corpus --graine 20260825

## Pourquoi synthétique, et pourquoi d'abord

Le corpus annoté est l'étape la plus délicate du lot, et ce n'est **pas un problème
technique**. Les œuvres commerciales ont été purgées du dépôt une fois pour toutes
(`86c3d3d`, `b3d1eaa`) et ne reviennent pas, même pour mesurer. Manga109-s est sous conditions
d'usage académique — le dépôt le signale déjà (`manga/models.py`, `manga_models/README.md`) —
et les poids de recherche ont la même restriction.

Trois voies restaient. Des œuvres sous licence libre (la seule qui produise un banc
reproductible par un tiers, et la seule qui demande de chercher avant de promettre une
taille) ; **un jeu synthétique** ; un corpus privé dont on ne publie que les chiffres. Ce
fichier est la deuxième : une journée de travail, redistribuable sans réserve, et elle couvre
immédiatement les cas limites que les lots 12 et 13 visent.

## Ce qu'il contient, et pourquoi chaque cas est là

| Cas | Ce qu'il piège |
|---|---|
| bulle ordinaire | le témoin — si elle tombe, rien d'autre ne veut dire quoi que ce soit |
| bulle **minuscule** (≈ 40 px) | le redimensionnement d'entrée (`input_size`, lot 12) : c'est la première à disparaître |
| ballon de **cri** (contour en étoile) | un remplissage de boîte bas SANS goulot — `bubbles_split.classer_non_scindees` doit dire « dentelée », pas « bi-lobée » |
| **récitatif** rectangulaire | une bulle qui n'est pas un ovale |
| bulle **bi-lobée** (deux ballons collés) | annotée comme DEUX bulles : c'est la scission du lot 13 qui est mesurée, pas une préférence |
| bulle **à cheval sur deux cases** | le trait de case traverse le masque |
| **bande de 1080×10 000** | le découpage en fenêtres (`detection.fenetres`) — et la seule façon de faire tourner le lot 14 en CI |

⚠ La bande longue n'est pas un supplément : c'est **gratuit à générer** et c'est la seule
planche du dépôt qui exerce le chemin webtoon de bout en bout.

## Licence

Tout ce que ce fichier produit est généré par ce fichier. Aucune œuvre, aucun scan, aucun
poids de modèle n'y entre — le corpus est donc redistribuable **sans réserve**, sous la
licence du dépôt (AGPL-3.0-or-later). C'est écrit dans `info.licence` de chaque
`annotations.json`, parce qu'un corpus dont la licence n'est pas dans le fichier n'est pas
redistribuable en pratique.

## Déterminisme

La graine par défaut est **écrite dans le dépôt** (`GRAINE`). Deux exécutions rendent le même
corpus au pixel près : sans cela, un banc « avant/après » comparerait deux corpus différents
et attribuerait au code ce qui vient du hasard.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

#: Graine par défaut, FIGÉE et publiée. La changer change le corpus, donc la ligne de base.
GRAINE = 20260825

#: Hauteur de la bande. 10 000 px n'est pas un chiffre rond gratuit : `manga/detection.py`
#: découpe en fenêtres au-delà d'un certain allongement, et une bande plus courte ne
#: déclencherait pas ce chemin — donc ne testerait rien de ce qu'elle est là pour tester.
BANDE = (1080, 10_000)
PAGE = (1200, 1800)

LICENCE = "AGPL-3.0-or-later — généré par tools/corpus_synthetique.py, aucune œuvre tierce"

#: Police japonaise DU SYSTÈME, résolue par `tools/polices.py` — le même module que
#: `tests/conftest.py`, pour que le corpus et la fixture ne divergent pas. Le texte n'est pas
#: décoratif : un ovale vide et un ballon lettré ne donnent pas le même score au détecteur, et
#: mesurer sur des bulles vides surestimerait la difficulté.
#:
#: ⚠ Le repli `load_default()` est CONSERVÉ ici, contrairement aux tests qui échouent
#: désormais. Ce n'est pas une incohérence : ce script est un GÉNÉRATEUR qu'on lance à la main
#: pour recalibrer un corpus, et rendre du tofu au lieu de rien laisse au moins voir ce qui a
#: été produit. Mais le corpus ainsi obtenu ne se compare PAS à un corpus lettré — d'où
#: l'avertissement écrit sur la sortie d'erreur.
_REPLIQUES = ("こんにちは", "まって！", "ゴォォォ", "なに…", "そうか", "行くぞ！")

_AVERTI_SANS_POLICE = False


def _police(taille: int):
    global _AVERTI_SANS_POLICE
    from PIL import ImageFont

    from tools.polices import explication_absence, police_japonaise
    chemin = police_japonaise()
    if chemin is not None:
        try:
            return ImageFont.truetype(str(chemin), taille)
        except OSError:
            pass
    if not _AVERTI_SANS_POLICE:
        _AVERTI_SANS_POLICE = True
        print(explication_absence(), file=sys.stderr)
        print("  → corpus généré avec la police par défaut de Pillow : les bulles seront "
              "vides ou en tofu, et le rappel mesuré dessus n'est PAS comparable au corpus "
              "de référence.", file=sys.stderr)
    return ImageFont.load_default()


def _fond(dessin, largeur: int, hauteur: int, rng: random.Random, *, trame: bool) -> None:
    """Le décor. Deux régimes de fond, parce que le nettoyage et la détection n'ont pas le
    même comportement sur du blanc et sur de la trame — c'est mesuré : `clean.py` choisit son
    mode d'après l'uniformité de la zone."""
    if trame:
        for y in range(0, hauteur, 6):
            dessin.line([(0, y), (largeur, y)], fill=(214, 214, 214), width=2)
    for _ in range(18):
        x0, y0 = rng.randrange(largeur), rng.randrange(hauteur)
        dessin.line([(x0, y0), (x0 + rng.randrange(-200, 200), y0 + rng.randrange(-200, 200))],
                    fill=(60, 60, 60), width=rng.choice((2, 3, 5)))


def _cases(dessin, largeur: int, hauteur: int, lignes: int) -> list[int]:
    """Trace une grille de cases et rend les ordonnées des traits — la bulle « à cheval »
    doit tomber SUR l'un d'eux."""
    pas = hauteur // lignes
    traits = []
    for i in range(1, lignes):
        y = i * pas
        dessin.line([(40, y), (largeur - 40, y)], fill=(0, 0, 0), width=6)
        traits.append(y)
    dessin.rectangle([20, 20, largeur - 20, hauteur - 20], outline=(0, 0, 0), width=6)
    return traits


def _polygone_ellipse(cx: float, cy: float, rx: float, ry: float, n: int = 48) -> list[float]:
    """Le contour d'une ellipse, en polygone COCO. 48 sommets : l'écart d'aire avec l'ellipse
    exacte tombe sous 0,2 %, très en dessous de ce que l'IoU d'appariement (0,50) peut voir."""
    points = []
    for k in range(n):
        a = 2 * math.pi * k / n
        points += [cx + rx * math.cos(a), cy + ry * math.sin(a)]
    return points


def _polygone_etoile(cx: float, cy: float, rx: float, ry: float, pointes: int = 12,
                     creux: float = 0.62) -> list[float]:
    """Le contour d'un ballon de CRI. Son remplissage de boîte est bas (~0,55) **sans aucun
    goulot** : c'est exactement le cas que `bubbles_split` doit classer « dentelée » et ne pas
    scinder."""
    points = []
    for k in range(pointes * 2):
        a = math.pi * k / pointes - math.pi / 2
        f = 1.0 if k % 2 == 0 else creux
        points += [cx + rx * f * math.cos(a), cy + ry * f * math.sin(a)]
    return points


def _peindre(dessin, polygone: list[float], texte: str | None, taille_police: int) -> None:
    points = list(zip(polygone[0::2], polygone[1::2]))
    dessin.polygon(points, fill=(255, 255, 255), outline=(0, 0, 0))
    # Le contour à 4 px : un trait d'un pixel disparaît au redimensionnement d'entrée du
    # réseau, et la bulle minuscule perdrait alors sa seule arête.
    dessin.line([*points, points[0]], fill=(0, 0, 0), width=4)
    if not texte:
        return
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    police = _police(taille_police)
    boite = dessin.textbbox((0, 0), texte, font=police)
    dessin.text((cx - (boite[2] - boite[0]) / 2, cy - (boite[3] - boite[1]) / 2),
                texte, font=police, fill=(0, 0, 0))


def planche_paginee(rng: random.Random, *, trame: bool) -> tuple:
    """Une page de manga : cases, décor, et six cas de bulle dont le double et le minuscule."""
    from PIL import Image, ImageDraw
    largeur, hauteur = PAGE
    image = Image.new("RGB", (largeur, hauteur), (250, 250, 248))
    dessin = ImageDraw.Draw(image)
    _fond(dessin, largeur, hauteur, rng, trame=trame)
    traits = _cases(dessin, largeur, hauteur, 3)

    polygones: list[list[float]] = []
    # 1. La bulle ordinaire — le témoin.
    polygones.append(_polygone_ellipse(320, 220, 190, 120))
    # 2. La minuscule : 44×30 px, la première que le redimensionnement d'entrée écrase.
    polygones.append(_polygone_ellipse(900, 150, 22, 15))
    # 3. Le ballon de cri : remplissage bas, aucun goulot.
    polygones.append(_polygone_etoile(880, 430, 180, 130))
    # 4. Le récitatif : une bulle qui n'est pas un ovale.
    polygones.append([120.0, 700.0, 480.0, 700.0, 480.0, 830.0, 120.0, 830.0])
    # 5. Deux ballons COLLÉS, annotés comme DEUX bulles. C'est la scission qui est mesurée.
    polygones.append(_polygone_ellipse(760, 900, 130, 95))
    polygones.append(_polygone_ellipse(940, 980, 130, 95))
    # 6. À cheval sur le trait de case.
    polygones.append(_polygone_ellipse(560, traits[1], 200, 110))

    for i, polygone in enumerate(polygones):
        aire_petite = i == 1
        _peindre(dessin, polygone, None if aire_petite else _REPLIQUES[i % len(_REPLIQUES)],
                 14 if aire_petite else 34)
    return image, polygones


def bande_webtoon(rng: random.Random) -> tuple:
    """La bande longue : 1080×10 000, huit bulles réparties sur toute la hauteur.

    Elle exerce le découpage en fenêtres de `manga/detection.py` — sans lui, une bulle de
    webtoon arrive au réseau en 26×32 px et n'est tout simplement pas émise."""
    from PIL import Image, ImageDraw
    largeur, hauteur = BANDE
    image = Image.new("RGB", (largeur, hauteur), (252, 250, 250))
    dessin = ImageDraw.Draw(image)
    _fond(dessin, largeur, hauteur, rng, trame=False)
    polygones = []
    for k in range(8):
        cy = 600 + k * (hauteur - 1200) / 7
        rx, ry = (40, 28) if k == 3 else (200, 110)
        polygones.append(_polygone_ellipse(200 + (k % 3) * 320, cy, rx, ry))
    for k, polygone in enumerate(polygones):
        _peindre(dessin, polygone, None if k == 3 else _REPLIQUES[k % len(_REPLIQUES)], 34)
    return image, polygones


def construire(graine: int = GRAINE) -> list[tuple]:
    """Le corpus entier : `[(nom, image, polygones)]`. Déterministe pour une graine donnée.

    Deux pages et une bande — ce que le lot juge suffisant pour la CI, et ce qui tient dans
    un temps de build."""
    rng = random.Random(graine)
    page1, poly1 = planche_paginee(rng, trame=False)
    page2, poly2 = planche_paginee(rng, trame=True)
    bande, poly3 = bande_webtoon(rng)
    return [("page_manga_01.png", page1, poly1),
            ("page_manga_02.png", page2, poly2),
            ("bande_webtoon_01.png", bande, poly3)]


def annotations_coco(planches: list[tuple]) -> dict:
    """Le corpus au format COCO instance segmentation — celui que tout outil d'annotation
    exporte, et qu'aucun outil de ce dépôt n'a besoin d'apprendre à écrire."""
    images, annotations = [], []
    for i, (nom, image, polygones) in enumerate(planches, start=1):
        images.append({"id": i, "file_name": nom,
                       "width": image.size[0], "height": image.size[1]})
        for polygone in polygones:
            xs, ys = polygone[0::2], polygone[1::2]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            annotations.append({
                "id": len(annotations) + 1, "image_id": i, "category_id": 1,
                "bbox": [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)],
                "segmentation": [[round(v, 1) for v in polygone]],
                "area": round((x1 - x0) * (y1 - y0), 1), "iscrowd": 0,
            })
    return {
        "info": {"description": "Corpus synthétique de mesure — Angelith",
                 "licence": LICENCE,
                 "generateur": "tools/corpus_synthetique.py"},
        "images": images,
        "annotations": annotations,
        "categories": [{"id": 1, "name": "bulle", "supercategory": "texte"}],
    }


def ecrire(sortie: Path, graine: int = GRAINE) -> dict:
    """Écrit images + `annotations.json` sous `sortie`. Renvoie les annotations."""
    sortie = Path(sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    planches = construire(graine)
    for nom, image, _polygones in planches:
        image.save(sortie / nom, optimize=True)
    coco = annotations_coco(planches)
    (sortie / "annotations.json").write_text(
        json.dumps(coco, ensure_ascii=False, indent=1), encoding="utf-8")
    return coco


def main() -> int:
    from core.cli import configurer_stdout
    configurer_stdout()
    ap = argparse.ArgumentParser(description="Génère le corpus de mesure synthétique.")
    ap.add_argument("--sortie", default=str(RACINE / "tests" / "corpus" / "synthetique"))
    ap.add_argument("--graine", type=int, default=GRAINE)
    args = ap.parse_args()
    coco = ecrire(Path(args.sortie), args.graine)
    print(f"{len(coco['images'])} planche(s), {len(coco['annotations'])} bulle(s) annotée(s) "
          f"→ {args.sortie}")
    print(f"Licence : {LICENCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
