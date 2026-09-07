# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`read_all` groupe les bulles en un `generate()` par lot.

Ce qui est en jeu n'est pas la vitesse — c'est que le groupement soit NEUTRE. Le décodage
est glouton et indépendant par séquence, donc le texte doit être identique bulle à bulle ;
mesuré sur 64 bulles réelles à toutes les tailles de lot de 1 à 64 (cf. `TAILLE_LOT`), et
verrouillé ici sur le câblage, sans charger le moindre modèle.
"""
import numpy as np
import pytest
from PIL import Image

from manga import ocr as ocr_mod
from manga.detection import BubbleRegion


def _region(box, canvas=(200, 200)):
    x0, y0, x1, y1 = box
    mask = np.zeros((canvas[1], canvas[0]), dtype=bool)
    mask[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=box, mask=mask, score=0.9, cls=0, kind="bulle")


class _FauxModele:
    """Double de `manga_ocr.MangaOcr` : rend un texte dérivé de la TAILLE de chaque découpe,
    ce qui suffit à distinguer les bulles les unes des autres."""

    def __init__(self):
        self.lots = []          # tailles des lots reçus, dans l'ordre

    # — chemin une-à-une —
    def __call__(self, img):
        return f"<{img.size[0]}x{img.size[1]}>"


@pytest.fixture
def lecteur(monkeypatch):
    """Un `MangaOCR` sans `__init__` : on ne charge ni transformers ni les poids."""
    obj = ocr_mod.MangaOCR.__new__(ocr_mod.MangaOCR)
    obj._mocr = _FauxModele()
    return obj


def test_le_lot_est_neutre_sur_le_texte(lecteur, monkeypatch):
    """La propriété qui autorise le groupement : même texte, même ordre, quel que soit le
    découpage en lots."""
    image = Image.new("RGB", (200, 200), "white")
    regions = [_region((10, 10, 40, 40)), _region((60, 10, 120, 50)),
               _region((10, 60, 50, 130)), _region((90, 90, 190, 190))]

    # Le lot rend ce que le chemin une-à-une rendrait : c'est l'hypothèse mesurée.
    monkeypatch.setattr(ocr_mod.MangaOCR, "_lot",
                        lambda self, crops: [self._mocr(c) for c in crops])

    attendu = [lecteur.read(image, r) for r in regions]
    for taille in (1, 2, 3, 4, 16):
        monkeypatch.setattr(ocr_mod, "TAILLE_LOT", taille)
        assert lecteur.read_all(image, regions) == attendu, f"lot={taille}"


def test_le_decoupage_respecte_la_taille_de_lot(lecteur, monkeypatch):
    """Un lot trop large repaye en rembourrage ce qu'il gagne en aller-retours (mesuré :
    le gain disparaît à 64). Le plafond doit donc être réellement appliqué."""
    tailles = []
    monkeypatch.setattr(ocr_mod.MangaOCR, "_lot",
                        lambda self, crops: tailles.append(len(crops)) or ["x"] * len(crops))
    monkeypatch.setattr(ocr_mod, "TAILLE_LOT", 3)

    image = Image.new("RGB", (200, 200), "white")
    regions = [_region((10 + 5 * i, 10, 20 + 5 * i, 30)) for i in range(7)]
    lecteur.read_all(image, regions)

    assert tailles == [3, 3, 1]


def test_repli_sur_la_lecture_une_a_une(lecteur, monkeypatch):
    """Si l'API d'`manga_ocr` bouge, on relit — on n'échoue pas. Le gain est un confort,
    la lecture ne l'est pas."""
    def _casse(self, crops):
        raise AttributeError("API upstream modifiée")

    monkeypatch.setattr(ocr_mod.MangaOCR, "_lot", _casse)
    image = Image.new("RGB", (200, 200), "white")
    regions = [_region((10, 10, 40, 40)), _region((60, 10, 120, 50))]

    sorties = lecteur.read_all(image, regions)

    assert len(sorties) == 2
    assert all(s.startswith("<") for s in sorties)


def test_aucune_bulle_ne_lance_aucun_lot(lecteur, monkeypatch):
    monkeypatch.setattr(ocr_mod.MangaOCR, "_lot",
                        lambda self, crops: pytest.fail("ne doit pas être appelé"))
    assert lecteur.read_all(Image.new("RGB", (50, 50)), []) == []


def test_le_fond_mesure_est_transmis_a_chaque_bulle(lecteur, monkeypatch):
    """Sur une bulle inversée, une toile blanche autour d'un texte clair détruit le
    contraste. Le groupement ne doit pas perdre `styles`."""
    fonds = []

    class _Style:
        ok = True
        background = (12, 34, 56)

    monkeypatch.setattr(ocr_mod, "masked_crop",
                        lambda image, region, background, marge, agrandissement_min:
                        fonds.append(background) or Image.new("RGB", (10, 10)))
    monkeypatch.setattr(ocr_mod.MangaOCR, "_lot", lambda self, crops: ["x"] * len(crops))

    image = Image.new("RGB", (200, 200), "white")
    regions = [_region((10, 10, 40, 40)), _region((60, 10, 120, 50))]
    lecteur.read_all(image, regions, styles=[_Style(), _Style()])

    assert fonds == [(12, 34, 56), (12, 34, 56)]
