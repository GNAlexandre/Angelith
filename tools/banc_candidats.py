#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc des détecteurs CANDIDATS — mesurer une alternative AVANT de l'adopter (lot 16).

    # Rappel / précision / F1 sur le corpus annoté, à armes égales
    python tools/banc_candidats.py --corpus tests/corpus/synthetique --input-size 1024

    # Le webtoon, planche par planche, avec l'OCR du projet
    python tools/banc_candidats.py "webtoon A" Chap.11 --ocr --markdown

    # Les planches à ZÉRO bulle des dix volumes — le régime de l'escalade
    python tools/banc_candidats.py --tous --sur-zero --markdown

Les poids candidats se déclarent à la ligne de commande, jamais en dur :

    --actuel                       le détecteur du dépôt, tel que `config.yaml` le construit
    --yolo   CHEMIN.onnx  [NOM]    un export ONNX YOLOv8 **detect** (boîtes seules)
    --rtdetr CHEMIN.onnx  [NOM]    un export ONNX RT-DETR-v2 « deploy » (labels/boxes/scores)

## Pourquoi un banc à part, et pas une colonne de plus dans `tools/banc.py`

`tools/banc.py` lit le **cache** : il ne charge aucun modèle, ne réécrit rien, et se lance
pendant qu'un run tourne. C'est sa discipline et elle vaut d'être gardée. Mesurer un détecteur
qui n'a jamais tourné sur le corpus demande exactement le contraire : charger des poids et
détecter 1 513 planches. Les deux ne tiennent pas dans le même outil sans mentir sur l'un des
deux contrats.

## Ce que cet outil compare, et ce qu'il ne compare pas

Il compare **des détecteurs**, sur les indicateurs que le banc publie déjà :

- le nombre de bulles, et sa distribution par planche ;
- les planches à **zéro bulle** — la métrique qui décide (cf. `docs/procedures/banc-de-mesure.md`) ;
- les **bulles sans texte OCR**, quand `--ocr` est passé : c'est le meilleur substitut
  mesurable des « zones restaurées », et il est mesuré sur le corpus, pas supposé. Vérifié sur
  le cache du webtoon de référence : **11 zones restaurées** pour **12 bulles sans texte OCR**
  sur 59 — les deux indicateurs se suivent à une unité près, parce qu'une bulle dont l'OCR ne
  tire rien n'a pas de réplique, donc voit son dessin recollé. ⚠ Vrai sur une source **latine**
  seulement : cf. `COUVERTURE_TEXTE_MIN` et l'option `--texte` ;
- les régions que le nettoyage **refuserait** (uniformité < `nettoyage.seuil_abandon`), par
  `detection_retry.arbitrer` — l'arbitre du dépôt, pas un second critère qui divergerait.

Il ne compare **pas** des rendus : personne ne relance dix volumes pour choisir un détecteur.

⚠ **Il n'écrit rien sous `build/`.** Aucun checkpoint n'est touché, aucun cache invalidé : le
tableau sort sur la sortie standard, comme celui de `tools/banc.py`.

## La réserve la plus importante : boîtes contre masques

Le détecteur en place est un YOLOv8-**seg** : il rend un masque par bulle, et tout l'aval en
dépend — `clean.py` peint le masque, `psd.py` en fait un calque, `bubbles_split.py` le scinde.
Les deux candidats Apache-2.0 rendent des **boîtes**. La question n'est donc pas « lequel
détecte mieux » mais celle que pose le plan du lot 16 :

> une boîte proposée là où le détecteur principal ne voit rien, plus un masque dérivé par
> remplissage depuis l'intérieur, vaut-elle une bulle ?

`masque_par_remplissage` dérive ce masque, et la colonne **IoU masque** mesure ce qu'il vaut
face au masque du réseau, sur les bulles que le candidat et la référence voient au même endroit.
C'est un chiffre à publier avant toute intégration, pas après. Mesuré sur le webtoon de
référence : **0,88–0,89**, contre 0,99 pour le détecteur en place contre son propre cache. Assez
pour un second avis, pas pour un remplacement.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from core.cli import charger_config, configurer_stdout        # noqa: E402
from manga import checkpoints, clean, detection               # noqa: E402
from manga.detection import BubbleDetector, BubbleRegion      # noqa: E402
from manga.detection_retry import apparier, arbitrer, iou_masques   # noqa: E402
from manga.geometry import composantes                        # noqa: E402
from tools import _banc_commun as banc                        # noqa: E402
from tools import banc as banc_cache                          # noqa: E402

#: Familles d'export ONNX que ce banc sait interroger. Le nom est celui du format de SORTIE,
#: pas celui du dépôt amont : c'est la sortie qui décide du post-traitement.
FAMILLES = ("yoloseg", "yolo", "rtdetr")

