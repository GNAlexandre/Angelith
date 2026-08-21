# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Porteur de modèles à durée de vie EXPLICITE — détecteurs ONNX, OCR, agents, glossaire.

## Le défaut que ça corrige

`process_volume` porte une closure `_lazy` qui charge chaque modèle à son premier usage réel et
le garde pour tout le tome. C'est exactement le bon comportement — mais il est **enfermé dans
un appel** : il naît et meurt avec le run.

L'interface graphique, elle, vit des heures et fait des gestes unitaires. En 1.1.0, chaque clic
sur « Retraduire » reconstruisait les agents, relisait les prompts sur disque, ouvrait un
nouveau client LLM **et rechargeait le glossaire YAML** — pour un appel de deux secondes. Seul
`MangaOCR` était mis en cache, et à un seul endroit.

D'où cette extraction : la même paresse, mais avec une durée de vie que l'appelant choisit. La
CLI en crée un par run et le libère ; l'interface en crée **un par fenêtre**.

## Pourquoi ce n'est pas un singleton

Deux tomes ouverts, deux configurations possibles (un `endpoint:` différent, un `num_ctx`
différent). Un singleton global rendrait la deuxième fenêtre silencieusement fausse. L'objet
est donc passé, jamais cherché.

## Le glossaire

`gloss_text` est sérialisé UNE fois (`glossary.to_text`, plafonné à 4 000 tokens) et réutilisé.
C'est le même arbitrage que dans `process_volume`, où il est figé avant la boucle des
planches : un glossaire qui bougerait entre deux bulles donnerait à chacune un contexte
différent, ce qui est précisément le défaut que la passe terminologique de volume a corrigé au
lot 4.1.

