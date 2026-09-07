# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le tome de démonstration (`manga/demonstration.py`) — **critère 9 du `PLAN-36`**.

« « Créer un tome de démonstration » produit un tome utilisable de bout en bout, marqué comme
démonstration, supprimable, et se refuse **proprement** si la police nécessaire manque. »

Quatre propriétés, quatre familles de tests. La quatrième est la plus importante et la plus
facile à rater : `tests/conftest.py` a le droit de *skipper* quand la police manque, une
application livrée à quelqu'un ne l'a pas. Un refus muet, ou une planche en tofu, feraient
croire à un défaut d'Angelith.

⚠ Aucun test ici n'appelle de LLM ni ne charge de poids ONNX : c'est tout l'intérêt du tome,
et donc de ses tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from manga import demonstration as demo


@pytest.fixture()
def config(tmp_path: Path) -> dict:
    return {"chemins": {"sources": str(tmp_path / "sources"),
                        "build": str(tmp_path / "build")}}


# --------------------------------------------------------------------------- #
#  Il produit un tome utilisable
# --------------------------------------------------------------------------- #

def test_il_ecrit_des_planches_et_leurs_checkpoints(config):
    """⚠ Les checkpoints sont écrits **d'avance** — régions, OCR, traduction, page nettoyée —
    pour que la retouche et le rendu marchent sans qu'aucun modèle ne soit installé ni
    joignable. C'est ce qui rend le geste utile sur une installation neuve."""
    from manga import checkpoints

    tome = demo.creer(config)
    assert len(tome.planches) == demo.PLANCHES
    for planche in tome.planches:
        assert planche.is_file()
    for indice in range(1, demo.PLANCHES + 1):
        ckpt = checkpoints.page_checkpoint_dir(tome.build, indice)
        assert checkpoints.load_ocr(ckpt), f"page {indice} sans OCR"
        assert checkpoints.clean_page_path(tome.build, indice).is_file()


def test_les_traductions_sont_ecrites_d_avance_donc_sans_LLM(config):
    """Le tome doit être retouchable et rendable **sans qu'aucun LLM ne soit joignable**, ce
    qui est précisément l'état d'une installation neuve."""
    from manga import checkpoints

    tome = demo.creer(config)
    textes = checkpoints.load_traduction(
        checkpoints.page_checkpoint_dir(tome.build, 1))
    assert textes and all(t.strip() for t in textes)


def test_le_projet_json_est_ecrit_donc_la_bibliotheque_le_voit(config):
    tome = demo.creer(config)
    assert (tome.build / "projet.json").is_file()


# --------------------------------------------------------------------------- #
#  Il est marqué comme démonstration
# --------------------------------------------------------------------------- #

def test_le_dossier_porte_un_marqueur_lisible_a_la_main(config):
    """⚠ « Un utilisateur ne doit jamais confondre le tome de démonstration avec une œuvre. »
    Le marqueur est lu par le programme ET par quelqu'un qui tombe dessus dans l'explorateur."""
    tome = demo.creer(config)
    marqueur = tome.sources / demo.MARQUEUR
    assert marqueur.is_file()
    texte = marqueur.read_text(encoding="utf-8")
    assert "DÉMONSTRATION" in texte
    assert "aucune œuvre" in texte
    assert "supprimer" in texte


def test_le_nom_du_projet_le_range_en_tete_et_ne_ressemble_a_aucune_oeuvre():
    """Le tiret bas de tête n'est pas décoratif : il range le dossier avant toutes les œuvres
    dans un tri alphabétique."""
    assert demo.PROJET.startswith("_")
    assert "monstration" in demo.PROJET


def test_existe_repose_sur_le_marqueur_et_pas_sur_le_dossier(config):
    """Un dossier vide créé à la main ne doit pas passer pour une démonstration."""
    assert demo.existe(config) is False
    demo.dossier_sources(config).mkdir(parents=True)
    assert demo.existe(config) is False, "un dossier nu n'est pas une démonstration"
    demo.creer(config, ecraser=True)
    assert demo.existe(config) is True


# --------------------------------------------------------------------------- #
#  Il est supprimable, et il ne peut effacer que lui-même
# --------------------------------------------------------------------------- #

def test_il_se_supprime_entierement_sources_et_build(config):
    demo.creer(config)
    effaces = demo.supprimer(config)
    assert len(effaces) == 2
    assert demo.existe(config) is False
    assert not demo.dossier_sources(config).exists()
    assert not demo.dossier_build(config).exists()


