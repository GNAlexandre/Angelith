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

from .extract import IMG_MARKER, make_marker, split_marker

_MARKER_RE = re.compile(r"<!-- IMG: (.*?) -->")


def orphan_markers(full_text: str, chapters) -> list[str]:
    """Contenus de marqueurs présents dans `full_text` mais dans AUCUN chapitre détecté,
    dans l'ordre de la source et avec leur multiplicité.

    Ce sont, en pratique, les PLANCHES COULEUR de tête de volume : elles précèdent la
    première frontière de chapitre, et `split._build` ne construit les chapitres qu'à
    partir de celle-ci — tout ce qui est avant disparaissait donc du rendu. Mesuré sur
    roman B Vol.2 : 12 illustrations sur 20 perdues, alors que les fichiers étaient bien
    extraits dans `media/`.

    On travaille par DIFFÉRENCE de comptage plutôt qu'en exposant les bornes de
    `detect_chapters` : c'est indépendant du chemin de détection (déterministe comme
    repli LLM, qui appelle aussi `_build`) et ça rattrape en prime tout marqueur qui
    serait perdu ENTRE deux chapitres."""
    from collections import Counter
    dans_chapitres = Counter()
    for ch in chapters or []:
        dans_chapitres += Counter(_MARKER_RE.findall(getattr(ch, "body", "") or ""))
    reste = Counter(_MARKER_RE.findall(full_text)) - dans_chapitres
    if not reste:
        return []
    out: list[str] = []
    for raw in _MARKER_RE.findall(full_text):      # ordre de la source
        if reste[raw] > 0:
            out.append(raw)
            reste[raw] -= 1
    return out


def manifest_for_chapter(chapter_text_with_markers: str) -> list[tuple[float, str]]:
    """Renvoie [(fraction, contenu_marqueur)] pour chaque image du chapitre source.

    La fraction = position du marqueur parmi les paragraphes (0 = début, 1 = fin).
    `contenu_marqueur` est le contenu brut du marqueur (chemin, ou chemin|attrs).
    """
    # On segmente en « unités » (paragraphes et marqueurs), comme à l'affichage.
    units: list[str] = []
    buf: list[str] = []
    for line in chapter_text_with_markers.splitlines():
        if line.strip() == "":
            if buf:
                units.append("\n".join(buf)); buf = []
        elif "<!-- IMG:" in line:
            if buf:
                units.append("\n".join(buf)); buf = []
            units.append(line.strip())
        else:
            buf.append(line)
    if buf:
        units.append("\n".join(buf))

    total = max(1, len(units))
    out: list[tuple[float, str]] = []
    for i, u in enumerate(units):
        m = _MARKER_RE.search(u)
        if m:
            out.append((i / total, m.group(1)))
    return out


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
    return _MARKER_RE.sub(_r, text)
