# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Analyse de la mise en page d'une page de roman japonais — **sans le moindre modèle**.

## Pourquoi ce module existe, et pourquoi il est purement géométrique

`manga-ocr` redimensionne son entrée en 224 × 224. Mesuré sur *manga C*
Vol.1 page 100 (2 452 × 3 543 px), une colonne entière de ~40 caractères (2 733 px de haut)
en ressort **inventée** : 23 à 29 caractères rendus, sans rapport avec la page. Les mêmes
pixels découpés en tranches de 8 à 16 caractères sont lus correctement à ~95 %.

Tout ce module existe donc pour répondre à une seule question : **où couper ?** Et il y
répond sans réseau de neurones, parce qu'une page de roman imprimé est une grille régulière
— exactement le raisonnement que `manga/ocr.py` tient déjà pour l'ordre de lecture (« le
tout sans le moindre modèle »).

## Les trois mesures qui fixent les constantes

**Le seuil de binarisation n'est pas un détail.** À `< 200`, le halo JPEG autour des glyphes
donne une médiane de 17 px d'encre par colonne d'image : il ne reste **aucune** gouttière et
la page sort en UNE bande. À `< 100`, la médiane tombe à 0 et 1 518 colonnes sur 2 452 sont
franchement vides. Le seuil ne déplace pas un compromis, il fait exister ou non la structure.

**Une bande brute n'est pas une colonne.** Un glyphe fin — un `「`, un `ー` d'allongement —
laisse une colonne d'image sans encre au milieu de sa propre colonne de texte : 41 bandes
brutes pour 16 colonnes réelles sur la page mesurée. D'où la fusion.

**L'indentation ne se lit pas sur le haut d'encre brut.** Le haut d'encre d'une colonne varie
de ±20 px selon son premier glyphe (`ま` monte plus haut que `お`), soit un tiers de cellule.
Sur la page mesurée, les `y0` se répartissent en 368-386, 407-411 et 439-456 : c'est le
**mode** (409) qui donne le haut du corps, et le troisième groupe — exactement les quatre
ouvertures de paragraphe de la page — se détache à +30/+47 px. Prendre le minimum aurait
classé douze colonnes sur seize comme indentées.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

# --- Binarisation ---------------------------------------------------------- #
SEUIL_ENCRE = 112
# Seuils essayés quand aucun n'est imposé. Le balayage entier coûte 63 ms par page —
# négligeable devant les ~30 s d'OCR qu'il conditionne.
SEUILS_BALAYAGE = (88, 96, 104, 112, 120, 128)
# Au-delà de cette part d'encre, la page n'est pas du texte.
ENCRE_MAX = 0.12
# Largeur admise pour une colonne « régulière », en fraction du pas. C'est la mesure qui note
# une binarisation (cf. `regularite`).
REGULARITE_FRAC = 0.20

# --- Colonnes -------------------------------------------------------------- #
SEUIL_BANDE = 2            # px d'encre pour qu'une colonne d'image compte comme non vide
FUSION_FRAC = 0.15         # écart de fusion, en fraction de la plus large bande brute
CORPS_FRAC = 0.50          # largeur mini d'une colonne de corps, en fraction de la plus large
RUBY_MIN, RUBY_MAX = 0.22, 0.68    # largeur d'une ruby, en fraction du pas
RUBY_ECART_FRAC = 0.50     # écart maxi entre une ruby et le bord droit de sa colonne
MOBILIER_HAUTEUR_FRAC = 0.30       # sous cette fraction de la plus haute, une bande est courte
# Gouttière qui isole un fragment du corps de sa colonne, en cellules. Une colonne de roman
# ne contient jamais de cellule vide : un paragraphe qui s'achève laisse la colonne se
# terminer, il n'y ouvre pas de trou. Un trou d'une cellule et demie dénonce donc un corps
# étranger — en pratique le numéro de page posé juste au-dessus de la colonne.
MOBILIER_ECART_FRAC = 1.5
MOBILIER_CASES_MAX = 2.0   # au-delà, le fragment est du texte, pas un numéro de page

