# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Pose des GLOSES françaises à côté du texte japonais laissé sur le dessin.

## Le compromis, et pourquoi c'est celui-là

Effacer une onomatopée demande de **reconstruire le dessin** qu'elle recouvre : c'est le
métier d'un modèle d'inpainting (LaMa chez *koharu*). La brique s'y refuse — « l'IA ne
dessine jamais » (README §12) — et cette règle n'est pas un scrupule décoratif : c'est elle
qui permet de garantir, test à l'appui, que tout pixel hors des masques de bulles ressort
bit-à-bit identique au scan.

La glose est la réponse honnête à cette contrainte : on **ajoute** une petite traduction
française à côté du japonais, sans jamais y toucher. C'est d'ailleurs ce que fait la
fantrad à la main depuis toujours pour les SFX, précisément parce que redessiner un fond
coûte plus cher que le résultat ne vaut.

## L'invariant

Une glose ne recouvre JAMAIS :

  · les pixels d'encre d'une onomatopée (celle qu'elle traduit comme les autres) ;
  · le masque d'une bulle — le lettrage français y est déjà, et l'écraser serait pire que
    de ne rien poser ;
  · une glose déjà posée.

Faute d'emplacement satisfaisant, **on ne pose rien** et on le dit au rapport. C'est la même
règle que partout ailleurs dans la brique : une bulle vide signalée vaut mieux qu'une
mauvaise réplique dessinée (cf. `orchestrator_manga._rattraper_bulles`).

## Le choix de l'emplacement

Huit positions sont essayées autour de la boîte du texte source — les quatre côtés puis les
quatre coins — et celle qui tombe sur la zone la plus **calme** l'emporte, mesurée par
l'écart-type des luminances sous le rectangle. Poser une glose sur un aplat de ciel plutôt
que sur un enchevêtrement de traits de vitesse ne change rien à la légitimité du résultat,
mais beaucoup à sa lisibilité. À défaut, le corps est réduit d'un cran et on recommence.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from ._config import fusion
from .detection import BubbleRegion
from .geometry import dilate
from .typeset import load_font, resolve_font, texte_dessinable

_DEFAUTS = {
    "glose_taille_max": 22,
    "glose_taille_min": 10,
    # Air laissé autour du texte de la glose, en fraction de son corps. Sans elle, le
    # contour du texte touche l'encre voisine et les deux se confondent.
    "glose_marge": 0.45,
    # Écart minimal, en pixels, entre la glose et tout ce qu'elle n'a pas le droit de
    # toucher. Dilate les masques interdits avant le test de collision.
    "glose_ecart": 3,
    "glose_contour": True,
    # --- Contour MESURÉ (lot 21, L21.5) ------------------------------------------------
    #
    # ⚠ Le plan de lot posait ici une prémisse FAUSSE, et elle est corrigée plutôt que
    # recopiée : il attribuait le contour blanc des gloses à `typeset.calque_fit`, qui prend
    # `stroke_fill = (*style.background, 255)` alors que `clean.analyze_regions` force
    # `background = (255, 255, 255)` pour toute zone non-bulle. C'est exact pour le lettrage
    # DES BULLES — mais les gloses ne passent pas par `calque_fit` : `dessiner` ci-dessous a
    # toujours choisi sa polarité localement, par `_claire`, et son contour est donc déjà
    # noir ou blanc selon le fond. Le défaut réel n'est pas « blanc par construction ».
    #
    # Le défaut réel est que ces deux poles sont **purs** : sur un aplat gris de trame, un
    # contour blanc franc découpe un halo qui se voit plus que la glose. Armé, ce réglage
    # prend la couleur dominante réellement mesurée sous le rectangle (mode de luminance à
    # 32 classes, affinage ±16, médiane RGB — la méthode calibrée de `clean`) et lui oppose
    # le pôle contrasté pour le texte.
    #
    # `false` = comportement d'avant le lot, au bit près.
    "glose_contour_mesure": False,
}

# Les huit ancrages essayés, dans l'ordre de préférence à calme égal : d'abord les côtés
# (une glose alignée sur le texte se rattache visuellement à lui sans ambiguïté), puis les
# coins. (dx, dy) est exprimé en parts de la taille de la glose et de la boîte source.
_ANCRAGES = (
    ("droite", 1.0, 0.5), ("gauche", -1.0, 0.5),
    ("bas", 0.5, 1.0), ("haut", 0.5, -1.0),
    ("bas_droite", 1.0, 1.0), ("bas_gauche", -1.0, 1.0),
    ("haut_droite", 1.0, -1.0), ("haut_gauche", -1.0, -1.0),
)

#: Marge de comparaison des coordonnées d'ancrage. Écrasante par rapport à tout écart de
#: représentation, et sans effet sur les seules valeurs qui existent ici (±1 et 0,5).
_EPS_ANCRAGE = 1e-9


def _colle_au_bord(v: float) -> bool:
    """`±1` = ancrage COLLÉ au bord de la boîte source ; toute autre valeur = position
    relative dans la boîte.

    ⚠ Le test s'écrivait `abs(v) == 1.0`. Il était juste — les valeurs viennent d'un littéral
    de ce module, pas d'un calcul — mais une égalité flottante nue est une invitation : la
    première coordonnée d'ancrage qui naîtrait d'une division ferait basculer un ancrage de
    bord en ancrage relatif, en silence et sans rien casser de visible."""
    return abs(abs(v) - 1.0) < _EPS_ANCRAGE


@dataclass
class Glose:
    """Une glose effectivement plaçable. `None` à sa place = non posée."""
    rect: tuple[int, int, int, int]
    texte: str
    taille: int
    ancrage: str
    claire: bool          # texte clair sur fond sombre
    calme: float          # écart-type des luminances sous le rectangle
    #: Couleur DOMINANTE mesurée sous le rectangle (`clean._couleur_de_fond`), lot 21 L21.5.
    #: `None` quand la mesure n'a pas été demandée — le rendu retombe alors sur le noir et le
    #: blanc purs, au bit près.
    fond: tuple[int, int, int] | None = None


def _cfg(cfg: dict | None) -> dict:
    """⚠ HUITIÈME site du même défaut, et le seul que le relevé du lot 11 n'avait pas vu :
    `{**_DEFAUTS, **(cfg or {})}` laissait `glose_taille_max: null` remplacer le défaut par
    `None`, que `load_font` reçoit ensuite en taille de police."""
    return fusion(_DEFAUTS, cfg)


def _zone_interdite(forme: tuple[int, int], sfx: list[BubbleRegion],
                    bulles: list[BubbleRegion], ecart: int) -> np.ndarray:
    """Tout ce qu'une glose n'a pas le droit de recouvrir, dilaté de `ecart`.

    Les onomatopées y sont TOUTES, pas seulement celle qu'on gloses : deux SFX voisines sur
    une page d'action se disputeraient sinon le même blanc."""
    interdit = np.zeros(forme, dtype=bool)
    for r in list(sfx) + list(bulles):
        m = getattr(r, "mask", None)
        if m is not None and m.shape == forme:
            interdit |= m
    return dilate(interdit, ecart) if ecart > 0 else interdit


def _calme(gris: np.ndarray, rect: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = rect
    fenetre = gris[y0:y1, x0:x1]
    return float(fenetre.std()) if fenetre.size else 1e9


def _claire(gris: np.ndarray, rect: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = rect
    fenetre = gris[y0:y1, x0:x1]
    return bool(fenetre.mean() < 110) if fenetre.size else False


def _fond_mesure(arr: np.ndarray, rect: tuple[int, int, int, int]) -> tuple[int, int, int]:
    """Couleur dominante sous le rectangle d'une glose (lot 21, L21.5).

    ⚠ Délègue à `clean._couleur_de_fond` plutôt que de prendre une moyenne : le choix du
    MODE y est documenté par une mesure — sur une bulle inversée, un p90 rend « la couleur du
    TEXTE ». Le même piège existe ici : une glose posée à côté d'une onomatopée noire aurait
    un fond mesuré à mi-chemin entre le papier et l'encre, et son contour disparaîtrait dans
    les deux."""
    from .clean import _couleur_de_fond
    x0, y0, x1, y1 = rect
    fenetre = arr[y0:y1, x0:x1]
    if fenetre.size == 0:
        return (255, 255, 255)
    fond, _luma = _couleur_de_fond(fenetre.reshape(-1, 3))
    return fond


def placer(image: Image.Image, sfx: list[BubbleRegion], textes: list[str], *,
           bulles: list[BubbleRegion] | None = None, cfg: dict | None = None,
           font_path: str | None = None) -> tuple[list[Glose | None], list[str]]:
    """Décide où poser chaque glose. Ne dessine rien.

    Renvoie `(gloses, refus)` — `gloses` aligné par position sur `sfx` (`None` = non posée),
    `refus` une liste de motifs lisibles pour le rapport."""
    c = _cfg(cfg)
    police = resolve_font(font_path)
    bulles = list(bulles or [])
    arr_u8 = np.asarray(image.convert("RGB"))
    arr = arr_u8.astype(np.float32)
    gris = arr.mean(axis=2)
    # La mesure de couleur n'est faite que si elle sert : elle coûte un histogramme par
    # candidat d'ancrage, et il y en a huit par corps essayé.
    mesurer_fond = bool(c["glose_contour_mesure"])
    h, w = gris.shape
    interdit = _zone_interdite((h, w), sfx, bulles, int(c["glose_ecart"]))
    occupe = np.zeros((h, w), dtype=bool)

    gloses: list[Glose | None] = []
    refus: list[str] = []
    t_max, t_min = int(c["glose_taille_max"]), int(c["glose_taille_min"])

    for idx, region in enumerate(sfx):
        brut = (textes[idx] if idx < len(textes) else "") or ""
        contenu, police_reelle, _subs, _supp = texte_dessinable(brut.strip(), police)
        contenu = contenu.strip()
        if not contenu:
            # Rien à poser : ni traduction, ni glyphe dessinable. Ce n'est pas un refus de
            # placement — le modèle a pu juger, à raison, qu'un filigrane ne se glose pas.
            gloses.append(None)
            continue

        bx0, by0, bx1, by1 = region.bbox
        pose: Glose | None = None
        # Le corps part d'une fraction du texte source — une onomatopée pleine page mérite
        # une glose plus grande qu'un petit bruitage — puis décroît jusqu'au plancher.
        depart = max(t_min, min(t_max, int(round(min(bx1 - bx0, by1 - by0) * 0.45))))
        for taille in range(depart, t_min - 1, -1):
            font = load_font(police_reelle, taille)
            tw = int(round(font.getlength(contenu)))
            th = taille
            marge = max(1, int(round(taille * float(c["glose_marge"]))))
            gw, gh = tw + 2 * marge, th + 2 * marge
            if gw >= w or gh >= h:
                continue
            candidats: list[tuple[float, Glose]] = []
            # L'ancrage est décalé de `ecart` : les masques interdits sont dilatés d'autant,
            # donc une glose posée EXACTEMENT au bord de la boîte source tombe toujours dans
            # la zone interdite et aucun candidat ne survit. Invisible sur une planche réelle
            # — l'encre d'une onomatopée ne remplit pas sa boîte — mais systématique dès que
            # le masque est plein.
            ecart = int(c["glose_ecart"])
            for nom, dx, dy in _ANCRAGES:
                if _colle_au_bord(dx):
                    x = bx1 + ecart if dx > 0 else bx0 - gw - ecart
                else:
                    x = int(bx0 + (bx1 - bx0 - gw) * dx)
                if _colle_au_bord(dy):
                    y = by1 + ecart if dy > 0 else by0 - gh - ecart
                else:
                    y = int(by0 + (by1 - by0 - gh) * dy)
                x, y = int(x), int(y)
                if x < 0 or y < 0 or x + gw > w or y + gh > h:
                    continue
                rect = (x, y, x + gw, y + gh)
                if interdit[y:y + gh, x:x + gw].any() or occupe[y:y + gh, x:x + gw].any():
                    continue
                calme = _calme(gris, rect)
                candidats.append((calme, Glose(rect=rect, texte=contenu, taille=taille,
                                               ancrage=nom, claire=_claire(gris, rect),
                                               calme=calme,
                                               fond=(_fond_mesure(arr_u8, rect)
                                                     if mesurer_fond else None))))
            if candidats:
                candidats.sort(key=lambda t: t[0])
                pose = candidats[0][1]
                break

        if pose is None:
            gloses.append(None)
            refus.append(f"bulle {idx + 1} — « {contenu[:24]} » : aucune zone libre "
                         f"autour de ({bx0}, {by0})")
            continue
        x0, y0, x1, y1 = pose.rect
        occupe[y0:y1, x0:x1] = True
        gloses.append(pose)
    return gloses, refus


def dessiner(image: Image.Image, gloses: list[Glose | None], *,
             cfg: dict | None = None, font_path: str | None = None) -> Image.Image:
    """Dessine les gloses décidées par `placer`. Renvoie une NOUVELLE image.

    Le texte prend la polarité de son fond — clair sur sombre, sombre sur clair — avec un
    contour de la couleur opposée. Sur du dessin, c'est le contour qui fait la lisibilité :
    sans lui, un texte noir sur des hachures noires disparaît."""
    c = _cfg(cfg)
    police = resolve_font(font_path)
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    for g in gloses:
        if g is None:
            continue
        _cont, police_reelle, _s, _p = texte_dessinable(g.texte, police)
        font = load_font(police_reelle, g.taille)
        marge = (g.rect[2] - g.rect[0] - int(round(font.getlength(g.texte)))) // 2
        x, y = g.rect[0] + marge, g.rect[1] + marge
        # ⚠ Le contour prend la couleur MESURÉE quand elle existe, et le blanc pur sinon
        # (lot 21, L21.5). Le texte prend le pôle opposé : sur un fond mesuré à luma 60, un
        # contour à 60 et un texte blanc restent lisibles là où un contour blanc franc
        # découpait un halo dans le dessin.
        if g.fond is not None:
            from .clean import _luma
            fonce = float(_luma(np.array(g.fond, dtype=float))) < 128.0
            arriere = tuple(int(v) for v in g.fond)
            avant = (255, 255, 255) if fonce else (0, 0, 0)
        else:
            avant = (255, 255, 255) if g.claire else (0, 0, 0)
            arriere = (0, 0, 0) if g.claire else (255, 255, 255)
        epaisseur = max(1, g.taille // 8) if c["glose_contour"] else 0
        draw.text((x, y), g.texte, font=font, fill=avant,
                  stroke_width=epaisseur, stroke_fill=arriere)
    return out
