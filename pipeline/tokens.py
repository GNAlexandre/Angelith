# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Alias de transition : `pipeline.tokens` **est** `core.tokens` (lot 2.1).

L'estimation du nombre de tokens n'a rien de propre au light novel : le module a été
déplacé tel quel dans le socle partagé `core/`. Cet alias reste pour ne pas casser les
imports existants (tests, `run.py`, `app.py`, `manga/`).

L'auto-remplacement dans `sys.modules` — et **surtout pas** `from core.tokens import *` —
garantit `pipeline.tokens is core.tokens` : monkeypatch, `id()`, `isinstance` et
`mock.patch("pipeline.tokens.…")` se comportent exactement comme avant le déplacement.
Voir `core/__init__.py` pour le détail de ce piège."""
import sys

from core import tokens as _impl

sys.modules[__name__] = _impl
