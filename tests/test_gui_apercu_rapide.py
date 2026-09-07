# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le chemin rapide mono-bulle — ré-habiller UNE réplique sans recomposer la planche.

Composer un aperçu coûte 1,37 s en médiane : l'ouverture du scan d'origine (qui peut extraire
une archive CBZ entière) et `clean.analyze_regions`. C'est acceptable pour changer de planche,
et rédhibitoire pour suivre la frappe ou le tirage d'une poignée. `gui.apercu.recomposer_bulle`
réutilise les styles déjà mesurés et ne refait que le lettrage d'une bulle.

Ce que ces tests protègent :

- **la fidélité** — le chemin rapide doit produire, au pixel près, ce que produit le chemin
  complet. Un aperçu « à peu près » serait pire que pas d'aperçu : on corrigerait une mise en
  page qui n'existe pas ;
- **le poids** — les styles entrent dans le cache LRU, et un `BubbleStyle` brut porte deux
  masques pleine page ;
- **le repli** — un aperçu pas encore composé ne doit rien casser, juste ne pas accélérer.

⚠ Aucun import de PySide6 : `gui/apercu.py` ne connaît que PIL et `manga`, et doit rester
testable sans la dépendance graphique, qui est optionnelle.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from gui import apercu as apercu_mod
from manga import checkpoints, clean
from manga.detection import BubbleRegion

TAILLE = (400, 600)
BOX = (60, 60, 340, 300)


