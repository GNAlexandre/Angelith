# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Orchestrateur — traitement d'un Tome entier, par chapitre puis par BLOCS.

Étapes par bloc : terminologie → traduction/amélioration → correction → mise en page.
Après la terminologie d'un chapitre : consolidation des relevés en glossaire.yaml (avant le
traducteur). Étape par chapitre : réinjection des images.

Reprise : chaque bloc terminé est écrit dans build/<...>/.checkpoints/, donc un
arrêt (commande STOP ou Ctrl+C) ou un reboot ne perd que le bloc en cours d'appel.
Relancer la même commande reprend automatiquement au bloc suivant.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import re
import shutil
import time
from dataclasses import dataclass, replace
from pathlib import Path

from core import (chemins, glossary, glossary_build, glossary_force, glossary_lang,
                  quality, report, runtime, tokens)
from core import insertion as insertion_mod
from core.agents import build_agents
from core.langues import resoudre_pack
from core.control import StopRequested, clear_stop, install_sigint, should_stop
from core.llm import LLM
from core.reporter import Reporter
from core.version import __version__

from . import images, split
from . import typographie as ty
from .extract import IMG_MARKER, strip_images
from .render import _collapse_repetitions, render
from .sources import scan_volume

#: Nom de fichier du glossaire d'une œuvre, quand `chemins.glossaire_fichier` ne le dit pas.
#: Cité trois fois, dans trois fonctions différentes : la valeur par défaut d'un `.get()` est
#: une décision, et trois copies d'une décision finissent par ne plus être la même.
GLOSSAIRE_DEFAUT = "glossaire.yaml"

#: Ce que le terminologue rend quand il n'a rien relevé. C'est une VALEUR SENTINELLE : elle
#: est écrite au cache, relue, comparée, et sert de charge utile de dry-run. Cinq copies
#: littérales pour une chaîne dont l'ÉGALITÉ compte — et dont l'accent de « signaler » fait
#: partie.
RIEN_A_SIGNALER = "- (rien à signaler)"

#: Puce d'une sous-liste dans le rapport de fin de tome.
PUCE_SOUS_LISTE = "\n  - "


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _write(p: Path, s: str) -> None:
    """Écrit par temporaire + `os.replace`, qui est atomique sur NTFS comme sur POSIX.

    ⚠ Un `write_text` direct laisse un fichier TRONQUÉ si le processus meurt au milieu, ou si
    une synchro OneDrive verrouille la cible. `_run_blocks` traite déjà un bloc vide comme « à
    recalculer », ce qui absorbe le cas le plus fréquent — mais pas un bloc coupé au milieu
    d'une phrase, qui repartirait en aval comme s'il était complet. Miroir de
    `manga.checkpoints._ecrire_atomique`."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemins.derive(p, ".tmp")
    tmp.write_text(s, encoding="utf-8")
    os.replace(tmp, p)


def _strip_fences(t: str) -> str:
    t = t.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```$", "", t)
    return t.strip()


def _flags(text: str) -> list[str]:
    return [m.strip() for m in re.findall(r"<!--\s*AMBIGU\s*:\s*(.+?)-->", text, re.DOTALL)]


def _dedup_lines(text: str) -> str:
    """Concatène les notes de terminologie en supprimant les doublons (entrées en liste)."""
    seen: set[str] = set()
    out: list[str] = []
    for ln in text.splitlines():
        k = ln.strip()
        if k.startswith(("-", "•")):
            if k in seen:
                continue
            seen.add(k)
        out.append(ln)
    return "\n".join(out).strip()


def _est_tokens(s: str) -> int:
    """Estimation prudente : CJK ~1 token/caractère, latin ~4 caractères/token.
    Nom historique conservé (call sites + tests) ; l'heuristique vit désormais dans
    tokens.py, PARTAGÉE avec glossary._approx_tokens — avant cette unification les
    deux divergeaient (glossary.py ignorait le CJK), ce qui pouvait sous-budgéter
    une source japonaise/chinoise ici et la sur-tronquer là-bas."""
    return tokens.estimate(s)


def _truncate_tokens(s: str, max_tok: int) -> str:
    """Tronque `s` (en gardant le début) pour rester sous ~max_tok tokens estimés."""
    if max_tok <= 0:
        return ""
    if _est_tokens(s) <= max_tok:
        return s
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _est_tokens(s[:mid]) <= max_tok:
            lo = mid
        else:
            hi = mid - 1
    return s[:lo].rstrip() + " […]"


# Plafond de tokens de sortie : déplacé vers `core/quality.py` au lot 2.5 (il ne dépend que
# de `tokens.estimate`), ré-exporté sous son ancien nom pour les 8 call sites et les tests.
_out_cap = quality.out_cap


# Forçage déterministe du glossaire : extrait vers `core/glossary_force.py` au lot 2.5, à
# l'identique (rien là-dedans n'est propre au light novel — le lot 3 l'appliquera aux bulles).
# Ré-exports NOMMÉS sous les anciens noms privés, importés par tests/test_orchestrator.py.
_enforce_force = glossary_force.enforce_force
_match_case = glossary_force.match_case

_IMG_RE = re.compile(r"<!--\s*IMG:\s*(.+?)\s*-->")
_ATX_ANY = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)


_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Un idéogramme vaut ~½ mot. Ordre de grandeur assumé (un mot japonais fait 1 à 3
# caractères, et le japonais n'écrit ni articles ni prépositions), calé sur les 9 blocs du
# ch03 de roman A Vol.1 : le ratio sortie/entrée y vaut 1,19 à 1,33 sur les 7 blocs
# sains et 0,17 / 0,26 sur les 2 blocs tronqués. Le seuil `perte_mots_ratio.traducteur` de
# 0,60 les sépare donc avec le double de marge de chaque côté, sans avoir à le retoucher.
_MOTS_PAR_CAR_CJK = 0.5


def _word_count(s: str) -> int:
    """Compte de mots (lettres uniquement) — utilisé pour le garde-fou anti-perte-de-
    mots : une comparaison grossière entrée/sortie, pas une mesure linguistique fine.

    ⚠ `\\w` inclut les idéogrammes en Unicode : une phrase japonaise, écrite sans espaces,
    comptait donc pour UN SEUL mot. Le garde-fou `perte_mots` était par construction aveugle
    sur un pivot CJK — mesuré sur roman A Vol.1, où deux blocs coupés en plein mot
    (ch03 4/9 et 7/9, ~600 et ~800 tokens de français contre 3 100 à 4 800 pour leurs
    voisins) affichaient des ratios de 1,66 et 1,11, très au-dessus du seuil de 0,60, et
    ont traversé tout le run comptés « ok ». On neutralise donc les suites CJK avant de
    compter les mots latins, puis on les recompte à part.

    Sur un texte SANS caractère CJK, `sub` est l'identité et le terme ajouté vaut 0 : le
    résultat est strictement identique à celui d'avant (cf. `test_word_count_basic`)."""
    cjk = len(tokens.CJK_TEXTE.findall(s))
    return len(_WORD_RE.findall(tokens.CJK_TEXTE.sub(" ", s))) + int(cjk * _MOTS_PAR_CAR_CJK)


def _words_after_last_image(s: str) -> int:
    """Nombre de mots de texte situés APRÈS le dernier marqueur `<!-- IMG: … -->`.
    Sert à détecter une troncature du modèle qui s'arrête net à une image et perd le
    récit qui suit. Renvoie 0 s'il n'y a aucune image (rien à surveiller)."""
    last = None
    for m in _IMG_RE.finditer(s):
        last = m
    if last is None:
        return 0
    return _word_count(s[last.end():])


_GLOSSARY_SIGNALS = (
    re.compile(r'^\s*#+\s*(Personnages|Lieux|Organisations|Créatures|Objets|Termes)\b', re.M | re.I),
    re.compile(r'\[(?:masculin|féminin|\?)[^\]]*(?:FORCÉ|NE PAS TRADUIRE)[^\]]*\]'),
    re.compile(r'\(variantes\s*:', re.I),
    re.compile(r'mot\(s\) source à repérer', re.I),
)


def _looks_like_glossary(text: str) -> bool:
    """Détecte qu'une sortie d'agent est (en tout ou partie) une RECOPIE du glossaire
    fourni en contexte, au lieu du texte attendu — le 9B régurgite parfois le glossaire.
    Sans ce garde-fou, le glossaire finit collé dans le chapitre, et `_enforce_force`
    y remplace ensuite toutes les formes interdites (« jamais : Leprechaun, Leprechaun… »).
    On exige DEUX signaux distincts pour éviter un faux positif sur un texte qui, par
    hasard, contiendrait « (variantes : … » ou un titre de section isolé."""
    hits = sum(1 for rx in _GLOSSARY_SIGNALS if rx.search(text))
    return hits >= 2


def _looks_like_style_guide(text: str, typo=None) -> bool:
    """Détecte qu'une sortie recopie le GUIDE DE STYLE fourni en contexte (le 9B a
    régurgité « # Guide de style — conventions générales de traduction » en tête de
    bloc). Le titre est très distinctif → un seul signal suffit.

    ⚠ Le titre cherché vient du PACK de langue cible. Un pack anglais dont le guide
    s'intitulerait « Style guide » rendrait ce garde-fou muet si le motif restait français —
    et un garde-fou muet est pire qu'un garde-fou absent, parce qu'on croit l'avoir."""
    return bool((typo or ty.DEFAUT).guide_de_style.search(text))


def _has_runaway_repetition(text: str) -> bool:
    """Détecte une DÉGÉNÉRESCENCE en boucle du modèle : un même paragraphe SUBSTANTIEL
    (≥60 caractères) répété ≥3 fois. Motif réel (Vol.3 ch01) : le traducteur 9B a bouclé
    12× sur un échange de dialogue — invisible pour les garde-fous de longueur (chaque
    étage restait sous son plafond proportionnel à l'entrée). Grossier mais fiable ; le
    seuil de 3 évite de pénaliser un refrain légitime répété une fois."""
    from collections import Counter
    paras = [p.strip() for p in re.split(r'\n\s*\n', text) if len(p.strip()) >= 60]
    if len(paras) < 3:
        return False
    return Counter(paras).most_common(1)[0][1] >= 3


def _salvage_repetition(text: str, dry_payload: str, min_ratio: float = 0.55) -> str | None:
    """DERNIER RECOURS sur une boucle dégénérée que ni le retry ni le redécoupage n'ont
    cassée : effondre les cycles répétés (même filet que le rendu, `render._collapse_repetitions`)
    et garde le résultat s'il reste du récit exploitable — au moins `min_ratio` des mots de
    l'entrée, et plus aucune répétition.

    Raison d'être : une boucle ne détruit pas le texte, elle le NOIE. Le modèle a
    généralement traduit correctement le passage AVANT de se mettre à le répéter ; effondrer
    les répétitions rend donc un vrai bloc français. Cela vaut infiniment mieux que le repli
    historique sur la langue source, qui laissait passer un bloc entier en anglais dans le
    document final (5 blocs sur roman D Vol.1). Renvoie None si le texte dégonflé
    est trop amputé pour être honnête — dans ce cas seulement on retombe sur le pivot."""
    if not text.strip():
        return None
    cleaned = _collapse_repetitions(text).strip()
    if not cleaned or _has_runaway_repetition(cleaned):
        return None
    if _word_count(cleaned) < _word_count(dry_payload) * min_ratio:
        return None
    return cleaned


def _chemin_style_guide(config: dict, pack=None) -> Path:
    """Guide de style du pack de langue cible, ou `chemins.style_guide`.

    ⚠ Le repli est écrit ICI et non dans `core/langues.py` : `chemins.style_guide` est un
    artefact du light novel, et `tests/test_core_cli.py` interdit qu'une clé de rendu de
    brique remonte dans le socle. Le socle sait servir un fichier d'un pack ; c'est la brique
    qui sait lequel elle veut et d'où elle le tire sinon."""
    pack = pack if pack is not None else resoudre_pack(config)
    # La config EXPLICITE prime ; le pack fournit le défaut (cf. `render._chemin`).
    explicite = (config.get("chemins") or {}).get("style_guide")
    return Path(str(explicite)) if explicite else pack.fichier("style_guide.md")


def _dire(pack, cle: str, defaut: str) -> str:
    """Consigne du pack de langue cible, ou le texte français resté ici.

    ⚠ Le défaut n'est PAS recopié dans `core/langues.py`, et c'est délibéré : deux chaînes
    libres de diverger, dont l'une décide de la sortie d'un tome, seraient un défaut qu'aucun
    test ne verrait. En le laissant à son site d'appel, l'identité au bit près du mode
    compatibilité est vraie par construction (cf. `core.langues.Pack.consigne`)."""
    return pack.consigne(cle, defaut) if pack is not None else defaut


def _consigne_naturalisation(intensite: float, pack=None) -> str:
    """Traduit le curseur `naturalisation.intensite` (0.0–1.0) en une consigne injectée
    dans le message du TRADUCTEUR (# CONSIGNE DE NATURALISATION). 0 = traduction fidèle
    (comportement historique) ; 1 = reformulage marqué pour un français de roman publié.
    Le sens, la terminologie et les informations ne changent JAMAIS, quelle que soit
    l'intensité — c'est la garantie du prompt traducteur.md, ce curseur ne règle que
    l'AMPLEUR des reformulations de forme autorisées."""
    if intensite <= 0.15:
        return _dire(pack, "naturalisation_minimale",
                "Édition MINIMALE : corrige uniquement les temps du récit, les accords/genres, "
                "les anglicismes et les calques FLAGRANTS. Ailleurs, garde les mots et l'ordre.")
    if intensite <= 0.45:
        return _dire(pack, "naturalisation_legere",
                "Reformulage LÉGER : en plus du minimum, dé-calque les tournures qui « sentent la "
                "traduction » (ordre de mots anglais, « ... pour rien », négations lourdes) quand "
                "une phrase française plus idiomatique dit EXACTEMENT la même chose.")
    if intensite <= 0.75:
        return _dire(pack, "naturalisation_moderee",
                "Reformulage MODÉRÉ : réécris pour un français fluide et idiomatique CHAQUE phrase "
                "qui se lit comme une traduction, en préservant sens, terminologie, registre et information.")
    return _dire(pack, "naturalisation_marquee",
            "Reformulage MARQUÉ : vise le naturel d'un roman publié ; restructure sans hésiter une "
            "phrase entière pour qu'elle sonne française, sans jamais trahir le sens ni omettre d'information.")


def _fmt_duree(secondes: float) -> str:
    """Formatte une durée en `Xh​YY` / `Ymin` / `Zs` pour les estimations de temps."""
    s = max(0, int(secondes))
    h, r = divmod(s, 3600)
    m = r // 60
    if h:
        return f"{h}h{m:02d}"
    if m:
        return f"{m}min"
    return f"{s}s"


def _translate_title(title: str, glo_txt: str, llm, model: str, ck: Path, dry: bool = False,
                     pack=None) -> str:
    """Traduit un TITRE de chapitre en français via un appel COURT et NON-thinking (client
    par défaut), mis en cache dans `.checkpoints/chNN/title.txt` (réutilisé aux reprises).
    Renvoie le titre inchangé en dry-run, si le client est absent, ou si la sortie est vide
    ou suspecte (le garde-fou évite qu'un modèle qui divague ne pourrisse le titre)."""
    f = ck / "title.txt"
    if f.exists():
        cached = f.read_text(encoding="utf-8").strip()
        if cached:
            return cached
    if dry or llm is None or not title.strip():
        return title
    system = _dire(pack, "titre_chapitre",
              "Tu traduis un TITRE de chapitre de light novel en français naturel et concis. "
              "Respecte STRICTEMENT la terminologie du glossaire (noms propres, casse exacte). Si le "
              "titre est déjà en français, renvoie-le inchangé. Réponds UNIQUEMENT par le titre "
              "traduit, sur une seule ligne, sans guillemets ni commentaire.")
    try:
        out = (llm.chat(model, system, f"{glo_txt}\n\n# TITRE À TRADUIRE\n{title}",
                        temperature=0.2, max_tokens=128) or "").strip()
    except Exception:
        out = ""
    out = out.splitlines()[0].strip() if out else ""
    # Garde-fou : sortie vide, anormalement longue (divagation) ou parasitée → on garde l'original.
    if not out or len(out) > max(80, len(title) * 3) or out[:1] in {"#", "`", "-", "<", "|"}:
        return title
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(out, encoding="utf-8")
    return out


