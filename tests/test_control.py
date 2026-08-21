# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de control.py : arrêt propre (fichier STOP + SIGINT) et reprise."""
import signal

import pytest

from pipeline import control


@pytest.fixture(autouse=True)
def _reset_control_state():
    """Le module control.py maintient un état GLOBAL (_state) — on l'isole entre
    les tests, et on restaure le handler SIGINT d'origine pour ne pas polluer le
    reste de la suite pytest."""
    original_handler = signal.getsignal(signal.SIGINT)
    control._state["stop"] = False
    control._state["installed"] = False
    yield
    control._state["stop"] = False
    control._state["installed"] = False
    signal.signal(signal.SIGINT, original_handler)


def test_stop_file_path(tmp_path):
    assert control.stop_file(tmp_path) == tmp_path / "STOP"


def test_request_stop_creates_file_and_parent_dirs(tmp_path):
    build_dir = tmp_path / "build" / "Projet" / "Vol.1"
    f = control.request_stop(build_dir)
    assert f.exists()
    assert f.read_text(encoding="utf-8") == "stop"


def test_should_stop_reflects_file_presence(tmp_path):
    assert control.should_stop(tmp_path) is False
    control.request_stop(tmp_path)
    assert control.should_stop(tmp_path) is True


def test_clear_stop_removes_file_and_resets_flag(tmp_path):
    control.request_stop(tmp_path)
    control._state["stop"] = True
    control.clear_stop(tmp_path)
    assert control.should_stop(tmp_path) is False
    assert not control.stop_file(tmp_path).exists()


def test_should_stop_true_when_internal_flag_set_even_without_file(tmp_path):
    """Le handler SIGINT positionne _state['stop'] directement (pas de fichier) —
    should_stop doit quand même répondre True."""
    control._state["stop"] = True
    assert control.should_stop(tmp_path) is True


def test_install_sigint_is_idempotent():
    control.install_sigint()
    handler_after_first = signal.getsignal(signal.SIGINT)
    control.install_sigint()   # 2e appel : ne doit rien changer
    assert signal.getsignal(signal.SIGINT) is handler_after_first


def test_sigint_handler_first_call_sets_stop_flag_and_notifies():
    messages = []

    class _Rep:
        def info(self, msg):
            messages.append(msg)

    control.install_sigint(reporter=_Rep())
    handler = signal.getsignal(signal.SIGINT)
    handler(signal.SIGINT, None)   # simule le 1er Ctrl+C
    assert control._state["stop"] is True
    assert messages and "Arrêt demandé" in messages[0]


def test_sigint_handler_second_call_raises_keyboard_interrupt():
    control.install_sigint()
    handler = signal.getsignal(signal.SIGINT)
    handler(signal.SIGINT, None)   # 1er : arrêt en douceur
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGINT, None)   # 2e : force
