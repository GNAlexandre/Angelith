# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les boîtes que la fenêtre n'avait pas — création de projet, aide, diagnostic, préférences.

**Que du Qt.** Rien ne décide ici : la validation d'un nom de projet vit dans
`manga/creation_projet.py`, le catalogue des raccourcis dans `gui/actions.py`, la légende des
symboles dans `gui/pellicule.py`, et les réglages persistés dans `gui/reglages.py`. Ces boîtes
ne font que montrer et collecter — c'est ce qui permet de tester les quatre modules précédents
sans écran, et de n'avoir ici que du code qu'on relit.

⚠ Aucune de ces boîtes n'écrit sur le disque. `DialogueNouveauProjet` rend une DESCRIPTION de
ce qu'il faut créer ; la copie, qui peut porter sur plusieurs centaines de mégaoctets, part
dans le fil de travail — jamais dans le fil d'affichage, où elle gèlerait la fenêtre pour la
durée d'un `.cbz`.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSpinBox, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

import bibliotheque as biblio
from core import glossary
from core import glossary_export as gexport
from core import provenance
from core.version import ETAT_BRIQUES, __version__
import creation as crea
from . import actions as act
from . import depot_guide as dg
from . import pellicule as pel
from . import sorties as so
from . import theme
from . import vue_maj as vmaj

#: Séparateur de paragraphe — le même que `gui/editeur.py`, pour la même raison (les `\n`
#: littéraux dans une f-string sont interdits avant Python 3.12 et illisibles après).
SAUT_LIGNE = chr(10) * 2


# --------------------------------------------------------------------------- #
#  L18.1 — créer un projet
# --------------------------------------------------------------------------- #

class DialogueNouveauProjet(QDialog):
    """Désigner des sources, nommer le projet et le tome. **Ne crée rien.**

    Rend, par `description()`, tout ce dont `manga.creation_projet.creer` a besoin. La copie
    elle-même est soumise au fil de travail par la fenêtre.

    ⚠ Le nom du projet et celui du tome sont **pré-remplis depuis la source** quand c'est
    possible : un `.cbz` nommé `Mon Manga - Vol.3.cbz` propose « Mon Manga » et « Vol.3 ». Une
    boîte qui demande de retaper ce qu'elle sait déjà est une boîte qu'on referme."""

    def __init__(self, config: dict, chemins=(), parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Nouveau projet")
        self.setMinimumWidth(560)
        self._construire()
        if chemins:
            self._ajouter(list(chemins))

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        layout = QVBoxLayout(self)

        explication = QLabel(
            "Les fichiers choisis seront <b>copiés</b> sous <code>sources/</code>. "
            "Un projet qui référencerait des fichiers restés ailleurs casserait au premier "
            "déplacement, et tout le pipeline suppose cette arborescence.")
        explication.setWordWrap(True)
        layout.addWidget(explication)

        boite_src = QGroupBox("Sources")
        vsrc = QVBoxLayout(boite_src)
        self.liste_sources = QListWidget()
        self.liste_sources.setMaximumHeight(120)
        vsrc.addWidget(self.liste_sources)
        ligne = QHBoxLayout()
        bouton_dossier = QPushButton("Ajouter un dossier…")
        bouton_dossier.clicked.connect(self._choisir_dossier)
        bouton_fichiers = QPushButton("Ajouter des images ou une archive…")
        bouton_fichiers.clicked.connect(self._choisir_fichiers)
        self.bouton_vider = QPushButton("Vider")
        self.bouton_vider.clicked.connect(self._vider)
        ligne.addWidget(bouton_dossier)
        ligne.addWidget(bouton_fichiers)
        ligne.addStretch(1)
        ligne.addWidget(self.bouton_vider)
        vsrc.addLayout(ligne)
        self.etiquette_poids = QLabel("—")
        theme.poser_role(self.etiquette_poids, "faible")
        vsrc.addWidget(self.etiquette_poids)
        layout.addWidget(boite_src)

        boite_nom = QGroupBox("Où le ranger")
        forme = QFormLayout(boite_nom)
        self.champ_projet = QLineEdit()
        self.champ_projet.setPlaceholderText("Mon Manga")
        self.champ_projet.textChanged.connect(self._maj_apercu)
        self.champ_tome = QLineEdit()
        self.champ_tome.setPlaceholderText("Vol.1")
        self.champ_tome.textChanged.connect(self._maj_apercu)
        # ⚠ **Light novel compris depuis le lot 40**, et c'est le manque le plus visible que
        # l'interface portait : la brique historique du projet était la seule qu'on ne pouvait
        # pas créer ici. `app.py` disait « crée un dossier sous sources/ » — le geste manquant
        # exact que `manga/creation_projet.py` avait comblé pour le manga.
        self.choix_format = QComboBox()
        for identifiant, dispo in crea.DISPOSITIONS.items():
            self.choix_format.addItem(dispo.libelle, identifiant)
        self.choix_format.setToolTip(
            "« Manga » = planches paginées, lecture de droite à gauche. « Webtoon » = bandes "
            "verticales — c'est ce choix qui décide du sens de lecture et du découpage en "
            "fenêtres de détection. « Light novel » = un roman, dont les sources sont des "
            ".docx/.pdf/.epub/.txt/.md rangés par langue.")
        self.choix_format.currentTextChanged.connect(self._maj_disposition)
        self.choix_langue = QComboBox()
        self.choix_langue.setToolTip(
            "Ajoute un dossier de langue sous le format. ⚠ Il est OBLIGATOIRE pour un light "
            "novel : `pipeline/sources.py` cherche des dossiers de langue directement sous le "
            "tome, et un roman sans langue n'est lisible par aucune brique.")
        self.choix_langue.currentIndexChanged.connect(self._maj_apercu)
        forme.addRow("Projet", self.champ_projet)
        forme.addRow("Tome", self.champ_tome)
        forme.addRow("Format", self.choix_format)
        forme.addRow("Langue source", self.choix_langue)
        layout.addWidget(boite_nom)

        self.apercu = QLabel("—")
        self.apercu.setWordWrap(True)
        theme.poser_role(self.apercu, "mono")
        layout.addWidget(self.apercu)

        self.erreur = QLabel("")
        self.erreur.setWordWrap(True)
        theme.poser_role(self.erreur, "erreur")
        layout.addWidget(self.erreur)

        self.boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.boutons.button(QDialogButtonBox.Ok).setText("Créer le projet")
        self.boutons.accepted.connect(self._valider)
        self.boutons.rejected.connect(self.reject)
        layout.addWidget(self.boutons)
        self._chemins: list[Path] = []
        # ⚠ **`_maj_disposition` AVANT `_maj_apercu`, et il ne peut pas être omis** : depuis le
        # lot 40, la liste des langues n'est plus statique — elle dépend de la disposition, qui
        # décide si « langue par défaut » a un sens. Elle est branchée sur `currentTextChanged`,
        # qui ne part PAS à la construction : sans cet appel, la boîte s'ouvrait avec un combo
        # « Langue source » **vide** tant qu'on ne changeait pas de format. Trouvé par
        # `tests/test_gui_dialogues_maj.py`, qui interroge le combo au lieu de le cliquer.
        self._maj_disposition()

    # ------------------------------------------------------------------ #

    def _maj_disposition(self) -> None:
        """Recale le combo de langue sur ce que la disposition choisie exige.

        ⚠ Le light novel n'offre PAS « langue par défaut » : un tome de roman sans dossier de
        langue n'est lisible par personne. Laisser l'entrée visible puis refuser à la
        validation serait proposer une impasse."""
        dispo = crea.disposition(self.choix_format.currentData())
        courante = self.choix_langue.currentData()
        self.choix_langue.blockSignals(True)
        self.choix_langue.clear()
        if not dispo.langue_obligatoire:
            self.choix_langue.addItem("(langue par défaut du projet)", None)
        for code in (dispo.langues or crea.LANGUES_LN):
            self.choix_langue.addItem(code, code)
        index = self.choix_langue.findData(courante)
        self.choix_langue.setCurrentIndex(max(0, index))
        self.choix_langue.blockSignals(False)
        self._maj_apercu()

    def _choisir_dossier(self) -> None:
        dossier = QFileDialog.getExistingDirectory(self, "Dossier de planches")
        if dossier:
            self._ajouter([Path(dossier)])

    def _choisir_fichiers(self) -> None:
        motifs = "Planches et archives (*.png *.jpg *.jpeg *.webp *.bmp *.cbz *.cbr *.zip)"
        fichiers, _ = QFileDialog.getOpenFileNames(self, "Images ou archive", "",
                                                   f"{motifs};;Tous les fichiers (*)")
        if fichiers:
            self._ajouter([Path(f) for f in fichiers])

    def _ajouter(self, chemins: list[Path]) -> None:
        for chemin in chemins:
            if chemin not in self._chemins:
                self._chemins.append(Path(chemin))
        self.liste_sources.clear()
        for chemin in self._chemins:
            self.liste_sources.addItem(str(chemin))
        self._deviner_noms()
        self._maj_apercu()

    def _vider(self) -> None:
        self._chemins.clear()
        self.liste_sources.clear()
        self._maj_apercu()

    def _deviner_noms(self) -> None:
        """Pré-remplit projet et tome depuis le premier chemin, sans jamais écraser une saisie.

        Deux formes reconnues, et pas une de plus : `Mon Manga - Vol.3` (archive ou dossier), et
        `…/Mon Manga/Vol.3/` (arborescence). Deviner davantage ferait proposer des noms faux
        assez souvent pour qu'on cesse de les lire."""
        if not self._chemins:
            return
        premier = self._chemins[0]
        tige = premier.stem if premier.is_file() else premier.name
        projet, tome = "", tige
        for separateur in (" - ", " – ", "_-_"):
            if separateur in tige:
                projet, tome = (m.strip() for m in tige.split(separateur, 1))
                break
        if not projet and premier.is_dir() and premier.parent.name:
            projet = premier.parent.name
        if not self.champ_projet.text().strip():
            self.champ_projet.setText(projet or tige)
        if not self.champ_tome.text().strip():
            self.champ_tome.setText(tome if projet else "Vol.1")

    # ------------------------------------------------------------------ #

    def _maj_apercu(self) -> None:
        quelle = self.choix_format.currentData() or crea.MANGA
        fichiers = crea.lister_sources(self._chemins, quelle)
        if fichiers:
            poids = crea.poids_lisible(crea.estimer_poids(fichiers))
            self.etiquette_poids.setText(
                f"{len(fichiers)} fichier(s) à copier · {poids}")
        else:
            attendu = ", ".join(crea.disposition(quelle).extensions)
            self.etiquette_poids.setText(
                f"aucun fichier lisible dans ce qui est choisi — attendu : {attendu}"
                if self._chemins else "—")
        try:
            cible = crea.dossier_cible(
                self.config, self.champ_projet.text().strip() or "…",
                self.champ_tome.text().strip() or "…",
                quelle=quelle, langue=self.choix_langue.currentData())
            self.apercu.setText(str(cible))
        except crea.ErreurCreation as err:
            self.apercu.setText(str(err))
        pret = bool(fichiers) and bool(self.champ_projet.text().strip()) \
            and bool(self.champ_tome.text().strip())
        self.boutons.button(QDialogButtonBox.Ok).setEnabled(pret)
        self.erreur.setText("")

    def _valider(self) -> None:
        """Valide par `creation_projet` — la MÊME fonction que la création elle-même.

        Revalider ici avec une règle recopiée serait le meilleur moyen d'accepter dans la boîte
        ce que la copie refuserait ensuite."""
        try:
            crea.valider_nom(self.champ_projet.text(), "nom de projet")
            crea.valider_nom(self.champ_tome.text(), "nom de tome")
            crea.preparer(self.config, self.champ_projet.text(), self.champ_tome.text(),
                          quelle=self.choix_format.currentData(),
                          langue=self.choix_langue.currentData())
        except crea.ErreurCreation as err:
            self.erreur.setText(str(err))
            return
        self.accept()

    # ------------------------------------------------------------------ #

    def description(self) -> dict:
        """Ce qu'il faut créer. Consommé tel quel par `creation_projet.creer`."""
        return {"projet": self.champ_projet.text().strip(),
                "tome": self.champ_tome.text().strip(),
                "chemins": list(self._chemins),
                # ⚠ `quelle` et non `format` depuis le lot 40 : « light_novel » n'est pas un
                # format de la brique manga, c'est une DISPOSITION — une façon de ranger des
                # fichiers. Garder le nom `format` aurait installé dans le contrat la
                # confusion que `gui/parametres.py` a déjà refusée pour `panneaux`.
                "quelle": self.choix_format.currentData(),
                "langue": self.choix_langue.currentData()}


# --------------------------------------------------------------------------- #
#  Panneau de texte — diagnostic, test LLM, rapport d'import
# --------------------------------------------------------------------------- #

class DialogueTexte(QDialog):
    """Un résultat long, en monospace, sélectionnable.

    ⚠ `setReadOnly` et **pas** un `QMessageBox` : le diagnostic complet fait une trentaine de
    lignes, et une boîte de message les tronque sans le dire. Sélectionnable, parce que la
    première chose qu'on fait d'un diagnostic est de le coller quelque part."""

    def __init__(self, titre: str, texte: str, parent=None, *, sous_titre: str = ""):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.resize(820, 560)
        layout = QVBoxLayout(self)
        if sous_titre:
            entete = QLabel(sous_titre)
            entete.setWordWrap(True)
            layout.addWidget(entete)
        self.zone = QPlainTextEdit()
        self.zone.setReadOnly(True)
        self.zone.setPlainText(texte)
        theme.poser_role(self.zone, "mono")
        self.zone.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.zone, 1)
        boutons = QDialogButtonBox(QDialogButtonBox.Close)
        boutons.rejected.connect(self.reject)
        boutons.accepted.connect(self.accept)
        layout.addWidget(boutons)


