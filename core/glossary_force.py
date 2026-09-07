# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Forçage déterministe des entrées `force: true` du glossaire.

Extrait de `pipeline/orchestrator.py` au lot 2.5, **sans changer une ligne**. Ce module ne
connaît que du texte brut et un glossaire : rien de propre au light novel. Le lot 3 l'appelle
sur les chaînes de bulles manga, qui posent exactement les mêmes problèmes d'élision et
d'accord français — c'est même là que le besoin est le plus fort, une bulle étant trop courte
pour qu'un lecteur puisse deviner le terme canonique d'après le contexte.
"""
from __future__ import annotations

import re

from . import glossary, glossary_lang


_PLURAL_DET_SET = {"les", "des", "ces", "plusieurs", "certains", "certaines", "quelques",
                   "deux", "trois", "quatre", "cinq", "autres", "d'autres", "d’autres"}
_DET_FEM = {"une", "la", "cette", "ma", "sa", "ta", "toute"}
_DET_MASC = {"un", "le", "ce", "cet", "mon", "son", "ton", "tout"}
# Élision collée au mot remplacé (apostrophe droite ou typographique) : « l'infirmière ».
_ELISION_RE = re.compile(r"(?P<el>qu|[ldnsjmtc])['’]\s*$", re.IGNORECASE)
# Dernier mot (+ son espace) avant le mot remplacé : « une infirmière », « les forces ».
_PREV_WORD_RE = re.compile(r"(?P<w>[\w’'-]+)(?P<sp>\s+)$", re.IGNORECASE)
_VOWEL_START = re.compile(r"^[aàâäeéèêëiîïoôöuùûüyAÀÂÄEÉÈÊËIÎÏOÔÖUÙÛÜY]")
# Consonne franche : on EXCLUT le « h » (h muet/aspiré indécidable sans dictionnaire →
# on ne touche pas à l'élision dans ce cas, plutôt que de risquer « le hôpital »).
_CONSONANT_START = re.compile(r"^[bcdfgjklmnpqrstvwxzBCDFGJKLMNPQRSTVWXZ]")


class AccordFrancais:
    """Les règles d'accord du FRANÇAIS — déplacées ici sans changer une ligne.

    Elles décidaient jusqu'ici en dur dans `enforce_force`. Elles sont désormais une
    **fonction du pack de langue cible** : le français accorde le déterminant et répare les
    élisions, l'anglais n'a rien à accorder, l'allemand aurait besoin des cas.

    ⚠ Le principe à préserver, quelle que soit l'implémentation : **le déterministe ne doit
    JAMAIS introduire une faute que le modèle n'aurait pas faite.** Un remplacement dont le
    genre est incertain est REFUSÉ, jamais rendu fautif."""

    def pluriel_attendu(self, ctx: str) -> bool:
        """Le contexte appelle-t-il la forme plurielle ? (« les », « des », « plusieurs »…)"""
        prev_m = None if _ELISION_RE.search(ctx) else _PREV_WORD_RE.search(ctx)
        prev_word = prev_m.group("w").lower() if prev_m else ""
        return prev_word in _PLURAL_DET_SET

    def examiner(self, ctx: str, cible: str, genre: str) -> tuple[str, int, str | None]:
        """`(déterminant de remplacement, caractères à retirer, raison de refus)`.

        Une `raison` non nulle veut dire « ne remplace pas » : c'est le garde-fou qui préfère
        laisser la forme d'origine plutôt que d'écrire « L'médecin » ou « Une médecin »."""
        el_m = _ELISION_RE.search(ctx)
        prev_m = None if el_m else _PREV_WORD_RE.search(ctx)
        prev_word = prev_m.group("w").lower() if prev_m else ""

        ctx_genre = ("féminin" if prev_word in _DET_FEM else
                     "masculin" if prev_word in _DET_MASC else "")

        # Garde-fou 2 : le déterministe ne corrigerait que le nom, pas les accords autour.
        if genre and ctx_genre and ctx_genre != genre:
            return "", 0, f"le déterminant « {prev_word} » est {ctx_genre}, l'entrée est {genre}"

        # Garde-fou 1 : élision à réécrire quand la cible change d'initiale.
        new_det, trim = "", 0
        if el_m and _CONSONANT_START.match(cible):
            el = el_m.group("el").lower()
            if el == "l":
                if not genre:
                    return "", 0, ("« l' » suivi d'une consonne et genre inconnu : impossible "
                                   "de choisir entre « le » et « la » — précise `genre:` dans "
                                   "le glossaire")
                new_det = "la " if genre == "féminin" else "le "
            elif el == "d":
                new_det = "de "
            if new_det:
                if el_m.group(0)[0].isupper():
                    new_det = new_det[0].upper() + new_det[1:]
                trim = len(el_m.group(0))
        elif prev_word in ("le", "la", "de") and _VOWEL_START.match(cible):
            new_det = "l’" if prev_word in ("le", "la") else "d’"
            if prev_m.group("w")[0].isupper():
                new_det = new_det[0].upper() + new_det[1:]
            trim = len(prev_m.group(0))
        return new_det, trim, None


