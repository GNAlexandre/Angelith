# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""OCR japonais des bulles détectées, via le modèle DÉDIÉ `manga-ocr`
(kha-white/manga-ocr-base — ViT+BERT, spécialisé texte manga vertical/stylisé).

Volontairement PAS le LLM de traduction pour cette étape : un modèle dédié à l'OCR
est nettement plus fiable sur le japonais vertical, les furigana et les polices
stylisées manga qu'un modèle de vision généraliste (cf. plan de faisabilité, § 2).
Le rôle « vision » du LLM (optionnel, `manga.mode_traduction: vision`) est de
traduire avec le contexte visuel de la planche — pas de faire l'OCR lui-même.

Ce module porte aussi l'**ordre de lecture**, qui est le pivot de toute la brique :
`regions.json`, `ocr.json` et `traduction.json` s'alignent PAR POSITION sur lui.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .detection import BubbleRegion

MODELE_OCR = "kha-white/manga-ocr-base"

_DEFAUTS_OCR = {
    "masquer_hors_bulle": True,
    "marge_crop": 6,
    "agrandissement_min": 64,
    "hors_ligne": "auto",
}


def dossier_cache(modele: str = MODELE_OCR) -> str | None:
    """Dossier local du modèle s'il est DÉJÀ en cache, `None` sinon. **N'accède pas au réseau.**

    `snapshot_download(local_files_only=True)` ne fait que résoudre le cache : il lève si le
    modèle n'y est pas, et ne télécharge jamais."""
    try:
        from huggingface_hub import snapshot_download
        return snapshot_download(modele, local_files_only=True)
    except Exception:
        return None


class MangaOCR:
    """Charge le modèle une seule fois (coûteux) puis lit des bulles à la volée."""

    def __init__(self, cfg: dict | None = None, *, dire=None):
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        # ⚠ AVANT d'importer `manga_ocr`. L'avertissement « ViTImageProcessor requires
        # torchvision » est émis à l'import de `ViTImageProcessor`, pas à celui de
        # `transformers` — le poser ici le fait taire, torchvision installé ou non. Les
        # ERREURS remontent toujours, et les lignes de `manga_ocr` lui-même (« Loading OCR
        # model… », « Using CPU », « OCR ready ») restent visibles.
        import transformers.utils.logging as journal_hf
        journal_hf.set_verbosity_error()

        c = {**_DEFAUTS_OCR, **(cfg or {})}
        brut = c.get("hors_ligne", "auto")
        mode = "auto" if isinstance(brut, str) and brut.lower() == "auto" else bool(brut)
        source = MODELE_OCR
        if mode is not False:
            # Charger depuis le CHEMIN local plutôt que par identifiant de dépôt. Sinon
            # `from_pretrained` contacte le Hub à CHAQUE lancement pour revalider la
            # révision : latence réseau, avertissement « unauthenticated requests », échec
            # hors ligne — et surtout une nouvelle révision peut arriver en plein tome et
            # changer l'OCR sans prévenir. Le chemin local fige la révision.
            local = dossier_cache(MODELE_OCR)
            if local:
                source = local
            elif mode is True:
                raise SystemExit(
                    f"OCR : `manga.ocr.hors_ligne: true` exige que {MODELE_OCR} soit déjà en "
                    f"cache, et il ne l'est pas.\n"
                    f"  → lance une fois avec `hors_ligne: auto` (le défaut) pour le "
                    f"télécharger, ou mets `false`.")
            elif dire is not None:
                dire(f"OCR : {MODELE_OCR} absent du cache — premier téléchargement "
                     f"(~424 Mo), une seule fois.")

        from manga_ocr import MangaOcr    # nom de classe upstream (casse différente)
        self._mocr = MangaOcr(pretrained_model_name_or_path=source)

    def read(self, image: Image.Image, region: BubbleRegion,
             background: tuple[int, int, int] | None = None,
             cfg: dict | None = None) -> str:
        """Lit une bulle. Par défaut, la bulle est **isolée** de son voisinage avant l'OCR
        (cf. `masked_crop`) ; `background` est la couleur mesurée de la bulle."""
        c = {**_DEFAUTS_OCR, **(cfg or {})}
        if not c["masquer_hors_bulle"]:
            return self._mocr(image.crop(region.bbox))
        return self._mocr(masked_crop(
            image, region, background=background or (255, 255, 255),
            marge=int(c["marge_crop"]), agrandissement_min=int(c["agrandissement_min"])))

    def read_all(self, image: Image.Image, regions: list[BubbleRegion],
                 styles: list | None = None, cfg: dict | None = None) -> list[str]:
        """Lit toutes les bulles, dans l'ordre reçu (= l'ordre de lecture persisté).

        `styles` (optionnel, aligné par position) fournit la couleur de fond mesurée de
        chaque bulle — indispensable sur une bulle inversée."""
        sorties: list[str] = []
        for i, r in enumerate(regions):
            fond = None
            if styles is not None and i < len(styles) and getattr(styles[i], "ok", False):
                fond = styles[i].background
            sorties.append(self.read(image, r, background=fond, cfg=cfg))
        return sorties


