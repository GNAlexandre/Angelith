# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Aperçu d'une planche, **un calque par bulle** — le même que le rendu final.

## Pourquoi des calques et pas une image

L'éditeur de la 1.1.0 affichait `pages_out/`, c'est-à-dire une image aplatie où le texte est
cuit dans les pixels. Il n'y avait donc rien à déplacer : ni item de texte dans la scène, ni
donnée de position nulle part. Le geste que l'on veut — traîner un bloc de texte, le
redimensionner, le recentrer — était impossible par construction.

Ici, le fond est la planche **nettoyée** et chaque réplique est un calque RGBA distinct,
produit par `typeset.calque_fit` : **exactement la fonction qu'utilise le rendu final**.
L'aperçu n'est donc pas une approximation, c'est le rendu, décomposé. Un déplacement se
traduit par une translation de calque — instantanée, sans recalcul — et le ré-habillage
n'intervient qu'au dépôt.

## Le coût, et pourquoi il est payé dans la file

Les styles de bulle (`inverted`, couleur de fond, uniformité) ne se mesurent que sur le **scan
d'origine** : sur une planche déjà nettoyée l'intérieur est uni, et la bulle blanche sur noir
de la page 44 deviendrait indéductible. Il faut donc l'image source, dont l'obtention peut
extraire une archive CBZ entière. C'est une tâche de fond, jamais un appel sur le fil
d'affichage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from manga import checkpoints, clean, rendu, typeset


@dataclass
class CalqueBulle:
    """Le texte d'une bulle, prêt à être posé sur la scène."""
    index: int
    image: Image.Image                     # RGBA
    x: int                                 # décalage dans la planche
    y: int
    rect: tuple[int, int, int, int]        # zone d'habillage effective (= masque de découpe)
    taille: int
    deborde: bool = False


@dataclass
class StyleCompact:
    """Un `BubbleStyle` sans ses masques PLEINE PAGE — la forme du ballon, recadrée et
    empaquetée à 1 bit par pixel.

    ## Pourquoi ne pas garder le style tel quel

    `BubbleStyle` porte `interior` **et** `text_mask`, deux booléens à la taille de la planche :
    3,7 Mo pièce sur un scan 1600×2300, soit ~74 Mo pour une planche de dix bulles. Or un
    `ApercuPlanche` va au cache LRU, plafonné à 120 Mo : garder les styles bruts viderait le
    cache dès la première planche, et l'on aurait payé le préchargement pour rien. C'est le
    même piège que `orchestrator_manga._bbox_des_styles` a désamorcé pour la traduction par
    lots (« ~350 Mo de masques pour 20 planches »).

    ## Pourquoi ne pas se contenter de la bbox

    Parce que `typeset._profil` mesure la largeur utilisable **ligne par ligne dans le masque**,
    et qu'une bulle n'est pas sa boîte : une bulle en éclat, un ballon à queue, un lobe de
    bulle scindée donneraient un tout autre habillage. On garde donc la forme, recadrée à sa
    bbox et empaquetée : ~15 ko pour une bulle de 300×400, 250 fois moins.

    ⚠ `text_mask` est **jeté**. Seul `clean.clean_bubbles` le lit (mode « texte ») ; le lettrage
    ne le regarde jamais. Un style déplié ne doit donc pas repartir vers le nettoyage."""
    # ⚠ DEUX boîtes, et les confondre change le rendu. `bbox` est celle du STYLE — la boîte de
    # la région, que `calque_fit` reporte dans `CalqueBulle.rect` et que l'éditeur enregistre
    # comme rectangle d'habillage. `fenetre` est l'emprise réelle du masque ÉRODÉ, qui est plus
    # petite (`safe_erode` retire 2 à 12 px) et ne sert qu'à recadrer les bits. Recalculer
    # `bbox` depuis le masque rétrécirait silencieusement le rectangle à chaque aller-retour.
    bbox: tuple[int, int, int, int]
    fenetre: tuple[int, int, int, int]     # emprise du crop empaqueté
    masque: bytes                          # np.packbits du crop — 1 bit par pixel
    forme: tuple[int, int]                 # (h, w) du crop ; packbits perd la forme
    page: tuple[int, int]                  # (H, W) de la planche
    background: tuple[int, int, int]
    background_luma: float
    text_color: tuple[int, int, int]
    inverted: bool
    uniformity: float
    erode_radius: int
    mode: str
    center_x: int
    ok: bool = True

    @property
    def octets(self) -> int:
        return len(self.masque)


