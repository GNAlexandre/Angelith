# Angelith

**Translate a book-length document without it ever leaving your machine.**

Angelith is a local-first, multi-agent translation pipeline for long-form documents. It
ingests whole volumes — `.docx`, `.pdf`, `.epub`, or scanned images through OCR — runs them
through a locally hosted language model, and exports publication-ready Markdown, DOCX, EPUB
and PDF. Nothing is uploaded. No token is ever paid for.

> **Français ?** La documentation de référence est en français :
> **[docs/README.fr.md](docs/README.fr.md)** (guide complet) et
> **[docs/COMMANDES.fr.md](docs/COMMANDES.fr.md)** (mémo des commandes).

<!-- TODO: screenshot or GIF of the GUI retouching a comic page. -->

---

## What it does that a machine translator does not

Sentence-level translators translate sentences. Angelith is built around the problems that
only appear at the scale of a **whole book**.

- **Terminological consistency across a volume.** A persistent glossary keeps a proper noun
  identical from chapter 1 to chapter 12 — and across media, so a novel and its comic
  adaptation share one terminology. Forced replacements re-agree the French determiner, and
  **when the gender is uncertain the replacement is refused rather than guessed**, and logged.
- **Multi-source arbitration.** Several source languages (JP / EN / ES / ZH) can be given for
  the same volume and weighed against each other, so a mistranslation present in only one of
  them is caught instead of inherited.
- **Deterministic guardrails.** Content loss, model runaway, structural damage and lost
  section titles are detected by rules, not by trusting the model. A failed block is retried
  at reduced temperature and counted; an uncounted failure is treated as a bug.
- **Editorial output, not a text dump.** Chapter and sub-chapter detection, image recovery and
  re-anchoring, your own layout styles, and export to Word / EPUB / PDF.
- **100 % local.** Runs against [Ollama](https://ollama.com) on consumer hardware.

Three pipelines share this core: long-form text (stable), comics and images (stable), and OCR
of scanned pages (beta — the reserve is named, not hidden: see `core/version.py`).

---

## Install

```bash
pip install -r requirements.txt              # openai, pyyaml, pymupdf, python-docx, rich
pip install weasyprint                       # recommended PDF engine
# + Pandoc          https://pandoc.org/installing.html
# + Ollama          https://ollama.com  — then `ollama serve`
ollama ls                                    # check your model is available
```

## Minimal example

Sources are one directory per project, one sub-directory per volume, then one per language:

```
sources/My Project/Vol.1/JAP/volume.epub
sources/My Project/Vol.1/ENG/volume.docx
```

```bash
python run.py "My Project" Vol.1 --plan     # show the detected structure, translate nothing
python run.py "My Project" Vol.1            # full run → build/My Project/Vol.1/
python run.py --check                       # diagnose the installation
```

Comics and scanned pages have their own entry points, `run_manga.py` and `run_ocr.py`. A
graphical interface (`python gui.py`) runs the pipelines and lets you retouch comic pages.
Every command is listed in [docs/COMMANDES.fr.md](docs/COMMANDES.fr.md).

---

## Languages

| | |
|---|---|
| **Source languages** | Japanese, English, Spanish, Chinese |
| **Target language** | **French only** |

The French-only output is a real, structural limitation, and it is the next thing being
worked on. The eight agent prompts, the typographic rules and the document templates are
French-specific. Version 1.8.0 begins moving them into a **language pack architecture** — one
directory per target language, contributable without touching the engine — with English as
the first proof. See [docs/roadmap.md](docs/roadmap.md).

## Hardware requirements, honestly

This is the part most local-AI projects are vague about.

- **A GPU with enough VRAM to hold a 27-billion-parameter model with a 32k context window.**
  On the reference setup that is a 20 GB consumer card running a quantised 27B model.
- Smaller models work and translate faster, but terminological consistency over hundreds of
  pages degrades — which is precisely the thing this tool exists to hold.
- **Runs are long.** A full volume is hours of GPU time, not minutes. Checkpoints exist so an
  interrupted run resumes instead of restarting.
- CPU-only inference is technically possible and practically not worth it.

Automatic hardware detection and a guided first-run setup are planned (2.3.0), not done.

---

## Tests

```bash
pip install -r requirements-dev.txt          # pytest + psd-tools (test dependencies only)
python -m pytest -q
```

**1 908 automated tests**, none of which require a real LLM call — the agents are simulated.
They cover the failures that actually happened: glossary schema, defensive parsing of
malformed agent output, merge and de-duplication, forced replacement with its elision and
gender guardrails, runaway and content-loss detection, Pandoc fences, image anchoring,
chapter detection, and binary PSD output re-read by an independent library.

Run them after any change to a prompt or to pipeline code, **before** starting a real run.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Adding a target language is meant to be a directory of
data, not a code change — and the explicit goal is that language packs arrive from native
speakers. Please also read our [Code of Conduct](CODE_OF_CONDUCT.md) and, for vulnerability
reports, [SECURITY.md](SECURITY.md).

## Use of generative AI

This project is developed with AI assistance, and says so.

- **Tool used:** [Claude Code](https://claude.com/claude-code) (Anthropic), model noted per
  commit.
- **What it assists with:** implementation from a specification, refactorings, test writing,
  and documentation.
- **What stays human:** the architecture, the translation prompts under `prompts/` — which are
  the source code of the translation's voice, not documentation — every design decision, and
  the review of every diff before it is committed. Nothing is merged unread.
- **Traceability:** commits containing AI-assisted code carry the model, the date and the
  prompt in the commit message. Longer sessions are recorded in
  [docs/ai-provenance.md](docs/ai-provenance.md).

We consider undisclosed AI authorship a defect. If you contribute AI-assisted code, follow the
same convention — it is described in [CONTRIBUTING.md](CONTRIBUTING.md).

## Third-party components

Angelith orchestrates tools it does not ship. Their licences are listed in
[NOTICE](NOTICE) — notably Pandoc (GPL), WeasyPrint (BSD), PySide6 (LGPL) and the ONNX
detection weights, which are **downloaded at install time rather than vendored**.

## Licence

[GNU Affero General Public License v3.0 or later](LICENSE) — AGPL-3.0-or-later.

Copyright (C) 2026 Alexandre Tournel.

Angelith is a translation *tool*. It ships no copyrighted text, and the corpora used to
measure its quality are not distributed with it.
