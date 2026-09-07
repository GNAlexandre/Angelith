# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ingestion : tri naturel, extraction .cbz (arborescence aplatie), listing des
sources d'un dossier manga. Aucune dépendance lourde (zipfile = stdlib)."""
import zipfile

from manga import ingest


def test_natural_key_orders_numbers_correctly():
    names = ["page10.png", "page2.png", "page1.png"]
    ordered = sorted(names, key=ingest.natural_key)
    assert ordered == ["page1.png", "page2.png", "page10.png"]


def test_extract_archive_cbz_flattens_and_sorts(tmp_path):
    archive = tmp_path / "tome.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        for name in ["sub/p2.png", "p1.png", "p10.png", "notes.txt"]:
            zf.writestr(name, b"fake-image-bytes")

    staging = tmp_path / "staging"
    pages = ingest.extract_archive(archive, staging)

    assert [p.name for p in pages] == ["p1.png", "p2.png", "p10.png"]
    assert all(p.exists() for p in pages)


def test_extract_archive_raises_if_no_images(tmp_path):
    archive = tmp_path / "vide.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", b"pas une image")
    try:
        ingest.extract_archive(archive, tmp_path / "staging")
        raise AssertionError("devrait lever SystemExit (aucune image)")
    except SystemExit:
        pass


def test_extract_archive_unsupported_format(tmp_path):
    bogus = tmp_path / "tome.7z"
    bogus.write_bytes(b"")
    try:
        ingest.extract_archive(bogus, tmp_path / "staging")
        raise AssertionError("devrait lever SystemExit (format non supporté)")
    except SystemExit:
        pass


def test_list_source_files(tmp_path):
    (tmp_path / "a.cbz").write_bytes(b"")
    (tmp_path / "loose.png").write_bytes(b"")
    (tmp_path / "ignored.txt").write_bytes(b"")
    archives, images = ingest.list_source_files(tmp_path)
    assert [a.name for a in archives] == ["a.cbz"]
    assert [i.name for i in images] == ["loose.png"]
