# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le pane de navigation — ses trois modes, et **ce que voit quelqu'un qui n'a que le clavier**.

`tests/test_gui_destinations.py` vérifie la DÉCISION (`mode_pour_largeur`), sans écran. Ici on
vérifie que le widget la sert, et qu'il ne perd pas ce que le `PLAN-19` a livré :

- un `PARCOURS` explicite, comme les autres panneaux ;
- un `AccessibleName` par item, **qui survit au mode compact** où le texte visible disparaît ;
- l'état sélectionné annoncé autrement que par la couleur.

⚠ `QT_QPA_PLATFORM=offscreen` est posé avant toute construction de `QApplication`, comme dans
les autres fichiers d'interface : la suite doit tourner sans écran, en CI comme en local.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                                # noqa: E402
from PySide6.QtWidgets import QApplication                                   # noqa: E402

from gui import destinations as dst                                          # noqa: E402
from gui import theme                                                        # noqa: E402
from gui.navigation import PanneauNavigation                                 # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    theme.appliquer(app, theme.CLAIR)
    yield app


@pytest.fixture
def pane(qt_app):
    panneau = PanneauNavigation()
    yield panneau
    panneau.deleteLater()


# --------------------------------------------------------------------------- #
# La table arrive à l'écran
# --------------------------------------------------------------------------- #

def test_le_corps_et_le_pied_portent_ce_que_la_table_declare(pane):
    corps = [pane.liste.item(i).data(Qt.UserRole) for i in range(pane.liste.count())]
    pied = [pane.liste_pied.item(i).data(Qt.UserRole)
            for i in range(pane.liste_pied.count())]
    assert corps == [d.identifiant for d in dst.corps()]
    assert pied == [d.identifiant for d in dst.pied()]


def test_chaque_item_porte_une_icone_non_nulle(pane):
    """En mode COMPACT, l'icône est le seul libellé : une icône absente y rend la destination
    inatteignable à la souris."""
    for liste in (pane.liste, pane.liste_pied):
        for index in range(liste.count()):
            assert not liste.item(index).icon().isNull(), liste.item(index).data(Qt.UserRole)


def test_choisir_une_destination_l_emet_une_fois(pane):
    vues = []
    pane.choisie.connect(vues.append)
    pane.liste.setCurrentRow(2)
    assert vues == [dst.corps()[2].identifiant]


def test_selectionner_ne_reemet_pas(pane):
    """⚠ `setCurrentItem` réémet `currentItemChanged`, donc `choisie`, donc la fenêtre
    reviendrait ici — le même aller-retour de signal que `_restaurer_selection_de_tome`
    coupe côté tome."""
    vues = []
    pane.choisie.connect(vues.append)
    pane.selectionner("manga")
    assert vues == []
    assert pane.courante() == "manga"


def test_une_entree_de_pied_demande_son_action_et_ne_navigue_pas(pane):
    """« Réglages » ouvre un dialogue ; en faire une destination donnerait une navigation dont
    on ne saurait pas revenir."""
    pane.selectionner("manga")
    navigations, actions = [], []
    pane.choisie.connect(navigations.append)
    pane.demande_action.connect(actions.append)
    pane.liste_pied.itemClicked.emit(pane.liste_pied.item(0))
    assert actions == [dst.pied()[0].action]
    assert navigations == []
    assert pane.courante() == "manga"


def test_le_pied_n_est_pas_selectionnable(pane):
    """Deux destinations actives à la fois, dont une fausse — c'est ce que la sélection du
    pied afficherait."""
    from PySide6.QtWidgets import QAbstractItemView

    assert pane.liste_pied.selectionMode() == QAbstractItemView.NoSelection
    assert pane.liste.selectionMode() == QAbstractItemView.SingleSelection


def test_selectionner_une_entree_de_pied_ne_fait_rien(pane):
    pane.selectionner("manga")
    pane.selectionner("reglages")
    assert pane.courante() == "manga"


# --------------------------------------------------------------------------- #
# Les trois modes de largeur
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("largeur, mode", [(1520, dst.DEPLOYE), (800, dst.COMPACT),
                                           (500, dst.MINIMAL)])
def test_le_pane_suit_la_largeur_de_la_fenetre(pane, largeur, mode):
    assert pane.appliquer_largeur(largeur) == mode
    assert pane.mode() == mode


def test_le_mode_compact_retire_le_texte_mais_pas_le_nom_accessible(pane):
    """⚠ **Le point qu'on perd le plus facilement.** Sans `AccessibleTextRole`, un lecteur
    d'écran annoncerait un item VIDE dès que la fenêtre passe sous 1008 px."""
    pane.appliquer_largeur(800)
    for index in range(pane.liste.count()):
        item = pane.liste.item(index)
        assert item.text() == ""
        assert item.data(Qt.AccessibleTextRole), item.data(Qt.UserRole)
        assert item.toolTip()


def test_le_mode_deploye_rend_les_libelles(pane):
    pane.appliquer_largeur(800)
    pane.appliquer_largeur(1520)
    assert [pane.liste.item(i).text() for i in range(pane.liste.count())] == [
        d.libelle for d in dst.corps()]


