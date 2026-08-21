# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Écriture des entrées de glossaire : détecter le CJK, et remettre chaque graphie dans
le champ qui lui revient.

## Pourquoi un module, et pas trois lignes dans `glossary_build`

Le schéma du glossaire distingue le **rendu français** (`nom`) de la **graphie source**
(`termes_source`) — mais rien, dans le nom du champ `nom`, ne dit qu'il doit être en
français. Sur une œuvre dont la langue pivot EST la langue source (premier cas du dépôt :
roman A, pivot japonais), le terminologue n'a aucune raison de deviner la règle :
il écrit le headword japonais dans `nom`, le glossaire le présente au traducteur comme
« le rendu français à respecter », et le traducteur obéit — 447 séquences japonaises dans
le rendu du Vol.1.

Trois raisons d'en faire un module du SOCLE plutôt qu'un correctif local :

1. **Le glossaire est partagé entre les deux briques.** `manga/terminology.py` écrit dans
   le MÊME `sources/<Projet>/glossaire.yaml`. Une validation qui ne vivrait que dans
   `pipeline/` laisserait la moitié des producteurs la contourner.
2. **Les jeux de caractères CJK ont déjà divergé une fois.** `tokens.CJK` est LARGE (budget
   de tokens : une ponctuation pleine chasse coûte autant qu'un idéogramme) ; la brique
   manga a dû se fabriquer une classe étroite après avoir déclaré « du japonais » sur une
   bulle ne contenant que `（）`. Ici on réutilise `tokens.CJK_TEXTE`, l'étroite, plutôt que
   d'en écrire une troisième.
3. **La réparation doit être pure et testable sans LLM.** `reparer_entree` ne fait que
   déplacer des chaînes entre champs ; c'est ce qui permet de la brancher sur les trois
   producteurs (terminologue, glossariste, import) en un seul point.

## Ce que ce module NE fait pas

Il ne romanise rien. Transformer 天茜 en « Akane » demande la LECTURE (あかね), que seul le
texte source porte — c'est le rôle du terminologue, à qui les furigana seront fournis. Ici
on se contente de constater qu'une entrée n'est pas encore romanisée, de ranger la graphie
source là où elle sert, et de le signaler.

`core/` n'importe ni `pipeline/` ni `manga/` : ce module ne dépend que de `tokens`.
"""
from __future__ import annotations

import re

from . import tokens

#: Codes de langue (cf. `config.yaml > langues.dossiers`) dont l'écriture n'est pas latine.
LANGUES_CJK = frozenset({"jp", "zh", "ko"})

#: Caractères porteurs de texte CJK — LA classe étroite, réutilisée telle quelle.
CJK = tokens.CJK_TEXTE

_LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")

# Au-delà de cette proportion de caractères CJK, un texte est considéré comme écrit en
# CJK. Volontairement bas : un chapitre japonais est à ~0,95, un texte latin parsemé de
# quelques noms propres japonais reste très en dessous.
_SEUIL_PIVOT = 0.15

#: Champs d'une entrée qui portent une forme DESTINÉE AU LECTEUR français.
_CHAMPS_RENDUS = ("nom", "pluriel")


def contient_cjk(s: str) -> bool:
    return bool(CJK.search(s or ""))


def contient_latin(s: str) -> bool:
    return bool(_LATIN.search(s or ""))


def taux_cjk(s: str) -> float:
    """Proportion de caractères porteurs de CJK. Les espaces et la ponctuation comptent
    au dénominateur : c'est une mesure de « à quoi ressemble ce texte », pas une
    statistique linguistique."""
    if not s:
        return 0.0
    return len(CJK.findall(s)) / len(s)


def pivot_est_cjk(code: str | None, echantillon: str = "") -> bool:
    """La langue pivot s'écrit-elle en CJK ?

    Teste le CODE **ou** la MESURE. Le code seul suffirait aujourd'hui (`config.yaml`
    mappe `JAP→jp`, `CHINOIS→zh`), mais cette table est éditable par l'utilisateur : la
    mesure rattrape un dossier nommé autrement, et le mode « amélioration » sur un
    brouillon français encore truffé de japonais."""
    if (code or "").strip().lower() in LANGUES_CJK:
        return True
    return taux_cjk(echantillon[:4000]) > _SEUIL_PIVOT


def reparer_entree(e: dict) -> tuple[dict, list[str]]:
    """Remet les graphies CJK dans `termes_source`. Renvoie `(entrée, avertissements)`.

    Pure et idempotente : aucune E/S, aucun appel LLM, et la rejouer ne duplique rien.
    L'entrée d'origine n'est pas mutée.

    Trois cas, et un quatrième volontairement ignoré :

    - une **variante** en CJK → déplacée vers `termes_source`. `variantes` est la clé de
      recherche du dédoublonneur : y laisser une graphie source la fait concurrencer les
      orthographes latines légitimes ;
    - un **`nom` en CJK avec une variante latine disponible** → la variante devient le
      `nom`, la graphie CJK rejoint `termes_source`. Réparation sans perte ni ambiguïté,
      donc silencieuse ;
    - un **`nom` en CJK sans aucune forme latine** → le `nom` est CONSERVÉ (le retirer
      perdrait la description et le genre, coûteux à reconstruire) mais l'entrée est
      marquée `a_romaniser: True` et signalée. C'est ce drapeau que le rendu du glossaire
      utilisera pour ne pas présenter l'entrée au traducteur comme un rendu français ;
    - `nom == termes_source` **en latin** n'est PAS un défaut : sur une source anglaise,
      un nom propre inchangé (`Semifer`) est exactement ce qu'on veut.
    """
    e = dict(e)
    avertissements: list[str] = []
    variantes = [v for v in (e.get("variantes") or []) if str(v).strip()]
    sources = [s for s in (e.get("termes_source") or []) if str(s).strip()]

    def _ajouter_source(forme: str) -> None:
        if forme not in sources:
            sources.append(forme)

    # 1) Graphies source rangées dans `variantes`.
    cjk_dans_variantes = [v for v in variantes if contient_cjk(v)]
    if cjk_dans_variantes:
        variantes = [v for v in variantes if not contient_cjk(v)]
        for v in cjk_dans_variantes:
            _ajouter_source(v)

    # 2) Le `nom` lui-même.
    nom = str(e.get("nom") or "").strip()
    if nom and contient_cjk(nom):
        _ajouter_source(nom)
        latine = next((v for v in variantes if contient_latin(v) and not contient_cjk(v)), None)
        if latine:
            variantes.remove(latine)
            e["nom"] = latine
            # Une passe précédente avait pu poser le drapeau faute de forme latine : il
            # doit tomber maintenant qu'il y en a une, sinon l'entrée resterait masquée
            # au traducteur alors qu'elle a désormais un rendu.
            e.pop("a_romaniser", None)
        else:
            e["a_romaniser"] = True
            avertissements.append(
                f"« {nom} » n'a pas de rendu français : graphie source conservée "
                f"(termes_source : {', '.join(sources)})")
    elif nom and e.get("a_romaniser"):
        # Le nom a été romanisé entre-temps (à la main, ou par une relance de la
        # terminologie) : le drapeau doit tomber, sinon l'entrée resterait masquée.
        e.pop("a_romaniser", None)

    # 3) Un `pluriel` en CJK n'est jamais un pluriel français : il ne sert à rien au rendu.
    pluriel = str(e.get("pluriel") or "").strip()
    if pluriel and contient_cjk(pluriel):
        _ajouter_source(pluriel)
        e["pluriel"] = ""

    if variantes or "variantes" in e:
        e["variantes"] = variantes
    if sources or "termes_source" in e:
        e["termes_source"] = sources
    return e, avertissements


def formes_cjk_autorisees(glossaire: dict) -> tuple[str, ...]:
    """Formes CJK qu'il est LÉGITIME de trouver dans un texte français, triées de la plus
    longue à la plus courte (pour qu'un retrait par remplacement ne laisse pas les
    morceaux d'une forme plus longue).

    Deux sources de légitimité : une entrée marquée `traduire: false` (décision explicite
    de ne pas traduire) et une entrée `a_romaniser` (pas encore de rendu français — la
    bannir ferait boucler le contrôle sur une sortie pourtant conforme au glossaire qu'on
    a nous-même fourni au traducteur).

    `termes_source` en est volontairement EXCLU : un mot source n'est jamais légitime dans
    le texte français, c'est justement ce qu'on cherche à détecter."""
    formes: set[str] = set()
    for cat, entrees in (glossaire or {}).items():
        if not isinstance(entrees, list):
            continue
        for e in entrees:
            if not isinstance(e, dict):
                continue
            if not (e.get("traduire") is False or e.get("a_romaniser")):
                continue
            for champ in _CHAMPS_RENDUS:
                val = str(e.get(champ) or "").strip()
                if val and contient_cjk(val):
                    formes.add(val)
            for v in (e.get("variantes") or []):
                if contient_cjk(str(v)):
                    formes.add(str(v))
    return tuple(sorted(formes, key=len, reverse=True))


def auditer(glossaire: dict) -> list[str]:
    """Entrées dont le rendu français manque encore, en lignes prêtes pour `RAPPORT.md`.

    Lecture seule : ne répare rien, ne mute rien. Sert à rendre VISIBLE ce que
    `reparer_entree` a dû laisser en l'état."""
    lignes: list[str] = []
    for cat, entrees in (glossaire or {}).items():
        if not isinstance(entrees, list):
            continue
        for e in entrees:
            if not isinstance(e, dict):
                continue
            nom = str(e.get("nom") or "").strip()
            if not nom:
                continue
            if e.get("a_romaniser") or contient_cjk(nom):
                src = ", ".join(str(s) for s in (e.get("termes_source") or [])) or "—"
                lignes.append(f"{cat} : « {nom} » (source : {src})")
    return lignes


def consigne_pivot_cjk() -> str:
    """Consigne injectée dans le MESSAGE du terminologue quand le pivot est CJK.

    Dans le message et non dans `prompts/terminologue.md` : ce prompt système est partagé
    avec la brique manga et lu à chaque bloc de chaque œuvre, dont la grande majorité a un
    pivot latin. Une règle de romanisation n'y a rien à faire à demeure."""
    return (
        "# LANGUE DU BLOC — IMPORTANT\n"
        "Ce bloc est ta SEULE source, et il n'est pas écrit en alphabet latin.\n"
        "Pour chaque entrée :\n"
        "- `nom` = ce que le lecteur FRANÇAIS lira. Toujours en alphabet latin. Romanisation "
        "Hepburn s'il s'agit d'un nom propre (personnage, lieu, organisation) ; traduction "
        "française s'il s'agit d'un nom commun, d'un concept, d'un titre ou d'une fonction.\n"
        "- `termes_source` = la graphie d'origine, telle qu'elle apparaît dans le bloc.\n"
        "N'écris JAMAIS de caractère japonais ou chinois dans `nom` ni dans `variantes`.\n"
        "Exemple : `- Yaeyamabuki | termes_source: 八重山吹 | Agence de chasse aux dragons.`"
    )
