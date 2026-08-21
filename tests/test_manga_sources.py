# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Scan d'un volume manga : dossier d'images OU archive, structure
sources/<Projet>/<Tome>/manga/ (miroir léger de tests/test_sources.py côté LN)."""
import zipfile

import pytest

from manga.sources_manga import scan_volume


def test_scan_volume_folder_of_images(tmp_path):
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1"
    manga_dir = vol_dir / "manga"
    manga_dir.mkdir(parents=True)
    (manga_dir / "page2.png").write_bytes(b"x")
    (manga_dir / "page1.png").write_bytes(b"x")

    build_dir = tmp_path / "build" / "MonManga" / "Vol.1" / "manga"
    plan = scan_volume(vol_dir, build_dir)

    assert plan.source_kind == "dossier"
    assert [p.name for p in plan.pages] == ["page1.png", "page2.png"]
    assert plan.project == "MonManga"
    assert plan.volume == "Vol.1"


def test_scan_volume_archive_takes_priority_over_loose_images(tmp_path):
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1"
    manga_dir = vol_dir / "manga"
    manga_dir.mkdir(parents=True)
    (manga_dir / "isolee.png").write_bytes(b"x")
    with zipfile.ZipFile(manga_dir / "tome.cbz", "w") as zf:
        zf.writestr("p1.png", b"x")
        zf.writestr("p2.png", b"x")

    build_dir = tmp_path / "build"
    plan = scan_volume(vol_dir, build_dir)

    assert plan.source_kind == "archive"
    assert len(plan.pages) == 2
    assert plan.warnings   # avertit que l'image isolée est ignorée


def test_scan_volume_raises_if_nothing_found(tmp_path):
    vol_dir = tmp_path / "sources" / "Vide" / "Vol.1"
    (vol_dir / "manga").mkdir(parents=True)
    with pytest.raises(SystemExit):
        scan_volume(vol_dir, tmp_path / "build")


def test_scan_volume_falls_back_to_volume_dir_without_manga_subfolder(tmp_path):
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1"
    vol_dir.mkdir(parents=True)
    (vol_dir / "page1.png").write_bytes(b"x")

    plan = scan_volume(vol_dir, tmp_path / "build")
    assert plan.source_kind == "dossier"
    assert len(plan.pages) == 1
