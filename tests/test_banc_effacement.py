# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc de l'effacement — `tools/banc_effacement.py` (lot 22).

Il ne lit aucun cache ici : les tomes de `build/` ne sont pas dans le dépôt, et un banc dont
les tests exigeraient le corpus ne se vérifierait sur aucune machine neuve. Ce qui est
vérifié est ce qui doit l'être — que les **trois mesures** disent ce qu'elles prétendent, et
que la **figure publiée** se refait à l'identique.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from tools import banc_effacement as banc


def test_les_trois_fonds_synthetiques_couvrent_les_trois_situations():
    """La figure du dépôt n'est pas une illustration : ses trois fonds reproduisent les trois
    régimes que la distribution d'uniformité du corpus désigne, dont celui où l'on refuse."""
    from manga import clean, effacement, sfx_lecture
    from manga.detection import BubbleRegion

    verdicts = {}
    for nom in banc.FONDS_SYNTHETIQUES:
        fond = banc._fond_synthetique(nom, 260, 150)
        encre = np.zeros((150, 260), dtype=bool)
        banc._glyphe(encre, 70, 36)
        arr = np.dstack([fond] * 3)
        arr[encre] = 245 if float(fond.mean()) < 128.0 else 16
        image = Image.fromarray(arr)
        masque = np.zeros((150, 260), dtype=bool)
        masque[28:126, 62:196] = True
        zone = BubbleRegion(bbox=(62, 28, 196, 126), mask=masque, score=1.0, cls=0,
                            kind="onomatopee")
        style = clean.analyser_zone_hors_bulle(image, zone)
        motif, _u = effacement.decider(style, sfx_lecture.LECTURE_SURE, {})
        verdicts[nom] = motif

    assert verdicts["aplat"] in effacement.MOTIFS_PEINTS
    assert verdicts["trame"] in effacement.MOTIFS_PEINTS
    # Le troisième existe pour montrer ce que le module NE FAIT PAS. S'il se mettait à
    # peindre, la figure publiée mentirait — et c'est le seul avant/après que le dépôt puisse
    # montrer, le corpus n'étant pas redistribuable.
    assert verdicts["structure"] == effacement.MOTIF_FOND_NON_UNIFORME


def test_la_figure_se_refait_a_l_identique(tmp_path):
    """Deux exécutions, deux fichiers identiques au bit près : aucune police système, aucun
    tirage aléatoire. `tests/conftest.py` rappelle ce que coûte une ressource système
    absente — la couverture saute en silence."""
    a = banc.figure_synthetique(tmp_path / "a.png", {})
    b = banc.figure_synthetique(tmp_path / "b.png", {})
    assert a.read_bytes() == b.read_bytes()


