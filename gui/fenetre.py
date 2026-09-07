# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Fenêtre principale : la coquille — navigation, destinations paresseuses, journal, runs.

## Ce qu'elle possède, et pourquoi elle seule

Après le lot 31, la fenêtre garde **exactement quatre choses**, et rien d'autre :

| Ce qu'elle garde | Pourquoi elle seule |
|---|---|
| `FilDeTravail` + `SignauxTravail` | un seul fil ⇒ jamais deux écritures sur le même checkpoint |
| `FilDeLecture` | les compositions d'aperçu ne doivent pas attendre derrière un run |
| le `Services` du tome ouvert en retouche | un par tome — deux tomes peuvent viser deux endpoints |
| le journal, la barre d'état, la progression | un run se regarde d'où qu'on soit |

- **le fil de travail** (`FilDeTravail`) — un seul, créé une fois. Les panneaux lui soumettent
  des tâches, ils ne créent jamais de fil. C'est ce qui ferme les trois trous de concurrence
  de la 1.1.0 : plus de `QThread` écrasé, plus d'objet de signaux réassigné sous un fil vivant ;
- **les signaux** (`SignauxTravail`) — créés une fois eux aussi, pour la même raison ;
- **les modèles chauds** (`manga.services.Services`) — un par tome. Sans eux, chaque clic sur
  « Retraduire » reconstruisait les agents et rechargeait le glossaire YAML. ⚠ Le `Services`
  reste créé **par la fenêtre, à la demande de la destination**, jamais par la destination :
  c'est ce qui garde vraie la ligne « un `Services` par tome » et son `liberer()`.

## Le démarrage ne charge rien — lot 31

Jusqu'à la 2.24.1, `__init__` appelait `_remplir_projets()` alors que les deux `QComboBox`
étaient déjà branchés : remplir la liste **déclenchait** l'ouverture du premier projet par
ordre alphabétique. Un `Tome` lu, un `Services` construit, l'éditeur peuplé, la composition
d'aperçus lancée — pour un tome que personne n'avait demandé. Mesuré sur le corpus réel le
2026-09-04 : **1,89 s** avant le premier pixel, dont **1,40 s** pour ce seul tome, 692
ouvertures de fichiers, 11 aperçus et 62,4 Mo de cache dans les dix secondes suivantes
(`docs/mesures/coquille-2026-09-04.md`).

Désormais :

- **aucune destination n'est construite au démarrage** sauf l'accueil. Une destination est une
  FABRIQUE (`page_<identifiant>`), appelée au premier affichage et gardée ensuite ;
- **aucun tome n'est ouvert** : `self.tome` et `self.services` valent `None` après `show()`.
  `dernier_projet` / `dernier_tome` alimentent la carte « Reprendre » de l'accueil, un clic ;
- **aucune sonde ne part sur le fil d'affichage** : les trois marqueurs de l'accueil sont
  mesurés dans le fil de travail, après `show()` (`gui/sondes.py`).

## Le verrou est par planche

`_marquer_occupe` désactivait tout le panneau éditeur d'un bloc. Désormais la fenêtre relaie
les signaux `debut`/`fin` du fil vers `PanneauEditeur.marquer_verrou`, qui ne grise que la
planche concernée. Une tâche de genre `run` porte `planche=None` et verrouille la totalité —
un `process_volume` touche à toutes les planches, éditer sous lui produirait deux vérités sur
le même checkpoint.

## Le journal n'est pas décoratif

`perf.log` est écrit comme en ligne de commande — mais encore fallait-il l'ouvrir, ce que la
1.1.0 ne faisait nulle part : `Reporter._to_log` teste `getattr(self, "_vlog", None)` et
sautait donc **toutes** les écritures en silence. `cli.make_reporter` est maintenant appelé
comme dans `run_manga.py`, et le lanceur porte une case « verbose » sans laquelle le canal
verbose de l'orchestrateur reste vide par construction.

## Le bandeau de run appartient à la FENÊTRE — lot 32

Un run se regarde depuis n'importe quelle destination, y compris pendant qu'on retouche une
planche : le bandeau est donc en pied de fenêtre et non dans un panneau (`gui/bandeau.py`).

La fenêtre ne DÉCIDE rien de ce qu'il affiche. Elle tient un `core.progression.Progression`,
le nourrit depuis les signaux du fil (`_avancer`, `_contexte` — deux reflets Qt de
`core.progression.appliquer`), et lui demande son état. `gui/avancement.py` traduit cet état
en lignes, en titre de fenêtre et en bilan de fin. C'est ce découpage qui permet aux tests de
rejouer les traces réelles de `tests/corpus/progression/` **sans monter une fenêtre**, tout en
garantissant que la barre de l'écran et la fraction assertée par le test sont la même chose.

