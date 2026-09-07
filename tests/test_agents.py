# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de agents.py : construction des agents, routage multi-endpoint et mode
« thinking » par requête (paramètre `think` d'Ollama)."""
import pytest

from pipeline.agents import build_agents


def _base_config():
    return {
        "chemins": {"prompts": "prompts"},
        "llm": {"base_url": "http://localhost:11434/v1", "api_key": "ollama", "timeout": 60,
               "max_retries": 1, "extra_directive": "", "think": False,
               "thinking_budget": 2048, "endpoints": {}},
        "modeles": {n: "qwen3.5-9b-yumetrad" for n in
                   ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]},
        "temperatures": {n: 0.2 for n in
                        ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]},
    }


def test_build_agents_backward_compatible_plain_strings():
    cfg = _base_config()
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=True)
    assert len(agents) == 5
    assert all(a.llm == "LLM_DEFAUT" for a in agents.values())


def test_build_agents_dict_spec_routes_to_named_endpoint():
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"base_url": "http://localhost:11435/v1"}}
    cfg["modeles"]["terminologue"] = {"model": "qwen3.5-9b-yumetrad", "endpoint": "reflexion"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["terminologue"].llm != "LLM_DEFAUT"
    assert str(agents["terminologue"].llm.client.base_url).rstrip("/") == "http://localhost:11435/v1"
    assert agents["traducteur"].llm == "LLM_DEFAUT"          # les autres agents inchangés


def test_build_agents_shares_one_client_per_endpoint():
    """Deux agents pointant vers le MÊME endpoint doivent partager UN seul client."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"think": True}}
    cfg["modeles"]["terminologue"] = {"model": "qwen3.5-9b-yumetrad", "endpoint": "reflexion"}
    cfg["modeles"]["glossariste"] = {"model": "qwen3.5-9b-yumetrad", "endpoint": "reflexion"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["terminologue"].llm is agents["glossariste"].llm


def test_build_agents_unknown_endpoint_raises_clear_error():
    cfg = _base_config()
    cfg["modeles"]["terminologue"] = {"model": "x", "endpoint": "inexistant"}
    with pytest.raises(SystemExit):
        build_agents(cfg, llm="LLM_DEFAUT", dry_run=True)


def test_build_agents_misplaced_endpoint_gives_actionable_hint():
    """Piège d'indentation réel : `reflexion` défini sous `llm:` au lieu de
    `llm.endpoints:` (parce que `endpoints: {}` l'a fermé). Le message doit pointer
    précisément ce problème."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {}
    cfg["llm"]["reflexion"] = {"think": True}   # au mauvais niveau
    cfg["modeles"]["terminologue"] = {"model": "m", "endpoint": "reflexion"}
    with pytest.raises(SystemExit) as exc:
        build_agents(cfg, llm="LLM_DEFAUT", dry_run=True)
    msg = str(exc.value)
    assert "mauvais niveau" in msg and "endpoints" in msg


def test_build_agents_endpoint_think_true_sets_thinking_flag():
    """Un endpoint « reflexion » avec think:true marque l'agent comme thinking et
    transmet think=True au client ; le défaut (think:false) ne l'est pas."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"think": True}}
    cfg["modeles"]["terminologue"] = {"model": "qwen3.5-9b-yumetrad", "endpoint": "reflexion"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["terminologue"].thinking is True
    assert agents["terminologue"].llm.think is True
    assert agents["traducteur"].thinking is False


def test_build_agents_endpoint_defaults_base_url_to_main_server():
    """Un endpoint qui ne précise que think (pas base_url) reprend le serveur principal
    — cas Ollama : un seul serveur, on change juste le réglage think."""
    cfg = _base_config()
    cfg["llm"]["base_url"] = "http://localhost:11434/v1"
    cfg["llm"]["endpoints"] = {"reflexion": {"think": True}}
    cfg["modeles"]["terminologue"] = {"model": "qwen3.5-9b-yumetrad", "endpoint": "reflexion"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert str(agents["terminologue"].llm.client.base_url).rstrip("/") == "http://localhost:11434/v1"
    assert agents["terminologue"].modele == "qwen3.5-9b-yumetrad"


def test_temperature_manquante_est_signalee_cote_ln():
    """Le LN reste STRICT (`temperature_defaut=None`) : un agent défini sans température
    est une erreur de config, pas un cas à combler en silence — au lot 2.2 c'était un
    `KeyError` nu, c'est désormais un message qui dit quoi ajouter et où."""
    cfg = _base_config()
    del cfg["temperatures"]["traducteur"]
    with pytest.raises(SystemExit) as exc:
        build_agents(cfg, llm="LLM_DEFAUT", dry_run=True)
    msg = str(exc.value)
    assert "temperatures.traducteur" in msg and "modeles.traducteur" in msg
    assert "manga." not in msg          # pas de préfixe de section à la racine


def test_agent_desactive_nexige_pas_de_temperature():
    """`modeles.correcteur: null` doit rester gratuit : ni prompt lu, ni température
    exigée. C'est ce qui permet de désactiver une étape sans toucher au reste."""
    cfg = _base_config()
    cfg["modeles"]["correcteur"] = None
    del cfg["temperatures"]["correcteur"]
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=True)
    assert agents["correcteur"] is None
    assert set(agents) == set(cfg["modeles"])       # la clé existe quand même


def test_le_roster_ln_est_fixe_meme_si_la_config_en_ajoute():
    """`names=None` à la racine = `NOMS_LN`, pas « les clés de modeles ». Un modèle
    étranger dans `modeles` (ex. celui du manga recopié par erreur) ne doit pas créer un
    sixième agent LN, dont l'orchestrateur ne saurait rien faire."""
    cfg = _base_config()
    cfg["modeles"]["manga_traducteur"] = "m"
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=True)
    assert "manga_traducteur" not in agents
    assert len(agents) == 5


