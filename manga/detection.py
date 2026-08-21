# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Détection des bulles de dialogue (et, à terme, du texte posé sur le dessin —
onomatopées, phase 2) via un modèle ONNX de segmentation de type YOLOv8-seg.

Ce module ne fait que LIRE l'image (localiser les bulles + leur masque de texte) :
il n'écrit jamais de pixels. C'est `manga/clean.py` (remplissage déterministe du
masque) et `manga/typeset.py` (dessin du texte traduit) qui écrivent — jamais un
modèle génératif. Voir le principe directeur du plan de faisabilité.

Le modèle attendu est un export ONNX standard Ultralytics YOLOv8-seg (2 sorties :
`output0` = boîtes+scores+coefficients de masque, `output1` = « proto » des masques).
Ce format est celui de poids publics comme `kitsumed/yolov8m_seg-speech-bubble`
(Hugging Face) — voir `manga_models/README.md` pour le lien de téléchargement.
Tourne sur CPU par défaut ; `providers=["DmlExecutionProvider", "CPUExecutionProvider"]`
active l'accélération GPU sur AMD/Windows via DirectML (`onnxruntime-directml`)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

INPUT_SIZE = 640          # résolution d'entraînement standard YOLOv8-seg
CONF_THRESHOLD = 0.35
IOU_THRESHOLD = 0.45
MASK_THRESHOLD = 0.5


@dataclass
class BubbleRegion:
    bbox: tuple[int, int, int, int]   # (x0, y0, x1, y1) en pixels image d'origine
    mask: np.ndarray                   # bool, taille = image d'origine (H, W)
    score: float
    cls: int
    kind: str = "bulle"                # réservé phase 2 : "onomatopee" (texte sur dessin)
    # Vraie quand cette région est un LOBE issu d'une région bi-lobée découpée
    # (`manga/bubbles_split.py`). Persistée dans `regions.json`, donc encore lisible après un
    # `--from rendu` : c'est ce qui permet à `RAPPORT.md` de décrire le tome et non le run.
    scindee: bool = False


@dataclass
class Inference:
    """Sortie BRUTE du réseau pour une planche, avec ce qu'il faut pour défaire le letterbox.

    Séparer l'inférence du post-traitement est ce qui rend un balayage de seuils presque
    gratuit : les seuils n'interviennent qu'après le réseau."""
    out0: np.ndarray
    proto: np.ndarray
    r: float
    dw: float
    dh: float
    w0: int
    h0: int


class BubbleDetector:
    """Enveloppe ONNX Runtime autour d'un modèle YOLOv8-seg de détection de bulles."""

    def __init__(self, model_path: str, providers: list[str] | None = None,
                 conf_threshold: float = CONF_THRESHOLD, iou_threshold: float = IOU_THRESHOLD,
                 *, telechargement_auto: bool = True, model_url: str | None = None, dire=None):
        import onnxruntime as ort

        from . import models
        # Le modèle se télécharge tout seul s'il manque, comme le fait déjà `manga-ocr` pour le
        # sien. Un fichier de 104 Mo absent du dépôt (il est dans `.gitignore`) ne doit pas
        # arrêter un tome de 150 planches sur une consigne à recopier à la main.
        model_path = models.assurer_detecteur(
            model_path, url=model_url or models.DETECTEUR_URL,
            auto=telechargement_auto, dire=dire)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        avail = ort.get_available_providers()
        wanted = providers or ["CPUExecutionProvider"]
        used = [p for p in wanted if p in avail] or ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(model_path), providers=used)
        self._input_name = self.session.get_inputs()[0].name

    def inferer(self, image: Image.Image) -> Inference:
        """Passe ONNX seule, SANS post-traitement — la partie chère, et la seule.

        `conf_threshold` et `iou_threshold` ne servent qu'au filtrage et au NMS : le réseau,
        lui, ne les voit jamais. Les séparer rend un **balayage de seuils** presque gratuit —
        une inférence, dix post-traitements — ce qui est tout l'intérêt de
        `tools/apercu_detection.py` : essayer douze réglages sur une planche coûte le prix
        d'un seul passage du modèle."""
        w0, h0 = image.size
        tensor, r, (dw, dh) = _letterbox(image, INPUT_SIZE)
        out0, proto = self.session.run(None, {self._input_name: tensor})[:2]
        return Inference(out0=out0, proto=proto, r=r, dw=dw, dh=dh, w0=w0, h0=h0)

    def regions_de(self, inference: Inference, *, conf_threshold: float | None = None,
                   iou_threshold: float | None = None) -> list[BubbleRegion]:
        """Post-traite une inférence déjà calculée, aux seuils demandés."""
        return _postprocess(
            inference.out0, inference.proto, inference.r, inference.dw, inference.dh,
            inference.w0, inference.h0,
            self.conf_threshold if conf_threshold is None else float(conf_threshold),
            self.iou_threshold if iou_threshold is None else float(iou_threshold))

    def detect(self, image: Image.Image, *, conf_threshold: float | None = None,
               iou_threshold: float | None = None) -> list[BubbleRegion]:
        """Détecte les bulles d'une planche. `image` = PIL.Image RGB.

        Les seuils par appel priment sur ceux de l'instance : c'est ce qui permet de relancer
        UNE planche à d'autres réglages sans reconstruire le détecteur — donc sans recharger
        104 Mo de poids — ni toucher aux réglages du tome."""
        return self.regions_de(self.inferer(image), conf_threshold=conf_threshold,
                               iou_threshold=iou_threshold)


