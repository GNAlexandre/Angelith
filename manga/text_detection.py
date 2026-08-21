# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Détection du texte posé SUR LE DESSIN — onomatopées, narration libre, cartouches.

## Pourquoi ce module existe

`manga/detection.py` ne connaît qu'une classe : la bulle. Sur les 1 593 régions des deux
tomes du *manga A*, `kind` vaut `"bulle"` **1 593 fois**. Tout ce qui est
écrit hors d'un ballon — les onomatopées géantes d'une page d'action, une pensée posée en
colonne dans un blanc de case — n'est donc ni détecté, ni nettoyé, ni traduit : il reste en
japonais sur la planche finale. C'était la limite de phase 1, assumée par le README.

Mesuré sur le Vol.2 : **23 planches sans aucune détection de bulle**, dont 13 de vrai
contenu (les pages 63 à 65 et 134 à 136 pèsent 450 à 720 Ko de dessin et de katakana). Le
Vol.1 a exactement le même défaut. Ce n'était pas une régression, c'était un angle mort.

## Ce que ce module fait, et ne fait pas

Il **lit**, comme `detection.py`. Il ne peint rien : le principe directeur de la brique —
« l'IA ne dessine jamais » — reste entier. `clean.py` n'est pas touché, aucun pixel du
dessin n'est repeint, et l'effacement des onomatopées (qui demanderait de reconstruire le
fond, donc un modèle génératif type LaMa) est délibérément **écarté**. Le texte trouvé ici
est traduit puis **glosé** à côté, par `typeset.py`.

## Le modèle, et pourquoi celui-là

`comic-text-detector` (dmMaze), export ONNX `mayocream/comic-text-detector-onnx`. Trois
sorties pour une entrée `[1, 3, 1024, 1024]` :

    blk  [1, 64512, 7]      tête YOLOv5 : boîtes de blocs de texte
    seg  [1, 1, 1024, 1024] masque de texte DENSE, déjà passé par sigmoïde
    det  [1, 2, 1024, 1024] cartes de lignes (style DBNet)

**On n'utilise que `seg`.** Mesuré sur les planches réelles du Vol.2, la tête `blk` rate
précisément ce qu'on vient chercher : page 63, elle propose 3 boîtes au-dessus de 0,5 —
toutes sur du petit texte horizontal — alors que la colonne de katakana géants qui barre la
planche est parfaitement dessinée dans `seg`. Une tête entraînée sur des *blocs de texte*
ne reconnaît pas un ゴォォォ de 400 px de haut ; un masque par pixel, si.

`seg` a un second avantage, décisif : il donne un **masque**, ce dont l'appariement
texte↔bulle a besoin (cf. `hors_des_bulles`).

Le RF-DETR 4 classes de *koharu* aurait fait les deux en une passe et mieux, mais il n'est
publié qu'en `safetensors` (il faudrait `torch` en dépendance dure) et ses poids sont sous
conditions Manga109 d'usage académique.

