# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`--extract-glossary` / `--optimize-glossary` côté manga : le glossaire de l'ŒUVRE,
peuplé et nettoyé **sans traduire ni relettrer une seule planche**.

Ce que ces tests verrouillent tient en une phrase : la commande ne doit écrire que dans
`.checkpoints/` et dans `sources/<Projet>/glossaire.yaml`. C'est cette promesse qui la rend
lançable sur une œuvre finie — un `RAPPORT.md` écrasé par des statistiques de traduction
vides, ou un CBZ de 230 Mo réencodé sur un dossier synchronisé, la rendraient inutilisable.

Le défaut d'origine est nommé par le README : « une planche n'est relevée que si elle va être
**traduite** ». Peupler le glossaire d'une œuvre de quinze chapitres coûtait donc une
retraduction intégrale. `test_toutes_les_planches_sont_relevees` est le test de ce lot.

Aucun modèle réel : le détecteur ONNX est INTERDIT par défaut, l'OCR et les agents sont
factices. Le fichier ne porte donc ni le marqueur `modeles` ni `lent`.
"""
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image, ImageDraw

from core.reporter import Reporter
from manga import checkpoints
from manga.detection import BubbleRegion

ROOT = Path(__file__).resolve().parent.parent
BOX = (60, 40, 340, 200)
TAILLE = (400, 260)
OEUVRE = "MonManga"


# --------------------------------------------------------------------------- #
# Fixtures — un chapitre sur disque, des modèles factices
# --------------------------------------------------------------------------- #

def _config(tmp_path: Path) -> dict:
    """La VRAIE `config.yaml`, avec les seuls chemins déviés vers `tmp_path`.

    On règle la racine et pas `manga.chemins` : la brique en hérite par fusion profonde, et
    ces fixtures sont donc aussi le test de bout en bout de cet héritage."""
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    config["chemins"]["prompts"] = str(ROOT / "prompts")
    # Chemin DÉLIBÉRÉMENT inexistant : une extraction sur cache ne doit jamais le toucher.
    config["manga"]["detection"]["model_path"] = str(tmp_path / "absent.onnx")
    config["manga"]["detection"]["telechargement_auto"] = False
    config.setdefault("options", {})["dry_run"] = False
    return config


def _planche() -> Image.Image:
    img = Image.new("RGB", TAILLE, (20, 20, 20))
    d = ImageDraw.Draw(img)
    d.ellipse(list(BOX), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    return img


def _masque() -> np.ndarray:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse(list(BOX), fill=255)
    return np.asarray(m) > 127


def _region() -> BubbleRegion:
    return BubbleRegion(bbox=BOX, mask=_masque(), score=0.95, cls=0)


def _semer(tmp_path: Path, tomes=("Vol.1",), *, planches=1, avec_regions=True,
           avec_ocr=True, avec_trad=False, ocr=None, trad=None) -> Path:
    """Une œuvre sur disque, avec les checkpoints demandés déjà en place."""
    build_root = tmp_path / "build"
    for tome in tomes:
        vol_dir = tmp_path / "sources" / OEUVRE / tome / "manga"
        vol_dir.mkdir(parents=True, exist_ok=True)
        page = _planche()
        build_dir = build_root / OEUVRE / tome / "manga"
        # Les deux dossiers que l'orchestrateur crée lui-même : ici, pour que les tests
        # puissent y poser des TÉMOINS avant de vérifier qu'ils ne bougent pas.
        (build_dir / "pages_out").mkdir(parents=True, exist_ok=True)
        (build_dir / "pages_clean").mkdir(parents=True, exist_ok=True)
        for i in range(1, planches + 1):
            page.save(vol_dir / f"page_{i:04d}.png")
            ckpt = checkpoints.page_checkpoint_dir(build_dir, i)
            if avec_regions:
                checkpoints.save_regions(ckpt, [_region()], page.size)
            if avec_ocr:
                checkpoints.save_ocr(ckpt, list(ocr or ["リベルティナ"]))
            if avec_trad:
                checkpoints.save_traduction(ckpt, list(trad or ["Libentina arrive enfin"]))
    return build_root / OEUVRE / tomes[0] / "manga"


def _glossaire(tmp_path: Path, entrees=()) -> Path:
    from core import glossary
    glo = glossary.empty()
    for cat, entree in entrees:
        glo[cat].append(entree)
    chemin = tmp_path / "sources" / OEUVRE / "glossaire.yaml"
    glossary.save(glo, chemin)
    return chemin


class _FauxAgent:
    """Agent factice : réponse fixe, appels comptés. `llm=None` suffit à `core.runtime`,
    qui tolère un client absent (dry-run) comme un client factice sans `.close()`."""

    def __init__(self, reponse: str = "- (rien à signaler)"):
        self.reponse, self.appels = reponse, 0
        self.llm = None
        self.thinking = False

    def run(self, user_content, dry_payload="", max_tokens=None, temperature=None,
            images=None):
        self.appels += 1
        return self.reponse


class _FauxOCR:
    appels = 0

    def __init__(self, cfg=None, *, dire=None):
        self.cfg, self.dire = cfg, dire

    def read_all(self, image, regions, styles=None, cfg=None):
        type(self).appels += 1
        return ["リベルティナ" for _ in regions]


class _FauxDetecteur:
    appels = 0

    def __init__(self, *a, **k):
        pass

    def detect(self, image, conf_threshold=None, iou_threshold=None):
        type(self).appels += 1
        return [_region()]


@pytest.fixture
def modeles_factices(monkeypatch):
    """Interdit le détecteur ONNX (il lèverait de toute façon), remplace l'OCR par un faux.

    Le détecteur est réactivé à la demande par `autoriser_la_detection` : c'est le test de la
    détection À LA VOLÉE qui en a besoin, aucun autre."""
    import manga.detection as det
    import manga.ocr as ocr_mod

    def _boom(*a, **k):
        raise AssertionError("une extraction sur cache ne doit pas charger le détecteur ONNX")

    _FauxOCR.appels = 0
    _FauxDetecteur.appels = 0
    monkeypatch.setattr(det, "BubbleDetector", _boom)
    monkeypatch.setattr(ocr_mod, "MangaOCR", _FauxOCR)


@pytest.fixture
def autoriser_la_detection(monkeypatch):
    import manga.detection as det
    monkeypatch.setattr(det, "BubbleDetector", _FauxDetecteur)


def _brancher_agents(monkeypatch, **agents):
    """Remplace le roster que l'orchestrateur construit depuis `manga.modeles`."""
    import manga.orchestrator_manga as orch
    monkeypatch.setattr(orch, "build_manga_agents",
                        lambda config, dry_run=False: dict(agents))
    return agents