# --- Grille ---------------------------------------------------------------- #
INDENT_FRAC = 0.45         # décalage mini du haut d'une colonne pour ouvrir un paragraphe
TOLERANCE_MODE_FRAC = 0.25  # largeur de groupement des `y0` pour en tirer le mode
CREUX_MIN = 3              # hauteur mini d'une gouttière, en px (plancher absolu)
# Hauteur mini d'une gouttière pour qu'on ait le droit d'y couper, en fraction du pas.
# Un glyphe japonais est plein de blancs internes : mesuré sur une colonne de 44 caractères
# de la page 100, on relève 143 gouttières d'au moins 1 px, dont les largeurs vont de 1 à
# 87 px. Les fines (1 à 7 px) séparent les TRAITS d'un même signe ; y couper donne un demi-
# glyphe à chacune des deux tranches, et le modèle — qui rend toujours quelque chose de
# plausible — invente un caractère de chaque côté. C'est l'origine exacte des doublons
# mesurés (`苦労労もせ`, `安物でで`, `ようにに`, `忘れれ`). Les gouttières d'au moins 0,15 × pas
# ≈ 9 px sont, elles, de vraies frontières entre caractères.
CREUX_COUPE_FRAC = 0.15
CARACTERES_PAR_TRANCHE = 10
# Rayon de recherche d'une gouttière autour de la coupe visée, en fraction du pas. Étroit,
# et c'est le point : la GRILLE dit où tombe la frontière entre deux caractères, la gouttière
# ne fait que l'affiner. À 0,45 le rayon couvrait presque une cellule entière et déplaçait la
# coupe d'un caractère — mesuré page 100, la coupe visée à y = 1 002 partait à 1 023, en
# plein milieu d'un glyphe, que les deux tranches lisaient alors chacune en entier (`苦労` /
# `労もせ…`).
RECHERCHE_COUPE_FRAC = 0.25

# --- Verdict de page ------------------------------------------------------- #
COLONNES_MIN_TEXTE = 4
TITRE_PAS_MIN = 1.6        # une page de titre a des glyphes nettement plus grands
TITRE_COLONNES_MAX = 3
SATURATION_MAX = 12        # au-delà, la page est en couleur : c'est une illustration

CORPS = "corps"
RUBY = "ruby"
MOBILIER = "mobilier"

TEXTE = "texte"
ILLUSTRATION = "illustration"
TITRE = "titre"


@dataclass
class Colonne:
    """Une colonne de texte vertical, prête à être découpée en tranches d'OCR."""
    x0: int
    x1: int
    y0: int
    y1: int
    genre: str = CORPS
    indentee: bool = False
    # Nombre de caractères que la GRILLE prédit. C'est un garde-fou gratuit : l'OCR rendra
    # une chaîne, et un écart franc entre les deux dénonce une hallucination sans qu'aucun
    # humain n'ait à relire (cf. `scan/lecture.py`).
    cases: int = 0
    coupes: list[int] = field(default_factory=list)
    # Boîtes des ruby satellites, jamais incluses dans le crop de la colonne : les mêler au
    # texte de base les fait lire en alternance et corrompt la ligne entière.
    ruby: list[tuple[int, int, int, int]] = field(default_factory=list)
    # Au moins une coupe n'a trouvé aucune gouttière et est tombée sur du plein.
    coupe_forcee: bool = False

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x0, self.y0, self.x1, self.y1)

    def tranches(self) -> list[tuple[int, int]]:
        """Intervalles `[haut, bas)` à découper, dans l'ordre de lecture (haut → bas)."""
        bornes = [self.y0, *self.coupes, self.y1]
        return [(a, b) for a, b in zip(bornes, bornes[1:]) if b > a]


@dataclass
class PlanPage:
    verdict: str
    colonnes: list[Colonne]
    pas: float
    taille: tuple[int, int]
    part_encre: float = 0.0
    seuil: int = SEUIL_ENCRE
    motif: str = ""            # pourquoi ce verdict — pour le rapport

    @property
    def corps(self) -> list[Colonne]:
        return [c for c in self.colonnes if c.genre == CORPS]

    @property
    def mobilier(self) -> list[Colonne]:
        return [c for c in self.colonnes if c.genre == MOBILIER]