⚠ Licence : le code amont est GPL-3.0 et les poids sont entraînés pour partie sur
Manga109-s. À vérifier avant toute diffusion des planches produites — même vigilance que
pour les polices (cf. `templates/fonts/README.md`).
"""
from __future__ import annotations

import re

import numpy as np
from PIL import Image

from core import tokens

from .detection import BubbleRegion, _letterbox
from .geometry import composantes, dilate

INPUT_SIZE = 1024          # résolution d'entrée du modèle, fixe (pas de dimension dynamique)
SEUIL_MASQUE = 0.5
# Part du petit côté de la planche servant de rayon de GROUPEMENT. Une onomatopée est faite
# de traits disjoints — les deux barres d'un ゴ sont deux composantes connexes. Sans
# groupement, une seule onomatopée produirait dix régions, donc dix appels d'OCR et dix
# gloses. Le rayon doit franchir l'espace entre traits d'un même signe sans souder deux
# signes voisins : 0,008 × 1125 ≈ 9 px sur les planches du tome.
GROUPEMENT_FRAC = 0.008
AIRE_MIN = 1200            # px² — en dessous, c'est du bruit de trame, pas du lettrage
CONTAINMENT_BULLE = 0.90   # au-delà, le texte est DANS une bulle, donc déjà traité
# Écart maximal entre deux fragments d'un MÊME texte, en fraction de la taille du plus petit
# des deux. Un rayon de dilatation fixe ne peut pas marcher ici : l'espacement d'une
# onomatopée est proportionnel à sa taille. Mesuré page 63 du Vol.2 — la colonne ゴォォォ est
# faite de glyphes de ~90 px séparés de ~30 px : à 9 px de dilatation elle sortait en
# **8 zones**, donc huit lectures d'OCR, huit lignes de traduction et huit gloses
# contradictoires posées le long d'un seul son. Le critère relatif les réunit en une.
VOISINAGE_FRAC = 0.60


class TextDetector:
    """Enveloppe ONNX Runtime autour de `comic-text-detector`.

    Même forme que `detection.BubbleDetector` — et pour la même raison : séparer l'inférence
    (chère) du post-traitement (gratuit) rend un balayage de seuils abordable."""

    def __init__(self, model_path: str, providers: list[str] | None = None, *,
                 telechargement_auto: bool = True, model_url: str | None = None, dire=None):
        import onnxruntime as ort

        from . import models
        model_path = models.assurer_modele(
            model_path, url=model_url or models.TEXTE_URL,
            sha256=models.TEXTE_SHA256, octets_attendus=models.TEXTE_OCTETS,
            auto=telechargement_auto, quoi="de détection de texte", dire=dire)
        avail = ort.get_available_providers()
        wanted = providers or ["CPUExecutionProvider"]
        used = [p for p in wanted if p in avail] or ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(model_path), providers=used)
        self._input_name = self.session.get_inputs()[0].name

    def masque_texte(self, image: Image.Image, *, seuil: float = SEUIL_MASQUE) -> np.ndarray:
        """Masque booléen du texte de la planche, à la taille de l'image d'origine.

        ⚠ `seg` sort **déjà activé** (valeurs dans [0, 1]) : lui appliquer une sigmoïde de
        plus — le réflexe hérité de YOLOv8-seg, dont les prototypes sont des logits — ramène
        tout au-dessus de 0,5 et déclare 94 % de la planche « texte ». Constaté en mesurant."""
        w0, h0 = image.size
        tensor, _r, (dw, dh) = _letterbox(image, INPUT_SIZE)
        seg = self.session.run(None, {self._input_name: tensor})[1]
        carte = Image.fromarray((np.clip(seg[0, 0], 0.0, 1.0) * 255).astype(np.uint8))
        # Défaire le letterbox : retirer le padding gris, puis revenir à l'échelle d'origine.
        crop = (round(dw), round(dh), INPUT_SIZE - round(dw), INPUT_SIZE - round(dh))
        carte = carte.crop(crop).resize((w0, h0), Image.BILINEAR)
        return np.asarray(carte) >= seuil * 255


def _union_bulles(bulles: list[BubbleRegion], forme: tuple[int, int]) -> np.ndarray:
    union = np.zeros(forme, dtype=bool)
    for r in bulles:
        m = getattr(r, "mask", None)
        if m is not None and m.shape == forme:
            union |= m
    return union


# ─────────────────────────────────────────────────────────────────────────────
# Mobilier de page (filigranes de scan) — lot 13
#
# Mesuré sur les rendus v0.40.0 : sur les 448 zones hors bulle du Vol.1 du *manga A*,
# **283 sont des filigranes de scan** (`ＲａｗＬａｚｙ．ＳＩ`, `13DL.me`, `ＤＥＦＲａｍＡＳ`) —
# 63 %. manga B : 105 sur 217. On payait une lecture OCR et un appel LLM pour du mobilier
# de page, et le rapport en était noyé.
#
# Le discriminant n'est ni la position (un vrai texte peut occuper un coin) ni le contenu (l'OCR
# n'est pas fiable ici, cf. la réserve du mode « rapport ») : c'est la **récurrence
# géométrique**. Un filigrane revient à la MÊME place sur toutes les planches ; une onomatopée,
# jamais. C'est exactement le raisonnement que la brique LN tient déjà sur les bandeaux de PDF
# (`pipeline/extract.py`, `footer_frac_pages`), et on en reprend la formulation.
MOBILIER_FRAC_PLANCHES = 0.30
MOBILIER_IOU = 0.50
# Au-delà de cette part de la planche, une zone n'est jamais du mobilier : une onomatopée pleine
# page ne se répète pas d'une planche à l'autre, mais si elle le faisait on ne veut pas l'effacer
# du rapport pour autant.
MOBILIER_AIRE_MAX_FRAC = 0.05
# Sous ce nombre de planches, « récurrent » ne veut rien dire : deux bulles qui coïncident par
# hasard ne font pas un filigrane.
MOBILIER_MIN_PLANCHES = 3


def _iou_boites(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    aire_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    aire_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = aire_a + aire_b - inter
    return inter / union if union > 0 else 0.0


def mobilier_de_tome(pages: dict, *, frac_planches: float = MOBILIER_FRAC_PLANCHES,
                     iou: float = MOBILIER_IOU,
                     aire_max_frac: float = MOBILIER_AIRE_MAX_FRAC,
                     min_planches: int = MOBILIER_MIN_PLANCHES) -> tuple[set, list[dict]]:
    """Zones qui sont du **mobilier de page** et non du contenu.

    `pages` : `{numéro de planche: (liste de boîtes, (largeur, hauteur))}`.
    Renvoie `({(planche, index)}, groupes)` — `groupes` décrit ce qui a été écarté, pour que le
    rapport puisse le montrer et qu'un faux positif se voie.

    Regroupement glouton par recouvrement de boîtes : le coût est en O(zones × groupes), et il y
    a quelques centaines de zones par tome. Une zone ne peut jamais rejoindre un groupe où sa
    propre planche figure déjà — deux onomatopées superposées sur une même planche ne sont pas
    une récurrence."""
    porteuses = [p for p, (boites, _t) in pages.items() if boites]
    if len(porteuses) < min_planches:
        return set(), []

    groupes: list[dict] = []
    for planche in sorted(pages):
        boites, taille = pages[planche]
        largeur, hauteur = taille if taille else (0, 0)
        aire_page = max(1, int(largeur) * int(hauteur))
        for idx, boite in enumerate(boites):
            b = tuple(boite)
            aire = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
            if aire > aire_max_frac * aire_page:
                continue          # trop grande pour être un filigrane
            for g in groupes:
                if planche in g["planches"]:
                    continue
                if _iou_boites(b, g["boite"]) >= iou:
                    g["membres"].append((planche, idx))
                    g["planches"].add(planche)
                    break
            else:
                groupes.append({"boite": b, "membres": [(planche, idx)],
                                "planches": {planche}})

    seuil = max(min_planches, round(len(porteuses) * frac_planches))
    retenus = [g for g in groupes if len(g["planches"]) >= seuil]
    mobilier = {m for g in retenus for m in g["membres"]}
    description = [{"boite": list(g["boite"]), "planches": len(g["planches"]),
                    "zones": len(g["membres"])} for g in retenus]
    description.sort(key=lambda d: -d["planches"])
    return mobilier, description


# Lettres et chiffres, demi ou pleine chasse. Une zone hors bulle qui n'a AUCUN caractère
# japonais mais porte des lettres n'est pas du texte : c'est `manga-ocr` qui a halluciné sur du
# dessin (`ＥｌｅＨＴ`, `［ｉｓｕｃｅ］`, `ＯＦＦＦＩＮＥ`, `ＲａｙＬｉｎｇｅｒ．`). Un mot latin
# authentique dans une onomatopée japonaise est assez rare pour qu'on préfère le perdre.
_LETTRE_OU_CHIFFRE = re.compile(r"[A-Za-z0-9０-９Ａ-Ｚａ-ｚ]")

TRI_MOBILIER = "mobilier"        # récurrent à la même place — filigrane de scan
TRI_BRUIT = "bruit"              # aucun japonais, mais des lettres : hallucination d'OCR
TRI_PONCTUATION = "ponctuation"  # aucun japonais, aucune lettre : `！！`, `．．．`, `〜`
TRI_JAPONAIS = "japonais"        # à traduire


def trier_zone(texte: str, *, mobilier: bool = False) -> str:
    """Que faire d'une zone hors bulle : l'écarter, la rendre sans LLM, ou la traduire.

    Mesuré sur les deux tomes rendus en v0.40.0 — 448 zones (manga A Vol.1) et 217 (manga B) :

    |                       | manga A | manga B |
    |-----------------------|--------:|-------:|
    | mobilier (écarté)     |      92 |      0 |
    | bruit latin (écarté)  |      15 |     12 |
    | ponctuation (sans LLM)|      81 |     47 |
    | japonais (LLM)        |     260 |    158 |

    Soit **42 %** des zones du Vol.1 et **27 %** de celles de manga B retirées de la charge LLM,
    sans rien perdre de traduisible.

    ⚠ La ponctuation n'est PAS du bruit. `！！` posé à côté d'un visage stupéfait est du
    contenu, et `latiniser` le rend fidèlement en `!!` — mieux qu'un LLM, qui pourrait
    broder."""
    t = (texte or "").strip()
    if mobilier:
        return TRI_MOBILIER
    if not t:
        return TRI_BRUIT
    if tokens.CJK_TEXTE.search(t):
        return TRI_JAPONAIS
    return TRI_BRUIT if _LETTRE_OU_CHIFFRE.search(t) else TRI_PONCTUATION


def _boite(comp: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(comp)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _ecart(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Distance entre deux boîtes, 0 si elles se touchent ou se chevauchent."""
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return float(max(dx, dy))


