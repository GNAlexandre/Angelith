# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Cohérence terminologique d'un tome manga (lot 3) : relevé des noms propres par le
terminologue, et **forçage déterministe** des formes canoniques dans les bulles.

## Le défaut, mesuré sur *manga A* Vol.1

Chaque planche est traduite en isolation. Le modèle ne sait pas quelle romanisation il a
retenue vingt planches plus tôt, si bien qu'**une même chaîne source ressort avec plusieurs
orthographes françaises** :

| Source | Rendus observés |
|---|---|
| `カタフラクト` | Kataphrakt · Katafrakt · Kataphrakto · Cataphracte |
| `リベルティナ` | Libertina · Ribitina · Libidina |
| `フェルゼン` | Felsen · Fersen · Ferzen |
| `クルーテオ` | Kuran · Cluteo · Kruuteo |
| `三影` (kanji !) | Mitsukage · Mikage · Miyage |
| `弥月` (kanji !) | Yuzuki · Yozuki · Miyuki |

Les deux dernières lignes sont les plus parlantes : ce sont des **kanji**, strictement
identiques d'une bulle à l'autre. Aucune ambiguïté de lecture OCR ne peut l'expliquer — c'est
le modèle qui hésite, planche par planche. Un lecteur ne peut pas deviner que « Mikage » et
« Mitsukage » sont la même personne : une bulle est trop courte pour porter ce contexte.

## Deux leviers, dans cet ordre

1. **Préventif** — le glossaire de l'œuvre est déjà injecté en contexte du traducteur
   (`orchestrator_manga`). Le terminologue l'enrichit à partir du **japonais OCR**, ce qui
   suffit à faire converger les planches suivantes. Les agents sont agnostiques du média :
   `prompts/terminologue.md` et `prompts/glossariste.md` sont réutilisés **tels quels**, et
   ils écrivent dans le MÊME `sources/<Projet>/glossaire.yaml` que le light novel — c'est ce
   qui garde les noms cohérents entre un roman et son manga.
2. **Curatif** — `core.glossary_force.enforce_force` remplace les formes bannies par la forme
   canonique, quoi que le modèle ait produit. Déterministe, sans appel LLM, avec la gestion
   française de l'élision et de l'accord.

## Pourquoi le forçage s'applique à l'USAGE et non à l'écriture du cache

Le light novel force **juste après la traduction** et stocke le texte forcé : il doit le
faire, parce que le correcteur tourne ensuite et travaille sur ce texte.

La brique manga n'a aucun agent en aval — l'étape suivante est un lettrage déterministe. On
garde donc dans `traduction.json` la **sortie brute du modèle**, et on force au moment de
s'en servir. Conséquence concrète : corriger une entrée du glossaire et relancer
`--from rendu` suffit à réécrire les 150 planches, **sans un seul appel LLM**. Stocker le
texte forcé imposerait de retraduire le tome à chaque correction d'orthographe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core import glossary, glossary_build
from core.glossary import ENTITY_CATS
from core.glossary_force import enforce_force

# ─────────────────────────────────────────────────────────────────────────────
# Détection de DÉRIVE : les formes que le glossaire n'a pas encore bannies
#
# Le forçage ne rattrape que ce qu'on lui a listé. Sur le run v0.21.0 du Vol.1, les
# `interdits` contenaient les fautes du run PRÉCÉDENT (`Aselam`, `Kruuteo`, `Kataphrakto`) et
# le tome en a produit de NOUVELLES (`Libentina` ×4, `Libertaine`). `compter_variantes.py`
# annonçait « 0 forme bannie » — exact, et trompeur : le mécanisme n'est pas cassé, il n'est
# jamais alimenté. C'est cette boucle qu'on ferme ici, sans un seul appel LLM.
# ─────────────────────────────────────────────────────────────────────────────

# Un nom canonique plus court que cela n'est pas séparable du lexique français : `Vers`, nom
# de l'organisation de ce tome, est à **distance 1** de « Mers », « Verre » ou de la
# préposition « vers » elle-même, et à distance 2 de « Les » et « Des ». Le surveiller
# reviendrait à bannir des mots français. Limite ASSUMÉE : un nom de moins de cinq caractères
# n'est pas surveillable automatiquement — il reste couvert par les `interdits` écrits à la main.
LONGUEUR_MIN = 5

