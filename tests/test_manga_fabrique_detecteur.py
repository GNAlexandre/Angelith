# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`BubbleDetector.depuis_config` est le SEUL point de construction du détecteur.

Il y en avait trois, copiés les uns sur les autres, et ils avaient déjà divergé : le
correctif webtoon a ajouté `fenetrage` à l'orchestrateur et à `tools/apercu_detection.py`,
et manqué `manga/services.py` — où les réglages `fenetre_*` de l'utilisateur étaient donc
silencieusement perdus. Invisible, parce que ce troisième chemin n'a aucun appelant
aujourd'hui : du code mort porteur d'un bug déjà cassé.

Ces tests ne chargent aucun modèle — c'est le CÂBLAGE qu'ils vérifient, pas l'inférence."""
import pytest

from manga import detection, services, text_detection


@pytest.fixture
def espion(monkeypatch):
    """Remplace `BubbleDetector.__init__` par un enregistreur d'arguments."""
    vus = {}

    def _init(self, model_path, providers=None, conf_threshold=None, iou_threshold=None,
              *, telechargement_auto=True, model_url=None, dire=None, fenetrage=None,
              input_size=detection.INPUT_SIZE, aire_min_frac=detection.AIRE_MIN_FRAC):
        vus.update(model_path=model_path, providers=providers, conf_threshold=conf_threshold,
                   iou_threshold=iou_threshold, telechargement_auto=telechargement_auto,
                   model_url=model_url, fenetrage=fenetrage, input_size=input_size,
                   aire_min_frac=aire_min_frac)

    monkeypatch.setattr(detection.BubbleDetector, "__init__", _init)
    return vus


CONFIG = {
    "model_path": "manga_models/bubble_detector.onnx",
    "providers": ["CPUExecutionProvider"],
    "conf_threshold": 0.42,
    "iou_threshold": 0.55,
    "fenetre_hauteur": 2160,
    "fenetre_ratio_min": 3.0,
    "fenetre_recouvrement": 0.2,
}


def test_la_fabrique_transmet_le_fenetrage(espion):
    """Le défaut qui a motivé l'extraction : sans `fenetrage`, une bulle de webtoon arrive au
    réseau en 26×32 px et n'est pas émise du tout."""
    detection.BubbleDetector.depuis_config(CONFIG)

    assert espion["fenetrage"]["fenetre_hauteur"] == 2160
    assert espion["fenetrage"]["fenetre_ratio_min"] == 3.0
    assert espion["fenetrage"]["fenetre_recouvrement"] == 0.2


def test_services_construit_par_la_fabrique(espion):
    """`Services.detecteur()` était la copie divergée. Il doit désormais passer par la même
    fabrique — donc transmettre le fenêtrage, ce qu'il ne faisait pas."""
    svc = services.Services({"manga": {"detection": CONFIG}}, "Projet", langue="ja")
    svc.detecteur()

    assert espion["fenetrage"]["fenetre_hauteur"] == 2160
    assert espion["conf_threshold"] == 0.42
    assert espion["iou_threshold"] == 0.55


def test_les_defauts_ne_vivent_qu_ici(espion):
    """Une config qui ne dit rien doit retomber sur les constantes de `manga.detection`, et
    non sur des littéraux recopiés dans chaque appelant."""
    detection.BubbleDetector.depuis_config({"model_path": "x.onnx"})

    assert espion["conf_threshold"] == detection.CONF_THRESHOLD
    assert espion["iou_threshold"] == detection.IOU_THRESHOLD
    assert espion["telechargement_auto"] is True
    assert espion["model_url"] is None
    # Lot 12 : deux réglages de plus, branchés au MÊME endroit et pas dans les appelants.
    assert espion["input_size"] == detection.INPUT_SIZE
    assert espion["aire_min_frac"] == detection.AIRE_MIN_FRAC


def test_la_fabrique_transmet_la_RESOLUTION_et_laire_minimale(espion):
    """`input_size` était une constante de module que rien ne remontait — ni paramètre de
    `__init__`, ni clé de config — alors que les poids livrés (`model_dynamic.onnx`) sont un
    export à axes dynamiques qui accepte n'importe quelle résolution.

    C'est le plus gros levier du lot 12 : à 1024, la résolution effective est multipliée par
    1,6 sur TOUTES les planches, **sans une seule inférence supplémentaire** — là où le
    fenêtrage en paie une par fenêtre."""
    detection.BubbleDetector.depuis_config(
        {**CONFIG, "input_size": 1024, "aire_min_frac": 0.0005})

    assert espion["input_size"] == 1024
    assert espion["aire_min_frac"] == pytest.approx(0.0005)


def test_la_resolution_venue_du_YAML_est_un_ENTIER(espion):
    """Même raison que pour les seuils : un `input_size: "1024"` remonterait en chaîne jusqu'à
    `_letterbox`, où il échouerait loin de sa cause."""
    detection.BubbleDetector.depuis_config({**CONFIG, "input_size": "1024"})

    assert espion["input_size"] == 1024 and isinstance(espion["input_size"], int)


def test_les_seuils_sont_des_flottants(espion):
    """Un `conf_threshold: "0.42"` dans le YAML ne doit pas remonter en chaîne jusqu'au
    filtrage, où la comparaison échouerait loin de sa cause."""
    detection.BubbleDetector.depuis_config({**CONFIG, "conf_threshold": "0.42"})

    assert espion["conf_threshold"] == pytest.approx(0.42)
    assert isinstance(espion["conf_threshold"], float)


def test_detecteur_texte_partage_les_providers(monkeypatch):
    """Les deux modèles tournent sur le même backend : `providers` vient de
    `manga.detection`, pas de `manga.onomatopees`."""
    vus = {}

    def _init(self, model_path, providers=None, *, telechargement_auto=True,
              model_url=None, dire=None):
        vus.update(model_path=model_path, providers=providers)

    monkeypatch.setattr(text_detection.TextDetector, "__init__", _init)
    text_detection.TextDetector.depuis_config(
        {"model_path": "manga_models/text_detector.onnx"},
        {"providers": ["CUDAExecutionProvider"]})

    assert vus["providers"] == ["CUDAExecutionProvider"]
    assert vus["model_path"] == "manga_models/text_detector.onnx"
