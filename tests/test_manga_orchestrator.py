# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Test de bout en bout (dry-run) de l'orchestrateur manga : détection + OCR réels,
traduction en dry-run (pass-through, sans appel LLM), nettoyage + lettrage + sauvegarde.
Sauté si les extras manga (onnxruntime, manga-ocr, modèle téléchargé) sont absents."""
from pathlib import Path

import pytest
import yaml

pytest.importorskip("onnxruntime")
pytest.importorskip("manga_ocr")

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "manga_models" / "bubble_detector.onnx"
# 250 s mesurees : ces 17 tests exercent le VRAI detecteur de bulles, et c'est leur
# raison d'etre. `pytest -m "not modeles"` les ecarte sur une machine secondaire.
pytestmark = [pytest.mark.modeles, pytest.mark.lent, pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason="modèle de détection non téléchargé (voir manga_models/README.md)")]


def _base_config(tmp_path):
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    # On règle la racine, PAS `manga.chemins` : la brique en hérite par fusion profonde
    # depuis le lot 2.3. Les deux lignes recopiaient auparavant `sources`/`build` sous
    # `manga:`, exactement la duplication que le socle a supprimée — ces fixtures sont donc
    # aussi le test de bout en bout de cet héritage.
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    config["manga"]["detection"]["model_path"] = str(MODEL_PATH)
    # ⚠ Le `skipif` de ce fichier porte sur le détecteur de BULLES, qui est bien ce que ces
    # 17 tests exercent. La passe `sfx` est un AUTRE modèle et un autre sujet : aucun test
    # d'ici n'affirme quoi que ce soit sur le texte hors bulle, et elle coûtait pourtant
    # 110 s d'inférence ONNX par planche (profilé). `test_manga_text_detection.py` la couvre.
    config["manga"]["onomatopees"]["actif"] = False
    config["chemins"]["prompts"] = str(ROOT / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    config.setdefault("langues", {})["packs"] = str(ROOT / "langues")
    config.setdefault("options", {})["dry_run"] = True
    return config


def test_orchestrator_dry_run_end_to_end(tmp_path, synthetic_manga_page):
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    completed = process_volume("MonManga", "Vol.1", config, reporter=Reporter())
    assert completed is True

    out_page = tmp_path / "build" / "MonManga" / "Vol.1" / "manga" / "pages_out" / "page_0001.png"
    assert out_page.exists()


def test_orchestrator_skips_already_generated_pages_unless_forced(tmp_path, synthetic_manga_page):
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    process_volume("MonManga", "Vol.1", config, reporter=Reporter())

    out_page = tmp_path / "build" / "MonManga" / "Vol.1" / "manga" / "pages_out" / "page_0001.png"
    first_mtime = out_page.stat().st_mtime_ns

    process_volume("MonManga", "Vol.1", config, reporter=Reporter())
    assert out_page.stat().st_mtime_ns == first_mtime   # sauté (déjà généré)

    process_volume("MonManga", "Vol.1", config, reporter=Reporter(), force=True)
    assert out_page.stat().st_mtime_ns != first_mtime   # refait (--force)


def _manga_build_dir(tmp_path):
    return tmp_path / "build" / "MonManga" / "Vol.1" / "manga"


def test_orchestrator_produces_visible_clean_pages(tmp_path, synthetic_manga_page):
    """Demande explicite : pouvoir VOIR les pages nettoyées (bulles vidées, sans
    texte) — elles doivent exister dans un dossier normal, pas dans le cache caché."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    process_volume("MonManga", "Vol.1", config, reporter=Reporter())

    clean_page = _manga_build_dir(tmp_path) / "pages_clean" / "page_0001.png"
    assert clean_page.exists()


