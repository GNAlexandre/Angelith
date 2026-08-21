# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de sources.py : ordre de lecture des fichiers, regroupement de chapitres
par nom de fichier, et scan_volume (langues détectées, filtre sources_utilisees,
élection du pivot/de la langue d'images, alignement des chapitres). Fixtures en
.txt (lues directement par extract.py, sans Pandoc/PyMuPDF)."""
from pathlib import Path

import pytest

from pipeline import sources


def _cfg(**over):
    base = {
        "langues": {
            "dossiers": {"ENG": "en", "ENGLISH": "en", "JAP": "jp", "FR": "fr",
                         "ESP": "es", "CHINOIS": "zh"},
            "priorite_sens": ["en", "jp", "es", "zh"],
            "priorite_images": ["fr", "en", "jp", "es", "zh"],
            "sources_utilisees": None,
        },
        "decoupage": {"chapter_patterns": None, "mise_en_forme": None},
    }
    for k, v in over.items():
        section, key = k.split(".", 1)
        base[section][key] = v
    return base


# --------------------------------------------------------------------------- #
# _map_folder
# --------------------------------------------------------------------------- #

def test_map_folder_is_case_insensitive():
    mapping = {"ENG": "en", "FR": "fr"}
    assert sources._map_folder("eng", mapping) == "en"
    assert sources._map_folder("Eng", mapping) == "en"
    assert sources._map_folder("fr", mapping) == "fr"


def test_map_folder_unknown_returns_none():
    assert sources._map_folder("KLINGON", {"ENG": "en"}) is None


# --------------------------------------------------------------------------- #
# _reading_order_key : prologue d'abord, tri numérique naturel entre les deux
# --------------------------------------------------------------------------- #

def test_reading_order_prologue_first_epilogue_last():
    paths = [Path("Vol.1 Epilogue.pdf"), Path("Vol.1 Chap.2.pdf"),
             Path("Vol.1 Prologue.pdf"), Path("Vol.1 Chap.1.pdf")]
    ordered = sorted(paths, key=sources._reading_order_key)
    assert [p.name for p in ordered] == [
        "Vol.1 Prologue.pdf", "Vol.1 Chap.1.pdf", "Vol.1 Chap.2.pdf", "Vol.1 Epilogue.pdf"]


def test_reading_order_numeric_sort_not_lexicographic():
    """Part.2 doit passer AVANT Part.10 (tri numérique, pas alphabétique)."""
    paths = [Path("Chap.1 Part.10.pdf"), Path("Chap.1 Part.2.pdf"), Path("Chap.1 Part.1.pdf")]
    ordered = sorted(paths, key=sources._reading_order_key)
    assert [p.name for p in ordered] == [
        "Chap.1 Part.1.pdf", "Chap.1 Part.2.pdf", "Chap.1 Part.10.pdf"]


# --------------------------------------------------------------------------- #
# _chapter_key_from_name / _chapters_from_filenames
# --------------------------------------------------------------------------- #

def test_chapter_key_from_name_recognizes_various_patterns():
    assert sources._chapter_key_from_name("Vol.1 Prologue") == (0, 0, "Prologue")
    assert sources._chapter_key_from_name("Vol.1 Chap.3") == (1, 3, "Chapitre 3")
    assert sources._chapter_key_from_name("Vol.1 Chapter 12") == (1, 12, "Chapitre 12")
    assert sources._chapter_key_from_name("Vol.1 Capítulo 5") == (1, 5, "Chapitre 5")
    assert sources._chapter_key_from_name("Vol.1 第7") == (1, 7, "Chapitre 7")
    assert sources._chapter_key_from_name("Vol.1 Epilogue") == (3, 0, "Épilogue")
    assert sources._chapter_key_from_name("Vol.1 Postface") == (3, 1, "Postface")


def test_chapter_key_from_name_unrecognizable_returns_none():
    assert sources._chapter_key_from_name("Untitled Document 3") is None


def test_chapters_from_filenames_groups_consecutive_parts():
    extracted = [
        (Path("Chap.1 Part.1.pdf"), "Texte 1a."),
        (Path("Chap.1 Part.2.pdf"), "Texte 1b."),
        (Path("Chap.2 Part.1.pdf"), "Texte 2a."),
    ]
    chapters = sources._chapters_from_filenames(extracted)
    assert chapters is not None
    assert len(chapters) == 2
    assert chapters[0].title == "Chapitre 1"
    assert "Texte 1a." in chapters[0].body and "Texte 1b." in chapters[0].body
    assert chapters[1].title == "Chapitre 2"


def test_chapters_from_filenames_none_if_any_name_unrecognizable():
    extracted = [(Path("Chap.1.pdf"), "A"), (Path("random_untitled.pdf"), "B")]
    assert sources._chapters_from_filenames(extracted) is None


def test_chapters_from_filenames_none_if_fewer_than_two_groups():
    extracted = [(Path("Chap.1 Part.1.pdf"), "A"), (Path("Chap.1 Part.2.pdf"), "B")]
    assert sources._chapters_from_filenames(extracted) is None


# --------------------------------------------------------------------------- #
# list_projects / list_volumes
# --------------------------------------------------------------------------- #

def test_list_projects_returns_sorted_dir_names(tmp_path):
    (tmp_path / "Zeta").mkdir()
    (tmp_path / "Alpha").mkdir()
    (tmp_path / "not_a_dir.txt").write_text("x", encoding="utf-8")
    assert sources.list_projects(tmp_path) == ["Alpha", "Zeta"]


def test_list_projects_missing_dir_returns_empty(tmp_path):
    assert sources.list_projects(tmp_path / "nonexistent") == []


def test_list_volumes_returns_sorted_dir_names(tmp_path):
    proj = tmp_path / "Proj"
    (proj / "Vol.2").mkdir(parents=True)
    (proj / "Vol.1").mkdir()
    assert sources.list_volumes(tmp_path, "Proj") == ["Vol.1", "Vol.2"]


def test_list_volumes_missing_project_returns_empty(tmp_path):
    assert sources.list_volumes(tmp_path, "Inconnu") == []


# --------------------------------------------------------------------------- #
# scan_volume : mode / pivot
# --------------------------------------------------------------------------- #

def test_scan_volume_traduction_mode_pivot_by_priorite_sens(tmp_path):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    for folder in ("JAP", "ENG"):
        (vol_dir / folder).mkdir(parents=True)
        (vol_dir / folder / "v.txt").write_text("Chapter 1\n\nText.", encoding="utf-8")
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    plan = sources.scan_volume(vol_dir, _cfg(), build_dir)
    assert plan.mode == "traduction"
    assert plan.pivot == "en"   # priorite_sens = [en, jp, ...] : en avant jp


def test_scan_volume_amelioration_mode_when_fr_present(tmp_path):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    for folder in ("FR", "ENG"):
        (vol_dir / folder).mkdir(parents=True)
        (vol_dir / folder / "v.txt").write_text("Chapter 1\n\nText.", encoding="utf-8")
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    plan = sources.scan_volume(vol_dir, _cfg(), build_dir)
    assert plan.mode == "amelioration"
    assert plan.pivot == "fr"


def test_scan_volume_raises_systemexit_when_no_usable_source(tmp_path):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    vol_dir.mkdir(parents=True)
    (vol_dir / "UNKNOWN").mkdir()
    (vol_dir / "UNKNOWN" / "v.txt").write_text("x", encoding="utf-8")
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    with pytest.raises(SystemExit):
        sources.scan_volume(vol_dir, _cfg(), build_dir)


def test_scan_volume_concatenates_multiple_files_in_reading_order(tmp_path):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    (vol_dir / "ENG").mkdir(parents=True)
    (vol_dir / "ENG" / "Vol.1 Chap.2.txt").write_text("Second chunk.", encoding="utf-8")
    (vol_dir / "ENG" / "Vol.1 Prologue.txt").write_text("Prologue chunk.", encoding="utf-8")
    (vol_dir / "ENG" / "Vol.1 Chap.1.txt").write_text("First chunk.", encoding="utf-8")
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    plan = sources.scan_volume(vol_dir, _cfg(), build_dir)
    en = plan.langs["en"]
    assert [f.name for f in en.files] == [
        "Vol.1 Prologue.txt", "Vol.1 Chap.1.txt", "Vol.1 Chap.2.txt"]
    assert en.full_text.index("Prologue chunk.") < en.full_text.index("First chunk.") \
        < en.full_text.index("Second chunk.")


# --------------------------------------------------------------------------- #
# scan_volume : sources_utilisees
# --------------------------------------------------------------------------- #

def test_scan_volume_sources_utilisees_filters_languages(tmp_path):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    for folder in ("ENG", "JAP"):
        (vol_dir / folder).mkdir(parents=True)
        (vol_dir / folder / "v.txt").write_text("Chapter 1\n\nText.", encoding="utf-8")
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    cfg = _cfg(**{"langues.sources_utilisees": ["en"]})
    plan = sources.scan_volume(vol_dir, cfg, build_dir)
    assert set(plan.langs) == {"en"}
    assert any("non utilisées" in w for w in plan.warnings)


def test_scan_volume_sources_utilisees_matching_nothing_falls_back_to_all(tmp_path):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    (vol_dir / "ENG").mkdir(parents=True)
    (vol_dir / "ENG" / "v.txt").write_text("Chapter 1\n\nText.", encoding="utf-8")
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    cfg = _cfg(**{"langues.sources_utilisees": ["zh"]})   # zh absent des sources
    plan = sources.scan_volume(vol_dir, cfg, build_dir)
    assert set(plan.langs) == {"en"}
    assert any("ne correspond à aucune langue" in w for w in plan.warnings)


# --------------------------------------------------------------------------- #
# scan_volume : alignement des chapitres (avertissement, pas d'échec)
# --------------------------------------------------------------------------- #

def test_scan_volume_alignment_warning_when_chapter_counts_differ(tmp_path):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    (vol_dir / "FR").mkdir(parents=True)
    (vol_dir / "FR" / "v.txt").write_text(
        "Chapitre 1\n\nTexte un.\n\nChapitre 2\n\nTexte deux.", encoding="utf-8")
    (vol_dir / "ENG").mkdir(parents=True)
    (vol_dir / "ENG" / "v.txt").write_text(
        "Just one blob of English text, no chapter markers at all.", encoding="utf-8")
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    plan = sources.scan_volume(vol_dir, _cfg(), build_dir)
    assert plan.mode == "amelioration" and plan.pivot == "fr"
    assert plan.n_chapters == 2
    assert any("Alignement" in w for w in plan.warnings)


def test_scan_volume_no_warning_when_chapter_counts_match(tmp_path):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    (vol_dir / "FR").mkdir(parents=True)
    (vol_dir / "FR" / "v.txt").write_text(
        "Chapitre 1\n\nTexte un.\n\nChapitre 2\n\nTexte deux.", encoding="utf-8")
    (vol_dir / "ENG").mkdir(parents=True)
    (vol_dir / "ENG" / "v.txt").write_text(
        "Chapter 1\n\nText one.\n\nChapter 2\n\nText two.", encoding="utf-8")
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    plan = sources.scan_volume(vol_dir, _cfg(), build_dir)
    assert plan.warnings == []


# --------------------------------------------------------------------------- #
# scan_volume : élection de la langue d'IMAGES (une seule, par priorité)
# --------------------------------------------------------------------------- #

def test_scan_volume_elects_first_priority_language_that_actually_has_images(tmp_path, monkeypatch):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    for folder in ("FR", "ENG"):
        (vol_dir / folder).mkdir(parents=True)
        (vol_dir / folder / "v.txt").write_text("x", encoding="utf-8")

    from pipeline.extract import Extracted

    def fake_extract(path, media_dir, extract_images=True, format_cfg=None, **_):
        if path.parent.name == "ENG" and extract_images:
            return Extracted(text="Chapter 1\n\nText.", images=["media/en1.png"])
        return Extracted(text="Chapitre 1\n\nTexte.", images=[])

    monkeypatch.setattr(sources.extract, "extract", fake_extract)
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    plan = sources.scan_volume(vol_dir, _cfg(), build_dir)
    # priorite_images = [fr, en, ...] : FR est essayé en premier mais n'a pas
    # d'image (fake) → on retombe sur EN, qui en a.
    assert plan.image_lang == "en"
    assert plan.langs["en"].images == ["media/en1.png"]
    assert plan.langs["fr"].images == []


def test_scan_volume_image_lang_none_when_nobody_has_images(tmp_path, monkeypatch):
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    (vol_dir / "ENG").mkdir(parents=True)
    (vol_dir / "ENG" / "v.txt").write_text("x", encoding="utf-8")

    from pipeline.extract import Extracted
    monkeypatch.setattr(sources.extract, "extract",
                        lambda path, media_dir, extract_images=True, format_cfg=None, **_:
                        Extracted(text="Chapter 1\n\nText.", images=[]))
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    plan = sources.scan_volume(vol_dir, _cfg(), build_dir)
    assert plan.image_lang is None


# --------------------------------------------------------------------------- #
# scan_volume : les langues « texte seul » (jamais sondées pour les images, cf.
# ci-dessus) sont extraites en PARALLÈLE — B4a.
# --------------------------------------------------------------------------- #

def test_scan_volume_extracts_remaining_languages_concurrently(tmp_path, monkeypatch):
    """FR (1er de priorite_images) a des images : la sonde s'arrête là, séquentielle.
    EN/JP/ES (jamais sondés, want_images=False → aucune écriture dans media_dir, donc
    aucun risque de collision) doivent alors tourner en PARALLÈLE — vérifié par le
    temps d'horloge total, largement sous le séquentiel pur."""
    import time
    vol_dir = tmp_path / "sources" / "Proj" / "Vol.1"
    for folder in ("FR", "ENG", "JAP", "ESP"):
        (vol_dir / folder).mkdir(parents=True)
        (vol_dir / folder / "v.txt").write_text("x", encoding="utf-8")

    from pipeline.extract import Extracted
    calls = []

    def slow_extract(path, media_dir, extract_images=True, format_cfg=None, **_):
        code = path.parent.name
        calls.append(code)
        if code == "FR" and extract_images:
            time.sleep(0.05)
            return Extracted(text="Chapitre 1\n\nTexte.", images=["media/fr1.png"])
        time.sleep(0.15)
        return Extracted(text=f"Chapter 1\n\nText from {code}.", images=[])

    monkeypatch.setattr(sources.extract, "extract", slow_extract)
    build_dir = tmp_path / "build" / "Proj" / "Vol.1"
    t0 = time.perf_counter()
    plan = sources.scan_volume(vol_dir, _cfg(), build_dir)
    elapsed = time.perf_counter() - t0

    # Séquentiel pur : 0.05 (FR) + 3×0.15 (EN/JP/ES) = 0.50s. En parallèle pour ces
    # 3 derniers : ~0.05 + 0.15 = 0.20s.
    assert elapsed < 0.35
    assert sorted(calls) == ["ENG", "ESP", "FR", "JAP"]   # chaque langue extraite UNE SEULE fois
    assert plan.image_lang == "fr"
    assert set(plan.langs) == {"fr", "en", "jp", "es"}
    assert "Text from ENG" in plan.langs["en"].full_text
    assert "Text from JAP" in plan.langs["jp"].full_text
    assert "Text from ESP" in plan.langs["es"].full_text
