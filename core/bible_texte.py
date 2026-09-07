# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L23.4 — les attributs d'apparence qui viennent du TEXTE, et qui citent leur phrase.

Le texte traduit est sous `build/<Projet>/<Tome>/chapters/*.md` : du français propre, déjà
découpé en chapitres. Ce module y cherche les passages qui parlent de l'apparence d'un
personnage, et **rend des passages, jamais des attributs**.

## Deux passes, dans cet ordre, et la première est déterministe

1. **Lexique** (ici) : une liste de mots d'apparence croisée avec le nom du personnage et ses
   `variantes` du glossaire, dans une fenêtre de N phrases. Aucun modèle. C'est cette passe
   qui donne le **dénominateur** — combien de personnages ont au moins un passage candidat —
   et c'est ce dénominateur qui dit si la passe LLM vaut la peine d'être lancée.
2. **LLM** (`tools/bible.py --proposer`, prompt `langues/<code>/prompts/bible_apparence.md`) :
   sur les seuls passages candidats, pour en extraire l'attribut normalisé.

L'ordre n'est pas une commodité. Une passe LLM sur tout le tome coûterait un appel par
chapitre pour un rendement inconnu ; la passe lexicale dit d'avance combien de passages il y
a à traiter, et sur quels personnages.

## Ce que ce module ne fait pas

Il ne décide **jamais** qu'un personnage a les cheveux blonds. Il dit : « voici la phrase du
chapitre 3 où le mot *cheveux* apparaît à deux phrases du nom Tory ». La décision est prise
plus loin, par un modèle puis par un œil, et la phrase reste attachée à l'attribut jusqu'au
bout — c'est la règle de citation de `core/bible.py`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .marqueurs import strip_images

#: Mots qui annoncent un attribut visuel, par attribut.
#:
#: **Convention d'écriture, et elle est mesurée.** Un mot terminé par `*` est une RACINE :
#: il s'apparie au début d'un mot du texte, suivi d'au plus `SUFFIXE_MAX` lettres
#: (`cheveu*` → « cheveux », `blond*` → « blonde », « blonds »). Un mot sans `*` s'apparie
#: **exactement**, aux frontières de mot.
#:
#: ⚠ La distinction n'est pas cosmétique : c'est le correctif d'un défaut mesuré. Avec un
#: simple `sous-chaîne`, `« ans »` s'appariait à *dans*, *sans*, *enfants*, et `« regard »` à
#: *regarder*, *regardait* — sur roman D, **1 257 des 1 565** passages candidats étaient des
#: faux de cette famille, soit **80,3 %**, tous rangés sous `age_apparent`. Les racines
#: courtes et ambiguës sont donc écrites sans `*`, et `regard` a été retiré : un regard n'est
#: pas un attribut dessinable.
#:
#: ⚠ Cette liste est volontairement COURTE et concrète. Une liste large (« beau », « grand »,
#: « visage ») ferait exploser le nombre de candidats sans rien ajouter de descriptible : ce
#: qu'un modèle d'image sait faire d'un attribut, c'est le dessiner, et « beau » ne se
#: dessine pas.
LEXIQUE: dict[str, tuple[str, ...]] = {
    "cheveux": ("cheveu*", "chevelure*", "mèche*", "frange*", "chignon*", "tresse*",
                "natte*", "blond*", "brun*", "roux", "rousse*", "châtain*", "coiffure*"),
    "yeux": ("yeux", "oeil", "œil", "prunelle*", "iris", "pupille*"),
    "age_apparent": ("ans", "âge", "adolescent*", "enfant*", "vieillard*", "gamin*",
                     "quadragénaire*", "quinquagénaire*", "septuagénaire*", "nourrisson*"),
    "tenue": ("uniforme*", "manteau*", "veste", "vestes", "robe*", "chemise*", "casquette*",
              "casque*", "chapeau*", "botte*", "gant*", "écharpe*", "blouse*", "tablier*",
              "cape", "capes", "armure*", "vêtement*", "tenue*", "jupe*", "pantalon*"),
    "signes": ("cicatrice*", "lunette*", "tatouage*", "bandage*", "pansement*", "monocle*",
               "barbe", "barbes", "moustache*", "borgne*", "bandeau*", "collier*"),
}

