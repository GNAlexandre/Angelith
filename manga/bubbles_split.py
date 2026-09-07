# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Scission des régions **bi-lobées** : deux ballons que le détecteur a pris pour un.

## Le défaut

Le modèle de détection (`yolov8m_seg-speech-bubble`) émet parfois **une** instance là où le
dessinateur a mis **deux** ballons qui se touchent : 5 régions pour 6 ballons page 136, 8 pour
9 page 142 du *manga A* Vol.1. Tout le reste de la chaîne se comporte alors
correctement, ce qui rend le défaut invisible :

  · `ocr.read_all` lit **une** chaîne pour la région, donc les deux répliques collées —
    page 136 : `敵機２時方向！いいよ転校生！！`, deux locuteurs différents ;
  · le traducteur reçoit une bulle, rend une réplique — « Avion ennemi à deux heures !
    Allez, nouvelle élève !! » ;
  · le lettreur compose ce bloc dans la géométrie fusionnée. `clean._centre_x` place l'axe du
    texte au centroïde de l'ENSEMBLE du masque, donc dans le vide entre les lobes ; le profil
    de largeur symétrique de `typeset._profil` ne garde alors de la place qu'au **goulot** ;
    et `layout_at_size` centre le bloc verticalement sur toute l'étendue utile, ce qui le pose
    précisément dessus. Résultat mesuré : 13 px dans une boîte de 360×595 px, quand les autres
    bulles de la planche sont à 17-31 px.

Aucun compteur ne s'en apercevait : autant de traductions que de bulles, donc pas d'écart de
comptage ; le texte tenait, donc pas de débordement. `RAPPORT.md` déclarait la planche propre.
Les deux métriques qui l'auraient attrapé — remplissage du masque et dérive du centroïde —
n'étaient calculées nulle part.

## Où la scission a lieu

**Avant `reading_order`, donc avant l'OCR** : l'ordre de lecture doit voir les vraies bulles, et
chaque ballon doit recevoir son propre texte. C'est un post-traitement de MASQUES, sans réseau
de neurones : il s'applique donc aussi aux masques déjà en cache, ce qui permet de migrer un
tome sans le modèle ONNX (cf. `checkpoints.migrate_page`).

## Ce que le lot 13 y ajoute

Le réglage livré jusqu'ici laissait **33 régions bi-lobées suspectes non scindées** sur les
cinq volumes du corpus (9 sur manga A Vol.1, 7 sur le Vol.2, 7 sur manga B Chap.5, 9 sur
manga D Vol.15, 1 sur webtoon A Chap.11). Elles sont **nommées, avec leur
remplissage**, dans chaque `RAPPORT.md` : il n'y avait rien à chercher, seulement à mesurer ce
qu'on en gagne et à quel prix. Trois leviers, tous **inactifs par défaut** et tous
individuellement mesurables :

  · `stabilite` — n'accepter un découpage que s'il tient sur plusieurs échelons d'érosion, au
    lieu d'abandonner au premier `k` qui sépare (cf. `geometry.scinder_par_erosion`) ;
  · `remplissage_lobe_relatif` — juger la compacité d'un lobe par rapport à celle du PARENT,
    ce qui débloque les ballons de cri accolés, dont le remplissage est bas par nature ;
  · `encre` — corroborer le goulot par le TRAIT de contour, la sonde ci-dessous.

