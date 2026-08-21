# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`core/runtime.py` branché sur la brique manga (lot 2.4).

Les quatre fonctions elles-mêmes sont déjà couvertes côté light novel
(`tests/test_orchestrator.py`) — elles n'ont pas changé d'une ligne. Ce qui est nouveau,
c'est que la brique manga les utilise, alors qu'elle n'en avait **aucune** : les incidents
de ses clients LLM partaient sur stdout et étaient perdus, ses sockets restaient pendantes,
et son rapport ne lisait qu'un seul client. Ces tests portent donc sur le branchement, pas
sur les fonctions.

Un run NON dry-run est nécessaire : en dry-run tous les clients valent `None` et il n'y a
rien à brancher, fermer ni agréger.
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


class FauxLLM:
    """Client LLM factice, observable : ce qu'on veut vérifier c'est qui lui parle."""

    instances: list["FauxLLM"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.think = kwargs.get("think")
        self.stats = {"appels": 0, "tokens_generes": 0, "temps_generation": 0.0,
                      "retries": 0, "vides_persistants": 0,
                      "thinking_overflow": 0, "troncature_length": 0}
        self.on_event = None
        self.ferme = 0
        self.last_reason = None
        FauxLLM.instances.append(self)

    def chat(self, modele, system, user, temperature, max_tokens=None, images=None):
        self.stats["appels"] += 1
        self.stats["tokens_generes"] += 20
        self.stats["temps_generation"] += 0.5
        # Incident typique : budget « thinking » épuisé. Le client le signale par son canal
        # `on_event` — `print` par défaut, donc invisible dans perf.log.
        self._event("[llm] budget « thinking » épuisé, réponse tronquée")
        n = sum(1 for ln in user.splitlines() if ln.strip()[:2].rstrip(".").isdigit())
        return "\n".join(f"{i}. Réplique {i}" for i in range(1, max(1, n) + 1))

    def _event(self, msg):
        (self.on_event or print)(msg)

    def close(self):
        self.ferme += 1


def _config(tmp_path: Path, modeles=None) -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    config["chemins"]["prompts"] = str(ROOT / "prompts")
    config["manga"]["detection"]["model_path"] = str(tmp_path / "absent.onnx")
    # ⚠ Neutraliser le détecteur de BULLES ne suffisait pas : la passe `sfx` est
    # délibérément hors du graphe d'invalidation, donc elle tournait même sur un tome dont
    # détection, nettoyage et OCR sont déjà en cache. Profilé sur ce fichier : **554 s sur
    # 564** partaient dans `onnxruntime.run`, soit 110 s par appel — 98 % du temps de tests
    # qui ne mesurent que des statistiques d'appels LLM. Rien ici ne concerne le texte hors
    # bulle ; `test_manga_text_detection.py` s'en charge, sur une image minuscule.
    config["manga"].setdefault("onomatopees", {})["actif"] = False
    if modeles is not None:
        config["manga"]["modeles"] = modeles
    config.setdefault("options", {})["dry_run"] = False   # sinon il n'y a aucun client
    config["options"]["verbose"] = True                   # pour écrire perf.log
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


def _semer(tmp_path: Path) -> Path:
    """Tome d'une page, détection + nettoyage + OCR déjà en cache, traduction À FAIRE :
    c'est l'appel LLM qu'on veut voir passer."""
    vol_dir = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol_dir.mkdir(parents=True)
    page = _planche()
    page.save(vol_dir / "page_0001.png")

    build_dir = tmp_path / "build" / "MonManga" / "Vol.1" / "manga"
    (build_dir / "pages_out").mkdir(parents=True, exist_ok=True)
    (build_dir / "pages_clean").mkdir(parents=True, exist_ok=True)
    ckpt = checkpoints.page_checkpoint_dir(build_dir, 1)
    region = BubbleRegion(bbox=BOX, mask=_masque(), score=0.95, cls=0)
    checkpoints.save_regions(ckpt, [region], page.size)
    from manga.clean import clean_bubbles
    clean_bubbles(page, [region]).save(checkpoints.clean_page_path(build_dir, 1))
    checkpoints.save_ocr(ckpt, ["こんにちは"])
    return build_dir


@pytest.fixture
def faux_llm(monkeypatch):
    """Remplace la vraie classe `LLM` là où `build_agents` la résout."""
    import core.agents as agents_mod
    FauxLLM.instances = []
    monkeypatch.setattr(agents_mod, "LLM", FauxLLM)
    return FauxLLM


def _run(tmp_path, config, reporter):
    from manga.orchestrator_manga import process_volume
    return process_volume("MonManga", "Vol.1", config, reporter=reporter)


def test_les_incidents_du_client_atteignent_perf_log(tmp_path, faux_llm):
    """Défaut corrigé : les messages d'incident partaient sur stdout via un `print()` brut.
    Après un run de nuit sur 150 planches, plus aucune trace de quelle page avait dérapé ni
    pourquoi — et en mode TUI ils corrompaient la barre de progression Live."""
    from core.reporter import Reporter

    build_dir = _semer(tmp_path)
    rep = Reporter()
    rep.set_verbose_log(build_dir / "perf.log")
    assert _run(tmp_path, _config(tmp_path), rep) is True

    perf = (build_dir / "perf.log").read_text(encoding="utf-8")
    assert "budget « thinking » épuisé" in perf


def test_le_canal_dincident_est_bien_celui_du_reporter(tmp_path, faux_llm):
    """Le branchement se fait AVANT la boucle des pages, donc même un run qui ne traduit
    rien laisse les clients câblés."""
    from core.reporter import Reporter

    _semer(tmp_path)
    rep = Reporter()
    _run(tmp_path, _config(tmp_path), rep)
    assert faux_llm.instances, "aucun client construit : le test ne prouve rien"
    for client in faux_llm.instances:
        assert client.on_event == rep.warn


def test_les_sockets_sont_fermees_a_la_fin_du_run(tmp_path, faux_llm):
    """Une socket vers Ollama laissée pendante à chaque run : le LN fermait déjà les
    siennes, la brique manga non."""
    from core.reporter import Reporter

    _semer(tmp_path)
    assert _run(tmp_path, _config(tmp_path), Reporter()) is True
    assert all(c.ferme >= 1 for c in faux_llm.instances)


def test_les_sockets_sont_fermees_aussi_a_larret_propre(tmp_path, faux_llm, monkeypatch):
    """`--stop` est le cas le plus fréquent sur un tome long — c'est là qu'il ne faut
    surtout pas oublier de fermer.

    On patche `should_stop` plutôt que d'écrire le fichier STOP : `process_volume` appelle
    `clear_stop` en entrée (c'est voulu — sinon un arrêt d'hier bloquerait le run
    d'aujourd'hui), donc un STOP posé avant le lancement est effacé et le run va au bout.
    L'arrêt à simuler est bien celui qui survient PENDANT la boucle."""
    import core.control as control_mod
    from core.reporter import Reporter

    _semer(tmp_path)
    monkeypatch.setattr(control_mod, "should_stop", lambda *a, **k: True)
    assert _run(tmp_path, _config(tmp_path), Reporter()) is False
    assert faux_llm.instances and all(c.ferme >= 1 for c in faux_llm.instances)


def test_le_rapport_somme_les_clients_de_tous_les_agents(tmp_path, faux_llm):
    """Le rapport lisait `agents["manga_traducteur"].llm.stats` : le client PAR DÉFAUT.

    Ce n'était pas encore un bug observable — la brique n'a qu'un agent, et il fait tous les
    appels. Ça le devient dès que `endpoint:` fonctionne (lot 2.2) et que le lot 3 branchera
    `terminologue`/`glossariste` : chacun sur son endpoint aura son propre client, et le
    rapport en ignorerait la majorité. C'est le défaut exact que le LN avait mesuré chez lui,
    79 appels annoncés contre 183 réellement tracés dans perf.log.

    Deux agents, deux clients distincts (endpoints différents), tous deux ayant réellement
    travaillé. Le trafic du terminologue était encore SIMULÉ ici jusqu'au lot 4.1 : le droit
    de relever était adossé à l'étape `terminologie`, dont le cache est non bloquant, si bien
    qu'un tome déjà OCRisé ne relevait jamais rien. Depuis qu'il est adossé à la traduction,
    l'agent tourne pour de vrai et le test n'a plus rien à injecter à la main."""
    from core.reporter import Reporter

    build_dir = _semer(tmp_path)
    config = _config(tmp_path, modeles={
        "manga_traducteur": {"model": "m", "endpoint": "reflexion"},
        "terminologue": {"model": "m"}})
    config["manga"]["temperatures"] = {"manga_traducteur": 0.3, "terminologue": 0.2}
    config["llm"]["endpoints"] = {"reflexion": {"think": True}}
    assert _run(tmp_path, config, Reporter()) is True

    from core.runtime import aggregate_llm_stats

    clients = faux_llm.instances
    assert len({id(c) for c in clients}) == 2, "les deux agents doivent avoir des clients distincts"
    assert all(c.stats["appels"] > 0 for c in clients), \
        "traducteur ET terminologue doivent avoir appelé leur propre client"

    agents = {nom: type("A", (), {"llm": c})()
              for nom, c in zip(("manga_traducteur", "terminologue"), clients)}
    total = aggregate_llm_stats(None, agents)
    assert total["appels"] == sum(c.stats["appels"] for c in clients)
    assert total["appels"] > max(c.stats["appels"] for c in clients), \
        "lire un seul client sous-compterait — c'est tout le point de l'agrégation"


def test_un_run_sans_aucun_appel_le_dit_au_lieu_dannoncer_zero(tmp_path, faux_llm):
    """Changement de sortie assumé : une reprise entièrement en cache affichait
    « Appels LLM : 0 · ~0 tok/s », ce qui se lit comme une mesure. Le rapport dit désormais
    qu'il n'y a rien à mesurer — le message existait déjà pour le dry-run."""
    from core.reporter import Reporter

    build_dir = _semer(tmp_path)
    checkpoints.save_traduction(checkpoints.page_checkpoint_dir(build_dir, 1), ["Bonjour"])
    from manga.typeset import typeset_page
    from PIL import Image as _I
    typeset_page(_I.open(checkpoints.clean_page_path(build_dir, 1)).convert("RGB"),
                 [BubbleRegion(bbox=BOX, mask=_masque(), score=0.95, cls=0)],
                 ["Bonjour"]).save(checkpoints.final_page_path(build_dir, 1))

    assert _run(tmp_path, _config(tmp_path), Reporter()) is True
    rapport = (build_dir / "RAPPORT.md").read_text(encoding="utf-8")
    assert "aucun appel" in rapport
    assert "Appels LLM : 0" not in rapport
