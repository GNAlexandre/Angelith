# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Le** générateur de formulaire — un seul, pour les quatre destinations de lancement.

## Pourquoi un générateur, et pas quatre formulaires

Parce que quatre formulaires écrits à la main divergent au troisième ajout. Le lanceur du lot
18 portait sept réglages utiles quand `run_manga.py` en offrait vingt-huit ; l'écart ne venait
pas d'une décision mais de l'absence d'un endroit où la décision se prend. Cet endroit est
`gui/parametres.py` ; ce module ne fait qu'en dessiner le contenu.

Ici, donc : **aucune décision**. Pas un libellé, pas un défaut, pas une borne. Tout vient de
la table. C'est ce qui rend la table testable sans Qt et ce module testable sans recopier la
table — la même séparation que `gui/actions.py` / `gui/fenetre.py:_construire_menu`.

## Trois règles que le générateur applique à TOUS les contrôles

1. **le libellé dit l'effet, l'infobulle porte l'équivalent en ligne de commande.** La règle
   est L18.9, et elle était appliquée à la main sur trois cases ; elle l'est maintenant sur
   les dix-neuf, parce qu'une seule fonction les fabrique ;
2. **« selon `config.yaml` » n'est pas une valeur par défaut, c'est une absence.** Pour un
   nombre, elle s'écrit sur la valeur SPÉCIALE du contrôle (son minimum), et le texte dit
   **ce que vaut** le défaut du fichier, pas seulement qu'il en existe un ;
3. **un paramètre qui en exige un autre est GRISÉ, jamais refusé après coup.** `--conf` et
   `--iou` n'ont de sens que sur une planche unique — c'est le contrat de `process_volume`,
   qui refuserait sinon après avoir chargé son modèle de détection. Le formulaire le dit
   pendant qu'on remplit, pas une fois le GPU engagé.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QLineEdit, QSpinBox, QWidget)

from . import parametres as par

#: Ce que le générateur ajoute à chaque infobulle qui a un équivalent. Une seule formulation,
#: parce que trois formulations pour la même promesse feraient douter de la promesse.
GABARIT_EQUIVALENT = "Équivaut à `{equivalent}` en ligne de commande."


