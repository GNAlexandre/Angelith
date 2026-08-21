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

## Template for new entries

```markdown
## YYYY-MM-DD — short title

- **Tool / model:**
- **Scope:**
- **Prompt:**
- **What was changed:**
- **Human review:**
```
