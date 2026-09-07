# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Complète une police de lettrage pour qu'elle couvre le français, à partir de ses PROPRES
tracés autant que possible.

## Le défaut que cet outil corrige

`manga/typeset.py:font_pour_texte` choisit la police **par bulle** : si un seul caractère
manque à la police demandée, TOUTE la réplique est redessinée dans la première police de
repli qui la couvre. Et ce basculement n'est journalisé nulle part — `typeset_page`
n'alimente le rapport que si des caractères ont été *substitués* ou *supprimés*.

Mesuré sur manga A / Vol.1, après passage de ComicNeue-Bold à Wildjess :

    Wildjess_normal.ttf   755 bulles
    ComicNeue-Bold.ttf     60 bulles      ← basculées, en silence
    l_10646.ttf             3 bulles      ← Lucida Sans Unicode, en silence

soit **63 bulles sur 818, réparties sur 45 planches sur 150**, sorties dans une autre police
que celle de `config.yaml`. Caractères coupables, par fréquence :

    «  ×17    œ  ×16    »  ×14    Ç  ×11    —  ×8    À  ×5    ♪  ×2

Le seul indice était une ligne du RAPPORT.md qui ressemblait à une note d'installation :
« PSD — police(s) à installer : ComicNeue-Bold, LucidaSansUnicode, WildjessNormal ».

La bonne réponse n'est pas de rendre le repli plus malin : c'est que la police demandée
sache dessiner le français.

## Pourquoi reconstruire plutôt que greffer

Greffer les glyphes manquants depuis une autre police est mécanique (mêmes contours
TrueType, même `unitsPerEm`), mais un « Ç » Comic Neue au milieu d'un mot Wildjess se voit —
et ça fait cohabiter deux licences dans un même fichier.

Or une police à laquelle il manque `À` possède presque toujours `A` **et** `È` : l'accent
grave est là, il est juste posé sur une autre lettre. Cet outil le détache et le repose.
Trois techniques, dans cet ordre de préférence :

1. **greffe interne** — l'accent est extrait d'un glyphe existant de la MÊME police et
   reposé sur la capitale. Style identique par construction ;
