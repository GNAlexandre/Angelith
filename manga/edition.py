# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Édition MANUELLE des zones d'une planche — ajouter, déplacer, supprimer, scinder une bulle.

## Le seul écrivain de `regions.json` en dehors du pipeline

La détection automatique manque des ballons, en fusionne deux, ou en invente. Jusqu'ici la
seule réponse était `--page N --conf S`, c'est-à-dire redemander au réseau — et accepter tout
ce qu'il renvoie. Ce module permet de corriger UNE zone à la main, et il est délibérément
séparé de l'interface graphique : il ne connaît ni Qt ni pixels d'écran, seulement le cache.
C'est ce qui le rend testable avec `pytest` et réutilisable par un script.

## Ce qui est repris, et pourquoi ce n'est pas `invalider_textes`

`checkpoints.invalider_textes` supprime `ocr.json`, `traduction.json` et `qa.json` dès que le
nombre de régions change. C'est la bonne réponse à une **re-détection**, qui rebat toutes les
régions d'un coup : plus rien ne correspond, et l'alignement par position est irrécupérable.

Ce serait la mauvaise réponse ici. Ajouter une bulle oubliée sur une planche qui en compte sept
jetterait les six autres — six traductions déjà payées, et les corrections manuelles avec.
D'où un **appariement par IoU** entre l'ancien et le nouveau jeu de régions : ce qui est
resté la même bulle garde son OCR, sa traduction ET sa correction manuelle, même si l'ordre de
lecture a changé. Seules les zones réellement nouvelles ou modifiées sont marquées à relire.

Le motif n'est pas inventé pour l'occasion : `checkpoints.migrate_page` calcule déjà une
permutation v1→v2 et l'applique aux textes plutôt que de tout invalider, et
`detection_retry.apparier` fournit déjà l'appariement glouton par IoU décroissante.

## Deux invariants qu'on ne peut pas relâcher

**L'ordre de lecture est le pivot.** `ocr.json` et `traduction.json` s'alignent sur
`regions.json` PAR POSITION. Toute opération recalcule donc `ocr.reading_order` et applique la
permutation aux textes — y compris aux clés de `traduction_manuelle.json`, qui sont des index
de bulle et pointeraient sinon la mauvaise réplique.

**Les masques ne se chevauchent pas.** `masks.png` est une image d'ÉTIQUETTES (0 = fond,
i+1 = bulle i) : un pixel appartient à une seule région, et deux masques qui se recouvrent
verraient le second effacer le premier au rechargement, silencieusement. Une zone dessinée à la
main peut parfaitement empiéter sur une voisine — d'où `_rendre_disjoints`, qui attribue chaque
pixel contesté à la première région dans l'ordre de lecture.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import checkpoints, document
from . import ocr as ocr_mod
from . import geometry
from .detection import BubbleRegion

FORMES = ("rectangle", "ellipse")

# Au-dessous, deux régions ne sont plus « la même bulle » et le texte n'est pas reporté. Plus
# bas que le 0,50 de `detection_retry.apparier` : ici l'utilisateur a délibérément retaillé une
# zone, souvent largement, et lui refaire payer l'OCR d'une bulle qu'il vient d'ajuster de
# quelques pixels serait absurde. Un déplacement franc vers une AUTRE bulle passe, lui, bien
# sous ce seuil.
SEUIL_REPORT = 0.30

# Aire minimale d'un lobe issu d'une scission, en pixels. En dessous, c'est une bavure du trait
# de coupe, pas un ballon.
AIRE_LOBE_MIN = 200


class ErreurEdition(Exception):
    """Opération impossible — l'appelant l'affiche telle quelle.

    Une exception plutôt qu'un `SystemExit` : le dépôt réserve `SystemExit` aux problèmes de
    configuration détectés en ligne de commande, et une interface graphique ne doit pas mourir
    parce qu'on a dessiné une zone hors de la planche."""


# ─────────────────────────────────────────────────────────────────────────────
# Masques
# ─────────────────────────────────────────────────────────────────────────────

