# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Relecture d'une planche traduite — **à mandat étroit**, et désactivée par défaut.

## Le constat

La brique manga n'a **aucun agent en aval**. `terminology.py` le dit : « l'étape suivante est
un lettrage déterministe ». Le roster manga ne contient pas de `correcteur` ; le light novel
en a un, câblé et livré à `null`. Ce qui sort du traducteur manga est dessiné dans la bulle.

## Ce qu'il ne faut SURTOUT pas faire

Un relecteur générique qui « améliore le style » est le pire ajout possible : il coûte un
appel par planche, rend le résultat non reproductible, et défait autant qu'il répare. La
doctrine du projet doit tenir — **l'IA ne dessine jamais**, et un accord incertain est refusé
plutôt que produit.

## Ce que fait celui-ci

Il ne voit la planche entière que pour vérifier un **petit nombre de règles explicites**, et
il ne peut proposer une correction qu'en **nommant la règle violée**. Une correction sans
règle nommée, ou nommant une règle inconnue, est **rejetée par le code** — pas par le modèle,
qui est justement la partie qu'on ne contrôle pas.

Les règles sont celles qu'une bulle isolée ne peut pas trancher, et qu'une planche peut :

    registre     cohérence du tutoiement / vouvoiement entre bulles d'un même couple
    accord       genre ou nombre indevinable bulle par bulle
    contradiction une réplique qui contredit celle à laquelle elle répond
    glossaire    un terme du glossaire présent dans la source et absent du rendu

## La quatrième règle n'a pas besoin d'un modèle, et elle est livrée sans lui

`termes_manques` la calcule **lexicalement**, sans le moindre appel : le glossaire dit quels
`termes_source` repérer et quel `nom` rendre ; la source les porte ou non, le rendu aussi.
C'est le même patron que les dérives d'orthographe de `terminology` — purement lexical, donc
actif même quand aucun agent ne l'est, donc mesurable sur les tomes déjà produits. Elle
alimente le rapport et le banc (`tools/banc.py --traduction`), qui l'attendait explicitement.

## Il est livré DÉSACTIVÉ, et c'est un résultat aussi

Comme le `correcteur` du light novel, à `null`. Un relecteur se **mesure** avant d'être
recommandé : combien de corrections proposées, combien acceptées par le code, combien jugées
justes à la relecture humaine. Les deux premiers compteurs sont ici (`stats`) ; le troisième
demande un œil, et appartient au banc. S'il ne gagne rien, on l'écrit et on le laisse à
`null`.

⚠ `manga_relecteur.md` n'est **pas** dans `core.langues.PROMPTS_REQUIS`. Un pack tiers écrit
avant ce lot deviendrait sinon invalide au démarrage — c'est-à-dire qu'un agent optionnel,
désactivé par défaut, casserait des installations qui ne l'utilisent pas. Les deux packs du
dépôt le fournissent ; un pack qui ne le fournit pas échoue seulement si on l'active, et
bruyamment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import consignes, quality_manga, terminology

#: Les règles que le relecteur a le droit d'invoquer. Une proposition qui en nomme une autre
#: est rejetée sans être lue — c'est tout l'intérêt du mandat étroit.
REGLES = {
    "registre": "tutoiement/vouvoiement incohérent entre deux bulles du même échange",
    "accord": "accord de genre ou de nombre indevinable sur une bulle isolée",
    "contradiction": "la réplique contredit celle à laquelle elle répond",
    "glossaire": "un terme du glossaire est présent dans la source et absent du rendu",
}

#: Nom de l'agent dans `manga.modeles`. Absent du roster livré : la passe ne tourne pas.
AGENT = "manga_relecteur"

#: `N | règle | correction`. Le séparateur est le pipe et non la virgule : une réplique en
#: contient, un nom de règle non.
_LIGNE = re.compile(r"^\s*(\d+)\s*\|\s*([a-zéèêà_]+)\s*\|\s*(.+?)\s*$", re.IGNORECASE)

#: Réponse d'un modèle qui n'a rien trouvé. Exigée explicitement par le prompt : une réponse
#: VIDE est indistinguable d'un appel raté, et on ne veut pas confondre les deux au rapport.
RIEN = "RAS"


@dataclass(frozen=True)
class Proposition:
    """Une correction proposée, telle que le code l'a lue. `motif_refus` vide = acceptée."""
    bulle: int                 # 1-indexé, comme la numérotation du prompt
    regle: str
    texte: str
    motif_refus: str = ""

    @property
    def acceptee(self) -> bool:
        return not self.motif_refus


# ─────────────────────────────────────────────────────────────────────────────
# La règle « glossaire », déterministe et livrée sans modèle
# ─────────────────────────────────────────────────────────────────────────────

