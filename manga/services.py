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

    def __init__(self, config: dict, projet: str, *, reporter=None,
                 langue: str | None = None):
        self.config = config
        self.projet = projet
        self.reporter = reporter
        self.mcfg = config.get("manga") or {}
        # Langue SOURCE du tome ouvert : elle décide du moteur d'OCR (`manga-ocr` ne lit que
        # le japonais) et de la consigne envoyée au traducteur unitaire. Un `Services` vit le
        # temps d'un tome, elle est donc posée une fois à l'ouverture.
        self.langue = str(langue or self.mcfg.get("langue_source") or "jp").lower()
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
            self._cache["det"] = detection.BubbleDetector.depuis_config(
                self.mcfg["detection"], dire=self._dire)
        return self._cache["det"]

    def detecteur_texte(self):
        """Détecteur du texte posé sur le dessin (second modèle ONNX)."""
        if "txt" not in self._cache:
            from . import text_detection
            self._cache["txt"] = text_detection.TextDetector.depuis_config(
                self.mcfg.get("onomatopees") or {}, self.mcfg.get("detection") or {},
                dire=self._dire)
        return self._cache["txt"]

    def lecteur(self):
        """Moteur d'OCR adapté à la langue du tome. Le plus cher à monter, et celui qu'on
        relance le plus souvent depuis l'éditeur.

        ⚠ Routé par `ocr_routeur` et non câblé sur `MangaOCR` : relire une bulle anglaise avec
        le modèle japonais ne rend pas un texte approximatif, il rend une chaîne collée et
        parsemée de kanji inventés."""
        if "ocr" not in self._cache:
            from . import ocr_routeur
            self._cache["ocr"] = ocr_routeur.lecteur_pour(
                self.langue, self.mcfg.get("ocr"), dire=self._dire)
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

    def pack(self):
        """Le pack de la langue CIBLE, résolu une fois par session.

        ⚠ Il ne sert pas qu'aux prompts de `langues/<code>/prompts/` : `Pack.consigne` porte
        les consignes que le code assemble lui-même, dont celle du prompt unitaire
        (`traduction_unitaire.CLE_CONSIGNE`). Sans lui, le bouton « retraduire cette bulle »
        réclame une traduction FRANÇAISE par une consigne codée en dur, quelle que soit la
        cible du projet."""
        if "pack" not in self._cache:
            from core.langues import resoudre_pack
            self._cache["pack"] = resoudre_pack(self.config)
        return self._cache["pack"]

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
