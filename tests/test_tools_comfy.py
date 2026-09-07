# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`tools/comfy.py` — les cinq sous-commandes, et **la preuve qu'aucune ne génère**.

Le critère 2 du `PLAN-28` demande que l'outil « ne puisse pas générer ». Ce n'est pas une
propriété qui se relit dans les sources : elle se **compte**. `test_aucune_sous_commande_n_envoie_de_generation`
fait tourner chaque sous-commande contre un serveur factice qui enregistre chaque requête, et
vérifie qu'aucun `POST` n'est parti.

⚠ **Pourquoi ce garde-fou existe.** `run_illustration.py` porte la porte humaine (`valide:
true`, ou une question à l'écran) et le marquage AI Act. Un outil capable d'envoyer un
`/prompt` serait une **seconde porte, non gardée** — et le dépôt tient la première par un test
d'exécution (`illustration/frontiere.py`), pas par une relecture.
"""
import json

import pytest

from tests.test_illustration_sonde import SYSTEM_STATS, TransportFactice
from tests.test_illustration_validation import GRAPHE, INFO

comfy = pytest.importorskip("tools.comfy")


@pytest.fixture
def config(tmp_path):
    """Une configuration minimale qui pointe sur un workflow réel écrit dans `tmp_path`."""
    workflow = tmp_path / "w.api.json"
    workflow.write_text(json.dumps(GRAPHE), encoding="utf-8")
    return {"chemins": {"build": str(tmp_path / "build"), "sources": str(tmp_path / "src")},
            "illustration": {"actif": True, "moteur": "comfyui",
                             "image": {"pas": 4, "guidage": 1.0},
                             "comfyui": {"base_url": "http://127.0.0.1:8188",
                                         "workflow": str(workflow)}}}


@pytest.fixture
def transport():
    return TransportFactice(object_info=INFO, journal={"entries": [
        {"m": "loaded completely 14000.0 12000.0"},
        {"m": "Prompt executed in 103.70 seconds"}]})


# ═══════════════════════  La propriété qui compte : aucune génération  ═══════════════════════

def test_aucune_sous_commande_n_envoie_de_generation(config, transport, tmp_path, capsys):
    """⚠ **Critère 2 du plan.** Trois sous-commandes qui parlent au serveur, zéro `POST`."""
    comfy.commande_sonde(config, transport=transport)
    comfy.commande_valider(config, "*", transport=transport)
    comfy.commande_journal(config, transport=transport)
    assert transport.postes == []
    assert set(transport.vus) <= {"/system_stats", "/object_info", "/internal/logs/raw"}


def test_le_graphe_ne_TELEVERSE_rien(tmp_path):
    """`--graphe` calcule le nom que ComfyUI donnera à chaque référence depuis l'empreinte de
    son contenu : il n'a rien à envoyer pour montrer le graphe exact."""
    from illustration.comfyui import MoteurComfyUI

    reference = tmp_path / "ref.png"
    reference.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
    graphe = {**GRAPHE, "10": {"class_type": "LoadImage",
                               "inputs": {"image": "%reference_1%"}}}
    chemin = tmp_path / "w.api.json"
    chemin.write_text(json.dumps(graphe), encoding="utf-8")
    transport = TransportFactice(object_info=INFO)
    moteur = MoteurComfyUI(chemin, transport=transport, dossier_tome=tmp_path)

    from illustration.moteur import Requete

    substitue, envois = moteur.graphe_substitue(
        Requete(prompt="x", references=("ref.png",)), televerser=False)
    assert transport.postes == []
    assert envois[0]["nom"].startswith("angelith/angelith-")
    assert substitue["10"]["inputs"]["image"] == envois[0]["nom"]


def test_le_nom_televerse_est_le_MEME_avec_ou_sans_serveur(tmp_path):
    """C'est ce qui rend le graphe écrit par `--graphe` identique à celui qui partira : le nom
    porte l'empreinte du contenu, pas un compteur."""
    from illustration.comfyui import MoteurComfyUI, nom_televerse
    from illustration.moteur import Requete

    reference = tmp_path / "ref.png"
    reference.write_bytes(b"\x89PNG\r\n\x1a\n" + b"y" * 40)
    chemin = tmp_path / "w.api.json"
    chemin.write_text(json.dumps({**GRAPHE, "10": {"class_type": "LoadImage",
                                                   "inputs": {"image": "%reference_1%"}}}),
                      encoding="utf-8")
    moteur = MoteurComfyUI(chemin, transport=TransportFactice(object_info=INFO),
                           dossier_tome=tmp_path)
    hors_ligne, _ = moteur.graphe_substitue(Requete(prompt="x", references=("ref.png",)),
                                            televerser=False)
    assert hors_ligne["10"]["inputs"]["image"] == nom_televerse(reference)


# ═══════════════════════════════  --sonde  ═══════════════════════════════

def test_la_sonde_dit_la_version_les_noeuds_tiers_et_la_marge(config, transport, capsys):
    assert comfy.commande_sonde(config, transport=transport) == 0
    sortie = capsys.readouterr().out
    assert "0.34.2" in sortie
    assert "ComfyUI-GGUF" in sortie
    assert "marge" in sortie


def test_la_sonde_rend_1_quand_le_serveur_ne_repond_pas(config, capsys):
    from tests.test_illustration_sonde import TransportMuet

    assert comfy.commande_sonde(config, transport=TransportMuet()) == 1
    assert "INJOIGNABLE" in capsys.readouterr().out


# ═══════════════════════════════  --valider  ═══════════════════════════════

def test_valider_rend_1_sur_un_refus(config, transport, capsys):
    """Un code de sortie non nul est ce qui rend la commande utilisable dans un script."""
    config["illustration"]["image"]["guidage"] = 4.0
    assert comfy.commande_valider(config, config["illustration"]["comfyui"]["workflow"],
                                  transport=transport) == 1
    assert "guidage_incoherent" in capsys.readouterr().out


def test_valider_sans_argument_prend_les_trois_graphes_du_depot(config, transport, capsys):
    comfy.commande_valider(config, "*", transport=transport)
    sortie = capsys.readouterr().out
    for nom in ("qwen-image-2512.api.json", "qwen-image-2512-lightning.api.json",
                "qwen-image-edit-2511.api.json"):
        assert nom in sortie


# ═══════════════════════════════  --diff  ═══════════════════════════════

def test_le_diff_nomme_le_champ_qui_a_change():
    """⚠ Un `diff` de texte sur deux graphes est illisible : l'ordre des clés n'a aucun sens.
    On veut lire « la graine a changé », pas « 40 lignes ont changé »."""
    avant = {"7": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 4}}}
    apres = {"7": {"class_type": "KSampler", "inputs": {"seed": 2, "steps": 4}}}
    lignes = comfy.lignes_de_diff(avant, apres)
    assert lignes == ["~ 7.KSampler.seed : 1 → 2"]


