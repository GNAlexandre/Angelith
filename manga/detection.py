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

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from PIL import Image

from ._config import fusion

#: Résolution d'entrée du réseau, par DÉFAUT — `manga.detection.input_size` la déplace.
#:
#: 640 est la résolution d'entraînement standard d'Ultralytics, et c'est pourquoi elle reste le
#: défaut : le comportement livré ne change pas d'un pixel. Mais ce n'était pas une contrainte
#: du modèle, seulement une constante jamais remontée. Les poids téléchargés
#: (`models.DETECTEUR_URL`, `model_dynamic.onnx`) sont un export à **axes dynamiques** —
#: l'entrée est déclarée `['batch', 3, 'height', 'width'] `, vérifié le 25/08/2026 sur le
#: fichier livré — et acceptent donc n'importe quelle résolution multiple du stride.
#:
#: Ce que ça change, et pourquoi c'est le plus gros levier du lot 12 : `_letterbox` met TOUTE
#: la planche dans un carré de ce côté-là. Passer à 1024 multiplie la résolution effective par
#: 1,6 sur **toutes** les planches — y compris les scans paginés basse résolution (844×1200,
#: 848×1200) où les petites bulles de fond arrivent sous 30 px — **sans une seule inférence
#: supplémentaire**, là où le fenêtrage en paie une par fenêtre (cf. `DEFAUTS_FENETRE`).
INPUT_SIZE = 640
CONF_THRESHOLD = 0.35
IOU_THRESHOLD = 0.45
MASK_THRESHOLD = 0.5

#: Stride maximal de YOLOv8 : l'entrée doit être un multiple de 32, sinon les cartes de
#: caractéristiques ne se recomposent pas et ONNX Runtime refuse avec un message d'algèbre.
#: On arrondit au multiple le plus proche plutôt que d'échouer — un `input_size: 1000` est une
#: intention parfaitement claire, et la refuser pour 24 px n'aiderait personne.
STRIDE = 32

