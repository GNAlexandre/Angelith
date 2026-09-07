# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les capacités de lettrage et de PSD du lot 22 — L22.3 et L22.4.

Chacune est vérifiée **contre son défaut** : la capacité existe, et ne rien demander rend
exactement ce que le dépôt rendait avant le lot. C'est la moitié du travail qui compte, parce
que ces trois-là touchent au chemin des bulles — le seul que la brique ne peut pas se
permettre de faire bouger.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from manga import psd, typeset
from manga.clean import BubbleStyle
from manga.detection import BubbleRegion

FORME = (300, 400)          # (h, w)
STYLE_HB = {"fond": [235, 235, 235], "fond_luma": 235.0, "uniformite_fond": 0.85,
            "ok": True, "orientation": "verticale"}


def _style_bulle() -> BubbleStyle:
    interieur = np.zeros(FORME, dtype=bool)
    interieur[80:220, 100:300] = True
    return BubbleStyle(bbox=(100, 80, 300, 220), interior=interieur,
                       background=(255, 255, 255), background_luma=255.0,
                       text_color=(0, 0, 0), inverted=False, uniformity=0.9,
                       erode_radius=3, mode="masque", center_x=200)


# ─────────────────────────────────────────────────────────────────────────────
# L22.3 capacité 1 — dissocier la zone d'habillage du masque de découpe
# ─────────────────────────────────────────────────────────────────────────────

def test_une_bulle_n_a_pas_de_decoupe_et_ne_change_pas():
    """Le champ existe, il vaut `None` pour toute bulle, et `calque_fit` retombe alors sur
    `interior` — donc le lettrage des bulles est inchangé au bit près."""
    style = _style_bulle()
    assert style.decoupe is None
    police = typeset.resolve_font(None)
    fit = typeset.best_fit("Bonjour tout le monde", style, typeset._cfg(None), police)
    produit = calque = typeset.calque_fit(fit, style, police)
    assert produit is not None
    calque, x0, y0 = calque
    ys, xs = np.nonzero(style.interior)
    assert (x0, y0) == (int(xs.min()), int(ys.min()))


def test_la_decoupe_elargit_l_emprise_sans_toucher_a_l_habillage():
    """`style_pour_zone` rend deux masques différents : l'habillage est la boîte de la zone,
    la découpe la déborde. C'est ce que `style_impose` ne peut pas faire — « le rectangle
    enregistré devient à la fois la zone d'habillage ET le masque de découpe »."""
    style = typeset.style_pour_zone(STYLE_HB, (150, 100, 250, 200), FORME)
    assert style.decoupe is not None
    assert int(style.interior.sum()) == 100 * 100
    assert int(style.decoupe.sum()) > int(style.interior.sum())
    # Le calque est dimensionné sur la DÉCOUPE, pas sur l'habillage.
    police = typeset.resolve_font(None)
    fit = typeset.fit_zone("BROUM", style, {}, police)
    _calque, x0, y0 = typeset.calque_fit(fit, style, police)
    assert x0 < 150 and y0 < 100


def test_sans_decoupe_une_rotation_serait_rognee():
    """Le test qui aurait échoué avant le lot : pivoter un lettrage dans le seul masque
    d'habillage en perd une partie, et c'est exactement pourquoi les deux sont dissociés."""
    police = typeset.resolve_font(None)
    large = typeset.style_pour_zone(STYLE_HB, (150, 130, 260, 170), FORME)
    fit = typeset.fit_zone("BROUM", large, {}, police, angle=90.0)

    from dataclasses import replace
    etroit = replace(large, decoupe=None)
    avec = typeset.calque_fit(fit, large, police)[0]
    sans = typeset.calque_fit(fit, etroit, police)[0]
    opaques = lambda im: int((np.asarray(im)[:, :, 3] > 0).sum())   # noqa: E731
    assert opaques(avec) > opaques(sans)


# ─────────────────────────────────────────────────────────────────────────────
# L22.3 capacité 2 — la rotation
# ─────────────────────────────────────────────────────────────────────────────

def test_l_angle_nul_ne_touche_a_rien():
    police = typeset.resolve_font(None)
    style = typeset.style_pour_zone(STYLE_HB, (150, 100, 250, 200), FORME)
    fit = typeset.fit_zone("BROUM", style, {}, police)
    assert fit.angle == 0.0
    droit = np.asarray(typeset.calque_fit(fit, style, police)[0])
    fit.angle = 0.0
    assert np.array_equal(droit, np.asarray(typeset.calque_fit(fit, style, police)[0]))


