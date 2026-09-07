# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Une seule** fonction résout les données livrées — critère 7 du `PLAN-37`.

## Le mode de panne, et pourquoi un test de SOURCE

« Un chemin oublié est une brique qui marche en développement et échoue gelée ; c'est le mode
de panne le plus courant de cet exercice. » Il ne se voit pas à l'exécution dans le dépôt,
parce que `Path(__file__).parents[1]` et `sys._MEIPASS` désignent le même dossier quand on lance
`python gui.py` depuis la racine. Un test de comportement ne peut donc rien attraper ici sans
construire un vrai gel — plusieurs minutes par exécution.

Ce fichier lit donc les **sources**, comme `tests/test_gui_destinations.py` lit celles de
l'interface avec `ast` : il échoue le jour où un `Path(__file__)` réapparaît dans un module qui
résout une donnée livrée. Le coût est nul, et le défaut est attrapé le jour même.

## ⚠ Ce que ce test ne dit pas

Il ne dit pas que le gel MARCHE — c'est le job de CI du `PLAN-37` L37.7, qui fait tourner
`--version`, `--diagnostic-json` et `--verifier-demarrage` sur le vrai binaire. Il dit
seulement qu'aucun chemin n'a été réintroduit par la porte de derrière.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Les modules qui résolvent une donnée LIVRÉE, et qui doivent donc passer par
#: `core/installation.py`. La liste est nommée plutôt que devinée : un balayage de tout le
#: dépôt attraperait `tests/` et `tools/`, qui n'entrent jamais dans un gel.
MODULES_DE_DONNEES = (
    "manga/typeset.py",             # les polices livrées
    "illustration/gabarits/__init__.py",   # les gabarits de prompt
    "gui/dialogues.py",             # les fiches de provenance des poids
    "manga/reparations.py",         # le script d'installation des polices
    "core/langues.py",              # les packs et les prompts
    "gui/reglages.py",              # `.angelith/`
    "gui/profils.py",               # `.angelith/`
    "core/cli.py",                  # `config.yaml`
)

#: Le seul module autorisé à connaître `sys._MEIPASS`. Un second lecteur, c'est deux
#: résolutions qui divergeront.
MODULE_RESOLVEUR = "core/installation.py"


def _sans_docstrings(chemin: Path) -> str:
    """Le code du fichier, ses docstrings et commentaires exclus.

    ⚠ Indispensable : ces modules DOCUMENTENT le défaut qu'ils ont corrigé, en citant
    `Path(__file__)` dans leurs commentaires. Un test qui lirait le texte brut échouerait sur
    l'explication du correctif — le pire des faux positifs, celui qui punit d'avoir écrit
    pourquoi."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)) and ast.get_docstring(noeud):
            noeud.body = noeud.body[1:] or [ast.Pass()]
    return ast.unparse(arbre)


@pytest.mark.parametrize("relatif", MODULES_DE_DONNEES)
def test_aucun_chemin_relatif_a_dunder_file(relatif):
    code = _sans_docstrings(RACINE / relatif)
    assert "__file__" not in code, (
        f"{relatif} construit un chemin depuis __file__. Gelé, il désignerait l'intérieur "
        f"de l'archive PyInstaller. Passe par core.installation.ressource().")


@pytest.mark.parametrize("relatif", MODULES_DE_DONNEES)
def test_aucun_module_ne_lit_meipass_lui_meme(relatif):
    code = _sans_docstrings(RACINE / relatif)
    assert "_MEIPASS" not in code, (
        f"{relatif} lit sys._MEIPASS. Un seul module a le droit : {MODULE_RESOLVEUR}.")


def test_le_resolveur_est_le_seul_a_connaitre_meipass():
    """Le balayage complémentaire : si un module non listé se met à lire `_MEIPASS`, il
    contourne la résolution unique et ce test le nomme."""
    coupables = []
    for chemin in RACINE.rglob("*.py"):
        relatif = chemin.relative_to(RACINE).as_posix()
        if relatif.startswith(("tests/", "tools/")) or "__pycache__" in relatif:
            continue
        if relatif == MODULE_RESOLVEUR:
            continue
        if "_MEIPASS" in _sans_docstrings(chemin):
            coupables.append(relatif)
    assert not coupables, coupables


def test_le_resolveur_connait_bien_meipass():
    """Le test miroir : si `installation.py` cessait de lire `_MEIPASS`, les trois précédents
    passeraient au vert sur un dépôt qui ne sait plus se geler."""
    assert "_MEIPASS" in (RACINE / MODULE_RESOLVEUR).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
#  Le `.spec` déclare bien ce que ces modules iront chercher
# --------------------------------------------------------------------------- #

def _donnees_du_spec() -> list[str]:
    """Les sources déclarées dans `DONNEES` de `angelith.spec`, telles quelles."""
    texte = (RACINE / "angelith.spec").read_text(encoding="utf-8")
    bloc = texte[texte.index("DONNEES = ["):]
    bloc = bloc[:bloc.index("\n]")]
    return re.findall(r'\(\s*"([^"]+)"\s*,\s*"[^"]*"\s*\)', bloc)


@pytest.mark.parametrize("attendu", ["config.yaml", "langues", "templates/fonts",
                                     "illustration/gabarits", "tools/installer_polices.ps1",
                                     "LICENSE", "NOTICE"])
def test_le_spec_embarque_la_donnee(attendu):
    assert attendu in _donnees_du_spec()


def test_chaque_donnee_declaree_existe_vraiment():
    """Une entrée mal orthographiée dans le `.spec` ne fait pas échouer le gel — PyInstaller
    avertit et continue —, elle fait échouer le programme chez l'utilisateur."""
    manquants = [d for d in _donnees_du_spec() if not (RACINE / d).exists()]
    assert not manquants, manquants


def test_le_script_de_polices_est_bien_celui_que_la_reparation_appelle():
    """L'exception à l'exclusion de `tools/` doit désigner le fichier que le code appelle, pas
    un homonyme. Si la réparation change de script, ce test le dit."""
    code = (RACINE / "manga/reparations.py").read_text(encoding="utf-8")
    assert '"installer_polices.ps1"' in code
    assert "tools/installer_polices.ps1" in _donnees_du_spec()
