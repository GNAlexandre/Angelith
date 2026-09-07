# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Escalade de détection — « plus aucune planche muette » (lot 12, L4.2).

## Le constat, mesuré sur dix volumes

**188 planches sur 1 513 rendent zéro bulle** (12,4 %), dont **183 portent de l'encre** : des
pages entièrement non traduites. `RAPPORT.md` les comptait déjà, et les triait déjà — ce qui
manquait n'était pas la mesure, c'était **l'escalade** : rien ne réagissait.

La machinerie de réparation existait pourtant et était calibrée (`manga/detection_retry.py`,
quatre vétos ordonnés, lot 4.2). Elle avait **un seul site d'appel** — `--conf`/`--iou` en
ligne de commande, avec `--page` obligatoire — et `len(regions) == 0` ne déclenchait rien du
tout : un `regions.json` vide s'écrivait en silence, et comme `len(regions) != len(reference)`
était faux (0 == 0), l'invalidation des textes en aval n'avait même pas lieu.

Ces tests portent sur les DÉCIDEURS — les réglages par défaut, les déclencheurs, l'arbitre —
et non sur la boucle de l'orchestrateur : aucun modèle n'est chargé.
"""
import numpy as np
from PIL import Image, ImageDraw

from manga import detection, detection_retry
from manga.orchestrator_manga import DEFAUTS_ESCALADE
from manga._config import fusion


# --------------------------------------------------------------------------- #
# Les réglages livrés
# --------------------------------------------------------------------------- #

def test_lescalade_est_LIVREE_ACTIVE():
    """C'est ce que le lot est venu faire. Elle coûte une inférence de plus sur les planches
    suspectes SEULEMENT — mesuré à 5,5 s par planche suspecte, 1 002 s pour les 183 planches
    des dix volumes — et la détection n'est pas l'étape chère d'un tome (manga A Vol.2 :
    46 min 56 s pour 150 planches). Ce qu'elle rapporte : 188 → 153 planches à zéro bulle."""
    assert DEFAUTS_ESCALADE["actif"] is True


def test_le_vrai_levier_est_la_RESOLUTION_pas_le_seuil():
    """Baisser `conf` ne fait qu'accepter ce que le réseau émettait déjà. Mesuré sur le
    webtoon : descendre jusqu'à 0,10 ne gagnait AUCUNE bulle, « parce que le réseau ne les émet
    pas du tout ». Relever `input_size` change ce que le réseau PEUT voir."""
    assert DEFAUTS_ESCALADE["input_size"] > detection.INPUT_SIZE
    assert DEFAUTS_ESCALADE["input_size"] % detection.STRIDE == 0
    assert DEFAUTS_ESCALADE["conf_threshold"] < detection.CONF_THRESHOLD


def test_desactiver_lescalade_rend_le_comportement_DAVANT():
    cfg = fusion(DEFAUTS_ESCALADE, {"actif": False})
    assert cfg["actif"] is False
    # …et les autres réglages restent lisibles : on désarme, on n'efface pas.
    assert cfg["input_size"] == DEFAUTS_ESCALADE["input_size"]


def test_la_mediane_ne_sarme_pas_sur_un_echantillon_DERISOIRE():
    """Sans cette borne, la planche 2 d'un tome déciderait à elle seule de la médiane du tome."""
    assert DEFAUTS_ESCALADE["mediane_echantillon_min"] >= 10


def test_les_motifs_descalade_ont_tous_un_libelle():
    assert set(detection_retry.MOTIFS_ESCALADE) == {"zero_bulle_encree", "sous_la_mediane"}
    assert all(isinstance(v, str) and v for v in detection_retry.MOTIFS_ESCALADE.values())


# --------------------------------------------------------------------------- #
# Déclencheur 1 : zéro bulle sur une planche qui porte de l'encre
# --------------------------------------------------------------------------- #

def _planche(dessinee: bool):
    img = Image.new("RGB", (844, 1200), "white")
    if dessinee:
        ImageDraw.Draw(img).rectangle([80, 80, 760, 1000], outline="black", width=8)
    return img


def test_une_planche_BLANCHE_a_zero_bulle_nest_pas_suspecte():
    """Une page de garde ou un séparateur n'a rien à traduire : escalader dessus paierait une
    inférence pour rien, sur chaque tome et à chaque relance."""
    seuil = float(DEFAUTS_ESCALADE["seuil_encre"])
    assert detection.porte_de_l_encre(_planche(False), seuil=seuil) is False


