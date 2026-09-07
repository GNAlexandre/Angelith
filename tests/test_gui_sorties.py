# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les sorties d'un tome — `gui/sorties.py` (lot 34, L34.5). **Sans PySide6.**

⚠ Le test qui compte est `test_aucune_sortie_ne_lance_un_run` : un « Exporter en PSD » qui
relancerait le rendu de 131 planches sans le dire serait la pire action coûteuse sans
garde-fou de l'application (`PLAN-34` L34.5 point 2).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import bibliotheque as biblio
from gui import sorties as so


def _config(racine: Path) -> dict:
    return {"chemins": {"sources": str(racine / "sources"), "build": str(racine / "build"),
                        "glossaire_fichier": "glossaire.yaml"},
            "langues": {"dossiers": {"ENG": "en", "JAP": "jp"}}}


def _ecrire(chemin: Path, octets: int = 8) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(b"\0" * octets)
    return chemin


@pytest.fixture()
def tome_manga(tmp_path):
    config = _config(tmp_path)
    for i in range(1, 4):
        _ecrire(tmp_path / "sources" / "Manga A" / "Vol.1" / "manga" / f"{i:03d}.png")
        _ecrire(tmp_path / "build" / "Manga A" / "Vol.1" / "manga" / ".checkpoints"
                / f"page_{i:04d}" / "regions.json")
        _ecrire(tmp_path / "build" / "Manga A" / "Vol.1" / "manga" / "pages_out"
                / f"page_{i:04d}.png", 1000)
    return tmp_path, config, biblio.tome_info(config, "Manga A", "Vol.1")


def test_ce_qui_existe_est_montre_avec_sa_date_et_sa_taille(tome_manga):
    _racine, config, info = tome_manga
    panneau = so.panneau(config, info)
    images = next(s for s in panneau.sorties if s.cle == "images")
    assert images.etat == so.PRESENTE
    assert images.fichiers == 3
    assert images.octets == 3000
    assert images.date != "—"
    assert "3 fichier(s)" in images.resume


def test_ce_qui_n_existe_pas_porte_le_geste_ET_son_cout(tome_manga):
    """Règle 1 du L34.5 : « ce qui n'existe pas est montré comme absent, avec le geste qui le
    produirait **et son coût** »."""
    _racine, config, info = tome_manga
    panneau = so.panneau(config, info)
    for sortie in panneau.sorties:
        if sortie.existe:
            continue
        assert sortie.geste, f"{sortie.cle} : aucun geste annoncé"
        assert sortie.cout, f"{sortie.cle} : aucun coût annoncé"


def test_aucune_sortie_ne_lance_un_run(tome_manga):
    """⚠ Le geste est une CHAÎNE, pas un appelable. C'est ce qui garantit qu'aucun bouton de
    ce panneau ne peut engager des heures de GPU par accident."""
    _racine, config, info = tome_manga
    for sortie in so.panneau(config, info).sorties:
        assert isinstance(sortie.geste, str)
        assert not callable(sortie.geste)


def test_le_psd_dit_qu_il_exige_un_run_et_ne_se_produit_pas_apres_coup(tome_manga):
    """Règle 2 du L34.5. Le PSD est écrit PENDANT le run, quand `formats:` le demande."""
    _racine, config, info = tome_manga
    psd = next(s for s in so.panneau(config, info).sorties if s.cle == "psd")
    assert psd.etat == so.EXIGE_RUN
    assert "manga.rendu.formats" in psd.note
    assert "rendu complet" in psd.cout