def test_la_figure_du_depot_est_a_jour():
    """Elle est publiée dans `docs/mesures/relettrage-2026-08-28.md` : si le module change ce qu'il
    peint, l'image du dépôt cesse de décrire le code, et un document de mesure qui montre
    autre chose que ce que la commande produit est pire qu'une absence d'image.

    ⚠ **On compare les PIXELS, pas les octets du PNG, et la nuance a un chiffre.** Le test
    comparait le flux d'octets ; il passait sous Windows et échouait sous `ubuntu-latest`
    depuis que la figure existe (lot 22), sur une différence de **longueur du bloc IDAT** —
    c'est-à-dire de compression zlib, pas de dessin. Comparer un encodage revient à tester la
    version de zlib du runner, ce que ce test ne veut pas dire.

    **Et les pixels, eux, ne peuvent pas diverger.** `figure_synthetique` n'ouvre aucune
    police, ne tire aucun aléa, et le seul appel transcendant est `6·sin(x/37)` dans le fond
    « aplat », converti en `uint8` par TRONCATURE. Mesuré sur la grille réelle : les seules
    valeurs exactement entières viennent de `x = 0`, où `sin(0) = 0` est exact sur toute
    plateforme IEEE ; la plus petite partie fractionnaire non nulle vaut **9,27 × 10⁻⁶** et la
    plus petite distance sous un entier **3,13 × 10⁻⁵**. Un écart d'1 ULP au voisinage de 242
    vaut ~2,8 × 10⁻¹⁴ — **neuf ordres de grandeur en dessous**. Aucune implémentation de `sin`
    ne peut donc faire basculer un pixel.

    L'identité au bit près reste vérifiée là où elle a un sens : deux exécutions sur la même
    machine, par `test_la_figure_se_refait_a_l_identique`."""
    import tempfile
    from pathlib import Path

    from PIL import Image
    publiee = Path(__file__).resolve().parents[1] / "docs" / "img" / "effacement-2026-08-28.png"
    assert publiee.exists(), "figure absente : `--synthetique` ne l'a jamais écrite"
    with tempfile.TemporaryDirectory() as d:
        refaite = banc.figure_synthetique(Path(d) / "f.png", {})
        with Image.open(refaite) as a, Image.open(publiee) as b:
            attendue, obtenue = np.asarray(b.convert("RGB")), np.asarray(a.convert("RGB"))
    assert obtenue.shape == attendue.shape, (
        f"la figure du dépôt n'a plus les mêmes dimensions : {attendue.shape} publiée contre "
        f"{obtenue.shape} refaite — relancer `python tools/banc_effacement.py --tous "
        f"--synthetique docs/img/effacement-2026-08-28.png`")
    differents = int((obtenue != attendue).any(axis=2).sum())
    assert differents == 0, (
        f"la figure du dépôt ne correspond plus au code — {differents} pixel(s) sur "
        f"{attendue.shape[0] * attendue.shape[1]} diffèrent, écart maximal "
        f"{int(np.abs(obtenue.astype(int) - attendue.astype(int)).max())} niveau(x). "
        f"Relancer `python tools/banc_effacement.py --tous "
        f"--synthetique docs/img/effacement-2026-08-28.png`")


def test_le_residu_mesure_bien_ce_qu_il_annonce():
    """« Part de la boîte dont la luminance s'écarte du fond de plus de `seuil` » — pas une
    moyenne, pas un écart-type. Un chiffre dont personne ne peut refaire la définition n'est
    pas une mesure."""
    arr = np.full((60, 60, 3), 200, dtype=np.uint8)
    arr[10:30, 10:40] = 20                       # 600 px sur 3 600 dans la boîte pleine
    assert banc._residu(arr, (0, 0, 60, 60), 200.0, 45.0) == 600 / 3600
    assert banc._residu(arr, (40, 40, 60, 60), 200.0, 45.0) == 0.0


def test_la_couture_se_lit_contre_le_grain_du_fond():
    """Une marche de 12 niveaux est invisible sur une trame et voyante sur un aplat : sans le
    grain, la couture n'a pas d'échelle. C'est le rapport des deux qui se lit."""
    arr = np.full((60, 60, 3), 200, dtype=np.uint8)
    peint = np.zeros((60, 60), dtype=bool)
    peint[20:40, 20:40] = True
    arr[peint] = 140                              # une marche franche de 60 niveaux
    anneau = np.zeros((60, 60), dtype=bool)
    anneau[0:10, :] = True                        # du fond parfaitement plat
    couture, grain = banc._couture(arr, peint, anneau)
    assert couture > 50 and grain == 0.0

    # Le même écart, sur un fond bruité : le grain monte, et le rapport le dit.
    bruite = arr.copy()
    rng = np.random.default_rng(22)
    bruite[0:10, :] = rng.integers(150, 250, (10, 60, 1)).repeat(3, axis=2)
    _couture2, grain2 = banc._couture(bruite, peint, anneau)
    assert grain2 > 10


def test_le_palier_range_chaque_zone_dans_une_seule_tranche():
    faire = lambda u: banc.Mesure(          # noqa: E731
        projet="p", tome="t", page=1, index=0, tri="japonais", motif="diffusion",
        uniformite=u, aire_boite=1)
    assert faire(0.90).palier == "≥0,60"
    assert faire(0.60).palier == "≥0,60"
    assert faire(0.59).palier == "0,35–0,60"
    assert faire(0.35).palier == "0,35–0,60"
    assert faire(0.34).palier == "<0,35"
    assert faire(0.00).palier == "<0,35"
