# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`illustration/sonde.py` — ce que le serveur expose, relevé contre un `/object_info` factice.

Le critère 8 du `PLAN-28` l'exige mot pour mot : « la sonde et le validateur se testent contre
un `/object_info` factice, comme le client se teste déjà contre un transport factice ». Ce
fichier tourne donc **sans ComfyUI**, sans GPU et sans réseau — donc en CI.

Le test qui compte le plus est `test_un_serveur_ETEINT_ne_dit_pas_que_les_noeuds_manquent` :
c'est la distinction dont dépend tout le lot. Un relevé vide et un relevé « on ne sait pas »
ne sont pas la même chose, et les confondre produirait le faux avertissement que
`core/config_schema.py` décrit en tête — « pire que pas de vérification du tout ».
"""
import urllib.error

import pytest

from illustration import sonde as sonde_mod

#: Un `/object_info` qui ressemble au vrai : un nœud du cœur, un nœud tiers, une liste pleine
#: et une liste **vide** — l'état exact de `ModelPatchLoader` relevé le 2026-08-30.
OBJECT_INFO = {
    "KSampler": {
        "input": {"required": {"model": ["MODEL"], "seed": ["INT", {"default": 0}],
                               "sampler_name": [["euler", "heun"], {}]}},
        "python_module": "nodes"},
    "UnetLoaderGGUF": {
        "input": {"required": {"unet_name": [["qwen-image-2512-Q4_1.gguf"], {}]}},
        "python_module": "custom_nodes.ComfyUI-GGUF"},
    "VAELoader": {
        "input": {"required": {"vae_name": [["qwen_image_vae.safetensors"], {}]}},
        "python_module": "nodes"},
    "ModelPatchLoader": {
        "input": {"required": {"name": [[], {}]}},
        "python_module": "nodes"},
}

SYSTEM_STATS = {
    "system": {"os": "nt", "comfyui_version": "0.34.2", "python_version": "3.13.12 (main)",
               "pytorch_version": "2.12.0+rocm7.14.0", "embedded_python": True,
               "argv": ["C:/ComfyUI/main.py", "--listen"]},
    "devices": [{"name": "cuda:0 AMD Radeon RX 7900 XT", "type": "cuda",
                 "vram_total": 21458059264, "vram_free": 8000000000,
                 "torch_vram_total": 9000000000, "torch_vram_free": 100000000}],
}


class TransportFactice:
    """Un ComfyUI de papier **en lecture seule** : il compte tout ce qu'on lui demande."""

    def __init__(self, *, object_info=None, stats=None, journal=None) -> None:
        self.object_info = OBJECT_INFO if object_info is None else object_info
        self.stats = SYSTEM_STATS if stats is None else stats
        self.journal = journal
        self.vus: list[str] = []
        self.postes: list[str] = []

    def get_json(self, chemin):
        self.vus.append(chemin)
        if chemin == "/system_stats":
            return self.stats
        if chemin == "/object_info":
            return self.object_info
        if chemin == "/internal/logs/raw":
            if self.journal is None:
                raise urllib.error.URLError("route absente")
            return self.journal
        return {}

    def post_json(self, chemin, charge):                 # pragma: no cover — jamais appelé
        self.postes.append(chemin)
        return {}

    def get_bytes(self, chemin, parametres):             # pragma: no cover — jamais appelé
        self.vus.append(chemin)
        return b""

    def post_fichier(self, *args, **champs):             # pragma: no cover — jamais appelé
        self.postes.append(args[0] if args else "?")
        return {}


class TransportMuet:
    """Un serveur éteint : chaque route lève, comme `urllib` le ferait."""

    def get_json(self, chemin):
        raise urllib.error.URLError("connexion refusée")

    def post_json(self, chemin, charge):                 # pragma: no cover
        raise urllib.error.URLError("connexion refusée")


@pytest.fixture
def releve():
    return sonde_mod.sonder("http://127.0.0.1:8188", transport=TransportFactice())


# ─────────────────────────────  Ce que la sonde relève  ─────────────────────────────

def test_la_sonde_releve_la_version_les_noeuds_et_la_vram(releve):
    assert releve.joignable is True
    assert releve.version == "0.34.2"
    assert releve.pytorch == "2.12.0+rocm7.14.0"
    assert releve.noeuds == frozenset(OBJECT_INFO)
    assert releve.appareil_principal.vram_total == 21458059264


def test_la_sonde_lit_le_CONTENU_des_listes_deroulantes(releve):
    """C'est tout l'intérêt de `/object_info` : un graphe stocke le NOM d'un fichier, pas un
    identifiant. Sans la liste, « ce modèle existe-t-il ici » est indécidable."""
    assert releve.liste("UnetLoaderGGUF", "unet_name") == ("qwen-image-2512-Q4_1.gguf",)
    assert releve.liste("KSampler", "sampler_name") == ("euler", "heun")


def test_une_liste_VIDE_n_est_pas_une_liste_ABSENTE(releve):
    """`ModelPatchLoader` expose une liste vide sur ce serveur (relevé le 2026-08-30) : le
    nœud existe, aucun poids n'est installé. `()` est un constat, `None` est une ignorance."""
    assert releve.liste("ModelPatchLoader", "name") == ()
    assert releve.liste("KSampler", "champ_inexistant") is None


def test_les_noeuds_TIERS_sont_nommes_avec_leur_module(releve):
    """La liste des dossiers de `custom_nodes/` ne dit pas lesquels ont réellement chargé ;
    `python_module` le dit. C'est ce qui répond à l'étape 0.1 du plan, mécaniquement."""
    assert releve.tiers == {"ComfyUI-GGUF": ["UnetLoaderGGUF"]}