def test_le_diff_voit_un_noeud_ajoute_et_un_noeud_retire():
    avant = {"1": {"class_type": "A", "inputs": {}}}
    apres = {"2": {"class_type": "B", "inputs": {}}}
    lignes = comfy.lignes_de_diff(avant, apres)
    assert "− nœud 1 (A) retiré" in lignes and "+ nœud 2 (B) ajouté" in lignes


def test_deux_graphes_identiques_le_disent():
    assert comfy.lignes_de_diff(GRAPHE, GRAPHE) == ["= les deux graphes sont identiques."]


# ═══════════════════════════════  --journal  ═══════════════════════════════

def test_le_journal_dit_qu_il_n_y_a_rien_quand_rien_n_a_ete_produit(config, transport,
                                                                    capsys):
    assert comfy.commande_journal(config, transport=transport) == 0
    assert "Aucune image produite" in capsys.readouterr().out


def test_le_journal_lit_le_graphe_et_les_lignes_ARCHIVES(tmp_path, config, transport,
                                                         capsys):
    """⚠ La distinction du lot : le sidecar porte ce qui a été archivé AU MOMENT du run —
    c'est une trace. Le journal du serveur porte l'état courant de sa console — un souvenir,
    qui s'efface au redémarrage."""
    dossier = tmp_path / "build" / "Projet" / "illustrations"
    dossier.mkdir(parents=True)
    (dossier / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (dossier / "a.png.provenance.json").write_text(json.dumps({
        "image": "a.png", "date": "2026-09-02T10:00:00+00:00", "secondes": 103.7,
        "angelith": "2.22.0", "modele": "qwen", "moteur": "comfyui",
        "payload": {"graine": 42},
        "graphe": {"fichier": "a.png.graphe.json", "noeuds": 12, "sha256": "abc123"},
        "journal_serveur": {"disponible": True, "rogne": True,
                            "lignes": ["loaded partially 9000.0 lowvram patches: 42"]}}),
        encoding="utf-8")
    comfy.commande_journal(config, transport=transport)
    sortie = capsys.readouterr().out
    assert "a.png.graphe.json" in sortie
    assert "lowvram patches: 42" in sortie
    assert "ROGNÉ" in sortie


def test_le_journal_dit_quand_le_graphe_est_ABSENT(tmp_path, config, transport, capsys):
    """Une image produite avant la 2.22.0, ou par le moteur factice, n'a pas de graphe. Le
    dire vaut mieux que d'afficher une ligne vide."""
    dossier = tmp_path / "build" / "Projet" / "illustrations"
    dossier.mkdir(parents=True)
    (dossier / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (dossier / "a.png.provenance.json").write_text(json.dumps(
        {"image": "a.png", "secondes": 1.0, "payload": {}}), encoding="utf-8")
    comfy.commande_journal(config, transport=transport)
    assert "graphe envoyé : ABSENT" in capsys.readouterr().out


def test_le_journal_du_serveur_absent_n_est_pas_une_panne(config, capsys):
    transport = TransportFactice(object_info=INFO, stats=SYSTEM_STATS)  # sans journal
    assert comfy.commande_journal(config, transport=transport) == 0
    assert "indisponible" in capsys.readouterr().out


def test_le_graphe_avertit_quand_la_graine_est_ALEATOIRE(tmp_path, config, capsys):
    """⚠ Le seul écart possible entre le fichier écrit et ce qui partira : `graine: null` est
    tirée À CHAQUE lecture de `requete.yaml`. Comparer deux images produites avec deux graines
    différentes ne mesurerait rien — donc on le dit plutôt que de laisser croire."""
    import yaml

    from illustration import requete as requete_mod

    doc = requete_mod.vide(modele="qwen")
    bloc = requete_mod.image_vide("aya")
    bloc["prompt"] = "une jeune femme"
    bloc["graine"] = None
    doc["images"] = [bloc]
    cible = tmp_path / "requete.yaml"
    cible.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    comfy.commande_graphe(config, str(cible))
    sortie = capsys.readouterr().out
    assert "GRAINE ALÉATOIRE" in sortie
    assert (tmp_path / "graphes" / "aya.api.json").is_file()