def masque_de_forme(forme: str, bbox, taille: tuple[int, int]) -> np.ndarray:
    """Masque booléen plein d'un rectangle ou d'une ellipse, à la taille de la planche.

    L'ellipse n'est pas un raffinement : un ballon est rond, et un masque rectangulaire laisse
    aux quatre coins du fond de case que le nettoyage repeindrait en blanc (`mode: "masque"`
    remplit tout l'intérieur du masque). Le dessin passe par Pillow, déjà requis par la brique
    — pas d'OpenCV, cf. l'en-tête de `requirements-manga.txt`."""
    if forme not in FORMES:
        raise ErreurEdition(f"forme inconnue : {forme!r} (attendu : {', '.join(FORMES)})")
    largeur, hauteur = taille
    x0, y0, x1, y1 = (int(round(v)) for v in bbox)
    x0, x1 = sorted((max(0, min(x0, largeur)), max(0, min(x1, largeur))))
    y0, y1 = sorted((max(0, min(y0, hauteur)), max(0, min(y1, hauteur))))
    if x1 - x0 < 2 or y1 - y0 < 2:
        raise ErreurEdition(
            f"zone trop petite ou hors de la planche : {bbox} sur une planche "
            f"{largeur}×{hauteur}")
    img = Image.new("L", (largeur, hauteur), 0)
    dessin = ImageDraw.Draw(img)
    boite = [x0, y0, x1 - 1, y1 - 1]
    (dessin.ellipse if forme == "ellipse" else dessin.rectangle)(boite, fill=255)
    return np.asarray(img) > 127


def etirer_masque(masque: np.ndarray, bbox_source, bbox_cible,
                  taille: tuple[int, int]) -> np.ndarray:
    """Le masque d'une bulle, ÉTIRÉ de `bbox_source` vers `bbox_cible`. Même forme, autre boîte.

    C'est l'opération d'un redimensionnement par poignées, et elle diffère volontairement de
    `masque_de_forme` : celui-ci REMPLACE la forme par un rectangle ou une ellipse neufs, ce
    qui jette la queue qui pointe vers le locuteur, les dentelures d'une bulle de cri, les deux
    lobes d'une bulle que le détecteur a fusionnés. Étirer le masque existant fait d'un
    agrandissement un agrandissement, et non un remplacement.

    ⚠ **NEAREST, jamais BILINEAR.** Un masque est booléen. Un rééchantillonnage lisse suivi
    d'un seuillage grignote un demi-pixel de contour par côté, et surtout **dissout les détails
    fins en réduction** : une queue de 3 px moyennée à 0,4× tombe à ~40 % de gris, donc sous le
    seuil, donc disparaît sans que rien ne le signale. NEAREST préserve la connexité et est
    idempotent — réétirer vers la même boîte est l'identité. Ses marches d'escalier en fort
    agrandissement sont sans conséquence : `clean.analyze_bubble` érode ensuite de 2 à 12 px, et
    ce que l'œil voit d'un ballon est son TRAIT dessiné, pas le masque qui le recouvre.

    ⚠ Pillow, pas scipy ni OpenCV — cf. l'en-tête de `requirements-manga.txt` et celui de
    `manga/geometry.py` : les deux sont écartés du projet, et Pillow fait déjà exactement ce
    travail pour `masque_de_forme`."""
    largeur, hauteur = taille
    sx0, sy0, sx1, sy1 = (int(round(v)) for v in bbox_source)
    cx0, cy0, cx1, cy1 = (int(round(v)) for v in bbox_cible)
    cx0, cx1 = sorted((max(0, min(cx0, largeur)), max(0, min(cx1, largeur))))
    cy0, cy1 = sorted((max(0, min(cy0, hauteur)), max(0, min(cy1, hauteur))))
    if cx1 - cx0 < 2 or cy1 - cy0 < 2:
        raise ErreurEdition(
            f"zone trop petite ou hors de la planche : {tuple(bbox_cible)} sur une planche "
            f"{largeur}×{hauteur}")

    crop = np.asarray(masque, dtype=bool)[sy0:sy1, sx0:sx1]
    if crop.size == 0 or not crop.any():
        raise ErreurEdition(
            "le masque de cette zone est vide : il n'y a rien à étirer. Retrace-la avec "
            "« Redessiner ».")

    sortie = np.zeros((hauteur, largeur), dtype=bool)
    if (sx0, sy0, sx1, sy1) == (cx0, cy0, cx1, cy1):
        # Rien à rééchantillonner. Ce n'est pas qu'une optimisation : un déplacement pur doit
        # être EXACTEMENT une translation, sans le pixel de contour que NEAREST peut décaler à
        # l'aller-retour. C'est ce qui rend `retailler_zone` utilisable pour un simple glisser.
        sortie[cy0:cy1, cx0:cx1] = crop
        return sortie
    vignette = Image.fromarray(crop.astype(np.uint8) * 255, mode="L")
    etiree = vignette.resize((cx1 - cx0, cy1 - cy0), Image.NEAREST)
    sortie[cy0:cy1, cx0:cx1] = np.asarray(etiree) > 127
    return sortie


