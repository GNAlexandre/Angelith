# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les trois boîtes du lot 40 — créer un roman, importer un tome corrigé, se mettre à jour.

Comme `tests/test_gui_dialogues_oeuvres.py` : elles ne **décident** de rien — `import_build.py`
et `gui/vue_maj.py` portent les règles et sont testés sans écran ailleurs. Ce fichier vérifie
ce qui ne se teste que monté :

- que le bouton d'installation **n'existe pas** quand rien n'est vérifiable ;
- que fermer la fenêtre de mise à jour à la croix ne vaut **pas** un consentement ;
- que « Ne plus afficher » est lu même quand la réponse est « plus tard » — c'est le cas le plus
  fréquent : « pas maintenant, et ne me le redemande plus » ;
- que la boîte d'import **n'écrit rien** tant qu'on n'a pas validé ;
- que « Light novel » est bien dans la boîte de création, et que la langue y est
  **obligatoire** — c'est le point 1 de la demande, et la boîte est le seul endroit où il
  se constate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6",
                    reason="interface graphique : pip install -r requirements-gui.txt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialogButtonBox                   # noqa: E402

from core import maj                                                          # noqa: E402
from gui.dialogues import (DialogueImportBuild, DialogueMaj,                  # noqa: E402
                           DialogueNouveauProjet)


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


INSTALLEUR = maj.Asset("Angelith-99.0.0-windows-x64-setup.exe",
                       "https://example.invalid/setup.exe", 306242994)
SOMMES = maj.Asset(maj.NOM_SOMMES, "https://example.invalid/SHA256SUMS.txt", 105)


def _resultat(**kw) -> maj.Resultat:
    base = {"arme": True, "disponible": True, "version": "99.0.0",
            "assets": (INSTALLEUR, SOMMES)}
    base.update(kw)
    return maj.Resultat(**base)


def _libelles(boite) -> list[str]:
    cadre = boite.findChild(QDialogButtonBox)
    return [b.text() for b in cadre.buttons()]


# --------------------------------------------------------------------------- #
#  La mise à jour
# --------------------------------------------------------------------------- #

def test_gelee_et_verifiable_le_bouton_d_installation_est_la(qt_app):
    boite = DialogueMaj(_resultat(), "2.33.0", gele=True)
    assert any("Installer" in libelle for libelle in _libelles(boite))
    boite.deleteLater()


def test_depuis_les_sources_il_n_y_a_PAS_de_bouton_d_installation(qt_app):
    """⚠ Absent, et pas grisé : un bouton grisé se lit « pas encore », alors qu'ici c'est
    « jamais depuis un dépôt git »."""
    boite = DialogueMaj(_resultat(), "2.33.0", gele=False)
    assert not any("Installer" in libelle for libelle in _libelles(boite))
    assert any("page" in libelle for libelle in _libelles(boite))
    boite.deleteLater()


def test_sans_fichier_d_empreintes_non_plus(qt_app):
    boite = DialogueMaj(_resultat(assets=(INSTALLEUR,)), "2.33.0", gele=True)
    assert not any("Installer" in libelle for libelle in _libelles(boite))
    boite.deleteLater()


def test_le_texte_dit_ce_que_l_empreinte_ne_protege_pas(qt_app):
    boite = DialogueMaj(_resultat(), "2.33.0", gele=True)
    texte = boite.zone.toPlainText()
    assert "NE remplace PAS une signature de code" in texte
    assert "292,1 Mio" in texte
    boite.deleteLater()


def test_fermer_a_la_croix_ne_vaut_pas_un_consentement(qt_app):
    """⚠ Le défaut est « plus tard ». Une fenêtre qu'on chasse n'a rien accepté."""
    boite = DialogueMaj(_resultat(), "2.33.0", gele=True)
    boite.reject()
    assert boite.choix() == "plus_tard"
    boite.deleteLater()


def test_ne_plus_afficher_est_lu_meme_quand_on_repond_plus_tard(qt_app):
    """C'est le cas le PLUS fréquent : « pas maintenant, et ne me le redemande plus ». Lire la
    case uniquement sur un `Accepted` la perdrait exactement là où elle sert."""
    boite = DialogueMaj(_resultat(), "2.33.0", gele=True)
    boite.case_silence.setChecked(True)
    boite.reject()
    assert boite.silencieuse() is True
    boite.deleteLater()


