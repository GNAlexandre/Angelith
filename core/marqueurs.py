# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le contrat du marqueur d'image `<!-- IMG: chemin -->`, et lui seul.

Les marqueurs portent, quand elle est connue, la **taille d'affichage d'origine**
(`chemin|{width="…" height="…"}`), préservée de bout en bout pour qu'une image ressorte à sa
taille voulue et non à sa résolution native.

## Pourquoi ce module existe, et pourquoi dans `core/`

Ces fonctions vivaient dans `pipeline/extract.py` et `pipeline/images.py`, où elles ne
servaient qu'au light novel. Le lot 23 leur donne un second usager — `core/illustrations.py`,
qui rattache une illustration à son chapitre — et **`core/` n'a pas le droit d'importer
`pipeline/`** : deux tests le vérifient, `test_core_cli.py::
test_le_socle_nimporte_ni_les_briques_ni_les_cli` et `test_core_alias.py`.

Deux issues étaient possibles, et une seule est bonne. Réécrire un second analyseur de
marqueurs dans `core/` serait la mauvaise : deux analyseurs du même format divergent le jour
où le format bouge, et c'est exactement ce que le `PLAN-23` L23.1 interdit (« n'écrivez pas un
second parseur de marqueurs »). Reconnaître que **le format du marqueur est un contrat
partagé** et le poser dans le socle est la bonne.

⚠ **Aucun changement de comportement.** `pipeline.extract` et `pipeline.images` réexportent
tout ce qui suit sous les noms qu'ils portaient : `from pipeline.extract import split_marker`
et `images.manifest_for_chapter(...)` continuent de désigner ces objets-ci. Ce qui reste dans
`pipeline/images.py` est ce qui relève vraiment du rendu light novel — `insert_into` et
`markers_to_markdown`.
"""
from __future__ import annotations

import re
from collections import Counter

#: Gabarit d'écriture d'un marqueur.
IMG_MARKER = "<!-- IMG: {} -->"

#: Lecture d'un marqueur. Non greedy : deux marqueurs sur la même ligne restent deux.
MARQUEUR_RE = re.compile(r"<!-- IMG: (.*?) -->")

_STRIP_RE = re.compile(r"^\s*<!-- IMG: .*? -->\s*$", re.MULTILINE)


def make_marker(path: str, attrs: str = "") -> str:
    """Le marqueur d'une image, avec ses attributs de taille éventuels
    (`path|{width=... height=...}`) — voir `split_marker` pour le sens inverse."""
    return IMG_MARKER.format(f"{path}|{attrs}" if attrs else path)


def split_marker(raw: str) -> tuple[str, str]:
    """Sépare un contenu de marqueur `path` ou `path|attrs` → (path, attrs)."""
    if "|" in raw:
        path, attrs = raw.split("|", 1)
        return path.strip(), attrs.strip()
    return raw.strip(), ""


def strip_images(text: str) -> str:
    """Retire les marqueurs d'images (texte propre pour les sources de référence)."""
    return _STRIP_RE.sub("", text)


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
    dans_chapitres = Counter()
    for ch in chapters or []:
        dans_chapitres += Counter(MARQUEUR_RE.findall(getattr(ch, "body", "") or ""))
    reste = Counter(MARQUEUR_RE.findall(full_text)) - dans_chapitres
    if not reste:
        return []
    out: list[str] = []
    for raw in MARQUEUR_RE.findall(full_text):      # ordre de la source
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
        m = MARQUEUR_RE.search(u)
        if m:
            out.append((i / total, m.group(1)))
    return out
