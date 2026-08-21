# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Panneau de lancement des runs — manga ET light novel.

## Pourquoi les deux briques ici, alors que l'éditeur ne connaît que le manga

Parce que « lancer un run » est le même geste des deux côtés : choisir un projet, un tome, une
étape de reprise, et regarder défiler un journal. Les deux orchestrateurs ont **la même
signature de retour** (`True` = terminé, `False` = arrêté proprement) et le même protocole de
`Reporter` — c'est ce qui rend un lanceur commun honnête plutôt que bricolé. L'ÉDITION, elle,
n'a de sens que sur des planches : elle reste au manga.

## Ce que le panneau ne réécrit pas

`config.yaml` n'est jamais modifié. Les réglages d'un run (taille de lot, raisonnement, étape
de reprise, planche unique, `--force`) sont des mutations du dictionnaire **en mémoire**,
exactement comme les drapeaux de `run_manga.py`. Les 800 lignes de commentaires du fichier sont
sa documentation ; un aller-retour `yaml.safe_dump` les effacerait toutes, et ce serait la
seule chose que l'interface aurait vraiment cassée.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from manga.orchestrator_manga import MAX_PLANCHES_LOT

# Étapes de reprise proposées, avec ce qu'elles coûtent réellement — l'information qui manque
# le plus quand on choisit dans un menu (cf. le tableau de coûts du README).
ETAPES_MANGA = [
    ("(tout, depuis le cache)", None, "reprend là où le tome en est"),
    ("rendu", "rendu", "relettrage seul — aucun appel LLM"),
    ("traduction", "traduction", "retraduit puis relettre"),
    ("terminologie", "terminologie", "relève les noms, retraduit, relettre"),
    ("ocr", "ocr", "relit le japonais puis tout l'aval"),
    ("sfx", "sfx", "texte hors bulle seulement"),
    ("nettoyage", "nettoyage", "revide les bulles puis relettre"),
    ("detection", "detection", "tout — modèle ONNX requis, des heures"),
]
ETAPES_LN = [
    ("(tout, depuis le cache)", None, "reprend là où le tome en est"),
    ("rendu", "rendu", "réassemble les formats de sortie"),
    ("mise_en_page", "mise_en_page", ""),
    ("correction", "correction", ""),
    ("traduction", "traduction", ""),
    ("terminologie", "terminologie", ""),
]


