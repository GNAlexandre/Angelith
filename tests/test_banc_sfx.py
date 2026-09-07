# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`tools/banc_sfx.py` — l'instrument de mesure du lot 21.

Il lit des caches réels sous `build/`, absents de la CI. Ce qui se teste ici, c'est donc ce
qui décide : le **tirage reproductible** de l'échantillon de vérité terrain, et l'agrégation.
Un échantillon dont personne ne peut refaire le tirage n'est pas une référence.
"""
import json

import pytest
from PIL import Image

from tools import banc_sfx


def _zone(projet="manga A", tome="Vol.1", page=1, index=0, bbox=(0, 0, 10, 10),
          texte="ゴォォォ", mobilier=False, tri="japonais", aire_page=1000):
    return banc_sfx.Zone(
        projet=projet, tome=tome, page=page, index=index, bbox=bbox, texte=texte,
        mobilier=mobilier, tri=tri,
        aire_bbox=(bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), aire_page=aire_page)


def _lot(n=200):
    return [_zone(page=1 + i // 5, index=i % 5) for i in range(n)]


# --------------------------------------------------------------------------- #
# Le tirage — la propriété qui fait de l'échantillon une référence
# --------------------------------------------------------------------------- #

def test_la_graine_est_ecrite_dans_le_depot():
    """L21 étape 0.2 l'exige explicitement, et c'est la moitié de ce que « reproductible »
    veut dire."""
    assert banc_sfx.GRAINE_ECHANTILLON == 21
    assert banc_sfx.TAILLE_ECHANTILLON == 60


def test_le_tirage_est_reproductible():
    a = banc_sfx.echantillon(_lot(), 60, 21)
    b = banc_sfx.echantillon(_lot(), 60, 21)
    assert [z.cle for z in a] == [z.cle for z in b]
    assert len(a) == 60


def test_le_tirage_ne_depend_pas_de_l_ordre_d_enumeration():
    """⚠ L'ordre de `build/` dépend du système de fichiers. Un tirage qui en dépendrait ne
    serait pas reproductible **malgré** sa graine — le pire des deux mondes, puisque la
    graine donnerait l'illusion du contraire."""
    lot = _lot()
    a = banc_sfx.echantillon(lot, 60, 21)
    b = banc_sfx.echantillon(list(reversed(lot)), 60, 21)
    assert [z.cle for z in a] == [z.cle for z in b]


def test_deux_graines_donnent_deux_tirages():
    a = banc_sfx.echantillon(_lot(), 60, 21)
    b = banc_sfx.echantillon(_lot(), 60, 22)
    assert [z.cle for z in a] != [z.cle for z in b]


def test_le_tirage_est_sans_remise():
    tirage = banc_sfx.echantillon(_lot(), 60, 21)
    assert len({z.cle for z in tirage}) == 60


def test_un_lot_plus_petit_que_l_echantillon_est_rendu_entier():
    tirage = banc_sfx.echantillon(_lot(12), 60, 21)
    assert len(tirage) == 12


def test_le_tirage_porte_AUSSI_le_mobilier():
    """Écarter le mobilier avant de tirer ferait mesurer le triage par l'échantillon qu'il a
    lui-même filtré."""
    lot = [_zone(index=i, mobilier=(i % 2 == 0), tri="mobilier" if i % 2 == 0 else "japonais")
           for i in range(100)]
    tirage = banc_sfx.echantillon(lot, 60, 21)
    assert any(z.mobilier for z in tirage)
    assert any(not z.mobilier for z in tirage)


# --------------------------------------------------------------------------- #
# L'agrégation
# --------------------------------------------------------------------------- #

def test_le_resume_compte_le_triage_et_les_planches_porteuses():
    lot = [_zone(page=1, index=0, tri="japonais"),
           _zone(page=1, index=1, tri="ponctuation"),
           _zone(page=2, index=0, tri="mobilier", mobilier=True)]
    r = banc_sfx.resumer(lot)
    assert r["zones"] == 3
    assert r["pages_porteuses"] == 2
    assert r["tri"] == {"japonais": 1, "ponctuation": 1, "mobilier": 1}