# Mots capitalisés qui ne sont jamais des noms propres : têtes de phrase françaises
# courantes. Vivait dans `tools/compter_variantes.py`, qui l'importe désormais d'ici — la
# liste sert maintenant au pipeline, et deux copies auraient divergé.
MOTS_COURANTS = frozenset("""Alors Attends Après Aussi Avant Avec Bien Bon Cela Celle
Cependant Ces Cette Chaque Comme Comment Dans Depuis Des Deux Donc Elle Elles Encore Enfin
Est Et Euh Faut Hein Ici Ils Jamais Juste Laisse Laisser Les Leur Mais Merci Mes Moi Mon Nos
Notre Nous Oui Non Par Parce Pas Passe Peut Plus Pour Pourquoi Puis Quand Que Quel Quelle Qui
Quoi Regarde Rien Sans Ses Son Sur Tes Toi Ton Tous Tout Toute Très Une Vite Voilà Vos Votre
Vous Vraiment Haa Hmm Ah Oh Eh""".split())

# Mot capitalisé, SANS apostrophe dans la classe : sur « l'Areyon », une classe qui l'inclut
# capture « l'Areyon » d'un bloc et la forme nue n'est jamais vue. Ici le moteur échoue sur
# « l » puis repart sur « Areyon ».
_MOT_CAPITALISE = re.compile(r"[A-ZÀ-Ý][A-Za-zÀ-ÿ-]{2,}")

# Ce qui précède un mot en TÊTE de phrase. Tout le reste (une lettre, une virgule) signe une
# capitale de milieu de phrase, donc un nom propre plutôt qu'un début de réplique.
_AVANT_PHRASE = set(".!?…«»\"'([-—:;\n")

_DEFAUTS_DERIVE = {
    "actif": True,
    # T2 : le nom canonique doit être solidement installé dans le tome avant qu'une forme
    # proche puisse être déclarée fautive. 5 occurrences et un rapport de 3 pour 1.
    "min_occurrences": 5,
    "dominance": 3,
}


@dataclass(frozen=True)
class Derive:
    """Une forme française soupçonnée d'être une variante fautive d'un nom du glossaire.

    `niveau` porte la FORCE DE LA PREUVE, et rien d'autre ne décide de ce qu'on en fait :

    | niveau | preuve                                                        | interdits | corrigé |
    |--------|---------------------------------------------------------------|-----------|---------|
    | `T1`   | un `termes_source` japonais de l'entrée est dans l'OCR de la   | oui       | ce run  |
    |        | **même bulle** — la bulle parle bien de cette entité           |           |         |
    | `T2`   | le nom domine le tome (≥ N occurrences et ≥ K × le candidat)   | oui       | `--from rendu` |
    | `T3`   | distance lexicale seule                                       | **non**   | non — rapport |
    """
    nom: str                # forme canonique du glossaire
    candidat: str           # forme observée dans le texte français
    categorie: str          # section du glossaire (personnages, termes…)
    niveau: str             # "T1" | "T2" | "T3"
    page: int = 0
    bulle: int = 0          # numéro humain (1-based), 0 si hors page
    source: str = ""        # terme japonais qui ancre la preuve (T1)
    occurrences_nom: int = 0
    occurrences_candidat: int = 0
    forcee: bool = True     # l'entrée porte-t-elle `force: true` ? sinon l'interdit est inerte

    @property
    def ecrit_interdit(self) -> bool:
        return self.niveau in ("T1", "T2")


def budget_edition(nom: str) -> int:
    """Nombre d'éditions tolérées entre un nom et une dérive présumée.

    Proportionné à la longueur, et volontairement serré : `Libentina`/`Libertina` = 1 édition
    sur 9 caractères, donc retenu. **`Avion`/`Areion` = 2 sur 6, donc rejeté — délibérément**,
    parce que tout réglage assez large pour l'attraper rattrape aussi « Les » → « Vers ».
    Cette limite est TESTÉE, pour qu'un futur élargissement la casse bruyamment."""
    return 1 if len(nom) <= 7 else 2


