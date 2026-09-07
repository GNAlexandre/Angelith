# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le script du tableau du corpus — `tools/inventaire_oeuvres.py` (lot 34, étape 0.1).

Le critère 1 du `PLAN-34` demande que le tableau soit **produit par un script livré**, pas
relevé à la main. Ces tests gardent les deux propriétés qui font qu'il reste utilisable :

- il rend une ligne par tome, avec toutes les colonnes du plan ;
- `--anonyme` retire les titres du corpus, parce que ce sont des œuvres sous droit d'auteur
  et qu'un tableau publié dans `docs/` n'a pas à les nommer (critère 9).
"""
from __future__ import annotations

import os
from pathlib import Path

import bibliotheque as biblio
from tools import inventaire_oeuvres as inv


def _corpus(tmp_path: Path) -> dict:
    config = {"chemins": {"sources": str(tmp_path / "sources"),
                          "build": str(tmp_path / "build"),
                          "glossaire_fichier": "glossaire.yaml"},
              "langues": {"dossiers": {"ENG": "en", "JAP": "jp"}}}
    for i in range(1, 3):
        chemin = tmp_path / "sources" / "Manga A" / "Vol.1" / "manga" / f"{i:03d}.png"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"\0")
    livre = tmp_path / "sources" / "Roman B" / "Vol.1" / "ENG" / "livre.epub"
    livre.parent.mkdir(parents=True, exist_ok=True)
    livre.write_bytes(b"\0")
    return config


def test_une_ligne_par_tome_avec_toutes_les_colonnes(tmp_path):
    config = _corpus(tmp_path)
    lignes = inv.lignes(biblio.Inventaire(config).oeuvres(paralleles=1))
    assert len(lignes) == 2
    for ligne in lignes:
        assert len(ligne) == len(inv.COLONNES)
    titres = {ligne[0] for ligne in lignes}
    assert titres == {"Manga A", "Roman B"}


def test_les_colonnes_sont_celles_du_plan():
    assert inv.COLONNES == ("Œuvre", "Tome", "Brique", "Format", "Langue", "Unités",
                            "Étapes", "Sorties", "Glossaire", "Dernier run")


def test_anonyme_retire_les_titres_du_corpus(tmp_path):
    """⚠ Critère 9 : ce sont des œuvres sous droit d'auteur. Le document de mesure publie les
    chiffres, pas les titres — et les chiffres, eux, ne bougent pas d'un iota."""
    config = _corpus(tmp_path)
    oeuvres = biblio.Inventaire(config).oeuvres(paralleles=1)
    nommees = inv.lignes(oeuvres)
    anonymes = inv.lignes(oeuvres, anonyme=True)
    assert {ligne[0] for ligne in anonymes} == {"Œuvre 1", "Œuvre 2"}
    assert not any("Manga A" in cellule or "Roman B" in cellule
                   for ligne in anonymes for cellule in ligne)
    # Les colonnes de MESURE sont identiques : l'anonymat ne change aucun chiffre.
    for a, b in zip(nommees, anonymes):
        assert a[2:] == b[2:]


def test_les_pastilles_sont_des_caracteres_pas_des_couleurs(tmp_path):
    config = _corpus(tmp_path)
    lignes = inv.lignes(biblio.Inventaire(config).oeuvres(paralleles=1))
    marques = {marque for _, marque, _ in biblio.LEGENDE_ETATS}
    for ligne in lignes:
        assert ligne[6]
        assert set(ligne[6]) <= marques


def test_le_compteur_d_appels_systeme_compte_vraiment(tmp_path):
    """Le chiffre du critère 1 (« le nombre d'appels `os.stat` ») doit être une mesure, pas
    une impression — et le compteur doit reposer les fonctions d'origine en sortant."""
    config = _corpus(tmp_path)
    vrai_stat = os.stat
    with inv.Compteur() as compteur:
        biblio.Inventaire(config).oeuvres(paralleles=1)
    assert os.stat is vrai_stat, "le compteur n'a pas reposé os.stat"
    assert compteur.total > 0
    assert compteur.appels["scandir"] > 0


def test_le_tableau_markdown_est_du_markdown(tmp_path):
    config = _corpus(tmp_path)
    lignes = inv.lignes(biblio.Inventaire(config).oeuvres(paralleles=1))
    texte = inv._tableau_markdown(lignes)
    lignes_texte = texte.splitlines()
    assert lignes_texte[0].startswith("| Œuvre |")
    assert set(lignes_texte[1]) <= set("|-")
    assert len(lignes_texte) == 2 + len(lignes)
