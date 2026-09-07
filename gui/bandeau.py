# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Le bandeau de run** — où on en est, visible depuis n'importe quelle destination.

## Ce qu'il remplace

Une `QProgressBar` seule, en pied de fenêtre, qui affichait `%v / %m (%p%)` sur un
dénominateur changeant, et une barre d'état dont le message s'effaçait au bout de **huit
secondes**. Sur un run de plusieurs heures, l'étape en cours n'était donc lisible que dans un
journal replié à zéro par défaut, qui ne se déplie tout seul que sur un avertissement.

## Ce qu'il montre, et la règle qui décide de chaque ligne

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Manga · Mon Manga / Vol.2      Traduction et rendu (5/6)                    │
│ ███████████████████░░░░░░░░░░  planche 84 / 131   ~1 h 10 restantes         │
│ page_0084.png · lot 80→99 · 3 planches par appel        [Arrêter proprement]│
└────────────────────────────────────────────────────────────────────────────┘
```

1. **temps restant, jamais temps écoulé**, formaté par `avancement.duree_lisible`, qui
   refuse déjà la fausse précision ;
2. **indéterminé = ni pourcentage, ni temps.** `gui/avancement.lignes_de_run` le décide, pas
   ce widget : c'est une décision, et une décision se teste sans Qt ;
3. **l'objet en cours est nommé** — le « Updating address 3 of 50 » de NN/g ;
4. **`Arrêter proprement`**, jamais « Annuler » : le travail partiellement fait est conservé.
   Même libellé et même infobulle que le bouton du lanceur, parce que c'est le même geste ;
5. **rien n'y clignote**, et il disparaît quand aucun run ne tourne. Un bandeau vide en
   permanence devient du décor qu'on cesse de lire.

⚠ **Le journal reste.** Il n'est pas décoratif, et il est le seul endroit où l'on relit ce
qui s'est passé après un incident. Le bandeau ne le remplace pas ; il cesse d'obliger à le
lire pour savoir où on en est.

## La barre des tâches Windows — décision du 2026-09-05 : **rien**

`PLAN-32` L32.4(b) laissait la question ouverte et autorisait explicitement un « non ».
Constat relevé ce jour, sur l'installation de développement : **PySide6 6.11.1, Qt 6.11.1,
et aucun module `QtWinExtras` parmi les 64 livrés** (`pkgutil.iter_modules(PySide6.__path__)`).
`QWinTaskbarProgress` n'existe donc pas, et n'existera pas : le module a été retiré de Qt 6.

Restaient trois options. `ITaskbarList3` par `ctypes` — du COM Windows-spécifique dans un
dossier qui garde Linux et macOS en ligne de mire (`PLAN-20`), pour un confort ; une
dépendance tierce — refusée par le plan lui-même (« aucune dépendance tierce ajoutée pour ce
confort ») ; ou rien.

**Rien est livré**, parce que le besoin est déjà couvert : le titre de fenêtre porte
l'avancement en tête (`avancement.titre_de_fenetre`), et c'est très précisément l'usage que
Microsoft prête au titre — « optimize the title for display on the taskbar by concisely
placing the distinguishing information first ». La barre des tâches affiche ce titre.

⚠ Cette affirmation porte sa date parce qu'elle porte une VERSION. Le jour où PySide6 relivre
un `QtWinExtras`, `tests/test_gui_bandeau.py` le dira — il vérifie le constat, il ne le croit
pas sur parole.

## Ce qu'il ne fait pas

Aucune décision d'affichage. Il pose des chaînes que `gui/avancement.py` a calculées à partir
de l'état de `core/progression.py`. C'est la règle de couche du dépôt, et c'est ce qui rend
l'ensemble testable sans PySide6 — seul le câblage ci-dessous ne l'est pas.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from . import avancement as av, theme

#: L'infobulle du bouton d'arrêt. **Recopiée du lanceur, mot pour mot** : le bandeau propose
#: le même geste, et deux formulations pour une même garantie feraient douter de la garantie.
INFOBULLE_ARRET = (
    "Le run s'arrête à la prochaine frontière propre — une planche, ou un lot entier si "
    "le lot > 1 — et tout ce qui est fait est conservé.\n"
    "Même mécanisme que `--stop` : un fichier STOP dans le dossier de build.")


class BandeauDeRun(QWidget):
    """Trois lignes, une barre, deux boutons. Caché tant qu'aucun run n'a commencé."""

    demande_arret = Signal()
    demande_avertissements = Signal()
    #: « Retoucher les 3 planches » — L35.2, le chemin inverse de `editeur.demande_runs`.
    #: ⚠ Il n'apparaît qu'AU BILAN, jamais pendant : proposer d'éditer un tome qu'un
    #: `process_volume` est en train de réécrire donnerait deux vérités sur le même
    #: checkpoint, et c'est précisément ce que le verrou de run global interdit.
    demande_retouche = Signal()
    #: « Annuler l'extinction ». ⚠ Le seul geste du bandeau qui touche à la MACHINE et non au
    #: travail — d'où une quatrième ligne à lui, et un bouton qui n'est jamais mêlé aux trois
    #: autres. Cf. `gui/extinction.py`.
    demande_annulation_extinction = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Bandeau de run")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.Espacement.S, theme.Espacement.XS,
                                  theme.Espacement.S, theme.Espacement.XS)
        layout.setSpacing(theme.Espacement.XS)

        haut = QHBoxLayout()
        self.etiquette_cible = QLabel("")
        self.etiquette_cible.setAccessibleName("Tome en cours de traitement")
        self.etiquette_phase = QLabel("")
        self.etiquette_phase.setAccessibleName("Phase du run")
        theme.poser_role(self.etiquette_phase, "accent")
        haut.addWidget(self.etiquette_cible)
        haut.addStretch(1)
        haut.addWidget(self.etiquette_phase)
        layout.addLayout(haut)

        milieu = QHBoxLayout()
        self.barre = QProgressBar()
        self.barre.setAccessibleName("Avancement du run")
        # ⚠ `setTextVisible(False)` : le texte de la barre est le seul endroit où Qt sait
        # écrire `%p%`, et un pourcentage est précisément ce que ce lot refuse d'afficher
        # sur une fraction COMPTÉE. Le compte vit dans une étiquette à côté, où il porte son
        # unité et son dénominateur.
        self.barre.setTextVisible(False)
        self.barre.setRange(0, av.PAS_DE_BARRE)
        self.barre.setValue(0)
        self.etiquette_compte = QLabel("")
        self.etiquette_compte.setAccessibleName("Avancement compté")
        self.etiquette_restant = QLabel("")
        self.etiquette_restant.setAccessibleName("Temps restant estimé")
        theme.poser_role(self.etiquette_restant, "faible")
        milieu.addWidget(self.barre, 1)
        milieu.addWidget(self.etiquette_compte)
        milieu.addWidget(self.etiquette_restant)
        layout.addLayout(milieu)

        bas = QHBoxLayout()
        self.etiquette_objet = QLabel("")
        self.etiquette_objet.setAccessibleName("Objet en cours")
        self.etiquette_objet.setTextInteractionFlags(Qt.TextSelectableByMouse)
        theme.poser_role(self.etiquette_objet, "faible")
        self.bouton_avertissements = QPushButton("")
        self.bouton_avertissements.setToolTip(
            "Ouvre les avertissements de ce run, sans avoir à les retrouver dans le journal.")
        self.bouton_avertissements.clicked.connect(self.demande_avertissements.emit)
        self.bouton_avertissements.setVisible(False)
        self.bouton_retoucher = QPushButton("")
        self.bouton_retoucher.setToolTip(
            "Ouvre la destination « Retouche » sur le tome que ce run vient d'écrire.\n"
            "Rien n'est modifié : la retouche lit les checkpoints que le run a produits.")
        self.bouton_retoucher.clicked.connect(self.demande_retouche.emit)
        self.bouton_retoucher.setVisible(False)
        self.bouton_fermer = QPushButton("Fermer")
        self.bouton_fermer.setToolTip("Retire le bilan du run. Le journal, lui, le garde.")
        self.bouton_fermer.clicked.connect(self.effacer)
        self.bouton_fermer.setVisible(False)
        self.bouton_arreter = QPushButton("Arrêter proprement")
        self.bouton_arreter.setToolTip(INFOBULLE_ARRET)
        self.bouton_arreter.clicked.connect(self.demande_arret.emit)
        bas.addWidget(self.etiquette_objet, 1)
        bas.addWidget(self.bouton_retoucher)
        bas.addWidget(self.bouton_avertissements)
        bas.addWidget(self.bouton_fermer)
        bas.addWidget(self.bouton_arreter)
        layout.addLayout(bas)

        # -- L33.2, la quatrième ligne : le compte à rebours d'extinction --------------- #
        #
        # ⚠ Elle est **cachée par défaut et n'apparaît que lorsqu'une extinction est
        # programmée**. Le `PLAN-32` L32.5 refuse toute modale à la fin d'un run — « un run de
        # nuit finit à 3 h du matin et l'utilisateur peut être en train de taper une
        # réplique » — mais un compte à rebours d'extinction DOIT se voir et s'annuler sans
        # chercher. Le bandeau est le seul endroit qui tient les deux : déjà visible depuis
        # n'importe quelle destination, et il ne vole pas le focus.
        extinction = QHBoxLayout()
        self.etiquette_extinction = QLabel("")
        self.etiquette_extinction.setWordWrap(True)
        self.etiquette_extinction.setAccessibleName("Compte à rebours d'extinction du PC")
        theme.poser_role(self.etiquette_extinction, "avertissement")
        self.bouton_annuler_extinction = QPushButton("Annuler l'extinction")
        self.bouton_annuler_extinction.setToolTip(
            "Annule l'extinction programmée du PC. Le run, lui, est déjà terminé.")
        self.bouton_annuler_extinction.clicked.connect(
            self.demande_annulation_extinction.emit)
        extinction.addWidget(self.etiquette_extinction, 1)
        extinction.addWidget(self.bouton_annuler_extinction)
        layout.addLayout(extinction)
        self.etiquette_extinction.setVisible(False)
        self.bouton_annuler_extinction.setVisible(False)

        self.setVisible(False)

    # ------------------------------------------------------------------ #

    def demarrer_extinction(self, etat) -> None:
        """Une extinction est programmée : la quatrième ligne apparaît, et le bandeau reste.

        `etat` est un `gui.extinction.Rebours` — ce module décide, celui-ci affiche."""
        self.etiquette_extinction.setText(etat.phrase())
        self.etiquette_extinction.setVisible(True)
        self.bouton_annuler_extinction.setVisible(True)
        self.bouton_annuler_extinction.setEnabled(True)
        self.setVisible(True)

    def peindre_extinction(self, etat) -> None:
        """Un battement du compte à rebours. ⚠ Quand il est fini, le bouton se DÉSARME plutôt
        que de disparaître : la machine part, et un bouton qui s'évanouit à la seconde où l'on
        clique dessus est pire qu'un bouton grisé."""
        self.etiquette_extinction.setText(etat.phrase())
        if etat.fini:
            self.bouton_annuler_extinction.setEnabled(False)

    def effacer_extinction(self) -> None:
        """L'extinction est annulée : la quatrième ligne disparaît, le bilan du run reste."""
        self.etiquette_extinction.setText("")
        self.etiquette_extinction.setVisible(False)
        self.bouton_annuler_extinction.setVisible(False)

    # ------------------------------------------------------------------ #

    def demarrer(self, cible: str = "", arret_possible: bool = True) -> None:
        """Un run commence : le bandeau apparaît, vide de tout bilan précédent.

        `arret_possible=False` retire le bouton d'arrêt. Toutes les tâches globales n'ont pas
        de frontière propre : un import de glossaire ou une copie de sources s'arrête quand
        il a fini. Proposer « Arrêter proprement » là où rien ne l'écoute serait promettre une
        garantie qu'on ne tient pas — et c'est le contraire de ce que ce bouton veut dire."""
        self.etiquette_cible.setText(cible)
        self.etiquette_phase.setText("")
        self.etiquette_compte.setText("")
        self.etiquette_restant.setText("")
        self.etiquette_objet.setText("")
        # Indéterminée tant que rien n'est compté : c'est vrai, et ça évite la barre à zéro
        # qui laisse croire que rien n'a démarré.
        self.barre.setRange(0, 0)
        self.bouton_arreter.setVisible(bool(arret_possible))
        self.bouton_arreter.setEnabled(bool(arret_possible))
        self.bouton_avertissements.setVisible(False)
        self.bouton_retoucher.setVisible(False)
        self.bouton_fermer.setVisible(False)
        self.setVisible(True)

    def peindre(self, etat: dict, cible: str = "") -> None:
        """Repeint depuis l'état de `core/progression.py`. Aucune décision ici."""
        lignes = av.lignes_de_run(etat, cible or self.etiquette_cible.text())
        self.etiquette_cible.setText(lignes.cible)
        self.etiquette_phase.setText(lignes.phase)
        self.etiquette_compte.setText(lignes.compte)
        self.etiquette_restant.setText(lignes.restant)
        self.etiquette_objet.setText(lignes.objet)
        if lignes.determinee:
            self.barre.setRange(0, lignes.maximum)
            self.barre.setValue(lignes.valeur)
        else:
            self.barre.setRange(0, 0)

    def terminer(self, resume: str, avertissements: int = 0, retouche: str = "") -> None:
        """L'état TERMINAL, qui reste à l'écran.

        ⚠ **Aucune boîte modale.** Un run de nuit finit à 3 h du matin et l'utilisateur peut
        être en train de taper une réplique dans la retouche : un dialogue qui surgit avale
        la frappe. Le bilan attend ici, sans voler le focus et sans clignoter."""
        self.etiquette_phase.setText("")
        self.etiquette_compte.setText(resume)
        self.etiquette_restant.setText("")
        self.etiquette_objet.setText("")
        self.barre.setRange(0, av.PAS_DE_BARRE)
        self.barre.setValue(av.PAS_DE_BARRE)
        self.bouton_arreter.setVisible(False)
        self.bouton_avertissements.setText(
            f"Avertissements ({avertissements})" if avertissements else "")
        self.bouton_avertissements.setVisible(bool(avertissements))
        # L35.2 — le libellé vient de `gui/vue_retouche.libelle_retouche`, qui décide (et se
        # teste) sans Qt. Vide = rien à proposer : un run light novel, ou une tâche qui n'a
        # pas de tome.
        self.bouton_retoucher.setText(retouche)
        self.bouton_retoucher.setVisible(bool(retouche))
        self.bouton_fermer.setVisible(True)
        self.setVisible(True)

    def effacer(self) -> None:
        """Plus rien à dire : le bandeau s'efface.

        ⚠ **Sauf si une extinction est en compte à rebours.** « Fermer » retire le bilan du
        run ; il ne doit pas emporter avec lui la seule chose qui dit que la machine va
        s'éteindre — ni le seul bouton qui l'arrête."""
        if self.bouton_annuler_extinction.isVisible():
            self.etiquette_compte.setText("")
            self.etiquette_objet.setText("")
            self.bouton_avertissements.setVisible(False)
            self.bouton_retoucher.setVisible(False)
            self.bouton_fermer.setVisible(False)
            return
        self.setVisible(False)
        self.etiquette_compte.setText("")
        self.etiquette_objet.setText("")
        self.bouton_avertissements.setVisible(False)
        self.bouton_fermer.setVisible(False)
