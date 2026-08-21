# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de formatting.py : détection de la taille du corps de texte et regroupement
des tailles de titre en paliers (Chapitre / Partie), partagés PDF+DOCX."""
from pipeline.formatting import body_size, cluster_heading_tiers


def test_body_size_picks_dominant_weighted_size():
    sizes = [(15.0, 7000), (13.0, 400), (17.2, 40), (24.7, 12)]
    assert body_size(sizes) == 15.0


def test_body_size_falls_back_to_weighted_median_without_clear_majority():
    """Distribution fragmentée : aucune taille ne dépasse 15 % du poids total (10
    tailles à 10 % chacune) → repli sur la médiane pondérée plutôt que le mode brut."""
    sizes = [(float(i), 10) for i in range(1, 11)]  # 1.0..10.0, poids égal
    assert body_size(sizes) == 5.0


def test_body_size_empty_returns_zero():
    assert body_size([]) == 0.0


def test_cluster_heading_tiers_roman_c_like_two_tiers():
    """Motif réel (roman C Vol.1) : corps 15.0pt, titres à 17.2pt (Partie) et 24.7pt
    (Chapitre) — les deux paliers doivent ressortir, triés du plus grand au plus petit."""
    bold_sizes = [24.7] * 12 + [17.2] * 38
    tiers = cluster_heading_tiers(bold_sizes, body=15.0, ratio=1.10)
    assert len(tiers) == 2
    assert tiers[0] > tiers[1]
    assert round(tiers[0], 1) == 24.7
    assert round(tiers[1], 1) == 17.2


def test_cluster_heading_tiers_merges_near_duplicate_sizes():
    bold_sizes = [20.0, 20.1, 19.9, 14.0, 14.2]
    tiers = cluster_heading_tiers(bold_sizes, body=12.0, ratio=1.10, merge_eps=0.5)
    assert len(tiers) == 2


def test_cluster_heading_tiers_truncates_to_max_tiers():
    bold_sizes = [30.0] * 5 + [22.0] * 5 + [16.0] * 5
    tiers = cluster_heading_tiers(bold_sizes, body=12.0, ratio=1.10, max_tiers=2)
    assert len(tiers) == 2
    assert round(tiers[0]) == 30 and round(tiers[1]) == 22


def test_cluster_heading_tiers_below_threshold_excluded():
    bold_sizes = [12.5, 12.8]  # pas assez au-dessus du corps (12.0 * 1.10 = 13.2)
    tiers = cluster_heading_tiers(bold_sizes, body=12.0, ratio=1.10)
    assert tiers == []


def test_cluster_heading_tiers_zero_body_returns_empty():
    assert cluster_heading_tiers([20.0], body=0.0, ratio=1.10) == []
