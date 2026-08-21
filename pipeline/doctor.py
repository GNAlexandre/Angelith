# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Diagnostic de l'environnement du pipeline light novel (`run.py --check`, `app.py`).

Extrait de `run.py` au lot 2.6 pour qu'`app.py` cesse d'importer une CLI. L'inversion de
couche était réelle : la TUI dépendait d'une CLI concurrente, si bien qu'on ne pouvait pas
toucher à `run.py` sans risquer de casser `app.py`.

Ce diagnostic **n'est pas** allé dans `core/cli.py` : sections de `config.yaml`, chemins,
Pandoc, moteur PDF, `reference.docx`, `epub.css` — tout ici est propre à la brique light
novel. Le mettre dans le socle y aurait fait entrer la connaissance d'une brique, exactement
ce que le lot 2 défait. Seules les sections réellement communes (Ollama, dépendances Python,
ligne de conclusion) vivent dans `core/cli.py`, et les deux doctors s'en servent.
"""
from __future__ import annotations

import shutil as _shutil
from pathlib import Path

from core import cli


def run_doctor(config: dict) -> bool:
    """Diagnostic complet de l'environnement : structure de config.yaml, chemins
    attendus, outils externes (Pandoc, moteur PDF), puis connexion Ollama (réutilise
    `llm.test_connection`). Plus large que --test-llm (qui ne couvre qu'Ollama).
    Affiche un ✓/⚠/❌ par point ; renvoie False si un point BLOQUANT échoue (une simple
    dégradation, comme l'absence de weasyprint, reste un ⚠)."""
    ok = True

    print("— Structure de config.yaml —")
    required = ["llm", "modeles", "temperatures", "decoupage", "langues",
               "garde_fous", "rendu", "options", "chemins"]
    missing = [k for k in required if k not in config]
    if missing:
        print(f"❌ Section(s) manquante(s) dans config.yaml : {missing}")
        ok = False
    else:
        print("✓ Toutes les sections principales sont présentes.")

    print("\n— Chemins —")
    chemins = config.get("chemins", {})
    for key in ("sources", "prompts"):
        p = Path(chemins.get(key, ""))
        if chemins.get(key) and p.exists():
            print(f"✓ {key} : {p}")
        else:
            print(f"❌ {key} introuvable : {p or '(non défini)'}")
            ok = False
    sg = Path(chemins.get("style_guide", ""))
    if chemins.get("style_guide") and sg.exists():
        print(f"✓ style_guide : {sg}")
    else:
        print(f"❌ style_guide introuvable : {sg or '(non défini)'}")
        ok = False

    print("\n— Outils externes —")
    if _shutil.which("pandoc"):
        print("✓ Pandoc trouvé.")
    else:
        print("❌ Pandoc introuvable — https://pandoc.org/installing.html")
        ok = False

    rendu = config.get("rendu", {})
    formats = rendu.get("formats", [])
    engine = rendu.get("pdf_engine", "weasyprint")
    if "pdf" in formats:
        if engine == "weasyprint":
            try:
                import weasyprint  # noqa: F401
                print("✓ weasyprint installé.")
            except Exception:
                print("⚠ weasyprint non importable — le PDF ne sera pas généré (`pip install weasyprint`).")
        elif _shutil.which(engine):
            print(f"✓ moteur PDF « {engine} » trouvé.")
        else:
            print(f"⚠ moteur PDF « {engine} » introuvable dans le PATH — le PDF ne sera pas généré.")

    ref = Path(rendu.get("reference_docx", ""))
    if "docx" in formats:
        if ref.exists():
            print(f"✓ reference_docx : {ref}")
        else:
            print(f"❌ reference_docx introuvable : {ref or '(non défini)'} — le rendu docx échouera.")
            ok = False
    css = Path(rendu.get("epub_css", ""))
    if {"epub", "pdf"} & set(formats):
        if css.exists():
            print(f"✓ epub_css : {css}")
        else:
            print(f"❌ epub_css introuvable : {css or '(non défini)'} — epub/pdf échoueront.")
            ok = False

    modeles = config.get("modeles", {})
    off = [nom for nom in modeles if modeles.get(nom) is None]
    if off:
        print("\n— Agents désactivés (modeles.<agent>: null) —")
        print(f"  {', '.join(off)} — étape(s) sautée(s), le texte passe inchangé.")

    if not cli.section_ollama(config):
        ok = False
    return cli.conclure(ok)
