# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les garde-fous de dépôt survivent à une console **cp1252** — et n'importent rien.

## Le défaut que ce fichier ferme

`tools/verifier_disclosure.py` levait un `UnicodeEncodeError` sur une console Windows par
défaut, **après** avoir jugé les commits : il perdait son verdict au moment de l'imprimer, sur
le premier « ⚠ » de sa sortie. Mesuré le 2026-09-04. `tools/sonar_issues.py` tombait dès son
`--help`, dont la docstring en porte deux.

Le défaut est d'autant plus vicieux qu'il ne touche que les cas qui ont quelque chose à
DIRE : un dépôt propre passe, une branche à problème plante. Un garde-fou qui ne tombe que
lorsqu'il aurait servi n'est pas un garde-fou.

## Les deux propriétés, et pourquoi elles vont ensemble

1. **ces outils reconfigurent stdout ET stderr en UTF-8** ;
2. **ils n'importent que la bibliothèque standard.**

La seconde explique la forme de la première. `core/cli.py:configurer_stdout()` fait exactement
ce qu'il faut — mais `core/cli.py` importe `yaml`, et
`.github/workflows/garde-fous.yml` lance ces outils sur un Python nu, **sans un seul
`pip install`**. Utiliser le helper partagé y casserait le job. Les quatre lignes sont donc
répétées, et c'est ce fichier qui les tient en phase.

⚠ **Le jour où l'un de ces outils gagnera une dépendance**, le test 2 tombera — et c'est le bon
moment pour se demander si le job de CI doit installer quelque chose, pas six mois plus tard
en lisant un `ModuleNotFoundError` dans un log d'Actions.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Les outils lancés par le job « Garde-fous » — les trois qui doivent tourner sur un Python
#: nu — plus les deux autres outils de dépôt sans dépendance. Cf. `garde-fous.yml`.
OUTILS_SANS_DEPENDANCE = ("verifier_disclosure.py", "verifier_arbre.py",
                          "verifier_livraison.py", "compte_de_tests.py",
                          "sonar_issues.py")

#: Ceux que `garde-fous.yml` lance vraiment. Un sous-ensemble, et c'est celui dont l'absence
#: de dépendance n'est pas un confort mais une condition d'exécution.
OUTILS_DE_LA_CI = ("verifier_disclosure.py", "verifier_arbre.py", "verifier_livraison.py")

#: Ceux qui doivent reconfigurer leur sortie. `compte_de_tests.py` n'imprime que du JSON
#: (`ensure_ascii` par défaut), il n'en a pas besoin et ne le fait pas — l'exiger de lui
#: serait de la cérémonie.
OUTILS_UTF8 = ("verifier_disclosure.py", "verifier_arbre.py", "verifier_livraison.py",
               "sonar_issues.py", "notes_de_version.py")


def _source(nom: str) -> str:
    return (RACINE / "tools" / nom).read_text(encoding="utf-8")


def _lancer(args: list[str]) -> subprocess.CompletedProcess:
    """Lance un outil avec la console Windows par défaut — **c'est tout le test**.

    `PYTHONIOENCODING=cp1252` reproduit exactement ce qu'un `python tools/…` rencontre dans
    un terminal Windows non configuré, qui est le cas de l'immense majorité des lancements."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run([sys.executable, *args], cwd=str(RACINE), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)


# --------------------------------------------------------------------------- #
# 1. La sortie survit à cp1252
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("nom", OUTILS_UTF8)
def test_l_outil_reconfigure_ses_deux_flux(nom):
    """stdout **et** stderr. `notes_de_version.py` ne reconfigurait que stdout, et son seul
    chemin d'erreur (`print(str(e), file=sys.stderr)`) portait donc le même défaut."""
    source = _source(nom)
    assert "_flux.reconfigure(encoding=\"utf-8\")" in source, nom
    assert "sys.stdout, sys.stderr" in source, f"{nom} : stderr aussi, pas seulement stdout"


@pytest.mark.parametrize("nom", OUTILS_UTF8)
def test_l_aide_ne_tombe_pas_sur_une_console_cp1252(nom):
    """⚠ `sonar_issues.py --help` tombait ici : sa docstring porte deux « ⚠ », et `argparse`
    l'imprime comme description. Un outil dont on ne peut pas lire l'aide est un outil qu'on
    n'utilise pas."""
    sortie = _lancer(["tools/" + nom, "--help"])
    assert "UnicodeEncodeError" not in sortie.stderr, sortie.stderr[-1500:]
    assert sortie.returncode == 0, sortie.stderr[-1500:]


def test_le_verdict_de_disclosure_survit_a_cp1252():
    """**Le cas exact qui a motivé ce fichier.**

    L'outil jugeait les commits, puis mourait en imprimant son verdict — et il ne meurt que
    quand il a quelque chose à dire, puisque le « ⚠ » n'apparaît que sur un commit qui déclare
    « Revu et testé manuellement : non ». Un dépôt propre passait ; une branche à relire
    plantait."""
    sortie = _lancer(["tools/verifier_disclosure.py", "--historique", "3"])
    assert "UnicodeEncodeError" not in sortie.stderr, sortie.stderr[-1500:]
    assert sortie.returncode == 0, sortie.stderr[-1500:]
    assert "commits conformes" in sortie.stdout


def test_verifier_arbre_et_livraison_survivent_aussi():
    """Ils ne tombaient pas au 2026-09-04 — aucun de leurs messages ne portait de caractère
    hors cp1252 — et c'est précisément pour cela qu'ils sont ici : la seule chose qui les
    séparait de la panne était qu'aucun « ⚠ » n'avait encore été tapé dans leurs chaînes."""
    for args in (["tools/verifier_arbre.py", "--suivi", "--non-bloquant"],
                 ["tools/verifier_livraison.py", "--base", "HEAD~1"]):
        sortie = _lancer(args)
        assert "UnicodeEncodeError" not in sortie.stderr, (args, sortie.stderr[-1500:])


# --------------------------------------------------------------------------- #
# 2. …et ils n'importent rien, ce qui explique la forme du correctif
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("nom", OUTILS_SANS_DEPENDANCE)
def test_l_outil_n_importe_que_la_bibliotheque_standard(nom):
    """⚠ **C'est une condition d'exécution, pas un principe.** `garde-fous.yml` ne fait aucun
    `pip install` : un import de `yaml`, de `PySide6` ou même de `core.cli` (qui importe
    `yaml`) casserait le job. C'est la raison pour laquelle ces outils ne peuvent PAS appeler
    `core.cli.configurer_stdout()` et répètent ses quatre lignes."""
    arbre = ast.parse(_source(nom))
    modules = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules |= {a.name.split(".")[0] for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            modules.add(noeud.module.split(".")[0])
    hors = sorted(m for m in modules if m not in sys.stdlib_module_names)
    assert hors == [], (
        f"{nom} importe {hors} — or « Garde-fous » le lance sans `pip install`. Si cette "
        f"dépendance est voulue, il faut l'installer dans le job AVANT de la déclarer ici.")


def test_le_job_garde_fous_n_installe_toujours_rien():
    """Le pendant du test précédent : si le job se met à installer, la contrainte tombe et la
    duplication des quatre lignes n'a plus de justification. Qu'on le sache le jour même."""
    workflow = (RACINE / ".github" / "workflows" / "garde-fous.yml").read_text(encoding="utf-8")
    assert "pip install" not in workflow
    for nom in OUTILS_DE_LA_CI:
        assert f"tools/{nom}" in workflow, f"{nom} n'est plus lancé par le job"
