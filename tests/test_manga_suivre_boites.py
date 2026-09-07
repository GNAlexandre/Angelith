# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`geometry.suivre_boites` — retrouver une bulle après que les index ont bougé.

C'est la brique qui fait suivre les brouillons de saisie quand une bulle est insérée au milieu
d'une planche : `reading_order` réordonne, donc « la bulle 6 » désigne alors une autre bulle.
L'index n'est pas une identité stable, la géométrie l'est.

Testé sans Qt : la fonction est de la géométrie pure, et PySide6 n'est qu'une dépendance
optionnelle du dépôt.
"""

from manga.edition import SEUIL_REPORT
from manga.geometry import suivre_boites

A = (0, 0, 100, 100)
B = (0, 200, 100, 300)
C = (0, 400, 100, 500)


def test_ordre_inchange():
    assert suivre_boites([A, B], [A, B], SEUIL_REPORT) == {0: 0, 1: 1}


def test_insertion_au_milieu_decale_les_suivantes():
    """LE cas du bug : une bulle apparaît entre les deux, tout ce qui suit glisse d'un cran."""
    assert suivre_boites([A, B], [A, C, B], SEUIL_REPORT) == {0: 0, 1: 2}


def test_suppression_remonte_les_suivantes():
    assert suivre_boites([A, B, C], [A, C], SEUIL_REPORT) == {0: 0, 2: 1}


def test_permutation_complete():
    assert suivre_boites([A, B], [B, A], SEUIL_REPORT) == {0: 1, 1: 0}


def test_une_boite_disparue_est_absente_du_resultat():
    """Rien vaut mieux qu'un faux : ce qui est en jeu est du texte écrit à la main."""
    suivi = suivre_boites([A, B], [A], SEUIL_REPORT)
    assert suivi == {0: 0}
    assert 1 not in suivi


def test_un_leger_redimensionnement_reste_la_meme_bulle():
    presque = (2, 2, 98, 98)
    assert suivre_boites([A], [presque], SEUIL_REPORT) == {0: 0}


def test_sous_le_seuil_on_ne_suit_pas():
    loin = (0, 90, 100, 190)          # ne recouvre A que sur 10 %
    assert suivre_boites([A], [loin], SEUIL_REPORT) == {}


def test_deux_anciennes_ne_peuvent_pas_reclamer_la_meme_nouvelle():
    """Appariement glouton : sans lui, la seconde écraserait la première en silence."""
    proche = (0, 10, 100, 110)
    suivi = suivre_boites([A, proche], [A], SEUIL_REPORT)
    assert list(suivi.values()) == [0]
    assert len(suivi) == 1, "une seule ancienne peut réclamer la nouvelle"


def test_entrees_vides():
    assert suivre_boites([], [A], SEUIL_REPORT) == {}
    assert suivre_boites([A], [], SEUIL_REPORT) == {}


def test_le_meilleur_recouvrement_gagne():
    """À deux candidates, c'est l'IoU qui tranche, pas l'ordre de la liste."""
    exacte, decalee = A, (0, 30, 100, 130)
    assert suivre_boites([A], [decalee, exacte], SEUIL_REPORT) == {0: 1}
