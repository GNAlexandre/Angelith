# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'effacement déterministe du texte hors bulle — lot 22.

Trois familles de tests, et la première est la seule qui ne se négocie pas :

1. **Les garde-fous.** Une lecture non concordante, un style non mesuré, un fond trop
   structuré : dans les trois cas, **aucun pixel n'est écrit**. Le premier est le critère 10
   du plan de lot et aucune clé de configuration ne le désarme — c'est cela qu'on vérifie ici,
   pas seulement que le défaut est sûr.
2. **L'invariant.** Rien hors de la boîte de la zone n'est jamais modifié, et l'image d'entrée
   n'est jamais mutée. C'est le pendant hors bulle du `paint &= region.mask` de `clean.py`.
3. **L'iso-comportement.** Mode « aucun » et mode « calque » rendent une planche aplatie
   identique **au bit près** à celle d'avant le lot.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from manga import effacement, rendu, sfx_lecture
from manga.detection import BubbleRegion

STYLE_UNI = {"fond": [235, 235, 235], "fond_luma": 235.0, "uniformite_fond": 0.92,
             "ok": True, "orientation": "horizontale"}


def _planche(fond: int = 235) -> tuple[Image.Image, np.ndarray]:
    arr = np.full((240, 320, 3), fond, dtype=np.uint8)
    arr[100:140, 120:220] = 12          # le « glyphe »
    return Image.fromarray(arr), arr


def _zone(bbox=(110, 90, 230, 150)) -> BubbleRegion:
    masque = np.zeros((240, 320), dtype=bool)
    masque[bbox[1]:bbox[3], bbox[0]:bbox[2]] = True
    return BubbleRegion(bbox=bbox, mask=masque, score=1.0, cls=0, kind="onomatopee")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Les garde-fous
# ─────────────────────────────────────────────────────────────────────────────

def test_une_lecture_douteuse_n_est_jamais_effacee():
    """Critère 10 du plan de lot, et le plus important de sa liste."""
    image, _ = _planche()
    eff = effacement.effacer_zones(image, [_zone()], [STYLE_UNI],
                                   [sfx_lecture.LECTURE_DOUTEUSE])
    assert eff.rgba is None
    assert eff.pixels == 0
    assert eff.motifs() == {effacement.MOTIF_LECTURE_DOUTEUSE: 1}


def test_un_verdict_absent_vaut_douteux():
    """Une seule voie de lecture ne concorde avec rien. C'est l'état réel du dépôt, et
    l'appeler « sûre » baptiserait le problème."""
    image, _ = _planche()
    eff = effacement.effacer_zones(image, [_zone()], [STYLE_UNI], None)
    assert eff.rgba is None
    assert eff.motifs() == {effacement.MOTIF_LECTURE_DOUTEUSE: 1}


@pytest.mark.parametrize("cle,valeur", [
    ("exiger_lecture_sure", False),
    ("lecture_douteuse", True),
    ("forcer", True),
])
def test_aucune_cle_de_configuration_ne_desarme_le_garde_fou(cle, valeur):
    """La règle est DANS LE CODE. `fusion` ignore les clés inconnues, donc inventer une clé
    ne peut pas ouvrir la porte — et c'est exactement la propriété qu'on veut verrouiller."""
    image, _ = _planche()
    eff = effacement.effacer_zones(image, [_zone()], [STYLE_UNI],
                                   [sfx_lecture.LECTURE_DOUTEUSE], {cle: valeur})
    assert eff.rgba is None


def test_sous_le_seuil_d_abandon_rien_n_est_peint():
    """Le palier du gratte-ciel de la page 44. En dessous, la zone garde son texte source."""
    image, avant = _planche()
    style = dict(STYLE_UNI, uniformite_fond=0.13)
    eff = effacement.effacer_zones(image, [_zone()], [style], [sfx_lecture.LECTURE_SURE])
    assert eff.rgba is None
    assert eff.motifs() == {effacement.MOTIF_FOND_NON_UNIFORME: 1}
    assert np.array_equal(np.asarray(effacement.composer(image, eff)), avant)


def test_un_style_non_mesure_ne_peint_rien():
    image, _ = _planche()
    for style in (None, dict(STYLE_UNI, ok=False)):
        eff = effacement.effacer_zones(image, [_zone()], [style],
                                       [sfx_lecture.LECTURE_SURE])
        assert eff.rgba is None
        assert eff.motifs() == {effacement.MOTIF_MESURE_ABSENTE: 1}


def test_une_zone_sans_encre_est_dite_telle():
    """Un aplat n'a rien à effacer, et le rapport doit pouvoir le distinguer d'un refus."""
    image = Image.fromarray(np.full((240, 320, 3), 235, dtype=np.uint8))
    eff = effacement.effacer_zones(image, [_zone()], [STYLE_UNI],
                                   [sfx_lecture.LECTURE_SURE])
    assert eff.rgba is None
    assert eff.motifs() == {effacement.MOTIF_SANS_ENCRE: 1}


# ─────────────────────────────────────────────────────────────────────────────
# 2. L'invariant
# ─────────────────────────────────────────────────────────────────────────────