def _formes_rendues(entree: dict) -> list[str]:
    """Toutes les graphies qui comptent comme « le terme est là » : le nom canonique, son
    pluriel, et ses variantes acceptées.

    ⚠ Les `interdits` n'en font PAS partie : une forme bannie présente dans le rendu est un
    défaut que `terminology.forcer_bulles` traite, pas une absence. Les compter ici ferait
    passer pour « terme rendu » exactement ce que le glossaire refuse."""
    formes = [(entree.get("nom") or "").strip()]
    pluriel = entree.get("pluriel")
    if isinstance(pluriel, str) and pluriel.strip():
        formes.append(pluriel.strip())
    for v in entree.get("variantes") or []:
        if v and v.strip():
            formes.append(v.strip())
    return [f for f in formes if f]


def termes_manques(sources: list[str] | None, rendus: list[str] | None, glo: dict | None,
                   *, page: int = 0) -> list[tuple[int, str, str]]:
    """`(bulle_1indexée, terme_source, nom_attendu)` pour chaque terme perdu à la traduction.

    **Aucun appel LLM.** Le glossaire dit quels `termes_source` repérer et quel `nom` rendre ;
    la comparaison est une recherche de sous-chaîne, insensible à la casse côté cible.

    ⚠ Un terme n'est réclamé que si sa bulle a **effectivement été traduite**. Une bulle vide
    est déjà signalée comme telle, par le rapport et par le rattrapage unitaire ; la compter
    ici une seconde fois ferait passer un trou de traduction pour une infidélité au
    glossaire, et gonflerait la mesure d'un facteur que personne ne saurait défalquer."""
    if not glo or not sources:
        return []
    manques: list[tuple[int, str, str]] = []
    for i, source in enumerate(sources):
        rendu = (rendus[i] if rendus and i < len(rendus) else "") or ""
        if not (source or "").strip() or not rendu.strip():
            continue
        bas = rendu.lower()
        for _cat, entree, nom in terminology._entrees(glo):
            ancre = next((s for s in (entree.get("termes_source") or [])
                          if s and s.strip() and s in source), "")
            if not ancre:
                continue
            if any(f.lower() in bas for f in _formes_rendues(entree)):
                continue
            manques.append((i + 1, ancre, nom))
    return manques


# ─────────────────────────────────────────────────────────────────────────────
# La passe LLM
# ─────────────────────────────────────────────────────────────────────────────

CONSIGNE = (
    "Tu relis une planche déjà traduite. Ton mandat est ÉTROIT : tu ne corriges QUE ce qui "
    "viole l'une des règles nommées ci-dessous, et tu ne touches à rien d'autre — ni le "
    "style, ni le rythme, ni le vocabulaire, ni la ponctuation.\n\n"
    "Règles, et leurs noms exacts :\n"
    + "".join(f"- {nom} : {desc}\n" for nom, desc in REGLES.items())
    + "\nRéponds par UNE LIGNE PAR CORRECTION, au format strict :\n"
      "numéro_de_bulle | nom_de_la_règle | réplique corrigée entière\n\n"
      f"Si rien ne viole une règle, réponds exactement « {RIEN} » et rien d'autre. "
      "Une ligne qui ne nomme pas une règle de la liste est rejetée sans être lue : ne "
      "propose pas d'amélioration hors mandat, elle sera perdue.")

#: Clé de pack pour `CONSIGNE`. Même règle que partout : le texte français reste ici.
CLE_CONSIGNE = "manga_relecteur"


def lire_propositions(brut: str, *, n: int, rendus: list[str] | None = None
                      ) -> list[Proposition]:
    """Lit la réponse du relecteur et **rejette dans le code** ce qui sort du mandat.

    Cinq refus, et chacun ferme une porte par laquelle un relecteur générique rentrerait :

    · `hors_format` — une ligne qui n'est pas `N | règle | texte`. C'est la forme d'une
      remarque libre, et une remarque libre n'a rien à faire dans une bulle ;
    · `regle_inconnue` — le modèle a inventé un nom de règle, donc un mandat ;
    · `bulle_hors_bornes` — un numéro qui ne désigne aucune bulle de la planche ;
    · `identique` — la « correction » est le texte déjà en place, à la casse et aux espaces
      près : un appel payé pour rien, et un compteur qu'il ne faut pas gonfler ;
    · `vide` — une correction qui efface une réplique. Une bulle vide est un défaut signalé,
      jamais une correction."""
    propositions: list[Proposition] = []
    for ligne in (brut or "").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.upper() == RIEN:
            continue
        m = _LIGNE.match(ligne)
        if m is None:
            propositions.append(Proposition(0, "", ligne[:80], "hors_format"))
            continue
        i, regle, texte = int(m.group(1)), m.group(2).strip().lower(), m.group(3).strip()
        texte = quality_manga.sans_prefixe(texte, n)
        if regle not in REGLES:
            propositions.append(Proposition(i, regle, texte, "regle_inconnue"))
        elif not 1 <= i <= n:
            propositions.append(Proposition(i, regle, texte, "bulle_hors_bornes"))
        elif not texte:
            propositions.append(Proposition(i, regle, texte, "vide"))
        elif (rendus and i <= len(rendus)
                and texte.strip().lower() == (rendus[i - 1] or "").strip().lower()):
            propositions.append(Proposition(i, regle, texte, "identique"))
        else:
            propositions.append(Proposition(i, regle, texte))
    return propositions


