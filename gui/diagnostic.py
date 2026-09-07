# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La page Diagnostic — **une destination, plus une capture de texte**.

## Ce qu'elle remplace

`Fenetre._capturer_diagnostic` redirigeait la sortie **console** des deux doctors dans un
`DialogueTexte`. Trois défauts, tous mesurés le 2026-09-06 : aucun geste n'était attaché à un
problème, rien n'était réutilisable, et le dialogue **bloquait** pendant l'appel réseau.

Ici, chaque manque porte son constat, sa conséquence et son geste — et un bouton quand le
geste est sûr. La structure vient de `core/diagnostic.py`, les décisions d'affichage de
`gui/vue_diagnostic.py` (sans Qt, testé sans écran), et il ne reste ici que des widgets.

## ⚠ Ce que cette page ne fait pas

- **elle ne sonde rien au chargement.** Elle s'ouvre en disant qu'aucun diagnostic n'a tourné,
  ce qui est vrai. Le `PLAN-31` a mesuré ce que coûte un démarrage qui en fait trop ;
- **elle ne télécharge rien toute seule.** Chaque bouton de réparation ouvre d'abord la
  licence, la source et la taille, et demande confirmation. `core.reparations.executer` refuse
  sans `consentement=True` ;
- **elle ne répare pas pendant un run.** Le même appel refuse avec `run_en_cours=True`, et la
  page le dit au lieu de griser un bouton sans explication ;
- **elle n'installe aucun logiciel système.** Un verdict dont la réparation est de classe
  `UTILISATEUR` n'a pas de bouton : il a une commande copiable et un lien.

## Le fil

Le diagnostic complet part dans le **fil de travail** de la fenêtre, comme les sondes de
l'accueil : sur un serveur arrêté, la section Ollama attend son délai (mesuré à 12,1 s le
2026-09-06). Sur le fil d'affichage, ce serait douze secondes de fenêtre gelée.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from core import diagnostic as diag

from . import theme
from . import vue_diagnostic as vue

#: Le rôle de thème par gravité. ⚠ Il DOUBLE le symbole, il ne le remplace pas : un état
#: annoncé par la seule couleur est un état que 8 % des hommes ne lisent pas (`PLAN-19`).
ROLES = {diag.BLOQUANT: "erreur", diag.DEGRADE: "avertissement",
         diag.INFORMATION: "faible", diag.CONFORME: "succes"}


class CarteVerdict(QFrame):
    """Un point du diagnostic : constat, conséquence, geste, et le bouton s'il est permis."""

    demande_reparation = Signal(str)

    def __init__(self, verdict, parent=None):
        super().__init__(parent)
        self.verdict = verdict
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(theme.Espacement.M, theme.Espacement.S,
                                   theme.Espacement.M, theme.Espacement.S)
        colonne.setSpacing(theme.Espacement.XS)

        self.constat = QLabel(f"{verdict.symbole} {verdict.constat}")
        self.constat.setWordWrap(True)
        self.constat.setAccessibleName(
            f"{diag.PHRASES_GRAVITE.get(verdict.gravite, '')} — {verdict.constat}")
        theme.poser_role(self.constat, ROLES.get(verdict.gravite, "faible"))
        colonne.addWidget(self.constat)

        if verdict.consequence:
            consequence = QLabel(verdict.consequence)
            consequence.setWordWrap(True)
            colonne.addWidget(consequence)

        # ⚠ Critère 4 du `PLAN-36` : aucun verdict non conforme ne s'affiche sans geste.
        # `phrase_geste` garantit qu'il y a toujours quelque chose — au pire « hors périmètre »,
        # explicitement.
        geste = vue.phrase_geste(verdict)
        if geste:
            self.geste = QLabel("→ " + geste)
            self.geste.setWordWrap(True)
            self.geste.setTextInteractionFlags(Qt.TextSelectableByMouse)
            theme.poser_role(self.geste, "faible")
            colonne.addWidget(self.geste)

        # ⚠ **La licence, dans le CORPS de la page** — lot 38. Elle n'était visible qu'en
        # infobulle du bouton et dans la boîte de confirmation, c'est-à-dire APRÈS le clic,
        # alors que le geste promettait « licence affichée avant ». Une promesse tenue par une
        # infobulle n'est pas tenue.
        licence = vue.phrase_licence(verdict)
        if licence:
            self.licence = QLabel(licence)
            self.licence.setWordWrap(True)
            self.licence.setTextInteractionFlags(Qt.TextSelectableByMouse)
            theme.poser_role(self.licence, "faible")
            colonne.addWidget(self.licence)

        reparation = vue.bouton_pour(verdict)
        if reparation is not None:
            ligne = QHBoxLayout()
            bouton = QPushButton(reparation.libelle + f" ({reparation.taille_lisible})")
            bouton.setToolTip(reparation.consigne())
            bouton.clicked.connect(
                lambda _c=False, i=reparation.identifiant: self.demande_reparation.emit(i))
            ligne.addWidget(bouton)
            ligne.addStretch(1)
            colonne.addLayout(ligne)