#: Tolérance de luminance du remplissage, en niveaux de gris (0-255).
#:
#: C'est `nettoyage.seuil_texte` (45) et pas `clean._TOL_UNIFORMITE` (25) : on cherche
#: l'étendue du FOND de la bulle, et le seuil qui sépare le fond du texte est précisément
#: celui-là. Le prendre plus serré ferait fuir le remplissage dans le trait de contour ;
#: le prendre plus large le ferait déborder dans le dessin par la queue de la bulle.
TOLERANCE_REMPLISSAGE = 45

#: Nombre de classes de bulle retenues par défaut pour un candidat multi-classe. `rtdetr`
#: distingue `bubble` (0), `text_bubble` (1) et `text_free` (2) : seule la première décrit un
#: BALLON, les deux autres décrivent du texte et relèvent de `manga/text_detection.py`.
CLASSES_BULLE_RTDETR = (0,)

#: Langue inférée par `tools/banc.py` → code de langue attendu par `manga/ocr_routeur.py`.
#: Le banc de cache infère `cjk` / `latin` de l'OCR déjà en place ; le routeur, lui, attend un
#: code ISO. Les deux vocabulaires existaient déjà, cette table est la seule à les joindre.
LANGUES_OCR = {"cjk": "jp", "latin": "en"}

#: Couverture de texte, en fraction du masque de la bulle, au-dessus de laquelle la bulle
#: **porte quelque chose**. Mesurée par le détecteur de TEXTE (`manga/text_detection.py`),
#: c'est-à-dire par un modèle étranger au chemin d'OCR.
#:
#: 1 % vient du relevé du lot 14 (`docs/mesures/webtoon-2026-08-26.md` § 7), qui a interrogé ce même
#: détecteur sur un crop de chaque bulle : les muettes couvrent **0,00 %, 0,00 % et 0,41 %**
#: de leur masque, les témoins lus **3,70 % et 4,08 %**. Le creux est large, et 1 % tombe
#: dedans. Échantillon de 3 contre 2 : cela oriente, cela ne démontre pas — d'où une colonne
#: publiée à côté de `sans OCR`, et non à sa place.
#:
#: ⚠ **Cette colonne existe parce que `sans OCR` ne suffit pas sur du japonais.** `manga-ocr`
#: est un modèle génératif de dialogue : il rend rarement une chaîne vide, même sur du dessin.
#: Sur les neuf volumes paginés, `tools/banc.py` compte d'ailleurs **0 bulle sans texte OCR** —
#: ce qui ne prouve pas qu'il n'y a aucune fausse détection, seulement qu'aucune ne s'est
#: trahie par un silence.
COUVERTURE_TEXTE_MIN = 0.01

COLONNES = [
    "détecteur", "input", "volume", "régime", "langue", "planches", "bulles", "médiane b/pl",
    "0 bulle", "0 bulle réf", "récupérées", "gagnées/cache", "perdues/cache",
    "non nettoyables",
    "sans OCR", "sans texte", "IoU masque", "s/planche",
]


# ---------------------------------------------------------------------------
# Dériver un masque d'une BOÎTE
# ---------------------------------------------------------------------------

def _luma(arr: np.ndarray) -> np.ndarray:
    """Luminance ITU-R 601, la même que `clean._luma`. Sur un tableau HWC, rend un HW."""
    return arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114


def _boucher_trous(masque: np.ndarray) -> np.ndarray:
    """Rebouche les trous d'un masque : tout ce qui n'est ni le masque, ni relié au bord.

    Les trous d'une bulle remplie depuis l'intérieur sont **le texte**, c'est-à-dire
    exactement ce que le nettoyage doit couvrir. Un masque troué ferait dire à
    `clean.analyze_bubble` que l'intérieur est uniforme parce qu'on lui aurait retiré tout ce
    qui ne l'est pas — l'uniformité mesurée ne voudrait plus rien dire."""
    dehors = ~masque
    plein = masque.copy()
    for comp in composantes(dehors):
        if (comp[0, :].any() or comp[-1, :].any()
                or comp[:, 0].any() or comp[:, -1].any()):
            continue
        plein |= comp
    return plein


