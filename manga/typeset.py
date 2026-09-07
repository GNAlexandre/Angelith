# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Réinjection du texte traduit dans les bulles nettoyées : dessin déterministe via Pillow
(ImageDraw/ImageFont) — AUCUNE génération d'image, juste du texte peint.

────────────────────────────────────────────────────────────────────────────────────────
Réécrit pour corriger trois défauts mesurés sur le tome (150 planches, 797 bulles) :

**1. On composait dans la BBOX, pas dans la bulle.** Une bulle de la page 60 fait 281 px de
large en son milieu mais 53 px en haut : un texte calé sur la bbox débordait aux extrémités,
par-dessus le trait de contour et le dessin. La largeur disponible est désormais *mesurée
ligne par ligne* dans le masque (`geometry.width_profile`), et une ligne de texte n'utilise
que le **minimum** du profil sur toute sa hauteur — c'est ce `min` qui empêche le débordement
dans les coins arrondis.

**2. La largeur était estimée en NOMBRE DE CARACTÈRES.** `avg_char_w = getbbox("Wl")/2` puis
`textwrap.wrap` : une approximation qui ignore le crénage et les largeurs réelles, d'où des
lignes qui dépassaient malgré le calcul. On mesure maintenant en pixels avec
`font.getlength()`.

**3. Le repli était un trou.** À l'échec, l'ancien code renvoyait `min_size` **sans
revérifier que ça tenait** et sans rien rogner ; combiné au `fill=(0,0,0)` en dur, cela
donnait du texte noir sur fond noir hors de la bulle. Il y a désormais une **échelle de
replis explicite**, et tout débordement résiduel est *signalé*, jamais silencieux.

Deux règles non négociables, héritées de la philosophie du pipeline :
  · **ne jamais tronquer** — un échec non compté est un échec invisible ;
  · **ne jamais agrandir la bulle** — cela violerait l'invariant « aucun pixel hors masque
    n'est modifié », qui est le fondement de toute la brique.
Le bon correctif d'un débordement est de *raccourcir la traduction*, et le rapport dit
exactement quelle bulle de quelle page.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .clean import BubbleStyle, analyze_bubble
from core import installation

from .detection import BubbleRegion
from .geometry import width_profile

# Polices LIVRÉES avec le dépôt. Avant ce lot, `templates/fonts/` n'existait pas et la chaîne
# tombait SYSTÉMATIQUEMENT sur Arial — une police de traitement de texte, qui trahit une
# planche au premier coup d'œil. Voir `templates/fonts/README.md` pour les licences.
#
# ⚠ Chemins ABSOLUS, ancrés sur la racine du dépôt. Ils étaient relatifs, donc résolus
# contre le RÉPERTOIRE COURANT du processus : lancé d'ailleurs que de la racine,
# `Path.exists()` échouait sur les deux et la chaîne sautait directement aux polices
# système — un tome en Arial, sans un mot. Même idiome que `tools/banc.py`.
# ⚠ `installation.racine_livree()` et non `Path(__file__)` depuis la 2.31.0 : gelées, ces
# polices sont dépaquetées sous `sys._MEIPASS`, où `parents[1]` ne mène pas. La fonction rend
# la racine du dépôt hors gel, donc ces deux chemins sont inchangés dans le dépôt.
_RACINE = installation.racine_livree()
POLICES_LIVREES = (
    str(_RACINE / "templates" / "fonts" / "manga_typeset.ttf"),   # ta police, sans
                                                                  # toucher à la config
    str(_RACINE / "templates" / "fonts" / "ComicNeue-Bold.ttf"),  # défaut livré (OFL 1.1)
)

