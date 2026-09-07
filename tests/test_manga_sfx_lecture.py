# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Lot 21 — lire l'onomatopée avant de prétendre l'écrire.

Cinq objets neufs, cinq blocs de tests :

· `clean.analyser_zone_hors_bulle` — la mesure que `analyze_regions` ne fait pas (L21.2) ;
· les bornes hautes de `text_detection.hors_des_bulles`, désarmées (L21.1) ;
· `sfx_lecture` — normalisation, similarité, verdict de concordance (L21.3) ;
· `quality_manga.onomatopee_brodee` — le refus d'une phrase inventée (L21.4) ;
· `gloss` — le contour pris sur la couleur mesurée (L21.5).

⚠ Aucun de ces tests ne charge de modèle ni Qt : tout ce qui décide se teste sans les deux
(cf. `docs/plans/00-CONTEXTE-AGENT.md` §8).
"""
import numpy as np
import pytest
from PIL import Image

from manga import gloss as gloss_mod
from manga import quality_manga as q
from manga import sfx_lecture, text_detection
from manga.clean import (StyleHorsBulle, analyser_zone_hors_bulle,
                         analyser_zones_hors_bulle, analyze_regions)
from manga.detection import BubbleRegion


# --------------------------------------------------------------------------- #
# L21.2 — mesurer une zone hors bulle
# --------------------------------------------------------------------------- #

def _planche(fond=(255, 255, 255), taille=(400, 300)) -> Image.Image:
    return Image.new("RGB", taille, fond)


def _zone(box, taille=(400, 300), mask=None) -> BubbleRegion:
    return BubbleRegion(bbox=box, mask=mask, score=1.0, cls=0, kind="onomatopee")


def _peindre(image, box, couleur):
    arr = np.asarray(image).copy()
    x0, y0, x1, y1 = box
    arr[y0:y1, x0:x1] = couleur
    return Image.fromarray(arr)


def test_encre_sombre_sur_fond_clair_n_est_pas_inversee():
    im = _peindre(_planche(), (150, 120, 220, 180), (10, 10, 10))
    st = analyser_zone_hors_bulle(im, _zone((150, 120, 220, 180)))
    assert st.ok
    assert st.inverted is False
    assert st.fond == (255, 255, 255)
    assert max(st.encre) < 40


def test_encre_claire_sur_fond_sombre_est_detectee_comme_inversee():
    """⚠ LE défaut que `analyze_regions` codait en dur.

    Pour `kind != "bulle"` il rend `inverted=False` **toujours**. Un `ゴォォォ` blanc à
    contour noir sur un dessin sombre est le cas exactement inverse, et il vaut 13,6 % des
    2 455 zones mesurées du corpus. Ce test aurait échoué avant le lot 21 : la fonction
    n'existait pas, et la seule réponse disponible était `False`."""
    im = _peindre(_planche(fond=(12, 12, 12)), (150, 120, 220, 180), (245, 245, 245))
    st = analyser_zone_hors_bulle(im, _zone((150, 120, 220, 180)))
    assert st.ok
    assert st.inverted is True
    assert min(st.fond) < 40
    assert min(st.encre) > 200


def test_analyze_regions_rend_toujours_le_style_vide_sur_une_non_bulle():
    """L'alignement par position ne bouge pas : c'est la raison de la fonction séparée."""
    im = _peindre(_planche(fond=(12, 12, 12)), (150, 120, 220, 180), (245, 245, 245))
    r = _zone((150, 120, 220, 180), mask=np.zeros((300, 400), dtype=bool))
    (style,) = analyze_regions(im, [r])
    assert style.ok is False
    assert style.inverted is False
    assert style.background == (255, 255, 255)


