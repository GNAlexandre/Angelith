# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**L26.0 — choisir les images, et écrire pourquoi.**

Le test central du fichier est `test_une_image_GENEREE_n_est_jamais_candidate` : c'est la
règle 2 du plan, et elle est absolue. Sans elle, une image produite par la brique pourrait
conditionner la suivante — le rebouclage que le `PLAN-27` L27.3 doit rendre impossible, et qui
transformerait une dérive en boucle fermée dont personne ne verrait le début.

Le second est `test_chaque_image_porte_son_motif_retenue_comme_ecartee` : la règle 3. Sans
motif, la porte humaine se réduit à un clic de confiance.
"""
import pytest
from PIL import Image

from core import bible as bible_mod
from illustration import identite as ident_mod
from illustration import selection as selection_mod


def _image(chemin, taille=(700, 1000), teinte=(120, 120, 120)):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", taille, teinte).save(chemin)
    return chemin


@pytest.fixture
def projet(tmp_path):
    """Un tome à quatre illustrations, dont la couverture (`p1`, cf. `core/illustrations.py`)."""
    ident_mod._CLASSES.clear()
    sources = tmp_path / "sources" / "Projet Témoin"
    sources.mkdir(parents=True)
    media = tmp_path / "build" / "Projet Témoin" / "Vol.1" / "media"
    for nom in ("p1_couv.png", "p20_illus.png", "p40_illus.png", "p60_decor.png"):
        _image(media / nom)

    entree = bible_mod.personnage("Tory Noelle")
    entree["apparence"]["cheveux"] = "gris"
    entree["citations"] = [{"attribut": "cheveux", "source": "c.md", "texte": "gris"}]
    entree["references"] = [
        {"fichier": "media/p1_couv.png", "role": "identite", "confiance": "humaine"},
        {"fichier": "media/p20_illus.png", "role": "identite", "confiance": "humaine"},
        {"fichier": "media/p40_illus.png", "role": "identite", "confiance": "humaine"},
        {"fichier": "media/p60_decor.png", "role": "identite", "confiance": "llm"},
    ]
    bible = {"personnages": [entree],
             "style": {"ancrages": [
                 {"fichier": "media/p60_decor.png", "classe": "pleine_page",
                  "motif": "écart au centre du tome : 0.39", "valide_par_humain": True},
                 {"fichier": "media/p40_illus.png", "classe": "pleine_page",
                  "motif": "proposition non relue", "valide_par_humain": False}]}}
    bible_mod.save(bible, bible_mod.chemin(sources))
    return bible_mod.load(bible_mod.chemin(sources)), tmp_path / "build" / "Projet Témoin"


# ══════════════════════  Règle 2 — une image générée n'est JAMAIS candidate  ══════════════════════

def test_une_image_GENEREE_n_est_jamais_candidate(tmp_path, projet):
    """**La règle la plus dure du L26.0, et elle est vérifiée plutôt que promise.**

    Les candidates ne viennent que de `bible.references[]` et de `media/`, donc en théorie
    aucune image produite ne peut entrer. Le dépôt ne se contente jamais d'un raisonnement là
    où un test existe — `manga/clean.py` garde son `paint &= region.mask` « parce que
    l'invariant ne doit pas dépendre d'un raisonnement ».

    Ici : quelqu'un recopie une image produite dans `media/` et la déclare en référence. Elle
    porte le marquage AI Act dans son PNG, et **aucun chemin de code de ce dépôt ne sait
    écrire un PNG généré sans ce bloc**. Elle est donc écartée, avec son motif."""
    from illustration import marquage
    from illustration.moteur import MoteurFactice, Requete

    bible, racine = projet
    sortie = MoteurFactice().generer(Requete(prompt="x"))
    produite, _ = marquage.ecrire(
        sortie, racine / "Vol.1" / "media" / "p90_generee.png",
        provenance=marquage.manifeste(Requete(prompt="x"), sortie, projet="", tome="",
                                      identifiant="oeuvre-test", validation={"par": "A"}))
    assert produite.is_file()

    entree = bible["personnages"][0]
    entree["references"].append({"fichier": "media/p90_generee.png", "role": "identite",
                                 "confiance": "humaine"})
    ident_mod._CLASSES.clear()
    candidates = selection_mod.candidates_identite(bible, "Tory Noelle", racine)
    assert "media/p90_generee.png" not in [c.fichier for c in candidates]


def test_une_image_du_dossier_de_la_brique_n_est_jamais_candidate(tmp_path, projet):
    """Le second signe, indépendant du premier : le dossier de la brique est le **seul**
    endroit où elle écrit, et `illustration/frontiere.py` le garantit à l'exécution."""
    from illustration.orchestrateur import NOM_DOSSIER

    bible, racine = projet
    _image(racine / "Vol.1" / NOM_DOSSIER / "deja-produite.png")
    entree = bible["personnages"][0]
    entree["references"].append(
        {"fichier": f"{NOM_DOSSIER}/deja-produite.png", "role": "identite",
         "confiance": "humaine"})
    ident_mod._CLASSES.clear()
    candidates = selection_mod.candidates_identite(bible, "Tory Noelle", racine)
    assert all(NOM_DOSSIER not in c.fichier for c in candidates)


