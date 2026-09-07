# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Lire une onomatopée, et savoir quand on ne sait pas — lot 21, L21.3.

## Le problème, mesuré

`manga-ocr` est un modèle de **dialogue**. Il rend toujours une phrase japonaise plausible,
y compris sur un aplat de dessin, et il n'expose aucun score de confiance exploitable. Sur
l'échantillon de 60 zones transcrites à l'œil (graine 21, `docs/mesures/sfx-2026-08-28.md`) :

| verdict sur les 41 zones dont la lecture nourrit le LLM | n | part |
|---|--:|--:|
| lecture **exacte** | 6 | 14,6 % |
| lecture partielle (le sens passe, la chaîne est fausse) | 6 | 14,6 % |
| **plausible mais fausse** — le cas dangereux | 21 | 51,2 % |
| manifestement absurde | 8 | 19,5 % |

Et le détail qui décide de tout : les 6 lectures exactes se répartissent en **4 narrations
sur 9** (44 %) et **2 onomatopées sur 14** (14 %), les deux étant des katakana standard de
deux signes (`ゴッ`, `ズッ`). Autrement dit `manga-ocr` lit correctement la NARRATION
imprimée — qui est typographiquement du dialogue — et n'atteint presque jamais l'onomatopée
stylisée. C'est cohérent avec ce qu'il est, et ce n'est pas réparable par un meilleur
découpage : les trois découpes essayées avant ce lot échouaient déjà également.

## Le critère : la CONCORDANCE, pas la confiance

Aucune de ces voies ne rend un score exploitable. En revanche, **deux voies indépendantes
qui s'accordent sont un signal fort**, et deux voies qui divergent le sont dans l'autre
sens. C'est le seul critère de première classe que ce module implémente, et c'est lui — et
lui seul — qui autorisera `PLAN-22` à dessiner quoi que ce soit.

    lecture_sure     : deux voies indépendantes rendent la même chose (à la normalisation
                       près). La zone est utilisable.
    lecture_douteuse : elles divergent, ou une seule voie a répondu. La zone part en voie C.

## Voie C — refuser de lire, et le dire mieux

Une zone `lecture_douteuse` n'est pas jetée : son **crop est exporté** et listé au rapport,
pour qu'un humain la transcrive en dix secondes au lieu de rouvrir la planche et de la
chercher. Cela transforme « il y a 260 zones de texte quelque part dans ce tome » en une
planche-contact qu'on peut traiter. C'est peu, et c'est immédiatement utile.

## Ce que ce module ne fait pas

Il ne dessine rien, ne décide d'aucun mode de rendu, et **n'est armé par aucun défaut** :
`manga.onomatopees.concordance` vaut `false` dans le code comme dans `config.yaml`, parce
que la seconde voie coûte un appel LLM de plus par planche porteuse. Ce qu'il apporte
désarmé, c'est le vocabulaire — `LECTURE_SURE` / `LECTURE_DOUTEUSE` — sans lequel `PLAN-22`
n'a rien sur quoi s'appuyer.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

#: Verdicts de lecture. Valeurs PERSISTÉES (`sfx.json`, `RAPPORT.md`) : les renommer
#: invaliderait les rapports déjà écrits pour un gain cosmétique.
LECTURE_SURE = "sure"
LECTURE_DOUTEUSE = "douteuse"

#: Similarité minimale entre deux lectures normalisées pour les dire concordantes.
#:
#: ⚠ **Pas l'égalité stricte**, et c'est une mesure : sur l'échantillon de 60 zones, deux
#: lectures d'une même narration diffèrent couramment d'un signe — `私の知らないところで歳の
#: ように変わっていく` contre `…冗談のように…` — là où deux lectures d'un dessin n'ont
#: rigoureusement rien en commun. Un seuil de similarité sépare les deux cas ; l'égalité
#: stricte les confondrait tous les deux en « douteux » et le drapeau ne dirait plus rien.
#:
#: 0,80 est calé sur l'écart d'un caractère sur cinq, c'est-à-dire la longueur médiane d'une
#: onomatopée du corpus (`sfx.json` : médiane 3 caractères hors ponctuation, p90 12).
SEUIL_CONCORDANCE = 0.80

