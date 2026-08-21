# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Verification des cles de `config.yaml` (`core/config.verifier`).

Le defaut vise : le code lit sa configuration a travers 603 `.get(...)` a defaut silencieux.
Ecrire `manga.typeset.font_paht` laisse le run se derouler entierement avec la police par
defaut, sans un mot — et rien ne le rattrape apres coup.

⚠ Le test le PLUS important du fichier est `test_la_reference_colle_au_fichier_reel` : une
reference qui derive produit de FAUX avertissements, ce qui est pire que pas de verification
du tout, parce qu'on cesse alors de les lire.
"""
from pathlib import Path

import yaml

from core import config as cfg
from core.config_schema import CLES_CONNUES, CLES_LIBRES

RACINE = Path(__file__).resolve().parent.parent


def _config_reelle() -> dict:
    with open(RACINE / "config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------- #
#  La reference ne doit pas deriver
# --------------------------------------------------------------------------- #

def test_la_reference_colle_au_fichier_reel():
    """Si ce test echoue, une cle a ete ajoutee a config.yaml sans etre declaree."""
    reelles = set(cfg.chemins_de(_config_reelle()))
    manquantes = reelles - set(CLES_CONNUES)
    fantomes = set(CLES_CONNUES) - reelles
    assert not manquantes, (
        "cles presentes dans config.yaml mais absentes de core/config_schema.py — "
        f"a ajouter : {sorted(manquantes)}")
    assert not fantomes, (
        "cles declarees mais disparues de config.yaml — a retirer : " f"{sorted(fantomes)}")


def test_le_config_du_depot_ne_leve_aucun_avertissement():
    """La reference livree doit etre propre : un avertissement au premier lancement
    apprendrait a l'ignorer."""
    assert cfg.verifier(_config_reelle()) == []


# --------------------------------------------------------------------------- #
#  Ce qui est signale
# --------------------------------------------------------------------------- #

def test_une_faute_de_frappe_est_signalee():
    config = _config_reelle()
    config["manga"]["typeset"]["font_paht"] = "x"
    avertissements = cfg.verifier(config)
    assert len(avertissements) == 1
    assert "manga.typeset.font_paht" in avertissements[0]


def test_la_cle_proche_est_suggeree():
    """Nommer le coupable probable : la faute cherchee est presque toujours a une lettre."""
    config = _config_reelle()
    config["manga"]["typeset"]["font_paht"] = "x"
    assert "font_path" in cfg.verifier(config)[0]


def test_une_cle_racine_inventee_est_signalee():
    config = _config_reelle()
    config["manga_typeset"] = {}
    assert any("manga_typeset" in a for a in cfg.verifier(config))


def test_un_bloc_entier_inconnu_ne_noie_pas_le_rapport():
    """Un bloc inconnu compte pour UNE cle : lister ses enfants ferait defiler l'utile."""
    config = _config_reelle()
    config["inconnu"] = {"a": 1, "b": {"c": 2}}
    assert len([a for a in cfg.verifier(config) if "inconnu" in a]) == 1


# --------------------------------------------------------------------------- #
#  Ce qui ne doit PAS l'etre
# --------------------------------------------------------------------------- #

def test_un_endpoint_invente_par_l_utilisateur_est_legitime():
    """`llm.endpoints` porte des noms choisis par l'utilisateur."""
    config = _config_reelle()
    config["llm"]["endpoints"]["mon_endpoint"] = {"think": True}
    assert cfg.verifier(config) == []


def test_un_alias_de_dossier_de_langue_est_legitime():
    config = _config_reelle()
    config["langues"]["dossiers"]["NIHONGO"] = "japonais"
    assert cfg.verifier(config) == []


def test_un_agent_mal_orthographie_est_bien_signale():
    """Les blocs d'agents ne sont deliberement PAS libres : leurs noms sont resolus par le
    code, donc une faute de frappe y est un vrai defaut."""
    config = _config_reelle()
    config["modeles"]["traducteurr"] = {"model": "m"}
    assert any("traducteurr" in a for a in cfg.verifier(config))


def test_une_cle_absente_n_est_pas_une_erreur():
    """Tout est optionnel : le code a des defauts partout, et c'est voulu."""
    assert cfg.verifier({"llm": {"base_url": "http://x"}}) == []


def test_une_config_vide_ne_leve_pas():
    assert cfg.verifier({}) == []
    assert cfg.verifier(None) == []


# --------------------------------------------------------------------------- #
#  chemins_de
# --------------------------------------------------------------------------- #

def test_chemins_de_descend_en_profondeur():
    chemins = set(cfg.chemins_de({"a": {"b": {"c": 1}}}))
    assert chemins == {"a", "a.b", "a.b.c"}


def test_chemins_de_s_arrete_sous_un_bloc_libre():
    chemins = set(cfg.chemins_de({"llm": {"endpoints": {"perso": {"think": True}}}}))
    assert "llm.endpoints" in chemins
    assert "llm.endpoints.perso" not in chemins


def test_les_blocs_libres_sont_tous_des_cles_connues():
    """Un bloc libre qui ne serait pas lui-meme declare serait signale a chaque lancement."""
    assert set(CLES_LIBRES) <= set(CLES_CONNUES)
