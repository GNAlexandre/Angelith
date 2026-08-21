# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""OCR des tranches — la seule partie de la brique qui charge un modèle.

## Pourquoi `manga-ocr` et pas autre chose

C'est le modèle que le dépôt utilise déjà, il est japonais, il lit le vertical, il tourne
hors ligne et il est déjà en cache. `manga/ocr.py` porte en outre tout le raisonnement sur
la révision figée et le mode hors ligne, qu'on n'a aucune envie de réécrire.

Tesseract `jpn_vert` lirait une colonne entière d'un coup et serait donc plus rapide ; il
demande un binaire externe, ses données de langue, et sa qualité sur ce matériau n'est pas
mesurée. On reste sur le modèle mesuré.

## Le garde-fou, et pourquoi il est gratuit

`scan/grille.py` sait combien de caractères une colonne contient — c'est sa hauteur divisée
par le pas. L'OCR rend une chaîne. Comparer les deux ne coûte rien et attrape exactement le
mode d'échec mesuré : la colonne entière de 40 caractères rendue en 23. Une colonne dont la
lecture s'écarte trop du compte prédit (cf. `ECART_SUSPECT`) est relue **une fois**, avec un
découpage décalé d'une demi-tranche — refaire le même découpage redonnerait exactement la
même hallucination, le modèle étant déterministe.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from . import assemblage
from .grille import Colonne, PlanPage, coupes_de_colonne

# Marge autour d'une tranche. `manga-ocr` a été entraîné sur des imagettes de manga, traits
# d'origine compris : un cadrage au pixel près le prive du contexte dont l'encodeur se sert
# (cf. `manga/ocr.py:region_rectangulaire`, où la mesure est faite).
MARGE = 8
LOT = 16
# Écart toléré entre le nombre de cases prédit par la grille et le nombre lu.
#
# ⚠ `cases` est une PRÉDICTION approchée, pas un compte. Elle vaut hauteur / pas, où `pas`
# est la largeur d'encre médiane des colonnes (63 px page 100) et non l'avance typographique
# réelle (~67 px) : les approches latérales du glyphe manquent à la mesure, si bien que la
# grille surestime d'environ 7 %. J'ai essayé de retrouver l'avance en cherchant le pas qui
# rend les hauteurs de colonnes les plus proches de multiples entiers ; sur cinq pages, il
# ressort entre 0,92 et 1,33 fois la largeur médiane, pour un résidu à peine meilleur que le
# hasard. L'estimateur ne tient pas, et une calibration fragile serait pire qu'un seuil large
# assumé.
#
# D'où 25 % plutôt que 20 : assez lâche pour absorber ce biais sans signaler de bonnes
# colonnes, assez serré pour attraper le mode d'échec réel — la colonne de 40 caractères
# rendue en 23, soit −42 %.
ECART_SUSPECT = 0.25
# Sous ce nombre de cases, l'écart relatif ne veut rien dire : une colonne de trois
# caractères lue en quatre est à 33 % d'écart et parfaitement correcte.
CASES_MIN_CONTROLE = 6


@dataclass
class ResultatColonne:
    texte: str
    tranches: list[str]
    ruby: list[str]
    suspecte: bool = False
    relue: bool = False

    def en_dict(self) -> dict:
        return {"texte": self.texte, "tranches": self.tranches, "ruby": self.ruby,
                "suspecte": self.suspecte, "relue": self.relue}


