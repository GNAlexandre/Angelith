# Roadmap

## How version numbers work here

This project's `MAJOR` means one specific thing, and the CHANGELOG promises it:

> **A `MAJOR` release means the user must delete `build/` or edit `config.yaml` before
> re-running the same command.**

A new capability that invalidates no cache and breaks no configuration key is a `MINOR`,
however large it is. Adding menus to the graphical interface breaks nothing, so it is not a
`3.0.0`. This is why the milestones below are not numbered by how impressive they are.

Current **released** version: **2.27.0** (2026-09-05) — the single source of truth is
[`core/version.py`](../core/version.py), and `tests/test_version.py` checks it against the
first dated entry of the CHANGELOG. Every commit message carries its version in front —
`[X.Y.Z]` — so the graph shows the milestones without opening this file.

> ⚠ **This file was stale, and said so nowhere.** It announced 2.7.0 while `core/version.py`
> said 2.24.1, and its *Shipped* table stopped at 2.8.0 — seventeen releases behind. A
> planning document that is wrong is worse than one that is absent, so the rule from now on is
> the repository's own: **a claim about state carries its date**. This one is dated
> **2026-09-05**, and the CHANGELOG is what it defers to for everything between 2.9.0 and
> 2.24.1.
>
> ⚠ **Updated 2026-09-06.** Current released version: **2.31.0**. The header above was itself
> two lots behind within a day of being written, which is the point it was making: a state
> claim without a date rots, and this one now carries two.
>
> ⚠ **Updated 2026-09-06, later the same day (lot 40).** Current released version: **2.34.0** —
> the line above was stale again after three more lots, and it is lifted rather than rewritten,
> for the third time in this block. That is now the evidence, not the claim: **this file cannot
> be trusted to hold a version number.** The CHANGELOG is the only thing that carries one
> correctly, because it is the file a release cannot be cut without touching. Three lots landed
> since: 2.32.0 (one-command freeze, weight licences single-sourced), 2.33.0 (Angelith runs
> without an LLM server), 2.34.0 (light novel creation, importing a corrected volume, and
> update checking — **armed by default**, which lifts a 2.31.0 decision by a dated block of its
> own).

## Shipped

| Version | Milestone |
|---|---|
| **1.9.0** | Language-pack resolver, typography externalised, complete `fr` pack; behaviour unchanged for `cible: fr` |
| **2.0.0** | English pack, **multi-target glossary** (MAJOR — the schema changes and a migration is required), direct live editing in the interface |
| **2.1.0** | **The measurement bench** — `tools/banc.py`, an annotated corpus that ships with the repository, a CI job that breaks the build if recall drops or false positives rise |
| **2.2.0** | **Reconnecting what was already written** — the work-context sheet reaching the default translation path, the language pack reaching the single-bubble retry, one character budget for both paths, one CJK class |
| **2.3.0** | Out-of-bubble text (onomatopoeia, free narration) detected, read and reported **by default** — nothing is drawn on the plates |
| **2.4.0** | **No more silent plates** — the input resolution becomes configurable, a plate that returns zero bubbles while carrying ink gets a second, more sensitive inference, and the arbiter decides. Measured: **188 → 153** zero-bubble plates across ten volumes, 47 bubbles gained, **zero regressions** |
| **2.5.0** | **Double bubbles and out-of-bubble text read backwards** — the split criterion goes after the 33 suspect two-lobed regions the reports had been naming since lot 4.2, and the out-of-bubble sort finally honours the format's reading direction instead of being hard-coded right-to-left |
| **2.6.0** | **The webtoon, measured** — false detections on the 9 reference strips fall from **22.0 % to 15.1–17.0 %** with **no real bubble lost**; resident memory becomes a measured figure for the first time (`perf.log` + `RAPPORT.md`, no new dependency); the windowing cliff becomes a detectability criterion that follows `input_size`; the PSD size limit is refused cleanly instead of written corrupt. **Three settings the plan asked for are shipped disarmed, measurement in hand** |
| **2.7.0** | **The translator stops working blind** — the plate's own structure reaches the prompt: layout groups, bubble type and a probable speaker, all deterministic and **without a single LLM call**. The rule that governs the lot is *claim nothing you do not know*: across **7 862 bubbles** in ten volumes, **86.2 % stay untyped**, and that is the figure to watch. Sixteen hard-coded French instructions leave Python for the language packs — **before** the prompt is enriched, not after. Two silent defects are closed: a batch's images were paired to plates **positionally** and slid by one whenever a plate had none, and the inter-plate context threw away whole plates. A seventh failure motive finally bounds replies **from below** |

