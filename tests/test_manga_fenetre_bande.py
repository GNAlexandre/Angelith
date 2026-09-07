# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`--fenetre-hauteur` / `--fenetre-recouvrement` — **le câblage, pas la détection**.

## Pourquoi ce fichier existe

Ces deux options sont nées au lot 31 pour une raison qui n'est pas d'abord une raison de
ligne de commande : le `PLAN-31` L31.7 demande que la destination « Webtoon » remonte les
réglages de bande, et `gui/__init__.py` promet qu'« un tome retouché ici se relance à
l'identique avec `run_manga.py` ». Un champ dans un panneau sans drapeau équivalent aurait
cassé cette promesse ; les deux existent donc **des deux côtés**, et ce fichier vérifie que
les deux écrivent au **même endroit**.

⚠ **Le défaut que ce fichier empêche est celui du correctif 2.24.1** : `--liberer-vram` était
testé côté protocole, jamais côté COMMANDE, et mourait sur un `TypeError` avant le premier
appel. `grep -rn "liberer_vram" tests/` ne rendait rien. Ici, ce qui est vérifié est
exactement la chaîne `argparse → config → manga/formats.config_format`.

## Ce que ce fichier ne teste PAS

Rien de ce que la détection FAIT de ces valeurs. Le découpage lui-même, le rabotage à 80 % et
le rejet des détections coupées par une couture sont couverts par
`tests/test_manga_detection.py` et `tests/test_manga_webtoon.py`, qui chargent le modèle.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_manga as rm
from manga import formats as fmt_mod

RACINE = Path(__file__).resolve().parent.parent


def _config() -> dict:
    """Le strict nécessaire : `manga.detection` porte les défauts livrés."""
    return {"manga": {"detection": {"fenetre_hauteur": 2160, "fenetre_recouvrement": 900},
                      "lot": {}}}


def _args(**over):
    base = dict(dry_run=False, verbose=False, lot=None, think=None,
                fenetre_hauteur=None, fenetre_recouvrement=None, format_planche=None)
    base.update(over)
    return SimpleNamespace(**base)


def _parser():
    """Un vrai `ArgumentParser` : `ap.error` doit lever `SystemExit`, pas être doublé."""
    return argparse.ArgumentParser(prog="run_manga.py", exit_on_error=False)


# --------------------------------------------------------------------------- #
# Les deux drapeaux existent et se parsent
# --------------------------------------------------------------------------- #

