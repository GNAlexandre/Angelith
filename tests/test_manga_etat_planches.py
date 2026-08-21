# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce qui rend un rendu périmé (`manga/etat_planches.py`).

Le défaut que ce fichier verrouille : `_pages_perimees` ne comparait `pages_out/` qu'à
`traduction.json`. Or l'éditeur graphique n'écrit **jamais** là — une réplique corrigée à la
main va dans `traduction_manuelle.json`, un bloc déplacé dans `mise_en_page.json`, et c'est
justement ce qui les fait survivre à un `--from traduction`. Corriger une réplique ne marquait
donc le rendu périmé nulle part, et l'archive continuait d'embarquer l'ancienne image.
"""
import os
import time

import numpy as np
import pytest

from manga import checkpoints, etat_planches as ep
from manga.detection import BubbleRegion

RECENT = time.time()
ANCIEN = RECENT - 3600


def _dater(chemin, quand: float) -> None:
    os.utime(chemin, (quand, quand))


@pytest.fixture
def tome(tmp_path):
    """Une planche détectée, traduite et rendue — tout à jour."""
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

    # Les données sont anciennes, le rendu est récent : rien n'est périmé.
    for nom in (ep.REGIONS_FILENAME, checkpoints.TRADUCTION_FILENAME,
                checkpoints.OCR_FILENAME, "masks.png"):
        if (ckpt / nom).exists():
            _dater(ckpt / nom, ANCIEN)
    _dater(rendu, RECENT)
    return build, ckpt, rendu


# --------------------------------------------------------------------------- #
#  Péremption
# --------------------------------------------------------------------------- #

def test_un_rendu_a_jour_n_est_pas_perime(tome):
    build, _ckpt, _rendu = tome
    assert ep.planches_a_relettrer(build) == []
    assert ep.motifs_de_peremption(build, 1) == []


def test_une_correction_manuelle_perime_le_rendu(tome):
    """LE cas qui échappait à l'ancienne règle."""
    build, ckpt, _rendu = tome
    checkpoints.save_traduction_manuelle(ckpt, {0: "Ma version"})
    _dater(ckpt / checkpoints.TRADUCTION_MANUELLE_FILENAME, RECENT + 10)
    assert ep.planches_a_relettrer(build) == [1]
    assert "réplique corrigée à la main" in ep.motifs_de_peremption(build, 1)


def test_un_bloc_deplace_perime_le_rendu(tome):
    build, ckpt, _rendu = tome
    checkpoints.save_mise_en_page(ckpt, {0: {"rect": [1, 2, 3, 4], "taille": 20}})
    _dater(ckpt / checkpoints.MISE_EN_PAGE_FILENAME, RECENT + 10)
    assert ep.planches_a_relettrer(build) == [1]
    assert "texte déplacé" in ep.motifs_de_peremption(build, 1)


def test_une_zone_retouchee_perime_le_rendu(tome):
    build, ckpt, _rendu = tome
    _dater(ckpt / ep.REGIONS_FILENAME, RECENT + 10)
    assert ep.planches_a_relettrer(build) == [1]
    assert "zones retouchées" in ep.motifs_de_peremption(build, 1)


def test_une_traduction_refaite_perime_le_rendu(tome):
    """L'ancien comportement doit continuer de marcher : on élargit, on ne remplace pas."""
    build, ckpt, _rendu = tome
    _dater(ckpt / checkpoints.TRADUCTION_FILENAME, RECENT + 10)
    assert ep.planches_a_relettrer(build) == [1]
    assert "traduction refaite" in ep.motifs_de_peremption(build, 1)


def test_les_motifs_se_cumulent(tome):
    build, ckpt, _rendu = tome
    checkpoints.save_traduction_manuelle(ckpt, {0: "Ma version"})
    checkpoints.save_mise_en_page(ckpt, {0: {"rect": [1, 2, 3, 4]}})
    for nom in (checkpoints.TRADUCTION_MANUELLE_FILENAME, checkpoints.MISE_EN_PAGE_FILENAME):
        _dater(ckpt / nom, RECENT + 10)
    motifs = ep.motifs_de_peremption(build, 1)
    assert len(motifs) == 2
    assert motifs[0] == "réplique corrigée à la main", "le geste manuel se nomme en premier"


def test_une_planche_jamais_rendue_n_est_pas_perimee(tome):
    """Elle n'est pas en retard, elle n'existe pas encore. La compter ferait passer un tome à
    peine détecté pour un tome à refaire."""
    build, _ckpt, rendu = tome
    rendu.unlink()
    assert ep.motifs_de_peremption(build, 1) == []
    assert ep.planches_a_relettrer(build) == []


def test_un_fichier_absent_ne_perime_rien(tome):
    """Un tome traité avant l'existence de `mise_en_page.json` ne doit pas se croire périmé."""
    build, ckpt, _rendu = tome
    assert not (ckpt / checkpoints.MISE_EN_PAGE_FILENAME).exists()
    assert ep.planches_a_relettrer(build) == []


def test_indices_restreint_l_examen(tome):
    build, ckpt, _rendu = tome
    _dater(ckpt / checkpoints.TRADUCTION_FILENAME, RECENT + 10)
    assert ep.planches_a_relettrer(build, indices=[1]) == [1]
    assert ep.planches_a_relettrer(build, indices=[2, 3]) == []


def test_un_build_vide_ne_leve_pas(tmp_path):
    assert ep.planches_a_relettrer(tmp_path / "rien") == []
    assert ep.resume(tmp_path / "rien") == []


