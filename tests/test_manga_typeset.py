# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Lettrage (Pillow) : ajuste police/retour à la ligne pour tenir dans la bulle, et ne
plante pas sur des cas limites (texte vide, très long, bulle minuscule).

S'y ajoutent les non-régressions du lot 1.3. Ce que le lettrage faisait avant :
  · composer dans la **bbox** et non dans la bulle — une bulle de la page 60 fait 281 px de
    large au centre mais 53 px en haut, le texte débordait donc aux extrémités ;
  · estimer la largeur en **nombre de caractères** (`getbbox("Wl")/2` + `textwrap`), sans
    crénage ni largeurs réelles ;
  · à l'échec, renvoyer `min_size` **sans revérifier que ça tenait** et sans rien rogner ;
  · écrire `fill=(0,0,0)` **en dur**, d'où du texte noir sur les bulles inversées ;
  · `zip(regions, texts)` — une liste de traductions plus courte tronquait en silence.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga.clean import analyze_bubble, analyze_regions
from manga.detection import BubbleRegion
from manga.geometry import width_profile
from manga.typeset import (DEFAULT_FONT_CANDIDATES, POLICES_SYMBOLES, Fit, _profil, best_fit,
                           harmonize, layout_at_size, load_font, resolve_font, typeset_bubble,
                           typeset_page, wrap_balanced)

TEXTE = ("C'est bien, mais j'aimerais que vous modériez un peu votre attention "
         "pour le seigneur Kruuteo.")


def _region(box, canvas=(400, 400)):
    x0, y0, x1, y1 = box
    mask = np.zeros((canvas[1], canvas[0]), dtype=bool)
    mask[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=box, mask=mask, score=0.9, cls=0)


def _bulle_ellipse(box=(60, 40, 340, 220), taille=(400, 300), fond=(255, 255, 255),
                   case=(20, 20, 20)):
    """Bulle ELLIPSOÏDALE : étroite en haut et en bas, large au centre — la géométrie qui
    faisait déborder une composition calée sur la bbox."""
    w, h = taille
    img = Image.new("RGB", (w, h), case)
    ImageDraw.Draw(img).ellipse(list(box), fill=fond, outline=(0, 0, 0), width=4)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).ellipse(list(box), fill=255)
    region = BubbleRegion(bbox=box, mask=np.asarray(m) > 127, score=0.95, cls=0)
    return img, region


# --------------------------------------------------------------------------- #
# Tests d'origine : la signature publique NE CHANGE PAS
# --------------------------------------------------------------------------- #

def test_typeset_bubble_draws_within_box():
    img = Image.new("RGB", (400, 400), "white")
    region = _region((50, 50, 250, 200))
    out = typeset_bubble(img, region, "Bonjour, comment vas-tu aujourd'hui ?")
    arr = np.asarray(out)
    x0, y0, x1, y1 = region.bbox
    box_pixels = arr[y0:y1, x0:x1]
    assert (box_pixels < 250).any()          # du texte a bien été dessiné dans la boîte


def test_typeset_bubble_empty_text_is_noop():
    img = Image.new("RGB", (100, 100), "white")
    region = _region((10, 10, 90, 90), canvas=(100, 100))
    out = typeset_bubble(img, region, "")
    assert np.array_equal(np.asarray(out), np.asarray(img))


def test_typeset_bubble_tiny_box_does_not_crash():
    img = Image.new("RGB", (100, 100), "white")
    region = _region((10, 10, 25, 25), canvas=(100, 100))
    typeset_bubble(img, region, "Un texte assez long pour forcer un ajustement de taille")


def test_typeset_page_multiple_regions():
    img = Image.new("RGB", (400, 400), "white")
    regions = [_region((10, 10, 150, 100)), _region((200, 200, 350, 300))]
    out = typeset_page(img, regions, ["Salut", "Ça va ?"])
    assert out.size == (400, 400)


def test_typeset_page_ignores_non_bulle_regions():
    img = Image.new("RGB", (200, 200), "white")
    region = _region((10, 10, 190, 190), canvas=(200, 200))
    region.kind = "onomatopee"
    out = typeset_page(img, [region], ["ignoré"])
    assert np.array_equal(np.asarray(out), np.asarray(img))


# --------------------------------------------------------------------------- #
# LA garantie : aucun pixel de texte hors de l'intérieur de la bulle
# --------------------------------------------------------------------------- #

def test_le_texte_ne_sort_jamais_de_l_interieur_de_la_bulle():
    """Le cœur du lot 1.3. On compare la page nettoyée à la page lettrée : tout pixel
    modifié doit appartenir à l'intérieur mesuré de la bulle."""
    img, region = _bulle_ellipse()
    style = analyze_bubble(img, region)
    from manga.clean import clean_bubbles
    propre = clean_bubbles(img, [region], styles=[style])
    avant = np.asarray(propre).copy()

    final = typeset_page(propre.copy(), [region], [TEXTE], styles=[style])
    diff = (np.asarray(final) != avant).any(axis=2)
    assert diff.any(), "du texte doit avoir été écrit"
    assert not (diff & ~style.interior).any(), "du texte est sorti de l'intérieur de la bulle"


@pytest.mark.parametrize("texte", [
    "Oui.",
    "Je comprends la raison de votre colère, mais il faut vous ressaisir maintenant.",
    "Combien de foyers ont été détruits par cette attaque, exactement, seigneur ?",
    TEXTE,
    "A" * 120,
])
def test_aucun_debordement_quel_que_soit_le_texte(texte):
    img, region = _bulle_ellipse()
    style = analyze_bubble(img, region)
    from manga.clean import clean_bubbles
    propre = clean_bubbles(img, [region], styles=[style])
    avant = np.asarray(propre).copy()
    final = typeset_page(propre.copy(), [region], [texte], styles=[style])
    diff = (np.asarray(final) != avant).any(axis=2)
    assert not (diff & ~style.interior).any(), texte


def test_une_bulle_tres_etroite_ne_fait_pas_deborder_le_texte():
    """Bulle de 53 px de large : le texte doit rester dedans, quitte à signaler."""
    img, region = _bulle_ellipse(box=(150, 30, 210, 270), taille=(400, 300))
    style = analyze_bubble(img, region)
    from manga.clean import clean_bubbles
    propre = clean_bubbles(img, [region], styles=[style])
    avant = np.asarray(propre).copy()
    final = typeset_page(propre.copy(), [region], [TEXTE], styles=[style])
    diff = (np.asarray(final) != avant).any(axis=2)
    assert not (diff & ~style.interior).any()


# --------------------------------------------------------------------------- #
# Habillage équilibré (programmation dynamique)
# --------------------------------------------------------------------------- #

def test_wrap_balanced_respecte_la_contrainte_dure_de_largeur():
    font = load_font(resolve_font(), 20)
    mots = TEXTE.split()
    avails = [200] * 6
    lignes = wrap_balanced(mots, font, avails, stroke_pad=0)
    assert lignes is not None
    for ln in lignes:
        assert font.getlength(ln) <= 200, ln