def appliquer(rendus: list[str], propositions: list[Proposition]) -> tuple[list[str], int]:
    """Applique les propositions ACCEPTÉES. Renvoie `(textes, nombre_appliqué)`.

    Une seule correction par bulle : la première acceptée gagne. Le modèle se reprend
    rarement pour le mieux, et faire dépendre le résultat de l'ordre des lignes de sa réponse
    serait la même faute que `analyser_numerotation` a déjà tranchée pour les doublons."""
    textes = list(rendus or [])
    vues: set[int] = set()
    n = 0
    for p in propositions:
        if not p.acceptee or p.bulle in vues or not 1 <= p.bulle <= len(textes):
            continue
        textes[p.bulle - 1] = p.texte
        vues.add(p.bulle)
        n += 1
    return textes, n


def prompt_relecture(sources: list[str], rendus: list[str], *, gloss_text: str = "",
                     contexte_oeuvre: str = "", lignes_bulles: list[str] | None = None,
                     manques: list[tuple[int, str, str]] | None = None,
                     pack=None) -> str:
    """Message utilisateur du relecteur : la planche entière, source et rendu appariés.

    ⚠ La fiche de registre (`contexte_oeuvre`) est ici pour la même raison qu'au traducteur,
    et à la même place — avant les exemples, jamais après : c'est une consigne de VOIX, et
    une consigne qui suit ses exemples se lit comme un commentaire sur eux.

    ⚠ Les manques de glossaire **déjà calculés** lui sont donnés plutôt que laissés à
    trouver. C'est la règle la moins intéressante à faire chercher par un modèle (elle est
    décidable), et la lui donner concentre son attention sur les trois autres."""
    parts = [p for p in (gloss_text, contexte_oeuvre) if p]
    parts.append(pack.consigne(CLE_CONSIGNE, CONSIGNE) if pack is not None else CONSIGNE)
    if manques:
        parts.append(consignes.texte(pack, "manga_relecteur_manques") + "\n"
                     + "\n".join(consignes.texte(pack, "manga_relecteur_manque_ligne",
                                                 bulle=i, source=src, nom=nom)
                                 for i, src, nom in manques))
    lignes = lignes_bulles or [f"{k + 1}. {t}" for k, t in enumerate(sources)]
    parts.append(consignes.texte(pack, "manga_relecteur_source") + "\n" + "\n".join(lignes))
    parts.append(consignes.texte(pack, "manga_relecteur_rendu") + "\n"
                 + "\n".join(f"{k + 1}. {t}" for k, t in enumerate(rendus)))
    return "\n\n".join(parts)


def relire(agent, sources: list[str], rendus: list[str], *, gloss_text: str = "",
           contexte_oeuvre: str = "", lignes_bulles: list[str] | None = None,
           glo: dict | None = None, page: int = 0, stats: dict | None = None,
           pack=None) -> tuple[list[str], list[Proposition]]:
    """Relit une planche. Renvoie `(textes, propositions)` — propositions refusées comprises.

    `agent is None` rend les textes inchangés : c'est le chemin livré, et il ne coûte rien."""
    manques = termes_manques(sources, rendus, glo, page=page)
    if stats is not None and manques:
        stats["glossaire_manque"] = stats.get("glossaire_manque", 0) + len(manques)
    if agent is None or not any((t or "").strip() for t in rendus or []):
        return list(rendus or []), []

    n = len(rendus)
    message = prompt_relecture(sources, rendus, gloss_text=gloss_text,
                               contexte_oeuvre=contexte_oeuvre, lignes_bulles=lignes_bulles,
                               manques=manques, pack=pack)
    # Plafond calé sur la planche : au pire, le relecteur réécrit toutes ses bulles.
    cap = quality_manga.bubbles_cap("\n".join(rendus), n)
    brut = agent.run(message, dry_payload=RIEN, max_tokens=cap)
    propositions = lire_propositions(brut, n=n, rendus=rendus)
    textes, appliquees = appliquer(rendus, propositions)
    if stats is not None:
        stats["relecture_appels"] = stats.get("relecture_appels", 0) + 1
        stats["relecture_proposees"] = stats.get("relecture_proposees", 0) + len(propositions)
        stats["relecture_appliquees"] = stats.get("relecture_appliquees", 0) + appliquees
        for p in propositions:
            if p.motif_refus:
                cle = f"relecture_refus_{p.motif_refus}"
                stats[cle] = stats.get(cle, 0) + 1
    return textes, propositions
