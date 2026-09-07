# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Détection du texte posé SUR LE DESSIN — onomatopées, narration libre, cartouches.

## Pourquoi ce module existe

`manga/detection.py` ne connaît qu'une classe : la bulle. Sur les 1 593 régions des deux
tomes du *manga A*, `kind` vaut `"bulle"` **1 593 fois**. Tout ce qui est
écrit hors d'un ballon — les onomatopées géantes d'une page d'action, une pensée posée en
colonne dans un blanc de case — n'est donc ni détecté, ni nettoyé, ni traduit : il reste en
japonais sur la planche finale. C'était la limite de phase 1, assumée par le README.

> **Dénominateur de ce 1 593** — mesuré sur les rendus de la **v1.0.0**, en comptant les
> bulles depuis les `qa.json` des deux tomes. Ce n'est pas le même dénominateur que celui de
> `regions.json`, qui est la source de vérité de la détection et qui compte aussi les planches
> dépourvues de contrôle qualité. Le chiffre historique est conservé tel quel — il documente
> une mesure datée, pas l'état courant. Pour l'état courant :
> `python tools/banc.py --tous`, et le protocole est dans
> [`docs/chiffres-de-reference.md`](../docs/chiffres-de-reference.md).

Mesuré sur le Vol.2 : **23 planches sans aucune détection de bulle**, dont 13 de vrai
contenu (les pages 63 à 65 et 134 à 136 pèsent 450 à 720 Ko de dessin et de katakana). Le
Vol.1 a exactement le même défaut. Ce n'était pas une régression, c'était un angle mort.

## Ce que ce module fait, et ne fait pas

Il **lit**, comme `detection.py`. Il ne peint rien : le principe directeur de la brique —
« l'IA ne dessine jamais » — reste entier. `clean.py` n'est pas touché et aucun pixel du
dessin n'est repeint par ce module.

⚠ **Deux corrections, lot 22 L22.5**, parce qu'une affirmation fausse du dépôt est un défaut
livrable au même titre qu'un bug.

· Le dessin de la glose **ne se fait pas dans `typeset.py`** : le mot `glose` n'y apparaît
  nulle part. Il se fait dans `manga/gloss.py` (`placer` puis `dessiner`), appelé par
  `manga/rendu.py`.
· L'effacement des onomatopées n'est plus « délibérément écarté » **sans nuance**. Ce qui
  reste écarté, et l'a été par écrit avant tout code, est le **modèle génératif** (LaMa,
  Qwen-Image-Edit) — cf. `docs/mesures/relettrage-2026-08-28.md`. Un effacement **déterministe**
  existe depuis le lot 22 dans `manga/effacement.py` : masque d'encre dilaté rempli par la
  couleur de fond mesurée, ou reconstruit par diffusion en numpy pur. Il est **désarmé par
  défaut** (`manga.onomatopees.effacement.mode: "aucun"`) et n'efface jamais une zone dont la
  lecture n'est pas concordante.

## Le modèle, et pourquoi celui-là

`comic-text-detector` (dmMaze), export ONNX `mayocream/comic-text-detector-onnx`. Trois
sorties pour une entrée `[1, 3, 1024, 1024]` :

    blk  [1, 64512, 7]      tête YOLOv5 : boîtes de blocs de texte
    seg  [1, 1, 1024, 1024] masque de texte DENSE, déjà passé par sigmoïde
    det  [1, 2, 1024, 1024] cartes de lignes (style DBNet)

**On n'utilise que `seg`.** Mesuré sur les planches réelles du Vol.2, la tête `blk` rate
précisément ce qu'on vient chercher : page 63, elle propose 3 boîtes au-dessus de 0,5 —
toutes sur du petit texte horizontal — alors que la colonne de katakana géants qui barre la
planche est parfaitement dessinée dans `seg`. Une tête entraînée sur des *blocs de texte*
ne reconnaît pas un ゴォォォ de 400 px de haut ; un masque par pixel, si.

`seg` a un second avantage, décisif : il donne un **masque**, ce dont l'appariement
texte↔bulle a besoin (cf. `hors_des_bulles`).

Le RF-DETR 4 classes de *koharu* aurait fait les deux en une passe et mieux, mais il n'est
publié qu'en `safetensors` (il faudrait `torch` en dépendance dure) et ses poids sont sous
conditions Manga109 d'usage académique.

