# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le tableau du corpus — **et c'est la spécification de la vue** (`PLAN-34` étape 0.1).

    python tools/inventaire_oeuvres.py                  # le tableau, en console
    python tools/inventaire_oeuvres.py --markdown        # le même, pour docs/mesures/
    python tools/inventaire_oeuvres.py --cout            # le chronomètre et les appels système

## Pourquoi ce script existe avant la vue, et pas après

Parce que le plan le demande dans cet ordre, et la raison est bonne : le tableau **est** le
modèle de données. Écrire la vue d'abord aurait produit des colonnes qu'on sait afficher
plutôt que des colonnes qu'on sait remplir.

## Ce qu'il ne fait pas, et ce que ça garantit

⚠ **Aucune image n'est ouverte** et **aucun modèle n'est chargé** : tout passe par
`bibliotheque.py`, dont c'est l'invariant testé. `--cout` le montre plutôt que de
l'affirmer, en comptant les appels système du balayage complet.

⚠ **Aucun titre d'œuvre du corpus n'est écrit dans `docs/`** par la sortie `--markdown` telle
quelle : ce sont des œuvres sous droit d'auteur, et un tableau qui les nomme reste une donnée
de travail. `--anonyme` remplace chaque nom par « Œuvre N » pour ce qui doit être publié — le
document de mesure du lot s'en sert, et les chiffres, eux, ne changent pas d'un iota.

## Le compteur d'appels système, et ce qu'il ne dit pas

⚠ Il compte `os.stat`, `os.scandir` et `os.listdir` — c'est-à-dire ce que le module DEMANDE.
Sous Windows, `os.scandir` renvoie déjà les métadonnées de chaque entrée : un
`DirEntry.stat()` qui suit ne touche pas le disque et n'apparaît donc pas dans ce compte.
Le chiffre est un plancher, pas un total d'entrées-sorties, et il se lit à côté du
chronomètre — jamais à sa place.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bibliotheque as biblio  # noqa: E402
from core import cli  # noqa: E402


class Compteur:
    """Remplace `os.stat` / `os.scandir` / `os.listdir` le temps d'un balayage, et compte.

    Un décorateur plutôt qu'un profileur : ce qu'on veut savoir n'est pas où le temps passe
    mais **combien de fois on interroge le système de fichiers**, parce que c'est ce chiffre
    qui décide si la vue tiendra sur un dossier synchronisé (OneDrive), où chaque appel coûte
    cent fois ce qu'il coûte en local."""

    def __init__(self):
        self.appels: dict[str, int] = {"stat": 0, "scandir": 0, "listdir": 0}
        self._anciens: dict[str, object] = {}

    def __enter__(self):
        for nom in self.appels:
            ancien = getattr(os, nom)
            self._anciens[nom] = ancien
            setattr(os, nom, self._enrober(nom, ancien))
        return self

    def __exit__(self, *_exc):
        for nom, ancien in self._anciens.items():
            setattr(os, nom, ancien)
        return False

    def _enrober(self, nom, fonction):
        def _appel(*args, **kwargs):
            self.appels[nom] += 1
            return fonction(*args, **kwargs)
        return _appel

    @property
    def total(self) -> int:
        return sum(self.appels.values())


def _horodatage(valeur: float | None) -> str:
    if not valeur:
        return "—"
    return time.strftime("%Y-%m-%d", time.localtime(valeur))


def _resume_etapes(info) -> str:
    """« ●●●●●●● » — une pastille par étape, dans l'ordre d'exécution, avec sa légende
    ailleurs. Jamais la couleur seule : ce sont des CARACTÈRES, lisibles par un lecteur
    d'écran comme par un terminal sans couleur."""
    symboles = {etat: symbole for etat, symbole, _ in biblio.LEGENDE_ETATS}
    return "".join(symboles.get(info.etapes.get(e, biblio.ABSENTE), "?")
                   for e in biblio.etapes_de_brique(info.brique))