def test_les_deux_drapeaux_existent_ET_l_aide_se_formate():
    """**Le test qui aurait attrapé le défaut de 2.24.1**, et il lance la VRAIE commande.

    Deux choses dans un seul `--help`, parce qu'elles échouent à deux moments différents :

    1. **la déclaration** — les deux options apparaissent dans l'usage, donc `argparse` les
       connaît. C'est ce qui manquait à `--liberer-vram`, testé côté protocole et jamais côté
       COMMANDE, et qui mourait sur un `TypeError` avant le premier appel ;
    2. **le formatage** — un `%` littéral non doublé dans un texte d'aide ne lève pas à la
       déclaration mais au `--help`. Le premier jet de ce lot portait « 80 % de la hauteur »,
       et `python run_manga.py --help` mourait sur
       `TypeError: %d format: a real number is required, not dict` : l'aide de tout le
       programme cassée par un texte d'aide.
    """
    sortie = subprocess.run(
        [sys.executable, str(RACINE / "run_manga.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(RACINE), timeout=180)
    assert sortie.returncode == 0, sortie.stderr[-2000:]
    assert "--fenetre-hauteur" in sortie.stdout
    assert "--fenetre-recouvrement" in sortie.stdout
    assert "833" in sortie.stdout, "l'aide cite la mesure qui justifie la borne basse"


def test_une_valeur_hors_bornes_est_refusee_par_la_VRAIE_commande():
    """Une borne qui ne se vérifie qu'en test unitaire n'est pas une borne de commande."""
    sortie = subprocess.run(
        [sys.executable, str(RACINE / "run_manga.py"), "Projet", "Vol.1",
         "--fenetre-hauteur", "12"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(RACINE), timeout=180)
    assert sortie.returncode != 0
    assert "fenetre-hauteur" in (sortie.stderr + sortie.stdout)


# --------------------------------------------------------------------------- #
# Où les valeurs atterrissent
# --------------------------------------------------------------------------- #

def test_sans_format_les_valeurs_vont_dans_manga_detection():
    config = _config()
    rm._appliquer_options_bande(_parser(), _args(fenetre_hauteur=3000), config)
    assert config["manga"]["detection"]["fenetre_hauteur"] == 3000
    assert config["manga"]["detection"]["fenetre_recouvrement"] == 900, "l'autre ne bouge pas"


def test_avec_un_format_les_valeurs_vont_dans_le_bloc_du_format():
    """⚠ **Au niveau le plus PRÉCIS que le run va lire.** `config_format` fusionne
    `manga.detection` avec `manga.formats.<format>.detection`, le second l'emportant : écrire
    toujours dans le premier laisserait un bloc de format ajouté demain écraser silencieusement
    l'option de la ligne de commande."""
    config = _config()
    rm._appliquer_options_bande(
        _parser(), _args(fenetre_hauteur=3000, fenetre_recouvrement=1200,
                         format_planche="webtoon"), config)
    propre = config["manga"]["formats"]["webtoon"]["detection"]
    assert propre == {"fenetre_hauteur": 3000, "fenetre_recouvrement": 1200}
    # …et c'est bien ce que le run lira.
    resolu = fmt_mod.config_format(config, "webtoon", "detection")
    assert (resolu["fenetre_hauteur"], resolu["fenetre_recouvrement"]) == (3000, 1200)


def test_le_format_manga_n_est_pas_touche_par_un_reglage_de_webtoon():
    """Le sens de tout l'exercice : un réglage de bande est un réglage de BANDE."""
    config = _config()
    rm._appliquer_options_bande(
        _parser(), _args(fenetre_hauteur=3000, format_planche="webtoon"), config)
    resolu = fmt_mod.config_format(config, "manga", "detection")
    assert resolu["fenetre_hauteur"] == 2160


def test_sans_option_rien_n_est_ecrit():
    """« Ne pas poser la clé du tout est différent de poser sa valeur par défaut. »"""
    config = _config()
    rm._appliquer_options_bande(_parser(), _args(format_planche="webtoon"), config)
    assert "formats" not in config["manga"]


def test_les_options_de_bande_passent_par_le_meme_point_que_lot_et_think():
    """`_appliquer_options_lot` est le point unique que `--all` et l'interface partagent —
    « deux copies auraient fini par diverger »."""
    config = _config()
    rm._appliquer_options_lot(
        _parser(), _args(fenetre_hauteur=2560, format_planche="webtoon"), config)
    assert config["manga"]["formats"]["webtoon"]["detection"]["fenetre_hauteur"] == 2560


# --------------------------------------------------------------------------- #
# Les bornes — elles refusent au lieu de laisser produire un résultat absurde
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("hauteur", [0, 100, 511, 20001, 999999])
def test_une_hauteur_hors_bornes_est_refusee(hauteur):
    with pytest.raises(SystemExit):
        rm._appliquer_options_bande(_parser(), _args(fenetre_hauteur=hauteur), _config())


def test_un_recouvrement_negatif_est_refuse():
    with pytest.raises(SystemExit):
        rm._appliquer_options_bande(_parser(), _args(fenetre_recouvrement=-1), _config())


def test_un_recouvrement_au_moins_egal_a_la_hauteur_est_refuse():
    """⚠ À l'égalité le pas tombe à zéro. `manga/detection.py` rabote de toute façon au-delà
    de 80 % — « un recouvrement de 2159 px sur 2160 produirait 7 841 fenêtres pour une seule
    bande » — mais un refus à la ligne de commande dit *pourquoi*, et tout de suite."""
    with pytest.raises(SystemExit):
        rm._appliquer_options_bande(
            _parser(), _args(fenetre_hauteur=1000, fenetre_recouvrement=1000), _config())


def test_la_coherence_croise_l_option_donnee_et_le_fichier():
    """On peut n'en donner qu'une : c'est alors `config.yaml` qui fournit la seconde borne.

    Ici la hauteur descend à 800 alors que le fichier porte un recouvrement de 900 — la paire
    résultante est incohérente, et c'est cette paire-là qu'il faut refuser, pas l'option."""
    with pytest.raises(SystemExit):
        rm._appliquer_options_bande(_parser(), _args(fenetre_hauteur=800), _config())


def test_les_bornes_acceptent_les_valeurs_du_depot():
    """Les défauts livrés doivent évidemment passer, et la borne basse est justifiée par la
    plus haute bulle mesurée du corpus."""
    config = _config()
    rm._appliquer_options_bande(
        _parser(), _args(fenetre_hauteur=2160, fenetre_recouvrement=900), config)
    assert config["manga"]["detection"]["fenetre_hauteur"] == 2160
    assert rm.PLUS_HAUTE_BULLE == 833
