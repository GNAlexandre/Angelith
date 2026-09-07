# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Effacer le texte HORS BULLE, sans aucun modèle génératif — lot 22, L22.1.

## Ce que ce module est, et ce qu'il n'est pas

Il **n'est pas** une renégociation du principe directeur. « L'IA ne dessine jamais »
(README §12) reste écrit en cinq mots, et le lot 22 l'a tranché par écrit avant d'écrire une
ligne de code : le modèle génératif est **refusé**, pour trois raisons mesurées et dans cet
ordre — le garde-fou de lecture le rend inutile aujourd'hui (cf. plus bas), le matériel ne le
porte pas (20 milliards de paramètres à côté d'un traducteur de 27), et la licence des poids
`big-lama` n'a pas pu être établie sur une source primaire.

Ce qu'il ajoute est **déterministe**, et c'est exactement le mode `"texte"` de `clean.py`
transposé hors de la bulle : remplir un masque d'encre dilaté avec la couleur de fond
**mesurée** par `clean.analyser_zone_hors_bulle` (lot 21, L21.2). Aucun modèle, aucune
dépendance neuve, et **pas d'OpenCV** — `requirements-manga.txt` le refuse (~60 Mo pour trois
opérations de morphologie), et `manga/geometry.py` fait déjà son érosion et sa dilatation en
numpy pur. `cv2.inpaint` n'est donc pas à portée d'import ; sa version naïve, elle, s'écrit en
une vingtaine de lignes (cf. `diffuser`).

## Le seuil qui décide, et celui que la mesure a fait sauter

L'échelle est celle de `clean_bubbles`, déjà calibrée sur 797 bulles, transposée au **fond
local** d'une zone hors bulle — c'est-à-dire à l'anneau autour de sa boîte, jamais à son
intérieur (l'encre de l'onomatopée y est, et elle ferait chuter l'uniformité de toute zone,
y compris posée sur un aplat de ciel).

| uniformité du fond local | ce qui est fait | part du corpus |
|---|---|--:|
| ≥ 0,35 | reconstruction par **diffusion** (`diffuser`) | **89,4 %** |
| < 0,35 | **rien n'est peint**, et le rapport le dit | 10,6 % |

Parts mesurées par `tools/banc_sfx.py --tous` sur 2 455 zones de six tomes
(`docs/mesures/sfx-2026-08-28.md`). Le seuil d'abandon est le même que celui qui a sauvé la page 44 du
Vol.1 : un gratte-ciel aux fenêtres sombres pris pour une bulle, uniformité 0,131, que le mode
« texte » repeignait entièrement en noir. En dessous, la zone garde son texte source — visible,
donc corrigible à la main — au lieu de coûter un morceau de planche.

⚠ **Le plan de lot en prévoyait un troisième, et la mesure l'a fait sauter.** Il posait qu'au
dessus de 0,60 d'uniformité « un remplissage de couleur unique serait correct », la diffusion
n'étant qu'un repli pour la bande du milieu. `tools/banc_effacement.py` dit le contraire :
**sur ce palier-là aussi**, le remplissage plat laisse une couture 2,4 fois plus franche que le
grain naturel du fond, là où la diffusion tombe à 0,84 — et le résidu ne les départage pas. Le
seuil de 0,60 existe toujours (`methode: "auto"`) mais il n'est plus le défaut, et c'est écrit
ici plutôt que corrigé en silence.

## Le garde-fou qui rend ce module défendable, et qu'aucune clé ne désarme

**Une zone dont la lecture n'est pas concordante n'est JAMAIS effacée.** C'est le critère 10
du plan de lot, et c'est le plus important de sa liste : effacer une onomatopée sur une
lecture douteuse produit exactement le défaut que la brique passe son temps à éviter — une
erreur *dessinée* à la place d'une erreur *signalée*. La règle est dans le code, pas dans la
configuration : `manga/sfx_lecture.py` rend `LECTURE_SURE` quand deux voies indépendantes
s'accordent, et rien d'autre n'ouvre la porte.