def distance_edition(a: str, b: str, budget: int = 99) -> int:
    """Distance de Levenshtein, bornée : renvoie `budget + 1` dès que le seuil est dépassé.

    Une vraie distance d'édition, et non le ratio de `difflib.SequenceMatcher` du mode
    exploratoire. Mesuré sur le tome : à son seuil de 0,78, ce ratio produit **11 groupes
    dont 9 de bruit** — `Qu'est-ce ~ Est-ce` (0,80), `Désolé ~ Désolée`, `Comte ~ Vicomte`,
    `Cibles ~ Cible`, `Attaque ~ Attaquez`, `Allez-y ~ Allez`, `Hihi ~ Hihihi`, `KGI-6 ~
    KGI-7`, `Mitsukage ~ Mitsukage-san`. Un ratio relatif à la longueur ne sépare pas une
    variante d'orthographe d'une flexion française.

    Mais le vrai correctif n'est pas un meilleur seuil : c'est de ne comparer qu'aux **noms du
    glossaire**, jamais les mots entre eux. Aucun des neuf groupes ci-dessus n'implique un nom
    canonique, donc aucun n'est même examiné."""
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > budget:
        return budget + 1
    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        courante = [i]
        for j, cb in enumerate(b, start=1):
            courante.append(min(precedente[j] + 1,          # suppression
                                courante[j - 1] + 1,        # insertion
                                precedente[j - 1] + (ca != cb)))   # substitution
        if min(courante) > budget:
            return budget + 1
        precedente = courante
    return precedente[-1]


def est_pluriel(nom: str, candidat: str) -> bool:
    """`Kataphrakts` n'est pas une dérive de `Kataphrakt` : c'est son pluriel.

    Le bannir ferait remplacer le pluriel par le singulier au milieu d'une phrase. Le champ
    `pluriel:` du glossaire existe précisément pour cela — le rapport le propose."""
    bas = candidat.lower()
    return bas in (nom.lower() + "s", nom.lower() + "x")


def candidats(texte: str) -> set[str]:
    """Mots capitalisés éligibles à l'examen : assez longs, hors lexique courant."""
    return {m.group(0) for m in _MOT_CAPITALISE.finditer(texte or "")
            if len(m.group(0)) >= LONGUEUR_MIN and m.group(0) not in MOTS_COURANTS}


def compter_occurrences(textes: list[str], forme: str) -> int:
    """Occurrences de `forme` comme mot entier.

    ⚠ Frontières `\\b`, EXACTEMENT celles de `core.glossary_force.enforce_force`. Exclure
    l'apostrophe du contexte gauche paraît prudent et l'est moins : `l'Areyon` ne serait pas
    compté, et une forme bannie survivant à une élision passerait pour éliminée."""
    return len(re.findall(rf"\b{re.escape(forme)}\b", "\n".join(textes)))


def capitalise_en_milieu(textes: list[str], mot: str) -> bool:
    """Le mot apparaît-il au moins une fois AILLEURS qu'en tête de phrase ?

    Une capitale de début de réplique ne prouve rien — dans une bulle, presque tout mot peut
    s'y trouver. En milieu de phrase, elle signe un nom propre."""
    motif = re.compile(rf"\b{re.escape(mot)}\b")
    for texte in textes:
        for m in motif.finditer(texte or ""):
            avant = texte[:m.start()].rstrip()
            if avant and avant[-1] not in _AVANT_PHRASE:
                return True
    return False


def _entrees(glo: dict):
    """(catégorie, entrée, nom) des entrées surveillables du glossaire."""
    for cat in ENTITY_CATS:
        for e in glo.get(cat) or []:
            nom = (e.get("nom") or "").strip()
            if len(nom) >= LONGUEUR_MIN:
                yield cat, e, nom


def formes_connues(glo: dict) -> set[str]:
    """Toutes les formes déjà décrites par le glossaire, en minuscules.

    Un candidat déjà listé n'est pas une dérive à découvrir : soit il est canonique, soit il
    est déjà banni — et le forçage s'en charge."""
    connues: set[str] = set()
    for _cat, e, nom in _entrees(glo):
        connues.add(nom.lower())
        for champ in ("variantes", "interdits", "pluriel"):
            valeur = e.get(champ)
            for f in ([valeur] if isinstance(valeur, str) else (valeur or [])):
                if f and f.strip():
                    connues.add(f.strip().lower())
    return connues


def _eligible(nom: str, candidat: str, connues: set[str]) -> bool:
    """Les gardes communes à tous les niveaux, dans l'ordre du moins cher au plus cher."""
    if len(candidat) < LONGUEUR_MIN:
        return False
    if candidat.lower() == nom.lower() or candidat.lower() in connues:
        return False
    if est_pluriel(nom, candidat):
        return False
    budget = budget_edition(nom)
    return 0 < distance_edition(nom, candidat, budget) <= budget


