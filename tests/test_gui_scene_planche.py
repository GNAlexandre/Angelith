# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La manipulation directe sur le canevas — attraper, déplacer, redimensionner.

## Le défaut que ces tests verrouillent

`ScenePlanche.mousePressEvent` n'appelait **jamais** `super()` en mode « Choisir ». Or c'est
l'implémentation parente qui pose le `mouseGrabberItem` : sans elle, aucun item ne reçoit le
press, `ItemIsMovable` n'est qu'une décoration, et pas un seul `mouseMoveEvent` d'item n'arrive
jamais. Les blocs de texte n'étaient pas « difficiles à attraper » — ils n'étaient jamais saisis
du tout. S'y ajoutait le `shapeMode` par défaut (`MaskShape`), qui rendait attrapables les seuls
pixels opaques des glyphes : même corrigé, il aurait fallu cliquer pile sur un trait de lettre.

Deux défauts, deux tests, et ils ne se remplacent pas : le premier vérifie qu'un grab est posé,
le second qu'il l'est aussi **entre** les lettres.

## Ce que les tests protègent en plus

- **la sélection** — laisser passer le geste aux items ne doit pas court-circuiter `choisir()` ;
- **les poignées** — taille constante à l'écran, présentes seulement quand c'est légitime ;
- **le grab pendant un rafraîchissement** — remplacer un calque ne doit pas détruire son item ;
- **les modes de dessin** — rectangle, ellipse, redessiner, scinder émettent toujours pareil.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

from PIL import Image                                                        # noqa: E402
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt                       # noqa: E402
from PySide6.QtGui import QPixmap                                            # noqa: E402
from PySide6.QtWidgets import (QApplication, QGraphicsSceneMouseEvent,       # noqa: E402
                               QGraphicsView)

from gui import scene_planche as sp                                          # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    """Une `QApplication` — des widgets, donc pas une simple `QCoreApplication`."""
    app = QApplication.instance() or QApplication([])
    yield app


class _Bulle:
    """Le minimum que `ScenePlanche.charger` attend d'une bulle."""

    def __init__(self, index, bbox, affichee="Bonjour", manuelle=None):
        self.index, self.bbox = index, bbox
        self.affichee, self.manuelle = affichee, manuelle


class _Calque:
    """Un `CalqueBulle` factice — l'image est ce qui compte, pas d'où elle vient."""

    def __init__(self, index, rect, taille=20, opaque=False):
        x0, y0, x1, y1 = rect
        # Par défaut TRANSPARENT : c'est le cas qui piégeait `MaskShape`. Un pixmap opaque
        # aurait masqué le défaut, puisque n'importe quel clic serait tombé sur un pixel plein.
        alpha = 255 if opaque else 0
        self.image = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, alpha))
        self.index, self.rect, self.taille = index, rect, taille
        self.x, self.y = x0, y0
        self.deborde = False


@pytest.fixture
def scene(qt_app):
    """Deux bulles bien séparées, avec leurs calques de texte posés."""
    s = sp.ScenePlanche()
    s.setSceneRect(QRectF(0, 0, 400, 600))
    s.charger(None, [_Bulle(0, (50, 50, 250, 200)), _Bulle(1, (50, 300, 250, 450))])
    s.poser_calques([_Calque(0, (60, 60, 240, 190)), _Calque(1, (60, 310, 240, 440))])
    vue = QGraphicsView(s)
    vue.resize(400, 600)
    s._vue_de_test = vue                       # garde une référence : sans vue, pas de zoom
    return s


def _press(scene, point, *, modifiers=Qt.NoModifier):
    """Un press de souris tel que `QGraphicsView` le fabrique.

    ⚠ `buttonDownScenePos` doit être renseigné : les poignées s'en servent pour mesurer le
    déplacement, et un événement construit à la main le laisse à zéro."""
    ev = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.GraphicsSceneMousePress)
    ev.setScenePos(QPointF(*point))
    ev.setButton(Qt.LeftButton)
    ev.setButtons(Qt.LeftButton)
    ev.setModifiers(modifiers)
    ev.setButtonDownScenePos(Qt.LeftButton, QPointF(*point))
    scene.mousePressEvent(ev)
    return ev


def _bouger(item, depart, arrivee):
    ev = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.GraphicsSceneMouseMove)
    ev.setScenePos(QPointF(*arrivee))
    ev.setButtons(Qt.LeftButton)
    ev.setButtonDownScenePos(Qt.LeftButton, QPointF(*depart))
    ev.setLastScenePos(QPointF(*depart))
    item.mouseMoveEvent(ev)
    return ev


