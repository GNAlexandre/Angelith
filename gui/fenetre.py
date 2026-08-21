# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Fenêtre principale : choix du tome, éditeur de planches, lanceur de runs, journal.

## Ce qu'elle possède, et pourquoi elle seule

Trois objets à durée de vie longue vivent ici et sont **injectés** dans les panneaux :

- **le fil de travail** (`FilDeTravail`) — un seul, créé une fois. Les panneaux lui soumettent
  des tâches, ils ne créent jamais de fil. C'est ce qui ferme les trois trous de concurrence
  de la 1.1.0 : plus de `QThread` écrasé, plus d'objet de signaux réassigné sous un fil vivant ;
- **les signaux** (`SignauxTravail`) — créés une fois eux aussi, pour la même raison ;
- **les modèles chauds** (`manga.services.Services`) — un par tome. Sans eux, chaque clic sur
  « Retraduire » reconstruisait les agents et rechargeait le glossaire YAML.

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
"""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QSplitter, QTabWidget, QVBoxLayout, QWidget)

from core import cli
from core.version import ETAT_BRIQUES, __version__
from manga import etat_planches
from manga.services import Services
from .editeur import SAUT_LIGNE, PanneauEditeur
from .lanceur import PanneauLanceur
from .modele_tome import Tome, lister_projets, lister_tomes
from .travailleur import (GENRE_ASSEMBLAGE, GENRE_RUN, FilDeLecture, FilDeTravail,
                          ReporterQt, SignauxTravail, Tache, build_dir_de, demander_arret,
                          tache_run)

_COULEURS = {"warn": QColor(220, 150, 40), "verbose": QColor(120, 170, 220),
             "stage": QColor(150, 200, 150), "info": QColor(210, 210, 210)}

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


def _liste(numeros, *, maximum: int = 8, majuscule: bool = False) -> str:
    """« la planche 12 », « les planches 12, 27 et 40 », « les planches 1, 2… et 30 autres ».

    Nommer les planches plutôt que les compter : « 5 planches en attente » n'apprend rien
    à qui cherche à savoir SI son travail sur la 27 est dedans. On plafonne quand même la
    liste — trente numéros dans une boîte de dialogue ne se lisent pas."""
    nums = sorted(int(n) for n in numeros)
    if not nums:
        return "aucune planche"
    tete = "L" if majuscule else "l"
    if len(nums) == 1:
        return f"{tete}a planche {nums[0]}"
    if len(nums) > maximum:
        reste = len(nums) - maximum
        visibles = ", ".join(str(n) for n in nums[:maximum])
        return (f"{tete}es planches {visibles} et {reste} autre"
                + ("s" if reste > 1 else ""))
    return (f"{tete}es planches " + ", ".join(str(n) for n in nums[:-1])
            + f" et {nums[-1]}")


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
        self.signaux.debut.connect(self._sur_debut)
        self.signaux.fin.connect(self._sur_fin)
        self.signaux.file.connect(self._sur_file)
        self.signaux.apercu_pret.connect(self._sur_apercu_pret)
        self.signaux.prechargement.connect(self._sur_prechargement)

        # `[*]` est l'emplacement où Qt insère la marque « modifié » (cf. `setWindowModified`).
        self.setWindowTitle(f"Angelith {__version__} [*]— brique manga : "
                            f"{ETAT_BRIQUES['manga']}")
        self.resize(1520, 960)
        self._construire()
        cfg_gui = (config.get("gui") or {}).get("apercu") or {}
        self.editeur.cache.plafond = max(1, int(cfg_gui.get("plafond_mo", 120))) * 1024 * 1024
        self.editeur.brancher(self.fil, None, self.fil_lecture,
                              fenetre=int(cfg_gui.get("fenetre", 10)))
        self.fil.start()
        self.fil_lecture.start()
        self._remplir_projets()

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)

        barre = QHBoxLayout()
        self.choix_projet = QComboBox()
        self.choix_projet.setMinimumWidth(240)
        self.choix_projet.currentTextChanged.connect(self._remplir_tomes)
        self.choix_tome = QComboBox()
        self.choix_tome.setMinimumWidth(160)
        self.choix_tome.currentTextChanged.connect(self._ouvrir_tome)
        barre.addWidget(QLabel("Projet"))
        barre.addWidget(self.choix_projet)
        barre.addWidget(QLabel("Tome"))
        barre.addWidget(self.choix_tome)
        barre.addStretch(1)
        self.bouton_projet = QPushButton("Enregistrer les modifications du projet")
        self.bouton_projet.setShortcut("Ctrl+Shift+S")
        self.bouton_projet.setToolTip(
            "Écrit toutes les planches en attente, relettre celles dont le rendu est périmé, "
            "puis réassemble le CBZ/PDF UNE seule fois.")
        self.bouton_projet.clicked.connect(self._enregistrer_projet)
        self.bouton_projet.setEnabled(False)
        barre.addWidget(self.bouton_projet)
        self.etiquette_file = QLabel("")
        barre.addWidget(self.etiquette_file)
        self.etiquette_prechargement = QLabel("")
        self.etiquette_prechargement.setStyleSheet("color: #7aa;")
        barre.addWidget(self.etiquette_prechargement)
        self.etiquette_revision = QLabel("—")
        barre.addWidget(self.etiquette_revision)
        layout.addLayout(barre)

        self.onglets = QTabWidget()
        self.editeur = PanneauEditeur()
        self.editeur.journal.connect(self._journaliser)
        self.editeur.demande_relettrage.connect(self._relettrer)
        self.editeur.etat_document.connect(self._marquer_modifie)
        self.lanceur = PanneauLanceur(self.config)
        self.lanceur.demande_run.connect(self._lancer_run)
        self.lanceur.demande_arret.connect(self._arreter_run)
        self.lanceur.demande_assemblage.connect(self._assembler)
        self.onglets.addTab(self.editeur, "Planches")
        self.onglets.addTab(self.lanceur, "Runs")

        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(5000)
        self.journal.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")

        # Le journal occupait 220 px en permanence pour un contenu qu'on ne lit qu'après un
        # incident. Il est replié au départ et se déplie tout seul au premier avertissement.
        self.separateur = QSplitter(Qt.Vertical)
        self.separateur.addWidget(self.onglets)
        self.separateur.addWidget(self.journal)
        self.separateur.setStretchFactor(0, 1)
        self.separateur.setSizes([940, 0])
        layout.addWidget(self.separateur, 1)

        self.barre_progres = QProgressBar()
        self.barre_progres.setTextVisible(True)
        self.barre_progres.setRange(0, 1)
        layout.addWidget(self.barre_progres)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Prêt.")
        self._construire_menu()

    def _construire_menu(self) -> None:
        fichier = self.menuBar().addMenu("&Fichier")
        action_config = QAction("Ouvrir config.yaml dans l'éditeur système", self)
        action_config.setToolTip(
            "L'interface ne réécrit jamais config.yaml : ses 800 lignes de commentaires en "
            "sont la documentation, et une réécriture automatique les effacerait.")
        action_config.triggered.connect(self._ouvrir_config)
        fichier.addAction(action_config)
        action_projet = QAction("Enregistrer les modifications du projet", self)
        action_projet.setShortcut("Ctrl+Shift+S")
        action_projet.triggered.connect(self._enregistrer_projet)
        fichier.addAction(action_projet)
        fichier.addSeparator()
        action_dossier = QAction("Ouvrir le dossier de build du tome", self)
        action_dossier.triggered.connect(self._ouvrir_build)
        fichier.addAction(action_dossier)
        action_journal = QAction("Afficher le journal", self)
        action_journal.setShortcut("Ctrl+J")
        action_journal.triggered.connect(self.deplier_journal)
        fichier.addAction(action_journal)
        action_gloss = QAction("Recharger le glossaire depuis le disque", self)
        action_gloss.setToolTip("À faire après avoir édité glossaire.yaml à la main : le "
                                "glossaire est gardé en mémoire pour ne pas le relire à "
                                "chaque bulle traduite.")
        action_gloss.triggered.connect(self._recharger_glossaire)
        fichier.addAction(action_gloss)
        fichier.addSeparator()
        quitter = QAction("Quitter", self)
        quitter.triggered.connect(self.close)
        fichier.addAction(quitter)

    # ------------------------------------------------------------------ #
    # Tome
    # ------------------------------------------------------------------ #

    def _remplir_projets(self) -> None:
        projets = lister_projets(self.config)
        self.choix_projet.clear()
        self.choix_projet.addItems(projets)
        if not projets:
            self._journaliser("warn", "Aucun projet manga trouvé sous sources/ — dépose des "
                                      "images ou un .cbz sous sources/<Projet>/<Tome>/manga/.")

    def _remplir_tomes(self, projet: str) -> None:
        self.choix_tome.clear()
        if projet:
            self.choix_tome.addItems(lister_tomes(self.config, projet))

    def _ouvrir_tome(self, tome: str) -> None:
        projet = self.choix_projet.currentText()
        if not (projet and tome):
            return
        if self.services is not None:
            self.services.liberer()
        self.tome = Tome(self.config, projet, tome)
        # Un `Services` par tome : deux tomes peuvent viser des endpoints différents, et un
        # porteur global rendrait le second silencieusement faux.
        self.services = Services(self.config, projet, reporter=ReporterQt(self.signaux))
        self.lanceur.viser(projet, tome)
        self.editeur.brancher(self.fil, self.services, self.fil_lecture)
        self.editeur.ouvrir(self.tome)
        self._maj_revision()
        self._journaliser("stage", f"{projet} / {tome} — "
                                   f"{len(self.tome.index_planches())} planche(s) en cache")

    def _maj_revision(self) -> None:
        if self.tome is None:
            return
        revision = self.tome.revision()
        self.etiquette_revision.setText(
            f"révision {revision}" if revision else "jamais traité")

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
        config = parametres["config"]
        # Un run lancé depuis l'onglet « Runs » peut réécrire n'importe quelle planche : on
        # ne sait pas lesquelles, donc on retombe sur le vidage complet. Remettre `None` ici
        # est ce qui empêche d'hériter de la liste d'un « Enregistrer le projet » précédent.
        self._planches_du_run = None
        self._cible_run = {k: parametres[k] for k in ("brique", "projet", "tome")}
        self._cible_run["config"] = config
        reporter = self._reporter_de_run(config, parametres["brique"],
                                         parametres["projet"], parametres["tome"])
        self.fil.soumettre(tache_run(reporter=reporter, **parametres))
        self.lanceur.marquer_en_cours(True)

    def _arreter_run(self) -> None:
        if self._cible_run is None:
            return
        demander_arret(self._cible_run["config"], self._cible_run["brique"],
                       self._cible_run["projet"], self._cible_run["tome"])
        self._journaliser("warn", "Arrêt demandé — le run s'arrêtera à la prochaine frontière "
                                  "propre (une planche, ou un lot entier si le lot > 1).")

    def _relettrer(self, planche: int, etape: str) -> None:
        """Bouton « Appliquer » de l'éditeur : un run sur UNE planche.

        `passes_volume=False` : le relevé terminologique, le dédoublonnage du glossariste et
        la fiche de contexte raisonnent à l'échelle du TOME. Les rejouer pour une planche
        isolée est du temps pur — et, dans le cas du glossariste, une réécriture complète du
        glossaire pour rien."""
        if self.tome is None:
            return
        config = copy.deepcopy(self.config)
        config.setdefault("options", {})["verbose"] = self.lanceur.verbose()
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

        ecrites, refusees = self.editeur.enregistrer_tout()
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
        config.setdefault("options", {})["verbose"] = self.lanceur.verbose()
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
        self.lanceur.marquer_en_cours(True)

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

    def _sur_debut(self, planche, genre: str, libelle: str) -> None:
        self._journaliser("stage", libelle)
        self.editeur.marquer_verrou(planche, libelle, True)
        if planche is None:
            self.choix_projet.setEnabled(False)
            self.choix_tome.setEnabled(False)

    def _sur_fin(self, planche, genre: str, succes: bool, message: str) -> None:
        self.editeur.marquer_verrou(planche, "", False)
        self._journaliser("info" if succes else "warn", message)
        self._liberer_reporters()
        if planche is None:
            self.choix_projet.setEnabled(True)
            self.choix_tome.setEnabled(True)
            self.lanceur.marquer_en_cours(False)
            self.barre_progres.setRange(0, 1)
            self.barre_progres.setValue(1 if succes else 0)
        self._maj_revision()
        # Une tâche a réécrit le disque : les aperçus qu'elle touche ne valent plus rien.
        #
        # ⚠ « Qu'elle touche », pas « tous ». Un run global vidait le cache entier, y compris
        # après un « Enregistrer le projet » qui n'avait relettré que trois planches : les ~21
        # aperçus de la fenêtre partaient avec, soit ~29 s de recomposition (1,37 s pièce) pour
        # rien. Le vidage complet reste le repli quand la liste est inconnue — un run lancé
        # depuis l'onglet « Runs » peut toucher n'importe quelle planche.
        if planche is not None:
            self.editeur.oublier_apercu(planche)
        elif self._planches_du_run is not None:
            for numero in self._planches_du_run:
                self.editeur.oublier_apercu(numero)
            self.editeur.rafraichir_pellicule(self._planches_du_run)
        else:
            self.editeur.cache.vider()
            self.editeur.cache_etats.vider()
        if planche is None:
            self._planches_du_run = None
        # La planche à l'écran vient peut-être d'être réécrite : on la relit, en gardant les
        # brouillons de saisie, qui n'appartiennent pas au disque.
        if planche is None or (self.editeur.planche
                               and planche == self.editeur.planche.index):
            self.editeur.rafraichir()

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
        self.editeur.apercu_pret(planche)

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
        self.bouton_projet.setEnabled(modifie or bool(self._planches_perimees()))

    # ------------------------------------------------------------------ #
    # Journal
    # ------------------------------------------------------------------ #

    def _journaliser(self, niveau: str, message: str) -> None:
        prefixes = {"warn": "⚠ ", "verbose": "⏱ ", "stage": "· ", "info": "  "}
        forme = QTextCharFormat()
        forme.setForeground(_COULEURS.get(niveau, _COULEURS["info"]))
        curseur = self.journal.textCursor()
        curseur.movePosition(QTextCursor.End)
        curseur.insertText(prefixes.get(niveau, "  ") + message + "\n", forme)
        self.journal.setTextCursor(curseur)
        if niveau in ("stage", "warn"):
            self.statusBar().showMessage(message, 8000)
        if niveau == "warn":
            self.deplier_journal()

    def deplier_journal(self) -> None:
        """Ouvre le journal s'il est replié — un avertissement qui n'est pas lu ne sert à rien."""
        tailles = self.separateur.sizes()
        if len(tailles) > 1 and tailles[1] < 40:
            hauteur = sum(tailles)
            self.separateur.setSizes([int(hauteur * 0.75), int(hauteur * 0.25)])

    def _avancer(self, courant: int, total: int) -> None:
        if total > 0:
            self.barre_progres.setRange(0, total)
            self.barre_progres.setValue(courant)
            self.barre_progres.setFormat("%v / %m  (%p%)")
        else:
            self.barre_progres.setRange(0, 0)          # indéterminé : un lot est en cours

    # ------------------------------------------------------------------ #

    def _ouvrir_config(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.chemin_config).resolve())))

    def _ouvrir_build(self) -> None:
        if self.tome is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        dossier = self.tome.build_dir
        if not dossier.exists():
            QMessageBox.information(self, "Rien à ouvrir",
                                    f"{dossier} n'existe pas encore — lance un run d'abord.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dossier.resolve())))

    def closeEvent(self, event) -> None:
        """Trois choses à ne pas perdre : les saisies non enregistrées **de tout le tome**,
        une tâche en cours, et la propreté d'un checkpoint à moitié écrit.

        ⚠ La 1.5.0 a fait passer l'éditeur d'UNE planche ouverte à N, mais cette méthode
        appelait encore `enregistrer_document()`, qui n'écrit que la planche AFFICHÉE : avec
        cinq planches modifiées, « Enregistrer et quitter » en sauvait une et jetait les
        quatre autres sans un mot — ni boîte, ni journal, ni trace."""
        attente = self.editeur.planches_modifiees()
        if attente:
            boite = QMessageBox(self)
            boite.setWindowTitle("Modifications non enregistrées")
            boite.setText(f"{_liste(attente, majuscule=True)} porte"
                          f"{'nt' if len(attente) > 1 else ''} des modifications non "
                          f"enregistrées.")
            boite.setInformativeText("Quitter sans enregistrer les abandonnera.")
            enregistrer = boite.addButton("Enregistrer et quitter", QMessageBox.AcceptRole)
            quitter = boite.addButton("Quitter sans enregistrer",
                                      QMessageBox.DestructiveRole)
            boite.addButton("Annuler", QMessageBox.RejectRole)
            boite.setDefaultButton(enregistrer)
            boite.exec()
            if boite.clickedButton() is enregistrer:
                ecrites, refusees = self.editeur.enregistrer_tout()
                if ecrites:
                    self._journaliser("info", f"{len(ecrites)} planche(s) enregistrée(s) : "
                                              f"{', '.join(str(n) for n in ecrites)}.")
                if refusees:
                    # Partir sur un refus muet serait le défaut qu'on corrige sous un autre
                    # nom : on annule la fermeture et on NOMME les planches en cause.
                    pluriel = len(refusees) > 1
                    QMessageBox.warning(
                        self, "Planches non enregistrées",
                        f"{_liste(refusees, majuscule=True)} n'{'ont' if pluriel else 'a'} pas "
                        f"pu être enregistrée{'s' if pluriel else ''} : un run "
                        f"{'les' if pluriel else "l'"}a réécrite{'s' if pluriel else ''} "
                        f"depuis son ouverture." + SAUT_LIGNE
                        + "La fermeture est annulée — ce travail est conservé.")
                    event.ignore()
                    return
            elif boite.clickedButton() is not quitter:
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
        self.fil_lecture.wait(2000)
        self.fil.arreter()
        self.fil.wait(3000)
        # Le fil est mort : plus personne n'écrira, on peut fermer sans condition.
        for reporter in self._reporters_ouverts:
            fermer = getattr(reporter, "close", None)
            if callable(fermer):
                fermer()
        self._reporters_ouverts.clear()
        if self.services is not None:
            self.services.liberer()
        event.accept()
