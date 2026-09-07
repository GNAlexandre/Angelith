# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Métriques de DÉTECTION contre une vérité terrain, et le format d'annotation qui va avec.

## Ce que les chiffres du dépôt ne mesuraient pas

Le projet a de bons chiffres et les cite. Ils sont réels. Mais aucun ne mesure la
**détection** : ils mesurent ce que le pipeline a fait des bulles qu'il a *vues*. Sans vérité
terrain, « 12 bulles de plus » et « 12 faux positifs de plus » s'écrivent pareil — et le
risque est réel : sur le seul webtoon du corpus de référence, **11 des 59 bulles** sont des
fausses détections probables (zones RESTAURÉES) — contre **zéro sur les 7 803 bulles** des neuf
volumes de manga paginé (mesuré le 2026-08-25, cf. `docs/mesures/banc-2026-08-25.md`).

⚠ **Ce 11 est un plancher, et le lot 14 a dit pourquoi.** Il vient de `qa["restaurees"]`, or
deux planches du chapitre n'ont pas de `qa.json` du tout — leurs textes sont pourtant en cache,
alignés par position sur `regions.json`. Compté là, le chiffre est **13 sur 59** (22 %). C'est
le piège n° 1 de `tools/banc.py` retourné contre le banc lui-même, et c'est une raison de plus
de préférer `regions.json` comme dénominateur. Le rejeu complet est dans
`docs/mesures/webtoon-2026-08-26.md`, où le taux tombe à **15,1–17,0 %**.

## Le format d'annotation : aucun n'est inventé

**COCO instance segmentation**, celui que tout outil d'annotation exporte. Un seul fichier
`annotations.json` par corpus, les images à côté. La conversion se fait **à la lecture**
(`regions_de_verite`), et `ecrire_cache_verite` écrit la même vérité au format du pipeline
(`regions.json` + `masks.png`) — pour que la comparaison soit directe et que la vérité terrain
se relise avec les mêmes outils que le reste.

## La métrique qui décide n'est pas le F1

Rappel, précision et F1 sont là parce qu'ils sont attendus. Mais celle qui décide est :

> **le nombre de planches portant du texte et rendant zéro bulle.**

Une planche à 60 % de rappel produit un résultat imparfait qu'un relecteur corrige ; une
planche à zéro produit une page **entièrement non traduite** que personne ne voit passer. Une
moyenne de F1 les confond. Et à côté d'elle, promue au même rang par la mesure du webtoon :
**le taux de fausses détections par planche**.

⚠ **L'appariement passe par `detection_retry.apparier`, pas par une réimplémentation.** Il est
glouton, à IoU de masques ≥ 0,50, et son argument est le bon : « une bulle conservée est la
même bulle, pas une bulle au même endroit ». Deux implémentations mesureraient deux choses.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

#: Seuil d'IoU de masques de l'appariement. Repris de `detection_retry.apparier` (0,50), et
#: nommé ici parce qu'un banc publie ses seuils.
SEUIL_IOU = 0.50

#: Bornes des tranches de TAILLE de bulle, en pixels d'aire de masque. C'est là que se voit le
#: gain d'`input_size` (lot 12, L4.3) : un rappel global stable peut cacher un effondrement sur
#: les petites bulles, qui sont justement celles que le redimensionnement d'entrée écrase.
TRANCHES_AIRE = ((0, 2_000), (2_000, 10_000), (10_000, 40_000), (40_000, 10**12))

ANNOTATIONS = "annotations.json"


@dataclass
class Planche:
    """Une planche annotée : son image, sa taille, et ses bulles de vérité."""

    id: int
    fichier: str
    largeur: int
    hauteur: int
    polygones: list[list[float]] = field(default_factory=list)

    @property
    def est_bande(self) -> bool:
        return self.largeur > 0 and self.hauteur / self.largeur >= 3.0


@dataclass
class Corpus:
    """Un corpus annoté, tel qu'il est sur le disque."""

    racine: Path
    planches: list[Planche]
    licence: str = ""

    def chemin(self, planche: Planche) -> Path:
        return self.racine / planche.fichier


def charger_annotations(racine: Path | str) -> Corpus | None:
    """Lit `annotations.json` (COCO instance segmentation). `None` si le fichier manque.

    Seules les catégories nommées `bulle` / `speech_bubble` sont retenues : un corpus annoté
    pour autre chose (cases, onomatopées) reste lisible, il ne contribue simplement pas à
    cette mesure-ci."""
    racine = Path(racine)
    data = _lire(racine / ANNOTATIONS)
    if data is None:
        return None
    bulles = {c["id"] for c in data.get("categories") or []
              if str(c.get("name", "")).lower() in ("bulle", "bubble", "speech_bubble")}
    par_image: dict[int, list[list[float]]] = {}
    for a in data.get("annotations") or []:
        if bulles and a.get("category_id") not in bulles:
            continue
        for polygone in a.get("segmentation") or []:
            if len(polygone) >= 6:            # trois sommets minimum, sinon ce n'est pas une aire
                par_image.setdefault(a["image_id"], []).append([float(v) for v in polygone])
    planches = [
        Planche(id=im["id"], fichier=im["file_name"],
                largeur=int(im["width"]), hauteur=int(im["height"]),
                polygones=par_image.get(im["id"], []))
        for im in sorted(data.get("images") or [], key=lambda i: i.get("file_name", ""))
    ]
    return Corpus(racine=racine, planches=planches,
                  licence=str((data.get("info") or {}).get("licence", "")))


