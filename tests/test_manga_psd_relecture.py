# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Relecture des PSD par un lecteur **indépendant** (`psd-tools`).

Pourquoi ce fichier existe. `tests/test_manga_psd.py` embarque son propre analyseur — écrit par
le même auteur, à partir de la même lecture de la spécification, que l'écrivain qu'il teste. Il
a donc reproduit fidèlement une erreur au lieu de la révéler : le descripteur Photoshop
n'écrivait pas son identifiant de classe (4 octets obligatoires même à longueur nulle), si bien
que Photoshop lisait « 0 item » et affichait « Problèmes à la lecture des calques […]
utiliseront les données de pixel existantes ». L'analyseur maison, lui, relisait exactement ce
qu'il avait écrit et ne voyait rien.

La leçon vaut au-delà du bug : un format binaire ne se valide pas contre soi-même. `psd-tools`
est orienté LECTURE — c'est précisément ce qu'on veut ici, et c'est une dépendance de TEST
seulement (`requirements-dev.txt`), jamais de `requirements-manga.txt` : l'écriture reste en
`struct` de la bibliothèque standard.

⚠ Ce que ces tests ne prouvent toujours pas : qu'Adobe Photoshop lui-même ouvre le fichier sans
broncher. Ils prouvent qu'un tiers conforme à la spécification y retrouve des calques de TYPE,
leur texte, leur police et leurs paragraphes — ce qui est la condition nécessaire manquante
jusqu'ici.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import psd
from manga.clean import analyze_regions, clean_bubbles
from manga.detection import BubbleRegion
from manga.typeset import typeset_page

psd_tools = pytest.importorskip("psd_tools", reason="pip install -r requirements-dev.txt")
from psd_tools import PSDImage                                          # noqa: E402
from psd_tools.constants import Tag                                     # noqa: E402


TAILLE = (300, 400)
BOX = (50, 40, 250, 200)
BOX2 = (60, 230, 240, 370)