# --------------------------------------------------------------------------- #
#  Aide
# --------------------------------------------------------------------------- #

#: Raccourcis qui ne passent PAS par une action de menu, parce qu'ils appartiennent à un
#: widget et non à la fenêtre. Ils sont listés quand même : le but de cette boîte est qu'un
#: utilisateur sache ce que son clavier peut faire, pas de refléter une architecture.
RACCOURCIS_LOCAUX: tuple[tuple[str, str], ...] = (
    ("Page préc. / Page suiv.", "planche précédente / suivante (saute celles que le filtre "
                                "masque)"),
    ("Échap", "revenir à l'outil « Choisir »"),
    ("Molette", "zoomer sous le pointeur"),
    ("Entrée", "dans le champ de recherche : chercher dans tout le tome"),
    ("1 – 5", "choisir un outil de dessin (Choisir, + Rectangle, + Ellipse, Redessiner, "
              "Scinder)"),
    # L19.6.6 — l'alternative clavier aux gestes de canevas. Elle a autant besoin d'être
    # DÉCOUVRABLE que les autres : un geste qu'on ne sait pas possible n'existe pas.
    ("← ↑ → ↓", "déplacer la bulle sélectionnée d'un pixel (Maj : dix)"),
    ("Ctrl + ← ↑ → ↓", "la retailler d'un pixel (Ctrl+Maj : dix). ⚠ TRACER une zone reste un "
                       "geste de souris — le clavier déplace et retaille, il ne dessine pas"),
)


def _poser_parcours(hote, noms: tuple[str, ...]) -> None:
    """Chaîne l'ordre de tabulation déclaré par `PARCOURS`.

    Le lot 19 a posé la règle (critère 6) : l'ordre de tabulation d'un panneau est **déclaré**,
    pas laissé à l'ordre de construction — celui-ci change dès qu'on déplace un widget, et
    personne ne s'en aperçoit sans clavier."""
    widgets = [getattr(hote, nom) for nom in noms if hasattr(hote, nom)]
    for avant, apres in zip(widgets, widgets[1:]):
        QWidget.setTabOrder(avant, apres)


