# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La page Diagnostic (`gui/diagnostic.py`) — avec Qt, sans écran, sans réseau.

Ce fichier ne re-teste pas les décisions : elles sont dans `gui/vue_diagnostic.py` et
`tests/test_gui_vue_diagnostic.py`, qui tournent sans PySide6. Ici on vérifie ce que seul Qt
peut dire : que les widgets apparaissent, que les boutons émettent, et surtout **que la page
ne fait rien qu'on ne lui a pas demandé**.

⚠ `QT_QPA_PLATFORM=offscreen` est posé avant toute construction de `QApplication`, comme dans
le reste de la suite d'interface.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                          # noqa: E402

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from core import diagnostic as diag                    # noqa: E402
from gui.diagnostic import PanneauDiagnostic           # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def panneau(qt_app):
    p = PanneauDiagnostic()
    yield p
    p.deleteLater()


def _v(identifiant, brique, gravite, **kw):
    return diag.Verdict(identifiant, brique, gravite,
                        constat=kw.pop("constat", identifiant), **kw)


def _sections(*verdicts):
    return (diag.Section("— test —", tuple(verdicts)),)


# --------------------------------------------------------------------------- #
#  Ce que la page ne fait PAS
# --------------------------------------------------------------------------- #

def test_la_page_n_inspecte_rien_a_la_construction(panneau):
    """⚠ Elle s'ouvre en disant qu'aucun diagnostic n'a tourné, ce qui est vrai. Un diagnostic
    complet interroge le serveur de modèles — 12,1 s sur un serveur arrêté, mesuré le
    2026-09-06 — et le lancer au premier affichage rejouerait le défaut du `PLAN-31`."""
    assert panneau.sections() == ()
    assert "Aucun diagnostic" in panneau.resume.text()


def test_le_bouton_dit_ce_qu_il_coute_avant_le_clic(panneau):
    assert "12,1 s" in panneau.bouton_lancer.toolTip()


def test_lancer_emet_le_signal_avec_le_choix_de_reseau(panneau):
    recus: list[bool] = []
    panneau.demande_diagnostic.connect(recus.append)
    panneau.case_reseau.setChecked(False)
    panneau.bouton_lancer.click()
    panneau.case_reseau.setChecked(True)
    panneau.bouton_lancer.click()
    assert recus == [False, True]


def test_marquer_en_cours_dit_ce_qui_se_passe(panneau):
    """⚠ Il n'est pas seulement grisé : un bouton grisé sans texte ne dit pas s'il travaille ou
    s'il est interdit."""
    panneau.marquer_en_cours(True)
    assert panneau.bouton_lancer.isEnabled() is False
    assert "en cours" in panneau.bouton_lancer.text()
    panneau.marquer_en_cours(False)
    assert panneau.bouton_lancer.isEnabled() is True


# --------------------------------------------------------------------------- #
#  Ce qu'elle affiche
# --------------------------------------------------------------------------- #

def _textes(panneau) -> str:
    from PySide6.QtWidgets import QLabel
    return "\n".join(w.text() for w in panneau.corps.findChildren(QLabel))


def test_chaque_verdict_montre_constat_consequence_et_geste(panneau):
    """⚠ **Critère 4 du `PLAN-36`**, vérifié à l'écran cette fois."""
    panneau.poser_sections(_sections(_v(
        "pandoc", diag.LN, diag.BLOQUANT, constat="Pandoc introuvable dans le PATH",
        consequence="les sorties DOCX ne seront pas produites",
        geste="installe Pandoc — https://pandoc.org/installing.html")))
    texte = _textes(panneau)
    assert "Pandoc introuvable dans le PATH" in texte
    assert "les sorties DOCX ne seront pas produites" in texte
    assert "pandoc.org/installing.html" in texte


def test_les_conformes_sont_comptes_et_non_affiches(panneau):
    panneau.poser_sections(_sections(*[_v(f"c{i}", diag.LN, diag.CONFORME)
                                       for i in range(4)]))
    texte = _textes(panneau)
    assert "4 points vérifiés" in texte
    assert "c0" not in texte


def test_la_case_montrer_les_conformes_les_fait_apparaitre(panneau):
    panneau.poser_sections(_sections(_v("c0", diag.LN, diag.CONFORME)))
    assert "c0" not in _textes(panneau)
    panneau.case_conformes.setChecked(True)
    assert "c0" in _textes(panneau)


def test_reposer_des_sections_ne_laisse_rien_de_l_affichage_precedent(panneau):
    panneau.poser_sections(_sections(_v("premier", diag.LN, diag.BLOQUANT, geste="g")))
    panneau.poser_sections(_sections(_v("second", diag.MANGA, diag.BLOQUANT, geste="g")))
    texte = _textes(panneau)
    assert "second" in texte
    assert "premier" not in texte


# --------------------------------------------------------------------------- #
#  Les boutons de réparation
# --------------------------------------------------------------------------- #

def _boutons(panneau) -> list[str]:
    return [b.text() for b in panneau.corps.findChildren(QPushButton)]


