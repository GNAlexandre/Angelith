# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Détection de chapitres et découpage en blocs.

`detect_chapters` combine deux signaux (union) :
  • les TITRES structurels (styles de titre Word → titres Markdown `#`/`##`,
    ou mise en forme police+gras promue en `#`/`##` par `extract.py`) ;
  • les MOTS-CLÉS multilingues (Chapter / Chapitre / Capítulo / 第N章 / Prologue…).
Cela rattrape les œuvres dont les chapitres sont des titres (sans le mot « chapitre »).

Quand DEUX niveaux de titre distincts sont présents (ex. `#`/`##`), le niveau le
moins profond devient la frontière de CHAPITRE et le niveau suivant celle de
PARTIE (sous-chapitre), imbriquée DANS le chapitre — jamais l'inverse. Un seul
niveau (ou aucun) donne le comportement historique : chapitres plats, `parts=[]`.

`detect_chapters_llm` (option/repli) demande au modèle quels titres candidats
ouvrent un chapitre — utile quand aucun signal déterministe ne marche.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core import tokens

DEFAULT_CHAPTER_PATTERNS = [
    r"^\s*#{0,4}\s*(chapter|chapitre|cap[ií]tulo)\s+[\dIVXLC]+",
    r"^\s*#{0,4}\s*(prologue|prólogo|prologo|épilogue|epilogue|ep[ií]logo|interlude|intermède)\b",
    r"^\s*#{0,4}\s*第\s*[\d一二三四五六七八九十百千零]+\s*[章話话回]",
]


@dataclass
class Part:
    title: str
    body: str


@dataclass
class Chapter:
    title: str
    body: str
    parts: list[Part] = field(default_factory=list)


def _compile(patterns: list[str]) -> list[re.Pattern]:
    """Compile les motifs de `chapter_patterns`. Un motif SIMPLE fourni par
    l'utilisateur (ex. « POV », « Chapter » — cf. `config.yaml`) est un simple mot,
    pas une regex ancrée : le laisser tel quel le ferait matcher n'importe où en
    PLEINE PHRASE (« stopover » contient « POV », « chapters » contient « Chapter »)
    — motif réel observé en production (roman C Vol.1). On l'ancre donc en DÉBUT DE
    LIGNE (avec un `#`+ optionnel devant, pour un titre déjà promu) et on exige une
    limite de mot en fin. Un motif qui commence déjà par `^` (les
    `DEFAULT_CHAPTER_PATTERNS`, déjà soigneusement ancrés) est laissé intact."""
    out: list[re.Pattern] = []
    for p in patterns:
        if not p.startswith("^"):
            # `re.escape` : le motif utilisateur est un mot-clé LITTÉRAL (un « . » ne doit
            # pas devenir un joker). `(?!\w)` remplace `\b` en fin : un `\b` après un motif
            # qui se termine par une ponctuation (« NPC No. ») ne matche JAMAIS quand un
            # espace suit (« NPC No. 1 »), car il n'y a pas de frontière mot↔non-mot entre
            # deux non-mots. `(?!\w)` équivaut à `\b` après une lettre (« Chapters » reste
            # rejeté) ET fonctionne après une ponctuation. Le bord gauche est déjà ancré par `^`.
            p = rf"^\s*#{{0,4}}\s*(?:{re.escape(p)})(?!\w)"
        out.append(re.compile(p, re.IGNORECASE))
    return out


def _heading_levels(lines: list[str]) -> dict[int, list[int]]:
    """Indices des lignes de titre ATX, PAR NIVEAU (1..6) — sans en choisir un seul."""
    levels: dict[int, list[int]] = {}
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+\S", ln)
        if m:
            levels.setdefault(len(m.group(1)), []).append(i)
    return levels


def _qualifying_levels(levels: dict[int, list[int]]) -> list[int]:
    """Niveaux avec ≥2 occurrences (un titre de Tome isolé n'en est pas un),
    triés du moins profond (le plus « large ») au plus profond."""
    return sorted(lvl for lvl, idxs in levels.items() if len(idxs) >= 2)