def _sorties(info) -> str:
    return ", ".join(sorted(info.sorties)) or "—"


COLONNES = ("Œuvre", "Tome", "Brique", "Format", "Langue", "Unités", "Étapes",
            "Sorties", "Glossaire", "Dernier run")


def lignes(oeuvres, *, anonyme: bool = False) -> list[tuple[str, ...]]:
    sortie: list[tuple[str, ...]] = []
    for rang, oeuvre in enumerate(oeuvres, 1):
        nom = f"Œuvre {rang}" if anonyme else oeuvre.projet
        for numero, info in enumerate(oeuvre.tomes, 1):
            sortie.append((
                nom,
                f"Tome {numero}" if anonyme else info.tome,
                info.libelle_brique,
                info.format or "—",
                info.langue_source or "—",
                info.compte,
                _resume_etapes(info),
                _sorties(info),
                "—" if oeuvre.glossaire is None else str(oeuvre.glossaire),
                _horodatage(info.dernier_run),
            ))
    return sortie


def _tableau_markdown(lignes_: list[tuple[str, ...]]) -> str:
    entete = "| " + " | ".join(COLONNES) + " |"
    separateur = "|" + "|".join("---" for _ in COLONNES) + "|"
    corps = ["| " + " | ".join(c.replace("|", "\\|") for c in ligne) + " |"
             for ligne in lignes_]
    return "\n".join([entete, separateur, *corps])


def _tableau_console(lignes_: list[tuple[str, ...]]) -> str:
    largeurs = [max(len(str(x)) for x in (col, *(l[i] for l in lignes_)))
                for i, col in enumerate(COLONNES)]
    def _ligne(valeurs):
        return "  ".join(str(v).ljust(w) for v, w in zip(valeurs, largeurs)).rstrip()
    return "\n".join([_ligne(COLONNES), _ligne("-" * w for w in largeurs),
                      *(_ligne(l) for l in lignes_)])


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Inventaire des œuvres de sources/ — le tableau du PLAN-34 étape 0.1.")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--markdown", action="store_true",
                    help="tableau Markdown, pour docs/mesures/")
    ap.add_argument("--anonyme", action="store_true",
                    help="remplace les titres du corpus par « Œuvre N » — les œuvres sont "
                         "sous droit d'auteur, et un tableau publié n'a pas à les nommer")
    ap.add_argument("--cout", action="store_true",
                    help="chronomètre le balayage complet et compte les appels système")
    args = ap.parse_args()

    # ⚠ Avant la première ligne imprimée : les titres du corpus portent des caractères
    # japonais, et une console Windows en cp1252 lèverait sur le premier d'entre eux.
    cli.configurer_stdout()
    config = cli.charger_config(args.config)

    debut = time.perf_counter()
    with Compteur() as compteur:
        oeuvres = biblio.Inventaire(config).oeuvres()
    duree = time.perf_counter() - debut

    lignes_ = lignes(oeuvres, anonyme=args.anonyme)
    print(_tableau_markdown(lignes_) if args.markdown else _tableau_console(lignes_))

    tomes = sum(len(o.tomes) for o in oeuvres)
    unites = sum(t.unites or 0 for o in oeuvres for t in o.tomes)
    print(f"\n{len(oeuvres)} œuvre(s), {tomes} tome(s), {unites} unité(s) source "
          f"dénombrée(s) — les tomes indénombrables (« ? ») ne sont pas comptés.")

    if args.cout:
        print(f"\nBalayage complet : {duree * 1000:.0f} ms")
        for nom, n in sorted(compteur.appels.items()):
            print(f"  os.{nom:8s} {n:6d}")
        print(f"  {'total':13s}{compteur.total:6d}")
        print("\n⚠ Ce compte est un PLANCHER : sous Windows, `os.scandir` rend déjà les "
              "métadonnées\n  de chaque entrée, si bien qu'un `DirEntry.stat()` qui suit ne "
              "touche pas le disque\n  et n'apparaît pas ici.")


if __name__ == "__main__":
    main()
