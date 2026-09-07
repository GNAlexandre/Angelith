# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Gardes de chemin (`core/chemins.py`).

Ce module est né du lot Sonar : quatre points du dépôt construisaient un chemin à partir
d'un nom d'œuvre ou d'un chemin de configuration tapé en ligne de commande. Le scénario
d'attaque n'existe pas ici — le programme tourne sur la machine de celui qui a tapé — mais
deux défauts RÉELS se cachaient derrière, et ce sont eux que les tests ci-dessous pinnent :

  · un chemin dérivé n'était vérifié nulle part, donc rien ne garderait la propriété après
    une réécriture de l'appelant ;
  · `exists()` était pris pour « c'est un fichier », et un dossier faisait lever le
    `read_bytes()` suivant avec un message qui ne nomme rien.
"""
from __future__ import annotations

import pytest

from core import chemins


# --- derive ----------------------------------------------------------------------

def test_derive_rend_un_frere_du_fichier(tmp_path):
    base = tmp_path / "sous" / "glossaire.yaml"
    voisin = chemins.derive(base, ".avant-multicibles.bak")
    assert voisin.name == "glossaire.yaml.avant-multicibles.bak"
    assert voisin.parent == base.parent


def test_derive_reproduit_exactement_les_deux_appels_du_depot():
    """Les deux appelants réels — la sauvegarde de glossaire et le temporaire d'écriture
    atomique — écrivaient `with_suffix(p.suffix + …)` et `with_name(p.name + …)`. Deux
    formulations, un seul résultat : c'est ce résultat qu'on fige."""
    from pathlib import PurePosixPath
    glossaire = PurePosixPath("sources/Mon LN/glossaire.yaml")
    assert chemins.derive(glossaire, ".avant-multicibles.bak").name == \
        "glossaire.yaml.avant-multicibles.bak"
    assert chemins.derive(PurePosixPath("build/bloc.md"), ".tmp").name == "bloc.md.tmp"


@pytest.mark.parametrize("suffixe", ["/ailleurs", "\\ailleurs", "../evade", "..", "", " .bak"])
def test_derive_refuse_ce_qui_sortirait_du_dossier(suffixe):
    """Le cœur de la garde. « Ajouter une extension » ne doit jamais pouvoir devenir
    « écrire ailleurs », même si un appelant retouche la constante qu'il passe."""
    with pytest.raises(ValueError):
        chemins.derive("sources/Mon LN/glossaire.yaml", suffixe)


def test_derive_refuse_un_suffixe_qui_ne_change_rien():
    with pytest.raises(ValueError):
        chemins.derive("a/b.yaml", "\x00")


# --- fichier_lisible -------------------------------------------------------------

def test_fichier_lisible_rend_le_chemin_quand_c_est_un_fichier(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("a: 1", encoding="utf-8")
    assert chemins.fichier_lisible(f, "configuration") == f


def test_fichier_lisible_nomme_ce_qui_manque(tmp_path):
    with pytest.raises(RuntimeError, match="configuration introuvable"):
        chemins.fichier_lisible(tmp_path / "absent.yaml", "configuration")


def test_un_dossier_nest_pas_un_fichier_lisible(tmp_path):
    """LE défaut que la fonction supprime : un dossier passe `exists()`, et c'est le
    `read_bytes()` d'après qui lève — `IsADirectoryError` sous Linux, `PermissionError`
    sous Windows, aucun des deux ne nommant le fichier attendu."""
    dossier = tmp_path / "config.yaml"
    dossier.mkdir()
    with pytest.raises(RuntimeError, match="n'est pas un fichier"):
        chemins.fichier_lisible(dossier, "configuration")


def test_l_empreinte_de_config_ne_leve_plus_sur_un_dossier(tmp_path):
    """Le même défaut, chez son appelant : `empreinte_config` testait `exists()` et lançait
    un banc de plusieurs minutes qui tombait au moment d'empreindre."""
    from tools._banc_commun import empreinte_config
    dossier = tmp_path / "config.yaml"
    dossier.mkdir()
    assert empreinte_config(dossier) == "(absente)"


# --- segment ---------------------------------------------------------------------

@pytest.mark.parametrize("nom", ["roman Q", "Vol.1", "roman P", "roman_T",
                                 "Chap.5", "  roman S  "])
def test_un_nom_d_oeuvre_ordinaire_passe(nom):
    assert chemins.segment(nom, "projet") == nom.strip()


@pytest.mark.parametrize("nom", ["../autre", "a/b", r"a\b", "..", ".", "", "   ",
                                 "sources/Mon LN", "C:/Windows"])
def test_un_nom_qui_est_un_chemin_est_refuse(nom):
    """Le cas réel n'est pas une attaque, c'est un collage : on copie « sources/Mon LN »
    depuis l'explorateur au lieu de taper « Mon LN », et la sauvegarde du glossaire part
    ailleurs que là où on croit."""
    with pytest.raises(ValueError):
        chemins.segment(nom, "projet")


def test_le_message_de_refus_nomme_ce_qu_on_attendait():
    with pytest.raises(ValueError, match="tome"):
        chemins.segment("a/b", "tome")


def test_un_projet_en_forme_de_chemin_est_refuse_avant_toute_ecriture(tmp_path):
    """Le garde-fou est à la FRONTIÈRE : la réintégration doit refuser sans avoir touché au
    disque, pas au milieu de l'écriture."""
    from core.glossary_import import reintegrer_dans_projet
    ancien = tmp_path / "ancien.yaml"
    ancien.write_text("termes: []\n", encoding="utf-8")
    config = {"chemins": {"sources": str(tmp_path), "glossaire_fichier": "glossaire.yaml"}}
    with pytest.raises(ValueError):
        reintegrer_dans_projet("../evade", [ancien], config)
    assert not list(tmp_path.glob("**/glossaire.yaml"))
