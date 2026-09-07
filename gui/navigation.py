# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La navigation latérale — le pane, ses trois modes de largeur, et son accessibilité.

## Pourquoi latérale et pas trois onglets de plus

Fluent / WinUI `NavigationView` : navigation **latérale** de 5 à 10 destinations de premier
niveau d'importance égale, navigation **haute** en dessous de 5. Sept destinations plus deux
entrées de pied — hors de la fourchette des onglets. Et NN/g le dit autrement : un onglet est
un conteneur, pas une destination ; trois onglets qui portent des métiers différents forcent
l'utilisateur à deviner lequel « contient » ce qu'il veut faire.

## Ce que ce widget ne fait pas

Il ne construit aucune page, n'ouvre aucun tome et ne connaît pas la fenêtre. Il émet
`choisie(identifiant)` et `demande_action(identifiant)` ; c'est la fenêtre qui décide. C'est
ce qui permet de le tester sans corpus et sans modèle.

## L'accessibilité — `PLAN-19` tenu, pas perdu

Trois points, et le troisième est celui qu'on perd le plus facilement :

1. **un `PARCOURS` explicite**, comme les autres panneaux. « Le critère 6 du `PLAN-19` demande
   UN ordre explicite PAR PANNEAU, pas un par défaut qui se trouve juste » ;
2. **un `AccessibleName` par item**, qui porte le libellé même en mode compact — où le texte
   visible disparaît ;
3. **l'état sélectionné annoncé autrement que par la couleur** : l'item actif est en **gras**
   et son `AccessibleDescription` dit « destination active ». Un état qui ne se lit qu'à la
   teinte est un état que 8 % des hommes ne lisent pas.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QListWidget, QListWidgetItem,
                               QToolButton, QVBoxLayout, QWidget)

from . import destinations as dest
from . import icones as ico
from . import theme

#: Largeur du pane déployé, en pixels. Assez pour « Illustrations » au corps normal sans
#: élider, pas assez pour manger la place d'une pellicule de planches.
LARGEUR_DEPLOYE = 176

#: Largeur du pane compact : une icône de 16 px et ses marges, rien de plus.
LARGEUR_COMPACT = 48

#: Hauteur d'un item. Assez haute pour être une cible de clic confortable (WCAG 2.2 : 24 px
#: minimum pour une cible, et 32 px est le pas de la barre d'outils du dépôt).
HAUTEUR_ITEM = 32

#: Ce que `AccessibleDescription` porte sur l'item actif. Lu tel quel par un lecteur d'écran.
MARQUE_ACTIVE = "destination active"


class _Liste(QListWidget):
    """Une liste d'items de navigation. Séparée pour que le corps et le pied partagent tout.

    ⚠ `NoSelection` sur le PIED, `SingleSelection` sur le corps : une entrée de pied ouvre un
    dialogue et ne devient jamais « l'endroit où l'on est ». La laisser sélectionnable
    afficherait deux destinations actives à la fois, dont une fausse."""

    def __init__(self, selectionnable: bool, parent=None):
        super().__init__(parent)
        self.setFrameShape(QListWidget.NoFrame)
        self.setSelectionMode(QAbstractItemView.SingleSelection if selectionnable
                              else QAbstractItemView.NoSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(ico.COTE, ico.COTE))

    def hauteur_voulue(self) -> int:
        return self.count() * HAUTEUR_ITEM + 4


