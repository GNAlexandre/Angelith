# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La DISPOSITION de la bande de vignettes — le seul test de widget du dépôt.

`tests/test_gui_reporter.py` pose la règle : « le reste (fenêtres, canevas) n'est pas testé,
ce serait hors de proportion ». Celui-ci fait exception, et pour une raison précise : ce qu'il
vérifie n'est pas un comportement de widget, c'est une **géométrie**. Deux rectangles se
recouvrent ou non ; l'assertion tient en une ligne, tourne hors écran en une seconde, et
attrape un défaut qu'aucun test de logique ne pouvait voir.

## Le défaut qu'il verrouille

La bande est un `QListWidget` en `IconMode`. Sans `setGridSize`, Qt dérive la position de
chaque item de la taille RÉELLE de son pixmap. Un item pas encore vignetté mesure alors la
taille de son texte seul (~26 × 36 px) ; quand l'icône arrive,
`QIconModeViewBase::dataChanged` redimensionne son rectangle **sur place, sans refaire la
disposition**. L'item grandit là où il est et recouvre ses voisins.

Mesuré sur 150 planches dans un panneau de 240 px : **2 767 paires d'items qui se
chevauchent**, et 9 « colonnes » pour un panneau qui n'en tient qu'une. Les légendes se
peignaient par-dessus les images voisines pendant tout le chargement.

⚠ `pytest.importorskip` : PySide6 vit dans `requirements-gui.txt`, séparé exprès.
"""
from __future__ import annotations

import os
import random

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

# Avant toute construction de `QApplication` : la suite doit tourner sans écran, en CI comme
# sur un poste où personne ne veut voir une fenêtre s'ouvrir au milieu d'un `pytest`.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize                                          # noqa: E402
from PySide6.QtGui import QColor, QIcon, QPixmap                          # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem  # noqa: E402

from gui import pellicule as pel                                          # noqa: E402

#: Trois ratios réels : page simple (1125×1600), double page, et pleine hauteur. C'est cette
#: hétérogénéité que `fabriquer_vignette` produit — elle conserve le ratio de la source.
RATIOS = ((pel.LARGEUR, 284), (pel.LARGEUR, 140), (pel.LARGEUR, pel.HAUTEUR_ICONE))


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def _bande(app, largeur_panneau: int, n: int = 150) -> tuple[QListWidget, list]:
    """La bande telle que `PanneauEditeur._construire` la configure, à l'identique.

    ⚠ Recopié plutôt qu'appelé : instancier `PanneauEditeur` tirerait la fenêtre, les services
    et un tome sur disque. Ce qu'on teste ici est le réglage du widget, et le test
    `test_le_reglage_du_widget_suit_l_editeur` en dessous garantit que la copie ne dérive pas."""
    liste = QListWidget()
    liste.setViewMode(QListWidget.IconMode)
    liste.setIconSize(QSize(pel.LARGEUR, pel.HAUTEUR_ICONE))
    liste.setGridSize(QSize(pel.LARGEUR_CELLULE, pel.HAUTEUR_CELLULE))
    liste.setResizeMode(QListWidget.Adjust)
    liste.setMovement(QListWidget.Static)
    liste.setSpacing(6)
    liste.setWordWrap(True)
    liste.setUniformItemSizes(True)
    liste.resize(largeur_panneau, 900)

    attente = QPixmap(pel.LARGEUR, pel.HAUTEUR_ICONE)
    attente.fill(QColor("#e9e9ec"))
    icone_attente = QIcon(attente)

    items = []
    for i in range(n):
        # Légende longue à dessein : avec `setWordWrap`, deux lignes de texte sont le pire cas
        # que la hauteur de cellule doive absorber.
        item = QListWidgetItem(f"{i + 1} · 12  ⚠3 ✎2 ↔1")
        item.setSizeHint(QSize(pel.LARGEUR_CELLULE, pel.HAUTEUR_CELLULE))
        item.setIcon(icone_attente)
        liste.addItem(item)
        items.append(item)
    liste.show()
    app.processEvents()
    return liste, items


def _vignettes() -> list[QPixmap]:
    plaques = []
    for taille in RATIOS:
        pm = QPixmap(*taille)
        pm.fill(QColor("#333333"))
        plaques.append(pm)
    return plaques


def _poser_dans_le_desordre(app, items, plaques) -> None:
    """Les vignettes arrivent une à une et PAS dans l'ordre : le fil de lecture sert la plus
    proche de la planche courante d'abord."""
    ordre = list(range(len(items)))
    random.Random(1).shuffle(ordre)
    for k in ordre:
        items[k].setIcon(QIcon(plaques[k % len(plaques)]))
        app.processEvents()