#: Lettres qu'une racine marquée `*` accepte après elle avant la frontière de mot. Deux, et
#: pas plus : à trois, `age*` attrapait *agent* et *agence*.
SUFFIXE_MAX = 2

#: Fenêtre, en phrases, entre la mention du nom et le mot d'apparence. Deux phrases de part
#: et d'autre : au-delà, le lien n'est plus une observation sur le personnage, c'est une
#: coïncidence de vocabulaire dans le même paragraphe.
FENETRE = 2

#: Longueur maximale d'une citation retenue, en caractères. Une phrase plus longue est
#: tronquée à la fin du dernier mot entier — une citation qui déborde n'est plus une citation,
#: c'est un extrait.
LONGUEUR_CITATION = 320

_FIN_DE_PHRASE = re.compile(r"(?<=[.!?…])\s+")
_FENCE_PANDOC = re.compile(r"^\s*:::.*$", re.MULTILINE)
_TITRE = re.compile(r"^\s*#{1,6}\s.*$", re.MULTILINE)
_GRAS = re.compile(r"\*{1,2}")


@dataclass(frozen=True)
class Candidat:
    """Un passage où un attribut d'apparence pourrait être dit d'un personnage."""

    nom: str
    attribut: str
    texte: str
    source: str
    #: Mot du lexique qui a déclenché le candidat. Publié pour que la liste se règle sur des
    #: cas réels et non au jugé.
    declencheur: str