# --------------------------------------------------------------------------- #
#  État d'une planche
# --------------------------------------------------------------------------- #

def test_l_etat_compte_ce_que_la_vignette_montre(tome):
    build, ckpt, _rendu = tome
    checkpoints.save_traduction_manuelle(ckpt, {0: "Ma version"})
    etat = ep.etat_planche(build, 1)
    assert etat["detectee"] is True
    assert etat["bulles"] == 1
    assert etat["corrigees"] == 1
    assert etat["rendue"] is True


def test_une_planche_sans_detection_rend_un_etat_pauvre_sans_lever(tmp_path):
    etat = ep.etat_planche(tmp_path / "manga", 7)
    assert etat["detectee"] is False
    assert etat["bulles"] == 0
    assert etat["index"] == 7
    assert "aucune détection" in ep.libelle_etat(etat)


def test_une_replique_vide_est_comptee(tome):
    build, ckpt, _rendu = tome
    checkpoints.save_traduction(ckpt, ["   "])
    assert ep.etat_planche(build, 1)["vides"] == 1


def test_le_libelle_nomme_le_motif_de_peremption(tome):
    build, ckpt, _rendu = tome
    checkpoints.save_traduction_manuelle(ckpt, {0: "Ma version"})
    _dater(ckpt / checkpoints.TRADUCTION_MANUELLE_FILENAME, RECENT + 10)
    libelle = ep.libelle_etat(ep.etat_planche(build, 1))
    assert "rendu périmé" in libelle
    assert "corrigée à la main" in libelle


def test_resume_suit_l_ordre_de_lecture(tome):
    build, _ckpt, _rendu = tome
    for numero in (3, 2):
        checkpoints.page_checkpoint_dir(build, numero).mkdir(parents=True)
    assert [e["index"] for e in ep.resume(build)] == [1, 2, 3]



# --------------------------------------------------------------------------- #
#  Memoisation (CacheEtats)
#
#  Le defaut verrouille ici : `etat_planche` coute 5,9 ms, et l'interface le demandait
#  150 fois par geste -- ouverture du tome, changement de filtre, rafraichissement complet.
#  Soit ~890 ms de fenetre gelee, plusieurs fois par minute de travail.
# --------------------------------------------------------------------------- #

def test_le_cache_rend_exactement_ce_que_rend_l_appel_direct(tome):
    build, _ckpt, _rendu = tome
    cache = ep.CacheEtats()
    assert cache.lire(build, 1) == ep.etat_planche(build, 1)


def test_un_second_appel_ne_recalcule_pas(tome):
    build, _ckpt, _rendu = tome
    cache = ep.CacheEtats()
    for _ in range(5):
        cache.lire(build, 1)
    assert (cache.calculs, cache.succes) == (1, 4)


def test_une_correction_manuelle_invalide_l_entree(tome):
    """La cle EST l'etat du disque : il n'y a aucune invalidation explicite a oublier."""
    build, ckpt, _rendu = tome
    cache = ep.CacheEtats()
    assert cache.lire(build, 1)["corrigees"] == 0
    checkpoints.save_traduction_manuelle(ckpt, {0: "Ma version"})
    assert cache.lire(build, 1)["corrigees"] == 1
    assert cache.calculs == 2


def test_un_relettrage_invalide_l_entree(tome):
    build, _ckpt, rendu = tome
    cache = ep.CacheEtats()
    cache.lire(build, 1)
    _dater(rendu, RECENT + 120)
    cache.lire(build, 1)
    assert cache.calculs == 2, "un rendu reecrit doit faire recalculer"


def test_deux_planches_ne_se_collisionnent_pas(tome):
    build, _ckpt, _rendu = tome
    ckpt2 = checkpoints.page_checkpoint_dir(build, 2)
    ckpt2.mkdir(parents=True)
    cache = ep.CacheEtats()
    assert cache.lire(build, 1)["detectee"] is True
    assert cache.lire(build, 2)["detectee"] is False


def test_oublier_force_le_recalcul(tome):
    """Redondant avec la signature, et c'est voulu : sur un `mtime` d'une seconde de
    resolution, ecrire puis relire dans la meme seconde rendrait la meme cle."""
    build, _ckpt, _rendu = tome
    cache = ep.CacheEtats()
    cache.lire(build, 1)
    cache.oublier(1)
    cache.lire(build, 1)
    assert cache.calculs == 2


def test_vider_oublie_tout(tome):
    build, _ckpt, _rendu = tome
    cache = ep.CacheEtats()
    cache.lire(build, 1)
    assert len(cache) == 1
    cache.vider()
    assert len(cache) == 0


def test_la_signature_ne_lit_aucun_json(tome, monkeypatch):
    """Le cache ne vaut que parce que verifier la fraicheur est CENT FOIS moins cher que la
    reponse : 13 ms de `stat` contre 1 095 ms de parsing sur un tome de 150 planches. Si la
    signature se mettait a parser, le cache ne ferait que deplacer le cout."""
    build, _ckpt, _rendu = tome
    import json
    appels = []
    vrai = json.loads
    monkeypatch.setattr(json, "loads", lambda *a, **k: (appels.append(1), vrai(*a, **k))[1])
    ep.signature(build, 1)
    assert appels == []


def test_une_planche_absente_ne_fait_pas_lever(tmp_path):
    """La pellicule couvre tout le tome : lever sur une planche le rendrait inaffichable."""
    cache = ep.CacheEtats()
    etat = cache.lire(tmp_path / "manga", 42)
    assert etat["index"] == 42 and etat["detectee"] is False
