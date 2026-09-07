# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'onglet **Atelier** — et son écran central n'est pas la galerie.

`PLAN-27` : « la forme de l'atelier est imposée par le déroulé en deux phases : l'écran
central de ce lot n'est pas la galerie, c'est **l'écran de relecture du prompt**. Une
interface qui enchaînerait les deux phases d'un seul bouton supprimerait la porte humaine,
donc la propriété qui rend cette brique défendable. »

Le panneau a donc **deux pages**, et on ne peut aller de la première à la seconde qu'en
passant par la phase 1 :

    ┌ Page 1 — le catalogue ───────────────────────────────────────────┐
    │ qui est illustrable · cadrage · combien d'images · graine        │
    │ la galerie de ce qui a été produit, garder / jeter               │
    │            [ Préparer la requête ]  → phase 1 (LLM)              │
    └──────────────────────────────────────────────────────────────────┘
                                    ↓
    ┌ Page 2 — la RELECTURE ───────────────────────────────────────────┐
    │ prompt éditable + original restaurable · prompt négatif + motifs │
    │ vignettes en DEUX groupes · source de chaque attribut · canaux   │
    │   [ Annuler ]              [ Valider et générer ] → phase 2      │
    └──────────────────────────────────────────────────────────────────┘

## La règle de couche, et c'est le piège de ce lot

`gui/__init__.py` : « toute la logique métier vit dans le module, en Python nu, et se teste
avec `pytest` sans que PySide6 soit installé. Ici on ne trouve que des fenêtres, des scènes et
des signaux. »

Un atelier attire naturellement la logique dans la fenêtre : la sélection du personnage, le
choix du cadrage, la file d'attente, le verdict de ressemblance. **Rien de cela n'est du Qt.**
Ce fichier ne décide donc rien :

| Ce qu'on pourrait croire ici | Où c'est vraiment |
|---|---|
| qui est illustrable, et pourquoi pas | `illustration/atelier.py:catalogue` |
| ce que l'écran de relecture montre | `illustration/relecture.py:ecrans` |
| la porte vers la phase 2 | `illustration/relecture.py:Porte` |
| garder / jeter / purger, l'inventaire, les trois verdicts en phrases | `illustration/galerie.py` |
| les trois phases de la progression | `illustration/progression.py` |
| quelle interface la mesure impose | `illustration/attente.py` |

## Pourquoi tous les imports de la brique sont TARDIFS et gardés

`tests/test_imports_briques.py` tenait jusqu'ici que **personne** n'importe `illustration/` :
« c'est ce qui rend la brique supprimable sans rien casser ». Un onglet d'atelier crée
forcément cette arête — mais la propriété qui compte, elle, se garde entièrement :

- **aucun import au niveau module.** Chaque import vit dans une méthode ou une fabrique ;
- **le panneau se construit sans la brique**, et affiche alors un état vide qui dit pourquoi ;
- `tests/test_gui_atelier.py` le prouve en rendant `illustration` inimportable puis en
  construisant la fenêtre entière.

C'est un affaiblissement réel de la propriété, il est écrit, et il est mesuré plutôt
qu'affirmé — voir `docs/mesures/atelier-illustration-2026-09-02.md`.

## Ce que la mesure impose à cette interface, et ce n'est pas un choix de goût

`illustration/attente.py` : la médiane relevée est de **103,7 s par image** (n = 4, RX 7900 XT)
et le pire cas de 1 524 s. La tranche du tableau de l'étape 0.1 est donc **« run par lot :
on lance, on revient »**, et le panneau la sert :

- il **annonce la fourchette avant** d'engager le GPU, comme `gui/lanceur.py:_confirmer` ;
- sa barre reste **indéterminée** tant qu'aucune image n'est terminée — il n'invente pas de
  pourcentage sur un coût qui varie d'un facteur 14,7 ;
- il compte en **images terminées**, jamais en pas de débruitage ;
- il distingue **préparation (LLM) / bascule de modèle / génération (image)**, parce qu'une
  barre bloquée qui ne dit pas ce qui occupe la carte est un défaut d'information.