def test_la_case_dit_a_l_ecran_ce_qu_elle_ne_coupe_pas(qt_app):
    """⚠ Une case « ne plus afficher » qui couperait silencieusement l'appel réseau serait un
    opt-out que personne ne saurait retrouver. La fenêtre doit dire les deux."""
    boite = DialogueMaj(_resultat(), "2.33.0", gele=True)
    from PySide6.QtWidgets import QLabel
    textes = " ".join(e.text() for e in boite.findChildren(QLabel))
    assert "maj.verifier" in textes
    assert "Réglages" in textes
    boite.deleteLater()


def test_le_bouton_page_rend_le_bon_choix(qt_app):
    boite = DialogueMaj(_resultat(), "2.33.0", gele=False)
    cadre = boite.findChild(QDialogButtonBox)
    for bouton in cadre.buttons():
        if "page" in bouton.text():
            bouton.click()
    assert boite.choix() == "page"
    boite.deleteLater()


# --------------------------------------------------------------------------- #
#  L'import d'un tome corrigé
# --------------------------------------------------------------------------- #

def _tome(racine: Path, nom: str, textes: list[str], *, projet: str = "Oeuvre",
          tome: str = "Vol.1") -> Path:
    """Un `build/<P>/<T>/manga/` minimal. ⚠ **Recopié de `tests/test_import_build.py`** plutôt
    qu'importé : ce fichier-ci ne s'exécute qu'avec PySide6, et l'autre doit rester lisible
    sans. Les deux décrivent la même arborescence, celle que `manga/projet.py` indexe."""
    from manga import checkpoints as ck

    dossier = racine / nom / "manga"
    for index, texte in enumerate(textes, 1):
        page = dossier / ".checkpoints" / f"page_{index:04d}"
        page.mkdir(parents=True)
        (page / "regions.json").write_text(
            json.dumps({"format": ck.FORMAT_VERSION, "image_size": [10, 10], "regions": []}),
            encoding="utf-8")
        (page / "traduction.json").write_text(json.dumps([texte]), encoding="utf-8")
    (dossier / "projet.json").write_text(
        json.dumps({"format": 1, "projet": projet, "tome": tome, "outil": "x",
                    "revision": 1, "pages": []}), encoding="utf-8")
    return dossier


def test_l_import_montre_ce_qui_va_changer_et_n_ecrit_rien(qt_app, tmp_path):
    """⚠ **Rien n'est écrit tant qu'on n'a pas validé** — même exigence que le dépôt guidé du
    lot 34, et pour la même raison : un aperçu qui écrirait ne serait pas un aperçu."""
    cible = _tome(tmp_path, "local", ["A", "B", "C"])
    source = _tome(tmp_path, "recu", ["A", "B corrigé", "C"])
    avant = {f: f.read_bytes() for f in cible.rglob("*") if f.is_file()}

    boite = DialogueImportBuild(cible)
    boite.champ_source.setText(str(source))
    plan = boite.plan()
    assert plan is not None and plan.executable
    assert plan.compte("modifiee") == 1 or len(plan.planches) == 3
    assert boite.detail.count() == 1, "seules les planches qui changent sont listées"
    assert boite.boutons.button(QDialogButtonBox.Ok).isEnabled()
    apres = {f: f.read_bytes() for f in cible.rglob("*") if f.is_file()}
    assert apres == avant, "l'aperçu a écrit dans le tome local"
    boite.deleteLater()


def test_sans_dossier_choisi_le_bouton_reste_inerte(qt_app, tmp_path):
    cible = _tome(tmp_path, "local", ["A"])
    boite = DialogueImportBuild(cible)
    assert boite.plan() is None
    assert not boite.boutons.button(QDialogButtonBox.Ok).isEnabled()
    boite.deleteLater()


def test_la_case_des_planches_rendues_est_decochee_et_dit_son_prix(qt_app, tmp_path):
    """⚠ Mesuré le 2026-09-06 sur les 10 tomes manga du corpus : les checkpoints — tout le
    travail humain — pèsent 0,1 % du poids. Transférer 3 Go pour 4 Mo de corrections doit être
    un choix explicite."""
    cible = _tome(tmp_path, "local", ["A"])
    boite = DialogueImportBuild(cible)
    assert boite.case_rendus.isChecked() is False
    assert "Go" in boite.case_rendus.text()
    boite.deleteLater()