⚠ Le bandeau ne sert que les tâches GLOBALES (`planche=None`). Un relettrage de planche a
déjà son retour, et il est local : l'éditeur grise cette planche-là et annonce ce qu'elle
subit. Un bandeau qui clignoterait à chaque bulle relue deviendrait du décor.
"""
from __future__ import annotations

import copy
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (QAction, QKeySequence, QShortcut, QTextCharFormat,
                           QTextCursor)
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPlainTextEdit,
                               QMenu, QSizePolicy, QSplitter, QStackedWidget, QVBoxLayout,
                               QWidget)

from core import cli
from core import diagnostic as dia
from core import installation as inst
from core import maj
from core import modeles as mdl
from core import progression as prg
from core.version import ETAT_BRIQUES, __version__
from manga import etat_planches
from manga.services import Services
from . import actions as act
from . import destinations as dst
from . import garde as grd
from . import vue_retouche as vue_ret
from . import icones as ico
from . import extinction as ext
from . import sondes as snd
from . import theme
from . import avancement as av
from . import depot as dep
from .bandeau import BandeauDeRun
from . import reglages as reg
from . import vue_maj as vmaj
from .pellicule import nommer as _liste
from .editeur import SAUT_LIGNE
from .modele_tome import Tome, lister_projets
from .navigation import PanneauNavigation
from .travailleur import (GENRE_ASSEMBLAGE, GENRE_BIBLIOTHEQUE, GENRE_CREATION,
                          GENRE_DIAGNOSTIC,
                          GENRE_EDITION, GENRE_ILLUSTRATION, GENRE_MAJ, GENRE_RUN, GENRE_SONDE,
                          FilDeLecture, FilDeTravail, ReporterQt, SignauxTravail, Tache,
                          build_dir_de, demander_arret, tache_run)

#: `identifiant de destination de lancement → (brique, format imposé)`.
#:
#: ⚠ **Le webtoon n'est pas une brique.** `core/version.py:ETAT_BRIQUES` n'en connaît pas, et
#: il a raison : `run_manga.py --format {manga,webtoon}` est un format du MÊME orchestrateur.
#: La destination Webtoon est donc le lanceur manga avec `format_planche="webtoon"` — un
#: paramètre, pas un chemin de traitement dupliqué. Cf. `gui/lanceur.py`.
LANCEURS: dict[str, tuple[str, str | None]] = {
    "light_novel": ("ln", None),
    "manga": ("manga", None),
    "webtoon": ("manga", "webtoon"),
}

#: `niveau du journal → rôle de couleur`. Ce sont des RÔLES, pas des valeurs : les quatre
#: `QColor` d'avant (`(220,150,40)`, `(120,170,220)`, `(150,200,150)`, `(210,210,210)`)
#: étaient des couleurs de thème SOMBRE écrites dans un `QPlainTextEdit` que le style natif
#: peint en blanc. Le `info` à `#d2d2d2` donnait 1,4:1 — c'est-à-dire illisible, et c'est le
#: niveau le plus fréquent.
ROLES_JOURNAL = {"warn": "avertissement", "verbose": "accent",
                 "stage": "succes", "info": "information"}

#: Le préfixe de chaque niveau. Sorti de `_journaliser` pour que `_repeindre_journal` puisse
#: retrouver le niveau d'une ligne DÉJÀ écrite — cf. sa docstring.
PREFIXES_JOURNAL = {"warn": "⚠ ", "verbose": "⏱ ", "stage": "· ", "info": "  "}

#: Coût d'un relettrage de planche, en secondes. **Mesuré, pas estimé** : 469 lignes
#: `[rendu] page N/T : X.XXs` relevées dans les `perf.log` de *manga A*
#: (Vol.1 à Vol.3) et *manga C* — médiane 3,93 s, moyenne 4,00 s, de 0,32 s
#: à 9,25 s.
#:
#: ⚠ La valeur précédente était 1,5 s, soit **2,7× trop bas**. Sur vingt planches la boîte
#: promettait 30 s pour en coûter 80 ; sur cinquante, 1 min pour 3 min 20. Or cette boîte
#: n'a qu'un rôle : dire à quoi on s'engage avant plusieurs minutes de travail bloquant.
#: Trois fois trop bas ne la rend pas approximative, ça la rend trompeuse.
#:
#: ⚠ On ne dérive PAS cette valeur des `perf.log` à l'exécution : le fichier peut être
#: absent, tronqué, ou venir d'une autre machine. Une constante datée vaut mieux qu'une
#: mesure fragile — mais elle doit être réelle.
SECONDES_PAR_RELETTRAGE = 4.0


class Fenetre(QMainWindow):
    def __init__(self, config: dict, chemin_config: str):
        super().__init__()
        self.config = config
        self.chemin_config = chemin_config
        self.tome: Tome | None = None
        self.services: Services | None = None
        self._cible_run: dict | None = None
        # Planches qu'un run global va réécrire, quand on les connaît. Sans cette liste,
        # `_sur_fin` jette TOUT le cache d'aperçus après un relettrage de trois planches :
        # ~21 aperçus perdus, soit ~29 s de recomposition pour rien.
        self._planches_du_run: list[int] | None = None
        # Reporters dont le `perf.log` est encore ouvert. La fenêtre en construit un PAR
        # run : sans suivi, trente relettrages laissaient trente descripteurs ouverts sur
        # le même fichier, et Windows le VERROUILLE tant qu'un handle vit.
        self._reporters_ouverts: list = []

        # Créés UNE fois, pour toute la vie de la fenêtre.
        self.signaux = SignauxTravail()
        self.fil = FilDeTravail(self.signaux, parent=self)
        # DEUX voies, et la séparation n'est pas cosmétique. `FilDeTravail` est unique parce
        # qu'un seul fil garantit qu'on n'écrit jamais deux fois le même checkpoint ; cette
        # raison ne vaut pas pour les compositions d'aperçu, qui ne font que lire. Les avoir
        # mises dans la même file coûtait à l'utilisateur : l'aperçu de la planche 13
        # attendait derrière la retraduction d'une bulle de la 12.
        self.fil_lecture = FilDeLecture(self.signaux, parent=self)
        self.signaux.ligne.connect(self._journaliser)
        self.signaux.progression.connect(self._avancer)
        self.signaux.contexte.connect(self._contexte)
        self.signaux.debut.connect(self._sur_debut)
        self.signaux.fin.connect(self._sur_fin)
        self.signaux.file.connect(self._sur_file)
        self.signaux.apercu_pret.connect(self._sur_apercu_pret)
        self.signaux.prechargement.connect(self._sur_prechargement)

        # Temps restant, estimé sur le débit du run EN COURS — un tome traverse des étages
        # dont les coûts par planche n'ont rien de comparable, aucune constante ne les couvre.
        # Créé une fois pour la vie de la fenêtre, remis à zéro à chaque run.
        self._estimateur = av.Estimateur()
        # Lot 32 — le modèle de progression, en Python nu. L'estimateur lui est INJECTÉ :
        # `core/` ne dépend pas de `gui/`, et c'est aussi ce qui rend le modèle testable
        # sans horloge. Il est nourri par `_avancer` et `_contexte`, qui ne font que
        # refléter `core.progression.appliquer` — la table de référence.
        self.progression = prg.Progression(estimateur=self._estimateur)
        #: Ce que le bandeau nomme : « Manga · Mon Manga / Vol.2 ».
        self._cible_libelle = ""
        #: Ce qu'il faudra dire à la fin du run. Compté ICI parce que `_sur_fin` ne reçoit
        #: qu'un message : le nombre d'avertissements et la durée ne sont nulle part ailleurs.
        self._avertissements_du_run: list[str] = []
        self._debut_du_run: float | None = None
        #: Le genre de la tâche GLOBALE en cours (`planche=None`), ou `""`. Le fil, lui, ne
        #: l'expose pas — et le déduire du panneau visible serait faux dès que l'utilisateur
        #: change de destination, ce que le lot 32 encourage précisément à faire.
        self._genre_du_run = ""
        #: Le catalogue de modèles de l'endpoint LLM, tel que la sonde l'a rendu. « Inconnu »
        #: tant qu'elle n'a pas répondu — c'est l'état réel pendant la seconde qui suit le
        #: lancement, et le confondre avec « aucun modèle » ferait dire faux à l'écran.
        self._catalogue_modeles = mdl.inconnu()
        #: Le run de nuit demandé par le lanceur : `{keep_awake, shutdown, shutdown_delay}`.
        #: Vidé à la fin du run, APRÈS que l'extinction a été armée ou écartée.
        self._energie_du_run: dict = {}
        #: L'extinction en cours de compte à rebours, ou `None`. Cf. `_armer_extinction`.
        self._extinction = None
        self._minuteur_extinction = None

        # État de travail persisté (`gui/reglages.py`). Lu ICI, avant `_construire`, parce que
        # la géométrie et les tailles de colonnes se posent à la construction ; le reste
        # s'applique après, quand les widgets existent.
        self.reglages = reg.lire()
        # ⚠ **Le serveur LLM réglé pour CETTE installation, appliqué AVANT toute sonde.**
        # `gui/sondes.py` et le sélecteur de modèles lisent `self.config` ; l'appliquer plus
        # tard les ferait interroger l'adresse de `config.yaml` pendant la première seconde,
        # puis l'autre — deux verdicts pour un seul endpoint.
        self._appliquer_serveur_llm()
        # Changement de tome en cours : `_ouvrir_tome` est appelé par un signal du
        # `QComboBox`, et la garde qui protège le travail non enregistré doit pouvoir REMETTRE
        # l'ancienne sélection sans se rappeler elle-même.
        self._retour_de_garde = False
        self._tome_precedent: tuple[str, str] | None = None
        # Tâches hors tome en vol (cf. `_apres_creation`).
        self._creation_en_attente: tuple[str, str] | None = None
        self._glossaire_touche = False

        # `[*]` est l'emplacement où Qt insère la marque « modifié » (cf. `setWindowModified`).
        #
        # ⚠ **Le gabarit est RETENU, pas recomposé.** Le lot 32 pose l'avancement en tête du
        # titre (« 84/131 — Manga … ») pour la barre des tâches ; le reconstruire à chaque
        # avancement à coups de concaténation ferait tôt ou tard disparaître `[*]`, et avec
        # lui la seule marque de travail non enregistré. `avancement.titre_de_fenetre`
        # PRÉFIXE ce gabarit et n'y touche jamais.
        self._titre_base = (f"Angelith {__version__} [*]— brique manga : "
                            f"{ETAT_BRIQUES['manga']}")
        self.setWindowTitle(self._titre_base)
        fen = self.reglages["fenetre"]
        self.resize(int(fen["largeur"]), int(fen["hauteur"]))
        # ⚠ **Le registre des destinations construites.** Vide ici, et il ne se remplit qu'au
        # premier affichage de chaque destination : c'est tout le lot 31. Les trois panneaux
        # pèsent 181 Ko de Python à eux trois et étaient construits d'un bloc au démarrage.
        self._panneaux: dict[str, QWidget] = {}
        self._construire()
        if fen.get("maximisee"):
            self.showMaximized()
        # ⚠ Le glisser-déposer est armé sur la FENÊTRE, pas sur un panneau : un lâcher est un
        # geste qu'on fait « quelque part sur l'application », et le viser à 40 px près serait
        # le rendre inutilisable. Cf. `gui/depot.py` pour ce qui décide de ce qu'on a lâché.
        self.setAcceptDrops(True)
        self.fil.start()
        self.fil_lecture.start()
        # ⚠ **Aucun `_remplir_projets()` ici.** C'était la chaîne involontaire de la 2.24.1 :
        # remplir la liste déclenchait `currentTextChanged`, donc l'ouverture du premier projet
        # par ordre alphabétique. La seule chose lue au démarrage est le nombre de projets, et
        # seulement pour savoir si l'accueil doit montrer son état vide.
        self._appliquer_reglages()
        # ⚠ APRÈS `_construire` : `_repeindre_journal` et `rafraichir_theme` touchent des
        # widgets qui doivent exister.
        #
        # ⚠ **Toujours appelé**, même quand `gui.py` a déjà posé le même mode. C'est
        # `theme.appliquer` qui décide de sauter le travail, en comparant la FEUILLE produite
        # à celle qui est en place — et lui seul peut le faire honnêtement. Sauter l'appel ici
        # sur l'égalité des MODES a coûté une régression : une fenêtre construite sans qu'aucun
        # `theme.appliquer` n'ait précédé restait sans une seule règle de style, journal en
        # Segoe UI compris, et rien ne le disait.
        self._appliquer_theme(self.reglages.get("theme") or theme.AUTO)

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        """La coquille, et **rien de son contenu**.

        ⚠ Aucune destination n'est instanciée ici. `_construire` pose le pane, une pile vide,
        le journal, la barre d'état et les menus ; `_appliquer_reglages` choisit ensuite la
        destination d'ouverture, et c'est ELLE seule qui est construite. Le test qui aurait
        échoué avant le lot est exactement là :
        `Fenetre(...).show()` puis `panneaux_construits() == {"accueil"}`."""
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(theme.Espacement.S, theme.Espacement.S,
                                  theme.Espacement.S, theme.Espacement.S)

        # -- le pane et la pile ------------------------------------------- #
        corps = QHBoxLayout()
        corps.setSpacing(theme.Espacement.S)
        self.navigation = PanneauNavigation()
        self.navigation.choisie.connect(self.aller_a)
        self.navigation.demande_action.connect(self._declencher_action)
        corps.addWidget(self.navigation)

        self.pile = QStackedWidget()
        self.pile.setAccessibleName("Destination affichée")
        corps.addWidget(self.pile, 1)

        boite_corps = QWidget()
        boite_corps.setLayout(corps)

        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(5000)
        # ⚠ Un RÔLE, et une pile de polices MULTIPLATEFORME. `Consolas` est une police
        # Windows ; le repli `monospace` sauvait la mise, mais c'est le genre de valeur qui
        # rend un logiciel « développé sur Windows » visible au premier coup d'œil ailleurs.
        theme.poser_role(self.journal, "journal")
        self.journal.setAccessibleName("Journal des runs")

        # Le journal occupait 220 px en permanence pour un contenu qu'on ne lit qu'après un
        # incident. Il est replié au départ et se déplie tout seul au premier avertissement.
        self.separateur = QSplitter(Qt.Vertical)
        self.separateur.addWidget(boite_corps)
        self.separateur.addWidget(self.journal)
        self.separateur.setStretchFactor(0, 1)
        self.separateur.setSizes(list(self.reglages["journal"]))
        layout.addWidget(self.separateur, 1)

        # ⚠ **Le bandeau appartient à la FENÊTRE, pas à une destination.** C'est la seule
        # façon de tenir la promesse du `PLAN-32` : « la progression doit se voir depuis
        # n'importe quelle destination ». Un widget posé dans le lanceur manga aurait
        # disparu dès qu'on regarde la retouche — c'est-à-dire précisément pendant qu'un run
        # tourne. Il est caché tant qu'aucun run n'a commencé (cf. `gui/bandeau.py`).
        self.bandeau = BandeauDeRun()
        self.bandeau.demande_arret.connect(self._arreter_run)
        self.bandeau.demande_avertissements.connect(self._montrer_avertissements)
        self.bandeau.demande_retouche.connect(self._retoucher_le_run)
        self.bandeau.demande_annulation_extinction.connect(self._annuler_extinction)
        layout.addWidget(self.bandeau)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Prêt.")
        # ⚠ La file et le préchargement passent en widgets PERMANENTS de la barre d'état, et
        # non plus dans une barre haute qui n'existe plus. Ils décrivent l'état de la FENÊTRE —
        # un fil unique, un préchargement unique — et suivre une destination les aurait rendus
        # invisibles dès qu'on regarde ailleurs, ce qui est précisément quand un run tourne.
        self.etiquette_file = QLabel("")
        self.etiquette_file.setAccessibleName("File de travail")
        self.statusBar().addPermanentWidget(self.etiquette_file)
        self.etiquette_prechargement = QLabel("")
        theme.poser_role(self.etiquette_prechargement, "faible")
        self.etiquette_prechargement.setAccessibleName("Préchargement des aperçus")
        self.statusBar().addPermanentWidget(self.etiquette_prechargement)

        self._construire_menu()

    # ------------------------------------------------------------------ #
    # Les menus — construits DEPUIS le catalogue, jamais posés à la main
    # ------------------------------------------------------------------ #

    def _construire_menu(self) -> None:
        """Parcourt `gui/actions.py` et fabrique la barre.

        ⚠ Aucune `QAction` n'est déclarée ailleurs, et aucun bouton ne porte plus son propre
        `setShortcut` : c'est la seule façon de tenir la promesse « une action = un raccourci =
        une déclaration ». Le `Ctrl+Shift+S` qui était posé DEUX fois — sur le bouton de la
        barre haute et sur l'entrée de menu, tous deux enfants de la fenêtre — venait
        exactement de l'absence de ce point unique. Les boutons se branchent maintenant sur
        l'action (`_brancher_bouton`), ce qui leur donne le libellé, l'infobulle et le
        raccourci sans les redéclarer."""
        self.actions_menu: dict[str, QAction] = {}
        self._alias_gardes: list = []
        # ⚠ Les `QMenu` sont GARDÉS côté Python. Sans référence, `QMenuBar.actions()[i].menu()`
        # rend un objet dont le pendant C++ a déjà été détruit — `libshiboken: Internal C++
        # object already deleted` — et la barre devient inspectable seulement par accident.
        self.menus: dict[str, object] = {}
        self.sous_menus: dict[tuple[str, str], object] = {}
        barre = self.menuBar()
        for nom in act.MENUS:
            entrees = act.par_menu(nom)
            if not entrees:
                continue
            menu = self.menus[nom] = barre.addMenu(nom)
            # Sans cela, l'infobulle d'une entrée de menu ne s'affiche jamais — et pour la
            # moitié d'entre elles, c'est elle qui distingue « Enregistrer cette planche » de
            # « Enregistrer tout le tome ».
            menu.setToolTipsVisible(True)
            sous_menus: dict[str, object] = {}
            for entree in entrees:
                if not isinstance(entree, act.Action):
                    menu.addSeparator()
                    continue
                action = self._fabriquer_action(entree)
                if not entree.groupe:
                    menu.addAction(action)
                    continue
                if entree.groupe not in sous_menus:
                    # ⚠ Construit avec la FENÊTRE pour parent, puis rattaché. `menu.addMenu(…)`
                    # rend un objet dont le pendant C++ est détruit dès que Qt le juge inutile,
                    # et l'inspecter plus tard lève « Internal C++ object already deleted ».
                    sous = QMenu(entree.groupe, self)
                    menu.addMenu(sous)
                    sous.setToolTipsVisible(True)
                    sous_menus[entree.groupe] = sous
                    self.sous_menus[(nom, entree.groupe)] = sous
                sous_menus[entree.groupe].addAction(action)
        self._maj_actions_tome()

    def _fabriquer_action(self, entree: act.Action) -> QAction:
        """Une `QAction` depuis une ligne du catalogue, reliée à `action_<identifiant>`.

        L'absence de méthode est une **erreur de programmation**, pas un cas à tolérer : une
        entrée de menu qui ne fait rien est le pire des deux mondes, elle promet et ne tient
        pas. `tests/test_gui_actions.py` la refuse d'ailleurs sans construire de fenêtre."""
        action = QAction(entree.libelle, self)
        if entree.raccourci:
            action.setShortcut(entree.raccourci)
        if entree.infobulle:
            action.setToolTip(entree.infobulle)
            action.setStatusTip(entree.infobulle)
        if entree.bascule:
            action.setCheckable(True)
        methode = getattr(self, entree.gestionnaire)
        if entree.donnee is not None:
            action.setData(entree.donnee)
        if entree.bascule and entree.donnee is not None:
            action.toggled.connect(
                lambda actif, m=methode, d=entree.donnee: m(d, actif))
        elif entree.bascule:
            action.toggled.connect(methode)
        elif entree.donnee is not None:
            # ⚠ Une entrée à DONNÉE qui n'est PAS une bascule — les sept destinations du menu
            # « Aller à », nées au lot 31. Ce cas n'existait pas : `donnee` n'avait servi
            # jusqu'ici qu'aux filtres et aux thèmes, qui sont tous des bascules. Sans cette
            # branche, `m()` partait sans argument et les sept raccourcis levaient un
            # `TypeError` **dans un slot Qt**, c'est-à-dire à la console et pas à l'écran :
            # le raccourci ne faisait simplement rien.
            action.triggered.connect(
                lambda _c=False, m=methode, d=entree.donnee: m(d))
        else:
            action.triggered.connect(lambda _c=False, m=methode: m())
        self.actions_menu[entree.identifiant] = action
        for alias in entree.alias:
            # ⚠ Un alias est un `QShortcut` séparé, pas une seconde séquence sur la même
            # action : `QAction.setShortcuts` les afficherait TOUS dans le menu, et le menu
            # deviendrait « Ajuster à la fenêtre  Ctrl+0, F » — plus long à lire que le geste
            # à faire. L'alias est un repli, pas une promesse.
            raccourci = QShortcut(QKeySequence(alias), self)
            raccourci.activated.connect(methode)
            self._alias_gardes.append(raccourci)
        return action

    def _maj_actions_tome(self) -> None:
        """Grise ce qui n'a pas de sens sans tome ouvert.

        Une entrée grisée dit « cette action existe, il te manque un tome » ; une entrée
        absente dit « cette action n'existe pas ». Les deux messages sont différents, et c'est
        le premier qui est vrai."""
        ouvert = self.tome is not None
        for entree in act.actions():
            if entree.exige_tome and entree.identifiant in self.actions_menu:
                self.actions_menu[entree.identifiant].setEnabled(ouvert)

    def _brancher_bouton(self, bouton, identifiant: str, *, libelle: bool = False) -> None:
        """Relie un bouton existant à l'action du catalogue.

        Le bouton garde sa place et son apparence ; il perd seulement le droit de déclarer un
        raccourci pour son compte. C'est ce qui rend le test d'unicité vrai pour toute la
        fenêtre et pas seulement pour sa barre de menus."""
        action = self.actions_menu[identifiant]
        bouton.setShortcut("")
        bouton.clicked.connect(action.trigger)
        if libelle:
            bouton.setText(action.text())
        if action.toolTip():
            rappel = f"{action.toolTip()}"
            if action.shortcut().toString():
                rappel += f"  ({action.shortcut().toString()})"
            bouton.setToolTip(rappel)

    # ================================================================== #
    # Les destinations — une fabrique par identifiant, appelée UNE fois
    # ================================================================== #
    #
    # ⚠ Le nom `page_<identifiant>` n'est pas décoratif : `_construire_page` le résout par
    # `getattr`, et `tests/test_gui_destinations.py` vérifie — sans PySide6, en lisant ce
    # fichier par `ast` — que chaque destination de corps en a une. Une entrée de nav sans
    # fabrique ferait tomber la navigation au premier clic.

    def panneaux_construits(self) -> set[str]:
        """Les destinations réellement instanciées. **C'est ce que le lot mesure.**"""
        return set(self._panneaux)

    def aller_a(self, identifiant: str) -> QWidget | None:
        """Montre une destination, en la construisant si c'est la première fois.

        ⚠ Une entrée de pied qui nomme une ACTION (Réglages) n'est pas une page : elle
        déclenche son dialogue et la destination courante ne bouge pas. La traiter comme une
        page ferait d'un clic sur « Réglages » une navigation dont on ne saurait pas revenir.

        ⚠ **MISE À JOUR lot 36** : le Diagnostic, lui, EST une page — il est en pied par
        convention Fluent, pas par nature. C'est `destination.action` qui tranche, et non
        `destination.pied` : la place dans le pane et la nature de la destination sont deux
        choses différentes (cf. `gui/destinations.py`)."""
        destination = dst.par_identifiant(identifiant)
        if destination is None:
            return None
        if destination.action:
            self._declencher_action(destination.action)
            return None
        # ⚠ **Le chemin qui ne demande jamais rien, et qui passe quand même par la garde.**
        # Le `PLAN-31` annonçait ici un trou : quitter la retouche est devenu un changement de
        # destination, que rien ne gardait. La mesure de l'étape 0.2 du `PLAN-35` dit que le
        # trou ne s'ouvre pas — les pages vivent dans un `QStackedWidget`, en quitter une la
        # CACHE — et `gui/garde.py` porte ce verdict avec son motif. L'appel reste, pour que
        # le jour où une page serait détruite au lieu d'être cachée, il n'y ait qu'une ligne
        # à changer, à un endroit qui a déjà son test.
        if identifiant != self.destination() and not self.peut_quitter("destination"):
            return self._panneaux.get(self.destination())
        panneau = self._panneaux.get(identifiant)
        if panneau is None:
            panneau = self._construire_page(destination)
        self.pile.setCurrentWidget(panneau)
        self._contraindre_a_la_page_courante(panneau)
        self.navigation.selectionner(identifiant)
        self._destination = identifiant
        return panneau

    def _contraindre_a_la_page_courante(self, courante) -> None:
        """Seule la page AFFICHÉE contraint la largeur minimale de la fenêtre.

        ⚠ Un `QStackedWidget` prend le maximum des minimums de **toutes** ses pages, visibles
        ou non. Mesuré le 2026-09-04 : `PanneauEditeur` en demande 3 375 px à lui seul, si bien
        qu'ouvrir une fois la retouche condamnait la fenêtre à 3 593 px pour le reste de la
        session — y compris de retour sur l'accueil, qui en demande 690.

        Le défaut n'est pas neuf : en 2.24.1, l'éditeur étant construit au démarrage, la fenêtre
        avait ce minimum de 3 395 px **dès le premier pixel**, et `resize(1520, 960)` était
        silencieusement ignoré. Ce lot ne le corrige pas à sa source — cela demanderait de
        toucher `gui/editeur.py`, ce que le plan écarte (§4) — mais il cesse de le propager
        aux six autres destinations."""
        for index in range(self.pile.count()):
            page = self.pile.widget(index)
            politique = (QSizePolicy.Preferred if page is courante else QSizePolicy.Ignored)
            page.setSizePolicy(politique, politique)
        self.pile.updateGeometry()
        # ⚠ `setMinimumSize(0, 0)` PUIS `activate()` : le minimum de la fenêtre est latché par
        # la disposition, et il ne redescend pas tout seul quand celui d'un enfant baisse.
        self.setMinimumSize(0, 0)
        disposition = self.layout()
        if disposition is not None:
            disposition.activate()
        # ⚠ …et il faut RÉÉLARGIR quand la nouvelle page en demande davantage. Sans cela, une
        # fenêtre réduite sur l'accueil garderait sa largeur en passant à la retouche, et
        # l'éditeur serait rogné — on aurait échangé un minimum absurde contre un panneau
        # illisible, ce qui est pire.
        # ⚠ La largeur voulue est lue sur la PILE, pas sur la fenêtre : `QMainWindow` met son
        # `minimumSizeHint` en cache et rend encore l'ancienne valeur juste après `activate()`,
        # si bien que le réélargissement ne partait pas et que la retouche s'ouvrait rognée.
        # La pile, elle, répond juste — et elle ne répond que pour la page courante, les
        # autres étant en `Ignored`.
        besoin = (self.pile.minimumSizeHint().width() + self.navigation.width()
                  + 4 * theme.Espacement.S)
        if self.width() < besoin:
            self.resize(besoin, self.height())

    def _construire_page(self, destination) -> QWidget:
        """Appelle la fabrique, range le panneau et le pose dans la pile.

        L'absence de fabrique est une **erreur de programmation**, pas un cas à tolérer : une
        destination qui ne mène nulle part est le pire des deux mondes, elle promet et ne
        tient pas. C'est le même arbitrage que `_fabriquer_action`."""
        fabrique = getattr(self, destination.fabrique)
        panneau = fabrique()
        self._panneaux[destination.identifiant] = panneau
        self.pile.addWidget(panneau)
        return panneau

    def _declencher_action(self, identifiant: str) -> None:
        action = self.actions_menu.get(identifiant)
        if action is not None:
            action.trigger()

    def destination(self) -> str:
        return getattr(self, "_destination", dst.ACCUEIL)

    # ------------------------------------------------------------------ #

    def page_accueil(self) -> QWidget:
        """L'accueil, et **il n'ouvre rien**. Cf. `gui/accueil.py`."""
        from .accueil import PanneauAccueil

        panneau = PanneauAccueil()
        panneau.demande_destination.connect(self.aller_a)
        panneau.demande_reprise.connect(self._reprendre)
        panneau.demande_creation.connect(self.action_nouveau_projet)
        panneau.demande_sources.connect(self.action_ouvrir_sources)
        panneau.demande_demonstration.connect(self.action_tome_de_demonstration)
        panneau.poser_recents(list(self.reglages.get("recents") or []),
                              sources=self._racine_sources())
        self._maj_etat_vide(panneau)
        return panneau

    def page_light_novel(self) -> QWidget:
        return self._page_lanceur("light_novel")

    def page_manga(self) -> QWidget:
        return self._page_lanceur("manga")

    def page_webtoon(self) -> QWidget:
        """Le lanceur manga avec `--format webtoon`, et la réserve mesurée en tête.

        ⚠ Aucun code de traitement n'est dupliqué : c'est la même classe, le même
        `process_volume`, le même `tache_run`. Le seul écart est le paramètre — exactement
        comme en ligne de commande."""
        return self._page_lanceur("webtoon")

    def _page_lanceur(self, identifiant: str) -> QWidget:
        from .lanceur import RESERVE_WEBTOON, PanneauLanceur

        brique, format_planche = LANCEURS[identifiant]
        panneau = PanneauLanceur(
            self.config, brique=brique, format_planche=format_planche,
            reserve=RESERVE_WEBTOON if identifiant == "webtoon" else "")
        panneau.demande_run.connect(self._lancer_run)
        panneau.demande_arret.connect(self._arreter_run)
        panneau.demande_assemblage.connect(self._assembler)
        panneau.demande_modeles.connect(self._lancer_sonde_modeles)
        panneau.brancher_actions(self.actions_menu, self._brancher_bouton)
        panneau.appliquer_reglages((self.reglages.get("runs") or {}).get(identifiant) or {})
        # ⚠ Le catalogue de modèles est celui que la sonde de démarrage a rendu, ou
        # « inconnu ». Un panneau construit après la sonde doit voir ce qu'elle a trouvé ; un
        # panneau construit avant doit afficher « inconnu » et non une liste vide qui se
        # lirait « aucun modèle ».
        panneau.poser_modeles(self._catalogue_modeles)
        # Un run peut déjà tourner quand la destination s'ouvre : un panneau construit en
        # retard doit refléter l'état de la fenêtre, pas celui de sa naissance.
        panneau.marquer_en_cours(self.fil.touche_tout())
        return panneau

    def page_illustrations(self) -> QWidget:
        from .atelier import PanneauAtelier

        panneau = PanneauAtelier(self.config, self.chemin_config)
        panneau.journal.connect(self._journaliser)
        panneau.demande_tache.connect(self.fil.soumettre)
        panneau.demande_bible.connect(self._ouvrir_bible)
        panneau.demande_dossier.connect(self._ouvrir_illustrations)
        panneau.appliquer_reglages(self.reglages.get("atelier") or {})
        panneau.poser_modeles(self._catalogue_modeles)
        return panneau

    def page_oeuvres(self) -> QWidget:
        """La bibliothèque des œuvres. Cf. `gui/oeuvres.py` — lot 34.

        ⚠ Le balayage ne part pas d'ici : il part sur le fil de travail, en `GENRE_BIBLIOTHEQUE`
        (donc sans verrouiller quoi que ce soit). Le construire de façon synchrone gèlerait la
        fenêtre pendant la seconde que coûtent les 18 œuvres du corpus — mesuré."""
        from .oeuvres import PanneauOeuvres

        panneau = PanneauOeuvres()
        panneau.demande_creation.connect(self.action_nouveau_projet)
        panneau.demande_sources.connect(self.action_ouvrir_sources)
        panneau.demande_balayage.connect(self._balayer_bibliotheque)
        panneau.demande_lancement.connect(self._oeuvres_lancer)
        panneau.demande_retouche.connect(self.retoucher)
        panneau.demande_import.connect(self.action_importer_build)
        panneau.demande_exports.connect(self._oeuvres_sorties)
        panneau.demande_export_glossaire.connect(self._oeuvres_exporter_glossaire)
        panneau.demande_dossier.connect(self._oeuvres_ouvrir_dossier)
        panneau.poser_racine(self._racine_sources())
        self._balayer_bibliotheque()
        return panneau

    # ------------------------------------------------------------------ #
    #  L34 — la bibliothèque : balayer, puis les cinq gestes d'un tome
    # ------------------------------------------------------------------ #

    def _balayer_bibliotheque(self) -> None:
        """Relit `sources/` et `build/` **hors du fil d'affichage**.

        ⚠ Un `Inventaire` NEUF à chaque balayage, et c'est délibéré : sa mémoïsation n'a
        aucune clé d'invalidation (cf. sa docstring), donc réutiliser l'objet ferait de
        « Rafraîchir » un bouton qui ne rafraîchit rien. Le coût est celui d'une lecture de
        répertoires, pas d'un décodage."""
        import bibliotheque as biblio

        config = self.config
        resultat = self._resultat_bibliotheque = {}

        def _travail():
            oeuvres = biblio.Inventaire(config).oeuvres()
            resultat["oeuvres"] = oeuvres
            tomes = sum(len(o.tomes) for o in oeuvres)
            return f"{len(oeuvres)} œuvre(s), {tomes} tome(s) relus."

        self.fil.soumettre(Tache(genre=GENRE_BIBLIOTHEQUE, fonction=_travail, planche=None,
                                 libelle="Lecture de la bibliothèque"))

    def _recevoir_bibliotheque(self, succes: bool, message: str) -> None:
        panneau = self._panneaux.get("oeuvres")
        if panneau is None:
            return
        oeuvres = (getattr(self, "_resultat_bibliotheque", {}) or {}).get("oeuvres")
        if not succes or oeuvres is None:
            # ⚠ Un échec ne laisse pas « Lecture des œuvres… » à l'écran pour toujours : une
            # attente qui ne finit jamais se lit comme une application bloquée.
            panneau.etat.setText(f"La lecture des œuvres a échoué : {message}")
            self._journaliser("warn", message)
            return
        panneau.poser_oeuvres(oeuvres)

    def _oeuvres_lancer(self, projet: str, tome: str, brique: str) -> None:
        """« Lancer » depuis la bibliothèque — **ouvre le lanceur, ne démarre rien.**

        ⚠ C'est le point du `PLAN-34` L34.5 : aucun bouton de la bibliothèque ne peut engager
        des heures de GPU. On amène à la destination qui annonce le coût, avec le tome
        présélectionné, et le focus sur son bouton — comme `_aller_aux_runs` le fait déjà
        depuis la retouche."""
        import bibliotheque as biblio

        destination = {biblio.MANGA: "manga", biblio.WEBTOON: "webtoon",
                       biblio.LN: "light_novel"}.get(brique)
        if destination is None:
            QMessageBox.information(
                self, "Pas de lanceur pour cette brique",
                f"« {projet} / {tome} » est un tome de la brique « {brique} », qui n'a pas de "
                f"destination dans l'interface. Elle se lance en console :" + SAUT_LIGNE
                + f'    python run_ocr.py "{projet}" {tome}')
            return
        lanceur = self.aller_a(destination)
        if lanceur is None:
            return
        if not lanceur.viser(projet, tome):
            self._journaliser("warn", f"« {projet} / {tome} » n'apparaît pas dans les listes "
                                      f"du lanceur — le tome a-t-il été déplacé ?")
            return
        lanceur.bouton_lancer.setFocus()

    def _oeuvres_sorties(self, projet: str, tome: str) -> None:
        """Le panneau des sorties d'un tome. **Il n'exécute rien.**"""
        import bibliotheque as biblio
        from .dialogues import DialogueSorties
        from . import sorties as srt

        info = biblio.tome_info(self.config, projet, tome,
                                glossaire=biblio.compter_glossaire(self.config, projet))
        boite = DialogueSorties(srt.panneau(self.config, info), self)
        boite.demande_ouverture.connect(self._ouvrir_dans_le_systeme)
        boite.exec()

    def _oeuvres_exporter_glossaire(self, projet: str, tome: str) -> None:
        """L'export du glossaire de l'ŒUVRE. Cf. `core/glossary_export.py`.

        ⚠ **Sur le fil d'affichage, et c'est justifié** : le plus gros glossaire du corpus
        fait 38 Ko et 124 entrées (manga D, mesuré le 2026-09-05). Écrire 38 Ko n'est
        pas une copie de 400 Mo ; envoyer ça sur le fil de travail ajouterait une file
        d'attente à un geste instantané."""
        import bibliotheque as biblio
        from .dialogues import DialogueExportGlossaire

        source = biblio.chemin_glossaire(self.config, projet)
        if not source.is_file():
            QMessageBox.information(
                self, "Aucun glossaire",
                f"« {projet} » n'a pas encore de glossaire ({source})." + SAUT_LIGNE
                + "Il est créé au premier run qui relève de la terminologie, et il est "
                  "partagé par tous les tomes de l'œuvre — roman et manga compris.")
            return
        boite = DialogueExportGlossaire(self.config, projet, tome, self)
        if boite.exec() == boite.DialogCode.Accepted:
            ecrit = getattr(boite, "ecrit", None)
            if ecrit is not None:
                self._journaliser("info", f"Glossaire exporté : {ecrit}")
                self.statusBar().showMessage(f"Glossaire exporté : {ecrit}", 8000)

    def _oeuvres_ouvrir_dossier(self, projet: str) -> None:
        dossier = self._racine_sources() / projet
        if not dossier.exists():
            QMessageBox.information(self, "Rien à ouvrir", f"{dossier} n'existe pas.")
            return
        self._ouvrir_dans_le_systeme(dossier)

    def page_diagnostic(self) -> QWidget:
        """La page Diagnostic — `PLAN-36` L36.2. Cf. `gui/diagnostic.py`.

        ⚠ **Elle ne lance rien à la construction.** Elle s'ouvre en disant qu'aucun diagnostic
        n'a tourné, ce qui est vrai, et attend un clic. Un diagnostic complet interroge le
        serveur de modèles — 12,1 s sur un serveur arrêté, mesuré le 2026-09-06 — et le lancer
        au premier affichage rejouerait exactement le défaut que le `PLAN-31` a corrigé."""
        from .diagnostic import PanneauDiagnostic

        # ⚠ La config est passée à la CONSTRUCTION : le bloc « Poids et modèles » lit
        # où chaque poids doit atterrir, et il s'affiche sans qu'aucun diagnostic ait
        # tourné — télécharger un poids est un geste, pas une réparation d'erreur.
        panneau = PanneauDiagnostic(config=self.config)
        panneau.demande_diagnostic.connect(self._lancer_diagnostic)
        panneau.demande_reparation.connect(self._lancer_reparation)
        panneau.demande_texte.connect(self._montrer_diagnostic_texte)
        return panneau

    # ------------------------------------------------------------------ #
    #  L36 — le diagnostic structuré, et les réparations gardées
    # ------------------------------------------------------------------ #

    def _lancer_diagnostic(self, reseau: bool = True) -> None:
        """Collecte les verdicts des deux briques **dans le fil de travail**.

        ⚠ `GENRE_SONDE`, comme les trois marqueurs de l'accueil, et pour la même raison : le
        genre décide de ce que l'interface verrouille, et un diagnostic n'écrit rien. Le
        passer en `GENRE_CREATION` grillerait le bandeau de run et poserait un verrou
        d'écriture pendant douze secondes de délai réseau.

        ⚠ `telechargement=False` : la console de `run_manga.py --check` récupère les poids
        manquants — taper la commande EST le geste explicite — mais **ouvrir une page ne l'est
        pas**. Ici on constate, et un bouton propose (`PLAN-36` L36.2 règle 1)."""
        panneau = self._panneaux.get("diagnostic")
        if panneau is not None:
            panneau.marquer_en_cours(True)
        config = self.config
        resultat = self._resultat_diagnostic = {}

        def _travail():
            from manga import doctor as doctor_manga
            from pipeline import doctor as doctor_ln

            sections = []
            for nom, collecte in (("light novel", doctor_ln.sections),
                                  ("manga", doctor_manga.sections)):
                try:
                    if nom == "manga":
                        sections.extend(collecte(config, ecrire=None, reseau=reseau,
                                                 telechargement=False))
                    else:
                        sections.extend(collecte(config, ecrire=None, reseau=reseau))
                except Exception as err:               # noqa: BLE001 — un doctor qui lève
                    # ⚠ Un doctor qui tombe ne doit pas emporter l'autre : c'est tout l'objet
                    # d'un diagnostic que d'inspecter ce qui reste inspectable.
                    sections.append(dia.Section("", (dia.Verdict(
                        f"doctor_{nom}", dia.SOCLE, dia.BLOQUANT,
                        constat=f"le diagnostic de la brique {nom} s'est interrompu "
                                f"({type(err).__name__} : {err})",
                        consequence="ce que cette brique aurait signalé reste inconnu.",
                        geste="relance le diagnostic ; si l'erreur persiste, lance "
                              "« run.py --check » en console, dont la sortie est plus "
                              "bavarde."),)))
            # ⚠ L'écart entre le `config.yaml` de l'utilisateur et celui que le paquet livre
            # (`PLAN-37` L37.4, piège 2). Rend `None` hors gel : rien n'apparaît pour qui lance
            # `python gui.py` depuis le dépôt.
            installation_ = dia.section_installation()
            if installation_ is not None:
                sections.append(installation_)
            resultat["sections"] = tuple(sections)
            compte = dia.resume(resultat["sections"])
            return (f"Diagnostic : {compte[dia.BLOQUANT]} bloquant(s), "
                    f"{compte[dia.DEGRADE]} dégradation(s) sur {compte['total']} point(s).")

        self.fil.soumettre(Tache(genre=GENRE_DIAGNOSTIC, fonction=_travail, planche=None,
                                 libelle="Diagnostic complet"))

    def _recevoir_diagnostic(self, succes: bool, message: str) -> None:
        """Pose les sections sur la page, **si elle est construite**."""
        panneau = self._panneaux.get("diagnostic")
        if panneau is None:
            return
        panneau.marquer_en_cours(False)
        sections = (getattr(self, "_resultat_diagnostic", {}) or {}).get("sections")
        if not succes or sections is None:
            self._journaliser("warn", f"Diagnostic : {message}")
            return
        panneau.poser_sections(sections)
        self._journaliser("info", message)

    def _lancer_reparation(self, identifiant: str) -> None:
        """Un geste réparateur — **licence affichée avant, confirmation, puis fil de travail**.

        Les trois refus possibles, et aucun n'est un incident :

        · la réparation n'est pas automatique (classe `UTILISATEUR` ou `HORS_PERIMETRE`) : on
          affiche ce qu'il faut faire, et on s'arrête. Angelith n'installe aucun logiciel
          système ;
        · un run est en cours : **aucun téléchargement pendant un run** — un run de nuit qui
          se met à récupérer deux gigaoctets n'est plus le run qu'on a lancé ;
        · l'utilisateur ne confirme pas. C'est le cas normal du bouton « Annuler », et c'est
          pourquoi `reparations.executer` exige `consentement=True` explicitement.
        """
        from core import reparations as rep
        # ⚠ Importer ce module ENREGISTRE les réparations de la brique manga dans le catalogue
        # commun. Sans lui, `par_identifiant("poids_detection")` rendrait `None` — ce qui est
        # exact au sens de `core/reparations.py` (« on ne répare pas une brique qu'on n'a pas
        # chargée ») et faux ici, puisque la fenêtre pilote bel et bien la brique manga.
        from manga import reparations as _rep_manga  # noqa: F401

        reparation = rep.par_identifiant(identifiant)
        if reparation is None:
            return
        if not reparation.automatique:
            QMessageBox.information(self, reparation.libelle, reparation.consigne())
            return
        if self.fil.occupe() or self.fil.en_attente():
            QMessageBox.warning(self, reparation.libelle, rep.MOTIF_RUN_EN_COURS)
            return
        boite = QMessageBox(self)
        boite.setWindowTitle(reparation.libelle)
        boite.setText(f"{reparation.libelle} ?")
        # ⚠ `consigne()` porte la LICENCE, la source primaire et la taille — et elle est
        # montrée AVANT le clic. Une licence affichée après le téléchargement ne sert à rien.
        boite.setInformativeText(reparation.consigne())
        boite.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        boite.setDefaultButton(QMessageBox.Cancel)
        if boite.exec() != QMessageBox.Ok:
            return

        config = self.config

        def _travail():
            chemin = rep.executer(identifiant, config, consentement=True, run_en_cours=False,
                                  dire=lambda m: self.signaux.ligne.emit("info", str(m)))
            return (f"{reparation.libelle} : terminé"
                    + (f" — {chemin}" if chemin else "."))

        self.fil.soumettre(Tache(genre=GENRE_CREATION, fonction=_travail, planche=None,
                                 libelle=reparation.libelle))

    def _montrer_diagnostic_texte(self) -> None:
        """La sortie console exacte, pour qui doit la coller dans un rapport.

        ⚠ Elle est reconstituée depuis les `lignes_console` des verdicts déjà collectés — on
        ne relance pas les doctors. Relancer coûterait un second appel réseau et pourrait
        rendre un texte qui ne décrit plus ce que la page montre."""
        from .dialogues import DialogueTexte

        panneau = self._panneaux.get("diagnostic")
        sections = panneau.sections() if panneau is not None else ()
        texte = dia.texte_console(sections) if sections else ""
        DialogueTexte(
            "Diagnostic — sortie console", texte or
            "(aucun diagnostic n'a encore tourné dans cette session)", self,
            sous_titre="Le texte exact de « run.py --check » et « run_manga.py --check »."
        ).exec()

    def page_retouche(self) -> QWidget:
        """L'éditeur de planches, avec **son propre** couple projet/tome. Cf. `gui/retouche.py`.

        ⚠ C'est ici que la barre haute de la fenêtre a atterri, et nulle part ailleurs. Le
        tome n'est plus un état de la fenêtre que trois panneaux lisent : il appartient à la
        destination qui l'édite, et les lanceurs ont les leurs depuis le lot 18."""
        from .retouche import PanneauRetouche

        panneau = PanneauRetouche(self.config)
        editeur = panneau.editeur
        editeur.journal.connect(self._journaliser)
        editeur.demande_relettrage.connect(self._relettrer)
        editeur.etat_document.connect(self._marquer_modifie)
        # L18.1 — l'état vide n'est plus une ligne de journal mais deux boutons dans le
        # panneau. Le panneau ne sait pas créer un projet ; il demande, la fenêtre fait.
        editeur.demande_creation.connect(self.action_nouveau_projet)
        editeur.demande_sources.connect(self.action_ouvrir_sources)
        # L19.7 — « jamais traité » demande un run, et le geste attendu est maintenant un
        # bouton plutôt qu'une phrase qui nomme un onglet.
        editeur.demande_runs.connect(self._aller_aux_runs)
        # L35.5 — « Arrêter proprement » depuis l'éditeur verrouillé. Le MÊME `_arreter_run`
        # que le bandeau de run et que le lanceur : un seul mécanisme d'arrêt, donc une seule
        # garantie à tenir.
        editeur.demande_arret.connect(self._arreter_run)
        panneau.demande_tome.connect(self.ouvrir_tome)

        cfg_gui = (self.config.get("gui") or {}).get("apercu") or {}
        plafond = self.reglages.get("plafond_mo") or cfg_gui.get("plafond_mo", 120)
        fenetre_pre = self.reglages.get("fenetre_apercu")
        if fenetre_pre is None:
            fenetre_pre = cfg_gui.get("fenetre", 10)
        editeur.cache.plafond = max(1, int(plafond)) * 1024 * 1024
        editeur.brancher(self.fil, self.services, self.fil_lecture,
                         fenetre=int(fenetre_pre))
        editeur.appliquer_reglages(self.reglages)
        self._brancher_bouton(panneau.bouton_projet, "enregistrer_tome", libelle=True)
        editeur.brancher_actions(self.actions_menu, self._brancher_bouton)
        editeur.choix_filtre.currentTextChanged.connect(self._refleter_filtre)
        self._refleter_filtre(editeur.choix_filtre.currentText())
        # ⚠ APRÈS le branchement, et **sans rien ouvrir** : c'est le point du lot. Les deux
        # `blockSignals` de `PanneauRetouche.remplir_projets` coupent la chaîne qui, jusqu'à
        # la 2.24.1, ouvrait le premier projet par ordre alphabétique.
        projets = panneau.remplir_projets()
        if not projets:
            self._avertir_sources_vide()
            editeur.montrer_accueil(
                "Aucun projet manga sous " + str(self._racine_sources()),
                "Angelith lit les planches sous sources/<Projet>/<Tome>/manga/. "
                "Le bouton ci-dessous crée cette arborescence et y copie tes images ou ton "
                "archive — tu peux aussi les faire glisser sur cette fenêtre.")
        panneau.marquer_run(self.fil.touche_tout())
        return panneau

    # ------------------------------------------------------------------ #
    #  Les panneaux, quand ils existent
    # ------------------------------------------------------------------ #
    #
    # ⚠ Ces propriétés rendent `None` tant que la destination n'a pas été ouverte, et tous les
    # appelants le gèrent. C'est le prix de la construction paresseuse, et il est explicite :
    # un `self.editeur` qui existerait toujours voudrait dire qu'on l'a construit au
    # démarrage, c'est-à-dire exactement ce que le lot supprime.

    @property
    def retouche(self):
        return self._panneaux.get("retouche")

    @property
    def editeur(self):
        panneau = self._panneaux.get("retouche")
        return panneau.editeur if panneau is not None else None

    @property
    def atelier(self):
        return self._panneaux.get("illustrations")

    def lanceurs(self) -> list:
        """Les panneaux de lancement CONSTRUITS, dans l'ordre du pane."""
        return [self._panneaux[i] for i in LANCEURS if i in self._panneaux]

    def _verbose_manga(self) -> bool:
        """La case « Journal détaillé » du lanceur manga, ou sa valeur persistée.

        ⚠ Lue par le bouton « Appliquer » de la retouche : un relettrage doit laisser la même
        trace qu'un run, sinon `perf.log` raconte un tome à trous. Le lanceur peut ne pas être
        construit — c'est même le cas normal après ce lot — d'où le repli sur le fichier de
        réglages, qui porte la même valeur."""
        panneau = self._panneaux.get("manga")
        if panneau is not None:
            return panneau.verbose()
        return bool(((self.reglages.get("runs") or {}).get("manga") or {})
                    .get("verbose", True))

    # ------------------------------------------------------------------ #
    # Le tome — ouvert À LA DEMANDE, jamais au démarrage
    # ------------------------------------------------------------------ #

    def _racine_sources(self) -> Path:
        from manga.creation_projet import racine_sources
        return racine_sources(self.config)

    def _avertir_sources_vide(self) -> None:
        """La ligne `warn` du lot 18 — elle déplie le journal et tient 8 s en barre d'état.

        ⚠ Elle RESTE, et l'accueil ne la remplace pas : elle décrit un geste à faire dans un
        AUTRE logiciel, ce que l'écran ne dit pas, et elle laisse dans le journal — qu'on
        relit après coup — la trace d'un démarrage sur un `sources/` vide."""
        self._journaliser("warn", "Aucun projet manga trouvé sous sources/ — « Fichier → "
                                  "Nouveau projet » crée l'arborescence pour toi.")

    def action_tome_de_demonstration(self) -> None:
        """L36.4 — « Créer un tome de démonstration ». Le geste d'une installation neuve.

        Trois refus possibles, et chacun dit ce qu'il refuse :

        · **la police manque** — le geste se refuse PROPREMENT, en nommant la variable
          d'environnement, les candidats essayés et la commande d'installation. Une planche de
          démonstration dont les bulles rendent des tofus ferait croire à un défaut
          d'Angelith, et `tests/conftest.py` a le droit de *skipper* là où une application
          livrée ne l'a pas (`PLAN-20` L20.2) ;
        · **le tome existe déjà** — on propose de le refaire, ce qui l'écrase. Aucune œuvre
          n'est concernée : `manga/demonstration.py` refuse d'effacer un dossier qui ne porte
          pas exactement son nom ;
        · **un run tourne** — l'écriture passe par la file, comme toute écriture sous
          `sources/`.

        ⚠ Dans le fil de travail, en `GENRE_CREATION` : il écrit sous `sources/` et sous
        `build/`, donc il prend le verrou d'écriture comme un import d'archive."""
        from manga import demonstration as demo

        config = self.config
        ecraser = False
        if demo.existe(config):
            reponse = QMessageBox.question(
                self, "Tome de démonstration",
                f"Le tome de démonstration existe déjà :\n{demo.dossier_sources(config)}\n\n"
                f"Le refaire ? Son contenu actuel sera remplacé. Aucune de tes œuvres n'est "
                f"concernée.")
            if reponse != QMessageBox.Yes:
                return
            ecraser = True

        def _travail():
            tome = demo.creer(config, ecraser=ecraser,
                              dire=lambda m: self.signaux.ligne.emit("info", str(m)))
            return (f"Tome de démonstration prêt : {tome.libelle} — "
                    f"{len(tome.planches)} planche(s) sous {tome.sources}.")

        self.fil.soumettre(Tache(genre=GENRE_CREATION, fonction=_travail, planche=None,
                                 libelle="Tome de démonstration"))

    def _maj_etat_vide(self, accueil=None) -> None:
        """Dit à l'accueil si `sources/` est vide. **Un listage de dossier, pas un balayage.**"""
        panneau = accueil if accueil is not None else self._panneaux.get(dst.ACCUEIL)
        if panneau is None:
            return
        if lister_projets(self.config):
            panneau.cacher_etat_vide()
        else:
            panneau.montrer_etat_vide(self._racine_sources())

    def ouvrir_tome(self, projet: str, tome: str) -> None:
        """Ouvre un tome DANS LA RETOUCHE. Le seul chemin, et il part d'un geste.

        ⚠ La garde de travail non enregistré est ici, inchangée. Elle était armée sur le
        changement de combo de la barre haute ; la barre haute est descendue dans
        `PanneauRetouche`, la garde l'a suivie. Aucune autre destination ne change ce tome :
        les lanceurs ont leurs propres listes et ne touchent qu'à la cible de leur run."""
        if not (projet and tome):
            return
        panneau = self._panneaux.get("retouche")
        if panneau is None:
            panneau = self.aller_a("retouche")
            if panneau is None:
                return
        if self._tome_precedent == (projet, tome) and self.tome is not None:
            # ⚠ Le MÊME tome, réémis. Remplir la liste des tomes la vide puis la repeuple —
            # donc `currentTextChanged` part deux fois — et un run qui se termine rafraîchit la
            # fenêtre. Sans cette garde, chacun de ces passages rouvrait le tome (donc jetait
            # brouillons et documents) ou, depuis le lot 18, demandait s'il faut les jeter.
            return
        # ⚠ « projet » plutôt que « tome » quand c'est le PROJET qui a changé : les deux
        # perdent le même travail et posent la même boîte, mais `gui/garde.py` les nomme
        # séparément parce que le tableau de l'étape 0.2 les compte séparément — et une ligne
        # de tableau sans correspondant dans le code est une ligne qui vieillit sans qu'on
        # s'en aperçoive.
        ancien = self._tome_precedent
        chemin = "projet" if (ancien and ancien[0] != projet) else "tome"
        if not self.peut_quitter(chemin, cible=f"{projet} / {tome}"):
            return
        if self.services is not None:
            self.services.liberer()
        self.tome = Tome(self.config, projet, tome)
        # Un `Services` par tome : deux tomes peuvent viser des endpoints différents, et un
        # porteur global rendrait le second silencieusement faux.
        self.services = Services(self.config, projet, reporter=ReporterQt(self.signaux),
                                 langue=self.tome.langue_source())
        panneau.editeur.brancher(self.fil, self.services, self.fil_lecture)
        panneau.editeur.ouvrir(self.tome)
        self._maj_revision()
        self._tome_precedent = (projet, tome)
        self._maj_actions_tome()
        self.reglages = reg.noter_recent(self.reglages, projet, tome, "retouche")
        self._journaliser("stage", f"{projet} / {tome} — "
                                   f"{len(self.tome.index_planches())} planche(s) en cache")

    def retoucher(self, projet: str, tome: str) -> None:
        """Ouvrir un tome dans la retouche **et y aller** — `PLAN-35` L35.2.

        ⚠ La distinction avec `ouvrir_tome` n'est pas un raffinement, c'est un défaut mesuré.
        Le lot 34 branchait « Retoucher » de la bibliothèque directement sur `ouvrir_tome`,
        qui ne navigue que si la destination n'existe pas encore :

            panneau = self._panneaux.get("retouche")
            if panneau is None:
                panneau = self.aller_a("retouche")

        Autrement dit, le bouton marchait **la première fois** et paraissait sans effet
        ensuite — le tome s'ouvrait bien, derrière la bibliothèque restée à l'écran. C'est le
        pire des retours : le geste a réussi et rien ne le montre.

        Le chemin inverse, lui, existait déjà dans l'autre sens depuis le lot 19
        (`editeur.demande_runs` → `_aller_aux_runs`), et pour la même raison — « le geste
        attendu est un bouton plutôt qu'une phrase qui nomme un onglet »."""
        if not (projet and tome):
            return
        if self.aller_a("retouche") is None:
            return
        self.ouvrir_tome(projet, tome)

    def _retoucher_le_run(self) -> None:
        """« Retoucher les planches » depuis le bilan d'un run — L35.2, le chemin inverse.

        ⚠ Le tome visé est celui du run qui vient de finir, pas celui qui serait ouvert dans
        la retouche : `_cible_run` le porte, et c'est ce qui rend le bouton juste même quand
        on a lancé le run depuis « Manga » sans jamais ouvrir la retouche de la session."""
        cible = self._cible_run or {}
        projet, tome = str(cible.get("projet") or ""), str(cible.get("tome") or "")
        if not (projet and tome):
            return
        self.retoucher(projet, tome)

    def _reprendre(self, destination: str, projet: str, tome: str) -> None:
        """La carte « Reprendre » de l'accueil : **un clic**, pas un effet de bord du démarrage.

        ⚠ Ce que le fichier de réglages dit peut être périmé — un tome supprimé, un dossier
        renommé depuis la dernière session. On le DIT plutôt que d'ouvrir un tome vide : c'est
        exactement le mode de panne qu'avait l'ancien démarrage, en silence."""
        # ⚠ `viser` est le contrat commun de `PanneauRetouche` et de `PanneauLanceur`. Une
        # destination qui ne le porte pas — l'accueil, les œuvres — ne peut pas recevoir un
        # tome ; y renvoyer un « Reprendre » serait un clic sans effet.
        panneau = self.aller_a(destination) if destination in dst.identifiants() else None
        if panneau is None or not hasattr(panneau, "viser"):
            panneau = self.aller_a("retouche")
        if panneau is None:
            return
        if not panneau.viser(projet, tome):
            self._journaliser(
                "warn", f"« {projet} / {tome} » est dans les récents mais introuvable sous "
                        f"{self._racine_sources()} — le dossier a-t-il été renommé ou "
                        f"supprimé ?")

    def _restaurer_selection_de_tome(self) -> None:
        """Remet les listes de la retouche sur le tome qu'on n'a pas quitté.

        ⚠ `PanneauRetouche.restaurer` porte la garde `_retour_de_garde` : `setCurrentText`
        réémet `currentTextChanged`, donc la demande d'ouverture, donc la garde — et la boîte
        se rouvrirait à l'infini."""
        panneau = self._panneaux.get("retouche")
        if panneau is None or self._tome_precedent is None:
            return
        panneau.restaurer(*self._tome_precedent)

    def peut_quitter(self, chemin: str, *, cible: str = "") -> bool:
        """**La** garde de travail non enregistré — une implémentation, six appelants.

        `PLAN-35` L35.4. Renvoie `False` quand il faut renoncer au geste ; `True` sinon,
        éventuellement après avoir écrit ce qui attendait.

        ## Les six chemins, et pourquoi trois ne demandent rien

        La liste et les verdicts sont dans `gui/garde.py`, sans Qt, chacun avec son motif :
        changer de tome, changer de projet et fermer la fenêtre perdent le travail ; changer
        de destination, lancer un run et créer un projet ne le perdent pas. Les six passent
        quand même par ici, et ce n'est pas de la cérémonie — c'est ce qui fait qu'ajouter un
        septième chemin demain oblige à écrire son verdict au lieu de l'oublier.

        ⚠ **Aucune boîte sur un chemin qui ne perd rien, même avec trente planches en
        attente.** Un dialogue qui se pose à chaque changement d'onglet est un dialogue qu'on
        apprend à cliquer sans lire, et c'est la façon la plus sûre de perdre du travail
        *avec* une garde en place (`PLAN-35` L35.4).

        ## Le défaut que ceci ferme, et qui est plus ancien que le lot 35

        Fermer la fenêtre avec du travail non enregistré ouvrait une boîte « Enregistrer /
        Quitter sans enregistrer / Annuler ». **Changer de tome, non** : `PanneauEditeur.ouvrir`
        vide `_brouillons_par_planche` et `documents` inconditionnellement, sans un mot. Le seul
        filet était le miroir de récupération écrit toutes les 30 s — un filet, pas une
        décision. Le lot 18 a branché la boîte sur ce chemin-là ; ce lot-ci nomme les quatre
        autres et prouve lesquels sont sans risque."""
        editeur = self.editeur
        attente = editeur.planches_modifiees() if (editeur and self.tome) else []
        if not grd.doit_demander(chemin, attente):
            return True
        verbe, consequence = grd.phrase(chemin, cible)
        choix = self._boite_travail_en_attente(attente, verbe=verbe, consequence=consequence)
        if choix == "annuler":
            self._annuler_le_geste(chemin)
            return False
        if choix == "enregistrer":
            ecrites, refusees = editeur.enregistrer_tout()
            if ecrites:
                self._journaliser("info", f"{len(ecrites)} planche(s) enregistrée(s) : "
                                          f"{', '.join(str(n) for n in ecrites)}.")
            if refusees:
                # Partir sur un refus MUET serait le défaut qu'on corrige sous un autre nom :
                # on renonce au geste et on NOMME les planches en cause.
                pluriel = len(refusees) > 1
                QMessageBox.warning(
                    self, "Planches non enregistrées",
                    f"{_liste(refusees, majuscule=True)} n'{'ont' if pluriel else 'a'} pas pu "
                    f"être enregistrée{'s' if pluriel else ''} : un run "
                    f"{'les' if pluriel else 'l’'}a réécrite{'s' if pluriel else ''} depuis son "
                    f"ouverture." + SAUT_LIGNE
                    + f"« {verbe} » est annulé — ce travail est conservé.")
                self._annuler_le_geste(chemin)
                return False
        return True

    def _annuler_le_geste(self, chemin: str) -> None:
        """Remet l'interface dans l'état d'avant un geste refusé.

        ⚠ Seuls les deux chemins qui passent par une liste déroulante ont quelque chose à
        défaire : `setCurrentText` a déjà bougé quand la boîte s'ouvre. La fermeture, elle,
        s'annule par `event.ignore()` chez l'appelant — il n'y a aucun widget à remettre."""
        if chemin in ("tome", "projet"):
            self._restaurer_selection_de_tome()

    def _boite_travail_en_attente(self, attente: list[int], *, verbe: str,
                                  consequence: str) -> str:
        """La boîte à trois choix. Renvoie `"enregistrer"`, `"abandonner"` ou `"annuler"`.

        Une SEULE implémentation, appelée par `closeEvent` et par la garde de changement de
        tome. Deux boîtes qui se ressemblent finissent toujours par diverger, et c'est
        justement la divergence — l'une existait, l'autre pas — que le lot 18 corrige."""
        boite = QMessageBox(self)
        boite.setWindowTitle("Modifications non enregistrées")
        boite.setText(f"{_liste(attente, majuscule=True)} porte"
                      f"{'nt' if len(attente) > 1 else ''} des modifications non "
                      f"enregistrées.")
        boite.setInformativeText(consequence)
        enregistrer = boite.addButton(f"Enregistrer et {verbe.lower()}", QMessageBox.AcceptRole)
        abandonner = boite.addButton(f"{verbe} sans enregistrer", QMessageBox.DestructiveRole)
        boite.addButton("Annuler", QMessageBox.RejectRole)
        boite.setDefaultButton(enregistrer)
        boite.exec()
        clique = boite.clickedButton()
        if clique is enregistrer:
            return "enregistrer"
        return "abandonner" if clique is abandonner else "annuler"

    def _maj_revision(self) -> None:
        panneau = self._panneaux.get("retouche")
        if self.tome is None or panneau is None:
            return
        panneau.poser_revision(self.tome.revision())

    def _recharger_glossaire(self) -> None:
        if self.services is not None:
            self.services.recharger_glossaire()
            self._journaliser("info", "Glossaire rechargé depuis le disque.")

    # ------------------------------------------------------------------ #
    # Runs
    # ------------------------------------------------------------------ #

    def _reporter_de_run(self, config: dict, brique: str, projet: str, tome: str) -> ReporterQt:
        """Un `ReporterQt` avec son `perf.log`, exactement comme `run_manga._make_reporter`.

        C'est ce qui manquait : `set_verbose_log` n'était appelé nulle part depuis `gui/`, si
        bien que `Reporter._to_log` sautait silencieusement toutes les écritures et que
        `perf.log` n'existait jamais pour un run lancé à l'écran."""
        reporter = cli.make_reporter(
            ReporterQt(self.signaux), build_dir_de(config, brique, projet, tome),
            verbose=bool(config.get("options", {}).get("verbose")),
            dry_run=bool(config.get("options", {}).get("dry_run")))
        self._reporters_ouverts.append(reporter)
        return reporter

    def _lancer_run(self, parametres: dict) -> None:
        if self.fil.touche_tout():
            QMessageBox.information(self, "Run en cours",
                                    "Un run tourne déjà. Attends-le, ou demande l'arrêt propre.")
            return
        # ⚠ Un run global VERROUILLE le tome ouvert, il ne le jette pas : `gui/garde.py` le
        # classe donc sans perte, et cet appel ne pose aucune boîte. Il est là pour que le
        # tableau des six chemins de l'étape 0.2 ait six appelants réels — un verdict qu'aucun
        # code n'exerce est un verdict qu'on ne saura pas avoir cassé.
        if not self.peut_quitter("run"):
            return
        parametres = dict(parametres)
        config = parametres["config"]
        # ⚠ L'énergie du run (`--keep-awake` / `--shutdown`) QUITTE le dictionnaire ici :
        # l'anti-veille repart dans la tâche, l'extinction reste à la fenêtre. Cf.
        # `gui/extinction.py` pour la ligne entre les deux, et pourquoi elle est là.
        energie = self._energie_du_run = dict(parametres.pop("energie", {}) or {})
        parametres["keep_awake"] = bool(energie.get("keep_awake"))
        # Un run lancé depuis l'onglet « Runs » peut réécrire n'importe quelle planche : on
        # ne sait pas lesquelles, donc on retombe sur le vidage complet. Remettre `None` ici
        # est ce qui empêche d'hériter de la liste d'un « Enregistrer le projet » précédent.
        self._planches_du_run = None
        self._cible_run = {k: parametres[k] for k in ("brique", "projet", "tome")}
        self._cible_run["config"] = config
        self._arret_demande = False
        reporter = self._reporter_de_run(config, parametres["brique"],
                                         parametres["projet"], parametres["tome"])
        self.fil.soumettre(tache_run(reporter=reporter, **parametres))
        self._marquer_run(True)
        self.reglages = reg.noter_recent(self.reglages, parametres["projet"],
                                         parametres["tome"], self.destination())

    def _arreter_run(self) -> None:
        """« Arrêter proprement », qu'on l'ait demandé au lanceur ou au bandeau.

        ⚠ **Les deux briques ne s'arrêtent pas par le même chemin**, et le bandeau est
        visible pour les deux. Un run d'orchestrateur s'arrête par un fichier `STOP` dans son
        dossier de build — le mécanisme de `--stop` ; l'atelier d'illustration, lui, porte un
        drapeau que sa boucle relit entre deux images, parce qu'un modèle interrompu en plein
        débruitage laisse le pilote dans un mauvais état. Router un geste vers l'autre
        écrirait un `STOP` dans le dossier d'un tome que personne ne traite."""
        if self._genre_du_run == GENRE_ILLUSTRATION:
            atelier = self.atelier
            if atelier is not None:
                atelier.demander_arret()
            return
        if self._cible_run is None:
            return
        demander_arret(self._cible_run["config"], self._cible_run["brique"],
                       self._cible_run["projet"], self._cible_run["tome"])
        # ⚠ Un arrêt DEMANDÉ annule l'extinction, un échec ne l'annule pas. C'est le
        # comportement de `core/cli.finalize_power`, mot pour mot — et `gui/extinction.py`
        # porte le pourquoi. L'interface et la ligne de commande doivent éteindre dans les
        # mêmes cas, ou l'une des deux ment.
        self._arret_demande = True
        self._journaliser("warn", "Arrêt demandé — le run s'arrêtera à la prochaine frontière "
                                  "propre (une planche, ou un lot entier si le lot > 1).")
        if self._energie_du_run.get("shutdown"):
            self._journaliser("warn", "L'extinction du PC prévue à la fin de ce run est "
                                      "annulée : un arrêt demandé est une présence humaine.")

    def _relettrer(self, planche: int, etape: str) -> None:
        """Bouton « Appliquer » de l'éditeur : un run sur UNE planche.

        `passes_volume=False` : le relevé terminologique, le dédoublonnage du glossariste et
        la fiche de contexte raisonnent à l'échelle du TOME. Les rejouer pour une planche
        isolée est du temps pur — et, dans le cas du glossariste, une réécriture complète du
        glossaire pour rien."""
        if self.tome is None:
            return
        config = copy.deepcopy(self.config)
        config.setdefault("options", {})["verbose"] = self._verbose_manga()
        self._cible_run = {"brique": "manga", "projet": self.tome.projet,
                           "tome": self.tome.tome, "config": config}
        reporter = self._reporter_de_run(config, "manga", self.tome.projet, self.tome.tome)

        projet, tome = self.tome.projet, self.tome.tome

        def _travail():
            from manga.orchestrator_manga import process_volume
            termine = process_volume(projet, tome, config, reporter=reporter,
                                     restart_from=etape, only_page=planche,
                                     passes_volume=False)
            return (f"Planche {planche} régénérée depuis « {etape} »." if termine
                    else "Arrêté proprement.")

        # ⚠ `planche=planche`, et non `None`. Une tâche sans numéro déclare « je touche tout
        # le tome » et `_sur_debut` grisait donc l'éditeur ENTIER pour le relettrage d'une
        # seule planche — un sur-verrouillage pur, puisque `only_page` garantit le contraire.
        self.fil.soumettre(Tache(genre=GENRE_RUN, fonction=_travail, planche=planche,
                                 libelle=f"Planche {planche} — reprise depuis « {etape} »"))

    # ------------------------------------------------------------------ #
    # Enregistrer le projet
    # ------------------------------------------------------------------ #

    def _planches_perimees(self) -> list[int]:
        if self.tome is None:
            return []
        return etat_planches.planches_a_relettrer(self.tome.build_dir)

    def _enregistrer_projet(self) -> None:
        """Écrire tout, relettrer ce qui est périmé, réassembler **une fois**.

        C'est le geste que l'interface ne savait pas faire : « Appliquer » relançait
        l'orchestrateur planche par planche, et le CBZ était un bouton à part. Corriger dix
        planches coûtait dix démarrages et dix archives.

        L'ordre compte. On écrit d'abord — sinon `planches_a_relettrer`, qui compare des dates
        de fichiers, ne verrait pas ce qui est encore en mémoire."""
        if self.tome is None:
            return
        if self.fil.touche_tout():
            QMessageBox.information(self, "Run en cours",
                                    "Un run tourne déjà. Attends-le, ou demande l'arrêt propre.")
            return

        editeur = self.editeur
        if editeur is None:
            return
        ecrites, refusees = editeur.enregistrer_tout()
        if ecrites:
            self._journaliser("info", f"{len(ecrites)} planche(s) enregistrée(s) : "
                                      + ", ".join(str(n) for n in ecrites))
        if refusees:
            self._journaliser("warn", f"{len(refusees)} planche(s) refusée(s) (modifiées sur "
                                      f"le disque entre-temps, leur travail est CONSERVÉ) : "
                                      + ", ".join(str(n) for n in refusees))
        self._maj_revision()

        perimees = self._planches_perimees()
        if not perimees:
            self._journaliser("info", "Rien à relettrer : tous les rendus sont à jour.")
            QMessageBox.information(self, "Projet à jour",
                                    "Tout est enregistré et aucun rendu n'est périmé.")
            return

        choix = self._demander_relettrage(perimees)
        if choix is None:
            return
        planches, assembler = choix
        self._lancer_relettrage_groupe(planches, assembler)

    def _demander_relettrage(self, perimees: list[int]):
        """Le récapitulatif avant de s'engager. Renvoie `(planches, assembler)` ou `None`.

        Engager plusieurs minutes sans l'avoir annoncé serait le défaut même qu'on corrige."""
        assert self.tome is not None
        lignes = []
        for numero in perimees[:15]:
            motifs = etat_planches.motifs_de_peremption(self.tome.build_dir, numero)
            lignes.append(f"  · planche {numero} — " + (", ".join(motifs) or "à relettrer"))
        if len(perimees) > 15:
            lignes.append(f"  · … et {len(perimees) - 15} autre(s)")

        secondes = max(1, round(len(perimees) * SECONDES_PAR_RELETTRAGE))
        duree = (f"{secondes} s" if secondes < 90
                 else f"{secondes // 60} min {secondes % 60:02d}")

        boite = QMessageBox(self)
        boite.setWindowTitle("Enregistrer les modifications du projet")
        boite.setText(f"{len(perimees)} planche(s) à relettrer (~{duree}).")
        boite.setInformativeText("\n".join(lignes))
        case = QCheckBox("Réassembler le CBZ/PDF ensuite")
        case.setChecked(True)
        boite.setCheckBox(case)
        lancer = boite.addButton("Enregistrer", QMessageBox.AcceptRole)
        boite.addButton("Annuler", QMessageBox.RejectRole)
        boite.setDefaultButton(lancer)
        boite.exec()
        if boite.clickedButton() is not lancer:
            return None
        return perimees, case.isChecked()

    def _lancer_relettrage_groupe(self, planches: list[int], assembler: bool) -> None:
        """UN seul `process_volume` pour toutes les planches, puis UN seul assemblage."""
        assert self.tome is not None
        config = copy.deepcopy(self.config)
        config.setdefault("options", {})["verbose"] = self._verbose_manga()
        projet, tome = self.tome.projet, self.tome.tome
        self._cible_run = {"brique": "manga", "projet": projet, "tome": tome, "config": config}
        reporter = self._reporter_de_run(config, "manga", projet, tome)
        build_dir = self.tome.build_dir
        cibles = list(planches)

        def _travail():
            from manga.orchestrator_manga import assemble_outputs, process_volume
            termine = process_volume(projet, tome, config, reporter=reporter,
                                     restart_from="rendu", only_pages=set(cibles),
                                     passes_volume=False)
            if not termine:
                return "Arrêté proprement — les planches déjà relettrées sont écrites."
            resume = f"{len(cibles)} planche(s) relettrée(s)"
            if assembler:
                sorties = assemble_outputs(build_dir, config["manga"], projet, tome,
                                           reporter=reporter)
                resume += " · " + (", ".join(Path(s).name for s in sorties)
                                   or "rien à assembler")
            return resume

        # `planche=None` reste juste : `process_volume` peut toucher à tout le tome, donc le
        # verrou d'écriture doit être global. Mais les planches RÉÉCRITES, elles, sont connues.
        self._planches_du_run = list(cibles)
        self.fil.soumettre(Tache(genre=GENRE_RUN, fonction=_travail, planche=None,
                                 libelle=f"Projet — {len(cibles)} planche(s) à relettrer"))
        self._marquer_run(True)

    def _assembler(self) -> None:
        if self.tome is None:
            return
        from manga.orchestrator_manga import assemble_outputs
        tome, config = self.tome, self.config
        reporter = ReporterQt(self.signaux)

        def _travail():
            sorties = assemble_outputs(tome.build_dir, config["manga"], tome.projet,
                                       tome.tome, reporter=reporter)
            return "Sorties réassemblées : " + (", ".join(Path(s).name for s in sorties)
                                                or "rien à écrire")

        # Assembler relit `pages_out/` sans en réécrire une seule : aucun aperçu ne devient
        # faux. La liste vide dit exactement cela, là où `None` déclencherait un vidage.
        self._planches_du_run = []
        self.fil.soumettre(Tache(genre=GENRE_ASSEMBLAGE, fonction=_travail, planche=None,
                                 libelle="Assemblage des sorties"))

    # ------------------------------------------------------------------ #
    # Retours du fil
    # ------------------------------------------------------------------ #

    def _marquer_run(self, en_cours: bool) -> None:
        """Un run global : les lanceurs construits basculent, la retouche grise son tome.

        ⚠ **Le changement de DESTINATION reste libre.** Ce qui est interdit pendant un run,
        c'est de changer le tome ouvert — un `process_volume` réécrit ses checkpoints, en
        éditer un autre par-dessus donnerait deux vérités. Regarder ailleurs pendant que ça
        tourne n'a jamais rien cassé, et c'est même ce que le `PLAN-32` demandera."""
        for lanceur in self.lanceurs():
            lanceur.marquer_en_cours(en_cours)
        panneau = self._panneaux.get("retouche")
        if panneau is not None:
            panneau.marquer_run(en_cours)

    def _brique_du_run(self, genre: str) -> str:
        """Quel jeu de phases déclarer. `""` = aucun, donc avancement purement compté.

        ⚠ Ce n'est PAS deviné sur un libellé. Le genre de tâche et `_cible_run["brique"]`
        sont posés par celui qui a soumis le travail ; les lire est le seul chemin qui ne
        se trompe pas le jour où un libellé change."""
        if genre == GENRE_ILLUSTRATION:
            return "illustration"
        if genre != GENRE_RUN:
            # Un import, une copie de sources, un assemblage : aucune phase déclarée, donc
            # une barre indéterminée qui dit ce qu'elle fait — plutôt qu'un faux avancement
            # emprunté au jeu de phases d'une brique qui ne tourne pas.
            return ""
        cible = self._cible_run or {}
        brique = str(cible.get("brique") or "")
        return brique if brique in prg.PHASES else ""

    def _libelle_de_cible(self, genre: str, libelle: str = "") -> str:
        """« Manga · Mon Manga / Vol.2 » — ce que le bandeau nomme en tête.

        ⚠ **`_cible_run` ne vaut que pour un run.** Un import de glossaire, une copie de
        sources ou un diagnostic portent eux aussi `planche=None` et passent donc par le
        bandeau — mais `_cible_run` garde alors le tome du run PRÉCÉDENT, et le bandeau
        annoncerait « Manga · P / Vol.1 » sur un geste qui n'y touche pas. Ces genres-là
        sont nommés par le libellé de leur tâche, qui est ce qu'ils ont de plus juste."""
        if genre == GENRE_ILLUSTRATION:
            return "Illustrations"
        if genre != GENRE_RUN:
            return libelle
        cible = self._cible_run or {}
        projet, tome = cible.get("projet"), cible.get("tome")
        if not projet:
            return libelle
        titres = {"manga": "Manga", "ln": "Light novel"}
        tete = titres.get(str(cible.get("brique") or ""), "Run")
        return f"{tete} · {projet} / {tome}" if tome else f"{tete} · {projet}"

    def _clore_bandeau(self, succes: bool) -> None:
        """L'état terminal du bandeau — `PLAN-32` L32.5.

        ⚠ **Rien qui vole le focus.** Pas de boîte modale à la fin d'un run : l'utilisateur
        peut être en train de taper une réplique dans la retouche, et un dialogue qui surgit
        avale la frappe. Le bilan attend dans le bandeau, avec un bouton vers les
        avertissements — ceux-là mêmes qu'il fallait jusqu'ici retrouver dans un journal."""
        # ⚠ `bilan()` et non `compte()`. Un run finit dans sa phase d'assemblage, qui ne
        # compte rien : lire le compte courant à ce moment-là ferait dire « Terminé » tout
        # court sur un run de 131 planches.
        unites, unite = self.progression.bilan()
        secondes = (time.monotonic() - self._debut_du_run) if self._debut_du_run else None
        # L35.2 — le chemin inverse de `editeur.demande_runs` : un run qui vient d'écrire des
        # planches propose de les retoucher. ⚠ Lu AVANT que `_sur_fin` ne remette
        # `_planches_du_run` à `None` — c'est ce qui permet au bouton de porter le compte
        # exact après un « Enregistrer tout le tome », et de rester muet sur ce compte après
        # un run global, qui peut avoir touché n'importe quelle planche.
        cible = self._cible_run or {}
        retouche = vue_ret.libelle_retouche(str(cible.get("brique") or ""),
                                            self._planches_du_run) if succes else ""
        self.bandeau.terminer(
            av.resume_de_fin(unites=unites, unite=unite, secondes=secondes,
                             avertissements=len(self._avertissements_du_run), succes=succes),
            len(self._avertissements_du_run), retouche=retouche)
        self._debut_du_run = None
        self._genre_du_run = ""
        self._cible_libelle = ""
        self.setWindowTitle(self._titre_base)
        self._armer_extinction()

    # ------------------------------------------------------------------ #
    # L33.2 — l'extinction, la seule action qui touche à la machine
    # ------------------------------------------------------------------ #

    def _armer_extinction(self) -> None:
        """Programme l'extinction si elle a été demandée, et affiche son compte à rebours.

        ⚠ **L'extinction est programmée auprès du SYSTÈME tout de suite**, comme
        `core/cli.finalize_power` le fait : `power.shutdown(délai)` rend la main aussitôt, et
        le compte à rebours du bandeau ne fait qu'AFFICHER ce qui est déjà promis. Un plantage
        de l'interface pendant l'attente ne change donc rien — et la commande d'annulation
        depuis un autre terminal, que le journal recopie, reste le dernier recours.

        ⚠ **Aucune modale.** Le `PLAN-32` L32.5 l'interdit à la fin d'un run, et le
        `PLAN-33` L33.2 exige que le compte à rebours soit « visible et annulable sans
        chercher ». Le bandeau est le seul endroit qui tient les deux."""
        energie, self._energie_du_run = self._energie_du_run, {}
        if not ext.doit_eteindre(arme=bool(energie.get("shutdown")),
                                 arret_demande=bool(getattr(self, "_arret_demande", False))):
            return
        from core import power

        delai = ext.delai_valide(energie.get("shutdown_delay"))
        annulation = power.shutdown(delai)
        self._journaliser("warn", ext.phrase_journal(delai, annulation))
        self._extinction = (delai, time.monotonic())
        self.bandeau.demarrer_extinction(ext.rebours(delai, 0.0))
        minuteur = self._minuteur_extinction = QTimer(self)
        minuteur.setInterval(1000)
        minuteur.timeout.connect(self._battre_extinction)
        minuteur.start()

    def _battre_extinction(self) -> None:
        if self._extinction is None:
            return
        delai, debut = self._extinction
        etat = ext.rebours(delai, time.monotonic() - debut)
        self.bandeau.peindre_extinction(etat)
        if etat.fini:
            self._arreter_minuteur_extinction()

    def _annuler_extinction(self) -> None:
        """« Annuler l'extinction » — le bouton du bandeau, et rien d'autre à chercher."""
        if self._extinction is None:
            return
        from core import power

        note = power.cancel_shutdown()
        self._arreter_minuteur_extinction()
        self.bandeau.effacer_extinction()
        self._journaliser("info", ext.phrase_annulation(note))

    def _arreter_minuteur_extinction(self) -> None:
        if self._minuteur_extinction is not None:
            self._minuteur_extinction.stop()
            self._minuteur_extinction = None
        self._extinction = None

    def _suivre_illustration(self) -> None:
        """Recopie l'état de l'atelier dans le bandeau — `PLAN-32` L32.6, premier cas.

        ⚠ **Indéterminé tant qu'aucune image n'est écrite.** Le coût par image varie d'un
        facteur 14,7 sur la machine de référence (103,7 s à 1 524 s) : une barre qui
        annoncerait « 42 % » après 43 s se tromperait d'un facteur dix un jour sur deux.
        C'est exactement ce que refuse `illustration/progression.fraction()`, et le bandeau
        ne peut pas être moins prudent que le modèle qu'il affiche."""
        atelier = self.atelier
        etat = atelier.etat_progression() if atelier is not None else None
        if not etat or self._genre_du_run != GENRE_ILLUSTRATION:
            return
        if etat.get("phase"):
            self.progression.entrer(str(etat["phase"]))
        faites = int(etat.get("images_faites") or 0)
        total = int(etat.get("total_images") or 0)
        if total:
            self.progression.avancer(faites, total)     # pose le dénominateur
        if faites <= 0:
            # …mais rien n'est encore COMPTABLE : `total = 0` garde la position et tait la
            # fraction, donc ni pourcentage ni temps restant.
            self.progression.avancer(0, 0)
        self._repeindre_bandeau()

    def _montrer_avertissements(self) -> None:
        """Les avertissements du run, sans avoir à les chercher dans le journal.

        C'est le « journal filtré sur les avertissements » de L32.5. Le journal, lui, reste
        entier et à sa place : il est le seul endroit où l'on relit ce qui s'est passé, dans
        l'ordre, avec ce qui l'entourait."""
        from .dialogues import DialogueTexte
        lignes = self._avertissements_du_run
        DialogueTexte(
            "Avertissements du run",
            "\n".join(f"⚠ {ligne}" for ligne in lignes) or "(aucun avertissement)", self,
            sous_titre=f"{len(lignes)} ligne(s) — le journal complet reste sous Ctrl+J."
        ).exec()

    def _sur_debut(self, planche, genre: str, libelle: str) -> None:
        if genre == GENRE_BIBLIOTHEQUE:
            # ⚠ Même parti que la sonde, et pour la même raison : le balayage ne fait que
            # lire des entrées de répertoire. Le faire passer par le chemin d'un run
            # afficherait « lecture de la bibliothèque » dans la barre d'état et grillerait
            # le bandeau de run pour une seconde de `scandir`.
            return
        if genre in (GENRE_SONDE, GENRE_DIAGNOSTIC):
            # ⚠ Une sonde d'installation ne se journalise pas et ne verrouille rien : elle
            # fait trois lectures. La faire passer par le chemin d'un run afficherait « sonde
            # d'installation » dans la barre d'état à chaque démarrage, pour deux secondes.
            # ⚠ Le diagnostic est dans le même cas, et il a en plus SA propre indication : le
            # bouton de la page dit « Diagnostic en cours… ». Le doubler d'un bandeau de run
            # ferait croire qu'un tome est en traitement.
            return
        self._journaliser("stage", libelle)
        editeur = self.editeur
        if editeur is not None:
            editeur.marquer_verrou(planche, libelle, True)
        if genre == GENRE_ILLUSTRATION:
            atelier = self.atelier
            if atelier is not None:
                atelier.marquer_en_cours(True)
        if planche is None:
            self._marquer_run(True)
            # Un nouveau run, un nouveau débit : garder les points du précédent annoncerait
            # un temps tiré d'un travail qui n'a plus rien à voir. `declarer()` remet aussi
            # l'estimateur à zéro — c'est lui qui le porte, maintenant.
            self.progression.declarer(prg.PHASES.get(self._brique_du_run(genre), ()))
            self._cible_libelle = self._libelle_de_cible(genre, libelle)
            self._avertissements_du_run = []
            self._debut_du_run = time.monotonic()
            self._genre_du_run = genre
            self.bandeau.demarrer(self._cible_libelle,
                                  arret_possible=genre in (GENRE_RUN, GENRE_ILLUSTRATION))
            self._repeindre_bandeau()

    def _sur_fin(self, planche, genre: str, succes: bool, message: str) -> None:
        if genre == GENRE_BIBLIOTHEQUE:
            self._recevoir_bibliotheque(succes, message)
            return
        if genre == GENRE_SONDE:
            self._recevoir_sondes(succes, message)
            return
        if genre == GENRE_DIAGNOSTIC:
            self._recevoir_diagnostic(succes, message)
            return
        if genre == GENRE_MAJ:
            self._marquer_run(False)
            self._clore_bandeau(succes)
            self._journaliser("info" if succes else "warn", message)
            self._recevoir_maj(succes, message)
            return
        editeur = self.editeur
        if editeur is not None:
            editeur.marquer_verrou(planche, "", False)
        self._journaliser("info" if succes else "warn", message)
        self._liberer_reporters()
        if genre == GENRE_ILLUSTRATION:
            atelier = self.atelier
            if atelier is not None:
                atelier.apres_tache(succes, message)
            # ⚠ `_sur_debut` a désarmé le choix de tome parce que la tâche porte
            # `planche=None`. Rendre la main ici sans le réarmer laisserait la retouche gelée
            # pour le reste de la session — une destination figée par un travail qui ne la
            # concerne pas.
            self._marquer_run(False)
            self._clore_bandeau(succes)
            self.statusBar().showMessage(message)
            return
        if genre == GENRE_CREATION:
            self._apres_creation(succes)
            return
        if planche is None:
            self._marquer_run(False)
            self._clore_bandeau(succes)
        self._maj_revision()
        # Une tâche a réécrit le disque : les aperçus qu'elle touche ne valent plus rien.
        #
        # ⚠ « Qu'elle touche », pas « tous ». Un run global vidait le cache entier, y compris
        # après un « Enregistrer le projet » qui n'avait relettré que trois planches : les ~21
        # aperçus de la fenêtre partaient avec, soit ~29 s de recomposition (1,37 s pièce) pour
        # rien. Le vidage complet reste le repli quand la liste est inconnue — un run lancé
        # depuis l'onglet « Runs » peut toucher n'importe quelle planche.
        # ⚠ Une édition de ZONE a changé le nombre et l'ordre des bulles sur le disque. Le
        # document que l'éditeur garde en mémoire est donc faux par construction : le laisser
        # en place ferait recoller les anciens textes sur les nouvelles bulles, par position.
        # C'est la cause du décalage des répliques, des bulles marquées « … » et de
        # l'`ErreurDocument` à l'enregistrement.
        # ⚠ Tout ce bloc est gardé par `editeur is not None` : après le lot 31, un run peut
        # tourner alors que la destination Retouche n'a jamais été ouverte — c'est même le cas
        # normal quand on lance depuis « Manga ». Il n'y a alors aucun cache à invalider, et
        # rien à rafraîchir.
        if editeur is None:
            if planche is None:
                self._planches_du_run = None
            return
        if planche is not None and genre == GENRE_EDITION and succes:
            editeur.invalider_document(planche)
        if planche is not None:
            editeur.oublier_apercu(planche)
        elif self._planches_du_run is not None:
            for numero in self._planches_du_run:
                editeur.oublier_apercu(numero)
            editeur.rafraichir_pellicule(self._planches_du_run)
        else:
            editeur.cache.vider()
            editeur.cache_etats.vider()
        if planche is None:
            self._planches_du_run = None
        # La planche à l'écran vient peut-être d'être réécrite : on la relit, en gardant les
        # brouillons de saisie, qui n'appartiennent pas au disque.
        if planche is None or (editeur.planche and planche == editeur.planche.index):
            editeur.rafraichir()

    def _apres_creation(self, succes: bool) -> None:
        """Une tâche hors tome vient de finir : remettre la fenêtre en accord avec le disque.

        ⚠ **Sans revider aucun cache d'aperçu.** Une création de projet, un import de glossaire
        et un diagnostic ne réécrivent AUCUN checkpoint du tome ouvert — passer par le chemin
        de `_sur_fin` d'un run jetterait les ~21 aperçus de la fenêtre (~29 s de recomposition)
        pour rien. C'est la raison du retour anticipé dans `_sur_fin`."""
        self._clore_bandeau(succes)
        if getattr(self, "_glossaire_touche", False):
            self._glossaire_touche = False
            if self.services is not None:
                # Le glossaire vient de changer sur le disque ; celui que les agents tiennent
                # en mémoire décrirait l'état d'avant, et la prochaine bulle traduite s'en
                # servirait sans que rien ne le dise.
                self.services.recharger_glossaire()
                self._journaliser("info", "Glossaire rechargé — les agents repartent du "
                                          "fichier qui vient d'être écrit.")
        creation = getattr(self, "_creation_en_attente", None)
        if creation is None:
            # ⚠ On rafraîchit quand même l'accueil et la bibliothèque. Le tome de
            # démonstration (L36.4) fait apparaître un projet sous `sources/` sans passer par
            # `_creation_en_attente`, qui sert à OUVRIR le tome importé — or on ne veut pas
            # ouvrir la démonstration, seulement cesser d'afficher « aucun projet ».
            self._maj_etat_vide()
            if "oeuvres" in self._panneaux:
                self._balayer_bibliotheque()
            return
        self._creation_en_attente = None
        self._maj_etat_vide()
        # ⚠ La bibliothèque a vieilli : un tome vient d'apparaître sous `sources/`. Elle ne
        # se rafraîchit pas toute seule (aucun cache à invalider, aucune surveillance de
        # dossier), et la laisser afficher l'état d'avant serait précisément le défaut
        # qu'elle est faite pour corriger.
        if "oeuvres" in self._panneaux:
            self._balayer_bibliotheque()
        if not succes:
            return
        projet, tome = creation
        # Un tome fraîchement créé n'a aucun checkpoint : l'éditeur n'aurait rien à montrer.
        # Le geste attendu est un run, et la destination « Manga » le porte — on y va, et on
        # y porte la cible, plutôt que de nommer un onglet dans une phrase.
        self._journaliser(
            "stage", f"« {projet} / {tome} » est créé. « Manga » → « Lancer » pour le "
                     f"traiter — compte plusieurs heures la première fois (détection).")
        lanceur = self.aller_a("manga")
        if lanceur is not None:
            lanceur.viser(projet, tome)

    def _liberer_reporters(self) -> None:
        """Referme les `perf.log` dès que plus aucune tâche ne peut écrire dedans.

        ⚠ La condition porte sur la file **entière**, pas sur la tâche qui vient de finir :
        `_sur_fin` ne sait pas quel reporter appartenait à quelle tâche, et plusieurs peuvent
        être en vol (un relettrage par planche s'empile). Fermer trop tôt couperait le journal
        d'un run encore vivant — on attend donc que la voie d'écriture soit au repos, ce qui
        arrive de toute façon à chaque accalmie."""
        if self.fil.occupe() or self.fil.en_attente():
            return
        for reporter in self._reporters_ouverts:
            fermer = getattr(reporter, "close", None)
            if callable(fermer):
                fermer()
        self._reporters_ouverts.clear()

    def _sur_file(self, restantes: int) -> None:
        self.etiquette_file.setText(f"file : {restantes}" if restantes else "")

    def _sur_apercu_pret(self, planche: int) -> None:
        editeur = self.editeur
        if editeur is not None:
            editeur.apercu_pret(planche)
        # L35.3 point 3 — le chiffre de mémoire suit le cache, et rien d'autre ne le
        # rafraîchit : pas de minuteur, donc pas de clignotement sur un panneau au repos.
        panneau = self._panneaux.get("retouche")
        if panneau is not None:
            panneau.rafraichir_cache()

    def _sur_prechargement(self, pretes: int, total: int) -> None:
        """Avancement du préchargement — discret, et jamais au détriment d'un run.

        Un run pose sa propre progression ; l'écraser par celle du préchargement ferait
        perdre de vue ce qui compte vraiment."""
        if self.fil.occupe():
            return
        self.etiquette_prechargement.setText(
            f"aperçus {pretes}/{total}" if pretes < total else "")

    def _marquer_modifie(self, modifie: bool) -> None:
        """Titre marqué `[*]` — la convention Qt pour « document non enregistré ».

        Une modification retenue en mémoire et rien à l'écran pour le dire serait pire que
        l'écriture immédiate qu'on vient d'abandonner."""
        self.setWindowModified(modifie)
        panneau = self._panneaux.get("retouche")
        if panneau is None:
            return
        perimees = self._planches_perimees()
        panneau.bouton_projet.setEnabled(modifie or bool(perimees))
        # L18.5 — le compteur. « Enregistrer tout le tome » ne disait pas COMBIEN, et un bouton
        # grisé ne disait pas pourquoi. Le nombre était déjà calculé (`planches_modifiees`) et
        # n'était affiché nulle part.
        attente = panneau.editeur.planches_modifiees() if self.tome is not None else []
        total = len(set(attente) | set(perimees))
        panneau.bouton_projet.setText(
            f"Enregistrer tout le tome ({total} planche{'s' if total > 1 else ''})"
            if total else "Enregistrer tout le tome")
        panneau.etiquette_attente.setText(
            f"⚠ {len(attente)} planche(s) non écrite(s) : {_liste(attente)}"
            if attente else "")

    # ------------------------------------------------------------------ #
    # Journal
    # ------------------------------------------------------------------ #

    def _journaliser(self, niveau: str, message: str) -> None:
        forme = QTextCharFormat()
        forme.setForeground(theme.qcolor(ROLES_JOURNAL.get(niveau, "information")))
        curseur = self.journal.textCursor()
        curseur.movePosition(QTextCursor.End)
        curseur.insertText(PREFIXES_JOURNAL.get(niveau, "  ") + message + "\n", forme)
        self.journal.setTextCursor(curseur)
        # L'état des trois phases vient du MODÈLE PUR (`illustration/progression.py`), pas
        # d'une lecture du texte du journal : une progression devinée dans une chaîne cesse
        # d'avancer le jour où un libellé change, et personne ne s'en aperçoit.
        atelier = getattr(self, "atelier", None)
        if atelier is not None:
            atelier.rafraichir_progression()
            self._suivre_illustration()
        if niveau in ("stage", "warn"):
            self.statusBar().showMessage(message, 8000)
        if niveau == "warn":
            # Retenus pour le bilan de fin de run (L32.5). Plafonné : un run pathologique
            # peut en produire des milliers, et un bilan qu'on ne peut pas lire n'est pas un
            # bilan. Le journal, lui, les garde tous — c'est son rôle.
            if len(self._avertissements_du_run) < 500:
                self._avertissements_du_run.append(message)
            self.deplier_journal()

    def deplier_journal(self) -> None:
        """Ouvre le journal s'il est replié — un avertissement qui n'est pas lu ne sert à rien."""
        tailles = self.separateur.sizes()
        if len(tailles) > 1 and tailles[1] < 40:
            hauteur = sum(tailles)
            self.separateur.setSizes([int(hauteur * 0.75), int(hauteur * 0.25)])

    def _avancer(self, courant: int, total: int) -> None:
        """Le canal chiffré — `progres`, `chapter`, et le repli par regex sur `stage`.

        ⚠ **Une seule ligne de logique, et elle est ailleurs.** `core.progression.appliquer`
        est la table de référence, et ce slot n'en est que le reflet Qt. C'est ce qui permet
        aux tests de rejouer les traces réelles de `tests/corpus/progression/` sans monter
        une fenêtre — et c'est ce qui garantit que la barre de l'écran et la fraction
        assertée par le test sont la même chose."""
        self.progression.avancer(courant, total)
        self._repeindre_bandeau()

    def _contexte(self, phase: str, objet: str, detail: str) -> None:
        """Les deux canaux du lot 32 : la PHASE du run et l'OBJET en cours.

        Une chaîne vide veut dire « inchangé ». Les trois arrivent par un seul signal parce
        qu'un ordre de délivrance ne doit jamais décider de ce qui s'affiche."""
        if phase:
            self.progression.entrer(phase)
        if objet:
            self.progression.nommer(objet)
        if detail:
            self.progression.detailler(detail)
        self._repeindre_bandeau()

    def _repeindre_bandeau(self) -> None:
        """Le bandeau, puis le titre. Aucune décision : `gui/avancement.py` les a prises.

        ⚠ **Muet tant qu'aucune tâche GLOBALE ne tourne.** Un relettrage de planche unique
        émet lui aussi `progres`, et il n'a pas de bandeau : il porte `planche=7`, donc
        l'éditeur grise cette planche-là et annonce ce qu'elle subit — un retour local pour
        un travail local. Repeindre ici mettrait « 1/1 » dans le titre de la fenêtre pour
        une bulle relue, et ferait apparaître un bandeau qui clignoterait à chaque geste."""
        if not self._genre_du_run:
            return
        etat = self.progression.etat()
        self.bandeau.peindre(etat, self._cible_libelle)
        self.setWindowTitle(av.titre_de_fenetre(self._titre_base, etat, self._cible_libelle))
        # L35.5 — le même état descend dans le bandeau de l'éditeur verrouillé. ⚠ ICI et non
        # dans `_sur_debut` : à l'instant où le run démarre, `declarer()` n'a pas encore posé
        # ses phases, et le motif porterait celles du run PRÉCÉDENT. Repeindre au même
        # battement que le bandeau garantit qu'un seul état alimente les deux affichages —
        # deux sources pour un même chiffre finissent toujours par diverger.
        editeur = self.editeur
        if editeur is not None:
            editeur.poser_motif_de_verrou(
                vue_ret.motif_de_verrou(etat, self._cible_libelle),
                arret_possible=self._genre_du_run in (GENRE_RUN, GENRE_ILLUSTRATION))

    # ================================================================== #
    # Les actions de menu — une méthode `action_<identifiant>` par entrée
    # ================================================================== #
    #
    # ⚠ Le nom n'est pas décoratif : `_fabriquer_action` le résout par `getattr`, et
    # `tests/test_gui_actions.py` vérifie que chaque identifiant du catalogue en a une. Une
    # entrée de menu sans méthode ferait tomber la construction de la fenêtre au démarrage —
    # ce qui est exactement le bon moment pour tomber.

    def _ouvrir_dans_le_systeme(self, chemin: Path) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(chemin).resolve())))

    # -- Fichier -------------------------------------------------------- #

    def action_nouveau_projet(self, chemins=()) -> None:
        """L18.1 — la boîte, puis la copie **dans le fil de travail**.

        ⚠ Jamais sur le fil d'affichage. Une archive de webtoon pèse couramment plusieurs
        centaines de mégaoctets ; `shutil.copy2` la recopie à la vitesse du disque, et la
        fenêtre serait gelée pour toute cette durée — un gel qu'aucune barre de progression ne
        peut rattraper si elle ne peut pas se redessiner."""
        from .dialogues import DialogueNouveauProjet
        boite = DialogueNouveauProjet(self.config, chemins, parent=self)
        if boite.exec() != boite.DialogCode.Accepted:
            return
        self._creer_projet(boite.description())

    def action_depot_guide(self, chemins=()) -> None:
        """L34.3 — le parcours complet d'un lâcher, jusqu'au compte rendu.

        ⚠ Elle n'est PAS une entrée de menu : elle n'a de sens qu'avec des chemins déjà
        désignés, c'est-à-dire depuis `dropEvent`. Le geste sans chemins reste « Nouveau
        projet… », qui commence par demander les sources."""
        from .dialogues import DialogueDepotGuide

        if not chemins:
            self.action_nouveau_projet()
            return
        boite = DialogueDepotGuide(self.config, chemins, parent=self)
        if boite.exec() != boite.DialogCode.Accepted:
            return
        self._creer_projet(boite.description())

    def _creer_projet(self, description: dict) -> None:
        # ⚠ Créer un projet — à la main ou par glisser-déposer — n'écrit que sous `sources/`
        # d'un tome NEUF, et `_apres_creation` prend soin de ne pas passer par le chemin de
        # `_sur_fin` pour ne pas jeter les aperçus de la retouche (lot 18). Rien n'est perdu,
        # donc aucune boîte ; l'appel matérialise le sixième chemin de l'étape 0.2.
        if not self.peut_quitter("creation"):
            return
        # ⚠ `creation` (racine) et non `manga.creation_projet` depuis le lot 40 :
        # c'est l'agrégateur des trois dispositions, light novel compris. Même
        # précédent que `bibliotheque.py` — l'agrégateur vit AU-DESSUS des briques.
        import creation as crea
        signaux = self.signaux
        projet, tome = description["projet"], description["tome"]
        # ⚠ Absent des descriptions de `DialogueNouveauProjet` : le défaut est donc la COPIE,
        # et le déplacement n'existe que quand la boîte qui l'a demandé le porte.
        deplacer = bool(description.get("deplacer"))

        def _travail():
            def _progres(fait, total, nom):
                signaux.progression.emit(fait, total)
                if fait == 1 or fait == total or fait % 10 == 0:
                    signaux.ligne.emit("verbose",
                                       f"{'déplacement' if deplacer else 'copie'} "
                                       f"{fait}/{total} — {nom}")
            creation = crea.creer(self.config, projet, tome, description["chemins"],
                                  quelle=description.get("quelle")
                                  or description.get("format") or crea.MANGA,
                                  langue=description["langue"],
                                  progres=_progres, deplacer=deplacer)
            verbe = "déplacé(s)" if deplacer else "copié(s)"
            return (f"{projet} / {tome} — {len(creation.fichiers)} fichier(s) {verbe} "
                    f"({crea.poids_lisible(creation.octets)}) dans {creation.dossier}")

        self._creation_en_attente = (projet, tome)
        self.fil.soumettre(Tache(genre=GENRE_CREATION, fonction=_travail, planche=None,
                                 libelle=f"Création de « {projet} / {tome} »"))

    def action_ouvrir_sources(self) -> None:
        racine = self._racine_sources()
        if not racine.exists():
            reponse = QMessageBox.question(
                self, "Créer le dossier de sources ?",
                f"{racine} n'existe pas encore.\n\nLe créer maintenant ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reponse != QMessageBox.Yes:
                return
            try:
                racine.mkdir(parents=True, exist_ok=True)
            except OSError as err:
                QMessageBox.warning(self, "Impossible", str(err))
                return
        self._ouvrir_dans_le_systeme(racine)

    def action_enregistrer_planche(self) -> None:
        editeur = self.editeur
        if editeur is not None:
            editeur.enregistrer_document()

    def action_enregistrer_tome(self) -> None:
        self._enregistrer_projet()

    def action_ouvrir_build(self) -> None:
        if self.tome is None:
            return
        dossier = self.tome.build_dir
        if not dossier.exists():
            QMessageBox.information(self, "Rien à ouvrir",
                                    f"{dossier} n'existe pas encore — lance un run d'abord.")
            return
        self._ouvrir_dans_le_systeme(dossier)

    def action_ouvrir_config(self) -> None:
        self._ouvrir_dans_le_systeme(Path(self.chemin_config))

    # -- Atelier d'illustration (lot 27) --------------------------------- #

    def _ouvrir_bible(self, projet: str) -> None:
        """« Ouvrir la bible » — critère L27.1 point 5.

        ⚠ **100 % des refus de génération se règlent là.** Un personnage grisé dans l'atelier
        l'est parce que sa fiche de bible n'a ni attribut cité ni image candidate ; le bouton
        mène donc au fichier, pas à un message. Une bible absente n'est pas une erreur : c'est
        une bible qui n'a pas encore été commencée, et on le dit avec la commande qui la
        commence."""
        if not projet:
            return
        chemin = Path(self.config["chemins"]["sources"]) / projet / "bible.yaml"
        if not chemin.is_file():
            QMessageBox.information(
                self, "Bible visuelle",
                f"« {projet} » n'a pas encore de bible visuelle ({chemin}).\n\n"
                f"Sans elle, un prompt ne viendrait pas de l'œuvre — il viendrait d'un "
                f"modèle. Pour la commencer :\n\n"
                f"    python tools/bible.py \"{projet}\" --proposer\n"
                f"    python tools/bible.py \"{projet}\" --revue")
            return
        self._ouvrir_dans_le_systeme(chemin)

    def _ouvrir_illustrations(self, projet: str) -> None:
        """Le dossier des candidates. Les images RETENUES, elles, vivent sous `sources/`."""
        if not projet:
            return
        dossier = Path(self.config["chemins"]["build"]) / projet / "illustrations"
        if not dossier.exists():
            QMessageBox.information(
                self, "Rien à ouvrir",
                f"{dossier} n'existe pas encore — aucune image n'a été produite pour "
                f"« {projet} ».")
            return
        self._ouvrir_dans_le_systeme(dossier)

    def action_quitter(self) -> None:
        self.close()

    # -- Édition -------------------------------------------------------- #

    def _editeur_visible(self):
        """L'éditeur, **et la destination Retouche à l'écran**. `None` s'il n'y en a pas.

        ⚠ Aller à la destination fait partie de l'action : `Ctrl+F` depuis « Manga » doit
        amener le curseur dans le champ de recherche, pas le poser dans un panneau caché où la
        frappe suivante irait nulle part. C'est ce que faisait `setCurrentWidget` sur les
        onglets ; le geste est le même, la destination a changé de nom."""
        if self.editeur is None and self.tome is None:
            # Rien à chercher, rien à annuler : ces actions sont `exige_tome` et donc grisées.
            # Construire la retouche ici ouvrirait un panneau vide sur un raccourci.
            return None
        self.aller_a("retouche")
        return self.editeur

    def action_annuler(self) -> None:
        editeur = self.editeur
        if editeur is not None:
            editeur.annuler()

    def action_refaire(self) -> None:
        editeur = self.editeur
        if editeur is not None:
            editeur.refaire()

    def action_rechercher(self) -> None:
        editeur = self._editeur_visible()
        if editeur is None:
            return
        editeur.champ_recherche.setFocus()
        editeur.champ_recherche.selectAll()

    def action_remplacer(self) -> None:
        editeur = self._editeur_visible()
        if editeur is None:
            return
        editeur.champ_remplacement.setFocus()
        editeur.champ_remplacement.selectAll()

    # -- Affichage ------------------------------------------------------ #

    def action_zoom_plus(self) -> None:
        if self.editeur is not None:
            self.editeur.zoomer(1.25)

    def action_zoom_moins(self) -> None:
        if self.editeur is not None:
            self.editeur.zoomer(1 / 1.25)

    def action_ajuster(self) -> None:
        if self.editeur is not None:
            self.editeur.ajuster()

    def action_garder_cadrage(self, actif: bool) -> None:
        if self.editeur is not None:
            self.editeur.bouton_garder_zoom.setChecked(bool(actif))

    def action_comparer_rendu(self, actif: bool) -> None:
        editeur = self.editeur
        if editeur is None:
            return
        editeur.bouton_finale.setChecked(bool(actif))
        editeur.basculer_fond()

    # -- Aller à --------------------------------------------------------- #

    def action_aller(self, identifiant: str) -> None:
        """Les sept entrées du menu « Aller à », et les sept raccourcis `Ctrl+…`.

        Une seule méthode pour sept entrées, comme les six filtres et les trois thèmes : la
        table nomme la destination, la fenêtre la sert."""
        self.aller_a(identifiant)

    def action_destination_suivante(self) -> None:
        """`Ctrl+Tab`. Il faisait « onglet suivant » ; il fait la même promesse sur sept
        destinations."""
        self.aller_a(dst.suivante(self.destination()))

    def action_filtre(self, nom: str, actif: bool = True) -> None:
        """Un filtre de pellicule, depuis le sous-menu « Affichage ».

        ⚠ Sans éditeur construit, il n'y a pas de pellicule à filtrer : ces entrées sont
        `exige_tome`, donc grisées, et ce retour anticipé n'est qu'une ceinture.

        Exclusif : décocher celui qui est actif revient à « toutes », plutôt que de laisser la
        pellicule sans filtre déclaré et le menu sans coche. Un menu qui ne dit pas lequel est
        actif ne fait que rappeler que des filtres existent."""
        if self.editeur is None:
            return
        if not actif:
            if self.editeur.choix_filtre.currentText() == nom:
                self.editeur.choix_filtre.setCurrentIndex(0)
            return
        self.editeur.choix_filtre.setCurrentText(nom)

    def _refleter_filtre(self, nom: str) -> None:
        """Met les coches du sous-menu en accord avec la liste déroulante de l'éditeur.

        La liste déroulante reste le maître : elle est sous les yeux, à côté de la pellicule
        qu'elle filtre. Le menu la reflète — c'est un index découvrable, pas un second
        contrôle qui pourrait diverger."""
        for entree in act.actions():
            if entree.methode != "filtre":
                continue
            action = self.actions_menu[entree.identifiant]
            voulu = entree.donnee == nom
            if action.isChecked() != voulu:
                action.blockSignals(True)
                action.setChecked(voulu)
                action.blockSignals(False)

    def action_journal(self) -> None:
        self.deplier_journal()

    def _aller_aux_runs(self) -> None:
        """Ouvre l'onglet « Runs » et y porte le tome choisi — L19.7.

        ⚠ Le tome est reporté dans le lanceur, qui a ses PROPRES listes depuis L18.8.2. Sans
        ça, le bouton amènerait sur un panneau réglé sur un autre tome, et le clic suivant
        lancerait un run sur ce qu'on ne regardait pas."""
        panneau = self._panneaux.get("retouche")
        projet, tome = panneau.cible() if panneau is not None else ("", "")
        lanceur = self.aller_a("manga")
        if lanceur is None:
            return
        if projet and tome:
            lanceur.viser(projet, tome)
        lanceur.bouton_lancer.setFocus()

    # -- Le thème -------------------------------------------------------- #

    def action_theme(self, mode: str, actif: bool = True) -> None:
        """Bascule de thème, depuis le sous-menu « Affichage → Thème ».

        Exclusif, comme les filtres : décocher le mode actif le remet, plutôt que de laisser
        l'application dans un thème que le menu ne déclare plus."""
        if not actif:
            self._refleter_theme()
            return
        if mode == self.reglages.get("theme"):
            self._refleter_theme()
            return
        self.reglages["theme"] = mode
        self._appliquer_theme(mode)

    def _appliquer_theme(self, mode: str) -> None:
        """Repose le style, la palette, la feuille — et **ce que la feuille ne couvre pas**.

        ⚠ Trois choses échappent à `QApplication.setStyleSheet`, et les oublier laisserait
        l'interface à moitié basculée :

        1. **Les icônes.** Elles sont rendues en pixmap avec la couleur du token AU MOMENT du
           rendu. Le cache est donc vidé et les cinq boutons de mode redemandent la leur.
        2. **Le canevas.** Fond de scène, cadres de zone, poignées, numéros sont des
           `QGraphicsItem`, pas des widgets : aucune règle QSS ne les atteint. Ils ne changent
           pas de couleur d'un thème à l'autre (le canevas reste sombre), mais ils sont
           reconstruits pour reprendre la couleur du jeu courant plutôt que celle capturée à
           leur construction.
        3. **Le journal.** Chaque ligne porte un `QTextCharFormat` figé à l'insertion. Un
           journal de trois cents lignes garderait donc les couleurs du thème précédent."""
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        avant = theme.jeu().mode
        apres = theme.appliquer(app, mode).mode
        # ⚠ La reprise des pixels déjà peints ne sert QUE si la palette a changé — et elle
        # coûte : elle repasse sur toute la pellicule, jusqu'à 150 vignettes. À la
        # construction d'une fenêtre, ou en passant de « Clair » à « Suivre le système » sur
        # une machine réglée en clair, il n'y a rien à reprendre.
        if apres != avant:
            ico.oublier()
            # ⚠ Les icônes sont des pixmaps : aucune règle QSS ne les atteint. Tout ce qui en
            # porte doit les redemander — la nav latérale comprise, sans quoi elle garderait
            # les glyphes du thème précédent jusqu'au prochain lancement.
            self.navigation.rafraichir_theme()
            accueil = self._panneaux.get(dst.ACCUEIL)
            if accueil is not None:
                accueil.rafraichir_theme()
            if self.editeur is not None:
                self.editeur.rafraichir_theme()
            self._repeindre_journal()
        self._refleter_theme()

    def _refleter_theme(self) -> None:
        """Met les coches du sous-menu en accord avec le mode choisi."""
        courant = self.reglages.get("theme") or theme.AUTO
        for entree in act.actions():
            if entree.methode != "theme":
                continue
            action = self.actions_menu.get(entree.identifiant)
            if action is None:
                continue
            voulu = entree.donnee == courant
            if action.isChecked() != voulu:
                action.blockSignals(True)
                action.setChecked(voulu)
                action.blockSignals(False)

    def _repeindre_journal(self) -> None:
        """Redonne à chaque ligne DÉJÀ écrite la couleur de son niveau dans le thème courant.

        ⚠ Le niveau est retrouvé par le PRÉFIXE de la ligne (`⚠ `, `⏱ `, `· `), pas par un
        historique gardé en mémoire. Garder une copie des cinq mille lignes que le journal
        retient déjà serait payer deux fois pour la même information — et une copie qui
        dériverait du widget donnerait un journal repeint aux mauvaises couleurs, ce qui est
        pire que pas repeint du tout."""
        par_prefixe = {p: n for n, p in PREFIXES_JOURNAL.items() if p.strip()}
        document = self.journal.document()
        curseur = QTextCursor(document)
        bloc = document.begin()
        while bloc.isValid():
            texte = bloc.text()
            niveau = par_prefixe.get(texte[:2], "info")
            forme = QTextCharFormat()
            forme.setForeground(theme.qcolor(ROLES_JOURNAL[niveau]))
            curseur.setPosition(bloc.position())
            curseur.setPosition(bloc.position() + bloc.length() - 1,
                                QTextCursor.KeepAnchor)
            curseur.setCharFormat(forme)
            bloc = bloc.next()

    def action_reinitialiser_disposition(self) -> None:
        """La sortie de secours d'un état persisté corrompu.

        ⚠ Elle efface le FICHIER, pas seulement l'état en mémoire : un état corrompu qui
        resterait sur le disque reviendrait au prochain lancement, et la sortie de secours
        aurait duré une session."""
        reponse = QMessageBox.question(
            self, "Réinitialiser la disposition",
            f"Rendre à la fenêtre sa taille, ses colonnes et son filtre d'origine, et "
            f"supprimer {reg.chemin()} ?" + SAUT_LIGNE
            + "Aucune planche, aucun réglage de run et aucun fichier de projet n'est touché.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse != QMessageBox.Yes:
            return
        reg.effacer()
        self.reglages = reg.defauts()
        fen = self.reglages["fenetre"]
        self.showNormal()
        self.resize(int(fen["largeur"]), int(fen["hauteur"]))
        self.separateur.setSizes(list(self.reglages["journal"]))
        if self.editeur is not None:
            self.editeur.appliquer_reglages(self.reglages)
        self.aller_a(dst.ACCUEIL)
        self._appliquer_theme(self.reglages.get("theme") or theme.AUTO)
        self._journaliser("info", "Disposition réinitialisée.")

    # -- Projet --------------------------------------------------------- #

    def action_recharger_glossaire(self) -> None:
        self._recharger_glossaire()

    def action_importer_build(self, projet: str = "", tome: str = "") -> None:
        """L40.2 — réintégrer le travail d'un relecteur. **L'écriture part dans le fil.**

        ⚠ Trois refus AVANT toute écriture (`import_build.planifier`) : un autre tome, un
        `regions.json` d'une autre version de format, un run en cours. Le second est celui qui
        compte — l'ordre des zones est le pivot auquel `ocr.json` et `traduction.json`
        s'alignent par position, et un cache d'une autre version ferait atterrir les
        traductions dans les mauvaises bulles, silencieusement.

        ⚠ Le fil de travail, pas le fil d'affichage : avec les planches rendues, l'import
        porte sur des gigaoctets."""
        import import_build as imp

        from .dialogues import DialogueImportBuild
        # ⚠ Deux appelants, deux façons de désigner le tome — lot 41. Le menu « Projet »
        # n'en donne aucun et vise le tome OUVERT ; la page Œuvres donne celui qui est
        # sélectionné, sans rien ouvrir. Exiger un tome ouvert dans les deux cas rendait le
        # geste inatteignable depuis la page qui sert justement à choisir un tome.
        if not (projet and tome):
            if self.tome is None:
                QMessageBox.information(
                    self, "Importer un tome corrigé",
                    "Choisis d'abord le tome dans lequel réintégrer les corrections — ouvre-le, "
                    "ou sélectionne-le dans « Œuvres » et clique « Importer un tome corrigé… ». "
                    "L'import vérifie que le paquet est bien celui de CE tome avant d'écrire "
                    "quoi que ce soit.")
                return
            projet, tome = self.tome.projet, self.tome.tome
        cible = build_dir_de(self.config, "manga", projet, tome)
        boite = DialogueImportBuild(cible, parent=self)
        if boite.exec() != boite.DialogCode.Accepted:
            return
        plan = boite.plan()
        if plan is None or not plan.executable:
            return
        if self.fil.occupe() or self.fil.en_attente():
            QMessageBox.warning(self, "Importer un tome corrigé",
                                "Un run est en cours — attends la fin, ou arrête-le.")
            return

        signaux = self.signaux

        def _travail():
            def _progres(fait, total, nom):
                signaux.progression.emit(fait, total)
                signaux.ligne.emit("verbose", f"import {fait}/{total} — {nom}")

            ecrites, sauvegarde = imp.appliquer(plan, progres=_progres)
            ou = f" — l'ancienne version est dans {sauvegarde.name}" if sauvegarde else ""
            return f"{ecrites} planche(s) réintégrée(s){ou}."

        self.fil.soumettre(Tache(genre=GENRE_CREATION, fonction=_travail, planche=None,
                                 libelle="Import d'un tome corrigé"))

    def action_importer_glossaire(self, chemins=()) -> None:
        """L18.3 — l'import de glossaire, avec la sauvegarde que la console n'écrivait pas.

        ⚠ `sources/<Projet>/glossaire.yaml` est **partagé avec le light novel**. Une fusion
        malheureuse casse la cohérence de noms entre un roman et son manga, et il n'existait
        aucun repli : `import_into_project` réécrivait le fichier sans filet. Une sauvegarde
        `.avant-import.bak` part maintenant avant toute réécriture — le patron existait déjà
        deux fois dans `core/` (`.avant-multicibles.bak`, `.avant-reintegration.bak`)."""
        projet = self._projet_courant("Importer un glossaire")
        if not projet:
            return
        fichiers = [str(c) for c in chemins]
        if not fichiers:
            fichiers, _ = QFileDialog.getOpenFileNames(
                self, "Glossaire à importer", str(self._racine_sources()),
                "Glossaires (*.yaml *.yml *.docx *.txt *.md *.csv);;Tous les fichiers (*)")
        if not fichiers:
            return
        yamls = [f for f in fichiers if dep.est_glossaire_yaml(f)]
        rediges = [f for f in fichiers if not dep.est_glossaire_yaml(f)]
        cible = self._racine_sources() / projet / (
            (self.config.get("chemins") or {}).get("glossaire_fichier") or "glossaire.yaml")
        reponse = QMessageBox.question(
            self, "Importer un glossaire",
            f"Fusionner {len(fichiers)} fichier(s) dans le glossaire de « {projet} » ?"
            + SAUT_LIGNE + f"Destination : {cible}" + SAUT_LIGNE
            + "⚠ Ce glossaire est PARTAGÉ avec la brique light novel : ce qui est importé ici "
              "s'appliquera aussi au roman du même projet. Une sauvegarde est écrite avant "
              "toute modification.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse != QMessageBox.Yes:
            return

        config = self.config

        def _travail():
            from core import glossary_import as gi
            lignes = []
            if yamls:
                _, total, _ = gi.reintegrer_dans_projet(projet, yamls, config)
                lignes.append(f"{len(yamls)} glossaire(s) YAML réintégré(s) — "
                              f"{total['ajouts']} ajout(s), {total['fusions']} fusion(s), "
                              f"{total['conflits']} conflit(s), {total['entrees']} entrée(s) "
                              f"au total")
            for fichier in rediges:
                _, ajouts, lues = gi.import_into_project(projet, fichier, config)
                total_lues = sum(len(v) for v in lues.values())
                lignes.append(f"{Path(fichier).name} — {total_lues} lue(s), "
                              f"{ajouts['ajouts']} ajout(s), {ajouts['fusions']} fusion(s), "
                              f"{ajouts['conflits']} conflit(s)")
            return " · ".join(lignes) or "Rien à importer."

        self._glossaire_touche = True
        self.fil.soumettre(Tache(genre=GENRE_CREATION, fonction=_travail, planche=None,
                                 libelle=f"Import de glossaire — {projet}"))

    def action_optimiser_glossaire(self) -> None:
        """Le dédoublonnage, **avec la confirmation chiffrée** que la console ne donnait pas.

        `run_optimize` fait des appels LLM sur tout le glossaire d'une œuvre : sur un glossaire
        de plusieurs centaines d'entrées, c'est plusieurs minutes. Annoncer le nombre d'entrées
        avant de partir est le minimum — c'est le patron du récapitulatif de « Enregistrer tout
        le tome », appliqué ici."""
        projet = self._projet_courant("Optimiser le glossaire")
        if not projet:
            return
        from core import glossary
        chemin = self._racine_sources() / projet / (
            (self.config.get("chemins") or {}).get("glossaire_fichier") or "glossaire.yaml")
        if not chemin.exists():
            QMessageBox.information(self, "Aucun glossaire",
                                    f"{chemin} n'existe pas encore — importe-en un d'abord.")
            return
        try:
            entrees = glossary.total(glossary.load(chemin) or glossary.empty())
        except Exception as err:                       # noqa: BLE001 — YAML abîmé
            QMessageBox.warning(self, "Glossaire illisible", str(err))
            return
        reponse = QMessageBox.question(
            self, "Optimiser le glossaire",
            f"Dédoublonner les {entrees} entrée(s) du glossaire de « {projet} » ?"
            + SAUT_LIGNE
            + "C'est un travail LLM sur tout le glossaire — compte plusieurs minutes, et "
              "davantage au-delà de quelques centaines d'entrées. Le fichier sera réécrit.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reponse != QMessageBox.Yes:
            return

        config = copy.deepcopy(self.config)
        config.setdefault("options", {}).setdefault("dry_run", False)
        reporter = ReporterQt(self.signaux)

        def _travail():
            from pipeline.orchestrator import run_optimize
            resultat = run_optimize(projet, config, reporter=reporter) or {}
            return (f"Glossaire de « {projet} » optimisé — "
                    + ", ".join(f"{k} : {v}" for k, v in resultat.items())
                    if resultat else f"Glossaire de « {projet} » optimisé.")

        self._glossaire_touche = True
        self.fil.soumettre(Tache(genre=GENRE_CREATION, fonction=_travail, planche=None,
                                 libelle=f"Optimisation du glossaire — {projet}"))

    def action_assembler(self) -> None:
        """L18.8.4 — la confirmation manquante. Réassembler réécrit le CBZ et le PDF."""
        if self.tome is None:
            return
        reponse = QMessageBox.question(
            self, "Assembler CBZ/PDF",
            f"Réassembler les sorties de « {self.tome.projet} / {self.tome.tome} » depuis "
            f"pages_out/ ?" + SAUT_LIGNE
            + "Le CBZ et le PDF existants seront réécrits. Rien n'est retraduit ni relettré.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reponse == QMessageBox.Yes:
            self._assembler()

    def action_preferences(self) -> None:
        from .dialogues import DialoguePreferences
        boite = DialoguePreferences(self.reglages, parent=self)
        if boite.exec() != boite.DialogCode.Accepted:
            return
        self.reglages.update(boite.valeurs())
        editeur = self.editeur
        if editeur is not None:
            editeur.cache.plafond = max(1, int(self.reglages["plafond_mo"])) * 1024 * 1024
            editeur.fenetre_prechargement = max(0, int(self.reglages["fenetre_apercu"]))
        change = self._appliquer_serveur_llm()
        reg.ecrire(self._collecter_reglages())
        self._journaliser("info", f"Préférences enregistrées dans {reg.chemin()}.")
        if change is not None:
            self._journaliser("info", f"Serveur LLM : {change[0] or '(défaut)'} → {change[1]}. "
                                      f"⚠ config.yaml n'est pas touché.")

    def _appliquer_serveur_llm(self):
        """Reporte le serveur réglé dans les préférences sur la configuration **en mémoire**.

        Rend `(avant, après)` si l'adresse a changé, `None` sinon.

        ⚠ **`config.yaml` n'est jamais écrit** (interdit 5) : le fichier reste la référence
        partagée, et ce qui est réglé ici vaut pour CETTE installation — même doctrine que le
        plafond du cache d'aperçus, écrite dans `DialoguePreferences`.

        ⚠ Appelée aussi au DÉMARRAGE : un réglage qui ne s'appliquerait qu'après un passage par
        la boîte serait un réglage qui ne survit pas à la fermeture de la fenêtre."""
        from core import modeles as mdl
        return mdl.outrepasser_endpoint(self.config, None, self.reglages.get("serveur_llm"))

    # -- Aide ----------------------------------------------------------- #

    def action_raccourcis(self) -> None:
        from .dialogues import DialogueRaccourcis
        DialogueRaccourcis(self).exec()

    def action_legende_symboles(self) -> None:
        from .dialogues import DialogueLegende
        DialogueLegende(self).exec()

    def action_diagnostic(self) -> None:
        """Va à la page Diagnostic, et lance l'inspection si elle n'a rien encore.

        ## ⚠ MISE À JOUR lot 36 (2026-09-06) — ce n'était pas une page, c'en est une

        Le lot 18 écrivait ici : « les deux doctors impriment sur `stdout` : les réécrire pour
        rendre du texte serait toucher à `pipeline/` et `manga/` hors du périmètre du lot. On
        les capture donc. » C'était vrai, et c'est le `PLAN-36` qui a fait ce travail-là :
        `core/diagnostic.py` rend des `Verdict` structurés, les deux doctors les produisent,
        et leur sortie console n'a pas bougé d'un octet.

        Ce que la capture ne pouvait pas faire et que la page fait : attacher un geste à
        chaque manque, distinguer « bloquant pour le manga » de « bloquant pour le light
        novel », et proposer un bouton là où la réparation est sûre.

        La sortie console brute reste accessible depuis la page (« Sortie console… ») : elle
        sert à coller dans un rapport, et ce besoin-là n'a pas disparu."""
        panneau = self.aller_a("diagnostic")
        if panneau is not None and not panneau.sections():
            self._lancer_diagnostic(True)

    def action_tester_llm(self) -> None:
        self._panneau_de_sortie(
            "Test de la connexion LLM", self._capturer_test_llm,
            sous_titre="Joignabilité du serveur, modèles disponibles, mini-génération.")

    def action_a_propos(self) -> None:
        """⚠ **Aucun appel réseau ici** — lot 40. Le résultat de la vérification du démarrage
        est passé tel quel : elle a déjà eu lieu, dans le fil de travail. Sans ce passage, la
        page repartirait pour 3,0 s de délai sur le fil d'affichage pour réafficher la même
        phrase. `None` quand la tâche n'a pas encore rendu — `texte_a_propos` retombe alors sur
        son comportement d'origine, qui est celui que ses tests décrivent."""
        from .dialogues import DialogueTexte, texte_a_propos
        resultat = ((getattr(self, "_resultat_sondes", {}) or {}).get("maj")
                    or (getattr(self, "_resultat_maj", {}) or {}).get("maj"))
        DialogueTexte("À propos d'Angelith", texte_a_propos(self.config, resultat),
                      self).exec()

    # ------------------------------------------------------------------ #
    # L40.3 — la mise à jour : vérifier, proposer, télécharger, installer
    #
    # ⚠ Quatre étapes SÉPARÉES, et l'utilisateur peut sortir entre chacune. Un seul bouton
    # « mets-moi à jour » cacherait le seul moment où il peut encore dire non : entre
    # l'empreinte vérifiée et l'installeur lancé.
    # ------------------------------------------------------------------ #

    def action_rechercher_maj(self) -> None:
        """Le bouton d'« À propos ». **La vérification part dans le fil de travail.**

        ⚠ Le `GET` est court (3,0 s de plafond), mais il reste un appel réseau, et la règle du
        dépôt ne connaît pas d'exception de taille : `gui/sondes.py` — « aucune sonde ne
        s'exécute sur le fil d'affichage ». Le clic répond donc par une ligne de journal, pas
        par une fenêtre immédiate."""
        config = self.config
        resultat = self._resultat_maj = {}

        def _travail():
            resultat["maj"] = maj.verifier(config)
            return resultat["maj"].phrase()

        self._maj_demandee = True
        self.fil.soumettre(Tache(genre=GENRE_SONDE, fonction=_travail, planche=None,
                                 libelle="Recherche de mise à jour"))

    def _proposer_maj(self, resultat, *, demandee: bool) -> None:
        """La fenêtre, **si elle a lieu d'être**.

        Deux appelants, deux exigences différentes, et c'est tout l'objet de `demandee` :

        · au **démarrage**, on n'ouvre que si une version plus récente existe ET que la case
          « ne plus afficher » n'a pas été cochée (`vue_maj.doit_proposer`). ⚠ Un échec de
          vérification n'ouvre jamais rien : au 2026-09-06 c'est le cas nominal — le miroir
          public est privé et l'API rend 404 — et une fenêtre « je n'ai pas pu vérifier » à
          chaque démarrage serait la seule chose que ce lot aurait livrée à tout le monde ;
        · sur **clic**, on répond toujours quelque chose, y compris « vous avez la dernière » et
          y compris l'échec : un bouton qui ne fait rien passe pour cassé."""
        if resultat is None:
            return
        if not demandee:
            if not vmaj.doit_proposer(resultat, self.reglages):
                return
        elif not resultat.disponible:
            QMessageBox.information(self, "Rechercher une mise à jour", resultat.phrase())
            return

        from .dialogues import DialogueMaj
        boite = DialogueMaj(resultat, __version__, gele=inst.gele(), parent=self)
        code = boite.exec()
        if boite.silencieuse():
            # ⚠ Écrit tout de suite, et pas seulement à la fermeture de l'application : qui
            # coche « ne plus afficher » puis débranche la machine ne doit pas revoir la
            # fenêtre au démarrage suivant.
            self.reglages["maj_silencieuse"] = True
            reg.ecrire(self._collecter_reglages())
        if code != boite.DialogCode.Accepted:
            return
        if boite.choix() == "page":
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(resultat.page))
            return
        if boite.choix() == "installer":
            self._telecharger_maj(resultat)

    def _telecharger_maj(self, resultat) -> None:
        """Télécharge l'installeur et vérifie son empreinte — **dans le fil de travail**.

        292 Mio à 2,5 Mio/s font ~115 s (1 mesure, 2026-09-06). Rien de tout cela ne peut
        tourner sur le fil d'affichage, et la progression passe par les signaux ordinaires.

        ⚠ **L'empreinte est vérifiée ICI, pas à l'installation.** Un fichier dont l'empreinte
        ne correspond pas est effacé sur place : le laisser sur le disque, c'est prendre le
        risque qu'il soit lancé plus tard à la main."""
        fichier = resultat.installeur()
        sommes = resultat.sommes()
        if fichier is None or sommes is None:      # pragma: no cover — `installable` l'exclut
            return
        if self.fil.occupe() or self.fil.en_attente():
            QMessageBox.warning(self, "Mise à jour",
                                "Un travail est en cours — attends la fin, ou arrête-le. "
                                "L'installation ferme l'application.")
            return
        signaux = self.signaux
        etat = self._maj_en_cours = {"resultat": resultat}

        def _travail():
            import tempfile

            dossier = Path(tempfile.mkdtemp(prefix="angelith-maj-"))
            attendue = maj.empreinte_attendue(maj.lire_texte(sommes), fichier.nom)
            if not attendue:
                raise RuntimeError(
                    f"{fichier.nom} ne figure pas dans le {maj.NOM_SOMMES} de cette release : "
                    "rien n'a été téléchargé, parce que rien n'aurait pu être vérifié.")

            def _progres(lus, total):
                signaux.ligne.emit("verbose", vmaj.phrase_progres(lus, total))
                signaux.progression.emit(lus, total or 0)

            chemin = maj.telecharger(fichier, dossier / fichier.nom, progres=_progres)
            obtenue = maj.empreinte(chemin)
            if obtenue != attendue:
                chemin.unlink(missing_ok=True)
                raise RuntimeError(vmaj.phrase_echec_empreinte(attendue, obtenue))
            etat["installeur"] = chemin
            return f"{fichier.nom} téléchargé et son empreinte vérifiée."

        self.fil.soumettre(Tache(genre=GENRE_MAJ, fonction=_travail, planche=None,
                                 libelle="Téléchargement de la mise à jour"))

    def _recevoir_maj(self, succes: bool, message: str) -> None:
        """Le fichier est là et vérifié : **une dernière confirmation, puis on quitte.**

        ⚠ C'est le dernier moment où quelqu'un peut dire non, et il est explicite : lancer
        l'installeur ferme l'application, et personne ne doit découvrir ça après coup."""
        etat = getattr(self, "_maj_en_cours", {}) or {}
        chemin = etat.get("installeur")
        if not succes or chemin is None:
            QMessageBox.warning(self, "Mise à jour", message)
            return
        reponse = QMessageBox.question(
            self, "Installer la mise à jour",
            f"{message}\n\n"
            "L'installeur va se lancer et Angelith se ferme pour le laisser remplacer "
            "l'installation.\n"
            "Tes projets, tes réglages et tes poids de modèles ne sont pas touchés.\n\n"
            "Lancer l'installeur maintenant ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reponse != QMessageBox.Yes:
            self._journaliser(
                "info", f"Installation reportée — l'installeur vérifié est dans {chemin}.")
            return
        try:
            maj.installer(chemin)
        except Exception as err:                   # noqa: BLE001 — un lancement qui échoue
            QMessageBox.warning(self, "Mise à jour",
                                f"L'installeur n'a pas pu être lancé : {err}")
            return
        self.close()

    # ------------------------------------------------------------------ #
    # Diagnostic — capture de sortie, dans le fil de travail
    # ------------------------------------------------------------------ #

    # ⚠ `_capturer_diagnostic` a été SUPPRIMÉ au lot 36, et c'est le sujet du lot : il
    # redirigeait `stdout` des deux doctors dans un `DialogueTexte`, ce qui donnait un texte
    # sans geste, inexploitable par l'accueil comme par le dépôt guidé. Le diagnostic est
    # maintenant une structure (`core/diagnostic.py`) et une page (`gui/diagnostic.py`) ; la
    # sortie console exacte reste disponible par `_montrer_diagnostic_texte`, reconstituée
    # depuis les verdicts déjà collectés plutôt qu'en relançant un appel réseau.
    #
    # `_capturer_test_llm` RESTE, lui, et c'est délibéré : le `PLAN-36` §4 l'écrit — « Tester
    # la connexion LLM peut rester une capture de texte si sa sortie n'a pas de geste
    # attaché ». Sa sortie est une trace de conversation avec un serveur, pas une liste de
    # manques.

    def _capturer_test_llm(self) -> str:
        import contextlib
        import io
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            try:
                from core.llm import test_connection
                test_connection(self.config)
            except Exception as err:                   # noqa: BLE001
                print(f"❌ test interrompu : {err}")
        return tampon.getvalue()

    def _panneau_de_sortie(self, titre: str, capture, *, sous_titre: str = "") -> None:
        """Exécute `capture()` dans le fil de travail et montre son texte.

        ⚠ Le diagnostic parle à Ollama : sur un serveur injoignable, `test_connection` attend
        son délai de 30 s. Sur le fil d'affichage, ce serait trente secondes de fenêtre gelée
        pour une entrée de menu."""
        boite_attente = QMessageBox(self)
        boite_attente.setWindowTitle(titre)
        boite_attente.setText(f"{titre} en cours…")
        boite_attente.setStandardButtons(QMessageBox.NoButton)
        resultat: dict = {}

        def _travail():
            resultat["texte"] = capture()
            return f"{titre} : terminé."

        def _fini(_planche, genre, _succes, _message):
            if genre != GENRE_CREATION or "texte" not in resultat:
                return
            self.signaux.fin.disconnect(_fini)
            boite_attente.done(0)
            from .dialogues import DialogueTexte
            DialogueTexte(titre, resultat["texte"] or "(aucune sortie)", self,
                          sous_titre=sous_titre).exec()

        self.signaux.fin.connect(_fini)
        self.fil.soumettre(Tache(genre=GENRE_CREATION, fonction=_travail, planche=None,
                                 libelle=titre))
        boite_attente.exec()

    def _projet_courant(self, titre: str) -> str | None:
        """Le projet visé par une action de glossaire — celui qui est ouvert, ou un choix.

        ⚠ La liste proposée est celle de `pipeline.sources.list_projects`, pas celle de
        `lister_projets` : un glossaire appartient à l'ŒUVRE, light novel compris, et refuser
        d'importer dans un projet purement roman parce que l'éditeur de planches ne l'affiche
        pas serait absurde."""
        if self.tome is not None:
            return self.tome.projet
        from pipeline.sources import list_projects
        try:
            projets = list_projects(self._racine_sources())
        except OSError:
            projets = []
        if not projets:
            QMessageBox.information(self, titre,
                                    f"Aucun projet sous {self._racine_sources()}.")
            return None
        from PySide6.QtWidgets import QInputDialog
        projet, ok = QInputDialog.getItem(self, titre, "Projet", projets, 0, False)
        return projet if ok and projet else None

    # ------------------------------------------------------------------ #
    # L18.2 — le glisser-déposer
    # ------------------------------------------------------------------ #

    def dragEnterEvent(self, event) -> None:
        """Accepte, et le DIT. Un survol sans retour visuel fait passer le geste pour cassé."""
        chemins = self._chemins_du_depot(event)
        if not chemins:
            event.ignore()
            return
        genre, _, message = dep.classer(chemins)
        self.statusBar().showMessage(message, 4000)
        if genre == dep.INCONNU:
            # ⚠ On accepte quand même le survol : refuser ici priverait `dropEvent` du lâcher,
            # donc du seul moment où l'on peut EXPLIQUER pourquoi ça ne marche pas. Un curseur
            # barré et rien d'autre est précisément le silence que le plan reproche.
            event.acceptProposedAction()
            return
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self.statusBar().clearMessage()
        event.accept()

    def dropEvent(self, event) -> None:
        chemins = self._chemins_du_depot(event)
        genre, retenus, message = dep.classer(chemins)
        event.acceptProposedAction()
        self.statusBar().clearMessage()
        if genre == dep.SOURCES:
            # ⚠ Le dépôt GUIDÉ (lot 34), et non plus la boîte « Nouveau projet ». Le geste
            # part d'un lâcher : ce qui manquait n'était pas la création mais le compte rendu
            # de ce qu'on vient de lâcher, la collision nommée, et le refus d'un `.cbr` sans
            # `unrar` AVANT l'import plutôt qu'au milieu de la copie. Cf. `gui/depot_guide.py`.
            self.action_depot_guide(retenus)
        elif genre == dep.SOURCES_LN:
            # ⚠ Le parcours guidé ne convient pas à un roman : il lit des ARCHIVES et compte
            # des planches. Un `.pdf` ou un `.epub` va donc droit à « Nouveau projet », qui
            # sait déjà proposer le nom du projet et du tome depuis le chemin.
            self.action_nouveau_projet(retenus)
        elif genre == dep.GLOSSAIRE:
            self.action_importer_glossaire(retenus)
        else:
            # ⚠ Un message, jamais un silence.
            self._journaliser("warn", message)
            QMessageBox.information(self, "Rien à faire de ce dépôt", message)

    @staticmethod
    def _chemins_du_depot(event) -> list[Path]:
        donnees = event.mimeData()
        if donnees is None or not donnees.hasUrls():
            return []
        return [Path(url.toLocalFile()) for url in donnees.urls() if url.isLocalFile()]

    def closeEvent(self, event) -> None:
        """Trois choses à ne pas perdre : les saisies non enregistrées **de tout le tome**,
        une tâche en cours, et la propreté d'un checkpoint à moitié écrit.

        ⚠ La 1.5.0 a fait passer l'éditeur d'UNE planche ouverte à N, mais cette méthode
        appelait encore `enregistrer_document()`, qui n'écrit que la planche AFFICHÉE : avec
        cinq planches modifiées, « Enregistrer et quitter » en sauvait une et jetait les
        quatre autres sans un mot — ni boîte, ni journal, ni trace."""
        # ⚠ **La MÊME garde qu'au changement de tome**, et depuis le lot 35 le même code :
        # `peut_quitter("fermeture")`. La boîte était déjà partagée (`_boite_travail_en_attente`,
        # lot 18) ; ce qui ne l'était pas est la décision de la poser, et c'est justement elle
        # qui avait divergé — un chemin gardé, l'autre non. `peut_quitter` couvre aussi le
        # refus d'écriture d'une planche qu'un run a réécrite : il la nomme et rend `False`.
        if not self.peut_quitter("fermeture"):
            event.ignore()
            return
        if self.fil.touche_tout():
            reponse = QMessageBox.question(
                self, "Run en cours",
                "Un run tourne encore. Demander l'arrêt propre et attendre ?\n\n"
                "« Non » ferme la fenêtre — le run continue jusqu'à la prochaine frontière "
                "propre puis s'arrête.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reponse == QMessageBox.Yes:
                self._arreter_run()
                event.ignore()
                return
            self._arreter_run()
        self.fil_lecture.arreter()
        self.fil.arreter()
        # ⚠ Attendre VRAIMENT que les fils rendent la main. Un `wait()` court qui expire laisse
        # Qt détruire l'objet QThread C++ pendant que le fil tourne encore — d'où le
        # « QThread: Destroyed while thread is still running » au terminal, et un risque réel
        # d'écriture à moitié faite. On attend par tranches (le `wait` de Qt n'est pas
        # interruptible), et si le fil ne rend toujours pas la main, on le DIT plutôt que de
        # fermer en silence : une tâche coupée en plein `save_regions` laisse un checkpoint
        # incomplet, et c'est exactement ce que l'utilisateur doit savoir.
        for nom, fil, budget_ms in (("aperçus", self.fil_lecture, 5_000),
                                    ("travaux", self.fil, 30_000)):
            reste = budget_ms
            while fil.isRunning() and reste > 0:
                fil.wait(250)
                reste -= 250
            if fil.isRunning():
                self._journaliser(
                    "warn", f"Le fil des {nom} n'a pas rendu la main en "
                            f"{budget_ms // 1000} s — la tâche en cours peut laisser un "
                            f"checkpoint incomplet. Relance un run sur la planche concernée.")
        # Les fils sont morts : plus personne n'écrira, on peut fermer sans condition.
        for reporter in self._reporters_ouverts:
            fermer = getattr(reporter, "close", None)
            if callable(fermer):
                fermer()
        self._reporters_ouverts.clear()
        if self.services is not None:
            self.services.liberer()
        # ⚠ En DERNIER, et après `event.accept()` serait trop tard. La disposition n'est pas du
        # travail à protéger — c'est pourquoi `reglages.ecrire` avale ses erreurs plutôt que de
        # faire échouer une fermeture sur un dossier en lecture seule.
        self._enregistrer_reglages()
        event.accept()

    # ------------------------------------------------------------------ #
    # L18.7 — l'état de travail survit au redémarrage
    # ------------------------------------------------------------------ #

    def _appliquer_reglages(self) -> None:
        """Repose ce que la session précédente a laissé — **et ne rouvre aucun tome**.

        ⚠ C'est ici que le lot 31 se voit le plus. La version d'avant reposait le tome :
        `setCurrentText` sur les deux `QComboBox` de la barre haute, donc `_ouvrir_tome`, donc
        un `Tome`, un `Services` et une pellicule. `dernier_projet` / `dernier_tome` restent
        persistés, mais ils n'alimentent plus qu'une **carte** de l'accueil : il faut un clic.

        Les réglages de chaque destination ne sont pas appliqués ici non plus — chaque fabrique
        applique les siens au panneau qu'elle vient de construire. Les appliquer d'avance
        supposerait que les panneaux existent, ce qui est précisément ce qu'on refuse."""
        etat = self.reglages
        voulue = str(etat.get("destination") or dst.ACCUEIL)
        # ⚠ La condition porte sur `action`, pas sur `pied` : depuis le lot 36 le Diagnostic
        # est une page de pied, et rouvrir dessus est légitime — rouvrir sur un DIALOGUE ne
        # l'est pas, puisqu'il n'y a pas d'écran derrière.
        destination_voulue = dst.par_identifiant(voulue)
        if destination_voulue is None or destination_voulue.action:
            voulue = dst.ACCUEIL
        if voulue != dst.ACCUEIL and not etat.get("reprendre", True):
            # « Reprendre la dernière session » décochée : on rouvre sur l'accueil, qui est le
            # seul écran dont on soit sûr qu'il ne coûte rien.
            voulue = dst.ACCUEIL
        self.aller_a(voulue)

    def showEvent(self, event) -> None:
        """Repose la disposition **après** que la fenêtre a une géométrie, et lance les sondes.

        ⚠ `QSplitter.setSizes` sur un widget sans géométrie est sans effet : Qt répartit à
        parts égales à la première mise en page, et écrase ce qu'on vient de poser. Les
        réglages sont lus dans `__init__`, donc bien avant `show()`. Sans ce second passage,
        `.angelith/interface.json` serait écrit fidèlement et relu pour rien.

        ⚠ **Les sondes partent d'ICI, et pas plus tôt.** Elles font un appel réseau ; les
        lancer dans `__init__` les mettrait avant le premier pixel, c'est-à-dire exactement ce
        que `gui/sondes.py` interdit."""
        super().showEvent(event)
        if getattr(self, "_disposition_posee", False):
            return
        self._disposition_posee = True
        self.separateur.setSizes(list(self.reglages["journal"]))
        editeur = self.editeur
        if editeur is not None:
            editeur.poser_disposition()
        self.navigation.appliquer_largeur(self.width())
        self._lancer_sondes()

    def resizeEvent(self, event) -> None:
        """Le pane suit la largeur de la fenêtre — 1008 px et 641 px, les seuils Fluent.

        La décision est prise par `destinations.mode_pour_largeur`, en Python nu ; ici on ne
        fait que la lui demander à chaque redimensionnement.

        ⚠ `event.size()`, et **pas** `self.width()`. Sous `QT_QPA_PLATFORM=offscreen`, la
        géométrie du widget n'est pas encore à jour quand l'événement arrive : le pane restait
        déployé quelle que soit la largeur demandée, et le test de bascule adaptative passait
        pour une limite de la plateforme alors que c'était la mesure qui était prise au mauvais
        endroit."""
        super().resizeEvent(event)
        navigation = getattr(self, "navigation", None)
        if navigation is not None:
            navigation.appliquer_largeur(event.size().width())

    # ------------------------------------------------------------------ #
    # L31.6 — les trois sondes, et aucune sur le fil d'affichage
    # ------------------------------------------------------------------ #

    def _lancer_sondes(self) -> None:
        """Soumet les trois sondes au fil de travail. **Une seule fois par session.**

        ⚠ `GENRE_SONDE` — et non `GENRE_CREATION`. Le genre décide de ce que l'interface
        verrouille : une tâche `planche=None` de genre ordinaire grise le bouton « Lancer »
        (`FilDeTravail.touche_tout`), ce qui poserait un verrou d'écriture pendant les deux
        secondes du délai réseau, à chaque démarrage, pour un travail qui n'écrit rien."""
        if getattr(self, "_sondes_lancees", False):
            return
        self._sondes_lancees = True
        config = self.config
        resultat = self._resultat_sondes = {}

        def _travail():
            # ⚠ La vérification de version part AVEC les sondes, dans la même tâche du fil de
            # travail — lot 40. Deux raisons, et la seconde est la vraie : c'est un appel
            # réseau, donc il est interdit de fil d'affichage (`gui/sondes.py`) ; et une tâche
            # de plus paierait une seconde fois l'ordonnancement pour un `GET` de 3 lignes.
            # `maj.verifier` ne lève jamais et ne part pas si `config.yaml` ne l'arme pas.
            resultat["maj"] = maj.verifier(config)
            resultat["sondes"] = snd.sonder_tout(config)
            # ⚠ La liste des modèles part avec les trois sondes, et pas dans une tâche à
            # elle : c'est le même appel réseau vers le même serveur, et deux tâches
            # paieraient deux fois le délai de résolution de `localhost` — 2,04 s sur cette
            # machine, mesuré (cf. `core/modeles.py`).
            resultat["modeles"] = mdl.lister(snd.url_llm(config))
            return "Sondes d'installation terminées."

        self.fil.soumettre(Tache(genre=GENRE_SONDE, fonction=_travail, planche=None,
                                 libelle="Sondes d'installation"))

    def _lancer_sonde_modeles(self) -> None:
        """« Rafraîchir la liste » — la même sonde, sans les trois marqueurs d'installation.

        ⚠ **Dans le fil de travail, comme tout appel réseau.** Un GET sur un endpoint arrêté
        coûte des secondes ; sur le fil d'affichage, ce serait la fenêtre gelée pour une
        information de confort — la règle absolue de `gui/sondes.py`."""
        config = self.config
        resultat = self._resultat_sondes = {}

        def _travail():
            resultat["modeles"] = mdl.lister(snd.url_llm(config))
            return "Liste des modèles rafraîchie."

        self.fil.soumettre(Tache(genre=GENRE_SONDE, fonction=_travail, planche=None,
                                 libelle="Liste des modèles"))

    def _recevoir_sondes(self, succes: bool, message: str) -> None:
        """Pose les verdicts sur l'accueil — **s'il est construit et si elles ont répondu**.

        Un échec ne laisse pas les trois marqueurs à « inconnu » par accident : `sonder_tout`
        ne lève pas, et si la tâche échoue quand même, la ligne part au journal en `verbose`
        plutôt que d'inventer un verdict."""
        # ⚠ EN TÊTE, avant les `return` qui suivent : la tâche du bouton « Rechercher une
        # mise à jour » ne rapporte aucune sonde, et un branchement en fin de méthode ne
        # serait jamais atteint pour elle.
        self._recevoir_maj_verifiee(succes)
        resultat = getattr(self, "_resultat_sondes", {}) or {}
        catalogue = resultat.get("modeles")
        if succes and catalogue is not None:
            self._catalogue_modeles = catalogue
            for panneau in [*self.lanceurs(), self.atelier]:
                if panneau is not None:
                    panneau.poser_modeles(catalogue)
            self._journaliser("verbose", catalogue.phrase())
        sondes = resultat.get("sondes")
        if not succes or not sondes:
            if not succes:
                self._journaliser("verbose", f"Sondes d'installation : {message}")
            return
        accueil = self._panneaux.get(dst.ACCUEIL)
        if accueil is not None:
            accueil.poser_sondes(sondes)
        for sonde in sondes:
            if sonde.etat == snd.INJOIGNABLE:
                self._journaliser("verbose", sonde.ligne())

    def _recevoir_maj_verifiee(self, succes: bool) -> None:
        """Le versant « mise à jour » de la tâche des sondes, quel que soit son déclencheur.

        ⚠ Il ne sait pas si la tâche venait du démarrage ou du bouton : c'est `_maj_demandee`
        qui le dit, et il est remis à `False` ici même. Sans cette remise à zéro, la sonde de
        modèles suivante rouvrirait la fenêtre du bouton."""
        demandee = bool(getattr(self, "_maj_demandee", False))
        self._maj_demandee = False
        # ⚠ **Deux sources, et jamais le repli de l'une sur l'autre.** `_resultat_maj` garde le
        # résultat du dernier clic pour toute la session ; y retomber quand la tâche est une
        # autre sonde ferait rouvrir la fenêtre de proposition à chaque « Rafraîchir la liste
        # des modèles », sur un résultat qui date. Une tâche répond de SON résultat.
        seau = "_resultat_maj" if demandee else "_resultat_sondes"
        resultat = (getattr(self, seau, {}) or {}).get("maj")
        if resultat is None:
            if demandee:
                self._journaliser("warn", "Recherche de mise à jour : aucune réponse.")
            return
        if not succes:
            if demandee:
                QMessageBox.information(self, "Rechercher une mise à jour", resultat.phrase())
            return
        self._journaliser("verbose", resultat.phrase())
        self._proposer_maj(resultat, demandee=demandee)

    def _collecter_reglages(self) -> dict:
        """L'état à persister. **Aucune case coûteuse ici** — cf. `reglages.NON_PERSISTES`.

        ⚠ **Seuls les panneaux CONSTRUITS sont interrogés**, et c'est indispensable : une
        session qui reste sur l'accueil n'a pas d'éditeur, et lui demander ses colonnes
        écraserait celles de la session précédente par des valeurs par défaut. Ce qui n'a pas
        été ouvert garde ce que le fichier disait — le lot ne doit rien faire perdre à qui ne
        va nulle part."""
        etat = dict(self.reglages)
        etat["fenetre"] = {"largeur": self.normalGeometry().width() or self.width(),
                           "hauteur": self.normalGeometry().height() or self.height(),
                           "maximisee": bool(self.isMaximized())}
        etat["journal"] = list(self.separateur.sizes())
        etat["destination"] = self.destination()
        panneau = self._panneaux.get("retouche")
        if panneau is not None:
            projet, tome = panneau.cible()
            etat["dernier_projet"] = projet
            etat["dernier_tome"] = tome
            etat.update(panneau.editeur.reglages())
        runs = dict(etat.get("runs") or {})
        for identifiant in LANCEURS:
            lanceur = self._panneaux.get(identifiant)
            if lanceur is not None:
                runs[identifiant] = lanceur.reglages_persistables()
        etat["runs"] = runs
        atelier = self.atelier
        if atelier is not None:
            etat["atelier"] = atelier.reglages()
        return etat

    def _enregistrer_reglages(self) -> None:
        self.reglages = self._collecter_reglages()
        reg.ecrire(self.reglages)
