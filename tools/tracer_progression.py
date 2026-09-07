#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que le canal de progression dit VRAIMENT pendant un run — `PLAN-32` étape 0.1.

    # enregistrer un run réel, brique par brique
    python tools/tracer_progression.py --enregistrer "Mon Manga" Vol.1 --brique manga \
        --sortie docs/mesures/traces/manga.jsonl

    # reconstruire la trace d'un run DÉJÀ passé, depuis son perf.log
    python tools/tracer_progression.py --depuis-perf "build/X/Vol.1/manga/perf.log" \
        --sortie trace.jsonl

    # le verdict : reculs, dénominateurs, phases, secondes sans temps restant affichable
    python tools/tracer_progression.py --analyser trace.jsonl
    python tools/tracer_progression.py --depuis-perf build/*/*/manga/perf.log --markdown

## Les deux sources, et pourquoi il en faut deux

**L'enregistreur** (`Enregistreur`) est un `Reporter` décorateur : il transmet tout à celui
qu'il enveloppe et écrit `(horodatage, méthode, arguments)` en JSONL. C'est la source
directe — elle voit exactement ce que l'interface voit — mais elle exige de **relancer** le
run. Sur un tome de 150 planches, cela coûte des heures de GPU et un appel LLM par lot.

**La reconstruction** (`depuis_perf_log`) lit un `perf.log` déjà écrit. Elle est utilisable
sur les runs du dépôt sans en relancer un seul, et ses durées sont **réelles**. Ce qu'elle
n'a pas : le temps non instrumenté (assemblage CBZ, export docx, chargement de config), qui
n'apparaît dans aucune ligne de perf. Les deux chiffres sont donc publiés séparément.

⚠ **Ce que la trace ne dit pas.** Elle porte le canal, pas l'écran : elle ne sait pas si la
fenêtre était visible, ni ce que l'utilisateur regardait. Et une reconstruction ne voit que
ce qui est instrumenté : la passe terminologique du manga écrit bien une ligne de perf par
planche, mais elle n'appelle ni `stage` ni `progres` — c'est précisément un des trous que
l'étape 0 chiffre, et la reconstruction le reproduit fidèlement plutôt que de le combler.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core.reporter import Reporter                                          # noqa: E402
from gui.avancement import FENETRE, MINIMUM, Estimateur                     # noqa: E402


# --------------------------------------------------------------------------- #
#  1. L'enregistreur — un `Reporter` décorateur
# --------------------------------------------------------------------------- #

def _json_sur(valeur):
    """Rend un argument sérialisable **sans jamais lever**.

    `volume(plan)` reçoit un `VolumePlan`, pas un scalaire. On en garde ce qui décrit un
    run — projet, tome, nombre de chapitres — et rien d'autre : une trace n'a pas à
    transporter le texte de l'œuvre."""
    if valeur is None or isinstance(valeur, (bool, int, float, str)):
        return valeur
    if isinstance(valeur, (list, tuple)):
        return [_json_sur(v) for v in valeur]
    resume = {}
    for champ in ("project", "volume", "n_chapters", "mode", "pivot"):
        if hasattr(valeur, champ):
            resume[champ] = _json_sur(getattr(valeur, champ))
    return resume or repr(valeur)[:120]