def test_supprimer_ne_touche_a_aucune_autre_oeuvre(config):
    """⚠ **Le garde-fou.** Une fonction qui efface un dossier de `sources/` doit être incapable
    d'effacer autre chose que ce qu'elle a créé — même principe que
    `illustration/frontiere.py`, qui refuse à l'exécution toute écriture hors du dossier de sa
    brique."""
    oeuvre = Path(config["chemins"]["sources"]) / "Une Œuvre" / "Vol.1"
    oeuvre.mkdir(parents=True)
    (oeuvre / "page.png").write_bytes(b"x")
    demo.creer(config)
    demo.supprimer(config)
    assert (oeuvre / "page.png").is_file(), "une œuvre a été emportée"


def test_supprimer_sur_une_installation_sans_demonstration_ne_leve_pas(config):
    assert demo.supprimer(config) == []


def test_creer_deux_fois_refuse_sans_ecraser_explicite(config):
    demo.creer(config)
    with pytest.raises(FileExistsError):
        demo.creer(config)
    demo.creer(config, ecraser=True)      # le geste explicite passe


# --------------------------------------------------------------------------- #
#  ⚠ Il se refuse PROPREMENT quand la police manque — `PLAN-20` L20.2
# --------------------------------------------------------------------------- #

def test_sans_police_le_geste_se_refuse_en_disant_pourquoi(config, monkeypatch):
    """⚠ **Le test qui compte.** `tests/conftest.py` *skippe* quand la police manque ; une
    application livrée à quelqu'un ne le peut pas. Le message doit nommer la variable
    d'environnement, les candidats essayés et la commande d'installation."""
    monkeypatch.setattr("tools.polices.police_japonaise", lambda *a, **k: None)
    with pytest.raises(demo.PoliceIndisponible) as echec:
        demo.creer(config)
    message = str(echec.value)
    assert "ANGELITH_POLICE_JP" in message
    assert "Candidats essayés" in message
    assert "installer" in message.lower()


def test_un_refus_de_police_ne_laisse_RIEN_sur_le_disque(config, monkeypatch):
    """⚠ « La police est résolue AVANT d'écrire quoi que ce soit : un refus doit laisser le
    disque exactement comme il était, pas un dossier à moitié rempli. » Un demi-tome serait
    pire que pas de tome : il passerait `existe()` et donnerait une retouche vide."""
    monkeypatch.setattr("tools.polices.police_japonaise", lambda *a, **k: None)
    with pytest.raises(demo.PoliceIndisponible):
        demo.creer(config)
    assert not demo.dossier_sources(config).exists()
    assert demo.existe(config) is False


def test_un_refus_de_police_ne_detruit_pas_un_tome_existant(config, monkeypatch):
    """Le cas vicieux : « Refaire » avec une police qui vient de disparaître ne doit pas
    laisser l'utilisateur sans rien."""
    demo.creer(config)
    monkeypatch.setattr("tools.polices.police_japonaise", lambda *a, **k: None)
    with pytest.raises(demo.PoliceIndisponible):
        demo.creer(config, ecraser=True)
    assert demo.existe(config) is True


def test_une_police_illisible_est_traitee_comme_une_police_absente(config, monkeypatch,
                                                                   tmp_path):
    """Un fichier présent mais illisible (tronqué, mauvais format) doit produire le même refus
    explicite qu'une absence — pas une exception Pillow que personne ne sait lire."""
    faux = tmp_path / "pas_une_police.ttf"
    faux.write_bytes(b"ceci n'est pas une police")
    monkeypatch.setattr("tools.polices.police_japonaise", lambda *a, **k: faux)
    with pytest.raises(demo.PoliceIndisponible):
        demo.creer(config)


# --------------------------------------------------------------------------- #
#  Les chemins viennent de config.yaml, sans défaut inventé
# --------------------------------------------------------------------------- #

def test_les_racines_viennent_de_config_yaml(config):
    assert demo.racine_sources(config) == Path(config["chemins"]["sources"])
    assert demo.racine_build(config) == Path(config["chemins"]["build"])


def test_les_racines_ont_les_memes_defauts_que_le_reste_du_programme():
    assert demo.racine_sources({}) == Path("sources")
    assert demo.racine_build({}) == Path("build")