def masque_par_remplissage(image: Image.Image, bbox: tuple[int, int, int, int], *,
                           tolerance: int = TOLERANCE_REMPLISSAGE) -> np.ndarray | None:
    """Masque booléen PLEINE PAGE dérivé d'une boîte, par remplissage depuis l'intérieur.

    C'est la pièce que le plan du lot 16 met en jeu : un candidat qui ne rend que des boîtes ne
    peut entrer dans ce pipeline qu'à condition qu'on sache en tirer un masque, et le juge est
    déjà là — `clean.analyze_bubble` refuse une région dont l'intérieur n'est pas uniforme.

    Quatre étapes, et chacune répond à un piège mesuré :

    1. **La couleur de fond est la classe MODALE de la luminance du quart central**, comme
       `clean._couleur_de_fond`. Une médiane dériverait vers le texte dès qu'une bulle est
       dense en caractères, et un percentile haut renverrait la couleur du texte sur une bulle
       inversée.
    2. **Le remplissage part du centre de la boîte**, pas de sa plus grande composante : sur
       une boîte qui mord sur une case voisine claire, la plus grande région uniforme peut
       être le décor.
    3. **Les trous sont rebouchés** (cf. `_boucher_trous`), sinon l'uniformité mesurée ensuite
       serait celle d'un masque dont on a retiré tout ce qui n'est pas uniforme.
    4. **Le résultat est borné à la boîte**, comme `detection._postprocess` le fait déjà pour
       les masques du réseau.

    Rend `None` quand la boîte est trop petite pour être remplie ou que le remplissage ne
    trouve rien — jamais un masque vide, qui se lirait comme une bulle dégénérée."""
    x0, y0, x1, y1 = (int(v) for v in bbox)
    largeur, hauteur = image.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(largeur, x1), min(hauteur, y1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    sous = _luma(np.asarray(image.convert("RGB"), dtype=np.float32)[y0:y1, x0:x1])
    h, w = sous.shape
    cy0, cy1, cx0, cx1 = h // 4, h - h // 4, w // 4, w - w // 4
    centre = sous[cy0:cy1, cx0:cx1]
    if centre.size == 0:
        centre = sous
    hist, bords = np.histogram(centre, bins=32, range=(0.0, 255.0))
    i = int(hist.argmax())
    fond = (bords[i] + bords[i + 1]) / 2.0

    proche = np.abs(sous - fond) <= tolerance
    if not proche.any():
        return None
    # ⚠ Le QUART CENTRAL, et surtout pas le pixel central. Sur une bulle dense en texte, le
    # pixel du milieu tombe une fois sur deux DANS une lettre — le remplissage n'y trouve
    # alors aucune composante et la bulle est perdue. Mesuré : la planche de test du dépôt
    # met une ligne de texte pile au centre, et c'est le cas le plus courant, pas un cas
    # tordu. On retient donc la composante qui couvre le mieux le quart central.
    interieur = np.zeros_like(proche)
    interieur[cy0:cy1, cx0:cx1] = True
    retenue, meilleure = None, 0
    for comp in composantes(proche):
        recouvrement = int(np.count_nonzero(comp & interieur))
        if recouvrement > meilleure:
            retenue, meilleure = comp, recouvrement
    if retenue is None:
        return None
    retenue = _boucher_trous(retenue)

    masque = np.zeros((hauteur, largeur), dtype=bool)
    masque[y0:y1, x0:x1] = retenue
    return masque if masque.any() else None


# ---------------------------------------------------------------------------
# Les détecteurs candidats
# ---------------------------------------------------------------------------

@dataclass
class Poids:
    """Un jeu de poids à mesurer : ce qu'il est, d'où il vient, et sous quelle licence."""

    nom: str
    famille: str
    chemin: Path | None = None
    licence: str = "(non déclarée)"
    classes_bulle: tuple[int, ...] | None = None


class Candidat:
    """Un détecteur alternatif réduit au seul contrat dont le banc a besoin : une image, des
    `BubbleRegion`.

    ⚠ **Le fenêtrage et le dédoublonnage sont ceux du pipeline** — `detection.fenetres` et
    `detection.assembler_fenetres`. Un candidat mesuré avec un autre découpage ne serait pas
    comparable au détecteur en place, et l'écart mesuré serait celui des deux découpages."""

    def __init__(self, poids: Poids, det_cfg: dict, *, input_size: int,
                 conf_threshold: float, iou_threshold: float):
        import onnxruntime as ort

        self.poids = poids
        self.input_size = detection.normaliser_input_size(input_size)
        self.conf_threshold = float(conf_threshold)
        self.iou_threshold = float(iou_threshold)
        self.fenetrage = dict(det_cfg)
        avail = ort.get_available_providers()
        wanted = det_cfg.get("providers") or ["CPUExecutionProvider"]
        used = [p for p in wanted if p in avail] or ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(poids.chemin), providers=used)
        self._entrees = [e.name for e in self.session.get_inputs()]
        detection.verifier_axe_dynamique(
            self.session.get_inputs()[0].shape, self.input_size, poids.chemin)

    # -- l'inférence, une vue à la fois ------------------------------------

    def _boites_yolo(self, image: Image.Image) -> list[tuple[tuple, float, int]]:
        """Export Ultralytics YOLOv8 **detect** : une sortie `(1, 4 + nc, N)`, boîtes en
        `cxcywh` dans le canevas letterboxé. Même préparation et même NMS que
        `detection._postprocess`, moins les masques — qui n'existent pas ici."""
        tensor, r, (dw, dh) = detection._letterbox(image, self.input_size)
        pred = self.session.run(None, {self._entrees[0]: tensor})[0][0].T
        nc = pred.shape[1] - 4
        scores = pred[:, 4:4 + nc].max(axis=1)
        classes = pred[:, 4:4 + nc].argmax(axis=1)
        garde = scores >= self.conf_threshold
        if not garde.any():
            return []
        boites, scores, classes = pred[garde][:, :4], scores[garde], classes[garde]
        cx, cy, bw, bh = boites[:, 0], boites[:, 1], boites[:, 2], boites[:, 3]
        xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
        w0, h0 = image.size
        sorties = []
        for i in detection._nms(xyxy, scores, self.iou_threshold):
            bx0, by0, bx1, by1 = xyxy[i]
            sorties.append(((max(0.0, min(w0, (bx0 - dw) / r)),
                             max(0.0, min(h0, (by0 - dh) / r)),
                             max(0.0, min(w0, (bx1 - dw) / r)),
                             max(0.0, min(h0, (by1 - dh) / r))),
                            float(scores[i]), int(classes[i])))
        return sorties

    def _boites_rtdetr(self, image: Image.Image) -> list[tuple[tuple, float, int]]:
        """Export RT-DETR-v2 « deploy » : `images` + `orig_target_sizes`, sorties
        `labels` / `boxes` / `scores`, boîtes DÉJÀ ramenées aux coordonnées de l'image.

        ⚠ Trois écarts avec YOLO, tous vérifiés sur le fichier livré :
        `preprocessor_config.json` dit `do_normalize: false` (rescale seul, pas de
        moyenne/écart-type), `do_pad: false` et un redimensionnement **plein cadre** — pas de
        letterbox. C'est cohérent avec la fiche du modèle : « Training Images were resized,
        not cropped ». Lui appliquer le letterbox d'Ultralytics changerait sa distribution
        d'entrée et mesurerait autre chose que le modèle publié.

        `orig_target_sizes` est en `(largeur, hauteur)` — l'ordre de l'export du dépôt RT-DETR,
        et non celui de `RTDetrImageProcessor` de `transformers`, qui attend `(h, w)`. Vérifié
        contre le cache : les boîtes rendues coïncident au pixel près avec celles du détecteur
        en place sur une planche que les deux voient pareil."""
        w0, h0 = image.size
        vue = image.convert("RGB").resize((self.input_size, self.input_size), Image.BILINEAR)
        tensor = np.ascontiguousarray(
            (np.asarray(vue, dtype=np.float32) / 255.0).transpose(2, 0, 1)[None, ...])
        labels, boites, scores = self.session.run(
            None, {self._entrees[0]: tensor,
                   self._entrees[1]: np.array([[w0, h0]], dtype=np.int64)})
        labels, boites, scores = labels[0], boites[0], scores[0]
        garde = scores >= self.conf_threshold
        return [(tuple(float(v) for v in b), float(s), int(c))
                for b, s, c in zip(boites[garde], scores[garde], labels[garde])]

    def _boites(self, image: Image.Image) -> list[tuple[tuple, float, int]]:
        brut = (self._boites_rtdetr(image) if self.poids.famille == "rtdetr"
                else self._boites_yolo(image))
        classes = self.poids.classes_bulle
        return [b for b in brut if classes is None or b[2] in classes]

    def _regions_dune_vue(self, image: Image.Image) -> list[BubbleRegion]:
        regions = []
        for (x0, y0, x1, y1), score, cls in self._boites(image):
            bbox = (int(x0), int(y0), int(x1), int(y1))
            masque = masque_par_remplissage(image, bbox)
            if masque is None:
                continue
            regions.append(BubbleRegion(bbox=bbox, mask=masque, score=score, cls=cls))
        return regions

    def detect(self, image: Image.Image) -> list[BubbleRegion]:
        """Les bulles d'une planche, fenêtrées comme le pipeline les fenêtre."""
        largeur, hauteur = image.size
        bandes = detection.fenetres(largeur, hauteur, self.fenetrage,
                                    input_size=self.input_size)
        if not bandes:
            return self._regions_dune_vue(image)
        par_fenetre = [(self._regions_dune_vue(image.crop((0, y0, largeur, y1))), y0, y1)
                       for y0, y1 in bandes]
        return detection.assembler_fenetres(par_fenetre, hauteur, self.iou_threshold)