class Formulaire:
    """Les contrôles d'un panneau, construits depuis `gui/parametres.py`.

    `panneau` — un identifiant de `parametres.PANNEAUX`.
    `defauts_config` — `{identifiant: valeur lue dans config.yaml}`, pour que le texte
    « selon config.yaml (2160 px) » dise le CHIFFRE. Une clé absente donne « selon
    config.yaml » tout court, ce qui reste vrai.
    `choix` — `{nom du jeu: ((libellé, valeur), …)}` pour les listes que la table ne peut pas
    geler : les étapes de reprise dépendent de la brique, les langues et les modèles de ce que
    le disque et le serveur répondent.
    """

    def __init__(self, panneau: str, *, defauts_config: dict | None = None,
                 choix: dict | None = None):
        if panneau not in par.PANNEAUX:
            raise KeyError(f"panneau inconnu : {panneau!r}")
        self.panneau = panneau
        self._defauts_config = dict(defauts_config or {})
        self._choix = dict(choix or {})
        self._widgets: dict[str, QWidget] = {}
        self._groupes: dict[str, QGroupBox] = {}

    # ------------------------------------------------------------------ #

    def construire(self, hote: QWidget) -> list[QGroupBox]:
        """Les groupes de ce panneau, dans l'ordre de `parametres.GROUPES`.

        ⚠ Chaque widget est aussi posé **en attribut de `hote`**, sous le nom déclaré par
        `Parametre.attribut`. Ce n'est pas de la commodité : `case_force`, `champ_lot` et
        `champ_fenetre_hauteur` sont les noms que les tests d'interface nomment depuis le lot
        18, et un lot qui ne promet aucune réécriture n'a pas à les renommer."""
        groupes = []
        for cle, titre, dedans in par.groupes_de(self.panneau):
            boite = QGroupBox(titre, hote)
            self._groupes[cle] = boite
            self._poser_lignes(hote, QFormLayout(boite), dedans, boite)
            groupes.append(boite)
        self._brancher_exigences()
        return groupes

    def construire_dans(self, hote: QWidget, forme, cle: str) -> None:
        """Pose les lignes d'UN groupe dans un `QFormLayout` **existant**.

        ⚠ C'est ce que l'atelier d'illustration utilise, et c'est délibérément la seule
        concession faite à sa forme : le `PLAN-33` interdit de le démembrer pour
        l'uniformiser, et lui imposer trois `QGroupBox` neufs au milieu d'un formulaire qui en
        a déjà deux serait exactement ça. Il reçoit donc les mêmes libellés, les mêmes bornes
        et les mêmes infobulles, dans sa propre mise en page."""
        dedans = tuple(p for p in par.pour(self.panneau) if p.groupe == cle)
        if not dedans:
            return
        self._poser_lignes(hote, forme, dedans, hote)
        self._brancher_exigences()

    def _poser_lignes(self, hote: QWidget, forme, dedans, parent) -> None:
        for parametre in dedans:
            widget = self._widget(parametre, parent)
            self._widgets[parametre.identifiant] = widget
            setattr(hote, parametre.attribut, widget)
            if parametre.genre == par.BASCULE:
                # Une case porte son libellé elle-même : une étiquette de plus le
                # doublerait, et un lecteur d'écran l'annoncerait deux fois.
                forme.addRow(widget)
            else:
                forme.addRow(parametre.libelle, widget)

    def widget(self, identifiant: str) -> QWidget | None:
        return self._widgets.get(identifiant)

    def groupe(self, cle: str) -> QGroupBox | None:
        """La boîte d'un groupe, pour qu'un panneau y ajoute ce qu'une table ne déclare pas —
        la phrase des réglages de bande non modifiables, le bouton de rafraîchissement des
        modèles. `None` quand ce panneau ne remplit pas ce groupe."""
        return self._groupes.get(cle)

    def parcours(self) -> tuple[str, ...]:
        """L'ordre de tabulation induit par la table — celui des groupes, puis des lignes.

        Le `PLAN-19` critère 6 demande UN ordre explicite PAR PANNEAU, « pas un par défaut qui
        se trouve juste ». Il est explicite : il se lit dans la table, et une ligne ajoutée
        demain au milieu d'un groupe le déplace là où on l'a écrite, pas ailleurs."""
        return tuple(p.attribut for p in par.pour(self.panneau))

    # ------------------------------------------------------------------ #

    def _widget(self, parametre, parent) -> QWidget:
        genre = parametre.genre
        if genre == par.BASCULE:
            widget = QCheckBox(parametre.libelle, parent)
            widget.setChecked(bool(parametre.defaut))
        elif genre == par.CHOIX:
            widget = QComboBox(parent)
            for libelle, valeur in self._entrees(parametre):
                widget.addItem(libelle, valeur)
        elif genre in (par.ENTIER, par.REEL):
            widget = QSpinBox(parent) if genre == par.ENTIER else QDoubleSpinBox(parent)
            if genre == par.REEL:
                widget.setDecimals(parametre.decimales)
            widget.setRange(parametre.minimum, parametre.maximum)
            widget.setSingleStep(parametre.pas)
            if parametre.suffixe:
                widget.setSuffix(parametre.suffixe)
            if parametre.special:
                widget.setSpecialValueText(self._special(parametre))
            widget.setValue(parametre.minimum if parametre.defaut is None
                            else parametre.defaut)
        else:
            widget = QLineEdit(parent)
            widget.setText(str(parametre.defaut or ""))
        widget.setAccessibleName(parametre.libelle)
        widget.setToolTip(self._infobulle(parametre))
        return widget

    def _entrees(self, parametre) -> tuple[tuple[str, object], ...]:
        """Les entrées d'une liste : celles de la table, ou celles que le panneau a fournies.

        ⚠ Un jeu dynamique ABSENT donne une liste à une seule entrée, « selon config.yaml ».
        C'est le comportement voulu quand le serveur ne répond pas : la liste des modèles est
        vide, et l'interface ne prétend pas en connaître. Elle ne se grise pas non plus — la
        valeur « selon config.yaml » reste le choix juste, et c'est déjà celui qui est fait."""
        if parametre.choix:
            return parametre.choix
        entrees = self._choix.get(parametre.choix_dynamiques)
        if not entrees:
            return (("selon config.yaml", None),)
        return tuple(entrees)

    def _special(self, parametre) -> str:
        defaut = self._defauts_config.get(parametre.identifiant)
        if "{defaut}" not in parametre.special:
            return parametre.special
        if defaut is None:
            # ⚠ On retire la parenthèse plutôt que d'écrire « selon config.yaml (None) ».
            # Un chiffre qu'on n'a pas lu ne s'affiche pas — règle §5 du contexte agent.
            return parametre.special.split(" (")[0]
        return parametre.special.format(defaut=defaut)

    def _infobulle(self, parametre) -> str:
        morceaux = [parametre.infobulle] if parametre.infobulle else []
        if parametre.cout:
            morceaux.append(f"Coût : {parametre.cout}.")
        if parametre.equivalent:
            morceaux.append(GABARIT_EQUIVALENT.format(equivalent=parametre.equivalent))
        return "\n".join(morceaux)

    # ------------------------------------------------------------------ #

    def _brancher_exigences(self) -> None:
        """Grise ce qui n'a pas de sens tant que son prérequis n'est pas rempli."""
        for parametre in par.pour(self.panneau):
            if not parametre.exige:
                continue
            source = self._widgets.get(parametre.exige)
            cible = self._widgets.get(parametre.identifiant)
            if source is None or cible is None:
                continue
            rafraichir = self._fabriquer_rafraichissement(parametre.exige, cible)
            for nom in ("toggled", "valueChanged", "currentIndexChanged"):
                signal = getattr(source, nom, None)
                if signal is not None:
                    signal.connect(lambda *_a, f=rafraichir: f())
                    break
            rafraichir()

    def _fabriquer_rafraichissement(self, exige: str, cible: QWidget):
        def rafraichir() -> None:
            cible.setEnabled(bool(self._valeur(exige)))
        return rafraichir

    # ------------------------------------------------------------------ #

    def valeurs(self) -> dict:
        """L'état du formulaire, `{identifiant: valeur}` — **toutes** les clés, `None` compris.

        ⚠ Un `None` y est une réponse (« selon config.yaml »), pas un trou : c'est
        `parametres.appliquer()` qui décide de ne pas poser la clé, et il ne peut le décider
        que si la valeur lui parvient."""
        return {p.identifiant: self._valeur(p.identifiant) for p in par.pour(self.panneau)}

    def _valeur(self, identifiant: str):
        widget = self._widgets.get(identifiant)
        parametre = par.par_identifiant(self.panneau, identifiant)
        if widget is None or parametre is None:
            return None
        if parametre.genre == par.BASCULE:
            return bool(widget.isChecked())
        if parametre.genre == par.CHOIX:
            return widget.currentData()
        if parametre.genre in (par.ENTIER, par.REEL):
            return widget.value()
        return widget.text()

    def appliquer(self, valeurs: dict) -> None:
        """Repose un état lu dans les réglages ou dans un profil. **Tolérant par décision** :
        une clé inconnue, hors bornes ou d'un type inattendu est ignorée, jamais fatale — le
        fichier est éditable à la main, et une disposition abîmée ne doit pas empêcher de
        lancer un run."""
        for parametre in par.pour(self.panneau):
            if parametre.identifiant not in valeurs:
                continue
            self._poser(parametre, valeurs[parametre.identifiant])
        self.reinitialiser_non_persistes()

    def _poser(self, parametre, valeur) -> None:
        widget = self._widgets.get(parametre.identifiant)
        if widget is None:
            return
        if parametre.genre == par.BASCULE:
            widget.setChecked(bool(valeur))
        elif parametre.genre == par.CHOIX:
            index = widget.findData(valeur)
            if index >= 0:
                widget.setCurrentIndex(index)
        elif parametre.genre in (par.ENTIER, par.REEL):
            if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
                return
            if widget.minimum() <= valeur <= widget.maximum():
                widget.setValue(valeur)
        elif isinstance(valeur, str):
            widget.setText(valeur)

    def reinitialiser_non_persistes(self) -> None:
        """Remet à leur défaut les paramètres qui ne se persistent pas.

        ⚠ **Explicitement, et pas « parce que c'est le défaut ».** `force`, `dry_run` et
        `shutdown` repartent à zéro à CHAQUE application de réglages, quoi qu'ait fait la
        session précédente et quoi que dise un fichier édité à la main. Le motif est chiffré
        pour le premier et vaut pour les trois : « des heures de GPU pour un état que personne
        n'a redemandé » — et, pour `shutdown`, une machine éteinte que personne n'a
        redemandée."""
        for identifiant in sorted(par.non_persistes(self.panneau)):
            parametre = par.par_identifiant(self.panneau, identifiant)
            if parametre is None:
                continue
            defaut = parametre.defaut
            self._poser(parametre, parametre.minimum if defaut is None else defaut)

    def valeurs_persistables(self) -> dict:
        """Ce qu'on écrit dans le fichier de réglages. Cf. `parametres.persistables`."""
        return par.persistables(self.panneau, self.valeurs())

    # ------------------------------------------------------------------ #

    def reposer_choix(self, nom: str, entrees) -> None:
        """Remplace les entrées d'un jeu dynamique — la liste des modèles, quand la sonde a
        fini de répondre. La sélection courante est **conservée si elle survit** : une liste
        qui arrive en retard ne doit pas défaire ce que l'utilisateur vient de choisir."""
        self._choix[nom] = tuple(entrees)
        for parametre in par.pour(self.panneau):
            if parametre.choix_dynamiques != nom:
                continue
            widget = self._widgets.get(parametre.identifiant)
            if widget is None:
                continue
            avant = widget.currentData()
            widget.blockSignals(True)
            widget.clear()
            for libelle, valeur in self._entrees(parametre):
                widget.addItem(libelle, valeur)
            index = widget.findData(avant)
            widget.setCurrentIndex(max(0, index))
            widget.blockSignals(False)
