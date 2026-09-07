# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le système visuel, **la moitié qui demande Qt** — `PLAN-19`, critères 2, 4, 6 et 7.

## Pourquoi un second fichier

`tests/test_gui_theme.py` porte tout ce qui se vérifie en Python nu : contrastes, échelle
typographique, balayage des littéraux, table des rôles. Il **n'importe pas PySide6**, parce
que le job de CI qui ne l'installe pas doit exécuter ces garde-fous — c'est ce job qui tient
la règle de couche de `gui/__init__.py`.

⚠ Un `pytest.importorskip` posé au milieu d'un seul fichier n'aurait pas suffi : il saute le
MODULE entier, pas la moitié qui suit. La séparation en deux fichiers est ce qui rend la
promesse vérifiable au lieu de la rendre plausible.

Ici : le style `Fusion` réellement posé, l'échelle dérivée de `QApplication.font()`, les douze
icônes rendues, les noms accessibles, l'ordre de tabulation et le périmètre du clavier.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

from PySide6.QtWidgets import QApplication, QLabel, QWidget                  # noqa: E402

from gui import icones as ico                                               # noqa: E402
from gui import theme                                                       # noqa: E402
from gui.editeur import PanneauEditeur                                      # noqa: E402
from gui.lanceur import PanneauLanceur                                      # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_appliquer_pose_fusion_et_la_palette(qt_app):
    """`Fusion` est le PRÉREQUIS : `windowsvista` ignore une grande partie du QSS et ne
    respecte pas une `QPalette`. C'est pour ça que les douze feuilles d'avant étaient inline."""
    jeu = theme.appliquer(qt_app, theme.SOMBRE)
    assert jeu.mode == theme.SOMBRE
    # ⚠ `app.style()` rend un `QStyleSheetStyle` — un PROXY — dès qu'une feuille est posée,
    # et `name()` comme `objectName()` y sont vides. Le style posé est donc lu sur le jeu,
    # qui le mémorise ; que « Fusion » soit un style RÉEL est vérifié séparément.
    from PySide6.QtWidgets import QStyleFactory
    assert jeu.style == theme.STYLE
    assert theme.STYLE in QStyleFactory.keys()
    assert qt_app.styleSheet()
    from PySide6.QtGui import QPalette
    fond = qt_app.palette().color(QPalette.ColorRole.Window).name()
    assert fond == theme.SOMBRE_PALETTE.fond
    theme.appliquer(qt_app, theme.CLAIR)
    assert theme.couleur("fond") == theme.CLAIRE.fond


def test_appliquer_repose_la_feuille_meme_quand_le_mode_ne_change_pas(qt_app):
    """⚠ **Le test de la régression du lot.** `appliquer` saute le travail quand la feuille en
    place est déjà la bonne — c'est ce qui rend une bascule inutile gratuite. Mais un
    appelant qui déciderait de sauter sur l'égalité des MODES sauterait aussi le premier
    appel, celui où rien n'a encore été posé.

    Un `mode` égal ne veut pas dire « déjà appliqué » ; une feuille égale, si. Et c'est
    `appliquer` qui doit en juger, parce que lui seul voit la feuille."""
    theme.appliquer(qt_app, theme.CLAIR)
    qt_app.setStyleSheet("")                 # quelqu'un a tout effacé — ou rien n'a été posé
    theme.appliquer(qt_app, theme.CLAIR)     # MÊME mode
    assert qt_app.styleSheet(), "la feuille doit être reposée, le mode ne prouve rien"
    assert '[role="journal"]' in qt_app.styleSheet()


def test_appliquer_ne_repose_pas_une_feuille_identique(qt_app):
    """L'autre moitié : reposer une feuille identique restyle tous les widgets vivants de
    l'application. Cinq secondes pour deux bascules qui ne changent rien, mesuré."""
    theme.appliquer(qt_app, theme.CLAIR)
    feuille = qt_app.styleSheet()
    marque = "/* marque de test */"
    qt_app.setStyleSheet(feuille)            # identique : `appliquer` doit s'abstenir
    appels = []
    ancien_setter = qt_app.setStyleSheet
    try:
        qt_app.setStyleSheet = lambda f: (appels.append(f), ancien_setter(f))[1]
        theme.appliquer(qt_app, theme.CLAIR)
        assert appels == [], "une feuille identique ne se repose pas"
    finally:
        del qt_app.setStyleSheet
    assert marque not in qt_app.styleSheet()


