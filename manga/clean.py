# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Nettoyage déterministe des bulles : repeint l'INTÉRIEUR de chaque bulle avec sa couleur
de fond mesurée — AUCUNE IA, aucune régénération de pixels.

C'est ce module (+ `typeset.py` pour l'écriture) qui garantit que le dessin n'est JAMAIS
altéré hors des bulles : tout pixel en dehors des masques ressort bit-à-bit identique à
l'original. C'est le principe directeur du plan de faisabilité — vérifié par
`tests/test_manga_clean.py` (comparaison pixel-à-pixel hors masque).

────────────────────────────────────────────────────────────────────────────────────────
Ce module a été réécrit pour corriger le défaut qui rendait le rendu du tome
inexploitable : **308 bulles sur 797, réparties sur 117 des 150 planches, étaient
repeintes en gris ou en noir** au lieu de blanc.

Cause exacte. `detection.py` renvoie le masque de **toute la bulle**, contour compris,
mais ce module était écrit comme si c'était un masque **de texte** (ses docstrings le
disaient). Il en tirait deux erreurs enchaînées :

  1. la couleur de fond était échantillonnée sur `ring = ~sub_mask` dans la bbox —
     c'est-à-dire sur les pixels **du dessin autour** de la bulle. D'où des fonds gris ou
     noirs pour des bulles parfaitement blanches (page 60 : (139,139,139), (118,118,118),
     (35,35,35), (112,112,112) — toutes blanches en réalité) ;
  2. remplir *tout* le masque effaçait le **trait de contour** de la bulle, qui est à
     cheval sur la frontière du masque.

Combiné au `fill=(0,0,0)` en dur de `typeset.py`, cela donnait du texte noir sur fond
noir. Le correctif tient en une idée : **éroder d'abord, mesurer et peindre ensuite**, à
l'intérieur seulement. Après réécriture, sur les mêmes 797 bulles, il ne reste que **2**
bulles à fond sombre — les deux qui le sont réellement (fond sombre, texte clair).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .detection import BubbleRegion
from .geometry import adaptive_radius, dilate, safe_erode

# Tolérance de luminance pour juger qu'un pixel « est » du fond, au sens du taux
# d'uniformité. Volontairement plus large que `seuil_texte` : on veut compter comme fond
# le grain du scan et la compression JPEG, pas seulement le fond parfaitement uni.
_TOL_UNIFORMITE = 25

# Demi-largeur de la classe modale retenue pour affiner la couleur (en luminance).
_AFFINAGE_LUMA = 16

# En dessous de cette fraction de l'intérieur, le « masque de texte » provisoire est jugé
# non significatif : on ne s'en sert alors pas pour déduire la polarité (une bulle vide de
# texte ne doit pas basculer en inversé sur trois pixels de poussière).
_MIN_FRACTION_TEXTE = 0.002

_DEFAUTS = {
    "marge_bord": 0.03,
    "mode": "auto",
    "seuil_uniformite": 0.60,
    "seuil_abandon": 0.35,
    "seuil_texte": 45,
    "dilatation_texte": 0.6,
    "couleur_texte_sombre": (0, 0, 0),
    "couleur_texte_clair": (255, 255, 255),
}


@dataclass
class BubbleStyle:
    """Tout ce que le nettoyage a MESURÉ sur une bulle, et dont le lettrage a besoin.

    Ces informations ne peuvent pas être redécouvertes après le nettoyage : sur une page
    déjà nettoyée, la bulle est uniforme, le masque de texte provisoire ressort vide et la
    polarité devient indéductible. C'est pourquoi l'orchestrateur analyse toujours l'image
    **d'origine** (qu'il ouvre de toute façon), y compris quand il reprend à `--from rendu`
    et recharge la page nettoyée depuis le disque."""
    bbox: tuple[int, int, int, int]
    interior: np.ndarray                  # bool, taille image — l'intérieur SÛR (érodé)
    background: tuple[int, int, int]
    background_luma: float
    text_color: tuple[int, int, int]
    inverted: bool
    uniformity: float
    erode_radius: int                     # rayon RÉELLEMENT appliqué (0 = repli brut)
    mode: str                             # "masque" | "texte"
    center_x: int
    ok: bool = True
    text_mask: np.ndarray | None = field(default=None, repr=False)


def _cfg(cfg: dict | None) -> dict:
    out = dict(_DEFAUTS)
    if cfg:
        out.update({k: v for k, v in cfg.items() if v is not None})
    return out


def _luma(px: np.ndarray) -> np.ndarray:
    """Luminance Rec. 601 sur un tableau de pixels RGB (…, 3) → (…)."""
    return px[..., 0] * 0.299 + px[..., 1] * 0.587 + px[..., 2] * 0.114


