# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`core/bible.py`, `core/bible_texte.py`, `core/bible_llm.py` — la bible visuelle.

Le test central du lot est `test_un_attribut_sans_citation_n_est_PAS_ecrit` : c'est la règle
qui fait toute la valeur du fichier. Un attribut sans sa source n'est pas une observation,
c'est une invention, et il se propagerait dans toutes les images générées du personnage sans
que personne sache d'où il vient.

Le second est `test_le_mot_ans_ne_se_declenche_pas_sur_dans` : la passe lexicale appariait à
l'origine des sous-chaînes, et **1 257 des 1 565** passages candidats de roman D — 80,3 % —
étaient des faux de cette seule famille (*dans*, *sans*, *enfants*), tous rangés sous
`age_apparent`.
"""
from pathlib import Path

import pytest
import yaml

from core import bible, bible_llm, bible_texte


def _entree(nom="Tory Noelle", **champs) -> dict:
    base = bible.personnage(nom)
    base.update(champs)
    return base


def _citation(attribut, source="chapters/ch03.md", texte="Ses cheveux blonds."):
    return {"attribut": attribut, "texte": texte, "source": source}


# ──────────────────────────────  Schéma et écriture  ──────────────────────────────

def test_fill_defaults_ecrit_TOUS_les_champs_meme_vides():
    """Même promesse que le glossaire : ce qui est visible se complète, ce qui est absent
    s'oublie."""
    rempli = bible.fill_defaults({"personnages": [{"nom": "Tory"}]})
    entree = rempli["personnages"][0]
    assert list(entree) == list(bible.CHAMPS_PERSONNAGE)
    assert set(entree["apparence"]) == set(bible.ATTRIBUTS)
    assert rempli["style"]["signature"]["echantillon"] == 0


def test_les_champs_liste_ne_partagent_pas_un_objet_par_defaut():
    """PyYAML crée des ancres `&id001` pour les objets identiques ; deux entrées qui
    partageraient la même liste vide sortiraient liées dans le fichier."""
    rempli = bible.fill_defaults({"personnages": [{"nom": "A"}, {"nom": "B"}]})
    rempli["personnages"][0]["apparence"]["signes"].append("cicatrice")
    assert rempli["personnages"][1]["apparence"]["signes"] == []


def test_un_aller_retour_disque_preserve_un_champ_rempli_a_la_main(tmp_path):
    chemin = tmp_path / "Projet" / "bible.yaml"
    entree = _entree(apparence={**bible._apparence_vide(), "yeux": "gris"},
                     citations=[_citation("yeux", texte="Des yeux gris.")],
                     valide_par_humain=True)
    bible.save({"personnages": [entree]}, chemin)
    relue = bible.load(chemin)
    assert relue["personnages"][0]["apparence"]["yeux"] == "gris"
    assert relue["personnages"][0]["valide_par_humain"] is True


def test_charger_une_bible_absente_rend_une_bible_vide(tmp_path):
    """Un projet sans bible est un projet dont la bible n'a pas encore été commencée — pas
    une erreur."""
    assert bible.load(tmp_path / "rien.yaml") == bible.vide()


# ───────────────────────  LA règle : pas de citation, pas d'attribut  ───────────────────────

def test_un_attribut_sans_citation_n_est_PAS_ecrit(tmp_path):
    chemin = tmp_path / "Projet" / "bible.yaml"
    entree = _entree(apparence={**bible._apparence_vide(),
                                "cheveux": "blonds", "yeux": "gris"},
                     citations=[_citation("cheveux")])
    retires = bible.save({"personnages": [entree]}, chemin)
    relue = bible.load(chemin)
    assert relue["personnages"][0]["apparence"]["cheveux"] == "blonds"
    assert relue["personnages"][0]["apparence"]["yeux"] == ""
    assert ("Tory Noelle", "yeux") in retires
    # La purge doit être VISIBLE dans le fichier, pas seulement dans le retour.
    assert "gris" not in chemin.read_text(encoding="utf-8")


def test_une_citation_sans_source_ne_vaut_pas_citation(tmp_path):
    entree = _entree(apparence={**bible._apparence_vide(), "cheveux": "blonds"},
                     citations=[{"attribut": "cheveux", "texte": "…", "source": ""}])
    _, retires = bible.purger_sans_citation({"personnages": [entree]})
    assert ("Tory Noelle", "cheveux") in retires