def _relacher(item, depart, arrivee):
    ev = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.GraphicsSceneMouseRelease)
    ev.setScenePos(QPointF(*arrivee))
    ev.setButton(Qt.LeftButton)
    ev.setButtonDownScenePos(Qt.LeftButton, QPointF(*depart))
    item.mouseReleaseEvent(ev)
    return ev


def _capter(signal):
    recu = []
    signal.connect(lambda *args: recu.append(args))
    return recu


# --------------------------------------------------------------------------- #
# Attraper un bloc de texte — le défaut d'origine
# --------------------------------------------------------------------------- #

def test_un_clic_sur_un_bloc_de_texte_pose_le_grab(scene):
    """**Le test du bug.** Sans `super().mousePressEvent`, Qt ne désigne aucun
    `mouseGrabberItem` et le déplacement ne peut littéralement pas commencer."""
    _press(scene, (150, 120))
    assert isinstance(scene.mouseGrabberItem(), sp.CalqueTexteItem)


def test_le_bloc_est_attrapable_hors_des_glyphes(scene):
    """**Le second défaut**, indépendant du premier. Le pixmap d'un calque est TRANSPARENT
    partout sauf sur les traits de lettres ; avec le `MaskShape` par défaut, cliquer entre deux
    mots ou entre deux lignes ne saisissait rien. Le calque de ce test est entièrement
    transparent : seul `BoundingRectShape` peut l'attraper."""
    assert scene.calque(0).shapeMode() == sp.CalqueTexteItem.BoundingRectShape
    _press(scene, (150, 120))
    assert scene.mouseGrabberItem() is scene.calque(0)


def test_attraper_un_bloc_selectionne_sa_bulle(scene):
    """Sinon l'inspecteur montrerait une autre réplique que celle qu'on manipule."""
    recu = _capter(scene.zone_choisie)
    _press(scene, (150, 120))
    assert scene.index_courant == 0 and recu == [(0,)]


def test_un_clic_hors_de_tout_bloc_selectionne_encore_la_zone(scene):
    """Non-régression : laisser passer le geste aux items ne doit pas court-circuiter
    `choisir()`. ⚠ Un `ZoneItem` est `ItemIsSelectable`, donc il accepte le press lui aussi —
    se fier à `event.isAccepted()` aurait cassé la sélection."""
    recu = _capter(scene.zone_choisie)
    _press(scene, (55, 55))                    # dans la zone, hors du calque
    assert scene.index_courant == 0 and recu == [(0,)]


def test_un_clic_dans_le_vide_deselectionne(scene):
    recu = _capter(scene.zone_choisie)
    _press(scene, (350, 550))
    assert scene.index_courant == -1 and recu == [(-1,)]


def test_deplacer_un_bloc_emet_son_nouveau_rectangle(scene):
    item = scene.calque(0)
    _press(scene, (150, 120))
    recu = _capter(scene.texte_deplace)
    item.setPos(item.pos() + QPointF(30, 40))
    _relacher(item, (150, 120), (180, 160))

    assert len(recu) == 1
    index, rect = recu[0]
    assert index == 0 and (rect.left(), rect.top()) == (90.0, 100.0)


def test_un_clic_sans_deplacement_n_emet_rien(scene):
    """Un clic est une sélection, pas un déplacement d'un pixel : l'écrire dans
    `mise_en_page.json` marquerait la planche modifiée pour rien."""
    item = scene.calque(0)
    _press(scene, (150, 120))
    recu = _capter(scene.texte_deplace)
    _relacher(item, (150, 120), (150, 120))
    assert recu == []


def test_alt_fait_passer_le_geste_a_la_zone(scene):
    """Le bloc de texte couvre presque toute la bulle ; sans échappatoire, la zone qu'il
    recouvre serait inatteignable. ⚠ C'est le PRESS qui doit être ignoré — Qt ne propose le
    geste à l'item suivant qu'à ce moment-là."""
    scene.choisir(0)
    _press(scene, (150, 120), modifiers=Qt.AltModifier)
    assert isinstance(scene.mouseGrabberItem(), sp.ZoneItem)


def test_deplacer_la_zone_emet_sa_nouvelle_boite(scene):
    """⚠ Le point de saisie doit éviter DEUX choses : le bloc de texte (qui prendrait le geste)
    et les poignées (qui chevauchent les bords par construction — c'est voulu, cf.
    `test_les_poignees_sont_visables_par_dessus_le_cadre`). D'où cette marge droite."""
    zone = scene.zone(0)
    scene.choisir(0)
    recu = _capter(scene.zone_retaillee)
    _press(scene, (245, 100))
    assert scene.mouseGrabberItem() is zone
    zone.setPos(QPointF(20, 10))
    _relacher(zone, (245, 100), (265, 110))

    assert len(recu) == 1
    index, boite = recu[0]
    assert index == 0
    assert (boite.left(), boite.top(), boite.width()) == (70.0, 60.0, 200.0)


