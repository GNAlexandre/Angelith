# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de `manga/serie.py` — l'état d'un chapitre lu SANS l'ouvrir.

C'est ce module qui décide, pendant un run de nuit, qu'un chapitre n'a pas besoin d'être
traité. Une erreur ici ne se voit pas : elle saute un chapitre qu'il fallait faire, ou
réécrit un CBZ de 230 Mo pour rien. D'où l'insistance sur les cas limites — archive,
dossier vide, comptes égaux mais rendu périmé.
"""
import json
import os
import zipfile
from pathlib import Path

from PIL import Image

from manga import serie


def _image(chemin: Path, taille=(8, 8)) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", taille, "white").save(chemin)
    return chemin


def _chapitre_source(racine: Path, projet: str, tome: str, n: int) -> Path:
    """`sources/<projet>/<tome>/manga/` avec `n` planches."""
    d = racine / projet / tome / "manga"
    for i in range(1, n + 1):
        _image(d / f"{i:03d}.jpg")
    return d


def _rendre(build_root: Path, projet: str, tome: str, n: int) -> Path:
    """`build/<projet>/<tome>/manga/pages_out/` avec `n` planches rendues."""
    d = serie.build_dir_de(build_root, projet, tome) / "pages_out"
    for i in range(1, n + 1):
        _image(d / f"page_{i:04d}.png")
    return d


# --------------------------------------------------------------------------- #
# Ordre de lecture
# --------------------------------------------------------------------------- #

def test_les_chapitres_sortent_dans_l_ordre_de_lecture(tmp_path):
    """LE défaut que ce module corrige. Le tri alphabétique classe `Chap.10` avant `Chap.2`,
    et `pipeline.sources._reading_order_key` ne sait pas faire mieux ici : il travaille sur
    `Path.stem`, or `Path("Chap.5").stem` vaut `"Chap"` — tous les chapitres rendent alors la
    même clé."""
    src = tmp_path / "sources"
    for nom in ("Chap.10", "Chap.2", "Chap.5", "Chap.1", "Chap.17"):
        (src / "Oeuvre" / nom).mkdir(parents=True)

    assert serie.lister_chapitres(src, "Oeuvre") == [
        "Chap.1", "Chap.2", "Chap.5", "Chap.10", "Chap.17"]


def test_le_tri_alphabetique_aurait_donne_un_autre_ordre(tmp_path):
    """Le témoin : sans ce module, l'ordre serait faux. Il l'a été jusqu'ici."""
    src = tmp_path / "sources"
    noms = ["Chap.10", "Chap.2"]
    for nom in noms:
        (src / "Oeuvre" / nom).mkdir(parents=True)
    assert sorted(noms) == ["Chap.10", "Chap.2"]                 # l'ordre naïf
    assert serie.lister_chapitres(src, "Oeuvre") == ["Chap.2", "Chap.10"]


def test_une_oeuvre_inconnue_ne_leve_pas(tmp_path):
    """Un pré-vol ne doit jamais tuer la série : il répond « rien », l'appelant décide."""
    assert serie.lister_chapitres(tmp_path / "sources", "Fantome") == []


def test_seuls_les_dossiers_comptent(tmp_path):
    """`glossaire.yaml` vit à côté des chapitres, dans `sources/<Œuvre>/`."""
    src = tmp_path / "sources"
    (src / "Oeuvre" / "Chap.1").mkdir(parents=True)
    (src / "Oeuvre" / "glossaire.yaml").write_text("personnages: []", encoding="utf-8")
    assert serie.lister_chapitres(src, "Oeuvre") == ["Chap.1"]


# --------------------------------------------------------------------------- #
# Comptage des planches source
# --------------------------------------------------------------------------- #

def test_comptage_d_un_dossier_d_images(tmp_path):
    _chapitre_source(tmp_path, "Oeuvre", "Chap.1", 7)
    assert serie.compter_pages_source(tmp_path / "Oeuvre" / "Chap.1") == 7


def test_comptage_quand_les_images_sont_a_la_racine_du_chapitre(tmp_path):
    """Le repli de `sources_manga.scan_volume` : pas de sous-dossier `manga/`, le chapitre
    porte directement ses planches. Le pré-vol doit regarder au MÊME endroit que le scan."""
    d = tmp_path / "Oeuvre" / "Chap.1"
    for i in range(1, 4):
        _image(d / f"{i:03d}.jpg")
    assert serie.compter_pages_source(d) == 3


