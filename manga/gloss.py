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


@dataclass
class Glose:
    """Une glose effectivement plaçable. `None` à sa place = non posée."""
    rect: tuple[int, int, int, int]
    texte: str
    taille: int
    ancrage: str
    claire: bool          # texte clair sur fond sombre
    calme: float          # écart-type des luminances sous le rectangle


def _cfg(cfg: dict | None) -> dict:
    return {**_DEFAUTS, **(cfg or {})}


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


def placer(image: Image.Image, sfx: list[BubbleRegion], textes: list[str], *,
           bulles: list[BubbleRegion] | None = None, cfg: dict | None = None,
           font_path: str | None = None) -> tuple[list[Glose | None], list[str]]:
    """Décide où poser chaque glose. Ne dessine rien.

    Renvoie `(gloses, refus)` — `gloses` aligné par position sur `sfx` (`None` = non posée),
    `refus` une liste de motifs lisibles pour le rapport."""
    c = _cfg(cfg)
    police = resolve_font(font_path)
    bulles = list(bulles or [])
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    gris = arr.mean(axis=2)
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
                if abs(dx) == 1.0:
                    x = bx1 + ecart if dx > 0 else bx0 - gw - ecart
                else:
                    x = int(bx0 + (bx1 - bx0 - gw) * dx)
                if abs(dy) == 1.0:
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
                                               calme=calme)))
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
        avant = (255, 255, 255) if g.claire else (0, 0, 0)
        arriere = (0, 0, 0) if g.claire else (255, 255, 255)
        epaisseur = max(1, g.taille // 8) if c["glose_contour"] else 0
        draw.text((x, y), g.texte, font=font, fill=avant,
                  stroke_width=epaisseur, stroke_fill=arriere)
    return out