def fusionner_proches(comps: list[np.ndarray], *,
                      facteur: float = VOISINAGE_FRAC) -> list[np.ndarray]:
    """Réunit les fragments d'un même texte, par un critère RELATIF à leur taille.

    Deux fragments appartiennent au même texte si l'écart entre leurs boîtes est inférieur à
    `facteur × taille du plus petit des deux`. C'est ce qui distingue les glyphes d'une même
    onomatopée (espacés proportionnellement à leur corps) de deux textes distincts, qu'un
    rayon de dilatation en pixels ne sait pas séparer : il faudrait qu'il soit grand pour
    réunir des katakana de 90 px, et petit pour ne pas souder deux répliques voisines.

    Union-find sur quelques dizaines de composantes — le coût quadratique est sans objet."""
    n = len(comps)
    if n < 2:
        return list(comps)
    boites = [_boite(c) for c in comps]
    # Taille caractéristique : le plus GRAND côté. Un `ー` d'allongement est un trait fin et
    # long — son petit côté vaut 5 px et le prendrait pour du bruit isolé.
    tailles = [max(b[2] - b[0], b[3] - b[1]) for b in boites]
    parent = list(range(n))

    def trouver(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            seuil = facteur * min(tailles[i], tailles[j])
            if _ecart(boites[i], boites[j]) <= seuil:
                ri, rj = trouver(i), trouver(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)

    groupes: dict[int, np.ndarray] = {}
    for i, comp in enumerate(comps):
        r = trouver(i)
        groupes[r] = comp if r not in groupes else (groupes[r] | comp)
    return list(groupes.values())


def hors_des_bulles(masque: np.ndarray, bulles: list[BubbleRegion], *,
                    containment: float = CONTAINMENT_BULLE,
                    groupement: int = 0, aire_min: int = AIRE_MIN,
                    voisinage: float = VOISINAGE_FRAC) -> list[BubbleRegion]:
    """Régions de texte qui ne sont PAS dans une bulle déjà détectée.

    L'appariement se fait par **containment de masques**, l'idée la plus directement
    réutilisable de *koharu* (`stages/detection.rs`) :

        part_dans_bulle = |texte ∩ bulle| / |texte|

    et non par IoU de boîtes. L'IoU compare deux aires globales : une réplique de 200 px²
    dans un ballon de 40 000 px² donne un IoU de 0,005 et serait déclarée « hors bulle »,
    alors qu'elle y est entièrement. Le containment répond à la seule question qui compte —
    *ce texte est-il déjà pris en charge ?* — et vaut ici 1,0.

    Le groupement précède l'appariement : on dilate, on étiquette, **puis** on érode le
    résultat pour rendre à chaque région son contour réel. Dilater sans rendre gonflerait le
    masque de glose et mordrait sur le dessin."""
    forme = masque.shape
    union = _union_bulles(bulles, forme)
    rayon = int(groupement) if groupement else max(2, round(min(forme) * GROUPEMENT_FRAC))

    # Le groupement ne sert QU'À décider ce qui fait région ; les pixels rendus restent ceux
    # du masque d'origine (`comp & masque`).
    groupe = dilate(masque, rayon)
    # Deux étages de groupement, et ils ne font pas le même travail : la dilatation soude les
    # TRAITS d'un même glyphe (elle est en pixels, calée sur la finesse du lettrage), la
    # fusion relative réunit les GLYPHES d'un même texte (elle est proportionnelle, calée sur
    # leur corps). Aucun rayon unique ne peut faire les deux.
    bruts = [c & masque for c in composantes(groupe, min_aire=1)]
    regions: list[BubbleRegion] = []
    for reel in fusionner_proches(bruts, facteur=voisinage):
        aire = int(reel.sum())
        if aire < aire_min:
            continue
        if union.any():
            dedans = int((reel & union).sum())
            if aire and dedans / aire >= containment:
                continue          # déjà dans une bulle : traité par le chemin nominal
        ys, xs = np.nonzero(reel)
        if ys.size == 0:
            continue
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        regions.append(BubbleRegion(bbox=bbox, mask=reel, score=1.0, cls=0,
                                    kind="onomatopee"))
    # Ordre de lecture manga : droite → gauche, puis haut → bas. Les onomatopées n'ont pas la
    # régularité d'une grille de bulles ; un tri direct suffit et reste reproductible.
    regions.sort(key=lambda r: (-r.bbox[2], r.bbox[1]))
    return regions