⚠ Licence : le code amont est GPL-3.0 et les poids sont entraînés pour partie sur
Manga109-s. À vérifier avant toute diffusion des planches produites — même vigilance que
pour les polices (cf. `templates/fonts/README.md`).
"""
from __future__ import annotations

import re

import numpy as np
from PIL import Image

from core import tokens

from ._config import fusion
from . import detection as detection_mod
from .detection import BubbleRegion, _letterbox
from .geometry import composantes, dilate
from .ocr import reading_order

INPUT_SIZE = 1024          # résolution d'entrée du modèle, fixe (pas de dimension dynamique)
SEUIL_MASQUE = 0.5

# ─────────────────────────────────────────────────────────────────────────────
# Fenêtrage de la passe HORS BULLE (lot 14, L6.1)
#
# Le même défaut que celui du détecteur de bulles, dans le même module, non corrigé : ce
# module letterboxait la bande **entière** dans 1024². Sur 1080×10 000,
# `r = min(1024/1080, 1024/10000) = 0,1024` — la planche occupe **110 colonnes sur 1 024**, le
# reste étant du gris. `text_detection` n'importait même pas `fenetres`.
#
# ## Ce que la mesure donne, avant de corriger quoi que ce soit
#
# ⚠ L'ancien plan affirmait que la passe est « structurellement inopérante sur bande ». C'est
# un raisonnement, et il est **faux**. Mesuré sur la bande 1 de *webtoon A* Chap.11 : le
# masque marque **6,65 % de la planche** (718 655 px) et rend **24 composantes**. La passe ne
# trouve donc pas « rien » ; elle trouve des taches, à une résolution où un ゴォォォ et un
# aplat de trame ne se distinguent plus.
#
# Ce que la mesure donne aussi, et qui n'était nulle part : **une inférence de ce modèle coûte
# 128 s sur une bande, avec un pic de mémoire de +746 Mo**. C'est, de loin, l'appel le plus
# cher de tout le pipeline — le détecteur de bulles, lui, tourne en ~1 s par fenêtre. C'est ce
# chiffre-là, et non un principe, qui dicte le réglage ci-dessous.
#
# ## Pourquoi des fenêtres PLUS HAUTES que celles des bulles
#
# Trois raisons, et aucune n'est un arrondi :
#
# 1. **Ce modèle tourne à 1024, l'autre à 640.** À hauteur de fenêtre égale, il voit déjà
#    1,6× plus grand. Une fenêtre de 3 072 px lui rend une occupation de **360 px sur 1 024**,
#    contre 110 pour la bande entière — 3,3× mieux — là où le détecteur de bulles a besoin de
#    2 160 px pour atteindre 512 à 640.
# 2. **Le recouvrement doit couvrir le TEXTE, pas la bulle.** Celui des bulles est calibré sur
#    « la plus haute bulle du corpus fait 833 px ». Une colonne de katakana géants est plus
#    haute : le cas mesuré du corpus paginé est déjà de **1 470 px** (cf. `config.yaml`,
#    page 63 du Vol.2). D'où 1 600, et non 900.
# 3. **Chaque fenêtre est une inférence pleine.** Reprendre 2 160/900 donnerait **8** fenêtres
#    sur une bande de 10 000 px, avec un recouvrement trop court pour le texte ; 3 072/1 600
#    en donne **6**, avec le recouvrement qu'il faut. On ne paie pas deux fois pour voir moins
#    bien.
#
# ## Pourquoi il n'y a RIEN à dédoublonner ici
#
# Le lot 12 (L4.5) a dû écrire un dédoublonnage de couture pour les bulles, parce que chaque
# fenêtre y produit des *régions* qu'il faut ensuite réunir. Ici, non : on réunit les
# **masques** (`|=`) avant de chercher les composantes. Un texte à cheval sur une couture est
# vu tronqué d'un côté, entier de l'autre, et l'union rend l'entier — puis `composantes` n'en
# trouve qu'un. Le problème ne se pose pas, plutôt que d'être résolu.
#
# ## Ce que ça COÛTE, et pourquoi l'interrupteur existe
#
# ⚠ **Une inférence de ce modèle coûte le même prix quelle que soit la taille de la planche.**
# Mesuré sur ce dépôt, trois tailles, même environnement : 1080×10 000 → 109 s, 1080×3 072 →
# 123 s, 1125×1 600 → 125 s. C'est logique et c'est ce qui rend l'arbitrage brutal : l'entrée
# est un carré de 1024 dans tous les cas, donc **fenêtrer multiplie le coût par le nombre de
# fenêtres, exactement**. Six fenêtres = six fois le prix, sans remise.
#
# ⚠ Ces secondes-là sont celles d'un environnement **CPU seul**. Le `perf.log` du run de
# référence (v1.4.0, avec `onnxruntime-directml`) donne **1,5 à 1,9 s** pour toute la passe sur
# une planche paginée — soit un rapport de ~65× entre les deux backends. Ne cite donc jamais
# « 110 s » comme une propriété du modèle : c'est une propriété de la machine. Ce qui est une
# propriété du modèle, c'est l'**invariance à la taille de la planche**, et elle vaut partout.
#
# ## Pourquoi le défaut est `true`, et ce qu'il a fallu deux bandes pour voir
#
# ⚠ **La première mesure disait le contraire, et une seule planche aurait suffi à livrer le
# mauvais défaut.** Rejeu, bande par bande (`docs/mesures/webtoon-2026-08-26.md`) :
#
#     planche 3 (dialogue, 13 bulles) · bande entière : 2,46 %, **0 zone**,             128 s
#     planche 3                       · fenêtrée (6)  : 1,97 %, **0 zone**,             787 s
#     planche 6 (action, 1 bulle)     · bande entière : 0,27 %, **0 zone**,             195 s
#     planche 6                       · fenêtrée (6)  : 0,64 %, **5 ZONES** (max 39 k), 927 s
#     planche 1 (liminaire illustré)  · bande entière : 6,65 %, 4 zones (max 480 k),    268 s
#     planche 1                       · fenêtrée (6)  : 5,62 %, 8 zones (max 285 k),  1 099 s
#
# · **Dialogue** : le fenêtrage ne fait que nettoyer le masque, sans rien changer au décompte.
# · **Action** : il rend **5 zones là où la passe pleine bande n'en trouvait aucune**, d'aires
#   1 227 à 39 607 px² — c'est-à-dire des tailles d'onomatopée. C'est exactement la planche
#   pour laquelle cette passe existe, et la passe pleine bande y est **aveugle**. C'est ce
#   cas-là qui décide.
# · **Liminaire illustré** : la nuance, et il faut l'écrire. Le fenêtrage double le nombre de
#   zones (4 → 8) et découpe le plus gros blob (480 001 → 285 444 px²) — mais 285 444 px² font
#   encore 2,6 % de la bande : les deux passes se trompent, la fenêtrée se trompe en plus petit
#   et plus souvent. ⚠ Cette planche nomme le prochain levier, que ce lot ne tire pas : il
#   n'existe aucune borne SUPÉRIEURE d'aire dans `hors_des_bulles`. Une borne se mesure.
#
# Autrement dit, la passe pleine bande n'est pas « un peu moins bonne » : elle est **aveugle
# là où la passe sert**, et son masque plus fourni sur la planche de dialogue était du bruit,
# pas de la sensibilité.
#
# ## Ce que ça coûte, et pourquoi c'est quand même le bon défaut
#
# ×4,8 à ×6,1, et le facteur est exact (une inférence par fenêtre). Deux raisons de l'armer
# malgré tout :
#
# 1. **Sur une planche paginée, ce réglage ne fait rigoureusement RIEN.** `fenetres()` rend
#    `[]` — une page occupe 720 px du canevas de 1024, très au-dessus du seuil. Le coût ne
#    tombe donc que sur les bandes, c'est-à-dire sur le format qu'il répare.
# 2. **Il est annoncé.** `masque_texte` écrit une ligne, une seule fois par détecteur, qui dit
#    le nombre de fenêtres, la raison, le coût et la clé pour l'éteindre. Un coût qu'on
#    découvre en regardant l'horloge est un défaut ; un coût annoncé est un arbitrage.
#
# `manga.onomatopees.fenetrage: false` rend exactement le comportement d'avant le lot.
DEFAUTS_FENETRE_SFX = {
    "fenetrage": True,
    "fenetre_hauteur": 3072,
    "fenetre_recouvrement": 1600,
}
# Part du petit côté de la planche servant de rayon de GROUPEMENT. Une onomatopée est faite
# de traits disjoints — les deux barres d'un ゴ sont deux composantes connexes. Sans
# groupement, une seule onomatopée produirait dix régions, donc dix appels d'OCR et dix
# gloses. Le rayon doit franchir l'espace entre traits d'un même signe sans souder deux
# signes voisins : 0,008 × 1125 ≈ 9 px sur les planches du tome.
GROUPEMENT_FRAC = 0.008
AIRE_MIN = 1200            # px² — en dessous, c'est du bruit de trame, pas du lettrage
# Aire minimale d'une COMPOSANTE CONNEXE, avant tout groupement (`hors_des_bulles`). À ne
# pas confondre avec `AIRE_MIN`, qui s'applique au groupe FUSIONNÉ, bien plus tard.
#
# ⚠ **Ce seuil n'est pas neutre, et le raisonnement évident est faux.** On aimerait écrire
# qu'il peut monter sans changer un résultat, au motif que la dilatation ne peut que faire
# grossir une composante. Il n'en est rien : `AIRE_MIN` est comparé à l'aire du groupe
# **fusionné**, pas à la composante. Un fragment passé sous ce seuil — un dakuten, un trait
# d'allongement, un éclat de glyphe — est supprimé alors qu'il aurait rejoint un groupe
# légitime, et le masque comme la boîte de ce groupe s'en trouvent changés. C'est
# exactement ce que `fusionner_proches` existe pour faire : la colonne ゴォォォ de la
# page 63 sortait en huit zones distinctes avant elle.
#
# 1 était le défaut historique, et il a un coût mesurable : `composantes` alloue un masque
# booléen **pleine page** par composante, et `hors_des_bulles` en alloue un second avec le
# `& masque`. Sur une planche 1125×1600 cela fait 1,8 Mo par composante ; sur une bande
# webtoon 1080×10 000, **10,8 Mo**. Et `fusionner_proches` boucle en O(n²) Python pur sur
# ces composantes, sans que rien ne borne leur nombre.
#
# Le défaut reste donc 1 — iso-comportement garanti — et la clé
# `manga.onomatopees.min_composante` permet de le relever après vérification d'équivalence
# sur le corpus. Le vrai remède au coût n'est de toute façon pas ce seuil mais le format du
# masque : un masque LOCAL avec sa boîte (lot 14) supprime le problème **sans toucher au
# résultat**.
MIN_COMPOSANTE = 1
CONTAINMENT_BULLE = 0.90   # au-delà, le texte est DANS une bulle, donc déjà traité
# Écart maximal entre deux fragments d'un MÊME texte, en fraction de la taille du plus petit
# des deux. Un rayon de dilatation fixe ne peut pas marcher ici : l'espacement d'une
# onomatopée est proportionnel à sa taille. Mesuré page 63 du Vol.2 — la colonne ゴォォォ est
# faite de glyphes de ~90 px séparés de ~30 px : à 9 px de dilatation elle sortait en
# **8 zones**, donc huit lectures d'OCR, huit lignes de traduction et huit gloses
# contradictoires posées le long d'un seul son. Le critère relatif les réunit en une.
VOISINAGE_FRAC = 0.60

# ─────────────────────────────────────────────────────────────────────────────
# Bornes HAUTES — lot 21, L21.1. **Livrées DÉSARMÉES**, et voici le chiffre.
#
# Le lot 14 avait nommé le levier sans le tirer : « il n'existe aucune borne SUPÉRIEURE
# d'aire dans `hors_des_bulles` ; c'est le prochain levier, et il se mesurera. » Il est
# mesuré. Le résultat est négatif, et il est livré tel quel.
#
# ## Ce que la mesure dit (`tools/banc_sfx.py --tous`, 2 456 zones, 6 tomes)
#
# La distribution d'aire est **continue** : aucun creux ne sépare le dessin du texte.
#
#     borne     zones rejetées   dont classées « texte » par `trier_zone`
#     0,05           648 (26 %)                557
#     0,10           364 (15 %)                313
#     0,20           178  (7 %)                147
#     0,30           110  (4 %)                 86
#
# ## Et la vérité terrain dit le contraire de ce qu'on attendait
#
# Sur l'échantillon de 60 zones transcrites à l'œil (graine 21, `docs/mesures/sfx-2026-08-28.md`),
# rangées par nature réelle :
#
#     nature réelle        n     aire médiane   aire maximale
#     onomatopée          14        3,4 %           32,3 %
#     dessin (aucun texte) 16       0,8 %            4,2 %
#     agrégat             14        5,3 %           26,1 %
#
# **Le dessin pris pour du texte est PLUS PETIT que les vraies onomatopées, pas plus
# grand.** Une borne haute couperait donc les onomatopées géantes — exactement ce que la
# passe existe pour trouver — et laisserait passer les faux positifs. La zone de 285 444 px²
# du liminaire, qui a suggéré ce levier, est un **agrégat** (plusieurs objets réunis dans une
# boîte), pas du dessin pur : le bon remède n'est pas de la jeter mais de la découper, et
# c'est un autre travail.
#
# ## Le garde-fou de FORME ne discrimine pas non plus
#
# `geometry.remplissage` sépare une bulle d'un masque bi-lobé (médiane 0,89 sur les 687
# bulles de plus de 20 000 px² du *manga A* Vol.1, 0,60-0,61 pour les deux faux doubles).
# Transposé au hors-bulle, il est **plat** : part d'encre médiane 0,457 sur les onomatopées
# de l'échantillon contre 0,456 sur le dessin pur, et 0,37 à 0,48 dans **toutes** les bandes
# d'aire du corpus. Il ne porte aucune information ici. C'était à mesurer ; c'est mesuré.
#
# ## Pourquoi les livrer quand même
#
# Parce qu'un scan d'une autre provenance peut se comporter autrement, et parce qu'un
# réglage désarmé documenté par sa mesure vaut mieux qu'une absence de réglage qu'il faudra
# re-mesurer. `0.0` = pas de borne, comportement d'avant le lot **au bit près**.
#
# ⚠ Et tout rejet est COMPTÉ (`diagnostic["rejets"]`), puis publié au rapport. Un filtre muet
# est la façon dont on perd les zones suivantes sans le voir.
AIRE_MAX_FRAC = 0.0        # 0 = pas de borne haute d'aire (mesure ci-dessus)
REMPLISSAGE_MAX = 0.0      # 0 = pas de borne haute de remplissage (mesure ci-dessus)


class TextDetector:
    """Enveloppe ONNX Runtime autour de `comic-text-detector`.

    Même forme que `detection.BubbleDetector` — et pour la même raison : séparer l'inférence
    (chère) du post-traitement (gratuit) rend un balayage de seuils abordable."""

    def __init__(self, model_path: str, providers: list[str] | None = None, *,
                 telechargement_auto: bool = True, model_url: str | None = None, dire=None):
        import onnxruntime as ort

        from . import models
        model_path = models.assurer_modele(
            model_path, url=model_url or models.TEXTE_URL,
            sha256=models.TEXTE_SHA256, octets_attendus=models.TEXTE_OCTETS,
            auto=telechargement_auto, quoi="de détection de texte", dire=dire)
        avail = ort.get_available_providers()
        wanted = providers or ["CPUExecutionProvider"]
        used = [p for p in wanted if p in avail] or ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(model_path), providers=used)
        self._input_name = self.session.get_inputs()[0].name

    @classmethod
    def depuis_config(cls, sfx_cfg: dict, det_cfg: dict, *, dire=None) -> "TextDetector":
        """Construit le détecteur de texte depuis `manga.onomatopees` (+ `providers`, qui
        vient de `manga.detection` : les deux modèles tournent sur le même backend).

        Point de construction unique, cf. `BubbleDetector.depuis_config`."""
        return cls(
            sfx_cfg.get("model_path", "manga_models/text_detector.onnx"),
            providers=det_cfg.get("providers"),
            telechargement_auto=bool(sfx_cfg.get("telechargement_auto", True)),
            model_url=sfx_cfg.get("model_url") or None, dire=dire)

    def masque_texte(self, image: Image.Image, *, seuil: float = SEUIL_MASQUE,
                     fenetrage: dict | None = None, dire=None) -> np.ndarray:
        """Masque booléen du texte de la planche, à la taille de l'image d'origine.

        Une bande très allongée est traitée **fenêtre par fenêtre** puis réunie (cf.
        `DEFAUTS_FENETRE_SFX`) ; une planche paginée passe par le chemin d'origine, inchangé —
        `fenetres()` rend `[]` et l'appel unique ci-dessous est exactement celui d'avant.

        `fenetrage` vient de `manga.onomatopees` : passer `None` désarme le découpage, ce qui
        est le comportement des appelants qui ne connaissent pas la config (tests, outils).
        `manga.onomatopees.fenetrage: false` le désarme aussi, explicitement — cf. le coût,
        qui se multiplie par le nombre de fenêtres et que l'utilisateur doit pouvoir refuser."""
        cfg = fusion(DEFAUTS_FENETRE_SFX, fenetrage) if fenetrage else {}
        bandes = (detection_mod.fenetres(*image.size, cfg, input_size=INPUT_SIZE)
                  if cfg.get("fenetrage", False) else [])
        if not bandes:
            return self._masque_dune_vue(image, seuil)
        largeur, hauteur = image.size
        # ⚠ ANNONCÉ, et une seule fois par détecteur — même discipline que le rabot de
        # recouvrement de `BubbleDetector`. Six inférences au lieu d'une est un fait que
        # l'utilisateur doit lire AVANT de se demander pourquoi son chapitre prend une heure,
        # pas après.
        if dire is not None and not getattr(self, "_fenetrage_annonce", False):
            self._fenetrage_annonce = True
            dire(f"[sfx] bande de {hauteur} px : le texte hors bulle est lu en "
                 f"{len(bandes)} fenêtre(s) de {cfg['fenetre_hauteur']} px — sans quoi la "
                 f"planche n'occuperait que "
                 f"{detection_mod.occupation(largeur, hauteur, INPUT_SIZE):.0f} px du canevas "
                 f"de {INPUT_SIZE}. Coût : {len(bandes)} inférences au lieu d'une "
                 f"(`manga.onomatopees.fenetrage: false` rend le comportement d'avant).")
        # Réunion par OU sur le masque PLEINE PAGE — 10,8 Mo sur une bande, alloué une fois.
        # C'est aussi ce qui rend tout dédoublonnage de couture inutile (cf. le module).
        masque = np.zeros((hauteur, largeur), dtype=bool)
        for y0, y1 in bandes:
            masque[y0:y1] |= self._masque_dune_vue(image.crop((0, y0, largeur, y1)), seuil)
        return masque

    def _masque_dune_vue(self, image: Image.Image, seuil: float) -> np.ndarray:
        """Une passe du réseau sur UNE vue, sans découpage. La partie chère : 128 s sur une
        bande entière, mesuré.

        ⚠ `seg` sort **déjà activé** (valeurs dans [0, 1]) : lui appliquer une sigmoïde de
        plus — le réflexe hérité de YOLOv8-seg, dont les prototypes sont des logits — ramène
        tout au-dessus de 0,5 et déclare 94 % de la planche « texte ». Constaté en mesurant."""
        w0, h0 = image.size
        tensor, _r, (dw, dh) = _letterbox(image, INPUT_SIZE)
        seg = self.session.run(None, {self._input_name: tensor})[1]
        carte = Image.fromarray((np.clip(seg[0, 0], 0.0, 1.0) * 255).astype(np.uint8))
        # Défaire le letterbox : retirer le padding gris, puis revenir à l'échelle d'origine.
        crop = (round(dw), round(dh), INPUT_SIZE - round(dw), INPUT_SIZE - round(dh))
        carte = carte.crop(crop).resize((w0, h0), Image.BILINEAR)
        return np.asarray(carte) >= seuil * 255