2. **synthèse** — le glyphe est fabriqué en transformant un glyphe existant (le tiret
   cadratin est un trait d'union étiré, la ligature `œ` est un `o` et un `e` accolés) ;
3. **greffe externe** — dernier recours, pour ce que la police ne peut pas produire
   (`♪ ♥ ~ | ``, et les guillemets). Le résumé de sortie le dit, glyphe par glyphe.

⚠ Les guillemets français sont le contre-exemple, et il a été MESURÉ avant d'être tranché.
La synthèse par chevrons `<` `>` existe (`guillemet`, `--guillemets synthese`) et ses
proportions sont correctes, mais rendue à 44 px côte à côte avec la greffe, elle lit
`<< … >>` et non `« … »`. Un chevron d'opérateur est un trait plié à angle vif ; un
guillemet est deux virgules couchées. Aucune mise à l'échelle ne transforme l'un en l'autre,
et la greffe est donc le défaut.

## ⚠ Droits

Cet outil produit un **travail dérivé** de la police d'entrée. La plupart des licences de
fonderie l'interdisent. Vérifie la tienne avant de t'en servir, et ne redistribue pas le
fichier produit — `NOTICE` documente le cas de `Wildjess`, dont le `nameID 0` porte
« ©1995 Comicraft. All rights reserved. » et qui est pour cette raison exclue du dépôt.

Le `nameID 0` d'origine est CONSERVÉ dans le fichier produit, avec une mention de dérivation
ajoutée à la suite. On n'efface pas un copyright.

## Usage

    python tools/completer_police.py templates/fonts/Wildjess_normal.ttf
    python tools/completer_police.py entree.ttf -o sortie.ttf --nom "Wildjess Complet"
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.cli import configurer_stdout       # noqa: E402  (après l'ajout du chemin du dépôt)
from manga.typeset import polices_symboles   # noqa: E402

_RACINE = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Faite:
    """Un glyphe ajouté : le caractère, par quelle technique, et à partir de quoi."""
    caractere: str
    technique: str
    detail: str

#: Première police de la greffe EXTERNE : livrée avec le dépôt, SIL OFL 1.1
#: (`templates/fonts/OFL.txt`), donc le seul fichier dont le droit de réutilisation soit
#: établi ici. Chemin ABSOLU : cet outil se lance depuis n'importe où.
BOUCHE_TROU = _RACINE / "templates" / "fonts" / "ComicNeue-Bold.ttf"


def polices_de_secours(premiere: Path | None = None) -> list[Path]:
    """Les polices où piocher un glyphe que l'entrée ne peut pas produire, dans l'ordre.

    ⚠ Comic Neue est une police LATINE : elle n'a ni `♪` ni `♥`, que le traducteur produit
    pourtant (« Moi, je préfère les filles ♪ »). `manga.typeset.polices_symboles` résout
    déjà exactement ce problème pour la chaîne de repli du lettrage — Lucida Sans Unicode
    sous Windows, DejaVu sous Linux. On réutilise sa liste plutôt que d'en tenir une
    seconde, qui divergerait au premier système ajouté."""
    candidats = [premiere or BOUCHE_TROU, *(Path(c) for c in polices_symboles())]
    return [c for c in candidats if c.is_file()]

#: Écart vertical entre le haut d'une capitale et le bas de son accent, en unités de police.
#: ⚠ Ce n'est PAS une constante choisie : elle est MESURÉE sur la police d'entrée, en
#: comparant un couple capitale accentuée / capitale nue qu'elle possède déjà (`È` et `E` :
#: accent ymin 807, E ymax 796 → 11). La valeur ci-dessous n'est qu'un repli pour une police
#: qui n'aurait aucun couple mesurable, et elle vaut alors 1,5 % de l'em.
ECART_ACCENT_DEFAUT = 15

#: Les accents à détacher, et où les prendre. Pour chaque accent : les couples
#: (glyphe accentué, glyphe nu) essayés dans l'ordre. Un couple de CAPITALES est préféré —
#: l'accent y est déjà dimensionné et positionné pour une capitale ; à défaut on prend le
#: couple minuscule et on relève l'accent (cf. `_ecart_accent`).
SOURCES_ACCENT: dict[str, tuple[tuple[str, str], ...]] = {
    "grave":       (("È", "E"), ("À", "A"), ("Ù", "U"), ("è", "e"), ("à", "a"), ("ù", "u")),
    "aigu":        (("É", "E"), ("Ú", "U"), ("é", "e"), ("ú", "u"), ("á", "a")),
    "circonflexe": (("Ê", "E"), ("Â", "A"), ("Ô", "O"), ("ê", "e"), ("â", "a"), ("ô", "o")),
    "trema":       (("Ë", "E"), ("Ï", "I"), ("Ö", "O"), ("ë", "e"), ("ï", "i"), ("ö", "o")),
    "cedille":     (("Ç", "C"), ("ç", "c")),
}

#: De quel côté de la lettre l'accent dépasse. Tout dépasse par le haut, sauf la cédille.
SENS_ACCENT: dict[str, str] = {"cedille": "bas"}

#: Ce qu'on cherche à produire, par greffe interne : caractère → (base, accent).
#: Le jeu couvre TOUT le français accentué, pas seulement ce qu'un tome a montré : une lettre
#: absente ne se voit qu'une fois la planche sortie, et refaire un tome coûte des heures de
#: GPU. Une entrée que la police possède déjà est simplement sautée.
LETTRES_ACCENTUEES: dict[str, tuple[str, str]] = {
    "À": ("A", "grave"),   "Â": ("A", "circonflexe"), "Ä": ("A", "trema"),
    "Ç": ("C", "cedille"),
    "È": ("E", "grave"),   "É": ("E", "aigu"),        "Ê": ("E", "circonflexe"),
    "Ë": ("E", "trema"),
    "Î": ("I", "circonflexe"), "Ï": ("I", "trema"),
    "Ô": ("O", "circonflexe"), "Ö": ("O", "trema"),
    "Ù": ("U", "grave"),   "Ú": ("U", "aigu"),        "Û": ("U", "circonflexe"),
    "Ü": ("U", "trema"),
    # Minuscules : Wildjess a à â ç è é ê ë î ï ô ö ù ú û ü, mais ni ä ni ÿ.
    "à": ("a", "grave"),   "â": ("a", "circonflexe"), "ä": ("a", "trema"),
    "ç": ("c", "cedille"),
    "è": ("e", "grave"),   "é": ("e", "aigu"),        "ê": ("e", "circonflexe"),
    "ë": ("e", "trema"),
    "î": ("i", "circonflexe"), "ï": ("i", "trema"),
    "ô": ("o", "circonflexe"), "ö": ("o", "trema"),
    "ù": ("u", "grave"),   "û": ("u", "circonflexe"), "ü": ("u", "trema"),
    "ÿ": ("y", "trema"),
}

#: Ligatures à synthétiser : caractère → les deux glyphes à accoler.
LIGATURES: dict[str, tuple[str, str]] = {"œ": ("o", "e"), "Œ": ("O", "E"),
                                         "æ": ("a", "e"), "Æ": ("A", "E")}

#: Recouvrement d'une ligature, en fraction de la chasse de la première lettre. Repli
#: seulement : `recouvrement_ligature` le MESURE sur une police qui a un vrai `œ`. La valeur
#: est celle de ComicNeue-Bold (0,346), qui sert donc aussi de défaut.
RECOUVREMENT_LIGATURE = 0.346

#: Tirets à synthétiser depuis le trait d'union : caractère → (facteur d'étirement, chasse).
#: Un tiret cadratin fait un cadratin de large (1000) ; un demi-cadratin, la moitié. Le
#: facteur est appliqué au TRACÉ, la chasse est imposée : étirer le trait sans corriger la
#: chasse collerait le tiret au mot suivant.
#: ― (barre horizontale) est du même acabit : `manga.typeset._SUBSTITUTIONS` le mappe vers
#: —, mais la substitution intervient APRÈS la chaîne de repli, donc elle ne joue jamais tant
#: qu'une police de la chaîne le couvre. Mesuré : 1 bulle du Vol.1 basculait sur Lucida pour
#: ce seul signe. Le dessiner ici supprime le repli au lieu de le déplacer.
TIRETS: dict[str, tuple[float, int]] = {"—": (2.10, 1000), "―": (2.10, 1000),
                                        "–": (1.40, 600)}

#: Guillemets français, fabriqués à partir des chevrons `<` et `>` — cf. `forme_guillemet`,
#: qui va lire leurs proportions sur une police qui en possède de vrais plutôt que de les
#: inventer. Le résultat demande tout de même une validation À L'ŒIL sur une planche.
#: Écart entre les deux chevrons d'un guillemet, en fraction de sa largeur totale. Mesuré
#: sur le `«` de ComicNeue-Bold : 490 unités d'encre pour deux chevrons de ~208, soit 74 de
#: blanc entre eux — 15 %.
ECART_GUILLEMET = 0.15

#: Ce que la police ne peut pas produire seule : aucun glyphe existant ne s'en approche.
#: `♪ ♥` sortent du traducteur (« Moi, je préfère les filles ♪ ») ; `~ |` sont de l'ASCII que
#: bien des polices de lettrage omettent, et dont l'absence ferait basculer toute une bulle.
#: Greffés depuis `BOUCHE_TROU`, donc au style de CETTE police-là — le résumé le dit.
#: ⚠ L'accent grave ASCII ` est le débouché de ｀ (grave pleine chasse) par la table des
#: formes pleine chasse de `manga.typeset` : sans lui, la substitution produit un caractère
#: que la police ne sait pas plus dessiner que l'original. Mesuré : 1 bulle du Vol.1.
GREFFE_EXTERNE = ("♪", "♥", "~", "|", "`")

#: Contrôle final : le fichier produit doit savoir dessiner tout ceci. Chaque signe y est
#: parce qu'il est SORTI du traducteur sur un vrai tome, ou parce qu'il appartient au jeu
#: minimal d'une édition française.
ALPHABET_FRANCAIS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "àâäçéèêëîïôöùûüÿœæ"
    "ÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŒÆ"
    ".,;:!?…«»“”‘’'\"()[]-–—/\\&%$#@*+=<>~|"
)


# --------------------------------------------------------------------------------------
# Découpe et recomposition de contours
#
# fontTools ne donne pas d'accès « par contour » à un glyphe. On passe donc par un
# `RecordingPen` : chaque contour y commence par un `moveTo` et se termine par un
# `closePath`, ce qui suffit à les séparer, à les mesurer, puis à ne rejouer que ceux qu'on
# veut. Le détour est volontaire : il marche identiquement pour des courbes quadratiques
# (TrueType) et cubiques, là où lire `glyph.coordinates` à la main obligerait à réimplémenter
# la gestion des points de contrôle implicites.
# --------------------------------------------------------------------------------------

def _contours(jeu_de_glyphes, nom: str) -> list[list[tuple]]:
    """Les contours de `nom`, chacun sous forme de liste d'instructions de stylo."""
    # ⚠ `DecomposingRecordingPen` et non `RecordingPen` : un glyphe peut être COMPOSITE,
    # c'est-à-dire une simple référence à d'autres glyphes. Le `«` de ComicNeue-Bold en est
    # un — deux `guilsinglleft`. Recopié tel quel dans une police qui n'a pas ce composant,
    # il donne un glyphe VIDE : la chasse est là, l'encre a disparu, et rien ne le signale.
    stylo = DecomposingRecordingPen(jeu_de_glyphes)
    jeu_de_glyphes[nom].draw(stylo)
    contours, courant = [], []
    for operation in stylo.value:
        courant.append(operation)
        if operation[0] in ("closePath", "endPath"):
            contours.append(courant)
            courant = []
    if courant:
        contours.append(courant)
    return contours


def _points(contour: list[tuple]) -> list[tuple[float, float]]:
    """Tous les points cités par un contour, points de contrôle compris."""
    points: list[tuple[float, float]] = []
    for _operation, arguments in contour:
        for argument in arguments:
            # `qCurveTo` peut finir par `None` (contour entièrement hors-courbe).
            if isinstance(argument, tuple) and len(argument) == 2:
                points.append(argument)
            elif isinstance(argument, (list, tuple)):
                points.extend(p for p in argument if isinstance(p, tuple) and len(p) == 2)
    return points


def _boite(contours: list[list[tuple]]) -> tuple[float, float, float, float] | None:
    """`(xMin, yMin, xMax, yMax)` de l'ensemble, ou `None` s'il est vide."""
    points = [p for contour in contours for p in _points(contour)]
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _rejouer(contours: list[list[tuple]], stylo) -> None:
    """Rejoue `contours` dans `stylo`."""
    for contour in contours:
        for operation, arguments in contour:
            getattr(stylo, operation)(*arguments)


def _glyphe(jeu_de_glyphes, contours: list[list[tuple]], transformation=None):
    """Fabrique un glyphe TrueType à partir de contours, éventuellement transformés."""
    stylo = TTGlyphPen(jeu_de_glyphes)
    _rejouer(contours, TransformPen(stylo, transformation) if transformation else stylo)
    return stylo.glyph()


def _decale(contours: list[list[tuple]], dx: float, dy: float) -> list[list[tuple]]:
    """Les mêmes contours, translatés. On translate les POINTS plutôt que d'empiler des
    `TransformPen` : deux morceaux d'origines différentes doivent pouvoir être décalés
    séparément avant d'être réunis dans un même stylo."""
    def bouge(argument):
        if isinstance(argument, tuple) and len(argument) == 2 \
                and all(isinstance(v, (int, float)) for v in argument):
            return (argument[0] + dx, argument[1] + dy)
        if isinstance(argument, (list, tuple)):
            return type(argument)(bouge(a) for a in argument)
        return argument
    return [[(operation, tuple(bouge(a) for a in arguments))
             for operation, arguments in contour] for contour in contours]


# --------------------------------------------------------------------------------------
# Lecture de la police d'entrée
# --------------------------------------------------------------------------------------

class Police:
    """Une police ouverte, plus ce qu'il faut pour y piocher des morceaux par caractère."""

    def __init__(self, chemin: Path):
        self.chemin = chemin
        self.tt = TTFont(str(chemin))
        self.cmap = self.tt.getBestCmap()
        self.jeu = self.tt.getGlyphSet()
        self.hmtx = self.tt["hmtx"]
        self.upem = self.tt["head"].unitsPerEm

    def a(self, caractere: str) -> bool:
        return ord(caractere) in self.cmap

    def nom(self, caractere: str) -> str:
        return self.cmap[ord(caractere)]

    def contours(self, caractere: str) -> list[list[tuple]]:
        return _contours(self.jeu, self.nom(caractere))

    def chasse(self, caractere: str) -> int:
        return self.hmtx[self.nom(caractere)][0]

    def boite(self, caractere: str):
        return _boite(self.contours(caractere))


def _ecart_accent(police: Police) -> float:
    """L'écart vertical capitale → accent, MESURÉ sur la police elle-même.

    On cherche un couple de capitales qu'elle possède déjà (`È`/`E`, `É`/`E`, …) et on lit
    la distance entre le haut de la lettre nue et le bas de l'accent. C'est ce qui évite
    d'inventer un chiffre : chaque dessinateur place ses accents à sa hauteur, et une valeur
    empruntée à une autre police se verrait."""
    for accentue, nu in (("È", "E"), ("É", "E"), ("Ê", "E"), ("Å", "A"),
                         ("Ô", "O"), ("Û", "U")):
        if not (police.a(accentue) and police.a(nu)):
            continue
        boite_nue = police.boite(nu)
        morceaux = _separer_accent(police, accentue, nu, "haut")
        if boite_nue and morceaux:
            boite_accent = _boite(morceaux)
            if boite_accent:
                return boite_accent[1] - boite_nue[3]
    return ECART_ACCENT_DEFAUT * police.upem / 1000


def _separer_accent(police: Police, accentue: str, nu: str,
                    sens: str) -> list[list[tuple]] | None:
    """Les contours de `accentue` qui ne sont pas la lettre `nu` — l'accent seul.

    ⚠ On repere l'accent par sa POSITION, pas en diffant les contours des deux glyphes.
    Le diff a ete essayé et il est faux : dans Wildjess, le `E` de `È` n'est pas le meme
    dessin que le `E` isolé (bbox (53,-33)-(580,785) contre (49,-41)-(618,796), soit 38
    unités d'écart en xMax). Toute tolérance assez large pour les rapprocher confondrait
    aussi un accent avec une contre-forme, et toute tolérance assez fine emportait ici le
    corps du `È` sur le `A` — c'est le trait vertical qu'on voyait barrer le `À`.

    La position, elle, ne ment pas : un accent est ce qui dépasse de la lettre.

    · `sens="haut"` — le contour commence au-dessus du sommet de la lettre nue (grave, aigu,
      circonflexe, tréma).
    · `sens="bas"`  — le contour descend sous le pied de la lettre nue (cédille). On teste
      son `yMin` et non son `yMax` : la cédille REMONTE jusqu'au `c` pour s'y raccorder
      (contour -96..113 dans Wildjess), donc seul son point le plus bas la distingue.
    """
    boite_nue = police.boite(nu)
    if boite_nue is None:
        return None
    marge = police.upem * 0.02
    restants = []
    for contour in police.contours(accentue):
        boite = _boite([contour])
        if boite is None:
            continue
        if sens == "haut" and boite[1] >= boite_nue[3] - marge:
            restants.append(contour)
        elif sens == "bas" and boite[1] < boite_nue[1] - marge:
            restants.append(contour)
    return restants or None


def accent(police: Police, forme: str) -> list[list[tuple]] | None:
    """Les contours de l'accent `forme`, détachés du premier couple disponible."""
    for accentue, nu in SOURCES_ACCENT.get(forme, ()):
        if not (police.a(accentue) and police.a(nu)):
            continue
        morceaux = _separer_accent(police, accentue, nu,
                                   SENS_ACCENT.get(forme, "haut"))
        if morceaux:
            return morceaux
    return None


# --------------------------------------------------------------------------------------
# Les trois techniques
# --------------------------------------------------------------------------------------

def lettre_accentuee(police: Police, base: str, forme: str,
                     ecart: float) -> tuple[object, int] | None:
    """Greffe INTERNE : la capitale `base`, plus l'accent `forme` détaché d'un autre glyphe."""
    if not police.a(base):
        return None
    morceaux = accent(police, forme)
    if morceaux is None:
        return None

    boite_base = police.boite(base)
    boite_accent = _boite(morceaux)
    if boite_base is None or boite_accent is None:
        return None

    # Horizontalement : l'accent est centré sur la lettre. Un accent hérité d'un `E` posé
    # tel quel sur un `A` serait décalé de la différence de chasse, ce qui se voit.
    centre_base = (boite_base[0] + boite_base[2]) / 2
    centre_accent = (boite_accent[0] + boite_accent[2]) / 2
    dx = centre_base - centre_accent

    if forme == "cedille":
        # La cédille pend sous la ligne de base : sa hauteur ne dépend pas de la lettre, et
        # la relever la décollerait du `C`.
        dy = 0.0
    else:
        # L'accent est reposé à `ecart` au-dessus de la lettre, quelle que soit la casse de
        # sa source. Reprendre tel quel un accent pris sur un `E` (ymax 796) pour le poser
        # sur un `A` (ymax 785) le laisserait flotter 11 unités trop haut — assez pour se
        # voir à 40 px. `ecart` étant mesuré sur un couple que la police possède déjà, le
        # calcul rend exactement 0 pour ce couple-là : on ne déplace jamais un accent que le
        # dessinateur avait posé lui-même.
        dy = (boite_base[3] + ecart) - boite_accent[1]

    contours = police.contours(base) + _decale(morceaux, dx, dy)
    return _glyphe(police.jeu, contours), police.chasse(base)


def ligature(police: Police, gauche: str, droite: str,
             recouvrement: float) -> tuple[object, int] | None:
    """Synthèse : deux lettres accolées, avec le recouvrement d'une vraie ligature.

    `recouvrement` est une fraction de la chasse de la PREMIÈRE lettre — cf.
    `recouvrement_ligature`, qui le mesure sur une police qui possède un vrai `œ` plutôt que
    de le poser au jugé."""
    if not (police.a(gauche) and police.a(droite)):
        return None
    decalage = police.chasse(gauche) * (1 - recouvrement)
    contours = police.contours(gauche) + _decale(police.contours(droite), decalage, 0)
    return _glyphe(police.jeu, contours), int(round(decalage + police.chasse(droite)))


def recouvrement_ligature(reference: Police | None) -> float:
    """De combien la seconde lettre d'une ligature mord sur la première, en fraction de la
    chasse de la première.

    Mesuré sur `reference` si elle possède un VRAI `œ` — ComicNeue-Bold en a un :
    `o` 517 + `e` 491 = 1008 dégroupés, contre 829 pour le `œ`, donc la seconde lettre
    commence 179 unités avant la fin de la première, soit 0,346 de la chasse du `o`.
    Sans référence, `RECOUVREMENT_LIGATURE` reprend ce même chiffre — mais mesuré vaut
    toujours mieux que recopié : une police plus étroite ligature autrement."""
    if reference is None or not all(reference.a(c) for c in "oeœ"):
        return RECOUVREMENT_LIGATURE
    chasse_o = reference.chasse("o")
    if chasse_o <= 0:
        return RECOUVREMENT_LIGATURE
    decalage = reference.chasse("œ") - reference.chasse("e")
    return max(0.0, min(0.6, 1 - decalage / chasse_o))


def tiret(police: Police, facteur: float, chasse: int) -> tuple[object, int] | None:
    """Synthèse : le trait d'union étiré horizontalement, puis recentré dans sa chasse."""
    source = "-" if police.a("-") else ("‐" if police.a("‐") else None)
    if source is None:
        return None
    contours = police.contours(source)
    boite = _boite(contours)
    if boite is None:
        return None
    largeur = (boite[2] - boite[0]) * facteur
    marge = (chasse - largeur) / 2
    # Une SEULE affine, plutôt qu'un étirement puis une translation : un glyphe TrueType déjà
    # compilé ne se redessine pas sans sa table `glyf`, et réouvrir une police intermédiaire
    # pour déplacer un trait serait absurde. x ↦ (x − xMin)·facteur + marge.
    return _glyphe(police.jeu, contours,
                   (facteur, 0, 0, 1, marge - boite[0] * facteur, 0)), chasse


def forme_guillemet(reference: Police | None) -> tuple[float, float, float, float]:
    """Les proportions d'un guillemet, RAPPORTÉES À LA HAUTEUR D'X, lues sur une police qui
    en possède de vrais.

    Rend `(hauteur, largeur, pied, chasse)`, tous en fraction de la hauteur d'x.

    ⚠ C'est ici que se joue le seul glyphe de cet outil dont la forme ne dérive d'aucun
    modèle interne : un chevron d'opérateur mathématique n'est pas un guillemet. Il est plus
    haut, il vise le centre mathématique et non la hauteur d'x, et deux chevrons collés
    donnent `<<`, pas `«` — c'est exactement ce qui sortait de la première version.

    Plutôt que d'inventer trois réglages, on lit ceux d'une police qui a résolu le problème.
    ComicNeue-Bold, à `o` de hauteur d'x 493 : `«` occupe 50..540 × 57..433 pour une chasse
    de 580, soit une hauteur de 0,763 hauteur d'x, une largeur de 0,994, un pied à 0,116 et
    une chasse de 1,177. On reporte ces rapports sur la police à compléter, et son propre
    chevron est mis à l'échelle — en x et en y séparément — pour les tenir."""
    defaut = (0.763, 0.994, 0.116, 1.177)
    if reference is None or not (reference.a("«") and reference.a("o")):
        return defaut
    boite = reference.boite("«")
    hauteur_x = (reference.boite("o") or (0, 0, 0, 0))[3]
    if not boite or hauteur_x <= 0:
        return defaut
    return ((boite[3] - boite[1]) / hauteur_x, (boite[2] - boite[0]) / hauteur_x,
            boite[1] / hauteur_x, reference.chasse("«") / hauteur_x)


def guillemet(police: Police, ouvrant: bool,
              reference: Police | None) -> tuple[object, int] | None:
    """Synthèse : deux chevrons de la police, redimensionnés aux proportions d'un vrai
    guillemet (cf. `forme_guillemet`) et posés à hauteur d'x.

    ⚠ **Ce n'est plus le défaut, et c'est une mesure, pas un avis.** Rendu à 44 px côte à
    côte avec la greffe, sur « Attends ! » et « Ça alors ? », le résultat lit `<< ... >>` :
    les proportions sont bonnes, la FORME ne l'est pas. Un chevron d'opérateur est un trait
    plié à angle vif ; un guillemet est deux virgules couchées. Aucune mise à l'échelle ne
    transforme l'un en l'autre. La fonction reste disponible (`--guillemets synthese`) pour
    une police dont le chevron serait plus rond, mais pour Wildjess la greffe gagne.

    ⚠ Le redimensionnement est ANISOTROPE. Le chevron de Wildjess est proportionnellement
    plus étroit que celui de Comic Neue (478×746 contre 403×485) : mis à l'échelle
    uniformément pour tenir la hauteur visée, la paire déborderait la largeur d'un guillemet
    de 13 %. On comprime donc légèrement en x. Un chevron est un trait plié — il supporte
    cette compression là où une lettre ne le supporterait pas."""
    source = "<" if ouvrant else ">"
    if not police.a(source):
        return None
    contours = police.contours(source)
    boite = _boite(contours)
    hauteur_x = (police.boite("o") or (0, 0, 0, 0))[3] if police.a("o") else 0
    if boite is None or hauteur_x <= 0:
        return None

    part_hauteur, part_largeur, part_pied, part_chasse = forme_guillemet(reference)
    hauteur_visee = part_hauteur * hauteur_x
    largeur_visee = part_largeur * hauteur_x
    y_bas = part_pied * hauteur_x

    echelle_y = hauteur_visee / (boite[3] - boite[1])
    # La paire doit tenir dans `largeur_visee`, écart compris. L'écart est pris à 15 % de la
    # largeur totale : c'est ce que montre le `«` de Comic Neue (490 d'encre pour deux
    # chevrons de 208).
    largeur_chevron = largeur_visee * (1 - ECART_GUILLEMET) / 2
    echelle_x = largeur_chevron / (boite[2] - boite[0])
    ecart = largeur_visee * ECART_GUILLEMET

    stylo = TTGlyphPen(police.jeu)
    for decalage in (0.0, largeur_chevron + ecart):
        _rejouer(contours, TransformPen(stylo, (
            echelle_x, 0, 0, echelle_y,
            decalage - boite[0] * echelle_x, y_bas - boite[1] * echelle_y)))
    glyphe = stylo.glyph()

    # La chasse est celle du modèle, et l'encre est centrée dedans : la caler sur l'encre
    # collerait le guillemet au mot.
    chasse = part_chasse * hauteur_x
    marge = (chasse - largeur_visee) / 2
    if marge > 1:
        stylo = TTGlyphPen(police.jeu)
        for decalage in (marge, marge + largeur_chevron + ecart):
            _rejouer(contours, TransformPen(stylo, (
                echelle_x, 0, 0, echelle_y,
                decalage - boite[0] * echelle_x, y_bas - boite[1] * echelle_y)))
        glyphe = stylo.glyph()
    return glyphe, int(round(chasse))


def greffe_externe(police: Police, sources: list[Police],
                   caractere: str) -> tuple[tuple[object, int], Police] | None:
    """Dernier recours : le glyphe est copié de la première `sources` qui le possède, mise à
    l'échelle si les deux polices n'ont pas le même `unitsPerEm`.

    Rend `((glyphe, chasse), source)` — la source est rendue pour que le résumé puisse dire
    D'OÙ vient chaque glyphe étranger, et non seulement qu'il l'est."""
    for source in sources:
        if not source.a(caractere):
            continue
        facteur = police.upem / source.upem
        transformation = (facteur, 0, 0, facteur, 0, 0) if facteur != 1 else None
        glyphe = _glyphe(police.jeu, source.contours(caractere), transformation)
        return (glyphe, int(round(source.chasse(caractere) * facteur))), source
    return None


# --------------------------------------------------------------------------------------
# Écriture
# --------------------------------------------------------------------------------------

def _nom_de_glyphe(caractere: str, pris: set[str]) -> str:
    """Un nom de glyphe libre et lisible. Le nom n'a aucun effet sur le rendu, mais un
    `uni00C0` dans un éditeur de police est moins parlant qu'un `Agrave`."""
    usuels = {"À": "Agrave", "Â": "Acircumflex", "Ä": "Adieresis", "Ç": "Ccedilla",
              "È": "Egrave", "É": "Eacute", "Ê": "Ecircumflex", "Ë": "Edieresis",
              "Î": "Icircumflex", "Ï": "Idieresis", "Ô": "Ocircumflex", "Ö": "Odieresis",
              "Ù": "Ugrave", "Ú": "Uacute", "Û": "Ucircumflex", "Ü": "Udieresis",
              "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE",
              "—": "emdash", "–": "endash",
              "«": "guillemotleft", "»": "guillemotright",
              "♪": "musicalnote", "♥": "heart"}
    propose = usuels.get(caractere, "uni%04X" % ord(caractere))
    if propose not in pris:
        return propose
    suffixe = 1
    while f"{propose}.{suffixe}" in pris:
        suffixe += 1
    return f"{propose}.{suffixe}"


def _ajouter(tt: TTFont, caractere: str, nom: str, glyphe, chasse: int) -> None:
    """Pose un glyphe dans la police et le rend accessible par son point de code."""
    tt.setGlyphOrder(tt.getGlyphOrder() + [nom])
    tt["glyf"].glyphs[nom] = glyphe
    # Un glyphe sorti d'un stylo n'a pas encore de boîte : `maxp.recalc` et l'approche gauche
    # de `hmtx` la lisent tous les deux, et sans elle la police ne se compile pas.
    glyphe.recalcBounds(tt["glyf"])
    tt["hmtx"].metrics[nom] = (int(chasse), int(getattr(glyphe, "xMin", 0) or 0))
    for table in tt["cmap"].tables:
        if table.isUnicode():
            table.cmap[ord(caractere)] = nom


def _renommer(tt: TTFont, nom_famille: str) -> None:
    """Change le nom de la police, en CONSERVANT le copyright d'origine.

    Le fichier produit n'est pas la police d'origine : lui laisser son nom ferait qu'une
    installation système écraserait l'une par l'autre, et que le RAPPORT.md nommerait une
    police qui n'est pas celle qui a servi."""
    postscript = "".join(nom_famille.split())
    table = tt["name"]
    ancien = table.getDebugName(0) or ""
    for enregistrement in table.names:
        if enregistrement.nameID in (1, 3, 4, 16):
            table.setName(nom_famille, enregistrement.nameID,
                          enregistrement.platformID, enregistrement.platEncID,
                          enregistrement.langID)
        elif enregistrement.nameID == 6:
            table.setName(postscript, 6, enregistrement.platformID,
                          enregistrement.platEncID, enregistrement.langID)
        elif enregistrement.nameID == 0:
            # On AJOUTE la mention de dérivation, on n'efface pas le copyright d'origine.
            mention = (f"{ancien} — Glyphes latins complétés par "
                       f"tools/completer_police.py (Angelith). Travail dérivé, non "
                       f"redistribué ; les droits d'origine s'appliquent.")
            table.setName(mention, 0, enregistrement.platformID,
                          enregistrement.platEncID, enregistrement.langID)


# --------------------------------------------------------------------------------------

def completer(entree: Path, sortie: Path, nom_famille: str | None = None,
              bouche_trou: Path | None = None,
              guillemets: str = "greffe") -> tuple[list[Faite], str]:
    """Complète `entree` dans `sortie`.

    Rend `(ce qui a été ajouté, ce qui n'a PAS pu l'être)`. Le second n'est pas une erreur —
    une police de lettrage n'a pas à savoir tout dessiner — mais il doit REMONTER : chaque
    caractère qui reste absent est une bulle qui basculera en silence sur une autre police,
    et c'est précisément le défaut qu'on répare ici."""
    police = Police(entree)
    ecart = _ecart_accent(police)
    secours = [Police(c) for c in polices_de_secours(bouche_trou)]
    # La première police de secours sert AUSSI de modèle typographique : c'est elle qui
    # fournit les proportions d'un vrai guillemet et le recouvrement d'une vraie ligature,
    # sans qu'aucun de ses tracés n'entre dans le fichier produit.
    modele = secours[0] if secours else None
    recouvrement = recouvrement_ligature(modele)

    faites: list[Faite] = []
    ratees: list[str] = []
    pris = set(police.tt.getGlyphOrder())

    def poser(caractere: str, produit, technique: str, detail: str) -> None:
        if produit is None:
            ratees.append(caractere)
            return
        glyphe, chasse = produit
        nom = _nom_de_glyphe(caractere, pris)
        pris.add(nom)
        _ajouter(police.tt, caractere, nom, glyphe, chasse)
        faites.append(Faite(caractere, technique, detail))

    for caractere, (base, forme) in LETTRES_ACCENTUEES.items():
        if police.a(caractere):
            continue
        poser(caractere, lettre_accentuee(police, base, forme, ecart),
              "greffe interne", f"{base} + accent {forme}")

    for caractere, (gauche, droite) in LIGATURES.items():
        if police.a(caractere):
            continue
        poser(caractere, ligature(police, gauche, droite, recouvrement),
              "synthèse", f"{gauche} + {droite} accolés, recouvrement {recouvrement:.0%}")

    for caractere, (facteur, chasse) in TIRETS.items():
        if police.a(caractere):
            continue
        poser(caractere, tiret(police, facteur, chasse),
              "synthèse", f"trait d'union étiré ×{facteur:g}, chasse {chasse}")

    for caractere, ouvrant in (("«", True), ("»", False)):
        if police.a(caractere):
            continue
        if guillemets == "greffe":
            trouve = greffe_externe(police, secours, caractere)
            if trouve is None:
                ratees.append(caractere)
                continue
            produit, source = trouve
            poser(caractere, produit, "greffe externe", f"copié de {source.chemin.name}")
            continue
        poser(caractere, guillemet(police, ouvrant, modele),
              "synthèse",
              f"chevron {'<' if ouvrant else '>'} doublé, aux proportions de "
              f"{modele.chemin.name if modele else 'référence par défaut'}")

    for caractere in GREFFE_EXTERNE:
        if police.a(caractere):
            continue
        trouve = greffe_externe(police, secours, caractere)
        if trouve is None:
            ratees.append(caractere)
            continue
        produit, source = trouve
        poser(caractere, produit, "greffe externe", f"copié de {source.chemin.name}")

    if nom_famille:
        _renommer(police.tt, nom_famille)

    police.tt["maxp"].recalc(police.tt)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    police.tt.save(str(sortie))
    return faites, "".join(ratees)


def manquants(chemin: Path, alphabet: str = ALPHABET_FRANCAIS) -> str:
    """Les caractères d'`alphabet` que la police de `chemin` ne sait pas dessiner.

    ⚠ Test sur la `cmap`, pas sur le rendu : à ce stade on vérifie que le glyphe EXISTE.
    `manga.typeset.a_le_glyphe` fait le contrôle plus sévère (le rendu diffère-t-il du
    `.notdef` ?) au moment du lettrage, et c'est lui qui a le dernier mot."""
    cmap = TTFont(str(chemin), lazy=True).getBestCmap()
    return "".join(c for c in dict.fromkeys(alphabet)
                   if not c.isspace() and ord(c) not in cmap)


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        description="Complète une police de lettrage pour qu'elle couvre le français.",
        epilog="⚠ Produit un travail dérivé de la police d'entrée. Vérifie sa licence, et "
               "ne redistribue pas le fichier produit.")
    analyseur.add_argument("entree", type=Path, help="la police .ttf à compléter")
    analyseur.add_argument("-o", "--sortie", type=Path,
                           help="défaut : <entree>_complet.ttf, à côté de l'entrée")
    analyseur.add_argument("--nom", help="nouveau nom de famille "
                                         "(défaut : « <nom d'origine> Complet »)")
    analyseur.add_argument("--bouche-trou", type=Path, default=None,
                           help=f"police de greffe externe (défaut : {BOUCHE_TROU.name})")
    analyseur.add_argument("--guillemets", choices=("greffe", "synthese"),
                           default="greffe",
                           help="« » copiés d'une police qui en a de vrais (défaut), ou "
                                "fabriqués avec les chevrons de la police à compléter. "
                                "Cf. `guillemet` : la synthèse a été essayée et elle donne "
                                "« << », pas « « » — c'est le seul arbitrage de cet outil "
                                "qui se tranche à l'œil, et il a été tranché")
    args = analyseur.parse_args(argv)
    configurer_stdout()

    if not args.entree.is_file():
        print(f"❌ Police introuvable : {args.entree}", file=sys.stderr)
        return 2

    origine = TTFont(str(args.entree), lazy=True)
    nom_origine = origine["name"].getDebugName(1) or args.entree.stem
    nom_famille = args.nom or f"{nom_origine.strip()} Complet"
    sortie = args.sortie or args.entree.with_name(args.entree.stem + "_complet.ttf")

    avant = manquants(args.entree)
    faites, ratees = completer(args.entree, sortie, nom_famille, args.bouche_trou,
                               args.guillemets)
    apres = manquants(sortie)

    print(f"  {args.entree}  →  {sortie}")
    print(f"  nom de famille : « {nom_famille} »")
    print(f"  manquants avant : {len(avant)}  ·  après : {len(apres)}")

    if faites:
        print()
        print("  Glyphes ajoutés :")
        largeur = max(len(f.technique) for f in faites)
        for f in faites:
            print(f"    {f.caractere}  U+{ord(f.caractere):04X}  "
                  f"{f.technique:<{largeur}}  {f.detail}")

    externes = [f.caractere for f in faites if f.technique == "greffe externe"]
    if externes:
        print()
        print(f"  ⚠ {len(externes)} glyphe(s) viennent d'une AUTRE police "
              f"({' '.join(externes)}) : leur dessin ne sera pas au style de "
              f"l'originale.")

    if ratees:
        # Pas une erreur : une police de lettrage n'a pas à tout savoir dessiner. Mais
        # taire ce trou réinstallerait le silence que cet outil existe pour supprimer.
        print()
        print(f"  ⚠ NON produit(s) : {' '.join(ratees)} — aucun tracé interne ne s'en "
              f"approche, et aucune police de secours disponible ne les possède.")
        print("    Les bulles qui en contiennent basculeront encore sur une police de "
              "repli. Polices de secours essayées :")
        for chemin in polices_de_secours(args.bouche_trou):
            print(f"      · {chemin}")

    if apres:
        print()
        detail = " ".join("%s (U+%04X)" % (c, ord(c)) for c in apres)
        print(f"❌ Il manque encore : {detail}", file=sys.stderr)
        print("   La police produite ne couvre pas le français : le lettrage "
              "basculerait encore, en silence, sur une police de repli.",
              file=sys.stderr)
        return 1

    print()
    print("  ✓ Couverture française complète.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
