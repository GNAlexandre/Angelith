# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Résolution d'entrée du réseau, aire minimale et rejets comptés — lot 12 (L4.3, L4.1).

`INPUT_SIZE` était une constante de module que RIEN ne remontait : ni paramètre de
`BubbleDetector.__init__`, ni clé de config, alors même que les poids téléchargés
(`model_dynamic.onnx`) sont un export à axes dynamiques qui accepte n'importe quelle
résolution. Le seul levier proposé contre les bulles ratées était donc le découpage en
fenêtres — ×9 en temps d'inférence, et sur une seule classe d'images.

Aucun de ces tests ne charge de modèle : ils portent sur la fabrique, le post-traitement et la
fusion inter-fenêtres, tous testables en numpy pur.
"""
import numpy as np
import pytest

from manga import detection
from manga.detection import BubbleRegion


# --------------------------------------------------------------------------- #
# `input_size` : normalisation et vérification de l'axe dynamique
# --------------------------------------------------------------------------- #

def test_le_defaut_est_640_et_ne_bouge_pas():
    """LE critère du lot : le comportement livré ne change pas d'un pixel. C'est ce qui rend
    l'étape sans risque, et c'est ce qui permet à un tome relancé sans toucher la config de
    produire un `regions.json` identique au bit."""
    assert detection.INPUT_SIZE == 640
    assert detection.normaliser_input_size(detection.INPUT_SIZE) == 640


def test_une_taille_hors_stride_est_ARRONDIE_et_annoncee():
    """On arrondit plutôt que d'échouer : `input_size: 1000` est une intention parfaitement
    claire, et refuser un tome de 150 planches pour 24 px ne protégerait personne. Mais on le
    DIT — un réglage silencieusement remplacé est un réglage qu'on croit avoir posé."""
    dits = []
    assert detection.normaliser_input_size(1000, dire=dits.append) == 992
    assert len(dits) == 1 and "992" in dits[0] and "input_size" in dits[0]
    # …et une taille déjà alignée ne dit rien du tout.
    dits.clear()
    assert detection.normaliser_input_size(1024, dire=dits.append) == 1024
    assert dits == []


def test_une_taille_absurde_est_REFUSEE():
    with pytest.raises(ValueError, match="input_size"):
        detection.normaliser_input_size(16)


def test_un_modele_a_axes_DYNAMIQUES_accepte_toute_resolution():
    """C'est la forme du modèle que ce projet télécharge, vérifiée sur le fichier livré :
    `['batch', 3, 'height', 'width']`."""
    detection.verifier_axe_dynamique(["batch", 3, "height", "width"], 1024, "m.onnx")


def test_un_modele_a_axes_FIGES_le_dit_CLAIREMENT():
    """Sans cette garde, ONNX Runtime refuse à la première planche sur une erreur d'algèbre de
    tenseurs qui ne nomme ni la clé de config fautive ni le fichier de poids. C'est le motif
    de `manga/models.py` : un message qui dit quoi faire."""
    with pytest.raises(SystemExit) as e:
        detection.verifier_axe_dynamique([1, 3, 640, 640], 1024, "m.onnx")
    message = str(e.value)
    assert "input_size" in message and "640" in message and "m.onnx" in message


def test_un_axe_fige_a_la_BONNE_valeur_nest_pas_une_erreur():
    """Le cas nominal d'un utilisateur qui a figé son export à 640 et n'a rien changé."""
    detection.verifier_axe_dynamique([1, 3, 640, 640], 640, "m.onnx")


def test_linference_PORTE_sa_resolution():
    """`regions_de` doit pouvoir post-traiter une inférence faite à une AUTRE résolution que
    celle du tome — c'est exactement ce que fait l'escalade, qui relance une planche suspecte à
    1024 sans toucher aux réglages des 149 autres."""
    champs = detection.Inference.__dataclass_fields__
    assert "size" in champs
    assert champs["size"].default == detection.INPUT_SIZE


# --------------------------------------------------------------------------- #
# `aire_min_frac` et les rejets comptés
# --------------------------------------------------------------------------- #

def test_tous_les_motifs_de_rejet_ont_un_libelle():
    """Un motif sans libellé sort tel quel dans `RAPPORT.md` : `masque_vide` au lieu de
    « masque vide après recadrage sur la boîte »."""
    assert set(detection.MOTIFS_REJET) == {
        "boite_degeneree", "aire_min", "masque_vide", "couture"}
    assert all(isinstance(v, str) and v for v in detection.MOTIFS_REJET.values())


