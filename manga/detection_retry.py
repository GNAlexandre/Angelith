# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Arbitre d'une relance de détection : « mieux » n'est jamais « plus de bulles ».

## Le problème

Baisser `conf_threshold` fait toujours apparaître des régions. La question n'est pas
combien, mais **lesquelles** : sur le tome de référence, deux des détections basses étaient du
dessin (un gratte-ciel page 44, une trame). Une relance qui se contenterait de compter les
bulles installerait donc des faux positifs, et chacun coûte un nettoyage qui abîme la planche,
un OCR de bruit et une réplique inventée.

## La règle centrale, qui ne coûte rien de neuf

`manga/clean.py` **refuse déjà** de toucher une région dont l'uniformité tombe sous
`nettoyage.seuil_abandon` (0,35, posé dans un creux mesuré de la distribution : deux cas à
0,131 et 0,226, puis 0,457). Ce seuil existe, il est calibré, et il dit exactement ce qu'on
veut savoir :

> **Une région que le nettoyeur refuserait de nettoyer ne doit pas être détectée.**

L'arbitre s'y adosse plutôt que d'inventer un second critère qui divergerait du premier.

## Forme

Registre ORDONNÉ de vétos, sur l'idiome de `quality_manga.MOTIFS` : le premier qui répond
décide, et son nom est le motif. Numpy pur, aucune E/S, aucun modèle — donc testable sans GPU
et sans les 104 Mo de poids.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .detection import BubbleRegion
from .geometry import remplissage

# Un doublement du nombre de bulles n'est pas une amélioration de détection, c'est un
# effondrement de seuil. Mesuré sur le tome : la planche la plus peuplée a 13 bulles, et
# aucune relance légitime n'en fait apparaître plus de deux ou trois d'un coup.
_FACTEUR_EXPLOSION = 2.0

# Deux masques qui se recouvrent à ce point décrivent la même bulle deux fois. C'est aussi une
# corruption du cache : `save_regions` écrit UNE image d'étiquettes, donc un pixel partagé est
# attribué à la dernière région écrite, et le masque de la première est amputé en silence.
_IOU_CHEVAUCHEMENT = 0.30

LIBELLES = {
    "bulle_perdue": "une bulle de référence a disparu",
    "region_non_nettoyable": "une bulle gagnée serait refusée par le nettoyage (du dessin)",
    "chevauchement": "deux masques se recouvrent — la même bulle détectée deux fois",
    "explosion": "le nombre de bulles explose : c'est un effondrement de seuil",
    "aucun_gain": "aucune bulle gagnée, aucune géométrie améliorée",
}


@dataclass
class Verdict:
    """Ce que l'arbitre a conclu, et sur quoi."""
    accepte: bool
    motif: str = ""                  # clé de `LIBELLES` quand `accepte` est faux
    gagnees: list[int] = field(default_factory=list)      # index dans `candidates`
    perdues: list[int] = field(default_factory=list)      # index dans `reference`
    # Régions de référence disparues que le NETTOYEUR refusait déjà de toucher : les perdre
    # est un gain, pas une perte. C'est la même règle qu'ailleurs, appliquée à l'envers.
    faux_positifs_ecartes: list[int] = field(default_factory=list)
    conservees: int = 0
    detail: str = ""

    def __str__(self) -> str:
        etat = "ACCEPTÉ" if self.accepte else f"REFUSÉ ({LIBELLES.get(self.motif, self.motif)})"
        return (f"{etat} · +{len(self.gagnees)} / −{len(self.perdues)} "
                f"/ ={self.conservees}"
                + (f" / {len(self.faux_positifs_ecartes)} faux positif(s) écarté(s)"
                   if self.faux_positifs_ecartes else "")
                + (f" · {self.detail}" if self.detail else ""))


