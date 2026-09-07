# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le système visuel — **le seul endroit du dépôt où une couleur a le droit d'être écrite**.

## Ce que ce module remplace

Vingt-six littéraux de couleur, dix-neuf valeurs distinctes, dans cinq fichiers, sans aucun
point de définition commun. Et un défaut qui se voyait à l'œil nu : les gris `#9aa`, `#7aa` et
le `#d2d2d2` du journal sont des valeurs de thème SOMBRE, appliquées sur des widgets que le
style natif de Windows peint en BLANC. L'application mélangeait deux hypothèses de fond
contradictoires, et le seul endroit qui nommait l'idée d'un thème était `pellicule.couleur`,
qui rendait `None` pour dire « couleur par défaut du thème ». Elle avait raison, et elle était
seule.

## Trois surfaces, pas deux

- **`chrome`** — menus, panneaux, formulaires, listes. Suit le thème choisi.
- **`canevas`** — le fond derrière la planche. **Toujours sombre, dans les deux thèmes.** Un
  fond sombre autour d'une planche évite d'éblouir et fait ressortir le dessin ; c'est la
  convention de tous les outils d'image, et `QColor(40, 40, 44)` l'appliquait déjà. Un outil
  d'image a le droit d'avoir un canevas qui ne suit pas le thème ; il n'a pas le droit d'avoir
  un formulaire illisible.
- **`journal`** — monospace, contrasté, quatre niveaux qui doivent rester distinguables.

## Python, et pas un QSS ni un YAML

Le canevas a besoin des couleurs en `QColor`, la pellicule en chaîne `#rrggbb`, la feuille de
style en texte. Un seul endroit, trois consommateurs — et deux d'entre eux ne veulent pas de
Qt.

⚠ **Aucun import Qt au niveau du module.** `gui/pellicule.py` est Qt-libre et testé sans
PySide6 (règle de couche, `gui/__init__.py`) ; il consomme les rôles de ce fichier. Qt n'est
importé que dans le corps de `appliquer()`, `qcolor()`, `qpalette()` et `police_mono()` —
c'est-à-dire là où il y a réellement une application à peindre. C'est aussi ce qui permet à
`tests/test_gui_theme.py` de vérifier les contrastes dans le job de CI qui n'installe pas
PySide6, et `test_le_module_de_theme_ne_tire_pas_qt` garde la propriété par lecture du source.

## Nommer par rôle, jamais par valeur

`avertissement`, pas `orange`. C'est ce qui permet aux deux thèmes de partager le même code
d'appel — et c'est exactement ce que les vingt-six couleurs d'avant ne faisaient pas.

## Le contraste se calcule, il ne s'estime pas

`contraste()` implémente la luminance relative de WCAG 2.1. `tests/test_gui_theme.py` publie
et vérifie le tableau des paires ; `docs/mesures/systeme-visuel-2026-08-27.md` le reproduit. Cible :
**4,5:1 pour le texte courant, 3:1 pour les gros textes et les bordures d'état**. Une couleur
qui n'y arrive pas est changée ; la cible, non.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

# --------------------------------------------------------------------------- #
#  Les modes
# --------------------------------------------------------------------------- #

CLAIR = "clair"
SOMBRE = "sombre"
AUTO = "auto"

#: Les valeurs acceptées par `gui/reglages.py` et par le menu Affichage.
MODES: tuple[str, ...] = (AUTO, CLAIR, SOMBRE)

#: Repli quand le système ne sait pas dire ce qu'il préfère. Clair, parce que c'est ce que le
#: style natif de Windows donnait jusqu'ici : le défaut du lot est iso-perception.
MODE_PAR_DEFAUT = CLAIR

#: Variable d'environnement de secours — le temps de la mise au point, pas un réglage livré.
#: `ANGELITH_STYLE_NATIF=1` rend le style de la plateforme (`windowsvista`), qui ignore une
#: grande partie du QSS. Cf. `appliquer()`.
VARIABLE_STYLE_NATIF = "ANGELITH_STYLE_NATIF"


# --------------------------------------------------------------------------- #
#  L'échelle d'espacement
# --------------------------------------------------------------------------- #

class Espacement:
    """L'échelle, et **rien entre**.

    Six pas suffisent à toute l'interface. Une marge de 7 px n'existe pas : elle serait le
    signe qu'on a réglé un cas particulier à l'œil au lieu de choisir un rang."""

    XS = 4
    S = 8
    M = 12
    L = 16
    XL = 24
    XXL = 32

    ECHELLE: tuple[int, ...] = (4, 8, 12, 16, 24, 32)


# --------------------------------------------------------------------------- #
#  L'échelle typographique
# --------------------------------------------------------------------------- #

