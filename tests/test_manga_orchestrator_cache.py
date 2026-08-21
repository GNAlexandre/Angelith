# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Reprises PUREMENT EN CACHE de l'orchestrateur manga : `--from nettoyage` et
`--from rendu` ne doivent avoir besoin **ni du modèle de détection ONNX, ni de
`manga-ocr`** — toutes les régions et tous les textes viennent de `.checkpoints/`.

Complément indispensable à `test_manga_orchestrator.py`, qui est **entièrement sauté** dès
que `manga_models/bubble_detector.onnx` est absent (le cas sur une machine de
développement fraîche) : l'orchestrateur n'avait alors plus aucune couverture.

Le défaut corrigé ici : `BubbleDetector` et `MangaOCR()` étaient construits
inconditionnellement avant la boucle des pages. Le premier lève `SystemExit` si le .onnx
manque, le second charge un modèle ViT+BERT — si bien que la commande de vérification du
lot 1 (`--from nettoyage`, censée ne rien recalculer) échouait avant la première page.
"""
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image, ImageDraw

from manga import checkpoints
from manga.detection import BubbleRegion

ROOT = Path(__file__).resolve().parent.parent
BOX = (60, 40, 340, 200)
TAILLE = (400, 260)


def _config(tmp_path: Path) -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    # On règle la racine, PAS `manga.chemins` : la brique en hérite par fusion profonde
    # depuis le lot 2.3. Les deux lignes recopiaient auparavant `sources`/`build` sous
    # `manga:`, exactement la duplication que le socle a supprimée — ces fixtures sont donc
    # aussi le test de bout en bout de cet héritage.
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    # Chemin DÉLIBÉRÉMENT inexistant : une reprise en cache ne doit jamais le toucher.
    config["manga"]["detection"]["model_path"] = str(tmp_path / "absent.onnx")
    # ⚠ Neutraliser le détecteur de BULLES ne suffit pas à rester hors de la vision : la
    # passe `sfx` est hors du graphe d'invalidation, donc elle tourne même sur un tome dont
    # tout le reste est en cache — 110 s d'inférence ONNX par appel, mesurées au profileur.
    config["manga"]["onomatopees"]["actif"] = False
    config["chemins"]["prompts"] = str(ROOT / "prompts")
    config.setdefault("options", {})["dry_run"] = True
    return config


def _planche() -> Image.Image:
    """Bulle blanche sur case sombre — la configuration qui produisait des blobs gris."""
    img = Image.new("RGB", TAILLE, (20, 20, 20))
    d = ImageDraw.Draw(img)
    d.ellipse(list(BOX), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    cy = (BOX[1] + BOX[3]) // 2
    for i in range(5):
        x = BOX[0] + 40 + i * 40
        d.rectangle([x, cy - 20, x + 22, cy + 20], fill=(0, 0, 0))
    return img


def _masque_ellipse() -> np.ndarray:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse(list(BOX), fill=255)
    return np.asarray(m) > 127


def _semer(tmp_path: Path, *, avec_clean: bool, avec_ocr: bool, avec_trad: bool):
    """Prépare une arborescence de tome avec les checkpoints demandés déjà en place."""
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    page = _planche()
    page.save(vol_dir / "page_0001.png")

    build_dir = tmp_path / "build" / "MonManga" / "Vol.1" / "manga"
    (build_dir / "pages_out").mkdir(parents=True, exist_ok=True)
    (build_dir / "pages_clean").mkdir(parents=True, exist_ok=True)
    ckpt = checkpoints.page_checkpoint_dir(build_dir, 1)

    region = BubbleRegion(bbox=BOX, mask=_masque_ellipse(), score=0.95, cls=0)
    checkpoints.save_regions(ckpt, [region], page.size)
    if avec_clean:
        from manga.clean import clean_bubbles
        clean_bubbles(page, [region]).save(checkpoints.clean_page_path(build_dir, 1))
    if avec_ocr:
        checkpoints.save_ocr(ckpt, ["こんにちは"])
    if avec_trad:
        checkpoints.save_traduction(ckpt, ["Bonjour, comment vas-tu ?"])
    return build_dir


class _FauxOCR:
    """OCR factice : évite de charger le vrai modèle ViT+BERT (lent, et inutile pour
    tester la tuyauterie de reprise).

    La signature suit celle de `MangaOCR` — configuration OCR et `dire` — depuis que le
    chargement peut être hors ligne et doit pouvoir le signaler."""
    appels = 0

    def __init__(self, cfg=None, *, dire=None):
        self.cfg, self.dire = cfg, dire

    def read_all(self, image, regions, styles=None, cfg=None):
        type(self).appels += 1
        return ["こんにちは" for _ in regions]


@pytest.fixture
def interdit_le_detecteur(monkeypatch):
    """Fait exploser toute tentative de construire le détecteur ONNX, et remplace l'OCR
    par un faux.

    ⚠ On n'interdit PAS l'OCR pour toutes les reprises : `--from <étape>` régénère cette
    étape **et toutes les suivantes** (cf. docstring de `process_volume`), donc
    `--from nettoyage` refait aussi l'OCR. Voir
    `test_from_nettoyage_reinvalide_l_ocr_alors_qu_il_n_en_depend_pas`, qui documente que
    cette cascade est un gaspillage réel."""
    import manga.detection as det
    import manga.ocr as ocr_mod

    def _boom(*a, **k):
        raise AssertionError("une reprise en cache ne doit pas charger le détecteur ONNX")

    _FauxOCR.appels = 0
    monkeypatch.setattr(det, "BubbleDetector", _boom)
    monkeypatch.setattr(ocr_mod, "MangaOCR", _FauxOCR)


def test_from_rendu_ne_charge_aucun_modele(tmp_path, interdit_le_detecteur):
    """`--from rendu` : tout est en cache, seul le lettrage est refait."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    config = _config(tmp_path)

    assert process_volume("MonManga", "Vol.1", config, reporter=Reporter(),
                          restart_from="rendu") is True
    assert checkpoints.final_page_path(build_dir, 1).exists()