def _defilement(html: str) -> QScrollArea:
    """Une zone qui défile autour d'un `QLabel` riche.

    ⚠ Sans elle, une liste de trente raccourcis dans une boîte non redimensionnée coupe les
    dernières lignes en silence — et ce sont justement celles qu'on ne connaît pas."""
    vue = QLabel(html)
    vue.setTextInteractionFlags(Qt.TextSelectableByMouse)
    vue.setWordWrap(True)
    vue.setAlignment(Qt.AlignTop)
    vue.setContentsMargins(theme.Espacement.M, theme.Espacement.XS,
                           theme.Espacement.M, theme.Espacement.M)
    zone = QScrollArea()
    zone.setWidget(vue)
    zone.setWidgetResizable(True)
    return zone


def _table_html(lignes) -> str:
    corps = "".join(
        f"<tr><td style='padding:2px 14px 2px 0;white-space:nowrap;'><b>{cle}</b></td>"
        f"<td style='padding:2px 0;'>{valeur}</td></tr>" for cle, valeur in lignes)
    return f"<table>{corps}</table>"


class DialogueRaccourcis(QDialog):
    """La liste des raccourcis, construite depuis `gui/actions.py`.

    ⚠ Construite, pas recopiée. Une liste d'aide écrite à la main devient fausse au premier
    raccourci ajouté, et une aide fausse est pire que pas d'aide."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Raccourcis clavier")
        self.resize(680, 640)
        layout = QVBoxLayout(self)
        morceaux = []
        for menu in act.MENUS:
            lignes = [(a.raccourci, a.libelle) for a in act.actions()
                      if a.menu == menu and a.raccourci]
            if lignes:
                morceaux.append(f"<h3>{menu}</h3>" + _table_html(lignes))
        alias = [(al, f"{a.libelle} (alias de {a.raccourci})")
                 for a in act.actions() for al in a.alias]
        if alias:
            morceaux.append("<h3>Alias conservés</h3>" + _table_html(alias))
        morceaux.append("<h3>Dans l'éditeur de planche</h3>" + _table_html(RACCOURCIS_LOCAUX))
        layout.addWidget(_defilement("".join(morceaux)), 1)
        boutons = QDialogButtonBox(QDialogButtonBox.Close)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)


class DialogueLegende(QDialog):
    """Le sens des symboles — jusqu'ici accessible seulement par survol."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Légende des symboles")
        self.resize(680, 620)
        layout = QVBoxLayout(self)
        morceaux = [f"<h3>{titre}</h3>" + _table_html(lignes)
                    for titre, lignes in pel.LEGENDE]
        layout.addWidget(_defilement("".join(morceaux)), 1)
        boutons = QDialogButtonBox(QDialogButtonBox.Close)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)


#: Les dossiers où l'on cherche des fiches de provenance. ⚠ Relatifs à la racine du dépôt, et
#: pas au dossier courant : la page « À propos » doit dire la même chose quel que soit l'endroit
#: d'où l'application a été lancée.
DOSSIERS_DE_POIDS = ("manga_models", "illustration_models")


def _racine_du_depot() -> Path:
    """⚠ Les fiches de provenance vivent à côté des POIDS, pas dans le paquet : aucun poids
    n'est redistribué (`PLAN-37` §0.3), donc en gel elles sont dans le dossier utilisateur,
    là où `core/reparations.py` les écrit. Hors gel, la racine du dépôt, comme avant."""
    from core.installation import dossier_utilisateur, gele, racine_livree
    return dossier_utilisateur() if gele() else racine_livree()


def licences_des_poids_presents(dossiers=None) -> list[str]:
    """Les licences des poids **réellement présents sur cette machine** — `PLAN-36` L36.5.

    ⚠ C'est une liste MESURÉE, pas récitée. Le bloc statique ci-dessous dit ce qu'Angelith
    sait récupérer et sous quelle licence ; celui-ci dit ce qui est là. Les deux sont
    nécessaires : un utilisateur qui redistribue des planches doit savoir ce que SA machine a
    produit, pas ce que le projet pourrait produire.

    Un poids sans fiche de provenance n'est pas crédité d'une licence : `core/provenance.py`
    l'ignore, et c'est volontaire — inventer une licence pour un fichier arrivé par un chemin
    inconnu serait exactement l'affirmation que ce lot combat."""
    racine = _racine_du_depot()
    chemins = [racine / d for d in (dossiers or DOSSIERS_DE_POIDS)]
    return [fiche.resume() for fiche in provenance.inventorier(chemins)]


def texte_a_propos(config: dict | None = None, resultat=None) -> str:
    """Version, état des briques, licence du logiciel, et **les licences des poids présents**.

    ⚠ Le texte du `NOTICE`, pas une paraphrase. Les poids ne sont pas distribués avec le
    dépôt ; ils sont téléchargés au premier usage, et leurs licences ne sont donc pas celles du
    programme. Quiconque redistribue des planches produites ici doit pouvoir le lire sans
    ouvrir un fichier au clavier.

    ## ⚠ MISE À JOUR lot 36 (2026-09-06) — le nom public est tranché, et l'inventaire est réel

    Deux ajouts, et chacun ferme une question ouverte :

    · **« Angelith » est le nom public, « Yume-Trad » le nom du dépôt de travail.** Le contexte
      agent du 2026-08-26 s'interrogeait (« vérifier s'il s'agit d'un renommage ou d'une
      brique ») ; au 2026-09-06 tout le code applicatif dit Angelith —
      `app.setApplicationName("Angelith")`, le titre de fenêtre, `orchestrator_manga.py`,
      `.angelith/` pour les réglages. La question était tranchée dans les faits ; elle est
      écrite ici ;
    · **la liste des poids est celle du disque**, lue dans les fiches de provenance écrites par
      `core/reparations.py`. Le bloc qui suit dit ce que le projet SAIT récupérer ; l'inventaire
      dit ce qui est là.

    ## ⚠ MISE À JOUR lot 37 (2026-09-06) — la vérification de version, et elle est DÉSARMÉE

    `config` est optionnel, et la ligne qu'il ajoute dit d'abord ce qui **ne** se passe pas :
    « Vérification des versions : désarmée. Rien ne sort de cette machine. » C'est l'un des six
    différenciateurs annoncés du projet, et il vaut mieux l'écrire à l'endroit où quelqu'un
    cherche des informations sur le logiciel qu'ailleurs.

    ⚠ **L'appel réseau, quand il est armé, se fait ICI** — donc sur le fil d'affichage, dans une
    boîte que l'utilisateur vient d'ouvrir volontairement, avec un délai plafonné à 3,0 s. Ce
    n'est PAS le cas de l'accueil, dont les trois sondes partent dans le fil de travail
    (`gui/sondes.py`) : là, l'appel serait sur le chemin du premier pixel. Deux endroits, deux
    règles, et la différence est que celui-ci répond à un clic.

    ## ⚠ MISE À JOUR lot 40 (2026-09-06) — l'appel N'A PLUS LIEU ICI quand on lui donne

    L'avertissement ci-dessus reste vrai pour un appel sans `resultat`, et c'est ce que font
    les tests. Mais `gui/fenetre.py` passe désormais **le résultat déjà obtenu** par la tâche
    des sondes, et cette page ne rappelle alors plus rien : la vérification est armée par
    défaut depuis ce lot, donc elle a déjà eu lieu au démarrage, dans le fil de travail. Payer
    3,0 s de délai une seconde fois pour réafficher la même phrase serait un gel de fenêtre
    sans contrepartie.

    La ligne renvoie en outre vers le bouton « Rechercher une mise à jour » du menu Aide, qui
    est le geste, là où cette page n'est qu'un constat."""
    from core import maj
    from manga import models
    presents = licences_des_poids_presents()
    briques = " · ".join(f"{nom} : {etat}" for nom, etat in ETAT_BRIQUES.items())
    inventaire = ("\n".join(f"  · {ligne}" for ligne in presents) if presents
                  else "  (aucune fiche de provenance : soit aucun poids n'a été récupéré par\n"
                       "   Angelith sur cette machine, soit ils ont été posés à la main — dans\n"
                       "   ce cas leur licence n'est pas établie ici, va la vérifier à la source.)")
    return (
        f"Angelith {__version__}\n"
        f"Pipeline de fan-traduction local — light novel, manga/webtoon, OCR de scans.\n"
        f"État des briques — {briques}.\n"
        f"{(resultat if resultat is not None else maj.verifier(config or {})).phrase()}\n"
        f"Aide > Rechercher une mise à jour… pour vérifier maintenant.\n"
        f"\n"
        f"« Angelith » est le nom public du logiciel ; « Yume-Trad » est le nom du dépôt de\n"
        f"travail. Les deux désignent la même chose.\n"
        f"\n"
        f"Licence : GNU AGPL-3.0-or-later (fichier LICENSE).\n"
        f"C'est une conséquence, pas une préférence : PyMuPDF est AGPL-3.0.\n"
        f"PySide6 est LGPL-3.0 — un programme AGPL peut le lier.\n"
        f"\n"
        f"Poids de modèles — TÉLÉCHARGÉS, jamais inclus dans le dépôt, jamais redistribués\n"
        f"ni miroités par ce projet :\n"
        # ⚠ Les licences sont LUES depuis `manga/models.py` (lot 38), plus recopiées ici. Le
        # dépôt en portait trois versions différentes, dont une fausse ; cette page-ci était
        # l'une des deux qui disaient vrai, et elle le dit maintenant par construction.
        f"  · détecteur de bulles : {models.DETECTEUR_URL}\n"
        f"    {models.DETECTEUR_LICENCE}\n"
        f"    {models.DETECTEUR_LICENCE_NOTE}\n"
        f"  · détecteur de texte sur le dessin : {models.TEXTE_URL}\n"
        f"    {models.TEXTE_LICENCE}\n"
        f"    {models.TEXTE_LICENCE_NOTE}\n"
        f"  · manga-ocr (OCR japonais) : {models.OCR_LICENCE}, récupéré au premier lancement.\n"
        f"\n"
        f"Poids RÉELLEMENT PRÉSENTS sur cette machine, d'après leurs fiches de provenance :\n"
        f"{inventaire}\n"
        f"\n"
        f"⚠ Vérifie la licence de chaque poids sur sa page AVANT de redistribuer quoi que ce\n"
        f"soit qui en dérive. Le détail complet est dans NOTICE.\n"
        f"\n"
        f"Images générées : marquées au sens de l'AI Act art. 50(2) — c'est un défaut sans\n"
        f"interrupteur de la brique illustration.\n"
        f"\n"
        f"Polices : Comic Neue — SIL OFL 1.1 (templates/fonts/OFL.txt).\n"
        f"Aucun corpus sous droits n'est distribué avec ce projet.\n")


