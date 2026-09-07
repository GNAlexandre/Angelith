# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Instrument de mesure des variantes (`tools/compter_variantes.py`), à 0 % jusqu'ici.

## Pourquoi ce fichier existe

Le module le dit de lui-même : « un instrument de mesure qui ne compte pas comme compte ce
qu'il mesure ne vaut rien ». Il en découle deux propriétés qu'aucun test ne tenait, et dont
la seconde est la plus facile à casser sans s'en apercevoir —

- **le français mesuré vient de `qa.json`**, c'est-à-dire du texte RÉELLEMENT dessiné sur la
  planche, donc après forçage du glossaire. `traduction.json` garde délibérément la sortie
  brute du modèle ; mesurer ce cache-là ne dirait rien de ce que le lecteur voit, tout en
  produisant des chiffres d'apparence irréprochable. `--brut` fait l'inverse EXPRÈS ;
- **le code de sortie vaut verdict** : une forme bannie encore présente doit faire sortir la
  commande en 1, sinon la mesure ne sert que si quelqu'un lit l'écran.
"""
from __future__ import annotations

import sys

import pytest

from tools import compter_variantes as cv

GLOSSAIRE_FORCE = {
    "personnages": [
        {"nom": "Leprechaun", "force": True, "interdits": ["lutin", "farfadet"],
         "variantes": ["Leprechaune"]},
        {"nom": "Sans forçage", "interdits": ["ignoré"]},      # pas de `force: true`
    ],
    "termes": [{"nom": "", "force": True}],                    # nom vide : ignoré
}


# --- _familles -------------------------------------------------------------------

def test_seules_les_entrees_forcees_forment_une_famille():
    """`force: true` est ce qui autorise un remplacement automatique. Une entrée sans lui a
    des `interdits` purement indicatifs — les compter comme des fautes serait faux."""
    familles = dict(cv._familles(GLOSSAIRE_FORCE))
    assert set(familles) == {"Leprechaun"}


def test_variantes_et_interdits_sont_bannis_ensemble_sauf_le_nom_lui_meme():
    familles = dict(cv._familles(GLOSSAIRE_FORCE))
    assert sorted(familles["Leprechaun"]) == ["Leprechaune", "farfadet", "lutin"]


def test_le_nom_canonique_ne_se_bannit_pas_lui_meme():
    """Une entrée qui se liste dans ses propres variantes se déclarerait éternellement
    fautive : chaque occurrence correcte compterait comme un reste."""
    glo = {"personnages": [{"nom": "Roi-démon", "force": True,
                            "variantes": ["roi-démon", "Roi-démon"]}]}
    assert cv._familles(glo) == [("Roi-démon", [])]


def test_un_glossaire_vide_ne_donne_aucune_famille():
    assert cv._familles({}) == []


# --- _rapport_glossaire ----------------------------------------------------------

def test_sans_entree_forcee_le_rapport_le_dit_et_ne_compte_rien(capsys):
    assert cv._rapport_glossaire(["du texte"], {}) == 0
    assert "Aucune entrée `force: true`" in capsys.readouterr().out


def test_un_texte_propre_ne_laisse_aucune_occurrence_residuelle(capsys):
    textes = ["Le Leprechaun rit.", "Un autre Leprechaun passe."]
    assert cv._rapport_glossaire(textes, GLOSSAIRE_FORCE) == 0
    sortie = capsys.readouterr().out
    assert "✓ Leprechaun" in sortie
    assert "RESTE" not in sortie


def test_une_forme_bannie_encore_presente_est_comptee_et_nommee(capsys):
    """Le chiffre EST le verdict : c'est lui que `main` transforme en code de sortie."""
    textes = ["Le lutin rit.", "Un farfadet passe.", "Un autre lutin."]
    assert cv._rapport_glossaire(textes, GLOSSAIRE_FORCE) == 3
    sortie = capsys.readouterr().out
    assert "✗ Leprechaun" in sortie
    assert "lutin ×2" in sortie and "farfadet ×1" in sortie


