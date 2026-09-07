# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Gestion des images : on les extrait de la source prioritaire, on mémorise leur
position relative dans le chapitre, puis on les réinjecte à la même position
proportionnelle dans le texte français final (robuste aux écarts de langue).

Priorité de la source d'images : une SEULE langue à la fois (la plus prioritaire
parmi celles présentes, cf. `sources.scan_volume`) — jamais un mélange de plusieurs
langues, qui provoquerait des collisions de noms de fichiers (chaque document
renumérote ses médias depuis 1) et donc de mauvaises images.

Les marqueurs `<!-- IMG: chemin -->` ou `<!-- IMG: chemin|attrs -->` portent, quand
elle est connue, la TAILLE D'AFFICHAGE D'ORIGINE (`attrs` = `{width="…" height="…"}"),
préservée de bout en bout pour que l'image ressorte à sa taille voulue et non à sa
résolution native.
"""
from __future__ import annotations

import re

from core.marqueurs import (  # noqa: F401  (réexport : voir la note ci-dessous)
    MARQUEUR_RE,
    manifest_for_chapter,
    orphan_markers,
)

from .extract import IMG_MARKER, split_marker

# ⚠ `orphan_markers` et `manifest_for_chapter` vivent dans `core/marqueurs.py` depuis le
# lot 23, avec `IMG_MARKER`, `split_marker` et l'expression du marqueur : `core/` n'a pas le
# droit d'importer `pipeline/`, et `core/illustrations.py` a besoin du même analyseur. Ils
# sont réexportés ici sous leurs noms d'origine — `images.manifest_for_chapter(...)` désigne
# exactement le même objet qu'avant. Ce qui reste dans ce module est ce qui relève vraiment
# du RENDU light novel : la réinjection proportionnelle et la conversion en Markdown.


def insert_into(final_text: str, manifest: list[tuple[float, str]]) -> str:
    """Insère les marqueurs IMG dans `final_text` aux positions proportionnelles."""
    if not manifest:
        return final_text

    paras = [p for p in re.split(r"\n\s*\n", final_text) if p.strip()]
    if not paras:
        return final_text
    n = len(paras)

    # position d'insertion (index de paragraphe) → liste de contenus de marqueur
    inserts: dict[int, list[str]] = {}
    for frac, raw in manifest:
        idx = min(n, max(0, round(frac * n)))
        inserts.setdefault(idx, []).append(raw)

    out: list[str] = []
    for i in range(n + 1):
        for raw in inserts.get(i, []):
            out.append(IMG_MARKER.format(raw))
        if i < n:
            out.append(paras[i])
    return "\n\n".join(out)


def markers_to_markdown(text: str, media_prefix: str = "") -> str:
    """Convertit `<!-- IMG: path -->` / `<!-- IMG: path|attrs -->` en image markdown
    `![](path)` ou `![](path){attrs}` — la taille d'origine (si connue) est transmise
    telle quelle à Pandoc pour le rendu final. Aucune image n'est redimensionnée : une
    petite illustration de séparation (~3 cm) reste petite, une pleine page reste grande."""
    def _r(m: re.Match) -> str:
        path, attrs = split_marker(m.group(1))
        if media_prefix and not path.startswith(media_prefix):
            path = f"{media_prefix.rstrip('/')}/{path}"
        return f"![]({path}){attrs}" if attrs else f"![]({path})"
    return MARQUEUR_RE.sub(_r, text)