def derives_ancrees(glo: dict, texts_jp: list[str], textes_fr: list[str],
                    *, page: int = 0) -> list[Derive]:
    """**T1** — dérives prouvées par le japonais de la bulle elle-même.

    C'est la seule preuve qui ne repose pas sur une statistique de volume : si l'OCR de la
    bulle contient `カタフラクト` et que le français y écrit `Kataphrakto`, il n'y a rien à
    interpréter. D'où le droit de corriger **ce run** — l'appelant ajoute l'interdit puis
    laisse `enforce_force` faire le remplacement, avec ses garde-fous d'élision et d'accord."""
    connues = formes_connues(glo)
    out: list[Derive] = []
    for i, fr in enumerate(textes_fr or []):
        jp = texts_jp[i] if texts_jp and i < len(texts_jp) else ""
        if not (fr or "").strip() or not (jp or "").strip():
            continue
        mots = candidats(fr)
        if not mots:
            continue
        for cat, e, nom in _entrees(glo):
            ancre = next((s for s in (e.get("termes_source") or []) if s and s in jp), "")
            if not ancre:
                continue
            for candidat in sorted(mots):
                if _eligible(nom, candidat, connues):
                    out.append(Derive(nom=nom, candidat=candidat, categorie=cat, niveau="T1",
                                      page=page, bulle=i + 1, source=ancre,
                                      forcee=bool(e.get("force"))))
    return out


def derives_de_volume(glo: dict, textes: list[str], *, deja: set[str] | None = None,
                      cfg: dict | None = None) -> list[Derive]:
    """**T2 et T3** — ce que seule la statistique du tome entier peut dire.

    T2 exige que le nom canonique DOMINE : au moins `min_occurrences` occurrences et au moins
    `dominance` fois celles du candidat. Une forme majoritaire n'est pas une faute d'orthographe,
    c'est un choix de traduction — et l'écraser serait pire que de la laisser.

    T3 n'écrit rien : c'est une piste pour le rapport, pas une décision."""
    c = {**_DEFAUTS_DERIVE, **(cfg or {})}
    connues = formes_connues(glo)
    deja = {d.lower() for d in (deja or set())}
    tous = candidats("\n".join(t for t in textes if t))
    out: list[Derive] = []
    for cat, e, nom in _entrees(glo):
        n_nom = compter_occurrences(textes, nom)
        for candidat in sorted(tous):
            if candidat.lower() in deja or not _eligible(nom, candidat, connues):
                continue
            n_cand = compter_occurrences(textes, candidat)
            domine = (n_nom >= int(c["min_occurrences"])
                      and n_nom >= int(c["dominance"]) * max(1, n_cand))
            if not domine and not capitalise_en_milieu(textes, candidat):
                continue        # T3 sans capitale de milieu de phrase : trop faible, on jette
            out.append(Derive(nom=nom, candidat=candidat, categorie=cat,
                              niveau="T2" if domine else "T3",
                              occurrences_nom=n_nom, occurrences_candidat=n_cand,
                              forcee=bool(e.get("force"))))
    return out


def appliquer_derives(glo: dict, derives: list[Derive]) -> int:
    """Écrit les dérives T1 et T2 dans le champ **`interdits`** de leur entrée.

    > ⚠ **Jamais dans `variantes`.** `variantes` est la CLÉ DE RECHERCHE de
    > `core.glossary_build._find_any` : y déposer une faute ferait fusionner une future entrée
    > légitime dans la mauvaise, et la corruption serait silencieuse et durable. `interdits`
    > porte exactement le sens voulu — « ne produis jamais cette forme » — et c'est ce que lit
    > `enforce_force`.

    Idempotent : réappliquer une dérive déjà écrite ne compte pas. Renvoie le nombre d'ajouts
    réels, ce qui permet à l'appelant de n'écrire le fichier que s'il a changé."""
    par_nom = {nom.lower(): e for _cat, e, nom in _entrees(glo)}
    ajouts = 0
    for d in derives:
        if not d.ecrit_interdit:
            continue
        e = par_nom.get(d.nom.lower())
        if e is None:
            continue
        interdits = list(e.get("interdits") or [])
        if any(x.strip().lower() == d.candidat.lower() for x in interdits if x):
            continue
        interdits.append(d.candidat)
        e["interdits"] = interdits
        ajouts += 1
    return ajouts


def proposer_pluriels(glo: dict, textes: list[str]) -> list[tuple[str, str, int]]:
    """(nom, pluriel observé, occurrences) pour les entrées dont le pluriel n'est pas déclaré.

    `Kataphrakts` ×8 sur le tome : ce n'est pas une dérive à bannir, c'est un champ `pluriel:`
    qui manque. Le distinguer évite au rapport de crier au loup huit fois."""
    out = []
    for _cat, e, nom in _entrees(glo):
        if (e.get("pluriel") or "").strip():
            continue
        for suffixe in ("s", "x"):
            n = compter_occurrences(textes, nom + suffixe)
            if n:
                out.append((nom, nom + suffixe, n))
                break
    return out