def _build(lines: list[str], starts: list[int], part_starts: list[int] | None = None) -> list[Chapter]:
    """Découpe `lines` en chapitres aux indices `starts`. Si `part_starts` est fourni,
    découpe en plus les Parties de chaque chapitre à ses frontières internes — le corps
    du chapitre lui-même n'est PAS modifié (il contient toujours les lignes `##`
    brutes) : `parts` n'est qu'une métadonnée auxiliaire parallèle."""
    part_starts = part_starts or []
    chapters: list[Chapter] = []
    for idx, s in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        title = re.sub(r"^#+\s*", "", lines[s]).strip()
        body = "\n".join(lines[s + 1:end]).strip()
        local = [p for p in part_starts if s < p < end]
        parts: list[Part] = []
        for pi, ps in enumerate(local):
            pend = local[pi + 1] if pi + 1 < len(local) else end
            ptitle = re.sub(r"^#+\s*", "", lines[ps]).strip()
            pbody = "\n".join(lines[ps + 1:pend]).strip()
            parts.append(Part(title=ptitle, body=pbody))
        chapters.append(Chapter(title=title, body=body, parts=parts))
    # on retire les chapitres sans contenu ni parties (titres de Tome isolés, etc.)
    non_vides = [c for c in chapters if c.body.strip() or c.parts]
    return non_vides or chapters


def detect_chapters(text: str, patterns: list[str] | None = None) -> list[Chapter]:
    """Découpe `text` en chapitres (titres structurels ∪ mots-clés), avec Parties
    imbriquées si un second niveau de titre qualifiant est présent.

    `patterns` est une liste de motifs ADDITIONNELS : les défauts multilingues restent
    toujours actifs. Ils les REMPLAÇAIENT auparavant, ce qui faisait perdre le motif CJK
    `第N章` dès qu'un `chapter_patterns` était renseigné dans `config.yaml` — or il l'est,
    avec une liste 100 % latine. Un utilisateur qui ajoute « POV » ne demande pas à cesser
    de détecter « Prologue ».

    L'union se fait ICI et non chez les appelants : `sources.scan_volume` et
    `orchestrator.process_volume` lisent tous deux la clé, et la laisser à leur charge les
    ferait diverger au premier oubli."""
    regexes = _compile(list(DEFAULT_CHAPTER_PATTERNS) + list(patterns or []))
    lines = text.splitlines()
    levels = _heading_levels(lines)
    qualifying = _qualifying_levels(levels)
    keyword_idx = {i for i, ln in enumerate(lines) if any(rx.search(ln) for rx in regexes)}

    if len(qualifying) < 2:
        # Comportement historique, inchangé : au plus un niveau de titre retenu.
        top = qualifying[0] if qualifying else (min(levels) if levels else None)
        bounds = set(keyword_idx) | (set(levels[top]) if top is not None else set())
        if not bounds:
            return [Chapter(title="", body=text.strip())]
        return _build(lines, sorted(bounds))

    # ≥2 niveaux qualifiants : le plus large = Chapitre, le suivant = Partie imbriquée.
    # Niveaux 3+ ignorés pour le découpage (limite à 2 niveaux) — leur texte reste tel
    # quel, littéral, dans le corps de la Partie qui les contient.
    chap_lvl, part_lvl = qualifying[0], qualifying[1]
    chap_bounds = set(levels[chap_lvl]) | keyword_idx
    # Un mot-clé tombant sur une ligne de Partie la PROMEUT en frontière de Chapitre
    # (ex. un « Epilogue » tapé au niveau Partie) — elle est retirée des bornes de Partie.
    part_bounds = set(levels[part_lvl]) - chap_bounds
    if not chap_bounds:
        return [Chapter(title="", body=text.strip())]
    return _build(lines, sorted(chap_bounds), sorted(part_bounds))


def detect_chapters_llm(text: str, llm, model: str, patterns: list[str] | None = None,
                        temperature: float = 0.0, extra_directive: str = "") -> list[Chapter]:
    """Détection assistée par le modèle. Repli sur `detect_chapters` si indisponible
    ou si la réponse n'est pas exploitable. Charge utile bornée : seulement les
    lignes COURTES candidates à être des titres."""
    if llm is None:
        return detect_chapters(text, patterns)

    lines = text.splitlines()
    cands: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or len(s) > 70:
            continue
        prev_blank = (i == 0) or (lines[i - 1].strip() == "")
        if prev_blank:
            cands.append((i, re.sub(r"^#+\s*", "", s)))
    if not cands:
        return detect_chapters(text, patterns)

    listing = "\n".join(f"{k}. {t}" for k, (i, t) in enumerate(cands))
    system = (
        "Tu repères les DÉBUTS DE CHAPITRES dans une liste de lignes candidates "
        "(titres potentiels) extraites d'un light novel. Réponds UNIQUEMENT par les "
        "numéros (séparés par des virgules) des lignes qui ouvrent un nouveau chapitre "
        "(prologue, chapitre, épilogue, interlude…). Aucun autre texte."
    )
    user = listing + (f"\n\n{extra_directive}" if extra_directive else "")
    try:
        ans = llm.chat(model, system, user, temperature)
        nums = [int(x) for x in re.findall(r"\d+", ans)]
        idxs = sorted({cands[k][0] for k in nums if 0 <= k < len(cands)})
    except Exception:
        return detect_chapters(text, patterns)
    if not idxs:
        return detect_chapters(text, patterns)
    return _build(lines, idxs)