# Motifs d'échec de bloc pour lesquels REDÉCOUPER le bloc en deux et relancer a une
# chance de marcher : tous ont pour cause commune un bloc TROP GROS pour le modèle —
# le budget de raisonnement part entièrement dans le <think> et la réponse finale est
# tronquée ou absente, ou bien la sortie sature le plafond `_out_cap` et le modèle
# dérive sur les sources de référence (passages dupliqués). Deux moitiés, chacune avec
# son propre plafond proportionné, passent là où le bloc entier échouait.
#
# "repetition" EN FAIT PARTIE (mesuré sur roman D Vol.1 : 5 blocs — ch11 1/2,
# ch14 2/3, ch19 1/2 et 2/2, ch21 4/4 — réinjectés en anglais). La dégénérescence en boucle
# est un SYMPTÔME de taille, pas une incompréhension de la consigne : ces 5 blocs ont généré
# 19 000 à 29 700 tokens contre ~10 000 pour un bloc normal, c'est-à-dire qu'ils ont bouclé
# JUSQU'À saturer leur plafond. Comme `_diagnose` teste la boucle AVANT la saturation, ils
# étaient étiquetés "repetition" au lieu de "emballement" et perdaient le redécoupage.
# Couper change tout : chaque moitié reçoit un plafond deux fois plus bas (moins de place
# pour partir en boucle), et une boucle dans une moitié n'emporte plus l'autre — au pire on
# récupère 3 sous-blocs sur 4 en français au lieu de 0.
# Volontairement EXCLUS : "glossaire_fuite", "styleguide_fuite" et "titre_perdu" — là le
# modèle a vraiment mal compris la consigne ; couper ne changerait rien et doublerait le
# coût en tokens.
# "troncature_length" et "thinking_overflow" viennent du CLIENT LLM, pas d'une heuristique
# sur la sortie : ce sont les deux signaux DIRECTS qu'un bloc était trop gros pour le
# budget — `finish_reason == "length"` d'un côté, raisonnement sans réponse finale de
# l'autre. Ils étaient détectés et comptés depuis longtemps, mais ne déclenchaient rien.
_RESPLIT_REASONS = frozenset({"vide", "emballement", "troncature_image", "perte_mots",
                              "repetition", "troncature_length", "thinking_overflow",
                              "timeout"})

# Motifs dont le retry NE DOIT PAS baisser la température : la dégénérescence en boucle est
# une pathologie de BASSE température (le modèle re-choisit indéfiniment la continuation la
# plus probable). Le retry historique à `température × 0.4` la rendait donc PLUS probable —
# vérifié sur roman D Vol.1, où les deux appels de chaque bloc perdu ont bouclé
# (temps et tokens doublés dans perf.log). Pour ces motifs on RELÈVE la température à la
# place, ce qui casse le cycle.
_RETRY_HOTTER_REASONS = frozenset({"repetition"})

_TRAD_FAIL_LABELS = {
    "vide": "réponse vide du modèle",
    "glossaire_fuite": "le modèle a recopié le glossaire au lieu de traduire",
    "styleguide_fuite": "le modèle a recopié le guide de style au lieu de traduire",
    "repetition": "le modèle a bouclé (passage répété en boucle)",
    "troncature_image": "le modèle s'est arrêté à une image et a perdu le texte qui suit",
    "titre_perdu": "un titre de partie (##) a disparu de la sortie",
    "perte_mots": "chute anormale de longueur (texte vraisemblablement tronqué)",
    "troncature_length": "génération coupée net au plafond max_tokens (texte tronqué en plein mot)",
    "thinking_overflow": "budget de raisonnement épuisé avant la réponse finale",
    "cjk_residuel": "des noms sont restés en écriture source (japonais/chinois)",
    "timeout": "génération expirée (bloc trop long pour le budget de temps)",
}
# Motifs pour lesquels la sortie n'est PAS une traduction exploitable : on retombe alors
# sur le texte pivot (langue source) plutôt que de laisser passer du non-français.
_TRAD_GARBAGE = ("vide", "glossaire_fuite", "styleguide_fuite", "repetition")


@dataclass
class _CtxLN:
    """Tout ce dont les prédicats light novel ont besoin pour juger une sortie de bloc.

    Les trois `ref_*` sont dérivés de l'ENTRÉE une seule fois : ils étaient auparavant
    capturés par la fermeture de `_diagnose`, ce que le passage à un registre de fonctions
    de module ne permet plus."""
    sortie: str
    entree: str                      # le `dry_payload` : le bloc source, tel quel
    cap: int
    min_ratio: float | None
    ref_words: int
    ref_tail: int                    # mots de récit APRÈS la dernière image
    ref_titres: int                  # titres ATX (`#`/`##`) en entrée
    # Formes CJK légitimes dans un texte français (entrées `traduire: false` ou pas encore
    # romanisées) et seuil de déclenchement. Défauts NEUTRES : sans eux le motif ne peut pas
    # se déclencher, donc tout contexte construit à la main reste inchangé.
    cjk_autorise: tuple = ()
    cjk_seuil: int = 0
    # Cause du DERNIER appel LLM ("troncature" | "thinking_overflow" | "vide" | None), lue
    # sur le client APRÈS l'appel — c'est le seul champ qui ne se déduit PAS de la sortie.
    # Défaut neutre, et en dernière position : les prédicats qui s'en servent ne se
    # déclenchent pas sans elle, donc tout contexte construit à la main reste inchangé.
    raison_llm: str | None = None
    # Règles typographiques de la langue cible. Défaut NEUTRE — le français d'origine —
    # pour que tout contexte construit à la main reste inchangé ; les tests en
    # construisent, et c'est la convention des deux champs qui précèdent.
    typo: object = None


def _ln_vide(c: _CtxLN) -> bool:
    return not c.sortie.strip()


def _ln_glossaire_fuite(c: _CtxLN) -> bool:
    return _looks_like_glossary(c.sortie)


def _ln_styleguide_fuite(c: _CtxLN) -> bool:
    return _looks_like_style_guide(c.sortie, c.typo)


def _ln_repetition(c: _CtxLN) -> bool:
    """Dégénérescence en boucle (passage répété N fois) : non captée par les plafonds
    de longueur (proportionnels à l'entrée). Un retry à température MODIFIÉE casse
    généralement la boucle."""
    return _has_runaway_repetition(c.sortie)


def _ln_emballement(c: _CtxLN) -> bool:
    return _est_tokens(c.sortie) >= c.cap * 0.95


def _ln_timeout(c: _CtxLN) -> bool:
    """La génération a expiré, même après les tentatives du client.

    ⚠ Ce prédicat DOIT être testé avant `_ln_vide` : un timeout ne rend rien, donc une
    sortie vide, et `vide` appartient à `_TRAD_GARBAGE` — le bloc serait réinjecté en
    LANGUE SOURCE alors qu'il n'a jamais été soumis correctement. Un timeout n'est pas un
    modèle qui refuse de répondre : c'est un bloc trop long pour son budget, donc un
    symptôme de TAILLE, et couper en deux y est un remède causal."""
    return c.raison_llm == "timeout"


def _ln_troncature_length(c: _CtxLN) -> bool:
    """Le client a lu `finish_reason == "length"` : la génération a été coupée NET au
    plafond `max_tokens`. Signal direct, sans heuristique — et longtemps sans effet : il
    était compté puis le contenu tronqué repartait comme une réponse valide.

    `_ln_emballement` ne le rattrape pas : il compare au `cap` de l'appelant, alors que le
    plafond réellement envoyé vaut `cap + thinking_budget`. Une sortie coupée après un long
    raisonnement peut donc être COURTE, très loin des 95 % du `cap`."""
    return c.raison_llm == "troncature"


def _ln_thinking_overflow(c: _CtxLN) -> bool:
    """Le modèle a raisonné sans jamais produire de réponse finale, et le repli sans
    raisonnement a servi de filet. La sortie est exploitable mais DÉGRADÉE : elle n'a pas
    bénéficié du raisonnement que cet agent a précisément pour rôle de faire.

    Ne se déclenche que sur une sortie NON VIDE : sortie vide → `_ln_vide` (plus grossier,
    testé en premier), qui mène au même redécoupage."""
    return c.raison_llm == "thinking_overflow" and bool(c.sortie.strip())


_COMMENTAIRE_RE = re.compile(r"<!--.*?-->", re.S)


def _ln_cjk_residuel(c: _CtxLN) -> bool:
    """Des noms sont restés en écriture source dans un texte censé être français.

    Le registre light novel n'avait AUCUN contrôle de ce genre — alors que la brique manga
    en a un depuis longtemps, et que la docstring de `core/quality.py` cite « japonais
    résiduel » en exemple sans qu'il ait jamais été implémenté. Un chapitre entier en
    japonais ressortait donc « ok ».

    Tolère ce que le glossaire autorise explicitement (`traduire: false`) et ce qu'il n'a pas
    encore romanisé : les bannir ferait boucler le retry sur une sortie pourtant CONFORME au
    glossaire qu'on a nous-même fourni au traducteur. On retire aussi les marqueurs d'image
    (un nom de fichier peut porter du CJK) et les commentaires `<!-- AMBIGU: … -->`."""
    if not c.cjk_seuil:
        return False
    txt = _COMMENTAIRE_RE.sub("", _IMG_RE.sub("", c.sortie))
    for forme in c.cjk_autorise:          # déjà triées de la plus longue à la plus courte
        txt = txt.replace(forme, "")
    return len(glossary_lang.CJK.findall(txt)) >= c.cjk_seuil


def _ln_troncature_image(c: _CtxLN) -> bool:
    """Le modèle s'arrête au marqueur `<!-- IMG: … -->` comme s'il terminait le document,
    et perd le texte qui suit. Motif observé en prod (fin du Vol.3 : tout l'épilogue après
    la dernière image sauté). Indépendant de `min_ratio` → protège AUSSI le traducteur (qui
    n'a volontairement pas de ratio).

    Double condition pour NE PAS pénaliser une image simplement REPOSITIONNÉE en fin de
    sortie (le texte est là, mais après l'image) : on exige que la sortie ait AUSSI nettement
    raccourci globalement — signe d'une vraie perte, pas d'un déplacement."""
    return (c.ref_tail >= 12 and _words_after_last_image(c.sortie) < c.ref_tail * 0.5
            and _word_count(c.sortie) < _word_count(c.entree) * 0.85)


def _ln_titre_perdu(c: _CtxLN) -> bool:
    """`perte_mots` ne détecte que la longueur globale : un titre de Partie (`##`) qui perd
    son préfixe en cours de route (fondu dans la prose, ou simplement supprimé) ne change
    quasiment pas le compte de mots — d'où ce garde-fou dédié, indépendant de `min_ratio`."""
    return bool(c.ref_titres) and len(_ATX_ANY.findall(c.sortie)) < c.ref_titres


def _ln_perte_mots(c: _CtxLN) -> bool:
    return (c.min_ratio is not None and c.ref_words > 0
            and _word_count(c.sortie) < c.ref_words * c.min_ratio)


# Registre ORDONNÉ des contrôles light novel — l'ordre reproduit exactement celui de
# l'ancienne cascade de `if` de `_diagnose`, et il compte : `repetition` est testé AVANT
# `emballement`, ce qui étiquette « repetition » un bloc qui a bouclé JUSQU'À saturer son
# plafond (cf. le commentaire de `_RESPLIT_REASONS`, qui s'appuie sur cet ordre).
#
# Dix motifs, dont trois seulement sont universels (`vide`, `emballement`, `repetition`) et
# trois sont ancrés dans des artefacts light novel : `troncature_image` lit `<!-- IMG: -->`,
# `titre_perdu` lit les titres ATX, `styleguide_fuite` lit un guide de style que le manga
# n'injecte jamais. C'est POUR ÇA que le socle ne partage que le moteur, et que chaque brique
# fournit son registre (cf. `core/quality.py`).
#
# `troncature_length` et `thinking_overflow` sont placés APRÈS `emballement` et AVANT les
# trois motifs structurels : ils disent « le budget a manqué », un diagnostic plus précis et
# plus actionnable que « il manque un titre » ou « le texte a raccourci », qui n'en sont que
# les CONSÉQUENCES sur un bloc coupé. Les placer avant `repetition`/`emballement` masquerait
# en revanche une boucle qui a saturé son plafond — elle se termine aussi en `length`, mais
# couper au bon endroit y répond mieux que constater la troncature.
_MOTIFS_LN: tuple[tuple[str, object], ...] = (
    # `timeout` passe AVANT `vide` : les deux donnent une sortie vide, mais seul `vide`
    # appartient à `_TRAD_GARBAGE` (repli sur la langue source). Les intervertir ferait
    # ressortir en japonais un bloc que le modèle n'a simplement pas eu le temps de traiter.
    ("timeout", _ln_timeout),
    ("vide", _ln_vide),
    ("glossaire_fuite", _ln_glossaire_fuite),
    ("styleguide_fuite", _ln_styleguide_fuite),
    ("repetition", _ln_repetition),
    ("emballement", _ln_emballement),
    ("troncature_length", _ln_troncature_length),
    ("thinking_overflow", _ln_thinking_overflow),
    # Placé AVANT les trois motifs structurels : « la réponse n'est pas en français » est un
    # diagnostic plus utile que « il manque un titre » ou « le texte a raccourci », qui n'en
    # seraient que les conséquences. Et APRÈS `repetition`/`emballement`, qui décrivent une
    # sortie inexploitable — plus grossier passe en premier.
    ("cjk_residuel", _ln_cjk_residuel),
    ("troncature_image", _ln_troncature_image),
    ("titre_perdu", _ln_titre_perdu),
    ("perte_mots", _ln_perte_mots),
)


def _ln_prefere(gardee: str, motif_garde: str, candidate: str, motif_candidate: str) -> bool:
    """Une tentative ratée est-elle meilleure que celle déjà gardée ?

    À motif ÉGAL (deux boucles, deux troncatures…) la plus longue a le plus de récit
    récupérable pour le rattrapage en aval (`_salvage_repetition`) ou pour la conservation
    « à vérifier ». À motif différent, on garde la première : c'est elle qui décrit ce qui a
    réellement dérapé, et comparer des longueurs entre deux pathologies distinctes n'a pas
    de sens."""
    return motif_candidate == motif_garde and _word_count(candidate) > _word_count(gardee)


