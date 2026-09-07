# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`pyproject.toml` — **la version est LUE, jamais recopiée**, et les cinq enveloppes tiennent.

## Ce que ce fichier protège

Le critère 3 du `PLAN-37` : « la version est lue **dynamiquement** depuis `core/version.py` ;
un test compare la version des métadonnées du paquet à `__version__` ».

Le risque est nommé dans le plan : « Deux numéros de version, c'est un `tests/test_version.py`
qui passe pendant qu'on livre le mauvais numéro. » `tests/test_version.py` compare
`core/version.py` au CHANGELOG ; il ne saurait rien d'un `version = "2.29.0"` recopié à la main
dans `pyproject.toml`. Ce fichier-ci ferme la boucle.

Il tient aussi le critère 5 — « les cinq `requirements-*.txt` fonctionnent toujours » — au seul
niveau où un test peut le tenir sans installer quoi que ce soit : chacun appelle bien l'extra
qui lui correspond, et chaque extra existe.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from core.version import __version__

RACINE = Path(__file__).resolve().parent.parent
PYPROJECT = RACINE / "pyproject.toml"


@pytest.fixture(scope="module")
def projet() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
#  La version
# --------------------------------------------------------------------------- #

def test_la_version_est_declaree_dynamique(projet):
    """⚠ Le test qui compte, et il est NÉGATIF : `version` doit être absent de `[project]`.
    Un littéral recopié passerait tous les autres tests de ce fichier."""
    assert "version" in projet["project"]["dynamic"]
    assert "version" not in projet["project"], (
        "un littéral de version dans pyproject.toml : la source unique reste core/version.py")