def test_un_signe_est_une_liste_et_obeit_a_la_meme_regle():
    entree = _entree(apparence={**bible._apparence_vide(), "signes": ["cicatrice"]})
    assert ("Tory Noelle", "signes") in bible.attributs_sans_citation(
        {"personnages": [entree]})


# ────────────────────────────────  Fusion sans écrasement  ────────────────────────────────

def test_la_fusion_n_ecrase_jamais_un_champ_deja_rempli():
    ancienne = {"personnages": [_entree(
        apparence={**bible._apparence_vide(), "cheveux": "argentés"},
        citations=[_citation("cheveux", texte="Cheveux argentés.")])]}
    neuve = {"personnages": [_entree(
        apparence={**bible._apparence_vide(), "cheveux": "blonds", "yeux": "gris"},
        citations=[_citation("yeux", texte="Yeux gris.")])]}
    fondue = bible.fusionner(ancienne, neuve)
    assert fondue["personnages"][0]["apparence"]["cheveux"] == "argentés"
    assert fondue["personnages"][0]["apparence"]["yeux"] == "gris"


def test_une_entree_validee_n_accepte_plus_qu_un_AJOUT():
    """« Validée » veut dire quelque chose : relancer la passe automatique ne défait pas une
    relecture."""
    ancienne = {"personnages": [_entree(valide_par_humain=True)]}
    neuve = {"personnages": [_entree(
        apparence={**bible._apparence_vide(), "cheveux": "blonds"},
        citations=[_citation("cheveux")],
        references=[{"fichier": "media/p1.jpg", "confiance": "llm"}])]}
    fondue = bible.fusionner(ancienne, neuve)
    assert fondue["personnages"][0]["apparence"]["cheveux"] == ""
    assert len(fondue["personnages"][0]["references"]) == 1


def test_une_reference_validee_a_la_main_n_est_pas_retrogradee():
    ancienne = {"personnages": [_entree(references=[
        {"fichier": "media/p1.jpg", "confiance": "humaine", "role": "identite"}])]}
    neuve = {"personnages": [_entree(references=[
        {"fichier": "media/p1.jpg", "confiance": "llm", "role": "identite"}])]}
    fondue = bible.fusionner(ancienne, neuve)
    assert fondue["personnages"][0]["references"][0]["confiance"] == "humaine"


def test_une_signature_fraiche_remplace_l_ancienne():
    """La signature est MESURÉE, jamais saisie : un tome enrichi de planches ne doit pas
    garder une signature calculée sur un échantillon plus pauvre."""
    ancienne = {"style": {"signature": {**bible.signature_vide(), "echantillon": 3,
                                        "contraste": 0.1}}}
    neuve = {"style": {"signature": {**bible.signature_vide(), "echantillon": 30,
                                     "contraste": 0.2}}}
    assert bible.fusionner(ancienne, neuve)["style"]["signature"]["echantillon"] == 30


# ────────────────────────────────  Cohérence  ────────────────────────────────

def test_un_nom_absent_du_glossaire_est_refuse():
    """Le glossaire reste la source unique des noms : la bible en décrit, elle n'en crée pas."""
    problemes = bible.verifier_coherence({"personnages": [_entree("Inventé")]},
                                         ["Tory Noelle"])
    assert any("n'existe pas dans le glossaire" in p for p in problemes)


def test_une_reference_introuvable_sur_le_disque_est_signalee(tmp_path):
    (tmp_path / "Vol.1" / "media").mkdir(parents=True)
    (tmp_path / "Vol.1" / "media" / "p1.jpg").write_bytes(b"x")
    bonne = _entree(references=[{"fichier": "media/p1.jpg", "confiance": "humaine"}])
    mauvaise = _entree(references=[{"fichier": "media/absente.jpg", "confiance": "llm"}])
    problemes = bible.verifier_coherence({"personnages": [bonne, mauvaise]},
                                         ["Tory Noelle"], tmp_path)
    assert sum("introuvable sur le disque" in p for p in problemes) == 1


