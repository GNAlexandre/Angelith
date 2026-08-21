# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Fragments de CLI partagés (`core/cli.py`, lot 2.6) et sens des dépendances.

Le cycle de vie « veille / préchargement / extinction » est déjà couvert par
`tests/test_run_cli.py`, qui l'exerce via `run.py`. Ici : ce que le déplacement a rendu
possible (`app.py` et `run_manga.py` s'en servent aussi), les points où les deux briques
diffèrent, et le sens des dépendances — qui est la raison d'être du lot.
"""
from __future__ import annotations

import ast
from pathlib import Path

from core import cli

RACINE = Path(__file__).resolve().parents[1]


# --- sens des dépendances --------------------------------------------------------

def test_app_nimporte_plus_run():
    """LE point du lot : `app.py` importait `_finalize_power`/`_run_doctor`/
    `_models_in_config` depuis `run.py`. Inversion de couche — la TUI dépendait d'une CLI
    concurrente, si bien qu'on ne pouvait pas toucher à `run.py` sans risquer de casser
    `app.py`."""
    arbre = ast.parse((RACINE / "app.py").read_text(encoding="utf-8"))
    fautifs = []
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "run":
            fautifs.append(f"ligne {n.lineno} : from {n.module} import …")
        if isinstance(n, ast.Import):
            fautifs += [f"ligne {n.lineno} : import {a.name}"
                        for a in n.names if a.name.split(".")[0] == "run"]
    assert not fautifs, "app.py importe encore une CLI :\n" + "\n".join(fautifs)


def test_le_socle_nimporte_ni_les_briques_ni_les_cli():
    """Complète `tests/test_core_alias.py` : `core/cli.py` est le module le plus exposé à la
    tentation d'aller chercher `pipeline.sources` ou `run` pour « faire simple »."""
    fautifs = []
    for f in sorted((RACINE / "core").glob("*.py")):
        for i, ligne in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            nu = ligne.strip()
            for interdit in ("pipeline", "manga", "run", "run_manga", "app"):
                if nu.startswith((f"import {interdit}", f"from {interdit} import",
                                  f"from {interdit}.")):
                    fautifs.append(f"{f.name}:{i}: {nu}")
    assert not fautifs, "le socle dépend d'une couche supérieure :\n" + "\n".join(fautifs)


def _litteraux_de_code(chemin: Path) -> set[str]:
    """Chaînes littérales et identifiants d'un module, **docstrings exclues**.

    Le contrôle porte sur le CODE : les docstrings du socle citent volontiers
    `reference_docx` ou `pandoc` comme contre-exemples de ce qui ne doit PAS y entrer — un
    simple `not in texte` se déclencherait sur l'avertissement lui-même."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    docstrings = set()
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            corps = getattr(n, "body", [])
            if (corps and isinstance(corps[0], ast.Expr)
                    and isinstance(corps[0].value, ast.Constant)
                    and isinstance(corps[0].value.value, str)):
                docstrings.add(id(corps[0].value))
    out: set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            out.add(n.value)
        elif isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def test_le_doctor_light_novel_nest_pas_dans_le_socle():
    """Il diagnostique des sections de `config.yaml`, Pandoc, `reference.docx` : tout est
    propre à la brique. Le mettre dans `core/` y ferait entrer la connaissance d'une brique,
    exactement ce que le lot 2 défait. Il vit donc dans `pipeline/doctor.py`."""
    assert (RACINE / "pipeline" / "doctor.py").exists()
    socle: set[str] = set()
    for f in (RACINE / "core").glob("*.py"):
        socle |= _litteraux_de_code(f)
    # Marqueurs de la CONFIG DE RENDU light novel. Pas « pandoc » : `core/glossary_import.py`
    # l'appelle légitimement pour convertir un glossaire `.docx` en texte, et le glossaire est
    # partagé par les deux briques (c'est tout l'objet du lot 3). Un outil n'est pas un
    # marqueur de brique ; une clé de config de rendu, si.
    for marqueur in ("reference_docx", "epub_css", "pdf_engine", "style_guide", "weasyprint"):
        assert marqueur not in socle, f"« {marqueur} » a fui dans le socle"


# --- afficher_liste --------------------------------------------------------------

def _arbo(tmp_path, tomes, generes=(), sous_dossier=""):
    src, build = tmp_path / "sources", tmp_path / "build"
    for t in tomes:
        (src / "Proj" / t).mkdir(parents=True)
    for t in generes:
        cible = build / "Proj" / t
        (cible / sous_dossier if sous_dossier else cible).mkdir(parents=True)
    return src, build


def _listeurs():
    return (lambda s: sorted(p.name for p in s.iterdir()) if s.exists() else [],
            lambda s, p: sorted(x.name for x in (s / p).iterdir()) if (s / p).exists() else [])


def test_liste_des_tomes_marque_ceux_deja_generes(tmp_path, capsys):
    src, build = _arbo(tmp_path, ["Vol.1", "Vol.2"], generes=["Vol.1"])
    lp, lt = _listeurs()
    cli.afficher_liste(lp, lt, src, build, "Proj")
    out = capsys.readouterr().out
    assert "✓ Vol.1" in out and "(déjà généré)" in out
    assert "Vol.2" in out and out.count("(déjà généré)") == 1


def test_le_sous_dossier_manga_decide_si_un_tome_est_genere(tmp_path, capsys):
    """Côté manga les sorties vivent sous `build/<projet>/<tome>/manga/` : sans ce suffixe,
    un tome dont seul le build LN existe serait annoncé « déjà généré »."""
    src, build = _arbo(tmp_path, ["Vol.1"], generes=["Vol.1"])   # build LN seulement
    lp, lt = _listeurs()
    cli.afficher_liste(lp, lt, src, build, "Proj", sous_dossier="manga")
    assert "(déjà généré)" not in capsys.readouterr().out
    (build / "Proj" / "Vol.1" / "manga").mkdir()
    cli.afficher_liste(lp, lt, src, build, "Proj", sous_dossier="manga")
    assert "(déjà généré)" in capsys.readouterr().out


def test_un_projet_sans_tome_le_dit(tmp_path, capsys):
    src, build = _arbo(tmp_path, [])
    (src / "Proj").mkdir(parents=True)
    lp, lt = _listeurs()
    cli.afficher_liste(lp, lt, src, build, "Proj")
    assert "Aucun tome trouvé" in capsys.readouterr().out


def test_sans_projet_on_liste_les_projets_avec_leur_nombre_de_tomes(tmp_path, capsys):
    src, build = _arbo(tmp_path, ["Vol.1", "Vol.2"])
    lp, lt = _listeurs()
    cli.afficher_liste(lp, lt, src, build, None)
    assert "Proj  (2 tome(s))" in capsys.readouterr().out


# --- models_in_config ------------------------------------------------------------

def test_les_modeles_sont_dedoublonnes_et_les_specs_dict_lues():
    config = {"modeles": {"a": "m1", "b": {"model": "m1"}, "c": "m2", "d": None}}
    assert cli.models_in_config(config) == ["m1", "m2"]


def test_les_modeles_dune_section_sont_lus_separement():
    """C'est ce qui permet à `run_manga.py` de précharger/décharger SON modèle : lire la
    racine lui ferait charger les modèles du light novel."""
    config = {"modeles": {"traducteur": "ln"}, "manga": {"modeles": {"manga_traducteur": "mg"}}}
    assert cli.models_in_config(config, "manga") == ["mg"]
    assert cli.models_in_config(config) == ["ln"]


def test_une_section_absente_ne_leve_pas():
    assert cli.models_in_config({"modeles": {"a": "m"}}, "manga") == []


# --- déchargement ----------------------------------------------------------------

def test_le_dechargement_est_saute_en_dry_run(monkeypatch):
    appels = []
    monkeypatch.setattr("core.power.ollama_unload", lambda base, m: appels.append(m))
    cli.unload_models({"options": {"dry_run": True}, "llm": {"base_url": "x"}}, ["m"])
    assert appels == []
    cli.unload_models({"options": {}, "llm": {"base_url": "x"}}, ["m"])
    assert appels == ["m"]


def test_le_base_url_de_la_brique_est_respecte(monkeypatch):
    """La brique manga peut viser un autre serveur : décharger sur celui du LN ne libérerait
    rien, et laisserait le modèle résident en VRAM."""
    vus = []
    monkeypatch.setattr("core.power.ollama_unload", lambda base, m: vus.append(base))
    cli.unload_models({"options": {}, "llm": {"base_url": "racine"}}, ["m"],
                      base_url="brique")
    assert vus == ["brique"]


def test_le_prechargement_est_saute_en_dry_run(monkeypatch):
    appels = []
    monkeypatch.setattr("core.power.ollama_load", lambda base, m: appels.append(m))
    cli.precharger_modeles({"llm": {"base_url": "x"}}, ["m"], dry_run=True)
    assert appels == []
    cli.precharger_modeles({"llm": {"base_url": "x"}}, ["m"], dry_run=False)
    assert appels == ["m"]


def test_preparer_veille_ne_fait_rien_si_inactif(monkeypatch):
    monkeypatch.setattr("core.power.keep_awake",
                        lambda: (_ for _ in ()).throw(AssertionError("ne doit pas être appelé")))
    assert cli.preparer_veille(False, "message") is None


# --- les deux CLI ----------------------------------------------------------------

def test_les_deux_cli_ont_les_flags_de_veille():
    """`--keep-awake`/`--shutdown` manquaient côté manga, et y sont plus utiles encore : un
    tome de 150 planches avec raisonnement activé dépasse les deux heures."""
    import argparse
    for source in ("run.py", "run_manga.py"):
        src = (RACINE / source).read_text(encoding="utf-8")
        assert "cli.ajouter_flags_veille(ap)" in src, source
    ap = argparse.ArgumentParser()
    cli.ajouter_flags_veille(ap)
    args = ap.parse_args(["--keep-awake", "--shutdown", "--shutdown-delay", "30"])
    assert (args.keep_awake, args.shutdown, args.shutdown_delay) == (True, True, 30)


def test_from_rendu_ne_precharge_aucun_modele(tmp_path, monkeypatch):
    """`--from rendu` ne relettre que depuis les traductions déjà en cache. Précharger y
    ferait monter un modèle de 27 B en VRAM pour rien, et le déchargement final évincerait un
    modèle que l'utilisateur avait peut-être chargé pour autre chose. Même raisonnement que
    le chargement paresseux du détecteur ONNX (lot 1) — et le préchargement manga, ajouté au
    lot 2.6, l'aurait annulé sur exactement la commande de vérification de ce lot-là."""
    import sys

    import run_manga

    charges, decharges = [], []
    monkeypatch.setattr("core.power.ollama_load", lambda base, m: charges.append(m))
    monkeypatch.setattr("core.power.ollama_unload", lambda base, m: decharges.append(m))
    monkeypatch.setattr("manga.orchestrator_manga.process_volume",
                        lambda *a, **k: True)
    (tmp_path / "sources" / "Proj" / "Vol.1" / "manga").mkdir(parents=True)
    cfg = str(tmp_path / "c.yaml")
    (tmp_path / "c.yaml").write_text(
        "llm: {base_url: 'http://x', api_key: k}\n"
        "modeles: {}\ntemperatures: {}\noptions: {}\n"
        f"chemins: {{sources: '{(tmp_path / 'sources').as_posix()}', "
        f"build: '{(tmp_path / 'build').as_posix()}', prompts: prompts}}\n"
        "manga:\n  modeles: {manga_traducteur: 'qwen3.6:27b'}\n"
        "  temperatures: {manga_traducteur: 0.3}\n  detection: {model_path: absent.onnx}\n",
        encoding="utf-8")

    def _lancer(*flags):
        charges.clear(); decharges.clear()
        monkeypatch.setattr(sys, "argv", ["run_manga.py", "Proj", "Vol.1", "--config", cfg,
                                          *flags])
        try:
            run_manga.main()
        except SystemExit:
            pass

    _lancer("--from", "rendu")
    assert charges == [] and decharges == []
    _lancer("--from", "traduction")
    assert charges == ["qwen3.6:27b"] and decharges == ["qwen3.6:27b"]


def test_les_deux_cli_configurent_stdout_avant_tout_import_lourd():
    """L'ordre compte : `configurer_stdout()` doit tourner AVANT les imports qui peuvent
    afficher un avertissement (transformers en émet un). Sinon la console Windows en cp1252
    lève `UnicodeEncodeError` avant même d'avoir commencé."""
    for source in ("run.py", "run_manga.py", "app.py"):
        lignes = (RACINE / source).read_text(encoding="utf-8").splitlines()
        i_appel = next(i for i, l in enumerate(lignes) if l.strip() == "cli.configurer_stdout()")
        lourds = [i for i, l in enumerate(lignes)
                  if l.startswith(("from pipeline", "from manga", "from rich"))]
        assert all(i > i_appel for i in lourds), source


# --------------------------------------------------------------------------- #
#  make_reporter : le fichier n'est plus conditionné à --verbose
# --------------------------------------------------------------------------- #

def test_le_perf_log_est_ouvert_meme_sans_verbose(tmp_path):
    """LE correctif d'observabilité : un run de nuit lancé sans `--verbose` ne laissait
    aucune trace fichier, alors que `warn()` y écrivait déjà."""
    from core.cli import make_reporter
    from core.reporter import Reporter

    r = make_reporter(Reporter(), tmp_path / "b", verbose=False, dry_run=False)
    r.warn("planche 87 en échec")
    r.close()

    log = tmp_path / "b" / "perf.log"
    assert log.exists()
    assert "planche 87 en échec" in log.read_text(encoding="utf-8")


def test_sans_verbose_la_console_reste_muette_sur_la_perf(tmp_path, capsys):
    from core.cli import make_reporter
    from core.reporter import Reporter

    r = make_reporter(Reporter(), tmp_path / "b", verbose=False, dry_run=False)
    r.verbose("detection 1.20s")
    r.close()

    assert "detection 1.20s" not in capsys.readouterr().out
    assert "detection 1.20s" in (tmp_path / "b" / "perf.log").read_text(encoding="utf-8")


def test_le_dry_run_n_ecrit_toujours_aucun_fichier(tmp_path):
    """Un dry-run ne doit rien laisser derrière lui — y compris pas de dossier de build créé
    juste pour un journal."""
    from core.cli import make_reporter
    from core.reporter import Reporter

    make_reporter(Reporter(), tmp_path / "b", verbose=True, dry_run=True)
    assert not (tmp_path / "b").exists()