def test_la_limite_du_signe_de_marquage_est_ECRITE():
    """⚠ Ce test documente une **limite**, il ne célèbre pas une garantie.

    Le marquage n'est pas réciproque : une image générée par un autre programme et déposée
    dans `media/` ne le porte pas, et rien ici ne l'attraperait. C'est la limite de tout
    marquage — l'article 50(2) oblige le FOURNISSEUR à marquer ses sorties, il ne rend pas
    détectables celles des autres."""
    doc = selection_mod._refuser_les_generees.__doc__
    assert "n'est **pas** réciproque" in doc
    assert "50(2)" in doc


# ══════════════════════  Règle 3 — un motif par image, retenue ou non  ══════════════════════

def test_chaque_image_porte_son_motif_retenue_comme_ecartee(projet):
    """« Un utilisateur qui retire une image doit voir pourquoi elle avait été prise. Sans
    motif, la porte humaine se réduit à un clic de confiance. »"""
    bible, racine = projet
    candidates = selection_mod.candidates_identite(bible, "Tory Noelle", racine)
    choix = selection_mod.choisir(candidates, plafond=2)
    assert len(choix) == len(candidates)
    assert all(c.motif.strip() for c in choix)
    assert [c.retenue for c in choix].count(True) == 2


def test_le_motif_dit_ce_qui_est_VERIFIABLE_pas_un_jugement(projet):
    """« Validée par un humain (pleine_page) » se vérifie ; « bonne référence » ne se vérifie
    pas. C'est la même règle que pour les citations de la bible."""
    bible, racine = projet
    choix = selection_mod.choisir(
        selection_mod.candidates_identite(bible, "Tory Noelle", racine), plafond=2)
    retenus = [c for c in choix if c.retenue]
    assert all("validée par un humain" in c.motif for c in retenus)
    ecarte = next(c for c in choix if not c.retenue and "non validée" in c.motif)
    assert "confiance: humaine" in ecarte.motif


# ══════════════════════  Règle 1 — le plafond est celui du lot 25  ══════════════════════

def test_le_plafond_est_celui_MESURE_par_le_lot_25(projet):
    """⚠ **2, et c'est un verdict de mesure, pas une prudence.** « La rupture est entre 1 et
    2, pas entre 2 et 3 » : à une référence le modèle rend un COLLAGE, à deux un portrait
    cohérent, et la troisième est indiscernable de la deuxième — à l'œil **comme au juge** —
    pour 175 s de plus par image."""
    assert selection_mod.PLAFOND_REFERENCES == 2
    bible, racine = projet
    choix = selection_mod.choisir(
        selection_mod.candidates_identite(bible, "Tory Noelle", racine),
        plafond=selection_mod.PLAFOND_REFERENCES)
    hors_plafond = [c for c in choix if "plafond" in c.motif]
    assert hors_plafond, "aucune image n'a été écartée par le plafond"
    assert "identite-2026-08-29" in hors_plafond[0].motif