def test_un_tome_etranger_est_refuse_et_le_bouton_reste_inerte(qt_app, tmp_path):
    """On n'installe pas le tome d'un autre. ⚠ Le refus est affiché AVANT toute écriture."""
    cible = _tome(tmp_path, "local", ["A", "B"])
    source = _tome(tmp_path, "recu", ["A", "B corrigé"], projet="AUTRE", tome="Vol.9")

    boite = DialogueImportBuild(cible)
    boite.champ_source.setText(str(source))
    plan = boite.plan()
    assert plan is not None and not plan.executable and plan.refus
    assert not boite.boutons.button(QDialogButtonBox.Ok).isEnabled()
    boite.deleteLater()


# --------------------------------------------------------------------------- #
#  Créer un projet — « Light novel » y était absent, et c'est la brique historique
# --------------------------------------------------------------------------- #

def _config_ln(racine: Path) -> dict:
    return {"chemins": {"sources": str(racine / "sources")},
            "manga": {"chemins": {"sources": str(racine / "sources")}},
            "langues": {"dossiers": {"ENG": "en", "JAP": "jp"}}}


def test_les_trois_dispositions_sont_proposees(qt_app, tmp_path):
    """Point 1 de la demande : la boîte offrait Manga et Webtoon, **pas** Light novel — la
    brique historique du projet était la seule qu'on ne pouvait pas créer ici."""
    boite = DialogueNouveauProjet(_config_ln(tmp_path))
    libelles = [boite.choix_format.itemText(i) for i in range(boite.choix_format.count())]
    assert any("Light novel" in libelle for libelle in libelles), libelles
    boite.deleteLater()


def test_pour_un_roman_la_langue_n_a_PAS_de_valeur_par_defaut(qt_app, tmp_path):
    """⚠ Laisser « (langue par défaut du projet) » visible puis refuser à la validation serait
    proposer une impasse : `pipeline/sources.py` cherche des dossiers de langue directement
    sous le tome, et un roman sans langue n'est lisible par aucune brique."""
    import creation as crea

    boite = DialogueNouveauProjet(_config_ln(tmp_path))
    boite.choix_format.setCurrentIndex(boite.choix_format.findData(crea.LIGHT_NOVEL))
    donnees = [boite.choix_langue.itemData(i) for i in range(boite.choix_langue.count())]
    assert None not in donnees, donnees
    assert "ENG" in donnees
    boite.deleteLater()


def test_pour_un_manga_la_langue_reste_facultative(qt_app, tmp_path):
    """Iso : un cran de moins reste un cran de moins à comprendre, et `manga.langue_source`
    s'applique déjà."""
    import creation as crea

    boite = DialogueNouveauProjet(_config_ln(tmp_path))
    boite.choix_format.setCurrentIndex(boite.choix_format.findData(crea.MANGA))
    donnees = [boite.choix_langue.itemData(i) for i in range(boite.choix_langue.count())]
    assert None in donnees
    boite.deleteLater()


def test_la_description_porte_la_disposition_et_pas_un_format(qt_app, tmp_path):
    """⚠ `quelle`, pas `format` : « light_novel » n'est pas un format de la brique manga, c'est
    une DISPOSITION. Garder `format` aurait installé la confusion dans le contrat."""
    import creation as crea

    boite = DialogueNouveauProjet(_config_ln(tmp_path))
    boite.choix_format.setCurrentIndex(boite.choix_format.findData(crea.LIGHT_NOVEL))
    boite.champ_projet.setText("Mon Roman")
    boite.champ_tome.setText("Vol.1")
    description = boite.description()
    assert description["quelle"] == crea.LIGHT_NOVEL
    assert description["langue"]
    boite.deleteLater()


def test_la_boite_de_creation_n_ecrit_rien(qt_app, tmp_path):
    """Même exigence que les deux autres boîtes de ce fichier : la copie est soumise au fil de
    travail par la fenêtre, jamais faite ici."""
    boite = DialogueNouveauProjet(_config_ln(tmp_path))
    boite.champ_projet.setText("Mon Roman")
    boite.champ_tome.setText("Vol.1")
    boite.description()
    assert not (tmp_path / "sources").exists()
    boite.deleteLater()