⚠ **Conséquence, dite plutôt que découverte : sur le corpus d'aujourd'hui, ce module efface
zéro zone.** Le taux de `lecture_sure` mesuré sur les six tomes est de **0 %**, faute de
seconde voie (`manga.onomatopees.concordance` exige un serveur LLM vision, injoignable sur la
machine du lot 21). Le chemin est complet, testé, et sans effet tant que cette condition n'est
pas remplie. C'est un résultat, pas un manque.

## L'invariant, et il est du même genre que celui de `clean.py`

Une **seule** écriture par zone, `out[peindre] = valeurs`, précédée de
`peindre &= boite & encre_dilatee`. Autrement dit :

  · aucun pixel hors de la boîte de la zone n'est modifié — jamais, quelle que soit la
    dilatation ;
  · aucun pixel qui n'est pas de l'encre (au sens du contraste au fond local) n'est modifié ;
  · l'image d'entrée n'est **jamais** mutée : ce module rend un **calque**, et c'est
    l'appelant qui décide de le composer ou de le laisser dans le PSD.

Ce dernier point est la voie 1 de L22.6, et c'est elle qui évite de faire entrer `sfx` dans le
graphe d'invalidation : l'effacement est un étage **nouveau**, après `nettoyage`, qui ne
modifie pas `nettoyage`. `sfx` reste dans `checkpoints.CACHE_NON_BLOQUANT`, aucun rendu
existant n'est périmé, et le calque PSD séparé en découle naturellement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from ._config import fusion
from .geometry import adaptive_radius, dilate
from .sfx_lecture import LECTURE_SURE

#: Motifs de décision, alignés sur le vocabulaire du rapport. Valeurs AFFICHÉES dans
#: `RAPPORT.md` : les renommer changerait un rapport déjà écrit pour un gain cosmétique.
MOTIF_UNIFORME = "uniforme"              # peint : remplissage de la couleur mesurée
MOTIF_DIFFUSION = "diffusion"            # peint : diffusion depuis le bord du trou
MOTIF_LECTURE_DOUTEUSE = "lecture_douteuse"
MOTIF_FOND_NON_UNIFORME = "fond_non_uniforme"
MOTIF_MESURE_ABSENTE = "mesure_absente"
MOTIF_SANS_ENCRE = "sans_encre"

#: Ceux qui correspondent à des pixels réellement écrits.
MOTIFS_PEINTS = (MOTIF_UNIFORME, MOTIF_DIFFUSION)

LIBELLES = {
    MOTIF_UNIFORME: "remplissage de la couleur de fond mesurée",
    MOTIF_DIFFUSION: "reconstruit par diffusion depuis le bord du trou",
    MOTIF_LECTURE_DOUTEUSE: "lecture non concordante — jamais effacée",
    MOTIF_FOND_NON_UNIFORME: "fond trop structuré — rien n'est peint",
    MOTIF_MESURE_ABSENTE: "style non mesuré — rien n'est peint",
    MOTIF_SANS_ENCRE: "aucune encre détectée dans la boîte",
}

