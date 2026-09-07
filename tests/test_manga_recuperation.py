# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Brouillons d'édition sur disque (`manga/recuperation.py`) — sans Qt.

L'invariant que ce fichier défend avant tout : **un brouillon ne périme rien.** C'est ce qui
distingue cette solution de celle qu'on a écartée (écrire directement dans les checkpoints),
laquelle ferait passer une planche en « à relettrer » à chaque caractère tapé et ferait
avertir `assemble_outputs` sur du travail en cours.
"""
import os
import time

import numpy as np
import pytest

from manga import checkpoints, document, etat_planches as ep, recuperation as rec
from manga.detection import BubbleRegion

RECENT = time.time()
ANCIEN = RECENT - 3600


@pytest.fixture
def tome(tmp_path):
    """Une planche détectée, traduite et rendue — rien de périmé."""
    build = tmp_path / "manga"
    ckpt = checkpoints.page_checkpoint_dir(build, 1)
    ckpt.mkdir(parents=True)
    masque = np.zeros((40, 30), dtype=bool)
    masque[5:20, 5:20] = True
    checkpoints.save_regions(ckpt, [BubbleRegion(bbox=(5, 5, 20, 20), mask=masque,
                                                 score=0.9, cls=0)], (30, 40))
    checkpoints.save_ocr(ckpt, ["こんにちは"])
    checkpoints.save_traduction(ckpt, ["Bonjour"])
    rendu = checkpoints.final_page_path(build, 1)
    rendu.parent.mkdir(parents=True, exist_ok=True)
    rendu.write_bytes(b"PNG")
    for chemin in ckpt.iterdir():
        os.utime(chemin, (ANCIEN, ANCIEN))
    os.utime(rendu, (RECENT, RECENT))
    return build, ckpt


# --------------------------------------------------------------------------- #
#  L'invariant : un brouillon ne perime rien
# --------------------------------------------------------------------------- #

def test_un_brouillon_ne_perime_aucun_rendu(tome):
    """LE test du fichier. Ecrire un brouillon ne doit changer aucun verdict."""
    build, ckpt = tome
    assert ep.planches_a_relettrer(build) == []
    etat = document.lire_etat(ckpt)
    etat.manuelles[0] = "Ma version"
    rec.ecrire(build, 1, etat)
    assert ep.planches_a_relettrer(build) == [], "un brouillon n'est pas un enregistrement"
    assert ep.motifs_de_peremption(build, 1) == []


def test_le_brouillon_vit_hors_des_checkpoints(tome):
    """`etat_planches._indices` parcourt `.checkpoints/` : le miroir doit rester dehors."""
    build, _ckpt = tome
    etat = document.lire_etat(checkpoints.page_checkpoint_dir(build, 1))
    rec.ecrire(build, 1, etat)
    assert rec.DOSSIER != ".checkpoints"
    assert rec.dossier(build).name == rec.DOSSIER
    assert rec.dossier_planche(build, 1).is_dir()
    assert not str(rec.dossier(build)).startswith(str(build / ".checkpoints"))


def test_un_brouillon_n_ajoute_aucune_planche_au_tome(tome):
    """Un miroir sur une planche inconnue ne doit pas la faire apparaitre dans le tome."""
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    rec.ecrire(build, 77, etat)
    assert [e["index"] for e in ep.resume(build)] == [1]


# --------------------------------------------------------------------------- #
#  Aller-retour
# --------------------------------------------------------------------------- #

def test_le_brouillon_se_relit_a_l_identique(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    etat.manuelles[0] = "Ma version"
    # Schema reel : c'est `rect` qui porte la position, et une entree sans `rect`
    # exploitable est ecartee a la lecture (cf. `checkpoints.CHAMPS_MISE_EN_PAGE`).
    etat.mises_en_page[0] = {"rect": [3, 4, 13, 9], "taille": 18}
    rec.ecrire(build, 1, etat)
    relu = rec.lire(build, 1)
    assert relu is not None
    assert relu.manuelles == {0: "Ma version"}
    assert relu.mises_en_page == {0: {"rect": [3, 4, 13, 9], "taille": 18}}
    assert relu.traduction == etat.traduction
    assert len(relu.regions) == len(etat.regions), "les regions font partie du brouillon"


def test_le_brouillon_n_ecrase_pas_le_checkpoint(tome):
    """Le disque reel doit rester intact tant que rien n'est enregistre."""
    build, ckpt = tome
    avant = checkpoints.load_traduction_manuelle(ckpt)
    etat = document.lire_etat(ckpt)
    etat.manuelles[0] = "Ma version"
    rec.ecrire(build, 1, etat)
    assert checkpoints.load_traduction_manuelle(ckpt) == avant


def test_une_planche_sans_brouillon_rend_none(tome):
    build, _ckpt = tome
    assert rec.lire(build, 9) is None


def test_un_brouillon_tronque_rend_none_au_lieu_de_lever(tome):
    """Un miroir ecrit a l'instant du plantage peut etre incomplet. Lever ferait echouer
    l'ouverture du tome entier — l'incident serait puni deux fois."""
    build, ckpt = tome
    rec.ecrire(build, 1, document.lire_etat(ckpt))
    (rec.dossier_planche(build, 1) / "regions.json").write_text("{ tronque", encoding="utf-8")
    assert rec.lire(build, 1) is None


