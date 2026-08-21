# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Scission des régions bi-lobées (lot 4.2) : primitives numpy, décision, migration du cache.

Le défaut visé, mesuré sur *manga A* Vol.1 : le détecteur émet **une** région
là où le dessinateur a mis **deux** ballons qui se touchent (5 régions pour 6 ballons page 136,
8 pour 9 page 142). Les deux répliques sont alors OCRisées en une chaîne
(`敵機２時方向！いいよ転校生！！`, deux locuteurs), traduites en une, et composées dans la
géométrie fusionnée — donc sur le goulot entre les lobes, à 13 px quand les autres bulles de la
planche sont à 17-31 px. Aucun compteur ne s'en apercevait.

Le réglage est CONSERVATEUR et les tests le disent : scinder à tort casse une planche correcte,
ne pas scinder laisse le défaut en place. Plusieurs tests vérifient donc qu'on ne scinde **pas**.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import bubbles_split, checkpoints, geometry
from manga.detection import BubbleRegion

TAILLE = (300, 400)          # (largeur, hauteur)


def _ellipse(box, taille=TAILLE) -> np.ndarray:
    m = Image.new("L", taille, 0)
    ImageDraw.Draw(m).ellipse(list(box), fill=255)
    return np.asarray(m) > 127


def _bilobe() -> np.ndarray:
    """Deux ballons en diagonale qui se touchent — la géométrie exacte des pages 136 et 142 :
    le recouvrement horizontal des deux lobes (60 px ici) est le goulot que l'érosion coupe,
    et il est plus ÉTROIT que chaque lobe (160 px)."""
    return _ellipse((120, 20, 280, 200)) | _ellipse((20, 180, 180, 380))


def _region(mask, kind="bulle") -> BubbleRegion:
    ys, xs = np.nonzero(mask)
    return BubbleRegion(bbox=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
                        mask=mask, score=0.9, cls=0, kind=kind)


# --------------------------------------------------------------------------- #
# geometry.composantes
# --------------------------------------------------------------------------- #

def test_composantes_separe_et_trie_par_aire_decroissante():
    m = np.zeros((40, 60), bool)
    m[5:15, 5:20] = True                   # 150 px
    m[20:35, 30:55] = True                 # 375 px
    comps = geometry.composantes(m)
    assert [int(c.sum()) for c in comps] == [375, 150]


def test_composantes_est_une_partition_exacte():
    m = np.zeros((40, 60), bool)
    m[5:15, 5:20] = True
    m[20:35, 30:55] = True
    m[0, 0] = True
    comps = geometry.composantes(m)
    assert len(comps) == 3
    union = np.zeros_like(m)
    for c in comps:
        assert not (union & c).any(), "les composantes ne doivent pas se chevaucher"
        union |= c
    assert (union == m).all()


def test_composantes_filtre_les_eclats():
    m = np.zeros((40, 60), bool)
    m[5:15, 5:20] = True
    m[0, 0] = True
    assert len(geometry.composantes(m, min_aire=10)) == 1


def test_composantes_est_en_4_connexite():
    """Deux blocs qui ne se touchent que par un COIN doivent rester deux composantes : c'est
    exactement le cas qu'on veut pouvoir séparer, et la 8-connexité les fusionnerait."""
    m = np.zeros((10, 10), bool)
    m[0:5, 0:5] = True
    m[5:10, 5:10] = True
    assert len(geometry.composantes(m)) == 2


def test_composantes_dun_masque_vide():
    assert geometry.composantes(np.zeros((5, 5), bool)) == []


def test_composantes_gere_une_ligne_pleine():
    """`argmin` renvoie 0 sur une ligne entièrement vraie : le garde-fou de l'extraction des
    plages doit tenir sur un masque qui touche les deux bords."""
    m = np.ones((6, 7), bool)
    comps = geometry.composantes(m)
    assert len(comps) == 1 and int(comps[0].sum()) == 42


# --------------------------------------------------------------------------- #
# geometry.remplissage
# --------------------------------------------------------------------------- #

def test_remplissage_dun_rectangle_vaut_un():
    m = np.zeros((20, 30), bool)
    m[2:12, 4:24] = True
    assert geometry.remplissage(m) == pytest.approx(1.0)


def test_remplissage_dune_ellipse_approche_pi_sur_4():
    assert geometry.remplissage(_ellipse((10, 10, 210, 310))) == pytest.approx(0.785, abs=0.01)


