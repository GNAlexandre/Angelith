# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Langue SOURCE et FORMAT de planche : les deux axes que la brique manga ignorait.

Le défaut d'origine : `manga/ocr.py` charge un modèle japonais, et toute la chaîne en
dépendait sans le dire. Sur un webtoon anglais, l'OCR rendait
`ＨＥＳＣＥＲＴＡＮＡＹＮＯＯＯＲＤＩＮＡＲＹＰＥＲＳＯＮ` et des kanji inventés à partir de
chiffres ; le LLM traduisait consciencieusement cette bouillie, et le rapport n'y voyait rien.

Ces tests couvrent les deux axes SÉPARÉMENT — les confondre est l'erreur symétrique : un scan
anglais d'un manga japonais se lit toujours droite→gauche.
"""
import numpy as np
import pytest

from manga import formats, sources_manga, text_detection
from manga.detection import BubbleRegion

CONFIG = {
    "langues": {"dossiers": {"ENG": "en", "JAP": "jp", "FR": "fr", "KO": "ko"}},
    "manga": {"langue_source": "jp",
              "rendu": {"sens_lecture": "droite_gauche", "langue_iso": "fr"},
              "formats": {"webtoon": {"rendu": {"sens_lecture": "gauche_droite"}}}},
}


def _planches(dossier, n=2):
    dossier.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (dossier / f"{i}.png").write_bytes(b"")
    return dossier


# --------------------------------------------------------------------------- #
# Résolution format + langue
# --------------------------------------------------------------------------- #

def test_manga_nu_reste_du_japonais_droite_gauche(tmp_path):
    """RÉTROCOMPATIBILITÉ : la structure historique ne doit RIEN changer.

    C'est le test qui garantit qu'aucun des tomes déjà traduits ne repart de zéro."""
    vol = tmp_path / "Oeuvre" / "Vol.1"
    _planches(vol / "manga")
    dossier, fmt, code, _av = sources_manga.resoudre_source(vol, CONFIG)
    assert dossier == vol / "manga"
    assert (fmt, code) == ("manga", "jp")
    assert formats.sens_lecture(CONFIG, fmt) == "droite_gauche"


def test_tome_nu_sans_sous_dossier(tmp_path):
    """Second repli historique : les images à plat dans le tome."""
    vol = tmp_path / "Oeuvre" / "Vol.1"
    _planches(vol)
    dossier, fmt, code, _av = sources_manga.resoudre_source(vol, CONFIG)
    assert (dossier, fmt, code) == (vol, "manga", "jp")


def test_dossier_de_langue_sous_manga(tmp_path):
    """Un SCAN ANGLAIS d'un manga : la langue change, le sens de lecture NON."""
    vol = tmp_path / "Oeuvre" / "Vol.1"
    _planches(vol / "manga" / "ENG")
    dossier, fmt, code, _av = sources_manga.resoudre_source(vol, CONFIG)
    assert (dossier, fmt, code) == (vol / "manga" / "ENG", "manga", "en")
    assert formats.sens_lecture(CONFIG, fmt) == "droite_gauche"


def test_webtoon_anglais(tmp_path):
    """Le cas du run raté : webtoon + anglais. Les deux axes bougent ensemble."""
    vol = tmp_path / "Oeuvre" / "Chap.11"
    _planches(vol / "webtoon" / "ENG", n=9)
    dossier, fmt, code, _av = sources_manga.resoudre_source(vol, CONFIG)
    assert (dossier, fmt, code) == (vol / "webtoon" / "ENG", "webtoon", "en")
    assert formats.sens_lecture(CONFIG, fmt) == "gauche_droite"


def test_webtoon_sans_dossier_de_langue(tmp_path):
    """Format déclaré, langue non : on hérite du défaut de config, pas du format."""
    vol = tmp_path / "Oeuvre" / "Chap.1"
    _planches(vol / "webtoon")
    _dossier, fmt, code, _av = sources_manga.resoudre_source(vol, CONFIG)
    assert (fmt, code) == ("webtoon", "jp")


def test_langue_forcee_gagne(tmp_path):
    vol = tmp_path / "Oeuvre" / "Vol.1"
    _planches(vol / "manga" / "ENG", n=2)
    _planches(vol / "manga" / "JAP", n=9)
    # Sans --langue, le plus fourni gagne (JAP, 9 planches)...
    _d, _f, code, avert = sources_manga.resoudre_source(vol, CONFIG)
    assert code == "jp"
    assert avert and "--langue" in avert[0]
    # ...et --langue tranche.
    _d, _f, code, _av = sources_manga.resoudre_source(vol, CONFIG, langue="ENG")
    assert code == "en"


def test_format_force_gagne(tmp_path):
    vol = tmp_path / "Oeuvre" / "Vol.1"
    _planches(vol / "manga", n=9)
    _planches(vol / "webtoon", n=2)
    _d, fmt, _c, _av = sources_manga.resoudre_source(vol, CONFIG, format="webtoon")
    assert fmt == "webtoon"