#: Polices SYSTÈME du repli à symboles, par plateforme — cf. `font_pour_texte`.
#:
#: ⚠ Cette liste était `["C:/Windows/Fonts/l_10646.ttf", "comic.ttf", "arial.ttf"]`, sans
#: distinction de plateforme, et c'était un défaut de PRODUIT autant que de CI : hors Windows,
#: aucun de ces chemins n'existe, la chaîne se réduisait à Comic Neue — une police latine — et
#: le `♪` de « Moi, je préfère les filles ♪ » repartait dans la branche « supprimé ». La
#: planche sortait donc amputée d'un signe que le traducteur avait bel et bien produit, en ne
#: laissant qu'une ligne de rapport. Même symptôme que le skip silencieux du lot 20 : ce qui
#: manque ne se voit qu'en lisant le compte-rendu.
#:
#: ⚠ Et surtout AUCUNE police CJK ici, si tentante soit-elle (Noto Sans CJK couvre tout).
#: `font_pour_texte` bascule **toute la bulle** d'un coup : un seul `・` ferait alors changer
#: de dessin un paragraphe entier de français, et court-circuiterait la substitution
#: (`_SUBSTITUTIONS`) qui est le bon traitement pour ces signes-là. Les candidats ci-dessous
#: sont des polices à large répertoire SYMBOLE mais sans kana ni kanji, exprès.
#:
#: · Windows — Lucida Sans Unicode est livrée avec le système et couvre ♪ ♫ ♥ → ♂ ♀.
#: · Linux — DejaVu (`fonts-dejavu-core`, installé par `.github/workflows/ci.yml`) est
#:   l'équivalent le plus répandu ; les deux graisses sont listées, la grasse d'abord pour
#:   rester cohérente avec le lettrage.
#: · macOS — présent pour un contributeur, PAS pour la CI : `docs/roadmap.md` classe macOS
#:   hors périmètre faute de machine pour le tester.
POLICES_SYMBOLES: dict[str, tuple[str, ...]] = {
    "win32": (
        "C:/Windows/Fonts/l_10646.ttf",       # Lucida Sans Unicode — cohérent avec le LN
        # ⚠ Ces deux-là étaient écrits « comic.ttf » et « arial.ttf », sans dossier. Or
        # les deux points d'usage filtrent par `Path(c).exists()`, résolu contre le
        # répertoire COURANT : ils n'ont donc jamais été trouvés. Le commentaire ci-dessus
        # promettait trois candidats sous Windows, il n'y en avait qu'un.
        "C:/Windows/Fonts/comic.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ),
    "linux": (
        # Debian/Ubuntu, puis Fedora, puis Arch : le même fichier, trois emplacements.
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ),
    "darwin": (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ),
}


def polices_symboles(plateforme: str | None = None) -> tuple[str, ...]:
    """Les polices système du repli sur `plateforme` (défaut : celle qui tourne)."""
    return POLICES_SYMBOLES.get(plateforme or sys.platform, ())


# Ordre de préférence complet : ce que le dépôt livre, puis ce que le système offre.
DEFAULT_FONT_CANDIDATES = [*POLICES_LIVREES, *polices_symboles()]

# Jusqu'où accepter de réduire la police pour éviter des lignes d'un seul mot. 0,72 laisse
# 2 à 4 points de marge aux tailles usuelles (28 → 20), assez pour faire entrer un second mot
# dans une bulle étroite, trop peu pour rendre le texte illisible.
_FENETRE_QUALITE = 0.72

# Nombre de positions verticales essayées quand le glissement est autorisé (le centre en plus,
# essayé le premier). 5 suffisent : sur les 199 bulles mesurées du tome, passer à 9 positions et
# au glissement libre n'ajoute que 7 bulles gagnantes et 1 px de gain médian.
_N_POSITIONS = 5

_DEFAUTS = {
    "taille_min": 11,
    # Plancher EMPRUNTABLE, et seulement quand la géométrie rend `taille_min` inatteignable —
    # c'est-à-dire quand le mot le plus long ne tient pas en largeur, quelle que soit la
    # coupure. Une bulle saine n'y touche jamais : elle a déjà trouvé sa taille bien avant.
    "taille_min_absolue": 8,
    # En dessous de cette aire intérieure, une région n'est plus une bulle : le lettrage n'y
    # peindrait que des fragments de lettres. Mesuré sur le Vol.1 — la seule région concernée
    # fait 181 px², la plus petite vraie bulle 3 055.
    "aire_min_bulle": 900,
    # Dessiné dans une bulle dont la source n'était pas vide mais dont la traduction l'est :
    # des points de suspension se lisent comme un silence, donc la planche n'est pas trahie,
    # et le trou devient repérable. `""` rétablit la bulle vierge.
    "marqueur_vide": "…",
    "taille_max": 60,
    "interligne": 1.12,
    "interligne_min": 0.95,
    "marge_interne": 0.04,
    "majuscules": False,
    "cesure_traits_union": True,
    "contour": "auto",
    "contour_epaisseur": 0.07,
    "harmonisation": True,
    "harmonisation_ratio_max": 1.25,
    "debordement": "signaler",
    "glissement_vertical": 0.5,
    # --- Lettrage d'une zone HORS BULLE (lot 22, L22.3) ------------------------------
    #
    # ⚠ Ces trois clés ne servent QUE `style_pour_zone` / `fit_zone`, c'est-à-dire un chemin
    # qu'aucun mode par défaut n'emprunte. Le lettrage des bulles ne les lit jamais.

    # Épaisseur du contour d'un lettrage hors bulle, en fraction du corps.
    # 0,125 n'est pas choisi : c'est **la valeur que le dépôt emploie déjà** pour du texte
    # posé sur du dessin — `gloss.dessiner` écrit `max(1, taille // 8)` depuis le lot 13, et
    # c'est le seul endroit du code qui ait vu de vraies planches sur ce point. La reprendre
    # évite d'inventer un second chiffre pour le même problème.
    "contour_epaisseur_sfx": 0.125,
    # Plancher d'aire d'une zone hors bulle, en px². **Désarmé (0), et c'est une mesure** :
    # `manga.onomatopees.aire_min` borne déjà la détection à 1 200 px², donc toute zone qui
    # arrive ici est au-dessus de `aire_min_bulle` (900) par construction. Un second plancher
    # ne pourrait que rejeter ; il existe pour un corpus dont la détection serait réglée plus
    # bas.
    "aire_min_sfx": 0,
    # Fait pivoter le lettrage d'une zone mesurée « verticale » (cf.
    # `clean.StyleHorsBulle.orientation`). **Désarmé**, et le dire est plus honnête que
    # l'armer : le lot 22 n'a pu lettrer AUCUNE zone réelle (taux de `lecture_sure` de 0 %),
    # donc personne n'a vu à quoi ressemble une onomatopée française inclinée sur ce corpus.
    # Armer un réglage qu'aucune image ne soutient est exactement ce que la règle de mesure
    # honnête du dépôt interdit.
    "sfx_rotation": False,
}


def _cfg(cfg: dict | None) -> dict:
    out = dict(_DEFAUTS)
    if cfg:
        out.update({k: v for k, v in cfg.items() if v is not None})
    return out


@dataclass
class Fit:
    """Une mise en page retenue pour une bulle : où écrire quoi, à quelle taille."""
    lines: list[str]
    size: int
    line_h: int
    top: int                       # y de la première ligne (ascendante incluse)
    center_x: int
    stroke: int
    overflow: bool = False
    repli: str = ""                # étape de l'échelle de replis qui a abouti
    # POURQUOI la bulle a été difficile : `bulle_degeneree` · `bulle_etroite` ·
    # `texte_trop_long`. Le rapport conseillait « raccourcir la traduction » neuf fois et
    # n'avait raison qu'une seule — les deux premières causes désignent la DÉTECTION.
    cause: str = ""
    avails: list[int] = field(default_factory=list, repr=False)
    harmonise_vers: int | None = None   # taille imposée par l'harmonisation de planche
    # Mise en page IMPOSÉE par l'utilisateur (cf. `mise_en_page.json`). L'harmonisation de
    # planche ne doit pas y toucher : elle ramène les bulles trop grandes vers la médiane, ce
    # qui est un bon réflexe automatique et une trahison quand quelqu'un a choisi une taille.
    impose: bool = False
    # ROTATION du calque, en degrés trigonométriques (lot 22, L22.3 capacité 2). `0.0` — le
    # cas de toutes les bulles — ne fait rigoureusement rien : `calque_fit` ne touche à sa
    # couche que si l'angle est non nul, et le rendu d'une bulle est donc inchangé au bit
    # près. Elle n'existe que pour le texte hors bulle, où une colonne de katakana mesurée
    # « verticale » (`clean.StyleHorsBulle.orientation`) demande un mot français incliné
    # plutôt qu'un mot français horizontal posé dans une boîte étroite.
    angle: float = 0.0


# `resolve_font` faisait un `Path.exists()` PAR BULLE et `ImageFont.truetype` était rouvert
# À CHAQUE TAILLE ESSAYÉE : ~800 ouvertures de fichier de police par tome. Les deux caches
# suppriment tout cela. La signature de `resolve_font` est inchangée.
@lru_cache(maxsize=8)
def resolve_font(font_path: str | None = None) -> str:
    candidates = ([font_path] if font_path else []) + DEFAULT_FONT_CANDIDATES
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise SystemExit(
        "Aucune police trouvée pour le lettrage manga. Renseigne "
        "config.yaml > manga.typeset.font_path, ou dépose une police (vérifie sa "
        "licence de diffusion) dans templates/fonts/manga_typeset.ttf.")


@lru_cache(maxsize=256)
def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


# Caractère de la zone à usage privé : aucune police n'en a le glyphe, son rendu EST donc
# le rendu du `.notdef` — le fameux carré « tofu ».
_TOFU = ""


def _rendu(font: ImageFont.FreeTypeFont, ch: str) -> bytes:
    im = Image.new("L", (72, 72), 0)
    ImageDraw.Draw(im).text((4, 4), ch, font=font, fill=255)
    return im.tobytes()


@lru_cache(maxsize=8192)
def a_le_glyphe(font_path: str, ch: str) -> bool:
    """La police a-t-elle un VRAI glyphe pour `ch` ?

    ⚠ On ne peut pas se fier à `font.getmask(ch).getbbox() is None` : Pillow substitue le
    glyphe `.notdef`, dont la boîte est **non vide**. Un tel test déclarait Comic Neue
    couvrante pour `♪ ♥ ★ →` alors que la page sortait avec des carrés tofu. On compare donc
    le rendu au rendu d'un caractère à coup sûr absent."""
    police = load_font(font_path, 24)
    return _rendu(police, ch) != _rendu(police, _TOFU)


def glyphes_manquants(font_path: str, texte: str) -> str:
    """Caractères de `texte` que `font_path` ne sait pas dessiner, dans l'ordre, sans
    doublon."""
    return "".join(c for c in dict.fromkeys(texte)
                   if not c.isspace() and not a_le_glyphe(font_path, c))


def font_pour_texte(texte: str, font_path: str | None = None) -> tuple[str, str]:
    """Choisit, DANS LA CHAÎNE DE REPLI, la première police qui sait dessiner tout `texte`.

    Comic Neue est un excellent dessin de lettrage mais une police *latine* : elle n'a ni
    `♪` ni `♥` ni `→`, que le traducteur produit pourtant (« Moi, je préfère les filles ♪ »).
    Sans ce repli, la planche sortait avec un carré tofu. Mesuré sur la chaîne :

        ComicNeue-Bold      manque ♪ ♫ ♥ ★ ☆ → ← ↑ ↓ ※ 〜 ♂ ♀
        Lucida Sans Unicode manque         ★ ☆ 〜          (Windows)
        arial.ttf           manque         ★ ☆ ※ 〜        (Windows)
        DejaVuSans-Bold     manque               〜        (Linux, `fonts-dejavu-core`)

    Le repli est décidé **par bulle** : la quasi-totalité garde donc Comic Neue, et seules
    celles qui contiennent un symbole exotique basculent. Renvoie
    `(chemin_retenu, encore_manquants)` — `encore_manquants` non vide signifie qu'aucune
    police de la chaîne ne couvre le texte, et doit être signalé plutôt que tu."""
    principal = resolve_font(font_path)
    manquants = glyphes_manquants(principal, texte)
    if not manquants:
        return principal, ""
    for candidat in ([font_path] if font_path else []) + DEFAULT_FONT_CANDIDATES:
        if not candidat or not Path(candidat).exists():
            continue
        if not glyphes_manquants(candidat, texte):
            return candidat, ""
    # Aucune police complète : on garde la principale (le meilleur dessin) et on signale.
    return principal, manquants


def explication_absence_symboles(plateforme: str | None = None) -> str:
    """Le message d'échec quand aucune police à symboles n'est installée.

    ⚠ Il existe pour la même raison que `tools.polices.explication_absence` : sans police de
    repli, `♪ ♥ →` ne lèvent RIEN — ils partent en « supprimé » et la planche sort amputée,
    la perte n'apparaissant que dans une ligne de rapport que personne ne relit. Le message
    nomme donc la commande, plutôt que de laisser chercher."""
    plat = plateforme or sys.platform
    essais = ("\n".join(f"    · {c}" for c in polices_symboles(plat))
              or "    · (aucun candidat connu pour cette plateforme)")
    paquet = {"linux": "sudo apt-get install -y fonts-dejavu-core",
              "win32": "Lucida Sans Unicode est livrée avec Windows",
              "darwin": "installer Arial Unicode, ou pointer une police à symboles"}
    return (
        f"Aucune police à symboles trouvée sur cette plateforme ({plat}).\n"
        f"  Candidats essayés :\n{essais}\n"
        f"  Pour installer : {paquet.get(plat, 'installer une police à large répertoire')}\n"
        f"  Ou pointer la vôtre : config.yaml > manga.typeset.font_path\n"
        f"\n"
        f"  ⚠ Sans elle, la chaîne se réduit aux polices LATINES livrées : ♪ ♫ ♥ ★ → ♂ ♀ ne "
        f"sont plus dessinés du tout, ils sont SUPPRIMÉS du texte de la bulle. La planche "
        f"part amputée d'un signe que le traducteur avait produit, sans rien de rouge nulle "
        f"part — seulement une ligne « glyphes_manquants » dans le rapport.")


#: Ce qu'une police de lettrage français doit savoir dessiner.
#:
#: Ce n'est pas une liste d'école. Chaque signe y est parce qu'il est SORTI du traducteur sur
#: un vrai tome, ou parce qu'il appartient au jeu minimal d'une édition française. Mesuré sur
#: manga A / Vol.1 après un changement de police : « ×17, œ ×16, » ×14,
#: Ç ×11, — ×8, À ×5, ♪ ×2 — soit 63 bulles sur 818, réparties sur 45 planches sur 150,
#: sorties dans une AUTRE police que celle demandée, sans une ligne de rapport.
ALPHABET_FRANCAIS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "àâäçéèêëîïôöùûüÿœæ"
    "ÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŒÆ"
    ".,;:!?…«»“”‘’'\"()[]-–—/&%$#@*+=<>~|"
)

#: Police de référence pour la mesure de LARGEUR. C'est le défaut livré du dépôt : annoncer
#: « 1,28× » ne veut rien dire sans dire 1,28 fois quoi.
POLICE_ETALON = str(_RACINE / "templates" / "fonts" / "ComicNeue-Bold.ttf")


@dataclass
class Couverture:
    """Ce qu'une police sait dessiner du français, et ce qu'elle coûte en largeur."""
    demandee: str            #: ce que `config.yaml` demande, tel quel
    existe: bool             #: le fichier existe-t-il ? ⚠ `resolve_font` AVALE le cas contraire
    retenue: str             #: ce que `resolve_font` rendra vraiment
    manquants_alphabet: str  #: signes du français courant qu'elle ne sait pas dessiner
    manquants_textes: str    #: idem, mais vus dans les traductions réellement en cache
    bulles_touchees: int     #: bulles qui basculeront sur une autre police
    bulles_vues: int
    pages_touchees: list[int]
    largeur_relative: float  #: largeur à corps égal, rapportée à `POLICE_ETALON`


