# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Fichier de PROJET d'un tome — l'index que lira l'interface graphique (lot 16).

## Pourquoi maintenant, alors que la CLI n'en a pas besoin

Parce que le rétrofitter coûtera plus cher que l'écrire. Une interface graphique doit pouvoir
ouvrir un tome sans rejouer le pipeline : savoir quelles planches existent, dans quel ordre,
lesquelles ont changé depuis la dernière fois, et par quelle version de l'outil elles ont été
produites. Aujourd'hui cette information est éparpillée dans 150 dossiers de checkpoints et ne
se reconstitue qu'en les parcourant tous.

## Ce qu'on prend à koharu, et ce qu'on lui laisse

`koharu-storage` écrit un conteneur binaire : magic `KHRSTATE`, version `u32`, longueur `u64`,
somme BLAKE3, puis un corps sérialisé. On en garde les deux idées qui comptent — **un champ de
version explicite**, sans lequel aucune migration n'est possible, et **une empreinte**, qui dit
si quelqu'un a touché au cache en dehors de l'outil.

On lui laisse le conteneur binaire lui-même. Il sert chez lui des blobs adressés par contenu
avec un ramasse-miettes, dont nous n'avons pas l'usage, et il coûte la lisibilité à la main —
or tout le cache de ce dépôt se lit dans un éditeur de texte (`ocr.json`, `traduction.json`,
`regions.json`, `qa.json`), et c'est une propriété qu'on a défendue à chaque lot. Un JSON avec
un numéro de format tient la même promesse sans rien fermer.

## La révision

Un entier qui n'augmente **que** lorsque le contenu change réellement (empreinte différente).
C'est ce qui permettra à une GUI de savoir qu'un re-rendu a eu lieu, et — plus tard — de
refuser un commit calculé sur un état périmé, comme le fait `expected_revision` chez koharu.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FORMAT_PROJET = 1
NOM_FICHIER = "projet.json"

# Les fichiers dont dépend le RENDU d'une planche. Volontairement pas `qa.json` (il décrit le
# run, pas le contenu) ni `masks.png` (il est déterminé par `regions.json`).
_SUIVIS = ("regions.json", "ocr.json", "traduction.json", "traduction_manuelle.json",
           "sfx.json", "sfx_traduction.json",
           # Déplacer un bloc de texte CHANGE le rendu : sans cette entrée, la révision ne
           # bougerait pas et le contrôle de fraîcheur de l'éditeur ne verrait rien passer.
           "mise_en_page.json")


def _empreinte_page(ckpt_dir: Path) -> str:
    """Empreinte du contenu d'une planche : stable, indépendante des dates de fichier.

    Les `mtime` seraient plus rapides mais mentent — une synchronisation OneDrive les réécrit
    sans que rien n'ait changé, et le dépôt vit précisément dans un dossier synchronisé."""
    h = hashlib.sha256()
    for nom in _SUIVIS:
        p = Path(ckpt_dir) / nom
        h.update(nom.encode("utf-8"))
        h.update(p.read_bytes() if p.exists() else b"")
    return h.hexdigest()[:16]


def construire(build_dir: Path, *, projet: str, tome: str, pages: list,
               version: str, page_ckpt,
               format_planche: str = "manga", langue_source: str = "jp",
               sens: str = "droite_gauche") -> dict:
    """Assemble l'état du tome. `page_ckpt(build_dir, i)` rend le dossier de la planche `i`.

    `format_planche`, `langue_source` et `sens` décrivent COMMENT le tome a été traité. Ils
    sont écrits ici plutôt que redéduits, parce que les deux consommateurs de cet index —
    l'interface graphique et `--assembler` — ne rescannent pas les sources : sans eux, un
    webtoon rassemblé seul repartait en `ComicInfo.xml` avec le drapeau de lecture manga.

    ⚠ Ils ne comptent PAS dans la révision (cf. `ecrire`, qui ne compare que `pages`) : ce
    sont des métadonnées de traitement, pas du contenu de planche."""
    entrees = []
    for i, chemin in enumerate(pages, 1):
        entrees.append({"index": i, "fichier": Path(chemin).name,
                        "empreinte": _empreinte_page(page_ckpt(build_dir, i))})
    return {"format": FORMAT_PROJET, "outil": version, "projet": projet, "tome": tome,
            "format_planche": format_planche, "langue_source": langue_source, "sens": sens,
            "revision": 1, "pages": entrees}


def lire(build_dir: Path) -> dict | None:
    """État précédent, ou `None`. Un fichier illisible ou d'un format inconnu vaut `None` —
    on le réécrira, plutôt que d'arrêter un tome sur un index qui n'est qu'une commodité."""
    p = Path(build_dir) / NOM_FICHIER
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or int(data.get("format", 0)) != FORMAT_PROJET:
        return None
    return data


def ecrire(build_dir: Path, etat: dict) -> Path:
    """Écrit l'index, en n'incrémentant la révision que si le CONTENU a bougé."""
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    ancien = lire(build_dir)
    if ancien is not None:
        inchange = ancien.get("pages") == etat.get("pages")
        etat = {**etat, "revision": int(ancien.get("revision", 1)) + (0 if inchange else 1)}
    (build_dir / NOM_FICHIER).write_text(
        json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
    return build_dir / NOM_FICHIER
