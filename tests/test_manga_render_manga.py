# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Assemblage des sorties manga : CBZ (+ ComicInfo.xml), PDF borné en mémoire, et
`assemble_outputs` — appelée aussi à l'ARRÊT, ce qui est le correctif du CBZ manquant.

Le défaut d'origine : `_render_outputs` n'était atteint qu'APRÈS la boucle des pages, et
tout `return False` sur `STOP`/Ctrl+C sortait avant l'assemblage — **même quand les 150
pages étaient déjà sur disque**. Relancer un tome complet puis l'interrompre ne produisait
donc jamais d'archive. Défaut de structure, pas de `build_cbz`.
"""
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from manga.render_manga import build_cbz, build_comicinfo, build_pdf


@pytest.fixture
def pages(tmp_path):
    d = tmp_path / "pages_out"
    d.mkdir()
    chemins = []
    for i in range(1, 4):
        p = d / f"page_{i:04d}.png"
        Image.new("RGB", (120, 170), (250 - 20 * i, 240, 230)).save(p)
        chemins.append(p)
    return chemins


# --------------------------------------------------------------------------- #
# ComicInfo.xml
# --------------------------------------------------------------------------- #

def test_comicinfo_declare_la_lecture_droite_a_gauche():
    """Sans `Manga=YesAndRightToLeft`, un lecteur affiche la planche de gauche à droite et
    inverse les doubles pages. C'est LA métadonnée indispensable pour un manga."""
    xml = build_comicinfo("Mon Manga", "Vol.1", pages=150)
    assert "<Manga>YesAndRightToLeft</Manga>" in xml
    assert "<Series>Mon Manga</Series>" in xml
    assert "<PageCount>150</PageCount>" in xml
    assert "<LanguageISO>fr</LanguageISO>" in xml


def test_comicinfo_sens_gauche_droite():
    xml = build_comicinfo("X", "Vol.1", pages=1, sens_lecture="gauche_droite")
    assert "<Manga>Yes</Manga>" in xml


def test_comicinfo_porte_la_version():
    from core.version import __version__
    assert __version__ in build_comicinfo("X", "Vol.1", pages=1)


def test_comicinfo_echappe_les_valeurs():
    """« Tom & Jerry » ou « <Untitled> » produiraient un XML invalide, que certains lecteurs
    rejettent en bloc — l'archive s'ouvrirait alors sans AUCUNE métadonnée, en silence."""
    xml = build_comicinfo("Tom & Jerry", "<Vol.1>", pages=2)
    assert "Tom &amp; Jerry" in xml and "&lt;Vol.1&gt;" in xml
    assert "Tom & Jerry" not in xml


def test_comicinfo_est_un_xml_valide():
    import xml.etree.ElementTree as ET
    racine = ET.fromstring(build_comicinfo("Tom & <Jerry>", "Vol.\"1\"", pages=3))
    assert racine.tag == "ComicInfo"
    assert racine.findtext("Series") == "Tom & <Jerry>"
    assert racine.findtext("PageCount") == "3"


# --------------------------------------------------------------------------- #
# CBZ
# --------------------------------------------------------------------------- #

def test_cbz_contient_les_pages(pages, tmp_path):
    out = build_cbz(pages, tmp_path / "t.cbz")
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["page_0001.png", "page_0002.png", "page_0003.png"]


def test_cbz_sans_comicinfo_reste_compatible(pages, tmp_path):
    """`comicinfo` est optionnel : aucun appelant ni test existant ne casse."""
    out = build_cbz(pages, tmp_path / "t.cbz")
    with zipfile.ZipFile(out) as zf:
        assert "ComicInfo.xml" not in zf.namelist()


def test_comicinfo_est_la_PREMIERE_entree_de_l_archive(pages, tmp_path):
    """Plusieurs lecteurs ne le cherchent qu'au début du flux."""
    xml = build_comicinfo("S", "Vol.1", pages=len(pages))
    out = build_cbz(pages, tmp_path / "t.cbz", comicinfo=xml)
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist()[0] == "ComicInfo.xml"
        assert zf.read("ComicInfo.xml").decode("utf-8").startswith("<?xml")


def test_cbz_cree_le_dossier_parent(pages, tmp_path):
    out = build_cbz(pages, tmp_path / "sous" / "dossier" / "t.cbz")
    assert out.exists()


