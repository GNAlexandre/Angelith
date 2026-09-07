# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests des helpers de run.py : --all (_run_all_volumes, enchaîne tous les tomes
d'un projet) et --check (_run_doctor, diagnostic complet de l'environnement)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import run as run_mod
from core import cli as cli_mod


def _base_config(tmp_path):
    return {
        "chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path / "build")},
        "options": {},
        "modeles": {"traducteur": "qwen/qwen3.5"},
        "llm": {"base_url": "http://localhost:11434/v1"},
        "langues": {},
    }


def _base_args(**over):
    base = dict(projet="Proj", tome=None, verbose=False, dry_run=True,
               keep_awake=False, shutdown=False, shutdown_delay=120,
               render_only=False, force=False, from_stage=None, chapitre=None)
    base.update(over)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# _run_all_volumes (--all)
# --------------------------------------------------------------------------- #

def test_run_all_volumes_processes_each_volume_in_order(tmp_path, monkeypatch):
    (tmp_path / "sources" / "Proj" / "Vol.1").mkdir(parents=True)
    (tmp_path / "sources" / "Proj" / "Vol.2").mkdir(parents=True)
    calls = []

    def fake_process_volume(projet, tome, config, reporter=None, render_only=False,
                            force=False, restart_from=None, only_chapter=None):
        calls.append(tome)
        return True

    monkeypatch.setattr(run_mod, "process_volume", fake_process_volume)
    run_mod._run_all_volumes(_base_args(), _base_config(tmp_path))
    assert calls == ["Vol.1", "Vol.2"]


def test_run_all_volumes_stops_series_when_a_volume_is_interrupted(tmp_path, monkeypatch):
    (tmp_path / "sources" / "Proj" / "Vol.1").mkdir(parents=True)
    (tmp_path / "sources" / "Proj" / "Vol.2").mkdir(parents=True)
    calls = []

    def fake_process_volume(projet, tome, config, reporter=None, render_only=False,
                            force=False, restart_from=None, only_chapter=None):
        calls.append(tome)
        return False   # arrêté (Ctrl+C / --stop) sur ce tome

    monkeypatch.setattr(run_mod, "process_volume", fake_process_volume)
    run_mod._run_all_volumes(_base_args(), _base_config(tmp_path))
    # Vol.2 ne doit JAMAIS être touché : la série s'arrête au tome interrompu.
    assert calls == ["Vol.1"]


def test_run_all_volumes_passes_shared_flags_to_every_volume(tmp_path, monkeypatch):
    (tmp_path / "sources" / "Proj" / "Vol.1").mkdir(parents=True)
    (tmp_path / "sources" / "Proj" / "Vol.2").mkdir(parents=True)
    seen = []

    def fake_process_volume(projet, tome, config, reporter=None, render_only=False,
                            force=False, restart_from=None, only_chapter=None):
        seen.append((tome, force, restart_from, only_chapter))
        return True

    monkeypatch.setattr(run_mod, "process_volume", fake_process_volume)
    run_mod._run_all_volumes(_base_args(force=True, from_stage="correction", chapitre=3),
                             _base_config(tmp_path))
    assert seen == [("Vol.1", True, "correction", 3), ("Vol.2", True, "correction", 3)]


def test_run_all_volumes_no_volumes_exits_nonzero(tmp_path, monkeypatch):
    (tmp_path / "sources" / "Proj").mkdir(parents=True)   # projet vide, aucun tome
    with pytest.raises(SystemExit) as exc:
        run_mod._run_all_volumes(_base_args(), _base_config(tmp_path))
    assert exc.value.code != 0


def test_run_all_volumes_propagates_exception_after_cleanup(tmp_path, monkeypatch):
    (tmp_path / "sources" / "Proj" / "Vol.1").mkdir(parents=True)
    unloaded = []

    def fake_process_volume(*a, **kw):
        raise RuntimeError("modèle introuvable")

    monkeypatch.setattr(run_mod, "process_volume", fake_process_volume)
    monkeypatch.setattr(cli_mod, "unload_models", lambda config, models, base_url=None: unloaded.append(True))
    monkeypatch.setattr(run_mod, "_finalize_power", lambda args, inhibitor, interrupted: None)
    monkeypatch.setattr("pipeline.power.ollama_load", lambda base_url, model, timeout=120: True)
    with pytest.raises(RuntimeError, match="modèle introuvable"):
        run_mod._run_all_volumes(_base_args(dry_run=False), _base_config(tmp_path))
    assert unloaded == [True]   # le nettoyage a bien lieu MALGRÉ l'exception