def test_le_mode_minimal_garde_un_chemin_a_la_souris(pane):
    """« Le faire disparaître tout à fait laisserait une fenêtre sans aucun chemin de
    navigation à la souris — et la souris est le seul chemin qu'on n'a pas à apprendre. »"""
    pane.appliquer_largeur(500)
    assert pane.bouton_menu.isVisibleTo(pane)
    assert not pane.liste.isVisibleTo(pane)
    pane.bouton_menu.click()
    assert pane.liste.isVisibleTo(pane)
    assert pane.liste.item(0).text() == dst.corps()[0].libelle


def test_le_bouton_de_menu_existe_dans_les_trois_modes(pane):
    """« Le créer à la demande ferait de la bascule un moment où des widgets naissent, donc un
    moment où le parcours de tabulation change sous les doigts. »"""
    for largeur in (1520, 800, 500):
        pane.appliquer_largeur(largeur)
        assert pane.bouton_menu is not None


# --------------------------------------------------------------------------- #
# L31.8 — ce que voit quelqu'un qui n'a que le clavier
# --------------------------------------------------------------------------- #

def test_l_etat_selectionne_n_est_pas_annonce_QUE_par_la_couleur(pane):
    """Un état qui ne se lit qu'à la teinte est un état que 8 % des hommes ne lisent pas."""
    pane.selectionner("manga")
    for index in range(pane.liste.count()):
        item = pane.liste.item(index)
        actif = item.data(Qt.UserRole) == "manga"
        assert item.font().bold() is actif, item.data(Qt.UserRole)
        marque = item.data(Qt.AccessibleDescriptionRole) or ""
        assert bool(marque) is actif, item.data(Qt.UserRole)


def test_le_marqueur_accessible_dit_ce_qu_il_est(pane):
    from gui.navigation import MARQUE_ACTIVE

    pane.selectionner("retouche")
    item = next(pane.liste.item(i) for i in range(pane.liste.count())
                if pane.liste.item(i).data(Qt.UserRole) == "retouche")
    assert item.data(Qt.AccessibleDescriptionRole) == MARQUE_ACTIVE


def test_les_deux_listes_ont_un_nom_accessible(pane):
    assert pane.liste.accessibleName() == "Destinations"
    assert pane.liste_pied.accessibleName()
    assert pane.bouton_menu.accessibleName()


def test_le_pane_declare_son_parcours(pane):
    """« Le critère 6 du `PLAN-19` demande UN ordre explicite PAR PANNEAU, pas un par défaut
    qui se trouve juste. »"""
    from PySide6.QtWidgets import QWidget

    assert PanneauNavigation.PARCOURS == ("bouton_menu", "liste", "liste_pied")
    for nom in PanneauNavigation.PARCOURS:
        assert isinstance(getattr(pane, nom), QWidget), nom


def test_la_bascule_de_theme_redemande_les_icones(pane):
    """⚠ Un `QIcon` déjà rendu est un pixmap : aucune règle QSS ne l'atteint. Sans reprise
    explicite, le pane garderait les glyphes du thème précédent jusqu'au prochain lancement —
    le même défaut que la pellicule, au même endroit."""
    from gui import icones as ico

    theme.appliquer(QApplication.instance(), theme.SOMBRE)
    ico.oublier()
    pane.rafraichir_theme()
    for index in range(pane.liste.count()):
        assert not pane.liste.item(index).icon().isNull()
    theme.appliquer(QApplication.instance(), theme.CLAIR)


# --------------------------------------------------------------------------- #
#  Le pied du pane — lot 41
#
#  ⚠ Le pied porte DEUX sortes d'entrées, et le code n'en servait qu'une : « Réglages » a une
#  `action` (un dialogue), « Diagnostic » n'en a pas — c'est une PAGE depuis le lot 36.
#  Cliquer sur Diagnostic ne faisait donc RIEN, en silence.
# --------------------------------------------------------------------------- #

def test_le_pied_porte_bien_les_deux_sortes_d_entrees():
    """Si un jour les deux avaient une `action`, les tests suivants passeraient au vert sans
    rien prouver. On vérifie donc d'abord que le cas existe."""
    pied = dst.pied()
    assert any(d.action for d in pied), "aucune entrée à action : le test ne prouve rien"
    assert any(not d.action for d in pied), "aucune entrée-page : le test ne prouve rien"


def test_une_entree_de_pied_SANS_action_navigue(qt_app):
    """**Le défaut du lot 41.** Un clic qui ne produit rien passe pour une application
    cassée — c'est le reproche que `gui/depot.py` fait déjà au lâcher muet."""
    pane = PanneauNavigation()
    page = next(d for d in dst.pied() if not d.action)
    vus: list[str] = []
    pane.choisie.connect(vus.append)
    pane.liste_pied.itemClicked.emit(pane._items[page.identifiant])
    assert vus == [page.identifiant]
    assert pane.courante() == page.identifiant


def test_une_entree_de_pied_AVEC_action_ouvre_son_dialogue(qt_app):
    """Iso : « Réglages » continue d'ouvrir un dialogue, et ne navigue PAS."""
    pane = PanneauNavigation()
    avec = next(d for d in dst.pied() if d.action)
    actions: list[str] = []
    navigations: list[str] = []
    pane.demande_action.connect(actions.append)
    pane.choisie.connect(navigations.append)
    pane.liste_pied.itemClicked.emit(pane._items[avec.identifiant])
    assert actions == [avec.action]
    assert navigations == []