def forcer_bulles(textes: list[str], glo: dict) -> tuple[list[str], int, list[str]]:
    """Applique les entrées `force: true` du glossaire à chaque bulle.

    Renvoie `(textes, n_remplacements, refus)`. Bulle par bulle et non sur la page
    concaténée : `enforce_force` lit une fenêtre de contexte arrière pour décider de l'accord
    et de l'élision, et la fin d'une bulle n'est pas le contexte grammatical du début de la
    suivante — concaténer ferait lire « … arrive. » comme déterminant du premier mot d'après.
    """
    if not glo or not textes:
        return textes, 0, []
    sortie: list[str] = []
    total = 0
    refus: list[str] = []
    for texte in textes:
        if not texte or not texte.strip():
            sortie.append(texte)
            continue
        forced, n = enforce_force(texte, glo, refus)
        sortie.append(forced)
        total += n
    return sortie, total, refus


def compter_forcees(glo: dict) -> int:
    """Nombre d'entrées `force: true` du glossaire — le rapport doit pouvoir distinguer
    « 0 remplacement parce que tout était déjà canonique » de « 0 remplacement parce
    qu'aucune entrée n'impose quoi que ce soit »."""
    from core.glossary import ENTITY_CATS
    return sum(1 for cat in ENTITY_CATS for e in (glo.get(cat) or [])
               if e.get("force") and (e.get("nom") or "").strip())


def contexte_terminologue(glo_txt: str, page: int, total: int,
                          texts_jp: list[str], deja_fr: list[str] | None = None) -> str:
    """Message utilisateur du terminologue pour une planche.

    Le japonais OCR est donné comme SOURCE (champ `termes_source` du glossaire) : c'est lui
    qui permet au relevé d'ancrer « リベルティナ → Libertina » plutôt que de constater une
    orthographe française au hasard. Le français déjà traduit est joint quand il existe — sur
    un tome déjà traduit, il donne au terminologue les variantes réellement produites, donc de
    quoi les lister en `interdits`."""
    bulles = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts_jp) if (t or "").strip())
    parts = [p for p in (glo_txt,) if p]
    parts.append(
        "# PLANCHE {}/{} — bulles en JAPONAIS (source, ordre de lecture)\n{}".format(
            page, total, bulles or "(aucun texte)"))
    if deja_fr and any((t or "").strip() for t in deja_fr):
        parts.append("# TRADUCTION FRANÇAISE DÉJÀ PRODUITE POUR CES MÊMES BULLES\n"
                     "# (relève les variantes d'orthographe d'un même nom : elles vont en "
                     "`interdits`)\n"
                     + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(deja_fr)
                                 if (t or "").strip()))
    return "\n\n".join(parts)


def relever_page(agent, glo: dict, index: dict, *, page: int, total: int,
                 texts_jp: list[str], deja_fr: list[str] | None = None,
                 glo_budget: int = 1500, max_tokens: int = 1024) -> tuple[str, dict]:
    """Un appel de terminologue sur une planche, fusionné aussitôt dans `glo`.

    Renvoie `(notes, ajouts)`. La fusion est **incrémentale** comme côté light novel : chaque
    planche voit le glossaire déjà construit par les précédentes et l'enrichit tout de suite,
    ce qui évite les décisions contradictoires d'une planche à l'autre (genre, orthographe,
    variantes). `index` est l'index de `core.glossary_build.build_index`, muté en place par
    `merge_notes` — sans lui, la recherche de doublon redevient un scan linéaire sur un
    glossaire qui accumule toute une série."""
    if not any((t or "").strip() for t in texts_jp):
        return "", {"ajouts": 0, "fusions": 0, "conflits": 0}
    user = contexte_terminologue(glossary.to_text(glo, max_tokens=glo_budget),
                                 page, total, texts_jp, deja_fr)
    notes = agent.run(user, dry_payload="- (rien à signaler)", max_tokens=max_tokens)
    return notes, fusionner(notes, glo, index)


def fusionner(notes: str, glo: dict, index: dict) -> dict:
    """Fusionne des notes (fraîches ou relues du cache) dans le glossaire vivant."""
    if not (notes or "").strip():
        return {"ajouts": 0, "fusions": 0, "conflits": 0}
    return glossary_build.merge_notes(glo, notes, index=index)