_ATX_LINE = re.compile(r"^#{1,6}\s+\S")


def _paragraphs(text: str) -> list[str]:
    paras: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            if buf:
                paras.append("\n".join(buf).strip()); buf = []
        elif "<!-- IMG:" in line or _ATX_LINE.match(line):
            # Marqueur/titre atomique : jamais fusionné avec la prose voisine, pour
            # qu'un titre de Partie (`##`) survive intact au découpage en blocs.
            if buf:
                paras.append("\n".join(buf).strip()); buf = []
            paras.append(line.strip())
        else:
            buf.append(line)
    if buf:
        paras.append("\n".join(buf).strip())
    return [p for p in paras if p]


def _heading_level(p: str) -> int:
    m = re.match(r"^(#{1,6})\s+\S", p)
    return len(m.group(1)) if m else 0


# Fin de phrase : ponctuation forte, éventuellement suivie d'un guillemet/parenthèse
# fermante, puis d'une espace. Couvre le latin ET le CJK (。！？, sans espace obligatoire
# après — d'où le `|$` et le `\s*`).
_SENTENCE_END_RE = re.compile(r"[.!?…][\"'»”’\)\]]*\s|[。！？…][\"'»”’\)\]]*\s*")


def _is_atomic(p: str) -> bool:
    """Un marqueur d'image ou un titre ATX ne se coupe JAMAIS (cf. `_paragraphs`)."""
    return "<!-- IMG:" in p or bool(_ATX_LINE.match(p))


def _best_cut(text: str) -> int:
    """Indice de la meilleure coupe de `text`, au plus près du milieu.
    Priorité décroissante : saut de ligne > fin de phrase > espace — on ne coupe au
    milieu d'une phrase que faute de mieux, et jamais au milieu d'un mot.
    Renvoie 0 si aucune coupe propre n'existe (texte d'un seul tenant)."""
    mid = len(text) // 2
    candidates = (
        [i + 1 for i, ch in enumerate(text) if ch == "\n"],
        [m.end() for m in _SENTENCE_END_RE.finditer(text)],
        [i + 1 for i, ch in enumerate(text) if ch == " "],
    )
    for cuts in candidates:
        cuts = [c for c in cuts if 0 < c < len(text)]
        if cuts:
            return min(cuts, key=lambda c: abs(c - mid))
    return 0


def split_oversized(p: str, max_chars: int) -> list[str]:
    """Coupe un paragraphe PLUS GROS que `max_chars` en morceaux qui tiennent sous la
    limite, aux frontières de phrase (cf. `_best_cut`).

    Sans ça, `split_blocks` laissait passer un tel paragraphe ENTIER : un chapitre
    dont l'extraction n'a produit aucune ligne vide se retrouvait en UN SEUL bloc,
    très au-dessus de `max_block_chars`. Conséquences observées en production : le
    plafond de sortie (`_out_cap`) saturait, le budget de raisonnement partait
    entièrement dans le `<think>`, et le modèle dérivait sur les sources de référence
    en retraduisant du texte hors-bloc.

    Un paragraphe qui tient déjà sous la limite, un marqueur `<!-- IMG:` ou un titre
    ATX sont renvoyés tels quels — le découpage reste donc STRICTEMENT identique à
    l'ancien pour tout texte sainement paragraphé."""
    if len(p) <= max_chars or _is_atomic(p):
        return [p]
    cut = _best_cut(p)
    if not cut:
        return [p]                       # d'un seul tenant (ni espace ni ponctuation)
    left, right = p[:cut].strip(), p[cut:].strip()
    if not left or not right:
        return [p]
    return split_oversized(left, max_chars) + split_oversized(right, max_chars)


def split_in_half(text: str) -> list[str]:
    """Coupe `text` en DEUX au plus près du milieu, en préférant une frontière de
    paragraphe. Utilisé par le redécoupage-relance de l'orchestrateur : un bloc qui a
    fait échouer le modèle (budget « thinking » épuisé, sortie qui sature le plafond,
    troncature) est rejoué en deux moitiés, chacune avec son propre plafond de sortie
    — plutôt que d'être abandonné et réinjecté en langue source.
    Renvoie `[text]` si aucune coupe propre n'existe."""
    t = text.strip()
    if not t:
        return [text]
    paras = _paragraphs(t)
    if len(paras) >= 2:
        mid = len(t) // 2
        best_i, best_d, acc = 1, None, 0
        for i, p in enumerate(paras[:-1]):
            acc += len(p) + 2
            d = abs(acc - mid)
            if best_d is None or d < best_d:
                best_d, best_i = d, i + 1
        left = "\n\n".join(paras[:best_i]).strip()
        right = "\n\n".join(paras[best_i:]).strip()
        if left and right:
            return [left, right]
    cut = _best_cut(t)                   # paragraphe unique → coupe interne
    if not cut:
        return [text]
    left, right = t[:cut].strip(), t[cut:].strip()
    return [left, right] if left and right else [text]


