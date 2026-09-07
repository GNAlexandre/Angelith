# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le panneau de la destination « Œuvres » — `gui/oeuvres.py` (lot 34, L34.2).

Les **décisions** (colonnes, filtres, pastilles, légende) sont testées sans écran dans
`tests/test_gui_vue_oeuvres.py`. Ici on vérifie ce qui a besoin de Qt : que le panneau se
construise, se remplisse, grise ce qu'il doit griser, et **demande** plutôt qu'il n'agisse.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6",
                    reason="interface graphique : pip install -r requirements-gui.txt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import bibliotheque as biblio                                                 # noqa: E402
from gui import oeuvres as oe                                                 # noqa: E402
from gui import vue_oeuvres as vue                                            # noqa: E402
from PySide6.QtWidgets import QApplication                                    # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def _corpus(tmp_path: Path) -> tuple[dict, list]:
    config = {"chemins": {"sources": str(tmp_path / "sources"),
                          "build": str(tmp_path / "build"),
                          "glossaire_fichier": "glossaire.yaml"},
              "langues": {"dossiers": {"ENG": "en", "JAP": "jp"}}}
    for i in range(1, 3):
        chemin = tmp_path / "sources" / "Manga A" / "Vol.1" / "manga" / f"{i:03d}.png"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"\0")
    livre = tmp_path / "sources" / "Roman B" / "Vol.1" / "ENG" / "livre.pdf"
    livre.parent.mkdir(parents=True, exist_ok=True)
    livre.write_bytes(b"\0")
    glo = tmp_path / "sources" / "Manga A" / "glossaire.yaml"
    glo.write_text("personnages:\n- nom: X\n", encoding="utf-8")
    return config, biblio.Inventaire(config).oeuvres(paralleles=1)


def test_le_panneau_se_construit_vide_et_le_dit(qt_app, tmp_path):
    panneau = oe.PanneauOeuvres()
    panneau.poser_racine(tmp_path / "sources")
    assert str(tmp_path / "sources") in panneau.chemin.text()
    assert "Lecture" in panneau.etat.text()
    assert panneau.arbre.topLevelItemCount() == 0
    panneau.deleteLater()


def test_le_panneau_montre_les_oeuvres_et_leurs_tomes(qt_app, tmp_path):
    _config, oeuvres = _corpus(tmp_path)
    panneau = oe.PanneauOeuvres()
    panneau.poser_oeuvres(oeuvres)
    assert panneau.arbre.topLevelItemCount() == 2
    titres = {panneau.arbre.topLevelItem(i).text(0) for i in range(2)}
    assert titres == {"Manga A", "Roman B"}
    assert "2 tome(s) affiché(s) sur 2" in panneau.etat.text()
    panneau.deleteLater()


def test_le_filtre_de_brique_reduit_la_liste(qt_app, tmp_path):
    _config, oeuvres = _corpus(tmp_path)
    panneau = oe.PanneauOeuvres()
    panneau.poser_oeuvres(oeuvres)
    panneau.choix_brique.setCurrentIndex(
        [c for c, _ in vue.FILTRES_BRIQUE].index(biblio.LN))
    assert panneau.arbre.topLevelItemCount() == 1
    assert panneau.arbre.topLevelItem(0).text(0) == "Roman B"
    panneau.deleteLater()


def test_retoucher_est_grise_sur_un_roman(qt_app, tmp_path):
    """⚠ La retouche édite des PLANCHES. La proposer sur un roman serait promettre un écran
    qui s'ouvrirait vide."""
    _config, oeuvres = _corpus(tmp_path)
    panneau = oe.PanneauOeuvres()
    panneau.poser_oeuvres(oeuvres)

    def _selectionner(projet, tome):
        for i in range(panneau.arbre.topLevelItemCount()):
            parent = panneau.arbre.topLevelItem(i)
            if parent.text(0) != projet:
                continue
            for j in range(parent.childCount()):
                if parent.child(j).text(0) == tome:
                    panneau.arbre.setCurrentItem(parent.child(j))
                    return

    _selectionner("Manga A", "Vol.1")
    assert panneau.bouton_retoucher.isEnabled()
    assert panneau.bouton_glossaire.isEnabled()
    _selectionner("Roman B", "Vol.1")
    assert not panneau.bouton_retoucher.isEnabled()
    # Pas de glossaire pour « Roman B » : le bouton ne promet rien qu'il ne puisse tenir.
    assert not panneau.bouton_glossaire.isEnabled()
    panneau.deleteLater()