class Lecteur:
    """Enveloppe de lot autour de `manga-ocr`.

    `manga.ocr.MangaOCR` résout le cache hors ligne et fige la révision du modèle ; on
    l'instancie pour cela, puis on descend jusqu'au modèle qu'il porte pour traiter un LOT
    d'images en un appel. `MangaOcr.__call__` ne prend qu'une image à la fois, et une page
    en demande une soixantaine.

    Mesuré : 0,655 s/tranche une par une, 0,488 s/tranche par lots de 16 — et **sortie
    identique**, ce qu'un test verrouille. Le gain est modeste parce que le décodage
    autorégressif domine ; il est pris quand même, il représente vingt minutes sur un tome."""

    def __init__(self, cfg: dict | None = None, *, lot: int = LOT, dire=None):
        from manga.ocr import MangaOCR
        self._enveloppe = MangaOCR(cfg or {}, dire=dire)
        self._mocr = self._enveloppe._mocr
        self.lot = max(1, int(lot))

    def lire(self, images: list[Image.Image]) -> list[str]:
        if not images:
            return []
        import torch
        from manga_ocr.ocr import post_process

        sorties: list[str] = []
        for debut in range(0, len(images), self.lot):
            paquet = [im.convert("L").convert("RGB") for im in images[debut:debut + self.lot]]
            pixels = self._mocr.processor(paquet, return_tensors="pt").pixel_values
            with torch.no_grad():
                jetons = self._mocr.model.generate(pixels.to(self._mocr.model.device),
                                                   max_length=300)
            sorties.extend(post_process(self._mocr.tokenizer.decode(j, skip_special_tokens=True))
                           for j in jetons.cpu())
        return sorties


# --------------------------------------------------------------------------- #
#  Découpe d'une colonne en imagettes
# --------------------------------------------------------------------------- #

def _bord_droit(colonne: Colonne) -> int:
    """Où s'arrêter à droite d'une colonne.

    En vertical, les furigana se posent à DROITE de leur graphie, à quelques pixels : la
    marge de confort passerait dessus et l'OCR lirait la lecture en alternance avec le texte
    de base, ce qui détruit la ligne entière. Quand la colonne porte des ruby, la marge
    droite s'arrête donc juste avant elles."""
    limite = colonne.x1 + MARGE
    if colonne.ruby:
        limite = min(limite, min(r[0] for r in colonne.ruby) - 2)
    return max(colonne.x1, limite)


def imagettes_de_colonne(image: Image.Image, colonne: Colonne,
                         tranches: list[tuple[int, int]] | None = None) -> list[Image.Image]:
    """Les tranches d'une colonne, prêtes pour l'OCR."""
    largeur, hauteur = image.size
    x0 = max(0, colonne.x0 - MARGE)
    x1 = min(largeur, _bord_droit(colonne))
    sorties = []
    bornes = tranches if tranches is not None else colonne.tranches()
    for i, (a, b) in enumerate(bornes):
        haut = max(0, a - (MARGE if i == 0 else 1))
        bas = min(hauteur, b + (MARGE if i == len(bornes) - 1 else 1))
        sorties.append(image.crop((x0, haut, x1, bas)))
    return sorties


def imagettes_de_ruby(image: Image.Image, colonne: Colonne) -> list[Image.Image]:
    largeur, hauteur = image.size
    return [image.crop((max(0, x0 - 2), max(0, y0 - MARGE),
                        min(largeur, x1 + 2), min(hauteur, y1 + MARGE)))
            for x0, x1, y0, y1 in colonne.ruby]


# --------------------------------------------------------------------------- #
#  Lecture d'une page
# --------------------------------------------------------------------------- #

def cellules(texte: str) -> int:
    """Nombre de CASES qu'occupe un texte lu — pas son nombre de caractères.

    `manga_ocr.post_process` développe `…` en trois points : une cellule de la grille en
    ressort à trois caractères. Sans cette normalisation, toute réplique à points de
    suspension serait déclarée suspecte et relue pour rien.

    ⚠ Le comptage délègue à `assemblage.restaurer_points`, et ce n'est pas de la
    mutualisation de confort : les deux répondent à la MÊME question — combien de cellules
    de la page ces points représentent-ils. Une première version en tenait deux réponses,
    l'une repliant toute suite de points sur une seule cellule, l'autre par groupes de
    trois. Le garde-fou et le document auraient alors compté différemment le même texte."""
    return len(assemblage.restaurer_points(texte or ""))


def est_suspecte(colonne: Colonne, texte: str) -> bool:
    """La lecture contredit-elle la grille ?

    Le test ne s'applique qu'aux colonnes d'au moins six cases : en deçà, l'écart relatif
    est du bruit — une colonne de trois caractères lue en quatre est à 33 % d'écart et
    parfaitement correcte. C'est exactement le détecteur qui aurait signalé la colonne de
    40 caractères rendue en 23."""
    if colonne.cases < CASES_MIN_CONTROLE:
        return False
    return abs(cellules(texte) - colonne.cases) > ECART_SUSPECT * colonne.cases