# --------------------------------------------------------------------------- #
# Les poignées
# --------------------------------------------------------------------------- #

def test_les_poignees_apparaissent_avec_la_selection(scene):
    assert scene._poignees == []
    scene.choisir(0)
    assert len(scene._poignees) == 8
    scene.choisir(-1)
    assert scene._poignees == []


def test_les_poignees_encadrent_la_zone(scene):
    scene.choisir(0)
    coins = {(p.ancre, (p.pos().x(), p.pos().y())) for p in scene._poignees}
    assert ("no", (50.0, 50.0)) in coins
    assert ("se", (250.0, 200.0)) in coins
    assert ("n", (150.0, 50.0)) in coins


def test_les_poignees_gardent_leur_taille_ecran_au_zoom(scene):
    """⚠ `ItemIgnoresTransformations` : le rect local est en pixels ÉCRAN. C'est ce qui répond
    à l'objection historique (« quatre pixels à attraper sur une planche affichée à 30 % »), et
    ce qui évite d'avoir à les repositionner à chaque changement de zoom."""
    scene.choisir(0)
    poignee = scene._poignees[0]
    assert poignee.flags() & sp.PoigneeItem.ItemIgnoresTransformations
    assert poignee.rect().width() == pytest.approx(sp._COTE_POIGNEE)

    vue = scene._vue_de_test
    for facteur in (0.3, 10.0):
        vue.resetTransform()
        vue.scale(facteur, facteur)
        largeur = poignee.deviceTransform(vue.viewportTransform()).mapRect(
            poignee.rect()).width()
        assert largeur == pytest.approx(sp._COTE_POIGNEE, abs=1.0)


def test_les_poignees_ne_sont_pas_enfants_de_la_zone(scene):
    """⚠ Le flag ignore aussi les transformations du PARENT : huit poignées enfants
    s'empileraient à l'origine de la zone."""
    scene.choisir(0)
    assert all(p.parentItem() is None for p in scene._poignees)


def test_tirer_une_poignee_redimensionne_pendant_le_geste(scene):
    scene.choisir(0)
    poignee = next(p for p in scene._poignees if p.ancre == "se")
    recu_pendant = _capter(scene.zone_en_cours)
    _press(scene, (250, 200))
    _bouger(poignee, (250, 200), (300, 260))

    assert recu_pendant, "rien n'a été émis pendant le geste"
    assert scene.zone(0).rect_scene().bottomRight() == QPointF(300, 260)


def test_tirer_une_poignee_n_emet_le_depot_qu_au_relachement(scene):
    scene.choisir(0)
    poignee = next(p for p in scene._poignees if p.ancre == "se")
    recu = _capter(scene.zone_retaillee)
    _press(scene, (250, 200))
    _bouger(poignee, (250, 200), (300, 260))
    assert recu == [], "l'écriture ne doit pas partir à chaque pixel parcouru"

    _relacher(poignee, (250, 200), (300, 260))
    assert len(recu) == 1 and recu[0][0] == 0
    assert recu[0][1].bottomRight() == QPointF(300, 260)


def test_une_poignee_du_coin_oppose_ne_bouge_que_ses_aretes(scene):
    scene.choisir(0)
    poignee = next(p for p in scene._poignees if p.ancre == "no")
    _press(scene, (50, 50))
    _bouger(poignee, (50, 50), (70, 80))

    boite = scene.zone(0).rect_scene()
    assert (boite.left(), boite.top()) == (70.0, 80.0)
    assert (boite.right(), boite.bottom()) == (250.0, 200.0)


def test_une_poignee_refuse_de_degenerer_la_boite(scene):
    """Tirer la poignée au-delà du bord opposé ne doit pas produire une zone d'un pixel :
    `etirer_masque` lèverait au dépôt, en plein geste, pour un geste qu'on voyait venir."""
    scene.choisir(0)
    poignee = next(p for p in scene._poignees if p.ancre == "se")
    _press(scene, (250, 200))
    _bouger(poignee, (250, 200), (52, 52))
    assert scene.zone(0).rect_scene().width() >= sp._TAILLE_MIN_TRACE


def test_les_poignees_sont_visables_par_dessus_le_cadre(scene):
    """Elles chevauchent le cadre de la zone par construction ; si celui-ci l'emportait, on ne
    pourrait jamais en attraper une."""
    scene.choisir(0)
    _press(scene, (250, 200))
    assert isinstance(scene.mouseGrabberItem(), sp.PoigneeItem)


