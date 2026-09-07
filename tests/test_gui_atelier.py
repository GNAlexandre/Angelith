# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'onglet **Atelier** — les seuls tests qui exigent vraiment Qt.

⚠ **Ils sont peu nombreux, et c'est le critère 3 du `PLAN-27`** : « toute la logique de
l'atelier est dans `illustration/`, testable sans PySide6. Comptez et publiez vos tests neufs
avec et sans Qt. » Ce fichier ne vérifie donc que ce qui est réellement du Qt :

- l'onglet existe et la fenêtre se construit avec ;
- **la fenêtre se construit encore quand `illustration/` est introuvable** — c'est la moitié
  de la propriété de feuille que le lot 27 conserve, et elle ne se prouve qu'à l'exécution ;
- un personnage sans référence validée est **grisé, non cliquable, avec l'infobulle qui dit
  quoi faire** (critère 2), ce qui est un état de widget et rien d'autre ;
- le badge « générée par IA » n'a **aucun** interrupteur dans les sources du panneau.

Tout le reste — le catalogue, l'écran de relecture, la porte, garder/jeter, l'inventaire, la
progression — se teste sans Qt dans `tests/test_illustration_*.py`.
"""
from __future__ import annotations

import ast
import importlib
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                                # noqa: E402
from PySide6.QtWidgets import QApplication                                   # noqa: E402

from gui import atelier as gui_atelier                                       # noqa: E402

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _config(tmp_path):
    (tmp_path / "sources" / "Temoin").mkdir(parents=True)
    (tmp_path / "build").mkdir(exist_ok=True)
    return {"chemins": {"sources": str(tmp_path / "sources"),
                        "build": str(tmp_path / "build")},
            "illustration": {"actif": True, "moteur": "factice"},
            "llm": {}, "modeles": {}, "langues": {"cible": "fr"}}


# ─────────────────────────────  Le panneau existe  ─────────────────────────────

def test_le_panneau_se_construit_et_montre_le_catalogue_d_abord(app, tmp_path):
    """L'écran central de ce lot n'est PAS la galerie, mais on n'y arrive qu'en partant du
    catalogue : la page 0 est le catalogue, la page 1 la relecture."""
    panneau = gui_atelier.PanneauAtelier(_config(tmp_path))
    assert panneau.pages.count() == 2
    assert panneau.pages.currentIndex() == 0


def test_l_atelier_est_une_destination_a_cote_des_autres(app, tmp_path, monkeypatch):
    """⚠ L'atelier était un ONGLET jusqu'au lot 30 ; il est une destination depuis le lot 31,
    et il n'est plus construit au démarrage — c'est même lui qui coûtait le plus cher, cf.
    `test_l_atelier_ne_lit_plus_le_glossaire_au_demarrage`."""
    from gui import destinations as dst
    from gui.fenetre import Fenetre

    monkeypatch.setenv("ANGELITH_REGLAGES", str(tmp_path / "interface.json"))
    fenetre = Fenetre(_config(tmp_path), str(tmp_path / "config.yaml"))
    assert dst.par_identifiant("illustrations").libelle == "Illustrations"
    assert fenetre.atelier is None, "rien n'est construit avant qu'on y aille"
    panneau = fenetre.aller_a("illustrations")
    assert panneau is fenetre.atelier
    assert isinstance(panneau, gui_atelier.PanneauAtelier)
    fenetre.close()


def test_l_atelier_ne_lit_plus_le_glossaire_au_demarrage(app, tmp_path, monkeypatch):
    """**Une prémisse du dépôt qui était fausse, et que l'étape 0 du `PLAN-31` a levée.**

    Le lot 27 écrivait, dans `gui/fenetre.py` : « son constructeur ne charge aucun poids : le
    catalogue se calcule en lisant des champs et en listant des fichiers. Un utilisateur qui
    n'ouvre jamais l'onglet ne paie rien. » C'était faux du CONSTRUCTEUR lui-même :
    `PanneauAtelier.__init__` appelle `_remplir_projets` → `_sur_projet` →
    `illustration.orchestrateur._glossaire`, qui lit `sources/<Projet>/glossaire.yaml`. Relevé
    le 2026-09-04 sur le corpus réel : **26,9 Ko de YAML lus au démarrage**, pour un onglet que
    personne n'avait ouvert.

    La phrase était vraie de son intention, pas de son code. Le lot 31 la rend vraie."""
    from core import glossary
    from gui.fenetre import Fenetre

    monkeypatch.setenv("ANGELITH_REGLAGES", str(tmp_path / "interface.json"))
    lus = []
    monkeypatch.setattr(glossary, "load", lambda c, *a, **k: lus.append(str(c)) or {})
    fenetre = Fenetre(_config(tmp_path), str(tmp_path / "config.yaml"))
    fenetre.show()
    assert lus == [], f"aucun glossaire ne doit être lu au démarrage — lu : {lus}"
    fenetre.close()


def test_une_tache_d_atelier_ne_gele_pas_le_choix_de_tome(app, tmp_path, monkeypatch):
    """Une tâche d'illustration porte `planche=None`, donc `_sur_debut` désarme le choix de
    tome comme pour un run. Sans réarmement à la fin, il resterait gelé pour le reste de la
    session — une destination voisine figée par un travail qui ne la concerne pas.

    ⚠ Le choix de tome a déménagé dans `PanneauRetouche` au lot 31 ; le comportement s'est
    déplacé avec lui, il n'a pas disparu."""
    from gui.fenetre import Fenetre
    from gui.travailleur import GENRE_ILLUSTRATION

    monkeypatch.setenv("ANGELITH_REGLAGES", str(tmp_path / "interface.json"))
    fenetre = Fenetre(_config(tmp_path), str(tmp_path / "config.yaml"))
    retouche = fenetre.aller_a("retouche")
    fenetre._sur_debut(None, GENRE_ILLUSTRATION, "Génération")
    assert not retouche.choix_tome.isEnabled()
    fenetre._sur_fin(None, GENRE_ILLUSTRATION, True, "1 image écrite.")
    assert retouche.choix_tome.isEnabled()
    assert retouche.choix_projet.isEnabled()
    fenetre.close()