def test_from_nettoyage_ne_charge_pas_le_detecteur(tmp_path, interdit_le_detecteur):
    """`--from nettoyage` : la commande de vérification du lot 1. Régénère `pages_clean/`
    à partir des régions en cache, sans détection ni OCR."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    clean_path = checkpoints.clean_page_path(build_dir, 1)
    clean_path.unlink()                      # à régénérer

    config = _config(tmp_path)
    assert process_volume("MonManga", "Vol.1", config, reporter=Reporter(),
                          restart_from="nettoyage") is True
    assert clean_path.exists()


def test_from_nettoyage_ne_reinvalide_PAS_l_ocr(tmp_path, interdit_le_detecteur):
    """`nettoyage` et `ocr` sont des **frères**, pas une chaîne : `ocr` lit l'image
    d'origine et les régions, jamais la page nettoyée (cf. `read_all(image, regions)`).
    Refaire le nettoyage ne doit donc pas coûter un OCR ni une traduction.

    Sur le tome de 150 planches, la cascade linéaire coûtait ~38 minutes (5,6 s/page d'OCR
    + 9,7 s/page de traduction, appels LLM compris) pour un résultat identique au bit près.
    C'est aussi ce qui rendait fausse la commande de vérification « rejouer sans aucun
    appel LLM »."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    clean_path = checkpoints.clean_page_path(build_dir, 1)
    clean_path.unlink()

    process_volume("MonManga", "Vol.1", _config(tmp_path), reporter=Reporter(),
                   restart_from="nettoyage")

    assert _FauxOCR.appels == 0, "le nettoyage ne doit pas déclencher d'OCR"
    assert clean_path.exists()


def test_from_ocr_refait_bien_l_ocr(tmp_path, interdit_le_detecteur):
    """Le contre-exemple : demander explicitement `--from ocr` doit refaire l'OCR."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    process_volume("MonManga", "Vol.1", _config(tmp_path), reporter=Reporter(),
                   restart_from="ocr")
    assert _FauxOCR.appels == 1


def test_un_cache_d_ocr_absent_declenche_l_ocr_meme_sans_from(tmp_path, interdit_le_detecteur):
    """Une étape dont le cache manque doit être calculée, `--from` ou pas."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=False, avec_trad=False)
    process_volume("MonManga", "Vol.1", _config(tmp_path), reporter=Reporter())
    assert _FauxOCR.appels == 1
    assert checkpoints.load_ocr(checkpoints.page_checkpoint_dir(build_dir, 1)) is not None


def test_from_rendu_ne_refait_PAS_l_ocr(tmp_path, interdit_le_detecteur):
    """Le contre-exemple : `--from rendu` est bien la reprise la plus économe."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    process_volume("MonManga", "Vol.1", _config(tmp_path), reporter=Reporter(),
                   restart_from="rendu")
    assert _FauxOCR.appels == 0


def test_le_nettoyage_en_cache_produit_une_bulle_BLANCHE(tmp_path, interdit_le_detecteur):
    """Le critère chiffré du lot 1, sur une planche synthétique : plus aucun blob gris.
    La médiane de l'intérieur de la bulle doit être blanche, pas la couleur de la case."""
    from pipeline.reporter import Reporter

    from manga.clean import analyze_regions
    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    checkpoints.clean_page_path(build_dir, 1).unlink()
    config = _config(tmp_path)
    process_volume("MonManga", "Vol.1", config, reporter=Reporter(),
                   restart_from="nettoyage")

    clean_img = Image.open(checkpoints.clean_page_path(build_dir, 1)).convert("RGB")
    region = BubbleRegion(bbox=BOX, mask=_masque_ellipse(), score=0.9, cls=0)
    interior = analyze_regions(_planche(), [region])[0].interior
    median = np.median(np.asarray(clean_img)[interior], axis=0)
    assert median.min() >= 200, f"blob sombre résiduel : {median}"