def test_les_trois_paliers_d_uniformite_sont_ceux_de_clean_bubbles():
    """0,60 et 0,35 ne sont pas choisis ici : ce sont les seuils de `clean_bubbles`,
    transposés au fond local. C'est ce qui rend la distribution comparable à la seule échelle
    calibrée du dépôt."""
    lot = []
    for u in (0.90, 0.70, 0.50, 0.40, 0.20, 0.10):
        z = _zone(index=len(lot))
        z.style = {"ok": True, "uniformite_fond": u, "inverted": False,
                   "remplissage": 0.4, "orientation": "carree"}
        lot.append(z)
    paliers = banc_sfx.resumer(lot)["uniformite_paliers"]
    assert paliers == {"≥0.60": 2, "0.35–0.60": 2, "<0.35": 2}


def test_une_zone_non_mesurable_ne_fausse_pas_la_distribution():
    ok = _zone(index=0)
    ok.style = {"ok": True, "uniformite_fond": 0.9, "inverted": False,
                "remplissage": 0.4, "orientation": "carree"}
    pas_ok = _zone(index=1)
    pas_ok.style = {"ok": False, "uniformite_fond": 0.0, "inverted": False,
                    "remplissage": 0.0, "orientation": "carree"}
    r = banc_sfx.resumer([ok, pas_ok])
    assert r["zones"] == 2
    assert r["mesurees"] == 1
    assert r["uniformite"]["n"] == 1


def test_les_quantiles_d_une_distribution_vide_ne_levent_pas():
    r = banc_sfx.resumer([])
    assert r["zones"] == 0
    assert r["uniformite"]["med"] is None


def test_la_cle_d_une_zone_est_stable_et_lisible():
    assert _zone(page=63, index=2).cle == "manga A/Vol.1/p0063/z02"


# --------------------------------------------------------------------------- #
# Les crops — voie C
# --------------------------------------------------------------------------- #

def test_les_crops_sont_ecrits_hors_du_depot_et_nommes_par_leur_cle(tmp_path):
    volume = banc_sfx.banc.Volume("manga A", "Vol.1", tmp_path / "build")
    (tmp_path / "build" / "pages_out").mkdir(parents=True)
    Image.new("RGB", (100, 100), (255, 255, 255)).save(
        tmp_path / "build" / "pages_out" / "page_0001.png")
    zones = [_zone(page=1, index=0, bbox=(10, 10, 40, 40))]
    noms = banc_sfx.exporter_crops(zones, {("manga A", "Vol.1"): volume},
                                   tmp_path / "crops")
    assert noms == ["manga A_Vol.1_p0001_z00.png"]
    with Image.open(tmp_path / "crops" / noms[0]) as im:
        assert im.size == (30, 30)


def test_une_planche_absente_ne_fait_pas_echouer_l_export(tmp_path):
    volume = banc_sfx.banc.Volume("manga A", "Vol.1", tmp_path / "vide")
    noms = banc_sfx.exporter_crops([_zone()], {("manga A", "Vol.1"): volume},
                                   tmp_path / "crops")
    assert noms == []


# --------------------------------------------------------------------------- #
# Le tableau
# --------------------------------------------------------------------------- #

def test_le_tableau_porte_toutes_ses_colonnes():
    ligne = banc_sfx.ligne_volume("manga A / Vol.1", banc_sfx.resumer(_lot(10)))
    assert set(banc_sfx.COLONNES) <= set(ligne)


@pytest.mark.parametrize("valeur,attendu", [(None, "—"), (0.5, "0.500"), (1234, "1 234")])
def test_le_formatage_des_nombres(valeur, attendu):
    assert banc_sfx._n(valeur) == attendu


def test_les_zones_se_serialisent_en_json():
    """`--json` doit produire un fichier relisable : c'est lui qui porte la mesure quand les
    planches, elles, ne peuvent pas sortir du disque."""
    from dataclasses import asdict
    brut = json.dumps([asdict(z) for z in _lot(3)], ensure_ascii=False)
    relu = json.loads(brut)
    assert len(relu) == 3
    assert relu[0]["texte"] == "ゴォォォ"