⚠ Ils changent le NOMBRE de bulles d'un tome déjà traité. C'est le mécanisme d'invalidation
existant qui s'en charge (`invalider_textes` + `downstream("detection")`), pas une rupture de
format ; le CHANGELOG le compte comme MINEUR.
"""
from __future__ import annotations

import numpy as np

from ._config import fusion
from .detection import BubbleRegion
from .geometry import dilate, remplissage, scinder_par_erosion

# Au-dessus de ce remplissage, on ne cherche même pas : un ballon, même dentelé, remplit sa
# boîte (médiane 0,89 sur les 687 bulles de plus de 20 000 px² du tome de référence). Le seuil
# n'est qu'une ÉCONOMIE — la plus haute scission retenue est à 0,849, et le tenter sur les 797
# bulles donne exactement le même résultat, en 68 s au lieu de 20.
#
# ⚠ **Ce « même résultat » vaut à GARDE-FOUS INCHANGÉS, et c'est tout ce qu'il dit.** Aucune
# scission n'a jamais été retenue au-dessus de 0,849 parce que les garde-fous refusaient tout
# au-delà ; le plafond n'est donc pas un fait de nature, c'est une conséquence. Les leviers du
# lot 13 (`stabilite`, `remplissage_lobe_relatif`) le remettent en jeu — d'où l'ordre imposé :
# les activer d'abord, REFAIRE la mesure ensuite, et seulement alors décider si ce seuil doit
# bouger. Le relever avant coûterait 48 s par tome pour rien, ce que le dépôt a déjà démontré.
#
# ⚠ Deux dénominateurs ici, et un troisième ailleurs :
#   · 797 = toutes les régions du tome au moment de cette mesure (lot 4.2) ;
#   · 687 = celles de plus de 20 000 px², seules concernées par la médiane citée.
#   · `geometry.scinder_par_erosion` dit 790 pour ce qui se présente comme le MÊME tome et
#     les MÊMES 40 découpages candidats. L'écart de 7 n'est expliqué nulle part, et il ne se
#     tranche pas par relecture : il se tranche en remesurant.
# `python tools/banc.py --tous` recompte depuis `regions.json` ; le protocole et le tableau
# daté sont dans `docs/chiffres-de-reference.md`.
SEUIL_CANDIDAT = 0.88

# En dessous de ce remplissage sans avoir pu être scindée, une région est SIGNALÉE dans
# `RAPPORT.md` : c'est là que le lettrage peut souffrir sans que rien d'autre ne le dise.
SEUIL_SUSPECT = 0.70

#: Sonde d'ENCRE (lot 13, L5.5) — corroboration du goulot par le trait de contour.
#:
#: ⚠ **Livrée inactive, et menée comme une ÉVALUATION, pas comme une étape à livrer.** C'est le
#: seul point du lot dont le résultat est incertain, et le critère d'abandon est écrit ici,
#: à l'avance, pour qu'on n'ait pas à en débattre après coup :
#:
#:   La sonde est abandonnée si, sur les 33 suspectes des cinq volumes, elle ne fait pas
#:   franchir le cap à au moins CINQ vrais doubles supplémentaires — ou si elle produit ne
#:   serait-ce qu'UN faux au sens du critère du lot (bulles non nettoyées : 2/813, 0/778,
#:   4/876, 1/924 · zéro zone restaurée sur les volumes paginés).
#:
#: Un gain nul la disqualifie autant qu'un faux positif : une étape qui ne rapporte rien est
#: une dette d'entretien sans contrepartie.
_ENCRE_DEFAUTS = {
    "actif": False,
    # Part des pixels de la FRONTIÈRE entre deux lobes qui doit être de l'encre pour que le
    # goulot soit confirmé. Deux ballons accolés ont DEUX contours qui se touchent : la
    # frontière suit une ligne d'encre continue. Une bulle unique tranchée à tort a une
    # frontière qui traverse son intérieur blanc.
    "part_min": 0.60,
    # Où placer la barre entre « fond » et « encre » dans l'histogramme du masque : 0.5 = à
    # mi-chemin entre le 5ᵉ centile (le plus noir : trait et texte) et le 75ᵉ (le fond).
    # Relatif, jamais absolu : une bulle inversée (blanc sur noir) existe dans le corpus.
    "facteur_seuil": 0.50,
    # Seuil de relâchement : quand l'encre confirme, le remplissage exigé d'un lobe retombe à
    # ce plancher. C'est le SEUL assouplissement que la sonde autorise — elle ne peut jamais
    # faire accepter un lobe plus creux que ça.
    "plancher_confirme": 0.35,
}

_DEFAUTS = {
    "actif": True,
    "seuil_remplissage": SEUIL_CANDIDAT,
    "seuil_suspect": SEUIL_SUSPECT,
    "remplissage_lobe_min": 0.72,
    "min_lobe_frac": 0.10,
    "aire_min": 10000,
    # ── Lot 13 ────────────────────────────────────────────────────────────────────────────
    # Les trois valeurs qui étaient RÉELLEMENT en dur. Ni l'une ni l'autre n'était dans
    # `_DEFAUTS`, donc `_cfg` les aurait ignorées **en silence** si on les avait écrites dans
    # `config.yaml` — et `max_lobes` n'est pas un rejet mais une TRONCATURE des germes : une
    # grappe de cinq ballons était ramenée à quatre, les pixels du cinquième repartant au lobe
    # le plus proche, sans un mot nulle part.
    #
    # ⚠ `seuil_remplissage` et `seuil_suspect`, eux, étaient déjà configurables — contrairement
    # à ce qu'affirmait l'ancien plan 05.
    "max_lobes": 4,
    "germe_frac": 0.02,
    "k_max": 0,                       # 0 = automatique (petit côté de la boîte // 3)
    # Aire minimale en FRACTION de la planche. 0.0 = on garde `aire_min` en pixels, ce qui est
    # le défaut livré. La valeur iso-comportement sur la planche de référence (1125×1600) est
    # 10000 / 1 800 000 ≈ 0.0056 ; c'est elle qu'il faut écrire pour que le seuil veuille dire
    # la même chose sur les scans 844×1200 de manga D.
    "aire_min_frac": 0.0,
    # Nombre d'échelons d'érosion consécutifs sur lesquels un découpage doit se répéter à
    # l'identique. 1 = régime historique (une seule chance, au premier `k` qui sépare).
    "stabilite": 1,
    "iou_stabilite": 0.80,
    # Compacité d'un lobe exigée RELATIVEMENT à celle du parent. 0.0 = seuil absolu
    # (`remplissage_lobe_min`), le défaut livré.
    "remplissage_lobe_relatif": 0.0,
    # Plancher bas et très permissif du mode relatif. 0.20 est calé sur le critère de
    # non-régression du lot : la configuration livrée sort DÉJÀ deux lobes à 0,01 et 0,14 sur
    # le webtoon, et aucun assouplissement ne doit pouvoir en produire un de plus.
    "remplissage_lobe_plancher": 0.20,
    "encre": dict(_ENCRE_DEFAUTS),
}


def _cfg(cfg: dict | None) -> dict:
    """C'est CE motif — clé connue **et** valeur non nulle — que `_config.fusion` généralise
    aux dix sites de la brique. Il vivait ici seul depuis le lot 4.2.

    ⚠ `fusion` est **plate** : un `encre:` partiel écrit dans `config.yaml` remplacerait tout
    le bloc et ferait disparaître les défauts des clés non écrites. D'où la seconde fusion,
    sur le sous-bloc — le seul de la brique qui en ait un."""
    c = fusion(_DEFAUTS, cfg)
    c["encre"] = fusion(_ENCRE_DEFAUTS, c.get("encre"))
    return c


def _kwargs(c: dict, *, remplissage_lobe_min: float | None = None) -> dict:
    """Les réglages de `c` traduits en arguments de `geometry.scinder_par_erosion`.

    Factorisé parce que les trois sites d'appel — la scission, le classement du rapport et la
    seconde chance de la sonde d'encre — doivent poser **exactement** la même question. Deux
    listes d'arguments tenues en parallèle divergent toujours, et ici la divergence signifie
    que `RAPPORT.md` décrirait une décision que le pipeline n'a pas prise.

    `remplissage_lobe_min` force le seuil de forme et neutralise le mode relatif : c'est ce
    dont la seconde chance a besoin pour rejouer le même découpage avec le seul plancher."""
    forcer = remplissage_lobe_min is not None
    return {
        "min_lobe_frac": c["min_lobe_frac"],
        "remplissage_lobe_min": (remplissage_lobe_min if forcer
                                 else c["remplissage_lobe_min"]),
        "remplissage_lobe_relatif": (0.0 if forcer else float(c["remplissage_lobe_relatif"])),
        "remplissage_lobe_plancher": float(c["remplissage_lobe_plancher"]),
        "aire_min": int(c["aire_min"]),
        "aire_min_frac": float(c["aire_min_frac"]),
        "germe_frac": float(c["germe_frac"]),
        "max_lobes": int(c["max_lobes"]),
        "k_max": int(c["k_max"]) or None,
        "stabilite": int(c["stabilite"]),
        "iou_stabilite": float(c["iou_stabilite"]),
    }


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Boîte englobante `(x0, y0, x1, y1)`, `x1`/`y1` exclusifs — même convention que
    `BubbleRegion.bbox` telle que la produit `detection.py`."""
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# ─────────────────────────────────────────────────────────────────────────────────────────
# Sonde d'ENCRE — lot 13, L5.5
#
# Toute la scission est morphologique : `scinder_par_erosion`, `_repousser`, `composantes` et
# `remplissage` ne reçoivent qu'un `np.ndarray`, et `geometry.py` n'importe que `numpy`. C'est
# sa propriété la plus utile — il ne connaît que des tableaux nus, donc il se teste sans corpus
# et sans modèle — et elle ne doit pas être cassée. La sonde vit donc ICI, dans le module qui a
# déjà l'accès au contexte, et `geometry.py` reste aveugle à l'image.
#
# Ce que la sonde apporte, et pourquoi elle est plausible : le TRAIT de contour est un signal
# fort, présent et gratuit — la chose la plus noire et la plus continue de la région —, et deux
# ballons accolés ont **deux** contours qui se touchent, donc une ligne d'encre qui traverse la
# région exactement là où le goulot se trouve.
#
# Elle répond aussi à un biais réel de l'érosion : l'élément structurant est CARRÉ et séparable
# (excellent pour la vitesse), donc anisotrope. Une bande à 45° de largeur perpendiculaire *w*
# n'admet qu'un carré de côté w/√2, contre *w* pour une bande alignée sur un axe : un goulot
# diagonal cède à un `k` environ 30 % plus petit qu'un goulot droit de même largeur. La
# conséquence n'est pas qu'on rate les goulots diagonaux — c'est que **le `k` retenu n'a pas la
# même signification selon l'orientation**, donc que les garde-fous de forme ne jugent pas la
# même chose dans les deux cas. Le trait, lui, n'a pas d'orientation privilégiée.
# ─────────────────────────────────────────────────────────────────────────────────────────

