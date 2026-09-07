# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Panneau de lancement des runs — light novel, manga, webtoon.

## Pourquoi les deux briques ici, alors que l'éditeur ne connaît que le manga

Parce que « lancer un run » est le même geste des deux côtés : choisir un projet, un tome, une
étape de reprise, et regarder défiler un journal. Les deux orchestrateurs ont **la même
signature de retour** (`True` = terminé, `False` = arrêté proprement) et le même protocole de
`Reporter` — c'est ce qui rend un lanceur commun honnête plutôt que bricolé. L'ÉDITION, elle,
n'a de sens que sur des planches : elle reste au manga.

## Une instance par destination (lot 31), et la brique n'est plus un choix

Depuis le lot 31, la fenêtre construit **trois** instances de ce panneau — « Light novel »,
« Manga », « Webtoon » — chacune avec sa brique et son format FIXÉS à la construction. La liste
déroulante « Brique » disparaît alors : la destination l'a déjà dite, et la reposer dans le
panneau donnerait deux endroits où répondre à la même question, dont un qui peut contredire le
pane.

⚠ **Le repli « brique libre » a été RETIRÉ au lot 33 (2026-09-05).** Il survivait depuis le
lot 31 sans appelant, au motif qu'il rendrait « la nouvelle forme vérifiable contre l'ancienne
dans un test » — aucun test ne l'a jamais fait. Il est devenu franchement faux avec le
formulaire déclaré : les paramètres offerts dépendent du panneau (`gui/parametres.py`), donc
changer de brique en cours de session devrait reconstruire tout le formulaire. Un second
chemin non testé qui reconstruit un formulaire est exactement ce que ce lot supprime.
`brique` est donc **obligatoire**.

⚠ **Le webtoon n'est pas une brique**, et le code doit le dire. `run_manga.py` porte
`--format {manga,webtoon}` : c'est un **format** du même orchestrateur, avec ses seuils propres
(`manga.formats`, `SENS_PAR_DEFAUT`, le découpage des bandes très allongées). `ETAT_BRIQUES` ne
connaît pas de brique « webtoon », et il a raison. La destination Webtoon **est** donc ce
panneau avec `format_planche="webtoon"` — aucun code de traitement n'est dupliqué, le drapeau
équivalent est nommé dans l'interface, et la réserve mesurée du corpus de bandes est affichée
en tête (`RESERVE_WEBTOON`).

## Le formulaire est DÉCLARÉ, pas écrit ici (lot 33)

Les dix-neuf paramètres déclarés dans `gui/parametres.py` — jusqu'à **seize** sur une même
destination — sont dessinés par `gui/formulaire.py`. Ce module ne pose plus que ce qu'un générateur ne peut pas savoir : la
CIBLE (projet, tome), les profils, les boutons, et le récapitulatif de lancement. C'est ce qui
a fait passer le lanceur manga de sept réglages utiles à quatorze sans qu'il grossisse.

Ce qui n'a **pas** changé, et ne doit pas : les noms d'attributs des widgets (`case_force`,
`champ_lot`, `champ_fenetre_hauteur`) sont déclarés dans la table et posés par le générateur,
donc les tests d'interface du lot 18 continuent de les nommer.

## Ce que le panneau ne réécrit pas

`config.yaml` n'est jamais modifié. Les réglages d'un run (taille de lot, raisonnement, étape
de reprise, planche unique, `--force`, le modèle) sont des mutations du dictionnaire **en
mémoire**, exactement comme les drapeaux de `run_manga.py`. Les 800 lignes de commentaires du
fichier sont sa documentation ; un aller-retour `yaml.safe_dump` les effacerait toutes, et ce
serait la seule chose que l'interface aurait vraiment cassée.
`tests/test_gui_lanceur_config.py` en garde l'empreinte SHA-256 avant et après un run lancé
avec **chaque** paramètre modifié.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from core import modeles as mod

from . import extinction as ext
from . import formulaire as frm
from . import parametres as par
from . import profils as prf
from . import theme

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

