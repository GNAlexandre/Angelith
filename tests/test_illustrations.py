# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`core/illustrations.py` — le classement, le rattachement et la signature de style.

Tout est fabriqué dans un `tmp_path` par Pillow : **aucune fixture ne dépend de `build/`**.
Un test qui lirait le corpus réel mesurerait le corpus, pas le code, et tomberait le jour où
un tome change.

Le test qui porte une DÉCISION du lot 23 est
`test_une_illustration_au_trait_n_est_pas_une_vignette` : le `PLAN-23` proposait de classer
en vignette toute image de « moins de 3 couleurs dominantes », et la mesure sur les
446 fichiers du corpus a montré que ce critère rangeait 48 illustrations au trait — 10,8 % —
parmi les logos. Le critère a été retiré ; ce test empêche qu'il revienne.
"""
from pathlib import Path

import pytest

from core import illustrations as ill

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402


def _img(chemin: Path, largeur: int, hauteur: int, couleur=(255, 255, 255),
         traits: int = 0) -> Path:
    """Une image synthétique, éventuellement hachurée pour lui donner de la densité de trait."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (largeur, hauteur), couleur)
    if traits:
        dessin = ImageDraw.Draw(image)
        for x in range(0, largeur, max(1, largeur // traits)):
            dessin.line([(x, 0), (x, hauteur)], fill=(0, 0, 0), width=1)
    image.save(chemin)
    return chemin


def _illus(nom: str, largeur: int, hauteur: int) -> ill.Illustration:
    return ill.Illustration(Path(nom), nom, largeur, hauteur, octets=1)


# ─────────────────────────────  classer : pur, sans disque  ─────────────────────────────

MEDIANE = 1400 * 1964                                  # la médiane réelle d'un tome du corpus


def test_une_vignette_est_reconnue_a_sa_surface():
    contexte = ill.ContexteTome(mediane_surface=MEDIANE)
    assert ill.classer(_illus("logo.jpg", 192, 192), contexte) == ill.VIGNETTE


def test_une_double_page_est_reconnue_a_son_ratio():
    contexte = ill.ContexteTome(mediane_surface=MEDIANE)
    assert ill.classer(_illus("dp.jpg", 2991, 1300), contexte) == ill.DOUBLE_PAGE


def test_une_pleine_page_portrait_de_taille_mediane():
    contexte = ill.ContexteTome(mediane_surface=MEDIANE)
    assert ill.classer(_illus("pp.jpg", 1400, 1964), contexte) == ill.PLEINE_PAGE


def test_la_couverture_prime_sur_la_pleine_page():
    contexte = ill.ContexteTome(mediane_surface=MEDIANE, couverture="p1.jpg")
    assert ill.classer(_illus("p1.jpg", 1400, 1991), contexte) == ill.COUVERTURE


def test_une_vignette_prime_sur_la_couverture():
    """Un logo d'éditeur désigné par erreur comme couverture reste un logo. L'ordre des tests
    de `classer` EST la définition, et cet ordre-là est délibéré."""
    contexte = ill.ContexteTome(mediane_surface=MEDIANE, couverture="logo.jpg")
    assert ill.classer(_illus("logo.jpg", 192, 192), contexte) == ill.VIGNETTE


def test_le_doute_tombe_en_indeterminee_et_pas_ailleurs():
    """roman D Vol.1 p209 : 2740×2200, ratio 1,25 — une double page réelle sous le seuil.
    La classe généreuse l'absorbe plutôt que de trancher."""
    contexte = ill.ContexteTome(mediane_surface=MEDIANE)
    assert ill.classer(_illus("p209.jpg", 2740, 2200), contexte) == ill.INDETERMINEE


def test_une_image_illisible_ne_fait_pas_tomber_le_classement():
    contexte = ill.ContexteTome(mediane_surface=MEDIANE)
    assert ill.classer(_illus("casse.emf", 0, 0), contexte) == ill.ILLISIBLE


def test_une_illustration_au_trait_n_est_pas_une_vignette(tmp_path):
    """La décision mesurée du lot 23 : le critère « moins de 3 couleurs dominantes » du
    `PLAN-23` étape 0.1 classait 48 illustrations sur 446 (10,8 %) parmi les logos. Une
    planche noir sur blanc n'a que deux teintes dominantes et reste une pleine page."""
    _img(tmp_path / "media" / "trait.png", 1400, 1964, traits=6)
    _img(tmp_path / "media" / "autre.png", 1400, 1964, traits=6)
    images = {i.nom: i for i in ill.inventaire(tmp_path)}
    assert images["trait.png"].couleurs_dominantes < 3
    assert images["trait.png"].classe in (ill.COUVERTURE, ill.PLEINE_PAGE)


# ───────────────────────────  couverture_candidate : pur aussi  ───────────────────────────

def test_la_couverture_suit_l_ordre_NATUREL_des_noms():
    """`p2` avant `p12`. Un tri lexical mettrait `p12` en tête et désignerait la mauvaise
    image — c'est exactement le défaut mesuré sur roman D Vol.1, dont la couverture `p1` n'est
    citée par aucun marqueur."""
    images = [_illus("v_p12.jpg", 1400, 1964), _illus("v_p2.jpg", 1400, 1964)]
    assert ill.couverture_candidate(images, MEDIANE) == "v_p2.jpg"


def test_la_couverture_saute_la_vignette_et_le_paysage():
    images = [_illus("a_colophon.png", 200, 201),      # vignette
              _illus("b_bandeau.jpg", 2048, 829),      # paysage
              _illus("c_cover.jpg", 1500, 2114)]
    assert ill.couverture_candidate(images, MEDIANE) == "c_cover.jpg"


def test_un_tome_sans_candidat_n_a_pas_de_couverture():
    assert ill.couverture_candidate([_illus("logo.png", 20, 20)], MEDIANE) == ""


# ────────────────────────────────  inventaire / rattacher  ────────────────────────────────

def _tome_synthetique(racine: Path) -> Path:
    """Un tome complet : trois illustrations, deux chapitres, un Markdown de volume dont la
    première image PRÉCÈDE le premier chapitre — donc orpheline, donc tête de volume."""
    media = racine / "media"
    _img(media / "p1.png", 1400, 1964, traits=4)         # couverture (ordre naturel)
    _img(media / "p2.png", 1400, 1964, traits=8)         # tête de volume
    _img(media / "p9.png", 1400, 1964, traits=8)         # dans le chapitre 1
    _img(media / "p20.png", 1400, 1964, traits=8)        # citée par personne

    chapitres = racine / "chapters"
    chapitres.mkdir(parents=True, exist_ok=True)
    (chapitres / "ch01.md").write_text(
        "# Un\n\nParagraphe.\n\n<!-- IMG: media/p9.png -->\n\nAutre paragraphe.\n",
        encoding="utf-8")
    (chapitres / "ch02.md").write_text("# Deux\n\nParagraphe.\n", encoding="utf-8")
    (racine / "Oeuvre_Vol.1.md").write_text(
        "<!-- IMG: media/p2.png -->\n\n# Un\n\nParagraphe.\n\n"
        "<!-- IMG: media/p9.png -->\n\nAutre paragraphe.\n\n# Deux\n\nParagraphe.\n",
        encoding="utf-8")
    return racine


def test_l_inventaire_lit_toutes_les_images_et_les_classe(tmp_path):
    images = ill.inventaire(_tome_synthetique(tmp_path))
    assert [i.nom for i in images] == ["p1.png", "p2.png", "p9.png", "p20.png"]
    assert {i.classe for i in images} == {ill.COUVERTURE, ill.PLEINE_PAGE}


def test_l_inventaire_d_un_tome_sans_media_est_vide(tmp_path):
    assert ill.inventaire(tmp_path) == []


def test_rattacher_place_chaque_image_dans_son_contexte(tmp_path):
    par_contexte = ill.rattacher(_tome_synthetique(tmp_path))
    assert [i.nom for i in par_contexte["ch01"]] == ["p9.png"]
    assert par_contexte["ch01"][0].contexte.startswith("ch01@")
    # La planche qui précède la première frontière de chapitre est la meilleure référence du
    # tome, et elle était purement et simplement perdue avant le correctif de
    # `pipeline/images.py`. Elle doit ressortir marquée, pas jetée.
    assert [i.nom for i in par_contexte[ill.TETE_DE_VOLUME]] == ["p2.png"]
    assert {i.nom for i in par_contexte[ill.NON_REFERENCEE]} == {"p1.png", "p20.png"}


def test_rattacher_ne_reecrit_pas_un_parseur_de_marqueurs(tmp_path):
    """Le rattachement doit passer par `pipeline.images` — un second parseur divergerait le
    jour où le format du marqueur change. On le vérifie en donnant un marqueur AVEC attributs
    de taille, forme que seul `split_marker` sait défaire."""
    racine = _tome_synthetique(tmp_path)
    (racine / "chapters" / "ch02.md").write_text(
        '# Deux\n\nTexte.\n\n<!-- IMG: media/p20.png|{width="6.2in" height="8.8in"} -->\n',
        encoding="utf-8")
    par_contexte = ill.rattacher(racine)
    assert [i.nom for i in par_contexte["ch02"]] == ["p20.png"]


def test_inventaire_rattache_porte_la_classe_ET_le_contexte(tmp_path):
    images = {i.nom: i for i in ill.inventaire_rattache(_tome_synthetique(tmp_path))}
    assert images["p2.png"].contexte == ill.TETE_DE_VOLUME
    assert images["p2.png"].classe == ill.PLEINE_PAGE
    assert ill.exploitable(images["p2.png"])


# ──────────────────────────────  L23.7 — signature de style  ──────────────────────────────

def test_la_signature_porte_TOUJOURS_son_echantillon(tmp_path):
    """Un descripteur sans son dénominateur est une impression, pas une mesure."""
    signature = ill.signature(ill.inventaire_rattache(_tome_synthetique(tmp_path)))
    assert signature["echantillon"] == 4
    assert set(ill.DESCRIPTEURS) <= set(signature)
    assert signature["palette"]


def test_un_tome_sans_image_exploitable_rend_une_signature_vide():
    signature = ill.signature([])
    assert signature["echantillon"] == 0
    assert signature["saturation_moyenne"] is None


def test_la_densite_de_trait_separe_un_aplat_d_une_hachure(tmp_path):
    aplat = tmp_path / "aplat"
    hachure = tmp_path / "hachure"
    for i in range(2):
        _img(aplat / "media" / f"p{i + 1}.png", 800, 1200, traits=2)
        _img(hachure / "media" / f"p{i + 1}.png", 800, 1200, traits=80)
    sa = ill.signature(ill.inventaire_rattache(aplat))
    sh = ill.signature(ill.inventaire_rattache(hachure))
    assert sh["densite_trait"] > sa["densite_trait"]
    assert sa["part_aplats"] > sh["part_aplats"]


def test_l_ecart_de_signature_se_publie_avec_ses_deux_echantillons(tmp_path):
    aplat = tmp_path / "a"
    hachure = tmp_path / "h"
    _img(aplat / "media" / "p1.png", 800, 1200, traits=2)
    for i in range(3):
        _img(hachure / "media" / f"p{i + 1}.png", 800, 1200, traits=80)
    ecart = ill.ecart_signature(ill.signature(ill.inventaire_rattache(aplat)),
                                ill.signature(ill.inventaire_rattache(hachure)))
    assert ecart["echantillons"] == [1, 3]
    assert ecart["moyenne"] > 0


def test_les_ancrages_proposes_ne_sont_jamais_valides_d_office(tmp_path):
    """Le déterministe propose, l'humain confirme. Une ancre auto-validée serait exactement
    le geste que le `PLAN-23` L23.7 interdit."""
    ancrages = ill.ancrages_proposes(
        ill.inventaire_rattache(_tome_synthetique(tmp_path)), nombre=2)
    assert len(ancrages) == 2
    assert all(a["valide_par_humain"] is False for a in ancrages)
    assert all(a["fichier"].startswith("media/") for a in ancrages)
