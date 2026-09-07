# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**L26.2, l'appel LLM facultatif** — le texte traduit dit ce que le personnage FAIT.

    build/<Projet>/<Tome>/chapters/*.md  →  les passages qui NOMMENT le personnage
                                        →  le LLM (`illustration_portrait.md`)
                                        →  une clause de scène, filtrée par `prompt.epurer`

## Ce que ce module cherche, et ce qu'il refuse de chercher

Il cherche des **poses**, pas des **attributs**. La différence commande tout le reste :

| | ce qui le dit | qui le fournit |
|---|---|---|
| l'apparence — cheveux, yeux, âge, tenue, signes | `bible.apparence` + `citations[]` | la bible, mot pour mot |
| la scène — pose, geste, expression, lumière | un passage du chapitre | le LLM, **reformulé** |

⚠ **Le lexique d'apparence de `core/bible_texte.py` n'est PAS réutilisé ici, et c'est
volontaire.** Il sert à trouver les phrases qui parlent de cheveux et d'yeux — exactement
celles dont ce module ne veut pas. Ici on cherche les phrases qui **nomment** le personnage,
et on laisse le modèle y trouver un geste. Se tromper de lexique aurait donné des clauses de
scène systématiquement rejetées par `prompt.epurer`, et le rejet aurait eu l'air d'un défaut
du filtre.

## Le plafond de jetons : on DÉCOUPE, on ne tronque pas

`decoupage.max_input_tokens` vaut 24 000 dans la configuration livrée, et un chapitre entier
n'y entre pas. Le plafond mord donc sur le **nombre de passages**, jamais au milieu d'une
phrase : une phrase amputée décrirait une scène qui n'a pas eu lieu, et le modèle n'aurait
aucun moyen de le savoir. C'est la même règle que `manga/decoupage.py` applique au texte d'une
planche, et que le `PLAN-26` L26.4 rappelle mot pour mot.

## Ce qui n'est PAS mesuré ici, et il faut le savoir

⚠ **L'apport de la clause de scène sur l'image produite n'est pas mesuré — au 2026-09-02.**
Le `PLAN-26` classe la forme du texte en dernier dans l'ordre de grandeur — « images de référence ≫ masques
d'entités ≫ forme du texte » — et la mesure de ce lot a confirmé que le levier est ailleurs
(le CHOIX des images). Ce module est donc livré **complet et désarmé** : rien ne l'appelle
tant que `illustration.prompt.llm.actif` vaut `false`, et son effet reste à mesurer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core import bible_texte

#: Nom du prompt dans le pack de langue. ⚠ **Hors `core.langues.PROMPTS_REQUIS`**, comme
#: `illustration_style` et pour la même raison : les huit prompts de ce tuple sont ceux dont
#: l'absence invaliderait le pack `langues/en`.
PROMPT = "illustration_portrait"

#: Réponse d'un modèle qui n'a rien vu de dessinable. Exigée explicitement : une réponse VIDE
#: est indistinguable d'un appel raté, et on ne veut pas confondre les deux au rapport. Même
#: convention que `core/bible_llm.py` et `manga/relecture.py`.
RIEN = "RAS"

#: Combien de passages au plus sont montrés au modèle. Le plafond de jetons prime ; celui-ci
#: évite d'envoyer trente phrases quand cinq suffisent à décrire une pose.
PASSAGES_MAX = 8

#: Phrases de contexte gardées autour de la mention. Une seule de chaque côté : la pose est
#: dans la phrase qui nomme le personnage ou dans sa voisine immédiate. Au-delà, c'est une
#: autre scène — le même arbitrage que `bible_texte.FENETRE`, en plus serré.
CONTEXTE = 1

#: Longueur maximale de la clause retenue, en caractères. Le prompt demande vingt-cinq mots ;
#: au-delà, le modèle a écrit un paragraphe, et un paragraphe dans un prompt d'image noie les
#: attributs qui, eux, viennent de l'œuvre.
CLAUSE_MAX = 220

MOTIFS = {
    "aucun_passage": "aucun passage du tome ne nomme ce personnage",
    "modele_muet": "le modèle n'a vu aucune pose descriptible (RAS)",
    "clause_impure": "la clause décrivait un attribut d'apparence — rejetée en entier",
    "appel_echoue": "l'appel au modèle a échoué",
    "plafond_jetons": "plafond de jetons atteint : des passages ont été ÉCARTÉS, aucun tronqué",
}


@dataclass(frozen=True)
class Passage:
    """Un extrait du texte traduit qui nomme le personnage, **avec sa source**."""

    texte: str
    source: str

    def __str__(self) -> str:
        return self.texte


def passages(racine, entree: dict, *, plafond_jetons: int = 0,
             passages_max: int = PASSAGES_MAX) -> tuple[list, list]:
    """Les passages de l'ŒUVRE qui **nomment** ce personnage. Rend `(passages, motifs)`.

    `racine` est `build/<Projet>/` — **tous les tomes** — ou `build/<Projet>/<Tome>/` si
    l'appelant restreint volontairement. Les deux formes sont acceptées, et la source rendue
    porte le tome quand il y en a un.

    ⚠ **Une œuvre, pas un tome.** Un personnage n'apparaît pas forcément dans le volume qu'on
    illustre : sur le tome de référence, 7 des 10 références validées vivent dans un autre
    volume que le premier. Chercher la pose d'un personnage dans le seul tome courant
    reviendrait à ne lire qu'un dixième de ce que l'œuvre en dit.

    ⚠ `plafond_jetons` écarte des passages **entiers**. Il n'en tronque aucun : le plan écrit
    « découpez, ne tronquez pas silencieusement », et une phrase amputée décrirait une scène
    qui n'a pas eu lieu."""
    from core import tokens

    formes = bible_texte.formes_du_personnage(entree)
    if not formes:
        return [], ["aucun_passage"]

    trouves: list[Passage] = []
    for chemin, source in _chapitres(racine):
        texte = bible_texte.texte_propre(chemin.read_text(encoding="utf-8"))
        phrases = bible_texte.phrases(texte)
        normalisees = [bible_texte._sans_accent(p) for p in phrases]
        for index in _mentions(normalisees, formes):
            debut = max(0, index - CONTEXTE)
            fin = min(len(phrases), index + CONTEXTE + 1)
            trouves.append(Passage(texte=" ".join(phrases[debut:fin]).strip(), source=source))
            if len(trouves) >= passages_max:
                break
        if len(trouves) >= passages_max:
            break

    if not trouves:
        return [], ["aucun_passage"]

    plafond = int(plafond_jetons or 0)
    if plafond <= 0:
        return trouves, []
    retenus, total, motifs = [], 0, []
    for passage in trouves:
        cout = tokens.estimate(passage.texte)
        if total + cout > plafond:
            motifs.append("plafond_jetons")
            break
        retenus.append(passage)
        total += cout
    return retenus, motifs


def _chapitres(racine) -> list:
    """`[(chemin, source lisible)]` — les chapitres d'un tome OU de toute une œuvre.

    ⚠ La source rendue porte le tome quand `racine` en couvre plusieurs (`Vol.2/chapters/
    ch03.md`), et ne le porte pas quand l'appelant a restreint à un tome. Un chemin cité dans
    `attributs_sources` doit pouvoir s'ouvrir tel quel depuis la racine qu'on a donnée."""
    racine = Path(racine)
    propre = racine / "chapters"
    if propre.is_dir():
        return [(c, f"chapters/{c.name}") for c in sorted(propre.glob("*.md"))]
    if not racine.is_dir():
        return []
    sortie = []
    for tome in sorted(t for t in racine.iterdir() if t.is_dir()):
        dossier = tome / "chapters"
        if dossier.is_dir():
            sortie.extend((c, f"{tome.name}/chapters/{c.name}")
                          for c in sorted(dossier.glob("*.md")))
    return sortie


def _mentions(phrases_normalisees: list, formes: list) -> list:
    """Les index des phrases qui nomment le personnage, dans l'ordre.

    ⚠ Frontière de mot, jamais sous-chaîne. `core/bible_texte.py` a payé ce défaut : avec une
    recherche en sous-chaîne, **1 257 des 1 565** passages candidats d'un tome étaient des faux
    de cette famille — 80,3 %."""
    motifs = [re.compile(r"\b" + re.escape(bible_texte._sans_accent(f)) + r"\b")
              for f in formes if f]
    return [i for i, phrase in enumerate(phrases_normalisees)
            if any(m.search(phrase) for m in motifs)]


def formater(liste) -> str:
    """Les passages numérotés, tels qu'ils partent au modèle. Le format est celui de
    `core/bible_llm.py:formater_passages` — un seul format de message dans le dépôt."""
    return "\n".join(f"{i}. {p.texte}" for i, p in enumerate(liste, start=1))


def reformuler(llm, modele: str, systeme: str, personnage: str, liste, gab) -> tuple[str, list]:
    """Un appel, une clause de scène. Rend `(clause, motifs)` — la clause est **filtrée**.

    ⚠ **Le filtre est appliqué ICI, pas laissé à l'appelant.** Un module qui rendrait la
    réponse brute du modèle laisserait le prochain appelant décider s'il filtre, et le
    critère 4 du `PLAN-26` deviendrait une convention plutôt qu'une garantie."""
    from illustration import prompt as prompt_mod

    if not liste:
        return "", ["aucun_passage"]
    message = f"personnage: {personnage}\n\n{formater(liste)}"
    try:
        reponse = llm.chat(modele, systeme, message, temperature=0.0)
    except Exception as err:                         # noqa: BLE001 — un appel raté n'arrête rien
        return "", [f"appel_echoue:{type(err).__name__}"]
    clause = " ".join(str(reponse or "").split())[:CLAUSE_MAX].strip()
    if not clause or clause.upper().startswith(RIEN):
        return "", ["modele_muet"]
    epuree, motifs = prompt_mod.epurer(clause, gab)
    if not epuree:
        return "", motifs or ["clause_impure"]
    return epuree, []
