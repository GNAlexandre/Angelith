# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Contrôle de l'ordre de lecture persisté (`tools/verifier_ordre.py`), à 0 % jusqu'ici.

## Pourquoi ce fichier existe

L'outil est un DÉTECTEUR de défaut silencieux : sur un webtoon, une édition depuis
l'interface re-triait toute la planche en ordre manga, sans que le nombre de bulles, le
`sens` annoncé ni l'appariement texte↔bulle ne changent. Rien ne le signalait.

Un détecteur non testé est le pire des deux mondes : il rassure sans rien garantir. Trois
propriétés valent d'être figées ici, et la troisième est la plus dangereuse —

- une planche re-triée dans le mauvais sens est SIGNALÉE ;
- une planche dont les bulles sont empilées verticalement sort identique dans les deux sens :
  elle est déclarée saine mais **ambiguë**, parce que le contrôle n'y prouve rien ;
- `--corriger` est une PERMUTATION : l'OCR, les traductions, les corrections écrites à la
  main et les mises en page suivent leurs bulles. Une permutation qui oublierait un de ces
  dictionnaires creux ferait pointer une correction manuelle sur la mauvaise réplique — le
  défaut même que l'outil répare.
"""
from __future__ import annotations

import numpy as np
import pytest

from manga import checkpoints, document
from manga.detection import BubbleRegion
from tools import verifier_ordre as vo


def _region(bbox, taille=(200, 100)):
    x0, y0, x1, y1 = bbox
    masque = np.zeros((taille[1], taille[0]), dtype=bool)
    masque[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=bbox, mask=masque, score=0.9, cls=0)


@pytest.fixture
def planche(tmp_path):
    """Deux bulles CÔTE À CÔTE — la seule géométrie où le sens de lecture se voit."""
    def _fabriquer(sens, ordre=("gauche", "droite")):
        ckpt = checkpoints.page_checkpoint_dir(tmp_path / "manga", 1)
        ckpt.mkdir(parents=True, exist_ok=True)
        boites = {"gauche": (10, 10, 60, 60), "droite": (120, 10, 180, 60)}
        regions = [_region(boites[nom]) for nom in ordre]
        checkpoints.save_regions(ckpt, regions, (200, 100), sens=sens)
        checkpoints.save_ocr(ckpt, [f"jp-{nom}" for nom in ordre])
        checkpoints.save_traduction(ckpt, [f"fr-{nom}" for nom in ordre])
        return ckpt
    return _fabriquer


# --- verifier_planche ------------------------------------------------------------

def test_sans_cache_il_n_y_a_pas_de_verdict(tmp_path):
    """`None` et non « sain » : une planche jamais détectée n'a pas d'ordre à juger, et la
    compter comme saine gonflerait le dénominateur."""
    vide = tmp_path / "rien"
    vide.mkdir()
    assert vo.verifier_planche(vide) is None


def test_un_ordre_conforme_au_sens_declare_ne_deplace_rien(planche):
    """Droite→gauche (manga) : la bulle de droite d'abord. C'est l'ordre stocké."""
    ckpt = planche("droite_gauche", ordre=("droite", "gauche"))
    verdict = vo.verifier_planche(ckpt)
    assert verdict["sens"] == "droite_gauche"
    assert verdict["bulles"] == 2
    assert verdict["deplacees"] == []
    assert verdict["ambigue"] is False


def test_une_planche_retriee_dans_le_mauvais_sens_est_signalee(planche):
    """LE défaut que l'outil existe pour débusquer : `sens` annonce le webtoon, mais l'ordre
    stocké est celui du manga."""
    ckpt = planche("gauche_droite", ordre=("droite", "gauche"))
    verdict = vo.verifier_planche(ckpt)
    assert verdict["deplacees"], "une planche re-triée à l'envers doit ressortir fautive"
    assert sorted(verdict["perm"]) == [0, 1]


def test_des_bulles_empilees_sont_saines_mais_declarees_AMBIGUES(tmp_path):
    """⚠ La nuance qui empêche l'outil d'être rassurant à tort : un empilement vertical sort
    identique dans les deux sens. Son ordre est juste, mais le contrôle n'y prouve rien."""
    ckpt = checkpoints.page_checkpoint_dir(tmp_path / "manga", 1)
    ckpt.mkdir(parents=True)
    regions = [_region((10, 10, 60, 40)), _region((10, 60, 60, 90))]
    checkpoints.save_regions(ckpt, regions, (200, 100), sens="gauche_droite")
    verdict = vo.verifier_planche(ckpt)
    assert verdict["deplacees"] == []
    assert verdict["ambigue"] is True


# --- verifier_sfx ----------------------------------------------------------------