class AccordNeutre:
    """Aucun accord grammatical : la langue cible n'en demande pas.

    L'anglais est le cas type — pas de genre, pas d'élision, pas de déterminant à réécrire.
    Le remplacement forcé s'y réduit donc à la substitution, ce qui est exactement ce qu'il
    doit être : **ne rien faire est la bonne réponse**, pas une implémentation en attente.

    Le pluriel reste consulté : `pluriel:` existe dans toutes les langues à nombre, et
    l'anglais en a un. Mais on ne le devine pas depuis le contexte — aucun déterminant
    anglais ne le marque de façon fiable (« the » vaut pour les deux). On rend donc `False`,
    et la forme plurielle ne s'emploie que si l'entrée n'a pas de singulier."""

    def pluriel_attendu(self, ctx: str) -> bool:
        return False

    def examiner(self, ctx: str, cible: str, genre: str) -> tuple[str, int, str | None]:
        return "", 0, None


#: Implémentations disponibles, nommées dans `pack.yaml` sous `accord:`.
ACCORDS = {"francais": AccordFrancais, "aucun": AccordNeutre}

#: Défaut : le français. C'est le comportement d'avant, et il ne change pas sans pack.
ACCORD_DEFAUT = AccordFrancais()


def accord_pour(nom: str | None):
    """Instance d'accord nommée dans un pack, ou le français."""
    classe = ACCORDS.get(str(nom or "").strip().lower())
    return classe() if classe else ACCORD_DEFAUT