def _segments_by_part(paras: list[str], has_parts: bool) -> list[tuple[bool, list[str]]]:
    """Regroupe `paras` en segments `(is_part, paragraphes)`. `has_parts=False` (le
    défaut, `chapter.parts == []`) renvoie TOUT `paras` comme un seul segment
    `is_part=False`, SANS scruter les titres — garantit l'identité bit-à-bit avec
    l'ancien `split_blocks`, même si une ligne ATX isolée (mise en forme
    accidentelle, titre à occurrence unique non qualifiant) traîne par ailleurs
    dans le texte. Sinon, le segment avant le premier titre est `is_part=False`, et
    chaque titre de niveau 1/2 ouvre un nouveau segment `is_part=True` (niveau 3+
    ignoré, cohérent avec la limite à 2 niveaux de `detect_chapters`)."""
    if not has_parts:
        return [(False, paras)] if paras else []
    segments: list[tuple[bool, list[str]]] = [(False, [])]
    for p in paras:
        if _heading_level(p) in (1, 2):
            segments.append((True, [p]))
        else:
            segments[-1][1].append(p)
    return [(is_part, ps) for is_part, ps in segments if ps]


def limite_caracteres(text: str, max_chars: int, max_tokens: int | None) -> int:
    """Limite de bloc en CARACTÈRES, dérivée d'un budget en TOKENS et de la densité
    réellement mesurée sur `text`.

    Un bloc de 6 000 caractères ne pèse pas la même chose selon la langue : ~1 500 tokens
    en anglais (≈4 caractères/token), ~5 900 en japonais (≈1 token/caractère). Découper en
    caractères revient donc à donner au modèle quatre fois plus de travail par bloc sur un
    pivot CJK — mesuré sur roman A Vol.1 (densité 0,977 tok/car. sur tout l'EPUB),
    où le plafond de sortie `out_cap` saturait son `ceil` sur 8 blocs sur 8.

    `max_tokens=None` → `max_chars` rendu tel quel, comportement historique bit-à-bit.
    Sinon la limite ne peut que RÉTRÉCIR (`min`) : `max_block_chars` garde exactement sa
    sémantique de plafond dur, et un pivot latin (densité ~0,25) dérive une limite de
    ~4× `max_tokens`, donc au-dessus du plafond — **sa découpe est inchangée**."""
    if not max_tokens or not text:
        return max_chars
    densite = tokens.estimate(text) / len(text)
    if densite <= 0:
        return max_chars
    return max(1, min(max_chars, int(max_tokens / densite)))


class _BlocEnCours:
    """Le bloc en cours de constitution, et ceux déjà clos.

    ⚠ C'étaient trois variables libres (`blocks`, `cur`, `size`) qu'un `nonlocal` reliait à
    une fermeture `_flush`. Les tenir ensemble ne change rien au découpage : cela rend
    seulement chaque branche lisible seule, au lieu d'obliger à remonter la fonction pour
    savoir ce que « vider » touche."""

    def __init__(self) -> None:
        self.blocks: list[str] = []
        self.cur: list[str] = []
        self.size = 0

    def vider(self) -> None:
        """Clôt le bloc en cours, s'il y en a un."""
        if self.cur:
            self.blocks.append("\n\n".join(self.cur))
            self.cur, self.size = [], 0

    def ajouter(self, paragraphes: list[str], taille: int) -> None:
        self.cur.extend(paragraphes)
        self.size += taille


def _ajouter_paragraphe_par_paragraphe(acc: _BlocEnCours, seg_paras: list[str],
                                       max_chars: int) -> None:
    """Contenu ordinaire (hors Partie), ou Partie trop grosse même avec la marge : repli sur
    le découpage paragraphe par paragraphe historique.

    `split_oversized` est TRANSPARENT tant qu'aucun paragraphe ne dépasse `max_chars` (il
    renvoie `[p]`) : le découpage d'un texte sainement paragraphé est inchangé. Il ne
    s'active que sur le cas pathologique d'un paragraphe géant, qui passait auparavant
    entier et faisait exploser la taille du bloc."""
    for p in seg_paras:
        for q in split_oversized(p, max_chars):
            if acc.cur and acc.size + len(q) > max_chars:
                acc.vider()
            acc.ajouter([q], len(q) + 2)


