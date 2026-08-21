# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Arbitre d'une relance de détection : « mieux » n'est jamais « plus de bulles ».

Baisser `conf_threshold` fait TOUJOURS apparaître des régions. La question n'est pas combien,
mais lesquelles : sur le tome de référence, deux détections basses étaient du dessin (un
gratte-ciel page 44, une trame). Chaque faux positif installé coûte un nettoyage qui abîme la
planche, un OCR de bruit et une réplique inventée.

Aucun modèle, aucune image, aucune E/S : l'arbitre est du numpy pur, exactement pour être
testable ainsi.
"""
import numpy as np
import pytest

from manga import detection_retry as dr
from manga.detection import BubbleRegion

TAILLE = (200, 200)


def _region(x0, y0, x1, y1, score=0.9, trous=0):
    """Une bulle rectangulaire. `trous` perce des lignes vides pour baisser le remplissage."""
    m = np.zeros(TAILLE, dtype=bool)
    m[y0:y1, x0:x1] = True
    for k in range(trous):
        m[y0 + 1 + 2 * k:y0 + 2 + 2 * k, x0:x1] = False
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=m, score=score, cls=0)


A = _region(10, 10, 60, 60)
B = _region(100, 10, 150, 60)
C = _region(10, 100, 60, 150)


# --------------------------------------------------------------------------- #
# Appariement
# --------------------------------------------------------------------------- #

def test_une_bulle_identique_est_APPARIEE_pas_gagnee():
    assert dr.apparier([A, B], [A, B]) == [0, 1]


def test_lappariement_suit_la_bulle_et_non_sa_position():
    """Une bulle « conservée » est la même bulle, pas une bulle au même rang."""
    assert dr.apparier([A, B], [B, A]) == [1, 0]


def test_une_bulle_absente_na_pas_dappariement():
    assert dr.apparier([A, B], [A]) == [0, None]


def test_deux_masques_disjoints_ont_une_iou_nulle():
    assert dr.iou_masques(A.mask, B.mask) == 0.0
    assert dr.iou_masques(A.mask, A.mask) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Vétos — le doute profite à la détection en place
# --------------------------------------------------------------------------- #

def test_perdre_une_VRAIE_bulle_est_un_veto():
    """Ce n'est pas un affinage, c'est une perte de contenu : le texte qu'elle portait ne
    serait plus ni lu ni traduit — et l'OCR comme la traduction ont déjà été payés."""
    v = dr.arbitrer([A, B], [A])
    assert not v.accepte and v.motif == "bulle_perdue"
    assert v.perdues == [1] and "2" in v.detail


def test_perdre_un_FAUX_positif_est_un_gain():
    """La règle centrale joue dans les deux sens : une région que le nettoyeur refuserait de
    nettoyer ne doit pas être détectée — donc la gagner est un véto, et la perdre est un gain.

    Cas mesuré page 44 : un gratte-ciel pris pour une bulle, score 0,36, uniformité 0,13."""
    v = dr.arbitrer([A, B], [A], uniformites_reference={1: 0.13})
    assert v.accepte and v.faux_positifs_ecartes == [1]
    assert "faux positif" in v.detail


def test_une_bulle_gagnee_NON_NETTOYABLE_est_un_veto():
    """La détecter n'apporterait qu'une région non nettoyée, un OCR de bruit et une réplique
    inventée. Le seuil est celui du nettoyeur, pas un second critère qui divergerait."""
    v = dr.arbitrer([A], [A, B], {1: 0.20})
    assert not v.accepte and v.motif == "region_non_nettoyable"
    assert "0.20" in v.detail and "0.35" in v.detail


def test_une_bulle_gagnee_NETTOYABLE_est_un_gain():
    v = dr.arbitrer([A], [A, B], {1: 0.90})
    assert v.accepte and v.gagnees == [1] and v.conservees == 1


