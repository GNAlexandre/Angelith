# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ordre de lecture manga par **coupe X-Y récursive**, et isolement de la bulle avant OCR.

Ces tests n'ont besoin ni du modèle ONNX ni de `manga-ocr` : la coupe X-Y ne travaille que
sur des boîtes, et `masked_crop` que sur des pixels.

Le défaut corrigé : l'ordre était calculé par agrégation par chevauchement vertical **sur
toute la largeur de la page**. Deux cases côte à côte tombaient donc dans la même « bande »
et leurs bulles étaient lues en zigzag d'une case à l'autre — le dialogue traduit s'en
trouvait mélangé, sans aucune alerte puisque le NOMBRE de bulles restait juste.
"""
import numpy as np
import pytest
from PIL import Image

from manga.detection import BubbleRegion
from manga.ocr import _gouttiere, masked_crop, reading_order


def _b(x0, y0, x1, y1, nom=None):
    r = BubbleRegion(bbox=(x0, y0, x1, y1), mask=np.zeros((1, 1), dtype=bool),
                     score=0.9, cls=0)
    r.nom = nom                     # étiquette de lisibilité pour les assertions
    return r


def _noms(regions):
    return [r.nom for r in regions]


# --------------------------------------------------------------------------- #
# Gouttières
# --------------------------------------------------------------------------- #

def test_gouttiere_trouve_le_plus_grand_trou():
    """Trous de 2 (10→12) et de 40 (20→60) : on retient le second, coupé en son milieu."""
    largeur, coupe = _gouttiere([(0, 10), (12, 20), (60, 70)])
    assert largeur == 40 and coupe == 40.0


def test_gouttiere_absente_si_les_segments_se_recouvrent():
    assert _gouttiere([(0, 50), (20, 80), (40, 100)]) == (0.0, None)


def test_gouttiere_gere_les_segments_imbriques():
    """Un segment entièrement contenu dans un autre ne crée pas de gouttière."""
    assert _gouttiere([(0, 100), (20, 30)]) == (0.0, None)


def test_gouttiere_segment_unique():
    assert _gouttiere([(0, 10)]) == (0.0, None)


# --------------------------------------------------------------------------- #
# Ordre de lecture
# --------------------------------------------------------------------------- #

def test_ordre_droite_a_gauche_sur_une_meme_ligne():
    gauche, milieu, droite = _b(10, 10, 100, 90, "G"), _b(150, 10, 240, 90, "M"), _b(300, 10, 390, 90, "D")
    assert _noms(reading_order([gauche, droite, milieu])) == ["D", "M", "G"]


def test_ordre_haut_en_bas_sur_une_meme_colonne():
    haut, bas = _b(10, 10, 100, 90, "H"), _b(10, 200, 100, 290, "B")
    assert _noms(reading_order([bas, haut])) == ["H", "B"]


def test_deux_cases_cote_a_cote_ne_sont_PAS_entrelacees():
    """LE cas de la page 20. Deux cases côte à côte, chacune avec des bulles à des hauteurs
    qui se chevauchent d'une case à l'autre.

    L'ancienne agrégation par chevauchement vertical formait des bandes sur toute la largeur
    de la page : D1 et G1 se retrouvaient dans la même bande, puis D2 et G2 — d'où la
    lecture D1, G1, D2, G2, qui saute d'une case à l'autre à chaque réplique. La coupe X-Y
    voit d'abord la gouttière VERTICALE entre les deux cases et lit donc la case de droite
    en entier, puis celle de gauche."""
    # case de droite (x ≈ 600-950) et case de gauche (x ≈ 50-400), gouttière à x ≈ 500
    d1 = _b(620, 20, 900, 140, "D1")
    d2 = _b(640, 200, 920, 320, "D2")
    g1 = _b(60, 60, 340, 180, "G1")      # chevauche verticalement D1 ET D2
    g2 = _b(80, 240, 360, 360, "G2")
    ordre = _noms(reading_order([g2, d1, g1, d2]))
    assert ordre == ["D1", "D2", "G1", "G2"], ordre


def test_une_bande_horizontale_est_lue_avant_la_suivante():
    """Rangées de cases : la gouttière horizontale doit primer."""
    r1d, r1g = _b(600, 20, 900, 200, "R1D"), _b(60, 20, 360, 200, "R1G")
    r2d, r2g = _b(600, 400, 900, 580, "R2D"), _b(60, 400, 360, 580, "R2G")
    ordre = _noms(reading_order([r2g, r1g, r2d, r1d]))
    assert ordre == ["R1D", "R1G", "R2D", "R2G"], ordre


def test_planche_a_trois_niveaux_de_decoupe():
    """Deux rangées, deux cases par rangée, deux bulles par case : la récursion doit
    descendre proprement les trois niveaux, en RANGÉES puis de droite à gauche.

    Géométrie d'une planche réelle (1125×1600, gouttières ~40 px dans les deux sens). Ce
    détail compte : un damier 2×2 est géométriquement ambigu entre lecture en rangées et en
    colonnes, et c'est la normalisation par l'étendue du groupe qui tranche — une page étant
    plus haute que large, l'écart normalisé est plus grand sur l'axe vertical à gouttières
    comparables, donc la coupe en rangées gagne."""
    boites, attendu = [], []
    for ligne, ytop in enumerate((60, 840), start=1):
        for case, xleft in ((1, 600), (2, 60)):        # droite d'abord
            for bulle, dy in ((1, 0), (2, 330)):
                nom = f"L{ligne}C{case}B{bulle}"
                boites.append(_b(xleft, ytop + dy, xleft + 460, ytop + dy + 300, nom))
                attendu.append(nom)
    melange = [boites[i] for i in (5, 0, 7, 2, 4, 1, 6, 3)]
    assert _noms(reading_order(melange)) == attendu


def test_une_gouttiere_verticale_franche_prime_sur_un_petit_ecart_horizontal():
    """Le pendant du test précédent, et le cas de la page 20 : quand la gouttière verticale
    est franchement plus large que l'horizontale (260 px contre 20 px), c'est bien la coupe
    verticale qui gagne — la case de droite est lue en entier avant celle de gauche."""
    d1, d2 = _b(620, 20, 900, 140, "D1"), _b(640, 200, 920, 320, "D2")
    g1, g2 = _b(60, 60, 340, 180, "G1"), _b(80, 240, 360, 360, "G2")
    assert _noms(reading_order([g2, d1, g1, d2])) == ["D1", "D2", "G1", "G2"]


def test_repli_diagonal_quand_aucune_gouttiere():
    """Bulles qui se chevauchent sur les DEUX axes (mise en page très libre) : aucune
    gouttière exploitable, on retombe sur la diagonale `y0/H + (W − x1)/W`.

    Le tri suit la formule, et non une intuition : ici B passe avant A parce qu'elle est
    nettement plus à droite (bord droit à 300 contre 200) pour un décalage vertical modeste.
    On vérifie donc l'accord avec la formule documentée, sur laquelle un lecteur peut
    raisonner, plutôt qu'un ordre codé en dur."""
    a, b, c = _b(0, 0, 200, 200, "A"), _b(100, 100, 300, 300, "B"), _b(50, 150, 250, 350, "C")
    ordre = _noms(reading_order([c, a, b]))
    assert set(ordre) == {"A", "B", "C"}

    gy0, gy1 = 0, 350
    gx0, gx1 = 0, 300
    cle = {r.nom: (r.bbox[1] - gy0) / (gy1 - gy0) + (gx1 - r.bbox[2]) / (gx1 - gx0)
           for r in (a, b, c)}
    assert ordre == sorted(cle, key=cle.get)
    assert ordre == ["B", "A", "C"]