NOTE = "### PERSONNAGES\n- Libertina | genre: féminin | termes_source: リベルティナ | la princesse\n"


# --------------------------------------------------------------------------- #
# LE test du lot : toute planche OCRisée a droit à un relevé
# --------------------------------------------------------------------------- #

def test_toutes_les_planches_sont_relevees(tmp_path, monkeypatch, modeles_factices):
    """Un chapitre ENTIÈREMENT traduit et rendu n'a plus rien à traduire : dans un run
    normal, `a_relever` est donc vide et pas une planche n'est relevée. C'est le défaut que
    la commande corrige — ici les trois planches doivent l'être."""
    from manga.glossaire_manga import run_extract_glossary

    build_dir = _semer(tmp_path, planches=3, avec_trad=True)
    for i in range(1, 4):
        _planche().save(checkpoints.final_page_path(build_dir, i))
        _planche().save(checkpoints.clean_page_path(build_dir, i))
    _glossaire(tmp_path)
    term = _FauxAgent(NOTE)
    _brancher_agents(monkeypatch, terminologue=term)

    assert run_extract_glossary(OEUVRE, "Vol.1", _config(tmp_path)) is True
    assert term.appels == 3


def test_le_glossaire_est_enrichi_sur_disque(tmp_path, monkeypatch, modeles_factices):
    from core import glossary
    from manga.glossaire_manga import run_extract_glossary

    _semer(tmp_path)
    chemin = _glossaire(tmp_path)
    _brancher_agents(monkeypatch, terminologue=_FauxAgent(NOTE))

    run_extract_glossary(OEUVRE, "Vol.1", _config(tmp_path))
    assert [e["nom"] for e in glossary.load(chemin)["personnages"]] == ["Libertina"]


# --------------------------------------------------------------------------- #
# La promesse : rien n'est écrit hors de .checkpoints/ et du glossaire
# --------------------------------------------------------------------------- #

def test_aucune_planche_ni_rapport_ni_archive_n_est_reecrit(tmp_path, monkeypatch,
                                                            modeles_factices):
    """Le chapitre est complet : pages nettoyées, pages finales, RAPPORT.md, CBZ. Aucun de
    ces fichiers ne doit être touché — c'est ce qui autorise à lancer la commande sur une
    œuvre finie sans risquer des heures de réencodage."""
    from manga.glossaire_manga import run_extract_glossary

    build_dir = _semer(tmp_path, avec_trad=True)
    temoins = [checkpoints.final_page_path(build_dir, 1),
               checkpoints.clean_page_path(build_dir, 1),
               build_dir / "RAPPORT.md",
               build_dir / f"{OEUVRE} - Vol.1.cbz"]
    for chemin in temoins:
        if chemin.suffix == ".png":
            _planche().save(chemin)
        else:
            chemin.write_text("temoin", encoding="utf-8")
    avant = {c: (c.read_bytes(), c.stat().st_mtime_ns) for c in temoins}
    _glossaire(tmp_path)
    _brancher_agents(monkeypatch, terminologue=_FauxAgent(NOTE))

    run_extract_glossary(OEUVRE, "Vol.1", _config(tmp_path))

    for chemin, (octets, mtime) in avant.items():
        assert chemin.read_bytes() == octets, chemin.name
        assert chemin.stat().st_mtime_ns == mtime, chemin.name


