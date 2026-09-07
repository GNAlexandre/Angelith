# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La sonde de modèles — **critère 9 du `PLAN-33`**, et l'étape 0.2 qui la fonde.

Aucun réseau, aucun serveur : les réponses sont celles **relevées le 2026-09-05** sur l'Ollama
de la machine de développement (`docs/mesures/lanceurs-2026-09-05.md` §3), rejouées telles
quelles. C'est ce qui rend ces tests reproductibles sans endpoint — exigence du critère 12.
"""
import copy
import json

import pytest
import yaml

from core import modeles as mod

#: La réponse RÉELLE de `GET /v1/models`, relevée le 2026-09-05. ⚠ Elle ne porte que des
#: noms : ni capacité vision, ni fenêtre de contexte. C'est la conclusion n° 1 de l'étape 0.2,
#: et c'est elle qui interdit au sélecteur de promettre quoi que ce soit de plus.
REPONSE_V1_MODELS = {
    "object": "list",
    "data": [
        {"id": "yume-27b:latest", "object": "model", "created": 1787244361,
         "owned_by": "library"},
        {"id": "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ4_XS", "object": "model",
         "created": 1787244348, "owned_by": "unsloth"},
        {"id": "qwen3.6:27b", "object": "model", "created": 1783354099,
         "owned_by": "library"},
        {"id": "qwen3.5:9b-q8_0", "object": "model", "created": 1783099093,
         "owned_by": "library"},
    ],
}

#: La réponse RÉELLE de `GET /api/tags`, même relevé. ⚠ Elle porte `capabilities` et
#: `details.context_length` — mais ce second chiffre est celui de l'ARCHITECTURE (262 144),
#: pas celui que le serveur sert (32 768 dans ce dépôt). Cf. `core/power.contexte_charge`.
REPONSE_API_TAGS = {
    "models": [
        {"name": "yume-27b:latest",
         "details": {"family": "qwen35", "context_length": 262144},
         "capabilities": ["completion", "vision"]},
        {"name": "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ4_XS",
         "details": {"family": "qwen35", "context_length": 262144},
         "capabilities": ["completion", "vision"]},
        {"name": "qwen3.6:27b",
         "details": {"family": "qwen35", "context_length": 262144},
         "capabilities": ["vision", "completion", "tools", "thinking"]},
        {"name": "qwen3.5:9b-q8_0",
         "details": {"family": "qwen35", "context_length": 262144},
         "capabilities": ["vision", "completion", "tools", "thinking"]},
    ],
}


def _serveur(monkeypatch, *, tags=REPONSE_API_TAGS, models=REPONSE_V1_MODELS):
    """Rejoue les deux réponses. `tags=None` simule un endpoint OpenAI qui n'est PAS Ollama —
    LM Studio, vLLM, llama.cpp — c'est-à-dire le cas nominal du contrat déclaré."""
    def _lire(url, delai):
        if url.endswith("/api/tags"):
            if tags is None:
                raise OSError("404")
            return json.loads(json.dumps(tags))
        if url.endswith("/models"):
            if models is None:
                raise OSError("connexion refusée")
            return json.loads(json.dumps(models))
        raise AssertionError(f"URL inattendue : {url}")

    monkeypatch.setattr(mod, "_lire_json", _lire)


def test_l_endpoint_openai_seul_ne_dit_que_des_noms(monkeypatch):
    """**Conclusion n° 1 de l'étape 0.2.** `llm.base_url` est déclaré OpenAI-compatible ; tout
    ce qui dépasse la liste des noms est l'information d'un serveur PARTICULIER.

    Sur un endpoint qui n'est pas Ollama, les quatre modèles sortent avec une capacité vision
    **inconnue** — et la liste n'est ni filtrée ni raccourcie pour autant."""
    _serveur(monkeypatch, tags=None)
    catalogue = mod.lister("http://localhost:11434/v1")
    assert catalogue.etat == mod.JOIGNABLE
    assert len(catalogue.modeles) == 4
    assert all(m.vision is None for m in catalogue.modeles)
    assert all(m.vision_lisible == "inconnu" for m in catalogue.modeles)
    assert all(m.contexte_modele is None for m in catalogue.modeles)
    assert "capacité vision inconnue pour 4" in catalogue.phrase()


def test_ollama_sait_dire_la_vision_et_le_dit(monkeypatch):
    """**Conclusion n° 2.** `GET /api/tags` porte `capabilities`. Quand on l'a, on l'affiche ;
    on ne l'invente jamais."""
    _serveur(monkeypatch)
    catalogue = mod.lister("http://localhost:11434/v1")
    yume = catalogue.par_identifiant("yume-27b:latest")
    assert yume.vision is True and yume.vision_lisible == "oui"
    assert yume.source == "Ollama /api/tags"
    assert "vision : oui" in yume.ligne()


