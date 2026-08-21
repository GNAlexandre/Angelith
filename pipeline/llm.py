# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Alias de transition : `pipeline.llm` **est** `core.llm` (lot 2.1).

Le client LLM (Ollama / API compatible OpenAI) n'a rien de propre au light novel : le module a été
déplacé tel quel dans le socle partagé `core/`. Cet alias reste pour ne pas casser les
imports existants (tests, `run.py`, `app.py`, `manga/`).

L'auto-remplacement dans `sys.modules` — et **surtout pas** `from core.llm import *` —
garantit `pipeline.llm is core.llm` : monkeypatch, `id()`, `isinstance` et
`mock.patch("pipeline.llm.…")` se comportent exactement comme avant le déplacement.
Voir `core/__init__.py` pour le détail de ce piège."""
import sys

from core import llm as _impl

sys.modules[__name__] = _impl
