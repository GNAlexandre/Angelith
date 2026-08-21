# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Mesure de la VALEUR AJOUTÉE de chaque agent, à partir des checkpoints d'un tome
déjà traité (`build/<projet>/<tome>/.checkpoints/`). Aucun appel LLM, lecture seule.

Répond à deux questions concrètes qu'on se posait à la main jusqu'ici :

1. **« Cet agent sert-il à quelque chose ? »** — combien de blocs il modifie vraiment,
   combien de retouches, et si sa sortie n'est pas simplement identique à son entrée.
2. **« Les temps du récit sont-ils au passé simple/imparfait ? »** — comptage des passés
   composés dans la NARRATION SEULE (les dialogues gardent légitimement le passé composé ;
   les compter fait chuter le taux et rend la mesure trompeuse), traduction → correction.

Le découpage en blocs de la mise en page DIFFÈRE de celui des étages précédents (le
texte français est re-découpé) : cette étape est donc comparée au niveau du CHAPITRE
entier, pas bloc à bloc — comparer par index donnerait des chiffres faux.
"""
from __future__ import annotations

import difflib
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

# Chaîne des étages alignés bloc à bloc (même nombre de blocs par chapitre).
ALIGNED_STAGES = ["traduction", "correction"]
LABELS = {"traduction": "traduction", "correction": "correction",
          "mise_en_page": "mise en page"}

_WORD = re.compile(r"[\wÀ-ÿ'’-]+")
# Auxiliaire + participe passé = temps composé. Heuristique volontairement grossière :
# elle sert à comparer AVANT/APRÈS sur le même texte, pas à analyser la langue.
_COMPOSED = re.compile(
    r"\b(ai|as|a|avons|avez|ont|suis|es|est|sommes|êtes|sont)\s+\w+"
    r"(é|ée|és|ées|i|is|it|u|us|ue)\b", re.IGNORECASE)


def _is_dialogue(line: str) -> bool:
    l = line.strip()
    return l.startswith(("«", "—", "–", "-", "“", "\"")) or "«" in l


def count_composed_past(text: str, narration_only: bool = True) -> int:
    """Nombre de temps composés. `narration_only` exclut les lignes de dialogue : la
    narration doit passer au passé simple/imparfait (consigne des prompts traducteur et
    correcteur), mais les dialogues gardent leur passé composé — les compter masque le
    travail réel sur la narration."""
    total = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if narration_only and _is_dialogue(line):
            continue
        total += len(_COMPOSED.findall(line))
    return total


@dataclass
class StageStats:
    """Comparaison d'un étage avec celui qui le précède."""
    stage: str
    unit: str                 # "bloc" ou "chapitre" (mise en page = re-découpage)
    n: int = 0
    touched: int = 0
    identical: int = 0
    edits_total: int = 0
    edits_median_touched: int = 0
    edits_max: int = 0
    similarity_median: float = 1.0
    words_delta_median: float = 0.0

    @property
    def label(self) -> str:
        return LABELS.get(self.stage, self.stage)


@dataclass
class Analysis:
    n_blocks: int = 0
    chapters: dict[str, int] = field(default_factory=dict)
    stages: list[StageStats] = field(default_factory=list)
    tenses_before: int = 0            # temps composés en narration après traduction
    tenses_after: int = 0             # … après correction


def _stage_blocks(ch_dir: Path, stage: str) -> list[str]:
    d = ch_dir / stage
    if not d.exists():
        return []
    return [f.read_text(encoding="utf-8") for f in sorted(d.glob("*.txt"))]


def _compare(pairs: list[tuple[str, str]], stage: str, unit: str) -> StageStats:
    st = StageStats(stage=stage, unit=unit, n=len(pairs))
    if not pairs:
        return st
    ratios, deltas, edits = [], [], []
    for a, b in pairs:
        ops = [o for o in difflib.SequenceMatcher(None, a.split(), b.split()).get_opcodes()
               if o[0] != "equal"]
        edits.append(len(ops))
        ratios.append(difflib.SequenceMatcher(None, a.split(), b.split()).ratio())
        wa, wb = len(_WORD.findall(a)), len(_WORD.findall(b))
        deltas.append((wb - wa) / wa * 100 if wa else 0.0)
        if a.strip() == b.strip():
            st.identical += 1
    touched = [e for e in edits if e]
    st.touched = len(touched)
    st.edits_total = sum(edits)
    st.edits_median_touched = int(statistics.median(touched)) if touched else 0
    st.edits_max = max(edits)
    st.similarity_median = statistics.median(ratios)
    st.words_delta_median = statistics.median(deltas)
    return st