def test_restart_from_rendu_reuses_all_earlier_caches(tmp_path, synthetic_manga_page):
    """--from rendu : ne redessine QUE le lettrage, à partir des pages clean +
    traductions déjà en cache — détection/nettoyage/OCR ne doivent PAS être refaits
    (vérifié par les dates de modification des fichiers de cache, inchangées)."""
    from pipeline.reporter import Reporter

    from manga import checkpoints
    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    process_volume("MonManga", "Vol.1", config, reporter=Reporter())

    build_dir = _manga_build_dir(tmp_path)
    ckpt_dir = checkpoints.page_checkpoint_dir(build_dir, 1)
    clean_path = checkpoints.clean_page_path(build_dir, 1)
    out_path = checkpoints.final_page_path(build_dir, 1)

    masks_mtime = (ckpt_dir / "masks.png").stat().st_mtime_ns
    ocr_mtime = (ckpt_dir / "ocr.json").stat().st_mtime_ns
    clean_mtime = clean_path.stat().st_mtime_ns

    # Édite manuellement la traduction en cache (simule un changement de police/relecture).
    checkpoints.save_traduction(ckpt_dir, ["TEXTE ÉDITÉ MANUELLEMENT"])

    process_volume("MonManga", "Vol.1", config, reporter=Reporter(), restart_from="rendu")

    # Détection/nettoyage/OCR NON refaits (caches intacts) ; seul le rendu a changé.
    assert (ckpt_dir / "masks.png").stat().st_mtime_ns == masks_mtime
    assert (ckpt_dir / "ocr.json").stat().st_mtime_ns == ocr_mtime
    assert clean_path.stat().st_mtime_ns == clean_mtime
    assert out_path.exists()


def test_restart_from_ocr_reuses_detection_and_clean_only(tmp_path, synthetic_manga_page):
    """--from ocr : réutilise détection+nettoyage (masks/clean inchangés), mais
    refait OCR → traduction → rendu (ocr.json doit être réécrit)."""
    from pipeline.reporter import Reporter

    from manga import checkpoints
    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    process_volume("MonManga", "Vol.1", config, reporter=Reporter())

    build_dir = _manga_build_dir(tmp_path)
    ckpt_dir = checkpoints.page_checkpoint_dir(build_dir, 1)
    clean_path = checkpoints.clean_page_path(build_dir, 1)

    masks_mtime = (ckpt_dir / "masks.png").stat().st_mtime_ns
    clean_mtime = clean_path.stat().st_mtime_ns

    process_volume("MonManga", "Vol.1", config, reporter=Reporter(), restart_from="ocr")

    assert (ckpt_dir / "masks.png").stat().st_mtime_ns == masks_mtime   # détection réutilisée
    assert clean_path.stat().st_mtime_ns == clean_mtime                # nettoyage réutilisé
    assert checkpoints.load_ocr(ckpt_dir) is not None                   # OCR bien refait


def test_verbose_reports_per_stage_timing_and_speed(tmp_path, synthetic_manga_page, capsys):
    """--verbose (config.options.verbose) doit afficher le temps de CHAQUE étape
    (détection/nettoyage/ocr/rendu) ainsi que les tokens/vitesse de la traduction —
    miroir du --verbose côté LN."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    config["options"]["verbose"] = True
    process_volume("MonManga", "Vol.1", config, reporter=Reporter())

    out = capsys.readouterr().out
    assert "[detection] page 1/1" in out
    assert "[nettoyage] page 1/1" in out
    assert "[ocr] page 1/1" in out
    assert "[rendu] page 1/1" in out
    # dry-run : pas de vrai client LLM → pas de ligne de CHRONO [traduction] (comme le LN,
    # qui ne suit tokens/vitesse que si un client LLM réel est utilisé pour l'agent).
    # ⚠ On cible la ligne de chrono (`page 1/1 :`) et non la sous-chaîne `[traduction]` seule :
    # en dry-run la « traduction » est le texte OCR japonais, donc le garde-fou
    # `japonais_residuel` émet légitimement un AVERTISSEMENT « ⚠ [traduction] page 1 : … ».
    # L'assertion large échouait donc dès que le modèle de détection était présent — ce qui
    # n'arrivait pas tant que ce test était sauté faute de poids sur la machine.
    assert "[traduction] page 1/1" not in out


def test_without_verbose_no_per_stage_lines(tmp_path, synthetic_manga_page, capsys):
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    process_volume("MonManga", "Vol.1", config, reporter=Reporter())

    out = capsys.readouterr().out
    assert "[detection]" not in out


def test_only_page_restricts_processing(tmp_path, synthetic_manga_page):
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")
    img.save(vol_dir / "page_0002.png")

    config = _base_config(tmp_path)
    process_volume("MonManga", "Vol.1", config, reporter=Reporter(), only_page=1)

    build_dir = _manga_build_dir(tmp_path)
    assert (build_dir / "pages_out" / "page_0001.png").exists()
    assert not (build_dir / "pages_out" / "page_0002.png").exists()


def test_une_page_hors_bornes_echoue_SANS_rien_reecrire(tmp_path, synthetic_manga_page):
    """`--page 999` ne traitait rien mais allait quand même au bout : `RAPPORT.md` était
    réécrit et le CBZ réencodé, si bien qu'une faute de frappe passait pour un run réussi."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    assert process_volume("MonManga", "Vol.1", config, reporter=Reporter(),
                          only_page=1) is True
    build_dir = _manga_build_dir(tmp_path)
    rapport = build_dir / "RAPPORT.md"
    empreinte = rapport.read_bytes()

    for page in (999, 0, -1):
        assert process_volume("MonManga", "Vol.1", config, reporter=Reporter(),
                              only_page=page) is False, page
        assert rapport.read_bytes() == empreinte, page


