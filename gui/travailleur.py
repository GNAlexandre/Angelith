# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Un SEUL fil de travail, une file d'attente, et un verrou par planche.

## Ce que la 1.1.0 faisait, et pourquoi c'était intenable

Deux `QThread` créés à la demande, aucune file, et un `_marquer_occupe` qui désactivait le
panneau éditeur **d'un bloc**. Relire une bulle de la planche 12 interdisait donc de toucher à
la planche 30, alors que rien ne les relie. Pire, trois trous de concurrence se refermaient
mal : `_lancer_run` ne testait pas la tâche d'édition, `_assembler` écrasait un `QThread`
vivant, et `self._signaux` était réassigné **sous** le fil précédent, qui continuait d'émettre
vers un objet que plus personne n'écoutait.

Et les éditions de zone, elles, ne passaient par aucun fil : `edition.ajouter_zone` manipule
des masques booléens pleine page et réécrit quatre fichiers, le tout sur le fil d'affichage.

## Le modèle retenu

Un fil unique qui consomme une `queue.Queue`. Comme il est unique, les tâches sont
naturellement sérialisées — il n'y a jamais deux écritures concurrentes sur le même
checkpoint, sans qu'aucun verrou n'ait à être posé pour ça.

Le **verrou par planche** n'est donc pas un verrou d'exclusion mais un état d'affichage : la
planche en cours de traitement est grisée et annonce ce qu'elle subit, les autres restent
éditables. Une seconde demande sur une planche occupée est **mise en file**, jamais refusée
par une boîte de dialogue — refuser un geste que l'utilisateur vient de faire est le pire des
retours.

Une tâche de genre `run` porte `planche=None` : un `process_volume` touche à toutes les
planches, il verrouille donc la totalité.

## Ce qui ne change pas

`ReporterQt` reste un `Reporter` du socle, donc `set_verbose_log` et l'écriture dans
`perf.log` fonctionnent — encore faut-il les appeler, ce que la 1.1.0 ne faisait nulle part
(cf. lot 20). `control.install_sigint` ne fait rien hors du fil principal : appeler
`process_volume` d'ici reste sûr, et le fichier `STOP` reste le seul chemin d'arrêt.
"""
from __future__ import annotations

import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal

from core import cli, config as core_config, control
from core.reporter import Reporter

# Genres de tâches. Le genre décide de ce que l'interface verrouille et de ce qu'elle affiche ;
# il ne change rien à l'exécution, qui est la même file pour tout le monde.
GENRE_RUN = "run"                  # process_volume — touche tout le tome
GENRE_EDITION = "edition"          # ajouter / modifier / supprimer / scinder une zone
GENRE_OCR = "ocr"                  # relire une bulle
GENRE_TRADUCTION = "traduction"    # retraduire une bulle
GENRE_REPRISE = "reprise"          # nettoyer + lire + traduire une zone (lot 21)
GENRE_ASSEMBLAGE = "assemblage"    # CBZ / PDF
GENRE_APERCU = "apercu"            # composition des calques de texte d'une planche
GENRE_VIGNETTE = "vignette"        # imagette de la pellicule

LIBELLES_GENRE = {
    GENRE_RUN: "run",
    GENRE_EDITION: "édition de zone",
    GENRE_OCR: "lecture OCR",
    GENRE_TRADUCTION: "traduction",
    GENRE_REPRISE: "reprise de bulle",
    GENRE_ASSEMBLAGE: "assemblage",
    GENRE_APERCU: "composition de l'aperçu",
    GENRE_VIGNETTE: "vignette",
}

# Genres qui ne font que LIRE. Ils passent par `FilDeLecture` et ne verrouillent aucune
# planche : rien n'est écrit, donc il n'y a rien à protéger de l'utilisateur.
GENRES_LECTURE = frozenset({GENRE_APERCU, GENRE_VIGNETTE})


@dataclass
class Tache:
    """Une unité de travail dans la file.

    `planche = None` signifie « touche tout le tome » : l'interface verrouille alors tout.
    `fonction` s'exécute dans le fil de travail et ne doit toucher **aucun** widget ; ce
    qu'elle renvoie part dans le signal `fin` sous forme de message."""

    genre: str
    fonction: Callable[[], object]
    planche: int | None = None
    libelle: str = ""
    # Les tâches d'un même (planche, genre) qui s'empilent sont fusionnées : cliquer trois fois
    # sur « Relire » ne doit pas payer trois OCR. `None` désactive la fusion — c'est le cas des
    # éditions de zone, dont chacune est un geste distinct qu'on n'a pas le droit de perdre.
    cle_fusion: tuple | None = None