def test_ordre_est_une_permutation_exacte():
    """Aucune bulle perdue, aucune dupliquée — l'alignement par position en dépend."""
    rng = np.random.default_rng(5)
    boites = []
    for i in range(24):
        x = int(rng.integers(0, 900)); y = int(rng.integers(0, 1400))
        boites.append(_b(x, y, x + 90, y + 70, f"b{i}"))
    ordre = reading_order(boites)
    assert len(ordre) == len(boites)
    assert sorted(id(r) for r in ordre) == sorted(id(r) for r in boites)


def test_liste_vide_et_singleton():
    assert reading_order([]) == []
    seule = _b(0, 0, 10, 10, "S")
    assert reading_order([seule]) == [seule]


def test_ordre_est_deterministe():
    boites = [_b(600, 20, 900, 140, "A"), _b(60, 60, 340, 180, "B"),
              _b(640, 200, 920, 320, "C")]
    a = _noms(reading_order(list(boites)))
    b = _noms(reading_order(list(reversed(boites))))
    assert a == b


def test_ancien_comportement_de_reference_reste_valide():
    """Le test historique : haut-droite, haut-gauche, puis bas."""
    hd, hg, bas = _b(80, 0, 100, 20, "HD"), _b(0, 0, 20, 20, "HG"), _b(0, 100, 20, 120, "B")
    assert _noms(reading_order([bas, hg, hd])) == ["HD", "HG", "B"]


# --------------------------------------------------------------------------- #
# masked_crop
# --------------------------------------------------------------------------- #

def _region_ellipse(box, taille):
    m = Image.new("L", taille, 0)
    from PIL import ImageDraw
    ImageDraw.Draw(m).ellipse(list(box), fill=255)
    return BubbleRegion(bbox=box, mask=np.asarray(m) > 127, score=0.9, cls=0)


