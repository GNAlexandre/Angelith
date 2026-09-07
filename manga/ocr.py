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

from ._config import fusion
from .detection import BubbleRegion

MODELE_OCR = "kha-white/manga-ocr-base"

# Nombre de bulles envoyées au modèle en un seul `generate()`.
#
# ⚠ Ce n'est PAS « le plus grand possible ». Mesuré sur 64 bulles réelles de manga A Vol.1
# (CPU, manga-ocr-base), en ms par bulle :
#
#     lot=1  446,9   ·  lot=4  399,0   ·  lot=8  362,0   ·  lot=16  377,7
#     lot=32 379,9   ·  lot=64 436,7  ← le gain a DISPARU
#
# Le rembourrage est ce qui retourne la courbe : les découpes de bulles ont des formes très
# inégales, et un lot large aligne tout sur la plus grande. À 64 on repaye en padding ce
# qu'on économise en aller-retours. Le plateau utile est 8–32, d'où 16.
#
# En pratique le lot réel est plus petit : une planche porte 5 bulles en médiane, 13 au plus
# (821 bulles sur les 150 planches de manga A Vol.1). Grouper ENTRE planches pour remplir le
# lot est délibérément écarté — l'OCR tourne sous `_filet`, dont l'isolation d'échec est PAR
# PLANCHE, et une lecture à cheval sur deux planches ferait tomber les deux ensemble.
#
# Le texte produit est identique à toutes les tailles mesurées ci-dessus : le décodage est
# glouton et indépendant par séquence. C'est vérifié bulle à bulle, pas déduit.
TAILLE_LOT = 16

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

        c = fusion(_DEFAUTS_OCR, cfg)
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
        return self._mocr(self._crop(image, region, background=background, cfg=cfg))

    def read_all(self, image: Image.Image, regions: list[BubbleRegion],
                 styles: list | None = None, cfg: dict | None = None) -> list[str]:
        """Lit toutes les bulles, dans l'ordre reçu (= l'ordre de lecture persisté).

        `styles` (optionnel, aligné par position) fournit la couleur de fond mesurée de
        chaque bulle — indispensable sur une bulle inversée.

        Les bulles partent au modèle **en un seul lot par planche** plutôt qu'une par une.
        Le décodage est glouton et indépendant par séquence : le texte est identique bulle à
        bulle, ce qui est la seule raison pour laquelle ce regroupement est acceptable — et
        c'est vérifié, pas supposé (cf. `TAILLE_LOT` et `tests/test_manga_ocr_lot.py`)."""
        crops = []
        for i, r in enumerate(regions):
            fond = None
            if styles is not None and i < len(styles) and getattr(styles[i], "ok", False):
                fond = styles[i].background
            crops.append(self._crop(image, r, background=fond, cfg=cfg))
        return self._lire_crops(crops)

    def _crop(self, image: Image.Image, region: BubbleRegion,
              background: tuple[int, int, int] | None = None,
              cfg: dict | None = None) -> Image.Image:
        """Le découpage que `read` fait avant d'appeler le modèle, isolé pour être groupé."""
        c = fusion(_DEFAUTS_OCR, cfg)
        if not c["masquer_hors_bulle"]:
            return image.crop(region.bbox)
        return masked_crop(image, region, background=background or (255, 255, 255),
                           marge=int(c["marge_crop"]),
                           agrandissement_min=int(c["agrandissement_min"]))

    def _lire_crops(self, crops: list[Image.Image]) -> list[str]:
        """Lit une liste de découpes en lots. Retombe sur la lecture une-à-une si l'API
        d'`manga_ocr` bouge — le gain est un confort, la lecture ne l'est pas."""
        if not crops:
            return []
        try:
            sorties: list[str] = []
            for i in range(0, len(crops), TAILLE_LOT):
                sorties += self._lot(crops[i:i + TAILLE_LOT])
            return sorties
        except Exception:      # noqa: BLE001 — cf. la docstring : on relit, on n'échoue pas
            return [self._mocr(c) for c in crops]

    def _lot(self, crops: list[Image.Image]) -> list[str]:
        """UN `generate()` pour tout le lot.

        ⚠ Le prétraitement reproduit `MangaOcr.__call__` à la lettre, `convert("L")` compris :
        c'est cette conversion en niveaux de gris qui fixe ce que le ViT voit, et l'omettre
        changerait les lectures sans rien signaler."""
        from manga_ocr.ocr import post_process

        m = self._mocr
        gris = [c.convert("L").convert("RGB") for c in crops]
        px = m.processor(images=gris, return_tensors="pt").pixel_values
        ids = m.model.generate(px.to(m.model.device), max_length=300)
        return [post_process(m.tokenizer.decode(i, skip_special_tokens=True))
                for i in ids.cpu()]


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


