# Style guide — general translation conventions

Conventions **stable across every project and every volume**. Read by the terminologist,
translator, copy-editor and layout agents. This file is **generic**: it must never contain a
character name, a place name or a line of dialogue from any particular work — only rules of
form, applicable to any light novel. Anything specific to a work (names, genders, nicknames)
belongs in its `glossaire.yaml`, never here.

## Register and tense
- **Narration**: simple past by default, past progressive for action in progress or habitual
  states, past perfect for anything anterior. Correct any present tense left in narration.
  > ⚠ English has no separate literary past tense. The distinction here is **aspect**, not
  > register: do not turn every simple past into a progressive to sound more literary.
- **Casual dialogue**: present and present perfect are fine, as is contraction.
- **Attribution verbs** in the simple past (he said, she asked, X replied, X nodded, X sighed…).
  **No inversion** — `he said`, never *said-he*. Both `"Go!" she shouted` and
  `"Go!" shouted the girl` are correct; pick whichever reads better and stay consistent.

## Punctuation
- **Double quotes for dialogue**: `"…"`, single quotes for a quote inside a quote: `'…'`.
  Never French `« … »`.
- **Typographic quotes and apostrophes** (`"`, `"`, `'`) — never the straight ASCII versions.
- **Em dash** `—` unspaced for interruption and aside: `he turned—too late.`
- **No serial comma** by default; keep one only where its absence creates a genuine ambiguity.
- **Ellipsis** as the single character `…`, not three periods.

## Three paragraph registers (→ three styles)
1. **Narration** → style **"Body Text"**.
   All the story, including descriptive passages with narrative attribution.
2. **Dialogue** → style **"List Paragraph"**.
   A line spoken by a character, with or without an attribution verb, on ITS OWN line.
   See `dialogue_dash_in_text` in config.yaml for whether a dash opens the line.
3. **Inner thought** → style **"Thought"** (automatic italics).
   Interior monologue, often an immediate reaction, with no listener, on its own line.

## Special cases
- **Drop cap**: the **first word or phrase** of the chapter, whatever it is, in **bold**.
- **Game-menu boxes** (status, achievement, crafting recipe) → style **"Body Text"** + bold + italic.
- **Occasional inline italics** (emphasis inside a paragraph of another style): `*word*` in Markdown.

## Recurring translation traps
- **Dropped subjects and unmarked gender.** Japanese omits both. Infer the referent, then stay
  consistent across the whole passage — a character who is "he" must not drift to "they".
- **Articles and number.** Japanese marks neither: `a`/`an`/`the` and singular/plural are
  decisions to make deliberately, and the two things most often lost when copying a draft.
- **Honorifics.** Follow the glossary: keep `-san`/`-kun`/`-sama` if the retained name carries
  one, add nothing if it does not, and never substitute "Mr."/"Miss" for one.
- Mishandled negation and ellipsis.
- Japanese onomatopoeia left romanised in fan translations → an established English sound effect.
- Duplicates (the same sentence emitted twice) → keep the better version.
- Lines split mid-sentence → rejoin them.

## Splitting
- Respect the paragraph breaks of the reference original, without ever losing content.

<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Copyright (C) 2026 Alexandre Tournel
-->
