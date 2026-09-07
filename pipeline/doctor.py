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

## ⚠ MISE À JOUR lot 36 (2026-09-06) : il RÉPOND, il n'imprime plus seulement

Chaque `_verifier_*` rendait un `bool` et imprimait. Il rend maintenant une
`core.diagnostic.Section` de `Verdict` **et** imprime — l'impression est passée en paramètre
(`ecrire`), le défaut `print` gardant la sortie de `run.py --check` identique octet pour
octet. C'est ce que vérifie `tests/test_core_diagnostic_iso.py`, sur un gabarit gelé.

Ce que la structure permet et que le texte interdisait : la page Diagnostic de l'interface
attache un GESTE à chaque manque, le dépôt guidé sait si `unrar` existe avant de proposer un
import, et le `PLAN-37` pourra faire tourner ce diagnostic en CI sur l'exécutable gelé.
"""
from __future__ import annotations

import shutil as _shutil
from pathlib import Path

from core import cli
from core import diagnostic as diag


#: Sections que `config.yaml` doit porter pour que le pipeline démarre.
SECTIONS_REQUISES = ["llm", "modeles", "temperatures", "decoupage", "langues",
                     "garde_fous", "rendu", "options", "chemins"]


def _verifier_sections_config(config: dict, ecrire=print) -> diag.Section:
    entete = "— Structure de config.yaml —"
    diag.dire(ecrire, entete)
    missing = [k for k in SECTIONS_REQUISES if k not in config]
    if missing:
        return diag.Section(entete, (diag.Verdict(
            "config_sections", diag.LN, diag.BLOQUANT,
            constat=f"section(s) manquante(s) dans config.yaml : {missing}",
            consequence="le pipeline light novel ne peut pas démarrer.",
            geste="rétablis ces sections dans config.yaml — le fichier du dépôt sert de "
                  "référence (git checkout config.yaml).",
            lignes_console=diag.dire(
                ecrire, f"❌ Section(s) manquante(s) dans config.yaml : {missing}")),))
    return diag.Section(entete, (diag.Verdict(
        "config_sections", diag.LN, diag.CONFORME,
        constat="toutes les sections principales de config.yaml sont présentes",
        lignes_console=diag.dire(ecrire, "✓ Toutes les sections principales sont présentes.")),))


def _verifier_chemins(config: dict, pack, ecrire=print) -> diag.Section:
    """`chemins.sources` et le guide de style.

    `prompts` n'est PAS vérifié ici : il vient du pack de langue cible, et `cli.bloc_langue`
    le montre déjà avec le pack qui le sert. Le tester par `chemins.prompts` signalerait une
    absence sur toute installation normale.

    ⚠ Le guide de style se résout par le PACK de langue cible, avec `chemins.style_guide` en
    repli — vérifier la clé de config seule signalerait une absence là où le pack fournit le
    fichier, ce qui est le cas normal depuis la refonte des langues."""
    entete = "\n— Chemins —"
    diag.dire(ecrire, entete)
    verdicts: list[diag.Verdict] = []
    chemins = config.get("chemins", {})
    p = Path(chemins.get("sources", ""))
    if chemins.get("sources") and p.exists():
        verdicts.append(diag.Verdict(
            "chemin_sources", diag.LN, diag.CONFORME, constat=f"sources : {p}",
            lignes_console=diag.dire(ecrire, f"✓ sources : {p}")))
    else:
        verdicts.append(diag.Verdict(
            "chemin_sources", diag.LN, diag.BLOQUANT,
            constat=f"le dossier des sources est introuvable : {p or '(non défini)'}",
            consequence="aucune œuvre ne peut être lue.",
            geste="crée le dossier, ou corrige chemins.sources dans config.yaml.",
            lignes_console=diag.dire(ecrire,
                                     f"❌ sources introuvable : {p or '(non défini)'}")))
    sg = (Path(chemins["style_guide"]) if chemins.get("style_guide")
          else pack.fichier("style_guide.md"))
    if sg and sg.exists():
        verdicts.append(diag.Verdict(
            "style_guide", diag.LN, diag.CONFORME, constat=f"style_guide : {sg}",
            lignes_console=diag.dire(ecrire, f"✓ style_guide : {sg}")))
    else:
        verdicts.append(diag.Verdict(
            "style_guide", diag.LN, diag.BLOQUANT,
            constat=f"le guide de style est introuvable : {sg or '(non défini)'}",
            consequence="les agents traduiraient sans consigne de style.",
            geste="rétablis langues/<code>/style_guide.md, ou pointe chemins.style_guide "
                  "sur un fichier existant.",
            lignes_console=diag.dire(
                ecrire, f"❌ style_guide introuvable : {sg or '(non défini)'}")))
    return diag.Section(entete, tuple(verdicts))


def _verifier_outils_externes(config: dict, ecrire=print) -> diag.Section:
    """Pandoc (BLOQUANT) et le moteur PDF (simple dégradation, donc ⚠ et jamais ❌).

    ⚠ **Bloquant POUR LE LIGHT NOVEL**, et pour lui seul : `brique=diag.LN` porte cette
    portée, et `diagnostic.bloquants_pour("manga")` n'en verra rien. Dire à quelqu'un qui ne
    traduit que des planches que Pandoc le bloque serait faux, et le découragerait pour rien."""
    entete = "\n— Outils externes —"
    diag.dire(ecrire, entete)
    verdicts: list[diag.Verdict] = []
    if _shutil.which("pandoc"):
        verdicts.append(diag.Verdict(
            "pandoc", diag.LN, diag.CONFORME, constat="Pandoc trouvé dans le PATH",
            lignes_console=diag.dire(ecrire, "✓ Pandoc trouvé.")))
    else:
        verdicts.append(diag.Verdict(
            "pandoc", diag.LN, diag.BLOQUANT,
            constat="Pandoc introuvable dans le PATH",
            consequence="les sorties DOCX et EPUB du light novel ne seront pas produites.",
            geste="installe Pandoc — https://pandoc.org/installing.html. ⚠ Angelith "
                  "n'installe aucun logiciel système : c'est à toi de le faire, puis de "
                  "relancer le diagnostic.",
            reparable=False,
            lignes_console=diag.dire(
                ecrire, "❌ Pandoc introuvable — https://pandoc.org/installing.html")))

    rendu = config.get("rendu", {})
    engine = rendu.get("pdf_engine", "weasyprint")
    if "pdf" not in rendu.get("formats", []):
        return diag.Section(entete, tuple(verdicts))
    if engine == "weasyprint":
        try:
            import weasyprint  # noqa: F401
            verdicts.append(diag.Verdict(
                "moteur_pdf", diag.LN, diag.CONFORME, constat="weasyprint installé",
                lignes_console=diag.dire(ecrire, "✓ weasyprint installé.")))
        except Exception as err:                       # noqa: BLE001 — libs système absentes
            verdicts.append(diag.Verdict(
                "moteur_pdf", diag.LN, diag.DEGRADE,
                constat=f"weasyprint n'est pas importable ({type(err).__name__})",
                consequence="le PDF du light novel ne sera pas généré ; DOCX et EPUB, si.",
                geste="pip install weasyprint — ⚠ il demande aussi des bibliothèques "
                      "système (GTK/Pango) qu'Angelith n'installe pas.",
                lignes_console=diag.dire(
                    ecrire, "⚠ weasyprint non importable — le PDF ne sera pas généré "
                            "(`pip install weasyprint`).")))
    elif _shutil.which(engine):
        verdicts.append(diag.Verdict(
            "moteur_pdf", diag.LN, diag.CONFORME,
            constat=f"moteur PDF « {engine} » trouvé dans le PATH",
            lignes_console=diag.dire(ecrire, f"✓ moteur PDF « {engine} » trouvé.")))
    else:
        verdicts.append(diag.Verdict(
            "moteur_pdf", diag.LN, diag.DEGRADE,
            constat=f"le moteur PDF « {engine} » est introuvable dans le PATH",
            consequence="le PDF du light novel ne sera pas généré ; DOCX et EPUB, si.",
            geste=f"installe « {engine} », ou repasse rendu.pdf_engine à weasyprint. "
                  f"⚠ Angelith n'installe aucun logiciel système.",
            lignes_console=diag.dire(
                ecrire, f"⚠ moteur PDF « {engine} » introuvable dans le PATH — le PDF ne "
                        f"sera pas généré.")))
    return diag.Section(entete, tuple(verdicts))


def _verifier_gabarits(config: dict, pack, ecrire=print) -> diag.Section:
    """`reference.docx` et `epub.css`, chacun seulement si son format est demandé.

    Mêmes replis que le rendu réel (cf. `pipeline/render.py`) : le pack d'abord, la config
    ensuite. Tester la clé de config seule signalait une absence sur toute installation
    normale depuis que les gabarits vivent dans le pack.

    ⚠ Cette section n'a **pas** d'en-tête, et n'en a jamais eu : ses lignes se rangent sous
    « — Outils externes — ». Lui en donner un aujourd'hui casserait le contrat scripté."""
    verdicts: list[diag.Verdict] = []
    rendu = config.get("rendu", {})
    formats = rendu.get("formats", [])
    ref = (Path(rendu["reference_docx"]) if rendu.get("reference_docx")
           else pack.fichier("templates/reference.docx"))
    if "docx" in formats:
        if ref.exists():
            verdicts.append(diag.Verdict(
                "reference_docx", diag.LN, diag.CONFORME, constat=f"reference_docx : {ref}",
                lignes_console=diag.dire(ecrire, f"✓ reference_docx : {ref}")))
        else:
            verdicts.append(diag.Verdict(
                "reference_docx", diag.LN, diag.BLOQUANT,
                constat=f"reference.docx introuvable : {ref or '(non défini)'}",
                consequence="le rendu DOCX échouera (le format est demandé par "
                            "rendu.formats).",
                geste="rétablis langues/<code>/templates/reference.docx, ou retire « docx » "
                      "de rendu.formats.",
                lignes_console=diag.dire(
                    ecrire, f"❌ reference_docx introuvable : {ref or '(non défini)'} — "
                            f"le rendu docx échouera.")))
    css = (Path(rendu["epub_css"]) if rendu.get("epub_css")
           else pack.fichier("templates/epub.css"))
    if {"epub", "pdf"} & set(formats):
        if css.exists():
            verdicts.append(diag.Verdict(
                "epub_css", diag.LN, diag.CONFORME, constat=f"epub_css : {css}",
                lignes_console=diag.dire(ecrire, f"✓ epub_css : {css}")))
        else:
            verdicts.append(diag.Verdict(
                "epub_css", diag.LN, diag.BLOQUANT,
                constat=f"epub.css introuvable : {css or '(non défini)'}",
                consequence="les rendus EPUB et PDF échoueront.",
                geste="rétablis langues/<code>/templates/epub.css, ou retire « epub » et "
                      "« pdf » de rendu.formats.",
                lignes_console=diag.dire(
                    ecrire, f"❌ epub_css introuvable : {css or '(non défini)'} — "
                            f"epub/pdf échoueront.")))
    return diag.Section("", tuple(verdicts))