def test_l_ordre_de_tabulation_est_declare_et_sans_doublon(app, tmp_path):
    """Critère 6 du `PLAN-19` : un ordre explicite PAR PANNEAU, pas un défaut qui se trouve
    juste."""
    panneau = gui_atelier.PanneauAtelier(_config(tmp_path))
    assert len(gui_atelier.PanneauAtelier.PARCOURS) >= 10
    assert len(set(gui_atelier.PanneauAtelier.PARCOURS)) == \
        len(gui_atelier.PanneauAtelier.PARCOURS)
    for nom in gui_atelier.PanneauAtelier.PARCOURS:
        assert hasattr(panneau, nom), nom


# ─────────────────  La feuille : la fenêtre survit sans la brique  ─────────────────

class _Bloqueur:
    """Rend `illustration` introuvable, comme si le dossier avait été supprimé."""

    def find_spec(self, nom, chemin=None, cible=None):
        if nom == "illustration" or nom.startswith("illustration."):
            raise ModuleNotFoundError(f"No module named {nom!r}")
        return None


@pytest.fixture
def sans_brique(monkeypatch):
    charges = {n: m for n, m in sys.modules.items()
               if n == "illustration" or n.startswith("illustration.")}
    for nom in charges:
        monkeypatch.delitem(sys.modules, nom, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_Bloqueur(), *sys.meta_path])
    yield
    for nom, module in charges.items():
        sys.modules.setdefault(nom, module)


