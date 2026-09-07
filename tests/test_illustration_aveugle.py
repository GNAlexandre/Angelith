# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`PLAN-29` L29.2 — le protocole en aveugle : la discipline, testée.

Le module `illustration/aveugle.py` est délibérément bête ; sa valeur est dans trois règles,
et ce sont ces trois-là que ces tests tiennent :

1. **le seuil est fixé à la création**, écrit dans le protocole, et `rapport` le lit **de
   là** — un seuil qu'on peut passer en option après avoir vu les résultats ne mesure rien ;
2. **rien ne trahit la configuration** — ni le nom du fichier présenté, ni l'ordre d'écriture
   sur le disque ;
3. **les réponses sont horodatées et conservées**, en ajout seul.

Plus le livrable central du lot, qui n'est pas un verdict : **l'accord entre le juge humain
et le juge automatique** sur les mêmes paires.

⚠ Aucun encodeur, aucun GPU, aucun serveur. Les « scores automatiques » sont un dictionnaire.
"""
import json

import pytest

from illustration import aveugle as aveugle_mod


def _candidats(n=6, configurations=("avec", "sans")):
    return [{"image": f"/img/{i}.png", "configuration": configurations[i % len(configurations)]}
            for i in range(n)]


def _protocole(nombre=4, seuil=3, configurations=("avec", "sans")):
    liste = aveugle_mod.paires(_candidats(configurations=configurations), nombre=nombre)
    return aveugle_mod.protocole(liste, reference="/img/ref.png", seuil=seuil)


def _reponses(doc, choix):
    """`choix` est `{n: "A"|"B"|"="|"?"}`."""
    return [aveugle_mod.reponse(n, v) for n, v in choix.items()]


# ────────────────────────────  Règle 1 — le seuil d'avance  ────────────────────────────

def test_le_seuil_est_ECRIT_dans_le_protocole():
    doc = _protocole(seuil=14)
    assert doc["seuil"] == 14
    assert doc["cree"]


def test_un_protocole_sans_seuil_est_REFUSE_plutot_que_de_retomber_sur_le_defaut():
    """⚠ La règle qu'on viole toujours. Un rapport calculé contre un seuil que le protocole
    ne portait pas serait le seuil ajusté après coup que L29.2 interdit."""
    doc = _protocole()
    doc["seuil"] = None
    with pytest.raises(aveugle_mod.ProtocoleInvalide, match="seuil"):
        aveugle_mod.rapport(doc, [])


def test_le_rapport_lit_le_seuil_du_FICHIER_et_de_nulle_part_ailleurs():
    doc = _protocole(nombre=4, seuil=3)
    # 3 voix pour « avec » sur 4 paires, toutes opposant les deux configurations.
    doc["paires"] = [{"n": i, "gauche": f"/img/g{i}.png", "droite": f"/img/d{i}.png",
                      "_config_gauche": "avec", "_config_droite": "sans"}
                     for i in range(1, 5)]
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "A", 2: "A", 3: "A", 4: "B"}))
    assert resultat["seuil"] == 3
    assert resultat["verdict"] is True

    doc["seuil"] = 4
    assert aveugle_mod.rapport(doc, _reponses(doc, {1: "A", 2: "A", 3: "A",
                                                    4: "B"}))["verdict"] is False


def test_un_seuil_non_franchi_est_un_RESULTAT_pas_un_echec():
    doc = _protocole(nombre=2, seuil=2)
    doc["paires"] = [{"n": 1, "gauche": "a", "droite": "b",
                      "_config_gauche": "avec", "_config_droite": "sans"},
                     {"n": 2, "gauche": "c", "droite": "d",
                      "_config_gauche": "avec", "_config_droite": "sans"}]
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "A", 2: "B"}))
    assert resultat["verdict"] is False
    assert "c'est son résultat" in resultat["motif"]


def test_le_seuil_ne_s_applique_PAS_a_six_oppositions_et_le_dit():
    """« 14 sur 20 » compare DEUX configurations. Vingt paires qui en opposeraient six deux à
    deux ne se résument pas ainsi, et trancher quand même serait un chiffre faux."""
    doc = _protocole(nombre=3, seuil=2)
    doc["paires"] = [{"n": 1, "gauche": "a", "droite": "b",
                      "_config_gauche": "x", "_config_droite": "y"},
                     {"n": 2, "gauche": "c", "droite": "d",
                      "_config_gauche": "y", "_config_droite": "z"},
                     {"n": 3, "gauche": "e", "droite": "f",
                      "_config_gauche": "x", "_config_droite": "z"}]
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "A", 2: "A", 3: "A"}))
    assert resultat["verdict"] is None
    assert "n'en résume pas" in resultat["motif"]
    assert resultat["voix"]["x"] == 2


# ──────────────────────  Règle 2 — rien ne trahit la configuration  ──────────────────────

def test_l_ordre_A_B_est_tire_au_sort_et_pas_celui_des_candidats():
    """Si l'ordre suivait celui des candidats, la configuration se lirait dans la colonne."""
    liste = aveugle_mod.paires(_candidats(n=12), nombre=20, graine=7)
    gauches = {p["_config_gauche"] for p in liste}
    assert gauches == {"avec", "sans"}, "toutes les paires mettent la même config à gauche"


