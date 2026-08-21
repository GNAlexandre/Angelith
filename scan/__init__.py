# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Brique SCAN — lire un light novel japonais livré en images de pages.

Troisième brique du dépôt, à côté de `pipeline/` (light novel) et `manga/` (planches).
Elle ne traduit rien : elle transforme un dossier de scans en un `.md` que le pipeline LN
sait déjà lire. Le couplage avec le reste du dépôt est donc un FICHIER, pas du code.

Dépendance à sens unique : `scan/` importe `manga/` (pour l'OCR japonais et la géométrie),
jamais l'inverse, et `pipeline/` n'importe jamais `scan/`.
"""
