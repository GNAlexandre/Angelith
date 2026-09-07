# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`gui/lancement.py` — le point d'entrée, ses deux sondes de livraison, et la ligne « À propos ».

## Ce que ce fichier protège

Trois propriétés que le lot 37 a payées, dont deux qu'il a d'abord perdues :

1. **`cli.configurer_stdout()` est appelé à l'IMPORT.** Il l'était dans `gui.py` ; il a été
   perdu au déménagement de `main`, et le gel est mort sur `UnicodeEncodeError` au premier
   « ⚠ » d'un JSON, sur une console cp1252. Le test lit la source plutôt que le comportement :
   l'appel doit être au niveau du module, pas dans `main` — c'est cette différence-là qui a
   coûté un cycle de gel de huit minutes ;
2. **`--diagnostic-json` rend un JSON analysable**, dans un fichier si on le demande. Mesuré le
   2026-09-06 : `transformers` écrit un avertissement sur la sortie standard **avant** le
   premier octet du JSON ;
3. **la page « À propos » dit que la vérification de version est désarmée**, plutôt que de se
   taire. Une promesse (« rien ne sort de la machine ») s'écrit là où on la cherche.

⚠ `--verifier-demarrage` n'est pas testé ici : il demande une `QApplication`, une fenêtre et un
`show()`. C'est `tests/test_gui_fenetre.py` qui construit la fenêtre, et la CI qui rejoue le
drapeau sur le binaire gelé — là où il sert.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.version import __version__

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "gui" / "lancement.py"


def test_configurer_stdout_est_appele_a_l_import():
    """⚠ Au niveau du MODULE. Dans `main`, il serait trop tard pour un `--help` et pour toute
    erreur d'argparse, et il ne couvrirait pas un import qui écrit."""
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    appels = [n for n in arbre.body
              if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
              and getattr(n.value.func, "attr", "") == "configurer_stdout"]
    assert appels, (
        "cli.configurer_stdout() n'est plus appelé à l'import de gui/lancement.py — "
        "une console cp1252 fera tomber la première sortie qui porte un « ⚠ »")


def test_les_deux_sondes_sont_hors_de_l_aide():
    """Ce sont des sondes de livraison, pas des modes d'usage. Les afficher dans `--help`
    inviterait à s'en servir pour diagnostiquer, alors que le geste documenté est
    `run.py --check` ou la page Diagnostic."""
    from gui import lancement
    aide = lancement.construire_parseur().format_help()
    assert "--diagnostic-json" not in aide
    assert "--verifier-demarrage" not in aide


def test_la_version_affichee_porte_la_version_et_l_etat_de_la_brique():
    from gui import lancement
    from core.version import ETAT_BRIQUES
    affiche = lancement.version_affichee()
    assert __version__ in affiche
    assert ETAT_BRIQUES["manga"] in affiche


def test_diagnostic_json_ecrit_un_fichier_analysable(tmp_path):
    """Bout en bout, dans un sous-processus : c'est le seul moyen de reproduire ce que la CI
    fait, y compris le bruit qu'une dépendance tierce écrit sur la sortie standard."""
    cible = tmp_path / "diagnostic.json"
    resultat = subprocess.run(
        [sys.executable, "gui.py", "--diagnostic-json", str(cible)],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
    charge = json.loads(cible.read_text(encoding="utf-8"))
    assert __version__ in charge["version"]
    assert charge["gele"] is False           # on tourne depuis le dépôt
    assert charge["resume"]["total"] > 0
    assert charge["verdicts"]


def test_le_diagnostic_du_depot_passe_le_verificateur_de_gel_sauf_les_points_de_machine_nue(
        tmp_path):
    """⚠ Le complément honnête du test précédent. Sur CETTE machine, les poids sont là et
    `sources/` existe : les deux points que la CI exige sur un runner nu sont donc absents, et
    c'est normal. Ce qu'on vérifie ici, c'est que le vérificateur ne se plaint de RIEN
    d'autre — sinon il échouerait en CI pour une raison sans rapport avec le gel."""
    from tools import verifier_gel
    cible = tmp_path / "diagnostic.json"
    subprocess.run([sys.executable, "gui.py", "--diagnostic-json", str(cible)],
                   cwd=RACINE, capture_output=True, check=True)
    echecs = verifier_gel.verifier_diagnostic(cible)
    restants = [e for e in echecs
                if not any(a in e for a in verifier_gel.ATTENDUS_MACHINE_NUE)
                and "gelé" not in e]
    assert not restants, restants


@pytest.mark.parametrize("config", [{}, {"maj": {}}, {"maj": {"verifier": False}}])
def test_la_page_a_propos_dit_que_la_verification_est_desarmee(config):
    pytest.importorskip("PySide6")
    from gui.dialogues import texte_a_propos
    texte = texte_a_propos(config)
    assert "désarmée" in texte
    assert "Rien ne sort de cette machine" in texte


def test_la_page_a_propos_ne_fait_aucun_appel_reseau_quand_c_est_desarme(monkeypatch):
    """Le double lèverait si une requête partait. Une promesse se teste."""
    pytest.importorskip("PySide6")
    faux = type(sys)("httpx")
    faux.get = lambda *a, **k: (_ for _ in ()).throw(AssertionError("appel réseau interdit"))
    monkeypatch.setitem(sys.modules, "httpx", faux)
    from gui.dialogues import texte_a_propos
    assert "désarmée" in texte_a_propos({})
