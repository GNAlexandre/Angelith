# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Test d'ENCRE — « cette planche porte-t-elle autre chose que du fond ? »

C'est le discriminant qui arme l'escalade de détection (lot 12, L4.2) et qui remplit la colonne
« dont encrées » du banc. Le seul qui existait avant lui était `bool(qa["sfx"])`, indisponible
dès que la passe onomatopées ne tourne pas — et les trois volumes de *manga D* du
corpus de mesure n'ont aucun `sfx.json`.

Sans modèle, sans E/S, sans dépendance nouvelle : ces tests tournent sur un checkout frais.
"""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import detection


def _planche(fond="white", trait=None, taille=(844, 1200), epaisseur=6):
    """Une planche unie, éventuellement barrée d'un rectangle d'une autre couleur."""
    img = Image.new("RGB", taille, fond)
    if trait is not None:
        ImageDraw.Draw(img).rectangle([100, 100, taille[0] - 100, taille[1] - 200],
                                      outline=trait, width=epaisseur)
    return img


def test_une_planche_UNIE_ne_porte_pas_dencre():
    assert detection.part_encre(_planche()) == 0.0
    assert detection.porte_de_l_encre(_planche()) is False


def test_une_planche_DESSINEE_porte_de_lencre():
    assert detection.porte_de_l_encre(_planche(trait="black")) is True


def test_le_fond_est_la_MEDIANE_et_non_le_blanc():
    """Une planche inversée (blanc sur noir) et un webtoon couleur ont un fond qui n'est pas
    blanc. Mesurer « ce qui n'est pas blanc » les déclarerait tous couverts d'encre, alors que
    le second peut être une page de garde colorée."""
    inversee = _planche(fond="black", trait="white")
    unie_sombre = _planche(fond="black")
    assert detection.porte_de_l_encre(inversee) is True
    assert detection.porte_de_l_encre(unie_sombre) is False
    # …et les deux sens donnent la MÊME part : le test ne privilégie aucune polarité.
    assert detection.part_encre(inversee) == pytest.approx(
        detection.part_encre(_planche(trait="black")), abs=1e-6)


def test_la_luminance_est_signee_des_DEUX_cotes_du_fond():
    """int16 et non uint8 : `abs(arr - fond)` sur des uint8 repasse par zéro sur un pixel plus
    SOMBRE que le fond — c'est-à-dire sur tout le trait d'un manga."""
    arr = np.full((400, 400), 200, dtype=np.uint8)
    arr[100:110, :] = 10                       # un trait bien plus sombre que le fond
    assert detection.part_encre(arr) > 0.01


def test_le_SOUS_ECHANTILLONNAGE_ne_fait_pas_disparaitre_un_trait_fin():
    """`Image.BOX` fait une vraie moyenne de bloc. `NEAREST` prendrait un pixel sur seize et
    raterait un trait fin une fois sur quatre, ce qui rendrait le verdict dépendant de
    l'alignement du lettrage sur la grille de sous-échantillonnage.

    Le trait fait 2 px ; le facteur de réduction, 4."""
    for decalage in range(4):
        arr = np.full((400, 400), 240, dtype=np.uint8)
        arr[100 + decalage:102 + decalage, :] = 0
        assert detection.porte_de_l_encre(arr), f"trait perdu au décalage {decalage}"


def test_le_test_dencre_coute_des_MILLISECONDES():
    """Il est posé sur chaque planche d'un run, donc sur 1 513 planches du corpus de mesure.
    Une passe pleine résolution le rendrait impraticable — d'où le sous-échantillonnage.

    On ne mesure pas un temps (une CI n'a pas de temps stable) mais le fait que le tableau
    RÉELLEMENT parcouru est bien 16 fois plus petit que la planche."""
    grande = _planche(taille=(1600, 2400))
    reduit = detection._luminance(grande, detection.SOUS_ECHANTILLON_ENCRE)
    assert reduit.shape == (2400 // 4, 1600 // 4)


def test_un_chemin_et_une_image_donnent_le_MEME_verdict(tmp_path):
    """Le pipeline passe une `PIL.Image` déjà ouverte, le banc passe un chemin. Deux réponses
    différentes pour la même planche rendraient le rapport incomparable au run."""
    chemin = tmp_path / "planche.png"
    _planche(trait="black").save(chemin)
    assert detection.part_encre(chemin) == pytest.approx(
        detection.part_encre(_planche(trait="black")))


def test_une_image_VIDE_ne_leve_pas():
    assert detection.part_encre(Image.new("RGB", (0, 0))) == 0.0


def test_le_seuil_est_bas_EXPRES():
    """L'asymétrie est le sujet : un faux positif coûte une inférence de plus sur une page de
    garde ; un faux négatif efface du décompte une planche entièrement non traduite — l'erreur
    que le lot 12 cherche précisément à rendre visible."""
    assert detection.SEUIL_ENCRE <= 0.01
    # Un séparateur portant un seul petit logo doit basculer du bon côté.
    planche = _planche()
    ImageDraw.Draw(planche).rectangle([400, 560, 460, 620], fill="black")
    assert detection.porte_de_l_encre(planche) is True