def test_remplissage_dun_bilobe_est_bas():
    """C'est LA mesure qui distingue les deux cas — mesuré 0,606 page 136 et 0,616 page 142,
    contre une médiane de 0,89 sur les 687 bulles de plus de 20 000 px² du tome."""
    assert geometry.remplissage(_bilobe()) < 0.70


def test_remplissage_dun_masque_vide_vaut_zero():
    assert geometry.remplissage(np.zeros((5, 5), bool)) == 0.0


# --------------------------------------------------------------------------- #
# geometry.scinder_par_erosion
# --------------------------------------------------------------------------- #

def test_un_bilobe_est_scinde_en_deux():
    lobes = geometry.scinder_par_erosion(_bilobe())
    assert lobes is not None and len(lobes) == 2
    assert all(geometry.remplissage(x) >= 0.72 for x in lobes)


def test_la_scission_est_une_partition_exacte_du_masque():
    """Contrainte dure : `checkpoints.save_regions` écrit une image d'ÉTIQUETTES et
    attribuerait un pixel partagé à la dernière bulle écrite. Et l'union doit valoir le masque
    d'origine, sinon le nettoyage laisserait du japonais visible."""
    m = _bilobe()
    lobes = geometry.scinder_par_erosion(m)
    union = np.zeros_like(m)
    for lobe in lobes:
        assert not (union & lobe).any()
        union |= lobe
    assert (union == m).all()


def test_une_bulle_unique_nest_jamais_scindee():
    """Une ellipse remplit 0,785 de sa boîte : elle passe donc le filtre des candidats, et
    c'est la validation qui doit la protéger. Scinder à tort casse une planche correcte."""
    assert geometry.scinder_par_erosion(_ellipse((20, 20, 280, 380))) is None


def test_un_rectangle_nest_jamais_scinde():
    m = np.zeros((400, 300), bool)
    m[20:380, 20:280] = True
    assert geometry.scinder_par_erosion(m) is None


def test_une_region_trop_petite_nest_pas_scindee():
    """Deux répliques françaises ne tiennent pas dans 100×100 px. Mesuré : un fragment de
    kanji de 4 116 px (page 33) était scindé en deux « ballons » plausibles."""
    petit = _ellipse((10, 10, 60, 50), taille=(80, 80)) | _ellipse((10, 45, 60, 75), taille=(80, 80))
    assert geometry.scinder_par_erosion(petit) is None


def test_un_lobe_trop_maigre_fait_refuser_la_scission():
    """Un ballon plus un mince appendice n'est pas un double : `remplissage_lobe_min` doit le
    rejeter. Mesuré page 80 : une bulle unique tranchée en deux, remplissage de lobe 0,36."""
    m = _ellipse((60, 20, 240, 260))
    m[270:380, 145:155] = True          # tige fine, collée par le bas
    assert geometry.scinder_par_erosion(m) is None


def test_un_eclat_detache_ne_fait_pas_rejeter_une_bonne_scission():
    """Défaut trouvé page 64 : un éclat de 200 px situé à l'opposé du masque, recollé au plus
    gros lobe, faisait passer sa boîte de 44 000 à 91 700 px² — son remplissage tombait à 0,48
    et une scission pourtant parfaite était rejetée. La validation se fait donc sur les lobes
    AVANT absorption des restes."""
    m = _bilobe()
    m[5:12, 5:12] = True                # éclat isolé, hors de portée de la repousse
    lobes = geometry.scinder_par_erosion(m)
    assert lobes is not None and len(lobes) == 2
    union = np.zeros_like(m)
    for lobe in lobes:
        union |= lobe
    assert (union == m).all(), "l'éclat doit être rattaché, pas perdu"


def test_la_scission_est_deterministe():
    m = _bilobe()
    a = geometry.scinder_par_erosion(m)
    b = geometry.scinder_par_erosion(m)
    assert all((x == y).all() for x, y in zip(a, b))


# --------------------------------------------------------------------------- #
# bubbles_split.scinder_regions
# --------------------------------------------------------------------------- #

def test_une_region_bilobee_est_remplacee_par_ses_lobes():
    regions = [_region(_bilobe())]
    sortie, diag = bubbles_split.scinder_regions(regions)
    assert len(sortie) == 2
    assert all(r.scindee for r in sortie)
    assert all(r.score == 0.9 and r.cls == 0 and r.kind == "bulle" for r in sortie)
    assert [d["type"] for d in diag] == ["scindee"]
    assert diag[0]["lobes"] == 2


