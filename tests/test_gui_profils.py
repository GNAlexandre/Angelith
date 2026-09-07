# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les profils de lancement — **critère 8 du `PLAN-33`**, deuxième moitié.

Miroir de `tests/test_gui_reglages.py`, avec la même exigence centrale : `nettoyer()` retire
les clés interdites **quoi qu'on lui donne, y compris un fichier écrit à la main**. C'est le
seul barrage que ni le formulaire ni l'appelant ne peuvent tenir.

Aucun import Qt.
"""
import json

import pytest

from gui import parametres as par
from gui import profils as prf


@pytest.fixture(autouse=True)
def _isoler(tmp_path, monkeypatch):
    """Chaque test écrit dans son `tmp_path`. ⚠ Sans ça, le premier `ecrire()` poserait un
    `.angelith/profils.json` à la racine du dépôt de qui lance la suite."""
    monkeypatch.setenv(prf.VARIABLE, str(tmp_path / "profils.json"))


def _valeurs(**over):
    base = {"verbose": True, "lot": 12, "think": "high", "keep_awake": True,
            "shutdown_delay": 300, "depuis": "rendu"}
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
#  L'aller-retour
# --------------------------------------------------------------------------- #

def test_un_profil_fait_l_aller_retour_par_le_fichier():
    prf.enregistrer("nuit complète", par.MANGA, _valeurs())
    relus = prf.pour(par.MANGA)
    assert [p.nom for p in relus] == ["nuit complète"]
    assert relus[0].valeurs["lot"] == 12
    assert relus[0].valeurs["think"] == "high"
    assert relus[0].valeurs["keep_awake"] is True


def test_un_profil_est_lie_a_son_panneau():
    """« lot de 20 planches » n'a aucun sens côté light novel, qui ne connaît pas les
    planches — c'est la raison qui a fait passer `runs` à un dictionnaire par destination au
    lot 31."""
    prf.enregistrer("nuit complète", par.MANGA, _valeurs())
    prf.enregistrer("nuit complète", par.LIGHT_NOVEL, {"verbose": False})
    assert len(prf.pour(par.MANGA)) == 1
    assert len(prf.pour(par.LIGHT_NOVEL)) == 1
    assert prf.pour(par.LIGHT_NOVEL)[0].valeurs == {"verbose": False}
    # …et enregistrer l'un n'a pas effacé l'autre, bien qu'ils portent le même nom.
    assert prf.pour(par.MANGA)[0].valeurs["lot"] == 12


def test_reenregistrer_remplace_au_lieu_d_empiler():
    prf.enregistrer("reprise", par.MANGA, _valeurs(lot=1))
    prf.enregistrer("reprise", par.MANGA, _valeurs(lot=20))
    assert len(prf.pour(par.MANGA)) == 1
    assert prf.pour(par.MANGA)[0].valeurs["lot"] == 20


def test_supprimer_retire_le_bon_profil():
    prf.enregistrer("a", par.MANGA, _valeurs())
    prf.enregistrer("b", par.MANGA, _valeurs())
    prf.supprimer("a", par.MANGA)
    assert [p.nom for p in prf.pour(par.MANGA)] == ["b"]


def test_un_nom_vide_est_refuse():
    prf.enregistrer("   ", par.MANGA, _valeurs())
    assert prf.pour(par.MANGA) == ()


def test_un_panneau_inconnu_est_refuse():
    prf.enregistrer("x", "onglet_fantome", _valeurs())
    assert prf.lire() == ()


# --------------------------------------------------------------------------- #
#  Critère 8 — ce qu'un profil n'a JAMAIS le droit de porter
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("panneau", [par.LIGHT_NOVEL, par.MANGA, par.WEBTOON])
def test_un_profil_ne_porte_ni_force_ni_dry_run_ni_shutdown(panneau):
    """⚠ Un profil est **pire** qu'un fichier de réglages sur ce point : il se rappelle
    exprès, et sous un nom rassurant. « Nuit complète » qui rearme `--force` détruirait un
    cache que personne n'a demandé de refaire."""
    prf.enregistrer("nuit complète", panneau,
                    {"verbose": True, "force": True, "dry_run": True, "shutdown": True})
    valeurs = prf.pour(panneau)[0].valeurs
    assert valeurs == {"verbose": True}, panneau


def test_un_profil_ne_porte_ni_projet_ni_tome():
    """« Un profil qui se souvient d'un tome est un raccourci qui lance le mauvais run » —
    la seule erreur de la liste qui ne coûte pas du GPU mais un tome écrasé."""
    prf.enregistrer("x", par.MANGA,
                    {"verbose": True, "projet": "Mon Manga", "tome": "Vol.2"})
    assert prf.pour(par.MANGA)[0].valeurs == {"verbose": True}


