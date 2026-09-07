# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de llm.py : retrait du raisonnement, initialisation des statistiques."""
from unittest.mock import MagicMock, patch

import pytest

from pipeline.llm import LLM, strip_thinking

# 67 s mesurees sur une machine sans serveur LLM : chaque connexion refusee coute
# ~4 s, et ce fichier en fait beaucoup. Les tests PASSENT (les clients sont doubles),
# ils sont seulement lents. `pytest -m "not lent"` les ecarte.
pytestmark = pytest.mark.lent


def test_strip_thinking_removes_closed_block():
    assert strip_thinking("<think>raisonnement</think>Réponse finale.") == "Réponse finale."


def test_strip_thinking_removes_unclosed_block():
    assert strip_thinking("Avant<think>raisonnement jamais fermé") == "Avant"


def test_strip_thinking_untouched_without_think():
    assert strip_thinking("Rien à retirer ici.") == "Rien à retirer ici."


def test_extra_body_maps_think_to_reasoning_effort():
    """Sur l'endpoint OpenAI d'Ollama, `think` doit être traduit en `reasoning_effort`
    (le paramètre `think` natif y est ignoré)."""
    assert LLM("http://x/v1", "k", think=True)._extra_body() == {"reasoning_effort": "medium"}
    assert LLM("http://x/v1", "k", think=False)._extra_body() == {"reasoning_effort": "none"}
    assert LLM("http://x/v1", "k", think=None)._extra_body() is None


def test_close_closes_underlying_client():
    """close() ferme le pool httpx sous-jacent (évite d'abandonner une socket en pleine
    génération sur Ctrl+C) et est idempotent/best-effort."""
    llm = LLM("http://x/v1", "k")
    with patch.object(llm.client, "close") as mock_close:
        llm.close()
        llm.close()   # idempotent — ne lève pas
    assert mock_close.call_count == 2


def test_close_swallows_client_errors():
    llm = LLM("http://x/v1", "k")
    with patch.object(llm.client, "close", side_effect=RuntimeError("déjà fermé")):
        llm.close()   # ne doit pas propager


def test_resolve_model_adds_missing_tag():
    """Ollama liste « modele:latest » ; une requête « modele » sans tag doit être
    résolue vers le nom taggé réel."""
    from unittest.mock import MagicMock, patch
    llm = LLM("http://x/v1", "k")
    fake = MagicMock()
    fake.data = [MagicMock(id="qwen3.5-9b-yumetrad:latest")]
    with patch.object(llm.client.models, "list", return_value=fake):
        assert llm._resolve_model("qwen3.5-9b-yumetrad") == "qwen3.5-9b-yumetrad:latest"
        assert llm._resolve_model("qwen3.5-9b-yumetrad") == "qwen3.5-9b-yumetrad:latest"  # cache


def test_model_not_found_raises_systemexit_immediately():
    """Un 404 « model not found » lève une SystemExit actionnable sans retenter."""
    from unittest.mock import patch
    import pytest as _pytest
    llm = LLM("http://x/v1", "k", max_retries=2)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      side_effect=Exception("Error code: 404 - model 'm' not found")):
        with _pytest.raises(SystemExit):
            llm.chat("m", "s", "u")


def test_thinking_truncation_falls_back_to_no_think():
    """Si le raisonnement épuise le budget (content vide + reasoning présent), on
    retente une fois sans thinking plutôt que d'échouer."""
    from unittest.mock import MagicMock, patch
    llm = LLM("http://x/v1", "k", think=True, max_retries=0)
    llm._model_cache = {"m": "m"}
    r1 = MagicMock(); r1.choices = [MagicMock(message=MagicMock(content="", reasoning="…"))]; r1.usage = None
    r2 = MagicMock(); r2.choices = [MagicMock(message=MagicMock(content="Réponse."))]; r2.usage = None
    with patch.object(llm.client.chat.completions, "create", side_effect=[r1, r2]):
        assert llm.chat("m", "s", "u") == "Réponse."


def test_no_think_fallback_counts_tokens():
    """Régression : le repli sans-thinking doit incrémenter tokens_generes (sinon le
    --verbose affichait ~0 tok sur les agents en thinking)."""
    from unittest.mock import MagicMock, patch
    llm = LLM("http://x/v1", "k", think=True, max_retries=0)
    llm._model_cache = {"m": "m"}
    r1 = MagicMock(); r1.choices = [MagicMock(message=MagicMock(content="", reasoning="…"))]; r1.usage = None
    r2 = MagicMock(); r2.choices = [MagicMock(message=MagicMock(content="Repli."))]
    r2.usage = MagicMock(completion_tokens=42)
    with patch.object(llm.client.chat.completions, "create", side_effect=[r1, r2]):
        llm.chat("m", "s", "u")
    assert llm.stats["tokens_generes"] == 42


