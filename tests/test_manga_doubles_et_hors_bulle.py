# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Lot 13 — les bulles doubles et le texte hors bulle.

Deux familles de défauts, réunies ici parce qu'elles partagent leur corpus de mesure et leur
critère d'acceptation.

**Les doubles.** Le réglage livré depuis le lot 4.2 laissait **33 régions bi-lobées suspectes
non scindées** sur les cinq volumes du corpus (9 sur manga A Vol.1, 7 sur le Vol.2, 7 sur
manga B Chap.5, 9 sur manga D Vol.15, 1 sur webtoon A Chap.11) — nommées,
avec leur remplissage, dans chaque `RAPPORT.md`. Trois leviers vont les chercher, et le point
commun des trois est qu'ils sont **livrés inactifs** : ils changent le nombre de bulles d'un
tome déjà traité, donc ils se décident, ils ne se subissent pas.

**Le hors bulle.** Trois correctifs sans changement d'interface : l'ordre de lecture qui
ignorait le format, un seuil de composante qui matérialisait chaque tache de trame en masque
pleine page, et un `if` qui avalait une incohérence de forme sans un mot.

Sans modèle, sans corpus, sans E/S : ces tests tournent sur un checkout frais, dans la boucle
courte (`pytest -m "not lent and not llm"`).
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import bubbles_split, geometry, text_detection
from manga.detection import BubbleRegion

TAILLE = (300, 400)          # (largeur, hauteur)


def _ellipse(box, taille=TAILLE) -> np.ndarray:
    m = Image.new("L", taille, 0)
    ImageDraw.Draw(m).ellipse(list(box), fill=255)
    return np.asarray(m) > 127


def _bilobe() -> np.ndarray:
    """Deux ballons en diagonale qui se touchent — la géométrie des pages 136 et 142.

    Le goulot cède à TOUS les échelons d'érosion de 2 à 13 : c'est la signature d'un vrai
    double, et c'est ce que le critère de stabilité vient chercher."""
    return _ellipse((120, 20, 280, 200)) | _ellipse((20, 180, 180, 380))


def _artefact_a_un_seul_k() -> np.ndarray:
    """Un masque qui ne se sépare qu'à **un seul** échelon d'érosion, k = 8.

    Un grand rectangle, un pont de 15 px et un petit carré de 44 px. Le pont cède à k = 8
    (un carré structurant de côté 17 ne tient plus dans 15 px) ; à k = 9 le petit carré est
    déjà passé sous le seuil d'aire des germes, et le masque redevient d'un seul tenant.

    C'est la forme même du faux positif que le lot 13 vient écarter : une séparation qui
    n'existe qu'à un `k`, donc un accident de bruit et non une couture entre deux ballons."""
    m = np.zeros((420, 320), bool)
    m[40:250, 50:260] = True
    m[250:270, 148:163] = True
    m[270:314, 133:177] = True
    return m