class Typo:
    """Quatre corps, **en points, dérivés de la police de l'application**.

    ⚠ Pas de `px`. Une taille en pixels ne suit ni le réglage système ni le facteur DPI, et
    c'est la cause la plus fréquente d'une interface illisible sur un écran à forte densité.
    Les trois valeurs d'avant (`11px`, `12px`, `20px`) en étaient.

    Le 1× vient de `QApplication.font()`, donc du réglage système, donc de l'utilisateur."""

    PETIT = 0.85
    NORMAL = 1.0
    GRAND = 1.15
    TITRE = 1.30

    #: Pile monospace multiplateforme. `Consolas` d'abord — c'est ce que la machine de
    #: développement a — puis des noms qui EXISTENT ailleurs, et `monospace` en dernier.
    #: L'ancienne déclaration s'arrêtait à `Consolas, monospace` : le repli sauvait la mise,
    #: mais c'est le genre de valeur qui rend un logiciel « développé sur Windows » visible au
    #: premier coup d'œil ailleurs.
    MONOSPACE: tuple[str, ...] = ("Consolas", "Cascadia Mono", "SF Mono", "Menlo",
                                  "DejaVu Sans Mono", "Liberation Mono", "monospace")

    @staticmethod
    def echelle(base_pt: float) -> dict[str, float]:
        """`{nom: taille en points}` pour une police de base donnée.

        ⚠ Aucun `max()`, aucun plancher : un plancher écraserait les deux premiers rangs l'un
        sur l'autre pour une base de 8 pt, et l'échelle cesserait d'être une échelle. C'est
        exactement ce que `test_l_echelle_reste_croissante` refuse."""
        base = float(base_pt)
        return {"petit": round(base * Typo.PETIT, 2),
                "normal": round(base * Typo.NORMAL, 2),
                "grand": round(base * Typo.GRAND, 2),
                "titre": round(base * Typo.TITRE, 2)}

    @staticmethod
    def famille_mono() -> str:
        """La pile, prête pour une déclaration CSS/QSS."""
        return ", ".join(Typo.MONOSPACE)


# --------------------------------------------------------------------------- #
#  Les rôles
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Palette:
    """Les couleurs **par rôle**. Toutes en `#rrggbb`, sans alpha — cf. `ALPHAS`."""

    nom: str

    # -- chrome : ce qui suit le thème ------------------------------------- #
    fond: str
    fond_eleve: str
    bordure: str
    texte: str
    texte_faible: str
    accent: str
    accent_texte: str
    selection: str
    selection_texte: str
    focus: str
    desactive_texte: str
    desactive_fond: str
    lecture_seule_fond: str

    # -- états : messages, journal, pastilles ------------------------------ #
    avertissement: str
    erreur: str
    succes: str
    information: str
    modifie: str

    # -- pellicule --------------------------------------------------------- #
    pastille_perimee: str
    pastille_main: str
    pastille_absente: str
    pastille_brouillon: str
    vignette_attente: str

    # -- canevas : IDENTIQUE dans les deux thèmes -------------------------- #
    canevas_fond: str = "#28282c"
    zone: str = "#4696ff"
    zone_choisie: str = "#ffaa28"
    zone_vide: str = "#e65050"
    zone_main: str = "#78d278"
    zone_trace: str = "#ffffff"
    poignee_contour: str = "#1e1e22"
    numero_texte: str = "#141414"
    numero_fond: str = "#ffd25a"

    def role(self, nom: str) -> str:
        """La couleur d'un rôle, par son nom. Lève sur un rôle inconnu — une faute de frappe
        dans un nom de rôle doit se voir au premier lancement, pas se peindre en noir."""
        try:
            return getattr(self, nom)
        except AttributeError:
            raise KeyError(f"rôle de couleur inconnu : {nom!r}") from None

    def sombre_p(self) -> bool:
        """Le chrome est-il sombre ? Décidé sur la LUMINANCE du fond, pas sur le nom : un
        thème ajouté demain n'aura pas à se souvenir de le déclarer."""
        return luminance(self.fond) < 0.5


#: Opacités des remplissages de zone, en 0–255. Elles ne sont pas des couleurs : les poser
#: dans la palette obligerait à écrire huit variantes translucides des cinq états.
ALPHAS = {"zone_remplissage": 20, "zone_remplissage_choisie": 48, "numero_fond": 230}


#: Les rôles du CANEVAS — ceux qui ne changent pas d'un thème à l'autre. Un test le vérifie :
#: c'est la décision de l'étape 0, et elle doit rester vérifiable, pas seulement écrite.
ROLES_CANEVAS: tuple[str, ...] = (
    "canevas_fond", "zone", "zone_choisie", "zone_vide", "zone_main", "zone_trace",
    "poignee_contour", "numero_texte", "numero_fond")


