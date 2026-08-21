# Roadmap

## How version numbers work here

This project's `MAJOR` means one specific thing, and the CHANGELOG promises it:

> **A `MAJOR` release means the user must delete `build/` or edit `config.yaml` before
> re-running the same command.**

A new capability that invalidates no cache and breaks no configuration key is a `MINOR`,
however large it is. Adding menus to the graphical interface breaks nothing, so it is not a
`3.0.0`. This is why the milestones below are not numbered by how impressive they are.

Current version: **1.8.0**.

## Planned

| Version | Milestone | Why this number |
|---|---|---|
| **1.8.0** | Language-pack architecture; behaviour unchanged for `cible: fr` | MINOR — new capability, no cache invalidated |
| **1.9.0** | Typography externalised, complete `fr` pack | MINOR |
| **2.0.0** | English pack, **multi-target glossary**, **direct live editing in the interface** | **MAJOR, and the only one planned** — the glossary schema changes, so caches are invalidated and a migration is required |
| **2.1.0** | Menus and project management in the interface (functional, not necessarily beautiful) | MINOR |
| **2.2.0** | Glossary and project import/export, drag and drop | MINOR |
| **2.3.0** | Automatic detection, installation and deployment of language models | MINOR |
| **2.4.0** | One-click Windows/Linux packaging, English documentation, accessibility pass | MINOR |

**There is deliberately no 3.0.0 on this list.** A `MAJOR` is *observed* when a piece of work
turns out to break a cache or a configuration key. Reserving one in advance would invert the
rule above and make the number meaningless.

## Out of scope for now

Kept on the list, not scheduled:

- webtoon (vertical scroll) format
- onomatopoeia genuinely re-lettered rather than detected and reported — this is heavy R&D,
  and the current honest default is `manga.onomatopees.mode: "rapport"`
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
