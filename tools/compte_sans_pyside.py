#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'écart de collecte AVEC et SANS PySide6, mesuré sans désinstaller quoi que ce soit.

    python -m pytest --collect-only -q                                # avec
    python -m pytest --collect-only -q -p tools.compte_sans_pyside    # sans

## Pourquoi cet outil existe

`docs/chiffres-de-reference.md` porte un couple « collectés avec PySide6 / sans PySide6 » qui
MESURE l'effet de son installation. Il n'avait plus été remesuré depuis le lot 27 : le lot 28
disait *non remesuré* plutôt qu'un chiffre déduit, ce qui était juste, et les lots 29, 30 et le
correctif 2.24.1 ont reconduit la case vide.

Le remesurer demandait jusqu'ici de désinstaller PySide6, donc de casser l'environnement de qui
lançait la mesure — c'est-à-dire de ne jamais le faire. Ce plugin le rend introuvable le temps
d'une collecte, ce qui est exactement ce que `pytest.importorskip("PySide6")` teste.

## Ce que la mesure ne dit pas

⚠ **Ce n'est pas la même chose qu'une installation sans PySide6.** Un module rendu introuvable
par `meta_path` ne reproduit pas l'absence de la roue : une dépendance qui importerait PySide6
par un autre chemin (variable d'environnement, `.pth`, extension compilée) ne serait pas
attrapée. La méthode est validée par reproduction : appliquée à `1e41504` (2.24.1), elle rend
**3 998 / 3 779, soit 219** — le chiffre exact que le lot 27 avait mesuré en installant
réellement les deux configurations.

⚠ **Et ce n'est PAS le couple de `ci.yml`**, qui est mesuré dans une autre configuration —
socle + GUI + dev, **sans** `requirements-manga.txt`. Trois dénominateurs légitimes, qu'il ne
faut pas unifier de force (`docs/chiffres-de-reference.md`).
"""
from __future__ import annotations

import sys


class Bloqueur:
    """Un chercheur de modules qui refuse `PySide6`, comme s'il n'était pas installé."""

    def find_spec(self, nom, chemin=None, cible=None):
        if nom == "PySide6" or nom.startswith("PySide6."):
            raise ModuleNotFoundError(f"No module named {nom!r}")
        return None


# ⚠ Posé à l'IMPORT du plugin, donc avant la collecte : un `pytest_configure` arriverait après
# que certains fichiers de test ont déjà importé Qt.
sys.meta_path.insert(0, Bloqueur())
for _nom in [n for n in sys.modules if n == "PySide6" or n.startswith("PySide6.")]:
    del sys.modules[_nom]