def test_run_all_volumes_cleanup_runs_on_keyboardinterrupt(tmp_path, monkeypatch):
    """Régression du bug de perf : un Ctrl+C (KeyboardInterrupt) DOIT quand même
    déclencher le déchargement du modèle — sinon il reste résident en VRAM et le débit
    GPU chute au run suivant. Le déchargement passe par le `finally` unique."""
    (tmp_path / "sources" / "Proj" / "Vol.1").mkdir(parents=True)
    unloaded, finalized = [], []

    def fake_process_volume(*a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_mod, "process_volume", fake_process_volume)
    monkeypatch.setattr(cli_mod, "unload_models", lambda config, models, base_url=None: unloaded.append(True))
    monkeypatch.setattr(run_mod, "_finalize_power",
                        lambda args, inhibitor, interrupted: finalized.append(interrupted))
    monkeypatch.setattr("pipeline.power.ollama_load", lambda base_url, model, timeout=120: True)
    # KeyboardInterrupt est rattrapé dans _run_all_volumes → pas de propagation.
    run_mod._run_all_volumes(_base_args(dry_run=False), _base_config(tmp_path))
    assert unloaded == [True]       # modèle déchargé malgré le Ctrl+C
    assert finalized == [True]      # interrupted=True → pas d'extinction programmée


def test_shielded_unload_ignores_sigint_during_unload_and_restores_handler(monkeypatch):
    """Le déchargement doit tourner avec SIGINT neutralisé (un Ctrl+C tardif ne peut plus
    le sauter) PUIS restaurer le handler précédent."""
    import signal
    sentinel = lambda *a: None
    signal.signal(signal.SIGINT, sentinel)
    try:
        seen = {}
        monkeypatch.setattr(cli_mod, "unload_models",
                            lambda config, models, base_url=None: seen.setdefault("during", signal.getsignal(signal.SIGINT)))
        run_mod._shielded_unload({"options": {}}, ["m"])
        assert seen["during"] is signal.SIG_IGN             # ignoré PENDANT le déchargement
        assert signal.getsignal(signal.SIGINT) is sentinel  # handler restauré APRÈS
    finally:
        signal.signal(signal.SIGINT, signal.SIG_DFL)


# --------------------------------------------------------------------------- #
# _finalize_power : annulation d'extinction par UN SEUL Ctrl+C
# --------------------------------------------------------------------------- #

def _shutdown_args(**over):
    a = dict(keep_awake=False, shutdown=True, shutdown_delay=15)
    a.update(over)
    return SimpleNamespace(**a)


def test_finalize_power_single_ctrlc_cancels_shutdown_and_restores_handler(monkeypatch):
    """Un SEUL Ctrl+C pendant l'attente doit annuler l'extinction (plus besoin de 2), et le
    handler SIGINT précédent doit être restauré après."""
    import signal
    calls = {"shutdown": 0, "cancel": 0}
    monkeypatch.setattr("pipeline.power.shutdown", lambda delay: (calls.__setitem__("shutdown", calls["shutdown"] + 1), "shutdown /a")[1])
    monkeypatch.setattr("pipeline.power.cancel_shutdown", lambda: (calls.__setitem__("cancel", calls["cancel"] + 1), "shutdown /a")[1])
    monkeypatch.setattr("pipeline.power.release", lambda: None)
    monkeypatch.setattr("pipeline.power.stop_inhibitor", lambda inh: None)
    # simule UN Ctrl+C : le sleep de la fenêtre d'attente lève KeyboardInterrupt une fois
    monkeypatch.setattr("time.sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))

    sentinel = lambda *a: None
    signal.signal(signal.SIGINT, sentinel)
    try:
        run_mod._finalize_power(_shutdown_args(), None, interrupted=False)
        assert calls == {"shutdown": 1, "cancel": 1}           # extinction programmée puis annulée
        assert signal.getsignal(signal.SIGINT) is sentinel      # handler restauré
    finally:
        signal.signal(signal.SIGINT, signal.SIG_DFL)


def test_finalize_power_no_shutdown_when_interrupted(monkeypatch):
    """Sur arrêt (Ctrl+C du run), aucune extinction n'est programmée."""
    calls = {"shutdown": 0}
    monkeypatch.setattr("pipeline.power.shutdown", lambda delay: (calls.__setitem__("shutdown", calls["shutdown"] + 1), "shutdown /a")[1])
    monkeypatch.setattr("pipeline.power.release", lambda: None)
    monkeypatch.setattr("pipeline.power.stop_inhibitor", lambda inh: None)
    monkeypatch.setattr("time.sleep", lambda s: (_ for _ in ()).throw(AssertionError("ne doit pas attendre")))
    run_mod._finalize_power(_shutdown_args(), None, interrupted=True)
    assert calls["shutdown"] == 0


# --------------------------------------------------------------------------- #
# _run_doctor (--check)
# --------------------------------------------------------------------------- #

def _full_config(tmp_path):
    (tmp_path / "sources").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "style_guide.md").write_text("x", encoding="utf-8")
    (tmp_path / "reference.docx").write_text("x", encoding="utf-8")
    (tmp_path / "epub.css").write_text("x", encoding="utf-8")
    return {
        "llm": {"base_url": "http://localhost:11434/v1", "api_key": "ollama"},
        "modeles": {"traducteur": "qwen/qwen3.5"},
        "temperatures": {},
        "decoupage": {},
        "langues": {},
        "garde_fous": {},
        "rendu": {"formats": ["docx", "epub", "pdf"], "pdf_engine": "weasyprint",
                  "reference_docx": str(tmp_path / "reference.docx"),
                  "epub_css": str(tmp_path / "epub.css")},
        "options": {},
        "chemins": {"sources": str(tmp_path / "sources"), "prompts": str(tmp_path / "prompts"),
                    "style_guide": str(tmp_path / "style_guide.md")},
    }