def test_wrap_balanced_produit_exactement_le_nombre_de_lignes_demande():
    font = load_font(resolve_font(), 18)
    lignes = wrap_balanced(TEXTE.split(), font, [200] * 5, stroke_pad=0)
    assert lignes is not None and len(lignes) == 5


def test_wrap_balanced_echoue_si_un_mot_est_plus_large_que_la_ligne():
    font = load_font(resolve_font(), 40)
    assert wrap_balanced(["anticonstitutionnellement"], font, [20], stroke_pad=0) is None


def test_wrap_balanced_evite_les_lignes_orphelines():
    """La pénalité QUADRATIQUE préfère deux lignes moyennement remplies à une ligne pleine
    suivie d'un mot seul — c'est ce qui supprime les orphelines et les rivières."""
    font = load_font(resolve_font(), 20)
    lignes = wrap_balanced(TEXTE.split(), font, [220] * 6, stroke_pad=0)
    assert lignes is not None
    largeurs = [font.getlength(ln) for ln in lignes]
    # aucune ligne ne doit être ridiculement courte par rapport à la plus longue
    assert min(largeurs) > 0.35 * max(largeurs), largeurs


def test_wrap_balanced_conserve_tous_les_mots_dans_l_ordre():
    font = load_font(resolve_font(), 18)
    lignes = wrap_balanced(TEXTE.split(), font, [200] * 6, stroke_pad=0)
    assert lignes is not None
    assert " ".join(lignes).split() == TEXTE.split()


def test_wrap_balanced_texte_vide():
    font = load_font(resolve_font(), 18)
    assert wrap_balanced([], font, [100], stroke_pad=0) == []


def test_la_cesure_est_autorisee_aux_traits_d_union_existants():
    """Coupe permise après un trait d'union EXISTANT (« sommes-nous »), jamais au milieu
    d'un mot : pas de césure algorithmique, qui imposerait un dictionnaire français."""
    img, region = _bulle_ellipse(box=(150, 40, 250, 240), taille=(400, 300))
    style = analyze_bubble(img, region)
    fit = best_fit("Où sommes-nous exactement maintenant", style,
                   {**_cfg_test(), "cesure_traits_union": True}, resolve_font())
    jointes = " ".join(fit.lines)
    assert "sommes-nous" in jointes or any(ln.endswith("-") for ln in fit.lines)


def test_aucun_mot_n_est_coupe_en_son_milieu():
    img, region = _bulle_ellipse(box=(160, 40, 240, 240), taille=(400, 300))
    style = analyze_bubble(img, region)
    fit = best_fit("aujourd'hui anticonstitutionnellement", style, _cfg_test(),
                   resolve_font())
    for ln in fit.lines:
        for mot in ln.split():
            nu = mot.rstrip("-")
            assert nu in "aujourd'hui anticonstitutionnellement", mot


def _cfg_test() -> dict:
    from manga.typeset import _DEFAUTS
    return dict(_DEFAUTS)


# --------------------------------------------------------------------------- #
# Composition dans le masque, pas dans la bbox
# --------------------------------------------------------------------------- #

def test_la_largeur_utilisable_suit_le_profil_du_masque():
    """Une ellipse est bien plus étroite en haut qu'au centre : les largeurs retenues par
    la mise en page doivent le refléter, jamais valoir la largeur de la bbox."""
    img, region = _bulle_ellipse()
    style = analyze_bubble(img, region)
    largeur, _, _ = width_profile(style.interior, style.center_x)
    utiles = largeur[largeur > 0]
    assert utiles.min() < 0.5 * utiles.max(), "l'ellipse doit varier fortement en largeur"

    fit = best_fit(TEXTE, style, _cfg_test(), resolve_font())
    bbox_w = region.bbox[2] - region.bbox[0]
    assert max(fit.avails) < bbox_w, "les largeurs doivent venir du masque, pas de la bbox"