_DEFAUTS = {
    # "aucun" (DÉFAUT) : rien n'est calculé, comportement d'avant le lot au bit près.
    # "calque" : l'effacement est calculé et exporté en calque PSD masquable, mais la planche
    #            aplatie de `pages_out/` n'est PAS touchée.
    # "aplati" : le calque est en plus composé sur la planche finale.
    "mode": "aucun",
    # "diffusion" (DÉFAUT) : toujours diffuser, quel que soit le palier.
    # "uniforme"  : toujours remplir de la couleur mesurée.
    # "auto"      : le schéma à deux bandes du plan de lot — remplissage au-dessus de
    #               `seuil_uniformite`, diffusion en dessous.
    #
    # ⚠ **Le défaut contredit une prémisse du plan de lot, et c'est une mesure.** Le plan
    # posait qu'au-dessus de 0,60 d'uniformité « un remplissage de couleur unique serait
    # correct », et n'envisageait la diffusion que pour la bande du milieu. Mesuré sur les
    # 217 zones du *manga B* Chap.5 (`tools/banc_effacement.py`), la couture rapportée au
    # grain du fond intact — 1,0 = se raccorde comme le fond se raccorde à lui-même :
    #
    #     tout uniforme   couture/grain 2,78   · sur le palier ≥ 0,60 seul : 2,43
    #     tout diffusion  couture/grain 0,89   · sur le palier ≥ 0,60 seul : 0,84
    #
    # Le remplissage plat laisse une arête deux fois et demie plus franche que celle que le
    # dessin porte naturellement, y compris là où le fond est réputé uni : ce qu'il ne
    # reconstruit pas, c'est le halo d'anti-crénelage que la dilatation n'a pas mangé. Le
    # résidu, lui, ne les départage pas (0,108 contre 0,124). La diffusion est donc le défaut,
    # et `"uniforme"` reste disponible — il est plus rapide, et un corpus au fond parfaitement
    # plat n'a rien à gagner à 32 passes de numpy.
    "methode": "diffusion",
    # Ne sert qu'en `methode: "auto"`. Les deux seuils de `clean_bubbles`, transposés au fond
    # LOCAL. Repris tels quels et non recalibrés : ils sont calibrés sur des bulles, et un
    # seuil propre au hors-bulle ne peut s'établir qu'en voyant des effacements casser.
    "seuil_uniformite": 0.60,
    # Celui-ci s'applique TOUJOURS : c'est le palier du gratte-ciel de la page 44, en dessous
    # duquel rien n'est peint.
    "seuil_abandon": 0.35,
    # Écart de luminance au fond local au-delà duquel un pixel de la boîte est de l'encre.
    # Même valeur que `clean._DEFAUTS_HORS_BULLE["seuil_texte"]`, et pour la même raison :
    # c'est le même contraste, mesuré contre le même fond.
    "seuil_encre": 45,
    # Dilatation du masque d'encre, en multiple du rayon adaptatif de la boîte. L'anti-
    # crénelage d'un glyphe déborde de son encre franche ; ne pas le manger laisse un halo
    # gris à la forme exacte du caractère effacé, ce qui est pire qu'un caractère.
    #
    # ⚠ **Balayé, et le balayage ne désigne aucun optimum.** Sur les 217 zones du *manga B*
    # Chap.5 (`tools/banc_effacement.py --dilatation …`) :
    #
    #     dilatation      0,6    1,0    1,6    2,4    3,2
    #     empreinte     0,402  0,476  0,557  0,653  0,710   ← ce qu'on repeint du dessin
    #     résidu        0,122  0,111  0,099  0,082  0,070   ← ce qu'il reste du glyphe
    #     couture/grain  1,65   1,94   1,83   1,94   1,99   ← plat, ne départage rien
    #
    # Les deux premières lignes sont monotones et opposées, la troisième est plate : aucun
    # coude, donc aucune valeur que la mesure désigne. 1,0 est retenu parce qu'à départage nul
    # on prend celui qui **touche le moins au dessin** — la règle qui a déjà décidé du mode
    # « aucun » de `clean_bubbles`. Ce qui trancherait vraiment est un contrôle visuel sur des
    # effacements réels, et il demande d'abord une seconde voie de lecture.
    "dilatation": 1.0,
    # Passes de la diffusion. Chaque passe propage la valeur des bords d'un pixel vers
    # l'intérieur du trou : il en faut au moins la demi-épaisseur du trait le plus épais.
    # 32 couvre un trait de 64 px, c'est-à-dire une onomatopée pleine page.
    "passes_diffusion": 32,
    # Anneau LU autour de la boîte pour donner ses conditions au bord à la diffusion. Jamais
    # écrit — c'est la même dissymétrie que `clean.analyser_zone_hors_bulle`, qui mesure le
    # fond sur un anneau hors de la boîte.
    #
    # ⚠ Il n'est pas décoratif, et le mesurer l'a montré. Sur une bande de 90×30 px dont
    # l'encre dilatée occupe presque toute la boîte, une diffusion bornée à la boîte n'a plus
    # aucun pixel connu d'où partir : elle rend l'amorce, c'est-à-dire exactement le
    # remplissage uniforme (erreur moyenne au dégradé de référence : 17,4 contre 19,4 —
    # autant dire rien). Avec 24 px d'anneau, la même diffusion tombe à 1,7.
    "marge_diffusion": 24,
}