def bbox_du_masque(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Boîte englobante d'un masque, au format `(x0, y0, x1, y1)` exclusif à droite/en bas —
    la convention de `BubbleRegion.bbox`, celle que lisent le lettrage et le rapport."""
    try:
        return document._bbox_du_masque(mask)
    except document.ErreurDocument as err:
        raise ErreurEdition(str(err)) from err


# `rendre_disjoints` vit dans `manga/document.py` : c'est le cœur pur, partagé avec le document
# tamponné de l'éditeur. L'alias garde le nom historique lisible depuis ce module.
_rendre_disjoints = document.rendre_disjoints


# ─────────────────────────────────────────────────────────────────────────────
# Réécriture du cache
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContextePlanche:
    """Ce dont une opération de zone a besoin pour REPEINDRE la planche nettoyée.

    Optionnel, et c'est délibéré : `manga/edition.py` doit rester utilisable sur un cache seul
    (c'est ce que font tous ses tests). Quand le contexte est fourni, chaque zone touchée est
    vidée dans `pages_clean/` ; sans lui, seules les métadonnées bougent.

    ⚠ `image_source` est le SCAN D'ORIGINE, pas la planche nettoyée. La polarité d'une bulle
    (`inverted`) ne se mesure que là : sur une planche déjà nettoyée, l'intérieur est uni et le
    texte blanc sur noir de la page 44 deviendrait indéductible — c'est exactement pourquoi le
    balayage B recalcule les styles depuis la source plutôt que de les transporter."""

    image_source: object                 # PIL.Image ou chemin
    chemin_clean: Path
    cfg_nettoyage: dict | None = None


def repeindre_clean(ctx: "ContextePlanche", a_vider: list[BubbleRegion],
                    a_restaurer: list[BubbleRegion]) -> dict:
    """Met `pages_clean/` d'accord avec les zones qu'on vient d'éditer.

    **C'est le correctif du défaut le plus visible de la 1.1.0** : `ajouter_zone` ne touchait
    jamais la planche nettoyée, et aucune des étapes de reprise proposées par l'éditeur
    (`rendu`, `traduction`, `ocr`) ne relance le nettoyage — `downstream("rendu")` vaut
    `{"rendu"}`. Le lettrage recomposait donc sur une planche où la nouvelle zone n'avait
    jamais été vidée, et le français s'écrivait **par-dessus** le japonais.

    Deux gestes symétriques, **dans cet ordre** (cf. l'avertissement dans le corps) :

    · `a_restaurer` — les zones SUPPRIMÉES ou abandonnées par un redimensionnement.
    · `a_vider` — les zones nouvelles ou redessinées. Le style est mesuré sur le SCAN
      D'ORIGINE (polarité, couleur de fond, uniformité : indéductibles d'une planche déjà
      nettoyée) puis peint sur la planche nettoyée, via le mot-clé `styles=` de
      `clean_bubbles`. Mesurer ici, peindre là : c'est exactement ce que ce paramètre existe
      pour permettre.
    · `a_restaurer` — les zones SUPPRIMÉES. Une fausse détection déjà nettoyée a laissé un
      aplat blanc sur le dessin ; on y recolle les pixels d'origine. Sans ça, retirer une
      fausse bulle laissait un trou définitif que rien ne signalait.

    ⚠ L'invariant du nettoyage tient inchangé : **aucun pixel hors des masques traités n'est
    modifié**. `clean_bubbles` ne peint que dans l'intérieur érodé, et la restauration ne
    recopie que sous le masque retiré.

    Renvoie `{"vidées": n, "restaurées": n, "abandons": [index…]}` — `abandons` liste les
    zones que le nettoyage a refusé de peindre (`mode: "aucun"`, intérieur trop peu uniforme),
    parce qu'une bulle non vidée gardera son japonais et que l'utilisateur doit le savoir."""
    from . import clean

    chemin = Path(ctx.chemin_clean)
    if not chemin.exists():
        raise ErreurEdition(
            f"{chemin.name} est absent : la planche n'a jamais été nettoyée, il n'y a rien à "
            f"repeindre. Lance `--page N --from nettoyage` d'abord.")
    source = ctx.image_source
    if not hasattr(source, "crop"):
        source = Image.open(source)
    source = source.convert("RGB")
    page = Image.open(chemin).convert("RGB")

    # ⚠ **RESTAURER D'ABORD, VIDER ENSUITE.** L'ordre inverse était un défaut silencieux :
    # `modifier_zone` et `retailler_zone` passent la MÊME bulle des deux côtés (son ancienne
    # emprise à restaurer, sa nouvelle à vider), et restaurer en dernier recollait le japonais
    # de la source par-dessus la zone qu'on venait de nettoyer. La bulle ressortait avec son
    # texte d'origine, sous lequel le lettrage écrivait ensuite le français. La docstring de
    # `modifier_zone` promettait déjà cet ordre-ci ; seul le code disait le contraire.
    for region in a_restaurer:
        # Recolle le dessin d'origine sous la zone retirée. `Image.paste` avec un masque ne
        # touche que les pixels du masque — l'invariant tient.
        masque = Image.fromarray((region.mask * 255).astype(np.uint8), mode="L")
        page.paste(source, (0, 0), masque)

    abandons: list[int] = []
    if a_vider:
        # Mesure sur la SOURCE, peinture sur la planche nettoyée.
        styles = [clean.analyze_bubble(source, r, ctx.cfg_nettoyage) for r in a_vider]
        abandons = [k for k, st in enumerate(styles)
                    if getattr(st, "mode", "") == "aucun" or not getattr(st, "ok", False)]
        page = clean.clean_bubbles(page, a_vider, ctx.cfg_nettoyage, styles=styles)

    page.save(chemin)
    return {"videes": len(a_vider), "restaurees": len(a_restaurer), "abandons": abandons}


def _charger(ckpt_dir: Path) -> tuple[list[BubbleRegion], tuple[int, int]]:
    regions = checkpoints.load_regions(ckpt_dir)
    taille = checkpoints.taille_image(ckpt_dir)
    if regions is None or taille is None:
        raise ErreurEdition(
            f"aucune détection exploitable dans {ckpt_dir} — la planche n'a pas encore été "
            f"détectée, ou son cache est dans un format périmé (lance `--page N "
            f"--from detection`).")
    return regions, taille


def _reecrire(ckpt_dir: Path, anciennes: list[BubbleRegion],
              nouvelles: list[BubbleRegion], touchees: set[int], *,
              ctx: "ContextePlanche | None" = None,
              retirees: list[BubbleRegion] | None = None,
              relire: bool = True) -> dict:
    """Calcule le nouvel état, l'écrit, puis repeint la planche nettoyée.

    ⚠ Le CALCUL n'est plus ici : il vit dans `manga/document.py:poser_regions`, d'où le
    document tamponné de l'éditeur le tire aussi. C'est la même règle que pour
    `manga/rendu.py` — deux implémentations de « qu'est-ce qui est conservé, qu'est-ce qui est
    perdu » finiraient par diverger, et celle-ci décide du sort de traductions déjà payées.

    Ne reste ici que le mode **écriture immédiate** : celui d'un script ou d'un appel unitaire,
    par opposition au document, qui accumule en mémoire jusqu'à `enregistrer()`.

    `ctx` déclenche la repeinte de `pages_clean/` (cf. `repeindre_clean`). Sans lui, seules les
    métadonnées bougent — c'est le mode qu'utilisent les tests, et il reste légitime pour un
    script qui ne fait que réordonner."""
    try:
        etat = document.lire_etat(ckpt_dir)
    except document.ErreurDocument as err:
        raise ErreurEdition(str(err)) from err
    # L'appelant a construit `nouvelles` à partir de `anciennes`, qui peut différer de l'état
    # relu si quelqu'un a écrit entre-temps ; on fait foi de ce que l'appelant a vu.
    etat = document.EtatPlanche(
        regions=list(anciennes), ocr=etat.ocr, traduction=etat.traduction,
        manuelles=etat.manuelles, origines=etat.origines,
        mises_en_page=etat.mises_en_page, taille=etat.taille, sens=etat.sens)
    try:
        neuf, rapport = document.poser_regions(etat, nouvelles, touchees, relire=relire)
    except document.ErreurDocument as err:
        raise ErreurEdition(str(err)) from err

    document.ecrire_etat(ckpt_dir, neuf, motif="edition_manuelle")

    # Repeinte de la planche NETTOYÉE — après l'écriture des métadonnées, pour qu'un échec de
    # peinture laisse un cache cohérent plutôt qu'un demi-état.
    rapport["nettoyage"] = None
    if ctx is not None:
        # ⚠ `indices_touches`, pas `indices_a_relire` : avec `relire=False` (une retaille) le
        # second est VIDE, et s'y fier laisserait la planche nettoyée en désaccord avec le
        # masque qu'on vient de changer.
        touchees_finales = set(rapport.get("indices_touches")
                               or rapport["indices_a_relire"])
        rapport["nettoyage"] = repeindre_clean(
            ctx, [neuf.regions[i] for i in sorted(touchees_finales)], list(retirees or []))
    return rapport


# ─────────────────────────────────────────────────────────────────────────────
# Opérations
# ─────────────────────────────────────────────────────────────────────────────

def ajouter_zone(ckpt_dir: Path, bbox, *, forme: str = "rectangle",
                 ctx: ContextePlanche | None = None) -> dict:
    """Ajoute une bulle que la détection a manquée. Les autres gardent leurs textes.

    Avec `ctx`, la zone est aussi VIDÉE dans `pages_clean/` — sans quoi le lettrage écrirait
    le français par-dessus le japonais, la planche nettoyée n'ayant jamais connu cette bulle."""
    anciennes, taille = _charger(ckpt_dir)
    mask = masque_de_forme(forme, bbox, taille)
    # `score=1.0` : la zone vient de l'utilisateur, pas du réseau. C'est la valeur qu'utilise
    # déjà `sfx.json` pour les zones non issues d'un score de confiance, et elle évite qu'une
    # bulle posée à la main soit rangée parmi les détections douteuses du rapport.
    neuve = BubbleRegion(bbox=bbox_du_masque(mask), mask=mask, score=1.0, cls=0)
    nouvelles = list(anciennes) + [neuve]
    return _reecrire(ckpt_dir, anciennes, nouvelles, {len(nouvelles) - 1}, ctx=ctx)


def modifier_zone(ckpt_dir: Path, index: int, bbox, *, forme: str = "rectangle",
                  ctx: ContextePlanche | None = None) -> dict:
    """Redessine la zone `index`. Son OCR et sa traduction sont remis à zéro — les pixels
    lus ont changé, le texte qu'on en avait tiré ne vaut plus."""
    anciennes, taille = _charger(ckpt_dir)
    _verifier_index(index, anciennes)
    mask = masque_de_forme(forme, bbox, taille)
    nouvelles = list(anciennes)
    ancienne = nouvelles[index]
    nouvelles[index] = BubbleRegion(bbox=bbox_du_masque(mask), mask=mask,
                                    score=ancienne.score, cls=ancienne.cls,
                                    kind=ancienne.kind, scindee=ancienne.scindee)
    # L'ancienne emprise est restaurée avant que la nouvelle ne soit vidée : une zone
    # rétrécie laisserait sinon un aplat blanc là où le dessin doit revenir.
    return _reecrire(ckpt_dir, anciennes, nouvelles, {index}, ctx=ctx, retirees=[ancienne])


def retailler_zone(ckpt_dir: Path, index: int, bbox, *,
                   ctx: ContextePlanche | None = None) -> dict:
    """Redimensionne ou déplace la zone `index` en ÉTIRANT son masque. **Garde son texte.**

    C'est le geste des poignées, et c'est la différence avec `modifier_zone` : celui-ci repart
    d'une forme neuve, donc les pixels lus ne sont plus les mêmes et l'OCR ne vaut plus rien.
    Ici la bulle reste la même bulle, un peu plus grande ou un peu à côté — lui refaire payer
    une lecture, voire une traduction, à chaque ajustement de quelques pixels rendrait le geste
    inutilisable. L'appariement par IoU reste le juge : une zone traînée sur une AUTRE bulle
    tombe sous `SEUIL_REPORT` et perd son texte comme il se doit.

    Déplacer, c'est retailler à taille constante — une seule opération pour les deux gestes,
    donc rien qui puisse diverger entre eux.

    Avec `ctx`, la planche nettoyée est mise d'accord : l'ancienne emprise est rendue au dessin
    AVANT que la nouvelle ne soit vidée, sans quoi une zone rétrécie laisserait un aplat blanc
    là où le dessin doit revenir."""
    anciennes, taille = _charger(ckpt_dir)
    _verifier_index(index, anciennes)
    ancienne = anciennes[index]
    mask = etirer_masque(ancienne.mask, ancienne.bbox, bbox, taille)
    nouvelles = list(anciennes)
    nouvelles[index] = BubbleRegion(bbox=bbox_du_masque(mask), mask=mask,
                                    score=ancienne.score, cls=ancienne.cls,
                                    kind=ancienne.kind, scindee=ancienne.scindee)
    return _reecrire(ckpt_dir, anciennes, nouvelles, {index}, ctx=ctx,
                     retirees=[ancienne], relire=False)


def supprimer_zone(ckpt_dir: Path, index: int, *,
                   ctx: ContextePlanche | None = None) -> dict:
    """Retire une fausse détection. Aucune autre bulle n'est touchée.

    Avec `ctx`, le DESSIN D'ORIGINE est recollé sous la zone retirée : une fausse bulle déjà
    nettoyée a laissé un aplat blanc sur la planche, et la supprimer sans restaurer laisserait
    un trou définitif que rien ne signale."""
    anciennes, _taille = _charger(ckpt_dir)
    _verifier_index(index, anciennes)
    if len(anciennes) == 1:
        raise ErreurEdition("c'est la dernière bulle de la planche : la supprimer laisserait "
                            "une planche sans texte, que le pipeline traiterait comme jamais "
                            "détectée.")
    nouvelles = [r for k, r in enumerate(anciennes) if k != index]
    return _reecrire(ckpt_dir, anciennes, nouvelles, set(), ctx=ctx,
                     retirees=[anciennes[index]])


def scinder_zone(ckpt_dir: Path, index: int, coupe, *,
                 ctx: ContextePlanche | None = None) -> dict:
    """Coupe une région en deux le long du segment `coupe = ((x0, y0), (x1, y1))`.

    Le cas visé est celui que `bubbles_split` traite automatiquement et rate parfois : deux
    ballons qui se touchent, pris pour un seul par le détecteur, dont l'OCR rend les deux
    répliques dans une seule chaîne. Ici c'est l'œil humain qui place le trait — la ligne est
    prolongée à l'infini, seuls comptent les pixels du masque de part et d'autre.

    Les deux lobes sont réduits à leur plus grande composante connexe : un trait qui frôle un
    bord détacherait sinon une écharde de trois pixels, promue au rang de bulle."""
    anciennes, _taille = _charger(ckpt_dir)
    _verifier_index(index, anciennes)
    (ax, ay), (bx, by) = coupe
    if (ax, ay) == (bx, by):
        raise ErreurEdition("le trait de coupe est réduit à un point")

    cible = anciennes[index]
    hauteur, largeur = cible.mask.shape
    ys, xs = np.ogrid[:hauteur, :largeur]
    # Produit vectoriel : signe du côté de la droite (AB) où tombe chaque pixel.
    cote = (bx - ax) * (ys - ay) - (by - ay) * (xs - ax)
    lobes = []
    for garde in (cote > 0, cote <= 0):
        morceau = cible.mask & garde
        parts = geometry.composantes(morceau, min_aire=AIRE_LOBE_MIN)
        if parts:
            lobes.append(parts[0])
    if len(lobes) < 2:
        raise ErreurEdition(
            "le trait ne coupe pas la bulle en deux morceaux exploitables — il passe à côté, "
            f"ou l'un des deux lobes fait moins de {AIRE_LOBE_MIN} pixels.")

    nouvelles = list(anciennes)
    nouvelles[index:index + 1] = [
        BubbleRegion(bbox=bbox_du_masque(m), mask=m, score=cible.score, cls=cible.cls,
                     kind=cible.kind, scindee=True)
        for m in lobes]
    return _reecrire(ckpt_dir, anciennes, nouvelles, {index, index + 1}, ctx=ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Reprise d'UNE bulle — OCR et traduction
# ─────────────────────────────────────────────────────────────────────────────

def relire_zone(ckpt_dir: Path, image_source, index: int, *, cfg_manga: dict | None = None,
                lecteur=None) -> str:
    """Relance l'OCR sur la SEULE bulle `index` et écrit le résultat dans `ocr.json`.

    `lecteur` permet de réutiliser un `ocr.MangaOCR` déjà chargé — le modèle pèse ~424 Mo et
    met plusieurs secondes à monter. Une interface qui relit trois bulles d'affilée doit le
    garder, sinon elle le recharge trois fois.

    Le fond mesuré de la bulle est passé à `read` : sur une bulle INVERSÉE (texte blanc sur
    noir), l'isolement du voisinage doit remplir avec du noir, faute de quoi l'OCR lit une
    page blanche. C'est le même calcul que fait le balayage A, via `clean.analyze_regions`.

    ⚠ N'écrit PAS la traduction : relire ne traduit pas. La réplique reste celle d'avant, et
    c'est à l'appelant de décider s'il retraduit — une correction d'OCR à un caractère près ne
    justifie pas toujours un appel LLM."""
    from PIL import Image as PILImage

    from . import clean

    regions, _taille = _charger(ckpt_dir)
    _verifier_index(index, regions)
    mcfg = cfg_manga or {}
    image = image_source if hasattr(image_source, "crop") else PILImage.open(image_source)
    image = image.convert("RGB")

    styles = clean.analyze_regions(image, regions, mcfg.get("nettoyage"))
    style = styles[index] if index < len(styles) else None
    fond = style.background if (style is not None and getattr(style, "ok", False)) else None

    lecteur = lecteur or ocr_mod.MangaOCR(mcfg.get("ocr"))
    texte = lecteur.read(image, regions[index], background=fond, cfg=mcfg.get("ocr"))

    textes = checkpoints.load_ocr(ckpt_dir) or [""] * len(regions)
    textes = (list(textes) + [""] * len(regions))[:len(regions)]
    textes[index] = texte
    checkpoints.save_ocr(ckpt_dir, textes)
    checkpoints.marquer_origine(ckpt_dir, index, checkpoints.ORIGINE_EDITEUR)
    return texte


def retraduire_zone(ckpt_dir: Path, index: int, agent, *,
                    gloss_text: str = "",
                    langue: str = "jp", pack=None) -> tuple[str, str | None]:
    """Retraduit la SEULE bulle `index` et écrit le résultat dans `traduction.json`.

    Passe par `traduction_unitaire.traduire_bulle`, donc par le MÊME prompt et les mêmes refus
    que le rattrapage automatique. Une réponse refusée n'écrit rien : la réplique précédente
    est conservée, et le motif remonte à l'appelant pour être affiché.

    ⚠ Écrit dans `traduction.json` — la sortie du modèle — et non dans
    `traduction_manuelle.json`, qui est réservé à ce que la MAIN a saisi. La distinction est
    ce qui fait qu'un `--from traduction` ultérieur peut écraser cette réplique-ci (elle vient
    du modèle) sans jamais toucher une correction écrite au clavier."""
    from . import traduction_unitaire

    regions, _taille = _charger(ckpt_dir)
    _verifier_index(index, regions)
    sources = checkpoints.load_ocr(ckpt_dir) or []
    source = sources[index] if index < len(sources) else ""

    texte, motif = traduction_unitaire.traduire_bulle(
        agent, source, gloss_text=gloss_text, bbox=regions[index].bbox, langue=langue,
        pack=pack)
    if motif is not None:
        return "", motif

    textes = checkpoints.load_traduction(ckpt_dir) or [""] * len(regions)
    textes = (list(textes) + [""] * len(regions))[:len(regions)]
    textes[index] = texte
    checkpoints.save_traduction(ckpt_dir, textes)
    # ⚠ Marqué `editeur` : cette réplique n'a PAS vu le contexte de planche (le prompt unitaire
    # ne porte qu'une bulle), et `qa.json` doit pouvoir le dire au relecteur.
    checkpoints.marquer_origine(ckpt_dir, index, checkpoints.ORIGINE_EDITEUR)
    return texte, None


def reprendre_zone(ckpt_dir: Path, index: int, *, ctx: ContextePlanche,
                   lecteur=None, agent=None, gloss_text: str = "",
                   cfg_manga: dict | None = None, langue: str = "jp") -> dict:
    """Le geste complet sur UNE bulle : **vide, lit, traduit**.

    C'est le bouton unique de l'éditeur, et il n'invente rien — il compose trois primitives
    qui existaient déjà, dans le seul ordre qui marche :

    1. `repeindre_clean` — la bulle est vidée dans `pages_clean/`. Sans cette étape d'abord,
       le lettrage réécrirait par-dessus le texte source ;
    2. `relire_zone` — l'OCR de la langue du tome sur cette seule bulle ;
    3. `retraduire_zone` — un appel court, une bulle, une réponse.

    L'ordre compte pour une seconde raison : l'OCR lit l'image **d'origine** (jamais la planche
    nettoyée, cf. le graphe de dépendances de `checkpoints`), donc vider d'abord ne lui retire
    rien. L'inverse — traduire puis nettoyer — laisserait une fenêtre où la planche porte du
    français sur la source.

    Chaque étape est optionnelle par ses dépendances : sans `lecteur` on saute l'OCR, sans
    `agent` on saute la traduction. Ce qui permet d'utiliser la fonction pour « juste vider »
    quand le texte est déjà bon.

    Renvoie un compte rendu par étape ; `refus` porte le motif si le modèle a été rejeté (une
    mauvaise réplique dessinée est pire qu'une bulle vide)."""
    regions, _taille = _charger(ckpt_dir)
    _verifier_index(index, regions)
    mcfg = cfg_manga or {}

    compte = {"nettoyage": repeindre_clean(ctx, [regions[index]], []),
              "ocr": None, "traduction": None, "refus": None}
    if compte["nettoyage"]["abandons"]:
        # `mode: "aucun"` — l'intérieur est trop peu uniforme pour être repeint sans abîmer le
        # dessin. La bulle gardera son texte source visible ; le taire serait pire.
        compte["refus"] = "nettoyage_abandonne"

    if lecteur is not None:
        compte["ocr"] = relire_zone(ckpt_dir, ctx.image_source, index,
                                    cfg_manga=mcfg, lecteur=lecteur)
    if agent is not None:
        texte, motif = retraduire_zone(ckpt_dir, index, agent, gloss_text=gloss_text,
                                       langue=langue)
        compte["traduction"] = texte
        if motif is not None:
            compte["refus"] = motif
    return compte


def _verifier_index(index: int, regions: list[BubbleRegion]) -> None:
    if not (0 <= index < len(regions)):
        raise ErreurEdition(f"bulle {index} inconnue : la planche en compte {len(regions)} "
                            f"(index de 0 à {len(regions) - 1})")