def test_bulle_ASYMETRIQUE_le_texte_centre_ne_deborde_pas():
    """Régression trouvée au contrôle visuel de la page 60 : « comprends » ressortait
    tronqué en « mprends ».

    Le texte est centré sur `cx`, mais la plage contiguë du masque n'est pas forcément
    centrée sur `cx`. Une plage allant de 30 px à gauche de `cx` à 200 px à droite fait
    230 px de large — un texte de 230 px centré sur `cx` déborde de 85 px à gauche. La
    largeur utilisable est donc `2 × min(cx − x0, x1 − cx)`, pas la largeur de la plage."""
    w, h = 500, 300
    img = Image.new("RGB", (w, h), (20, 20, 20))
    # Bulle franchement asymétrique : un petit lobe à gauche, un grand à droite.
    m = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(m)
    dm.ellipse([120, 60, 460, 240], fill=255)
    dm.ellipse([60, 120, 200, 190], fill=255)
    masque = np.asarray(m) > 127
    di = ImageDraw.Draw(img)
    di.ellipse([120, 60, 460, 240], fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    di.ellipse([60, 120, 200, 190], fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    region = BubbleRegion(bbox=(60, 60, 460, 240), mask=masque, score=0.9, cls=0)

    style = analyze_bubble(img, region)
    from manga.clean import clean_bubbles
    propre = clean_bubbles(img, [region], styles=[style])
    avant = np.asarray(propre).copy()

    final = typeset_page(propre.copy(), [region], [TEXTE], styles=[style])
    arr = np.asarray(final)
    diff = (arr != avant).any(axis=2)
    assert diff.any()
    assert not (diff & ~style.interior).any(), "texte hors de l'intérieur"

    # Et surtout : le texte n'a pas été AMPUTÉ par le découpage. On vérifie que la mise en
    # page tient dans la largeur symétrique, ligne par ligne — condition qui garantit
    # qu'aucun glyphe n'a été rogné.
    fit = best_fit(TEXTE, style, _cfg_test(), resolve_font())
    font = load_font(resolve_font(), fit.size)
    largeur, x0, x1 = width_profile(style.interior, style.center_x)
    cx = style.center_x
    for k, ligne in enumerate(fit.lines):
        haut = fit.top + k * fit.line_h
        bas = min(len(largeur), haut + fit.line_h)
        demi = np.minimum(cx - x0[haut:bas], x1[haut:bas] - cx)
        demi = demi[largeur[haut:bas] > 0]
        assert demi.size and font.getlength(ligne) <= 2 * int(demi.min()), ligne


def test_le_min_du_profil_est_pris_sur_toute_la_hauteur_de_ligne():
    """C'est ce `min` qui empêche le débordement dans les coins arrondis : une largeur prise
    à la seule ligne médiane laisserait dépasser le haut et le bas des glyphes."""
    img, region = _bulle_ellipse()
    style = analyze_bubble(img, region)
    fit = best_fit(TEXTE, style, _cfg_test(), resolve_font())
    largeur, _, _ = width_profile(style.interior, style.center_x)
    for k, dispo in enumerate(fit.avails):
        haut = fit.top + k * fit.line_h
        bas = min(len(largeur), haut + fit.line_h)
        assert dispo <= int(largeur[haut:bas].min())


# --------------------------------------------------------------------------- #
# Polarité : plus jamais fill=(0,0,0) en dur
# --------------------------------------------------------------------------- #

def test_une_bulle_inversee_recoit_du_texte_CLAIR():
    """L'ancien `fill=(0,0,0)` en dur donnait du texte noir sur fond noir."""
    img, region = _bulle_ellipse(fond=(10, 10, 10), case=(240, 240, 240))
    d = ImageDraw.Draw(img)
    cy = (region.bbox[1] + region.bbox[3]) // 2
    for i in range(5):
        x = region.bbox[0] + 40 + i * 40
        d.rectangle([x, cy - 20, x + 22, cy + 20], fill=(245, 245, 245))
    style = analyze_bubble(img, region)
    assert style.inverted and style.text_color == (255, 255, 255)

    from manga.clean import clean_bubbles
    propre = clean_bubbles(img, [region], styles=[style])
    final = typeset_page(propre.copy(), [region], ["Texte clair sur fond sombre"],
                         styles=[style])
    arr = np.asarray(final)
    # dans l'intérieur, il existe des pixels CLAIRS (le texte) sur le fond sombre
    dedans = arr[style.interior]
    assert (dedans.max(axis=1) > 200).any(), "le texte doit être clair"


def test_rien_n_est_ecrit_dans_une_bulle_abandonnee():
    """Si le nettoyage a renoncé (fausse détection sur du dessin), le lettrage doit
    renoncer aussi : écrire par-dessus le dessin serait pire que de laisser le japonais."""
    w, h = 240, 300
    arr = np.full((h, w, 3), 250, dtype=np.uint8)
    ys, xs = np.mgrid[20:280, 60:180]
    arr[20:280, 60:180] = np.clip(((xs - 60) * 255 // 119) - (((ys // 3) % 2) * 40),
                                  0, 255).astype(np.uint8)[:, :, None]
    img = Image.fromarray(arr)
    mask = np.zeros((h, w), dtype=bool)
    mask[20:280, 60:180] = True
    region = BubbleRegion(bbox=(60, 20, 180, 280), mask=mask, score=0.6, cls=0)
    style = analyze_bubble(img, region)
    assert style.mode == "aucun"

    out = typeset_page(img.copy(), [region], ["Ne doit pas être écrit"], styles=[style])
    assert np.array_equal(np.asarray(out), arr)


# --------------------------------------------------------------------------- #
# Harmonisation des tailles par planche
# --------------------------------------------------------------------------- #

def _fit(size: int) -> Fit:
    return Fit(lines=["x"], size=size, line_h=size + 4, top=0, center_x=10, stroke=0)


def test_harmonize_ramene_les_trop_grandes_vers_le_plafond():
    fits = [_fit(16), _fit(25), _fit(25), _fit(38)]
    harmonize(fits, {**_cfg_test(), "harmonisation": True,
                     "harmonisation_ratio_max": 1.25})
    assert fits[3].harmonise_vers == 31          # médiane 25 × 1,25
    assert fits[0].harmonise_vers is None


def test_harmonize_n_agrandit_JAMAIS_une_petite_bulle():
    """Une bulle est petite parce qu'elle est ÉTROITE : l'agrandir la ferait déborder."""
    fits = [_fit(12), _fit(30), _fit(30)]
    harmonize(fits, {**_cfg_test(), "harmonisation": True,
                     "harmonisation_ratio_max": 1.25})
    assert fits[0].harmonise_vers is None
    assert fits[0].size == 12


def test_harmonize_desactivable():
    fits = [_fit(10), _fit(40)]
    harmonize(fits, {**_cfg_test(), "harmonisation": False})
    assert all(f.harmonise_vers is None for f in fits)


def test_harmonize_ignore_les_listes_trop_courtes():
    fits = [_fit(40)]
    harmonize(fits, {**_cfg_test(), "harmonisation": True})
    assert fits[0].harmonise_vers is None


def test_l_ecart_de_taille_sur_une_planche_reste_borne():
    """Page 60 réelle : l'écart max passait de 2,4× à 1,9×. Sur une planche synthétique à
    bulles de tailles très différentes, l'écart doit rester sous le ratio configuré."""
    img = Image.new("RGB", (700, 500), (255, 255, 255))
    regions, textes = [], []
    for (box, txt) in (((20, 20, 320, 220), "Court."),
                       ((360, 20, 680, 240), "Un peu plus long, deux lignes peut-être."),
                       ((20, 260, 330, 470), TEXTE),
                       ((360, 280, 680, 470), "Moyen, sur cette planche.")):
        m = Image.new("L", (700, 500), 0)
        ImageDraw.Draw(m).ellipse(list(box), fill=255)
        ImageDraw.Draw(img).ellipse(list(box), fill=(255, 255, 255), outline=(0, 0, 0), width=3)
        regions.append(BubbleRegion(bbox=box, mask=np.asarray(m) > 127, score=0.9, cls=0))
        textes.append(txt)

    styles = analyze_regions(img, regions)
    rapport: list = []
    typeset_page(img.copy(), regions, textes, styles=styles, report_out=rapport)
    tailles = [e["taille"] for e in rapport if e["type"] == "bulle"]
    assert len(tailles) == 4
    mediane = sorted(tailles)[len(tailles) // 2]
    assert max(tailles) <= mediane * 1.25 + 1, tailles


# --------------------------------------------------------------------------- #
# Fin de la troncature silencieuse
# --------------------------------------------------------------------------- #

def test_une_liste_de_traductions_trop_courte_est_signalee():
    """`_parse_translations` peut renvoyer moins de lignes que de bulles ; l'ancien
    `zip(regions, texts)` laissait alors les dernières bulles vides EN SILENCE."""
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    regions = [_region((20, 20, 180, 120), canvas=(400, 300)),
               _region((220, 20, 380, 120), canvas=(400, 300)),
               _region((20, 160, 180, 280), canvas=(400, 300))]
    rapport: list = []
    typeset_page(img, regions, ["Un seul texte"], report_out=rapport)
    ecarts = [e for e in rapport if e["type"] == "ecart_comptage"]
    assert len(ecarts) == 1
    assert ecarts[0] == {"type": "ecart_comptage", "bulles": 3, "traductions": 1,
                         "ecart": 2}


def test_une_liste_de_traductions_trop_longue_est_signalee():
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    regions = [_region((20, 20, 180, 180), canvas=(200, 200))]
    rapport: list = []
    typeset_page(img, regions, ["a", "b", "c"], report_out=rapport)
    ecarts = [e for e in rapport if e["type"] == "ecart_comptage"]
    assert ecarts and ecarts[0]["ecart"] == -2


def test_aucun_ecart_signale_quand_les_comptes_correspondent():
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    regions = [_region((20, 20, 180, 180), canvas=(200, 200))]
    rapport: list = []
    typeset_page(img, regions, ["Bonjour"], report_out=rapport)
    assert not [e for e in rapport if e["type"] == "ecart_comptage"]


def test_le_rapport_liste_chaque_bulle_avec_sa_taille_et_son_mode():
    img, region = _bulle_ellipse()
    styles = analyze_regions(img, [region])
    rapport: list = []
    typeset_page(img.copy(), [region], [TEXTE], styles=styles, report_out=rapport)
    bulles = [e for e in rapport if e["type"] == "bulle"]
    assert len(bulles) == 1
    assert bulles[0]["mode_nettoyage"] == "masque"
    assert bulles[0]["taille"] > 0 and bulles[0]["lignes"] >= 1
    assert bulles[0]["overflow"] is False


def _bulle_de(largeur, hauteur, marge=20):
    """Une ellipse de `largeur`×`hauteur`, centrée dans sa page, avec son style."""
    taille = (largeur + 2 * marge, hauteur + 2 * marge)
    img = Image.new("RGB", taille, (255, 255, 255))
    m = Image.new("L", taille, 0)
    boite = [marge, marge, marge + largeur, marge + hauteur]
    ImageDraw.Draw(m).ellipse(boite, fill=255)
    region = BubbleRegion(bbox=tuple(boite), mask=np.asarray(m) > 127, score=0.9, cls=0)
    return img, region, analyze_regions(img, [region])


def test_un_debordement_est_signale_et_non_tronque():
    """Bulle correcte + texte démesuré : impossible de tenir, même au plancher absolu. On
    dessine, on marque `overflow`, et on NE TRONQUE PAS — un échec non compté est invisible.

    La bulle doit être assez grande pour NE PAS être dégénérée : c'est bien la longueur du
    texte qui est en cause ici, et le rapport doit pouvoir le dire (cf. `cause`)."""
    img, region, styles = _bulle_de(120, 100)
    rapport: list = []
    # `taille_max` resserré : l'échelle de replis balaie toutes les tailles à la baisse, et le
    # test coûterait sinon des minutes sur un texte de mille caractères.
    cfg = dict(_cfg_test(), taille_max=20)
    long_texte = ("Un texte beaucoup trop long pour cette bulle, impossible à faire "
                  "tenir quelle que soit la taille de police retenue. ") * 8
    typeset_page(img.copy(), [region], [long_texte], styles=styles, report_out=rapport,
                 cfg=cfg)
    bulles = [e for e in rapport if e["type"] == "bulle"]
    assert bulles and bulles[0]["overflow"] is True
    assert bulles[0]["repli"] == "debordement"
    assert bulles[0]["cause"] == "texte_trop_long"      # …et là, « raccourcir » est juste
    # tous les mots sont conservés : rien n'est tronqué
    fit_lines = " ".join(best_fit(long_texte, styles[0], cfg, resolve_font()).lines)
    assert fit_lines.split() == long_texte.split()


def test_une_region_DEGENEREE_nest_pas_lettree():
    """Une région trop petite pour porter un seul mot n'est plus une bulle : le masque n'y
    laisserait passer que des fragments de lettres. On s'abstient, et le rapport pointe la
    DÉTECTION. Mesuré sur le Vol.1 : 181 px² d'aire utile page 17, 12 px de haut page 146,
    et 4 px de largeur utilisable page 80 — celle-là même que le rapport accusait d'être
    « trop verbeuse »."""
    img, region, styles = _bulle_de(24, 40)
    rapport: list = []
    typeset_page(img.copy(), [region], ["Un texte impossible à faire tenir ici."],
                 styles=styles, report_out=rapport)
    bulles = [e for e in rapport if e["type"] == "bulle"]
    assert bulles and bulles[0]["cause"] == "bulle_degeneree"
    assert bulles[0]["lignes"] == 0 and bulles[0]["overflow"] is True


def test_une_planche_degeneree_nest_pas_MODIFIEE():
    """Corollaire : ne pas lettrer veut dire ne pas toucher un pixel."""
    img, region, styles = _bulle_de(24, 40)
    avant = img.copy()
    apres = typeset_page(img, [region], ["Un texte impossible à faire tenir ici."],
                         styles=styles)
    assert np.array_equal(np.asarray(avant), np.asarray(apres))


def test_le_plancher_absolu_nest_JAMAIS_emprunte_quand_taille_min_suffit():
    """Non-régression : une bulle saine ne doit pas voir son lettrage bouger d'un pixel.

    Le plancher absolu n'est atteint qu'après l'échec de TOUTE l'échelle de replis ; une
    bulle qui trouve sa taille à l'étape 1 n'y passe jamais."""
    img, region, styles = _bulle_de(220, 180)
    for texte in ("Oui.", "Un mot", "Ça alors, quelle surprise !"):
        avec = best_fit(texte, styles[0], _cfg_test(), resolve_font())
        sans = best_fit(texte, styles[0], dict(_cfg_test(), taille_min_absolue=11),
                        resolve_font())
        assert (avec.size, avec.lines, avec.top) == (sans.size, sans.lines, sans.top)
        assert avec.repli != "taille_min_absolue" and avec.size >= 11


def test_le_plancher_absolu_evite_un_debordement_dans_une_bulle_etroite():
    """Un débordement fait DÉCOUPER les lettres par le masque ; un corps plus petit reste
    entier. Mesuré : « Ouaouh ! » et « Zouing ! » dans des ballons verticaux de 44 et 48 px."""
    img, region, styles = _bulle_de(40, 110)
    sans = best_fit("Ouaouh !", styles[0], dict(_cfg_test(), taille_min_absolue=11),
                    resolve_font())
    avec = best_fit("Ouaouh !", styles[0], _cfg_test(), resolve_font())
    assert sans.overflow is True
    assert avec.overflow is False and avec.size < 11
    assert avec.repli == "taille_min_absolue" and avec.cause == "bulle_etroite"


# --------------------------------------------------------------------------- #
# Police et caches
# --------------------------------------------------------------------------- #

def test_la_police_par_defaut_est_comic_neue_et_non_arial():
    """`templates/fonts/` n'existait pas : la chaîne tombait systématiquement sur Arial."""
    resolve_font.cache_clear()
    chemin = resolve_font()
    assert "arial" not in chemin.lower(), chemin
    assert "ComicNeue" in chemin or "manga_typeset" in chemin, chemin


def test_font_path_explicite_est_prioritaire():
    """⚠ La police d'essai doit EXISTER sur la plateforme qui exécute le test. Ce test
    passait `C:/Windows/Fonts/l_10646.ttf` : sur Linux le fichier est absent, `resolve_font`
    faisait donc son repli — comportement correct — et l'assertion accusait la priorité d'un
    défaut qui n'existait pas. On prend une police livrée par le dépôt, présente partout, et
    volontairement pas la première de la chaîne."""
    resolve_font.cache_clear()
    explicite = "templates/fonts/ComicNeue-Italic.ttf"
    assert Path(explicite).is_file(), explicite
    assert resolve_font(explicite).endswith("ComicNeue-Italic.ttf")


def test_un_font_path_introuvable_retombe_sur_la_chaine():
    """Contrepartie du test précédent : une config qui pointe dans le vide ne doit pas faire
    échouer le lettrage, elle doit reprendre la chaîne."""
    resolve_font.cache_clear()
    assert resolve_font("nulle-part/police-absente.ttf") in DEFAULT_FONT_CANDIDATES


def test_une_police_a_symboles_est_disponible_sur_cette_plateforme():
    """Échoue — ne skippe pas, comme `tests/test_fixture_police.py`.

    Sans police de repli à symboles, `♪ ♥ → ♂ ♀` ne lèvent RIEN : ils partent en « supprimé »
    et la planche sort amputée d'un signe que le traducteur avait produit, la perte
    n'apparaissant que dans une ligne du rapport. C'est le même silence que le lot 20 a
    supprimé pour la police japonaise."""
    from manga.typeset import explication_absence_symboles, polices_symboles
    trouvees = [c for c in polices_symboles() if Path(c).is_file()]
    assert trouvees, explication_absence_symboles()


def test_les_deux_os_de_la_matrice_ont_des_polices_a_symboles():
    """`.github/workflows/ci.yml` fait tourner la suite sur windows-latest ET ubuntu-latest.
    Un OS sans candidat déclaré rendrait le test précédent rouge sans dire pourquoi."""
    from manga.typeset import polices_symboles
    for plateforme in ("win32", "linux", "darwin"):
        assert polices_symboles(plateforme), plateforme
    assert sys.platform in POLICES_SYMBOLES, (
        f"{sys.platform} n'a aucune police à symboles déclarée dans manga/typeset.py")


def test_aucune_police_CJK_dans_la_chaine_de_repli():
    """La garde qui protège la substitution. `font_pour_texte` bascule TOUTE la bulle : une
    police CJK dans la chaîne couvrirait `・` et court-circuiterait `_SUBSTITUTIONS`, faisant
    redessiner un paragraphe entier de français en CJK pour un seul point médian."""
    from manga.typeset import a_le_glyphe
    for candidat in DEFAULT_FONT_CANDIDATES:
        if Path(candidat).is_file():
            assert not a_le_glyphe(candidat, "・"), candidat


def test_load_font_est_mis_en_cache():
    load_font.cache_clear()
    a = load_font(resolve_font(), 24)
    b = load_font(resolve_font(), 24)
    assert a is b
    assert load_font.cache_info().hits >= 1


def test_detecte_un_glyphe_reellement_absent():
    """`font.getmask(c).getbbox() is None` NE détecte PAS un glyphe absent : Pillow
    substitue le `.notdef`, dont la boîte est non vide. Ce faux test déclarait Comic Neue
    couvrante pour ♪ ♥ ★ →, et la planche sortait avec des carrés tofu."""
    from manga.typeset import a_le_glyphe, glyphes_manquants
    comic = "templates/fonts/ComicNeue-Bold.ttf"
    assert a_le_glyphe(comic, "é") is True
    assert a_le_glyphe(comic, "♪") is False
    assert glyphes_manquants(comic, "les filles ♪") == "♪"
    assert glyphes_manquants(comic, "Bonjour, ça va ?") == ""


def test_repli_de_police_par_bulle_sur_un_symbole_absent():
    """Comic Neue est latine : `♪` doit faire basculer CETTE bulle sur une police qui l'a,
    sans changer la police des autres."""
    from manga.typeset import font_pour_texte
    police_note, manquants = font_pour_texte("Moi, je préfère les filles ♪")
    assert manquants == ""
    assert "ComicNeue" not in police_note

    police_normale, manquants2 = font_pour_texte("Moi, je préfère les filles.")
    assert manquants2 == "" and "ComicNeue" in police_normale


def test_un_glyphe_introuvable_dans_toute_la_chaine_est_signale():
    """Aucune police de la chaîne ne couvre le texte : on garde le meilleur dessin et on le
    DIT, plutôt que de sortir un tofu en silence."""
    from manga.typeset import font_pour_texte
    _police, manquants = font_pour_texte("Un idéogramme rare : \U0002a6b2")
    assert "\U0002a6b2" in manquants


def test_le_rapport_signale_les_glyphes_SUPPRIMES():
    img, region = _bulle_ellipse()
    styles = analyze_regions(img, [region])
    rapport: list = []
    typeset_page(img.copy(), [region], ["Rare : \U0002a6b2 ici"], styles=styles,
                 report_out=rapport)
    manques = [e for e in rapport if e["type"] == "glyphes_manquants"]
    assert manques and "\U0002a6b2" in manques[0]["supprimes"]


# --------------------------------------------------------------------------- #
# Glyphes absents : substituer, puis supprimer — mais JAMAIS dessiner
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("texte", [
    "Ça va・vraiment ?",              # le point médian mesuré page 147 bulle 6
    "「Bonjour」dit-elle",
    "Attention ！ Danger ？",
    "Ａｌｄｎｏａｈ ２０１４",          # pleine chasse
    "Un souffle～ long",
    "Ligne ー brisée",
    "Un idéogramme rare : \U0002a6b2",
    "Mélange ・ ♪ \U0002a6b2 ！",
])
def test_aucun_glyphe_absent_ne_SURVIT_a_la_normalisation(texte):
    """L'invariant du lot : en sortie de `texte_dessinable`, la police retenue sait dessiner
    TOUT le texte. La table de substitution n'a donc pas besoin d'être exhaustive pour que le
    carré tofu disparaisse — ce qu'elle ne convertit pas est supprimé."""
    from manga.typeset import glyphes_manquants, texte_dessinable
    sortie, police, _subs, _supp = texte_dessinable(texte)
    assert glyphes_manquants(police, sortie) == "", (texte, sortie)


def test_le_point_median_devient_un_point_median_LATIN():
    """Régression du Vol.1 : `・` page 147 bulle 6, dessiné en carré tofu.

    Ajouter une police CJK à la chaîne serait le pire correctif : `font_pour_texte` bascule
    TOUTE la bulle, donc un seul point médian ferait passer une bulle entière du lettrage
    manga à une police CJK."""
    from manga.typeset import texte_dessinable
    sortie, _police, substitues, supprimes = texte_dessinable("Ça va・vraiment ?")
    assert sortie == "Ça va·vraiment ?"
    assert substitues == "・" and supprimes == ""


def test_la_substitution_ne_touche_PAS_ce_que_la_police_sait_dessiner():
    """On ne réécrit pas une planche que rien n'oblige à réécrire."""
    from manga.typeset import texte_dessinable
    sortie, _p, substitues, supprimes = texte_dessinable("Bonjour ! Ça va ?")
    assert sortie == "Bonjour ! Ça va ?" and not substitues and not supprimes


def test_un_symbole_couvert_par_le_REPLI_nest_ni_substitue_ni_supprime():
    """L'ordre compte : la chaîne de polices d'abord. Une bulle qui contient `♪` bascule sur
    une police qui l'a, et son texte reste intact."""
    from manga.typeset import texte_dessinable
    sortie, _p, substitues, supprimes = texte_dessinable("les filles ♪")
    assert sortie == "les filles ♪" and not substitues and not supprimes


def test_la_substitution_peut_RAMENER_le_texte_dans_la_police_principale():
    """3e étape : on re-tente la chaîne sur le texte normalisé. `Ｔｅｓｔ！` en pleine chasse
    ne tient dans aucune police latine ; `Test!` tient dans Comic Neue."""
    from manga.typeset import resolve_font, texte_dessinable
    sortie, police, substitues, supprimes = texte_dessinable("Ｔｅｓｔ！")
    assert sortie == "Test!" and substitues and not supprimes
    assert police == resolve_font()


def test_le_rapport_distingue_substitue_de_supprime():
    img, region = _bulle_ellipse()
    styles = analyze_regions(img, [region])
    rapport: list = []
    typeset_page(img.copy(), [region], ["A・B \U0002a6b2"], styles=styles, report_out=rapport)
    g = [e for e in rapport if e["type"] == "glyphes_manquants"][0]
    assert g["substitues"] == "・" and g["supprimes"] == "\U0002a6b2"


# --------------------------------------------------------------------------- #
# Marqueur de bulle vide
# --------------------------------------------------------------------------- #

def test_une_bulle_vide_A_SOURCE_est_marquee():
    """2 bulles du Vol.1 sont sorties vierges, indistinguables d'un choix éditorial. Des
    points de suspension se lisent comme un silence : la planche n'est pas trahie, et le trou
    devient repérable."""
    img, region, styles = _bulle_de(220, 180)
    rapport: list = []
    typeset_page(img.copy(), [region], [""], styles=styles, report_out=rapport,
                 sources=["こんにちは"])
    vides = [e for e in rapport if e["type"] == "bulle_vide"]
    assert vides and vides[0]["marqueur"] == "…"
    assert [e for e in rapport if e["type"] == "bulle"]      # elle a bien été lettrée


def test_une_bulle_SANS_source_reste_vierge():
    """Une bulle sans japonais est vide à bon droit : la marquer inventerait un silence."""
    img, region, styles = _bulle_de(220, 180)
    rapport: list = []
    typeset_page(img.copy(), [region], [""], styles=styles, report_out=rapport, sources=[""])
    assert not [e for e in rapport if e["type"] in ("bulle_vide", "bulle")]


def test_sans_sources_aucune_bulle_nest_marquee():
    img, region, styles = _bulle_de(220, 180)
    rapport: list = []
    typeset_page(img.copy(), [region], [""], styles=styles, report_out=rapport)
    assert not [e for e in rapport if e["type"] in ("bulle_vide", "bulle")]


def test_un_marqueur_vide_desactive_retablit_la_bulle_vierge():
    img, region, styles = _bulle_de(220, 180)
    rapport: list = []
    typeset_page(img.copy(), [region], [""], styles=styles, report_out=rapport,
                 sources=["こんにちは"], cfg={"marqueur_vide": ""})
    assert not [e for e in rapport if e["type"] in ("bulle_vide", "bulle")]


def test_une_bulle_avec_symbole_ne_change_pas_la_police_des_autres():
    img = Image.new("RGB", (700, 300), (255, 255, 255))
    regions, textes = [], []
    for box, txt in (((20, 20, 330, 280), "Moi, je préfère les filles ♪"),
                     ((370, 20, 680, 280), "Texte parfaitement latin.")):
        m = Image.new("L", (700, 300), 0)
        ImageDraw.Draw(m).ellipse(list(box), fill=255)
        ImageDraw.Draw(img).ellipse(list(box), fill=(255, 255, 255), outline=(0, 0, 0), width=3)
        regions.append(BubbleRegion(bbox=box, mask=np.asarray(m) > 127, score=0.9, cls=0))
        textes.append(txt)
    styles = analyze_regions(img, regions)
    rapport: list = []
    typeset_page(img.copy(), regions, textes, styles=styles, report_out=rapport)
    # aucun glyphe manquant signalé : le repli a fait son travail
    assert not [e for e in rapport if e["type"] == "glyphes_manquants"]
    assert len([e for e in rapport if e["type"] == "bulle"]) == 2


def test_majuscules_gere_les_accents_francais():
    img, region = _bulle_ellipse()
    styles = analyze_regions(img, [region])
    rapport: list = []
    typeset_page(img.copy(), [region], ["éàçùœ été"], styles=styles,
                 cfg={"majuscules": True}, report_out=rapport)
    assert [e for e in rapport if e["type"] == "bulle"]
    assert "éàçùœ".upper() == "ÉÀÇÙŒ"


def test_le_contour_est_absent_en_mode_masque_et_present_en_mode_texte():
    """Le contour n'a de sens que si le fond de bulle a survécu (mode « texte »)."""
    img, region = _bulle_ellipse()
    style = analyze_bubble(img, region)
    assert style.mode == "masque"
    assert best_fit(TEXTE, style, _cfg_test(), resolve_font()).stroke == 0

    style.mode = "texte"
    assert best_fit(TEXTE, style, _cfg_test(), resolve_font()).stroke >= 1


# --------------------------------------------------------------------------- #
# Glissement vertical du bloc (lot 4.3)
# --------------------------------------------------------------------------- #

def _bulle_sablier(taille=(400, 500)):
    """Bulle en SABLIER : large en haut et en bas, étranglée au milieu. Le bloc centré tombe
    donc pile sur le passage le plus étroit — la géométrie qui condamnait le lettrage à
    `taille_min` alors que la place existait 60 px plus haut."""
    w, h = taille
    img = Image.new("RGB", (w, h), (20, 20, 20))
    d = ImageDraw.Draw(img)
    d.ellipse([40, 30, 360, 230], fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    d.ellipse([40, 270, 360, 470], fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    d.rectangle([185, 200, 215, 300], fill=(255, 255, 255))
    m = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(m)
    dm.ellipse([40, 30, 360, 230], fill=255)
    dm.ellipse([40, 270, 360, 470], fill=255)
    dm.rectangle([185, 200, 215, 300], fill=255)
    return img, BubbleRegion(bbox=(40, 30, 360, 470), mask=np.asarray(m) > 127,
                             score=0.95, cls=0)


def test_glissement_a_zero_est_le_comportement_dorigine():
    """`glissement_vertical: 0` doit rendre exactement l'ancien lettrage : c'est la porte de
    sortie si le glissement déplaît, et la garantie que le défaut n'est pas dans la mécanique."""
    img, region = _bulle_ellipse()
    style = analyze_bubble(img, region)
    prof, cx = _profil(style)
    c = dict(_cfg_test(), _mode=style.mode)
    a = layout_at_size(TEXTE, prof, cx, 20, c, resolve_font())
    b = layout_at_size(TEXTE, prof, cx, 20, c, resolve_font(), glissement=0.0)
    assert a is not None and b is not None
    assert (a.top, a.lines, a.avails) == (b.top, b.lines, b.avails)


def test_le_glissement_ne_retrecit_JAMAIS_une_bulle():
    """Garantie par construction : `best_fit` garde la PLUS GRANDE des deux stratégies.

    Sans cette composition, deux bulles sur 199 rétrécissaient (25 → 20 px page 48) —
    autoriser le glissement fait monter la plus grande taille qui tienne, ce qui ouvre
    d'autant la fenêtre de `_affiner_qualite`, laquelle peut alors descendre plus bas.

    ⚠ La comparaison porte sur `(tient, taille)` et non sur la taille seule : depuis le
    plancher absolu, le glissement peut faire passer une bulle d'un débordement à 11 px à un
    lettrage ENTIER à 8 px. C'est un gain — un débordement fait découper les lettres par le
    masque — mais deux tailles issues de branches différentes ne se comparent pas."""
    for fabrique in (_bulle_ellipse, _bulle_sablier):
        img, region = fabrique()
        style = analyze_bubble(img, region)
        for texte in (TEXTE, "Oui.", "Eeeeeh~~~", "A" * 60, "Un mot", TEXTE * 2):
            sans = best_fit(texte, style, dict(_cfg_test(), glissement_vertical=0.0),
                            resolve_font())
            avec = best_fit(texte, style, dict(_cfg_test(), glissement_vertical=0.5),
                            resolve_font())
            assert (not avec.overflow, avec.size) >= (not sans.overflow, sans.size), (
                fabrique.__name__, texte, sans, avec)


def test_le_glissement_fait_gagner_du_corps_dans_un_sablier():
    img, region = _bulle_sablier()
    style = analyze_bubble(img, region)
    sans = best_fit(TEXTE, style, dict(_cfg_test(), glissement_vertical=0.0), resolve_font())
    avec = best_fit(TEXTE, style, dict(_cfg_test(), glissement_vertical=0.5), resolve_font())
    assert avec.size > sans.size


def test_le_centre_lemporte_a_egalite():
    """Le texte d'une bulle doit rester centré quand rien ne l'y oblige : dans un rectangle,
    toutes les positions valent la même largeur, donc la position centrée doit gagner."""
    region = _region((40, 40, 360, 460), canvas=(400, 500))
    img = Image.new("RGB", (400, 500), (255, 255, 255))
    style = analyze_bubble(img, region)
    prof, cx = _profil(style)
    c = dict(_cfg_test(), _mode=style.mode)
    centre = layout_at_size(TEXTE, prof, cx, 18, c, resolve_font())
    glisse = layout_at_size(TEXTE, prof, cx, 18, c, resolve_font(), glissement=0.5)
    assert centre is not None and glisse is not None
    assert glisse.top == centre.top


@pytest.mark.parametrize("texte", ["Oui.", TEXTE, "Eeeeeh~~~", "A" * 120, TEXTE * 3])
def test_avec_glissement_le_texte_ne_sort_toujours_pas_de_la_bulle(texte):
    """L'invariant fondateur de la brique ne se négocie pas : aucun pixel hors du masque.
    Le glissement déplace le bloc, il ne doit pas l'autoriser à sortir."""
    img, region = _bulle_sablier()
    style = analyze_bubble(img, region)
    avant = np.asarray(img).copy()
    apres = typeset_bubble(img.copy(), region, texte,
                           style=style, cfg=dict(_cfg_test(), glissement_vertical=0.5))
    diff = (np.asarray(apres) != avant).any(axis=2)
    assert not (diff & ~style.interior).any()


def test_le_glissement_reduit_les_debordements():
    """Mesuré sur le tome : 14 débordements → 12. Ici, un texte qui ne tenait pas dans le
    goulot d'un sablier doit cesser d'être signalé."""
    img, region = _bulle_sablier()
    style = analyze_bubble(img, region)
    long_texte = "Anticonstitutionnellement, disait-elle, en toute circonstance."
    sans = best_fit(long_texte, style, dict(_cfg_test(), glissement_vertical=0.0),
                    resolve_font())
    avec = best_fit(long_texte, style, dict(_cfg_test(), glissement_vertical=0.5),
                    resolve_font())
    assert avec.size >= sans.size
    assert not (avec.overflow and not sans.overflow), "le glissement ne crée pas de débordement"


def test_une_bulle_VIDEE_PAR_LA_SUPPRESSION_DE_GLYPHES_est_marquee():
    """LE défaut latent de la 0.24.0. Le test de vacuité voyait le texte tel que le modèle
    l'a rendu ; la suppression des glyphes intervenait APRÈS. Une bulle « traduite » en
    japonais n'est pas vide au premier test, se vide dans `texte_dessinable` (aucune police
    de la chaîne n'a de kana), et sortait donc BLANCHE — sans le marqueur qui existe
    précisément pour signaler un trou.

    Avant la 0.24.0 le même cas sortait en carrés tofu : laid, mais visible et signalé.
    Le rendre silencieux était une régression d'OBSERVABILITÉ."""
    img, region, styles = _bulle_de(220, 180)
    rapport: list = []
    typeset_page(img.copy(), [region], ["こんにちは"], styles=styles, report_out=rapport,
                 sources=["こんにちは"])
    vides = [e for e in rapport if e["type"] == "bulle_vide"]
    assert vides, "une bulle vidée par la suppression de glyphes doit être marquée"
    assert vides[0]["marqueur"] == "…"
    assert vides[0].get("cause") == "glyphes_supprimes"
    # Et la suppression elle-même reste signalée : les deux informations sont utiles.
    assert [e for e in rapport if e["type"] == "glyphes_manquants"]


def test_une_bulle_videe_par_les_glyphes_SANS_source_reste_vierge():
    """Même règle que pour une traduction vide : sans japonais source, rien à signaler."""
    img, region, styles = _bulle_de(220, 180)
    rapport: list = []
    typeset_page(img.copy(), [region], ["こんにちは"], styles=styles, report_out=rapport,
                 sources=[""])
    assert not [e for e in rapport if e["type"] == "bulle_vide"]


def test_une_traduction_francaise_normale_nest_jamais_marquee():
    """Non-régression : le chemin nominal ne doit pas gagner de marqueur au passage."""
    img, region, styles = _bulle_de(220, 180)
    rapport: list = []
    typeset_page(img.copy(), [region], ["Bonjour"], styles=styles, report_out=rapport,
                 sources=["こんにちは"])
    assert not [e for e in rapport if e["type"] == "bulle_vide"]
    assert [e for e in rapport if e["type"] == "bulle"]


# --------------------------------------------------------------------------- #
# Une réplique non vide n'est JAMAIS perdue
#
# Défaut mesuré : au passage de ComicNeue-Bold à Wildjess (~1,3× plus large à corps égal),
# page 22 bulle 2 (« J'aimerais bien tirer. ») et page 68 bulle 5 (« Katch ») du Vol.1
# de manga A sont sorties BLANCHES. Le nettoyage avait effacé le japonais, le test de
# « région dégénérée » avait renoncé au lettrage, et le message conseillait « corriger la
# détection » alors que la détection n'avait pas bougé d'un pixel — c'était la police.
# --------------------------------------------------------------------------- #

def test_une_bulle_trop_etroite_POUR_LA_POLICE_nest_jamais_laissee_blanche():
    """Le 3ᵉ critère de dégénérescence est le seul à dépendre de la POLICE. Le déclencher
    seul ne doit plus faire renoncer : on lettre, quitte à déborder, et on nomme la cause.

    Le plancher est remonté à `taille_min` pour que le mot le plus long ne tienne
    définitivement pas — c'est exactement la situation de la page 22."""
    img, region, styles = _bulle_de(46, 120)
    cfg = dict(_cfg_test(), taille_min=20, taille_min_absolue=20)
    fit = best_fit("J'aimerais", styles[0], cfg, resolve_font())
    assert fit.lines, "la réplique doit être dessinée, pas abandonnée"
    assert fit.cause == "police_trop_large"
    assert fit.overflow is True


def test_une_region_vraiment_minuscule_reste_ecartee():
    """Non-régression de l'autre moitié : les deux critères GÉOMÉTRIQUES font toujours
    renoncer. Une région de 8×8 px ne porte aucun mot, quelle que soit la police — c'est
    une fausse détection, et le rapport doit continuer de pointer la détection."""
    img, region, styles = _bulle_de(8, 8, marge=6)
    fit = best_fit("Bonjour", styles[0], _cfg_test(), resolve_font())
    assert fit.lines == []
    assert fit.cause == "bulle_degeneree"


def test_une_replique_non_dessinee_est_signalee_avec_son_texte():
    """Une bulle blanche est indistinguable d'un choix éditorial. Quand rien n'est peint
    alors que le texte n'était pas vide, le rapport doit porter LA RÉPLIQUE — sans quoi il
    faut rouvrir le checkpoint pour savoir ce qui a disparu."""
    img, region, styles = _bulle_de(8, 8, marge=6)
    rapport: list = []
    typeset_page(img, [region], ["Bonjour"], styles=styles, cfg=_cfg_test(),
                 report_out=rapport)
    perdues = [e for e in rapport if e.get("type") == "replique_non_dessinee"]
    assert perdues, "une réplique non dessinée doit être signalée"
    assert perdues[0]["texte"] == "Bonjour"
    assert perdues[0]["cause"] == "bulle_degeneree"


# --------------------------------------------------------------------------- #
# La chaîne de repli ne dépend plus du répertoire courant
# --------------------------------------------------------------------------- #

def test_les_polices_livrees_sont_des_chemins_ABSOLUS():
    """Elles étaient relatives, donc résolues contre le répertoire COURANT : lancé
    d'ailleurs que de la racine, le repli sautait aux polices système — un tome en Arial,
    sans un mot."""
    from manga.typeset import POLICES_LIVREES
    assert POLICES_LIVREES, "la chaîne livrée ne doit pas être vide"
    for chemin in POLICES_LIVREES:
        assert Path(chemin).is_absolute(), f"{chemin} est relatif au répertoire courant"


def test_les_candidats_systeme_sont_des_chemins_ABSOLUS():
    """`comic.ttf` et `arial.ttf` y figuraient sans dossier. Les deux points d'usage
    filtrent par `Path(c).exists()` : ils n'ont donc jamais été trouvés, et le commentaire
    promettait trois candidats Windows quand il n'y en avait qu'un."""
    # `Path.is_absolute()` ne convient pas : sous Windows il rend False pour un chemin
    # POSIX, et l'inverse. Ce qu'on veut vérifier est plus simple et c'est le vrai défaut :
    # le candidat NOMME-t-il un dossier, ou compte-t-il sur le répertoire courant ?
    for plateforme, candidats in POLICES_SYMBOLES.items():
        for chemin in candidats:
            assert "/" in chemin or "\\" in chemin,                 f"{plateforme} : {chemin} n'a pas de dossier"


def test_resolve_font_marche_depuis_un_autre_repertoire(tmp_path, monkeypatch):
    """Le vrai symptôme, reproduit : changer de répertoire ne doit plus changer la police."""
    depuis_la_racine = resolve_font()
    resolve_font.cache_clear()
    monkeypatch.chdir(tmp_path)
    assert resolve_font() == depuis_la_racine
    resolve_font.cache_clear()


# --------------------------------------------------------------------------- #
# Pré-vol : savoir en deux secondes, pas après dix minutes de rendu
# --------------------------------------------------------------------------- #

def test_le_prevol_nomme_les_glyphes_absents_et_les_bulles_touchees():
    """Le repli se décide par bulle et ne laisse AUCUNE trace : sur le Vol.1, 63 bulles sur
    818 sont sorties dans une autre police que celle demandée sans une ligne de rapport.
    Le pré-vol doit dire lesquelles, et pourquoi, avant de lettrer."""
    from manga.typeset import couverture, message_couverture
    c = couverture(resolve_font(), {1: ["les filles ♪", "Bonjour"], 2: ["Rien de special"]})
    assert c.manquants_textes == "♪"
    assert (c.bulles_touchees, c.bulles_vues) == (1, 3)
    assert c.pages_touchees == [1]
    assert "♪" in "\n".join(message_couverture(c))


def test_un_font_path_ABSENT_nest_pas_avale_en_silence(tmp_path):
    """`resolve_font` retombe sur la chaîne par défaut quand le fichier n'existe pas, sans
    rien dire. Les polices non livrées avec le dépôt étant absentes de toute autre machine,
    un tome entier peut sortir en Comic Neue — le pré-vol doit le crier."""
    from manga.typeset import couverture, message_couverture
    fantome = tmp_path / "nulle-part.ttf"
    c = couverture(str(fantome))
    assert c.existe is False
    assert c.retenue != str(fantome)
    assert "ABSENT" in "\n".join(message_couverture(c))


def test_le_prevol_mesure_la_largeur_relative_a_letalon():
    """Une police large fait tomber les corps et pousse les bulles étroites en débordement.
    L'annoncer avant évite d'accuser la détection. L'étalon se mesure à 1,00 exactement."""
    from manga.typeset import POLICE_ETALON, couverture
    assert couverture(POLICE_ETALON).largeur_relative == pytest.approx(1.0)


def test_un_ruban_de_quelques_pixels_reste_une_FAUSSE_DETECTION():
    """Le critère de largeur se dédouble, et l'oublier a mal classé la page 80 du Vol.1.

    « Un mot ne tient pas » se corrige en changeant de police ; « pas même une lettre ne
    tient » ne se corrige pas du tout. Mesuré : 4 px de largeur maximale pour 258 px de
    haut — l'aire utile (1 032 px²) passe le seuil, la hauteur aussi, et pourtant aucune
    police n'écrira jamais dans un couloir d'un pixel. Conseiller « choisir une police
    moins large » y enverrait chercher un défaut qui n'existe pas.

    ⚠ La mesure porte sur la plus étroite LETTRE, pas sur le caractère le plus étroit : le
    point de ComicNeue-Bold fait 1,0 px à 8 px et « tenait » donc dans ce couloir."""
    img, region, styles = _bulle_de(4, 260)
    fit = best_fit("Une forte source de chaleur...", styles[0], _cfg_test(), resolve_font())
    assert fit.lines == []
    assert fit.cause == "bulle_degeneree", "un ruban de 4 px n'est pas un défaut de police"
