# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Morphologie et profils de masque en **numpy pur** — aucune dépendance ajoutée.

Ce module existe pour une raison précise : le masque renvoyé par `detection.py` couvre
**toute la bulle**, contour compris (modèle `yolov8m_seg-speech-bubble`). Or le trait de
contour est épais de 4 à 6 px et se trouve **à cheval sur la frontière** du masque. Mesuré
sur les planches du tome : la bande `mask & ~erode(mask, 1)` contient 55 à 70 % de pixels
sombres, et la bande *extérieure* (dilatation de 3 px) encore 45 à 65 %. À `k = 8`, la
bande retombe à 17-21 %. Autrement dit : pour mesurer ou repeindre l'intérieur d'une bulle
sans effacer son trait, il faut **éroder d'abord**. D'où `erode` et `safe_erode`.

**Pourquoi pas OpenCV.** L'érosion séparable en numpy donne un résultat **identique** à
`PIL.ImageFilter.MinFilter` (vérifié bit-à-bit par les tests, k = 1 à 8) tout en étant plus
rapide. Mesuré ici sur un masque 227×360 : 1,4 ms contre 3,7 ms à k=2, et 1,3 ms contre
21,6 ms à k=8. L'intérêt n'est pas tant le facteur brut que la **constance en k** — les
sommes cumulées rendent le coût indépendant du rayon, là où `MinFilter` croît avec lui, et
`clean.py` demande justement des rayons jusqu'à 12 px. Ajouter opencv (~60 Mo, conflits
fréquents de DLL avec `onnxruntime-directml`) casserait la promesse d'installation légère
de `requirements-manga.txt` pour un gain nul.

**Convention de bord** : les fenêtres sont *rognées* aux limites du tableau, et on exige
que la fenêtre rognée soit pleine. L'extérieur ne compte donc ni pour ni contre — c'est le
comportement d'extension de bord de `MinFilter`, et il rend `erode` et `dilate` exactement
duaux (`dilate(m, k) == ~erode(~m, k)`, vérifié par les tests).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _window_sums(mask: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Pour chaque ligne `i` de l'axe 0 : somme des booléens sur la fenêtre rognée
    `[i-k, i+k]`, et longueur réelle de cette fenêtre. Par somme cumulée : coût
    indépendant de `k`, là où un empilement de décalages coûterait 2k+1 passes."""
    n = mask.shape[0]
    cs = np.concatenate([np.zeros((1,) + mask.shape[1:], dtype=np.int32),
                         np.cumsum(mask, axis=0, dtype=np.int32)], axis=0)
    idx = np.arange(n)
    lo = np.clip(idx - k, 0, n)
    hi = np.clip(idx + k + 1, 0, n)
    longueur = (hi - lo).reshape((-1,) + (1,) * (mask.ndim - 1))
    return cs[hi] - cs[lo], longueur


def _erode_axis0(mask: np.ndarray, k: int) -> np.ndarray:
    somme, longueur = _window_sums(mask, k)
    return somme == longueur


def erode(mask: np.ndarray, k: int) -> np.ndarray:
    """Érosion par un élément structurant **carré** (2k+1)², appliqué de façon
    **séparable** (une passe par axe) — mathématiquement identique à la version 2-D, en
    O(1) par axe grâce aux sommes cumulées.

    `k <= 0` renvoie une copie inchangée."""
    mask = np.asarray(mask, dtype=bool)
    if k <= 0:
        return mask.copy()
    out = _erode_axis0(mask, k)
    return _erode_axis0(np.ascontiguousarray(out.T), k).T


def dilate(mask: np.ndarray, k: int) -> np.ndarray:
    """Dilatation = dual de l'érosion sur le complément. Sert à faire *grossir* le masque
    de texte provisoire pour manger l'anti-crénelage des glyphes (cf. `clean.py`, mode
    « texte »)."""
    mask = np.asarray(mask, dtype=bool)
    if k <= 0:
        return mask.copy()
    return ~erode(~mask, k)


def adaptive_radius(w: int, h: int, frac: float = 0.03, lo: int = 2, hi: int = 12) -> int:
    """Rayon d'érosion proportionnel au **petit côté** de la bulle, borné.

    Une fraction seule ne marche pas : sur une bulle de 40 px de haut, 3 % font 1 px et le
    contour survit dans l'intérieur ; sur une bulle pleine page, 3 % feraient 30 px et on
    perdrait toute la place utile. Les bornes [2, 12] encadrent le trait de contour réel
    (4-6 px, à cheval) sans jamais dévorer une petite bulle."""
    petit = max(1, min(int(w), int(h)))
    return int(np.clip(round(frac * petit), lo, hi))


def safe_erode(mask: np.ndarray, k: int, min_keep: float = 0.10,
               lo: int = 2) -> tuple[np.ndarray, int]:
    """Érode `mask` de `k`, mais **jamais au point de le faire disparaître**.

    Renvoie `(masque_érodé, k_effectif)`. Échelle de replis : `k`, puis `lo`, puis le
    masque brut (`k_effectif = 0`). Sans ce filet, une bulle fine ou une fausse détection
    en forme de sliver produirait un intérieur vide — donc une couleur de fond mesurée sur
    zéro pixel, et un lettrage sans place. `min_keep` est une fraction de l'aire d'origine.

    Le repli sur le masque brut est délibérément conservateur : il accepte de repeindre le
    contour de cette bulle-là plutôt que de ne rien pouvoir mesurer. Le cas est tracé dans
    `RAPPORT.md` (« bulles nettoyées en mode repli »)."""
    mask = np.asarray(mask, dtype=bool)
    aire = int(mask.sum())
    if aire == 0:
        return mask.copy(), 0
    seuil = min_keep * aire
    for k_essai in (int(k), int(lo)):
        if k_essai <= 0:
            continue
        erode_ = erode(mask, k_essai)
        if erode_.sum() >= seuil:
            return erode_, k_essai
    return mask.copy(), 0


def width_profile(mask: np.ndarray, cx: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Profil de largeur **utile** ligne par ligne : pour chaque `y`, la plage
    *contiguë* de pixels du masque qui **contient la colonne `cx`**.

    Renvoie `(largeur, x0, x1)`, trois tableaux de longueur H, avec `x1` **exclusif**. Une
    ligne dont le masque ne couvre pas `cx` a une largeur de 0.

    ⚠ C'est bien la plage contiguë, et non `premier..dernier` pixel de la ligne. La
    différence est ce qui rend le lettrage correct :
      · la **queue** de la bulle (l'appendice qui pointe vers le locuteur) est exclue,
        alors qu'un `premier..dernier` l'inclurait et annoncerait une largeur fantaisiste ;
      · un masque **bi-lobé** (deux bulles fusionnées par le détecteur) ne fait plus croire
        à une seule zone large qui engloberait le vide entre les deux.

    `cx` attendu : le centroïde horizontal du masque (le texte est centré dessus)."""
    mask = np.asarray(mask, dtype=bool)
    h, w = mask.shape
    cx = int(np.clip(cx, 0, w - 1))

    # Longueur du segment de True à partir de `cx`, vers la gauche puis vers la droite,
    # `cx` compté dans les deux. `argmin` donne l'indice du premier False ; quand la
    # ligne est entièrement True il renvoie 0, d'où le garde-fou `all()`.
    gauche = mask[:, :cx + 1][:, ::-1]
    n_gauche = np.where(gauche.all(axis=1), gauche.shape[1], gauche.argmin(axis=1))
    droite = mask[:, cx:]
    n_droite = np.where(droite.all(axis=1), droite.shape[1], droite.argmin(axis=1))

    dedans = mask[:, cx]
    largeur = np.where(dedans, n_gauche + n_droite - 1, 0).astype(np.int32)
    x0 = np.where(dedans, cx - n_gauche + 1, 0).astype(np.int32)
    x1 = np.where(dedans, cx + n_droite, 0).astype(np.int32)
    return largeur, x0, x1


