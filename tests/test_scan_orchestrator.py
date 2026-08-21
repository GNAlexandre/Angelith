# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Balayage complet d'un tome scanné (`scan/orchestrator_scan.py`), avec un lecteur factice.

Aucun modèle n'est chargé : `process_volume` accepte un `lecteur` injecté, et c'est ce qui
rend toute la brique testable. Les propriétés vérifiées ici sont celles qui coûtent cher
quand elles cassent : la reprise ne relit rien, l'arrêt rend la main sans perdre la page en
cours, et le document n'est jamais écrit sur un tome incomplet.
"""
import pytest

from conftest_scan import LecteurFactice, page
from core import control
from core.reporter import Reporter
from scan import checkpoints, grille, orchestrator_scan, pages


class ReporterMuet(Reporter):
    """Double du `Reporter` du socle — muet, mais fidèle à sa SIGNATURE.

    Un double qui s'écarte du protocole qu'il double ne teste plus rien : une première
    version déclarait `finish(self)` là où le socle demande `finish(self, outputs)`, et le
    balayage réel levait un `TypeError` que la suite ne voyait pas."""

    def __init__(self):
        self.infos, self.alertes, self.sorties = [], [], []
        self.arrets = []

    def volume(self, plan): pass
    def chapter(self, idx, total, title): pass
    def stage(self, name): pass
    def block(self, idx, total): pass
    def info(self, msg): self.infos.append(msg)
    def verbose(self, msg): pass
    def warn(self, msg): self.alertes.append(msg)
    def finish(self, outputs): self.sorties.extend(outputs)
    def stopped(self, done, total): self.arrets.append((done, total))


@pytest.fixture
def tome(tmp_path):
    """Un tome de six pages : cinq de texte, une d'illustration."""
    from PIL import Image

    racine = tmp_path / "sources" / "Projet" / "Vol.1" / "JAP"
    racine.mkdir(parents=True)
    for i in range(5):
        page([{"cases": 12 + i}, {"cases": 20}, {"cases": 15},
              {"cases": 18}, {"cases": 22}]).image().save(racine / f"{i:04d}.png")
    Image.new("L", (600, 800), 30).save(racine / "0005.png")   # page très encrée
    config = {
        "chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path / "build")},
        "langues": {"dossiers": {"JAP": "jp", "ENG": "en"}},
        "scan": {"lot_ocr": 4},
    }
    return config, tmp_path


def _lancer(config, **kw):
    lecteur = kw.pop("lecteur", None) or LecteurFactice()
    reporter = kw.pop("reporter", None) or ReporterMuet()
    recap = orchestrator_scan.process_volume("Projet", "Vol.1", config, reporter=reporter,
                                             lecteur=lecteur, **kw)
    return recap, lecteur, reporter


# --------------------------------------------------------------------------- #
#  Inventaire
# --------------------------------------------------------------------------- #

def test_le_dossier_de_langue_en_images_est_trouve(tome):
    config, racine = tome
    plan = pages.scan_volume(racine / "sources" / "Projet" / "Vol.1",
                             racine / "build", config)
    assert plan.code_langue == "jp"
    assert len(plan.pages) == 6
    assert plan.sortie.name == "Vol.1.md"
    assert plan.sortie.parent.name == "JAP"


def test_un_tome_sans_images_le_dit_clairement(tmp_path):
    (tmp_path / "sources" / "Projet" / "Vol.1" / "JAP").mkdir(parents=True)
    config = {"chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path)},
              "langues": {"dossiers": {"JAP": "jp"}}}
    with pytest.raises(SystemExit, match="images"):
        pages.scan_volume(tmp_path / "sources" / "Projet" / "Vol.1", tmp_path, config)


def test_les_pages_sont_triees_naturellement(tmp_path):
    racine = tmp_path / "sources" / "Projet" / "Vol.1" / "JAP"
    racine.mkdir(parents=True)
    for nom in ("10.png", "2.png", "1.png"):
        page([{"cases": 10}] * 5).image().save(racine / nom)
    config = {"chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path)},
              "langues": {"dossiers": {"JAP": "jp"}}}
    plan = pages.scan_volume(racine.parent, tmp_path, config)
    assert [p.name for p in plan.pages] == ["1.png", "2.png", "10.png"]


