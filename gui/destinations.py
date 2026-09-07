# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Catalogue des destinations de la navigation latérale — **déclaré ici, en Python nu**.

## Pourquoi une seconde table, et pas des entrées dans `gui/actions.py`

Parce que les deux tables ne répondent pas à la même question. `actions.py` dit *ce que
l'application sait faire* ; celle-ci dit *où l'on peut se trouver*. Une destination porte un
ordre dans le pane, une icône, un besoin de tome et une place (corps ou pied) — quatre
propriétés qu'une action n'a pas, et qui n'ont rien à faire dans un catalogue de menus.

Le patron, lui, est **exactement** celui de `gui/actions.py`, et c'est délibéré : une table
gelée, aucun import Qt, et un test qui la parcourt sans construire de fenêtre.

## ⚠ Les raccourcis restent déclarés dans `gui/actions.py`

Ici on porte le **nom** de l'action qui transporte le raccourci (`raccourci="aller_manga"`) ;
la **séquence** (`Ctrl+2`) vit dans `actions.SEQUENCES_DESTINATIONS`. Deux catalogues de
séquences seraient deux vérités, et le `Ctrl+Shift+S` posé deux fois au lot 18 est exactement
le défaut que cette séparation empêche de rejouer. `tests/test_gui_destinations.py` croise les
deux tables et refuse qu'une destination nomme une action qui n'existe pas, ou qu'une séquence
soit déclarée par deux entrées.

## Le verdict de nommage — `PLAN-31` étape 0.2, tranché le 2026-09-04

L'utilisateur avait demandé **LN / MANGA / WEB / Génération d'Image / Gestion des Œuvres /
Modification**. Ce qui est retenu, et pourquoi :

| Demandé | Retenu | Motif |
|---|---|---|
| — | **Accueil** | il faut un endroit qui n'ouvre rien |
| LN | **Light novel** | déjà le libellé du dépôt (`gui/lanceur.py`) ; un sigle en nav latérale ne se devine pas |
| MANGA | **Manga** | — |
| WEB | **Webtoon** | « WEB » se lit « site web » une fois sur deux, et ce n'est **pas** une brique : c'est `--format webtoon` du même orchestrateur |
| Génération d'Image | **Illustrations** | la destination porte un catalogue et une galerie, pas seulement un bouton |
| Gestion des Œuvres | **Œuvres** | une nav latérale nomme l'objet, pas l'activité |
| Modification | **Retouche** | « Modification » ne dit pas de quoi ; le panneau retouche des **planches** |
| — | **Réglages**, **Diagnostic** | en pied de pane, convention Fluent |

## Pourquoi une nav latérale, et pas trois onglets de plus

Fluent / WinUI `NavigationView` : navigation **latérale** recommandée de 5 à 10 destinations de
premier niveau d'importance égale, navigation **haute** en dessous de 5. Sept destinations plus
deux entrées de pied : dans la fourchette de la latérale, hors de celle des onglets. NN/g dit la
même chose autrement — un onglet est un conteneur, pas une destination.

## Les trois modes de largeur

`mode_pour_largeur()` est ici, en Python nu, parce que c'est une **décision** et que la règle de
couche du dépôt veut que tout ce qui décide se teste sans PySide6 (`gui/__init__.py`). Les
seuils sont ceux de `NavigationView` : 1008 px et 641 px.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Identifiant de la destination d'ouverture. Elle n'ouvre aucun tome — c'est tout son objet.
ACCUEIL = "accueil"

#: Les trois modes d'affichage du pane, repris de `NavigationView`.
DEPLOYE = "deploye"        # pane large, icône + libellé
COMPACT = "compact"        # bande d'icônes seules
MINIMAL = "minimal"        # pane replié, un bouton menu le déplie

#: Seuils, en pixels de largeur de fenêtre. Ce sont ceux de la documentation Fluent :
#: ≥ 1008 px déployé, 641-1007 px compact, ≤ 640 px minimal.
SEUIL_DEPLOYE = 1008
SEUIL_COMPACT = 641


def mode_pour_largeur(largeur: int) -> str:
    """Le mode de pane qu'impose une largeur de fenêtre.

    Fonction pure, et c'est le point : la bascule adaptative se vérifie sans écran, sans Qt et
    sans fenêtre — donc dans le job de CI qui n'installe pas PySide6."""
    if largeur >= SEUIL_DEPLOYE:
        return DEPLOYE
    return COMPACT if largeur >= SEUIL_COMPACT else MINIMAL


@dataclass(frozen=True)
class Destination:
    """Une entrée de la navigation latérale.

    `identifiant` — le nom que `gui/fenetre.py` relie à une fabrique `page_<identifiant>`
    (destinations de corps) ou à l'action nommée par `action` (entrées de pied).
    `libelle` — ce que lit l'utilisateur. Cf. le verdict de nommage en tête de module.
    `icone` — une clé de `gui/icones.py:TRACES`. Un item de nav sans icône devient illisible
    en mode compact, où le libellé disparaît.
    `raccourci` — le **nom de l'action** qui porte la séquence, jamais la séquence elle-même.
    `exige_tome` — la destination a-t-elle besoin d'un tome ouvert pour dire quelque chose ?
    C'est une propriété de la DESTINATION, pas une prescription : rien n'est grisé pour cette
    raison, mais l'accueil s'en sert pour dire ce qu'un clic va demander.
    `pied` — l'entrée vit dans le pied du pane (convention Fluent pour les réglages).
    `action` — l'identifiant de l'action du catalogue qu'une entrée de pied déclenche, quand
    elle ouvre un dialogue plutôt qu'une page.
    `infobulle` — ce que l'item promet, en une phrase.

    ## ⚠ MISE À JOUR lot 36 (2026-09-06) — une entrée de pied PEUT porter une page

    Le lot 31 écrivait ici : « une entrée de pied n'est pas une page : elle ouvre le dialogue
    qui existe déjà, et fabriquer deux écrans neufs pour les réglages et le diagnostic serait
    faire le `PLAN-36` sous couvert de coquille ». C'était juste, et c'est le `PLAN-36` qui le
    lève — pour le **Diagnostic seul**.

    La règle est donc celle-ci, et elle se lit sur la table : une entrée de pied qui nomme une
    `action` ouvre ce dialogue (c'est **Réglages**, et ça ne change pas) ; une entrée de pied
    sans `action` a une page `page_<identifiant>`, comme n'importe quelle destination de
    corps. Ce que Fluent range en pied de pane est une question de PLACE, pas de nature.
    """

    identifiant: str
    libelle: str
    icone: str
    raccourci: str | None = None
    exige_tome: bool = False
    pied: bool = False
    action: str = ""
    infobulle: str = ""

    @property
    def fabrique(self) -> str:
        """Le nom de la méthode de `Fenetre` qui construit la page de cette destination."""
        return f"page_{self.identifiant}"