def seuil_encre(gris: np.ndarray, mask: np.ndarray, facteur: float = 0.50) -> float:
    """Niveau de gris en dessous duquel un pixel du masque compte comme de l'**encre**.

    Placé à `facteur` du chemin entre le 5ᵉ centile (le plus noir de la région : trait de
    contour et texte) et le 75ᵉ (le fond du ballon). **Relatif, jamais absolu** : une bulle
    inversée — blanc sur noir — existe dans le corpus, et un seuil en valeur absolue y
    déclarerait tout le fond « encre »."""
    valeurs = gris[mask]
    if valeurs.size == 0:
        return 0.0
    noir = float(np.percentile(valeurs, 5))
    fond = float(np.percentile(valeurs, 75))
    return fond - float(facteur) * (fond - noir)


def _frontieres(lobes: list[np.ndarray]) -> np.ndarray:
    """Pixels par lesquels les lobes se TOUCHENT — la couture que la scission propose.

    `dilate(a, 1) & b` : les pixels de `b` adjacents à `a`. Deux à deux, donc valable pour une
    grappe de trois lobes comme pour un simple double.

    C'est cette courbe-là qu'on interroge, et non une colonne ou une ligne de la boîte :
    la couture épouse la géométrie réelle du goulot, **quelle que soit son orientation**. Un
    balayage par colonnes rendrait à la sonde exactement le biais anisotrope qu'elle est
    censée compenser."""
    if len(lobes) < 2:
        return np.zeros_like(lobes[0]) if lobes else np.zeros((1, 1), dtype=bool)
    couture = np.zeros_like(lobes[0])
    for i, a in enumerate(lobes):
        for b in lobes[i + 1:]:
            couture |= (dilate(a, 1) & b) | (dilate(b, 1) & a)
    return couture