def masked_crop(image: Image.Image, region: BubbleRegion,
                background: tuple[int, int, int] = (255, 255, 255),
                marge: int = 6, agrandissement_min: int = 64) -> Image.Image:
    """Découpe la bulle en **effaçant tout ce qui l'entoure**.

    `image.crop(region.bbox)` recadre un rectangle : sur une planche dense, le texte de la
    bulle voisine entre dans le cadre et `manga-ocr` le lit aussi, ce qui pollue la
    traduction sans qu'aucun compteur ne s'en aperçoive.

    On part donc d'une toile **unie de la couleur mesurée de la bulle**, et on n'y recolle
    l'original que là où le masque est vrai. ⚠ La couleur mesurée, pas du blanc : sur une
    bulle inversée (fond sombre, texte clair), une toile blanche autour d'un texte clair
    détruirait le contraste et donc l'OCR.

    Le masque utilisé est le masque **brut**, contour de bulle compris — c'est à cela que
    `manga-ocr` a été entraîné, et le trait aide le modèle à cadrer le texte. Les petites
    bulles sont agrandies ×2 en LANCZOS : sous ~64 px, le ViT perd beaucoup.
    """
    arr = np.asarray(image.convert("RGB"))
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = region.bbox
    x0 = max(0, int(x0) - marge)
    y0 = max(0, int(y0) - marge)
    x1 = min(w, int(x1) + marge)
    y1 = min(h, int(y1) + marge)
    if x1 <= x0 or y1 <= y0:
        return Image.new("RGB", (1, 1), background)

    sub = arr[y0:y1, x0:x1]
    m = region.mask[y0:y1, x0:x1]
    if not m.any():
        # Masque dégénéré (vide dans la bbox) : on ne sait rien de la forme de la bulle.
        # Repli sur le rectangle brut plutôt que de rendre une toile unie — sans quoi l'OCR
        # lirait une image vide et renverrait du bruit, en silence.
        out = Image.fromarray(sub)
    else:
        toile = np.empty_like(sub)
        toile[:] = np.asarray(background, dtype=sub.dtype)
        toile[m] = sub[m]
        out = Image.fromarray(toile)
    if min(out.size) < agrandissement_min:
        out = out.resize((out.width * 2, out.height * 2), Image.LANCZOS)
    return out


