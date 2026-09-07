# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`illustration/validation.py` — les vérifications 1 à 5, chacune sur son cas réel.

⚠ **La sixième (le nœud de sortie) et le graphe candidat sont dans
`tests/test_illustration_canaux.py`**, avec le reste du `PLAN-30`.

Le critère 3 du `PLAN-28` demande que `--valider` attrape « au moins : format écran, nœud
absent, modèle absent, incohérence pas/guidage, canaux déclarés », et que le tableau des cinq
vérifications soit publié « avec, pour chacune, un cas réel où elle aurait servi ». Le tableau
est dans `docs/mesures/comfy-visible-2026-09-02.md` ; les cinq tests sont ici, et chacun cite
la ligne du §9 de `docs/procedures/comfyui.md` qu'il rejoue.

⚠ **Aucun de ces tests ne parle à un serveur.** Le `/object_info` est un dictionnaire écrit à
la main, et c'est ce que le critère 8 du plan exige.
"""
import json

import pytest

from illustration import sonde as sonde_mod
from illustration import validation as validation_mod
from tests.test_illustration_sonde import OBJECT_INFO, SYSTEM_STATS, TransportFactice

#: Un graphe minimal mais **réaliste** : le chargeur GGUF du dépôt, sa LoRA Lightning, un
#: encodeur de texte et un échantillonneur qui portent leurs marqueurs.
GRAPHE = {
    "1": {"class_type": "UnetLoaderGGUF",
          "inputs": {"unet_name": "qwen-image-2512-Q4_1.gguf"}},
    "2": {"class_type": "LoraLoaderModelOnly",
          "inputs": {"lora_name": "Qwen-Image-2512-Lightning-4steps-V1.0-bf16.safetensors",
                     "model": ["1", 0]}},
    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "%prompt%"}},
    "7": {"class_type": "KSampler",
          "inputs": {"seed": "%graine%", "steps": "%pas%", "cfg": "%guidage%"}},
    "8": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
    # ⚠ **Ajouté au lot 30, et ce n'est pas cosmétique.** La sixième vérification refuse un
    # graphe sans nœud de sortie : ComfyUI l'exécuterait et ne publierait rien dans
    # `/history`. Ce fixtur était donc, jusqu'ici, un graphe qui ne pouvait PAS marcher.
    "9": {"class_type": "SaveImage",
          "inputs": {"images": ["8", 0], "filename_prefix": "angelith-test"}},
}

#: Le même serveur factice que la sonde, plus les deux nœuds que ce graphe utilise.
INFO = {**OBJECT_INFO,
        "LoraLoaderModelOnly": {
            "input": {"required": {"lora_name": [
                ["Qwen-Image-2512-Lightning-4steps-V1.0-bf16.safetensors"], {}]}},
            "python_module": "nodes"},
        "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {}]}},
                           "python_module": "nodes"},
        "SaveImage": {"input": {"required": {"filename_prefix": ["STRING", {}]}},
                      "python_module": "nodes"},
        "PreviewImage": {"input": {"required": {}}, "python_module": "nodes"}}


def _releve(object_info=None, stats=None):
    return sonde_mod.sonder("http://x", transport=TransportFactice(
        object_info=INFO if object_info is None else object_info, stats=stats))


def _graphe(tmp_path, contenu=None, *, nom="w.api.json"):
    chemin = tmp_path / nom
    chemin.write_text(json.dumps(GRAPHE if contenu is None else contenu), encoding="utf-8")
    return chemin


@pytest.fixture
def releve():
    return _releve()


# ═══════  Vérification 1 — le format API, et il le dit AVANT le GPU  ═══════

def test_un_export_au_format_ECRAN_est_refuse(tmp_path, releve):
    """§9, ligne 6 : « Angelith dit que le workflow n'est pas exploitable ». Le client savait
    déjà le dire — il le disait au moment de générer, donc après le déchargement du LLM."""
    chemin = tmp_path / "ecran.json"
    chemin.write_text(json.dumps({"nodes": [{"id": 1, "type": "KSampler"}], "links": []}),
                      encoding="utf-8")
    rapport = validation_mod.valider(chemin, releve=releve)
    assert not rapport.ok
    assert rapport.refus[0].code == "format"
    assert "Save (API Format)" in rapport.refus[0].correction


def test_un_fichier_absent_dit_quoi_faire(tmp_path, releve):
    rapport = validation_mod.valider(tmp_path / "rien.json", releve=releve)
    assert rapport.refus[0].code == "fichier_absent"
    assert "illustration.comfyui.workflow" in rapport.refus[0].correction


# ═══════  Vérification 2 — un nœud absent du serveur  ═══════

def test_un_noeud_ABSENT_du_serveur_est_refuse_avant_le_gpu(tmp_path):
    """§7 : `UnetLoaderGGUF` n'existe que si `ComfyUI-GGUF` est installé. Sur un serveur qui
    ne l'a pas, le graphe du dépôt échoue **au premier appel**, après le chargement des
    poids — c'est-à-dire au pire moment."""
    sans_gguf = {c: v for c, v in INFO.items() if c != "UnetLoaderGGUF"}
    rapport = validation_mod.valider(_graphe(tmp_path), releve=_releve(sans_gguf))
    refus = [c for c in rapport.refus if c.code == "noeud_absent"]
    assert len(refus) == 1
    assert "UnetLoaderGGUF" in refus[0].quoi
    assert "custom_nodes" in refus[0].correction and "REDÉMARRE" in refus[0].correction