def test_un_genre_hors_vocabulaire_est_signale():
    problemes = bible.verifier_coherence(
        {"personnages": [_entree(genre_confirme="féminine")]}, ["Tory Noelle"])
    assert any("genre_confirme" in p for p in problemes)


# ───────────────────────────  L23.4 — la passe lexicale  ───────────────────────────

PERSONNAGES = [{"nom": "Tory Noelle", "variantes": ["la médic"], "genre": "?"},
               {"nom": "Gabak", "variantes": [], "genre": "?"}]


def test_le_mot_ans_ne_se_declenche_pas_sur_dans():
    """Le défaut mesuré : 1 257 des 1 565 passages candidats de roman D — 80,3 % — venaient
    de sous-chaînes comme *dans*, *sans*, *enfants*."""
    candidats = bible_texte.candidats_du_chapitre(
        "Tory Noelle avança dans la pièce sans un mot.", "chapters/ch01.md", PERSONNAGES)
    assert candidats == []


def test_un_passage_d_apparence_pres_du_nom_devient_candidat():
    candidats = bible_texte.candidats_du_chapitre(
        "Tory Noelle releva la tête. Ses cheveux argentés collaient à son front.",
        "chapters/ch01.md", PERSONNAGES)
    assert [(c.nom, c.attribut, c.declencheur) for c in candidats] == [
        ("Tory Noelle", "cheveux", "cheveux")]


def test_un_passage_trop_loin_du_nom_n_est_pas_candidat():
    """Au-delà de la fenêtre, le lien n'est plus une observation sur le personnage, c'est une
    coïncidence de vocabulaire."""
    texte = ("Tory Noelle entra. " + "Une phrase neutre. " * 5
             + "Ses cheveux argentés brillaient.")
    assert bible_texte.candidats_du_chapitre(texte, "chapters/ch01.md", PERSONNAGES) == []


def test_le_prenom_seul_suffit_a_apparier():
    """Le glossaire porte « Tory Noelle », le texte dit « Tory ». Un appariement sur le nom
    complet seul manquerait la quasi-totalité des mentions."""
    candidats = bible_texte.candidats_du_chapitre(
        "Tory portait un uniforme vert.", "chapters/ch01.md", PERSONNAGES)
    assert [c.attribut for c in candidats] == ["tenue"]


def test_les_marqueurs_d_image_et_les_clotures_pandoc_sont_retires():
    texte = ('::: {.dialogue}\n**Tory** avait les yeux gris.\n:::\n'
             '<!-- IMG: media/p1.jpg -->\n')
    candidats = bible_texte.candidats_du_chapitre(texte, "chapters/ch01.md", PERSONNAGES)
    assert [c.attribut for c in candidats] == ["yeux"]
    assert "IMG" not in candidats[0].texte


def test_le_denominateur_porte_le_TOTAL_des_personnages():
    candidats = bible_texte.candidats_du_chapitre(
        "Tory Noelle avait les yeux gris.", "chapters/ch01.md", PERSONNAGES)
    mesure = bible_texte.denominateur(candidats, PERSONNAGES)
    assert mesure == {"personnages_avec_candidat": 1, "personnages": 2, "passages": 1,
                      "par_attribut": {"yeux": 1}}


def test_un_tome_sans_chapitres_rend_une_liste_vide(tmp_path):
    """Six projets du corpus sont dans ce cas au 2026-08-29 : des projets manga, qui n'ont ni
    `chapters/` ni `media/`."""
    assert bible_texte.candidats_du_tome(tmp_path, PERSONNAGES) == []


# ─────────────────────  L23.3 — ce que le CODE refuse au modèle  ─────────────────────

class _Candidat:
    def __init__(self, source="chapters/ch01.md", texte="Ses cheveux argentés."):
        self.source, self.texte = source, texte


def test_un_nom_hors_glossaire_est_rejete_pas_ajoute():
    """Même geste que `manga/relecture.py` : le refus est dans le code, pas dans le prompt —
    le prompt est justement la partie qu'on ne contrôle pas."""
    retenues, rejets = bible_llm.analyser(
        "Inventé | cheveux | blonds | 1", ["Tory Noelle"], [_Candidat()])
    assert retenues == []
    assert rejets["nom_inconnu"] == 1