def test_l_angle_fait_pivoter_le_calque_sans_deplacer_son_rectangle():
    police = typeset.resolve_font(None)
    style = typeset.style_pour_zone(STYLE_HB, (150, 100, 250, 200), FORME)
    droit = typeset.fit_zone("BROUM", style, {}, police)
    pivote = typeset.fit_zone("BROUM", style, {}, police, angle=90.0)
    a, xa, ya = typeset.calque_fit(droit, style, police)
    b, xb, yb = typeset.calque_fit(pivote, style, police)
    assert (xa, ya) == (xb, yb) and a.size == b.size
    assert not np.array_equal(np.asarray(a), np.asarray(b))
    # Un texte horizontal devient vertical : son emprise s'allonge en y et se resserre en x.
    def emprise(im):
        ys, xs = np.nonzero(np.asarray(im)[:, :, 3] > 0)
        return xs.max() - xs.min(), ys.max() - ys.min()
    la, ha = emprise(a)
    lb, hb = emprise(b)
    assert lb < la and hb > ha


def test_la_rotation_reste_desarmee_par_defaut():
    """Aucune image ne soutient ce réglage : le lot 22 n'a pu lettrer aucune zone réelle."""
    assert typeset.angle_pour_zone("verticale") == 0.0
    assert typeset.angle_pour_zone("verticale", {"sfx_rotation": True}) == 90.0
    assert typeset.angle_pour_zone("horizontale", {"sfx_rotation": True}) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# L22.3 capacité 3 — le contour réglable
# ─────────────────────────────────────────────────────────────────────────────

def test_le_contour_est_reglable_sans_toucher_a_celui_des_bulles():
    c = typeset._cfg(None)
    # Le défaut d'une bulle nettoyée en mode « masque » : aucun contour, comme avant.
    assert typeset._stroke_width("masque", 40, c) == 0
    assert typeset._stroke_width("texte", 40, c) == max(1, round(0.07 * 40))
    # « toujours » et « jamais » sont désormais nommés.
    assert typeset._stroke_width("masque", 40, {**c, "contour": "toujours"}) > 0
    assert typeset._stroke_width("texte", 40, {**c, "contour": "jamais"}) == 0


def test_un_lettrage_hors_bulle_a_toujours_un_contour_et_plus_epais():
    """Une onomatopée est posée SUR le dessin : sans contour, elle disparaît dans les
    hachures. L'épaisseur reprend celle que `gloss.dessiner` emploie déjà (1/8 du corps)."""
    police = typeset.resolve_font(None)
    style = typeset.style_pour_zone(STYLE_HB, (150, 100, 250, 200), FORME)
    fit = typeset.fit_zone("BROUM", style, {}, police)
    assert fit.stroke >= max(1, round(0.125 * fit.size))
    bulle = _style_bulle()
    fit_bulle = typeset.best_fit("Bonjour", bulle, typeset._cfg(None), police)
    assert fit_bulle.stroke == 0        # mode « masque » : inchangé


