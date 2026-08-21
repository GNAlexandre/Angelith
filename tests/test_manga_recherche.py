# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Recherche plein-tome (`manga/recherche.py`) — sans Qt.

Ce que ce fichier verrouille surtout : la **correction manuelle l'emporte**. Renvoyer la
traduction du modele pour une bulle corrigee a la main enverrait l'utilisateur verifier un
texte qui n'existe plus sur la planche.
"""
import numpy as np
import pytest

from manga import checkpoints, recherche as rech
from manga.detection import BubbleRegion


def _planche(build, index, *, traduction=(), ocr=(), manuelles=None):
    ckpt = checkpoints.page_checkpoint_dir(build, index)
    ckpt.mkdir(parents=True, exist_ok=True)
    n = max(len(traduction), len(ocr), 1)
    masque = np.zeros((20, 20), dtype=bool)
    masque[2:8, 2:8] = True
    checkpoints.save_regions(
        ckpt, [BubbleRegion(bbox=(2, 2, 8, 8), mask=masque, score=0.9, cls=0)] * n, (20, 20))
    if ocr:
        checkpoints.save_ocr(ckpt, list(ocr))
    if traduction:
        checkpoints.save_traduction(ckpt, list(traduction))
    if manuelles:
        checkpoints.save_traduction_manuelle(ckpt, manuelles)
    return ckpt


@pytest.fixture
def tome(tmp_path):
    build = tmp_path / "manga"
    _planche(build, 1, traduction=["Bonjour Léo", "Rien ici"], ocr=["こんにちは", "何も"])
    _planche(build, 2, traduction=["Le ciel est bleu"], ocr=["空は青い"])
    return build


# --------------------------------------------------------------------------- #
#  Normalisation
# --------------------------------------------------------------------------- #

def test_la_casse_est_ignoree(tome):
    assert [r["planche"] for r in rech.chercher(tome, "BONJOUR")] == [1]


def test_les_accents_sont_ignores(tome):
    """Chercher « leo » doit trouver « Léo » — sinon la recherche punit qui tape vite."""
    assert [r["planche"] for r in rech.chercher(tome, "leo")] == [1]


def test_le_japonais_est_trouve(tome):
    resultats = rech.chercher(tome, "空は青い")
    assert [(r["planche"], r["champ"]) for r in resultats] == [(2, rech.CHAMP_OCR)]


def test_la_normalisation_ne_casse_pas_les_kana():
    """`NFD` ne doit pas decomposer les kana en signes qu'on retirerait par erreur."""
    assert rech.normaliser("ガギグ") == "ガギグ".casefold()


# --------------------------------------------------------------------------- #
#  Ce qui l'emporte
# --------------------------------------------------------------------------- #

def test_la_correction_manuelle_est_la_replique_affichee(tmp_path):
    build = tmp_path / "manga"
    _planche(build, 1, traduction=["Version modele"], manuelles={0: "Ma version"})
    assert rech.repliques(build, 1)[0]["affichee"] == "Ma version"
    assert rech.repliques(build, 1)[0]["manuelle"] is True


def test_chercher_la_correction_la_trouve_comme_replique(tmp_path):
    build = tmp_path / "manga"
    _planche(build, 1, traduction=["Version modele"], manuelles={0: "Ma version"})
    resultats = rech.chercher(build, "Ma version")
    assert [r["champ"] for r in resultats] == [rech.CHAMP_AFFICHEE]


def test_la_traduction_remplacee_reste_trouvable_mais_nommee(tmp_path):
    """Retrouver ce qu'on a corrige est utile — a condition de savoir que c'est l'ancien."""
    build = tmp_path / "manga"
    _planche(build, 1, traduction=["Version modele"], manuelles={0: "Ma version"})
    resultats = rech.chercher(build, "Version modele")
    assert [r["champ"] for r in resultats] == [rech.CHAMP_TRADUCTION]


def test_une_bulle_non_corrigee_ne_sort_pas_deux_fois(tome):
    """Sans le filtre, chaque bulle sortirait en « replique » ET en « traduction »."""
    resultats = rech.chercher(tome, "Bonjour")
    assert len(resultats) == 1


# --------------------------------------------------------------------------- #
#  Forme des resultats
# --------------------------------------------------------------------------- #

def test_le_resultat_porte_planche_bulle_et_champ(tome):
    r = rech.chercher(tome, "Rien ici")[0]
    assert r["planche"] == 1 and r["bulle"] == 1 and r["champ"] == rech.CHAMP_AFFICHEE


def test_l_ordre_est_celui_de_lecture(tmp_path):
    build = tmp_path / "manga"
    for index in (3, 1, 2):
        _planche(build, index, traduction=["commun"])
    assert [r["planche"] for r in rech.chercher(build, "commun")] == [1, 2, 3]


def test_l_extrait_montre_le_texte_d_origine_accents_compris():
    """Afficher la forme normalisee montrerait « Leo » la ou la planche dit « Léo »."""
    assert "Léo" in rech.extrait("Bonjour Léo, comment vas-tu", "leo")


def test_l_extrait_est_borne_et_signale_la_coupe():
    long = "x" * 200 + "cible" + "y" * 200
    bout = rech.extrait(long, "cible")
    assert "cible" in bout and len(bout) < 100 and bout.startswith("…")


def test_l_extrait_aplatit_les_sauts_de_ligne():
    assert "\n" not in rech.extrait("Bonjour\nLéo", "bonjour")


# --------------------------------------------------------------------------- #
#  Cas limites
# --------------------------------------------------------------------------- #

def test_une_recherche_vide_ne_rend_rien(tome):
    """« Tout » serait le tome entier, ce qui n'est pas une reponse."""
    assert rech.chercher(tome, "") == []
    assert rech.chercher(tome, "   ") == []


def test_un_tome_sans_traduction_ne_fait_pas_lever(tmp_path):
    build = tmp_path / "manga"
    checkpoints.page_checkpoint_dir(build, 1).mkdir(parents=True)
    assert rech.chercher(build, "quoi") == []
    assert rech.repliques(build, 1) == []


def test_un_tome_inexistant_ne_fait_pas_lever(tmp_path):
    assert rech.chercher(tmp_path / "absent", "quoi") == []


def test_la_limite_borne_les_resultats(tmp_path):
    build = tmp_path / "manga"
    for index in range(1, 11):
        _planche(build, index, traduction=["commun"])
    assert len(rech.chercher(build, "commun", limite=4)) == 4


def test_la_restriction_aux_indices_est_respectee(tome):
    assert rech.chercher(tome, "e", indices=[2]) and \
        all(r["planche"] == 2 for r in rech.chercher(tome, "e", indices=[2]))


def test_une_correction_au_dela_des_bulles_ne_fait_pas_lever(tmp_path):
    """Le nombre de bulles peut avoir baisse depuis que la correction a ete ecrite."""
    build = tmp_path / "manga"
    _planche(build, 1, traduction=["Une seule"], manuelles={7: "Orpheline"})
    assert any(r["texte"] == "Orpheline" for r in rech.chercher(build, "Orpheline"))