def test_une_ligne_sans_numero_de_passage_valable_est_rejetee():
    _, rejets = bible_llm.analyser("Tory Noelle | cheveux | blonds | 9",
                                   ["Tory Noelle"], [_Candidat()])
    assert rejets["passage_invalide"] == 1


def test_un_attribut_hors_vocabulaire_est_rejete():
    _, rejets = bible_llm.analyser("Tory Noelle | caractere | doux | 1",
                                   ["Tory Noelle"], [_Candidat()])
    assert rejets["attribut_inconnu"] == 1


def test_une_valeur_qui_est_une_phrase_est_rejetee_pas_tronquee():
    """Une phrase tronquée reste fausse."""
    longue = "des cheveux qui semblent, sous cette lumière, tirer vers un blond très pâle"
    _, rejets = bible_llm.analyser(f"Tory Noelle | cheveux | {longue} | 1",
                                   ["Tory Noelle"], [_Candidat()])
    assert rejets["valeur_trop_longue"] == 1


def test_une_ligne_retenue_emporte_TOUJOURS_sa_citation():
    retenues, _ = bible_llm.analyser("Tory Noelle | cheveux | argentés | 1",
                                     ["Tory Noelle"], [_Candidat()])
    assert retenues[0].source == "chapters/ch01.md"
    assert retenues[0].texte == "Ses cheveux argentés."


def test_RAS_ne_produit_ni_proposition_ni_rejet():
    retenues, rejets = bible_llm.analyser("RAS", ["Tory Noelle"], [_Candidat()])
    assert retenues == [] and bible_llm.compte_des_rejets(rejets) == 0


def test_un_refus_garde_la_ligne_en_exemple():
    """Un compteur sans exemple ne se diagnostique pas : `passage_invalide: 25` ne se
    comprend qu'en voyant les lignes."""
    _, rejets = bible_llm.analyser("Tory Noelle | cheveux | blonds | 9",
                                   ["Tory Noelle"], [_Candidat()])
    assert rejets["exemples"] == ["passage_invalide : Tory Noelle | cheveux | blonds | 9"]


def test_la_boucle_du_modele_est_entierement_refusee():
    """Cas mesuré sur roman D : `yume-27b` a répété le même attribut en incrémentant le
    numéro de passage de 26 à 50, hors du lot de 25 fourni. Sans le contrôle de plage,
    l'attribut serait entré 25 fois avec 25 citations fabriquées."""
    boucle = chr(10).join(f"Tory Noelle | age_apparent | dix-huit ans | {n}"
                          for n in range(26, 51))
    retenues, rejets = bible_llm.analyser(boucle, ["Tory Noelle"], [_Candidat()] * 25)
    assert retenues == []
    assert rejets["passage_invalide"] == 25


def test_la_certitude_est_lue_et_vaut_indeterminee_par_defaut():
    retenues, _ = bible_llm.analyser(
        "certitude: haute\nTory Noelle | yeux | gris | 1", ["Tory Noelle"], [_Candidat()])
    assert retenues[0].certitude == "haute"
    sans, _ = bible_llm.analyser("Tory Noelle | yeux | gris | 1",
                                 ["Tory Noelle"], [_Candidat()])
    assert sans[0].certitude == "indeterminee"


def test_une_certitude_inconnue_retombe_sur_l_abstention():
    retenues, _ = bible_llm.analyser(
        "certitude: absolue\nTory Noelle | yeux | gris | 1", ["Tory Noelle"], [_Candidat()])
    assert retenues[0].certitude == "indeterminee"


def test_en_bible_ne_produit_pas_d_attribut_sans_sa_citation():
    """La règle devient structurelle : une proposition ne PEUT pas produire un attribut nu."""
    retenues, _ = bible_llm.analyser(
        "Tory Noelle | cheveux | argentés | 1", ["Tory Noelle"], [_Candidat()])
    produite = bible_llm.en_bible(retenues)
    assert bible.attributs_sans_citation(produite) == []


def test_en_bible_marque_toute_reference_en_confiance_llm():
    produite = bible_llm.en_bible(
        [], {"Tory Noelle": [("media/p1.jpg", "ch01@0.42", "pleine_page")]})
    reference = produite["personnages"][0]["references"][0]
    assert reference["confiance"] == "llm"
    assert reference["role"] == "identite"