def test_le_nettoyage_ne_tourne_jamais(tmp_path, monkeypatch, modeles_factices):
    """`pages_clean/` absent et non régénéré : le nettoyage n'appartient pas au glossaire, et
    le laisser tourner écrirait des planches que ce mode ne rend pas."""
    from manga.glossaire_manga import run_extract_glossary

    build_dir = _semer(tmp_path)
    _glossaire(tmp_path)
    _brancher_agents(monkeypatch, terminologue=_FauxAgent(NOTE))

    run_extract_glossary(OEUVRE, "Vol.1", _config(tmp_path))
    assert not checkpoints.clean_page_path(build_dir, 1).exists()
    assert not checkpoints.final_page_path(build_dir, 1).exists()


# --------------------------------------------------------------------------- #
# Détection + OCR à la volée, et cache
# --------------------------------------------------------------------------- #

def test_une_planche_sans_ocr_est_detectee_et_ocrisee(tmp_path, monkeypatch,
                                                      modeles_factices,
                                                      autoriser_la_detection):
    """Un chapitre vierge n'est pas sauté : c'est ce qui rend la commande utilisable AVANT la
    première traduction, et non seulement après."""
    from manga.glossaire_manga import run_extract_glossary

    _semer(tmp_path, avec_regions=False, avec_ocr=False)
    _glossaire(tmp_path)
    term = _FauxAgent(NOTE)
    _brancher_agents(monkeypatch, terminologue=term)

    run_extract_glossary(OEUVRE, "Vol.1", _config(tmp_path))
    assert _FauxDetecteur.appels == 1
    assert _FauxOCR.appels == 1
    assert term.appels == 1


def test_un_releve_en_cache_ne_repaie_aucun_appel(tmp_path, monkeypatch, modeles_factices):
    """Deux extractions de suite : la seconde re-fusionne les notes du disque, sans LLM."""
    from manga.glossaire_manga import run_extract_glossary

    _semer(tmp_path)
    _glossaire(tmp_path)
    term = _FauxAgent(NOTE)
    _brancher_agents(monkeypatch, terminologue=term)
    config = _config(tmp_path)

    run_extract_glossary(OEUVRE, "Vol.1", config)
    run_extract_glossary(OEUVRE, "Vol.1", config)
    assert term.appels == 1


def test_force_refait_le_releve(tmp_path, monkeypatch, modeles_factices):
    """Le contre-exemple : après avoir modifié `prompts/terminologue.md`, il faut pouvoir
    rejouer le relevé sans supprimer 150 fichiers à la main."""
    from manga.glossaire_manga import run_extract_glossary

    _semer(tmp_path)
    _glossaire(tmp_path)
    term = _FauxAgent(NOTE)
    _brancher_agents(monkeypatch, terminologue=term)
    config = _config(tmp_path)

    run_extract_glossary(OEUVRE, "Vol.1", config)
    run_extract_glossary(OEUVRE, "Vol.1", config, force=True)
    assert term.appels == 2


def test_from_rendu_ne_rappelle_pas_le_terminologue(tmp_path, monkeypatch, modeles_factices):
    """`--from rendu` ne dépend pas de la terminologie : son cache reste lu, pas refait."""
    from manga.glossaire_manga import run_extract_glossary

    _semer(tmp_path)
    _glossaire(tmp_path)
    term = _FauxAgent(NOTE)
    _brancher_agents(monkeypatch, terminologue=term)
    config = _config(tmp_path)

    run_extract_glossary(OEUVRE, "Vol.1", config)
    run_extract_glossary(OEUVRE, "Vol.1", config, restart_from="rendu")
    assert term.appels == 1


# --------------------------------------------------------------------------- #
# Dérives — ce que l'extraction sait faire de plus sur un chapitre déjà traduit
# --------------------------------------------------------------------------- #

def _perso(nom, source):
    return ("personnages", {"nom": nom, "variantes": [], "interdits": [],
                            "termes_source": [source], "description": "", "force": True})