def test_conf_et_iou_EXIGENT_une_page(tmp_path, synthetic_manga_page):
    """Un seuil pour tout le tome appartient à `config.yaml`, où il est tracé et relu au run
    suivant. En ligne de commande, il s'appliquerait à 150 planches sans laisser de trace."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    assert process_volume("MonManga", "Vol.1", config, reporter=Reporter()) is True
    build_dir = _manga_build_dir(tmp_path)
    empreinte = (build_dir / "RAPPORT.md").read_bytes()

    for kw in ({"conf_threshold": 0.25}, {"iou_threshold": 0.6},
               {"conf_threshold": 0.25, "iou_threshold": 0.6}):
        assert process_volume("MonManga", "Vol.1", config, reporter=Reporter(), **kw) is False
        assert (build_dir / "RAPPORT.md").read_bytes() == empreinte


def test_une_relance_de_seuils_SANS_gain_ne_touche_a_rien(tmp_path, synthetic_manga_page):
    """Le doute profite à la détection en place : elle a déjà été payée en OCR et en
    traduction. Relancer aux seuils du tome ne change rien, donc rien ne doit être réécrit."""
    from pipeline.reporter import Reporter

    from manga.orchestrator_manga import process_volume

    img, _bubble_box, _text = synthetic_manga_page
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    img.save(vol_dir / "page_0001.png")

    config = _base_config(tmp_path)
    process_volume("MonManga", "Vol.1", config, reporter=Reporter())
    build_dir = _manga_build_dir(tmp_path)
    from manga import checkpoints
    ckpt = checkpoints.page_checkpoint_dir(build_dir, 1)
    avant_ocr = (ckpt / checkpoints.OCR_FILENAME).read_bytes()
    n_avant = len(checkpoints.load_regions(ckpt) or [])

    seuils = config["manga"]["detection"]
    process_volume("MonManga", "Vol.1", config, reporter=Reporter(), only_page=1,
                   conf_threshold=float(seuils.get("conf_threshold", 0.35)),
                   iou_threshold=float(seuils.get("iou_threshold", 0.45)))

    assert len(checkpoints.load_regions(ckpt) or []) == n_avant
    assert (ckpt / checkpoints.OCR_FILENAME).read_bytes() == avant_ocr
    assert checkpoints.load_detection_meta(ckpt) == {}      # rien n'a été réécrit


# --------------------------------------------------------------------------- #
# Lot 14 — le contexte inter-planches, lu depuis les checkpoints
#
# ⚠ Depuis le lot 15, chaque ligne porte son ORIGINE (« - Planche N−1 : … ») et le budget est
# RÉPARTI entre les planches au lieu d'être tronqué globalement. Ces tests comparent donc les
# répliques, pas les lignes brutes ; la forme de l'étiquette est testée par
# `tests/test_manga_prompt_planche.py`, qui est l'endroit où elle compte.
# --------------------------------------------------------------------------- #


def _repliques(lignes):
    """Le texte seul, débarrassé de son étiquette d'origine."""
    return [ligne.split(" : ", 1)[-1] for ligne in lignes]