#: Aire minimale d'une détection, en **fraction de l'aire de la planche**. `0.0` = aucun
#: filtre, et c'est le défaut : la clé est livrée avec son instrumentation, sa calibration se
#: fait au banc (cf. `MOTIFS_REJET`).
#:
#: ⚠ En FRACTION, jamais en pixels. Le dépôt a déjà appris cette leçon deux fois —
#: `geometry.adaptive_radius` normalise par le petit côté, `text_detection.GROUPEMENT_FRAC`
#: par `min(forme)` — et les deux seuils restés en pixels absolus (`scission.aire_min`,
#: `onomatopees.aire_min`) sont précisément ceux qui cassent sur les scans 844×1200.
AIRE_MIN_FRAC = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# Fenêtrage des bandes très allongées (webtoon)
#
# `_letterbox` met TOUTE l'image dans un carré 640×640 en conservant le ratio. Sur une bande
# de 1080×10000 le facteur vaut 0,064 : la planche devient 69×640, soit **10,8 % de la largeur
# du canevas**, le reste étant du gris. Une bulle de 400×500 px arrive au réseau en 26×32 px —
# ~3×4 cellules au stride 8 de YOLOv8, c'est-à-dire à la limite de détectabilité. Mesuré sur
# *webtoon A* Chap.11 : descendre `conf_threshold` jusqu'à 0,10 ne gagne **aucune**
# bulle, parce que le réseau ne les émet pas du tout. Le seuil n'était pas le levier.
#
# En découpant la bande en fenêtres de 2160 px (2× la largeur), le facteur remonte à 0,296 et
# la même bulle arrive en 118×148 px.
#
# ⚠ Le RECOUVREMENT doit être ≥ la plus haute bulle attendue. C'est ce qui garantit que toute
# bulle est entièrement contenue dans au moins une fenêtre, et donc que jeter les détections
# coupées par une couture ne perd rien. Mesuré sur le corpus : la plus haute fait 833 px.
DEFAUTS_FENETRE = {
    "fenetre_ratio_min": 3.0,     # en deçà, une planche tient déjà bien dans le canevas
    "fenetre_hauteur": 2160,
    "fenetre_recouvrement": 900,
    # Cf. `OCCUPATION_MIN` : 0.0 = « dérive-la du ratio ci-dessus », et c'est le défaut livré.
    "fenetre_occupation_min": 0.0,
    # Cf. `porte_de_l_encre` et `fenetres_encrees` : 0.0 = porte DÉSARMÉE, défaut livré.
    "fenetre_encre_min": 0.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# Le critère de découpage : une DÉTECTABILITÉ, plus un ratio (lot 14, L6.4)
#
# `fenetre_ratio_min: 3.0` était une **falaise**, et à trois titres.
#
# 1. **Elle tombe au mauvais endroit.** Un webtoon découpé par son éditeur en tranches de
#    1080×3000 — cas très courant — a un ratio de 2,78 : aucun fenêtrage. Un ratio de 2,96
#    passe tout aussi juste. Rien dans le dessin ne change entre 2,96 et 3,04.
# 2. **Elle ne bouge pas avec `input_size`.** Le raisonnement de `DEFAUTS_FENETRE` porte sur
#    la taille d'une bulle APRÈS letterbox, pas sur la forme de la planche ; le ratio n'en est
#    qu'un proxy, et ce proxy n'est valable qu'à 640. Depuis que la résolution d'entrée est
#    configurable (lot 12, L4.3), la même planche à 1024 arrive au réseau 1,6× plus grande —
#    et se voit pourtant découpée exactement pareil, donc payée 8 inférences pour rien.
# 3. **Elle ignore le format déclaré, et symétriquement elle s'applique à ce qu'on ne lui a
#    pas demandé.** `fenetres()` ne reçoit que largeur, hauteur et config : une double page de
#    manga très allongée serait découpée sans que personne l'ait voulu.
#
# Le critère est donc écrit sur ce qui compte réellement : **combien de pixels du canevas
# carré la planche occupe-t-elle sur son petit côté**, une fois le letterbox appliqué.
#
#     occupation = petit_côté × input_size / grand_côté
#
# Sur une bande 1080×10 000 à 640, c'est **69 px sur 640** — 10,8 % du canevas, le reste étant
# du gris. Sur une planche paginée 1440×2048, c'est **450 px**. Le seuil sépare les deux, et
# il le fait de la même façon pour les deux formats, sans discontinuité et sans cas
# particulier « webtoon ».
#
# ## Pourquoi 213,33 et pas un chiffre rond
#
# Parce que c'est EXACTEMENT le ratio 3,0 à 640 : `640 / 3,0 = 213,33`. Le défaut livré est
# donc iso-comportement au bit près sur tout le corpus — vérifié sur les 1 513 planches des
# dix volumes et sur les 9 bandes : **aucune planche ne change de décision**. Ce qui change,
# c'est que le seuil est désormais exprimé dans l'unité où le raisonnement se tient, donc
# qu'il **suit `input_size`** : à 1024, la même valeur ne découpe plus qu'à partir d'un ratio
# de 4,8. Une planche entre 3,0 et 4,8 cesse d'y payer ses fenêtres pour rien.
#
# ⚠ **Deux choses que ce défaut ne fait PAS**, et il vaut mieux les écrire que les laisser
# croire :
#
# · il ne dispense PAS une vraie bande de son découpage à 1024 — 1080×10 000 y occupe encore
#   111 px sur 1 024, très en dessous du seuil. Relever la résolution ne remplace pas le
#   fenêtrage, elle le complète ;
# · il ne découpe TOUJOURS PAS la tranche de 1080×3000 (occupation 230 px à 640, au-dessus du
#   seuil), qui est pourtant le cas courant chez les éditeurs. Le relever est un geste qui se
#   MESURE, et le corpus ne contient aucune planche entre les ratios 3,0 et 4,8 : la mesure
#   qui trancherait n'existe pas encore. Cf. `docs/mesures/webtoon-2026-08-26.md`.
#: Occupation minimale par défaut, en pixels du canevas. `INPUT_SIZE` et non la résolution
#: effective : c'est une constante de DÉTECTABILITÉ du réseau, pas une fraction de l'entrée.
#: L'y accrocher la rendrait invariante d'échelle, donc rigoureusement équivalente au ratio —
#: c'est-à-dire sans aucun des trois bénéfices ci-dessus.
OCCUPATION_MIN = INPUT_SIZE / DEFAUTS_FENETRE["fenetre_ratio_min"]

# Tolérance, en pixels, pour juger qu'une détection touche le bord de sa fenêtre.
_MARGE_COUTURE = 4

#: Part d'une détection COUPÉE PAR UNE COUTURE contenue dans une détection entière au-delà de
#: laquelle la première est un doublon de la seconde. Cf. `fusionner_fenetres`.
_CONTAINMENT_COUTURE = 0.85

#: Pourquoi une détection du réseau n'est jamais devenue une région. Registre ORDONNÉ, sur
#: l'idiome de `quality_manga.MOTIFS` et de `detection_retry.LIBELLES` : le motif est une clé,
#: et il est COMPTÉ puis publié dans `RAPPORT.md`.
#:
#: Un filtre muet est la façon dont on perd les treize planches suivantes : c'est exactement ce
#: qui est arrivé au seul filtre qui existait — le « moins de 2 px » ci-dessous — dont personne
#: n'a jamais su combien de détections il mangeait, ni lesquelles.
MOTIFS_REJET = {
    "boite_degeneree": "boîte de moins de 2 px de côté",
    "aire_min": "aire sous `manga.detection.aire_min_frac`",
    "masque_vide": "masque vide après recadrage sur la boîte",
    "couture": "version tronquée d'une bulle vue entière dans une autre fenêtre",
}


def _compter(rejets: dict | None, motif: str) -> None:
    """Incrémente un compteur de rejets. `None` = l'appelant ne compte pas, et c'est légitime :
    `tools/mesurer_bulles.py` n'a que faire du détail."""
    if rejets is not None:
        rejets[motif] = rejets.get(motif, 0) + 1


def normaliser_input_size(taille, *, dire=None) -> int:
    """Une résolution d'entrée utilisable : entière, positive, multiple de `STRIDE`.

    On ARRONDIT plutôt que d'échouer, et on le dit quand ça bouge. `input_size: 1000` est une
    intention parfaitement claire ; refuser un tome de 150 planches pour 24 px de décalage
    serait le genre de rigueur qui ne protège personne."""
    valeur = int(taille)
    if valeur < STRIDE:
        raise ValueError(
            f"manga.detection.input_size = {taille} : une entrée de moins de {STRIDE} px "
            f"n'a pas de sens pour un YOLOv8 (stride maximal {STRIDE}).")
    arrondi = int(round(valeur / STRIDE)) * STRIDE
    if arrondi != valeur and dire is not None:
        dire(f"⚠ manga.detection.input_size = {valeur} n'est pas un multiple de {STRIDE} "
             f"(stride maximal de YOLOv8) : arrondi à {arrondi}.")
    return arrondi


def verifier_axe_dynamique(forme, taille: int, model_path) -> None:
    """Le modèle chargé accepte-t-il `taille` en entrée ? Lève un `SystemExit` clair sinon.

    `session.get_inputs()[0].shape` rend `['batch', 3, 'height', 'width']` sur un export à axes
    dynamiques (c'est le cas de `model_dynamic.onnx`, les poids que ce projet télécharge) et
    `[1, 3, 640, 640]` sur un export figé. Dans le second cas, demander autre chose que 640
    fait échouer ONNX Runtime **à la première planche**, sur une erreur d'algèbre de tenseurs
    qui ne nomme ni la clé de config fautive ni le fichier de poids.

    Un axe figé qui vaut DÉJÀ la taille demandée n'est pas une erreur : c'est le cas nominal
    d'un utilisateur qui aurait figé son export à 640 et n'a rien changé."""
    axes = list(forme or [])[-2:]
    figes = [a for a in axes if isinstance(a, int)]
    if not figes or all(a == taille for a in figes):
        return
    raise SystemExit(
        f"❌ Le modèle de détection {model_path} a une entrée FIGÉE à {axes[0]}×{axes[1]} :\n"
        f"   il ne peut pas recevoir une planche en {taille}×{taille}.\n"
        f"  → remets `manga.detection.input_size: {figes[0]}` dans config.yaml,\n"
        f"  → ou utilise un export à axes dynamiques (celui que télécharge ce projet en est "
        f"un : voir manga_models/README.md).")


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
    # Côté du canevas carré qui a produit cette inférence. Porté ICI et pas lu sur le
    # détecteur : `regions_de` doit pouvoir post-traiter une inférence faite à une AUTRE
    # résolution que celle du tome — c'est exactement ce que fait l'escalade (lot 12, L4.2),
    # qui relance une planche suspecte à 1024 sans toucher aux réglages des 149 autres.
    size: int = INPUT_SIZE


class BubbleDetector:
    """Enveloppe ONNX Runtime autour d'un modèle YOLOv8-seg de détection de bulles."""

    def __init__(self, model_path: str, providers: list[str] | None = None,
                 conf_threshold: float = CONF_THRESHOLD, iou_threshold: float = IOU_THRESHOLD,
                 *, telechargement_auto: bool = True, model_url: str | None = None, dire=None,
                 fenetrage: dict | None = None, input_size: int = INPUT_SIZE,
                 aire_min_frac: float = AIRE_MIN_FRAC):
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
        self.input_size = normaliser_input_size(input_size, dire=dire)
        self.aire_min_frac = max(0.0, float(aire_min_frac))
        # Réglages de découpage des bandes allongées (cf. `DEFAUTS_FENETRE`). Le bloc entier
        # est conservé, pas seulement les trois clés : il vient de `manga.detection`, qui en
        # porte bien d'autres, et `fenetres()` fait le tri.
        self.fenetrage = dict(fenetrage or {})
        # Le rabot du recouvrement se signale UNE fois par détecteur, pas une fois par
        # planche : sur un webtoon de 200 bandes, la même ligne répétée 200 fois cesse d'être
        # un avertissement pour devenir du bruit qu'on apprend à sauter.
        self._dire = dire
        self._rabot_signale = False
        avail = ort.get_available_providers()
        wanted = providers or ["CPUExecutionProvider"]
        used = [p for p in wanted if p in avail] or ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(model_path), providers=used)
        entree = self.session.get_inputs()[0]
        self._input_name = entree.name
        # ⚠ Dit CLAIREMENT qu'un modèle à axes figés ne peut pas changer de résolution, plutôt
        # que de laisser ONNX Runtime refuser à la première planche sur une erreur d'algèbre.
        # C'est le motif de `models.py` : un message qui nomme le fichier, la valeur fautive et
        # le geste qui répare vaut mieux qu'une trace de bibliothèque.
        verifier_axe_dynamique(entree.shape, self.input_size, model_path)

    @classmethod
    def depuis_config(cls, det_cfg: dict, *, dire=None) -> "BubbleDetector":
        """Construit le détecteur depuis le bloc `manga.detection` de la config.

        ⚠ **Le seul point de construction.** Il y en avait trois — l'orchestrateur,
        `tools/apercu_detection.py` et `manga/services.py` — copiés les uns sur les autres,
        et ils avaient déjà divergé : le correctif webtoon a ajouté `fenetrage=det_cfg` aux
        deux premiers et manqué le troisième, si bien que les réglages `fenetre_*` de
        l'utilisateur y étaient silencieusement perdus. C'était invisible parce que le
        troisième chemin n'a aujourd'hui aucun appelant — du code mort porteur d'un bug déjà
        cassé, qui aurait mordu au premier bouton « re-détecter » branché dans l'éditeur.

        Les défauts vivent ici et NULLE PART ailleurs, pour la même raison."""
        return cls(
            det_cfg["model_path"], providers=det_cfg.get("providers"),
            conf_threshold=float(det_cfg.get("conf_threshold", CONF_THRESHOLD)),
            iou_threshold=float(det_cfg.get("iou_threshold", IOU_THRESHOLD)),
            telechargement_auto=bool(det_cfg.get("telechargement_auto", True)),
            model_url=det_cfg.get("model_url") or None,
            # ⚠ Branchés ICI et pas dans les appelants — c'est tout l'objet de cette fabrique.
            # `input_size` était une constante de module que rien ne remontait : ni paramètre
            # de `__init__`, ni clé de config, alors même que les poids livrés acceptent
            # n'importe quelle résolution (`model_dynamic.onnx`).
            input_size=int(det_cfg.get("input_size", INPUT_SIZE)),
            aire_min_frac=float(det_cfg.get("aire_min_frac", AIRE_MIN_FRAC)),
            # Découpage des bandes allongées : sans lui, une bulle de webtoon arrive au
            # réseau en 26×32 px et n'est tout simplement pas émise (cf. `DEFAUTS_FENETRE`).
            fenetrage=det_cfg,
            # Le téléchargement passe par le reporter : 104 Mo en silence ressemblent à un
            # pipeline planté, et ces lignes atterrissent aussi dans perf.log.
            dire=dire)

    def inferer(self, image: Image.Image, *, input_size: int | None = None) -> Inference:
        """Passe ONNX seule, SANS post-traitement — la partie chère, et la seule.

        `conf_threshold` et `iou_threshold` ne servent qu'au filtrage et au NMS : le réseau,
        lui, ne les voit jamais. Les séparer rend un **balayage de seuils** presque gratuit —
        une inférence, dix post-traitements — ce qui est tout l'intérêt de
        `tools/apercu_detection.py` : essayer douze réglages sur une planche coûte le prix
        d'un seul passage du modèle.

        `input_size` est la SEULE exception à ce raisonnement : elle change le tenseur d'entrée,
        donc elle repaie l'inférence. C'est un paramètre par appel malgré tout, parce que
        reconstruire un détecteur pour la changer rechargerait 104 Mo de poids — et l'escalade
        (lot 12, L4.2) relance justement une poignée de planches à une autre résolution que
        celle du tome."""
        w0, h0 = image.size
        size = self.input_size if input_size is None else normaliser_input_size(input_size)
        tensor, r, (dw, dh) = _letterbox(image, size)
        out0, proto = self.session.run(None, {self._input_name: tensor})[:2]
        return Inference(out0=out0, proto=proto, r=r, dw=dw, dh=dh, w0=w0, h0=h0, size=size)

    def regions_de(self, inference: Inference, *, conf_threshold: float | None = None,
                   iou_threshold: float | None = None,
                   rejets: dict | None = None) -> list[BubbleRegion]:
        """Post-traite une inférence déjà calculée, aux seuils demandés.

        `rejets` est un compteur `{motif: n}` que le post-traitement INCRÉMENTE (cf.
        `MOTIFS_REJET`). Passé par l'appelant plutôt que renvoyé : le balayage de seuils
        appelle cette méthode douze fois de suite, et un compteur cumulatif est ce qu'il veut ;
        l'orchestrateur en passe un neuf par planche."""
        return _postprocess(
            inference.out0, inference.proto, inference.r, inference.dw, inference.dh,
            inference.w0, inference.h0,
            self.conf_threshold if conf_threshold is None else float(conf_threshold),
            self.iou_threshold if iou_threshold is None else float(iou_threshold),
            size=inference.size, aire_min_frac=self.aire_min_frac, rejets=rejets)

    def _dire_rabot(self, message: str) -> None:
        """Relaie le rabot de recouvrement, une seule fois pour la vie du détecteur."""
        if self._rabot_signale or self._dire is None:
            return
        self._rabot_signale = True
        self._dire(message)

    def inferer_fenetres(self, image: Image.Image, *, input_size: int | None = None,
                         sautees: dict | None = None) -> list[tuple[Inference, int, int]]:
        """Une inférence par fenêtre : `[(inference, y0, y1)]`. Liste à UN élément (la planche
        entière, `y0=0`) quand l'image n'est pas assez allongée pour être découpée.

        Séparée de `regions_de_fenetres` pour la même raison qu'`inferer` l'est de
        `regions_de` : un balayage de seuils reste presque gratuit, il ne repaie que le
        post-traitement.

        `sautees` est un compteur `{motif: n}` — même idiome que `rejets` — que la porte
        d'encre incrémente. Cf. `fenetres_encrees`."""
        w0, h0 = image.size
        # ⚠ La résolution EFFECTIVE, pas le défaut du module : c'est elle qui décide si la
        # planche a besoin d'être découpée (lot 14, L6.4). Une planche relancée à 1024 par
        # l'escalade n'a pas les mêmes besoins que la même planche à 640.
        taille = self.input_size if input_size is None else normaliser_input_size(input_size)
        bandes = fenetres(w0, h0, self.fenetrage, input_size=taille, dire=self._dire_rabot)
        if not bandes:
            return [(self.inferer(image, input_size=input_size), 0, h0)]
        bandes = fenetres_encrees(image, bandes, self.fenetrage, sautees=sautees)
        return [(self.inferer(image.crop((0, y0, w0, y1)), input_size=input_size), y0, y1)
                for y0, y1 in bandes]

    def regions_de_fenetres(self, morceaux: list[tuple[Inference, int, int]], hauteur: int, *,
                            conf_threshold: float | None = None,
                            iou_threshold: float | None = None,
                            rejets: dict | None = None) -> list[BubbleRegion]:
        """Post-traite chaque fenêtre, remonte les détections en coordonnées pleine page et
        déduplique ce que les recouvrements ont vu deux fois."""
        if len(morceaux) == 1 and morceaux[0][1] == 0 and morceaux[0][2] == hauteur:
            return self.regions_de(morceaux[0][0], conf_threshold=conf_threshold,
                                   iou_threshold=iou_threshold, rejets=rejets)
        iou = self.iou_threshold if iou_threshold is None else float(iou_threshold)
        # ⚠ Un GÉNÉRATEUR, et pas une liste. Le post-traitement d'une fenêtre produit un
        # masque par région à la taille de la FENÊTRE ; `_remonter` en fait aussitôt un masque
        # pleine page et le premier devient un déchet. Matérialiser les huit fenêtres d'une
        # bande de 10 000 px d'abord garderait les deux vivants en même temps — quelques
        # dizaines de mégaoctets pour rien, sur le format qui a justement le moins de marge.
        return assembler_fenetres(
            ((self.regions_de(inference, conf_threshold=conf_threshold,
                              iou_threshold=iou_threshold, rejets=rejets), y0, y1)
             for inference, y0, y1 in morceaux),
            hauteur, iou, rejets=rejets)

    def detect(self, image: Image.Image, *, conf_threshold: float | None = None,
               iou_threshold: float | None = None, input_size: int | None = None,
               rejets: dict | None = None, sautees: dict | None = None) -> list[BubbleRegion]:
        """Détecte les bulles d'une planche. `image` = PIL.Image RGB.

        Les seuils par appel priment sur ceux de l'instance : c'est ce qui permet de relancer
        UNE planche à d'autres réglages sans reconstruire le détecteur — donc sans recharger
        104 Mo de poids — ni toucher aux réglages du tome.

        Une bande très allongée est détectée **fenêtre par fenêtre** (cf. `fenetres`) ; une
        planche paginée passe par le chemin d'origine, inchangé."""
        return self.regions_de_fenetres(
            self.inferer_fenetres(image, input_size=input_size, sautees=sautees),
            image.size[1],
            conf_threshold=conf_threshold, iou_threshold=iou_threshold, rejets=rejets)


