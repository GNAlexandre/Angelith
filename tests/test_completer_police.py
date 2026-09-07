# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`tools/completer_police.py` — compléter une police pour qu'elle couvre le français.

⚠ Le cobaye est **ComicNeue-Regular.ttf**, jamais Wildjess. Comic Neue est livrée avec le
dépôt sous SIL OFL 1.1 (`templates/fonts/OFL.txt`), donc présente sur la CI et modifiable.
Wildjess est une police Comicraft « all rights reserved » que le dépôt ne distribue pas
(cf. `NOTICE`) : un test qui en dépendrait serait sauté en silence partout ailleurs que sur
la machine de son propriétaire — exactement le défaut que `tools/polices.py` a corrigé.

Comic Neue couvrant déjà le français, on lui RETIRE des glyphes pour fabriquer le cas à
traiter. C'est ce qui rend le test reproductible : il ne dépend d'aucune police incomplète
qu'il faudrait trouver quelque part.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import completer_police  # noqa: E402

SOURCE = Path(__file__).resolve().parents[1] / "templates" / "fonts" / "ComicNeue-Regular.ttf"


def _amputee(destination: Path, caracteres: str) -> Path:
    """Une copie de Comic Neue privée des points de code demandés."""
    police = TTFont(str(SOURCE))
    for table in police["cmap"].tables:
        for caractere in caracteres:
            table.cmap.pop(ord(caractere), None)
    police.save(str(destination))
    return destination


@pytest.fixture()
def source_amputee(tmp_path):
    return _amputee(tmp_path / "amputee.ttf", "ÀÇœŒ«»—–ÄËÏÖÜÂÎÔÛÙÚäÿÆ")


def test_la_police_produite_couvre_tout_le_francais(tmp_path, source_amputee):
    """Le contrat de l'outil. Sans lui, chaque signe absent fait basculer TOUTE la bulle qui
    le contient sur une autre police, en silence — 63 bulles sur 818 mesurées sur le Vol.1
    de manga A, réparties sur 45 planches sur 150."""
    assert completer_police.manquants(source_amputee), "le cobaye doit être incomplet"
    sortie = tmp_path / "complete.ttf"
    completer_police.completer(source_amputee, sortie)
    assert completer_police.manquants(sortie) == ""


def test_les_accents_viennent_des_TRACES_de_la_police_elle_meme(tmp_path, source_amputee):
    """La technique préférée est la greffe INTERNE : l'accent est détaché d'un glyphe que la
    police possède déjà, puis reposé sur la capitale. C'est ce qui garde le style homogène,
    et ce qui évite de mélanger deux licences dans un même fichier."""
    faites, _ratees = completer_police.completer(source_amputee, tmp_path / "c.ttf")
    par_caractere = {f.caractere: f.technique for f in faites}
    for caractere in "ÀÇÄËÏÖÜÂÎÔÛÙ":
        assert par_caractere.get(caractere) == "greffe interne", caractere


def test_un_accent_est_repose_A_LA_HAUTEUR_DE_SA_LETTRE(tmp_path, source_amputee):
    """Défaut mesuré et corrigé : l'accent était repris tel quel de sa source. Un grave pris
    sur un `È` (ymax 796) puis posé sur un `A` (ymax 785) flottait 11 unités trop haut —
    assez pour se voir à 40 px. Il doit surplomber SA lettre, pas celle d'où il vient."""
    sortie = tmp_path / "c.ttf"
    completer_police.completer(source_amputee, sortie)
    police = TTFont(str(sortie))
    glyf, cmap = police["glyf"], police.getBestCmap()

    def sommet(caractere: str) -> int:
        glyphe = glyf[cmap[ord(caractere)]]
        glyphe.expand(glyf)
        return glyphe.yMax

    # `A` est plus bas que `E` dans presque toutes les polices ; leurs accents doivent
    # suivre le même écart, à une unité d'arrondi près.
    ecart_lettres = sommet("E") - sommet("A")
    ecart_accents = sommet("È") - sommet("À")
    assert abs(ecart_accents - ecart_lettres) <= 2