def test_un_nom_PROCHE_est_proposé(tmp_path):
    """Le message porte la correction, pas seulement le constat : si le serveur expose un nom
    voisin, il est nommé."""
    graphe = {**GRAPHE, "1": {"class_type": "UnetLoaderGGUFF",
                              "inputs": {"unet_name": "qwen-image-2512-Q4_1.gguf"}}}
    rapport = validation_mod.valider(_graphe(tmp_path, graphe), releve=_releve())
    refus = [c for c in rapport.refus if c.code == "noeud_absent"][0]
    assert "UnetLoaderGGUF" in refus.correction


# ═══════  Vérification 3 — un fichier de modèle absent de la liste  ═══════

def test_un_modele_RENOMME_est_attrape_dans_la_liste_du_noeud(tmp_path, releve):
    """§9, ligne 7 : « Un modèle n'apparaît pas dans la liste ». Un graphe versionné stocke le
    NOM du fichier : renommer un modèle, ou changer de machine, casse le graphe."""
    graphe = {**GRAPHE, "1": {"class_type": "UnetLoaderGGUF",
                              "inputs": {"unet_name": "qwen-image-2512-Q4_0.gguf"}}}
    rapport = validation_mod.valider(_graphe(tmp_path, graphe), releve=releve)
    refus = [c for c in rapport.refus if c.code == "modele_absent"][0]
    assert "qwen-image-2512-Q4_0.gguf" in refus.quoi
    # Le nom réellement exposé est proposé à coller.
    assert "qwen-image-2512-Q4_1.gguf" in refus.correction


def test_une_liste_VIDE_dit_de_redemarrer_le_serveur(tmp_path):
    """`ModelPatchLoader` expose une liste vide (relevé le 2026-08-30) : le remède n'est pas
    « colle un autre nom », c'est « range le fichier, puis RELANCE le serveur » — ComfyUI ne
    relit ses dossiers qu'au démarrage."""
    graphe = {"9": {"class_type": "ModelPatchLoader", "inputs": {"name": "controlnet.safetensors"}}}
    rapport = validation_mod.valider(_graphe(tmp_path, graphe), releve=_releve())
    refus = [c for c in rapport.refus if c.code == "modele_absent"][0]
    assert "AUCUN fichier" in refus.correction


def test_un_MARQUEUR_n_est_pas_un_fichier_absent(tmp_path, releve):
    """⚠ `%reference_1%` sera remplacé par le nom d'une image téléversée : le compter comme
    manquant ferait refuser le seul graphe du dépôt qui porte des références."""
    graphe = {**GRAPHE, "10": {"class_type": "LoadImage",
                               "inputs": {"image": "%reference_1%"}}}
    rapport = validation_mod.valider(_graphe(tmp_path, graphe), releve=releve)
    assert not [c for c in rapport.refus if c.code == "modele_absent"]


# ═══════  Vérification 4 — les canaux que le graphe déclare  ═══════

def test_les_canaux_declares_sont_ceux_du_graphe(tmp_path, releve):
    rapport = validation_mod.valider(_graphe(tmp_path), releve=releve)
    assert rapport.canaux == frozenset({"prompt"})
    graphe = {**GRAPHE, "10": {"class_type": "LoadImage",
                               "inputs": {"image": "%reference_1%"}}}
    autre = validation_mod.valider(_graphe(tmp_path, graphe, nom="b.api.json"), releve=releve)
    assert autre.canaux == frozenset({"prompt", "references"})