def part_dencre(gris: np.ndarray, mask: np.ndarray, lobes: list[np.ndarray],
                *, facteur_seuil: float = 0.50) -> float:
    """Fraction de la couture entre lobes qui est de l'**encre**. `0.0` si la couture est vide.

    C'est la mesure de la sonde, et elle se lit directement : proche de 1, la scission suit une
    ligne d'encre continue — donc deux contours qui se touchent ; proche de 0, elle traverse
    l'intérieur blanc d'un ballon unique."""
    couture = _frontieres(lobes)
    n = int(couture.sum())
    if n == 0:
        return 0.0
    seuil = seuil_encre(gris, mask, facteur_seuil)
    return float((gris[couture] <= seuil).sum()) / n


def trait_traversant(gris: np.ndarray, mask: np.ndarray, *, facteur_seuil: float = 0.50,
                     part_min: float = 0.60, couverture_min: float = 0.80) -> bool:
    """Une ligne d'encre traverse-t-elle le masque de part en part ?

    Balayage par colonnes **et** par lignes : pour chaque coupe, la part de pixels du masque
    qui sont de l'encre, et la part de l'étendue du masque que la coupe couvre. Une colonne
    qui est encre à `part_min` sur `couverture_min` de la hauteur du masque est une cloison.

    ⚠ Cette sonde-là est **délibérément grossière et n'a le droit de rien décider** : elle
    n'est appelée que sur les régions où l'érosion n'a trouvé AUCUN goulot, et son seul
    résultat est une ligne de `RAPPORT.md`. Le principe directeur du projet est que l'outil ne
    décide pas à la place de l'humain quand il n'est pas sûr — et un balayage par axes ne voit
    pas une cloison diagonale, ce qui suffit à l'interdire comme critère de découpe."""
    if not mask.any():
        return False
    seuil = seuil_encre(gris, mask, facteur_seuil)
    encre = mask & (gris <= seuil)
    for axe in (0, 1):
        total = mask.sum(axis=axe)
        sombre = encre.sum(axis=axe)
        etendue = int(total.max())
        if etendue <= 0:
            continue
        # Une coupe ne compte que si elle traverse VRAIMENT : `couverture_min` de l'étendue
        # maximale du masque sur cet axe. Sans ce garde-fou, la pointe d'une queue de bulle —
        # deux pixels de masque, tous deux du trait — passerait pour une cloison.
        assez_large = total >= couverture_min * etendue
        if not assez_large.any():
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            part = np.where(total > 0, sombre / np.maximum(total, 1), 0.0)
        if (part[assez_large] >= part_min).any():
            return True
    return False