def _lire(chemin: Path):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def masque_de_polygones(polygones: list[list[float]], largeur: int, hauteur: int):
    """Rasterise des polygones COCO en un masque booléen pleine page.

    Passe par Pillow plutôt que par `pycocotools` : le dépôt refuse d'ajouter une dépendance
    binaire pour ce qu'un `ImageDraw.polygon` fait exactement pareil sur des polygones simples
    — et le corpus synthétique n'en produit pas d'autres."""
    import numpy as np
    from PIL import Image, ImageDraw
    toile = Image.new("L", (largeur, hauteur), 0)
    dessin = ImageDraw.Draw(toile)
    for polygone in polygones:
        points = list(zip(polygone[0::2], polygone[1::2]))
        if len(points) >= 3:
            dessin.polygon(points, fill=1)
    return np.asarray(toile, dtype=bool)


def regions_de_verite(planche: Planche):
    """Les bulles annotées d'une planche, en `BubbleRegion` — le type que tout le reste du
    dépôt manipule. C'est ce qui permet d'apparier la vérité et la prédiction avec la MÊME
    fonction que celle qui arbitre les relances de détection."""
    import numpy as np
    from manga.detection import BubbleRegion
    regions = []
    for polygone in planche.polygones:
        masque = masque_de_polygones([polygone], planche.largeur, planche.hauteur)
        if not masque.any():
            continue
        ys, xs = np.nonzero(masque)
        regions.append(BubbleRegion(
            bbox=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
            mask=masque, score=1.0, cls=0, kind="bulle"))
    return regions


def ecrire_cache_verite(ckpt_dir: Path, planche: Planche) -> None:
    """Écrit la vérité terrain au format du pipeline (`regions.json` + `masks.png`).

    Pourquoi convertir **vers** `regions.json` plutôt qu'inventer un format de comparaison :
    la vérité devient alors relisible par `tools/banc.py`, `tools/mesurer_bulles.py` et
    l'éditeur, exactement comme un tome réel. Une vérité terrain qu'on ne peut pas ouvrir avec
    ses outils habituels n'est vérifiée par personne."""
    from manga import checkpoints
    checkpoints.save_regions(Path(ckpt_dir), regions_de_verite(planche),
                             (planche.largeur, planche.hauteur))


# ---------------------------------------------------------------------------
# Les métriques
# ---------------------------------------------------------------------------

def _tranche(aire: int) -> str:
    for bas, haut in TRANCHES_AIRE:
        if bas <= aire < haut:
            return f"{bas}–{haut}" if haut < 10**12 else f"≥{bas}"
    return "?"


def mesurer_planche(verite: list, predites: list, *, seuil: float = SEUIL_IOU) -> dict:
    """Rappel, précision et fausses détections d'UNE planche, plus le détail par taille."""
    from manga.detection_retry import apparier
    appariement = apparier(verite, predites, seuil=seuil)
    trouvees = sum(1 for a in appariement if a is not None)
    par_tranche: dict[str, list[int]] = {}
    for region, a in zip(verite, appariement):
        aire = int(region.mask.sum()) if region.mask is not None else 0
        compteur = par_tranche.setdefault(_tranche(aire), [0, 0])
        compteur[0] += int(a is not None)
        compteur[1] += 1
    # Une prédiction qui recouvre DEUX bulles de vérité est un double non scindé, pas une
    # bulle de plus : `apparier` n'en retiendra qu'une, l'autre comptera comme manquée. Le
    # compter à part est ce qui distingue « le détecteur n'a pas vu » de « le détecteur a
    # fusionné » — deux défauts que le lot 13 traite différemment.
    fusions = _fusions(verite, predites, appariement, seuil=seuil)
    return {
        "verite": len(verite),
        "predites": len(predites),
        "trouvees": trouvees,
        "fausses": len(predites) - trouvees,
        "zero_alors_que_texte": bool(verite) and not predites,
        "fusions": fusions,
        "par_tranche": par_tranche,
    }


def _fusions(verite: list, predites: list, appariement: list, *, seuil: float) -> int:
    """Bulles de vérité manquées parce qu'une prédiction les avait fusionnées avec une
    voisine. Critère : la bulle manquée est recouverte à plus de la moitié par une prédiction
    déjà appariée à une autre."""
    import numpy as np
    prises = {a for a in appariement if a is not None}
    fusions = 0
    for region, a in zip(verite, appariement):
        if a is not None or region.mask is None:
            continue
        aire = int(region.mask.sum()) or 1
        for j in prises:
            autre = predites[j].mask
            if autre is None:
                continue
            if int(np.count_nonzero(region.mask & autre)) / aire > 0.5:
                fusions += 1
                break
    return fusions


