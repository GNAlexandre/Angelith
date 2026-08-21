# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Détection RÉELLE des bulles (modèle ONNX YOLOv8-seg) sur une planche synthétique.
Sauté si onnxruntime ou le modèle téléchargé sont absents (voir manga_models/README.md)
— ces tests ne bloquent donc jamais un checkout frais sans les extras manga."""
from pathlib import Path

import pytest

pytest.importorskip("onnxruntime")

MODEL_PATH = Path(__file__).resolve().parent.parent / "manga_models" / "bubble_detector.onnx"
pytestmark = pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason="modèle de détection non téléchargé (voir manga_models/README.md)")


def test_detects_bubble_on_synthetic_page(synthetic_manga_page):
    from manga.detection import BubbleDetector

    img, bubble_box, _text = synthetic_manga_page
    det = BubbleDetector(str(MODEL_PATH))
    regions = det.detect(img)

    assert len(regions) >= 1
    best = max(regions, key=lambda r: r.score)
    x0, y0, x1, y1 = best.bbox
    bx0, by0, bx1, by1 = bubble_box
    # Le rectangle détecté doit chevaucher largement la bulle dessinée.
    inter_w = min(x1, bx1) - max(x0, bx0)
    inter_h = min(y1, by1) - max(y0, by0)
    assert inter_w > 0 and inter_h > 0
    assert best.mask.shape == (img.height, img.width)
    assert best.mask.any()


def test_une_inference_sert_a_PLUSIEURS_post_traitements(synthetic_manga_page):
    """LE fait qui rend un balayage de seuils presque gratuit : `conf_threshold` et
    `iou_threshold` ne servent qu'au post-traitement, le réseau ne les voit jamais.

    Douze réglages coûtent donc une inférence et douze post-traitements — sans quoi
    `tools/apercu_detection.py --balayage` serait inutilisable."""
    from manga.detection import BubbleDetector

    img, _box, _text = synthetic_manga_page
    det = BubbleDetector(str(MODEL_PATH))
    inference = det.inferer(img)
    par_seuil = {c: len(det.regions_de(inference, conf_threshold=c))
                 for c in (0.05, 0.35, 0.99)}
    # Monotone : un seuil plus haut ne peut pas rendre PLUS de régions.
    assert par_seuil[0.05] >= par_seuil[0.35] >= par_seuil[0.99]
    # …et une même inférence rejouée au même seuil donne exactement le même résultat.
    assert len(det.regions_de(inference, conf_threshold=0.35)) == par_seuil[0.35]


def test_les_seuils_PAR_APPEL_priment_sur_ceux_de_linstance(synthetic_manga_page):
    """C'est ce qui permet de relancer UNE planche sans reconstruire le détecteur — donc sans
    recharger 104 Mo de poids — ni toucher aux réglages du tome."""
    from manga.detection import BubbleDetector

    img, _box, _text = synthetic_manga_page
    det = BubbleDetector(str(MODEL_PATH), conf_threshold=0.35)
    assert det.detect(img, conf_threshold=0.99) == []
    assert det.conf_threshold == 0.35            # l'instance n'a pas bougé
    assert det.detect(img) != []


def test_detector_raises_clear_error_if_model_missing(tmp_path):
    """⚠ `telechargement_auto=False` est INDISPENSABLE ici : sans lui ce test irait chercher
    104 Mo sur Hugging Face à chaque exécution de la suite."""
    from manga.detection import BubbleDetector
    with pytest.raises(SystemExit):
        BubbleDetector(str(tmp_path / "absent.onnx"), telechargement_auto=False)