def test_llm_stats_initialized():
    llm = LLM(base_url="http://localhost:1234/v1", api_key="x")
    assert llm.stats == {"appels": 0, "tokens_generes": 0, "temps_generation": 0.0,
                         "retries": 0, "vides_persistants": 0,
                         "thinking_overflow": 0, "troncature_length": 0, "timeout": 0}
    assert llm.last_reason is None


def test_llm_chat_updates_stats_on_success():
    llm = LLM(base_url="http://localhost:1234/v1", api_key="x")
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="Une réponse."))]
    fake_resp.usage = MagicMock(completion_tokens=42)
    with patch.object(llm.client.chat.completions, "create", return_value=fake_resp):
        out = llm.chat("modele", "system", "user")
    assert out == "Une réponse."
    assert llm.stats["appels"] == 1
    assert llm.stats["tokens_generes"] == 42


def test_llm_chat_empty_response_increments_vides_persistants():
    llm = LLM(base_url="http://localhost:1234/v1", api_key="x", max_retries=0)
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=""))]
    fake_resp.choices[0].message.reasoning = None
    fake_resp.choices[0].message.reasoning_content = None
    fake_resp.usage = None
    with patch.object(llm.client.chat.completions, "create", return_value=fake_resp):
        out = llm.chat("modele", "system", "user")
    assert out == ""
    assert llm.stats["vides_persistants"] == 1


def test_chat_without_images_sends_plain_string_content():
    """Rétro-compatibilité stricte (brique manga) : sans `images`, le contenu du
    message reste une simple chaîne — comportement identique à avant l'ajout du
    support vision, aucun appelant existant n'est affecté."""
    llm = LLM(base_url="http://localhost:1234/v1", api_key="x")
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="Réponse."))]
    fake_resp.usage = None
    with patch.object(llm.client.chat.completions, "create", return_value=fake_resp) as mock_create:
        llm.chat("modele", "system", "user")
    sent_messages = mock_create.call_args.kwargs["messages"]
    assert sent_messages[1]["content"] == "user"


def test_chat_with_images_builds_content_parts():
    """`images` (optionnel, utilisé par la brique manga en mode vision) ajoute des
    content-parts `image_url` en base64 au message utilisateur — format compatible
    avec l'endpoint OpenAI d'Ollama."""
    llm = LLM(base_url="http://localhost:1234/v1", api_key="x")
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="Réponse."))]
    fake_resp.usage = None
    with patch.object(llm.client.chat.completions, "create", return_value=fake_resp) as mock_create:
        llm.chat("modele", "system", "user", images=["ZmFrZQ=="])
    sent_content = mock_create.call_args.kwargs["messages"][1]["content"]
    assert isinstance(sent_content, list)
    assert sent_content[0] == {"type": "text", "text": "user"}
    assert sent_content[1]["type"] == "image_url"
    assert sent_content[1]["image_url"]["url"] == "data:image/png;base64,ZmFrZQ=="


def test_llm_chat_reasoning_without_content_falls_back_cleanly():
    """Régression réelle : modèle thinking dont le budget de tokens est épuisé par le
    raisonnement — content vide mais champ `reasoning` rempli. Doit se replier proprement
    (return "") au lieu de lever, pour que l'appelant garde le texte précédent."""
    llm = LLM(base_url="http://localhost:1234/v1", api_key="x", max_retries=0)
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=""))]
    fake_resp.choices[0].message.reasoning = "je réfléchis mais je n'ai pas fini..."
    fake_resp.usage = None
    with patch.object(llm.client.chat.completions, "create", return_value=fake_resp):
        out = llm.chat("modele", "system", "user")
    assert out == ""
    assert llm.stats["vides_persistants"] == 1


# --------------------------------------------------------------------------- #
# Cause de l'échec remontée à l'appelant (`last_reason`) : c'est ce qui permet à
# l'orchestrateur de décider s'il vaut la peine de redécouper le bloc et de
# relancer, au lieu de l'abandonner. Jusqu'ici `chat()` renvoyait "" sans dire
# pourquoi, et les messages partaient sur stdout via un print() brut.
# --------------------------------------------------------------------------- #

def _resp(content="", reasoning=None, finish_reason="stop", completion_tokens=None):
    r = MagicMock()
    choice = MagicMock()
    choice.message = MagicMock(content=content)
    choice.message.reasoning = reasoning
    choice.message.reasoning_content = None
    choice.finish_reason = finish_reason
    r.choices = [choice]
    r.usage = MagicMock(completion_tokens=completion_tokens) if completion_tokens else None
    return r


def test_last_reason_thinking_overflow_and_counter():
    llm = LLM("http://x/v1", "k", max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      return_value=_resp(reasoning="je réfléchis…")):
        assert llm.chat("m", "s", "u") == ""
    assert llm.last_reason == "thinking_overflow"
    assert llm.stats["thinking_overflow"] == 1