class Enregistreur(Reporter):
    """Enveloppe un `Reporter` et journalise chaque appel en JSONL.

    ⚠ **Il n'hérite du comportement de personne : il DÉLÈGUE.** Hériter et appeler `super()`
    imprimerait la sortie du `Reporter` texte EN PLUS de celle du reporter enveloppé. La
    classe de base n'est là que pour le contrat (`isinstance`) et pour les méthodes qu'un
    orchestrateur pourrait appeler sans qu'on y ait pensé.

    L'horloge est **injectée**, comme dans `gui/avancement.py` et
    `illustration/progression.py` : c'est ce qui permet de tester l'enregistreur à la
    milliseconde sans dormir."""

    def __init__(self, delegue, fichier=None, horloge=time.monotonic):
        self.delegue = delegue
        self._fichier = fichier
        self._horloge = horloge
        self._t0 = float(horloge())
        self.evenements: list[dict] = []

    # ---- la mécanique ---------------------------------------------------- #

    def _noter(self, methode: str, *args) -> None:
        evenement = {"t": round(float(self._horloge()) - self._t0, 4),
                     "methode": methode, "args": [_json_sur(a) for a in args]}
        self.evenements.append(evenement)
        if self._fichier is not None:
            self._fichier.write(json.dumps(evenement, ensure_ascii=False) + "\n")
            self._fichier.flush()

    def _relayer(self, methode: str, *args):
        cible = getattr(self.delegue, methode, None)
        return cible(*args) if callable(cible) else None

    # ---- le protocole ---------------------------------------------------- #

    def volume(self, plan) -> None:
        self._noter("volume", plan)
        self._relayer("volume", plan)

    def chapter(self, idx: int, total: int, title: str) -> None:
        self._noter("chapter", idx, total, title)
        self._relayer("chapter", idx, total, title)

    def stage(self, name: str) -> None:
        self._noter("stage", name)
        self._relayer("stage", name)

    def block(self, idx: int, total: int) -> None:
        self._noter("block", idx, total)
        self._relayer("block", idx, total)

    def progres(self, courant: int, total: int, objet: str = "") -> None:
        self._noter("progres", courant, total, objet)
        self._relayer("progres", courant, total, objet)

    def phase(self, identifiant: str, libelle: str = "") -> None:
        self._noter("phase", identifiant, libelle)
        self._relayer("phase", identifiant, libelle)

    def info(self, msg: str) -> None:
        self._noter("info", msg)
        self._relayer("info", msg)

    def verbose(self, msg: str) -> None:
        self._noter("verbose", msg)
        self._relayer("verbose", msg)

    def warn(self, msg: str) -> None:
        self._noter("warn", msg)
        self._relayer("warn", msg)

    def finish(self, outputs: list[str]) -> None:
        self._noter("finish", outputs)
        self._relayer("finish", outputs)

    def stopped(self, done: int, total: int) -> None:
        self._noter("stopped", done, total)
        self._relayer("stopped", done, total)

    # ---- ce qui ne s'enregistre pas : la plomberie du log ---------------- #

    def set_console_verbose(self, actif: bool) -> None:
        self._relayer("set_console_verbose", actif)

    def set_verbose_log(self, path) -> None:
        self._relayer("set_verbose_log", path)

    def close(self) -> None:
        self._relayer("close")

    def __enter__(self):
        self._relayer("__enter__")
        return self

    def __exit__(self, *a):
        return False


# --------------------------------------------------------------------------- #
#  2. La reconstruction depuis un `perf.log`
# --------------------------------------------------------------------------- #

_ENTETE = re.compile(r"^# (?:Angelith|Yume-Trad) ([\d.]+) — (.+?) — python (.*)$")
_PERF_PAGE = re.compile(r"^\[(?P<etape>[^\]]+)\] page (?P<page>\d+)/(?P<total>\d+)\s*:\s*"
                        r"(?:(?P<duree>[\d.]+)s)?")
_PERF_BLOC = re.compile(r"^(?:ch(?P<chap>\d+) )?\[(?P<etape>[^\]]+)\] bloc "
                        r"(?P<bloc>\d+)/(?P<total>\d+)\s*:\s*(?P<duree>[\d.]+)s")
_PERF_GLOSSARISTE = re.compile(r"^(?:ch(?P<chap>\d+) )?\[glossariste\] optimisation\s*:\s*"
                               r"(?P<duree>[\d.]+)s")

#: Les étapes du balayage A, dans l'ordre où `orchestrator_manga` les paie. Une planche
#: n'entre dans le balayage A que si l'une d'elles est à refaire (`etapes_cv`).
ETAPES_BALAYAGE_A = ("detection", "nettoyage", "ocr", "sfx")
#: Celles du balayage B. `psd` n'en fait pas partie : c'est une sortie annexe, écrite dans la
#: même itération, et elle ne porte aucun appel de progression.
ETAPES_BALAYAGE_B = ("traduction", "rendu")


def runs_de_perf(texte: str) -> list[list[str]]:
    """Découpe un `perf.log` en runs. Le fichier s'ouvre en `"a"` : ils s'y EMPILENT.

    ⚠ Un run **sans en-tête** ouvre le fichier : les versions antérieures à la 1.7.0
    n'écrivaient pas la ligne `# Angelith …`. Le premier bloc est donc rendu même s'il ne
    commence pas par un `#`, sinon on perdrait en silence les plus anciens runs du dépôt —
    qui sont précisément les seuls runs NEUFS qu'il possède."""
    runs: list[list[str]] = []
    courant: list[str] = []
    for ligne in texte.splitlines():
        if _ENTETE.match(ligne):
            if courant:
                runs.append(courant)
            courant = [ligne]
            continue
        courant.append(ligne)
    if courant:
        runs.append(courant)
    return [r for r in runs if any(l.startswith(("[", "ch")) for l in r)]


