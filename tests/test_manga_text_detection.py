# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Détection du texte posé SUR LE DESSIN (lot 9).

Aucun poids n'est chargé ici : `hors_des_bulles` et `fusionner_proches` sont des fonctions
pures sur des masques numpy, et c'est tout l'intérêt de les avoir séparées de l'inférence —
la logique qui décide ce qui est du texte hors bulle se teste sans les 95 Mo du modèle.
"""
import numpy as np
import pytest

from manga.detection import BubbleRegion
from manga.text_detection import (AIRE_MIN, TRI_BRUIT, TRI_JAPONAIS, TRI_MOBILIER,
                                  TRI_PONCTUATION, VOISINAGE_FRAC, fusionner_proches,
                                  hors_des_bulles, mobilier_de_tome, trier_zone)

TAILLE = (400, 300)          # (h, w)


def _masque(*rects) -> np.ndarray:
    m = np.zeros(TAILLE, dtype=bool)
    for x0, y0, x1, y1 in rects:
        m[y0:y1, x0:x1] = True
    return m


def _bulle(x0, y0, x1, y1) -> BubbleRegion:
    m = np.zeros(TAILLE, dtype=bool)
    m[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=m, score=0.9, cls=0)


# --------------------------------------------------------------------------- #
# Containment : la question est « ce texte est-il déjà pris en charge ? »
# --------------------------------------------------------------------------- #

def test_le_texte_dans_une_bulle_est_ecarte():
    """Une réplique déjà traitée par le chemin nominal ne doit pas être glosée en double."""
    texte = _masque((60, 60, 110, 110))
    bulle = _bulle(20, 20, 200, 200)
    assert hors_des_bulles(texte, [bulle]) == []


def test_le_texte_hors_bulle_est_retenu():
    texte = _masque((220, 220, 280, 280))
    bulle = _bulle(20, 20, 200, 200)
    zones = hors_des_bulles(texte, [bulle])
    assert len(zones) == 1
    assert zones[0].kind == "onomatopee"


def test_sans_aucune_bulle_tout_le_texte_est_hors_bulle():
    """Le cas des pleines pages d'action : 23 planches du Vol.2 n'ont AUCUNE bulle, et c'est
    précisément là que le japonais restait le plus visible."""
    texte = _masque((50, 50, 120, 120))
    assert len(hors_des_bulles(texte, [])) == 1


def test_le_containment_se_mesure_sur_les_masques_pas_les_boites():
    """Une petite réplique dans un grand ballon a un IoU de boîtes ridicule (0,005) et un
    containment de 1,0. C'est le containment qui répond à la bonne question."""
    petit = _masque((100, 100, 115, 115))          # 225 px²
    grand = _bulle(20, 20, 220, 220)               # 40 000 px²
    inter = float((petit & grand.mask).sum())
    iou = inter / (petit.sum() + grand.mask.sum() - inter)
    assert iou < 0.01                              # l'IoU dirait « hors bulle »
    assert hors_des_bulles(petit, [grand]) == []   # le containment dit la vérité


def test_un_texte_a_cheval_reste_retenu():
    """Sous le seuil de containment, la zone est traitée : mieux vaut une glose de trop
    qu'un texte japonais silencieusement abandonné."""
    texte = _masque((180, 100, 260, 140))          # moitié dedans, moitié dehors
    bulle = _bulle(20, 20, 220, 220)
    assert len(hors_des_bulles(texte, [bulle])) == 1


# --------------------------------------------------------------------------- #
# Aire minimale
# --------------------------------------------------------------------------- #

def test_le_bruit_de_trame_est_ignore():
    minuscule = _masque((50, 50, 55, 55))          # 25 px², très en dessous du seuil
    assert hors_des_bulles(minuscule, []) == []


def test_le_seuil_d_aire_est_reglable():
    petit = _masque((50, 50, 70, 70))              # 400 px²
    assert hors_des_bulles(petit, []) == []
    assert len(hors_des_bulles(petit, [], aire_min=100)) == 1


# --------------------------------------------------------------------------- #
# Groupement RELATIF — le correctif mesuré sur la page 63
# --------------------------------------------------------------------------- #