def test_l_echelle_appliquee_derive_de_la_police_de_l_application(qt_app):
    """Critère 4 : le 1× vient de `QApplication.font()`, donc du réglage système."""
    from PySide6.QtGui import QFont
    ancienne = qt_app.font()
    try:
        fonte = QFont(ancienne)
        fonte.setPointSizeF(14.0)
        qt_app.setFont(fonte)
        jeu = theme.appliquer(qt_app, theme.CLAIR)
        assert jeu.corps["normal"] == pytest.approx(14.0)
        assert jeu.corps["petit"] < 14.0 < jeu.corps["titre"]
    finally:
        qt_app.setFont(ancienne)
        theme.appliquer(qt_app, theme.CLAIR)


def test_poser_role_refuse_une_classe_que_la_feuille_ne_nomme_pas(qt_app):
    """⚠ Une règle QSS qui ne s'applique pas est SILENCIEUSE. Poser « faible » sur un
    `QPushButton` ne lèverait rien et ne peindrait rien — le pire des deux mondes."""
    from PySide6.QtWidgets import QPushButton

    with pytest.raises(TypeError):
        theme.poser_role(QPushButton("x"), "faible")


def test_poser_role_survit_a_un_widget_deja_construit(qt_app):
    """⚠ Qt ne réévalue PAS une feuille quand une propriété dynamique change. Sans
    `unpolish`/`polish`, poser un rôle après construction n'aurait aucun effet — le piège
    classique des propriétés dynamiques en QSS."""
    etiquette = QLabel("x")
    theme.poser_role(etiquette, "faible")
    assert etiquette.property("role") == "faible"


# --------------------------------------------------------------------------- #
#  Les icônes
# --------------------------------------------------------------------------- #

def test_le_compte_d_icones_est_celui_qui_est_justifie():
    """⚠ « Ne dessinez pas trente icônes » : les cinq outils, supprimer, annuler, refaire,
    enregistrer, zoom ±, ajuster. Une icône médiocre sur une action rare nuit plus qu'un
    libellé clair.

    ⚠ **Le compte est passé de 12 à 22 au lot 31 (2026-09-04), et pas par goût.** Le mode
    COMPACT de la nav latérale (641-1007 px) n'affiche QUE l'icône : une destination sans
    icône y devient un carré vide. Les dix ajoutées sont les neuf destinations plus le bouton
    de menu du mode minimal — et ce test les compte pour que la trentième, elle, demande
    encore une justification."""
    assert len(ico.noms()) == 22
    from gui import destinations as dest
    manquantes = [d.icone for d in dest.destinations() if d.icone not in ico.noms()]
    assert manquantes == [], f"destination(s) sans icône : {manquantes}"


def test_chaque_icone_declare_currentcolor():
    """Une icône qui ne suit pas le thème est pire qu'un libellé texte : elle devient un carré
    noir sur fond sombre."""
    for nom in ico.noms():
        assert "currentColor" in ico.svg(nom), nom


def test_la_teinte_est_substituee_avant_le_rendu():
    rendu = ico.svg("annuler", "#123456")
    assert "#123456" in rendu and "currentColor" not in rendu


def test_une_icone_inconnue_leve():
    with pytest.raises(KeyError):
        ico.svg("licorne")


def test_les_icones_se_rendent_et_se_mettent_en_cache(qt_app):
    theme.appliquer(qt_app, theme.CLAIR)
    ico.oublier()
    premiere = ico.pixmap("ajuster", "#000000", 16)
    assert not premiere.isNull() and premiere.width() == 16
    assert ico.pixmap("ajuster", "#000000", 16) is premiere
    ico.oublier()
    assert ico.pixmap("ajuster", "#000000", 16) is not premiere


def test_le_logo_se_rend(qt_app):
    assert not ico.logo(64).isNull()


def test_le_logo_vient_du_fichier_livre_et_porte_ses_sept_tailles(qt_app):
    """⚠ Ce test existe parce que le SVG de secours rendrait ce même `logo()` **non nul**.

    Sans lui, supprimer ou déplacer `templates/icone/angelith.ico` laisserait toute la suite au
    vert, et l'utilisateur verrait deux identités : celle du `.exe` dans le menu Démarrer,
    celle du secours dans la barre des tâches. Ce qui distingue les deux chemins n'est pas la
    couleur — c'est le nombre de résolutions : le SVG est rendu à une taille, le `.ico` en
    porte sept."""
    from core import installation

    fichier = installation.ressource(*ico.ICONE_LIVREE)
    assert fichier.is_file(), f"icône livrée introuvable : {fichier}"

    tailles = {(t.width(), t.height()) for t in ico.logo().availableSizes()}
    assert (16, 16) in tailles, "le 16 px est celui de la barre des tâches, il ne se déduit pas"
    assert (256, 256) in tailles
    assert len(tailles) >= 7