class CartePoids(QFrame):
    """Un poids qu'Angelith sait récupérer — sa licence, sa taille, son état, son bouton.

    ⚠ **Elle existe même quand tout va bien.** `CarteVerdict` ne s'affiche que sur un problème ;
    or « télécharger un poids de manière indépendante » est un GESTE, pas une réparation
    d'erreur. Deux des quatre réparations automatiques du dépôt (`poids_texte`, `modele_ocr`)
    n'avaient d'ailleurs aucun verdict, donc aucun bouton, donc aucun moyen d'être déclenchées
    depuis l'interface."""

    demande_reparation = Signal(str)

    def __init__(self, poids, parent=None):
        super().__init__(parent)
        self.poids = poids
        reparation = poids.reparation
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(theme.Espacement.M, theme.Espacement.S,
                                   theme.Espacement.M, theme.Espacement.S)
        colonne.setSpacing(theme.Espacement.XS)

        self.titre = QLabel(f"{reparation.libelle} — {reparation.taille_lisible}")
        self.titre.setWordWrap(True)
        colonne.addWidget(self.titre)

        self.etat = QLabel(vue.PHRASES_ETAT_POIDS.get(poids.etat, ""))
        self.etat.setWordWrap(True)
        self.etat.setAccessibleName(f"{reparation.libelle} — {poids.etat or 'non mesuré'}")
        theme.poser_role(self.etat, "faible")
        colonne.addWidget(self.etat)

        # ⚠ La licence AVANT le bouton, dans le corps, en toutes lettres. C'est la moitié du
        # défaut que ce lot ferme : elle n'était visible qu'en infobulle et après le clic.
        detail = f"\n{reparation.licence_url}" if reparation.licence_url else ""
        self.licence = QLabel(f"Licence : {reparation.licence}{detail}")
        self.licence.setWordWrap(True)
        self.licence.setTextInteractionFlags(Qt.TextSelectableByMouse)
        theme.poser_role(self.licence, "faible")
        colonne.addWidget(self.licence)

        if reparation.note:
            self.note = QLabel(reparation.note)
            self.note.setWordWrap(True)
            theme.poser_role(self.note, "faible")
            colonne.addWidget(self.note)

        if poids.recuperable:
            ligne = QHBoxLayout()
            self.bouton = QPushButton("Télécharger")
            self.bouton.setToolTip(reparation.consigne())
            self.bouton.clicked.connect(
                lambda _c=False, i=reparation.identifiant: self.demande_reparation.emit(i))
            ligne.addWidget(self.bouton)
            ligne.addStretch(1)
            colonne.addLayout(ligne)