def _coupe_xy(groupe: list[BubbleRegion], rtl: bool = True) -> list[BubbleRegion]:
    """Coupe X-Y récursive d'un groupe de bulles.

    À chaque niveau on cherche la plus grande gouttière horizontale et la plus grande
    gouttière verticale, **en écart normalisé** par l'étendue du groupe, et on coupe selon la
    plus franche :
      · coupe horizontale → le groupe du **haut**, puis celui du **bas** ;
      · coupe verticale   → celui de **droite** puis celui de **gauche** si `rtl` (sens
        manga), l'inverse sinon (webtoon, BD occidentale).

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
    entier avant celle de gauche. C'est exactement le comportement voulu.

    ⚠ Délégué à `_coupe_ruptures` depuis le lot 15 : c'est **exactement le même parcours**,
    dont on retient en plus la largeur de la gouttière qui a séparé chaque paire voisine.
    Cette fonction n'en garde que l'ordre, et reste donc iso-comportement au bit près."""
    return _coupe_ruptures(groupe, rtl)[0]


def _coupe_ruptures(groupe: list[BubbleRegion], rtl: bool = True,
                    etendue: tuple[int, int] | None = None
                    ) -> tuple[list[BubbleRegion], list[float], bool]:
    """La coupe X-Y de `_coupe_xy`, qui rend en plus **ce qui sépare** chaque paire voisine.

    Renvoie `(ordre, ruptures, repli)` :
      · `ordre` — identique à `_coupe_xy`, au bit près ;
      · `ruptures` — `len(ordre) - 1` valeurs : la gouttière qui sépare `ordre[i]` de
        `ordre[i+1]`, **normalisée par l'étendue de la PLANCHE** sur l'axe de la coupe ;
      · `repli` — vrai si le repli diagonal a servi quelque part.

    ## Pourquoi il n'y avait aucun « arbre de découpage » à faire remonter

    Il n'en existait jamais. Les trois retours de `_coupe_xy` sont des **concaténations de
    listes** : le regroupement n'existait que comme partition transitoire de listes locales
    sur la pile d'appels, et disparaissait au retour. Le modèle recevait « 1..N » et devait
    deviner que 1-2-3 étaient dans la même case.

    Plutôt que de rendre un `list[list[BubbleRegion]]` — qui aurait obligé à décider *dans*
    la récursion à quel niveau un groupe s'arrête, question à laquelle la géométrie seule ne
    répond pas — on rend la **mesure** qui permet de le décider après coup : la largeur de la
    gouttière entre deux voisins. `manga.planche.groupes_de_ruptures` en tire les groupes,
    avec un seuil qui, lui, est mesurable et réglable.

    ⚠ La normalisation des `ruptures` se fait par l'étendue de la **planche entière**, pas du
    sous-groupe courant. La normalisation locale de `_coupe_xy` est ce qui rend l'ARBITRAGE
    entre les deux axes correct (cf. le damier 2×2 ci-dessus) ; elle est en revanche
    inutilisable pour comparer deux coupes de profondeurs différentes, puisque l'étendue
    rétrécit à chaque niveau — deux bulles collées au fond d'un sous-groupe minuscule
    afficheraient une gouttière « énorme ». Les deux normalisations coexistent donc, chacune
    pour la question qu'elle sait trancher.

    ⚠ Le repli diagonal (l'ancien commentaire disait « à poids égal », ce qui est faux : à
    poids exactement égal c'est la coupe horizontale qui gagne, par le `>=` ci-dessous) ne
    laisse AUCUNE gouttière derrière lui : ses ruptures valent `0.0` et le drapeau `repli`
    remonte. Un groupement dont on sait qu'il est incertain doit être annoncé comme tel, pas
    présenté comme une structure."""
    if len(groupe) <= 1:
        return list(groupe), [], False

    gx0 = min(r.bbox[0] for r in groupe)
    gx1 = max(r.bbox[2] for r in groupe)
    gy0 = min(r.bbox[1] for r in groupe)
    gy1 = max(r.bbox[3] for r in groupe)
    etendue_x = max(1, gx1 - gx0)
    etendue_y = max(1, gy1 - gy0)
    # Étendue de la PLANCHE : posée au premier appel, transmise inchangée dans la récursion.
    planche_x, planche_y = etendue if etendue else (etendue_x, etendue_y)

    gap_h, coupe_h = _gouttiere([(r.bbox[1], r.bbox[3]) for r in groupe])
    gap_v, coupe_v = _gouttiere([(r.bbox[0], r.bbox[2]) for r in groupe])
    dims = (planche_x, planche_y)

    if coupe_h is not None and gap_h / etendue_y >= gap_v / etendue_x:
        haut = [r for r in groupe if r.bbox[3] <= coupe_h]
        bas = [r for r in groupe if r.bbox[3] > coupe_h]
        if haut and bas:
            oh, rh, ph = _coupe_ruptures(haut, rtl, dims)
            ob, rb, pb = _coupe_ruptures(bas, rtl, dims)
            return oh + ob, rh + [gap_h / planche_y] + rb, ph or pb

    if coupe_v is not None:
        droite = [r for r in groupe if r.bbox[0] >= coupe_v]
        gauche = [r for r in groupe if r.bbox[0] < coupe_v]
        if droite and gauche:
            premier, second = (droite, gauche) if rtl else (gauche, droite)
            o1, r1, p1 = _coupe_ruptures(premier, rtl, dims)
            o2, r2, p2 = _coupe_ruptures(second, rtl, dims)
            return o1 + o2, r1 + [gap_v / planche_x] + r2, p1 or p2

    # Aucune gouttière exploitable (bulles qui se chevauchent sur les deux axes, mise en
    # page très libre) : repli sur une diagonale haut→bas, du côté de départ vers l'autre.
    ecart_x = ((lambda r: (gx1 - r.bbox[2])) if rtl else (lambda r: r.bbox[0] - gx0))
    ordre = sorted(groupe, key=lambda r: (r.bbox[1] - gy0) / etendue_y
                   + ecart_x(r) / etendue_x)
    return ordre, [0.0] * (len(ordre) - 1), True