`recharger_glossaire()` existe pour le cas où l'utilisateur vient d'éditer le YAML à la main —
c'est un geste explicite, pas une vérification à chaque appel.
"""
from __future__ import annotations

from pathlib import Path

from core import config as core_config, glossary, runtime

# Budget de sérialisation du glossaire injecté en contexte. Même valeur que `process_volume` —
# la dupliquer serait la laisser diverger, d'où la constante partagée.
BUDGET_GLOSSAIRE = 4000


class Services:
    """Modèles et agents d'un tome, chargés à leur premier usage réel et gardés chauds.

    ⚠ Aucun chargement dans `__init__`. Construire un `Services` doit rester gratuit : c'est
    ce qui permet à l'interface d'en poser un par fenêtre sans faire monter 500 Mo de modèles
    pour quelqu'un qui vient seulement regarder ses planches."""

    def __init__(self, config: dict, projet: str, *, reporter=None):
        self.config = config
        self.projet = projet
        self.reporter = reporter
        self.mcfg = config.get("manga") or {}
        self._cache: dict = {}

    # ------------------------------------------------------------------ #
    # Modèles locaux
    # ------------------------------------------------------------------ #

    def _dire(self, msg: str) -> None:
        if self.reporter is not None:
            self.reporter.info(msg)

    def detecteur(self):
        """Détecteur de bulles (ONNX, ~104 Mo). Téléchargé au besoin, une seule fois."""
        if "det" not in self._cache:
            from . import detection
            det_cfg = self.mcfg["detection"]
            self._cache["det"] = detection.BubbleDetector(
                det_cfg["model_path"], providers=det_cfg.get("providers"),
                conf_threshold=det_cfg.get("conf_threshold", 0.35),
                iou_threshold=det_cfg.get("iou_threshold", 0.45),
                telechargement_auto=bool(det_cfg.get("telechargement_auto", True)),
                model_url=det_cfg.get("model_url") or None, dire=self._dire)
        return self._cache["det"]

    def detecteur_texte(self):
        """Détecteur du texte posé sur le dessin (second modèle ONNX)."""
        if "txt" not in self._cache:
            from . import text_detection
            sfx_cfg = self.mcfg.get("onomatopees") or {}
            det_cfg = self.mcfg.get("detection") or {}
            self._cache["txt"] = text_detection.TextDetector(
                sfx_cfg.get("model_path", "manga_models/text_detector.onnx"),
                providers=det_cfg.get("providers"),
                telechargement_auto=bool(sfx_cfg.get("telechargement_auto", True)),
                model_url=sfx_cfg.get("model_url") or None, dire=self._dire)
        return self._cache["txt"]

    def lecteur(self):
        """`MangaOCR` — ViT+BERT, ~424 Mo. Le plus cher à monter, et celui qu'on relance le
        plus souvent depuis l'éditeur."""
        if "ocr" not in self._cache:
            from . import ocr as ocr_mod
            self._cache["ocr"] = ocr_mod.MangaOCR(self.mcfg.get("ocr"), dire=self._dire)
        return self._cache["ocr"]

    # ------------------------------------------------------------------ #
    # Agents LLM
    # ------------------------------------------------------------------ #

    def agents(self) -> dict:
        """Agents manga, construits UNE fois.

        ⚠ `runtime.wire_reporter` est appelé ici et pas ailleurs : sans lui, les incidents des
        clients LLM (budget de raisonnement épuisé, réponse vide, nouvelle tentative) partent
        sur `stdout` par un `print` brut — donc nulle part, dans une interface graphique. C'est
        le défaut que la brique manga avait déjà corrigé pour ses runs et que l'éditeur avait
        réintroduit pour ses appels unitaires."""
        if "agents" not in self._cache:
            from .agents_manga import build_manga_agents
            dry = bool(self.config.get("options", {}).get("dry_run", False))
            agents = build_manga_agents(self.config, dry_run=dry)
            if self.reporter is not None:
                runtime.wire_reporter(None, agents, self.reporter)
            self._cache["agents"] = agents
        return self._cache["agents"]

    def traducteur(self):
        return self.agents().get("manga_traducteur")

    # ------------------------------------------------------------------ #
    # Glossaire
    # ------------------------------------------------------------------ #

    def chemin_glossaire(self) -> Path:
        chemins = core_config.section(self.config, "manga", "chemins")
        return (Path(chemins["sources"]) / self.projet
                / chemins.get("glossaire_fichier", "glossaire.yaml"))

    def glossaire(self) -> dict:
        if "gloss" not in self._cache:
            chemin = self.chemin_glossaire()
            self._cache["gloss"] = (glossary.load(chemin) if chemin.exists()
                                    else glossary.empty()) or glossary.empty()
        return self._cache["gloss"]

    def gloss_text(self) -> str:
        """Le glossaire SÉRIALISÉ, tel qu'il part dans un prompt. Calculé une fois.

        C'est ce que la 1.1.0 refaisait à chaque clic : charger le YAML, le parcourir, le
        re-sérialiser — pour un texte identique d'un appel à l'autre."""
        if "gloss_text" not in self._cache:
            gloss = self.glossaire()
            self._cache["gloss_text"] = (glossary.to_text(gloss, max_tokens=BUDGET_GLOSSAIRE)
                                         if glossary.total(gloss) else "")
        return self._cache["gloss_text"]

    def recharger_glossaire(self) -> None:
        """À appeler après une édition du YAML à la main. Geste explicite : revérifier le
        fichier à chaque appel coûterait une lecture disque par bulle traduite."""
        self._cache.pop("gloss", None)
        self._cache.pop("gloss_text", None)

    # ------------------------------------------------------------------ #

    def liberer(self) -> None:
        """Ferme les clients LLM et lâche les modèles. Idempotent.

        ⚠ Ne décharge PAS le modèle côté Ollama (`keep_alive: 0`) : c'est une décision de
        session, pas de fenêtre, et elle appartient à l'appelant — l'évincer parce qu'on ferme
        un onglet punirait l'utilisateur qui l'avait chargé pour autre chose."""
        agents = self._cache.get("agents")
        if agents:
            runtime.close_llm_clients(None, agents)
        self._cache.clear()