def _union_bulles(bulles: list[BubbleRegion], forme: tuple[int, int],
                  diagnostic: dict | None = None) -> np.ndarray:
    """Union des masques de bulles déjà détectés, à la forme de la planche.

    ⚠ **Un masque de forme inattendue était écarté sans un mot.** Aucun `warn`, aucun
    compteur, aucun retour : la fonction ne rendait que `union`. Et la cascade est brutale —
    `union` sort vide, `union.any()` est faux chez l'appelant, et **toutes** les répliques déjà
    prises en charge par une bulle sont re-détectées comme texte hors bulle : lues par
    `manga-ocr`, traduites une seconde fois comme glose, et listées au rapport.

    Quand cela arrive : dans le cas du fenêtrage. `detection._remonter` reconstruit un masque
    pleine hauteur, mais un masque relu d'un cache écrit avant un changement de découpage, ou
    une planche dont l'image a été remplacée entre deux runs, produit l'écart. Le pipeline a
    des garde-fous d'invalidation (`checkpoints.sens_perime`) et celui-ci passait dessous.

    `diagnostic` est rempli en place avec `{"masques_ecartes": int, "formes": [...]}` — le
    motif de `scinder_par_erosion`. Une condition `if` qui avale une incohérence est une dette
    qui se paie une fois par tome, au pire moment ; elle se paie ici en une ligne de rapport."""
    union = np.zeros(forme, dtype=bool)
    ecartes: list[str] = []
    for r in bulles:
        m = getattr(r, "mask", None)
        if m is None:
            continue
        if m.shape != forme:
            ecartes.append(f"{tuple(m.shape)} au lieu de {tuple(forme)}")
            continue
        union |= m
    if diagnostic is not None and ecartes:
        diagnostic["masques_ecartes"] = len(ecartes)
        diagnostic["formes"] = sorted(set(ecartes))
    return union