def test_la_variante_d_installation_se_deduit_du_python_EMBARQUE(releve):
    assert releve.variante == "portable/standalone"


def test_une_installation_non_embarquee_ne_pretend_PAS_savoir_laquelle():
    """Desktop et `git clone` dans un venv lancent tous deux un Python non embarqué : la
    sonde le dit au lieu de choisir, parce que les deux ne rangent pas les modèles pareil."""
    stats = {**SYSTEM_STATS,
             "system": {**SYSTEM_STATS["system"], "embedded_python": False}}
    releve = sonde_mod.sonder("http://x", transport=TransportFactice(stats=stats))
    assert releve.variante == "installée (Desktop ou venv)"


def test_sans_embedded_python_la_variante_est_INDETERMINEE():
    systeme = {c: v for c, v in SYSTEM_STATS["system"].items() if c != "embedded_python"}
    releve = sonde_mod.sonder("http://x", transport=TransportFactice(
        stats={**SYSTEM_STATS, "system": systeme}))
    assert releve.variante == "indéterminée"


# ───────────────────  Le serveur éteint, et ce qu'il ne prouve pas  ───────────────────

def test_un_serveur_ETEINT_ne_dit_pas_que_les_noeuds_manquent():
    """⚠ **Le test central du module.** Un relevé injoignable rend `None` sur chaque liste :
    le validateur en déduit « non fait », jamais « absent ». Sans cette distinction, éteindre
    ComfyUI ferait refuser les trois graphes du dépôt."""
    releve = sonde_mod.sonder("http://127.0.0.1:8188", transport=TransportMuet())
    assert releve.joignable is False
    assert "connexion refusée" in releve.erreur
    assert releve.liste("UnetLoaderGGUF", "unet_name") is None
    assert releve.noeuds == frozenset()


def test_un_serveur_eteint_ne_LEVE_pas():
    """Un serveur qui ne répond pas est une situation, pas une panne : `--check` doit pouvoir
    l'afficher et continuer son diagnostic."""
    releve = sonde_mod.sonder("http://x", transport=TransportMuet())
    assert "INJOIGNABLE" in "\n".join(releve.resume())


# ─────────────────────────  La marge de VRAM, et sa lecture  ─────────────────────────

def test_la_marge_compte_ce_que_pytorch_a_deja_RESERVE(releve):
    """⚠ Sans ce « plus », la vérification de VRAM serait un faux avertissement à chaque
    seconde génération : après un run, ComfyUI garde 12 083 Mio résidents et le libre tombe
    sous le pic, alors que relancer le même graphe ne recharge rien."""
    appareil = releve.appareil_principal
    assert appareil.marge_octets == appareil.vram_libre + appareil.torch_total
    assert appareil.marge_octets > appareil.vram_libre


# ──────────────────────────────  Le journal du serveur  ──────────────────────────────

def test_le_journal_ne_retient_que_les_lignes_qui_DECIDENT():
    journal = {"entries": [
        {"m": "got prompt"},
        {"m": "model weight dtype torch.float8_e4m3fn"},
        {"m": "Requested to load QwenImageTEModel_"},
        {"m": "loaded partially 9000.0 8900.0 lowvram patches: 42"},
        {"m": "Prompt executed in 103.70 seconds"}]}
    releve = sonde_mod.journal_serveur(
        "http://x", transport=TransportFactice(journal=journal))
    assert releve["disponible"] is True
    assert releve["rogne"] is True
    assert not any("got prompt" in ligne for ligne in releve["lignes"])
    assert any("Prompt executed in 103.70" in ligne for ligne in releve["lignes"])


def test_un_journal_SANS_rognage_le_dit():
    journal = {"entries": [{"m": "loaded completely 14000.0 12000.0"},
                           {"m": "Prompt executed in 103.70 seconds"}]}
    releve = sonde_mod.journal_serveur("http://x",
                                       transport=TransportFactice(journal=journal))
    assert releve["rogne"] is False


def test_une_route_de_journal_ABSENTE_n_est_pas_une_panne():
    """La route `/internal/logs/raw` n'existe pas sur toutes les versions. Une trace qui
    manque ne doit pas faire échouer un run dont l'image est produite."""
    releve = sonde_mod.journal_serveur("http://x", transport=TransportFactice())
    assert releve["disponible"] is False
    assert "/internal/logs/raw" in releve["motif"]


def test_le_journal_tolere_une_chaine_brute():
    releve = sonde_mod.journal_serveur(
        "http://x", transport=TransportFactice(journal="Prompt executed in 12.00 seconds\n"))
    assert releve["lignes"] == ["Prompt executed in 12.00 seconds"]


# ─────────────────────────────  Ce que la sonde n'est pas  ─────────────────────────────

def test_la_sonde_n_envoie_AUCUN_post():
    """⚠ Critère 2 du `PLAN-28` : la sonde **ne peut pas générer**. Elle ne connaît que des
    routes en lecture ; générer reste le travail de `run_illustration.py`, qui porte la porte
    humaine et le marquage."""
    transport = TransportFactice(journal={"entries": []})
    sonde_mod.sonder("http://x", transport=transport)
    sonde_mod.journal_serveur("http://x", transport=transport)
    assert transport.postes == []
    assert set(transport.vus) <= {"/system_stats", "/object_info", "/internal/logs/raw"}