#: Ponctuation et signes que la normalisation retire avant comparaison. Deux lectures qui ne
#: diffèrent que par un `．．．` contre `…` disent la même chose.
#: ⚠ Les formes ASCII y sont OBLIGATOIRES à côté des pleines chasses : `NFKC` passe AVANT
#: cette expression et replie déjà `．` sur `.`, `，` sur `,`, `！` sur `!`. Une classe qui
#: n'aurait listé que la pleine chasse ne retirerait donc rien du tout.
_A_RETIRER = re.compile(r"[\s　。、.,．，…‥・「」『』（）()！!？?〜~ー\-–—]+")


def normaliser(texte: str) -> str:
    """Forme canonique d'une lecture, pour la seule comparaison.

    Trois passes, dans cet ordre : compatibilité Unicode (`NFKC`, qui replie la pleine
    chasse `ＲａｗＬａｚｙ` sur `RawLazy` et `．` sur `.`), retrait de la ponctuation et des
    espaces, minuscules.

    ⚠ Le résultat n'est **jamais** persisté ni affiché : c'est une clé de comparaison, pas
    une lecture. Écrire la forme normalisée à la place du texte lu perdrait justement ce que
    l'allongement `ォォォ` porte — l'intensité."""
    t = unicodedata.normalize("NFKC", texte or "")
    return _A_RETIRER.sub("", t).lower()


def _nfkc(texte: str) -> str:
    """Forme de repli : compatibilité Unicode et minuscules, **sans** retrait de ponctuation.

    Elle sert au seul cas où la forme canonique ne dit plus rien — deux lectures de pure
    ponctuation, qui s'y réduisent toutes deux au vide. `．．．` et `...` se comparent alors
    ici, et ils concordent. Les traiter en « douteuses » ferait partir en voie C les
    **398 zones de ponctuation sur 2 456** du corpus, pour un problème d'encodage."""
    return unicodedata.normalize("NFKC", texte or "").strip().lower()


def similarite(a: str, b: str) -> float:
    """Similarité de deux lectures, une fois normalisées. `0.0` si l'une est vide.

    `difflib.SequenceMatcher` : bibliothèque standard, aucun poids, aucune dépendance. La
    règle du dépôt sur les dépendances lourdes vaut aussi pour les légères — une distance
    d'édition ne justifie pas un paquet."""
    na, nb = normaliser(a), normaliser(b)
    if not na and not nb:
        na, nb = _nfkc(a), _nfkc(b)      # deux lectures de pure ponctuation
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def verdict(lectures: list[str], *, seuil: float = SEUIL_CONCORDANCE) -> tuple[str, float]:
    """`(LECTURE_SURE | LECTURE_DOUTEUSE, meilleure similarité)` pour une même zone.

    `lectures` porte une entrée par VOIE, dans l'ordre où elles ont été tentées ; une voie
    qui n'a rien rendu y figure par une chaîne vide, pour que l'alignement par position
    survive.

    ⚠ **Une seule voie ne concorde avec rien.** Le verdict est alors `douteuse`, et ce n'est
    pas une sévérité gratuite : c'est exactement l'état du dépôt avant ce lot — une lecture,
    aucune confirmation — et l'appeler « sûre » reviendrait à baptiser le problème."""
    # `_nfkc` et non `normaliser` : une lecture de pure ponctuation EST une lecture, et
    # `similarite` sait la comparer (cf. `_nfkc`).
    utiles = [t for t in (lectures or []) if _nfkc(t)]
    if len(utiles) < 2:
        return LECTURE_DOUTEUSE, 0.0
    meilleure = max(similarite(a, b)
                    for i, a in enumerate(utiles) for b in utiles[i + 1:])
    return (LECTURE_SURE if meilleure >= seuil else LECTURE_DOUTEUSE), meilleure


def verdicts(par_zone: list[list[str]], *,
             seuil: float = SEUIL_CONCORDANCE) -> tuple[list[str], list[float]]:
    """`verdict` sur une liste de zones. Deux listes **alignées par position** sur l'entrée."""
    couples = [verdict(lectures, seuil=seuil) for lectures in (par_zone or [])]
    return [v for v, _ in couples], [round(s, 4) for _, s in couples]


def taux_sures(verdicts_zone: list[str]) -> float:
    """Part de zones `lecture_sure`. C'est le chiffre que le lot doit publier par tome."""
    if not verdicts_zone:
        return 0.0
    return sum(1 for v in verdicts_zone if v == LECTURE_SURE) / len(verdicts_zone)