def test_masked_crop_efface_le_texte_voisin():
    """`image.crop(bbox)` laissait entrer le texte de la bulle d'à côté, que manga-ocr
    lisait aussi — polluant la traduction sans qu'aucun compteur ne le voie."""
    taille = (300, 200)
    img = Image.new("RGB", taille, (255, 255, 255))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.ellipse([20, 20, 160, 180], fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    d.rectangle([60, 90, 120, 110], fill=(0, 0, 0))       # « texte » de NOTRE bulle
    d.rectangle([170, 40, 290, 70], fill=(0, 0, 0))       # texte VOISIN, dans la bbox élargie
    region = _region_ellipse((20, 20, 160, 180), taille)

    crop = masked_crop(img, region, background=(255, 255, 255), marge=30)
    arr = np.asarray(crop)
    # notre texte est là...
    assert (arr < 60).any()
    # ...et la zone du voisin (colonnes de droite du crop) est unie
    droite = arr[:, -25:]
    assert (droite == 255).all(), "le texte voisin n'a pas été effacé"


def test_masked_crop_utilise_la_couleur_mesuree_et_non_du_blanc():
    """Sur une bulle inversée, une toile blanche autour d'un texte clair détruirait le
    contraste, donc l'OCR."""
    taille = (200, 200)
    img = Image.new("RGB", taille, (250, 250, 250))
    from PIL import ImageDraw
    ImageDraw.Draw(img).ellipse([40, 40, 160, 160], fill=(8, 8, 8))
    region = _region_ellipse((40, 40, 160, 160), taille)
    crop = np.asarray(masked_crop(img, region, background=(8, 8, 8), marge=10))
    assert crop[0, 0].tolist() == [8, 8, 8]          # coin = fond de bulle, pas blanc


def test_masked_crop_conserve_le_contour_de_la_bulle():
    """Masque BRUT, contour compris : c'est à cela que manga-ocr a été entraîné."""
    taille = (200, 200)
    img = Image.new("RGB", taille, (255, 255, 255))
    from PIL import ImageDraw
    ImageDraw.Draw(img).ellipse([40, 40, 160, 160], fill=(255, 255, 255),
                                outline=(0, 0, 0), width=4)
    region = _region_ellipse((40, 40, 160, 160), taille)
    crop = np.asarray(masked_crop(img, region, marge=8))
    assert (crop < 60).any(), "le trait de contour doit survivre"


def test_masked_crop_agrandit_les_petites_bulles():
    taille = (100, 100)
    img = Image.new("RGB", taille, (255, 255, 255))
    region = _region_ellipse((40, 40, 70, 70), taille)
    petit = masked_crop(img, region, marge=0, agrandissement_min=64)
    assert min(petit.size) >= 60          # ×2 appliqué
    grand = masked_crop(img, region, marge=0, agrandissement_min=8)
    assert grand.size == (30, 30)         # pas d'agrandissement


def test_masked_crop_masque_vide_retombe_sur_le_rectangle():
    """Masque dégénéré : on rend le rectangle brut plutôt qu'une toile unie, sinon l'OCR
    lirait une image vide et renverrait du bruit en silence."""
    taille = (120, 120)
    img = Image.new("RGB", taille, (255, 255, 255))
    from PIL import ImageDraw
    ImageDraw.Draw(img).rectangle([50, 50, 90, 70], fill=(0, 0, 0))
    region = BubbleRegion(bbox=(40, 40, 100, 80),
                          mask=np.zeros((120, 120), dtype=bool), score=1.0, cls=0)
    crop = np.asarray(masked_crop(img, region, marge=0))
    assert (crop < 60).any(), "le contenu du rectangle doit être conservé"


def test_masked_crop_borne_la_marge_aux_limites_de_l_image():
    taille = (60, 60)
    img = Image.new("RGB", taille, (200, 200, 200))
    region = _region_ellipse((0, 0, 30, 30), taille)
    crop = masked_crop(img, region, marge=50)
    assert crop.width <= 60 * 2 and crop.height <= 60 * 2   # agrandissement possible


def test_masked_crop_ne_modifie_pas_l_image_source():
    taille = (150, 150)
    img = Image.new("RGB", taille, (255, 255, 255))
    region = _region_ellipse((30, 30, 120, 120), taille)
    avant = np.asarray(img).copy()
    masked_crop(img, region)
    assert np.array_equal(np.asarray(img), avant)


@pytest.mark.parametrize("marge", [0, 6, 20])
def test_masked_crop_ne_plante_pas_selon_la_marge(marge):
    taille = (200, 200)
    img = Image.new("RGB", taille, (255, 255, 255))
    region = _region_ellipse((50, 50, 150, 150), taille)
    assert masked_crop(img, region, marge=marge).size[0] > 0
