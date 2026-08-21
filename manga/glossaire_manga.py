# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le glossaire d'une œuvre manga, **sans passer par une traduction**.

## Le défaut que ce module corrige

Le glossaire est le MÊME fichier pour les deux briques (`sources/<Projet>/glossaire.yaml`) :
c'est ce qui garde les noms cohérents entre un roman et son manga. Le light novel savait
depuis longtemps le peupler et le nettoyer sans rien retraduire —
`run.py --extract-glossary` et `run.py --optimize-glossary`. La brique manga, non.

Pour enrichir le glossaire d'un manga, il fallait donc lancer un run COMPLET : le README le
disait noir sur blanc — « une planche n'est relevée que si elle va être **traduite** », donc
`--from traduction`. Sur une œuvre de quinze chapitres, peupler un glossaire coûtait une
retraduction intégrale : des heures de GPU, les `pages_out/` réécrites et les CBZ réencodés
(230 Mo par chapitre, sur un dossier synchronisé), pour un résultat qui tient dans un YAML de
quelques kilo-octets.

## Ce que fait ce module, et ce qu'il ne fait pas

`run_extract_glossary` délègue à `orchestrator_manga.process_volume(..., glossaire_seul=True)`
— un MODE de l'orchestrateur, et non un second orchestrateur : le balayage « détection →
OCR » est du code subtil (migration de cache, scission bi-lobée, ordre de lecture, styles de
bulle passés à l'OCR) et une copie aurait dérivé. Un chapitre qui n'a pas encore d'OCR est
détecté et OCRisé à la volée ; un chapitre déjà traité ne repaie rien.

Rien n'est écrit hors de `.checkpoints/` et du glossaire : ni page nettoyée, ni page finale,
ni `RAPPORT.md`, ni archive. C'est vérifié par `tests/test_manga_glossaire.py`, parce que
c'est la seule promesse qui rend la commande lançable sur une œuvre finie.

## Pourquoi le dédoublonnage est ICI et pas dans l'orchestrateur

`optimize_glossary_file` (le glossariste) porte sur le glossaire ENTIER de l'ŒUVRE. Le lancer
en fin de chapitre — ce que fait un run normal, et à juste titre, puisqu'il doit livrer un
glossaire propre à la traduction qui suit — coûterait quinze appels sur toute une œuvre là où
un seul, après le dernier chapitre, donne le même résultat. Aucune planche n'étant traduite
ici, la question du « moment » ne se pose pas : on optimise une fois, à la fin.

## Les agents sont ceux du MANGA

`pipeline.orchestrator.run_optimize` construit ses agents depuis `config["modeles"]` racine :
l'appeler ici ignorerait `manga.modeles` et `manga.llm`, donc le modèle, la température et
l'endpoint que l'utilisateur a réglés pour sa brique. On réutilise en revanche
`optimize_glossary_file` **tel quel** — garde-fou « sortie vide/suspecte » et sauvegarde
`.bak.yaml` compris —, exactement comme le fait déjà `orchestrator_manga`.
"""
from __future__ import annotations

from pathlib import Path

from core import config as core_config
from core import glossary, runtime
from core.reporter import Reporter

from .agents_manga import build_manga_agents


def chemin_glossaire(project: str, config: dict) -> Path:
    """`sources/<Projet>/glossaire.yaml`, résolu par la section manga.

    ⚠ Via `core_config.section(config, "manga", "chemins")` et jamais `config["chemins"]` en
    dur : `manga.chemins` HÉRITE de la racine par fusion profonde, et c'est cet héritage qui
    garantit que la brique manga écrit dans le fichier que le light novel enrichit. Écrire le
    chemin racine en dur remarcherait par accident tant que personne ne surcharge la section —
    et cesserait silencieusement le jour où quelqu'un le fait."""
    chemins = core_config.section(config, "manga", "chemins")
    return (Path(chemins["sources"]) / project
            / chemins.get("glossaire_fichier", "glossaire.yaml"))


def empreinte(project: str, config: dict) -> str:
    """Empreinte du glossaire de l'œuvre, pour savoir s'il a RÉELLEMENT bougé.

    Même mesure que `orchestrator_manga._passe_terminologie`, et pour la même raison : les
    compteurs de `merge_notes` renvoient « 1 fusion » en re-fusionnant des notes déjà
    intégrées, alors que rien ne change. S'y fier ferait rappeler le glossariste — un appel
    LLM sur tout le glossaire — à chaque relance d'une œuvre déjà relevée."""
    glo = glossary.load(chemin_glossaire(project, config)) or glossary.empty()
    return glossary.to_sectioned(glo)


def run_extract_glossary(project: str, volume: str, config: dict, reporter: Reporter | None = None,
                         *, force: bool = False, restart_from: str | None = None,
                         only_page: int | None = None) -> bool:
    """Relève la terminologie d'UN chapitre dans le glossaire de l'œuvre. Renvoie True si le
    chapitre est allé au bout, False sur un arrêt propre (`--stop` / Ctrl+C).

    N'optimise PAS : c'est l'appelant qui décide, une fois pour toute l'œuvre (cf. l'en-tête
    du module)."""
    from .orchestrator_manga import process_volume
    return process_volume(project, volume, config, reporter=reporter or Reporter(),
                          force=force, restart_from=restart_from, only_page=only_page,
                          glossaire_seul=True)


def run_optimize_glossary(project: str, config: dict,
                          reporter: Reporter | None = None) -> dict:
    """Dédoublonne / fusionne / reclasse le glossaire de l'ŒUVRE (agent `glossariste`).

    Pendant manga de `pipeline.orchestrator.run_optimize`, avec les agents de `manga.modeles`
    (cf. l'en-tête du module). Renvoie les compteurs par catégorie."""
    from pipeline.orchestrator import optimize_glossary_file
    reporter = reporter or Reporter()
    options = config.get("options") or {}
    dry = bool(options.get("dry_run", False))
    agents = build_manga_agents(config, dry_run=dry)
    runtime.wire_reporter(None, agents, reporter)
    try:
        return optimize_glossary_file(chemin_glossaire(project, config), agents, reporter,
                                      dry=dry, verbose=bool(options.get("verbose", False)))
    finally:
        # Même filet que `orchestrator_manga.process_volume` : une exception ne doit pas
        # abandonner un socket Ollama en pleine génération — c'est l'état que la docstring de
        # `LLM.close` relie à une chute PERSISTANTE du débit GPU au run suivant.
        runtime.close_llm_clients(None, agents)
