# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Quelles planches un run traite (`manga.orchestrator_manga.cibles_de_run`).

La logique de bornes vivait en ligne dans `process_volume` : la vérifier exigeait un
orchestrateur complet, avec ses modèles et son serveur LLM. Elle est désormais pure, et le
cas qu'elle protège mérite d'être verrouillé — `--page 999` ne traitait rien mais allait
quand même au bout, réécrivant `RAPPORT.md` et réencodant le CBZ, si bien qu'une faute de
frappe passait pour un run réussi.
"""
import pytest

from manga.orchestrator_manga import cibles_de_run


def _cibles(*args):
    return cibles_de_run(*args)[0]


def _abandon(*args):
    return cibles_de_run(*args)[2]


def _alertes(*args):
    return cibles_de_run(*args)[1]


# --------------------------------------------------------------------------- #
#  Le chemin nominal
# --------------------------------------------------------------------------- #

def test_sans_restriction_tout_le_tome_est_traite():
    assert _cibles(None, None, 10) is None, "None veut dire tout, pas rien"
    assert _abandon(None, None, 10) is False
    assert _alertes(None, None, 10) == []


def test_une_page_seule():
    assert _cibles(3, None, 10) == {3}


def test_un_ensemble_de_pages():
    assert _cibles(None, {3, 7}, 10) == {3, 7}


def test_l_ensemble_accepte_une_liste_et_des_doublons():
    assert _cibles(None, [3, 7, 3], 10) == {3, 7}


# --------------------------------------------------------------------------- #
#  Les bornes — le défaut historique
# --------------------------------------------------------------------------- #

def test_une_page_hors_bornes_abandonne_sans_rien_reecrire():
    cibles, alertes, abandon = cibles_de_run(999, None, 10)
    assert abandon is True
    assert cibles is None
    assert "10 planche(s)" in alertes[0]


def test_la_page_zero_est_hors_bornes():
    """Les planches sont numérotées à partir de 1 : `--page 0` est une faute de frappe."""
    assert _abandon(0, None, 10) is True


def test_les_bornes_incluent_la_premiere_et_la_derniere():
    assert _cibles(1, None, 10) == {1}
    assert _cibles(10, None, 10) == {10}


def test_une_selection_partiellement_hors_bornes_garde_le_valide_et_previent():
    cibles, alertes, abandon = cibles_de_run(None, {3, 99}, 10)
    assert cibles == {3}
    assert abandon is False
    assert "hors bornes" in alertes[0]


def test_une_selection_entierement_hors_bornes_abandonne():
    cibles, alertes, abandon = cibles_de_run(None, {99, 120}, 10)
    assert abandon is True
    assert cibles is None
    assert any("Aucune planche valide" in a for a in alertes)


def test_une_selection_vide_abandonne():
    assert _abandon(None, set(), 10) is True


# --------------------------------------------------------------------------- #
#  Composition — `--page` ne peut qu'affiner
# --------------------------------------------------------------------------- #

def test_page_et_ensemble_se_composent_par_intersection():
    assert _cibles(3, {3, 7}, 10) == {3}


def test_une_page_hors_de_la_selection_abandonne_au_lieu_de_l_elargir():
    """Sans l'intersection, `--page 5` aurait AJOUTÉ la planche 5 à une sélection qui ne la
    contenait pas — une restriction qui élargit serait un piège."""
    cibles, alertes, abandon = cibles_de_run(5, {3, 7}, 10)
    assert abandon is True
    assert cibles is None
    assert "n'appartient pas" in alertes[0]


@pytest.mark.parametrize("only_page,only_pages,attendu", [
    (None, None, None),
    (2, None, {2}),
    (None, {2}, {2}),
    (2, {2}, {2}),
])
def test_une_page_seule_est_equivalente_a_l_ensemble_qui_ne_contient_qu_elle(
        only_page, only_pages, attendu):
    assert _cibles(only_page, only_pages, 5) == attendu
