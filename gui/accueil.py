# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'accueil — **et il n'ouvre rien**.

## Le défaut qu'il ferme

Jusqu'au lot 30, `python gui.py` ouvrait le premier projet par ordre alphabétique. Pas
« affichait son nom » : **ouvrait**. Un `Tome` lu, un `Services` construit, l'éditeur peuplé,
et la composition d'aperçus lancée. Mesuré sur le corpus réel le 2026-09-04 (18 dossiers
sous `sources/`) : 1,89 s avant le premier pixel dont 1,40 s pour ce seul tome, 692 ouvertures de
fichiers, 11 aperçus et 62,4 Mo de cache dans les dix secondes suivantes — pour un tome que
personne n'avait demandé. Tout est dans `docs/mesures/coquille-2026-09-04.md`.

Cette page est ce qui prend sa place. Elle lit `.angelith/interface.json` et trois états de la
machine ; elle ne touche à `sources/` que pour savoir s'il est vide.

## Les trois informations d'état, et pourquoi elles n'arrivent pas tout de suite

`gui/sondes.py` les mesure **dans le fil de travail**, après `show()`. La page s'affiche
complète avec les trois marqueurs en « inconnu », et `poser_sondes()` les remplace quand elles
répondent. Un endpoint LLM injoignable coûte un délai d'attente, pas un refus : le mettre sur
le fil d'affichage gèlerait la fenêtre avant le premier pixel, pour une information de confort.

## L'état vide reste celui du lot 18

Quand `sources/` est vide, l'accueil porte les deux boutons que `PanneauEditeur.montrer_accueil`
portait — « Nouveau projet » et « Ouvrir sources » — et la ligne `warn` du journal reste émise
par la fenêtre (elle déplie le journal et s'affiche 8 s dans la barre d'état). On ne remplace
pas un état vide qui marche par un plus joli qui en fait moins.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from core.version import ETAT_BRIQUES, __version__

from . import destinations as dest
from . import icones as ico
from . import sondes as snd
from . import theme

#: Nombre d'œuvres récentes montrées. Deux ou trois : au-delà, la carte devient une
#: bibliothèque, et la bibliothèque est le `PLAN-34`.
RECENTS_MONTRES = 3

#: Ce que l'accueil dit de chaque brique, à côté de son état. ⚠ La brique `scan` est en BÊTA
#: et l'accueil doit le dire **là où l'utilisateur choisit** — pas seulement dans le titre de
#: la fenêtre, que personne ne lit avant de cliquer.
PHRASES_ETAT = {
    "stable": "éprouvée sur le corpus du dépôt",
    "beta": "bêta — mesurée sur un seul tirage",
    "experimental": "expérimentale — les images produites ne sont pas encore validées",
}


class Carte(QFrame):
    """Une carte de destination : icône, libellé, ce qu'elle fait. Cliquable en entier."""

    def __init__(self, destination, parent=None):
        super().__init__(parent)
        self.destination = destination
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(theme.Espacement.M, theme.Espacement.M,
                                   theme.Espacement.M, theme.Espacement.M)
        colonne.setSpacing(theme.Espacement.XS)
        entete = QHBoxLayout()
        self.bouton = QToolButton()
        self.bouton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.bouton.setAutoRaise(True)
        self.bouton.setText(destination.libelle)
        self.bouton.setIcon(ico.icone(destination.icone))
        self.bouton.setAccessibleName(f"Aller à {destination.libelle}")
        entete.addWidget(self.bouton)
        entete.addStretch(1)
        colonne.addLayout(entete)
        self.texte = QLabel(destination.infobulle)
        self.texte.setWordWrap(True)
        theme.poser_role(self.texte, "faible")
        colonne.addWidget(self.texte)

    def rafraichir_theme(self) -> None:
        self.bouton.setIcon(ico.icone(self.destination.icone))