#: Part de la hauteur de fenêtre au-delà de laquelle un recouvrement est raboté.
#:
#: La seule borne était `h - 1`, ce qui n'en est pas une : `fenetre_recouvrement: 2159` avec
#: `fenetre_hauteur: 2160` donne `pas = 1`, et une bande de 1080×10 000 produit alors
#: **7 841 fenêtres** — donc 7 841 inférences ONNX pour une seule planche, sans un mot. Au
#: défaut livré (900 sur 2160, soit 42 %), le même calcul donne 8 fenêtres.
#:
#: 80 % laisse largement la place aux réglages légitimes : un recouvrement de la moitié de la
#: fenêtre reste sous la borne, et au-delà on ne gagne plus rien qu'un facteur de coût — deux
#: fenêtres qui partagent 80 % de leur surface voient presque la même chose.
RECOUVREMENT_MAX_FRAC = 0.80


def occupation(largeur: int, hauteur: int, taille: int = INPUT_SIZE) -> float:
    """Pixels du canevas carré occupés par le PETIT CÔTÉ de la planche, après letterbox.

    C'est la résolution à laquelle le réseau voit réellement la planche, et donc le seul
    chiffre sur lequel décider s'il faut la découper. Cf. le bloc `OCCUPATION_MIN`."""
    grand = max(int(largeur), int(hauteur))
    if grand <= 0:
        return 0.0
    return min(int(largeur), int(hauteur)) * float(taille) / grand


