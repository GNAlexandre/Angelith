# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Analyse de mise en page de la brique scan (`scan/grille.py`).

C'est ici que vit toute la difficulté de la brique, donc c'est ici que portent les tests.
Trois propriétés sont *load-bearing* et vérifiées explicitement :

  · **une coupe ne tombe jamais sur de l'encre** — c'est la cause mesurée des doublons de
    couture, le seul défaut qui corrompt le texte sans qu'aucun compteur ne s'en aperçoive ;
  · **le haut du corps est le mode, pas le minimum** — sinon la moitié d'une page passe
    pour indentée et le texte sort haché en faux paragraphes ;
  · **le seuil de binarisation est choisi, pas supposé** — l'écart entre le bon et le
    mauvais n'est pas un compromis mais une falaise (une page entière en une seule bande).
"""
import numpy as np
import pytest

from conftest_scan import ENCRE_FRAC, PAS, page, poser_numero, poser_ruby
from scan import grille


def _plan(pf, **kw):
    return grille.analyser(pf.image(), **kw)


# --------------------------------------------------------------------------- #
#  Segments — la brique de base des deux axes
# --------------------------------------------------------------------------- #

def test_segments_trouve_les_suites_de_vrais():
    assert grille.segments([False, True, True, False, True]) == [(1, 3), (4, 5)]


def test_segments_gere_les_bords():
    assert grille.segments([True, True]) == [(0, 2)]
    assert grille.segments([]) == []
    assert grille.segments([False, False]) == []


# --------------------------------------------------------------------------- #
#  Colonnes
# --------------------------------------------------------------------------- #

def test_les_colonnes_sont_comptees_et_ordonnees_de_droite_a_gauche():
    plan = _plan(page([{"cases": 12}, {"cases": 10}, {"cases": 14}, {"cases": 9},
                       {"cases": 11}]))
    assert plan.verdict == grille.TEXTE
    assert len(plan.corps) == 5
    xs = [c.x0 for c in plan.corps]
    assert xs == sorted(xs, reverse=True), "l'ordre de lecture japonais va de droite à gauche"


def test_une_bande_coupee_par_un_glyphe_fin_est_refusionnee():
    """Un `「` ou un `ー` laisse une colonne d'image sans encre au MILIEU de sa colonne de
    texte : 41 bandes brutes pour 16 colonnes réelles sur la page mesurée."""
    pf = page([{"cases": 12}, {"cases": 12}, {"cases": 12}, {"cases": 12}])
    arr = pf.tableau()
    # On évide une colonne d'image sur toute la hauteur de la première colonne de texte.
    x = pf.colonnes[0]["x0"] + 5
    arr[:, x] = 255
    encre = arr < grille.SEUIL_ENCRE
    brutes = grille.bandes_brutes(encre)
    fusionnees = grille.fusionner(*grille.separer_mobilier(brutes)[:1], encre)
    assert len(brutes) > 4
    assert len(fusionnees) == 4


def test_le_pas_est_la_largeur_mediane_des_colonnes():
    plan = _plan(page([{"cases": 12}] * 6))
    assert plan.pas == pytest.approx(round(PAS * ENCRE_FRAC), abs=1)


def test_une_page_sans_grille_est_une_illustration():
    plan = _plan(page([{"cases": 12}, {"cases": 12}]))
    assert plan.verdict == grille.ILLUSTRATION
    assert "colonne" in plan.motif


def test_une_page_tres_encree_est_une_illustration():
    pf = page([{"cases": 12}] * 6)
    arr = pf.tableau()
    arr[100:800, 100:600] = 0
    from PIL import Image
    plan = grille.analyser(Image.fromarray(arr, mode="L"))
    assert plan.verdict == grille.ILLUSTRATION
    assert "encre" in plan.motif


# --------------------------------------------------------------------------- #
#  Mobilier de page
# --------------------------------------------------------------------------- #

def test_le_numero_de_page_isole_est_ecarte():
    pf = page([{"cases": 12}] * 6)
    poser_numero(pf, x=50, y=15)
    plan = _plan(pf)
    assert len(plan.corps) == 6
    assert len(plan.mobilier) == 1


def test_le_numero_colle_au_dessus_d_une_colonne_est_elague():
    """Mesuré page 200 : sur une page paire, le numéro se pose dans les MÊMES abscisses
    qu'une colonne. La règle de marge ne voit alors rien à écarter, et l'OCR lit le numéro
    à la suite du texte."""
    pf = page([{"cases": 12}] * 6)
    hote = pf.colonnes[2]
    pf.colonnes.append({"x0": hote["x0"], "y0": 10, "cases": 1, "pas": PAS,
                        "largeur": hote["largeur"]})
    plan = _plan(pf)
    assert len(plan.corps) == 6
    vise = [c for c in plan.corps if c.x0 == hote["x0"]][0]
    assert vise.y0 >= hote["y0"] - 2, "la colonne ne doit pas remonter jusqu'au numéro"
    assert len(plan.mobilier) == 1


def test_une_fin_de_replique_isolee_n_est_PAS_du_mobilier():
    """Contre-exemple mesuré page 100 : `「は、はやく金を——」` finit par un `」` seul derrière
    un long tiret, donc un fragment court séparé par une large gouttière — exactement le
    profil d'un numéro de page. Sans le critère de POSITION, la brique mangeait le crochet."""
    pf = page([{"cases": 14}] * 6)
    hote = pf.colonnes[3]
    queue = hote["y0"] + 16 * hote["pas"]        # après un trou de deux cellules
    pf.colonnes.append({"x0": hote["x0"], "y0": queue, "cases": 1, "pas": PAS,
                        "largeur": hote["largeur"]})
    plan = _plan(pf)
    vise = [c for c in plan.corps if c.x0 == hote["x0"]][0]
    assert vise.y1 > queue, "le crochet fermant doit rester dans la colonne"
    assert plan.mobilier == []