def test_sans_passe_hors_bulle_le_verdict_sfx_est_absent(planche):
    """`None` distingue « la passe n'a pas tourné » de « elle a tourné sans rien trouver » —
    deux états qu'un `0` confondrait."""
    ckpt = planche("droite_gauche")
    assert vo.verifier_sfx(ckpt, "droite_gauche") is None


def test_une_planche_sans_aucune_zone_hors_bulle_reste_sans_verdict(planche):
    ckpt = planche("droite_gauche")
    checkpoints.save_sfx(ckpt, [], [], (200, 100))
    assert vo.verifier_sfx(ckpt, "droite_gauche") is None


def test_les_zones_hors_bulle_sont_verifiees_contre_le_meme_sens(planche):
    """Le second ordre, celui du lot 13 : les onomatopées étaient triées EN DUR en
    droite→gauche. Sur webtoon, les bulles sortaient bonnes et les onomatopées à l'envers."""
    ckpt = planche("gauche_droite")
    zones = [_region((120, 10, 180, 60)), _region((10, 10, 60, 60))]   # droite puis gauche
    checkpoints.save_sfx(ckpt, zones, ["ドン", "バン"], (200, 100))
    verdict = vo.verifier_sfx(ckpt, "gauche_droite")
    assert verdict["zones"] == 2
    assert verdict["deplacees"], "l'ordre hors bulle doit suivre le sens déclaré lui aussi"

    conforme = vo.verifier_sfx(ckpt, "droite_gauche")
    assert conforme["deplacees"] == []


# --- corriger_planche ------------------------------------------------------------

def test_la_correction_emporte_ocr_traduction_et_corrections_manuelles(planche):
    """⚠ LE test de ce fichier. Une permutation qui oublierait `manuelles` ou
    `mises_en_page` — des dicts CREUX indexés par bulle — ferait pointer une correction
    écrite à la main sur la mauvaise réplique."""
    ckpt = planche("gauche_droite", ordre=("droite", "gauche"))
    etat = document.lire_etat(ckpt)
    etat.manuelles[0] = "ma version de la bulle de droite"
    etat.mises_en_page[0] = {"taille": 24}
    document.ecrire_etat(ckpt, etat, motif="test")

    vo.corriger_planche(ckpt, [1, 0])

    apres = document.lire_etat(ckpt)
    assert apres.ocr == ["jp-gauche", "jp-droite"]
    assert apres.traduction == ["fr-gauche", "fr-droite"]
    # L'ancienne bulle 0 occupe maintenant la position 1 : sa correction l'a suivie.
    assert apres.manuelles == {1: "ma version de la bulle de droite"}
    assert apres.mises_en_page == {1: {"taille": 24}}


def test_la_correction_remet_les_bulles_dans_l_ordre_attendu(planche):
    ckpt = planche("gauche_droite", ordre=("droite", "gauche"))
    verdict = vo.verifier_planche(ckpt)
    assert verdict["deplacees"]
    vo.corriger_planche(ckpt, verdict["perm"])
    assert vo.verifier_planche(ckpt)["deplacees"] == [], "la planche doit être saine après"


def test_une_permutation_invalide_est_refusee_avant_toute_ecriture(planche):
    """Une permutation qui n'en est pas une perdrait ou dupliquerait des bulles. Le refus
    doit précéder l'écriture, sinon l'état est déjà à moitié réécrit."""
    ckpt = planche("droite_gauche")
    avant = document.lire_etat(ckpt)
    for mauvaise in ([0, 0], [0], [0, 1, 2], [3, 4]):
        with pytest.raises(ValueError, match="permutation invalide"):
            vo.corriger_planche(ckpt, mauvaise)
    assert document.lire_etat(ckpt).ocr == avant.ocr


# --- sélection des chapitres -----------------------------------------------------

def test_sans_all_seul_le_tome_nomme_est_verifie():
    args = type("Args", (), {"tome": "Chap.11", "projet": "Mon Webtoon"})()
    assert vo._tomes(args, {}) == ["Chap.11"]


def test_all_enumere_les_chapitres_des_SOURCES(tmp_path, monkeypatch):
    """⚠ `sources/` et non `build/`, contrairement à `tools/banc.py` : cet outil peut
    CORRIGER, et une correction porte sur une œuvre qu'on possède."""
    sources = tmp_path / "sources"
    for nom in ("Chap.1", "Chap.2"):
        (sources / "Mon Webtoon" / nom).mkdir(parents=True)
    monkeypatch.setattr(vo._banc_commun, "racine_sources", lambda config: sources)
    args = type("Args", (), {"tome": None, "projet": "Mon Webtoon"})()
    assert vo._tomes(args, {}) == ["Chap.1", "Chap.2"]