def compacter(style) -> StyleCompact:
    """`BubbleStyle` → `StyleCompact`. Ne perd que ce que le lettrage n'utilise pas."""
    interieur = np.asarray(style.interior, dtype=bool)
    hauteur, largeur = interieur.shape[:2]
    ys, xs = np.nonzero(interieur)
    if ys.size == 0:
        fenetre, crop = (0, 0, 0, 0), np.zeros((0, 0), dtype=bool)
    else:
        fenetre = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        crop = interieur[fenetre[1]:fenetre[3], fenetre[0]:fenetre[2]]
    return StyleCompact(
        bbox=tuple(style.bbox), fenetre=fenetre,
        masque=np.packbits(crop).tobytes(), forme=crop.shape,
        page=(hauteur, largeur), background=tuple(style.background),
        background_luma=float(style.background_luma),
        text_color=tuple(style.text_color), inverted=bool(style.inverted),
        uniformity=float(style.uniformity), erode_radius=int(style.erode_radius),
        mode=str(style.mode), center_x=int(style.center_x), ok=bool(style.ok))


def deplier(compact: StyleCompact):
    """`StyleCompact` → `BubbleStyle` utilisable par le lettrage.

    L'allocation pleine page (`np.zeros`) passe par `calloc` : les pages ne sont touchées qu'à
    l'écriture, donc moins d'une milliseconde. Le style déplié est **transitoire** — il meurt à
    la fin du ré-habillage et n'entre jamais au cache."""
    hauteur, largeur = compact.page
    interieur = np.zeros((hauteur, largeur), dtype=bool)
    h, w = compact.forme
    if h and w:
        bits = np.unpackbits(np.frombuffer(compact.masque, dtype=np.uint8), count=h * w)
        x0, y0, _x1, _y1 = compact.fenetre
        interieur[y0:y0 + h, x0:x0 + w] = bits.reshape(h, w).astype(bool)
    return clean.BubbleStyle(
        bbox=compact.bbox, interior=interieur, background=compact.background,
        background_luma=compact.background_luma, text_color=compact.text_color,
        inverted=compact.inverted, uniformity=compact.uniformity,
        erode_radius=compact.erode_radius, mode=compact.mode,
        center_x=compact.center_x, ok=compact.ok, text_mask=None)


@dataclass
class ApercuPlanche:
    fond: Image.Image                      # la planche nettoyée, sans texte
    calques: list[CalqueBulle]
    qa: list[dict]
    # Ce qu'il faut pour RÉ-HABILLER une bulle sans rouvrir le scan. Tous optionnels : un
    # aperçu construit à la main (les tests le font) reste valable, il n'aura simplement pas
    # de chemin rapide — `recomposer_bulle` rendra `None` et l'appelant attendra la
    # composition complète.
    styles: dict[int, StyleCompact] = field(default_factory=dict)
    font_path: str | None = None
    cfg_typeset: dict | None = None