def test_le_fond_est_echantillonne_HORS_de_la_boite():
    """Sinon l'encre de l'onomatopée ferait chuter l'uniformité de toute zone.

    Ici la boîte est noire à 100 % et le pourtour parfaitement uni : l'uniformité doit valoir
    1,0. Un échantillonnage incluant la boîte la ferait tomber sous 0,5."""
    im = _peindre(_planche(), (150, 120, 220, 180), (0, 0, 0))
    st = analyser_zone_hors_bulle(im, _zone((150, 120, 220, 180)))
    assert st.uniformite_fond == pytest.approx(1.0)


def test_un_fond_local_bruite_fait_chuter_l_uniformite():
    rng = np.random.default_rng(21)
    arr = rng.integers(0, 256, size=(300, 400, 3), dtype=np.uint8)
    arr[120:180, 150:220] = 0
    st = analyser_zone_hors_bulle(Image.fromarray(arr), _zone((150, 120, 220, 180)))
    assert st.ok
    assert st.uniformite_fond < 0.35     # le palier « ne rien peindre » de `clean_bubbles`


def test_orientation_et_aire_relative():
    im = _peindre(_planche(), (150, 20, 200, 280), (0, 0, 0))
    st = analyser_zone_hors_bulle(im, _zone((150, 20, 200, 280)))
    assert st.orientation == "verticale"
    assert st.aire_frac == pytest.approx(50 * 260 / (400 * 300))
    horizontale = analyser_zone_hors_bulle(
        _peindre(_planche(), (20, 140, 380, 170), (0, 0, 0)), _zone((20, 140, 380, 170)))
    assert horizontale.orientation == "horizontale"


def test_une_zone_sans_contraste_est_non_ok_plutot_que_devinee():
    """Ne jamais deviner : c'est la règle de `analyze_bubble`, qui rend non-ok au lieu de
    supposer du blanc."""
    st = analyser_zone_hors_bulle(_planche(), _zone((150, 120, 220, 180)))
    assert st.ok is False
    assert st.part_encre == 0.0


def test_une_boite_degeneree_ne_leve_pas():
    st = analyser_zone_hors_bulle(_planche(), _zone((10, 10, 10, 10)))
    assert st.ok is False


def test_la_liste_reste_alignee_sur_les_regions():
    im = _peindre(_planche(), (150, 120, 220, 180), (0, 0, 0))
    regions = [BubbleRegion(bbox=(0, 0, 50, 50), mask=None, score=1.0, cls=0, kind="bulle"),
               _zone((150, 120, 220, 180))]
    styles = analyser_zones_hors_bulle(im, regions)
    assert len(styles) == len(regions)
    assert all(isinstance(s, StyleHorsBulle) for s in styles)
    assert styles[0].ok is False       # une bulle n'est pas mesurée par cette fonction
    assert styles[1].ok is True


# --------------------------------------------------------------------------- #
# L21.1 — les bornes hautes, et le fait qu'elles soient DÉSARMÉES
# --------------------------------------------------------------------------- #

def _masque_avec(boites, forme=(300, 400)) -> np.ndarray:
    m = np.zeros(forme, dtype=bool)
    for x0, y0, x1, y1 in boites:
        m[y0:y1, x0:x1] = True
    return m


def test_les_bornes_hautes_sont_desarmees_par_defaut():
    """Le comportement par défaut est celui d'avant le lot, au bit près."""
    assert text_detection.AIRE_MAX_FRAC == 0.0
    assert text_detection.REMPLISSAGE_MAX == 0.0
    masque = _masque_avec([(10, 10, 390, 290)])         # 95 % de la planche
    zones = text_detection.hors_des_bulles(masque, [])
    assert len(zones) == 1


def test_la_borne_d_aire_armee_ecarte_et_COMPTE():
    masque = _masque_avec([(10, 10, 390, 290), (20, 20, 60, 60)])
    diag: dict = {}
    zones = text_detection.hors_des_bulles(masque, [], aire_max_frac=0.20,
                                           diagnostic=diag)
    assert zones == []            # la petite est absorbée par la grande au groupement
    assert diag["rejets"]["aire_max"] == 1