# --------------------------------------------------------------------------- #
#  Balayage nominal
# --------------------------------------------------------------------------- #

def test_un_tome_complet_produit_le_document_et_le_rapport(tome):
    config, racine = tome
    recap, _lecteur, _rep = _lancer(config)
    sortie = racine / "sources" / "Projet" / "Vol.1" / "JAP" / "Vol.1.md"
    assert sortie.exists()
    assert recap["document"] == str(sortie)
    assert (racine / "build" / "Projet" / "Vol.1" / "ocr" / "RAPPORT.md").exists()
    assert recap["par_verdict"]["illustration"] == 1
    assert recap["par_verdict"]["texte"] == 5
    assert str(sortie) in _rep.sorties, "`finish` doit annoncer le document produit"


def test_l_illustration_est_copiee_et_referencee(tome):
    config, racine = tome
    _recap, _l, _r = _lancer(config)
    media = racine / "sources" / "Projet" / "Vol.1" / "JAP" / "media"
    assert (media / "page_0005.png").exists()
    texte = (racine / "sources" / "Projet" / "Vol.1" / "JAP" / "Vol.1.md").read_text("utf-8")
    assert "<!-- IMG: media/page_0005.png -->" in texte


def _pages_lues(build):
    return [i for i in range(6)
            if checkpoints.load_texte(checkpoints.page_checkpoint_dir(build, i)) is not None]


def test_une_page_d_illustration_ne_coute_aucun_appel_d_ocr(tome):
    config, racine = tome
    _recap, _lecteur, _rep = _lancer(config)
    build = racine / "build" / "Projet" / "Vol.1" / "ocr"
    assert _pages_lues(build) == [0, 1, 2, 3, 4], "la page 5 est une illustration"


# --------------------------------------------------------------------------- #
#  Reprise — la propriété qui rend la brique utilisable
# --------------------------------------------------------------------------- #

def test_relancer_ne_relit_aucune_page(tome):
    """L'invariant de cache. Un tome coûte deux heures : le relancer par réflexe ne doit
    rien coûter."""
    config, _racine = tome
    _lancer(config)
    _recap, lecteur, _rep = _lancer(config)
    assert lecteur.appels == []


def test_depuis_lecture_relit_sans_refaire_l_analyse(tome):
    config, racine = tome
    _lancer(config)
    build = racine / "build" / "Projet" / "Vol.1" / "ocr"
    avant = (checkpoints.page_checkpoint_dir(build, 0) / "plan.json").stat().st_mtime_ns
    _recap, lecteur, _rep = _lancer(config, depuis="lecture")
    apres = (checkpoints.page_checkpoint_dir(build, 0) / "plan.json").stat().st_mtime_ns
    assert lecteur.appels, "la lecture doit être refaite"
    assert avant == apres, "l'analyse ne doit pas être réécrite"


def test_force_refait_tout(tome):
    config, racine = tome
    _lancer(config)
    build = racine / "build" / "Projet" / "Vol.1" / "ocr"
    avant = {i: (checkpoints.page_checkpoint_dir(build, i) / "texte.json").stat().st_mtime_ns
             for i in _pages_lues(build)}
    _recap, lecteur, _rep = _lancer(config, force=True)
    apres = {i: (checkpoints.page_checkpoint_dir(build, i) / "texte.json").stat().st_mtime_ns
             for i in _pages_lues(build)}
    assert lecteur.appels, "le modèle doit être rappelé"
    assert set(avant) == set(apres) == {0, 1, 2, 3, 4}
    assert all(apres[i] >= avant[i] for i in avant)


def test_une_page_isolee_n_ecrit_pas_le_document(tome):
    config, racine = tome
    recap, lecteur, _rep = _lancer(config, page=0)
    build = racine / "build" / "Projet" / "Vol.1" / "ocr"
    assert lecteur.appels, "la page visée doit bien être lue"
    assert _pages_lues(build) == [0], "et elle seule"
    assert recap["document"] is None
    assert not (racine / "sources" / "Projet" / "Vol.1" / "JAP" / "Vol.1.md").exists()


