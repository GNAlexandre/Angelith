# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Fabrique de pages de roman japonais SYNTHÉTIQUES pour les tests de la brique scan.

Aucun asset externe, aucun contenu protégé : les pages sont dessinées à la volée avec
Pillow et une police système. Le point important est qu'elles reproduisent la GÉOMÉTRIE
d'une page réelle — pas de texte lisible, seulement une grille de cellules d'encre à la
bonne échelle. C'est cette géométrie que `scan/grille.py` mesure, donc c'est elle qu'il
faut simuler ; le contenu des glyphes ne joue aucun rôle.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Échelle réduite d'un scan réel : pas de 40 px au lieu de 63, mêmes RAPPORTS — c'est le
# seul point qui compte. Un caractère japonais occupe ~0,88 de son avance ; une maquette qui
# lui en donnerait 0,75 exagérerait de moitié l'écart entre la largeur d'encre mesurée et
# l'avance réelle, et ferait échouer les tests sur un défaut qui n'existe pas à l'échelle
# du matériau (63 px d'encre pour ~67 px d'avance, soit 6 %).
PAS = 40
ENCRE_FRAC = 0.88
PITCH = 76            # entraxe des colonnes (place réservée aux ruby comprise)
MARGE_HAUT = 120
MARGE_DROITE = 80
BLANC = 255
NOIR = 20


@dataclass
class PageFactice:
    largeur: int
    hauteur: int
    colonnes: list[dict] = field(default_factory=list)

    def image(self):
        from PIL import Image
        return Image.fromarray(self.tableau(), mode="L")

    def tableau(self) -> np.ndarray:
        arr = np.full((self.hauteur, self.largeur), BLANC, dtype=np.uint8)
        for col in self.colonnes:
            _peindre(arr, col)
        return arr


def _peindre(arr: np.ndarray, col: dict) -> None:
    """Une colonne = des cellules d'encre séparées par de vraies gouttières.

    Le glyphe occupe `ENCRE_FRAC` × pas et laisse donc le reste en blanc entre deux
    cellules — assez large pour que `CREUX_COUPE_FRAC` (0,15 × pas) y voie des frontières,
    et assez étroit pour reproduire le vrai rapport encre/avance d'un caractère imprimé."""
    pas = col.get("pas", PAS)
    encre = round(pas * ENCRE_FRAC)
    for k in range(col["cases"]):
        haut = col["y0"] + k * pas
        arr[haut:haut + encre, col["x0"]:col["x0"] + col.get("largeur", encre)] = NOIR


def page(colonnes: list[dict], *, largeur: int = 1400, hauteur: int = 1800) -> PageFactice:
    """`colonnes` décrit, de DROITE à gauche : `{"cases": n, "indent": bool}`."""
    faite = []
    for i, spec in enumerate(colonnes):
        x0 = largeur - MARGE_DROITE - (i + 1) * PITCH
        y0 = MARGE_HAUT + (PAS if spec.get("indent") else 0)
        faite.append({"x0": x0, "y0": y0, "cases": spec["cases"],
                      "pas": spec.get("pas", PAS),
                      "largeur": spec.get("largeur", round(PAS * ENCRE_FRAC))})
    return PageFactice(largeur=largeur, hauteur=hauteur, colonnes=faite)


def poser_numero(page_factice: PageFactice, x: int | None = None, y: int = 40) -> None:
    """Ajoute un numéro de page en marge haute — deux petits blocs d'encre."""
    x = page_factice.largeur - MARGE_DROITE - 20 if x is None else x
    page_factice.colonnes.append({"x0": x, "y0": y, "cases": 1, "pas": PAS, "largeur": 16})


def poser_ruby(page_factice: PageFactice, indice_colonne: int, *, apres: int = 2,
               cases: int = 2) -> None:
    """Colle une colonne de ruby à DROITE de la colonne visée, comme en vertical réel."""
    hote = page_factice.colonnes[indice_colonne]
    page_factice.colonnes.append({
        "x0": hote["x0"] + hote["largeur"] + 6,
        "y0": hote["y0"] + apres * hote["pas"],
        "cases": cases, "pas": round(hote["pas"] * 0.5),
        "largeur": round(hote["largeur"] * 0.45),
    })


class LecteurFactice:
    """Double du modèle d'OCR : rend un texte prévisible et journalise ses appels.

    Le contrat qui compte pour les tests n'est pas ce que le modèle lit, mais **combien
    d'imagettes on lui donne et dans quel ordre** — c'est de là que viennent les défauts
    réels (coutures, ruby mêlées au texte, colonnes oubliées)."""

    def __init__(self, reponses=None, par_defaut: str = "あいうえおかきくけこ"):
        self.reponses = list(reponses) if reponses is not None else None
        self.par_defaut = par_defaut
        self.appels: list[int] = []          # taille de chaque lot reçu
        self.tailles: list[tuple[int, int]] = []   # dimensions des imagettes reçues

    def lire(self, images):
        self.appels.append(len(images))
        self.tailles.extend(im.size for im in images)
        sorties = []
        for _ in images:
            if self.reponses:
                sorties.append(self.reponses.pop(0))
            elif self.reponses is not None:
                sorties.append("")
            else:
                sorties.append(self.par_defaut)
        return sorties
