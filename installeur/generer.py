#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Écrit `installeur/version.iss` depuis `core/version.py` — `PLAN-37` L37.5 point 4.

    python installeur/generer.py
    python installeur/generer.py --verifier      # ne réécrit rien, échoue si c'est périmé

## Pourquoi un générateur plutôt qu'une ligne dans le `.iss`

Inno Setup ne sait pas lire un module Python, et `core/version.py` est la source unique de
vérité du dépôt. Les deux seules issues étaient donc : recopier le numéro à la main dans le
`.iss`, ou l'y écrire depuis Python. La première a un mode de panne connu et silencieux — un
installeur qui annonce 2.29.0 en portant 2.31.0 —, et l'installeur est précisément le fichier
que personne ne relit.

`--verifier` existe pour la CI et pour `tests/test_empaquetage.py` : il répond « à jour » ou
« périmé » sans rien écrire, ce qui permet de garder le fichier généré **dans le dépôt** — donc
lisible dans un diff — sans qu'il puisse dériver.

## Ce que le fichier contient, et rien de plus

Deux définitions : `MaVersion` (« 2.31.0 ») et `MaVersionQuadruplet` (« 2.31.0.0 », la forme
que la ressource de version Windows exige). Aucune logique, aucun chemin, aucune date — tout
ce qui pourrait vieillir vit ailleurs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core.version import __version__                                    # noqa: E402

CIBLE = Path(__file__).resolve().parent / "version.iss"


def contenu(version: str = "") -> str:
    version = version or __version__
    majeur, mineur, correctif = version.split(".")
    return (
        "; Généré par `python installeur/generer.py` — NE PAS ÉDITER.\n"
        "; La source unique de vérité est `core/version.py` ; `tests/test_empaquetage.py`\n"
        "; échoue si ce fichier ne lui correspond plus.\n"
        f'#define MaVersion "{version}"\n'
        f'#define MaVersionQuadruplet "{majeur}.{mineur}.{correctif}.0"\n')


def main() -> int:
    # ⚠ **Pas `core.cli.configurer_stdout()`** : cet outil doit tourner sur un Python nu, comme
    # `tools/verifier_livraison.py` — la convention et son motif sont dans
    # `tests/test_outils_sortie.py`. Sans ces quatre lignes, une console Windows en cp1252 fait
    # tomber l'outil sur le premier « ⚠ », c'est-à-dire au moment précis où il a quelque chose
    # à dire.
    for _flux in (sys.stdout, sys.stderr):
        try:
            _flux.reconfigure(encoding="utf-8")
        except Exception:      # noqa: BLE001 — flux remplacé (test, pipe) ou non reconfigurable
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verifier", action="store_true",
                    help="n'écrit rien ; sort en erreur si le fichier est périmé")
    args = ap.parse_args()

    attendu = contenu()
    actuel = CIBLE.read_text(encoding="utf-8") if CIBLE.is_file() else ""
    if args.verifier:
        if actuel == attendu:
            print(f"installeur/version.iss : à jour ({__version__}).")
            return 0
        print(f"installeur/version.iss est PÉRIMÉ — core/version.py annonce {__version__}.\n"
              "  → python installeur/generer.py", file=sys.stderr)
        return 1

    CIBLE.write_text(attendu, encoding="utf-8")
    print(f"installeur/version.iss écrit — {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