def composer(ckpt_dir: Path, chemin_clean: Path, image_source, *,
             textes: list[str], font_path: str | None, cfg_typeset: dict | None,
             cfg_nettoyage: dict | None = None,
             layouts: dict | None = None) -> ApercuPlanche:
    """Construit l'aperçu d'une planche : le fond nettoyé et un calque par réplique.

    ⚠ Passe par `rendu.rendre_planche` — le chemin partagé — et non par un appel direct à
    `typeset_page`. C'est ce qui garantit que ce qu'on voit à l'écran est ce que le pipeline
    écrira : mêmes polices résolues, même harmonisation de planche, mêmes replis.

    Le rendu travaille sur une COPIE : le fond rendu à l'appelant reste la planche nettoyée
    intacte, puisque c'est elle qu'on affichera sous les calques."""
    regions = checkpoints.load_regions(ckpt_dir)
    if regions is None:
        raise ValueError(f"aucune détection exploitable dans {ckpt_dir}")

    source = image_source if hasattr(image_source, "crop") else Image.open(image_source)
    source = source.convert("RGB")
    fond = Image.open(chemin_clean).convert("RGB")

    # Styles mesurés sur la SOURCE — seule image où la polarité d'une bulle est lisible.
    styles = clean.analyze_regions(source, regions, cfg_nettoyage)

    resultat = rendu.rendre_planche(
        fond.copy(), regions, textes, styles=styles, font_path=font_path,
        cfg_typeset=cfg_typeset, sources=checkpoints.load_ocr(ckpt_dir) or [],
        layouts=layouts, avec_fits=True)

    calques: list[CalqueBulle] = []
    for entree in resultat.fits:
        fit, style = entree["fit"], entree["style"]
        produit = typeset.calque_fit(fit, style, entree["police"])
        if produit is None:
            continue
        image, x, y = produit
        calques.append(CalqueBulle(
            index=entree["index"], image=image, x=x, y=y,
            rect=tuple(style.bbox), taille=int(fit.size),
            deborde=bool(fit.overflow)))

    # ⚠ Les styles viennent de `analyze_regions` ci-dessus, PAS de `resultat.fits` : ce dernier
    # ne contient que les bulles effectivement dessinées, donc une bulle vide n'y aurait aucun
    # style — et c'est justement celle où l'utilisateur va taper.
    return ApercuPlanche(
        fond=fond, calques=calques, qa=resultat.qa,
        styles={k: compacter(st) for k, st in enumerate(styles) if st is not None},
        font_path=font_path, cfg_typeset=cfg_typeset)


