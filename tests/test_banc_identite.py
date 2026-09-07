# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc d'identité (`PLAN-25` L25.4), **sans poids et sans GPU**.

Il tourne ici avec un encodeur factice et `MoteurFactice`, exactement comme `tools/banc.py`
tourne en CI sur des caches : c'est ce qui rend le banc testable hors marqueur `modeles`. Le
vrai encodeur et le vrai moteur sont mesurés à la main, et leurs chiffres vivent dans
`docs/mesures/`.

Le test central est `test_le_corpus_publie_ses_ecarts_au_plan` : sur le corpus réel, l'étape
0.1 du plan **n'est pas satisfaite**, et le plan écrit « dites-le, ne le contournez pas ». Un
banc qui ne saurait pas le dire laisserait ce fait à la charge de la personne qui rédige le
document — c'est-à-dire nulle part.
"""
from pathlib import Path

import pytest
from PIL import Image

from core import bible as bible_mod
from illustration import identite as ident_mod
from illustration import juge as juge_mod
from illustration.moteur import MoteurFactice
from tests.test_illustration_juge import EncodeurFactice
from tools import banc_identite as banc


@pytest.fixture
def corpus(tmp_path):
    """Trois personnages : un à trois références, un à une seule, un sans aucune."""
    projet = "Projet Témoin"
    sources = tmp_path / "sources" / projet
    sources.mkdir(parents=True)
    media = tmp_path / "build" / projet / "Vol.1" / "media"
    media.mkdir(parents=True)
    for index in range(4):
        Image.new("RGB", (300, 450), (30 + index * 40, 40, 50)).save(media / f"p{index}.png")
    autre = tmp_path / "build" / "Pride and Prejudice" / "Vol.1" / "media"
    autre.mkdir(parents=True)
    for index in range(3):
        Image.new("RGB", (300, 450), (200, 190 - index * 20, 180)).save(autre / f"q{index}.png")

    def _personnage(nom, fichiers, confiance="humaine"):
        entree = bible_mod.personnage(nom)
        entree["apparence"]["cheveux"] = "châtains"
        entree["citations"] = [{"attribut": "cheveux", "source": "chapters/ch01.md",
                                "texte": "cheveux châtains"}]
        entree["references"] = [{"fichier": f"media/{f}", "role": "identite",
                                 "confiance": confiance} for f in fichiers]
        entree["valide_par_humain"] = True
        return entree

    bible_mod.save({
        "personnages": [_personnage("Riche", ["p0.png", "p1.png", "p2.png"]),
                        _personnage("Pauvre", ["p3.png"]),
                        _personnage("Muet", ["p0.png"], confiance="llm")],
        "style": {"mots": "trait fin",
                  "ancrages": [{"fichier": "media/p0.png", "valide_par_humain": True}],
                  "signature": {"saturation_moyenne": 0.02, "contraste": 0.24,
                                "densite_trait": 0.26, "part_aplats": 0.36,
                                "couleur": False, "echantillon": 4}}},
        bible_mod.chemin(sources))

    config = {"chemins": {"sources": str(tmp_path / "sources"),
                          "build": str(tmp_path / "build")},
              "illustration": {"actif": True, "moteur": "factice",
                               "vram": {"decharger_llm": False},
                               "identite": {"actif": True}}}
    return banc.lire_corpus(projet, config, tome="Vol.1"), config, projet


# ─────────────────────────────────  Le corpus  ─────────────────────────────────

def test_le_corpus_compte_les_references_VALIDEES_seulement(corpus):
    lu, _, _ = corpus
    assert lu.distribution == {0: 1, 1: 1, 3: 1}
    assert [p.nom for p in lu.avec_reference] == ["Riche", "Pauvre"]


def test_le_corpus_publie_ses_ecarts_au_plan(corpus):
    """L'étape 0.1 demande 8 personnages, dont ≥2 à une référence et ≥2 à trois ou plus.
    Le banc doit **nommer** chaque exigence non tenue plutôt que de publier des chiffres
    comme si le corpus les portait."""
    lu, _, _ = corpus
    ecarts = " ".join(lu.exigences_du_plan())
    assert "8 personnages" in ecarts
    assert "2 personnages à une seule référence" in ecarts
    assert "trois références ou plus" in ecarts


def test_un_corpus_conforme_ne_signale_rien():
    conforme = banc.Corpus(projet="x", racine=Path("."), personnages=[
        banc.Personnage(nom=f"p{i}", references=[
            ident_mod.Reference(fichier=f"f{j}", source=Path(f"f{j}"), confiance="humaine")
            for j in range(1 if i < 4 else 3)])
        for i in range(8)])
    assert conforme.exigences_du_plan() == []


def test_le_controle_negatif_vient_du_domaine_public(corpus):
    """La seule œuvre dont une image aurait le droit de figurer dans un document de mesure."""
    lu, _, _ = corpus
    assert lu.autre_oeuvre == "Pride and Prejudice"
    assert len(lu.autres) == 3


# ──────────────────────────────  L'étalonnage  ──────────────────────────────

def test_l_etalonnage_remplit_les_cinq_planchers(corpus):
    lu, _, _ = corpus
    resultat = banc.etalonner(EncodeurFactice(), lu)
    assert set(resultat["echelles"]) == {nom for nom, _ in juge_mod.PAIRES}
    assert resultat["echelles"]["identite_haut"].n == 3        # C(3, 2) pour « Riche »
    assert resultat["echelles"]["identite_confusion"].n == 3   # 3 × 1
    assert resultat["echelles"]["identite_negatif"].n == 12    # 4 références × 3 autres


def test_une_illustration_de_GROUPE_est_comptee_a_part(tmp_path):
    """Le cas que le critère 8 du plan demande d'examiner, et il existe sur le corpus réel :
    deux personnages partagent une illustration. Leur cosinus vaut 1,0 par construction et
    tirerait la médiane de confusion vers le haut pour une raison sans rapport avec la
    ressemblance."""
    projet = "Groupe"
    sources = tmp_path / "sources" / projet
    sources.mkdir(parents=True)
    media = tmp_path / "build" / projet / "Vol.1" / "media"
    media.mkdir(parents=True)
    Image.new("RGB", (300, 450), (60, 70, 80)).save(media / "groupe.png")
    Image.new("RGB", (300, 450), (90, 70, 80)).save(media / "seul.png")

    def _p(nom, fichiers):
        entree = bible_mod.personnage(nom)
        entree["apparence"]["cheveux"] = "noirs"
        entree["citations"] = [{"attribut": "cheveux", "source": "c.md", "texte": "noirs"}]
        entree["references"] = [{"fichier": f"media/{f}", "role": "identite",
                                 "confiance": "humaine"} for f in fichiers]
        return entree

    bible_mod.save({"personnages": [_p("A", ["groupe.png", "seul.png"]),
                                    _p("B", ["groupe.png"])]}, bible_mod.chemin(sources))
    config = {"chemins": {"sources": str(tmp_path / "sources"),
                          "build": str(tmp_path / "build")}}
    lu = banc.lire_corpus(projet, config, tome="Vol.1")
    resultat = banc.etalonner(EncodeurFactice(), lu)

    assert resultat["partages"] == [("A", "B", "media/groupe.png")]
    # La paire partagée est EXCLUE : seule (seul.png, groupe.png) reste en confusion.
    assert resultat["echelles"]["identite_confusion"].n == 1


def test_l_echantillonnage_est_reproductible(corpus):
    """Une graine fixe : deux exécutions du banc doivent publier les mêmes nombres, sinon le
    tableau ne se compare pas au suivant."""
    lu, _, _ = corpus
    premier = banc.etalonner(EncodeurFactice(), lu, paires_max=5)
    second = banc.etalonner(EncodeurFactice(), lu, paires_max=5)
    for nom in premier["echelles"]:
        assert premier["echelles"][nom].valeurs == second["echelles"][nom].valeurs, nom


def test_les_planchers_derivent_de_l_etalonnage_et_de_rien_d_autre():
    echelles = {"identite_haut": juge_mod.Echelle("identite_haut", [0.4, 0.6, 0.9]),
                "identite_confusion": juge_mod.Echelle("identite_confusion", [0.2, 0.3, 0.4])}
    planchers = banc.planchers_de(echelles, True)
    assert planchers.confusion == pytest.approx(0.3)             # la médiane de confusion
    assert planchers.nouveaute == pytest.approx(1.0 - 0.9)       # 1 − le MAXIMUM du haut
    # ⚠ Le plancher de style n'est PAS dérivable de l'étalonnage d'embedding : il reste None,
    # c'est-à-dire désarmé, et le critère 4 bis du plan l'autorise explicitement.
    assert planchers.style_descripteurs is None


def test_un_etalonnage_vide_ne_fabrique_aucun_plancher():
    planchers = banc.planchers_de(
        {"identite_haut": juge_mod.Echelle("identite_haut"),
         "identite_confusion": juge_mod.Echelle("identite_confusion")}, False)
    assert planchers.confusion is None and planchers.nouveaute is None


# ──────────────────────────────  Le balayage  ──────────────────────────────

def test_le_balayage_change_UN_parametre_a_la_fois():
    """La discipline de `tools/apercu_detection.py --balayage`, et le critère 3 du plan."""
    plan = banc.configurations()
    axes = {c.axe for c in plan}
    assert axes == {"nombre_references", "force"}
    nombres = [c for c in plan if c.axe == "nombre_references"]
    assert len({c.pas for c in nombres}) == 1, "l'axe des références ne bouge que les références"
    forces = [c for c in plan if c.axe == "force"]
    assert len({c.references for c in forces}) == 1, "l'axe de force ne bouge que la force"


def test_le_balayage_publie_les_trois_grandeurs_et_les_perdantes(corpus, tmp_path):
    lu, _, _ = corpus
    riche = next(p for p in lu.personnages if p.nom == "Riche")
    dossier = tmp_path / "balayage"
    lignes = banc.balayer(
        MoteurFactice(), EncodeurFactice(), lu, riche, dossier=dossier,
        planchers=ident_mod.Planchers(confusion=0.5, juge_utilisable=True),
        prompt="Portrait.", largeur=64, hauteur=64, graine=7, dire=lambda _m: None)

    assert len(lignes) == len(banc.configurations())
    for ligne in lignes:
        assert "ressemblance" in ligne and "nouveauté" in ligne
        assert "style (descripteurs)" in ligne
    # Une image marquée par ligne — le banc du lot 24 écrivait des PNG nus, celui-ci non.
    from illustration import marquage
    for ligne in lignes:
        assert marquage.relire(ligne["image"])["AIGenerated"] == "true"
        assert marquage.manifeste_de(ligne["image"]).is_file()


def test_le_balayage_refuse_un_personnage_sans_reference_validee(corpus, tmp_path):
    lu, _, _ = corpus
    muet = next(p for p in lu.personnages if p.nom == "Muet")
    with pytest.raises(ident_mod.SansReferenceValidee):
        banc.balayer(MoteurFactice(), EncodeurFactice(), lu, muet, dossier=tmp_path / "b",
                     planchers=ident_mod.Planchers(), prompt="x", largeur=64, hauteur=64,
                     graine=1, dire=lambda _m: None)
    assert not (tmp_path / "b").glob("*.png") or not list((tmp_path / "b").glob("*.png"))


def test_une_configuration_impossible_est_dite_et_non_sautee(corpus, tmp_path):
    """« Non mesurée » est une ligne du tableau, pas une absence de ligne : le plan demande
    « le tableau complet, y compris les configurations perdantes »."""
    lu, _, _ = corpus
    pauvre = next(p for p in lu.personnages if p.nom == "Pauvre")     # une seule référence
    lignes = banc.balayer(
        MoteurFactice(), EncodeurFactice(), lu, pauvre, dossier=tmp_path / "b",
        planchers=ident_mod.Planchers(), prompt="x", largeur=64, hauteur=64, graine=1,
        dire=lambda _m: None)
    non_mesurees = [ligne for ligne in lignes if "non mesurée" in str(ligne.get("verdict", ""))]
    assert len(non_mesurees) >= 2                       # r2 et r3 sont hors de portée
    assert len(lignes) == len(banc.configurations())


def test_les_grandeurs_degenerees_sont_signalees(corpus, tmp_path):
    lu, _, _ = corpus
    pauvre = next(p for p in lu.personnages if p.nom == "Pauvre")
    lignes = banc.balayer(
        MoteurFactice(), EncodeurFactice(), lu, pauvre, dossier=tmp_path / "b",
        planchers=ident_mod.Planchers(), prompt="x", largeur=64, hauteur=64, graine=1,
        dire=lambda _m: None)
    texte = "\n".join(banc.section_balayage(lignes, "Pauvre"))
    assert "nouveauté` sont la MÊME mesure" in texte or "MÊME mesure" in texte


# ──────────────────────────────  Les triplets  ──────────────────────────────

def test_les_triplets_ne_portent_aucune_etiquette(corpus, tmp_path):
    """Le protocole en aveugle de l'étape 0.3 : A et B ne disent pas d'où ils viennent, et le
    banc ne rend AUCUN verdict — c'est un humain qui répond."""
    lu, _, _ = corpus
    riche = next(p for p in lu.personnages if p.nom == "Riche")
    lignes = banc.balayer(
        MoteurFactice(), EncodeurFactice(), lu, riche, dossier=tmp_path / "b",
        planchers=ident_mod.Planchers(), prompt="x", largeur=64, hauteur=64, graine=1,
        dire=lambda _m: None)
    liste = banc.triplets(lignes, nombre=4)
    assert len(liste) == 4
    rendu = "\n".join(banc.section_triplets(liste))
    assert "_config_A" not in rendu and "_config_B" not in rendu
    assert "à remplir" in rendu


