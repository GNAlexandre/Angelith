#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Interface console (TUI) — menu d'actions avec les mêmes capacités que la CLI
(run.py) : traiter un tome (--force/--from/--chapitre/--verbose/--keep-awake/
--shutdown), tester le LLM, diagnostic complet, glossaire (import/optimisation),
et demande d'arrêt propre d'un run en cours."""
from core import cli

cli.configurer_stdout()

# ⚠ Les imports qui suivent sont VOLONTAIREMENT après l'appel ci-dessus : `configurer_stdout()`
# réencode la sortie console, et tout module qui touche à stdout en l'important — `rich` au
# premier chef — figerait l'ancien encodage. D'où les suppressions E402 de ce bloc.

from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.prompt import Confirm, IntPrompt, Prompt  # noqa: E402

from core.reporter import Reporter, RichReporter  # noqa: E402
from pipeline import sources  # noqa: E402
from pipeline.orchestrator import STAGES, process_volume  # noqa: E402

console = Console()


def _choose(title: str, items: list[str]) -> str | None:
    if not items:
        console.print(f"[red]Aucun élément pour : {title}[/]")
        return None
    console.print(f"\n[bold]{title}[/]")
    for i, it in enumerate(items, 1):
        console.print(f"  [cyan]{i}[/]. {it}")
    choice = Prompt.ask("Choix", choices=[str(i) for i in range(1, len(items) + 1)], default="1")
    return items[int(choice) - 1]


def _choose_project_and_volume(config: dict) -> tuple[str, str] | tuple[None, None]:
    src = Path(config["chemins"]["sources"])
    project = _choose("Projets disponibles", sources.list_projects(src))
    if not project:
        console.print(f"Crée un dossier sous [cyan]{src}/[/] (ex. {src}/Mon LN/Vol.1/ENG/…)")
        return None, None
    volume = _choose(f"Tomes de « {project} »", sources.list_volumes(src, project))
    if not volume:
        return None, None
    return project, volume


def _choose_stage_or_none() -> str | None:
    console.print("\n[bold]Relancer à partir d'une étape ?[/]")
    console.print("  [cyan]0[/]. (toutes les étapes — traitement complet)")
    for i, s in enumerate(STAGES, 1):
        console.print(f"  [cyan]{i}[/]. {s}")
    choice = Prompt.ask("Choix", choices=[str(i) for i in range(len(STAGES) + 1)], default="0")
    idx = int(choice)
    return None if idx == 0 else STAGES[idx - 1]


def _run_volume(config: dict) -> None:
    project, volume = _choose_project_and_volume(config)
    if not project:
        return

    console.print("\n[dim]Analyse des sources…[/]")
    src = Path(config["chemins"]["sources"])
    build_dir = Path(config["chemins"]["build"]) / project / volume
    try:
        plan = sources.scan_volume(src / project / volume, config, build_dir)
    except SystemExit as e:
        console.print(f"[red]{e}[/]")
        return

    console.print(Panel(
        f"Langues : [cyan]{', '.join(plan.langs)}[/]\n"
        f"Pivot : [green]{plan.pivot}[/]   ·   Images : [magenta]{plan.image_lang or '—'}[/]\n"
        f"Mode : [yellow]{plan.mode}[/]   ·   Chapitres détectés : [bold]{plan.n_chapters}[/]"
        + ("".join(f"\n[yellow]⚠ {w}[/]" for w in plan.warnings)),
        title="Plan", border_style="green"))

    restart_from = _choose_stage_or_none()
    only_chapter = None
    if Confirm.ask("Ne (re)traiter qu'UN seul chapitre ?", default=False):
        only_chapter = IntPrompt.ask("Numéro du chapitre (1-indexé)", default=1)
    force = False
    if only_chapter is None and restart_from is None:
        force = Confirm.ask("Refaire les chapitres déjà générés (--force) ?", default=False)
    verbose = Confirm.ask("Afficher la performance par bloc (--verbose) ?", default=False)
    dry = Confirm.ask("Mode dry-run (sans appel LLM, pour tester) ?", default=False)
    keep_awake = shutdown = False
    shutdown_delay = 120
    if not dry:
        keep_awake = Confirm.ask("Empêcher la mise en veille pendant le run (--keep-awake) ?", default=False)
        shutdown = Confirm.ask("Éteindre le PC à la fin du run (--shutdown) ?", default=False)
        if shutdown:
            shutdown_delay = IntPrompt.ask("Délai avant extinction, en secondes (annulable)", default=120)

    if not Confirm.ask("Lancer le traitement ?", default=True):
        return

    config["options"]["dry_run"] = dry
    config["options"]["verbose"] = verbose

    # Anti-veille / préchargement-déchargement Ollama / extinction : le socle `core.cli`,
    # PLUS `run.py`. L'import depuis la CLI était une inversion de couche — la TUI dépendait
    # d'une CLI concurrente, si bien qu'on ne pouvait pas toucher à `run.py` sans risquer de
    # casser `app.py`. Même comportement, même code, sans la dépendance.
    power_args = SimpleNamespace(keep_awake=keep_awake, shutdown=shutdown, shutdown_delay=shutdown_delay)

    inhibitor = cli.preparer_veille(keep_awake or shutdown, "")
    if inhibitor is not None or keep_awake or shutdown:
        console.print("[dim]Veille du PC désactivée pour la durée du run.[/]")
    models_used = cli.models_in_config(config)
    cli.precharger_modeles(config, models_used, dry_run=dry)

    # Par `cli.make_reporter` et non `set_verbose_log` en direct : c'est lui qui porte la règle
    # « le fichier est écrit dans tous les cas, le flag ne décide que de l'affichage ». La TUI
    # l'ouvrait sous `if verbose`, donc un run lancé d'ici sans cocher l'option ne laissait
    # aucune trace — le défaut même que la 1.7.0 corrige côté CLI et interface graphique.
    rep = cli.make_reporter(RichReporter(), build_dir, verbose=verbose, dry_run=dry)
    interrupted = False
    try:
        with rep:
            process_volume(project, volume, config, reporter=rep, force=force,
                           restart_from=restart_from, only_chapter=only_chapter)
    except KeyboardInterrupt:
        interrupted = True
        console.print("\n[yellow]Interrompu. Relance pour reprendre.[/]")
    except Exception as e:
        console.print(f"\n[red]⚠ Erreur : {e}[/]\n"
                      "[dim]Ton avancement par bloc est sauvegardé — corrige puis relance pour reprendre.[/]")
        cli.unload_models(config, models_used)
        cli.finalize_power(power_args, inhibitor, interrupted=False)
        raise
    cli.unload_models(config, models_used)
    cli.finalize_power(power_args, inhibitor, interrupted=interrupted)


def _test_llm(config: dict) -> None:
    from core.llm import test_connection
    test_connection(config)


def _check(config: dict) -> None:
    # `pipeline.doctor`, plus `run.py` : le diagnostic appartient à la BRIQUE qu'il examine
    # (sections de config, chemins, Pandoc, moteur PDF), pas à une CLI. Il n'est pas non plus
    # allé dans `core/` — seules ses sections réellement communes (Ollama, dépendances,
    # conclusion) y vivent, et les deux doctors s'en servent.
    from pipeline.doctor import run_doctor
    run_doctor(config)


def _optimize_glossary(config: dict) -> None:
    src = Path(config["chemins"]["sources"])
    project = _choose("Projets disponibles", sources.list_projects(src))
    if not project:
        return
    from pipeline.orchestrator import run_optimize
    run_optimize(project, config, reporter=Reporter())


def _import_glossary(config: dict) -> None:
    src = Path(config["chemins"]["sources"])
    project = _choose("Projets disponibles", sources.list_projects(src))
    if not project:
        return
    fichier = Prompt.ask("Chemin du fichier à importer (.docx/.txt/.md)")
    from core.glossary_import import import_into_project
    try:
        gpath, added, parsed = import_into_project(project, fichier, config)
    except Exception as e:
        console.print(f"[red]⚠ {e}[/]")
        return
    tot = sum(len(v) for v in parsed.values())
    console.print(f"Glossaire importé dans : [cyan]{gpath}[/]")
    console.print(f"  Entrées lues : {tot} · ajouts {added['ajouts']} · "
                 f"fusions {added['fusions']} · conflits {added['conflits']}")


def _request_stop(config: dict) -> None:
    project, volume = _choose_project_and_volume(config)
    if not project:
        return
    from core.control import request_stop
    build_dir = Path(config["chemins"]["build"]) / project / volume
    request_stop(build_dir)
    console.print(f"[yellow]Arrêt demandé pour {project} / {volume}.[/] Les IA termineront "
                 "le bloc en cours, sauvegarderont, puis s'arrêteront.")


_ACTIONS = [
    ("Traiter un tome", _run_volume),
    ("Tester la connexion LLM", _test_llm),
    ("Diagnostic complet de l'environnement", _check),
    ("Optimiser le glossaire d'une œuvre", _optimize_glossary),
    ("Importer un glossaire existant", _import_glossary),
    ("Demander l'arrêt propre d'un run en cours", _request_stop),
    ("Quitter", None),
]


def main() -> None:
    config = cli.charger_config()

    console.print(Panel.fit("[bold]Angelith[/] — pipeline de fan-traduction local",
                            border_style="blue"))

    while True:
        console.print("\n[bold]Que veux-tu faire ?[/]")
        for i, (label, _) in enumerate(_ACTIONS, 1):
            console.print(f"  [cyan]{i}[/]. {label}")
        choice = Prompt.ask("Choix", choices=[str(i) for i in range(1, len(_ACTIONS) + 1)], default="1")
        _, action = _ACTIONS[int(choice) - 1]
        if action is None:
            break
        action(config)


if __name__ == "__main__":
    main()