def iou_masques(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection sur union de deux masques booléens de même taille."""
    inter = int(np.count_nonzero(a & b))
    if not inter:
        return 0.0
    union = int(np.count_nonzero(a | b))
    return inter / union if union else 0.0


def apparier(reference: list[BubbleRegion], candidates: list[BubbleRegion],
             *, seuil: float = 0.50) -> list[int | None]:
    """Pour chaque région de `reference`, l'index de la candidate qui lui correspond.

    Appariement glouton par IoU décroissante : une bulle « conservée » est la même bulle, pas
    une bulle au même endroit. Sans cela, une région qui se scinde en deux compterait comme
    une conservée plus une gagnée, alors qu'elle a changé de nature."""
    paires = sorted(
        ((iou_masques(r.mask, c.mask), i, j)
         for i, r in enumerate(reference) for j, c in enumerate(candidates)),
        reverse=True)
    appariement: list[int | None] = [None] * len(reference)
    pris: set[int] = set()
    for score, i, j in paires:
        if score < seuil or appariement[i] is not None or j in pris:
            continue
        appariement[i], _ = j, pris.add(j)
    return appariement


def arbitrer(reference: list[BubbleRegion], candidates: list[BubbleRegion],
             uniformites: dict[int, float] | None = None, *,
             seuil_abandon: float = 0.35,
             uniformites_reference: dict[int, float] | None = None) -> Verdict:
    """Faut-il remplacer `reference` par `candidates` ?

    `uniformites` donne, par index de candidate, l'uniformité mesurée par `clean.analyze_bubble`
    — injectée plutôt que calculée ici, pour que ce module reste sans image ni E/S. Une
    candidate absente du dictionnaire n'est pas jugée sur ce critère (l'appelant n'a pas
    mesuré), ce qui est plus sûr que de lui inventer une valeur. `uniformites_reference` fait
    de même pour les régions en place.

    La règle centrale joue **dans les deux sens** : une région que le nettoyeur refuserait de
    nettoyer ne doit pas être détectée — donc la gagner est un véto, et la perdre est un gain.
    Sans cette symétrie, monter `conf` pour écarter le gratte-ciel pris pour une bulle page 44
    (score 0,36, uniformité 0,13) serait refusé comme « bulle perdue ».

    Vétos d'abord, gain ensuite : **le doute profite toujours à la détection en place**, parce
    qu'elle a déjà été payée en OCR et en traduction."""
    appariement = apparier(reference, candidates)
    perdues = [i for i, j in enumerate(appariement) if j is None]
    apparies = {j for j in appariement if j is not None}
    gagnees = [j for j in range(len(candidates)) if j not in apparies]
    uref = uniformites_reference or {}
    ecartes = [i for i in perdues if uref.get(i, 1.0) < seuil_abandon]
    vraies_pertes = [i for i in perdues if i not in ecartes]

    def _verdict(ok, motif="", detail=""):
        return Verdict(ok, motif, gagnees, perdues, ecartes, len(apparies), detail)

    if vraies_pertes:
        # Une vraie bulle a disparu : ce n'est pas un affinage, c'est une perte de contenu. Le
        # texte qu'elle portait ne serait plus ni lu ni traduit.
        return _verdict(False, "bulle_perdue",
                        f"bulle(s) de référence {[i + 1 for i in vraies_pertes]}")

    if reference and len(candidates) > _FACTEUR_EXPLOSION * len(reference):
        return _verdict(False, "explosion", f"{len(reference)} → {len(candidates)} bulles")

    for j in gagnees:
        u = (uniformites or {}).get(j)
        if u is not None and u < seuil_abandon:
            # Le nettoyeur refuserait de la toucher : la détecter n'apporterait qu'une région
            # non nettoyée, un OCR de bruit et une réplique inventée.
            return _verdict(False, "region_non_nettoyable",
                            f"bulle gagnée {j + 1}, uniformité {u:.2f} < {seuil_abandon:.2f}")

    for a in range(len(candidates)):
        for b in range(a + 1, len(candidates)):
            if iou_masques(candidates[a].mask, candidates[b].mask) >= _IOU_CHEVAUCHEMENT:
                return _verdict(False, "chevauchement", f"bulles {a + 1} et {b + 1}")

    if gagnees or ecartes:
        morceaux = []
        if gagnees:
            morceaux.append(f"{len(gagnees)} bulle(s) gagnée(s)")
        if ecartes:
            morceaux.append(f"{len(ecartes)} faux positif(s) écarté(s) "
                            f"(uniformité < {seuil_abandon:.2f})")
        return _verdict(True, "", ", ".join(morceaux) + ", aucune vraie bulle perdue")

    # Aucune bulle gagnée : reste la géométrie. Un masque mieux rempli sur la MÊME bulle veut
    # dire que le détecteur l'a mieux cernée — c'est un gain réel, invisible au décompte.
    avant = [remplissage(reference[i].mask) for i, j in enumerate(appariement) if j is not None]
    apres = [remplissage(candidates[j].mask) for j in appariement if j is not None]
    if avant and apres and sum(apres) > sum(avant) + 1e-6:
        return _verdict(True, "", f"remplissage moyen {np.mean(avant):.3f} → "
                                  f"{np.mean(apres):.3f}")
    return _verdict(False, "aucun_gain")
