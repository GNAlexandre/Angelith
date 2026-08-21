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
"""
from __future__ import annotations

import numpy as np

from .detection import BubbleRegion
from .geometry import remplissage, scinder_par_erosion

# Au-dessus de ce remplissage, on ne cherche même pas : un ballon, même dentelé, remplit sa
# boîte (médiane 0,89 sur les 687 bulles de plus de 20 000 px² du tome de référence). Le seuil
# n'est qu'une ÉCONOMIE — la plus haute scission retenue est à 0,849, et le tenter sur les 797
# bulles donne exactement le même résultat, en 68 s au lieu de 20.
SEUIL_CANDIDAT = 0.88

# En dessous de ce remplissage sans avoir pu être scindée, une région est SIGNALÉE dans
# `RAPPORT.md` : c'est là que le lettrage peut souffrir sans que rien d'autre ne le dise.
SEUIL_SUSPECT = 0.70

_DEFAUTS = {
    "actif": True,
    "seuil_remplissage": SEUIL_CANDIDAT,
    "seuil_suspect": SEUIL_SUSPECT,
    "remplissage_lobe_min": 0.72,
    "min_lobe_frac": 0.10,
    "aire_min": 10000,
}


def _cfg(cfg: dict | None) -> dict:
    out = dict(_DEFAUTS)
    for cle, val in (cfg or {}).items():
        if cle in out and val is not None:
            out[cle] = val
    return out


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Boîte englobante `(x0, y0, x1, y1)`, `x1`/`y1` exclusifs — même convention que
    `BubbleRegion.bbox` telle que la produit `detection.py`."""
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def classer_non_scindees(regions: list[BubbleRegion],
                         cfg: dict | None = None) -> dict[int, str]:
    """Pour chaque région au remplissage bas et NON scindée : `"suspecte"` ou `"dentelee"`.

    Le remplissage seul ne dit pas si une région est bi-lobée — les 45 « suspectes » du Vol.2
    sont des ballons de cri et des bulles à queue (cf. `scinder_regions`). Seule l'existence
    d'un GOULOT le dit, et c'est l'érosion qui répond.

    Appelée à chaque rendu, y compris `--from rendu` : le coût est celui d'une érosion sur les
    seules régions au remplissage bas — une quarantaine sur un tome de 150 planches — et c'est
    ce qui permet au rapport de décrire le tome sans exiger de relancer la détection."""
    c = _cfg(cfg)
    classement: dict[int, str] = {}
    if not c["actif"]:
        return classement
    for i, r in enumerate(regions or []):
        if r.kind != "bulle" or r.mask is None or not r.mask.any():
            continue
        if getattr(r, "scindee", False):
            continue
        rempl = remplissage(r.mask)
        if rempl >= c["seuil_suspect"]:
            continue
        diag: dict = {}
        scinder_par_erosion(r.mask, min_lobe_frac=c["min_lobe_frac"],
                            remplissage_lobe_min=c["remplissage_lobe_min"],
                            aire_min=c["aire_min"], diagnostic=diag)
        classement[i] = "suspecte" if diag.get("separable") else "dentelee"
    return classement


def scinder_regions(regions: list[BubbleRegion],
                    cfg: dict | None = None) -> tuple[list[BubbleRegion], list[dict]]:
    """Renvoie `(régions, diagnostics)`.

    Les régions scindées sont remplacées **à leur place** par leurs lobes, ce qui laisse
    `reading_order` faire son travail ensuite ; `score`, `cls` et `kind` sont héritées, la
    boîte est recalculée sur chaque lobe.

    `diagnostics` contient une entrée par région scindée (`type: "scindee"`) et une par région
    suspecte non scindée (`type: "suspecte"`), avec les remplissages mesurés. `index` est
    l'indice de la région **dans la liste d'entrée**, pas dans l'ordre de lecture — la
    numérotation du rapport se fait plus tard, après le tri.

    Ne touche pas aux régions dont `kind != "bulle"` (réservé phase 2 : onomatopées, texte
    posé sur le dessin), ni à rien du tout si `cfg["actif"]` est faux."""
    c = _cfg(cfg)
    if not c["actif"]:
        return list(regions), []

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
        lobes = scinder_par_erosion(
            r.mask, min_lobe_frac=c["min_lobe_frac"],
            remplissage_lobe_min=c["remplissage_lobe_min"], aire_min=c["aire_min"],
            diagnostic=diag)
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
                type_diag = "suspecte" if diag.get("separable") else "dentelee"
                diagnostics.append({"type": type_diag, "index": i, "bbox": r.bbox,
                                    "remplissage": round(rempl, 3),
                                    "motif": diag.get("motif", "")})
            continue

        for lobe in lobes:
            sorties.append(BubbleRegion(bbox=_bbox(lobe), mask=lobe, score=r.score,
                                        cls=r.cls, kind=r.kind, scindee=True))
        diagnostics.append({"type": "scindee", "index": i, "bbox": r.bbox,
                            "remplissage": round(rempl, 3), "lobes": len(lobes),
                            "remplissages_lobes": [round(remplissage(x), 3) for x in lobes]})
    return sorties, diagnostics
