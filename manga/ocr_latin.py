# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""OCR des bulles en écriture LATINE (et cyrillique, hangûl…), via RapidOCR / PP-OCRv4.

Pourquoi ce module existe — le défaut qu'il corrige
---------------------------------------------------
`manga/ocr.py` charge `kha-white/manga-ocr-base`, un ViT+BERT entraîné sur du **japonais
manga vertical**. Son décodeur n'a tout simplement **pas de token d'espace** : le japonais
n'en écrit pas. Lui donner de l'anglais ne produit donc pas « un OCR un peu moins bon »,
mais une sortie structurellement fausse, mesurée sur *webtoon A* Chap.11 :

    HE'S CERTAINLY NO ORDINARY PERSON  →  ＨＥＳＣＥＲＴＡＮＡＹＮＯＯＯＲＤＩＮＡＲＹＰＥＲＳＯＮ
    (une date)                         →  ２０１６年１０月１９日に２０日   ← kanji INVENTÉS

Les kanji hallucinés déclenchaient ensuite le garde-fou `japonais_residuel`, brûlaient les
relances, puis étaient supprimés au rendu faute de glyphe dans la police de lettrage. Toute
la cascade de ce run vient de là.

RapidOCR (PP-OCRv4 exporté en ONNX) rend des boîtes de LIGNE avec leur texte et leur
confiance, espaces compris. Il tourne sur `onnxruntime`, qui est déjà une dépendance de la
brique manga pour le détecteur de bulles, embarque ses modèles dans la roue (~15 Mo) et
n'exige ni torch ni réseau.

⚠ Limite mesurée, et assumée : le DÉTECTEUR de RapidOCR rate parfois une bulle de
ponctuation seule (`...`), que manga-ocr lisait. Le repli évident — relancer la seule
reconnaissance sur le crop entier (`use_det=False`) — a été essayé et REJETÉ : sur la bulle
en question il rend `福`, c'est-à-dire qu'il invente. Mieux vaut une bulle vide, que le
rapport signale, qu'un caractère inventé qui traverse toute la chaîne.

Ce module expose délibérément la MÊME surface d'API que `MangaOCR` (`read`, `read_all`) pour
être interchangeable avec lui derrière `manga/ocr_routeur.py`, et réutilise tels quels
`masked_crop`, `region_rectangulaire` et `fond_pour_texte` — qui sont agnostiques de la
langue."""
from __future__ import annotations

import re

from PIL import Image

from ._config import fusion
from .detection import BubbleRegion
from .ocr import _DEFAUTS_OCR, masked_crop

#: Modèle de reconnaissance par langue. RapidOCR livre `ch` (chinois **+ latin**, c'est son
#: modèle par défaut et il lit très bien l'anglais), `en`, `korean`, `japan`, `cyrillic`…
#: On ne descend au modèle spécialisé que quand il apporte vraiment quelque chose.
MODELE_REC: dict[str, str] = {
    "ko": "korean",
    "zh": "ch",
}

#: Confiance en dessous de laquelle une ligne est jetée. PP-OCRv4 est franc : sur du
#: lettrage BD propre il rend 0.90+, et ce qu'il donne sous ce seuil est du dessin lu comme
#: du texte. Le laisser passer ferait halluciner le traducteur — exactement le défaut qu'on
#: est en train de corriger.
SEUIL_CONFIANCE = 0.50

#: Deux lignes appartiennent à la même LIGNE VISUELLE si leurs centres verticaux sont plus
#: proches que cette fraction de la hauteur de ligne. Sert à recomposer un texte de bulle
#: coupé en deux boîtes côte à côte.
TOLERANCE_LIGNE = 0.60

_ESPACES = re.compile(r"\s+")


class OCRLatin:
    """Charge PP-OCRv4 une seule fois (coûteux) puis lit des bulles à la volée."""

    def __init__(self, cfg: dict | None = None, *, langue: str = "en", dire=None):
        self.langue = (langue or "en").lower()
        rec = MODELE_REC.get(self.langue)
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as err:
            raise SystemExit(
                f"OCR : la source est en « {self.langue} », ce qui demande un OCR latin — "
                f"`rapidocr-onnxruntime` n'est pas installé.\n"
                f"  → pip install rapidocr-onnxruntime\n"
                f"  ⚠ si tu utilises `onnxruntime-directml` (mutuellement exclusif avec "
                f"`onnxruntime`), installe avec `--no-deps` pour ne pas te le faire "
                f"réinstaller par-dessus.\n"
                f"  détail : {err}") from err

        options: dict = {}
        if rec:
            # RapidOCR nomme ses modèles embarqués ; on ne passe la clé que si on dévie du
            # défaut, pour ne pas casser à la moindre évolution de leur nomenclature.
            options["Rec.lang_type"] = rec
        try:
            self._ocr = RapidOCR(**options) if options else RapidOCR()
        except (TypeError, ValueError):
            # Version de RapidOCR qui ne connaît pas cette option : le modèle par défaut
            # (`ch`, latin compris) reste un choix correct. Mieux vaut lire que s'arrêter.
            if dire is not None and rec:
                dire(f"OCR : modèle « {rec} » indisponible dans cette version de RapidOCR — "
                     f"repli sur le modèle par défaut (latin pris en charge).")
            self._ocr = RapidOCR()

    # ------------------------------------------------------------------ #

    def read(self, image: Image.Image, region: BubbleRegion,
             background: tuple[int, int, int] | None = None,
             cfg: dict | None = None) -> str:
        """Lit une bulle. Même contrat que `MangaOCR.read` : la bulle est **isolée** de son
        voisinage avant l'OCR, et `background` est la couleur mesurée de la bulle."""
        c = fusion(_DEFAUTS_OCR, cfg)
        if not c["masquer_hors_bulle"]:
            crop = image.crop(region.bbox)
        else:
            crop = masked_crop(
                image, region, background=background or (255, 255, 255),
                marge=int(c["marge_crop"]), agrandissement_min=int(c["agrandissement_min"]))
        return self._lire_image(crop)

    def read_all(self, image: Image.Image, regions: list[BubbleRegion],
                 styles: list | None = None, cfg: dict | None = None) -> list[str]:
        """Lit toutes les bulles, dans l'ordre reçu (= l'ordre de lecture persisté)."""
        sorties: list[str] = []
        for i, r in enumerate(regions):
            fond = None
            if styles is not None and i < len(styles) and getattr(styles[i], "ok", False):
                fond = styles[i].background
            sorties.append(self.read(image, r, background=fond, cfg=cfg))
        return sorties

    # ------------------------------------------------------------------ #

    def _lire_image(self, crop: Image.Image) -> str:
        import numpy as np
        resultat, _elapsed = self._ocr(np.asarray(crop.convert("RGB")))
        return recomposer(resultat)


