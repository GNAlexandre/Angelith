# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Test central de la brique manga : `clean.clean_bubbles` ne doit JAMAIS modifier un
pixel en dehors des masques de bulles — l'invariant qui garantit que le dessin n'est
jamais altéré (cf. plan de faisabilité, principe directeur).

S'y ajoutent les non-régressions du défaut qui rendait le rendu du tome inexploitable :
**308 bulles sur 797** repeintes en gris/noir. Le masque du détecteur couvre TOUTE la
bulle, contour compris ; l'ancien code l'interprétait comme un masque de TEXTE et
échantillonnait donc `~mask` — le dessin **autour** de la bulle.

⚠ Le test `..._filled_with_measured_background` a dû être réécrit : il construisait un
masque de texte seul (« seul le texte est masqué, pas toute la bulle »), ce qui encodait
la sémantique fausse et masquait précisément ce bug.
"""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga.clean import analyze_bubble, analyze_regions, clean_bubbles
from manga.detection import BubbleRegion
from manga.geometry import erode

BOX = (60, 40, 340, 200)
TAILLE = (400, 260)


def _region_from_box(w: int, h: int, box, kind: str = "bulle") -> BubbleRegion:
    x0, y0, x1, y1 = box
    mask = np.zeros((h, w), dtype=bool)
    mask[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=box, mask=mask, score=0.9, cls=0, kind=kind)


def _masque_ellipse(box, taille) -> np.ndarray:
    """Masque tel que le rend `detection.py` : TOUTE la bulle, contour compris."""
    w, h = taille
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).ellipse(list(box), fill=255)
    return np.asarray(m) > 127


def _planche(fond_case=(20, 20, 20), fond_bulle=(255, 255, 255),
             couleur_texte=(0, 0, 0), box=BOX, taille=TAILLE,
             contour=(0, 0, 0), texte=True):
    """Planche synthétique : une case au fond `fond_case`, une bulle ellipsoïdale au fond
    `fond_bulle` avec son trait de contour, et des « glyphes » à l'intérieur.

    Le fond de case est SOMBRE par défaut : c'est la configuration qui produisait le bug
    (l'ancien code mesurait la couleur là, et repeignait la bulle en gris foncé)."""
    w, h = taille
    img = Image.new("RGB", (w, h), fond_case)
    d = ImageDraw.Draw(img)
    d.ellipse(list(box), fill=fond_bulle, outline=contour, width=4)
    if texte:
        # « glyphes » déterministes (pas de police : reproductible partout), ~8 % de l'aire
        cy = (box[1] + box[3]) // 2
        for i in range(6):
            x = box[0] + 40 + i * 34
            d.rectangle([x, cy - 22, x + 20, cy + 22], fill=couleur_texte)
    region = BubbleRegion(bbox=box, mask=_masque_ellipse(box, taille),
                          score=0.95, cls=0)
    return img, region


# --------------------------------------------------------------------------- #
# L'invariant fondateur
# --------------------------------------------------------------------------- #

def test_pixels_outside_mask_are_bit_identical():
    w, h = 200, 150
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    region = _region_from_box(w, h, (20, 20, 80, 60))

    out = clean_bubbles(img, [region])
    out_arr = np.asarray(out)

    outside = ~region.mask
    assert np.array_equal(out_arr[outside], arr[outside])


def test_aucun_pixel_hors_masque_sur_une_vraie_bulle():
    """Même invariant, sur une bulle ellipsoïdale (masque non rectangulaire) posée sur un
    dessin bruité — le cas réel."""
    rng = np.random.default_rng(3)
    w, h = TAILLE
    fond = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    img = Image.fromarray(fond, mode="RGB")
    d = ImageDraw.Draw(img)
    d.ellipse(list(BOX), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    region = BubbleRegion(bbox=BOX, mask=_masque_ellipse(BOX, TAILLE), score=0.9, cls=0)
    avant = np.asarray(img).copy()

    out = np.asarray(clean_bubbles(img, [region]))
    dehors = ~region.mask
    assert np.array_equal(out[dehors], avant[dehors])


def test_non_bulle_kind_is_left_untouched():
    """Réservé phase 2 (onomatopées sur dessin) : ignoré tant que `kind != 'bulle'`."""
    w, h = 50, 50
    img = Image.new("RGB", (w, h), (1, 2, 3))
    region = _region_from_box(w, h, (5, 5, 20, 20), kind="onomatopee")
    out = clean_bubbles(img, [region])
    assert np.array_equal(np.asarray(out), np.asarray(img))


def test_original_image_is_not_mutated():
    w, h = 60, 60
    img = Image.new("RGB", (w, h), (200, 200, 200))
    original = np.asarray(img).copy()
    region = _region_from_box(w, h, (10, 10, 40, 40))
    clean_bubbles(img, [region])
    assert np.array_equal(np.asarray(img), original)


# --------------------------------------------------------------------------- #
# LA non-régression : la couleur est mesurée DANS la bulle
# --------------------------------------------------------------------------- #

def test_pixels_inside_mask_are_filled_with_measured_background():
    """Réécrit. Le masque couvre TOUTE la bulle (sémantique réelle de `detection.py`), et
    la couleur retenue doit être celle de l'intérieur — pas celle du dessin autour."""
    img, region = _planche(fond_case=(20, 20, 20), fond_bulle=(255, 255, 255))
    style = analyze_bubble(img, region)
    assert style.background == (255, 255, 255)

    out = np.asarray(clean_bubbles(img, [region]))
    cx, cy = (BOX[0] + BOX[2]) // 2, (BOX[1] + BOX[3]) // 2
    assert tuple(out[cy, cx]) == (255, 255, 255)


def test_bulle_blanche_sur_case_noire_reste_blanche():
    """LE bug d'origine, reproduit puis verrouillé : l'ancien code échantillonnait
    `~mask` dans la bbox — le fond de case noir — et repeignait la bulle en (35,35,35) à
    (177,177,177). Sur 797 bulles du tome, 308 étaient dans ce cas."""
    img, region = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255))
    style = analyze_bubble(img, region)
    assert style.background == (255, 255, 255)
    assert style.background_luma > 250
    assert not style.inverted
    assert style.text_color == (0, 0, 0)

    out = np.asarray(clean_bubbles(img, [region]))
    # tout l'intérieur est blanc : plus aucun « glyphe » résiduel
    assert (out[style.interior] == 255).all()