def _try_with_temp_retry(agent, user: str, dry_payload: str, cap: int, stats: dict,
                         min_ratio: float | None = None, temp_factor: float = 0.4,
                         postprocess=None,
                         repli_sans_raisonnement: bool | None = None,
                         cjk_autorise: tuple = (), cjk_seuil: int = 0,
                         typo=None) -> tuple[str, bool, str | None]:
    """Appelle un agent ; si la sortie est vide, emballée (sature `cap`), ou (si
    `min_ratio` fourni) a perdu trop de mots par rapport à `dry_payload`, RETENTE UNE
    fois à température MODIFIÉE avant de renoncer. `postprocess` (ex. retrait de
    ```fences```) s'applique à chaque tentative AVANT le diagnostic. Renvoie
    (texte, ok, motif_échec) — ok=False signifie qu'il faut retomber sur `dry_payload`
    (motif_échec renseigné : "vide" / "emballement" / "perte_mots"…).

    Depuis le lot 2.5, ne reste ici que ce qui est propre au light novel : la construction de
    l'appel (signature d'`Agent.run` + `postprocess`), le contexte et le registre de motifs.
    La mécanique de retry — direction de la correction de température, comptage, choix de la
    sortie à conserver — vit dans `core/quality.py`, partagée avec la brique manga."""
    ctx = _CtxLN(sortie="", entree=dry_payload, cap=cap, min_ratio=min_ratio,
                 ref_words=_word_count(dry_payload) if min_ratio else 0,
                 ref_tail=_words_after_last_image(dry_payload),
                 ref_titres=len(_ATX_ANY.findall(dry_payload)),
                 cjk_autorise=cjk_autorise, cjk_seuil=cjk_seuil, typo=typo)
    # Cause du DERNIER appel. Elle DOIT être relevée juste après chaque `agent.run` : le
    # client la remet à None à chaque `chat()`, et ce moteur peut appeler deux fois (retry à
    # température corrigée). La lire une seule fois après coup ne décrirait que le second
    # appel — c'est ce que faisait le seul point de lecture existant.
    raisons: list[str | None] = [None]

    def _diagnose(out: str) -> str | None:
        return quality.premier_motif(_MOTIFS_LN,
                                     replace(ctx, sortie=out, raison_llm=raisons[-1]))

    def _call(temp: float | None) -> str:
        # Transmis SEULEMENT s'il est demandé : `MangaAgent.run` et les agents factices des
        # tests n'ont pas ce paramètre, et `None` vaut de toute façon « défaut du client ».
        extra = ({} if repli_sans_raisonnement is None
                 else {"repli_sans_raisonnement": repli_sans_raisonnement})
        o = agent.run(user, dry_payload=dry_payload, max_tokens=cap, temperature=temp, **extra)
        # `getattr` en cascade : en dry-run l'agent n'a pas de client, et un agent factice
        # de test n'a pas forcément de `llm`.
        raisons.append(getattr(getattr(agent, "llm", None), "last_reason", None))
        return postprocess(o) if postprocess else o

    return quality.try_with_temp_retry(
        _call, _diagnose, stats=stats, temperature=agent.temperature,
        temp_factor=temp_factor, max_retries=1, cle_ok="blocs_ok",
        motifs_plus_chaud=_RETRY_HOTTER_REASONS, prefere=_ln_prefere)


def _keep_images(original: str, output: str) -> str:
    """Garantit que la sortie d'un agent porte EXACTEMENT les marqueurs IMG du bloc
    d'entrée : on retire le SURPLUS que l'agent aurait ajouté et on ré-ajoute (en fin de
    bloc) ce qu'il aurait supprimé. Les images restent ainsi ancrées au texte, sans perte
    ni doublon, même si le modèle est imprécis.

    ⚠ On raisonne par QUOTA (nombre d'occurrences dans l'entrée), pas par présence :
    la version d'origine dédoublonnait à UNE occurrence par marqueur distinct, ce qui
    supprimait les répétitions LÉGITIMES. Un séparateur de scène revient plusieurs fois
    dans un même bloc — mesuré sur roman B Vol.2 : un séparateur perdu dans chacun des
    chapitres 5, 8 et 10. « Répété » n'est pas « en trop »."""
    from collections import Counter
    orig = [m.group(1).strip() for m in _IMG_RE.finditer(original)]
    if not orig:
        return output
    quota = Counter(orig)
    used: Counter = Counter()

    def repl(m: re.Match) -> str:
        p = m.group(1).strip()
        if used[p] >= quota[p]:
            return ""                      # au-delà du quota d'entrée → surplus retiré
        used[p] += 1
        return f"<!-- IMG: {p} -->"
    out = _IMG_RE.sub(repl, output)
    # Déficit : on complète dans l'ORDRE de la source, en respectant la multiplicité.
    reste = quota - used                   # Counter : ne garde que les positifs
    missing: list[str] = []
    for p in orig:
        if reste[p] > 0:
            missing.append(p)
            reste[p] -= 1
    if missing:
        out = out.rstrip() + "\n\n" + "\n\n".join(f"<!-- IMG: {p} -->" for p in missing)
    return out


_BOLD_LINE_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")


def _repair_headings(original: str, output: str) -> str:
    """Répare le cas le plus fréquent de « titre perdu » du traducteur : il rend un
    titre de partie `## …` en **gras** (ligne entièrement en gras) au lieu de garder la
    syntaxe ATX. On restaure alors `##` sur les premières lignes entièrement en gras,
    tant que la sortie a MOINS de titres `##` que l'entrée. Sans ça, le garde-fou
    `titre_perdu` se déclenche sur une traduction par ailleurs correcte, le retry
    reproduit le même formatage, et le bloc retombe sur le texte SOURCE (anglais) —
    exactement le symptôme « bloc réinjecté en anglais ». Déterministe et borné : ne
    touche jamais plus de lignes que de titres réellement manquants."""
    want = len(_ATX_ANY.findall(original))
    if not want:
        return output
    lines = output.split("\n")
    need = want - sum(1 for l in lines if _ATX_ANY.match(l))
    if need <= 0:
        return output
    for i, l in enumerate(lines):
        if need <= 0:
            break
        if _ATX_ANY.match(l):
            continue
        m = _BOLD_LINE_RE.match(l)
        if m:
            lines[i] = f"## {m.group(1).strip()}"
            need -= 1
    return "\n".join(lines)


def _warn(reporter, msg: str) -> None:
    """Signale un incident non fatal. Passe par `reporter.warn` (qui écrit AUSSI dans
    perf.log) et retombe sur `info` pour tolérer un reporter tiers/de test antérieur à
    l'ajout de `warn`."""
    fn = getattr(reporter, "warn", None) or getattr(reporter, "info", None)
    if callable(fn):
        fn(msg)


# Cycle de vie des clients LLM : extrait vers `core/runtime.py` au lot 2.4, à l'identique.
# Ré-exports NOMMÉS sous les anciens noms privés — `tests/test_orchestrator.py` les importe,
# et les 25 call sites de ce fichier n'ont pas à changer pour un déplacement.
_all_llm_clients = runtime.all_llm_clients
_close_llm_clients = runtime.close_llm_clients
_wire_reporter = runtime.wire_reporter
_aggregate_llm_stats = runtime.aggregate_llm_stats


# Nom VOLONTAIREMENT sans `.txt` : `stagediff._stage_blocks` liste les blocs d'un étage par
# `sorted(d.glob("*.txt"))`, et un marqueur en `.txt` s'y ajouterait comme un bloc fantôme en
# fin de liste (le chiffre trie avant l'underscore). Même raison que le `_done` de
# `run_extract_glossary`.
_SIGNATURE_FICHIER = "_decoupage.sig"


def _signature_blocs(blocks: list[str]) -> str:
    """Empreinte du DÉCOUPAGE d'un chapitre : nombre de blocs + longueurs.

    Les checkpoints sont indexés par NUMÉRO de bloc (`000.txt`, `001.txt`…) et rechargés
    tels quels. Si le découpage change entre deux runs — nouvelle valeur de
    `max_block_chars`, source ré-extraite, algorithme de `split_blocks` modifié — les
    anciens fichiers sont relus en face des NOUVEAUX blocs : le chapitre se retrouve
    silencieusement recomposé de morceaux qui ne se suivent pas. Rien ne le signalait.

    On empreinte les LONGUEURS et non le contenu : c'est la frontière des blocs qui casse
    l'alignement, et empreinter le texte ferait jeter des heures de cache pour une
    différence d'extraction sans conséquence sur les indices."""
    h = hashlib.sha256("|".join(str(len(b)) for b in blocks).encode("utf-8")).hexdigest()
    return f"{len(blocks)}:{h[:12]}"


def _sceller_decoupage(stage: str, ck_sub: Path, signature: str, reporter) -> None:
    """Invalide le cache de l'étage si le découpage a changé, puis (re)pose la signature.

    Signature ABSENTE = checkpoints d'avant ce garde-fou : on la pose sans rien jeter —
    livrer ce lot ne doit invalider aucun tome déjà traité. La protection ne vaut donc
    qu'à partir du run suivant, ce qui est exactement le moment où elle sert."""
    marqueur = ck_sub / _SIGNATURE_FICHIER
    ancienne = marqueur.read_text(encoding="utf-8").strip() if marqueur.exists() else ""
    if ancienne and ancienne != signature:
        shutil.rmtree(ck_sub, ignore_errors=True)
        _warn(reporter, f"[{stage}] découpage modifié ({ancienne.split(':')[0]} → "
                        f"{signature.split(':')[0]} blocs) — cache de l'étape invalidé "
                        f"et recalculé")
    ck_sub.mkdir(parents=True, exist_ok=True)
    marqueur.write_text(signature, encoding="utf-8")


def _ligne_decoupage(plan, pivot: str, max_chars: int, max_tokens_bloc: int | None,
                     agents: dict) -> str:
    """Une ligne pour comprendre le dimensionnement du run EN LE LISANT.

    C'est ce qui manquait sur roman A Vol.1 : le rapport ne disait ni la densité du
    pivot, ni la taille réelle des blocs, ni le budget envoyé au modèle — trois chiffres
    sans lesquels « ~22000 tok générés » dans `perf.log` reste une énigme."""
    texte = plan.langs[pivot].full_text
    densite = tokens.estimate(texte) / max(1, len(texte))
    limite = split.limite_caracteres(texte, max_chars, max_tokens_bloc)
    trad = agents.get("traducteur")
    budget = getattr(trad, "thinking_budget", 0) if getattr(trad, "thinking", False) else 0
    return (f"Découpage : {limite} car./bloc (densité {densite:.2f} tok/car."
            + (f", budget {max_tokens_bloc} tok" if max_tokens_bloc else ", en caractères seuls")
            + f") · plafond de sortie ≤ {quality.CEIL_DEFAUT} tok"
            + (f" + {budget} de raisonnement" if budget else ""))


def _run_blocks(stage: str, n: int, compute, ck_sub: Path,
                reporter: Reporter, build_dir: Path, agent=None, verbose: bool = False,
                signature: str | None = None, budget_bloc=None) -> list[str]:
    """Exécute un étage bloc par bloc, avec reprise (cache) et arrêt propre.

    `compute(bi) -> str`. Les blocs déjà présents dans `ck_sub` sont rechargés ;
    après CHAQUE bloc calculé, on vérifie la demande d'arrêt.
    Si `verbose` et `agent` fournis, affiche après chaque bloc calculé le temps, les
    tokens générés et la vitesse (tok/s) de CE bloc — lus sur le client LLM DE L'AGENT
    (qui peut router vers un endpoint différent du client par défaut).

    `signature` (cf. `_signature_blocs`) fait jeter le cache de l'étage si le découpage a
    changé depuis le run précédent. `None` = pas de contrôle (appelants tiers et tests).

    `budget_bloc(bi) -> int` (optionnel) donne le `max_tokens` du bloc : sert à annoncer,
    AVANT l'appel, combien de temps l'attente peut durer."""
    import time as _t
    llm = getattr(agent, "llm", None)
    if signature is not None:
        _sceller_decoupage(stage, ck_sub, signature, reporter)
    ck_sub.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    resumed = 0
    for bi in range(n):
        f = ck_sub / f"{bi:03d}.txt"
        if f.exists():
            cached = f.read_text(encoding="utf-8")
            if cached.strip():            # checkpoint valide → on le garde
                out.append(cached)
                resumed += 1
                continue
            # checkpoint VIDE (réponse vide d'un run précédent) → on recalcule ce bloc
        reporter.block(bi + 1, n)
        # Ce que l'attente va coûter, AVANT de la subir. Une génération peut légitimement
        # durer plus d'une heure (cf. `LLM.timeout_pour`), et une heure sans un octet est
        # indiscernable d'un blocage : c'est ce qui a fait tuer un run de nuit pourtant
        # vivant. Le budget et l'échéance rendent le silence lisible.
        if verbose and llm is not None and budget_bloc:
            expire = llm.timeout_pour(budget_bloc(bi))
            reporter.verbose(f"[{stage}] bloc {bi + 1}/{n} en cours · budget "
                             f"{budget_bloc(bi)} tok · expire dans {_fmt_duree(expire)}")
        t0 = _t.perf_counter()
        tok0 = llm.stats["tokens_generes"] if (verbose and llm) else 0
        res = compute(bi)
        if verbose and llm:
            dt = _t.perf_counter() - t0
            dtok = llm.stats["tokens_generes"] - tok0
            speed = dtok / dt if dt > 0 else 0
            reporter.verbose(f"[{stage}] bloc {bi + 1}/{n} : {dt:.1f}s · ~{dtok} tok générés "
                             f"· ~{speed:.1f} tok/s")
        f.write_text(res, encoding="utf-8")
        out.append(res)
        if should_stop(build_dir):
            raise StopRequested()
    if resumed and resumed < n:
        reporter.info(f"{stage} : {resumed}/{n} bloc(s) repris du cache")
    return out


# --------------------------------------------------------------------------- #
STAGES = ["terminologie", "traduction", "correction", "mise_en_page", "rendu"]


def optimize_glossary_file(glo_path: Path, agents: dict, reporter: Reporter, dry: bool = False,
                           verbose: bool = False) -> dict:
    """Passe d'optimisation du glossaire (agent glossariste) : dédoublonne, fusionne
    les variantes et reclasse. Sauvegarde une copie .bak.yaml avant d'écrire."""
    if agents.get("glossariste") is None:
        # glossariste désactivé (modeles.glossariste: null) → aucune optimisation.
        reporter.info("optimisation du glossaire désactivée (modeles.glossariste: null)")
        return {}
    glo = glossary.load(glo_path)
    if not glo or glossary.total(glo) == 0:
        reporter.info("glossaire vide — rien à optimiser")
        return {}
    if dry:
        reporter.info("optimisation du glossaire : nécessite le LLM (ignorée en dry-run)")
        return glossary.counts(glo)
    reporter.stage("optimisation du glossaire")
    sec = glossary.to_sectioned(glo)              # glossaire COMPLET (non plafonné : il faut tout voir)
    sec_tok = glossary._approx_tokens(sec)
    if sec_tok > 24000:
        reporter.info(f"⚠ glossaire volumineux (~{sec_tok} tokens) : assure-toi que la « Longueur de "
                      f"contexte » (num_ctx du Modelfile Ollama) est assez grande (tu peux monter, tu as la VRAM).")
    out_cap = min(32000, max(4096, sec_tok + 1024))
    glo_llm = agents["glossariste"].llm   # peut être un client d'endpoint différent du défaut
    t0 = time.perf_counter()
    tok0 = glo_llm.stats["tokens_generes"] if (verbose and glo_llm) else 0
    out = agents["glossariste"].run(f"# GLOSSAIRE À OPTIMISER\n{sec}", dry_payload=sec, max_tokens=out_cap)
    if verbose and glo_llm:
        dt = time.perf_counter() - t0
        dtok = glo_llm.stats["tokens_generes"] - tok0
        reporter.verbose(f"[glossariste] optimisation : {dt:.1f}s · ~{dtok} tok générés "
                         f"· ~{(dtok / dt if dt > 0 else 0):.1f} tok/s")
    parsed = glossary_build.parse_notes(out) if out.strip() else glossary.empty()
    # Garde-fou : sortie vide / qui a perdu plus de la moitié des entrées → on n'écrase pas.
    if glossary.total(parsed) < max(1, int(glossary.total(glo) * 0.5)):
        reporter.info("optimisation ignorée (sortie vide/suspecte) — glossaire inchangé")
        return glossary.counts(glo)
    bak = Path(glo_path).with_suffix(".bak.yaml")
    glossary.save(glo, bak)
    glossary.save(parsed, glo_path)
    reporter.info(f"glossaire optimisé : {glossary.total(glo)} → {glossary.total(parsed)} entrées "
                  f"(sauvegarde : {bak.name})")
    return glossary.counts(parsed)


