# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`import_build.py` — réintégrer un tome corrigé par un tiers, sans rien perdre.

## Ce que ces tests protègent

Un import écrit dans `build/`, c'est-à-dire là où vivent des heures de GPU. Trois propriétés,
et chacune a son test :

1. **rien n'est écrit tant qu'on ne l'a pas demandé** — `planifier()` ne fait que lire ;
2. **rien n'est supprimé**, jamais : une planche présente ici et absente du paquet reste ;
3. **rien n'est écrasé sans sauvegarde** — l'ancienne version part dans
   `.avant-import-<date>/` avant que la nouvelle ne s'écrive.

## ⚠ Le refus qui compte, et pourquoi il ne passe pas par `checkpoint_format`

L'ordre persisté dans `regions.json` est le **pivot** : `ocr.json` et `traduction.json` s'y
alignent par POSITION. Installer un cache d'une autre version ferait atterrir les traductions
dans les mauvaises bulles, silencieusement.

`checkpoints.checkpoint_format` exige `regions.json` **et** `masks.png` — elle répond à « puis-je
charger ce cache ? ». Un paquet sans `masks.png` la ferait donc répondre `None`, et le
garde-fou serait **contourné en silence**. `import_build` lit la version dans le JSON, avec la
même règle tolérante (liste nue = v1).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import import_build as imp
from manga import checkpoints as ck


def _tome(racine: Path, nom: str, textes: list[str], *,
          version: int = ck.FORMAT_VERSION, projet: str = "Oeuvre",
          tome: str = "Vol.1") -> Path:
    """Un `build/<P>/<T>/manga/` minimal mais réaliste."""
    dossier = racine / nom / "manga"
    for index, texte in enumerate(textes, 1):
        page = dossier / ".checkpoints" / f"page_{index:04d}"
        page.mkdir(parents=True)
        (page / "regions.json").write_text(
            json.dumps({"format": version, "image_size": [10, 10], "regions": []}),
            encoding="utf-8")
        (page / "traduction.json").write_text(json.dumps([texte]), encoding="utf-8")
    (dossier / "projet.json").write_text(
        json.dumps({"format": 1, "projet": projet, "tome": tome, "outil": "x",
                    "revision": 1, "pages": []}), encoding="utf-8")
    return dossier


@pytest.fixture
def local(tmp_path) -> Path:
    return _tome(tmp_path, "local", ["A", "B", "C"])


# --------------------------------------------------------------------------- #
#  Lire ne change rien
# --------------------------------------------------------------------------- #

def test_planifier_n_ecrit_rien(tmp_path, local):
    """La propriété première : un aperçu qui écrirait ne serait pas un aperçu."""
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    avant = {p: p.read_bytes() for p in local.rglob("*") if p.is_file()}
    imp.planifier(tiers, local)
    apres = {p: p.read_bytes() for p in local.rglob("*") if p.is_file()}
    assert avant == apres


def test_l_apercu_nomme_ce_qui_change(tmp_path, local):
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    plan = imp.planifier(tiers, local)
    assert plan.executable
    assert plan.compte(imp.MODIFIEE) == 1
    assert plan.compte(imp.IDENTIQUE) == 2
    assert "1 planche(s) corrigée(s) sur 3" in plan.annonce()


def test_le_motif_du_changement_est_nomme(tmp_path, local):
    """⚠ Les libellés sont ceux de `manga/etat_planches.SOURCES_DE_PEREMPTION` : deux
    vocabulaires pour la même chose, c'est deux phrases à tenir en phase."""
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    plan = imp.planifier(tiers, local)
    modifiee = next(p for p in plan.planches if p.etat == imp.MODIFIEE)
    assert "traduction refaite" in modifiee.motifs


def test_un_paquet_identique_n_a_rien_a_faire(tmp_path, local):
    tiers = _tome(tmp_path, "tiers", ["A", "B", "C"])
    plan = imp.planifier(tiers, local)
    assert not plan.executable
    assert "identiques" in plan.annonce()


def test_les_deux_gestes_de_designation_marchent(tmp_path, local):
    """Un tiers renvoie tantôt `Vol.3/`, tantôt `Vol.3/manga/`. Refuser l'un des deux serait
    refuser pour une raison que personne ne devine."""
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    par_manga = imp.planifier(tiers, local)
    par_tome = imp.planifier(tiers.parent, local.parent)
    assert par_manga.compte(imp.MODIFIEE) == par_tome.compte(imp.MODIFIEE) == 1


# --------------------------------------------------------------------------- #
#  Les trois refus
# --------------------------------------------------------------------------- #

def test_un_autre_tome_est_refuse(tmp_path, local):
    """On n'installe pas le tome d'un autre par mégarde."""
    autre = _tome(tmp_path, "autre", ["A"], projet="Autre œuvre")
    plan = imp.planifier(autre, local)
    assert plan.refus
    assert "Autre œuvre" in plan.refus
    assert not plan.executable


def test_un_format_de_cache_different_est_refuse(tmp_path, local):
    """⚠ **LE refus du lot.** L'ordre des zones est le pivot ; un cache d'une autre version
    ferait atterrir les traductions dans les mauvaises bulles, silencieusement."""
    vieux = _tome(tmp_path, "vieux", ["A"], version=1)
    plan = imp.planifier(vieux, local)
    assert plan.refus
    assert "version 1" in plan.refus and f"version {ck.FORMAT_VERSION}" in plan.refus
    assert "PIVOT" in plan.refus