# --- _lire_tome : la source du français ------------------------------------------

class _Planche:
    def __init__(self, numero, ocr, traduction, qa):
        self.numero, self.ocr, self.traduction, self.qa = numero, ocr, traduction, qa


@pytest.fixture
def tome(monkeypatch):
    """Une planche dont `qa.json` et `traduction.json` DIVERGENT — c'est tout le sujet."""
    planches = [_Planche(
        1, ["レプラコーン"], ["Le lutin rit."],
        {"bulles": [{"traduction": "Le Leprechaun rit."}]})]
    monkeypatch.setattr(cv._banc_commun, "planches", lambda build: planches)
    return planches


def test_le_francais_mesure_est_celui_reellement_dessine(tome):
    """⚠ LE point du module. `qa.json` porte le texte d'APRÈS forçage ; mesurer
    `traduction.json` annoncerait une faute que le lecteur ne voit pas."""
    pages = list(cv._lire_tome("build"))
    assert pages == [(1, ["レプラコーン"], ["Le Leprechaun rit."])]


def test_le_mode_brut_mesure_la_sortie_du_modele(tome):
    """Le pendant, et il est délibéré : comparer l'avant/après forçage."""
    pages = list(cv._lire_tome("build", brut=True))
    assert pages == [(1, ["レプラコーン"], ["Le lutin rit."])]


def test_sans_qa_on_retombe_sur_la_traduction(monkeypatch):
    """Une planche non encore rendue n'a pas de `qa.json` : la mesure continue sur ce
    qu'elle a, plutôt que de sauter la page en silence."""
    monkeypatch.setattr(cv._banc_commun, "planches",
                        lambda build: [_Planche(2, ["ドン"], ["Boum"], None)])
    assert list(cv._lire_tome("build")) == [(2, ["ドン"], ["Boum"])]


def test_une_planche_sans_rien_est_sautee(monkeypatch):
    monkeypatch.setattr(cv._banc_commun, "planches",
                        lambda build: [_Planche(3, ["ドン"], None, None)])
    assert list(cv._lire_tome("build")) == []


# --- les deux rapports d'exploration ---------------------------------------------

def test_les_derives_non_encore_bannies_sont_proposees_sans_rien_ecrire(capsys):
    """« 0 forme bannie » est exact ET trompeur : les `interdits` listent les fautes des runs
    PRÉCÉDENTS. Ce rapport montre ce que le pipeline écrirait — sans l'écrire."""
    glo = {"personnages": [{"nom": "Kataphrakte", "force": True,
                            "termes_source": ["カタフラクト"]}]}
    pages = [(1, ["カタフラクト"], ["Le Kataphrakto avance."])]
    cv._rapport_derives(["Le Kataphrakto avance."], glo, pages)
    sortie = capsys.readouterr().out
    assert "Dérives NON encore bannies" in sortie
    assert "Kataphrakto" in sortie and "[T1]" in sortie
    assert glo["personnages"][0].get("interdits") is None, "l'outil est en LECTURE SEULE"


def test_sans_aucune_derive_le_rapport_le_dit_explicitement(capsys):
    cv._rapport_derives(["Rien de particulier."], {}, [(1, [], ["Rien de particulier."])])
    assert "(aucune)" in capsys.readouterr().out


def test_le_mode_exploratoire_groupe_les_orthographes_proches(capsys):
    textes = ["Le Kataphrakto avance.", "Un Kataphrakte passe.", "Encore un Kataphrakto."]
    cv._rapport_exploratoire(textes, [(1, [], textes)])
    sortie = capsys.readouterr().out
    assert "Groupes de mots capitalisés proches" in sortie
    assert "Kataphrakto" in sortie and "Kataphrakte" in sortie