# --------------------------------------------------------------------------- #
#  Préférences
# --------------------------------------------------------------------------- #

class DialoguePreferences(QDialog):
    """Réglages de l'INTERFACE. **`config.yaml` n'est jamais touché ici.**

    C'est la ligne de partage, et elle n'est pas négociable : `config.yaml` est un document de
    95 Ko dont l'essentiel est de la prose qui justifie chaque valeur par un chiffre. Un
    aller-retour `yaml.safe_dump` l'effacerait. Ce que cette boîte règle vit donc dans
    `.angelith/interface.json`, qui n'a aucune prose à perdre — et pour tout le reste, elle
    renvoie au fichier, par le bouton du bas."""

    def __init__(self, etat: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Préférences de l'interface")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

        avertissement = QLabel(
            "Ces réglages n'appartiennent qu'à l'interface et vivent dans "
            "<code>.angelith/interface.json</code>. <b>Aucun ne touche à "
            "<code>config.yaml</code></b>, dont les commentaires sont la documentation.")
        avertissement.setWordWrap(True)
        layout.addWidget(avertissement)

        boite = QGroupBox("Au démarrage")
        forme = QFormLayout(boite)
        self.case_reprendre = QComboBox()
        self.case_reprendre.addItem("rouvrir le dernier tome", True)
        self.case_reprendre.addItem("repartir sur le premier projet", False)
        self.case_reprendre.setCurrentIndex(0 if etat.get("reprendre", True) else 1)
        forme.addRow("Tome", self.case_reprendre)
        # ⚠ **C'est ici qu'on revient sur un « Ne plus afficher »** — lot 40. Une case qui se
        # coche depuis une fenêtre et ne se décoche de nulle part est un réglage perdu ; celle
        # de la fenêtre de mise à jour annonce d'ailleurs qu'elle est réversible depuis les
        # Réglages, et cette ligne-ci est cette promesse.
        self.case_maj = QCheckBox("proposer la mise à jour quand une version plus récente "
                                  "existe")
        self.case_maj.setChecked(not bool(etat.get("maj_silencieuse", False)))
        self.case_maj.setToolTip(
            "Décoché, la fenêtre ne s'ouvre plus au démarrage. ⚠ Cela ne coupe PAS l'appel "
            "réseau : ce qui décide qu'une requête part est config.yaml > maj.verifier. Le "
            "bouton « Rechercher une mise à jour » du menu Aide continue de marcher dans les "
            "deux cas.")
        forme.addRow("Mise à jour", self.case_maj)
        layout.addWidget(boite)

        boite_ap = QGroupBox("Aperçus")
        forme_ap = QFormLayout(boite_ap)
        self.champ_plafond = QSpinBox()
        self.champ_plafond.setRange(16, 4096)
        self.champ_plafond.setSuffix(" Mo")
        self.champ_plafond.setValue(int(etat.get("plafond_mo") or 120))
        self.champ_plafond.setToolTip(
            "Mémoire maximale du cache d'aperçus composés. Un aperçu de planche coûte 1,37 s "
            "à recomposer (mesuré) : un plafond trop bas se paie en attente à chaque "
            "navigation.")
        self.champ_fenetre = QSpinBox()
        self.champ_fenetre.setRange(0, 60)
        self.champ_fenetre.setValue(int(etat.get("fenetre_apercu") or 10))
        self.champ_fenetre.setToolTip(
            "Nombre de planches autour de celle qu'on regarde dont l'aperçu est préparé "
            "d'avance. 0 = aucun préchargement.")
        forme_ap.addRow("Plafond du cache", self.champ_plafond)
        forme_ap.addRow("Planches préchargées", self.champ_fenetre)
        layout.addWidget(boite_ap)

        boite_llm = QGroupBox("Serveur LLM")
        forme_llm = QFormLayout(boite_llm)
        self.champ_serveur = QLineEdit(str(etat.get("serveur_llm") or ""))
        self.champ_serveur.setPlaceholderText(
            "vide = celui de config.yaml (http://localhost:11434/v1)")
        self.champ_serveur.setToolTip(
            "L'adresse du serveur compatible OpenAI (Ollama, LM Studio) que les runs "
            "appelleront. ⚠ Laisser VIDE ne coupe rien : cela veut dire « s'en remettre à "
            "config.yaml », qui reste la référence partagée." + SAUT_LIGNE
            + "⚠ 127.0.0.1 plutôt que localhost : mesuré le 2026-09-05, la résolution de "
            "« localhost » coûte 2,04 s contre 0,003 s — un facteur 680 payé à chaque sonde.")
        self.bouton_tester = QPushButton("Tester")
        self.bouton_tester.setToolTip(
            "Demande la liste des modèles à cette adresse. Ne lève jamais et ne modifie rien.")
        self.bouton_tester.clicked.connect(self._tester_serveur)
        self.verdict_serveur = QLabel("")
        self.verdict_serveur.setWordWrap(True)
        theme.poser_role(self.verdict_serveur, "faible")
        ligne_llm = QHBoxLayout()
        ligne_llm.addWidget(self.champ_serveur, 1)
        ligne_llm.addWidget(self.bouton_tester)
        forme_llm.addRow("Adresse", ligne_llm)
        forme_llm.addRow("", self.verdict_serveur)
        layout.addWidget(boite_llm)

        note_llm = QLabel(
            "⚠ Angelith n'a <b>pas besoin</b> d'un serveur pour tout faire : détection, "
            "nettoyage, OCR, relettrage et saisie manuelle n'en appellent aucun. Pour traduire "
            "un tome sans serveur, mets <code>llm.actif: false</code> dans "
            "<code>config.yaml</code> ou coche « sans LLM » au lancement — les bulles sortent "
            "vides, prêtes à saisir dans la Retouche.")
        note_llm.setWordWrap(True)
        theme.poser_role(note_llm, "faible")
        layout.addWidget(note_llm)

        note = QLabel(
            "Ces deux valeurs ont aussi une clé dans <code>config.yaml</code> "
            "(<code>gui.apercu.plafond_mo</code>, <code>gui.apercu.fenetre</code>). Ce qui est "
            "réglé ici l'emporte pour cette installation ; le fichier reste la référence "
            "partagée.")
        note.setWordWrap(True)
        theme.poser_role(note, "faible")
        layout.addWidget(note)

        self.boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.boutons.accepted.connect(self.accept)
        self.boutons.rejected.connect(self.reject)
        layout.addWidget(self.boutons)

    def _tester_serveur(self) -> None:
        """Demande la liste des modèles à l'adresse saisie. **Ne lève jamais.**

        ⚠ Sur le fil d'affichage, et c'est assumé ici : la boîte est modale, l'utilisateur
        vient de cliquer, et `core.modeles.lister` est plafonné à 6,0 s. C'est l'inverse des
        sondes de l'accueil (`gui/sondes.py`), qui partent dans le fil de travail parce
        qu'elles sont sur le chemin du premier pixel."""
        from core import modeles as mdl

        adresse = self.champ_serveur.text().strip() or "http://localhost:11434/v1"
        self.verdict_serveur.setText("Interrogation…")
        self.bouton_tester.setEnabled(False)
        try:
            catalogue = mdl.lister(adresse)
        finally:
            self.bouton_tester.setEnabled(True)
        if catalogue.etat == mdl.JOIGNABLE:
            noms = ", ".join(m.nom for m in catalogue.modeles[:6]) or "aucun modèle déclaré"
            self.verdict_serveur.setText(f"● joignable — {len(catalogue.modeles)} modèle(s) : "
                                         f"{noms}")
        else:
            self.verdict_serveur.setText(f"○ {catalogue.detail or 'injoignable'}")

    def valeurs(self) -> dict:
        return {"reprendre": bool(self.case_reprendre.currentData()),
                "plafond_mo": int(self.champ_plafond.value()),
                "fenetre_apercu": int(self.champ_fenetre.value()),
                # ⚠ `None` et non `""` quand le champ est vide : c'est la règle des trois états
                # de `gui/parametres.py` — absent veut dire « s'en remettre à config.yaml », pas
                # « efface l'adresse ». Une chaîne vide persistée couperait le serveur.
                "serveur_llm": self.champ_serveur.text().strip() or None,
                # ⚠ La case dit OUI à la proposition, la clé dit OUI au silence : elles sont
                # inverses l'une de l'autre. Une case « ne plus afficher » dans une page de
                # réglages se lirait à l'envers de toutes ses voisines, qui activent.
                "maj_silencieuse": not self.case_maj.isChecked()}


# --------------------------------------------------------------------------- #
#  L34.3 — le dépôt guidé
# --------------------------------------------------------------------------- #

class DialogueDepotGuide(QDialog):
    """Le parcours d'un lâcher, jusqu'au bout du geste. **Ne crée rien, ne copie rien.**

    Les cinq écrans du `PLAN-34` L34.3 tiennent dans une seule boîte, dans l'ordre où on se
    les pose : *ce que j'ai lu* → *où ça va* → *ce qui s'y trouve déjà* → *le coût* → *on y
    va ?*. Les séparer en un assistant à cinq pages ferait cliquer quatre fois sur « Suivant »
    pour un geste qui doit rester à la portée d'un glisser-déposer.

    ⚠ **Toute la lecture vit dans `gui/depot_guide.py`, sans Qt.** Ici on affiche et on
    collecte : la liste d'un `.cbz` sans l'extraire, le refus d'un `.cbr` sans `unrar`, la
    collision nommée, le poids annoncé — tout cela se teste sans écran. C'est la même
    séparation que `DialogueNouveauProjet` tient déjà avec `manga/creation_projet.py`.

    ⚠ **La case « Déplacer » est décochée, et elle le reste.** Elle n'est pas persistée dans
    les réglages : un lâcher qui vide le dossier d'origine est irréversible, et le souvenir
    d'une case cochée la semaine dernière est exactement ce qu'il ne faut pas avoir ici. Même
    parti que `force` et `dry_run` dans `gui/reglages.py:NON_PERSISTES`.
    """

    #: L'ordre de tabulation, déclaré — cf. le critère 6 du `PLAN-19`.
    PARCOURS: tuple[str, ...] = ("champ_projet", "champ_tome", "choix_format",
                                 "choix_langue", "case_deplacer", "boutons")

    def __init__(self, config: dict, chemins, parent=None):
        super().__init__(parent)
        self.config = config
        self._chemins = [Path(c) for c in chemins]
        self._format_choisi = False
        self.setWindowTitle("Importer ces sources")
        self.setMinimumWidth(640)
        self._construire()
        self._relire()

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)

        boite_lu = QGroupBox("Ce que j'ai lu")
        vlu = QVBoxLayout(boite_lu)
        self.resume = QLabel("—")
        self.resume.setWordWrap(True)
        vlu.addWidget(self.resume)
        self.detail = QListWidget()
        self.detail.setMaximumHeight(110)
        self.detail.setToolTip(
            "Le contenu d'une archive est listé SANS l'extraire : son index suffit.")
        vlu.addWidget(self.detail)
        colonne.addWidget(boite_lu)

        boite_ou = QGroupBox("Où ça va")
        forme = QFormLayout(boite_ou)
        self.champ_projet = QLineEdit()
        self.champ_projet.textChanged.connect(self._relire)
        self.champ_tome = QLineEdit()
        self.champ_tome.textChanged.connect(self._relire)
        # ⚠ **Manga et webtoon seulement.** Ce parcours part d'un LÂCHER d'images ou
        # d'archive ; un roman n'entre pas par là, et lui offrir « Light novel » serait une
        # impasse. La création d'un roman passe par « Nouveau projet ».
        self.choix_format = QComboBox()
        for fmt in crea.FORMATS_PLANCHES:
            self.choix_format.addItem(fmt, fmt)
        self.choix_format.activated.connect(self._format_active)
        self.choix_format.currentTextChanged.connect(self._relire)
        self.choix_langue = QComboBox()
        self.choix_langue.addItem("(langue par défaut du projet)", None)
        for code in ("JAP", "ENG", "CHINOIS", "ESP", "FR"):
            self.choix_langue.addItem(code, code)
        self.choix_langue.currentIndexChanged.connect(self._relire)
        forme.addRow("Projet", self.champ_projet)
        forme.addRow("Tome", self.champ_tome)
        forme.addRow("Format", self.choix_format)
        forme.addRow("Langue source", self.choix_langue)
        colonne.addWidget(boite_ou)

        self.cible = QLabel("—")
        self.cible.setWordWrap(True)
        theme.poser_role(self.cible, "mono")
        self.cible.setAccessibleName("Dossier de destination")
        colonne.addWidget(self.cible)

        self.collision = QLabel("")
        self.collision.setWordWrap(True)
        theme.poser_role(self.collision, "avertissement")
        colonne.addWidget(self.collision)

        self.case_deplacer = QCheckBox(
            "Déplacer au lieu de copier — vide le dossier d'origine")
        self.case_deplacer.setToolTip(
            "Décoché par défaut, et volontairement : un import qui vide le dossier d'origine "
            "est irréversible. À cocher seulement pour une archive volumineuse dont tu ne "
            "veux pas garder deux exemplaires.")
        self.case_deplacer.toggled.connect(self._relire)
        colonne.addWidget(self.case_deplacer)

        self.annonce = QLabel("—")
        self.annonce.setWordWrap(True)
        colonne.addWidget(self.annonce)

        self.erreur = QLabel("")
        self.erreur.setWordWrap(True)
        theme.poser_role(self.erreur, "erreur")
        colonne.addWidget(self.erreur)

        self.boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.boutons.button(QDialogButtonBox.Ok).setText("Importer")
        self.boutons.accepted.connect(self._valider)
        self.boutons.rejected.connect(self.reject)
        colonne.addWidget(self.boutons)
        _poser_parcours(self, self.PARCOURS)

    # ------------------------------------------------------------------ #

    def _format_active(self, *_args) -> None:
        """L'utilisateur a choisi le format lui-même : la proposition tirée du chemin ne doit
        plus le réécrire à la frappe suivante dans « Tome »."""
        self._format_choisi = True

    def _relire(self) -> None:
        """Recalcule le plan à chaque frappe. **Aucune règle n'est écrite ici.**"""
        plan = dg.planifier(
            self.config, self._chemins,
            projet=self.champ_projet.text().strip(),
            tome=self.champ_tome.text().strip(),
            format=self.choix_format.currentData(),
            langue=self.choix_langue.currentData(),
            deplacer=self.case_deplacer.isChecked())
        self._plan = plan

        self.resume.setText(plan.lecture.resume)
        self.detail.clear()
        for archive in plan.lecture.archives:
            self.detail.addItem(archive.libelle)
        isolees = [f for f in plan.lecture.fichiers
                   if f.suffix.lower() not in dg.ARCHIVES]
        for fichier in isolees[:40]:
            self.detail.addItem(fichier.name)
        if len(isolees) > 40:
            self.detail.addItem(f"… et {len(isolees) - 40} autre(s)")
        for avertissement in plan.lecture.avertissements:
            self.detail.addItem(f"⚠ {avertissement}")

        # ⚠ Les propositions ne sont posées qu'une fois, et jamais par-dessus une saisie :
        # une boîte qui réécrit ce qu'on tape est une boîte qu'on ne peut pas corriger.
        if not self.champ_projet.text().strip() and plan.lecture.projet_propose:
            self.champ_projet.setText(plan.lecture.projet_propose)
        if not self.champ_tome.text().strip() and plan.lecture.tome_propose:
            self.champ_tome.setText(plan.lecture.tome_propose)
        if not self._format_choisi:
            self.choix_format.setCurrentText(plan.lecture.format_propose)

        self.cible.setText(str(plan.destination.dossier))
        self.collision.setText(plan.destination.message)
        self.annonce.setText(plan.annonce)
        refus = plan.refus
        self.erreur.setText(refus)
        self.boutons.button(QDialogButtonBox.Ok).setEnabled(plan.executable and not refus)

    def _valider(self) -> None:
        """Un déplacement se confirme. **C'est le seul geste irréversible de cette boîte.**"""
        if self.case_deplacer.isChecked():
            reponse = QMessageBox.question(
                self, "Déplacer les fichiers ?",
                f"{len(self._plan.lecture.fichiers)} fichier(s) vont être DÉPLACÉS vers"
                + SAUT_LIGNE + str(self._plan.destination.dossier) + SAUT_LIGNE
                + "Le dossier d'origine sera vidé de ces fichiers. C'est irréversible.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reponse != QMessageBox.Yes:
                return
        self.accept()

    # ------------------------------------------------------------------ #

    def plan(self):
        """Le plan courant — celui que la fenêtre exécute, sur le fil de travail."""
        return self._plan

    def description(self) -> dict:
        """La même forme que `DialogueNouveauProjet.description()`, plus `deplacer`.

        C'est délibéré : `Fenetre._creer_projet` consomme un seul dictionnaire, quelle que
        soit la boîte qui l'a produit. Deux formes de description feraient deux chemins de
        création, et l'un des deux vieillirait."""
        plan = self._plan
        return {"projet": plan.destination.projet, "tome": plan.destination.tome,
                "chemins": list(self._chemins), "format": plan.destination.format,
                "langue": plan.destination.langue, "deplacer": plan.deplacer}


# --------------------------------------------------------------------------- #
#  L34.4 — l'export du glossaire
# --------------------------------------------------------------------------- #

class DialogueExportGlossaire(QDialog):
    """Choisir un format, voir ce qu'il perd, écrire le fichier.

    ⚠ **Le format d'archive et les vues ne sont pas présentés à égalité.** Le YAML est
    proposé en premier et sélectionné par défaut ; les deux autres affichent, avant l'écriture
    et non après, la liste de ce qu'ils ne portent pas. « Exporter en CSV » ne doit pas
    laisser croire qu'on peut réimporter le CSV sans perte — le `PLAN-34` L34.4 le dit, et
    c'est la raison d'être de ce panneau plutôt que d'un simple `QFileDialog`.

    ⚠ **Cette boîte n'écrit rien tant qu'on n'a pas validé**, et l'écriture ne touche jamais
    `sources/<Projet>/glossaire.yaml` : elle produit un fichier NEUF, ailleurs. Un export qui
    modifierait sa source serait le seul geste irréversible de ce lot.
    """

    PARCOURS: tuple[str, ...] = ("choix_format", "champ_destination", "bouton_parcourir",
                                 "boutons")

    def __init__(self, config: dict, projet: str, tome: str = "", parent=None):
        super().__init__(parent)
        self.config = config
        self.projet, self.tome = projet, tome
        self.source = biblio.chemin_glossaire(config, projet)
        self.setWindowTitle(f"Exporter le glossaire — {projet}")
        self.setMinimumWidth(660)
        self._construire()
        self._maj()

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)

        self.entete = QLabel("—")
        self.entete.setWordWrap(True)
        colonne.addWidget(self.entete)

        forme = QFormLayout()
        self.choix_format = QComboBox()
        for code, _ext, libelle in gexport.FORMATS:
            self.choix_format.addItem(libelle, code)
        self.choix_format.currentIndexChanged.connect(self._maj)
        forme.addRow("Format", self.choix_format)

        ligne = QHBoxLayout()
        self.champ_destination = QLineEdit()
        self.champ_destination.textChanged.connect(self._maj_bouton)
        self.bouton_parcourir = QPushButton("Parcourir…")
        self.bouton_parcourir.clicked.connect(self._choisir)
        ligne.addWidget(self.champ_destination, 1)
        ligne.addWidget(self.bouton_parcourir)
        forme.addRow("Fichier", ligne)
        colonne.addLayout(forme)

        self.pertes = QLabel("")
        self.pertes.setWordWrap(True)
        theme.poser_role(self.pertes, "avertissement")
        colonne.addWidget(self.pertes)

        self.erreur = QLabel("")
        self.erreur.setWordWrap(True)
        theme.poser_role(self.erreur, "erreur")
        colonne.addWidget(self.erreur)

        self.boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.boutons.button(QDialogButtonBox.Ok).setText("Exporter")
        self.boutons.accepted.connect(self._exporter)
        self.boutons.rejected.connect(self.reject)
        colonne.addWidget(self.boutons)
        _poser_parcours(self, self.PARCOURS)

    # ------------------------------------------------------------------ #

    def _format(self) -> str:
        return self.choix_format.currentData() or gexport.ARCHIVE

    def _maj(self) -> None:
        format = self._format()
        try:
            entrees = gexport.compter(gexport.lire_brut(self.source))
        except (OSError, RuntimeError) as err:
            self.entete.setText(str(err))
            self.pertes.setText("")
            self.boutons.button(QDialogButtonBox.Ok).setEnabled(False)
            return

        depuis = f" (depuis « {self.tome} »)" if self.tome else ""
        self.entete.setText(
            f"Glossaire de l'œuvre « {self.projet} »{depuis} — <b>{entrees} entrée(s)</b>."
            "<br>Il est propre à l'ŒUVRE : le fichier exporté vaut pour tous ses tomes, pas "
            "seulement pour celui d'où part l'export.")

        pertes = gexport.PERTES.get(format, ())
        cible = glossary.cible_du_run()
        if pertes:
            self.pertes.setText(
                "⚠ VUE, PAS ARCHIVE. Ce fichier ne portera pas :<ul>"
                + "".join(f"<li>{p.format(cible=cible)}</li>" for p in pertes)
                + "</ul>La même liste sera écrite EN TÊTE du fichier produit, pour que "
                  "quiconque le rouvre dans six mois la lise aussi.")
        else:
            self.pertes.setText(
                "Format d'ARCHIVE : l'aller-retour est garanti, et testé sur les glossaires "
                "réels du dépôt. C'est celui à choisir pour sauvegarder ou transmettre.")

        propose = gexport.nom_propose(self.projet, self.tome, format)
        actuel = self.champ_destination.text().strip()
        if not actuel or Path(actuel).name.startswith(f"{self.projet}"):
            dossier = Path(actuel).parent if actuel else Path.home()
            self.champ_destination.setText(str(dossier / propose))
        self._maj_bouton()

    def _maj_bouton(self) -> None:
        self.erreur.setText("")
        self.boutons.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.champ_destination.text().strip()) and self.source.is_file())

    def _choisir(self) -> None:
        format = self._format()
        extension = gexport.EXTENSIONS[format]
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter le glossaire", self.champ_destination.text().strip(),
            f"Glossaire (*{extension});;Tous les fichiers (*)")
        if chemin:
            self.champ_destination.setText(chemin)

    def _exporter(self) -> None:
        destination = Path(self.champ_destination.text().strip())
        if destination.exists():
            reponse = QMessageBox.question(
                self, "Écraser ?", f"{destination} existe déjà." + SAUT_LIGNE
                + "L'écraser ?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reponse != QMessageBox.Yes:
                return
        try:
            self.ecrit = gexport.exporter(
                self.source, destination, self._format(),
                projet=self.projet, tome=self.tome)
        except (OSError, RuntimeError, ValueError) as err:
            self.erreur.setText(str(err))
            return
        self.accept()


# --------------------------------------------------------------------------- #
#  L34.5 — les sorties d'un tome, réunies
# --------------------------------------------------------------------------- #

class DialogueSorties(QDialog):
    """Ce qui existe sur le disque pour ce tome — **et ce qui n'existe pas**.

    ⚠ **Aucun bouton d'ici ne lance un run.** Une sortie absente affiche la commande qui la
    produirait ET son coût, en toutes lettres, à recopier. C'est le point du `PLAN-34` L34.5 :
    un « Exporter en PSD » qui relancerait le rendu de 131 planches sans le dire serait la
    pire action coûteuse sans garde-fou de l'application. Le seul geste actif est « Ouvrir »,
    qui passe par `_ouvrir_dans_le_systeme` — celui qui sert déjà pour `build/`, la bible et
    les illustrations.

    ⚠ **Le refus de PSD au-delà de la limite du format est un ÉTAT**, pas une erreur : la
    2.6.0 a livré ce refus propre plutôt qu'un fichier corrompu, et l'afficher en rouge
    défiterait ce choix.
    """

    #: `(chemin)` — la fenêtre ouvre, le dialogue ne sait pas comment.
    demande_ouverture = Signal(object)

    def __init__(self, panneau, parent=None):
        super().__init__(parent)
        self.panneau = panneau
        self.setWindowTitle(f"Sorties — {panneau.projet} / {panneau.tome}")
        self.resize(900, 520)
        self._construire()

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)

        entete = QLabel(
            f"<b>{self.panneau.projet} / {self.panneau.tome}</b> — "
            f"{self.panneau.resume}<br>"
            "Ce panneau <b>montre</b> ce qui existe ; il ne produit aucun format nouveau et "
            "ne lance aucun run.")
        entete.setWordWrap(True)
        colonne.addWidget(entete)

        for avertissement in self.panneau.avertissements:
            ligne = QLabel(avertissement)
            ligne.setWordWrap(True)
            theme.poser_role(ligne, "avertissement")
            colonne.addWidget(ligne)

        self.table = QTreeWidget()
        self.table.setColumnCount(4)
        self.table.setHeaderLabels(["Sortie", "État", "Ce qu'il y a", "Comment l'obtenir"])
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        for sortie in self.panneau.sorties:
            geste = so.commande(sortie, self.panneau.projet, self.panneau.tome)
            colonne_geste = "" if sortie.existe else (
                f"{geste}   ({sortie.cout})" if geste else sortie.cout)
            item = QTreeWidgetItem([sortie.libelle,
                                    so.LIBELLES_ETAT.get(sortie.etat, sortie.etat),
                                    sortie.resume, colonne_geste])
            infobulle = "\n".join(x for x in (
                str(sortie.chemin) if sortie.chemin else "",
                sortie.note,
                f"Coût annoncé : {sortie.cout}" if sortie.cout and sortie.cout != "—" else "",
            ) if x)
            for rang in range(4):
                item.setToolTip(rang, infobulle)
            item.setData(0, Qt.UserRole, sortie.chemin if sortie.existe else None)
            self.table.addTopLevelItem(item)
        for rang in range(4):
            self.table.resizeColumnToContents(rang)
        self.table.currentItemChanged.connect(lambda *_: self._maj_ouvrir())
        self.table.itemDoubleClicked.connect(lambda *_: self._ouvrir())
        colonne.addWidget(self.table, 1)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        theme.poser_role(self.note, "faible")
        colonne.addWidget(self.note)

        pied = QHBoxLayout()
        self.bouton_ouvrir = QPushButton("Ouvrir")
        self.bouton_ouvrir.setToolTip(
            "Ouvre la sortie sélectionnée dans l'application du système. Aucune œuvre n'est "
            "copiée ni exportée hors de build/.")
        self.bouton_ouvrir.clicked.connect(self._ouvrir)
        pied.addWidget(self.bouton_ouvrir)
        pied.addStretch(1)
        boutons = QDialogButtonBox(QDialogButtonBox.Close)
        boutons.rejected.connect(self.reject)
        pied.addWidget(boutons)
        colonne.addLayout(pied)
        self._maj_ouvrir()

    def _selection(self):
        item = self.table.currentItem()
        return None if item is None else item.data(0, Qt.UserRole)

    def _maj_ouvrir(self) -> None:
        item = self.table.currentItem()
        self.bouton_ouvrir.setEnabled(self._selection() is not None)
        rang = self.table.indexOfTopLevelItem(item) if item is not None else -1
        sortie = self.panneau.sorties[rang] if 0 <= rang < len(self.panneau.sorties) else None
        self.note.setText(sortie.note if sortie is not None else "")

    def _ouvrir(self) -> None:
        chemin = self._selection()
        if chemin is not None:
            self.demande_ouverture.emit(chemin)