# --- main() de bout en bout ------------------------------------------------------

@pytest.fixture
def tome_sur_disque(tmp_path, monkeypatch):
    """Un chapitre complet sous `build/`, avec `charger_config` et les racines détournées."""
    def _fabriquer(sens, ordre):
        build_root = tmp_path / "build"
        build_dir = build_root / "Mon Webtoon" / "Chap.1" / "manga"
        ckpt = checkpoints.page_checkpoint_dir(build_dir, 1)
        ckpt.mkdir(parents=True, exist_ok=True)
        boites = {"gauche": (10, 10, 60, 60), "droite": (120, 10, 180, 60)}
        regions = [_region(boites[nom]) for nom in ordre]
        checkpoints.save_regions(ckpt, regions, (200, 100), sens=sens)
        checkpoints.save_ocr(ckpt, [f"jp-{nom}" for nom in ordre])
        checkpoints.save_traduction(ckpt, [f"fr-{nom}" for nom in ordre])
        monkeypatch.setattr(vo, "charger_config", lambda chemin: {})
        monkeypatch.setattr(vo, "configurer_stdout", lambda: None)
        monkeypatch.setattr(vo._banc_commun, "racine_build", lambda config: build_root)
        monkeypatch.setattr(vo._banc_commun, "numeros_de_planches", lambda d: [1])
        return build_dir, ckpt
    return _fabriquer


def _lancer(monkeypatch, *argv):
    import sys
    monkeypatch.setattr(sys, "argv", ["verifier_ordre.py", *argv])
    return vo.main()


def test_main_sort_en_zero_quand_tout_est_conforme(tome_sur_disque, monkeypatch, capsys):
    tome_sur_disque("droite_gauche", ("droite", "gauche"))
    assert _lancer(monkeypatch, "Mon Webtoon", "Chap.1") == 0
    sortie = capsys.readouterr().out
    assert "sens déclaré : droite_gauche" in sortie
    assert "Total : 0 planche(s) à reprendre." in sortie


def test_main_sort_en_un_et_nomme_la_page_fautive(tome_sur_disque, monkeypatch, capsys):
    """Le code de sortie est ce qu'un script d'intégration lit : une planche à reprendre
    doit faire échouer la commande, pas seulement s'imprimer."""
    tome_sur_disque("gauche_droite", ("droite", "gauche"))
    assert _lancer(monkeypatch, "Mon Webtoon", "Chap.1") == 1
    sortie = capsys.readouterr().out
    assert "⚠ page 1" in sortie
    assert "À REPRENDRE" in sortie
    assert "--corriger" in sortie, "le message doit dire comment réparer"


def test_main_corrige_et_conserve_les_textes(tome_sur_disque, monkeypatch, capsys):
    _build, ckpt = tome_sur_disque("gauche_droite", ("droite", "gauche"))
    assert _lancer(monkeypatch, "Mon Webtoon", "Chap.1", "--corriger") == 1
    sortie = capsys.readouterr().out
    assert "remise dans l'ordre" in sortie
    assert "--from rendu" in sortie, "le rendu est à refaire, et le message doit le dire"
    apres = document.lire_etat(ckpt)
    assert apres.ocr == ["jp-gauche", "jp-droite"]
    assert vo.verifier_planche(ckpt)["deplacees"] == []


def test_main_signale_les_zones_hors_bulle_sans_proposer_de_les_corriger(
        tome_sur_disque, monkeypatch, capsys):
    """⚠ Pas de `--corriger` pour les onomatopées : trois fichiers indexés séparément,
    contre un seul état de planche du côté des bulles."""
    _build, ckpt = tome_sur_disque("gauche_droite", ("gauche", "droite"))
    zones = [_region((120, 10, 180, 60)), _region((10, 10, 60, 60))]
    checkpoints.save_sfx(ckpt, zones, ["ドン", "バン"], (200, 100))
    assert _lancer(monkeypatch, "Mon Webtoon", "Chap.1") == 1
    sortie = capsys.readouterr().out
    assert "texte hors bulle" in sortie
    assert "relancer la passe" in sortie


def test_main_exige_un_tome_ou_all(monkeypatch):
    with pytest.raises(SystemExit):
        _lancer(monkeypatch, "Mon Webtoon")


def test_un_tome_sans_checkpoints_est_saute_sans_planter(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vo, "charger_config", lambda chemin: {})
    monkeypatch.setattr(vo, "configurer_stdout", lambda: None)
    monkeypatch.setattr(vo._banc_commun, "racine_build", lambda config: tmp_path / "build")
    assert _lancer(monkeypatch, "Mon Webtoon", "Chap.42") == 0
    assert "Total : 0" in capsys.readouterr().out