@pytest.mark.parametrize("fond_case", [(0, 0, 0), (20, 20, 20), (60, 60, 60),
                                       (128, 128, 128), (200, 200, 200)])
def test_la_couleur_du_fond_de_case_n_influence_jamais_la_bulle(fond_case):
    """Le fond de case peut être n'importe quoi : la couleur retenue ne doit dépendre que
    de l'intérieur de la bulle."""
    img, region = _planche(fond_case=fond_case, fond_bulle=(255, 255, 255))
    assert analyze_bubble(img, region).background == (255, 255, 255)


def test_le_contour_de_la_bulle_est_preserve():
    """Remplir tout le masque effaçait le trait de contour, qui est à cheval sur la
    frontière du masque. L'intérieur érodé doit rester en retrait de ce trait."""
    img, region = _planche(fond_case=(230, 230, 230), fond_bulle=(255, 255, 255))
    style = analyze_bubble(img, region)
    out = np.asarray(clean_bubbles(img, [region]))
    avant = np.asarray(img)

    # l'anneau = le masque moins l'intérieur peint : il doit être intact
    anneau = region.mask & ~style.interior
    assert anneau.any()
    assert np.array_equal(out[anneau], avant[anneau])
    # et il contient encore des pixels sombres : le trait est là
    assert (out[anneau].min(axis=1) < 100).any()


def test_l_interieur_est_strictement_inclus_dans_le_masque_erode():
    img, region = _planche()
    style = analyze_bubble(img, region)
    assert style.erode_radius > 0
    assert (style.interior & ~region.mask).sum() == 0
    assert np.array_equal(style.interior, erode(region.mask, style.erode_radius))


# --------------------------------------------------------------------------- #
# Polarité : héritée du contraste réel, jamais déduite d'un seuil de luma
# --------------------------------------------------------------------------- #

def test_bulle_inversee_recoit_du_texte_clair():
    """Fond sombre, texte clair (2 bulles du tome). Le MODE de l'histogramme donne la
    couleur du fond sans hypothèse de polarité — un percentile haut renverrait 193, soit
    la couleur du TEXTE."""
    img, region = _planche(fond_case=(240, 240, 240), fond_bulle=(10, 10, 10),
                           couleur_texte=(245, 245, 245), contour=(255, 255, 255))
    style = analyze_bubble(img, region)
    assert style.background_luma < 40
    assert style.inverted is True
    assert style.text_color == (255, 255, 255)


def test_bulle_grise_a_texte_noir_garde_du_texte_noir():
    """Une règle « luma < 128 → texte blanc » basculerait à tort. La polarité vient du
    contraste mesuré, pas d'un seuil absolu."""
    img, region = _planche(fond_case=(250, 250, 250), fond_bulle=(120, 120, 120),
                           couleur_texte=(0, 0, 0))
    style = analyze_bubble(img, region)
    assert 100 <= style.background_luma <= 140
    assert style.inverted is False
    assert style.text_color == (0, 0, 0)