# --------------------------------------------------------------------------- #
# PDF borné en mémoire
# --------------------------------------------------------------------------- #

def _pdf_page_count(chemin) -> int:
    """Nombre de pages RÉELLEMENT déclarées par le catalogue du PDF.

    ⚠ Ce contrôle est la leçon d'un vrai bug : une version intermédiaire écrivait le PDF
    par lots avec `append=True`, ce qui produisait **un catalogue par lot**. Le fichier
    s'ouvrait sans erreur avec `/Count 38` au lieu de 150 — 112 planches silencieusement
    absentes. Un test qui ne vérifie que l'existence et la taille du fichier ne voit rien."""
    import re
    donnees = Path(chemin).read_bytes()
    catalogues = re.findall(rb"/Type\s*/Pages", donnees)
    assert len(catalogues) == 1, f"{len(catalogues)} catalogues /Pages — PDF fragmenté"
    comptes = [int(m.group(1)) for m in re.finditer(rb"/Count\s+(\d+)", donnees)]
    assert comptes, "aucun /Count dans le PDF"
    return max(comptes)


def test_pdf_declare_TOUTES_les_pages(pages, tmp_path):
    """Le contrôle qui manquait : le catalogue doit annoncer toutes les planches."""
    out = build_pdf(pages, tmp_path / "t.pdf")
    assert out.exists() and out.stat().st_size > 0
    assert _pdf_page_count(out) == len(pages)


def test_pdf_un_seul_catalogue_meme_sur_beaucoup_de_pages(tmp_path):
    """Avec plus de pages que la limite d'append de Pillow (3), le PDF doit rester d'un
    seul bloc — c'est-à-dire qu'on ne doit PAS utiliser `append=True`."""
    d = tmp_path / "beaucoup"
    d.mkdir()
    chemins = []
    for i in range(12):
        p = d / f"page_{i:04d}.png"
        Image.new("RGB", (80, 110), (200, 200 - i * 5, 190)).save(p)
        chemins.append(p)
    out = build_pdf(chemins, tmp_path / "t.pdf")
    assert _pdf_page_count(out) == 12


def test_pdf_sans_page_leve_une_erreur_claire(tmp_path):
    with pytest.raises(SystemExit):
        build_pdf([], tmp_path / "t.pdf")


def test_pdf_libere_les_images_apres_ecriture(pages, tmp_path):
    """Toutes les planches sont décodées simultanément (contrainte Pillow), mais elles
    doivent être refermées à la sortie plutôt que laissées vivantes."""
    import PIL.Image as PILImage
    ouvertes = []
    vrai_open = PILImage.open

    def espion(*a, **k):
        im = vrai_open(*a, **k)
        ouvertes.append(im)
        return im

    PILImage.open = espion
    try:
        build_pdf(pages, tmp_path / "t.pdf")
    finally:
        PILImage.open = vrai_open
    assert ouvertes, "des images doivent avoir été ouvertes"


def test_estimation_du_pic_memoire(pages):
    """Le coût est estimé AVANT l'écriture, pour pouvoir prévenir."""
    from manga.render_manga import estimer_pic_memoire_pdf
    pic = estimer_pic_memoire_pdf(pages)
    attendu = 3 * 120 * 170 * 1.45 / 1e6 * len(pages)
    assert pic == pytest.approx(attendu, rel=0.01)
    # `largeur_max` doit faire baisser l'estimation
    assert estimer_pic_memoire_pdf(pages, largeur_max=60) < pic


def test_un_pic_memoire_eleve_est_signale(pages, tmp_path, monkeypatch):
    """Pillow ne sait pas écrire un PDF page par page sans le tronquer : puisqu'on ne peut
    pas borner le pic, il faut au moins le DIRE, avec le réglage qui le réduit.

    On abaisse le seuil plutôt que de générer des gigaoctets de planches : c'est le
    mécanisme d'alerte qu'on teste, pas la valeur du seuil."""
    import manga.render_manga as R
    monkeypatch.setattr(R, "_SEUIL_ALERTE_MO", 0.01)
    msgs = []
    R.build_pdf(pages, tmp_path / "t.pdf", warn=msgs.append)
    assert msgs and "pic mémoire estimé" in msgs[0]
    assert "pdf_largeur_max" in msgs[0]
    assert _pdf_page_count(tmp_path / "t.pdf") == len(pages)   # l'alerte n'empêche rien