class SignauxTravail(QObject):
    """Créé UNE fois, pour toute la vie de la fenêtre.

    C'est le correctif du troisième trou de concurrence : en 1.1.0, chaque lancement
    réassignait `self._signaux`, si bien qu'un fil encore vivant émettait vers un objet que
    plus personne n'écoutait — ses lignes de journal disparaissaient sans un mot."""

    ligne = Signal(str, str)                # (niveau, texte) — info | stage | verbose | warn
    progression = Signal(int, int)          # (courant, total) ; total 0 = indéterminé
    debut = Signal(object, str, str)        # (planche | None, genre, libellé)
    fin = Signal(object, str, bool, str)    # (planche | None, genre, succès, message)
    file = Signal(int)                      # tâches restantes, celle en cours comprise
    # Voie de LECTURE — une composition d'aperçu est prête pour cette planche. Le fil
    # d'affichage va la chercher dans le cache : elle n'est jamais transportée dans le signal,
    # une image PIL n'ayant rien à faire dans une file de signaux Qt.
    apercu_pret = Signal(int)
    # (prêtes, voulues) — avancement du préchargement, pour la barre de progression.
    prechargement = Signal(int, int)


class ReporterQt(Reporter):
    """`Reporter` qui émet des signaux Qt au lieu d'imprimer.

    ⚠ Aucune méthode ne doit toucher un widget : elle est appelée depuis le fil de travail.
    Les signaux traversent vers le fil d'affichage en connexion différée, ce que Qt fait de
    lui-même dès que l'émetteur et le récepteur vivent dans deux fils.

    Hérite de `Reporter`, et pas seulement par économie : c'est ce qui apporte
    `set_verbose_log` et `_to_log`, donc un `perf.log` identique à celui d'un run lancé au
    terminal."""

    def __init__(self, signaux: SignauxTravail, prefixe: str = ""):
        self.signaux = signaux
        self.prefixe = prefixe

    def _dire(self, niveau: str, msg: str) -> None:
        self.signaux.ligne.emit(niveau, f"{self.prefixe}{msg}" if self.prefixe else msg)

    # `volume` n'est appelé que par le light novel (il lit `plan.langs`, `plan.pivot`…) ;
    # la brique manga écrit son propre en-tête par `info`.
    def volume(self, plan) -> None:
        self._dire("stage", f"{plan.project} / {plan.volume}")
        for w in getattr(plan, "warnings", []) or []:
            self._dire("warn", w)

    def chapter(self, idx: int, total: int, title: str) -> None:
        self._chap_idx = idx                      # lu par `_chap_prefix` pour perf.log
        self.signaux.progression.emit(idx, total)
        self._dire("stage", f"Chapitre {idx}/{total} — {title or '(sans titre)'}")

    def stage(self, name: str) -> None:
        self._dire("stage", name)
        # « Page 12/131 — … » et « Lot planches 21→40 … » sont les deux formes que la brique
        # manga produit ; on en tire la progression sans imposer un second canal à
        # l'orchestrateur, qui n'a pas à connaître l'interface.
        courant, total = progression_de_stage(name)
        if courant:
            self.signaux.progression.emit(courant, total)

    def block(self, idx: int, total: int) -> None:
        self.signaux.progression.emit(idx, total)

    def info(self, msg: str) -> None:
        self._dire("info", msg)

    def verbose(self, msg: str) -> None:
        self._dire("verbose", msg)
        self._to_log(msg)

    def warn(self, msg: str) -> None:
        self._dire("warn", msg)
        self._to_log(f"⚠ {msg}")

    def finish(self, outputs: list[str]) -> None:
        self._dire("info", "Terminé. Fichiers : " + ", ".join(outputs))

    def stopped(self, done: int, total: int) -> None:
        self._dire("warn", f"Arrêté proprement : {done}/{total} — le travail en cours est "
                           f"sauvegardé, relance pour reprendre.")