def test_rien_hors_de_la_boite_n_est_modifie():
    """Le pendant hors bulle du `paint &= region.mask` de `clean.py`. Vérifié avec une
    dilatation volontairement excessive : c'est précisément elle qui déborderait."""
    image, avant = _planche()
    zone = _zone()
    x0, y0, x1, y1 = zone.bbox
    eff = effacement.effacer_zones(image, [zone], [STYLE_UNI],
                                   [sfx_lecture.LECTURE_SURE], {"dilatation": 12.0})
    apres = np.asarray(effacement.composer(image, eff))
    hors = np.ones((240, 320), dtype=bool)
    hors[y0:y1, x0:x1] = False
    assert np.array_equal(apres[hors], avant[hors])


def test_l_image_d_entree_n_est_jamais_mutee():
    """C'est la voie 1 de L22.6 : l'effacement est un étage, pas une modification du
    nettoyage. Sans cette propriété, `sfx` devrait entrer dans le graphe d'invalidation et
    tous les rendus existants seraient périmés."""
    image, avant = _planche()
    effacement.effacer_zones(image, [_zone()], [STYLE_UNI], [sfx_lecture.LECTURE_SURE])
    assert np.array_equal(np.asarray(image), avant)


def test_le_calque_est_rogne_a_l_emprise_peinte():
    """Une planche dont trois glyphes sont effacés ne porte pas un calque pleine page."""
    image, _ = _planche()
    eff = effacement.effacer_zones(image, [_zone()], [STYLE_UNI],
                                   [sfx_lecture.LECTURE_SURE])
    assert eff.rgba is not None
    hauteur, largeur = eff.rgba.shape[:2]
    assert largeur < 320 and hauteur < 240
    # Tout pixel opaque du calque tombe bien dans la boîte de la zone.
    ys, xs = np.nonzero(eff.rgba[:, :, 3] > 0)
    assert (xs + eff.x).min() >= 110 and (xs + eff.x).max() < 230
    assert (ys + eff.y).min() >= 90 and (ys + eff.y).max() < 150


def test_l_effacement_supprime_bien_le_glyphe():
    """Le résidu — part de la boîte encore en fort contraste avec le fond — doit s'effondrer.
    Sans quoi « effacer » ne veut rien dire."""
    image, avant = _planche()
    zone = _zone()
    x0, y0, x1, y1 = zone.bbox

    def residu(arr):
        boite = arr[y0:y1, x0:x1].astype(float).mean(axis=2)
        return float((np.abs(boite - 235.0) > 45).mean())

    eff = effacement.effacer_zones(image, [zone], [STYLE_UNI], [sfx_lecture.LECTURE_SURE])
    apres = np.asarray(effacement.composer(image, eff))
    assert residu(avant) > 0.30
    assert residu(apres) < 0.02


# ─────────────────────────────────────────────────────────────────────────────
# 3. La diffusion, en propre
# ─────────────────────────────────────────────────────────────────────────────

def test_la_diffusion_reconstruit_un_degrade_la_ou_le_remplissage_echoue():
    """La mesure qui a fait sauter une prémisse du plan de lot : sur un fond dégradé, la
    diffusion raccorde, le remplissage plat pose une marche."""
    degrade = np.tile(np.linspace(40, 250, 320, dtype=np.uint8)[None, :, None], (240, 1, 3))
    troue = degrade.copy()
    troue[110:130, 140:200] = 5
    trou = np.zeros((240, 320), dtype=bool)
    trou[110:130, 140:200] = True

    rempli = effacement.diffuser(troue, trou, passes=64, amorce=(145, 145, 145))
    erreur_diffusion = np.abs(rempli[trou] - degrade[trou]).mean()
    erreur_uniforme = np.abs(145.0 - degrade[trou].astype(float)).mean()
    # Mesuré : 4,8 niveaux de luminance contre 10,8 — un facteur 2,2. Le seuil est posé à 2
    # et non au chiffre exact : ce test verrouille la PROPRIÉTÉ (la diffusion suit le
    # dégradé, le remplissage plat ne le peut pas), pas une décimale de l'implémentation.
    assert erreur_diffusion < erreur_uniforme / 2


def test_la_diffusion_ne_touche_pas_les_pixels_connus():
    arr = np.random.default_rng(22).integers(0, 255, (40, 40, 3)).astype(np.uint8)
    trou = np.zeros((40, 40), dtype=bool)
    trou[10:20, 10:20] = True
    out = effacement.diffuser(arr, trou, passes=8)
    assert np.array_equal(out[~trou], arr[~trou].astype(np.float32))