def test_la_table_du_journal_est_bien_celle_ci():
    """Le pendant Qt de `test_les_quatre_niveaux_du_journal_ont_un_role` : deux tables qui
    divergeraient laisseraient un niveau repeint à la mauvaise couleur, en silence."""
    from gui.fenetre import PREFIXES_JOURNAL, ROLES_JOURNAL
    assert set(ROLES_JOURNAL.values()) == {"avertissement", "accent", "succes", "information"}
    assert set(ROLES_JOURNAL) == set(PREFIXES_JOURNAL)
    # ⚠ Les préfixes doivent rester DISTINCTS : c'est par eux que `_repeindre_journal`
    # retrouve le niveau d'une ligne déjà écrite, à la bascule de thème.
    marquants = [p for p in PREFIXES_JOURNAL.values() if p.strip()]
    assert len(set(marquants)) == len(marquants)


# --------------------------------------------------------------------------- #
#  Critère 6 — noms accessibles, ordre de tabulation, focus
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def panneau(qt_app):
    theme.appliquer(qt_app, theme.CLAIR)
    return PanneauEditeur()


#: Les widgets dont le libellé visible n'est **pas un mot** : `🔒`, `−`, `+`, `%`, et les
#: listes qui n'ont aucun `QLabel` associé. Ce sont exactement ceux qu'un lecteur d'écran
#: annonce comme « bouton » et rien d'autre.
SANS_LIBELLE_LISIBLE = (
    "bouton_garder_zoom", "bouton_zoom_moins", "bouton_zoom_plus", "etiquette_zoom",
    "liste_planches", "liste_bulles", "liste_resultats",
    "choix_filtre", "champ_recherche", "champ_remplacement",
    "champ_ocr", "champ_trad", "champ_corps", "choix_etape",
)


@pytest.mark.parametrize("nom", SANS_LIBELLE_LISIBLE)
def test_chaque_widget_sans_libelle_lisible_a_un_nom_accessible(nom, panneau):
    """**Critère 6.** Une heure de travail, et c'est ce qui décide qu'un lecteur d'écran est
    utilisable ou pas. Il y en avait **zéro** avant ce lot."""
    widget = getattr(panneau, nom)
    assert widget.accessibleName(), nom
    assert len(widget.accessibleName()) > 2, nom


def test_les_cinq_outils_portent_leur_nom_accessible(panneau):
    for bouton in panneau._boutons_modes.values():
        assert bouton.accessibleName() == bouton.text()


def test_l_ordre_de_tabulation_est_explicite_et_ne_nomme_que_des_widgets(panneau):
    """⚠ L'ordre implicite traversait les **quatorze boutons de la barre du canevas** entre la
    pellicule et l'inspecteur. Passer du champ de réplique au bouton « Retraduire » demandait
    une dizaine de tabulations, sur le geste le plus répété du logiciel."""
    assert len(PanneauEditeur.PARCOURS) >= 15
    for nom in PanneauEditeur.PARCOURS:
        assert isinstance(getattr(panneau, nom), QWidget), nom
    assert len(set(PanneauEditeur.PARCOURS)) == len(PanneauEditeur.PARCOURS)


def test_le_parcours_va_de_la_replique_a_retraduire_sans_detour(panneau):
    """La mesure du défaut, retournée en critère : trois crans, pas dix."""
    ordre = list(PanneauEditeur.PARCOURS)
    saut = ordre.index("bouton_retraduire") - ordre.index("champ_trad")
    assert 0 < saut <= 6, f"{saut} tabulations entre la réplique et « Retraduire »"


def test_le_parcours_saute_la_barre_de_zoom(panneau):
    """Les trois boutons de zoom ont chacun un raccourci de menu ; les laisser dans le
    parcours revient à faire payer trois tabulations pour un geste qui a `Ctrl+0`."""
    from PySide6.QtCore import Qt
    for nom in ("bouton_zoom_moins", "bouton_zoom_plus", "bouton_ajuster"):
        assert getattr(panneau, nom).focusPolicy() == Qt.NoFocus, nom
    assert not set(PanneauEditeur.PARCOURS) & {"bouton_zoom_moins", "bouton_zoom_plus",
                                               "bouton_ajuster"}