def finaliser(brutes: list[BubbleRegion], det_cfg: dict) -> list[BubbleRegion]:
    """Détections BRUTES → régions telles que le pipeline les ÉCRIRAIT : scission des régions
    bi-lobées, puis masques rendus disjoints.

    ⚠ **Sans cette étape, aucune colonne n'est comparable à celle de `tools/banc.py`.** Le
    cache ne porte pas la sortie du réseau, il porte la sortie de `_fabriquer_regions` : sur les
    9 bandes du webtoon de référence, `regions.json` compte 59 bulles dont **6 sont des lobes**
    issus de la scission. Un candidat mesuré sans elle afficherait mécaniquement moins de bulles
    que le détecteur en place, et l'écart serait celui du post-traitement, pas des poids.

    C'est le même argument que l'escalade du lot 12 : « comparer un jeu scindé et disjoint à un
    jeu brut ferait dire à l'arbitre n'importe quoi »."""
    from manga import bubbles_split
    from manga import document as doc_mod
    scindees, _diag = bubbles_split.scinder_regions(brutes, det_cfg.get("scission") or {})
    disjointes, _origines = doc_mod.rendre_disjoints(sorted(scindees, key=lambda r: -r.score))
    return disjointes


def fabriquer(poids: Poids, config: dict, *, input_size: int):
    """`(image) -> list[BubbleRegion]`, pour n'importe quelle famille.

    La famille `yoloseg` passe par `BubbleDetector.depuis_config` — **le détecteur du
    pipeline**, avec ses seuils, son fenêtrage et son aire minimale. Mesurer le détecteur en
    place autrement que le pipeline ne le construit reviendrait à comparer un candidat à un
    troisième détecteur qui n'existe nulle part."""
    det_cfg = dict(config["manga"]["detection"])
    det_cfg["input_size"] = int(input_size)
    if poids.chemin is not None:
        det_cfg["model_path"] = str(poids.chemin)
    if poids.famille == "yoloseg":
        detecteur = BubbleDetector.depuis_config(det_cfg)
        def _detecter(image):
            return detecteur.regions_de_fenetres(
                detecteur.inferer_fenetres(image), image.size[1])
    else:
        candidat = Candidat(
            poids, det_cfg, input_size=input_size,
            conf_threshold=float(det_cfg.get("conf_threshold", detection.CONF_THRESHOLD)),
            iou_threshold=float(det_cfg.get("iou_threshold", detection.IOU_THRESHOLD)))
        _detecter = candidat.detect
    return lambda image: finaliser(_detecter(image), det_cfg)