def test_bulle_teintee_est_mesuree_a_trois_pres():
    """Bulles teintées (4 dans le tome) : on MESURE la teinte, on ne suppose pas du blanc."""
    for teinte in ((212, 205, 190), (198, 214, 228)):
        img, region = _planche(fond_case=(30, 30, 30), fond_bulle=teinte)
        fond = analyze_bubble(img, region).background
        assert all(abs(a - b) <= 3 for a, b in zip(fond, teinte)), (fond, teinte)


def test_bulle_sans_texte_ne_bascule_pas_en_inverse():
    """Une bulle vide ne doit pas décider d'une polarité sur trois pixels de poussière."""
    img, region = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255), texte=False)
    style = analyze_bubble(img, region)
    assert style.inverted is False
    assert style.text_color == (0, 0, 0)


# --------------------------------------------------------------------------- #
# Mode de remplissage
# --------------------------------------------------------------------------- #

def test_mode_masque_sur_une_bulle_uniforme():
    img, region = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255))
    style = analyze_bubble(img, region)
    assert style.uniformity >= 0.60
    assert style.mode == "masque"


def test_bascule_en_mode_texte_sur_un_interieur_en_damier():
    """Fausse détection ou bulle contenant du dessin : l'uniformité s'effondre, on ne vide
    plus tout l'intérieur — le fond survit, on n'efface que le texte."""
    w, h = TAILLE
    img = Image.new("RGB", (w, h), (255, 255, 255))
    arr = np.asarray(img).copy()
    ys, xs = np.mgrid[:h, :w]
    damier = ((ys // 8) + (xs // 8)) % 2 == 0
    arr[damier] = (10, 10, 10)
    img = Image.fromarray(arr)
    region = BubbleRegion(bbox=BOX, mask=_masque_ellipse(BOX, TAILLE), score=0.9, cls=0)

    style = analyze_bubble(img, region)
    assert style.uniformity < 0.60
    assert style.mode == "texte"

    out = np.asarray(clean_bubbles(img, [region]))
    # en mode "texte", une partie de l'intérieur n'est PAS repeinte
    inchange = (out[style.interior] == np.asarray(img)[style.interior]).all(axis=1)
    assert inchange.any(), "le mode texte doit laisser survivre du fond de bulle"


def test_fausse_detection_sur_du_dessin_sombre_est_ABANDONNEE():
    """Régression trouvée au contrôle visuel de `page_0044` : le détecteur avait pris un
    gratte-ciel aux fenêtres sombres pour une bulle. Fond mesuré à luma 4, polarité
    « inversée », uniformité 0,131 — et en mode « texte » toute la structure CLAIRE du
    bâtiment devenait le « masque de texte », repeinte en noir. Le dessin était détruit.

    En dessous de `seuil_abandon`, on ne peint plus rien : mieux vaut un texte japonais
    resté visible (donc corrigible) qu'un morceau de planche perdu."""
    w, h = 240, 300
    arr = np.full((h, w, 3), 250, dtype=np.uint8)
    # Dessin richement texturé : la luminance est ÉTALÉE sur toute la plage, si bien
    # qu'aucune valeur ne domine — c'est la signature d'un morceau de planche, pas d'une
    # bulle (dont l'intérieur est uni par construction). Sur page_0044 réelle : 0,131.
    ys, xs = np.mgrid[20:280, 60:180]
    degrade = ((xs - 60) * 255 // 119).astype(np.uint8)
    hachures = (((ys // 3) % 2) * 40).astype(np.uint8)
    zone = np.clip(degrade.astype(np.int16) - hachures, 0, 255).astype(np.uint8)
    arr[20:280, 60:180] = zone[:, :, None]
    img = Image.fromarray(arr)
    mask = np.zeros((h, w), dtype=bool)
    mask[20:280, 60:180] = True
    region = BubbleRegion(bbox=(60, 20, 180, 280), mask=mask, score=0.62, cls=0)

    style = analyze_bubble(img, region)
    assert style.uniformity < 0.35
    assert style.mode == "aucun"

    out = clean_bubbles(img, [region])
    assert np.array_equal(np.asarray(out), arr), "le dessin doit rester intact"


def test_le_mode_texte_reste_actif_entre_les_deux_seuils():
    """Une bulle légitime qui contient un peu de dessin (uniformité entre les deux seuils)
    doit encore être nettoyée en mode « texte », pas abandonnée."""
    img, region = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255))
    style = analyze_bubble(img, region, {"seuil_uniformite": 0.99, "seuil_abandon": 0.10})
    assert style.mode == "texte"


def test_seuil_abandon_configurable():
    img, region = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255))
    # abandon quasi impossible à franchir → tout est abandonné
    assert analyze_bubble(img, region, {"seuil_abandon": 1.01,
                                        "seuil_uniformite": 1.02}).mode == "aucun"


def test_une_bulle_abandonnee_reste_dans_styles_out():
    """L'alignement par position doit survivre à un abandon (le rapport en a besoin)."""
    img, region = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255))
    styles: list = []
    clean_bubbles(img, [region], {"seuil_abandon": 1.01, "seuil_uniformite": 1.02},
                  styles_out=styles)
    assert len(styles) == 1 and styles[0].mode == "aucun" and styles[0].ok


