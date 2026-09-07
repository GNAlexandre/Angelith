# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La garde du travail non enregistré — **la décision, pas la boîte**.

## Ce que ce module tranche, et pourquoi il est sans Qt

Il répond à une seule question : *ce geste peut-il faire perdre du travail non écrit ?* La
réponse ne dépend d'aucun widget, elle dépend du geste — et elle se teste donc sans écran,
comme `gui/depot.py` et `gui/vue_oeuvres.py` avant elle (règle de couche, `gui/__init__.py`).
La boîte à trois choix, elle, reste dans `gui/fenetre.py` : c'est du Qt.

## Le trou que le `PLAN-31` a ouvert, et ce que la mesure en dit

Le `PLAN-31` a fait de la retouche une **destination** parmi sept, et il annonçait que
« quitter la retouche » deviendrait un changement de destination que rien ne garderait. La
mesure de l'étape 0.2 du `PLAN-35` (2026-09-05, `docs/mesures/retouche-2026-09-05.md`) dit
que ce trou **ne s'ouvre pas**, et elle dit pourquoi : les destinations vivent dans un
`QStackedWidget`, en quitter une la cache sans rien détruire. Brouillons et documents restent
en mémoire, le miroir de récupération continue d'écrire toutes les 30 s.

⚠ **La conclusion n'est donc pas « ajouter une garde de plus », c'est « nommer les six
chemins et prouver lesquels ne perdent rien ».** Un dialogue qui se pose à chaque changement
d'onglet est un dialogue qu'on apprend à cliquer sans lire, et c'est la façon la plus sûre de
perdre du travail *avec* une garde en place (`PLAN-35` L35.4).

## Les six chemins

Ils viennent du tableau de l'étape 0.2, relevé sur le dépôt en 2.28.0. Chacun est ici avec
son verdict, et le verdict est **testé** — `tests/test_gui_garde.py`.
"""
from __future__ import annotations

from typing import NamedTuple


class Chemin(NamedTuple):
    """Un geste qui quitte quelque chose, et ce qu'il coûte au travail non écrit.

    `perd_le_travail` est le seul champ qui décide. Les deux autres composent la phrase de
    la boîte, et ils vivent ici plutôt qu'au point d'appel pour la raison qui a motivé
    `_boite_travail_en_attente` au lot 18 : deux formulations pour une même garantie
    finissent par diverger, et c'est la divergence qu'on paie."""

    identifiant: str
    verbe: str
    consequence: str
    perd_le_travail: bool
    motif: str


#: Le tableau de l'étape 0.2, en code. ⚠ L'ordre est celui du plan, pour que le document de
#: mesure et ce module se relisent ligne à ligne.
CHEMINS: dict[str, Chemin] = {
    "tome": Chemin(
        "tome", "Changer de tome",
        "Ouvrir « {cible} » sans enregistrer les abandonnera.", True,
        "`PanneauEditeur.ouvrir` vide `_brouillons_par_planche`, `documents` et le cache "
        "d'aperçus : le tome qu'on quitte n'existe plus en mémoire."),
    "projet": Chemin(
        "projet", "Changer de tome",
        "Ouvrir « {cible} » sans enregistrer les abandonnera.", True,
        "Même chemin que « tome » : changer de projet repose la liste des tomes, donc "
        "rouvre un tome, donc passe par `PanneauEditeur.ouvrir`."),
    "destination": Chemin(
        "destination", "Changer de destination", "", False,
        "Les destinations vivent dans un `QStackedWidget` : en quitter une la CACHE. Rien "
        "n'est détruit, rien n'est vidé, et le miroir de récupération continue d'écrire "
        "toutes les 30 s. Revenir retrouve tout, à la planche près."),
    "fermeture": Chemin(
        "fermeture", "Quitter", "Quitter sans enregistrer les abandonnera.", True,
        "Le processus s'arrête : ce qui n'est qu'en mémoire est perdu. Le miroir de "
        "récupération le rattraperait à la session suivante, mais un filet n'est pas une "
        "décision."),
    "run": Chemin(
        "run", "Lancer un run", "", False,
        "Un run global VERROUILLE le tome ouvert (`marquer_verrou(planche=None)`) : il "
        "empêche d'écrire, il ne jette rien. Les brouillons survivent au run, et le refus "
        "d'enregistrer une planche qu'un run a réécrite est traité à l'enregistrement, par "
        "le contrôle de révision de `DocumentPlanche`."),
    "creation": Chemin(
        "creation", "Créer un projet", "", False,
        "`_apres_creation` emmène au lanceur « Manga » avec la cible présélectionnée. Elle "
        "ne touche pas au tome ouvert dans la retouche — et le lot 18 avait déjà pris soin "
        "de ne pas passer par le chemin de `_sur_fin`, pour ne pas jeter ses aperçus."),
}


def chemin(identifiant: str) -> Chemin:
    """Le chemin nommé. Lève sur un identifiant inconnu — **délibérément**.

    Un appelant qui se trompe de nom obtiendrait sinon la garde la plus permissive, donc
    aucune boîte, donc la perte silencieuse que ce module existe pour empêcher. Le même
    arbitrage que `_construire_page` fait sur une fabrique manquante."""
    try:
        return CHEMINS[identifiant]
    except KeyError:
        raise KeyError(
            f"chemin de garde inconnu : {identifiant!r}. Les six chemins de l'étape 0.2 du "
            f"PLAN-35 sont {', '.join(sorted(CHEMINS))}.") from None


def doit_demander(identifiant: str, planches_en_attente) -> bool:
    """Faut-il poser la question ? `False` veut dire « laisse passer, sans un mot ».

    Deux conditions, et **les deux** sont nécessaires : le geste doit pouvoir perdre le
    travail, et il doit y avoir du travail à perdre. C'est ce qui garantit le critère 5 du
    plan — changer de destination sans changer de tome ne déclenche aucun dialogue, même
    avec trente planches en attente."""
    return bool(chemin(identifiant).perd_le_travail) and bool(planches_en_attente)


def phrase(identifiant: str, cible: str = "") -> tuple[str, str]:
    """Le verbe et la conséquence, pour la boîte à trois choix. `cible` = « Projet / Tome »."""
    ligne = chemin(identifiant)
    return ligne.verbe, ligne.consequence.format(cible=cible)


def chemins_gardes() -> list[str]:
    """Les identifiants qui peuvent perdre du travail, triés. Sert au document de mesure."""
    return sorted(i for i, c in CHEMINS.items() if c.perd_le_travail)