def couverture(font_path: str | None,
               textes_par_page: dict[int, list[str]] | None = None) -> Couverture:
    """Mesure une police AVANT de lettrer quoi que ce soit.

    Ce contrôle existe parce que le défaut qu'il détecte est entièrement silencieux : le
    lettrage choisit sa police BULLE PAR BULLE (`font_pour_texte`), et un basculement propre
    — la chaîne a trouvé une police couvrante — ne produit aucune entrée de rapport. Le tome
    sort donc en trois polices sans qu'une ligne le dise, et cela ne se découvre qu'après dix
    minutes de rendu, en relisant `RAPPORT.md`.

    `textes_par_page` — les traductions en cache. Absentes (premier run), la mesure ne porte
    que sur `ALPHABET_FRANCAIS`, et `message_couverture` le DIT plutôt que de laisser croire
    à un contrôle complet.
    """
    demandee = font_path or ""
    existe = bool(demandee) and Path(demandee).exists()
    retenue = resolve_font(font_path)

    manquants_alphabet = glyphes_manquants(retenue, ALPHABET_FRANCAIS)
    manquants: dict[str, None] = {}
    bulles_touchees = bulles_vues = 0
    pages: list[int] = []
    for page, textes in sorted((textes_par_page or {}).items()):
        touchee = False
        for texte in textes:
            if not (texte or "").strip():
                continue
            bulles_vues += 1
            # On mesure sur le texte tel qu'il sera DESSINÉ : les substitutions latines
            # (『 → «) changent les glyphes demandés, et compter avant elles décrirait une
            # bulle qui n'existe pas.
            contenu, _police, _subs, _supp = texte_dessinable(texte, font_path)
            absents = glyphes_manquants(retenue, contenu)
            if absents:
                bulles_touchees += 1
                touchee = True
                manquants.update(dict.fromkeys(absents))
        if touchee:
            pages.append(int(page))

    try:
        etalon = load_font(resolve_font(POLICE_ETALON), 24).getlength(ALPHABET_FRANCAIS)
        largeur = load_font(retenue, 24).getlength(ALPHABET_FRANCAIS) / etalon if etalon else 1.0
    except (OSError, SystemExit):
        largeur = 1.0

    return Couverture(demandee=demandee, existe=existe, retenue=retenue,
                      manquants_alphabet=manquants_alphabet,
                      manquants_textes="".join(manquants),
                      bulles_touchees=bulles_touchees, bulles_vues=bulles_vues,
                      pages_touchees=pages, largeur_relative=largeur)


def message_couverture(c: Couverture) -> list[str]:
    """Les lignes du pré-vol. Vide quand il n'y a rien à dire.

    Suit `explication_absence_symboles` : nommer le problème, les glyphes, et la commande."""
    if c.demandee and not c.existe:
        # ⚠ Le cas le plus traître : `resolve_font` retombe EN SILENCE sur la chaîne par
        # défaut quand le fichier n'existe pas. Les polices non livrées avec le dépôt étant
        # absentes de toute autre machine, un tome entier peut sortir en Comic Neue sans
        # qu'une ligne le dise.
        return [f"[police] manga.typeset.font_path pointe un fichier ABSENT : {c.demandee}",
                f"  → le tome sortirait en {c.retenue}, sans un mot de plus."]

    lignes: list[str] = []
    absents = c.manquants_textes or c.manquants_alphabet
    if absents:
        quoi = ("des traductions en cache" if c.manquants_textes else
                "du français courant (aucune traduction en cache : la mesure ne porte que "
                "sur l'alphabet)")
        lignes.append(f"[police] {Path(c.retenue).name} ne couvre pas {len(absents)} "
                      f"signe(s) {quoi} : {' '.join(absents)}")
        if c.bulles_vues:
            lignes.append(f"  → {c.bulles_touchees} bulle(s) sur {c.bulles_vues} "
                          f"({len(c.pages_touchees)} planche(s)) seront dessinées dans une "
                          f"AUTRE police, silencieusement — le repli se décide par bulle.")
        lignes.append(f"  → pour compléter la police : "
                      f"python tools/completer_police.py {c.retenue}")
    if c.largeur_relative >= 1.15:
        # Pas un défaut, une prévision : une police large fait tomber les corps et pousse les
        # bulles étroites en débordement. Le savoir avant évite d'accuser la détection.
        lignes.append(f"[police] {Path(c.retenue).name} est {c.largeur_relative:.2f}× plus "
                      f"large que ComicNeue-Bold à corps égal : corps plus petits, et des "
                      f"bulles étroites passeront en débordement (cause `police_trop_large`).")
    return lignes


# Équivalents latins des signes que le japonais laisse passer dans la traduction. Aucune
# police de la chaîne ne les couvre — vérifié sur les trois — et le rendu était donc un carré
# tofu (`・` page 147 bulle 6 du Vol.1).
#
# ⚠ Pourquoi PAS une police CJK dans la chaîne, qui serait la réponse évidente :
# `font_pour_texte` bascule **toute la bulle** d'un coup. Un seul point médian ferait donc
# passer une bulle entière du lettrage manga à une police CJK — le remède serait bien pire.
_SUBSTITUTIONS = {
    "・": "·", "、": ",", "。": ".", "〜": "~", "～": "~", "ー": "—", "―": "—", "－": "-",
    "「": "«", "」": "»", "『": "«", "』": "»", "〈": "‹", "〉": "›", "《": "«", "》": "»",
    "【": "[", "】": "]", "〔": "[", "〕": "]", "※": "*", "♂": "♂", "♀": "♀",
}
# Formes PLEINE CHASSE : ponctuation, chiffres et latin. Générées plutôt qu'énumérées — la
# plage est contiguë par construction Unicode (U+FF01…U+FF5E ↔ U+0021…U+007E).
_SUBSTITUTIONS.update({chr(0xFF01 + i): chr(0x21 + i) for i in range(0x7E - 0x21 + 1)})
_SUBSTITUTIONS["　"] = " "                     # espace idéographique


def substituer_glyphes(texte: str, absents: str) -> tuple[str, str]:
    """Remplace, dans `texte`, les seuls caractères d'`absents` qui ont un équivalent latin.

    Renvoie `(texte, caractères effectivement substitués)`. La substitution est limitée aux
    caractères que la police ne sait PAS dessiner : un `！` reste un `！` si la police le
    couvre — on ne réécrit pas une planche que rien n'oblige à réécrire."""
    cibles = {c for c in absents if c in _SUBSTITUTIONS}
    if not cibles:
        return texte, ""
    sortie = "".join(_SUBSTITUTIONS[c] if c in cibles else c for c in texte)
    return sortie, "".join(c for c in dict.fromkeys(texte) if c in cibles)


def latiniser(texte: str) -> str:
    """Applique TOUTES les substitutions connues (pleine chasse → latin, ponctuation CJK).

    `substituer_glyphes` ne remplace que ce que la police ne couvre pas ; ici on veut la
    conversion inconditionnelle, pour rendre déterministement une zone qui ne contient QUE de
    la ponctuation (`！！` → `!!`, `．．．` → `...`). Aucun appel LLM n'a rien à y faire."""
    return "".join(_SUBSTITUTIONS.get(c, c) for c in texte)


def texte_dessinable(texte: str, font_path: str | None = None) -> tuple[str, str, str, str]:
    """Texte que la police retenue sait dessiner ENTIÈREMENT, et ce qu'il a fallu en faire.

    Renvoie `(texte, police, substitués, supprimés)`. Quatre étapes, dans cet ordre :

      1. la **chaîne de polices** (`font_pour_texte`) — une bulle qui contient `♪` bascule sur
         une police qui l'a, et rien n'est réécrit ;
      2. la **table de substitution**, sur les seuls caractères qu'aucune police ne couvre ;
      3. on **re-tente la chaîne** sur le texte normalisé : la substitution peut le ramener
         dans Comic Neue, donc dans le bon dessin, alors que le texte d'origine en sortait ;
      4. ce qui reste absent est **supprimé**.

    > Invariant, testé : `glyphes_manquants(police, texte) == ""` en sortie. **On ne dessine
    > jamais un glyphe qu'on n'a pas** — la table n'a donc pas besoin d'être exhaustive pour
    > que le tofu disparaisse."""
    police, manquants = font_pour_texte(texte, font_path)
    if not manquants:
        return texte, police, "", ""
    normalise, substitues = substituer_glyphes(texte, manquants)
    police, manquants = font_pour_texte(normalise, font_path)
    if not manquants:
        return normalise, police, substitues, ""
    supprimes = "".join(c for c in dict.fromkeys(normalise) if c in manquants)
    normalise = "".join(c for c in normalise if c not in manquants)
    police, _reste = font_pour_texte(normalise, font_path)
    return normalise, police, substitues, supprimes


def _line_height(font: ImageFont.FreeTypeFont, interligne: float, stroke: int) -> int:
    """Hauteur de ligne à partir des VRAIES métriques de la police.

    `font.getmetrics()` donne (ascendante, descendante) ; l'ancien code utilisait
    `getbbox("Ag")[3] + 4`, qui ignore la descente réelle et faisait se chevaucher les
    jambages des `g`, `p`, `q` avec la ligne suivante. Le contour s'ajoute en hauteur **et**
    en largeur : `getlength()` ne le compte pas."""
    ascendante, descendante = font.getmetrics()
    return max(1, int(round((ascendante + descendante) * interligne)) + 2 * stroke)


def _decoupe_mots(texte: str, cesure_traits_union: bool) -> list[str]:
    """Découpe en unités insécables. Une coupe est autorisée après un trait d'union
    **existant** (`sommes-nous` → `sommes-` / `nous`), jamais au milieu d'un mot : pas de
    césure algorithmique, qui imposerait un dictionnaire de coupure française."""
    mots: list[str] = []
    for brut in texte.split():
        # Trait d'union INTÉRIEUR seulement : `brut[1:-1]` écarte un tiret cadratin de
        # dialogue en tête (« -Bonjour ») et un tiret final, qui ne sont pas des césures.
        coupable = cesure_traits_union and len(brut) > 2 and "-" in brut[1:-1]
        if not coupable:
            mots.append(brut)
            continue
        morceaux = [m for m in brut.split("-") if m]
        for k, m in enumerate(morceaux):
            mots.append(m + "-" if k < len(morceaux) - 1 else m)
    return mots


