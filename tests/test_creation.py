# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`creation.py` — créer un projet pour les TROIS dispositions, light novel compris.

## Le manque que ce fichier garde

`manga/creation_projet.py` était le seul module du dépôt qui écrive sous `sources/`, et il ne
connaissait que `manga` et `webtoon`. **Aucune fonction ne savait créer
`sources/<Projet>/<Tome>/<LANGUE>/`** — l'arborescence de la brique historique du projet. La
console se contentait de dire à l'utilisateur de faire le dossier à la main.

## ⚠ Ce que ces tests prouvent, et ce qu'ils ne prouvent pas

Ils prouvent que l'arborescence écrite est **celle que `pipeline/sources.py` lit** : le test
`test_le_pipeline_reconnait_les_cinq_langues` crée un tome par langue et vérifie que le
détecteur de langues du pipeline le voit. C'est la seule preuve qui compte — un dossier créé
que le pipeline ignorerait serait pire qu'une absence de fonction.

Ils ne prouvent pas qu'un tome ainsi créé se traduit : cela demande un run.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import creation as cr

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def config(tmp_path) -> dict:
    return {"chemins": {"sources": str(tmp_path / "sources")},
            "manga": {"chemins": {"sources": str(tmp_path / "sources")}}}


@pytest.fixture
def brut(tmp_path) -> Path:
    """Un dossier qui contient de tout — c'est ce qu'un vrai lâcher produit."""
    dossier = tmp_path / "brut"
    dossier.mkdir()
    (dossier / "volume.epub").write_bytes(b"PK" + b"x" * 100)
    (dossier / "notes.txt").write_text("hello", encoding="utf-8")
    (dossier / "couverture.jpg").write_bytes(b"\xff\xd8" + b"y" * 50)
    return dossier


# --------------------------------------------------------------------------- #
#  Les trois dispositions
# --------------------------------------------------------------------------- #

def test_les_trois_dispositions_existent():
    assert set(cr.DISPOSITIONS) == {cr.MANGA, cr.WEBTOON, cr.LIGHT_NOVEL}


def test_le_light_novel_n_a_pas_de_cran_de_format(config):
    """⚠ **Le point structurant.** `pipeline/sources.py:_langues_presentes` fait un `iterdir()`
    sur le dossier du TOME : insérer un `light_novel/` rendrait le tome invisible au pipeline
    qui doit le lire."""
    cible = cr.dossier_cible(config, "Roman", "Vol.1", quelle=cr.LIGHT_NOVEL, langue="ENG")
    assert cible.parent.name == "Vol.1"
    assert cible.name == "ENG"


def test_le_manga_garde_son_cran_de_format(config):
    """Iso : l'arborescence du manga ne bouge pas d'un cran."""
    assert cr.dossier_cible(config, "M", "Vol.1", quelle=cr.MANGA).name == "manga"
    cible = cr.dossier_cible(config, "M", "Vol.1", quelle=cr.WEBTOON, langue="ENG")
    assert cible.parent.name == "webtoon" and cible.name == "ENG"


def test_la_langue_est_obligatoire_pour_un_roman(config):
    """Un tome de roman sans dossier de langue n'est lisible par personne. Le refuser ICI vaut
    mieux que créer un dossier que rien ne saura ouvrir."""
    with pytest.raises(cr.ErreurCreation) as err:
        cr.dossier_cible(config, "Roman", "Vol.1", quelle=cr.LIGHT_NOVEL)
    assert "langue source est obligatoire" in str(err.value)


def test_la_langue_reste_facultative_pour_le_manga(config):
    """Iso : `manga.langue_source` s'applique déjà, et un cran de moins est un cran de moins à
    comprendre."""
    assert cr.dossier_cible(config, "M", "Vol.1", quelle=cr.MANGA) is not None


def test_une_disposition_inconnue_est_refusee(config):
    with pytest.raises(cr.ErreurCreation):
        cr.dossier_cible(config, "P", "Vol.1", quelle="roman-graphique")


# --------------------------------------------------------------------------- #
#  Ce que chaque disposition accepte
# --------------------------------------------------------------------------- #

def test_le_roman_ne_prend_que_du_texte(brut):
    fichiers = cr.lister_sources([brut], cr.LIGHT_NOVEL)
    noms = sorted(p.name for p in fichiers)
    assert noms == ["notes.txt", "volume.epub"]
    assert "couverture.jpg" not in noms


def test_le_manga_ne_prend_que_des_images(brut):
    noms = {p.name for p in cr.lister_sources([brut], cr.MANGA)}
    assert "couverture.jpg" in noms
    assert "volume.epub" not in noms