def recomposer_bulle(vue: ApercuPlanche, index: int, texte: str, *,
                     rect=None, taille: int | None = None,
                     masque=None) -> CalqueBulle | None:
    """Ré-habille UNE bulle, sans rouvrir le scan ni réanalyser la planche. `None` si on ne
    peut pas (pas de style connu, bulle vide, texte qui ne tient pas au corps demandé).

    ## Pourquoi c'est rapide

    Ce qui coûte 1,37 s dans `composer`, c'est l'ouverture du scan d'origine — qui peut
    extraire une archive CBZ entière — et `clean.analyze_regions`. L'aperçu ayant conservé les
    styles (`StyleCompact`), ré-habiller une bulle se réduit à `_profil` + `layout_at_size` +
    `calque_fit` : quelques millisecondes, assez pour suivre la frappe et le glisser.

    ## Ce qui garantit que c'est le MÊME lettrage

    ⚠ **Aucun lettrage n'est réécrit ici.** Chaque étape est la fonction qu'appelle
    `typeset_page` : `preparer_contenu`, `style_impose` / `style_depuis_masque`, `fit_impose` /
    `best_fit`, `calque_fit`. C'est la règle du dépôt — cf. `manga/rendu.py` et
    `test_manga_rendu.py::test_les_deux_chemins_donnent_la_meme_image` — et la seule façon de
    ne pas montrer à l'utilisateur autre chose que ce qui sera écrit.

    ⚠ **Seule divergence assumée : `harmonize`.** L'harmonisation ramène les bulles trop
    grandes vers la MÉDIANE DE LA PLANCHE ; elle ne peut pas se calculer sur une bulle isolée.
    Pendant le geste, une bulle hors norme s'affiche donc à sa taille non harmonisée ; la
    recomposition complète qui suit la rétablit. L'écart est borné par
    `harmonisation_ratio_max` et ne touche jamais la bulle dont on est en train de choisir la
    taille : celle-là porte `fit.impose`, que `harmonize` épargne déjà.

    `rect`, `taille` et `masque` décrivent ce que l'utilisateur est en train de faire, pas ce
    qui est enregistré : c'est ce qui permet d'afficher le résultat **avant** de l'écrire."""
    compact = (vue.styles or {}).get(index)
    if compact is None or not compact.ok:
        return None                        # aperçu pas encore composé : pas de chemin rapide
    cfg = typeset._cfg(vue.cfg_typeset)
    contenu, police, _subs, _sup = typeset.preparer_contenu(texte or "", cfg, vue.font_path)
    if not contenu.strip():
        return None                        # une bulle vidée n'a pas de calque, elle en perd un

    style = deplier(compact)
    if masque is not None:
        style = typeset.style_depuis_masque(style, masque)
    if rect is not None:
        # ⚠ Le rectangle est AUSSI le masque de découpe (cf. `style_impose`) : les deux ne
        # peuvent pas diverger, sinon un bloc traîné hors de sa bulle serait rogné à l'ancienne
        # forme et disparaîtrait — le pire mode d'échec possible pour un éditeur.
        style = typeset.style_impose(style, rect)
    if not style.ok or not style.interior.any():
        return None

    fit = None
    if taille:
        # Corps explicite : on l'honore ou on renonce. ⚠ Pas de repli sur `best_fit` ici — le
        # corps sauterait à une valeur autre que celle affichée dans le réglage, et le curseur
        # deviendrait impilotable. L'appelant garde le calque précédent ; la recomposition
        # complète appliquera le repli documenté, et rien n'est perdu.
        fit = typeset.fit_impose(contenu, style, cfg, police, {"taille": int(taille)})
    elif rect is not None:
        # Déplacer ne change pas le corps : c'est la promesse d'`entree_mise_en_page`.
        courant = next((c for c in vue.calques if c.index == index), None)
        if courant is not None:
            fit = typeset.fit_impose(contenu, style, cfg, police,
                                     {"taille": int(courant.taille)})
    if fit is None and not taille:
        # Ni corps imposé ni repli tenable : on cherche, exactement comme le rendu final.
        fit = typeset.best_fit(contenu, style, cfg, police)
    if fit is None:
        return None

    produit = typeset.calque_fit(fit, style, police)
    if produit is None:
        return None
    image, x, y = produit
    return CalqueBulle(index=index, image=image, x=x, y=y, rect=tuple(style.bbox),
                       taille=int(fit.size), deborde=bool(fit.overflow))


def entree_mise_en_page(calque: CalqueBulle | None, rect=None,
                        taille: int | None = None) -> dict:
    """Construit l'entrée de `mise_en_page.json` d'une bulle déplacée ou recorpsée.

    La taille est celle du calque courant, sauf demande explicite : déplacer un bloc ne doit
    pas changer son corps. C'est au réglage du corps, ou à un ré-habillage demandé, qu'elle
    bouge.

    `rect` est **optionnel** : imposer un corps sans imposer de cadre est un geste légitime, et
    fabriquer un rectangle depuis la bbox remplacerait l'intérieur du ballon par ses quatre
    coins (cf. `checkpoints.load_mise_en_page`).

    ⚠ Cette fonction a longtemps été écrite mais jamais appelée, pendant que
    `editeur._sur_texte_deplace` construisait son entrée à la main — et y perdait la taille,
    faute d'un attribut qui n'existait pas. C'est elle, désormais, l'unique constructeur."""
    entree: dict = {"ancre": "libre"}
    if rect is not None:
        x0, y0, x1, y1 = (int(round(v)) for v in rect)
        entree["rect"] = [x0, y0, x1, y1]
    corps = taille if taille else (int(calque.taille) if calque is not None else None)
    if corps:
        entree["taille"] = int(corps)
    return entree
