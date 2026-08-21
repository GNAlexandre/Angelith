# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Alias de transition : `pipeline.reporter` **est** `core.reporter` (lot 2.1).

L'affichage de progression et `perf.log` n'ont rien de propre au light novel : le module a été
déplacé tel quel dans le socle partagé `core/`. Cet alias reste pour ne pas casser les
imports existants (tests, `run.py`, `app.py`, `manga/`).

L'auto-remplacement dans `sys.modules` — et **surtout pas** `from core.reporter import *` —
garantit `pipeline.reporter is core.reporter` : monkeypatch, `id()`, `isinstance` et
`mock.patch("pipeline.reporter.…")` se comportent exactement comme avant le déplacement.
Voir `core/__init__.py` pour le détail de ce piège."""
import sys

from core import reporter as _impl

sys.modules[__name__] = _impl