# ---------------------------------------------------------------------------
# La mesure
# ---------------------------------------------------------------------------

@dataclass
class MesurePlanche:
    """Ce qu'un détecteur a fait d'UNE planche, face au cache en place."""

    numero: int
    bulles: int = 0
    reference: int = 0
    gagnees: int = 0
    perdues: int = 0
    non_nettoyables: int = 0
    sans_ocr: int | None = None
    sans_texte: int | None = None
    ious: list[float] = field(default_factory=list)
    secondes: float = 0.0


def _uniformites(image: Image.Image, regions: list[BubbleRegion],
                 cfg_nettoyage: dict) -> dict[int, float]:
    """Uniformité de chaque région, par `clean.analyze_bubble` — le juge du dépôt.

    Injectée dans `detection_retry.arbitrer`, qui reste sans image et sans E/S."""
    return {i: clean.analyze_bubble(image, r, cfg_nettoyage).uniformity
            for i, r in enumerate(regions)}


def couverture_de_texte(image: Image.Image, region: BubbleRegion, detecteur_texte) -> float:
    """Fraction du masque de `region` que le détecteur de TEXTE marque comme du texte.

    Interrogé sur un **crop de la boîte** et non sur la planche entière : c'est le protocole du
    lot 14 (§ 7), et il tient à une contrainte du modèle — `comic-text-detector` reçoit un carré
    de 1 024 px, si bien qu'une bulle de 400 px dans une bande de 10 000 arrive au réseau à
    41 px de haut et n'y est plus rien."""
    x0, y0, x1, y1 = region.bbox
    if x1 - x0 < 2 or y1 - y0 < 2:
        return 0.0
    masque_texte = detecteur_texte.masque_texte(image.crop(region.bbox))
    dans_la_bulle = region.mask[y0:y1, x0:x1]
    aire = int(dans_la_bulle.sum())
    if not aire:
        return 0.0
    hauteur = min(masque_texte.shape[0], dans_la_bulle.shape[0])
    largeur = min(masque_texte.shape[1], dans_la_bulle.shape[1])
    croise = masque_texte[:hauteur, :largeur] & dans_la_bulle[:hauteur, :largeur]
    return int(croise.sum()) / aire