def test_source_absente_dit_ou_deposer(tmp_path):
    vol = tmp_path / "Oeuvre" / "Vol.1"
    vol.mkdir(parents=True)
    with pytest.raises(SystemExit) as err:
        sources_manga.resoudre_source(vol, CONFIG)
    assert "webtoon" in str(err.value) and "ENG" in str(err.value)


def test_mode_glossaire_quand_source_est_la_cible(tmp_path):
    """Un manga DÉJÀ français ne se traduit pas — il alimente le glossaire."""
    vol = tmp_path / "Oeuvre" / "Vol.1"
    _planches(vol / "manga" / "FR")
    build = tmp_path / "build"
    plan = sources_manga.scan_volume(vol, build, CONFIG)
    assert (plan.code_langue, plan.mode) == ("fr", "glossaire")

    _planches(vol / "manga" / "ENG", n=5)
    plan = sources_manga.scan_volume(vol, build, CONFIG, langue="ENG")
    assert (plan.code_langue, plan.mode) == ("en", "traduction")


# --------------------------------------------------------------------------- #
# Surcouche de configuration par format
# --------------------------------------------------------------------------- #

def test_le_format_herite_de_manga_et_ne_redeclare_que_le_sens():
    """Tout l'intérêt du format : ne PAS entretenir deux configurations parallèles."""
    rendu_manga = formats.config_format(CONFIG, "manga", "rendu")
    rendu_webtoon = formats.config_format(CONFIG, "webtoon", "rendu")
    assert rendu_webtoon["langue_iso"] == rendu_manga["langue_iso"] == "fr"
    assert rendu_webtoon["sens_lecture"] == "gauche_droite"
    assert rendu_manga["sens_lecture"] == "droite_gauche"


def test_format_inconnu_herite_du_manga():
    assert formats.sens_lecture(CONFIG, "bd_franco_belge") == "droite_gauche"


# --------------------------------------------------------------------------- #
# Ordre de lecture
# --------------------------------------------------------------------------- #

def _r(x0, y0, x1, y1):
    return BubbleRegion(bbox=(x0, y0, x1, y1),
                        mask=np.zeros((1, 1), dtype=bool), score=1.0, cls=0)


def test_ordre_de_lecture_suit_le_sens():
    """Deux bulles côte à côte : c'est LE cas où le sens change le résultat.

    Sans ce branchement, un webtoon recevait ses répliques dans l'ordre inverse — un mélange
    silencieux, puisque le NOMBRE de bulles restait juste."""
    from manga.ocr import reading_order

    gauche, droite = _r(0, 0, 40, 40), _r(60, 0, 100, 40)
    regions = [gauche, droite]
    assert reading_order(regions, "droite_gauche") == [droite, gauche]
    assert reading_order(regions, "gauche_droite") == [gauche, droite]
    # Défaut inchangé : le manga.
    assert reading_order(regions) == [droite, gauche]


def test_ordre_de_lecture_haut_bas_independant_du_sens():
    from manga.ocr import reading_order

    haut, bas = _r(0, 0, 40, 40), _r(0, 60, 40, 100)
    for sens in ("droite_gauche", "gauche_droite"):
        assert reading_order([bas, haut], sens) == [haut, bas]


# --------------------------------------------------------------------------- #
# Triage des zones hors bulle — l'heuristique qui S'INVERSE
# --------------------------------------------------------------------------- #

def test_triage_source_japonaise_inchange():
    trier = text_detection.trier_zone
    assert trier("ドドド", langue="jp") == text_detection.TRI_TEXTE
    # Du latin sur une source japonaise reste une hallucination de manga-ocr.
    assert trier("ＥｌｅＨＴ", langue="jp") == text_detection.TRI_BRUIT
    assert trier("！！", langue="jp") == text_detection.TRI_PONCTUATION


def test_triage_source_latine_garde_les_onomatopees():
    """Sans l'inversion, TOUTES les onomatopées d'une œuvre anglaise partaient au rebut."""
    trier = text_detection.trier_zone
    assert trier("KRAKOOM", langue="en") == text_detection.TRI_TEXTE
    assert trier("THUD", langue="en") == text_detection.TRI_TEXTE
    # Et c'est le CJK qui devient l'intrus.
    assert trier("ドドド", langue="en") == text_detection.TRI_BRUIT
    # La ponctuation reste de la ponctuation, dans les deux sens.
    assert trier("！！", langue="en") == text_detection.TRI_PONCTUATION
    # Une lettre isolée reste du dessin mal lu.
    assert trier("E", langue="en") == text_detection.TRI_BRUIT


def test_mobilier_prime_sur_tout():
    for langue in ("jp", "en"):
        assert text_detection.trier_zone("x", mobilier=True,
                                         langue=langue) == text_detection.TRI_MOBILIER


def test_alias_tri_japonais_conserve():
    """La valeur PERSISTÉE ne change pas : les index déjà écrits restent lisibles."""
    assert text_detection.TRI_JAPONAIS == text_detection.TRI_TEXTE == "japonais"
