# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Détection de titres par mise en forme (taille de police + gras), partagée entre
l'extraction PDF (PyMuPDF, spans) et DOCX (python-docx, runs) — voir `extract.py`.

Seule la partie NUMÉRIQUE est mutualisée ici : PyMuPDF et python-docx exposent des
formes de données trop différentes (spans vs runs, avec/sans notion de bloc/page)
pour qu'un parcours commun simplifie réellement les choses.
"""
from __future__ import annotations

from collections import defaultdict


def body_size(sizes: list[tuple[float, int]]) -> float:
    """Taille de police du CORPS DE TEXTE : le mode, pondéré par nombre de caractères
    (pas par nombre de spans/runs — un long paragraphe pèse plus qu'un titre court).
    Repli sur la médiane pondérée si aucune taille ne domine nettement (< 15 % du
    total) — motif possible si le texte est fragmenté en beaucoup de petits spans."""
    if not sizes:
        return 0.0
    totals: dict[float, int] = defaultdict(int)
    total_weight = 0
    for size, weight in sizes:
        totals[round(size, 1)] += weight
        total_weight += weight
    if total_weight == 0:
        return 0.0
    best_size, best_weight = max(totals.items(), key=lambda kv: kv[1])
    if best_weight / total_weight >= 0.15:
        return best_size
    ordered = sorted(sizes, key=lambda t: t[0])
    half = total_weight / 2
    cum = 0
    for size, weight in ordered:
        cum += weight
        if cum >= half:
            return size
    return ordered[-1][0]


def cluster_heading_tiers(bold_sizes: list[float], body: float, ratio: float,
                          max_tiers: int = 2, merge_eps: float = 0.5) -> list[float]:
    """Tailles de titre candidates (gras) au-dessus du corps de texte, regroupées en
    paliers (des tailles à `merge_eps` près sont le même palier), triées du plus
    grand (Chapitre) au plus petit (Partie), tronquées à `max_tiers` — au-delà, un
    palier supplémentaire n'est pas retenu comme niveau de découpage (il reste du
    texte littéral, cf. `split.py`)."""
    if body <= 0:
        return []
    threshold = body * ratio
    filtered = sorted(s for s in bold_sizes if s >= threshold)
    if not filtered:
        return []
    clusters: list[list[float]] = [[filtered[0]]]
    for s in filtered[1:]:
        if s - clusters[-1][-1] <= merge_eps:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    tiers = sorted((sum(c) / len(c) for c in clusters), reverse=True)
    return tiers[:max_tiers]