# ─────────────────────────────────────────────────────────────────────────────
# Mobilier de page (filigranes de scan) — lot 13
#
# ⚠ **CORRIGÉ au lot 21.** Ce bloc annonçait « 283 filigranes sur les 448 zones hors bulle
# du Vol.1 du *manga A* — 63 % » et « 105 sur 217 » pour le *manga B*. Les deux chiffres
# sont FAUX, et le commit qui les a écrits (v1.0.0, lot 13) porte lui-même la mesure qui les
# contredit, à trois lignes d'écart : « Vol.1 : 92 mobilier · 15 bruit latin · 81 ponctuation
# · 260 japonais », dont la somme fait 448 sans laisser de place à 283 filigranes. Le 283
# n'a jamais eu de dénominateur ; c'est précisément le cas que `docs/chiffres-de-reference.md`
# existe pour trancher.
#
# La mesure, rejouée sur les caches réels (`python tools/banc_sfx.py --tous`, 2026-08-28,
# 2 456 zones sur 6 tomes) : **92 sur 448 (20,5 %)** pour le Vol.1, **0 sur 217** pour le
# *manga B*. Et le plafond est structurel, pas paramétrique : un balayage complet de
# `MOBILIER_IOU` × `MOBILIER_FRAC_PLANCHES` ne dépasse jamais 181 zones sur le Vol.1, et
# seules 123 des 448 se trouvent à proximité d'une position récurrente. Le détecteur ne voit
# le filigrane que sur 47 et 45 planches sur 150 selon le groupe : ce n'est pas le filtre
# qui rate des filigranes, c'est la détection qui ne les trouve pas.
#
# Le gain reste réel — 92 lectures OCR et autant de zones de rapport économisées sur un
# tome — mais il vaut un cinquième de ce que le dépôt annonçait.
#
# Le discriminant n'est ni la position (un vrai texte peut occuper un coin) ni le contenu (l'OCR
# n'est pas fiable ici, cf. la réserve du mode « rapport ») : c'est la **récurrence
# géométrique**. Un filigrane revient à la MÊME place sur toutes les planches ; une onomatopée,
# jamais. C'est exactement le raisonnement que la brique LN tient déjà sur les bandeaux de PDF
# (`pipeline/extract.py`, `footer_frac_pages`), et on en reprend la formulation.
MOBILIER_FRAC_PLANCHES = 0.30
MOBILIER_IOU = 0.50
# Au-delà de cette part de la planche, une zone n'est jamais du mobilier : une onomatopée pleine
# page ne se répète pas d'une planche à l'autre, mais si elle le faisait on ne veut pas l'effacer
# du rapport pour autant.
MOBILIER_AIRE_MAX_FRAC = 0.05
# Sous ce nombre de planches, « récurrent » ne veut rien dire : deux bulles qui coïncident par
# hasard ne font pas un filigrane.
MOBILIER_MIN_PLANCHES = 3