def _planche() -> Image.Image:
    img = Image.new("RGB", TAILLE, (200, 200, 200))
    ImageDraw.Draw(img).ellipse(list(BOX), fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    # Du « japonais » à effacer : sans lui, la planche nettoyée serait identique à la source
    # et l'on ne saurait pas si le nettoyage a eu lieu.
    ImageDraw.Draw(img).rectangle([140, 140, 260, 200], fill=(0, 0, 0))
    return img


def _region() -> BubbleRegion:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse(list(BOX), fill=255)
    return BubbleRegion(bbox=BOX, mask=np.asarray(m) > 127, score=0.9, cls=0)


@pytest.fixture
def planche(tmp_path):
    """Une planche à UNE seule bulle, cache complet, et son aperçu composé.

    ⚠ Une seule bulle, et c'est délibéré : `typeset.harmonize` ramène les bulles trop grandes
    vers la médiane de la planche, ce que le chemin rapide ne peut pas calculer sur une bulle
    isolée. Sur une planche à une bulle, l'harmonisation est inopérante — les deux chemins
    doivent donc coïncider **exactement**, et c'est ce que vérifie le test central."""
    ckpt = tmp_path / "page_0001"
    source = _planche()
    source.save(tmp_path / "source.png")
    region = _region()
    checkpoints.save_regions(ckpt, [region], TAILLE)
    checkpoints.save_ocr(ckpt, ["アアア"])

    chemin_clean = tmp_path / "clean.png"
    clean.clean_bubbles(source, [region]).save(chemin_clean)
    return ckpt, chemin_clean, tmp_path / "source.png"


def _composer(planche, textes, layouts=None):
    ckpt, chemin_clean, source = planche
    return apercu_mod.composer(ckpt, chemin_clean, source, textes=textes, font_path=None,
                               cfg_typeset=None, layouts=layouts)


def _pixels(calque):
    return np.asarray(calque.image.convert("RGBA"))


# --------------------------------------------------------------------------- #
# La forme compacte
# --------------------------------------------------------------------------- #

def _style():
    return clean.analyze_bubble(_planche(), _region(), None)


def test_compacter_puis_deplier_rend_le_meme_interieur():
    """Bit à bit. C'est la seule façon d'être sûr que `_profil` mesurera la même chose, donc
    que l'habillage sera le même."""
    style = _style()
    assert np.array_equal(apercu_mod.deplier(apercu_mod.compacter(style)).interior,
                          style.interior)


def test_compacter_conserve_les_scalaires_du_lettrage():
    style = _style()
    rendu = apercu_mod.deplier(apercu_mod.compacter(style))
    assert rendu.text_color == style.text_color
    assert rendu.background == style.background
    assert rendu.mode == style.mode and rendu.center_x == style.center_x
    assert rendu.inverted == style.inverted and rendu.ok == style.ok


def test_la_forme_compacte_pese_bien_moins_que_le_masque():
    """Le chiffre qui justifie l'existence de `StyleCompact` : les styles entrent dans un cache
    plafonné à 120 Mo, et un `interior` pleine page pèse quelques mégaoctets à lui seul.

    Deux gains se composent, et seul le premier est visible ici : l'empaquetage à 1 bit (×8,
    garanti quelle que soit la planche) et le recadrage (proportionnel au vide autour de la
    bulle). Sur cette planche de test la bulle couvre presque toute la page, donc le recadrage
    ne rend presque rien ; sur un scan 1600×2300 portant dix bulles, c'est lui qui fait passer
    74 Mo à ~150 ko."""
    style = _style()
    compact = apercu_mod.compacter(style)
    assert compact.octets < style.interior.nbytes / 8


def test_le_recadrage_paie_quand_la_bulle_est_petite():
    """Le second gain, isolé : à masque égal, une planche plus grande ne coûte pas plus cher.
    C'est ce qui borne le poids des styles dans le cache."""
    petit = np.zeros((2300, 1600), dtype=bool)
    petit[900:1100, 700:900] = True
    style = clean.BubbleStyle(
        bbox=(700, 900, 900, 1100), interior=petit, background=(255, 255, 255),
        background_luma=255.0, text_color=(0, 0, 0), inverted=False, uniformity=1.0,
        erode_radius=0, mode="masque", center_x=800, ok=True)
    assert apercu_mod.compacter(style).octets < petit.nbytes / 100


def test_le_masque_de_texte_est_jete():
    """Seul `clean.clean_bubbles` lit `text_mask` ; le lettrage ne le regarde jamais. Le garder
    doublerait le poids pour rien — et un style déplié ne doit pas repartir vers le nettoyage."""
    assert apercu_mod.deplier(apercu_mod.compacter(_style())).text_mask is None


def test_un_style_vide_se_compacte_sans_lever():
    """Les régions non-bulle reçoivent un style `ok=False` à masque vide, pour que la liste
    reste alignée par position. Elles passent par ici comme les autres."""
    style = _style()
    vide = apercu_mod.compacter(
        clean.BubbleStyle(bbox=(0, 0, 0, 0), interior=np.zeros(TAILLE[::-1], dtype=bool),
                          background=(255, 255, 255), background_luma=255.0,
                          text_color=(0, 0, 0), inverted=False, uniformity=0.0,
                          erode_radius=0, mode="aucun", center_x=0, ok=False))
    assert vide.octets == 0
    assert not apercu_mod.deplier(vide).interior.any()
    assert apercu_mod.compacter(style).octets > 0


# --------------------------------------------------------------------------- #
# Le chemin rapide
# --------------------------------------------------------------------------- #

def test_composer_conserve_les_styles(planche):
    vue = _composer(planche, ["Bonjour"])
    assert set(vue.styles) == {0}
    assert vue.cfg_typeset is None and vue.font_path is None


def test_les_styles_couvrent_aussi_une_bulle_sans_calque(planche):
    """⚠ Ils viennent d'`analyze_regions`, pas de `resultat.fits` : ce dernier ne contient que
    les bulles DESSINÉES. Une bulle sans calque n'aurait donc pas de style — et c'est justement
    celle où l'utilisateur va se mettre à taper.

    Une bulle sans source japonaise ne reçoit même pas le `marqueur_vide` : elle est vide à bon
    droit, et n'a aucun fit. C'est le cas le plus dépouillé, donc le plus révélateur."""
    ckpt, _clean, _source = planche
    checkpoints.save_ocr(ckpt, [""])
    vue = _composer(planche, [""])

    assert vue.calques == [], "aucun calque : c'est bien le cas que l'on veut tester"
    assert set(vue.styles) == {0}
    calque = apercu_mod.recomposer_bulle(vue, 0, "Enfin une réplique")
    assert calque is not None and calque.image.getbbox() is not None


def test_recomposer_donne_le_meme_calque_que_composer(planche):
    """**Le test central.**

    Le pendant de `test_manga_rendu.py::test_les_deux_chemins_donnent_la_meme_image`, appliqué
    au chemin rapide. S'il tombe, c'est que le relettrage en direct a divergé du lettrage réel,
    et l'éditeur montre alors une mise en page que le pipeline n'écrira pas."""
    vue = _composer(planche, ["Bonjour"])
    complet = vue.calques[0]
    rapide = apercu_mod.recomposer_bulle(_composer(planche, [""]), 0, "Bonjour")

    assert rapide is not None
    assert (rapide.x, rapide.y) == (complet.x, complet.y)
    assert rapide.rect == complet.rect and rapide.taille == complet.taille
    assert np.array_equal(_pixels(rapide), _pixels(complet))


def test_recomposer_suit_le_texte_tape(planche):
    """La frappe en direct : deux textes différents doivent donner deux calques différents,
    sans repasser par la composition complète."""
    vue = _composer(planche, ["Bonjour"])
    a = apercu_mod.recomposer_bulle(vue, 0, "Bonjour")
    b = apercu_mod.recomposer_bulle(vue, 0, "Bonsoir tout le monde")
    assert a is not None and b is not None
    assert not np.array_equal(_pixels(a), _pixels(b))


def test_recomposer_avec_une_taille_impose_le_corps(planche):
    vue = _composer(planche, ["Bonjour"])
    calque = apercu_mod.recomposer_bulle(vue, 0, "Bonjour", taille=17)
    assert calque is not None and calque.taille == 17


def test_une_taille_intenable_ne_retombe_pas_sur_la_recherche(planche):
    """⚠ Renoncer, plutôt que sauter à un autre corps. Sinon le réglage deviendrait
    impilotable : on monte d'un cran, le texte redescend tout seul à une valeur qui n'est pas
    celle affichée. L'appelant garde le calque précédent, et la composition complète appliquera
    le repli documenté."""
    vue = _composer(planche, ["Bonjour"])
    long_texte = "Une réplique nettement plus longue que prévu, vraiment très longue"
    assert apercu_mod.recomposer_bulle(vue, 0, long_texte, taille=60) is None


def test_recomposer_avec_un_rect_deplace_le_calque_et_garde_le_corps(planche):
    """Déplacer un bloc ne change pas son corps — la promesse d'`entree_mise_en_page`, que
    l'éditeur ne tenait pas faute d'un attribut jamais assigné."""
    vue = _composer(planche, ["Bonjour"])
    corps = vue.calques[0].taille
    cible = (80, 70, 330, 290)           # même gabarit, déplacé : le corps doit y tenir
    calque = apercu_mod.recomposer_bulle(vue, 0, "Bonjour", rect=cible)

    assert calque is not None
    assert calque.taille == corps
    assert calque.rect == cible


def test_un_rect_trop_petit_retombe_sur_la_recherche(planche):
    """Une mise en page enregistrée est une préférence forte, pas une consigne suicide — le
    même repli que `typeset_page`, et pour la même raison : mieux vaut une réplique au mauvais
    corps qu'une réplique disparue."""
    vue = _composer(planche, ["Bonjour"])
    etroit = apercu_mod.recomposer_bulle(vue, 0, "Bonjour", rect=(100, 180, 300, 280))
    assert etroit is not None and etroit.taille < vue.calques[0].taille


def test_recomposer_avec_un_masque_suit_la_nouvelle_forme(planche):
    """Le geste des poignées : le masque étiré est connu avant d'être écrit, et le texte doit
    se ré-habiller dedans pendant qu'on tire."""
    vue = _composer(planche, ["Bonjour tout le monde"])
    etroit = np.zeros(TAILLE[::-1], dtype=bool)
    etroit[80:280, 140:260] = True
    calque = apercu_mod.recomposer_bulle(vue, 0, "Bonjour tout le monde", masque=etroit)

    assert calque is not None
    assert calque.rect == (140, 80, 260, 280)
    # Le calque est découpé au nouveau masque : il ne peut pas être plus large que lui.
    assert calque.image.width <= 120 and (calque.x, calque.y) == (140, 80)
    large = apercu_mod.recomposer_bulle(vue, 0, "Bonjour tout le monde")
    assert large is not None and large.image.width > calque.image.width


def test_recomposer_sans_style_rend_none(planche):
    """Le repli gracieux : cache froid, aperçu pas encore composé. Le rectangle et les poignées
    suivent quand même à pleine cadence ; seul le texte attend. Aucune erreur, aucun message —
    un geste qui échoue bruyamment serait pire que lent."""
    vue = _composer(planche, ["Bonjour"])
    vue.styles = {}
    assert apercu_mod.recomposer_bulle(vue, 0, "Bonjour") is None


def test_recomposer_un_index_inconnu_rend_none(planche):
    vue = _composer(planche, ["Bonjour"])
    assert apercu_mod.recomposer_bulle(vue, 7, "Bonjour") is None


def test_recomposer_un_texte_vide_rend_none(planche):
    """Une bulle vidée ne reçoit pas un calque blanc : elle en perd un. L'appelant retire
    l'item plutôt que d'afficher une trace du texte précédent."""
    vue = _composer(planche, ["Bonjour"])
    assert apercu_mod.recomposer_bulle(vue, 0, "   ") is None


def test_recomposer_applique_la_casse_comme_le_rendu(planche):
    """`preparer_contenu` est partagé avec `typeset_page` : si le chemin rapide en divergeait,
    taper montrerait une casse que le rendu final ne produira pas."""
    ckpt, chemin_clean, source = planche
    cfg = {"majuscules": True}
    vue = apercu_mod.composer(ckpt, chemin_clean, source, textes=["Bonjour"],
                              font_path=None, cfg_typeset=cfg, layouts=None)
    rapide = apercu_mod.recomposer_bulle(vue, 0, "Bonjour")
    assert rapide is not None
    assert np.array_equal(_pixels(rapide), _pixels(vue.calques[0]))


# --------------------------------------------------------------------------- #
# L'entrée de `mise_en_page.json`
# --------------------------------------------------------------------------- #

def test_entree_mise_en_page_porte_la_taille_du_calque(planche):
    vue = _composer(planche, ["Bonjour"])
    entree = apercu_mod.entree_mise_en_page(vue.calques[0], rect=(1.4, 2.6, 3.0, 4.0))
    assert entree == {"ancre": "libre", "rect": [1, 3, 3, 4],
                      "taille": vue.calques[0].taille}


def test_entree_mise_en_page_sans_rect_est_valide():
    """Imposer un corps sans imposer de cadre est un geste légitime, et `load_mise_en_page`
    doit accepter l'entrée qui en sort."""
    entree = apercu_mod.entree_mise_en_page(None, taille=22)
    assert entree == {"ancre": "libre", "taille": 22}


def test_entree_mise_en_page_relue_telle_quelle(tmp_path, planche):
    """L'aller-retour complet : ce que l'éditeur construit doit survivre au disque."""
    vue = _composer(planche, ["Bonjour"])
    entree = apercu_mod.entree_mise_en_page(vue.calques[0], rect=(10, 20, 110, 90))
    checkpoints.save_mise_en_page(tmp_path, {0: entree})
    assert checkpoints.load_mise_en_page(tmp_path) == {0: entree}