def _ajouter_partie_entiere(acc: _BlocEnCours, seg_paras: list[str], seg_len: int,
                            max_chars: int, max_with_tolerance: float) -> None:
    """Partie qui rentre en entier (avec marge de tolérance si besoin) : jamais scindée
    entre deux blocs."""
    if acc.cur and acc.size + seg_len > max_with_tolerance:
        acc.vider()
    acc.ajouter(seg_paras, seg_len)
    if acc.size > max_chars:
        acc.vider()


def split_blocks(text: str, max_chars: int, has_parts: bool = False,
                 part_tolerance: float = 0.20, *, max_tokens: int | None = None) -> list[str]:
    """Découpe `text` en blocs de `max_chars` caractères max. Si `has_parts` (le
    chapitre a des Parties détectées, `chapter.parts` non vide), une Partie
    (délimitée par une ligne `##`/`#`) est gardée ENTIÈRE dans un même bloc quand
    c'est possible, en tolérant jusqu'à `part_tolerance` (20 % par défaut) de
    dépassement de `max_chars` pour y arriver — plutôt que de la couper en deux
    blocs simplement parce qu'elle chevauche la limite. Une Partie encore trop
    grosse même avec la marge retombe sur le découpage paragraphe par paragraphe
    historique. Sans Parties (`has_parts=False`, le cas de la grande majorité des
    projets), comportement strictement identique à l'algorithme d'origine.

    `max_tokens` (optionnel) borne le bloc en TOKENS plutôt qu'en caractères : la limite
    effective devient `min(max_chars, max_tokens / densité)` (cf. `limite_caracteres`).
    Absent → comportement inchangé."""
    paras = _paragraphs(text)
    if not paras:
        return []
    max_chars = limite_caracteres(text, max_chars, max_tokens)
    max_with_tolerance = max_chars * (1 + part_tolerance)

    acc = _BlocEnCours()
    for is_part, seg_paras in _segments_by_part(paras, has_parts):
        seg_len = sum(len(p) + 2 for p in seg_paras)
        if not is_part or seg_len > max_with_tolerance:
            _ajouter_paragraphe_par_paragraphe(acc, seg_paras, max_chars)
        else:
            _ajouter_partie_entiere(acc, seg_paras, seg_len, max_chars, max_with_tolerance)
    acc.vider()
    return acc.blocks


def split_into_n(text: str, n: int) -> list[str]:
    """Découpe `text` en `n` morceaux d'un NOMBRE DE PARAGRAPHES égal. Reste
    l'alignement de référence au niveau CHAPITRE (où il n'y a pas de poids par bloc
    à respecter) ; pour aligner sur des blocs de tailles inégales, voir
    `split_proportional`."""
    if n <= 1:
        return [text.strip()]
    paras = _paragraphs(text)
    if not paras:
        return [""] * n
    per = max(1, len(paras) / n)
    blocks: list[str] = []
    for i in range(n):
        start = round(i * per)
        end = round((i + 1) * per) if i < n - 1 else len(paras)
        blocks.append("\n\n".join(paras[start:end]).strip())
    return blocks


def split_proportional(text: str, weights: list[int]) -> list[str]:
    """Découpe `text` en `len(weights)` morceaux dont les TAILLES suivent les
    proportions de `weights` — typiquement les longueurs en caractères des blocs du
    pivot, pour qu'une source de référence éclaire réellement le bloc auquel elle est
    associée.

    Pourquoi pas `split_into_n` : celui-ci répartit par NOMBRE de paragraphes, alors
    que `split_blocks` découpe le pivot par VOLUME de caractères. Les deux divergent
    dès que les paragraphes ne sont pas homogènes — la « source alignée sur le bloc i »
    couvrait alors une autre tranche du chapitre, et le traducteur (à qui le prompt
    demande de recouper les sources) retraduisait ce hors-bloc. Symptôme observé en
    production : des passages entiers en double sur les chapitres à 1 ou 2 blocs.

    On raisonne en FRACTIONS du total, ce qui neutralise la différence de densité
    entre langues : un chapitre japonais (CJK) est bien plus court en caractères que
    son équivalent anglais, mais ses proportions internes restent comparables.

    Un morceau peut ressortir VIDE si un seul paragraphe de la référence couvre
    plusieurs blocs du pivot — les appelants filtrent déjà sur `.strip()`."""
    n = len(weights)
    if n <= 1:
        return [text.strip()]
    paras = _paragraphs(text)
    if not paras:
        return [""] * n
    total_w = sum(weights)
    if total_w <= 0:
        return split_into_n(text, n)
    lens = [len(p) + 2 for p in paras]
    total_l = sum(lens)
    # Frontières cibles, exprimées en caractères cumulés du texte de RÉFÉRENCE.
    targets, acc = [], 0
    for w in weights[:-1]:
        acc += w
        targets.append(acc / total_w * total_l)
    groups: list[list[str]] = [[] for _ in range(n)]
    k, pos = 0, 0
    for p, l in zip(paras, lens):
        # Un paragraphe bascule dans le morceau suivant dès que son MILIEU dépasse la
        # cible : il va donc au bloc auquel il appartient majoritairement.
        while k < n - 1 and pos + l / 2 > targets[k]:
            k += 1
        groups[k].append(p)
        pos += l
    return ["\n\n".join(g).strip() for g in groups]