def test_lancer_emet_un_signal_et_ne_lance_rien(qt_app, tmp_path):
    """⚠ Le panneau **demande**, la fenêtre décide. Aucun `process_volume` n'est joignable
    depuis ici."""
    _config, oeuvres = _corpus(tmp_path)
    panneau = oe.PanneauOeuvres()
    panneau.poser_oeuvres(oeuvres)
    recu = []
    panneau.demande_lancement.connect(lambda p, t, b: recu.append((p, t, b)))
    parent = panneau.arbre.topLevelItem(0)
    panneau.arbre.setCurrentItem(parent.child(0))
    panneau.bouton_lancer.click()
    assert recu == [("Manga A", "Vol.1", biblio.MANGA)]
    panneau.deleteLater()


def test_la_legende_est_depliable_et_toujours_lisible_en_pied(qt_app, tmp_path):
    _config, oeuvres = _corpus(tmp_path)
    panneau = oe.PanneauOeuvres()
    panneau.poser_oeuvres(oeuvres)
    assert not panneau.legende.isVisible()
    panneau.case_legende.setChecked(True)
    assert panneau.legende.text() == vue.texte_legende()
    # Et même repliée, la barre d'état la porte : une pastille n'est jamais seule.
    assert "●" in panneau.etat.text()
    panneau.deleteLater()


def test_aucune_colonne_de_vignette(qt_app):
    """⚠ Critère 9. Ce sont des œuvres sous droit d'auteur : une grille de couvertures est la
    capture d'écran qu'on ne pourra jamais montrer."""
    entetes = [nom.lower() for nom, _ in vue.COLONNES]
    assert not any(mot in " ".join(entetes)
                   for mot in ("vignette", "couverture", "aperçu", "miniature"))
    module = Path(__file__).resolve().parents[1] / "gui" / "oeuvres.py"
    source = module.read_text(encoding="utf-8")
    assert "QPixmap" not in source and "QIcon(" not in source


# --------------------------------------------------------------------------- #
#  ⚠ Un bouton grisé DIT ce qu'il attend
#
#  Le module le promettait — « un bouton grisé dit ce qu'il attend » — et ne le tenait pas :
#  l'infobulle était la même, actif ou grisé. Sur une liste vide, six boutons se grisent d'un
#  coup et rien n'explique pourquoi. Le 2026-09-07, le mainteneur a cherché « Importer un tome
#  corrigé… » alors que le bouton était sous ses yeux, grisé faute de sélection.
# --------------------------------------------------------------------------- #

def _panneau(qt_app):
    panneau = oe.PanneauOeuvres()
    panneau.poser_oeuvres([])          # l'état exact d'une installation neuve
    return panneau


def test_sur_une_liste_vide_chaque_bouton_dit_ce_qu_il_attend(qt_app):
    """**Le défaut signalé.** Six boutons grisés sans un mot, c'est une option qu'on croit
    absente."""
    panneau = _panneau(qt_app)
    for nom in oe.PanneauOeuvres.ATTENTES:
        bouton = getattr(panneau, nom)
        assert not bouton.isEnabled(), f"{nom} devrait être grisé sur une liste vide"
        assert bouton.toolTip() == oe.PanneauOeuvres.ATTENTES[nom], nom
    panneau.deleteLater()


def test_l_import_grise_dit_qu_il_attend_un_tome(qt_app):
    """Celui que le mainteneur cherchait : son infobulle nomme la SÉLECTION qui lui manque, et
    la brique qu'il exige."""
    panneau = _panneau(qt_app)
    aide = panneau.bouton_importer.toolTip()
    assert "Sélectionne" in aide
    assert "MANGA" in aide and "WEBTOON" in aide
    panneau.deleteLater()


def test_le_bouton_actif_retrouve_son_infobulle_de_geste(qt_app):
    """⚠ L'infobulle d'origine décrit le geste et son coût — c'est ce qu'un bouton UTILISABLE
    doit annoncer. Sans la mémoire des textes d'origine, la première grisée l'effacerait pour
    de bon, et le bouton actif expliquerait ce qu'il attend alors qu'il n'attend plus rien."""
    panneau = _panneau(qt_app)
    grisee = panneau.bouton_retoucher.toolTip()
    panneau._griser("bouton_retoucher", True, panneau._aides["bouton_retoucher"])
    active = panneau.bouton_retoucher.toolTip()
    assert active != grisee
    assert active not in oe.PanneauOeuvres.ATTENTES.values()
    panneau.deleteLater()


def test_chaque_bouton_grisable_a_son_attente(qt_app):
    """Un bouton ajouté à la rangée sans attente déclarée lèverait un `KeyError` au premier
    clic sur la liste. On l'exige ici plutôt que de le découvrir à l'écran."""
    panneau = _panneau(qt_app)
    for nom in oe.PanneauOeuvres.ATTENTES:
        assert hasattr(panneau, nom), nom
    assert set(oe.PanneauOeuvres.ATTENTES) <= set(oe.PanneauOeuvres.PARCOURS)
    panneau.deleteLater()
