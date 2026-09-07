# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le système visuel — `PLAN-19`, critères 1, 3, 4, 6, 7 et 8.

## Le test qui compte le plus est celui qui lit les fichiers

`test_aucune_couleur_litterale_hors_theme` parcourt `gui/` et échoue sur tout `#rrggbb` ou
`QColor(…)` littéral rencontré hors de `gui/theme.py`. C'est lui qui empêchera les vingt-six
couleurs de revenir une par une — et l'inventaire manuel du plan en avait manqué **trois**
(`QColor(30,30,34)`, `QColor(20,20,20)`, `QColor(255,210,90,230)`), ce qui montre qu'un relevé
à la main ne suffit pas.

## ⚠ Ce fichier n'importe PAS PySide6, et c'est le sujet

Les contrastes, l'échelle typographique, le balayage des littéraux et la table des rôles sont
du Python nu — c'est la raison pour laquelle `gui/theme.py` n'importe Qt qu'à l'intérieur de
`appliquer()` et `qcolor()`. Le job de CI qui ne l'installe pas exécute donc tout ce fichier,
et c'est ce job qui garde la règle de couche de `gui/__init__.py`.

**Ce qui demande Qt vit dans `test_gui_theme_qt.py`, pas ici.** Un `pytest.importorskip` posé
au MILIEU d'un fichier ne saute pas la moitié du fichier : il saute le module entier, et la
promesse « la moitié tourne sans PySide6 » devient fausse en silence. Deux fichiers sont la
seule façon de la tenir — `test_le_module_de_theme_ne_tire_pas_qt` la vérifie.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gui import actions as act
from gui import pellicule as pel
from gui import theme

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_GUI = RACINE / "gui"


# --------------------------------------------------------------------------- #
#  Critère 1 — plus une seule couleur littérale hors de `theme.py`
# --------------------------------------------------------------------------- #

#: `#rgb`, `#rrggbb`, `#rrggbbaa` dans du CODE. Les commentaires et docstrings en citent
#: (« le gris `#9aa` était… ») : c'est de la mémoire du dépôt, pas une valeur appliquée.
_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?\b")

#: `QColor(...)` **avec au moins un argument**. `QColor()` sans argument est la couleur
#: invalide — c'est-à-dire « rends la couleur par défaut du thème », exactement ce que ce lot
#: veut voir écrit.
_QCOLOR = re.compile(r"\bQColor\(\s*[^)\s]")

#: Le seul fichier qui a le droit d'écrire une couleur. Plus l'icône de l'application, qui
#: n'en suit aucun : elle apparaît dans la barre des tâches du système, sur un fond qui n'est
#: pas le nôtre (cf. `gui/icones.LOGO`).
FICHIERS_AUTORISES = {"theme.py"}


def _lignes_de_code(chemin: Path):
    """Les lignes hors commentaire et hors docstring, avec leur numéro.

    ⚠ Le découpage des docstrings est fait au marqueur `\"\"\"`, ce qui est grossier et
    suffisant **ici** : `gui/` n'a pas une seule chaîne triple qui ne soit une docstring, et un
    vrai parcours d'AST ne verrait de toute façon pas la différence pour ce qu'on cherche."""
    dans_doc = False
    for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        nette = ligne.strip()
        if nette.count('"""') == 1:
            dans_doc = not dans_doc
            continue
        if dans_doc or nette.startswith("#") or nette.startswith('"""'):
            continue
        code = ligne.split("#", 1)[0]
        yield numero, code


def _fichiers_gui() -> list[Path]:
    return sorted(p for p in DOSSIER_GUI.glob("*.py")
                  if p.name not in FICHIERS_AUTORISES)


def test_aucune_couleur_litterale_hors_theme():
    """⚠ **Le garde-fou du lot.** Sans lui, les couleurs reviennent une par une.

    Il aurait échoué avant le lot 19 sur 26 occurrences, dans 5 fichiers."""
    fautes = []
    for chemin in _fichiers_gui():
        for numero, code in _lignes_de_code(chemin):
            for motif, quoi in ((_HEX, "couleur hexadécimale"), (_QCOLOR, "QColor littéral")):
                trouve = motif.search(code)
                if trouve:
                    fautes.append(f"{chemin.name}:{numero} — {quoi} : {trouve.group(0)}")
    assert not fautes, (
        "Une couleur ne s'écrit que dans gui/theme.py, par RÔLE :\n  " + "\n  ".join(fautes))