def mesurer_planche(image: Image.Image, predites: list[BubbleRegion],
                    reference: list[BubbleRegion], cfg_nettoyage: dict, *,
                    numero: int, lecteur=None, cfg_ocr: dict | None = None,
                    detecteur_texte=None, seuil_abandon: float = 0.35) -> MesurePlanche:
    """Le verdict d'une planche, avec l'arbitre et l'OCR du dépôt, jamais un critère neuf."""
    unis = _uniformites(image, predites, cfg_nettoyage)
    verdict = arbitrer(reference, predites, unis,
                       seuil_abandon=seuil_abandon,
                       uniformites_reference=_uniformites(image, reference, cfg_nettoyage)
                       if reference else None)
    mesure = MesurePlanche(
        numero=numero, bulles=len(predites), reference=len(reference),
        gagnees=len(verdict.gagnees), perdues=len(verdict.perdues),
        non_nettoyables=sum(1 for u in unis.values() if u < seuil_abandon))
    # IoU du masque DÉRIVÉ contre celui du réseau, sur les seules bulles que les deux voient
    # au même endroit : c'est le chiffre qui dit si une boîte remplie vaut un masque.
    for i, j in enumerate(apparier(reference, predites)):
        if j is not None and reference[i].mask is not None and predites[j].mask is not None:
            mesure.ious.append(iou_masques(reference[i].mask, predites[j].mask))
    if lecteur is not None:
        styles = [clean.analyze_bubble(image, r, cfg_nettoyage) for r in predites]
        textes = lecteur.read_all(image, predites, styles, cfg_ocr or {})
        mesure.sans_ocr = sum(1 for t in textes if not (t or "").strip())
    if detecteur_texte is not None:
        mesure.sans_texte = sum(
            1 for r in predites
            if couverture_de_texte(image, r, detecteur_texte) < COUVERTURE_TEXTE_MIN)
    return mesure


def mesurer_volume(volume, poids: Poids, config: dict, *, input_size: int,
                   sur_zero: bool = False, ocr: bool = False, texte: bool = False,
                   limite: int | None = None, dire=None) -> dict:
    """Un détecteur, un volume. Rend une ligne de tableau plus le détail par planche."""
    predire = fabriquer(poids, config, input_size=input_size)
    cfg_nettoyage = config["manga"].get("nettoyage") or {}
    seuil_abandon = float(cfg_nettoyage.get("seuil_abandon", 0.35))
    sources = banc.planches_sources(volume, config)
    regime, langue = profil_du_volume(volume)
    lecteur, cfg_ocr = None, config["manga"].get("ocr") or {}
    detecteur_texte = None
    if texte:
        from manga.text_detection import TextDetector
        detecteur_texte = TextDetector.depuis_config(
            config["manga"].get("onomatopees") or {}, config["manga"]["detection"])
    mesures: list[MesurePlanche] = []
    for planche in banc.planches(volume):
        chemin = sources.get(planche.numero)
        if chemin is None or not chemin.exists():
            continue
        if sur_zero and planche.bulles:
            continue
        if limite is not None and len(mesures) >= limite:
            break
        reference = banc.charger_regions(
            checkpoints.page_checkpoint_dir(volume.build_dir, planche.numero)) or []
        with Image.open(chemin) as brut:
            image = brut.convert("RGB")
        depart = time.perf_counter()
        predites = predire(image)
        duree = time.perf_counter() - depart
        if ocr and lecteur is None and predites:
            from manga import ocr_routeur
            lecteur = ocr_routeur.lecteur_pour(LANGUES_OCR.get(langue, "jp"), cfg_ocr)
        mesure = mesurer_planche(
            image, predites, reference, cfg_nettoyage, numero=planche.numero,
            lecteur=lecteur if ocr else None, cfg_ocr=cfg_ocr,
            detecteur_texte=detecteur_texte, seuil_abandon=seuil_abandon)
        mesure.secondes = duree
        mesures.append(mesure)
        if dire is not None:
            dire(f"  {volume.nom} p{planche.numero:>4} · {poids.nom} : "
                 f"{mesure.bulles} bulle(s) (réf {mesure.reference}) · {duree:.1f} s")
    return {"volume": volume.nom, "poids": poids, "input": input_size, "régime": regime,
            "langue": langue, "planches": mesures,
            "ligne": agreger(volume, poids, input_size, mesures,
                             regime=regime, langue=langue)}


