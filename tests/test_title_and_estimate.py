# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests des utilitaires ajoutés : formatage de durée (estimations de temps) et
traduction du titre de chapitre (appel court + cache + garde-fous)."""
from pipeline.orchestrator import _fmt_duree, _translate_title


def test_fmt_duree_seconds_minutes_hours():
    assert _fmt_duree(45) == "45s"
    assert _fmt_duree(90) == "1min"
    assert _fmt_duree(3600) == "1h00"
    assert _fmt_duree(3660) == "1h01"
    assert _fmt_duree(7325) == "2h02"
    assert _fmt_duree(-5) == "0s"


class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def chat(self, model, system, user, temperature=0.2, max_tokens=None, **_):
        self.calls += 1
        return self.reply


def test_translate_title_uses_cache(tmp_path):
    ck = tmp_path / "ch01"
    ck.mkdir()
    (ck / "title.txt").write_text("Titre en cache", encoding="utf-8")
    llm = _FakeLLM("NE DEVRAIT PAS ÊTRE APPELÉ")
    assert _translate_title("Chapter 1", "", llm, "m", ck) == "Titre en cache"
    assert llm.calls == 0                    # cache → aucun appel LLM


def test_translate_title_dry_or_no_llm_returns_original(tmp_path):
    ck = tmp_path / "ch01"; ck.mkdir()
    assert _translate_title("Chapter 1", "", None, "m", ck) == "Chapter 1"          # llm None
    assert _translate_title("Chapter 1", "", _FakeLLM("x"), "m", ck, dry=True) == "Chapter 1"
    assert not (ck / "title.txt").exists()   # rien mis en cache


def test_translate_title_translates_and_caches(tmp_path):
    ck = tmp_path / "ch01"; ck.mkdir()
    llm = _FakeLLM("Chapitre 1 : Le refus")
    out = _translate_title('NPC No. 1: "But I refuse!"', "glossaire", llm, "m", ck)
    assert out == "Chapitre 1 : Le refus"
    assert (ck / "title.txt").read_text(encoding="utf-8") == "Chapitre 1 : Le refus"
    out2 = _translate_title('NPC No. 1: "But I refuse!"', "glossaire", llm, "m", ck)
    assert out2 == "Chapitre 1 : Le refus" and llm.calls == 1     # 2e fois = relu du cache


def test_translate_title_guardrail_rejects_garbage(tmp_path):
    ck = tmp_path / "ch01"; ck.mkdir()
    assert _translate_title("Prologue", "", _FakeLLM("x" * 500), "m", ck) == "Prologue"   # divague
    ck2 = tmp_path / "ch02"; ck2.mkdir()
    assert _translate_title("Prologue", "", _FakeLLM("# blabla"), "m", ck2) == "Prologue"  # parasité
    assert not (ck / "title.txt").exists() and not (ck2 / "title.txt").exists()


def test_translate_title_keeps_first_line_only(tmp_path):
    ck = tmp_path / "ch01"; ck.mkdir()
    out = _translate_title("Prologue", "", _FakeLLM("Prologue\n(explication en trop)"), "m", ck)
    assert out == "Prologue"