def fenetres(largeur: int, hauteur: int, cfg: dict | None = None,
             *, input_size: int | None = None, dire=None) -> list[tuple[int, int]]:
    """Bandes horizontales `(y0, y1)` à détecter séparément, ou `[]` s'il n'y a rien à découper.

    Pleine largeur : c'est la hauteur seule qui écrase le letterbox, la largeur d'une planche
    tient toujours dans le canevas. Renvoyer `[]` est le cas nominal d'un manga paginé — une
    planche 1440×2048 occupe 450 px du canevas, très au-dessus du seuil, et son chemin ne
    change pas d'un pixel.

    `input_size` est la résolution à laquelle la planche sera réellement envoyée au réseau.
    C'est ce qui rend le critère juste : la MÊME planche mérite d'être découpée à 640 et pas à
    1024. `None` = le défaut du module, ce qui préserve le comportement des rares appelants
    qui ne savent pas à quelle résolution ils tournent.

    ⚠ **Le découpage ne dépend pas du FORMAT déclaré, et c'est délibéré.** Ni `plan.format` ni
    `--format webtoon` n'arrivent jusqu'ici, et il n'y a rien à y ajouter : une bande de
    webtoon et une double page de manga anormalement allongée posent au réseau exactement le
    même problème de résolution, et méritent exactement la même réponse. Un cas particulier
    par format serait deux critères à entretenir pour un seul phénomène.

    La dernière fenêtre est **recalée sur le bas** de l'image plutôt qu'allongée : toutes les
    fenêtres ont ainsi la même hauteur, donc le même facteur de letterbox, donc la même
    sensibilité. Une dernière fenêtre plus courte aurait détecté un peu mieux que les autres,
    ce qui rendrait le résultat dépendant de la hauteur totale de la planche."""
    c = fusion(DEFAUTS_FENETRE, cfg)
    if largeur <= 0 or hauteur <= 0:
        return []
    taille = INPUT_SIZE if input_size is None else int(input_size)
    seuil = float(c.get("fenetre_occupation_min") or 0.0)
    if seuil <= 0:
        # Dérivé du ratio, à `INPUT_SIZE` : c'est ce qui rend le défaut iso-comportement.
        seuil = INPUT_SIZE / max(1e-9, float(c["fenetre_ratio_min"]))
    if occupation(largeur, hauteur, taille) > seuil:
        return []
    h = max(1, int(c["fenetre_hauteur"]))
    if h >= hauteur:
        return []
    # ⚠ Le rabot est ANNONCÉ, jamais silencieux. Un recouvrement démesuré ne produit pas un
    # résultat faux mais un run qui n'en finit pas, et c'est précisément le genre de panne
    # qu'on met deux heures à attribuer à une ligne de `config.yaml`.
    demande = max(0, int(c["fenetre_recouvrement"]))
    plafond = min(h - 1, int(h * RECOUVREMENT_MAX_FRAC))
    recouvrement = min(demande, plafond)
    if demande > recouvrement and dire is not None:
        dire(f"⚠ manga.detection.fenetre_recouvrement = {demande} px pour une fenêtre de "
             f"{h} px : raboté à {recouvrement} px ({RECOUVREMENT_MAX_FRAC:.0%} de la "
             f"fenêtre). Sans ce rabot, une bande de {hauteur} px demanderait "
             f"{len(range(0, max(1, hauteur - h + 1), max(1, h - demande)))} inférences.")
    pas = max(1, h - recouvrement)
    departs = list(range(0, hauteur - h + 1, pas))
    if departs[-1] + h < hauteur:
        departs.append(hauteur - h)
    return [(y, y + h) for y in departs]