class PanneauDiagnostic(QWidget):
    """La destination « Diagnostic ». Elle n'inspecte rien tant qu'on ne le lui demande pas."""

    #: Lancer le diagnostic complet. `bool` = interroger le serveur de modèles.
    demande_diagnostic = Signal(bool)
    #: Lancer une réparation, par son identifiant de `core/reparations.py`.
    demande_reparation = Signal(str)
    #: Ouvrir la sortie console brute — le `DialogueTexte` d'avant, gardé pour qui script.
    demande_texte = Signal()

    PARCOURS: tuple[str, ...] = ("case_reseau", "bouton_lancer", "bouton_texte")

    def __init__(self, parent=None, config: dict | None = None):
        super().__init__(parent)
        self._sections: tuple = ()
        self._config = config
        self._construire()

    def poser_config(self, config: dict) -> None:
        """La configuration sert au bloc « Poids et modèles », qui lit où chaque poids doit
        atterrir. Séparée du constructeur pour que la page reste construisible sans elle."""
        self._config = config
        self._redessiner()

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(theme.Espacement.XL, theme.Espacement.L,
                                   theme.Espacement.XL, theme.Espacement.L)
        colonne.setSpacing(theme.Espacement.M)

        self.titre = QLabel("Diagnostic")
        theme.poser_role(self.titre, "titre")
        self.titre.setAccessibleName("Diagnostic de l'installation")
        colonne.addWidget(self.titre)

        self.resume = QLabel(vue.PHRASE_VIERGE)
        self.resume.setWordWrap(True)
        colonne.addWidget(self.resume)

        self.utilisables = QLabel("")
        self.utilisables.setWordWrap(True)
        theme.poser_role(self.utilisables, "faible")
        colonne.addWidget(self.utilisables)

        ligne = QHBoxLayout()
        self.bouton_lancer = QPushButton("Lancer le diagnostic")
        self.bouton_lancer.setToolTip(vue.PHRASE_COUT)
        self.bouton_lancer.clicked.connect(
            lambda: self.demande_diagnostic.emit(self.case_reseau.isChecked()))
        ligne.addWidget(self.bouton_lancer)
        self.case_reseau = QCheckBox("interroger le serveur de modèles")
        self.case_reseau.setChecked(True)
        self.case_reseau.setToolTip(vue.PHRASE_COUT)
        ligne.addWidget(self.case_reseau)
        self.case_conformes = QCheckBox("montrer les points conformes")
        self.case_conformes.setToolTip(
            "Par défaut la page ne montre que ce qui demande un geste : quatorze lignes « ✓ » "
            "ne se lisent pas, elles se comptent.")
        self.case_conformes.toggled.connect(lambda _c: self._redessiner())
        ligne.addWidget(self.case_conformes)
        ligne.addStretch(1)
        self.bouton_texte = QPushButton("Sortie console…")
        self.bouton_texte.setToolTip(
            "Le texte exact de « run.py --check » et « run_manga.py --check », pour le coller "
            "dans un rapport. C'est le même contenu, sans les gestes.")
        self.bouton_texte.clicked.connect(self.demande_texte.emit)
        ligne.addWidget(self.bouton_texte)
        colonne.addLayout(ligne)

        self.defilement = QScrollArea()
        self.defilement.setWidgetResizable(True)
        self.defilement.setFrameShape(QFrame.NoFrame)
        self.corps = QWidget()
        self.pile = QVBoxLayout(self.corps)
        self.pile.setContentsMargins(0, 0, 0, 0)
        self.pile.setSpacing(theme.Espacement.S)
        self.pile.addStretch(1)
        self.defilement.setWidget(self.corps)
        colonne.addWidget(self.defilement, 1)

        self._poser_parcours()
        # ⚠ Un premier dessin AVANT tout diagnostic : c'est ce qui fait apparaître le bloc
        # « Poids et modèles ». Sans lui, la page reste vide jusqu'à `poser_sections()`, et
        # télécharger un poids redeviendrait un geste enfermé derrière « Lancer le
        # diagnostic » — c'est-à-dire une réparation d'erreur, ce qu'il n'est pas.
        self._redessiner()

    def _poser_parcours(self) -> None:
        precedent = None
        for nom in self.PARCOURS:
            widget = getattr(self, nom, None)
            if widget is None:
                continue
            if precedent is not None:
                QWidget.setTabOrder(precedent, widget)
            precedent = widget

    # ------------------------------------------------------------------ #

    def marquer_en_cours(self, en_cours: bool) -> None:
        """Le bouton dit ce qui se passe. ⚠ Il n'est pas seulement grisé : un bouton grisé
        sans texte ne dit pas s'il travaille ou s'il est interdit."""
        self.bouton_lancer.setEnabled(not en_cours)
        self.bouton_lancer.setText("Diagnostic en cours…" if en_cours
                                   else "Lancer le diagnostic")

    def poser_sections(self, sections) -> None:
        """Pose le résultat d'un diagnostic. C'est le seul point d'entrée des données."""
        self._sections = tuple(sections)
        self._redessiner()

    def sections(self) -> tuple:
        return self._sections

    def _vider(self) -> None:
        """Retire tout sauf l'élastique de fin. ⚠ `setParent(None)` et pas `deleteLater()` :
        sans boucle d'événements — le cas d'un test — les widgets différés resteraient
        enfants de la pile et s'empileraient d'un diagnostic à l'autre."""
        while self.pile.count() > 1:
            element = self.pile.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.setParent(None)

    def _redessiner(self) -> None:
        self._vider()
        self.resume.setText(vue.phrase_resume(self._sections))
        self.utilisables.setText(vue.phrase_briques_utilisables(self._sections))
        groupes = vue.grouper(self._sections,
                              montrer_conformes=self.case_conformes.isChecked())
        index = 0
        for groupe in groupes:
            titre = QLabel(groupe.titre)
            theme.poser_role(titre, "accent")
            self.pile.insertWidget(index, titre)
            index += 1
            for verdict in groupe.verdicts:
                carte = CarteVerdict(verdict)
                carte.demande_reparation.connect(self.demande_reparation.emit)
                self.pile.insertWidget(index, carte)
                index += 1
            phrase = groupe.phrase_conformes()
            if phrase and not self.case_conformes.isChecked():
                compte = QLabel(phrase)
                theme.poser_role(compte, "faible")
                self.pile.insertWidget(index, compte)
                index += 1

        index = self._poser_poids(index)

    def _poser_poids(self, index: int) -> int:
        """Le bloc « Poids et modèles ». ⚠ Il ne dépend PAS d'un diagnostic lancé : il liste ce
        que l'application sait récupérer, avec la licence de chacun, qu'on ait cliqué sur
        « Lancer le diagnostic » ou non."""
        if self._config is None:
            return index
        poids = vue.poids_recuperables(self._config)
        if not poids:
            return index
        titre = QLabel("Poids et modèles")
        theme.poser_role(titre, "accent")
        self.pile.insertWidget(index, titre)
        index += 1
        intro = QLabel(vue.PHRASE_POIDS)
        intro.setWordWrap(True)
        theme.poser_role(intro, "faible")
        self.pile.insertWidget(index, intro)
        index += 1
        for entree in poids:
            carte = CartePoids(entree)
            carte.demande_reparation.connect(self.demande_reparation.emit)
            self.pile.insertWidget(index, carte)
            index += 1
        return index

    # ⚠ **Pas de `rafraichir_theme` ici, et c'est délibéré.** Cette page ne porte AUCUN
    # pixmap : les rôles posés par `theme.poser_role` sont des propriétés Qt, et la bascule de
    # thème réapplique la feuille de style à tous les widgets vivants de l'application. Une
    # méthode de rafraîchissement serait du code mort qui laisse croire qu'il se passe quelque
    # chose — c'est `gui/accueil.py` qui en a besoin, parce que ses cartes portent des icônes.