def _signaler_agents_desactives(config: dict, ecrire=print) -> diag.Section:
    """Les agents à `null`. **Information, jamais un défaut** : c'est un réglage voulu."""
    modeles = config.get("modeles", {})
    off = [nom for nom in modeles if modeles.get(nom) is None]
    if not off:
        return diag.Section("", ())
    entete = "\n— Agents désactivés (modeles.<agent>: null) —"
    diag.dire(ecrire, entete)
    return diag.Section(entete, (diag.Verdict(
        "agents_desactives", diag.LN, diag.INFORMATION,
        constat=f"agent(s) désactivé(s) : {', '.join(off)}",
        consequence="ces étapes sont sautées, le texte passe inchangé.",
        geste="c'est un réglage volontaire de config.yaml > modeles — rien à corriger. "
              "Pour le rétablir, redonne un modèle à l'agent.",
        lignes_console=diag.dire(
            ecrire, f"  {', '.join(off)} — étape(s) sautée(s), le texte passe inchangé.")),))


def sections(config: dict, *, ecrire=print, reseau: bool = True) -> tuple[diag.Section, ...]:
    """Le diagnostic light novel, **structuré**, et écrit au fil de l'eau si `ecrire`.

    `reseau=False` saute la section Ollama, qui est le seul appel réseau du lot. C'est ce que
    passe la page Diagnostic quand l'utilisateur lui demande de ne pas sonder le serveur, et
    ce que passent les tests : `pytest -m "not modeles and not lent"` doit tourner **sans
    réseau** (critère 11 du `PLAN-36`).

    ⚠ Une LISTE, et non une chaîne de `and` : le diagnostic doit tout inspecter avant de
    conclure, et `and` court-circuiterait dès la première section en échec — l'utilisateur
    relancerait alors la commande autant de fois qu'il a de problèmes."""
    from core.langues import resoudre_pack
    pack = resoudre_pack(config)
    blocs = [
        _verifier_sections_config(config, ecrire),
        _verifier_chemins(config, pack, ecrire),
        _verifier_outils_externes(config, ecrire),
        _verifier_gabarits(config, pack, ecrire),
        _signaler_agents_desactives(config, ecrire),
    ]
    if reseau:
        blocs.append(cli.section_ollama(config, ecrire=ecrire))
    return tuple(blocs)


def run_doctor(config: dict) -> bool:
    """Diagnostic complet de l'environnement : structure de config.yaml, chemins
    attendus, outils externes (Pandoc, moteur PDF), puis connexion Ollama (réutilise
    `llm.test_connection`). Plus large que --test-llm (qui ne couvre qu'Ollama).
    Affiche un ✓/⚠/❌ par point ; renvoie False si un point BLOQUANT échoue (une simple
    dégradation, comme l'absence de weasyprint, reste un ⚠).

    ⚠ Il ne fait plus qu'une chose : appeler `sections()` avec `ecrire=print`, et conclure.
    Le verdict se lit sur les gravités — `BLOQUANT` fait échouer, `DEGRADE` non — ce qui est
    exactement la règle qu'appliquaient les `bool` d'avant."""
    blocs = sections(config, ecrire=print)
    return cli.conclure(not diag.par_gravite(blocs, diag.BLOQUANT))