def test_les_boites_des_lobes_sont_recalculees():
    regions = [_region(_bilobe())]
    sortie, _ = bubbles_split.scinder_regions(regions)
    for r in sortie:
        ys, xs = np.nonzero(r.mask)
        assert r.bbox == (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        assert r.bbox != regions[0].bbox


def test_une_bulle_bien_remplie_nest_meme_pas_examinee():
    m = np.zeros((400, 300), bool)
    m[20:380, 20:280] = True             # remplissage 1,0 > seuil des candidats
    sortie, diag = bubbles_split.scinder_regions([_region(m)])
    assert len(sortie) == 1 and diag == []


def test_une_region_non_bulle_est_laissee_intacte():
    """`kind != "bulle"` est réservé à la phase 2 (onomatopées, texte posé sur le dessin) :
    la scission ne doit pas y toucher."""
    regions = [_region(_bilobe(), kind="onomatopee")]
    sortie, diag = bubbles_split.scinder_regions(regions)
    assert sortie == regions and diag == []


def test_actif_false_ne_touche_a_rien():
    regions = [_region(_bilobe())]
    sortie, diag = bubbles_split.scinder_regions(regions, {"actif": False})
    assert [id(r) for r in sortie] == [id(r) for r in regions] and diag == []


def test_une_bulle_A_LONGUE_QUEUE_est_DENTELEE_et_non_suspecte():
    """Un ballon prolongé d'une queue a un remplissage bas — 0,3 à 0,6 — sans être bi-lobé
    pour autant. Le rapport le rangeait sous « bi-lobée SUSPECTE ».

    Mesuré sur le Vol.2 : les **45** régions ainsi signalées sont TOUTES de cette famille
    (ballons de cri au contour en étoile, bulles à queue, une case de décor). Pas un seul vrai
    double, et donc 45 lignes de rapport qui accusaient la détection pour la forme normale
    d'une bulle de manga."""
    m = _ellipse((60, 20, 240, 260))
    m[270:380, 145:155] = True
    sortie, diag = bubbles_split.scinder_regions([_region(m)])
    assert len(sortie) == 1
    assert [d["type"] for d in diag] == ["dentelee"]
    assert diag[0]["motif"] == "aucun_goulot"
    assert diag[0]["remplissage"] < 0.70


def test_une_region_AVEC_GOULOT_refusee_reste_suspecte():
    """L'autre branche, la seule vraiment ambiguë : l'érosion a bien trouvé deux lobes, et
    les garde-fous ont refusé de couper. C'est là — et seulement là — qu'un œil humain a
    quelque chose à trancher."""
    sortie, diag = bubbles_split.scinder_regions(
        [_region(_bilobe())], {"remplissage_lobe_min": 0.99, "seuil_suspect": 0.99})
    assert len(sortie) == 1
    assert [d["type"] for d in diag] == ["suspecte"]
    assert diag[0]["motif"] == "lobe_trop_creux"


def test_classer_non_scindees_distingue_les_deux_familles():
    queue = _ellipse((60, 20, 240, 260))
    queue[270:380, 145:155] = True
    classement = bubbles_split.classer_non_scindees([_region(queue)])
    assert classement == {0: "dentelee"}
    ambigue = bubbles_split.classer_non_scindees(
        [_region(_bilobe())], {"remplissage_lobe_min": 0.99, "seuil_suspect": 0.99})
    assert ambigue == {0: "suspecte"}


def test_classer_non_scindees_ignore_les_bulles_pleines():
    """Une bulle ronde ordinaire remplit sa boîte : rien à classer, et surtout rien à
    éroder — c'est ce qui garde le coût de cette sonde négligeable sur un tome."""
    assert bubbles_split.classer_non_scindees([_region(_ellipse((20, 20, 280, 380)))]) == {}


def test_l_ordre_des_autres_regions_est_preserve():
    """`ocr.json` et `traduction.json` s'alignent PAR POSITION sur cet ordre : une région
    scindée doit être remplacée à sa place, pas ajoutée en fin de liste."""
    plein = np.zeros((400, 300), bool)
    plein[300:380, 20:120] = True
    avant, apres = _region(plein), _region(plein.copy())
    sortie, _ = bubbles_split.scinder_regions([avant, _region(_bilobe()), apres])
    assert len(sortie) == 4
    assert sortie[0] is avant and sortie[3] is apres
    assert sortie[1].scindee and sortie[2].scindee


def test_les_seuils_sont_configurables():
    regions = [_region(_bilobe())]
    # Un remplissage de lobe exigé irréaliste doit tout refuser.
    sortie, diag = bubbles_split.scinder_regions(regions, {"remplissage_lobe_min": 0.99})
    assert len(sortie) == 1
    assert [d["type"] for d in diag] == ["suspecte"]


# --------------------------------------------------------------------------- #
# Persistance et migration du cache
# --------------------------------------------------------------------------- #

def _scinder(regions):
    return bubbles_split.scinder_regions(regions)


def test_le_drapeau_scindee_survit_au_cache(tmp_path):
    """Il doit survivre, sinon `RAPPORT.md` ne pourrait décrire que le run et non le tome :
    un `--from rendu` réécrit tous les `qa.json`."""
    sortie, _ = bubbles_split.scinder_regions([_region(_bilobe())])
    checkpoints.save_regions(tmp_path, sortie, TAILLE)
    relues = checkpoints.load_regions(tmp_path)
    assert relues is not None and len(relues) == 2
    assert all(r.scindee for r in relues)


def test_une_region_non_scindee_se_relit_sans_drapeau(tmp_path):
    m = np.zeros((400, 300), bool)
    m[20:380, 20:280] = True
    checkpoints.save_regions(tmp_path, [_region(m)], TAILLE)
    assert checkpoints.load_regions(tmp_path)[0].scindee is False


def test_migration_v2_v3_scinde_et_invalide_les_textes(tmp_path):
    """Le cœur de la migration : elle se fait **sans le modèle ONNX** (c'est un
    post-traitement de masques), mais une page qui gagne des bulles perd ses textes — leur
    alignement par position est irrécupérable, et la chaîne fusionnée portait deux répliques."""
    from manga.ocr import reading_order

    ancienne = _region(_bilobe())
    checkpoints.save_regions(tmp_path, [ancienne], TAILLE)
    # Rétrograder le format à la main : c'est l'état d'un cache d'avant le lot 4.2.
    import json
    meta = json.loads((tmp_path / "regions.json").read_text(encoding="utf-8"))
    meta["format"] = 2
    (tmp_path / "regions.json").write_text(json.dumps(meta), encoding="utf-8")
    checkpoints.save_ocr(tmp_path, ["敵機２時方向！いいよ転校生！！"])
    checkpoints.save_traduction(tmp_path, ["Avion ennemi ! Allez, nouvelle élève !!"])
    (tmp_path / checkpoints.QA_FILENAME).write_text("{}", encoding="utf-8")

    resume = checkpoints.migrate_page(tmp_path, reading_order, _scinder)

    assert resume is not None and "scindée" in resume
    assert len(checkpoints.load_regions(tmp_path)) == 2
    assert checkpoints.load_ocr(tmp_path) is None
    assert checkpoints.load_traduction(tmp_path) is None
    assert not (tmp_path / checkpoints.QA_FILENAME).exists()


def test_migration_v2_v3_ne_touche_pas_une_page_sans_bilobe(tmp_path):
    """Les planches saines gardent tout : c'est ce qui rend la migration bon marché — 18
    planches sur 150 touchées sur le tome de référence."""
    from manga.ocr import reading_order

    import json
    m = np.zeros((400, 300), bool)
    m[20:380, 20:280] = True
    checkpoints.save_regions(tmp_path, [_region(m)], TAILLE)
    meta = json.loads((tmp_path / "regions.json").read_text(encoding="utf-8"))
    meta["format"] = 2
    (tmp_path / "regions.json").write_text(json.dumps(meta), encoding="utf-8")
    checkpoints.save_ocr(tmp_path, ["こんにちは"])
    checkpoints.save_traduction(tmp_path, ["Bonjour"])

    resume = checkpoints.migrate_page(tmp_path, reading_order, _scinder)

    assert resume is not None and "aucune bulle bi-lobée" in resume
    assert checkpoints.load_ocr(tmp_path) == ["こんにちは"]
    assert checkpoints.load_traduction(tmp_path) == ["Bonjour"]
    assert checkpoints.checkpoint_format(tmp_path) == checkpoints.FORMAT_VERSION


def test_migration_est_idempotente(tmp_path):
    from manga.ocr import reading_order

    import json
    checkpoints.save_regions(tmp_path, [_region(_bilobe())], TAILLE)
    meta = json.loads((tmp_path / "regions.json").read_text(encoding="utf-8"))
    meta["format"] = 2
    (tmp_path / "regions.json").write_text(json.dumps(meta), encoding="utf-8")

    assert checkpoints.migrate_page(tmp_path, reading_order, _scinder) is not None
    assert checkpoints.migrate_page(tmp_path, reading_order, _scinder) is None
