# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Cycle de vie des clients LLM d'un run : inventaire, branchement des incidents sur le
reporter, agrégation des compteurs, fermeture des sockets.

Ces quatre fonctions ne connaissent **rien** de l'unité de travail — ni bloc de texte ni
planche de bulles. Elles ne voient qu'un client par défaut et un dictionnaire d'agents.
C'est exactement la frontière d'extraction du lot 2 (cf. `core/__init__.py`), et c'est
pourquoi elles étaient les premières à devoir sortir de `pipeline/orchestrator.py` : la
brique manga n'en avait aucune, et payait les trois défauts que le light novel avait déjà
diagnostiqués et corrigés chez lui.

Le point commun des trois : **un client autre que celui par défaut existe dès qu'un agent
vise un `endpoint:`**. Tant que `endpoint:` était silencieusement ignoré côté manga (corrigé
au lot 2.2), le manga n'avait toujours qu'un seul client et les trois défauts restaient
théoriques. Ils ne le sont plus.
"""
from __future__ import annotations


def all_llm_clients(llm, agents: dict) -> list:
    """Tous les clients LLM DISTINCTS d'un run : le client par défaut ET ceux des
    endpoints (« reflexion » a le sien, cf. `build_agents`). Dédoublonne par `id()` car
    `build_agents` met les clients en cache par `(base_url, think)`. En dry-run tous les
    clients valent None → liste vide."""
    seen: dict[int, object] = {}
    if llm is not None:
        seen[id(llm)] = llm
    for ag in (agents or {}).values():
        c = getattr(ag, "llm", None)
        if c is not None:
            seen.setdefault(id(c), c)
    return list(seen.values())


def close_llm_clients(llm, agents: dict) -> None:
    """Ferme les pools HTTP (Ollama) ouverts pour un run. Best-effort (cf. `LLM.close`) :
    appelé aux sorties délibérées d'un orchestrateur pour ne pas laisser une socket vers
    Ollama pendante après un arrêt."""
    for c in all_llm_clients(llm, agents):
        close = getattr(c, "close", None)   # tolère un client factice (tests) sans .close()
        if callable(close):
            close()


def wire_reporter(llm, agents: dict, reporter) -> None:
    """Branche les messages d'incident des clients LLM (budget « thinking » épuisé,
    nouvelle tentative, réponse inexploitable) sur `reporter.warn`, pour qu'ils
    atterrissent AUSSI dans perf.log. Sans ça, ils partaient sur stdout via un `print()`
    brut : après un run de plusieurs heures, plus aucune trace de quels blocs avaient
    dérapé ni pourquoi — et en mode TUI ils corrompaient la barre de progression Live."""
    warn = getattr(reporter, "warn", None)
    if not callable(warn):
        return
    for c in all_llm_clients(llm, agents):
        try:
            c.on_event = warn
        except Exception:
            pass


def aggregate_llm_stats(llm, agents: dict) -> dict:
    """Somme les compteurs de TOUS les clients du run. Le résumé de `RAPPORT.md` ne lisait
    que `llm.stats`, soit le client par défaut : sur un tome où traducteur, terminologue
    et glossariste tournent sur l'endpoint « reflexion » (qui a son propre client), il
    ignorait la majorité des appels — 79 annoncés contre 183 réellement tracés dans
    perf.log sur roman B Vol.2."""
    total = {"appels": 0, "tokens_generes": 0, "temps_generation": 0.0, "retries": 0,
             "vides_persistants": 0, "thinking_overflow": 0, "troncature_length": 0}
    for c in all_llm_clients(llm, agents):
        st = getattr(c, "stats", None) or {}
        for k in total:
            total[k] += st.get(k, 0)
    return total