def profil_du_volume(volume) -> tuple[str, str]:
    """`(régime, langue source)` d'un tome, lus dans le cache par les fonctions de
    `tools/banc.py`.

    ⚠ **La langue est indispensable, et le banc de mesure dit pourquoi** : le seul volume
    webtoon du corpus est aussi le seul à source latine. Un candidat mesuré sans elle
    confondrait un effet de FORMAT avec un effet d'OCR — c'est la réserve que le plan du
    lot 16 impose de lever avant de conclure quoi que ce soit sur le détecteur."""
    tailles, sens, textes = set(), None, []
    for planche in banc.planches(volume):
        if planche.image_size:
            tailles.add(tuple(planche.image_size))
        sens = sens or planche.sens
        for entree in (planche.ocr or []):
            textes.append(entree.get("texte", "") if isinstance(entree, dict) else str(entree))
    return banc_cache._regime(tailles, sens), banc_cache._langue_source(textes)


def agreger(volume, poids: Poids, input_size: int, mesures: list[MesurePlanche], *,
            regime: str = "—", langue: str = "—") -> dict:
    """La ligne du tableau. Les indicateurs de fausse détection sont À CÔTÉ du compte de
    bulles et non trois colonnes plus loin — même ordre que `tools/banc.py`, pour la même
    raison : un lot qui gagne des bulles sans publier ses faux positifs affiche un succès."""
    import statistics
    bulles = [m.bulles for m in mesures]
    ious = [v for m in mesures for v in m.ious]
    sans_ocr = [m.sans_ocr for m in mesures if m.sans_ocr is not None]
    zero_ref = [m for m in mesures if m.reference == 0]
    return {
        "détecteur": poids.nom,
        "input": input_size,
        "volume": volume.nom if volume is not None else "**tous**",
        "régime": regime,
        "langue": langue,
        "planches": len(mesures),
        "bulles": sum(bulles),
        "médiane b/pl": round(statistics.median(bulles), 1) if bulles else None,
        "0 bulle": sum(1 for m in mesures if m.bulles == 0),
        "0 bulle réf": len(zero_ref),
        "récupérées": sum(1 for m in zero_ref if m.bulles > m.non_nettoyables),
        "gagnées/cache": sum(m.gagnees for m in mesures),
        "perdues/cache": sum(m.perdues for m in mesures),
        "non nettoyables": sum(m.non_nettoyables for m in mesures),
        "sans OCR": sum(sans_ocr) if sans_ocr else None,
        "sans texte": (sum(m.sans_texte for m in mesures if m.sans_texte is not None)
                       if any(m.sans_texte is not None for m in mesures) else None),
        "IoU masque": round(sum(ious) / len(ious), 3) if ious else None,
        "s/planche": round(sum(m.secondes for m in mesures) / len(mesures), 2)
        if mesures else None,
    }


# ---------------------------------------------------------------------------
# Le corpus annoté
# ---------------------------------------------------------------------------

def mesurer_corpus(racine: Path, poids_list: list[Poids], config: dict, *,
                   input_size: int, markdown: bool = False) -> str:
    """Rappel / précision / F1 de chaque candidat, par `tools/_banc_detection` — le même banc
    que la CI, avec la seule fonction de prédiction changée."""
    from tools import _banc_detection as bancdet
    blocs = []
    for poids in poids_list:
        predire = fabriquer(poids, config, input_size=input_size)
        resultat = bancdet.mesurer_corpus(racine, predire=predire)
        if resultat is None:
            blocs.append(f"❌ Aucune annotation lisible sous {racine}")
            continue
        blocs.append(f"## {poids.nom} — `input_size` {input_size} — licence {poids.licence}\n")
        blocs.append(bancdet.rendre(resultat, markdown=False))
        blocs.append("")
    if not markdown:
        return "\n".join(blocs)
    entete = banc.entete_publication(
        RACINE / "config.yaml", [], titre="Banc des détecteurs candidats — corpus annoté",
        commande=f"python tools/banc_candidats.py --corpus {racine} "
                 f"--input-size {input_size}")
    return "\n".join([*entete, *blocs])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _poids_demandes(args) -> list[Poids]:
    """Les jeux de poids à mesurer, dans l'ordre où ils ont été demandés."""
    poids: list[Poids] = []
    if args.actuel:
        poids.append(Poids(nom="kitsumed/yolov8m_seg (actuel)", famille="yoloseg",
                           licence="GPL-3.0"))
    for valeur in args.yolo or []:
        chemin, nom = _chemin_et_nom(valeur)
        poids.append(Poids(nom=nom, famille="yolo", chemin=chemin, licence=args.licence))
    for valeur in args.rtdetr or []:
        chemin, nom = _chemin_et_nom(valeur)
        poids.append(Poids(nom=nom, famille="rtdetr", chemin=chemin, licence=args.licence,
                           classes_bulle=CLASSES_BULLE_RTDETR))
    return poids