def test_la_version_dynamique_pointe_sur_l_attribut_du_depot(projet):
    attr = projet["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "core.version.__version__", attr


def test_setuptools_lit_bien_la_meme_version():
    """Bout en bout : ce que le CONSTRUCTEUR de paquet obtient, comparé à `__version__`.

    ⚠ `read_configuration` et non `pip install` : construire une roue à chaque exécution de la
    suite coûterait plusieurs secondes pour la même assertion. Si setuptools cessait de savoir
    lire l'attribut — un changement d'API amont —, ce test tomberait le jour même."""
    setuptools = pytest.importorskip("setuptools.config.pyprojecttoml")
    lu = setuptools.read_configuration(str(PYPROJECT))["project"]["version"]
    assert lu == __version__, (
        f"pyproject.toml rend {lu}, core/version.py annonce {__version__}")


# --------------------------------------------------------------------------- #
#  L'identité du paquet
# --------------------------------------------------------------------------- #

def test_le_nom_public_est_angelith(projet):
    """`Yume-Trad` est le nom du dépôt de travail, jamais celui qu'un utilisateur voit."""
    assert projet["project"]["name"] == "angelith"
    from core.installation import NOM
    assert NOM.lower() == projet["project"]["name"]


def test_la_licence_est_l_agpl(projet):
    assert projet["project"]["license"] == "AGPL-3.0-or-later"
    assert (RACINE / "LICENSE").is_file()


# --------------------------------------------------------------------------- #
#  Les points d'entrée — L37.1
# --------------------------------------------------------------------------- #

#: Les quatre briques en console, telles que `tests/test_version.py:BRIQUES` les nomme.
ENTREES_CONSOLE = {
    "angelith": ("run", "run.py"),
    "angelith-manga": ("run_manga", "run_manga.py"),
    "angelith-ocr": ("run_ocr", "run_ocr.py"),
    "angelith-illustration": ("run_illustration", "run_illustration.py"),
    "angelith-console": ("app", "app.py"),
}


@pytest.mark.parametrize("nom,cible", sorted(ENTREES_CONSOLE.items()))
def test_chaque_entree_console_pointe_sur_un_main_qui_existe(projet, nom, cible):
    module, script = cible
    assert projet["project"]["scripts"][nom] == f"{module}:main"
    assert (RACINE / script).is_file()
    assert "\ndef main(" in (RACINE / script).read_text(encoding="utf-8")


def test_l_interface_est_en_gui_scripts_et_pas_en_scripts(projet):
    """⚠ La distinction n'est pas cosmétique : sous Windows, un point d'entrée `scripts` ouvre
    une console noire derrière la fenêtre."""
    assert "angelith-gui" in projet["project"]["gui-scripts"]
    assert "angelith-gui" not in projet["project"].get("scripts", {})


def test_l_interface_ne_pointe_pas_sur_gui_py(projet):
    """`gui.py` n'est pas importable — le dépôt porte un module `gui.py` ET un paquet `gui/`,
    et Python résout le paquet. Le point d'entrée doit donc viser `gui.lancement`."""
    assert projet["project"]["gui-scripts"]["angelith-gui"] == "gui.lancement:main"
    from gui import lancement
    assert callable(lancement.main)


def test_gui_py_delegue_et_ne_duplique_pas():
    """Le corps de `main` vit à un seul endroit. Deux copies, c'est deux comportements le jour
    où l'une des deux est corrigée."""
    code = (RACINE / "gui.py").read_text(encoding="utf-8")
    assert "from gui.lancement import main" in code
    assert "QApplication" not in code.split('"""')[-1]


# --------------------------------------------------------------------------- #
#  Les extras et les cinq enveloppes — L37.2
# --------------------------------------------------------------------------- #

#: Chaque fichier et l'extra qu'il doit appeler. `requirements.txt` appelle le socle nu.
ENVELOPPES = {
    "requirements.txt": "-e .",
    "requirements-gui.txt": "-e .[gui]",
    "requirements-manga.txt": "-e .[manga]",
    "requirements-scan.txt": "-e .[scan]",
    "requirements-dev.txt": "-e .[dev]",
}


@pytest.mark.parametrize("fichier,ligne", sorted(ENVELOPPES.items()))
def test_chaque_requirements_est_une_enveloppe(fichier, ligne):
    lignes = [ln.strip() for ln in (RACINE / fichier).read_text(encoding="utf-8").splitlines()]
    vivantes = [ln for ln in lignes if ln and not ln.startswith("#")]
    assert ligne in vivantes, (fichier, vivantes)


@pytest.mark.parametrize("fichier", sorted(ENVELOPPES))
def test_aucune_enveloppe_ne_redeclare_une_dependance(fichier, projet):
    """⚠ **Le test du critère 5.** Une dépendance déclarée aux deux endroits finit par en
    diverger, et c'est le gel qui manque un module. La seule exception écrite est `pytest` dans
    `requirements.txt`, qui n'est pas une dépendance d'exécution du paquet et que le fichier
    déclare depuis toujours comme outil de test."""
    tous = set(projet["project"]["dependencies"])
    for paquets in projet["project"]["optional-dependencies"].values():
        tous |= set(paquets)
    noms = {re.split(r"[<>=!\[ ]", p)[0].lower() for p in tous}
    lignes = [ln.strip() for ln in (RACINE / fichier).read_text(encoding="utf-8").splitlines()]
    vivantes = [ln for ln in lignes if ln and not ln.startswith("#") and not ln.startswith("-e")]
    intrus = [ln for ln in vivantes
              if re.split(r"[<>=!\[ ]", ln)[0].lower() in noms and "pytest" not in ln]
    assert not intrus, (fichier, intrus)


def test_les_cinq_fichiers_existent_toujours():
    """Ils ne disparaissent pas : la CI, les procédures et le README les citent nommément."""
    for fichier in ENVELOPPES:
        assert (RACINE / fichier).is_file(), fichier


def test_le_socle_est_recopie_a_la_lettre_du_fichier_historique(projet):
    """Le plafond `openai<3` est une MESURE (`requirements.txt` l'explique sur dix lignes) : il
    doit survivre au déménagement, pas être arrondi."""
    assert "openai>=1.40,<3" in projet["project"]["dependencies"]
    assert "httpx>=0.27" in projet["project"]["dependencies"]


def test_scan_est_un_sous_ensemble_strict_de_manga(projet):
    """Mesuré le 2026-09-06 : les deux jeux rendent la MÊME liste de 72 paquets. Le plan
    demandait quatre jeux de dépendances à peser ; il n'y en a que trois de distincts."""
    extras = projet["project"]["optional-dependencies"]
    assert set(extras["scan"]) <= set(extras["manga"])


def test_les_extras_du_plan_existent_tous(projet):
    attendus = {"gui", "manga", "scan", "illustration", "dev"}
    assert attendus <= set(projet["project"]["optional-dependencies"])
