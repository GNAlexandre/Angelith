# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La table des destinations (`gui/destinations.py`) — **sans PySide6**.

## Ce que ce fichier protège, et ce qu'il aurait attrapé

Le `Ctrl+Shift+S` posé DEUX fois au lot 18 venait de l'absence d'un point unique de
déclaration. Le lot 31 ajoute sept raccourcis d'un coup et une seconde table ; sans un test qui
croise les deux, la même faute se rejouerait immédiatement — et Qt ne signale rien : deux
raccourcis identiques de portée fenêtre rendent seulement le comportement dépendant de l'ordre
de création.

D'où quatre invariants, tous vérifiables sans écran :

1. **aucune séquence n'est déclarée deux fois**, en croisant `destinations` et
   `actions.sequences()` — donc les filtres, les thèmes et les onze raccourcis d'avant ;
2. **chaque destination nomme une action qui existe** dans le catalogue, et cette action
   pointe bien vers elle ;
3. **chaque destination de corps a une fabrique** `page_<identifiant>` dans `Fenetre` ;
4. **chaque entrée de pied nomme une action qui existe**.

## Pourquoi il tourne sans Qt

`gui/destinations.py` et `gui/actions.py` n'importent rien de PySide6. La couverture des
fabriques est vérifiée en LISANT `gui/fenetre.py` par `ast` — comme
`tests/test_gui_actions.py` le fait pour les méthodes d'action : importer le module tirerait
Qt, et ce test doit tourner dans le job de CI qui ne l'installe pas.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from gui import actions as act
from gui import destinations as dst

RACINE = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Unicité — le croisement que le plan réclame nommément
# --------------------------------------------------------------------------- #

def test_aucune_sequence_de_destination_n_est_declaree_deux_fois():
    """Critère 3 : « croise avec `actions.sequences()` pour l'unicité ».

    C'est le test qui aurait attrapé le `Ctrl+Shift+S` du lot 18, appliqué d'avance à sept
    raccourcis neufs."""
    doublons = act.doublons()
    assert doublons == {}, (
        "séquence(s) déclarée(s) par plusieurs actions : "
        + "; ".join(f"{seq} → {', '.join(ids)}" for seq, ids in doublons.items()))


def test_les_sept_destinations_ont_bien_leur_sequence():
    """`Ctrl+1` … `Ctrl+6` pour les six métier, plus l'accueil."""
    declarees = act.sequences()
    for attendu in ("Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5", "Ctrl+6"):
        assert attendu in declarees, attendu
    assert act.SEQUENCES_DESTINATIONS[dst.ACCUEIL] in declarees
    metier = [d for d in dst.corps() if d.identifiant != dst.ACCUEIL]
    assert [act.SEQUENCES_DESTINATIONS[d.identifiant] for d in metier] == [
        "Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5", "Ctrl+6"]