def test_le_contexte_vient_des_planches_qui_PRECEDENT(tmp_path):
    """Sans état de boucle : les trois cas (run complet, run partiel, `--page N`) donnent le
    même contexte, celui des planches réellement précédentes."""
    from manga import checkpoints
    from manga.orchestrator_manga import _contexte_precedent

    for page, textes in ((1, ["Un", "Deux"]), (2, ["Trois"]), (3, ["Quatre", "Cinq"])):
        checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tmp_path, page), textes)

    assert _repliques(_contexte_precedent(tmp_path, 4, 3, 18)) == [
        "Un", "Deux", "Trois", "Quatre", "Cinq"]
    assert _repliques(_contexte_precedent(tmp_path, 4, 1, 18)) == ["Quatre", "Cinq"]


def test_le_contexte_est_amorce_sur_une_planche_ISOLEE(tmp_path):
    """`--page 3` partait avec une fenêtre VIDE, alors que `page_0002/traduction.json` est sur
    le disque depuis le premier run."""
    from manga import checkpoints
    from manga.orchestrator_manga import _contexte_precedent

    checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tmp_path, 2), ["Bonjour"])
    assert _repliques(_contexte_precedent(tmp_path, 3, 3, 18)) == ["Bonjour"]


def test_une_planche_SAUTEE_ne_transmet_plus_un_contexte_perime(tmp_path):
    """LE bug : la variable de boucle n'était pas réinitialisée sur un `continue`, si bien
    qu'un run partiel faisait recevoir à la planche 40 les répliques de la 12. En lisant les
    checkpoints, la planche 40 reçoit la 39, sautée ou non."""
    from manga import checkpoints
    from manga.orchestrator_manga import _contexte_precedent

    checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tmp_path, 12), ["Vieux"])
    checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tmp_path, 39), ["Récent"])
    assert _repliques(_contexte_precedent(tmp_path, 40, 3, 18)) == ["Récent"]


def test_le_contexte_est_plafonne(tmp_path):
    """Le plafond tient toujours — c'est ce qui empêche une planche bavarde de gonfler le
    prompt. ⚠ Ici une seule planche précède, elle prend donc tout le budget ; c'est quand
    plusieurs se partagent la fenêtre que la répartition du lot 15 se voit (cf.
    `tests/test_manga_prompt_planche.py`)."""
    from manga import checkpoints
    from manga.orchestrator_manga import _contexte_precedent

    checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tmp_path, 1),
                                [f"R{i}" for i in range(30)])
    assert len(_contexte_precedent(tmp_path, 2, 3, 18)) == 18


def test_zero_planche_desactive_le_contexte(tmp_path):
    from manga import checkpoints
    from manga.orchestrator_manga import _contexte_precedent

    checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tmp_path, 1), ["Bonjour"])
    assert _contexte_precedent(tmp_path, 2, 0, 18) == []


def test_le_contexte_transmet_l_orthographe_FORCEE(tmp_path):
    """Le cache garde la sortie BRUTE (le forçage s'applique à l'usage). Sans le rejouer, le
    contexte transmettrait les orthographes que le glossaire interdit — l'inverse de son but."""
    from manga import checkpoints
    from manga.orchestrator_manga import _contexte_precedent

    gloss = {"personnages": [{"nom": "Mitsukage", "force": True, "interdits": ["Mikage"]}]}
    checkpoints.save_traduction(checkpoints.page_checkpoint_dir(tmp_path, 1),
                                ["Mikage arrive"])

    assert _repliques(_contexte_precedent(tmp_path, 2, 3, 18, gloss)) == ["Mitsukage arrive"]