def test_la_borne_de_remplissage_armee_ecarte_et_COMPTE():
    masque = _masque_avec([(50, 50, 250, 250)])         # boîte pleine : remplissage 1,0
    diag: dict = {}
    zones = text_detection.hors_des_bulles(masque, [], remplissage_max=0.80,
                                           diagnostic=diag)
    assert zones == []
    assert diag["rejets"]["remplissage_max"] == 1


def test_les_rejets_sont_cumules_entre_appels():
    """Le diagnostic d'un tome agrège plusieurs planches ; un écrasement perdrait tout sauf
    la dernière."""
    diag: dict = {}
    for _ in range(3):
        text_detection.hors_des_bulles(_masque_avec([(10, 10, 390, 290)]), [],
                                       aire_max_frac=0.20, diagnostic=diag)
    assert diag["rejets"]["aire_max"] == 3


def test_une_zone_sous_l_aire_minimale_est_comptee_elle_aussi():
    diag: dict = {}
    text_detection.hors_des_bulles(_masque_avec([(10, 10, 20, 20)]), [], diagnostic=diag)
    assert diag["rejets"]["aire_min"] == 1


# --------------------------------------------------------------------------- #
# L21.3 — concordance
# --------------------------------------------------------------------------- #

def test_deux_lectures_identiques_sont_sures():
    assert sfx_lecture.verdict(["ゴォォォ", "ゴォォォ"])[0] == sfx_lecture.LECTURE_SURE


def test_une_seule_voie_ne_concorde_avec_rien():
    """⚠ C'est l'état du dépôt AVANT ce lot : une lecture, aucune confirmation. L'appeler
    « sûre » reviendrait à baptiser le problème."""
    assert sfx_lecture.verdict(["ゴォォォ"])[0] == sfx_lecture.LECTURE_DOUTEUSE
    assert sfx_lecture.verdict(["ゴォォォ", ""])[0] == sfx_lecture.LECTURE_DOUTEUSE
    assert sfx_lecture.verdict([])[0] == sfx_lecture.LECTURE_DOUTEUSE


def test_le_cas_mesure_de_la_page_63_reste_douteux():
    """`ゴォォォ` lu `こっちは` par `manga-ocr` : deux voies qui divergent franchement."""
    verdict, score = sfx_lecture.verdict(["ゴォォォ", "こっちは"])
    assert verdict == sfx_lecture.LECTURE_DOUTEUSE
    assert score < 0.5


def test_la_ponctuation_pleine_et_demi_chasse_concorde():
    """`．．．` et `...` disent la même chose ; les déclarer discordants ferait passer en voie
    C 398 zones sur 2 456 pour un problème d'encodage."""
    assert sfx_lecture.verdict(["．．．", "..."])[0] == sfx_lecture.LECTURE_SURE


def test_un_ecart_d_un_caractere_reste_concordant():
    """Mesuré sur l'échantillon : deux lectures d'une même narration diffèrent couramment
    d'un signe, là où deux lectures d'un dessin n'ont rien en commun."""
    a = "私の知らないところで冗談のように変わっていく"
    b = "私の知らないところで歳のように変わっていく"
    assert sfx_lecture.verdict([a, b])[0] == sfx_lecture.LECTURE_SURE


def test_la_normalisation_n_est_jamais_ce_qu_on_persiste():
    """Elle replie l'allongement de la ponctuation, pas celui des voyelles : `ォォォ` porte
    l'intensité et doit survivre à la comparaison."""
    assert "ォォォ" in sfx_lecture.normaliser("ゴォォォ！！")
    assert sfx_lecture.normaliser("ＲａｗＬａｚｙ．ＳＩ") == "rawlazysi"
    # NFKC replie la pleine chasse AVANT le retrait : les deux formes doivent disparaître.
    assert sfx_lecture.normaliser("．．．") == sfx_lecture.normaliser("...") == ''


