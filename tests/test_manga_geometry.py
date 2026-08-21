# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Morphologie numpy de la brique manga (`manga/geometry.py`).

Deux propriétés sont load-bearing pour tout le lot 1 et vérifiées ici explicitement :
  · `erode` est **équivalent à `PIL.ImageFilter.MinFilter`** — c'est ce qui justifie de ne
    PAS ajouter opencv (~60 Mo, conflits de DLL avec onnxruntime-directml) ;
  · `erode` et `dilate` sont **duaux**, sinon le mode « texte » de `clean.py` (qui dilate
    un masque de texte) mordrait sur le contour de la bulle.
"""
import numpy as np
import pytest
from PIL import Image, ImageFilter

from manga import geometry
from manga.geometry import (adaptive_radius, dilate, erode, safe_erode,
                            vertical_extent, width_profile)


def _disque(h: int, w: int, cy: float, cx: float, r: float) -> np.ndarray:
    y, x = np.ogrid[:h, :w]
    return ((y - cy) ** 2 + (x - cx) ** 2) <= r ** 2


# --------------------------------------------------------------------------- #
# erode / dilate
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("k", [1, 2, 3, 5, 8])
def test_erode_est_equivalent_a_pil_minfilter(k):
    """LA justification du choix numpy. MinFilter n'accepte que des tailles impaires,
    et sa taille vaut 2k+1 pour un rayon k."""
    rng = np.random.default_rng(7)
    mask = rng.random((60, 80)) < 0.65
    # quelques formes franches en plus du bruit, pour couvrir bords et coins
    mask[:6, :6] = True
    mask[-6:, -6:] = False
    mask |= _disque(60, 80, 30, 40, 15)

    attendu = np.asarray(Image.fromarray((mask * 255).astype(np.uint8), mode="L")
                         .filter(ImageFilter.MinFilter(2 * k + 1))) > 127
    assert np.array_equal(erode(mask, k), attendu)


@pytest.mark.parametrize("k", [1, 2, 4, 7])
def test_dilate_est_le_dual_de_erode(k):
    rng = np.random.default_rng(11)
    mask = rng.random((40, 50)) < 0.4
    assert np.array_equal(dilate(mask, k), ~erode(~mask, k))


def test_erode_retrecit_et_dilate_agrandit():
    mask = _disque(60, 60, 30, 30, 20)
    assert erode(mask, 3).sum() < mask.sum()
    assert dilate(mask, 3).sum() > mask.sum()
    # monotonie : l'érodé est inclus dans le masque, qui est inclus dans le dilaté
    assert (mask | erode(mask, 3)).sum() == mask.sum()
    assert (mask & dilate(mask, 3)).sum() == mask.sum()


def test_erode_est_monotone_en_k():
    mask = _disque(80, 80, 40, 40, 30)
    aires = [erode(mask, k).sum() for k in (0, 1, 2, 4, 8)]
    assert aires == sorted(aires, reverse=True)


def test_erode_k_nul_ou_negatif_renvoie_une_copie():
    mask = _disque(20, 20, 10, 10, 6)
    for k in (0, -1):
        out = erode(mask, k)
        assert np.array_equal(out, mask)
        out[0, 0] = True                     # ne doit pas toucher l'original
        assert not mask[0, 0]


def test_erode_carre_retire_bien_k_de_chaque_cote():
    """Élément structurant carré : un rectangle plein perd exactement k pixels sur
    chaque bord (les fenêtres de bord sont rognées, cf. convention du module)."""
    mask = np.zeros((30, 30), dtype=bool)
    mask[10:20, 8:24] = True                 # 10 de haut, 16 de large
    out = erode(mask, 2)
    ys, xs = np.nonzero(out)
    assert (ys.min(), ys.max()) == (12, 17)
    assert (xs.min(), xs.max()) == (10, 21)


def test_erode_masque_vide_et_masque_plein():
    vide = np.zeros((10, 10), dtype=bool)
    plein = np.ones((10, 10), dtype=bool)
    assert not erode(vide, 3).any()
    # convention de bord : les fenêtres sont rognées, un masque plein reste plein
    assert erode(plein, 3).all()


def test_erode_efface_une_forme_plus_fine_que_le_noyau():
    mask = np.zeros((20, 20), dtype=bool)
    mask[10, 2:18] = True                    # ligne de 1 px d'épaisseur
    assert not erode(mask, 1).any()


def test_erode_ne_mute_pas_l_entree():
    mask = _disque(30, 30, 15, 15, 10)
    avant = mask.copy()
    erode(mask, 3)
    dilate(mask, 3)
    assert np.array_equal(mask, avant)


def test_erode_accepte_un_masque_non_booleen():
    mask = (_disque(20, 20, 10, 10, 6)).astype(np.uint8)
    assert erode(mask, 2).dtype == bool


# --------------------------------------------------------------------------- #
# adaptive_radius
# --------------------------------------------------------------------------- #

def test_adaptive_radius_suit_le_petit_cote():
    # 3 % de 300 = 9 px, dans les bornes
    assert adaptive_radius(1000, 300) == 9
    assert adaptive_radius(300, 1000) == 9   # symétrique : c'est le PETIT côté


def test_adaptive_radius_borne_en_bas_et_en_haut():
    assert adaptive_radius(40, 40) == 2      # 3 % = 1,2 px → plancher : le contour survivrait
    assert adaptive_radius(5000, 5000) == 12  # 3 % = 150 px → plafond : plus de place utile


def test_adaptive_radius_degenere_sans_planter():
    assert adaptive_radius(0, 0) >= 2
    assert adaptive_radius(1, 1) == 2


# --------------------------------------------------------------------------- #
# safe_erode
# --------------------------------------------------------------------------- #

def test_safe_erode_nominal_utilise_le_k_demande():
    mask = _disque(120, 120, 60, 60, 50)
    out, k_eff = safe_erode(mask, 8)
    assert k_eff == 8
    assert np.array_equal(out, erode(mask, 8))


def test_safe_erode_replie_sur_lo_quand_le_k_demande_vide_trop():
    """Bulle fine : k=8 la ferait disparaître, on retombe sur lo=2."""
    mask = np.zeros((60, 200), dtype=bool)
    mask[28:33, 20:180] = True               # 5 px de haut seulement
    out, k_eff = safe_erode(mask, 8)
    assert k_eff == 2
    assert out.any()


def test_safe_erode_replie_sur_le_masque_brut_en_dernier_recours():
    """Sliver de 2 px : même lo=2 l'efface. On préfère repeindre le contour de CETTE
    bulle plutôt que de ne rien pouvoir mesurer (cas tracé dans RAPPORT.md)."""
    mask = np.zeros((40, 100), dtype=bool)
    mask[20:22, 10:90] = True
    out, k_eff = safe_erode(mask, 6)
    assert k_eff == 0
    assert np.array_equal(out, mask)


def test_safe_erode_masque_vide():
    out, k_eff = safe_erode(np.zeros((10, 10), dtype=bool), 4)
    assert k_eff == 0 and not out.any()


def test_safe_erode_respecte_min_keep():
    mask = _disque(100, 100, 50, 50, 40)
    # min_keep très exigeant : même une érosion modérée « perd trop »
    _out, k_eff = safe_erode(mask, 10, min_keep=0.99)
    assert k_eff in (2, 0)


def test_safe_erode_ne_mute_pas_l_entree():
    mask = _disque(50, 50, 25, 25, 20)
    avant = mask.copy()
    safe_erode(mask, 5)
    assert np.array_equal(mask, avant)


# --------------------------------------------------------------------------- #
# width_profile — le cœur de la composition « dans la bulle »
# --------------------------------------------------------------------------- #

def test_width_profile_sur_un_disque_est_maximal_au_centre():
    h = w = 101
    mask = _disque(h, w, 50, 50, 40)
    largeur, x0, x1 = width_profile(mask, 50)
    assert largeur.shape == (h,)
    assert largeur[50] == largeur.max() == 81
    assert largeur[0] == 0                   # au-dessus du disque
    assert (x1 - x0 == largeur)[largeur > 0].all()


def test_width_profile_exclut_la_queue_de_la_bulle():
    """LE cas qui motive la plage contiguë. Une bbox (ou un premier..dernier) inclurait
    la queue et annoncerait une largeur bien trop grande à ces hauteurs."""
    mask = np.zeros((100, 200), dtype=bool)
    mask[20:60, 40:160] = True               # corps de la bulle
    mask[50:56, 170:195] = True              # queue, DÉTACHÉE horizontalement
    largeur, x0, x1 = width_profile(mask, 100)
    assert largeur[52] == 120                # la queue n'est pas comptée
    assert x0[52] == 40 and x1[52] == 160
    # contrôle : un premier..dernier naïf aurait donné 155
    ligne = np.nonzero(mask[52])[0]
    assert ligne.max() - ligne.min() + 1 == 155


def test_width_profile_gere_un_masque_bi_lobe():
    """Deux bulles fusionnées par le détecteur : on ne garde que le lobe qui contient cx,
    au lieu de croire à une seule zone large englobant le vide entre les deux."""
    mask = np.zeros((50, 200), dtype=bool)
    mask[10:40, 10:70] = True                # lobe gauche
    mask[10:40, 130:190] = True              # lobe droit
    largeur, x0, x1 = width_profile(mask, 40)      # cx dans le lobe GAUCHE
    assert largeur[25] == 60 and (x0[25], x1[25]) == (10, 70)
    largeur_d, x0_d, _ = width_profile(mask, 160)  # cx dans le lobe DROIT
    assert largeur_d[25] == 60 and x0_d[25] == 130


def test_width_profile_ligne_sans_le_centre_est_de_largeur_nulle():
    mask = np.zeros((10, 20), dtype=bool)
    mask[5, 0:4] = True                      # ne couvre pas cx=10
    largeur, x0, x1 = width_profile(mask, 10)
    assert largeur[5] == 0 and x0[5] == 0 and x1[5] == 0


def test_width_profile_ligne_pleine():
    mask = np.ones((5, 30), dtype=bool)
    largeur, x0, x1 = width_profile(mask, 15)
    assert (largeur == 30).all()
    assert (x0 == 0).all() and (x1 == 30).all()


def test_width_profile_cx_hors_bornes_est_ramene_dans_l_image():
    mask = np.ones((4, 10), dtype=bool)
    for cx in (-5, 999):
        largeur, _, _ = width_profile(mask, cx)
        assert (largeur == 10).all()


def test_width_profile_x1_est_exclusif():
    mask = np.zeros((3, 10), dtype=bool)
    mask[1, 3:7] = True                      # colonnes 3,4,5,6
    largeur, x0, x1 = width_profile(mask, 5)
    assert (largeur[1], x0[1], x1[1]) == (4, 3, 7)


# --------------------------------------------------------------------------- #
# vertical_extent
# --------------------------------------------------------------------------- #

def test_vertical_extent_encadre_les_lignes_utiles():
    largeur = np.array([0, 0, 5, 9, 7, 0, 0])
    assert vertical_extent(largeur) == (2, 5)        # y1 exclusif


def test_vertical_extent_profil_vide():
    assert vertical_extent(np.zeros(10, dtype=int)) == (0, 0)


def test_vertical_extent_profil_entierement_plein():
    assert vertical_extent(np.ones(6, dtype=int)) == (0, 6)


def test_vertical_extent_est_coherent_avec_width_profile():
    mask = _disque(101, 101, 50, 50, 30)
    largeur, _, _ = width_profile(mask, 50)
    y0, y1 = vertical_extent(largeur)
    assert (y0, y1) == (20, 81)
    assert largeur[y0] > 0 and largeur[y1 - 1] > 0
    assert not largeur[:y0].any() and not largeur[y1:].any()


# --------------------------------------------------------------------------- #
# IoU de boîtes
# --------------------------------------------------------------------------- #
#
# Le pendant bon marché de `detection_retry.iou_masques`. L'éditeur s'en sert pour retrouver
# LA MÊME bulle après une retaille, dans un jeu de régions que `reading_order` vient de
# réordonner : l'index n'est pas une identité stable, la géométrie l'est.

def test_iou_bbox_identique_vaut_un():
    assert geometry.iou_bbox((10, 20, 110, 120), (10, 20, 110, 120)) == pytest.approx(1.0)


def test_iou_bbox_disjointes_vaut_zero():
    assert geometry.iou_bbox((0, 0, 10, 10), (50, 50, 60, 60)) == 0.0


def test_iou_bbox_qui_se_touchent_sans_se_recouvrir_vaut_zero():
    """Bords droit et bas EXCLUS, la convention de `BubbleRegion.bbox`. Deux boîtes bord à
    bord ne partagent aucun pixel."""
    assert geometry.iou_bbox((0, 0, 10, 10), (10, 0, 20, 10)) == 0.0


def test_iou_bbox_est_symetrique():
    a, b = (0, 0, 100, 100), (50, 50, 150, 150)
    assert geometry.iou_bbox(a, b) == pytest.approx(geometry.iou_bbox(b, a))


def test_iou_bbox_d_une_boite_incluse():
    """Un carré de 50 dans un carré de 100 : l'intersection est le petit, l'union le grand."""
    assert geometry.iou_bbox((0, 0, 100, 100), (0, 0, 50, 50)) == pytest.approx(0.25)


def test_iou_bbox_d_un_ajustement_reste_franchement_au_dessus_du_seuil():
    """Le cas d'usage : une bulle élargie de 8 px de chaque côté doit rester « la même bulle »
    pour le seuil de report (0,30), sinon un simple ajustement perdrait sa traduction."""
    boite = (60, 40, 340, 220)
    ajustee = (boite[0] - 8, boite[1] - 8, boite[2] + 8, boite[3] + 8)
    assert geometry.iou_bbox(boite, ajustee) > 0.30