def recomposer(resultat, seuil: float = SEUIL_CONFIANCE) -> str:
    """Assemble les boîtes de ligne de RapidOCR en un texte de bulle.

    `resultat` est la liste `[boite, texte, confiance]` que rend RapidOCR, ou `None` quand
    il n'a rien vu (bulle vide, ou fausse détection sur du dessin — cas fréquent et normal).

    Le latin s'écrit horizontalement : on ordonne haut→bas, puis gauche→droite à l'intérieur
    d'une même ligne visuelle. ⚠ Cet ordre-là est bien celui de la LANGUE, pas celui du
    format : même dans un manga japonais lu droite→gauche, une bulle anglaise se lit de
    gauche à droite. Le sens de lecture du format ordonne les BULLES entre elles
    (`ocr.reading_order`), pas les lignes DANS une bulle."""
    if not resultat:
        return ""

    lignes = []
    for entree in resultat:
        try:
            boite, texte, score = entree[0], entree[1], float(entree[2])
        except (IndexError, TypeError, ValueError):
            continue
        texte = (texte or "").strip()
        if not texte or score < seuil:
            continue
        ys = [float(p[1]) for p in boite]
        xs = [float(p[0]) for p in boite]
        lignes.append(((min(ys) + max(ys)) / 2, min(xs), max(ys) - min(ys), texte))

    if not lignes:
        return ""

    hauteur = max(1.0, sum(l[2] for l in lignes) / len(lignes))
    lignes.sort(key=lambda l: (l[0], l[1]))

    # Regroupement en lignes visuelles : deux boîtes côte à côte forment une seule ligne.
    groupes: list[list[tuple]] = [[lignes[0]]]
    for ligne in lignes[1:]:
        if abs(ligne[0] - groupes[-1][0][0]) <= hauteur * TOLERANCE_LIGNE:
            groupes[-1].append(ligne)
        else:
            groupes.append([ligne])

    morceaux = [" ".join(l[3] for l in sorted(g, key=lambda l: l[1])) for g in groupes]
    return _ESPACES.sub(" ", " ".join(morceaux)).strip()
