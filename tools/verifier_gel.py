#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les vérifications de l'ARTEFACT gelé — `PLAN-37` L37.7.

    python tools/verifier_gel.py --diagnostic diagnostic-gel.json
    python tools/verifier_gel.py --demarrage demarrage-gel.json
    python tools/verifier_gel.py --empreintes dist --sortie dist/SHA256SUMS.txt

## Pourquoi un outil, et pas trois lignes de `python -c` dans le YAML

Parce qu'un garde-fou écrit dans un fichier de CI ne se teste pas. Celui-ci a ses propres tests
(`tests/test_empaquetage.py`), il se rejoue en local sur un gel construit à la main, et le
jour où un job passe au vert sans rien vérifier, c'est ici qu'on le voit — pas dans quatre
cents lignes de YAML.

C'est la même raison qui a fait naître `tools/compte_de_tests.py` au lot 20 : *une* assertion
enterrée dans un `run:` est une assertion que personne ne relit.

## Ce que chaque mode vérifie, et ce qu'il ne vérifie PAS

- `--diagnostic` : que le binaire **se sait gelé**, qu'il a **collecté** des verdicts, et que
  les points qu'une machine nue doit signaler y sont. ⚠ Il ne vérifie pas qu'il n'y a rien à
  signaler : sur une machine nue il y a TOUT à signaler, et c'est le résultat attendu. Ce qu'on
  attrape ici, c'est un diagnostic vide — donc des chemins de données non résolus ;
- `--demarrage` : que la fenêtre s'est ouverte **sur l'accueil et sans tome**. C'est le
  critère 2 du `PLAN-31`, revérifié sur le gel parce qu'un module Qt élagué de trop ne se voit
  pas à l'import mais à la création du premier widget ;
- `--empreintes` : la liste SHA-256 des fichiers publiés. Ce n'est pas une signature et ce
  fichier ne dit pas qui a construit le binaire — il dit seulement que ce qu'on a téléchargé
  est ce qui a été construit. Tant qu'aucun certificat ne signe les binaires, c'est la seule
  garantie d'intégrité que ce projet offre, et il vaut mieux l'écrire que la laisser croire.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

#: Les points qu'un diagnostic doit signaler sur une machine SANS rien d'installé. Leur
#: absence est le défaut qu'on cherche : un diagnostic qui ne voit pas que les poids manquent
#: ne voit rien, et il ne le dirait pas non plus chez un utilisateur.
ATTENDUS_MACHINE_NUE: tuple[str, ...] = ("poids_detection", "chemin_sources")

#: Les extensions publiées, et elles seules. Le dossier `dist/` porte aussi le gel entier ;
#: en lister les 356 fichiers dans un `SHA256SUMS.txt` noierait les deux lignes qui comptent.
PUBLIES: tuple[str, ...] = (".exe",)


def verifier_diagnostic(chemin: Path) -> list[str]:
    """Les défauts trouvés dans le relevé de diagnostic. Liste vide = tout va bien."""
    releve = json.loads(chemin.read_text(encoding="utf-8"))
    echecs: list[str] = []
    if releve.get("gele") is not True:
        echecs.append("le binaire ne se sait pas gelé (installation.gele() est faux)")
    resume = releve.get("resume") or {}
    if not resume.get("total"):
        echecs.append(f"aucun verdict collecté — résumé : {resume}")
    vus = {v.get("identifiant") for v in releve.get("verdicts") or []}
    for attendu in ATTENDUS_MACHINE_NUE:
        if attendu not in vus:
            echecs.append(f"« {attendu} » absent du diagnostic du gel — vus : {sorted(vus)}")
    racine = releve.get("racine_livree") or ""
    if not racine:
        echecs.append("le gel ne dit pas où sont ses données livrées")
    return echecs