def _iou_boites(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    aire_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    aire_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = aire_a + aire_b - inter
    return inter / union if union > 0 else 0.0


def mobilier_de_tome(pages: dict, *, frac_planches: float = MOBILIER_FRAC_PLANCHES,
                     iou: float = MOBILIER_IOU,
                     aire_max_frac: float = MOBILIER_AIRE_MAX_FRAC,
                     min_planches: int = MOBILIER_MIN_PLANCHES) -> tuple[set, list[dict]]:
    """Zones qui sont du **mobilier de page** et non du contenu.

    `pages` : `{numéro de planche: (liste de boîtes, (largeur, hauteur))}`.
    Renvoie `({(planche, index)}, groupes)` — `groupes` décrit ce qui a été écarté, pour que le
    rapport puisse le montrer et qu'un faux positif se voie.

    Regroupement glouton par recouvrement de boîtes : le coût est en O(zones × groupes), et il y
    a quelques centaines de zones par tome. Une zone ne peut jamais rejoindre un groupe où sa
    propre planche figure déjà — deux onomatopées superposées sur une même planche ne sont pas
    une récurrence."""
    porteuses = [p for p, (boites, _t) in pages.items() if boites]
    if len(porteuses) < min_planches:
        return set(), []

    groupes: list[dict] = []
    for planche in sorted(pages):
        boites, taille = pages[planche]
        largeur, hauteur = taille if taille else (0, 0)
        aire_page = max(1, int(largeur) * int(hauteur))
        for idx, boite in enumerate(boites):
            b = tuple(boite)
            aire = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
            if aire > aire_max_frac * aire_page:
                continue          # trop grande pour être un filigrane
            for g in groupes:
                if planche in g["planches"]:
                    continue
                if _iou_boites(b, g["boite"]) >= iou:
                    g["membres"].append((planche, idx))
                    g["planches"].add(planche)
                    break
            else:
                groupes.append({"boite": b, "membres": [(planche, idx)],
                                "planches": {planche}})

    seuil = max(min_planches, round(len(porteuses) * frac_planches))
    retenus = [g for g in groupes if len(g["planches"]) >= seuil]
    mobilier = {m for g in retenus for m in g["membres"]}
    description = [{"boite": list(g["boite"]), "planches": len(g["planches"]),
                    "zones": len(g["membres"])} for g in retenus]
    description.sort(key=lambda d: -d["planches"])
    return mobilier, description


# Lettres et chiffres, demi ou pleine chasse. Sur une source JAPONAISE, une zone hors bulle
# qui n'a aucun caractère japonais mais porte des lettres n'est pas du texte : c'est
# `manga-ocr` qui a halluciné sur du dessin (`ＥｌｅＨＴ`, `［ｉｓｕｃｅ］`, `ＯＦＦＦＩＮＥ`,
# `ＲａｙＬｉｎｇｅｒ．`). Un mot latin authentique dans une onomatopée japonaise est assez
# rare pour qu'on préfère le perdre.
_LETTRE_OU_CHIFFRE = re.compile(r"[A-Za-z0-9０-９Ａ-Ｚａ-ｚ]")

#: Deux lettres consécutives. Sur une source latine, c'est le signal INVERSE du précédent :
#: `KRAKOOM` est du contenu, tandis qu'une lettre isolée reste du dessin mal lu.
_MOT_LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]{2,}")