def wrap_balanced(words: list[str], font: ImageFont.FreeTypeFont, avails: list[int],
                  stroke_pad: int) -> list[str] | None:
    """Habillage ÉQUILIBRÉ par programmation dynamique, sous contrainte dure de largeur.

    `avails[k]` est la largeur utilisable de la k-ième ligne (elles diffèrent : une bulle est
    plus étroite en haut et en bas). On minimise la somme des carrés du blanc résiduel,
    `dp[i][k] = min_j (dp[j][k-1] + (avail_k − largeur(j..i))²)`.

    La pénalité **quadratique** est ce qui supprime les lignes orphelines et les rivières :
    elle préfère deux lignes moyennement remplies à une pleine suivie d'un mot seul. Effet
    mesuré, page 60 bulle 1 :

        avant : « C'est bien, mais | j'aimerais que vous | modériez un peu |
                  votre attention | pour le seigneur | Kruuteo. »
        après : « C'est bien, | mais j'aimerais | que vous modériez |
                  un peu votre | attention pour | le seigneur | Kruuteo. »

    Renvoie `None` si aucun découpage ne respecte les largeurs (mot plus large que sa ligne).
    Les largeurs viennent de `font.getlength()`, qui tient compte du crénage — l'ancienne
    estimation par nombre de caractères ne le faisait pas.
    """
    n, k_max = len(words), len(avails)
    if n == 0:
        return []
    if k_max == 0:
        return None

    espace = font.getlength(" ")
    # cumul[i] = largeur des mots 0..i-1 mis bout à bout, séparés d'une espace
    cumul = [0.0]
    for m in words:
        cumul.append(cumul[-1] + font.getlength(m) + espace)

    def largeur(j: int, i: int) -> float:
        """Largeur des mots j..i-1 sur une ligne (sans l'espace finale)."""
        return cumul[i] - cumul[j] - espace

    INF = float("inf")
    # dp[k][i] : coût minimal pour placer les i premiers mots sur exactement k lignes
    dp = [[INF] * (n + 1) for _ in range(k_max + 1)]
    choix = [[-1] * (n + 1) for _ in range(k_max + 1)]
    dp[0][0] = 0.0
    for k in range(1, k_max + 1):
        dispo = avails[k - 1] - stroke_pad
        for i in range(1, n + 1):
            for j in range(i):
                if dp[k - 1][j] == INF:
                    continue
                w = largeur(j, i)
                if w > dispo:
                    continue          # contrainte DURE : jamais de ligne trop large
                reste = dispo - w
                cout = dp[k - 1][j] + reste * reste
                if cout < dp[k][i]:
                    dp[k][i] = cout
                    choix[k][i] = j
    # On veut exactement k_max lignes non vides ; si c'est impossible, échec.
    if dp[k_max][n] == INF:
        return None
    lignes: list[str] = []
    i = n
    for k in range(k_max, 0, -1):
        j = choix[k][i]
        if j < 0:
            return None
        lignes.append(" ".join(words[j:i]).replace("- ", "-"))
        i = j
    lignes.reverse()
    return lignes


def _profil(style: BubbleStyle) -> tuple[np.ndarray, int]:
    """Profil de largeur **utilisable par du texte CENTRÉ**, calculé une seule fois par
    bulle — hors de la boucle de recherche de taille, qui l'évaluait sinon à chaque essai.

    ⚠ Ce n'est pas la largeur de la plage contiguë, mais `2 × min(cx − x0, x1 − cx)`. La
    nuance est essentielle et a été trouvée au contrôle visuel de la page 60 : le texte est
    centré sur `cx` (`anchor="ma"`), or la plage contiguë n'est pas forcément centrée sur
    `cx`. Sur une bulle en éclat dont la plage s'étend de 30 px à gauche de `cx` et de 200 px
    à droite, la plage fait 230 px de large — mais un texte de 230 px centré sur `cx`
    déborderait de 85 px à gauche. Le mot « comprends » ressortait ainsi tronqué en
    « mprends ».

    Prendre la largeur SYMÉTRIQUE règle le problème à la source, plutôt que de compter sur
    le découpage de `_draw_fit` (qui reste le filet de dernier recours)."""
    largeur, x0, x1 = width_profile(style.interior, style.center_x)
    cx = style.center_x
    demi = np.minimum(cx - x0, x1 - cx)
    symetrique = np.where(largeur > 0, np.maximum(0, 2 * demi), 0).astype(np.int32)
    return symetrique, cx