def test_une_candidate_NON_MESUREE_nest_pas_jugee_sur_luniformite():
    """Plus sûr que de lui inventer une valeur : l'appelant n'a pas mesuré, on ne tranche pas
    à sa place — les autres vétos, eux, s'appliquent toujours."""
    assert dr.arbitrer([A], [A, B], {}).accepte is True


def test_deux_masques_qui_se_RECOUVRENT_sont_un_veto():
    """C'est aussi une corruption du cache : `save_regions` écrit UNE image d'étiquettes, donc
    un pixel partagé est attribué à la dernière région écrite et le premier masque est amputé
    en silence."""
    presque = _region(12, 12, 62, 62)
    v = dr.arbitrer([A], [A, presque], {1: 0.9})
    assert not v.accepte and v.motif == "chevauchement"


def test_une_EXPLOSION_du_nombre_de_bulles_est_un_veto():
    """Ce n'est pas une amélioration de détection, c'est un effondrement de seuil."""
    nouvelles = [_region(10 + 60 * k, 160, 50 + 60 * k, 195) for k in range(3)]
    v = dr.arbitrer([A], [A, *nouvelles], {i: 0.9 for i in range(4)})
    assert not v.accepte and v.motif == "explosion"


def test_lordre_des_vetos_va_du_plus_grave_au_plus_fin():
    """Une relance qui perd une vraie bulle ET gagne du dessin doit être refusée POUR la
    bulle perdue : c'est ce que l'utilisateur doit lire en premier."""
    v = dr.arbitrer([A, B], [A, C], uniformites={1: 0.10})
    assert v.motif == "bulle_perdue"


def test_tous_les_motifs_ont_un_libelle():
    motifs = {dr.arbitrer(*cas[0], **cas[1]).motif for cas in (
        (([A, B], [A]), {}),
        (([A], [A, B]), {"uniformites": {1: 0.1}}),
        (([A], [A, _region(12, 12, 62, 62)]), {"uniformites": {1: 0.9}}),
        (([A], [A, *[_region(10 + 60 * k, 160, 50 + 60 * k, 195) for k in range(3)]]),
         {"uniformites": {i: 0.9 for i in range(4)}}),
        (([A], [A]), {}),
    )}
    assert motifs <= set(dr.LIBELLES)


# --------------------------------------------------------------------------- #
# Gain
# --------------------------------------------------------------------------- #

def test_rien_ne_change_nest_PAS_un_gain():
    v = dr.arbitrer([A, B], [A, B])
    assert not v.accepte and v.motif == "aucun_gain" and v.conservees == 2


def test_une_GEOMETRIE_amelioree_est_un_gain_sans_bulle_gagnee():
    """Un masque mieux rempli sur la MÊME bulle veut dire que le détecteur l'a mieux cernée —
    un gain réel, et parfaitement invisible au décompte des bulles."""
    troue = _region(10, 10, 60, 60, trous=8)
    v = dr.arbitrer([troue], [A])
    assert v.accepte and v.gagnees == [] and "remplissage" in v.detail


def test_une_geometrie_DEGRADEE_nest_pas_un_gain():
    troue = _region(10, 10, 60, 60, trous=8)
    assert not dr.arbitrer([A], [troue]).accepte


def test_un_tome_sans_reference_accepte_ce_qui_est_nettoyable():
    """Première détection d'une planche : il n'y a rien à protéger."""
    assert dr.arbitrer([], [A, B], {0: 0.9, 1: 0.9}).accepte is True


def test_une_relance_qui_ne_trouve_RIEN_sur_une_page_vide_est_neutre():
    v = dr.arbitrer([], [])
    assert not v.accepte and v.motif == "aucun_gain"


def test_le_resume_lisible_dit_letat_et_le_bilan():
    assert "ACCEPTÉ" in str(dr.arbitrer([A], [A, B], {1: 0.9}))
    assert "REFUSÉ" in str(dr.arbitrer([A, B], [A]))