def test_le_plafond_mesure_est_PLUS_BAS_que_la_limite_cablee():
    """Ce n'est pas une incohérence : 3 est ce que le GRAPHE sait câbler
    (`TextEncodeQwenImageEditPlus` expose `image1`, `image2`, `image3`), 2 est ce que la
    MESURE recommande. Une limite technique et une limite mesurée n'ont pas à coïncider."""
    assert selection_mod.PLAFOND_REFERENCES < ident_mod.REFERENCES_MAX


def test_une_couverture_passe_en_queue_donc_tombe_hors_du_plafond(projet):
    """Conséquence directe et voulue du plafond à 2 : sur un personnage à trois références
    validées dont une couverture, la couverture n'est plus envoyée au modèle — et le problème
    du titre peint dans les pixels disparaît de lui-même."""
    bible, racine = projet
    choix = selection_mod.choisir(
        selection_mod.candidates_identite(bible, "Tory Noelle", racine), plafond=2)
    couverture = next(c for c in choix if "p1_couv" in c.fichier)
    assert couverture.retenue is False


# ══════════════════════  Règle 0 — identité et style ne se mélangent pas  ══════════════════════

def test_les_ancrages_sont_une_liste_DISTINCTE_des_references(projet):
    """« Ce sont deux usages du même canal d'images, et les mélanger sans le dire produit une
    image dont on ne sait pas ce qui a raté. »"""
    bible, racine = projet
    ancrages = selection_mod.candidates_ancrage(bible, racine)
    assert [a.usage for a in ancrages] == [selection_mod.USAGE_ANCRAGE]
    assert [a.fichier for a in ancrages] == ["media/p60_decor.png"]


def test_une_ancre_NON_validee_par_un_humain_n_est_pas_une_ancre(projet):
    """C'est une proposition, pas une ancre. Le `PLAN-23` L23.7 a retenu 2 à 5 ancrages
    **relus à la main** ; sans cette relecture, la signature du tome ne vaut rien."""
    bible, racine = projet
    assert "media/p40_illus.png" not in [
        a.fichier for a in selection_mod.candidates_ancrage(bible, racine)]


# ══════════════════════  Le choix par le modèle de vision  ══════════════════════

def test_analyser_lit_les_trois_lignes_attendues():
    retenue, visage, motif = selection_mod.analyser(
        "retenue: oui\nvisage: non\nmotif: décor de tente au trait, aucun personnage")
    assert retenue is True and visage is False
    assert motif == "décor de tente au trait, aucun personnage"


def test_une_reponse_MAL_FORMEE_vaut_non_retenue():
    """⚠ Le défaut penche du côté du refus, comme partout dans cette brique : une image
    entrée par erreur dans le conditionnement produit un portrait faux qu'on ne sait pas
    expliquer ; une image écartée par erreur se rattrape en décochant une case."""
    retenue, visage, motif = selection_mod.analyser("Bien sûr ! Cette image me semble bonne.")
    assert retenue is False and visage is None
    assert motif == selection_mod.MOTIFS["llm_illisible"]


