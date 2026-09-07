# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les deux garde-fous d'AVAL du lot 15 : le registre (L7.10) et la relecture (L7.9).

Ils ferment le même trou par deux bouts. La fiche de contexte du tome dit « X vouvoie Y », et
**rien ne vérifiait que la traduction l'avait suivie** — même une fois la fiche branchée, on
ne pouvait pas savoir si elle servait. Et la brique manga n'a **aucun agent en aval** : ce qui
sort du traducteur est dessiné dans la bulle.

Deux principes, testés ici plus que les fonctionnalités elles-mêmes :

1. **Le registre compte, il ne corrige jamais.** Un basculement peut être une scène. Même
   discipline que la dérive lexicale T3 de `terminology` : « signalé au rapport, jamais
   écrit ».
2. **Le relecteur est rejeté par le CODE, pas par le modèle.** Une correction qui ne nomme
   pas une règle connue n'est pas lue. C'est la seule chose qui distingue un relecteur à
   mandat étroit d'un relecteur générique — lequel serait le pire ajout possible.

Aucun appel LLM : le relecteur est un double, et la règle « glossaire » n'en a pas besoin.
"""
from __future__ import annotations

from manga import registre, relecture

# --------------------------------------------------------------------------- #
# Registre — L7.10
# --------------------------------------------------------------------------- #


def test_le_tutoiement_et_le_vouvoiement_sont_reconnus():
    assert registre.detecter("Tu viens avec moi ?") == registre.TUTOIEMENT
    assert registre.detecter("Vous venez avec moi ?") == registre.VOUVOIEMENT
    assert registre.detecter("Ton frère t'attend") == registre.TUTOIEMENT
    assert registre.detecter("Votre frère vous attend") == registre.VOUVOIEMENT


def test_une_replique_sans_deuxieme_personne_ne_compte_pas():
    assert registre.detecter("Il pleuvait sur la ville") == ""


def test_un_mot_qui_contient_tu_n_est_pas_un_tutoiement():
    """`tu` est court et fréquent en composition. Sans ancrage sur des frontières de mot, une
    statue et une vertu suffiraient à faire basculer le registre d'un tome."""
    assert registre.detecter("La statue de la vertu") == ""


def test_une_replique_qui_porte_les_deux_ne_tranche_pas():
    """Dialogue rapporté, ou « vous » pluriel dans une réplique tutoyée : la compter dans les
    deux plateaux ferait mentir le basculement qu'on cherche."""
    assert registre.detecter("Tu leur diras que vous partez") == ""


def test_une_langue_sans_deuxieme_personne_ne_mesure_rien():
    """L'anglais n'a qu'une deuxième personne : « ne rien mesurer » y est la réponse complète,
    la même que `AccordNeutre` donne à l'accord."""
    assert registre.relever_planche(["You are late"], "en") == {}


def test_le_basculement_est_releve_entre_planches_porteuses():
    par_planche = {1: {"tu": 3, "vous": 0},
                   2: {"tu": 0, "vous": 0},      # planche muette : ne fait pas basculer
                   3: {"tu": 0, "vous": 4},
                   4: {"tu": 0, "vous": 2}}

    releve = registre.relever_tome(par_planche)

    assert releve.tutoiement == 3 and releve.vouvoiement == 6
    assert releve.basculements == [3]
    assert releve.dominant() == registre.VOUVOIEMENT


def test_une_planche_qui_mele_les_deux_est_signalee():
    """Le signal le plus actionnable : dans une même planche, deux répliques d'une même scène
    ne devraient pas basculer."""
    releve = registre.relever_tome({7: {"tu": 2, "vous": 1}})

    assert releve.planches_mixtes == [7]


def test_le_releve_ne_corrige_jamais():
    """Il n'existe aucune fonction d'écriture dans ce module, et c'est délibéré : un
    basculement peut être une scène, et c'est un humain qui tranche."""
    assert not [nom for nom in dir(registre)
                if nom.startswith(("corriger", "appliquer", "forcer"))]


# --------------------------------------------------------------------------- #
# Relecture — la règle « glossaire », déterministe et livrée sans modèle
# --------------------------------------------------------------------------- #

GLOSSAIRE = {"personnages": [{"nom": "Inaho", "termes_source": ["界塚"],
                              "variantes": ["Inahô"], "genre": "m"}]}


def test_un_terme_du_glossaire_perdu_a_la_traduction_est_releve():
    manques = relecture.termes_manques(["界塚が来た"], ["Il est arrivé"], GLOSSAIRE)

    assert manques == [(1, "界塚", "Inaho")]


def test_un_terme_rendu_par_une_variante_acceptee_ne_manque_pas():
    assert relecture.termes_manques(["界塚が来た"], ["Inahô est arrivé"], GLOSSAIRE) == []


def test_une_bulle_non_traduite_n_est_pas_un_manque_de_glossaire():
    """Elle est déjà signalée comme vide, par le rapport et par le rattrapage unitaire. La
    compter ici une seconde fois ferait passer un trou de traduction pour une infidélité au
    glossaire, et gonflerait la mesure d'un facteur que personne ne saurait défalquer."""
    assert relecture.termes_manques(["界塚が来た"], [""], GLOSSAIRE) == []


def test_sans_glossaire_rien_n_est_reclame():
    assert relecture.termes_manques(["界塚が来た"], ["Il est arrivé"], None) == []


# --------------------------------------------------------------------------- #
# Relecture — ce que le CODE rejette
# --------------------------------------------------------------------------- #

