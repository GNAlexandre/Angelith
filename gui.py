#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Interface graphique de Angelith — lancer les runs, et retoucher une planche manga.

    pip install -r requirements-gui.txt
    python gui.py
    python gui.py --config autre.yaml

Ce que l'interface apporte, et que la ligne de commande ne peut pas donner :

  · VOIR les zones de bulles superposées à la planche, avec leur numéro d'ordre de lecture —
    l'ordre qui aligne `ocr.json` et `traduction.json`, et dont une inversion est invisible sur
    la page rendue ;
  · CORRIGER une zone que la détection a manquée, mal découpée ou inventée (ajouter,
    redessiner, supprimer, scinder) sans passer par Photoshop ni par l'édition de JSON ;
  · RETOUCHER une réplique au clavier — elle part dans `traduction_manuelle.json`, que le
    pipeline ne réécrit jamais ;
  · RELETTRER la planche d'un bouton, et regarder le résultat.

Ce qu'elle n'apporte PAS, délibérément : aucun chemin de traitement qui lui soit propre. Tout
passe par `manga.orchestrator_manga.process_volume` et `manga.edition` — un tome retouché ici
se relance à l'identique avec `run_manga.py`, et réciproquement.

⚠ `config.yaml` n'est jamais réécrit par l'interface. Ses commentaires sont sa documentation ;
les réglages d'un run sont appliqués en mémoire, comme les drapeaux des CLI.
"""
from __future__ import annotations

import argparse
import sys

from core import cli

cli.configurer_stdout()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Interface graphique de Angelith (runs + édition des planches manga).")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--version", action="version", version=_version())
    args = ap.parse_args()

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        raise SystemExit(
            "L'interface graphique demande PySide6, qui n'est pas installé.\n"
            "  → pip install -r requirements-gui.txt\n"
            "  (les CLI `run.py` et `run_manga.py` fonctionnent sans.)")

    config = cli.charger_config(args.config)
    if "manga" not in config:
        raise SystemExit(f"Aucune section « manga: » dans {args.config} — l'éditeur de "
                         f"planches n'aurait rien à ouvrir.")

    from gui.fenetre import Fenetre

    app = QApplication(sys.argv)
    app.setApplicationName("Angelith")
    fenetre = Fenetre(config, args.config)
    fenetre.show()
    sys.exit(app.exec())


def _version() -> str:
    from core.version import ETAT_BRIQUES, __version__
    return f"Angelith {__version__} (brique manga : {ETAT_BRIQUES['manga']})"


if __name__ == "__main__":
    main()