CLAIRE = Palette(
    nom=CLAIR,
    fond="#f3f3f6",
    fond_eleve="#ffffff",
    bordure="#8b8b96",
    texte="#16161a",
    texte_faible="#55555f",
    accent="#0f5ea8",
    accent_texte="#ffffff",
    selection="#0f5ea8",
    selection_texte="#ffffff",
    focus="#0f5ea8",
    desactive_texte="#6b6b75",
    desactive_fond="#e7e7ec",
    lecture_seule_fond="#ececeF".lower(),
    avertissement="#8a4d00",
    erreur="#a71d13",
    succes="#186a30",
    information="#3a3a44",
    modifie="#8a4d00",
    pastille_perimee="#8a4d00",
    pastille_main="#1a5b8c",
    pastille_absente="#63636d",
    pastille_brouillon="#a71d13",
    vignette_attente="#8f8f9a",
)

SOMBRE_PALETTE = Palette(
    nom=SOMBRE,
    fond="#1e1e22",
    fond_eleve="#2a2a30",
    bordure="#757582",
    texte="#eaeaee",
    texte_faible="#a9a9b6",
    accent="#6aa6d8",
    accent_texte="#10141a",
    selection="#2f6fa8",
    selection_texte="#ffffff",
    focus="#7ab6e8",
    desactive_texte="#8a8a96",
    desactive_fond="#26262c",
    lecture_seule_fond="#232329",
    avertissement="#e5a94f",
    erreur="#f4796a",
    succes="#7fca8d",
    information="#d2d2d6",
    modifie="#e5a94f",
    pastille_perimee="#e5a94f",
    pastille_main="#6aa6d8",
    pastille_absente="#9a9aa6",
    pastille_brouillon="#f4796a",
    vignette_attente="#7a7a87",
)

PALETTES: dict[str, Palette] = {CLAIR: CLAIRE, SOMBRE: SOMBRE_PALETTE}


def palette(mode: str) -> Palette:
    """La palette d'un mode. `auto` est résolu par `mode_effectif()`."""
    return PALETTES[mode_effectif(mode)]


def mode_effectif(mode: str | None) -> str:
    """`auto` → ce que le système préfère ; tout le reste est rendu tel quel.

    ⚠ Lit `QStyleHints.colorScheme()` **si Qt est là**. Sans Qt — c'est-à-dire dans le job de
    CI qui teste les contrastes sans PySide6 — le repli est `MODE_PAR_DEFAUT`, et il ne pend
    pas."""
    if mode in (CLAIR, SOMBRE):
        return mode
    return _mode_systeme()


def _mode_systeme() -> str:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        return MODE_PAR_DEFAUT
    app = QGuiApplication.instance()
    if app is None:
        return MODE_PAR_DEFAUT
    try:
        schema = app.styleHints().colorScheme()
    except (AttributeError, RuntimeError):
        return MODE_PAR_DEFAUT
    if schema == Qt.ColorScheme.Dark:
        return SOMBRE
    if schema == Qt.ColorScheme.Light:
        return CLAIR
    return MODE_PAR_DEFAUT


# --------------------------------------------------------------------------- #
#  Le contraste — WCAG 2.1, calculé et non estimé
# --------------------------------------------------------------------------- #

#: Rapport minimal exigé du texte courant. WCAG 2.1 AA.
CIBLE_TEXTE = 4.5
#: Rapport minimal exigé des gros textes (≥ 18 pt, ou 14 pt gras) et des bordures d'état.
CIBLE_GROS = 3.0


