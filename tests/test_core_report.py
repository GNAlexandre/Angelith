# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Squelette commun des `RAPPORT.md` (`core/report.py`, lot 2.6).

Le *contenu* des deux rapports n'a presque rien en commun ; leur squelette, si — et il avait
déjà divergé. Ces tests portent sur les points de divergence, pas sur la mise en forme.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.report import ecrire, entete_run, lignes_llm, section, tronquer
from core.version import __version__

RACINE = Path(__file__).resolve().parents[1]


def test_lentete_porte_la_version_du_depot():
    """Un tome se relance des semaines plus tard : savoir avec quelle version il a été
    produit est la première question."""
    lignes = entete_run(0)
    assert f"- Version : {__version__}" in lignes


def test_lentete_porte_lheure_de_fin():
    """Pas un ornement : un tome de 150 planches se lance en run de nuit, et « quand ça s'est
    terminé » est ce qu'on cherche le matin."""
    assert any(re.fullmatch(r"- Terminé le : \d{4}-\d{2}-\d{2} à \d{2}h\d{2}", l)
               for l in entete_run(None))


def test_la_duree_est_omise_si_inconnue():
    """Un rapport partiel (arrêt propre) peut ne pas avoir de durée à annoncer ; « 0min 0s »
    serait faux."""
    assert not any("Durée" in l for l in entete_run(None))
    assert "- Durée totale : 2min 5s" in entete_run(125.9)


# --- statistiques LLM ------------------------------------------------------------


def test_un_agregat_a_zero_dit_quil_ny_a_rien_a_mesurer():
    """« Appels LLM : 0 · ~0 tok/s » se lit comme une MESURE, alors que c'est une absence de
    mesure — le cas d'une reprise entièrement en cache. Les deux briques affichaient là deux
    formulations différentes, dont l'une était mensongère."""
    for stats in (None, {}, {"appels": 0, "temps_generation": 0, "tokens_generes": 0}):
        lignes = lignes_llm(stats)
        assert lignes == ["- (dry-run ou aucun appel — pas de statistique LLM)"], stats


def test_la_vitesse_est_calculee_sur_lagregat():
    lignes = lignes_llm({"appels": 3, "tokens_generes": 900, "temps_generation": 30.0})
    assert "Appels LLM : 3" in lignes[0]
    assert "~30 tok/s" in lignes[0]


def test_pas_de_division_par_zero_si_le_temps_est_nul():
    """Cas réel : des appels comptés mais un temps de génération à zéro (réponses toutes
    servies depuis un cache côté serveur, ou horloge trop grossière)."""
    lignes = lignes_llm({"appels": 2, "tokens_generes": 10, "temps_generation": 0})
    assert "Appels LLM : 2" in lignes[0] and "~0 tok/s" in lignes[0]


def test_le_budget_de_generation_napparait_que_sil_a_ete_depasse():
    base = {"appels": 1, "tokens_generes": 10, "temps_generation": 1.0}
    assert len(lignes_llm(base)) == 1
    avec = lignes_llm({**base, "thinking_overflow": 2})
    assert len(avec) == 2 and "thinking" in avec[1]


def test_les_incidents_reseau_sont_mentionnes_quand_il_y_en_a():
    base = {"appels": 1, "tokens_generes": 10, "temps_generation": 1.0}
    assert "réseau" not in lignes_llm(base)[0]
    assert "1 tentative(s) réseau/vide" in lignes_llm({**base, "retries": 1})[0]


# --- troncature ------------------------------------------------------------------


def test_tronquer_ne_touche_pas_une_liste_assez_courte():
    assert tronquer(["a", "b"], 5) == ["a", "b"]


def test_tronquer_annonce_ce_qui_a_ete_coupe():
    """Taire le reste rendrait le rapport mensonger ; tout afficher le noierait."""
    out = tronquer([str(i) for i in range(10)], 3)
    assert out[:3] == ["0", "1", "2"]
    assert out[-1] == "(… 7 autre(s))"


def test_une_section_vide_ne_produit_aucun_titre():
    """Sinon dix titres « 0 problème » précéderaient l'information utile."""
    assert section("Titre", [], 5) == []


def test_une_section_annonce_son_compte_total_pas_le_tronque():
    """Le compte du titre doit être le VRAI nombre : « (3) » sur une section tronquée à 2
    laisserait croire qu'on voit tout."""
    bloc = section("Débordements", ["a", "b", "c"], 2)
    assert bloc[0] == "## Débordements (3)"
    assert bloc[-2] == "- (… 1 autre(s))"


def test_ecrire_cree_larborescence(tmp_path):
    chemin = ecrire(tmp_path / "a" / "b", "contenu")
    assert chemin.name == "RAPPORT.md"
    assert chemin.read_text(encoding="utf-8") == "contenu"


# --- non-régression de couche ----------------------------------------------------


def test_les_deux_briques_passent_par_le_socle():
    """Garde-fou contre la redivergence : c'est en réécrivant la ligne « Appels LLM » à la
    main de chaque côté que les deux formulations avaient fini par différer."""
    for chemin in (RACINE / "pipeline" / "orchestrator.py",
                   RACINE / "manga" / "report_manga.py"):
        src = chemin.read_text(encoding="utf-8")
        assert "report.lignes_llm(" in src, chemin.name
        assert "- Appels LLM :" not in src, f"{chemin.name} reformate la ligne à la main"