def enforce_force(text: str, glo: dict, refus: list[str] | None = None,
                  accord=None) -> tuple[str, int]:
    """Remplacement déterministe des entrées `force: true` : toute forme listée en
    `variantes`/`interdits`/`termes_source` est remplacée par `nom` (ou par `pluriel`
    si un déterminant pluriel précède ET que l'entrée fournit ce champ), GARANTI —
    indépendant de ce que le modèle a produit. Filet de sécurité absolu, pas juste une
    consigne de prompt ; inclure `termes_source` ici rattrape aussi le cas où un mot en
    langue source (ex. anglais) serait resté non traduit dans le texte final.

    ⚠ PRINCIPE : le déterministe ne doit JAMAIS introduire une faute que le modèle
    n'aurait pas faite. Deux garde-fous, ajoutés après démonstration sur un vrai tome
    (le remplacement brut produisait « L'médecin de combat », « Une médecin de combat
    expérimentée ») :

    1. **Élision réparée** : si le mot remplacé est précédé de `l'`/`d'` et que la forme
       cible commence par une consonne, l'élision est réécrite (`l'` → `le`/`la` selon
       le `genre` de l'entrée, `d'` → `de`). Si le `genre` est absent/« ? », on ne peut
       pas choisir entre `le` et `la` → le remplacement est REFUSÉ (et signalé) plutôt
       que de produire une faute. Cas inverse traité aussi (`le`/`la`/`de` + cible à
       initiale vocalique → `l'`/`d'`).
    2. **Changement de genre refusé** : si le déterminant qui précède révèle un genre
       (une/la/cette… vs un/le/ce…) en CONFLIT avec le `genre` de l'entrée, le
       remplacement est refusé et signalé — corriger le seul nom laisserait l'article et
       les adjectifs accordés au genre d'origine. C'est le travail du correcteur,
       qui peut réécrire les mots autour ; pas celui d'un regex.

    `refus` (facultatif) reçoit un message par remplacement refusé, pour le rapport.

    Limites connues, assumées :
    - Seul le DÉTERMINANT est réaccordé, pas les adjectifs/participes autour : « L'infirmière
      était épuisée » devient « Le médecin de combat était épuisée » (« épuisée » reste au
      féminin). C'est acceptable parce que le forçage s'applique JUSTE APRÈS la traduction
      (cf. `process_volume`) : le correcteur tourne ensuite et rattrape ces
      accords. Un regex ne peut pas réécrire un accord à distance de façon fiable.
    - Le pluriel repose sur le déterminant qui précède ET sur le champ `pluriel:` ; les
      formes plurielles doivent en plus être listées explicitement dans `interdits`
      (`\\b…\\b` ne fait pas correspondre « infirmières » à « infirmière »)."""
    accord = accord if accord is not None else ACCORD_DEFAUT
    # (forme source, nom singulier, pluriel ou "", genre ou "")
    rules: list[tuple[str, str, str, str]] = []
    for cat in glossary.ENTITY_CATS:
        for e in (glo.get(cat) or []):
            nom = (e.get("nom") or "").strip()
            if not e.get("force") or not nom:
                continue
            # ⚠ Un `nom` encore en écriture source ne doit JAMAIS être forcé : les formes
            # remplacées incluent `termes_source` (cf. `forms` plus bas), donc un
            # `force: true` posé à la main sur une entrée non romanisée réécrirait
            # « 霊峰・不尽山 » en « 不尽山 » — verrouillant le japonais dans le rendu final,
            # de façon déterministe et sans appel LLM pour le trahir.
            if glossary_lang.contient_cjk(nom):
                continue
            pluriel = (e.get("pluriel") or "").strip()
            genre = (e.get("genre") or "").strip().lower()
            if genre not in ("masculin", "féminin"):
                genre = ""                       # « ? », vide, ou catégorie sans genre
            forms = (list(e.get("variantes") or []) + list(e.get("interdits") or [])
                    + list(e.get("termes_source") or []))
            for f in forms:
                # Comparaison SENSIBLE À LA CASSE : une forme qui ne diffère du `nom` que
                # par la casse (« forces de défense » vs « Forces de défense ») est un cas
                # LÉGITIME et le plus sûr de tous (aucun risque d'accord) — l'ancienne
                # comparaison en minuscules l'excluait silencieusement, rendant impossible
                # le forçage d'une simple majuscule imposée par le glossaire.
                if f and f.strip() != nom:
                    rules.append((f.strip(), nom, pluriel, genre))
    if not rules:
        return text, 0
    rules.sort(key=lambda t: len(t[0]), reverse=True)   # plus long d'abord (évite les sous-matches)
    lookup = {f.lower(): (nom, pluriel, genre) for f, nom, pluriel, genre in rules}
    pattern = re.compile(r"\b(" + "|".join(re.escape(f) for f, _, _, _ in rules) + r")\b",
                         re.IGNORECASE)

    out: list[str] = []
    pos = 0
    count = 0
    for m in pattern.finditer(text):
        if m.start() < pos:            # chevauchement : déjà consommé par un motif plus long
            continue
        forme = m.group(0)
        nom, pluriel, genre = lookup[forme.lower()]
        segment = text[pos:m.start()]              # texte intact depuis le dernier remplacement
        # Fenêtre arrière BORNÉE pour lire le déterminant : un déterminant/une élision
        # tient en quelques caractères. Passer tout le préfixe (`text[:m.start()]`) à un
        # regex ancré `$` le fait rescanner depuis le début à chaque occurrence — mesuré
        # quadratique (3,7 s pour 40 ko, et un tome fait des centaines de ko).
        ctx = text[max(0, m.start() - 48):m.start()]

        # Les règles d'accord viennent du PACK de langue cible : le français accorde le
        # déterminant et répare les élisions, l'anglais n'a rien à accorder.
        cible = pluriel if (accord.pluriel_attendu(ctx) and pluriel) else nom
        new_det, trim, raison = accord.examiner(ctx, cible, genre)
        if raison is not None:
            if refus is not None:
                refus.append(f"« {forme} » → « {nom} » non forcé ({raison}) — "
                             f"laissé au correcteur")
            out.append(segment + forme)
            pos = m.end()
            continue

        remplacement = match_case(forme, cible)
        if remplacement == forme and not trim:
            # Le regex est insensible à la casse : il matche aussi la forme DÉJÀ canonique.
            # Rien à changer → on ne compte pas un remplacement fantôme (le compteur sert
            # à savoir si un agent aval réintroduit des formes bannies, cf. RAPPORT.md).
            out.append(segment + forme)
            pos = m.end()
            continue

        if trim and len(segment) >= trim:
            out.append(segment[:-trim] + new_det)
        else:
            out.append(segment)            # élision hors du segment courant → on n'y touche pas
        out.append(remplacement)
        count += 1
        pos = m.end()

    out.append(text[pos:])
    return "".join(out), count


def match_case(original: str, replacement: str) -> str:
    """N'AJOUTE une majuscule que si le texte trouvé en avait une et que le
    remplacement (tel qu'écrit dans `nom`) commence par une minuscule (ex. début de
    phrase). Ne rabaisse JAMAIS une casse déjà voulue dans `nom` (ex. « Leprechaun »,
    nom propre, reste capitalisé même si la forme rencontrée était en minuscule)."""
    if not original or not replacement:
        return replacement
    if original[0].isupper() and replacement[0].islower():
        return replacement[0].upper() + replacement[1:]
    return replacement