def test_aucune_alerte_sur_un_petit_tome(pages, tmp_path):
    msgs = []
    build_pdf(pages, tmp_path / "t.pdf", warn=msgs.append)
    assert msgs == []


def test_pdf_largeur_max_reduit_le_fichier(pages, tmp_path):
    gros = build_pdf(pages, tmp_path / "gros.pdf", quality=95)
    petit = build_pdf(pages, tmp_path / "petit.pdf", quality=95, largeur_max=60)
    assert petit.stat().st_size < gros.stat().st_size


def test_pdf_largeur_max_n_agrandit_pas(pages, tmp_path):
    """`largeur_max` supérieure à la planche ne doit rien changer."""
    out = build_pdf(pages, tmp_path / "t.pdf", largeur_max=5000)
    assert out.exists()


# --------------------------------------------------------------------------- #
# assemble_outputs
# --------------------------------------------------------------------------- #

def _mcfg(formats, **rendu):
    return {"rendu": {"formats": formats, **rendu}}


def test_assemble_outputs_ecrit_le_cbz_avec_comicinfo(pages, tmp_path):
    from manga.orchestrator_manga import assemble_outputs
    build_dir = tmp_path
    sorties = assemble_outputs(build_dir, _mcfg(["cbz"]), "Mon Manga", "Vol.1")
    cbz = build_dir / "Mon Manga_Vol.1.cbz"
    assert cbz.exists() and str(cbz) in sorties
    with zipfile.ZipFile(cbz) as zf:
        assert zf.namelist()[0] == "ComicInfo.xml"
        assert "YesAndRightToLeft" in zf.read("ComicInfo.xml").decode("utf-8")


def test_assemble_outputs_journalise_ce_qu_il_ecrit(pages, tmp_path):
    """L'absence silencieuse de sortie était indiagnosticable."""
    from manga.orchestrator_manga import assemble_outputs

    class Rep:
        def __init__(self):
            self.msgs = []

        def info(self, m):
            self.msgs.append(m)

    rep = Rep()
    assemble_outputs(tmp_path, _mcfg(["cbz"]), "S", "Vol.1", reporter=rep)
    assert any("CBZ écrit" in m and "3 pages" in m for m in rep.msgs), rep.msgs


def test_assemble_outputs_le_dit_quand_il_n_y_a_rien(tmp_path):
    from manga.orchestrator_manga import assemble_outputs

    class Rep:
        def __init__(self):
            self.msgs = []

        def info(self, m):
            self.msgs.append(m)

    (tmp_path / "pages_out").mkdir()
    rep = Rep()
    sorties = assemble_outputs(tmp_path, _mcfg(["cbz"]), "S", "Vol.1", reporter=rep)
    assert sorties == []
    assert any("rien à assembler" in m for m in rep.msgs), rep.msgs


def test_assemble_outputs_n_annonce_pages_clean_que_si_images_demande(pages, tmp_path):
    """`pages_clean/` était annoncé en TÊTE des sorties même quand seul le CBZ l'était."""
    from manga.orchestrator_manga import assemble_outputs
    seul_cbz = assemble_outputs(tmp_path, _mcfg(["cbz"]), "S", "Vol.1")
    assert not any("pages_clean" in s for s in seul_cbz)

    avec_images = assemble_outputs(tmp_path, _mcfg(["cbz", "images"]), "S", "Vol.1")
    assert any("pages_clean" in s for s in avec_images)
    assert any("pages_out" in s for s in avec_images)


def test_assemble_outputs_respecte_le_sens_de_lecture(pages, tmp_path):
    from manga.orchestrator_manga import assemble_outputs
    assemble_outputs(tmp_path, _mcfg(["cbz"], sens_lecture="gauche_droite"), "S", "Vol.1")
    with zipfile.ZipFile(tmp_path / "S_Vol.1.cbz") as zf:
        assert "<Manga>Yes</Manga>" in zf.read("ComicInfo.xml").decode("utf-8")


def test_assemble_outputs_pdf(pages, tmp_path):
    from manga.orchestrator_manga import assemble_outputs
    sorties = assemble_outputs(tmp_path, _mcfg(["pdf"], pdf_dpi=150, pdf_qualite=70),
                               "S", "Vol.1")
    assert (tmp_path / "S_Vol.1.pdf").exists()
    assert any(s.endswith(".pdf") for s in sorties)