#: Pourquoi une fenêtre n'a pas reçu d'inférence. Même registre ORDONNÉ que `MOTIFS_REJET`,
#: et pour la même raison : ce qu'on saute en silence, on ne le retrouve jamais.
MOTIFS_SAUT = {
    "fenetre_sans_encre": "fenêtre écartée par `manga.detection.fenetre_encre_min`",
}


def fenetres_encrees(image: Image.Image, bandes: list[tuple[int, int]],
                     cfg: dict | None = None, *,
                     sautees: dict | None = None) -> list[tuple[int, int]]:
    """Retire des `bandes` celles qui ne portent que du fond. Liste inchangée si la porte est
    désarmée (`fenetre_encre_min: 0.0`, le défaut livré).

    Réutilise `part_encre` — le test d'encre du lot 12 — plutôt que d'en écrire un second. Un
    projet qui mesure deux fois « y a-t-il quelque chose sur cette image » avec deux
    définitions du fond finit par publier deux chiffres qui se contredisent.

    ## Ce que la mesure dit, et pourquoi le défaut est DÉSARMÉ

    L'idée est juste dans l'absolu : une bande comporte de larges plages sans texte, le blanc
    y fait le rythme, et une fenêtre vide coûte aujourd'hui une inférence pleine. Sur le seul
    webtoon du corpus, elle ne tient pas.

    · **0 fenêtre sur 71** tombe sous le seuil d'encre livré (0,004). La moins encrée du
      corpus est à **0,0065**, et la médiane à 0,79 — c'est une bande couleur, illustrée d'un
      bord à l'autre. La porte ne sauterait rigoureusement rien.
    · **Et le gain visé était surestimé d'un ordre de grandeur.** `config.yaml` annonçait
      « ~70 s au lieu de ~8 s par planche » ; mesuré sur les 9 bandes, le fenêtrage coûte
      **7,1 s** contre **0,85 s** pour une inférence unique — le facteur ×8,3 est juste, les
      valeurs absolues ne l'étaient pas. Ce qu'une porte parfaite économiserait se compte donc
      en **secondes sur un tome de 48 minutes**.

    Sauter une fenêtre qui contenait une bulle est exactement le défaut que le lot 12 vient de
    corriger. Échanger ce risque contre quelques secondes serait un mauvais marché, et le
    défaut livré le dit : **0.0, porte désarmée**. Le mécanisme est là, instrumenté, pour la
    bande en noir et blanc à grandes plages vides que ce corpus ne contient pas — et il se
    calibre au banc, comme `aire_min_frac`."""
    seuil = float((fusion(DEFAUTS_FENETRE, cfg)).get("fenetre_encre_min") or 0.0)
    if seuil <= 0 or not bandes:
        return list(bandes)
    largeur = image.size[0]
    gardees = []
    for y0, y1 in bandes:
        if part_encre(image.crop((0, y0, largeur, y1))) >= seuil:
            gardees.append((y0, y1))
        else:
            _compter(sautees, "fenetre_sans_encre")
    # ⚠ Jamais TOUTES. Une bande dont chaque fenêtre passe sous le seuil est une bande que la
    # porte a mal jugée, pas une bande vide : on rend la liste d'origine et on ne compte rien.
    # Sans cette ligne, un seuil mal réglé produirait une planche à zéro bulle en silence —
    # très précisément le défaut du lot 12.
    if not gardees:
        if sautees is not None:
            sautees.pop("fenetre_sans_encre", None)
        return list(bandes)
    return gardees


