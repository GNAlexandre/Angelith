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


def scinder_par_erosion(mask: np.ndarray, *, min_lobe_frac: float = 0.10,
                        remplissage_lobe_min: float = 0.72, aire_min: int = 10000,
                        germe_frac: float = 0.02, max_lobes: int = 4,
                        k_max: int | None = None,
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
       le découpage — une seule fois, au **premier** `k` qui sépare. On ne continue PAS
       l'échelle après un échec : ce serait chercher un `k` qui passe les garde-fous, donc
       s'en servir comme objectif de recherche au lieu de contrôle. Le premier `k` qui sépare
       est aussi le plus fidèle (l'érosion la plus douce).

    **Les seuils viennent d'une mesure, pas d'une intuition.** Les 790 bulles du tome de
    référence ont été passées avec une validation minimale, et les 40 découpages obtenus
    inspectés un par un sur le dessin. Les huit faux — une bulle unique tranchée en deux
    (pages 80 et 134), un fragment de kanji pris pour une bulle (page 33), une onomatopée sur
    de la trame (page 84) — ont tous un **remplissage de lobe** ≤ 0,71, là où les vrais doubles
    montent à 0,72-0,91. C'est ce qui fixe `remplissage_lobe_min`.

    Le réglage est délibérément **conservateur**, parce que les deux erreurs ne coûtent pas la
    même chose : scinder à tort une bulle qui allait bien casse une planche correcte (deux OCR
    partiels du même ballon, deux blocs de texte dans ses deux moitiés), alors que ne pas
    scinder un vrai double laisse simplement le défaut en place. Zéro faux positif sur le tome
    mesuré, au prix d'une douzaine de vrais doubles manqués (remplissage 0,57 à 0,71).

    Le résultat est une PARTITION, jamais des masques qui se chevauchent :
    `checkpoints.save_regions` écrit une image d'étiquettes et attribuerait un pixel partagé à
    la dernière bulle écrite.

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

    `diagnostic` est rempli en place (motif du pattern `styles_out` de `clean.py`) avec
    `{"separable": bool, "motif": str}`."""
    def _noter(separable: bool, motif: str):
        if diagnostic is not None:
            diagnostic["separable"] = separable
            diagnostic["motif"] = motif

    _noter(False, "aire_insuffisante")
    mask = np.asarray(mask, dtype=bool)
    aire = int(mask.sum())
    # Deux répliques françaises ne tiennent pas dans une région de 100×100 px : sous
    # `aire_min`, la scission n'a rien à apporter et ne peut être qu'un artefact.
    if aire < max(1, int(aire_min)):
        return None

    # Tout le travail se fait sur la BOÎTE, pas sur la pleine page. Un masque de bulle occupe
    # ~2 % d'une planche de 1125×1600 : éroder et étiqueter la page entière à chaque échelon
    # de l'échelle coûtait 5 s par bulle.
    ys, xs = np.nonzero(mask)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    sous = mask[y0:y1, x0:x1]
    petit_cote = min(y1 - y0, x1 - x0)
    if k_max is None:
        # Au-delà du tiers du petit côté, on ne sépare plus deux lobes : on les détruit.
        k_max = max(2, petit_cote // 3)
    germe_min = max(16, int(germe_frac * aire))
    min_aire = int(min_lobe_frac * aire)

    _noter(False, "aucun_goulot")
    for k in range(2, int(k_max) + 1):
        comps = composantes(erode(sous, k), min_aire=germe_min)
        if len(comps) < 2:
            continue
        lobes, reste = _repousser(sous, comps[:max_lobes], tours=int(k_max) + 2)
        # Validation sur les lobes SEULS, avant absorption des restes (cf. `_repousser`).
        if not all(int(lobe.sum()) >= min_aire and remplissage(lobe) >= remplissage_lobe_min
                   for lobe in lobes):
            _noter(True, "lobe_trop_creux")
            return None
        if reste.any():
            # L'union des lobes doit valoir le masque d'origine, sinon le nettoyage laisserait
            # du japonais visible. Chaque fragment va au lobe dont la BOÎTE est la plus proche.
            for frag in composantes(reste):
                lobes[_lobe_le_plus_proche(lobes, frag)] |= frag
        plein = []
        for lobe in lobes:
            p = np.zeros_like(mask)
            p[y0:y1, x0:x1] = lobe
            plein.append(p)
        _noter(True, "scindee")
        return plein
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
