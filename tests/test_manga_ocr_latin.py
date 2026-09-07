# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Routage du moteur d'OCR et recomposition des lignes RapidOCR.

Aucun modèle n'est chargé ici : le routeur est testé par ses décisions, et `recomposer` est
une fonction pure qui prend la sortie brute de RapidOCR.
"""
import pytest

from manga import ocr_routeur
from manga.ocr_latin import recomposer


# --------------------------------------------------------------------------- #
# Routage
# --------------------------------------------------------------------------- #

def test_le_japonais_va_a_manga_ocr():
    assert ocr_routeur.moteur_pour("jp") == ocr_routeur.MOTEUR_MANGA
    assert ocr_routeur.moteur_pour("ja") == ocr_routeur.MOTEUR_MANGA


def test_tout_le_reste_va_a_rapidocr():
    """Y compris le chinois et le coréen : manga-ocr n'est entraîné que sur du japonais."""
    for langue in ("en", "fr", "es", "ko", "zh", "ru"):
        assert ocr_routeur.moteur_pour(langue) == ocr_routeur.MOTEUR_LATIN, langue


def test_le_moteur_peut_etre_force():
    assert ocr_routeur.moteur_pour("en", {"moteur": "manga_ocr"}) == ocr_routeur.MOTEUR_MANGA
    assert ocr_routeur.moteur_pour("jp", {"moteur": "rapidocr"}) == ocr_routeur.MOTEUR_LATIN


def test_moteur_inconnu_arrete_avec_les_valeurs_attendues():
    with pytest.raises(SystemExit) as err:
        ocr_routeur.moteur_pour("en", {"moteur": "tesseract"})
    assert "tesseract" in str(err.value) and "rapidocr" in str(err.value)


def test_rapidocr_absent_dit_quoi_installer():
    """Un `ImportError` nu enverrait chercher un bug là où il n'y a qu'un `pip install`."""
    pytest.importorskip  # noqa: B018 — lisibilité : ce test ne dépend d'aucun paquet
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("rapidocr-onnxruntime est installé : le chemin d'erreur ne s'ouvre pas")
    with pytest.raises(SystemExit) as err:
        ocr_routeur.lecteur_pour("en", {})
    message = str(err.value)
    assert "pip install rapidocr-onnxruntime" in message
    assert "--no-deps" in message, "le conflit avec onnxruntime-directml doit être annoncé"


# --------------------------------------------------------------------------- #
# Recomposition — ce qui répare le `ＨＥＳＣＥＲＴＡＮＡＹ…`
# --------------------------------------------------------------------------- #

def _ligne(texte, x0, y0, x1, y1, score=0.95):
    """Une boîte RapidOCR : `[quadrilatère, texte, confiance]`."""
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]], texte, score]


def test_les_espaces_survivent():
    """LE défaut que ce module corrige : manga-ocr n'a pas de token d'espace."""
    brut = [_ligne("HE'S CERTAINLY NO", 0, 0, 200, 30),
            _ligne("ORDINARY PERSON", 0, 40, 180, 70)]
    assert recomposer(brut) == "HE'S CERTAINLY NO ORDINARY PERSON"


def test_les_lignes_sont_ordonnees_haut_bas():
    brut = [_ligne("DEUX", 0, 40, 100, 70), _ligne("UN", 0, 0, 100, 30)]
    assert recomposer(brut) == "UN DEUX"


def test_deux_boites_sur_la_meme_ligne_visuelle_sont_recollees_gauche_droite():
    """Le latin se lit de gauche à droite DANS la bulle, même dans un manga lu à l'envers."""
    brut = [_ligne("MONDE", 110, 0, 200, 30), _ligne("BONJOUR", 0, 0, 100, 30)]
    assert recomposer(brut) == "BONJOUR MONDE"


def test_les_lectures_peu_sures_sont_jetees():
    """Sous le seuil, PP-OCRv4 rend du dessin lu comme du texte — le laisser passer ferait
    halluciner le traducteur, exactement le défaut qu'on corrige."""
    brut = [_ligne("VRAI", 0, 0, 100, 30, score=0.97),
            _ligne("xJ8", 0, 40, 100, 70, score=0.12)]
    assert recomposer(brut) == "VRAI"


def test_rien_de_lu_rend_une_chaine_vide():
    """Cas fréquent et normal : bulle vide, ou fausse détection sur du dessin."""
    assert recomposer(None) == ""
    assert recomposer([]) == ""
    assert recomposer([_ligne("   ", 0, 0, 10, 10)]) == ""


def test_les_entrees_malformees_sont_ignorees_sans_lever():
    """Un tome de 150 planches ne doit pas mourir sur une boîte inattendue."""
    brut = [_ligne("BON", 0, 0, 100, 30), ["incomplet"], None]
    assert recomposer(brut) == "BON"


def test_les_espaces_multiples_sont_normalises():
    brut = [_ligne("  TROP   D'ESPACES  ", 0, 0, 200, 30)]
    assert recomposer(brut) == "TROP D'ESPACES"