#: La réserve du webtoon, **mesurée**, affichée en tête de la destination Webtoon.
#:
#: ⚠ Elle n'est pas décorative. `docs/mesures/webtoon-2026-08-26.md` donne 15,1-17,0 % de
#: fausses détections pour une cible de 5 %, et un sous-comptage à 5,9 bulles par bande là où
#: 25-35 seraient attendues — le tout sur **un seul** webtoon du corpus (*webtoon A*
#: Chap.11), qui est aussi le seul volume à source latine : les deux effets sont confondus.
#: Offrir le webtoon au même rang que le manga sans afficher cet écart promettrait plus que ce
#: qui est mesuré, et le dépôt refuse ça ailleurs (`docs/chiffres-de-reference.md`).
RESERVE_WEBTOON = (
    "⚠ Le webtoon est le MÊME orchestrateur que le manga, avec --format webtoon : sens de "
    "lecture et découpage des bandes très allongées. Ce n'est pas une brique séparée.\n"
    "⚠ Et il est moins bien mesuré que le manga. Sur le seul webtoon du corpus "
    "(docs/mesures/webtoon-2026-08-26.md, 2026-08-26) : 15,1 à 17,0 % de fausses détections "
    "pour une cible de 5 %, et 5,9 bulles détectées par bande là où 25 à 35 seraient "
    "attendues. Ce tirage est aussi le seul à source latine du dépôt : les deux effets sont "
    "confondus, et aucun des deux n'est isolé."
)


def panneau_de(brique: str, format_planche: str | None) -> str:
    """L'identifiant de panneau d'une destination de lancement.

    ⚠ Une fonction, et pas un dictionnaire dans `gui/fenetre.py` : c'est ELLE qui encode que
    « webtoon » est un format et non une brique, et elle doit être lisible depuis le panneau
    comme depuis la fenêtre."""
    if format_planche == "webtoon":
        return par.WEBTOON
    return par.LIGHT_NOVEL if brique == "ln" else par.MANGA