def test_une_planche_DESSINEE_a_zero_bulle_est_suspecte():
    seuil = float(DEFAUTS_ESCALADE["seuil_encre"])
    assert detection.porte_de_l_encre(_planche(True), seuil=seuil) is True


def test_le_declencheur_ne_depend_PAS_de_la_passe_onomatopees():
    """Le seul discriminant qui existait était `bool(qa["sfx"])` — indisponible quand la passe
    est inactive. Les trois volumes de *manga D* du corpus n'ont **aucun** `sfx.json` :
    leurs 72 planches à zéro bulle n'étaient triées du tout.

    Le test d'encre vit dans `manga.detection`, qui ne charge aucun second modèle."""
    import inspect
    source = inspect.getsource(detection.porte_de_l_encre) + inspect.getsource(
        detection.part_encre) + inspect.getsource(detection._luminance)
    assert "sfx" not in source and "onomatop" not in source.lower()


# --------------------------------------------------------------------------- #
# L'arbitre, sur le régime qui décide de tout
# --------------------------------------------------------------------------- #

TAILLE = (400, 400)


def _region(x0, y0, x1, y1, score=0.9):
    m = np.zeros(TAILLE, dtype=bool)
    m[y0:y1, x0:x1] = True
    return detection.BubbleRegion(bbox=(x0, y0, x1, y1), mask=m, score=score, cls=0)


def test_une_escalade_sur_planche_MUETTE_rend_les_bulles_nettoyables():
    """Le cas nominal du lot : la planche n'avait rien, l'escalade trouve deux ballons propres
    et un bout de trame. Les deux ballons partent, la trame reste dehors."""
    ballons = [_region(10, 10, 100, 100), _region(200, 10, 290, 100)]
    trame = _region(10, 200, 40, 230)
    candidates = [*ballons, trame]
    verdict = detection_retry.arbitrer([], candidates, {0: 0.92, 1: 0.88, 2: 0.14})
    assert verdict.accepte
    assert verdict.retenir(candidates) == ballons


def test_une_escalade_qui_ne_trouve_QUE_du_dessin_est_refusee():
    """« Une bulle nettoyable est une bulle ; une bulle qu'on ne sait pas peindre est
    probablement du décor. » C'est la règle centrale du module, et sur une planche où l'on
    vient d'abaisser les seuils c'est le seul rempart calibré dont on dispose."""
    candidates = [_region(10, 10, 60, 60), _region(200, 200, 250, 250)]
    verdict = detection_retry.arbitrer([], candidates, {0: 0.12, 1: 0.20})
    assert not verdict.accepte and verdict.motif == "aucune_nettoyable"
    assert verdict.retenir(candidates) == []


def test_une_escalade_ne_DEGRADE_jamais_une_planche_qui_allait_bien():
    """La seconde moitié du critère d'acceptation du lot, et celle que l'arbitre garantit : une
    escalade qui ferait disparaître une bulle déjà détectée est refusée, et la détection en
    place est conservée telle quelle."""
    en_place = [_region(10, 10, 100, 100), _region(200, 10, 290, 100)]
    # L'escalade ne retrouve que la première, plus une nouvelle ailleurs.
    candidates = [en_place[0], _region(10, 200, 100, 290)]
    verdict = detection_retry.arbitrer(en_place, candidates, {0: 0.9, 1: 0.9},
                                       uniformites_reference={0: 0.9, 1: 0.9})
    assert not verdict.accepte and verdict.motif == "bulle_perdue"


def test_une_escalade_qui_EXPLOSE_est_un_effondrement_de_seuil():
    """Un doublement du nombre de bulles n'est pas une amélioration de détection."""
    en_place = [_region(10, 10, 100, 100)]
    candidates = [en_place[0], _region(120, 10, 200, 100), _region(220, 10, 300, 100),
                  _region(10, 120, 100, 200)]
    verdict = detection_retry.arbitrer(en_place, candidates,
                                       {i: 0.9 for i in range(4)},
                                       uniformites_reference={0: 0.9})
    assert not verdict.accepte and verdict.motif == "explosion"


def test_le_verdict_reste_LISIBLE_pour_le_rapport():
    """`RAPPORT.md` publie la ligne d'escalade telle quelle : planche, réglage, verdict, bulles
    gagnées. Un verdict illisible y devient une ligne inutile."""
    candidates = [_region(10, 10, 100, 100)]
    texte = str(detection_retry.arbitrer([], candidates, {0: 0.9}))
    assert "ACCEPTÉ" in texte and "n'en avait aucune" in texte