def reading_order(regions: list[BubbleRegion],
                  sens: str = "droite_gauche") -> list[BubbleRegion]:
    """Ordre de lecture, haut → bas, par **coupe X-Y récursive**.

    `sens` vient du FORMAT de la planche (`manga.formats.<format>.rendu.sens_lecture`, via
    `manga.formats.sens_lecture`) : `"droite_gauche"` pour un manga, `"gauche_droite"` pour
    un webtoon ou une BD occidentale. ⚠ Il ne se déduit **pas** de la langue source — un scan
    anglais d'un manga japonais se lit toujours droite→gauche.

    Remplace une agrégation par chevauchement vertical calculée **sur toute la largeur de la
    page**, qui entrelaçait deux cases côte à côte : sur la page 20, cinq bulles appartenant
    à deux cases distinctes se retrouvaient dans la même « bande », donc lues en zigzag
    d'une case à l'autre. Le dialogue traduit s'en trouvait mélangé — sans aucune alerte,
    puisque le nombre de bulles restait juste.

    ⚠ L'ordre produit ici est celui persisté dans `regions.json`, et `ocr.json` /
    `traduction.json` s'y alignent **par position**. Changer `sens` sur un tome déjà détecté
    invalide donc ses checkpoints — d'où le sens enregistré dans le bloc de provenance de
    `checkpoints.save_regions`, qui permet de n'invalider que les pages réellement
    concernées plutôt que d'incrémenter `FORMAT_VERSION` (ce qui retraduirait TOUS les
    projets existants)."""
    if not regions:
        return []
    return _coupe_xy(list(regions), str(sens) != "gauche_droite")


def ordre_et_ruptures(regions: list[BubbleRegion],
                      sens: str = "droite_gauche",
                      taille: tuple[int, int] | None = None
                      ) -> tuple[list[BubbleRegion], list[float], bool]:
    """`reading_order`, plus la **gouttière qui sépare chaque paire voisine** (cf.
    `_coupe_ruptures`).

    C'est le seul point d'entrée public de la mesure : `manga.planche` la consomme pour
    construire les groupes annoncés au traducteur, et le reste du dépôt continue d'appeler
    `reading_order`, dont la sortie est inchangée.

    ⚠ `taille` est la taille de la PLANCHE, et il faut la donner. Sans elle, les gouttières
    sont normalisées par l'étendue des bulles elles-mêmes — si bien qu'un seuil de 4,5 %
    signifie 72 px sur une planche bien remplie et 13 px sur une planche qui ne porte que deux
    répliques voisines. Le même écart de 20 px y serait tantôt un simple interligne, tantôt
    une rupture de mise en page. Rapportée à la planche, la mesure veut dire la même chose
    partout, ce qui est la condition pour qu'un seuil soit calibrable."""
    if not regions:
        return [], [], False
    return _coupe_ruptures(list(regions), str(sens) != "gauche_droite",
                           (max(1, taille[0]), max(1, taille[1])) if taille else None)