# --------------------------------------------------------------------------- #
# Interaction coupée
# --------------------------------------------------------------------------- #

def test_aucune_poignee_quand_l_interaction_est_coupee(scene):
    """Le rendu aplati du pipeline, ou un run en cours : il n'y a rien à manipuler."""
    scene.choisir(0)
    scene.regler_interaction(False)
    assert scene._poignees == []

    scene.regler_interaction(True)
    assert len(scene._poignees) == 8


def test_interaction_coupee_le_clic_ne_fait_que_selectionner(scene):
    scene.regler_interaction(False)
    recu = _capter(scene.zone_choisie)
    _press(scene, (150, 120))
    assert scene.mouseGrabberItem() is None
    assert recu == [(0,)]


def test_interaction_coupee_la_zone_n_est_plus_mobile(scene):
    scene.regler_interaction(False)
    assert not (scene.zone(0).flags() & sp.ZoneItem.ItemIsMovable)


# --------------------------------------------------------------------------- #
# Remplacer un calque sans casser le geste
# --------------------------------------------------------------------------- #

def test_remplacer_un_calque_conserve_l_item(scene):
    """⚠ **Ce qui rend le relettrage en direct possible.** `poser_calques` retire TOUS les
    items ; l'appeler pendant un glisser détruirait celui qui tient le `mouseGrabberItem`, et
    le geste mourrait au premier rafraîchissement — sans erreur, sans trace, et sans que rien
    n'explique pourquoi le bloc décroche dès qu'on le bouge."""
    avant = scene.calque(0)
    _press(scene, (150, 120))
    assert scene.remplacer_calque(_Calque(0, (70, 70, 250, 200), taille=31))

    assert scene.calque(0) is avant, "l'item a été recréé : le grab est perdu"
    assert scene.mouseGrabberItem() is avant
    assert avant.taille == 31
    assert avant.rect_habillage == QRectF(70, 70, 180, 130)
    assert (avant.pos().x(), avant.pos().y()) == (70.0, 70.0)


def test_remplacer_un_calque_inconnu_ne_fait_rien(scene):
    """Le repli : une bulle sans calque (réplique vide) n'a rien à remplacer."""
    assert scene.remplacer_calque(_Calque(7, (0, 0, 10, 10))) is False


def test_poser_les_calques_porte_la_taille(scene):
    """La donnée que `_sur_texte_deplace` allait chercher dans un attribut inexistant."""
    scene.poser_calques([_Calque(0, (60, 60, 240, 190), taille=42)])
    assert scene.calque(0).taille == 42


# --------------------------------------------------------------------------- #
# Les modes de dessin ne sont pas cassés
# --------------------------------------------------------------------------- #

def _tracer(scene, depart, arrivee):
    _press(scene, depart)
    ev = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.GraphicsSceneMouseMove)
    ev.setScenePos(QPointF(*arrivee))
    scene.mouseMoveEvent(ev)
    fin = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.GraphicsSceneMouseRelease)
    fin.setScenePos(QPointF(*arrivee))
    scene.mouseReleaseEvent(fin)


def test_le_mode_rectangle_emet_toujours_sa_boite(scene):
    scene.mode = sp.MODE_RECTANGLE
    recu = _capter(scene.zone_dessinee)
    _tracer(scene, (300, 60), (380, 160))
    assert len(recu) == 1 and recu[0][1] == sp.MODE_RECTANGLE


def test_le_mode_ellipse_annonce_sa_forme(scene):
    scene.mode = sp.MODE_ELLIPSE
    recu = _capter(scene.zone_dessinee)
    _tracer(scene, (300, 60), (380, 160))
    assert len(recu) == 1 and recu[0][1] == sp.MODE_ELLIPSE


def test_le_mode_redessiner_vise_la_zone_choisie(scene):
    scene.choisir(1)
    scene.mode = sp.MODE_MODIFIER
    recu = _capter(scene.zone_modifiee)
    _tracer(scene, (60, 310), (240, 440))
    assert len(recu) == 1 and recu[0][0] == 1


def test_le_mode_scinder_emet_une_droite(scene):
    scene.choisir(0)
    scene.mode = sp.MODE_SCINDER
    recu = _capter(scene.coupe_dessinee)
    _tracer(scene, (60, 120), (240, 125))
    assert len(recu) == 1 and isinstance(recu[0][1], QLineF)


def test_un_trace_minuscule_reste_un_clic_maladroit(scene):
    scene.mode = sp.MODE_RECTANGLE
    recu = _capter(scene.zone_dessinee)
    _tracer(scene, (300, 60), (302, 62))
    assert recu == []