def realign_chapters(ref_bodies: list[str], pivot_sizes: list[int],
                     tolerance: float = 0.5, max_grow: int = 2
                     ) -> tuple[list[str], list[tuple[int, ...]]]:
    """Répare les frontières de chapitre d'une source de RÉFÉRENCE qui a dérivé par
    rapport au pivot, alors même que les deux ont le MÊME nombre de chapitres.

    Pourquoi c'est nécessaire : l'orchestrateur considérait qu'un nombre de chapitres
    identique valait alignement 1:1. Faux — il suffit qu'une seule frontière soit placée
    au mauvais endroit d'un côté pour décaler le contenu. Cas réel, roman B Vol.2 : le
    chapitre 15 japonais contenait EN PLUS tout l'épilogue (7093 caractères au lieu des
    ~1800 attendus), et le chapitre 16 japonais n'en gardait que la fin (2296 au lieu de
    ~4580). Le traducteur, à qui on demande de recouper les sources, a donc traduit tout
    l'épilogue une seconde fois à la fin du chapitre 15.

    Méthode, volontairement conservatrice : on compare la taille de chaque chapitre de
    référence à sa part ATTENDUE (sa proportion dans le pivot, appliquée au total de la
    référence — ce qui neutralise le rapport de densité entre langues). Un chapitre qui
    s'en écarte de plus de `tolerance` est « hors proportion ». Les hors-proportion
    consécutifs forment un intervalle, étendu (au plus `max_grow` fois) au voisin dont
    l'erreur est de signe OPPOSÉ : une frontière mal placée DÉPLACE du texte d'un
    chapitre à l'autre, elle n'en crée pas — l'excédent de l'un est le déficit du
    voisin. L'intervalle est alors re-découpé d'un bloc, proportionnellement aux tailles
    du pivot.

    Renvoie `(bodies, intervalles_réparés)`. Sans anomalie, `bodies` est identique à
    l'entrée et la liste d'intervalles est vide : les volumes correctement alignés
    (l'immense majorité) ne sont pas touchés."""
    n = len(pivot_sizes)
    out = list(ref_bodies)
    if len(out) != n or n < 2:
        return out, []
    total_p, total_r = sum(pivot_sizes), sum(len(b) for b in out)
    if total_p <= 0 or total_r <= 0:
        return out, []
    exp = [total_r * s / total_p for s in pivot_sizes]
    err = [len(out[i]) - exp[i] for i in range(n)]
    hors = [i for i in range(n) if abs(err[i]) > tolerance * max(exp[i], 1.0)]
    if not hors:
        return out, []

    runs: list[list[int]] = []
    for i in hors:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])

    deja: set[int] = set()
    repares: list[tuple[int, ...]] = []
    for base in runs:
        run, net, grown = list(base), sum(err[i] for i in base), 0
        # On n'étend que TANT QUE l'excédent/déficit net de l'intervalle reste hors
        # tolérance : dès qu'il s'équilibre, le texte déplacé est retrouvé et élargir
        # ne ferait que re-découper des chapitres sains.
        while grown < max_grow and abs(net) > tolerance * max(sum(exp[i] for i in run), 1.0):
            cands = [j for j in (run[0] - 1, run[-1] + 1)
                     if 0 <= j < n and j not in run and err[j] * net < 0]
            if not cands:
                break
            j = max(cands, key=lambda k: abs(err[k]))
            run = ([j] + run) if j < run[0] else (run + [j])
            net += err[j]
            grown += 1
        if len(run) < 2 or deja & set(run):
            continue          # rien à échanger avec un voisin, ou déjà recalé
        joint = "\n\n".join(out[i] for i in run if out[i].strip())
        pieces = split_proportional(joint, [pivot_sizes[i] for i in run])
        for k, i in enumerate(run):
            out[i] = pieces[k]
        deja |= set(run)
        repares.append(tuple(run))
    return out, repares