_RE_PAGE = re.compile(r"Page (\d+)/(\d+)")
_RE_LOT = re.compile(r"Lot planches (\d+)→(\d+)")


def progression_de_stage(nom: str) -> tuple[int, int]:
    """`(courant, total)` extrait d'un libellé d'étape, ou `(0, 0)`.

    Volontairement tolérant : si un jour le libellé change, la barre cesse d'avancer et rien
    d'autre ne casse. Une progression est un confort, pas une donnée."""
    m = _RE_PAGE.search(nom)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _RE_LOT.search(nom)
    if m:
        return int(m.group(1)), 0
    return 0, 0


class FilDeTravail(QThread):
    """Le fil unique. Consomme la file jusqu'à ce qu'on lui demande de s'arrêter.

    ⚠ `queue.Queue.get()` bloque : le fil dort quand il n'y a rien à faire, il ne tourne pas
    à vide. `arreter()` pousse une sentinelle plutôt que de tuer le fil — une tâche
    interrompue en plein `save_regions` laisserait un checkpoint à moitié écrit."""

    _SENTINELLE = object()

    def __init__(self, signaux: SignauxTravail, parent=None):
        super().__init__(parent)
        self.signaux = signaux
        self._file: queue.Queue = queue.Queue()
        self._en_cours: tuple | None = None       # (planche, genre)
        self._cles_en_file: set = set()

    # ------------------------------------------------------------------ #

    def soumettre(self, tache: Tache) -> bool:
        """Met une tâche en file. Renvoie `False` si elle a été **fusionnée** avec une
        identique déjà en attente — cliquer trois fois sur « Relire » ne doit pas payer trois
        OCR, alors que trois éditions de zone successives sont trois gestes distincts."""
        if tache.cle_fusion is not None:
            if tache.cle_fusion in self._cles_en_file:
                return False
            self._cles_en_file.add(tache.cle_fusion)
        self._file.put(tache)
        self.signaux.file.emit(self._file.qsize() + (1 if self._en_cours else 0))
        return True

    def arreter(self) -> None:
        self._file.put(self._SENTINELLE)

    def occupe(self) -> bool:
        return self._en_cours is not None

    def planche_en_cours(self) -> int | None:
        return self._en_cours[0] if self._en_cours else None

    def touche_tout(self) -> bool:
        """Une tâche globale (un run) est en cours : plus rien n'est éditable."""
        return self._en_cours is not None and self._en_cours[0] is None

    def en_attente(self) -> int:
        return self._file.qsize()

    # ------------------------------------------------------------------ #

    def run(self) -> None:                       # noqa: D102 — surcharge de QThread
        while True:
            tache = self._file.get()
            if tache is self._SENTINELLE:
                return
            if tache.cle_fusion is not None:
                self._cles_en_file.discard(tache.cle_fusion)
            self._en_cours = (tache.planche, tache.genre)
            self.signaux.debut.emit(tache.planche, tache.genre,
                                    tache.libelle or LIBELLES_GENRE.get(tache.genre, tache.genre))
            try:
                resultat = tache.fonction()
                message = resultat if isinstance(resultat, str) else (
                    tache.libelle or "Terminé.")
                self._en_cours = None
                self.signaux.fin.emit(tache.planche, tache.genre, True, message)
            except Exception as err:              # noqa: BLE001 — remonté à l'écran
                self._en_cours = None
                self.signaux.ligne.emit("warn", f"{type(err).__name__} : {err}")
                self.signaux.fin.emit(tache.planche, tache.genre, False,
                                      f"{type(err).__name__} : {err}")
            self.signaux.file.emit(self._file.qsize())


