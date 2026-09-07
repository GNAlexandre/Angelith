# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le dépôt guidé — `gui/depot_guide.py` (lot 34, L34.3).

**Sans PySide6.** Tout le parcours d'un lâcher — la lecture, la destination, la collision, le
refus d'un `.cbr` sans `unrar` — se teste sans écran ; la boîte de dialogue ne fait que
montrer ce que ces fonctions rendent.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from gui import depot_guide as dg
from manga import creation_projet as crea


def _config(racine: Path) -> dict:
    return {"chemins": {"sources": str(racine / "sources"), "build": str(racine / "build")},
            "langues": {"dossiers": {"ENG": "en", "JAP": "jp"}}}


def _images(dossier: Path, n: int, octets: int = 10) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (dossier / f"{i:03d}.png").write_bytes(b"\0" * octets)
    return dossier


def _cbz(chemin: Path, images: int, *, autres: int = 0) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(chemin, "w") as zf:
        for i in range(1, images + 1):
            zf.writestr(f"pages/{i:03d}.jpg", b"\0" * 32)
        for i in range(autres):
            zf.writestr(f"lisezmoi_{i}.txt", "x")
    return chemin


# --------------------------------------------------------------------------- #
#  1. Ce que j'ai lu
# --------------------------------------------------------------------------- #

def test_un_dossier_d_images_est_lu_avec_ses_comptes_et_son_poids(tmp_path):
    dossier = _images(tmp_path / "Mon Manga - Vol.3", 5, octets=100)
    lecture = dg.lire([dossier])
    assert len(lecture.fichiers) == 5
    assert lecture.images == 5
    assert lecture.planches == 5
    assert lecture.octets == 500
    assert lecture.extensions == {".png": 5}
    assert "5 fichier(s)" in lecture.resume and "5 planche(s)" in lecture.resume


def test_une_archive_est_comptee_SANS_etre_extraite(tmp_path, monkeypatch):
    """⚠ Le point du L34.3 : « son contenu listé sans l'extraire ». Un `.cbz` de 230 Mo ne
    doit pas être déplié pour afficher la première ligne du parcours."""
    from manga import ingest

    def _interdit(*_a, **_k):
        raise AssertionError("l'archive a été extraite")

    monkeypatch.setattr(ingest, "extract_archive", _interdit)
    archive = _cbz(tmp_path / "Mon Manga - Vol.3.cbz", 42, autres=2)
    lecture = dg.lire([archive])
    assert len(lecture.archives) == 1
    assert lecture.archives[0].images == 42          # les 2 .txt ne comptent pas
    assert lecture.archives[0].lisible
    assert lecture.planches == 42
    assert "42 image(s)" in lecture.archives[0].libelle
    assert not (tmp_path / "pages").exists()


def test_une_archive_corrompue_est_dite_illisible_et_bloque_l_import(tmp_path):
    archive = tmp_path / "casse.cbz"
    archive.write_bytes(b"ce n'est pas un zip")
    lecture = dg.lire([archive])
    assert lecture.archives[0].lisible is False
    assert lecture.planches is None                  # ⚠ pas zéro : on ne SAIT pas
    assert lecture.avertissements


def test_le_projet_et_le_tome_sont_preremplis_par_ce_qui_a_ete_lu(tmp_path):
    archive = _cbz(tmp_path / "Mon Manga - Vol.3.cbz", 3)
    lecture = dg.lire([archive])
    assert lecture.projet_propose == "Mon Manga"
    assert lecture.tome_propose == "Vol.3"

    dossier = _images(tmp_path / "Autre Manga" / "Vol.7", 2)
    lecture = dg.lire([dossier])
    assert (lecture.projet_propose, lecture.tome_propose) == ("Autre Manga", "Vol.7")


def test_le_format_webtoon_est_deduit_du_chemin_jamais_des_pixels(tmp_path):
    plat = _images(tmp_path / "A" / "Chap.1" / "manga", 2)
    assert dg.lire([plat]).format_propose == "manga"
    bande = _images(tmp_path / "B" / "Chap.1" / "webtoon", 2)
    assert dg.lire([bande]).format_propose == "webtoon"


def test_un_lacher_sans_rien_de_lisible_le_dit(tmp_path):
    dossier = tmp_path / "documents"
    dossier.mkdir()
    (dossier / "notes.pdf").write_text("x", encoding="utf-8")
    lecture = dg.lire([dossier])
    assert lecture.fichiers == ()
    assert lecture.avertissements
    assert "Rien de lisible" in lecture.resume


