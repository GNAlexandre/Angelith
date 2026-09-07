# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`core.llm.test_connection` écrit par un `ecrire` — **et son défaut reste `print`**.

## Pourquoi ce paramètre existe

`core/diagnostic.py` avait besoin du CONSTAT de la sonde LLM (joignable ou non, quels modèles),
la console avait besoin du TEXTE, et une capture de `stdout` aurait tout gâché : cette section
met une douzaine de secondes contre un serveur arrêté (mesuré à 12,1 s le 2026-09-06), et une
capture différée aurait laissé la console muette pendant tout ce temps.

Un paramètre `ecrire` règle les deux : le collecteur passe une fonction qui note ET imprime, la
console garde son défaut `print`, et la sortie de `run.py --test-llm` ne bouge pas d'un octet.

⚠ **Aucun test ici n'ouvre de socket** : le client OpenAI est doublé.
"""
from __future__ import annotations

import pytest

from core import llm


class _FauxModeles:
    def __init__(self, ids):
        self._ids = ids

    def list(self):
        class _Rep:
            data = [type("M", (), {"id": i})() for i in self._ids]
        return _Rep()


class _FauxClient:
    """Un serveur qui répond. La génération est doublée par `_essai_de_generation` doublé."""

    def __init__(self, ids=("m:latest",)):
        self.models = _FauxModeles(list(ids))


@pytest.fixture()
def config():
    return {"llm": {"base_url": "http://exemple/v1"}, "modeles": {"traducteur": "m"}}


def test_le_defaut_reste_print_donc_la_console_ne_change_pas(config, monkeypatch, capsys):
    """⚠ La garantie qui compte : `run.py --test-llm` n'a pas bougé."""
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: _FauxClient())
    monkeypatch.setattr(llm, "_essai_de_generation", lambda *a, **kw: True)
    assert llm.test_connection(config) is True
    sortie = capsys.readouterr().out
    assert "Test de connexion → http://exemple/v1" in sortie
    assert "✓ Serveur joignable." in sortie


def test_avec_un_ecrire_rien_ne_part_sur_stdout(config, monkeypatch, capsys):
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: _FauxClient())
    monkeypatch.setattr(llm, "_essai_de_generation", lambda *a, **kw: True)
    lignes: list[str] = []
    llm.test_connection(config, lignes.append)
    assert capsys.readouterr().out == ""
    assert lignes[0] == "Test de connexion → http://exemple/v1"


def test_les_deux_chemins_produisent_exactement_les_memes_lignes(config, monkeypatch, capsys):
    """⚠ **L'invariant.** Si les deux divergeaient, la page Diagnostic montrerait autre chose
    que la console et personne ne saurait laquelle des deux ment."""
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: _FauxClient())
    monkeypatch.setattr(llm, "_essai_de_generation", lambda *a, **kw: True)
    llm.test_connection(config)
    par_print = capsys.readouterr().out
    lignes: list[str] = []
    llm.test_connection(config, lignes.append)
    assert "".join(ligne + "\n" for ligne in lignes) == par_print


def test_un_serveur_injoignable_ecrit_les_quatre_lignes_d_avant(config, monkeypatch):
    """Les quatre lignes — le constat, le geste, le `base_url` et le détail — sont ce que lit
    quelqu'un dont le run vient d'échouer. Elles n'ont pas changé."""
    def _leve(**kw):
        raise RuntimeError("boum")

    class _ClientQuiTombe:
        class models:
            @staticmethod
            def list():
                raise RuntimeError("Connection error.")

    monkeypatch.setattr(llm, "OpenAI", lambda **kw: _ClientQuiTombe())
    lignes: list[str] = []
    assert llm.test_connection(config, lignes.append) is False
    assert lignes == [
        "Test de connexion → http://exemple/v1",
        "❌ Serveur injoignable.",
        "   • Démarre Ollama : `ollama serve` (ou l'app Ollama).",
        "   • base_url attendu dans config.yaml : http://exemple/v1",
        "   • détail : Connection error.",
    ]


def test_verifier_modeles_rend_les_manquants_et_les_ecrit():
    """Le constat que `core/diagnostic.py` consomme, et le texte que la console imprime."""
    lignes: list[str] = []
    manquants = llm._verifier_modeles({"a", "b"}, ["a:latest"], lignes.append)
    assert manquants == ["b"]
    assert any("absents d'Ollama" in ligne for ligne in lignes)


def test_verifier_modeles_dit_quand_tout_est_la():
    lignes: list[str] = []
    assert llm._verifier_modeles({"a"}, ["a:latest"], lignes.append) == []
    assert lignes == ["✓ Tous les modèles de config.yaml sont disponibles."]


def test_la_section_ollama_rend_un_verdict_bloquant_de_capacite(config, monkeypatch):
    """Le serveur LLM rend un verdict BLOQUANT — sur la **capacité** `llm`, pas sur le socle.

    ⚠ **MISE À JOUR 2026-09-06, lot 39 : l'affirmation de ce test était FAUSSE.** Il disait
    « le serveur LLM appartient au SOCLE : son absence bloque toutes les briques, et c'est la
    seule famille de verdicts dont ce soit vrai », et il le vérifiait fidèlement — c'est
    justement ce qui rendait le défaut invisible.

    Un endpoint injoignable faisait rendre à la page Diagnostic « Aucune brique n'est
    utilisable en l'état » à quelqu'un dont le nettoyage, l'OCR, le relettrage et la saisie
    manuelle marchaient parfaitement. `gui/lanceur.py` décrit d'ailleurs `--from rendu` comme
    « relettrage seul, aucun appel LLM ».

    Le serveur n'est pas une brique, c'est une CAPACITÉ : `diag.LLM` est dans la portée de `ln`
    et de `manga` (donc rien ne change pour un run qui traduit), et `bloquants_pour` sait l'en
    retirer quand le mode sans LLM est actif.

    ⚠ Le TEXTE console, lui, est inchangé — `brique` n'est pas imprimé."""
    from core import cli, diagnostic as diag

    class _ClientQuiTombe:
        class models:
            @staticmethod
            def list():
                raise RuntimeError("Connection error.")

    monkeypatch.setattr(llm, "OpenAI", lambda **kw: _ClientQuiTombe())
    section = cli.section_ollama(config, ecrire=None)
    verdict = section.verdicts[0]
    assert verdict.identifiant == "serveur_llm"
    assert verdict.brique == diag.LLM
    assert verdict.gravite == diag.BLOQUANT
    assert "ollama serve" in verdict.geste
    assert verdict.lignes_console[0].startswith("Test de connexion")
    # ⚠ Il bloque toujours un run qui TRADUIT — la correction ne l'a pas rendu inoffensif.
    section_seule = (section,)
    assert diag.bloquants_pour(section_seule, diag.MANGA)
    assert diag.bloquants_pour(section_seule, diag.LN)
    # …mais plus un run qui ne traduit pas, ni la brique scan, qui ne traduit jamais.
    assert not diag.bloquants_pour(section_seule, diag.MANGA, sans_llm=True)
    assert not diag.bloquants_pour(section_seule, diag.SCAN)
