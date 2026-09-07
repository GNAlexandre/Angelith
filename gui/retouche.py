# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La destination « Retouche » — l'éditeur de planches, **et son propre couple projet/tome**.

## Ce que ce panneau est, et ce qu'il n'est pas

C'est une **enveloppe**. Il porte la barre projet/tome que la fenêtre portait jusqu'au lot 30,
l'indicateur de travail non enregistré, le bouton « Enregistrer tout le tome » et la révision
du tome sur le disque ; et il montre `PanneauEditeur` en dessous, inchangé.

⚠ **`gui/editeur.py` n'est pas touché**, et c'est une contrainte du plan (§4 : « Il ne modifie
pas `gui/editeur.py` au-delà du strict nécessaire pour le recevoir comme destination »).
L'éditeur pèse 107 Ko et porte la moitié de la couverture d'interface du dépôt ; lui greffer
deux listes déroulantes serait payer la refonte deux fois.

## Pourquoi le tome descend ici

Jusqu'au lot 30, le couple projet/tome était un état de la FENÊTRE que trois panneaux
lisaient — et l'onglet « Runs » avait dû se doter des SIENS au lot 18, parce que la liste de la
barre haute est filtrée sur les tomes manga : « il n'existait aucun chemin d'interface pour
lancer un run light novel sur un projet qui n'a pas aussi du manga ». Deux sélecteurs
concurrents dans une même fenêtre sont un symptôme, pas un défaut à corriger sur place. Chaque
destination porte donc le sien, et `PanneauLanceur` est le modèle.

## ⚠ La garde de travail non enregistré n'a pas bougé — et c'est voulu

`Fenetre.peut_quitter` est armée sur le changement de **tome**, pas sur le changement de
destination. Changer de destination ne détruit rien : le panneau vit dans un
`QStackedWidget`, ses brouillons et ses documents restent en mémoire. Le seul geste qui jette
du travail reste l'ouverture d'un AUTRE tome ici — et il passe toujours par la même boîte à
trois choix.

Le `PLAN-31` annonçait un trou à refermer par le `PLAN-35` L35.4 ; la mesure du lot 31 montre
qu'il ne s'ouvre pas, à condition que les combos de cette barre soient le seul chemin vers un
changement de tome de la retouche. Ils le sont : les lanceurs ont leurs propres listes et ne
touchent jamais au tome ouvert ici. C'est écrit dans `docs/mesures/coquille-2026-09-04.md`.

> ⚠ **MISE À JOUR 2026-09-05, lot 35.** Le constat ci-dessus tient, et il est maintenant
> **nommé et testé** plutôt que déduit : `gui/garde.py` porte les six chemins de perte de
> l'étape 0.2, chacun avec son verdict et son motif, et `Fenetre.peut_quitter(chemin)` est
> l'unique implémentation que les six appellent. « Changer de destination » y figure avec
> `perd_le_travail=False`, donc **aucune boîte**, même avec trente planches en attente : un
> dialogue qui se pose à chaque changement d'onglet est un dialogue qu'on apprend à cliquer
> sans lire.

## Ce que la destination ne devient pas — `PLAN-35` L35.6

Deux bornes, écrites ici parce que ce sera la tentation du prochain lot :

- **la retouche reste manga et webtoon.** Il n'y a pas d'éditeur light novel dans ce dépôt, et
  en esquisser un livrerait une demi-capacité. `gui.py` le dit déjà : « L'ÉDITION […] n'a de
  sens que sur des planches : elle reste au manga ». La liste des tomes le montre plutôt que
  de le taire — cf. `vue_retouche.phrase_tomes_absents` ;
- **la retouche n'invente aucun chemin de traitement.** Tout passe par `manga.edition`,
  `checkpoints.save_traduction_manuelle` et `process_volume(only_page=N,
  restart_from="rendu")` — c'est la promesse de `gui/__init__.py`, et c'est elle qui garantit
  qu'« un tome retouché ici se relance à l'identique avec `run_manga.py` ».
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from . import theme
from . import vue_retouche as vue
from .editeur import PanneauEditeur
from .modele_tome import lister_projets, lister_tomes, tomes_non_editables


