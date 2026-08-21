# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`build_agents` unifié, vu depuis la brique manga (lot 2.2).

`build_manga_agents` n'avait **aucun test** — c'est précisément ce qui a laissé vivre son
défaut le plus vicieux : `endpoint:` était silencieusement ignoré côté manga, et
`config.yaml` s'était mis à *documenter* le piège (« ⚠ `endpoint:` n'est PAS lu par
build_manga_agents … l'idiome serait SILENCIEUSEMENT ignoré ») au lieu de le corriger.
Ces tests verrouillent donc les deux sens : ce que le manga gagne, et ce qu'il ne perd pas.
"""
from __future__ import annotations

import pytest

from manga.agents_manga import MangaAgent, build_manga_agents


def _config(modeles=None, temperatures=None, llm_manga=None, **llm_racine):
    """Config minimale à deux niveaux : racine (LN) + section `manga`."""
    llm = {"base_url": "http://localhost:11434/v1", "api_key": "ollama", "timeout": 60,
           "max_retries": 1, "extra_directive": "", "think": False,
           "thinking_budget": 2048, "endpoints": {}}
    llm.update(llm_racine)
    manga = {"modeles": modeles if modeles is not None
             else {"manga_traducteur": {"model": "qwen3.6:27b", "think": False}},
             "temperatures": temperatures if temperatures is not None
             else {"manga_traducteur": 0.3}}
    if llm_manga is not None:
        manga["llm"] = llm_manga
    return {"chemins": {"prompts": "prompts"}, "llm": llm, "modeles": {}, "temperatures": {},
            "manga": manga}


def test_construit_un_agent_par_entree_de_manga_modeles():
    """Roster OUVERT : aucune liste fixe de noms, contrairement au LN."""
    cfg = _config(modeles={"manga_traducteur": "m", "terminologue": "m"},
                  temperatures={"manga_traducteur": 0.3, "terminologue": 0.2})
    agents = build_manga_agents(cfg, dry_run=True)
    assert set(agents) == {"manga_traducteur", "terminologue"}
    assert all(isinstance(a, MangaAgent) for a in agents.values())


def test_la_classe_est_mangaagent_et_accepte_images():
    """`agent_cls` est la raison d'être du paramètre : le socle ne peut pas importer
    `manga/`, c'est l'appelant qui injecte la sous-classe."""
    agents = build_manga_agents(_config(), dry_run=True)
    agent = agents["manga_traducteur"]
    assert isinstance(agent, MangaAgent)
    assert agent.run("u", dry_payload="tel quel", images=["b64"]) == "tel quel"


def test_think_en_ligne_reste_lu():
    """Forme utilisée par `config.yaml` livré : `{model: …, think: false}`. Elle marchait
    avant l'unification et doit continuer — c'est le seul levier documenté du
    raisonnement côté manga."""
    cfg = _config(modeles={"manga_traducteur": {"model": "m", "think": True}})
    agents = build_manga_agents(cfg, dry_run=False)
    assert agents["manga_traducteur"].thinking is True
    assert agents["manga_traducteur"].llm.think is True

    cfg = _config(modeles={"manga_traducteur": {"model": "m", "think": False}})
    agents = build_manga_agents(cfg, dry_run=False)
    assert agents["manga_traducteur"].thinking is False


def test_endpoint_nomme_est_desormais_lu_cote_manga():
    """LE gain du lot 2.2. Avant, cette config ne produisait AUCUN effet et AUCUN
    message : l'agent tournait sur le serveur par défaut, sans raisonnement."""
    cfg = _config(endpoints={"reflexion": {"think": True}},
                  modeles={"manga_traducteur": {"model": "m", "endpoint": "reflexion"}})
    agents = build_manga_agents(cfg, dry_run=False)
    assert agents["manga_traducteur"].thinking is True
    assert agents["manga_traducteur"].llm.think is True


def test_endpoint_nomme_peut_changer_de_serveur():
    cfg = _config(endpoints={"autre": {"base_url": "http://localhost:11435/v1"}},
                  modeles={"manga_traducteur": {"model": "m", "endpoint": "autre"}})
    agents = build_manga_agents(cfg, dry_run=False)
    base = str(agents["manga_traducteur"].llm.client.base_url).rstrip("/")
    assert base == "http://localhost:11435/v1"


def test_endpoint_inconnu_leve_une_erreur_qui_nomme_la_section_manga():
    """Le message doit envoyer l'utilisateur au bon endroit : `manga.modeles.<agent>`,
    et `llm.endpoints` (racine) tant que la brique n'a pas son propre bloc `llm:`."""
    cfg = _config(modeles={"manga_traducteur": {"model": "m", "endpoint": "inexistant"}})
    with pytest.raises(SystemExit) as exc:
        build_manga_agents(cfg, dry_run=True)
    msg = str(exc.value)
    assert "manga.modeles.manga_traducteur" in msg
    assert "llm.endpoints" in msg and "manga.llm.endpoints" not in msg


def test_endpoint_inconnu_pointe_manga_llm_quand_la_brique_a_son_bloc():
    """Avec un bloc `manga.llm`, c'est LUI qu'il faut aller éditer — pas la racine."""
    cfg = _config(llm_manga={"base_url": "http://localhost:11434/v1", "endpoints": {}},
                  modeles={"manga_traducteur": {"model": "m", "endpoint": "inexistant"}})
    with pytest.raises(SystemExit) as exc:
        build_manga_agents(cfg, dry_run=True)
    assert "manga.llm.endpoints" in str(exc.value)