def test_ce_qui_ne_peut_PAS_etre_produit_est_dit(tmp_path, source_amputee, monkeypatch):
    """Une police de lettrage n'a pas à tout savoir dessiner — mais taire ce trou
    réinstallerait le silence que cet outil existe pour supprimer.

    ⚠ On neutralise AUSSI `polices_symboles` : sans ça le test ne mesure rien sous Windows,
    où Lucida Sans Unicode fournit ♪ et ♥ — et il passerait pour vert sur une CI Linux sans
    DejaVu, ce qui est exactement le skip silencieux que `tools/polices.py` a supprimé."""
    monkeypatch.setattr(completer_police, "polices_symboles", lambda *a, **k: ())
    sortie = tmp_path / "c.ttf"
    vide = tmp_path / "aucune.ttf"      # n'existe pas : `polices_de_secours` la filtre
    faites, ratees = completer_police.completer(
        source_amputee, sortie, bouche_trou=vide, guillemets="synthese")
    assert "♪" in ratees and "♥" in ratees
    assert all(f.technique != "greffe externe" for f in faites)
    # … et le reste a quand même été produit : un trou ne doit pas emporter le lot.
    assert {f.caractere for f in faites} >= set("ÀÇœ«»—")


def test_le_copyright_dorigine_est_CONSERVE(tmp_path, source_amputee):
    """Le fichier produit est un travail dérivé. On ajoute une mention de dérivation, on
    n'efface pas le copyright — cf. `NOTICE`, et la police que ce dépôt ne distribue pas."""
    sortie = tmp_path / "c.ttf"
    avant = TTFont(str(source_amputee))["name"].getDebugName(0)
    completer_police.completer(source_amputee, sortie, nom_famille="Cobaye Complet")
    apres = TTFont(str(sortie))["name"].getDebugName(0)
    assert avant and avant in apres
    assert apres != avant, "la dérivation doit être mentionnée"


def test_la_police_produite_change_de_NOM(tmp_path, source_amputee):
    """Lui laisser son nom ferait qu'une installation système écraserait l'une par l'autre,
    et que `RAPPORT.md` nommerait une police qui n'est pas celle qui a lettré."""
    sortie = tmp_path / "c.ttf"
    completer_police.completer(source_amputee, sortie, nom_famille="Cobaye Complet")
    noms = TTFont(str(sortie))["name"]
    assert noms.getDebugName(1) == "Cobaye Complet"
    assert noms.getDebugName(6) == "CobayeComplet"


def test_un_glyphe_COMPOSITE_est_greffe_avec_son_encre(tmp_path, source_amputee):
    """Défaut mesuré : le `«` de ComicNeue-Bold est un composite (deux `guilsinglleft`).
    Recopié tel quel dans une police qui n'a pas ce composant, il donnait un glyphe VIDE —
    la chasse était là, l'encre avait disparu, et rien ne le signalait."""
    sortie = tmp_path / "c.ttf"
    completer_police.completer(source_amputee, sortie, guillemets="greffe")
    police = TTFont(str(sortie))
    glyphe = police["glyf"][police.getBestCmap()[0x00AB]]
    glyphe.expand(police["glyf"])
    assert glyphe.numberOfContours > 0, "le guillemet greffé est vide"
    assert glyphe.xMax > glyphe.xMin


def test_les_metriques_generales_ne_bougent_pas(tmp_path, source_amputee):
    """On ajoute des glyphes, on ne redessine pas la police : `unitsPerEm` et les métriques
    verticales doivent être intactes, sans quoi tout le lettrage du tome se décalerait."""
    sortie = tmp_path / "c.ttf"
    completer_police.completer(source_amputee, sortie)
    avant, apres = TTFont(str(source_amputee)), TTFont(str(sortie))
    assert avant["head"].unitsPerEm == apres["head"].unitsPerEm
    assert (avant["hhea"].ascent, avant["hhea"].descent) == \
           (apres["hhea"].ascent, apres["hhea"].descent)
    # Les glyphes préexistants gardent leur chasse : seule l'addition est permise.
    for caractere in "AEIOUaeiou.,!?":
        nom_avant = avant.getBestCmap()[ord(caractere)]
        nom_apres = apres.getBestCmap()[ord(caractere)]
        assert avant["hmtx"][nom_avant] == apres["hmtx"][nom_apres], caractere


def test_la_police_produite_se_charge_dans_pillow(tmp_path, source_amputee):
    """Le vrai contrat de sortie : c'est Pillow qui lettre. Une police que fontTools sait
    écrire mais que Pillow refuse ferait échouer TOUT le rendu, planche après planche."""
    from PIL import ImageFont

    from manga.typeset import ALPHABET_FRANCAIS, glyphes_manquants
    sortie = tmp_path / "c.ttf"
    completer_police.completer(source_amputee, sortie)
    police = ImageFont.truetype(str(sortie), 24)
    assert police.getlength("À demain ! Ça alors ? « Œuf »") > 0
    # ⚠ Contrôle plus sévère que `manquants` : celui-ci compare le RENDU au `.notdef`, donc
    # il attrape un glyphe déclaré dans la `cmap` mais dessiné en carré tofu.
    assert glyphes_manquants(str(sortie), ALPHABET_FRANCAIS) == ""