def test_le_garde_fou_de_version_ne_depend_pas_de_masks_png(tmp_path, local):
    """⚠ Le contournement que ce module évite : `checkpoints.checkpoint_format` exige
    `masks.png` et rend `None` sans lui — un paquet sans masque passerait donc le contrôle
    de version sans être contrôlé."""
    vieux = _tome(tmp_path, "vieux", ["A"], version=1)
    assert not (vieux / ".checkpoints" / "page_0001" / "masks.png").exists()
    assert ck.checkpoint_format(vieux / ".checkpoints" / "page_0001") is None
    assert imp.planifier(vieux, local).refus


def test_une_liste_nue_vaut_la_version_1(tmp_path, local):
    """Même lecture tolérante que `checkpoints._lire_regions_brut`."""
    nu = tmp_path / "nu" / "manga" / ".checkpoints" / "page_0001"
    nu.mkdir(parents=True)
    (nu / "regions.json").write_text("[]", encoding="utf-8")
    assert "version 1" in imp.planifier(tmp_path / "nu", local).refus


def test_un_run_en_cours_est_refuse(tmp_path, local):
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    plan = imp.planifier(tiers, local, run_en_cours=True)
    assert "run est en cours" in plan.refus


def test_un_dossier_qui_n_est_pas_un_tome_le_dit(tmp_path, local):
    plan = imp.planifier(tmp_path, local)
    assert "`.checkpoints/`" in plan.refus


def test_appliquer_refuse_un_plan_refuse(tmp_path, local):
    vieux = _tome(tmp_path, "vieux", ["A"], version=1)
    with pytest.raises(imp.RefusDImporter):
        imp.appliquer(imp.planifier(vieux, local))


# --------------------------------------------------------------------------- #
#  Écrire — et ce qui n'est jamais écrasé ni supprimé
# --------------------------------------------------------------------------- #

def test_la_planche_corrigee_est_ecrite(tmp_path, local):
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    ecrites, _sauvegarde = imp.appliquer(imp.planifier(tiers, local))
    assert ecrites == 1
    lu = json.loads(
        (local / ".checkpoints" / "page_0002" / "traduction.json").read_text(encoding="utf-8"))
    assert lu == ["B corrigé"]


def test_l_ancienne_version_est_sauvegardee_avant_d_etre_remplacee(tmp_path, local):
    """⚠ La sauvegarde d'ABORD, l'écriture ensuite. L'ordre inverse laisserait, sur une
    coupure, des planches remplacées sans copie de secours."""
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    _ecrites, sauvegarde = imp.appliquer(imp.planifier(tiers, local))
    assert sauvegarde is not None and sauvegarde.is_dir()
    ancien = json.loads(
        (sauvegarde / "page_0002" / "traduction.json").read_text(encoding="utf-8"))
    assert ancien == ["B"]


def test_une_planche_absente_du_paquet_est_conservee(tmp_path, local):
    """**Rien n'est supprimé, jamais.** Un tiers qui n'a corrigé que trois planches sur cent
    cinquante ne doit pas en faire disparaître cent quarante-sept."""
    tiers = _tome(tmp_path, "tiers", ["A"])
    plan = imp.planifier(tiers, local)
    assert plan.compte(imp.ABSENTE) == 2
    imp.appliquer(plan)
    for index in (2, 3):
        assert (local / ".checkpoints" / f"page_{index:04d}" / "traduction.json").is_file()


def test_une_planche_ajoutee_est_ecrite(tmp_path, local):
    tiers = _tome(tmp_path, "tiers", ["A", "B", "C", "D"])
    plan = imp.planifier(tiers, local)
    assert plan.compte(imp.AJOUTEE) == 1
    imp.appliquer(plan)
    assert (local / ".checkpoints" / "page_0004" / "traduction.json").is_file()


def test_une_planche_identique_n_est_pas_reecrite(tmp_path, local):
    """Réécrire à l'identique ferait bouger les dates de fichier — et `manga/projet.py`
    documente précisément que les `mtime` mentent."""
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    intacte = local / ".checkpoints" / "page_0001" / "traduction.json"
    avant = intacte.stat().st_mtime_ns
    imp.appliquer(imp.planifier(tiers, local))
    assert intacte.stat().st_mtime_ns == avant


# --------------------------------------------------------------------------- #
#  Les rendus — une case à cocher, pas un défaut
# --------------------------------------------------------------------------- #

def test_les_rendus_ne_sont_pas_copies_par_defaut(tmp_path, local):
    """⚠ Mesuré le 2026-09-06 : les checkpoints sont **0,1 % du poids** d'un `build/`.
    Transférer 3 Go pour 4 Mo de corrections doit être un choix, pas un défaut."""
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    (tiers / "pages_out").mkdir()
    (tiers / "pages_out" / "page_0002.png").write_bytes(b"x" * 5000)
    plan = imp.planifier(tiers, local)
    assert plan.avec_rendus is False
    imp.appliquer(plan)
    assert not (local / "pages_out").exists()


def test_les_rendus_sont_copies_si_on_le_demande(tmp_path, local):
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    (tiers / "pages_out").mkdir()
    (tiers / "pages_out" / "page_0002.png").write_bytes(b"x" * 5000)
    plan = imp.planifier(tiers, local, avec_rendus=True)
    assert plan.octets_rendus == 5000
    assert "planches rendues" in plan.annonce()
    imp.appliquer(plan)
    assert (local / "pages_out" / "page_0002.png").is_file()


def test_l_apercu_chiffre_ce_qui_sera_ecrit(tmp_path, local):
    tiers = _tome(tmp_path, "tiers", ["A", "B corrigé", "C"])
    plan = imp.planifier(tiers, local)
    assert plan.octets_checkpoints > 0
    assert "de corrections" in plan.annonce()


def test_les_fichiers_suivis_sont_ceux_de_projet_py():
    """En écrire une seconde liste ferait diverger les deux le jour où un fichier s'ajoute."""
    from manga import projet as projet_mod
    assert imp.SUIVIS == projet_mod._SUIVIS