def test_un_prompt_absent_est_un_refus_explicite_pas_un_repli(tmp_path):
    """« Aucun repli silencieux » est la règle écrite de `core/langues.py` : un attribut
    relevé dans une autre langue que la cible serait faux sans être visible."""
    class _Pack:
        def prompt(self, nom):
            return tmp_path / "prompts" / f"{nom}.md"

    with pytest.raises(bible_llm.PromptAbsent):
        bible_llm.charger_prompt(_Pack())


def test_le_prompt_du_pack_francais_existe_et_porte_sa_licence_A_LA_FIN():
    """L'en-tête de licence d'un prompt est à la FIN du fichier (interdit n° 6) : un modèle
    lit le haut du fichier comme une instruction."""
    for code in ("fr", "en"):
        chemin = Path("langues") / code / "prompts" / f"{bible_llm.PROMPT}.md"
        texte = chemin.read_text(encoding="utf-8")
        assert "SPDX-License-Identifier" in texte
        assert not texte.lstrip().startswith("<!--")


def test_bible_apparence_n_est_PAS_dans_les_prompts_requis():
    """Y ajouter un nom rendrait invalide, au démarrage d'un run de traduction, tout pack
    tiers écrit avant ce lot. Le précédent exact est `manga_relecteur.md`."""
    from core.langues import PROMPTS_REQUIS
    assert bible_llm.PROMPT not in PROMPTS_REQUIS


# ────────────────────────────────  Le fichier écrit  ────────────────────────────────

def test_le_fichier_ecrit_est_du_yaml_lisible_avec_sa_banniere(tmp_path):
    chemin = tmp_path / "Mon Œuvre" / "bible.yaml"
    bible.save(bible.vide(), chemin)
    texte = chemin.read_text(encoding="utf-8")
    assert "Bible visuelle — Mon Œuvre" in texte
    assert "N'entre JAMAIS dans le prompt du traducteur" in texte
    assert yaml.safe_load(texte)["version"] == bible.VERSION


def test_la_bible_se_range_a_cote_du_glossaire_sous_sources():
    """Elle reste sous `sources/`, que `.gitignore` exclut en bloc — l'arbre git exposerait
    sinon le NOM de chaque œuvre comme nom de dossier."""
    assert bible.chemin("sources/Projet") == Path("sources/Projet/bible.yaml")
    assert bible.chemin_propositions("sources/Projet").name == "bible.propositions.yaml"


# ────────────────────  L23.5 — l'indice de genre, mesuré et refusable  ────────────────────

def test_un_indice_de_genre_ancre_sur_le_NOM_est_releve():
    """Ancré sur le nom, et pas « la phrase contient *elle* » : dans une scène à plusieurs,
    seul l'ancrage attribue le signal à la bonne personne."""
    indices = bible_texte.indices_de_genre(
        ["Mademoiselle Tory Noelle entra.", "Tory était une soldate."], PERSONNAGES)
    assert indices["Tory Noelle"].feminin == 2
    assert indices["Tory Noelle"].propose == "féminin"


def test_un_indice_unique_ne_propose_RIEN():
    """Un personnage cité une fois n'a pas un genre, il a un bruit. Le champ `genre` commande
    les accords : une erreur produirait « il est arrivée » sur tout un tome."""
    indices = bible_texte.indices_de_genre(["Mademoiselle Tory entra."], PERSONNAGES)
    assert indices["Tory Noelle"].feminin == 1
    assert indices["Tory Noelle"].propose == ""


def test_deux_genres_a_egalite_ne_proposent_RIEN():
    indices = bible_texte.indices_de_genre(
        ["Mademoiselle Tory entra.", "Madame Tory sortit.",
         "Monsieur Tory revint.", "Messire Tory partit."], PERSONNAGES)
    assert indices["Tory Noelle"].propose == ""


def test_chaque_personnage_recoit_un_indice_meme_a_zero():
    """Un dictionnaire qui n'aurait que les personnages trouvés perdrait le dénominateur."""
    indices = bible_texte.indices_de_genre(["Rien de pertinent."], PERSONNAGES)
    assert set(indices) == {"Tory Noelle", "Gabak"}
    assert indices["Gabak"].propose == ""