def test_un_tome_incomplet_n_ecrit_pas_le_document(tome):
    """Un `.md` tronqué en silence est le pire résultat possible : le tome partirait en
    traduction amputé, et rien ne le dirait."""
    config, racine = tome
    _lancer(config, page=0)
    recap, _l, reporter = _lancer(config, depuis="lecture", page=1)
    assert recap["document"] is None
    assert not (racine / "sources" / "Projet" / "Vol.1" / "JAP" / "Vol.1.md").exists()


# --------------------------------------------------------------------------- #
#  Arrêt propre
# --------------------------------------------------------------------------- #

def test_un_stop_arrete_le_balayage_et_conserve_ce_qui_est_lu(tome):
    config, racine = tome
    build = racine / "build" / "Projet" / "Vol.1" / "ocr"
    build.mkdir(parents=True, exist_ok=True)

    class LecteurQuiDemandeLArret(LecteurFactice):
        def lire(self, images):
            sortie = super().lire(images)
            if len(self.appels) == 2:
                control.request_stop(build)
            return sortie

    lecteur = LecteurQuiDemandeLArret()
    recap, _l, reporter = _lancer(config, lecteur=lecteur)
    assert len(lecteur.appels) < 5, "le balayage doit s'être arrêté"
    assert checkpoints.load_texte(checkpoints.page_checkpoint_dir(build, 0)) is not None
    assert recap["document"] is None
    assert any("Arrêt" in a for a in reporter.alertes)
    assert reporter.arrets, "l'arrêt doit passer par `stopped` du protocole"
    assert not control.should_stop(build), "le fichier STOP doit être consommé"


def test_apres_un_arret_la_reprise_termine_le_tome(tome):
    config, racine = tome
    build = racine / "build" / "Projet" / "Vol.1" / "ocr"
    build.mkdir(parents=True, exist_ok=True)

    class LecteurQuiDemandeLArret(LecteurFactice):
        def lire(self, images):
            sortie = super().lire(images)
            if len(self.appels) == 2:
                control.request_stop(build)
            return sortie

    _lancer(config, lecteur=LecteurQuiDemandeLArret())
    recap, lecteur, _rep = _lancer(config)
    assert lecteur.appels, "il restait des pages à lire"
    assert recap["document"] is not None
    assert (racine / "sources" / "Projet" / "Vol.1" / "JAP" / "Vol.1.md").exists()


# --------------------------------------------------------------------------- #
#  Verdict de titre — déterminisme
# --------------------------------------------------------------------------- #

def test_le_verdict_de_titre_ne_depend_pas_de_l_ordre_des_pages(tmp_path):
    """En une seule passe, le pas médian ne serait connu que des pages déjà vues, et
    `--page 12` ne donnerait pas le même verdict qu'un tome entier."""
    racine = tmp_path / "sources" / "Projet" / "Vol.1" / "JAP"
    racine.mkdir(parents=True)
    for i in range(4):
        page([{"cases": 20}] * 6, hauteur=1200).image().save(racine / f"{i:04d}.png")
    page([{"cases": 4, "pas": 120, "largeur": 105}] * 2,
         largeur=1400, hauteur=1200).image().save(racine / "0004.png")
    config = {"chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path / "b")},
              "langues": {"dossiers": {"JAP": "jp"}}, "scan": {"colonnes_min": 2}}

    entier, _l, _r = _lancer(config)
    verdict_entier = [p["verdict"] for p in entier["pages"]][4]

    build = tmp_path / "b" / "Projet" / "Vol.1" / "ocr"
    isolee, _l, _r = _lancer(config, page=4, force=True)
    assert isolee["pages"][0]["verdict"] == verdict_entier
    assert checkpoints.load_plan(checkpoints.page_checkpoint_dir(build, 4)) is not None


def test_le_rapport_nomme_les_pages_a_verifier(tome):
    config, racine = tome
    _lancer(config, lecteur=LecteurFactice(par_defaut="あ"))
    rapport = (racine / "build" / "Projet" / "Vol.1" / "ocr" / "RAPPORT.md").read_text("utf-8")
    assert "Pages à vérifier" in rapport
    assert "suspecte" in rapport


def test_la_config_scan_absente_ne_casse_rien(tmp_path):
    assert orchestrator_scan.config_scan({})["caracteres_par_tranche"] == \
        grille.CARACTERES_PAR_TRANCHE
    assert orchestrator_scan.config_scan({"scan": {"lot_ocr": 3}})["lot_ocr"] == 3