@dataclass
class Decision:
    """Ce qui a été décidé pour UNE zone, et pourquoi. Aligné par position sur `regions`."""

    index: int
    motif: str
    uniformite: float = 0.0
    pixels: int = 0

    @property
    def peint(self) -> bool:
        return self.motif in MOTIFS_PEINTS


@dataclass
class Effacement:
    """Le calque produit, et le journal de ce qui a été décidé.

    `rgba` est `None` quand rien n'a été peint — le cas nominal aujourd'hui, cf. l'en-tête du
    module. Sinon c'est un tableau `(h, w, 4)` en uint8, **rogné** à l'emprise réellement
    peinte, avec `(x, y)` son coin supérieur gauche dans la page : exactement ce que
    `psd.Calque` attend, et ce qui évite un calque pleine page de 7 Mo pour trois glyphes."""

    rgba: np.ndarray | None = None
    x: int = 0
    y: int = 0
    decisions: list[Decision] = field(default_factory=list)

    @property
    def pixels(self) -> int:
        return sum(d.pixels for d in self.decisions)

    @property
    def zones_effacees(self) -> int:
        return sum(1 for d in self.decisions if d.peint)

    def motifs(self) -> dict[str, int]:
        """Compte par motif, pour `RAPPORT.md`. Un filtre muet est la façon dont on perd les
        zones suivantes sans le voir — c'est l'acquis de L21.1, et il vaut ici aussi."""
        out: dict[str, int] = {}
        for d in self.decisions:
            out[d.motif] = out.get(d.motif, 0) + 1
        return out


def _valeur(style, cle: str, defaut):
    """Lit un champ de style, qu'il vienne d'un `clean.StyleHorsBulle` ou du dict persisté.

    Les deux existent et aucun n'est de trop : l'orchestrateur relit `sfx.json`, qui porte des
    dictionnaires, tandis qu'un test ou l'éditeur ont l'objet sous la main. Convertir l'un vers
    l'autre demanderait de reconstruire des champs que le cache ne persiste pas (`aire`,
    `pourtour_pixels`) et dont ce module n'a que faire."""
    if style is None:
        return defaut
    if isinstance(style, dict):
        v = style.get(cle, defaut)
    else:
        v = getattr(style, cle, defaut)
    return defaut if v is None else v


def _luma(px: np.ndarray) -> np.ndarray:
    """Luminance Rec. 601, la même que `clean._luma`. Recopiée plutôt qu'importée d'un
    module privé ? Non : importée, justement, pour qu'un changement de coefficients ne puisse
    pas faire diverger la mesure du lot 21 et l'effacement qui en dépend."""
    from .clean import _luma as luma_clean
    return luma_clean(px)