TRI_MOBILIER = "mobilier"        # récurrent à la même place — filigrane de scan
TRI_BRUIT = "bruit"              # ni texte ni ponctuation : hallucination d'OCR
TRI_PONCTUATION = "ponctuation"  # aucune lettre : `！！`, `．．．`, `〜`
TRI_TEXTE = "japonais"           # à traduire

#: ⚠ Ancien nom, conservé : c'est aussi la valeur PERSISTÉE (index de recherche,
#: `RAPPORT.md`). La renommer sur le disque invaliderait les index déjà écrits pour un gain
#: purement cosmétique.
TRI_JAPONAIS = TRI_TEXTE

#: Langues dont l'écriture est elle-même le signal de contenu (cf. `trier_zone`).
_LANGUES_CJK = frozenset({"jp", "ja", "zh", "ko"})


def trier_zone(texte: str, *, mobilier: bool = False, langue: str = "jp") -> str:
    """Que faire d'une zone hors bulle : l'écarter, la rendre sans LLM, ou la traduire.

    Mesuré sur les deux tomes rendus en v0.40.0 — 448 zones (manga A Vol.1) et 217 (manga B) :

    |                       | manga A | manga B |
    |-----------------------|--------:|-------:|
    | mobilier (écarté)     |      92 |      0 |
    | bruit latin (écarté)  |      15 |     12 |
    | ponctuation (sans LLM)|      81 |     47 |
    | texte (LLM)           |     260 |    158 |

    Soit **42 %** des zones du Vol.1 et **27 %** de celles de manga B retirées de la charge LLM,
    sans rien perdre de traduisible.

    ⚠ **Rejoué au lot 21** (`python tools/banc_sfx.py --tous`, 2026-08-28) sur les six tomes
    dont le cache porte la passe — les deux colonnes ci-dessus sortent **au chiffre près**, et
    voici les quatre autres :

    | tome           | zones | mobilier | bruit | ponctuation | texte |
    |----------------|------:|---------:|------:|------------:|------:|
    | manga A Vol.2  |   465 |      114 |    20 |          94 |   237 |
    | manga A Vol.3  |   379 |      129 |    14 |          43 |   193 |
    | manga A Vol.4  |   438 |        0 |    41 |          78 |   319 |
    | manga C Vol.1  |   509 |        0 |    12 |          55 |   442 |
    | **total (6)**  | 2 456 |      335 |   114 |         398 | 1 609 |

    ⚠ Et ce que le triage ne dit PAS, mesuré au lot 21 sur 60 zones transcrites à l'œil : la
    classe `japonais` ne veut pas dire « du texte ». **16 des 60 zones ne portent aucun
    texte** et 14 sont des agrégats mêlant onomatopée, bulle et dessin ; `trier_zone` les
    laisse toutes passer parce que `manga-ocr` a rendu une phrase japonaise plausible sur du
    dessin. Le triage écarte ce qu'il sait écarter — un filigrane, du latin, de la
    ponctuation — pas un faux positif de détection.

    ⚠ **L'heuristique s'INVERSE avec la langue source**, et c'est le point délicat de cette
    fonction. Sur une source japonaise, du latin signale une hallucination de `manga-ocr` et
    part au rebut. Appliquer cette règle à une source anglaise jetterait **toutes** les
    onomatopées de l'œuvre en silence. Sur une source latine, c'est donc le CJK qui devient
    le signal de bruit, et un mot latin qui devient du contenu.

    ⚠ La ponctuation n'est PAS du bruit. `！！` posé à côté d'un visage stupéfait est du
    contenu, et `latiniser` le rend fidèlement en `!!` — mieux qu'un LLM, qui pourrait
    broder."""
    t = (texte or "").strip()
    if mobilier:
        return TRI_MOBILIER
    if not t:
        return TRI_BRUIT

    if (langue or "jp").lower() in _LANGUES_CJK:
        if tokens.CJK_TEXTE.search(t):
            return TRI_TEXTE
        return TRI_BRUIT if _LETTRE_OU_CHIFFRE.search(t) else TRI_PONCTUATION

    # Source latine : le CJK est l'intrus (reliquat de scan, tampon d'éditeur), et seul un
    # vrai mot compte comme texte.
    if tokens.CJK_TEXTE.search(t):
        return TRI_BRUIT
    if _MOT_LATIN.search(t):
        return TRI_TEXTE
    return TRI_BRUIT if _LETTRE_OU_CHIFFRE.search(t) else TRI_PONCTUATION