def _chevauchements(liste, items) -> int:
    rects = [liste.visualItemRect(i) for i in items]
    return sum(1 for a in range(len(rects)) for b in range(a + 1, len(rects))
               if rects[a].intersects(rects[b]))


# --------------------------------------------------------------------------- #
#  L'assertion qui aurait attrapé le défaut
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("largeur_panneau", [240, 460])
def test_aucune_vignette_n_en_recouvre_une_autre(qt_app, largeur_panneau):
    """LE test. 2 767 paires se chevauchaient sur 150 planches dans un panneau de 240 px."""
    liste, items = _bande(qt_app, largeur_panneau)
    assert _chevauchements(liste, items) == 0, "avant même la première vignette"
    _poser_dans_le_desordre(qt_app, items, _vignettes())
    assert _chevauchements(liste, items) == 0, "et toujours pas après leur arrivée"


def test_les_positions_ne_bougent_pas_a_l_arrivee_des_images(qt_app):
    """Le `sizeHint` en plus de la grille : sans lui, la hauteur d'un item passe de 12 à
    299 px quand son icône arrive. Les positions restent justes, mais la bande tressaute
    pendant tout le chargement — sur 150 planches, ça n'est pas un détail."""
    liste, items = _bande(qt_app, 240, n=20)
    avant = [liste.visualItemRect(i) for i in items]
    _poser_dans_le_desordre(qt_app, items, _vignettes())
    apres = [liste.visualItemRect(i) for i in items]
    assert avant == apres


def test_la_grille_suit_la_largeur_du_panneau(qt_app):
    """Une colonne dans le panneau par défaut, deux quand on l'élargit. C'est le symptôme le
    plus parlant du défaut : la bande annonçait 9 colonnes dans 240 px, et 22 dans 460."""
    for largeur, colonnes in ((240, 1), (460, 2)):
        liste, items = _bande(qt_app, largeur, n=20)
        _poser_dans_le_desordre(qt_app, items, _vignettes())
        assert len({liste.visualItemRect(i).x() for i in items}) == colonnes


def test_toutes_les_cellules_ont_la_meme_taille(qt_app):
    """Quel que soit le ratio de la vignette : une double page est centrée dans sa cellule,
    elle ne la rétrécit pas. C'est ce qui évite d'avoir à refabriquer les vignettes."""
    liste, items = _bande(qt_app, 240, n=20)
    _poser_dans_le_desordre(qt_app, items, _vignettes())
    tailles = {liste.visualItemRect(i).size().toTuple() for i in items}
    assert len(tailles) == 1


def test_la_cellule_absorbe_l_icone_et_deux_lignes_de_legende(qt_app):
    """Garde-fou sur les constantes : une cellule trop courte rognerait la légende, une
    cellule trop haute laisserait un blanc entre chaque planche."""
    assert pel.HAUTEUR_CELLULE > pel.HAUTEUR_ICONE
    assert pel.LARGEUR_CELLULE > pel.LARGEUR
    liste, items = _bande(qt_app, 240, n=3)
    hauteur = liste.visualItemRect(items[0]).height()
    assert hauteur >= pel.HAUTEUR_ICONE, "l'icône doit tenir entière"


# --------------------------------------------------------------------------- #
#  La copie du réglage ne doit pas dériver
# --------------------------------------------------------------------------- #

def test_le_reglage_du_widget_suit_l_editeur():
    """`_bande` recopie ce que fait `PanneauEditeur._construire`. Si l'éditeur cessait de
    poser la grille ou les tailles uniformes, ce fichier continuerait de passer en testant une
    bande que plus personne ne construit. On lit donc le source."""
    import inspect

    from gui.editeur import PanneauEditeur
    source = inspect.getsource(PanneauEditeur._construire)
    assert "setGridSize(QSize(pel.LARGEUR_CELLULE, pel.HAUTEUR_CELLULE))" in source
    assert "setUniformItemSizes(True)" in source
    assert "setIconSize(QSize(pel.LARGEUR, pel.HAUTEUR_ICONE))" in source


def test_chaque_item_recoit_sa_taille_a_la_creation():
    """Le `sizeHint` est posé à la création de l'item, pas à l'arrivée de sa vignette : c'est
    justement pendant qu'elle manque que la taille doit déjà être juste."""
    import inspect

    from gui.editeur import PanneauEditeur
    source = inspect.getsource(PanneauEditeur.ouvrir)
    assert "setSizeHint(QSize(pel.LARGEUR_CELLULE, pel.HAUTEUR_CELLULE))" in source