def test_think_en_ligne_marche_aussi_cote_ln():
    """Nouvelle capacité symétrique : la forme en ligne `{model: …, think: true}`, jusque-là
    propre au manga, vaut endpoint anonyme et évite d'avoir à déclarer un endpoint pour le
    seul réglage `think`."""
    cfg = _base_config()
    cfg["modeles"]["terminologue"] = {"model": "m", "think": True}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["terminologue"].thinking is True
    assert agents["terminologue"].llm.think is True
    assert agents["traducteur"].llm == "LLM_DEFAUT"      # les autres gardent le client fourni


def test_think_en_ligne_affine_lendpoint_nomme():
    """Le plus spécifique gagne : l'endpoint fournit le serveur, la spec du modèle peut
    en corriger le `think` sans avoir à dupliquer l'endpoint."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"base_url": "http://localhost:11435/v1",
                                            "think": True}}
    cfg["modeles"]["terminologue"] = {"model": "m", "endpoint": "reflexion", "think": False}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["terminologue"].thinking is False
    assert str(agents["terminologue"].llm.client.base_url).rstrip("/") == \
        "http://localhost:11435/v1"


def test_thinking_agent_gets_larger_token_budget():
    """Un agent thinking ajoute son thinking_budget au max_tokens demandé ; un agent
    non-thinking laisse le max_tokens tel quel."""
    from pipeline.agents import Agent

    class _FakeLLM:
        def __init__(self): self.last_max = None
        def chat(self, model, system, user, temp, max_tokens=None, **_):
            self.last_max = max_tokens; return "ok"

    import os
    import tempfile
    p = os.path.join(tempfile.gettempdir(), "prompt_test.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("prompt")

    thinker = Agent("terminologue", p, _FakeLLM(), "m", 0.2, thinking=True, thinking_budget=2048)
    thinker.run("u", max_tokens=1024)
    assert thinker.llm.last_max == 1024 + 2048

    plain = Agent("traducteur", p, _FakeLLM(), "m", 0.2, thinking=False)
    plain.run("u", max_tokens=1024)
    assert plain.llm.last_max == 1024


# --------------------------------------------------------------------------- #
# Niveau de réflexion et budget par endpoint
# --------------------------------------------------------------------------- #

def test_endpoint_think_niveau_nomme():
    """`think` accepte un niveau (`"low"`), pas seulement un booléen : le niveau pèse
    lourd sur le coût — 74 à 97 % de la génération partait dans le raisonnement en
    "medium" sur des blocs japonais."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"think": "low"}}
    cfg["modeles"]["traducteur"] = {"model": "m", "endpoint": "reflexion"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["traducteur"].thinking is True
    assert agents["traducteur"].llm._extra_body() == {"reasoning_effort": "low"}


def test_endpoint_think_none_ne_consomme_pas_de_budget_de_reflexion():
    """`bool("none")` vaut True : sans traitement, un agent explicitement SANS
    raisonnement se verrait accorder le budget de tokens supplémentaire."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"muet": {"think": "none"}}
    cfg["modeles"]["traducteur"] = {"model": "m", "endpoint": "muet"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["traducteur"].thinking is False
    assert agents["traducteur"].llm._extra_body() == {"reasoning_effort": "none"}


def test_niveau_de_reflexion_invalide_est_signale():
    """Une faute de frappe doit échouer ici, avec un message actionnable, plutôt que de
    partir chez Ollama et de revenir en 400 opaque au premier bloc."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"think": "meduim"}}
    cfg["modeles"]["traducteur"] = {"model": "m", "endpoint": "reflexion"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    with pytest.raises(SystemExit) as e:
        agents["traducteur"].llm._extra_body()
    assert "meduim" in str(e.value) and "low, medium, high" in str(e.value)


def test_thinking_budget_saffine_par_endpoint():
    """Le budget de raisonnement se règle là où se règlent le niveau et la taille des
    blocs. Un agent hors de l'endpoint garde celui de la brique."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"think": True, "thinking_budget": 8000}}
    cfg["modeles"]["traducteur"] = {"model": "m", "endpoint": "reflexion"}
    cfg["modeles"]["glossariste"] = {"model": "m", "endpoint": "reflexion"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["traducteur"].thinking_budget == 8000
    assert agents["glossariste"].thinking_budget == 8000
    assert agents["terminologue"].thinking_budget == 2048      # valeur de la brique


def test_thinking_budget_en_ligne_affine_lendpoint_nomme():
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"think": True, "thinking_budget": 8000}}
    cfg["modeles"]["traducteur"] = {"model": "m", "endpoint": "reflexion",
                                    "thinking_budget": 12000}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["traducteur"].thinking_budget == 12000


def test_thinking_budget_absent_reste_celui_de_la_brique():
    """Non-régression : sans la nouvelle clé, rien ne change."""
    cfg = _base_config()
    cfg["llm"]["endpoints"] = {"reflexion": {"think": True}}
    cfg["modeles"]["traducteur"] = {"model": "m", "endpoint": "reflexion"}
    agents = build_agents(cfg, llm="LLM_DEFAUT", dry_run=False)
    assert agents["traducteur"].thinking_budget == 2048