#: **La** table, dans l'ORDRE du pane. Un ajout ici suffit à faire apparaître l'item, l'entrée
#: de menu et le raccourci ; les tests d'unicité et de couverture s'appliquent immédiatement.
CATALOGUE: tuple[Destination, ...] = (
    Destination(ACCUEIL, "Accueil", "accueil", raccourci="aller_accueil",
                infobulle="Le point d'entrée. Il n'ouvre aucun tome et ne charge aucun "
                          "modèle."),
    Destination("light_novel", "Light novel", "light_novel", raccourci="aller_light_novel",
                infobulle="Lancer un run de traduction de roman (run.py)."),
    Destination("manga", "Manga", "manga", raccourci="aller_manga",
                infobulle="Lancer un run de traduction de planches (run_manga.py)."),
    Destination("webtoon", "Webtoon", "webtoon", raccourci="aller_webtoon",
                infobulle="Le même orchestrateur que « Manga », avec --format webtoon : sens "
                          "de lecture et découpage des bandes très allongées."),
    Destination("illustrations", "Illustrations", "illustrations",
                raccourci="aller_illustrations",
                infobulle="Catalogue des personnages, coût annoncé, galerie et relecture."),
    Destination("oeuvres", "Œuvres", "oeuvres", raccourci="aller_oeuvres",
                infobulle="Créer un projet, ouvrir le dossier de sources."),
    Destination("retouche", "Retouche", "retouche", raccourci="aller_retouche",
                exige_tome=True,
                infobulle="Corriger les zones et les répliques d'une planche, puis relettrer."),
    Destination("reglages", "Réglages", "reglages", pied=True, action="preferences",
                infobulle="Réglages de l'INTERFACE seulement. config.yaml n'est jamais "
                          "réécrit."),
    # ⚠ Pas d'`action` : depuis le lot 36, le Diagnostic est une PAGE (`page_diagnostic`), pas
    # un dialogue de capture de texte. L'action `diagnostic` du catalogue existe toujours et
    # mène ici — c'est `Fenetre.action_diagnostic`, qui navigue au lieu d'ouvrir une boîte.
    Destination("diagnostic", "Diagnostic", "diagnostic", pied=True,
                infobulle="Ce qui manque à cette installation, ce que ça coûte, et quoi "
                          "faire — l'équivalent structuré de « run.py --check » et "
                          "« run_manga.py --check »."),
)


def destinations() -> tuple[Destination, ...]:
    """Toute la table, dans l'ordre du pane."""
    return CATALOGUE


def corps() -> tuple[Destination, ...]:
    """Les destinations du corps du pane — celles qui portent une page."""
    return tuple(d for d in CATALOGUE if not d.pied)


def pied() -> tuple[Destination, ...]:
    """Les entrées du pied du pane (convention Fluent pour les réglages et le diagnostic)."""
    return tuple(d for d in CATALOGUE if d.pied)


def pages() -> tuple[Destination, ...]:
    """Toutes les destinations qui portent une PAGE — corps, plus le pied sans `action`.

    ⚠ C'est ce que parcourt `tests/test_gui_destinations.py` pour vérifier qu'une fabrique
    `page_<identifiant>` existe. Se contenter de `corps()` laisserait le Diagnostic sans
    couverture, et son absence de fabrique tomberait au premier clic — ce que `getattr` sans
    repli garantit d'ailleurs bruyamment."""
    return tuple(d for d in CATALOGUE if not d.action)


def dialogues() -> tuple[Destination, ...]:
    """Les entrées qui ouvrent un dialogue existant au lieu d'une page. Réglages, aujourd'hui."""
    return tuple(d for d in CATALOGUE if d.action)


def par_identifiant(identifiant: str) -> Destination | None:
    for destination in CATALOGUE:
        if destination.identifiant == identifiant:
            return destination
    return None


def identifiants() -> tuple[str, ...]:
    return tuple(d.identifiant for d in CATALOGUE)


def suivante(identifiant: str) -> str:
    """La destination de corps suivante, en boucle — ce que `Ctrl+Tab` fait désormais.

    Il faisait « onglet suivant » sur trois onglets ; il fait la même chose sur sept
    destinations. Les entrées de pied en sont exclues : `Ctrl+Tab` ne doit pas ouvrir un
    dialogue de réglages au milieu d'un cycle de navigation."""
    liste = [d.identifiant for d in corps()]
    if identifiant not in liste:
        return liste[0]
    return liste[(liste.index(identifiant) + 1) % len(liste)]