def test_un_fichier_ECRIT_A_LA_MAIN_est_lave_a_la_lecture(tmp_path):
    """⚠ **Le barrage que ni le formulaire ni l'appelant ne peuvent tenir**, et le seul motif
    pour lequel `nettoyer()` est appelée aux DEUX bouts.

    C'est le test que `tests/test_gui_reglages.py` fait déjà pour les réglages, étendu aux
    profils comme le `PLAN-33` L33.4 l'exige."""
    charge = {"version": prf.VERSION,
              "profils": [{"nom": "piège", "panneau": par.MANGA,
                           "valeurs": {"force": True, "dry_run": True, "shutdown": True,
                                       "projet": "Mon Manga", "tome": "Vol.2",
                                       "verbose": True, "lot": 20}}]}
    (tmp_path / "profils.json").write_text(json.dumps(charge), encoding="utf-8")
    profil = prf.pour(par.MANGA)[0]
    assert profil.nom == "piège"
    assert profil.valeurs == {"verbose": True, "lot": 20}
    assert "force" not in profil.valeurs and "shutdown" not in profil.valeurs


def test_une_cle_inconnue_du_panneau_est_ecartee():
    """Un profil ne doit pas transporter des clés que le formulaire ne saura pas reposer :
    elles resteraient dans le fichier, invisibles, et une clé homonyme ajoutée demain les
    ferait ressurgir avec une valeur que personne n'a choisie."""
    prf.enregistrer("x", par.MANGA, {"verbose": True, "clef_inventee": 42})
    assert prf.pour(par.MANGA)[0].valeurs == {"verbose": True}


def test_les_interdits_couvrent_ce_que_la_table_refuse_de_persister():
    for panneau in par.PANNEAUX:
        assert par.non_persistes(panneau) <= prf.interdits(panneau), panneau
        assert prf.CIBLE <= prf.interdits(panneau), panneau


# --------------------------------------------------------------------------- #
#  Robustesse — un fichier abîmé ne doit pas empêcher de lancer un run
# --------------------------------------------------------------------------- #

def test_un_fichier_illisible_rend_une_liste_vide(tmp_path):
    (tmp_path / "profils.json").write_text("{ pas du json", encoding="utf-8")
    assert prf.lire() == ()


def test_un_fichier_de_version_inconnue_est_ignore_en_bloc(tmp_path):
    """Même arbitrage que `gui/reglages.py` : des profils perdus coûtent une resaisie, des
    profils à moitié lus coûtent un run lancé avec des réglages que personne n'a choisis."""
    (tmp_path / "profils.json").write_text(
        json.dumps({"version": prf.VERSION + 99, "profils": [{"nom": "x",
                                                              "panneau": par.MANGA}]}),
        encoding="utf-8")
    assert prf.lire() == ()


def test_un_fichier_absent_rend_une_liste_vide():
    assert prf.lire() == ()


def test_ecrire_dans_un_dossier_impossible_ne_leve_pas(monkeypatch, tmp_path):
    """Silencieux sur échec, comme `reglages.ecrire` : un dossier en lecture seule ne doit pas
    empêcher de fermer la fenêtre."""
    cible = tmp_path / "fichier"
    cible.write_text("", encoding="utf-8")
    monkeypatch.setenv(prf.VARIABLE, str(cible / "impossible" / "profils.json"))
    assert prf.ecrire([prf.Profil("x", par.MANGA, {"verbose": True})]) is None


def test_le_nombre_de_profils_est_plafonne():
    for n in range(prf.MAX_PROFILS + 5):
        prf.enregistrer(f"p{n}", par.MANGA, {"verbose": True})
    assert len(prf.lire()) == prf.MAX_PROFILS


# --------------------------------------------------------------------------- #
#  Le résumé affiché
# --------------------------------------------------------------------------- #

def test_le_resume_ne_cite_que_ce_qui_s_ecarte_du_fichier():
    """Un profil dont toutes les valeurs disent « selon config.yaml » ne promet rien, et
    l'écrire en toutes lettres vaut mieux que d'aligner six « selon config.yaml »."""
    assert prf.resume(par.MANGA, {"lot": None, "think": None}) == \
        "Rien qui s'écarte de config.yaml."
    phrase = prf.resume(par.MANGA, {"lot": 20, "think": "high", "keep_awake": True})
    assert "Planches par appel : 20" in phrase
    assert "Raisonnement : high" in phrase
    assert "Empêcher la mise en veille" in phrase


def test_le_resume_ne_cite_jamais_une_cle_interdite():
    """Même si quelqu'un la lui donne : le résumé passe par `nettoyer()`, comme tout le reste."""
    phrase = prf.resume(par.MANGA, {"force": True, "shutdown": True, "lot": 20})
    assert "Tout refaire" not in phrase and "Éteindre" not in phrase
    assert "Planches par appel : 20" in phrase