def test_le_mode_exploratoire_relie_une_source_katakana_a_ses_rendus(capsys):
    """Le signal le plus net : la MÊME bulle source rendue de plusieurs façons."""
    pages = [(1, ["カタフラクト"], ["Le Kataphrakto."]),
             (2, ["カタフラクト"], ["Le Kataphrakte."]),
             (3, ["カタフラクト"], ["Le Kataphrakto encore."])]
    cv._rapport_exploratoire([t for _p, _o, tr in pages for t in tr], pages)
    sortie = capsys.readouterr().out
    assert "orthographes latines différentes" in sortie
    assert "カタフラクト" in sortie


# --- main ------------------------------------------------------------------------

def _lancer(monkeypatch, *argv):
    monkeypatch.setattr(cv, "configurer_stdout", lambda: None)
    monkeypatch.setattr(sys, "argv", ["compter_variantes.py", *argv])
    return cv.main()


def test_sans_argument_l_aide_sort_en_2(monkeypatch, capsys):
    assert _lancer(monkeypatch) == 2
    assert "compter_variantes" in capsys.readouterr().out.lower()


def test_un_tome_absent_le_dit_et_sort_en_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cv, "charger_config", lambda chemin: {})
    monkeypatch.setattr(cv._banc_commun, "racine_build", lambda config: tmp_path / "build")
    assert _lancer(monkeypatch, "Mon Manga", "Vol.1") == 1
    assert "Rien à mesurer" in capsys.readouterr().out


def _preparer(monkeypatch, tmp_path, glossaire: dict | None, qa_texte: str):
    build = tmp_path / "build" / "Mon Manga" / "Vol.1" / "manga"
    build.mkdir(parents=True)
    monkeypatch.setattr(cv, "charger_config", lambda chemin: {})
    monkeypatch.setattr(cv._banc_commun, "racine_build", lambda config: tmp_path / "build")
    monkeypatch.setattr(cv._banc_commun, "racine_sources", lambda config: tmp_path / "sources")
    monkeypatch.setattr(cv.core_config, "section", lambda *a, **k: {})
    monkeypatch.setattr(cv._banc_commun, "planches", lambda b: [
        _Planche(1, ["レプラコーン"], [qa_texte], {"bulles": [{"traduction": qa_texte}]})])
    monkeypatch.setattr(cv.glossary, "load", lambda p: glossaire)


def test_une_forme_bannie_fait_sortir_la_commande_en_1(monkeypatch, tmp_path, capsys):
    """Le code de sortie EST le verdict : sans lui, la mesure ne sert que si on lit l'écran."""
    _preparer(monkeypatch, tmp_path, GLOSSAIRE_FORCE, "Le lutin rit.")
    assert _lancer(monkeypatch, "Mon Manga", "Vol.1") == 1
    assert "RESTE" in capsys.readouterr().out


def test_un_tome_propre_sort_en_0(monkeypatch, tmp_path, capsys):
    _preparer(monkeypatch, tmp_path, GLOSSAIRE_FORCE, "Le Leprechaun rit.")
    assert _lancer(monkeypatch, "Mon Manga", "Vol.1") == 0
    assert "texte réellement dessiné" in capsys.readouterr().out


def test_sans_glossaire_on_bascule_en_mode_exploratoire(monkeypatch, tmp_path, capsys):
    _preparer(monkeypatch, tmp_path, None, "Le Kataphrakto avance.")
    assert _lancer(monkeypatch, "Mon Manga", "Vol.1") == 0
    sortie = capsys.readouterr().out
    assert "mode exploratoire" in sortie
    assert "Groupes de mots capitalisés proches" in sortie


def test_le_drapeau_brut_change_la_source_annoncee(monkeypatch, tmp_path, capsys):
    _preparer(monkeypatch, tmp_path, GLOSSAIRE_FORCE, "Le Leprechaun rit.")
    assert _lancer(monkeypatch, "Mon Manga", "Vol.1", "--brut") == 0
    assert "sortie BRUTE du modèle" in capsys.readouterr().out