def test_une_proposition_bien_formee_est_acceptee():
    props = relecture.lire_propositions("2 | registre | Tu viens ?", n=3, rendus=["a", "b", "c"])

    assert len(props) == 1
    assert props[0].acceptee and props[0].bulle == 2 and props[0].regle == "registre"


def test_une_regle_inventee_est_rejetee():
    """C'est tout le mandat étroit : le modèle ne choisit pas l'étendue de son propre
    pouvoir."""
    props = relecture.lire_propositions("1 | style | Plus joli", n=2, rendus=["a", "b"])

    assert props[0].motif_refus == "regle_inconnue"


def test_une_remarque_libre_est_rejetee():
    props = relecture.lire_propositions("La planche 3 gagnerait à être relue.", n=2,
                                        rendus=["a", "b"])

    assert props[0].motif_refus == "hors_format"


def test_un_numero_hors_bornes_est_rejete():
    props = relecture.lire_propositions("9 | accord | Contente", n=2, rendus=["a", "b"])

    assert props[0].motif_refus == "bulle_hors_bornes"


def test_une_correction_identique_est_rejetee():
    """Un appel payé pour rien, et un compteur qu'il ne faut pas gonfler."""
    props = relecture.lire_propositions("1 | accord | Bonjour", n=2, rendus=["bonjour", "b"])

    assert props[0].motif_refus == "identique"


def test_une_correction_vide_est_rejetee():
    """On n'efface jamais une réplique : une bulle vide est un défaut signalé, jamais une
    correction."""
    props = relecture.lire_propositions("1 | accord | ", n=2, rendus=["a", "b"])

    assert props and props[0].motif_refus in ("vide", "hors_format")


def test_ras_ne_produit_aucune_proposition():
    assert relecture.lire_propositions(relecture.RIEN, n=2, rendus=["a", "b"]) == []


def test_seules_les_propositions_acceptees_sont_appliquees():
    props = relecture.lire_propositions(
        "1 | registre | Tu viens ?\n2 | style | Plus joli", n=2, rendus=["Vous venez ?", "b"])

    textes, n = relecture.appliquer(["Vous venez ?", "b"], props)

    assert n == 1
    assert textes == ["Tu viens ?", "b"]


def test_une_seule_correction_par_bulle():
    """La première acceptée gagne. Le modèle se reprend rarement pour le mieux, et faire
    dépendre le résultat de l'ordre de ses lignes serait la faute qu'`analyser_numerotation` a
    déjà tranchée pour les doublons."""
    props = relecture.lire_propositions("1 | accord | Première\n1 | accord | Seconde",
                                        n=1, rendus=["origine"])

    textes, n = relecture.appliquer(["origine"], props)

    assert n == 1 and textes == ["Première"]


# --------------------------------------------------------------------------- #
# Relecture — la passe elle-même
# --------------------------------------------------------------------------- #

class _Relecteur:
    """Double : rend ce qu'on lui a dit de rendre, et compte ses appels."""

    def __init__(self, reponse: str = relecture.RIEN):
        self.reponse = reponse
        self.appels = 0
        self.dernier = ""

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.appels += 1
        self.dernier = user
        return self.reponse


def test_sans_agent_la_passe_ne_coute_rien_et_ne_change_rien():
    """Le chemin LIVRÉ : `manga_relecteur` n'est pas dans `manga.modeles`."""
    stats: dict = {}

    textes, props = relecture.relire(None, ["源"], ["Rendu"], stats=stats)

    assert textes == ["Rendu"] and props == []
    assert "relecture_appels" not in stats


def test_sans_agent_la_regle_glossaire_tourne_quand_meme():
    """Elle est purement lexicale. C'est elle qui alimente la colonne que `tools/banc.py`
    attendait explicitement du lot 15."""
    stats: dict = {}

    relecture.relire(None, ["界塚が来た"], ["Il est arrivé"], glo=GLOSSAIRE, stats=stats)

    assert stats["glossaire_manque"] == 1


def test_les_refus_sont_comptes_par_motif():
    """« Combien de corrections proposées, combien acceptées par le code » : c'est ce qu'il
    faut pour décider si le relecteur mérite d'être recommandé — ou de rester à `null`."""
    agent = _Relecteur("1 | registre | Tu viens ?\n2 | style | Plus joli")
    stats: dict = {}

    textes, props = relecture.relire(agent, ["a", "b"], ["Vous venez ?", "b"], stats=stats)

    assert textes[0] == "Tu viens ?"
    assert stats["relecture_appels"] == 1
    assert stats["relecture_proposees"] == 2
    assert stats["relecture_appliquees"] == 1
    assert stats["relecture_refus_regle_inconnue"] == 1


def test_une_planche_entierement_vide_ne_coute_aucun_appel():
    agent = _Relecteur()

    relecture.relire(agent, ["a", "b"], ["", ""])

    assert agent.appels == 0


def test_le_prompt_donne_les_manques_deja_calcules():
    """La règle la moins intéressante à faire chercher par un modèle : elle est décidable. La
    lui donner concentre son attention sur les trois autres."""
    agent = _Relecteur()

    relecture.relire(agent, ["界塚が来た"], ["Il est arrivé"], glo=GLOSSAIRE)

    assert "Inaho" in agent.dernier
    assert "Traduction en place" in agent.dernier


def test_les_quatre_regles_sont_nommees_dans_la_consigne():
    for nom in relecture.REGLES:
        assert nom in relecture.CONSIGNE