def test_un_graphe_SANS_aucun_marqueur_est_une_reserve(tmp_path, releve):
    graphe = {"7": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 4, "cfg": 1.0}}}
    rapport = validation_mod.valider(_graphe(tmp_path, graphe), releve=releve)
    assert [c for c in rapport.reserves if c.code == "aucun_canal"]


# ═══════  Vérification 5 — pas / guidage, la seule qui ne dit RIEN côté ComfyUI  ═══════

def test_une_lora_LIGHTNING_avec_un_guidage_de_4_est_refusee(tmp_path, releve):
    """§9, ligne 1 : « Images brûlées, contrastes saturés » — `cfg 4` avec la LoRA Lightning,
    distillée sans guidage. ⚠ **C'est la seule des cinq dont l'échec ne produit aucun message
    côté ComfyUI** : il exécute, et l'image sort. Il faut avoir l'œil pour la reconnaître."""
    rapport = validation_mod.valider(_graphe(tmp_path), releve=releve, pas=4, guidage=4.0)
    refus = [c for c in rapport.refus if c.code == "guidage_incoherent"][0]
    assert "1.0" in refus.correction and "brûlées" in refus.correction


def test_un_guidage_de_1_passe(tmp_path, releve):
    rapport = validation_mod.valider(_graphe(tmp_path), releve=releve, pas=4, guidage=1.0)
    assert rapport.ok


def test_cinquante_pas_sur_une_lora_4_pas_est_une_reserve(tmp_path, releve):
    """Le lot 25 l'a mesuré : de 4 à 50 pas, −24 % d'écart de style pour 12,5 fois plus de
    calcul. C'est une réserve et pas un refus — l'image sera juste, elle coûtera cher."""
    rapport = validation_mod.valider(_graphe(tmp_path), releve=releve, pas=50, guidage=1.0)
    assert [c for c in rapport.reserves if c.code == "pas_inutiles"]
    assert rapport.ok


def test_sans_pas_ni_guidage_la_cinquieme_verification_ne_se_prononce_PAS(tmp_path, releve):
    rapport = validation_mod.valider(_graphe(tmp_path), releve=releve)
    # ⚠ La réserve `copie_non_marquee` du lot 30 est là sur TOUT graphe à `SaveImage` : elle
    # ne dit rien des pas ni du guidage, et ce test ne porte que sur eux.
    assert rapport.ok
    assert [c.code for c in rapport.reserves] == ["copie_non_marquee"]


def test_un_graphe_qui_FIXE_ses_pas_dit_que_la_config_est_sans_effet(tmp_path, releve):
    """Fixer une valeur dans le graphe est légitime ; croire la régler dans `config.yaml` ne
    l'est pas."""
    graphe = {**GRAPHE, "7": {"class_type": "KSampler",
                              "inputs": {"seed": "%graine%", "steps": 20, "cfg": "%guidage%"}}}
    rapport = validation_mod.valider(_graphe(tmp_path, graphe), releve=releve,
                                     pas=4, guidage=1.0)
    reserve = [c for c in rapport.reserves if c.code == "pas_fixe"][0]
    assert "SANS EFFET" in reserve.correction


# ═══════  Le serveur éteint : « non fait » n'est pas « passé »  ═══════

def test_sans_serveur_les_verifications_2_et_3_sont_NON_FAITES(tmp_path):
    """⚠ Le garde-fou contre le faux avertissement. Un validateur qui refuserait un nœud
    parce que ComfyUI est éteint refuserait les trois graphes du dépôt à chaque `--check`
    hors ligne — et un avertissement faux cesse d'être lu."""
    rapport = validation_mod.valider(_graphe(tmp_path), releve=None, pas=4, guidage=1.0)
    assert rapport.ok
    assert "NON FAIT" in rapport.verifications["nœuds exposés"]
    assert "NON FAIT" in rapport.verifications["fichiers et listes"]
    # Les vérifications 1, 4 et 5 se font sur le fichier seul : elles, elles ont eu lieu.
    assert rapport.verifications["format API"].startswith("✓")
    assert rapport.canaux == frozenset({"prompt"})


def test_hors_ligne_le_guidage_incoherent_est_QUAND_MEME_attrape(tmp_path):
    """La cinquième vérification ne demande rien au serveur : elle marche sur le PC
    secondaire, celui qui n'a ni ComfyUI ni carte."""
    rapport = validation_mod.valider(_graphe(tmp_path), releve=None, pas=4, guidage=4.0)
    assert [c for c in rapport.refus if c.code == "guidage_incoherent"]


# ═══════  Les graphes du dépôt, tels qu'ils sont versionnés  ═══════