@dataclass
class Appariement:
    """Ce qu'une source de référence donne à chaque chapitre du pivot.

    Un tuple ne suffisait plus : `--plan` et `RAPPORT.md` doivent pouvoir NOMMER les unités
    retenues et celles écartées. Sans ça, un décalage reste invisible — c'est ainsi que
    l'épilogue de *roman B Vol.3* s'est retrouvé apparié à la postface de l'auteur sans que
    rien ne le signale."""
    groupes: list[str]          # un corps de référence par chapitre du pivot
    indices: list[list[int]]    # les unités retenues, par chapitre
    ecartees: list[int]         # les unités abandonnées (tête et queue seulement)
    notes: list[str]


# Au plus tant d'unités écartées de CHAQUE côté. Le front et le back matter d'un livre en
# comptent une poignée (couverture, sommaire, crédits, colophon, postface) ; au-delà, ce n'est
# plus du hors-corps, c'est du contenu — et le plafond de volume ne suffirait pas à le dire sur
# un volume dont les chapitres seraient courts.
_MAX_UNITES_ECARTEES = 6


def apparier_chapitres(ref_bodies: list[str], pivot_sizes: list[int],
                       seuil_bruit: float = 0.005,
                       abandon_max: float = 0.10) -> Appariement:
    """Apparie les unités d'une source de RÉFÉRENCE aux chapitres du pivot, quand les deux
    n'en comptent pas le même nombre.

    ## Le cas, et pourquoi `split_into_n` n'y répondait pas

    Une source de référence détecte rarement le même découpage que le pivot : un EPUB fait des
    « chapitres » de sa couverture, de son sommaire et de son colophon, et porte souvent une
    postface que l'édition traduite n'a pas reprise. Mesuré sur *roman B Vol.3* : **9 unités
    japonaises pour 5 chapitres pivot**, alors que les cinq qui se correspondent ont des
    proportions quasi identiques.

    L'orchestrateur retombait alors sur `split_into_n`, qui répartit par **nombre de
    paragraphes égal**. Sur des chapitres inégaux (2 000 à 41 000 caractères), le prologue
    recevait 25 896 caractères au lieu de 3 600 — les trois premières sections du chapitre 1 —
    et pas un seul des 5 chapitres n'était aligné.

    ## Les trois temps

    1. **Le bruit des extrémités est écarté** — les unités sous `seuil_bruit` (0,5 % du total :
       sommaire, colophon, page de crédits, cahier d'illustrations) situées en tête ou en queue
       du volume.
    2. **Un préfixe et un suffixe supplémentaires peuvent être abandonnés**, si cela rapproche
       les proportions. C'est ce qui écarte une postface : trop lourde pour le point 1 (1,9 %
       du volume), mais sans équivalent dans le pivot.
    3. **L'appariement proprement dit**, par programmation dynamique sur les unités retenues.

    ## Trois décisions, et ce qu'elles protègent

    · **En fractions du total**, jamais en caractères — comme `split_proportional` et
      `realign_chapters`. C'est ce qui neutralise le rapport de densité entre langues : un
      chapitre japonais est ~2,5 fois plus court que son équivalent anglais, mais sa part du
      volume est la même.
    · **Programmation dynamique**, pas glouton : une frontière mal placée tôt se paierait sur
      tout le reste du volume, et un choix localement bon peut être globalement mauvais.
    · ⚠ **On n'abandonne qu'en TÊTE et en QUEUE, jamais au milieu.** Autoriser l'abandon
      partout rendrait la fonction plus générale — une référence avec un interlude non traduit
      — mais rien n'empêcherait alors de jeter un vrai chapitre en silence, pour la seule
      raison qu'il arrangerait les proportions. Le front et le back matter sont, eux,
      structurellement aux extrémités. Le corps du volume reste donc **intégralement couvert**,
      et c'est cette garantie qui rend l'abandon acceptable.

    ⚠ **L'abandon est borné et annoncé** : au plus `abandon_max` du volume et
    `_MAX_UNITES_ECARTEES` unités de chaque côté, et la liste part dans `notes`, donc dans
    `RAPPORT.md`. Perdre du texte de référence doit rester rare et visible — c'est la
    contrepartie de l'autorisation, et sans elle on ne saurait pas, sur un tome déjà traité, ce
    qui a été mis en regard de quoi."""
    n, m = len(pivot_sizes), len(ref_bodies)
    if n <= 0:
        return Appariement([], [], [], [])
    if m == 0:
        return Appariement([""] * n, [[] for _ in range(n)], [], [])
    if m < n:
        # Moins d'unités que de chapitres : rien à grouper. On redécoupe le texte entier —
        # au moins `split_proportional` respecte-t-il les volumes.
        joint = "\n\n".join(b for b in ref_bodies if b.strip())
        return Appariement(
            split_proportional(joint, pivot_sizes), [[] for _ in range(n)], [],
            [f"{m} unité(s) de référence pour {n} chapitre(s) du pivot → redécoupage "
             f"proportionnel du texte entier"])

    tailles = [len(b) for b in ref_bodies]
    total_ref = sum(tailles)
    total_p = sum(pivot_sizes)
    if total_ref <= 0 or total_p <= 0:
        return Appariement(split_into_n("\n\n".join(ref_bodies), n),
                           [[] for _ in range(n)], [], [])
    cible = [p / total_p for p in pivot_sizes]

    # --- 1) Le bruit des extrémités ------------------------------------------------- #
    plancher = seuil_bruit * total_ref
    debut, fin = 0, m
    while fin - debut > n and tailles[debut] < plancher:
        debut += 1
    while fin - debut > n and tailles[fin - 1] < plancher:
        fin -= 1

    # --- 2) et 3) Meilleur (a, b) retenu, puis appariement dessus -------------------- #
    meilleur = None
    borne_a = min(debut + _MAX_UNITES_ECARTEES, fin - n)
    for a in range(debut, borne_a + 1):
        borne_b = max(a + n, fin - _MAX_UNITES_ECARTEES)
        for b in range(borne_b, fin + 1):
            if (total_ref - sum(tailles[a:b])) > abandon_max * total_ref:
                continue
            resultat = _apparier_intervalle(tailles, a, b, cible, seuil_bruit * total_ref)
            if resultat is not None and (meilleur is None or resultat[0] < meilleur[0]):
                meilleur = (resultat[0], resultat[1], a, b)
    if meilleur is None:                       # aucun découpage admissible : tout consommer
        secours = _apparier_intervalle(tailles, 0, m, cible, plancher)
        if secours is None:
            return Appariement(split_into_n("\n\n".join(ref_bodies), n),
                               [[] for _ in range(n)], [], [])
        meilleur = (secours[0], secours[1], 0, m)
    _cout, bornes, a, b = meilleur

    indices = [list(range(x, y)) for x, y in bornes]
    groupes = ["\n\n".join(ref_bodies[k] for k in idx if ref_bodies[k].strip()).strip()
               for idx in indices]
    ecartees = [k for k in range(m) if not (a <= k < b)]

    notes: list[str] = []
    if m != n:
        detail = ", ".join(f"ch.{i + 1}←{len(idx)} unité(s)"
                           for i, idx in enumerate(indices) if len(idx) != 1)
        notes.append(f"{m} unité(s) de référence appariées aux {n} chapitre(s) du pivot par "
                     f"proportions" + (f" ({detail})" if detail else ""))
    if ecartees:
        perdu = sum(tailles[k] for k in ecartees)
        notes.append("unité(s) de référence écartée(s) (hors corps, sans équivalent dans le "
                     "pivot) : n°" + ", ".join(str(k + 1) for k in ecartees)
                     + f" — {perdu} caractère(s), {100 * perdu / total_ref:.1f} % du volume")
    return Appariement(groupes, indices, ecartees, notes)


