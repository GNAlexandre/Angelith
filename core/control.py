# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Arrêt propre + reprise.

Deux déclencheurs d'arrêt, traités de la même façon :
  • un fichier `STOP` dans le dossier de build (posé par `run.py ... --stop`) ;
  • Ctrl+C (SIGINT) dans le terminal qui exécute le pipeline.

Dans les deux cas, le BLOC en cours se termine, son résultat est déjà écrit sur
disque (checkpoints), puis on s'arrête. Relancer la même commande reprend là où
on s'était arrêté — y compris après un redémarrage du PC.
"""
from __future__ import annotations

import signal
from pathlib import Path


class StopRequested(Exception):
    """Levée après qu'un bloc se soit terminé proprement, pour arrêter le pipeline."""


_state = {"stop": False, "installed": False}


def install_sigint(reporter=None) -> None:
    """Premier Ctrl+C → arrêt en douceur après le bloc. Deuxième → arrêt forcé."""
    if _state["installed"]:
        return

    def handler(signum, frame):
        if _state["stop"]:
            raise KeyboardInterrupt  # 2e Ctrl+C : on force
        _state["stop"] = True
        msg = "Arrêt demandé : fin du bloc en cours puis arrêt (Ctrl+C de nouveau = forcer)."
        try:
            (reporter.info if reporter else print)(msg)
        except Exception:
            print(msg)

    try:
        signal.signal(signal.SIGINT, handler)
        _state["installed"] = True
    except Exception:
        pass  # pas de signal disponible (thread secondaire, etc.)


def stop_file(build_dir) -> Path:
    return Path(build_dir) / "STOP"


def request_stop(build_dir) -> Path:
    """Pose le fichier STOP (commande d'arrêt externe)."""
    f = stop_file(build_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("stop", encoding="utf-8")
    return f


def should_stop(build_dir) -> bool:
    return _state["stop"] or stop_file(build_dir).exists()


def clear_stop(build_dir) -> None:
    """Réinitialise l'état (au démarrage d'un run, et après un arrêt traité)."""
    _state["stop"] = False
    f = stop_file(build_dir)
    if f.exists():
        try:
            f.unlink()
        except Exception:
            pass
