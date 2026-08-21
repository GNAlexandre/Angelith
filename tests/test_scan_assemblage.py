# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Recollage des colonnes en document (`scan/assemblage.py`) — pur, sans E/S.

La propriété qui compte : **un paragraphe traverse les pages**. Un roman dont chaque page
formerait un paragraphe donnerait au traducteur un texte haché tous les quarante caractères,
et le découpage en blocs du pipeline LN s'en trouverait faussé de bout en bout.
"""
from scan.assemblage import (OUVRANTES, PageLue, assembler, nettoyer, ouvre_paragraphe,
                             poser_lectures, position_de_ruby, restaurer_points)


def _page(textes, indentations=None, **kw):
    return PageLue(index=kw.pop("index", 0), verdict=kw.pop("verdict", "texte"),
                   textes=textes,
                   indentations=indentations or [False] * len(textes), **kw)


# --------------------------------------------------------------------------- #
#  Paragraphes
# --------------------------------------------------------------------------- #

def test_les_colonnes_non_indentees_forment_un_seul_paragraphe():
    sortie = assembler([_page(["あいう", "えおか", "きくけ"])])
    assert sortie.strip() == "あいうえおかきくけ"


def test_une_colonne_indentee_ouvre_un_paragraphe():
    sortie = assembler([_page(["あいう", "えおか", "きくけ"], [False, True, False])])
    assert sortie.strip().split("\n\n") == ["あいう", "えおかきくけ"]


def test_une_ouvrante_ouvre_un_paragraphe_meme_sans_indentation():
    """En typographie japonaise une réplique n'est PAS indentée — le crochet occupe
    visuellement le retrait. La règle géométrique ne peut donc pas la voir."""
    sortie = assembler([_page(["あいう", "「ええ」", "かきく"])])
    assert sortie.strip().split("\n\n") == ["あいう", "「ええ」かきく"]


def test_toutes_les_ouvrantes_japonaises_comptent():
    for ouvrante in OUVRANTES:
        assert ouvre_paragraphe(ouvrante + "あ", indentee=False) is True


def test_une_colonne_ordinaire_n_ouvre_rien():
    assert ouvre_paragraphe("あいう", indentee=False) is False
    assert ouvre_paragraphe("", indentee=False) is False


def test_un_paragraphe_traverse_les_pages():
    """La propriété centrale du module."""
    sortie = assembler([_page(["あいう", "えおか"], index=0),
                        _page(["きくけ", "こさし"], index=1)])
    assert sortie.strip() == "あいうえおかきくけこさし"
    assert "\n\n" not in sortie.strip()


def test_une_page_qui_s_ouvre_sur_une_indentation_ferme_le_paragraphe_precedent():
    sortie = assembler([_page(["あいう"], index=0),
                        _page(["えおか"], [True], index=1)])
    assert sortie.strip().split("\n\n") == ["あいう", "えおか"]


def test_les_colonnes_vides_sont_ignorees_sans_couper_le_paragraphe():
    sortie = assembler([_page(["あいう", "", "えおか"])])
    assert sortie.strip() == "あいうえおか"


# --------------------------------------------------------------------------- #
#  Illustrations et titres
# --------------------------------------------------------------------------- #

def test_une_illustration_devient_un_marqueur_et_coupe_le_paragraphe():
    sortie = assembler([
        _page(["あいう"], index=0),
        PageLue(index=1, verdict="illustration", media="media/page_0001.jpg"),
        _page(["えおか"], index=2),
    ])
    blocs = sortie.strip().split("\n\n")
    assert blocs == ["あいう", "<!-- IMG: media/page_0001.jpg -->", "えおか"]


def test_une_illustration_sans_media_ne_produit_pas_de_marqueur_vide():
    sortie = assembler([PageLue(index=0, verdict="illustration", media=None)])
    assert "IMG" not in sortie


def test_une_page_de_titre_devient_un_titre_markdown():
    sortie = assembler([_page(["あいう"], index=0),
                        _page(["第一話"], index=1, verdict="titre"),
                        _page(["えおか"], index=2)])
    blocs = sortie.strip().split("\n\n")
    assert blocs == ["あいう", "# 第一話", "えおか"]


def test_un_titre_vide_n_est_pas_ecrit():
    assert "#" not in assembler([_page([""], index=0, verdict="titre")])


# --------------------------------------------------------------------------- #
#  Points de suspension
# --------------------------------------------------------------------------- #

def test_les_points_developpes_par_l_ocr_sont_restitues():
    """`manga_ocr.post_process` développe `…` en trois points pleine chasse. Sans retour en
    arrière, le japonais transmis au traducteur est trois fois plus long qu'à l'original sur
    toutes les suspensions."""
    assert restaurer_points("あ．．．い") == "あ…い"
    assert restaurer_points("あ．．．．．．い") == "あ……い"


def test_restaurer_points_laisse_un_point_isole_tranquille():
    assert restaurer_points("あ.い") == "あ.い"


def test_nettoyer_enleve_les_blancs_de_bord():
    assert nettoyer("  あい  ") == "あい"
    assert nettoyer(None) == ""


# --------------------------------------------------------------------------- #
#  Furigana
# --------------------------------------------------------------------------- #

def test_les_ruby_sont_ignorees_par_defaut():
    page = _page(["唖然とする"], lectures=[[(2, "あぜん")]])
    assert "あぜん" not in assembler([page])


def test_le_mode_parentheses_insere_la_lecture():
    page = _page(["唖然とする"], lectures=[[(2, "あぜん")]])
    assert assembler([page], ruby="parentheses").strip() == "唖然(あぜん)とする"


def test_plusieurs_lectures_sur_une_colonne_ne_se_decalent_pas():
    """Les insertions se font de la fin vers le début, sinon la première décale la seconde."""
    sortie = poser_lectures("東京都港区", [(2, "とうきょう"), (5, "みなとく")])
    assert sortie == "東京(とうきょう)都港区(みなとく)"


def test_une_lecture_vide_n_insere_pas_de_parentheses_vides():
    assert poser_lectures("東京", [(2, "  ")]) == "東京"


def test_une_position_hors_bornes_est_ramenee_dans_le_texte():
    assert poser_lectures("東京", [(99, "とうきょう")]) == "東京(とうきょう)"


def test_position_de_ruby_compte_depuis_le_haut_de_la_colonne():
    """La ruby couvre la graphie qu'elle annote : son BAS marque la fin du mot."""
    assert position_de_ruby((0, 10, 100, 180), y0_colonne=100, avance=40.0) == 2
    assert position_de_ruby((0, 10, 100, 180), y0_colonne=100, avance=0) == 0


# --------------------------------------------------------------------------- #
#  Forme du document
# --------------------------------------------------------------------------- #

def test_le_document_se_termine_par_une_seule_fin_de_ligne():
    sortie = assembler([_page(["あいう"])])
    assert sortie.endswith("\n") and not sortie.endswith("\n\n")


def test_un_tome_sans_texte_donne_un_document_vide_mais_valide():
    assert assembler([]) == "\n"