def classer_non_scindees(regions: list[BubbleRegion],
                         cfg: dict | None = None) -> dict[int, str]:
    """Pour chaque région au remplissage bas et NON scindée : `"suspecte"`, `"instable"` ou
    `"dentelee"`.

    Le remplissage seul ne dit pas si une région est bi-lobée — les 45 « suspectes » du Vol.2
    sont des ballons de cri et des bulles à queue (cf. `scinder_regions`). Seule l'existence
    d'un GOULOT le dit, et c'est l'érosion qui répond.

    Trois familles depuis le lot 13, parce que le régime exigeant sait dire une chose de plus :

      · `dentelee` — aucun goulot à aucun échelon. Forme normale d'un ballon de cri ;
      · `instable` — un goulot s'ouvre, mais jamais deux échelons de suite sur la même
        géométrie. Signature d'un artefact de bruit, et **pas** un double manqué ;
      · `suspecte` — un goulot stable, refusé par les garde-fous de forme. Le seul cas
        réellement ambigu, donc le seul qui mérite qu'on aille voir la planche.

    Appelée à chaque rendu, y compris `--from rendu` : le coût est celui d'une érosion sur les
    seules régions au remplissage bas — une quarantaine sur un tome de 150 planches — et c'est
    ce qui permet au rapport de décrire le tome sans exiger de relancer la détection."""
    c = _cfg(cfg)
    classement: dict[int, str] = {}
    if not c["actif"]:
        return classement
    kwargs = _kwargs(c)
    for i, r in enumerate(regions or []):
        if r.kind != "bulle" or r.mask is None or not r.mask.any():
            continue
        if getattr(r, "scindee", False):
            continue
        rempl = remplissage(r.mask)
        if rempl >= c["seuil_suspect"]:
            continue
        diag: dict = {}
        scinder_par_erosion(r.mask, diagnostic=diag, **kwargs)
        if diag.get("motif") == "scission_instable":
            classement[i] = "instable"
        else:
            classement[i] = "suspecte" if diag.get("separable") else "dentelee"
    return classement


