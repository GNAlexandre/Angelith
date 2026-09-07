# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Découpage des bandes très allongées en fenêtres de détection.

Le défaut corrigé : `_letterbox` met toute l'image dans un carré 640×640 en conservant le
ratio. Sur une bande de 1080×10000 la planche devient 69×640 — 10,8 % de la largeur du canevas
— et une bulle de 400×500 px arrive au réseau en 26×32 px. Mesuré sur *webtoon A*
Chap.11 : descendre `conf_threshold` jusqu'à 0,10 ne récupère **aucune** bulle, parce que le
réseau ne les émet pas du tout.

Ces tests ne chargent **pas** le modèle ONNX : tout ce qui est vérifié ici est de la géométrie
pure. `manga.detection` n'importe `onnxruntime` que dans `BubbleDetector.__init__`.
"""
import numpy as np

from manga.detection import (DEFAUTS_FENETRE, BubbleRegion, _remonter, _touche_couture,
                             fenetres, fusionner_fenetres)

LARGEUR, HAUTEUR = 1080, 10000


def _region(x0, y0, x1, y1, score=0.9, hauteur=HAUTEUR):
    masque = np.zeros((hauteur, LARGEUR), dtype=bool)
    masque[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=masque, score=score, cls=0)


# --------------------------------------------------------------------------- #
# Découpage
# --------------------------------------------------------------------------- #

def test_une_bande_de_webtoon_est_decoupee():
    bandes = fenetres(LARGEUR, HAUTEUR)
    assert len(bandes) == 8
    assert bandes[0][0] == 0, "la première fenêtre part du haut"
    assert bandes[-1][1] == HAUTEUR, "la dernière atteint le bas"
    assert all(y1 - y0 == DEFAUTS_FENETRE["fenetre_hauteur"] for y0, y1 in bandes), \
        "toutes les fenêtres ont la MÊME hauteur, donc le même facteur de letterbox"


def test_la_couverture_est_continue():
    """Aucun trou : une bulle ne doit pas pouvoir tomber entre deux fenêtres."""
    bandes = fenetres(LARGEUR, HAUTEUR)
    for (_, fin), (debut_suivant, _) in zip(bandes, bandes[1:]):
        assert debut_suivant <= fin


def test_le_recouvrement_depasse_la_plus_haute_bulle():
    """C'est l'invariant qui rend sûr d'écarter les détections coupées par une couture."""
    bandes = fenetres(LARGEUR, HAUTEUR)
    recouvrements = [fin - debut_suivant
                     for (_, fin), (debut_suivant, _) in zip(bandes, bandes[1:])]
    assert min(recouvrements) >= DEFAUTS_FENETRE["fenetre_recouvrement"]


def test_une_planche_manga_paginee_n_est_PAS_decoupee():
    """Non-régression : ratio 1,4, elle occupe déjà 70 % du canevas et n'a rien à y gagner."""
    assert fenetres(1440, 2048) == []


def test_les_formats_courants_ne_sont_pas_touches():
    for largeur, hauteur in ((1000, 1000), (1125, 1600), (2048, 1440), (800, 2000)):
        assert fenetres(largeur, hauteur) == [], f"{largeur}x{hauteur}"


def test_une_image_degeneree_ne_leve_pas():
    assert fenetres(0, 0) == []
    assert fenetres(100, 0) == []


def test_le_decoupage_est_reglable():
    bandes = fenetres(1000, 8000, {"fenetre_hauteur": 4000, "fenetre_recouvrement": 0})
    assert bandes == [(0, 4000), (4000, 8000)]


def test_un_ratio_min_eleve_desactive_le_decoupage():
    assert fenetres(LARGEUR, HAUTEUR, {"fenetre_ratio_min": 99}) == []


# --------------------------------------------------------------------------- #
# Remontée en coordonnées pleine page
# --------------------------------------------------------------------------- #

def test_une_detection_de_fenetre_revient_a_sa_place():
    dans_fenetre = _region(100, 50, 400, 300, hauteur=2160)
    entiere = _remonter(dans_fenetre, 1260, HAUTEUR)
    assert entiere.bbox == (100, 1310, 400, 1560)
    assert entiere.mask.shape == (HAUTEUR, LARGEUR)
    ys, xs = np.nonzero(entiere.mask)
    assert (ys.min(), ys.max() + 1) == (1310, 1560)
    assert (xs.min(), xs.max() + 1) == (100, 400)


def test_la_remontee_preserve_le_score():
    entiere = _remonter(_region(0, 0, 10, 10, score=0.42, hauteur=2160), 500, HAUTEUR)
    assert entiere.score == 0.42


# --------------------------------------------------------------------------- #
# Coutures
# --------------------------------------------------------------------------- #

def test_une_detection_collee_a_une_couture_interieure_est_reperee():
    fenetre = (1260, 3420)
    assert _touche_couture(_region(0, 1260, 100, 1800), *fenetre, HAUTEUR) is True
    assert _touche_couture(_region(0, 3000, 100, 3420), *fenetre, HAUTEUR) is True


def test_le_bord_REEL_de_la_planche_n_est_pas_une_couture():
    """Une bulle collée au haut de la page l'est légitimement — rien ne la complètera."""
    assert _touche_couture(_region(0, 0, 100, 500), 0, 2160, HAUTEUR) is False
    assert _touche_couture(_region(0, 9500, 100, HAUTEUR), 7840, HAUTEUR, HAUTEUR) is False


def test_une_detection_au_milieu_de_sa_fenetre_est_intacte():
    assert _touche_couture(_region(0, 2000, 100, 2500), 1260, 3420, HAUTEUR) is False


# --------------------------------------------------------------------------- #
# Fusion
# --------------------------------------------------------------------------- #

def test_la_meme_bulle_vue_deux_fois_n_est_gardee_qu_une():
    a = _region(100, 1000, 500, 1500, score=0.90)
    b = _region(102, 1002, 498, 1498, score=0.85)
    gardees = fusionner_fenetres([(a, False), (b, False)], 0.45)
    assert len(gardees) == 1
    assert gardees[0].score == 0.90, "le meilleur score gagne"


def test_la_version_ENTIERE_prime_sur_la_version_tronquee_MIEUX_notee():
    """Sans ce critère, une bulle coupée par une couture pourrait évincer la bulle entière."""
    tronquee = _region(100, 1260, 500, 1500, score=0.95)
    entiere = _region(100, 1100, 500, 1500, score=0.70)
    gardees = fusionner_fenetres([(tronquee, True), (entiere, False)], 0.45)
    assert len(gardees) == 1
    assert gardees[0].bbox == (100, 1100, 500, 1500)


def test_une_bulle_tronquee_partout_survit_quand_meme():
    """Plus haute que le recouvrement : elle est coupée dans toutes les fenêtres. Mieux vaut la
    garder tronquée — l'éditeur sait la retailler — que la faire disparaître en silence."""
    gardees = fusionner_fenetres([(_region(0, 1260, 400, 3420, score=0.8), True)], 0.45)
    assert len(gardees) == 1


def test_deux_bulles_DISTINCTES_sont_toutes_deux_gardees():
    a = _region(100, 1000, 500, 1400)
    b = _region(100, 5000, 500, 5400)
    assert len(fusionner_fenetres([(a, False), (b, False)], 0.45)) == 2


def test_aucune_candidate():
    assert fusionner_fenetres([], 0.45) == []