class PanneauLanceur(QWidget):
    """Choix du run à lancer. N'exécute rien lui-même : la fenêtre tient le fil.

    `brique` et `format_planche` sont **fixés à la construction** : c'est la destination qui
    les dit, et la liste déroulante « Brique » disparaît alors."""

    demande_run = Signal(dict)
    demande_arret = Signal()
    demande_assemblage = Signal()
    #: « Rafraîchir la liste des modèles » — la fenêtre la relance dans le FIL DE TRAVAIL.
    #: Un GET sur un endpoint arrêté coûte des secondes ; sur le fil d'affichage, ce serait la
    #: fenêtre gelée. La règle est celle de `gui/sondes.py`, et elle est absolue.
    demande_modeles = Signal()

    def __init__(self, config: dict, parent=None, *, brique: str,
                 format_planche: str | None = None, reserve: str = ""):
        super().__init__(parent)
        if brique not in ("manga", "ln"):
            raise KeyError(f"brique inconnue : {brique!r}")
        self.config = config
        self._brique_fixee = brique
        self._format = format_planche
        self._reserve = reserve
        self._panneau = panneau_de(brique, format_planche)
        self._catalogue = mod.inconnu()
        self.formulaire = frm.Formulaire(
            self._panneau, defauts_config=self._defauts_config(),
            choix=self._choix_dynamiques())
        self._construire()

    # ------------------------------------------------------------------ #
    #  Ce que la table ne peut pas savoir : les défauts lus dans config.yaml
    # ------------------------------------------------------------------ #

    def _defauts_config(self) -> dict:
        """`{identifiant: valeur du fichier}`, pour que « selon config.yaml » dise le chiffre.

        ⚠ Résolu par la MÊME chaîne que le run (`manga/formats.py:config_format`), jamais
        recopié : deux lectures qui divergeraient feraient dire à l'écran l'inverse de ce que
        le run fait."""
        defauts: dict = {}
        manga = self.config.get("manga") or {}
        lot = (manga.get("lot") or {}).get("planches")
        if lot:
            defauts["lot"] = int(lot)
        if self._format:
            from manga import formats as fmt_mod
            detection = fmt_mod.config_format(self.config, self._format, "detection")
            for cle, repli in (("fenetre_hauteur", 2160), ("fenetre_recouvrement", 900)):
                defauts[cle] = int(detection.get(cle) or repli)
        return defauts

    def _choix_dynamiques(self) -> dict:
        """Les listes que la table ne peut pas geler : étapes, langues, modèles."""
        etapes = ETAPES_MANGA if self._brique_fixee == "manga" else ETAPES_LN
        return {
            "etape": tuple((f"{libelle}  —  {aide}" if aide else libelle, valeur)
                           for libelle, valeur, aide in etapes),
            "langue": self._langues(),
            "modele": self._entrees_modeles(),
        }

    def _langues(self) -> tuple[tuple[str, object], ...]:
        """Les dossiers de langue source connus de `config.yaml`, plus « selon config.yaml ».

        ⚠ La première entrée ne vaut PAS « japonais » : elle ne pose pas `langue` du tout, ce
        qui laisse `run_manga` déduire la langue du sous-dossier trouvé sous
        `sources/<Projet>/<Tome>/<format>/`, puis de `manga.langue_source`. Poser une valeur
        par défaut ici ferait lire `JAP` sur un tome rangé en `ENG/`."""
        dossiers = ((self.config.get("langues") or {}).get("dossiers") or {})
        entrees = [("selon config.yaml", None)]
        for code in sorted(dossiers):
            entrees.append((f"{code}  —  {dossiers[code]}", code))
        return tuple(entrees)

    def _entrees_modeles(self) -> tuple[tuple[str, object], ...]:
        """La liste déroulante des modèles, telle que la sonde permet de l'écrire.

        ⚠ **La liste n'est jamais filtrée sur une devinette.** Quand la capacité vision est
        inconnue, elle est écrite « inconnu » à côté du nom — et la brique manga, qui en
        dépend, l'avertit au récapitulatif. Filtrer sur `vision is not False` reviendrait à
        cacher des modèles parfaitement utilisables sur un serveur qui ne sait pas répondre à
        la question."""
        entrees: list[tuple[str, object]] = [("selon config.yaml", None)]
        for modele in self._catalogue.modeles:
            entrees.append((modele.ligne(), modele.identifiant))
        return tuple(entrees)

    # ------------------------------------------------------------------ #

    def _construire(self) -> None:
        layout = QVBoxLayout(self)

        if self._reserve:
            # En TÊTE, avant le bouton. Une réserve affichée sous le bouton « Lancer » est une
            # réserve qu'on lit après avoir engagé le GPU.
            self.bandeau = QLabel(self._reserve)
            self.bandeau.setWordWrap(True)
            self.bandeau.setAccessibleName("Réserve mesurée de ce format")
            theme.poser_role(self.bandeau, "avertissement")
            layout.addWidget(self.bandeau)

        layout.addWidget(self._groupe_cible())
        for groupe in self.formulaire.construire(self):
            layout.addWidget(groupe)
        self._completer_groupe_bande()
        self._completer_groupe_modele()
        layout.addWidget(self._groupe_profils())

        boutons = QHBoxLayout()
        self.bouton_lancer = QPushButton("Lancer")
        self.bouton_lancer.clicked.connect(self._lancer)
        self.bouton_arreter = QPushButton("Arrêter proprement")
        self.bouton_arreter.setToolTip(
            "Le run s'arrête à la prochaine frontière propre — une planche, ou un lot entier si "
            "le lot > 1 — et tout ce qui est fait est conservé.\n"
            "Même mécanisme que `--stop` : un fichier STOP dans le dossier de build.")
        self.bouton_arreter.setEnabled(False)
        self.bouton_arreter.clicked.connect(self.demande_arret.emit)
        # ⚠ Le bouton « Assembler » n'émet plus directement : il passe par l'action de menu,
        # qui demande confirmation. Réassembler réécrit le CBZ et le PDF, et le faire sur un
        # simple clic était l'une des trois actions coûteuses sans garde-fou (L18.8.4).
        self.bouton_assembler = QPushButton("Assembler CBZ/PDF")
        self.bouton_assembler.setToolTip("Réassemble les sorties depuis pages_out/, sans rien "
                                         "retraduire ni relettrer.")
        boutons.addWidget(self.bouton_lancer)
        boutons.addWidget(self.bouton_arreter)
        boutons.addWidget(self.bouton_assembler)
        layout.addLayout(boutons)
        layout.addStretch(1)

        self._poser_parcours()
        self._remplir_projets()
        self._recharger_profils()

    def _groupe_cible(self) -> QGroupBox:
        """Projet et tome — la seule partie du formulaire qui ne se déclare pas.

        Elle se REMPLIT depuis le disque, et sa liste dépend de la brique : `modele_tome`
        côté manga, `pipeline.sources` côté light novel. Un générateur de table ne sait pas
        faire ça, et lui apprendre à le faire ferait entrer le disque dans une table gelée."""
        groupe = QGroupBox("Le tome à traiter")
        forme = QFormLayout(groupe)
        self.choix_brique = QComboBox()
        self.choix_brique.addItem("Manga", "manga")
        self.choix_brique.addItem("Light novel", "ln")
        index = self.choix_brique.findData(self._brique_fixee)
        self.choix_brique.setCurrentIndex(index)
        # ⚠ Le widget est GARDÉ mais caché, pas supprimé : `brique()` le lit, et le remplacer
        # par un attribut ferait deux chemins pour la même question.
        self.choix_brique.setVisible(False)
        self.choix_projet = QComboBox()
        self.choix_projet.setMinimumWidth(220)
        self.choix_projet.currentTextChanged.connect(self._remplir_tomes)
        self.choix_tome = QComboBox()
        self.choix_tome.setMinimumWidth(160)
        forme.addRow("Projet", self.choix_projet)
        forme.addRow("Tome", self.choix_tome)
        return groupe

    def _completer_groupe_bande(self) -> None:
        """La phrase qui dit ce que le FORMAT impose et que l'interface ne change pas.

        ## Ce qui est MODIFIABLE, et ce qui ne l'est pas — `PLAN-33` L33.5

        Le partage n'est pas arbitraire : **un panneau ne propose que ce que `run_manga.py`
        sait faire**. C'est la promesse de `gui/__init__.py` — « un tome retouché ici se
        relance à l'identique avec run_manga.py » — et un bouton sans équivalent en ligne de
        commande la casserait.

        · **hauteur de fenêtre** et **recouvrement** ⇒ `--fenetre-hauteur` /
          `--fenetre-recouvrement`, nées au lot 31 précisément pour que ces deux champs
          existent sans créer de chemin propre à l'interface ;
        · **le seuil d'entrée du découpage**, le **sens de lecture** et le **PSD du scan
          d'origine** ⇒ **affichés avec leurs chiffres, pas modifiables**. Aucun des trois n'a
          d'équivalent en ligne de commande, et le sens de lecture, changé sur un tome déjà
          détecté, ferait reprendre toutes ses planches à la détection — une invalidation de
          cache, que l'interdit n° 1 du dépôt veut voir ne jamais se produire par accident."""
        groupe = self.formulaire.groupe("bande")
        if groupe is None:
            return
        self.etiquette_bande = QLabel(self._phrase_bande())
        self.etiquette_bande.setWordWrap(True)
        self.etiquette_bande.setAccessibleName("Réglages de bande non modifiables")
        theme.poser_role(self.etiquette_bande, "faible")
        groupe.layout().addRow(self.etiquette_bande)

    def _phrase_bande(self) -> str:
        """Les trois réglages de bande non modifiables, **avec leurs chiffres**.

        Résolus depuis `config.yaml` par la même chaîne que le run — jamais recopiés."""
        from manga import formats as fmt_mod

        sens = fmt_mod.sens_lecture(self.config, self._format)
        rendu = fmt_mod.config_format(self.config, self._format, "rendu")
        detection = fmt_mod.config_format(self.config, self._format, "detection")
        psd = bool(rendu.get("psd_original"))
        lisible = {"gauche_droite": "gauche → droite",
                   "droite_gauche": "droite → gauche"}.get(sens, sens)
        ratio = detection.get("fenetre_ratio_min")
        occupation = detection.get("fenetre_occupation_min")
        if occupation:
            entree = (f"une planche est découpée quand son petit côté occupe moins de "
                      f"{occupation} px du canevas du réseau après letterbox")
        else:
            entree = (f"une planche est découpée à partir d'un rapport hauteur/largeur de "
                      f"{ratio if ratio is not None else 3.0} (un manga est à ~1,4) ; à "
                      f"input_size 640 cela vaut 213,3 px de petit côté vu par le réseau")
        return (
            f"Imposé par le format, et non modifiable ici :\n"
            f"· seuil d'entrée du découpage — {entree}. Le régler appartient à config.yaml "
            f"(manga.formats.{self._format}.detection), où chaque chiffre porte sa mesure ;\n"
            f"· sens de lecture {lisible} (numérotation des bulles ET ComicInfo.xml) ; "
            f"scan d'origine dans le PSD : {'oui' if psd else 'non'}.\n"
            f"Le sens de lecture change la numérotation des bulles : le modifier sur un tome "
            f"déjà détecté ferait reprendre toutes ses planches à la détection. Il vit donc "
            f"dans config.yaml (manga.rendu.sens_lecture), et nulle part ailleurs.")

    def _completer_groupe_modele(self) -> None:
        """Le bouton de rafraîchissement et la phrase d'état de la liste des modèles."""
        groupe = self.formulaire.groupe("modele")
        if groupe is None:
            return
        self.bouton_modeles = QPushButton("Rafraîchir la liste")
        self.bouton_modeles.setToolTip(
            "Redemande la liste au serveur (GET <llm.base_url>/models). ⚠ Aucun "
            "téléchargement n'est déclenché : installer un modèle est un geste séparé.")
        self.bouton_modeles.clicked.connect(self.demande_modeles.emit)
        self.etiquette_modeles = QLabel(self._catalogue.phrase())
        self.etiquette_modeles.setWordWrap(True)
        self.etiquette_modeles.setAccessibleName("État de la liste des modèles")
        theme.poser_role(self.etiquette_modeles, "faible")
        groupe.layout().addRow(self.bouton_modeles)
        groupe.layout().addRow(self.etiquette_modeles)

    def poser_modeles(self, catalogue) -> None:
        """Reçoit le verdict de la sonde de modèles. **Appelée depuis le fil d'affichage**,
        avec un résultat calculé ailleurs — comme `PanneauAccueil.poser_sondes`."""
        self._catalogue = catalogue
        self.formulaire.reposer_choix("modele", self._entrees_modeles())
        if hasattr(self, "etiquette_modeles"):
            self.etiquette_modeles.setText(catalogue.phrase())

    # ------------------------------------------------------------------ #
    #  Les profils — L33.4
    # ------------------------------------------------------------------ #

    def _groupe_profils(self) -> QGroupBox:
        groupe = QGroupBox("Profils")
        ligne = QHBoxLayout(groupe)
        self.choix_profil = QComboBox()
        self.choix_profil.setMinimumWidth(220)
        self.choix_profil.setAccessibleName("Profil de lancement")
        self.choix_profil.setToolTip(
            "Un jeu de réglages nommé, rangé dans .angelith/profils.json.\n"
            "⚠ Un profil ne porte JAMAIS « Tout refaire depuis zéro », « Simuler sans "
            "traduire », « Éteindre le PC », ni le projet et le tome : c'est un raccourci de "
            "saisie, pas un mandat.")
        self.choix_profil.currentIndexChanged.connect(self._appliquer_profil)
        self.bouton_profil_enregistrer = QPushButton("Enregistrer…")
        self.bouton_profil_enregistrer.setToolTip(
            "Enregistre les réglages actuels sous un nom, pour cette destination.")
        self.bouton_profil_enregistrer.clicked.connect(self._enregistrer_profil)
        self.bouton_profil_supprimer = QPushButton("Supprimer")
        self.bouton_profil_supprimer.clicked.connect(self._supprimer_profil)
        ligne.addWidget(self.choix_profil, 1)
        ligne.addWidget(self.bouton_profil_enregistrer)
        ligne.addWidget(self.bouton_profil_supprimer)
        return groupe

    def _recharger_profils(self, selection: str = "") -> None:
        self.choix_profil.blockSignals(True)
        self.choix_profil.clear()
        self.choix_profil.addItem("(aucun profil)", None)
        for profil in prf.pour(self._panneau):
            self.choix_profil.addItem(profil.nom, profil.nom)
            self.choix_profil.setItemData(
                self.choix_profil.count() - 1,
                prf.resume(self._panneau, profil.valeurs), 3)      # Qt.ToolTipRole
        if selection:
            index = self.choix_profil.findData(selection)
            if index >= 0:
                self.choix_profil.setCurrentIndex(index)
        self.choix_profil.blockSignals(False)

    def _appliquer_profil(self) -> None:
        nom = self.choix_profil.currentData()
        if not nom:
            return
        for profil in prf.pour(self._panneau):
            if profil.nom == nom:
                self.formulaire.appliquer(profil.valeurs)
                return

    def _enregistrer_profil(self) -> None:
        nom, ok = QInputDialog.getText(self, "Enregistrer un profil",
                                       "Nom du profil (« nuit complète », « reprise "
                                       "rapide »…) :")
        if not (ok and nom.strip()):
            return
        prf.enregistrer(nom.strip(), self._panneau, self.formulaire.valeurs_persistables())
        self._recharger_profils(nom.strip())

    def _supprimer_profil(self) -> None:
        nom = self.choix_profil.currentData()
        if not nom:
            return
        prf.supprimer(nom, self._panneau)
        self._recharger_profils()

    # ------------------------------------------------------------------ #

    #: L'ordre de tabulation du panneau — **déclaré**, comme le veut le critère 6 du
    #: `PLAN-19`, et non déduit de l'ordre de construction.
    #:
    #: ⚠ C'est l'UNION des quatre panneaux : `_poser_parcours` saute ce qui n'existe pas sur
    #: l'instance (`hasattr`), parce qu'un ordre qui exigerait tous ses widgets interdirait à
    #: un panneau d'avoir deux formes. `tests/test_gui_lanceur.py` vérifie qu'aucun attribut
    #: déclaré dans `gui/parametres.py` n'y manque — c'est ce qui empêche un paramètre ajouté
    #: demain de tomber en fin de parcours sans qu'on l'ait décidé.
    PARCOURS: tuple[str, ...] = (
        "bandeau", "choix_brique", "choix_projet", "choix_tome",
        "choix_etape", "champ_page", "choix_langue",
        "case_force", "case_dry", "case_sans_llm", "case_verbose",
        "champ_lot", "choix_think",
        "champ_conf", "champ_iou",
        "champ_fenetre_hauteur", "champ_fenetre_recouvrement",
        "choix_modele", "bouton_modeles",
        "case_veille", "case_extinction", "champ_delai",
        "choix_profil", "bouton_profil_enregistrer", "bouton_profil_supprimer",
        "bouton_lancer", "bouton_arreter", "bouton_assembler",
    )

    def _poser_parcours(self) -> None:
        widgets = [getattr(self, nom) for nom in self.PARCOURS if hasattr(self, nom)]
        for avant, apres in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(avant, apres)

    # ------------------------------------------------------------------ #

    def brancher_actions(self, actions: dict, brancher) -> None:
        """Reçoit le catalogue d'actions de la fenêtre (cf. `Fenetre._construire_menu`)."""
        brancher(self.bouton_assembler, "assembler")

    def _remplir_projets(self) -> None:
        """La liste des projets **de la brique choisie**.

        Côté manga on filtre sur les tomes qui portent des planches (`modele_tome`) ; côté
        light novel on prend `pipeline.sources`, qui est ce que `run.py` lit. Un même dépôt
        peut porter les deux, et un projet purement roman doit apparaître ici."""
        courant = self.choix_projet.currentText()
        self.choix_projet.blockSignals(True)
        self.choix_projet.clear()
        self.choix_projet.addItems(self._projets())
        if courant and self.choix_projet.findText(courant) >= 0:
            self.choix_projet.setCurrentText(courant)
        self.choix_projet.blockSignals(False)
        self._remplir_tomes(self.choix_projet.currentText())

    def _projets(self) -> list[str]:
        if self.brique() == "manga":
            from .modele_tome import lister_projets
            return lister_projets(self.config)
        from pathlib import Path

        from pipeline.sources import list_projects
        try:
            return list_projects(Path(self.config["chemins"]["sources"]))
        except (KeyError, OSError):
            return []

    def _remplir_tomes(self, projet: str) -> None:
        courant = self.choix_tome.currentText()
        self.choix_tome.clear()
        if not projet:
            return
        if self.brique() == "manga":
            from .modele_tome import lister_tomes
            tomes = lister_tomes(self.config, projet)
        else:
            from pathlib import Path

            from pipeline.sources import list_volumes
            try:
                tomes = list_volumes(Path(self.config["chemins"]["sources"]), projet)
            except (KeyError, OSError):
                tomes = []
        self.choix_tome.addItems(tomes)
        if courant and self.choix_tome.findText(courant) >= 0:
            self.choix_tome.setCurrentText(courant)

    def brique(self) -> str:
        return self.choix_brique.currentData()

    def panneau(self) -> str:
        """L'identifiant de panneau de `gui/parametres.py` — ce que le formulaire suit."""
        return self._panneau

    def format_planche(self) -> str | None:
        """Le format imposé par la destination, ou `None` — l'équivalent de `--format`."""
        return self._format

    def verbose(self) -> bool:
        """Lu aussi par le bouton « Appliquer » de l'éditeur : un relettrage doit laisser la
        même trace qu'un run, sinon `perf.log` raconte un tome à trous."""
        return self.case_verbose.isChecked()

    def cible(self) -> tuple[str, str]:
        return self.choix_projet.currentText(), self.choix_tome.currentText()

    def viser(self, projet: str, tome: str) -> bool:
        """Suivre la retouche — mais seulement côté manga, et sans jamais forcer.

        Rend `False` quand la cible est introuvable : la carte « Reprendre » de l'accueil s'en
        sert pour DIRE qu'un tome des récents a disparu, plutôt que d'ouvrir un panneau réglé
        sur autre chose sans un mot."""
        if self.choix_projet.findText(projet) < 0:
            self._remplir_projets()
        if self.choix_projet.findText(projet) < 0:
            return False
        self.choix_projet.setCurrentText(projet)
        if self.choix_tome.findText(tome) < 0:
            return False
        self.choix_tome.setCurrentText(tome)
        return True

    def marquer_en_cours(self, en_cours: bool) -> None:
        self.bouton_lancer.setEnabled(not en_cours)
        self.bouton_assembler.setEnabled(not en_cours)
        self.bouton_arreter.setEnabled(en_cours)

    # ------------------------------------------------------------------ #
    # L18.7 — ce qui se persiste, et ce qui ne se persiste JAMAIS
    # ------------------------------------------------------------------ #

    def reglages(self) -> dict:
        """L'état à retenir. **Ni `force`, ni `dry_run`, ni `shutdown`.**

        Une case « Tout refaire depuis zéro » cochée hier et retrouvée cochée aujourd'hui,
        c'est un tome relancé depuis la détection : des heures de GPU pour un état que personne
        n'a redemandé. Une case « Éteindre le PC » retrouvée cochée, c'est pire : c'est une
        machine éteinte. Le filtre est doublé dans `reglages.nettoyer()`, qui retire ces clés à
        l'écriture ET à la lecture — un fichier édité à la main ne doit pas plus armer un run
        qu'une case oubliée."""
        etat = self.formulaire.valeurs_persistables()
        etat["brique"] = self.brique()
        return etat

    def reglages_persistables(self) -> dict:
        """Comme `reglages()`, sans la brique — elle est FIXÉE par la destination.

        ⚠ Un état qui n'est plus un choix ne se persiste pas : le relire demain le
        réappliquerait par-dessus ce que la destination a déjà décidé, et le jour où les deux
        divergeraient, c'est le fichier qui gagnerait."""
        etat = self.reglages()
        etat.pop("brique", None)
        return etat

    def appliquer_reglages(self, etat: dict) -> None:
        self.formulaire.appliquer(self._compatibilite(etat))

    @staticmethod
    def _compatibilite(etat: dict) -> dict:
        """Relit un fichier écrit AVANT le lot 33, sans changer la version du format.

        ⚠ Une seule clé a changé de nature : `think` était l'INDEX de la liste déroulante, il
        est maintenant sa VALEUR. Bumper `reglages.VERSION` aurait fait perdre au passage la
        taille de fenêtre, les colonnes et les récents de tout le monde — pour une clé. Les
        cinq index historiques sont donc traduits ici, et le commentaire qui les nomme est le
        seul endroit du dépôt où l'ancien ordre survit.

        `[None, False, "low", "medium", "high"]` — l'ordre du menu depuis le lot 18."""
        historique = [None, False, "low", "medium", "high"]
        propre = dict(etat)
        pensee = propre.get("think")
        if isinstance(pensee, int) and not isinstance(pensee, bool):
            propre["think"] = historique[pensee] if 0 <= pensee < len(historique) else None
        return propre

    # ------------------------------------------------------------------ #

    def demande(self) -> par.Demande:
        """Ce que le formulaire demande au socle, sur une COPIE PROFONDE de la config.

        La copie est profonde parce que les réglages de ce run ne doivent pas rester collés à
        la config partagée avec l'éditeur, qui construit ses propres agents."""
        return par.appliquer(copy.deepcopy(self.config), self._panneau,
                             self.formulaire.valeurs(), format_planche=self._format)

    def reglages_bande(self) -> dict:
        """`{clé de détection: valeur}` pour ce qui est réglé à l'écran. Vide = ne rien poser.

        `0` veut dire « selon config.yaml », donc **absence de clé** — et non « zéro pixel »."""
        valeurs = self.formulaire.valeurs()
        reglages = {}
        for cle in ("fenetre_hauteur", "fenetre_recouvrement"):
            if valeurs.get(cle):
                reglages[cle] = int(valeurs[cle])
        return reglages

    def _appliquer_bande(self, config: dict) -> None:
        """Écrit les réglages de bande dans la copie de config du run.

        ⚠ **Dans le bloc du FORMAT**, exactement comme `run_manga._appliquer_options_bande` —
        et c'est `parametres.appliquer()` qui le fait désormais, pour les deux chemins à la
        fois. Cette méthode reste le point d'entrée nommé par les tests du lot 31."""
        reglages = self.reglages_bande()
        if not reglages:
            return
        cible = config.setdefault("manga", {})
        if self._format:
            cible = cible.setdefault("formats", {}).setdefault(self._format, {})
        cible.setdefault("detection", {}).update(reglages)

    def _lancer(self) -> None:
        projet, tome = self.cible()
        if not (projet and tome):
            return
        # ⚠ La demande est rangée sur le panneau AVANT la confirmation, plutôt que passée en
        # argument : `_confirmer(projet, tome)` est la signature que les tests d'interface du
        # lot 18 remplacent pour sauter la boîte, et l'élargir ferait échouer un test qui a
        # raison de ne pas connaître le lot 33.
        demande = self._derniere_demande = self.demande()
        if not self._confirmer(projet, tome):
            return
        self.demande_run.emit({
            "brique": self.brique(), "projet": projet, "tome": tome,
            "config": demande.config,
            # ⚠ `format_planche=None` côté manga = « ne rien imposer », comme l'absence de
            # `--format` en ligne de commande : l'orchestrateur déduit alors le format des
            # dimensions des planches. Seule la destination Webtoon pose une valeur.
            **demande.arguments,
            "energie": demande.energie,
        })

    # ------------------------------------------------------------------ #

    def _confirmer(self, projet: str, tome: str) -> bool:
        """L18.8.4 — le récapitulatif avant un run.

        ⚠ **On ne chiffre PAS la durée d'un run**, et le lot 33 garde ce refus : « aucune
        constante mesurée ne couvre un run complet, dont le coût dépend du nombre de planches,
        du modèle et de l'étape — l'annoncer serait inventer un chiffre ». Ce qui s'affiche
        ici est ce qui est **mesuré et publié**, et chaque chiffre porte son dénominateur : le
        coût de `--force` vient de la table (`gui/parametres.py`), celui du fenêtrage des
        9 bandes de `config.yaml`, le délai d'extinction de ce qu'on vient de saisir.

        La demande est celle que `_lancer` vient de ranger dans `_derniere_demande` ; elle
        est recalculée quand il n'y en a pas — c'est le cas des tests du lot 31, qui appellent
        `_confirmer(projet, tome)` directement."""
        demande = getattr(self, "_derniere_demande", None) or self.demande()
        valeurs = self.formulaire.valeurs()
        etape = self.choix_etape.currentText().split("  —  ")[0]
        page = demande.arguments.get("page")
        portee = "tout le tome"
        if page:
            portee = ("la planche " if self.brique() == "manga" else "le chapitre ") + str(page)
        lignes = [f"Brique : {self.choix_brique.currentText()}"
                  + (f" (--format {self._format})" if self._format else ""),
                  f"Tome : {projet} / {tome}",
                  f"Reprendre à : {etape}",
                  f"Portée : {portee}"]

        # Les paramètres coûteux, avec le coût que la TABLE déclare — donc avec son
        # dénominateur, ou pas du tout.
        for parametre in par.pour(self._panneau):
            if parametre.genre != par.BASCULE or not valeurs.get(parametre.identifiant):
                continue
            if parametre.identifiant == "verbose":
                continue
            ligne = parametre.libelle
            if parametre.cout:
                ligne = f"⚠ {ligne} — {parametre.cout}"
            lignes.append(ligne)

        for cle, valeur in self.reglages_bande().items():
            lignes.append(f"Découpage de la bande : {cle} = {valeur} px")
        for cle in ("conf", "iou"):
            if demande.arguments.get(cle) is not None:
                lignes.append(f"Seuil de détection {cle} = {demande.arguments[cle]} — "
                              f"la détection de cette planche est refaite")
        if valeurs.get("langue"):
            lignes.append(f"Langue source lue : {valeurs['langue']}")
        lignes.extend(self._lignes_modele(demande))
        if valeurs.get("shutdown"):
            lignes.append(ext.phrase_confirmation(valeurs.get("shutdown_delay")))
        elif valeurs.get("keep_awake"):
            lignes.append("La veille du PC est empêchée pendant le run, et levée à la fin.")

        boite = QMessageBox(self)
        boite.setWindowTitle("Lancer le run")
        boite.setText("Un run peut durer plusieurs heures et occupe le GPU jusqu'au bout.")
        boite.setInformativeText("\n".join(f"  · {ligne}" for ligne in lignes))
        lancer = boite.addButton("Lancer", QMessageBox.AcceptRole)
        boite.addButton("Annuler", QMessageBox.RejectRole)
        boite.setDefaultButton(lancer)
        boite.exec()
        return boite.clickedButton() is lancer

    def _lignes_modele(self, demande) -> list[str]:
        """Ce que le choix de modèle change, **agent par agent**.

        ⚠ Et l'avertissement vision, quand la brique en dépend. Le mode vision du traducteur
        manga lit la planche elle-même (`manga.modeles`, `orchestrator_manga`) : lancer un run
        manga sur un modèle dont la capacité vision est INCONNUE est possible, mais doit être
        dit. On ne filtre pas la liste sur une devinette ; on avertit sur ce qu'on ignore."""
        if not demande.agents_outrepasses:
            return []
        choisi = demande.agents_outrepasses[0][2]
        noms = ", ".join(nom for nom, _, _ in demande.agents_outrepasses)
        lignes = [f"⚠ Modèle de ce run : « {choisi} » — il outrepasse {noms} "
                  f"(config.yaml n'est pas modifié ; l'endpoint de chaque agent est gardé)."]
        modele = self._catalogue.par_identifiant(choisi)
        if self.brique() == "manga":
            if modele is None or modele.vision is None:
                lignes.append("⚠ Capacité vision INCONNUE pour ce modèle — la brique manga "
                              "en dépend (mode vision du traducteur). L'endpoint ne sait pas "
                              "la dire, et l'interface ne la devine pas.")
            elif modele.vision is False:
                lignes.append("⚠ Ce modèle n'est PAS vision-capable, et la brique manga en "
                              "dépend (mode vision du traducteur).")
        return lignes