def _duree(m) -> float:
    valeur = m.groupdict().get("duree")
    return float(valeur) if valeur else 0.0


def trace_manga(lignes: list[str]) -> list[dict]:
    """Reconstruit la séquence `stage` / `progres` d'un run manga depuis ses lignes de perf.

    La séquence est **déterminée par le code** : `orchestrator_manga` annonce une étape puis
    appelle `progres(i, total)` juste avant de payer les étapes CV de la planche `i`
    (balayage A, L894-895), puis recommence sur le même dénominateur au balayage B
    (L1614-1616). Chaque groupe de lignes de perf portant la même planche est donc précédé,
    dans le run réel, d'exactement un couple `stage` + `progres`.

    ⚠ **Le canal `phase` est RECONSTRUIT, pas relevé.** Aucun `perf.log` du dépôt n'a été
    écrit par une version qui le connaissait — il est livré par ce lot. Mais le balayage
    auquel appartient une ligne est un fait du code, pas une hypothèse : `[detection]`,
    `[nettoyage]`, `[ocr]` et `[sfx]` ne sont payés que dans le balayage A, `[terminologie]`
    que dans la passe terminologique, `[traduction]` et `[rendu]` que dans le balayage B. La
    reconstruction pose donc les frontières de phase là où le code les pose, et le document
    de mesure le dit plutôt que de laisser croire à un relevé."""
    evenements: list[dict] = []
    t = 0.0
    precedent: tuple[str, int] | None = None      # (balayage, page)
    phase_posee = ""
    pages_analysees = 0

    def _noter(methode, *args):
        evenements.append({"t": round(t, 4), "methode": methode, "args": list(args)})

    def _phase(identifiant):
        nonlocal phase_posee
        if identifiant != phase_posee:
            phase_posee = identifiant
            _noter("phase", identifiant, "")

    _phase("preparation")
    for ligne in lignes:
        m = _PERF_PAGE.match(ligne)
        if m:
            etape, page, total = m["etape"], int(m["page"]), int(m["total"])
            if etape in ETAPES_BALAYAGE_A:
                balayage = "A"
            elif etape in ETAPES_BALAYAGE_B:
                balayage = "B"
            elif etape == "terminologie":
                balayage = "T"
            else:
                balayage = ""          # psd, projet… : aucune progression annoncée
            if balayage and precedent != (balayage, page):
                if balayage == "A":
                    pages_analysees += 1
                    # La première planche porte le chargement du modèle ONNX : c'est la
                    # phase que `PLAN-32` L32.6 demande de NOMMER plutôt que d'estimer.
                    _phase("chargement" if pages_analysees == 1 else "analyse")
                elif balayage == "T":
                    _phase("terminologie")
                else:
                    _phase("traduction")
                if balayage != "T":
                    _noter("stage", f"Page {page}/{total} — page_{page:04d}.png ({etape})")
                _noter("progres", page, total, f"page_{page:04d}.png")
                precedent = (balayage, page)
            t += _duree(m)
            continue
        m = _PERF_GLOSSARISTE.match(ligne)
        if m:
            t += _duree(m)
    _phase("finalisation")
    return evenements


