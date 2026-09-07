# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'inventaire des œuvres — `bibliotheque.py` (lot 34).

Aucun de ces tests n'a besoin de PySide6 : c'est tout l'intérêt du module, et c'est ce qui
fait qu'ils tournent dans le job de CI qui ne l'installe pas.

⚠ Deux tests portent les invariants du `PLAN-34` et **doivent** échouer si on les casse :
`test_le_balayage_n_ouvre_aucune_image` (par instrumentation, pas par confiance) et
`test_perime_a_exactement_le_sens_de_planches_a_relettrer`.
"""
from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path

import pytest

import bibliotheque as biblio


# --------------------------------------------------------------------------- #
#  Fabrique de corpus — un dépôt minuscule, sur disque, sans une seule image
# --------------------------------------------------------------------------- #

def _config(racine: Path) -> dict:
    return {
        "chemins": {"sources": str(racine / "sources"), "build": str(racine / "build"),
                    "glossaire_fichier": "glossaire.yaml"},
        "langues": {"dossiers": {"ENG": "en", "JAP": "jp", "FR": "fr"}},
    }


def _ecrire(chemin: Path, contenu: str = "x") -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _tome_manga(racine: Path, projet: str, tome: str, *, planches: int = 3,
                rendues: int | None = None, etapes=("detection", "ocr", "traduction"),
                format: str = "manga") -> None:
    """Un tome manga sur disque. Les « images » sont des fichiers vides : **rien ici ne les
    ouvre**, et c'est précisément ce que le test d'instrumentation vérifie."""
    source = racine / "sources" / projet / tome / format
    for i in range(1, planches + 1):
        _ecrire(source / f"{i:03d}.png")
    build = racine / "build" / projet / tome / "manga"
    rendues = planches if rendues is None else rendues
    fichiers = {"detection": "regions.json", "ocr": "ocr.json",
                "terminologie": "terminologie.txt", "traduction": "traduction.json",
                "sfx": "sfx.json"}
    for i in range(1, planches + 1):
        ckpt = build / ".checkpoints" / f"page_{i:04d}"
        for etape in etapes:
            if etape in fichiers:
                _ecrire(ckpt / fichiers[etape], "{}")
    for i in range(1, rendues + 1):
        _ecrire(build / "pages_out" / f"page_{i:04d}.png")
        _ecrire(build / "pages_clean" / f"page_{i:04d}.png")


def _tome_ln(racine: Path, projet: str, tome: str, *, chapitres: int = 2,
             langue: str = "ENG", extension: str = ".pdf", rendus=("docx",)) -> None:
    _ecrire(racine / "sources" / projet / tome / langue / f"{projet}{extension}")
    build = racine / "build" / projet / tome
    for i in range(1, chapitres + 1):
        for etape in ("terminologie", "traduction", "mise_en_page"):
            (build / ".checkpoints" / f"ch{i:02d}" / etape).mkdir(parents=True, exist_ok=True)
        _ecrire(build / "chapters" / f"ch{i:02d}.md")
    tige = f"{projet}_{tome}".replace(" ", "_")
    _ecrire(build / f"{tige}.md")
    for suffixe in rendus:
        _ecrire(build / f"{tige}.{suffixe}")


@pytest.fixture()
def corpus(tmp_path: Path) -> tuple[Path, dict]:
    """Trois œuvres : un manga complet, un roman, et un tome à deux briques."""
    _tome_manga(tmp_path, "Manga A", "Vol.1", planches=3)
    _tome_manga(tmp_path, "Manga A", "Vol.2", planches=4, rendues=1)
    _tome_ln(tmp_path, "Roman B", "Vol.1", chapitres=2)
    # Un tome qui porte À LA FOIS des planches et un dossier de langue d'images : c'est le
    # cas réel de `sources/manga C/Vol.1` au 2026-09-05.
    _tome_manga(tmp_path, "Mixte C", "Vol.1", planches=2)
    _ecrire(tmp_path / "sources" / "Mixte C" / "Vol.1" / "JAP" / "0001.png")
    _ecrire(tmp_path / "sources" / "Manga A" / "glossaire.yaml",
            "personnages:\n- nom: X\n- nom: Y\n")
    return tmp_path, _config(tmp_path)


# --------------------------------------------------------------------------- #
#  Le modèle
# --------------------------------------------------------------------------- #

def test_les_briques_sont_deduites_de_l_arborescence(corpus):
    racine, config = corpus
    src = biblio.racine_sources(config)
    assert biblio.briques_du_tome(src / "Manga A" / "Vol.1", config) == ("manga",)
    assert biblio.briques_du_tome(src / "Roman B" / "Vol.1", config) == ("ln",)
    assert biblio.briques_du_tome(src / "Mixte C" / "Vol.1", config) == ("manga", "scan")


def test_un_webtoon_est_reconnu_comme_tel(tmp_path):
    config = _config(tmp_path)
    _tome_manga(tmp_path, "Webtoon D", "Chap.1", planches=2, format="webtoon")
    info = biblio.tome_info(config, "Webtoon D", "Chap.1")
    assert info.brique == biblio.WEBTOON
    assert info.unite == "bande"


def test_la_sortie_md_du_scan_ne_fait_pas_du_tome_un_roman(tmp_path):
    """⚠ `scan/pages.py` écrit son `.md` DANS le dossier de langue. Le compter comme une
    source de light novel ferait disparaître la brique scan du tome dès qu'elle a tourné."""
    config = _config(tmp_path)
    _ecrire(tmp_path / "sources" / "Scan E" / "Vol.1" / "JAP" / "0001.png")
    src = biblio.racine_sources(config)
    assert biblio.briques_du_tome(src / "Scan E" / "Vol.1", config) == ("scan",)
    _ecrire(tmp_path / "sources" / "Scan E" / "Vol.1" / "JAP" / "Vol.1.md")
    assert biblio.briques_du_tome(src / "Scan E" / "Vol.1", config) == ("scan",)
    # …alors qu'un VRAI fichier de roman, lui, ajoute bien la brique.
    _ecrire(tmp_path / "sources" / "Scan E" / "Vol.1" / "JAP" / "roman.epub")
    assert biblio.briques_du_tome(src / "Scan E" / "Vol.1", config) == ("ln", "scan")


