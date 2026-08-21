# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Canevas d'une planche : l'image, les zones de bulles, et les outils de dessin.

## Ce qui est dessiné, et ce qui ne l'est pas

Les zones sont affichées par leur **boîte englobante**, pas par leur masque. `regions.json` ne
retient pas la forme choisie (rectangle ou ellipse) — seul `masks.png` porte les pixels, et
c'est lui qui compte pour le nettoyage. Le rectangle à l'écran est donc un repère de
sélection, pas une promesse sur ce que le nettoyage repeindra. Afficher le masque exact
demanderait de composer un calque RGBA pleine page par bulle à chaque rafraîchissement, pour
une information que l'utilisateur lit déjà sur la planche nettoyée qu'il a sous les yeux.

## Poignées : ce qui a changé, et pourquoi

Ce module a longtemps affirmé qu'il n'en fallait pas — « quatre pixels à attraper sur une
planche affichée à 30 % seraient de toute façon inconfortables, et l'opération sous-jacente
(`edition.modifier_zone`) prend une bbox, pas un déplacement ». Les deux moitiés de
l'argument sont tombées :

· **L'inconfort venait du zoom, pas de la poignée.** `PoigneeItem` porte
  `ItemIgnoresTransformations` : son rect local est en pixels ÉCRAN, elle mesure donc 11 px
  quel que soit le grossissement. Le dépôt s'en servait déjà pour les numéros de bulle.
· **`modifier_zone` n'est plus la seule opération.** `edition.retailler_zone` étire le masque
  existant vers une nouvelle boîte et **garde l'OCR et la traduction** — là où « Redessiner »
  les remet à zéro, à bon droit puisqu'il repart d'une forme neuve. Ajuster une bulle de
  quelques pixels ne coûte donc plus une relecture.

« Redessiner » reste : c'est le seul moyen de changer de famille de forme (rectangle ↔
ellipse) et de repartir d'un masque propre quand celui du détecteur est faux.

## Le trait de coupe