def scinder_regions(regions: list[BubbleRegion], cfg: dict | None = None,
                    gris: np.ndarray | None = None) -> tuple[list[BubbleRegion], list[dict]]:
    """Renvoie `(régions, diagnostics)`.

    Les régions scindées sont remplacées **à leur place** par leurs lobes, ce qui laisse
    `reading_order` faire son travail ensuite ; `score`, `cls` et `kind` sont héritées, la
    boîte est recalculée sur chaque lobe.

    `diagnostics` contient une entrée par région scindée (`type: "scindee"`) et une par région
    non scindée au remplissage bas (`type` : `"suspecte"`, `"instable"` ou `"dentelee"`), avec
    les remplissages mesurés. `index` est l'indice de la région **dans la liste d'entrée**, pas
    dans l'ordre de lecture — la numérotation du rapport se fait plus tard, après le tri.

    `gris` est la planche en niveaux de gris (`np.ndarray` 2-D à la taille des masques), et il
    n'est là que pour la sonde d'encre. **Optionnel par nécessité** : `checkpoints.migrate_page`
    scinde des masques déjà en cache sans jamais ouvrir l'image, et c'est ce qui permet de
    migrer un tome sans le modèle ONNX. Sans image, la sonde est simplement inactive.

    Ne touche pas aux régions dont `kind != "bulle"` (réservé phase 2 : onomatopées, texte
    posé sur le dessin), ni à rien du tout si `cfg["actif"]` est faux."""
    c = _cfg(cfg)
    if not c["actif"]:
        return list(regions), []

    enc = c["encre"]
    sonde = bool(enc["actif"]) and gris is not None
    kwargs = _kwargs(c)

    sorties: list[BubbleRegion] = []
    diagnostics: list[dict] = []
    for i, r in enumerate(regions):
        if r.kind != "bulle" or r.mask is None or not r.mask.any():
            sorties.append(r)
            continue
        rempl = remplissage(r.mask)
        if rempl >= c["seuil_remplissage"]:
            sorties.append(r)
            continue

        diag: dict = {}
        lobes = scinder_par_erosion(r.mask, diagnostic=diag, **kwargs)
        encre_part: float | None = None

        if lobes is None and sonde and diag.get("separable"):
            # ── Seconde chance, EN APPUI et jamais en remplacement ────────────────────────
            # Un goulot a été trouvé et les garde-fous de forme l'ont refusé. On rejoue le
            # MÊME découpage avec le seul plancher, uniquement pour obtenir les lobes, et on
            # demande au trait s'il confirme la couture. Le découpage n'est retenu que si
            # l'encre répond oui : la sonde ne peut jamais faire accepter autre chose que ce
            # que l'érosion avait déjà proposé.
            candidats = scinder_par_erosion(
                r.mask, **_kwargs(c, remplissage_lobe_min=float(enc["plancher_confirme"])))
            if candidats is not None:
                encre_part = part_dencre(gris, r.mask, candidats,
                                         facteur_seuil=float(enc["facteur_seuil"]))
                if encre_part >= float(enc["part_min"]):
                    lobes = candidats
                    diag = {"separable": True, "motif": "scindee_par_encre",
                            "germes_tronques": diag.get("germes_tronques", 0),
                            "k": diag.get("k")}

        if lobes is None:
            sorties.append(r)
            # ⚠ Un remplissage bas ne fait PAS une région bi-lobée. Sur le Vol.2, les
            # 45 régions rangées sous « bi-lobées SUSPECTES » ont été inspectées une par une :
            # ce sont des ballons de CRI (contour en étoile), des bulles à longue queue et une
            # case de décor — pas un seul vrai double. Leur remplissage est bas par nature
            # (0,15 à 0,70), et le rapport accusait la détection pour la forme normale d'une
            # bulle de manga.
            #
            # Le discriminant n'est donc pas le remplissage mais l'existence d'un GOULOT : une
            # région n'est ambiguë que si l'érosion a réellement trouvé deux lobes et que les
            # garde-fous ont refusé de couper. Aucune des 45 n'est dans ce cas.
            if rempl < c["seuil_suspect"]:
                if diag.get("motif") == "scission_instable":
                    type_diag = "instable"
                elif diag.get("separable"):
                    type_diag = "suspecte"
                else:
                    type_diag = "dentelee"
                entree = {"type": type_diag, "index": i, "bbox": r.bbox,
                          "remplissage": round(rempl, 3),
                          "motif": diag.get("motif", "")}
                if encre_part is not None:
                    entree["encre"] = round(encre_part, 3)
                # Un trait traverse le masque, mais l'érosion n'a trouvé aucun goulot : on le
                # SIGNALE, on ne scinde pas d'autorité. C'est le principe directeur du projet —
                # l'outil ne décide pas à la place de l'humain quand il n'est pas sûr.
                if sonde and type_diag == "dentelee" and trait_traversant(
                        gris, r.mask, facteur_seuil=float(enc["facteur_seuil"]),
                        part_min=float(enc["part_min"])):
                    entree["trait_sans_goulot"] = True
                if diag.get("germes_tronques"):
                    entree["germes_tronques"] = int(diag["germes_tronques"])
                diagnostics.append(entree)
            continue

        for lobe in lobes:
            sorties.append(BubbleRegion(bbox=_bbox(lobe), mask=lobe, score=r.score,
                                        cls=r.cls, kind=r.kind, scindee=True))
        entree = {"type": "scindee", "index": i, "bbox": r.bbox,
                  "remplissage": round(rempl, 3), "lobes": len(lobes),
                  "motif": diag.get("motif", "scindee"),
                  "remplissages_lobes": [round(remplissage(x), 3) for x in lobes]}
        if encre_part is not None:
            entree["encre"] = round(encre_part, 3)
        # Ce que `max_lobes` a écarté sur cette région. Jusqu'au lot 13, une grappe de cinq
        # ballons était ramenée à quatre sans un mot — ni log, ni rapport, ni diagnostic.
        if diag.get("germes_tronques"):
            entree["germes_tronques"] = int(diag["germes_tronques"])
        diagnostics.append(entree)
    return sorties, diagnostics