def test_le_lanceur_a_aussi_un_parcours_explicite(qt_app):
    """Critère 6 : **chaque** panneau, pas seulement celui qui allait mal.

    ⚠ `bandeau` n'existe que sur la destination Webtoon, qui porte sa réserve mesurée en tête.
    Les `PARCOURS` du dépôt sont volontairement des ordres DÉCLARÉS et non des inventaires :
    `_poser_parcours` saute ce qui n'existe pas (`hasattr`), et le test fait de même — un ordre
    qui exigerait tous ses widgets interdirait à un panneau d'avoir deux formes."""
    # ⚠ `brique` est OBLIGATOIRE depuis le lot 33 : les paramètres offerts dépendent du
    # panneau (`gui/parametres.py`), donc un panneau sans brique n'a pas de formulaire à
    # construire. Le repli « brique libre » a été retiré — il n'avait aucun appelant.
    lanceur = PanneauLanceur({"chemins": {"sources": "sources", "build": "build"}},
                             brique="manga")
    for nom in PanneauLanceur.PARCOURS:
        if not hasattr(lanceur, nom):
            continue
        assert isinstance(getattr(lanceur, nom), QWidget), nom
    manquants = [n for n in PanneauLanceur.PARCOURS if not hasattr(lanceur, n)]
    assert manquants == ["bandeau", "champ_fenetre_hauteur", "champ_fenetre_recouvrement"],         manquants
    # …et sur la destination Webtoon, les trois EXISTENT : c'est elle qui porte la réserve
    # mesurée et le groupe « Découpage de la bande ».
    from gui.lanceur import RESERVE_WEBTOON
    webtoon = PanneauLanceur({"chemins": {"sources": "sources", "build": "build"}},
                             brique="manga", format_planche="webtoon",
                             reserve=RESERVE_WEBTOON)
    for nom in PanneauLanceur.PARCOURS:
        assert isinstance(getattr(webtoon, nom), QWidget), nom


def test_les_panneaux_du_lot_31_declarent_leur_parcours(qt_app):
    """La nav latérale et les trois destinations neuves, au même standard que les autres.

    « Le critère 6 du `PLAN-19` demande UN ordre explicite PAR PANNEAU, pas un par défaut qui
    se trouve juste » — une nav latérale qui hériterait de l'ordre de construction serait
    exactement ce cas-là."""
    from gui.accueil import PanneauAccueil
    from gui.navigation import PanneauNavigation
    from gui.oeuvres import PanneauOeuvres

    for classe in (PanneauNavigation, PanneauAccueil, PanneauOeuvres):
        assert classe.PARCOURS, classe.__name__
        panneau = classe()
        for nom in classe.PARCOURS:
            if nom in ("cartes", "reprises"):     # des GROUPES, cf. `PanneauAccueil`
                continue
            assert isinstance(getattr(panneau, nom), QWidget), f"{classe.__name__}.{nom}"


def test_l_anneau_de_focus_est_visible():
    """Sans lui, `setTabOrder` et `setAccessibleName` ne servent à rien : on ne sait pas où
    l'on est."""
    feuille = theme.qss(theme.CLAIRE)
    assert ":focus" in feuille
    assert f"2px solid {theme.CLAIRE.focus}" in feuille


# --------------------------------------------------------------------------- #
#  Critère 7 — le clavier déplace et retaille, et NE DESSINE PAS
# --------------------------------------------------------------------------- #

def test_les_cinq_outils_portent_icone_ET_libelle(panneau):
    """⚠ « Redessiner » remet l'OCR et la traduction de la bulle à zéro. Une icône seule ne
    dira jamais cela."""
    from PySide6.QtCore import Qt
    for bouton in panneau._boutons_modes.values():
        assert bouton.toolButtonStyle() == Qt.ToolButtonTextBesideIcon
        assert not bouton.icon().isNull()
        assert bouton.text()


def test_les_gestes_clavier_sont_dans_la_boite_des_raccourcis():
    """⚠ Un geste qu'on ne sait pas possible n'existe pas. La boîte « Raccourcis clavier » est
    le seul endroit qui annonce les gestes qui n'ont pas d'entrée de menu — et elle doit dire
    aussi ce que le clavier NE fait pas, sinon on cherchera longtemps comment tracer."""
    from gui.dialogues import RACCOURCIS_LOCAUX

    table = {cle: texte for cle, texte in RACCOURCIS_LOCAUX}
    fleches = [cle for cle in table if "←" in cle]
    assert len(fleches) == 2, "le déplacement ET le retaillage doivent être annoncés"
    tout = " ".join(table[c] for c in fleches).lower()
    assert "déplacer" in tout and "retailler" in tout
    assert "souris" in tout, "le périmètre doit être écrit, pas deviné"


def test_le_panneau_declare_les_deux_pas_de_clavier():
    assert PanneauEditeur.PAS_FIN < PanneauEditeur.PAS_LARGE
    # Le dépôt doit être plus lent que la répétition automatique du clavier (~30 ms), sans
    # quoi une flèche tenue enfoncée écrirait vingt fois sur le disque.
    assert PanneauEditeur.DELAI_DEPOT_MS >= 300