En mode scission, le glisser trace une **droite**, prolongée à l'infini par
`edition.scinder_zone` : il suffit de la faire passer par le goulot entre les deux ballons, pas
de la caler précisément sur les bords.
"""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView)

# Modes de l'outil. `MODE_CHOISIR` est le repos : on sélectionne, on ne dessine rien.
MODE_CHOISIR = "choisir"
MODE_RECTANGLE = "rectangle"
MODE_ELLIPSE = "ellipse"
MODE_MODIFIER = "modifier"
MODE_SCINDER = "scinder"

_COULEUR_ZONE = QColor(70, 150, 255)
_COULEUR_CHOISIE = QColor(255, 170, 40)
_COULEUR_VIDE = QColor(230, 80, 80)          # bulle sans réplique : elle se voit de loin
_COULEUR_MAIN = QColor(120, 210, 120)        # réplique reprise à la main
_COULEUR_TRACE = QColor(255, 255, 255)

# Sous cette taille en pixels de planche, un glisser est un clic maladroit et non un tracé.
_TAILLE_MIN_TRACE = 6

# Côté d'une poignée, en pixels ÉCRAN (cf. `ItemIgnoresTransformations`). 11 px : assez large
# pour être visé à la souris sans viser, assez étroit pour ne pas masquer une petite bulle.
_COTE_POIGNEE = 11.0

# Les huit poignées, dans le sens horaire depuis le coin haut-gauche. Chaque entrée dit quelles
# ARÊTES du rectangle la poignée déplace : (gauche, haut, droite, bas).
_ANCRES_POIGNEE = (
    ("no", (1, 1, 0, 0)), ("n", (0, 1, 0, 0)), ("ne", (0, 1, 1, 0)), ("e", (0, 0, 1, 0)),
    ("se", (0, 0, 1, 1)), ("s", (0, 0, 0, 1)), ("so", (1, 0, 0, 1)), ("o", (1, 0, 0, 0)),
)

_CURSEURS_POIGNEE = {
    "no": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    "ne": Qt.SizeBDiagCursor, "so": Qt.SizeBDiagCursor,
    "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
    "e": Qt.SizeHorCursor, "o": Qt.SizeHorCursor,
}


class ZoneItem(QGraphicsRectItem):
    """Le rectangle d'une bulle. Porte son index — c'est lui que l'éditeur manipule.

    **Déplaçable** quand la scène est interactive : le glisser translate la zone DÉTECTÉE,
    masque compris, et l'éditeur en fait un `edition.retailler_zone` à taille constante. Ce
    n'est pas le même geste que déplacer le bloc de texte (qui, lui, ne bouge que le lettrage
    dans `mise_en_page.json` et ne touche ni au masque ni au nettoyage)."""

    def __init__(self, index: int, rect: QRectF, *, etat: str = "normal",
                 interactif: bool = True):
        super().__init__(rect)
        self.index = index
        self.etat = etat
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.regler_interaction(interactif)
        self._depart: QPointF | None = None
        self._appliquer(False)

    def regler_interaction(self, actif: bool) -> None:
        self.setFlag(QGraphicsRectItem.ItemIsMovable, bool(actif))
        self.setFlag(QGraphicsRectItem.ItemSendsGeometryChanges, bool(actif))
        self.setCursor(Qt.SizeAllCursor if actif else Qt.ArrowCursor)

    def rect_scene(self) -> QRectF:
        """La boîte en coordonnées de PLANCHE. `rect()` est local ; après un déplacement, il
        n'a pas bougé et c'est `pos()` qui porte la translation."""
        return self.rect().translated(self.pos())

    # ⚠ Les signaux partent de `mouseMoveEvent`/`mouseReleaseEvent`, JAMAIS de `itemChange`.
    # Un slot branché sur `ItemPositionHasChanged` qui rappellerait `setPos` sur ce même item
    # rejouerait l'`itemChange` : récursion silencieuse, et un rectangle qui colle au curseur.
    def mousePressEvent(self, event) -> None:
        self._depart = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        scene = self.scene()
        if self._depart is not None and scene is not None:
            scene.zone_en_cours.emit(self.index, self.rect_scene())

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._depart is None:
            return
        delta = self.pos() - self._depart
        self._depart = None
        scene = self.scene()
        if scene is None:
            return
        if abs(delta.x()) < 1 and abs(delta.y()) < 1:
            scene.rafraichir_poignees()      # un clic : la zone n'a pas bougé
            return
        scene.zone_retaillee.emit(self.index, self.rect_scene())

    def _appliquer(self, choisie: bool) -> None:
        if choisie:
            couleur, epaisseur = _COULEUR_CHOISIE, 4
        elif self.etat == "vide":
            couleur, epaisseur = _COULEUR_VIDE, 3
        elif self.etat == "manuelle":
            couleur, epaisseur = _COULEUR_MAIN, 3
        else:
            couleur, epaisseur = _COULEUR_ZONE, 2
        stylo = QPen(couleur, epaisseur)
        stylo.setCosmetic(True)       # épaisseur constante à l'écran quel que soit le zoom
        self.setPen(stylo)
        remplissage = QColor(couleur)
        remplissage.setAlpha(48 if choisie else 20)
        self.setBrush(QBrush(remplissage))

    def marquer(self, choisie: bool) -> None:
        self._appliquer(choisie)


class PoigneeItem(QGraphicsRectItem):
    """Une des huit poignées de redimensionnement de la zone sélectionnée.

    ## Pourquoi elle n'est PAS enfant du `ZoneItem`

    `ItemIgnoresTransformations` rend l'item insensible aux transformations de la vue **et de
    ses parents**. Un enfant du `ZoneItem` verrait donc sa position interprétée dans un repère
    non transformé : les huit poignées s'empileraient à l'origine du parent. Ce sont des items
    FRÈRES, posés en coordonnées de scène ; seule leur taille est figée en pixels écran.
    Corollaire commode : rien à recalculer au zoom, donc pas de branchement sur
    `VuePlanche.zoom_change`, donc pas de chemin de mise à jour à oublier.

    ## Pourquoi `event.accept()` explicite

    La poignée n'est ni `ItemIsMovable` ni `ItemIsSelectable` — elle pilote le rectangle de la
    zone, elle ne se déplace pas elle-même. Or `QGraphicsItem::mousePressEvent` **ignore**
    l'événement dans ce cas : pas de grab, donc pas un seul `mouseMoveEvent`. C'est le même
    piège que celui qui rendait les blocs de texte inattrapables, une couche plus bas."""

    def __init__(self, index: int, ancre: str, aretes: tuple[int, int, int, int]):
        demi = _COTE_POIGNEE / 2
        super().__init__(QRectF(-demi, -demi, _COTE_POIGNEE, _COTE_POIGNEE))
        self.index = index
        self.ancre = ancre
        self.aretes = aretes
        self.setFlag(QGraphicsRectItem.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(_CURSEURS_POIGNEE[ancre])
        self.setZValue(4)
        stylo = QPen(QColor(30, 30, 34), 1)
        stylo.setCosmetic(True)
        self.setPen(stylo)
        self.setBrush(QBrush(_COULEUR_CHOISIE))
        self._depart: QRectF | None = None

    def mousePressEvent(self, event) -> None:
        scene = self.scene()
        zone = scene.zone(self.index) if scene is not None else None
        self._depart = zone.rect_scene() if zone is not None else None
        event.accept()                   # ⚠ sans ça : aucun grab, aucun mouseMoveEvent

    def _boite(self, event) -> QRectF | None:
        """La boîte visée par la position courante du curseur, ou `None`."""
        if self._depart is None:
            return None
        delta = event.scenePos() - event.buttonDownScenePos(Qt.LeftButton)
        g, h, d, b = self.aretes
        boite = QRectF(self._depart)
        boite.adjust(delta.x() * g, delta.y() * h, delta.x() * d, delta.y() * b)
        # `normalized` seul suffirait à retourner une boîte tirée « à l'envers », mais une
        # boîte dégénérée ferait lever `ErreurEdition` au dépôt. On plancher ici, pendant le
        # geste, où l'utilisateur voit ce qu'il fait.
        boite = boite.normalized()
        if boite.width() < _TAILLE_MIN_TRACE or boite.height() < _TAILLE_MIN_TRACE:
            return None
        return boite

    def mouseMoveEvent(self, event) -> None:
        boite = self._boite(event)
        scene = self.scene()
        if boite is None or scene is None:
            return
        scene.poser_boite_zone(self.index, boite)
        scene.zone_en_cours.emit(self.index, boite)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        boite = self._boite(event)
        depart, self._depart = self._depart, None
        scene = self.scene()
        if scene is None:
            return
        event.accept()
        if boite is None or (depart is not None and boite == depart):
            scene.rafraichir_poignees()
            return
        scene.zone_retaillee.emit(self.index, boite)


class CalqueTexteItem(QGraphicsPixmapItem):
    """Le texte d'une bulle, posé sur la planche nettoyée et **déplaçable**.

    Produit par `typeset.calque_fit`, donc identique au pixel près à ce que le rendu final
    écrira. Le glisser translate l'item — instantané, aucun recalcul ; c'est au dépôt que
    l'habillage est rejoué sur le nouveau rectangle.

    ⚠ L'item porte son `rect` d'habillage, qui est AUSSI son masque de découpe : `calque_fit`
    découpe le texte à l'intérieur du style, si bien qu'un bloc traîné hors de sa bulle serait
    rogné à l'ancienne forme et disparaîtrait. Les deux ne peuvent pas diverger parce que
    c'est le même rectangle qui est enregistré et relu."""

    def __init__(self, index: int, pixmap: QPixmap, rect: QRectF, *, taille: int = 0):
        super().__init__(pixmap)
        self.index = index
        self.rect_habillage = rect
        # Le corps auquel ce bloc a été lettré. Il repart tel quel dans `mise_en_page.json` :
        # déplacer un texte ne doit pas changer sa taille. L'éditeur le lisait jusqu'ici dans
        # un `_calques_prets` qui n'a JAMAIS été assigné — la taille ne partait donc pas,
        # `fit_impose` retombait sur `taille_max`, échouait, et le corps était recalculé à
        # chaque déplacement. C'est exactement ce que la docstring promettait d'éviter.
        self.taille = int(taille)
        self.setFlag(QGraphicsPixmapItem.ItemIsMovable, True)
        self.setFlag(QGraphicsPixmapItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsPixmapItem.ItemSendsGeometryChanges, True)
        # ⚠ `BoundingRectShape`, pas le défaut `MaskShape`. Le pixmap est un calque de texte :
        # son masque alpha est celui des GLYPHES. Avec le mode par défaut, seul un clic tombant
        # pile sur un trait de lettre attrapait le bloc — entre deux mots, entre deux lignes,
        # dans une contre-forme, le geste passait au travers. C'est la moitié du « impossible à
        # sélectionner » ; l'autre moitié était dans `ScenePlanche.mousePressEvent`.
        self.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
        self.setZValue(2)
        self.setCursor(Qt.OpenHandCursor)
        self._depart = None

    def mousePressEvent(self, event) -> None:
        # Alt laisse le geste descendre à la ZONE sous le texte : c'est ainsi qu'on déplace la
        # bulle entière alors que son bloc de texte couvre presque toute sa surface.
        # ⚠ Il faut ignorer le PRESS (pas le move) : c'est le seul moment où Qt propose le
        # geste à l'item suivant dans l'ordre de profondeur.
        if event.modifiers() & Qt.AltModifier:
            event.ignore()
            return
        self._depart = self.pos()
        self.setCursor(Qt.ClosedHandCursor)
        scene = self.scene()
        if scene is not None:
            scene.choisir(self.index)
            scene.zone_choisie.emit(self.index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        if self._depart is None:
            return
        scene = self.scene()
        if scene is not None:
            scene.texte_glisse.emit(self.index,
                                    self.rect_habillage.translated(self.pos() - self._depart))

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.OpenHandCursor)
        if self._depart is None:
            return
        delta = self.pos() - self._depart
        self._depart = None
        if abs(delta.x()) < 1 and abs(delta.y()) < 1:
            return                     # un clic, pas un déplacement
        nouveau = self.rect_habillage.translated(delta)
        self.rect_habillage = nouveau
        scene = self.scene()
        if scene is not None:
            scene.texte_deplace.emit(self.index, nouveau)