def mesurer_corpus(racine: Path | str, *, predire=None, config: dict | None = None,
                   seuil: float = SEUIL_IOU) -> dict | None:
    """Le banc de détection complet sur un corpus annoté.

    `predire(image) -> list[BubbleRegion]` est injectable : la CI passe le vrai détecteur, un
    test unitaire passe une fonction déterministe. Sans lui, le détecteur est construit depuis
    `config` par `detection.depuis_config` — **la même fabrique que le pipeline**, sans quoi
    le banc mesurerait un autre détecteur que celui du run.

    ⚠ Les deux régimes sont séparés. Un manga paginé et un webtoon ne se moyennent pas : entre
    0 % et 19 % de zones restaurées selon le format (mesuré), une moyenne unique masquerait
    exactement le défaut qu'on cherche."""
    corpus = charger_annotations(racine)
    if corpus is None or not corpus.planches:
        return None
    if predire is None:
        predire = _detecteur_de_config(config)

    from PIL import Image
    par_planche = []
    for planche in corpus.planches:
        chemin = corpus.chemin(planche)
        if not chemin.exists():
            continue
        with Image.open(chemin) as im:
            predites = predire(im.convert("RGB"))
        mesure = mesurer_planche(regions_de_verite(planche), predites, seuil=seuil)
        mesure["planche"] = planche.fichier
        mesure["regime"] = "webtoon" if planche.est_bande else "manga"
        par_planche.append(mesure)
    if not par_planche:
        return None
    return {"corpus": str(corpus.racine), "licence": corpus.licence,
            "planches": par_planche,
            "global": agreger(par_planche),
            "par_regime": {r: agreger([m for m in par_planche if m["regime"] == r])
                           for r in sorted({m["regime"] for m in par_planche})}}


def _detecteur_de_config(config: dict | None):
    from manga.detection import BubbleDetector
    if config is None:
        from core.cli import charger_config
        config = charger_config(str(Path(__file__).resolve().parents[1] / "config.yaml"))
    detecteur = BubbleDetector.depuis_config(config["manga"]["detection"])

    def predire(image):
        return detecteur.regions_de_fenetres(detecteur.inferer_fenetres(image),
                                             image.size[1])
    return predire


def agreger(mesures: list[dict]) -> dict:
    """Le bilan, avec ses deux métriques de tête en premier. L'ordre n'est pas cosmétique : un
    lot qui gagne des bulles sans publier les fausses détections peut dégrader le résultat en
    affichant un succès."""
    verite = sum(m["verite"] for m in mesures)
    predites = sum(m["predites"] for m in mesures)
    trouvees = sum(m["trouvees"] for m in mesures)
    fausses = sum(m["fausses"] for m in mesures)
    n = len(mesures) or 1
    rappel = trouvees / verite if verite else 0.0
    precision = trouvees / predites if predites else 0.0
    tranches: dict[str, list[int]] = {}
    for m in mesures:
        for cle, (vus, total) in m["par_tranche"].items():
            courant = tranches.setdefault(cle, [0, 0])
            courant[0] += vus
            courant[1] += total
    return {
        "planches": len(mesures),
        "zéro alors que texte": sum(1 for m in mesures if m["zero_alors_que_texte"]),
        "fausses/planche": round(fausses / n, 3),
        "rappel": round(rappel, 4),
        "précision": round(precision, 4),
        "F1": round(2 * rappel * precision / (rappel + precision), 4)
        if (rappel + precision) else 0.0,
        "bulles annotées": verite,
        "bulles détectées": predites,
        "doubles non scindées": sum(m["fusions"] for m in mesures),
        "rappel par taille": {cle: round(vus / total, 3) if total else 0.0
                              for cle, (vus, total) in sorted(tranches.items())},
    }


def rendre(resultat: dict, *, markdown: bool = False) -> str:
    """Le bilan, imprimable. En Markdown, un tableau par régime plus un global."""
    from tools import _banc_commun as commun
    lignes = [{"régime": "**tous**", **resultat["global"]}]
    lignes += [{"régime": r, **bilan} for r, bilan in resultat["par_regime"].items()]
    colonnes = ["régime", *resultat["global"].keys()]
    tableau = commun.tableau_markdown(colonnes, lignes)
    if not markdown:
        return tableau
    return "\n".join([
        "# Banc de détection — corpus annoté", "",
        # Séparateurs normalisés : ce document est publié et relu sur d'autres machines
        # qu'un poste Windows.
        f"- **Corpus** : `{resultat['corpus'].replace(chr(92), '/')}`",
        f"- **Licence du corpus** : {resultat['licence'] or '(non déclarée)'}",
        f"- **Appariement** : `detection_retry.apparier`, IoU de masques ≥ {SEUIL_IOU:.2f}",
        "", tableau, "",
    ])