def test_les_sequences_ne_sont_declarees_QUE_dans_actions():
    """⚠ « Deux catalogues de raccourcis seraient deux vérités. »

    `gui/destinations.py` porte le NOM de l'action, `gui/actions.py` la séquence. Un champ
    `raccourci` qui contiendrait « Ctrl+2 » ici serait le début de la divergence."""
    source = (RACINE / "gui" / "destinations.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.keyword) and noeud.arg == "raccourci":
            valeur = getattr(noeud.value, "value", None)
            assert valeur is None or not valeur.startswith("Ctrl"), valeur
    for destination in dst.destinations():
        if destination.raccourci:
            assert destination.raccourci.startswith("aller_"), destination.identifiant


def test_chaque_destination_nomme_une_action_qui_existe():
    identifiants = {a.identifiant for a in act.actions()}
    for destination in dst.corps():
        assert destination.raccourci in identifiants, destination.identifiant


def test_l_action_d_une_destination_pointe_bien_vers_elle():
    """Une entrée « Aller à » qui nommerait une autre destination serait un clic qui ment."""
    par_identifiant = {a.identifiant: a for a in act.actions()}
    for destination in dst.corps():
        action = par_identifiant[destination.raccourci]
        assert action.donnee == destination.identifiant
        assert action.methode == "aller"
        assert action.libelle == destination.libelle
        assert action.menu == "Aller à"


# --------------------------------------------------------------------------- #
# Couverture — chaque destination mène quelque part
# --------------------------------------------------------------------------- #

def _methodes_de_la_fenetre() -> set[str]:
    arbre = ast.parse((RACINE / "gui" / "fenetre.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ClassDef) and noeud.name == "Fenetre":
            return {c.name for c in noeud.body
                    if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))}
    raise AssertionError("classe Fenetre introuvable dans gui/fenetre.py")


def test_chaque_destination_a_page_a_sa_fabrique():
    """⚠ `Fenetre._construire_page` fait un `getattr` sans repli : l'absence ferait tomber la
    navigation au premier clic. Ce test le dit plus tôt, et sans écran.

    ⚠ **MISE À JOUR lot 36** : il portait sur `dst.corps()`. Il porte maintenant sur
    `dst.pages()` — le Diagnostic est en pied ET porte une page, et se contenter du corps
    l'aurait laissé sans couverture."""
    methodes = _methodes_de_la_fenetre()
    manquantes = [d.identifiant for d in dst.pages() if d.fabrique not in methodes]
    assert manquantes == [], f"fabrique(s) `page_…` manquante(s) : {manquantes}"


def test_chaque_entree_de_pied_a_soit_une_action_soit_une_page():
    """Une entrée de pied ouvre un dialogue (Réglages) **ou** porte une page (Diagnostic).

    ⚠ Ce qui décide n'est pas la place dans le pane — Fluent y range les réglages par
    convention d'ERGONOMIE — mais la présence d'une `action`. Une entrée qui n'aurait ni l'une
    ni l'autre serait un item de navigation qui ne mène nulle part : elle promet et ne tient
    pas."""
    identifiants = {a.identifiant for a in act.actions()}
    assert dst.pied(), "le pied porte au moins Réglages et Diagnostic (convention Fluent)"
    methodes = _methodes_de_la_fenetre()
    for destination in dst.pied():
        if destination.action:
            assert destination.action in identifiants, destination.action
        else:
            assert destination.fabrique in methodes, destination.identifiant


def test_le_diagnostic_est_une_page_de_pied_depuis_le_lot_36():
    """L36.2 — la destination Diagnostic ne nomme plus d'action : elle a `page_diagnostic`.

    ⚠ L'action `diagnostic` du catalogue existe toujours et mène ici — c'est
    `Fenetre.action_diagnostic`, qui NAVIGUE au lieu d'ouvrir une boîte de texte."""
    destination = dst.par_identifiant("diagnostic")
    assert destination.pied is True
    assert destination.action == ""
    assert destination.fabrique == "page_diagnostic"
    assert "diagnostic" in {a.identifiant for a in act.actions()}


def test_pages_et_dialogues_partitionnent_le_catalogue():
    """Les deux familles ne se recouvrent pas et ne laissent rien de côté."""
    pages = {d.identifiant for d in dst.pages()}
    dialogues = {d.identifiant for d in dst.dialogues()}
    assert pages & dialogues == set()
    assert pages | dialogues == set(dst.identifiants())


def test_les_deux_entrees_de_pied_sont_celles_de_la_convention_fluent():
    assert [d.identifiant for d in dst.pied()] == ["reglages", "diagnostic"]


# --------------------------------------------------------------------------- #
# La table elle-même
# --------------------------------------------------------------------------- #

def test_les_identifiants_sont_uniques():
    identifiants = [d.identifiant for d in dst.destinations()]
    assert len(identifiants) == len(set(identifiants))


def test_l_accueil_est_en_tete_et_n_exige_aucun_tome():
    """« Il faut un endroit qui n'ouvre rien » — et il doit être le premier du pane."""
    premiere = dst.corps()[0]
    assert premiere.identifiant == dst.ACCUEIL
    assert premiere.exige_tome is False


def test_le_verdict_de_nommage_est_celui_qui_a_ete_publie():
    """L'étape 0.2 demandait un **verdict écrit**, pas un choix silencieux. Le voici, gelé.

    ⚠ « WEB » se lirait « site web » une fois sur deux ; « LN » est un sigle qui ne se devine
    pas en nav latérale ; « Modification » ne dit pas de quoi ; une nav latérale nomme l'objet
    (« Œuvres ») et non l'activité."""
    assert [d.libelle for d in dst.corps()] == [
        "Accueil", "Light novel", "Manga", "Webtoon", "Illustrations", "Œuvres", "Retouche"]
    assert [d.libelle for d in dst.pied()] == ["Réglages", "Diagnostic"]


def test_seule_la_retouche_exige_un_tome():
    """Un lanceur choisit sa cible lui-même ; l'atelier travaille à l'échelle de l'œuvre."""
    assert [d.identifiant for d in dst.destinations() if d.exige_tome] == ["retouche"]


def test_chaque_destination_porte_une_infobulle_et_une_icone():
    """En mode COMPACT le libellé disparaît : l'icône et l'infobulle deviennent le seul texte."""
    for destination in dst.destinations():
        assert destination.icone, destination.identifiant
        assert destination.infobulle, destination.identifiant


def test_la_destination_webtoon_dit_qu_elle_partage_l_orchestrateur():
    """L31.7 point 1 — « la docstring de la destination dit qu'elle partage l'orchestrateur, et
    nomme le drapeau équivalent »."""
    webtoon = dst.par_identifiant("webtoon")
    assert "--format webtoon" in webtoon.infobulle
    assert "Manga" in webtoon.infobulle


def test_par_identifiant_rend_None_sur_un_inconnu():
    assert dst.par_identifiant("licorne") is None


# --------------------------------------------------------------------------- #
# La suite de `Ctrl+Tab`
# --------------------------------------------------------------------------- #

def test_la_destination_suivante_boucle_sur_le_corps():
    identifiants = [d.identifiant for d in dst.corps()]
    vues = [dst.suivante(identifiants[-1])]
    for _ in range(len(identifiants) - 1):
        vues.append(dst.suivante(vues[-1]))
    assert vues == identifiants


def test_la_destination_suivante_ignore_le_pied():
    """`Ctrl+Tab` ne doit pas ouvrir un dialogue de réglages au milieu d'un cycle."""
    for destination in dst.pied():
        assert dst.suivante(destination.identifiant) == dst.ACCUEIL


def test_une_destination_inconnue_ramene_a_l_accueil():
    assert dst.suivante("licorne") == dst.ACCUEIL


# --------------------------------------------------------------------------- #
# Les trois modes de largeur — la décision, sans Qt
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("largeur, attendu", [
    (2560, dst.DEPLOYE),
    (1008, dst.DEPLOYE),          # le seuil EXACT est déployé
    (1007, dst.COMPACT),
    (641, dst.COMPACT),           # le seuil EXACT est compact
    (640, dst.MINIMAL),
    (320, dst.MINIMAL),
    (0, dst.MINIMAL),
])
def test_les_seuils_sont_ceux_de_navigationview(largeur, attendu):
    """≥ 1008 px déployé, 641-1007 px compact, ≤ 640 px minimal.

    Ce sont les seuils de la documentation Fluent, et ils sont ici en Python nu **parce que
    c'est une décision** : la règle de couche du dépôt veut que tout ce qui décide se teste
    sans PySide6."""
    assert dst.mode_pour_largeur(largeur) == attendu


def test_les_trois_modes_sont_distincts():
    assert len({dst.DEPLOYE, dst.COMPACT, dst.MINIMAL}) == 3