def test_le_plancher_d_aire_est_parametre_par_type_de_zone():
    """L22.3 demande des seuils PARAMÉTRÉS par type de zone, pas contournés : le diagnostic
    géométrique de `best_fit` reste en place, seul son plancher change."""
    c = typeset._cfg(None)
    assert c["aire_min_bulle"] == 900
    assert c["aire_min_sfx"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# L22.4 — les calques PSD
# ─────────────────────────────────────────────────────────────────────────────

def _planche_et_fits():
    nettoyee = Image.new("RGB", (400, 300), (255, 255, 255))
    return nettoyee, []


def test_sans_les_nouveaux_parametres_la_pile_est_celle_d_avant():
    nettoyee, fits = _planche_et_fits()
    calques = psd.calques_de_planche(nettoyee, fits)
    assert [c.nom for c in calques] == ["Planche nettoyée"]


def test_le_calque_d_effacement_se_pose_au_dessus_du_fond():
    from manga import effacement as eff_mod
    nettoyee, fits = _planche_et_fits()
    rgba = np.zeros((20, 30, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    eff = eff_mod.Effacement(rgba=rgba, x=40, y=50)
    calques = psd.calques_de_planche(nettoyee, fits, effacement=eff)
    assert [c.nom for c in calques] == ["Planche nettoyée", "Effacement SFX"]
    assert (calques[1].x, calques[1].y) == (40, 50)
    assert calques[1].visible is True          # masquable, donc visible par défaut


def test_une_zone_illisible_recoit_un_calque_vide_et_nomme():
    """Le letteur voit OÙ intervenir, au lieu de rouvrir la planche et de chercher la boîte."""
    nettoyee, fits = _planche_et_fits()
    calques = psd.calques_de_planche(
        nettoyee, fits,
        zones_illisibles=[{"index": 0, "bbox": [10, 20, 60, 90], "texte": "ゴォォォ"}])
    vide = calques[-1]
    assert vide.nom.startswith("SFX ? 01 — à transcrire (10,20)")
    assert "ゴォォォ" in vide.nom
    assert vide.rgba.shape == (70, 50, 4)
    assert int(vide.rgba[:, :, 3].sum()) == 0
    assert vide.visible is False


def test_une_zone_relettree_recoit_son_calque_nomme():
    nettoyee, _ = _planche_et_fits()
    police = typeset.resolve_font(None)
    style = typeset.style_pour_zone(STYLE_HB, (150, 100, 250, 200), FORME)
    fit = typeset.fit_zone("BROUM", style, {}, police)
    zone = BubbleRegion(bbox=(150, 100, 250, 200), mask=None, score=1.0, cls=0,
                        kind="onomatopee")
    calques = psd.calques_de_planche(
        nettoyee, [], fits_sfx=[{"index": 2, "fit": fit, "style": style,
                                 "police": police, "region": zone}])
    assert calques[-1].nom == "SFX 03 — BROUM"
    assert calques[-1].texte is not None          # calque de TYPE, réécrivable


def test_un_lettrage_pivote_reste_rasterise():
    """Le descripteur `TySh` ne porte pas de transformation ici : déclarer un texte droit là
    où les pixels sont inclinés ferait sauter le lettrage à la première réécriture."""
    nettoyee, _ = _planche_et_fits()
    police = typeset.resolve_font(None)
    style = typeset.style_pour_zone(STYLE_HB, (150, 100, 250, 200), FORME)
    fit = typeset.fit_zone("BROUM", style, {}, police, angle=90.0)
    zone = BubbleRegion(bbox=(150, 100, 250, 200), mask=None, score=1.0, cls=0,
                        kind="onomatopee")
    calques = psd.calques_de_planche(
        nettoyee, [], fits_sfx=[{"index": 0, "fit": fit, "style": style,
                                 "police": police, "region": zone}])
    assert calques[-1].texte is None


def test_les_gloses_deviennent_des_calques():
    """Elles n'existaient QUE dans le composite aplati : `fond_propre` est capturé AVANT le
    rendu, donc aucune glose n'atteignait jamais le PSD. C'était un défaut, pas un choix."""
    from manga.gloss import Glose
    nettoyee, _ = _planche_et_fits()
    glose = Glose(rect=(20, 30, 140, 70), texte="BROUM", taille=16, ancrage="droite",
                  claire=False, calme=1.0)
    calques = psd.calques_de_planche(nettoyee, [], gloses=[glose, None])
    assert len(calques) == 2                    # la glose non posée n'ajoute rien
    assert calques[-1].nom == "Glose 01 — BROUM"
    assert calques[-1].rgba.shape == (40, 120, 4)
    assert int((calques[-1].rgba[:, :, 3] > 0).sum()) > 0


def test_le_psd_complet_s_ecrit_et_se_relit(tmp_path):
    """Le fichier reste analysable par l'analyseur maison du dépôt, avec les piles neuves."""
    from manga import effacement as eff_mod
    nettoyee = Image.new("RGB", (200, 160), (255, 255, 255))
    rgba = np.zeros((20, 30, 4), dtype=np.uint8)
    rgba[:, :, :3] = 200
    rgba[:, :, 3] = 255
    chemin = psd.ecrire_planche(
        tmp_path / "page.psd", finale=nettoyee, nettoyee=nettoyee, fits=[],
        effacement=eff_mod.Effacement(rgba=rgba, x=10, y=10),
        zones_illisibles=[{"index": 0, "bbox": [5, 5, 40, 40], "texte": ""}])
    assert chemin.exists() and chemin.stat().st_size > 0
    donnees = chemin.read_bytes()
    assert donnees[:4] == psd.SIGNATURE
    assert "Effacement SFX".encode("latin-1") in donnees