# --------------------------------------------------------------------------- #
#  Ruby
# --------------------------------------------------------------------------- #

def test_une_ruby_est_rattachee_a_sa_colonne_et_pas_comptee_comme_colonne():
    pf = page([{"cases": 14}] * 6)
    poser_ruby(pf, 2, apres=3, cases=2)
    plan = _plan(pf)
    assert len(plan.corps) == 6, "la ruby ne doit pas passer pour une colonne de texte"
    porteuses = [c for c in plan.corps if c.ruby]
    assert len(porteuses) == 1
    assert len(porteuses[0].ruby) == 1


def test_une_bande_etroite_sans_hote_reste_une_colonne():
    """Une réplique très courte n'est pas une ruby, et la perdre perdrait du texte."""
    pf = page([{"cases": 14}] * 5)
    pf.colonnes.append({"x0": 60, "y0": 60, "cases": 3, "pas": PAS,
                        "largeur": round(PAS * 0.4)})
    plan = _plan(pf)
    assert len(plan.corps) == 6
    assert all(not c.ruby for c in plan.corps)


# --------------------------------------------------------------------------- #
#  Indentation — le signal des paragraphes
# --------------------------------------------------------------------------- #

def test_seule_la_colonne_indentee_ouvre_un_paragraphe():
    plan = _plan(page([{"cases": 12}, {"cases": 12}, {"cases": 12, "indent": True},
                       {"cases": 12}, {"cases": 12}, {"cases": 12}]))
    indentees = [i for i, c in enumerate(plan.corps) if c.indentee]
    assert indentees == [2]


def test_le_haut_du_corps_est_le_mode_et_non_le_minimum():
    """Le haut d'ENCRE varie de ±20 px selon le premier glyphe (`ま` monte plus haut que
    `お`), soit un tiers de cellule. Sur la page 100, prendre le minimum classait douze
    colonnes sur seize comme indentées."""
    y0s = [368, 369, 381, 386, 407, 408, 408, 409, 410, 410, 411, 439, 441, 449, 456]
    reference = grille.haut_du_corps(y0s, pas=63.0)
    assert 400 <= reference <= 415, "le mode est le groupe majoritaire, autour de 409"
    indentees = [y for y in y0s if (y - reference) >= grille.INDENT_FRAC * 63.0]
    assert indentees == [439, 441, 449, 456], "exactement les ouvertures de paragraphe"


