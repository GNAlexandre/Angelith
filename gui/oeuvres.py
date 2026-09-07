# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La destination « Œuvres » — **la bibliothèque**, et ce qu'elle refuse d'afficher.

Le `PLAN-31` avait livré ici un état vide nommé, en disant ce qu'il ne faisait pas encore.
C'est ce lot-ci. Ce qui a changé : `bibliotheque.py` sait maintenant lire les 18 œuvres
de `sources/` sans ouvrir une image, et cette destination ne fait que le montrer.

## Ce que ce panneau ne fait pas, et pourquoi

⚠ **Pas de vignettes de planches.** Deux raisons, et la première suffit : ce sont des œuvres
sous droit d'auteur, et une grille de couvertures est la capture d'écran qu'on ne pourra
jamais montrer. `tools/captures_gui.py` porte déjà le raisonnement — « une capture d'écran de
l'éditeur montre une planche en pleine page : la verser dans `docs/` reviendrait à publier
une planche de manga dans le dépôt » — et il vaut pour toute la bibliothèque. La seconde
raison est le coût : dix-huit décodages d'image au premier affichage, pour une information
que le titre donne déjà.

⚠ **Aucun run n'est lancé depuis ici.** « Lancer » emmène à la destination du lanceur, avec
le tome présélectionné. Un bouton de bibliothèque qui démarrerait 131 planches serait la
pire action coûteuse sans garde-fou de l'application.

⚠ **Rien n'est supprimé.** Pas de « supprimer un tome » : la corbeille d'une application qui
gère des heures de GPU est un lot à elle seule, avec sa confirmation et sa réversibilité
(`PLAN-34` §4).

## Où vivent les décisions

⚠ Rien de ce qui **décide** n'est écrit ici : les colonnes, les filtres, les pastilles et la
légende sont dans `gui/vue_oeuvres.py`, sans Qt, exactement comme `gui/pellicule.py` porte
celles de la pellicule. C'est ce qui les rend testables dans le job de CI qui n'installe pas
PySide6.

## La légende est obligatoire

`gui/dialogues.py:DialogueLegende` existe depuis le lot 19 pour les symboles de l'éditeur, et
pour la raison exacte qui vaut ici : **une pastille sans légende est une couleur**. Les états
sont donc dits par un CARACTÈRE (`●◐○↻`) doublé d'une infobulle en toutes lettres, et la
légende complète est dépliable dans le panneau — jamais par la couleur seule. Les libellés
viennent de `bibliotheque.LEGENDE_ETATS`, sans Qt, pour que la console et l'écran les
disent avec les mêmes mots.

## Le balayage ne bloque pas la fenêtre

`Inventaire.oeuvres()` coûte ~1,3 s sur les 18 œuvres du corpus (mesuré, cf.
`docs/mesures/bibliotheque-2026-09-05.md`). C'est peu, mais c'est **treize fois** le seuil au
delà duquel un gel se voit : il part donc sur le fil de TRAVAIL, en `GENRE_BIBLIOTHEQUE` —
un genre **sans verrou**, parce qu'il ne fait que lire des entrées de répertoire — et le
panneau affiche « Lecture… » en attendant. Les affichages suivants sont mémoïsés : 1,4 ms.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

import bibliotheque as biblio

from . import theme
from .vue_oeuvres import (COLONNES, FILTRES_BRIQUE, FILTRES_STATUT, date_lisible,
                          detail_avancement, pastilles, retenu, texte_legende)

# ⚠ Les colonnes, les filtres, les pastilles et la légende vivent dans `gui/vue_oeuvres.py`,
# **sans Qt** : ce sont des décisions, et le dépôt les teste sans écran (cf. `gui/__init__.py`,
# la couche « les décisions »). Ici il ne reste que des widgets.