def layout_at_size(text: str, largeur_profil: np.ndarray, center_x: int, size: int,
                   cfg: dict, font_path: str, *, interligne: float | None = None,
                   marge: float | None = None, glissement: float = 0.0) -> Fit | None:
    """Tente une mise en page à la taille `size`. Renvoie `None` si le texte ne tient pas.

    Le nombre de lignes est **énuméré** de 1 à `H_utile // line_h`. Cela résout d'un coup la
    circularité « le nombre de lignes dépend des largeurs, qui dépendent de la position du
    bloc, qui dépend du nombre de lignes », sans itération de point fixe.

    `glissement` autorise le bloc à **quitter le centre vertical**, d'au plus cette fraction de
    l'espace libre de part et d'autre (0 = centré, comportement d'origine bit à bit). La
    position retenue est celle qui maximise la largeur disponible la plus faible, le centre
    l'emportant à égalité.

    Pourquoi c'est utile : la largeur disponible d'une ligne est le **minimum** du profil sur
    toute sa hauteur, si bien qu'un bloc centré dans une bulle dentelée ou asymétrique peut
    tomber sur son passage le plus étroit alors que 30 px plus haut il aurait deux fois la
    place. Mesuré sur 199 bulles du tome de référence : 65 gagnent jusqu'à 14 px de corps, et
    2 débordements disparaissent."""
    c = cfg
    inter = c["interligne"] if interligne is None else interligne
    frac_marge = c["marge_interne"] if marge is None else marge

    font = load_font(font_path, size)
    stroke = _stroke_width(style_mode=c.get("_mode", "masque"), size=size, cfg=c)
    line_h = _line_height(font, inter, stroke)

    lignes_utiles = np.flatnonzero(largeur_profil > 0)
    if lignes_utiles.size == 0:
        return None
    y0, y1 = int(lignes_utiles[0]), int(lignes_utiles[-1]) + 1
    h_utile = y1 - y0
    if h_utile < line_h:
        return None

    largeur_max = int(largeur_profil.max())
    pad = max(2, int(round(frac_marge * largeur_max)))

    mots = _decoupe_mots(text, bool(c["cesure_traits_union"]))
    if not mots:
        return None

    n_max = max(1, h_utile // line_h)
    for n in range(1, int(n_max) + 1):
        bloc_h = n * line_h
        libre = h_utile - bloc_h
        centre = y0 + libre // 2
        meilleur: tuple[int, Fit] | None = None
        for top in _positions_verticales(centre, y0, libre, glissement):
            # Largeur utilisable de chaque ligne : le MINIMUM du profil sur TOUTE la hauteur
            # de la ligne. C'est ce min qui empêche le débordement dans les coins arrondis —
            # un profil pris à la seule ligne médiane laisserait dépasser les extrémités.
            avails: list[int] = []
            ok = True
            for k in range(n):
                haut = top + k * line_h
                bas = min(len(largeur_profil), haut + line_h)
                if haut < 0 or haut >= bas:
                    ok = False
                    break
                dispo = int(largeur_profil[haut:bas].min()) - 2 * pad
                if dispo <= 0:
                    ok = False
                    break
                avails.append(dispo)
            if not ok:
                continue
            lignes = wrap_balanced(mots, font, avails, stroke_pad=2 * stroke)
            if lignes is None:
                continue
            fit = Fit(lines=lignes, size=size, line_h=line_h, top=top, center_x=center_x,
                      stroke=stroke, avails=avails)
            # `>` et non `>=` : le centre est essayé en premier et garde donc l'égalité. Le
            # texte d'une bulle doit rester centré quand rien ne l'y oblige.
            if meilleur is None or min(avails) > meilleur[0]:
                meilleur = (min(avails), fit)
        if meilleur is not None:
            return meilleur[1]
    return None


def _positions_verticales(centre: int, y0: int, libre: int, glissement: float) -> list[int]:
    """Positions candidates du haut du bloc, **le centre en premier**.

    `glissement` est la fraction de l'espace libre autorisée de part et d'autre du centre.
    À 0 (défaut) la liste vaut `[centre]` : le comportement d'origine, sans un essai de plus."""
    if libre <= 0 or glissement <= 0:
        return [centre]
    amplitude = int(glissement * libre / 2)
    if amplitude <= 0:
        return [centre]
    positions = [centre]
    for k in range(_N_POSITIONS):
        top = centre + int(round(amplitude * (2 * k / (_N_POSITIONS - 1) - 1)))
        if y0 <= top <= y0 + libre and top not in positions:
            positions.append(top)
    return positions


def _orphelines(lignes: list[str]) -> int:
    """Nombre de lignes ne portant qu'**un seul mot**, sur une mise en page multi-lignes.

    C'est la signature du lettrage automatique : une colonne de mots isolés
    (« Un / rappel / dès le / premier / jour de / transfert / ?! »). Un texte d'un ou deux
    mots en tout n'est évidemment pas concerné."""
    if len(lignes) < 2:
        return 0
    mots_total = sum(len(ln.split()) for ln in lignes)
    if mots_total <= 2:
        return 0
    return sum(1 for ln in lignes if len(ln.split()) <= 1)


def _stroke_width(style_mode: str, size: int, cfg: dict) -> int:
    """Épaisseur du contour du texte.

    Trois réglages, et `contour` les nomme tous les trois (lot 22, L22.3 capacité 3) :

    · `"auto"` (défaut) — **0 en mode de nettoyage « masque »** : la bulle est uniformément
      repeinte, un contour n'apporterait rien et épaissirait le dessin des lettres. Il ne sert
      qu'en mode « texte », où le fond de bulle a survécu et où le texte doit rester lisible
      sur un fond non uni ;
    · `"toujours"` (ou tout autre valeur vraie) — contour systématique. C'est ce dont une
      onomatopée relettrée a besoin : elle est posée SUR le dessin, jamais sur un fond
      nettoyé, et sans contour elle disparaît dans les hachures ;
    · `"aucun"` / `"jamais"` / `False` — jamais de contour.

    L'épaisseur vient de `contour_epaisseur`, en fraction du corps. Elle était jusqu'ici
    dérivée du seul mode de nettoyage ; elle est désormais réglable indépendamment, ce qui est
    la seule façon d'obtenir le trait épais qu'un lettrage hors bulle demande sans épaissir
    celui des bulles."""
    reglage = cfg.get("contour", "auto")
    if reglage is False or reglage in ("aucun", "jamais"):
        return 0
    if reglage == "auto" and style_mode != "texte":
        return 0
    return max(1, int(round(cfg["contour_epaisseur"] * size)))


def _affiner_qualite(best: Fit, essai, cfg: dict) -> Fit:
    """Choisit, parmi les tailles qui tiennent, celle qui **casse le moins mal les lignes**.

    Maximiser la taille est un mauvais objectif à lui seul. Dans une bulle étroite, la plus
    grande taille qui « tient » ne laisse la place que d'**un mot par ligne** — exactement le
    défaut relevé page 20 sur « Un rappel dès le premier jour ?! », rendu en sept lignes d'un
    mot. Aucun habillage, même équilibré, ne peut le corriger : à cette taille, deux mots
    n'entrent pas. Il faut accepter de descendre d'un ou deux points.

    On explore donc vers le bas dans une fenêtre bornée (`_FENETRE_QUALITE` de la taille
    maximale, jamais moins de `taille_min`) et on retient le **minimum de lignes orphelines**,
    en préférant la plus grande taille à égalité. La fenêtre évite de dégringoler vers du
    texte minuscule : mieux vaut une orpheline qu'un lettrage illisible."""
    if _orphelines(best.lines) == 0:
        return best
    plancher = max(int(cfg["taille_min"]), int(round(best.size * _FENETRE_QUALITE)))
    meilleur, score = best, _orphelines(best.lines)
    for size in range(best.size - 1, plancher - 1, -1):
        f = essai(size)
        if f is None:
            continue
        s = _orphelines(f.lines)
        if s < score:
            meilleur, score = f, s
            if s == 0:
                break
    return meilleur


def best_fit(text: str, style: BubbleStyle, cfg: dict, font_path: str) -> Fit:
    """Plus grande taille qui tient, par **recherche dichotomique** (~6 essais au lieu des
    ~20 pas de 2 px de l'ancien balayage), avec repli sur un balayage linéaire décroissant
    si la dichotomie échoue — la propriété « ça tient » n'est pas parfaitement monotone en
    taille, l'habillage étant discret.

    Puis l'**échelle de replis** garantie anti-débordement, dans cet ordre :
      1. dichotomie sur la taille ;
      2. `interligne_min` (on serre les lignes) ;
      3. `marge_interne` réduite de moitié + césure aux traits d'union ;
      4. dessin à `taille_min` avec la meilleure mise en page trouvée, `overflow=True`, et
         **signalement** dans le rapport.
    On grignote la marge de sécurité, **jamais** le contour de la bulle."""
    c = dict(cfg)
    c["_mode"] = style.mode
    largeur_profil, center_x = _profil(style)
    lo, hi = int(c["taille_min"]), int(c["taille_max"])
    glissement = float(c.get("glissement_vertical") or 0.0)

    def essai(size: int, **kw) -> Fit | None:
        return layout_at_size(text, largeur_profil, center_x, size, c, font_path, **kw)

    def dichotomie(essayer) -> Fit | None:
        """Plus grande taille qui TIENNE, puis affinage de la qualité des coupures."""
        best: Fit | None = None
        bas, haut = lo, hi
        while bas <= haut:
            milieu = (bas + haut) // 2
            f = essayer(milieu)
            if f is not None:
                best, bas = f, milieu + 1
            else:
                haut = milieu - 1
        return None if best is None else _affiner_qualite(best, essayer, c)

    # 1. dichotomie sur la taille, **deux fois** : bloc centré, puis bloc autorisé à glisser.
    #
    # On ne remplace pas la première par la seconde, on garde la PLUS GRANDE des deux. Sans
    # cette composition, deux bulles sur 199 rétrécissaient (25 → 20 px page 48) : autoriser
    # le glissement fait monter la plus grande taille qui tienne, ce qui ouvre d'autant la
    # fenêtre de `_affiner_qualite` — laquelle peut alors descendre plus bas qu'avant en
    # chassant les lignes orphelines. Prendre le maximum rend la régression impossible par
    # construction, au prix d'une seconde dichotomie (~6 essais, le lettrage coûte ~0,3 s
    # par planche).
    best = dichotomie(essai)
    if glissement > 0:
        glisse = dichotomie(lambda size, **kw: essai(size, glissement=glissement, **kw))
        if glisse is not None and (best is None or glisse.size > best.size):
            best = glisse
    if best is not None:
        return best

    # …repli : balayage linéaire décroissant (rattrape la non-monotonie). L'échelle de replis
    # est le chemin ANTI-DÉBORDEMENT : elle glisse aussi, puisqu'à ce stade la seule
    # alternative est de dessiner à `taille_min` et de signaler.
    for size in range(hi, lo - 1, -1):
        f = essai(size, glissement=glissement)
        if f is not None:
            f.repli = "balayage"
            return f

    # 2. interligne serré
    for size in range(hi, lo - 1, -1):
        f = essai(size, interligne=c["interligne_min"], glissement=glissement)
        if f is not None:
            f.repli = "interligne_min"
            return f

    # 3. marge interne réduite
    for size in range(hi, lo - 1, -1):
        f = essai(size, interligne=c["interligne_min"], marge=c["marge_interne"] / 2,
                  glissement=glissement)
        if f is not None:
            f.repli = "marge_reduite"
            return f

    # ─── Diagnostic géométrique — POURQUOI ça ne tient pas ────────────────────────────────
    # Le rapport a conseillé « raccourcir la traduction » neuf fois sur ce tome et n'avait
    # raison qu'une seule : les huit autres bulles étaient trop étroites ou dégénérées. Un
    # conseil faux huit fois sur neuf est pire qu'aucun conseil.
    font = load_font(font_path, lo)
    stroke = _stroke_width(style.mode, lo, c)
    line_h = _line_height(font, c["interligne_min"], stroke)
    lignes_utiles = np.flatnonzero(largeur_profil > 0)
    y0 = int(lignes_utiles[0]) if lignes_utiles.size else 0
    largeur_max = max(1, int(largeur_profil.max())) if largeur_profil.size else 1
    mots = _decoupe_mots(text, True) or [text]
    dispo = max(1, largeur_max - 2 * max(2, int(round(c["marge_interne"] / 2 * largeur_max))))
    aire = int(largeur_profil.sum())
    plancher = max(1, min(int(c.get("taille_min_absolue") or lo), lo))
    aire_min = int(c.get("aire_min_bulle") or 0)
    plus_long = max(mots, key=font.getlength) if mots else ""

    # Le plancher absolu sert de juge : ce qui ne tient pas à la plus petite taille permise ne
    # tiendra JAMAIS, quelle que soit la coupure.
    font_plancher = load_font(font_path, plancher)
    line_h_plancher = _line_height(font_plancher, c["interligne_min"],
                                   _stroke_width(style.mode, plancher, c))
    # ⚠ Ces trois critères ne se valent PAS, et les confondre a coûté deux répliques.
    #
    # Les deux premiers sont GÉOMÉTRIQUES : ils décrivent la région, et aucune police ne
    # les changera. Le troisième dépend de la POLICE — il mesure un mot avec
    # `font_plancher`.
    #
    # Mesuré : au passage de ComicNeue-Bold à Wildjess (~1,3× plus large à corps égal), le
    # seul troisième critère a fait basculer page 22 bulle 2 (51×106 px, remplissage 0,874,
    # « J'aimerais bien tirer. ») et page 68 bulle 5 (« Katch ») du côté « dégénéré ». Or le
    # nettoyage a DÉJÀ effacé le japonais : la planche est sortie avec deux bulles
    # BLANCHES, et le message conseillait « corriger la détection » alors que la détection
    # n'avait pas bougé d'un pixel. `J'aimerais` à 8 px : 34 unités en Comic Neue, 45 en
    # Wildjess.
    #
    # Donc : la géométrie fait toujours renoncer, la police JAMAIS. Un texte rogné se voit
    # et se corrige ; une bulle blanche ne se voit pas.
    #
    # ⚠ Le critère de LARGEUR se dédouble, et l'oublier a mal classé la page 80 du Vol.1.
    # « Un mot ne tient pas » et « pas même un caractère ne tient » ne se corrigent pas au
    # même endroit : le premier se règle en changeant de police ou en raccourcissant, le
    # second ne se règle pas du tout. Mesuré page 80 bulle 4 : 4 px de largeur maximale,
    # donc `dispo = 1 px` pour 258 px de haut — l'aire utile (1 032 px²) passe le seuil et
    # la hauteur aussi, mais aucune police n'écrira jamais dans un couloir d'un pixel.
    # Conseiller « choisir une police moins large » y enverrait chercher un défaut qui
    # n'existe pas : c'est la détection qui a produit ce ruban.
    #
    # On mesure la plus étroite LETTRE du texte : si elle ne passe pas, rien de lisible
    # ne passera. ⚠ Pas le caractère le plus étroit tout court — le point de ComicNeue-Bold
    # mesure 1,0 px à 8 px et « tenait » donc dans le couloir d'un pixel de la page 80,
    # ce qui reclassait la région en défaut de police. Un texte sans aucune lettre
    # (« … ») retombe sur le caractère le plus étroit, faute de mieux.
    caracteres = [ch for ch in text if not ch.isspace()]
    lettres = [ch for ch in caracteres if ch.isalnum()] or caracteres or ["i"]
    aucun_glyphe = font_plancher.getlength(min(lettres, key=font_plancher.getlength)) > dispo
    trop_petite = (aire < aire_min or int(lignes_utiles.size) < line_h_plancher
                   or aucun_glyphe)
    mot_trop_large = font_plancher.getlength(plus_long) > dispo
    if trop_petite:
        # La région ne peut pas porter UN SEUL MOT, même au plus petit corps : ce n'est plus
        # une bulle. Le lettrage n'y peindrait que des fragments de lettres découpés par le
        # masque — on s'abstient, et le rapport pointe la DÉTECTION, pas le traducteur.
        # Mesuré sur le Vol.1 : 181 px² d'aire utile page 17, 12 px de haut page 146, et
        # **4 px de largeur utilisable** page 80 — celle-là même que le rapport accusait
        # d'être « trop verbeuse ».
        return Fit(lines=[], size=lo, line_h=line_h, top=y0, center_x=center_x,
                   stroke=stroke, overflow=True, repli="debordement",
                   cause="bulle_degeneree")

    # La bulle PEUT porter du texte. Reste à dire ce qui manque — la largeur ou la place :
    # c'est toute la différence entre « corriger la détection » et « raccourcir la réplique ».
    #
    # `police_trop_large` est le troisième cas : même le mot le plus long ne tient pas au
    # plancher, mais la région, elle, est saine. Ni la détection ni la traduction ne sont
    # en cause — c'est la POLICE. On le nomme pour que le conseil affiché cesse d'accuser
    # la détection (cf. `orchestrator_manga`).
    if mot_trop_large:
        cause = "police_trop_large"
    else:
        cause = ("bulle_etroite" if font.getlength(plus_long) > dispo
                 else "texte_trop_long")

    # Descendre sous `taille_min`, jusqu'au plancher absolu, plutôt que de déborder. Un
    # débordement fait DÉCOUPER les lettres par le masque ; un corps plus petit reste entier.
    # Les bulles saines n'arrivent jamais ici — elles ont trouvé leur taille à l'étape 1 — donc
    # leur lettrage est inchangé au bit près.
    for size in range(lo - 1, plancher - 1, -1):
        f = essai(size, interligne=c["interligne_min"], marge=c["marge_interne"] / 2,
                  glissement=glissement)
        if f is not None:
            f.repli, f.cause = "taille_min_absolue", cause
            return f

    # 4. dernier recours : taille_min, mise en page au mieux, DÉBORDEMENT SIGNALÉ.
    #    On ne tronque pas (perte silencieuse de contenu) et on n'agrandit pas la bulle
    #    (violation de l'invariant). Le rapport nomme la page, la bulle et la cause.
    lignes, courante = [], ""
    for m in mots:
        essai_ligne = f"{courante} {m}".strip()
        if courante and font.getlength(essai_ligne) > dispo:
            lignes.append(courante)
            courante = m
        else:
            courante = essai_ligne
    if courante:
        lignes.append(courante)
    return Fit(lines=lignes, size=lo, line_h=line_h, top=y0, center_x=center_x,
               stroke=stroke, overflow=True, repli="debordement", cause=cause)


def harmonize(fits: list[Fit | None], cfg: dict) -> None:
    """Ramène les bulles trop grandes vers la médiane de la planche. **Modifie `fits` sur
    place.**

    Plafond = médiane × `harmonisation_ratio_max`. **On n'agrandit JAMAIS** une petite
    bulle : elle est petite parce qu'elle est étroite, l'agrandir la ferait déborder.
    Mesuré page 60 : médiane 25, plafond 31 → 2 bulles redescendent, l'écart maximal passe
    de 2,4× à 1,9×. Une bulle dont le recalcul échoue est **gardée telle quelle** plutôt que
    dégradée.

    ⚠ Rendait `fits` — c'est-à-dire son propre argument, par les deux chemins de sortie. Une
    valeur de retour qui ne peut pas varier suggère un résultat là où il n'y en a pas : elle
    invitait à écrire `fits = harmonize(fits, cfg)`, comme si la liste d'origine restait
    intacte. Aucun des cinq appelants ne s'en servait ; la signature dit maintenant ce que la
    fonction fait."""
    reels = [f for f in fits if f is not None and f.lines and not f.impose]
    if not cfg["harmonisation"] or len(reels) < 2:
        return
    tailles = sorted(f.size for f in reels)
    mediane = tailles[len(tailles) // 2]
    plafond = int(mediane * cfg["harmonisation_ratio_max"])
    for f in reels:
        f.harmonise_vers = plafond if f.size > plafond else None


def typeset_bubble(image: Image.Image, region: BubbleRegion, text: str,
                   font_path: str | None = None, *, style: BubbleStyle | None = None,
                   cfg: dict | None = None, fit: Fit | None = None) -> Image.Image:
    """Dessine `text` DANS la bulle de `region`, directement sur `image` (à appeler sur une
    image déjà nettoyée par `clean.clean_bubbles`). Modifie `image` en place et la renvoie.

    Les paramètres `style` / `cfg` / `fit` sont *keyword-only* et optionnels : la signature
    publique historique `typeset_bubble(image, region, text, font_path=…)` est préservée.
    Quand `style is None`, l'intérieur est dérivé à la volée — pratique pour un test, mais
    l'orchestrateur passe toujours le style mesuré sur l'image **d'origine** (sur une page
    déjà nettoyée, la polarité serait indéductible)."""
    if not text or not text.strip():
        return image
    c = _cfg(cfg)
    if style is None:
        style = analyze_bubble(image, region)
    if not style.ok or style.mode == "aucun":
        return image        # rien n'a été nettoyé ici : n'y écrivons pas non plus

    contenu = text.upper() if c["majuscules"] else text
    contenu, resolved, _subs, _supp = texte_dessinable(contenu, font_path)
    if fit is None:
        fit = best_fit(contenu, style, c, resolved)
    _draw_fit(image, fit, style, resolved)
    return image


def _draw_fit(image: Image.Image, fit: Fit, style: BubbleStyle, font_path: str) -> None:
    """Peint les lignes, **découpées à l'intérieur de la bulle**.

    `anchor="ma"` (milieu horizontal / ascendante) supprime le `cx − lw/2` manuel de
    l'ancien code, et `fill=style.text_color` remplace le `fill=(0,0,0)` **en dur** qui
    donnait du texte noir sur les bulles inversées.

    Le découpage est l'exact miroir du `paint &= region.mask` de `clean.py`, et pour la même
    raison : l'invariant « aucun pixel hors masque n'est modifié » est le fondement de la
    brique et ne doit pas dépendre d'un raisonnement sur la mise en page. Il est
    **indispensable** dans un cas que l'échelle de replis ne peut pas résoudre : un mot
    insécable plus large que la bulle (une URL, un nom propre à rallonge, `"A" * 120`).
    Aucun habillage ne le fera tenir ; sans découpage il déborderait sur le dessin. On
    préfère une bulle illisible — et *signalée* comme telle — à une planche abîmée. Le bon
    correctif reste de raccourcir la traduction."""
    produit = calque_fit(fit, style, font_path)
    if produit is None:
        return
    calque, x0, y0 = produit
    couche = np.asarray(calque, dtype=np.float32)
    alpha = couche[:, :, 3:4] / 255.0
    y1, x1 = y0 + calque.height, x0 + calque.width
    zone = np.asarray(image.convert("RGB"), dtype=np.float32)[y0:y1, x0:x1]
    fondu = np.round(zone * (1.0 - alpha) + couche[:, :, :3] * alpha).astype(np.uint8)
    image.paste(Image.fromarray(fondu), (x0, y0))


def calque_fit(fit: Fit, style: BubbleStyle,
               font_path: str) -> tuple[Image.Image, int, int] | None:
    """Calque **RGBA** du texte d'une seule bulle, déjà découpé au masque, avec son décalage
    `(x0, y0)` dans la page. `None` si le masque est vide.

    Extrait de `_draw_fit` au lot 4.4 : c'est exactement l'artefact qu'un calque PSD demande
    (des pixels, un rectangle, une transparence), et il était construit puis aplati puis jeté.
    L'export PSD s'en sert tel quel pour son repli rasterisé — donc un calque rasterisé d'un
    PSD est **pixel pour pixel** ce que la planche aplatie contient.

    ## Deux capacités du lot 22, et toutes deux neutres par défaut

    · **Le masque de découpe est `style.decoupe` quand il existe, `style.interior` sinon.**
      Pour une bulle, `decoupe` est `None` et rien ne change au bit près. Pour une zone hors
      bulle, les deux diffèrent : `interior` dit où le texte se replie, `decoupe` où il a le
      droit d'apparaître. Sans cette dissociation, une traduction d'onomatopée serait découpée
      à l'emprise du glyphe japonais qu'elle remplace — c'est-à-dire perdue, puisqu'elle n'a ni
      sa forme ni sa taille.
    · **`fit.angle` fait pivoter le calque**, autour du centre du bloc de texte, avant le
      découpage. À `0.0` — toutes les bulles — aucune opération n'est faite. La rotation est
      un geste sur du RGBA, avant composition : elle ne touche ni l'habillage, ni la découpe,
      ni le masque.

    ⚠ L'invariant n'est pas relâché, il est **nommé** : l'alpha est toujours multiplié par un
    masque, et ce qui tombe hors du masque est toujours perdu. C'est le miroir exact du
    `paint &= region.mask` de `clean.py`, et il reste indispensable dans un cas que l'échelle
    de replis ne peut pas résoudre — un mot insécable plus large que la bulle."""
    masque = style.decoupe if style.decoupe is not None else style.interior
    ys, xs = np.nonzero(masque)
    if ys.size == 0:
        return None
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1

    # Calque transparent aux dimensions du seul masque : tout ce qui tomberait à côté est
    # écrit hors du calque, donc simplement perdu.
    calque = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    draw = ImageDraw.Draw(calque)
    font = load_font(font_path, fit.size)
    y = fit.top - y0
    for ligne in fit.lines:
        draw.text((fit.center_x - x0, y), ligne, font=font, fill=(*style.text_color, 255),
                  anchor="ma", stroke_width=fit.stroke,
                  stroke_fill=(*style.background, 255) if fit.stroke else None)
        y += fit.line_h

    if fit.angle:
        calque = _pivoter(calque, fit, x0, y0)

    # Découpage : miroir exact du `paint &= region.mask` de `clean.py`. L'invariant « aucun
    # pixel hors masque n'est modifié » ne doit pas dépendre d'un raisonnement sur la mise en
    # page — il est indispensable pour un mot insécable plus large que la bulle.
    couche = np.asarray(calque).copy()
    couche[:, :, 3] = (couche[:, :, 3].astype(np.float32)
                       * masque[y0:y1, x0:x1]).astype(np.uint8)
    return Image.fromarray(couche, mode="RGBA"), x0, y0


def _pivoter(calque: Image.Image, fit: Fit, x0: int, y0: int) -> Image.Image:
    """Fait pivoter le calque de `fit.angle` degrés autour du centre du bloc de texte.

    `expand=False` et un centre explicite, pour que le rectangle du calque — et donc le
    `(x0, y0)` que l'appelant a déjà — reste exactement le même. Ce qui sort du rectangle est
    perdu, comme tout ce qui sort du masque : c'est la même règle, appliquée au même endroit,
    et c'est à l'appelant d'avoir donné un `decoupe` assez large s'il veut de la place.

    ⚠ `BICUBIC` et non `NEAREST` : une rotation au plus proche voisin sur du texte à contour
    produit un crénelage en escalier que le contour rend deux fois plus visible."""
    cx = float(fit.center_x - x0)
    cy = float(fit.top - y0) + fit.line_h * max(1, len(fit.lines)) / 2.0
    return calque.rotate(fit.angle, resample=Image.BICUBIC, expand=False,
                         center=(cx, cy))


def preparer_contenu(texte: str, cfg: dict, font_path: str | None) -> tuple:
    """Le texte tel qu'il sera DESSINÉ, et la police qui le dessinera.

    Renvoie `(contenu, police, substitues, supprimes)`.

    Extrait de `typeset_page`, qui l'appelle désormais. Ce n'est pas un rangement : le
    relettrage en direct de l'éditeur (`gui.apercu.recomposer_bulle`) doit passer par les mêmes
    deux gestes — la casse, puis la substitution des glyphes que la police ne couvre pas — sans
    quoi ce qu'on voit en tapant divergerait de ce que le rendu écrira, sur un point
    (majuscules, guillemets, tirets cadratins) que rien à l'écran ne signalerait."""
    c = _cfg(cfg)
    contenu = texte.upper() if c["majuscules"] else texte
    return texte_dessinable(contenu, font_path)


def style_impose(style: BubbleStyle, rect) -> BubbleStyle:
    """Un `BubbleStyle` dont l'INTÉRIEUR est le rectangle donné, tout le reste inchangé.

    ⚠ C'est la pièce qui rend une mise en page déplaçable. `_profil` mesure la largeur
    utilisable sur `style.interior`, et surtout `calque_fit` **découpe** le texte à ce même
    masque : un bloc traîné hors de sa bulle disparaîtrait donc silencieusement, ce qui est le
    pire mode d'échec possible pour un éditeur. Le rectangle enregistré devient à la fois la
    zone d'habillage et le masque de découpe, et les deux ne peuvent plus diverger.

    Les couleurs, la polarité et le mode viennent toujours de la bulle d'origine : déplacer un
    texte ne change pas la façon dont il doit être encré."""
    hauteur, largeur = style.interior.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    x0, x1 = sorted((max(0, min(x0, largeur)), max(0, min(x1, largeur))))
    y0, y1 = sorted((max(0, min(y0, hauteur)), max(0, min(y1, hauteur))))
    interieur = np.zeros((hauteur, largeur), dtype=bool)
    interieur[y0:y1, x0:x1] = True
    return replace(style, interior=interieur, bbox=(x0, y0, x1, y1),
                   center_x=(x0 + x1) // 2)


def style_depuis_masque(style: BubbleStyle, masque) -> BubbleStyle:
    """Un `BubbleStyle` dont l'intérieur est le MASQUE donné — le jumeau de `style_impose`
    pour une forme quelconque plutôt qu'un rectangle.

    Sert à l'aperçu d'une zone qu'on est en train de retailler : le masque étiré est connu bien
    avant que `manga.edition` ne l'écrive, et ré-habiller dessus donne à voir le résultat exact
    pendant le geste. Les couleurs, la polarité et le mode viennent toujours de la bulle
    d'origine : changer la taille d'un ballon ne change pas la façon dont il doit être encré.

    ⚠ `center_x` est recalculé par CENTROÏDE, pas pris au milieu de la boîte. Sur un ballon à
    queue latérale, le milieu de la bbox tombe à côté du corps, et le texte — centré sur
    `center_x` par `anchor="ma"` — se retrouverait décalé puis rogné par la découpe. C'est
    exactement la raison d'être de `clean._centre_x`, qu'on réutilise ici plutôt que d'en
    refaire une version approchée."""
    from .clean import _centre_x

    interieur = np.asarray(masque, dtype=bool)
    ys, xs = np.nonzero(interieur)
    if ys.size == 0:
        return replace(style, interior=interieur, ok=False)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return replace(style, interior=interieur, bbox=bbox,
                   center_x=_centre_x(interieur, bbox), text_mask=None)


def angle_pour_zone(orientation: str, cfg: dict | None = None) -> float:
    """Angle de lettrage d'une zone hors bulle, en degrés. `0.0` tant que `sfx_rotation` est
    désarmé — c'est-à-dire toujours, par défaut.

    Une seule valeur non nulle, et c'est délibéré : `clean.StyleHorsBulle.orientation` ne rend
    pas un angle mais une classe (`verticale` / `horizontale` / `carree`), parce que c'est tout
    ce qu'un rapport de côtés peut dire. Interpoler un angle continu à partir d'un booléen
    serait inventer une précision que la mesure n'a pas."""
    c = _cfg(cfg)
    if not c.get("sfx_rotation"):
        return 0.0
    return 90.0 if orientation == "verticale" else 0.0


def style_pour_zone(style_hb, bbox, forme: tuple[int, int], *,
                    marge_decoupe: float = 0.5) -> BubbleStyle:
    """Un `BubbleStyle` pour lettrer une zone HORS BULLE, à partir de sa mesure du lot 21.

    C'est la capacité 1 de L22.3, et c'est ici qu'elle prend son sens : la zone d'habillage
    (`interior`) est la boîte de la zone source, tandis que le masque de découpe (`decoupe`)
    est cette même boîte **dilatée de `marge_decoupe`**. Les deux ne peuvent pas coïncider —
    la traduction française d'un `ゴォォォ` n'a ni sa forme ni son emprise — et `style_impose`
    ne peut pas rendre ce service : il fait du rectangle enregistré à la fois l'habillage et la
    découpe, « et les deux ne peuvent plus diverger ».

    Les couleurs viennent de la mesure : `background` est le fond local (c'est la couleur du
    CONTOUR, cf. `calque_fit`), `text_color` le pôle contrasté. `mode="texte"` n'est pas un
    détail — c'est lui qui fait rendre un contour à `_stroke_width` en réglage `"auto"`, et un
    lettrage posé sur du dessin sans contour disparaît dans les hachures.

    `style_hb` accepte un `clean.StyleHorsBulle` ou le dict persisté dans `sfx.json`, pour la
    même raison que `effacement._valeur` : les deux existent, et convertir l'un vers l'autre
    demanderait de reconstruire des champs que le cache ne porte pas."""
    from .effacement import _valeur

    h, w = forme
    x0, y0, x1, y1 = (int(v) for v in bbox)
    x0, y0 = max(0, min(x0, w)), max(0, min(y0, h))
    x1, y1 = max(0, min(x1, w)), max(0, min(y1, h))
    interieur = np.zeros((h, w), dtype=bool)
    interieur[y0:y1, x0:x1] = True

    marge_x = int(round((x1 - x0) * float(marge_decoupe)))
    marge_y = int(round((y1 - y0) * float(marge_decoupe)))
    decoupe = np.zeros((h, w), dtype=bool)
    decoupe[max(0, y0 - marge_y):min(h, y1 + marge_y),
            max(0, x0 - marge_x):min(w, x1 + marge_x)] = True

    fond = tuple(int(v) for v in _valeur(style_hb, "fond", (255, 255, 255)))
    fond_luma = float(_valeur(style_hb, "fond_luma", 255.0))
    # Le texte prend le pôle CONTRASTÉ du fond mesuré, le contour prend le fond. C'est la
    # règle de `gloss.dessiner`, et elle a été mesurée là-bas : deux pôles purs découpent un
    # halo sur une trame, le fond mesuré ne le fait pas.
    encre = (255, 255, 255) if fond_luma < 128.0 else (0, 0, 0)
    return BubbleStyle(
        bbox=(x0, y0, x1, y1), interior=interieur, background=fond,
        background_luma=fond_luma, text_color=encre,
        inverted=bool(fond_luma < 128.0), uniformity=float(
            _valeur(style_hb, "uniformite_fond", 0.0)),
        erode_radius=0, mode="texte", center_x=(x0 + x1) // 2,
        ok=bool(_valeur(style_hb, "ok", False)), decoupe=decoupe)


def fit_zone(contenu: str, style: BubbleStyle, cfg: dict, police: str, *,
             angle: float = 0.0) -> Fit:
    """`best_fit` pour une zone hors bulle : contour systématique, épaisseur propre, plancher
    d'aire propre, et rotation optionnelle.

    Les trois garde-fous de `best_fit` sont **paramétrés, pas contournés** — c'est ce que
    L22.3 demande explicitement. `aire_min_bulle` et `contour_epaisseur` sont calibrés pour des
    bulles ; les remplacer par leurs jumeaux hors bulle laisse le diagnostic géométrique
    (`bulle_degeneree`, `bulle_etroite`, `texte_trop_long`) intact et utile, alors que le
    désarmer perdrait ce que le lot 5 avait gagné — « le rapport a conseillé de raccourcir la
    traduction neuf fois et n'avait raison qu'une seule »."""
    c = dict(_cfg(cfg))
    c["contour"] = "toujours"
    c["contour_epaisseur"] = c["contour_epaisseur_sfx"]
    c["aire_min_bulle"] = c["aire_min_sfx"]
    fit = best_fit(contenu, style, c, police)
    fit.angle = float(angle)
    return fit


def fit_impose(contenu: str, style: BubbleStyle, cfg: dict, police: str,
               layout: dict) -> Fit | None:
    """Mise en page IMPOSÉE : on ne cherche pas la plus grande taille qui tient, on habille au
    corps demandé dans le rectangle demandé.

    Renvoie `None` si le texte ne tient pas — l'appelant retombe alors sur `best_fit`, parce
    qu'un rectangle devenu trop petit (texte rallongé depuis) ne doit pas faire disparaître la
    réplique. Une mise en page enregistrée est une préférence forte, pas une consigne suicide."""
    cc = dict(cfg)
    cc["_mode"] = style.mode
    if layout.get("interligne"):
        cc["interligne"] = float(layout["interligne"])
    profil, cx = _profil(style)
    taille = int(layout.get("taille") or cfg.get("taille_max", 40))
    fit = layout_at_size(contenu, profil, cx, taille, cc, police)
    if fit is None:
        return None
    fit.impose = True
    fit.repli = "mise_en_page"
    return fit


def typeset_page(image: Image.Image, regions: list[BubbleRegion], texts: list[str],
                 font_path: str | None = None, *, styles: list[BubbleStyle] | None = None,
                 cfg: dict | None = None,
                 report_out: list[dict] | None = None,
                 fits_out: list[dict] | None = None,
                 sources: list[str] | None = None,
                 layouts: dict | None = None) -> Image.Image:
    """Lettre toute une planche, avec **harmonisation des tailles** entre bulles.

    `sources` (le japonais OCR, par bulle) n'est utilisé que pour le `marqueur_vide` : une
    bulle rendue vierge est indistinguable d'un choix éditorial, mais seule celle qui AVAIT
    une source mérite un marqueur. Sans `sources`, aucune bulle n'en reçoit — une bulle sans
    japonais est vide à bon droit.

    `fits_out`, si fourni, reçoit la **recette de lettrage** de chaque bulle effectivement
    écrite : `{"index", "fit", "style", "police", "region"}`, où `fit` est le `Fit` FINAL
    (après harmonisation de planche). Même idiome que `report_out` ici et que `styles_out` dans
    `clean.py`. Tout cela était calculé puis jeté ; l'export PSD (`manga/psd.py`) en a besoin
    pour écrire un calque par bulle, et il n'y avait aucun moyen de le récupérer — `qa.json` ne
    garde qu'une taille et un *nombre* de lignes, pas les lignes, ni `top`, ni `center_x`, ni
    `line_h`, ni la police résolue, ni la couleur.

    `layouts` (`{index: {rect, taille, …}}`, cf. `checkpoints.load_mise_en_page`) impose la
    position et le corps de certaines bulles au lieu de les chercher. Une bulle absente du
    dictionnaire est lettrée exactement comme avant — c'est ce qui rend le paramètre
    strictement additif. Un rectangle devenu trop petit fait retomber sur `best_fit` plutôt
    que de perdre la réplique.

    ⚠ Fin d'une troncature silencieuse : l'ancien code faisait `zip(regions, texts)`, or
    `_parse_translations` peut renvoyer une liste **plus courte** que le nombre de bulles —
    les dernières bulles restaient alors vides sans que rien ne le signale. La longueur est
    désormais contrôlée explicitement, complétée par des chaînes vides, et l'écart est
    remonté dans `report_out`."""
    c = _cfg(cfg)
    textes = list(texts or [])
    ecart = len(regions) - len(textes)
    if ecart > 0:
        textes += [""] * ecart
    elif ecart < 0:
        textes = textes[:len(regions)]
    if report_out is not None and ecart != 0:
        report_out.append({"type": "ecart_comptage", "bulles": len(regions),
                           "traductions": len(texts or []), "ecart": ecart})

    styles = styles if styles is not None else [None] * len(regions)   # type: ignore[list-item]

    # 1re passe : calculer les mises en page, sans rien dessiner (l'harmonisation a besoin
    # de connaître toutes les tailles de la planche avant d'en fixer une seule). La police
    # est choisie PAR BULLE selon la couverture réelle du texte (cf. `font_pour_texte`).
    fits: list[Fit | None] = []
    polices: list[str] = []
    # Le texte RÉELLEMENT dessiné, après normalisation des glyphes : la 2e passe recalculait
    # sa mise en page depuis `texte` brut, ce qui aurait redessiné le tofu qu'on vient
    # d'écarter — et faisait déjà travailler la police de repli sur un texte qu'elle n'avait
    # pas servi à choisir.
    contenus: list[str] = []
    # Le style RÉELLEMENT employé par bulle. Distinct de `styles` : une mise en page imposée
    # remplace l'intérieur par son rectangle, et la 2e passe (dessin) doit voir le même — sinon
    # elle redécoupe au masque d'origine et le texte déplacé disparaît.
    styles_effectifs: list = [None] * len(regions)
    marqueur = str(c.get("marqueur_vide") or "")
    for idx, (region, texte, style) in enumerate(zip(regions, textes, styles)):
        polices.append(resolve_font(font_path))
        contenus.append("")
        if region.kind != "bulle":
            fits.append(None)
            continue
        if not texte or not texte.strip():
            # Bulle vide : marquée seulement si sa SOURCE ne l'était pas. Des points de
            # suspension se lisent comme un silence dans une bulle de manga — la planche
            # n'est pas trahie, et le trou devient repérable au lieu de passer pour un choix.
            source = sources[idx] if sources and idx < len(sources) else ""
            if not (marqueur and (source or "").strip()):
                fits.append(None)
                continue
            texte = marqueur
            if report_out is not None:
                report_out.append({"type": "bulle_vide", "index": idx, "marqueur": marqueur})
        st = style if style is not None else analyze_bubble(image, region, None)
        styles_effectifs[idx] = st
        if not st.ok or st.mode == "aucun":
            if texte.strip() and report_out is not None:
                # Le nettoyage a renoncé (uniformité sous `seuil_abandon`), donc le
                # japonais est CONSERVé et la planche n'est pas trahie — mais la
                # traduction, elle, n'est nulle part. Seule la section « Bulles NON
                # nettoyées » en portait la trace, sans dire quel texte tombait.
                report_out.append({"type": "replique_non_dessinee", "index": idx,
                                   "cause": "bulle_non_nettoyee", "texte": texte})
            fits.append(None)
            continue
        contenu, police, substitues, supprimes = preparer_contenu(texte, c, font_path)
        if (substitues or supprimes) and report_out is not None:
            report_out.append({"type": "glyphes_manquants", "index": idx,
                               "substitues": substitues, "supprimes": supprimes,
                               # Compat : l'ancien champ nommait ce qui allait être DESSINÉ en
                               # tofu. Il ne reste plus que ce qui a été retiré.
                               "caracteres": supprimes, "police": Path(police).name})
        # ⚠ SECONDE vacuité, après la suppression des glyphes. Le test de la ligne 840 voit le
        # texte tel que le modèle l'a rendu ; celui-ci voit ce qui reste une fois retirés les
        # caractères qu'aucune police de la chaîne ne couvre. Une bulle « traduite » en
        # japonais traverse le premier (elle n'est pas vide) et se vide dans `texte_dessinable`
        # — elle sortait donc blanche, SANS le marqueur qui existe précisément pour ça.
        # Avant la 0.24.0 le même cas sortait en carrés tofu : laid, mais visible et signalé.
        if not contenu.strip():
            source = sources[idx] if sources and idx < len(sources) else ""
            if not (marqueur and (source or "").strip()):
                fits.append(None)
                continue
            contenu, police = marqueur, resolve_font(font_path)
            if report_out is not None:
                report_out.append({"type": "bulle_vide", "index": idx, "marqueur": marqueur,
                                   "cause": "glyphes_supprimes"})
        polices[idx] = police
        contenus[idx] = contenu
        layout = (layouts or {}).get(idx)
        if layout and (layout.get("rect") or layout.get("taille")):
            if layout.get("rect"):
                # Le style est remplacé par celui du RECTANGLE enregistré : c'est lui qui porte
                # l'habillage ET la découpe (cf. `style_impose`), sans quoi un texte déplacé
                # hors de sa bulle serait découpé à l'ancienne bulle, donc invisible.
                st = style_impose(st, layout["rect"])
                styles_effectifs[idx] = st
            # ⚠ Sans `rect`, le style mesuré est CONSERVÉ. Fabriquer un rectangle à partir de
            # la bbox pour la seule raison qu'on veut imposer un corps remplacerait l'intérieur
            # du ballon par ses quatre coins, et le texte déborderait sur le contour dessiné.
            fit = fit_impose(contenu, st, c, police, layout)
            if fit is not None:
                fits.append(fit)
                continue
            if report_out is not None:
                report_out.append({"type": "mise_en_page_abandonnee", "index": idx,
                                   "rect": list(layout["rect"]) if layout.get("rect") else None,
                                   "taille": layout.get("taille")})
        fits.append(best_fit(contenu, st, c, police))

    harmonize(fits, c)

    # 2e passe : recalculer au plafond les bulles trop grandes, puis dessiner.
    for idx, (region, texte, style) in enumerate(zip(regions, textes, styles)):
        fit = fits[idx]
        if fit is None:
            continue
        st = styles_effectifs[idx]
        if st is None:
            st = style if style is not None else analyze_bubble(image, region, None)
        police = polices[idx]
        plafond = fit.harmonise_vers
        if plafond:
            cc = dict(c)
            cc["_mode"] = st.mode
            profil, cx = _profil(st)
            recalc = layout_at_size(contenus[idx], profil, cx, int(plafond), cc, police)
            if recalc is not None:      # échec → on garde la mise en page d'origine
                recalc.cause = fit.cause
                fit = recalc
                fits[idx] = fit
        _draw_fit(image, fit, st, police)
        if not fit.lines and contenus[idx].strip() and report_out is not None:
            # `_draw_fit` sur un `Fit` sans ligne ne peint RIEN : le calque reste
            # transparent. Or le nettoyage a déjà effacé la source, donc la bulle sort
            # BLANCHE et la réplique est perdue. Jusqu'ici elle n'était rapportée que
            # comme une bulle ordinaire en débordement, sans son texte : impossible de
            # savoir CE QUI avait disparu sans rouvrir le checkpoint.
            report_out.append({"type": "replique_non_dessinee", "index": idx,
                               "cause": fit.cause or "bulle_degeneree",
                               "texte": contenus[idx]})
        if report_out is not None:
            report_out.append({
                "type": "bulle", "index": idx, "taille": fit.size,
                "lignes": len(fit.lines), "overflow": bool(fit.overflow),
                "repli": fit.repli, "cause": fit.cause, "mode_nettoyage": st.mode})
        if fits_out is not None:
            fits_out.append({"index": idx, "fit": fit, "style": st, "police": police,
                             "region": region})
    return image
