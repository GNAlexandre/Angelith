# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Cache par page de la brique scan (`scan/checkpoints.py`).

Un tome coûte ~2 h d'OCR : la seule chose qui rende la brique utilisable est qu'une
interruption ne fasse rien reperdre. Ce fichier vérifie donc surtout des NON-relectures.
"""
from conftest_scan import page
from scan import checkpoints, grille


def _plan_reel():
    return grille.analyser(page([{"cases": 12}, {"cases": 20, "indent": True},
                                 {"cases": 40}, {"cases": 8}, {"cases": 30}],
                                hauteur=1900).image())


# --------------------------------------------------------------------------- #
#  Aller-retour sur disque
# --------------------------------------------------------------------------- #

def test_un_plan_relu_est_identique_a_celui_qu_on_a_ecrit(tmp_path):
    plan = _plan_reel()
    checkpoints.save_plan(tmp_path, plan)
    relu = checkpoints.load_plan(tmp_path)
    assert relu.verdict == plan.verdict
    assert relu.pas == plan.pas
    assert relu.seuil == plan.seuil
    assert len(relu.colonnes) == len(plan.colonnes)
    for avant, apres in zip(plan.colonnes, relu.colonnes):
        assert (apres.x0, apres.x1, apres.y0, apres.y1) == (avant.x0, avant.x1,
                                                            avant.y0, avant.y1)
        assert apres.coupes == avant.coupes
        assert apres.indentee == avant.indentee
        assert apres.cases == avant.cases
        assert apres.genre == avant.genre


def test_les_ruby_survivent_a_l_aller_retour(tmp_path):
    plan = _plan_reel()
    plan.colonnes[0].ruby = [(10, 20, 30, 40)]
    checkpoints.save_plan(tmp_path, plan)
    relu = checkpoints.load_plan(tmp_path)
    assert relu.colonnes[0].ruby == [(10, 20, 30, 40)]


def test_le_texte_fait_un_aller_retour_fidele(tmp_path):
    colonnes = [{"texte": "あい", "tranches": ["あ", "い"], "ruby": ["よみ"],
                 "suspecte": True, "relue": False}]
    checkpoints.save_texte(tmp_path, colonnes)
    assert checkpoints.load_texte(tmp_path) == colonnes


# --------------------------------------------------------------------------- #
#  Tolérance aux caches abîmés
# --------------------------------------------------------------------------- #

def test_un_cache_absent_rend_none(tmp_path):
    assert checkpoints.load_plan(tmp_path) is None
    assert checkpoints.load_texte(tmp_path) is None


def test_un_cache_abime_rend_none_au_lieu_d_exploser(tmp_path):
    """Un cache est une optimisation : une interruption au mauvais moment doit faire refaire
    la page, pas condamner le tome."""
    (tmp_path / checkpoints.PLAN_FILENAME).write_text("{ ceci n'est pas", encoding="utf-8")
    (tmp_path / checkpoints.TEXTE_FILENAME).write_text("", encoding="utf-8")
    assert checkpoints.load_plan(tmp_path) is None
    assert checkpoints.load_texte(tmp_path) is None


def test_un_format_perime_est_ignore(tmp_path):
    checkpoints.save_plan(tmp_path, _plan_reel())
    fichier = tmp_path / checkpoints.PLAN_FILENAME
    fichier.write_text(fichier.read_text(encoding="utf-8").replace(
        f'"format": {checkpoints.FORMAT_VERSION}', '"format": 99'), encoding="utf-8")
    assert checkpoints.load_plan(tmp_path) is None


# --------------------------------------------------------------------------- #
#  Quelles étapes refaire
# --------------------------------------------------------------------------- #

def test_un_cache_vide_fait_tout_refaire(tmp_path):
    assert checkpoints.etapes_a_refaire(tmp_path) == {"analyse", "lecture"}


def test_un_cache_complet_ne_fait_rien_refaire(tmp_path):
    checkpoints.save_plan(tmp_path, _plan_reel())
    checkpoints.save_texte(tmp_path, [])
    assert checkpoints.etapes_a_refaire(tmp_path) == set()


def test_une_analyse_seule_laisse_la_lecture_a_faire(tmp_path):
    checkpoints.save_plan(tmp_path, _plan_reel())
    assert checkpoints.etapes_a_refaire(tmp_path) == {"lecture"}


def test_refaire_l_analyse_perime_toujours_la_lecture(tmp_path):
    """La chaîne est linéaire, à la différence du graphe d'étapes du manga : on ne peut pas
    lire des tranches sans savoir où couper."""
    checkpoints.save_plan(tmp_path, _plan_reel())
    checkpoints.save_texte(tmp_path, [])
    assert checkpoints.etapes_a_refaire(tmp_path, depuis="analyse") == {"analyse", "lecture"}


def test_depuis_lecture_epargne_l_analyse(tmp_path):
    checkpoints.save_plan(tmp_path, _plan_reel())
    checkpoints.save_texte(tmp_path, [])
    assert checkpoints.etapes_a_refaire(tmp_path, depuis="lecture") == {"lecture"}


def test_force_refait_tout_meme_avec_un_cache_complet(tmp_path):
    checkpoints.save_plan(tmp_path, _plan_reel())
    checkpoints.save_texte(tmp_path, [])
    assert checkpoints.etapes_a_refaire(tmp_path, force=True) == {"analyse", "lecture"}


def test_une_lecture_orpheline_fait_refaire_l_analyse(tmp_path):
    """Le texte sans le plan est inexploitable : on ne saurait plus à quelle colonne
    rattacher quoi."""
    checkpoints.save_texte(tmp_path, [])
    assert checkpoints.etapes_a_refaire(tmp_path) == {"analyse", "lecture"}


def test_les_dossiers_de_page_sont_numerotes_sur_quatre_chiffres(tmp_path):
    assert checkpoints.page_checkpoint_dir(tmp_path, 7).name == "page_0007"
    assert checkpoints.page_checkpoint_dir(tmp_path, 1234).name == "page_1234"