def test_les_etapes_disent_faite_partielle_absente(corpus):
    _racine, config = corpus
    complet = biblio.tome_info(config, "Manga A", "Vol.1")
    assert complet.etapes["detection"] == biblio.FAITE
    assert complet.etapes["ocr"] == biblio.FAITE
    assert complet.etapes["rendu"] == biblio.FAITE
    assert complet.etapes["terminologie"] == biblio.ABSENTE

    partiel = biblio.tome_info(config, "Manga A", "Vol.2")
    assert partiel.etapes["detection"] == biblio.FAITE
    assert partiel.etapes["rendu"] == biblio.PARTIELLE
    assert partiel.statut == "partiel"


def test_les_sorties_ne_listent_que_ce_qui_existe(corpus):
    racine, config = corpus
    info = biblio.tome_info(config, "Manga A", "Vol.1")
    assert set(info.sorties) == {"images", "clean"}
    build = racine / "build" / "Manga A" / "Vol.1" / "manga"
    _ecrire(build / "Manga A_Vol.1.cbz")
    assert "cbz" in biblio.tome_info(config, "Manga A", "Vol.1").sorties


def test_le_glossaire_est_par_oeuvre_et_sa_lecture_ne_reecrit_rien(corpus):
    racine, config = corpus
    chemin = racine / "sources" / "Manga A" / "glossaire.yaml"
    avant = chemin.read_bytes()
    assert biblio.compter_glossaire(config, "Manga A") == 2
    assert biblio.compter_glossaire(config, "Roman B") is None
    assert chemin.read_bytes() == avant


def test_un_tome_de_roman_compte_ses_chapitres(corpus):
    _racine, config = corpus
    info = biblio.tome_info(config, "Roman B", "Vol.1")
    assert info.brique == biblio.LN
    assert info.unites == 2 and info.unite == "chapitre"
    assert info.format == "pdf" and info.langue_source == "en"
    assert info.etapes["traduction"] == biblio.FAITE
    assert info.etapes["rendu"] == biblio.FAITE
    assert set(info.sorties) >= {"md", "docx"}