def test_un_bouton_apparait_devant_un_poids_recuperable(panneau):
    panneau.poser_sections(_sections(_v(
        "poids_detection", diag.MANGA, diag.BLOQUANT, geste="g", reparable=True,
        reparation="poids_detection")))
    boutons = _boutons(panneau)
    assert boutons, "aucun bouton devant un poids récupérable"
    assert "Mo" in boutons[0], "la taille est annoncée avant le clic"


def test_aucun_bouton_devant_un_logiciel_systeme(panneau):
    """⚠ Angelith n'installe aucun logiciel système : Pandoc n'a pas de bouton."""
    panneau.poser_sections(_sections(_v(
        "pandoc", diag.LN, diag.BLOQUANT, geste="installe Pandoc", reparable=True,
        reparation="pandoc")))
    assert _boutons(panneau) == []


def test_le_bouton_montre_la_licence_dans_son_infobulle(panneau):
    """⚠ « Une licence montrée après le téléchargement ne sert à rien. »"""
    panneau.poser_sections(_sections(_v(
        "poids_texte", diag.MANGA, diag.BLOQUANT, geste="g", reparable=True,
        reparation="poids_texte")))
    bouton = panneau.corps.findChildren(QPushButton)[0]
    assert "Licence :" in bouton.toolTip()
    assert "Manga109" in bouton.toolTip()


def test_le_bouton_emet_l_identifiant_de_la_reparation(panneau):
    panneau.poser_sections(_sections(_v(
        "poids_detection", diag.MANGA, diag.BLOQUANT, geste="g", reparable=True,
        reparation="poids_detection")))
    recus: list[str] = []
    panneau.demande_reparation.connect(recus.append)
    panneau.corps.findChildren(QPushButton)[0].click()
    assert recus == ["poids_detection"]


# --------------------------------------------------------------------------- #
#  L'accessibilité — le symbole double la couleur
# --------------------------------------------------------------------------- #

def test_le_symbole_double_la_couleur(panneau):
    """⚠ Un état annoncé par la seule couleur est un état que 8 % des hommes ne lisent pas
    (`PLAN-19`, critère d'accessibilité)."""
    panneau.poser_sections(_sections(_v("x", diag.LN, diag.BLOQUANT, geste="g"),
                                     _v("y", diag.LN, diag.DEGRADE, geste="g")))
    texte = _textes(panneau)
    assert diag.SYMBOLES[diag.BLOQUANT] in texte
    assert diag.SYMBOLES[diag.DEGRADE] in texte


def test_le_nom_accessible_dit_la_gravite_en_toutes_lettres(panneau):
    panneau.poser_sections(_sections(_v("x", diag.LN, diag.BLOQUANT, geste="g")))
    from gui.diagnostic import CarteVerdict
    carte = panneau.corps.findChildren(CarteVerdict)[0]
    assert diag.PHRASES_GRAVITE[diag.BLOQUANT] in carte.constat.accessibleName()


# --------------------------------------------------------------------------- #
#  L36.3 — l'accueil mène au diagnostic, sans y aller tout seul
# --------------------------------------------------------------------------- #

def test_l_accueil_ne_montre_le_lien_que_si_quelque_chose_manque(qt_app):
    """⚠ Un bouton toujours visible devient du décor. Celui-ci apparaît quand une sonde vient
    de dire « absent », et **pas** sur `INCONNU` : « je n'ai pas encore regardé » n'est pas
    « c'est cassé »."""
    from gui import sondes as snd
    from gui.accueil import PanneauAccueil

    # ⚠ `isHidden()` et non `isVisible()` : le panneau n'est jamais montré dans un test, donc
    # `isVisible()` répond « non » pour toute la descendance, quoi qu'on ait demandé. C'est
    # l'état DEMANDÉ qu'on mesure ici, pas la présence à l'écran.
    accueil = PanneauAccueil()
    try:
        assert accueil.bouton_diagnostic.isHidden() is True
        accueil.poser_sondes(snd.inconnues())
        assert accueil.bouton_diagnostic.isHidden() is True, "« inconnu » n'est pas un manque"
        accueil.poser_sondes((snd.Sonde("Pandoc", snd.INJOIGNABLE, "absent du PATH"),))
        assert accueil.bouton_diagnostic.isHidden() is False
        accueil.poser_sondes((snd.Sonde("Pandoc", snd.JOIGNABLE, "/usr/bin/pandoc"),))
        assert accueil.bouton_diagnostic.isHidden() is True
    finally:
        accueil.deleteLater()


def test_le_lien_de_l_accueil_demande_la_destination_diagnostic(qt_app):
    from gui import sondes as snd
    from gui.accueil import PanneauAccueil

    accueil = PanneauAccueil()
    try:
        accueil.poser_sondes((snd.Sonde("Pandoc", snd.INJOIGNABLE, "absent"),))
        recus: list[str] = []
        accueil.demande_destination.connect(recus.append)
        accueil.bouton_diagnostic.click()
        assert recus == ["diagnostic"]
    finally:
        accueil.deleteLater()