class FilDeLecture(QThread):
    """La voie de LECTURE : elle compose des aperçus, elle n'écrit jamais.

    ## Pourquoi une seconde voie

    `FilDeTravail` est unique **pour une raison** : un seul fil, donc jamais deux écritures
    concurrentes sur un checkpoint. Cette raison ne s'applique pas aux compositions d'aperçu,
    qui sont purement des lectures — et les mettre dans la même file avait un coût mesurable
    pour l'utilisateur : l'aperçu de la planche 13 attendait derrière la retraduction d'une
    bulle de la 12, un travail qui ne le concerne pas. Composer coûte 1,37 s en médiane ;
    attendre un appel LLM derrière, dix fois plus.

    ## Un ENSEMBLE de planches voulues, pas une file de tâches

    C'est le point de conception. Une file aurait deux défauts que rien ne rattrape : elle
    grossirait à chaque déplacement dans le tome, et elle continuerait à composer des planches
    qu'on a quittées depuis longtemps. Ici, `vouloir()` **remplace** l'ensemble et le fil prend
    toujours la planche la plus proche de la courante. Se déplacer repriorise ; il n'y a rien à
    annuler, donc rien à annuler *de travers*.

    ## DEUX natures de travail, et c'est tout l'ordonnancement

    Une **vignette** coûte quelques dizaines de millisecondes et concerne tout le tome ; un
    **aperçu** coûte 1,37 s en médiane et ne concerne que la fenêtre autour de la planche
    courante. Les trier ensemble par simple proximité faisait passer les 21 aperçus de la
    fenêtre devant TOUTES les vignettes : une trentaine de secondes pendant lesquelles la bande
    restait vide au-delà du voisinage immédiat. Le CHANGELOG 1.5.0 énonçait déjà la distinction
    — « deux portées délibérément différentes » — mais elle ne vivait que dans la portée, pas
    dans la priorité.

    Les deux sont donc des unités de travail SÉPARÉES (`GENRE_VIGNETTE`, `GENRE_APERCU`), ce
    qui règle du même coup deux défauts qui n'en faisaient qu'un :

    · une vignette écrite sur disque n'est plus perdue quand l'aperçu de la même planche lève.
      Elle était fabriquée puis annoncée par le MÊME code de retour, si bien qu'un aperçu déjà
      en cache, un scan source introuvable ou une composition en échec la faisaient disparaître
      — définitivement, la planche entrant alors dans la mémoire d'échec ;
    · la mémoire d'échec est **par genre**. Un aperçu qu'on ne sait pas composer ne condamne
      plus la vignette de sa planche, qui, elle, réussit très bien.

    ## Ce que le fil ne fait jamais

    Toucher un widget, écrire un checkpoint, construire un `QPixmap`. Il dépose ses résultats
    dans le cache (qui porte son propre verrou) et émet un signal ; c'est le fil d'affichage
    qui décide quoi en faire."""

    def __init__(self, signaux: SignauxTravail, parent=None):
        super().__init__(parent)
        self.signaux = signaux
        self._verrou = threading.Lock()
        self._reveil = threading.Event()
        self._voulues: list[int] = []
        self._courante: int = 0
        # Travaux qui ont échoué, en `(genre, planche)`. ⚠ Sans cette mémoire, une planche qui
        # échoue n'entre jamais au cache, donc reste « manquante », donc est redemandée en
        # boucle — et affame toutes les autres. Mesuré par un test : sur trois planches dont
        # une illisible, seule l'illisible était traitée, indéfiniment. Le couple, et non le
        # seul numéro : un aperçu impossible ne doit pas emporter sa vignette.
        self._echoues: set[tuple[str, int]] = set()
        self._arret = False
        self._vignette = None
        self._composer = None
        self._restant = None

    # ------------------------------------------------------------------ #

    def brancher(self, vignette, composer, restant) -> None:
        """Les trois rappels de la voie de lecture, tous appelés **depuis ce fil**.

        · `vignette(index) -> bool` — fabrique la vignette si elle manque ou a vieilli ;
        · `composer(index) -> bool` — compose l'aperçu et le range au cache ;
        · `restant(index) -> str | None` — `GENRE_VIGNETTE`, `GENRE_APERCU`, ou `None` si la
          planche est réglée. C'est lui qui porte la connaissance de ce qui reste à faire ;
          le fil n'en sait rien et n'a pas à en savoir.

        Aucun des trois ne doit toucher un widget."""
        self._vignette = vignette
        self._composer = composer
        self._restant = restant

    def vouloir(self, pages, courante: int) -> None:
        """Remplace l'ensemble des planches à précharger. Idempotent, appelable à volonté."""
        with self._verrou:
            self._voulues = [int(p) for p in pages]
            self._courante = int(courante)
        self._reveil.set()

    def oublier(self) -> None:
        """Cesse tout préchargement — au changement de tome, par exemple."""
        self.vouloir([], 0)

    def reessayer(self, index: int | None = None) -> None:
        """Rend une planche (ou toutes) de nouveau composable après un échec.

        ⚠ `vouloir()` ne le fait PAS : il est appelé à chaque changement de planche, et
        réarmer là ferait retomber dans la boucle d'échec. On ne réessaie que quand quelque
        chose a pu changer — un run vient de réécrire la planche, ou l'on rouvre le tome.

        Réarme les DEUX genres : l'appelant raisonne en planches, pas en natures de travail,
        et ce qui a pu changer (un run, une réouverture) les concerne l'une comme l'autre."""
        with self._verrou:
            if index is None:
                self._echoues.clear()
            else:
                index = int(index)
                self._echoues -= {(GENRE_VIGNETTE, index), (GENRE_APERCU, index)}

    def arreter(self) -> None:
        self._arret = True
        self._reveil.set()

    # ------------------------------------------------------------------ #

    def _rang(self, genre: str, planche: int, courante: int) -> int:
        """Priorité d'un travail. Plus petit passe d'abord.

        L'aperçu de la planche COURANTE est seul en tête : c'est la seule image que
        l'utilisateur est en train de regarder, et l'attendre derrière quoi que ce soit se voit
        immédiatement. Viennent ensuite toutes les vignettes — quelques dizaines de
        millisecondes pièce, et c'est la bande entière qui se remplit —, puis les aperçus de la
        fenêtre, à 1,37 s l'unité pour des planches où l'on n'est pas encore."""
        if genre == GENRE_APERCU and planche == courante:
            return 0
        return 1 if genre == GENRE_VIGNETTE else 2

    def _prochaine(self) -> tuple[str | None, int | None, int, int]:
        """`(genre, planche, nombre de réglées, nombre de voulues)`.

        À genre égal, la plus proche de la planche courante d'abord : c'est l'ordre dans lequel
        l'utilisateur va les rencontrer."""
        with self._verrou:
            voulues, courante = list(self._voulues), self._courante
            echoues = set(self._echoues)
        if not voulues or self._restant is None:
            return None, None, 0, 0
        # Un travail en échec compte comme RÉGLÉ : la barre doit pouvoir atteindre son total,
        # et l'utilisateur n'a rien à attendre d'une planche qu'on ne sait pas composer.
        manquants = []
        for planche in voulues:
            genre = self._restant(planche)
            if genre is not None and (genre, planche) not in echoues:
                manquants.append((genre, planche))
        reglees = len(voulues) - len(manquants)
        if not manquants:
            return None, None, reglees, len(voulues)
        genre, planche = min(
            manquants,
            key=lambda gp: (self._rang(gp[0], gp[1], courante), abs(gp[1] - courante)))
        return genre, planche, reglees, len(voulues)

    def run(self) -> None:                       # noqa: D102 — surcharge de QThread
        while not self._arret:
            genre, planche, pretes, total = self._prochaine()
            if planche is None:
                # Rien à faire : on dort jusqu'au prochain `vouloir`. Le délai borne l'attente
                # au cas où un `set()` arriverait juste avant le `clear()`.
                self._reveil.wait(0.25)
                self._reveil.clear()
                continue
            faire = self._vignette if genre == GENRE_VIGNETTE else self._composer
            try:
                if faire is not None and faire(planche):
                    self.signaux.apercu_pret.emit(planche)
            except Exception as err:              # noqa: BLE001 — un aperçu raté n'arrête rien
                with self._verrou:
                    self._echoues.add((genre, planche))
                # ⚠ Volontairement discret. Un aperçu est un confort : échouer à en composer un
                # ne doit ni interrompre le préchargement, ni noyer le journal sous une ligne
                # par planche non détectée d'un tome à peine commencé.
                self.signaux.ligne.emit("verbose",
                                        f"{genre} de la planche {planche} : "
                                        f"{type(err).__name__} — {err}")
            self.signaux.prechargement.emit(pretes + 1, total)