def composantes(mask: np.ndarray, min_aire: int = 0) -> list[np.ndarray]:
    """Composantes connexes (voisinage à **4**) de `mask`, de la plus grande à la plus petite,
    filtrées à `min_aire` pixels. Chaque composante est un masque booléen de la taille de
    `mask`.

    Étiquetage par **plages de lignes + union-find** : les plages s'extraient en numpy (une
    passe de `diff` par ligne), et l'union ne parcourt que les plages — quelques centaines
    pour une bulle, là où une boucle par pixel en parcourrait cent mille. Pas de scipy
    (`ndimage.label` ferait ça en une ligne, mais scipy pèse ~40 Mo et le module entier tient
    la promesse d'installation légère de `requirements-manga.txt`, cf. l'en-tête).

    Le voisinage à 4 est délibéré : en 8-connexité, deux lobes qui ne se touchent que par un
    coin de pixel formeraient une seule composante, ce qui est exactement le cas qu'on veut
    séparer."""
    mask = np.asarray(mask, dtype=bool)
    h, w = mask.shape
    if not mask.any():
        return []

    # Extraction des plages en DEUX opérations numpy pour toute l'image, sans boucle par
    # ligne : une bordure de colonnes vides à gauche et à droite, puis un `diff` horizontal
    # dont les +1 sont les débuts et les -1 les fins. Une boucle Python par ligne coûtait
    # 150 ms par appel sur une boîte de 352×589 — et `scinder_par_erosion` appelle cette
    # fonction une fois par échelon de son échelle d'érosion.
    borde = np.zeros((h, w + 2), dtype=np.int8)
    borde[:, 1:-1] = mask
    d = np.diff(borde, axis=1)
    ly, lx0 = np.nonzero(d == 1)
    _ly1, lx1 = np.nonzero(d == -1)
    n = ly.size

    parent = np.arange(n, dtype=np.int64)

    def _trouver(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return int(x)

    def _unir(a: int, b: int) -> None:
        ra, rb = _trouver(a), _trouver(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # `ly` est trié par ligne (ordre de `np.nonzero`) : les plages d'une même ligne sont donc
    # contiguës, et un découpage par frontières suffit à les grouper.
    debuts = np.searchsorted(ly, np.arange(h), side="left")
    fins = np.searchsorted(ly, np.arange(h), side="right")

    # Union avec la ligne précédente : deux plages se touchent si leurs intervalles [x0, x1)
    # se chevauchent (voisinage à 4 : pas de tolérance d'un pixel de biais).
    for y in range(1, h):
        i, i_fin = debuts[y - 1], fins[y - 1]
        for j in range(debuts[y], fins[y]):
            b0, b1 = lx0[j], lx1[j]
            while i < i_fin and lx1[i] <= b0:
                i += 1
            k = i
            while k < i_fin and lx0[k] < b1:
                _unir(int(k), int(j))
                k += 1

    racines = np.array([_trouver(i) for i in range(n)], dtype=np.int64)
    longueurs = (lx1 - lx0).astype(np.int64)
    aires: dict[int, int] = {}
    for r, lg in zip(racines.tolist(), longueurs.tolist()):
        aires[r] = aires.get(r, 0) + lg

    gardees = sorted((a, r) for r, a in aires.items() if a >= min_aire)
    gardees.reverse()
    sorties: list[np.ndarray] = []
    for _aire, racine in gardees:
        comp = np.zeros((h, w), dtype=bool)
        for idx in np.flatnonzero(racines == racine).tolist():
            comp[ly[idx], lx0[idx]:lx1[idx]] = True
        sorties.append(comp)
    return sorties


def iou_bbox(a, b) -> float:
    """Intersection sur union de deux boîtes `(x0, y0, x1, y1)`, bords droit/bas exclus.

    Le pendant bon marché de `detection_retry.iou_masques` : il ne faut pas les masques, juste
    quatre nombres. L'éditeur s'en sert pour retrouver, après une retaille, LA MÊME bulle dans
    un jeu de régions que `reading_order` vient de réordonner — l'index n'est pas une identité
    stable, la géométrie l'est.

    Ici plutôt que dans `gui/` : c'est de la géométrie pure, elle doit rester testable sans
    PySide6, qui n'est qu'une dépendance optionnelle."""
    ax0, ay0, ax1, ay1 = (float(v) for v in a)
    bx0, by0, bx1, by1 = (float(v) for v in b)
    largeur = min(ax1, bx1) - max(ax0, bx0)
    hauteur = min(ay1, by1) - max(ay0, by0)
    if largeur <= 0 or hauteur <= 0:
        return 0.0
    inter = largeur * hauteur
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return float(inter / union) if union > 0 else 0.0


def suivre_boites(anciennes, nouvelles, seuil: float) -> dict[int, int]:
    """Où sont passées les boîtes `anciennes` dans le jeu `nouvelles` ? `{ancien: nouveau}`.

    Généralise à un LOT ce que l'éditeur faisait déjà pour une seule zone (`_resuivre_zone`),
    et pour la même raison : après une édition, `reading_order` a pu réordonner les index, si
    bien qu'une valeur attachée à « la bulle 6 » désigne une autre bulle. L'index n'est pas une
    identité stable, la géométrie l'est.

    Appariement **glouton par IoU décroissante**, comme `detection_retry.apparier` : sans lui,
    deux anciennes boîtes proches pourraient réclamer la même nouvelle, et la seconde écraserait
    la première en silence. Chaque nouvelle boîte n'est attribuée qu'une fois.

    Une ancienne boîte qui ne trouve rien au-dessus de `seuil` est **absente du résultat** —
    à l'appelant de décider ce qu'il en fait. Ne rien rendre vaut mieux que rendre un
    appariement faux : ce qui est en jeu est du texte écrit à la main."""
    scores = sorted(
        ((iou_bbox(a, b), i, j)
         for i, a in enumerate(anciennes) for j, b in enumerate(nouvelles)
         if iou_bbox(a, b) >= seuil),
        reverse=True)
    correspondance: dict[int, int] = {}
    pris: set[int] = set()
    for _score, i, j in scores:
        if i in correspondance or j in pris:
            continue
        correspondance[i] = j
        pris.add(j)
    return correspondance


def remplissage(mask: np.ndarray) -> float:
    """Fraction de la boîte englobante que le masque occupe réellement. `0.0` si vide.

    C'est LA mesure qui distingue une bulle d'un masque bi-lobé : sur les 687 bulles de plus
    de 20 000 px² du *manga A* Vol.1, la médiane est de **0,89** — un ballon,
    même dentelé, remplit sa boîte. Les deux masques que le détecteur avait fusionnés tombent
    à **0,61** et **0,60** : deux lobes en diagonale ne peuvent pas remplir leur boîte
    commune. Aucun code ne la calculait avant le lot 4.2, ce qui explique qu'aucun rapport
    n'ait jamais signalé le défaut."""
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return 0.0
    ys, xs = np.nonzero(mask)
    boite = (int(ys.max() - ys.min()) + 1) * (int(xs.max() - xs.min()) + 1)
    return float(mask.sum()) / boite


def _repousser(mask: np.ndarray, germes: list[np.ndarray],
               tours: int) -> tuple[list[np.ndarray], np.ndarray]:
    """Fait repousser `germes` par dilatations successives bornées à `mask`. Renvoie
    `(lobes, reste)`, où `reste` est ce que la repousse n'a **jamais atteint** — un fragment
    du masque détaché du corps principal (éclat de contour, artefact de détection).

    Un pixel revendiqué par deux germes au même tour est remis au tour suivant (la frontière
    aura bougé) ; s'il ne reste que du contesté, on tranche par ordre de germe — déterministe,
    puisque `composantes` les rend triés par aire.

    ⚠ `reste` est rendu à part, et non recollé au plus gros lobe, parce qu'il fausserait toute
    évaluation du découpage. Mesuré page 64 : un éclat de 200 px situé à l'opposé du masque
    faisait passer la boîte du lobe de 44 000 à 91 700 px² — son remplissage tombait à 0,48 et
    une scission pourtant parfaite était rejetée. Un fragment de 0,3 % de l'aire ne peut pas
    décider si un découpage est bon."""
    lobes = [g.copy() for g in germes]
    pris = np.zeros_like(mask)
    for lobe in lobes:
        pris |= lobe
    for _ in range(tours):
        libre = mask & ~pris
        if not libre.any():
            break
        # Pas de dilatation > 1 : la distance à couvrir est de l'ordre du rayon d'érosion,
        # un pas de 1 px multiplierait les tours pour rien.
        revendique = [dilate(lobe, 2) & libre for lobe in lobes]
        compte = np.zeros(mask.shape, dtype=np.int16)
        for r in revendique:
            compte += r
        progres = False
        for lobe, r in zip(lobes, revendique):
            gain = r & (compte == 1)
            if gain.any():
                lobe |= gain
                pris |= gain
                progres = True
        if not progres:
            for lobe, r in zip(lobes, revendique):
                gain = r & ~pris
                if gain.any():
                    lobe |= gain
                    pris |= gain
                    progres = True
            if not progres:
                break
    return lobes, mask & ~pris


def _boite_de(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Boîte englobante `(x0, y0, x1, y1)`, bords droit/bas **exclus** — la convention de
    `iou_bbox` et de `BubbleRegion.bbox`. Un masque vide rend une boîte nulle."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return 0, 0, 0, 0
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _memes_lobes(a: list[np.ndarray], b: list[np.ndarray], seuil: float) -> bool:
    """Les deux découpages désignent-ils **les mêmes lobes** ?

    Même cardinal, et appariement complet des boîtes au-dessus de `seuil` d'IoU. On passe par
    `suivre_boites` — donc par un appariement glouton, chaque lobe n'étant attribué qu'une
    fois — et non par une comparaison indice à indice : `composantes` trie par aire
    décroissante, et deux lobes d'aires voisines peuvent permuter d'un échelon d'érosion au
    suivant sans que le découpage ait bougé d'un pixel.

    Comparer des BOÎTES et non des masques est délibéré : c'est ce qui rend le critère
    insensible au fait que la repousse gagne ou perd quelques pixels de frontière à chaque
    `k`, tout en restant franchement discriminant — deux découpages différents d'un même
    masque ne peuvent pas avoir les mêmes boîtes."""
    if len(a) != len(b) or not a:
        return False
    correspondance = suivre_boites([_boite_de(m) for m in a],
                                   [_boite_de(m) for m in b], seuil)
    return len(correspondance) == len(a)


def scinder_par_erosion(mask: np.ndarray, *, min_lobe_frac: float = 0.10,
                        remplissage_lobe_min: float = 0.72, aire_min: int = 10000,
                        aire_min_frac: float = 0.0,
                        remplissage_lobe_relatif: float = 0.0,
                        remplissage_lobe_plancher: float = 0.20,
                        germe_frac: float = 0.02, max_lobes: int = 4,
                        k_max: int | None = None,
                        stabilite: int = 1, iou_stabilite: float = 0.80,
                        diagnostic: dict | None = None) -> list[np.ndarray] | None:
    """Sépare un masque **bi-lobé** (deux bulles que le détecteur a prises pour une) en une
    **partition** de ses pixels. Renvoie `None` si aucune séparation n'est trouvée, ce qui est
    le cas normal : une bulle unique ne doit jamais être scindée.

    Deux temps.

    1. **Trouver les germes.** On érode de plus en plus fort jusqu'à ce que le masque tombe en
       au moins deux composantes. C'est le goulot entre les lobes qui cède le premier —
       mesuré sur *manga A* Vol.1, il vaut le **recouvrement horizontal** des
       deux ballons : 46 px page 136, 87 px page 142, contre des lobes larges de 150 à 215 px.
       Une coupe droite en ligne ou en colonne échouerait là où l'érosion réussit, car le
       goulot est parfois plus LARGE que chaque lobe (266 px page 136 : les deux ballons y
       sont présents ensemble, donc la ligne qui les traverse est la plus large du masque).

       ⚠ Le seuil d'aire des germes (`germe_frac`) est délibérément **bas**. Le mesurer sur
       l'aire d'origine avec une valeur haute ne marche pas : à `k = 44`, l'érosion qui coupe
       enfin le goulot de la page 142 a déjà réduit le petit lobe à 11 % de l'aire de départ.
       Un germe n'a qu'un rôle, marquer *où* est un lobe ; sa taille se juge après la repousse.

    2. **Faire repousser les germes** dans le masque d'origine (`_repousser`), puis **valider**
       le découpage.

    ## Deux régimes de validation — `stabilite`

    `stabilite <= 1` — **régime historique** (lots 4.2 à 12), conservé au bit près. La
    validation a lieu une seule fois, au **premier** `k` qui sépare, et un échec des
    garde-fous fait abandonner toute l'échelle. Le raisonnement : continuer après un échec,
    ce serait chercher un `k` qui passe les garde-fous, donc s'en servir comme objectif de
    recherche au lieu de contrôle.

    `stabilite >= 2` — **régime exigeant** (lot 13). L'objection ci-dessus est sérieuse, mais
    l'abandon au premier échec est exactement ce qui produisait les 33 régions listées
    « bi-lobées SUSPECTES » des cinq volumes : un goulot large cède à `k = 3` en donnant deux
    lobes déséquilibrés, alors qu'à `k = 5` il aurait donné deux lobes propres. La sortie de
    l'impasse n'est pas « essayer jusqu'à ce que ça passe » — c'est **exiger la stabilité** :

      · un découpage n'est retenu que s'il se présente **identique sur `stabilite` échelons
        consécutifs** (même nombre de lobes, et lobes appariés d'un `k` au suivant par IoU de
        boîtes, cf. `_memes_lobes`) ;
      · dès qu'un échelon donne un découpage différent — ou ne sépare plus —, la série est
        **rompue** et le compte repart de zéro.

    C'est **plus exigeant que le critère historique, pas moins** : un vrai goulot produit une
    scission robuste sur une plage de `k`, un artefact de bruit produit une scission qui
    n'existe qu'à un seul `k`. Le découpage rendu est le **premier de la série** qui passe les
    garde-fous, c'est-à-dire l'érosion la plus douce : la plus fidèle au masque d'origine.

    Le coût est `k_max` érosions au lieu d'un arrêt au premier succès. `erode` et `dilate`
    sont séparables par sommes cumulées et **indépendants de `k`** (cf. l'en-tête du module :
    1,4 ms contre 3,7 ms à k=2, et 1,3 ms contre 21,6 ms à k=8) : le surcoût est **linéaire**
    en `k_max`, jamais quadratique.

    ## Les seuils de forme — absolu, ou relatif au parent

    **Les seuils viennent d'une mesure, pas d'une intuition.** Les 790 bulles du tome de
    référence ont été passées avec une validation minimale, et les 40 découpages obtenus
    inspectés un par un sur le dessin. (⚠ `bubbles_split.SEUIL_CANDIDAT` dit 797 pour le même
    tome et les mêmes 40 candidats : l'écart de 7 n'est expliqué nulle part et se tranche en
    remesurant — `python tools/banc.py --tous`, cf. `docs/chiffres-de-reference.md`.) Les huit faux — une bulle unique tranchée en deux
    (pages 80 et 134), un fragment de kanji pris pour une bulle (page 33), une onomatopée sur
    de la trame (page 84) — ont tous un **remplissage de lobe** ≤ 0,71, là où les vrais doubles
    montent à 0,72-0,91. C'est ce qui fixe `remplissage_lobe_min`.

    ⚠ Ce seuil **absolu** a un angle mort, et c'est le second défaut que le lot 13 traite :
    deux **ballons de cri** accolés — contour en étoile, très courant en action — ont chacun
    un remplissage naturellement bien en dessous de 0,72. Ils ne sont donc *jamais* scindés,
    quel que soit le `k`, et ce sont précisément les bulles où deux personnages crient
    séparément, donc où la fusion se voit le plus.

    `remplissage_lobe_relatif > 0` remplace le seuil absolu par un seuil **relatif à la forme
    du parent** :

        seuil_du_lobe = max(remplissage_lobe_plancher,
                            remplissage_lobe_relatif × remplissage(parent))

    Le critère devient « la scission ne **dégrade** pas la compacité » au lieu de « les lobes
    sont compacts dans l'absolu ». Les repères mesurés sont ceux de `remplissage` : médiane
    **0,89** sur 687 bulles de plus de 20 000 px², et **0,61** / **0,60** pour les deux
    masques réellement fusionnés. Un parent à 0,60 accepte donc des lobes à 0,57 ; un parent à
    0,89 exige des lobes convaincants.

    `remplissage_lobe_plancher` reste un **plancher bas, très permissif** : il refuse les
    scissions franchement dentelées, et il est là pour empêcher de reproduire les deux lobes à
    remplissage **0,01** et **0,14** que la configuration livrée sort déjà sur le webtoon
    (*webtoon A* Chap.11). Assouplir un garde-fou sans ce plancher, c'est les
    multiplier.

    ## L'aire minimale — absolue, ou relative à la planche

    `aire_min` est en **pixels**, et c'est un défaut : sur un scan basse résolution — il y en a
    dans le corpus, *manga D* est en 844×1200 et 848×1200 — deux petites bulles
    collées de 90×90 chacune font 16 200 px² ensemble et **passent**, tandis que deux de 60×60
    font 7 200 px² et ne sont **jamais examinées**. Le seuil n'exprime pas ce qu'on veut dire :
    on veut dire « assez grande pour qu'un goulot soit interprétable », et ça se mesure
    relativement à la planche.

    `aire_min_frac > 0` l'exprime relativement à la planche (`mask` est un masque pleine page),
    sur le motif exact de `adaptive_radius` : en fraction du **carré du petit côté**, et non de
    l'aire. La valeur iso-comportement sur la planche de référence est
    `10000 / 1125² ≈ 0,0079`.

    ⚠ **Le petit côté, et surtout pas l'aire.** Sur un webtoon, « la planche » est une bande
    d'un chapitre entier : 1080 × 10 000. Une fraction d'AIRE y vaut 0,0056 × 10,8 Mpx =
    **60 480 px²**, soit six fois le seuil visé — le garde-fou deviendrait plus sévère sur le
    format où les ballons sont déjà les plus petits. Le carré du petit côté rend 9 215 px², et
    la même valeur reste juste sur les quatre tailles de planche que *manga D* Vol.1
    mélange dans un seul tome (844×1200, 1000×1200, 1030×732, 1688×1200).

    ## Ce que le résultat garantit

    Le résultat est une PARTITION, jamais des masques qui se chevauchent :
    `checkpoints.save_regions` écrit une image d'étiquettes et attribuerait un pixel partagé à
    la dernière bulle écrite.

    Le réglage reste **conservateur** dans les deux régimes, parce que les deux erreurs ne
    coûtent pas la même chose : scinder à tort une bulle qui allait bien casse une planche
    correcte (deux OCR partiels du même ballon, deux blocs de texte dans ses deux moitiés),
    alors que ne pas scinder un vrai double laisse simplement le défaut en place.

    ## `diagnostic` — pourquoi `None` ne suffit pas

    `None` recouvrait deux situations que rien ne distinguait, et qui n'ont pourtant rien à
    voir :

      · **aucun goulot n'existe** — le masque ne se sépare à AUCUN échelon d'érosion. C'est
        une bulle unique : dentelée (ballon de cri), pointue (longue queue), peu importe. Son
        remplissage est bas par NATURE.
      · **un goulot existe mais les garde-fous l'ont refusé** — deux lobes ont bien été
        trouvés, et l'un d'eux ne remplit pas assez sa boîte pour qu'on ose couper.

    Seul le second cas est ambigu, donc digne d'être signalé. Mesuré sur le Vol.2 : sur les
    45 régions rangées sous « bi-lobées SUSPECTES », **aucune** n'a de goulot — ce sont
    45 ballons de cri et bulles à queue. Le rapport accusait la détection pour la forme
    normale d'une bulle de manga.

    Le régime exigeant en ajoute un troisième, et il ne dit pas la même chose que les deux
    autres : **`scission_instable`** — un découpage a bien été trouvé, mais il n'a jamais
    tenu `stabilite` échelons de suite. C'est la signature d'un artefact de bruit, et la
    ranger avec les vrais doubles reproduirait exactement le défaut que le lot 4.2 a corrigé
    pour les ballons de cri.

    `diagnostic` est rempli en place (motif du pattern `styles_out` de `clean.py`) avec
    `{"separable": bool, "motif": str, "germes_tronques": int, "k": int | None}`.
    `germes_tronques` compte les germes que `max_lobes` a **écartés** : une grappe de cinq
    ballons est ramenée à quatre, et les pixels du cinquième repartent au lobe le plus proche
    (`_lobe_le_plus_proche`). Jusqu'au lot 13, silencieusement."""
    etat = {"germes_tronques": 0}

    def _noter(separable: bool, motif: str, k: int | None = None):
        if diagnostic is not None:
            diagnostic["separable"] = separable
            diagnostic["motif"] = motif
            diagnostic["germes_tronques"] = int(etat["germes_tronques"])
            diagnostic["k"] = k

    _noter(False, "aire_insuffisante")
    mask = np.asarray(mask, dtype=bool)
    aire = int(mask.sum())
    # Deux répliques françaises ne tiennent pas dans une région de 100×100 px : sous
    # `aire_min`, la scission n'a rien à apporter et ne peut être qu'un artefact.
    petit_cote_planche = min(mask.shape) if mask.ndim == 2 else 0
    seuil_aire = (int(round(float(aire_min_frac) * petit_cote_planche ** 2))
                  if aire_min_frac > 0 else int(aire_min))
    if aire < max(1, seuil_aire):
        return None

    # Tout le travail se fait sur la BOÎTE, pas sur la pleine page. Un masque de bulle occupe
    # ~2 % d'une planche de 1125×1600 : éroder et étiqueter la page entière à chaque échelon
    # de l'échelle coûtait 5 s par bulle.
    ys, xs = np.nonzero(mask)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    sous = mask[y0:y1, x0:x1]
    petit_cote = min(y1 - y0, x1 - x0)
    if not k_max:
        # Au-delà du tiers du petit côté, on ne sépare plus deux lobes : on les détruit.
        k_max = max(2, petit_cote // 3)
    germe_min = max(16, int(germe_frac * aire))
    min_aire = int(min_lobe_frac * aire)
    # Seuil de forme d'un lobe : absolu, ou relatif à la compacité du parent (cf. supra).
    if remplissage_lobe_relatif > 0:
        seuil_lobe = max(float(remplissage_lobe_plancher),
                         float(remplissage_lobe_relatif) * remplissage(mask))
    else:
        seuil_lobe = float(remplissage_lobe_min)

    def _valide(lobes: list[np.ndarray]) -> bool:
        return all(int(lobe.sum()) >= min_aire and remplissage(lobe) >= seuil_lobe
                   for lobe in lobes)

    def _rendre(lobes: list[np.ndarray], reste: np.ndarray,
                k: int) -> list[np.ndarray] | None:
        """Absorbe les restes, contrôle une dernière fois, et remonte à la taille de `mask`.

        ⚠ **La copie n'est pas de la précaution, elle est nécessaire.** L'absorption écrit dans
        les lobes (`|=`), et en régime exigeant ces mêmes lobes servent de terme de comparaison
        à l'échelon suivant (`serie[-1]`). Les muter ferait comparer la géométrie du prochain
        `k` à une géométrie déjà modifiée."""
        lobes = [lobe.copy() for lobe in lobes]
        if reste.any():
            # L'union des lobes doit valoir le masque d'origine, sinon le nettoyage laisserait
            # du japonais visible. Chaque fragment va au lobe dont la BOÎTE est la plus proche.
            for frag in composantes(reste):
                lobes[_lobe_le_plus_proche(lobes, frag)] |= frag
        # ── Le plancher, une seconde fois — APRÈS absorption ────────────────────────────
        # `_valide` juge les lobes SEULS, avant les restes, et c'est délibéré : un éclat de
        # 200 px à l'opposé du masque faisait passer la boîte d'un lobe de 44 000 à 91 700 px²
        # et rejetait un découpage parfait (cf. `_repousser`). Mais le prix de ce choix est
        # qu'un lobe peut retomber sous le plancher une fois les restes recollés — mesuré à
        # **0,190** sur manga A Vol.1 en mode relatif, sous un plancher de 0,20.
        #
        # Le critère du lot porte sur les masques RÉELLEMENT écrits, pas sur ce que la
        # validation a vu : on re-contrôle donc ici, et seulement le plancher — jamais le seuil
        # relatif, qui redeviendrait sensible aux éclats.
        #
        # ⚠ Uniquement en mode relatif : le plancher est une notion de CE mode, et le régime
        # absolu doit rester iso-comportement au bit près.
        if remplissage_lobe_relatif > 0 and any(
                remplissage(lobe) < float(remplissage_lobe_plancher) for lobe in lobes):
            return None
        plein = []
        for lobe in lobes:
            p = np.zeros_like(mask)
            p[y0:y1, x0:x1] = lobe
            plein.append(p)
        _noter(True, "scindee", k)
        return plein

    exigeant = int(stabilite) >= 2
    # Série d'échelons CONSÉCUTIFS ayant rendu le même découpage : `(lobes, reste, valide, k)`.
    serie: list[tuple[list[np.ndarray], np.ndarray, bool, int]] = []
    vu_separation = False
    refus_stable = False
    # Échelons dont le rendu a déjà échoué (plancher non tenu après absorption des restes).
    # Sans cette mémoire, chaque échelon supplémentaire d'une série longue re-tenterait tous
    # les précédents, et `_rendre` n'est pas gratuit — il étiquette les restes.
    rendus_refuses: set[int] = set()

    _noter(False, "aucun_goulot")
    for k in range(2, int(k_max) + 1):
        comps = composantes(erode(sous, k), min_aire=germe_min)
        if len(comps) < 2:
            serie = []          # la série est rompue : ce n'était pas le même découpage
            continue
        vu_separation = True
        # Ce que `max_lobes` écarte. Ce n'est pas un rejet mais une TRONCATURE des germes : les
        # pixels du cinquième ballon d'une grappe repartent au lobe le plus proche.
        etat["germes_tronques"] = max(int(etat["germes_tronques"]),
                                      len(comps) - int(max_lobes))
        lobes, reste = _repousser(sous, comps[:max_lobes], tours=int(k_max) + 2)
        # Validation sur les lobes SEULS, avant absorption des restes (cf. `_repousser`).
        ok = _valide(lobes)

        if not exigeant:
            # Régime historique : une seule chance, au premier `k` qui sépare.
            rendu = _rendre(lobes, reste, k) if ok else None
            if rendu is None:
                _noter(True, "lobe_trop_creux", k)
                return None
            return rendu

        if serie and _memes_lobes(serie[-1][0], lobes, iou_stabilite):
            serie.append((lobes, reste, ok, k))
        else:
            serie = [(lobes, reste, ok, k)]
        if len(serie) >= int(stabilite):
            # Le découpage a tenu : on rend le PREMIER échelon valide de la série, donc
            # l'érosion la plus douce — la plus fidèle au masque d'origine.
            rendu = None
            for candidat in serie:
                if not candidat[2] or candidat[3] in rendus_refuses:
                    continue
                rendu = _rendre(candidat[0], candidat[1], candidat[3])
                if rendu is not None:
                    break
                rendus_refuses.add(candidat[3])
            if rendu is not None:
                return rendu
            refus_stable = True

    if refus_stable:
        _noter(True, "lobe_trop_creux")
    elif vu_separation:
        # Un goulot s'est ouvert quelque part, mais jamais `stabilite` échelons de suite sur la
        # même géométrie : c'est du bruit, pas une couture entre deux ballons.
        _noter(True, "scission_instable")
    return None


def _lobe_le_plus_proche(lobes: list[np.ndarray], frag: np.ndarray) -> int:
    """Indice du lobe dont la boîte englobante est la plus proche de celle de `frag`
    (distance de rectangle à rectangle, 0 s'ils se touchent). Départage par indice, donc
    par aire décroissante."""
    fy, fx = np.nonzero(frag)
    fy0, fy1, fx0, fx1 = int(fy.min()), int(fy.max()), int(fx.min()), int(fx.max())
    meilleur, d_min = 0, None
    for i, lobe in enumerate(lobes):
        ly, lx = np.nonzero(lobe)
        dy = max(0, max(int(ly.min()) - fy1, fy0 - int(ly.max())))
        dx = max(0, max(int(lx.min()) - fx1, fx0 - int(lx.max())))
        d = dy * dy + dx * dx
        if d_min is None or d < d_min:
            meilleur, d_min = i, d
    return meilleur


def vertical_extent(width: np.ndarray) -> tuple[int, int]:
    """Première et dernière ligne (bornes `[y0, y1)`, `y1` exclusif) où le profil de
    largeur est non nul. `(0, 0)` si le profil est vide — l'appelant doit traiter ce cas
    comme « pas de place », jamais comme une bulle de hauteur 0."""
    lignes = np.flatnonzero(np.asarray(width) > 0)
    if lignes.size == 0:
        return 0, 0
    return int(lignes[0]), int(lignes[-1]) + 1


# ═════════════════════════════════════════════════════════════════════════════════════════
# La QUEUE et les SAILLIES d'une bulle (lot 15, L7.3 et L7.4)
#
# `width_profile` documente, depuis toujours, qu'il calcule la plage CONTIGUË « pour que la
# queue de la bulle (l'appendice qui pointe vers le locuteur) soit exclue ». La décision est
# bonne pour son objet — mesurer la largeur utile au lettrage — mais elle nomme elle-même ce
# qu'on jette : **la queue est le seul signal graphique qui désigne le locuteur**, et le
# pipeline la calculait pour s'en débarrasser. Vérifié avant ce lot : aucun code du dépôt
# n'extrayait la queue ni sa direction, et les neuf occurrences du mot « queue » dans
# `manga/` étaient toutes descriptives (une catégorie de forme au rapport).
#
# ## Le principe, et pourquoi c'est de la morphologie et pas de la reconnaissance
#
# Une **ouverture** morphologique — érosion puis dilatation du même rayon — efface tout ce
# qui est plus fin que l'élément structurant et restitue le reste presque à l'identique. Ce
# qu'elle enlève à une bulle, c'est exactement ce qui dépasse de son corps : la queue, les
# festons d'un ballon de pensée, les pointes d'un ballon de cri. On appelle ces résidus des
# **saillies**, et leur nombre, leur taille et leur régularité suffisent à distinguer les
# trois formes — sans le moindre modèle, donc sans licence à respecter.
#
# ⚠ C'est la seule voie ouverte. L'appariement texte↔locuteur est traité en recherche
# (*The Manga Whisperer*, CVPR 2024, et les modèles Magi qui en découlent), avec de bons
# résultats — mais ces poids sont « available for academic research purposes only », et le
# corpus Manga109 qui les sous-tend a ses propres conditions. Ils sont donc inutilisables
# dans un projet redistribué sous AGPL. La conclusion est double : le problème est faisable,
# et la géométrie est la seule voie ouverte ici.
#
# ## Ce qu'on sait, et ce qu'on ne sait pas
#
# On ne sait pas *qui* parle. On sait *combien* de locuteurs et *qui reprend la parole* —
# exactement ce qu'il faut pour choisir un tutoiement et accorder un adjectif.
# ═════════════════════════════════════════════════════════════════════════════════════════

#: Rayon d'ouverture, en fraction du **petit côté** de la bulle. Une queue de bulle mesure
#: typiquement 10 à 20 % de la largeur du ballon à sa base ; 6 % la coupe donc franchement
#: sans entamer le corps. Bornes larges : sur une bulle de 40 px, 6 % font 2 px.
_QUEUE_FRAC = 0.06
_QUEUE_RAYON_MIN = 2
_QUEUE_RAYON_MAX = 24

#: Aire minimale d'une saillie, en fraction de l'aire du masque. En dessous, c'est du bruit
#: de contour ou un artefact de segmentation, pas une forme.
_SAILLIE_MIN_FRAC = 0.004


@dataclass(frozen=True)
class Queue:
    """La queue d'une bulle : où elle pointe, et ce qu'elle pèse.

    `angle` est en radians dans le repère IMAGE (y vers le bas), mesuré du centroïde du
    **corps** vers la pointe. `cible` est le point vers lequel la queue désigne — la pointe
    prolongée d'une demi-longueur de queue, c'est-à-dire approximativement la bouche du
    locuteur. C'est `cible`, et non l'angle, qui sert à décider que deux bulles ont le même
    locuteur : deux queues parallèles issues de bulles éloignées ne désignent pas la même
    personne, deux queues convergentes si."""
    angle: float
    pointe: tuple[int, int]
    cible: tuple[int, int]
    aire_frac: float


@dataclass(frozen=True)
class ProfilForme:
    """Ce que la morphologie sait dire d'un masque de bulle. Aucune interprétation ici : le
    classement en dialogue/pensée/récitatif/cri vit dans `manga.planche`, qui est aussi
    l'endroit où le taux d'« indéterminé » se mesure."""
    remplissage: float
    #: Remplissage du **corps** (masque ouvert), c'est-à-dire sans la queue ni les festons.
    #:
    #: ⚠ C'est celui-ci qu'il faut lire pour juger d'une FORME, et le brut qui trompe : une
    #: bulle de dialogue parfaitement ordinaire munie d'une longue queue tombe à 0,60 de
    #: remplissage brut — la queue étire la boîte englobante sans rien remplir — soit
    #: exactement la valeur d'un ballon de cri. C'est aussi ce qui explique que la section
    #: « contour DENTELÉ ou à longue queue » du rapport mêle les deux depuis toujours.
    remplissage_corps: float
    #: Nombre de saillies retenues (aire ≥ `_SAILLIE_MIN_FRAC`).
    saillies: int
    #: Aire de la plus grosse saillie, en fraction de l'aire du masque.
    saillie_max_frac: float
    #: Écart-type des aires de saillie rapporté à leur moyenne. Bas = festons réguliers
    #: (pensée) ; haut = une grosse pointe parmi des petites (queue, cri asymétrique).
    saillie_dispersion: float
    #: Fraction des lignes du masque dont la largeur contiguë est à moins de 10 % de la
    #: largeur maximale. Proche de 1 = les côtés sont parallèles, donc un rectangle.
    rectangularite: float
    #: Amplitude de l'ondulation du contour, **rapportée au rayon médian** et mesurée sur un
    #: contour dé-elliptisé (cf. `_profil_radial`). ~0 pour une ellipse ou un rectangle,
    #: faible pour un ballon de pensée (festons peu profonds), forte pour un ballon de cri
    #: (pointes profondes).
    ondulation: float
    #: Écart moyen au profil LISSÉ, rapporté au rayon médian : le RELIEF du contour, une fois
    #: sa forme générale retirée. C'est la mesure qui sépare un récitatif rectangulaire (dont
    #: l'`ondulation` est pourtant élevée, à cause de ses coins) d'un ballon festonné.
    relief: float
    #: Amplitude du lobe PÉRIODIQUE dominant du contour (cf. `_harmonique`). C'est la seule
    #: des trois mesures de contour qui distingue un ballon en étoile d'un masque simplement
    #: mal segmenté : douze pointes régulières concentrent l'énergie sur une harmonique, le
    #: bruit l'étale sur toutes.
    harmonique: float
    #: Nombre de maxima locaux du contour. Un ballon de pensée et un ballon de cri en ont
    #: tous les deux beaucoup ; c'est l'amplitude du lobe qui les sépare, pas leur nombre.
    pointes: int
    queue: Queue | None


def _saillies(mask: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    """`(corps, saillies)` — l'ouverture morphologique du masque, et ce qu'elle a retiré.

    Les saillies sont triées de la plus grande à la plus petite (`composantes` le fait) et
    filtrées à `_SAILLIE_MIN_FRAC` de l'aire du masque."""
    mask = np.asarray(mask, dtype=bool)
    aire = int(mask.sum())
    if aire == 0:
        return mask, []
    ys, xs = np.nonzero(mask)
    h = int(ys.max() - ys.min()) + 1
    w = int(xs.max() - xs.min()) + 1
    k = adaptive_radius(w, h, frac=_QUEUE_FRAC, lo=_QUEUE_RAYON_MIN, hi=_QUEUE_RAYON_MAX)
    corps = dilate(erode(mask, k), k) & mask
    if not corps.any():
        # Bulle plus fine que l'élément structurant : il n'y a pas de corps à distinguer
        # d'une saillie, et prétendre le contraire produirait n'importe quoi.
        return mask, []
    residu = mask & ~corps
    return corps, composantes(residu, max(1, int(aire * _SAILLIE_MIN_FRAC)))


#: Nombre de secteurs angulaires du profil radial. 120 donne 3° par secteur : assez fin pour
#: séparer deux festons voisins d'un ballon de pensée usuel (une dizaine sur le tour), assez
#: grossier pour qu'un secteur ne soit jamais vide sur une bulle de 40 px.
_SECTEURS = 120


def _profil_radial(mask: np.ndarray, reference: np.ndarray | None = None,
                   secteurs: int = _SECTEURS) -> np.ndarray:
    """Rayon du contour par secteur angulaire, sur un masque **dé-elliptisé**.

    ⚠ La dé-elliptisation n'est pas un raffinement : sans elle, une bulle ovale ordinaire
    — c'est-à-dire la forme la plus courante du corpus — présente un profil radial qui varie
    du simple au double entre son grand et son petit axe, et se lirait comme un contour
    violemment ondulé. On divise donc les écarts au centroïde par les demi-étendues : une
    ellipse devient un cercle, et ce qui reste d'ondulation est du contour, pas de la forme
    générale.

    ⚠ `reference` est le masque qui donne le CENTRE et les DEMI-ÉTENDUES ; `mask` est celui
    dont on mesure le contour. Les deux diffèrent, et c'est indispensable : on veut mesurer le
    contour BRUT (l'ouverture efface les pointes d'un ballon de cri, c'est-à-dire exactement
    la forme cherchée) mais se repérer sur le CORPS (la boîte du masque brut inclut la queue,
    qui étire une demi-étendue de 40 % et rend la dé-elliptisation fausse — un ballon ordinaire
    à longue queue y affichait alors 0,55 d'ondulation, soit autant qu'une étoile). Le corps
    donne le repère, le masque brut donne la forme.

    Un secteur vide (bulle très concave) hérite du rayon médian, ce qui ne crée ni pointe ni
    creux — un trou de mesure ne doit pas devenir un signal."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return np.zeros(secteurs)
    rys, rxs = np.nonzero(reference) if reference is not None else (ys, xs)
    if rys.size == 0:
        rys, rxs = ys, xs
    cy, cx = float(rys.mean()), float(rxs.mean())
    demi_y = max(1.0, float(rys.max() - rys.min()) / 2.0)
    demi_x = max(1.0, float(rxs.max() - rxs.min()) / 2.0)
    dy = (ys - cy) / demi_y
    dx = (xs - cx) / demi_x
    angle = np.arctan2(dy, dx)
    rayon = np.hypot(dy, dx)
    idx = np.clip(((angle + np.pi) / (2 * np.pi) * secteurs).astype(np.int64), 0, secteurs - 1)
    profil = np.zeros(secteurs)
    np.maximum.at(profil, idx, rayon)
    vus = profil > 0
    if not vus.any():
        return profil
    profil[~vus] = float(np.median(profil[vus]))
    return profil


#: Largeur de la moyenne glissante qui sert de « forme générale » (cf. `_ondulation`). 21
#: secteurs = 63° : au-delà de cette période c'est la FORME de la bulle (un coin de rectangle
#: arrondi revient tous les 90°), en deçà c'est du RELIEF de contour (six festons ou plus).
_LISSAGE = 21


#: Bornes du balayage harmonique (cf. `_harmonique`). Un ballon festonné ou en étoile porte
#: entre 6 et 20 lobes sur son tour ; en deçà c'est la FORME générale (2 = une ellipse mal
#: dé-elliptisée, 4 = les coins d'un rectangle), au-delà c'est du bruit de segmentation, dont
#: la période est de l'ordre du pixel.
_HARM_MIN, _HARM_MAX = 6, 20


def _harmonique(profil: np.ndarray) -> float:
    """Amplitude du lobe PÉRIODIQUE dominant du contour, rapportée au rayon médian.

    ## Pourquoi il a fallu cette mesure-là, et pas seulement le relief

    `relief` répond « il y a du relief », et c'est vrai d'un ballon de cri comme d'un masque
    de segmentation dentelé. Mesuré sur le corpus : le 94ᵉ centile du relief est atteint par
    des masques bruités, pas par des ballons en étoile — un seuil posé là aurait donc typé
    « cri » les bulles les moins bien segmentées du tome. C'est exactement l'annotation fausse
    que ce lot s'interdit.

    Ce qui distingue une étoile d'un contour sale n'est pas l'amplitude du relief mais sa
    **périodicité** : douze pointes régulières concentrent l'énergie sur une harmonique, le
    bruit l'étale sur toutes. On prend donc le plus grand coefficient de Fourier du profil
    radial dans la bande des lobes plausibles, et on ignore le reste."""
    n = profil.size
    median = float(np.median(profil)) if n else 0.0
    if n == 0 or median <= 0:
        return 0.0
    spectre = np.abs(np.fft.rfft(profil - profil.mean()))
    haut = min(_HARM_MAX, spectre.size - 1)
    if haut < _HARM_MIN:
        return 0.0
    # `2/n` ramène un coefficient de rFFT à l'amplitude crête de sa sinusoïde.
    return float(spectre[_HARM_MIN:haut + 1].max()) * 2.0 / n / median


def _ondulation(profil: np.ndarray) -> tuple[float, float, int]:
    """`(amplitude, relief, pointes)` d'un profil radial circulaire.

    Deux mesures, et il en fallait deux — c'est ce que le corpus a montré.

    · **amplitude** — écart interdécile rapporté à la médiane. Robuste à une queue unique, qui
      ne pèse que quelques secteurs, là où un `max - min` en ferait tout le verdict. ⚠ Mais
      elle mesure « à quel point ce n'est pas une ellipse », pas « à quel point c'est
      ondulé » : un récitatif rectangulaire y vaut 0,3 — le rayon d'un coin est √2 fois celui
      d'un côté — soit autant qu'un ballon de cri. Mesurée sur les 2 534 bulles de `build/` :
      médiane **0,22**, ce qui la rend inutilisable seule.
    · **relief** — écart moyen au profil LISSÉ, rapporté à la médiane. Le lissage retire la
      forme générale (ellipse, rectangle arrondi) et ne laisse que ce qui revient plus souvent
      qu'une fois par 63° : les festons d'un ballon de pensée, les pointes d'un ballon de cri.
      C'est la seule des deux qui sépare un récitatif d'un cri.

    Les deux sont rendues parce que chacune ferme une porte : le relief dit qu'il y a du
    relief, l'amplitude dit s'il est PROFOND. Un feston est un relief peu profond, une pointe
    de cri un relief profond."""
    if profil.size == 0 or float(np.median(profil)) <= 0:
        return 0.0, 0.0, 0
    median = float(np.median(profil))
    amplitude = float(np.percentile(profil, 90) - np.percentile(profil, 10)) / median
    # Moyenne glissante CIRCULAIRE : le profil se referme sur lui-même, et traiter ses bords
    # comme ceux d'un tableau ouvert créerait deux faux reliefs au secteur 0.
    noyau = np.ones(_LISSAGE) / _LISSAGE
    etendu = np.concatenate([profil[-_LISSAGE:], profil, profil[:_LISSAGE]])
    lisse = np.convolve(etendu, noyau, mode="same")[_LISSAGE:_LISSAGE + profil.size]
    relief = float(np.abs(profil - lisse).mean()) / median
    # Maxima locaux stricts sur un profil CIRCULAIRE, au-dessus de la médiane : un feston ou
    # une pointe, jamais une simple rugosité de segmentation.
    avant = np.roll(profil, 1)
    apres = np.roll(profil, -1)
    pointes = int(np.count_nonzero((profil > avant) & (profil >= apres)
                                   & (profil > median * 1.02)))
    return amplitude, relief, pointes


def profil_de_forme(mask: np.ndarray) -> ProfilForme:
    """Mesure la forme d'un masque de bulle. **Ne décide de rien.**

    ⚠ Le masque attendu est celui de `detection.py` : la bulle entière, contour compris. Le
    passer érodé (`BubbleStyle.interior`) donnerait un profil sans queue ni feston, ce qui
    est précisément ce que l'érosion sert à faire ailleurs.

    ⚠ **On recadre sur la boîte englobante avant de mesurer**, et ce n'est pas une
    micro-optimisation. Les masques de `detection.py` sont booléens **pleine page** : mesurer
    six bulles d'une planche 1125×1600 sans recadrer, c'est une dizaine de passes sur 1,8
    million de pixels par bulle, pour une bulle qui en occupe trente mille. Le recadrage rend
    le coût proportionnel à la bulle, ce qui est ce qu'il doit être quand la mesure tourne sur
    toutes les planches d'un tome. Les coordonnées de la queue sont rendues dans le repère de
    l'IMAGE : le décalage est remis à la fin."""
    mask = np.asarray(mask, dtype=bool)
    aire = int(mask.sum())
    if aire == 0:
        return ProfilForme(0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, None)
    ys0, xs0 = np.nonzero(mask)
    oy, ox = int(ys0.min()), int(xs0.min())
    mask = mask[oy:int(ys0.max()) + 1, ox:int(xs0.max()) + 1]

    corps, saillies = _saillies(mask)
    aires = np.array([float(s.sum()) for s in saillies], dtype=float)
    max_frac = float(aires.max() / aire) if aires.size else 0.0
    dispersion = float(aires.std() / aires.mean()) if aires.size and aires.mean() > 0 else 0.0

    # Rectangularité : constance de la largeur contiguë ligne par ligne. Un récitatif a des
    # côtés parallèles, un ballon a un ventre. Mesurée sur le CORPS, pour qu'une queue ne
    # vienne pas trancher le verdict — c'est justement `width_profile` qui l'exclut déjà.
    ys, xs = np.nonzero(corps)
    cx = int(round(xs.mean()))
    largeur, _x0, _x1 = width_profile(corps, cx)
    lignes = largeur[largeur > 0]
    rect = (float((lignes >= 0.90 * lignes.max()).mean())
            if lignes.size and lignes.max() > 0 else 0.0)

    # ⚠ Le profil radial se mesure sur le masque BRUT, et surtout pas sur le corps.
    #
    # Le corps est une OUVERTURE morphologique : elle efface tout ce qui est plus fin que
    # l'élément structurant — la queue, mais aussi **les pointes d'un ballon de cri**. Mesuré
    # sur un ballon en étoile de synthèse : son contour, une fois ouvert, ondule à 0,16 là où
    # le contour brut ondule à 0,58. Autrement dit, mesurer le relief sur le corps revient à
    # gommer exactement la forme qu'on cherche.
    #
    # Ce qu'on redoutait en passant par le corps — qu'une queue unique fasse passer toute
    # bulle de dialogue pour un cri — n'arrive pas, à une condition : que le REPÈRE reste le
    # corps (cf. `_profil_radial`). La queue devient alors une pointe locale, qu'un écart
    # interdécile ignore (cinq à dix secteurs sur cent vingt) et qu'une analyse harmonique de
    # la bande 6-20 lobes n'excite pas.
    radial = _profil_radial(mask, corps)
    amplitude, relief, pointes = _ondulation(radial)
    harmonique = _harmonique(radial)

    queue = _queue_depuis(corps, saillies, aire)
    if queue is not None:
        queue = Queue(angle=queue.angle,
                      pointe=(queue.pointe[0] + ox, queue.pointe[1] + oy),
                      cible=(queue.cible[0] + ox, queue.cible[1] + oy),
                      aire_frac=queue.aire_frac)

    return ProfilForme(remplissage=remplissage(mask), remplissage_corps=remplissage(corps),
                       saillies=len(saillies),
                       saillie_max_frac=max_frac, saillie_dispersion=dispersion,
                       rectangularite=rect, ondulation=amplitude, relief=relief,
                       harmonique=harmonique, pointes=pointes,
                       queue=queue)


def _queue_depuis(corps: np.ndarray, saillies: list[np.ndarray], aire: int) -> Queue | None:
    """La queue, s'il y en a une : la saillie qui **s'éloigne** du corps, et une seule.

    Trois refus, et ils sont ce qui rend l'étiquette de locuteur défendable :

    · **aucune saillie assez grosse** — une bulle lisse n'est pas parlée (récitatif) ;
    · **la saillie ne dépasse pas** — un creux de contour, une bosse de feston : sa pointe
      reste à l'intérieur du rayon médian du corps, elle ne désigne rien ;
    · **deux saillies rivales** — un ballon festonné ou en étoile en porte cinq ou dix, toutes
      comparables. En désigner une comme « la » queue serait tirer au sort la direction du
      locuteur, et une direction fausse est pire qu'aucune direction (cf. `manga.planche`)."""
    if not saillies:
        return None
    ys, xs = np.nonzero(corps)
    cy, cx = float(ys.mean()), float(xs.mean())
    rayon_median = float(np.median(np.hypot(ys - cy, xs - cx)))
    if rayon_median <= 0:
        return None

    # Pour chaque saillie : son pixel le plus éloigné du centroïde du corps.
    candidates = []
    for s in saillies:
        sy, sx = np.nonzero(s)
        d = np.hypot(sy - cy, sx - cx)
        j = int(d.argmax())
        candidates.append((float(d[j]), int(sx[j]), int(sy[j]), float(s.sum())))
    candidates.sort(reverse=True)

    d_max, px, py, aire_s = candidates[0]
    # Une vraie queue sort NETTEMENT du corps. Le facteur est bas (1,15) parce que le
    # centroïde d'une bulle allongée est déjà loin de ses extrémités ; c'est la comparaison
    # avec les autres saillies, juste en dessous, qui fait le vrai tri.
    if d_max < 1.15 * rayon_median:
        return None
    if len(candidates) > 1 and candidates[1][0] > 0.88 * d_max:
        return None                      # deux appendices aussi saillants : on ne tranche pas

    angle = float(np.arctan2(py - cy, px - cx))
    longueur = d_max - rayon_median
    cible = (int(round(px + 0.5 * longueur * np.cos(angle))),
             int(round(py + 0.5 * longueur * np.sin(angle))))
    return Queue(angle=angle, pointe=(px, py), cible=cible,
                 aire_frac=float(aire_s / aire) if aire else 0.0)
