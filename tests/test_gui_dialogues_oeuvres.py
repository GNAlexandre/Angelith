# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les trois boîtes du lot 34 — dépôt guidé, export de glossaire, sorties d'un tome.

Elles ne **décident** de rien : `gui/depot_guide.py`, `core/glossary_export.py` et
`gui/sorties.py` portent les règles, et sont testés sans écran ailleurs. Ce fichier vérifie ce
qui ne se teste que monté : que la boîte montre ce que le module a rendu, qu'elle grise son
bouton quand rien n'est faisable, et qu'elle **n'écrit rien** avant qu'on valide.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("PySide6",
                    reason="interface graphique : pip install -r requirements-gui.txt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import bibliotheque as biblio                                                 # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox                  # noqa: E402

from gui import depot_guide as dg                                             # noqa: E402
from gui import sorties as so                                                 # noqa: E402
from gui.dialogues import (DialogueDepotGuide, DialogueExportGlossaire,       # noqa: E402
                           DialogueSorties)


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def _config(racine: Path) -> dict:
    return {"chemins": {"sources": str(racine / "sources"), "build": str(racine / "build"),
                        "glossaire_fichier": "glossaire.yaml"},
            "langues": {"dossiers": {"ENG": "en", "JAP": "jp"}}}


def _images(dossier: Path, n: int) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (dossier / f"{i:03d}.png").write_bytes(b"\0" * 64)
    return dossier


# --------------------------------------------------------------------------- #
#  Le dépôt guidé
# --------------------------------------------------------------------------- #

def test_le_depot_guide_montre_ce_qui_a_ete_lu_et_ou_ca_va(qt_app, tmp_path):
    source = _images(tmp_path / "Mon Manga - Vol.3", 4)
    boite = DialogueDepotGuide(_config(tmp_path), [source])
    try:
        assert "4 fichier(s)" in boite.resume.text()
        assert boite.champ_projet.text() == "Mon Manga"
        assert boite.champ_tome.text() == "Vol.3"
        assert str(boite.plan().destination.dossier) == boite.cible.text()
        assert "Nouvelle œuvre" in boite.collision.text()
        assert boite.boutons.button(QDialogButtonBox.Ok).isEnabled()
    finally:
        boite.deleteLater()


def test_la_case_deplacer_est_decochee_et_le_dit(qt_app, tmp_path):
    """⚠ Un lâcher qui vide le dossier d'origine est irréversible."""
    source = _images(tmp_path / "M - Vol.1", 2)
    boite = DialogueDepotGuide(_config(tmp_path), [source])
    try:
        assert boite.case_deplacer.isChecked() is False
        assert "irréversible" in boite.case_deplacer.toolTip()
        assert "copié" in boite.annonce.text()
        assert boite.description()["deplacer"] is False
        boite.case_deplacer.setChecked(True)
        assert "DÉPLACÉ" in boite.annonce.text()
        assert boite.description()["deplacer"] is True
    finally:
        boite.deleteLater()


def test_un_cbr_sans_outil_grise_le_bouton_et_dit_pourquoi(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "outil_rar",
                        lambda: dg.OutilRar(False, motif="l'outil externe « unrar » est "
                                                         "introuvable dans le PATH."))
    archive = tmp_path / "Mon Manga - Vol.3.cbr"
    archive.write_bytes(b"Rar!\x1a\x07\x00")
    boite = DialogueDepotGuide(_config(tmp_path), [archive])
    try:
        assert not boite.boutons.button(QDialogButtonBox.Ok).isEnabled()
        assert "unrar" in boite.erreur.text()
    finally:
        boite.deleteLater()


def test_le_depot_guide_n_ecrit_rien(qt_app, tmp_path):
    """La copie part dans le fil de travail, jamais depuis la boîte."""
    source = _images(tmp_path / "M - Vol.1", 2)
    boite = DialogueDepotGuide(_config(tmp_path), [source])
    try:
        assert not (tmp_path / "sources").exists()
        assert boite.plan().destination.dossier.exists() is False
    finally:
        boite.deleteLater()


def test_une_archive_est_listee_sans_etre_extraite(qt_app, tmp_path):
    archive = tmp_path / "Mon Manga - Vol.1.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        for i in range(6):
            zf.writestr(f"p{i}.jpg", b"\0" * 16)
    boite = DialogueDepotGuide(_config(tmp_path), [archive])
    try:
        libelles = [boite.detail.item(i).text() for i in range(boite.detail.count())]
        assert any("6 image(s)" in x for x in libelles)
        assert not (tmp_path / "pages_src").exists()
    finally:
        boite.deleteLater()


# --------------------------------------------------------------------------- #
#  L'export du glossaire
# --------------------------------------------------------------------------- #

@pytest.fixture()
def projet_avec_glossaire(tmp_path):
    config = _config(tmp_path)
    chemin = tmp_path / "sources" / "Mon Œuvre" / "glossaire.yaml"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("personnages:\n- nom: X\n- nom: Y\n", encoding="utf-8")
    return config, chemin


def test_l_export_annonce_la_perte_AVANT_d_ecrire(qt_app, projet_avec_glossaire, tmp_path):
    """⚠ « Exporter en CSV » ne doit pas laisser croire qu'on peut réimporter sans perte."""
    config, _chemin = projet_avec_glossaire
    boite = DialogueExportGlossaire(config, "Mon Œuvre", "Vol.1")
    try:
        assert "2 entrée(s)" in boite.entete.text()
        assert "ARCHIVE" in boite.pertes.text()          # YAML par défaut
        indices = {boite.choix_format.itemData(i): i
                   for i in range(boite.choix_format.count())}
        assert boite.choix_format.itemData(0) == "yaml", "l'archive est proposée en premier"
        boite.choix_format.setCurrentIndex(indices["csv"])
        assert "VUE, PAS ARCHIVE" in boite.pertes.text()
        assert "AUTRES langues cibles" in boite.pertes.text()
        assert not list(tmp_path.glob("*.csv")), "la boîte a écrit avant qu'on valide"
    finally:
        boite.deleteLater()


def test_le_nom_propose_suit_le_format(qt_app, projet_avec_glossaire):
    config, _chemin = projet_avec_glossaire
    boite = DialogueExportGlossaire(config, "Mon Œuvre", "Vol.1")
    try:
        assert boite.champ_destination.text().endswith(".yaml")
        indices = {boite.choix_format.itemData(i): i
                   for i in range(boite.choix_format.count())}
        boite.choix_format.setCurrentIndex(indices["md"])
        assert boite.champ_destination.text().endswith(".md")
    finally:
        boite.deleteLater()


def test_l_export_ecrit_le_fichier_et_laisse_la_source_intacte(qt_app, projet_avec_glossaire,
                                                               tmp_path):
    config, chemin = projet_avec_glossaire
    avant = chemin.read_bytes()
    boite = DialogueExportGlossaire(config, "Mon Œuvre", "Vol.1")
    try:
        boite.champ_destination.setText(str(tmp_path / "sortie.yaml"))
        boite._exporter()
        assert boite.ecrit.is_file()
        assert "Mon Œuvre" in boite.ecrit.read_text(encoding="utf-8")
        assert chemin.read_bytes() == avant
    finally:
        boite.deleteLater()


# --------------------------------------------------------------------------- #
#  Les sorties d'un tome
# --------------------------------------------------------------------------- #

def test_les_sorties_montrent_le_geste_et_le_cout_sans_pouvoir_le_lancer(qt_app, tmp_path):
    """⚠ Le seul bouton actif est « Ouvrir », et il émet un signal — la fenêtre ouvre."""
    config = _config(tmp_path)
    _images(tmp_path / "sources" / "P" / "Vol.1" / "manga", 2)
    build = tmp_path / "build" / "P" / "Vol.1" / "manga"
    for i in (1, 2):
        chemin = build / "pages_out" / f"page_{i:04d}.png"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"\0" * 128)
    info = biblio.tome_info(config, "P", "Vol.1")
    boite = DialogueSorties(so.panneau(config, info))
    try:
        assert boite.table.topLevelItemCount() == len(boite.panneau.sorties)
        colonnes = {boite.table.topLevelItem(i).text(0): i
                    for i in range(boite.table.topLevelItemCount())}
        rang = colonnes["Archive CBZ"]
        item = boite.table.topLevelItem(rang)
        assert item.text(1) == "absente"
        assert "--assembler" in item.text(3)
        assert "relit pages_out/" in item.text(3)

        recus = []
        boite.demande_ouverture.connect(recus.append)
        boite.table.setCurrentItem(boite.table.topLevelItem(colonnes[
            "Planches lettrées (pages_out/)"]))
        assert boite.bouton_ouvrir.isEnabled()
        boite.bouton_ouvrir.click()
        assert recus == [build / "pages_out"]

        # Une sortie absente n'a rien à ouvrir : le bouton le dit en étant grisé.
        boite.table.setCurrentItem(boite.table.topLevelItem(colonnes["Archive CBZ"]))
        assert not boite.bouton_ouvrir.isEnabled()
    finally:
        boite.deleteLater()