def masque_encre(arr: np.ndarray, bbox: tuple[int, int, int, int], fond_luma: float, *,
                 masque_zone: np.ndarray | None = None, seuil: float = 45.0,
                 dilatation: float = 1.6) -> np.ndarray:
    """Masque booléen, **à la taille de la page**, des pixels à reconstruire.

    Trois gestes, dans cet ordre :

    1. l'encre est ce qui, DANS la boîte, s'écarte du fond local de plus de `seuil` — la même
       définition que `clean.analyser_zone_hors_bulle`, et le même seuil ;
    2. intersection au masque du détecteur quand il existe. C'est une carte de probabilité de
       texte et non un tracé d'encre : elle borne, elle ne décide pas ;
    3. dilatation du rayon adaptatif de la boîte, pour manger l'anti-crénelage.

    ⚠ Le résultat est **ré-intersecté à la boîte** après dilatation. La dilatation déborde par
    construction, et un débordement ici écrirait sur du dessin que rien n'a mesuré. C'est le
    même filet explicite que le `paint &= region.mask` de `clean.py`, gardé pour la même
    raison : l'invariant ne doit pas dépendre d'un raisonnement."""
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = _boite_saine(bbox, w, h)
    encre = np.zeros((h, w), dtype=bool)
    if x1 <= x0 or y1 <= y0:
        return encre
    boite = arr[y0:y1, x0:x1]
    ecart = np.abs(_luma(boite.astype(np.float64)) - float(fond_luma))
    local = ecart > float(seuil)
    if masque_zone is not None and getattr(masque_zone, "shape", None) == (h, w):
        sous = masque_zone[y0:y1, x0:x1]
        if sous.any():
            local = local & sous
    encre[y0:y1, x0:x1] = local
    rayon = max(1, int(round(float(dilatation)
                             * adaptive_radius(x1 - x0, y1 - y0, frac=0.03))))
    encre = dilate(encre, rayon)
    # Filet explicite : la dilatation vient de déborder de la boîte, et c'est normal.
    dedans = np.zeros((h, w), dtype=bool)
    dedans[y0:y1, x0:x1] = True
    return encre & dedans


