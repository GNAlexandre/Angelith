# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les métriques de détection et le corpus synthétique — **sans modèle**.

La détection réelle est mesurée ailleurs (`tests/test_banc_corpus_synthetique.py`, marqué
`modeles`). Ici on vérifie ce qui décide : le format d'annotation, la rasterisation, et le
fait que l'appariement compte ce qu'on croit qu'il compte. La prédiction est **injectée**,
donc parfaitement contrôlée — c'est la seule façon de tester une métrique : en connaissant
d'avance la bonne réponse.

⚠ Aucun marqueur : boucle courte.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from tools import _banc_detection as mesure          # noqa: E402
from tools import corpus_synthetique                 # noqa: E402


def _region(x0, y0, x1, y1, taille=(200, 200)):
    from manga.detection import BubbleRegion
    masque = np.zeros((taille[1], taille[0]), dtype=bool)
    masque[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=masque, score=0.9, cls=0, kind="bulle")


# --- format d'annotation ----------------------------------------------------

def test_les_annotations_coco_se_relisent(tmp_path: Path):
    coco = corpus_synthetique.ecrire(tmp_path)
    corpus = mesure.charger_annotations(tmp_path)
    assert corpus is not None
    assert len(corpus.planches) == len(coco["images"]) == 3
    assert sum(len(p.polygones) for p in corpus.planches) == len(coco["annotations"])


def test_une_categorie_qui_n_est_pas_une_bulle_est_ignoree(tmp_path: Path):
    """Un corpus annoté pour autre chose — cases, onomatopées — reste lisible ; il ne
    contribue simplement pas à CETTE mesure. Sans ce tri, une annotation de case gonflerait le
    dénominateur du rappel."""
    (tmp_path / "annotations.json").write_text(json.dumps({
        "images": [{"id": 1, "file_name": "a.png", "width": 100, "height": 100}],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 1, "segmentation": [[0, 0, 9, 0, 9, 9]]},
            {"id": 2, "image_id": 1, "category_id": 2, "segmentation": [[0, 0, 99, 0, 99, 99]]},
        ],
        "categories": [{"id": 1, "name": "bulle"}, {"id": 2, "name": "case"}],
    }), encoding="utf-8")
    corpus = mesure.charger_annotations(tmp_path)
    assert len(corpus.planches[0].polygones) == 1


def test_un_dossier_sans_annotations_rend_none(tmp_path: Path):
    assert mesure.charger_annotations(tmp_path) is None


def test_un_polygone_devient_un_masque_puis_une_region():
    planche = mesure.Planche(id=1, fichier="a.png", largeur=100, hauteur=100,
                             polygones=[[10, 10, 60, 10, 60, 40, 10, 40]])
    regions = mesure.regions_de_verite(planche)
    assert len(regions) == 1
    assert regions[0].bbox == (10, 10, 61, 41)
    assert regions[0].mask.sum() == pytest.approx(51 * 31, rel=0.05)


def test_la_verite_s_ecrit_au_format_du_pipeline(tmp_path: Path):
    """La vérité terrain doit se relire avec les outils du dépôt — sinon personne ne la
    vérifie jamais."""
    from tools import _banc_commun as commun
    planche = mesure.Planche(id=1, fichier="a.png", largeur=120, hauteur=90,
                             polygones=[[10, 10, 60, 10, 60, 40, 10, 40]])
    mesure.ecrire_cache_verite(tmp_path, planche)
    relu = commun.lire_meta_regions(tmp_path)
    assert relu["image_size"] == (120, 90)
    assert len(relu["regions"]) == 1
    assert len(commun.charger_regions(tmp_path)) == 1


# --- les métriques ----------------------------------------------------------

def test_une_detection_parfaite_donne_un_rappel_de_un():
    verite = [_region(10, 10, 60, 60), _region(100, 100, 150, 150)]
    m = mesure.mesurer_planche(verite, list(verite))
    assert (m["trouvees"], m["fausses"]) == (2, 0)
    assert mesure.agreger([m])["rappel"] == 1.0


