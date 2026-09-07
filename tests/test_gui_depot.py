# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce qu'on vient de lâcher sur la fenêtre (`gui/depot.py`) — **sans PySide6**.

Le glisser-déposer n'existait pas : zéro `setAcceptDrops`, zéro `dragEnterEvent`, zéro
`dropEvent`, zéro `mimeData` dans tout `gui/`. Ce module en est la moitié qui DÉCIDE ; la
moitié Qt se réduit à convertir un `QMimeData` en liste de chemins.

## Les deux propriétés qui comptent

**Aucun lâcher ne reste silencieux.** Un geste qui ne produit rien passe pour un défaut de
l'application une fois sur deux — c'est le reproche même que le plan adresse à l'état vide du
premier lancement. `classer()` rend donc toujours un message, y compris quand tout va bien.

**On ne devine pas sur un dépôt ambigu.** Deux `.cbz` et un `.docx` lâchés ensemble ne sont pas
un geste : choisir à la place de l'utilisateur créerait un projet ou fusionnerait un glossaire,
et l'un des deux serait toujours le mauvais.
"""
from __future__ import annotations

import pytest

from gui import depot as dep


@pytest.fixture
def planches(tmp_path):
    """Un dossier de planches à plat."""
    dossier = tmp_path / "Mon Manga - Vol.1"
    dossier.mkdir()
    for i in range(1, 4):
        (dossier / f"page_{i:04d}.png").write_bytes(b"\x89PNG")
    return dossier


# --------------------------------------------------------------------------- #
# Les trois cas du plan
# --------------------------------------------------------------------------- #

def test_un_dossier_de_planches_est_une_source(planches):
    genre, retenus, message = dep.classer([planches])
    assert genre == dep.SOURCES
    assert retenus == [planches]
    assert "projet" in message


def test_un_dossier_dont_les_planches_sont_un_cran_plus_bas(tmp_path):
    """`Tome/manga/*.png` est l'arborescence que le pipeline écrit lui-même ; la refuser
    ferait échouer le geste sur un tome copié depuis un autre poste."""
    tome = tmp_path / "Vol.2"
    (tome / "manga").mkdir(parents=True)
    (tome / "manga" / "p1.jpg").write_bytes(b"\xff\xd8")
    assert dep.classer([tome])[0] == dep.SOURCES


@pytest.mark.parametrize("nom", ["tome.cbz", "tome.cbr", "tome.zip"])
def test_une_archive_est_une_source(tmp_path, nom):
    archive = tmp_path / nom
    archive.write_bytes(b"PK")
    assert dep.classer([archive])[0] == dep.SOURCES


def test_une_image_seule_est_une_source(tmp_path):
    image = tmp_path / "planche.webp"
    image.write_bytes(b"RIFF")
    assert dep.classer([image])[0] == dep.SOURCES


@pytest.mark.parametrize("nom", ["glossaire.yaml", "g.yml", "termes.docx", "notes.txt",
                                 "liste.md", "export.csv"])
def test_les_formats_de_glossaire(tmp_path, nom):
    fichier = tmp_path / nom
    fichier.write_text("a = b", encoding="utf-8")
    genre, _, message = dep.classer([fichier])
    assert genre == dep.GLOSSAIRE
    assert "glossaire" in message


def test_un_yaml_se_distingue_d_un_glossaire_redige(tmp_path):
    """Deux sémantiques, deux fonctions de `core/glossary_import.py` : un YAML du projet se
    RÉINTÈGRE (il fait autorité), un glossaire rédigé à la main s'IMPORTE (il enrichit)."""
    assert dep.est_glossaire_yaml(tmp_path / "glossaire.yaml") is True
    assert dep.est_glossaire_yaml(tmp_path / "glossaire.docx") is False


# --------------------------------------------------------------------------- #
# Le refus, qui doit parler
# --------------------------------------------------------------------------- #

def test_un_type_inconnu_produit_un_message_qui_nomme_l_extension(tmp_path):
    fichier = tmp_path / "planche.psd"
    fichier.write_bytes(b"8BPS")
    genre, _, message = dep.classer([fichier])
    assert genre == dep.INCONNU
    assert ".psd" in message
    assert ".cbz" in message, "le message doit dire ce qui EST attendu, pas seulement refuser"