# --------------------------------------------------------------------------- #
#  Binarisation
# --------------------------------------------------------------------------- #

def binariser(image: Image.Image, seuil: int = SEUIL_ENCRE) -> np.ndarray:
    """Masque booléen de l'encre, à un seuil imposé."""
    return np.asarray(image.convert("L")) < seuil


def saturation(image: Image.Image) -> int:
    """Saturation moyenne, mesurée sur une vignette.

    Une page de texte scannée en RVB reste grise ; une illustration couleur ne l'est pas.
    Sur une vignette 64 × 64 parce que la question ne demande aucune précision et qu'une
    page pèse 8 mégapixels."""
    if image.mode not in ("RGB", "RGBA"):
        return 0
    arr = np.asarray(image.convert("RGB").resize((64, 64), Image.BILINEAR)).astype(np.int16)
    return int((arr.max(axis=2) - arr.min(axis=2)).mean())


# --------------------------------------------------------------------------- #
#  Segments, bandes, colonnes
# --------------------------------------------------------------------------- #

def segments(plein) -> list[tuple[int, int]]:
    """Suites d'indices vrais consécutifs d'un vecteur booléen — `[(début, fin), …]`.

    Sert sur les deux axes : les bandes verticales de la page, et les gouttières
    inter-caractères à l'intérieur d'une colonne. Le même besoin, donc la même fonction."""
    plein = np.asarray(plein, dtype=bool)
    if plein.size == 0:
        return []
    bords = np.diff(plein.astype(np.int8))
    debuts = [int(i) + 1 for i in np.flatnonzero(bords == 1)]
    fins = [int(i) + 1 for i in np.flatnonzero(bords == -1)]
    if plein[0]:
        debuts.insert(0, 0)
    if plein[-1]:
        fins.append(int(plein.size))
    return list(zip(debuts, fins))


def _etendue(encre: np.ndarray, x0: int, x1: int) -> tuple[int, int]:
    """Bornes verticales de l'encre entre deux abscisses, ou `(0, 0)` si la bande est vide."""
    ou = np.flatnonzero(encre[:, x0:x1].any(axis=1))
    return (int(ou[0]), int(ou[-1]) + 1) if ou.size else (0, 0)


def bandes_brutes(encre: np.ndarray, *, seuil: int = SEUIL_BANDE
                  ) -> list[tuple[int, int, int, int]]:
    """Bandes verticales non vides, avec leur étendue : `[(x0, x1, y0, y1), …]`."""
    proj = encre.sum(axis=0)
    sorties = []
    for x0, x1 in segments(proj > seuil):
        y0, y1 = _etendue(encre, x0, x1)
        if y1 > y0:
            sorties.append((x0, x1, y0, y1))
    return sorties


def separer_mobilier(bandes: list[tuple[int, int, int, int]]):
    """Sépare le corps du **mobilier de page** (numéro de page, titre courant).

    Le corps est défini par les bandes HAUTES : sur la page mesurée, les colonnes de texte
    font 2 700 px et le numéro de page 15. Une bande dont l'étendue verticale tombe
    entièrement hors de celle du corps est du mobilier.

    ⚠ Ce tri doit passer **avant** la fusion, sans quoi le numéro de page est absorbé par la
    colonne voisine : mesuré page 100, le `90` en marge haute (x 2 059-2 063) se faisait
    avaler par la colonne x 1 974-2 030, et l'OCR le lisait à la suite du texte."""
    if not bandes:
        return [], []
    hauteur_max = max(y1 - y0 for _x0, _x1, y0, y1 in bandes)
    hautes = [b for b in bandes if (b[3] - b[2]) > MOBILIER_HAUTEUR_FRAC * hauteur_max]
    if not hautes:
        return list(bandes), []
    haut = min(b[2] for b in hautes)
    bas = max(b[3] for b in hautes)
    corps, mobilier = [], []
    for b in bandes:
        (mobilier if (b[3] <= haut or b[2] >= bas) else corps).append(b)
    return corps, mobilier