def test_un_ollama_sans_capabilities_rend_inconnu_et_non_faux(monkeypatch):
    """⚠ `capabilities` absent ≠ « pas de vision ». Un Ollama antérieur au champ ne le renvoie
    pas ; répondre `False` ferait dire à l'écran qu'un modèle vision-capable ne l'est pas."""
    tags = copy.deepcopy(REPONSE_API_TAGS)
    for entree in tags["models"]:
        entree.pop("capabilities")
    _serveur(monkeypatch, tags=tags)
    catalogue = mod.lister("http://localhost:11434/v1")
    assert all(m.vision is None for m in catalogue.modeles)


def test_la_fenetre_servie_n_est_jamais_promise(monkeypatch):
    """**Conclusion n° 3, et la plus importante.** `details.context_length` vaut 262 144 pour
    les quatre modèles relevés : c'est la fenêtre de l'ARCHITECTURE, pas celle que le serveur
    sert. Le dépôt travaille à 32 768 avec `max_input_tokens: 24000`.

    `core/power.contexte_charge` existe précisément parce qu'« une valeur déclarative fausse
    est pire qu'absente » : `config.yaml` annonçait 65 536 quand le Modelfile en servait
    32 768, et le garde-fou de lot croyait disposer de 55 705 tokens là où le plafond réel
    est 27 852. Le champ rendu ici s'appelle donc `contexte_modele`, et **aucune API du module
    ne rend une fenêtre servie**."""
    _serveur(monkeypatch)
    catalogue = mod.lister("http://localhost:11434/v1")
    modele = catalogue.par_identifiant("qwen3.6:27b")
    assert modele.contexte_modele == 262144
    assert not hasattr(modele, "contexte_servi")
    assert not hasattr(modele, "num_ctx")
    # …et la ligne affichée ne le cite pas : un 262 144 dans une liste déroulante serait lu
    # comme une promesse de fenêtre utile.
    assert "262" not in modele.ligne()


def test_un_endpoint_arrete_rend_injoignable_sans_lever(monkeypatch):
    """Et il DIT que les modèles de `config.yaml` restent en place — L33.3, point 1."""
    _serveur(monkeypatch, models=None)
    catalogue = mod.lister("http://localhost:11434/v1")
    assert catalogue.etat == mod.INJOIGNABLE
    assert catalogue.modeles == ()
    assert "les modèles de config.yaml restent en place" in catalogue.phrase()


def test_l_etat_de_depart_est_inconnu_et_pas_vide():
    """« Inconnu » n'est pas une commodité d'implémentation : c'est l'état réel tant que la
    sonde n'a pas répondu, et le confondre avec « aucun modèle » ferait dire faux à l'écran
    pendant la seconde qui suit le lancement."""
    catalogue = mod.inconnu()
    assert catalogue.etat == mod.INCONNU
    assert "non encore demandée" in catalogue.phrase()


def test_le_delai_tient_compte_du_cout_mesure_de_localhost():
    """⚠ Mesuré le 2026-09-05 sur cette machine : `localhost` coûte **2,04 s** contre
    **0,003 s** pour `127.0.0.1` — Windows tente `::1`, Ollama n'écoute qu'en IPv4. Or le
    défaut du dépôt EST `http://localhost:11434/v1`.

    Un budget de 2,0 s — celui de `gui/sondes.DELAI_RESEAU`, choisi pour un GET sur la
    racine — ferait donc échouer cette sonde contre un serveur parfaitement sain."""
    from gui import sondes as snd

    assert mod.DELAI > snd.DELAI_RESEAU * 2, (
        "le délai de la sonde de modèles doit dépasser largement le coût de résolution de "
        "localhost mesuré à 2,04 s")


def test_racine_ollama_est_celle_de_core_power():
    """Deux calculs différents feraient interroger deux serveurs différents."""
    from core import power

    for url in ("http://x:11434/v1", "http://x:11434/v1/", "http://x:11434"):
        assert mod.racine(url) == power.racine_ollama(url)


# --------------------------------------------------------------------------- #
#  L'outrepassement — en mémoire, et il NOMME ce qu'il change
# --------------------------------------------------------------------------- #

