# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ingestion des pages manga : dossier d'images ou archive CBZ/CBR → liste de
fichiers image sur disque, triés dans l'ordre de lecture (tri naturel).

Aucune dépendance lourde : `.cbz`/`.zip` via `zipfile` (stdlib) ; `.cbr` via le
paquet `rarfile` + l'outil externe `unrar`/`unar` dans le PATH (même principe que
Pandoc pour le pipeline LN — externe, documenté, absence détectée clairement)."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def natural_key(name: str):
    """Tri naturel (Page.2 avant Page.10) : segmente texte/nombre."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def extract_archive(archive_path: Path, staging_dir: Path) -> list[Path]:
    """Extrait les images d'une archive `.cbz`/`.zip` ou `.cbr` dans
    `staging_dir/<nom_archive>/`, et renvoie leurs chemins triés (ordre de lecture).
    L'arborescence interne de l'archive est aplatie (seul le nom de fichier compte)."""
    archive_path = Path(archive_path)
    out_dir = staging_dir / archive_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = archive_path.suffix.lower()
    if suffix in (".cbz", ".zip"):
        names = _extract_zip(archive_path, out_dir)
    elif suffix == ".cbr":
        names = _extract_rar(archive_path, out_dir)
    else:
        raise SystemExit(f"Format d'archive non supporté : {archive_path} "
                          f"(attendu : .cbz, .cbr ou .zip)")

    images = sorted((out_dir / n for n in names if Path(n).suffix.lower() in IMG_EXTS),
                     key=lambda p: natural_key(p.name))
    if not images:
        raise SystemExit(f"Aucune image trouvée dans l'archive {archive_path}")
    return images


def _extract_zip(archive_path: Path, out_dir: Path) -> list[str]:
    with zipfile.ZipFile(archive_path) as zf:
        names: list[str] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if Path(name).suffix.lower() not in IMG_EXTS:
                continue
            target = out_dir / name
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            names.append(name)
        return names


def _extract_rar(archive_path: Path, out_dir: Path) -> list[str]:
    try:
        import rarfile
    except ImportError:
        raise SystemExit(
            "Le paquet « rarfile » est requis pour lire les .cbr : "
            "`pip install -r requirements-manga.txt`.") from None
    try:
        with rarfile.RarFile(archive_path) as rf:
            names: list[str] = []
            for info in rf.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                if Path(name).suffix.lower() not in IMG_EXTS:
                    continue
                target = out_dir / name
                with rf.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                names.append(name)
            return names
    except rarfile.RarCannotExec as err:
        raise SystemExit(
            f"Impossible de lire {archive_path} : l'outil externe unrar/unar est "
            f"introuvable dans le PATH (requis par le paquet « rarfile » pour les .cbr).\n"
            f"  → installe « unrar » (https://www.rarlab.com/rar_add.htm) ou « unar », "
            f"puis relance. Sinon, préfère le format .cbz.\n  détail : {err}") from None


def list_source_files(manga_dir: Path) -> tuple[list[Path], list[Path]]:
    """Renvoie (archives, images_isolées) triées, dans `manga_dir`."""
    manga_dir = Path(manga_dir)
    archives = sorted((p for p in manga_dir.iterdir() if p.suffix.lower() in (".cbz", ".cbr", ".zip")),
                       key=lambda p: natural_key(p.stem))
    images = sorted((p for p in manga_dir.iterdir() if p.suffix.lower() in IMG_EXTS),
                     key=lambda p: natural_key(p.stem))
    return archives, images