| **2.25.0** | **Startup loads nothing** — the interface used to *open* the first project in alphabetical order before showing a single pixel: a `Tome` read, a `Services` built, previews composed. Measured on the real corpus: **1.89 s → 0.13 s** to first pixel, **692 → 1** file opened, **311 → 106 MB** of peak memory, and zero volume, zero glossary, zero preview. Three tabs become **seven destinations** in a side navigation (Fluent `NavigationView`: 5-10 destinations, thresholds at 1008 px and 641 px), each one a **factory** built on first display. The volume becomes a gesture: `dernier_projet` is still persisted, it now feeds a *Resume* card. Three installation probes run **off the display thread** and the home page shows three states, not two. And a claim the repository made about itself turned out false — the illustration workshop's constructor *did* read a 26.9 KB glossary at startup. See [coquille-2026-09-04.md](mesures/coquille-2026-09-04.md), which walks the plan's eleven criteria one by one, including the two that are not met |
| **2.28.0** | **The library of works** — the interface had no place that answered *where do my works stand?*: the only inventory was `run_manga.py --list`, in a console, and the glossary — the project's **first differentiator**, shared novel ↔ manga — could be imported, merged and optimised but **never exported**. Both are closed by **one model, two displays**: the CLI and the new *Works* destination read the same `bibliotheque.py`, and the console output is **iso**, compared line by line across the corpus. The corpus itself turned out to be **18 works, not the 17 every plan in the series repeats** — 55 volumes, 3 493 source plates and pages, 14 glossaries, 791 entries — and one volume carries **two bricks** at once, which the plan's data model could not express. The plan also asked for the model to live in `core/`; two existing tests forbid it, and the first version of the lot **failed them** — the aggregator of the four bricks belongs above them, not in the foundation. The sweep costs **1.25 s** for the whole corpus after **78 % of its system calls were removed** (`os.stat`: 13 667 → 1 151), three of which were pre-existing defects that also make `--list` and the editor cheaper — **without changing a single verdict**. The cache the plan asked for beyond one second is **deliberately not shipped**: the only affordable invalidation key is wrong, and a cache that says *up to date* on a volume just corrected by hand is worse than a one-second sweep. Glossary export ships with **one archive format and two views**, and the difference is written **inside the files**: the YAML round-trip is tested on the **14 real glossaries**, the CSV names what it drops. Writing that export exposed two defects in the importer, including a `.csv` path the interface had been advertising since lot 18 and that raised *unsupported format*. No thumbnails, ever: these are copyrighted works. See [bibliotheque-2026-09-05.md](mesures/bibliotheque-2026-09-05.md), which walks the plan's twelve criteria one by one, including the two that are not met |
| **2.27.0** | **The four launchers** — the graphical interface was **the only one of the three** that could not start a night run, in a repository with a branch named `run-de-nuit-v1.7.0`. It now can: keep-awake, shutdown with a named delay, and a countdown that is **visible in the run banner and cancellable without hunting for it** — no modal, per the previous lot's rule. Run parameters stop being written by hand: **nineteen declared parameters** in a Qt-free table feed **one** form generator for all four launch destinations, and `tools/inventaire_drapeaux.py` cross-checks them against the four CLIs by AST introspection — **93 arguments, 24 in the form, 26 elsewhere in the interface, 43 deliberately absent with a written motive, 0 unclassified**. The plan's own hand-made count was wrong by eleven, in the two ways a hand-made count always is: it missed nine flags that are not written where it was looking (`cli.ajouter_flags_veille`), and it had aged by two. A model selector reads `GET /v1/models` and **refuses to promise what the endpoint does not say** — 384 bytes and four names, no vision capability, no context window; the interface prints *unknown*, warns when the manga brick depends on it, and never filters the list on a guess. The scan brick stays out, **in writing**: it is beta, and its only published measurement is a throughput. See [lanceurs-2026-09-05.md](mesures/lanceurs-2026-09-05.md), which walks the plan's thirteen criteria one by one, including the two that are not met |
| **2.26.0** | **The run watches itself** — the progress bar used to *go backwards*, and the repository now has the figure: replayed over the 24 `perf.log` files of `build/` (36 real runs), a 25-chapter light novel run showed **66 regressions**, **6 distinct denominators**, and **89.7 % of a twelve-hour run with no time estimate at all**. A Qt-free progression model (`core/progression.py`) makes the fraction **monotone by construction**; the `Reporter` protocol gains two channels — a `phase` and a named object — both **silent on the console**, byte for byte. A run banner, owned by the window, is visible from all seven destinations, names the phase, the object and the time remaining, and goes **indeterminate rather than lie** in the three cases where nothing is countable. The window title carries the count for the taskbar; `QtWinExtras` is gone from Qt 6, so the answer to the taskbar question is a documented **no**. And the measurement said **no** to the plan's own premise: only **one phase out of six** carries a usable time weight, so the weights ship **disarmed** and the percentage disappears from the screen rather than stay false. See [progression-2026-09-05.md](mesures/progression-2026-09-05.md) |
| … | *2.9.0 to 2.24.1 — see the [CHANGELOG](../CHANGELOG.md). This table was left stale for seventeen releases; it is not reconstructed retroactively, because a summary written a month late is a summary nobody measured* |
| **2.8.0** | **The two Apache-2.0 candidates, measured** — before fine-tuning anything, the two public weights trained on webtoon are run against the detector in place, at equal input size, on the real corpus. Neither replaces it: on the nine reference strips the rate of bubbles with no OCR text is **13.2 %** (current), **13.8 %** and **11.1 %**. And the candidate that recovers **52 of the 188 mute plates** turns out not to detect balloons at all — a hand-labelled sample of **12 plates and 33 regions** contains **zero**; 22 are out-of-bubble story text. Its own weights said so (`text_bubble` / `text_free`), its model card did not. **The four abandonment thresholds are written before the first training run**, which has not happened |