def _letterbox(image: Image.Image, size: int):
    """Redimensionne en conservant le ratio + complète en gris (114,114,114) pour
    obtenir une entrée carrée `size x size`, comme à l'entraînement Ultralytics.
    Renvoie (tenseur NCHW float32 normalisé, ratio r, (padding_x, padding_y))."""
    w0, h0 = image.size
    r = min(size / w0, size / h0)
    new_w, new_h = round(w0 * r), round(h0 * r)
    resized = image.convert("RGB").resize((new_w, new_h), Image.BILINEAR)
    dw, dh = (size - new_w) / 2, (size - new_h) / 2
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    canvas.paste(resized, (round(dw), round(dh)))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    tensor = arr.transpose(2, 0, 1)[None, ...]   # HWC → NCHW
    return np.ascontiguousarray(tensor), r, (dw, dh)


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """NMS classique en numpy pur (pas de dépendance à OpenCV)."""
    x0, y0, x1, y1 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0, x1 - x0) * np.maximum(0, y1 - y0)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx0 = np.maximum(x0[i], x0[order[1:]])
        yy0 = np.maximum(y0[i], y0[order[1:]])
        xx1 = np.minimum(x1[i], x1[order[1:]])
        yy1 = np.minimum(y1[i], y1[order[1:]])
        inter = np.maximum(0, xx1 - xx0) * np.maximum(0, yy1 - yy0)
        iou = inter / np.maximum(1e-9, areas[i] + areas[order[1:]] - inter)
        order = order[1:][iou <= iou_threshold]
    return keep


def _postprocess(out0: np.ndarray, proto: np.ndarray, r: float, dw: float, dh: float,
                  w0: int, h0: int, conf_threshold: float, iou_threshold: float,
                  ) -> list[BubbleRegion]:
    # out0 : (1, 4+nc+nm, N) → (N, 4+nc+nm). nm = nb de coefficients de masque (32,
    # standard Ultralytics) ; nc déduit du nombre de canaux restants (peu importe le
    # nombre de classes réel du modèle téléchargé).
    pred = out0[0].T
    nm = proto.shape[1]                 # ex. 32
    nc = pred.shape[1] - 4 - nm
    boxes_cxcywh = pred[:, :4]
    cls_scores = pred[:, 4:4 + nc]
    mask_coeffs = pred[:, 4 + nc:4 + nc + nm]
    scores = cls_scores.max(axis=1)
    classes = cls_scores.argmax(axis=1)

    keep_conf = scores >= conf_threshold
    if not keep_conf.any():
        return []
    boxes_cxcywh = boxes_cxcywh[keep_conf]
    scores, classes, mask_coeffs = scores[keep_conf], classes[keep_conf], mask_coeffs[keep_conf]

    cx, cy, bw, bh = boxes_cxcywh[:, 0], boxes_cxcywh[:, 1], boxes_cxcywh[:, 2], boxes_cxcywh[:, 3]
    boxes_xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)

    keep_idx = _nms(boxes_xyxy, scores, iou_threshold)
    if not keep_idx:
        return []

    _, mh, mw = proto.shape[1], proto.shape[2], proto.shape[3]  # noqa (lisibilité)
    proto_flat = proto[0].reshape(proto.shape[1], -1)           # (nm, mh*mw)

    regions: list[BubbleRegion] = []
    for i in keep_idx:
        bx0, by0, bx1, by1 = boxes_xyxy[i]
        # Undo letterbox → coordonnées de l'image d'origine.
        ox0 = max(0, min(w0, (bx0 - dw) / r))
        oy0 = max(0, min(h0, (by0 - dh) / r))
        ox1 = max(0, min(w0, (bx1 - dw) / r))
        oy1 = max(0, min(h0, (by1 - dh) / r))
        if ox1 - ox0 < 2 or oy1 - oy0 < 2:
            continue

        # Masque : combinaison linéaire des prototypes, sigmoïde, reshape (mh, mw).
        coeffs = mask_coeffs[i]
        m = 1.0 / (1.0 + np.exp(-(coeffs @ proto_flat)))
        m = m.reshape(proto.shape[2], proto.shape[3])
        m_img = Image.fromarray((m * 255).astype(np.uint8)).resize(
            (INPUT_SIZE, INPUT_SIZE), Image.BILINEAR)
        # Retire le padding du letterbox, puis remet à l'échelle de l'image d'origine.
        crop_box = (round(dw), round(dh), INPUT_SIZE - round(dw), INPUT_SIZE - round(dh))
        m_crop = m_img.crop(crop_box).resize((w0, h0), Image.BILINEAR)
        mask_full = np.asarray(m_crop) >= (MASK_THRESHOLD * 255)

        # Sécurité supplémentaire : masque hors bbox mis à zéro (évite toute fuite de
        # texture au-delà de la zone détectée en cas de masque bruité).
        bbox_mask = np.zeros_like(mask_full)
        bbox_mask[int(oy0):int(oy1), int(ox0):int(ox1)] = True
        mask_full &= bbox_mask

        regions.append(BubbleRegion(
            bbox=(int(ox0), int(oy0), int(ox1), int(oy1)),
            mask=mask_full, score=float(scores[i]), cls=int(classes[i]),
        ))
    return regions