def fusionner(bandes: list[tuple[int, int, int, int]], encre: np.ndarray, *,
              frac: float = FUSION_FRAC) -> list[tuple[int, int, int, int]]:
    """Réunit les bandes qu'un glyphe fin a coupées en deux.

    L'écart de fusion est **relatif** à la plus large bande brute — un écart en pixels ne
    peut pas suivre un scan pris à une autre résolution. Mesuré page 100 : 0,15 × 68 ≈ 10 px,
    ce qui ramène 41 bandes à 16 colonnes, exactement le compte réel."""
    if not bandes:
        return []
    ecart = max(2, round(frac * max(x1 - x0 for x0, x1, *_ in bandes)))
    fusionnees: list[list[int]] = []
    for x0, x1, *_ in sorted(bandes):
        if fusionnees and x0 - fusionnees[-1][1] <= ecart:
            fusionnees[-1][1] = max(fusionnees[-1][1], x1)
        else:
            fusionnees.append([x0, x1])
    sorties = []
    for x0, x1 in fusionnees:
        y0, y1 = _etendue(encre, x0, x1)
        if y1 > y0:
            sorties.append((x0, x1, y0, y1))
    return sorties


def bande_de_texte(bandes: list[tuple[int, int, int, int]], pas: float) -> tuple[float, float]:
    """Ordonnées entre lesquelles vit le texte de la page.

    Le haut est la **médiane** des débuts de colonnes, jamais leur minimum : une seule
    colonne contaminée par un numéro de page collé au-dessus d'elle tirerait le minimum
    jusqu'au numéro, et la bande de texte engloberait ce qu'on cherche justement à écarter.
    Le bas est le maximum, lui : la colonne la plus longue définit le fond de la justification,
    et aucune ne descend plus bas qu'elle."""
    if not bandes:
        return (0.0, 0.0)
    haut = float(np.median([b[2] for b in bandes])) - 0.5 * pas
    bas = float(max(b[3] for b in bandes)) + 0.5 * pas
    return (haut, bas)


