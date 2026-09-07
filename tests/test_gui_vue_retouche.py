# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que la destination « Retouche » dit (`gui/vue_retouche.py`) — **sans Qt**.

Quatre phrases, et chacune vient d'une mesure du lot 35 :

| Fonction | Ce qu'elle empêche |
|---|---|
| `phrase_tomes_absents` | une liste filtrée qu'on croit complète |
| `motif_de_verrou` | un panneau gris qui ne dit pas pour combien de temps |
| `ligne_de_cache` / `infobulle_de_cache` | un coût mémoire que rien n'affiche |
| `libelle_retouche` | un chiffre sans dénominateur sur un bouton |
"""
from __future__ import annotations

from gui import vue_retouche as vue

MO = 1024 * 1024


# --------------------------------------------------------------------------- #
#  L35.1 — pourquoi ce tome n'est pas dans la liste
# --------------------------------------------------------------------------- #

def test_rien_a_dire_quand_tous_les_tomes_sont_editables():
    """Une ligne permanente qui dit « tout est là » est du décor, et le décor cesse d'être lu
    avant l'avertissement qu'il entoure."""
    assert vue.phrase_tomes_absents([]) == ""


def test_un_tome_absent_est_nomme_et_la_raison_est_dite():
    phrase = vue.phrase_tomes_absents(["Vol.2"])
    assert "Vol.2" in phrase
    assert "PLANCHES" in phrase and "light novel" in phrase
    assert "apparaît" in phrase, "singulier"


def test_plusieurs_tomes_absents_accordent_le_verbe():
    assert "apparaissent" in vue.phrase_tomes_absents(["Vol.2", "Vol.3"])


def test_au_dela_de_trois_on_compte_le_reste_plutot_que_de_tout_nommer():
    phrase = vue.phrase_tomes_absents([f"Vol.{n}" for n in range(1, 8)])
    assert "Vol.1" in phrase and "Vol.3" in phrase
    assert "Vol.7" not in phrase
    assert "et 4 autres" in phrase


# --------------------------------------------------------------------------- #
#  L35.5 — le verrou porte son motif
# --------------------------------------------------------------------------- #

def _etat(**kw) -> dict:
    base = {"phase_libelle": "Traduction et rendu", "rang": 5, "phases": 6,
            "courant": 84, "total": 131, "unite": "planche"}
    base.update(kw)
    return base


def test_le_motif_nomme_le_tome_l_etape_et_l_avancement():
    """C'est l'exemple du `PLAN-35` L35.5, mot pour mot."""
    motif = vue.motif_de_verrou(_etat(), "Manga · Mon Manga / Vol.2")
    assert "Mon Manga / Vol.2" in motif
    assert "Traduction et rendu (5/6)" in motif
    assert "planche 84/131" in motif
    assert motif.endswith("affichage seul")


def test_sans_cible_il_n_y_a_rien_a_dire():
    assert vue.motif_de_verrou(_etat(), "") == ""


def test_une_tache_sans_phases_n_invente_aucun_avancement():
    """Un import de glossaire, une copie de sources : le motif se réduit, il ne se remplit
    pas d'un compte emprunté."""
    motif = vue.motif_de_verrou({}, "Mon Manga / Vol.2")
    assert motif == "Verrouillé : run en cours sur Mon Manga / Vol.2 — affichage seul"


def test_une_phase_sans_total_ne_produit_pas_de_compte():
    motif = vue.motif_de_verrou(_etat(total=0), "A / B")
    assert "Traduction et rendu (5/6)" in motif and "/131" not in motif


# --------------------------------------------------------------------------- #
#  L35.3 point 3 — la mémoire mesurée, affichée
# --------------------------------------------------------------------------- #

def test_un_seul_apercu_ne_donne_pas_une_moyenne():
    """« Une estimation fausse est pire que pas d'estimation » — même règle que
    `gui/avancement.MINIMUM`."""
    assert vue.ligne_de_cache(1, 35 * MO, 120 * MO, 9) == ""


def test_la_ligne_porte_le_poids_le_plafond_et_le_cout_unitaire():
    ligne = vue.ligne_de_cache(3, 105 * MO, 120 * MO, 9)
    assert "3/9" in ligne
    assert "105.0 Mo sur 120" in ligne
    assert "35.0 Mo pièce" in ligne


def test_la_ligne_ne_promet_pas_moins_que_ce_qu_elle_a():
    """Un cache plus grand que la fenêtre voulue — après un run qui a tout invalidé sauf
    quelques planches — ne doit pas afficher « 12/3 »."""
    assert "12/12" in vue.ligne_de_cache(12, 100 * MO, 120 * MO, 3)


def test_l_infobulle_explique_le_frein_quand_il_agit():
    bulle = vue.infobulle_de_cache(12, 112 * MO, 120 * MO, tenable=12, demandee=21)
    assert "21 planches" in bulle and "ramenée à 12" in bulle
    assert "gui.apercu.plafond_mo" in bulle


def test_l_infobulle_le_dit_aussi_quand_le_frein_n_agit_pas():
    bulle = vue.infobulle_de_cache(11, 40 * MO, 120 * MO, tenable=33, demandee=11)
    assert "tient entièrement dedans" in bulle
    assert "ramenée" not in bulle


# --------------------------------------------------------------------------- #
#  L35.2 — le bouton « Retoucher » du bilan de run
# --------------------------------------------------------------------------- #

def test_un_run_light_novel_ne_propose_pas_la_retouche():
    """Il n'y a pas d'éditeur light novel dans ce dépôt (L35.6) : le bouton mènerait à une
    destination où le tome n'apparaît même pas dans la liste."""
    assert vue.libelle_retouche("ln", [1, 2, 3]) == ""


def test_le_bouton_porte_le_compte_quand_le_depot_le_connait():
    assert vue.libelle_retouche("manga", [3, 7, 9]) == "Retoucher 3 planches"


def test_une_seule_planche_accorde_le_singulier():
    assert vue.libelle_retouche("manga", [7]) == "Retoucher 1 planche"


def test_un_compte_inconnu_n_est_pas_invente():
    """Un run lancé depuis « Manga » peut toucher n'importe quelle planche : « Retoucher les
    131 planches » serait un chiffre sans dénominateur."""
    assert vue.libelle_retouche("manga", None) == "Retoucher ce tome"


def test_le_webtoon_est_retouchable_comme_le_manga():
    """⚠ La destination « Webtoon » soumet un run de brique `"manga"` : c'est le même
    orchestrateur avec `--format webtoon` (`PLAN-31` L31.7). C'est donc la ligne « manga »
    qui la couvre en pratique ; celle-ci garde la porte ouverte."""
    assert vue.libelle_retouche("manga", None) == "Retoucher ce tome"
    assert vue.libelle_retouche("webtoon", None) == "Retoucher ce tome"


def test_une_brique_inconnue_ne_propose_rien():
    """Le repli est le SILENCE, pas le bouton : un `!= "ln"` rendrait `True` sur tout ce
    qu'on n'aurait pas prévu."""
    assert vue.libelle_retouche("scan", [1]) == ""
    assert vue.libelle_retouche("", [1]) == ""