def _chemin_et_nom(valeur: str) -> tuple[Path, str]:
    chemin = Path(valeur)
    if not chemin.exists():
        raise SystemExit(f"Poids introuvable : {chemin}")
    return chemin, chemin.stem


def _volumes(args, config: dict) -> list:
    racine = Path(args.build) if args.build else banc.racine_build(config)
    if args.tous:
        return banc.enumerer_volumes(racine)
    if not (args.projet and args.tome):
        raise SystemExit("Précise un volume (`\"Projet\" Tome`) ou `--tous`.")
    return [banc.Volume(args.projet, args.tome,
                        banc.build_dir_de(racine, args.projet, args.tome))]


def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Mesure un détecteur de bulles CANDIDAT contre celui du dépôt (lot 16).")
    ap.add_argument("projet", nargs="?", default=None)
    ap.add_argument("tome", nargs="?", default=None)
    ap.add_argument("--tous", action="store_true", help="tous les volumes de build/")
    ap.add_argument("--corpus", metavar="DOSSIER", default=None,
                    help="rappel/précision/F1 contre un corpus annoté, au lieu des volumes")
    ap.add_argument("--actuel", action="store_true",
                    help="mesurer aussi le détecteur en place (YOLOv8-seg, masques)")
    ap.add_argument("--yolo", action="append", metavar="CHEMIN.onnx",
                    help="un export ONNX YOLOv8 detect (boîtes) — répétable")
    ap.add_argument("--rtdetr", action="append", metavar="CHEMIN.onnx",
                    help="un export ONNX RT-DETR-v2 deploy (boîtes) — répétable")
    ap.add_argument("--licence", default="(non déclarée)",
                    help="licence des poids candidats, reportée telle quelle dans le tableau")
    ap.add_argument("--input-size", type=int, default=None,
                    help="résolution d'entrée COMMUNE — le « à armes égales » du lot 16")
    ap.add_argument("--sur-zero", action="store_true",
                    help="ne mesurer que les planches à zéro bulle du cache")
    ap.add_argument("--ocr", action="store_true",
                    help="lire les bulles trouvées (coûteux) pour compter celles sans texte")
    ap.add_argument("--texte", action="store_true",
                    help="interroger le détecteur de TEXTE sur chaque bulle (coûteux) — "
                         "l'indicateur qui reste valable là où `manga-ocr` hallucine")
    ap.add_argument("--limite", type=int, default=None,
                    help="s'arrêter après N planches par volume (mise au point)")
    ap.add_argument("--markdown", action="store_true", help="tableau daté et signé, publiable")
    ap.add_argument("--silencieux", action="store_true", help="pas de progression planche à planche")
    ap.add_argument("--build", metavar="DOSSIER", default=None)
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    config = charger_config(args.config)
    poids_list = _poids_demandes(args)
    if not poids_list:
        raise SystemExit("Aucun poids demandé : passe `--actuel`, `--yolo` ou `--rtdetr`.")
    taille = args.input_size or int(
        (config["manga"]["detection"]).get("input_size", detection.INPUT_SIZE))

    if args.corpus:
        print(mesurer_corpus(Path(args.corpus), poids_list, config,
                             input_size=taille, markdown=args.markdown))
        return 0

    volumes = _volumes(args, config)
    dire = None if args.silencieux else (lambda m: print(m, file=sys.stderr))
    lignes, tous = [], {p.nom: [] for p in poids_list}
    for poids in poids_list:
        for volume in volumes:
            resultat = mesurer_volume(volume, poids, config, input_size=taille,
                                      sur_zero=args.sur_zero, ocr=args.ocr,
                                      texte=args.texte, limite=args.limite, dire=dire)
            lignes.append(resultat["ligne"])
            tous[poids.nom].extend(resultat["planches"])
    for poids in poids_list:
        ligne = agreger(None, poids, taille, tous[poids.nom])
        ligne["volume"] = f"**tous ({len(volumes)} volume(s))**"
        lignes.append(ligne)

    tableau = banc.tableau_markdown(COLONNES, lignes)
    if not args.markdown:
        print(tableau)
        return 0
    entete = banc.entete_publication(
        args.config, volumes, titre="Banc des détecteurs candidats",
        commande="python tools/banc_candidats.py " + " ".join(sys.argv[1:]))
    print("\n".join([*entete,
                     *[f"- **{p.nom}** — famille `{p.famille}`, licence {p.licence}"
                       for p in poids_list],
                     "", tableau, ""]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