def _fragments_entre_creux(bande: tuple[int, int, int, int],
                           creux: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Les morceaux de colonne que les gouttières `creux` laissent entre elles, en `(y, y)`."""
    _x0, _x1, y0, y1 = bande
    fragments, curseur = [], y0
    for a, b in creux:
        if a > curseur:
            fragments.append((curseur, a))
        curseur = b
    if curseur < y1:
        fragments.append((curseur, y1))
    return fragments


def _est_mobilier(frag: tuple[int, int], court: float, haut: float, bas: float) -> bool:
    """Court ET hors de la justification.

    La brièveté ne suffit pas : mesuré page 100, la réplique `「は、はやく金を——」` se
    termine par un `」` isolé derrière un long tiret, ce qui en fait un fragment court
    séparé par une large gouttière — exactement le profil d'un numéro de page. Sans le
    critère de position, la brique mangeait le crochet fermant."""
    if (frag[1] - frag[0]) >= court:
        return False
    return frag[1] <= haut or frag[0] >= bas


def elaguer(encre: np.ndarray, bande: tuple[int, int, int, int], pas: float,
            texte: tuple[float, float] | None = None):
    """Retire d'une colonne le mobilier qui lui est **collé** — `(colonne, [mobilier])`.

    `separer_mobilier` traite le cas facile, celui d'un numéro de page qui forme sa propre
    bande verticale (page 100 : le `90` en x 2 059-2 063, à droite de tout). Mais une page
    paire pose son numéro **au-dessus d'une colonne**, dans les mêmes abscisses : mesuré page
    200, la bande x 1 969-2 036 court de y 238 à 3 170, soit 2 932 px là où une colonne
    pleine en fait 2 740. La règle de marge ne voit alors rien à écarter, et l'OCR lit `200`
    à la suite du texte.

    Le discriminant est le blanc : un fragment de moins de deux cellules, séparé du reste par
    une gouttière d'une cellule et demie, n'appartient pas à la colonne. On n'élague qu'aux
    **extrémités** — un trou au milieu d'une colonne est un cas de typographie qu'on préfère
    laisser passer plutôt que de couper une phrase en deux."""
    x0, x1, _y0, _y1 = bande
    if pas <= 0:
        return bande, []
    creux = [g for g in gouttieres(encre, bande) if (g[1] - g[0]) >= MOBILIER_ECART_FRAC * pas]
    if not creux:
        return bande, []

    fragments = _fragments_entre_creux(bande, creux)
    if len(fragments) < 2:
        return bande, []

    court = MOBILIER_CASES_MAX * pas
    haut, bas = texte if texte else (float("inf"), float("-inf"))

    mobilier = []
    while len(fragments) > 1 and _est_mobilier(fragments[0], court, haut, bas):
        mobilier.append(fragments.pop(0))
    while len(fragments) > 1 and _est_mobilier(fragments[-1], court, haut, bas):
        mobilier.append(fragments.pop())
    if not mobilier:
        return bande, []
    return ((x0, x1, fragments[0][0], fragments[-1][1]),
            [(x0, x1, a, b) for a, b in mobilier])


def pas_de_page(bandes: list[tuple[int, int, int, int]]) -> float:
    """Avance d'un caractère, en pixels — la largeur médiane des colonnes de CORPS.

    Le japonais est carré : la largeur d'une colonne est aussi la hauteur d'un caractère.
    Vérifié page 100 — largeur médiane 63 px, et une colonne de 2 733 px y porte 40
    caractères, soit 68 px d'avance. C'est bien la même grandeur, à l'approximation près du
    dernier glyphe.

    ⚠ Ce n'est PAS le pas entre colonnes (~121 px page 100) : l'interligne d'un roman
    japonais réserve la place des furigana. Confondre les deux diviserait par deux le nombre
    de tranches et ramènerait l'hallucination que tout ce module sert à éviter."""
    if not bandes:
        return 0.0
    largeurs = [x1 - x0 for x0, x1, *_ in bandes]
    plafond = max(largeurs)
    corps = [w for w in largeurs if w >= CORPS_FRAC * plafond]
    return float(np.median(corps or largeurs))


def regularite(bandes: list[tuple[int, int, int, int]], pas: float) -> float:
    """Note d'une binarisation : **la grille qu'elle révèle est-elle régulière ?**

    Une page de roman est une grille de colonnes de largeur constante. Une binarisation
    réussie la fait apparaître ; une binarisation trop haute soude tout, une trop basse
    hache les glyphes. On compte donc les colonnes dont la largeur tient à 20 % près du pas,
    et on retranche la moitié des autres — les colonnes irrégulières sont du bruit, et une
    note qui ne récompenserait que le nombre choisirait le seuil le plus bruité."""
    if not bandes or pas <= 0:
        return 0.0
    justes = sum(1 for x0, x1, *_ in bandes if abs((x1 - x0) - pas) <= REGULARITE_FRAC * pas)
    return float(justes) - 0.5 * (len(bandes) - justes)


def choisir_seuil(image: Image.Image, seuils=SEUILS_BALAYAGE) -> tuple[np.ndarray, int, float]:
    """Binarise en **essayant**, et garde le seuil qui révèle la grille la plus régulière.

    Un seuil fixe ne tient pas d'un scan à l'autre, et l'écart entre le bon et le mauvais
    n'est pas un compromis mais une falaise. Mesuré sur cinq pages du Vol.1 :

    | seuil | 88 | 96 | 104 | 112 | 120 | 128 |
    |-------|---:|---:|----:|----:|----:|----:|
    | colonnes régulières (page 100) | 2 | 14 | — | **16** | — | 1 |
    | colonnes régulières (page 250) | 2 | 10 | — | **15** | — | 1 |

    À 128, *toutes* les pages s'effondrent sur une seule bande : le halo JPEG referme les
    gouttières et il n'y a plus de structure du tout. À 88, les glyphes se fragmentent. Aucune
    valeur fixe n'est sûre — mais la bonne se **reconnaît**, et c'est ce que fait cette
    fonction. Le balayage complet coûte 63 ms/page, contre ~30 s d'OCR qu'il conditionne.

    ⚠ Ne pas remplacer par Otsu. Sur une page de roman l'histogramme est écrasé sur le blanc
    (médiane 255, 95e centile 255) : Otsu y place le seuil à ~195, soit très au-delà de la
    falaise. Mesuré sur les pages 150 et 250, il rendait la page en **une seule colonne**."""
    gris = np.asarray(image.convert("L"))
    meilleur = (None, int(seuils[0]), -1.0)
    for seuil in seuils:
        encre = gris < seuil
        utiles, _mobilier = separer_mobilier(bandes_brutes(encre))
        fusionnees = fusionner(utiles, encre)
        note = regularite(fusionnees, pas_de_page(fusionnees))
        if note > meilleur[2]:
            meilleur = (encre, int(seuil), note)
    encre = meilleur[0] if meilleur[0] is not None else (gris < int(seuils[0]))
    return encre, meilleur[1], meilleur[2]


def classer(bandes: list[tuple[int, int, int, int]], pas: float):
    """Sépare les colonnes de corps de leurs ruby satellites.

    En écriture verticale, les furigana se posent **à droite** de leur graphie. Une bande
    étroite (0,22 à 0,68 fois le pas) collée au bord droit d'une colonne est donc sa ruby ;
    la même bande isolée est une colonne de corps très courte, qu'il ne faut pas perdre —
    une réplique d'un seul caractère existe.

    Renvoie `(colonnes, {indice de colonne: ruby})`, les colonnes dans l'ordre de lecture
    (droite → gauche)."""
    def largeur(b):
        return b[1] - b[0]

    candidates_ruby = [b for b in bandes if RUBY_MIN * pas <= largeur(b) <= RUBY_MAX * pas]
    colonnes = [b for b in bandes if largeur(b) > RUBY_MAX * pas]

    # Une bande étroite sans hôte n'est PAS une ruby : c'est une colonne courte. On la
    # réintègre avant de calculer les indices, sinon ils désigneraient la mauvaise colonne.
    def hote_de(b, liste):
        for i, c in enumerate(liste):
            if 0 <= b[0] - c[1] <= RUBY_ECART_FRAC * pas:
                return i
        return None

    orphelines = [b for b in candidates_ruby if hote_de(b, colonnes) is None]
    colonnes = sorted(colonnes + orphelines, key=lambda b: -b[0])

    rubis: dict[int, list[tuple[int, int, int, int]]] = {}
    for b in candidates_ruby:
        if b in orphelines:
            continue
        i = hote_de(b, colonnes)
        if i is not None:
            rubis.setdefault(i, []).append(tuple(b))
    return colonnes, rubis


# --------------------------------------------------------------------------- #
#  Grille : indentation et coupes
# --------------------------------------------------------------------------- #

def haut_du_corps(y0s: list[int], pas: float) -> int:
    """Haut de la grille — le **mode** des débuts d'encre, pas leur minimum.

    Un glyphe qui monte haut (`ま`, `「`) fait commencer l'encre de sa colonne 20 à 40 px
    au-dessus d'une colonne voisine qui commence par `お`. Sur la page 100, prendre le
    minimum (368) plaçait la barre d'indentation à 368 + 0,45 × 63 ≈ 396 et déclarait
    indentées douze colonnes sur seize. Le mode (409) en retient quatre — exactement les
    quatre ouvertures de paragraphe de la page."""
    if not y0s:
        return 0
    tolerance = max(1.0, TOLERANCE_MODE_FRAC * pas)
    meilleur, compte = y0s[0], 0
    for pivot in y0s:
        n = sum(1 for y in y0s if abs(y - pivot) <= tolerance)
        # À égalité, le groupe le plus HAUT gagne : une page très dialoguée peut friser
        # l'égalité entre lignes pleines et ouvertures, et le corps est toujours au-dessus.
        if n > compte or (n == compte and pivot < meilleur):
            meilleur, compte = pivot, n
    groupe = [y for y in y0s if abs(y - meilleur) <= tolerance]
    return int(round(float(np.median(groupe))))


def gouttieres(encre: np.ndarray, colonne: tuple[int, int, int, int], *,
               mini: int = CREUX_MIN) -> list[tuple[int, int]]:
    """Intervalles verticaux sans encre à l'intérieur d'une colonne — les blancs entre
    caractères, seuls endroits où l'on ait le droit de couper."""
    x0, x1, y0, y1 = colonne
    lignes = encre[y0:y1, x0:x1].any(axis=1)
    return [(y0 + a, y0 + b) for a, b in segments(~lignes) if (b - a) >= mini]


def coupes_de_colonne(encre: np.ndarray, colonne: tuple[int, int, int, int], pas: float, *,
                      caracteres: int = CARACTERES_PAR_TRANCHE,
                      decalage: float = 0.0) -> tuple[list[int], int, bool]:
    """Où couper la colonne pour l'OCR — `(coupes, cases, forcée)`.

    Chaque coupe visée à intervalle régulier est **ramenée au milieu d'une vraie gouttière**.
    C'est la correction du seul défaut résiduel mesuré : découpée à pas fixe, la page 100
    rendait `…この銃が目` puis `見えないのか？` — un `目` fantôme né d'un glyphe coupé en deux
    et lu par les deux tranches. Le même effet produisait des `ことははさっうさ` et des `やるや`.

    `decalage` (en fraction de tranche) sert à la relecture d'une colonne suspecte : refaire
    le même découpage donnerait exactement la même hallucination.

    `forcée` signale qu'au moins une coupe n'a trouvé aucune gouttière et est tombée sur du
    plein — la colonne part alors suspecte, et le rapport le dira."""
    x0, x1, y0, y1 = colonne
    hauteur = y1 - y0
    cases = max(1, int(round(hauteur / pas))) if pas > 0 else 1
    n = max(1, int(round(cases / max(1, caracteres))))
    if n <= 1:
        return [], cases, False

    # ⚠ Seules les gouttières LARGES sont des frontières entre caractères (cf.
    # `CREUX_COUPE_FRAC`). Couper dans un blanc intra-glyphe donne un demi-signe à chaque
    # tranche, et le modèle en invente un entier de part et d'autre.
    mini = max(CREUX_MIN, int(round(CREUX_COUPE_FRAC * pas)))
    creux = gouttieres(encre, colonne, mini=mini)
    rayon = max(3.0, RECHERCHE_COUPE_FRAC * pas)

    coupes: list[int] = []
    forcee = False
    for k in range(1, n):
        # La coupe visée est PROPORTIONNELLE à la hauteur, et ne passe pas par `cases`.
        # C'est délibéré : `cases` est une estimation biaisée (le pas mesure la largeur
        # d'encre, pas l'avance typographique), et la faire entrer dans le placement des
        # coupes propageait ce biais en le multipliant par le rang — sur une colonne
        # découpée en quatre, la dernière coupe dérivait de plusieurs caractères.
        vise = y0 + (k + decalage) * hauteur / n
        fenetre = [(b - a, (a + b) // 2) for a, b in creux
                   if abs((a + b) // 2 - vise) <= rayon]
        # À portée, on prend la gouttière la plus LARGE : une frontière franche est une
        # frontière sûre, alors que la plus proche peut n'être qu'un blanc intra-glyphe.
        candidats = [m for _l, m in sorted(fenetre, reverse=True) if m not in coupes]
        if candidats:
            coupes.append(candidats[0])
        else:
            coupes.append(int(round(vise)))
            forcee = True
    return sorted(set(c for c in coupes if y0 < c < y1)), cases, forcee


# --------------------------------------------------------------------------- #
#  Analyse d'une page
# --------------------------------------------------------------------------- #

def reclasser(plan: PlanPage, pas_reference: float, *,
              seuil: float = TITRE_PAS_MIN) -> bool:
    """Décide après coup si une page est une page de TITRE. Renvoie `True` si le verdict a
    changé.

    Le verdict `titre` est une **comparaison** au tome entier, pas une analyse : il n'y a
    donc rien à recalculer, et surtout rien à relire. C'est ce qui permet à l'orchestrateur
    d'analyser tout le tome d'abord, d'en tirer le pas médian, puis de trancher — au lieu de
    faire dépendre le verdict d'une page de celles qu'on a vues avant elle."""
    if plan.verdict == ILLUSTRATION or not pas_reference:
        return False
    attendu = (plan.pas >= seuil * pas_reference
               and len(plan.corps) <= TITRE_COLONNES_MAX)
    nouveau = TITRE if attendu else TEXTE
    if nouveau == plan.verdict:
        return False
    plan.verdict = nouveau
    plan.motif = (f"pas {plan.pas:.0f} px contre {pas_reference:.0f} px pour le tome"
                  if attendu else "")
    return True


def analyser(image: Image.Image, *, seuil: int | None = None,
             caracteres_par_tranche: int = CARACTERES_PAR_TRANCHE,
             pas_reference: float | None = None,
             encre_max: float = ENCRE_MAX,
             colonnes_min: int = COLONNES_MIN_TEXTE) -> PlanPage:
    """Plan complet d'une page : verdict, colonnes, ruby, coupes.

    `seuil` force la binarisation ; laissé à `None`, il est **choisi par balayage** (cf.
    `choisir_seuil`). Le forcer ne sert qu'à l'aperçu de réglage, où l'on veut voir l'effet
    d'une valeur précise.

    `pas_reference` est le pas MÉDIAN du tome, connu de l'orchestrateur après quelques pages.
    Il ne sert qu'à reconnaître une page de titre — des glyphes 1,6 fois plus grands que le
    corps du volume. Sans lui (première page, ou analyse d'une page isolée) le verdict
    `titre` n'est simplement pas rendu, ce qui est le bon repli : une page de titre lue comme
    du texte reste lisible, elle manque seulement son `#`."""
    largeur, hauteur = image.size
    if seuil is None:
        encre, seuil_retenu, _note = choisir_seuil(image)
    else:
        encre, seuil_retenu = binariser(image, seuil), int(seuil)
    part = float(encre.mean())

    if saturation(image) > SATURATION_MAX:
        return PlanPage(ILLUSTRATION, [], 0.0, (largeur, hauteur), part, seuil_retenu,
                        "page en couleur")
    if part > encre_max:
        return PlanPage(ILLUSTRATION, [], 0.0, (largeur, hauteur), part, seuil_retenu,
                        f"{part * 100:.1f} % d'encre")

    brutes = bandes_brutes(encre)
    utiles, mobilier = separer_mobilier(brutes)
    fusionnees = fusionner(utiles, encre)
    pas = pas_de_page(fusionnees)
    if pas <= 0 or len(fusionnees) < colonnes_min:
        return PlanPage(ILLUSTRATION, [], pas, (largeur, hauteur), part, seuil_retenu,
                        f"{len(fusionnees)} colonne(s) détectée(s)")

    # Second filet : le mobilier collé à une colonne, que la règle de marge ne peut pas voir.
    justification = bande_de_texte(fusionnees, pas)
    elaguees = []
    for bande in fusionnees:
        gardee, rejetee = elaguer(encre, bande, pas, justification)
        elaguees.append(gardee)
        mobilier.extend(rejetee)
    fusionnees = elaguees

    colonnes_brutes, rubis = classer(fusionnees, pas)
    reference = haut_du_corps([b[2] for b in colonnes_brutes], pas)

    colonnes: list[Colonne] = []
    for i, (x0, x1, y0, y1) in enumerate(colonnes_brutes):
        coupes, cases, forcee = coupes_de_colonne(
            encre, (x0, x1, y0, y1), pas, caracteres=caracteres_par_tranche)
        colonnes.append(Colonne(
            x0=x0, x1=x1, y0=y0, y1=y1, genre=CORPS,
            indentee=(y0 - reference) >= INDENT_FRAC * pas,
            cases=cases, coupes=coupes, coupe_forcee=forcee,
            ruby=[tuple(b) for b in rubis.get(i, [])],
        ))
    for x0, x1, y0, y1 in mobilier:
        colonnes.append(Colonne(x0=x0, x1=x1, y0=y0, y1=y1, genre=MOBILIER))

    verdict, motif = TEXTE, ""
    if (pas_reference and pas >= TITRE_PAS_MIN * pas_reference
            and len(colonnes_brutes) <= TITRE_COLONNES_MAX):
        verdict = TITRE
        motif = f"pas {pas:.0f} px contre {pas_reference:.0f} px pour le tome"
    return PlanPage(verdict, colonnes, pas, (largeur, hauteur), part, seuil_retenu, motif)
