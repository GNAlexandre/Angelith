# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Éditeur de planche : voir, corriger une réplique, corriger une zone, relettrer.

## Ce que la 1.1.0 faisait mal, et que ce module corrige

**Tout figeait.** Les éditions de zone étaient synchrones sur le fil d'affichage — masques
numpy pleine page, réécriture de quatre fichiers — et le premier clic sur « Relire » déclenchait
`scan_volume`, donc l'extraction d'un CBZ entier. Tout passe désormais par la file
(`gui/travailleur.py`), et le verrou est **par planche** : relire une bulle de la planche 12
n'empêche plus de toucher à la 30.

**Les modèles ne restaient pas chauds.** Chaque « Retraduire » reconstruisait les agents,
relisait les prompts et rechargeait le glossaire YAML. Ils vivent maintenant dans un
`manga.services.Services` porté par la fenêtre.

**La saisie en cours était perdue.** Changer de bulle écrasait le champ sans un mot. Les
modifications non enregistrées sont désormais retenues dans des **brouillons** : elles
survivent à la navigation, la liste les marque, et rien n'est écrit sur disque sans un geste
explicite.

## Ce que le panneau ne fait toujours pas lui-même

Il n'écrit aucun fichier directement. Chaque action délègue :

| Action | Délégué à |
|---|---|
| ajouter / modifier / supprimer / scinder une zone | `manga.edition` |
| vider + lire + traduire une bulle (bouton unique) | `manga.edition.reprendre_zone` |
| corriger une réplique au clavier | `checkpoints.save_traduction_manuelle` |
| relettrer la planche | `process_volume(only_page=N, restart_from=…)` |

Le dernier point reste le plus important : **aucun chemin de rendu n'est réécrit ici**. Ce qui
sort de l'interface est, au bit près, ce que produirait `run_manga.py --page N --from …`.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap, QTransform
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
                               QLineEdit, QToolButton, QVBoxLayout, QWidget)

from manga import (checkpoints, document as doc_mod, edition, etat_planches, geometry,
                   recherche as rech_mod, recuperation)
from . import apercu as apercu_mod
from . import scene_planche as sp
from . import pellicule as pel
from .cache_apercu import CacheApercu, signature
from .modele_tome import Tome
from .travailleur import (GENRE_APERCU, GENRE_EDITION, GENRE_OCR, GENRE_REPRISE,
                          GENRE_TRADUCTION, GENRE_VIGNETTE, FilDeTravail, Tache)


# Séparateur de paragraphe des boîtes de dialogue.
SAUT_LIGNE = chr(10) * 2