# --------------------------------------------------------------------------- #
#  2-4. Où ça va, et ce qui s'y trouve déjà
# --------------------------------------------------------------------------- #

def test_une_oeuvre_neuve_est_annoncee_comme_telle(tmp_path):
    destination = dg.preparer(_config(tmp_path), "Neuve", "Vol.1")
    assert destination.projet_existe is False
    assert destination.bloquant is False
    assert "Nouvelle œuvre" in destination.message
    assert destination.dossier.name == "manga"
    assert not destination.dossier.exists(), "preparer() ne doit RIEN créer"


def test_un_tome_ajoute_a_une_oeuvre_existante_est_annonce_comme_tel(tmp_path):
    config = _config(tmp_path)
    _images(tmp_path / "sources" / "Existante" / "Vol.1" / "manga", 2)
    destination = dg.preparer(config, "Existante", "Vol.2")
    assert destination.projet_existe and not destination.tome_existe
    assert "Nouveau tome" in destination.message


def test_la_collision_est_NOMMEE_et_jamais_silencieuse(tmp_path):
    """Critère 7 : « un tome qui existe déjà n'est pas écrasé en silence »."""
    config = _config(tmp_path)
    _images(tmp_path / "sources" / "Existante" / "Vol.1" / "manga", 7)
    destination = dg.preparer(config, "Existante", "Vol.1")
    assert destination.tome_existe
    assert destination.fichiers_presents == 7
    assert "DÉJÀ 7 planche(s)" in destination.message
    # ⚠ Nommée, mais pas bloquante : `creation_projet.copier` renumérote les doublons plutôt
    # que d'écraser. Bloquer priverait d'un ajout légitime à un tome incomplet.
    assert destination.bloquant is False


def test_un_nom_refuse_bloque_avec_la_raison(tmp_path):
    destination = dg.preparer(_config(tmp_path), "Mon/Projet", "Vol.1")
    assert destination.bloquant
    assert "caractère interdit" in destination.message


def test_la_validation_est_celle_de_creation_projet(tmp_path):
    """Revalider avec une règle recopiée ferait accepter dans la boîte ce que la copie
    refuserait ensuite."""
    for nom in ("CON", "fin.", "x" * 101):
        destination = dg.preparer(_config(tmp_path), nom, "Vol.1")
        assert destination.bloquant
        with pytest.raises(crea.ErreurCreation):
            crea.valider_nom(nom, "nom de projet")


# --------------------------------------------------------------------------- #
#  5. Le plan, le coût, le refus
# --------------------------------------------------------------------------- #

def test_le_plan_annonce_le_cout_avant_le_premier_octet(tmp_path):
    config = _config(tmp_path)
    _images(tmp_path / "Mon Manga - Vol.3", 4, octets=1024)
    plan = dg.planifier(config, [tmp_path / "Mon Manga - Vol.3"])
    assert plan.executable
    assert "4 fichier(s)" in plan.annonce
    assert "4 ko" in plan.annonce
    assert "copié" in plan.annonce
    assert str(plan.destination.dossier) in plan.annonce


def test_copier_est_le_defaut_et_deplacer_se_demande(tmp_path):
    """Critère 7 : « copie par défaut, ne déplace que sur une case explicitement cochée »."""
    config = _config(tmp_path)
    _images(tmp_path / "src", 2)
    assert dg.planifier(config, [tmp_path / "src"]).deplacer is False
    assert "copié" in dg.planifier(config, [tmp_path / "src"]).annonce
    bouge = dg.planifier(config, [tmp_path / "src"], deplacer=True)
    assert bouge.deplacer is True
    assert "DÉPLACÉ" in bouge.annonce


def test_copier_par_defaut_laisse_la_source_intacte(tmp_path):
    config = _config(tmp_path)
    source = _images(tmp_path / "src", 3)
    crea.creer(config, "Œuvre", "Vol.1", [source])
    assert len(list(source.glob("*.png"))) == 3
    cible = crea.dossier_cible(config, "Œuvre", "Vol.1")
    assert len(list(cible.glob("*.png"))) == 3


def test_deplacer_vide_bien_le_dossier_d_origine(tmp_path):
    config = _config(tmp_path)
    source = _images(tmp_path / "src", 3)
    crea.creer(config, "Œuvre", "Vol.1", [source], deplacer=True)
    assert list(source.glob("*.png")) == []
    cible = crea.dossier_cible(config, "Œuvre", "Vol.1")
    assert len(list(cible.glob("*.png"))) == 3


