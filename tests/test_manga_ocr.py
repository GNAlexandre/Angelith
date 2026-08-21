# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""OCR RÉEL (manga-ocr) sur un crop synthétique. Sauté si le paquet `manga_ocr`
n'est pas installé (voir requirements-manga.txt) — ne bloque pas un checkout frais."""
import numpy as np
import pytest

pytest.importorskip("manga_ocr")


def test_ocr_reads_synthetic_japanese_text(synthetic_manga_page):
    from manga.detection import BubbleRegion
    from manga.ocr import MangaOCR

    img, bubble_box, expected_text = synthetic_manga_page
    mask = np.zeros((img.height, img.width), dtype=bool)
    region = BubbleRegion(bbox=bubble_box, mask=mask, score=1.0, cls=0)

    reader = MangaOCR()
    text = reader.read(img, region)
    assert text.strip() == expected_text


# --------------------------------------------------------------------------- #
# Chargement du modèle : silencieux, et HORS LIGNE dès qu'il est en cache
#
# Sans cela, `from_pretrained` contacte Hugging Face à CHAQUE lancement pour revalider la
# révision : latence, avertissement « unauthenticated requests », run impossible hors ligne —
# et une nouvelle révision peut arriver EN PLEIN TOME et changer l'OCR sans prévenir.
#
# Le vrai modèle n'est jamais chargé ici : `manga_ocr.MangaOcr` est remplacé par un espion.
# --------------------------------------------------------------------------- #

class _EspionMangaOcr:
    """Faux `manga_ocr.MangaOcr` : retient l'argument reçu, ne charge rien."""
    dernier: str | None = None

    def __init__(self, pretrained_model_name_or_path=None, force_cpu=False):
        type(self).dernier = pretrained_model_name_or_path


@pytest.fixture
def espion(monkeypatch):
    import manga_ocr
    _EspionMangaOcr.dernier = None
    monkeypatch.setattr(manga_ocr, "MangaOcr", _EspionMangaOcr)
    return _EspionMangaOcr


def test_le_modele_en_cache_est_charge_par_son_CHEMIN_local(espion, monkeypatch):
    from manga import ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "dossier_cache", lambda *a, **k: r"C:\cache\snapshots\abc")
    ocr_mod.MangaOCR()
    assert espion.dernier == r"C:\cache\snapshots\abc"


def test_sans_cache_on_retombe_sur_lidentifiant_de_depot(espion, monkeypatch):
    """Premier lancement : il FAUT bien télécharger une fois — et le dire."""
    from manga import ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "dossier_cache", lambda *a, **k: None)
    dits: list[str] = []
    ocr_mod.MangaOCR(dire=dits.append)
    assert espion.dernier == ocr_mod.MODELE_OCR
    assert dits and "cache" in dits[0]


def test_hors_ligne_TRUE_sans_cache_echoue_au_lieu_de_telecharger(espion, monkeypatch):
    """Le mode strict sert à garantir qu'un run ne touchera pas le réseau : télécharger en
    douce serait exactement ce qu'il cherche à empêcher."""
    from manga import ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "dossier_cache", lambda *a, **k: None)
    with pytest.raises(SystemExit, match="cache"):
        ocr_mod.MangaOCR({"hors_ligne": True})
    assert espion.dernier is None      # rien n'a été chargé


def test_hors_ligne_FALSE_rétablit_lidentifiant_de_depot(espion, monkeypatch):
    from manga import ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "dossier_cache",
                        lambda *a, **k: pytest.fail("ne doit pas consulter le cache"))
    ocr_mod.MangaOCR({"hors_ligne": False})
    assert espion.dernier == ocr_mod.MODELE_OCR


def test_le_bruit_de_transformers_est_tu_AVANT_import(espion, monkeypatch):
    """L'avertissement « ViTImageProcessor requires torchvision » est émis à l'import de
    `ViTImageProcessor`, donc de `manga_ocr` — pas à celui de `transformers`. Le silence doit
    être posé avant, sinon il est trop tard."""
    import transformers.utils.logging as journal
    from manga import ocr as ocr_mod
    monkeypatch.setattr(ocr_mod, "dossier_cache", lambda *a, **k: None)
    niveaux: list[int] = []
    monkeypatch.setattr(journal, "set_verbosity_error",
                        lambda: niveaux.append(journal.ERROR))
    ocr_mod.MangaOCR()
    assert niveaux, "le niveau de journalisation n'a pas été abaissé"


def test_dossier_cache_ne_touche_PAS_au_reseau(monkeypatch):
    """`local_files_only=True` ne fait que résoudre le cache. Un modèle absent rend `None`,
    il ne déclenche jamais un téléchargement."""
    from manga import ocr as ocr_mod
    assert ocr_mod.dossier_cache("depot/qui-nexiste-pas-du-tout") is None


def test_reading_order_sorts_right_to_left_then_top_to_bottom():
    from manga.detection import BubbleRegion
    from manga.ocr import reading_order

    mask = np.zeros((10, 10), dtype=bool)
    top_right = BubbleRegion(bbox=(80, 0, 100, 20), mask=mask, score=1.0, cls=0)
    top_left = BubbleRegion(bbox=(0, 0, 20, 20), mask=mask, score=1.0, cls=0)
    bottom = BubbleRegion(bbox=(0, 100, 20, 120), mask=mask, score=1.0, cls=0)

    ordered = reading_order([bottom, top_left, top_right])
    assert ordered == [top_right, top_left, bottom]


def test_region_rectangulaire_remplit_la_boite():
    """Hors bulle, l'OCR travaille sur le RECTANGLE et non sur le masque d'encre.

    Mesuré sur les zones réelles du Vol.2 : l'encre nue fait halluciner `manga-ocr`
    (`人間の場所…`, `民主の人とセックスを`) là où le crop brut lit juste (`ああ…陽弥…`,
    et le filigrane `ＲａｗＬａｚｙ．ｓ．` exactement). Le ViT a été entraîné sur des imagettes
    de manga, anti-crénelage compris ; le masque de segmentation retire précisément les
    demi-teintes dont il se sert."""
    import numpy as np

    from manga.detection import BubbleRegion
    from manga.ocr import region_rectangulaire

    encre = np.zeros((50, 50), dtype=bool)
    encre[10:14, 10:40] = True          # un trait fin
    encre[30:34, 10:40] = True
    region = BubbleRegion(bbox=(10, 10, 40, 34), mask=encre, score=1.0, cls=0,
                          kind="onomatopee")
    plein = region_rectangulaire(region)
    assert plein.bbox == region.bbox
    assert plein.mask[10:34, 10:40].all()
    assert int(plein.mask.sum()) == 24 * 30
    # L'original n'est pas muté : il sert ensuite à mesurer la polarité et à placer la glose.
    assert int(region.mask.sum()) == 2 * 4 * 30