# --------------------------------------------------------------------------- #
#  Inventaire et effacement
# --------------------------------------------------------------------------- #

def test_les_planches_en_attente_sont_listees_triees(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    for numero in (12, 3, 40):
        rec.ecrire(build, numero, etat)
    assert rec.planches(build) == [3, 12, 40]


def test_un_tome_sans_brouillon_ne_propose_rien(tmp_path):
    assert rec.planches(tmp_path / "manga") == []
    assert rec.date(tmp_path / "manga") is None
    assert rec.resume(tmp_path / "manga")["existe"] is False


def test_le_resume_porte_la_date_et_les_planches(tome):
    build, ckpt = tome
    rec.ecrire(build, 1, document.lire_etat(ckpt))
    resume = rec.resume(build)
    assert resume["existe"] is True and resume["planches"] == [1]
    assert resume["date"] is not None and abs(resume["date"] - time.time()) < 60


def test_effacer_une_planche_laisse_les_autres(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    rec.ecrire(build, 1, etat)
    rec.ecrire(build, 2, etat)
    rec.effacer(build, 1)
    assert rec.planches(build) == [2]


def test_effacer_la_derniere_retire_le_dossier(tome):
    """Un marqueur seul annoncerait une reprise vide."""
    build, ckpt = tome
    rec.ecrire(build, 1, document.lire_etat(ckpt))
    rec.effacer(build, 1)
    assert not rec.dossier(build).exists()
    assert rec.resume(build)["existe"] is False


def test_effacer_sans_index_efface_tout(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    for numero in (1, 2, 3):
        rec.ecrire(build, numero, etat)
    rec.effacer(build)
    assert rec.planches(build) == []


def test_effacer_un_tome_sans_brouillon_ne_leve_pas(tmp_path):
    rec.effacer(tmp_path / "manga")
    rec.effacer(tmp_path / "manga", 3)


def test_reecrire_un_brouillon_remplace_le_precedent(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    etat.manuelles[0] = "Premiere"
    rec.ecrire(build, 1, etat)
    etat.manuelles[0] = "Seconde"
    rec.ecrire(build, 1, etat)
    assert rec.lire(build, 1).manuelles == {0: "Seconde"}


# --------------------------------------------------------------------------- #
#  Empreinte : ne reecrire que ce qui a change
#
#  Le defaut verrouille ici : la sauvegarde automatique reecrivait l'etat COMPLET de chaque
#  planche en attente a chaque tic de 30 s, masks.png compris, sur le fil d'affichage. A
#  13-41 ms par planche, trente planches gelaient la fenetre 0,4 a 1,2 s toutes les
#  demi-minutes -- pour reecrire les memes octets.
#
#  On compte les ECRITURES, pas le temps : une mesure de duree serait instable, un compteur
#  ne ment pas.
# --------------------------------------------------------------------------- #

def test_un_etat_inchange_rend_la_meme_empreinte(tome):
    build, ckpt = tome
    # Les deux lectures sont NOMMÉES, et ce n'est pas cosmétique : écrite en une ligne,
    # l'assertion comparait deux expressions identiques, ce qui se lit comme une tautologie
    # alors que le test porte sur la relecture — `lire_etat` est appelé DEUX fois, et c'est
    # sa reproductibilité qu'on mesure.
    premiere = rec.empreinte(document.lire_etat(ckpt))
    seconde = rec.empreinte(document.lire_etat(ckpt))
    assert premiere == seconde


def test_une_correction_d_un_seul_caractere_change_l_empreinte(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    avant = rec.empreinte(etat)
    etat.manuelles[0] = "Bonjour!"
    assert rec.empreinte(etat) != avant


def test_retirer_une_correction_change_l_empreinte(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    etat.manuelles[0] = "Ma version"
    avec = rec.empreinte(etat)
    etat.manuelles.pop(0)
    assert rec.empreinte(etat) != avec


def test_deplacer_un_bloc_change_l_empreinte(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    avant = rec.empreinte(etat)
    etat.mises_en_page[0] = {"rect": [1, 2, 3, 4]}
    assert rec.empreinte(etat) != avant


def test_bouger_une_region_change_l_empreinte(tome):
    """Les masques ne sont pas haches (plusieurs Mo) : c'est la boite qui porte le geste."""
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    avant = rec.empreinte(etat)
    etat.regions[0].bbox = (6, 6, 21, 21)
    assert rec.empreinte(etat) != avant


def test_supprimer_une_region_change_l_empreinte(tome):
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    avant = rec.empreinte(etat)
    etat.regions = []
    assert rec.empreinte(etat) != avant


def test_l_empreinte_ne_touche_pas_au_disque(tome, monkeypatch):
    """Elle doit etre CENT fois moins chere que l'ecriture qu'elle evite."""
    build, ckpt = tome
    etat = document.lire_etat(ckpt)
    monkeypatch.setattr(rec.document, "ecrire_etat",
                        lambda *a, **k: pytest.fail("l'empreinte ne doit rien ecrire"))
    rec.empreinte(etat)


def test_l_empreinte_survit_a_un_etat_vide(tmp_path):
    """Une planche jamais traduite ne doit pas faire lever la sauvegarde automatique."""
    vide = document.EtatPlanche()
    assert rec.empreinte(vide) == rec.empreinte(document.EtatPlanche())