def _touche_couture(region: "BubbleRegion", y0: int, y1: int, hauteur: int) -> bool:
    """La détection est-elle coupée par un bord INTÉRIEUR de sa fenêtre ?

    Le bord réel de la planche n'en est pas un : une bulle collée au haut de la première
    fenêtre est légitimement collée au haut de la page."""
    haut, bas = region.bbox[1], region.bbox[3]
    if y0 > 0 and haut <= y0 + _MARGE_COUTURE:
        return True
    return y1 < hauteur and bas >= y1 - _MARGE_COUTURE


def assembler_fenetres(par_fenetre: Iterable[tuple[list["BubbleRegion"], int, int]],
                       hauteur: int, iou_threshold: float, *,
                       rejets: dict | None = None) -> list["BubbleRegion"]:
    """Remonte en coordonnées pleine page les régions détectées `(regions, y0, y1)` fenêtre par
    fenêtre, puis déduplique ce que les recouvrements ont vu deux fois.

    Extraite de `BubbleDetector.regions_de_fenetres` — qui reste son seul appelant du pipeline
    — pour que **le banc des détecteurs candidats** (`tools/banc_candidats.py`, lot 16) fenêtre
    exactement comme le pipeline. Un second avis mesuré avec un autre découpage, un autre
    critère de couture ou un autre dédoublonnage ne serait pas comparable au premier : c'est le
    même argument que `_banc_detection`, qui apparie par `detection_retry.apparier` plutôt que
    par une réimplémentation.

    Le paramètre porte des RÉGIONS et non des inférences, parce qu'un candidat qui ne donne que
    des boîtes n'a pas d'`Inference` au sens de ce module. Il est déclaré `Iterable` et
    consommé une fenêtre à la fois : l'appelant du pipeline y passe un générateur, ce qui
    évite de garder vivants en même temps les masques de fenêtre et les masques pleine page.
    """
    candidates: list[tuple[BubbleRegion, bool]] = []
    for regions, y0, y1 in par_fenetre:
        for region in regions:
            entiere = _remonter(region, y0, hauteur)
            candidates.append((entiere, _touche_couture(entiere, y0, y1, hauteur)))
    return fusionner_fenetres(candidates, iou_threshold, rejets=rejets)


def fusionner_fenetres(candidates: list[tuple["BubbleRegion", bool]],
                       iou_threshold: float, *,
                       rejets: dict | None = None) -> list["BubbleRegion"]:
    """Déduplique les détections venues de fenêtres qui se recouvrent.

    Une bulle prise dans le recouvrement est détectée deux fois. On garde la meilleure, avec un
    ordre de priorité en deux temps : **d'abord celles qu'aucune couture ne coupe**, puis le
    score. Sans ce premier critère, une version tronquée mieux notée pourrait évincer la
    version entière.

    ⚠ On ne JETTE jamais purement et simplement les détections coupées : elles restent
    candidates en second rang. Une bulle plus haute que le recouvrement serait tronquée dans
    *toutes* les fenêtres, et la jeter partout la ferait disparaître — mieux vaut une bulle
    tronquée, que l'éditeur peut retailler, qu'une bulle absente que personne ne voit.

    ## Pourquoi l'IoU de boîtes ne suffit pas, avec le calcul

    Aux défauts livrés (`fenetre_hauteur: 2160`, `fenetre_recouvrement: 900`, donc
    `pas = 1260`), une bulle de 500 px de haut à y ∈ [2000, 2500] est vue **tronquée** par la
    fenêtre [0, 2160) — 160 px, marquée couture — et **entière** par la fenêtre [1260, 3420).
    Leur IoU vaut 160/500 = **0,32** : sous le seuil, donc les deux sont conservées. La
    tronquée passe ensuite dans `rendre_disjoints`, en ressort en sliver, et produit une bulle
    vide de plus dans `regions.json`, un OCR de plus, et **une réplique numérotée de plus
    attendue du LLM** — donc un décalage de numérotation sur toute la planche.

    ⚠ Et le seuil n'est pas un 0,45 en dur : `iou_threshold` est **le même paramètre** que le
    NMS intra-fenêtre (cf. `regions_de_fenetres`). Le déplacer pour réparer la couture le
    déplacerait aussi dans le NMS, où il ne décrit pas la même chose. D'où le critère
    ci-dessous, qui n'y touche pas du tout.

    Le bon critère est celui que le dépôt défend déjà ailleurs, dans `text_detection`
    (`hors_des_bulles`) : le **containment** de masques, et non l'IoU de boîtes. « Une réplique
    de 200 px² dans un ballon de 40 000 px² donne un IoU de 0,005 » alors que le containment
    vaut 1,0 — et l'argument s'applique ici mot pour mot. Une candidate marquée couture
    contenue à ≥ `_CONTAINMENT_COUTURE` dans une candidate ENTIÈRE est un doublon, quel que
    soit l'IoU. La doctrine reste intacte : on ne jette la coupée que quand sa version entière
    est là."""
    ordre = sorted(range(len(candidates)),
                   key=lambda i: (candidates[i][1], -candidates[i][0].score))
    gardees: list[tuple[BubbleRegion, bool]] = []
    for i in ordre:
        region, coupee = candidates[i]
        if any(_iou_bbox(region.bbox, g.bbox) > iou_threshold for g, _ in gardees):
            continue
        # Le tri place TOUTES les entières avant les coupées : quand on examine une coupée,
        # toutes les entières retenues sont déjà là. Le test n'a donc pas besoin d'un second
        # passage, et une coupée n'évince jamais une autre coupée.
        if coupee and any(not gc and _containment(region.mask, g.mask) >= _CONTAINMENT_COUTURE
                          for g, gc in gardees):
            _compter(rejets, "couture")
            continue
        gardees.append((region, coupee))
    return [g for g, _ in gardees]