def region_rectangulaire(region: BubbleRegion) -> BubbleRegion:
    """La même région, masque REMPLI à sa boîte — pour l'OCR du texte sur dessin.

    ⚠ À rebours de ce que fait `masked_crop` pour une bulle, et c'est une MESURE qui l'impose.
    Isoler le texte hors bulle sur son seul masque d'encre paraissait mieux : fond uni,
    contraste maximal. Comparé sur les zones réelles du Vol.2, c'est nettement PIRE —

        zone (241,1115) page 25 · encre nue → `人間の場所．．．`   (inventé)
                                 · crop brut → `ああ．．．陽弥．．．` (correct)
        zone (30,30)   page 25 · encre nue → `民主の人とセックスを` (inventé)
                                 · crop brut → `ＲａｗＬａｚｙ．ｓ．`  (le filigrane, exact)

    `manga-ocr` est un ViT entraîné sur des **imagettes de manga**, traits d'origine et
    anti-crénelage compris. Le masque de segmentation coupe au pixel près : il retire
    justement les demi-teintes dont l'encodeur se sert, et le modèle — qui produit toujours
    une phrase plausible — comble par de l'hallucination.

    C'est le seul point où *koharu* avait raison contre notre réflexe : il croppe au rectangle
    brut. À l'INTÉRIEUR d'une bulle, le masquage reste indispensable (il empêche la bulle
    voisine d'entrer dans le cadre) ; hors bulle, il nuit."""
    plein = np.zeros_like(region.mask)
    x0, y0, x1, y1 = region.bbox
    plein[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=region.bbox, mask=plein, score=region.score, cls=region.cls,
                        kind=region.kind)


def fond_pour_texte(image: Image.Image, region: BubbleRegion) -> tuple[int, int, int]:
    """Couleur de toile à utiliser pour OCRiser du texte posé SUR LE DESSIN.

    Hors d'un ballon, il n'y a pas de « couleur de bulle » à mesurer : le fond est du dessin,
    et le recopier autour des lettres rendrait l'OCR aussi difficile que sur la planche. On
    prend donc le contrepied de l'encre — texte sombre → toile blanche, texte clair → toile
    noire — ce qui donne exactement ce sur quoi `manga-ocr` a été entraîné : des glyphes
    contrastés sur un fond uni.

    La polarité se lit sur le masque lui-même, qui ne contient QUE les pixels d'encre (c'est
    un masque de segmentation de texte, pas une boîte). Une onomatopée blanche cernée de noir
    — le cas le plus fréquent sur une page d'action sombre — sort donc en blanc sur noir, et
    non en blanc sur blanc."""
    arr = np.asarray(image.convert("RGB"))
    m = region.mask
    if m is None or not m.any():
        return (255, 255, 255)
    encre = float(np.asarray(arr[m], dtype=np.float32).mean())
    return (255, 255, 255) if encre < 128 else (0, 0, 0)


# --------------------------------------------------------------------------- #
# Ordre de lecture — coupe X-Y récursive
# --------------------------------------------------------------------------- #

def _gouttiere(intervalles: list[tuple[int, int]]) -> tuple[float, float | None]:
    """Plus grande **gouttière** (intervalle vide) d'un ensemble de segments 1-D.

    Renvoie `(largeur, coordonnée_de_coupe)`, ou `(0.0, None)` s'il n'y a aucun trou : les
    segments se recouvrent alors de bout en bout."""
    if len(intervalles) < 2:
        return 0.0, None
    ordre = sorted(intervalles)
    fin = ordre[0][1]
    meilleure, coupe = 0.0, None
    for debut, f in ordre[1:]:
        if debut > fin and (debut - fin) > meilleure:
            meilleure, coupe = float(debut - fin), (fin + debut) / 2.0
        fin = max(fin, f)
    return meilleure, coupe


