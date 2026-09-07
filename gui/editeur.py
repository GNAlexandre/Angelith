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


from PySide6.QtCore import QElapsedTimer, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap, QTransform
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
                               QLineEdit, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from manga import (checkpoints, document as doc_mod, etat_planches, recherche as rech_mod, recuperation)
from . import icones as ico
from . import scene_planche as sp
from . import pellicule as pel
from . import theme
from .editeur_apercus import MixinApercus
from .editeur_zones import MixinZones
from .cache_apercu import CacheApercu
from .modele_tome import Tome
from .travailleur import (FilDeTravail)


# Séparateur de paragraphe des boîtes de dialogue.
SAUT_LIGNE = chr(10) * 2

#: `touche → (dx, dy)`. Le sens du déplacement d'une flèche, en pixels de planche.
#: Déclaré au module et non dans la classe : `Qt.Key_Left` n'est pas hachable comme clé de
#: dictionnaire de classe sans que Qt soit importé, ce qui est déjà le cas ici.
_FLECHES = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0),
            Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}


class PanneauEditeur(MixinApercus, MixinZones, QWidget):
    """Colonne planches · canevas · inspecteur de bulle."""

    journal = Signal(str, str)                  # (niveau, message) → onglet Journal
    demande_relettrage = Signal(int, str)       # (planche, étape de reprise)
    etat_document = Signal(bool)                # reste-t-il des modifications non écrites ?
    # L18.1 — l'état vide. Le panneau ne sait pas créer un projet : il DEMANDE, la fenêtre
    # fait. C'est la même séparation que `demande_relettrage`, et elle vaut ici pour la même
    # raison — la copie d'une archive appartient au fil de travail, que seule la fenêtre tient.
    demande_creation = Signal()
    demande_sources = Signal()
    #: L19.7 — le SECOND état vide (« tome jamais traité ») appelait un geste que rien ne
    #: proposait : il fallait lire la phrase, comprendre « onglet Runs », et aller le
    #: chercher. Une place ET une forme, c'est un bouton.
    demande_runs = Signal()
    #: « Arrêter proprement », depuis le bandeau de l'éditeur VERROUILLÉ — `PLAN-35` L35.5.
    #: ⚠ Le même geste que le bouton du bandeau de run et que celui du lanceur, donc le même
    #: libellé et la même infobulle : trois formulations pour une seule garantie feraient
    #: douter de la garantie. La fenêtre le relaie vers `_arreter_run`.
    demande_arret = Signal()

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
        # Le motif détaillé du verrou (tome, étape, avancement) et le geste qu'il autorise.
        # Posés par la fenêtre, jamais devinés ici : l'éditeur ne connaît pas les phases.
        self._motif_verrou = ""
        self._arret_possible = False
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
        # ⚠ Ce que la fenêtre a DEMANDÉ, et ce que le plafond du cache lui laisse — lot 35.
        # Les deux sont gardés parce que l'écart est ce qu'il y a à dire à l'utilisateur :
        # « 21 planches voulues, 12 tenables » explique un préchargement qui paraît lent
        # bien mieux qu'une barre qui n'avance pas. Cf. `gui/vue_retouche.ligne_de_cache`.
        self._fenetre_demandee = 0
        self._fenetre_tenable = 0
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
        # Dépôt d'un déplacement ou d'un retaillage fait aux FLÈCHES (cf. `_flecher`).
        self._minuteur_flecher = QTimer(self)
        self._minuteur_flecher.setSingleShot(True)
        self._minuteur_flecher.timeout.connect(self._deposer_flechage)
        # Étranglement ADAPTATIF du relettrage pendant un glisser (cf.
        # `_rafraichir_bulle_rapide`).
        self._chrono_rapide = QElapsedTimer()
        self._cout_rapide_ms = 0.0
        self._dernier_rapide = QElapsedTimer()
        self._dernier_rapide.start()
        # La zone à resélectionner après une édition : `reading_order` peut avoir permuté les
        # index, donc on la retrouve par sa GÉOMÉTRIE (cf. `_resuivre_zone`).
        self._zone_a_resuivre: tuple[int, tuple] | None = None
        # Brouillons en attente de re-clé après une édition qui a bougé les index :
        # `(planche, [(bbox, texte), …])`. Même mécanique que `_zone_a_resuivre`.
        self._brouillons_a_resuivre: tuple[int, list] | None = None
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
        # ⚠ Aucune de ces trois listes n'a de `QLabel` associé : leur seul « libellé » est ce
        # qu'elles contiennent. Un lecteur d'écran annonce donc « liste » et rien d'autre
        # (L19.6.1).
        self.liste_planches.setAccessibleName("Pellicule des planches")
        self.liste_planches.setAccessibleDescription(
            "Vignettes du tome. Page précédente / Page suivante changent de planche.")
        self.liste_planches.currentRowChanged.connect(self._sur_changement_planche)

        self.choix_filtre = QComboBox()
        self.choix_filtre.setAccessibleName("Filtre de la pellicule")
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
        self.champ_recherche.setAccessibleName("Chercher dans le tome")
        self.champ_recherche.setToolTip(
            "Cherche dans les répliques, les corrections manuelles et l'OCR japonais.\n"
            "Insensible à la casse et aux accents ; un clic sur un résultat ouvre la bulle.")
        self.champ_recherche.returnPressed.connect(self._chercher)

        # Remplacement. Le champ reste VIDE et sans effet tant qu'on ne l'utilise pas : la
        # recherche seule est le geste courant, le remplacement l'exception.
        self.champ_remplacement = QLineEdit()
        self.champ_remplacement.setPlaceholderText("Remplacer par…")
        self.champ_remplacement.setClearButtonEnabled(True)
        self.champ_remplacement.setAccessibleName("Remplacer par")
        # ⚠ L18.8.3 — l'infobulle disait « Remplace dans la RÉPLIQUE affichée » et contredisait
        # son propre code : `_remplacer` applique sur toutes les occurrences cochées, dans TOUT
        # le tome, et sa boîte de confirmation nomme d'ailleurs les planches concernées. Une
        # infobulle qui minimise la portée d'un geste irréversible est pire qu'aucune infobulle.
        self.champ_remplacement.setToolTip(
            "Remplace dans TOUTES les répliques cochées ci-dessous, sur l'ensemble du tome —\n"
            "pas seulement sur la planche affichée. La confirmation nomme les planches.\n"
            "Jamais dans l'OCR japonais (c'est du texte source) ni dans la traduction du\n"
            "modèle (un « --from traduction » la réécrirait). Le remplacement va dans\n"
            "traduction_manuelle.json, comme une saisie au clavier : il survit à toute relance.\n"
            "⚠ Ce geste ne s'annule pas d'un Ctrl+Z, qui ne couvre que la planche affichée.")
        self.champ_remplacement.returnPressed.connect(self._remplacer)

        self.bouton_remplacer = QPushButton("Remplacer")
        self.bouton_remplacer.setEnabled(False)
        self.bouton_remplacer.clicked.connect(self._remplacer)

        ligne_remplacement = QWidget()
        hremplacement = QHBoxLayout(ligne_remplacement)
        hremplacement.setContentsMargins(0, 0, 0, 0)
        hremplacement.addWidget(self.champ_remplacement, 1)
        hremplacement.addWidget(self.bouton_remplacer)

        self.liste_resultats = QListWidget()
        self.liste_resultats.setAccessibleName("Résultats de la recherche")
        self.liste_resultats.setMaximumHeight(150)
        self.liste_resultats.hide()
        self.liste_resultats.itemActivated.connect(self._aller_au_resultat)
        self.liste_resultats.itemClicked.connect(self._aller_au_resultat)
        # ⚠ `itemChanged` couvre la COCHE comme le texte ; on ne s'en sert que pour rafraîchir
        # le compte du bouton, jamais pour écrire.
        self.liste_resultats.itemChanged.connect(lambda _i: self._maj_bouton_remplacer())

        colonne = QWidget()
        vcolonne = QVBoxLayout(colonne)
        vcolonne.setContentsMargins(0, 0, 0, 0)
        vcolonne.addWidget(self.champ_recherche)
        vcolonne.addWidget(ligne_remplacement)
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
        # ⚠ Le TROISIÈME état vide (L19.7) : la planche existe, elle est à l'écran, et elle
        # n'a aucune bulle. La différence avec les deux autres est qu'ici **il ne faut surtout
        # pas cacher le canevas** — c'est la planche qu'on est venu regarder. D'où un bandeau
        # au-dessus d'elle plutôt qu'une page à la place d'elle.
        #
        # Jusqu'ici, ce cas se lisait dans une ligne de journal replié à zéro. Le bouton dit ce
        # qu'on peut faire, et il fait exactement ce qu'un tracé à la souris ferait : rien de
        # nouveau, une place et une forme.
        self.bandeau_vide = QWidget()
        hvide = QHBoxLayout(self.bandeau_vide)
        hvide.setContentsMargins(theme.Espacement.S, theme.Espacement.XS,
                                 theme.Espacement.S, theme.Espacement.XS)
        self.texte_vide = QLabel("")
        self.texte_vide.setWordWrap(True)
        self.bouton_tracer = QPushButton("Tracer une bulle à la main")
        self.bouton_tracer.setIcon(ico.icone("rectangle"))
        self.bouton_tracer.setToolTip(
            "Passe en mode « + Rectangle ». Une zone tracée à la main est une bulle comme une "
            "autre : elle se lit, se traduit et se lettre.")
        self.bouton_tracer.clicked.connect(
            lambda: self._changer_mode(sp.MODE_RECTANGLE))
        hvide.addWidget(self.texte_vide, 1)
        hvide.addWidget(self.bouton_tracer)
        self.bandeau_vide.hide()
        vlayout.addWidget(self.bandeau_vide)
        vlayout.addWidget(self.vue, 1)
        # Ce que le bouton grisé laissait sans réponse : où en est cette planche, et
        # reste-t-il du travail en attente ailleurs dans le tome.
        self.ligne_etat = QLabel("")
        # ⚠ Un RÔLE, pas un `setStyleSheet` inline. Le gris `#9aa` était une valeur de thème
        # sombre posée sur un widget que le style natif peint en blanc : 2,3:1, sous la cible
        # de 4,5:1. Et `11px` ne suit ni le réglage système ni le facteur DPI.
        theme.poser_role(self.ligne_etat, "faible")
        self.ligne_etat.setAccessibleName("État de la planche affichée")
        vlayout.addWidget(self.ligne_etat)
        # L35.5 — le bandeau d'état du panneau, et **le seul geste utile quand il verrouille**.
        # Le verrou de run global grisait tout ce qui écrit en disant « … — affichage seul » :
        # vrai, mais muet sur le tome, l'étape et l'avancement, donc muet sur *combien de
        # temps*. Le bandeau du `PLAN-32` porte déjà ces chiffres ; ils descendent ici, et
        # « Arrêter proprement » avec eux.
        ligne_verrou = QHBoxLayout()
        ligne_verrou.setContentsMargins(0, 0, 0, 0)
        self.etat_planche = QLabel("")
        self.etat_planche.setWordWrap(True)
        theme.poser_role(self.etat_planche, "modifie")
        self.etat_planche.setAccessibleName("Bandeau d'état du panneau")
        self.bouton_arret_verrou = QPushButton("Arrêter proprement")
        self.bouton_arret_verrou.setToolTip(
            "Le run s'arrête à la prochaine frontière propre — une planche, ou un lot entier "
            "si le lot > 1 — et tout ce qui est fait est conservé.\n"
            "Même mécanisme que `--stop` : un fichier STOP dans le dossier de build.")
        self.bouton_arret_verrou.clicked.connect(self.demande_arret.emit)
        self.bouton_arret_verrou.setVisible(False)
        ligne_verrou.addWidget(self.etat_planche, 1)
        ligne_verrou.addWidget(self.bouton_arret_verrou)
        vlayout.addLayout(ligne_verrou)

        self.splitter = splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.colonne_planches)
        splitter.addWidget(centre)
        splitter.addWidget(self._inspecteur())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 860, 380])

        # ⚠ Deux pages, et pas un panneau qu'on grise. Un éditeur complet mais inerte
        # n'apprend rien à qui vient de lancer l'application sur un `sources/` vide : il
        # montre douze boutons dont aucun ne marche. L'accueil montre DEUX boutons, dont les
        # deux marchent — c'est tout ce qu'il y a à faire à ce moment-là.
        self.pages = QStackedWidget()
        self.pages.addWidget(splitter)
        self.pages.addWidget(self._accueil())

        principal = QHBoxLayout(self)
        principal.setContentsMargins(theme.Espacement.XS, theme.Espacement.XS,
                                     theme.Espacement.XS, theme.Espacement.XS)
        principal.addWidget(self.pages)
        self._poser_parcours()

    #: L'ordre de tabulation du panneau, dans l'ordre du TRAVAIL et non de la construction.
    #:
    #: ⚠ L'ordre implicite — celui de la construction, jamais vérifié — traversait recherche →
    #: remplacement → bouton → résultats → filtre → pellicule → **les quatorze boutons de la
    #: barre du canevas** → vue → liste de bulles → inspecteur. Passer du champ de réplique au
    #: bouton « Retraduire » demandait une dizaine de tabulations, sur un logiciel dont c'est
    #: le geste le plus répété (L19.6.2).
    #:
    #: Le parcours livré va de gauche à droite, colonne par colonne, et saute la barre du
    #: canevas : ses quatorze boutons ont tous soit un raccourci, soit une entrée de menu.
    PARCOURS: tuple[str, ...] = (
        "champ_recherche", "champ_remplacement", "bouton_remplacer", "liste_resultats",
        "choix_filtre", "liste_planches",
        "vue",
        "liste_bulles", "champ_trad", "champ_corps", "bouton_corps_auto",
        "bouton_rendre", "bouton_relire", "bouton_retraduire", "bouton_reprendre",
        "choix_etape", "bouton_appliquer",
        "bouton_supprimer", "bouton_annuler", "bouton_refaire", "bouton_enregistrer_doc",
        "bouton_finale",
    )

    def _poser_parcours(self) -> None:
        """Chaîne les widgets de `PARCOURS` deux à deux — c'est tout ce que `setTabOrder` sait
        faire, et c'est pour cela qu'un ordre explicite tient dans une table plutôt que dans
        vingt appels dispersés."""
        widgets = [getattr(self, nom) for nom in self.PARCOURS if hasattr(self, nom)]
        for avant, apres in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(avant, apres)

    def _accueil(self) -> QWidget:
        """L'état vide — L18.1.

        Ce que remplaçait jusqu'ici un aplat gris `QColor(40, 40, 44)` et une ligne de journal
        décrivant un geste à faire **dans un autre logiciel** : créer une arborescence à la
        main dans l'explorateur de fichiers."""
        page = QWidget()
        vertical = QVBoxLayout(page)
        vertical.addStretch(1)
        self.accueil_titre = QLabel("Aucun projet manga")
        self.accueil_titre.setAlignment(Qt.AlignCenter)
        theme.poser_role(self.accueil_titre, "titre")
        self.accueil_texte = QLabel("")
        self.accueil_texte.setAlignment(Qt.AlignCenter)
        self.accueil_texte.setWordWrap(True)
        self.accueil_texte.setMaximumWidth(640)
        vertical.addWidget(self.accueil_titre)
        vertical.addSpacing(8)
        centre_texte = QHBoxLayout()
        centre_texte.addStretch(1)
        centre_texte.addWidget(self.accueil_texte)
        centre_texte.addStretch(1)
        vertical.addLayout(centre_texte)
        vertical.addSpacing(18)
        boutons = QHBoxLayout()
        boutons.addStretch(1)
        self.bouton_creer = QPushButton("Créer un projet…")
        self.bouton_creer.setToolTip(
            "Choisis des images ou une archive : Angelith crée "
            "sources/<Projet>/<Tome>/<format>/ et y COPIE les fichiers.")
        self.bouton_creer.clicked.connect(self.demande_creation.emit)
        self.bouton_sources = QPushButton("Ouvrir le dossier de sources")
        self.bouton_sources.setToolTip(
            "Ouvre sources/ dans l'explorateur de fichiers, pour y déposer un tome à la main.")
        self.bouton_sources.clicked.connect(self.demande_sources.emit)
        self.bouton_runs = QPushButton("Aller à l'onglet « Runs »")
        self.bouton_runs.setToolTip(
            "Ouvre l'onglet qui lance le traitement. La première passe d'un tome — la "
            "détection des bulles — compte en heures.")
        self.bouton_runs.clicked.connect(self.demande_runs.emit)
        boutons.addWidget(self.bouton_creer)
        boutons.addWidget(self.bouton_sources)
        boutons.addWidget(self.bouton_runs)
        boutons.addStretch(1)
        vertical.addLayout(boutons)
        vertical.addSpacing(10)
        astuce = QLabel("… ou fais glisser un dossier de planches, un .cbz ou un .cbr "
                        "n'importe où sur cette fenêtre.")
        astuce.setAlignment(Qt.AlignCenter)
        theme.poser_role(astuce, "faible")
        vertical.addWidget(astuce)
        vertical.addStretch(2)
        return page

    #: `nom d'état vide → boutons montrés`. Deux états, deux gestes attendus — et rien
    #: d'autre à l'écran : un éditeur complet mais inerte n'apprend rien à qui vient d'ouvrir
    #: l'application sur un `sources/` vide.
    BOUTONS_ACCUEIL = {
        "aucun_projet": ("bouton_creer", "bouton_sources"),
        "jamais_traite": ("bouton_runs",),
    }

    def montrer_accueil(self, titre: str, texte: str, cas: str = "aucun_projet") -> None:
        """Bascule sur l'état vide, avec ce qu'il faut dire **et le bouton qui va avec**.

        ⚠ Les deux cas n'appellent pas les mêmes gestes, et c'est tout l'intérêt de les
        distinguer. « Aucun projet » veut un projet ; « jamais traité » veut un run, et
        proposer « Créer un projet… » à quelqu'un qui vient d'en créer un serait lui rendre le
        geste qu'il vient de faire."""
        self.accueil_titre.setText(titre)
        self.accueil_texte.setText(texte)
        montres = self.BOUTONS_ACCUEIL.get(cas, self.BOUTONS_ACCUEIL["aucun_projet"])
        for nom in ("bouton_creer", "bouton_sources", "bouton_runs"):
            getattr(self, nom).setVisible(nom in montres)
        self.pages.setCurrentIndex(1)

    def montrer_editeur(self) -> None:
        self.pages.setCurrentIndex(0)

    def _barre_outils(self) -> QHBoxLayout:
        barre = QHBoxLayout()
        self._groupe_modes = QButtonGroup(self)
        self._groupe_modes.setExclusive(True)
        outils = [
            (sp.MODE_CHOISIR, "choisir", "Choisir",
             "Sélectionner une bulle (aucune modification)"),
            (sp.MODE_RECTANGLE, "rectangle", "+ Rectangle",
             "Tracer une bulle manquée, masque rectangulaire"),
            (sp.MODE_ELLIPSE, "ellipse", "+ Ellipse", "Tracer une bulle manquée, masque "
                                           "elliptique — la "
                                           "forme d'un ballon, et pas de coins repeints"),
            (sp.MODE_MODIFIER, "redessiner", "Redessiner",
             "Repart d'une forme NEUVE (rectangle ou ellipse) pour la bulle sélectionnée, et "
             "remet son OCR et sa traduction à zéro — les pixels lus ne sont plus les mêmes.\n"
             "Pour simplement agrandir, rétrécir ou déplacer une bulle EN GARDANT son texte, "
             "tire ses poignées en mode Choisir."),
            (sp.MODE_SCINDER, "scinder", "Scinder",
             "Tracer un trait au travers de la bulle sélectionnée pour la couper en deux"),
        ]
        # ⚠ `_boutons_modes` est un DICTIONNAIRE mode → bouton, et ce n'est pas du confort.
        #
        # `keyPressEvent` retrouvait le bouton « Choisir » en comparant son LIBELLÉ AFFICHÉ :
        #
        #     if bouton.text() == "Choisir":
        #
        # Renommer ce bouton, le traduire, ou seulement lui ajouter un raccourci entre
        # parenthèses cassait la touche Échap — en silence, et sans qu'aucun test ne le voie.
        # Le mode est l'identité de l'outil ; le libellé est ce qu'on en montre.
        self._boutons_modes: dict[str, QToolButton] = {}
        # ⚠ `1`–`5` sont des raccourcis MONO-TOUCHE dans un panneau qui porte quatre champs de
        # saisie. Ils ne sont donc PAS déclarés en `setShortcut` — un raccourci de portée
        # fenêtre volerait le « 1 » qu'on tape dans une réplique. Ils passent par
        # `keyPressEvent`, qui ne les voit que si aucun champ n'a consommé la touche : la même
        # mécanique que `PagePrec`/`PageSuiv`, et pour la même raison.
        self._modes_par_rang: dict[int, str] = {}
        #: `mode → nom d'icône`. Gardé pour la bascule de thème, qui repeint les cinq.
        self._icones_modes: dict[str, str] = {m: n for m, n, _l, _a in outils}
        for rang, (mode, nom_icone, libelle, aide) in enumerate(outils, 1):
            bouton = QToolButton()
            bouton.setText(libelle)
            # ⚠ Icône **et** libellé, jamais l'icône seule (L19.4.3). Ces cinq outils font des
            # choses irréversibles hors annulation — « Redessiner » remet l'OCR et la
            # traduction de la bulle à zéro — et aucun pictogramme ne dira jamais cela.
            bouton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            bouton.setIcon(ico.icone(nom_icone))
            bouton.setToolTip(f"{aide}\n(touche {rang})")
            bouton.setAccessibleName(libelle)
            bouton.setCheckable(True)
            bouton.clicked.connect(lambda _c, m=mode: self._changer_mode(m))
            self._groupe_modes.addButton(bouton)
            self._boutons_modes[mode] = bouton
            self._modes_par_rang[rang] = mode
            barre.addWidget(bouton)
            if mode == sp.MODE_CHOISIR:
                bouton.setChecked(True)

        self.bouton_supprimer = QPushButton("Supprimer la zone")
        self.bouton_supprimer.setIcon(ico.icone("supprimer"))
        self.bouton_supprimer.setToolTip("Retire une fausse détection. Les autres bulles "
                                         "gardent leur texte, et le dessin d'origine revient "
                                         "sous la zone retirée.")
        self.bouton_supprimer.clicked.connect(self._supprimer_zone)
        barre.addSpacing(16)
        barre.addWidget(self.bouton_supprimer)
        barre.addStretch(1)

        # ⚠ Plus aucun `setShortcut` sur ces trois boutons : ils se branchent sur les actions
        # de menu (`brancher_actions`), qui portent la déclaration UNIQUE de leur séquence.
        # C'est exactement le défaut du `Ctrl+Shift+S` déclaré deux fois — sur un bouton et
        # sur une action de menu, tous deux enfants de la fenêtre — mais généralisé avant
        # qu'il ne se reproduise.
        self.bouton_annuler = QPushButton("Annuler")
        self.bouton_annuler.setIcon(ico.icone("annuler"))
        self.bouton_annuler.setToolTip("Annule le dernier geste. L'historique remonte "
                                       "jusqu'à l'ouverture de la planche.")
        self.bouton_refaire = QPushButton("Refaire")
        self.bouton_refaire.setIcon(ico.icone("refaire"))
        # ⚠ L18.5 — « Enregistrer CETTE planche », face à « Enregistrer TOUT LE TOME » dans la
        # barre haute. Les deux libellés promettaient la même écriture, la distinction ne
        # vivait que dans une infobulle, et les deux boutons sont aux deux extrémités de
        # l'écran. Le verbe est le même — c'est le bon verbe — mais chacun porte désormais sa
        # PORTÉE dans son libellé, et celui du tome porte en plus son compteur.
        self.bouton_enregistrer_doc = QPushButton("Enregistrer cette planche")
        self.bouton_enregistrer_doc.setIcon(ico.icone("enregistrer"))
        self.bouton_enregistrer_doc.setToolTip(
            "Écrit sur le disque ce qui a été modifié sur CETTE planche. Rien n'est écrit "
            "avant — c'est ce qui permet d'essayer, puis de revenir en arrière.\n"
            "Grisé = cette planche n'a aucune modification en attente.\n"
            "Pour tout écrire et réassembler : « Enregistrer tout le tome ».")
        barre.addWidget(self.bouton_annuler)
        barre.addWidget(self.bouton_refaire)
        barre.addWidget(self.bouton_enregistrer_doc)
        barre.addSpacing(12)

        self.bouton_finale = QToolButton()
        self.bouton_finale.setText("Comparer au rendu du pipeline")
        self.bouton_finale.setAccessibleName("Comparer au rendu du pipeline")
        self.bouton_finale.setCheckable(True)
        self.bouton_finale.setToolTip(
            "Bascule entre la planche NETTOYÉE — celle qui porte les calques de texte "
            "déplaçables — et la page telle que le pipeline l'a écrite. Comparer reste "
            "utile, mais on ne peut rien déplacer sur une image aplatie.\n"
            "Le retour est instantané : l'aperçu reste en cache.")
        self.bouton_finale.clicked.connect(self.basculer_fond)
        barre.addWidget(self.bouton_finale)

        # Groupe de zoom. « Ajuster » fonctionnait déjà, mais `_charger_planche` ajuste à
        # chaque planche : sans avoir zoomé d'abord, le bouton semblait inerte, et rien à
        # l'écran ne disait à quel grossissement on était.
        barre.addSpacing(12)
        self.bouton_zoom_moins = QToolButton()
        self.bouton_zoom_moins.setText("−")
        self.bouton_zoom_moins.setIcon(ico.icone("zoom_moins"))
        self.bouton_zoom_moins.setToolTip("Dézoomer")
        self.bouton_zoom_moins.setAccessibleName("Dézoomer")
        self.etiquette_zoom = QLabel("—")
        self.etiquette_zoom.setMinimumWidth(52)
        self.etiquette_zoom.setAlignment(Qt.AlignCenter)
        self.etiquette_zoom.setAccessibleName("Grossissement")
        self.bouton_zoom_plus = QToolButton()
        self.bouton_zoom_plus.setText("+")
        self.bouton_zoom_plus.setIcon(ico.icone("zoom_plus"))
        self.bouton_zoom_plus.setToolTip("Zoomer")
        self.bouton_zoom_plus.setAccessibleName("Zoomer")
        # ⚠ `F` était un raccourci MONO-TOUCHE dans un panneau qui porte quatre champs de
        # saisie. Il n'était sauvé que par le fait que `keyPressEvent` est neutralisé pendant
        # une saisie — un filet, pas une conception. `Ctrl+0` (la convention) le remplace, et
        # `F` reste un alias : le retirer casserait la main de qui l'utilise depuis six mois.
        # Le libellé ne cite plus la touche : le menu Affichage la montre, et deux endroits qui
        # annoncent un raccourci finissent par en annoncer deux différents.
        self.bouton_ajuster = QPushButton("Ajuster")
        self.bouton_ajuster.setIcon(ico.icone("ajuster"))
        self.bouton_ajuster.setToolTip("Ramène la planche entière dans la fenêtre.")
        self.bouton_garder_zoom = QToolButton()
        self.bouton_garder_zoom.setText("🔒")
        # ⚠ Un lecteur d'écran annonce « 🔒 » comme « cadenas fermé », ou comme rien du tout.
        # Les quatre libellés de cette barre qui ne sont pas des mots — `🔒`, `−`, `+`, `%` —
        # sont les seuls widgets de l'interface dont le nom accessible n'est PAS déductible de
        # ce qui est écrit dessus. C'est une heure de travail et c'est ce qui décide qu'un
        # lecteur d'écran est utilisable ou pas (L19.6.1).
        self.bouton_garder_zoom.setAccessibleName("Garder le cadrage d'une planche à l'autre")
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
        # ⚠ Hors du parcours de tabulation (L19.6.4) : les quatorze boutons de cette barre
        # séparaient le champ de réplique du bouton « Retraduire » par une dizaine de
        # tabulations. Les trois du zoom ont chacun un raccourci de menu (Ctrl+±, Ctrl+0) et
        # n'ont donc rien à faire dans un parcours au clavier.
        for widget in (self.bouton_zoom_moins, self.bouton_zoom_plus, self.bouton_ajuster):
            widget.setFocusPolicy(Qt.NoFocus)
        self.vue.zoom_change.connect(self._maj_zoom)
        return barre

    def zoomer(self, facteur: float) -> None:
        self.vue.scale(facteur, facteur)
        self._maj_zoom()

    def ajuster(self) -> None:
        self.vue.ajuster()
        self._maj_zoom()

    # ------------------------------------------------------------------ #
    # Les actions de la fenêtre — L18.4
    # ------------------------------------------------------------------ #

    def brancher_actions(self, actions: dict, brancher) -> None:
        """Relie les boutons de l'éditeur aux actions du menu.

        ⚠ C'est ici que la règle « une action = une déclaration de raccourci » se referme :
        les boutons perdent leur `setShortcut` et gagnent celui de l'action, avec son
        infobulle. Un bouton qui déclarait son propre raccourci était la moitié du défaut
        `Ctrl+Shift+S` ; l'autre moitié était l'action de menu qui déclarait le même."""
        brancher(self.bouton_annuler, "annuler")
        brancher(self.bouton_refaire, "refaire")
        brancher(self.bouton_enregistrer_doc, "enregistrer_planche")
        brancher(self.bouton_ajuster, "ajuster")
        brancher(self.bouton_zoom_plus, "zoom_plus")
        brancher(self.bouton_zoom_moins, "zoom_moins")
        # Les deux bascules sont l'inverse : c'est le bouton qui commande, l'action de menu ne
        # fait que le refléter. Les brancher dans les deux sens ferait une boucle.
        self._actions_bascule = {
            "garder_cadrage": actions.get("garder_cadrage"),
            "comparer_rendu": actions.get("comparer_rendu"),
        }
        self.bouton_garder_zoom.toggled.connect(
            lambda actif: self._refleter_bascule("garder_cadrage", actif))
        self.bouton_finale.toggled.connect(
            lambda actif: self._refleter_bascule("comparer_rendu", actif))

    def _refleter_bascule(self, identifiant: str, actif: bool) -> None:
        action = getattr(self, "_actions_bascule", {}).get(identifiant)
        if action is not None and action.isChecked() != actif:
            action.blockSignals(True)
            action.setChecked(actif)
            action.blockSignals(False)

    def annuler(self) -> None:
        self._annuler()

    def refaire(self) -> None:
        self._refaire()

    # ------------------------------------------------------------------ #
    # L18.7 — la disposition de l'éditeur survit au redémarrage
    # ------------------------------------------------------------------ #

    def reglages(self) -> dict:
        return {"colonnes": list(self.splitter.sizes()),
                "filtre": self.choix_filtre.currentText(),
                "garder_cadrage": bool(self.bouton_garder_zoom.isChecked())}

    def rafraichir_theme(self) -> None:
        """Reprend les couleurs et les icônes du thème COURANT — appelé à la bascule.

        ⚠ Ce que la feuille de style ne couvre pas, et qu'il faut donc reprendre à la main :

        - les **icônes**, rendues en pixmap avec la couleur du token au moment du rendu ;
        - la **scène**, faite de `QGraphicsItem` qu'aucune règle QSS n'atteint — fond, cadres
          de zone, poignées, pastilles de numéro ;
        - l'**aplat d'attente** de la pellicule, un `QPixmap` rempli une fois pour toutes ;
        - la **teinte des légendes** de la pellicule, posée item par item.

        Rien de tout cela n'est du style : ce sont des pixels déjà peints. Un thème qui ne les
        reprendrait pas laisserait une bande de vignettes du thème précédent au milieu d'une
        fenêtre basculée."""
        for mode, bouton in getattr(self, "_boutons_modes", {}).items():
            nom = self._icones_modes.get(mode)
            if nom:
                bouton.setIcon(ico.icone(nom))
        for bouton, nom in ((self.bouton_supprimer, "supprimer"),
                            (self.bouton_annuler, "annuler"),
                            (self.bouton_refaire, "refaire"),
                            (self.bouton_enregistrer_doc, "enregistrer"),
                            (self.bouton_zoom_moins, "zoom_moins"),
                            (self.bouton_zoom_plus, "zoom_plus"),
                            (self.bouton_ajuster, "ajuster")):
            bouton.setIcon(ico.icone(nom))
        # L'aplat d'attente est mis en cache sur l'instance : sans cet oubli, la pellicule
        # garderait le gris clair du thème précédent jusqu'au prochain lancement.
        self._attente = None
        self.vue.setBackgroundBrush(QBrush(theme.qcolor("canevas_fond")))
        self.scene.rafraichir_theme()
        if self.tome is not None:
            self.rafraichir_pellicule()

    def poser_disposition(self) -> None:
        """Repose les colonnes une fois la fenêtre affichée. Appelée par `Fenetre.showEvent`."""
        colonnes = getattr(self, "_colonnes_a_poser", None)
        if colonnes:
            self.splitter.setSizes(colonnes)
            self._colonnes_a_poser = None

    def appliquer_reglages(self, etat: dict) -> None:
        """Repose les colonnes, le filtre et le verrou de cadrage.

        ⚠ Une taille de colonne à zéro est REFUSÉE. Un état persisté corrompu — ou seulement
        une fenêtre fermée alors qu'un panneau était replié à fond — rouvrirait sur une
        pellicule invisible, et la sortie de secours serait d'aller éditer un JSON. « Réinitialiser
        la disposition » existe pour les cas plus graves, mais celui-là est trop courant pour
        lui être renvoyé."""
        colonnes = [int(c) for c in (etat.get("colonnes") or []) if isinstance(c, (int, float))]
        if len(colonnes) == self.splitter.count() and all(c >= 40 for c in colonnes):
            self.splitter.setSizes(colonnes)
            # ⚠ Et on les GARDE pour les reposer au premier affichage. `QSplitter.setSizes` sur
            # un widget qui n'a pas encore de géométrie est sans effet : Qt répartit à parts
            # égales à la première mise en page. Les réglages sont lus dans `__init__`, donc
            # bien avant `show()` — sans ce second passage, la disposition persistée serait
            # écrite fidèlement et jamais appliquée.
            self._colonnes_a_poser = colonnes
        filtre = etat.get("filtre")
        if filtre and self.choix_filtre.findText(filtre) >= 0:
            self.choix_filtre.setCurrentText(filtre)
        self.bouton_garder_zoom.setChecked(bool(etat.get("garder_cadrage")))

    def _maj_zoom(self) -> None:
        self.etiquette_zoom.setText(f"{self.vue.transform().m11() * 100:.0f} %")

    def _cadrage(self):
        """Instantané de ce qu'on regarde : grossissement et point visé."""
        rect = self.scene.sceneRect()
        if rect.isEmpty():
            return None
        return (rect.size(), QTransform(self.vue.transform()),
                self.vue.mapToScene(self.vue.viewport().rect().center()))

    def _reprendre_cadrage(self, avant, *, meme_planche: bool = False) -> None:
        """Restaure le cadrage précédent, ou ajuste.

        ⚠ On ne le restaure que si la planche fait la MÊME taille. À grossissement égal sur
        une planche plus petite, le point qu'on regardait tombe hors de l'image : on
        découvrirait du vide, ce qui est pire que d'avoir reperdu son zoom.

        ⚠ `meme_planche` court-circuite le bouton 🔒, et c'est délibéré : celui-ci répond à la
        question « garder le cadrage en CHANGEANT de planche ? », qui n'a rien à voir. Quand
        on recharge la planche qu'on est déjà en train de regarder — après une édition de zone,
        une relecture, une retraduction — reperdre son zoom n'est jamais ce qu'on veut. Sur un
        webtoon de 9 551 px de haut, `fitInView` ramenait la planche à 3 % à chaque bulle
        ajoutée, et faisait perdre l'endroit où l'on travaillait."""
        if avant is None or not (meme_planche or self.bouton_garder_zoom.isChecked()):
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
        self.liste_bulles.setAccessibleName("Bulles, dans l'ordre de lecture")
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
        self.champ_ocr.setAccessibleName("Texte source lu par l'OCR")
        self.champ_trad = QPlainTextEdit()
        self.champ_trad.setMaximumHeight(90)
        self.champ_trad.setPlaceholderText("réplique française")
        self.champ_trad.setAccessibleName("Réplique traduite")
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
        # ⚠ Le suffixe « px » est le libellé visible de ce champ, et ce n'est pas un mot.
        self.champ_corps.setAccessibleName("Corps de la police de cette bulle, en pixels")
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
        self.choix_etape.setAccessibleName("Étape à relancer sur cette planche")
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
            # Le SECOND état vide : le tome existe, il n'a simplement jamais été traité. Il
            # ne se confond pas avec le premier (« aucun projet ») et n'appelle pas les mêmes
            # boutons — ici, ce qu'il faut, c'est lancer un run.
            self.journal.emit("warn", f"{tome.projet} / {tome.tome} : aucune planche traitée "
                                      f"— lance un run d'abord.")
            self.scene.charger(None, [])
            self.montrer_accueil(
                f"{tome.projet} / {tome.tome} — jamais traité",
                "Ce tome porte des sources mais aucun checkpoint : il n'y a rien à éditer "
                "tant qu'un run n'a pas détecté ses bulles. "
                "La toute première passe (détection) compte en heures.",
                cas="jamais_traite")
            return
        self.montrer_editeur()
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

    def _brouillons_de(self, numero: int) -> int:
        """Combien de modifications non écrites porte cette planche — L18.6.

        Les saisies en attente ET le document modifié : une bulle déplacée n'est pas un
        brouillon de texte mais reste du travail que rien n'a écrit, et c'est exactement l'un
        des trois gestes qui ne produisaient aucun retour dans le panneau."""
        saisies = len(self._brouillons_par_planche.get(numero) or {})
        document = self.documents.get(numero)
        if document is not None and document.modifie:
            saisies = max(1, saisies)
        return saisies

    def _parer_item(self, item: QListWidgetItem, numero: int) -> None:
        """Pose la vignette, la légende et la couleur d'une planche."""
        if self.tome is None:
            return
        etat = self._etat(numero)
        brouillons = self._brouillons_de(numero)
        item.setText(pel.legende(etat, brouillons))
        detail = etat_planches.libelle_etat(etat)
        if brouillons:
            detail += f" · {brouillons} modification(s) NON enregistrée(s)"
        item.setToolTip(detail)
        # `pellicule` décide d'un RÔLE (elle est Qt-libre) ; le thème décide du pixel.
        role = pel.role_couleur(etat, brouillons)
        item.setForeground(theme.qcolor(role) if role else QColor())
        chemin = pel.chemin_vignette(self.tome.build_dir, numero)
        item.setIcon(QIcon(str(chemin)) if chemin.exists() else self._icone_attente())

    def _icone_attente(self) -> QIcon:
        """Aplat neutre à la taille d'une vignette, pour une planche pas encore miniaturisée.

        Une cellule vide serait à la bonne taille — la grille s'en charge — mais ne dirait pas
        s'il reste du travail ou si la planche n'a simplement rien à montrer. L'aplat donne
        cette lecture d'un coup d'œil, et l'image le remplace à sa place exacte, sans que rien
        ne bouge.

        ⚠ Sa couleur était `#e9e9ec` : **1,1:1 sur le blanc d'une liste**, donc invisible.
        Le rôle `vignette_attente` la porte maintenant à 3:1 sur le fond de la pellicule, dans
        les deux thèmes — la docstring ci-dessus décrivait une lecture « d'un coup d'œil »
        qu'aucun contraste ne rendait possible.

        Construit UNE fois et gardé : c'est un objet Qt, donc du fil d'affichage — ce que
        `_parer_item` est déjà, et ce que la voie de lecture n'est pas."""
        icone = getattr(self, "_attente", None)
        if icone is None:
            plaque = QPixmap(pel.LARGEUR, pel.HAUTEUR_ICONE)
            plaque.fill(theme.qcolor("vignette_attente"))
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
        """Cherche dans tout le tome et liste les occurrences.

        Les résultats REMPLAÇABLES (ceux de la réplique affichée) portent une case, cochée par
        défaut. Les autres — OCR japonais, traduction du modèle — restent de simples lignes de
        navigation : un remplacement n'y a pas de sens, et leur donner une case laisserait
        croire le contraire."""
        self.liste_resultats.clear()
        self._motif_courant = motif = self.champ_recherche.text().strip()
        if self.tome is None or not motif:
            self.liste_resultats.hide()
            self._maj_bouton_remplacer()
            return
        resultats = rech_mod.chercher(self.tome.build_dir, motif)
        for res in resultats:
            item = QListWidgetItem(
                f"{res['planche']} · bulle {res['bulle'] + 1} [{res['champ']}] "
                f"{res['extrait']}")
            item.setData(Qt.UserRole, (res["planche"], res["bulle"]))
            if res["champ"] == rech_mod.CHAMP_AFFICHEE:
                item.setData(Qt.UserRole + 1, True)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
            self.liste_resultats.addItem(item)
        if not resultats:
            # Une liste vide qui disparaît laisserait croire que la recherche n'a pas eu lieu.
            self.liste_resultats.addItem(QListWidgetItem(f"aucune occurrence de « {motif} »"))
        self.liste_resultats.show()
        self._maj_bouton_remplacer()
        self.journal.emit("info", f"Recherche « {motif} » : {len(resultats)} occurrence(s).")

    def _occurrences_cochees(self) -> list[dict]:
        """Les occurrences remplaçables dont la case est cochée."""
        cochees = []
        for ligne in range(self.liste_resultats.count()):
            item = self.liste_resultats.item(ligne)
            if not item.data(Qt.UserRole + 1) or item.checkState() != Qt.Checked:
                continue
            planche, bulle = item.data(Qt.UserRole)
            cochees.append({"planche": planche, "bulle": bulle,
                            "champ": rech_mod.CHAMP_AFFICHEE})
        return cochees

    def _maj_bouton_remplacer(self) -> None:
        n = len(self._occurrences_cochees())
        self.bouton_remplacer.setEnabled(bool(n) and self.tome is not None)
        self.bouton_remplacer.setText(f"Remplacer ({n})" if n else "Remplacer")

    def _remplacer(self) -> None:
        """Applique le remplacement aux occurrences cochées, après confirmation.

        ⚠ La confirmation n'est pas une politesse. Un remplacement porte sur des dizaines de
        planches d'un coup et ne se défait pas par `Ctrl+Z` : l'historique d'annulation vit
        dans le document de la planche AFFICHÉE, il ne couvre pas les trente-neuf autres."""
        occurrences = self._occurrences_cochees()
        motif = getattr(self, "_motif_courant", "")
        par = self.champ_remplacement.text()
        if self.tome is None or not occurrences or not motif:
            return

        planches = sorted({o["planche"] for o in occurrences})
        reponse = QMessageBox.question(
            self, "Remplacer dans le tome",
            f"Remplacer « {motif} » par « {par} » dans {len(occurrences)} réplique(s), "
            f"sur {pel.nommer(planches)} ?\n\n"
            f"Le texte est écrit comme une correction manuelle : il survivra aux relances, "
            f"mais ce geste ne s'annule pas d'un Ctrl+Z — celui-ci ne couvre que la planche "
            f"affichée.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse != QMessageBox.Yes:
            return

        try:
            modifiees = rech_mod.remplacer(self.tome.build_dir, motif, par, occurrences)
        except Exception as err:      # noqa: BLE001 — un échec ici ne doit pas tuer l'éditeur
            self.journal.emit("warn", f"Remplacement impossible : {err}")
            return

        for numero in modifiees:
            self.invalider_document(numero)
        self.rafraichir_pellicule(modifiees)
        if self.planche is not None and self.planche.index in modifiees:
            self._charger_planche(self.planche.index)
        self.journal.emit(
            "info",
            f"« {motif} » → « {par} » : {len(occurrences)} réplique(s) sur "
            f"{len(modifiees)} planche(s). Elles sont à relettrer "
            f"(« Enregistrer les modifications du projet »).")
        self._chercher()      # la liste décrivait l'état d'avant

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
        # L18.6 — la pastille de la vignette concernée suit. Le mécanisme existait déjà
        # (`pellicule.pastilles`) ; il ne comptait simplement pas les brouillons, et rien dans
        # la pellicule ne distinguait donc une planche corrigée-non-écrite d'une planche
        # intacte. On ne repare QUE la planche affichée : `_parer_item` relit un état mémoïsé,
        # mais repasser sur 150 items à chaque frappe reste du travail pour rien.
        if self.planche is not None:
            item = self._item_de(self.planche.index)
            if item is not None:
                self._parer_item(item, self.planche.index)
        self._maj_ligne_etat()

    #: Ce que le bandeau du troisième état vide annonce, par cas.
    TEXTES_VIDE = {
        "jamais_detectee":
            "Cette planche n'a jamais été analysée : aucune bulle n'a été détectée dessus. "
            "Un run la traiterait avec les autres — ou trace la première zone toi-même.",
        "aucune_bulle":
            "La détection a tourné sur cette planche et n'y a trouvé aucune bulle. C'est "
            "normal sur une illustration pleine page ; ça ne l'est pas sur une planche "
            "dialoguée.",
    }

    def _maj_bandeau_vide(self) -> None:
        """Le TROISIÈME état vide (L19.7) : une planche à l'écran, et rien à éditer dessus.

        ⚠ Deux cas, et ils ne disent pas la même chose. « Jamais analysée » est un travail qui
        reste à faire ; « analysée, zéro bulle » est un RÉSULTAT, qui peut être juste (une
        illustration pleine page) ou faux (une planche dialoguée que le détecteur a manquée).
        Les confondre ferait relancer un run là où il n'y a rien à trouver, ou renoncer là où
        il y avait tout à reprendre."""
        if self.planche is None or self.tome is None:
            self.bandeau_vide.hide()
            return
        if self.planche.bulles:
            self.bandeau_vide.hide()
            return
        detectee = bool(self._etat(self.planche.index).get("detectee"))
        self.texte_vide.setText(
            self.TEXTES_VIDE["aucune_bulle" if detectee else "jamais_detectee"])
        self.bandeau_vide.show()

    def _maj_ligne_etat(self) -> None:
        """La ligne sous la barre d'outils. Elle répond à la question que le bouton grisé
        laissait sans réponse : « pourquoi ne puis-je pas enregistrer ? »."""
        self._maj_bandeau_vide()
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
            self._libelle_verrou = f"{libelle} — affichage seul" if actif else ""
            if not actif:
                # ⚠ Le motif MEURT avec le verrou. Le laisser derrière ferait réapparaître
                # « étape traduction, planche 84/131 » au premier bandeau suivant — un
                # avancement figé sur un run terminé, c'est-à-dire un faux.
                self._motif_verrou = ""
                self._arret_possible = False
            self._maj_bandeau()
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
        self._libelle_verrou = f"Planche {courante} — {libelle}…" if occupee else ""
        self._maj_bandeau()

    #: Ce que le bandeau annonce quand la comparaison au rendu du pipeline est armée.
    #:
    #: ⚠ **Le cas le plus important de la liste des états** (`PLAN-19` L19.5). Cocher
    #: « Comparer au rendu du pipeline » coupe TOUTE interaction du canevas — les poignées et
    #: les calques disparaissent, `regler_interaction(False)` est appelé deux lignes plus
    #: bas — et le seul indice était l'état enfoncé d'un bouton. Le cas voisin du run, lui,
    #: affichait « — affichage seul » depuis toujours. Deux situations identiques pour
    #: l'utilisateur, un seul bandeau : c'est celui qui manquait.
    BANDEAU_COMPARAISON = "Rendu du pipeline — affichage seul, rien n'est déplaçable ici"

    def poser_motif_de_verrou(self, motif: str, *, arret_possible: bool = True) -> None:
        """Le motif détaillé du verrou de run global, et le bouton qui va avec — L35.5.

        Appelée par `Fenetre._repeindre_bandeau`, donc à chaque battement de progression :
        c'est ce qui fait que le tome, l'étape et le compte restent d'accord avec le bandeau
        de run, quelle que soit la destination affichée.

        ⚠ **Elle n'arme rien toute seule.** Si `_run_global` est faux — aucun run n'a
        verrouillé ce panneau — le motif est ignoré : un relettrage de planche unique a son
        propre retour, local, et lui superposer un bandeau de run ferait clignoter le panneau
        à chaque geste (c'est la raison pour laquelle `_repeindre_bandeau` est muet hors run
        global).

        ⚠ `arret_possible=False` retire le bouton plutôt que de le griser. Toutes les tâches
        globales n'ont pas de frontière propre — un import de glossaire, une copie de sources
        s'arrêtent quand ils ont fini — et proposer « Arrêter proprement » là où rien ne
        l'écoute serait promettre une garantie qu'on ne tient pas. Même arbitrage que
        `BandeauDeRun.demarrer`."""
        if not getattr(self, "_run_global", False):
            return
        self._motif_verrou = str(motif or "")
        self._arret_possible = bool(arret_possible)
        self._maj_bandeau()

    def _maj_bandeau(self) -> None:
        """Le bandeau d'état, composé d'une seule source.

        Le verrou l'emporte : pendant un run, savoir que rien ne s'écrit prime sur savoir
        pourquoi la planche est aplatie."""
        verrou = getattr(self, "_libelle_verrou", "")
        if verrou:
            # ⚠ Le motif DÉTAILLÉ l'emporte sur le libellé de tâche quand la fenêtre en a
            # posé un : il porte le tome, l'étape et l'avancement, là où le libellé seul ne
            # dit que ce que la tâche s'appelle.
            motif = getattr(self, "_motif_verrou", "")
            self.etat_planche.setText(motif or verrou)
            self.bouton_arret_verrou.setVisible(
                bool(motif) and getattr(self, "_arret_possible", False))
            return
        self.bouton_arret_verrou.setVisible(False)
        compare = self.bouton_finale.isChecked()
        self.etat_planche.setText(self.BANDEAU_COMPARAISON if compare else "")

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
        # Capturé AVANT la réaffectation : c'est ce qui distingue « je recharge ce que je
        # regarde » de « je change de planche » (cf. `_reprendre_cadrage`).
        meme_planche = self.planche is not None and self.planche.index == numero
        self.planche = self.tome.planche(numero)
        self.revision_ouverte = self.tome.revision()
        # AVANT tout ce qui lit les brouillons (`_remplir_liste_bulles`, `_figer_plan_apercu`)
        # et avant `_appliquer_document` : leurs index doivent déjà être les bons.
        self._resuivre_brouillons()
        # ⚠ FILET : un document dont le nombre de régions ne correspond plus au disque est
        # périmé, et l'appliquer serait pire que de ne rien faire — `_appliquer_document`
        # réaligne PAR POSITION, donc il recollerait les textes sur les mauvaises bulles.
        # `invalider_document` couvre déjà les chemins d'édition connus ; cette garde-ci
        # couvre ceux qu'on oublierait de brancher plus tard, et elle est bon marché.
        perime = self.documents.get(numero)
        if perime is not None and len(perime.etat.regions) != len(self.planche.bulles):
            self.journal.emit(
                "warn", f"Planche {numero} : le cache d'édition en mémoire ({len(perime.etat.regions)} "
                        f"bulles) ne correspond plus au disque ({len(self.planche.bulles)}) — "
                        f"il est relu.")
            self.documents.pop(numero, None)
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
        self._maj_bandeau()
        self.scene.charger(fond, self.planche.bulles)
        self._reprendre_cadrage(avant, meme_planche=meme_planche)
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
        saisie = self._en_saisie()
        if not saisie and touche == Qt.Key_PageUp:
            self.aller_a(-1)
            return
        if not saisie and touche == Qt.Key_PageDown:
            self.aller_a(1)
            return
        if touche == Qt.Key_Escape:
            self._changer_mode(sp.MODE_CHOISIR)
            return
        if not saisie and Qt.Key_1 <= touche <= Qt.Key_9:
            mode = self._modes_par_rang.get(touche - Qt.Key_1 + 1)
            if mode is not None:
                self._changer_mode(mode)
                return
        if not saisie and touche in _FLECHES and self._flecher(touche, event.modifiers()):
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # L'alternative clavier aux gestes de canevas — L19.6.6
    # ------------------------------------------------------------------ #
    #
    # ⚠ **Ce qui n'est PAS couvert, et c'est écrit plutôt que prétendu : DESSINER une zone.**
    # Tracer un rectangle au clavier demande une notion de curseur dans la scène — un point
    # courant, visible, déplaçable, avec un geste d'ancrage puis un geste d'extension — c'est
    # un autre chantier que celui-ci. Déplacer et retailler la zone SÉLECTIONNÉE couvrent
    # l'essentiel du travail de retouche, et sont livrés.
    #
    # Le dépôt est TEMPORISÉ, et ce n'est pas un raffinement : `zone_retaillee` réécrit
    # `regions.json`, `masks.png` **et repeint la planche nettoyée**, ouverture du scan
    # d'origine comprise — de l'ordre de la seconde. Une écriture par flèche rendrait le geste
    # inutilisable et empilerait vingt pas d'historique pour un déplacement de vingt pixels.
    # C'est la même mécanique que le glisser à la souris : beaucoup de `zone_en_cours`, un
    # seul dépôt au relâchement. Ici, le « relâchement » est une pause de la main.

    #: Pas fin, en pixels de planche.
    PAS_FIN = 1
    #: Pas large — `Maj`. Dix pixels : ce qui se voit d'un coup d'œil sur une planche affichée
    #: à 50 %, sans faire sortir la bulle du ballon en trois pressions.
    PAS_LARGE = 10
    #: Délai avant dépôt, en millisecondes. 500 ms : au-dessus de la répétition automatique du
    #: clavier (~30 ms), donc une seule écriture pour une flèche tenue enfoncée ; assez court
    #: pour que l'écriture parte pendant qu'on regarde encore le résultat.
    DELAI_DEPOT_MS = 500

    def _flecher(self, touche, modificateurs) -> bool:
        """Une flèche : déplace (seule ou `Maj`) ou retaille (`Ctrl`) la zone sélectionnée."""
        if self.planche is None or self.scene.index_courant < 0:
            return False
        dx, dy = _FLECHES[touche]
        pas = self.PAS_LARGE if modificateurs & Qt.ShiftModifier else self.PAS_FIN
        if modificateurs & Qt.ControlModifier:
            bouge = self.scene.retailler_zone_courante(dx * pas, dy * pas)
        else:
            bouge = self.scene.deplacer_zone_courante(dx * pas, dy * pas)
        if bouge:
            self._minuteur_flecher.start(self.DELAI_DEPOT_MS)
        return bouge

    def _deposer_flechage(self) -> None:
        """La main s'est arrêtée : on dépose, comme un relâchement de souris."""
        self.scene.deposer_zone_courante()

    def _en_saisie(self) -> bool:
        """Un champ de texte a le focus — les raccourcis mono-touche lui appartiennent.

        ⚠ La liste couvre les QUATRE champs, pas les deux d'origine. `champ_recherche` et
        `champ_remplacement` sont arrivés après `keyPressEvent`, et taper « 1 » dans une
        recherche aurait changé d'outil de dessin sous les doigts."""
        return any(champ.hasFocus() for champ in
                   (self.champ_trad, self.champ_ocr,
                    self.champ_recherche, self.champ_remplacement))

    def _changer_mode(self, mode: str) -> None:
        """Choisit l'outil, et met le bouton en accord.

        ⚠ Le bouton se retrouve par son MODE, jamais par son libellé. `keyPressEvent`
        comparait `bouton.text() == "Choisir"` : renommer ce bouton, le traduire ou lui
        ajouter « (1) » cassait la touche Échap, en silence."""
        bouton = getattr(self, "_boutons_modes", {}).get(mode)
        if bouton is not None and not bouton.isChecked():
            bouton.setChecked(True)
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

    def basculer_fond(self) -> None:
        """Passe de la planche nettoyée (calques déplaçables) au rendu final aplati."""
        if self.planche is not None:
            self._charger_planche(self.planche.index, garder_brouillons=True)

    #: Nom historique, gardé : plusieurs tests l'appellent, et le renommer ne changerait rien
    #: pour l'utilisateur — ce qui est exactement le critère pour ne pas casser un appelant.
    _basculer_fond = basculer_fond

    # ------------------------------------------------------------------ #
    # Aperçus — voie de LECTURE et cache
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Corps de la police
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Tâches modèles — OCR, LLM
    # ------------------------------------------------------------------ #

    def _appliquer(self) -> None:
        if self.planche is None:
            return
        if self.a_des_modifications():
            # Le relettrage relit le DISQUE : il ne verrait rien de ce qui n'est pas écrit.
            if not self.enregistrer_document():
                return
        self.demande_relettrage.emit(self.planche.index, self.choix_etape.currentData())