def rvb(couleur: str) -> tuple[int, int, int]:
    """`« #rrggbb »` → `(r, v, b)`. Accepte la forme courte `« #rvb »`."""
    brut = couleur.lstrip("#")
    if len(brut) == 3:
        brut = "".join(c * 2 for c in brut)
    if len(brut) != 6:
        raise ValueError(f"couleur illisible : {couleur!r}")
    return tuple(int(brut[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(couleur: str) -> float:
    """Luminance relative WCAG 2.1 — la formule, pas une approximation par la moyenne."""
    canaux = []
    for brut in rvb(couleur):
        c = brut / 255
        canaux.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, v, b = canaux
    return 0.2126 * r + 0.7152 * v + 0.0722 * b


def contraste(avant: str, arriere: str) -> float:
    """Le rapport de contraste entre deux couleurs, de 1,0 à 21,0."""
    a, b = luminance(avant), luminance(arriere)
    clair, sombre = (a, b) if a > b else (b, a)
    return (clair + 0.05) / (sombre + 0.05)


#: Les paires que le lot s'engage à tenir : `(rôle du texte, rôle du fond, cible)`.
#:
#: ⚠ C'est cette table qui est le CRITÈRE, pas la prose. `tests/test_gui_theme.py` la parcourt
#: pour les deux palettes, et `docs/mesures/systeme-visuel-2026-08-27.md` publie le tableau qu'elle
#: produit. Une couleur ajoutée sans sa paire ici n'est pas mesurée, donc pas tenue.
PAIRES_CONTRASTE: tuple[tuple[str, str, float], ...] = (
    # -- chrome ------------------------------------------------------------ #
    ("texte", "fond", CIBLE_TEXTE),
    ("texte", "fond_eleve", CIBLE_TEXTE),
    ("texte_faible", "fond", CIBLE_TEXTE),
    ("texte_faible", "fond_eleve", CIBLE_TEXTE),
    ("texte", "lecture_seule_fond", CIBLE_TEXTE),
    ("accent", "fond", CIBLE_TEXTE),
    ("accent_texte", "accent", CIBLE_TEXTE),
    ("selection_texte", "selection", CIBLE_TEXTE),
    # ⚠ Un widget désactivé doit rester LISIBLE, pas effacé : pendant un run, huit widgets
    # mutants passent par là, et c'est l'état qu'on regarde le plus longtemps.
    ("desactive_texte", "desactive_fond", CIBLE_GROS),
    ("desactive_texte", "fond", CIBLE_GROS),
    ("bordure", "fond", CIBLE_GROS),
    ("bordure", "fond_eleve", CIBLE_GROS),
    ("focus", "fond", CIBLE_GROS),
    ("focus", "fond_eleve", CIBLE_GROS),
    # -- états -------------------------------------------------------------- #
    ("avertissement", "fond", CIBLE_TEXTE),
    ("avertissement", "fond_eleve", CIBLE_TEXTE),
    ("erreur", "fond", CIBLE_TEXTE),
    ("erreur", "fond_eleve", CIBLE_TEXTE),
    ("succes", "fond", CIBLE_TEXTE),
    ("succes", "fond_eleve", CIBLE_TEXTE),
    ("information", "fond", CIBLE_TEXTE),
    ("information", "fond_eleve", CIBLE_TEXTE),
    ("modifie", "fond", CIBLE_TEXTE),
    # -- pellicule : le texte de la légende, sur le fond d'une liste --------- #
    ("pastille_perimee", "fond_eleve", CIBLE_TEXTE),
    ("pastille_main", "fond_eleve", CIBLE_TEXTE),
    ("pastille_absente", "fond_eleve", CIBLE_TEXTE),
    ("pastille_brouillon", "fond_eleve", CIBLE_TEXTE),
    # ⚠ L'aplat d'attente était `#e9e9ec` : **1,1:1 sur le blanc d'une liste**. Une vignette
    # pas encore fabriquée était donc invisible, alors que c'est tout son rôle — dire qu'il
    # reste du travail à cet endroit-là de la pellicule. La cible ne bouge pas, la couleur si.
    ("vignette_attente", "fond_eleve", CIBLE_GROS),
    # -- canevas : les cinq états de zone se lisent sur le FOND du canevas --- #
    ("zone", "canevas_fond", CIBLE_GROS),
    ("zone_choisie", "canevas_fond", CIBLE_GROS),
    ("zone_vide", "canevas_fond", CIBLE_GROS),
    ("zone_main", "canevas_fond", CIBLE_GROS),
    ("zone_trace", "canevas_fond", CIBLE_GROS),
    ("numero_texte", "numero_fond", CIBLE_TEXTE),
    ("poignee_contour", "zone_choisie", CIBLE_GROS),
)


def tableau_contraste(pal: Palette) -> list[tuple[str, str, float, float, bool]]:
    """`[(texte, fond, rapport, cible, tenu)]` — ce que le critère 3 demande de publier."""
    lignes = []
    for avant, arriere, cible in PAIRES_CONTRASTE:
        rapport = round(contraste(pal.role(avant), pal.role(arriere)), 2)
        lignes.append((avant, arriere, rapport, cible, rapport >= cible))
    return lignes


def echecs_contraste(pal: Palette) -> list[tuple[str, str, float, float, bool]]:
    """Les paires qui ne tiennent pas leur cible. Vide = la palette est livrable."""
    return [ligne for ligne in tableau_contraste(pal) if not ligne[4]]


# --------------------------------------------------------------------------- #
#  Le jeu appliqué
# --------------------------------------------------------------------------- #

#: Le style Qt que le lot pose. Neutre, identique sur les trois plateformes, et — c'est
#: l'essentiel — il respecte à la fois `QPalette` et le QSS, ce que `windowsvista` ne fait pas.
STYLE = "Fusion"


@dataclass(frozen=True)
class Jeu:
    """Une palette, une échelle typographique et le style posé — ce qu'une session applique.

    ⚠ `style` est mémorisé ICI parce qu'il n'est pas relisable ailleurs : dès qu'une feuille
    de style est posée, `QApplication.style()` rend un `QStyleSheetStyle` — un proxy dont
    `name()` et `objectName()` sont vides. Sans ce champ, « quel style est appliqué ? » n'a
    pas de réponse, ni pour un test ni pour un diagnostic."""

    palette: Palette
    corps: dict[str, float] = field(default_factory=lambda: Typo.echelle(9.0))
    style: str = STYLE

    @property
    def mode(self) -> str:
        return self.palette.nom


#: Le jeu courant. Posé par `appliquer()` ; lu par le canevas, la pellicule et les dialogues.
#: Un module-level plutôt qu'un passage de paramètre à travers douze constructeurs : le thème
#: est un état d'application, exactement comme `QApplication.font()`.
_JEU = Jeu(palette=CLAIRE)


def jeu() -> Jeu:
    """Le jeu courant. Toujours défini — un import sans `appliquer()` rend le thème clair."""
    return _JEU


def couleur(role: str) -> str:
    """La couleur d'un rôle du jeu courant, en `#rrggbb`. **Le point d'appel courant.**"""
    return _JEU.palette.role(role)


def corps(nom: str = "normal") -> float:
    """Une taille de l'échelle typographique courante, en POINTS."""
    return _JEU.corps[nom]


def qcolor(role: str, alpha: int | None = None):
    """La couleur d'un rôle en `QColor`. Qt importé ici, pas au chargement du module."""
    from PySide6.QtGui import QColor

    valeur = QColor(couleur(role))
    if alpha is not None:
        valeur.setAlpha(int(alpha))
    return valeur


def police_mono(base: object = None):
    """Une `QFont` monospace au corps `petit`, avec la pile de replis de `Typo.MONOSPACE`.

    ⚠ `setFamilies` et pas `setFamily` : c'est le seul appel qui donne à Qt la LISTE des
    replis. `setFamily("Consolas, monospace")` demande une police dont le nom contient une
    virgule, et rend la police par défaut sur toute machine qui n'a pas Consolas."""
    from PySide6.QtGui import QFont

    fonte = QFont(base) if base is not None else QFont()
    fonte.setFamilies(list(Typo.MONOSPACE))
    fonte.setStyleHint(QFont.Monospace)
    fonte.setPointSizeF(corps("petit"))
    return fonte


# --------------------------------------------------------------------------- #
#  La feuille de style
# --------------------------------------------------------------------------- #

def qss(pal: Palette, corps_pt: dict[str, float] | None = None) -> str:
    """La feuille de style de l'application, assemblée depuis les rôles.

    ## Ce qu'elle traite, et pourquoi ce sont ceux-là

    Sans QSS, aucun widget n'a d'état visuel au-delà de ce que le style natif fournit. Or ce
    logiciel grise beaucoup : pendant un run, huit widgets mutants sont désactivés et deux
    champs passent en lecture seule pour rester lisibles. Les cinq états traités ici sont ceux
    que `PLAN-19` L19.5 relève :

    - `:disabled` — doit rester **lisible**, pas effacé (cf. `desactive_texte`) ;
    - lecture seule ≠ désactivé — c'est déjà la logique du code, elle devient visible ;
    - `:checked` — les cinq outils, le verrou de cadrage, « Comparer au rendu du pipeline » ;
    - `:focus` — prérequis de toute navigation au clavier, invisible avant ce lot ;
    - `:hover` — sur les vignettes de la pellicule, cliquables sans le montrer.

    ⚠ Les tailles sont en `pt`, jamais en `px`."""
    c = corps_pt or Typo.echelle(9.0)
    p = pal
    return f"""
/* ------------------------------------------------------------------ chrome */
QWidget {{
    color: {p.texte};
    font-size: {c['normal']}pt;
}}
QMainWindow, QDialog, QTabWidget::pane, QStatusBar {{
    background-color: {p.fond};
}}
QMenuBar, QMenu, QToolTip {{
    background-color: {p.fond_eleve};
    color: {p.texte};
}}
QMenu, QToolTip {{
    border: 1px solid {p.bordure};
}}
QMenu::item:selected, QMenuBar::item:selected {{
    background-color: {p.selection};
    color: {p.selection_texte};
}}
QMenu::separator {{
    height: 1px;
    background: {p.bordure};
    margin: {Espacement.XS}px {Espacement.S}px;
}}
QGroupBox {{
    border: 1px solid {p.bordure};
    border-radius: 3px;
    margin-top: {Espacement.M}px;
    padding-top: {Espacement.S}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {Espacement.S}px;
    padding: 0 {Espacement.XS}px;
    color: {p.texte_faible};
}}
QSplitter::handle {{
    background-color: {p.bordure};
}}

/* ------------------------------------------------------- champs et listes */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox,
QListWidget, QListView, QTreeView, QTableView {{
    background-color: {p.fond_eleve};
    border: 1px solid {p.bordure};
    border-radius: 3px;
    selection-background-color: {p.selection};
    selection-color: {p.selection_texte};
}}
QLineEdit, QSpinBox, QComboBox {{
    padding: {Espacement.XS}px {Espacement.S}px;
}}
/* ⚠ LECTURE SEULE ≠ DÉSACTIVÉ. Pendant un run, les deux champs de texte passent en lecture
   seule PLUTÔT qu'en désactivé, pour rester lisibles et sélectionnables. Sans cette règle,
   rien à l'écran ne distinguait les deux, et la distinction ne vivait que dans le code. */
QPlainTextEdit[readOnly="true"], QLineEdit[readOnly="true"], QTextEdit[readOnly="true"] {{
    background-color: {p.lecture_seule_fond};
    border-style: dashed;
}}
QListWidget::item:hover, QListView::item:hover {{
    background-color: {p.desactive_fond};
}}
QListWidget::item:selected, QListView::item:selected {{
    background-color: {p.selection};
    color: {p.selection_texte};
}}

/* ------------------------------------------------------------- les états */
QPushButton, QToolButton {{
    background-color: {p.fond_eleve};
    border: 1px solid {p.bordure};
    border-radius: 3px;
    padding: {Espacement.XS}px {Espacement.M}px;
}}
QPushButton:hover, QToolButton:hover {{
    border-color: {p.accent};
}}
QPushButton:pressed, QToolButton:pressed {{
    background-color: {p.desactive_fond};
}}
/* `:checked` — les cinq outils, le verrou de cadrage, « Comparer au rendu du pipeline ».
   Un aplat d'accent, pas seulement un enfoncement : l'état enfoncé du style natif était le
   SEUL indice que la comparaison coupait toute interaction du canevas. */
QPushButton:checked, QToolButton:checked {{
    background-color: {p.accent};
    color: {p.accent_texte};
    border-color: {p.accent};
}}
/* ⚠ Un widget désactivé reste LISIBLE. `setEnabled(False)` sur un texte effacé, pendant les
   minutes que dure un run, revient à cacher l'information au moment où on la relit. */
QWidget:disabled {{
    color: {p.desactive_texte};
}}
QPushButton:disabled, QToolButton:disabled, QComboBox:disabled,
QLineEdit:disabled, QSpinBox:disabled, QPlainTextEdit:disabled {{
    background-color: {p.desactive_fond};
    color: {p.desactive_texte};
    border-color: {p.bordure};
}}
/* L'anneau de focus. Sans lui, `setTabOrder` et `setAccessibleName` ne servent à rien : on
   ne sait pas où l'on est. */
QPushButton:focus, QToolButton:focus, QComboBox:focus, QCheckBox:focus,
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QTabBar::tab:focus,
QListWidget:focus, QListView:focus {{
    border: 2px solid {p.focus};
    outline: none;
}}

/* --------------------------------------------------------------- onglets */
QTabBar::tab {{
    background-color: {p.fond};
    border: 1px solid {p.bordure};
    border-bottom: none;
    padding: {Espacement.S}px {Espacement.L}px;
}}
QTabBar::tab:selected {{
    background-color: {p.fond_eleve};
    color: {p.accent};
}}

/* ------------------------------------------------------------ progression */
QProgressBar {{
    background-color: {p.fond_eleve};
    border: 1px solid {p.bordure};
    border-radius: 3px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {p.accent};
}}

/* ------------------------------------------------------- rôles applicatifs */
/* Posés par `setProperty("role", …)` — cf. `poser_role()`. Une propriété plutôt qu'un
   `setStyleSheet` inline : c'est ce qui fait que le widget suit la bascule de thème sans
   qu'aucun code n'aille le repeindre un par un.

   ⚠ **Les sélecteurs nomment leur CLASSE — jamais `*[role=…]`.** Un sélecteur universel avec
   attribut force Qt à évaluer la propriété dynamique sur CHAQUE widget de l'application, à
   chaque résolution de style.

   ⚠ **Et la mesure a corrigé l'intuition** : passer de `*` aux classes a fait tomber
   `tests/test_gui_fenetre.py` de 313 s à 266 s — réel, mais loin d'expliquer le reste. Le
   gros du coût venait d'ailleurs (une fuite de fenêtres dans les tests, cf.
   `docs/mesures/systeme-visuel-2026-08-27.md` §6.4). Le changement est gardé pour ce qu'il vaut, pas
   pour ce qu'on avait cru qu'il valait, et
   `test_la_feuille_ne_contient_aucun_selecteur_universel` empêche le retour en arrière.

   Les deux seules classes qui portent un rôle sont `QLabel` et `QPlainTextEdit` ;
   `ROLES_WIDGET`, `CLASSES_A_ROLE` et ce bloc doivent rester d'accord, ce que
   `test_chaque_role_est_nomme_par_une_classe_que_la_feuille_connait` vérifie. */
QLabel[role="faible"] {{
    color: {p.texte_faible};
    font-size: {c['petit']}pt;
}}
QLabel[role="titre"] {{
    color: {p.texte};
    font-size: {c['titre']}pt;
}}
QLabel[role="avertissement"] {{ color: {p.avertissement}; }}
QLabel[role="erreur"]        {{ color: {p.erreur}; }}
QLabel[role="succes"]        {{ color: {p.succes}; }}
QLabel[role="modifie"]       {{ color: {p.modifie}; }}
QLabel[role="accent"]        {{ color: {p.accent}; }}
QPlainTextEdit[role="journal"] {{
    font-family: {Typo.famille_mono()};
    font-size: {c['petit']}pt;
    background-color: {p.fond_eleve};
}}
QLabel[role="mono"], QPlainTextEdit[role="mono"] {{
    font-family: {Typo.famille_mono()};
    font-size: {c['petit']}pt;
}}
""".strip() + "\n"


#: Les valeurs acceptées par `poser_role()`. Une liste fermée, parce qu'une faute de frappe
#: dans un nom de rôle ne produit **aucune erreur Qt** : la règle QSS ne s'applique
#: simplement jamais, et le défaut est invisible jusqu'à ce qu'on regarde.
ROLES_WIDGET: frozenset[str] = frozenset(
    {"faible", "titre", "avertissement", "erreur", "succes", "modifie", "accent",
     "journal", "mono"})

#: Les classes de widget que `qss()` nomme. **Poser un rôle sur autre chose ne peindrait
#: rien** — et sans erreur, puisqu'une règle QSS qui ne s'applique pas est silencieuse.
#: `poser_role` refuse donc l'inconnu, dans les deux sens : le rôle ET la classe.
#:
#: ⚠ Élargir cette liste demande d'élargir les sélecteurs de `qss()`. Ce qu'il ne faut PAS
#: faire est revenir à `*[role=…]` : cf. l'avertissement du bloc « rôles applicatifs ».
CLASSES_A_ROLE: tuple[str, ...] = ("QLabel", "QPlainTextEdit")


def poser_role(widget, role: str) -> None:
    """Marque un widget d'un rôle visuel. **Remplace les douze `setStyleSheet` inline.**

    ⚠ `unpolish`/`polish` : Qt ne réévalue pas une feuille de style quand une propriété
    dynamique change. Sans ces deux appels, poser le rôle après la construction du widget
    n'aurait aucun effet — c'est le piège classique des propriétés dynamiques en QSS."""
    if role not in ROLES_WIDGET:
        raise KeyError(f"rôle de widget inconnu : {role!r}")
    classes = {c.__name__ for c in type(widget).__mro__}
    if not classes & set(CLASSES_A_ROLE):
        raise TypeError(
            f"{type(widget).__name__} ne porte pas de rôle : la feuille ne nomme que "
            f"{', '.join(CLASSES_A_ROLE)}. La règle ne s'appliquerait pas, et en silence.")
    widget.setProperty("role", role)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


# --------------------------------------------------------------------------- #
#  L'application
# --------------------------------------------------------------------------- #

def appliquer(app, mode: str = AUTO) -> Jeu:
    """Pose le style, la palette et la feuille sur `QApplication`. Rend le jeu appliqué.

    ## Pourquoi `Fusion`

    `QApplication` n'appelait jamais `setStyle` : le style était donc `windowsvista`, qui
    **ignore une grande partie du QSS** et ne respecte pas une `QPalette`. C'est la raison
    technique pour laquelle les douze `setStyleSheet` d'avant étaient tous inline sur un
    unique widget — c'était le seul endroit où ils prenaient.

    `Fusion` est le style Qt neutre, identique sur les trois plateformes, et il respecte à la
    fois la palette et la feuille. C'est le prérequis de tout le reste.

    ⚠ `ANGELITH_STYLE_NATIF=1` rend le style de la plateforme, **le temps de la mise au
    point**. Ce n'est pas un réglage de l'interface et il n'apparaît dans aucun menu : un
    repli qu'on peut choisir est un second chemin à tenir.

    ## ⚠ Idempotente, et c'est la fonction qui en décide

    Reposer une feuille identique n'est pas gratuit : `QApplication.setStyleSheet` **restyle
    tous les widgets vivants de l'application**. Mesuré sur `tests/test_gui_fenetre.py`, où
    quarante fenêtres coexistent : cinq secondes pour deux bascules qui ne changent rien.

    La comparaison se fait donc ICI, sur la feuille RÉELLEMENT produite — et pas chez
    l'appelant, sur le nom du mode. Un appelant qui comparerait les modes sauterait l'appel
    alors que **rien n'a encore été posé** : c'est le défaut qui a fait sortir les captures du
    thème clair sans une seule règle de style, journal en Segoe UI compris. Un `mode` égal ne
    veut pas dire « déjà appliqué » ; une feuille égale, si."""
    global _JEU

    from PySide6.QtGui import QPalette

    effectif = mode_effectif(mode)
    pal = PALETTES[effectif]
    natif = bool(os.environ.get(VARIABLE_STYLE_NATIF))
    base = app.font().pointSizeF()
    if base <= 0:                       # une police déclarée en pixels — rare, mais possible
        base = 9.0
    echelle = Typo.echelle(base)
    feuille = qss(pal, echelle)
    if app.styleSheet() != feuille:
        if not natif:
            app.setStyle(STYLE)
        app.setPalette(qpalette(pal, QPalette))
        app.setStyleSheet(feuille)
    _JEU = Jeu(palette=pal, corps=echelle,
               style="" if natif else STYLE)
    return _JEU


def qpalette(pal: Palette, classe=None):
    """La `QPalette` correspondante. **Les deux doivent être posées** : la feuille de style
    ne couvre pas tout (les rendus d'items de vue, par exemple, interrogent la palette)."""
    if classe is None:
        from PySide6.QtGui import QPalette as classe
    from PySide6.QtGui import QColor

    q = classe()
    groupes = (classe.ColorGroup.Active, classe.ColorGroup.Inactive)
    couleurs = {
        classe.ColorRole.Window: pal.fond,
        classe.ColorRole.WindowText: pal.texte,
        classe.ColorRole.Base: pal.fond_eleve,
        classe.ColorRole.AlternateBase: pal.fond,
        classe.ColorRole.Text: pal.texte,
        classe.ColorRole.Button: pal.fond_eleve,
        classe.ColorRole.ButtonText: pal.texte,
        classe.ColorRole.Highlight: pal.selection,
        classe.ColorRole.HighlightedText: pal.selection_texte,
        classe.ColorRole.ToolTipBase: pal.fond_eleve,
        classe.ColorRole.ToolTipText: pal.texte,
        classe.ColorRole.PlaceholderText: pal.texte_faible,
        classe.ColorRole.Link: pal.accent,
        # ⚠ Les cinq rôles de RELIEF, que le premier jet avait oubliés. `Fusion` dessine
        # lui-même les cadres qu'aucune règle QSS ne couvre — l'indicateur d'une case à
        # cocher, la flèche d'une liste déroulante, le sillon d'une barre de défilement — et
        # il les tire de `Mid`, `Dark`, `Light`, `Midlight` et `Shadow`. Sans eux, une case
        # non cochée n'avait presque plus de bordure dans le thème sombre : visible sur la
        # capture de l'onglet « Runs », et sur rien d'autre.
        classe.ColorRole.Mid: pal.bordure,
        classe.ColorRole.Dark: pal.bordure,
        classe.ColorRole.Midlight: pal.fond,
        classe.ColorRole.Light: pal.fond_eleve,
        classe.ColorRole.Shadow: pal.bordure,
    }
    for role, valeur in couleurs.items():
        for groupe in groupes:
            q.setColor(groupe, role, QColor(valeur))
    for role in (classe.ColorRole.WindowText, classe.ColorRole.Text,
                 classe.ColorRole.ButtonText):
        q.setColor(classe.ColorGroup.Disabled, role, QColor(pal.desactive_texte))
    q.setColor(classe.ColorGroup.Disabled, classe.ColorRole.Button,
               QColor(pal.desactive_fond))
    q.setColor(classe.ColorGroup.Disabled, classe.ColorRole.Base,
               QColor(pal.desactive_fond))
    return q


def variante(pal: Palette, **remplacements) -> Palette:
    """Une palette dérivée — pour un test, jamais pour la version livrée."""
    return replace(pal, **remplacements)
