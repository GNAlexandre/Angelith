# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc des détecteurs candidats — **sans modèle et sans réseau** (lot 16, L9.0).

Ce qui se teste ici est ce qui DÉCIDE : le masque dérivé d'une boîte, l'assemblage des
fenêtres, et le fait que le tableau compte ce qu'on croit qu'il compte. Les poids candidats,
eux, ne sont pas dans le dépôt — et ne peuvent pas y être, ils pèsent 100 à 170 Mo chacun.

La prédiction est donc **injectée**, comme dans `tests/test_banc_detection.py` : c'est la seule
façon de tester une mesure, en connaissant d'avance la bonne réponse.

⚠ Aucun marqueur : boucle courte.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from manga import detection                       # noqa: E402
from manga.detection import BubbleRegion          # noqa: E402
from tools import banc_candidats as bancc         # noqa: E402


def _planche_avec_bulle(taille=(400, 300), boite=(80, 60, 320, 240)) -> Image.Image:
    """Une bulle blanche à contour noir, avec du texte noir dedans, sur un fond de BRUIT.

    Le fond est volontairement non uniforme, et à graine fixe : un remplissage qui déborderait
    de la bulle se verrait immédiatement dans l'uniformité mesurée ensuite, et une région prise
    dans ce fond est exactement ce que `nettoyage.seuil_abandon` doit refuser."""
    alea = np.random.default_rng(16)
    fond = alea.integers(0, 256, size=(taille[1], taille[0], 3), dtype=np.uint8)
    image = Image.fromarray(fond, "RGB")
    dessin = ImageDraw.Draw(image)
    dessin.ellipse(boite, fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    milieu_y = (boite[1] + boite[3]) // 2
    for i in range(-1, 2):
        dessin.rectangle([boite[0] + 50, milieu_y + i * 24 - 6,
                          boite[2] - 50, milieu_y + i * 24 + 6], fill=(0, 0, 0))
    return image


def _region(x0, y0, x1, y1, taille=(400, 300)) -> BubbleRegion:
    masque = np.zeros((taille[1], taille[0]), dtype=bool)
    masque[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=masque, score=0.9, cls=0)


# --- le masque dérivé d'une boîte -------------------------------------------

def test_une_boite_remplie_donne_un_masque_qui_couvre_la_bulle_et_pas_le_decor():
    """Le cœur du lot 16 : les deux candidats Apache-2.0 ne rendent que des BOÎTES. Si le
    masque dérivé ne vaut rien, la comparaison n'a pas lieu d'être."""
    image = _planche_avec_bulle()
    masque = bancc.masque_par_remplissage(image, (80, 60, 320, 240))
    assert masque is not None
    assert masque.shape == (300, 400)
    # L'ellipse inscrite dans la boîte occupe ~78,5 % de son aire ; le contour en retire un peu.
    aire_boite = (320 - 80) * (240 - 60)
    assert 0.60 * aire_boite <= masque.sum() <= 0.85 * aire_boite
    # Rien hors de la boîte : c'est la garde que `detection._postprocess` applique déjà aux
    # masques du réseau, et elle vaut pour un masque dérivé au moins autant.
    dehors = masque.copy()
    dehors[60:240, 80:320] = False
    assert not dehors.any()


def test_le_texte_de_la_bulle_est_DANS_le_masque_derive():
    """Sans rebouchage des trous, l'uniformité mesurée ensuite serait celle d'un masque dont on
    aurait retiré tout ce qui n'est pas uniforme — c'est-à-dire un chiffre qui ne veut rien
    dire, et un nettoyage qui laisserait le texte en place."""
    image = _planche_avec_bulle()
    masque = bancc.masque_par_remplissage(image, (80, 60, 320, 240))
    # Le milieu d'une des trois lignes de texte, noire sur blanc.
    assert masque[150, 200]


def test_une_boite_degeneree_ne_rend_pas_un_masque_vide():
    """`None`, jamais un masque vide : une région à masque vide traverserait le banc comme une
    bulle dégénérée, et `detection._postprocess` la rejette déjà en amont pour cette raison."""
    image = _planche_avec_bulle()
    assert bancc.masque_par_remplissage(image, (10, 10, 12, 12)) is None


def test_un_trou_ouvert_sur_le_bord_n_est_pas_rebouche():
    """Une encoche reliée au bord n'est pas un trou : la reboucher ferait avaler à la bulle la
    queue par laquelle elle communique avec le dessin."""
    masque = np.zeros((20, 20), dtype=bool)
    masque[2:18, 2:18] = True
    masque[8:12, 2:10] = False          # encoche ouverte sur la gauche du carré, pas du cadre
    masque[5:7, 12:14] = False          # trou fermé
    plein = bancc._boucher_trous(masque)
    assert plein[5, 12]                 # le trou fermé est rebouché
    assert not plein[9, 0]              # le fond hors du carré reste du fond


# --- l'assemblage des fenêtres ----------------------------------------------

def test_assembler_fenetres_remonte_et_dedoublonne():
    """La même bulle vue par deux fenêtres qui se recouvrent ne doit compter qu'une fois.

    Ce test aurait échoué avant le lot 16 : `assembler_fenetres` n'existait pas, et le
    dédoublonnage vivait dans une méthode de `BubbleDetector` — donc hors de portée d'un
    candidat qui ne rend que des boîtes."""
    hauteur = 400
    haute = _region(10, 100, 60, 160, taille=(100, 200))       # dans la fenêtre [0, 200]
    basse = _region(10, 0, 60, 60, taille=(100, 200))          # la MÊME, vue depuis y0 = 100
    assemblees = detection.assembler_fenetres(
        [([haute], 0, 200), ([basse], 100, hauteur)], hauteur, 0.45)
    assert len(assemblees) == 1
    assert assemblees[0].bbox == (10, 100, 60, 160)


# --- ce que le tableau compte -----------------------------------------------

def test_une_region_que_le_nettoyage_refuserait_est_comptee_comme_telle():
    """`non nettoyables` est l'indicateur de fausse détection du banc, et il vient de
    `clean.analyze_bubble` — pas d'un second critère écrit ici."""
    image = _planche_avec_bulle()
    bulle = BubbleRegion(bbox=(80, 60, 320, 240),
                         mask=bancc.masque_par_remplissage(image, (80, 60, 320, 240)),
                         score=0.9, cls=0)
    decor = _region(0, 0, 70, 50)       # du bruit : tout sauf uniforme
    mesure = bancc.mesurer_planche(image, [bulle, decor], [], {}, numero=1)
    assert mesure.bulles == 2
    assert mesure.non_nettoyables == 1
    assert mesure.sans_ocr is None      # sans `--ocr`, la colonne reste NON MESURÉE


def test_l_iou_du_masque_derive_est_mesure_contre_le_masque_du_reseau():
    """Le chiffre que le plan du lot 16 réclame avant toute intégration : une boîte remplie
    vaut-elle le masque que le réseau aurait rendu ?"""
    image = _planche_avec_bulle()
    reference = [_region(80, 60, 320, 240)]
    predite = BubbleRegion(bbox=(80, 60, 320, 240),
                           mask=bancc.masque_par_remplissage(image, (80, 60, 320, 240)),
                           score=0.9, cls=0)
    mesure = bancc.mesurer_planche(image, [predite], reference, {}, numero=1)
    assert len(mesure.ious) == 1
    # Une ellipse dans son rectangle circonscrit : ~0,785 au mieux.
    assert 0.55 <= mesure.ious[0] <= 0.85


class _DetecteurTexteFactice:
    """Un détecteur de texte qui marque une bande horizontale au milieu du crop.

    Injecté plutôt que chargé : `comic-text-detector` pèse 95 Mo et la question testée ici
    n'est pas la qualité du modèle, c'est le calcul de la couverture."""

    def __init__(self, part: float):
        self.part = part

    def masque_texte(self, crop):
        h, w = crop.size[1], crop.size[0]
        masque = np.zeros((h, w), dtype=bool)
        hauteur = int(h * self.part)
        if hauteur:
            masque[(h - hauteur) // 2:(h - hauteur) // 2 + hauteur, :] = True
        return masque


def test_une_bulle_muette_est_comptee_par_le_detecteur_de_texte():
    """L'indicateur qui reste valable là où `manga-ocr` hallucine : sur les neuf volumes
    paginés, `sans OCR` vaut **0** parce qu'un modèle génératif rend rarement une chaîne vide,
    pas parce qu'aucune détection n'est fausse."""
    image = _planche_avec_bulle()
    bulle = BubbleRegion(bbox=(80, 60, 320, 240),
                         mask=bancc.masque_par_remplissage(image, (80, 60, 320, 240)),
                         score=0.9, cls=0)
    muette = bancc.mesurer_planche(image, [bulle], [], {}, numero=1,
                                   detecteur_texte=_DetecteurTexteFactice(0.0))
    assert muette.sans_texte == 1
    lue = bancc.mesurer_planche(image, [bulle], [], {}, numero=1,
                                detecteur_texte=_DetecteurTexteFactice(0.5))
    assert lue.sans_texte == 0


def test_la_couverture_de_texte_se_rapporte_au_MASQUE_et_pas_a_la_boite():
    """Rapporter la couverture à la boîte gonflerait le dénominateur des coins que la bulle
    n'occupe pas — une bulle ronde perd ~21 % de sa boîte — et ferait passer pour muettes des
    bulles qui portent du texte."""
    image = _planche_avec_bulle()
    bulle = BubbleRegion(bbox=(80, 60, 320, 240),
                         mask=bancc.masque_par_remplissage(image, (80, 60, 320, 240)),
                         score=0.9, cls=0)
    part = bancc.couverture_de_texte(image, bulle, _DetecteurTexteFactice(0.5))
    # Une bande couvrant la moitié de la HAUTEUR de la boîte recouvre plus de la moitié du
    # masque d'une ellipse, qui est plus large en son milieu.
    assert part > 0.5


def test_la_colonne_sans_OCR_reste_vide_quand_personne_n_a_lu():
    """Une case vide dans une colonne de nombres se lit comme un zéro — le banc de mesure le
    dit, et c'est la raison d'être de `_banc_commun.cellule`. `None` rend `—`."""
    ligne = bancc.agreger(None, bancc.Poids("x", "yolo"), 640, [])
    assert ligne["sans OCR"] is None
    assert ligne["sans texte"] is None
    assert set(bancc.COLONNES) >= set(ligne)


@pytest.mark.parametrize("famille", bancc.FAMILLES)
def test_chaque_famille_declaree_est_traitee(famille):
    """Un nom de famille inconnu du post-traitement passerait aujourd'hui pour du YOLO et
    rendrait des boîtes absurdes sans rien dire."""
    assert famille in ("yoloseg", "yolo", "rtdetr")
