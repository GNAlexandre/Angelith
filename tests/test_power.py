# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de power.py : anti-veille (keep_awake/release), extinction programmée
(shutdown/cancel_shutdown), inhibiteurs macOS/Linux, et préchargement/déchargement
Ollama (ollama_load/ollama_unload). Toutes les frontières externes (ctypes, subprocess,
openai, urllib) sont mockées — aucun test ne touche réellement l'OS ou le réseau."""
import json
from types import SimpleNamespace

import pytest

from pipeline import power


@pytest.fixture(autouse=True)
def _release_keepawake_after_each_test():
    """keep_awake() démarre un thread de fond réel — on le referme systématiquement,
    même si le test a échoué avant d'appeler release() lui-même."""
    yield
    power.release()


# --------------------------------------------------------------------------- #
# ollama_load / ollama_unload
# --------------------------------------------------------------------------- #

def test_ollama_load_success(monkeypatch):
    calls = {}

    class _FakeCompletions:
        def create(self, **kw):
            calls.update(kw)
            return object()

    class _FakeClient:
        chat = type("Chat", (), {"completions": _FakeCompletions()})()

        def __init__(self, **kw):
            calls["client_kwargs"] = kw

    monkeypatch.setattr("openai.OpenAI", _FakeClient)
    assert power.ollama_load("http://localhost:11434/v1", "qwen") is True
    assert calls["model"] == "qwen"


def test_ollama_load_failure_returns_false_and_prints(monkeypatch, capsys):
    def _boom(**kw):
        raise RuntimeError("serveur down")

    monkeypatch.setattr("openai.OpenAI", _boom)
    assert power.ollama_load("http://localhost:11434/v1", "qwen") is False
    assert "préchargement" in capsys.readouterr().out


def test_ollama_unload_strips_v1_suffix_and_posts_keep_alive_zero(monkeypatch):
    captured = {}

    class _Resp:
        def read(self):
            return b"{}"

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    ok = power.ollama_unload("http://localhost:11434/v1", "qwen")
    assert ok is True
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert json.loads(captured["data"]) == {"model": "qwen", "keep_alive": 0}


def test_ollama_unload_failure_returns_false_and_prints(monkeypatch, capsys):
    def _boom(req, timeout=None):
        raise RuntimeError("injoignable")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    assert power.ollama_unload("http://localhost:11434/v1", "qwen") is False
    assert "déchargement" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# keep_awake / release (Windows : SetThreadExecutionState)
# --------------------------------------------------------------------------- #

def _faux_windll(monkeypatch, set_thread_execution_state):
    """Installe un `ctypes.windll` factice, sur Windows COMME sur Linux.

    ⚠ Ces tests écrivaient `monkeypatch.setattr("ctypes.windll.kernel32.…")`. La forme
    pointée impose à monkeypatch de RÉSOUDRE `ctypes.windll` avant de patcher — un attribut
    qui n'existe que sur Windows. Sur le runner Linux de la matrice, les trois tests ne
    tombaient donc pas sur ce qu'ils mesurent (`keep_awake` sous Windows simulé) mais sur un
    `ModuleNotFoundError: No module named 'ctypes.windll'` levé par l'outillage de test.
    On pose l'objet nous-mêmes — `raising=False` parce que hors Windows il n'y a rien à
    remplacer — ce qui teste la MÊME chose sur les deux OS."""
    import ctypes
    kernel32 = SimpleNamespace(SetThreadExecutionState=set_thread_execution_state)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False)


def test_keep_awake_windows_sets_display_required_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(power, "_IS_WIN", True)
    _faux_windll(monkeypatch, lambda flags: calls.append(flags) or 1)
    assert power.keep_awake() is True
    assert calls and calls[0] & power._ES_DISPLAY_REQUIRED
    assert calls[0] & power._ES_SYSTEM_REQUIRED