def analyse(ckpt_root: str | Path) -> Analysis:
    ckpt_root = Path(ckpt_root)
    res = Analysis()
    if not ckpt_root.exists():
        return res

    chapters = sorted(p for p in ckpt_root.iterdir() if p.is_dir() and p.name.startswith("ch"))
    aligned: dict[str, list[tuple[str, str]]] = {s: [] for s in ALIGNED_STAGES[1:]}
    mep_pairs: list[tuple[str, str]] = []

    for ch in chapters:
        per_stage = {s: _stage_blocks(ch, s) for s in ALIGNED_STAGES + ["mise_en_page"]}
        n = len(per_stage["traduction"])
        res.chapters[ch.name] = n
        res.n_blocks += n
        # Étages alignés : comparaison bloc à bloc avec l'étage précédent.
        for prev, cur in zip(ALIGNED_STAGES, ALIGNED_STAGES[1:]):
            for i in range(min(len(per_stage[prev]), len(per_stage[cur]))):
                aligned[cur].append((per_stage[prev][i], per_stage[cur][i]))
        # Mise en page : nombre de blocs différent (re-découpage) → niveau CHAPITRE,
        # comparée à la sortie de correction (l'étage qui la précède).
        if per_stage["correction"] and per_stage["mise_en_page"]:
            mep_pairs.append(("\n\n".join(per_stage["correction"]),
                              "\n\n".join(per_stage["mise_en_page"])))
        # Temps composés : traduction vs correction, narration seule.
        for i in range(min(len(per_stage["traduction"]), len(per_stage["correction"]))):
            res.tenses_before += count_composed_past(per_stage["traduction"][i])
            res.tenses_after += count_composed_past(per_stage["correction"][i])

    for stage in ALIGNED_STAGES[1:]:
        res.stages.append(_compare(aligned[stage], stage, "bloc"))
    res.stages.append(_compare(mep_pairs, "mise_en_page", "chapitre"))
    return res


def format_report(res: Analysis) -> str:
    if not res.n_blocks:
        return ("Aucun checkpoint exploitable — lance d'abord un traitement "
                "(les checkpoints sont conservés après le rendu).")
    out: list[str] = []
    out.append(f"Blocs analysés : {res.n_blocks} sur {len(res.chapters)} chapitre(s) "
               f"({', '.join(f'{c}:{n}' for c, n in res.chapters.items())})")
    out.append("")
    out.append(f"{'étape':<14}{'unité':>9}{'modifiés':>12}{'identiques':>12}"
               f"{'retouches':>11}{'médiane':>9}{'max':>6}{'similarité':>12}{'Δ mots':>9}")
    for st in res.stages:
        if not st.n:
            continue
        out.append(f"{st.label:<14}{st.unit:>9}{f'{st.touched}/{st.n}':>12}"
                   f"{f'{st.identical}/{st.n}':>12}{st.edits_total:>11}"
                   f"{st.edits_median_touched:>9}{st.edits_max:>6}"
                   f"{st.similarity_median * 100:>11.1f}%{st.words_delta_median:>+8.1f}%")
    out.append("")
    out.append("  « modifiés » = blocs où l'agent a réellement changé quelque chose.")
    out.append("  « mise en page » est comparée au CHAPITRE : son découpage en blocs diffère.")

    out.append("")
    if res.tenses_before:
        conv = (res.tenses_before - res.tenses_after) / res.tenses_before * 100
        out.append("Temps du récit (narration au passé simple/imparfait) :")
        out.append(f"  temps composés en NARRATION — traduction {res.tenses_before} "
                   f"→ correction {res.tenses_after}  ({conv:.0f} % convertis)")
        out.append("  (dialogues exclus : ils gardent légitimement le passé composé)")
    else:
        out.append("Temps du récit : aucun temps composé détecté en narration.")
    return "\n".join(out)