def test_les_triplets_sont_reproductibles(corpus, tmp_path):
    lu, _, _ = corpus
    riche = next(p for p in lu.personnages if p.nom == "Riche")
    lignes = banc.balayer(
        MoteurFactice(), EncodeurFactice(), lu, riche, dossier=tmp_path / "b",
        planchers=ident_mod.Planchers(), prompt="x", largeur=64, hauteur=64, graine=1,
        dire=lambda _m: None)
    assert banc.triplets(lignes, nombre=3) == banc.triplets(lignes, nombre=3)


# ──────────────────────────────  Le rendu  ──────────────────────────────

def test_les_nombres_du_tableau_gardent_quatre_decimales():
    """`cellule()` du banc commun arrondit à deux, ce qui écraserait la différence entre
    0,4649 et 0,4676 — c'est-à-dire tout ce que ce banc mesure."""
    assert banc._n4(0.46491) == "0.4649"
    assert banc._n4(None) == "—"


def test_le_document_dit_quand_le_juge_ne_separe_pas(corpus):
    lu, _, _ = corpus
    resultat = banc.etalonner(EncodeurFactice(), lu)
    texte = "\n".join(banc.section_etalonnage(resultat))
    assert "séparation" in texte
    assert "INUTILISABLE" in texte or "utilisable" in texte
    assert "pile ou face" in texte


def test_le_banc_n_ecrit_rien_pendant_l_etalonnage(corpus, tmp_path, monkeypatch):
    lu, _, _ = corpus
    avant = {p: p.stat().st_mtime_ns for p in Path(lu.racine).rglob("*") if p.is_file()}
    banc.etalonner(EncodeurFactice(), lu)
    apres = {p: p.stat().st_mtime_ns for p in Path(lu.racine).rglob("*") if p.is_file()}
    assert avant == apres