def trace_ln(lignes: list[str]) -> list[dict]:
    """Reconstruit la séquence `chapter` / `stage` / `block` d'un run light novel.

    `pipeline/orchestrator` appelle `chapter(ci+1, n)` à l'entrée de chaque chapitre et
    `block(bi+1, n)` avant **chaque bloc calculé** (`_run_blocks` L799) — un bloc repris du
    cache n'émet rien, et n'écrit pas non plus de ligne de perf : les deux se correspondent.

    ⚠ `n_ch` n'est pas dans le `perf.log`. On prend le plus grand `chNN` vu, ce qui est un
    **minorant** : un run arrêté au chapitre 5 d'un tome qui en compte 12 sera reconstruit
    comme un tome de 5. Cela ne change ni les reculs ni les dénominateurs de `block`, qui
    sont ce que l'étape 0 mesure."""
    n_ch = 0
    for ligne in lignes:
        m = _PERF_BLOC.match(ligne) or _PERF_GLOSSARISTE.match(ligne)
        if m and m.groupdict().get("chap"):
            n_ch = max(n_ch, int(m["chap"]))
    evenements: list[dict] = []
    t = 0.0
    chapitre = None
    etape = None

    def _noter(methode, *args):
        evenements.append({"t": round(t, 4), "methode": methode, "args": list(args)})

    _noter("phase", "preparation", "")
    for ligne in lignes:
        m = _PERF_BLOC.match(ligne)
        if not m:
            m2 = _PERF_GLOSSARISTE.match(ligne)
            if m2:
                _noter("stage", "optimisation du glossaire")
                t += _duree(m2)
            continue
        chap = int(m["chap"]) if m.groupdict().get("chap") else 1
        if chap != chapitre:
            if chapitre is None:
                _noter("phase", "chapitres", "")
            chapitre = chap
            etape = None
            _noter("chapter", chap, max(n_ch, chap), "")
        if m["etape"] != etape:
            etape = m["etape"]
            _noter("stage", etape)
        _noter("block", int(m["bloc"]), int(m["total"]))
        t += _duree(m)
    _noter("phase", "finalisation", "")
    return evenements


def depuis_perf_log(chemin, brique: str = "") -> list[list[dict]]:
    """Une trace par run empilé dans le fichier. `brique` vide = deviné sur le contenu."""
    texte = Path(chemin).read_text(encoding="utf-8", errors="replace")
    traces = []
    for lignes in runs_de_perf(texte):
        genre = brique or ("manga" if any(_PERF_PAGE.match(l) for l in lignes) else "ln")
        traces.append(trace_manga(lignes) if genre == "manga" else trace_ln(lignes))
    return [t for t in traces if t]


# --------------------------------------------------------------------------- #
#  3. L'analyse — les quatre chiffres que le plan réclame
# --------------------------------------------------------------------------- #

def avancements(evenements: list[dict]):
    """`(t, courant, total)` de chaque événement qui fait bouger une barre AUJOURD'HUI.

    C'est la définition d'AVANT le lot, et c'est délibéré : l'étape 0 mesure l'état
    existant. `ReporterQt` émet `progression` sur `chapter`, sur `block`, sur `progres`, et
    sur les libellés d'étape que `progression_de_stage` sait lire."""
    from core.progression import progression_de_stage
    for ev in evenements:
        m, a = ev["methode"], ev["args"]
        if m in ("progres", "chapter", "block"):
            yield ev["t"], int(a[0]), int(a[1])
        elif m == "stage":
            courant, total = progression_de_stage(str(a[0]))
            if courant:
                yield ev["t"], courant, total


def analyser(evenements: list[dict], *, fenetre: int = FENETRE,
             minimum: int = MINIMUM) -> dict:
    """Reculs, dénominateurs, durée, et **secondes sans temps restant affichable**.

    Le dernier chiffre est celui qui décide du lot (`PLAN-32` §0.1) : il rejoue
    `gui/avancement.Estimateur` sur la trace, exactement comme la fenêtre le fait, et
    additionne les intervalles pendant lesquels `restant()` rend `None`."""
    points = list(avancements(evenements))
    duree = max((ev["t"] for ev in evenements), default=0.0)
    reculs = 0
    denominateurs: set[int] = set()
    precedent = None
    for _, courant, total in points:
        if total > 0:
            denominateurs.add(total)
        if precedent is not None and courant < precedent:
            reculs += 1
        precedent = courant

    # Rejeu de l'estimateur, intervalle par intervalle.
    horloge = {"t": 0.0}
    estimateur = Estimateur(fenetre=fenetre, minimum=minimum, horloge=lambda: horloge["t"])
    sans_eta = 0.0
    precedent_t = 0.0
    affichable = False
    for t, courant, total in points:
        sans_eta += 0.0 if affichable else (t - precedent_t)
        precedent_t = t
        horloge["t"] = t
        estimateur.noter(courant, total)
        affichable = total > 0 and estimateur.restant(total) is not None
    sans_eta += 0.0 if affichable else (duree - precedent_t)

    return {
        "evenements": len(evenements),
        "avancements": len(points),
        "duree_s": round(duree, 1),
        "reculs": reculs,
        "denominateurs": sorted(denominateurs),
        "sans_eta_s": round(sans_eta, 1),
        "sans_eta_part": round(sans_eta / duree, 4) if duree else None,
    }