def test_comptage_d_une_archive_cbz_sans_l_extraire(tmp_path):
    """L'index d'un zip vit à la fin du fichier : on le lit sans toucher aux données. Et
    surtout, sans rien écrire dans `pages_src/` — ce que ferait `scan_volume`."""
    d = tmp_path / "Oeuvre" / "Chap.1" / "manga"
    d.mkdir(parents=True)
    src_img = _image(tmp_path / "tmp.png")
    with zipfile.ZipFile(d / "chap.cbz", "w") as zf:
        for i in range(1, 6):
            zf.write(src_img, f"{i:03d}.png")
        zf.writestr("ComicInfo.xml", "<x/>")        # non-image : ne compte pas

    assert serie.compter_pages_source(tmp_path / "Oeuvre" / "Chap.1") == 5
    assert not (tmp_path / "build").exists()


def test_plusieurs_archives_s_additionnent(tmp_path):
    d = tmp_path / "Oeuvre" / "Chap.1" / "manga"
    d.mkdir(parents=True)
    src_img = _image(tmp_path / "tmp.png")
    for nom, n in (("a.cbz", 3), ("b.cbz", 4)):
        with zipfile.ZipFile(d / nom, "w") as zf:
            for i in range(n):
                zf.write(src_img, f"{i:03d}.png")
    assert serie.compter_pages_source(tmp_path / "Oeuvre" / "Chap.1") == 7


def test_une_archive_cbr_rend_indenombrable_et_non_zero(tmp_path):
    """`None` et `0` ne veulent pas dire la même chose, et tout le module en dépend : on ne
    saute jamais un chapitre sur une incertitude. Lire un `.cbr` demanderait `rarfile` plus
    l'outil externe `unrar`, qu'un pré-vol n'a aucune raison d'exiger."""
    d = tmp_path / "Oeuvre" / "Chap.1" / "manga"
    d.mkdir(parents=True)
    (d / "chap.cbr").write_bytes(b"Rar!\x1a\x07\x00")
    assert serie.compter_pages_source(tmp_path / "Oeuvre" / "Chap.1") is None


def test_une_archive_illisible_rend_indenombrable(tmp_path):
    d = tmp_path / "Oeuvre" / "Chap.1" / "manga"
    d.mkdir(parents=True)
    (d / "chap.cbz").write_bytes(b"ceci n'est pas un zip")
    assert serie.compter_pages_source(tmp_path / "Oeuvre" / "Chap.1") is None


def test_les_archives_priment_sur_les_images_isolees(tmp_path):
    """Même règle que `sources_manga.scan_volume`. Sans elle, un chapitre livré en `.cbz`
    avec sa jaquette à côté serait compté à une planche et déclaré partiel pour toujours."""
    d = tmp_path / "Oeuvre" / "Chap.1" / "manga"
    d.mkdir(parents=True)
    src_img = _image(tmp_path / "tmp.png")
    _image(d / "jaquette.jpg")
    with zipfile.ZipFile(d / "chap.cbz", "w") as zf:
        for i in range(9):
            zf.write(src_img, f"{i:03d}.png")
    assert serie.compter_pages_source(tmp_path / "Oeuvre" / "Chap.1") == 9


def test_un_chapitre_vide_compte_zero(tmp_path):
    (tmp_path / "Oeuvre" / "Chap.1" / "manga").mkdir(parents=True)
    assert serie.compter_pages_source(tmp_path / "Oeuvre" / "Chap.1") == 0


# --------------------------------------------------------------------------- #
# Les cinq statuts
# --------------------------------------------------------------------------- #

def test_statut_sans_source(tmp_path):
    """Le cas réel de `manga C/Vol.2` : un dossier de light novel japonais
    sous une œuvre manga. L'ouvrir ne produirait qu'un `SystemExit`."""
    src, build = tmp_path / "sources", tmp_path / "build"
    (src / "Oeuvre" / "Vol.2" / "JAP").mkdir(parents=True)
    e = serie.etat_chapitre(src, build, "Oeuvre", "Vol.2")
    assert e.statut == serie.SANS_SOURCE
    assert serie.a_traiter(e) is False


def test_statut_non_traite(tmp_path):
    src, build = tmp_path / "sources", tmp_path / "build"
    _chapitre_source(src, "Oeuvre", "Chap.1", 12)
    e = serie.etat_chapitre(src, build, "Oeuvre", "Chap.1")
    assert (e.statut, e.pages_source, e.pages_rendues) == (serie.NON_TRAITE, 12, 0)
    assert serie.a_traiter(e) is True


def test_statut_partiel(tmp_path):
    """LE cas que `--list` ne savait pas voir : un chapitre arrêté en cours de route
    s'affichait « déjà généré » sur la seule existence de son dossier de build."""
    src, build = tmp_path / "sources", tmp_path / "build"
    _chapitre_source(src, "Oeuvre", "Chap.1", 150)
    _rendre(build, "Oeuvre", "Chap.1", 3)
    e = serie.etat_chapitre(src, build, "Oeuvre", "Chap.1")
    assert (e.statut, e.pages_rendues) == (serie.PARTIEL, 3)
    assert "3/150" in e.detail
    assert serie.a_traiter(e) is True


