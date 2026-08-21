# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Gloses des onomatopées (lot 9).

LE test de ce module est `test_une_glose_ne_recouvre_jamais...` : il tient le principe
directeur de la brique. Tout le reste en découle.
"""
import numpy as np
from PIL import Image

from manga import gloss
from manga.detection import BubbleRegion

W, H = 400, 300


def _region(x0, y0, x1, y1, kind="onomatopee") -> BubbleRegion:
    m = np.zeros((H, W), dtype=bool)
    m[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=m, score=1.0, cls=0, kind=kind)


def _planche(couleur=(255, 255, 255)) -> Image.Image:
    return Image.new("RGB", (W, H), couleur)


# --------------------------------------------------------------------------- #
# L'invariant
# --------------------------------------------------------------------------- #

def test_une_glose_ne_recouvre_jamais_l_encre_ni_une_bulle():
    """L'IA ne dessine jamais À LA PLACE du dessinateur. Une glose s'AJOUTE à côté ; si elle
    recouvrait l'encre japonaise ou le lettrage d'une bulle, elle détruirait ce qu'elle est
    censée servir."""
    sfx = [_region(40, 40, 90, 90), _region(300, 200, 360, 250)]
    bulles = [_region(150, 100, 260, 190, kind="bulle")]
    gloses, _refus = gloss.placer(_planche(), sfx, ["BOUM", "VLAN"], bulles=bulles)

    interdit = np.zeros((H, W), dtype=bool)
    for r in sfx + bulles:
        interdit |= r.mask
    for g in gloses:
        if g is None:
            continue
        x0, y0, x1, y1 = g.rect
        assert not interdit[y0:y1, x0:x1].any(), f"la glose {g.texte} mord sur l'encre"


def test_deux_gloses_ne_se_chevauchent_pas():
    """Deux onomatopées voisines se disputeraient le même blanc."""
    sfx = [_region(100, 100, 140, 140), _region(160, 100, 200, 140)]
    gloses, _ = gloss.placer(_planche(), sfx, ["BOUM", "VLAN"])
    poses = [g for g in gloses if g is not None]
    for i, a in enumerate(poses):
        for b in poses[i + 1:]:
            recouvre = not (a.rect[2] <= b.rect[0] or b.rect[2] <= a.rect[0]
                            or a.rect[3] <= b.rect[1] or b.rect[3] <= a.rect[1])
            assert not recouvre


def test_la_glose_reste_dans_la_planche():
    """Une onomatopée collée au bord ne doit pas pousser sa glose hors de l'image."""
    sfx = [_region(0, 0, 40, 40), _region(W - 40, H - 40, W, H)]
    gloses, _ = gloss.placer(_planche(), sfx, ["BOUM", "VLAN"])
    for g in gloses:
        if g is None:
            continue
        assert 0 <= g.rect[0] and 0 <= g.rect[1]
        assert g.rect[2] <= W and g.rect[3] <= H


# --------------------------------------------------------------------------- #
# Refus — dire plutôt que poser n'importe où
# --------------------------------------------------------------------------- #

def test_sans_zone_libre_rien_n_est_pose_et_c_est_signale():
    """Une planche entièrement occupée : on ne pose rien, et le rapport le dit. Même règle
    que le rattrapage — une mauvaise pose est pire qu'une absence signalée."""
    sfx = [_region(0, 0, W, H)]
    gloses, refus = gloss.placer(_planche(), sfx, ["BOUM"])
    assert gloses == [None]
    assert len(refus) == 1
    assert "aucune zone libre" in refus[0]


def test_une_traduction_vide_n_est_pas_un_refus():
    """Le prompt demande explicitement une ligne vide pour un filigrane de scan. Ne rien
    poser est alors le comportement VOULU, pas un incident à remonter."""
    gloses, refus = gloss.placer(_planche(), [_region(40, 40, 90, 90)], [""])
    assert gloses == [None]
    assert refus == []


def test_une_traduction_manquante_ne_leve_pas():
    """Moins de traductions que de zones : le rendu ne doit pas s'arrêter pour autant."""
    sfx = [_region(40, 40, 90, 90), _region(200, 200, 250, 250)]
    gloses, _ = gloss.placer(_planche(), sfx, ["BOUM"])
    assert len(gloses) == 2
    assert gloses[1] is None


# --------------------------------------------------------------------------- #
# Choix de l'emplacement
# --------------------------------------------------------------------------- #

def test_la_zone_calme_est_preferee():
    """À contrainte égale, la glose va sur l'aplat plutôt que sur les hachures : c'est ce
    qui la rend lisible."""
    arr = np.full((H, W, 3), 255, dtype=np.uint8)
    # Bruit dense à GAUCHE de l'onomatopée, aplat à droite.
    arr[:, :150:2] = 0
    sfx = [_region(160, 130, 200, 170)]
    gloses, _ = gloss.placer(Image.fromarray(arr), sfx, ["BOUM"])
    assert gloses[0] is not None
    assert gloses[0].rect[0] >= 200, "la glose s'est posée sur le bruit"


def test_le_texte_prend_la_polarite_de_son_fond():
    """Sur une planche sombre, une glose noire serait invisible."""
    sfx = [_region(40, 40, 90, 90)]
    claire, _ = gloss.placer(_planche((10, 10, 10)), sfx, ["BOUM"])
    sombre, _ = gloss.placer(_planche((250, 250, 250)), sfx, ["BOUM"])
    assert claire[0].claire is True
    assert sombre[0].claire is False


def test_le_corps_est_borne_par_la_configuration():
    sfx = [_region(20, 20, 380, 280)]      # énorme : le corps partirait très haut
    gloses, _ = gloss.placer(_planche(), sfx, ["BOUM"],
                             cfg={"glose_taille_max": 14, "glose_taille_min": 10})
    if gloses[0] is not None:
        assert 10 <= gloses[0].taille <= 14


# --------------------------------------------------------------------------- #
# Dessin
# --------------------------------------------------------------------------- #

def test_dessiner_ne_touche_pas_a_l_original():
    img = _planche()
    avant = np.asarray(img).copy()
    gloses, _ = gloss.placer(img, [_region(40, 40, 90, 90)], ["BOUM"])
    gloss.dessiner(img, gloses)
    assert np.array_equal(np.asarray(img), avant)


def test_dessiner_ecrit_bien_quelque_chose():
    img = _planche()
    gloses, _ = gloss.placer(img, [_region(40, 40, 90, 90)], ["BOUM"])
    out = gloss.dessiner(img, gloses)
    assert not np.array_equal(np.asarray(out), np.asarray(img))


def test_dessiner_sans_glose_rend_une_image_identique():
    img = _planche()
    out = gloss.dessiner(img, [None, None])
    assert np.array_equal(np.asarray(out), np.asarray(img))


def test_les_pixels_hors_des_rectangles_de_glose_sont_intacts():
    """La garantie qui prolonge celle de `clean.py` : hors des rectangles décidés par
    `placer`, la planche ressort bit-à-bit identique."""
    img = _planche((200, 180, 160))
    sfx = [_region(40, 40, 90, 90)]
    gloses, _ = gloss.placer(img, sfx, ["BOUM"])
    out = np.asarray(gloss.dessiner(img, gloses))
    avant = np.asarray(img)
    touche = np.zeros((H, W), dtype=bool)
    for g in gloses:
        if g is not None:
            x0, y0, x1, y1 = g.rect
            touche[y0:y1, x0:x1] = True
    assert np.array_equal(out[~touche], avant[~touche])