def test_keep_awake_returns_false_when_set_thread_execution_state_fails(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", True)
    _faux_windll(monkeypatch, lambda flags: 0)
    assert power.keep_awake() is False


def test_keep_awake_returns_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", False)
    assert power.keep_awake() is False


def test_release_restores_continuous_flag_and_stops_thread(monkeypatch):
    calls = []
    monkeypatch.setattr(power, "_IS_WIN", True)
    _faux_windll(monkeypatch, lambda flags: calls.append(flags) or 1)
    power.keep_awake()
    calls.clear()
    power.release()
    assert calls == [power._ES_CONTINUOUS]
    assert power._keepawake_thread is None


def test_release_without_prior_keep_awake_is_noop():
    power.release()   # ne doit pas lever, même sans keep_awake() préalable


# --------------------------------------------------------------------------- #
# start_inhibitor / stop_inhibitor (macOS/Linux)
# --------------------------------------------------------------------------- #

def test_start_inhibitor_returns_none_on_windows(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", True)
    monkeypatch.setattr(power, "_IS_MAC", False)
    assert power.start_inhibitor() is None


def test_start_inhibitor_uses_caffeinate_on_mac(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", False)
    monkeypatch.setattr(power, "_IS_MAC", True)
    calls = []
    monkeypatch.setattr(power.subprocess, "Popen", lambda cmd: calls.append(cmd) or object())
    power.start_inhibitor()
    assert calls == [["caffeinate", "-s"]]


def test_start_inhibitor_uses_systemd_inhibit_on_linux(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", False)
    monkeypatch.setattr(power, "_IS_MAC", False)
    calls = []
    monkeypatch.setattr(power.subprocess, "Popen", lambda cmd: calls.append(cmd) or object())
    power.start_inhibitor()
    assert calls[0][0] == "systemd-inhibit"


def test_start_inhibitor_returns_none_on_popen_failure(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", False)
    monkeypatch.setattr(power, "_IS_MAC", True)

    def _boom(cmd):
        raise OSError("caffeinate introuvable")

    monkeypatch.setattr(power.subprocess, "Popen", _boom)
    assert power.start_inhibitor() is None


def test_stop_inhibitor_terminates_process():
    class _FakeProc:
        def __init__(self):
            self.terminated = False

        def terminate(self):
            self.terminated = True

    p = _FakeProc()
    power.stop_inhibitor(p)
    assert p.terminated


def test_stop_inhibitor_none_is_noop():
    power.stop_inhibitor(None)   # ne doit pas lever


# --------------------------------------------------------------------------- #
# shutdown / cancel_shutdown
# --------------------------------------------------------------------------- #

def test_cancel_shutdown_windows(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", True)
    monkeypatch.setattr(power, "_IS_MAC", False)
    calls = []
    monkeypatch.setattr(power.subprocess, "run", lambda cmd, check=False: calls.append(cmd))
    hint = power.cancel_shutdown()
    assert calls == [["shutdown", "/a"]]
    assert hint == "shutdown /a"


def test_cancel_shutdown_linux(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", False)
    monkeypatch.setattr(power, "_IS_MAC", False)
    calls = []
    monkeypatch.setattr(power.subprocess, "run", lambda cmd, check=False: calls.append(cmd))
    power.cancel_shutdown()
    assert calls == [["shutdown", "-c"]]


def test_shutdown_windows_builds_command_with_delay_and_reason(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", True)
    monkeypatch.setattr(power, "_IS_MAC", False)
    calls = []
    monkeypatch.setattr(power.subprocess, "run", lambda cmd, check=False: calls.append(cmd))
    power.shutdown(300, reason="test run")
    assert calls == [["shutdown", "/s", "/t", "300", "/c", "test run"]]


def test_shutdown_delay_floored_to_minimum_5_seconds(monkeypatch):
    monkeypatch.setattr(power, "_IS_WIN", True)
    calls = []
    monkeypatch.setattr(power.subprocess, "run", lambda cmd, check=False: calls.append(cmd))
    power.shutdown(0)
    assert calls[0][calls[0].index("/t") + 1] == "5"