class PanneauEditeur(QWidget):
    """Colonne planches · canevas · inspecteur de bulle."""

    journal = Signal(str, str)                  # (niveau, message) → onglet Journal
    demande_relettrage = Signal(int, str)       # (planche, étape de reprise)
    etat_document = Signal(bool)                # reste-t-il des modifications non écrites ?

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tome: Tome | None = None
        self.planche = None
        self.revision_ouverte = -1
        self.fil: FilDeTravail | None = None
        self.fil_lecture = None
        self.services = None
        self.cache = CacheApercu()
        # Un run global est en cours : aucune commande d'écriture ne doit se rouvrir,
        # même quand on navigue (`_afficher_bulle` réactive `bouton_rendre`).
        self._run_global = False
        # Filet contre un plantage. La 1.5.0 permet d'accumuler trente planches en
        # mémoire pendant une heure : une coupure de courant les perdait toutes.
        # 30 s, et seulement les planches modifiées — 13 à 41 ms par planche (mesuré).
        # Ce qui a déjà été écrit dans le miroir, par planche. Sans cette mémoire, le
        # minuteur réécrivait tout à chaque tic — cf. `sauver_brouillons`.
        self._empreintes_brouillons: dict = {}
        self._minuteur_brouillons = QTimer(self)
        self._minuteur_brouillons.setInterval(30_000)
        self._minuteur_brouillons.timeout.connect(self.sauver_brouillons)
        self._minuteur_brouillons.start()
        # `etat_planche` coûte 5,9 ms et l'interface le demande 150 fois par geste :
        # ouverture du tome, changement de filtre, rafraîchissement complet. Sans ce
        # cache, chacun de ces gestes gelait la fenêtre ~890 ms (mesuré, cache OS chaud).
        self.cache_etats = etat_planches.CacheEtats()
        # `_item_de` balayait la liste entière à chaque appel, dans une boucle sur toutes
        # les planches : `rafraichir_pellicule` était donc en O(n²).
        self._items: dict = {}
        # ⚠ Brouillons et documents sont désormais PAR PLANCHE.
        #
        # Ils étaient uniques, et c'est ce qui obligeait à enregistrer planche par planche :
        # changer de planche ouvrait une boîte « Enregistrer / Abandonner / Rester », donc on
        # ne pouvait pas corriger dix planches puis tout écrire d'un coup. `DocumentPlanche`
        # était pourtant déjà par planche, avec son historique et son contrôle de révision
        # propres — seul l'éditeur n'en tenait qu'un.
        self._brouillons_par_planche: dict[int, dict[int, str]] = {}
        self.documents: dict[int, doc_mod.DocumentPlanche] = {}
        # Ce qu'il faut pour composer un aperçu, figé sur le FIL D'AFFICHAGE et lu par la voie
        # de lecture : celle-ci ne doit jamais parcourir un état que l'utilisateur modifie.
        self._plans_apercu: dict[int, tuple] = {}
        # Planches dont on veut l'aperçu COMPOSÉ (les autres n'auront que leur vignette).
        self._fenetre_apercu: set[int] = set()
        self.fenetre_prechargement = 10
        self._index_affiche = -1
        self._planches_verrouillees: set = set()
        # ── Le direct ──────────────────────────────────────────────────────────────────
        # L'aperçu de la planche affichée, gardé sous la main : c'est lui qui porte les styles
        # dont le chemin rapide a besoin. Sans cette référence, chaque frappe redemanderait une
        # composition complète à 1,37 s.
        self._apercu_courant = None
        # Coalescence de la frappe. 180 ms : au-dessus de l'intervalle inter-touches d'un
        # dactylo moyen (~200 ms à 60 mots/min), donc un relettrage par PAUSE et non par
        # caractère ; en dessous du seuil de perception d'une latence (~250 ms).
        self._minuteur_apercu = QTimer(self)
        self._minuteur_apercu.setSingleShot(True)
        self._minuteur_apercu.setInterval(180)
        self._minuteur_apercu.timeout.connect(self._relettrer_saisie)
        # Dépôt du corps dans le document. ⚠ Bien plus long que l'aperçu, et pour une raison
        # précise : `poser_mise_en_page` empile un pas d'historique. Tenir la flèche du réglage
        # deux secondes à 180 ms en produirait onze, et « Annuler » remonterait le temps par
        # crans de police. À 600 ms avec redémarrage, un seul pas par valeur posée.
        self._minuteur_corps = QTimer(self)
        self._minuteur_corps.setSingleShot(True)
        self._minuteur_corps.setInterval(600)
        self._minuteur_corps.timeout.connect(self._deposer_corps)
        self._corps_en_attente: tuple[int, int] | None = None
        # Étranglement ADAPTATIF du relettrage pendant un glisser (cf.
        # `_rafraichir_bulle_rapide`).
        self._chrono_rapide = QElapsedTimer()
        self._cout_rapide_ms = 0.0
        self._dernier_rapide = QElapsedTimer()
        self._dernier_rapide.start()
        # La zone à resélectionner après une édition : `reading_order` peut avoir permuté les
        # index, donc on la retrouve par sa GÉOMÉTRIE (cf. `_resuivre_zone`).
        self._zone_a_resuivre: tuple[int, tuple] | None = None
        self._construire()

    # ------------------------------------------------------------------ #

    @property
    def document(self) -> doc_mod.DocumentPlanche | None:
        """Le document de la planche affichée."""
        return self.documents.get(self.planche.index) if self.planche else None

    @property
    def _brouillons(self) -> dict[int, str]:
        """Répliques tapées mais non retenues, pour la planche affichée.

        Créé à la demande : une planche seulement consultée n'a pas à peser."""
        if self.planche is None:
            return {}
        return self._brouillons_par_planche.setdefault(self.planche.index, {})

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        self.liste_planches = QListWidget()
        # Une bande de vignettes plutôt qu'une liste de noms de fichiers : sur 150 planches,
        # `12   page_0012.png` obligeait à ouvrir pour savoir ce qu'on regardait.
        self.liste_planches.setViewMode(QListWidget.IconMode)
        self.liste_planches.setIconSize(QSize(pel.LARGEUR, pel.HAUTEUR_ICONE))
        # ⚠ `setGridSize` n'est PAS un réglage d'esthétique : c'est lui qui fait calculer les
        # positions sur une grille fixe au lieu de les dériver du pixmap réel. Sans lui, un
        # item pas encore vignetté a la taille de son texte seul, puis grandit SUR PLACE quand
        # l'icône arrive — Qt redimensionne le rectangle sans refaire la disposition, et la
        # bande devient un empilement illisible pendant tout le chargement (mesuré : 2 767
        # paires d'items qui se chevauchent sur 150 planches). Cf. `pellicule.HAUTEUR_CELLULE`.
        self.liste_planches.setGridSize(QSize(pel.LARGEUR_CELLULE, pel.HAUTEUR_CELLULE))
        self.liste_planches.setResizeMode(QListWidget.Adjust)
        self.liste_planches.setMovement(QListWidget.Static)
        self.liste_planches.setSpacing(6)
        self.liste_planches.setWordWrap(True)
        # Cohérent une fois les tailles fixes, et loin d'être gratuit : poser les 150 vignettes
        # passe de 78 ms à 3 ms, parce que Qt cesse d'interroger le delegate item par item.
        self.liste_planches.setUniformItemSizes(True)
        self.liste_planches.currentRowChanged.connect(self._sur_changement_planche)

        self.choix_filtre = QComboBox()
        self.choix_filtre.addItems(list(pel.FILTRES))
        self.choix_filtre.setToolTip(
            "Ne montrer que les planches qui demandent une attention — les mêmes que celles "
            "que « Enregistrer les modifications du projet » relettrera.")
        self.choix_filtre.currentTextChanged.connect(lambda _t: self._appliquer_filtre())

        # Recherche plein-tome. Sur ENTRÉE et non à chaque touche : un balayage complet
        # coûte ~210 ms sur 150 planches (mesuré), ce qui est confortable pour une recherche
        # validée et beaucoup trop cher à chaque frappe.
        self.champ_recherche = QLineEdit()
        self.champ_recherche.setPlaceholderText("Chercher dans le tome (Entrée)…")
        self.champ_recherche.setClearButtonEnabled(True)
        self.champ_recherche.setToolTip(
            "Cherche dans les répliques, les corrections manuelles et l'OCR japonais.\n"
            "Insensible à la casse et aux accents ; un clic sur un résultat ouvre la bulle.")
        self.champ_recherche.returnPressed.connect(self._chercher)

        self.liste_resultats = QListWidget()
        self.liste_resultats.setMaximumHeight(150)
        self.liste_resultats.hide()
        self.liste_resultats.itemActivated.connect(self._aller_au_resultat)
        self.liste_resultats.itemClicked.connect(self._aller_au_resultat)

        colonne = QWidget()
        vcolonne = QVBoxLayout(colonne)
        vcolonne.setContentsMargins(0, 0, 0, 0)
        vcolonne.addWidget(self.champ_recherche)
        vcolonne.addWidget(self.liste_resultats)
        vcolonne.addWidget(self.choix_filtre)
        vcolonne.addWidget(self.liste_planches, 1)
        self.colonne_planches = colonne

        self.scene = sp.ScenePlanche(self)
        self.vue = sp.VuePlanche(self.scene)
        self.scene.zone_choisie.connect(self._sur_choix_zone)
        self.scene.zone_dessinee.connect(self._sur_zone_dessinee)
        self.scene.zone_modifiee.connect(self._sur_zone_modifiee)
        self.scene.coupe_dessinee.connect(self._sur_coupe)
        self.scene.texte_deplace.connect(self._sur_texte_deplace)
        self.scene.zone_ouverte.connect(self._ouvrir_bulle)
        # Gestes CONTINUS. C'est l'éditeur qui les étrangle : lui seul sait ce que coûte un
        # ré-habillage, et il le mesure (cf. `_rafraichir_bulle_rapide`).
        self.scene.texte_glisse.connect(self._sur_texte_glisse)
        self.scene.zone_en_cours.connect(self._sur_zone_en_cours)
        self.scene.zone_retaillee.connect(self._sur_zone_retaillee)

        centre = QWidget()
        vlayout = QVBoxLayout(centre)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.addLayout(self._barre_outils())
        vlayout.addWidget(self.vue, 1)
        # Ce que le bouton grisé laissait sans réponse : où en est cette planche, et
        # reste-t-il du travail en attente ailleurs dans le tome.
        self.ligne_etat = QLabel("")
        self.ligne_etat.setStyleSheet("color: #9aa; font-size: 11px;")
        vlayout.addWidget(self.ligne_etat)
        self.etat_planche = QLabel("")
        self.etat_planche.setStyleSheet("color: #d09030;")
        vlayout.addWidget(self.etat_planche)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.colonne_planches)
        splitter.addWidget(centre)
        splitter.addWidget(self._inspecteur())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 860, 380])

        principal = QHBoxLayout(self)
        principal.setContentsMargins(4, 4, 4, 4)
        principal.addWidget(splitter)

    def _barre_outils(self) -> QHBoxLayout:
        barre = QHBoxLayout()
        self._groupe_modes = QButtonGroup(self)
        self._groupe_modes.setExclusive(True)
        outils = [
            (sp.MODE_CHOISIR, "Choisir", "Sélectionner une bulle (aucune modification)"),
            (sp.MODE_RECTANGLE, "+ Rectangle", "Tracer une bulle manquée, masque rectangulaire"),
            (sp.MODE_ELLIPSE, "+ Ellipse", "Tracer une bulle manquée, masque elliptique — la "
                                           "forme d'un ballon, et pas de coins repeints"),
            (sp.MODE_MODIFIER, "Redessiner",
             "Repart d'une forme NEUVE (rectangle ou ellipse) pour la bulle sélectionnée, et "
             "remet son OCR et sa traduction à zéro — les pixels lus ne sont plus les mêmes.\n"
             "Pour simplement agrandir, rétrécir ou déplacer une bulle EN GARDANT son texte, "
             "tire ses poignées en mode Choisir."),
            (sp.MODE_SCINDER, "Scinder", "Tracer un trait au travers de la bulle sélectionnée "
                                         "pour la couper en deux"),
        ]
        for mode, libelle, aide in outils:
            bouton = QToolButton()
            bouton.setText(libelle)
            bouton.setToolTip(aide)
            bouton.setCheckable(True)
            bouton.clicked.connect(lambda _c, m=mode: self._changer_mode(m))
            self._groupe_modes.addButton(bouton)
            barre.addWidget(bouton)
            if mode == sp.MODE_CHOISIR:
                bouton.setChecked(True)

        self.bouton_supprimer = QPushButton("Supprimer la zone")
        self.bouton_supprimer.setToolTip("Retire une fausse détection. Les autres bulles "
                                         "gardent leur texte, et le dessin d'origine revient "
                                         "sous la zone retirée.")
        self.bouton_supprimer.clicked.connect(self._supprimer_zone)
        barre.addSpacing(16)
        barre.addWidget(self.bouton_supprimer)
        barre.addStretch(1)

        self.bouton_annuler = QPushButton("Annuler")
        self.bouton_annuler.setShortcut("Ctrl+Z")
        self.bouton_annuler.setToolTip("Annule le dernier geste. L'historique remonte "
                                       "jusqu'à l'ouverture de la planche.")
        self.bouton_annuler.clicked.connect(self._annuler)
        self.bouton_refaire = QPushButton("Refaire")
        self.bouton_refaire.setShortcut("Ctrl+Y")
        self.bouton_refaire.clicked.connect(self._refaire)
        # ⚠ « Enregistrer la planche », pas « Enregistrer » : l'inspecteur porte déjà
        # « Garder ma version », et deux boutons dont le nom promet une écriture, dont l'un
        # est presque toujours grisé, ne se distinguent pas. Le grisé n'était d'ailleurs pas
        # un défaut mais l'absence de modification — que rien n'annonçait, d'où la ligne
        # d'état sous la barre.
        self.bouton_enregistrer_doc = QPushButton("Enregistrer la planche")
        self.bouton_enregistrer_doc.setShortcut("Ctrl+S")
        self.bouton_enregistrer_doc.setToolTip(
            "Écrit sur le disque ce qui a été modifié sur CETTE planche (Ctrl+S). Rien n'est "
            "écrit avant — c'est ce qui permet d'essayer, puis de revenir en arrière.\n"
            "Grisé = cette planche n'a aucune modification en attente.\n"
            "Pour tout écrire et réassembler : « Enregistrer les modifications du projet ».")
        self.bouton_enregistrer_doc.clicked.connect(self.enregistrer_document)
        barre.addWidget(self.bouton_annuler)
        barre.addWidget(self.bouton_refaire)
        barre.addWidget(self.bouton_enregistrer_doc)
        barre.addSpacing(12)

        self.bouton_finale = QToolButton()
        self.bouton_finale.setText("Comparer au rendu du pipeline")
        self.bouton_finale.setCheckable(True)
        self.bouton_finale.setToolTip(
            "Bascule entre la planche NETTOYÉE — celle qui porte les calques de texte "
            "déplaçables — et la page telle que le pipeline l'a écrite. Comparer reste "
            "utile, mais on ne peut rien déplacer sur une image aplatie.\n"
            "Le retour est instantané : l'aperçu reste en cache.")
        self.bouton_finale.clicked.connect(self._basculer_fond)
        barre.addWidget(self.bouton_finale)

        # Groupe de zoom. « Ajuster » fonctionnait déjà, mais `_charger_planche` ajuste à
        # chaque planche : sans avoir zoomé d'abord, le bouton semblait inerte, et rien à
        # l'écran ne disait à quel grossissement on était.
        barre.addSpacing(12)
        self.bouton_zoom_moins = QToolButton()
        self.bouton_zoom_moins.setText("−")
        self.bouton_zoom_moins.setToolTip("Dézoomer")
        self.bouton_zoom_moins.clicked.connect(lambda: self._zoomer(1 / 1.25))
        self.etiquette_zoom = QLabel("—")
        self.etiquette_zoom.setMinimumWidth(52)
        self.etiquette_zoom.setAlignment(Qt.AlignCenter)
        self.bouton_zoom_plus = QToolButton()
        self.bouton_zoom_plus.setText("+")
        self.bouton_zoom_plus.setToolTip("Zoomer")
        self.bouton_zoom_plus.clicked.connect(lambda: self._zoomer(1.25))
        self.bouton_ajuster = QPushButton("Ajuster (F)")
        self.bouton_ajuster.setShortcut("F")
        self.bouton_ajuster.setToolTip("Ramène la planche entière dans la fenêtre.")
        self.bouton_ajuster.clicked.connect(self._ajuster)
        self.bouton_garder_zoom = QToolButton()
        self.bouton_garder_zoom.setText("🔒")
        self.bouton_garder_zoom.setCheckable(True)
        self.bouton_garder_zoom.setToolTip(
            "Garder le cadrage d'une planche à l'autre.\n"
            "Comparer la même zone sur deux planches consécutives est le geste de relecture "
            "par excellence — sans cette bascule, on rezoome à chaque changement.\n"
            "L'ajustement reprend tout seul si la planche suivante n'a pas les mêmes "
            "dimensions.")
        for widget in (self.bouton_zoom_moins, self.etiquette_zoom, self.bouton_zoom_plus,
                       self.bouton_ajuster, self.bouton_garder_zoom):
            barre.addWidget(widget)
        self.vue.zoom_change.connect(self._maj_zoom)
        return barre

    def _zoomer(self, facteur: float) -> None:
        self.vue.scale(facteur, facteur)
        self._maj_zoom()

    def _ajuster(self) -> None:
        self.vue.ajuster()
        self._maj_zoom()

    def _maj_zoom(self) -> None:
        self.etiquette_zoom.setText(f"{self.vue.transform().m11() * 100:.0f} %")

    def _cadrage(self):
        """Instantané de ce qu'on regarde : grossissement et point visé."""
        rect = self.scene.sceneRect()
        if rect.isEmpty():
            return None
        return (rect.size(), QTransform(self.vue.transform()),
                self.vue.mapToScene(self.vue.viewport().rect().center()))

    def _reprendre_cadrage(self, avant) -> None:
        """Restaure le cadrage précédent, ou ajuste.

        ⚠ On ne le restaure que si la planche fait la MÊME taille. À grossissement égal sur
        une planche plus petite, le point qu'on regardait tombe hors de l'image : on
        découvrirait du vide, ce qui est pire que d'avoir reperdu son zoom."""
        if avant is None or not self.bouton_garder_zoom.isChecked():
            self.vue.ajuster()
            return
        taille, transfo, centre = avant
        if self.scene.sceneRect().size() != taille:
            self.vue.ajuster()
            return
        self.vue.setTransform(transfo)
        self.vue.centerOn(centre)
        self.vue.zoom_change.emit()

    def _inspecteur(self) -> QWidget:
        panneau = QWidget()
        layout = QVBoxLayout(panneau)

        self.liste_bulles = QListWidget()
        self.liste_bulles.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste_bulles.currentRowChanged.connect(self._sur_choix_liste)
        layout.addWidget(QLabel("Bulles (ordre de lecture)"))
        layout.addWidget(self.liste_bulles, 1)

        boite = QGroupBox("Bulle sélectionnée")
        forme = QFormLayout(boite)
        self.champ_ocr = QPlainTextEdit()
        self.champ_ocr.setReadOnly(True)
        self.champ_ocr.setMaximumHeight(70)
        self.champ_ocr.setPlaceholderText("japonais lu par l'OCR")
        self.champ_trad = QPlainTextEdit()
        self.champ_trad.setMaximumHeight(90)
        self.champ_trad.setPlaceholderText("réplique française")
        self.champ_trad.textChanged.connect(self._sur_saisie)
        forme.addRow("OCR", self.champ_ocr)
        forme.addRow("Réplique", self.champ_trad)

        self.etiquette_origine = QLabel("—")
        self.etiquette_origine.setWordWrap(True)
        forme.addRow("Origine", self.etiquette_origine)

        # ⚠ Le corps se règle ICI, et pas seulement en tirant sur une bulle : une réplique qui
        # déborde d'un cheveu se corrige d'un cran, sans toucher à la géométrie. Une entrée de
        # `mise_en_page.json` SANS `rect` n'impose que la taille et laisse le masque du ballon
        # intact — fabriquer un rectangle depuis la bbox ferait écrire dans les coins.
        corps = QHBoxLayout()
        self.champ_corps = QSpinBox()
        self.champ_corps.setRange(0, 200)
        self.champ_corps.setSpecialValueText("auto")
        self.champ_corps.setSuffix(" px")
        self.champ_corps.setToolTip(
            "Corps de la police pour CETTE bulle. « auto » rend la taille au moteur, qui "
            "cherche la plus grande qui tienne.\n"
            "L'aperçu suit immédiatement ; rien n'est écrit avant Ctrl+S.")
        self.champ_corps.valueChanged.connect(self._sur_corps)
        self.bouton_corps_auto = QPushButton("Auto")
        self.bouton_corps_auto.setToolTip(
            "Rend le corps ET la position au moteur de mise en page : la bulle retrouve le "
            "lettrage calculé, comme si elle n'avait jamais été retouchée.")
        self.bouton_corps_auto.clicked.connect(self._rendre_au_moteur)
        corps.addWidget(self.champ_corps, 1)
        corps.addWidget(self.bouton_corps_auto)
        forme.addRow("Corps", corps)

        # ⚠ « Garder ma version » a disparu, et ce n'est pas une simplification cosmétique :
        # taper suffit désormais. L'aperçu suit la frappe, et `_enregistrer_planche` verse déjà
        # les brouillons dans `traduction_manuelle.json` au Ctrl+S. Le bouton ne servait plus
        # qu'à faire croire qu'un geste de plus était nécessaire pour VOIR ce qu'on écrivait.
        actions = QHBoxLayout()
        self.bouton_rendre = QPushButton("Rendre au modèle")
        self.bouton_rendre.setToolTip("Retire la correction manuelle et rétablit la réplique "
                                      "produite par le modèle.")
        self.bouton_rendre.clicked.connect(self._retirer_correction)
        actions.addWidget(self.bouton_rendre)
        actions.addStretch(1)
        forme.addRow(actions)

        machine = QHBoxLayout()
        self.bouton_relire = QPushButton("Relire (OCR)")
        self.bouton_relire.setToolTip("Relance manga-ocr sur cette seule bulle. Ne traduit pas.")
        self.bouton_relire.clicked.connect(self._relire_bulle)
        self.bouton_retraduire = QPushButton("Retraduire")
        self.bouton_retraduire.setToolTip("Un appel LLM court, une bulle, une réponse.")
        self.bouton_retraduire.clicked.connect(self._retraduire_bulle)
        machine.addWidget(self.bouton_relire)
        machine.addWidget(self.bouton_retraduire)
        forme.addRow(machine)

        self.bouton_reprendre = QPushButton("Vider, lire et traduire cette bulle")
        self.bouton_reprendre.setToolTip(
            "Le geste complet sur une bulle ajoutée à la main : la zone est vidée dans la "
            "planche nettoyée, relue par l'OCR, puis traduite. Sans le vidage, le français "
            "s'écrirait par-dessus le japonais.")
        self.bouton_reprendre.clicked.connect(self._reprendre_bulle)
        forme.addRow(self.bouton_reprendre)
        layout.addWidget(boite)

        appliquer = QGroupBox("Appliquer à la planche")
        vappliquer = QVBoxLayout(appliquer)
        self.choix_etape = QComboBox()
        self.choix_etape.addItem("Relettrer (aucun appel LLM)", "rendu")
        self.choix_etape.addItem("Renettoyer puis relettrer", "nettoyage")
        self.choix_etape.addItem("Retraduire toute la planche", "traduction")
        self.choix_etape.addItem("Relire l'OCR puis retraduire", "ocr")
        vappliquer.addWidget(self.choix_etape)
        self.bouton_appliquer = QPushButton("Appliquer")
        self.bouton_appliquer.setToolTip(
            "Relance l'orchestrateur sur cette seule planche — exactement "
            "`run_manga.py --page N --from …`.")
        self.bouton_appliquer.clicked.connect(self._appliquer)
        vappliquer.addWidget(self.bouton_appliquer)
        layout.addWidget(appliquer)
        return panneau

    # ------------------------------------------------------------------ #
    # Câblage
    # ------------------------------------------------------------------ #

    def brancher(self, fil: FilDeTravail, services, fil_lecture=None,
                 fenetre: int | None = None) -> None:
        """Reçoit les deux voies et les modèles chauds, tous portés par la fenêtre."""
        self.fil = fil
        self.services = services
        if fil_lecture is not None:
            self.fil_lecture = fil_lecture
            fil_lecture.brancher(self.fabriquer_vignette, self.composer_planche,
                                 self.travail_restant)
        if fenetre is not None:
            self.fenetre_prechargement = max(0, int(fenetre))

    def ouvrir(self, tome: Tome) -> None:
        self.tome = tome
        # Changer de tome jette tout : brouillons, documents et aperçus appartiennent au tome
        # qu'on quitte. Les garder collerait une réplique d'un tome sur une bulle d'un autre.
        self._brouillons_par_planche.clear()
        self.documents.clear()
        self._plans_apercu.clear()
        self.cache.vider()
        self.cache_etats.vider()
        self._empreintes_brouillons.clear()
        self._items.clear()
        if self.fil_lecture is not None:
            self.fil_lecture.oublier()
            self.fil_lecture.reessayer()
        self.planche = None
        self.liste_planches.clear()
        index = tome.index_planches()
        if not index:
            self.journal.emit("warn", f"{tome.projet} / {tome.tome} : aucune planche traitée "
                                      f"— lance un run d'abord.")
            self.scene.charger(None, [])
            return
        for numero, fichier in index:
            item = QListWidgetItem()
            # La grille suffit à supprimer les chevauchements ; le `sizeHint` supprime en plus
            # le SAUTILLEMENT. Mesuré : avec la grille seule, la hauteur d'un item passe de 12
            # à 299 px à l'arrivée de son icône — les positions restent justes, mais la bande
            # tressaute pendant tout le chargement. Avec le `sizeHint`, elle vaut 344 du début
            # à la fin et rien ne bouge jamais.
            item.setSizeHint(QSize(pel.LARGEUR_CELLULE, pel.HAUTEUR_CELLULE))
            item.setData(Qt.UserRole, numero)
            item.setData(Qt.UserRole + 1, fichier)
            self.liste_planches.addItem(item)
            self._items[int(numero)] = item
            self._parer_item(item, numero)
        self.liste_planches.setCurrentRow(0)
        # Après le remplissage : la reprise crée des documents, et `_charger_planche` vient
        # d'en créer un depuis le DISQUE pour la première planche. La reprise doit donc
        # passer en dernier pour l'emporter, et la planche affichée être relue ensuite.
        if self.proposer_reprise() and self.planche is not None:
            self._charger_planche(self.planche.index, garder_brouillons=True)

    def _etat(self, numero: int) -> dict:
        """L'état d'une planche, mémoïsé. **Le seul point d'accès** — y aller en direct
        rouvrirait le gel que `CacheEtats` supprime."""
        assert self.tome is not None
        return self.cache_etats.lire(self.tome.build_dir, numero)

    def _parer_item(self, item: QListWidgetItem, numero: int) -> None:
        """Pose la vignette, la légende et la couleur d'une planche."""
        if self.tome is None:
            return
        etat = self._etat(numero)
        item.setText(pel.legende(etat))
        item.setToolTip(etat_planches.libelle_etat(etat))
        teinte = pel.couleur(etat)
        item.setForeground(QColor(teinte) if teinte else QColor())
        chemin = pel.chemin_vignette(self.tome.build_dir, numero)
        item.setIcon(QIcon(str(chemin)) if chemin.exists() else self._icone_attente())

    def _icone_attente(self) -> QIcon:
        """Aplat neutre à la taille d'une vignette, pour une planche pas encore miniaturisée.

        Une cellule vide serait à la bonne taille — la grille s'en charge — mais ne dirait pas
        s'il reste du travail ou si la planche n'a simplement rien à montrer. Le cadre donne
        cette lecture d'un coup d'œil, et l'image le remplace à sa place exacte, sans que rien
        ne bouge.

        Construit UNE fois et gardé : c'est un objet Qt, donc du fil d'affichage — ce que
        `_parer_item` est déjà, et ce que la voie de lecture n'est pas."""
        icone = getattr(self, "_attente", None)
        if icone is None:
            plaque = QPixmap(pel.LARGEUR, pel.HAUTEUR_ICONE)
            plaque.fill(QColor("#e9e9ec"))
            icone = self._attente = QIcon(plaque)
        return icone

    def _item_de(self, numero: int) -> QListWidgetItem | None:
        return self._items.get(int(numero))

    def rafraichir_pellicule(self, numeros=None) -> None:
        """Remet à jour les pastilles — après un enregistrement ou un run."""
        vises = ([int(n) for n in numeros] if numeros is not None
                 else [int(self.liste_planches.item(l).data(Qt.UserRole))
                       for l in range(self.liste_planches.count())])
        for numero in vises:
            item = self._item_de(numero)
            if item is not None:
                self._parer_item(item, numero)
        self._appliquer_filtre()

    def _chercher(self) -> None:
        """Cherche dans tout le tome et liste les occurrences."""
        self.liste_resultats.clear()
        motif = self.champ_recherche.text().strip()
        if self.tome is None or not motif:
            self.liste_resultats.hide()
            return
        resultats = rech_mod.chercher(self.tome.build_dir, motif)
        for res in resultats:
            item = QListWidgetItem(
                f"{res['planche']} · bulle {res['bulle'] + 1} [{res['champ']}] "
                f"{res['extrait']}")
            item.setData(Qt.UserRole, (res["planche"], res["bulle"]))
            self.liste_resultats.addItem(item)
        if not resultats:
            # Une liste vide qui disparaît laisserait croire que la recherche n'a pas eu lieu.
            self.liste_resultats.addItem(QListWidgetItem(f"aucune occurrence de « {motif} »"))
        self.liste_resultats.show()
        self.journal.emit("info", f"Recherche « {motif} » : {len(resultats)} occurrence(s).")

    def _aller_au_resultat(self, item) -> None:
        """Ouvre la planche du résultat et met le curseur dans sa bulle."""
        cible = item.data(Qt.UserRole)
        if cible is None:
            return
        planche, bulle = cible
        if self.planche is None or self.planche.index != planche:
            self._reselectionner_planche(planche)
        if 0 <= bulle < self.liste_bulles.count():
            self._ouvrir_bulle(bulle)

    def _reselectionner_planche(self, numero: int) -> None:
        """Sélectionne une planche dans la pellicule, en la démasquant si le filtre la cache.

        ⚠ Sans le démasquage, cliquer un résultat sur une planche que le filtre courant
        écarte ne ferait **rien** — le pire des retours pour un clic délibéré."""
        for ligne in range(self.liste_planches.count()):
            item = self.liste_planches.item(ligne)
            if int(item.data(Qt.UserRole)) != numero:
                continue
            if self.liste_planches.isRowHidden(ligne):
                self.liste_planches.setRowHidden(ligne, False)
            self.liste_planches.setCurrentRow(ligne)
            return

    def _appliquer_filtre(self) -> None:
        """Masque les lignes que le filtre écarte.

        On MASQUE au lieu de reconstruire la liste : les indices de `_precharger` et la
        sélection courante restent ainsi valables, et revenir à « toutes » ne coûte rien."""
        if self.tome is None:
            return
        filtre = self.choix_filtre.currentText()
        predicat = pel.FILTRES.get(filtre)
        for ligne in range(self.liste_planches.count()):
            item = self.liste_planches.item(ligne)
            numero = int(item.data(Qt.UserRole))
            garde = True
            if predicat is not None and filtre != "toutes":
                garde = bool(predicat(self._etat(numero)))
            # La planche AFFICHÉE ne se masque jamais : la faire disparaître sous les yeux de
            # celui qui l'édite serait le pire des retours.
            if self.planche is not None and numero == self.planche.index:
                garde = True
            self.liste_planches.setRowHidden(ligne, not garde)

    def rafraichir(self) -> None:
        """Relit la planche courante depuis le disque et redessine tout."""
        if self.tome is None or self.planche is None:
            return
        self._charger_planche(self.planche.index, garder_brouillons=True)

    # ------------------------------------------------------------------ #
    # Le document tamponné
    # ------------------------------------------------------------------ #

    def planches_modifiees(self) -> list[int]:
        """Planches qui portent un travail non écrit — dans l'ordre de lecture."""
        vises = {i for i, doc in self.documents.items() if doc.modifie}
        vises |= {i for i, br in self._brouillons_par_planche.items() if br}
        return sorted(vises)

    def _maj_etat_document(self) -> None:
        courante = bool((self.document and self.document.modifie) or self._brouillons)
        self.bouton_annuler.setEnabled(bool(self.document and self.document.peut_annuler))
        self.bouton_refaire.setEnabled(bool(self.document and self.document.peut_refaire))
        self.bouton_enregistrer_doc.setEnabled(courante)
        # Le titre `[*]` parle du TOME, pas de la planche affichée : c'est ce qui a un sens
        # maintenant qu'on peut corriger dix planches avant d'enregistrer.
        self.etat_document.emit(bool(self.planches_modifiees()))
        self._maj_ligne_etat()

    def _maj_ligne_etat(self) -> None:
        """La ligne sous la barre d'outils. Elle répond à la question que le bouton grisé
        laissait sans réponse : « pourquoi ne puis-je pas enregistrer ? »."""
        if self.planche is None or self.tome is None:
            self.ligne_etat.setText("")
            return
        etat = self._etat(self.planche.index)
        bouts = [etat_planches.libelle_etat(etat)]
        saisies = len(self._brouillons)
        if self.document is not None and self.document.modifie:
            bouts.append("modifications en attente"
                         + (f" + {saisies} saisie(s)" if saisies else ""))
        elif saisies:
            bouts.append(f"{saisies} saisie(s) en attente")
        else:
            # ⚠ Pas « à jour » : la phrase porte sur ce qui reste À ÉCRIRE, et se retrouvait
            # accolée à « rendu périmé », ce qui se lisait comme une contradiction.
            bouts.append("rien à enregistrer")
        autres = [i for i in self.planches_modifiees() if i != self.planche.index]
        if autres:
            bouts.append(f"{len(autres)} autre(s) planche(s) en attente")
        self.ligne_etat.setText(" · ".join(bouts))

    def _annuler(self) -> None:
        if self.document is not None and self.document.annuler():
            self._appliquer_document()
            self.journal.emit("info", "Annulé.")

    def _refaire(self) -> None:
        if self.document is not None and self.document.refaire():
            self._appliquer_document()
            self.journal.emit("info", "Refait.")

    def _appliquer_document(self, *, redessiner: bool = True) -> None:
        """Réaffiche la planche depuis l'état EN MÉMOIRE, sans relire le disque.

        C'est ce qui distingue un document tamponné d'un cache : après un « Annuler », le
        disque n'a pas bougé, donc le relire ramènerait exactement ce qu'on vient d'annuler."""
        if self.document is None or self.planche is None:
            return
        etat = self.document.etat
        for k, bulle in enumerate(self.planche.bulles):
            if k < len(etat.traduction):
                bulle.traduction = etat.traduction[k]
            if k < len(etat.ocr):
                bulle.ocr = etat.ocr[k]
            bulle.manuelle = etat.manuelles.get(k)
        self.planche.mises_en_page = dict(etat.mises_en_page)
        if redessiner:
            self._remplir_liste_bulles()
            self._figer_plan_apercu(self.planche.index)
            self._poser_apercu_si_pret(self.planche.index)
            self._precharger()

    def _etat_a_sauver(self, numero: int):
        """L'état complet d'une planche, saisies en cours comprises.

        ⚠ Sur un **instantané**, jamais sur le document : verser les brouillons dans le
        document créerait un pas d'historique à chaque sauvegarde automatique, et « Annuler »
        remonterait alors le temps par tranches de 30 s au lieu de défaire des gestes."""
        document = self.documents.get(numero)
        if document is None:
            return None
        etat = document.etat.instantane()
        for index, texte in (self._brouillons_par_planche.get(numero) or {}).items():
            if not (0 <= index < len(etat.regions)):
                continue
            if texte.strip():
                etat.manuelles[index] = texte
            else:
                etat.manuelles.pop(index, None)
        return etat

    def sauver_brouillons(self) -> list[int]:
        """Écrit le miroir de récupération des planches en attente. Renvoie les planches vues.

        ⚠ N'écrit **aucun** checkpoint : le miroir vit hors de `.checkpoints/` et ne périme
        donc aucun rendu. C'est tout l'intérêt par rapport à un enregistrement automatique,
        qui ferait passer une planche en « à relettrer » à chaque caractère tapé.

        ⚠ N'écrit **que ce qui a changé**. La première version réécrivait l'état complet de
        chaque planche en attente à chaque tic de 30 s, `masks.png` compris — sur le fil
        d'affichage. À 13-41 ms par planche (mesuré), trente planches modifiées gelaient la
        fenêtre 0,4 à 1,2 s toutes les demi-minutes, et réécrivaient les mêmes octets jusqu'à
        la fin de la session. C'était exactement le défaut que le cache d'états venait de
        corriger ailleurs : répéter à l'identique un travail déjà fait. Le cas courant — on
        réfléchit, on ne tape pas — ne coûte désormais **rien**."""
        if self.tome is None:
            return []
        vues = []
        for numero in self.planches_modifiees():
            etat = self._etat_a_sauver(numero)
            if etat is None:
                continue
            marque = recuperation.empreinte(etat)
            if self._empreintes_brouillons.get(numero) == marque:
                continue
            try:
                recuperation.ecrire(self.tome.build_dir, numero, etat)
                self._empreintes_brouillons[numero] = marque
                vues.append(numero)
            except OSError as err:
                # Un disque plein ne doit pas faire tomber l'éditeur : le travail est
                # toujours en mémoire, et c'est l'essentiel à ne pas perdre.
                self.journal.emit("warn", f"Brouillon de la planche {numero} non écrit : {err}")
        return vues

    def proposer_reprise(self) -> bool:
        """Un miroir attend : le proposer en nommant les planches et leur âge.

        Renvoie `True` si le travail a été repris. Ne rien demander et reprendre d'office
        serait pire : on ne saurait pas d'où vient ce qu'on voit."""
        if self.tome is None:
            return False
        resume = recuperation.resume(self.tome.build_dir)
        if not resume["existe"]:
            return False
        numeros = resume["planches"]
        quand = ""
        if resume["date"]:
            import datetime
            quand = datetime.datetime.fromtimestamp(resume["date"]).strftime(
                " du %d/%m à %Hh%M")
        boite = QMessageBox(self)
        boite.setWindowTitle("Travail non enregistré retrouvé")
        boite.setText(f"{len(numeros)} planche(s) portent des modifications non "
                      f"enregistrées{quand}.")
        boite.setInformativeText(
            "Planches : " + ", ".join(str(x) for x in numeros) + SAUT_LIGNE
            + "Reprendre les recharge en mémoire, sans rien écrire : tu restes libre de les "
              "enregistrer ou non.")
        reprendre = boite.addButton("Reprendre", QMessageBox.AcceptRole)
        jeter = boite.addButton("Ignorer et effacer", QMessageBox.DestructiveRole)
        boite.setDefaultButton(reprendre)
        boite.exec()
        if boite.clickedButton() is jeter:
            recuperation.effacer(self.tome.build_dir)
            return False
        if boite.clickedButton() is not reprendre:
            return False
        return bool(self._reprendre_brouillons(numeros))

    def _reprendre_brouillons(self, numeros) -> list[int]:
        """Recharge les états du miroir en documents ouverts et modifiés."""
        repris = []
        for numero in numeros:
            etat = recuperation.lire(self.tome.build_dir, numero)
            if etat is None:
                self.journal.emit("warn", f"Brouillon de la planche {numero} illisible — "
                                          f"ignoré, le disque fait foi.")
                continue
            document = doc_mod.DocumentPlanche(
                checkpoints.page_checkpoint_dir(self.tome.build_dir, numero), etat,
                revision=self.tome.revision())
            document.marquer_modifie()
            self.documents[numero] = document
            self.cache.oublier_planche(numero)
            repris.append(numero)
        if repris:
            self.journal.emit("info", f"{len(repris)} planche(s) reprise(s) : "
                                      f"{', '.join(str(x) for x in repris)}.")
            self._maj_etat_document()
        return repris

    def enregistrer_document(self) -> bool:
        """`Ctrl+S` — écrit la planche AFFICHÉE. Renvoie False si l'écriture a été refusée.

        Les brouillons de saisie sont versés dans le document juste avant : une réplique tapée
        puis enregistrée sans repasser par « Garder ma version » ne doit pas se perdre — c'est
        exactement le geste qu'un utilisateur fait naturellement.

        Le refus (un run a réécrit la planche entre-temps) est le seul cas où l'on interroge
        l'utilisateur : la modification est **conservée** tant qu'il n'a pas tranché."""
        if self.planche is None or self.tome is None:
            return False
        numero = self.planche.index
        if numero not in self.planches_modifiees():
            return True
        if self._enregistrer_planche(numero):
            self.journal.emit("info", f"Planche {numero} enregistrée.")
            self.rafraichir()
            self._maj_etat_document()
            return True
        reponse = QMessageBox.question(
            self, "Planche modifiée entre-temps",
            f"La planche {numero} a changé sur le disque depuis son ouverture." + SAUT_LIGNE
            + "Recharger la planche et perdre ces modifications ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse == QMessageBox.Yes:
            self.documents.pop(numero, None)
            self._brouillons_par_planche.pop(numero, None)
            self.oublier_apercu(numero)
            self.rafraichir()
        self._maj_etat_document()
        return False

    def a_des_modifications(self) -> bool:
        """Tout ce qui serait perdu en partant, sur N'IMPORTE QUELLE planche du tome."""
        return bool(self.planches_modifiees())

    def enregistrer_tout(self) -> tuple[list[int], list[int]]:
        """Écrit toutes les planches en attente — `(écrites, refusées)`.

        Une planche refusée (un run l'a réécrite entre-temps) est **nommée et n'arrête pas
        les autres** : abandonner neuf planches parce que la dixième a bougé serait le pire
        des retours, et c'est exactement ce que ferait une écriture tout-ou-rien."""
        ecrites, refusees = [], []
        courante = self.planche.index if self.planche else None
        for numero in self.planches_modifiees():
            if self._enregistrer_planche(numero):
                ecrites.append(numero)
            else:
                refusees.append(numero)
        if courante is not None and courante in ecrites:
            self.rafraichir()
        self._maj_etat_document()
        return ecrites, refusees

    def _enregistrer_planche(self, numero: int) -> bool:
        """Écrit UNE planche, sans boîte de dialogue. Renvoie False si la révision a bougé."""
        document = self.documents.get(numero)
        if document is None or self.tome is None:
            return True
        for index, texte in self._brouillons_par_planche.get(numero, {}).items():
            # ⚠ Un champ VIDÉ rend la bulle au modèle ; il n'épingle pas une correction
            # manuelle vide, que le pipeline ne réécrirait alors plus jamais. `_etat_a_sauver`
            # faisait déjà cette distinction pour le miroir de récupération, pas ce chemin-ci —
            # le désaccord était inoffensif tant qu'il fallait cliquer « Garder ma version »
            # pour poser une correction, et devient atteignable maintenant que taper suffit.
            document.poser_correction(index, texte if texte.strip() else None)
        self._brouillons_par_planche.pop(numero, None)
        if not document.modifie:
            return True
        try:
            document.enregistrer(revision_actuelle=self.tome.revision())
        except doc_mod.ErreurDocument as err:
            self.journal.emit("warn", f"Planche {numero} non enregistrée : {err}")
            return False
        # Le rendu vient de devenir périmé, et l'aperçu en cache ne vaut plus rien.
        self.cache.oublier_planche(numero)
        self.cache_etats.oublier(numero)
        # Le disque fait désormais foi : garder le brouillon ferait proposer une reprise
        # de travail déjà écrit, ce qui est le meilleur moyen de le réécrire par-dessus.
        recuperation.effacer(self.tome.build_dir, numero)
        # ⚠ Oublier l'empreinte AVEC le brouillon. La garder ferait considérer la planche
        # comme « déjà sauvegardée » alors que son miroir vient d'être supprimé : une
        # modification ultérieure identique à celle qu'on vient d'écrire ne serait plus
        # jamais recopiée, et le filet ne rattraperait rien.
        self._empreintes_brouillons.pop(numero, None)
        return True

    # ------------------------------------------------------------------ #
    # Verrous
    # ------------------------------------------------------------------ #

    def _widgets_mutants(self) -> tuple:
        """Les commandes qui ÉCRIVENT. Le verrou ne couvre qu'elles."""
        return (self.bouton_supprimer, self.bouton_relire, self.bouton_retraduire,
                self.bouton_reprendre, self.bouton_rendre, self.bouton_corps_auto,
                self.champ_corps, self.bouton_appliquer)

    def marquer_verrou(self, planche: int | None, libelle: str, actif: bool) -> None:
        """Grise ce qui écrit, jamais ce qui affiche.

        `planche=None` (un run) touche potentiellement tout le tome : plus rien ne doit
        s'écrire. Mais **lire ne risque rien**, et la version précédente faisait
        `setEnabled(False)` sur le panneau ENTIER — pendant « Enregistrer le projet », soit
        plusieurs minutes sur un gros tome, on ne pouvait plus ni parcourir la pellicule, ni
        zoomer, ni relire ce qu'on venait de corriger. Le verrou dépassait de loin ce qu'il
        protégeait.

        ⚠ L'affichage peut montrer un état transitoire : changer de planche pendant un run
        relit un disque que le run réécrit. C'est sans danger (on n'écrit rien) mais ce n'est
        pas anodin à lire, d'où la mention « affichage seul » dans la ligne d'état plutôt
        qu'un reverrouillage."""
        if planche is None:
            self._run_global = actif
            for widget in self._widgets_mutants():
                widget.setEnabled(not actif)
            # Taper une réplique pendant qu'un run réécrit la planche produirait deux vérités
            # sur le même checkpoint. `setReadOnly` plutôt que `setEnabled` : le texte reste
            # lisible et sélectionnable, ce qui est précisément ce qu'on veut pouvoir faire.
            self.champ_trad.setReadOnly(actif)
            self.champ_ocr.setReadOnly(actif)
            # Griser les boutons ne suffit pas : déplacer un bloc ou tirer une poignée n'est
            # pas un clic sur un widget, c'est un geste sur la scène. Il faut le refuser là.
            self.scene.regler_interaction(not actif and not self.bouton_finale.isChecked())
            self.etat_planche.setText(f"{libelle} — affichage seul" if actif else "")
            return
        if actif:
            self._planches_verrouillees.add(planche)
        else:
            self._planches_verrouillees.discard(planche)
        courante = self.planche.index if self.planche else None
        occupee = courante in self._planches_verrouillees
        for widget in self._widgets_mutants():
            widget.setEnabled(not occupee)
        self.vue.setEnabled(not occupee)
        self.etat_planche.setText(
            f"Planche {courante} — {libelle}…" if occupee else "")

    # ------------------------------------------------------------------ #
    # Chargement
    # ------------------------------------------------------------------ #

    def _sur_changement_planche(self, ligne: int) -> None:
        if ligne < 0 or self.tome is None:
            return
        item = self.liste_planches.item(ligne)
        self._charger_planche(int(item.data(Qt.UserRole)))

    def _charger_planche(self, numero: int, *, garder_brouillons: bool = False) -> None:
        """Affiche une planche. **Ne demande plus rien** : chaque planche garde son document
        et ses brouillons, donc changer de planche ne met plus rien en péril."""
        assert self.tome is not None
        self.planche = self.tome.planche(numero)
        self.revision_ouverte = self.tome.revision()
        if self.planche.detectee and numero not in self.documents:
            try:
                self.documents[numero] = doc_mod.DocumentPlanche.ouvrir(
                    self.planche.ckpt_dir, revision=self.revision_ouverte)
            except doc_mod.ErreurDocument as err:
                self.journal.emit("warn", str(err))
        if self.document is not None:
            # Le document porte l'état en mémoire — il fait autorité sur ce que le disque dit.
            self._appliquer_document(redessiner=False)

        montrer_finale = self.bouton_finale.isChecked()
        fond = (self.planche.image_finale if montrer_finale else None)
        fond = fond or self.planche.image_a_afficher
        avant = self._cadrage()
        # ⚠ L'aperçu retenu appartient à la planche qu'on quitte : ses styles décriraient
        # d'autres bulles, et le chemin rapide ré-habillerait la mauvaise forme.
        self._apercu_courant = None
        # Sur le rendu APLATI du pipeline, il n'y a plus de calque à déplacer ni de masque à
        # tirer. Une poignée qui répondrait sur une image cuite promettrait ce qu'elle ne peut
        # pas tenir.
        self.scene.regler_interaction(not montrer_finale and not self._run_global)
        self.scene.charger(fond, self.planche.bulles)
        self._reprendre_cadrage(avant)
        self._remplir_liste_bulles()
        self._resuivre_zone()
        self._maj_ligne_etat()
        if not montrer_finale:
            self._figer_plan_apercu(numero)
            self._poser_apercu_si_pret(numero)
        self._precharger()
        if not self.planche.detectee:
            self.journal.emit("warn", f"Planche {numero} : aucune détection en cache — "
                                      f"lance un run sur cette planche avant de l'éditer.")

    def _remplir_liste_bulles(self) -> None:
        self.liste_bulles.blockSignals(True)
        self.liste_bulles.clear()
        for bulle in (self.planche.bulles if self.planche else []):
            if bulle.index in self._brouillons:
                marque, texte = "● ", self._brouillons[bulle.index]
            elif bulle.manuelle is not None:
                marque, texte = "✎ ", bulle.affichee
            elif not bulle.affichee.strip():
                marque, texte = "∅ ", ""
            else:
                marque, texte = "   ", bulle.affichee
            self.liste_bulles.addItem(f"{marque}{bulle.index + 1}. {texte[:60]}")
        self.liste_bulles.blockSignals(False)
        self._afficher_bulle(-1)
        self._maj_etat_document()

    # ------------------------------------------------------------------ #
    # Sélection et saisie
    # ------------------------------------------------------------------ #

    def _sur_choix_zone(self, index: int) -> None:
        self.liste_bulles.blockSignals(True)
        self.liste_bulles.setCurrentRow(index)
        self.liste_bulles.blockSignals(False)
        self._afficher_bulle(index)

    def _sur_choix_liste(self, ligne: int) -> None:
        self.scene.choisir(ligne)
        self._afficher_bulle(ligne)

    def _bulle(self, index: int):
        if self.planche is None or not (0 <= index < len(self.planche.bulles)):
            return None
        return self.planche.bulles[index]

    def _sur_saisie(self) -> None:
        """Retient la frappe dans un brouillon, et arme le relettrage de l'aperçu.

        ## Taper suffit

        Il fallait auparavant cliquer « Garder ma version » pour voir le texte se poser sur la
        planche — un geste de plus, à chaque correction, pour obtenir ce que l'on venait déjà
        d'écrire. L'aperçu suit désormais la frappe, et `_enregistrer_planche` verse les
        brouillons dans `traduction_manuelle.json` au Ctrl+S : du point de vue de
        l'utilisateur, taper EST corriger.

        ⚠ **Le document n'est pas touché ici.** Appeler `poser_correction` à chaque frappe
        empilerait un pas d'historique par caractère (`document._avant_operation`), et
        « Annuler » défferait alors des lettres au lieu de défaire des gestes. C'est le même
        raisonnement que `_etat_a_sauver`, qui refuse pour cette raison de verser les brouillons
        dans le document à chaque sauvegarde automatique."""
        if self._index_affiche < 0:
            return
        bulle = self._bulle(self._index_affiche)
        if bulle is None:
            return
        texte = self.champ_trad.toPlainText()
        if texte == bulle.affichee:
            self._brouillons.pop(self._index_affiche, None)
        else:
            self._brouillons[self._index_affiche] = texte
        self._maj_etat_document()
        self._minuteur_apercu.start()          # relancé à chaque touche : coalescence

    def _relettrer_saisie(self) -> None:
        """Fin de la pause de frappe : on ré-habille la bulle, puis on refige le plan.

        Deux temps, et c'est délibéré. Le chemin rapide donne le résultat TOUT DE SUITE mais
        court-circuite l'harmonisation de planche ; `_recomposer_courante` redemande derrière
        la composition exacte à la voie de lecture, qui la remplacera sans qu'on l'attende."""
        if self._index_affiche < 0:
            return
        self._rafraichir_bulle_rapide(self._index_affiche)
        self._recomposer_courante()

    def _afficher_bulle(self, index: int) -> None:
        bulle = self._bulle(index)
        # ⚠ `_index_affiche = -1` gèle `_sur_saisie` ET `_sur_corps` le temps du remplissage.
        # Sans lui, poser la valeur du réglage de corps émettrait `valueChanged`, donc écrirait
        # une entrée de mise en page pour une bulle qu'on ne fait que REGARDER : un simple clic
        # dans la liste marquerait la planche comme modifiée.
        self._index_affiche = -1
        self.champ_ocr.setPlainText(bulle.ocr if bulle else "")
        self.champ_trad.setPlainText(
            self._brouillons.get(index, bulle.affichee) if bulle else "")
        self.champ_corps.setValue(self._corps_affiche(index))
        self._index_affiche = index

        if bulle is None:
            self.etiquette_origine.setText("—")
        else:
            details = []
            origine = (bulle.qa or {}).get("origine") or "pipeline"
            if bulle.manuelle is not None:
                details.append("corrigée à la main — le pipeline ne la réécrira pas")
            elif origine == "editeur":
                details.append("reprise depuis l'éditeur — sans le contexte de planche")
            else:
                details.append(f"modèle · confiance {bulle.score:.2f}")
            if (bulle.qa or {}).get("rattrapee"):
                details.append("rattrapée à l'unité")
            if (bulle.qa or {}).get("debordement"):
                details.append("débordement au lettrage")
            if (bulle.qa or {}).get("cause"):
                details.append(bulle.qa["cause"])
            if index in self._brouillons:
                details.append("⚠ modification non enregistrée")
            self.etiquette_origine.setText(" · ".join(details))

        for widget in (self.bouton_relire, self.bouton_retraduire, self.bouton_reprendre,
                       self.bouton_supprimer, self.champ_corps):
            widget.setEnabled(bulle is not None and not self._run_global)
        self.bouton_rendre.setEnabled(bulle is not None and bulle.manuelle is not None
                                      and not self._run_global)
        self.bouton_corps_auto.setEnabled(
            bulle is not None and not self._run_global
            and index in (self.planche.mises_en_page if self.planche else {}))

    def _ouvrir_bulle(self, index: int) -> None:
        """Sélectionne la bulle et met le curseur dans sa réplique."""
        self.liste_bulles.setCurrentRow(index)
        self.champ_trad.setFocus()
        curseur = self.champ_trad.textCursor()
        curseur.movePosition(curseur.MoveOperation.End)
        self.champ_trad.setTextCursor(curseur)

    def aller_a(self, decalage: int) -> None:
        """Planche précédente ou suivante, en sautant celles que le filtre masque."""
        ligne = self.liste_planches.currentRow()
        total = self.liste_planches.count()
        candidate = ligne + decalage
        while 0 <= candidate < total and self.liste_planches.isRowHidden(candidate):
            candidate += decalage
        if 0 <= candidate < total:
            self.liste_planches.setCurrentRow(candidate)

    def keyPressEvent(self, event) -> None:
        """Raccourcis de navigation.

        ⚠ Ils ne s'appliquent PAS pendant une saisie : `PagePrec` dans un champ de texte
        appartient au champ, et le détourner ferait sauter de planche au milieu d'une
        réplique."""
        touche = event.key()
        saisie = self.champ_trad.hasFocus() or self.champ_ocr.hasFocus()
        if not saisie and touche == Qt.Key_PageUp:
            self.aller_a(-1)
            return
        if not saisie and touche == Qt.Key_PageDown:
            self.aller_a(1)
            return
        if touche == Qt.Key_Escape:
            for bouton in self._groupe_modes.buttons():
                if bouton.text() == "Choisir":
                    bouton.setChecked(True)
                    break
            self._changer_mode(sp.MODE_CHOISIR)
            return
        super().keyPressEvent(event)

    def _changer_mode(self, mode: str) -> None:
        self.scene.mode = mode
        if mode in (sp.MODE_RECTANGLE, sp.MODE_ELLIPSE, sp.MODE_MODIFIER):
            self.scene.forme_ajout = (sp.MODE_ELLIPSE if mode == sp.MODE_ELLIPSE
                                      else sp.MODE_RECTANGLE)

    # ------------------------------------------------------------------ #
    # Écritures — toutes par la file
    # ------------------------------------------------------------------ #

    def _verifier_fraicheur(self) -> bool:
        """Refuse d'écrire sur un état périmé. Un run qui a retraduit la planche pendant
        qu'elle était à l'écran a fait avancer la révision de `projet.json`."""
        if self.tome is None or self.planche is None:
            return False
        actuelle = self.tome.revision()
        if actuelle != self.revision_ouverte:
            reponse = QMessageBox.question(
                self, "Planche modifiée entre-temps",
                f"La planche {self.planche.index} a changé sur le disque depuis son ouverture "
                f"(révision {self.revision_ouverte} → {actuelle}).\n\n"
                f"Recharger et abandonner la modification en cours ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reponse == QMessageBox.Yes:
                self.rafraichir()
            return False
        return True

    def _contexte(self) -> edition.ContextePlanche | None:
        """Le contexte qui autorise la repeinte de `pages_clean/`.

        `None` quand l'image source est introuvable : l'opération se fera alors en
        métadonnées seules, et l'appelant le dit — mieux vaut une zone non vidée annoncée
        qu'un échec opaque."""
        if self.tome is None or self.planche is None:
            return None
        source = self.tome.chemin_source(self.planche.index)
        if source is None:
            return None
        return edition.ContextePlanche(
            image_source=source, chemin_clean=self.planche.chemin_clean,
            cfg_nettoyage=(self.tome.config.get("manga") or {}).get("nettoyage"))

    def _soumettre(self, genre: str, libelle: str, fonction, *,
                   fusionnable: bool = False, discret: bool = False) -> None:
        if self.fil is None or self.planche is None:
            return
        planche = self.planche.index
        cle = (planche, genre) if fusionnable else None
        accepte = self.fil.soumettre(Tache(genre=genre, fonction=fonction, planche=planche,
                                           libelle=libelle, cle_fusion=cle))
        # `discret` : la composition d'aperçu tourne à chaque changement de planche.
        # La journaliser noierait les messages qui comptent sous un défilé de routine.
        if not discret:
            self.journal.emit("info", f"{libelle}…" if accepte
                              else f"{libelle} : déjà en attente, demande fusionnée")

    def _executer_edition(self, operation, description: str, *, suivre=None) -> None:
        """Une édition de zone : vérification de fraîcheur ICI (sur le fil d'affichage, où la
        boîte de dialogue est légale), exécution LÀ-BAS (dans la file).

        `suivre` est la boîte de la zone manipulée. Après l'édition la planche est rechargée et
        la sélection perdue ; on la retrouve par cette géométrie (cf. `_resuivre_zone`), parce
        que `reading_order` a pu réordonner les index entre-temps."""
        if not self._verifier_fraicheur():
            return
        if suivre is not None and self.planche is not None:
            self._zone_a_resuivre = (self.planche.index, tuple(suivre))
        self._soumettre(GENRE_EDITION, description, lambda: _resume_edition(operation()))

    def _sur_zone_dessinee(self, boite, forme: str) -> None:
        if self.planche is None:
            return
        bbox, ckpt, ctx = _bbox(boite), self.planche.ckpt_dir, self._contexte()
        self._executer_edition(
            lambda: edition.ajouter_zone(ckpt, bbox, forme=forme, ctx=ctx),
            f"Planche {self.planche.index} : zone ajoutée")

    def _sur_zone_modifiee(self, index: int, boite, forme: str) -> None:
        if self.planche is None or index < 0:
            return
        bbox, ckpt, ctx = _bbox(boite), self.planche.ckpt_dir, self._contexte()
        self._executer_edition(
            lambda: edition.modifier_zone(ckpt, index, bbox, forme=forme, ctx=ctx),
            f"Planche {self.planche.index} : bulle {index + 1} redessinée")

    def _sur_coupe(self, index: int, ligne) -> None:
        if self.planche is None or index < 0:
            return
        coupe = ((ligne.x1(), ligne.y1()), (ligne.x2(), ligne.y2()))
        ckpt, ctx = self.planche.ckpt_dir, self._contexte()
        self._executer_edition(
            lambda: edition.scinder_zone(ckpt, index, coupe, ctx=ctx),
            f"Planche {self.planche.index} : bulle {index + 1} scindée")

    def _basculer_fond(self) -> None:
        """Passe de la planche nettoyée (calques déplaçables) au rendu final aplati."""
        if self.planche is not None:
            self._charger_planche(self.planche.index, garder_brouillons=True)

    # ------------------------------------------------------------------ #
    # Aperçus — voie de LECTURE et cache
    # ------------------------------------------------------------------ #

    def _figer_plan_apercu(self, numero: int) -> None:
        """Fige, **sur le fil d'affichage**, tout ce qu'il faut pour composer une planche.

        La voie de lecture ne doit jamais parcourir un état que l'utilisateur est en train de
        modifier : une liste de répliques lue pendant qu'on tape produirait un aperçu qui ne
        correspond à rien. On lui remet donc un instantané immuable, et la clé du cache est
        calculée dessus — ce qui fait qu'une correction non enregistrée invalide l'entrée
        toute seule, sans invalidation explicite à écrire donc à oublier."""
        if self.tome is None:
            return
        courante = self.planche if (self.planche and self.planche.index == numero) else None
        planche = courante or self.tome.planche(numero)
        if not planche.detectee or not planche.chemin_clean.exists():
            self._plans_apercu.pop(numero, None)
            return
        document = self.documents.get(numero)
        if document is not None:
            etat = document.etat
            textes = [etat.manuelles.get(k, texte)
                      for k, texte in enumerate(etat.traduction)]
            layouts = dict(etat.mises_en_page)
        else:
            textes = [b.affichee for b in planche.bulles]
            layouts = dict(planche.mises_en_page)
        for k, texte in (self._brouillons_par_planche.get(numero) or {}).items():
            if 0 <= k < len(textes):
                textes[k] = texte
        mcfg = (self.tome.config.get("manga") or {})
        self._plans_apercu[numero] = (
            planche.ckpt_dir, planche.chemin_clean, tuple(textes), layouts,
            (mcfg.get("typeset") or {}).get("font_path") or None,
            mcfg.get("typeset"), mcfg.get("nettoyage"))

    def _cle_apercu(self, numero: int):
        plan = self._plans_apercu.get(numero)
        if plan is None:
            return None
        return signature(numero, plan[1], plan[2], plan[3])

    def travail_restant(self, numero: int) -> str | None:
        """Ce qu'il reste à faire pour cette planche. ⚠ Appelé depuis la VOIE DE LECTURE.

        Deux travaux de nature différente, et c'est le fil de lecture qui en tire l'ordre : sa
        **vignette** (toutes les planches en ont une, elle est sur disque et coûte quelques
        dizaines de millisecondes) et son **aperçu** (seulement la fenêtre autour de la planche
        courante, il coûte 1,4 s et pèse 1 Mo en mémoire). Une planche sans plan compte comme
        réglée : il n'y a rien à en faire, et la redemander sans fin affamerait les autres.

        La vignette d'abord dans la réponse comme dans le temps : tant qu'elle manque, c'est
        elle qui manque à l'écran."""
        if self.tome is not None and not pel.vignette_a_jour(self.tome.build_dir, numero):
            return GENRE_VIGNETTE
        if numero not in self._fenetre_apercu:
            return None
        cle = self._cle_apercu(numero)
        return None if (cle is None or cle in self.cache) else GENRE_APERCU

    def apercu_en_cache(self, numero: int) -> bool:
        """La planche est-elle entièrement réglée ? Mince délégué de `travail_restant`,
        conservé parce qu'il est nommé dans la docstring de la voie de lecture et lu comme la
        question qu'on se pose depuis le fil d'affichage."""
        return self.travail_restant(numero) is None

    def fabriquer_vignette(self, numero: int) -> bool:
        """Écrit la vignette d'une planche si elle manque ou a vieilli. ⚠ VOIE DE LECTURE.

        Séparée de `composer_planche`, et ce n'est pas un rangement : les deux partageaient un
        seul code de retour, si bien qu'une vignette fraîchement écrite était perdue dès que la
        suite ne se passait pas bien — aperçu déjà en cache (`return False`), scan source
        introuvable ou composition en échec (exception). Dans les deux derniers cas la planche
        entrait dans la mémoire d'échec du fil et son icône ne revenait plus de la session.
        Deux unités de travail distinctes, deux annonces distinctes."""
        if self.tome is None or pel.vignette_a_jour(self.tome.build_dir, numero):
            return False
        return pel.fabriquer_vignette(self.tome.build_dir, numero) is not None

    def composer_planche(self, numero: int) -> bool:
        """Compose l'aperçu d'une planche et le range au cache.

        ⚠ Appelé depuis la VOIE DE LECTURE : ne touche aucun widget, ne construit aucun
        `QPixmap`, n'écrit aucun checkpoint. Composer exige le SCAN D'ORIGINE — les styles de
        bulle (polarité, couleur de fond) ne se mesurent que là — et l'obtenir peut extraire
        une archive CBZ entière. C'est exactement le genre d'appel que la 1.1.0 faisait sur le
        fil d'affichage."""
        if self.tome is None:
            return False
        plan = self._plans_apercu.get(numero)
        if plan is None or numero not in self._fenetre_apercu:
            return False
        ckpt, chemin_clean, textes, layouts, police, cfg_typeset, cfg_nettoyage = plan
        cle = signature(numero, chemin_clean, textes, layouts)
        if cle in self.cache:
            return False
        from . import apercu as apercu_mod
        source = self.tome.chemin_source(numero)
        if source is None:
            raise RuntimeError(
                "image d'origine introuvable sous sources/ : les styles de bulle "
                "(polarité, couleur de fond) ne se lisent que sur le scan.")
        vue = apercu_mod.composer(
            ckpt, chemin_clean, source, textes=list(textes), font_path=police,
            cfg_typeset=cfg_typeset, cfg_nettoyage=cfg_nettoyage, layouts=layouts)
        self.cache.poser(cle, vue)
        return True

    def _precharger(self) -> None:
        """Demande à la voie de lecture la fenêtre de planches autour de la courante.

        C'est tout le lot de fluidité : composer coûte 1,37 s en médiane, et l'utilisateur ne
        doit jamais l'attendre pour une planche qu'il allait forcément atteindre."""
        if self.fil_lecture is None or self.planche is None or self.tome is None:
            return
        numeros = [int(self.liste_planches.item(ligne).data(Qt.UserRole))
                   for ligne in range(self.liste_planches.count())]
        if not numeros:
            return
        courante = self.planche.index
        rang = numeros.index(courante) if courante in numeros else 0
        marge = self.fenetre_prechargement
        # Deux portées, et c'est délibéré : les APERÇUS ne couvrent que la fenêtre (bornés en
        # mémoire, 1 Mo pièce), les VIGNETTES couvrent tout le tome (sur disque, une fois).
        self._fenetre_apercu = set(numeros[max(0, rang - marge): rang + marge + 1])
        for numero in self._fenetre_apercu:
            if numero not in self._plans_apercu:
                self._figer_plan_apercu(numero)
        self.fil_lecture.vouloir(numeros, courante)

    def _poser_apercu_si_pret(self, numero: int) -> bool:
        """Pose les calques déjà en cache. Sur le FIL D'AFFICHAGE — une scène Qt ne se touche
        jamais depuis un autre fil, et un `QPixmap` ne se construit pas ailleurs."""
        if self.planche is None or self.planche.index != numero:
            return False
        if self.bouton_finale.isChecked():
            return False
        cle = self._cle_apercu(numero)
        if cle is None:
            return False
        vue = self.cache.lire(cle)
        if vue is None:
            return False
        # ⚠ On garde la référence : c'est cet aperçu qui porte les `StyleCompact`, donc la
        # possibilité de ré-habiller une bulle en quelques millisecondes au lieu de 1,37 s.
        self._apercu_courant = vue
        self.scene.poser_calques(vue.calques)
        return True

    def _recomposer_courante(self) -> None:
        """Ce qui est affiché vient de changer : on refige le plan et on redemande.

        La nouvelle signature ne correspond à aucune entrée du cache, donc la voie de lecture
        recompose ; l'ancienne reste au cache et servira si l'on annule."""
        if self.planche is None:
            return
        numero = self.planche.index
        self._figer_plan_apercu(numero)
        if not self._poser_apercu_si_pret(numero):
            self._precharger()

    def apercu_pret(self, numero: int) -> None:
        """La voie de lecture vient de composer une planche (aperçu et/ou vignette)."""
        item = self._item_de(numero)
        if item is not None:
            self._parer_item(item, numero)
        self._poser_apercu_si_pret(numero)

    def oublier_apercu(self, numero: int) -> None:
        """Un run a réécrit cette planche : son aperçu ne vaut plus rien."""
        self.cache.oublier_planche(numero)
        self.cache_etats.oublier(numero)
        self._plans_apercu.pop(numero, None)
        if self.fil_lecture is not None:
            self.fil_lecture.reessayer(numero)

    def _sur_texte_deplace(self, index: int, rect) -> None:
        """Un bloc de texte vient d'être déposé ailleurs.

        Son rectangle part dans `mise_en_page.json` — que le pipeline ne réécrit jamais, comme
        `traduction_manuelle.json` — puis l'aperçu est recomposé pour rejouer l'habillage sur
        la nouvelle zone. Le déplacement lui-même était instantané ; seul le ré-habillage
        coûte, et il n'arrive qu'au dépôt."""
        if self.planche is None or self.tome is None:
            return
        if not self._verifier_fraicheur():
            self.rafraichir()
            return
        if self.document is None:
            return
        # ⚠ La taille vient de l'ITEM, qui la porte depuis sa construction. L'ancien code la
        # cherchait dans un `_calques_prets` qui n'a jamais été assigné nulle part : la branche
        # était morte, `taille` ne partait donc pas dans `mise_en_page.json`, `fit_impose`
        # prenait `taille_max` par défaut, échouait, et le corps se retrouvait RECALCULÉ après
        # un simple déplacement — l'exact contraire de ce que la docstring promettait.
        item = self.scene.calque(index)
        entree = apercu_mod.entree_mise_en_page(item, rect=_bbox(rect))
        self.document.poser_mise_en_page(index, entree)
        self.planche.mises_en_page = dict(self.document.etat.mises_en_page)
        self._maj_etat_document()
        self.journal.emit("info", f"Planche {self.planche.index} bulle {index + 1} : "
                                  f"position retenue — Ctrl+S pour l'écrire")
        # ⚠ Un dernier passage FORCÉ : sans lui, l'étranglement aurait pu avaler le tout
        # dernier mouvement et laisser à l'écran un texte décalé de la position déposée.
        self._rafraichir_bulle_rapide(index, rect=_bbox(rect), force=True)
        self._recomposer_courante()

    def _rendre_au_moteur(self) -> None:
        """Retire la mise en page imposée : la bulle retrouve le lettrage calculé.

        ⚠ Cette méthode existait déjà, complète et documentée — mais n'était **branchée à
        aucun bouton**. Le seul candidat plausible (`bouton_rendre`) pointe `_retirer_correction`,
        qui est un tout autre geste : l'un rend le TEXTE au modèle, l'autre rend sa POSITION au
        moteur. Il n'y avait donc aucun moyen d'annuler un déplacement hors Ctrl+Z."""
        index = self.liste_bulles.currentRow()
        if self.planche is None or index < 0 or not self._verifier_fraicheur():
            return
        if self.document is None:
            return
        self._minuteur_corps.stop()             # le dépôt en attente n'a plus d'objet
        self._corps_en_attente = None
        self.document.poser_mise_en_page(index, None)
        self.planche.mises_en_page = dict(self.document.etat.mises_en_page)
        self._maj_etat_document()
        self._afficher_bulle(index)             # le réglage de corps repasse à « auto »
        self.journal.emit("info", f"Planche {self.planche.index} bulle {index + 1} : "
                                  f"mise en page rendue au moteur — Ctrl+S pour l'écrire")
        self._rafraichir_bulle_rapide(index, force=True)
        self._recomposer_courante()

    # ------------------------------------------------------------------ #
    # Le direct — ré-habiller UNE bulle pendant le geste
    # ------------------------------------------------------------------ #
    #
    # ## Deux temps, jamais un seul
    #
    # Pendant le geste, `apercu.recomposer_bulle` ré-habille la seule bulle concernée à partir
    # des styles déjà mesurés : quelques millisecondes, sur le fil d'affichage. Au repos,
    # `_recomposer_courante` redemande la composition EXACTE à la voie de lecture, qui la
    # remplacera quand elle sera prête. Le premier temps donne la réponse tout de suite ; le
    # second garantit qu'on finit sur ce que le pipeline écrira.
    #
    # ⚠ Pourquoi le chemin rapide ne passe PAS par la voie de lecture, malgré ses 10 à 40 ms :
    # c'est une file ordonnée, et une composition complète (1,37 s) déjà en vol bloquerait un
    # relettrage de 20 ms derrière elle. On aggraverait la latence au lieu de la réduire.

    def _corps_affiche(self, index: int) -> int:
        """La valeur à montrer dans le réglage de corps. `0` (« auto ») si rien n'est imposé."""
        mises = self.planche.mises_en_page if self.planche else {}
        impose = (mises.get(index) or {}).get("taille")
        return int(impose or 0)

    def _rafraichir_bulle_rapide(self, index: int, *, rect=None, masque=None,
                                 taille: int | None = None, force: bool = False) -> bool:
        """Ré-habille la bulle `index` et remplace son calque **sans détruire l'item**.

        `False` si le chemin rapide n'était pas disponible (aperçu pas encore composé, texte
        vide, corps intenable) : l'appelant laisse alors le geste continuer sans texte plutôt
        que d'échouer bruyamment. Un geste qui s'interrompt pour annoncer une erreur est pire
        qu'un geste dont le texte arrive un peu plus tard.

        ## L'étranglement, et pourquoi il est adaptatif

        `force=True` (un relâchement, une fin de frappe) passe toujours. Sinon on espace les
        appels d'au moins deux fois le coût du précédent, avec un plancher de 40 ms. Un
        intervalle fixe à 25 Hz saturerait le fil d'affichage sur une planche lourde, et c'est
        alors le RECTANGLE lui-même qui se met à saccader — on aurait échangé un texte en
        retard contre un geste qui accroche. En mesurant, une planche lourde s'auto-régule.

        ⚠ Le relâchement doit **toujours** repasser ici avec `force`. Le mode de panne
        classique d'un étranglement est de perdre le dernier événement, donc de laisser à
        l'écran un texte qui ne correspond pas à la position réellement déposée."""
        vue = self._apercu_courant
        if vue is None or self.planche is None or self.bouton_finale.isChecked():
            return False
        if not force:
            attente = max(40.0, 2.0 * self._cout_rapide_ms)
            if self._dernier_rapide.elapsed() < attente:
                return False
        bulle = self._bulle(index)
        if bulle is None:
            return False
        texte = self._brouillons.get(index, bulle.affichee)
        if taille is None:
            taille = self._corps_affiche(index) or None

        self._chrono_rapide.start()
        try:
            calque = apercu_mod.recomposer_bulle(vue, index, texte, rect=rect, taille=taille,
                                                 masque=masque)
        except Exception as err:                # noqa: BLE001
            # Un ré-habillage est du CONFORT : il ne doit jamais faire tomber un geste en
            # cours. Le journal garde la trace, la composition complète tranchera.
            self.journal.emit("warn", f"Aperçu rapide indisponible : {err}")
            return False
        finally:
            self._cout_rapide_ms = float(self._chrono_rapide.elapsed())
            self._dernier_rapide.restart()
        if calque is None:
            return False
        return self.scene.remplacer_calque(calque)

    def _sur_texte_glisse(self, index: int, rect) -> None:
        """Le bloc de texte suit la souris : on le ré-habille dans son rectangle visé."""
        self._rafraichir_bulle_rapide(index, rect=_bbox(rect))

    def _sur_zone_en_cours(self, index: int, boite) -> None:
        """Une poignée (ou le cadre) bouge : le texte se ré-habille dans le masque étiré.

        ⚠ Le masque est calculé ici, avant toute écriture. C'est ce qui permet de voir le
        résultat exact pendant qu'on tire, et non un rectangle vide qu'on remplirait après
        coup."""
        masque = self._masque_etire(index, boite)
        if masque is not None:
            self._rafraichir_bulle_rapide(index, masque=masque)

    def _masque_etire(self, index: int, boite):
        """Le masque qu'aurait la zone `index` si elle était retaillée à `boite`. `None` si le
        calcul échoue — une boîte dégénérée pendant un geste n'est pas une erreur."""
        bulle = self._bulle(index)
        if bulle is None or self.planche is None:
            return None
        regions = checkpoints.load_regions(self.planche.ckpt_dir)
        if self.document is not None:
            regions = self.document.etat.regions
        if not regions or not (0 <= index < len(regions)):
            return None
        region = regions[index]
        hauteur, largeur = region.mask.shape[:2]
        try:
            return edition.etirer_masque(region.mask, region.bbox, _bbox(boite),
                                         (largeur, hauteur))
        except edition.ErreurEdition:
            return None

    def _sur_zone_retaillee(self, index: int, boite) -> None:
        """La zone détectée a été déposée à une nouvelle taille (ou à une nouvelle place).

        ⚠ `retailler_zone`, pas `modifier_zone` : la bulle reste la même bulle, elle garde donc
        son OCR et sa traduction. « Redessiner » reste le geste qui repart de zéro, et c'est à
        lui qu'il revient de les jeter.

        L'écriture part dans la file : elle réécrit `regions.json`, `masks.png`, et **repeint
        la planche nettoyée** — ouverture du scan d'origine comprise. C'est de l'ordre de la
        seconde, donc hors de question pendant le geste ; le direct s'est arrêté à l'aperçu."""
        if self.planche is None or index < 0:
            return
        bbox, ckpt, ctx = _bbox(boite), self.planche.ckpt_dir, self._contexte()
        self._executer_edition(
            lambda: edition.retailler_zone(ckpt, index, bbox, ctx=ctx),
            f"Planche {self.planche.index} : bulle {index + 1} retaillée", suivre=bbox)

    def _resuivre_zone(self) -> None:
        """Resélectionne, après une édition, la zone qu'on venait de manipuler.

        ⚠ **L'index n'est pas une identité stable.** `poser_regions` recalcule l'ordre de
        lecture : agrandir une bulle vers le haut peut la faire passer devant sa voisine, et
        tout se décale. On la retrouve donc par sa géométrie, au même seuil que
        `edition.SEUIL_REPORT` — c'est la même question (« est-ce la même bulle ? »), et deux
        seuils pour une seule question finiraient par se contredire.

        Sous le seuil, on ne sélectionne rien : mieux vaut aucune sélection qu'une sélection
        fausse, qui ferait porter le geste suivant sur une autre bulle."""
        vise, self._zone_a_resuivre = self._zone_a_resuivre, None
        if vise is None or self.planche is None or self.planche.index != vise[0]:
            return
        candidates = [(geometry.iou_bbox(b.bbox, vise[1]), b.index)
                      for b in self.planche.bulles]
        if not candidates:
            return
        score, index = max(candidates)
        if score >= edition.SEUIL_REPORT:
            self.liste_bulles.setCurrentRow(index)

    # ------------------------------------------------------------------ #
    # Corps de la police
    # ------------------------------------------------------------------ #

    def _sur_corps(self, valeur: int) -> None:
        """Le réglage de corps a bougé : l'aperçu suit tout de suite, le document plus tard.

        Les deux minuteurs ont des durées très différentes, et c'est le point : voir doit être
        immédiat, s'engager ne doit pas l'être (cf. `_minuteur_corps`)."""
        if self._index_affiche < 0:
            return
        self._corps_en_attente = (self._index_affiche, int(valeur))
        self._rafraichir_bulle_rapide(self._index_affiche, taille=int(valeur) or None,
                                      force=True)
        self._minuteur_corps.start()

    def _deposer_corps(self) -> None:
        """Écrit le corps choisi dans le document (en mémoire, annulable).

        ⚠ L'entrée n'a **pas** de `rect`. Fabriquer un rectangle depuis la bbox pour la seule
        raison qu'on change la taille remplacerait l'intérieur du ballon par ses quatre coins
        (`typeset.style_impose`), et le texte s'écrirait par-dessus le contour dessiné. Un
        corps seul laisse le masque mesuré intact."""
        attente, self._corps_en_attente = self._corps_en_attente, None
        if attente is None or self.planche is None or self.document is None:
            return
        index, valeur = attente
        if not self._verifier_fraicheur():
            self.rafraichir()
            return
        ancienne = dict(self.planche.mises_en_page.get(index) or {})
        if valeur:
            ancienne["taille"] = int(valeur)
            ancienne.setdefault("ancre", "libre")
        else:
            ancienne.pop("taille", None)        # « auto » : on rend la taille au moteur
        entree = ancienne if (ancienne.get("rect") or ancienne.get("taille")) else None

        self.document.poser_mise_en_page(index, entree)
        self.planche.mises_en_page = dict(self.document.etat.mises_en_page)
        self._maj_etat_document()
        self.bouton_corps_auto.setEnabled(index in self.planche.mises_en_page)
        corps = f"corps {valeur} px" if valeur else "corps rendu au moteur"
        self.journal.emit("info", f"Planche {self.planche.index} bulle {index + 1} : "
                                  f"{corps} — Ctrl+S pour l'écrire")
        self._recomposer_courante()


    def _supprimer_zone(self) -> None:
        index = self.liste_bulles.currentRow()
        if self.planche is None or index < 0:
            return
        ckpt, ctx = self.planche.ckpt_dir, self._contexte()
        self._executer_edition(
            lambda: edition.supprimer_zone(ckpt, index, ctx=ctx),
            f"Planche {self.planche.index} : bulle {index + 1} supprimée")

    # ------------------------------------------------------------------ #

    def _retirer_correction(self) -> None:
        index = self.liste_bulles.currentRow()
        if self.planche is None or index < 0 or not self._verifier_fraicheur():
            return
        if self.document is None:
            return
        self.document.poser_correction(index, None)
        self._brouillons.pop(index, None)
        self._appliquer_document()
        self.journal.emit("info", f"Planche {self.planche.index} bulle {index + 1} : "
                                  f"correction manuelle retirée — Ctrl+S pour l'écrire")

    # ------------------------------------------------------------------ #
    # Tâches modèles — OCR, LLM
    # ------------------------------------------------------------------ #

    def _prerequis_bulle(self) -> tuple | None:
        index = self.liste_bulles.currentRow()
        if self.planche is None or index < 0 or self.tome is None or self.services is None:
            return None
        return index, self.planche.ckpt_dir, (self.tome.config.get("manga") or {})

    def _relire_bulle(self) -> None:
        prets = self._prerequis_bulle()
        if prets is None:
            return
        index, ckpt, mcfg = prets
        services, tome, numero = self.services, self.tome, self.planche.index

        def _travail():
            source = tome.chemin_source(numero)          # peut extraire un CBZ : dans la file
            if source is None:
                raise edition.ErreurEdition(
                    "l'image d'origine de cette planche est introuvable sous sources/ — "
                    "l'OCR ne peut pas relire la bulle.")
            texte = edition.relire_zone(ckpt, source, index, cfg_manga=mcfg,
                                        lecteur=services.lecteur())
            return f"Bulle {index + 1} relue : « {texte[:60]} »"

        self._soumettre(GENRE_OCR, f"Relecture OCR de la bulle {index + 1}", _travail,
                        fusionnable=True)

    def _retraduire_bulle(self) -> None:
        prets = self._prerequis_bulle()
        if prets is None:
            return
        index, ckpt, _mcfg = prets
        services = self.services

        def _travail():
            texte, motif = edition.retraduire_zone(
                ckpt, index, services.traducteur(), gloss_text=services.gloss_text())
            if motif is not None:
                from manga.quality_manga import LIBELLES_RATTRAPAGE
                raise RuntimeError(
                    f"réponse refusée — {LIBELLES_RATTRAPAGE.get(motif, motif)} ; "
                    f"la réplique précédente est conservée")
            return f"Bulle {index + 1} : « {texte[:60]} »"

        self._soumettre(GENRE_TRADUCTION, f"Retraduction de la bulle {index + 1}", _travail,
                        fusionnable=True)

    def _reprendre_bulle(self) -> None:
        """Le bouton unique : vide la zone, la lit, la traduit."""
        prets = self._prerequis_bulle()
        if prets is None:
            return
        index, ckpt, mcfg = prets
        ctx = self._contexte()
        if ctx is None:
            QMessageBox.warning(self, "Image source introuvable",
                                "L'image d'origine est nécessaire pour vider la zone et la "
                                "relire. Elle n'a pas été retrouvée sous sources/.")
            return
        services = self.services

        def _travail():
            compte = edition.reprendre_zone(
                ckpt, index, ctx=ctx, lecteur=services.lecteur(),
                agent=services.traducteur(), gloss_text=services.gloss_text(),
                cfg_manga=mcfg)
            if compte["refus"] == "nettoyage_abandonne":
                return (f"Bulle {index + 1} : intérieur trop peu uniforme pour être vidé "
                        f"sans abîmer le dessin — le japonais reste visible.")
            if compte["refus"]:
                raise RuntimeError(f"traduction refusée ({compte['refus']}) ; la zone est "
                                   f"vidée et lue, la réplique reste à faire")
            return f"Bulle {index + 1} vidée, lue et traduite : « {compte['traduction']} »"

        self._soumettre(GENRE_REPRISE, f"Reprise complète de la bulle {index + 1}", _travail)

    def _appliquer(self) -> None:
        if self.planche is None:
            return
        if self.a_des_modifications():
            # Le relettrage relit le DISQUE : il ne verrait rien de ce qui n'est pas écrit.
            if not self.enregistrer_document():
                return
        self.demande_relettrage.emit(self.planche.index, self.choix_etape.currentData())


def _resume_edition(res: dict) -> str:
    """Ce qu'on affiche après une édition de zone — y compris ce que le nettoyage a refusé."""
    bouts = [f"{res['regions']} bulle(s)", f"{res['textes_conserves']} texte(s) conservé(s)"]
    if res.get("indices_a_relire"):
        bouts.append("à relire : " + ", ".join(str(i + 1) for i in res["indices_a_relire"]))
    net = res.get("nettoyage")
    if net:
        if net["videes"]:
            bouts.append(f"{net['videes']} zone(s) vidée(s)")
        if net["restaurees"]:
            bouts.append(f"{net['restaurees']} zone(s) rendue(s) au dessin")
        if net["abandons"]:
            bouts.append("⚠ nettoyage abandonné (intérieur trop peu uniforme) : le japonais "
                         "reste visible")
    return " · ".join(bouts)


def _bbox(boite) -> tuple[int, int, int, int]:
    """`QRectF` de scène → bbox entière en pixels de planche."""
    return (int(round(boite.left())), int(round(boite.top())),
            int(round(boite.right())), int(round(boite.bottom())))