def _boite(comp: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(comp)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _ecart(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Distance entre deux boîtes, 0 si elles se touchent ou se chevauchent."""
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return float(max(dx, dy))


def fusionner_proches(comps: list[np.ndarray], *,
                      facteur: float = VOISINAGE_FRAC) -> list[np.ndarray]:
    """Réunit les fragments d'un même texte, par un critère RELATIF à leur taille.

    Deux fragments appartiennent au même texte si l'écart entre leurs boîtes est inférieur à
    `facteur × taille du plus petit des deux`. C'est ce qui distingue les glyphes d'une même
    onomatopée (espacés proportionnellement à leur corps) de deux textes distincts, qu'un
    rayon de dilatation en pixels ne sait pas séparer : il faudrait qu'il soit grand pour
    réunir des katakana de 90 px, et petit pour ne pas souder deux répliques voisines.

    Union-find sur quelques dizaines de composantes — le coût quadratique est sans objet."""
    n = len(comps)
    if n < 2:
        return list(comps)
    boites = [_boite(c) for c in comps]
    # Taille caractéristique : le plus GRAND côté. Un `ー` d'allongement est un trait fin et
    # long — son petit côté vaut 5 px et le prendrait pour du bruit isolé.
    tailles = [max(b[2] - b[0], b[3] - b[1]) for b in boites]
    parent = list(range(n))

    def trouver(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            seuil = facteur * min(tailles[i], tailles[j])
            if _ecart(boites[i], boites[j]) <= seuil:
                ri, rj = trouver(i), trouver(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)

    # ⚠ Accumulation EN PLACE (`|=`), et une copie à la première insertion. `groupes[r] | comp`
    # allouait un masque **pleine page** neuf à chaque membre d'un groupe : sur une bande
    # webtoon 1080×10 000, c'est 10,8 Mo par union, et il y en a une par composante. La copie
    # initiale est indispensable — sans elle, le premier `|=` écrirait dans le tableau de
    # l'appelant. Résultat identique au bit, allocations divisées par la taille des groupes.
    groupes: dict[int, np.ndarray] = {}
    for i, comp in enumerate(comps):
        r = trouver(i)
        if r not in groupes:
            groupes[r] = comp.copy()
        else:
            groupes[r] |= comp
    return list(groupes.values())


def hors_des_bulles(masque: np.ndarray, bulles: list[BubbleRegion], *,
                    containment: float = CONTAINMENT_BULLE,
                    groupement: int = 0, aire_min: int = AIRE_MIN,
                    voisinage: float = VOISINAGE_FRAC,
                    min_composante: int = MIN_COMPOSANTE,
                    aire_max_frac: float = AIRE_MAX_FRAC,
                    remplissage_max: float = REMPLISSAGE_MAX,
                    sens: str = "droite_gauche",
                    diagnostic: dict | None = None) -> list[BubbleRegion]:
    """Régions de texte qui ne sont PAS dans une bulle déjà détectée.

    L'appariement se fait par **containment de masques**, l'idée la plus directement
    réutilisable de *koharu* (`stages/detection.rs`) :

        part_dans_bulle = |texte ∩ bulle| / |texte|

    et non par IoU de boîtes. L'IoU compare deux aires globales : une réplique de 200 px²
    dans un ballon de 40 000 px² donne un IoU de 0,005 et serait déclarée « hors bulle »,
    alors qu'elle y est entièrement. Le containment répond à la seule question qui compte —
    *ce texte est-il déjà pris en charge ?* — et vaut ici 1,0.

    Le groupement précède l'appariement : on dilate, on étiquette, **puis** on érode le
    résultat pour rendre à chaque région son contour réel. Dilater sans rendre gonflerait le
    masque de glose et mordrait sur le dessin.

    `sens` vient du FORMAT de la planche, comme partout ailleurs dans la chaîne
    (`manga.formats.sens_lecture`). ⚠ Jusqu'au lot 13, le tri était **codé en dur** en
    droite→gauche ici, et c'était le seul endroit du pipeline à ignorer le sens de lecture du
    format : sur un webtoon, dont les bulles sont pourtant ordonnées correctement par
    `ocr.reading_order(regions, "gauche_droite")`, les onomatopées étaient numérotées **à
    l'envers**. Le rapport les listait donc dans un ordre qui ne correspondait à rien, et le
    prompt de `_translate_sfx` les présentait au modèle dans cet ordre-là.

    ⚠ Le même défaut avait déjà été corrigé une fois ailleurs : `document.poser_regions`
    appelait `reading_order()` sans le sens, si bien que la moindre édition de zone depuis
    l'interface re-triait TOUTE la planche en ordre manga. `tools/verifier_ordre.py` est le
    test de non-régression de cette correction, et il vaut pour celle-ci.

    `aire_max_frac` et `remplissage_max` sont les deux bornes HAUTES du lot 21, **désarmées
    par défaut** (`0.0`) : la mesure ne les soutient pas, et le chiffre qui l'explique est
    sous `AIRE_MAX_FRAC`. Les armer sur un corpus qui se comporterait autrement reste
    possible, et tout rejet est compté.

    `diagnostic` remonte ce que l'appariement a dû écarter — cf. `_union_bulles` — et, sous
    la clé `rejets`, le nombre de zones écartées **par motif** (`aire_min`, `aire_max`,
    `remplissage_max`, `dans_bulle`), cumulé sur les appels successifs."""
    forme = masque.shape
    union = _union_bulles(bulles, forme, diagnostic)
    rayon = int(groupement) if groupement else max(2, round(min(forme) * GROUPEMENT_FRAC))

    # Le groupement ne sert QU'À décider ce qui fait région ; les pixels rendus restent ceux
    # du masque d'origine (`comp & masque`).
    groupe = dilate(masque, rayon)
    # Deux étages de groupement, et ils ne font pas le même travail : la dilatation soude les
    # TRAITS d'un même glyphe (elle est en pixels, calée sur la finesse du lettrage), la
    # fusion relative réunit les GLYPHES d'un même texte (elle est proportionnelle, calée sur
    # leur corps). Aucun rayon unique ne peut faire les deux.
    # ⚠ `min_composante` s'applique AVANT la fusion, donc à des fragments qui peuvent encore
    # rejoindre un groupe légitime (cf. `MIN_COMPOSANTE`). Le relever n'est pas gratuit : c'est
    # une vérification d'équivalence sur le corpus, pas un raisonnement.
    # `&=` en place : `composantes` rend des tableaux NEUFS, dont on est seul propriétaire.
    # `c & masque` en allouait un second, pleine page, par composante — 1,08 Mo sur une bande,
    # multiplié par les deux mille composantes qu'une planche d'action peut produire.
    bruts = []
    for c in composantes(groupe, min_aire=max(1, int(min_composante))):
        c &= masque
        bruts.append(c)
    # ⚠ Tout rejet est COMPTÉ par motif. Un filtre muet est la façon dont on perd les zones
    # suivantes sans le voir — et les deux bornes hautes sont désarmées par défaut
    # précisément parce que la mesure ne les soutient pas (cf. `AIRE_MAX_FRAC`).
    rejets = {"aire_min": 0, "aire_max": 0, "remplissage_max": 0, "dans_bulle": 0}
    aire_page = max(1, int(forme[0]) * int(forme[1]))
    regions: list[BubbleRegion] = []
    for reel in fusionner_proches(bruts, facteur=voisinage):
        aire = int(reel.sum())
        if aire < aire_min:
            rejets["aire_min"] += 1
            continue
        ys, xs = np.nonzero(reel)
        if ys.size == 0:
            continue
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        # L'aire comparée est celle du MASQUE, comme `aire_min` : deux seuils qui bornent la
        # même grandeur par le haut et par le bas doivent la mesurer pareil, sans quoi une
        # onomatopée fine dans une grande boîte tomberait entre les deux.
        if aire_max_frac > 0 and aire > aire_max_frac * aire_page:
            rejets["aire_max"] += 1
            continue
        if remplissage_max > 0:
            boite = max(1, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
            if aire / boite > remplissage_max:
                rejets["remplissage_max"] += 1
                continue
        if union.any():
            dedans = int((reel & union).sum())
            if aire and dedans / aire >= containment:
                rejets["dans_bulle"] += 1
                continue          # déjà dans une bulle : traité par le chemin nominal
        regions.append(BubbleRegion(bbox=bbox, mask=reel, score=1.0, cls=0,
                                    kind="onomatopee"))
    if diagnostic is not None and any(rejets.values()):
        cumul = diagnostic.setdefault("rejets", {})
        for motif, n in rejets.items():
            if n:
                cumul[motif] = cumul.get(motif, 0) + n
    # Ordre de lecture du FORMAT, et par la MÊME fonction que les bulles. Entretenir deux
    # ordres de lecture différents dans le même pipeline est précisément la dette qui a produit
    # `tools/verifier_ordre.py` — et `reading_order` fait de toute façon mieux qu'un tri par
    # abscisse, puisqu'il coupe en X-Y sur les gouttières (`ocr._coupe_xy`) : sur une planche
    # d'action, deux onomatopées appartenant à deux cases distinctes ne s'entrelacent plus.
    return reading_order(regions, sens)