def test_le_refus_de_psd_est_un_ETAT_pas_une_erreur(tome_manga):
    """Règle 3 du L34.5 : la 2.6.0 a livré ce refus **propre** plutôt qu'un fichier corrompu ;
    le panneau doit l'afficher comme un état."""
    from manga.psd import COTE_MAX

    racine, config, info = tome_manga
    # Deux PSD pour trois planches rendues : une bande a été refusée.
    for i in (1, 2):
        _ecrire(racine / "build" / "Manga A" / "Vol.1" / "manga" / "pages_psd"
                / f"page_{i:04d}.psd", 500)
    psd = next(s for s in so.panneau(config, info).sorties if s.cle == "psd")
    assert psd.etat == so.REFUSEE
    assert so.LIBELLES_ETAT[so.REFUSEE] == "refusée par le format"
    assert str(COTE_MAX) in psd.note
    assert "1 manquant(s)" in psd.note
    # ⚠ Et la note dit ce qu'elle ne sait pas — la cause est nommée, pas affirmée.
    assert "Non confirmé" in psd.note


def test_un_tome_de_roman_montre_ses_rendus_pandoc(tmp_path):
    config = _config(tmp_path)
    _ecrire(tmp_path / "sources" / "Roman B" / "Vol.1" / "ENG" / "livre.pdf")
    build = tmp_path / "build" / "Roman B" / "Vol.1"
    (build / ".checkpoints" / "ch01" / "traduction").mkdir(parents=True)
    _ecrire(build / "Roman_B_Vol.1.md", 200)
    _ecrire(build / "Roman_B_Vol.1.docx", 4000)
    info = biblio.tome_info(config, "Roman B", "Vol.1")
    panneau = so.panneau(config, info)
    cles = {s.cle: s.etat for s in panneau.sorties}
    assert cles["md"] == so.PRESENTE
    assert cles["docx"] == so.PRESENTE
    assert cles["epub"] == so.ABSENTE
    epub = next(s for s in panneau.sorties if s.cle == "epub")
    assert "rendu.formats" in epub.note
    assert "--render-only" in so.commande(epub, "Roman B", "Vol.1")


def test_la_sortie_du_scan_est_cherchee_dans_le_dossier_de_langue(tmp_path):
    """⚠ Pas sous `build/` : `scan/pages.py` l'écrit à côté des images pour que `run.py`
    l'enchaîne. La chercher ailleurs la déclarerait absente à jamais."""
    config = _config(tmp_path)
    langue = tmp_path / "sources" / "Scan C" / "Vol.1" / "JAP"
    for i in range(3):
        _ecrire(langue / f"{i:04d}.png")
    info = biblio.tome_info(config, "Scan C", "Vol.1")
    assert info.brique == biblio.SCAN
    assert next(iter(so.panneau(config, info).sorties)).etat == so.EXIGE_RUN

    _ecrire(langue / "Vol.1.md", 120)
    info = biblio.tome_info(config, "Scan C", "Vol.1")
    sortie = next(iter(so.panneau(config, info).sorties))
    assert sortie.etat == so.PRESENTE
    assert sortie.chemin == langue / "Vol.1.md"


def test_les_planches_perimees_sont_annoncees_avant_d_assembler(tome_manga, monkeypatch):
    """L'avertissement que `assemble_outputs` donne déjà au run, remonté dans le panneau :
    une archive assemblée maintenant embarquerait un lettrage qui ne correspond plus."""
    _racine, config, info = tome_manga
    perimee = biblio.TomeInfo(**{**info.__dict__, "perimees": (2,)})
    panneau = so.panneau(config, perimee)
    assert any("ANTÉRIEUR" in a for a in panneau.avertissements)


def test_le_resume_porte_ses_denominateurs(tome_manga):
    _racine, config, info = tome_manga
    resume = so.panneau(config, info).resume
    assert "sur" in resume and "possible(s)" in resume


def test_la_commande_substitue_le_projet_et_le_tome(tome_manga):
    _racine, config, info = tome_manga
    cbz = next(s for s in so.panneau(config, info).sorties if s.cle == "cbz")
    commande = so.commande(cbz, "Manga A", "Vol.1")
    assert '"Manga A" Vol.1' in commande
    assert "{p}" not in commande and "{t}" not in commande
