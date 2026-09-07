# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que la bibliothèque affiche — `gui/vue_oeuvres.py` (lot 34, L34.2). **Sans PySide6.**

⚠ Ce fichier n'importe **ni Qt ni `gui/oeuvres.py`**, et c'est la raison de son existence :
tant que ces fonctions vivaient dans le panneau, leurs tests étaient impossibles à collecter
dans le job de CI qui n'installe pas PySide6 (mesuré le 2026-09-05 : la collecte s'arrêtait en
erreur sur ce seul fichier).

Le test qui porte le critère 10 du plan est `test_l_etat_ne_se_dit_jamais_par_la_couleur_seule`.
"""
from __future__ import annotations

import bibliotheque as biblio
from gui import vue_oeuvres as oe


def _info(**kw) -> biblio.TomeInfo:
    base = {"projet": "P", "tome": "Vol.1", "brique": biblio.MANGA,
            "briques": (biblio.MANGA,), "unites": 3, "unite": "planche",
            "etapes": {e: biblio.FAITE for e in biblio.etapes_de_brique(biblio.MANGA)},
            "statut": "termine", "detail": "3 planche(s)"}
    base.update(kw)
    return biblio.TomeInfo(**base)


def test_une_pastille_par_etape_dans_l_ordre_d_execution():
    info = _info(etapes={"detection": biblio.FAITE, "nettoyage": biblio.PARTIELLE,
                         "ocr": biblio.ABSENTE, "terminologie": biblio.ABSENTE,
                         "traduction": biblio.ABSENTE, "sfx": biblio.ABSENTE,
                         "rendu": biblio.PERIMEE})
    assert oe.pastilles(info) == "●◐○○○○↻"
    assert len(oe.pastilles(info)) == len(biblio.etapes_de_brique(biblio.MANGA))


def test_l_etat_ne_se_dit_jamais_par_la_couleur_seule():
    """**Critère 10.** Chaque état est un CARACTÈRE distinct, et l'infobulle le nomme en
    toutes lettres — c'est ce qu'un lecteur d'écran lit, pas la suite de ronds."""
    marques = [oe.symbole(code) for code in biblio.ETATS_ETAPE]
    assert len(set(marques)) == len(marques), "deux états partagent le même caractère"
    assert "?" not in marques

    info = _info(etapes={"detection": biblio.FAITE, "rendu": biblio.PERIMEE},
                 perimees=(2, 5))
    bulle = oe.detail_avancement(info)
    for etape in biblio.etapes_de_brique(biblio.MANGA):
        assert etape in bulle
    assert "faite" in bulle and "perimee" in bulle
    assert "2, 5" in bulle


def test_la_legende_nomme_les_quatre_etats():
    legende = oe.texte_legende()
    for code, marque, _sens in biblio.LEGENDE_ETATS:
        assert marque in legende
        assert code in legende


def test_le_filtre_de_brique_regarde_TOUTES_les_briques_du_tome():
    """⚠ Un tome qui porte manga ET scan doit apparaître sous les deux — sans quoi filtrer
    sur « Scan » ferait disparaître le seul tome du corpus qui en porte un aux côtés de ses
    planches."""
    mixte = _info(brique=biblio.MANGA, briques=(biblio.MANGA, biblio.SCAN))
    assert oe.retenu(mixte, biblio.MANGA, "", "")
    assert oe.retenu(mixte, biblio.SCAN, "", "")
    assert not oe.retenu(mixte, biblio.LN, "", "")


def test_le_filtre_a_faire_couvre_non_traite_et_partiel():
    assert oe.retenu(_info(statut="non_traite"), "", "a_faire", "")
    assert oe.retenu(_info(statut="partiel"), "", "a_faire", "")
    assert not oe.retenu(_info(statut="termine"), "", "a_faire", "")
    assert oe.retenu(_info(statut="a_relettrer"), "", "a_relettrer", "")


def test_la_recherche_porte_sur_le_titre_et_le_tome():
    info = _info(projet="roman Q", tome="Vol.2")
    # ⚠ Casse DIFFÉRENTE de celle du titre : c'est cela que ce test vérifie, et non qu'une
    # sous-chaîne quelconque corresponde.
    assert oe.retenu(info, "", "", "Roman")
    assert oe.retenu(info, "", "", "VOL.2")
    assert not oe.retenu(info, "", "", "manga A")


def test_le_compte_porte_son_unite_et_dit_ce_qu_il_ignore():
    assert _info(unites=3, unite="planche").compte == "3 planches"
    assert _info(unites=1, unite="planche").compte == "1 planche"
    assert _info(unites=None, unite="chapitre").compte == "? chapitres"
