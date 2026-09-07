# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La STRUCTURE d'une planche : groupes, types de bulle, étiquettes de locuteur (lot 15).

Trois ajouts au prompt du traducteur, et **une seule règle** qui les gouverne tous les
trois : *ne rien affirmer qu'on ne sache*. Un groupe faux fait continuer une phrase par-dessus
un changement de plan ; un type faux fait écrire un cri comme un récitatif ; une étiquette de
locuteur fausse fait tutoyer un inconnu. L'annotation ABSENTE vaut mieux que l'annotation
fausse — le modèle sait travailler sans, c'est ce qu'il faisait avant ce lot.

Ces tests portent donc autant sur ce que le module REFUSE de dire que sur ce qu'il dit.

Aucun modèle, aucun appel LLM : de la géométrie sur des masques dessinés à la main.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from manga import consignes, geometry, planche
from manga.detection import BubbleRegion

TAILLE = (600, 900)


def _region(dessin, bbox) -> BubbleRegion:
    m = Image.new("L", TAILLE, 0)
    dessin(ImageDraw.Draw(m))
    return BubbleRegion(bbox=tuple(bbox), mask=np.asarray(m) > 127, score=0.9, cls=0)


def _ovale(bbox) -> BubbleRegion:
    return _region(lambda d: d.ellipse(list(bbox), fill=255), bbox)