def _coupe_xy(groupe: list[BubbleRegion]) -> list[BubbleRegion]:
    """Coupe X-Y récursive d'un groupe de bulles.

    À chaque niveau on cherche la plus grande gouttière horizontale et la plus grande
    gouttière verticale, **en écart normalisé** par l'étendue du groupe, et on coupe selon la
    plus franche :
      · coupe horizontale → le groupe du **haut**, puis celui du **bas** ;
      · coupe verticale   → le groupe de **droite**, puis celui de **gauche** (sens manga).

    C'est *panel-aware sans jamais détecter les cases* : les gouttières entre cases **sont**
    les gouttières entre groupes de bulles. Le tout sans le moindre modèle.

    ⚠ Un point subtil sur la normalisation. Un damier 2×2 de cases est géométriquement
    **ambigu** : rien, dans les boîtes seules, ne dit s'il faut lire en rangées ou en
    colonnes — seule la convention de la bande dessinée tranche (en rangées). Normaliser par
    l'étendue du groupe résout le cas de lui-même sur une planche réelle : une page de manga
    est plus **haute** que large, donc à gouttières de tailles comparables (ce qu'elles sont
    en pratique, ~40 px dans les deux sens) l'écart normalisé est plus grand sur l'axe
    vertical, et la coupe en rangées gagne. Vérifié sur une géométrie de planche réelle
    1125×1600 : l'ordre sort bien rangée par rangée, de droite à gauche.

    À l'inverse, quand la gouttière verticale est franchement plus large que l'horizontale —
    deux cases côte à côte contenant chacune des bulles empilées, cas de la page 20 : 260 px
    contre 20 px — c'est la coupe verticale qui gagne, et la case de droite est lue en
    entier avant celle de gauche. C'est exactement le comportement voulu."""
    if len(groupe) <= 1:
        return list(groupe)

    gx0 = min(r.bbox[0] for r in groupe)
    gx1 = max(r.bbox[2] for r in groupe)
    gy0 = min(r.bbox[1] for r in groupe)
    gy1 = max(r.bbox[3] for r in groupe)
    etendue_x = max(1, gx1 - gx0)
    etendue_y = max(1, gy1 - gy0)

    gap_h, coupe_h = _gouttiere([(r.bbox[1], r.bbox[3]) for r in groupe])
    gap_v, coupe_v = _gouttiere([(r.bbox[0], r.bbox[2]) for r in groupe])

    if coupe_h is not None and gap_h / etendue_y >= gap_v / etendue_x:
        haut = [r for r in groupe if r.bbox[3] <= coupe_h]
        bas = [r for r in groupe if r.bbox[3] > coupe_h]
        if haut and bas:
            return _coupe_xy(haut) + _coupe_xy(bas)

    if coupe_v is not None:
        droite = [r for r in groupe if r.bbox[0] >= coupe_v]
        gauche = [r for r in groupe if r.bbox[0] < coupe_v]
        if droite and gauche:
            return _coupe_xy(droite) + _coupe_xy(gauche)

    # Aucune gouttière exploitable (bulles qui se chevauchent sur les deux axes, mise en
    # page très libre) : repli sur une diagonale droite→gauche, haut→bas.
    return sorted(groupe, key=lambda r: (r.bbox[1] - gy0) / etendue_y
                  + (gx1 - r.bbox[2]) / etendue_x)


def reading_order(regions: list[BubbleRegion]) -> list[BubbleRegion]:
    """Ordre de lecture manga (droite → gauche, haut → bas), par **coupe X-Y récursive**.

    Remplace une agrégation par chevauchement vertical calculée **sur toute la largeur de la
    page**, qui entrelaçait deux cases côte à côte : sur la page 20, cinq bulles appartenant
    à deux cases distinctes se retrouvaient dans la même « bande », donc lues en zigzag
    d'une case à l'autre. Le dialogue traduit s'en trouvait mélangé — sans aucune alerte,
    puisque le nombre de bulles restait juste.

    ⚠ L'ordre produit ici est celui persisté dans `regions.json`, et `ocr.json` /
    `traduction.json` s'y alignent **par position**. Le changer invalide donc les
    checkpoints existants : d'où `checkpoints.FORMAT_VERSION = 2` et
    `checkpoints.migrate_page()`, qui réordonne les textes déjà calculés au lieu de tout
    recalculer."""
    if not regions:
        return []
    return _coupe_xy(list(regions))
