# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La voie de LECTURE de l'interface (`gui/travailleur.FilDeLecture`).

Ce qu'elle doit garantir, et pourquoi chacune de ces propriétés coûte cher quand elle casse :

  · elle **n'écrit jamais** — c'est ce qui justifie de la séparer de la voie unique, dont
    l'unicité protège les checkpoints ;
  · elle prend toujours la planche **la plus proche** de celle qu'on regarde : c'est l'ordre
    dans lequel l'utilisateur va les rencontrer ;
  · `vouloir()` **remplace** l'ensemble au lieu d'empiler. Une file aurait grossi à chaque
    déplacement et aurait continué à composer des planches quittées depuis longtemps ;
  · une composition qui échoue n'arrête pas le préchargement — un aperçu est un confort.

⚠ `pytest.importorskip` : PySide6 vit dans `requirements-gui.txt`, séparé exprès.
"""
from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

from PySide6.QtCore import QCoreApplication                                  # noqa: E402

from gui.travailleur import (GENRE_APERCU, GENRE_VIGNETTE, GENRES_LECTURE,   # noqa: E402
                             FilDeLecture, SignauxTravail)


@pytest.fixture(scope="module")
def qt_app():
    """Une `QCoreApplication` pour tout le module — sans elle, un signal émis depuis le fil
    de lecture vers le fil principal est mis en file par Qt et n'est jamais délivré."""
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


class _Atelier:
    """Atelier factice : il journalise ce qu'on lui demande et remplit un faux cache.

    ⚠ Par défaut, **aucune planche n'a d'aperçu à composer** (`fenetre` vide) : chaque planche
    ne représente alors qu'une seule unité de travail, sa vignette, et `demandes` garde une
    entrée par planche. C'est ce qui permet aux tests d'ordre et de robustesse ci-dessous de
    dire ce qu'ils disent sans se soucier des deux genres. Les tests qui visent la PRIORITÉ
    entre les deux natures peuplent `fenetre` explicitement."""

    def __init__(self, echouent=(), fenetre=(), echouent_apercu=()):
        self.vignettes: set[int] = set()          # vignettes fabriquées
        self.apercus: set[int] = set()            # aperçus composés
        self.demandes: list[int] = []             # numéros, dans l'ordre où on les a demandés
        self.travaux: list[tuple[str, int]] = []  # les mêmes, avec leur genre
        self.echouent = set(echouent)             # la VIGNETTE de ces planches lève
        self.echouent_apercu = set(echouent_apercu)
        self.fenetre = set(fenetre)               # planches qui ont AUSSI un aperçu à composer

    # `pretes` : l'ancien nom, conservé parce que plusieurs tests présèment l'état par lui.
    @property
    def pretes(self) -> set[int]:
        return self.vignettes

    def vignette(self, index: int) -> bool:
        self.demandes.append(index)
        self.travaux.append((GENRE_VIGNETTE, index))
        if index in self.echouent:
            raise RuntimeError(f"planche {index} indisponible")
        self.vignettes.add(index)
        return True

    def composer(self, index: int) -> bool:
        self.demandes.append(index)
        self.travaux.append((GENRE_APERCU, index))
        if index in self.echouent_apercu:
            raise RuntimeError(f"aperçu {index} incomposable")
        self.apercus.add(index)
        return True

    def restant(self, index: int) -> str | None:
        if index not in self.vignettes:
            return GENRE_VIGNETTE
        if index in self.fenetre and index not in self.apercus:
            return GENRE_APERCU
        return None

    def est_pret(self, index: int) -> bool:
        return self.restant(index) is None


def _tourner(fil: FilDeLecture, atelier: _Atelier, attendu: int, delai: float = 10.0) -> None:
    """Fait tourner la voie jusqu'à `attendu` compositions demandées, en pompant Qt."""
    fil.start()
    limite = time.monotonic() + delai
    while len(atelier.demandes) < attendu and time.monotonic() < limite:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    fil.arreter()
    fil.wait(2000)
    QCoreApplication.processEvents()


def _voie(atelier: _Atelier) -> tuple[FilDeLecture, SignauxTravail]:
    signaux = SignauxTravail()
    fil = FilDeLecture(signaux)
    fil.brancher(atelier.vignette, atelier.composer, atelier.restant)
    return fil, signaux


# --------------------------------------------------------------------------- #
#  Ordre et priorité
# --------------------------------------------------------------------------- #