def test_taux_sures_et_alignement_des_verdicts():
    verdicts, scores = sfx_lecture.verdicts([["ゴ", "ゴ"], ["ゴ", "バ"], []])
    assert verdicts == [sfx_lecture.LECTURE_SURE, sfx_lecture.LECTURE_DOUTEUSE,
                        sfx_lecture.LECTURE_DOUTEUSE]
    assert len(scores) == 3
    assert sfx_lecture.taux_sures(verdicts) == pytest.approx(1 / 3)
    assert sfx_lecture.taux_sures([]) == 0.0


# --------------------------------------------------------------------------- #
# L21.4 — refuser une traduction brodée
# --------------------------------------------------------------------------- #

def test_le_predicat_est_desarme_par_defaut():
    assert q.BRODERIE_RATIO == 0.0
    assert q.onomatopee_brodee(
        "あ", "C'est faisable. Après la diffusion vient le focalisation.") is False


def test_les_cas_mesures_du_corpus_sont_refuses():
    """Les six paires que le balayage a retenues sur 1 596 — aucune n'est une traduction."""
    for source, rendu in [
        ("あ", "C'est faisable. Après la diffusion vient le focalisation."),
        ("あれ", "Mitsukage... Désolé de t'avoir impliqué, je vais te le rendre."),
        ("プラン", "Ces émotions n'attendent que l'exécution. Cette sensation est-elle..."),
        ("ガズン", "LIEUTENANT AOZAKA ! UN KATAPHRHAKT INCONNU !"),
    ]:
        assert q.onomatopee_brodee(source, rendu, ratio=3.0), source


def test_une_vraie_onomatopee_passe():
    for source, rendu in [("ドドド", "BROUM"), ("ゴォォォ", "VROOOM"), ("ザッ", "SHTAK"),
                          ("シーン", "SILENCE"), ("．．．", "...")]:
        assert not q.onomatopee_brodee(source, rendu, ratio=3.0), source


def test_le_plancher_protege_une_glose_courte():
    """⚠ Sans lui, `『あ』 → « Eh bien alors… »` (ratio 4,0) serait refusé : c'est pourtant une
    glose parfaitement légitime. Le ratio seul retient 10 paires sur 1 596, dont 4
    innocentes."""
    assert not q.onomatopee_brodee("あ", "Eh bien alors...", ratio=3.0)


def test_le_refus_garde_l_alignement_par_position():
    """Un refus qui décalerait la liste serait bien pire que la broderie qu'il corrige."""
    sources = ["ドドド", "あ", "ザッ"]
    rendus = ["BROUM", "Une phrase entière inventée de toutes pièces par le modèle", "SHTAK"]
    sortie, refuses = q.refuser_onomatopees_brodees(sources, rendus, ratio=3.0)
    assert len(sortie) == 3
    assert sortie == ["BROUM", "", "SHTAK"]
    assert refuses == [1]


def test_le_motif_a_un_libelle_et_n_est_pas_dans_le_registre_de_page():
    assert q.MOTIF_SFX_BRODERIE in q.LIBELLES
    assert q.MOTIF_SFX_BRODERIE in q.MOTIFS_HORS_REGISTRE
    assert q.MOTIF_SFX_BRODERIE not in [nom for nom, _ in q.MOTIFS]


# --------------------------------------------------------------------------- #
# L21.5 — le contour de glose prend la couleur mesurée
# --------------------------------------------------------------------------- #

def _sfx_pour_glose(taille=(400, 300)):
    m = np.zeros((taille[1], taille[0]), dtype=bool)
    m[140:160, 40:80] = True
    return [BubbleRegion(bbox=(40, 140, 80, 160), mask=m, score=1.0, cls=0,
                         kind="onomatopee")]


def test_sans_le_reglage_la_glose_ne_porte_aucune_couleur_mesuree():
    """Comportement d'avant le lot, au bit près."""
    image = Image.new("RGB", (400, 300), (200, 200, 200))
    gloses, _refus = gloss_mod.placer(image, _sfx_pour_glose(), ["BOUM"])
    assert gloses[0] is not None
    assert gloses[0].fond is None