def _ecrire(tmp_path, textes, mode_texte="type"):
    img = Image.new("RGB", TAILLE, (30, 30, 30))
    d = ImageDraw.Draw(img)
    regions = []
    for box in (BOX, BOX2):
        d.ellipse(list(box), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
        m = Image.new("L", TAILLE, 0)
        ImageDraw.Draw(m).ellipse(list(box), fill=255)
        regions.append(BubbleRegion(bbox=box, mask=np.asarray(m) > 127, score=0.9, cls=0))

    styles = analyze_regions(img, regions)
    nettoyee = clean_bubbles(img, regions, styles=styles)
    fits: list[dict] = []
    finale = typeset_page(nettoyee.copy(), regions, textes, styles=styles, fits_out=fits)
    return psd.ecrire_planche(tmp_path / "p.psd", finale=finale, nettoyee=nettoyee, fits=fits,
                              originale=img, mode_texte=mode_texte)


def _calques_texte(document):
    return [c for c in document if c.name.startswith("Texte ")]


# --------------------------------------------------------------------------- #
# Le fichier s'ouvre, et les calques de texte en SONT
# --------------------------------------------------------------------------- #

def test_le_fichier_souvre_et_a_la_bonne_taille(tmp_path):
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut à toi"]))
    assert (doc.width, doc.height) == TAILLE


def test_les_calques_de_texte_sont_de_TYPE_pas_de_pixels(tmp_path):
    """LE test de non-régression. Avant le correctif du descripteur, `psd-tools` ne trouvait
    aucun `TySh` exploitable et ces calques ressortaient en `pixel` — exactement ce que
    Photoshop annonçait en retombant sur « les données de pixel existantes »."""
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut à toi"]))
    calques = _calques_texte(doc)
    assert len(calques) == 2
    assert [c.kind for c in calques] == ["type", "type"]


def test_les_fonds_restent_des_calques_de_pixels(tmp_path):
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut à toi"]))
    fonds = [c for c in doc if not c.name.startswith("Texte ")]
    assert [c.name for c in fonds] == ["Planche originale", "Planche nettoyée"]
    assert all(c.kind == "pixel" for c in fonds)


def test_en_mode_rasterise_aucun_calque_nest_de_type(tmp_path):
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut"], mode_texte="rasterise"))
    assert all(c.kind == "pixel" for c in doc)


# --------------------------------------------------------------------------- #
# Le texte lui-même
# --------------------------------------------------------------------------- #

def test_le_texte_se_relit_a_l_identique(tmp_path):
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut"]))
    relus = [c.text.replace("\r", " ").strip() for c in _calques_texte(doc)]
    assert relus == ["Bonjour", "Salut"]


def test_les_accents_francais_survivent(tmp_path):
    """Le nom de calque « historique » est en latin-1 ; le texte, lui, transite en UTF-16BE
    dans l'`EngineData`. C'est ce chemin-là qu'on vérifie."""
    replique = "Ça va ? J'ai déjà été très déçu…"
    doc = PSDImage.open(_ecrire(tmp_path, [replique, "Oui"]))
    relu = _calques_texte(doc)[0].text.replace("\r", " ")
    for mot in ("Ça", "J'ai", "déjà", "très", "déçu"):
        assert mot in relu


def test_une_bulle_multiligne_garde_ses_paragraphes(tmp_path):
    """Non-régression : `ParagraphRun` déclarait UN paragraphe couvrant tout le texte, quel que
    soit le nombre de retours. Photoshop refusait le calque dès la deuxième ligne — c'est-à-dire
    sur la quasi-totalité des bulles."""
    long_texte = "Tes écouteurs sont abîmés, non ? J'en ai un autre si tu veux"
    doc = PSDImage.open(_ecrire(tmp_path, [long_texte, "Oh !"]))
    calque = _calques_texte(doc)[0]
    assert calque.text.count("\r") >= 1, "le lettrage aurait dû couper cette réplique"

    moteur = calque.engine_dict
    longueurs = list(moteur["ParagraphRun"]["RunLengthArray"])
    runs = moteur["ParagraphRun"]["RunArray"]
    assert len(longueurs) == len(runs), "autant de longueurs que d'entrées de RunArray"
    assert len(longueurs) == calque.text.count("\r") + (0 if calque.text.endswith("\r") else 1)
    assert sum(longueurs) == len(calque.text) + (0 if calque.text.endswith("\r") else 1)


def test_le_texte_est_clos_par_un_retour_chariot(tmp_path):
    """Le moteur clôt chaque paragraphe, y compris le dernier."""
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut"]))
    moteur = _calques_texte(doc)[0].engine_dict
    assert moteur["Editor"]["Text"].value.endswith("\r")


def test_le_descripteur_et_le_moteur_annoncent_LA_MEME_longueur(tmp_path):
    """LE test de non-régression du plantage de la v0.19.1.

    Le descripteur `Txt ` disait 7 caractères là où les passes de style de l'`EngineData` en
    couvraient 8 : Photoshop dimensionne ses tampons sur le premier puis y écrit selon les
    secondes, et plantait à l'ouverture — sans même la boîte d'alerte précédente. Les deux
    doivent passer par `texte_moteur`."""
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour tout le monde, ça va ?", "Oui"]))
    for calque in _calques_texte(doc):
        depuis_descripteur = calque.text                      # descripteur `Txt `
        depuis_moteur = calque.engine_dict["Editor"]["Text"].value
        assert depuis_descripteur == depuis_moteur
        assert sum(calque.engine_dict["StyleRun"]["RunLengthArray"]) == len(depuis_descripteur)
        assert sum(calque.engine_dict["ParagraphRun"]["RunLengthArray"]) == len(depuis_descripteur)


def test_le_moteur_porte_les_cles_que_photoshop_ecrit(tmp_path):
    """Une feuille de style réduite à cinq clés laisse le reste non initialisé côté Photoshop :
    c'est ce qui sépare un calque « affichable » d'un calque « éditable » (Photopea dessinait
    le texte mais refusait de le rouvrir à l'outil Texte)."""
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut"]))
    calque = _calques_texte(doc)[0]
    assert "Rendered" in calque.engine_dict
    feuille = _feuille_de_style(calque)
    for cle in ("Font", "FontSize", "FauxBold", "AutoLeading", "Leading", "HorizontalScale",
                "Tracking", "BaselineShift", "AutoKerning", "FillColor", "StrokeColor",
                "FillFlag", "StrokeFlag", "Ligatures", "Language"):
        assert cle in feuille, cle
    props = calque.resource_dict["ParagraphSheetSet"][0]["Properties"]
    for cle in ("Justification", "FirstLineIndent", "StartIndent", "AutoHyphenate",
                "WordSpacing", "GlyphSpacing", "EveryLineComposer"):
        assert cle in props, cle


# --------------------------------------------------------------------------- #
# Le PSD minimal de diagnostic (`run_manga.py --psd-test`)
# --------------------------------------------------------------------------- #

def test_le_psd_minimal_a_un_fond_et_un_calque_de_texte(tmp_path):
    chemin = psd.psd_minimal(tmp_path / "mini.psd")
    doc = PSDImage.open(chemin)
    assert [(c.name, c.kind) for c in doc] == [("Fond", "pixel"), ("Texte — Test", "type")]
    assert _calques_texte(doc)[0].text.replace("\r", "") == "Test"


def test_le_psd_minimal_respecte_le_meme_invariant_de_longueur(tmp_path):
    doc = PSDImage.open(psd.psd_minimal(tmp_path / "mini.psd", texte="Bonjour"))
    calque = _calques_texte(doc)[0]
    assert calque.text == calque.engine_dict["Editor"]["Text"].value


# --------------------------------------------------------------------------- #
# Police, corps, couleur, géométrie
# --------------------------------------------------------------------------- #

def test_la_police_declaree_est_celle_du_lettrage(tmp_path):
    """`font_names` lit le `FontSet` de l'`EngineData`. Si Photoshop ne trouve pas ce nom
    PostScript sur le système, il substitue : le calque reste éditable mais le dessin change."""
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut"]))
    polices = _calques_texte(doc)[0].font_names
    assert polices and all(p.strip() for p in polices), f"FontSet relu : {polices}"


def _feuille_de_style(calque):
    return calque.resource_dict["StyleSheetSet"][0]["StyleSheetData"]


def test_le_corps_et_la_couleur_sont_ceux_du_fit(tmp_path):
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut"]))
    feuille = _feuille_de_style(_calques_texte(doc)[0])
    assert float(feuille["FontSize"]) > 0
    valeurs = [float(v) for v in feuille["FillColor"]["Values"]]
    assert len(valeurs) == 4
    assert valeurs[0] == pytest.approx(1.0)                     # alpha
    assert all(0.0 <= v <= 1.0 for v in valeurs[1:])            # RVB normalisé


def test_les_calques_de_texte_sont_bornes_a_leur_bulle(tmp_path):
    """Un calque de texte de pleine page ferait un PSD de 25 Mo au lieu de 4."""
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut à toi"]))
    for calque in _calques_texte(doc):
        assert calque.width < TAILLE[0] and calque.height < TAILLE[1]


# --------------------------------------------------------------------------- #
# Robustesse de la sérialisation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("replique", [
    "a",                                  # une lettre
    "Oh !",                               # court
    "Ça alors — vraiment ?!",             # tiret cadratin, ponctuation
    "Il dit : « bonjour » (enfin…)",      # parenthèses, à échapper dans l'EngineData
    "Un texte volontairement plus long pour forcer plusieurs lignes dans la bulle",
])
def test_le_bloc_TySh_se_relit_quelle_que_soit_la_replique(tmp_path, replique):
    """Balaye des longueurs de `TySh` variées, dont des tailles IMPAIRES : un bloc `8BIM` doit
    déclarer sa longueur ARRONDIE, sinon le lecteur repart un octet trop tôt et manque le bloc
    suivant."""
    doc = PSDImage.open(_ecrire(tmp_path, [replique, "Oui"]))
    calques = _calques_texte(doc)
    assert len(calques) == 2
    assert calques[0].kind == "type"
    assert calques[0].text.replace("\r", " ").strip()


