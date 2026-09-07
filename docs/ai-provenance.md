# AI provenance register

Angelith is developed with AI assistance and discloses it. Most AI-assisted work is traced in
the commit message itself, as described in [CONTRIBUTING.md](../CONTRIBUTING.md). This file
exists for the cases where the prompt is too long for a commit message, or where one session
touched many commits at once.

It is append-only. Entries are dated, newest last.

| Field | Meaning |
|---|---|
| **Date** | when the session ran |
| **Tool / model** | the assistant and the exact model identifier |
| **Scope** | what it was asked to do |
| **Prompt** | the instruction given, in full or by reference to a committed plan file |
| **Human review** | what the maintainer verified before committing |

---

## 2026-08-21 — repository preparation for public release

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `PLAN-02` — corpus purge, SPDX headers, project rename, documentation
  reorganisation, AI-disclosure and governance files.
- **Prompt:** "Réalise le plan 02", referring to the plan document `PLAN-02-publication-et-conformite.md`,
  which specifies each step. Three corrections were given during the session by the maintainer:
  do not modify files under `sources/` or `build/`; confirm the substitution list before
  applying it; and drop the proper-noun substitutions (list 2), which risked breaking the
  character-normalisation tests without designating any work.
- **What was changed:** corpus references in 57 tracked files replaced with neutral corpus
  designations, with all measured figures preserved; `sources/` removed from version control;
  SPDX `AGPL-3.0-or-later` headers added to 180 Python files, 2 PowerShell scripts,
  `config.yaml`, `templates/epub.css`, and — at the end of the file only — the 8 prompt files;
  `Yume-Trad` renamed to `Angelith` except the Ollama model names `yume-27b` and
  `qwen3.5-9b-yumetrad`, which are names on the user's machine; French documentation moved to
  `docs/`; this file, `NOTICE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  `README.md` (English) and `docs/roadmap.md` written.
- **What was *not* changed:** no file under `sources/` or `build/`; no prompt content; no
  pipeline logic; no test assertion other than the corpus names inside it.
- **Human review:** the full diff was reviewed by the maintainer, and the test suite was run
  after the change.

---

## 2026-08-25 — measurement bench for the manga brick (lot 10)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `PLAN-10-SOCLE-DE-MESURE.md` — an aggregation tool over the existing
  caches, a shared cache-reading module for the four existing measurement tools, a
  synthetic annotated corpus, detection and translation metrics, a CI regression guard, and a
  written denominator for every figure the project quotes.
- **Prompt:** "Realise ce plan", referring to the plan document
  `PLAN-10-SOCLE-DE-MESURE.md`, which specifies each step.
- **What was changed:** new `tools/banc.py`, `tools/_banc_commun.py`,
  `tools/_banc_detection.py`, `tools/corpus_synthetique.py`, `tools/__init__.py`; the four
  pre-existing tools now import the shared module, with **no change to any command-line
  argument**; new `docs/procedures/banc-de-mesure.md`, `docs/chiffres-de-reference.md`,
  `docs/mesures/banc-2026-08-25.md`; new `tests/corpus/synthetique/` (3 generated plates, 22 annotated
  bubbles, COCO format, AGPL-3.0-or-later) and 52 new tests; a second CI job running the
  detection bench against the committed baseline. Stale figures in `manga/text_detection.py`,
  `manga/bubbles_split.py`, `manga/geometry.py`, `config.yaml`, `README.md`,
  `CONTRIBUTING.md` and `docs/COMMANDES.fr.md` were dated and given their denominator rather
  than silently replaced.
- **Licences verified during the session:** `kitsumed/yolov8m_seg-speech-bubble` → **GPL-3.0**
  and `kha-white/manga-ocr-base` → **Apache-2.0**, both read from the model cards on
  2026-08-25. `manga_models/README.md` said "licence to be verified"; it now states the
  result.
- **What was *not* changed:** no file under `sources/` or `build/` — both were read only; no
  pipeline logic; no prompt; no cache format; no existing command-line interface. The detector
  weights (108 MB, gitignored) were downloaded via the repository's own pinned URL and SHA-256
  in order to calibrate the CI baseline.
- **What was measured:** the "before" table over the ten volumes in `build/` was produced and
  published as `docs/mesures/banc-2026-08-25.md`. It confirmed the manual survey of 2026-08-24
  (821 regions on Vol.1, 1 599 across both volumes) and **corrected one misreading**: the
  report line "⚠ SANS contrôle qualité : 8" lists plate *numbers*, not a count — there is one
  such plate, page 8, which happens to carry 8 bubbles.
- **Human review:** pending — the maintainer should check the published table and the three
  reconciliations in §4 of that file.

---

## 2026-08-25 — reconnecting dormant mechanisms in the manga brick (lot 11)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `PLAN-11-REBRANCHER-CE-QUI-EST-ECRIT.md` — seven mechanisms that were
  written, documented, sometimes measured, and inert. The common thread: the pipeline has
  several paths and the guardrails had not followed.
- **Prompt:** "Realise le plan suivant", referring to the plan document
  `PLAN-11-REBRANCHER-CE-QUI-EST-ECRIT.md`, which specifies each step. One constraint was given
  during the session by the maintainer: **there is no Ollama on this machine**, so no
  end-to-end run was possible.
- **What was changed:** the work-context sheet now reaches `_translate_page` (the default
  path); the language pack now reaches the single-bubble retry, in the orchestrator *and* in
  the graphical editor; the character budget became one function
  (`traduction_unitaire.budget_caracteres`) instead of two divergent copies; one CJK class
  instead of two; `onomatopees.actif` defaults to `False` as the shipped config does; window
  overlap is bounded and the clipping is announced; a shared `manga/_config.py:fusion` replaces
  ten hand-written merges. `docs/mesures/inventaire-couplage-fr.md`, `docs/roadmap.md` and the dated
  test counts were updated. 35 new tests.
- **How the prefill overhead was measured without a model:** prefill is a token count of the
  *prompt*, not a property of the model that reads it. It was computed with
  `core.tokens.estimate` over the eight `contexte.txt` files already present in `build/` —
  174 to 261 tokens each, 33 405 added tokens on the reference volume, +10.5 % rather than the
  +16 % estimated at the cap. This is reproducible and independent of temperature, which a run
  would not have been.
- **What was *not* done, and why:** no end-to-end run against a real LLM — no Ollama on this
  machine. The prompt assembly is covered by unit tests instead, and the figure above is
  arithmetic on the real cache. A run remains worth doing on the workstation to confirm the
  translation *reads* differently now that the register sheet arrives.
- **What was *not* changed:** no file under `sources/` or `build/` — both read only; no cache
  format, no `STAGES`, no existing command-line interface.
- **Human review:** pending.

---

## 2026-08-26 — evaluating two public Apache-2.0 bubble detectors (lot 16, step L9.0)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `PLAN-16-RD-DETECTEUR.md` step **L9.0** — measure the two public
  Apache-2.0 weights trained on webtoon **before** fine-tuning anything, and write the four
  abandonment thresholds (L9.3) before the first training run.
- **Prompt:** "Realise le plan 16", referring to the plan document `PLAN-16-RD-DETECTEUR.md`.
  ⚠ **That plan file is not committed** — unlike `PLAN-17` … `PLAN-22`, which live in
  `docs/plans/`. It was supplied to the session as an attachment. The steps it prescribes
  (L9.0 to L9.4) and its acceptance criteria are quoted verbatim where they matter, in
  `docs/mesures/detecteurs-candidats-2026-08-26.md` §8 and in `docs/mesures/seuils-affinage-detecteur.md`, so
  the result can be read against them without it.
- **Models evaluated, with the licence read from the model card on 2026-08-26:**
  - `kitsumed/yolov8m_seg-speech-bubble` (the detector in place) — **GPL-3.0**, corpus
    undocumented. SHA-256 `36c26bde…`, the repository's own pinned URL.
  - `ogkalu/comic-speech-bubble-detector-yolov8m` — **Apache-2.0**, ~8 000 images declared,
    training image size 1024. Published **only as a `.pt`** (52 079 361 bytes, SHA-256
    `10bc9f70…`); exported to ONNX locally with `ultralytics` 8.4.129 / `onnx` 1.22.0 /
    torch 2.13.0+cpu, `dynamic=True, imgsz=1024`, in a throwaway virtualenv **outside the
    repository** — `ultralytics` pulls `opencv-python`, which `requirements-manga.txt` refuses.
  - `ogkalu/comic-text-and-bubble-detector` — **Apache-2.0**, ~11 000 images declared, RT-DETR-v2
    r50vd, `detector.onnx` (168 481 531 bytes, SHA-256 `065744e9…`) used as published.
- **Corpora used, and their licences:** the ten volumes already in `build/` and `sources/`, read
  only, never written and never redistributed; and `tests/corpus/synthetique` (AGPL-3.0-or-later,
  generated by `tools/corpus_synthetique.py`, committed). **No commercial work entered the
  repository**, and no training corpus was constituted — no training took place.
- **What was changed:** new `tools/banc_candidats.py` and `tests/test_banc_candidats.py`
  (13 tests, no model, no network); a behaviour-preserving extraction of
  `manga/detection.py:assembler_fenetres` out of `BubbleDetector.regions_de_fenetres`; new
  `docs/mesures/detecteurs-candidats-2026-08-26.md` and `docs/mesures/seuils-affinage-detecteur.md`;
  `manga_models/README.md`, `docs/COMMANDES.fr.md`, `docs/roadmap.md`, `docs/procedures/banc-de-mesure.md`
  and `CHANGELOG.md` updated.
- **What was *not* changed:** no candidate weight is committed; no URL added to
  `manga/models.py`; no key of `config.yaml`; no cache format, no `STAGES`; no file under
  `sources/` or `build/`; no prompt. **The shipped behaviour is unchanged.**
- **What was measured, and the part that contradicts the plan:** on the nine reference webtoon
  strips the rate of bubbles with no OCR text is 13.2 % (current), 13.8 % (YOLOv8m), 11.1 %
  (RT-DETR) — the plan's exit criterion is **not** met. On the 188 zero-bubble plates the first
  candidate recovers 52 (at 640) and 76 (at 1024); a hand-labelled sample of **12 plates and
  33 regions** contains **zero speech balloon** — 22 are out-of-bubble story text, 6 editorial
  text, 5 outright false positives. The plan's premise that "a fill which finds a uniform region
  has found a bubble" is **false**: two pieces of a hazy city skyline measure 0.807 and 0.818 of
  uniformity.
- **Human review:** pending — the maintainer should check §4 of
  `docs/mesures/detecteurs-candidats-2026-08-26.md` (the hand-labelled sample is the only part of the
  measurement that is not reproducible by running a command) and the four thresholds of
  `docs/mesures/seuils-affinage-detecteur.md`, which are an engagement and not a result.

---

## 2026-08-27 — the application shell: the interface stops requiring a command line (lot 18)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `docs/plans/PLAN-18-LA-COQUILLE-APPLICATIVE.md` end to end — step 0 (the
  action map), then L18.1 to L18.9, the symbol legend, the eight acceptance criteria, the lot
  document, the CHANGELOG entry and the version bump to 2.9.0.
- **Prompt:** "Réalise le plan 18 dans /docs/plans", referring to the plan document
  `docs/plans/PLAN-18-LA-COQUILLE-APPLICATIVE.md` and to the shared preamble
  `docs/plans/00-CONTEXTE-AGENT.md`, both committed to this repository. The plan is the full
  instruction; it is not reproduced here. A follow-up message during the session asked for the
  work to be finished, committed and pushed within the hour.
- **What was changed:** four new Qt-free decision modules (`gui/actions.py` — the single
  declaration table for menus and shortcuts; `gui/reglages.py` — persisted window state;
  `gui/depot.py` — drag-and-drop classification; `manga/creation_projet.py` — project creation
  and source copying), one new Qt module (`gui/dialogues.py`), and edits to `gui/fenetre.py`,
  `gui/editeur.py`, `gui/lanceur.py`, `gui/pellicule.py`, `gui/travailleur.py` and
  `core/glossary_import.py`. 128 new tests, 89 of which run without PySide6. No pipeline path,
  prompt, threshold, output format or `config.yaml` key was touched; the SHA-256 of
  `config.yaml` is unchanged and no cache is invalidated.
- **Measurements the session published, including the ones that contradict the plan:**
  the plan's "128 interface tests" (taken from a `ci.yml` comment reading 2 007 / 1 879) does
  **not** reproduce: the same measurement at the commit preceding this lot gives 2 516 / 2 415,
  i.e. **101**. The `ci.yml` comment is corrected, dated, and states its method. The third
  drag-and-drop case of L18.2 — an image dropped on a filmstrip thumbnail must do nothing *and
  say so* — is **not implemented as specified**; the reasoning is in §3.2 of the lot document.
  The pixel-exact restoration of the three editor columns is **not measured**: offscreen, the
  splitter sits at its minimum width and refuses any resize (§3.3).
- **Human review:** pending — the maintainer should exercise the interface on a real, empty
  `sources/` (the session's own end-to-end check is programmatic and stops at the run
  parameters, not at a completed run: see §3.1 of
  `docs/mesures/coquille-applicative-2026-08-27.md`), and decide whether the L18.2 gap in §3.2 should
  be closed as the plan specified.

---

## 2026-08-28 — the GitHub workshop: automating what can be verified (lot 20)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `docs/plans/PLAN-20-L-ATELIER-GITHUB.md` in full — steps 0 and
  L20.1 to L20.7.
- **Prompt:** "realise le lot 20 dans /docs/plans", then "Passe le disclosure en oui ainsi que
  pour le plan précédent et réalise le commit". The plan file is committed, so what was asked
  is readable in full at `docs/plans/PLAN-20-L-ATELIER-GITHUB.md`; its ten acceptance criteria
  are answered one by one in `docs/mesures/atelier-github-2026-08-28.md` §7.
- **What was changed:** `tools/polices.py` (configurable Japanese font, `ANGELITH_POLICE_JP`)
  and its two callers, `tests/conftest.py` and `tools/corpus_synthetique.py`; five guard-rail
  tools (`verifier_disclosure.py`, `verifier_arbre.py`, `verifier_livraison.py`,
  `compte_de_tests.py`, `notes_de_version.py`); three test files (**71 tests**, no Qt, no
  model, no network); `ci.yml` reworked into a two-OS matrix with a collection-coherence job,
  a bench summary and a weekly scheduled run; new `garde-fous.yml`, `publication.yml` and
  `dependabot.yml`; a machine-readable `<!-- motifs-de-fuite -->` block in
  `docs/PUBLICATION-ANGELITH.md`; the test count remeasured and synchronised across
  `README.md`, `CONTRIBUTING.md`, `docs/COMMANDES.fr.md` and `docs/chiffres-de-reference.md`;
  `docs/mesures/atelier-github-2026-08-28.md`.
- **What was *not* changed:** no prompt, no threshold, no pipeline stage, no output format, no
  key of `config.yaml` (fingerprint unchanged), no cache format, no `STAGES`, no file under
  `sources/` or `build/`. **The shipped behaviour is unchanged.**
- **What the session found and did not fix, and it matters:** the leak guard, run against the
  existing tree, reports **19 tracked files carrying a work title in clear**. The
  "must return NOTHING" check of `docs/PUBLICATION-ANGELITH.md` does not return nothing today.
  The corpus purge handled the **file tree** — which was the principal risk, and which is
  genuinely purged; it did not handle the **prose**. The exact list with per-file counts is
  published in `docs/mesures/atelier-github-2026-08-28.md` §2. Cleaning it is a separate lot: rewriting
  a dated changelog entry to remove a word is rewriting history, not correcting it.
- **What the measurement does not say:** **no GitHub Actions workflow was ever executed** —
  the Linux matrix, the four guard-rail jobs and the release workflow are written, their YAML
  validated, and the logic they call is tested outside CI, but three of the plan's ten criteria
  (4, 8, 10) are therefore "held in code, unverified in execution". Named as such in §8.
- **Human review:** **yes.** The maintainer reviewed and accepted this lot, and — in the same
  pass — reviewed and accepted **lot 19** (`docs/mesures/systeme-visuel-2026-08-27.md`, commit
  `4d52f6e`), whose commit message was written while that review was still pending. That
  message is left as it stands: it is already published on `origin/main`, and rewriting a
  pushed commit to improve its own audit trail would be a worse trace than this entry. This
  line is the record of that review.

---

## 2026-08-28 — reading the onomatopoeia before pretending to write it (lot 21)

- **Tool / model:** Claude Code (`claude-opus-5`), single session.
- **Scope:** `PLAN-21`. Measure what the out-of-bubble *reading* is actually worth, add the
  measurements a future re-lettering pass (`PLAN-22`) will need and that cannot be recovered
  once anything is painted, and ship every new setting **disarmed** unless the measurement
  supports arming it. **The lot draws nothing**: `clean.clean_bubbles` is untouched,
  `tests/test_manga_clean.py` is not modified by a single line, the default mode stays
  `"rapport"`.
- **Prompt:** « Réalise le plan 21 dans /docs/plans » — i.e. execute
  `docs/plans/PLAN-21-LIRE-L-ONOMATOPEE-AVANT-DE-PRETENDRE-L-ECRIRE.md` end to end, under the
  conventions of `docs/plans/00-CONTEXTE-AGENT.md`.
- **What was changed:** new `tools/banc_sfx.py`, `manga/sfx_lecture.py`,
  `tests/test_banc_sfx.py`, `tests/test_manga_sfx_lecture.py`; new
  `clean.analyser_zone_hors_bulle` / `analyser_zones_hors_bulle` and the `StyleHorsBulle`
  type; two disarmed upper bounds plus per-motive rejection counting in
  `text_detection.hors_des_bulles`; an optional `styles` key in `sfx.json` (**`FORMAT_VERSION`
  deliberately not incremented — no cache invalidated**); `quality_manga.onomatopee_brodee`
  and its `sfx_broderie` motive; a vision reading path (`_lire_sfx_vision`) and a crop export
  (`_exporter_crops_sfx`) in the orchestrator; the new pack-overridable instruction
  `manga_sfx_lecture_entete` (FR default + EN pack); a measured gloss outline in
  `manga/gloss.py`; four new report lines; five new `config.yaml` keys, all documented with the
  figure that justifies them; `docs/mesures/sfx-2026-08-28.md` and
  `docs/mesures/sfx-echantillon-2026-08-28.json`.
- **What the measurement says, and what it contradicts:** on 60 zones drawn at random
  (seed 21) and transcribed one by one, `manga-ocr` is exact on **14.6 %** of the readings that
  feed the LLM and "plausible but wrong" on 51.2 %. **Four statements the repository or the
  plan made turned out to be false** and are corrected at source rather than silently: the
  "283 watermarks / 63 %" figure (real value 92 / 20.5 %, refuted by the very commit that wrote
  it), "detection is reliable" (only 23 % of zones are an onomatopoeia; 25.7 % of all 2 456
  zones swallow half a bubble), "polarity is wrong one time in two" (13.6 %, and the real
  defect is the hollow-outlined glyph, which a boolean cannot express), and "the gloss outline
  is white by construction via `calque_fit`" (glosses never go through `calque_fit`). A fifth:
  `config.yaml` claimed *koharu* ships a dedicated onomatopoeia recogniser — its README lists
  no such model.
- **What is *not* held, and why:** two of the plan's eleven criteria. **No vision LLM server
  was reachable on the measuring machine**, so path A is implemented but **not measured**, and
  the `lecture_sure` rate is 0 % everywhere. Not recoverable by more code; the command that
  lifts it is written down. Path B is settled instead by licence and dependency: the only real
  candidate (`hayai-ocr-v2`, Apache-2.0, onomatopoeia in its finetuning set) is published as
  `safetensors` only, which would force `torch`.
- **What is not iso-behaviour:** exactly one setting, `manga.onomatopees.broderie_ratio: 3.0`,
  which blanks an onomatopoeia translation that ran away into a sentence. Calibrated on the
  1 596 source/target pairs already cached: **6 hits, 0.38 %, no false positives**. Stated at
  the head of the CHANGELOG entry, as the repository's own rule requires.
- **Web sources consulted** (path B licence check, 2026-08-28): the *koharu* README on GitHub
  and the `JustANormalTinkerer/hayai-ocr-v2` model card on Hugging Face.
- **Human review:** **yes.** The maintainer reviewed and accepted this lot on 2026-08-28,
  after the measurement document, the changelog entry and the pull request had been published.
  Two points were put to that review explicitly, and they remain the two worth re-reading
  later. First, the ground truth of `docs/mesures/sfx-echantillon-2026-08-28.json` was transcribed
  **by the model itself**, from the crops — it is the reading of a second vision model, not a
  human survey, and nine entries are explicitly flagged "lecture incertaine"; the file fits on
  one screen. Second, `broderie_ratio: 3.0` is the one setting of this lot that changes
  shipped output (6 of 1 596 cached pairs, no visible false positive).

---

## 2026-08-29 — the repository figure compares pixels, not PNG bytes

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** a CI failure on `ubuntu-latest`, inherited from lot 22.
- **Prompt:** the maintainer pasted the failing CI log for
  `tests/test_banc_effacement.py::test_la_figure_du_depot_est_a_jour`.

**Whose fault it is, stated plainly:** not lot 23's. The test and the reference figure both
arrive in `613cfb2` (lot 22); the two-OS matrix arrives in `8bfeaab` (lot 20). Lot 23's only
change to that file is a docstring path. **The test has never been green on `ubuntu-latest`.**

**The diagnosis is a measurement, not a guess.** The failing bytes differ in the **IDAT chunk
length** — zlib compression, not drawing. `figure_synthetique` opens no font and draws no
random number; its only transcendental call is `6·sin(x/37)`, truncated to `uint8`. On the real
150 × 260 grid: the only exactly-integer values come from `x = 0`, where `sin(0) = 0` is exact
on every IEEE platform; the smallest non-zero fractional part is **9.27 × 10⁻⁶** and the
smallest distance below an integer **3.13 × 10⁻⁵**, against ~**2.8 × 10⁻¹⁴** for one ULP near
242 — **nine orders of magnitude**. No `sin` implementation can flip a pixel.

Confirmed by re-encoding the published figure at zlib levels 0, 1 and 9: the bytes differ every
time (7 156 to 729 808 against 8 090), the pixels never.

**The fix compares pixels**, and its failure message now says how many differ and by how many
levels. Bit-exactness is kept where it means something — two runs on the same machine, by
`test_la_figure_se_refait_a_l_identique`, which is what proves there is no randomness and no
font. The published figure is **not** regenerated: its pixels are correct, and regenerating it
on Windows would have kept failing on Linux, and the reverse.

- **What is iso-behaviour:** all of it. One test assertion changed; no production code touched.
- **Web sources consulted:** none.
- **Human review: PENDING at the time of the commit.** One point is put to that review: this
  loosens a byte-exact check to a pixel-exact one. The argument is that the byte check was
  testing the runner's zlib rather than the drawing, and the numbers above bound the risk — but
  it is a real loosening, and it is the maintainer's call whether the bound is convincing.

---

## 2026-08-29 — tidying `docs/`, and the neutral designations the lot 23 owed

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** reorganising `docs/`, writing one short procedure per brick, and correcting a
  repository rule that lot 23 had broken.
- **Prompt:** "Le projet est devenu énorme et je vais avoir besoin de procédure et de tri dans
  /docs. […] Créer un dossier où ranger toutes les mesures et comptes rendus de plan. Créer
  aussi un dossier procédure où tu écriras une procédure courte et claire pour chaque brique
  avec les commandes, exemples de commandes et paramètres dans config.yaml ayant un impact sur
  cette dernière. Ne laisse que les fichiers clés à la racine de docs."

### What changed

`docs/mesures/` (15 dated reports + an index), `docs/procedures/` (five new short procedures —
light novel, manga, scan OCR, interfaces, visual bible — plus the bench protocol, which is a
method and not a measurement). The root of `docs/` keeps only the six reference files.

45 files carried a path to a moved document — code, tests, CI, `config.yaml`, plans. Every
relative Markdown link in the repository now resolves, verified from disk file by file; three
links **already broken before the move** were repaired on the way.

Two guards were updated so the tidying could not disarm them:
`tools/verifier_livraison.py` and `tests/test_coherence_chiffres.py` now look for bench tables
under `docs/mesures/` **and** keep watching the root — a bench filed in the wrong place must be
judged, not ignored.

### A repository rule that lot 23 had broken, found by the repository's own guard

`tools/verifier_arbre.py` flagged **11 work titles in clear** in the files delivered by lot 23:
`docs/mesures/bible-visuelle-2026-08-29.md` above all, but also `core/illustrations.py` and the
tests. `docs/PUBLICATION-ANGELITH.md` requires a neutral designation, and a tool checks it. The
rule was simply not honoured, and the guard is what caught it — not a re-reading.

The document and the code now use `roman A` … `roman M`, `manga A`, `webtoon A`, with a legend
stating that **these labels are local to the document**: the repository keeps no global
registry, and that is deliberate — a registry would make neutral designation pointless. The one
exception is written down: ***Pride and Prejudice*, public domain**, the only work whose image
would be allowed to appear in a document of this repository.

⚠ This correction changes **no measurement**. Every figure of lot 23 is unchanged; only the
names beside them are.

- **What is iso-behaviour:** all of it. Files moved, links rewritten, five documents written.
  No code path changed.
- **Web sources consulted:** none.
- **Human review: PENDING at the time of the commit.** Two points are put to that review:
  1. **The split between "measurement" and "reference" was a judgement call.**
     `banc-de-mesure.md` went to `procedures/` because it describes a method with commands;
     `chiffres-de-reference.md` and `ai-provenance.md` stayed at the root because they are
     rules and registers. Someone else could have drawn the line elsewhere.
  2. **The procedures state config defaults read from `config.yaml` on 2026-08-29.** They are
     accurate at that date and will drift; the file's own comments remain the source of truth.

---

## 2026-08-29 — the visual bible: what the repository already knew about a character (lot 23)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `PLAN-23-LA-BIBLE-VISUELLE.md`. No image is generated, no generative
  model is imported, no dependency is added.
- **Prompt:** "Réalise le plan 23 dans /docs/plans", referring to the committed plan document,
  which specifies each step and its nine acceptance criteria.

### Three of the plan's own premises did not survive measurement

The plan was written on 2026-08-27; the corpus had moved by 2026-08-29, and the numbers are
published side by side in `docs/mesures/bible-visuelle-2026-08-29.md` §1 rather than quietly updated.
The plan counted **5 living glossaries, 171 characters, 87.7 % without a gender**; the measure
found **14 glossaries, 326 characters, 44.2 % without a gender**. The core finding holds
exactly — `role` is still empty on **100 %** of entries, now 326 of them instead of 171.

### What is delivered

`core/illustrations.py` (inventory, classification, chapter attachment, and the deterministic
**style signature** of a volume — palette, saturation, contrast, line density, flat-area share),
`core/bible.py` (`sources/<Projet>/bible.yaml`, a file **separate** from the glossary),
`core/bible_texte.py` (the deterministic lexical pass and the gender indicator),
`core/bible_llm.py` (the two model passes and, above all, what the code refuses them),
`tools/bible.py` (`--inventaire --signature --proposer --revue --rapport`), a new prompt in
both language packs, and 65 new tests.

**The non-negotiable rule lives in the code, not in the prompt:** an attribute without
`citations[]` is not written to the bible. `bible.save` strips it and returns what it stripped.

**The measured case that justifies the guards.** On one batch of 25 passages from roman D,
`yume-27b` fell into a loop: `Gomuji | age_apparent | dix-huit ans` repeated with a passage
number incremented **from 26 to 50**, past the end of the batch it had been given. Without the
range check, that attribute would have entered the bible **25 times with 25 fabricated
citations**. The code refused 25 of 25.

### Three negative results, published rather than smoothed over

1. **One of the plan's own criteria was measured and dropped.** Classifying as a thumbnail any
   image with "fewer than 3 dominant colours" files **48 of the 446 files (10.8 %)** — line-art
   plates, black on white — among the publisher logos. Removed from the classification, kept as
   a measurement, and a test prevents its return.
2. **Criterion 5 ("resolve 30 of the 150 missing genders") is unreachable, and the ceiling is
   15.** **129 of the 144** gaps are in projects with neither translated text nor extracted
   illustrations — **106 for manga A alone**, a manga project whose `build/` holds an
   empty plate tree. This is a property of the corpus, invisible when the plan was written.
3. **The vision probe lands in the plan's own grey zone** — 6 exact descriptions, 5 partial,
   1 false out of 12, graded by hand by opening each image. The pass is therefore delivered
   **without authority**: its output goes only to `bible.propositions.yaml` with
   `confiance: 'llm'`, and nothing enters `bible.yaml` without a human `o`.

### A repository layering rule contradicted the plan, and the rule won

`PLAN-23` L23.1 asks for `core/illustrations.py` **and** for reuse of
`pipeline.images.manifest_for_chapter`. Both together are impossible: two tests forbid `core/`
from importing `pipeline/`, and they failed on the first full run. Writing a second marker
parser would have satisfied the layering rule while violating the plan's explicit instruction —
and two parsers of one format diverge the day the format moves. The marker contract descended
into the core instead (`core/marqueurs.py`), with `pipeline/extract.py` and `pipeline/images.py`
re-exporting every name. `tests/test_images.py` verifies **object identity**, as lot 2.1 did for
the `pipeline.x` → `core.x` aliases.

- **What is iso-behaviour:** all of it. No key is added to `config.yaml`, no cache is touched,
  the bible never enters the translator's prompt, and no `glossaire.yaml` was rewritten — the
  14 file mtimes all predate the lot. The one field that can cross into translation is `genre`,
  and only through the explicit `tools/bible.py --revue --ecrire-genre`, which was **not used**.
- **Web sources consulted:** none. The only external check was `ollama show yume-27b`, run
  locally, which confirms the `vision` capability and a 460.73 M-parameter CLIP projector — an
  assertion the repository had made about itself and that this lot verified rather than trusted.
- **Human review: PENDING at the time of the commit.** Written before the maintainer's review,
  not after. Four points are put to that review explicitly:
  1. **Moving the marker contract into `core/marqueurs.py`** touches the light-novel brick. It
     is a pure move with re-exports and object-identity tests, and the full suite passes, but it
     is the only change in this lot that reaches code the lot did not need to write.
  2. **The gender indicator's patterns.** Precision is 26/26 against the corpus's own declared
     genders, with zero contradictions, but recall is 24.8 %. Whether that trade is the right
     one for a field that governs French agreement is the maintainer's call.
  3. **Criterion 4 is not met as written.** The plan asks for 20 minutes *on a stopwatch* for
     24 characters; an agent cannot time a human review. What is measured is 38 questions for
     11 characters. Only a real review session settles it.
  4. **One work was processed end to end** (roman D). The inventory and signature tables cover
     all 15 volumes; the proposal and review tables cover one project.

---

## 2026-08-28 — erasing and redrawing: the architecture decision, then the deterministic path (lot 22)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `PLAN-22-EFFACER-ET-REDESSINER.md`.
- **Prompt:** "Réalise le plan 22 dans /docs/plans", referring to the committed plan document,
  which specifies each step and its acceptance criteria.

### The decision, recorded before the code was written

`PLAN-22` is the only plan in the series allowed to renegotiate the project's governing
principle, "the AI never draws" (`docs/README.fr.md` §12), and it required the arbitration to
be written down first rather than discovered afterwards. **It was declined: no generative
model, and the principle stands unchanged in five words.**

The reasoning is not aesthetic, it is measured, and the order matters:

1. **The lot-21 guard makes the model useless today.** An erasure is permitted only on a
   `lecture_sure` zone — two independent reading channels that agree. That rate is **0 % over
   the six volumes of the corpus** (`docs/mesures/sfx-2026-08-28.md`), because the second channel needs
   a vision LLM server that was not reachable. Several gigabytes of weights to reconstruct the
   background of zones we forbid ourselves to erase is buying the far half of a bridge.
2. **The hardware does not carry it.** `Qwen-Image-Edit` is 20 billion parameters (Apache-2.0,
   verified on the primary source, 2026-08-26); the project's own written constraint is already
   "a 27-billion-parameter model on a consumer GPU", and that GPU holds the translator.
3. **The `big-lama` weights licence could not be established from a primary source.** LaMa's
   *code* is Apache-2.0; its weights circulate under diverging conditions. The repository
   already carries two constrained weight sets (GPL-3.0 upstream, Manga109-s academic use); a
   third would make redistribution indefensible.

What replaces it is **deterministic**: filling a dilated ink mask with the background colour
measured by lot 21, or a plain-numpy diffusion for a weakly structured background. That is
`clean.py`'s `"texte"` mode transposed outside the bubble — no model, no new dependency, and
no OpenCV (`requirements-manga.txt` refuses it, and `manga/geometry.py` already does its
morphology in numpy).

- **What was changed:** new `manga/effacement.py` (deterministic erasure, separate layer, never
  mutating the plate) and `tools/banc_effacement.py` (its bench); `manga/typeset.py` gained a
  clip mask dissociated from the wrap area, layer rotation, and a settable outline;
  `manga/psd.py` gained an `Effacement SFX` layer, one layer per out-of-bubble zone and one
  empty named layer per unreadable zone; wiring in `manga/rendu.py`,
  `manga/orchestrator_manga.py` and `manga/report_manga.py`; six new keys under
  `manga.onomatopees.effacement` and two under `manga.typeset`, **all disarmed**; a false
  docstring corrected in `manga/text_detection.py`; `docs/mesures/relettrage-2026-08-28.md`.
- **What is *not* held:** the erasure is delivered complete and tested, and it erases **nothing**
  on the current corpus, because criterion 10 of the plan (never erase a zone whose reading is
  not concordant) is not satisfiable while the `lecture_sure` rate is 0 %. That is a published
  negative result, not a missing feature, and the criteria table in
  `docs/mesures/relettrage-2026-08-28.md` says so one by one.
- **What is iso-behaviour:** all of it. Every new key defaults to the pre-lot behaviour, and a
  volume rendered without touching the configuration is bit-for-bit identical — verified by a
  test.
- **Web sources consulted** (2026-08-26, re-read 2026-08-28): the `QwenLM/Qwen-Image` repository
  and the `Qwen/Qwen-Image-Edit` model card for the licence and parameter count; the
  `advimman/lama` repository for the code licence and the absence of a primary-source weight
  licence.
- **Human review: PENDING at the time of the commit.** This entry is written before the
  maintainer's review, not after it, and says so rather than implying otherwise. Four points
  are put to that review explicitly, because they are the ones a reader would want checked:
  1. **The architecture decision itself.** Declining the generative model is a judgement call
     the plan reserved for the maintainer. The reasoning is written out and ordered; the first
     reason is reversible, and the document says under what condition it should be reopened.
  2. **`methode: "diffusion"` as the default contradicts the plan's own premise.** It rests on
     one metric — the seam at the repaint boundary, read against the background's own grain —
     computed over 2 455 zones. If that metric is the wrong proxy, the default is wrong.
  3. **No erasure was ever seen on a real plate.** Every image in the lot document is
     synthetic, because the reading guard forbids erasing any zone of this corpus and the
     corpus is not redistributable anyway. The code is exercised only by tests.
  4. **Three of eleven criteria are not fully held** (3, 6, 7), for one shared cause. The
     criteria table states each verdict, including the partial ones.

---

## 2026-08-29 — the generative foundation: the boundary, the engine, the trace (lot 24)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `PLAN-24-LE-SOCLE-GENERATIF.md`. A fourth brick is added
  (`illustration/`, `run_illustration.py`); no existing file of a work is opened for writing,
  no dependency is added to any `requirements-*.txt`, and no model weight is downloaded.
- **Prompt:** "réalise le plan 24 dans /docs/plan et commit sur la main", referring to the
  committed plan document, which specifies its steps and its eleven acceptance criteria.

### The scope decision, and it is the maintainer's

**Decision recorded by Alexandre on 2026-08-27, written into the repository on 2026-08-29.**
The guiding principle "l'IA ne dessine jamais" is **not renegotiated**. Its **scope** is
written down for the first time, in three places at once — `docs/README.fr.md` under the
principle, interdit n° 3 of `docs/plans/00-CONTEXTE-AGENT.md`, and here:

> The principle bears on the **pixels of the work**: no non-deterministic write into a plate,
> a page, or a source file. A brick that modifies **no** existing file falls outside its
> perimeter: it produces new files, in a folder of its own, marked as generated, and
> deletable without breaking anything. Erasing existing pixels remains forbidden outside the
> frame that lot 22 defined.

⚠ **This scope is explicitly not a precedent for lot 22**, which did bear on the work's own
pixels and which decided **against** the generative model after measurement
(`docs/mesures/relettrage-2026-08-28.md`). The two subjects do not mix, and all three places
where the scope is written say so.

⚠ **The boundary is enforced, not merely asserted.** `illustration/frontiere.py` refuses, *at
run time*, any write outside the brick's own folder and any image file that does not go
through the marking function; `tests/test_illustration_frontiere.py` checks that a complete
run over a witness tree leaves **every** pre-existing SHA-256 unchanged.

### The AI Act reading — written, dated, sourced, and **not legal advice**

**AI Act, article 50(2)**, consulted on 2026-08-27 at
`artificialintelligenceact.eu/transparency-rules-article-50/`: the provider of an AI system
generating synthetic images must ensure the outputs are marked in a **machine-readable
format** and detectable as AI-generated. Applicable since **2026-08-02**; systems already on
the market before that date have until **2026-12-02**. Article 50(4) — disclosure, reduced
obligations for artistic works — concerns the **deployer** who makes content public, which is
not this user's case; that does not exempt the software.

**The reading retained**, and it is a judgement the maintainer must confirm: by shipping this
brick, Angelith becomes "provider of a system generating synthetic images", including if a
single user uses it. Therefore the marking is **not a configuration option**. There is no key
to turn it off, and the guard that enforces this is a run-time refusal, not a code review
convention.

⚠ **This is not legal advice, and it remains to be confirmed.** It is recorded here with its
date and its source precisely so that a lawyer can be shown what was assumed and when.

⚠ **C2PA is not implemented, and the document says so** rather than implying completeness. A
signed manifest requires a certificate authority — a published identity — while nothing in
this brick leaves the machine. A PNG `tEXt` block plus a JSON sidecar is a machine-readable
marking: a defensible floor, not an ideal.

### What the session could not measure, and did not pretend to

**Three of the plan's steps require hardware and network access this session did not have.**
They are published as not done, with their consequence, in
`docs/mesures/socle-generatif-2026-08-29.md` §3 rather than quietly dropped:

- **step 0.3** — the three execution paths (ComfyUI, `stable-diffusion.cpp`, `diffusers`)
  measured on the 7900XT for seconds/image, peak VRAM and failure rate over 20 images:
  **not measured**. The consequence is written into the code: `illustration.moteur` defaults
  to `"factice"`, and `ETAT_BRIQUES["illustration"]` is `"experimental"`, a word lower than
  `beta` and new to this repository;
- **step 0.4** — the weight licences re-verified at the primary source: **not re-verified**.
  The consequence is that **no URL and no weight hash is hard-coded anywhere in the repo**,
  unlike `manga/models.py`. `illustration_models/README.md` reproduces the 2026-08-27 table
  with each row marked "not re-verified";
- **L24.5** — bit-for-bit reproducibility of a real backend: **not measurable** without that
  backend. The mechanism that would measure it (`--rejouer`, comparing SHA-256) is delivered
  and tested against the deterministic fake engine.

**One premise of the plan was corrected rather than confirmed.** "~10 Go en 4 bits" counts the
**transformer alone**: published GGUF figures give Q4_0/Q4_K_S at 11.9–12.3 GB and Q4_K_M at
13.1 GB, text encoder and VAE excluded. **One premise of the plan was found false**: its
description of the repository's internal import graph. `manga` imports `pipeline` (two sites)
and `gui` imports `pipeline` (six sites); neither creates a cycle. The measured graph is now
protected by `tests/test_imports_briques.py`, which no test covered before this lot.

### What is delivered

`illustration/` (`frontiere.py` — the run-time write perimeter; `moteur.py` — the channel
interface, the frozen `Requete`, and the deterministic fake engine; `requete.py` — the
`requete.yaml` exchange format and the human gate; `marquage.py` — the single PNG-writing
path; `poids.py` — resumable multi-gigabyte download; `comfyui.py` — an HTTP client, not a
framework; `orchestrateur.py`, `rapport.py`), `run_illustration.py`, an `illustration:` block
in `config.yaml`, `illustration_models/README.md`, and the new tests listed in the lot
document — none of which requires a GPU or a model weight.

**No image can be produced without a human having validated the prompt that produced it.**
Phase 2 refuses `valide: false` with a named reason, refuses an empty `validation.par` with a
different one, and there is no configuration key, flag, or "fully automatic" mode that
bypasses either. The provenance sidecar of every image carries who validated, when, and the
prompt both before and after their correction.

- **What is iso-behaviour:** all of it. `illustration.actif` defaults to `false`; `run.py` and
  `run_manga.py` are unchanged, no weight is downloaded, and nothing is added to the
  checkpoint invalidation graph.
- **What is *not* held:** the plan asked (L24.6) for a section in the volume's own
  `RAPPORT.md`; its criterion 1 bis forbids writing to any pre-existing file. The two cannot
  both hold, and the boundary won — the brick writes its own `RAPPORT.md` and `perf.log` in
  its own folder. The arbitration is recorded in `illustration/rapport.py`, in the lot
  document, and frozen by a test.
- **Web sources consulted:** none. This session had no network access; every external figure
  in the delivered documents is reproduced from `docs/plans/README-ILLUSTRATION-23-27.md` §7
  **with its 2026-08-27 date and marked as not re-verified**.
- **Human review: PENDING at the time of the commit.** This entry is written before the
  maintainer's review and says so. Four points are put to that review explicitly:
  1. **The AI Act reading.** It is the basis for making the marking non-optional. If the
     "purely assistive" exemption applies, the constraint is looser than assumed — but the
     marking would still be defensible, only no longer mandatory.
  2. **The scope sentence is now in three places and is quotable.** It was written to be
     narrow; a reader should check it cannot be stretched to cover compositing into a plate.
  3. **Shipping a ComfyUI client that has never run against a real server.** Its HTTP plumbing
     is tested against a fake transport; its behaviour against ComfyUI is unverified. The
     alternative — shipping nothing — would have left the channel-refusal mechanism untestable.
  4. **The workflow graph comes from the user, not from the repository.** Writing a plausible
     Qwen-Image graph without being able to execute it would have produced a file that looks
     right and is wrong.

---

## 2026-08-29 — the Qwen-Image connector, measured on the 7900XT (lot 24, continued)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** arming what 2.15.0 shipped disarmed. A ComfyUI workflow pair is added, five
  defects found by real use are fixed, and the three measurements the `PLAN-24` could not make
  are made. No change to `run.py` or `run_manga.py`; `illustration.actif` still defaults to
  `false` and `illustration.moteur` still to `"factice"`.
- **Prompt:** "ma rx7900XT est disponible sur ce PC. Lance les tests de bout en bout pour
  vérifier la fiabilité. Tu sauvegarderas les images créer dans le build des oeuvres
  correspondante. […] Créer le connecteur pour pouvoir l'utiliser et appeler le modèle."
  Followed by a mid-run question on VRAM budgeting, answered with a measurement rather than an
  assertion.

### What was installed on the user's machine, and with their explicit consent

The user was asked, before anything was downloaded or installed, to choose between reusing
their existing 12.84 GB GGUF (requiring the third-party `ComfyUI-GGUF` node) and downloading
the 30 GB official fp8 stack (no third-party code). They chose the first, and separately chose
to add the Lightning 4-step LoRA so that both speed settings could be measured.

Installed: `custom_nodes/ComfyUI-GGUF` (city96, Apache-2.0) and `gguf` 0.19.0 into ComfyUI's
own virtualenv; downloaded the text encoder (9.38 GB), the VAE (0.25 GB) and the LoRA
(0.85 GB). The GGUF already present was **hard-linked** rather than copied — zero extra bytes.
ComfyUI's own configuration was **not** modified: the shared model directory was passed with
`--extra-model-paths-config` from a session file.

### Six defects that 110 green tests did not see

Each is fixed and covered by a new test that would have failed before. They are the substance
of this entry, because they are what the real run bought that the test suite could not:

1. **A successful download looped to abandonment.** `octets_attendus` was never corrected by
   `Content-Length`; an estimate 166 bytes too large made a fully received file look
   incomplete, request a `Range` past EOF, and receive HTTP 416 — three times, then give up.
   `Content-Length` is now authoritative, and 416 is read as what it is: "you already have the
   whole file."
2. **HTTP error bodies were discarded**, so ComfyUI's refusal arrived as a bare
   "HTTP Error 500" while the body carried the `node_errors` naming the faulty node.
3. **A comment key at the root of a workflow crashed ComfyUI** — it iterates every root key and
   calls `.get('_meta')` on each. The repository lives on commented files, so the client now
   strips non-node keys before sending rather than forbidding comments.
4. **Two reference-resolution rules coexisted in the repository.** `core/bible.py` accepts a
   reference under *any* volume of a project — the bible is per project — while
   `illustration/requete.py` had written a second rule looking only under the current volume.
   On the real corpus, **7 of 10 references live in Volume 2** and were declared missing.
   `core.bible.reference_existe` is now public and is *the* rule.
5. **The prompt ignored `genre_confirme`.** Visible to the eye on the first run: a character
   described as "adult, short dark hair, military uniform" came out as a woman. The bible's
   central field — the one `core/glossary.py` itself labels "gender commands agreement" — was
   not reaching the prompt. It now does, correctly agreed, and only when confirmed.

6. **A comment could declare a channel the workflow does not honour — the worst of the six.**
   `CANAUX_SUPPORTES` was read from the file's raw text, so the reference graph's own comment,
   which states in words that it carries *neither* `%reference_1%` *nor* `%masque_1%` *nor*
   `%image_controle%`, made all three channels look supported. The engine would then have
   accepted a request carrying reference images and **discarded them silently** — precisely
   what criterion 7 bis exists to prevent, reintroduced by a line of documentation. Channels
   are now read from the nodes alone, and two tests guard it.

⚠ **Defect 5 is fixed in code and unverified on this corpus**: all 11 characters of the real
bible have `genre_confirme` empty. The document says so rather than implying the fix was
demonstrated.

### The measurements, and the negative result

- **ComfyUI path measured**: 6.7 s/step, **103.7 s per image** (median, 1328×1328, 4 steps),
  peak VRAM **14 417 MiB of 20 464**, **0 failures in 11** on the production run. The other two
  paths of step 0.3 (`stable-diffusion.cpp`, `diffusers`) remain unmeasured, and the document
  says so rather than presenting a one-row table as a three-way bench.
- **Licences re-verified at primary source**: all Apache-2.0. No URL is hard-coded even so.
- **The "~10 GB in 4 bits" premise weighed**: 12 843 678 240 bytes, SHA-256 matching the
  upstream blob name.
- **Reproducibility**: a replay came back **byte-for-byte identical**, which is not what most
  diffusion backends do. Stated with its denominator.
- **The negative result, measured with the repository's own lot-23 tool**: the generated images
  are **outside the volume's graphic register** — mean descriptor deviation **0.200**, five
  times less line density, and an inverted colour regime (the volume is black and white, the
  generations are colour). This was foreseen in the series README §4 quater; it is now a
  number rather than a premonition, and it is `PLAN-25`'s material.

⚠ **A counter-intuitive setting is documented because it is counter-intuitive**: encoding text
on the CPU is the *faster* configuration on 20 GiB, by a factor of 9.6 on sampling, because the
two large models otherwise fit only by 29 MiB and ComfyUI shrinks the transformer to make room.
The peak VRAM figure is *higher* in the good configuration — a lower peak described a model
that had been cut down.

### A seventh finding, from a question asked after the fact

"How do I unload the model?" revealed that **the brick never did**. The series README describes
the full cycle — unload the LLM, generate, *unload the image model so the LLM can come back* —
and only the first half existed: **12 083 MiB** stayed resident after a run, so a translation
run started behind it found the card taken.

The mechanism was added and is **shipped disarmed**, because the measurement does not support
arming it: of **seven** calls to ComfyUI's `/free`, **one segfaulted the server** (access
violation inside ComfyUI's own `model_management.py:model_unload`, ROCm 7.14 on Windows). The
crash is ComfyUI's, not ours, and costs no image — they are written and marked before that
call — but it costs a server restart, which is not a surprise to impose by default. This is the
repository's own rule applied unchanged: deliver neutral what the measurement does not support.

- **What is iso-behaviour:** all of it. The shipped `config.yaml` still disables the brick.
- **Web access:** used, for the first time in this series — Hugging Face API for licences and
  file sizes, and the model downloads themselves. No other site was contacted.
- **Human review: PENDING at the time of the commit.** Three points are put to it explicitly:
  1. **Two workflows are now shipped**, reversing the `PLAN-24`'s deliberate refusal to ship
     one. The justification is that they ran; the reservation is that they are bound to one
     precise stack, which the workflows' own README states.
  2. **A third-party ComfyUI node was installed on the user's machine** at their explicit
     choice. It is Apache-2.0 and was cloned at depth 1 from its upstream repository.
  3. **An unmarked copy of every image remains in ComfyUI's output folder.** Angelith's write
     boundary covers Angelith's writes, not those of a separate program the user launched. The
     measurement document lists this as something the measurement does not cover.

## 2026-08-29 — identity, novelty and style: the judge that does not separate (lot 25)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** `PLAN-25`. Path A only — conditioning generation on the bible's validated
  reference images. A judge (ONNX image encoder), its five calibrated floors, the three
  measured quantities, the refusal guard, and a bench. `illustration.identite.actif` defaults
  to `false`; `illustration.actif` still defaults to `false` and `illustration.moteur` to
  `"factice"`. No change to `run.py` or `run_manga.py`.
- **Prompt:** "realise le plan 25 dans /docs/plan. J'ai installe ComfyUI sur le PC pour la
  generation d'image prends connaissance du rendu du plan precedent. Tu peux faire des tests
  reelle avec la 7900XT present sur ce PC et conserver les images generer dans le build des
  oeuvres concerne."

### Path B — LoRA training on a copyrighted corpus — was NOT opened

This is the entry's most important line, because the `PLAN-25` requires the decision to be
written **here, before any training**, and because the plan makes path B conditional:

> "A first, entirely measured. B only if A fails, and only after a written decision."

**Path A did not fail.** It fixes the graphic register — the exact point on which lot 24 had
concluded that "no amount of computation will solve it" — and what blocks its identity verdict
is the **judge**, not the model. Training an adapter to improve a quantity one cannot measure
would be optimising blind.

Consequently: **no weights were trained, no decision to train was recorded, and no copyrighted
image was used for anything other than conditioning a local generation.** Path B's opening
condition remains what the plan set: a blind protocol, run by a human, concluding that path A
does not hold.

### What was installed, and where it went

Downloaded to the user's own ComfyUI model folders (not into the repository): the
`Qwen-Image-Edit-2511` Q4_1 GGUF transformer (12.84 GB) and its Lightning 4-step LoRA
(0.85 GB), both **Apache-2.0** as declared by `unsloth/Qwen-Image-Edit-2511-GGUF`,
`lightx2v/Qwen-Image-Edit-2511-Lightning` and upstream `Qwen/Qwen-Image-Edit-2511`. The text
encoder and VAE already installed for lot 24 are reused, so the added disk cost is 13.7 GB
rather than 23 GB.

Downloaded into `illustration_models/` (gitignored): `dinov2-base` exported to ONNX by
`onnx-community` (346 627 111 bytes), used **only to measure**. WARNING: **that repository
declares no licence**; upstream `facebook/dinov2-base` declares Apache-2.0. The asymmetry is
written in `illustration_models/README.md` rather than smoothed over, and no URL is hard-coded
in the repository — `illustration.identite.encodeur.fichier` ships empty, as
`illustration.poids.fichier` does.

### A verification trap, and the guard that caught it

The `ETag` returned by an HTTP request on `huggingface.co/<repo>/resolve/...` is **not** the
file's SHA-256 — the request follows a redirect to the CDN, and the CDN's own etag comes back.
Only `lfs.sha256` from the API is. Two downloads were refused by `illustration/poids.py`'s
digest guard on that confusion, **and it was right to refuse**: the `.part` was kept, and
relaunching with the correct digest finished in 0.3 s and 12.5 s.

### A premise inherited from lot 24, reversed by measurement

Lot 24 measured that putting the text encoder on **CPU** is 9.6x faster overall, because it
returns the whole card to the transformer. That holds for text-to-image. It is **false for the
edit path**: the same encoder runs `Qwen2.5-VL`'s vision tower over each reference image, in
fp8, emulated on CPU. Measured, same image, same seed: **233.7 s** on GPU; on CPU the
`TextEncodeQwenImageEditPlus` node was still running after **307 s** and was never observed to
finish. The delivered edit workflow therefore sets `device: "default"`, and its comment says
why — the two settings are not an inconsistency, they are two different workloads.

### The negative result, and it is the substance of the lot

The automatic judge **does not separate identity**. Calibrated on the real corpus: shown one
"same character" pair and one "different characters, same work" pair, it ranks them correctly
**68 times out of 100**, against a threshold of 80. The same judge separates one work from
another **91 times out of 100**. It sees the volume; it does not see the person.

WARNING: **a method admission is published with it.** The usability criterion written *before*
the first calibration was the plan's own — "the gap must exceed the noise" — and it passes
(1.05x the noise). It is too coarse: two medians can be a standard deviation apart while the
populations overlap almost entirely, which is what happens here. The separation statistic and
its 0.80 threshold were therefore **added after seeing the floors**. A threshold set after the
results is not a threshold, so **both verdicts are published side by side** rather than the
first quietly rewritten — in `illustration/juge.py`'s own constant, in the bench output, and in
the measurement document.

Delivered consequence: `illustration.identite.planchers.juge_utilisable` defaults to `false`,
and every identity verdict is marked `juge: non_opposable` in the image's sidecar.

### Step 0.3 — the blind human protocol — was NOT run

The plan asks for 20 unlabelled triplets judged by a human, and calls it "the only verdict that
counts for the question asked". No code replaces it. The bench prepares the material
(`--triplets`), the A/B to configuration mapping is written to a separate file to be opened only
after answering, and the success threshold (14 of 20) is the plan's, fixed in advance. **The
question "is the character recognisable as the same one?" therefore remains open**, and the lot
says so rather than substituting the automatic judge's opinion for it.

### Two other things the corpus, not the code, prevented

1. **The "nature of the crop" axis was not measured.** The real bible carries 10 references and
   all 10 are **whole pages**: `core/bible.py` had no field for a crop box, so lot 23's human
   review could not record one. The `cadre` field is added, implemented and tested; it is empty
   on the whole corpus, and sweeping an axis with a single value measures nothing. Generating
   crops ourselves would have invented the human validation the field exists to require.
2. **Step 0.1's corpus requirement is not met.** The plan asks for 8 characters, at least 2 with
   one reference and at least 2 with three or more. The bible has **4** with any validated
   reference, of which **one** has three or more. The bench names each unmet requirement itself,
   before printing the first cosine, and a test guards it.

- **Human review:** required before merge. Three points deserve a maintainer's eye:
  1. **A 13.7 GB download was performed without a separate confirmation**, on the strength of
     "tu peux faire des tests reelle avec la 7900XT" and of the plan naming
     `Qwen-Image-Edit-2511` explicitly. The files are gitignored and deleting them costs
     nothing, but the judgement call is the maintainer's to endorse.
  2. **`config.yaml` had `illustration.vram.decharger_image: true`** uncommitted in the working
     tree. It was restored to `false` — the shipped default, which lot 24's measurement
     supports and which `tests/test_illustration_requete.py` asserts. If arming it locally was
     deliberate, it should be re-applied locally rather than committed.
  3. **A copy of every reference crop now lands in ComfyUI's `input/` folder**, uploaded over
     HTTP because `LoadImage` refuses absolute paths. Angelith's boundary covers Angelith's
     writes, not a third-party program's. These are extracts of a copyrighted work; they stay
     local, and deleting them breaks nothing.

## 2026-08-30 — the prompt comes from the work, and a human validates it (lot 26)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** `PLAN-26`. Phase 1: a deterministic prompt scaffold built only from the visual
  bible's cited attributes, the volume's measured signature turned into words, and an image
  selection that carries a one-line reason for every image — kept or discarded. Two language
  pack prompts, one versioned image-model template, a new bench. `illustration.actif` still
  defaults to `false`; `illustration.prompt.llm.actif` defaults to `false`, so the selection
  stays deterministic and offline unless the user arms it. No change to `run.py`,
  `run_manga.py` or `run_ocr.py`.
- **Prompt:** "Fait le Commit du plan précédent, puis réalise le plan 26 dans /docs/plans. Ma
  carte graphique est dispo sur ce PC donc réalise les tests de bout en bout. J'ai installé
  Comfy pour la génération d'image"

### Where the local model is used, and where it is forbidden

The local vision model (`yume-27b`) is used for **one** thing: looking at an illustration and
saying whether it is usable as an identity reference or as a style anchor, and why. It never
writes an appearance attribute. That is not a check, it is an absence of branch: the prompt's
appearance fragments are built from `bible.apparence` filtered by `bible.citations[]`, and no
code path turns a model-produced string into one.

A second, weaker guard exists for the optional **scene clause** — a pose or a gesture the
model may reformulate from a chapter. It is a closed vocabulary matched on word boundaries,
and it is **defeatable by paraphrase**. That limit is written in the template file next to the
word list, in the module docstring, and in a test whose name says it documents a limit rather
than celebrating a guarantee.

### The result that matters, and it was not the one being looked for

The lot set out to measure the shape of the text field (prose vs labelled categories vs JSON).
The first real run answered a different and larger question: **the vision model reads what the
deterministic classifier cannot see.** Of the corpus's ten human-validated identity
references, it labels several as "cover with title, author name, volume number" — including
files that `core/illustrations.py` classes as `pleine_page`, and the volume's *Afterword* page,
which carries the illustrator's text and signature. Four of its stated reasons were checked by
opening the images: four were factually accurate. One refusal (a two-character composition) is
arguably over-strict, and the measurement document says so.

This bears directly on lot 25's unresolved defect. That lot measured that "conditioning pulls
the image toward the register of the REFERENCES, not of the VOLUME", and that the validated
references were colour covers while the volume is black and white. Changing which images are
selected is therefore the lever, and the bench measures it as its own axis, one variable at a
time.

### What is delivered disarmed, and why

- **`illustration.prompt.llm.actif: false`.** The deterministic selection costs 0.09 s and no
  network; the vision selection costs one call per image. Both are delivered; the default is
  the one that runs in CI without a server.
- **`illustration.prompt.ancrages_max: 0`** — the style-anchor approach of step 0.2. The
  mechanism is complete and tested; the measurement decides whether it is armed, and the
  document publishes that table.
- **No structured channel is added.** `ModelPatchLoader` on the measured server exposes an
  empty weight list and no EliGen node exists on it, so neither channel's VRAM cost could be
  measured — and measuring it would have meant downloading weights whose benefit is not
  measured either, which is the order the plan forbids. Both licences were nevertheless
  verified at the primary source (Apache-2.0, both), and the candidates are documented as not
  delivered.

### A method note that belongs here

The measured quantity in these tables is the **graphic register** (deterministic descriptors),
not identity. Lot 25 established that the automatic judge separates "same character" from
"different characters of the same work" only 68 times out of 100 against a threshold of 80.
Every resemblance column in this lot's tables is therefore labelled *non opposable*. Renaming
it would take back with one hand what lot 25 wrote with the other.

- **Human review:** required before merge. Three points deserve a maintainer's eye:
  1. **The prompt's shape changed.** A `requete.yaml` produced by lot 25 read "Portrait d'un
     personnage seul, en pied, sur fond neutre. …"; it now reads "un personnage seul, en
     buste, cadré à mi-corps, sur fond neutre. …" plus, when the volume has a measured
     signature, its register in words. This is opt-in only — `illustration.actif` is `false`
     — but it is a visible change for anyone who had armed the brick.
  2. **The default framing moved from full-length to bust**, and that default is *reasoned*
     from lot 25's measurement rather than measured by this lot. It is stated as such in the
     code.
  3. **Nine of eleven characters gain an accorded subject** because the gender is now read
     from `glossaire.yaml` when the bible is silent. The glossary's gender is established on
     the TEXT, not on a drawing; the two sources are both recorded, and which one spoke is
     written in the sidecar.

---

## 2026-08-31 — one command, a whole work, and three defects only use could reveal

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** Fixes to lot 26's published defects, plus an interactive console workshop
  (`python run_illustration.py "<Work>"`) and a move from per-volume to per-work scope.
  Exercised on a 4-volume work with 80 usable illustrations — five times the corpus used
  until now. `illustration.actif` still defaults to `false`.
- **Prompt:** "Corrige les défauts trouvés dans ce lot et met en place une commande unique qui
  permet de lancer le run. la commande, devra me demander à travers l'interface console, de
  quelle personnage je veux une image générer parmis ceux identifier précédemment et dont il
  aura des sources / illustrations fiable, ou me demander un choix personnalisé, ou je
  tapperai la description que je souhaite. Travaille sur une oeuvre autre que roman S comme
  roman N qui a beaucoup plus de contenu. PS les images et illustrations de références ou
  produite ne sont pas seulement par rapport à un volume mais une oeuvre compléte […]
  N'oublie pas d'écrire/mettre à jour la procédure"

### The line this lot had to hold, and where it moved

`bible.yaml` records `confiance: humaine` on a reference, and the repository's rule is that
only a human eye can put it there. This lot moves **where** that review happens — from
`tools/bible.py --revue`, out of context, into the workshop, at the moment someone asks for
the portrait and can see both the image and what it will be used for. It does not move **who**
does it: the workshop asks, and writes to the bible only on an explicit yes.

**The agent did not fabricate a review.** Of 23 characters the automatic pass proposed for the
new work, exactly **one** was reviewed — by opening all nine candidate images and reading every
citation — and the resulting image's sidecar records that in words: *"Claude Code (revue faite
en ouvrant les 9 images et en lisant chaque citation)"*. The other 22 wait for a review that is
not this agent's to give. `sources/roman N/bible.yaml` therefore holds one entry, and the
measurement document says so.

### What the review found, and why it changed the design

That single genuine review is what exposed the third defect. On the character with the most
candidate images, the automatic pass proposed five attributes and **three were wrong** — hair
"sky blue" where the drawings show green (the cited sentence describes a *different*
character), an apparent age of "about two years" for a teenager, and a "white mask" taken from
a sentence describing *passers-by in the street*. The dominant failure mode is **misattribution,
not misdescription**: correct sentences attached to the wrong person.

A single "are these attributes right? y/n" would have left two outcomes: write three errors, or
lose the two correct attributes. The review is now per attribute, with the sentence on screen —
the granularity `tools/bible.py --revue` already had, and which there was no reason to lose by
bringing it closer to where it is useful.

### A result worth recording

With those three attributes rejected, the prompt carried only "green eyes, wearing a plain
coat". **The generated image has the right hair colour anyway** — green, like the
illustrations, although the word appears nowhere in the prompt. It is the clearest confirmation
of what lot 26 measured: the reference images carry identity, the words do not. Rejecting a
false attribute costs nothing; writing one would have cost the likeness.

### Two defects that only a multi-volume work could show

1. **A reference without its volume is ambiguous.** The new work has an `image1` in both Vol.1
   and Vol.2; resolution returned whichever came first, silently, so the image model could
   receive a character from a different volume. References now carry their volume, and the
   ambiguity of already-written bibles is *reported* rather than resolved by luck.
2. **A classification must not depend on a speed flag.** The republished-cover detection was
   first tied to the "don't decode pixels" flag, for cost — and the fix then failed to reach
   the reference selector, the one place it was written for. Cost published instead: dry
   classification of a 98-image work goes from 0.03 s to 1.09 s.

- **Human review:** required before merge. Three points deserve a maintainer's eye:
  1. **The output directory moved** from `build/<Work>/<Volume>/illustrations/` to
     `build/<Work>/illustrations/`. An old `requete.yaml` is neither read nor moved — the run
     names it on screen. This is classed MINOR (no cache invalidated, no command changed, the
     brick is experimental and disarmed) but the line is thin and it is written at the top of
     the changelog entry rather than in a footnote.
  2. **`sources/roman N/bible.yaml` now exists**, written by the workshop during the agent's
     own review of one character. It is gitignored, so it is not committed; it is on the
     maintainer's machine. Redoing or extending that review is the maintainer's call.
  3. **The cache floor (2.0 s) was not verified against a real cache.** Reproducing the
     original defect would mean deliberately interrupting a generation, which costs 22 minutes
     of model reload. It is tested against a stub that answers instantly — same symptom, not
     the same cause.

---

## 2026-09-02 — the workshop in the interface, the door both interfaces walk through (lot 27)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** `PLAN-27`. A GUI "Atelier" tab whose central screen is the **prompt review**, not
  the gallery; keep/reject/purge with a disk inventory; opt-in, captioned insertion of
  retained illustrations into the light-novel outputs. `illustration.actif` and
  `illustration.inserer_dans_sorties` both default to `false`.
- **Prompt:** "Realise le plan 27 dans docs/plans" (see
  `docs/plans/PLAN-27-L-ATELIER-ET-LA-SORTIE.md` for the full specification the session
  worked from).

### The AI Act reading, extended to the visible output

Lot 24 recorded the reading of **Article 50(2)** and its consequence for the code: the
machine-readable marking (`tEXt` block, `AIGenerated=true`, plus a provenance sidecar) has no
configuration key that turns it off. Lot 27 extends the same reading to the **visible**
output, because an illustration can now be placed inside a document a reader opens:

> Every inserted illustration carries, directly beneath it, the sentence *« Illustration
> générée par IA — ne fait pas partie de l'œuvre originale »*, in the target language of the
> volume. `core/insertion.py` **raises** on an empty caption. There is no configuration key,
> no argument and no branch that writes the image marker without it.

⚠ **This remains a reading, not legal advice**, and it is still to be confirmed — the same
caveat as the lot 24 entry. What is settled is the code's behaviour, not the legal question.

### What was measured, and what was not

Nothing was measured on a GPU in this session: no ComfyUI, no image weights, no card. Every
GPU-facing path — the VRAM switch, cancellation, unload, reload — is exercised with **injected
callables** and the fake engine. The per-image figures published by the workshop interface
(103.7 s median, n = 4) are **lot 24-26 measurements, republished with their denominators**,
not new ones. Re-measuring them would have produced a fourth number to reconcile with three
existing ones, which the repository's own figures rule names as the defect to avoid.

The three output formats, on the other hand, were verified for real, with Pandoc 3.10: the
caption is present in the DOCX, the EPUB and the PDF.

### One of the plan's own requirements was narrowed, deliberately

L27.2 asks that "the LLM comes back" after a generation run. Applied literally that would be a
**defect**: reloading ~17 GB of language model while ComfyUI still holds ~12 GB of transformer
is precisely the scenario the architecture rules out. The reload is therefore conditioned on
the image model actually having returned the card — a setting that is itself disarmed by
default. When it does not happen, the brick **says so** instead of staying silent. This is
written in the measurement document (§6) rather than smoothed over.

### A repository property was weakened, and it is written down

`tests/test_imports_briques.py` held that **nobody** imports `illustration/` — "that is what
makes the brick deletable without breaking anything". A workshop tab necessarily creates that
edge from `gui/`. What is preserved and now tested for real: `pipeline/`, `manga/`, `scan/`
and `core/` still do not import it; there is **no module-level import** anywhere in `gui/`;
and a runtime test makes `illustration` unimportable, then builds the whole window, which
shows an empty state explaining why the tab is empty. The replacement property is weaker than
the original, and §7.6 of the measurement document says so.

### A defect in the repository itself, found on the way

The **published** `config.yaml` had been arming the experimental illustration brick since
2.20.0: six working values from one machine entered a commit that was about manga fonts
(`actif`, `moteur`, the ComfyUI workflow and timeout, `identite.actif`, `prompt.llm.actif`).
The repository's own guard, `test_le_defaut_du_depot_est_bien_desarme`, had been failing on
`git show HEAD:config.yaml` since that day. The six values are restored to their 2.19.1 state.

- **Human review:** required before merge. Four points deserve a maintainer's eye:
  1. **The restored configuration disarms a brick you may have been using.** If you relied on
     the file as shipped by 2.20.0, re-arm the keys you want — or keep a working copy and pass
     it with `--config`. Nothing else in the repository changed for you.
  2. **The GUI tab has never been driven by a human against a real corpus.** Lot 26 showed
     that only real use reveals certain defects ("a review in bulk is worth nothing", found on
     the first character reviewed outside a development session). Nothing says this screen has
     no equivalent.
  3. **The character-name placement heuristic is fallible.** It was already corrected once
     while writing its test — "Ai" matched "j'**ai**", because Python's `\w` does not treat the
     apostrophe as a letter. A nickname, a homonym or a name that is also a common word will
     still mis-place; the fallback is named (volume head) and the report says so.
  4. **`--purger` has no undo.** Deletion is permanent, the confirmation states what it will
     destroy, and that is the whole of what the lot promises.

---

## 2026-09-03 — the judge and the corpus: the blind protocol gets tooling, and seven of nine criteria go unmet (lot 29)

- **Tool / model:** Claude Code (claude-opus-5), run on the **secondary PC**.
- **Scope:** `PLAN-29`. New: `illustration/aveugle.py`, `tools/juge_humain.py`, five test
  files, `docs/mesures/identite-2026-09-03.md`. Modified: `core/bible.py`,
  `core/bible_llm.py`, `core/illustrations.py`, `illustration/identite.py`,
  `illustration/gabarits/` (+ `portrait.yaml`), `illustration/prompt.py`,
  `illustration/requete.py`, `illustration/orchestrateur.py`, `illustration/attente.py`,
  `tools/bible.py`, `tools/banc_identite.py`, `tools/banc_prompt.py`. No prompt file under
  `langues/` was touched; no dependency added; `config.yaml` unchanged (same SHA-256 as 2.21.0).
- **Prompt:** "Commit le plan 28 puis réalise le plan 29 dans docs/plans. Attention tu es sur
  le PC secondaire sans GPU ni Comfuy pour les tests réelles."

### What this lot mostly delivers is a documented negative result

Seven of the plan's nine criteria are **not met**, and the measurement document states each
one with its verdict. The cause is the machine — but, unlike lot 28, not only the GPU:
**three** resources were missing. No `bible.yaml` anywhere on this copy (0 files across
17 projects), no encoder weights under `illustration_models/`, and no ComfyUI or card.

⚠ **One consequence deserves a maintainer's attention**, because it is a fault in how the
plans are written rather than in the code: step 0.1 — "recalibrate the unchanged judge" — is
the only step of the lot that **did not need a GPU**. DINOv2 runs on CPU through
`onnxruntime`. It was blocked by the absence of the **weights**, which the repository
deliberately does not download. "Runs on the main PC" is too coarse a condition; future plans
should distinguish *what needs the card* from *what needs the corpus*.

### Three silent defects were found and fixed, all invisible from a machine without a card

1. **The crop field was written under one name and read under another** since 2.14.0 —
   `core/bible_llm.py` wrote `recadrage: []` while `illustration/identite.py` read `cadre`.
   The field the engine reads could never be filled by the toolchain, which partly explains
   why `PLAN-25`'s "nature of the crop" axis went unmeasured **two lots running** with the
   published reason "the field stays empty on the 10 references of the real corpus". No data
   was lost — the written value was always the empty list.
2. **`tools/banc_identite.py --balayage` raised `AttributeError` since 2.18.0**, which renamed
   `requete.depuis_bible` to `depuis_oeuvre` without updating this caller.
3. **Three callers of `orchestrateur.dossier` still passed a `tome`** after 2.19.0 dropped
   that parameter — one in `banc_identite.py`, two in `banc_prompt.py`, each raising
   `TypeError`. `--balayage` therefore carried **two** independent failures at once.

⚠ The real defect is none of the three: it is the **shape of the coverage**. These measurement
tools have a mode that loads weights and a mode that does not, and only the second is tested.
Until the first is split — the part that computes on one side, the part that calls the engine
on the other — the next rename will break the same lines. This lot split one of them and added
a signature-inspection test; the others remain.

### A test changed a line of production code

The blind protocol's image copies used `shutil.copy2`, which copies metadata — **modification
date included**. The copies inherited the source image's date, so a folder sorted by date
revealed the order in which the sweep had generated, i.e. the order of the configurations.
Shuffling the write order achieved nothing while the date followed the file. That is exactly
the leak the plan's rule 2 names, reintroduced by the most natural call in the standard
library.

- **Human review:** required before merge. Five points deserve a maintainer's eye:
  1. **Nothing here has been exercised against a real corpus, a real encoder or a real GPU.**
     The blind protocol has 36 tests proving it counts correctly and does not leak; none
     proves it is *bearable* to answer twenty times in a row. Lot 26 learned that lesson at
     full price ("a review in bulk is worth nothing", found on the first character reviewed
     outside a development session).
  2. **The crop rectangle is an assistance, not an automation**, and the measurement says so:
     across the 402 real illustrations of `build/`, the ink box covers a median **77,5 %** of
     the page and drops below 50 % on **10 images out of 402**. It removes margins, not the
     page. The half-day of human work the plan budgets is not reduced by it.
  3. **The `recadrage` → `cadre` migration has not been run on a real bible.** The alias is
     read and tested; no existing file was opened to confirm.
  4. **The decor lever ships disarmed on purpose.** If you want the part-of-flats measurement,
     it costs a sweep with `--decors neutre,trame,aucun` — and the shipped default must stay
     `neutre` until that measurement designates otherwise.
  5. **The GPU cost figure rests on a sample of one** for the path that matters (editing:
     233,7 s/image). The 5 h 11 min quote is an order of magnitude, not a promise.

---

## 2026-09-03 — the channels that are missing: one channel instrumented, none shipped (lot 30)

- **Tool / model:** Claude Code (claude-opus-5), run on the **secondary PC**, for the third
  lot running.
- **Scope:** `PLAN-30`. New: `illustration/workflows/qwen-image-edit-2511-controle.api.json`,
  `tests/test_illustration_canaux.py`, `docs/mesures/canaux-2026-09-03.md`,
  `docs/plans/A-EXECUTER-SUR-LE-PC-PRINCIPAL-28-30.md`. Modified: `illustration/comfyui.py`,
  `illustration/moteur.py`, `illustration/validation.py`, `illustration/vram.py`,
  `run_illustration.py`, `tools/banc_identite.py`, `config.yaml` (**comments only**),
  `illustration/workflows/README.md`, `docs/procedures/comfyui.md`, `docs/COMMANDES.fr.md`.
  No prompt file under `langues/` was touched; no dependency added.
- **Prompt:** "Realise le plan 30 dans /docs/plan. Tu es sur le PC secondaire donc sans
  Comfuy, GPU et autre du n'a donc pas possibilité de faire de tests réelle. Cela a été le cas
  pour les plan 28 et 29. A la fin du plan 30 en plus du commit sur Main, prépare un MD que je
  pourrais te donner une fois de retour sur le PC principale afin de te faire tester et valider
  les différents points des plan 28 à 30."

### No channel is shipped, and that is the lot's conclusion

The plan required choosing one channel **on its measured contribution**. Contribution can only
be measured with the calibrated judge of `PLAN-29`, which did not deliver its measurements.
On the gaps that *are* measured — proportion of flat areas, line density — **no channel of this
lot is justified**: those two are addressed by the prompt and by the references.

⚠ **This is not a consequence of the machine.** Even run on the main PC, this lot could not
have met criterion 1: it depends on a previous lot that did not deliver. The plan had written
exactly that risk ("if this plan runs before 29 has delivered, it will install weights for a
problem 29 would have fixed with one word"). The consequence was taken rather than worked
around.

What ships is an **instrument**: a candidate graph that declares itself as such, a sweep axis
closed by default, a counted `/free` protocol, and two more named refusals.

### The channel that *is* instrumented was chosen on dependency debt, and it is stated as such

`ModelPatchLoader` and `QwenImageDiffsynthControlnet` are **built into ComfyUI** (verified at
`docs.comfy.org/built-in-nodes/` on 2026-09-03); EliGen requires a **third-party** node
installed on no machine of the repository. The weight
(`qwen_image_canny_diffsynth_controlnet.safetensors`, Comfy-Org) is **Apache-2.0, verified at
the primary source on 2026-09-03**. ⚠ Its SHA-256 is **not** recorded — the file was not
downloaded — and the field says so rather than staying blank.

### One silent defect, found by writing the graph

`%image_controle%` was **not a prunable marker**. Pruning only knew *indexed* markers
(`%reference_2%`, `%masque_3%`), because no shipped graph carried `%image_controle%` — the case
could not occur. Without the fix, a request without a control image would have sent
`LoadImage(image: "")` to ComfyUI, which errors **after** loading the weights. Same pattern as
lot 29's three defects: a path no test reached because no shipped file walked it.

### A piece of the repository's own documentation was wrong

`illustration/workflows/README.md` had advised, since 2.16.0, replacing `SaveImage` with
`SaveImageWebsocket` to avoid the unmarked copy. **This client cannot read that node**: it
fetches the image through `/history` then `/view`, and `SaveImageWebsocket` publishes nothing
to the history. A graph carrying it would run, hold the card for minutes, then fail on "no
image produced". The validator now refuses it before the GPU, and the README carries a dated
block that **lifts** its former advice rather than rewriting it.

- **Human review:** required before merge. Five points deserve a maintainer's eye:
  1. **The candidate graph has never been executed, and it may not work at all.** The
     `MODEL_PATCH` is published for **Qwen-Image** (text-to-image); the graph stacks it on
     **Qwen-Image-Edit-2511 quantised to Q4_1**. Nothing establishes the two are compatible.
     That is the first thing to check on the main PC, and a documented failure there is a
     legitimate outcome.
  2. **The candidate-graph downgrade is a deliberate softening of the validator**, and it is
     worth a second look. Only `noeud_absent`, `modele_absent` and `valeur_absente` become
     reserves, and only on a graph carrying a `_candidat` block; everything else still
     refuses. The reason is that `--valider` with no argument would otherwise go red on every
     machine in the world.
  3. **A sixth validation check adds one reserve to every shipped graph.** It is not a refusal
     and changes no default, but every `--valider` output now carries a line that was not
     there before.
  4. **`config.yaml`'s SHA-256 changed, by comments only.** The value-by-value comparison is in
     `docs/mesures/canaux-2026-09-03.md` §8; it deserves an independent read.
  5. **The `/free` protocol has never been run.** It is tested against injected callables, not
     against a server that segfaults. The figure in force is still 1 in 7, from 2026-08-29.

---

## 2026-09-04 — startup loads nothing: the shell, seven destinations, the volume on demand (lot 31)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `docs/plans/PLAN-31-LE-DEMARRAGE-NE-CHARGE-RIEN.md` in full — step 0
  (0.1, 0.2, 0.3) and steps L31.1 to L31.8.
- **Prompt:** "Realise le plan 31 dans /docs/plans", then, after the first delivery was
  reviewed: *"Les 4 choses trouvé en chemin ont ils été corrigé ? J'arbitre — tu peux ajouter
  des paramètres si nécessaire mais décrit les moi en détails à la fin. Une fois tout cela
  fait, réalise le commit sur la main."* The plan file is committed, so what was asked is
  readable in full; its eleven acceptance criteria are answered one by one in
  `docs/mesures/coquille-2026-09-04.md` §5.
- **The maintainer's arbitration, and what it changed:** the plan contradicts itself — L31.7
  asks for the Webtoon destination "with the format fixed **and the strip settings brought
  up**", while §4 of the same plan forbids adding any run parameter. The first delivery chose
  §4 and shipped the format only. The maintainer arbitrated the other way, so **two run
  parameters are added**: `--fenetre-hauteur` and `--fenetre-recouvrement`, on `run_manga.py`
  **and** in the Webtoon destination. They are declared in `run_manga._appliquer_options_bande`
  — the function whose docstring already says it exists so options are "available identically
  to the graphical interface, which calls the orchestrator without going through this CLI".
  The reading direction and `psd_original` are **displayed and not editable**: changing the
  first on an already-detected volume restarts every plate at detection, which is a cache
  invalidation and therefore interdiction n° 1. Neither new parameter is *measured* on the
  strip corpus: the shipped default stays `2160 / 900`, and nothing in the interface suggests
  touching it.
- **What was changed:** six new modules under `gui/` — `destinations.py` and `sondes.py` (both
  **Qt-free**, both tested without PySide6), `navigation.py`, `accueil.py`, `retouche.py`,
  `oeuvres.py`; `fenetre.py` reworked into a shell that builds one panel at startup instead of
  three and opens no volume at all; `lanceur.py` takes a fixed brick and format; `actions.py`
  gains a "Aller à" menu derived from the destinations table; `reglages.py` goes to format
  version 2 (`onglet` → `destination`, per-destination `runs`, `recents`); `travailleur.py`
  gains `GENRE_SONDE` and narrows `touche_tout()`; `icones.py` goes from 12 to 22 glyphs;
  `tools/mesure_demarrage.py` and `tools/compte_sans_pyside.py` are new; `tools/captures_gui.py`
  captures four screens instead of two; `run_manga.py` gains `--fenetre-hauteur` and
  `--fenetre-recouvrement` (see the arbitration above). Four new test files (**81 tests**, of
  which **62 need neither Qt nor a model nor a network**) plus 33 tests added to existing
  files — **114 in total**; the test count remeasured and synchronised across `README.md`,
  `CONTRIBUTING.md`, `docs/COMMANDES.fr.md` and `docs/chiffres-de-reference.md`;
  `docs/roadmap.md` brought up to date after seventeen stale releases;
  `docs/mesures/coquille-2026-09-04.md`. A dated block was added to
  `docs/plans/PLAN-34-…md`, whose step 0 cites as a *precedent* the lot-27 claim this lot
  measured false.
- **What was *not* changed:** no prompt, no threshold, no pipeline stage, no output format, no
  key of `config.yaml` (**fingerprint unchanged**), no cache format, no `STAGES`, no
  `FORMAT_VERSION`, no file under `sources/` or `build/`. `gui/editeur.py` is untouched — the
  plan puts it out of scope, and the volume/tome bar was moved into a **wrapper**
  (`gui/retouche.py`) rather than grafted onto it.
- **What the measurement found, and it was not in the plan:**
  1. **A claim the repository made about itself was false.** Lot 27 wrote, in `gui/fenetre.py`,
     that `PanneauAtelier`'s constructor "loads no weight […] a user who never opens the tab
     pays nothing". Its constructor reads `sources/<Project>/glossaire.yaml` through
     `illustration.orchestrateur._glossaire` — **26.9 KB of YAML at every startup**, for a tab
     nobody had opened. True of the intent, false of the code. Now true, and guarded by a test.
  2. **The window ignored the size it was asked for, and nothing said so.** `PanneauEditeur`
     accumulates the minimum widths of its three columns; the editor being built at startup,
     the whole window carried that minimum **from the first pixel**. Measured on a real
     2 560 × 1 440 screen, on a worktree at `1e41504`: 2.24.1 opened at **2 016 × 981** and
     `resize(1520, 960)` — the default of `gui/reglages.py` — was silently ignored. 2.25.0
     opens at **1 520 × 960**, because only the displayed page constrains the window now.
     ⚠ The price is real and it is written: opening the Retouche widens the window to
     **2 214 px** against 2 016 before — the 198 px of the navigation pane. And the source is
     **not** fixed: it is in `gui/editeur.py`, which the plan puts out of scope (§4).
     ⚠ An earlier draft of the measurement quoted 3 395 / 3 583 px here. Those were
     **offscreen** figures, and offscreen has zero font families on this machine, so every
     text-driven minimum is inflated. Both columns are now published side by side, and the
     native one is the one that describes what a user sees.
  3. **The "hole" the plan announced does not open.** `PLAN-31` warned that leaving the retouche
     by changing destination would be unguarded, and `PLAN-35` L35.4 was to close it. Panels
     live in a `QStackedWidget`: leaving one hides it, drafts survive. The only gesture that
     discards work is still opening another volume, and it still goes through the same
     three-choice box. Written up in §4.1 — with the caveat that the property holds *because*
     panels are kept, and a later lot that destroyed them would reopen the hole.
  4. **A defect in the test harness, invisible by construction.** Fixtures stopped the worker
     thread with `wait(2000)`; the network probe holds it for up to 2 s, so Python exited with
     a live `QThread` and the process died on `STATUS_STACK_BUFFER_OVERRUN` (0xC0000409)
     **with no output at all** — a 69-test file looked mute, not red.
  5. **`Fenetre._fabriquer_action` could not wire a non-toggle entry carrying data.** The case
     had never existed; the seven destination shortcuts raised `TypeError` *inside a Qt slot*,
     i.e. on the console and not on screen. The shortcut simply did nothing.
- **What is *not* met, and it is written rather than fixed silently:** the `MINIMAL` mode of
  the side navigation (≤ 640 px) is unreachable in practice — the narrowest page of the
  software already asks for 832 px. That is the only criterion left unmet; "the strip settings
  brought up" was the second, and the maintainer's arbitration turned it into a delivery. Both
  are argued in `docs/mesures/coquille-2026-09-04.md` §6.
- **What the measurement does not say:** nothing about a cold disk (all timings are warm),
  nothing about real painting (`offscreen`), nothing about another machine or another corpus,
  and **nothing about whether seven destinations navigate better than three tabs** — that needs
  someone in front of the screen, and it is the verdict `core/version.py` has been reserving
  since 2.0.0 to say whether the interface is mature.
- **Human review:** required before merge. Four points deserve a maintainer's eye:
  1. **`.angelith/interface.json` is dropped once.** Format version 2, and a version-1 file is
     ignored wholesale — the behaviour the module has promised since lot 18, and there is
     deliberately no migration (converting `onglet: 0` would mean reopening a volume at
     startup, which is what the whole lot exists to stop). Window size, columns, filter and run
     settings go back to defaults **one time**.
  2. **`Ctrl+Tab` changes meaning**, from "next tab" to "next destination", and the accueil
     takes `Ctrl+Maj+A` rather than `Ctrl+1` — the plan's own two sentences were in tension and
     the arbitration is written in §3.
  3. **Three run parameters are born** — `format_planche` (reaching `tache_run` and
     `process_volume`), plus `--fenetre-hauteur` and `--fenetre-recouvrement` after the
     arbitration. All three are described at length in the session's closing message and in
     `docs/mesures/coquille-2026-09-04.md` §6.2.
  4. **The window now resizes itself** when a destination needs more width than the current
     window (`_contraindre_a_la_page_courante`). It reproduces what 2.24.1 did permanently, but
     it does it *at the moment one opens the retouche*, which is visible.

---

## 2026-09-04 — two repository guard-rails died on a Windows console (2.25.1)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** a correctif found while running lot 31's own delivery checks — not planned work.
- **Prompt:** "fait le correctif et push le", after the session reported that
  `tools/verifier_disclosure.py` crashed on a cp1252 console and offered a separate fix.
- **What was changed:** `tools/verifier_disclosure.py`, `tools/sonar_issues.py`,
  `tools/verifier_arbre.py`, `tools/verifier_livraison.py` and `tools/notes_de_version.py` now
  reconfigure **stdout and stderr** to UTF-8 at the top of `main()`; new
  `tests/test_outils_sortie.py` (18 tests); CHANGELOG entry and version bump.
- **What was *not* changed:** nothing under `gui/`, `manga/`, `pipeline/`, `core/`, `langues/`
  or `templates/`. No prompt, no threshold, no output format, no `config.yaml` key (fingerprint
  unchanged), no cache format. The tools' *logic* is untouched — only the encoding of the
  stream they print to.
- **What the measurement said, and it decided the shape of the fix:** every tool in `tools/`
  was run under `PYTHONIOENCODING=cp1252`. Exactly **two of ten** fell, both on `⚠` (U+26A0):
  `verifier_disclosure.py` on its verdict, `sonar_issues.py` on its `--help`. The obvious fix —
  call the shared `core.cli.configurer_stdout()`, as nineteen other tools do — **would have
  broken the CI job**: `core/cli.py` imports `yaml`, and `.github/workflows/garde-fous.yml`
  contains no `pip install` at all. Hence four repeated lines rather than one shared call, the
  reason written at each site, and a test that pins both the repetition and the constraint that
  forces it.
- **What is worth a second look:** three of the five tools did **not** fall and were changed
  anyway. The argument is that they run in the same dependency-free job, write to the same CI
  summary, and were one `⚠` away from the same crash. That is prevention inside a correctif,
  and a reviewer may legitimately want it split out.
- **Human review:** required before merge. The behavioural change is narrow but real: these
  five tools now emit UTF-8 where they emitted the console codepage. In CI that is what the
  step summary wants; in a local terminal it means accented output renders correctly instead of
  being mangled or fatal.

## 2026-09-06 — packaging: `pyproject.toml`, a frozen folder, an installer, a tested artefact (lot 37)

- **Tool / model:** Claude Code (Anthropic), `claude-opus-5`
- **Scope:** executing `docs/plans/PLAN-37-L-EMPAQUETAGE.md` end to end on the main PC — the
  step-0 weighing of four dependency sets, the product-form decision, `pyproject.toml` with a
  dynamically read version, the single path resolver that knows `sys._MEIPASS`, the
  `config.yaml` resolution for a frozen install, `angelith.spec` (one-folder), the Inno Setup
  installer, the opt-in version check, and the CI job that builds and **tests** the artefact.
- **Prompt:** "Réalise le plan 37 dans /docs/plans et push sur la main", referring to the plan
  document, itself preceded by `00-CONTEXTE-AGENT.md` and `README-INTERFACE-31-37.md`.
- **What was changed:** five new modules (`core/installation.py`, `core/maj.py`,
  `gui/lancement.py`, `tools/verifier_gel.py`, `installeur/generer.py`), `pyproject.toml`,
  `angelith.spec`, `installeur/angelith.iss`, a CI job, six test files, and one measurement
  document. The five `requirements-*.txt` became wrappers around the extras. `config.yaml`
  gained one disarmed section (`maj:`).
- **Measurements actually run on this machine, not asserted:** four clean virtual environments
  built and weighed; three PyInstaller freezes built, launched and timed; the installer
  compiled (231.9 s), installed silently, launched, and uninstalled — with five witness files
  proving no user data is removed; Windows Defender run against both freezes and the installer
  with its engine and signature versions recorded.
- **What is worth a second look:**
  - **the product-form decision** (ship `manga-ocr`, so `torch`, so 916.5 MB frozen) rests on
    two failed experiments and one corpus count. Both are published; a maintainer who weighs
    download size differently has a one-line change and the number to argue with;
  - **the requirements wrappers** change a documented command's behaviour: `pip install -r`
    now also installs `angelith` editable and must be run from the repository root. This is
    stated at the top of the CHANGELOG entry rather than hidden;
  - **the `MAX_PATH` failure** found while testing the installer is documented and **not
    fixed** — the fix would mean either stripping third-party licence texts from a
    redistributed package, or requiring a system setting;
  - **the multi-engine antivirus rate is not measured.** Submitting a binary to VirusTotal
    publishes it to a third-party sample repository; the decision was put to the maintainer and
    declined.
- **Human review:** required before merge. The lot ships a distribution channel — an
  executable that other people will run on their machines — and three of its criteria are only
  partially held (see `docs/mesures/empaquetage-2026-09-06.md` §8). The CI job has never run on
  a GitHub runner; its three checks were replayed by hand on this machine.

---

## Template for new entries

```markdown
## YYYY-MM-DD — short title

- **Tool / model:**
- **Scope:**
- **Prompt:**
- **What was changed:**
- **Human review:**
```