def test_le_tirage_est_reproductible_a_graine_egale():
    """Un protocole non reproductible n'est pas un protocole : deux passes sur les mêmes
    images doivent pouvoir se comparer."""
    a = aveugle_mod.paires(_candidats(n=8), nombre=6, graine=3)
    b = aveugle_mod.paires(_candidats(n=8), nombre=6, graine=3)
    assert a == b
    assert a != aveugle_mod.paires(_candidats(n=8), nombre=6, graine=4)


def test_les_paires_qui_OPPOSENT_deux_configurations_passent_en_premier():
    """Deux images de la même configuration ne disent rien sur la configuration. Elles ne
    sont pas jetées — l'accord humain/automatique n'a besoin que de deux images — mais
    elles passent après."""
    liste = aveugle_mod.paires(_candidats(n=6), nombre=4, graine=11)
    assert all(p["_config_gauche"] != p["_config_droite"] for p in liste)


def test_la_configuration_vit_sous_une_cle_a_TIRET_BAS():
    """La convention du dépôt pour « une clé qu'on n'affiche pas » (cf. `_interdits` d'un
    manifeste). Le rendu de `tools/juge_humain.py` ne publie que ce qui n'en porte pas."""
    paire = aveugle_mod.paires(_candidats(), nombre=1)[0]
    assert {"_config_gauche", "_config_droite"} <= set(paire)
    assert not any(cle.startswith("_") and "config" not in cle for cle in paire)


# ──────────────────────  Règle 3 — les réponses, en ajout seul  ──────────────────────

def test_une_reponse_porte_son_horodatage():
    ligne = aveugle_mod.reponse(3, "a", secondes=12.5)
    assert ligne["n"] == 3 and ligne["reponse"] == "A"
    assert ligne["horodatage"].endswith("+00:00")
    assert ligne["secondes"] == 12.5


def test_une_reponse_hors_vocabulaire_est_refusee():
    with pytest.raises(ValueError, match="hors de"):
        aveugle_mod.reponse(1, "peut-être")


def test_se_reprendre_AJOUTE_une_ligne_et_n_en_efface_aucune(tmp_path):
    """« Je me suis repris à la paire 7 » doit rester lisible six mois plus tard."""
    journal = tmp_path / aveugle_mod.NOM_REPONSES
    aveugle_mod.ajouter(journal, aveugle_mod.reponse(7, "A"))
    aveugle_mod.ajouter(journal, aveugle_mod.reponse(7, "B"))
    lignes = aveugle_mod.lire_reponses(journal)
    assert len(lignes) == 2
    assert aveugle_mod.dernieres(lignes)[7]["reponse"] == "B"