class ScenePlanche(QGraphicsScene):
    """Scène d'une planche. Émet ce que l'utilisateur a fait, jamais ce qu'il faut en faire —
    la décision (et l'écriture) appartiennent à l'éditeur."""

    zone_choisie = Signal(int)                  # index, ou -1
    zone_dessinee = Signal(QRectF, str)         # (boîte en pixels de planche, forme)
    zone_modifiee = Signal(int, QRectF, str)    # (index visé, nouvelle boîte, forme)
    coupe_dessinee = Signal(int, QLineF)        # (index visé, droite de coupe)
    texte_deplace = Signal(int, QRectF)         # (index, nouveau rectangle d'habillage)
    zone_ouverte = Signal(int)                  # double-clic : éditer CETTE bulle
    # Gestes CONTINUS — émis pendant, à pleine cadence. C'est l'éditeur qui les étrangle : lui
    # seul sait ce que coûte un ré-habillage, et une scène qui déciderait du rythme d'un
    # travail qu'elle ne fait pas serait un mauvais partage.
    texte_glisse = Signal(int, QRectF)          # (index, rectangle d'habillage visé)
    zone_en_cours = Signal(int, QRectF)         # (index, boîte de zone visée)
    zone_retaillee = Signal(int, QRectF)        # (index, boîte déposée) — au relâchement

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = MODE_CHOISIR
        self.forme_ajout = MODE_RECTANGLE
        self.index_courant = -1
        # Un fond aplati (« Comparer au rendu du pipeline ») ou un run en cours : plus rien ne
        # doit être saisissable. Ce n'est pas un grisage de widget — c'est le grab lui-même
        # qu'on refuse, sinon on déplacerait un texte qui n'est même pas affiché.
        self.interactif = True
        self._zones: dict[int, ZoneItem] = {}
        self._calques: dict[int, CalqueTexteItem] = {}
        self._poignees: list[PoigneeItem] = []
        self._fond: QGraphicsPixmapItem | None = None
        self._trace = None
        self._depart: QPointF | None = None

    # ------------------------------------------------------------------ #
    # Contenu
    # ------------------------------------------------------------------ #

    def charger(self, chemin_image, bulles, *, numeros: bool = True) -> None:
        """Remplace tout le contenu. Appelée à chaque rafraîchissement — reconstruire est plus
        sûr que réconcilier, et une planche compte une dizaine de zones."""
        self.clear()
        self._zones.clear()
        self._calques.clear()
        self._poignees.clear()          # ⚠ `clear()` les a déjà détruites : ne pas removeItem
        self._fond = None
        self._trace = None
        self.index_courant = -1

        if chemin_image is not None:
            pixmap = QPixmap(str(chemin_image))
            if not pixmap.isNull():
                self._fond = self.addPixmap(pixmap)
                self._fond.setZValue(-10)
                self.setSceneRect(QRectF(pixmap.rect()))

        for bulle in bulles:
            x0, y0, x1, y1 = bulle.bbox
            item = ZoneItem(bulle.index, QRectF(x0, y0, x1 - x0, y1 - y0),
                            etat=_etat_de_bulle(bulle), interactif=self.interactif)
            item.setZValue(1)
            self.addItem(item)
            self._zones[bulle.index] = item
            if numeros:
                self._poser_numero(bulle.index, x0, y0)

    def _poser_numero(self, index: int, x: float, y: float) -> None:
        """Le numéro de la bulle DANS L'ORDRE DE LECTURE. C'est l'information la plus utile de
        tout l'écran : c'est cet ordre qui aligne `ocr.json` et `traduction.json`, et une
        inversion se voit d'un coup d'œil ici alors qu'elle est invisible sur la page rendue."""
        etiquette = QGraphicsSimpleTextItem(str(index + 1))
        etiquette.setBrush(QBrush(QColor(20, 20, 20)))
        fonte = etiquette.font()
        fonte.setPointSizeF(16)
        fonte.setBold(True)
        etiquette.setFont(fonte)
        etiquette.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations, True)
        etiquette.setPos(x, y)
        etiquette.setZValue(3)
        fond = QGraphicsEllipseItem(-4, -2, 26, 24, etiquette)
        fond.setBrush(QBrush(QColor(255, 210, 90, 230)))
        fond.setPen(QPen(Qt.NoPen))
        fond.setZValue(-1)
        self.addItem(etiquette)

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-cliquer une bulle amène le curseur dans son champ de réplique.

        Il fallait jusqu'ici viser la liste de droite pour éditer ce qu'on regarde à gauche —
        un aller-retour du regard à chaque correction."""
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        index = getattr(item, "index", None)
        if index is not None:
            self.zone_ouverte.emit(int(index))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def poser_calques(self, calques) -> None:
        """Pose (ou remplace) les calques de texte au-dessus du fond nettoyé.

        Appelée séparément de `charger` parce qu'elle arrive plus tard : composer l'aperçu
        demande le scan d'origine, donc une tâche de fond. La planche s'affiche tout de suite,
        son texte s'y pose quand il est prêt."""
        for item in self._calques.values():
            self.removeItem(item)
        self._calques.clear()
        for calque in calques or []:
            item = CalqueTexteItem(calque.index, _pixmap_de(calque),
                                   QRectF(*_rect_qt(calque.rect)), taille=calque.taille)
            item.setPos(calque.x, calque.y)
            self.addItem(item)
            self._calques[calque.index] = item

    def remplacer_calque(self, calque) -> bool:
        """Met à jour UN calque **sans détruire son item**. `False` s'il n'existe pas encore.

        ⚠ C'est la raison d'être de cette méthode, et elle n'est pas cosmétique :
        `poser_calques` retire tous les items, or l'un d'eux peut être en train de tenir le
        `mouseGrabberItem`. L'appeler pendant un glisser tuerait le geste au premier
        rafraîchissement — sans erreur, sans trace, et sans que rien n'explique pourquoi le
        bloc « décroche » dès qu'on le bouge. C'est exactement le chemin qu'emprunte le
        relettrage en direct."""
        item = self._calques.get(calque.index)
        if item is None:
            return False
        item.setPixmap(_pixmap_de(calque))
        item.setPos(calque.x, calque.y)
        item.rect_habillage = QRectF(*_rect_qt(calque.rect))
        item.taille = int(calque.taille)
        return True

    def a_des_calques(self) -> bool:
        return bool(self._calques)

    def calque(self, index: int) -> CalqueTexteItem | None:
        """L'item de texte d'une bulle. C'est lui qui porte le corps auquel elle a été
        lettrée — la donnée que `_sur_texte_deplace` allait chercher dans un attribut
        inexistant."""
        return self._calques.get(index)

    # ------------------------------------------------------------------ #
    # Sélection, poignées, interaction
    # ------------------------------------------------------------------ #

    def zone(self, index: int) -> ZoneItem | None:
        return self._zones.get(index)

    def choisir(self, index: int) -> None:
        for k, item in self._zones.items():
            item.marquer(k == index)
        self.index_courant = index if index in self._zones else -1
        self.rafraichir_poignees()

    def poser_boite_zone(self, index: int, boite: QRectF) -> None:
        """Redessine le cadre d'une zone pendant un geste. **N'écrit rien** — le dépôt est
        l'affaire de `zone_retaillee`, donc de l'éditeur."""
        item = self._zones.get(index)
        if item is None:
            return
        item.setPos(0, 0)               # la boîte est donnée en coordonnées de scène
        item.setRect(boite)
        self.rafraichir_poignees()

    def regler_interaction(self, actif: bool) -> None:
        """Ouvre ou ferme la manipulation directe (zones, poignées, blocs de texte).

        Fermée sur le rendu aplati du pipeline — il n'y a plus de calque à déplacer, et une
        poignée qui répondrait sur une image cuite promettrait ce qu'elle ne peut pas tenir —
        et pendant un run global, où toute écriture est suspendue."""
        self.interactif = bool(actif)
        for item in self._zones.values():
            item.regler_interaction(self.interactif)
        self.rafraichir_poignees()

    def rafraichir_poignees(self) -> None:
        """Replace les huit poignées autour de la zone choisie, ou les retire.

        ⚠ Elles sont REPOSITIONNÉES, jamais recréées quand elles existent déjà : détruire
        l'item qu'on est en train de tirer couperait le grab en plein geste."""
        zone = self._zones.get(self.index_courant)
        if zone is None or not self.interactif:
            for item in self._poignees:
                self.removeItem(item)
            self._poignees.clear()
            return
        if not self._poignees or self._poignees[0].index != self.index_courant:
            for item in self._poignees:
                self.removeItem(item)
            self._poignees = [PoigneeItem(self.index_courant, ancre, aretes)
                              for ancre, aretes in _ANCRES_POIGNEE]
            for item in self._poignees:
                self.addItem(item)
        boite = zone.rect_scene()
        for item in self._poignees:
            item.setPos(_point_ancre(boite, item.ancre))

    # ------------------------------------------------------------------ #
    # Souris
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event) -> None:
        """⚠ **C'est ici que la manipulation directe était bloquée.**

        La version d'avant appelait `choisir()` puis `event.accept()`, et **jamais**
        `super().mousePressEvent`. Or c'est l'implémentation parente qui pose le
        `mouseGrabberItem` : sans elle, aucun item ne reçoit le press, donc `ItemIsMovable`
        n'est qu'une décoration et aucun `mouseMoveEvent` d'item n'arrive jamais. Les blocs de
        texte n'étaient pas « difficiles à attraper » — ils n'étaient jamais saisis du tout.

        On laisse donc d'abord passer le geste quand il vise un item MANIPULABLE, puis on
        retombe sur la sélection. ⚠ Le test porte sur le type de l'item, pas sur
        `event.isAccepted()` : un `ZoneItem` est `ItemIsSelectable`, il accepte donc le press
        lui aussi, et se fier à l'acceptation court-circuiterait `choisir()` — la sélection
        cesserait de fonctionner, ce qui échangerait un défaut contre un autre."""
        point = event.scenePos()
        if self.mode in (MODE_RECTANGLE, MODE_ELLIPSE, MODE_MODIFIER, MODE_SCINDER):
            if self.mode in (MODE_MODIFIER, MODE_SCINDER) and self.index_courant < 0:
                event.accept()
                return                       # rien à viser : le clic ne fait rien
            self._depart = point
            self._trace = self._nouveau_trace(point)
            event.accept()
            return
        if self.interactif and self._item_manipulable(point, event) is not None:
            super().mousePressEvent(event)
            if self.mouseGrabberItem() is not None:
                return
        self.choisir(self._index_sous(point))
        self.zone_choisie.emit(self.index_courant)
        event.accept()

    def _item_manipulable(self, point: QPointF, event):
        """Le premier item sous le curseur qui sait faire quelque chose d'un glisser.

        Les poignées d'abord — elles chevauchent le cadre de la zone par construction, et une
        poignée qu'on ne peut pas viser parce que le cadre la couvre ne sert à rien."""
        items = self.items(point)
        for item in items:
            if isinstance(item, PoigneeItem):
                return item
        alt = bool(event.modifiers() & Qt.AltModifier)
        for item in items:
            if isinstance(item, CalqueTexteItem) and not alt:
                return item
            if isinstance(item, ZoneItem) and item.index == self.index_courant:
                # Seule la zone DÉJÀ choisie se déplace : sinon le premier clic sur une bulle
                # la ferait bouger au lieu de la sélectionner, et l'on ne pourrait plus
                # désigner une bulle sans risquer de la déranger.
                return item
        return None

    def mouseMoveEvent(self, event) -> None:
        if self._trace is None or self._depart is None:
            super().mouseMoveEvent(event)
            return
        if self.mode == MODE_SCINDER:
            self._trace.setLine(QLineF(self._depart, event.scenePos()))
        else:
            self._trace.setRect(QRectF(self._depart, event.scenePos()).normalized())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._trace is None or self._depart is None:
            super().mouseReleaseEvent(event)
            return
        depart, arrivee = self._depart, event.scenePos()
        self.removeItem(self._trace)
        self._trace, self._depart = None, None
        event.accept()

        if self.mode == MODE_SCINDER:
            if QLineF(depart, arrivee).length() >= _TAILLE_MIN_TRACE:
                self.coupe_dessinee.emit(self.index_courant, QLineF(depart, arrivee))
            return

        boite = QRectF(depart, arrivee).normalized()
        if boite.width() < _TAILLE_MIN_TRACE or boite.height() < _TAILLE_MIN_TRACE:
            return                          # clic maladroit, pas un tracé
        if self.mode == MODE_MODIFIER:
            self.zone_modifiee.emit(self.index_courant, boite, self.forme_ajout)
        else:
            forme = MODE_ELLIPSE if self.mode == MODE_ELLIPSE else MODE_RECTANGLE
            self.zone_dessinee.emit(boite, forme)

    # ------------------------------------------------------------------ #

    def _nouveau_trace(self, point: QPointF):
        stylo = QPen(_COULEUR_TRACE, 2, Qt.DashLine)
        stylo.setCosmetic(True)
        if self.mode == MODE_SCINDER:
            item = QGraphicsLineItem(QLineF(point, point))
        elif self.mode == MODE_ELLIPSE:
            item = QGraphicsEllipseItem(QRectF(point, point))
        else:
            item = QGraphicsRectItem(QRectF(point, point))
        item.setPen(stylo)
        item.setZValue(20)
        self.addItem(item)
        return item

    def _index_sous(self, point: QPointF) -> int:
        """La zone la plus PETITE sous le curseur. Deux bulles qui se recouvrent à l'écran
        (leurs boîtes, pas leurs masques) sinon rendraient la plus grande impossible à quitter."""
        candidates = [item for item in self.items(point) if isinstance(item, ZoneItem)]
        if not candidates:
            return -1
        return min(candidates, key=lambda z: z.rect().width() * z.rect().height()).index