def test_la_fenetre_se_construit_encore_quand_illustration_est_introuvable(
        app, tmp_path, monkeypatch, sans_brique):
    """⚠ **C'est la propriété que le lot 27 devait conserver.** Le test d'imports statiques
    interdit tout `import illustration` de niveau module dans `gui/` ; celui-ci vérifie que
    ça suffit — la fenêtre entière se construit, la destination est là, et elle dit pourquoi
    elle est vide au lieu de faire tomber l'application.

    ⚠ Le lot 31 rend la propriété PLUS forte, pas moins : la destination n'étant plus
    construite au démarrage, une brique absente ne coûte même plus l'import raté — et quand on
    y va quand même, l'état vide est celui du lot 27, mot pour mot."""
    from gui import destinations as dst
    from gui.fenetre import Fenetre

    monkeypatch.setenv("ANGELITH_REGLAGES", str(tmp_path / "interface.json"))
    fenetre = Fenetre(_config(tmp_path), str(tmp_path / "config.yaml"))
    assert len(dst.corps()) == 7
    atelier = fenetre.aller_a("illustrations")
    assert "n'est pas disponible" in atelier.bandeau.text()
    assert not atelier.bouton_preparer.isEnabled()
    fenetre.close()


def test_l_etat_vide_est_un_ECRAN_pas_un_aplat_gris(app, tmp_path, sans_brique):
    """Leçon explicite du `PLAN-18` : la première version affichait deux listes vides et une
    phrase de journal décrivant un geste à faire ailleurs."""
    panneau = gui_atelier.PanneauAtelier(_config(tmp_path))
    texte = panneau.bandeau.text()
    assert "supprimer son dossier sans rien casser" in texte
    assert "fonctionne normalement" in texte


def test_brique_absente_rend_le_motif_quand_elle_manque_et_rien_sinon(sans_brique):
    assert "ModuleNotFoundError" in gui_atelier.brique_absente()


def test_brique_presente_rend_une_chaine_vide():
    importlib.import_module("illustration.relecture")
    assert gui_atelier.brique_absente() == ""


# ─────────────────  Critère 2 : le personnage grisé, avec l'infobulle  ─────────────────

def _bible(tmp_path, avec_reference: bool):
    from core import bible as bible_mod

    dossier = tmp_path / "sources" / "Temoin"
    (tmp_path / "build" / "Temoin" / "Vol.1" / "media").mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.new("RGB", (8, 8), (1, 2, 3)).save(
        tmp_path / "build" / "Temoin" / "Vol.1" / "media" / "image1.png")
    entree = {
        "nom": "Aya", "apparence": {"yeux": "verts"},
        "citations": [{"attribut": "yeux", "source": "ch01.md", "texte": "ses yeux verts"}],
        "references": ([{"fichier": "media/image1.png", "confiance": "humaine"}]
                       if avec_reference else [])}
    sans_rien = {"nom": "Muette", "apparence": {}, "citations": [], "references": []}
    bible_mod.save(bible_mod.fill_defaults({"personnages": [entree, sans_rien]}),
                   bible_mod.chemin(dossier))


def test_un_personnage_sans_reference_est_grise_et_non_cliquable(app, tmp_path):
    """⚠ Critère 2 : « aucune génération ne part et aucun message d'erreur n'apparaît APRÈS
    le clic ». L'interface le dit AVANT."""
    config = _config(tmp_path)
    _bible(tmp_path, avec_reference=False)
    panneau = gui_atelier.PanneauAtelier(config)
    panneau._sur_projet("Temoin")

    muette = [panneau.liste_personnages.item(i)
              for i in range(panneau.liste_personnages.count())
              if "Muette" in panneau.liste_personnages.item(i).text()]
    assert muette, "le personnage hors d'atteinte doit rester VISIBLE, avec son motif"
    assert muette[0].flags() == Qt.NoItemFlags
    assert "tools/bible.py" in muette[0].toolTip()


def test_un_personnage_pret_est_selectionnable(app, tmp_path):
    config = _config(tmp_path)
    _bible(tmp_path, avec_reference=True)
    panneau = gui_atelier.PanneauAtelier(config)
    panneau._sur_projet("Temoin")
    assert panneau._personnage_choisi() == "Aya"


