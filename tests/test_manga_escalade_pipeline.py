# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'escalade DANS la boucle de l'orchestrateur — lot 12, L4.2.

`tests/test_manga_escalade.py` couvre les décideurs (réglages livrés, test d'encre, arbitre).
Ici on vérifie le CÂBLAGE : que le déclencheur soit réellement consulté, que la seconde
inférence parte au bon réglage, que ce qui est écrit soit ce que l'arbitre a retenu, et que la
provenance atterrisse dans `regions.json` — donc dans `RAPPORT.md`.

Aucun modèle : le détecteur est un double qui compte ses appels et rend ce qu'on lui dit.
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
TAILLE = (844, 1200)


def _config(tmp_path, **detection):
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    config["chemins"]["prompts"] = str(ROOT / "prompts")
    config.setdefault("langues", {})["packs"] = str(ROOT / "langues")
    config["manga"]["detection"]["model_path"] = str(tmp_path / "absent.onnx")
    config["manga"]["detection"]["telechargement_auto"] = False
    config["manga"]["detection"].update(detection)
    # La passe onomatopées est un AUTRE modèle et un autre sujet — et c'est précisément le
    # point de L4.8 : le déclencheur ne doit pas en dépendre.
    config["manga"]["onomatopees"]["actif"] = False
    # Le PSD à calques coûte à lui seul l'essentiel du temps de ces tests (~25 s par planche
    # portant une bulle), et aucun d'eux n'affirme quoi que ce soit sur le lettrage : ce fichier
    # teste le CÂBLAGE de la détection. `test_manga_psd.py` couvre le PSD.
    config["manga"]["rendu"]["formats"] = ["images"]
    config.setdefault("options", {})["dry_run"] = True
    return config


def _planche(dessinee: bool) -> Image.Image:
    img = Image.new("RGB", TAILLE, "white")
    if dessinee:
        d = ImageDraw.Draw(img)
        d.rectangle([60, 60, 780, 1100], outline="black", width=10)
        d.ellipse([150, 200, 650, 600], outline="black", width=8)
    return img


def _region(x0, y0, x1, y1, score=0.95) -> BubbleRegion:
    m = np.zeros((TAILLE[1], TAILLE[0]), dtype=bool)
    m[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=(x0, y0, x1, y1), mask=m, score=score, cls=0)


class _Detecteur:
    """Double du détecteur : rend `[]` à la résolution nominale, des bulles à l'escalade.

    C'est exactement le cas des 188 planches du corpus — le réseau ne voit rien à 640, et
    voit à 1024."""

    def __init__(self, trouvailles):
        self.trouvailles = trouvailles
        self.appels: list[dict] = []

    def detect(self, image, conf_threshold=None, iou_threshold=None, input_size=None,
               rejets=None, sautees=None):
        # `sautees` est arrivé au lot 14 : il compte les FENÊTRES auxquelles la porte d'encre
        # n'a pas payé d'inférence. Compteur distinct de `rejets`, parce qu'une détection
        # écartée après examen et une portion de planche jamais regardée ne se lisent pas de
        # la même façon. La doublure honore le contrat complet, sinon elle ne teste plus le
        # chemin réel — et un `TypeError` ici se lit « planche en ÉCHEC », pas « signature
        # obsolète ».
        self.appels.append({"conf": conf_threshold, "input_size": input_size})
        if rejets is not None:
            rejets["boite_degeneree"] = rejets.get("boite_degeneree", 0) + 1
        return [] if input_size is None else list(self.trouvailles)


@pytest.fixture
def monter(tmp_path, monkeypatch):
    """Sème un tome d'une planche et branche le double + un OCR/nettoyage inoffensifs."""

    def _monter(dessinee=True, trouvailles=(), uniformites=None, **detection):
        import manga.clean as clean_mod
        import manga.detection as det_mod
        import manga.ocr_routeur as routeur

        vol = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
        vol.mkdir(parents=True, exist_ok=True)
        _planche(dessinee).save(vol / "page_0001.png")

        double = _Detecteur(trouvailles)
        monkeypatch.setattr(det_mod.BubbleDetector, "depuis_config",
                            classmethod(lambda cls, cfg, *, dire=None: double))

        # `analyze_regions` décide du véto de l'arbitre : on lui dicte l'uniformité de chaque
        # région, c'est la seule chose que l'escalade lui demande.
        vraie_analyse = clean_mod.analyze_regions

        def _analyse(image, regions, cfg=None):
            styles = vraie_analyse(image, regions, cfg)
            if uniformites is not None:
                for k, s in enumerate(styles):
                    object.__setattr__(s, "uniformity", uniformites.get(k, 0.9)) \
                        if hasattr(s, "__dataclass_fields__") else None
            return styles

        if uniformites is not None:
            monkeypatch.setattr(clean_mod, "analyze_regions", _analyse)

        class _OCR:
            def read_all(self, image, regions, styles=None, cfg=None):
                return ["テスト" for _ in regions]

        monkeypatch.setattr(routeur, "lecteur_pour",
                            lambda *a, **k: _OCR())
        return double, _config(tmp_path, **detection), tmp_path

    return _monter


def _lancer(config):
    from manga.orchestrator_manga import process_volume
    return process_volume("MonManga", "Vol.1", config, reporter=Reporter())


def _regions_ecrites(tmp_path):
    build = tmp_path / "build" / "MonManga" / "Vol.1" / "manga"
    ckpt = checkpoints.page_checkpoint_dir(build, 1)
    return checkpoints.load_regions(ckpt) or [], checkpoints.load_detection_meta(ckpt)


# --------------------------------------------------------------------------- #

def test_une_planche_MUETTE_et_encree_declenche_une_seconde_inference(monter):
    """Le cas du lot : `len(regions) == 0` ne déclenchait RIEN. Entre la détection et
    l'arbitre, il n'y avait aucun test de longueur, et un `regions.json` vide s'écrivait en
    silence."""
    double, config, tmp = monter(dessinee=True, trouvailles=[_region(200, 250, 600, 550)])
    _lancer(config)

    assert len(double.appels) == 2, "la planche muette n'a pas été relancée"
    assert double.appels[0]["input_size"] is None          # nominal : le réglage du tome
    assert double.appels[1]["input_size"] == 1024          # escalade : la résolution relevée
    assert double.appels[1]["conf"] == pytest.approx(0.20)

    regions, meta = _regions_ecrites(tmp)
    assert len(regions) == 1, "la bulle gagnée n'a pas été écrite"
    assert meta["escalade"]["motif"] == "zero_bulle_encree"
    assert meta["escalade"]["accepte"] is True
    assert (meta["escalade"]["avant"], meta["escalade"]["apres"]) == (0, 1)


def test_une_planche_BLANCHE_ne_declenche_rien(monter):
    """Une page de garde n'a rien à traduire. Escalader dessus paierait une inférence pour
    rien, sur chaque tome et à chaque relance — et c'est ce que le test d'encre évite."""
    double, config, tmp = monter(dessinee=False, trouvailles=[_region(200, 250, 600, 550)])
    _lancer(config)

    assert len(double.appels) == 1
    regions, meta = _regions_ecrites(tmp)
    assert regions == [] and "escalade" not in meta


def test_lescalade_DESACTIVEE_rend_le_comportement_davant(monter):
    double, config, tmp = monter(dessinee=True, trouvailles=[_region(200, 250, 600, 550)],
                                 escalade={"actif": False})
    _lancer(config)

    assert len(double.appels) == 1
    assert _regions_ecrites(tmp)[0] == []


def test_ce_qui_est_ECRIT_est_ce_que_larbitre_a_retenu(monter):
    """Sur une planche à référence vide l'arbitre SÉLECTIONNE : une bulle nettoyable est une
    bulle, une bulle qu'on ne sait pas peindre est du décor. Les deux ballons partent, la
    trame reste dehors."""
    trouvailles = [_region(150, 200, 500, 500), _region(520, 200, 780, 420),
                   _region(100, 900, 160, 960)]
    double, config, tmp = monter(dessinee=True, trouvailles=trouvailles,
                                 uniformites={0: 0.92, 1: 0.88, 2: 0.10})
    _lancer(config)

    regions, meta = _regions_ecrites(tmp)
    assert len(regions) == 2, "la région non nettoyable a été écrite"
    assert meta["escalade"]["apres"] == 2


def test_une_escalade_qui_ne_trouve_QUE_du_dessin_nemporte_rien(monter):
    double, config, tmp = monter(dessinee=True,
                                 trouvailles=[_region(100, 900, 200, 1000)],
                                 uniformites={0: 0.10})
    _lancer(config)

    regions, meta = _regions_ecrites(tmp)
    assert regions == []
    # …mais la TRACE reste : une escalade refusée est une information sur la planche.
    assert meta["escalade"]["accepte"] is False
    assert meta["escalade"]["motif"] == "zero_bulle_encree"


def test_les_rejets_du_post_traitement_sont_PERSISTES(monter):
    """Un filtre muet est la façon dont on perd les treize planches suivantes. `RAPPORT.md`
    les relit depuis `regions.json` — pas depuis `qa.json`, qui manque sur 423 des
    1 513 planches du corpus de mesure."""
    double, config, tmp = monter(dessinee=True, trouvailles=[_region(200, 250, 600, 550)])
    _lancer(config)

    _regions, meta = _regions_ecrites(tmp)
    assert meta["rejets"] == {"boite_degeneree": 2}      # une par inférence, cumulées


# --------------------------------------------------------------------------- #
# Relance ciblée `--conf` sur une planche à cache VIDE (lot 12, L4.2 point 2)
# --------------------------------------------------------------------------- #

def _relance(config, **kw):
    from manga.orchestrator_manga import process_volume
    return process_volume("MonManga", "Vol.1", config, reporter=Reporter(),
                          only_page=1, restart_from="detection", **kw)


def test_le_verdict_est_CONTRAIGNANT_meme_sur_un_cache_vide(monter):
    """Le défaut exact : la condition d'écriture était `if reference and not verdict.accepte`.
    Sur une planche à zéro bulle en cache — c'est-à-dire sur exactement le cas où l'utilisateur
    baisse `--conf` — le premier terme la désarmait entièrement. La trace affichait « REFUSÉ »
    juste avant que `save_regions` écrive quand même.

    Ici l'escalade est désarmée : c'est bien le chemin `--conf` qu'on exerce, seul."""
    trouvailles = [_region(150, 200, 500, 500), _region(100, 900, 200, 1000)]
    double, config, tmp = monter(dessinee=True, trouvailles=trouvailles,
                                 uniformites={0: 0.10, 1: 0.10},
                                 escalade={"actif": False})
    # Le double rend ses trouvailles dès qu'on lui passe une résolution ; `--conf` seul ne le
    # fait pas. On lui demande donc explicitement les deux.
    double.detect = lambda image, conf_threshold=None, iou_threshold=None, \
        input_size=None, rejets=None, sautees=None: (
            double.appels.append({"conf": conf_threshold, "input_size": input_size})
            or list(trouvailles))

    _relance(config, conf_threshold=0.10)

    regions, _meta = _regions_ecrites(tmp)
    assert regions == [], "des régions que le nettoyeur refuserait ont été écrites"


def test_sur_un_cache_vide_les_candidates_NETTOYABLES_sont_ecrites(monter):
    """Le pendant : le refus est contraignant, mais il n'est pas systématique. Une candidate
    que le nettoyeur accepterait est une bulle, et elle part."""
    trouvailles = [_region(150, 200, 500, 500), _region(100, 900, 200, 1000)]
    double, config, tmp = monter(dessinee=True, trouvailles=trouvailles,
                                 uniformites={0: 0.92, 1: 0.10},
                                 escalade={"actif": False})
    double.detect = lambda image, conf_threshold=None, iou_threshold=None, \
        input_size=None, rejets=None, sautees=None: list(trouvailles)

    _relance(config, conf_threshold=0.10)

    regions, meta = _regions_ecrites(tmp)
    assert len(regions) == 1, "la sélection candidate par candidate n'a pas eu lieu"
    assert meta["conf_threshold"] == 0.10        # la provenance reste écrite