def test_laire_minimale_est_une_FRACTION_et_non_des_pixels():
    """Le projet a déjà appris cette leçon deux fois (`geometry.adaptive_radius`,
    `text_detection.GROUPEMENT_FRAC`) et ne l'avait pas appliquée ici. Les deux seuils restés
    en pixels absolus sont exactement ceux qui cassent sur les scans 844×1200."""
    assert detection.AIRE_MIN_FRAC == 0.0        # défaut = aucun filtre, iso-comportement
    petite, grande = (400, 600), (2000, 3000)
    # 1 % de la planche : la même boîte de 100×100 passe sur la petite et tombe sur la grande.
    frac = 0.01
    assert 100 * 100 >= frac * petite[0] * petite[1]
    assert 100 * 100 < frac * grande[0] * grande[1]


def test_le_compteur_de_rejets_est_CUMULATIF():
    """Passé par l'appelant plutôt que renvoyé : `tools/apercu_detection.py --balayage` appelle
    le post-traitement douze fois de suite et veut le cumul, l'orchestrateur en passe un neuf
    par planche."""
    rejets: dict = {}
    detection._compter(rejets, "aire_min")
    detection._compter(rejets, "aire_min")
    detection._compter(rejets, "masque_vide")
    assert rejets == {"aire_min": 2, "masque_vide": 1}
    detection._compter(None, "aire_min")         # `None` = l'appelant ne compte pas


# --------------------------------------------------------------------------- #
# Coutures : containment de masques, pas IoU de boîtes (L4.5)
# --------------------------------------------------------------------------- #

TAILLE = (4000, 1080)


def _bulle(y0, y1, x0=200, x1=800):
    m = np.zeros(TAILLE, dtype=bool)
    m[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=m, score=0.9, cls=0)


def test_une_TRONQUEE_est_ecartee_quand_sa_version_ENTIERE_est_la():
    """Le cas mesuré, avec les défauts livrés (`fenetre_hauteur: 2160`,
    `fenetre_recouvrement: 900`) : une bulle de 500 px à y ∈ [2000, 2500] est vue tronquée par
    la fenêtre [0, 2160) — 160 px — et entière par [1260, 3420). Leur IoU vaut 160/500 = 0,32,
    donc SOUS le seuil de 0,45 : les deux étaient conservées.

    La tronquée passait ensuite dans `rendre_disjoints`, en ressortait en sliver, et produisait
    une bulle vide de plus, un OCR de plus, et **une réplique numérotée de plus attendue du
    LLM** — donc un décalage de numérotation sur toute la planche."""
    entiere = _bulle(2000, 2500)
    tronquee = _bulle(2000, 2160)
    assert detection._iou_bbox(tronquee.bbox, entiere.bbox) == pytest.approx(0.32, abs=0.01)
    rejets: dict = {}
    gardees = detection.fusionner_fenetres(
        [(entiere, False), (tronquee, True)], 0.45, rejets=rejets)
    assert len(gardees) == 1 and gardees[0].bbox == entiere.bbox
    assert rejets == {"couture": 1}


def test_le_SEUIL_DIOU_nest_pas_touche():
    """`iou_threshold` est le MÊME paramètre que le NMS intra-fenêtre : le déplacer pour
    réparer la couture le déplacerait aussi là où il ne décrit pas la même chose. Le critère de
    containment n'y touche pas — la preuve, il marche au seuil livré."""
    gardees = detection.fusionner_fenetres(
        [(_bulle(2000, 2500), False), (_bulle(2000, 2160), True)],
        detection.IOU_THRESHOLD)
    assert len(gardees) == 1


def test_une_coupee_SANS_version_entiere_est_CONSERVEE():
    """La doctrine du module reste intacte : on ne jette jamais purement et simplement une
    détection coupée. Une bulle plus haute que le recouvrement serait tronquée dans TOUTES les
    fenêtres, et la jeter partout la ferait disparaître — mieux vaut une bulle tronquée, que
    l'éditeur peut retailler, qu'une bulle absente que personne ne voit."""
    seule = _bulle(2000, 2160)
    lointaine = _bulle(100, 600)
    gardees = detection.fusionner_fenetres([(lointaine, False), (seule, True)], 0.45)
    assert len(gardees) == 2


def test_une_coupee_nen_evince_jamais_une_autre():
    """Le tri place toutes les entières avant les coupées ; le critère ne s'applique qu'à une
    entière retenue. Deux tronçons d'une même bulle trop haute pour le recouvrement doivent
    donc survivre tous les deux."""
    haut, bas = _bulle(1000, 2160), _bulle(1260, 2400)
    gardees = detection.fusionner_fenetres([(haut, True), (bas, True)], 0.99)
    assert len(gardees) == 2