def test_un_cbr_sans_outil_est_refuse_AVANT_l_import(tmp_path, monkeypatch):
    """Critère 7, dernier point. ⚠ Aujourd'hui l'échec remonte en `SystemExit` depuis
    `manga/ingest.py`, c'est-à-dire au milieu de la copie, après que l'utilisateur a nommé
    son projet."""
    monkeypatch.setattr(dg, "outil_rar",
                        lambda: dg.OutilRar(False, motif="l'outil externe « unrar » est "
                                                         "introuvable dans le PATH."))
    archive = tmp_path / "Mon Manga - Vol.3.cbr"
    archive.write_bytes(b"Rar!\x1a\x07\x00")
    plan = dg.planifier(_config(tmp_path), [archive])
    assert plan.refus
    assert "unrar" in plan.refus
    assert not plan.executable or plan.refus     # le bouton reste désarmé


def test_un_cbr_avec_outil_ne_bloque_pas_sur_l_absence_d_outil(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "outil_rar", lambda: dg.OutilRar(True, outil="unrar"))
    archive = tmp_path / "Mon Manga - Vol.3.cbr"
    archive.write_bytes(b"Rar!\x1a\x07\x00")
    plan = dg.planifier(_config(tmp_path), [archive])
    # L'archive reste illisible (ce n'est pas un vrai RAR), mais le motif ne parle plus de
    # l'outil manquant : on distingue « je ne peux pas lire les .cbr » de « ce .cbr est
    # cassé », et les deux n'appellent pas le même geste.
    assert "unrar" not in plan.refus


def test_outil_rar_dit_pourquoi_quand_il_dit_non(monkeypatch):
    """⚠ On double `core.diagnostic`, pas `gui.depot_guide` — lot 38.

    Ce test doublait `dg.shutil.which`, parce que le module cherchait l'exécutable lui-même.
    Il ne le cherche plus : il appelle `core.diagnostic.verdict_outil_externe`, la fonction du
    lot 36 qui était restée sans appelant en production. L'endroit où l'on double dit où vit
    la décision, et c'est bien ce que ce lot déplace."""
    from core import diagnostic as diag
    monkeypatch.setattr(diag.shutil, "which", lambda _nom: None)
    etat = dg.outil_rar()
    assert etat.disponible is False
    assert etat.motif
    assert "indisponible" in etat.message


def test_le_remede_du_cbr_vient_du_catalogue_de_reparations(monkeypatch):
    """Le motif ne réécrit plus le remède : il le lit là où la page Diagnostic le lit.

    Deux textes pour le même manque finissent par en dire deux choses — c'est exactement ce
    qui est arrivé aux licences de poids dans ce dépôt (lot 38).

    ⚠ **`rarfile` est POSÉ, il n'est pas supposé présent** — lot 42. La chaîne `.cbr` a deux
    maillons, et `outil_rar` rend le premier motif venu : sans `rarfile`, elle sort avant
    d'avoir regardé l'outil externe, et ce test-ci vérifiait alors une phrase qui n'a rien à
    voir avec le catalogue.

    Il passait sur une machine de développement (où `rarfile` est installé) et échouait en
    intégration continue, qui n'installe pas `requirements-manga.txt` — constaté le 2026-09-07,
    reproduit dans un environnement neuf. Un test dont le verdict dépend de ce qui traîne dans
    l'environnement ne mesure pas ce qu'il annonce."""
    import sys
    import types

    from core import diagnostic as diag
    from core import reparations as rep
    monkeypatch.setitem(sys.modules, "rarfile", types.ModuleType("rarfile"))
    monkeypatch.setattr(diag.shutil, "which", lambda _nom: None)
    etat = dg.outil_rar()
    reparation = rep.par_identifiant("unrar")
    assert reparation is not None
    assert reparation.consigne() in etat.motif


def test_sans_rarfile_le_motif_nomme_le_fichier_de_dependances(monkeypatch):
    """L'autre maillon, et il mérite son test plutôt que d'être le hasard du précédent : sans
    le paquet Python, le remède n'est pas d'installer un outil externe."""
    import sys

    monkeypatch.setitem(sys.modules, "rarfile", None)
    etat = dg.outil_rar()
    assert etat.disponible is False
    assert "requirements-manga.txt" in etat.motif


def test_un_lacher_vide_n_est_pas_executable(tmp_path):
    plan = dg.planifier(_config(tmp_path), [])
    assert not plan.executable
    assert plan.refus
