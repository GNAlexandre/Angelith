# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Scan d'un dossier de Tome manga : dossier d'images OU archive(s) CBZ/CBR.

Structure attendue :
    sources/<Projet>/<Tome>/manga/*.cbz|*.cbr|*.png|*.jpg|*.jpeg|*.webp
Plusieurs archives sont concaténées dans l'ordre DE LECTURE (tri naturel sur le nom
de fichier) ; à l'intérieur d'une archive, les pages sont triées par leur nom interne
(tri naturel également). Miroir léger de `pipeline/sources.py` (LN), mais entièrement
indépendant : ce module ne touche à rien du pipeline texte."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import ingest


@dataclass
class MangaVolumePlan:
    project: str
    volume: str
    pages: list[Path]              # images de page, dans l'ordre de lecture
    build_dir: Path
    staging_dir: Path              # dossier de travail (pages extraites d'archives)
    source_kind: str                # "dossier" | "archive"
    warnings: list[str] = field(default_factory=list)


def scan_volume(vol_dir: Path, build_dir: Path) -> MangaVolumePlan:
    vol_dir = Path(vol_dir)
    manga_dir = vol_dir / "manga"
    if not manga_dir.is_dir():
        # Repli : le tome lui-même contient directement les images/archives (pas de
        # sous-dossier "manga/" séparé) — pratique pour un tome 100 % manga.
        manga_dir = vol_dir
    if not manga_dir.exists():
        raise SystemExit(f"Aucun dossier trouvé sous {vol_dir} (attendu : {vol_dir / 'manga'})")

    staging_dir = build_dir / "pages_src"
    staging_dir.mkdir(parents=True, exist_ok=True)

    archives, loose_images = ingest.list_source_files(manga_dir)

    warnings: list[str] = []
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

    return MangaVolumePlan(
        project=vol_dir.parent.name, volume=vol_dir.name, pages=pages,
        build_dir=build_dir, staging_dir=staging_dir, source_kind=source_kind,
        warnings=warnings,
    )