def test_le_dessin_hors_bulle_est_intact_apres_un_run(tmp_path, interdit_le_detecteur):
    """L'invariant fondateur, vérifié de bout en bout à travers l'orchestrateur (et pas
    seulement en appelant `clean_bubbles` directement)."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    checkpoints.clean_page_path(build_dir, 1).unlink()
    process_volume("MonManga", "Vol.1", _config(tmp_path), reporter=Reporter(),
                   restart_from="nettoyage")

    origine = np.asarray(_planche())
    clean_arr = np.asarray(
        Image.open(checkpoints.clean_page_path(build_dir, 1)).convert("RGB"))
    dehors = ~_masque_ellipse()
    assert np.array_equal(clean_arr[dehors], origine[dehors])


def test_un_run_INTERROMPU_produit_quand_meme_le_CBZ(tmp_path, interdit_le_detecteur,
                                                     monkeypatch):
    """LE bug n° 4 du diagnostic. `_render_outputs` n'était atteint qu'APRÈS la boucle des
    pages, et tout `return False` sur STOP/Ctrl+C sortait avant l'assemblage — **même quand
    les 150 pages étaient déjà sur disque**. Relancer un tome complet puis l'interrompre ne
    produisait donc jamais d'archive. Défaut de structure, pas de `build_cbz`."""
    import zipfile

    from pipeline import control
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    # une page finale déjà présente, comme après un premier run complet
    _planche().save(checkpoints.final_page_path(build_dir, 1))

    monkeypatch.setattr(control, "should_stop", lambda _d: True)   # arrêt demandé
    config = _config(tmp_path)
    assert process_volume("MonManga", "Vol.1", config, reporter=Reporter()) is False

    cbz = build_dir / "MonManga_Vol.1.cbz"
    assert cbz.exists(), "l'archive doit être écrite même sur arrêt"
    with zipfile.ZipFile(cbz) as zf:
        assert "page_0001.png" in zf.namelist()
        assert zf.namelist()[0] == "ComicInfo.xml"


def test_assembler_seul_ne_retraduit_rien(tmp_path, interdit_le_detecteur):
    """`--assembler` : uniquement l'assemblage, depuis pages_out/."""
    import zipfile

    from manga.orchestrator_manga import assemble_outputs

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    for i in (1,):
        _planche().save(checkpoints.final_page_path(build_dir, i))

    sorties = assemble_outputs(build_dir, _config(tmp_path)["manga"], "MonManga", "Vol.1")
    cbz = build_dir / "MonManga_Vol.1.cbz"
    assert cbz.exists() and str(cbz) in sorties
    with zipfile.ZipFile(cbz) as zf:
        assert "YesAndRightToLeft" in zf.read("ComicInfo.xml").decode("utf-8")


def test_le_rapport_est_ecrit_a_la_fin_du_run(tmp_path, interdit_le_detecteur):
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    process_volume("MonManga", "Vol.1", _config(tmp_path), reporter=Reporter(),
                   restart_from="rendu")
    rapport = build_dir / "RAPPORT.md"
    assert rapport.exists()
    texte = rapport.read_text(encoding="utf-8")
    assert "Rapport manga — MonManga / Vol.1" in texte
    assert "Pages : 1 analysée(s) sur 1" in texte
    # le qa.json par page est bien persisté
    assert (checkpoints.page_checkpoint_dir(build_dir, 1) / "qa.json").exists()


def test_une_page_deja_finie_est_sautee_sans_modele(tmp_path, interdit_le_detecteur):
    """Reprise nominale (sans --from) : la page finale existe, rien à recalculer."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    build_dir = _semer(tmp_path, avec_clean=True, avec_ocr=True, avec_trad=True)
    final = checkpoints.final_page_path(build_dir, 1)
    final.parent.mkdir(parents=True, exist_ok=True)
    _planche().save(final)

    assert process_volume("MonManga", "Vol.1", _config(tmp_path),
                          reporter=Reporter()) is True