def test_une_detection_au_meme_endroit_mais_pas_la_meme_bulle_ne_compte_pas():
    """Le seuil d'IoU à 0,50 n'est pas une formalité : « une bulle conservée est la même
    bulle, pas une bulle au même endroit » (`detection_retry.apparier`)."""
    verite = [_region(10, 10, 60, 60)]
    a_peine = [_region(50, 50, 100, 100)]
    assert mesure.mesurer_planche(verite, a_peine)["trouvees"] == 0


def test_une_planche_a_zero_detection_alors_qu_elle_porte_du_texte_est_signalee():
    """LA métrique qui décide. Une planche à 60 % de rappel produit un résultat qu'un
    relecteur corrige ; une planche à zéro produit une page entièrement non traduite que
    personne ne voit passer."""
    m = mesure.mesurer_planche([_region(10, 10, 60, 60)], [])
    assert m["zero_alors_que_texte"] is True
    assert mesure.agreger([m])["zéro alors que texte"] == 1


def test_une_planche_vide_correctement_vide_n_est_pas_signalee():
    assert mesure.mesurer_planche([], [])["zero_alors_que_texte"] is False


def test_les_fausses_detections_sont_comptees_par_planche():
    """La seconde métrique de tête, promue par la mesure du webtoon : 11 fausses détections
    probables sur 59 bulles, là où les neuf volumes de manga paginé en ont ZÉRO sur 7 803."""
    verite = [_region(10, 10, 60, 60)]
    predites = [_region(10, 10, 60, 60), _region(120, 120, 170, 170)]
    bilan = mesure.agreger([mesure.mesurer_planche(verite, predites)])
    assert bilan["fausses/planche"] == 1.0
    assert bilan["précision"] == 0.5


def test_un_double_non_scinde_est_compte_comme_fusion_et_non_comme_oubli():
    """Deux ballons collés vus comme UNE région : le détecteur a vu, il n'a pas séparé. Le
    lot 13 traite ce défaut ; le confondre avec un oubli le rendrait invisible."""
    verite = [_region(10, 10, 60, 60), _region(60, 10, 110, 60)]
    fusionnee = [_region(10, 10, 110, 60)]
    m = mesure.mesurer_planche(verite, fusionnee)
    assert m["fusions"] == 1
    assert mesure.agreger([m])["doubles non scindées"] == 1


def test_le_rappel_est_ventile_par_taille_de_bulle():
    """C'est là que se voit le gain d'`input_size` : un rappel global stable peut cacher un
    effondrement sur les petites bulles, qui sont justement celles que le redimensionnement
    d'entrée écrase."""
    minuscule, grande = _region(0, 0, 20, 20), _region(50, 50, 190, 190)
    bilan = mesure.agreger([mesure.mesurer_planche([minuscule, grande], [grande])])
    par_taille = bilan["rappel par taille"]
    assert par_taille["0–2000"] == 0.0
    assert par_taille["10000–40000"] == 1.0


def test_les_deux_regimes_ne_sont_jamais_moyennes(tmp_path: Path):
    """Manga paginé et webtoon sont deux régimes différents — l'écart mesuré, de 0 % à 19 %
    de zones restaurées selon le format, suffit à le prouver. Une moyenne unique les
    masquerait."""
    corpus_synthetique.ecrire(tmp_path)
    resultat = mesure.mesurer_corpus(tmp_path, predire=lambda image: [])
    assert set(resultat["par_regime"]) == {"manga", "webtoon"}
    assert resultat["par_regime"]["webtoon"]["planches"] == 1
    assert resultat["par_regime"]["manga"]["planches"] == 2
    # Aucune prédiction : toutes les planches annotées rendent zéro bulle.
    assert resultat["global"]["zéro alors que texte"] == 3


def test_une_verite_parfaitement_predite_donne_un_f1_de_un(tmp_path: Path):
    """Le banc bout en bout, avec la vérité terrain en guise de prédiction — le seul cas dont
    on connaisse la réponse sans modèle."""
    corpus_synthetique.ecrire(tmp_path)
    corpus = mesure.charger_annotations(tmp_path)
    par_fichier = {p.fichier: mesure.regions_de_verite(p) for p in corpus.planches}
    ordre = iter([par_fichier[p.fichier] for p in corpus.planches])
    resultat = mesure.mesurer_corpus(tmp_path, predire=lambda image: next(ordre))
    assert resultat["global"]["F1"] == 1.0
    assert resultat["global"]["fausses/planche"] == 0.0