def test_mode_peut_etre_force_par_la_config():
    img, region = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255))
    assert analyze_bubble(img, region, {"mode": "texte"}).mode == "texte"
    assert analyze_bubble(img, region, {"mode": "masque"}).mode == "masque"


def test_seuil_uniformite_configurable():
    img, region = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255))
    # seuil impossible à atteindre → bascule en "texte"
    assert analyze_bubble(img, region, {"seuil_uniformite": 1.01}).mode == "texte"


# --------------------------------------------------------------------------- #
# safe_erode : bulles dégénérées
# --------------------------------------------------------------------------- #

def test_bulle_fine_retombe_sur_un_rayon_reduit_sans_planter():
    w, h = 200, 120
    img = Image.new("RGB", (w, h), (255, 255, 255))
    mask = np.zeros((h, w), dtype=bool)
    mask[58:64, 20:180] = True            # 6 px de haut
    region = BubbleRegion(bbox=(20, 58, 180, 64), mask=mask, score=0.9, cls=0)
    style = analyze_bubble(img, region)
    assert style.ok
    assert style.interior.any()


def test_masque_vide_ne_peint_rien():
    w, h = 60, 60
    img = Image.new("RGB", (w, h), (123, 45, 67))
    mask = np.zeros((h, w), dtype=bool)
    region = BubbleRegion(bbox=(10, 10, 40, 40), mask=mask, score=0.9, cls=0)
    style = analyze_bubble(img, region)
    assert style.ok is False
    out = clean_bubbles(img, [region])
    assert np.array_equal(np.asarray(out), np.asarray(img))


# --------------------------------------------------------------------------- #
# styles_out / analyze_regions : alignement par position
# --------------------------------------------------------------------------- #

def test_styles_out_est_rempli_dans_l_ordre():
    img, r1 = _planche(fond_case=(0, 0, 0), fond_bulle=(255, 255, 255),
                       box=(20, 20, 180, 120), taille=(400, 260))
    _img2, r2 = _planche(fond_case=(0, 0, 0), fond_bulle=(120, 120, 120),
                         box=(220, 140, 380, 240), taille=(400, 260))
    d = ImageDraw.Draw(img)
    d.ellipse([220, 140, 380, 240], fill=(120, 120, 120), outline=(0, 0, 0), width=4)

    styles: list = []
    clean_bubbles(img, [r1, r2], styles_out=styles)
    assert len(styles) == 2
    assert styles[0].background == (255, 255, 255)
    assert 100 <= styles[1].background_luma <= 140
    assert [s.bbox for s in styles] == [r1.bbox, r2.bbox]


def test_analyze_regions_garde_l_alignement_avec_les_non_bulles():
    """`regions`, `ocr.json` et `traduction.json` s'alignent PAR POSITION : une région
    non-bulle doit produire un style, pas être sautée."""
    img, bulle = _planche()
    onoma = _region_from_box(TAILLE[0], TAILLE[1], (10, 220, 60, 250), kind="onomatopee")
    styles = analyze_regions(img, [onoma, bulle, onoma])
    assert len(styles) == 3
    assert [s.ok for s in styles] == [False, True, False]


def test_styles_peut_etre_reutilise_sans_reanalyse():
    """L'orchestrateur analyse l'image D'ORIGINE une seule fois puis passe les styles :
    sur une page déjà nettoyée, la polarité serait indéductible."""
    img, region = _planche(fond_case=(240, 240, 240), fond_bulle=(10, 10, 10),
                           couleur_texte=(245, 245, 245), contour=(255, 255, 255))
    styles = analyze_regions(img, [region])
    assert styles[0].inverted is True

    out = clean_bubbles(img, [region], styles=styles)
    # la bulle est repeinte dans SA couleur sombre mesurée
    assert np.asarray(out)[styles[0].interior].max() < 40


def test_clean_bubbles_reste_compatible_sans_cfg_ni_styles():
    """Rétro-compatibilité : la signature à deux arguments et le type de retour ne
    changent pas (appelée telle quelle par l'orchestrateur historique)."""
    img, region = _planche()
    out = clean_bubbles(img, [region])
    assert isinstance(out, Image.Image)
    assert out.size == img.size
