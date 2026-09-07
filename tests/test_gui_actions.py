# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le catalogue des actions de la fenêtre — **sans PySide6**.

## Le test qui manquait, et ce qu'il aurait attrapé

`Ctrl+Shift+S` était déclaré DEUX fois dans la même fenêtre : sur le bouton « Enregistrer les
modifications du projet » et sur son entrée de menu, tous deux enfants de `Fenetre`. Deux
raccourcis identiques de portée fenêtre — ce que Qt ne signale pas, et qui rend le comportement
dépendant de l'ordre de création.

Le défaut est du genre qui revient : chaque raccourci ajouté est une occasion de le refaire.
D'où un test qui parcourt la déclaration plutôt qu'un test qui vérifie ce cas-là.

## Pourquoi il tourne sans Qt

`gui/actions.py` est la source unique et n'importe rien de PySide6. La couverture des méthodes
est vérifiée en LISANT `gui/fenetre.py` par `ast` : importer le module tirerait Qt, et ce test
doit tourner dans le job de CI qui ne l'installe pas — celui-là même qui compte 1 879 tests au
lieu de 2 007.
"""
from __future__ import annotations

import ast
from pathlib import Path

from gui import actions as act

RACINE = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Unicité — le test que le plan réclame nommément
# --------------------------------------------------------------------------- #

def test_aucun_raccourci_declare_deux_fois():
    """Le critère 7 du PLAN-18, dans sa forme la plus directe."""
    doublons = act.doublons()
    assert doublons == {}, (
        "raccourci(s) déclaré(s) par plusieurs actions : "
        + "; ".join(f"{seq} → {', '.join(ids)}" for seq, ids in doublons.items()))


def test_un_doublon_serait_bien_vu():
    """Le test d'unicité serait inutile s'il ne pouvait pas échouer.

    On refabrique la table avec une collision et on vérifie que la détection la voit — y
    compris écrite dans un autre ordre de modificateurs, qui est la forme sous laquelle le
    doublon passe le plus facilement inaperçu."""
    faux = (act.Action("a", "Fichier", "A", "Ctrl+Shift+S"),
            act.Action("b", "Fichier", "B", "shift+ctrl+s"))
    trouvees: dict[str, list[str]] = {}
    for action in faux:
        trouvees.setdefault(act.normaliser(action.raccourci), []).append(action.identifiant)
    assert [ids for ids in trouvees.values() if len(ids) > 1] == [["a", "b"]]


def test_la_normalisation_ignore_la_casse_et_l_ordre():
    assert act.normaliser("shift+CTRL+s") == act.normaliser("Ctrl+Shift+S")
    assert act.normaliser("ctrl++") == "Ctrl++"
    assert act.normaliser("Ctrl+-") == "Ctrl+-"
    assert act.normaliser("f1") == "F1"


def test_les_alias_comptent_dans_l_unicite():
    """`F` est un alias d'« Ajuster ». Le jour où une autre action prendrait `F`, le conflit
    serait réel — un alias est un raccourci comme un autre pour l'utilisateur."""
    assert "F" in act.sequences()
    assert act.sequences()["F"] == ["ajuster"]


# --------------------------------------------------------------------------- #
# Couverture — chaque entrée fait quelque chose
# --------------------------------------------------------------------------- #

def _methodes_de_la_fenetre() -> set[str]:
    arbre = ast.parse((RACINE / "gui" / "fenetre.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ClassDef) and noeud.name == "Fenetre":
            return {c.name for c in noeud.body
                    if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))}
    raise AssertionError("classe Fenetre introuvable dans gui/fenetre.py")


def test_chaque_action_a_sa_methode():
    """Une entrée de menu sans méthode promet et ne tient pas.

    ⚠ `Fenetre._fabriquer_action` fait un `getattr` sans repli : l'absence ferait tomber la
    construction de la fenêtre au démarrage. Ce test le dit plus tôt, et sans écran."""
    methodes = _methodes_de_la_fenetre()
    manquantes = [a.identifiant for a in act.actions() if a.gestionnaire not in methodes]
    assert manquantes == [], f"méthodes `action_…` manquantes : {manquantes}"