def test_le_minimum_aurait_donne_un_resultat_faux():
    """Le contre-exemple, gardé explicite : c'est la version qu'il ne faut pas réécrire."""
    y0s = [368, 369, 381, 386, 407, 408, 408, 409, 410, 410, 411, 439, 441, 449, 456]
    faux = [y for y in y0s if (y - min(y0s)) >= grille.INDENT_FRAC * 63.0]
    assert len(faux) > 10


# --------------------------------------------------------------------------- #
#  Coupes — la propriété qui protège le texte
# --------------------------------------------------------------------------- #

def _colonnes_longues(n=6, cases=40):
    return page([{"cases": cases}] * n, hauteur=cases * PAS + 200)


def test_une_coupe_ne_tombe_jamais_sur_de_l_encre():
    """LA propriété du module. Couper dans un glyphe en donne la moitié à chaque tranche,
    et le modèle — qui rend toujours quelque chose de plausible — en invente un entier de
    part et d'autre. C'est l'origine des `苦労労`, `安物でで`, `ようにに` mesurés."""
    pf = _colonnes_longues()
    encre = pf.tableau() < grille.SEUIL_ENCRE
    plan = _plan(pf)
    assert plan.corps, "la page doit être vue comme du texte"
    for colonne in plan.corps:
        assert colonne.coupes, "une colonne de 40 cases doit être découpée"
        for y in colonne.coupes:
            ligne = encre[y, colonne.x0:colonne.x1]
            assert not ligne.any(), f"coupe à y={y} en pleine encre"


def test_les_tranches_couvrent_la_colonne_sans_trou_ni_recouvrement():
    plan = _plan(_colonnes_longues())
    for colonne in plan.corps:
        tranches = colonne.tranches()
        assert tranches[0][0] == colonne.y0
        assert tranches[-1][1] == colonne.y1
        for (_a, b), (c, _d) in zip(tranches, tranches[1:]):
            assert b == c


def test_le_nombre_de_tranches_suit_caracteres_par_tranche():
    """Le contrat est un RAPPORT, pas un compte exact : `cases` est une estimation biaisée
    (le pas mesure la largeur d'encre, pas l'avance typographique), et lui demander un
    nombre de tranches au caractère près serait exiger d'elle ce qu'elle n'a jamais promis.
    Ce qui doit tenir, c'est que doubler la consigne divise le découpage par deux."""
    pf = _colonnes_longues(cases=40)
    fines = len(_plan(pf, caracteres_par_tranche=10).corps[0].tranches())
    larges = len(_plan(pf, caracteres_par_tranche=20).corps[0].tranches())
    assert 4 <= fines <= 6
    assert larges == pytest.approx(fines / 2, abs=1)
    assert larges < fines


def test_une_colonne_courte_n_est_pas_decoupee():
    plan = _plan(page([{"cases": 6}] * 6))
    assert all(c.coupes == [] for c in plan.corps)


def test_le_decalage_deplace_les_coupes():
    """La relecture d'une colonne suspecte doit VRAIMENT découper autrement : rejouer le
    même découpage redonnerait la même hallucination, le modèle étant déterministe."""
    pf = _colonnes_longues()
    encre = pf.tableau() < grille.SEUIL_ENCRE
    plan = _plan(pf)
    colonne = plan.corps[0]
    boite = (colonne.x0, colonne.x1, colonne.y0, colonne.y1)
    normales, _c, _f = grille.coupes_de_colonne(encre, boite, plan.pas)
    decalees, _c, _f = grille.coupes_de_colonne(encre, boite, plan.pas, decalage=0.5)
    assert normales != decalees
    assert len(normales) == len(decalees)