def rejouer_dans_le_modele(evenements: list[dict], jeu: str = "") -> dict:
    """Rejoue la trace dans `core/progression.py` et rend le verdict de MONOTONIE.

    C'est le critère 3 du plan, exécutable en dix secondes sur n'importe quelle trace : « un
    test rejoue les traces réelles en assertant que `fraction()` ne décroît jamais »."""
    from core import progression as prog
    from core.progression import progression_de_stage

    if not jeu:
        jeu = "ln" if any(e["methode"] == "chapter" for e in evenements) else "manga"
    horloge = {"t": 0.0}
    modele = prog.Progression(estimateur=Estimateur(horloge=lambda: horloge["t"]))
    modele.declarer(prog.PHASES[jeu])

    suite: list[float | None] = []
    duree = max((ev["t"] for ev in evenements), default=0.0)
    sans_eta = 0.0
    precedent_t = 0.0
    affichable = False
    for ev in evenements:
        t = float(ev.get("t") or 0.0)
        sans_eta += 0.0 if affichable else (t - precedent_t)
        precedent_t = t
        horloge["t"] = t
        prog.appliquer(modele, ev.get("methode", ""), ev.get("args", []),
                       repli=progression_de_stage)
        suite.append(modele.fraction())
        affichable = modele.restant() is not None
    sans_eta += 0.0 if affichable else (duree - precedent_t)

    connues = [f for f in suite if f is not None]
    reculs = sum(1 for a, b in zip(connues, connues[1:]) if b < a - 1e-12)
    return {"jeu": jeu, "points": len(connues), "reculs_fraction": reculs,
            "fraction_finale": round(connues[-1], 4) if connues else None,
            "reculs_de_canal": modele.reculs, "nature": modele.nature(),
            "indetermines": len(suite) - len(connues),
            "duree_s": round(duree, 1), "sans_eta_s": round(sans_eta, 1),
            "sans_eta_part": round(sans_eta / duree, 4) if duree else None}


def phases_observees(evenements: list[dict]) -> list[tuple[str, float]]:
    """Durée de chaque libellé d'étape, dans l'ordre où il apparaît.

    Grossier **exprès** : le libellé est la seule chose que la trace porte avant ce lot. Le
    poids par phase, lui, se mesure sur les lignes de perf — c'est `banc_progression.py`."""
    resultat: list[tuple[str, float]] = []
    courant = None
    debut = 0.0
    for ev in evenements:
        if ev["methode"] != "stage":
            continue
        nom = re.sub(r"\d+", "N", str(ev["args"][0]))[:60]
        if nom != courant:
            if courant is not None:
                resultat.append((courant, round(ev["t"] - debut, 1)))
            courant, debut = nom, ev["t"]
    if courant is not None:
        fin = max((ev["t"] for ev in evenements), default=debut)
        resultat.append((courant, round(fin - debut, 1)))
    return resultat


# --------------------------------------------------------------------------- #
#  4. La CLI
# --------------------------------------------------------------------------- #

def nom_de_volume(chemin) -> str:
    """« Projet / Tome » depuis un chemin de `perf.log`.

    ⚠ Les deux briques ne rangent pas leur log au même niveau : le light novel écrit
    `build/<Projet>/<Tome>/perf.log`, le manga `build/<Projet>/<Tome>/manga/perf.log`
    (cf. `core/cli.make_reporter`, dont le dossier est calculé par l'appelant). Compter les
    segments depuis la fin donnait donc « build / Projet » d'un côté et « Projet / Tome » de
    l'autre — deux tomes d'un même projet se confondaient sous le même nom."""
    parties = [p for p in Path(chemin).parts[:-1]
               if p not in ("build", "manga", "ocr", "illustrations")]
    return " / ".join(parties[-2:]) if parties else str(chemin)