def _containment(a: np.ndarray, b: np.ndarray) -> float:
    """Part de `a` qui est dans `b`. Asymétrique, et c'est tout l'intérêt : la question n'est
    pas « ces deux masques se ressemblent-ils » mais « celui-ci est-il déjà couvert par
    celui-là ». Même mesure que `text_detection.hors_des_bulles`, pour la même raison."""
    aire = int(np.count_nonzero(a))
    if not aire:
        return 0.0
    return int(np.count_nonzero(a & b)) / aire


def _iou_bbox(a, b) -> float:
    """Intersection sur union de deux boîtes. Recopié plutôt qu'importé de `manga.geometry` :
    `detection.py` ne doit dépendre que de numpy et Pillow — c'est le module que
    `tools/mesurer_bulles.py` importe sans le reste de la brique."""
    largeur = min(a[2], b[2]) - max(a[0], b[0])
    hauteur = min(a[3], b[3]) - max(a[1], b[1])
    if largeur <= 0 or hauteur <= 0:
        return 0.0
    inter = largeur * hauteur
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0


def _remonter(region: "BubbleRegion", y0: int, hauteur: int) -> "BubbleRegion":
    """Ramène une détection faite dans une fenêtre aux coordonnées de la planche entière."""
    x0, ry0, x1, ry1 = region.bbox
    masque = np.zeros((hauteur, region.mask.shape[1]), dtype=bool)
    masque[y0:y0 + region.mask.shape[0]] = region.mask
    return BubbleRegion(bbox=(x0, ry0 + y0, x1, ry1 + y0), mask=masque,
                        score=region.score, cls=region.cls, kind=region.kind,
                        scindee=region.scindee)


# ─────────────────────────────────────────────────────────────────────────────
# Test d'ENCRE — une planche à zéro bulle est-elle blanche, ou pleine de dessin ?
#
# Sans modèle, sans E/S, sans dépendance nouvelle : numpy et Pillow, comme le reste du module.
#
# ## Pourquoi il fallait l'écrire ici
#
# Le seul discriminant qui existait entre « page de garde » et « pleine page d'action » était
# `bool(qa["sfx"])` (`report_manga.py`). Il est correct pour ce que le rapport en dit, et il est
# INDISPONIBLE dès que la passe onomatopées ne tourne pas : sur les trois volumes de manga D,
# aucun `sfx.json` n'existe, et leurs 72 planches à zéro bulle ne sont triées **du
# tout**. Une escalade branchée dessus ne se déclencherait donc JAMAIS sur ces tomes-là — pas
# même sur leurs pleines pages d'action —, et se déclencherait normalement sur le tome d'à
# côté. Un discriminant dont la réponse dépend d'une option cochée ailleurs n'en est pas un.
#
# ## Ce que le test dit, et ce qu'il ne dit pas
#
# Il dit « cette planche porte autre chose que du fond ». Il ne dit PAS « elle porte du
# texte » : séparer le texte du dessin demande `text_detection`, donc un second modèle de
# 94,7 Mo et une passe ONNX par planche. Pour décider s'il vaut la peine de relancer une
# détection, « il y a quelque chose sur cette planche » est exactement la question utile — et
# c'est celle qu'on peut poser en quelques millisecondes sur 1 513 planches.
#
# Le vocabulaire est celui de `clean.py`, qui mesure déjà de l'uniformité : le fond est la
# luminance MÉDIANE et non le blanc. Une planche en niveaux de gris sombres, une planche
# inversée (blanc sur noir) et un webtoon couleur ont trois fonds différents, et mesurer « ce
# qui n'est pas blanc » les déclarerait toutes les trois couvertes d'encre.
# ─────────────────────────────────────────────────────────────────────────────

#: Facteur de SOUS-ÉCHANTILLONNAGE avant mesure. Le test doit coûter des millisecondes, pas
#: une passe pleine résolution — c'est ce qui permet de le poser sur les 1 513 planches du
#: corpus, et sur chaque planche d'un run sans qu'on s'en aperçoive.
#:
#: 4 suffit : ce qu'on cherche est une PART de pixels qui s'écartent du fond, pas un contour.
#: `Image.BOX` fait une vraie moyenne de bloc (et non un point sur seize), donc un trait fin
#: contribue à son bloc au lieu de disparaître une fois sur quatre — mais il contribue en
#: proportion, ce qui atténue l'écart d'un trait isolé. D'où une tolérance mesurée sur l'image
#: RÉDUITE et non recopiée de la pleine résolution (cf. `TOLERANCE_FOND`).
SOUS_ECHANTILLON_ENCRE = 4

#: Écart de luminance, en niveaux 0-255, au-delà duquel un pixel n'est plus « le fond ».
#: Assez large pour absorber le halo JPEG d'un scan, assez étroit pour qu'un trait compte.
TOLERANCE_FOND = 24

#: Part de pixels s'écartant du fond au-delà de laquelle la planche porte de l'encre.
#:
#: Le seuil est bas EXPRÈS, et l'asymétrie est le sujet : un faux positif coûte une inférence
#: de plus sur une page de garde ; un faux négatif efface du décompte une planche entièrement
#: non traduite — l'erreur que le lot 12 cherche précisément à rendre visible.
#:
#: ⚠ **Calibré sur les 188 planches à zéro bulle des dix volumes, pas à l'œil.** 183 sont
#: classées « porte de l'encre », 5 « blanche », zéro non mesurée. Les marges sont larges des
#: deux côtés : la plus encrée des blanches est à 0,0034 et la moins encrée des encrées à
#: 0,0048, alors que la médiane des encrées dépasse 0,2.
#:
#: ⚠ Et une prémisse répandue est FAUSSE : une couverture n'est pas une page blanche. Les
#: couvertures de manga A s'écartent du fond sur **0,72 à 0,99** de leurs pixels — ce sont des
#: illustrations pleine page. Le seul vrai séparateur de ces tomes est la planche 2 (0,0025),
#: et le test la classe correctement sur les quatre. L'escalade tourne donc sur les couvertures,
#: pour une inférence chacune, et compte tenu de l'asymétrie ci-dessus c'est le bon arbitrage.
#: ⚠ Elle en tire quelque chose : sur les 29 liminaires à zéro bulle des quatre tomes, 6 bulles
#: sur 5 planches — **que personne n'a encore inspectées à l'œil**. Une couverture peut porter
#: un vrai cartouche de titre comme une fausse détection sur un aplat, et c'est `RAPPORT.md`
#: (« zones restaurées », « bulles sans texte OCR ») qui tranchera au premier run complet.
#: Cf. `docs/chiffres-de-reference.md`.
SEUIL_ENCRE = 0.004


