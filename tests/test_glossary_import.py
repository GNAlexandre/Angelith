# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de glossary_import.py : import d'un glossaire existant (.docx/.txt/.md) —
parseur tolérant (tables Word, séparateurs variés, sections) et fusion dans le
glossaire YAML du projet."""
import shutil

import pytest

from pipeline import glossary, glossary_import as gi


# --------------------------------------------------------------------------- #
# Petites fonctions de nettoyage / détection
# --------------------------------------------------------------------------- #

def test_clean_strips_bullets_quotes_and_markdown_emphasis():
    assert gi._clean("  • **Feodor**  ") == "Feodor"
    assert gi._clean("— « Terme »") == "Terme"
    assert gi._clean("`code`") == "code"


def test_detect_section_recognizes_known_headers_case_insensitive():
    assert gi._detect_section("## Personnages") == "personnages"
    assert gi._detect_section("ANGLICISMES") == "anglicismes"
    assert gi._detect_section("Lieux et Objets :") == "termes"
    assert gi._detect_section("Characters") == "personnages"


def test_detect_section_ignores_long_lines_even_with_keyword():
    long_line = "personnage " + "x" * 40
    assert gi._detect_section(long_line) is None


def test_detect_section_returns_none_for_unrelated_prose():
    assert gi._detect_section("Le héros traversa la forêt en courant.") is None


def test_detect_genre_recognizes_symbols_and_keywords():
    assert gi._detect_genre("♀") == "féminin"
    assert gi._detect_genre("Personnage féminin, chef de guerre") == "féminin"
    assert gi._detect_genre("♂") == "masculin"
    assert gi._detect_genre("Un jeune garçon") == "masculin"


def test_detect_genre_returns_none_when_ambiguous():
    assert gi._detect_genre("Officier de la 5e division") is None


def test_split_pair_tries_separators_in_priority_order():
    assert gi._split_pair("Leprechaun\tLutin") == ("Leprechaun", "Lutin")
    assert gi._split_pair("Semifer => Homme Bête") == ("Semifer", "Homme Bête")
    assert gi._split_pair("Venenum → Poison") == ("Venenum", "Poison")
    assert gi._split_pair("Terme : Traduction") == ("Terme", "Traduction")


def test_split_pair_returns_none_without_separator_or_empty_side():
    assert gi._split_pair("Une phrase sans séparateur reconnu") is None
    assert gi._split_pair(" : Traduction seule") is None


# --------------------------------------------------------------------------- #
# parse_file : bout en bout sur du texte (sections, tableau Word, paires)
# --------------------------------------------------------------------------- #

def test_parse_file_txt_with_sections_and_pairs(tmp_path):
    f = tmp_path / "glossaire.txt"
    f.write_text(
        "# Personnages\n"
        "Feodor : Officier masculin de la 5e division\n"
        "\n"
        "# Anglicismes\n"
        "OK => D'accord\n"
        "\n"
        "# Termes\n"
        "Venenum → Poison\n",
        encoding="utf-8")
    parsed = gi.parse_file(f)
    assert {p["nom"] for p in parsed["personnages"]} == {"Feodor"}
    assert parsed["personnages"][0]["genre"] == "masculin"
    assert {(a["vo"], a["fr"]) for a in parsed["anglicismes"]} == {("OK", "D'accord")}
    assert any(t["nom"] == "Venenum" for t in parsed["termes"])


def test_parse_file_personnage_without_detectable_genre_becomes_terme(tmp_path):
    f = tmp_path / "g.txt"
    f.write_text("# Personnages\nZelqua : Créature légendaire des marais\n", encoding="utf-8")
    parsed = gi.parse_file(f)
    assert parsed["personnages"] == []
    assert any(t["nom"] == "Zelqua" for t in parsed["termes"])


def test_parse_file_word_style_table_skips_header_row(tmp_path):
    f = tmp_path / "g.txt"
    f.write_text(
        "# Termes\n"
        "| VO | FR |\n"
        "| --- | --- |\n"
        "| Semifer | Homme Bête |\n",
        encoding="utf-8")
    parsed = gi.parse_file(f)
    assert len(parsed["termes"]) == 1
    assert parsed["termes"][0]["nom"] == "Semifer"


# --------------------------------------------------------------------------- #
# _to_text : .txt/.md directs, .docx via Pandoc, extension non gérée
# --------------------------------------------------------------------------- #

def test_to_text_reads_txt_and_md_directly(tmp_path):
    f = tmp_path / "g.md"
    f.write_text("contenu markdown", encoding="utf-8")
    assert gi._to_text(f) == "contenu markdown"


def test_to_text_docx_requires_pandoc(tmp_path, monkeypatch):
    f = tmp_path / "g.docx"
    f.write_bytes(b"")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Pandoc"):
        gi._to_text(f)


def test_to_text_docx_calls_pandoc_and_returns_stdout(tmp_path, monkeypatch):
    f = tmp_path / "g.docx"
    f.write_bytes(b"")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/pandoc")

    class _Proc:
        returncode = 0
        stdout = "VO | FR\nSemifer | Homme Bête"
        stderr = ""

    calls = []
    monkeypatch.setattr(gi.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or _Proc())
    out = gi._to_text(f)
    assert "Semifer" in out
    assert calls[0][0] == "pandoc"


def test_to_text_unsupported_extension_raises():
    with pytest.raises(RuntimeError, match=r"\.docx/\.txt/\.md"):
        gi._to_text(__import__("pathlib").Path("glossaire.pdf"))


# --------------------------------------------------------------------------- #
# import_into_project : écriture/fusion dans sources/<projet>/glossaire.yaml
# --------------------------------------------------------------------------- #

def _config(tmp_path):
    return {"chemins": {"sources": str(tmp_path / "sources"), "glossaire_fichier": "glossaire.yaml"}}


def test_import_into_project_writes_glossary_file(tmp_path):
    src = tmp_path / "glossaire_source.txt"
    src.write_text("# Personnages\nFeodor : Officier masculin\n", encoding="utf-8")
    (tmp_path / "sources" / "Projet").mkdir(parents=True)

    gpath, added, parsed = gi.import_into_project("Projet", src, _config(tmp_path))
    assert gpath == tmp_path / "sources" / "Projet" / "glossaire.yaml"
    assert gpath.exists()
    saved = glossary.load(gpath)
    assert any(p["nom"] == "Feodor" for p in saved["personnages"])
    assert sum(added.values()) >= 1


def test_import_into_project_merges_into_existing_glossary_without_duplicating(tmp_path):
    src = tmp_path / "glossaire_source.txt"
    src.write_text("# Personnages\nFeodor : Officier masculin\n", encoding="utf-8")
    proj_dir = tmp_path / "sources" / "Projet"
    proj_dir.mkdir(parents=True)

    gi.import_into_project("Projet", src, _config(tmp_path))
    gpath, added2, _ = gi.import_into_project("Projet", src, _config(tmp_path))
    saved = glossary.load(gpath)
    # Une seule entrée « Feodor », pas deux : la 2e importation ne duplique pas.
    assert sum(1 for p in saved["personnages"] if p["nom"] == "Feodor") == 1