def test_diagnostic_dindentation_disponible_cote_manga():
    """`endpoints: {}` ferme le dictionnaire, la définition qui suit atterrit à côté."""
    cfg = _config(endpoints={}, reflexion={"think": True},
                  modeles={"manga_traducteur": {"model": "m", "endpoint": "reflexion"}})
    with pytest.raises(SystemExit) as exc:
        build_manga_agents(cfg, dry_run=True)
    assert "mauvais niveau" in str(exc.value)


def test_un_seul_client_par_endpoint_partage_entre_agents():
    cfg = _config(endpoints={"reflexion": {"think": True}},
                  modeles={"manga_traducteur": {"model": "m", "endpoint": "reflexion"},
                           "terminologue": {"model": "m", "endpoint": "reflexion"}},
                  temperatures={"manga_traducteur": 0.3, "terminologue": 0.2})
    agents = build_manga_agents(cfg, dry_run=False)
    assert agents["manga_traducteur"].llm is agents["terminologue"].llm


def test_les_agents_sans_endpoint_partagent_aussi_leur_client():
    """Le manga ne reçoit pas de client déjà ouvert (`llm=None`) : le socle en construit
    un pour le serveur principal. Il doit être mis en cache comme les autres, sinon un
    roster de N agents ouvrirait N pools de sockets vers le même Ollama."""
    cfg = _config(modeles={"manga_traducteur": "m", "terminologue": "m"},
                  temperatures={"manga_traducteur": 0.3, "terminologue": 0.2})
    agents = build_manga_agents(cfg, dry_run=False)
    assert agents["manga_traducteur"].llm is agents["terminologue"].llm
    assert agents["manga_traducteur"].llm is not None


def test_temperature_de_repli_a_0_3():
    """Tolérance historique de la brique manga, conservée : une température absente ne
    fait pas échouer le run (le LN, lui, est strict — cf. test_agents.py)."""
    cfg = _config(temperatures={})
    agents = build_manga_agents(cfg, dry_run=True)
    assert agents["manga_traducteur"].temperature == 0.3


def test_extra_directive_de_la_racine_atteint_le_manga():
    """Directive GLOBALE par définition (« ajouté à la fin de chaque message
    utilisateur ») : seul le LN l'appliquait, en silence."""
    cfg = _config(extra_directive="Reste sobre.")
    agents = build_manga_agents(cfg, dry_run=True)
    assert agents["manga_traducteur"].extra_directive == "Reste sobre."


def test_dry_run_nouvre_aucun_client():
    agents = build_manga_agents(_config(), dry_run=True)
    assert agents["manga_traducteur"].llm is None


def test_modele_null_desactive_lagent():
    """Cohérence avec le LN : `modeles.<nom>: null` ne construit pas d'agent (donc pas de
    lecture de prompt, pas d'exigence de température)."""
    cfg = _config(modeles={"manga_traducteur": "m", "glossariste": None},
                  temperatures={"manga_traducteur": 0.3})
    agents = build_manga_agents(cfg, dry_run=True)
    assert agents["glossariste"] is None
    assert agents["manga_traducteur"] is not None


def test_un_bloc_llm_manga_partiel_ne_perd_plus_la_racine():
    """La bascule du lot 2.3, vue depuis les agents. Ce test disait l'inverse au lot 2.2 :
    le bloc `manga.llm` REMPLAÇAIT la racine, donc décommenter le bloc de `config.yaml` pour
    n'y régler qu'un `thinking_budget` faisait perdre `llm.endpoints` — et un
    `endpoint: "reflexion"` par ailleurs correct échouait en `SystemExit`."""
    cfg = _config(endpoints={"reflexion": {"think": True}},
                  llm_manga={"thinking_budget": 2500},
                  modeles={"manga_traducteur": {"model": "m", "endpoint": "reflexion"}})
    agents = build_manga_agents(cfg, dry_run=True)
    agent = agents["manga_traducteur"]
    assert agent.thinking is True             # l'endpoint hérité de la racine est trouvé
    assert agent.thinking_budget == 2500      # …et le réglage propre à la brique s'applique


def test_le_diagnostic_nomme_le_bloc_ou_la_cle_mal_indentee_se_trouve():
    """Conséquence de la fusion : la clé fautive peut être dans l'AUTRE bloc que celui où
    il faudrait l'ajouter. Pointer le mauvais fait perdre le temps que ce message est censé
    économiser — ici « reflexion » est mal indenté sous la racine `llm:`, alors que la
    brique a son propre bloc."""
    cfg = _config(endpoints={}, reflexion={"think": True},
                  llm_manga={"thinking_budget": 2500},
                  modeles={"manga_traducteur": {"model": "m", "endpoint": "reflexion"}})
    with pytest.raises(SystemExit) as exc:
        build_manga_agents(cfg, dry_run=True)
    msg = str(exc.value)
    assert "mauvais niveau" in msg
    assert "sous `llm:`" in msg               # là où la clé est
    assert "absent de manga.llm.endpoints" in msg   # là où il faut l'ajouter