# --------------------------------------------------------------------------- #
#  L40.2 — réintégrer un tome corrigé par un tiers
# --------------------------------------------------------------------------- #

class DialogueImportBuild(QDialog):
    """Choisir un dossier reçu, voir ce qui va changer, décider. **N'écrit rien.**

    ⚠ L'écriture est soumise au fil de travail par la fenêtre, comme toute copie : un import
    de planches rendues porte sur des gigaoctets, et `shutil.copytree` les recopie à la vitesse
    du disque.

    ## ⚠ Ce que la case « planches rendues » coûte, mesuré

    Sur les 10 tomes manga du corpus (16,54 Go), les checkpoints — c'est-à-dire **tout le
    travail humain** — pèsent **0,1 % du poids** et représentent **72 % des fichiers**. Un tome
    fait 0,7 à 3,3 Go ; ses corrections, 0,3 à 4,0 Mo. La case est donc **décochée** :
    transférer 3 Go pour 4 Mo de corrections doit être un choix explicite.
    """

    def __init__(self, cible: Path, parent=None):
        super().__init__(parent)
        self.cible = Path(cible)
        self._plan = None
        self.setWindowTitle("Importer un tome corrigé")
        self.setMinimumWidth(620)
        self._construire()

    def _construire(self) -> None:
        layout = QVBoxLayout(self)

        explication = QLabel(
            "Réintègre le travail d'un relecteur — répliques corrigées, zones retouchées, "
            "textes déplacés. <b>Rien n'est supprimé</b> : une planche présente ici et absente "
            "du paquet est conservée. Ce qui est remplacé part d'abord dans "
            "<code>.avant-import-&lt;date&gt;/</code>.")
        explication.setWordWrap(True)
        layout.addWidget(explication)

        boite = QGroupBox("Le dossier reçu")
        vsrc = QVBoxLayout(boite)
        ligne = QHBoxLayout()
        self.champ_source = QLineEdit()
        self.champ_source.setPlaceholderText(
            "le dossier build/<Projet>/<Tome>/ que le relecteur a renvoyé")
        self.champ_source.textChanged.connect(self._relire)
        bouton = QPushButton("Parcourir…")
        bouton.clicked.connect(self._choisir)
        ligne.addWidget(self.champ_source, 1)
        ligne.addWidget(bouton)
        vsrc.addLayout(ligne)
        self.case_rendus = QCheckBox("importer aussi les planches rendues (plusieurs Go)")
        self.case_rendus.setToolTip(
            "Mesuré le 2026-09-06 sur le corpus : les corrections pèsent 0,1 % d'un dossier "
            "build/, les planches rendues et les PSD le reste. Décochée, l'importation ne "
            "transfère que le travail humain.")
        self.case_rendus.toggled.connect(lambda _c: self._relire())
        vsrc.addWidget(self.case_rendus)
        layout.addWidget(boite)

        self.cible_affichee = QLabel(f"Vers : {self.cible}")
        self.cible_affichee.setWordWrap(True)
        theme.poser_role(self.cible_affichee, "faible")
        layout.addWidget(self.cible_affichee)

        self.annonce = QLabel("Choisis un dossier pour voir ce qui changerait.")
        self.annonce.setWordWrap(True)
        layout.addWidget(self.annonce)

        self.detail = QListWidget()
        self.detail.setMaximumHeight(180)
        layout.addWidget(self.detail)

        self.boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.boutons.button(QDialogButtonBox.Ok).setText("Importer")
        self.boutons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.boutons.accepted.connect(self.accept)
        self.boutons.rejected.connect(self.reject)
        layout.addWidget(self.boutons)

    def _choisir(self) -> None:
        dossier = QFileDialog.getExistingDirectory(self, "Dossier reçu du relecteur")
        if dossier:
            self.champ_source.setText(dossier)

    def _relire(self) -> None:
        """Recalcule le plan à chaque frappe. ⚠ Lecture seule — `planifier` n'écrit rien."""
        import import_build as imp

        self.detail.clear()
        source = self.champ_source.text().strip()
        if not source or not Path(source).is_dir():
            self._plan = None
            self.annonce.setText("Choisis un dossier pour voir ce qui changerait.")
            self.boutons.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        self._plan = imp.planifier(source, self.cible,
                                   avec_rendus=self.case_rendus.isChecked())
        self.annonce.setText(self._plan.annonce())
        # ⚠ `"erreur"` ou `"faible"`, **jamais `""`** : `theme.poser_role` refuse un rôle
        # inconnu par un `KeyError`, et la chaîne vide en est un. Le défaut a été trouvé par
        # `tests/test_gui_dialogues_maj.py` : l'exception coupait `_relire` juste après cette
        # ligne, si bien que la liste des planches restait vide et que le bouton « Importer »
        # ne s'activait jamais — un aperçu muet et un import impossible, sans un mot à l'écran.
        theme.poser_role(self.annonce, "erreur" if self._plan.refus else "faible")
        for planche in self._plan.planches:
            if planche.etat == imp.IDENTIQUE:
                continue
            motifs = f" — {', '.join(planche.motifs)}" if planche.motifs else ""
            self.detail.addItem(f"page {planche.index:04d} : "
                                f"{imp.PHRASES_ETAT[planche.etat]}{motifs}")
        self.boutons.button(QDialogButtonBox.Ok).setEnabled(self._plan.executable)

    def plan(self):
        """Le plan retenu, ou `None`. C'est ce que la fenêtre soumet au fil de travail."""
        return self._plan