def test_un_dossier_sans_planches_est_refuse(tmp_path):
    vide = tmp_path / "captures"
    vide.mkdir()
    (vide / "notes.pdf").write_bytes(b"%PDF")
    genre, _, message = dep.classer([vide])
    assert genre == dep.INCONNU
    assert message


def test_un_depot_melange_ne_devine_pas(tmp_path, planches):
    glossaire = tmp_path / "glossaire.yaml"
    glossaire.write_text("termes: []", encoding="utf-8")
    genre, _, message = dep.classer([planches, glossaire])
    assert genre == dep.INCONNU
    assert "séparément" in message


def test_l_inconnu_l_emporte_sur_le_melange(tmp_path, planches):
    """Entre « je n'ai pas su lire ce fichier » et « tu m'as donné deux choses à la fois »,
    c'est le premier qui apprend quelque chose.

    ⚠ **L'exemple a changé au lot 40, pas la règle.** Ce test lâchait un `.pdf`, qui était
    alors inconnu ; il désigne désormais un tome de roman (`SOURCES_LN`). `.psd` prend sa place
    — c'est le format que le dépôt produit sans jamais l'ingérer, donc l'inconnu le plus
    probable dans un vrai dossier de travail."""
    bizarre = tmp_path / "planche.psd"
    bizarre.write_bytes(b"8BPS")
    genre, _, message = dep.classer([planches, bizarre])
    assert genre == dep.INCONNU
    assert ".psd" in message


def test_un_pdf_est_une_source_de_roman(tmp_path):
    """Lot 40. ⚠ `.pdf` et `.epub` sont les deux SEULES extensions de roman qui ne soient
    ambiguës avec rien — `.docx`, `.txt` et `.md` appartiennent déjà aux glossaires."""
    roman = tmp_path / "volume.pdf"
    roman.write_bytes(b"%PDF")
    genre, retenus, message = dep.classer([roman])
    assert genre == dep.SOURCES_LN
    assert retenus == [roman]
    assert "LIGHT NOVEL" in message


def test_un_docx_reste_un_glossaire(tmp_path):
    """⚠ **Le comportement est INCHANGÉ, et c'est délibéré.** Un `.docx` lâché peut aussi bien
    être un glossaire rédigé à la main qu'un tome de roman, et l'extension seule ne permet pas
    de trancher. Le dépôt refuse de deviner ; la création d'un roman à partir d'un `.docx`
    passe par « Nouveau projet », où l'on dit ce qu'on veut."""
    fichier = tmp_path / "glossaire.docx"
    fichier.write_bytes(b"PK")
    assert dep.nature(fichier) == dep.GLOSSAIRE


def test_un_melange_planches_et_roman_nomme_les_deux(tmp_path, planches):
    """Avec trois familles au lieu de deux, « des planches et des glossaires » serait faux une
    fois sur trois. Le message nomme ce qu'il a réellement vu."""
    roman = tmp_path / "volume.epub"
    roman.write_bytes(b"PK")
    genre, _, message = dep.classer([planches, roman])
    assert genre == dep.INCONNU
    assert "planches" in message and "roman" in message


def test_un_depot_vide_ne_leve_pas():
    genre, retenus, message = dep.classer([])
    assert genre == dep.INCONNU
    assert retenus == []
    assert message


def test_le_message_est_toujours_rempli(tmp_path, planches):
    """Y compris quand le verdict est bon : un geste réussi mérite autant d'être confirmé
    qu'un geste refusé d'être expliqué."""
    glossaire = tmp_path / "g.yaml"
    glossaire.write_text("termes: []", encoding="utf-8")
    for cible in ([planches], [glossaire], [tmp_path / "rien.xyz"], []):
        assert dep.classer(cible)[2].strip()


def test_les_extensions_d_images_viennent_du_pipeline():
    """Importées de `manga.ingest`, pas recopiées : deux listes qui divergent, c'est un `.bmp`
    accepté au dépôt et refusé au scan — un projet créé qui s'ouvre vide."""
    from manga.ingest import IMG_EXTS
    assert dep.IMG_EXTS is IMG_EXTS