def run_extract_glossary(project: str, volume: str, config: dict,
                         reporter: Reporter | None = None) -> dict:
    """Reconstruit/enrichit le glossaire d'une ŒUVRE à partir d'un tome DÉJÀ TRADUIT :
    le texte français final sert de pivot, et SEULE la terminologie (+ optimisation)
    tourne — aucun chapitre n'est retraduit, réécrit ni rendu. Sert à repartir d'un
    Vol.1 fini et propre pour peupler proprement le glossaire (CLI --extract-glossary).
    Reprise par bloc : les relevés du terminologue sont mis en cache par bloc, donc un
    arrêt (Ctrl+C ou `--stop`) puis une relance de la MÊME commande reprend là où on
    s'était arrêté au lieu de tout refaire (utile avec le thinking, qui est lent)."""
    reporter = reporter or Reporter()
    dry = config["options"].get("dry_run", False)
    verbose = config["options"].get("verbose", False)
    sources_dir = Path(config["chemins"]["sources"])
    glo_path = sources_dir / project / config["chemins"].get("glossaire_fichier", GLOSSAIRE_DEFAUT)
    style_txt = _read(_chemin_style_guide(config))
    budget = config["decoupage"].get("max_input_tokens", 24000)
    glo_budget_term = min(6000, max(1500, budget // 3))
    max_chars = config["decoupage"]["max_block_chars"]
    max_tokens_bloc = config["decoupage"].get("max_block_tokens")
    marge_partie = config["decoupage"].get("marge_partie_bloc", 0.20)

    build_dir = Path(config["chemins"]["build"]) / project / volume
    build_dir.mkdir(parents=True, exist_ok=True)
    term_ck_root = build_dir / ".checkpoints_glossaire"
    term_ck_root.mkdir(parents=True, exist_ok=True)
    install_sigint(reporter)
    clear_stop(build_dir)      # efface un STOP résiduel d'un crash précédent

    plan = scan_volume(sources_dir / project / volume, config,
                       Path(config["chemins"]["build"]) / project / volume)
    chapters = plan.langs[plan.pivot].chapters
    reporter.info(f"extraction glossaire — {project}/{volume} : pivot={plan.pivot}, "
                 f"{len(chapters)} chapitre(s) (lecture seule — aucune traduction/écriture)")

    llm = None if dry else LLM(base_url=config["llm"]["base_url"], api_key=config["llm"]["api_key"],
                               timeout=config["llm"]["timeout"], max_retries=config["llm"]["max_retries"],
                               think=config["llm"].get("think"),
                               debit_plancher=config["llm"].get("debit_plancher_tok_s"))
    agents = build_agents(config, llm, dry_run=dry)
    glo = glossary.load(glo_path) or glossary.empty()
    # Index nom/variante → entrée (glossary_build.build_index) : évite le scan linéaire
    # de _find_any à chaque fusion — le glossaire est celui de TOUTE la série, il ne
    # fait que grossir d'un tome à l'autre, donc ce scan devient le vrai coût dominant
    # sur une série longue si on le refait à chaque nouvelle entité de chaque bloc.
    glo_index = glossary_build.build_index(glo)

    ref_order = config["langues"]["priorite_sens"]
    others = [c for c in plan.langs if c != plan.pivot]
    # Même règle que dans `process_volume` : un pivot en écriture non latine a besoin de la
    # consigne de romanisation ET des lectures, sinon le terminologue recopie la graphie.
    _pivot_cjk = glossary_lang.pivot_est_cjk(plan.pivot, plan.langs[plan.pivot].full_text)
    _lectures = plan.langs[plan.pivot].lectures if _pivot_cjk else {}
    _pack = resoudre_pack(config)
    _consigne_cjk = ("\n\n" + glossary_lang.consigne_pivot_cjk(_pack)) if _pivot_cjk else ""

    def _lectures_bloc(bloc: str, maxi: int = 40) -> str:
        """Gloses dont la graphie apparaît dans CE bloc (cf. `_lectures_du_bloc`)."""
        vues = [(b, l) for b, l in _lectures.items() if b in bloc]
        if not vues:
            return ""
        vues.sort(key=lambda kv: len(kv[0]), reverse=True)
        return ("\n\n# LECTURES (furigana) — prononciation des graphies de ce bloc, "
                "pour la romanisation\n"
                + "\n".join(f"- {b} = {l}" for b, l in vues[:maxi]))

    n_ch = len(chapters)
    ref_chapter_text: dict[str, list[str]] = {}
    pivot_sizes = [len(strip_images(ch.body)) for ch in chapters]
    for c in others:
        src = plan.langs[c]
        if len(src.chapters) == n_ch:
            # Même recalage que dans `process_volume` : compteurs égaux ≠ alignement 1:1.
            bodies, repares = split.realign_chapters(
                [strip_images(ch.body) for ch in src.chapters], pivot_sizes)
            for run in repares:
                _warn(reporter, f"source [{c}] : frontières de chapitre recalées sur le pivot "
                                f"pour les chapitres " + ", ".join(str(i + 1) for i in run))
            ref_chapter_text[c] = bodies
        else:
            # ⚠ `apparier_chapitres`, PAS `split_into_n` : ce dernier répartit par nombre de
            # paragraphes égal, donc ignore les proportions. Cf. le site jumeau dans
            # `process_volume`, qui porte le détail.
            app = split.apparier_chapitres(
                [strip_images(ch.body) for ch in src.chapters], pivot_sizes)
            _warn(reporter, f"source [{c}] : {len(src.chapters)} chapitre(s) détecté(s) contre "
                            f"{n_ch} dans le pivot → appariés par proportions")
            for note in app.notes:
                _warn(reporter, f"source [{c}] : {note}")
            ref_chapter_text[c] = app.groupes

    # Cache du rendu du glossaire (`to_text`) : re-sérialiser TOUT le glossaire à
    # chaque bloc est du gâchis quand le bloc précédent n'a rien ajouté (le cas le
    # plus fréquent — la plupart des blocs de narration pure ne révèlent aucun nouveau
    # terme). `merge_notes` indique si quelque chose a réellement changé ; on ne
    # re-rend que dans ce cas, sinon on réutilise le texte déjà rendu.
    glo_dirty = True
    cached_glo_ctx = ""

    for ci, chap in enumerate(chapters):
        blocks = split.split_blocks(strip_images(chap.body), max_chars,
                                    has_parts=bool(chap.parts), part_tolerance=marge_partie,
                                    max_tokens=max_tokens_bloc) or [chap.body]
        n = len(blocks)
        ref_blocks = {c: split.split_proportional(ref_chapter_text[c][ci], [len(b) for b in blocks])
                      for c in others}
        reporter.chapter(ci + 1, len(chapters), chap.title)
        ch_ck = term_ck_root / f"ch{ci + 1:02d}"
        _sceller_decoupage("glossaire", ch_ck, _signature_blocs(blocks), reporter)
        done_marker = ch_ck / "_done"      # sentinelle : chapitre ENTIÈREMENT traité (blocs + optim)

        # Reprise au niveau CHAPITRE : si le chapitre est marqué terminé, on le saute
        # intégralement — ni ré-appel des blocs, ni ré-optimisation (qui est un appel LLM
        # coûteux, inutile de la refaire sur un chapitre déjà optimisé).
        if done_marker.exists():
            reporter.info(f"  chapitre {ci + 1} déjà traité — repris du cache (blocs + optimisation)")
            continue

        for bi, block in enumerate(blocks):
            reporter.block(bi + 1, n)
            ck_file = ch_ck / f"{bi:03d}.txt"
            # Reprise par bloc : relevés déjà en cache → re-merge déterministe sans LLM.
            if ck_file.exists():
                cached = ck_file.read_text(encoding="utf-8")
                added = glossary_build.merge_notes(glo, cached.strip() or RIEN_A_SIGNALER,
                                                   index=glo_index)
                if any(added.values()):
                    glo_dirty = True
                continue
            if glo_dirty:
                cached_glo_ctx = glossary.to_text(glo, max_tokens=glo_budget_term)
                glo_dirty = False
            glo_ctx = cached_glo_ctx
            refs = {c: ref_blocks[c][bi] for c in ref_blocks if bi < len(ref_blocks[c]) and ref_blocks[c][bi].strip()}
            kept = [c for c in ref_order if c in refs] + [c for c in refs if c not in ref_order]
            ref_section = ("\n\n# SOURCE(S) ÉTRANGÈRE(S) (pour repérer le mot d'origine — champ "
                          "termes_source)\n" + "\n\n".join(f"--- SOURCE [{c}] ---\n{refs[c]}" for c in kept)
                          if refs else "")
            import time as _t
            _term_llm = agents["terminologue"].llm   # peut être un client d'endpoint différent du défaut
            _t0 = _t.perf_counter()
            _tok0 = _term_llm.stats["tokens_generes"] if (verbose and _term_llm) else 0
            try:
                notes = agents["terminologue"].run(
                    f"{glo_ctx}\n\n{style_txt}{_consigne_cjk}\n\n"
                    f"# BLOC {bi + 1}/{n} ({plan.pivot})\n{block}"
                    f"{_lectures_bloc(block)}{ref_section}",
                    dry_payload=RIEN_A_SIGNALER, max_tokens=1024)
            except SystemExit:
                glossary.save(glo, glo_path)      # sauve l'acquis avant de remonter l'erreur fatale
                raise
            except Exception as e:
                reporter.info(f"⚠ bloc {bi + 1}/{n} ignoré (erreur : {e})")
                notes = ""
            if verbose and _term_llm:
                _dt = _t.perf_counter() - _t0
                _dtok = _term_llm.stats["tokens_generes"] - _tok0
                reporter.verbose(f"[terminologie] bloc {bi + 1}/{n} : {_dt:.1f}s · ~{_dtok} tok "
                                 f"· ~{_dtok / _dt if _dt > 0 else 0:.1f} tok/s")
            notes = notes.strip() or RIEN_A_SIGNALER
            ck_file.write_text(notes, encoding="utf-8")   # checkpoint AVANT merge (reprise fiable)
            added = glossary_build.merge_notes(glo, notes, index=glo_index)
            if any(added.values()):
                glo_dirty = True
            glossary.save(glo, glo_path)                  # sauve à chaque bloc (arrêt à tout moment)
            if should_stop(build_dir):
                reporter.info("Arrêt demandé — glossaire sauvegardé. Relance la même "
                              "commande pour reprendre où tu t'es arrêté.")
                raise StopRequested()
        glossary.save(glo, glo_path)
        if not dry and config["langues"].get("optimiser_apres_terminologie", True):
            optimize_glossary_file(glo_path, agents, reporter, dry=dry, verbose=verbose)
            glo = glossary.load(glo_path) or glo
            # L'optimisation reclassifie/fusionne les entrées : l'index (et le cache de
            # rendu) construits sur l'ancien `glo` sont désormais périmés.
            glo_index = glossary_build.build_index(glo)
            glo_dirty = True
        done_marker.write_text("ok", encoding="utf-8")    # chapitre terminé (blocs + optim) → ne plus le refaire

    reporter.info(f"glossaire final ({glossary.total(glo)}) : "
                 + ", ".join(f"{k} {v}" for k, v in glossary.counts(glo).items()))
    # Run terminé intégralement → on purge les checkpoints (un futur --extract-glossary
    # recommencera proprement, il ne reprendra pas un cache périmé).
    shutil.rmtree(term_ck_root, ignore_errors=True)
    _close_llm_clients(llm, agents)
    return glossary.counts(glo)


def run_optimize(project: str, config: dict, reporter: Reporter | None = None) -> dict:
    """Optimise le glossaire d'une ŒUVRE indépendamment d'un volume (CLI --optimize-glossary)."""
    reporter = reporter or Reporter()
    dry = config["options"].get("dry_run", False)
    verbose = config["options"].get("verbose", False)
    glo_path = Path(config["chemins"]["sources"]) / project / \
        config["chemins"].get("glossaire_fichier", GLOSSAIRE_DEFAUT)
    llm = None if dry else LLM(
        base_url=config["llm"]["base_url"], api_key=config["llm"]["api_key"],
        timeout=config["llm"]["timeout"], max_retries=config["llm"]["max_retries"],
        think=config["llm"].get("think"),
                               debit_plancher=config["llm"].get("debit_plancher_tok_s"))
    agents = build_agents(config, llm, dry_run=dry)
    return optimize_glossary_file(glo_path, agents, reporter, dry=dry, verbose=verbose)


def _inserer_illustrations(full_md: str, project: str, config: dict, build_dir,
                           pack, reporter) -> tuple:
    """`PLAN-27` L27.4 — les illustrations générées, **si et seulement si** on l'a demandé.

    Rend `(markdown, [Inseree])`. Quatre garde-fous, tous non négociables, et trois d'entre
    eux sont ici :

    1. **défaut `false`** — `illustration.inserer_dans_sorties`. Un tome relancé sans que
       l'utilisateur ait rien demandé sort **iso-octet** : on ne lit même pas le dossier des
       images retenues. C'est le critère 7 du plan, et un test rend deux fois le même tome
       pour comparer les octets ;
    2. **la légende n'est pas désactivable** — `core/insertion.py` lève sur une légende vide,
       et le texte vient du pack de langue CIBLE, donc un tome anglais porte la version
       anglaise ;
    3. **`RAPPORT.md` liste les images insérées**, avec leur personnage et leur graine.

    Le quatrième — « aucune insertion dans un fichier destiné à autrui » — est une absence :
    ce lot n'ajoute aucune fonction d'export, de partage, de publication ni de mise en ligne,
    et n'en facilite aucune. L'usage arrêté est privé.

    ⚠ **La brique d'illustration n'est PAS importée ici**, et elle ne doit pas l'être : le
    light novel doit continuer de rendre un tome sur une machine où `illustration/` a été
    effacé. Tout passe par `core/insertion.py`, qui ne connaît que des chemins de fichiers et
    des sidecars JSON.

    ⚠ **`--render-only` n'insère rien**, et c'est voulu : il rejoue le Markdown déjà
    assemblé, qui porte déjà ses marqueurs si le run précédent en avait posé. Y réinsérer
    doublerait chaque image à chaque rendu."""
    reglages = dict(config.get("illustration") or {})
    if not reglages.get("inserer_dans_sorties"):
        return full_md, []
    dossier = insertion_mod.dossier_retenues(config["chemins"]["sources"], project)
    images_retenues = insertion_mod.retenues(dossier)
    if not images_retenues:
        _warn(reporter, f"[illustration] insertion armée mais aucune image retenue sous "
                        f"{dossier} — rien n'est inséré. « Garder » déplace une image "
                        f"produite depuis build/ vers ce dossier.")
        return full_md, []
    position = str((reglages.get("insertion") or {}).get("position") or
                   insertion_mod.DEBUT_CHAPITRE)
    if position not in insertion_mod.POSITIONS:
        _warn(reporter, f"[illustration] illustration.insertion.position : "
                        f"« {position} » inconnu — repli sur "
                        f"« {insertion_mod.DEBUT_CHAPITRE} ».")
        position = insertion_mod.DEBUT_CHAPITRE
    sortie, inserees = insertion_mod.inserer(
        full_md, images_retenues, legende=insertion_mod.legende_du_pack(pack),
        depuis=build_dir, position=position)
    for collision in insertion_mod.collisions(sortie):
        # Le risque nommé par `pipeline/images.py` : « chaque document renumérote ses médias
        # depuis 1 ». Une illustration ne vient d'aucun document, mais on le VÉRIFIE.
        _warn(reporter, f"[illustration] collision de nom d'image — {collision}")
    reporter.info(f"illustrations générées : {len(inserees)} insérée(s) "
                  f"({insertion_mod.LIBELLES_POSITION[position]}), légende obligatoire "
                  f"sous chacune")
    return sortie, inserees


def process_volume(project: str, volume: str, config: dict,
                   reporter: Reporter | None = None,
                   render_only: bool = False, force: bool = False,
                   restart_from: str | None = None, optimize: bool = False,
                   only_chapter: int | None = None) -> bool:
    """Renvoie True si le tome a été traité jusqu'au bout, False s'il a été arrêté
    en cours de route (Ctrl+C / --stop) — utile pour --all (cf. run.py) : décide si
    la série doit continuer sur le tome suivant ou s'arrêter là."""
    # ⚠ Validés ICI, à l'entrée, et pas plus bas : `project` et `volume` viennent de la ligne
    # de commande et deviennent ensuite des composants de chemin à une quinzaine d'endroits —
    # `sources/<projet>/glossaire.yaml`, `build/<projet>/<tome>/…`, les checkpoints. Un seul
    # de ces endroits laissé sans garde suffit à écrire ailleurs que là où l'utilisateur
    # croit ; les valider une fois à la frontière les couvre tous.
    project = chemins.segment(project, "projet")
    volume = chemins.segment(volume, "tome")
    reporter = reporter or Reporter()
    dry = config["options"].get("dry_run", False)
    verbose = config["options"].get("verbose", False)

    if restart_from is not None and restart_from not in STAGES:
        raise SystemExit(f"Étape inconnue : {restart_from}. Choix : {', '.join(STAGES)}")

    def _do(stage: str) -> bool:
        """Faut-il (re)calculer cette étape ? Oui si pas de restart_from, ou si l'étape
        est à `restart_from` ou après. Les étapes antérieures sont relues du cache."""
        return restart_from is None or STAGES.index(stage) >= STAGES.index(restart_from)

    def _force(stage: str) -> bool:
        """Étape à RECALCULER de force (on vide son cache) : seulement avec restart_from,
        pour l'étape ciblée et toutes les suivantes."""
        return restart_from is not None and STAGES.index(stage) >= STAGES.index(restart_from)

    sources_dir = Path(config["chemins"]["sources"])
    vol_dir = sources_dir / project / volume
    build_dir = Path(config["chemins"]["build"]) / project / volume
    build_dir.mkdir(parents=True, exist_ok=True)
    chap_dir = build_dir / "chapters"
    ckpt_root = build_dir / ".checkpoints"
    full_md_path = build_dir / f"{project}_{volume}.md".replace(" ", "_")

    if render_only:
        if not full_md_path.exists():
            raise SystemExit(f"Rien à rendre : {full_md_path}")
        if only_chapter is not None:
            reporter.info(f"⚠ --chapitre {only_chapter} est ignoré avec --render-only : "
                         "le rendu porte toujours sur le Markdown COMPLET du tome déjà généré.")
        produced = render(full_md_path, build_dir, config, warn=lambda m: _warn(reporter, m))
        reporter.finish([p.name for p in produced])
        return True

    if force:  # tout refaire (ou juste le chapitre ciblé si --chapitre est aussi donné)
        if only_chapter is not None:
            shutil.rmtree(ckpt_root / f"ch{only_chapter:02d}", ignore_errors=True)
            (chap_dir / f"ch{only_chapter:02d}.md").unlink(missing_ok=True)
        else:
            for p in (ckpt_root, chap_dir):
                shutil.rmtree(p, ignore_errors=True)
            full_md_path.unlink(missing_ok=True)

    install_sigint(reporter)
    clear_stop(build_dir)  # repart propre (efface un STOP résiduel d'un crash précédent)

    # Lot 32 — la PHASE. Canal neuf, muet en console (`core/reporter.Reporter.phase`), et
    # c'est lui qui rend la barre monotone : sans lui, `chapter(ci, n)` et `block(bi, n)`
    # sont deux compteurs sans rapport que rien ne distingue. Mesuré sur un tome de 25
    # chapitres : 66 reculs, 6 dénominateurs, 89,7 % d'un run de 12 h sans estimation
    # (`docs/mesures/progression-2026-09-05.md`).
    reporter.phase("preparation")
    plan = scan_volume(vol_dir, config, build_dir)
    reporter.volume(plan)

    gname = config["chemins"].get("glossaire_fichier", GLOSSAIRE_DEFAUT)
    glo_path = sources_dir / project / gname
    glo = glossary.load(glo_path)
    if not glo:
        reporter.info("(pas de glossaire pour ce projet — il sera créé à partir des relevés du terminologue)")
    # Le pack de langue cible, résolu UNE fois pour tout le tome : il porte le guide de style
    # et les consignes que le code construit (naturalisation, titre de chapitre).
    pack = resoudre_pack(config)
    # Règles typographiques de la langue cible, compilées UNE fois pour le tome. Elles
    # servent au garde-fou « le modèle a régurgité le guide de style », dont le titre
    # cherché dépend du pack.
    typo = ty.Typographie.depuis_pack(pack, config.get("rendu"))
    style_txt = _read(_chemin_style_guide(config, pack))
    max_chars = config["decoupage"]["max_block_chars"]
    max_tokens_bloc = config["decoupage"].get("max_block_tokens")
    marge_partie = config["decoupage"].get("marge_partie_bloc", 0.20)
    budget = config["decoupage"].get("max_input_tokens", 12000)
    # Budgets de tokens pour le GLOSSAIRE injecté dans les prompts (anti-débordement) :
    #   - agents principaux : ~moitié du budget d'entrée ;
    #   - terminologue : plus serré (il n'a besoin que des noms/genres pour s'aligner).
    glo_budget_main = min(12000, max(2000, budget // 2))
    glo_budget_term = min(6000, max(1500, budget // 3))
    glo_txt = glossary.to_text(glo, max_tokens=glo_budget_main,
                               masquer_non_romanises=True)
    ref_order = config["langues"]["priorite_sens"]
    dash = config["rendu"]["dialogue_dash_in_text"]
    st = config["rendu"]["styles"]

    llm = None if dry else LLM(
        base_url=config["llm"]["base_url"], api_key=config["llm"]["api_key"],
        timeout=config["llm"]["timeout"], max_retries=config["llm"]["max_retries"],
        think=config["llm"].get("think"),
                               debit_plancher=config["llm"].get("debit_plancher_tok_s"))
    agents = build_agents(config, llm, dry_run=dry)
    _wire_reporter(llm, agents, reporter)

    def _agent_actif(nom: str) -> bool:
        """Un agent est DÉSACTIVÉ si son modèle est null/absent dans config.modeles
        (build_agents met alors agents[nom] = None) : son étape est SAUTÉE et le texte
        passe inchangé à la suivante. Le traducteur ne peut pas être désactivé."""
        return config["modeles"].get(nom) is not None

    if not _agent_actif("traducteur"):
        raise SystemExit("modeles.traducteur ne peut pas être désactivé (null) : "
                         "sans traduction, le pipeline n'a rien à produire.")

    pivot = plan.pivot
    others = [c for c in plan.langs if c != pivot]
    # Pivot en écriture non latine : le terminologue n'a alors AUCUNE forme latine sous les
    # yeux (`others` est vide sur une œuvre mono-source), et rien dans le nom du champ `nom`
    # ne lui dit qu'il doit produire du français. Sans ces deux injections, il recopie le
    # headword source — et le traducteur, à qui le glossaire le présente comme « le rendu à
    # respecter », obéit.
    if not others:
        _warn(reporter, f"aucune source de référence : le traducteur travaille sur le seul "
                        f"pivot [{pivot}], sans recoupement possible")
    pivot_cjk = glossary_lang.pivot_est_cjk(pivot, plan.langs[pivot].full_text)
    lectures_pivot = plan.langs[pivot].lectures if pivot_cjk else {}
    consigne_cjk = ("\n\n" + glossary_lang.consigne_pivot_cjk(pack)) if pivot_cjk else ""
    if pivot_cjk:
        reporter.info(f"pivot « {pivot} » en écriture non latine — consigne de romanisation "
                      f"active" + (f" · {len(lectures_pivot)} lecture(s) relevée(s) à "
                                   f"l'extraction" if lectures_pivot else
                                   " · aucune lecture disponible (source sans furigana)"))

    # Détection complémentaire des chapitres :
    #   1) par nom de fichier (multi-fichiers) puis structurelle — déjà faites au scan ;
    #   2) repli LLM. En mode "auto" : LLM uniquement sur les sources où le déterministe a
    #      échoué (<2 chapitres). En mode "llm" : LLM sur toutes les sources.
    mode_det = config["decoupage"].get("detection", "auto")
    if not dry and mode_det in ("llm", "auto") and _agent_actif("terminologue"):
        # Motifs ADDITIONNELS : les défauts multilingues restent actifs (cf. detect_chapters).
        pats = config["decoupage"]["chapter_patterns"] or None
        model = config["modeles"]["terminologue"]
        temp = config["temperatures"]["terminologue"]
        extra = config["llm"].get("extra_directive", "")
        targets = (list(plan.langs.items()) if mode_det == "llm"
                   else [(c, s) for c, s in plan.langs.items() if len(s.chapters) < 2])
        if targets:
            reporter.stage("détection des chapitres (LLM, secours)")
            for c, src in targets:
                src.chapters = split.detect_chapters_llm(src.full_text, llm, model,
                                                         patterns=pats, temperature=temp,
                                                         extra_directive=extra)
            reporter.info("chapitres — " + ", ".join(f"{c}:{len(s.chapters)}" for c, s in plan.langs.items()))

    # Alignement ANCRÉ SUR LE PIVOT (et non sur le minimum) : le pivot fixe le nombre de
    # chapitres. Une source au même nombre s'aligne chapitre par chapitre ; sinon, son texte
    # complet est découpé proportionnellement. La sur-/sous-détection d'une référence
    # (en=15, zh=1) ne fait donc plus s'effondrer tout l'alignement.
    n_ch = len(plan.langs[pivot].chapters) if plan.langs else 0
    if only_chapter is not None and not (1 <= only_chapter <= n_ch):
        raise SystemExit(f"--chapitre {only_chapter} hors limites : ce Tome a {n_ch} chapitre(s) (1 à {n_ch}).")
    ref_chapter_text: dict[str, list[str]] = {}
    realign_notes: list[str] = []
    pivot_sizes = [len(strip_images(ch.body)) for ch in plan.langs[pivot].chapters] if plan.langs else []
    for c in others:
        src = plan.langs[c]
        if len(src.chapters) == n_ch:
            bodies = [strip_images(ch.body) for ch in src.chapters]
            # ⚠ Un nombre de chapitres IDENTIQUE ne garantit PAS un alignement 1:1 : il
            # suffit qu'une frontière soit mal placée d'un côté pour décaler le contenu.
            # Cas réel (roman B Vol.2) : le chapitre 15 japonais contenait en plus tout
            # l'épilogue, que le traducteur a donc traduit une 2e fois en fin de ch15.
            bodies, repares = split.realign_chapters(bodies, pivot_sizes)
            for run in repares:
                nums = ", ".join(str(i + 1) for i in run)
                note = (f"source [{c}] : frontières de chapitre recalées sur le pivot pour les "
                        f"chapitres {nums} (le découpage de cette source divergeait — sans ça, "
                        f"le traducteur reçoit du texte hors-chapitre et le traduit en double)")
                _warn(reporter, note)
                realign_notes.append(note)
            ref_chapter_text[c] = bodies
        else:
            # ⚠ Les deux sources n'ont pas le même découpage — le cas ORDINAIRE dès qu'une
            # référence est un EPUB, qui fait des « chapitres » de sa couverture, de son
            # sommaire et de son colophon, et porte parfois une postface que le pivot n'a pas
            # traduite. On APPARIE les unités par proportions au lieu de redécouper le texte
            # entier par nombre de paragraphes égal (`split_into_n`) : sur des chapitres
            # inégaux, ce dernier donnait au prologue de roman B Vol.3 les 25 896 premiers
            # caractères du japonais — soit trois sections du chapitre 1 — et pas un seul des
            # 5 chapitres n'était aligné.
            app = split.apparier_chapitres(
                [strip_images(ch.body) for ch in src.chapters], pivot_sizes)
            note = (f"source [{c}] : {len(src.chapters)} chapitre(s) détecté(s) contre {n_ch} "
                    f"dans le pivot → appariés par proportions")
            _warn(reporter, note)
            realign_notes.append(note)
            for detail in app.notes:
                realign_notes.append(f"source [{c}] : {detail}")
            # Le DÉTAIL de l'appariement, chapitre par chapitre : sans lui, on ne peut pas
            # savoir a posteriori ce qui a été mis en regard de quoi — c'est ainsi qu'un
            # épilogue apparié à une postface est passé inaperçu.
            for i, idx in enumerate(app.indices):
                if not idx:
                    continue
                titres = " · ".join(
                    (src.chapters[k].title or f"unité {k + 1}")[:40] for k in idx)
                realign_notes.append(
                    f"source [{c}] : ch.{i + 1} « "
                    f"{(plan.langs[pivot].chapters[i].title or '')[:40]} » ← {titres}")
            ref_chapter_text[c] = app.groupes

    consigne_dash = (
        "Tirets de dialogue : ÉCRIS « — » en tête de réplique." if dash else
        "Tirets de dialogue : N'ÉCRIS PAS de tiret (le style l'ajoute automatiquement)."
    )
    gabarits = (
        'Dialogue → sur TROIS LIGNES SÉPARÉES, exactement comme ceci (avec de vrais retours '
        'à la ligne, jamais tout sur une seule ligne) :\n'
        f'::: {{.dialogue custom-style="{st["dialogue"]}"}}\n'
        '<texte>\n'
        ':::\n'
        'Pensée → même principe, sur TROIS LIGNES SÉPARÉES :\n'
        f'::: {{.pensee custom-style="{st["pensee"]}"}}\n'
        '<texte>\n'
        ':::\n'
        'Encadré game-menu → paragraphe normal avec ***gras+italique***\n'
        'Narration → paragraphe simple (sans balise)\n'
        'IMAGES : si le texte reçu contient déjà une ligne commençant par `<!-- IMG:`, conserve-la '
        'exactement, à sa place — n\'en ajoute JAMAIS une nouvelle, n\'en modifie jamais le contenu.\n'
        '⚠ ERREUR FRÉQUENTE À NE JAMAIS FAIRE : écrire `::: {.dialogue ...} texte :::` tout sur '
        'UNE SEULE ligne avec des espaces. Ça ne fonctionne PAS (le logiciel de conversion ignore '
        'silencieusement une fence qui n\'est pas sur sa propre ligne) — la ligne d\'ouverture '
        '`::: {...}`, le texte, et la ligne de fermeture `:::` sont TOUJOURS trois lignes distinctes.\n'
        'SÉPARE LES RÉPLIQUES : chaque réplique « … » va sur SON PROPRE paragraphe, dans un bloc '
        'Dialogue — jamais fondue dans la narration. Si un paragraphe reçu contient « réplique » '
        'récit « réplique », DÉCOUPE-le : un bloc Dialogue par réplique, la narration à part. '
        'Conserve les « » (la conversion les retire). EXCEPTION : une incise d\'attribution qui '
        'SUIT une réplique et COMMENCE par un verbe de parole/pensée (dit-il, hurla-t-elle, pensa, '
        'répondit, demanda…) reste DANS le même bloc Dialogue, jusqu\'à la fin de phrase (; . ! ? …). '
        'Un terme seulement CITÉ en pleine narration (« Leprechauns ») n\'est PAS une réplique : '
        'laisse-le dans le paragraphe de narration.'
    )

    chapter_mds: list[str] = []
    report_sections: list[str] = []
    t_start = time.perf_counter()
    # Compteurs de suivi (alimentent le résumé chiffré de RAPPORT.md) : mis à jour par
    # _try_with_temp_retry et incrémentés directement pour vide/emballement/reprise cache.
    stats: dict[str, int] = {"blocs_ok": 0, "vide": 0, "emballement": 0, "perte_mots": 0,
                             "titre_perdu": 0, "repetition": 0, "retry_temp_reduite": 0,
                             "retry_temp_relevee": 0, "recupere_par_retry": 0,
                             "forces_appliques": 0, "blocs_redecoupes": 0,
                             "recupere_par_redecoupage": 0, "recupere_par_deboucle": 0,
                             # Signaux DIRECTS du client LLM (cf. _RESPLIT_REASONS). Ils
                             # doivent exister ici : le résumé les lit en accès direct.
                             "troncature_length": 0, "thinking_overflow": 0,
                             "cjk_residuel": 0, "cap_sature": 0, "timeout": 0}
    # Entrées de glossaire encore en écriture source, accumulées sur tout le tome.
    glossaire_a_romaniser: list[str] = []
    # Remplacements `force: true` REFUSÉS par les garde-fous d'accord (cf. _enforce_force) :
    # ce ne sont pas des erreurs mais des cas délibérément laissés au correcteur,
    # listés dans RAPPORT.md pour que tu puisses compléter le glossaire (ex. ajouter `genre:`).
    force_refus: list[str] = []
    # Ratios minimaux (mots sortie / mots entrée) sous lesquels un bloc « préservation »
    # est considéré comme ayant perdu du contenu (repli + AMBIGU). None = pas de contrôle
    # (le traducteur peut légitimement condenser/synthétiser plusieurs sources).
    ratios = config.get("garde_fous", {}).get("perte_mots_ratio", {})
    ratio_trad = ratios.get("traducteur")     # None par défaut : le traducteur peut condenser
    ratio_corr = ratios.get("correcteur", 0.75)
    ratio_mep = ratios.get("mise_en_page", 0.90)
    temp_factor = config.get("garde_fous", {}).get("retry_temperature_facteur", 0.4)
    # Redécoupage-relance : un bloc qui échoue pour cause de TAILLE est coupé en deux et
    # rejoué, au lieu d'être abandonné (et réinjecté en langue source). Cf. _RESPLIT_REASONS.
    gf = config.get("garde_fous", {})
    resplit_on = gf.get("redecoupage_sur_echec", True)
    resplit_depth = max(0, int(gf.get("redecoupage_profondeur_max", 2)))
    resplit_min = max(1, int(gf.get("redecoupage_taille_min", 800)))
    # Nombre de caractères CJK tolérés dans une sortie française avant de la juger non
    # traduite. 0 = contrôle désactivé.
    cjk_seuil = max(0, int(gf.get("cjk_residuel_seuil", 1)))
    # Escalade : un timeout isolé est un bloc trop long (on redécoupe et on continue) ; N
    # blocs qui expirent d'affilée, c'est le SERVEUR qui ne répond plus. Sans ce seuil, le
    # tome se remplirait de japonais un bloc après l'autre, chacun payé au prix fort.
    max_timeouts = max(0, int(gf.get("abandon_apres_timeouts_consecutifs", 3)))
    timeouts_consecutifs = 0
    # Curseur de reformulage du TRADUCTEUR (cf. config.yaml > naturalisation), injecté dans
    # le message du traducteur (# CONSIGNE DE NATURALISATION). Le correcteur ne reformule
    # plus : son garde-fou de perte de mots n'est donc plus desserré par l'intensité.
    intensite_nat = min(1.0, max(0.0, float(config.get("naturalisation", {}).get("intensite", 0.35))))
    consigne_nat = _consigne_naturalisation(intensite_nat, pack)

    # Modèle du traducteur (chaîne), pour la traduction COURTE et non-thinking des titres.
    _trad_spec = config["modeles"]["traducteur"]
    trad_model = _trad_spec["model"] if isinstance(_trad_spec, dict) else _trad_spec
    # Estimation du temps : nb de blocs estimé par chapitre (≈ caractères / taille de bloc),
    # affiné par le temps réel moyen par bloc au fil du tome (cf. fin de boucle chapitre).
    # La taille de bloc est celle RÉELLEMENT dérivée pour chaque chapitre (`max_block_tokens`
    # la resserre sur un pivot dense) : l'estimer sur `max_chars` seul rendrait l'ETA ~4×
    # trop optimiste en japonais, sur un run qui dure déjà des heures.
    est_blocs_par_chap = []
    for c in plan.langs[pivot].chapters:
        taille = split.limite_caracteres(c.body, max_chars, max_tokens_bloc)
        est_blocs_par_chap.append(max(1, (len(c.body) + taille - 1) // taille))
    blocs_done = 0
    time_done = 0.0

    try:
        # Le CHAPITRE est la seule unité monotone du light novel : le bloc redémarre à 1 à
        # chaque étage de chaque chapitre. Il devient un détail affiché, pas un avancement.
        reporter.phase("chapitres")
        for ci in range(n_ch):
            pivot_chap = plan.langs[pivot].chapters[ci]
            title = pivot_chap.title or f"Chapitre {ci + 1}"
            out_md = chap_dir / f"ch{ci + 1:02d}.md"

            if only_chapter is not None and (ci + 1) != only_chapter:
                # Chapitre HORS CIBLE : jamais touché — on réutilise son .md s'il existe,
                # sinon on l'exclut simplement de cet assemblage (--chapitre sert à
                # retester UN chapitre déjà généré au moins une fois, pas à en produire
                # d'autres au passage).
                if out_md.exists():
                    chapter_mds.append(_read(out_md))
                else:
                    reporter.chapter(ci + 1, n_ch, title)
                    reporter.info(f"hors cible (--chapitre {only_chapter}) et jamais généré — "
                                 f"exclu de cet assemblage")
                continue

            if only_chapter is not None and restart_from is None:
                # --chapitre seul (sans --from) → redo complet de CE chapitre uniquement,
                # même s'il existait déjà (c'est tout le but : retester après une modif).
                shutil.rmtree(ckpt_root / f"ch{ci + 1:02d}", ignore_errors=True)
                out_md.unlink(missing_ok=True)

            if out_md.exists() and restart_from is None and only_chapter is None:
                reporter.chapter(ci + 1, n_ch, title)
                reporter.info("déjà fait — sauté (--force pour refaire)")
                chapter_mds.append(_read(out_md))
                continue

            if should_stop(build_dir):
                raise StopRequested()
            reporter.chapter(ci + 1, n_ch, title)
            ck = ckpt_root / f"ch{ci + 1:02d}"
            t_chap_start = time.perf_counter()

            def _ck(stage_key: str) -> Path:
                d = ck / stage_key
                if _force(stage_key):
                    shutil.rmtree(d, ignore_errors=True)   # restart_from → recalcul de cette étape
                return d

            # Le titre traduit est mis en cache dans `chNN/title.txt`, à CÔTÉ des dossiers
            # d'étape et non dedans : `_ck` ne pouvait donc jamais le purger, et
            # `--from traduction` laissait survivre un titre issu du run précédent — un
            # titre resté en japonais traversait ainsi toutes les relances. Il est produit
            # par le traducteur : il appartient à cette étape.
            if _force("traduction"):
                (ck / "title.txt").unlink(missing_ok=True)

            # On GARDE les marqueurs <!-- IMG --> inline dans le pivot : les images
            # restent ancrées à leur position d'origine (au lieu d'être retirées puis
            # réinjectées proportionnellement, ce qui les éparpillait).
            pivot_clean = pivot_chap.body
            pivot_has_images = bool(_IMG_RE.search(pivot_clean))
            ref_clean = {c: ref_chapter_text[c][ci] for c in others
                         if ci < len(ref_chapter_text[c]) and ref_chapter_text[c][ci].strip()}

            # Découpage en blocs + alignement proportionnel des références
            blocks = split.split_blocks(pivot_clean, max_chars, has_parts=bool(pivot_chap.parts),
                                        part_tolerance=marge_partie,
                                        max_tokens=max_tokens_bloc) or [""]
            n = len(blocks)
            # Alignement des références sur les TAILLES réelles des blocs du pivot, et non
            # sur leur nombre de paragraphes (`split_into_n`) : les deux découpages
            # divergeaient dès que les paragraphes n'étaient pas homogènes, la source
            # « alignée » sur un bloc couvrait une autre tranche du chapitre, et le
            # traducteur retraduisait ce hors-bloc — d'où des passages entiers en double
            # sur les chapitres à 1 ou 2 blocs. Cf. split.split_proportional.
            ref_blocks = {c: split.split_proportional(t, [len(b) for b in blocks])
                          for c, t in ref_clean.items()}
            # Empreinte du découpage du pivot : elle protège les trois étages indexés sur
            # CE partitionnement (terminologie, traduction, correction). La mise en page a
            # le sien, calculé plus bas sur le texte français.
            sig_blocs = _signature_blocs(blocks)

            def _lectures_du_bloc(bloc: str, maxi: int = 40) -> str:
                """Section « LECTURES » : uniquement les gloses dont la graphie apparaît
                dans CE bloc. C'est ce qui rend l'injection quasi gratuite — le lexique du
                tome fait ~1 900 entrées, un bloc en concerne quelques dizaines.

                Bornée à `maxi` : au-delà, ce n'est plus une aide à la romanisation des
                noms propres mais une recopie du lexique, qui noierait la consigne."""
                if not lectures_pivot:
                    return ""
                vues = [(base, lec) for base, lec in lectures_pivot.items() if base in bloc]
                if not vues:
                    return ""
                # Les plus longues d'abord : un nom propre composé est plus informatif
                # qu'un kanji isolé, et c'est lui qu'on veut voir survivre à la troncature.
                vues.sort(key=lambda kv: len(kv[0]), reverse=True)
                lignes = "\n".join(f"- {base} = {lec}" for base, lec in vues[:maxi])
                return ("\n\n# LECTURES (furigana) — prononciation des graphies de ce bloc, "
                        "pour la romanisation\n" + lignes)

            def _ref_text_for_terminologie(bi: int, cap_tokens: int = 2500) -> str:
                """Texte(s) de référence étranger(s) aligné(s) sur le bloc `bi`, donné en
                plus du FR au terminologue — pour qu'il puisse repérer et noter le mot
                SOURCE correspondant à un terme français (champ `termes_source`), utile
                à l'agent traducteur ensuite. Budget volontairement plus petit que celui
                du traducteur (le terminologue n'a besoin que d'un aperçu, pas du détail)."""
                refs = {c: ref_blocks[c][bi] for c in ref_blocks
                        if bi < len(ref_blocks[c]) and ref_blocks[c][bi].strip()}
                if not refs:
                    return ""
                kept = [c for c in ref_order if c in refs] + [c for c in refs if c not in ref_order]
                parts, used = [], 0
                for c in kept:
                    t = refs[c]
                    tok = _est_tokens(t)
                    if used and used + tok > cap_tokens:
                        break
                    if used + tok > cap_tokens:
                        t = _truncate_tokens(t, cap_tokens - used)
                    parts.append(f"--- SOURCE [{c}] ---\n{t}")
                    used += _est_tokens(t)
                return "\n\n".join(parts)

            # 1) Terminologie — PAR BLOC, INCRÉMENTALE et CONTEXTUELLE.
            #    Chaque bloc voit le glossaire DÉJÀ construit (blocs précédents) et
            #    l'enrichit/le corrige aussitôt : ça évite les doublons et les décisions
            #    contradictoires d'un bloc à l'autre (genre, orthographe, variantes de noms).
            divergences: list[str] = []
            if not _do("terminologie"):
                # On reprend après la terminologie → glossaire = celui du disque (édité par toi).
                glo = glossary.load(glo_path) or glossary.empty()
                glo_txt = glossary.to_text(glo, max_tokens=glo_budget_main,
                                           masquer_non_romanises=True)
                reporter.stage("terminologie")
                reporter.info("réutilisée — glossaire chargé du disque (non recalculé)")
            else:
                reporter.stage("terminologie")
                term_ck = ck / "terminologie"
                if _force("terminologie"):
                    shutil.rmtree(term_ck, ignore_errors=True)   # recalcul forcé
                # Cette boucle ne passe pas par `_run_blocks` (elle fusionne le glossaire au
                # fil des blocs) : elle doit sceller son découpage elle-même. Un relevé de
                # terminologie rejoué en face du mauvais bloc est d'autant plus pernicieux
                # qu'il est re-fusionné SANS appel LLM, donc sans rien coûter ni signaler.
                _sceller_decoupage("terminologie", term_ck, sig_blocs, reporter)
                live = glossary.load(glo_path) or glossary.empty()  # existant = graine + contexte
                live_index = glossary_build.build_index(live)  # évite le scan linéaire de _find_any
                resumed = 0
                # Cache du rendu (`to_text`) : la plupart des blocs de narration pure
                # ne révèlent aucun nouveau terme — inutile de re-sérialiser tout le
                # glossaire quand le bloc précédent n'a rien changé (cf. merge_notes ci-dessous).
                glo_dirty = True
                cached_glo_ctx = ""
                for bi in range(n):
                    f = term_ck / f"{bi:03d}.txt"
                    cached = f.read_text(encoding="utf-8") if f.exists() else ""
                    if cached.strip():
                        notes = cached
                        resumed += 1
                    else:
                        reporter.block(bi + 1, n)
                        if glo_dirty:
                            cached_glo_ctx = glossary.to_text(live, max_tokens=glo_budget_term)
                            glo_dirty = False
                        glo_ctx = cached_glo_ctx
                        ref_txt = _ref_text_for_terminologie(bi)
                        ref_section = (f"\n\n# SOURCE(S) ÉTRANGÈRE(S) (pour repérer le mot d'origine — "
                                      f"champ termes_source)\n{ref_txt}" if ref_txt else "")
                        term_llm = agents["terminologue"].llm   # peut être un client d'endpoint différent du défaut
                        t0 = time.perf_counter()
                        tok0 = term_llm.stats["tokens_generes"] if (verbose and term_llm) else 0
                        notes = agents["terminologue"].run(
                            f"{glo_ctx}\n\n{style_txt}{consigne_cjk}\n\n"
                            f"# BLOC {bi + 1}/{n} ({pivot})\n{blocks[bi]}"
                            f"{_lectures_du_bloc(blocks[bi])}{ref_section}",
                            dry_payload=RIEN_A_SIGNALER, max_tokens=1024)
                        if verbose and term_llm:
                            dt = time.perf_counter() - t0
                            dtok = term_llm.stats["tokens_generes"] - tok0
                            reporter.verbose(f"[terminologie] bloc {bi + 1}/{n} : {dt:.1f}s · ~{dtok} tok générés "
                                             f"· ~{(dtok / dt if dt > 0 else 0):.1f} tok/s")
                        if not notes.strip():
                            notes = RIEN_A_SIGNALER
                        f.write_text(notes, encoding="utf-8")
                        if should_stop(build_dir):
                            raise StopRequested()
                    added = glossary_build.merge_notes(live, notes, index=live_index)  # incrémente + corrige tout de suite
                    if any(added.values()):
                        glo_dirty = True
                    divergences += [ln.strip()[1:].strip() for ln in notes.splitlines()
                                    if ln.strip().startswith("- ⚠")]
                if resumed and resumed < n:
                    reporter.info(f"terminologie : {resumed}/{n} bloc(s) repris du cache")
                glossary.save(live, glo_path)               # glossaire construit/mis à jour
                glo = live
                glo_txt = glossary.to_text(glo, max_tokens=glo_budget_main,
                                           masquer_non_romanises=True)
            n_verif = sum("⚠" in (p.get("description") or "") for p in glo.get("personnages", []))
            cnt = glossary.counts(glo)
            résumé = ", ".join(f"{k} {v}" for k, v in cnt.items()) or "vide"
            reporter.info(f"glossaire ({glossary.total(glo)}) : {résumé}"
                          + (f" — ⚠ {n_verif} à vérifier" if n_verif else ""))
            # Entrées SANS rendu français : masquées au traducteur (elles lui ordonneraient
            # de recopier la graphie source), donc invisibles s'il n'y avait pas cette
            # remontée. Elles sont à romaniser à la main, ou par une relance du terminologue.
            a_romaniser = glossary_lang.auditer(glo)
            for ligne in a_romaniser:
                if ligne not in glossaire_a_romaniser:
                    glossaire_a_romaniser.append(ligne)
            if a_romaniser:
                _warn(reporter, f"glossaire : {len(a_romaniser)} entrée(s) sans rendu français "
                                f"— masquée(s) au traducteur (cf. RAPPORT.md)")

            # 1bis) Optimisation du glossaire APRÈS la terminologie (dédoublonnage/fusion des
            #       variantes que le déterministe laisse passer, ex. Fwedo→Feodor) — AVANT que
            #       les autres agents ne l'utilisent. Seulement si la terminologie a tourné.
            if (_do("terminologie") and not dry and _agent_actif("glossariste")
                    and config["langues"].get("optimiser_apres_terminologie", True)):
                if should_stop(build_dir):
                    raise StopRequested()
                optimize_glossary_file(glo_path, agents, reporter, dry=dry, verbose=verbose)
                glo = glossary.load(glo_path) or glossary.empty()
                glo_txt = glossary.to_text(glo, max_tokens=glo_budget_main,
                                           masquer_non_romanises=True)

            # Formes CJK qu'il est LÉGITIME de retrouver dans le texte français : entrées
            # `traduire: false` et entrées pas encore romanisées. Calculées UNE fois, après
            # la finalisation du glossaire du chapitre (optimisation comprise).
            cjk_ok = glossary_lang.formes_cjk_autorisees(glo)

            # 2) Traduction / amélioration (prompt borné par un budget de tokens)
            reporter.stage("traduction")

            def _force_fr(txt: str) -> str:
                """Applique les traductions imposées (`force: true`) DÈS LA SORTIE DU
                TRADUCTEUR, et non plus seulement sur le Markdown assemblé en fin de tome.

                Deux bénéfices : (1) le correcteur voit déjà la terminologie
                canonique et ne dépense plus d'appels LLM à corriger ce que le
                déterministe corrigerait de toute façon ; (2) il tourne APRÈS ce
                forçage, donc il rattrape les accords voisins que le regex ne sait pas
                réécrire (cf. la limite documentée dans `_enforce_force`).
                Volontairement PAS de seconde passe en fin de tome : réappliquer le regex
                sur un texte que les agents ont depuis restructuré risquerait de casser des
                phrases sans rien apporter (décision explicite)."""
                if not config["langues"].get("appliquer_traductions_forcees", True):
                    return txt
                txt, n = _enforce_force(txt, glo, force_refus, accord=pack.accorder())
                stats["forces_appliques"] += n
                return txt

            def _trad_once(pivot_block: str, refs: dict[str, str],
                           dernier_recours: bool = True) -> tuple[str, bool, str | None]:
                """UN passage du traducteur sur `pivot_block`, avec `refs` = le texte de
                référence par langue déjà aligné sur CE texte. Renvoie (sortie, ok, motif).
                Extrait de `_trad` pour être rejouable sur un sous-bloc : le prompt, le
                budget d'entrée et le plafond de sortie sont tous recalculés sur le texte
                reçu — c'est ce qui rend le redécoupage-relance efficace."""
                if plan.mode == "amelioration":
                    pivot_label = f"# BROUILLON FR À AMÉLIORER\n{pivot_block}"
                    refs_label = "# SOURCES DE RÉFÉRENCE (pour corriger le sens)"
                else:
                    pivot_label = f"# TEXTE PIVOT [{pivot}] (référence de structure)\n{pivot_block}"
                    refs_label = "# AUTRES SOURCES À RECOUPER"
                # Le glossaire (mis à jour par le terminologue) porte la terminologie ;
                # la consigne de naturalisation pilote l'intensité de reformulage du traducteur.
                header = (f"{glo_txt}\n\n{style_txt}\n\n"
                          f"# CONSIGNE DE NATURALISATION\n{consigne_nat}\n\n{pivot_label}")

                # Références : on garde les plus prioritaires, puis on tronque pour tenir le budget
                avail = budget - _est_tokens(header) - 96
                refs = {c: t for c, t in refs.items() if t.strip()}
                kept = [c for c in ref_order if c in refs] + [c for c in refs if c not in ref_order]
                while len(kept) > 1 and sum(_est_tokens(refs[c]) for c in kept) > avail:
                    kept.pop()
                if kept and sum(_est_tokens(refs[c]) for c in kept) > avail:
                    per = max(150, avail // len(kept))
                    for c in kept:
                        refs[c] = _truncate_tokens(refs[c], per)
                ref_text = "\n\n".join(f"--- SOURCE [{c}] ---\n{refs[c]}"
                                       for c in kept if refs[c].strip()) or "(aucune autre source)"
                user = f"{header}\n\n{refs_label}\n{ref_text}"
                cap = _out_cap(pivot_block)
                # Témoin : le plafond DUR de `out_cap` n'est atteignable qu'avec une langue
                # dense (il faudrait 12 000 caractères latins dans un bloc). Le voir saturer
                # dit que `max_block_tokens` est mal dimensionné pour ce pivot — c'est ce
                # qui aurait rendu le défaut visible dès le premier chapitre du Vol.1, où
                # les 8 blocs sur 8 le saturaient.
                if cap >= quality.CEIL_DEFAUT:
                    stats["cap_sature"] += 1
                # `_repair_headings` en post-traitement : un titre `##` rendu en **gras**
                # est corrigé AVANT le diagnostic, donc `titre_perdu` ne se déclenche plus
                # sur une traduction par ailleurs bonne (cause n°1 des blocs réinjectés en
                # anglais). Le pivot est capturé par la clôture (mode traduction = source).
                return _try_with_temp_retry(
                    agents["traducteur"], user, pivot_block, cap, stats,
                    min_ratio=ratio_trad, temp_factor=temp_factor,
                    postprocess=lambda o: _repair_headings(pivot_block, o),
                    cjk_autorise=cjk_ok, cjk_seuil=cjk_seuil,
                    # Tant que le bloc reste redécoupable, on INTERDIT au client de se
                    # rabattre sur une réponse non raisonnée : elle masquerait l'échec et
                    # nous priverait du redécoupage (cf. `LLM.repli_sans_raisonnement`).
                    repli_sans_raisonnement=True if dernier_recours else False, typo=typo)

            def _trad_resplit(pivot_block: str, refs: dict[str, str],
                              depth: int = 0, label: str = "") -> str:
                """Traduit `pivot_block` ; s'il échoue pour un motif de TAILLE, le coupe en
                deux et relance chaque moitié (récursivement, jusqu'à
                `redecoupage_profondeur_max`) au lieu d'abandonner.

                C'est le cas typique du budget « thinking » épuisé : le modèle raisonne sur
                un bloc trop gros, ne produit jamais de réponse finale, et l'ancien
                comportement réinjectait tout le bloc en langue source. Deux moitiés
                obtiennent chacune un plafond de sortie proportionné et des références
                réalignées, et passent le plus souvent sans encombre.

                Cela couvre AUSSI la boucle dégénérée (`repetition`) : le modèle boucle
                jusqu'à saturer son plafond, ce qui est un problème de taille (cf.
                `_RESPLIT_REASONS`). Et si la boucle survit à tout — retry plus chaud PUIS
                redécoupage jusqu'à la profondeur maximale — il reste le rattrapage par
                effondrement des répétitions (`_salvage_repetition`) avant tout repli sur la
                langue source."""
                # Le prédicat est calculé AVANT l'appel, avec EXACTEMENT la condition du
                # redécoupage plus bas : le repli sans raisonnement n'est rouvert que là où
                # couper ne peut plus rien apporter.
                redecoupable = (resplit_on and depth < resplit_depth
                                and len(pivot_block) >= resplit_min)
                out, ok, reason = _trad_once(pivot_block, refs,
                                             dernier_recours=not redecoupable)
                if ok:
                    if depth:
                        stats["recupere_par_redecoupage"] += 1
                    return _force_fr(_keep_images(pivot_block, out))
                # NB : pas de branche « repli dégradé accepté » ici. `thinking_overflow`
                # étant un motif à part entière, une sortie obtenue sans raisonnement est
                # TOUJOURS diagnostiquée — elle ne peut donc pas ressortir en `ok`. Quand
                # plus rien n'est redécoupable, elle suit le chemin d'échec ordinaire plus
                # bas : conservée (elle n'est pas dans `_TRAD_GARBAGE`) et marquée
                # « budget de raisonnement épuisé …, traduction conservée (à vérifier) ».

                if redecoupable and reason in _RESPLIT_REASONS:
                    halves = split.split_in_half(pivot_block)
                    if len(halves) == 2:
                        cause = getattr(agents["traducteur"].llm, "last_reason", None)
                        _warn(reporter,
                              f"[traduction] bloc {label} : {reason}"
                              + (f" ({cause})" if cause else "")
                              + f" → redécoupage en 2 et relance · {len(pivot_block)} c. → "
                                f"{len(halves[0])}+{len(halves[1])} c.")
                        stats["blocs_redecoupes"] += 1
                        sub = {c: split.split_proportional(t, [len(h) for h in halves])
                               for c, t in refs.items()}
                        return "\n\n".join(
                            _trad_resplit(h, {c: sub[c][k] for c in sub},
                                          depth + 1, f"{label}.{k + 1}")
                            for k, h in enumerate(halves))

                # Rattrapage d'une boucle irréductible : on effondre les cycles répétés
                # plutôt que de jeter tout le bloc. Une boucle NOIE le récit, elle ne le
                # détruit pas — le passage traduit avant l'emballement est récupérable.
                if reason == "repetition":
                    salvaged = _salvage_repetition(out, pivot_block)
                    if salvaged is not None:
                        stats["recupere_par_deboucle"] = stats.get("recupere_par_deboucle", 0) + 1
                        _warn(reporter,
                              f"[traduction] bloc {label} : {_TRAD_FAIL_LABELS[reason]} → "
                              f"répétitions effondrées, traduction conservée (à vérifier) · "
                              f"{_word_count(out)} → {_word_count(salvaged)} mots")
                        return (_force_fr(_keep_images(pivot_block, salvaged))
                                + f"\n\n<!-- AMBIGU: {_TRAD_FAIL_LABELS[reason]}, "
                                  "répétitions effondrées automatiquement (à vérifier) -->")

                lbl = _TRAD_FAIL_LABELS.get(reason, "sortie anormalement longue (emballement du modèle)")
                # Repli : NE JAMAIS réinjecter le texte SOURCE (langue de départ) comme
                # « traduction » — une sortie française imparfaite mais signalée vaut mieux
                # qu'un bloc resté en anglais qui traverse ensuite tous les étages suivants
                # (correction/mise en page se contentent de le recopier). On ne
                # retombe sur le pivot QUE si le modèle n'a produit aucun français
                # exploitable : réponse vide, ou recopie du glossaire / guide de style /
                # boucle dégénérée (dans ces cas la sortie n'est pas une vraie traduction).
                garbage = reason in _TRAD_GARBAGE
                perdu = garbage or not out.strip()
                _warn(reporter, f"[traduction] bloc {label} : {lbl} → "
                      + ("bloc laissé en LANGUE SOURCE" if perdu
                         else "traduction conservée (à vérifier)"))
                if perdu:
                    # Bloc resté en LANGUE SOURCE : ne pas y appliquer `force: true`
                    # (les `termes_source` y remplaceraient des mots anglais, produisant
                    # un hybride illisible) — le glossaire ne s'applique qu'au français.
                    return pivot_block + f"\n\n<!-- AMBIGU: {lbl}, bloc laissé en langue source (aucune traduction exploitable) -->"
                return _force_fr(_keep_images(pivot_block, out)) + f"\n\n<!-- AMBIGU: {lbl}, traduction conservée (à vérifier) -->"

            def _trad(bi: int) -> str:
                nonlocal timeouts_consecutifs
                refs = {c: ref_blocks[c][bi] for c in ref_clean
                        if bi < len(ref_blocks[c]) and ref_blocks[c][bi].strip()}
                sortie = _trad_resplit(blocks[bi], refs, label=f"{bi + 1}/{n}")
                # Le compteur suit le CLIENT, pas le motif du bloc : un bloc peut être
                # sauvé par redécoupage alors que le serveur est déjà en train de lâcher.
                if getattr(agents["traducteur"].llm, "last_reason", None) == "timeout":
                    timeouts_consecutifs += 1
                    if max_timeouts and timeouts_consecutifs >= max_timeouts:
                        _warn(reporter, f"[traduction] {timeouts_consecutifs} blocs expirés "
                                        f"d'affilée — le serveur ne suit plus. Arrêt propre : "
                                        f"l'avancement est sauvegardé, relance quand Ollama "
                                        f"aura repris.")
                        raise StopRequested()
                else:
                    timeouts_consecutifs = 0
                return sortie
            _trad_agent = agents["traducteur"]

            def _budget_trad(bi: int) -> int:
                cap = _out_cap(blocks[bi])
                return cap + (_trad_agent.thinking_budget if _trad_agent.thinking else 0)
            translated = _run_blocks("traduction", n, _trad, _ck("traduction"), reporter, build_dir, agent=agents["traducteur"], verbose=verbose, signature=sig_blocs, budget_bloc=_budget_trad)

            # 3) Correction (relecture : temps du récit, terminologie, genres — PAS de reformulation de style)
            reporter.stage("correction")
            if _agent_actif("correcteur"):
                def _corr(bi: int) -> str:
                    user = f"{glo_txt}\n\n{style_txt}\n\n# PREMIER JET À CORRIGER\n{translated[bi]}"
                    cap = _out_cap(translated[bi], mult=1.8)
                    out, ok, _ = _try_with_temp_retry(agents["correcteur"], user, translated[bi], cap,
                                                      stats, min_ratio=ratio_corr, temp_factor=temp_factor,
                                                      typo=typo)
                    if not ok:
                        return translated[bi]            # échec persistant → on garde le 1er jet
                    return _keep_images(translated[bi], out)
                revised = _run_blocks("correction", n, _corr, _ck("correction"), reporter, build_dir, agent=agents["correcteur"], verbose=verbose, signature=sig_blocs)
            else:
                reporter.info("désactivée (modeles.correcteur: null) — premier jet conservé")
                revised = list(translated)
            chapter_fr = "\n\n".join(b for b in revised if b.strip())

            # 5) Réinjection des images — UNIQUEMENT si le pivot n'avait pas ses propres
            #    images (mode traduction). En amélioration, les images du brouillon FR
            #    sont déjà ancrées inline et préservées par les agents.
            if not pivot_has_images and plan.image_lang and ci < len(plan.langs[plan.image_lang].chapters):
                manifest = images.manifest_for_chapter(plan.langs[plan.image_lang].chapters[ci].body)
                chapter_fr = images.insert_into(chapter_fr, manifest)

            # 6) Mise en page (drop-cap sur le 1er bloc)
            reporter.stage("mise en page")
            mep_blocks = split.split_blocks(chapter_fr, max_chars, has_parts=bool(pivot_chap.parts),
                                            part_tolerance=marge_partie,
                                            max_tokens=max_tokens_bloc) or [chapter_fr]
            m = len(mep_blocks)
            if _agent_actif("mise_en_page"):
                def _mep(j: int) -> str:
                    dc = "Applique le DROP-CAP (1er mot/expression en **gras**)." if j == 0 else "Pas de drop-cap ici."
                    user = (f"{style_txt}\n\n# CONSIGNES\n{consigne_dash}\n{dc}\n\n"
                            f"# GABARITS DE BLOCS\n{gabarits}\n\n# TEXTE À METTRE EN PAGE\n{mep_blocks[j]}")
                    cap = _out_cap(mep_blocks[j], mult=1.8, floor=1024)
                    out, ok, _ = _try_with_temp_retry(agents["mise_en_page"], user, mep_blocks[j], cap,
                                                      stats, min_ratio=ratio_mep, postprocess=_strip_fences,
                                                      temp_factor=temp_factor, typo=typo)
                    if not ok:
                        return mep_blocks[j]             # échec persistant → texte brut du bloc
                    return _keep_images(mep_blocks[j], out)
                styled = _run_blocks("mise en page", m, _mep, _ck("mise_en_page"), reporter, build_dir, agent=agents["mise_en_page"], verbose=verbose, signature=_signature_blocs(mep_blocks))
            else:
                reporter.info("désactivée (modeles.mise_en_page: null) — texte non balisé (dialogues stylés au rendu)")
                styled = list(mep_blocks)

            title_fr = (_translate_title(title, glo_txt, llm, trad_model, ck, dry=dry,
                                         pack=pack)
                        if (plan.mode == "traduction" and config["langues"].get("traduire_titres", True))
                        else title)
            chapter_md = f"# {title_fr}\n\n" + "\n\n".join(styled)
            _write(out_md, chapter_md)
            chapter_mds.append(chapter_md)
            # NB : on GARDE les checkpoints (ck) — ils permettent de relancer une étape
            # précise plus tard (python run.py … --from correction) sans tout refaire.

            fl = _flags(chapter_md)
            divs = sorted(set(divergences))
            report_sections.append(
                f"## Chapitre {ci + 1} — {title_fr}\n"
                f"- Blocs : {n}\n"
                f"- Points AMBIGU : "
                + ((PUCE_SOUS_LISTE + PUCE_SOUS_LISTE.join(fl)) if fl else "aucun") + "\n"
                "- Divergences terminologie : "
                + ((PUCE_SOUS_LISTE + PUCE_SOUS_LISTE.join(divs)) if divs else "aucune") + "\n"
                "- Genres à vérifier : " + (", ".join(
                    p["nom"] for p in glo.get("personnages", []) if "⚠" in (p.get("description") or "")) or "aucun") + "\n"
                "- Parties détectées : " + ("; ".join(p.title for p in pivot_chap.parts)
                                             if pivot_chap.parts else "aucune") + "\n")

            # Estimation du temps restant (runs complets seulement), affinée par le temps réel.
            chap_elapsed = time.perf_counter() - t_chap_start
            blocs_done += n
            time_done += chap_elapsed
            if only_chapter is None and ci + 1 < n_ch and blocs_done > 0:
                avg = time_done / blocs_done
                reste = sum(est_blocs_par_chap[ci + 1:])
                global_est = reste * avg
                eta = datetime.datetime.now() + datetime.timedelta(seconds=global_est)
                reporter.info(
                    f"⏳ estimation — chapitre suivant ~{_fmt_duree(est_blocs_par_chap[ci + 1] * avg)} · "
                    f"reste ~{_fmt_duree(global_est)} ({reste} bloc(s)) · fin vers {eta.strftime('%d/%m %Hh%M')}")

    except StopRequested:
        if chapter_mds:
            _write(full_md_path, "\n\n".join(chapter_mds))
        elapsed = time.perf_counter() - t_start
        mins, secs = divmod(int(elapsed), 60)
        total_blocs = stats["blocs_ok"] + sum(stats.get(r, 0) for r in _TRAD_FAIL_LABELS)
        vitesse_txt = ""
        if llm is not None and llm.stats["temps_generation"] > 0:
            vitesse_txt = f" · ~{llm.stats['tokens_generes'] / llm.stats['temps_generation']:.0f} tok/s"
        _write(build_dir / "RAPPORT.md",
              f"# Rapport (partiel — arrêté) — {project} / {volume}\n\n"
              f"Arrêté le {datetime.datetime.now().strftime('%Y-%m-%d à %Hh%M')} — "
              f"après {len(chapter_mds)}/{n_ch} chapitre(s) · durée : {mins}min {secs}s\n"
              f"Blocs traités : {total_blocs} — ok : {stats['blocs_ok']} · vide : {stats['vide']} · "
              f"emballement : {stats['emballement']} · perte de mots : {stats['perte_mots']} · "
              f"boucles : {stats['repetition']}{vitesse_txt}\n"
              # Le rapport partiel affichait « ok : 33 » sur un run qui contenait deux
              # blocs coupés en plein mot : les motifs de BUDGET doivent y figurer aussi.
              # C'est ce rapport-là qu'on lit après un Ctrl+C.
              f"Budget : {stats['troncature_length']} coupé(s) au plafond · "
              f"{stats['thinking_overflow']} raisonnement(s) épuisé(s)\n\n"
              + "\n".join(report_sections) +
              "\n\nRelance la même commande pour reprendre au chapitre/bloc suivant.\n")
        clear_stop(build_dir)
        reporter.stopped(len(chapter_mds), n_ch)
        _close_llm_clients(llm, agents)
        return False
    except BaseException:
        # Toute autre sortie du traitement des chapitres (KeyboardInterrupt d'un 2e
        # Ctrl+C « forcé », ou erreur inattendue) : on ferme les pools HTTP vers Ollama
        # avant de propager, pour ne pas abandonner une socket en pleine génération.
        # run.py enchaîne ensuite le déchargement VRAM protégé de SIGINT.
        _close_llm_clients(llm, agents)
        raise

    reporter.phase("finalisation")
    # Tome complet → assemblage + rendu.
    # ⚠ PAS de passe `_enforce_force` ici : les traductions imposées sont désormais
    # appliquées bloc par bloc, JUSTE APRÈS la traduction (cf. `_force_fr`). Réappliquer
    # le regex sur le texte assemblé — que correction/mise en page ont depuis
    # restructuré — risquerait de casser des phrases pour rien (décision explicite).
    full_md = "\n\n".join(chapter_mds)

    # Planches couleur de TÊTE DE VOLUME : elles précèdent le premier titre de chapitre,
    # donc `split._build` les jetait avec tout le texte qui précède la première frontière
    # (12 illustrations sur 20 perdues sur roman B Vol.2). On les réinjecte en préambule,
    # dans l'ordre de la source. Aucun agent n'intervient : ce sont des images.
    img_lang = plan.image_lang or pivot
    n_img_src = 0
    if img_lang in plan.langs:
        src_front = plan.langs[img_lang]
        n_img_src = len(_IMG_RE.findall(src_front.full_text))
        front = images.orphan_markers(src_front.full_text, src_front.chapters)
        if front:
            preambule = "\n\n".join(IMG_MARKER.format(raw) for raw in front)
            _write(chap_dir / "front-matter.md", preambule)   # inspectable comme un chapitre
            full_md = preambule + "\n\n" + full_md
            reporter.info(f"tête de volume : {len(front)} image(s) réinjectée(s) avant le chapitre 1")
        # Texte que la détection de chapitres a laissé de côté (page de titre, crédits,
        # sommaire — et, le cas échéant, de la vraie prose) : il n'est PAS traduit. Le dire
        # plutôt que de le perdre en silence. Mesure par DIFFÉRENCE, indépendante de la
        # position : robuste au repli LLM comme à la détection déterministe.
        def _sans_blanc(t: str) -> int:
            return len(re.sub(r"\s+", "", strip_images(t)))
        hors = (_sans_blanc(src_front.full_text)
                - sum(_sans_blanc(ch.body) for ch in src_front.chapters))
        if hors > 200:
            _warn(reporter, f"source [{img_lang}] : ~{hors} caractères de texte hors chapitres "
                            f"(avant le 1er titre) NON traduits — page de titre / crédits / sommaire, "
                            f"à vérifier s'il s'agit de récit")

    if stats["forces_appliques"]:
        reporter.info(f"traductions forcées (force: true) : {stats['forces_appliques']} "
                     f"remplacement(s) appliqué(s) à la sortie du traducteur")
    # LOT 27 — les illustrations générées, si et seulement si l'utilisateur l'a demandé.
    full_md, illustrations_inserees = _inserer_illustrations(
        full_md, project, config, build_dir, pack, reporter)
    # Empreinte de version en tête du Markdown assemblé : c'est l'artefact DURABLE du run,
    # rejoué tel quel par `--render-only` des mois plus tard. Un commentaire HTML est inerte
    # pour Pandoc et ne peut pas être pris pour un marqueur d'image : les trois expressions
    # qui les comptent exigent le littéral « IMG: » (_IMG_RE ici, render._MARKER_COUNT_RE).
    full_md = (f"<!-- Angelith {__version__} · {project} / {volume} · "
               f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} -->\n\n" + full_md)
    _write(full_md_path, full_md)
    # Contrôle de comptage des images source → Markdown → rendu : c'est l'absence de ce
    # contrôle qui a laissé passer plusieurs tomes amputés de leurs séparateurs de scène.
    n_img_md = len(_IMG_RE.findall(full_md))
    render_stats: dict = {}
    produced = render(full_md_path, build_dir, config,
                      warn=lambda m: _warn(reporter, m), stats=render_stats)
    n_img_out = render_stats.get("images_rendu", n_img_md)
    # On GARDE .checkpoints/ : permet de relancer une étape (--from …) après coup.

    # Résumé chiffré (Observabilité #10) : automatise ce qu'on dépouillait à la main
    # dans les logs — durée, issues par bloc, vitesse moyenne réelle.
    elapsed = time.perf_counter() - t_start
    # ⚠ Compter TOUS les motifs d'échec, pas seulement vide/emballement/perte_mots : sans
    # `repetition` ni `titre_perdu`, le résumé annonçait « 115 blocs — ok : 115 » alors que
    # 5 blocs avaient été perdus (roman D Vol.1). Un échec non compté est un
    # échec invisible.
    n_retries = stats["retry_temp_reduite"] + stats["retry_temp_relevee"]
    echecs = {r: stats.get(r, 0) for r in _TRAD_FAIL_LABELS}
    total_blocs = stats["blocs_ok"] + sum(echecs.values())
    resume = ["## Résumé du run"] + report.entete_run(elapsed) + [
        f"- Blocs traités (traduction/correction/mise en page) : {total_blocs} — "
        f"ok : {stats['blocs_ok']}" + (f" (dont {stats['recupere_par_retry']} récupéré(s) après "
                                       f"retry à température corrigée)" if stats['recupere_par_retry'] else ""),
        f"- Replis sur le texte précédent : {stats['vide']} vide(s) · {stats['emballement']} "
        f"emballement(s) · {stats['perte_mots']} perte(s) de mots détectée(s) · "
        f"{stats['repetition']} boucle(s) du modèle · {stats['titre_perdu']} titre(s) perdu(s)"
        + (f" · {n_retries} retry(s) tenté(s) au total" if n_retries else ""),
        # Ligne DÉDIÉE : ces trois compteurs disent que le BUDGET a manqué, pas que le
        # modèle a mal compris. Sans elle, un bloc coupé net au plafond se lisait comme un
        # bloc ordinaire — c'est exactement ce qui s'est produit sur roman A Vol.1.
        f"- Budget de génération : {stats['troncature_length']} bloc(s) coupé(s) net au "
        f"plafond max_tokens · {stats['thinking_overflow']} budget(s) de raisonnement "
        f"épuisé(s) avant la réponse finale"
        + ("" if (stats['troncature_length'] or stats['thinking_overflow'])
           else " — aucun bloc n'a manqué de budget"),
        (f"- Japonais/chinois résiduel : {stats['cjk_residuel']} bloc(s) où des noms sont "
         f"restés en écriture source — conservés et marqués AMBIGU"
         if stats["cjk_residuel"] else
         "- Japonais/chinois résiduel : aucun bloc concerné"),
        f"- Redécoupages sur échec : {stats['blocs_redecoupes']} bloc(s) coupé(s) en deux et "
        f"relancé(s) · {stats['recupere_par_redecoupage']} sous-bloc(s) récupéré(s)"
        + ("" if stats['blocs_redecoupes'] else " (aucun bloc n'a eu besoin d'être redécoupé)")
        + (f" · {stats['recupere_par_deboucle']} bloc(s) récupéré(s) par effondrement des "
           f"répétitions" if stats['recupere_par_deboucle'] else ""),
        # Images : source → Markdown assemblé → rendu. Un écart signale une perte (agent
        # qui supprime un marqueur, filtre de rendu trop zélé, tête de volume ignorée).
        f"- Images : {n_img_src} dans la source · {n_img_md} dans le Markdown assemblé · "
        f"{n_img_out} dans le rendu"
        + ("" if n_img_src == n_img_md == n_img_out
           else "  ⚠ écart — des images ont été perdues en route"),
        f"- Traductions imposées (`force: true`) : {stats['forces_appliques']} remplacement(s) "
        f"appliqué(s) à la sortie du traducteur"
        + (f" · {len(force_refus)} refusé(s) par les garde-fous d'accord" if force_refus else ""),
    ]
    if realign_notes:
        resume.append(
            "\n### Alignement des sources de référence\n"
            "Le découpage en chapitres d'une source de référence divergeait de celui du pivot.\n"
            "Sans recalage, le traducteur reçoit du texte hors-chapitre et le traduit en double.\n"
            + "\n".join(f"- {m}" for m in realign_notes))
    if illustrations_inserees:
        # Critère 3 de L27.4 : `RAPPORT.md` liste les images insérées, avec leur personnage
        # et leur graine. Une liste de noms de fichier obligerait à ouvrir onze sidecars.
        resume.append("\n".join(insertion_mod.lignes_de_rapport(illustrations_inserees)))
    if force_refus:
        # Dédoublonné : le même couple revient à chaque occurrence dans le tome.
        uniques = list(dict.fromkeys(force_refus))
        resume.append(
            "\n### Traductions imposées refusées (accord/élision impossible à garantir)\n"
            "Le remplacement déterministe s'est abstenu pour ne pas introduire une faute que le\n"
            "modèle n'aurait pas faite — le correcteur, lui, peut réécrire les mots autour.\n"
            "Pour en forcer davantage, complète le champ `genre:` de l'entrée concernée.\n"
            + "\n".join(f"- {m}" for m in report.tronquer(uniques, 20)))
    if glossaire_a_romaniser:
        resume.append(
            "\n### Entrées de glossaire sans rendu français\n"
            "Leur `nom` est encore la graphie source : elles sont MASQUÉES au traducteur (la\n"
            "lui montrer lui ordonnerait de recopier ce mot tel quel dans le texte français),\n"
            "mais restent visibles du terminologue et du glossariste, qui peuvent les réparer.\n"
            "Donne-leur un rendu latin dans `glossaire.yaml`, ou relance la terminologie.\n"
            + "\n".join(f"- {m}" for m in report.tronquer(glossaire_a_romaniser, 20)))
    # Agrégé sur TOUS les clients : le client par défaut seul ignorait les appels de
    # l'endpoint « reflexion » (traducteur/terminologue/glossariste), soit l'essentiel du run
    # — cf. `core.runtime.aggregate_llm_stats`.
    if stats["cap_sature"]:
        resume.append(
            f"\n### ⚠ Plafond de sortie saturé sur {stats['cap_sature']} bloc(s)\n"
            f"`out_cap` a atteint son maximum dur ({quality.CEIL_DEFAUT} tokens), ce qui "
            f"n'est possible qu'avec une langue dense : il faudrait 12 000 caractères\n"
            f"latins dans un bloc. Le plafond ne joue alors plus son rôle de filet —\n"
            f"baisse `decoupage.max_block_tokens` pour ce projet.")
    resume += report.lignes_llm(_aggregate_llm_stats(llm, agents))

    report.ecrire(
        build_dir,
        f"# Rapport — {project} / {volume}\n\n"
        f"Pivot : {pivot} · images : {plan.image_lang or '—'} · mode : {plan.mode} · "
        f"chapitres : {n_ch}\n"
        f"{_ligne_decoupage(plan, pivot, max_chars, max_tokens_bloc, agents)}\n\n"
        + "\n".join(resume) + "\n\n" + "\n".join(report_sections) +
        f"\n\nMarkdown complet : `{full_md_path.name}` · chapitres : `chapters/` · médias : `media/`\n")

    # Optimisation du glossaire en fin de volume (option config ou flag --optimize-glossary)
    if optimize or config["langues"].get("optimiser_glossaire_fin_volume", False):
        optimize_glossary_file(glo_path, agents, reporter, dry=dry, verbose=verbose)

    reporter.finish([p.name for p in produced])
    _close_llm_clients(llm, agents)
    return True
