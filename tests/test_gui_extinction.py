# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le compte à rebours d'extinction — **critère 7 du `PLAN-33`**, la partie qui décide.

L'extinction est la seule action de l'application qui touche à la machine : tout le reste
écrit dans `build/`, et le pire qu'un défaut y produise est un tome à refaire. Une décision de
cette portée ne vit donc pas dans un `QTimer` — elle vit dans `gui/extinction.py`, et ces
tests la vérifient sans écran, sans minuteur et sans éteindre quoi que ce soit.
"""
import ast
import inspect

import pytest

from gui import extinction as ext


# --------------------------------------------------------------------------- #
#  Quand on éteint, et quand on n'éteint pas
# --------------------------------------------------------------------------- #

def test_un_arret_demande_annule_l_extinction():
    """`core/cli.finalize_power` : « Sur Ctrl+C (`interrupted=True`), pas d'extinction ». Un
    arrêt demandé est une présence humaine ; éteindre sous le nez de qui vient de cliquer
    « Arrêter » serait absurde."""
    assert ext.doit_eteindre(arme=True, arret_demande=True) is False


def test_un_echec_n_annule_PAS_l_extinction():
    """⚠ Même source, et c'est délibéré : « On n'annule PAS l'extinction sur erreur — ça
    éviterait au PC de tourner toute la nuit pour rien. »

    Le comportement de l'interface est celui de la ligne de commande, ou l'un des deux ment.
    Un run de nuit qui tombe à la troisième planche n'a aucune raison de laisser la machine
    allumée jusqu'au matin."""
    assert ext.doit_eteindre(arme=True, arret_demande=False) is True


def test_sans_case_cochee_on_n_eteint_jamais():
    assert ext.doit_eteindre(arme=False, arret_demande=False) is False
    assert ext.doit_eteindre(arme=False, arret_demande=True) is False


# --------------------------------------------------------------------------- #
#  Le délai
# --------------------------------------------------------------------------- #

def test_le_delai_est_borne_par_le_formulaire_ET_par_le_systeme():
    """⚠ `core/power.shutdown` remonte de force à 5 s. Annoncer 3 s et en attendre 5 serait
    afficher un chiffre faux — « un chiffre affiché est lu comme une promesse »."""
    from gui import parametres as par

    assert ext.delai_valide(3) == ext.PLANCHER_SYSTEME
    assert ext.delai_valide(0) == ext.PLANCHER_SYSTEME
    assert ext.delai_valide(-10) == ext.PLANCHER_SYSTEME
    assert ext.delai_valide(10_000) == par.DELAI_MAX
    assert ext.delai_valide(300) == 300


def test_un_delai_illisible_retombe_sur_le_defaut_de_la_ligne_de_commande():
    from gui import parametres as par

    assert ext.delai_valide(None) == par.DELAI_EXTINCTION
    assert ext.delai_valide("bientôt") == par.DELAI_EXTINCTION


def test_le_plancher_systeme_est_bien_celui_de_core_power():
    """Deux planchers différents feraient annoncer un compte à rebours plus court que celui
    que le système applique."""
    from core import power

    source = ast.parse(inspect.getsource(power.shutdown))
    valeurs = [n.value for n in ast.walk(source)
               if isinstance(n, ast.Constant) and isinstance(n.value, int)]
    assert ext.PLANCHER_SYSTEME in valeurs, \
        "le plancher de core/power.shutdown a bougé"


# --------------------------------------------------------------------------- #
#  Le compte à rebours
# --------------------------------------------------------------------------- #

def test_le_rebours_descend_et_s_arrete_a_zero():
    assert ext.rebours(120, 0).restant == 120
    assert ext.rebours(120, 45.4).restant == 75
    assert ext.rebours(120, 119.6).restant == 0
    assert ext.rebours(120, 500).restant == 0
    assert ext.rebours(120, 500).fini is True
    assert ext.rebours(120, 0).fini is False


def test_le_rebours_ne_remonte_jamais():
    """Le `PLAN-32` interdit à la barre de progression de reculer ; un compte à rebours qui
    remonterait serait le même défaut, dans l'autre sens."""
    precedent = None
    for ecoule in range(0, 130, 7):
        etat = ext.rebours(120, ecoule)
        if precedent is not None:
            assert etat.restant <= precedent
        precedent = etat.restant


@pytest.mark.parametrize("secondes,attendu", [
    (0, "0 s"), (45, "45 s"), (60, "1 min"), (125, "2 min 5 s"), (3600, "60 min"),
])
def test_la_duree_est_lisible_sans_fausse_precision(secondes, attendu):
    assert ext.duree_lisible(secondes) == attendu


def test_la_phrase_du_rebours_dit_comment_l_annuler():
    """« Visible et annulable sans chercher » — L33.2. La phrase porte le geste, pas seulement
    le chiffre."""
    phrase = ext.rebours(120, 0).phrase()
    assert "2 min" in phrase and "Annuler l'extinction" in phrase
    assert "en cours" in ext.rebours(120, 500).phrase()


# --------------------------------------------------------------------------- #
#  Les phrases — la confirmation, le journal
# --------------------------------------------------------------------------- #

def test_la_confirmation_NOMME_le_delai():
    """L33.2 exige « une confirmation qui nomme le délai ». Elle le nomme, et elle dit les
    deux façons de l'annuler."""
    phrase = ext.phrase_confirmation(300)
    assert "5 min" in phrase
    assert "Annuler l'extinction" in phrase
    assert "arrêt propre l'annule" in phrase


def test_la_confirmation_ne_chiffre_AUCUNE_duree_de_run():
    """⚠ **Critère 11**, et le refus que le lot 33 hérite du lot 18 : « aucune constante
    mesurée ne couvre un run complet […] l'annoncer serait inventer un chiffre ».

    Le délai d'extinction est une exception apparente et pas une entorse : c'est une constante
    qu'on vient de SAISIR, pas une estimation. La phrase ne parle donc que de lui."""
    phrase = ext.phrase_confirmation(120).lower()
    # Le mot « run » y est — la phrase dit « à la fin de ce run » — mais aucun CHIFFRE ne s'y
    # rapporte : le seul de la phrase est le délai saisi.
    for mot in ("heure", "environ", "~", "estim", "durée", "restant"):
        assert mot not in phrase, mot
    chiffres = [m for m in phrase.split() if any(c.isdigit() for c in m)]
    assert chiffres == ["2"], f"un seul chiffre attendu — le délai : {chiffres}"


def test_une_ligne_de_journal_part_au_DEBUT_du_compte_a_rebours():
    """Règle 4 du module : pas à la fin — à ce moment-là, la machine s'éteint et le journal
    n'est plus lu par personne.

    Elle recopie aussi la commande d'annulation depuis un AUTRE terminal, qui est le seul
    recours si l'interface elle-même tombe pendant l'attente."""
    ligne = ext.phrase_journal(120, "shutdown /a")
    assert "programmée dans 2 min" in ligne
    assert "shutdown /a" in ligne
    assert "autre terminal" in ligne
    # …et sans commande d'annulation connue (macOS), la ligne reste vraie plutôt que vide.
    assert "programmée dans 2 min" in ext.phrase_journal(120)


def test_le_module_ne_decide_pas_avec_Qt():
    """Règle de couche du dépôt : tout ce qui décide se teste sans PySide6."""
    source = inspect.getsource(ext)
    assert "PySide6" not in source and "QtCore" not in source