def test_les_extensions_du_roman_sont_celles_du_pipeline():
    """⚠ Recopiées d'un seul endroit : `pipeline/sources.py` les liste dans son
    `_langues_presentes`. Deux listes qui divergent, c'est un `.md` accepté à la création et
    ignoré au scan — un projet créé qui s'ouvre vide."""
    source = (RACINE / "pipeline" / "sources.py").read_text(encoding="utf-8")
    for extension in cr.EXTENSIONS_LN:
        assert f'"{extension}"' in source, extension


def test_un_dossier_vide_de_lisible_le_dit(config, tmp_path):
    """Le cas le plus fréquent en pratique n'est pas un nom refusé, c'est un dossier qui ne
    contient rien de lisible. « Aucun fichier lisible » sans dire lesquels oblige à deviner."""
    vide = tmp_path / "vide"
    vide.mkdir()
    (vide / "planche.psd").write_bytes(b"8BPS")
    with pytest.raises(cr.ErreurCreation) as err:
        cr.creer(config, "Roman", "Vol.1", [vide], quelle=cr.LIGHT_NOVEL, langue="ENG")
    assert ".epub" in str(err.value)


# --------------------------------------------------------------------------- #
#  ⚠ La preuve qui compte : le pipeline lit ce qu'on a écrit
# --------------------------------------------------------------------------- #

def test_le_pipeline_reconnait_les_cinq_langues(config, brut):
    """**Le test du lot.** Un dossier créé que `pipeline/sources.py` ignorerait serait pire
    qu'une absence de fonction — et rien, dans le code de création, ne le dirait."""
    from pipeline import sources as ps

    reel = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    mapping = (reel.get("langues") or {}).get("dossiers") or {}
    racine = Path(config["chemins"]["sources"])
    for langue in cr.LANGUES_LN:
        cr.creer(config, "Roman", f"Vol.{langue}", [brut],
                 quelle=cr.LIGHT_NOVEL, langue=langue)
        vues = ps._langues_presentes(racine / "Roman" / f"Vol.{langue}", mapping)
        assert vues, f"{langue} : le pipeline ne voit aucune langue"


def test_le_pipeline_liste_le_projet_cree(config, brut):
    from pipeline import sources as ps

    cr.creer(config, "Mon Roman", "Vol.1", [brut], quelle=cr.LIGHT_NOVEL, langue="ENG")
    racine = str(config["chemins"]["sources"])
    assert ps.list_projects(racine) == ["Mon Roman"]
    assert ps.list_volumes(racine, "Mon Roman") == ["Vol.1"]


# --------------------------------------------------------------------------- #
#  Les garde-fous hérités, qui ne doivent pas se perdre au passage
# --------------------------------------------------------------------------- #

def test_un_tome_existant_n_est_jamais_ecrase(config, brut):
    """Un tome existant porte potentiellement des heures de travail."""
    cr.creer(config, "Roman", "Vol.1", [brut], quelle=cr.LIGHT_NOVEL, langue="ENG")
    with pytest.raises(cr.ErreurCreation) as err:
        cr.creer(config, "Roman", "Vol.1", [brut], quelle=cr.LIGHT_NOVEL, langue="ENG")
    assert "existe déjà" in str(err.value)


def test_les_noms_sont_valides_par_la_meme_fonction_que_le_manga(config, brut):
    """Revalider avec une règle recopiée serait le meilleur moyen d'accepter ici ce que la
    copie refuserait ensuite."""
    with pytest.raises(cr.ErreurCreation):
        cr.creer(config, "Mon/Roman", "Vol.1", [brut], quelle=cr.LIGHT_NOVEL, langue="ENG")


def test_le_module_manga_continue_de_fonctionner(config, brut):
    """⚠ `manga/creation_projet.py` RESTE : la CI, les tests et l'interface l'importent. Ce lot
    ajoute une couche au-dessus, il n'en retire aucune."""
    from manga import creation_projet as crea_manga

    creation = crea_manga.creer(config, "Manga", "Vol.1", [brut], format="manga")
    assert creation.fichiers
    assert Path(creation.dossier).name == "manga"


def test_le_roman_et_le_manga_ne_lisent_pas_la_meme_racine():
    """⚠ Le light novel lit `chemins.sources` à la RACINE ; le manga lit
    `manga.chemins.sources`, qui en hérite profondément. Les confondre ferait écrire le roman
    dans le dossier du manga sur une installation qui les a séparés."""
    config = {"chemins": {"sources": "romans"},
              "manga": {"chemins": {"sources": "planches"}}}
    assert cr.racine_sources(config, cr.LIGHT_NOVEL) == Path("romans")
    assert cr.racine_sources(config, cr.MANGA) == Path("planches")
