# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Créer un tome sous `sources/` (`manga/creation_projet.py`) — **sans PySide6**.

## Le geste que le dépôt ne savait pas faire

Le pipeline lit un dossier d'images, un `.cbz` et un `.cbr` depuis la 1.0.0. Ce qui manquait
n'était pas la lecture mais le GESTE : un premier lancement de l'interface affichait deux listes
vides et une ligne de journal expliquant comment fabriquer `sources/<Projet>/<Tome>/manga/` à la
main, dans un autre logiciel.

## Ce que ces tests tiennent

- **Copier, pas référencer.** Un projet qui pointerait vers un `.cbz` resté sur une clé USB
  casserait au premier débranchement, et toute l'arborescence du pipeline suppose que les
  planches sont sous `sources/`.
- **Refuser plutôt que corriger un nom.** Remplacer silencieusement `Vol/1` par `Vol_1`
  créerait un tome que l'utilisateur ne retrouverait pas sous le nom qu'il a tapé — et ce nom
  finit dans `RAPPORT.md`, dans les métadonnées du CBZ et dans le nom du PDF.
- **Ne jamais écraser un tome existant.** Deux tomes mélangés dans le même `build/` alignent
  l'aval par position sur des planches qui ne sont plus les mêmes.
- **Le résultat est lisible par le pipeline**, vérifié en le relisant avec
  `sources_manga.resoudre_source`, et pas seulement en regardant les chemins écrits.
"""
from __future__ import annotations

import pytest

from manga import creation_projet as crea
from manga.sources_manga import resoudre_source


@pytest.fixture
def config(tmp_path):
    return {"manga": {"chemins": {"sources": str(tmp_path / "sources"),
                                  "build": str(tmp_path / "build")}},
            "langues": {"dossiers": {"JAP": "jp", "ENG": "en"}}}


@pytest.fixture
def source(tmp_path):
    dossier = tmp_path / "entree"
    dossier.mkdir()
    for i in (1, 2, 10):
        (dossier / f"page_{i}.png").write_bytes(b"\x89PNG" + bytes(100))
    return dossier


# --------------------------------------------------------------------------- #
# La validation des noms
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("nom", ["Mon Manga", "Vol.1", "Chap. 11 — extra", "Ω 2"])
def test_les_noms_normaux_passent(nom):
    assert crea.valider_nom(nom) == nom


@pytest.mark.parametrize("nom", ["", "   ", "Vol/1", "a:b", "x?y", 'guillemet"', "pipe|"])
def test_les_noms_impossibles_sont_refuses(nom):
    with pytest.raises(crea.ErreurCreation):
        crea.valider_nom(nom)


@pytest.mark.parametrize("nom", ["CON", "con", "nul", "COM1", "LPT9"])
def test_les_noms_reserves_par_windows_sont_refuses(nom):
    """Windows refuse de créer le dossier, et son message (« paramètre incorrect ») n'apprend
    rien. Refuser ici permet de dire pourquoi."""
    with pytest.raises(crea.ErreurCreation, match="réservé"):
        crea.valider_nom(nom)


@pytest.mark.parametrize("nom", ["Vol.1.", "point.", "deux.."])
def test_un_nom_qui_finit_par_un_point_est_refuse(nom):
    """Windows refuse de créer un dossier dont le nom finit par un point.

    ⚠ L'espace de fin, elle, est simplement RETIRÉE : c'est une faute de frappe évidente, pas
    une intention, et refuser « Vol.1 » parce qu'une espace traîne serait pénible sans être
    utile. Le point, lui, peut faire partie du nom voulu (« Vol.1 ») — on ne peut pas le
    retirer sans changer ce que l'utilisateur a écrit."""
    with pytest.raises(crea.ErreurCreation):
        crea.valider_nom(nom)


def test_une_espace_de_fin_est_simplement_retiree():
    assert crea.valider_nom("Tome ") == "Tome"


def test_un_nom_trop_long_est_refuse():
    with pytest.raises(crea.ErreurCreation, match="100"):
        crea.valider_nom("a" * 101)


def test_le_nom_est_rendu_nettoye_des_espaces_de_bord():
    assert crea.valider_nom("  Mon Manga  ") == "Mon Manga"


# --------------------------------------------------------------------------- #
# Ce qu'on va copier
# --------------------------------------------------------------------------- #

def test_lister_sources_trie_naturellement(source):
    noms = [p.name for p in crea.lister_sources([source])]
    assert noms == ["page_1.png", "page_2.png", "page_10.png"], \
        "page_10 après page_2 : un tri lexicographique le mettrait en deuxième"


def test_lister_sources_descend_d_un_cran(tmp_path):
    tome = tmp_path / "Vol.3"
    (tome / "manga").mkdir(parents=True)
    (tome / "manga" / "a.png").write_bytes(b"x")
    assert [p.name for p in crea.lister_sources([tome])] == ["a.png"]


def test_lister_sources_ignore_ce_qui_n_est_pas_une_planche(tmp_path):
    dossier = tmp_path / "melange"
    dossier.mkdir()
    (dossier / "ok.png").write_bytes(b"x")
    (dossier / "notes.pdf").write_bytes(b"%PDF")
    (dossier / "brouillon.psd").write_bytes(b"8BPS")
    assert [p.name for p in crea.lister_sources([dossier])] == ["ok.png"]


def test_lister_sources_dedoublonne(source):
    """Deux chemins qui désignent les mêmes images ramèneraient 300 planches pour un tome de
    150, et rien ne le signalerait."""
    doublons = crea.lister_sources([source, source, source / "page_1.png"])
    assert len(doublons) == 3