class PanneauNavigation(QWidget):
    """Le pane. Corps en haut, pied en bas, et un bouton menu pour le mode minimal."""

    #: Une destination de corps a été choisie — la fenêtre montre sa page.
    choisie = Signal(str)
    #: Une entrée de pied a été activée — la fenêtre déclenche l'action qu'elle nomme.
    demande_action = Signal(str)

    #: L'ordre de tabulation. Deux listes et un bouton : court, mais **déclaré**, parce qu'un
    #: ordre qui se trouve juste aujourd'hui se déplace au premier widget ajouté demain.
    PARCOURS: tuple[str, ...] = ("bouton_menu", "liste", "liste_pied")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = dest.DEPLOYE
        self._courante = dest.ACCUEIL
        self._construire()

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(theme.Espacement.XS, theme.Espacement.XS,
                                   theme.Espacement.XS, theme.Espacement.XS)
        colonne.setSpacing(theme.Espacement.XS)

        # ⚠ Le bouton de menu existe dans les TROIS modes mais n'est visible qu'en minimal.
        # Le créer à la demande ferait de la bascule un moment où des widgets naissent, donc
        # un moment où le parcours de tabulation change sous les doigts.
        self.bouton_menu = QToolButton()
        self.bouton_menu.setAutoRaise(True)
        self.bouton_menu.setAccessibleName("Afficher les destinations")
        self.bouton_menu.setToolTip("Afficher les destinations (la fenêtre est trop étroite "
                                    "pour le pane).")
        self.bouton_menu.clicked.connect(self._basculer_minimal)
        colonne.addWidget(self.bouton_menu)

        self.liste = _Liste(True)
        self.liste.setAccessibleName("Destinations")
        self.liste.currentItemChanged.connect(self._sur_choix)
        colonne.addWidget(self.liste)
        colonne.addStretch(1)

        self.liste_pied = _Liste(False)
        self.liste_pied.setAccessibleName("Réglages et diagnostic")
        self.liste_pied.itemClicked.connect(self._sur_pied)
        colonne.addWidget(self.liste_pied)

        self._remplir()
        self._poser_parcours()
        self.appliquer_mode(dest.DEPLOYE)

    def _poser_parcours(self) -> None:
        widgets = [getattr(self, nom) for nom in self.PARCOURS if hasattr(self, nom)]
        for avant, apres in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(avant, apres)

    def _remplir(self) -> None:
        self._items: dict[str, QListWidgetItem] = {}
        for destination in dest.corps():
            self._items[destination.identifiant] = self._poser(self.liste, destination)
        for destination in dest.pied():
            self._items[destination.identifiant] = self._poser(self.liste_pied, destination)
        self.liste.setFixedHeight(self.liste.hauteur_voulue())
        self.liste_pied.setFixedHeight(self.liste_pied.hauteur_voulue())
        self.liste.setCurrentRow(0)

    def _poser(self, liste: _Liste, destination) -> QListWidgetItem:
        item = QListWidgetItem(destination.libelle, liste)
        item.setData(Qt.UserRole, destination.identifiant)
        item.setSizeHint(QSize(0, HAUTEUR_ITEM))
        if destination.infobulle:
            item.setToolTip(destination.infobulle)
        # ⚠ L'`AccessibleName` porte le LIBELLÉ, pas l'identifiant, et il survit au mode
        # compact où le texte visible est retiré. Sans lui, un lecteur d'écran annoncerait un
        # item vide dès que la fenêtre passe sous 1008 px.
        item.setData(Qt.AccessibleTextRole, destination.libelle)
        return item

    # ------------------------------------------------------------------ #
    #  Les trois modes
    # ------------------------------------------------------------------ #

    def mode(self) -> str:
        return self._mode

    def appliquer_largeur(self, largeur: int) -> str:
        """Bascule le pane selon la largeur de la FENÊTRE. Rend le mode appliqué.

        La décision est prise par `destinations.mode_pour_largeur`, en Python nu : c'est elle
        qui se teste sans écran, et ce widget ne fait que la servir."""
        return self.appliquer_mode(dest.mode_pour_largeur(int(largeur)))

    def appliquer_mode(self, mode: str) -> str:
        self._mode = mode
        minimal = mode == dest.MINIMAL
        compact = mode == dest.COMPACT
        self.bouton_menu.setVisible(minimal)
        self.bouton_menu.setIcon(ico.icone("menu"))
        for identifiant, item in self._items.items():
            destination = dest.par_identifiant(identifiant)
            item.setText("" if compact else destination.libelle)
            item.setIcon(ico.icone(destination.icone))
            item.setTextAlignment(Qt.AlignCenter if compact
                                  else Qt.AlignLeft | Qt.AlignVCenter)
        if minimal:
            # ⚠ Le pane MINIMAL ne disparaît pas : il se réduit au bouton. Le faire disparaître
            # tout à fait laisserait une fenêtre sans aucun chemin de navigation à la souris —
            # et la souris est le seul chemin que l'utilisateur n'a pas à apprendre.
            self.liste.setVisible(False)
            self.liste_pied.setVisible(False)
            self.setFixedWidth(LARGEUR_COMPACT)
        else:
            self.liste.setVisible(True)
            self.liste_pied.setVisible(True)
            self.setFixedWidth(LARGEUR_COMPACT if compact else LARGEUR_DEPLOYE)
        return mode

    def _basculer_minimal(self) -> None:
        """Le bouton menu du mode minimal : déplie le pane par-dessus, sans élargir la fenêtre."""
        visible = not self.liste.isVisible()
        self.liste.setVisible(visible)
        self.liste_pied.setVisible(visible)
        self.setFixedWidth(LARGEUR_DEPLOYE if visible else LARGEUR_COMPACT)
        for identifiant, item in self._items.items():
            item.setText(dest.par_identifiant(identifiant).libelle)

    def rafraichir_theme(self) -> None:
        """Redemande les icônes après une bascule de thème.

        ⚠ Un `QIcon` déjà rendu est un pixmap : aucune règle QSS ne l'atteint. Sans ce
        passage, le pane garderait les glyphes du thème précédent jusqu'au prochain
        lancement — le même défaut que la pellicule, au même endroit."""
        for identifiant, item in self._items.items():
            item.setIcon(ico.icone(dest.par_identifiant(identifiant).icone))
        self.bouton_menu.setIcon(ico.icone("menu"))
        self._marquer_active()

    # ------------------------------------------------------------------ #
    #  La sélection
    # ------------------------------------------------------------------ #

    def courante(self) -> str:
        return self._courante

    def selectionner(self, identifiant: str) -> None:
        """Pose la sélection **sans réémettre** — la fenêtre l'a déjà décidée.

        ⚠ `blockSignals` : `setCurrentItem` réémet `currentItemChanged`, donc `choisie`, donc
        la fenêtre reviendrait ici. C'est le patron de `_restaurer_selection_de_tome`, pour la
        même raison — un aller-retour de signal qui se rappelle lui-même."""
        item = self._items.get(identifiant)
        if item is None or item.listWidget() is not self.liste:
            return
        self._courante = identifiant
        self.liste.blockSignals(True)
        self.liste.setCurrentItem(item)
        self.liste.blockSignals(False)
        self._marquer_active()

    def _marquer_active(self) -> None:
        """Le gras et la description accessible. **Pas seulement la couleur de sélection.**"""
        for identifiant, item in self._items.items():
            actif = identifiant == self._courante
            fonte = item.font()
            fonte.setBold(actif)
            item.setFont(fonte)
            item.setData(Qt.AccessibleDescriptionRole, MARQUE_ACTIVE if actif else "")

    def _sur_choix(self, item, _precedent=None) -> None:
        if item is None:
            return
        identifiant = item.data(Qt.UserRole)
        self._courante = identifiant
        self._marquer_active()
        self.choisie.emit(identifiant)

    def _sur_pied(self, item) -> None:
        """Le pied porte DEUX sortes d'entrées, et il n'en servait qu'une.

        ⚠ **Le défaut que ceci corrige** : « Réglages » a une `action` (elle ouvre un
        dialogue), « Diagnostic » n'en a pas — depuis le lot 36 c'est une PAGE, et
        `destinations.pages()` le dit explicitement (« le pied sans `action` »). La condition
        `if destination.action` ne laissait donc passer que la première : cliquer sur
        Diagnostic dans le pied du pane **ne faisait rien du tout**, en silence.

        Un clic qui ne produit rien passe pour une application cassée — c'est le reproche que
        `gui/depot.py` fait déjà au lâcher muet, et il vaut ici mot pour mot."""
        destination = dest.par_identifiant(item.data(Qt.UserRole))
        if destination is None:
            return
        if destination.action:
            self.demande_action.emit(destination.action)
            return
        # Une entrée de pied SANS action est une destination comme une autre : on navigue, et
        # on marque la sélection pour que le pane dise où l'on est.
        self._courante = destination.identifiant
        self._marquer_active()
        self.choisie.emit(destination.identifiant)
