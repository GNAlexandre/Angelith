# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Contrat des alias de transition `pipeline.<nom>` → `core.<nom>` (lot 2.1).

Ces tests ne vérifient pas *que ça importe* — ça, n'importe quel shim le fait, y compris
un `from core.x import *` qui casserait silencieusement tout le monkeypatching du dépôt.
Ils vérifient l'**identité d'objet**, seule propriété qui rend le déplacement neutre.
"""
from __future__ import annotations

import importlib

import pytest

# Les neuf modules déplacés dans le socle au lot 2.1.
DEPLACES = ["agents", "control", "glossary", "glossary_build", "glossary_import",
            "llm", "power", "reporter", "tokens"]


@pytest.mark.parametrize("nom", DEPLACES)
def test_alias_est_le_meme_objet_module(nom):
    """`pipeline.x is core.x`. C'est CE test qui distingue l'auto-remplacement dans
    `sys.modules` d'un `import *` : le second créerait deux objets module distincts,
    tous les deux important sans erreur."""
    ancien = importlib.import_module(f"pipeline.{nom}")
    nouveau = importlib.import_module(f"core.{nom}")
    assert ancien is nouveau


@pytest.mark.parametrize("nom", DEPLACES)
def test_from_pipeline_import_rend_le_module_du_socle(nom):
    """`from pipeline import x` passe par l'attribut du paquet parent, pas par
    `sys.modules` — c'est une seconde voie d'accès, à vérifier séparément. Elle marche
    parce que `importlib._bootstrap._load()` relit `sys.modules[nom]` APRÈS exécution du
    module et lie *ce* résultat au paquet parent."""
    paquet = importlib.import_module("pipeline")
    assert getattr(paquet, nom) is importlib.import_module(f"core.{nom}")


def test_monkeypatch_via_lancien_chemin_atteint_le_code_appele(monkeypatch):
    """Le vrai risque du refactor, en situation : un test patche `pipeline.agents.LLM`
    (chemin historique) alors que `core.agents.build_agents` résout `LLM` dans ses
    globals. Sans identité d'objet, le patch ne porterait pas — `build_agents`
    instancierait la VRAIE classe et le test bloquerait sur une socket au lieu
    d'échouer."""
    import pipeline.agents as ancien

    from core.agents import build_agents

    temoins = []

    class FauxLLM:
        def __init__(self, **kwargs):
            temoins.append(kwargs)

    monkeypatch.setattr(ancien, "LLM", FauxLLM)
    config = {
        "chemins": {"prompts": "prompts"},
        "modeles": {"traducteur": {"model": "m", "endpoint": "reflexion"}},
        "temperatures": {"traducteur": 0.3},
        "llm": {"api_key": "k", "timeout": 1, "max_retries": 0,
                "base_url": "http://x", "endpoints": {"reflexion": {"think": True}}},
    }
    build_agents(config, llm=None)
    assert temoins, "le patch de pipeline.agents.LLM n'a pas atteint core.agents"
    assert temoins[0]["think"] is True


def test_les_alias_ne_reexportent_pas_par_etoile():
    """Garde-fou sur la FORME du shim, pas seulement sur son effet : un futur
    « simplification » en `from core.x import *` repasserait les deux tests d'identité
    ci-dessus au vert par accident tant que personne ne patche, puis casserait des tests
    éloignés de manière incompréhensible. On interdit donc la forme à la source.

    Contrôle sur l'AST et non sur le texte : les docstrings des shims *citent* justement
    `from core.x import *` comme contre-exemple à ne pas suivre — un `not in texte` se
    déclencherait sur l'avertissement lui-même."""
    import ast
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1] / "pipeline"
    for nom in DEPLACES:
        arbre = ast.parse((racine / f"{nom}.py").read_text(encoding="utf-8"))
        etoiles = [n for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom)
                   and any(a.name == "*" for a in n.names)]
        assert not etoiles, f"pipeline/{nom}.py réexporte par étoile"
        # …et l'auto-remplacement est bien là : `sys.modules[__name__] = _impl`.
        assigne = [n for n in ast.walk(arbre) if isinstance(n, ast.Assign)
                   and isinstance(n.targets[0], ast.Subscript)
                   and ast.unparse(n.targets[0]) == "sys.modules[__name__]"]
        assert assigne, f"pipeline/{nom}.py n'utilise pas l'auto-remplacement dans sys.modules"


def test_le_socle_ne_depend_pas_du_pipeline():
    """Le sens de la dépendance est la raison d'être du lot : `core/` doit pouvoir vivre
    sans `pipeline/`. Un `from pipeline import …` dans le socle recréerait le cycle
    qu'on vient de défaire (et ferait passer les imports par les alias, donc marcherait
    — d'où le besoin d'un test)."""
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1] / "core"
    fautifs = []
    for f in sorted(racine.glob("*.py")):
        for i, ligne in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            nu = ligne.strip()
            if nu.startswith(("import pipeline", "from pipeline", "import manga", "from manga")):
                fautifs.append(f"{f.name}:{i}: {nu}")
    assert not fautifs, "le socle importe une brique :\n" + "\n".join(fautifs)
