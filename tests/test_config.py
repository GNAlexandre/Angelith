# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Héritage de configuration entre la racine de `config.yaml` et une brique (lot 2.3).

Deux comportements-pièges sont testés explicitement parce qu'ils portent tous deux sur
`None` et vont dans des sens OPPOSÉS : un scalaire nul de la surcouche gagne (`think: null`
est une valeur utile, distincte de `false`), un sous-arbre nul est hérité (`llm:` écrit puis
laissé vide est un accident YAML, jamais une demande d'effacement).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.config import deep_merge, origine, section

RACINE = Path(__file__).resolve().parents[1]


# --- deep_merge ------------------------------------------------------------------


def test_les_branches_voisines_survivent():
    """LE point de la fusion profonde : régler une seule feuille ne doit pas emporter le
    reste de la branche. C'est exactement ce que faisait `mcfg.get("llm") or config["llm"]`."""
    base = {"base_url": "http://a", "api_key": "k", "endpoints": {"reflexion": {"think": True}}}
    out = deep_merge(base, {"thinking_budget": 2500})
    assert out["base_url"] == "http://a"
    assert out["endpoints"] == {"reflexion": {"think": True}}
    assert out["thinking_budget"] == 2500


def test_fusion_recursive_sur_plusieurs_niveaux():
    base = {"endpoints": {"reflexion": {"base_url": "http://a", "think": True}}}
    out = deep_merge(base, {"endpoints": {"reflexion": {"think": False}}})
    assert out["endpoints"]["reflexion"] == {"base_url": "http://a", "think": False}


def test_les_endpoints_des_deux_niveaux_se_cumulent():
    base = {"endpoints": {"reflexion": {"think": True}}}
    out = deep_merge(base, {"endpoints": {"rapide": {"think": False}}})
    assert set(out["endpoints"]) == {"reflexion", "rapide"}


def test_une_liste_remplace_et_ne_se_concatene_pas():
    """Une liste de `config.yaml` est une énumération COMPLÈTE (`formats`, `providers`) :
    concaténer rendrait impossible d'en retirer un élément dans la brique."""
    out = deep_merge({"providers": ["Dml", "CPU"]}, {"providers": ["CPU"]})
    assert out["providers"] == ["CPU"]


def test_un_scalaire_nul_de_la_surcouche_gagne():
    """`think: null` = « laisse le défaut du modèle », distinct de `think: false` = « pas de
    raisonnement » (cf. `core.llm.LLM` : rien envoyé / `reasoning_effort: none`). Sans cette
    règle, une brique ne pourrait pas revenir au défaut du modèle quand la racine impose
    `false`."""
    out = deep_merge({"think": False}, {"think": None})
    assert "think" in out and out["think"] is None


def test_un_sous_arbre_nul_est_herite():
    """`manga:\\n  llm:` (bloc écrit puis laissé vide) donne `None` en YAML — jamais une
    demande d'effacer tous les réglages LLM de la racine."""
    base = {"llm": {"base_url": "http://a"}, "x": 1}
    out = deep_merge(base, {"llm": None})
    assert out["llm"] == {"base_url": "http://a"}


def test_ne_modifie_aucun_des_deux_dictionnaires():
    """Les deux viennent du `config` global, partagé par tout le run : une mutation en
    place contaminerait la brique voisine."""
    base = {"endpoints": {"reflexion": {"think": True}}}
    sur = {"endpoints": {"rapide": {"think": False}}}
    fige_base, fige_sur = repr(base), repr(sur)
    deep_merge(base, sur)
    assert repr(base) == fige_base and repr(sur) == fige_sur


def test_une_surcouche_vide_rend_une_copie_de_la_base():
    base = {"a": {"b": 1}}
    out = deep_merge(base, {})
    assert out == base and out is not base


# --- section() -------------------------------------------------------------------


def _config():
    return {
        "llm": {"base_url": "http://a", "api_key": "k", "timeout": 900,
                "endpoints": {"reflexion": {"think": True}}},
        "chemins": {"sources": "sources", "build": "build", "prompts": "prompts",
                    "glossaire_fichier": "glossaire.yaml"},
        "rendu": {"formats": ["docx"], "reference_docx": "templates/reference.docx"},
        "manga": {"llm": {"thinking_budget": 2500},
                  "rendu": {"formats": ["cbz"], "sens_lecture": "droite_gauche"}},
    }


def test_section_racine_ne_herite_de_personne():
    cfg = _config()
    assert section(cfg, None, "llm") == cfg["llm"]
    assert section(cfg, None, "llm") is not cfg["llm"]       # copie


def test_section_manga_herite_de_la_racine():
    out = section(_config(), "manga", "llm")
    assert out["base_url"] == "http://a"                     # hérité
    assert out["endpoints"] == {"reflexion": {"think": True}}  # hérité
    assert out["thinking_budget"] == 2500                    # propre


def test_section_absente_rend_le_bloc_racine():
    cfg = _config()
    del cfg["manga"]["llm"]
    assert section(cfg, "manga", "llm") == cfg["llm"]


def test_section_chemins_du_manga_est_entierement_heritee():
    """`manga.chemins` est vide dans le `config.yaml` livré : tout vient de la racine."""
    cfg = _config()
    cfg["manga"]["chemins"] = None
    out = section(cfg, "manga", "chemins")
    assert out == cfg["chemins"]


def test_lheritage_est_opt_in_bloc_par_bloc():
    """`rendu` ne doit PAS hériter : la racine et le manga ont tous deux ce bloc mais ils
    ne parlent pas de la même chose (`reference_docx`/`epub_css` d'un côté, sens de lecture
    et qualité JPEG de l'autre). C'est pour ça que `section()` prend la clé en paramètre
    au lieu de fusionner toute la section — ce test dit que personne ne l'a « simplifié »."""
    cfg = _config()
    fusionne = section(cfg, "manga", "rendu")
    assert "reference_docx" in fusionne, "section() fusionne bien ce qu'on lui demande…"
    # …mais l'orchestrateur manga lit `mcfg["rendu"]` DIRECTEMENT, sans passer par
    # section() : c'est ce choix de call site qui garde `reference_docx` hors du rendu manga.
    src = (RACINE / "manga" / "orchestrator_manga.py").read_text(encoding="utf-8")
    assert 'section(config, "manga", "rendu")' not in src


@pytest.mark.parametrize("cle,attendu", [("llm", "manga.llm"), ("chemins", "chemins")])
def test_origine_nomme_le_bloc_a_editer(cle, attendu):
    """Les messages d'erreur doivent envoyer au bloc que l'utilisateur édite réellement."""
    cfg = _config()
    cfg["manga"]["chemins"] = None                # bloc vide → c'est la racine qui compte
    assert origine(cfg, "manga", cle) == attendu
    assert origine(cfg, None, cle) == cle


# --- le vrai config.yaml ---------------------------------------------------------


def test_le_config_yaml_livre_ne_duplique_plus_sources_et_build():
    """Régression directe : `manga.chemins` recopiait `sources` et `build`, avec le
    commentaire « même racine que le LN ». Deux copies à changer ensemble — modifier la
    seule racine faisait écrire la brique manga à l'ancien endroit, sans un mot."""
    cfg = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    propre = (cfg["manga"].get("chemins") or {})
    assert "sources" not in propre and "build" not in propre
    resolu = section(cfg, "manga", "chemins")
    assert resolu["sources"] == cfg["chemins"]["sources"]
    assert resolu["build"] == cfg["chemins"]["build"]
    # …et la brique gagne les clés qu'elle allait chercher dans la racine à la main.
    assert resolu["glossaire_fichier"] == cfg["chemins"]["glossaire_fichier"]
