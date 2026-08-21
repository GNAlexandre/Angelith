# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le chemin de rendu unique — et l'invariant qui autorise l'éditeur à redessiner lui-même.

L'éditeur doit pouvoir relettrer une planche sans relancer `process_volume` : un aller-retour
complet pour bouger un bloc de dix pixels serait inutilisable. Mais lui écrire un **second**
moteur de rendu serait pire — deux chemins libres de diverger sur la seule chose que
l'utilisateur regarde vraiment.

D'où le test central de ce fichier : **le rendu incrémental et celui de l'orchestrateur
doivent produire la même image, octet pour octet**. C'est la garantie qu'on tient déjà pour
les PSD (« 0 pixel d'écart sur 1 800 000 »), et c'est elle qui rend l'optimisation défendable.

⚠ L'invariant permanent du dépôt est vérifié ici aussi : hors des masques de bulles, tout
pixel reste **bit-à-bit identique** au fond fourni.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga import rendu, typeset
from manga.clean import analyze_bubble
from manga.detection import BubbleRegion

TAILLE = (420, 700)
BOITES = [(60, 40, 360, 240), (60, 320, 360, 520)]


def _planche() -> Image.Image:
    img = Image.new("RGB", TAILLE, (170, 170, 170))
    d = ImageDraw.Draw(img)
    for b in BOITES:
        d.ellipse(list(b), fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    return img


def _regions() -> list[BubbleRegion]:
    out = []
    for b in BOITES:
        m = Image.new("L", TAILLE, 0)
        ImageDraw.Draw(m).ellipse(list(b), fill=255)
        out.append(BubbleRegion(bbox=b, mask=np.asarray(m) > 127, score=0.9, cls=0))
    return out


@pytest.fixture
def planche():
    image = _planche()
    regions = _regions()
    styles = [analyze_bubble(image, r, None) for r in regions]
    return image, regions, styles


TEXTES = ["Première réplique", "Seconde réplique un peu plus longue"]


# --------------------------------------------------------------------------- #
# L'invariant qui autorise le rendu incrémental
# --------------------------------------------------------------------------- #

def test_les_deux_chemins_donnent_la_meme_image(planche):
    """LE test du lot. `rendu.rendre_planche` est le chemin de l'orchestrateur ET celui de
    l'éditeur : appelé deux fois avec les mêmes entrées, il doit rendre exactement la même
    chose — sinon « ce qui sort de l'interface est ce que produirait run_manga.py » n'est
    qu'une intention."""
    image, regions, styles = planche
    a = rendu.rendre_planche(image.copy(), regions, TEXTES, styles=styles,
                             cfg_typeset=None, sources=["あ", "い"])
    b = rendu.rendre_planche(image.copy(), regions, TEXTES, styles=styles,
                             cfg_typeset=None, sources=["あ", "い"])
    assert a.image.tobytes() == b.image.tobytes()


def test_l_orchestrateur_emprunte_bien_ce_chemin():
    """Si le bloc de rendu de l'orchestrateur regagnait un `typeset_page` en direct, ce test
    tomberait — c'est tout ce qu'on lui demande.

    ⚠ On inspecte `_process_volume` et non `process_volume` : depuis que celui-ci est une
    ENVELOPPE de vingt lignes (fermeture des clients LLM sur exception), son source ne
    contient plus une seule ligne de rendu et l'assertion passerait à vide."""
    import inspect

    from manga import orchestrator_manga as orch
    source = inspect.getsource(orch._process_volume)
    assert "rendu.rendre_planche(" in source
    assert "typeset.typeset_page(" not in source, (
        "le rendu de planche doit passer par manga/rendu.py, pas appeler typeset directement")


def test_une_mise_en_page_imposee_survit_au_chemin_partage(planche):
    """Le rendu incrémental existe POUR les mises en page déplacées : elles doivent traverser
    la fonction partagée, sinon l'éditeur et l'orchestrateur divergeraient sur elles."""
    image, regions, styles = planche
    sans = rendu.rendre_planche(image.copy(), regions, TEXTES, styles=styles)
    avec = rendu.rendre_planche(image.copy(), regions, TEXTES, styles=styles,
                                layouts={0: {"rect": [80, 60, 340, 130], "taille": 14}})
    assert sans.image.tobytes() != avec.image.tobytes()
    entree = next(e for e in avec.qa if e["type"] == "bulle" and e["index"] == 0)
    assert entree["repli"] == "mise_en_page"


# --------------------------------------------------------------------------- #
# L'invariant permanent
# --------------------------------------------------------------------------- #

def test_aucun_pixel_hors_bulle_n_est_modifie(planche):
    """L'invariant que le dépôt tient depuis le premier lot : le lettrage n'écrit QUE dans les
    intérieurs de bulles. Une gouttière entre deux cases doit ressortir bit-à-bit identique."""
    image, regions, styles = planche
    avant = np.asarray(image.copy())
    apres = np.asarray(rendu.rendre_planche(image.copy(), regions, TEXTES,
                                            styles=styles).image)

    dehors = np.ones(avant.shape[:2], dtype=bool)
    for st in styles:
        dehors &= ~st.interior
    assert (avant[dehors] == apres[dehors]).all()


def test_le_fond_est_mute_comme_typeset_page(planche):
    """Contrat conservé tel quel et documenté plutôt que corrigé : l'export PSD a besoin de la
    planche nettoyée intacte EN PLUS de la finale, et c'est l'appelant qui en garde une copie.
    Le changer ici ferait diverger les deux chemins sur un détail invisible en test unitaire
    et très visible en PSD."""
    image, regions, styles = planche
    avant = image.tobytes()
    resultat = rendu.rendre_planche(image, regions, TEXTES, styles=styles)
    assert image.tobytes() != avant
    assert resultat.image is image


# --------------------------------------------------------------------------- #
# Ce que le rendu rapporte
# --------------------------------------------------------------------------- #

def test_les_fits_ne_sont_produits_que_sur_demande(planche):
    """Ils étaient jusqu'ici conditionnés à l'activation du PSD : l'information n'existait donc
    pas quand elle n'était pas exportée, alors que l'éditeur en a besoin pour son aperçu."""
    image, regions, styles = planche
    sans = rendu.rendre_planche(image.copy(), regions, TEXTES, styles=styles)
    avec = rendu.rendre_planche(image.copy(), regions, TEXTES, styles=styles, avec_fits=True)
    assert sans.fits == []
    assert len(avec.fits) == 2
    assert {"index", "fit", "style", "police", "region"} <= set(avec.fits[0])


def test_le_qa_est_rempli_meme_sans_psd(planche):
    image, regions, styles = planche
    resultat = rendu.rendre_planche(image.copy(), regions, TEXTES, styles=styles)
    bulles = [e for e in resultat.qa if e["type"] == "bulle"]
    assert len(bulles) == 2
    assert all(e["taille"] > 0 for e in bulles)


def test_sans_glose_demandee_aucune_n_est_posee(planche):
    """Le mode par défaut est « rapport » : on détecte, on lit, on traduit, on rapporte — et
    on ne dessine rien sur le dessin."""
    image, regions, styles = planche
    resultat = rendu.rendre_planche(image.copy(), regions, TEXTES, styles=styles,
                                    zones_sfx=regions, traductions_sfx=["BOUM", "PAF"],
                                    mode_sfx="rapport")
    assert resultat.gloses == []