def test_statut_termine(tmp_path):
    src, build = tmp_path / "sources", tmp_path / "build"
    _chapitre_source(src, "Oeuvre", "Chap.1", 5)
    _rendre(build, "Oeuvre", "Chap.1", 5)
    e = serie.etat_chapitre(src, build, "Oeuvre", "Chap.1")
    assert e.statut == serie.TERMINE
    assert serie.a_traiter(e) is False


def test_statut_a_relettrer_quand_le_rendu_est_en_retard(tmp_path):
    """Comptes égaux ne suffit pas : une traduction refaite après le rendu laisse le CBZ
    porter une planche que plus personne n'a vue. C'est le défaut mesuré sur le Vol.4."""
    src, build = tmp_path / "sources", tmp_path / "build"
    _chapitre_source(src, "Oeuvre", "Chap.1", 3)
    _rendre(build, "Oeuvre", "Chap.1", 3)

    build_dir = serie.build_dir_de(build, "Oeuvre", "Chap.1")
    ckpt = build_dir / ".checkpoints" / "page_0002"
    ckpt.mkdir(parents=True)
    (ckpt / "traduction.json").write_text(json.dumps(["FR"]), encoding="utf-8")
    # La traduction est POSTÉRIEURE au rendu — l'ordre d'écriture est ce qui compte ici.
    rendu = build_dir / "pages_out" / "page_0002.png"
    os.utime(rendu, (1_600_000_000, 1_600_000_000))

    e = serie.etat_chapitre(src, build, "Oeuvre", "Chap.1")
    assert e.statut == serie.A_RELETTRER
    assert e.perimees == [2]
    assert serie.a_traiter(e) is True


def test_un_cbr_partiellement_rendu_reste_a_traiter(tmp_path):
    """Source indénombrable : on ne peut pas conclure « terminé », donc on traite."""
    src, build = tmp_path / "sources", tmp_path / "build"
    d = src / "Oeuvre" / "Chap.1" / "manga"
    d.mkdir(parents=True)
    (d / "chap.cbr").write_bytes(b"Rar!\x1a\x07\x00")
    _rendre(build, "Oeuvre", "Chap.1", 4)
    e = serie.etat_chapitre(src, build, "Oeuvre", "Chap.1")
    assert e.pages_source is None
    assert serie.a_traiter(e) is True


# --------------------------------------------------------------------------- #
# Le pré-vol dans son ensemble
# --------------------------------------------------------------------------- #

def test_le_prevol_n_ecrit_rien(tmp_path):
    """Contrat non négociable : `scan_volume` extrait les archives et lève sur un dossier
    vide. Un pré-vol qui ferait l'un ou l'autre serait pire que pas de pré-vol du tout."""
    src, build = tmp_path / "sources", tmp_path / "build"
    _chapitre_source(src, "Oeuvre", "Chap.1", 3)
    (src / "Oeuvre" / "Chap.2" / "manga").mkdir(parents=True)          # vide : sans source
    d = src / "Oeuvre" / "Chap.3" / "manga"
    d.mkdir(parents=True)
    with zipfile.ZipFile(d / "c.cbz", "w") as zf:
        zf.write(_image(tmp_path / "t.png"), "001.png")

    avant = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    etats = serie.etats_serie(src, build, "Oeuvre")
    apres = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))

    assert avant == apres, "le pré-vol a touché au disque"
    assert [e.statut for e in etats] == [
        serie.NON_TRAITE, serie.SANS_SOURCE, serie.NON_TRAITE]


def test_le_tableau_aligne_les_colonnes(tmp_path):
    src, build = tmp_path / "sources", tmp_path / "build"
    _chapitre_source(src, "Oeuvre", "Chap.9", 2)
    _chapitre_source(src, "Oeuvre", "Chap.10", 2)
    lignes = serie.tableau(serie.etats_serie(src, build, "Oeuvre"))
    assert len(lignes) == 2
    assert lignes[0].startswith("· Chap.9 ") and lignes[1].startswith("· Chap.10")
    # Même colonne de départ pour le détail, quelle que soit la longueur du nom.
    assert [l.index("2 planche(s)") for l in lignes] == [
        lignes[0].index("2 planche(s)")] * 2


def test_a_traiter_couvre_tous_les_statuts():
    """Garde-fou : un statut ajouté sans décision explicite ferait silencieusement traiter —
    ou pire, sauter — les chapitres qui le portent."""
    assert set(serie.STATUTS_SANS_TRAVAIL) <= set(serie.STATUTS)
    for statut in serie.STATUTS:
        etat = serie.EtatChapitre("X", 1, 1, [], statut, "")
        assert serie.a_traiter(etat) is (statut not in serie.STATUTS_SANS_TRAVAIL)
        assert statut in serie.PUCES