# --------------------------------------------------------------------------- #
#  Mise à jour — lot 40
# --------------------------------------------------------------------------- #

class DialogueMaj(QDialog):
    """Proposer une version plus récente. **Ne télécharge rien, n'installe rien.**

    C'est une fenêtre de décision, et la décision porte sur trois choses qui doivent être
    lisibles AVANT le clic : ce qui va arriver, ce que ça pèse, et ce que la vérification
    d'empreinte protège — cf. `gui/vue_maj.PHRASE_INTEGRITE`, affichée telle quelle. Le
    téléchargement part ensuite dans le fil de travail, sous la conduite de `gui/fenetre.py` :
    292 Mio à 2,5 Mio/s font ~115 s (mesuré le 2026-09-06), ce qui n'a rien à faire sur le fil
    d'affichage.

    ## Les deux boutons, et pourquoi il n'y en a pas trois

    « Installer maintenant » n'apparaît que si l'installation est **gelée** et si la release
    porte **et** l'installeur **et** son `SHA256SUMS.txt` (`vue_maj.installable`). Sinon il n'y
    a qu'« Ouvrir la page » : un installeur qu'on ne peut pas vérifier ne vaut pas mieux qu'un
    lien, et il vaut moins qu'un lien parce qu'il aurait l'air vérifié.

    ## ⚠ « Ne plus afficher » masque LA FENÊTRE, pas la capacité

    La case écrit `maj_silencieuse` dans `.angelith/interface.json`. L'appel réseau, lui, reste
    commandé par `config.yaml > maj.verifier`, et le bouton « Rechercher une mise à jour » d'« À
    propos » continue de marcher. La phrase sous la case le dit à l'écran, parce qu'une case
    qui couperait silencieusement plus que ce qu'elle annonce serait un opt-out que personne ne
    saurait retrouver."""

    def __init__(self, resultat, installee: str, *, gele: bool, parent=None):
        super().__init__(parent)
        self.resultat = resultat
        self._gele = bool(gele)
        self._choix = "plus_tard"
        self.setWindowTitle("Mise à jour disponible")
        self.resize(720, 420)

        layout = QVBoxLayout(self)
        titre = QLabel(f"<b>Angelith {resultat.version} est disponible</b>")
        layout.addWidget(titre)

        self.zone = QPlainTextEdit()
        self.zone.setReadOnly(True)
        self.zone.setPlainText(vmaj.phrase_proposition(resultat, installee, gele=self._gele))
        theme.poser_role(self.zone, "mono")
        layout.addWidget(self.zone, 1)

        self.case_silence = QCheckBox("Ne plus afficher cette fenêtre au démarrage")
        layout.addWidget(self.case_silence)
        note = QLabel(
            "Cette case masque la fenêtre, pas la vérification : le bouton « Rechercher une "
            "mise à jour » du menu Aide continue de marcher, et la case est réversible depuis "
            "les Réglages. Pour ne plus rien envoyer du tout, c'est config.yaml > "
            "maj.verifier.")
        note.setWordWrap(True)
        layout.addWidget(note)

        boutons = QDialogButtonBox()
        if vmaj.installable(resultat, gele=self._gele):
            installer = boutons.addButton("Installer maintenant",
                                          QDialogButtonBox.AcceptRole)
            installer.clicked.connect(lambda: self._decider("installer"))
        page = boutons.addButton("Ouvrir la page des releases", QDialogButtonBox.ActionRole)
        page.clicked.connect(lambda: self._decider("page"))
        plus_tard = boutons.addButton("Plus tard", QDialogButtonBox.RejectRole)
        plus_tard.clicked.connect(self.reject)
        layout.addWidget(boutons)

    def _decider(self, choix: str) -> None:
        self._choix = choix
        self.accept()

    def choix(self) -> str:
        """`"installer"`, `"page"` ou `"plus_tard"`. ⚠ Fermer la fenêtre à la croix rend
        `"plus_tard"` : une fenêtre qu'on chasse n'est pas un consentement."""
        return self._choix

    def silencieuse(self) -> bool:
        """La case est-elle cochée ? Lue même quand le choix est « plus tard » — c'est le cas
        le plus fréquent : « pas maintenant, et ne me le redemande plus »."""
        return bool(self.case_silence.isChecked())