def test_les_graphes_du_depot_sont_au_format_API_et_declarent_leurs_canaux():
    """Un graphe du dépôt qui cesserait d'être au format API, ou perdrait son `%prompt%`,
    casserait tous les runs sans qu'aucun test ne le voie.

    ⚠ **Quatre depuis le lot 30**, dont un CANDIDAT — et le candidat passe aussi : la
    rétrogradation ne porte que sur « nœud absent » et « modèle absent », qui ne se prononcent
    de toute façon pas ici (`releve=None`)."""
    from pathlib import Path

    dossier = Path(__file__).resolve().parents[1] / "illustration" / "workflows"
    graphes = sorted(dossier.glob("*.api.json"))
    assert len(graphes) == 4
    porteurs_de_references = 0
    porteurs_de_controle = 0
    for chemin in graphes:
        rapport = validation_mod.valider(chemin, releve=None, pas=4, guidage=1.0)
        assert rapport.ok, (chemin.name, [c.quoi for c in rapport.refus])
        assert "prompt" in rapport.canaux
        porteurs_de_references += "references" in rapport.canaux
        porteurs_de_controle += "image_controle" in rapport.canaux
    # Deux portent %reference_1% depuis le lot 30 : le graphe d'édition et son dérivé candidat.
    assert porteurs_de_references == 2
    # Et UN SEUL porte %image_controle% — celui qui est marqué candidat.
    assert porteurs_de_controle == 1


# ═══════  La VRAM, dite AVANT le déchargement du LLM  ═══════

def test_une_vram_trop_courte_est_dite_avec_son_pic_et_sa_date():
    """L28.2 : « dites-le AVANT de décharger le LLM, pas après »."""
    stats = {**SYSTEM_STATS, "devices": [
        {**SYSTEM_STATS["devices"][0], "vram_free": 1000000000, "torch_vram_total": 0}]}
    constats = validation_mod.verifier_vram(_releve(stats=stats))
    assert constats and "2026-08-29" in constats[0].quoi
    assert "POST /free" in constats[0].correction


def test_la_vram_RESERVEE_par_pytorch_compte_au_credit():
    """⚠ Le faux avertissement évité : après un run, ComfyUI garde ses modèles résidents. Le
    libre tombe sous le pic alors que relancer le même graphe ne recharge rien."""
    stats = {**SYSTEM_STATS, "devices": [
        {**SYSTEM_STATS["devices"][0], "vram_free": 1000000000,
         "torch_vram_total": 20000000000}]}
    assert validation_mod.verifier_vram(_releve(stats=stats)) == []


def test_sans_serveur_la_vram_ne_se_prononce_pas():
    assert validation_mod.verifier_vram(None) == []


# ═══════  La phase image refuse AVANT la bascule VRAM — L28.2  ═══════

def test_la_phase_image_refuse_le_graphe_AVANT_de_decharger_le_llm(tmp_path, monkeypatch):
    """⚠ **Le refus tombe avant que la carte ne soit rendue.** Un guidage incompatible avec la
    LoRA du graphe coûtait jusqu'ici le déchargement du LLM et le chargement de 12,84 Go de
    poids pour être découvert — et il ne produisait même pas d'erreur, juste une image
    brûlée."""
    from illustration import orchestrateur, sonde

    fige = _releve()
    monkeypatch.setattr(sonde, "sonder", lambda *a, **k: fige)
    reg = {"moteur": "comfyui", "image": {"pas": 4, "guidage": 4.0},
           "comfyui": {"workflow": str(_graphe(tmp_path)), "base_url": "http://x"}}
    with pytest.raises(ValueError) as echec:
        orchestrateur._valider_le_graphe(reg, print)
    message = str(echec.value)
    assert "AVANT la bascule VRAM" in message
    assert "guidage_incoherent" in message
    assert "tools/comfy.py --valider" in message


def test_un_moteur_FACTICE_n_a_pas_de_graphe_a_valider(tmp_path):
    from illustration import orchestrateur

    orchestrateur._valider_le_graphe(
        {"moteur": "factice", "image": {"pas": 4, "guidage": 4.0},
         "comfyui": {"workflow": "", "base_url": ""}}, print)


def test_un_graphe_VALIDE_laisse_passer(tmp_path, monkeypatch):
    from illustration import orchestrateur, sonde

    fige = _releve()
    monkeypatch.setattr(sonde, "sonder", lambda *a, **k: fige)
    orchestrateur._valider_le_graphe(
        {"moteur": "comfyui", "image": {"pas": 4, "guidage": 1.0},
         "comfyui": {"workflow": str(_graphe(tmp_path)), "base_url": "http://x"}}, print)