def test_avec_le_reglage_la_glose_porte_la_couleur_du_fond_local():
    image = Image.new("RGB", (400, 300), (96, 96, 96))
    gloses, _refus = gloss_mod.placer(image, _sfx_pour_glose(), ["BOUM"],
                                      cfg={"glose_contour_mesure": True})
    assert gloses[0] is not None
    assert gloses[0].fond == (96, 96, 96)


def test_le_contour_mesure_change_reellement_les_pixels():
    """Le test qui compte : deux rendus, deux images différentes.

    Sur un aplat gris à 96, le contour d'avant est du NOIR PUR — un halo qui se voit plus
    que la glose. Avec la couleur mesurée, il vaut 96 : le pixel le plus sombre de la
    planche remonte, et c'est exactement l'effet cherché."""
    image = Image.new("RGB", (400, 300), (96, 96, 96))
    sfx = _sfx_pour_glose()
    avant, _ = gloss_mod.placer(image, sfx, ["BOUM"])
    apres, _ = gloss_mod.placer(image, sfx, ["BOUM"],
                                cfg={"glose_contour_mesure": True})
    rendu_avant = np.asarray(gloss_mod.dessiner(image, avant))
    rendu_apres = np.asarray(gloss_mod.dessiner(image, apres,
                                                cfg={"glose_contour_mesure": True}))
    assert not np.array_equal(rendu_avant, rendu_apres)
    assert int(rendu_avant.min()) < 16          # halo noir posé sur un gris à 96
    assert int(rendu_apres.min()) >= 96         # plus aucun pixel plus sombre que le fond


# --------------------------------------------------------------------------- #
# Le câblage : rapport et orchestrateur
# --------------------------------------------------------------------------- #

def test_le_dossier_de_crops_ne_diverge_pas_entre_les_deux_modules():
    """`report_manga` ne peut pas importer l'orchestrateur (cycle), il porte donc le nom en
    double. Deux constantes valant la même chose à deux endroits sont deux constantes qui
    divergeront — sauf si un test l'interdit."""
    from manga import orchestrator_manga, report_manga
    assert report_manga.DOSSIER_CROPS_SFX == orchestrator_manga.DOSSIER_CROPS_SFX


def test_tous_les_motifs_de_rejet_ont_un_libelle():
    """Un filtre muet est la façon dont on perd les zones suivantes sans le voir."""
    from manga import report_manga
    diag: dict = {}
    text_detection.hors_des_bulles(_masque_avec([(10, 10, 390, 290), (5, 5, 8, 8)]), [],
                                   aire_max_frac=0.20, remplissage_max=0.80,
                                   diagnostic=diag)
    assert set(diag["rejets"]) <= set(report_manga.LIBELLES_REJET_SFX)
    # Et le registre couvre les quatre motifs que la fonction sait produire.
    assert set(report_manga.LIBELLES_REJET_SFX) == {
        "aire_min", "aire_max", "remplissage_max", "dans_bulle"}


def test_la_config_livree_arme_ce_que_la_mesure_soutient_et_rien_de_plus():
    """⚠ Le seul réglage armé par `config.yaml` est `broderie_ratio`, et c'est écrit en tête
    du CHANGELOG. Les quatre autres sont désarmés parce que la mesure ne les porte pas — ce
    test est ce qui empêche qu'on les arme un jour sans refaire la mesure."""
    import yaml
    from pathlib import Path
    racine = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))
    sfx = cfg["manga"]["onomatopees"]
    assert sfx["broderie_ratio"] == 3.0
    assert sfx["concordance"] is False
    assert sfx["crops_illisibles"] == 0
    assert sfx["aire_max_frac"] == 0.0
    assert sfx["remplissage_max"] == 0.0
    assert cfg["manga"]["typeset"]["glose_contour_mesure"] is False
