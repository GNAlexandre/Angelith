# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les six chemins de perte de travail (`gui/garde.py`) — **sans Qt, sans PySide6**.

Le `PLAN-35` L35.4 demande « une seule implémentation, six appelants ». Ce fichier vérifie la
moitié qui décide ; `tests/test_gui_retouche.py` vérifie les six appelants, avec un écran.

⚠ Ce que ces tests empêchent de revenir, et c'est le vrai risque du lot : **une garde de
plus, posée à chaque changement d'onglet**. Le `PLAN-35` l'écrit sans détour — « un dialogue
qui se pose à chaque changement d'onglet est un dialogue qu'on apprend à cliquer sans lire, et
c'est la façon la plus sûre de perdre du travail avec une garde en place ». Le test qui compte
n'est donc pas celui qui vérifie qu'on demande, c'est celui qui vérifie qu'on **ne demande
pas**.
"""
from __future__ import annotations

import pytest

from gui import garde


def test_les_six_chemins_de_l_etape_0_2_existent():
    """Le tableau du plan et le code doivent se relire ligne à ligne."""
    assert set(garde.CHEMINS) == {"tome", "projet", "destination", "fermeture", "run",
                                  "creation"}


def test_trois_chemins_perdent_le_travail_et_trois_ne_le_perdent_pas():
    assert garde.chemins_gardes() == ["fermeture", "projet", "tome"]


def test_chaque_chemin_porte_son_motif():
    """Un verdict sans motif est un verdict qu'on renversera sans savoir ce qu'il protégeait."""
    for identifiant, chemin in garde.CHEMINS.items():
        assert chemin.motif.strip(), identifiant
        assert chemin.identifiant == identifiant


@pytest.mark.parametrize("identifiant", ["tome", "projet", "fermeture"])
def test_un_chemin_qui_perd_demande_quand_il_y_a_du_travail(identifiant):
    assert garde.doit_demander(identifiant, [1, 4, 7])


@pytest.mark.parametrize("identifiant", ["tome", "projet", "fermeture"])
def test_aucun_chemin_ne_demande_sans_travail_en_attente(identifiant):
    assert not garde.doit_demander(identifiant, [])


@pytest.mark.parametrize("identifiant", ["destination", "run", "creation"])
def test_un_chemin_sans_perte_ne_demande_JAMAIS(identifiant):
    """**Le test qui aurait échoué si le lot avait ajouté une garde de plus.**

    Trente planches en attente, et pas une boîte : changer de destination, lancer un run ou
    créer un projet ne détruit rien — les pages vivent dans un `QStackedWidget`, un run
    verrouille sans jeter, une création n'écrit que sous `sources/` d'un tome neuf."""
    assert not garde.doit_demander(identifiant, list(range(1, 31)))


def test_un_chemin_inconnu_leve_plutot_que_de_laisser_passer():
    """Le mode de panne à éviter est le silencieux : un nom mal orthographié rendrait sinon
    la garde la plus permissive, donc aucune boîte, donc la perte que ce module empêche."""
    with pytest.raises(KeyError):
        garde.doit_demander("onglet", [1])


def test_la_phrase_du_changement_de_tome_nomme_la_cible():
    verbe, consequence = garde.phrase("tome", "Mon Manga / Vol.2")
    assert verbe == "Changer de tome"
    assert "Mon Manga / Vol.2" in consequence


def test_la_phrase_de_fermeture_ne_reclame_aucune_cible():
    verbe, consequence = garde.phrase("fermeture")
    assert verbe == "Quitter"
    assert consequence and "{cible}" not in consequence


def test_changer_de_projet_dit_la_meme_chose_que_changer_de_tome():
    """Les deux perdent le même travail ; deux formulations feraient douter de la garantie."""
    assert garde.phrase("projet", "A / B") == garde.phrase("tome", "A / B")
