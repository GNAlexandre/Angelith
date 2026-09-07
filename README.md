# Angelith

**Translate a book-length document without it ever leaving your machine.**

Angelith is a local-first, multi-agent translation pipeline for long-form documents. It
ingests whole volumes — `.docx`, `.pdf`, `.epub`, or scanned images through OCR — runs them
through a locally hosted language model, and exports publication-ready Markdown, DOCX, EPUB
and PDF. Nothing is uploaded. No token is ever paid for.

> **Français ?** La documentation de référence est en français :
> **[docs/README.fr.md](docs/README.fr.md)** (guide complet),
> **[docs/COMMANDES.fr.md](docs/COMMANDES.fr.md)** (mémo des commandes) et
> **[docs/procedures/](docs/procedures/README.md)** (une fiche courte par brique).

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
- **100 % local.** Runs against [Ollama](https://ollama.com) on consumer hardware — and
  **works without one**: cleaning, OCR, lettering and manual entry never call a model, so a
  machine that cannot host an LLM still gets empty bubbles ready to type into (2.33.0).
  ⚠ **Precisely, since 2.34.0**: this promise is about your *works* — no text, no plate, no
  glossary, no translation ever leaves the machine. It is **not** a claim that no byte does:
  the app asks GitHub whether a newer version exists, and that check is armed by default. One
  key turns it off — `maj.verifier: false` — and the earlier, wider wording is lifted by a
  dated block in `core/maj.py` rather than quietly rewritten.

Three pipelines share this core: long-form text (stable), comics and images (stable), and OCR
of scanned pages (beta — the reserve is named, not hidden: see `core/version.py`).

---

## Install

### From a release (Windows)

Since 2.31.0 there is a Windows installer: it installs **per user**, without UAC, into
`%LOCALAPPDATA%\Programs\Angelith`, and its uninstaller removes **no** data — not your works,
not your `build/`, not the weights you downloaded, not your `config.yaml`.

⚠ **What the installer does NOT contain**, said on its first screen rather than its sixth: no
bubble-detection weights (GPL-3.0 + Manga109-s, not redistributable), no language model, no OCR
model, no Pandoc, no WeasyPrint, no `unrar`, no ComfyUI, and no works. Open the Diagnostic page
after installing: it lists what is missing, what each gap costs, and the exact gesture to fix
it. ⚠ The binaries are **not code-signed**, so SmartScreen will warn on each new version; the
SHA-256 of every published file ships with the release.

### From the repository

```bash
pip install -r requirements.txt              # openai, pyyaml, pymupdf, python-docx, rich
pip install weasyprint                       # recommended PDF engine
# + Pandoc          https://pandoc.org/installing.html
# + Ollama          https://ollama.com  — then `ollama serve`
ollama ls                                    # check your model is available
```

⚠ Since 2.31.0 the five `requirements-*.txt` are **wrappers** around the extras declared in
`pyproject.toml` (`-e .[manga]`, and so on). Two consequences: `pip install -r` also installs
`angelith` itself in editable mode, and it must be run **from the repository root** — a `-e .`
inside a requirements file resolves against the current directory, not against the file.

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
fourth, `run_illustration.py`, is **experimental and off by default** — it generates *new*
illustrations from a volume's visual bible and never touches the work's own pixels (see
[The AI never draws](#the-ai-never-draws)). A graphical interface (`python gui.py`) runs the
pipelines and lets you retouch comic pages. Every command is listed in
[docs/COMMANDES.fr.md](docs/COMMANDES.fr.md).

---

## Languages

| | |
|---|---|
| **Source languages** | Japanese, English, Spanish, Chinese |
| **Target languages** | French. Others are now a matter of contributing a directory — see below |

### Adding a target language

Everything that depends on the output language lives in one directory, `langues/<code>/`.
Adding a language means adding a pack — no Python to touch.

```yaml
# config.yaml
langues:
  cible: fr        # which pack to use
  packs: langues   # where to look for them
```

```
langues/<code>/
├── pack.yaml       metadata, typography, output styles, instruction overrides
├── prompts/        the eight agent prompts — all eight are required
├── style_guide.md  conventions handed to the model as context
└── templates/      optional: reference.docx, epub.css
```

Start from `langues/fr/`, and read [langues/README.md](langues/README.md) — it documents
every key, and the two things that are easy to get wrong:

- **Adapt the prompts, do not translate them word for word.** Register, politeness and the
  handling of Japanese honorifics differ sharply between a French and an English rendering. A
  prompt is the source code of the translation's voice, not documentation.
- **Some languages have no attribution clause.** French glues `dit-il` to its line of
  dialogue; English writes `"...," he said`, with no inversion to enumerate. A pack that
  leaves `verbes_de_parole` unset simply does not glue — which is far better than doing it by
  French rules.

A pack that is missing or incomplete stops the run **at startup**, naming what is absent.
There is no silent fallback to French: six hours of GPU time to discover a volume came out in
the wrong language costs far more than an immediate refusal.

**Known limit.** The glossary schema is still French-shaped (`nom`, `pluriel`, `genre`), and
its deterministic enforcement agrees determiners and repairs elisions in French. A non-French
pack works today, but its glossary agreement will stay French. Making the glossary
multi-target rewrites every existing `glossaire.yaml`, so it is a breaking change scheduled
for 2.0.0. See [docs/roadmap.md](docs/roadmap.md).

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

**5 025 automated tests** (collected by `pytest --collect-only -q` on 2026-09-06 with every
optional dependency installed; 4 855 of them run in the short loop,
`-m "not lent and not modeles"`), none of which require a real LLM call — the agents are
simulated.
They cover the failures that actually happened: glossary schema, defensive parsing of
malformed agent output, merge and de-duplication, forced replacement with its elision and
gender guardrails, runaway and content-loss detection, Pandoc fences, image anchoring,
chapter detection, and binary PSD output re-read by an independent library.

Run them after any change to a prompt or to pipeline code, **before** starting a real run.

### The measurement bench

Detection quality is measured, not asserted. `python tools/banc.py --tous --markdown` produces
a dated table across every volume in `build/`, reading **only** the caches — no model is
loaded and nothing is rewritten. `python tools/banc.py --corpus tests/corpus/synthetique`
measures recall, precision and F1 against an annotated corpus that ships with the repository
and is redistributable without reserve.

A CI job runs that bench on every push and **breaks the build if recall drops or if false
positives rise** — both, because gaining bubbles at the cost of as many false detections is
not a gain.

Protocol: [docs/procedures/banc-de-mesure.md](docs/procedures/banc-de-mesure.md). What every figure in this project
counts, and how to reproduce it: [docs/chiffres-de-reference.md](docs/chiffres-de-reference.md).

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

### The AI never draws

For the comics pipeline this is an architectural rule, not a setting: detection and OCR only
**read** the image, and every pixel written back is deterministic — a measured background colour
poured into a detected mask, text drawn with Pillow, and (since 2.13.0, **off by default**) a
background reconstructed by flat fill or by a plain-numpy diffusion in
[`manga/effacement.py`](manga/effacement.py). No generative model touches the artwork.

**Its scope, written down in 2.15.0.** The rule bears on the **pixels of the work**: no
non-deterministic write into a plate, a page, or a source file. A component that modifies
**no existing file** falls outside it — it produces new files, in a folder of its own, marked
as AI-generated, and deletable without breaking anything. That is what the fourth entry point
(`run_illustration.py`, off by default) does: it reads `media/`, it writes elsewhere, and it
composites nothing into a plate or a page.

This is a boundary, not a loophole, and it is **enforced rather than promised**:
`illustration/frontiere.py` refuses at run time any write outside that folder and any image
file that does not carry its marking, and a test verifies that a complete run leaves **every**
pre-existing SHA-256 in the tree unchanged. Every generated PNG carries `AIGenerated=true` in
its metadata plus a provenance manifest naming the model, the seed, the exact payload and the
human who approved the prompt — **no image exists without that approval**, and there is no
setting that skips it. Erasing existing pixels remains governed by the 2.13.0 decision below.

This was re-examined and **upheld** in 2.13.0, in writing, before any code was written: an
inpainting model was considered and declined, on measurement rather than on principle alone.
Erasure is only permitted on a zone whose reading two independent channels agree on, and that
rate is currently **0 %** on the reference corpus; the candidate editing model is 20 billion
parameters on a GPU already holding a 27-billion-parameter translator; and the `big-lama`
weights licence could not be established from a primary source. The reasoning is in
[docs/README.fr.md §12](docs/README.fr.md) and the measurement in
[docs/mesures/relettrage-2026-08-28.md](docs/mesures/relettrage-2026-08-28.md).

## Third-party components

Angelith orchestrates tools it does not ship. Their licences are listed in
[NOTICE](NOTICE) — notably Pandoc (GPL), WeasyPrint (BSD), PySide6 (LGPL) and the ONNX
detection weights, which are **downloaded at install time rather than vendored**.

## Licence

[GNU Affero General Public License v3.0 or later](LICENSE) — AGPL-3.0-or-later.

Copyright (C) 2026 Alexandre Tournel.

Angelith is a translation *tool*. It ships no copyrighted text, and the corpora used to
measure its quality are not distributed with it.