def test_aucun_calque_ne_perd_son_nom_unicode(tmp_path):
    doc = PSDImage.open(_ecrire(tmp_path, ["Réplique accentuée : déjà vu", "Oui"]))
    noms = [c.name for c in doc]
    assert any("é" in n for n in noms), f"noms relus : {noms}"


def test_une_planche_sans_bulle_se_relit(tmp_path):
    img = Image.new("RGB", TAILLE, (255, 255, 255))
    chemin = psd.ecrire_planche(tmp_path / "vide.psd", finale=img, nettoyee=img, fits=[],
                                originale=img)
    doc = PSDImage.open(chemin)
    assert [c.name for c in doc] == ["Planche originale", "Planche nettoyée"]


def test_le_composite_reste_la_planche_aplatie(tmp_path):
    """Un lecteur qui ignore les calques doit voir exactement `pages_out/`."""
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut à toi"]))
    compose = doc.topil()
    assert compose.size == TAILLE


def test_le_bloc_de_type_est_bien_dans_les_infos_additionnelles(tmp_path):
    doc = PSDImage.open(_ecrire(tmp_path, ["Bonjour", "Salut"]))
    for calque in _calques_texte(doc):
        assert Tag.TYPE_TOOL_OBJECT_SETTING in calque.tagged_blocks