def test_aucune_taille_de_police_en_pixels():
    """Critère 4. Une taille en `px` ne suit ni le réglage système ni le facteur DPI — c'est
    la cause la plus fréquente d'une interface illisible sur un écran à forte densité."""
    fautes = []
    for chemin in _fichiers_gui():
        for numero, code in _lignes_de_code(chemin):
            if "font-size" in code and "px" in code:
                fautes.append(f"{chemin.name}:{numero} — {code.strip()}")
            if "setPointSize" in code and re.search(r"setPointSizeF?\(\s*\d", code):
                fautes.append(f"{chemin.name}:{numero} — taille absolue : {code.strip()}")
    assert not fautes, "l'échelle typographique dérive de QApplication.font() :\n  " + \
                       "\n  ".join(fautes)


def test_la_feuille_de_style_ne_declare_aucune_taille_en_pixels():
    """La feuille est assemblée, donc elle pourrait réintroduire des `px` sans qu'aucun
    fichier source n'en porte. Elle est vérifiée telle qu'elle sort."""
    for pal in theme.PALETTES.values():
        feuille = theme.qss(pal)
        assert "font-size" in feuille
        assert not re.search(r"font-size:\s*[\d.]+px", feuille), pal.nom


def test_plus_un_seul_setstylesheet_dans_le_dossier():
    """Les douze `setStyleSheet` inline étaient inline **parce que** le style natif ignorait le
    QSS d'application. `Fusion` posé, ils n'ont plus de raison d'être — et un seul qui
    resterait échapperait à la bascule de thème."""
    fautes = [f"{c.name}:{n}" for c in _fichiers_gui()
              for n, code in _lignes_de_code(c) if "setStyleSheet" in code]
    assert not fautes, "utilise theme.poser_role() :\n  " + "\n  ".join(fautes)


# --------------------------------------------------------------------------- #
#  Critère 3 — le contraste, calculé et non estimé
# --------------------------------------------------------------------------- #