def test_les_glyphes_d_une_meme_onomatopee_sont_reunis():
    """Page 63 du Vol.2 : la colonne ゴォォォ est faite de glyphes de ~90 px séparés de
    ~30 px. Sans critère relatif, elle sortait en 8 zones — donc 8 gloses contradictoires
    posées le long d'un seul son."""
    glyphes = [_masque((10, y, 100, y + 90)) for y in (0, 120, 240)]
    assert len(fusionner_proches(glyphes)) == 1


def test_deux_textes_eloignes_restent_distincts():
    a = _masque((10, 10, 60, 60))
    b = _masque((240, 240, 290, 290))
    assert len(fusionner_proches([a, b])) == 2


def test_le_critere_est_relatif_a_la_taille():
    """Le même écart de 40 px sépare deux petits fragments et réunit deux grands : c'est
    exactement ce qu'un rayon de dilatation en pixels ne sait pas faire."""
    petits = [_masque((10, 10, 30, 30)), _masque((10, 70, 30, 90))]     # 20 px, écart 40
    grands = [_masque((10, 10, 110, 110)), _masque((10, 150, 110, 250))]  # 100 px, écart 40
    assert len(fusionner_proches(petits)) == 2
    assert len(fusionner_proches(grands)) == 1


def test_fusionner_proches_est_stable_sur_zero_et_un_element():
    assert fusionner_proches([]) == []
    un = [_masque((10, 10, 40, 40))]
    assert len(fusionner_proches(un)) == 1


def test_la_fusion_preserve_tous_les_pixels():
    """Réunir deux fragments ne doit ni en perdre ni en inventer : la glose se place autour
    de l'encre réelle, et un pixel oublié est un pixel qu'on risque de recouvrir."""
    a = _masque((10, 10, 100, 100))
    b = _masque((10, 130, 100, 220))
    (fusion,) = fusionner_proches([a, b])
    assert np.array_equal(fusion, a | b)


# --------------------------------------------------------------------------- #
# Ordre de lecture
# --------------------------------------------------------------------------- #

def test_l_ordre_est_droite_vers_gauche():
    """Sens manga, comme pour les bulles : la zone la plus à DROITE se lit en premier."""
    texte = _masque((20, 20, 90, 90), (200, 20, 270, 90))
    zones = hors_des_bulles(texte, [])
    assert len(zones) == 2
    assert zones[0].bbox[0] > zones[1].bbox[0]


def test_les_masques_rendus_sont_ceux_de_l_encre_pas_ceux_dilates():
    """La dilatation ne sert qu'à DÉCIDER du groupement. Rendre le masque gonflé ferait
    ensuite reculer la glose bien au-delà de l'encre, et mordrait sur le dessin."""
    texte = _masque((100, 100, 160, 160))
    (zone,) = hors_des_bulles(texte, [])
    assert int(zone.mask.sum()) == int(texte.sum())
    assert zone.bbox == (100, 100, 160, 160)


def test_un_masque_vide_ne_produit_rien():
    assert hors_des_bulles(np.zeros(TAILLE, dtype=bool), []) == []


@pytest.mark.parametrize("valeur", [AIRE_MIN, VOISINAGE_FRAC])
def test_les_constantes_sont_documentees(valeur):
    """Garde-fou de relecture : ces deux valeurs viennent d'une mesure sur le Vol.2, pas
    d'un choix arbitraire. Les voir bouger doit obliger à relire le commentaire."""
    assert valeur > 0


# --------------------------------------------------------------------------- #
# Mobilier de page — lot 13
#
# Le discriminant n'est ni la position ni le contenu : c'est la RÉCURRENCE géométrique.
# Mesuré sur le Vol.1 du *manga A* : 92 zones écartées en 2 groupes (les filigranes des coins,
# présents sur 47 et 45 planches sur 141 porteuses). Sur *manga B*, qui n'a AUCUN
# filigrane, le filtre écarte 0 zone — c'est la preuve qu'il ne sur-écarte pas.
# --------------------------------------------------------------------------- #

def _pages(boites_par_page, taille=(1000, 1600)):
    return {p: (list(b), taille) for p, b in boites_par_page.items()}


def test_un_filigrane_recurrent_est_ecarte():
    coin = (30, 28, 164, 51)
    pages = _pages({p: [coin, (400, 700, 500, 800)] for p in range(1, 11)})
    mobilier, groupes = mobilier_de_tome(pages)
    assert len(groupes) >= 1
    assert all((p, 0) in mobilier for p in range(1, 11))