def _ovale_a_queue(bbox, pointe) -> BubbleRegion:
    """Un ballon ordinaire, muni d'une queue qui pointe vers `pointe`."""
    x0, y0, x1, y1 = bbox
    base = ((x0 + x1) // 2, y1 - 4)

    def dessin(d):
        d.ellipse([x0, y0, x1, y1], fill=255)
        d.polygon([(base[0] - 14, base[1]), (base[0] + 14, base[1]), pointe], fill=255)

    boite = (min(x0, pointe[0]), min(y0, pointe[1]),
             max(x1, pointe[0]), max(y1, pointe[1]))
    return _region(dessin, boite)


# --------------------------------------------------------------------------- #
# La queue — le signal que `width_profile` calculait pour le JETER
# --------------------------------------------------------------------------- #

def test_la_queue_est_extraite_et_sa_direction_lue():
    """`geometry.width_profile` documente qu'il exclut la queue « qui pointe vers le
    locuteur » : le pipeline la calculait donc, pour s'en débarrasser. On la garde."""
    region = _ovale_a_queue((150, 100, 450, 260), (300, 380))

    profil = geometry.profil_de_forme(region.mask)

    assert profil.queue is not None
    # Repère IMAGE, y vers le bas : une queue qui descend fait +90°.
    assert 70 <= math.degrees(profil.queue.angle) <= 110
    assert profil.queue.pointe[1] > 300


def test_une_bulle_sans_queue_n_en_invente_pas():
    assert geometry.profil_de_forme(_ovale((150, 100, 450, 260)).mask).queue is None


def test_deux_appendices_rivaux_ne_donnent_aucune_queue():
    """Un ballon festonné ou en étoile porte plusieurs appendices comparables. En désigner un
    comme « la » queue reviendrait à tirer au sort la direction du locuteur — et une direction
    fausse est pire qu'aucune direction."""
    def dessin(d):
        d.ellipse([150, 150, 450, 310], fill=255)
        d.polygon([(286, 300), (314, 300), (300, 420)], fill=255)
        d.polygon([(286, 160), (314, 160), (300, 40)], fill=255)

    assert geometry.profil_de_forme(_region(dessin, (150, 40, 450, 420)).mask).queue is None


# --------------------------------------------------------------------------- #
# Les groupes — la gouttière, jamais la « case »
# --------------------------------------------------------------------------- #

def test_une_gouttiere_franche_ouvre_un_groupe():
    """Deux bulles côte à côte en haut, une isolée 400 px plus bas : deux groupes."""
    regions = [_ovale((320, 40, 560, 180)), _ovale((60, 40, 300, 180)),
               _ovale((60, 620, 300, 760))]

    s = planche.analyser(regions, TAILLE)

    assert s.n_groupes == 2
    assert s.groupes[0] == s.groupes[1] < s.groupes[2]


def test_deux_bulles_voisines_restent_dans_le_meme_groupe():
    """L'espace entre deux répliques d'un même plan n'est pas une rupture de mise en page.
    Sans ce garde-fou, chaque bulle deviendrait son propre « groupe » et l'annotation
    n'apprendrait plus rien."""
    regions = [_ovale((60, 40, 540, 180)), _ovale((60, 200, 540, 340))]

    assert planche.analyser(regions, TAILLE).n_groupes == 1


def test_l_enonce_parle_de_groupes_et_jamais_de_cases():
    """`ocr._coupe_xy` ne détecte AUCUNE case : il coupe des gouttières, et sa docstring le
    dit. Annoncer des cases ferait inférer au modèle une précision qui n'existe pas.

    Deux exigences, et il faut les deux : le mot ne doit pas apparaître dans les LIGNES —
    c'est là que le modèle lit une affirmation — et la note de lecture doit dire
    explicitement que ce n'en sont pas, plutôt que de laisser le silence répondre."""
    s = planche.Structure(groupes=[1, 2], types=[planche.INDETERMINE] * 2, locuteurs=["", ""])

    lignes = " ".join(planche.lignes_bulles(["a", "b"], s))

    assert "case" not in lignes.lower()
    assert "Groupe" in lignes
    assert "ne sont pas des cases" in consignes.STRUCTURE_NOTE


def test_des_groupes_non_croissants_ne_sont_pas_annonces():
    """Un cache trié sous un autre sens de lecture (cf. `tools/verifier_ordre.py`) ferait
    revenir les numéros en arrière, donc afficher deux fois « — Groupe 1 — ». On préfère ne
    rien annoncer : une structure fausse présentée comme un fait est le seul vrai risque."""
    s = planche.Structure(groupes=[2, 1], types=[planche.INDETERMINE] * 2, locuteurs=["", ""])

    assert planche.lignes_bulles(["a", "b"], s) == ["1. a", "2. b"]


# --------------------------------------------------------------------------- #
# Les types — et surtout l'« indéterminé »
# --------------------------------------------------------------------------- #

def test_un_rectangle_plein_sans_queue_est_un_recitatif():
    region = _region(lambda d: d.rectangle([80, 100, 520, 300], fill=255), (80, 100, 520, 300))

    assert planche.classer(geometry.profil_de_forme(region.mask)) == planche.RECITATIF


def test_une_bulle_a_queue_et_contour_lisse_est_un_dialogue():
    region = _ovale_a_queue((150, 100, 450, 260), (300, 380))

    assert planche.classer(geometry.profil_de_forme(region.mask)) == planche.DIALOGUE


def test_un_ovale_nu_reste_indetermine():
    """Le cas le plus fréquent du corpus, et le plus important : rien, dans une ellipse lisse
    sans queue, ne dit si c'est un dialogue dont la queue n'a pas été segmentée ou un
    récitatif arrondi. On ne tranche pas."""
    profil = geometry.profil_de_forme(_ovale((150, 100, 450, 260)).mask)

    assert planche.classer(profil) == planche.INDETERMINE


def test_un_ballon_en_etoile_est_un_cri():
    def dessin(d):
        pts = []
        for i in range(24):
            a = 2 * math.pi * i / 24
            r = 1.0 if i % 2 == 0 else 0.55
            pts.append((300 + 220 * r * math.cos(a), 200 + 130 * r * math.sin(a)))
        d.polygon(pts, fill=255)

    region = _region(dessin, (80, 70, 520, 330))

    assert planche.classer(geometry.profil_de_forme(region.mask)) == planche.CRI


def test_le_taux_d_indetermine_est_publiable():
    """`tools/banc.py` et `RAPPORT.md` en dépendent : un classifieur dont personne ne peut
    mesurer la distribution est un classifieur qu'on ne peut pas contredire."""
    s = planche.Structure(groupes=[1, 1, 1],
                          types=[planche.RECITATIF, planche.INDETERMINE,
                                 planche.INDETERMINE],
                          locuteurs=["", "", ""])

    t = planche.taux([s])

    assert t["bulles"] == 3
    assert t["types"][planche.INDETERMINE] == 2
    assert t["types"][planche.CRI] == 0


# --------------------------------------------------------------------------- #
# Les locuteurs — les trois précautions
# --------------------------------------------------------------------------- #

def test_deux_queues_convergentes_donnent_le_meme_locuteur():
    a = _ovale_a_queue((60, 60, 260, 180), (300, 300))
    b = _ovale_a_queue((340, 60, 540, 180), (320, 300))

    s = planche.analyser([a, b], TAILLE)

    assert s.locuteurs[0] and s.locuteurs[0] == s.locuteurs[1]


def test_deux_queues_opposees_donnent_deux_locuteurs():
    """C'est ce qui fait d'une liste de répliques un ÉCHANGE — donc la condition du
    tutoiement cohérent et de l'accord des adjectifs."""
    a = _ovale_a_queue((60, 60, 260, 180), (90, 320))
    b = _ovale_a_queue((340, 60, 540, 180), (560, 320))

    s = planche.analyser([a, b], TAILLE)

    assert s.locuteurs[0] and s.locuteurs[1]
    assert s.locuteurs[0] != s.locuteurs[1]


def test_aucune_etiquette_quand_une_seule_queue_est_lisible():
    """Précaution n° 3 : une étiquette unique posée à côté de bulles muettes suggérerait
    faussement qu'on a tout vu."""
    s = planche.analyser([_ovale_a_queue((60, 60, 260, 180), (150, 300)),
                          _ovale((340, 60, 540, 180))], TAILLE)

    assert s.locuteurs == ["", ""]


def test_les_etiquettes_sont_locales_a_la_planche():
    """Aucune reconnaissance de personnages : rien ne relie le [A] d'une planche à celui de
    la suivante, et le prompt ne le prétend pas. Deux planches identiques doivent donc rendre
    les mêmes lettres, sans qu'aucun état ne circule."""
    paire = [_ovale_a_queue((60, 60, 260, 180), (90, 320)),
             _ovale_a_queue((340, 60, 540, 180), (560, 320))]

    premiere = planche.analyser(paire, TAILLE)
    seconde = planche.analyser(paire, TAILLE)

    assert premiere.locuteurs == seconde.locuteurs == ["A", "B"]


# --------------------------------------------------------------------------- #
# L'énoncé — et son iso-comportement
# --------------------------------------------------------------------------- #

def test_sans_structure_l_enonce_est_celui_de_la_1_0_0():
    """Le critère d'acceptation du lot : « le mode texte sans les nouvelles clés produit un
    résultat inchangé », vérifiable par diff de `traduction.json` sur un tome."""
    assert planche.lignes_bulles(["a", "b"], None) == ["1. a", "2. b"]
    assert planche.lignes_bulles(["a", "b"], planche.vide(2)) == ["1. a", "2. b"]


def test_une_structure_sans_rien_a_dire_n_ecrit_rien():
    """Un seul groupe, aucun type, aucun locuteur : coller la note de lecture serait payer
    des tokens pour décrire un vide."""
    s = planche.vide(3)

    assert not s.annotee()
    assert planche.note_de_lecture([s]) == ""


def test_l_enonce_porte_le_locuteur_puis_le_type():
    s = planche.Structure(groupes=[1, 1], types=[planche.PENSEE, planche.DIALOGUE],
                          locuteurs=["A", "B"])

    lignes = planche.lignes_bulles(["ici", "là"], s)

    assert lignes == ["1. [A] (pensée) ici", "2. [B] là"]


def test_le_depart_decale_la_numerotation_pour_un_lot():
    s = planche.Structure(groupes=[1, 1], types=[planche.INDETERMINE] * 2,
                          locuteurs=["", ""])

    assert planche.lignes_bulles(["a", "b"], s, depart=8) == ["8. a", "9. b"]


def test_la_structure_fait_l_aller_retour_par_le_json():
    """Elle est persistée dans `structure.json`, à côté de `ocr.json` — c'est ce qui permet au
    banc de publier la distribution sans rouvrir un seul masque."""
    s = planche.Structure(groupes=[1, 2], types=[planche.CRI, planche.RECITATIF],
                          locuteurs=["A", ""], repli_ordre=True)

    relue = planche.Structure.depuis_json(s.en_json())

    assert relue == s


def test_une_charge_json_invalide_rend_none():
    assert planche.Structure.depuis_json(None) is None
    assert planche.Structure.depuis_json("bruit") is None


# --------------------------------------------------------------------------- #
# Les crops de groupe (mode « cible »)
# --------------------------------------------------------------------------- #

def test_les_boites_de_groupe_couvrent_leurs_bulles_avec_une_marge():
    """La marge n'est pas cosmétique : une boîte de groupe ne couvre que les BULLES, alors que
    ce qu'un modèle vision doit voir est le dessin autour d'elles."""
    regions = [_ovale((320, 40, 560, 180)), _ovale((60, 40, 300, 180)),
               _ovale((60, 620, 300, 760))]
    s = planche.analyser(regions, TAILLE)

    boites = planche.boites_de_groupes(regions, s, TAILLE)

    assert len(boites) == 2
    for x0, y0, x1, y1 in boites:
        assert 0 <= x0 < x1 <= TAILLE[0]
        assert 0 <= y0 < y1 <= TAILLE[1]
    # Le groupe du haut englobe les DEUX bulles du haut, marge comprise.
    assert boites[0][0] <= 60 and boites[0][2] >= 560