def _boite_saine(bbox, w: int, h: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = (int(v) for v in bbox)
    x0, y0 = max(0, min(x0, w)), max(0, min(y0, h))
    x1, y1 = max(0, min(x1, w)), max(0, min(y1, h))
    return x0, y0, x1, y1


def diffuser(valeurs: np.ndarray, trou: np.ndarray, *, passes: int = 32,
             amorce: tuple[int, int, int] | None = None) -> np.ndarray:
    """Remplit `trou` par **diffusion** des valeurs de bord. numpy pur, aucune dépendance.

    C'est `cv2.inpaint` en version naïve — une itération de Jacobi sur l'équation de Laplace,
    conditions de Dirichlet aux pixels connus : à chaque passe, un pixel du trou prend la
    moyenne de ses quatre voisins. Le résultat est la surface la plus lisse qui raccorde les
    bords du trou, ce qui est exactement ce qu'on veut d'un dégradé ou d'une trame régulière,
    et exactement ce qu'on ne veut PAS d'une structure — d'où le seuil d'abandon, qui écarte
    ce cas avant d'arriver ici.

    L'amorce (la couleur de fond mesurée) n'est pas un raffinement : elle décide de ce que rend
    une diffusion tronquée. Sans elle, un trait de 60 px de large garderait en son centre la
    valeur noire de l'encre après 32 passes ; avec elle, il garde la couleur du papier. Une
    diffusion qui n'a pas convergé rend donc le fond mesuré, pas l'encre — le mauvais cas
    ressemble au palier du dessus, pas au palier d'en dessous.

    ⚠ Ne modifie pas `valeurs`. Rend un tableau neuf, en float32."""
    out = np.asarray(valeurs, dtype=np.float32).copy()
    trou = np.asarray(trou, dtype=bool)
    if not trou.any():
        return out
    if amorce is not None:
        out[trou] = np.asarray(amorce, dtype=np.float32)
    connu = ~trou
    for _ in range(max(1, int(passes))):
        # Somme des quatre voisins, avec réplication de bord : un pixel du trou collé au bord
        # de la fenêtre doit voir un voisin, pas un zéro qui l'assombrirait.
        haut = np.roll(out, 1, axis=0)
        haut[0] = out[0]
        bas = np.roll(out, -1, axis=0)
        bas[-1] = out[-1]
        gauche = np.roll(out, 1, axis=1)
        gauche[:, 0] = out[:, 0]
        droite = np.roll(out, -1, axis=1)
        droite[:, -1] = out[:, -1]
        moyenne = (haut + bas + gauche + droite) * 0.25
        out = np.where(trou[..., None] if out.ndim == 3 else trou, moyenne, out)
    # Les pixels connus n'ont jamais bougé — `np.where` les a repris à chaque passe — mais
    # l'écrire explicitement rend l'invariant indépendant du raisonnement ci-dessus.
    out[connu] = np.asarray(valeurs, dtype=np.float32)[connu]
    return out


def decider(style, verdict: str, cfg: dict | None = None) -> tuple[str, float]:
    """`(motif, uniformité)` pour une zone, **sans regarder un seul pixel**.

    Séparée du calcul parce qu'elle est ce qu'un banc, un rapport et un test veulent lire : la
    décision, pas les pixels. L'ordre des tests est celui du risque décroissant — la lecture
    d'abord, parce qu'une lecture douteuse interdit tout le reste."""
    c = fusion(_DEFAUTS, cfg)
    if verdict != LECTURE_SURE:
        # ⚠ Critère 10 du plan de lot, et aucune clé ne le désarme. Une erreur DESSINÉE à la
        # place d'une erreur SIGNALÉE est exactement le défaut que la brique évite partout
        # ailleurs.
        return MOTIF_LECTURE_DOUTEUSE, float(_valeur(style, "uniformite_fond", 0.0))
    if not bool(_valeur(style, "ok", False)):
        return MOTIF_MESURE_ABSENTE, float(_valeur(style, "uniformite_fond", 0.0))
    u = float(_valeur(style, "uniformite_fond", 0.0))
    if u < float(c["seuil_abandon"]):
        # Le seuil d'abandon s'applique quelle que soit la méthode : sous 0,35, le fond n'est
        # plus un fond, c'est du dessin. Aucune reconstruction déterministe ne le rend.
        return MOTIF_FOND_NON_UNIFORME, u
    methode = str(c["methode"]).lower()
    if methode == "uniforme":
        return MOTIF_UNIFORME, u
    if methode == "auto":
        return (MOTIF_UNIFORME if u >= float(c["seuil_uniformite"])
                else MOTIF_DIFFUSION), u
    return MOTIF_DIFFUSION, u


def effacer_zones(image: Image.Image, regions: list, styles: list | None = None,
                  verdicts: list[str] | None = None,
                  cfg: dict | None = None) -> Effacement:
    """Calcule le calque d'effacement d'une planche. **Ne mute jamais `image`.**

    `styles` porte un `clean.StyleHorsBulle` ou le dict persisté dans `sfx.json`, aligné par
    position sur `regions` ; `verdicts` porte `sfx_lecture.LECTURE_SURE` / `LECTURE_DOUTEUSE`,
    aligné de même. Un `verdicts` absent vaut « toutes douteuses » — c'est l'état réel du dépôt
    quand la seconde voie de lecture n'a pas tourné, et le prendre pour un feu vert
    baptiserait le problème.

    Le calque est rogné à l'emprise réellement peinte : une planche dont deux glyphes sont
    effacés ne porte pas un calque pleine page."""
    c = fusion(_DEFAUTS, cfg)
    arr = np.asarray(image.convert("RGB"))
    h, w = arr.shape[:2]
    peint = np.zeros((h, w), dtype=bool)
    sortie = arr.copy()
    decisions: list[Decision] = []

    for i, region in enumerate(regions or []):
        style = styles[i] if styles and i < len(styles) else None
        verdict = verdicts[i] if verdicts and i < len(verdicts) else ""
        motif, uniformite = decider(style, verdict, c)
        if motif not in MOTIFS_PEINTS:
            decisions.append(Decision(index=i, motif=motif, uniformite=uniformite))
            continue

        bbox = _boite_saine(getattr(region, "bbox", (0, 0, 0, 0)), w, h)
        fond = tuple(int(v) for v in _valeur(style, "fond", (255, 255, 255)))
        fond_luma = float(_valeur(style, "fond_luma",
                                  float(_luma(np.array(fond, dtype=float)))))
        encre = masque_encre(arr, bbox, fond_luma,
                             masque_zone=getattr(region, "mask", None),
                             seuil=float(c["seuil_encre"]),
                             dilatation=float(c["dilatation"]))
        # ⚠ Filet, redondant avec `masque_encre` qui ré-intersecte déjà à la boîte. Gardé pour
        # la raison écrite dans `clean.clean_bubbles` : l'invariant « rien hors de la boîte
        # n'est modifié » ne doit pas dépendre d'un raisonnement sur une autre fonction.
        dedans = np.zeros((h, w), dtype=bool)
        dedans[bbox[1]:bbox[3], bbox[0]:bbox[2]] = True
        encre = encre & dedans
        n = int(encre.sum())
        if n == 0:
            decisions.append(Decision(index=i, motif=MOTIF_SANS_ENCRE,
                                      uniformite=uniformite))
            continue

        if motif == MOTIF_UNIFORME:
            sortie[encre] = fond
        else:
            # ⚠ La fenêtre de diffusion est la boîte ÉLARGIE. L'anneau ajouté n'est que LU :
            # il porte les conditions au bord sans lesquelles la diffusion n'a rien d'où
            # partir (cf. `marge_diffusion`). Les pixels écrits restent ceux de `encre`, qui
            # est déjà borné à la boîte.
            marge = max(0, int(c["marge_diffusion"]))
            fx0, fy0, fx1, fy1 = _boite_saine(
                (bbox[0] - marge, bbox[1] - marge, bbox[2] + marge, bbox[3] + marge), w, h)
            fenetre = arr[fy0:fy1, fx0:fx1]
            trou = encre[fy0:fy1, fx0:fx1]
            rempli = diffuser(fenetre, trou, passes=int(c["passes_diffusion"]),
                              amorce=fond)
            bloc = sortie[fy0:fy1, fx0:fx1]
            bloc[trou] = np.clip(np.round(rempli[trou]), 0, 255).astype(np.uint8)
            sortie[fy0:fy1, fx0:fx1] = bloc
        peint |= encre
        decisions.append(Decision(index=i, motif=motif, uniformite=uniformite, pixels=n))

    if not peint.any():
        return Effacement(rgba=None, decisions=decisions)

    ys, xs = np.nonzero(peint)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    rgba = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
    rgba[:, :, :3] = sortie[y0:y1, x0:x1]
    rgba[:, :, 3] = np.where(peint[y0:y1, x0:x1], 255, 0).astype(np.uint8)
    return Effacement(rgba=rgba, x=x0, y=y0, decisions=decisions)


def composer(image: Image.Image, effacement: Effacement) -> Image.Image:
    """Applique le calque sur une COPIE de `image`. Rend l'image inchangée si rien n'est peint.

    C'est la seule fonction du module qui écrit sur une planche, et elle est appelée par le
    seul chemin `mode: "aplati"`. En `"calque"`, l'effacement existe dans le PSD et **la
    planche aplatie n'est pas touchée** — c'est ce qui rend le lot réversible en masquant un
    calque, sans relancer quoi que ce soit."""
    if effacement is None or effacement.rgba is None:
        return image
    out = image.convert("RGB").copy()
    calque = Image.fromarray(effacement.rgba, mode="RGBA")
    out.paste(calque, (effacement.x, effacement.y), calque)
    return out
