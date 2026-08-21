# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Découpe et lecture des tranches (`scan/lecture.py`), sans charger le moindre modèle.

Ce qui compte ici n'est pas ce que le modèle lit — c'est **ce qu'on lui donne** : les ruby
ne doivent jamais entrer dans le crop de leur colonne, les tranches doivent couvrir la
colonne entière, et une lecture qui contredit la grille doit être relue autrement.
"""
import pytest

from conftest_scan import LecteurFactice, page, poser_ruby
from scan import grille, lecture


def _page_longue(n=5, cases=40):
    return page([{"cases": cases}] * n, hauteur=cases * 40 + 300)


# --------------------------------------------------------------------------- #
#  Découpe en imagettes
# --------------------------------------------------------------------------- #

def test_toutes_les_tranches_de_toutes_les_colonnes_sont_envoyees():
    pf = _page_longue()
    plan = grille.analyser(pf.image())
    lecteur = LecteurFactice()
    lecture.lire_page(lecteur, pf.image(), plan)
    attendu = sum(len(c.tranches()) for c in plan.corps)
    assert sum(lecteur.appels) == attendu


def test_le_texte_d_une_colonne_est_la_concatenation_de_ses_tranches():
    pf = _page_longue(n=4, cases=40)
    plan = grille.analyser(pf.image())
    lecteur = LecteurFactice(reponses=[f"tranche{i}" for i in range(200)])
    resultats = lecture.lire_page(lecteur, pf.image(), plan)
    for r in resultats:
        assert r.texte == "".join(r.tranches)


def test_une_ruby_n_entre_jamais_dans_le_crop_de_sa_colonne():
    """En vertical, les furigana se posent à DROITE de la graphie, à quelques pixels : une
    marge de confort passerait dessus et l'OCR lirait la lecture en alternance avec le texte
    de base, ce qui détruit la ligne entière."""
    pf = page([{"cases": 20}] * 5, hauteur=1200)
    poser_ruby(pf, 1, apres=4, cases=3)
    plan = grille.analyser(pf.image())
    porteuse = [c for c in plan.corps if c.ruby][0]
    debut_ruby = min(r[0] for r in porteuse.ruby)
    imagettes = lecture.imagettes_de_colonne(pf.image(), porteuse)
    x0 = max(0, porteuse.x0 - lecture.MARGE)
    for im in imagettes:
        assert x0 + im.width <= debut_ruby, "le crop mord sur la ruby"


def test_les_ruby_sont_lues_a_part_et_rangees_avec_leur_colonne():
    pf = page([{"cases": 20}] * 5, hauteur=1200)
    poser_ruby(pf, 1, apres=4, cases=3)
    plan = grille.analyser(pf.image())
    lecteur = LecteurFactice(par_defaut="よみ")
    resultats = lecture.lire_page(lecteur, pf.image(), plan)
    porteuses = [r for r in resultats if r.ruby]
    assert len(porteuses) == 1
    assert porteuses[0].ruby == ["よみ"]


def test_une_colonne_sans_corps_ne_declenche_aucun_appel():
    plan = grille.PlanPage(grille.ILLUSTRATION, [], 0.0, (10, 10))
    lecteur = LecteurFactice()
    assert lecture.lire_page(lecteur, page([]).image(), plan) == []
    assert lecteur.appels == []


# --------------------------------------------------------------------------- #
#  Le garde-fou : la grille contredit-elle la lecture ?
# --------------------------------------------------------------------------- #

def _colonne(cases):
    return grille.Colonne(x0=0, x1=40, y0=0, y1=cases * 40, cases=cases)


def test_une_colonne_lue_bien_trop_court_est_suspecte():
    """Le mode d'échec mesuré : une colonne de 40 caractères donnée entière à `manga-ocr`
    en ressort à 23, inventée. C'est ce détecteur-là qui l'attrape."""
    assert lecture.est_suspecte(_colonne(40), "あ" * 23) is True


def test_une_colonne_lue_juste_n_est_pas_suspecte():
    assert lecture.est_suspecte(_colonne(40), "あ" * 38) is False


def test_une_colonne_courte_n_est_jamais_suspecte():
    """Sous six cases l'écart relatif est du bruit : trois caractères lus en quatre font
    déjà 33 % d'écart, et c'est parfaitement correct."""
    assert lecture.est_suspecte(_colonne(3), "あ" * 5) is False


def test_les_points_de_suspension_ne_rendent_pas_une_colonne_suspecte():
    """`manga_ocr.post_process` développe `…` en trois points pleine chasse : une réplique
    de six cellules en ressort à dix caractères."""
    # 「 + う + う + … + … + 」 : six cellules pour dix caractères rendus.
    assert lecture.cellules("「うう．．．．．．」") == 6
    assert len("「うう．．．．．．」") == 10
    assert lecture.est_suspecte(_colonne(7), "「うう．．．．．．」") is False


def test_cellules_laisse_le_texte_ordinaire_intact():
    assert lecture.cellules("あいうえお") == 5
    assert lecture.cellules("") == 0


# --------------------------------------------------------------------------- #
#  Relecture décalée
# --------------------------------------------------------------------------- #

def test_une_colonne_suspecte_est_relue_une_seule_fois_et_autrement():
    """Rejouer le MÊME découpage redonnerait la même hallucination : le modèle est
    déterministe. La relecture doit donc décaler les coupes."""
    pf = _page_longue(n=4, cases=40)
    image = pf.image()
    plan = grille.analyser(image)
    encre, _s, _n = grille.choisir_seuil(image)
    n_tranches = sum(len(c.tranches()) for c in plan.corps)

    class LecteurCourt(LecteurFactice):
        def __init__(self):
            super().__init__()
            self.tours = 0

        def lire(self, images):
            self.tours += 1
            super().lire(images)
            # Premier tour : réponses trop courtes → toutes les colonnes sont suspectes.
            # Second tour : réponses de bonne longueur.
            return ["あ" if self.tours == 1 else "あ" * 12 for _ in images]

    lecteur = LecteurCourt()
    resultats = lecture.lire_page(lecteur, image, plan, encre=encre)
    assert lecteur.tours == 2, "un seul tour de relecture, jamais deux"
    assert lecteur.appels[0] == n_tranches
    assert all(r.relue for r in resultats)


def test_sans_masque_d_encre_une_colonne_suspecte_est_signalee_mais_pas_relue():
    pf = _page_longue(n=4, cases=40)
    plan = grille.analyser(pf.image())
    lecteur = LecteurFactice(par_defaut="あ")
    resultats = lecture.lire_page(lecteur, pf.image(), plan)
    assert sum(lecteur.appels) == sum(len(c.tranches()) for c in plan.corps)
    assert len(lecteur.appels) == 1, "une page = un seul lot envoyé au modèle"
    assert any(r.suspecte for r in resultats)
    assert all(not r.relue for r in resultats)


def test_la_relecture_garde_la_meilleure_des_deux_lectures():
    pf = _page_longue(n=5, cases=40)
    image = pf.image()
    plan = grille.analyser(image)
    encre, _s, _n = grille.choisir_seuil(image)
    cases = plan.corps[0].cases

    class LecteurQuiSAmeliore(LecteurFactice):
        def __init__(self):
            super().__init__()
            self.tours = 0

        def lire(self, images):
            self.tours += 1
            super().lire(images)
            part = 3 if self.tours == 1 else max(1, cases // len(images))
            return ["あ" * part for _ in images]

    resultats = lecture.lire_page(lecteur := LecteurQuiSAmeliore(), image, plan, encre=encre)
    assert lecteur.tours == 2
    for colonne, r in zip(plan.corps, resultats):
        assert abs(len(r.texte) - colonne.cases) <= abs(3 * len(colonne.tranches())
                                                        - colonne.cases)


def test_en_dict_expose_ce_que_le_cache_attend():
    r = lecture.ResultatColonne(texte="あ", tranches=["あ"], ruby=[], suspecte=True)
    assert set(r.en_dict()) == {"texte", "tranches", "ruby", "suspecte", "relue"}


@pytest.mark.parametrize("cases,carac,mini", [(40, 10, 3), (12, 10, 1), (5, 10, 1)])
def test_le_nombre_de_tranches_reste_sain(cases, carac, mini):
    pf = page([{"cases": cases}] * 5, hauteur=cases * 40 + 300)
    plan = grille.analyser(pf.image(), caracteres_par_tranche=carac)
    assert all(len(c.tranches()) >= mini for c in plan.corps)