def test_les_planches_voulues_sont_toutes_composees(qt_app):
    atelier = _Atelier()
    fil, _s = _voie(atelier)
    fil.vouloir([10, 11, 12, 13], courante=12)
    _tourner(fil, atelier, 4)
    assert set(atelier.demandes) == {10, 11, 12, 13}


def test_la_plus_proche_de_la_courante_passe_en_premier(qt_app):
    """C'est l'ordre dans lequel l'utilisateur va les rencontrer."""
    atelier = _Atelier()
    fil, _s = _voie(atelier)
    fil.vouloir([5, 6, 7, 8, 9, 10, 11], courante=8)
    _tourner(fil, atelier, 7)
    assert atelier.demandes[0] == 8, "la planche regardée d'abord"
    assert set(atelier.demandes[1:3]) == {7, 9}, "puis ses deux voisines"


def test_une_planche_deja_prete_n_est_jamais_recomposee(qt_app):
    atelier = _Atelier()
    atelier.pretes.add(11)
    fil, _s = _voie(atelier)
    fil.vouloir([10, 11, 12], courante=11)
    _tourner(fil, atelier, 2)
    assert 11 not in atelier.demandes
    assert set(atelier.demandes) == {10, 12}


def test_aucune_planche_n_est_composee_deux_fois(qt_app):
    atelier = _Atelier()
    fil, _s = _voie(atelier)
    fil.vouloir([1, 2, 3], courante=2)
    _tourner(fil, atelier, 3)
    time.sleep(0.15)                       # on laisse la voie tourner à vide
    fil.arreter()
    fil.wait(1000)
    assert len(atelier.demandes) == len(set(atelier.demandes))


# --------------------------------------------------------------------------- #
#  Remplacement plutôt qu'empilement
# --------------------------------------------------------------------------- #

def test_vouloir_remplace_l_ensemble_au_lieu_d_empiler(qt_app):
    """Le point de conception : se déplacer repriorise, il n'y a rien à annuler.

    Une file aurait servi les trois premières avant de regarder les nouvelles ; ici la
    seconde demande efface la première, à la composition déjà engagée près."""
    atelier = _Atelier()
    fil, _s = _voie(atelier)
    fil.vouloir([100, 101, 102], courante=101)
    fil.vouloir([1, 2], courante=1)        # l'utilisateur a sauté au début du tome
    _tourner(fil, atelier, 2)
    assert {1, 2} <= set(atelier.demandes), "les nouvelles doivent être servies"
    assert len([d for d in atelier.demandes if d >= 100]) <= 1, \
        "au plus celle qui était déjà engagée"


def test_oublier_arrete_le_prechargement(qt_app):
    atelier = _Atelier()
    fil, _s = _voie(atelier)
    fil.vouloir([1, 2, 3], courante=2)
    _tourner(fil, atelier, 3)
    fil.oublier()
    assert fil._prochaine() == (None, None, 0, 0)


def test_un_ensemble_vide_ne_demande_rien(qt_app):
    atelier = _Atelier()
    fil, _s = _voie(atelier)
    fil.vouloir([], courante=0)
    fil.start()
    time.sleep(0.1)
    fil.arreter()
    fil.wait(1000)
    assert atelier.demandes == []


# --------------------------------------------------------------------------- #
#  Robustesse et signaux
# --------------------------------------------------------------------------- #

def test_une_composition_qui_echoue_n_arrete_pas_les_autres(qt_app):
    """Un aperçu est un confort : échouer à en composer un ne doit pas priver l'utilisateur
    de tous les suivants — une planche jamais détectée ne doit pas geler la pellicule."""
    atelier = _Atelier(echouent={2})
    fil, _s = _voie(atelier)
    fil.vouloir([1, 2, 3], courante=2)
    _tourner(fil, atelier, 3)
    assert {1, 3} <= set(atelier.demandes)
    assert atelier.pretes == {1, 3}


def test_une_planche_en_echec_n_est_pas_redemandee_en_boucle(qt_app):
    """Le défaut que ce test a trouvé : une planche qui échoue n'entre jamais au cache, donc
    reste « manquante », donc est redemandée indéfiniment — et affame toutes les autres. Sur
    trois planches dont une illisible, seule l'illisible était traitée."""
    atelier = _Atelier(echouent={2})
    fil, _s = _voie(atelier)
    fil.vouloir([1, 2, 3], courante=2)
    _tourner(fil, atelier, 3)
    assert atelier.demandes.count(2) == 1, "une seule tentative, pas une boucle"
    assert fil._prochaine()[1] is None, "plus rien à faire une fois l'échec retenu"