def test_une_derive_ancree_atterrit_en_interdits(tmp_path, monkeypatch, modeles_factices):
    """T1 : `リベルティナ` dans l'OCR de la bulle, `Libentina` dans son français. Aucune
    statistique, aucun appel LLM — et c'est exactement ce qu'un chapitre déjà traduit permet
    de récolter, là où le run complet ne le faisait que pour les planches qu'il retraduisait."""
    from core import glossary
    from manga.glossaire_manga import run_extract_glossary

    _semer(tmp_path, avec_trad=True)
    chemin = _glossaire(tmp_path, [_perso("Libertina", "リベルティナ")])
    _brancher_agents(monkeypatch)

    run_extract_glossary(OEUVRE, "Vol.1", _config(tmp_path))
    entree = glossary.load(chemin)["personnages"][0]
    assert entree["interdits"] == ["Libentina"]
    # ⚠ JAMAIS dans `variantes` : c'est la clé de recherche du dédoublonneur, et y déposer une
    # faute corromprait une future fusion, silencieusement et durablement.
    assert entree["variantes"] == []


def test_sans_francais_en_cache_aucune_derive(tmp_path, monkeypatch, modeles_factices):
    """Pas de `traduction.json` : rien à confronter au japonais, donc aucune preuve."""
    from core import glossary
    from manga.glossaire_manga import run_extract_glossary

    _semer(tmp_path, avec_trad=False)
    chemin = _glossaire(tmp_path, [_perso("Libertina", "リベルティナ")])
    _brancher_agents(monkeypatch)

    run_extract_glossary(OEUVRE, "Vol.1", _config(tmp_path))
    assert glossary.load(chemin)["personnages"][0]["interdits"] == []


@pytest.mark.parametrize("avec_terminologue", [False, True])
def test_en_dry_run_le_glossaire_n_est_pas_reecrit(tmp_path, monkeypatch, modeles_factices,
                                                   avec_terminologue):
    """Le glossaire est la SEULE sortie de ce mode : un dry-run qui l'écrirait quand même ne
    laisserait plus rien à répéter en blanc.

    ⚠ Le cas `avec_terminologue` est celui qui compte, et il n'est pas théorique : re-fusionner
    des notes DÉJÀ en cache change le glossaire **sans un seul appel LLM**. Mesuré sur *manga A
    Zero manga A* Vol.2 — 150 planches reprises, 0 appel, 23 fusions.

    ⚠ Cette garantie vaut pour `--extract-glossary`, et pour lui seul : le `--dry-run` d'un run
    manga ordinaire écrit l'OCR, les pages, le rapport et le CBZ (cf.
    `tests/test_manga_terminology.py`), il ne promet que l'absence d'appel LLM."""
    from manga.glossaire_manga import run_extract_glossary

    _semer(tmp_path, avec_trad=True)
    chemin = _glossaire(tmp_path, [_perso("Libertina", "リベルティナ")])
    avant = chemin.read_bytes()
    _brancher_agents(monkeypatch, **({"terminologue": _FauxAgent(NOTE)}
                                     if avec_terminologue else {}))
    config = _config(tmp_path)
    config["options"]["dry_run"] = True

    run_extract_glossary(OEUVRE, "Vol.1", config)
    assert chemin.read_bytes() == avant


# --------------------------------------------------------------------------- #
# Optimisation
# --------------------------------------------------------------------------- #

def test_l_optimisation_utilise_l_agent_du_manga(tmp_path, monkeypatch):
    """`pipeline.orchestrator.run_optimize` construirait ses agents depuis
    `config["modeles"]` racine : il ignorerait le modèle, la température et l'endpoint réglés
    sous `manga.modeles`. On vérifie que c'est bien le glossariste MANGA qui travaille."""
    import manga.glossaire_manga as gm
    from core import glossary

    chemin = _glossaire(tmp_path, [_perso("Libertina", "リベルティナ")])
    glossariste = _FauxAgent(NOTE)
    monkeypatch.setattr(gm, "build_manga_agents",
                        lambda config, dry_run=False: {"glossariste": glossariste})

    gm.run_optimize_glossary(OEUVRE, _config(tmp_path), reporter=Reporter())
    assert glossariste.appels == 1
    assert [e["nom"] for e in glossary.load(chemin)["personnages"]] == ["Libertina"]
    assert chemin.with_suffix(".bak.yaml").exists()


def test_le_chemin_du_glossaire_suit_la_section_manga(tmp_path):
    """`manga.chemins` hérite de la racine par fusion profonde ; une surcharge doit être
    respectée, sinon la brique écrirait à côté du fichier que le light novel enrichit."""
    from manga.glossaire_manga import chemin_glossaire

    config = _config(tmp_path)
    assert chemin_glossaire(OEUVRE, config) == tmp_path / "sources" / OEUVRE / "glossaire.yaml"
    config["manga"]["chemins"] = {"sources": str(tmp_path / "ailleurs")}
    assert chemin_glossaire(OEUVRE, config) == tmp_path / "ailleurs" / OEUVRE / "glossaire.yaml"