class PanneauOeuvres(QWidget):
    """La bibliothèque : une liste, des filtres, une légende, et les gestes d'un tome."""

    demande_creation = Signal()
    demande_sources = Signal()
    #: `(projet, tome, brique)` — la fenêtre décide de la destination à ouvrir.
    demande_lancement = Signal(str, str, str)
    demande_retouche = Signal(str, str)
    demande_export_glossaire = Signal(str, str)
    demande_exports = Signal(str, str)
    demande_dossier = Signal(str)
    #: Émis quand le panneau veut un balayage : la fenêtre le fait faire hors du fil d'affichage.
    demande_balayage = Signal()

    #: L'ordre de tabulation. Déclaré — cf. le critère 6 du `PLAN-19`.
    PARCOURS: tuple[str, ...] = (
        "champ_recherche", "choix_brique", "choix_statut", "case_legende", "arbre",
        "bouton_lancer", "bouton_retoucher", "bouton_exports", "bouton_glossaire",
        "bouton_dossier", "bouton_creer", "bouton_sources", "bouton_rafraichir")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._oeuvres: list = []
        self._infos: dict[tuple[str, str], object] = {}
        self._racine = Path("sources")
        self._construire()

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(theme.Espacement.XL, theme.Espacement.L,
                                   theme.Espacement.XL, theme.Espacement.L)
        colonne.setSpacing(theme.Espacement.S)

        self.titre = QLabel("Œuvres")
        theme.poser_role(self.titre, "titre")
        self.titre.setAccessibleName("Œuvres")
        colonne.addWidget(self.titre)

        self.chemin = QLabel("")
        self.chemin.setWordWrap(True)
        self.chemin.setTextInteractionFlags(Qt.TextSelectableByMouse)
        theme.poser_role(self.chemin, "mono")
        self.chemin.setAccessibleName("Dossier de sources")
        colonne.addWidget(self.chemin)

        filtres = QHBoxLayout()
        self.champ_recherche = QLineEdit()
        self.champ_recherche.setPlaceholderText("Filtrer par titre ou tome…")
        self.champ_recherche.setClearButtonEnabled(True)
        self.champ_recherche.textChanged.connect(self._remplir)
        self.choix_brique = QComboBox()
        for code, libelle in FILTRES_BRIQUE:
            self.choix_brique.addItem(libelle, code)
        self.choix_brique.currentIndexChanged.connect(self._remplir)
        self.choix_statut = QComboBox()
        for code, libelle in FILTRES_STATUT:
            self.choix_statut.addItem(libelle, code)
        self.choix_statut.currentIndexChanged.connect(self._remplir)
        self.case_legende = QCheckBox("Légende")
        self.case_legende.setToolTip(
            "Le sens des pastilles. ⚠ L'état n'est JAMAIS dit par la couleur seule : chaque "
            "pastille est un caractère, et l'infobulle d'une ligne nomme chaque étape.")
        self.case_legende.toggled.connect(self._basculer_legende)
        filtres.addWidget(self.champ_recherche, 1)
        filtres.addWidget(self.choix_brique)
        filtres.addWidget(self.choix_statut)
        filtres.addWidget(self.case_legende)
        colonne.addLayout(filtres)

        self.legende = QLabel(texte_legende())
        self.legende.setWordWrap(True)
        self.legende.setVisible(False)
        theme.poser_role(self.legende, "faible")
        colonne.addWidget(self.legende)

        self.arbre = QTreeWidget()
        self.arbre.setColumnCount(len(COLONNES))
        self.arbre.setHeaderLabels([nom for nom, _ in COLONNES])
        entete = self.arbre.header()
        for rang, (_, aide) in enumerate(COLONNES):
            self.arbre.headerItem().setToolTip(rang, aide)
        entete.setStretchLastSection(False)
        self.arbre.setRootIsDecorated(True)
        self.arbre.setAlternatingRowColors(True)
        self.arbre.setSelectionMode(QAbstractItemView.SingleSelection)
        self.arbre.setUniformRowHeights(True)
        self.arbre.currentItemChanged.connect(lambda *_: self._maj_gestes())
        self.arbre.itemDoubleClicked.connect(lambda *_: self._retoucher())
        colonne.addWidget(self.arbre, 1)

        self.etat = QLabel("Lecture des œuvres…")
        self.etat.setWordWrap(True)
        theme.poser_role(self.etat, "faible")
        colonne.addWidget(self.etat)

        gestes = QHBoxLayout()
        self.bouton_lancer = QPushButton("Lancer…")
        self.bouton_lancer.setToolTip(
            "Ouvre la destination de lancement avec ce tome présélectionné. ⚠ Ne démarre "
            "AUCUN run : c'est le lanceur qui annonce le coût et qui décide.")
        self.bouton_lancer.clicked.connect(self._lancer)
        self.bouton_retoucher = QPushButton("Retoucher")
        self.bouton_retoucher.setToolTip("Ouvre ce tome dans l'éditeur de planches.")
        self.bouton_retoucher.clicked.connect(self._retoucher)
        self.bouton_exports = QPushButton("Sorties…")
        self.bouton_exports.setToolTip(
            "Ce qui existe sur le disque pour ce tome, avec sa date et sa taille — et ce "
            "qui n'existe pas, avec le geste qui le produirait et son coût.")
        self.bouton_exports.clicked.connect(self._exports)
        self.bouton_glossaire = QPushButton("Exporter le glossaire…")
        self.bouton_glossaire.setToolTip(
            "YAML (archive, aller-retour garanti), CSV ou Markdown (vues, perte nommée "
            "dans le fichier produit).")
        self.bouton_glossaire.clicked.connect(self._exporter_glossaire)
        self.bouton_dossier = QPushButton("Ouvrir le dossier")
        self.bouton_dossier.setToolTip("Ouvre le dossier de sources de cette œuvre.")
        self.bouton_dossier.clicked.connect(self._ouvrir_dossier)
        for bouton in (self.bouton_lancer, self.bouton_retoucher, self.bouton_exports,
                       self.bouton_glossaire, self.bouton_dossier):
            gestes.addWidget(bouton)
        gestes.addStretch(1)
        colonne.addLayout(gestes)

        pied = QHBoxLayout()
        self.bouton_creer = QPushButton("Nouveau projet…")
        self.bouton_creer.setToolTip(
            "Crée sources/<Projet>/<Tome>/<format>/ et y COPIE les images ou l'archive "
            "choisies. Tu peux aussi les faire glisser sur cette fenêtre.")
        self.bouton_creer.clicked.connect(self.demande_creation.emit)
        self.bouton_sources = QPushButton("Ouvrir le dossier de sources")
        self.bouton_sources.clicked.connect(self.demande_sources.emit)
        self.bouton_rafraichir = QPushButton("Rafraîchir")
        self.bouton_rafraichir.setToolTip(
            "Relit sources/ et build/. Rien n'est mis en cache sur le disque : ce que tu "
            "vois est l'état réel au moment de la lecture.")
        self.bouton_rafraichir.clicked.connect(self.demande_balayage.emit)
        pied.addWidget(self.bouton_creer)
        pied.addWidget(self.bouton_sources)
        pied.addStretch(1)
        pied.addWidget(self.bouton_rafraichir)
        colonne.addLayout(pied)

        self._poser_parcours()
        self._maj_gestes()

    def _poser_parcours(self) -> None:
        widgets = [getattr(self, nom) for nom in self.PARCOURS if hasattr(self, nom)]
        for avant, apres in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(avant, apres)

    # ------------------------------------------------------------------ #

    def poser_racine(self, racine: Path) -> None:
        """Affiche le dossier de sources — **le vrai**, celui que la config nomme."""
        self._racine = Path(racine)
        self.chemin.setText(str(racine))

    def poser_oeuvres(self, oeuvres) -> None:
        """Reçoit le résultat du balayage. Appelée depuis le fil d'affichage, jamais depuis
        le fil qui a balayé."""
        self._oeuvres = list(oeuvres)
        self._infos = {(t.projet, t.tome): t for o in self._oeuvres for t in o.tomes}
        self._remplir()

    def _basculer_legende(self, visible: bool) -> None:
        self.legende.setVisible(visible)

    # ------------------------------------------------------------------ #

    def _remplir(self) -> None:
        brique = self.choix_brique.currentData() or ""
        statut = self.choix_statut.currentData() or ""
        recherche = self.champ_recherche.text().strip()

        self.arbre.clear()
        montres = 0
        for oeuvre in self._oeuvres:
            tomes = [t for t in oeuvre.tomes if retenu(t, brique, statut, recherche)]
            if not tomes:
                continue
            parent = QTreeWidgetItem([
                oeuvre.projet,
                " + ".join(biblio.LIBELLES_BRIQUE.get(b, b) for b in oeuvre.briques),
                f"{len(tomes)} tome(s)", "", "",
                "—" if oeuvre.glossaire is None else str(oeuvre.glossaire), ""])
            parent.setData(0, Qt.UserRole, (oeuvre.projet, ""))
            parent.setToolTip(0, str(self._racine / oeuvre.projet))
            self.arbre.addTopLevelItem(parent)
            for info in tomes:
                enfant = QTreeWidgetItem([
                    info.tome, info.libelle_brique, info.compte, pastilles(info),
                    ", ".join(sorted(info.sorties)) or "—",
                    "—" if info.glossaire is None else str(info.glossaire),
                    date_lisible(info.dernier_run)])
                enfant.setData(0, Qt.UserRole, (info.projet, info.tome))
                infobulle = detail_avancement(info)
                for rang in range(len(COLONNES)):
                    enfant.setToolTip(rang, infobulle)
                parent.addChild(enfant)
                montres += 1
            parent.setExpanded(True)

        for rang in range(len(COLONNES)):
            self.arbre.resizeColumnToContents(rang)
        total = sum(len(o.tomes) for o in self._oeuvres)
        self.etat.setText(
            f"{montres} tome(s) affiché(s) sur {total}, {len(self._oeuvres)} œuvre(s). "
            + texte_legende())
        self._maj_gestes()

    # ------------------------------------------------------------------ #

    def selection(self):
        """Le `TomeInfo` sélectionné, ou `None` si c'est une œuvre (ou rien)."""
        item = self.arbre.currentItem()
        if item is None:
            return None
        return self._infos.get(item.data(0, Qt.UserRole) or ("", ""))

    def projet_selectionne(self) -> str:
        item = self.arbre.currentItem()
        if item is None:
            return ""
        return (item.data(0, Qt.UserRole) or ("", ""))[0]

    def _maj_gestes(self) -> None:
        """Un bouton grisé dit ce qu'il attend. Un bouton actif qui ne fait rien ment."""
        info = self.selection()
        projet = self.projet_selectionne()
        self.bouton_lancer.setEnabled(info is not None)
        self.bouton_exports.setEnabled(info is not None)
        self.bouton_dossier.setEnabled(bool(projet))
        # ⚠ Le glossaire est par ŒUVRE : le geste vaut aussi sur une ligne de projet, et il
        # n'a de sens que si l'œuvre en a un.
        self.bouton_glossaire.setEnabled(bool(projet) and self._a_un_glossaire(projet))
        # ⚠ La retouche édite des PLANCHES. La proposer sur un roman serait promettre un
        # écran qui s'ouvrirait vide.
        self.bouton_retoucher.setEnabled(
            info is not None and info.brique in (biblio.MANGA, biblio.WEBTOON))

    def _a_un_glossaire(self, projet: str) -> bool:
        return any(o.projet == projet and o.glossaire is not None for o in self._oeuvres)

    # ------------------------------------------------------------------ #

    def _lancer(self) -> None:
        info = self.selection()
        if info is not None:
            self.demande_lancement.emit(info.projet, info.tome, info.brique)

    def _retoucher(self) -> None:
        info = self.selection()
        if info is not None and info.brique in (biblio.MANGA, biblio.WEBTOON):
            self.demande_retouche.emit(info.projet, info.tome)

    def _exports(self) -> None:
        info = self.selection()
        if info is not None:
            self.demande_exports.emit(info.projet, info.tome)

    def _exporter_glossaire(self) -> None:
        projet = self.projet_selectionne()
        if projet:
            info = self.selection()
            self.demande_export_glossaire.emit(projet, info.tome if info else "")

    def _ouvrir_dossier(self) -> None:
        projet = self.projet_selectionne()
        if projet:
            self.demande_dossier.emit(projet)