def _couleur_de_fond(px: np.ndarray) -> tuple[tuple[int, int, int], float]:
    """Couleur dominante d'un nuage de pixels : centre de la **classe modale** d'un
    histogramme de luminance à 32 classes, affiné à ±16, puis médiane RGB.

    ⚠ Le **mode**, et non la médiane ni un percentile haut. Sur la bulle inversée de
    `page_0044`, un p90 renverrait 193 — c'est-à-dire la couleur **du texte**. Le mode
    donne 255 sur bulle blanche, 4 sur bulle inversée, 212 sur bulle teintée, sans aucune
    hypothèse de polarité. Une médiane, elle, dériverait vers le texte dès qu'une bulle est
    dense en caractères."""
    lum = _luma(px)
    hist, bords = np.histogram(lum, bins=32, range=(0.0, 255.0))
    i = int(hist.argmax())
    centre = (bords[i] + bords[i + 1]) / 2.0
    proche = np.abs(lum - centre) <= _AFFINAGE_LUMA
    retenus = px[proche] if proche.any() else px
    fond = tuple(int(v) for v in np.median(retenus, axis=0))
    return fond, float(_luma(np.array(fond, dtype=float)))


def analyze_bubble(image: Image.Image, region: BubbleRegion,
                   cfg: dict | None = None) -> BubbleStyle:
    """Mesure le style d'une bulle sur l'image D'ORIGINE, sans rien écrire.

    Étapes, dans cet ordre parce que chacune dépend de la précédente :

    1. **Intérieur sûr** — `safe_erode` du masque, de `adaptive_radius` pixels. Le trait de
       contour (4-6 px, à cheval sur la frontière) reste donc **hors** de l'intérieur, et
       ne sera jamais réécrit.
    2. **Couleur de fond** — échantillonnée DANS cet intérieur (cf. `_couleur_de_fond`).
       C'est la correction du bug d'origine, qui échantillonnait le dessin autour.
    3. **Polarité héritée, pas déduite** — on construit un masque de texte provisoire
       `|lum − fond| > seuil_texte`, et `inverted` vaut « le texte est plus clair que le
       fond ». Une bulle grise à luma 140 avec du texte noir garde donc du texte noir, là
       où une règle « luma < 128 → texte blanc » basculerait arbitrairement.
    4. **Mode de remplissage** — selon l'uniformité de l'intérieur (cf. `clean_bubbles`)."""
    c = _cfg(cfg)
    arr = np.asarray(image.convert("RGB"))
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = region.bbox
    mask = region.mask

    # 1. intérieur sûr
    k = adaptive_radius(x1 - x0, y1 - y0, frac=c["marge_bord"])
    interior, k_eff = safe_erode(mask, k)

    if not interior.any():
        # Bulle dégénérée (masque vide) : on renvoie un style neutre marqué non-ok, et
        # `clean_bubbles` la laissera intacte. Ne jamais deviner du blanc et peindre.
        return BubbleStyle(
            bbox=region.bbox, interior=np.zeros((h, w), dtype=bool),
            background=(255, 255, 255), background_luma=255.0,
            text_color=tuple(c["couleur_texte_sombre"]), inverted=False,
            uniformity=0.0, erode_radius=0, mode="masque",
            center_x=(x0 + x1) // 2, ok=False)

    px = arr[interior]

    # 2. couleur de fond, mesurée DANS l'intérieur
    fond, fond_luma = _couleur_de_fond(px)

    # 3. polarité, héritée du contraste réel
    lum = _luma(px.astype(np.float64))
    ecart = np.abs(lum - fond_luma)
    est_texte = ecart > c["seuil_texte"]
    inverted = False
    if est_texte.mean() >= _MIN_FRACTION_TEXTE:
        inverted = bool(float(lum[est_texte].mean()) > fond_luma)

    # 4. uniformité → mode
    uniformity = float((ecart <= _TOL_UNIFORMITE).mean())
    mode = c["mode"]
    if mode not in ("masque", "texte", "aucun"):
        if uniformity >= c["seuil_uniformite"]:
            mode = "masque"
        elif uniformity >= c["seuil_abandon"]:
            mode = "texte"
        else:
            mode = "aucun"

    # Masque de texte plein cadre, utile au mode "texte" (et au rapport).
    text_mask = np.zeros((h, w), dtype=bool)
    text_mask[interior] = est_texte

    return BubbleStyle(
        bbox=region.bbox, interior=interior, background=fond,
        background_luma=fond_luma,
        text_color=tuple(c["couleur_texte_clair"] if inverted else c["couleur_texte_sombre"]),
        inverted=inverted, uniformity=uniformity, erode_radius=k_eff, mode=mode,
        center_x=_centre_x(interior, region.bbox), ok=True, text_mask=text_mask)


def _centre_x(interior: np.ndarray, bbox: tuple[int, int, int, int]) -> int:
    """Centroïde horizontal de l'intérieur — la colonne sur laquelle le texte sera centré,
    et celle que `width_profile` utilise pour choisir la plage contiguë. Le centre de la
    bbox ne convient pas : sur une bulle à queue latérale, il tombe à côté du corps."""
    par_colonne = interior.sum(axis=0)
    total = int(par_colonne.sum())
    if total == 0:
        return (bbox[0] + bbox[2]) // 2
    return int(round(float(par_colonne @ np.arange(interior.shape[1]) / total)))


def analyze_regions(image: Image.Image, regions: list[BubbleRegion],
                    cfg: dict | None = None) -> list[BubbleStyle]:
    """Styles de toutes les régions, dans l'ordre reçu. Les régions non-bulle
    (onomatopées, phase 2) reçoivent un style `ok=False` afin que la liste reste
    **alignée par position** avec `regions`, `ocr.json` et `traduction.json`."""
    out: list[BubbleStyle] = []
    for r in regions:
        if r.kind != "bulle":
            h, w = r.mask.shape[:2]
            x0, y0, x1, y1 = r.bbox
            out.append(BubbleStyle(
                bbox=r.bbox, interior=np.zeros((h, w), dtype=bool),
                background=(255, 255, 255), background_luma=255.0,
                text_color=(0, 0, 0), inverted=False, uniformity=0.0,
                erode_radius=0, mode="masque", center_x=(x0 + x1) // 2, ok=False))
        else:
            out.append(analyze_bubble(image, r, cfg))
    return out


def clean_bubbles(image: Image.Image, regions: list[BubbleRegion], cfg: dict | None = None,
                  styles_out: list[BubbleStyle] | None = None, *,
                  styles: list[BubbleStyle] | None = None) -> Image.Image:
    """Renvoie une COPIE de `image` où l'intérieur de chaque région « bulle » est repeint
    dans sa couleur de fond mesurée.

    Deux modes de remplissage, choisis par bulle selon l'uniformité de l'intérieur
    (`cfg["mode"] = "auto"` par défaut, forçable à `"masque"` ou `"texte"`) :

    · **`"masque"`** (uniformité ≥ `seuil_uniformite`) — remplir tout l'intérieur. C'est le
      cas nominal : propreté totale.
    · **`"texte"`** (≥ `seuil_abandon`) — ne remplir que le texte dilaté
      (`dilatation_texte` × rayon d'érosion, pour manger l'anti-crénelage des glyphes) : la
      bulle contient un peu de dessin ou une trame, le fond survit.
    · **`"aucun"`** (< `seuil_abandon`) — **ne rien peindre du tout**, et le signaler.

    Mesuré sur les 797 bulles du tome : uniformité médiane 0,892 · p5 0,770 · p1 0,591 ·
    minimum 0,131. Le seuil de 0,60 fait basculer 10 bulles en mode « texte ».

    Le troisième mode n'était pas prévu : il vient d'un contrôle visuel. Sur `page_0044`, le
    détecteur avait pris un **gratte-ciel** aux fenêtres sombres pour une bulle
    (uniformité 0,131, fond mesuré à luma 4, polarité « inversée »). En mode « texte », le
    masque de texte devient alors toute la **structure claire** du bâtiment, repeinte en
    noir : le dessin est détruit. Autrement dit, « limiter les dégâts » ne suffit pas quand
    la région n'est pas une bulle — il faut s'abstenir.

    Le seuil de 0,35 tombe dans un **creux net** de la distribution : les deux détections
    pathologiques sont à 0,131 et 0,226, la suivante à 0,457. Il isole donc exactement ces
    deux cas sur 797, sans toucher aux bulles légitimes qui contiennent du dessin. Une bulle
    abandonnée garde son texte japonais — visible, donc corrigible à la main — au lieu de
    coûter un morceau de planche. Les trois modes sont tracés dans `RAPPORT.md`.

    **Invariant garanti par construction** : une SEULE écriture, `out_arr[paint] = fond`,
    précédée de `paint &= region.mask`. Tout pixel hors des masques reste bit-à-bit
    identique à l'original.

    Rétro-compatibilité : `clean_bubbles(image, regions)` garde sa signature et son type de
    retour. Les styles remontent par le paramètre de sortie `styles_out` — le motif déjà
    utilisé côté LN (`render(..., stats=render_stats)`). `styles` (mot-clé) permet à
    l'inverse de réutiliser une analyse déjà faite sur l'image d'origine, ce dont
    l'orchestrateur a besoin pour ne pas la refaire deux fois."""
    c = _cfg(cfg)
    out_arr = np.asarray(image.convert("RGB")).copy()
    calcules = styles if styles is not None else analyze_regions(image, regions, cfg)

    for region, style in zip(regions, calcules):
        if styles_out is not None:
            styles_out.append(style)
        if region.kind != "bulle":
            continue   # texte sur dessin (onomatopées) : phase 2, non traité ici
        if not style.ok:
            continue   # masque dégénéré : ne rien peindre plutôt que deviner
        if style.mode == "aucun":
            continue   # ce n'est pas une bulle (cf. `seuil_abandon`) : on n'y touche pas

        if style.mode == "texte" and style.text_mask is not None:
            rayon = max(1, int(round(c["dilatation_texte"] * max(1, style.erode_radius))))
            paint = dilate(style.text_mask, rayon) & style.interior
        else:
            paint = style.interior

        # Filet explicite. `interior ⊆ erode(mask) ⊆ mask` rend ce `&=` redondant en
        # théorie ; on le garde parce que l'invariant « aucun pixel hors masque n'est
        # modifié » est le fondement de toute la brique et ne doit pas dépendre d'un
        # raisonnement.
        paint = paint & region.mask
        out_arr[paint] = style.background

    return Image.fromarray(out_arr)