def part_encre(image, *, tolerance: int = TOLERANCE_FOND,
               sous_echantillon: int = SOUS_ECHANTILLON_ENCRE) -> float:
    """Fraction des pixels de `image` qui s'écartent du fond de la planche.

    Accepte une `PIL.Image`, un chemin, ou un tableau numpy 2-D déjà en niveaux de gris."""
    arr = _luminance(image, sous_echantillon)
    if arr.size == 0:
        return 0.0
    fond = float(np.median(arr))
    return float((np.abs(arr - fond) > tolerance).mean())


def porte_de_l_encre(image, *, seuil: float = SEUIL_ENCRE,
                     tolerance: int = TOLERANCE_FOND,
                     sous_echantillon: int = SOUS_ECHANTILLON_ENCRE) -> bool:
    """La planche porte-t-elle autre chose que du fond ?

    C'est le test qui arme l'escalade de détection (`orchestrator_manga`) et qui remplit la
    colonne « dont encrées » du banc (`tools/_banc_commun.porte_de_l_encre`). Les deux passent
    par ici, et c'est le point : un rapport qui trie ses planches autrement que le pipeline ne
    mesure pas le pipeline."""
    return part_encre(image, tolerance=tolerance,
                      sous_echantillon=sous_echantillon) >= float(seuil)


def _luminance(image, sous_echantillon: int) -> np.ndarray:
    """Luminance de `image`, réduite d'un facteur `sous_echantillon`, en int16.

    int16 et non uint8 : `np.abs(arr - fond)` sur des uint8 repasse par zéro sur un pixel plus
    SOMBRE que le fond — c'est-à-dire sur tout le trait d'un manga."""
    from pathlib import Path

    if isinstance(image, np.ndarray):
        arr = np.asarray(image)
        if arr.ndim == 3:
            arr = np.asarray(Image.fromarray(arr.astype(np.uint8)).convert("L"))
        img = Image.fromarray(arr.astype(np.uint8), mode="L")
    elif isinstance(image, (str, Path)):
        with Image.open(image) as ouverte:
            img = ouverte.convert("L")
    else:
        img = image.convert("L")
    k = max(1, int(sous_echantillon))
    if k > 1 and img.width >= k and img.height >= k:
        # BOX = moyenne de bloc. NEAREST prendrait un pixel sur seize et raterait un trait fin
        # une fois sur quatre, ce qui rendrait le test dépendant de l'alignement du lettrage.
        img = img.resize((max(1, img.width // k), max(1, img.height // k)), Image.BOX)
    return np.asarray(img, dtype=np.int16)


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
                  *, size: int = INPUT_SIZE, aire_min_frac: float = AIRE_MIN_FRAC,
                  rejets: dict | None = None) -> list[BubbleRegion]:
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
            _compter(rejets, "boite_degeneree")
            continue
        # Aire minimale, en FRACTION de la planche. Sans elle, une detection de 10x10 px a
        # score 0,36 survivait a tout : son masque remplit sa boite, donc `bubbles_split` la
        # laissait filer avant tout examen, puis elle traversait l'ordre de lecture,
        # `save_regions`, l'OCR (agrandie x2 puis lue - du bruit) et occupait **une place
        # numerotee dans le prompt du traducteur**. Le seul rempart etait en aval, dans
        # `clean.py`, et il n'empeche ni l'OCR, ni l'appel LLM, ni le decalage de numerotation.
        if aire_min_frac > 0 and (ox1 - ox0) * (oy1 - oy0) < aire_min_frac * w0 * h0:
            _compter(rejets, "aire_min")
            continue

        # Masque : combinaison linéaire des prototypes, sigmoïde, reshape (mh, mw).
        coeffs = mask_coeffs[i]
        m = 1.0 / (1.0 + np.exp(-(coeffs @ proto_flat)))
        m = m.reshape(proto.shape[2], proto.shape[3])
        m_img = Image.fromarray((m * 255).astype(np.uint8)).resize(
            (size, size), Image.BILINEAR)
        # Retire le padding du letterbox, puis remet à l'échelle de l'image d'origine.
        crop_box = (round(dw), round(dh), size - round(dw), size - round(dh))
        m_crop = m_img.crop(crop_box).resize((w0, h0), Image.BILINEAR)
        mask_full = np.asarray(m_crop) >= (MASK_THRESHOLD * 255)

        # Sécurité supplémentaire : masque hors bbox mis à zéro (évite toute fuite de
        # texture au-delà de la zone détectée en cas de masque bruité).
        bbox_mask = np.zeros_like(mask_full)
        bbox_mask[int(oy0):int(oy1), int(ox0):int(ox1)] = True
        mask_full &= bbox_mask

        # ⚠ Deux lignes, et elles manquaient. Le recadrage ci-dessus peut vider
        # entièrement un masque bruité ; la région partait quand même dans
        # `regions.json`, avec sa boîte et son score, et c'est en aval seulement que
        # `clean.analyze_bubble` la neutralisait — trop tard pour lui épargner l'OCR,
        # l'appel LLM et sa place numérotée.
        if not mask_full.any():
            _compter(rejets, "masque_vide")
            continue

        regions.append(BubbleRegion(
            bbox=(int(ox0), int(oy0), int(ox1), int(oy1)),
            mask=mask_full, score=float(scores[i]), cls=int(classes[i]),
        ))
    return regions