# ─────────────────────────────────────────────────────────────────────────────
# Fabriques de tâches
# ─────────────────────────────────────────────────────────────────────────────

def build_dir_de(config: dict, brique: str, projet: str, tome: str) -> Path:
    """Dossier de build d'un tome — celui où le fichier `STOP` sera écrit."""
    chemins = (core_config.section(config, "manga", "chemins") if brique == "manga"
               else config["chemins"])
    base = Path(chemins["build"]) / projet / tome
    return base / "manga" if brique == "manga" else base


def tache_run(*, brique: str, projet: str, tome: str, config: dict, reporter: Reporter,
              force: bool = False, depuis: str | None = None,
              page: int | None = None) -> Tache:
    """Un `process_volume`, avec l'enveloppe d'énergie et de modèles de `run_manga.py`.

    La recopier plutôt que l'inventer garantit qu'un run lancé d'ici laisse la machine dans le
    même état qu'un run lancé au terminal : VRAM libérée, et modèle préchargé seulement s'il
    va réellement servir (la garde `traduira`)."""

    def _travail():
        if brique == "manga":
            from manga.checkpoints import downstream
            from manga.orchestrator_manga import process_volume
            traduira = depuis is None or "traduction" in downstream(depuis)
            llm_cfg = core_config.section(config, "manga", "llm")
            modeles = cli.models_in_config(config, "manga") if traduira else []

            def appel():
                return process_volume(projet, tome, config, reporter=reporter, force=force,
                                      restart_from=depuis, only_page=page)
        else:
            from pipeline.orchestrator import process_volume
            llm_cfg = config["llm"]
            modeles = cli.models_in_config(config, None)

            def appel():
                return process_volume(projet, tome, config, reporter=reporter, force=force,
                                      restart_from=depuis, only_chapter=page)

        dry = bool(config.get("options", {}).get("dry_run"))
        cli.precharger_modeles(config, modeles, dry_run=dry, base_url=llm_cfg.get("base_url"))
        try:
            termine = appel()
        finally:
            # Blindé comme le `finally` des deux CLI : la VRAM se libère même si le run lève,
            # et même si l'utilisateur ferme la fenêtre.
            cli.shielded_unload(config, modeles, base_url=llm_cfg.get("base_url"))
        return ("Run terminé." if termine
                else "Run arrêté proprement — relance pour reprendre.")

    return Tache(genre=GENRE_RUN, fonction=_travail, planche=None,
                 libelle=f"Run {brique} — {projet} / {tome}"
                         + (f", planche {page}" if page else ""))


def demander_arret(config: dict, brique: str, projet: str, tome: str) -> None:
    """Écrit le fichier `STOP` — le même mécanisme que `--stop`, pas un second en parallèle.

    Le run s'arrête à la prochaine frontière propre : une planche, ou un **lot** de planches
    si `manga.lot.planches` > 1."""
    control.request_stop(build_dir_de(config, brique, projet, tome))
