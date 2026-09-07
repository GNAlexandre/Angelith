# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Scan d'un dossier de Tome manga : quel format, quelle langue, quelles planches.

Structure attendue :
    sources/<Projet>/<Tome>/<FORMAT>/<LANGUE>/*.cbz|*.cbr|*.png|*.jpg|*.jpeg|*.webp

Les DEUX niveaux sont facultatifs, avec repli en cascade — aucun tome existant ne casse :

    <Tome>/manga/*.png          → format « manga »,   langue par défaut (`manga.langue_source`)
    <Tome>/*.png                → format « manga »,   langue par défaut
    <Tome>/manga/ENG/*.png      → format « manga »,   langue « en »
    <Tome>/webtoon/ENG/*.png    → format « webtoon », langue « en »

⚠ Format et langue sont deux axes ORTHOGONAUX, et les confondre est l'erreur qui se paie
cher : un scan **anglais** d'un manga japonais se lit toujours droite→gauche, tandis qu'un
webtoon **coréen** se lit gauche→droite. Le format fixe la géométrie de lecture (cf.
`manga/formats.py`), la langue fixe le moteur d'OCR et les consignes envoyées au modèle
(cf. `manga/ocr_routeur.py`).

Plusieurs archives sont concaténées dans l'ordre DE LECTURE (tri naturel sur le nom de
fichier) ; à l'intérieur d'une archive, les pages sont triées par leur nom interne (tri
naturel également). Miroir léger de `pipeline/sources.py` (LN) et de `scan/pages.py`, mais
entièrement indépendant : ce module ne touche à rien du pipeline texte."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import ingest

#: Formats reconnus, dans l'ordre de préférence quand un tome en porte plusieurs.
FORMATS: tuple[str, ...] = ("manga", "webtoon")

#: Langue source retenue quand aucun dossier de langue n'est présent. C'est CE défaut qui
#: garantit qu'un `<Tome>/manga/` d'avant cette version se comporte exactement comme avant.
LANGUE_DEFAUT = "jp"

#: Langue de sortie retenue quand `manga.rendu.langue_iso` est absent.
LANGUE_CIBLE_DEFAUT = "fr"


@dataclass
class MangaVolumePlan:
    project: str
    volume: str
    pages: list[Path]              # images de page, dans l'ordre de lecture
    build_dir: Path
    staging_dir: Path              # dossier de travail (pages extraites d'archives)
    source_kind: str               # "dossier" | "archive"
    source_dir: Path | None = None  # dossier réellement lu (utile aux messages d'erreur)
    format: str = "manga"          # "manga" | "webtoon" — fixe le sens de lecture
    code_langue: str = LANGUE_DEFAUT  # "jp", "en"… tel que `langues.dossiers` le donne
    mode: str = "traduction"       # "traduction" | "glossaire" (source déjà en langue cible)
    warnings: list[str] = field(default_factory=list)


def langue_defaut(config: dict | None) -> str:
    """Langue source à supposer quand aucun dossier de langue n'est présent."""
    return str(((config or {}).get("manga") or {}).get("langue_source")
               or LANGUE_DEFAUT).lower()


def langue_cible(config: dict | None) -> str:
    """Langue dans laquelle on REND — celle qui, si elle est aussi la source, interdit de
    traduire (cf. `mode`)."""
    rendu = ((config or {}).get("manga") or {}).get("rendu") or {}
    return str(rendu.get("langue_iso") or LANGUE_CIBLE_DEFAUT).lower()


def _mapping_langues(config: dict | None) -> dict[str, str]:
    """`{"ENG": "en", "JAP": "jp", …}` — la table du LN, réutilisée telle quelle.

    Sans config (outils annexes, GUI en lecture seule), on rend un mapping vide : le scan
    retombe alors sur le repli « pas de dossier de langue », c'est-à-dire le comportement
    d'avant cette version."""
    dossiers = ((config or {}).get("langues") or {}).get("dossiers") or {}
    return {str(k).upper(): str(v).lower() for k, v in dossiers.items()}


def sous_dossiers(dossier: Path) -> list[Path]:
    """Les sous-dossiers de `dossier`, triés — en **un** appel système.

    ⚠ Ce n'était pas gratuit, et le `PLAN-34` l'a mesuré le 2026-09-05. La forme d'avant,
    `sorted(p for p in dossier.iterdir() if p.is_dir())`, paie un `stat` PAR ENTRÉE : sur un
    `<Tome>/manga/` de 286 planches, c'est 286 appels système pour trouver les zéro à trois
    dossiers de langue. À l'échelle du corpus (18 œuvres, 55 tomes), cette seule ligne pesait
    **5 928 des 13 631 `os.stat`** du balayage complet — plus que le calcul de péremption,
    qui est pourtant la vraie question posée.

    `os.scandir` rend l'information de type avec l'entrée, sans second appel. Le tri porte sur
    les `Path`, exactement comme avant, pour que l'ordre — donc le dossier de langue retenu à
    contenu égal — ne bouge pas d'un cheveu."""
    try:
        with os.scandir(dossier) as entrees:
            return sorted(Path(e.path) for e in entrees if e.is_dir())
    except OSError:
        return []


def _a_du_contenu(dossier: Path) -> int:
    """Nombre d'archives + images directement dans `dossier` (0 = rien à lire).

    On ne compte QUE ce qui est à plat : c'est ce qui distingue un dossier de format
    (`manga/`, qui contient des dossiers de langue) d'un dossier de planches."""
    if not dossier.is_dir():
        return 0
    try:
        archives, images = ingest.list_source_files(dossier)
    except OSError:
        return 0
    return len(archives) + len(images)


def resoudre_source(vol_dir: Path, config: dict | None = None, *,
                    langue: str | None = None,
                    format: str | None = None) -> tuple[Path, str, str, list[str]]:
    """Où sont les planches, et sous quel format / quelle langue. Ne lit ni n'extrait rien.

    Renvoie `(dossier, format, code_langue, avertissements)`. Point d'entrée UNIQUE de cette
    résolution : `scan_volume`, le pré-vol de `manga/serie.py` et la GUI passent tous par ici,
    sans quoi un pré-vol jugerait un chapitre que le run n'écrit pas.

    `langue` et `format` forcent un choix quand le tome en porte plusieurs."""
    vol_dir = Path(vol_dir)
    mapping = _mapping_langues(config)
    defaut = langue_defaut(config)
    avertissements: list[str] = []

    formats = [f for f in FORMATS if not format or f == format.lower()]
    if format and not formats:
        raise SystemExit(
            f"Format inconnu : « {format} ». Formats reconnus : {', '.join(FORMATS)}.")

    # (dossier, format, code, nb_planches) — on garde tout, on tranche à la fin.
    candidats: list[tuple[Path, str, str, int]] = []
    for fmt in formats:
        dossier_fmt = vol_dir / fmt
        if not dossier_fmt.is_dir():
            continue
        # Niveau langue : <Tome>/<FORMAT>/<LANGUE>/
        for sub in sous_dossiers(dossier_fmt):
            code = mapping.get(sub.name.upper())
            if not code or (langue and sub.name.upper() != langue.upper()):
                continue
            n = _a_du_contenu(sub)
            if n:
                candidats.append((sub, fmt, code, n))
        # Repli : les planches sont à plat sous <Tome>/<FORMAT>/, sans dossier de langue.
        n = _a_du_contenu(dossier_fmt)
        if n:
            candidats.append((dossier_fmt, fmt, defaut, n))

    # Repli historique : le tome lui-même contient directement les images/archives.
    if not candidats and not format and not langue and _a_du_contenu(vol_dir):
        candidats.append((vol_dir, "manga", defaut, _a_du_contenu(vol_dir)))

    if not candidats:
        attendu = ", ".join(sorted(set(mapping))) or "ENG, JAP, FR…"
        raise SystemExit(
            f"Aucune planche trouvée sous {vol_dir}.\n"
            f"  → dépose tes pages (.png/.jpg) ou une archive .cbz/.cbr dans "
            f"{vol_dir / 'manga'} (ou {vol_dir / 'webtoon'}),\n"
            f"    éventuellement dans un sous-dossier de langue ({attendu}).")

    # Le plus fourni gagne. Un choix implicite sur des centaines de planches se dit.
    candidats.sort(key=lambda c: -c[3])
    if len(candidats) > 1:
        autres = ", ".join(f"{c[0].relative_to(vol_dir)} ({c[3]})" for c in candidats[1:])
        avertissements.append(
            f"Plusieurs sources possibles : {candidats[0][0].relative_to(vol_dir)} retenu "
            f"({candidats[0][3]}), ignorés : {autres}. "
            f"Utilise --format et/ou --langue pour choisir.")

    dossier, fmt, code, _n = candidats[0]
    return dossier, fmt, code, avertissements


def scan_volume(vol_dir: Path, build_dir: Path, config: dict | None = None, *,
                langue: str | None = None,
                format: str | None = None) -> MangaVolumePlan:
    """Plan de tome complet : les archives sont EXTRAITES ici, dans `pages_src/`.

    ⚠ Coûteux, contrairement à `resoudre_source` : n'appeler que quand on va vraiment lire
    les planches."""
    vol_dir = Path(vol_dir)
    manga_dir, fmt, code, warnings = resoudre_source(
        vol_dir, config, langue=langue, format=format)

    staging_dir = Path(build_dir) / "pages_src"
    staging_dir.mkdir(parents=True, exist_ok=True)

    archives, loose_images = ingest.list_source_files(manga_dir)

    pages: list[Path] = []
    source_kind = "dossier"
    if archives:
        source_kind = "archive"
        if loose_images:
            warnings.append(
                f"{len(loose_images)} image(s) isolée(s) ignorée(s) : {len(archives)} "
                f"archive(s) détectée(s), elles priment (évite un mélange page/planche).")
        for arc in archives:
            pages.extend(ingest.extract_archive(arc, staging_dir))
    elif loose_images:
        pages = loose_images
    else:
        raise SystemExit(
            f"Aucune image ni archive (.cbz/.cbr) trouvée sous {manga_dir}.\n"
            f"  → dépose tes pages (.png/.jpg) ou une archive .cbz/.cbr dedans.")

    # Mode, sur le modèle de `pipeline/sources.py` : une source DÉJÀ dans la langue de sortie
    # ne se traduit pas. Elle reste exploitable pour relever le glossaire de l'œuvre.
    mode = "glossaire" if code == langue_cible(config) else "traduction"

    return MangaVolumePlan(
        project=vol_dir.parent.name, volume=vol_dir.name, pages=pages,
        build_dir=Path(build_dir), staging_dir=staging_dir, source_kind=source_kind,
        source_dir=manga_dir, format=fmt, code_langue=code, mode=mode,
        warnings=warnings,
    )