class PanneauAccueil(QWidget):
    """La page d'ouverture. Aucun tome, aucun modèle, aucun appel réseau sur ce fil."""

    #: Aller à une destination — la fenêtre décide, comme pour le pane.
    demande_destination = Signal(str)
    #: Reprendre une œuvre : `(destination, projet, tome)`.
    demande_reprise = Signal(str, str, str)
    #: Les deux gestes de l'état vide, déjà servis par la fenêtre depuis le lot 18.
    demande_creation = Signal()
    demande_sources = Signal()
    #: L36.4 — « Créer un tome de démonstration ». Une installation neuve n'a aucune œuvre, et
    #: l'utilisateur ne peut pas en fournir une pour essayer sans se poser la question des
    #: droits. Ce geste écrit un tome fabriqué par le programme lui-même, redistribuable sans
    #: réserve, marqué comme démonstration et supprimable sans rien casser.
    demande_demonstration = Signal()

    #: L'ordre de tabulation — les cartes dans l'ordre du pane, puis la reprise, puis l'état
    #: vide. Déclaré, comme pour tous les panneaux depuis le `PLAN-19`.
    PARCOURS: tuple[str, ...] = ("cartes", "reprises", "bouton_diagnostic", "bouton_creer",
                                "bouton_sources", "bouton_demo")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cartes: dict[str, Carte] = {}
        self._boutons_reprise: list[QPushButton] = []
        self._construire()

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(theme.Espacement.XL, theme.Espacement.L,
                                   theme.Espacement.XL, theme.Espacement.L)
        colonne.setSpacing(theme.Espacement.M)

        self.titre = QLabel("Angelith")
        theme.poser_role(self.titre, "titre")
        self.titre.setAccessibleName("Accueil")
        colonne.addWidget(self.titre)

        self.version = QLabel(self._phrase_version())
        self.version.setWordWrap(True)
        theme.poser_role(self.version, "faible")
        colonne.addWidget(self.version)

        # -- les six cartes ------------------------------------------------ #
        grille = QGridLayout()
        grille.setSpacing(theme.Espacement.S)
        metier = [d for d in dest.corps() if d.identifiant != dest.ACCUEIL]
        for rang, destination in enumerate(metier):
            carte = Carte(destination)
            carte.bouton.clicked.connect(
                lambda _c=False, i=destination.identifiant:
                self.demande_destination.emit(i))
            grille.addWidget(carte, rang // 3, rang % 3)
            self._cartes[destination.identifiant] = carte
        colonne.addLayout(grille)

        # -- les œuvres récentes ------------------------------------------- #
        self.titre_recents = QLabel("Reprendre")
        colonne.addWidget(self.titre_recents)
        self.boite_recents = QWidget()
        self.ligne_recents = QHBoxLayout(self.boite_recents)
        self.ligne_recents.setContentsMargins(0, 0, 0, 0)
        self.ligne_recents.setSpacing(theme.Espacement.S)
        colonne.addWidget(self.boite_recents)

        # -- ce que la machine sait faire ---------------------------------- #
        self.titre_sondes = QLabel("Ce que cette machine sait faire")
        colonne.addWidget(self.titre_sondes)
        self.etat_sondes = QLabel("")
        self.etat_sondes.setWordWrap(True)
        self.etat_sondes.setAccessibleName("État de l'installation")
        theme.poser_role(self.etat_sondes, "mono")
        colonne.addWidget(self.etat_sondes)
        # L36.3 — quand une sonde dit « absent », l'accueil ne se contente pas de le
        # constater : il mène à l'endroit qui dit quoi faire. ⚠ Il n'y mène PAS tout seul —
        # une navigation automatique au démarrage serait pire que le silence.
        ligne_diag = QHBoxLayout()
        self.bouton_diagnostic = QPushButton("Voir le diagnostic")
        self.bouton_diagnostic.setToolTip(
            "Ce qui manque à cette installation, ce que ça coûte, et quoi faire. Les trois "
            "marqueurs ci-dessus ne disent que « est-ce que ça répond ? » ; le diagnostic, lui, "
            "inspecte la configuration, les dépendances, les poids et les polices.")
        self.bouton_diagnostic.clicked.connect(
            lambda: self.demande_destination.emit("diagnostic"))
        self.bouton_diagnostic.setVisible(False)
        ligne_diag.addWidget(self.bouton_diagnostic)
        ligne_diag.addStretch(1)
        colonne.addLayout(ligne_diag)
        self.poser_sondes(snd.inconnues())

        # -- l'état vide, celui du lot 18 ---------------------------------- #
        self.boite_vide = QWidget()
        ligne_vide = QVBoxLayout(self.boite_vide)
        ligne_vide.setContentsMargins(0, 0, 0, 0)
        self.titre_vide = QLabel("")
        self.titre_vide.setWordWrap(True)
        theme.poser_role(self.titre_vide, "avertissement")
        ligne_vide.addWidget(self.titre_vide)
        boutons = QHBoxLayout()
        self.bouton_creer = QPushButton("Créer un projet…")
        self.bouton_creer.setToolTip(
            "Choisis des images ou une archive : Angelith crée "
            "sources/<Projet>/<Tome>/<format>/ et y COPIE les fichiers.")
        self.bouton_creer.clicked.connect(self.demande_creation.emit)
        self.bouton_sources = QPushButton("Ouvrir le dossier de sources")
        self.bouton_sources.setToolTip(
            "Ouvre sources/ dans l'explorateur de fichiers, pour y déposer un tome à la main.")
        self.bouton_sources.clicked.connect(self.demande_sources.emit)
        boutons.addWidget(self.bouton_creer)
        boutons.addWidget(self.bouton_sources)
        boutons.addStretch(1)
        ligne_vide.addLayout(boutons)
        self.boite_vide.setVisible(False)
        colonne.addWidget(self.boite_vide)

        self.astuce = QLabel(
            "… ou fais glisser un dossier de planches, un .cbz ou un .cbr n'importe où sur "
            "cette fenêtre.")
        self.astuce.setWordWrap(True)
        theme.poser_role(self.astuce, "faible")
        colonne.addWidget(self.astuce)

        # -- L36.4 — de quoi essayer sans fournir d'œuvre ------------------- #
        # ⚠ Le bouton est TOUJOURS là, pas seulement dans l'état vide. Quelqu'un qui a déjà
        # dix-huit œuvres peut vouloir vérifier une installation sans y toucher, et c'est
        # même le cas d'usage le plus fréquent après une mise à jour.
        ligne_demo = QHBoxLayout()
        self.bouton_demo = QPushButton("Créer un tome de démonstration")
        self.bouton_demo.setToolTip(
            "Écrit un tome fabriqué par Angelith lui-même — deux planches, quatre bulles, "
            "aucune œuvre — sous sources/. Il permet de lancer un run court, de voir la "
            "retouche et de produire un CBZ et un PDF réels. Il est marqué comme "
            "démonstration et se supprime sans rien casser.")
        self.bouton_demo.clicked.connect(self.demande_demonstration.emit)
        ligne_demo.addWidget(self.bouton_demo)
        ligne_demo.addStretch(1)
        colonne.addLayout(ligne_demo)
        colonne.addStretch(1)
        self._poser_parcours()

    def _poser_parcours(self) -> None:
        """Chaîne les widgets deux à deux, dans l'ordre déclaré par `PARCOURS`.

        ⚠ `cartes` et `reprises` sont des GROUPES : un ordre par panneau qui s'arrêterait aux
        widgets nommés laisserait les six cartes dans l'ordre de construction — qui se trouve
        être le bon aujourd'hui, et qui cesserait de l'être au premier réagencement de la
        grille."""
        widgets: list[QWidget] = []
        for nom in self.PARCOURS:
            if nom == "cartes":
                widgets += [c.bouton for c in self._cartes.values()]
            elif nom == "reprises":
                widgets += list(self._boutons_reprise)
            elif hasattr(self, nom):
                widgets.append(getattr(self, nom))
        for avant, apres in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(avant, apres)

    @staticmethod
    def _phrase_version() -> str:
        """La version, et l'état de chaque brique — **avec le mot « bêta » quand il le faut**.

        Il était déjà dans le titre de la fenêtre, pour la seule brique manga. Une brique en
        bêta doit se dire là où l'on choisit d'y aller, pas dans une barre de titre."""
        morceaux = []
        for nom, etat in ETAT_BRIQUES.items():
            phrase = PHRASES_ETAT.get(etat)
            morceaux.append(f"{nom} : {etat}" + (f" ({phrase})" if phrase else ""))
        return f"Version {__version__} — " + "  ·  ".join(morceaux)

    # ------------------------------------------------------------------ #
    #  Ce que la fenêtre pose
    # ------------------------------------------------------------------ #

    def poser_sondes(self, sondes) -> None:
        """Affiche les trois marqueurs. Appelée au premier pixel avec `INCONNU`, puis avec les
        verdicts quand le fil de travail les rend.

        ⚠ **MISE À JOUR lot 36** — le bouton « Voir le diagnostic » n'apparaît **que si**
        quelque chose manque. Un bouton toujours visible devient du décor ; un bouton qui
        apparaît quand une sonde vient de dire « absent » est une réponse à ce qu'on lit. Et il
        n'apparaît pas sur `INCONNU` : « je n'ai pas encore regardé » n'est pas « c'est
        cassé »."""
        lignes = [s.ligne() for s in sondes]
        remedes = [s.remede for s in sondes if s.remede]
        self.etat_sondes.setText("\n".join(lignes + ([""] + remedes if remedes else [])))
        self.bouton_diagnostic.setVisible(
            any(s.etat == snd.INJOIGNABLE for s in sondes))

    def poser_recents(self, recents: list[dict], *, sources: Path | None = None) -> None:
        """Les œuvres récentes, **lues dans `.angelith/interface.json`**, pas sur le disque.

        ⚠ Un balayage de `sources/` pour dater dix-sept projets serait exactement le coût que
        cette page existe pour supprimer. Ce que le fichier dit peut être périmé — un tome
        supprimé depuis, un dossier renommé — et c'est pourquoi le bouton dit « Reprendre » et
        non « Ouvrir » : la fenêtre vérifiera à ce moment-là, et le dira si ça ne va plus."""
        for bouton in self._boutons_reprise:
            bouton.setParent(None)
        self._boutons_reprise.clear()
        for entree in list(recents)[:RECENTS_MONTRES]:
            projet = str(entree.get("projet") or "")
            tome = str(entree.get("tome") or "")
            destination = str(entree.get("destination") or "retouche")
            if not (projet and tome):
                continue
            bouton = QPushButton(f"Reprendre  ·  {projet} / {tome}")
            libelle = dest.par_identifiant(destination)
            bouton.setToolTip(f"Ouvre « {projet} / {tome} » dans "
                              f"« {libelle.libelle if libelle else destination} ».")
            bouton.setAccessibleName(f"Reprendre {projet} {tome}")
            bouton.clicked.connect(
                lambda _c=False, d=destination, p=projet, t=tome:
                self.demande_reprise.emit(d, p, t))
            self.ligne_recents.addWidget(bouton)
            self._boutons_reprise.append(bouton)
        self.ligne_recents.addStretch(1)
        vide = not self._boutons_reprise
        self.titre_recents.setVisible(not vide)
        self.boite_recents.setVisible(not vide)
        if vide and sources is not None:
            # Rien à reprendre n'est pas une erreur : c'est un premier lancement.
            self.titre_recents.setVisible(False)
        self._poser_parcours()

    def montrer_etat_vide(self, racine: Path | None) -> None:
        """`sources/` est vide : les deux boutons du lot 18, et la troisième voie du lot 36.

        ⚠ La phrase nomme les TROIS issues, dont celle qui ne demande rien à personne. Une
        installation neuve sans œuvre est le premier écran que voit un utilisateur, et lui
        dire seulement « apporte des fichiers » quand il n'en a pas encore le droit — ou pas
        encore l'envie — est ce que le `PLAN-36` L36.4 corrige."""
        self.boite_vide.setVisible(True)
        self.titre_vide.setText(
            f"Aucun projet manga sous {racine}.\n"
            "Angelith lit les planches sous sources/<Projet>/<Tome>/manga/. Le bouton "
            "ci-dessous crée cette arborescence et y copie tes images ou ton archive — ou "
            "crée un tome de démonstration, qui ne demande aucune œuvre.")

    def cacher_etat_vide(self) -> None:
        self.boite_vide.setVisible(False)

    def rafraichir_theme(self) -> None:
        """Les icônes des cartes sont des pixmaps : aucune règle QSS ne les atteint."""
        for carte in self._cartes.values():
            carte.rafraichir_theme()