> **What 1.9.0 actually delivered:** the resolver, the `fr` pack, and the externalisation of
> every language-dependent artefact *except the glossary*. A non-French pack is functional
> today; only its glossary agreement stays French — and **sixteen** instructions turned out to
> be hard-coded in Python rather than living in `prompts/`, which the coupling inventory now
> lists site by site. See [inventaire-couplage-fr.md](mesures/inventaire-couplage-fr.md).
>
> **2.7.0 closed the manga half of that list**, and closed it *before* adding to the prompt:
> the ten sites of §5.2 now live in `manga/consignes.py`, overridable key by key, and the
> eleven the lot needed were written there from the start. What stays coupled is named in
> the inventory: the SOURCE language name (`core/glossary_lang.py:NOMS`) still comes out in
> French whatever the pack.

## Planned

**In order, without pinned numbers** — and that is deliberate. This document used to reserve
`2.1.0` … `2.4.0` for the items below, and every lot that shipped in between forced a
renumbering of milestones nobody had started. A version number describes *what a release did
to the user*, so it can only be assigned when the work exists.

| Milestone | Why it is a MINOR |
|---|---|
| ~~Menus and project management in the interface~~ — **the shell shipped in 2.25.0**; project management proper is still ahead (works library, glossary export) | adds capability, breaks no cache and no configuration key |
| ~~Glossary and project import/export, drag and drop~~ — glossary export shipped in 2.32.0; **volume import/export shipped in 2.34.0** (`import_build.py`: hand a `build/` folder to a proofreader, get the corrections back, nothing deleted, nothing overwritten without a backup, and a version guard that refuses a cache whose region order would land translations in the wrong bubbles). Drag and drop covers plates, novels (`.pdf`, `.epub`) and glossaries | same |
| ~~Model selection in the interface~~ — **shipped in 2.27.0** (a per-run override, in memory, `config.yaml` untouched). ~~Detection, installation and deployment of models~~ — **shipped in 2.30.0**, and exactly as this line demanded: a structured diagnostic that says what is missing, what it costs and what to do; a separate gesture per repair, with **explicit consent, the licence shown before the click, and a provenance record (URL, date, size, SHA-256) written after**. ⚠ Angelith redistributes no weights and installs no system software | same |
| ~~One-click **Windows** packaging~~ — **shipped in 2.31.0**: `pyproject.toml`, a PyInstaller **one-folder** freeze, a per-user Inno Setup installer that removes no data on uninstall, and a CI job that **tests the frozen binary** (version, structured diagnostic, window opens on the home screen without loading a volume). ⚠ **Linux packaging is NOT shipped**, and the blocker is named: a `.spec` has never been exercised on a Linux runner, and Inno Setup does not exist there — see `docs/mesures/empaquetage-2026-09-06.md` §9. ⚠ No certificate signs the binaries: SmartScreen will warn, and the installer says so on screen 1. English documentation and the accessibility pass are still ahead | same |