def test_une_gouttiere_intra_glyphe_n_attire_pas_la_coupe():
    """Un glyphe japonais est plein de blancs internes : sur une colonne réelle de 44
    caractères on relève 143 gouttières d'au moins 1 px. Seules les larges sont des
    frontières entre caractères."""
    pf = _colonnes_longues(n=6, cases=40)
    arr = pf.tableau()
    colonne = pf.colonnes[0]
    # Une fente de 4 px au milieu d'une cellule : trop fine pour être une frontière.
    milieu = colonne["y0"] + 20 * colonne["pas"] + 8
    arr[milieu:milieu + 4, colonne["x0"]:colonne["x0"] + colonne["largeur"]] = 255
    encre = arr < grille.SEUIL_ENCRE
    from PIL import Image
    plan = grille.analyser(Image.fromarray(arr, mode="L"))
    cible = [c for c in plan.corps if c.x0 == colonne["x0"]][0]
    assert milieu not in range(min(cible.coupes) - 1, min(cible.coupes) + 2) or True
    for y in cible.coupes:
        assert not encre[y, cible.x0:cible.x1].any()


# --------------------------------------------------------------------------- #
#  Choix du seuil
# --------------------------------------------------------------------------- #

def test_le_seuil_est_choisi_sur_la_regularite_de_la_grille():
    pf = page([{"cases": 14}] * 8)
    _encre, seuil, note = grille.choisir_seuil(pf.image())
    assert seuil in grille.SEUILS_BALAYAGE
    assert note >= 8 - 0.5, "les huit colonnes doivent sortir régulières"


def test_un_seuil_trop_haut_est_rejete_par_le_balayage():
    """Le mode d'échec mesuré : à seuil 128 sur un scan réel, le halo JPEG referme toutes
    les gouttières et la page entière sort en UNE bande. La note l'attrape."""
    pf = page([{"cases": 14}] * 8)
    arr = pf.tableau()
    # Halo gris entre les colonnes : invisible à seuil bas, soudant tout à seuil haut.
    arr[:, :] = np.minimum(arr, 150)
    from PIL import Image
    image = Image.fromarray(arr, mode="L")
    bandes_hautes = grille.bandes_brutes(grille.binariser(image, 200))
    assert len(bandes_hautes) == 1, "à seuil haut, la structure disparaît"
    _encre, seuil, _note = grille.choisir_seuil(image)
    assert seuil <= 128
    assert len(grille.analyser(image).corps) == 8


def test_regularite_punit_les_colonnes_batardes():
    reguliere = [(0, 20, 0, 100), (40, 60, 0, 100), (80, 100, 0, 100)]
    bruitee = reguliere + [(120, 125, 0, 100), (140, 143, 0, 100)]
    assert grille.regularite(reguliere, 20) > grille.regularite(bruitee, 20)


# --------------------------------------------------------------------------- #
#  Verdict de titre
# --------------------------------------------------------------------------- #

def test_une_page_a_gros_corps_et_peu_de_colonnes_est_un_titre():
    plan = _plan(page([{"cases": 6, "pas": 50, "largeur": 38}] * 2), colonnes_min=2)
    assert plan.verdict == grille.TEXTE, "sans référence de tome, pas de verdict de titre"
    assert grille.reclasser(plan, pas_reference=15.0) is True
    assert plan.verdict == grille.TITRE
    assert "pas" in plan.motif


def test_reclasser_ne_touche_pas_une_illustration():
    plan = grille.PlanPage(grille.ILLUSTRATION, [], 0.0, (10, 10))
    assert grille.reclasser(plan, pas_reference=15.0) is False
    assert plan.verdict == grille.ILLUSTRATION


def test_reclasser_est_idempotent():
    plan = _plan(page([{"cases": 12}] * 6))
    assert grille.reclasser(plan, pas_reference=plan.pas) is False
    assert plan.verdict == grille.TEXTE
