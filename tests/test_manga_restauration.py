# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Restauration des zones sans texte — le correctif du « visage repeint ».

Mesuré sur *webtoon A* Chap.11 planche 4 : une fausse détection sur le visage d'un
personnage (score 0,569, OCR vide) avait été nettoyée comme une vraie bulle, repeignant 45,6 %
d'une zone de 488×619 px en `[252, 215, 175]` — la couleur de peau, échantillonnée dans ses
propres pixels.

La cause est une logique monotone dans le mauvais sens (`clean.py`) : plus une zone est
UNIFORME, plus le nettoyeur est confiant qu'il peut la repeindre — alors qu'une zone plate est
justement une zone sans texte.

⚠ Aucune statistique de pixels ne distingue une fausse bulle d'une vraie ; c'est **mesuré** sur
ce corpus, pas supposé. Les faux positifs avaient plus d'encre (0,16–0,28) que de vraies bulles
(0,03), et une bulle légitimement rose était plus saturée (0,355) que le visage (0,306). Le seul
séparateur fiable est le TEXTE — d'où une réparation au RENDU, où il est enfin connu.
"""
import numpy as np
from PIL import Image

from manga.detection import BubbleRegion
from manga.rendu import restaurer_sans_texte

TAILLE = (200, 200)


class _Style:
    """Le strict minimum que `restaurer_sans_texte` lit d'un `BubbleStyle`."""

    def __init__(self, ok=True, mode="masque"):
        self.ok, self.mode = ok, mode


def _region(x0, y0, x1, y1):
    masque = np.zeros((TAILLE[1], TAILLE[0]), dtype=bool)
    masque[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=masque, score=0.9, cls=0)


def _images(couleur_origine=(30, 60, 90), couleur_repeinte=(252, 215, 175)):
    """`(origine, nettoyée)` — la seconde a la zone 10..60 repeinte, comme un visage effacé."""
    origine = Image.new("RGB", TAILLE, couleur_origine)
    nettoyee = origine.copy()
    arr = np.asarray(nettoyee).copy()
    arr[10:60, 10:60] = couleur_repeinte
    return origine, Image.fromarray(arr)


def test_une_zone_sans_source_ni_replique_est_restauree():
    origine, nettoyee = _images()
    regions = [_region(10, 10, 60, 60)]
    restaurees = restaurer_sans_texte(nettoyee, origine, regions, [""], [""], [_Style()])
    assert restaurees == [0]
    assert np.array_equal(np.asarray(nettoyee), np.asarray(origine)), \
        "le dessin d'origine est revenu au pixel près"


def test_une_bulle_avec_source_n_est_PAS_restauree():
    """Une vraie bulle a été nettoyée à bon droit : y recoller le texte source serait absurde."""
    origine, nettoyee = _images()
    avant = np.asarray(nettoyee).copy()
    restaurees = restaurer_sans_texte(nettoyee, origine, [_region(10, 10, 60, 60)],
                                      [""], ["HELLO"], [_Style()])
    assert restaurees == []
    assert np.array_equal(np.asarray(nettoyee), avant)


def test_une_bulle_corrigee_A_LA_MAIN_n_est_PAS_restauree():
    """C'est LA raison de la double condition. L'OCR a pu échouer sur une vraie bulle et
    l'utilisateur avoir écrit la réplique lui-même : restaurer dessinerait le texte d'origine
    SOUS la traduction française."""
    origine, nettoyee = _images()
    avant = np.asarray(nettoyee).copy()
    restaurees = restaurer_sans_texte(nettoyee, origine, [_region(10, 10, 60, 60)],
                                      ["Ma traduction"], [""], [_Style()])
    assert restaurees == []
    assert np.array_equal(np.asarray(nettoyee), avant)


def test_une_zone_que_le_nettoyeur_avait_deja_refusee_n_est_pas_touchee():
    """`mode == "aucun"` : rien n'a été repeint, il n'y a rien à défaire."""
    origine, nettoyee = _images()
    avant = np.asarray(nettoyee).copy()
    restaurees = restaurer_sans_texte(nettoyee, origine, [_region(10, 10, 60, 60)],
                                      [""], [""], [_Style(mode="aucun")])
    assert restaurees == []
    assert np.array_equal(np.asarray(nettoyee), avant)


def test_un_style_degenere_est_ignore():
    origine, nettoyee = _images()
    restaurees = restaurer_sans_texte(nettoyee, origine, [_region(10, 10, 60, 60)],
                                      [""], [""], [_Style(ok=False)])
    assert restaurees == []


def test_seule_la_zone_visee_est_restauree():
    """Les masques étant disjoints, une restauration ne déborde jamais sur une voisine."""
    origine, nettoyee = _images()
    arr = np.asarray(nettoyee).copy()
    arr[100:150, 100:150] = (255, 255, 255)     # une VRAIE bulle, nettoyée à bon droit
    nettoyee = Image.fromarray(arr)
    regions = [_region(10, 10, 60, 60), _region(100, 100, 150, 150)]
    restaurees = restaurer_sans_texte(nettoyee, origine, regions,
                                      ["", "Bonjour"], ["", "HELLO"], [_Style(), _Style()])
    assert restaurees == [0]
    final = np.asarray(nettoyee)
    assert tuple(final[30, 30]) == (30, 60, 90), "le visage est revenu"
    assert tuple(final[120, 120]) == (255, 255, 255), "la vraie bulle reste nettoyée"


def test_sans_image_d_origine_on_ne_fait_rien():
    """Chemin de l'éditeur, qui n'a pas toujours le scan sous la main."""
    _origine, nettoyee = _images()
    avant = np.asarray(nettoyee).copy()
    assert restaurer_sans_texte(nettoyee, None, [_region(10, 10, 60, 60)],
                                [""], [""], [_Style()]) == []
    assert np.array_equal(np.asarray(nettoyee), avant)


def test_listes_plus_courtes_que_les_regions():
    """Robustesse : un cache tronqué ne doit pas lever."""
    origine, nettoyee = _images()
    assert restaurer_sans_texte(nettoyee, origine, [_region(10, 10, 60, 60)],
                                [], [], [_Style()]) == [0]