def test_un_roman_n_a_jamais_de_rendu_perime(corpus):
    """⚠ « Périmé » a UN sens dans ce dépôt, et il porte sur des planches. Ce test refuse
    qu'on en invente un second pour remplir une colonne."""
    _racine, config = corpus
    info = biblio.tome_info(config, "Roman B", "Vol.1")
    assert info.perimees == ()
    assert biblio.PERIMEE not in info.etapes.values()


def test_unites_none_n_est_pas_zero(tmp_path):
    """Un tome de roman dont rien n'a encore tourné n'a pas « 0 chapitre » : on ne SAIT pas
    combien il en porte tant qu'il n'a pas été extrait."""
    config = _config(tmp_path)
    _ecrire(tmp_path / "sources" / "Roman F" / "Vol.1" / "ENG" / "livre.epub")
    info = biblio.tome_info(config, "Roman F", "Vol.1")
    assert info.unites is None
    assert info.compte.startswith("?")


# --------------------------------------------------------------------------- #
#  Les invariants du plan
# --------------------------------------------------------------------------- #

def test_le_module_n_importe_ni_qt_ni_pil_ni_numpy():
    """Par lecture de l'AST, sans importer quoi que ce soit — donc valide même dans un
    environnement où PySide6 est absent."""
    module = Path(__file__).resolve().parents[1] / "bibliotheque.py"
    arbre = ast.parse(module.read_text(encoding="utf-8"))
    interdits = {"PySide6", "PIL", "numpy", "torch", "cv2"}
    for noeud in arbre.body:                 # NIVEAU MODULE seulement
        if isinstance(noeud, ast.Import):
            noms = {a.name.split(".")[0] for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom):
            noms = {(noeud.module or "").split(".")[0]}
        else:
            continue
        assert not (noms & interdits), f"import lourd au niveau module : {noms}"


def test_le_balayage_n_ouvre_aucune_image(corpus, monkeypatch):
    """**Par instrumentation, pas par confiance** — critère 2 du `PLAN-34`.

    `PIL.Image.open` est remplacé par une fonction qui lève. Un balayage complet du corpus
    doit passer sans jamais l'appeler."""
    PIL = pytest.importorskip("PIL.Image")
    _racine, config = corpus

    def _interdit(*args, **kwargs):
        raise AssertionError("le balayage a ouvert une image")

    monkeypatch.setattr(PIL, "open", _interdit)
    oeuvres = biblio.Inventaire(config).oeuvres(paralleles=1)
    assert {o.projet for o in oeuvres} == {"Manga A", "Roman B", "Mixte C"}
    assert sum(len(o.tomes) for o in oeuvres) == 4


def test_perime_a_exactement_le_sens_de_planches_a_relettrer(tmp_path):
    """Critère 4 : sur un tome fabriqué où une planche a été ÉDITÉE après son rendu, la
    bibliothèque doit dire exactement ce que `etat_planches.planches_a_relettrer` dit."""
    from manga import etat_planches

    config = _config(tmp_path)
    _tome_manga(tmp_path, "Manga A", "Vol.1", planches=3)
    build = tmp_path / "build" / "Manga A" / "Vol.1" / "manga"

    info = biblio.tome_info(config, "Manga A", "Vol.1")
    assert info.perimees == ()
    assert info.etapes["rendu"] == biblio.FAITE
    assert info.statut == "termine"

    # La planche 2 est corrigée à la main APRÈS son rendu. Une seconde d'écart suffit, et il
    # faut qu'elle soit réelle : les systèmes de fichiers à mtime d'une seconde de résolution
    # rendraient sinon la même date pour les deux écritures.
    ckpt = build / ".checkpoints" / "page_0002"
    _ecrire(ckpt / "traduction_manuelle.json", json.dumps({"0": "corrigée"}))
    futur = time.time() + 10
    os.utime(ckpt / "traduction_manuelle.json", (futur, futur))

    attendu = etat_planches.planches_a_relettrer(build)
    assert attendu == [2]
    info = biblio.tome_info(config, "Manga A", "Vol.1")
    assert list(info.perimees) == attendu
    assert info.etapes["rendu"] == biblio.PERIMEE
    assert info.statut == "a_relettrer"