def _rect_qt(rect) -> tuple[float, float, float, float]:
    """`(x0, y0, x1, y1)` → `(x, y, largeur, hauteur)`, la convention de `QRectF`."""
    x0, y0, x1, y1 = rect
    return float(x0), float(y0), float(x1 - x0), float(y1 - y0)


def _pixmap_de(calque) -> QPixmap:
    """L'image PIL d'un `CalqueBulle` en `QPixmap`.

    ⚠ Le `.copy()` du `QImage` n'est pas une précaution de style : `QImage` **ne possède pas**
    le tampon que `tobytes()` lui prête. Sans copie, le texte se corrompt par intermittence, au
    gré du ramasse-miettes — le genre de défaut qu'on ne reproduit jamais quand on le cherche.

    ⚠ Sur le FIL D'AFFICHAGE uniquement : un `QPixmap` ne se construit pas ailleurs. C'est
    pourquoi le cache d'aperçus ne garde que des images PIL."""
    from PySide6.QtGui import QImage

    rgba = calque.image.convert("RGBA")
    qimage = QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height,
                    QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


def _point_ancre(boite: QRectF, ancre: str) -> QPointF:
    """Le point de `boite` où se pose la poignée `ancre` ("no", "n", "ne", "e", …)."""
    x = {"o": boite.left(), "e": boite.right()}.get(ancre[-1], boite.center().x())
    y = {"n": boite.top(), "s": boite.bottom()}.get(ancre[0], boite.center().y())
    return QPointF(x, y)


def _etat_de_bulle(bulle) -> str:
    if bulle.manuelle is not None:
        return "manuelle"
    if not (bulle.affichee or "").strip():
        return "vide"
    return "normal"


class VuePlanche(QGraphicsView):
    """Vue avec zoom à la molette et ajustement à la fenêtre."""

    # Le grossissement a changé — la barre d'outils l'affiche. Sans ce signal, rien ne disait
    # à quel zoom on était, et « Ajuster » paraissait inerte quand on n'avait pas zoomé.
    zoom_change = Signal()

    def __init__(self, scene: ScenePlanche, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(40, 40, 44)))

    def wheelEvent(self, event) -> None:
        facteur = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(facteur, facteur)
        self.zoom_change.emit()

    def ajuster(self) -> None:
        rect = self.scene().sceneRect()
        if not rect.isEmpty():
            self.fitInView(rect, Qt.KeepAspectRatio)
        self.zoom_change.emit()