def lire_page(lecteur, image: Image.Image, plan: PlanPage, *, encre=None,
              caracteres_par_tranche: int | None = None) -> list[ResultatColonne]:
    """Lit toutes les colonnes de corps d'une page, dans l'ordre de lecture.

    Un seul appel de lot pour toute la page (tranches et ruby confondues) : le modèle est
    la ressource chère, et le rappeler colonne par colonne perdrait le peu que le lot
    apporte.

    `encre` (le masque binaire de la page) n'est nécessaire que pour la relecture décalée
    d'une colonne suspecte, qui doit retrouver les gouttières. Sans lui, une colonne suspecte
    est signalée mais pas relue — ce qui reste correct, et évite d'imposer le masque aux
    appelants qui n'en ont pas."""
    colonnes = plan.corps
    if not colonnes:
        return []

    imagettes: list[Image.Image] = []
    plages: list[tuple[int, int, int, int]] = []   # (indice colonne, début, fin, nb ruby)
    for i, col in enumerate(colonnes):
        tranches = imagettes_de_colonne(image, col)
        rubis = imagettes_de_ruby(image, col)
        plages.append((i, len(imagettes), len(imagettes) + len(tranches), len(rubis)))
        imagettes.extend(tranches)
        imagettes.extend(rubis)

    lues = lecteur.lire(imagettes)

    resultats: list[ResultatColonne] = []
    for i, debut, fin, n_ruby in plages:
        morceaux = lues[debut:fin]
        rubis = lues[fin:fin + n_ruby]
        texte = "".join(morceaux)
        resultats.append(ResultatColonne(texte=texte, tranches=list(morceaux),
                                         ruby=list(rubis),
                                         suspecte=est_suspecte(colonnes[i], texte)))

    if encre is not None:
        _relire_suspectes(lecteur, image, encre, plan, resultats,
                          caracteres_par_tranche=caracteres_par_tranche)
    return resultats


def _relire_suspectes(lecteur, image: Image.Image, encre, plan: PlanPage,
                      resultats: list[ResultatColonne], *,
                      caracteres_par_tranche: int | None = None) -> None:
    """Relit **une fois** les colonnes suspectes, avec un découpage décalé d'une demi-tranche.

    On garde la lecture dont la longueur colle le mieux à la grille. Rejouer le même
    découpage n'aurait aucun intérêt : le modèle est déterministe, et la coupe malheureuse
    qui a produit l'hallucination se reproduirait à l'identique."""
    colonnes = plan.corps
    a_relire = [i for i, r in enumerate(resultats) if r.suspecte]
    if not a_relire:
        return

    kwargs = {}
    if caracteres_par_tranche:
        kwargs["caracteres"] = caracteres_par_tranche

    imagettes: list[Image.Image] = []
    plages = []
    for i in a_relire:
        col = colonnes[i]
        coupes, _cases, _forcee = coupes_de_colonne(
            encre, (col.x0, col.x1, col.y0, col.y1), plan.pas, decalage=0.5, **kwargs)
        bornes = [col.y0, *coupes, col.y1]
        tranches = [(a, b) for a, b in zip(bornes, bornes[1:]) if b > a]
        morceaux = imagettes_de_colonne(image, col, tranches)
        plages.append((i, len(imagettes), len(imagettes) + len(morceaux)))
        imagettes.extend(morceaux)

    lues = lecteur.lire(imagettes)
    for i, debut, fin in plages:
        col = colonnes[i]
        candidat = "".join(lues[debut:fin])
        resultats[i].relue = True
        if abs(len(candidat) - col.cases) < abs(len(resultats[i].texte) - col.cases):
            resultats[i].texte = candidat
            resultats[i].tranches = list(lues[debut:fin])
        resultats[i].suspecte = est_suspecte(col, resultats[i].texte)