"""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from core import modeles as mod

from . import formulaire as frm
from . import parametres as par
from . import theme
from .travailleur import GENRE_ILLUSTRATION, Tache

#: Côté d'une vignette de la galerie et de l'écran de relecture, en pixels.
COTE_VIGNETTE = 120

#: Le badge que porte **toute** image produite, et il n'est pas masquable — critère 4 de
#: L27.1. Il n'y a ni case à cocher, ni réglage, ni raccourci pour l'éteindre : la seule
#: façon de ne pas le voir est de ne pas ouvrir l'onglet.
BADGE_IA = "⚙ générée par IA"

#: Les trois cadrages, avec ce qu'ils veulent dire. Recopiés de `illustration/console.py` —
#: c'est la même liste, et un test vérifie qu'elles ne divergent pas.
CADRAGES = (("visage", "gros plan sur le visage"),
            ("buste", "buste, à mi-corps — le défaut mesuré"),
            ("pied", "en pied, le personnage entier"))

#: Pastilles d'état d'un personnage. Elles reprennent `illustration/atelier.py` mot pour mot.
PASTILLES = {"pret": ("●", "succes", "référence validée — prêt à illustrer"),
             "a_relire": ("◐", "avertissement",
                          "référence proposée, non validée — à relire avant de générer"),
             "hors_atteinte": ("○", "faible", "sans référence utilisable")}


def brique_absente() -> str:
    """`""` si la brique est importable, sinon le motif — pour l'état vide.

    ⚠ Le seul point d'entrée vers `illustration/`, et il est **tardif et gardé**. Voir
    §« Pourquoi tous les imports de la brique sont tardifs » dans la docstring du module."""
    try:
        from illustration import atelier            # noqa: F401
        from illustration import relecture          # noqa: F401
    except Exception as err:                        # noqa: BLE001 — état vide, pas une panne
        return f"{type(err).__name__} : {err}"
    return ""


# ──────────────────────────────  Les deux tâches  ──────────────────────────────

def tache_preparation(*, config: dict, projet: str, tome: str | None, personnage: str,
                      cadrage: str, nombre: int, graine, reporter, deposer) -> Tache:
    """**Phase 1** : le LLM choisit les images et remplit `requete.yaml`. Aucun poids d'image.

    Le résultat déposé est une `relecture.Porte` — c'est-à-dire l'écran, pas le fichier. Le
    panneau n'a donc aucun moyen d'atteindre la phase 2 sans elle."""

    def _travail():
        from illustration import orchestrateur
        from illustration import relecture
        from illustration import requete as requete_mod

        recap = orchestrateur.phase_prompt(
            projet, config, tome=tome or None, personnages=[personnage] if personnage else None,
            ecraser=True, cadrage=cadrage, graine=graine, reporter=reporter)
        doc = requete_mod.load(recap["requete"])
        for bloc in doc["images"]:
            bloc["nombre_images"] = max(1, int(nombre))
        porte = relecture.Porte(
            doc, racine_projet=orchestrateur.racine_projet(config, projet))
        deposer({"porte": porte, "chemin": recap["requete"],
                 "secondes": recap["secondes"], "appels": recap["appels_llm"]})
        return (f"Requête prête : {recap['images']} image(s) à relire "
                f"({recap['secondes']:.1f} s, {recap['appels_llm']} appel(s) au modèle de "
                f"vision).")

    return Tache(genre=GENRE_ILLUSTRATION, fonction=_travail, planche=None,
                 libelle=f"Préparation de la requête — {personnage or projet}")


def tache_generation(*, config: dict, projet: str, tome: str | None, porte, chemin_requete,
                     chemin_config: str, reporter, avancement, annulation, deposer) -> Tache:
    """**Phase 2** : la bascule VRAM et les PNG marqués. **Le seul chemin vers `phase_image`.**

    ⚠ `porte.laissez_passer()` est appelé **avant** tout, et il lève tant que l'écran de
    relecture n'a pas été franchi. C'est le critère 1 bis du `PLAN-27` — « un test vérifie
    qu'aucun chemin de l'interface ne peut lancer la phase 2 sans passage par cet écran » — et
    il se vérifie de deux façons : à l'exécution ici, et statiquement par
    `tests/test_illustration_relecture.py`, qui lit ce fichier avec `ast` et refuse que
    `phase_image` apparaisse dans une fonction qui ne nomme pas `laissez_passer`.

    ⚠ `porte.verifier_le_disque` refuse ensuite si `requete.yaml` a bougé depuis que l'écran a
    été ouvert : le fichier est fait pour être édité à la main, et l'atelier console peut
    l'avoir réécrit dans une autre fenêtre."""

    def _travail():
        from illustration import orchestrateur

        porte.laissez_passer()
        porte.verifier_le_disque(chemin_requete)
        recap = orchestrateur.phase_image(
            projet, config, tome=tome or None, reporter=reporter,
            chemin_config=chemin_config, avancement=avancement, annulation=annulation)
        deposer({"recap": recap})
        images = recap.get("images") or []
        arret = recap.get("arret") or ""
        return (f"{len(images)} image(s) écrite(s) et marquée(s) dans {recap['dossier']}."
                + (f" {arret}" if arret else ""))

    return Tache(genre=GENRE_ILLUSTRATION, fonction=_travail, planche=None,
                 libelle=f"Génération — {projet}")


# ─────────────────────────────────  Le panneau  ─────────────────────────────────

