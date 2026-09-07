# Contributing to Angelith

Thanks for considering it. This project has one maintainer, so a short issue before a large
pull request will save you time.

## Running the tests

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt          # pytest + psd-tools + pytest-cov
python -m pytest -q                          # 5 076 tests (2026-09-06), no LLM call required
```

No test needs a real model: the agents are simulated. If a test needs a network connection or
a GPU, it is a bug in the test.

**One system dependency: a Japanese font.** The manga test fixture draws a synthetic page with
one, resolved by `tools/polices.py` — first `ANGELITH_POLICE_JP`, then a per-platform candidate
list. Windows ships `msgothic.ttc`; on Linux, `sudo apt-get install -y fonts-noto-cjk`.
Without one, `tests/test_fixture_police.py` **fails** rather than skipping, on purpose: the old
skip silently removed the entire detection/OCR/orchestrator coverage and left the suite green.

Run the suite after **any** change to pipeline code or to a prompt, and before opening a pull
request. A full run on a real volume takes hours; the suite takes seconds and catches most of
what that run would have found.

```bash
python run.py --check                        # diagnose an installation
```

Coverage, if you need the figure SonarQube Cloud publishes — the exact command the CI runs is
in [docs/COMMANDES.fr.md](docs/COMMANDES.fr.md), and the targets live in `.coveragerc`.

⚠ **If you add a top-level package**, add it to `sonar.sources` in
`sonar-project.properties` as well. That list is enumerated rather than written
`sonar.sources=.` on purpose: this repository has a `sources/` directory holding the works
being translated, which has nothing to do with `sonar.sources` and must stay excluded. The
price of avoiding that collision is one line to maintain by hand.

## Adding a target language

This is the contribution the project most wants, and it is deliberately **not** a code change:
a language pack is a directory of data. The architecture lands over 1.8.0–2.0.0 — see
[docs/roadmap.md](docs/roadmap.md). Until 1.9.0 ships, ask in an issue before starting, because
the pack layout is still moving.

The goal is explicit: a German or Polish pack should come from someone who speaks German or
Polish, not from the maintainer.

## The prompts are source code

Files under `prompts/` are not documentation. They are the source code of the translation's
voice, and changing one changes the output of every future run. Treat a prompt edit as a
behavioural change: say what you measured, on what, and against what baseline.

The licence header in a prompt file sits at the **end**, never at the top — a model reads the
top of the file as an instruction.

## Versioning

`MAJOR` means one thing here: **the user must delete `build/` or edit `config.yaml` before
re-running the same command.** A new capability that invalidates no cache is a `MINOR`, however
large it is. Adding menus to a GUI is not a major version.

## Commit convention — AI-assisted contributions

This project is developed with AI assistance and discloses it. If you use a generative model to
produce code, the commit message must carry the model, the date, and the prompt:

```
feat(langues): résolveur de pack de langue

Assisté par : Claude Code (claude-opus-5), 2026-08-22
Prompt : « implémente core/langues.py selon PLAN-01 étape 2, sans
modifier le comportement pour cible=fr »
Revu et testé manuellement : oui
```

When the prompt is too long for a commit message, record the session in
[docs/ai-provenance.md](docs/ai-provenance.md) and reference it.

Undisclosed AI authorship is treated as a defect. Purely AI-generated contributions that
nobody has read and tested are not accepted — the line that matters is not "was a model
involved" but "did a human review this and can they defend it".

**A commit written by hand is legitimate, and says so**: `Assisté par : aucun`. An absent line
is not a declaration — it does not distinguish "hand-written" from "forgotten".

`Revu et testé manuellement : non` is an honest answer, not a violation. It passes the
disclosure check and **blocks the merge**, which is exactly the intent of the paragraph above.

Check your branch before pushing:

```bash
python tools/verifier_disclosure.py --base origin/main
```

⚠ The CI job runs this on every pull request but is **not blocking yet**, and the date is
written down. Measured over the whole history on 2026-08-28, only **7 of 105 commits** carry
the disclosure — a guard rail that broke every build the day it landed would be disarmed the
day after. It becomes blocking on **2026-10-01**; until then each PR publishes its own rate.
See [docs/mesures/atelier-github-2026-08-28.md](docs/mesures/atelier-github-2026-08-28.md).

## Style

Match the surrounding code. Comments and documentation are in French in `docs/` and in the
code; the top-level `README.md` and issue discussions are in English. Both are fine in a pull
request.