def test_une_ligne_illisible_est_sautee_et_jamais_devinee(tmp_path):
    journal = tmp_path / aveugle_mod.NOM_REPONSES
    aveugle_mod.ajouter(journal, aveugle_mod.reponse(1, "A"))
    with journal.open("a", encoding="utf-8") as flux:
        flux.write("{ceci n'est pas du JSON\n")
        flux.write(json.dumps({"n": 2, "reponse": "peut-être"}) + "\n")
    assert [ligne["n"] for ligne in aveugle_mod.lire_reponses(journal)] == [1]


def test_un_journal_absent_rend_une_liste_vide(tmp_path):
    assert aveugle_mod.lire_reponses(tmp_path / "rien.jsonl") == []


# ────────────────  Le livrable central — l'accord humain / automatique  ────────────────

def _doc_pour_accord():
    doc = _protocole(nombre=3, seuil=2)
    doc["paires"] = [{"n": i, "gauche": f"g{i}", "droite": f"d{i}",
                      "_config_gauche": "avec", "_config_droite": "sans"}
                     for i in (1, 2, 3)]
    return doc


def test_l_accord_compte_les_paires_ou_les_DEUX_se_prononcent():
    doc = _doc_pour_accord()
    scores = {"g1": 0.9, "d1": 0.1,        # l'automatique dit « gauche »
              "g2": 0.1, "d2": 0.9,        # il dit « droite »
              "g3": 0.5, "d3": 0.5}        # ex æquo : il ne dit rien
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "A", 2: "A", 3: "A"}), scores)
    assert resultat["accord_n"] == 2
    assert resultat["accord_oui"] == 1
    assert resultat["accord"] == 0.5


def test_sans_encodeur_l_accord_est_None_et_JAMAIS_zero():
    """⚠ Un accord de 0 est une mesure (« ils ne sont jamais d'accord »), une absence
    d'encodeur n'en est pas une. Le dépôt distingue déjà les deux (`juge.mesurer`)."""
    doc = _doc_pour_accord()
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "A"}), None)
    assert resultat["accord"] is None
    assert resultat["accord_n"] == 0


def test_un_ex_aequo_automatique_ne_compte_pas_comme_un_desaccord():
    doc = _doc_pour_accord()
    scores = {"g1": 0.4, "d1": 0.4, "g2": 0.4, "d2": 0.4, "g3": 0.4, "d3": 0.4}
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "A", 2: "B", 3: "A"}), scores)
    assert resultat["accord"] is None


def test_une_abstention_sort_du_denominateur_et_ne_compte_pas_contre():
    doc = _doc_pour_accord()
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "A", 2: "?", 3: "?"}))
    assert resultat["repondues"] == 1
    assert resultat["voix"] == {"avec": 1.0}


def test_une_egalite_est_un_JUGEMENT_et_vaut_une_demi_voix_de_chaque_cote():
    """⚠ `=` et `?` ne sont pas la même chose : l'un juge que les deux se valent, l'autre
    s'abstient. Les confondre coûterait le sens de la mesure."""
    doc = _doc_pour_accord()
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "="}))
    assert resultat["repondues"] == 1
    assert resultat["voix"] == {"avec": 0.5, "sans": 0.5}


def test_une_paire_sans_reponse_apparait_au_detail_plutot_que_de_disparaitre():
    doc = _doc_pour_accord()
    resultat = aveugle_mod.rapport(doc, _reponses(doc, {1: "A"}))
    assert resultat["paires"] == 3 and resultat["repondues"] == 1
    assert [d["réponse"] for d in resultat["detail"]].count("(sans réponse)") == 2


def test_le_protocole_dit_combien_de_paires_il_porte():
    doc = _protocole(nombre=4)
    assert doc["sur"] == len(doc["paires"])
    assert doc["version"] == aveugle_mod.VERSION