def test_une_onomatopee_unique_nest_JAMAIS_du_mobilier():
    """Chaque planche a sa zone à un endroit différent : rien ne se répète."""
    pages = _pages({p: [(50 * p, 40 * p, 50 * p + 90, 40 * p + 90)] for p in range(1, 11)})
    mobilier, groupes = mobilier_de_tome(pages)
    assert mobilier == set() and groupes == []


def test_sous_le_seuil_de_planches_rien_nest_ecarte():
    """Deux planches sur dix ne font pas une récurrence — le seuil vaut 30 %.

    ⚠ Les huit autres planches portent des zones à des positions TOUTES DIFFÉRENTES : leur
    donner une position commune en ferait un groupe récurrent de 8/10, et le test vérifierait
    alors l'inverse de ce qu'il annonce."""
    coin = (30, 28, 164, 51)
    pages = _pages({**{p: [coin] for p in (1, 2)},
                    **{p: [(60 * p, 40 * p, 60 * p + 90, 40 * p + 90)]
                       for p in range(3, 11)}})
    assert mobilier_de_tome(pages)[0] == set()


def test_une_zone_TROP_GRANDE_nest_jamais_du_mobilier():
    """Une onomatopée pleine page ne se répète pas d'une planche à l'autre ; si elle le
    faisait, on ne veut pas l'effacer du rapport pour autant."""
    enorme = (0, 0, 900, 1500)          # bien au-delà de 5 % de la planche
    pages = _pages({p: [enorme] for p in range(1, 11)})
    assert mobilier_de_tome(pages)[0] == set()


def test_deux_zones_de_la_MEME_planche_ne_forment_pas_une_recurrence():
    """Deux onomatopées superposées sur une seule planche ne sont pas un filigrane."""
    boite = (30, 28, 164, 51)
    pages = _pages({1: [boite, boite, boite, boite]})
    assert mobilier_de_tome(pages)[0] == set()


def test_un_tome_trop_court_nest_pas_juge():
    pages = _pages({1: [(30, 28, 164, 51)], 2: [(30, 28, 164, 51)]})
    assert mobilier_de_tome(pages)[0] == set()


def test_les_groupes_sont_decrits_pour_le_rapport():
    """Un filtre qui écarte 63 % des zones doit pouvoir être vérifié d'un coup d'œil."""
    coin = (30, 28, 164, 51)
    pages = _pages({p: [coin] for p in range(1, 11)})
    _mobilier, groupes = mobilier_de_tome(pages)
    assert groupes[0]["planches"] == 10
    assert groupes[0]["boite"] == list(coin) or tuple(groupes[0]["boite"]) == coin


# --------------------------------------------------------------------------- #
# Triage — ce qui part au LLM, ce qui se rend sans lui, ce qu'on jette
# --------------------------------------------------------------------------- #

def test_le_japonais_part_au_LLM():
    assert trier_zone("ゴォォォ") == TRI_JAPONAIS
    assert trier_zone("陽弥……") == TRI_JAPONAIS


def test_la_ponctuation_seule_se_rend_SANS_appel():
    """`！！` posé à côté d'un visage stupéfait est du CONTENU. `latiniser` le rend en `!!`,
    fidèlement — là où un modèle broderait."""
    for t in ("！！", "．．．", "〜", "！？"):
        assert trier_zone(t) == TRI_PONCTUATION, t


def test_les_lettres_sans_japonais_sont_du_BRUIT():
    """`manga-ocr` hallucine sur du dessin : `ＥｌｅＨＴ`, `ＯＦＦＦＩＮＥ`, `［ｉｓｕｃｅ］`.
    Un mot latin authentique dans une onomatopée japonaise est assez rare pour qu'on préfère
    le perdre."""
    for t in ("ＥｌｅＨＴ", "ＯＦＦＦＩＮＥ", "RawLazy.SI", "１００"):
        assert trier_zone(t) == TRI_BRUIT, t


def test_le_mobilier_prime_sur_tout():
    assert trier_zone("ゴォォォ", mobilier=True) == TRI_MOBILIER


def test_une_zone_vide_est_du_bruit():
    assert trier_zone("") == TRI_BRUIT
    assert trier_zone("   ") == TRI_BRUIT
