# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Suivi d'avancement. `Reporter` = sortie texte simple (CLI).
`RichReporter` = affichage live avec barres de progression (TUI)."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from core.version import __version__


class Reporter:
    def volume(self, plan) -> None:
        print(f"\n=== {plan.project} / {plan.volume} ===")
        print(f"Angelith {__version__}")
        print(f"Langues : {', '.join(plan.langs)} | pivot : {plan.pivot} | "
              f"images : {plan.image_lang or '—'} | mode : {plan.mode} | "
              f"chapitres : {plan.n_chapters}")
        for w in plan.warnings:
            print(f"  ⚠ {w}")

    def chapter(self, idx: int, total: int, title: str) -> None:
        self._chap_idx = idx
        print(f"\n— Chapitre {idx}/{total} : {title or '(sans titre)'}")

    def stage(self, name: str) -> None:
        print(f"   · {name}")

    def block(self, idx: int, total: int) -> None:
        print(f"     bloc {idx}/{total}")

    def info(self, msg: str) -> None:
        print(f"     {msg}")

    # ----- écriture dans perf.log (partagée avec RichReporter) ----------------- #

    def _chap_prefix(self) -> str:
        """Préfixe `chNN ` des lignes du log : une ligne de perf.log ne portait ni
        horodatage ni chapitre, si bien que la recaler sur un chapitre imposait de
        croiser `.checkpoints/` et `RAPPORT.md`."""
        i = getattr(self, "_chap_idx", None)
        return f"ch{i:02d} " if i else ""

    def _to_log(self, msg: str) -> None:
        log = getattr(self, "_vlog", None)
        if log:
            try:
                log.write(self._chap_prefix() + msg + "\n"); log.flush()
            except Exception:
                pass

    def set_console_verbose(self, actif: bool) -> None:
        """Sépare ce qui s'IMPRIME de ce qui se JOURNALISE.

        `perf.log` et `--verbose` étaient un seul et même interrupteur : pas de flag, pas de
        fichier. Un run de nuit n'a aucune raison de faire défiler des lignes de perf devant
        un écran que personne ne regarde — mais il a toutes les raisons de les écrire. Les
        deux sont donc découplés : le fichier prend tout (cf. `cli.make_reporter`), la console
        ne prend les lignes de perf que si on les a demandées.

        Défaut `True` : sans appel explicite, un `Reporter` se comporte comme avant."""
        self._console_verbose = bool(actif)

    def verbose(self, msg: str) -> None:
        """Ligne de perf (temps/tokens/vitesse), visuellement distincte des messages
        de progression pour ne pas se noyer dans le défilement des blocs. Si un fichier
        log a été ouvert (set_verbose_log), la ligne y est AUSSI écrite — tu peux alors
        suivre uniquement la perf dans un 2e terminal : `Get-Content -Wait perf.log`.

        ⚠ L'écriture dans le log est INCONDITIONNELLE ; seul l'affichage dépend de
        `set_console_verbose`. C'est ce qui permet à un run de nuit silencieux de laisser
        quand même toutes ses mesures derrière lui."""
        if getattr(self, "_console_verbose", True):
            print(f"       ⏱ {msg}")
        self._to_log(msg)

    def warn(self, msg: str) -> None:
        """Incident non fatal (budget « thinking » épuisé, bloc redécoupé et relancé,
        repli sur le texte précédent). Comme `verbose`, la ligne va AUSSI dans
        perf.log : ces messages partaient jusqu'ici sur stdout via un `print()` brut
        et étaient perdus à la fermeture du terminal — impossible, après un run de
        14 h, de savoir quels blocs avaient dérapé ni pourquoi."""
        print(f"       ⚠ {msg}")
        self._to_log(f"⚠ {msg}")

    def set_verbose_log(self, path) -> None:
        try:
            self._vlog = open(path, "a", encoding="utf-8")
        except Exception:
            self._vlog = None
            return
        # perf.log s'ouvre en "a" : les runs s'y EMPILENT. Sans en-tête, rien n'indiquait
        # quelle version ni quelle commande avait produit quelle ligne — comparer la perf
        # d'avant/après un changement de code demandait de se souvenir de l'ordre des runs.
        try:
            args = [Path(a).name if i == 0 else a for i, a in enumerate(sys.argv)]
            cmd = " ".join(f'"{a}"' if " " in a else a for a in args)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Ligne vide de séparation seulement si le fichier a DÉJÀ du contenu (ouvert
            # en "a", `tell()` donne sa taille) : pas de première ligne vide inutile.
            sep = "\n" if self._vlog.tell() else ""
            self._vlog.write(f"{sep}# Angelith {__version__} — {stamp} — python {cmd}\n")
            self._vlog.flush()
        except Exception:
            pass   # un en-tête manquant ne doit jamais coûter le log lui-même

    def close(self) -> None:
        """Referme `perf.log`. Idempotent, et sans effet si aucun log n'a été ouvert.

        ⚠ Aucune donnée n'est en jeu — `_to_log` fait `flush()` à chaque ligne. C'est de
        l'hygiène de descripteur, et elle ne coûtait rien en ligne de commande, où le
        processus se termine de toute façon. L'interface graphique, elle, construit un
        reporter **par run** : trente relettrages dans une session laissaient trente
        descripteurs ouverts sur le même fichier. Sous Windows un handle ouvert VERROUILLE
        le fichier, si bien qu'ouvrir `perf.log` dans un éditeur ou l'effacer pouvait
        échouer sans qu'on comprenne pourquoi."""
        log = getattr(self, "_vlog", None)
        self._vlog = None
        if log is not None:
            try:
                log.close()
            except Exception:
                pass   # un descripteur déjà mort ne doit pas faire tomber la fermeture

    def finish(self, outputs: list[str]) -> None:
        print("\n✓ Terminé. Fichiers :", ", ".join(outputs))

    def stopped(self, done: int, total: int) -> None:
        print(f"\n■ Arrêté proprement : {done}/{total} chapitre(s) terminé(s). "
              "Le travail en cours est sauvegardé — relance la même commande pour reprendre.")

    # contexte (no-op en mode texte)
    def __enter__(self): return self
    def __exit__(self, *a): return False


class RichReporter(Reporter):
    def __init__(self):
        from rich.console import Console
        from rich.progress import (Progress, SpinnerColumn, BarColumn,
                                    TextColumn, TimeElapsedColumn)
        self.console = Console()
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._chap_task = None
        self._block_task = None

    def __enter__(self):
        self.progress.__enter__()
        return self

    def __exit__(self, *a):
        self.progress.__exit__(*a)
        return False

    def volume(self, plan) -> None:
        self.console.rule(f"[bold]{plan.project} / {plan.volume}")
        self.console.print(f"[dim]Angelith {__version__}[/]")
        self.console.print(
            f"Langues : [cyan]{', '.join(plan.langs)}[/]  ·  pivot : [green]{plan.pivot}[/]  ·  "
            f"images : [magenta]{plan.image_lang or '—'}[/]  ·  mode : [yellow]{plan.mode}[/]  ·  "
            f"chapitres : [bold]{plan.n_chapters}[/]"
        )
        for w in plan.warnings:
            self.console.print(f"  [yellow]⚠ {w}[/]")
        self._chap_task = self.progress.add_task("Chapitres", total=plan.n_chapters)

    def chapter(self, idx: int, total: int, title: str) -> None:
        self._chap_idx = idx
        self.progress.update(self._chap_task, completed=idx - 1,
                             description=f"Ch. {idx}/{total} {title[:30]}")

    def stage(self, name: str) -> None:
        """⚠ `_chap_task` n'existe QUE si `volume()` a été appelé — et `volume()` est propre
        au LN (il lit langues/pivot/chapitres sur un `VolumePlan`). Les briques manga et scan
        écrivent leur propre en-tête et n'en ont pas : sans ce garde-fou, la première étape
        annoncée les tuait sur un `KeyError: None` au fond de rich. La barre de progression
        de ces briques est portée par `block()`, qui crée sa tâche paresseusement ; l'étape
        est donc simplement ÉCRITE, comme le fait le reporter texte, plutôt que perdue.
        (`finish()` porte déjà le même garde-fou, pour la même raison.)"""
        if self._chap_task is None:
            self.console.print(f"   [bold blue]·[/] {name}")
            return
        self.progress.update(self._chap_task, description=f"{name}")

    def block(self, idx: int, total: int) -> None:
        if self._block_task is None:
            self._block_task = self.progress.add_task("blocs", total=total)
        self.progress.update(self._block_task, total=total, completed=idx)

    def info(self, msg: str) -> None:
        self.console.print(f"     [dim]{msg}[/]")

    def verbose(self, msg: str) -> None:
        """Comme Reporter.verbose, mais via Console.print (compatible avec la barre de
        progression Live active) plutôt qu'un print() brut qui la corromprait. Même
        découplage console/fichier : le log prend tout, l'affichage obéit à
        `set_console_verbose`."""
        if getattr(self, "_console_verbose", True):
            self.console.print(f"       [cyan]⏱ {msg}[/]")
        self._to_log(msg)

    def warn(self, msg: str) -> None:
        """Comme Reporter.warn, via Console.print (cf. verbose)."""
        self.console.print(f"       [yellow]⚠ {msg}[/]")
        self._to_log(f"⚠ {msg}")

    def finish(self, outputs: list[str]) -> None:
        if self._chap_task is not None:
            self.progress.update(self._chap_task, completed=self.progress.tasks[0].total)
        self.console.print("\n[bold green]✓ Terminé.[/] Fichiers : " + ", ".join(outputs))

    def stopped(self, done: int, total: int) -> None:
        self.console.print(
            f"\n[bold yellow]■ Arrêté proprement[/] : {done}/{total} chapitre(s) terminé(s). "
            "Le travail en cours est sauvegardé — relance la même commande pour reprendre.")