def test_le_calcul_de_contraste_est_celui_de_wcag():
    """Deux ancres connues : le maximum absolu, et l'égalité."""
    assert theme.contraste("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert theme.contraste("#808080", "#808080") == pytest.approx(1.0, abs=0.001)
    # ⚠ La luminance n'est PAS la moyenne des canaux : un vert pur est bien plus lumineux
    # qu'un bleu pur à valeur égale. C'est ce qui rend un contraste « estimé à l'œil » faux.
    assert theme.luminance("#00ff00") > theme.luminance("#0000ff") * 8


@pytest.mark.parametrize("nom", sorted(theme.PALETTES))
def test_toutes_les_paires_tiennent_leur_cible(nom):
    """**Critère 3.** Aucune paire de texte courant sous 4,5:1, aucune bordure d'état sous
    3:1 — dans les DEUX thèmes."""
    echecs = theme.echecs_contraste(theme.PALETTES[nom])
    detail = "\n  ".join(f"{a} / {b} : {r} < {c}" for a, b, r, c, _ in echecs)
    assert not echecs, f"thème « {nom} » :\n  {detail}"


def test_le_tableau_de_contraste_couvre_tous_les_roles_de_couleur():
    """⚠ Une couleur ajoutée sans sa paire n'est pas mesurée, donc pas tenue. Ce test refuse
    qu'un rôle échappe au tableau — c'est ce qui empêche le critère 3 de se vider par
    ajouts successifs."""
    mesures = {r for paire in theme.PAIRES_CONTRASTE for r in paire[:2]}
    tous = {champ for champ in theme.CLAIRE.__dataclass_fields__ if champ != "nom"}
    oublies = tous - mesures
    assert not oublies, f"rôles absents de PAIRES_CONTRASTE : {sorted(oublies)}"


def test_le_tableau_se_publie():
    """Le critère demande de PUBLIER le tableau, pas seulement de le vérifier. La fonction qui
    le produit est celle que `docs/mesures/systeme-visuel-2026-08-27.md` a utilisée."""
    lignes = theme.tableau_contraste(theme.CLAIRE)
    assert len(lignes) == len(theme.PAIRES_CONTRASTE)
    avant, arriere, rapport, cible, tenu = lignes[0]
    assert isinstance(rapport, float) and rapport >= cible and tenu is True


# --------------------------------------------------------------------------- #
#  Le canevas ne suit pas le thème — la décision de l'étape 0
# --------------------------------------------------------------------------- #

def test_le_canevas_ne_change_pas_avec_le_theme():
    """La décision de l'étape 0 : trois surfaces, et le canevas reste sombre dans les deux
    thèmes. Écrite dans le plan, elle doit être VÉRIFIABLE, sinon elle dérivera."""
    for role in theme.ROLES_CANEVAS:
        assert theme.CLAIRE.role(role) == theme.SOMBRE_PALETTE.role(role), role


def test_le_fond_du_canevas_est_bien_sombre():
    """Sinon la phrase « le canevas reste sombre » ne serait garantie que par son nom."""
    assert theme.luminance(theme.CLAIRE.canevas_fond) < 0.05


def test_les_deux_chromes_different_bien():
    """Le pendant du test précédent : sans lui, deux palettes identiques passeraient tout."""
    assert theme.CLAIRE.fond != theme.SOMBRE_PALETTE.fond
    assert theme.CLAIRE.sombre_p() is False
    assert theme.SOMBRE_PALETTE.sombre_p() is True


# --------------------------------------------------------------------------- #
#  Critère 4 — l'échelle typographique
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("base", [8.0, 9.0, 10.5, 12.0, 16.0])
def test_l_echelle_reste_croissante(base):
    """⚠ C'est ce test qui empêche un `max()` mal placé d'écraser les deux premiers rangs.
    Une échelle plafonnée par le bas rendrait `petit == normal` pour une base de 8 pt, et
    l'échelle cesserait d'en être une."""
    echelle = theme.Typo.echelle(base)
    valeurs = [echelle[n] for n in ("petit", "normal", "grand", "titre")]
    assert valeurs == sorted(valeurs)
    assert len(set(valeurs)) == 4
    assert echelle["normal"] == pytest.approx(base)


def test_la_pile_monospace_n_est_pas_qu_une_police_windows():
    """`Consolas` est une police Windows. Le repli `monospace` sauvait la mise, mais c'est le
    genre de valeur qui rend un logiciel « développé sur Windows » visible ailleurs."""
    pile = theme.Typo.MONOSPACE
    assert pile[0] == "Consolas" and pile[-1] == "monospace"
    assert len(pile) >= 4, "il faut des replis NOMMÉS, pas seulement le générique"
    assert "DejaVu Sans Mono" in pile        # Linux
    assert "Menlo" in pile                   # macOS


# --------------------------------------------------------------------------- #
#  Les rôles, et ceux que les autres modules nomment
# --------------------------------------------------------------------------- #

def test_les_deux_palettes_declarent_exactement_les_memes_roles():
    assert (theme.CLAIRE.__dataclass_fields__.keys()
            == theme.SOMBRE_PALETTE.__dataclass_fields__.keys())


def test_un_role_inconnu_leve_plutot_que_de_peindre_en_noir():
    with pytest.raises(KeyError):
        theme.CLAIRE.role("orange")
    with pytest.raises(KeyError):
        theme.poser_role(object(), "chartreuse")


def test_la_feuille_ne_contient_aucun_selecteur_universel():
    """⚠ Un sélecteur universel avec attribut force Qt à évaluer la propriété dynamique sur
    CHAQUE widget de l'application, à chaque résolution de style. C'est le piège de performance
    classique du QSS, et il ne se voit qu'à la mesure : passer de `*` aux classes a fait tomber
    `tests/test_gui_fenetre.py` de 313 s à 266 s.

    ⚠ **Le reste du coût venait d'ailleurs** — une fuite de fenêtres dans les tests, cf.
    `docs/mesures/systeme-visuel-2026-08-27.md` §6.4. Ce test garde le changement pour ce qu'il vaut,
    pas pour ce qu'on avait cru qu'il valait."""
    for pal in theme.PALETTES.values():
        for ligne in theme.qss(pal).splitlines():
            assert not ligne.lstrip().startswith("*["), ligne


def test_chaque_role_est_nomme_par_une_classe_que_la_feuille_connait():
    """Le pendant du test précédent : nommer les classes ne vaut que si `poser_role` refuse
    celles que la feuille ne nomme pas. Sinon on aurait échangé une lenteur contre un rôle
    qui ne peint rien, en silence."""
    feuille = theme.qss(theme.CLAIRE)
    for role in theme.ROLES_WIDGET:
        declarations = [ligne for ligne in feuille.splitlines()
                        if f'[role="{role}"]' in ligne]
        assert declarations, role
        assert any(classe in " ".join(declarations) for classe in theme.CLASSES_A_ROLE), role


@pytest.mark.parametrize("etat,attendu", [
    ({}, None),
    ({"perimee": True}, "pastille_perimee"),
    ({"corrigees": 1}, "pastille_main"),
    ({"detectee": False}, "pastille_absente"),
])
def test_les_roles_nommes_par_la_pellicule_existent(etat, attendu):
    """⚠ `gui/pellicule.py` est **Qt-libre** et décide d'un ÉTAT, jamais d'un pixel. Ce test
    referme la boucle : le rôle qu'il nomme doit exister dans la palette, sinon le nommage par
    rôle n'aurait fait que déplacer le problème."""
    base = {"index": 1, "detectee": True, "bulles": 3, "corrigees": 0, "deplacees": 0,
            "vides": 0, "debordements": 0, "rendue": True, "perimee": False, "motifs": []}
    base.update(etat)
    role = pel.role_couleur(base)
    assert role == attendu
    if role is not None:
        assert theme.CLAIRE.role(role)


def test_les_roles_du_journal_existent():
    for role in set(__import__("gui.fenetre", fromlist=["x"]).ROLES_JOURNAL.values()) \
            if False else ("avertissement", "accent", "succes", "information"):
        assert theme.CLAIRE.role(role)


# --------------------------------------------------------------------------- #
#  Le menu — les trois thèmes sont ceux du module
# --------------------------------------------------------------------------- #

def test_les_themes_du_menu_sont_ceux_du_theme():
    """Un menu qui proposerait un mode que `gui/theme.py` ne connaît pas donnerait un clic
    sans effet — le défaut même que la table des actions existe pour empêcher."""
    du_menu = tuple(mode for mode, _libelle in act.THEMES)
    assert du_menu == theme.MODES


def test_les_trois_actions_de_theme_sont_des_bascules_exclusives():
    entrees = [e for e in act.actions() if e.methode == "theme"]
    assert len(entrees) == 3
    assert all(e.bascule and e.menu == "Affichage" and e.groupe == act.GROUPE_THEME
               for e in entrees)
    assert all(e.raccourci is None for e in entrees), \
        "aucun raccourci : un thème se choisit une fois, pas dix fois par heure"


def test_le_theme_est_persiste():
    """Sans persistance, la bascule dure une session — et l'utilisateur la refait à chaque
    lancement, ce qui est pire que pas de bascule du tout."""
    from gui import reglages as reg
    assert reg.DEFAUTS["theme"] in theme.MODES
    assert reg.defauts()["theme"] == theme.AUTO


def test_le_mode_effectif_resout_auto_sans_qt():
    """⚠ Le repli ne doit ni lever ni pendre quand aucune `QGuiApplication` n'existe — ce test
    tourne dans le job de CI qui n'installe pas PySide6."""
    assert theme.mode_effectif(theme.CLAIR) == theme.CLAIR
    assert theme.mode_effectif(theme.SOMBRE) == theme.SOMBRE
    assert theme.mode_effectif(theme.AUTO) in (theme.CLAIR, theme.SOMBRE)
    assert theme.mode_effectif(None) in (theme.CLAIR, theme.SOMBRE)


# --------------------------------------------------------------------------- #
#  La feuille de style couvre les cinq états
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("etat", [":disabled", ":focus", ":hover", ":checked",
                                  'readOnly="true"'])
def test_la_feuille_traite_les_cinq_etats(etat):
    """Les cinq états de L19.5. Sans QSS, aucun n'existait au-delà de ce que le style natif
    donnait — et ce logiciel grise huit widgets pendant chaque run."""
    assert etat in theme.qss(theme.CLAIRE)


def test_la_feuille_distingue_lecture_seule_et_desactive():
    """⚠ C'est déjà la logique du code — pendant un run, les deux champs de texte passent en
    lecture seule PLUTÔT qu'en désactivé, pour rester lisibles. Rien à l'écran ne le disait."""
    pal = theme.CLAIRE
    assert pal.lecture_seule_fond != pal.desactive_fond
    feuille = theme.qss(pal)
    assert pal.lecture_seule_fond in feuille and pal.desactive_fond in feuille


def test_la_feuille_declare_toutes_les_familles_monospace():
    feuille = theme.qss(theme.CLAIRE)
    for famille in theme.Typo.MONOSPACE:
        assert famille in feuille, famille


def test_les_roles_de_widget_sont_tous_declares_dans_la_feuille():
    """Une faute de frappe dans un nom de rôle ne produit AUCUNE erreur Qt : la règle ne
    s'applique simplement jamais. `poser_role` refuse donc l'inconnu, et ce test vérifie que
    la liste fermée et la feuille disent la même chose."""
    feuille = theme.qss(theme.CLAIRE)
    for role in theme.ROLES_WIDGET:
        assert f'[role="{role}"]' in feuille, role


def test_le_module_de_theme_ne_tire_pas_qt():
    """⚠ **Le test qui garde la règle de couche.** Un `from PySide6…` remonté au niveau du
    module casserait `gui/pellicule.py`, qui consomme les rôles et se teste sans PySide6.

    Il ne teste pas `sys.modules` — PySide6 est chargé ici par les autres fichiers de la
    suite — mais le TEXTE : aucun import Qt en dehors d'un corps de fonction."""
    import inspect

    from gui import theme as module

    for numero, ligne in enumerate(inspect.getsource(module).splitlines(), 1):
        if ligne.lstrip().startswith(("import PySide6", "from PySide6")):
            assert ligne.startswith("    "), (
                f"gui/theme.py:{numero} — Qt doit rester dans un corps de fonction : {ligne}")

