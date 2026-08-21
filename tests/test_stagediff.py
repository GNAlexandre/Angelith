# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de stagediff.py : mesure de la valeur ajoutée par agent depuis les
checkpoints (blocs modifiés par étape, temps du récit traduction → correction).
Fixtures = arborescences de checkpoints écrites à la main, aucun appel LLM."""
from pathlib import Path

from pipeline import stagediff


def _write_block(ckpt: Path, chapter: str, stage: str, idx: int, text: str) -> None:
    d = ckpt / chapter / stage
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{idx:03d}.txt").write_text(text, encoding="utf-8")


def _project(tmp_path: Path, blocks: list[dict], chapter: str = "ch01") -> Path:
    """`blocks` : une entrée par bloc, avec les clés d'étape voulues."""
    ckpt = tmp_path / ".checkpoints"
    for i, b in enumerate(blocks):
        for stage, text in b.items():
            _write_block(ckpt, chapter, stage, i, text)
    return ckpt


# --------------------------------------------------------------------------- #
# count_composed_past : narration vs dialogue
# --------------------------------------------------------------------------- #

def test_count_composed_past_counts_narration():
    assert stagediff.count_composed_past("Il a mangé le pain.") == 1


def test_count_composed_past_handles_accented_participles():
    """Régression : un participe accentué (« a jeté », « est tombée ») doit compter.
    Une heuristique sans accents sous-estimait fortement la conversion des temps."""
    text = "Elle a jeté la pierre.\nIl est tombé.\nElles sont tombées."
    assert stagediff.count_composed_past(text) == 3


def test_count_composed_past_excludes_dialogue_lines_by_default():
    """Les dialogues gardent légitimement le passé composé : les compter masque le
    travail réel sur la narration."""
    text = "Il a mangé le pain.\n« J'ai mangé le pain », dit-il."
    assert stagediff.count_composed_past(text) == 1                      # narration seule
    assert stagediff.count_composed_past(text, narration_only=False) == 2


def test_count_composed_past_dialogue_detected_by_dash_and_quotes():
    for line in ("— J'ai compris.", "« J'ai compris »", "\"J'ai compris\""):
        assert stagediff.count_composed_past(line) == 0, line


# --------------------------------------------------------------------------- #
# analyse : comparaison par étage
# --------------------------------------------------------------------------- #

def test_analyse_empty_dir_returns_zero_blocks(tmp_path):
    res = stagediff.analyse(tmp_path / "inexistant")
    assert res.n_blocks == 0
    assert "Aucun checkpoint" in stagediff.format_report(res)


def test_analyse_detects_a_no_op_agent(tmp_path):
    """Un agent qui recopie son entrée doit ressortir avec 0 bloc modifié."""
    ckpt = _project(tmp_path, [
        {"traduction": "Le chat dormait.", "correction": "Le chat dormait."},
    ])
    corr = next(s for s in stagediff.analyse(ckpt).stages if s.stage == "correction")
    assert corr.touched == 0 and corr.identical == 1


def test_analyse_counts_real_edits_per_stage(tmp_path):
    ckpt = _project(tmp_path, [
        {"traduction": "Le chat a dormi longtemps.",
         "correction": "Le Chat dormit longtemps."},
    ])
    corr = next(s for s in stagediff.analyse(ckpt).stages if s.stage == "correction")
    assert corr.touched == 1 and corr.edits_total >= 1


def test_analyse_compares_mise_en_page_at_chapter_level(tmp_path):
    """La mise en page re-découpe le texte : 2 blocs en entrée, 3 en sortie. La
    comparaison doit se faire au CHAPITRE (unité « chapitre »), pas par index."""
    ckpt = tmp_path / ".checkpoints"
    for i, t in enumerate(["Un.", "Deux."]):
        _write_block(ckpt, "ch01", "traduction", i, t)
        _write_block(ckpt, "ch01", "correction", i, t)
    for i, t in enumerate(["Un.", "Deux.", "Trois."]):
        _write_block(ckpt, "ch01", "mise_en_page", i, t)
    mep = next(s for s in stagediff.analyse(ckpt).stages if s.stage == "mise_en_page")
    assert mep.unit == "chapitre"
    assert mep.n == 1 and mep.touched == 1


def test_analyse_tense_conversion_measured_on_narration(tmp_path):
    ckpt = _project(tmp_path, [
        {"traduction": "Il a mangé.\n« J'ai fini », dit-il.",
         "correction": "Il mangea.\n« J'ai fini », dit-il."},
    ])
    res = stagediff.analyse(ckpt)
    assert res.tenses_before == 1 and res.tenses_after == 0    # dialogue ignoré des deux côtés


def test_analyse_counts_multiple_chapters(tmp_path):
    ckpt = tmp_path / ".checkpoints"
    for ch, n in (("ch01", 2), ("ch02", 3)):
        for i in range(n):
            _write_block(ckpt, ch, "traduction", i, f"bloc {i}")
            _write_block(ckpt, ch, "correction", i, f"bloc {i}")
    res = stagediff.analyse(ckpt)
    assert res.n_blocks == 5
    assert res.chapters == {"ch01": 2, "ch02": 3}


def test_format_report_shows_tense_conversion(tmp_path):
    ckpt = _project(tmp_path, [
        {"traduction": "Il a mangé.", "correction": "Il mangea."},
    ])
    txt = stagediff.format_report(stagediff.analyse(ckpt))
    assert "Temps du récit" in txt