## How progress is measured

Since 2.1.0, detection and translation quality are **measured against a published baseline**,
not asserted. `tools/banc.py` aggregates every volume in `build/` into a dated table (date,
commit, SHA-256 of `config.yaml`), and a CI job breaks the build if recall drops or false
positives rise on the annotated corpus that ships with the repository.

A milestone that claims to improve detection is expected to publish its before/after table.
See [banc-de-mesure.md](procedures/banc-de-mesure.md). 2.4.0 published
[escalade-2026-08-25.md](mesures/escalade-2026-08-25.md) against the 2026-08-25 baseline — including
what the measurement does *not* say, which is the half that makes a table trustworthy.
2.6.0 published [webtoon-2026-08-26.md](mesures/webtoon-2026-08-26.md), which goes further: it names
**four claims the repository itself was making that turned out to be false**, and it ships
three of the lot's own settings **disarmed** because the measurement did not support arming
them. A table that only ever confirms the plan is not a measurement.

**There is deliberately no 3.0.0 on this list.** A `MAJOR` is *observed* when a piece of work
turns out to break a cache or a configuration key. Reserving one in advance would invert the
rule above and make the number meaningless.

## Out of scope for now

Kept on the list, not scheduled:

- webtoon (vertical scroll) format — ⚠ *partly done, and the honest status is written down.*
  2.6.0 measured it end to end ([webtoon-2026-08-26.md](mesures/webtoon-2026-08-26.md)): the format
  runs, false detections fell from 22 % to 15–17 %, and the memory figure now exists. What is
  **not** done is the target of under 5 %, which needs either a detector trained on webtoon or
  a corpus that separates the format effect from the OCR effect — the single strip volume in
  the repository is also its only Latin-source volume, so the two are confounded.
  **2.8.0 closed one of the two escape routes**: no public Apache-2.0 weight fixes it
  ([detecteurs-candidats-2026-08-26.md](mesures/detecteurs-candidats-2026-08-26.md)), so the remaining
  route is a fine-tuned detector — whose four abandonment thresholds are now written
  ([seuils-affinage-detecteur.md](mesures/seuils-affinage-detecteur.md)) and whose training has not
  started
- onomatopoeia genuinely re-lettered rather than detected and reported — this is heavy R&D,
  and the current honest default is `manga.onomatopees.mode: "rapport"`.
  **2.12.0 put a number behind that default** ([sfx-2026-08-28.md](mesures/sfx-2026-08-28.md)): on
  60 zones drawn at random (seed 21) and transcribed one by one, `manga-ocr` is exact on
  **14.6 %** of the readings that feed the LLM, and "plausible but wrong" on 51.2 %. It reads
  printed narration (4 of 9) and almost never a stylised onomatopoeia (2 of 14). Detection is
  not reliable either at the zone level: only 14 of the 60 zones are an onomatopoeia, 16 carry
  no text at all, and 14 are aggregates that swallow a bubble — the latter confirmed
  independently at **25.7 % of all 2 456 zones**. Two things now exist that did not:
  a `lecture_sure` / `lecture_douteuse` flag decided by **concordance between two independent
  readings**, and the local-background uniformity distribution that decides how far
  re-lettering can go without a generative model (53.2 % above 0.60, 36.2 % in the ambiguous
  band, 10.6 % below 0.35 — a mass in the middle, so two code paths, not one)
- macOS support
- taking the scan pipeline out of beta, which needs a second print run to measure against

## The one that matters

**2.0.0 is the point of the current effort.** Today Angelith translates *into French only* —
the eight agent prompts, the typographic rules and the document templates are all
French-specific. That is a structural limitation, not an oversight, and turning it into a
language-pack architecture that a native speaker can extend without touching the engine is the
single most valuable thing this project can do.

The hard part is not adding a directory. It is keeping French output bit-identical while making
the prompts language-parametric, generalising a grammar-aware glossary that **refuses a
replacement rather than producing a wrong one**, and migrating an accumulated glossary without
invalidating work that cost hours of GPU time to produce.
