# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La mise en page devient une DONNÉE — `mise_en_page.json` et son effet sur le lettrage.

Jusqu'ici la position du texte n'existait nulle part : `typeset_page` la recalculait à chaque
rendu depuis le masque de la bulle, et `fits_out` — la seule trace — n'était même alloué que si
l'export PSD était actif, puis jeté. Déplacer un bloc de texte était donc impossible par
construction : il n'y avait rien à déplacer.

Ce que ces tests protègent :

- **l'additivité** — une planche sans `mise_en_page.json` est lettrée exactement comme avant ;
- **la découpe** — le rectangle enregistré sert AUSSI de masque, sinon un texte traîné hors de
  sa bulle est découpé à l'ancienne et disparaît en silence ;
- **le repli** — un rectangle devenu trop petit fait retomber sur la recherche normale plutôt
  que de perdre la réplique ;
- **l'harmonisation** — elle ramène les bulles trop grandes vers la médiane, ce qui est un bon
  réflexe automatique et une trahison quand quelqu'un a choisi une taille.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import checkpoints, typeset
from manga.clean import analyze_bubble
from manga.detection import BubbleRegion

TAILLE = (400, 600)
BOX = (60, 60, 340, 300)


def _planche() -> Image.Image:
    img = Image.new("RGB", TAILLE, (200, 200, 200))
    ImageDraw.Draw(img).ellipse(list(BOX), fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    return img


def _region() -> BubbleRegion:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse(list(BOX), fill=255)
    return BubbleRegion(bbox=BOX, mask=np.asarray(m) > 127, score=0.9, cls=0)


@pytest.fixture
def bulle():
    image = _planche()
    region = _region()
    return image, region, analyze_bubble(image, region, None)


# --------------------------------------------------------------------------- #
# Le fichier
# --------------------------------------------------------------------------- #

def test_aller_retour(tmp_path):
    mises = {3: {"rect": [10, 20, 110, 90], "taille": 22, "interligne": 1.2}}
    checkpoints.save_mise_en_page(tmp_path, mises)
    assert checkpoints.load_mise_en_page(tmp_path) == mises


def test_un_dictionnaire_vide_supprime_le_fichier(tmp_path):
    """« Aucune position imposée » et « un fichier de positions vide » doivent se lire pareil."""
    checkpoints.save_mise_en_page(tmp_path, {1: {"rect": [0, 0, 10, 10]}})
    checkpoints.save_mise_en_page(tmp_path, {})
    assert not (tmp_path / checkpoints.MISE_EN_PAGE_FILENAME).exists()
    assert checkpoints.load_mise_en_page(tmp_path) == {}


def test_une_entree_sans_rect_mais_avec_taille_est_gardee(tmp_path):
    """Régler le corps d'une bulle ne doit pas obliger à lui inventer un rectangle.

    Ce test remplace un `test_une_entree_sans_rect_est_ecartee` qui verrouillait l'inverse. Le
    motif d'alors — « c'est le rectangle qui porte la position ET la découpe » — était juste,
    et c'est exactement pourquoi il ne faut pas en fabriquer un : `style_impose` remplacerait
    l'intérieur du ballon par ses quatre coins (cf.
    `test_une_taille_seule_garde_le_masque_du_ballon`)."""
    (tmp_path / checkpoints.MISE_EN_PAGE_FILENAME).write_text(
        '{"0": {"taille": 20}, "1": {"rect": [1, 2, 3, 4]}}', encoding="utf-8")
    charge = checkpoints.load_mise_en_page(tmp_path)
    assert list(charge) == [0, 1]
    assert charge[0] == {"taille": 20} and "rect" not in charge[0]


def test_une_entree_sans_rect_ni_style_est_ecartee(tmp_path):
    """`{}` et `{"ancre": "libre"}` ne décrivent rien : les garder ferait entrer dans le
    chemin « mise en page imposée » une bulle dont rien n'a été imposé."""
    (tmp_path / checkpoints.MISE_EN_PAGE_FILENAME).write_text(
        '{"0": {}, "1": {"ancre": "libre"}, "2": {"taille": 18}}', encoding="utf-8")
    assert list(checkpoints.load_mise_en_page(tmp_path)) == [2]


def test_un_rect_abime_ne_contamine_pas_le_style(tmp_path):
    """Un rectangle à trois nombres est ignoré, mais la taille qui l'accompagne survit."""
    (tmp_path / checkpoints.MISE_EN_PAGE_FILENAME).write_text(
        '{"0": {"rect": [1, 2, 3], "taille": 24}}', encoding="utf-8")
    assert checkpoints.load_mise_en_page(tmp_path) == {0: {"taille": 24}}


def test_un_fichier_abime_ne_fait_pas_echouer_un_tome(tmp_path):
    (tmp_path / checkpoints.MISE_EN_PAGE_FILENAME).write_text("{ pas du json", encoding="utf-8")
    assert checkpoints.load_mise_en_page(tmp_path) == {}


def test_la_mise_en_page_compte_dans_l_empreinte():
    """Sans elle dans `_SUIVIS`, déplacer un texte ne ferait pas bouger la révision de
    `projet.json` — et le contrôle de fraîcheur de l'éditeur ne verrait rien passer."""
    from manga import projet
    assert "mise_en_page.json" in projet._SUIVIS


# --------------------------------------------------------------------------- #
# Le style imposé
# --------------------------------------------------------------------------- #

def test_style_impose_remplace_l_interieur_par_le_rectangle(bulle):
    _img, _region, style = bulle
    impose = typeset.style_impose(style, (10, 20, 110, 90))

    ys, xs = np.nonzero(impose.interior)
    assert (int(xs.min()), int(ys.min())) == (10, 20)
    assert (int(xs.max()) + 1, int(ys.max()) + 1) == (110, 90)
    assert impose.center_x == 60


def test_style_impose_garde_les_couleurs_de_la_bulle(bulle):
    """Déplacer un texte ne change pas la façon dont il doit être encré : une bulle inversée
    reste blanche sur noir, où qu'on pose son texte."""
    _img, _region, style = bulle
    impose = typeset.style_impose(style, (10, 20, 110, 90))
    assert impose.text_color == style.text_color
    assert impose.background == style.background
    assert impose.inverted == style.inverted
    assert impose.mode == style.mode


def test_style_impose_borne_le_rectangle_a_la_planche(bulle):
    _img, _region, style = bulle
    impose = typeset.style_impose(style, (-50, -50, 10_000, 10_000))
    assert impose.interior.shape == style.interior.shape
    assert impose.interior.all(), "borné, mais non vidé"


# --------------------------------------------------------------------------- #
# Le lettrage
# --------------------------------------------------------------------------- #

def _rendre(image, region, texte, layouts=None, rapport=None):
    return typeset.typeset_page(image.copy(), [region], [texte], styles=None,
                                cfg=None, report_out=rapport, layouts=layouts)


def test_sans_layout_le_rendu_est_celui_d_avant(bulle):
    """L'additivité : le paramètre ne doit rien changer quand il est absent."""
    image, region, _style = bulle
    a = _rendre(image, region, "Bonjour tout le monde")
    b = typeset.typeset_page(image.copy(), [region], ["Bonjour tout le monde"])
    assert a.tobytes() == b.tobytes()


def test_un_layout_impose_la_taille(bulle):
    image, region, _style = bulle
    rapport: list[dict] = []
    _rendre(image, region, "Bonjour", layouts={0: {"rect": [80, 80, 320, 280], "taille": 18}},
            rapport=rapport)
    entree = next(e for e in rapport if e["type"] == "bulle")
    assert entree["taille"] == 18
    assert entree["repli"] == "mise_en_page"


def test_un_layout_deplace_reellement_le_texte(bulle):
    """Le test qui compte : deux rectangles différents doivent produire deux images
    différentes, et l'encre doit se trouver DANS le rectangle demandé."""
    image, region, _style = bulle
    haut = _rendre(image, region, "Bonjour",
                   layouts={0: {"rect": [80, 70, 320, 150], "taille": 16}})
    bas = _rendre(image, region, "Bonjour",
                  layouts={0: {"rect": [80, 200, 320, 280], "taille": 16}})
    assert haut.tobytes() != bas.tobytes()

    # On compte les pixels qui DIFFÈRENT de la planche vierge, et non les pixels sombres :
    # le contour du ballon traverse les deux bandes et se ferait compter comme du texte.
    vierge = np.asarray(image.convert("L"), dtype=int)

    def _ajout(img, y0, y1):
        rendu = np.asarray(img.convert("L"), dtype=int)
        return int((np.abs(rendu - vierge)[y0:y1, 80:320] > 40).sum())

    assert _ajout(haut, 70, 150) > 0 and _ajout(haut, 200, 280) == 0
    assert _ajout(bas, 200, 280) > 0 and _ajout(bas, 70, 150) == 0


def test_un_rectangle_trop_petit_fait_retomber_sur_la_recherche(bulle):
    """Une mise en page enregistrée est une préférence forte, pas une consigne suicide : si le
    texte a rallongé depuis, mieux vaut une réplique mal placée qu'une réplique perdue."""
    image, region, _style = bulle
    rapport: list[dict] = []
    _rendre(image, region,
            "Une réplique nettement plus longue que prévu, vraiment très longue",
            layouts={0: {"rect": [100, 100, 130, 120], "taille": 40}}, rapport=rapport)

    assert any(e["type"] == "mise_en_page_abandonnee" for e in rapport)
    entree = next(e for e in rapport if e["type"] == "bulle")
    assert entree["repli"] != "mise_en_page"


def test_l_harmonisation_epargne_une_taille_choisie():
    """Elle ramène les bulles trop grandes vers la médiane. Excellent réflexe automatique —
    et trahison quand quelqu'un a posé une taille à la main."""
    impose = typeset.Fit(lines=["A"], size=60, line_h=60, top=0, center_x=0, stroke=0,
                         impose=True)
    petits = [typeset.Fit(lines=["B"], size=20, line_h=20, top=0, center_x=0, stroke=0)
              for _ in range(3)]
    typeset.harmonize([impose] + petits, typeset._cfg(None))

    assert impose.harmonise_vers is None, "la taille choisie est intouchable"


# --------------------------------------------------------------------------- #
# La taille SEULE — imposer un corps sans imposer un cadre
# --------------------------------------------------------------------------- #

def test_une_taille_seule_change_le_corps(bulle):
    image, region, _style = bulle
    rapport: list[dict] = []
    _rendre(image, region, "Bonjour", layouts={0: {"taille": 18}}, rapport=rapport)
    entree = next(e for e in rapport if e["type"] == "bulle")
    assert entree["taille"] == 18 and entree["repli"] == "mise_en_page"


def _losange():
    """Un ballon en LOSANGE : sa bbox est deux fois plus large que lui à mi-hauteur.

    Une ellipse ne suffit pas à départager les deux implémentations — elle remplit assez sa
    boîte pour qu'un texte centré tienne pareil des deux côtés. Il faut une forme dont les
    coins sont franchement vides pour que la largeur disponible, donc le nombre de lignes,
    dise d'où vient le profil."""
    cx = (BOX[0] + BOX[2]) // 2
    cy = (BOX[1] + BOX[3]) // 2
    sommets = [(cx, BOX[1]), (BOX[2], cy), (cx, BOX[3]), (BOX[0], cy)]
    image = Image.new("RGB", TAILLE, (200, 200, 200))
    ImageDraw.Draw(image).polygon(sommets, fill=(255, 255, 255), outline=(0, 0, 0))
    masque = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(masque).polygon(sommets, fill=255)
    return image, BubbleRegion(bbox=BOX, mask=np.asarray(masque) > 127, score=0.9, cls=0)


def _lignes(image, region, texte, layouts):
    rapport: list[dict] = []
    _rendre(image, region, texte, layouts=layouts, rapport=rapport)
    return next(e for e in rapport if e["type"] == "bulle")["lignes"]


def test_une_taille_seule_n_est_pas_un_rect_deguise():
    """**Le test qui justifie que `rect` soit optionnel.**

    `style_impose` remplace l'intérieur du ballon par un RECTANGLE PLEIN. Si l'implémentation
    fabriquait ce rectangle depuis la bbox pour la seule raison qu'on veut changer le corps, le
    texte disposerait soudain de toute la largeur jusqu'aux coins — sur un losange, deux lignes
    au lieu de quatre, écrites par-dessus le contour dessiné. À corps ÉGAL, le découpage doit
    rester celui du masque."""
    image, region = _losange()
    texte = "Bonjour tout le monde et bien le bonsoir"
    sans_rect = _lignes(image, region, texte, {0: {"taille": 24}})
    avec_rect = _lignes(image, region, texte, {0: {"rect": list(BOX), "taille": 24}})
    assert sans_rect > avec_rect, ("imposer la taille seule a élargi la zone d'habillage : "
                                   "un rectangle a été fabriqué en douce")
    assert sans_rect == _lignes(image, region, texte, {0: {"taille": 24, "ancre": "libre"}})


def test_une_taille_seule_survit_a_l_harmonisation(bulle):
    """Même garantie que pour une taille posée avec un rectangle : `fit.impose` protège."""
    image, region, _style = bulle
    rapport: list[dict] = []
    _rendre(image, region, "Oui", layouts={0: {"taille": 52}}, rapport=rapport)
    entree = next(e for e in rapport if e["type"] == "bulle")
    assert entree["taille"] == 52


def test_une_taille_seule_intenable_retombe_sur_la_recherche(bulle):
    """Une préférence forte, pas une consigne suicide — comme pour un rectangle trop petit."""
    image, region, _style = bulle
    rapport: list[dict] = []
    _rendre(image, region, "Une réplique nettement plus longue que prévu, vraiment très longue "
                           "et qui ne tiendra jamais à ce corps-là",
            layouts={0: {"taille": 60}}, rapport=rapport)
    assert any(e["type"] == "mise_en_page_abandonnee" for e in rapport)
    entree = next(e for e in rapport if e["type"] == "bulle")
    assert entree["repli"] != "mise_en_page"


def test_preparer_contenu_est_ce_que_typeset_dessine():
    """Le chemin rapide de l'éditeur passe par `preparer_contenu` ; s'il divergeait de
    `typeset_page` sur la casse, taper montrerait autre chose que ce qui sera écrit."""
    contenu, _police, _subs, _sup = typeset.preparer_contenu(
        "Bonjour", typeset._cfg({"majuscules": True}), None)
    assert contenu == "BONJOUR"