def verifier_demarrage(chemin: Path) -> list[str]:
    """Les défauts trouvés dans le relevé d'ouverture de fenêtre."""
    texte = chemin.read_text(encoding="utf-8")
    # ⚠ La dernière ligne, pas le fichier entier : une dépendance tierce peut avoir écrit un
    # avertissement avant — c'est arrivé le 2026-09-06 avec `transformers`.
    lignes = [ln for ln in texte.splitlines() if ln.strip().startswith("{")]
    if not lignes:
        return [f"{chemin} ne contient aucun relevé JSON"]
    releve = json.loads(lignes[-1])
    echecs = list(releve.get("echecs") or [])
    if releve.get("ok") is not True and not echecs:
        echecs.append(f"relevé négatif sans motif : {releve}")
    return echecs


def empreintes(dossier: Path) -> list[tuple[str, str]]:
    """`(sha256, nom)` pour chaque fichier publiable du dossier, à plat et trié.

    ⚠ Non récursif, et c'est le point : `dist/` contient le dossier gelé entier. Ce qui est
    PUBLIÉ est l'installeur, et c'est de lui qu'on veut l'empreinte."""
    sortie = []
    for fichier in sorted(dossier.iterdir()):
        if not fichier.is_file() or fichier.suffix.lower() not in PUBLIES:
            continue
        h = hashlib.sha256()
        with fichier.open("rb") as fh:
            for bloc in iter(lambda: fh.read(1 << 20), b""):
                h.update(bloc)
        sortie.append((h.hexdigest(), fichier.name))
    return sortie


def main() -> int:
    # ⚠ **Pas `core.cli.configurer_stdout()`** : cet outil doit tourner sur un Python nu, comme
    # `tools/verifier_livraison.py` — la convention et son motif sont dans
    # `tests/test_outils_sortie.py`. Sans ces quatre lignes, une console Windows en cp1252 fait
    # tomber l'outil sur le premier « ⚠ », c'est-à-dire au moment précis où il a quelque chose
    # à dire.
    for _flux in (sys.stdout, sys.stderr):
        try:
            _flux.reconfigure(encoding="utf-8")
        except Exception:      # noqa: BLE001 — flux remplacé (test, pipe) ou non reconfigurable
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diagnostic", metavar="FICHIER",
                    help="relevé de `angelith-console.exe --diagnostic-json`")
    ap.add_argument("--demarrage", metavar="FICHIER",
                    help="relevé de `angelith-console.exe --verifier-demarrage`")
    ap.add_argument("--empreintes", metavar="DOSSIER",
                    help="calcule les SHA-256 des fichiers publiables du dossier")
    ap.add_argument("--sortie", metavar="FICHIER", default=None,
                    help="où écrire la liste d'empreintes (défaut : la sortie standard)")
    args = ap.parse_args()

    if not (args.diagnostic or args.demarrage or args.empreintes):
        ap.error("rien à vérifier — donne --diagnostic, --demarrage ou --empreintes")

    echecs: list[str] = []
    if args.diagnostic:
        echecs += verifier_diagnostic(Path(args.diagnostic))
    if args.demarrage:
        echecs += verifier_demarrage(Path(args.demarrage))

    if args.empreintes:
        lignes = [f"{sha}  {nom}" for sha, nom in empreintes(Path(args.empreintes))]
        if not lignes:
            echecs.append(f"aucun fichier publiable dans {args.empreintes}")
        texte = "\n".join(lignes) + "\n" if lignes else ""
        if args.sortie:
            Path(args.sortie).write_text(texte, encoding="utf-8")
        print(texte, end="")

    for echec in echecs:
        # ⚠ Le préfixe `::error::` est ce que GitHub Actions annote dans le résumé du run. Sans
        # lui, le motif se perd au milieu des logs, à l'instant précis où il sert.
        print(f"::error::{echec}", file=sys.stderr)
    if echecs:
        print(f"{len(echecs)} défaut(s) sur le gel.", file=sys.stderr)
        return 1
    if args.diagnostic or args.demarrage:
        print("Le gel passe les vérifications demandées.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