def lire_trace(chemin) -> list[dict]:
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def ecrire_trace(evenements: list[dict], chemin) -> None:
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        for ev in evenements:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _enregistrer(args) -> int:
    from core import cli
    config = cli.charger_config(args.config)
    config.setdefault("options", {})["verbose"] = True
    sortie = Path(args.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with open(sortie, "w", encoding="utf-8") as f:
        tracer = Enregistreur(Reporter(), f)
        if args.brique == "manga":
            from manga.orchestrator_manga import process_volume
        else:
            from pipeline.orchestrator import process_volume
        process_volume(args.projet, args.tome, config, reporter=tracer)
    print(f"{len(tracer.evenements)} événement(s) → {sortie}")
    return 0


def ligne_markdown(nom: str, r: dict) -> str:
    part = "—" if r["sans_eta_part"] is None else f"{r['sans_eta_part'] * 100:.1f} %"
    return (f"| {nom} | {r['evenements']} | {r['avancements']} | {r['duree_s']:.0f} | "
            f"**{r['reculs']}** | {len(r['denominateurs'])} | {r['sans_eta_s']:.0f} | {part} |")


ENTETE_MARKDOWN = ("| trace | événements | avancements | durée (s) | reculs | "
                   "dénominateurs | sans ETA (s) | part |\n|---|--:|--:|--:|--:|--:|--:|--:|")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--enregistrer", action="store_true",
                   help="lance un vrai run sous l'enregistreur")
    p.add_argument("projet", nargs="?")
    p.add_argument("tome", nargs="?")
    p.add_argument("--brique", choices=("manga", "ln"), default="manga")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--depuis-perf", nargs="+", default=[],
                   help="reconstruit la ou les traces d'un perf.log")
    p.add_argument("--analyser", nargs="+", default=[], help="fichiers .jsonl à juger")
    p.add_argument("--sortie", help="où écrire la trace (.jsonl) — le run le plus long")
    p.add_argument("--markdown", action="store_true")
    p.add_argument("--phases", action="store_true", help="durée par libellé d'étape")
    p.add_argument("--rejouer", action="store_true",
                   help="rejoue la trace dans core/progression.py et juge la monotonie")
    p.add_argument("--anonyme", action="store_true",
                   help="ne nomme pas les œuvres : « trace 1 », « trace 2 »…")
    args = p.parse_args(argv)

    if args.enregistrer:
        if not (args.projet and args.tome and args.sortie):
            p.error("--enregistrer exige projet, tome et --sortie")
        return _enregistrer(args)

    traces: list[tuple[str, list[dict]]] = []
    for chemin in args.depuis_perf:
        reconstruites = depuis_perf_log(chemin)
        nom = nom_de_volume(chemin)
        for i, trace in enumerate(reconstruites, 1):
            traces.append((f"{nom} · run {i}/{len(reconstruites)}", trace))
        if args.sortie and reconstruites:
            plus_long = max(reconstruites, key=len)
            ecrire_trace(plus_long, args.sortie)
            print(f"{len(plus_long)} événement(s) → {args.sortie}")
    for chemin in args.analyser:
        traces.append((Path(chemin).stem, lire_trace(chemin)))

    if not traces:
        p.error("rien à faire : --enregistrer, --depuis-perf ou --analyser")
    if args.anonyme:
        traces = [(f"trace {i}", t) for i, (_, t) in enumerate(traces, 1)]

    if args.markdown:
        print(ENTETE_MARKDOWN)
        for nom, trace in traces:
            print(ligne_markdown(nom, analyser(trace)))
    else:
        for nom, trace in traces:
            r = analyser(trace)
            print(f"\n=== {nom}")
            for cle, valeur in r.items():
                print(f"  {cle:16} {valeur}")
    if args.phases:
        for nom, trace in traces:
            print(f"\n--- phases de {nom}")
            for libelle, secondes in phases_observees(trace):
                print(f"  {secondes:9.1f} s  {libelle}")
    if args.rejouer:
        if args.markdown:
            print("\n| trace | jeu | points | reculs de fraction | reculs de canal | "
                  "indéterminés | sans ETA (s) | part | fraction finale |")
            print("|---|---|--:|--:|--:|--:|--:|--:|--:|")
        for nom, trace in traces:
            r = rejouer_dans_le_modele(trace)
            if args.markdown:
                part = "—" if r["sans_eta_part"] is None else f"{r['sans_eta_part'] * 100:.1f} %"
                print(f"| {nom} | {r['jeu']} | {r['points']} | **{r['reculs_fraction']}** | "
                      f"{r['reculs_de_canal']} | {r['indetermines']} | "
                      f"{r['sans_eta_s']:.0f} | {part} | {r['fraction_finale']} |")
            else:
                print(f"\n--- rejeu de {nom}")
                for cle, valeur in r.items():
                    print(f"  {cle:18} {valeur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
