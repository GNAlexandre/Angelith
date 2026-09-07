#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le POIDS de chaque phase d'un run, mesuré sur les `perf.log` du dépôt — `PLAN-32` § 0.2.

    python tools/banc_progression.py
    python tools/banc_progression.py --markdown
    python tools/banc_progression.py --markdown --anonyme > docs/mesures/x.md
    python tools/banc_progression.py --detail          # volume par volume

## Ce que l'outil calcule, et sur quoi

Un modèle de progression monotone a besoin d'un poids par phase — « la traduction, c'est
62 % du run ». **Ces poids doivent être mesurés**, et le dépôt a de quoi : `perf.log` est
écrit par `core/cli.make_reporter` dans tous les cas (le flag `--verbose` ne décide que de
l'AFFICHAGE), et il porte une ligne datée par étape et par unité de travail.

Chaque ligne `[<phase>] page N/T : X.XXs` ou `[<phase>] bloc i/n : X.Xs` donne la seconde
payée par cette phase. Leur somme par run donne la **part** de chaque phase. On publie la
médiane des parts, le `n` de runs, et l'**écart min-max**.

## La règle d'abandon, et elle est écrite dans le plan

> ⚠ Si l'écart min-max d'une phase dépasse un facteur 3, cette phase n'a pas de poids
> utilisable — on n'invente pas un pourcentage, on affiche l'avancement compté.

`FACTEUR_ABANDON` porte ce seuil, et `poids_utilisables()` rend le verdict phase par phase.
C'est cette fonction qui alimente `core/progression.py` : un poids que ce banc refuse n'est
pas recopié « au cas où ».

## Neuf ou reprise — deux tableaux, pas un

Le saut intelligent fausse tout poids naïf : le dépôt mesure 629 ms pour constater qu'un
chapitre est à jour contre 3 min 9 s pour le refaire. Un run de reprise n'a donc pas du tout
la même répartition qu'un run complet, et les mélanger produirait une moyenne qui ne décrit
aucun des deux. La classification est explicite (`est_neuf`) et publiée avec les tableaux.

## Ce que la mesure ne dit pas

- **Rien du temps NON instrumenté.** Le chargement de la config, la lecture du plan,
  l'assemblage CBZ/PDF, l'export docx et le rendu Pandoc n'écrivent aucune ligne de perf.
  Les parts sont donc des parts du **temps instrumenté**, jamais de la durée d'horloge du
  run — les deux ne sont pas le même dénominateur, et c'est écrit dans chaque tableau.
- **Rien d'une machine autre que celle qui a produit les logs.** Les `perf.log` du dépôt ont
  été écrits sur une seule machine, sur une plage de **douze** versions allant de la 0.29.0 à
  la 2.20.0 (relevé le 2026-09-05 sur les lignes d'en-tête `# Angelith …` de `build/`). Un poids
  mesuré ici décrit ce couple-là, et il mélange des versions dont les coûts ont bougé.
- **Rien des runs qui n'ont jamais eu lieu.** Aucun `perf.log` de run manga NEUF de bout en
  bout n'existe pour tous les volumes : plusieurs ont été traités par étapes successives.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.tracer_progression import (_PERF_BLOC, _PERF_GLOSSARISTE,      # noqa: E402
                                      _PERF_PAGE, nom_de_volume, runs_de_perf)

#: Au-delà de ce facteur entre la part la plus faible et la plus forte, une phase n'a **pas**
#: de poids utilisable (`PLAN-32` § 0.2). Trois, et pas dix : un modèle qui se trompe d'un
#: facteur trois sur le poids d'une phase annonce « 20 % » là où on est à 60 %.
FACTEUR_ABANDON = 3.0

#: En deçà de ce nombre de runs, une médiane n'est pas une médiane. Publié avec chaque ligne
#: pour que le lecteur juge lui-même — le banc ne cache aucune phase, il les qualifie.
MINIMUM_RUNS = 3

#: Les phases du manga, dans l'ordre où l'orchestrateur les paie. `psd` et `projet` en sont
#: exclus : le PSD est une sortie annexe (désarmée par défaut) et `[projet]` est une ligne
#: d'écriture de métadonnées, pas une étape de traitement.
PHASES_MANGA = ("detection", "nettoyage", "ocr", "sfx", "terminologie", "glossariste",
                "traduction", "rendu")

#: Celles du light novel. `révision` et `cohérence` sont des étages optionnels du mode
#: « relecture » ; ils sont relevés mais restent hors du tronc commun.
PHASES_LN = ("terminologie", "glossariste", "traduction", "correction", "mise en page",
             "révision", "cohérence")

#: **La granularité qui compte pour une barre**, et ce n'est pas celle des lignes de perf.
#:
#: L'orchestrateur ne peut pas annoncer « détection » puis « nettoyage » puis « OCR » : il les
#: paie planche par planche, dans le même balayage, et une phase qui oscille n'est pas une
#: phase. Ce qui est monotone, ce sont les BALAYAGES — et ce sont eux qu'annonce
#: `Reporter.phase`. Les regrouper change aussi la mesure : détection, nettoyage, OCR et SFX
#: se compensent l'un l'autre d'un tome à l'autre, si bien que leur somme est trois fois plus
#: stable que chacun pris à part (×1,6 contre ×5,0).
#:
#: C'est cette table qui alimente `core/progression.POIDS_MESURES`.
PHASES_DE_PROGRESSION: dict[str, dict[str, tuple[str, ...]]] = {
    "manga": {
        "analyse": ("detection", "nettoyage", "ocr", "sfx"),
        "terminologie": ("terminologie", "glossariste"),
        "traduction": ("traduction",),
        "rendu": ("rendu",),
    },
    "ln": {
        "terminologie": ("terminologie", "glossariste"),
        "traduction": ("traduction",),
        "mise en page": ("mise en page",),
    },
}


# --------------------------------------------------------------------------- #
#  Lecture d'un run
# --------------------------------------------------------------------------- #

def secondes_par_phase(lignes: list[str]) -> tuple[str, dict[str, float], dict[str, int]]:
    """`(brique, secondes par phase, nombre de lignes par phase)` d'UN run.

    La brique se déduit du CONTENU : une ligne `page N/T` ne peut venir que du manga, une
    ligne `bloc i/n` que du light novel. Se fier au chemin serait plus fragile — plusieurs
    volumes portent les deux briques sous le même projet."""
    secondes: dict[str, float] = {}
    compte: dict[str, int] = {}
    brique = ""
    for ligne in lignes:
        for motif, genre in ((_PERF_PAGE, "manga"), (_PERF_BLOC, "ln"),
                             (_PERF_GLOSSARISTE, "")):
            m = motif.match(ligne)
            if not m:
                continue
            phase = m.groupdict().get("etape") or "glossariste"
            duree = m.groupdict().get("duree")
            secondes[phase] = secondes.get(phase, 0.0) + (float(duree) if duree else 0.0)
            compte[phase] = compte.get(phase, 0) + 1
            brique = brique or genre
            break
    return brique, secondes, compte


def est_neuf(brique: str, secondes: dict[str, float], compte: dict[str, int]) -> bool:
    """Un run NEUF paie toutes ses phases ; un run de reprise en saute.

    La règle, écrite plutôt que devinée :

    · **manga** — la traduction a coûté quelque chose (une planche reprise du cache écrit
      `0.00s`) **et** la détection a autant de lignes que le rendu. Un `--from rendu` ne
      relance ni détection ni traduction : il tombe des deux côtés ;
    · **light novel** — le run porte au moins deux phases distinctes ayant réellement
      consommé du temps. Un run qui ne fait que réassembler n'écrit qu'une seule phase.

    ⚠ C'est un critère de TRI, pas un jugement de qualité. Un run de reprise est un run
    normal — c'est même le plus fréquent, et c'est pour ça qu'il a son propre tableau."""
    if brique == "manga":
        return (secondes.get("traduction", 0.0) > 1.0
                and compte.get("detection", 0) >= max(1, compte.get("rendu", 0)))
    payantes = [p for p, s in secondes.items() if s > 1.0]
    return len(payantes) >= 2


def runs_du_depot(racine: Path | None = None) -> list[dict]:
    """Tous les runs de tous les `perf.log` sous `build/`, à plat.

    ⚠ Un `perf.log` contient PLUSIEURS runs : le fichier s'ouvre en `"a"` et ils s'y
    empilent (c'est ce qui permet de comparer la perf d'avant et d'après un changement de
    code). Les compter comme un seul mélangerait un run neuf et six reprises."""
    racine = Path(racine or RACINE / "build")
    resultats: list[dict] = []
    if not racine.exists():
        return resultats
    for chemin in sorted(racine.glob("*/*/**/perf.log")) + sorted(racine.glob("*/*/perf.log")):
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        for indice, lignes in enumerate(runs_de_perf(texte), 1):
            brique, secondes, compte = secondes_par_phase(lignes)
            total = sum(secondes.values())
            if not brique or total <= 0:
                continue
            resultats.append({
                "volume": nom_de_volume(chemin), "indice": indice, "brique": brique,
                "secondes": secondes, "compte": compte, "total": total,
                "neuf": est_neuf(brique, secondes, compte)})
    # Un même run ne doit apparaître qu'une fois : `glob("*/*/**/perf.log")` et
    # `glob("*/*/perf.log")` se recoupent sur les logs de light novel.
    vus, uniques = set(), []
    for run in resultats:
        cle = (run["volume"], run["indice"], run["brique"], round(run["total"], 3))
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append(run)
    return uniques


# --------------------------------------------------------------------------- #
#  Agrégation
# --------------------------------------------------------------------------- #

def parts(runs: list[dict], phases: tuple[str, ...]) -> dict[str, list[float]]:
    """Part de chaque phase dans le temps instrumenté, run par run.

    ⚠ Une phase **absente** d'un run n'est pas comptée `0`. Un `--from rendu` ne paie pas la
    détection ; la faire entrer à zéro dans la médiane décrirait un run qui n'a jamais eu
    lieu — le même piège que `illustration/progression.resume`, qui refuse de lister une
    phase jamais ouverte."""
    resultat: dict[str, list[float]] = {p: [] for p in phases}
    for run in runs:
        total = run["total"]
        if total <= 0:
            continue
        for phase in phases:
            if phase in run["secondes"]:
                resultat[phase].append(run["secondes"][phase] / total)
    return resultat


def poids_utilisables(parts_par_phase: dict[str, list[float]], *,
                      facteur: float = FACTEUR_ABANDON,
                      minimum: int = MINIMUM_RUNS) -> dict[str, float | None]:
    """Le verdict, phase par phase : un poids, ou `None`.

    `None` signifie « pas de poids utilisable », et c'est une réponse complète. Le modèle de
    `core/progression.py` bascule alors en avancement **compté** — il ne se rabat pas sur des
    poids égaux, qui seraient un faux pourcentage avec l'aplomb d'un vrai."""
    verdict: dict[str, float | None] = {}
    for phase, valeurs in parts_par_phase.items():
        valeurs = [v for v in valeurs if v > 0]
        if len(valeurs) < minimum:
            verdict[phase] = None
            continue
        bas, haut = min(valeurs), max(valeurs)
        verdict[phase] = None if bas <= 0 or haut / bas > facteur else \
            round(statistics.median(valeurs), 4)
    return verdict


def tableau(runs: list[dict], phases: tuple[str, ...], *,
            facteur: float = FACTEUR_ABANDON) -> list[dict]:
    """Une ligne par phase : médiane, `n`, min, max, écart, et verdict."""
    p = parts(runs, phases)
    verdict = poids_utilisables(p, facteur=facteur)
    lignes = []
    for phase in phases:
        valeurs = [v for v in p[phase] if v > 0]
        if not valeurs:
            lignes.append({"phase": phase, "n": 0, "mediane": None, "min": None,
                           "max": None, "ecart": None, "poids": None})
            continue
        bas, haut = min(valeurs), max(valeurs)
        lignes.append({
            "phase": phase, "n": len(valeurs),
            "mediane": statistics.median(valeurs), "min": bas, "max": haut,
            "ecart": (haut / bas) if bas > 0 else None,
            "poids": verdict[phase]})
    return lignes


# --------------------------------------------------------------------------- #
#  Rendu
# --------------------------------------------------------------------------- #

def _pc(x) -> str:
    return "—" if x is None else f"{x * 100:.1f} %"


def rendre_markdown(runs: list[dict], brique: str, phases: tuple[str, ...],
                    neuf: bool) -> list[str]:
    lot = [r for r in runs if r["brique"] == brique and r["neuf"] is neuf]
    titre = "run neuf" if neuf else "run de reprise"
    sortie = [f"\n#### {brique} — {titre} ({len(lot)} run(s))\n"]
    if not lot:
        sortie.append("*Aucun run de cette nature dans `build/` — la case est vide, "
                      "pas nulle.*\n")
        return sortie
    duree = sum(r["total"] for r in lot)
    sortie.append(f"Temps instrumenté cumulé : **{duree / 3600:.1f} h**.\n")
    sortie.append("| phase | part médiane | n runs | min | max | écart | poids retenu |")
    sortie.append("|---|--:|--:|--:|--:|--:|---|")
    for ligne in tableau(lot, phases):
        if not ligne["n"]:
            continue
        ecart = "—" if ligne["ecart"] is None else f"×{ligne['ecart']:.1f}"
        poids = ("**aucun**" if ligne["poids"] is None
                 else f"**{ligne['poids'] * 100:.1f} %**")
        sortie.append(f"| {ligne['phase']} | {_pc(ligne['mediane'])} | {ligne['n']} | "
                      f"{_pc(ligne['min'])} | {_pc(ligne['max'])} | {ecart} | {poids} |")
    return sortie


def agreger(runs: list[dict], regroupement: dict[str, tuple[str, ...]]) -> list[dict]:
    """Le même tableau, mais sur les phases de PROGRESSION (cf. `PHASES_DE_PROGRESSION`).

    Chaque run est réécrit avec les phases regroupées, puis passé au même `tableau()` : une
    seule règle d'abandon, un seul chemin de calcul, aucune divergence possible entre les
    deux granularités."""
    regroupes = []
    for run in runs:
        secondes = {nom: sum(run["secondes"].get(tag, 0.0) for tag in tags)
                    for nom, tags in regroupement.items()}
        # Une phase dont AUCUN tag n'a été payé reste absente, comme dans `parts()`.
        secondes = {nom: s for nom, s in secondes.items() if s > 0}
        regroupes.append({**run, "secondes": secondes})
    return tableau(regroupes, tuple(regroupement))


def rendre_agrege(runs: list[dict], brique: str) -> list[str]:
    lot = [r for r in runs if r["brique"] == brique and r["neuf"]]
    sortie = [f"\n#### {brique} — phases de PROGRESSION, run neuf ({len(lot)} run(s))\n"]
    if not lot:
        sortie.append("*Aucun run neuf de cette brique dans `build/`.*\n")
        return sortie
    sortie.append("| phase | part médiane | n runs | min | max | écart | poids retenu |")
    sortie.append("|---|--:|--:|--:|--:|--:|---|")
    for ligne in agreger(lot, PHASES_DE_PROGRESSION[brique]):
        if not ligne["n"]:
            continue
        ecart = "—" if ligne["ecart"] is None else f"×{ligne['ecart']:.1f}"
        poids = ("**aucun**" if ligne["poids"] is None
                 else f"**{ligne['poids'] * 100:.1f} %**")
        sortie.append(f"| {ligne['phase']} | {_pc(ligne['mediane'])} | {ligne['n']} | "
                      f"{_pc(ligne['min'])} | {_pc(ligne['max'])} | {ecart} | {poids} |")
    return sortie


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--racine", default=None, help="dossier build/ à lire")
    p.add_argument("--markdown", action="store_true")
    p.add_argument("--detail", action="store_true", help="une ligne par run")
    p.add_argument("--anonyme", action="store_true",
                   help="ne nomme pas les œuvres — pour un document publié")
    args = p.parse_args(argv)

    runs = runs_du_depot(args.racine)
    if not runs:
        print("Aucun perf.log exploitable sous build/.")
        return 1

    if args.detail:
        noms = {}
        lignes = ["| run | brique | nature | temps instrumenté (s) | phases payées |",
                  "|---|---|---|--:|---|"]
        for run in runs:
            nom = run["volume"]
            if args.anonyme:
                nom = noms.setdefault(nom, f"volume {len(noms) + 1}")
            payees = ", ".join(f"{k} {v:.0f}s" for k, v in sorted(
                run["secondes"].items(), key=lambda kv: -kv[1]) if v > 0)
            lignes.append(f"| {nom} · run {run['indice']} | {run['brique']} | "
                          f"{'neuf' if run['neuf'] else 'reprise'} | {run['total']:.0f} | "
                          f"{payees} |")
        print("\n".join(lignes))
        return 0

    sortie: list[str] = []
    for brique, phases in (("manga", PHASES_MANGA), ("ln", PHASES_LN)):
        for neuf in (True, False):
            sortie += rendre_markdown(runs, brique, phases, neuf)
        sortie += rendre_agrege(runs, brique)
    texte = "\n".join(sortie)
    print(texte if args.markdown else texte.replace("**", "").replace("|", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