def test_run_doctor_reports_missing_config_sections(monkeypatch, capsys):
    monkeypatch.setattr("pipeline.llm.test_connection", lambda config, ecrire=print: True)
    ok = run_mod._run_doctor({"llm": {}, "modeles": {}, "chemins": {}, "rendu": {}})
    out = capsys.readouterr().out
    assert ok is False
    assert "manquante" in out


def test_run_doctor_reports_missing_paths(tmp_path, monkeypatch, capsys):
    cfg = _full_config(tmp_path)
    cfg["chemins"]["sources"] = str(tmp_path / "nexiste_pas")
    monkeypatch.setattr("pipeline.llm.test_connection", lambda config, ecrire=print: True)
    ok = run_mod._run_doctor(cfg)
    assert ok is False
    assert "sources introuvable" in capsys.readouterr().out


def test_run_doctor_all_ok_when_everything_present_and_ollama_reachable(tmp_path, monkeypatch):
    cfg = _full_config(tmp_path)
    monkeypatch.setattr("pipeline.llm.test_connection", lambda config, ecrire=print: True)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name)
    ok = run_mod._run_doctor(cfg)
    assert ok is True


def test_run_doctor_false_when_ollama_unreachable(tmp_path, monkeypatch):
    cfg = _full_config(tmp_path)
    monkeypatch.setattr("pipeline.llm.test_connection", lambda config, ecrire=print: False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name)
    ok = run_mod._run_doctor(cfg)
    assert ok is False


def test_run_doctor_missing_reference_docx_is_blocking_when_docx_in_formats(tmp_path, monkeypatch):
    cfg = _full_config(tmp_path)
    cfg["rendu"]["reference_docx"] = str(tmp_path / "nexiste_pas.docx")
    monkeypatch.setattr("pipeline.llm.test_connection", lambda config, ecrire=print: True)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name)
    ok = run_mod._run_doctor(cfg)
    assert ok is False


def test_run_doctor_missing_weasyprint_is_only_a_warning_not_blocking(tmp_path, monkeypatch):
    cfg = _full_config(tmp_path)
    monkeypatch.setattr("pipeline.llm.test_connection", lambda config, ecrire=print: True)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name if name == "pandoc" else None)
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **kw):
        if name == "weasyprint":
            raise ImportError("no weasyprint")
        return real_import(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    ok = run_mod._run_doctor(cfg)
    assert ok is True   # weasyprint manquant = avertissement, pas bloquant


# --------------------------------------------------------------------------- #
#  Demarrage : ce que `run.py` a le droit d'importer
# --------------------------------------------------------------------------- #

def _sonde(argv: list[str]) -> str:
    """Lance `run.py` dans un SOUS-PROCESSUS et dit si `openai` a ete importe.

    ⚠ Un simple `"openai" in sys.modules` ici serait faux : ce fichier importe deja `run`, et
    d'autres tests de la suite importent `openai` pour leur propre compte. Seul un processus
    neuf repond a la question posee. C'est aussi pourquoi on ne mesure pas une DUREE : sur une
    machine chargee elle est du bruit (le `python -c pass` de reference a ete chronometre a
    4,8 s), alors que la presence d'un module est binaire et ne ment pas.
    """
    import subprocess
    import sys as _sys
    code = (
        "import sys, runpy\n"
        f"sys.argv = {argv!r}\n"
        "try:\n"
        "    runpy.run_path('run.py', run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "sys.stderr.write('OPENAI' if 'openai' in sys.modules else 'PROPRE')\n"
    )
    res = subprocess.run([_sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(Path(__file__).resolve().parent.parent), timeout=300)
    return res.stderr[-6:]


def test_version_n_importe_pas_le_sdk_openai():
    """`from pipeline.orchestrator import …` en tete du module coutait **5,18 s** d'import
    `openai` (mesure au `python -X importtime`) a CHAQUE invocation — y compris `--version`,
    `--list`, `--check` et surtout `--stop`, qu'on lance dans un second terminal precisement
    pour arreter vite. `run_manga.py` importe son orchestrateur dans la branche qui s'en sert ;
    `run.py` etait le seul a ne pas suivre ce motif."""
    assert _sonde(["run.py", "--version"]) == "PROPRE"


def test_list_n_importe_pas_le_sdk_openai():
    assert _sonde(["run.py", "--list"]) == "PROPRE"