def test_l_echec_compte_comme_regle_pour_l_avancement(qt_app):
    """Sinon la barre de préchargement n'atteindrait jamais son total."""
    atelier = _Atelier(echouent={2})
    fil, signaux = _voie(atelier)
    avancement: list[tuple[int, int]] = []
    signaux.prechargement.connect(lambda a, b: avancement.append((a, b)))
    fil.vouloir([1, 2, 3], courante=2)
    _tourner(fil, atelier, 3)
    assert avancement[-1] == (3, 3)


def test_reessayer_rearme_une_planche_apres_un_run(qt_app):
    """`vouloir()` ne réarme surtout pas : il est appelé à chaque changement de planche, et
    réarmer là ferait retomber dans la boucle d'échec. On ne réessaie que quand quelque chose
    a pu changer."""
    atelier = _Atelier(echouent={2})
    fil, _s = _voie(atelier)
    fil.vouloir([2], courante=2)
    _tourner(fil, atelier, 1)
    fil.vouloir([2], courante=2)
    assert fil._prochaine()[1] is None, "vouloir() ne doit pas réarmer"

    atelier.echouent.clear()                # un run vient de réparer la planche
    fil.reessayer(2)
    assert fil._prochaine()[1] == 2


def test_une_planche_prete_est_annoncee(qt_app):
    atelier = _Atelier()
    fil, signaux = _voie(atelier)
    annonces: list[int] = []
    signaux.apercu_pret.connect(annonces.append)
    fil.vouloir([7], courante=7)
    _tourner(fil, atelier, 1)
    assert annonces == [7]


def test_l_avancement_du_prechargement_est_emis(qt_app):
    atelier = _Atelier()
    fil, signaux = _voie(atelier)
    avancement: list[tuple[int, int]] = []
    signaux.prechargement.connect(lambda a, b: avancement.append((a, b)))
    fil.vouloir([1, 2, 3], courante=1)
    _tourner(fil, atelier, 3)
    assert avancement, "la barre doit pouvoir avancer"
    assert avancement[-1][1] == 3


def test_une_voie_sans_compositeur_ne_leve_pas(qt_app):
    fil = FilDeLecture(SignauxTravail())
    fil.vouloir([1, 2], courante=1)
    assert fil._prochaine() == (None, None, 0, 0)


def test_les_genres_de_lecture_sont_declares():
    """L'interface s'en sert pour ne verrouiller aucune planche : rien n'est écrit, donc il
    n'y a rien à protéger de l'utilisateur."""
    assert GENRE_APERCU in GENRES_LECTURE
    assert GENRE_VIGNETTE in GENRES_LECTURE


# --------------------------------------------------------------------------- #
#  Deux natures de travail — vignette et aperçu
#
#  Elles n'ont ni le même coût (quelques dizaines de ms contre 1,37 s), ni la même portée
#  (tout le tome contre une fenêtre de 21 planches), ni le même droit à l'échec. Les traiter
#  comme une seule unité de travail produisait deux défauts distincts : une bande qui reste
#  vide trente secondes, et des vignettes écrites sur disque qui n'atteignent jamais l'écran.
# --------------------------------------------------------------------------- #

def test_toutes_les_vignettes_passent_avant_les_apercus_voisins(qt_app):
    """Le défaut mesuré : les 21 aperçus de la fenêtre passaient devant TOUTES les vignettes,
    parce que le seul critère était la proximité. Une trentaine de secondes pendant lesquelles
    la bande restait vide au-delà du voisinage immédiat.

    L'ordre juste tient en trois temps : la planche REGARDÉE d'abord, entièrement ; puis
    toutes les vignettes, qui coûtent quelques dizaines de millisecondes et remplissent la
    bande ; puis seulement les aperçus des voisines, à 1,37 s pièce."""
    atelier = _Atelier(fenetre={1, 2, 3, 4, 5})
    fil, _s = _voie(atelier)
    fil.vouloir([1, 2, 3, 4, 5], courante=3)
    _tourner(fil, atelier, 10)

    assert atelier.travaux[:2] == [(GENRE_VIGNETTE, 3), (GENRE_APERCU, 3)],         "la planche regardée est servie entièrement, et en premier"
    milieu = atelier.travaux[2:6]
    assert [g for g, _n in milieu] == [GENRE_VIGNETTE] * 4,         "puis TOUTES les vignettes restantes, avant le moindre aperçu voisin"
    assert sorted(n for _g, n in milieu) == [1, 2, 4, 5]
    assert [g for g, _n in atelier.travaux[6:]] == [GENRE_APERCU] * 4


