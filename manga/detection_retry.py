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
    # Lot 12, L4.4 : le remplissage montait, mais parce que le masque avait GROSSI.
    "masque_gonfle": "le remplissage monte parce que le masque a grossi, pas parce que la "
                     "boîte a rétréci — la région a avalé du décor",
    # Lot 12, L4.2 : régime « référence vide », celui des 188 planches à zéro bulle.
    "aucune_nettoyable": "aucune candidate ne passe le seuil d'abandon du nettoyage : sur une "
                         "planche sans référence, c'est du dessin",
}


#: Pourquoi une planche a été jugée SUSPECTE, donc relancée à un réglage plus sensible
#: (lot 12, L4.2). Registre ordonné, par certitude décroissante : le premier qui répond décide.
#:
#: Un troisième déclencheur figurait au plan — « le masque du détecteur de TEXTE voit du texte
#: là où aucune bulle n'est détectée ». Il n'est pas écrit ici, et c'est délibéré : sur une
#: planche à zéro bulle il désignerait un SOUS-ENSEMBLE de `zero_bulle_encree`, qui escalade
#: déjà ; sur une planche qui porte des bulles, il décrit du texte hors bulle, c'est-à-dire le
#: sujet du lot 13 et non de celui-ci. Il coûterait une passe ONNX de 94,7 Mo par planche
#: suspecte, et il ne serait disponible que si la passe onomatopées tourne — le plan le disait
#: lui-même : « il ne peut donc pas être le seul ».
MOTIFS_ESCALADE = {
    "zero_bulle_encree": "aucune bulle détectée sur une planche qui porte de l'encre",
    "sous_la_mediane": "très en dessous de la médiane de bulles du tome",
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
    # Index des candidates à ÉCRIRE. `None` = toutes, et c'est le régime historique : quand une
    # référence existe, l'arbitre tranche en bloc (accepter la moitié d'une relance
    # produirait une planche qui n'a jamais été détectée telle quelle).
    #
    # Sur une planche à référence VIDE il n'y a rien à préserver, donc rien qui justifie le
    # tout-ou-rien : une pleine page d'action où l'escalade trouve trois vraies bulles et un
    # bout de trame doit rendre les trois. D'où une sélection, candidate par candidate.
    retenues: list[int] | None = None

    def retenir(self, candidates: list[BubbleRegion]) -> list[BubbleRegion]:
        """Les candidates que ce verdict fait écrire. À n'appeler que si `accepte`."""
        if self.retenues is None:
            return list(candidates)
        return [candidates[j] for j in self.retenues]

    def __str__(self) -> str:
        etat = "ACCEPTÉ" if self.accepte else f"REFUSÉ ({LIBELLES.get(self.motif, self.motif)})"
        selection = ("" if self.retenues is None or len(self.retenues) == len(self.gagnees)
                     else f" · {len(self.retenues)} retenue(s)")
        return (f"{etat} · +{len(self.gagnees)} / −{len(self.perdues)} "
                f"/ ={self.conservees}{selection}"
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
    qu'elle a déjà été payée en OCR et en traduction.

    ## Deux régimes, et il fallait le dire

    Avec `reference == []`, tout le registre ci-dessus se DÉSARME de lui-même : `apparier`
    rend `[]`, donc `perdues` est vide et le véto `bulle_perdue` ne peut pas s'armer ; le véto
    `explosion` est court-circuité par le premier terme de sa conjonction ; et la porte
    d'acceptation « des bulles gagnées » s'ouvre. Il ne restait donc, sur les 188 planches à
    zéro bulle du corpus — précisément celles où l'on va délibérément baisser les seuils —
    qu'un seul véto réellement actif.

    C'était supportable tant que ce cas n'existait pas : il n'y avait aucun chemin automatique
    vers une relance, et le site d'appel de l'orchestrateur sautait de toute façon le bloc de
    refus quand la référence était vide. Le lot 12 en fait le cas NOMINAL, d'où une branche
    explicite (`_arbitrer_sans_reference`) plutôt qu'un registre qui s'applique par accident.
    """
    if not reference:
        return _arbitrer_sans_reference(candidates, uniformites, seuil_abandon)
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
    #
    # ## Ce que ce critère laissait passer, et la délimitation exacte du problème
    #
    # Pour ATTEINDRE cette ligne il faut que `vraies_pertes` et `gagnees or ecartes` soient
    # toutes deux fausses, donc `perdues == []`, `gagnees == []`, `ecartes == []`. `apparier`
    # garantissant l'injectivité par son jeu `pris`, il s'ensuit
    # `len(candidates) == len(reference) == len(apparies)` : **l'appariement est ici une
    # bijection, par construction**.
    #
    # Une candidate qui FUSIONNERAIT deux ballons que la référence séparait laisserait donc une
    # référence non appariée, et serait refusée bien avant par `bulle_perdue`. Ce mode de
    # défaillance est déjà couvert — et par conséquent un correctif du type « refuser si le
    # nombre de régions a baissé » serait **inerte** : la condition est vraie par construction
    # à cette ligne. Ne pas l'écrire est délibéré.
    #
    # ## Ce qui reste, et qui est réel
    #
    # À bijection donnée, le remplissage d'une région peut monter pour deux raisons opposées :
    #
    #   1. la **boîte a rétréci** autour du même masque — la bulle est réellement mieux cernée ;
    #   2. le **masque a grossi** dans la même boîte — la région a avalé du décor adjacent.
    #
    # Le critère d'origine ne les distinguait pas, et il acceptait le second. Or `geometry.py`
    # établit dans ce même dépôt qu'un remplissage BAS est le signal d'un vrai double (0,61 et
    # 0,60) contre une médiane de 0,89 pour une bulle unique : un masque qui gonfle vers un
    # remplissage élevé va dans le sens de la PERTE d'information, pas du gain.
    #
    # ⚠ Contre-exemple à garder sous les yeux avant de « simplifier » ce critère : une bulle
    # dont la boîte est juste et dont le masque déborde sur la case voisine voit son
    # remplissage monter de 0,74 à 0,95 — et c'est exactement le cas qu'il faut refuser.
    #
    # Le test est PAR RÉGION et non sur la somme : une région qui rétrécit de 1 000 px pendant
    # qu'une autre en gagne 10 laisserait passer la seconde sur un total. Le prix d'un refus
    # est nul (on garde la détection en place, qui a déjà été payée), celui d'un décor avalé ne
    # l'est pas.
    #
    # ⚠ Le prix ASSUMÉ de ce critère, parce qu'il est réel : un masque dont les seuls pixels
    # gagnés BOUCHENT des trous intérieurs — une segmentation qui ne perce plus le milieu du
    # ballon — est lui aussi refusé ici. Le distinguer d'un décor avalé demanderait une analyse
    # de trous (le masque est de toute façon écrêté à sa boîte par `_postprocess`, donc un
    # gonflement se fait toujours À L'INTÉRIEUR de la boîte), c'est-à-dire un critère de plus,
    # qui divergerait du seuil d'abandon. Et le cas n'est perdu que lorsque RIEN d'autre n'a
    # changé : dès qu'une bulle est gagnée ou qu'un faux positif est écarté, la porte
    # d'acceptation précédente s'ouvre et le masque bouché passe avec elle.
    paires = [(i, j) for i, j in enumerate(appariement) if j is not None]
    avant = [remplissage(reference[i].mask) for i, _ in paires]
    apres = [remplissage(candidates[j].mask) for _, j in paires]
    if avant and apres and sum(apres) > sum(avant) + 1e-6:
        gonflees = [j for i, j in paires
                    if int(candidates[j].mask.sum()) > int(reference[i].mask.sum())]
        if gonflees:
            return _verdict(False, "masque_gonfle",
                            f"bulle(s) {[j + 1 for j in gonflees]} — aire du masque en hausse")
        return _verdict(True, "", f"remplissage moyen {np.mean(avant):.3f} → "
                                  f"{np.mean(apres):.3f}")
    return _verdict(False, "aucun_gain")


def _arbitrer_sans_reference(candidates: list[BubbleRegion],
                             uniformites: dict[int, float] | None,
                             seuil_abandon: float) -> Verdict:
    """Le régime de la planche à ZÉRO bulle — celui des 188 planches du corpus.

    Il n'y a rien à préserver, donc rien à perdre : le tout-ou-rien des autres vétos n'a plus
    de sens, et le seul critère qui en garde est **la règle centrale du module**, appliquée
    candidate par candidate :

    > Une région que le nettoyeur refuserait de nettoyer ne doit pas être détectée.

    Une bulle nettoyable est une bulle ; une bulle qu'on ne sait pas peindre est probablement
    du décor. C'est délibérément CONSERVATEUR : sur une planche où l'on vient d'abaisser les
    seuils, le seuil d'abandon est le seul rempart calibré dont on dispose.

    ⚠ Une candidate absente d'`uniformites` est CONSERVÉE, comme partout ailleurs dans ce
    module : l'appelant n'a pas mesuré, et lui inventer une valeur serait pire. L'orchestrateur
    mesure toujours (`clean.analyze_regions` sur les candidates), donc le cas ne se présente
    qu'aux tests et aux outils.

    Le véto `chevauchement` reste armé : ce n'est pas un jugement de détection mais une garde
    de CACHE — `masks.png` est une image d'étiquettes, un pixel partagé est attribué à la
    dernière région écrite et l'autre masque revient amputé. Sur le chemin de l'orchestrateur
    il ne peut pas s'armer (`rendre_disjoints` passe avant), et c'est très bien : une garde
    qu'on n'a jamais à voir se déclencher est une garde qui marche."""
    unis = uniformites or {}
    retenues = [j for j in range(len(candidates)) if unis.get(j, 1.0) >= seuil_abandon]
    ecartees = [j for j in range(len(candidates)) if j not in set(retenues)]
    gagnees = list(range(len(candidates)))

    def _verdict(ok, motif="", detail="", garde=None):
        return Verdict(ok, motif, gagnees, [], [], 0, detail,
                       retenues=list(range(len(candidates))) if garde is None else garde)

    for a in retenues:
        for b in retenues:
            if a < b and iou_masques(candidates[a].mask, candidates[b].mask) >= _IOU_CHEVAUCHEMENT:
                return _verdict(False, "chevauchement", f"bulles {a + 1} et {b + 1}", garde=[])
    if not candidates:
        # Rien à juger : la relance n'a rien trouvé du tout. Ce n'est pas le même fait que
        # « tout ce qu'elle a trouvé est du dessin », et le rapport doit pouvoir les séparer.
        return _verdict(False, "aucun_gain", "aucune candidate", garde=[])
    if not retenues:
        return _verdict(False, "aucune_nettoyable",
                        f"{len(candidates)} candidate(s), toutes sous "
                        f"{seuil_abandon:.2f} d'uniformité", garde=[])
    detail = f"{len(retenues)} bulle(s) sur une planche qui n'en avait aucune"
    if ecartees:
        detail += (f", {len(ecartees)} candidate(s) écartée(s) "
                   f"(uniformité < {seuil_abandon:.2f})")
    return _verdict(True, "", detail, garde=retenues)