def _sans_accent(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def _motif(mot: str) -> str:
    """Le fragment d'expression régulière d'une entrée du lexique, normalisée sans accent."""
    racine = mot.endswith("*")
    base = re.escape(_sans_accent(mot[:-1] if racine else mot))
    return rf"{base}[a-z]{{0,{SUFFIXE_MAX}}}\b" if racine else rf"{base}\b"


def _compiler(lexique: dict[str, tuple[str, ...]]) -> dict[str, re.Pattern]:
    """Une expression par attribut, avec le mot déclencheur capturé.

    ⚠ `\\b` en tête et jamais en simple sous-chaîne : c'est ce qui empêche « dans » de
    déclencher « ans » — le défaut qui produisait 80,3 % de faux candidats."""
    return {attribut: re.compile(r"\b(" + "|".join(_motif(m) for m in mots) + ")")
            for attribut, mots in lexique.items()}


_MOTIFS = _compiler(LEXIQUE)


def texte_propre(markdown: str) -> str:
    """Le corps d'un chapitre, débarrassé de ce qui n'est pas de la prose : marqueurs
    d'images, clôtures Pandoc `:::`, titres, et emphase Markdown.

    ⚠ `strip_images` de `core.marqueurs` fait déjà la première ligne ; on ne la réécrit pas,
    on l'appelle."""
    texte = strip_images(markdown)
    texte = _FENCE_PANDOC.sub("", texte)
    texte = _TITRE.sub("", texte)
    texte = _GRAS.sub("", texte)
    return texte


def phrases(texte: str) -> list[str]:
    """Découpe en phrases. Grossier et assumé : la ponctuation finale suivie d'un blanc.

    Un découpage linguistique exact demanderait un modèle ou une liste d'abréviations ; ce
    qu'on veut ici est une **fenêtre de voisinage**, pas une analyse syntaxique. Une phrase
    coupée en deux au mauvais endroit élargit la fenêtre d'une unité, ce qui ne change pas la
    nature du candidat."""
    brut = [p.strip() for p in _FIN_DE_PHRASE.split(texte.replace("\n", " "))]
    return [p for p in brut if p]


def _tronquer(phrase: str) -> str:
    if len(phrase) <= LONGUEUR_CITATION:
        return phrase
    coupe = phrase[:LONGUEUR_CITATION].rsplit(" ", 1)[0]
    return coupe + " […]"


def formes_du_personnage(entree: dict) -> list[str]:
    """Toutes les graphies sous lesquelles un personnage peut apparaître dans le texte : son
    `nom` rendu, ses `variantes`, et les mots de son `nom` composé pris isolément.

    Le dernier point compte : le glossaire porte « Tory Noelle » et le texte dit « Tory ». Un
    appariement sur le nom complet seul manquerait la quasi-totalité des mentions. Les
    fragments de moins de trois caractères sont écartés — « de », « la » n'identifient rien."""
    formes = {str(entree.get("nom") or "").strip()}
    formes.update(str(v).strip() for v in (entree.get("variantes") or []))
    for mot in str(entree.get("nom") or "").split():
        if len(mot) >= 3:
            formes.add(mot.strip())
    return sorted({f for f in formes if len(f) >= 3})


def _index_des_mentions(phrases_normalisees: list[str], formes: list[str]) -> set[int]:
    formes_n = [_sans_accent(f) for f in formes]
    return {i for i, p in enumerate(phrases_normalisees)
            if any(f in p for f in formes_n)}


def candidats_du_chapitre(markdown: str, source: str, personnages: list[dict],
                          *, fenetre: int = FENETRE) -> list[Candidat]:
    """Les passages candidats d'UN chapitre, pour tous les personnages à la fois.

    Une seule normalisation du texte et un seul découpage en phrases servent tous les
    personnages : sur manga A, 114 personnages contre un chapitre, refaire le
    découpage par personnage coûterait 114 fois le même travail."""
    lignes = phrases(texte_propre(markdown))
    if not lignes:
        return []
    normalisees = [_sans_accent(p) for p in lignes]
    sortie: list[Candidat] = []
    for entree in personnages:
        nom = str(entree.get("nom") or "").strip()
        if not nom:
            continue
        mentions = _index_des_mentions(normalisees, formes_du_personnage(entree))
        if not mentions:
            continue
        for i, phrase_n in enumerate(normalisees):
            if not any(abs(i - m) <= fenetre for m in mentions):
                continue
            for attribut, motif in _MOTIFS.items():
                trouve = motif.search(phrase_n)
                if trouve is None:
                    continue
                sortie.append(Candidat(nom=nom, attribut=attribut,
                                       texte=_tronquer(lignes[i]), source=source,
                                       declencheur=trouve.group(1)))
    return sortie


def candidats_du_tome(tome: Path, personnages: list[dict],
                      *, fenetre: int = FENETRE) -> list[Candidat]:
    """Les passages candidats de tous les chapitres d'un tome, dans l'ordre des chapitres.

    Un tome sans dossier `chapters/` rend une liste vide — trois tomes du corpus sont dans ce
    cas au 2026-08-29 (images extraites, texte jamais produit)."""
    dossier = Path(tome) / "chapters"
    if not dossier.is_dir():
        return []
    sortie: list[Candidat] = []
    for fichier in sorted(dossier.glob("ch*.md")):
        corps = fichier.read_text(encoding="utf-8", errors="replace")
        sortie.extend(candidats_du_chapitre(
            corps, f"chapters/{fichier.name}", personnages, fenetre=fenetre))
    return sortie


def denominateur(candidats: list[Candidat], personnages: list[dict]) -> dict:
    """Le chiffre que la passe lexicale existe pour produire, **avec son dénominateur**.

    « 18 personnages sur 24 ont au moins un passage candidat » se lit ; « 18 personnages ont
    des passages » ne se lit pas. C'est la règle des chiffres du dépôt."""
    avec = {c.nom for c in candidats}
    total = len({str(p.get("nom") or "") for p in personnages if str(p.get("nom") or "")})
    par_attribut: dict[str, int] = {}
    for c in candidats:
        par_attribut[c.attribut] = par_attribut.get(c.attribut, 0) + 1
    return {
        "personnages_avec_candidat": len(avec),
        "personnages": total,
        "passages": len(candidats),
        "par_attribut": dict(sorted(par_attribut.items())),
    }


# ─────────────────────  L23.5 — l'indice de genre, et sa précision  ─────────────────────

#: Motifs qui LÈVENT le genre d'un personnage nommé, et rien d'autre. `{nom}` y est remplacé
#: par chaque graphie du personnage, sans accent.
#:
#: ⚠ **Volontairement peu nombreux et très spécifiques.** Le champ `genre` du glossaire
#: commande les accords français : une erreur ici produit « il est arrivée » sur tout un tome.
#: Un motif large (« la phrase contient *elle* ») aurait un rappel élevé et une précision
#: inconnue ; ceux-ci sont ancrés SUR LE NOM, ce qui est la seule façon d'attribuer le signal
#: à la bonne personne dans une scène à plusieurs.
INDICES_GENRE: dict[str, tuple[str, ...]] = {
    "féminin": (
        r"\b(?:mademoiselle|madame|mlle|mme|dame|soeur|la petite|la jeune|la vieille) {nom}\b",
        r"\b{nom} (?:est|etait|n'est|n'etait|devint|restait|semblait) (?:une|la) ",
        r"\b{nom} elle-meme\b",
        r"\b{nom},? (?:cette|ma|sa|notre|votre|leur) (?:fille|femme|jeune fille|gamine)\b",
    ),
    "masculin": (
        r"\b(?:monsieur|messire|sieur|frere|le petit|le jeune|le vieux) {nom}\b",
        r"\b{nom} (?:est|etait|n'est|n'etait|devint|restait|semblait) (?:un|le) ",
        r"\b{nom} lui-meme\b",
        r"\b{nom},? (?:ce|mon|son|notre|votre|leur) (?:garcon|homme|jeune homme|gamin)\b",
    ),
}

#: Nombre minimal d'occurrences pour qu'un indice soit proposé, et écart minimal avec le
#: genre concurrent. Un personnage cité une fois avec « la jeune X » et cinq fois avec
#: « le jeune X » n'a pas un genre, il a un bruit.
INDICE_MINIMUM = 2
INDICE_ECART = 2


@dataclass(frozen=True)
class IndiceGenre:
    """Ce que le texte laisse voir du genre d'un personnage — jamais une décision."""

    nom: str
    feminin: int
    masculin: int
    exemples: tuple[str, ...] = ()

    @property
    def propose(self) -> str:
        """Le genre proposé, ou `""` — et `""` est une réponse fréquente et correcte."""
        fort, faible = ((self.feminin, self.masculin) if self.feminin >= self.masculin
                        else (self.masculin, self.feminin))
        if fort < INDICE_MINIMUM or fort - faible < INDICE_ECART:
            return ""
        return "féminin" if self.feminin > self.masculin else "masculin"


def indices_de_genre(textes: list[str], personnages: list[dict]) -> dict[str, IndiceGenre]:
    """Les indices de genre relevés dans une liste de chapitres, personnage par personnage.

    Rend un `IndiceGenre` pour CHAQUE personnage, y compris ceux à zéro : un dictionnaire qui
    n'aurait que les personnages trouvés perdrait le dénominateur."""
    corpus = [_sans_accent(texte_propre(t)) for t in textes]
    sortie: dict[str, IndiceGenre] = {}
    for entree in personnages:
        nom = str(entree.get("nom") or "").strip()
        if not nom:
            continue
        formes = [re.escape(_sans_accent(f)) for f in formes_du_personnage(entree)]
        if not formes:
            continue
        alternative = "(?:" + "|".join(formes) + ")"
        comptes = {"féminin": 0, "masculin": 0}
        exemples: list[str] = []
        for genre, motifs in INDICES_GENRE.items():
            for motif in motifs:
                expression = re.compile(motif.format(nom=alternative))
                for texte in corpus:
                    for trouve in expression.finditer(texte):
                        comptes[genre] += 1
                        if len(exemples) < 4:
                            exemples.append(f"{genre} — « {trouve.group(0)} »")
        sortie[nom] = IndiceGenre(nom=nom, feminin=comptes["féminin"],
                                  masculin=comptes["masculin"], exemples=tuple(exemples))
    return sortie


def textes_du_tome(tome: Path) -> list[str]:
    """Le corps de chaque chapitre traduit du tome. Liste vide si le tome n'a pas de texte."""
    dossier = Path(tome) / "chapters"
    if not dossier.is_dir():
        return []
    return [f.read_text(encoding="utf-8", errors="replace")
            for f in sorted(dossier.glob("ch*.md"))]