def test_last_reason_troncature_on_finish_reason_length():
    """`finish_reason == "length"` = génération coupée net au plafond max_tokens.
    Signal direct de troncature, qui n'était pas lu du tout."""
    llm = LLM("http://x/v1", "k", max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      return_value=_resp(content="Une réponse coupée en plein", finish_reason="length")):
        assert llm.chat("m", "s", "u").startswith("Une réponse")
    assert llm.last_reason == "troncature"
    assert llm.stats["troncature_length"] == 1


def test_last_reason_vide_when_nothing_at_all():
    llm = LLM("http://x/v1", "k", max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create", return_value=_resp()):
        assert llm.chat("m", "s", "u") == ""
    assert llm.last_reason == "vide"


def test_last_reason_reset_between_calls():
    llm = LLM("http://x/v1", "k", max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create", return_value=_resp()):
        llm.chat("m", "s", "u")
    assert llm.last_reason == "vide"
    with patch.object(llm.client.chat.completions, "create",
                      return_value=_resp(content="Tout va bien maintenant.")):
        llm.chat("m", "s", "u")
    assert llm.last_reason is None


def test_on_event_receives_messages_instead_of_stdout(capsys):
    """Les incidents doivent pouvoir être routés vers le reporter (donc perf.log) au
    lieu de partir sur stdout et d'être perdus à la fermeture du terminal."""
    llm = LLM("http://x/v1", "k", max_retries=0)
    llm._model_cache = {"m": "m"}
    recu: list[str] = []
    llm.on_event = recu.append
    with patch.object(llm.client.chat.completions, "create", return_value=_resp()):
        llm.chat("m", "s", "u")
    assert recu and "inexploitable" in recu[0]
    assert "[LLM]" not in capsys.readouterr().out      # rien n'est parti sur stdout


def test_emit_falls_back_to_print_without_callback(capsys):
    llm = LLM("http://x/v1", "k", max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create", return_value=_resp()):
        llm.chat("m", "s", "u")
    assert "[LLM]" in capsys.readouterr().out


def test_no_think_fallback_keeps_images():
    """Régression : le repli sans-raisonnement passait la chaîne `user` brute au lieu du
    contenu multimodal — les images du chemin vision (manga) étaient silencieusement
    perdues et le repli dégénérait en appel texte."""
    llm = LLM("http://x/v1", "k", think=True, max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      side_effect=[_resp(reasoning="…"), _resp(content="Repli.")]) as create:
        assert llm.chat("m", "s", "u", images=["ZmFrZQ=="]) == "Repli."
    contenu = create.call_args_list[1].kwargs["messages"][1]["content"]
    assert isinstance(contenu, list)
    assert any(part.get("type") == "image_url" for part in contenu)


def test_no_think_fallback_counts_its_generation_time():
    """Le repli comptait ses tokens mais pas son temps : le tok/s de perf.log était
    donc surestimé sur tous les agents en thinking."""
    llm = LLM("http://x/v1", "k", think=True, max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      side_effect=[_resp(reasoning="…"), _resp(content="Repli.", completion_tokens=10)]):
        llm.chat("m", "s", "u")
    assert llm.stats["temps_generation"] > 0


# --------------------------------------------------------------------------- #
# Le repli sans raisonnement est un DERNIER RECOURS, pas le comportement par défaut
# --------------------------------------------------------------------------- #

def test_repli_refuse_rend_vide_et_laisse_lappelant_redecouper():
    """Le filet historique rendait `chat()` non vide, donc l'appelant concluait au succès
    et ne redécoupait jamais — alors que deux moitiés RAISONNÉES valent mieux qu'un bloc
    entier non raisonné. Refusé, le repli n'émet même pas de seconde requête."""
    llm = LLM("http://x/v1", "k", think=True, max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      return_value=_resp(reasoning="je réfléchis…")) as create:
        assert llm.chat("m", "s", "u", repli_sans_raisonnement=False) == ""
    assert llm.last_reason == "thinking_overflow"
    assert create.call_count == 1          # aucune requête de repli


def test_repli_autorise_explicitement_reste_le_filet():
    llm = LLM("http://x/v1", "k", think=True, max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      side_effect=[_resp(reasoning="…"), _resp(content="Repli.")]):
        assert llm.chat("m", "s", "u", repli_sans_raisonnement=True) == "Repli."
    assert llm.last_reason == "thinking_overflow"


def test_repli_actif_par_defaut_sur_linstance():
    """Non-régression : les appelants qui ne passent rien gardent le filet (c'est le cas
    de toute la brique manga, dont `MangaAgent.run` ne transmet pas ce paramètre)."""
    llm = LLM("http://x/v1", "k", think=True, max_retries=0)
    assert llm.repli_sans_raisonnement is True
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      side_effect=[_resp(reasoning="…"), _resp(content="Repli.")]):
        assert llm.chat("m", "s", "u") == "Repli."


def test_repli_tronque_a_son_tour_est_signale():
    """Le repli ne testait pas `finish_reason` sur SA PROPRE réponse : une réponse de
    secours elle-même coupée revenait comme un succès ordinaire."""
    llm = LLM("http://x/v1", "k", think=True, max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      side_effect=[_resp(reasoning="…"),
                                   _resp(content="Repli coupé en plein", finish_reason="length")]):
        assert llm.chat("m", "s", "u").startswith("Repli coupé")
    assert llm.last_reason == "troncature"
    assert llm.stats["troncature_length"] == 1


def test_troncature_est_tracee_et_pas_seulement_comptee():
    """Une troncature ne laissait AUCUNE ligne dans perf.log : sur roman A Vol.1,
    deux blocs coupés en plein mot n'y apparaissaient que comme des blocs ordinaires."""
    llm = LLM("http://x/v1", "k", max_retries=0)
    llm._model_cache = {"m": "m"}
    vus = []
    llm.on_event = vus.append
    with patch.object(llm.client.chat.completions, "create",
                      return_value=_resp(content="coupé", finish_reason="length",
                                         completion_tokens=22000)):
        llm.chat("m", "s", "u")
    assert any("coupée net au plafond" in m and "22000" in m for m in vus)


# --------------------------------------------------------------------------- #
# Timeout dérivé du budget, et expiration non fatale
# --------------------------------------------------------------------------- #

def _timeout_err():
    import httpx
    from openai import APITimeoutError
    return APITimeoutError(request=httpx.Request("POST", "http://x/v1/chat/completions"))


def test_le_timeout_est_derive_du_budget_de_generation():
    """Un timeout plat est une contradiction en puissance. Sur roman A Vol.1,
    `max_tokens` valait 20 644 — 1 376 s à 15 tok/s, 4 129 s à 5 — contre un timeout figé à
    900 s : le pire cas autorisé ne tenait à AUCUN débit, et le run de nuit est mort là."""
    llm = LLM("http://x/v1", "k", timeout=900)
    assert llm.timeout_pour(20644) == pytest.approx(20644 / 5)      # ~4129 s
    assert llm.timeout_pour(1000) == 900                            # plancher
    assert llm.timeout_pour(None) == 900                            # petit appel


def test_le_debit_plancher_est_reglable():
    assert LLM("http://x/v1", "k", timeout=900,
               debit_plancher=15).timeout_pour(20644) == pytest.approx(20644 / 15)


def test_le_timeout_derive_part_bien_dans_la_requete():
    llm = LLM("http://x/v1", "k", timeout=900, max_retries=0)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      return_value=_resp(content="ok")) as create:
        llm.chat("m", "s", "u", max_tokens=20644)
    assert create.call_args.kwargs["timeout"] == pytest.approx(20644 / 5)


def test_le_sdk_ne_retente_plus_dans_notre_dos():
    """Le SDK OpenAI vaut `max_retries=2` par défaut ET retente sur timeout. Cumulé aux
    tentatives de l'enveloppe, cela faisait 3 × 3 = 9 requêtes par bloc — 2 h 15 d'attente
    muette, invisible dans perf.log puisque le SDK ne journalise rien."""
    assert LLM("http://x/v1", "k").client.max_retries == 0


def test_une_expiration_persistante_nest_PAS_fatale():
    """C'était le seul motif d'échec LLM à lever, par absence de branche : une
    `APITimeoutError` n'est ni une `RuntimeError`, ni un message contenant « vide ». Un
    bloc trop long tuait donc le tome entier."""
    llm = LLM("http://x/v1", "k", timeout=900, max_retries=1)
    llm._model_cache = {"m": "m"}
    vus = []
    llm.on_event = vus.append
    with patch.object(llm.client.chat.completions, "create", side_effect=_timeout_err()):
        assert llm.chat("m", "s", "u", max_tokens=20644) == ""      # ne lève pas
    assert llm.last_reason == "timeout"
    assert llm.stats["timeout"] == 1
    assert any("expiration persistante" in m for m in vus)


def test_une_expiration_rattrapee_ne_compte_pas_comme_echec():
    llm = LLM("http://x/v1", "k", timeout=900, max_retries=1)
    llm._model_cache = {"m": "m"}
    with patch.object(llm.client.chat.completions, "create",
                      side_effect=[_timeout_err(), _resp(content="Réponse tardive.")]):
        assert llm.chat("m", "s", "u", max_tokens=20644) == "Réponse tardive."
    assert llm.stats["timeout"] == 0