def test_les_six_filtres_de_pellicule_sont_dans_un_sous_menu():
    """Six filtres à la racine du menu « Affichage » le noieraient sous un réglage de tri.

    ⚠ Ils sont DÉRIVÉS de `gui/pellicule.FILTRES`, pas recopiés : deux listes qui divergeraient
    donneraient un menu proposant un filtre que le panneau ne connaît pas, dont le clic ne
    ferait rien."""
    from gui.pellicule import FILTRES
    filtres = [a for a in act.actions() if a.groupe == act.GROUPE_FILTRES]
    assert [a.libelle for a in filtres] == list(FILTRES)
    assert all(a.methode == "filtre" and a.bascule for a in filtres)
    assert all(a.donnee in FILTRES for a in filtres)


def test_toutes_les_actions_appartiennent_a_un_menu_declare():
    inconnus = {a.menu for a in act.actions()} - set(act.MENUS)
    assert inconnus == set()


def test_chaque_menu_declare_porte_au_moins_une_action():
    """Un menu vide dans la barre est un menu qu'on ouvre pour rien."""
    for nom in act.MENUS:
        assert any(isinstance(e, act.Action) for e in act.par_menu(nom)), nom


def test_les_identifiants_sont_uniques():
    identifiants = [a.identifiant for a in act.actions()]
    assert len(identifiants) == len(set(identifiants))


def test_un_menu_ne_commence_ni_ne_finit_par_un_separateur():
    """Un trait en tête ou en queue est le signe d'une entrée supprimée, pas d'une intention."""
    for nom in act.MENUS:
        entrees = act.par_menu(nom)
        assert isinstance(entrees[0], act.Action), nom
        assert isinstance(entrees[-1], act.Action), nom


# --------------------------------------------------------------------------- #
# Ce que le plan exige nommément du contenu de la table
# --------------------------------------------------------------------------- #

def test_les_raccourcis_ajoutes_par_le_lot_sont_la():
    """`Ctrl+Q`, `Ctrl+F`, `Ctrl+H`, `F1`, `Ctrl++`, `Ctrl+-`, `Ctrl+0`, `Ctrl+Tab`.

    Tous absents avant le lot 18 : « Quitter » n'avait aucun raccourci, la recherche et le
    remplacement plein-tome existaient tous les deux sans en avoir, et l'aide n'existait pas."""
    declares = set(act.sequences())
    for attendu in ("Ctrl+Q", "Ctrl+F", "Ctrl+H", "F1", "Ctrl++", "Ctrl+-", "Ctrl+0",
                    "Ctrl+Tab"):
        assert attendu in declares, attendu


def test_ajuster_garde_F_en_alias_et_prend_Ctrl_0():
    """`F` seul, dans un panneau à quatre champs de saisie, était une bombe à retardement.

    Il n'était sauvé que par la neutralisation des gestionnaires de touches pendant une
    saisie — un filet, pas une conception. `Ctrl+0` est la convention ; `F` reste accepté,
    parce que le retirer casserait la main de qui l'utilise."""
    ajuster = next(a for a in act.actions() if a.identifiant == "ajuster")
    assert ajuster.raccourci == "Ctrl+0"
    assert "F" in ajuster.alias


def test_les_actions_de_tome_sont_marquees():
    """Elles se grisent sans tome ouvert : « cette action existe, il te manque un tome » n'est
    pas le même message que « cette action n'existe pas »."""
    exigent = {a.identifiant for a in act.actions() if a.exige_tome}
    for identifiant in ("enregistrer_planche", "enregistrer_tome", "annuler", "refaire",
                        "assembler", "ouvrir_build"):
        assert identifiant in exigent, identifiant
    # …et celles qui n'en ont pas besoin ne le sont PAS : créer un projet quand il n'y en a
    # aucun est précisément le geste que le lot 18 rend possible.
    for identifiant in ("nouveau_projet", "ouvrir_sources", "diagnostic", "raccourcis",
                        "importer_glossaire", "quitter"):
        assert identifiant not in exigent, identifiant


def test_les_cinq_actions_de_la_console_ont_leur_entree():
    """L18.3 — les quatre actions d'`app.py` sans équivalent graphique, plus l'assemblage.

    Importer un glossaire, l'optimiser, tester le LLM, le diagnostic complet : aucune n'avait
    d'entrée dans l'interface, alors que toutes les quatre existent au menu de la console."""
    identifiants = {a.identifiant for a in act.actions()}
    for identifiant in ("importer_glossaire", "optimiser_glossaire", "tester_llm",
                        "diagnostic", "assembler"):
        assert identifiant in identifiants, identifiant