@pytest.fixture()
def config():
    with open("config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_l_endpoint_d_un_agent_est_CONSERVE(config):
    """⚠ **Le piège que `--think` documente depuis le lot 18.** Le dépôt déclare des agents
    sous la forme `{model: "yume-27b", endpoint: "reflexion"}` : remplacer la spec entière
    désactiverait silencieusement l'endpoint de raisonnement.

    « Un sélecteur global qui écraserait un endpoint spécialisé sans le dire est pire que pas
    de sélecteur » — `PLAN-33` L33.3."""
    avant = {nom: dict(spec) for nom, spec in config["modeles"].items()
             if isinstance(spec, dict)}
    assert any(s.get("endpoint") for s in avant.values()), \
        "config.yaml doit porter au moins un endpoint d'agent pour que ce test ait un sens"
    mod.outrepasser(config, None, "un-modele-de-test")
    for nom, spec_avant in avant.items():
        spec = config["modeles"][nom]
        assert spec["model"] == "un-modele-de-test"
        assert spec.get("endpoint") == spec_avant.get("endpoint"), nom


def test_un_agent_a_null_reste_a_null(config):
    """`config.yaml` livre `correcteur: null` — « cet agent ne tourne pas ». Lui poser un
    modèle l'allumerait, et un sélecteur de modèle n'a pas le droit d'ajouter une étape au
    pipeline."""
    assert config["modeles"]["correcteur"] is None
    mod.outrepasser(config, None, "un-modele-de-test")
    assert config["modeles"]["correcteur"] is None


def test_l_outrepassement_nomme_ce_qu_il_change(config):
    """Un run qui ne tourne pas sur le modèle de `config.yaml` doit le dire AVANT, pas après."""
    change = mod.outrepasser(config, "manga", "un-modele-de-test")
    assert change, "aucun agent nommé"
    for nom, avant, apres in change:
        assert nom in config["manga"]["modeles"]
        assert apres == "un-modele-de-test" and avant != apres


def test_choisir_le_modele_deja_en_place_ne_change_rien(config):
    """…et ne le NOMME pas non plus : un récapitulatif qui annoncerait un outrepassement
    inexistant ferait douter des vrais."""
    modele = config["manga"]["modeles"]["manga_traducteur"]["model"]
    assert mod.outrepasser(config, "manga", modele) == ()


def test_une_spec_chaine_reste_une_chaine(config):
    """La promouvoir en dictionnaire ajouterait des clés que personne n'a demandées, dans un
    fichier dont chaque clé porte une mesure."""
    config["modeles"]["mise_en_page"] = "yume-27b"
    mod.outrepasser(config, None, "un-modele-de-test")
    assert config["modeles"]["mise_en_page"] == "un-modele-de-test"


def _code_sans_prose() -> str:
    """Le source du module, **docstrings retirées**.

    ⚠ Sans ça, ces deux tests échoueraient sur la prose qui EXPLIQUE les interdits : le module
    dit lui-même « il ne télécharge rien » et « il n'écrit rien dans config.yaml ». Un
    garde-fou qui interdit de nommer ce qu'il interdit est un garde-fou qu'on contourne en
    supprimant un commentaire."""
    import ast
    import inspect

    arbre = ast.parse(inspect.getsource(mod))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            corps = noeud.body
            if corps and isinstance(corps[0], ast.Expr) and                     isinstance(corps[0].value, ast.Constant) and                     isinstance(corps[0].value.value, str):
                corps.pop(0)
    return ast.unparse(arbre)


def test_aucun_telechargement_n_est_declenche():
    """⚠ **Refus explicite du `PLAN-33` L33.3.** Télécharger des poids est un geste
    d'installation, avec sa licence et sa taille : c'est le `PLAN-36` L36.2, avec consentement
    et provenance. Le module ne doit contenir aucun chemin qui y mène."""
    code = _code_sans_prose()
    for interdit in ("/api/pull", "subprocess", "Popen", "ollama_load", "ollama_pull"):
        assert interdit not in code, interdit
    # …et la seule méthode HTTP employée est GET : `urlopen` sans `data=` ni `method=`.
    assert "method=" not in code and "data=" not in code


def test_aucune_ecriture_de_config_yaml():
    """Interdit n° 5 du dépôt. Le module mute un dictionnaire ; il n'ouvre aucun fichier."""
    code = _code_sans_prose()
    # ⚠ « yaml » tout court ne peut pas être interdit : la phrase d'état du module DIT
    # « les modèles de config.yaml restent en place », et c'est une chaîne de code, pas de la
    # prose. On interdit donc les gestes, pas le mot.
    for interdit in ("safe_dump", "write_text", "yaml.", "import yaml", "Path("):
        assert interdit not in code, interdit