def test_le_balayage_massif_et_le_balayage_planche_par_planche_sont_d_accord(tmp_path):
    """Les deux chemins de `etat_planches` passent par `_motifs` — ce test refuse qu'ils
    divergent, ce qui ferait afficher « à jour » sur une planche que l'éditeur relettrerait."""
    from manga import etat_planches

    _tome_manga(tmp_path, "Manga A", "Vol.1", planches=4)
    build = tmp_path / "build" / "Manga A" / "Vol.1" / "manga"
    for numero, fichier in ((2, "traduction_manuelle.json"), (4, "mise_en_page.json")):
        chemin = _ecrire(build / ".checkpoints" / f"page_{numero:04d}" / fichier, "{}")
        futur = time.time() + 10
        os.utime(chemin, (futur, futur))

    balayage = etat_planches.balayer_tome(build)
    assert etat_planches.perimees_du_balayage(balayage) == [2, 4]
    for index in balayage:
        assert balayage[index]["motifs"] == etat_planches.motifs_de_peremption(build, index)


def test_les_etapes_declarees_suivent_les_orchestrateurs():
    """Une colonne « sfx » qui survivrait au renommage de l'étape afficherait un rond vide
    sur une étape qui tourne."""
    assert biblio.verifier_coherence_etapes() == []


def test_la_legende_couvre_tous_les_etats():
    """⚠ Une pastille sans légende est une couleur (critère 10)."""
    assert {code for code, _, _ in biblio.LEGENDE_ETATS} == set(biblio.ETATS_ETAPE)
    for _code, marque, sens in biblio.LEGENDE_ETATS:
        assert marque and sens


# --------------------------------------------------------------------------- #
#  L'inventaire paresseux
# --------------------------------------------------------------------------- #

def test_l_inventaire_ne_balaie_rien_avant_qu_on_demande(corpus, monkeypatch):
    """C'est ce qui permet à `run_manga.py --list` sans argument de ne rien payer."""
    _racine, config = corpus
    appels: list[tuple[str, str]] = []
    vrai = biblio.tome_info
    monkeypatch.setattr(biblio, "tome_info",
                        lambda cfg, p, t, **kw: (appels.append((p, t)), vrai(cfg, p, t, **kw))[1])

    inventaire = biblio.Inventaire(config)
    assert len(inventaire.projets()) == 3
    assert inventaire.tomes(None, "Manga A") == ["Vol.1", "Vol.2"]
    assert appels == []

    inventaire.tome("Manga A", "Vol.1")
    inventaire.tome("Manga A", "Vol.1")
    assert appels == [("Manga A", "Vol.1")]          # mémoïsé


def test_rafraichir_relit_vraiment(corpus):
    """« Rafraîchir » qui ne rafraîchit rien serait pire que pas de bouton du tout."""
    racine, config = corpus
    inventaire = biblio.Inventaire(config)
    assert "cbz" not in inventaire.tome("Manga A", "Vol.1").sorties
    _ecrire(racine / "build" / "Manga A" / "Vol.1" / "manga" / "Manga A_Vol.1.cbz")
    assert "cbz" not in inventaire.tome("Manga A", "Vol.1").sorties
    inventaire.rafraichir()
    assert "cbz" in inventaire.tome("Manga A", "Vol.1").sorties


def test_les_fils_ne_changent_pas_le_resultat(corpus):
    """Le balayage parallèle est une optimisation d'entrées-sorties, pas un autre calcul."""
    _racine, config = corpus
    sequentiel = biblio.Inventaire(config).oeuvres(paralleles=1)
    parallele = biblio.Inventaire(config).oeuvres(paralleles=8)
    assert [(o.projet, [t.tome for t in o.tomes]) for o in sequentiel] == \
           [(o.projet, [t.tome for t in o.tomes]) for o in parallele]
    for a, b in zip(sequentiel, parallele):
        for ta, tb in zip(a.tomes, b.tomes):
            assert (ta.etapes, ta.statut, ta.unites) == (tb.etapes, tb.statut, tb.unites)


def test_le_verdict_manga_reste_disponible_sur_un_roman(corpus):
    """⚠ C'est lui que `run_manga.py --list` imprime, et il doit rester le verdict de la
    brique MANGA — « aucune image ni archive » — même quand la bibliothèque, elle, sait que
    le tome est un roman terminé."""
    _racine, config = corpus
    info = biblio.tome_info(config, "Roman B", "Vol.1")
    assert info.statut == "termine"
    assert biblio.detail_manga(info) == "aucune image ni archive"
    assert biblio.puce(info) == "⚠"