class PanneauAtelier(QWidget):
    """Deux pages, une porte entre les deux. N'exécute rien : la fenêtre tient le fil."""

    journal = Signal(str, str)
    demande_tache = Signal(object)
    demande_bible = Signal(str)
    demande_dossier = Signal(str)

    def __init__(self, config: dict, chemin_config: str = "config.yaml", parent=None):
        super().__init__(parent)
        self.config = config
        self.chemin_config = chemin_config
        self._fiches: list = []
        self._porte = None
        self._chemin_requete = None
        self._avancement = None
        self._annulation = False
        self._resultat: dict = {}
        self._pieces: list = []
        self._arme = False
        self._catalogue_modeles = mod.inconnu()
        self.formulaire = frm.Formulaire(par.ILLUSTRATIONS,
                                         choix=self._choix_dynamiques())
        self._construire()
        self._remplir_projets()

    def _choix_dynamiques(self) -> dict:
        """Les seules entrées que la table ne peut pas geler : les modèles du serveur."""
        return {"modele": self._entrees_modeles()}

    def _entrees_modeles(self) -> tuple[tuple[str, object], ...]:
        entrees: list[tuple[str, object]] = [("selon config.yaml", None)]
        for modele in self._catalogue_modeles.modeles:
            entrees.append((modele.ligne(), modele.identifiant))
        return tuple(entrees)

    def poser_modeles(self, catalogue) -> None:
        """Reçoit le verdict de la sonde de modèles — **calculée dans le fil de travail**.

        ⚠ L'atelier reçoit la même liste que les lanceurs, et pour la même raison : la phase
        « prompt » de l'illustration passe par `cli.models_in_config(config)` sans section,
        donc par les agents de la RACINE de `config.yaml`. C'est le même endpoint, les mêmes
        modèles, et deux listes seraient deux vérités."""
        self._catalogue_modeles = catalogue
        self.formulaire.reposer_choix("modele", self._entrees_modeles())

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        layout = QVBoxLayout(self)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_catalogue())
        self.pages.addWidget(self._page_relecture())
        layout.addWidget(self.pages, 1)
        self.etiquette_phase = QLabel("")
        theme.poser_role(self.etiquette_phase, "faible")
        self.etiquette_phase.setAccessibleName("Phase du run d'illustration")
        layout.addWidget(self.etiquette_phase)
        self._poser_parcours()

    # -- Page 1 : le catalogue ----------------------------------------- #

    def _page_catalogue(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.bandeau = QLabel("")
        self.bandeau.setWordWrap(True)
        theme.poser_role(self.bandeau, "avertissement")
        self.bandeau.setAccessibleName("État de la brique d'illustration")
        layout.addWidget(self.bandeau)

        haut = QHBoxLayout()
        cible = QGroupBox("Ce qu'on illustre")
        forme = QFormLayout(cible)
        self.choix_projet = QComboBox()
        self.choix_projet.setMinimumWidth(220)
        self.choix_projet.currentTextChanged.connect(self._sur_projet)
        forme.addRow("Œuvre", self.choix_projet)

        self.liste_personnages = QListWidget()
        self.liste_personnages.setAccessibleName("Personnages illustrables")
        self.liste_personnages.setMinimumHeight(160)
        self.liste_personnages.currentRowChanged.connect(self._sur_personnage)
        forme.addRow("Personnage", self.liste_personnages)

        self.choix_cadrage = QComboBox()
        for nom, quoi in CADRAGES:
            self.choix_cadrage.addItem(f"{nom} — {quoi}", nom)
        self.choix_cadrage.setToolTip(
            "Le cadrage ne vient jamais du texte : c'est ton choix. Le défaut est celui que "
            "le lot 25 a mesuré comme le meilleur (illustration.prompt.cadrage).")
        forme.addRow("Cadrage", self.choix_cadrage)

        # ⚠ **Ces trois lignes viennent de `gui/parametres.py`, comme celles des trois
        # lanceurs** — `PLAN-33` L33.1, « la même déclaration de paramètres là où ses
        # paramètres sont de même nature (modèle, graine, nombre d'images), et rien de plus ».
        # L'atelier n'est PAS démembré pour autant : `construire_dans` pose les lignes dans SA
        # mise en page, sans lui imposer les groupes du lanceur.
        self.formulaire.construire_dans(self, forme, "image")
        self.formulaire.construire_dans(self, forme, "modele")
        # L'annonce de coût suit le nombre d'images : une fourchette qui ne bouge pas quand on
        # passe de 1 à 8 est pire qu'aucune fourchette.
        self.champ_nombre.valueChanged.connect(lambda _v: self._peindre_cout())
        haut.addWidget(cible, 1)

        etat = QGroupBox("Ce que ça va coûter")
        vetat = QVBoxLayout(etat)
        self.etiquette_cout = QLabel("")
        self.etiquette_cout.setWordWrap(True)
        theme.poser_role(self.etiquette_cout, "faible")
        vetat.addWidget(self.etiquette_cout)
        self.etiquette_inventaire = QLabel("")
        theme.poser_role(self.etiquette_inventaire, "mono")
        vetat.addWidget(self.etiquette_inventaire)
        vetat.addStretch(1)
        haut.addWidget(etat, 1)
        layout.addLayout(haut)

        boutons = QHBoxLayout()
        self.bouton_preparer = QPushButton("Préparer la requête…")
        self.bouton_preparer.setToolTip(
            "Phase 1 : le modèle de vision choisit les images de référence et la requête est "
            "écrite. AUCUNE image n'est produite — l'écran de relecture s'ouvre ensuite.")
        self.bouton_preparer.clicked.connect(self._preparer)
        self.bouton_bible = QPushButton("Ouvrir la bible…")
        self.bouton_bible.setToolTip(
            "100 % des refus de génération se règlent là : c'est la bible visuelle qui dit à "
            "quoi ressemble un personnage, et quelles images d'un humain l'ont validé.")
        self.bouton_bible.clicked.connect(
            lambda: self.demande_bible.emit(self.choix_projet.currentText()))
        self.bouton_arreter = QPushButton("Arrêter proprement")
        self.bouton_arreter.setEnabled(False)
        self.bouton_arreter.setToolTip(
            "L'arrêt a lieu ENTRE deux images, jamais au milieu de l'une : un modèle "
            "interrompu en plein débruitage laisse le pilote dans un mauvais état — mesuré, "
            "25 → 18 tok/s sur la traduction suivante. Les images déjà écrites sont gardées.")
        self.bouton_arreter.clicked.connect(self._arreter)
        boutons.addWidget(self.bouton_preparer)
        boutons.addWidget(self.bouton_bible)
        boutons.addWidget(self.bouton_arreter)
        boutons.addStretch(1)
        layout.addLayout(boutons)

        galerie = QGroupBox("Galerie — ce qui a été produit")
        vgalerie = QVBoxLayout(galerie)
        self.zone_galerie = QScrollArea()
        self.zone_galerie.setWidgetResizable(True)
        self.zone_galerie.setMinimumHeight(200)
        self.zone_galerie.setAccessibleName("Images produites")
        self.contenu_galerie = QWidget()
        self.grille_galerie = QGridLayout(self.contenu_galerie)
        self.zone_galerie.setWidget(self.contenu_galerie)
        vgalerie.addWidget(self.zone_galerie)
        gestes = QHBoxLayout()
        self.bouton_purger = QPushButton("Purger les rejetées…")
        self.bouton_purger.setToolTip(
            "Un rejet est une DONNÉE : jeter déplace, ne supprime pas. La purge est un geste "
            "séparé, et elle annonce ce qu'elle va détruire.")
        self.bouton_purger.clicked.connect(self._purger)
        self.bouton_dossier = QPushButton("Ouvrir le dossier")
        self.bouton_dossier.clicked.connect(
            lambda: self.demande_dossier.emit(self.choix_projet.currentText()))
        gestes.addWidget(self.bouton_purger)
        gestes.addWidget(self.bouton_dossier)
        gestes.addStretch(1)
        vgalerie.addLayout(gestes)
        layout.addWidget(galerie, 1)
        return page

    # -- Page 2 : la relecture ----------------------------------------- #

    def _page_relecture(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        titre = QLabel("Relecture du prompt — rien n'est généré tant que tu n'as pas validé")
        theme.poser_role(titre, "titre")
        layout.addWidget(titre)

        self.etiquette_anomalies = QLabel("")
        self.etiquette_anomalies.setWordWrap(True)
        theme.poser_role(self.etiquette_anomalies, "avertissement")
        self.etiquette_anomalies.setAccessibleName("Anomalies de la requête")
        layout.addWidget(self.etiquette_anomalies)

        zone = QScrollArea()
        zone.setWidgetResizable(True)
        contenu = QWidget()
        self.corps_relecture = QVBoxLayout(contenu)
        zone.setWidget(contenu)
        layout.addWidget(zone, 1)

        self.champ_valideur = QComboBox()
        self.champ_valideur.setEditable(True)
        self.champ_valideur.setMinimumWidth(220)
        self.champ_valideur.setToolTip(
            "Ce nom part dans le sidecar de CHAQUE image : c'est ce qui distingue « assisté » "
            "de « généré ». Il n'a pas de défaut, et « validé par (vide) » ne montre rien.")
        bas = QHBoxLayout()
        bas.addWidget(QLabel("Validé par"))
        bas.addWidget(self.champ_valideur)
        bas.addStretch(1)
        self.bouton_annuler = QPushButton("Annuler")
        self.bouton_annuler.setToolTip(
            "Rien n'est détruit : requete.yaml reste sur le disque, `valide` reste à false, "
            "et le travail du modèle de vision n'est pas perdu.")
        self.bouton_annuler.clicked.connect(self._annuler_relecture)
        self.bouton_valider = QPushButton("Valider et générer")
        self.bouton_valider.clicked.connect(self._valider)
        bas.addWidget(self.bouton_annuler)
        bas.addWidget(self.bouton_valider)
        layout.addLayout(bas)
        return page

    #: Ordre de tabulation — déclaré, comme l'exige le critère 6 du `PLAN-19`, et non laissé
    #: au hasard de l'ordre de construction.
    PARCOURS: tuple[str, ...] = (
        "choix_projet", "liste_personnages", "choix_cadrage", "champ_nombre",
        "champ_graine", "choix_modele", "bouton_preparer", "bouton_bible", "bouton_arreter",
        "bouton_purger", "bouton_dossier",
        "champ_valideur", "bouton_annuler", "bouton_valider",
    )

    def _poser_parcours(self) -> None:
        widgets = [getattr(self, nom) for nom in self.PARCOURS if hasattr(self, nom)]
        for avant, apres in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(avant, apres)

    # ------------------------------------------------------------------ #
    # Page 1 — remplir
    # ------------------------------------------------------------------ #

    def _remplir_projets(self) -> None:
        motif = brique_absente()
        if motif:
            self._etat_vide_brique(motif)
            return
        from illustration import orchestrateur

        reg = orchestrateur.reglages(self.config)
        self._peindre_bandeau(reg)
        racine = Path(self.config["chemins"]["sources"])
        projets = sorted(p.name for p in racine.iterdir() if p.is_dir()) \
            if racine.is_dir() else []
        self.choix_projet.blockSignals(True)
        self.choix_projet.clear()
        self.choix_projet.addItems(projets)
        self.choix_projet.blockSignals(False)
        self._sur_projet(self.choix_projet.currentText())

    def _etat_vide_brique(self, motif: str) -> None:
        """L'état vide est un ÉCRAN, pas un aplat gris — la leçon explicite du `PLAN-18`."""
        self.bandeau.setText(
            "La brique d'illustration n'est pas disponible dans cette installation.\n"
            f"  {motif}\n"
            "  L'onglet reste ouvert et le reste de l'application fonctionne normalement : "
            "cette brique est une feuille, on peut supprimer son dossier sans rien casser.")
        for bouton in (self.bouton_preparer, self.bouton_bible, self.bouton_purger,
                       self.bouton_dossier):
            bouton.setEnabled(False)

    def _peindre_bandeau(self, reg: dict) -> None:
        """Ce qui est armé, **avant** la première question — repris de l'atelier console.

        ⚠ Le croisement `identite.actif` × `comfyui.workflow` est ici parce que le refus
        arrivait sinon au moment de générer, c'est-à-dire après avoir choisi son personnage et
        relu cinq images. Constaté à l'usage le 2026-08-31."""
        from illustration import atelier as atelier_mod

        lignes = []
        if not reg["actif"]:
            lignes.append("Brique DÉSARMÉE (illustration.actif: false) — c'est le défaut "
                          "livré. Rien ne sera généré tant que la clé n'est pas à true.")
        if reg["moteur"] == "factice":
            lignes.append("Moteur « factice » : un carré uni, aucun modèle. Il vérifie la "
                          "chaîne, pas l'image.")
        for canal in atelier_mod.canaux_manquants(reg, self._canaux_du_moteur(reg)):
            lignes.append(f"Le canal « {canal} » est armé mais le moteur ne l'honore pas. "
                          + atelier_mod.remede_canal(canal, reg["comfyui"]["workflow"]))
        self.bandeau.setText("\n".join(f"⚠ {ligne}" for ligne in lignes))
        self.bandeau.setVisible(bool(lignes))
        self._arme = bool(reg["actif"])
        self.bouton_preparer.setEnabled(self._arme)
        # ⚠ **Le défaut du cadrage vient de la configuration, pas de l'ordre de la liste.**
        # L27.1 point 2 : « défaut = celui que le PLAN-25 L25.1 a mesuré comme le meilleur ».
        # Laisser « visage » gagner parce qu'il est premier dans le tuple ferait sortir un
        # gros plan là où la mesure recommande un buste, sans que personne ne l'ait demandé.
        index = self.choix_cadrage.findData(reg["prompt"]["cadrage"])
        if index >= 0:
            self.choix_cadrage.setCurrentIndex(index)

    @staticmethod
    def _canaux_du_moteur(reg: dict):
        """Aucun serveur n'est contacté : le graphe déclare ses marqueurs dans son fichier."""
        if reg["moteur"] != "comfyui" or not reg["comfyui"]["workflow"]:
            return ()
        try:
            from illustration.comfyui import MoteurComfyUI
            return MoteurComfyUI(reg["comfyui"]["workflow"]).CANAUX_SUPPORTES
        except Exception:                            # noqa: BLE001 — diagnostic seulement
            return ()

    def _sur_projet(self, projet: str) -> None:
        if brique_absente() or not projet:
            return
        from core import bible as bible_mod
        from illustration import atelier as atelier_mod
        from illustration import orchestrateur

        dossier_projet = orchestrateur.dossier_projet(self.config, projet)
        bible_doc = bible_mod.load(bible_mod.chemin(dossier_projet))
        propositions = self._propositions(dossier_projet)
        glossaire = orchestrateur._glossaire(self.config, projet, lambda _m: None)
        racine = orchestrateur.racine_projet(self.config, projet)
        self._fiches = atelier_mod.catalogue(bible_doc, glossaire, racine,
                                             propositions=propositions)
        self._peindre_personnages()
        self._peindre_galerie(projet)
        self._peindre_cout()

    @staticmethod
    def _propositions(dossier_projet) -> dict:
        import yaml

        from core import bible as bible_mod
        chemin = bible_mod.chemin_propositions(dossier_projet)
        if not chemin.is_file():
            return {}
        try:
            return bible_mod.fill_defaults(
                yaml.safe_load(chemin.read_text(encoding="utf-8")) or {})
        except (OSError, ValueError):
            return {}

    def _peindre_personnages(self) -> None:
        """Un personnage sans référence validée est **grisé et non cliquable**, avec
        l'infobulle qui dit quoi faire — critère 2 du `PLAN-27`.

        ⚠ Aucune génération ne part et **aucun message d'erreur n'apparaît après le clic** :
        `illustration/identite.py` refuse déjà de générer sans référence validée, et
        l'interface doit le dire AVANT, pas après."""
        from illustration import atelier as atelier_mod

        self.liste_personnages.clear()
        if not self._fiches:
            item = QListWidgetItem(
                "Aucun personnage n'a de référence visuelle validée.\n"
                "→ « Ouvrir la bible… » : c'est là que ça se règle.")
            item.setFlags(Qt.NoItemFlags)
            self.liste_personnages.addItem(item)
            return
        for fiche in self._fiches:
            marque, _role, aide = PASTILLES[fiche.etat]
            item = QListWidgetItem(f"{marque}  {fiche.nom}   —   {fiche.resume()}")
            item.setData(Qt.UserRole, fiche.nom)
            if fiche.etat == atelier_mod.HORS_ATTEINTE:
                item.setFlags(Qt.NoItemFlags)
                motifs = " · ".join(atelier_mod.MOTIFS[m] for m in fiche.motifs)
                item.setToolTip(
                    f"{motifs}.\n"
                    f"→ python tools/bible.py \"…\" --proposer puis --revue, ou "
                    f"« Ouvrir la bible… » ci-dessous. Tant que ce personnage n'a ni "
                    f"attribut cité ni image candidate, la phase 2 refuserait de générer.")
            else:
                item.setToolTip(aide)
            self.liste_personnages.addItem(item)
        for rang in range(self.liste_personnages.count()):
            if self.liste_personnages.item(rang).flags() != Qt.NoItemFlags:
                self.liste_personnages.setCurrentRow(rang)
                break

    def _sur_personnage(self, _rang: int) -> None:
        self._peindre_cout()

    def _peindre_cout(self) -> None:
        """La fourchette mesurée, **avant** d'engager le GPU. Jamais un temps unique."""
        if brique_absente():
            return
        from illustration import attente

        self.etiquette_cout.setText(attente.annonce(self.champ_nombre.value()))

    def _peindre_galerie(self, projet: str) -> None:
        from illustration import galerie as galerie_mod
        from illustration import orchestrateur

        for i in reversed(range(self.grille_galerie.count())):
            widget = self.grille_galerie.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        inventaire = galerie_mod.inventorier(
            orchestrateur.dossier(self.config, projet),
            orchestrateur.dossier_retenues(self.config, projet))
        self._pieces = list(inventaire.pieces)
        self.etiquette_inventaire.setText("\n".join(inventaire.resume()))
        candidates = [p for p in self._pieces if p.etat != galerie_mod.REJETEE]
        if not candidates:
            vide = QLabel("Aucune image produite pour cette œuvre.\n"
                          "« Préparer la requête… » ouvre l'écran de relecture ; c'est lui "
                          "qui mène à la génération, et il n'y a pas d'autre chemin.")
            vide.setWordWrap(True)
            theme.poser_role(vide, "faible")
            self.grille_galerie.addWidget(vide, 0, 0)
            return
        for index, piece in enumerate(candidates):
            self.grille_galerie.addWidget(self._carte(piece, projet), index // 4, index % 4)

    def _carte(self, piece, projet: str) -> QWidget:
        """Une vignette, **ses trois verdicts** et le badge non masquable — critère 4."""
        from illustration import galerie as galerie_mod

        carte = QFrame()
        carte.setFrameShape(QFrame.StyledPanel)
        vbox = QVBoxLayout(carte)
        image = QLabel()
        image.setPixmap(_vignette(piece.chemin))
        image.setAlignment(Qt.AlignCenter)
        vbox.addWidget(image)

        badge = QLabel(BADGE_IA)
        theme.poser_role(badge, "avertissement")
        badge.setToolTip("Le PNG porte un bloc tEXt `AIGenerated=true` et un sidecar de "
                         "provenance. Ce badge n'a pas d'interrupteur.")
        vbox.addWidget(badge)

        nom = QLabel(piece.chemin.name)
        theme.poser_role(nom, "faible")
        nom.setWordWrap(True)
        vbox.addWidget(nom)
        # ⚠ Les trois verdicts sont mis en phrases par `galerie.verdicts`, en Python nu :
        # décider de ce qui s'affiche est une décision, et la règle de couche veut que tout
        # ce qui décide se teste sans Qt.
        for ligne in galerie_mod.verdicts(piece):
            etiquette = QLabel(ligne)
            theme.poser_role(etiquette, "faible")
            etiquette.setWordWrap(True)
            vbox.addWidget(etiquette)

        if piece.etat == galerie_mod.CANDIDATE:
            gestes = QHBoxLayout()
            garder = QPushButton("Garder")
            garder.setToolTip(
                "Déplace l'image et son sidecar sous sources/<Projet>/illustrations/, qui "
                "survit à un `rm -r build/`. Une image de 103,7 s de GPU n'est PAS "
                "régénérable : la même graine sur une autre révision ne rend pas la même "
                "image.")
            garder.clicked.connect(lambda _=False, p=piece: self._garder(p, projet))
            jeter = QPushButton("Jeter")
            jeter.setToolTip("Déplace dans rejetees/. Ne supprime rien : un rejet est une "
                             "donnée de mesure.")
            jeter.clicked.connect(lambda _=False, p=piece: self._jeter(p, projet))
            gestes.addWidget(garder)
            gestes.addWidget(jeter)
            vbox.addLayout(gestes)
        else:
            etat = QLabel("retenue — sous sources/")
            theme.poser_role(etat, "succes")
            vbox.addWidget(etat)
        return carte

    # ------------------------------------------------------------------ #
    # Page 1 — les gestes
    # ------------------------------------------------------------------ #

    def _garder(self, piece, projet: str) -> None:
        from illustration import galerie as galerie_mod
        from illustration import orchestrateur

        try:
            image, _manifeste = galerie_mod.garder(
                piece.chemin, orchestrateur.dossier_retenues(self.config, projet))
        except galerie_mod.GesteImpossible as err:
            QMessageBox.warning(self, "Garder", str(err))
            return
        self.journal.emit("info", f"gardée : {image}")
        self._inscrire_dans_la_bible(piece, image, projet)
        self._peindre_galerie(projet)

    def _inscrire_dans_la_bible(self, piece, image, projet: str) -> None:
        """Note l'image sous `images_generees[]` — **jamais** sous `references[]`.

        ⚠ C'est le point le plus important du lot : reboucler une sortie dans l'entrée fait
        dériver le personnage à chaque tour, et la dérive est invisible image par image. La
        séparation n'est pas une convention d'appelant, c'est `galerie.inscrire` qui n'a
        aucun argument permettant l'inverse."""
        from core import bible as bible_mod
        from illustration import galerie as galerie_mod
        from illustration import orchestrateur

        if not piece.personnage:
            return
        chemin = bible_mod.chemin(orchestrateur.dossier_projet(self.config, projet))
        bible_doc = bible_mod.load(chemin)
        try:
            modifiee, combien = galerie_mod.inscrire(
                bible_doc, piece.personnage, image, cadrage=piece.cadrage,
                par=self.champ_valideur.currentText().strip())
        except galerie_mod.GesteImpossible as err:
            self.journal.emit("warn", f"bible : {err}")
            return
        if combien:
            bible_mod.save(modifiee, chemin)
            self.journal.emit("info", f"bible : {piece.chemin.name} notée sous "
                                      f"images_generees[] de « {piece.personnage} » — "
                                      f"jamais candidate à une génération suivante.")

    def _jeter(self, piece, projet: str) -> None:
        from illustration import galerie as galerie_mod
        from illustration import orchestrateur

        try:
            cible, _ = galerie_mod.jeter(piece.chemin,
                                         orchestrateur.dossier_rejetees(self.config, projet))
        except galerie_mod.GesteImpossible as err:
            QMessageBox.warning(self, "Jeter", str(err))
            return
        self.journal.emit("info", f"jetée (conservée) : {cible}")
        self._peindre_galerie(projet)

    def _purger(self) -> None:
        from illustration import galerie as galerie_mod
        from illustration import orchestrateur

        projet = self.choix_projet.currentText()
        dossier = orchestrateur.dossier_rejetees(self.config, projet)
        combien, octets = galerie_mod.poids_a_purger(dossier)
        if not combien:
            QMessageBox.information(self, "Purger", "Aucune image rejetée à purger.")
            return
        boite = QMessageBox(self)
        boite.setWindowTitle("Purger les rejetées")
        boite.setText(f"{combien} image(s) et leur manifeste vont être SUPPRIMÉS "
                      f"définitivement ({galerie_mod.octets_lisibles(octets)}).")
        boite.setInformativeText(
            "Un rejet est une donnée : le lot 25 s'en sert pour mesurer. Cette suppression "
            "n'est pas annulable.")
        purger = boite.addButton("Purger", QMessageBox.DestructiveRole)
        boite.addButton("Annuler", QMessageBox.RejectRole)
        boite.setDefaultButton(boite.buttons()[-1])
        boite.exec()
        if boite.clickedButton() is not purger:
            return
        nombre, libres = galerie_mod.purger(dossier)
        self.journal.emit("info", f"{nombre} image(s) rejetée(s) supprimée(s), "
                                  f"{galerie_mod.octets_lisibles(libres)} libérés.")
        self._peindre_galerie(projet)

    # ------------------------------------------------------------------ #
    # Phase 1 → l'écran de relecture
    # ------------------------------------------------------------------ #

    def _preparer(self) -> None:
        projet = self.choix_projet.currentText()
        personnage = self._personnage_choisi()
        if not projet or not personnage:
            QMessageBox.information(
                self, "Préparer la requête",
                "Choisis d'abord un personnage. Ceux qui sont grisés n'ont ni attribut cité "
                "ni image candidate dans la bible visuelle : « Ouvrir la bible… » y mène.")
            return
        self._resultat = {}
        # ⚠ Une COPIE PROFONDE mutée en mémoire, comme dans les lanceurs : le modèle choisi
        # pour ce run outrepasse la spec des agents sans toucher à `config.yaml`, et sans
        # rester collé à la configuration partagée avec le reste de la fenêtre.
        demande = par.appliquer(copy.deepcopy(self.config), par.ILLUSTRATIONS,
                                self.formulaire.valeurs())
        if demande.agents_outrepasses:
            noms = ", ".join(nom for nom, _, _ in demande.agents_outrepasses)
            self.journal.emit("info",
                              f"Modèle de ce run : « {self.choix_modele.currentData()} » — "
                              f"il outrepasse {noms} (config.yaml n'est pas modifié).")
        self.demande_tache.emit(tache_preparation(
            config=demande.config, projet=projet, tome=None, personnage=personnage,
            cadrage=self.choix_cadrage.currentData(), nombre=self.champ_nombre.value(),
            graine=self._graine(), reporter=self._reporter, deposer=self._deposer))

    def _personnage_choisi(self) -> str:
        item = self.liste_personnages.currentItem()
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def _graine(self):
        valeur = self.champ_graine.value()
        return None if valeur < 0 else int(valeur)

    def _deposer(self, resultat: dict) -> None:
        """Appelé **depuis le fil de travail** : on ne fait que ranger, jamais peindre."""
        self._resultat = dict(resultat or {})

    def apres_tache(self, succes: bool, message: str) -> None:
        """La fenêtre relaie la fin d'une tâche d'illustration. C'est ici qu'on peint."""
        self.marquer_en_cours(False)
        if not succes:
            self.journal.emit("warn", message)
            return
        self.journal.emit("info", message)
        porte = self._resultat.get("porte")
        if porte is not None:
            self._porte = porte
            self._chemin_requete = self._resultat.get("chemin")
            self._afficher_relecture(porte)
            return
        if self._resultat.get("recap") is not None:
            self.pages.setCurrentIndex(0)
            self._peindre_galerie(self.choix_projet.currentText())

    def _afficher_relecture(self, porte) -> None:
        """Remplit l'écran de relecture : les six choses de L27.1 bis, dans cet ordre."""
        while self.corps_relecture.count():
            item = self.corps_relecture.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        self._champs_prompt: dict = {}
        self._cases: dict = {}
        self._cases_canaux: dict = {}
        for ecran in porte.ecrans:
            self.corps_relecture.addWidget(self._bloc_relecture(ecran))
        self.corps_relecture.addStretch(1)
        anomalies = porte.anomalies()
        self.etiquette_anomalies.setText(
            "\n".join(f"⚠ {a}" for a in anomalies) if anomalies else "")
        self.etiquette_anomalies.setVisible(bool(anomalies))
        self.pages.setCurrentIndex(1)

    def _bloc_relecture(self, ecran) -> QWidget:
        from illustration import relecture as relecture_mod

        boite = QGroupBox(f"{ecran.nom} — {ecran.personnage or 'description libre'} "
                          f"· cadrage {ecran.cadrage}")
        vbox = QVBoxLayout(boite)

        # 1 — le prompt, éditable, l'original restaurable.
        vbox.addWidget(QLabel("Prompt"))
        champ = QPlainTextEdit(ecran.prompt)
        champ.setMinimumHeight(90)
        champ.setAccessibleName(f"Prompt de {ecran.nom}")
        vbox.addWidget(champ)
        restaurer = QPushButton("Restaurer le prompt d'origine")
        restaurer.setToolTip(
            "Une correction doit être annulable SANS relancer la phase 1, qui coûte des "
            "minutes de modèle de vision.")
        restaurer.clicked.connect(
            lambda _=False, c=champ, t=ecran.prompt_initial: c.setPlainText(t))
        restaurer.setEnabled(bool(ecran.prompt_initial))
        vbox.addWidget(restaurer)

        # 2 — le prompt négatif, éditable, chaque terme avec son motif en infobulle.
        vbox.addWidget(QLabel("Prompt négatif"))
        negatif = QPlainTextEdit(ecran.prompt_negatif)
        negatif.setMinimumHeight(56)
        negatif.setAccessibleName(f"Prompt négatif de {ecran.nom}")
        negatif.setToolTip("\n".join(
            f"· {t.texte} — {t.motif or 'AUCUN MOTIF : ce terme ne vient pas du gabarit'}"
            for t in ecran.termes_negatifs) or "aucun terme")
        vbox.addWidget(negatif)
        self._champs_prompt[ecran.nom] = (champ, negatif)

        # 3 — les images, en DEUX groupes visuellement distincts.
        for groupe, vignettes in ((relecture_mod.GROUPE_IDENTITE, ecran.references),
                                  (relecture_mod.GROUPE_STYLE, ecran.ancrages)):
            if not vignettes:
                continue
            vbox.addWidget(self._groupe_images(ecran.nom, groupe, vignettes))

        # 4 — la traçabilité des attributs.
        if ecran.attributs:
            vbox.addWidget(self._bloc_attributs(ecran))

        # 5 — les canaux structurés : désarmables, jamais éditables.
        armes = [c for c in ecran.canaux if c.arme]
        if armes:
            vbox.addWidget(self._bloc_canaux(ecran.nom, armes))
        return boite

    def _groupe_images(self, nom_bloc: str, groupe: str, vignettes) -> QWidget:
        from illustration import relecture as relecture_mod

        boite = QGroupBox(relecture_mod.TITRES_GROUPE[groupe])
        boite.setToolTip(relecture_mod.AIDES_GROUPE[groupe])
        grille = QGridLayout(boite)
        aide = QLabel(relecture_mod.AIDES_GROUPE[groupe])
        aide.setWordWrap(True)
        theme.poser_role(aide, "faible")
        grille.addWidget(aide, 0, 0, 1, 4)
        for index, vignette in enumerate(vignettes):
            colonne = QWidget()
            vbox = QVBoxLayout(colonne)
            image = QLabel()
            image.setPixmap(_vignette(vignette.chemin))
            image.setAlignment(Qt.AlignCenter)
            vbox.addWidget(image)
            case = QCheckBox(vignette.fichier)
            case.setChecked(vignette.retenue)
            case.setToolTip(vignette.motif or "aucun motif enregistré")
            self._cases[(nom_bloc, groupe, vignette.fichier)] = case
            vbox.addWidget(case)
            motif = QLabel(vignette.motif or "— aucun motif —")
            motif.setWordWrap(True)
            theme.poser_role(motif, "faible" if vignette.motif else "avertissement")
            vbox.addWidget(motif)
            if vignette.introuvable:
                perdue = QLabel("introuvable sur le disque")
                theme.poser_role(perdue, "erreur")
                vbox.addWidget(perdue)
            grille.addWidget(colonne, 1 + index // 4, index % 4)
        return boite

    @staticmethod
    def _bloc_attributs(ecran) -> QWidget:
        boite = QGroupBox("D'où vient chaque mot du prompt")
        vbox = QVBoxLayout(boite)
        for attribut in ecran.attributs:
            ligne = QLabel(
                f"{attribut.attribut} = {attribut.valeur}\n"
                f"    ↳ {attribut.source or 'AUCUNE SOURCE'} — « {attribut.texte[:160]} »")
            ligne.setWordWrap(True)
            theme.poser_role(ligne, "avertissement" if attribut.anomalie else "faible")
            if attribut.anomalie:
                ligne.setToolTip(attribut.motif_anomalie)
            vbox.addWidget(ligne)
        return boite

    def _bloc_canaux(self, nom_bloc: str, canaux) -> QWidget:
        boite = QGroupBox("Canaux structurés")
        vbox = QVBoxLayout(boite)
        aide = QLabel("On peut les DÉSARMER, pas les éditer : un éditeur de masque est un "
                      "lot à lui seul, et il n'est pas celui-ci.")
        aide.setWordWrap(True)
        theme.poser_role(aide, "faible")
        vbox.addWidget(aide)
        for canal in canaux:
            case = QCheckBox(f"désarmer « {canal.nom} » — {canal.description}")
            case.setToolTip("\n".join(canal.libelles) or canal.description)
            self._cases_canaux[(nom_bloc, canal.nom)] = case
            vbox.addWidget(case)
        return boite

    # ------------------------------------------------------------------ #
    # La porte, puis la phase 2
    # ------------------------------------------------------------------ #

    def _annuler_relecture(self) -> None:
        if self._porte is not None:
            self._porte.annuler()
        self.journal.emit("info",
                          "Relecture abandonnée. Rien n'est détruit : requete.yaml reste sur "
                          "le disque avec `valide: false`.")
        self.pages.setCurrentIndex(0)

    def _corrections(self) -> dict:
        from illustration import relecture as relecture_mod

        corrections: dict = {}
        for ecran in self._porte.ecrans:
            champ, negatif = self._champs_prompt[ecran.nom]
            retenues = {f for (bloc, groupe, f), case in self._cases.items()
                        if bloc == ecran.nom and groupe == relecture_mod.GROUPE_IDENTITE
                        and case.isChecked()}
            ancrages = {f for (bloc, groupe, f), case in self._cases.items()
                        if bloc == ecran.nom and groupe == relecture_mod.GROUPE_STYLE
                        and case.isChecked()}
            desarmes = {canal for (bloc, canal), case in self._cases_canaux.items()
                        if bloc == ecran.nom and case.isChecked()}
            corrections[ecran.nom] = relecture_mod.Correction(
                prompt=champ.toPlainText(), prompt_negatif=negatif.toPlainText(),
                retenues=retenues, ancrages_retenus=ancrages, canaux_desarmes=desarmes)
        return corrections

    def _valider(self) -> None:
        """Écrit `valide: true`, enregistre `requete.yaml`, puis soumet la phase 2.

        ⚠ Deux confirmations et pas une : la porte demande un NOM (sans défaut), et le
        récapitulatif annonce la fourchette de temps mesurée. Le patron est celui de
        `gui/lanceur.py:_confirmer` — « un run peut durer plusieurs heures et occupe le GPU
        jusqu'au bout »."""
        from illustration import relecture as relecture_mod
        from illustration import requete as requete_mod

        if self._porte is None:
            return
        par = self.champ_valideur.currentText().strip()
        try:
            doc = self._porte.valider(self._corrections(), par=par)
        except (relecture_mod.PorteFermee, requete_mod.RequeteNonValidee) as err:
            QMessageBox.warning(self, "Valider et générer", str(err))
            return
        if not self._confirmer(doc):
            return
        requete_mod.save(doc, self._chemin_requete,
                         projet=self.choix_projet.currentText(), tome="")
        self._lancer_la_generation()

    def _confirmer(self, doc: dict) -> bool:
        from illustration import attente

        total = sum(int(b.get("nombre_images") or 1) for b in doc["images"])
        boite = QMessageBox(self)
        boite.setWindowTitle("Valider et générer")
        boite.setText("Le GPU est pris jusqu'au bout de ce lot.")
        boite.setInformativeText(
            attente.annonce(total) + "\n\n"
            "Le prompt validé, les images retenues et ton nom partent dans le sidecar de "
            "chaque image, avec le prompt avant et après correction.")
        lancer = boite.addButton("Générer", QMessageBox.AcceptRole)
        boite.addButton("Revenir à la relecture", QMessageBox.RejectRole)
        boite.setDefaultButton(lancer)
        boite.exec()
        return boite.clickedButton() is lancer

    def _lancer_la_generation(self) -> None:
        from illustration import progression as progression_mod

        self._annulation = False
        self._avancement = progression_mod.Progression()
        self._resultat = {}
        self.marquer_en_cours(True)
        self.pages.setCurrentIndex(0)
        self.demande_tache.emit(tache_generation(
            config=self.config, projet=self.choix_projet.currentText(), tome=None,
            porte=self._porte, chemin_requete=self._chemin_requete,
            chemin_config=self.chemin_config, reporter=self._reporter,
            avancement=self._avancement, annulation=lambda: self._annulation,
            deposer=self._deposer))

    def demander_arret(self) -> None:
        """Arrêt propre de la génération. **Public**, parce que le bandeau de run de la
        fenêtre porte le même geste (lot 32) et qu'un même geste ne doit avoir qu'un seul
        chemin — sinon l'un des deux oublie de désarmer le bouton, ou d'écrire la ligne qui
        dit pourquoi ça ne s'arrête pas tout de suite."""
        self._arreter()

    def _arreter(self) -> None:
        self._annulation = True
        self.bouton_arreter.setEnabled(False)
        self.journal.emit("warn",
                          "Arrêt demandé. Il aura lieu à la fin de l'image en cours — un "
                          "modèle interrompu en plein débruitage laisse le pilote dans un "
                          "mauvais état. Le modèle rendra la carte avant de rendre la main.")

    # ------------------------------------------------------------------ #

    def marquer_en_cours(self, en_cours: bool) -> None:
        # ⚠ `self._arme` et pas seulement `not en_cours` : sans lui, la fin d'une tâche
        # RÉACTIVERAIT « Préparer la requête » sur une installation où la brique est désarmée,
        # et le refus n'arriverait qu'après le clic.
        self.bouton_preparer.setEnabled(
            not en_cours and self._arme and not brique_absente())
        self.bouton_valider.setEnabled(not en_cours)
        self.bouton_purger.setEnabled(not en_cours)
        self.bouton_arreter.setEnabled(en_cours)

    def rafraichir_progression(self) -> None:
        """Appelée par la fenêtre sur chaque ligne de journal : l'état vient du modèle pur."""
        if self._avancement is None:
            return
        self.etiquette_phase.setText(
            f"{self._avancement.libelle()}   ·   {self._avancement.resume()}")

    def etat_progression(self) -> dict | None:
        """L'état des trois phases, à plat — pour le bandeau de run de la fenêtre.

        ⚠ **`illustration/progression.py` n'est PAS fusionné dans `core/progression.py`**
        (`PLAN-32` L32.1). Il porte trois phases nommées, un état propre à la brique (la
        bascule VRAM) et il est testé. Le bandeau se contente de le LIRE : c'est une façade,
        pas une reprise, et supprimer cette méthode ne coûterait qu'un bandeau muet."""
        return self._avancement.etat() if self._avancement is not None else None

    @property
    def _reporter(self):
        """Un reporter minimal qui traverse vers le fil d'affichage par le signal `journal`."""
        emettre = self.journal.emit
        return type("R", (), {
            "info": staticmethod(lambda m: emettre("info", m)),
            "warn": staticmethod(lambda m: emettre("warn", m)),
            "verbose": staticmethod(lambda m: emettre("verbose", m)),
            "stage": staticmethod(lambda m: emettre("stage", m))})()

    # ------------------------------------------------------------------ #
    # L18.7 — ce qui se persiste
    # ------------------------------------------------------------------ #

    def reglages(self) -> dict:
        """⚠ **Ni le nom du valideur, ni la graine.** Le nom est une signature : le retrouver
        pré-rempli le jour suivant transformerait une validation en case cochée d'avance, ce
        qui est exactement ce que la porte humaine refuse. La graine ne se persiste pas non
        plus : une graine d'hier appliquée à un autre personnage produit une reproductibilité
        qui ne reproduit rien."""
        return {"projet": self.choix_projet.currentText(),
                "cadrage": self.choix_cadrage.currentIndex(),
                "nombre": int(self.champ_nombre.value())}

    def appliquer_reglages(self, etat: dict) -> None:
        projet = str(etat.get("projet") or "")
        if projet and self.choix_projet.findText(projet) >= 0:
            self.choix_projet.setCurrentText(projet)
        cadrage = etat.get("cadrage")
        if isinstance(cadrage, int) and 0 <= cadrage < self.choix_cadrage.count():
            self.choix_cadrage.setCurrentIndex(cadrage)
        if etat.get("nombre"):
            self.champ_nombre.setValue(int(etat["nombre"]))
        self._peindre_cout()


# ──────────────────────────────  Deux rouages  ──────────────────────────────

def _vignette(chemin) -> QPixmap:
    """Une imagette carrée, ou un carré vide. **Ne lève jamais** : un fichier illisible ne
    doit pas empêcher de relire les autres."""
    pixmap = QPixmap()
    if chemin is not None:
        try:
            pixmap.load(str(chemin))
        except Exception:                            # noqa: BLE001 — vignette de confort
            pixmap = QPixmap()
    if pixmap.isNull():
        pixmap = QPixmap(COTE_VIGNETTE, COTE_VIGNETTE)
        pixmap.fill(Qt.transparent)
        return pixmap
    return pixmap.scaled(COTE_VIGNETTE, COTE_VIGNETTE, Qt.KeepAspectRatio,
                         Qt.SmoothTransformation)