def _apparier_intervalle(tailles: list[int], a: int, b: int, cible: list[float],
                         plancher: float):
    """Meilleur découpage de `tailles[a:b]` en `len(cible)` groupes consécutifs.
    Renvoie `(coût, bornes)` ou `None` si l'intervalle est trop court.

    ⚠ Les unités sous `plancher` pèsent **zéro** : elles se rattachent à leur voisine sans
    déséquilibrer le groupe, au lieu d'attirer une frontière vers elles."""
    n, m = len(cible), b - a
    if m < n:
        return None
    poids = [t if t >= plancher else 0 for t in tailles[a:b]]
    total_w = sum(poids)
    if total_w <= 0:
        return None
    cumul = [0] * (m + 1)
    for j, w in enumerate(poids):
        cumul[j + 1] = cumul[j] + w

    infini = float("inf")
    cout = [[infini] * (m + 1) for _ in range(n + 1)]
    depuis = [[0] * (m + 1) for _ in range(n + 1)]
    cout[0][0] = 0.0
    for i in range(1, n + 1):
        # Chaque chapitre prend au moins une unité : d'où les bornes sur j et k.
        for j in range(i, m - (n - i) + 1):
            for k in range(i - 1, j):
                precedent = cout[i - 1][k]
                if precedent == infini:
                    continue
                candidat = precedent + abs((cumul[j] - cumul[k]) / total_w - cible[i - 1])
                if candidat < cout[i][j]:
                    cout[i][j], depuis[i][j] = candidat, k
    if cout[n][m] == infini:
        return None

    bornes: list[tuple[int, int]] = []
    j = m
    for i in range(n, 0, -1):
        k = depuis[i][j]
        bornes.append((a + k, a + j))
        j = k
    bornes.reverse()
    return cout[n][m], bornes