def test_la_methode_est_reglable_et_auto_rejoue_le_schema_du_plan():
    haut = dict(STYLE_UNI, uniformite_fond=0.80)
    bas = dict(STYLE_UNI, uniformite_fond=0.45)
    assert effacement.decider(haut, sfx_lecture.LECTURE_SURE, {"methode": "auto"})[0] \
        == effacement.MOTIF_UNIFORME
    assert effacement.decider(bas, sfx_lecture.LECTURE_SURE, {"methode": "auto"})[0] \
        == effacement.MOTIF_DIFFUSION
    # Le défaut, lui, diffuse dans les deux cas — c'est la correction mesurée du lot.
    assert effacement.decider(haut, sfx_lecture.LECTURE_SURE)[0] \
        == effacement.MOTIF_DIFFUSION
    assert effacement.decider(haut, sfx_lecture.LECTURE_SURE, {"methode": "uniforme"})[0] \
        == effacement.MOTIF_UNIFORME


def test_le_style_se_lit_en_objet_comme_en_dictionnaire():
    """Le cache porte des dicts, l'éditeur porte des objets. Les deux doivent marcher, sans
    quoi le mode ne s'armerait que sur un tome fraîchement détecté."""
    from manga.clean import analyser_zone_hors_bulle
    image, _ = _planche()
    zone = _zone()
    objet = analyser_zone_hors_bulle(image, zone)
    par_objet = effacement.effacer_zones(image, [zone], [objet],
                                         [sfx_lecture.LECTURE_SURE])
    dico = {"fond": list(objet.fond), "fond_luma": objet.fond_luma,
            "uniformite_fond": objet.uniformite_fond, "ok": objet.ok}
    par_dict = effacement.effacer_zones(image, [zone], [dico], [sfx_lecture.LECTURE_SURE])
    assert par_objet.pixels == par_dict.pixels
    assert np.array_equal(par_objet.rgba, par_dict.rgba)


# ─────────────────────────────────────────────────────────────────────────────
# 4. L'iso-comportement du rendu — critère 6 du plan de lot
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["aucun", "calque"])
def test_la_planche_aplatie_est_identique_au_bit_pres(mode):
    """Un utilisateur qui ne touche à rien — et même un utilisateur qui arme le mode
    « calque » — obtient exactement les pixels d'avant le lot dans `pages_out/`."""
    image, avant = _planche()
    resultat = rendu.rendre_planche(
        image.copy(), [], [], zones_sfx=[_zone()], traductions_sfx=["BROUM"],
        mode_sfx="relettrage", originale=image, styles_sfx=[STYLE_UNI],
        verdicts_sfx=[sfx_lecture.LECTURE_SURE], cfg_effacement={"mode": mode})
    assert np.array_equal(np.asarray(resultat.image), avant)


def test_le_mode_aplati_est_le_seul_qui_change_un_pixel():
    image, avant = _planche()
    resultat = rendu.rendre_planche(
        image.copy(), [], [], zones_sfx=[_zone()], traductions_sfx=["BROUM"],
        mode_sfx="relettrage", originale=image, styles_sfx=[STYLE_UNI],
        verdicts_sfx=[sfx_lecture.LECTURE_SURE], cfg_effacement={"mode": "aplati"})
    assert not np.array_equal(np.asarray(resultat.image), avant)
    assert resultat.effacement is not None and resultat.effacement.rgba is not None
    assert len(resultat.fits_sfx) == 1


def test_le_relettrage_exige_un_effacement():
    """Écrire le français par-dessus un japonais intact donne une bouillie ; le mode le
    refuse plutôt que de la produire."""
    image, _ = _planche()
    resultat = rendu.rendre_planche(
        image.copy(), [], [], zones_sfx=[_zone()], traductions_sfx=["BROUM"],
        mode_sfx="relettrage", originale=image, styles_sfx=[STYLE_UNI],
        verdicts_sfx=[sfx_lecture.LECTURE_SURE], cfg_effacement={"mode": "aucun"})
    assert resultat.fits_sfx == []
    assert resultat.effacement is None


def test_le_relettrage_saute_les_zones_a_lecture_douteuse():
    image, _ = _planche()
    resultat = rendu.rendre_planche(
        image.copy(), [], [], zones_sfx=[_zone()], traductions_sfx=["BROUM"],
        mode_sfx="relettrage", originale=image, styles_sfx=[STYLE_UNI],
        verdicts_sfx=[sfx_lecture.LECTURE_DOUTEUSE], cfg_effacement={"mode": "aplati"})
    assert resultat.fits_sfx == []


def test_le_journal_porte_aussi_les_refus():
    """Un filtre muet est la façon dont on perd les zones suivantes sans le voir — l'acquis
    de L21.1, et il vaut ici. Les décisions de NE PAS peindre sont dans le journal."""
    image, _ = _planche()
    zones = [_zone(), _zone((10, 10, 60, 60)), _zone((240, 160, 310, 230))]
    styles = [STYLE_UNI, dict(STYLE_UNI, uniformite_fond=0.10), None]
    verdicts = [sfx_lecture.LECTURE_SURE] * 3
    eff = effacement.effacer_zones(image, zones, styles, verdicts)
    motifs = eff.motifs()
    assert motifs[effacement.MOTIF_FOND_NON_UNIFORME] == 1
    assert motifs[effacement.MOTIF_MESURE_ABSENTE] == 1
    assert len(eff.decisions) == 3
    assert all(d.index == i for i, d in enumerate(eff.decisions))
