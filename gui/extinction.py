# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le compte à rebours d'extinction — **ce qui décide, sans Qt**.

## Pourquoi un module pour trois phrases

Parce que l'extinction est **la seule action de l'application qui touche à la machine**. Tout
le reste écrit dans `build/`, et le pire qu'un défaut y produise est un tome à refaire. Ici, le
pire est un PC éteint pendant qu'on travaille dessus.

Une décision de cette portée ne doit pas vivre dans un `QTimer`. Elle vit ici, en Python nu,
et `tests/test_gui_extinction.py` la vérifie sans écran : quand on éteint, quand on n'éteint
pas, ce que le compte à rebours affiche, et ce que le journal a écrit au moment où il a
commencé.

## Les quatre règles, et d'où elles viennent

1. **pas d'extinction après un arrêt propre.** C'est `core/cli.finalize_power` mot pour mot :
   « Sur Ctrl+C (`interrupted=True`), pas d'extinction ». Un arrêt demandé est une présence
   humaine ; éteindre sous le nez de qui vient de cliquer « Arrêter » serait absurde ;
2. **extinction après un ÉCHEC, en revanche, oui.** Même source : « On n'annule PAS
   l'extinction sur erreur — ça éviterait au PC de tourner toute la nuit pour rien. » Le
   comportement de l'interface est celui de la ligne de commande, ou l'un des deux ment ;
3. **le compte à rebours est visible et annulable sans chercher.** Le `PLAN-32` L32.5 refuse
   toute modale à la fin d'un run — « un run de nuit finit à 3 h du matin et l'utilisateur
   peut être en train de taper une réplique » — mais un compte à rebours d'extinction **doit**
   se voir. Le bandeau de run est le bon endroit : il est déjà là, déjà visible depuis
   n'importe quelle destination, et il ne vole pas le focus ;
4. **une ligne de journal part au moment où le compte à rebours commence.** Pas à la fin :
   à ce moment-là, la machine s'éteint et le journal n'est plus lu par personne.
"""
from __future__ import annotations

from dataclasses import dataclass

from .parametres import DELAI_EXTINCTION, DELAI_MAX, DELAI_MIN

#: Ce que `core/power.shutdown` remonte de force. Le redire ici évite d'annoncer 3 s et d'en
#: attendre 5 : « un chiffre affiché est lu comme une promesse ».
PLANCHER_SYSTEME = 5


def delai_valide(delai) -> int:
    """Le délai réellement appliqué, bornes du formulaire ET plancher système compris."""
    try:
        valeur = int(delai)
    except (TypeError, ValueError):
        valeur = DELAI_EXTINCTION
    valeur = max(DELAI_MIN, min(DELAI_MAX, valeur))
    return max(PLANCHER_SYSTEME, valeur)


def doit_eteindre(*, arme: bool, arret_demande: bool) -> bool:
    """Éteint-on ? Cf. les règles 1 et 2 du module.

    ⚠ L'ÉCHEC n'est pas un motif d'annulation — c'est délibéré, et c'est le comportement de
    `core/cli.finalize_power`. Un run de nuit qui tombe à la troisième planche n'a aucune
    raison de laisser la machine allumée jusqu'au matin."""
    return bool(arme) and not bool(arret_demande)


def duree_lisible(secondes: int) -> str:
    """`125` → `« 2 min 5 s »`. Court, sans fausse précision, et jamais « 0 min »."""
    secondes = max(0, int(secondes))
    if secondes < 60:
        return f"{secondes} s"
    minutes, reste = divmod(secondes, 60)
    return f"{minutes} min" + (f" {reste} s" if reste else "")


@dataclass(frozen=True)
class Rebours:
    """L'état d'un compte à rebours, tel que le bandeau le peint.

    `restant` est en secondes ; `fini` dit que la machine part maintenant. Le compte est
    **affiché**, mais ce n'est pas lui qui éteint : `core/power.shutdown` a déjà programmé
    l'extinction auprès du système au moment où il a commencé, exactement comme
    `finalize_power` le fait en ligne de commande. Un plantage de l'interface pendant
    l'attente ne change donc rien à ce qui a été promis."""

    restant: int
    delai: int

    @property
    def fini(self) -> bool:
        return self.restant <= 0

    def phrase(self) -> str:
        if self.fini:
            return "⏻ Extinction du PC en cours."
        return (f"⏻ Extinction du PC dans {duree_lisible(self.restant)} — "
                f"« Annuler l'extinction » l'arrête.")


def rebours(delai: int, ecoule: float) -> Rebours:
    """L'état du compte à rebours après `ecoule` secondes. Fonction pure — c'est le point."""
    total = delai_valide(delai)
    return Rebours(max(0, int(round(total - max(0.0, ecoule)))), total)


def phrase_confirmation(delai: int) -> str:
    """Ce que la boîte de lancement dit de l'extinction. **Elle NOMME le délai.**

    Le `PLAN-33` L33.2 l'exige (« une confirmation qui nomme le délai »), et le
    `PLAN-33` L33.6 interdit d'y chiffrer une durée de RUN. Les deux tiennent ensemble : le
    délai d'extinction est une constante qu'on vient de saisir, pas une estimation."""
    total = delai_valide(delai)
    return (f"⚠ Le PC s'ÉTEINDRA à la fin de ce run, après un compte à rebours de "
            f"{duree_lisible(total)} affiché dans le bandeau. "
            f"« Annuler l'extinction » l'arrête, et un arrêt propre l'annule aussi.")


def phrase_journal(delai: int, annulation: str = "") -> str:
    """La ligne écrite AU DÉMARRAGE du compte à rebours (règle 4).

    `annulation` est ce que `core/power.shutdown` rend : la commande qui annule depuis un
    autre terminal. On la recopie telle quelle — c'est ce que la ligne de commande imprime, et
    c'est le seul recours si l'interface elle-même tombe pendant l'attente."""
    total = delai_valide(delai)
    ligne = f"⏻ Extinction du PC programmée dans {duree_lisible(total)}."
    if annulation:
        ligne += (f" Pour ANNULER : le bouton « Annuler l'extinction » du bandeau, ou "
                  f"« {annulation} » depuis un autre terminal.")
    return ligne


def phrase_annulation(note: str = "") -> str:
    return "Extinction annulée." + (f" ({note})" if note else "")