def test_une_ancre_a_VISAGE_est_ecartee_par_le_modele(projet):
    """⚠ **La contamination d'identité**, nommée par l'étape 0.2 : une ancre qui montre
    quelqu'un peut le faire apparaître dans l'image produite, en plus du personnage voulu.
    Le dépôt ne sait pas détecter un visage (interdit n° 4 : pas d'OpenCV) — le modèle de
    vision, si, et c'est exactement à cela qu'il sert ici."""
    bible, racine = projet
    candidates = selection_mod.candidates_ancrage(bible, racine)

    class _LLM:
        def chat(self, *_a, **_k):
            return "retenue: oui\nvisage: oui\nmotif: deux personnages de face, nets"

    choix, secondes, appels = selection_mod.choisir_avec_llm(
        candidates, plafond=1, usage=selection_mod.USAGE_ANCRAGE, llm=_LLM(),
        modele="yume-27b", systeme="…")
    assert appels == 1 and secondes >= 0.0
    assert choix[0].retenue is False
    assert selection_mod.MOTIFS["llm_visage"] in choix[0].motif


def test_un_appel_rate_n_est_PAS_compte_comme_un_refus_du_modele(projet):
    """Confondre « le modèle a dit non » et « le serveur n'a pas répondu » ferait disparaître
    une panne dans un compteur de refus — et on optimiserait alors une bible qui n'a rien."""
    bible, racine = projet
    candidates = selection_mod.candidates_identite(bible, "Tory Noelle", racine)

    class _LLM:
        def chat(self, *_a, **_k):
            raise TimeoutError("le serveur ne répond pas")

    choix, _, appels = selection_mod.choisir_avec_llm(
        candidates, plafond=2, usage=selection_mod.USAGE_IDENTITE, llm=_LLM(),
        modele="yume-27b", systeme="…", personnage="Tory Noelle")
    assert appels == 0
    assert all(not c.retenue for c in choix)
    assert any("appel de vision échoué" in c.motif for c in choix)


def test_le_plafond_s_applique_APRES_le_modele_avec_son_motif(projet):
    """Il faut un motif pour **chaque** image, y compris pour celles que le plafond écarte :
    sans ça, un utilisateur ne saurait pas qu'une troisième référence existait et qu'elle
    avait été jugée bonne."""
    bible, racine = projet
    candidates = selection_mod.candidates_identite(bible, "Tory Noelle", racine)

    class _LLM:
        def chat(self, *_a, **_k):
            return "retenue: oui\nvisage: oui\nmotif: visage de face, net, tiers de l'image"

    choix, _, _ = selection_mod.choisir_avec_llm(
        candidates, plafond=2, usage=selection_mod.USAGE_IDENTITE, llm=_LLM(),
        modele="yume-27b", systeme="…", personnage="Tory Noelle")
    assert [c.retenue for c in choix].count(True) == 2
    hors = [c for c in choix if not c.retenue and "plafond" in c.motif]
    assert hors and "le modèle la jugeait bonne" in hors[0].motif


def test_le_prompt_de_selection_est_HORS_des_prompts_requis():
    """⚠ Les huit prompts de `core.langues.PROMPTS_REQUIS` sont ceux dont l'absence fait
    échouer `_verifier_prompts` et **invaliderait le pack `langues/en`**. Le modèle est
    `manga_relecteur.md` : livré dans les deux packs, absent du tuple."""
    from pathlib import Path

    from core import langues as langues_mod

    assert selection_mod.PROMPT not in langues_mod.PROMPTS_REQUIS
    for pack in ("fr", "en"):
        assert Path(f"langues/{pack}/prompts/{selection_mod.PROMPT}.md").is_file()
        assert Path(f"langues/{pack}/prompts/illustration_portrait.md").is_file()


def test_l_entete_de_licence_des_prompts_est_a_la_FIN():
    """Interdit n° 6, mot pour mot : « l'en-tête de licence d'un prompt est à la fin du
    fichier, jamais au début — un modèle lit le haut du fichier comme une instruction »."""
    from pathlib import Path

    for pack in ("fr", "en"):
        for nom in ("illustration_portrait", "illustration_style"):
            texte = Path(f"langues/{pack}/prompts/{nom}.md").read_text(encoding="utf-8")
            assert "SPDX-License-Identifier" in texte
            assert texte.index("SPDX-License-Identifier") > len(texte) * 0.8
