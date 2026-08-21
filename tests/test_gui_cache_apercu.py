# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Cache d'aperçus de l'interface (`gui/cache_apercu.py`) — sans Qt, sans PySide6.

Deux propriétés portent tout le lot de fluidité :

  · une modification NON ENREGISTRÉE doit invalider l'entrée. Le mode de panne à éviter est
    l'aperçu périmé : il montrerait à l'utilisateur un texte qui n'est plus le sien, sans rien
    pour le signaler ;
  · le plafond est en OCTETS. Une planche à deux bulles et une planche à quatorze ne coûtent
    pas la même chose ; un plafond en nombre d'entrées laisserait la mémoire suivre le contenu
    du tome.
"""
from dataclasses import dataclass, field

import pytest

from gui.cache_apercu import CacheApercu, poids_apercu, signature


@dataclass
class _ImageFactice:
    width: int
    height: int


@dataclass
class _CalqueFactice:
    image: _ImageFactice


@dataclass
class _ApercuFactice:
    calques: list = field(default_factory=list)
    fond: object = None


def _apercu(n_calques: int = 1, cote: int = 100) -> _ApercuFactice:
    return _ApercuFactice(calques=[_CalqueFactice(_ImageFactice(cote, cote))
                                   for _ in range(n_calques)])


@pytest.fixture
def planche(tmp_path):
    chemin = tmp_path / "page_0001.png"
    chemin.write_bytes(b"PNG")
    return chemin


# --------------------------------------------------------------------------- #
#  La signature
# --------------------------------------------------------------------------- #

def test_deux_appels_identiques_donnent_la_meme_signature(planche):
    a = signature(1, planche, ["Bonjour"], {0: {"rect": [1, 2, 3, 4]}})
    b = signature(1, planche, ["Bonjour"], {0: {"rect": [1, 2, 3, 4]}})
    assert a == b


def test_un_texte_modifie_change_la_signature(planche):
    """LA propriété du cache : la correction vit en mémoire, pas sur le disque, donc c'est
    elle qui doit invalider — il n'y a aucune invalidation explicite à écrire, donc aucune
    à oublier."""
    avant = signature(1, planche, ["Bonjour"], None)
    apres = signature(1, planche, ["Ma version"], None)
    assert avant != apres


def test_une_mise_en_page_modifiee_change_la_signature(planche):
    avant = signature(1, planche, ["Bonjour"], None)
    apres = signature(1, planche, ["Bonjour"], {0: {"rect": [1, 2, 3, 4]}})
    assert avant != apres


def test_l_ordre_des_mises_en_page_ne_change_pas_la_signature(planche):
    """Un dictionnaire n'est pas hachable et son ordre n'a aucun sens ici : deux mises en page
    identiques posées dans un ordre différent ne doivent pas produire deux entrées."""
    a = signature(1, planche, ["x"], {0: {"r": 1}, 1: {"r": 2}})
    b = signature(1, planche, ["x"], {1: {"r": 2}, 0: {"r": 1}})
    assert a == b


def test_deux_planches_ne_se_collisionnent_pas(planche):
    assert signature(1, planche, ["x"], None) != signature(2, planche, ["x"], None)


def test_une_planche_nettoyee_reecrite_change_la_signature(planche):
    import os
    avant = signature(1, planche, ["x"], None)
    futur = planche.stat().st_mtime + 120
    os.utime(planche, (futur, futur))
    assert signature(1, planche, ["x"], None) != avant


def test_un_fichier_absent_ne_leve_pas(tmp_path):
    assert signature(1, tmp_path / "jamais.png", ["x"], None)[1] == 0.0


# --------------------------------------------------------------------------- #
#  Le cache
# --------------------------------------------------------------------------- #

def test_lire_rend_ce_qu_on_a_pose():
    cache = CacheApercu()
    apercu = _apercu()
    cache.poser(("a",), apercu)
    assert cache.lire(("a",)) is apercu
    assert cache.succes == 1 and cache.echecs == 0


def test_une_cle_absente_rend_none_et_compte_un_echec():
    cache = CacheApercu()
    assert cache.lire(("jamais",)) is None
    assert cache.echecs == 1


def test_reposer_la_meme_cle_ne_compte_pas_deux_fois():
    cache = CacheApercu()
    cache.poser(("a",), _apercu(n_calques=2))
    poids = cache.octets
    cache.poser(("a",), _apercu(n_calques=2))
    assert cache.octets == poids
    assert len(cache) == 1


def test_le_plafond_evince_la_plus_ancienne():
    # Un calque de 100 × 100 × 4 = 40 000 octets ; le plafond de 1 Mo en contient 26.
    cache = CacheApercu(plafond_mo=1)
    for i in range(40):
        cache.poser((i,), _apercu())
    assert cache.octets <= cache.plafond
    assert (0,) not in cache, "la plus ancienne doit avoir été évincée"
    assert (39,) in cache, "la plus récente doit rester"


def test_un_succes_protege_de_l_eviction():
    """C'est tout l'intérêt d'un LRU plutôt que d'une file : la planche qu'on regarde ne doit
    pas être évincée par le préchargement de celles qu'on ne regarde pas."""
    cache = CacheApercu(plafond_mo=1)
    cache.poser((0,), _apercu())
    for i in range(1, 20):
        cache.poser((i,), _apercu())
        cache.lire((0,))
    for i in range(20, 40):
        cache.poser((i,), _apercu())
        cache.lire((0,))
    assert (0,) in cache


def test_une_entree_plus_grosse_que_le_plafond_est_conservee():
    """L'évincer ferait recomposer immédiatement ce qu'on vient de payer."""
    cache = CacheApercu(plafond_mo=1)
    cache.poser(("enorme",), _apercu(n_calques=1, cote=2000))
    assert cache.octets > cache.plafond
    assert cache.lire(("enorme",)) is not None


def test_oublier_planche_retire_toutes_ses_entrees(planche):
    cache = CacheApercu()
    cache.poser(signature(1, planche, ["a"], None), _apercu())
    cache.poser(signature(1, planche, ["b"], None), _apercu())
    cache.poser(signature(2, planche, ["a"], None), _apercu())
    assert cache.oublier_planche(1) == 2
    assert cache.planches_en_cache() == {2}
    assert cache.octets == poids_apercu(_apercu())


def test_vider_remet_tout_a_zero():
    cache = CacheApercu()
    cache.poser(("a",), _apercu())
    cache.vider()
    assert len(cache) == 0 and cache.octets == 0


def test_le_poids_compte_les_calques_et_le_fond():
    sans_fond = _apercu(n_calques=2, cote=10)
    assert poids_apercu(sans_fond) == 2 * 10 * 10 * 4
    avec_fond = _apercu(n_calques=1, cote=10)
    avec_fond.fond = _ImageFactice(20, 20)
    assert poids_apercu(avec_fond) == 10 * 10 * 4 + 20 * 20 * 3


def test_un_apercu_sans_calque_ne_pese_rien():
    assert poids_apercu(_ApercuFactice()) == 0