def test_le_poids_est_annonce_avant_de_copier(source):
    """Une archive de webtoon pèse couramment plusieurs centaines de mégaoctets ; une copie
    muette de cette taille passe pour un gel."""
    octets = crea.estimer_poids(crea.lister_sources([source]))
    assert octets > 0
    assert crea.poids_lisible(octets).endswith(("o", "ko", "Mo", "Go"))
    assert crea.poids_lisible(5 << 20) == "5 Mo"


# --------------------------------------------------------------------------- #
# La création
# --------------------------------------------------------------------------- #

def test_creer_ecrit_l_arborescence_attendue(config, source, tmp_path):
    creation = crea.creer(config, "Mon Manga", "Vol.1", [source])
    assert creation.dossier == tmp_path / "sources" / "Mon Manga" / "Vol.1" / "manga"
    assert creation.dossier.is_dir()
    assert len(creation.fichiers) == 3
    assert creation.projet == "Mon Manga"
    assert creation.tome == "Vol.1"


def test_les_fichiers_sont_COPIES_pas_deplaces(config, source):
    """La source reste intacte : on ne vide pas le dossier de quelqu'un sur un glisser-déposer."""
    avant = sorted(p.name for p in source.iterdir())
    crea.creer(config, "P", "T", [source])
    assert sorted(p.name for p in source.iterdir()) == avant


def test_le_pipeline_relit_ce_qui_vient_d_etre_ecrit(config, source):
    """La vérification qui compte. Écrire les bons chemins ne prouve rien : c'est
    `resoudre_source` — le point d'entrée unique de `scan_volume`, du pré-vol de `serie.py` et
    de l'interface — qui décide si un tome est lisible."""
    creation = crea.creer(config, "Mon Manga", "Vol.1", [source])
    dossier, fmt, code, _ = resoudre_source(creation.dossier.parent, config)
    assert dossier == creation.dossier
    assert fmt == "manga"
    assert code == "jp"


def test_le_format_webtoon_est_relu_comme_tel(config, source):
    creation = crea.creer(config, "Bande", "Chap.11", [source], format="webtoon")
    assert creation.dossier.name == "webtoon"
    _, fmt, _, _ = resoudre_source(creation.dossier.parent, config)
    assert fmt == "webtoon"


def test_un_dossier_de_langue_est_relu_comme_tel(config, source):
    creation = crea.creer(config, "Trad EN", "Vol.1", [source], langue="ENG")
    assert creation.dossier.name == "ENG"
    dossier, _, code, _ = resoudre_source(creation.dossier.parent.parent, config)
    assert dossier == creation.dossier
    assert code == "en"


def test_un_format_inconnu_est_refuse(config):
    with pytest.raises(crea.ErreurCreation, match="Format inconnu"):
        crea.dossier_cible(config, "P", "T", format="roman")


def test_creer_sans_rien_de_lisible_leve_avec_un_message(config, tmp_path):
    vide = tmp_path / "psd"
    vide.mkdir()
    (vide / "a.psd").write_bytes(b"8BPS")
    with pytest.raises(crea.ErreurCreation, match="Aucune image"):
        crea.creer(config, "P", "T", [vide])


def test_un_tome_existant_n_est_jamais_ecrase(config, source):
    """Deux tomes mélangés dans le même `build/` : les checkpoints de l'ancien restent, et
    l'aval s'aligne PAR POSITION sur des planches qui ne sont plus les mêmes."""
    crea.creer(config, "P", "Vol.1", [source])
    with pytest.raises(crea.ErreurCreation, match="contient déjà"):
        crea.creer(config, "P", "Vol.1", [source])


def test_un_dossier_cible_vide_ne_bloque_pas(config, source):
    """Le refus porte sur des PLANCHES existantes, pas sur un dossier créé puis abandonné."""
    crea.preparer(config, "P", "Vol.1")
    creation = crea.creer(config, "P", "Vol.1", [source])
    assert len(creation.fichiers) == 3


def test_les_collisions_de_nom_ne_perdent_aucune_planche(config, tmp_path):
    """Deux dossiers sources peuvent tous deux porter `page_0001.png`. Écraser ferait un tome
    à trous que rien ne signalerait."""
    a, b = tmp_path / "a", tmp_path / "b"
    for dossier, octet in ((a, b"A"), (b, b"B")):
        dossier.mkdir()
        (dossier / "page_0001.png").write_bytes(octet * 10)
    creation = crea.creer(config, "P", "T", [a, b])
    assert len(creation.fichiers) == 2
    assert len({f.name for f in creation.fichiers}) == 2
    assert {f.read_bytes()[:1] for f in creation.fichiers} == {b"A", b"B"}


def test_la_progression_est_rapportee(config, source):
    """C'est ce qui distingue une copie de 400 Mo d'un gel."""
    vus = []
    crea.creer(config, "P", "T", [source], progres=lambda f, t, n: vus.append((f, t, n)))
    assert [f for f, _, _ in vus] == [1, 2, 3]
    assert {t for _, t, _ in vus} == {3}


def test_les_noms_sont_valides_avant_toute_ecriture(config, source, tmp_path):
    """Un nom refusé ne doit laisser AUCUN dossier derrière lui."""
    with pytest.raises(crea.ErreurCreation):
        crea.creer(config, "Mon/Manga", "Vol.1", [source])
    assert not (tmp_path / "sources").exists() or \
        not any((tmp_path / "sources").iterdir())