def test_la_planche_regardee_est_servie_avant_ses_voisines(qt_app):
    """C'est la seule image que l'utilisateur est en train de regarder : l'attendre derrière
    quoi que ce soit se voit immédiatement.

    Sa vignette passe avant son aperçu — 30 ms contre 1,37 s, et c'est elle qui met une image
    dans la bande — mais les deux passent avant tout ce qui concerne une autre planche."""
    atelier = _Atelier(fenetre={10, 11, 12})
    fil, _s = _voie(atelier)
    fil.vouloir([10, 11, 12], courante=11)
    _tourner(fil, atelier, 6)
    assert atelier.travaux[:2] == [(GENRE_VIGNETTE, 11), (GENRE_APERCU, 11)]
    assert all(n != 11 for _g, n in atelier.travaux[2:])


def test_un_apercu_qui_leve_ne_fait_pas_perdre_sa_vignette(qt_app):
    """⚠ LE défaut. Vignette et aperçu partageaient un seul code de retour : une vignette
    fraîchement écrite sur disque était perdue dès que la composition qui la suivait levait —
    et la planche entrant alors dans la mémoire d'échec, son icône ne revenait plus de la
    session. C'est ce qui laissait des cases vides dans la pellicule."""
    atelier = _Atelier(fenetre={7}, echouent_apercu={7})
    fil, signaux = _voie(atelier)
    annonces: list[int] = []
    signaux.apercu_pret.connect(annonces.append)
    fil.vouloir([7], courante=7)
    _tourner(fil, atelier, 2)

    assert 7 in atelier.vignettes, "la vignette doit avoir été fabriquée"
    assert annonces == [7], "et ANNONCÉE, malgré l'aperçu en échec"
    assert 7 not in atelier.apercus


def test_la_memoire_d_echec_est_par_genre(qt_app):
    """Un aperçu qu'on ne sait pas composer ne doit pas condamner la vignette de sa planche,
    qui, elle, réussit très bien."""
    atelier = _Atelier(fenetre={4}, echouent_apercu={4})
    fil, _s = _voie(atelier)
    fil.vouloir([4], courante=4)
    _tourner(fil, atelier, 2)

    assert fil._echoues == {(GENRE_APERCU, 4)}
    assert (GENRE_VIGNETTE, 4) not in fil._echoues
    assert fil._prochaine()[1] is None, "plus rien à faire : la vignette est faite"


def test_reessayer_rearme_les_deux_genres(qt_app):
    """L'appelant raisonne en planches, pas en natures de travail : ce qui a pu changer — un
    run, une réouverture du tome — les concerne l'une comme l'autre."""
    atelier = _Atelier(fenetre={4}, echouent={4}, echouent_apercu={4})
    fil, _s = _voie(atelier)
    fil.vouloir([4], courante=4)
    _tourner(fil, atelier, 1)
    assert (GENRE_VIGNETTE, 4) in fil._echoues

    atelier.echouent.clear()
    atelier.echouent_apercu.clear()
    fil.reessayer(4)
    assert fil._echoues == set()
    assert fil._prochaine()[:2] == (GENRE_VIGNETTE, 4)


def test_une_planche_hors_fenetre_n_a_que_sa_vignette(qt_app):
    """Les deux portées : les APERÇUS ne couvrent que la fenêtre (bornés en mémoire, 1 Mo
    pièce), les VIGNETTES couvrent tout le tome (sur disque, une fois)."""
    atelier = _Atelier(fenetre={50})
    fil, _s = _voie(atelier)
    fil.vouloir([50, 51, 52], courante=50)
    _tourner(fil, atelier, 4)

    assert [n for g, n in atelier.travaux if g == GENRE_APERCU] == [50]
    assert sorted(n for g, n in atelier.travaux if g == GENRE_VIGNETTE) == [50, 51, 52]
