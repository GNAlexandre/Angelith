# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Vignettes et pastilles de la pellicule (`gui/pellicule.py`) — sans Qt.

Ce module vit dans `gui/` mais ne construit aucun widget : il fabrique des images et décide
ce qu'une pastille annonce. C'est la règle de couche du dépôt — ce qui décide se teste sans
PySide6, et c'est pour cela que ce fichier n'a pas d'`importorskip`.
"""
import os
import time

import numpy as np
import pytest
from PIL import Image

from gui import pellicule as pel
from manga import checkpoints
from manga.detection import BubbleRegion


def _etat(**kw) -> dict:
    """Un état de planche par défaut : détectée, rendue, rien à signaler."""
    base = {"index": 12, "detectee": True, "bulles": 6, "corrigees": 0, "deplacees": 0,
            "vides": 0, "debordements": 0, "rendue": True, "perimee": False, "motifs": []}
    base.update(kw)
    return base


@pytest.fixture
def tome(tmp_path):
    """Un tome d'une planche détectée et rendue."""
    build = tmp_path / "manga"
    ckpt = checkpoints.page_checkpoint_dir(build, 1)
    ckpt.mkdir(parents=True)
    masque = np.zeros((60, 40), dtype=bool)
    masque[5:30, 5:30] = True
    checkpoints.save_regions(ckpt, [BubbleRegion(bbox=(5, 5, 30, 30), mask=masque,
                                                 score=0.9, cls=0)], (40, 60))
    for chemin in (checkpoints.clean_page_path(build, 1),
                   checkpoints.final_page_path(build, 1)):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (400, 600), "white").save(chemin)
    return build


# --------------------------------------------------------------------------- #
#  Fabrication
# --------------------------------------------------------------------------- #

def test_la_vignette_est_ecrite_a_la_bonne_largeur(tome):
    chemin = pel.fabriquer_vignette(tome, 1, largeur=100)
    assert chemin is not None and chemin.exists()
    with Image.open(chemin) as vignette:
        assert vignette.width == 100
        assert vignette.height == 150, "le rapport de la planche est conservé"


def test_la_vignette_vit_dans_un_dossier_cache(tome):
    """Contrairement à `pages_clean/`, elle n'est faite pour être lue par personne."""
    assert pel.chemin_vignette(tome, 1).parent.name == ".vignettes"


def test_le_rendu_final_est_prefere_a_la_planche_nettoyee(tome):
    """C'est ce que l'utilisateur cherche à reconnaître."""
    assert pel.source_de_vignette(tome, 1) == checkpoints.final_page_path(tome, 1)


def test_sans_rendu_la_planche_nettoyee_fait_l_affaire(tome):
    """Une vignette sans texte vaut mieux que pas de vignette."""
    checkpoints.final_page_path(tome, 1).unlink()
    assert pel.source_de_vignette(tome, 1) == checkpoints.clean_page_path(tome, 1)


def test_une_planche_sans_image_ne_produit_rien_et_ne_leve_pas(tmp_path):
    assert pel.source_de_vignette(tmp_path / "manga", 3) is None
    assert pel.fabriquer_vignette(tmp_path / "manga", 3) is None


# --------------------------------------------------------------------------- #
#  Fraîcheur
# --------------------------------------------------------------------------- #

def test_une_vignette_absente_n_est_pas_a_jour(tome):
    assert pel.vignette_a_jour(tome, 1) is False


def test_une_vignette_fraiche_est_a_jour(tome):
    pel.fabriquer_vignette(tome, 1)
    assert pel.vignette_a_jour(tome, 1) is True


def test_un_relettrage_perime_la_vignette(tome):
    """Une vignette figée montrerait l'ancienne planche — exactement ce qu'on regarde pour
    vérifier son travail."""
    pel.fabriquer_vignette(tome, 1)
    futur = time.time() + 120
    os.utime(checkpoints.final_page_path(tome, 1), (futur, futur))
    assert pel.vignette_a_jour(tome, 1) is False


def test_une_planche_sans_image_compte_comme_a_jour(tmp_path):
    """Il n'y a pas de travail en attente : la redemander sans fin affamerait les autres."""
    assert pel.vignette_a_jour(tmp_path / "manga", 9) is True


# --------------------------------------------------------------------------- #
#  Pastilles
# --------------------------------------------------------------------------- #

def test_une_planche_sans_rien_a_signaler_ne_porte_aucune_pastille():
    assert pel.pastilles(_etat()) == []


def test_une_planche_non_detectee_le_dit_et_rien_d_autre():
    assert pel.pastilles(_etat(detectee=False, bulles=0)) == ["∅"]


def test_le_rendu_perime_passe_en_premier():
    """C'est la seule pastille qui appelle une action — les autres décrivent."""
    marques = pel.pastilles(_etat(perimee=True, corrigees=2, debordements=1))
    assert marques[0] == "⟳"


def test_les_corrections_et_deplacements_sont_comptes():
    marques = pel.pastilles(_etat(corrigees=2, deplacees=3))
    assert "✎2" in marques and "↔3" in marques


def test_la_legende_porte_le_numero_et_le_nombre_de_bulles():
    legende = pel.legende(_etat(index=12, bulles=6))
    assert legende.startswith("12") and "6" in legende


def test_la_couleur_distingue_trois_etats_seulement():
    assert pel.couleur(_etat()) is None
    assert pel.couleur(_etat(perimee=True)) == "#d09030"
    assert pel.couleur(_etat(corrigees=1)) == "#6aa6d8"
    assert pel.couleur(_etat(detectee=False)) == "#777"


def test_le_perime_l_emporte_sur_la_correction():
    assert pel.couleur(_etat(perimee=True, corrigees=1)) == "#d09030"


# --------------------------------------------------------------------------- #
#  Filtres
# --------------------------------------------------------------------------- #

def test_le_filtre_toutes_ne_masque_rien():
    etats = [_etat(index=1), _etat(index=2, perimee=True)]
    assert pel.filtrer(etats, "toutes") == etats


def test_le_filtre_perime_ne_garde_que_les_perimees():
    etats = [_etat(index=1), _etat(index=2, perimee=True)]
    assert [e["index"] for e in pel.filtrer(etats, "rendu périmé")] == [2]


def test_le_filtre_modifiees_voit_les_corrections_et_les_deplacements():
    etats = [_etat(index=1), _etat(index=2, corrigees=1), _etat(index=3, deplacees=1)]
    assert [e["index"] for e in pel.filtrer(etats, "modifiées à la main")] == [2, 3]


def test_un_filtre_inconnu_ne_masque_rien():
    """Perdre des planches sur une faute de frappe serait le pire des retours."""
    etats = [_etat(index=1), _etat(index=2)]
    assert pel.filtrer(etats, "n'existe pas") == etats


def test_tous_les_filtres_annonces_sont_utilisables():
    etats = [_etat(index=1), _etat(index=2, perimee=True, corrigees=1, vides=1,
                                   debordements=1, rendue=False)]
    for nom in pel.FILTRES:
        assert isinstance(pel.filtrer(etats, nom), list)