class PanneauRetouche(QWidget):
    """La barre projet/tome et l'éditeur de planches, dans une seule destination."""

    #: Un tome a été choisi ici — la fenêtre construit le `Tome` et le `Services`.
    #: ⚠ Elle seule : « un `Services` par tome » et le `liberer()` du changement de tome ne
    #: tiennent que si un seul objet les décide.
    demande_tome = Signal(str, str)

    #: L'ordre de tabulation : la barre, puis l'éditeur, qui a le sien.
    #:
    #: ⚠ `etiquette_absents` et `etiquette_cache` n'y sont PAS, et c'est délibéré : ce sont
    #: des `QLabel` non focusables. Les inscrire au parcours ferait deux arrêts de tabulation
    #: sur du texte qu'un lecteur d'écran annonce déjà en passant.
    PARCOURS: tuple[str, ...] = ("choix_projet", "choix_tome", "bouton_projet", "editeur")

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        # ⚠ La même garde que la fenêtre portait : `setCurrentText` réémet
        # `currentTextChanged`, donc la demande, donc la boîte — qui se rouvrirait à l'infini.
        self._retour_de_garde = False
        self._construire()

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(theme.Espacement.XS)

        barre = QHBoxLayout()
        self.choix_projet = QComboBox()
        self.choix_projet.setAccessibleName("Projet")
        self.choix_projet.setMinimumWidth(240)
        self.choix_projet.currentTextChanged.connect(self._remplir_tomes)
        self.choix_tome = QComboBox()
        self.choix_tome.setAccessibleName("Tome")
        self.choix_tome.setMinimumWidth(160)
        self.choix_tome.currentTextChanged.connect(self._sur_tome)
        barre.addWidget(QLabel("Projet"))
        barre.addWidget(self.choix_projet)
        barre.addWidget(QLabel("Tome"))
        barre.addWidget(self.choix_tome)
        barre.addStretch(1)

        # L18.6 — l'indicateur de modification vit DANS le panneau, à côté du bouton qui
        # l'écrit. Il descend d'un cran avec la barre : il n'a jamais eu de sens ailleurs
        # qu'auprès des planches qu'il compte.
        self.etiquette_attente = QLabel("")
        theme.poser_role(self.etiquette_attente, "modifie")
        self.etiquette_attente.setAccessibleName("Travail non enregistré")
        self.etiquette_attente.setToolTip(
            "Travail retenu en mémoire, pas encore écrit sur le disque. Un miroir de "
            "récupération est écrit toutes les 30 s, mais seul un enregistrement le rend au "
            "pipeline.")
        barre.addWidget(self.etiquette_attente)
        self.bouton_projet = QPushButton("Enregistrer tout le tome")
        self.bouton_projet.setEnabled(False)
        barre.addWidget(self.bouton_projet)
        self.etiquette_revision = QLabel("—")
        self.etiquette_revision.setAccessibleName("Révision du tome sur le disque")
        theme.poser_role(self.etiquette_revision, "faible")
        barre.addWidget(self.etiquette_revision)
        colonne.addLayout(barre)

        # L35.1 — pourquoi la liste est plus courte que le dossier. ⚠ Elle n'apparaît que
        # quand il y a quelque chose à expliquer : une ligne permanente qui dit « tout est là »
        # est du décor, et le décor cesse d'être lu avant l'avertissement qu'il entoure.
        self.etiquette_absents = QLabel("")
        self.etiquette_absents.setWordWrap(True)
        self.etiquette_absents.setAccessibleName("Tomes non éditables de ce projet")
        theme.poser_role(self.etiquette_absents, "faible")
        self.etiquette_absents.setVisible(False)
        colonne.addWidget(self.etiquette_absents)

        self.editeur = PanneauEditeur()
        colonne.addWidget(self.editeur, 1)

        # L35.3 point 3 — la mémoire MESURÉE, affichée. Le dépôt annonçait 1,04 Mo par aperçu
        # et la mesure du 2026-09-05 en trouve 9,35 sur un tome paginé, 35,2 sur une bande :
        # c'est le seul chiffre du panneau que personne ne pouvait connaître autrement.
        self.etiquette_cache = QLabel("")
        self.etiquette_cache.setAccessibleName("Mémoire du cache d'aperçus")
        theme.poser_role(self.etiquette_cache, "faible")
        self.etiquette_cache.setVisible(False)
        colonne.addWidget(self.etiquette_cache)
        self._poser_parcours()

    def _poser_parcours(self) -> None:
        widgets = [getattr(self, nom) for nom in self.PARCOURS if hasattr(self, nom)]
        for avant, apres in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(avant, apres)

    # ------------------------------------------------------------------ #
    #  Les listes
    # ------------------------------------------------------------------ #

    def remplir_projets(self) -> list[str]:
        """(Re)lit `sources/` et remplit la liste. Rend les projets trouvés.

        ⚠ **Elle n'ouvre rien, et c'est tout l'objet du lot.** `addItems` fait partir
        `currentTextChanged` — c'est exactement la chaîne involontaire d'avant le lot 31, où
        remplir la liste ouvrait le premier projet par ordre alphabétique (`gui/fenetre.py`
        L421 et L443 de la 2.24.1). Les deux `blockSignals` la coupent : la liste se remplit,
        rien ne s'ouvre, et il faut un geste — un clic dans la liste, ou une carte
        « Reprendre » de l'accueil — pour qu'un tome le soit."""
        projets = lister_projets(self.config)
        self.choix_projet.blockSignals(True)
        self.choix_projet.clear()
        self.choix_projet.addItems(projets)
        self.choix_projet.blockSignals(False)
        self._remplir_tomes(self.choix_projet.currentText(), muet=True)
        return projets

    def _remplir_tomes(self, projet: str, *, muet: bool = False) -> None:
        self.choix_tome.blockSignals(True)
        self.choix_tome.clear()
        if projet:
            self.choix_tome.addItems(lister_tomes(self.config, projet))
        self.choix_tome.blockSignals(False)
        self._dire_les_absents(projet)
        if not muet:
            self._sur_tome(self.choix_tome.currentText())

    def _dire_les_absents(self, projet: str) -> None:
        """L35.1 — nomme les tomes que la retouche ne montre pas, et dit pourquoi."""
        absents = tomes_non_editables(self.config, projet) if projet else []
        phrase = vue.phrase_tomes_absents(absents)
        self.etiquette_absents.setText(phrase)
        self.etiquette_absents.setVisible(bool(phrase))

    def cible(self) -> tuple[str, str]:
        return self.choix_projet.currentText(), self.choix_tome.currentText()

    def viser(self, projet: str, tome: str) -> bool:
        """Pose la sélection sur un tome et demande son ouverture. `False` s'il est introuvable.

        C'est le chemin de la carte « Reprendre » de l'accueil. Il rend `False` plutôt que de
        lever : un tome supprimé depuis la dernière session est un cas normal, pas une panne,
        et l'accueil doit pouvoir le dire."""
        if self.choix_projet.findText(projet) < 0:
            self.remplir_projets()
        if self.choix_projet.findText(projet) < 0:
            return False
        self.choix_projet.blockSignals(True)
        self.choix_projet.setCurrentText(projet)
        self.choix_projet.blockSignals(False)
        self._remplir_tomes(projet, muet=True)
        if self.choix_tome.findText(tome) < 0:
            return False
        self.choix_tome.blockSignals(True)
        self.choix_tome.setCurrentText(tome)
        self.choix_tome.blockSignals(False)
        # ⚠ La demande est émise EXPLICITEMENT, et non laissée à `currentTextChanged`. Les
        # listes portent déjà le premier projet et son premier tome — c'est ce que
        # `remplir_projets` a posé sans rien ouvrir — donc viser ce couple-là ne change aucun
        # texte, donc n'émet aucun signal. « Reprendre » sur le premier tome par ordre
        # alphabétique n'aurait alors rien fait : le seul cas où l'ancien démarrage, lui,
        # marchait.
        self.demande_tome.emit(projet, tome)
        return True

    def restaurer(self, projet: str, tome: str) -> None:
        """Remet les listes sur le tome qu'on n'a pas quitté, sans rappeler la garde."""
        self._retour_de_garde = True
        if self.choix_projet.currentText() != projet:
            self.choix_projet.setCurrentText(projet)
        self._retour_de_garde = True
        self.choix_tome.setCurrentText(tome)
        self._retour_de_garde = False

    def _sur_tome(self, tome: str) -> None:
        projet = self.choix_projet.currentText()
        if not (projet and tome):
            return
        if self._retour_de_garde:
            self._retour_de_garde = False
            return
        self.demande_tome.emit(projet, tome)

    # ------------------------------------------------------------------ #

    def marquer_run(self, en_cours: bool) -> None:
        """Un run global grise le choix de tome — **pas le changement de destination**.

        Le comportement se déplace avec les combos, il ne disparaît pas : changer de tome
        pendant qu'un `process_volume` réécrit celui qui est ouvert donnerait deux vérités sur
        le même checkpoint."""
        self.choix_projet.setEnabled(not en_cours)
        self.choix_tome.setEnabled(not en_cours)

    def poser_revision(self, revision: int | None) -> None:
        self.etiquette_revision.setText(
            f"révision {revision}" if revision else "jamais traité")

    def rafraichir_cache(self) -> None:
        """Repeint la ligne de mémoire du cache d'aperçus — L35.3 point 3.

        ⚠ Appelée par la fenêtre à chaque aperçu prêt, jamais par un minuteur. Un chiffre de
        mémoire qui se rafraîchit tout seul deux fois par seconde est un chiffre qui clignote,
        et le dépôt a déjà tranché contre le clignotement dans le bandeau de run."""
        cache = self.editeur.cache
        ligne = vue.ligne_de_cache(len(cache), cache.octets, cache.plafond,
                                   len(self.editeur._fenetre_apercu))
        self.etiquette_cache.setText(ligne)
        self.etiquette_cache.setVisible(bool(ligne))
        if ligne:
            self.etiquette_cache.setToolTip(vue.infobulle_de_cache(
                len(cache), cache.octets, cache.plafond,
                getattr(self.editeur, "_fenetre_tenable", 0),
                getattr(self.editeur, "_fenetre_demandee", 0)))