def _etoile(cx, cy, r_ext, r_int, pointes=12, taille=(400, 400)) -> np.ndarray:
    """Ballon de CRI : contour en étoile, donc remplissage de boîte bas **par nature**."""
    pts = []
    for i in range(pointes * 2):
        a = math.pi * i / pointes - math.pi / 2
        r = r_ext if i % 2 == 0 else r_int
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    m = Image.new("L", taille, 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return np.asarray(m) > 127


def _deux_cris() -> np.ndarray:
    """Deux ballons de cri accolés. Remplissage du parent ≈ 0,51 — donc chaque lobe est
    largement sous `remplissage_lobe_min` (0,72), et le seuil ABSOLU les condamne."""
    return _etoile(130, 200, 110, 62) | _etoile(275, 200, 110, 62)


def _region(mask, kind="bulle") -> BubbleRegion:
    ys, xs = np.nonzero(mask)
    return BubbleRegion(bbox=(int(xs.min()), int(ys.min()), int(xs.max()) + 1,
                              int(ys.max()) + 1),
                        mask=mask, score=0.9, cls=0, kind=kind)


# Garde-fous de forme volontairement PERMISSIFS : ces tests-là isolent le critère de
# stabilité, et un refus par `min_lobe_frac` ne prouverait rien sur lui.
_PERMISSIF = dict(min_lobe_frac=0.01, remplissage_lobe_min=0.50, aire_min=1000)


# --------------------------------------------------------------------------- #
# L5.1 — exiger la stabilité d'une scission
# --------------------------------------------------------------------------- #

def test_un_vrai_bilobe_est_scinde_dans_les_DEUX_regimes():
    for stabilite in (1, 2, 3, 4):
        lobes = geometry.scinder_par_erosion(_bilobe(), stabilite=stabilite, **_PERMISSIF)
        assert lobes is not None and len(lobes) == 2, stabilite


def test_un_artefact_a_UN_SEUL_k_passe_en_historique_et_est_refuse_en_stable():
    """LE test du lot : c'est exactement la promesse de L5.1, et elle est mesurable ici.

    Le régime historique valide au premier `k` qui sépare et n'a aucun moyen de savoir que ce
    `k` est le seul ; le régime exigeant le voit, parce qu'il regarde l'échelon suivant."""
    artefact = _artefact_a_un_seul_k()
    assert geometry.scinder_par_erosion(artefact, stabilite=1, **_PERMISSIF) is not None
    assert geometry.scinder_par_erosion(artefact, stabilite=2, **_PERMISSIF) is None


def test_le_motif_INSTABLE_est_distinct_de_aucun_goulot():
    """« Instable » et « dentelée » ne disent pas la même chose et ne se traitent pas pareil :
    la première a un goulot qu'on refuse, la seconde n'en a aucun."""
    diag: dict = {}
    geometry.scinder_par_erosion(_artefact_a_un_seul_k(), stabilite=2, diagnostic=diag,
                                 **_PERMISSIF)
    assert diag["motif"] == "scission_instable"
    assert diag["separable"] is True

    diag2: dict = {}
    geometry.scinder_par_erosion(_ellipse((40, 60, 260, 340)), stabilite=2, diagnostic=diag2,
                                 **_PERMISSIF)
    assert diag2["motif"] == "aucun_goulot"
    assert diag2["separable"] is False


def test_le_decoupage_retenu_est_LE_PLUS_DOUX_de_la_serie():
    """Le premier échelon valide de la série, donc l'érosion la plus douce — la plus fidèle
    au masque d'origine. Sur le bi-lobé de référence, la série commence à k = 2."""
    diag: dict = {}
    geometry.scinder_par_erosion(_bilobe(), stabilite=3, diagnostic=diag, **_PERMISSIF)
    assert diag["motif"] == "scindee"
    assert diag["k"] == 2


def test_le_regime_historique_est_le_DEFAUT():
    """Le lot ne doit rien changer tant qu'on n'a rien demandé : `stabilite` vaut 1, et
    l'artefact est donc toujours scindé comme avant."""
    assert geometry.scinder_par_erosion(_artefact_a_un_seul_k(), **_PERMISSIF) is not None


def test_la_scission_reste_une_partition_exacte_en_regime_stable():
    """L'invariant le plus important du module, et il ne dépend pas du régime : l'union des
    lobes vaut le masque, et deux lobes ne partagent aucun pixel. `masks.png` est une image
    d'étiquettes — un pixel partagé serait attribué à la dernière bulle écrite."""
    m = _bilobe()
    lobes = geometry.scinder_par_erosion(m, stabilite=3, **_PERMISSIF)
    union = np.zeros_like(m)
    total = 0
    for lobe in lobes:
        assert not (union & lobe).any()
        union |= lobe
        total += int(lobe.sum())
    assert (union == m).all()
    assert total == int(m.sum())


def test_la_stabilite_se_juge_sur_les_BOITES_et_non_sur_les_indices():
    """`composantes` trie par aire décroissante : deux lobes d'aires voisines peuvent permuter
    d'un échelon au suivant sans que le découpage ait bougé. Une comparaison indice à indice
    romprait la série pour rien."""
    a = [np.zeros((20, 20), bool), np.zeros((20, 20), bool)]
    a[0][2:8, 2:8] = True
    a[1][12:18, 12:18] = True
    b = [a[1].copy(), a[0].copy()]           # les MÊMES lobes, dans l'ordre inverse
    assert geometry._memes_lobes(a, b, 0.80)


def test_un_nombre_de_lobes_different_rompt_la_serie():
    a = [np.zeros((20, 20), bool), np.zeros((20, 20), bool)]
    a[0][2:8, 2:8] = True
    a[1][12:18, 12:18] = True
    assert not geometry._memes_lobes(a, a[:1], 0.80)
    assert not geometry._memes_lobes([], [], 0.80)


# --------------------------------------------------------------------------- #
# L5.2 — l'aire minimale en fraction de planche
# --------------------------------------------------------------------------- #

def _bilobe_a_lechelle(facteur: float) -> np.ndarray:
    """Le même bi-lobé, sur une planche `facteur` fois plus petite. La géométrie relative est
    identique — c'est ce que le seuil devrait voir, et ce qu'en pixels il ne voit pas."""
    taille = (int(TAILLE[0] * facteur), int(TAILLE[1] * facteur))
    b1 = tuple(int(v * facteur) for v in (120, 20, 280, 200))
    b2 = tuple(int(v * facteur) for v in (20, 180, 180, 380))
    return _ellipse(b1, taille) | _ellipse(b2, taille)


def test_le_seuil_EN_PIXELS_ignore_un_double_sur_un_scan_basse_resolution():
    """Le défaut que L5.2 nomme : *manga D* est en 844×1200 et 848×1200. À géométrie
    relative identique, le petit scan passe sous `aire_min` et n'est jamais examiné."""
    grand, petit = _bilobe_a_lechelle(1.0), _bilobe_a_lechelle(0.45)
    assert geometry.scinder_par_erosion(grand, aire_min=10000) is not None
    assert int(petit.sum()) < 10000              # la raison du refus, dite explicitement
    assert geometry.scinder_par_erosion(petit, aire_min=10000) is None


def test_le_seuil_EN_FRACTION_de_planche_voit_les_deux():
    """`aire_min_frac` exprime ce qu'on veut vraiment dire — « assez grande pour qu'un goulot
    soit interprétable » — et ça se mesure relativement à la planche."""
    frac = 10000 / min(TAILLE) ** 2              # iso-comportement sur la grande planche
    for m in (_bilobe_a_lechelle(1.0), _bilobe_a_lechelle(0.45)):
        assert geometry.scinder_par_erosion(m, aire_min_frac=frac) is not None


def test_le_seuil_relatif_se_mesure_sur_le_PETIT_COTE_et_non_sur_l_aire():
    """⚠ Sur un webtoon, « la planche » est une bande d'un chapitre entier — 1080 × 10 000. Une
    fraction d'AIRE y vaudrait 0,0056 × 10,8 Mpx = 60 480 px², six fois le seuil visé : le
    garde-fou deviendrait le plus sévère sur le format où les ballons sont les plus petits.

    Le carré du petit côté rend 9 215 px² et reste juste sur les quatre tailles de planche que
    *manga D* Vol.1 mélange dans un seul tome. C'est le motif de `adaptive_radius`."""
    frac = 10000 / 1125 ** 2                     # iso sur la planche de référence
    # Une bande : même largeur que la planche de référence, dix fois plus haute. Le seuil ne
    # doit PAS suivre la hauteur.
    bande = np.zeros((10000, 1125), bool)
    bande[100:400, 100:400] = True
    bande[380:680, 350:650] = True
    diag: dict = {}
    geometry.scinder_par_erosion(bande, aire_min_frac=frac, diagnostic=diag,
                                 min_lobe_frac=0.01, remplissage_lobe_min=0.50)
    # Le masque pèse ~170 000 px² : très au-dessus des 9 998 px² du seuil au petit côté, très
    # au-dessous des 63 000 px² qu'une fraction d'aire aurait produits.
    assert diag["motif"] != "aire_insuffisante"


def test_une_fraction_nulle_garde_le_seuil_en_pixels():
    """Le défaut livré : `aire_min_frac = 0.0` ne doit rien changer du tout."""
    petit = _bilobe_a_lechelle(0.45)
    assert geometry.scinder_par_erosion(petit, aire_min=10000, aire_min_frac=0.0) is None


# --------------------------------------------------------------------------- #
# L5.3 — la compacité d'un lobe, relative à celle du parent
# --------------------------------------------------------------------------- #

def test_deux_ballons_de_CRI_accoles_echappent_au_seuil_absolu():
    """L'angle mort de `remplissage_lobe_min` : deux ballons de cri ont un remplissage bas par
    NATURE, donc ne sont jamais scindés — et ce sont précisément les bulles où deux
    personnages crient séparément, donc où la fusion se voit le plus."""
    cris = _deux_cris()
    assert geometry.remplissage(cris) < 0.72
    diag: dict = {}
    assert geometry.scinder_par_erosion(cris, aire_min=5000, diagnostic=diag) is None
    assert diag["motif"] == "lobe_trop_creux"     # le goulot existe, la forme l'a refusé


def test_le_seuil_RELATIF_les_scinde_sans_degrader_la_compacite():
    """Le critère devient « la scission ne dégrade pas la compacité » : les lobes rendus sont
    aussi compacts que le parent, ce qui est exactement l'argument."""
    cris = _deux_cris()
    lobes = geometry.scinder_par_erosion(cris, aire_min=5000, stabilite=2,
                                         remplissage_lobe_relatif=0.95)
    assert lobes is not None and len(lobes) == 2
    parent = geometry.remplissage(cris)
    for lobe in lobes:
        assert geometry.remplissage(lobe) >= 0.95 * parent


def test_le_PLANCHER_refuse_un_lobe_franchement_creux():
    """Le plancher est le garde-fou de non-régression de L5.3 : quel que soit le relâchement,
    rien ne passe en dessous. Un parent déjà très creux ne peut donc pas légitimer des lobes
    encore plus creux — sinon assouplir reviendrait à multiplier les lobes à 0,01."""
    cris = _deux_cris()
    assert geometry.scinder_par_erosion(
        cris, aire_min=5000, stabilite=2, remplissage_lobe_relatif=0.95,
        remplissage_lobe_plancher=0.95) is None


def test_le_mode_relatif_est_INACTIF_par_defaut():
    assert geometry.scinder_par_erosion(_deux_cris(), aire_min=5000) is None


# --------------------------------------------------------------------------- #
# L5.4 — les trois valeurs qui étaient réellement en dur
# --------------------------------------------------------------------------- #

def test_les_trois_cles_en_dur_sont_DESORMAIS_dans_les_defauts():
    """Le vrai défaut n'était pas la valeur, c'était le SILENCE : absentes de `_DEFAUTS`,
    `max_lobes`, `germe_frac` et `k_max` écrites dans `config.yaml` étaient ignorées par
    `_cfg` sans un mot (cf. `_config.fusion`, qui filtre par clé connue)."""
    c = bubbles_split._cfg({"max_lobes": 7, "germe_frac": 0.05, "k_max": 12})
    assert (c["max_lobes"], c["germe_frac"], c["k_max"]) == (7, 0.05, 12)


def test_k_max_nul_veut_dire_automatique():
    """0 est la façon d'écrire « laisse le code décider » — le petit côté de la boîte // 3."""
    assert bubbles_split._kwargs(bubbles_split._cfg({"k_max": 0}))["k_max"] is None
    assert bubbles_split._kwargs(bubbles_split._cfg({"k_max": 9}))["k_max"] == 9


def test_max_lobes_TRONQUE_les_germes_et_le_COMPTE():
    """`max_lobes` n'est pas un rejet mais une troncature : une grappe de trois ballons ramenée
    à deux voit les pixels du troisième repartir au lobe le plus proche. Silencieusement,
    jusqu'ici — c'est le comptage qui est le correctif, pas la troncature."""
    grappe = (_ellipse((10, 20, 130, 140)) | _ellipse((120, 130, 250, 250))
              | _ellipse((30, 240, 160, 370)))
    diag: dict = {}
    lobes = geometry.scinder_par_erosion(grappe, max_lobes=2, aire_min=5000,
                                         min_lobe_frac=0.05, remplissage_lobe_min=0.40,
                                         diagnostic=diag)
    assert lobes is not None and len(lobes) == 2
    assert diag["germes_tronques"] >= 1
    # Rien n'est perdu : la partition couvre toujours tout le masque.
    union = np.zeros_like(grappe)
    for lobe in lobes:
        union |= lobe
    assert (union == grappe).all()


def test_sans_troncature_le_compteur_reste_a_zero():
    diag: dict = {}
    geometry.scinder_par_erosion(_bilobe(), max_lobes=4, diagnostic=diag, **_PERMISSIF)
    assert diag["germes_tronques"] == 0


# --------------------------------------------------------------------------- #
# L5.5 — la sonde d'encre
# --------------------------------------------------------------------------- #

def _paire_encree(recouvrement: int = 10, taille=(420, 300)):
    """Deux ballons côte à côte dont les CONTOURS se rejoignent — le cas réel.

    On remplit d'abord les deux, puis on trace les deux contours : c'est ce qui produit la
    double ligne d'encre dans la zone de contact, celle que la sonde vient chercher."""
    boites = ((20, 60, 220, 240), (220 - recouvrement, 60, 420 - recouvrement, 240))
    m = Image.new("L", taille, 0)
    dm = ImageDraw.Draw(m)
    for b in boites:
        dm.ellipse(list(b), fill=255)
    img = Image.new("L", taille, 200)          # fond = le dessin
    di = ImageDraw.Draw(img)
    for b in boites:
        di.ellipse(list(b), fill=250)          # intérieur du ballon
    for b in boites:
        di.ellipse(list(b), outline=0, width=5)
    return np.asarray(m) > 127, np.asarray(img)


def _ballon_seul(taille=TAILLE, barre=False):
    boite = [40, 60, 260, 340]
    m = Image.new("L", taille, 0)
    ImageDraw.Draw(m).ellipse(boite, fill=255)
    img = Image.new("L", taille, 200)
    d = ImageDraw.Draw(img)
    d.ellipse(boite, fill=250, outline=0, width=5)
    if barre:
        d.line([(45, 200), (255, 200)], fill=0, width=6)
    return np.asarray(m) > 127, np.asarray(img)


def test_la_couture_dun_VRAI_double_est_encree():
    masque, gris = _paire_encree()
    lobes = geometry.scinder_par_erosion(masque, aire_min=5000, min_lobe_frac=0.05,
                                         remplissage_lobe_min=0.50)
    assert lobes is not None
    assert bubbles_split.part_dencre(gris, masque, lobes) >= 0.60


def test_une_coupe_ARBITRAIRE_dans_le_blanc_nest_pas_encree():
    """Le discriminant, dans l'autre sens : trancher un ballon unique en deux fait passer la
    couture par son intérieur blanc, et la sonde le dit."""
    masque, gris = _ballon_seul()
    haut, bas = masque.copy(), masque.copy()
    haut[200:, :] = False
    bas[:200, :] = False
    assert bubbles_split.part_dencre(gris, masque, [haut, bas]) < 0.20


def test_le_seuil_dencre_est_RELATIF_a_la_region():
    """Une bulle INVERSÉE — blanc sur noir — existe dans le corpus. Un seuil en valeur absolue
    y déclarerait tout le fond « encre »."""
    masque, gris = _ballon_seul()
    seuil = bubbles_split.seuil_encre(gris, masque)
    assert 0 < seuil < 250
    assert bubbles_split.seuil_encre(255 - gris, masque) < 250


def test_un_TRAIT_TRAVERSANT_sans_goulot_est_detecte():
    _m_sain, gris_sain = _ballon_seul()
    masque, gris_barre = _ballon_seul(barre=True)
    assert bubbles_split.trait_traversant(gris_barre, masque)
    assert not bubbles_split.trait_traversant(gris_sain, masque)


def test_un_trait_sans_goulot_est_SIGNALE_jamais_scinde():
    """Le principe directeur du projet : l'outil ne décide pas à la place de l'humain quand il
    n'est pas sûr. Une cloison d'encre sans goulot d'érosion part au rapport, pas au découpage."""
    masque, gris = _ballon_seul(barre=True)
    # `seuil_suspect` haut : le signalement suit le MÊME chemin que les autres diagnostics de
    # forme, donc la région doit d'abord tomber dans la bande « remplissage bas ». Un ballon
    # bien rempli n'est de toute façon jamais examiné (`seuil_remplissage`).
    cfg = {"aire_min": 5000, "seuil_suspect": 0.99, "encre": {"actif": True}}
    sorties, diag = bubbles_split.scinder_regions([_region(masque)], cfg, gris)
    assert len(sorties) == 1                        # rien n'a été scindé
    assert diag and diag[0]["type"] == "dentelee"
    assert diag[0].get("trait_sans_goulot") is True


def test_la_sonde_ne_retient_que_ce_que_lEROSION_a_deja_propose():
    """« En appui et jamais en remplacement » : la sonde relâche le garde-fou de forme sur un
    découpage existant, elle n'en invente aucun. Sans goulot, elle ne peut rien scinder."""
    masque, gris = _ballon_seul(barre=True)
    cfg = {"aire_min": 5000, "encre": {"actif": True, "part_min": 0.0}}
    sorties, _diag = bubbles_split.scinder_regions([_region(masque)], cfg, gris)
    assert len(sorties) == 1


def test_la_sonde_est_INACTIVE_sans_image():
    """`checkpoints.migrate_page` scinde des masques en cache sans jamais ouvrir la planche —
    c'est ce qui permet de migrer un tome sans le modèle ONNX. La sonde doit s'effacer."""
    masque, _gris = _paire_encree()
    cfg = {"aire_min": 5000, "encre": {"actif": True}}
    sorties, _diag = bubbles_split.scinder_regions([_region(masque)], cfg, None)
    assert len(sorties) >= 1                        # aucune exception, aucun accès à l'image


def test_la_sonde_est_INACTIVE_par_defaut():
    assert bubbles_split._cfg(None)["encre"]["actif"] is False


def test_un_encre_partiel_ne_fait_pas_disparaitre_les_autres_defauts():
    """`_config.fusion` est PLATE : un sous-bloc partiel écrit dans `config.yaml` remplacerait
    tout `encre` et emporterait les clés non écrites. D'où la seconde fusion."""
    c = bubbles_split._cfg({"encre": {"actif": True}})
    assert c["encre"]["actif"] is True
    assert c["encre"]["part_min"] == bubbles_split._ENCRE_DEFAUTS["part_min"]


# --------------------------------------------------------------------------- #
# L5.6 — la composante minimale, et ce qu'elle filtre VRAIMENT
# --------------------------------------------------------------------------- #

def _masque_texte(*rects, taille=(400, 600)) -> np.ndarray:
    m = np.zeros(taille, bool)
    for x0, y0, x1, y1 in rects:
        m[y0:y1, x0:x1] = True
    return m


def test_min_composante_par_defaut_ne_change_rien():
    m = _masque_texte((50, 50, 130, 130), (250, 300, 330, 380))
    a = text_detection.hors_des_bulles(m, [])
    b = text_detection.hors_des_bulles(m, [], min_composante=1)
    assert [r.bbox for r in a] == [r.bbox for r in b]
    assert text_detection.MIN_COMPOSANTE == 1


def test_min_composante_sapplique_aux_composantes_DILATEES():
    """⚠ Le point que la mesure a corrigé, et il n'est pas intuitif. Le seuil s'applique APRÈS
    la dilatation de groupement (~9 px sur une planche de 1125 px de large), pas au masque
    d'encre. La plus petite composante mesurée sur une planche synthétique réaliste pèse déjà
    **240 px²** : tout seuil en dessous est inerte.

    C'est ce qui disqualifie `min_composante` comme levier de coût — il faudrait le monter au
    niveau d'`aire_min`, c'est-à-dire dans la zone où il change le résultat."""
    m = _masque_texte((50, 50, 120, 120))
    zones_basses = text_detection.hors_des_bulles(m, [], min_composante=100)
    zones_hautes = text_detection.hors_des_bulles(m, [], min_composante=1)
    assert [r.bbox for r in zones_basses] == [r.bbox for r in zones_hautes]


def test_la_fusion_ne_MUTE_pas_les_composantes_recues():
    """`fusionner_proches` accumule en place (`|=`) depuis le lot 13, pour cesser d'allouer un
    masque pleine page par membre de groupe. La copie initiale est ce qui empêche le premier
    `|=` d'écrire dans le tableau de l'appelant — sans elle, le bogue serait silencieux et se
    manifesterait des étapes plus loin."""
    a = np.zeros((60, 60), bool)
    a[10:20, 10:20] = True
    b = np.zeros((60, 60), bool)
    b[10:20, 22:32] = True
    avant = a.copy()
    fusion = text_detection.fusionner_proches([a, b], facteur=5.0)
    assert len(fusion) == 1
    assert (a == avant).all(), "l'entrée a été mutée"


def test_la_fusion_preserve_tous_les_pixels():
    a = np.zeros((60, 60), bool)
    a[10:20, 10:20] = True
    b = np.zeros((60, 60), bool)
    b[10:20, 22:32] = True
    fusion = text_detection.fusionner_proches([a, b], facteur=5.0)
    assert int(fusion[0].sum()) == int(a.sum()) + int(b.sum())


# --------------------------------------------------------------------------- #
# L5.7 — l'ordre de lecture des zones hors bulle suit le FORMAT
# --------------------------------------------------------------------------- #

def test_le_defaut_reste_lordre_MANGA():
    """Droite → gauche : rien ne change pour les tomes paginés déjà traités."""
    m = _masque_texte((30, 30, 110, 110), (280, 30, 360, 110))
    zones = text_detection.hors_des_bulles(m, [])
    assert [r.bbox[0] for r in zones] == [280, 30]


def test_le_sens_du_format_ordonne_les_zones_hors_bulle():
    """⚠ C'était le SEUL endroit du pipeline à ignorer le sens de lecture du format. Sur un
    webtoon, les bulles étaient ordonnées correctement par `ocr.reading_order` et les
    onomatopées numérotées à l'envers — le rapport comme le prompt de `_translate_sfx` les
    présentaient dans un ordre qui ne correspondait à rien."""
    m = _masque_texte((30, 30, 110, 110), (280, 30, 360, 110))
    zones = text_detection.hors_des_bulles(m, [], sens="gauche_droite")
    assert [r.bbox[0] for r in zones] == [30, 280]


def test_les_zones_passent_par_LA_MEME_fonction_que_les_bulles():
    """Entretenir deux ordres de lecture dans le même pipeline est la dette qui a produit
    `tools/verifier_ordre.py`. La coupe X-Y de `ocr.reading_order` fait de plus mieux qu'un
    tri par abscisse : deux zones de deux cases distinctes ne s'entrelacent plus."""
    from manga import ocr as ocr_mod
    m = _masque_texte((30, 30, 110, 110), (280, 30, 360, 110), (30, 300, 110, 380))
    zones = text_detection.hors_des_bulles(m, [], sens="gauche_droite")
    attendu = ocr_mod.reading_order(list(zones), "gauche_droite")
    assert [r.bbox for r in zones] == [r.bbox for r in attendu]


# --------------------------------------------------------------------------- #
# L5.8 — `_union_bulles` n'avale plus une incohérence de forme
# --------------------------------------------------------------------------- #

def _bulle(x0, y0, x1, y1, forme=(600, 400)) -> BubbleRegion:
    m = np.zeros(forme, bool)
    m[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=m, score=0.9, cls=0, kind="bulle")


def test_un_masque_de_forme_INATTENDUE_est_compte_et_decrit():
    """Aucun `warn`, aucun compteur, aucun diagnostic : la fonction ne rendait que l'union.
    Et la cascade est brutale — l'union sort vide, et toutes les répliques déjà prises en
    charge par une bulle sont re-détectées comme texte hors bulle, relues et retraduites."""
    bonne = _bulle(10, 10, 60, 60)
    mauvaise = BubbleRegion(bbox=(0, 0, 5, 5), mask=np.zeros((123, 45), bool),
                            score=0.9, cls=0, kind="bulle")
    diag: dict = {}
    union = text_detection._union_bulles([bonne, mauvaise], (600, 400), diag)
    assert union.any()                                   # la bonne compte toujours
    assert diag["masques_ecartes"] == 1
    assert "(123, 45)" in diag["formes"][0] and "(600, 400)" in diag["formes"][0]


def test_sans_masque_incoherent_le_diagnostic_reste_vide():
    diag: dict = {}
    text_detection._union_bulles([_bulle(10, 10, 60, 60)], (600, 400), diag)
    assert diag == {}


def test_le_diagnostic_est_OPTIONNEL_et_le_comportement_inchange():
    """Le motif de `scinder_par_erosion` : les appelants qui ne veulent rien savoir n'ont rien
    à changer."""
    mauvaise = BubbleRegion(bbox=(0, 0, 5, 5), mask=np.zeros((7, 7), bool),
                            score=0.9, cls=0, kind="bulle")
    union = text_detection._union_bulles([_bulle(10, 10, 60, 60), mauvaise], (600, 400))
    assert int(union.sum()) == 50 * 50


def test_une_bulle_sans_masque_nest_pas_comptee_comme_incoherente():
    """`mask=None` est un cas normal (une région reconstruite sans masque), pas une
    incohérence de forme. Les confondre noierait le signal qu'on vient d'ajouter."""
    sans = BubbleRegion(bbox=(0, 0, 5, 5), mask=None, score=0.9, cls=0, kind="bulle")
    diag: dict = {}
    text_detection._union_bulles([_bulle(10, 10, 60, 60), sans], (600, 400), diag)
    assert diag == {}


# --------------------------------------------------------------------------- #
# Bout en bout — le classement du rapport
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("stabilite,attendu", [(1, "suspecte"), (2, "instable")])
def test_classer_non_scindees_distingue_les_TROIS_familles(stabilite, attendu):
    """Le rapport range désormais en trois : « dentelée » (aucun goulot), « instable » (un
    goulot qui ne tient pas) et « suspecte » (un goulot stable, refusé). Seule la dernière
    demande qu'on aille voir la planche."""
    artefact = _artefact_a_un_seul_k()
    cfg = {"aire_min": 1000, "min_lobe_frac": 0.01, "remplissage_lobe_min": 0.99,
           "seuil_suspect": 0.99, "stabilite": stabilite}
    formes = bubbles_split.classer_non_scindees([_region(artefact)], cfg)
    assert formes == {0: attendu}


def test_une_bulle_unique_reste_DENTELEE_dans_les_deux_regimes():
    ballon = _ellipse((40, 60, 260, 340))
    for stabilite in (1, 2):
        formes = bubbles_split.classer_non_scindees(
            [_region(ballon)], {"seuil_suspect": 0.99, "stabilite": stabilite})
        assert formes == {0: "dentelee"}