def test_sans_personnage_du_tout_l_etat_vide_renvoie_a_la_bible(app, tmp_path):
    config = _config(tmp_path)
    panneau = gui_atelier.PanneauAtelier(config)
    panneau._sur_projet("Temoin")
    item = panneau.liste_personnages.item(0)
    assert "référence visuelle validée" in item.text().lower()
    assert "ouvrir la bible" in item.text().lower()
    assert item.flags() == Qt.NoItemFlags


# ─────────────────  Le badge, l'annonce de coût, et ce qui ne se persiste pas  ─────────────────

def test_le_badge_genere_par_ia_n_a_aucun_interrupteur():
    """Critère 4 de L27.1 : « le badge *générée par IA* **non masquable** ». Il n'y a ni case
    à cocher, ni réglage, ni raccourci — la seule façon de ne pas le voir est de ne pas ouvrir
    l'onglet."""
    source = (RACINE / "gui" / "atelier.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    poses = [n for n in ast.walk(arbre)
             if isinstance(n, ast.Name) and n.id == "BADGE_IA"]
    assert poses, "le badge doit être posé quelque part"
    for mot in ("masquer_badge", "afficher_badge", "sans_badge", "badge_visible"):
        assert mot not in source


def test_l_annonce_de_cout_est_affichee_avant_de_lancer(app, tmp_path):
    """« Un run par lot » : on annonce ce que ça coûte AVANT d'engager le GPU, comme
    `gui/lanceur.py:_confirmer`."""
    panneau = gui_atelier.PanneauAtelier(_config(tmp_path))
    panneau.champ_nombre.setValue(8)
    panneau._peindre_cout()
    assert "entre" in panneau.etiquette_cout.text()
    assert "GPU" in panneau.etiquette_cout.text()


def test_la_fin_d_une_tache_ne_reactive_pas_le_bouton_quand_la_brique_est_desarmee(
        app, tmp_path):
    """Sans ce garde, « Préparer la requête » redeviendrait cliquable après une tâche sur une
    installation désarmée, et le refus n'arriverait qu'après le clic."""
    config = _config(tmp_path)
    config["illustration"]["actif"] = False
    panneau = gui_atelier.PanneauAtelier(config)
    panneau.marquer_en_cours(True)
    panneau.marquer_en_cours(False)
    assert not panneau.bouton_preparer.isEnabled()


def test_ni_le_nom_du_valideur_ni_la_graine_ne_se_persistent(app, tmp_path):
    """Le nom est une signature : le retrouver pré-rempli le lendemain transformerait une
    validation en case cochée d'avance, ce qui est exactement ce que la porte humaine
    refuse."""
    panneau = gui_atelier.PanneauAtelier(_config(tmp_path))
    panneau.champ_valideur.setCurrentText("Alexandre")
    panneau.champ_graine.setValue(1234)
    etat = panneau.reglages()
    assert "Alexandre" not in str(etat)
    assert "graine" not in etat and 1234 not in etat.values()


def test_le_cadrage_par_defaut_vient_de_la_CONFIGURATION_pas_de_l_ordre_de_la_liste(
        app, tmp_path):
    """L27.1 point 2 : « défaut = celui que le PLAN-25 L25.1 a mesuré comme le meilleur ».
    Laisser « visage » gagner parce qu'il est premier dans le tuple sortirait un gros plan là
    où la mesure recommande un buste."""
    config = _config(tmp_path)
    config["illustration"]["prompt"] = {"cadrage": "pied"}
    panneau = gui_atelier.PanneauAtelier(config)
    assert panneau.choix_cadrage.currentData() == "pied"


def test_les_cadrages_de_l_onglet_sont_ceux_de_la_console():
    """Deux listes qui divergeraient donneraient un cadrage proposé par une interface et
    inconnu de l'autre."""
    from illustration import console

    assert [n for n, _ in gui_atelier.CADRAGES] == [n for n, _ in console.CADRAGES]