class PanneauLanceur(QWidget):
    """Choix du run à lancer. N'exécute rien lui-même : la fenêtre tient le fil."""

    demande_run = Signal(dict)
    demande_arret = Signal()
    demande_assemblage = Signal()

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self._construire()

    def _construire(self) -> None:
        layout = QVBoxLayout(self)

        cible = QGroupBox("Ce qui va tourner")
        forme = QFormLayout(cible)
        self.choix_brique = QComboBox()
        self.choix_brique.addItem("Manga", "manga")
        self.choix_brique.addItem("Light novel", "ln")
        self.choix_brique.currentIndexChanged.connect(self._remplir_etapes)
        self.etiquette_cible = QLabel("—")
        self.choix_etape = QComboBox()
        forme.addRow("Brique", self.choix_brique)
        forme.addRow("Tome", self.etiquette_cible)
        forme.addRow("Reprendre à", self.choix_etape)

        self.champ_page = QSpinBox()
        self.champ_page.setRange(0, 9999)
        self.champ_page.setSpecialValueText("toutes")
        self.champ_page.setToolTip("0 = tout le tome. Sinon, ne (re)traite que cette planche "
                                   "(ou ce chapitre côté light novel).")
        forme.addRow("Planche unique", self.champ_page)

        self.case_force = QCheckBox("--force (ignorer tout le cache)")
        self.case_dry = QCheckBox("--dry-run (aucun appel LLM de traduction)")
        # ⚠ Sans cette case, le canal verbose reste vide PAR CONSTRUCTION : toutes les lignes
        # de perf de l'orchestrateur sont gardées par `if verbose:`, et `perf.log` n'est même
        # pas ouvert. La 1.1.0 promettait le contraire dans ses docstrings.
        self.case_verbose = QCheckBox("--verbose (temps, tokens, vitesse — et perf.log)")
        self.case_verbose.setToolTip(
            "Écrit build/<projet>/<tome>/manga/perf.log, exactement comme en ligne de "
            "commande, et remplit le canal ⏱ du journal.")
        self.case_verbose.setChecked(True)
        forme.addRow(self.case_force)
        forme.addRow(self.case_dry)
        forme.addRow(self.case_verbose)
        layout.addWidget(cible)

        lot = QGroupBox("Traduction par lots (manga)")
        flot = QFormLayout(lot)
        self.champ_lot = QSpinBox()
        self.champ_lot.setRange(1, MAX_PLANCHES_LOT)
        self.champ_lot.setValue(int(((self.config.get("manga") or {}).get("lot")
                                     or {}).get("planches", 1)))
        self.champ_lot.setToolTip(
            "Planches par appel LLM. 1 = une planche, un appel. 20 fait 7 appels au lieu de "
            "131 sur un tome — mais l'unité d'arrêt propre ET l'unité de perte passent à 20.")
        self.choix_think = QComboBox()
        # ⚠ La PREMIÈRE entrée ne vaut pas `false` : elle ne pose pas la clé du tout. Poser
        # `think: false` écraserait la spec du modèle ET son `endpoint:` — c'est un
        # outrepassement, pas un défaut (cf. `_appliquer_reflexion_lot`). Le menu doit donc
        # pouvoir dire « n'y touche pas », sinon l'interface désactiverait en silence
        # l'endpoint « reflexion » de tout run lancé depuis elle.
        for libelle, valeur in [("selon config.yaml", None), ("désactivé", False),
                                ("low", "low"), ("medium", "medium"), ("high", "high")]:
            self.choix_think.addItem(libelle, valeur)
        self.choix_think.setToolTip(
            "Raisonnement du traducteur. Coûteux à une planche par appel ; c'est le lot qui "
            "le rend abordable, la trace étant payée une fois par lot.\n"
            "« selon config.yaml » ne touche à rien — les autres valeurs outrepassent aussi "
            "l'endpoint de l'agent.")
        flot.addRow("Planches par appel", self.champ_lot)
        flot.addRow("Raisonnement", self.choix_think)
        layout.addWidget(lot)

        boutons = QHBoxLayout()
        self.bouton_lancer = QPushButton("Lancer")
        self.bouton_lancer.clicked.connect(self._lancer)
        self.bouton_arreter = QPushButton("Arrêter proprement")
        self.bouton_arreter.setToolTip(
            "Écrit le fichier STOP — comme `--stop`. Le run s'arrête à la prochaine frontière "
            "propre et tout ce qui est fait est conservé.")
        self.bouton_arreter.setEnabled(False)
        self.bouton_arreter.clicked.connect(self.demande_arret.emit)
        self.bouton_assembler = QPushButton("Assembler CBZ/PDF")
        self.bouton_assembler.setToolTip("Réassemble les sorties depuis pages_out/, sans rien "
                                         "retraduire ni relettrer.")
        self.bouton_assembler.clicked.connect(self.demande_assemblage.emit)
        boutons.addWidget(self.bouton_lancer)
        boutons.addWidget(self.bouton_arreter)
        boutons.addWidget(self.bouton_assembler)
        layout.addLayout(boutons)
        layout.addStretch(1)

        self._remplir_etapes()

    # ------------------------------------------------------------------ #

    def _remplir_etapes(self) -> None:
        etapes = ETAPES_MANGA if self.brique() == "manga" else ETAPES_LN
        self.choix_etape.clear()
        for libelle, valeur, aide in etapes:
            self.choix_etape.addItem(f"{libelle}  —  {aide}" if aide else libelle, valeur)

    def brique(self) -> str:
        return self.choix_brique.currentData()

    def verbose(self) -> bool:
        """Lu aussi par le bouton « Appliquer » de l'éditeur : un relettrage doit laisser la
        même trace qu'un run, sinon `perf.log` raconte un tome à trous."""
        return self.case_verbose.isChecked()

    def viser(self, projet: str, tome: str) -> None:
        self._projet, self._tome = projet, tome
        self.etiquette_cible.setText(f"{projet} / {tome}")

    def marquer_en_cours(self, en_cours: bool) -> None:
        self.bouton_lancer.setEnabled(not en_cours)
        self.bouton_assembler.setEnabled(not en_cours)
        self.bouton_arreter.setEnabled(en_cours)

    # ------------------------------------------------------------------ #

    def _lancer(self) -> None:
        projet = getattr(self, "_projet", None)
        if not projet:
            return
        # Copie PROFONDE : les réglages de ce run ne doivent pas rester collés à la config
        # partagée avec l'éditeur, qui construit ses propres agents.
        config = copy.deepcopy(self.config)
        config.setdefault("options", {})["dry_run"] = self.case_dry.isChecked()
        config["options"]["verbose"] = self.case_verbose.isChecked()
        if self.brique() == "manga":
            lot = config["manga"].setdefault("lot", {})
            lot["planches"] = self.champ_lot.value()
            reflexion = self.choix_think.currentData()
            if reflexion is None:
                lot.pop("think", None)          # « selon config.yaml » : ne rien imposer
            else:
                lot["think"] = reflexion
        page = self.champ_page.value() or None
        self.demande_run.emit({
            "brique": self.brique(), "projet": projet, "tome": self._tome,
            "config": config, "force": self.case_force.isChecked(),
            "depuis": self.choix_etape.currentData(), "page": page,
        })