def test_le_bilan_se_rend_en_markdown(tmp_path: Path):
    corpus_synthetique.ecrire(tmp_path)
    resultat = mesure.mesurer_corpus(tmp_path, predire=lambda image: [])
    rendu = mesure.rendre(resultat, markdown=True)
    assert "Licence du corpus" in rendu and "AGPL-3.0" in rendu
    assert "detection_retry.apparier" in rendu       # le banc publie son appariement


# --- le corpus synthétique --------------------------------------------------

def test_le_corpus_est_deterministe(tmp_path: Path):
    """Deux exécutions rendent le même corpus au pixel près. Sans cela, un banc avant/après
    comparerait deux corpus différents et attribuerait au code ce qui vient du hasard."""
    a = corpus_synthetique.ecrire(tmp_path / "a")
    b = corpus_synthetique.ecrire(tmp_path / "b")
    assert a == b
    for nom in ("page_manga_01.png", "bande_webtoon_01.png"):
        assert (tmp_path / "a" / nom).read_bytes() == (tmp_path / "b" / nom).read_bytes()


def test_le_corpus_contient_une_bande_de_dix_mille_pixels(tmp_path: Path):
    """La bande n'est pas un supplément : c'est la seule planche du dépôt qui exerce le
    découpage en fenêtres, et la seule façon de faire tourner le lot 14 en CI."""
    corpus_synthetique.ecrire(tmp_path)
    corpus = mesure.charger_annotations(tmp_path)
    bandes = [p for p in corpus.planches if p.est_bande]
    assert [(p.largeur, p.hauteur) for p in bandes] == [(1080, 10_000)]


def test_le_corpus_couvre_les_cas_limites_visés(tmp_path: Path):
    """La minuscule, le double collé, et une majorité de bulles ordinaires. Un corpus qui ne
    porterait que des ovales de taille moyenne validerait un détecteur qui échoue partout où
    ça compte."""
    corpus_synthetique.ecrire(tmp_path)
    corpus = mesure.charger_annotations(tmp_path)
    aires = [int(r.mask.sum()) for p in corpus.planches
             for r in mesure.regions_de_verite(p)]
    assert min(aires) < 2_000, "aucune bulle minuscule : le gain d'input_size ne se verrait pas"
    assert max(aires) > 40_000
    assert len(aires) == 22


def test_le_corpus_commite_est_celui_que_le_generateur_produit(tmp_path: Path):
    """Le corpus du dépôt et son générateur ne doivent pas diverger : sinon la ligne de base
    de la CI (`tests/corpus/synthetique/reference.json`) décrit un corpus que plus personne ne
    peut reproduire — et un banc irreproductible ne prouve rien."""
    commit = RACINE / "tests" / "corpus" / "synthetique" / "annotations.json"
    if not commit.exists():
        pytest.skip("corpus non matérialisé (python tools/corpus_synthetique.py)")
    attendu = corpus_synthetique.ecrire(tmp_path)
    assert json.loads(commit.read_text(encoding="utf-8")) == attendu, (
        "le corpus commité ne correspond plus à `tools/corpus_synthetique.py` — "
        "régénère-le (`python tools/corpus_synthetique.py`) et recalibre reference.json")


def test_la_licence_du_corpus_est_ecrite_dans_le_corpus(tmp_path: Path):
    """Un corpus dont la licence n'est pas dans le fichier n'est pas redistribuable en
    pratique — c'est la contrainte qui a écarté Manga109-s et les œuvres commerciales."""
    coco = corpus_synthetique.ecrire(tmp_path)
    assert "AGPL-3.0" in coco["info"]["licence"]
    assert mesure.charger_annotations(tmp_path).licence == corpus_synthetique.LICENCE
