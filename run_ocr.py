#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Brique SCAN — lire un light novel japonais livré en images de pages.

Produit un `.md` DANS le dossier de langue, que `run.py` lit ensuite sans rien changer :

  python run_ocr.py "manga C" Vol.1
  python run.py     "manga C" Vol.1

Régler l'analyse sur UNE page avant de payer deux heures d'OCR :
  python run_ocr.py "Mon LN" Vol.1 --page 100 --apercu     # image de contrôle, sans OCR
  python run_ocr.py "Mon LN" Vol.1 --page 100 --verbose    # la page, texte compris

Reprendre, refaire, arrêter :
  python run_ocr.py "Mon LN" Vol.1                 # reprend où le dernier run s'est arrêté
  python run_ocr.py "Mon LN" Vol.1 --from lecture  # étapes : analyse, lecture
  python run_ocr.py "Mon LN" Vol.1 --force         # refait tout
  python run_ocr.py "Mon LN" Vol.1 --stop          # dans un AUTRE terminal : arrêt propre

Toute une série, une nuit durant :
  python run_ocr.py "Mon LN" --all --keep-awake --shutdown

Lister, diagnostiquer :
  python run_ocr.py --list
  python run_ocr.py "Mon LN" --list
  python run_ocr.py --check

⚠ Le coût est réel : ~0,5 s par tranche d'OCR, ~30 s par page, ~2 h pour un tome de 270
pages sur processeur. Le cache est par PAGE : un tome interrompu reprend sans rien relire.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import cli, control
from core.reporter import Reporter, RichReporter
from core.version import ETAT_BRIQUES, __version__
from scan import pages as scan_pages
from scan.orchestrator_scan import build_dir_de, process_volume

cli.configurer_stdout()

ETAPES = ["analyse", "lecture"]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="OCR d'un light novel japonais livré en images (brique SCAN).")
    ap.add_argument("projet", nargs="?", help="dossier projet sous sources/")
    ap.add_argument("tome", nargs="?", help="dossier de tome (ex. Vol.1)")
    ap.add_argument("--version", action="version",
                    version=f"Angelith {__version__} (brique scan : {ETAT_BRIQUES['scan']})")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--all", action="store_true", help="enchaîne tous les tomes du projet")
    ap.add_argument("--page", type=int, metavar="N", default=None,
                    help="ne traiter que la page N (index 0 = première image)")
    ap.add_argument("--from", dest="depuis", metavar="ÉTAPE", choices=ETAPES, default=None,
                    help=f"refait à partir de cette étape ({', '.join(ETAPES)})")
    ap.add_argument("--force", action="store_true", help="refait tout, cache ignoré")
    ap.add_argument("--langue", metavar="DOSSIER", default=None,
                    help="force le dossier de langue à lire (ex. JAP)")
    ap.add_argument("--apercu", nargs="?", const="apercu.png", metavar="FICHIER",
                    help="écrit une image de contrôle de l'analyse (avec --page) et s'arrête")
    ap.add_argument("--seuil", type=int, metavar="N", default=None,
                    help="force le seuil de binarisation (sinon choisi par balayage)")
    ap.add_argument("--verbose", action="store_true", help="lignes de perf (aussi dans perf.log)")
    ap.add_argument("--stop", action="store_true",
                    help="demande l'arrêt propre du run en cours sur ce tome")
    ap.add_argument("--list", action="store_true", help="liste les projets / tomes")
    ap.add_argument("--check", action="store_true", help="diagnostic de l'environnement")
    cli.ajouter_flags_veille(ap)
    args = ap.parse_args()

    config = cli.charger_config(args.config)
    chemins = config["chemins"]

    if args.check:
        cli.avertir_config(config)
        cli.bloc_langue(config)
        sys.exit(0 if _diagnostic(config) else 1)

    if args.list or not args.projet:
        # ⚠ Pas de 6e positionnel : `afficher_liste` porte un `*`, donc `sous_dossier` et
        # `etat` sont keyword-only. Ce `None` de trop levait un `TypeError` — `run_ocr.py
        # --list` était cassé, et rien ne le disait parce qu'aucun test n'appelait ce chemin.
        cli.afficher_liste(scan_pages.lister_projets, scan_pages.lister_tomes,
                           Path(chemins["sources"]), Path(chemins["build"]),
                           args.projet)
        return

    if args.stop:
        if not args.tome:
            sys.exit("--stop demande un tome : run_ocr.py \"Projet\" Vol.1 --stop")
        fichier = control.request_stop(build_dir_de(config, args.projet, args.tome))
        print(f"Arrêt demandé ({fichier}) — le run finira la page en cours.")
        return

    if args.apercu:
        if args.page is None:
            sys.exit("--apercu demande --page N (l'aperçu porte sur une page).")
        from scan.apercu import ecrire_apercu
        chemin = ecrire_apercu(config, args.projet, args.tome, args.page,
                               sortie=args.apercu, seuil=args.seuil, langue=args.langue)
        print(f"Aperçu écrit : {chemin}")
        return

    tomes = ([t for t in scan_pages.lister_tomes(Path(chemins["sources"]), args.projet)]
             if args.all else [args.tome])
    if not tomes or tomes == [None]:
        sys.exit("Précise un tome, ou utilise --all.")

    inhibiteur = cli.preparer_veille(args.keep_awake or args.shutdown,
                                     "OCR de scans en cours")
    interrompu = False
    try:
        for tome in tomes:
            reporter = _reporter(args, config, args.projet, tome)
            recap = process_volume(args.projet, tome, config, reporter=reporter,
                                   page=args.page, force=args.force, depuis=args.depuis,
                                   langue=args.langue)
            v = recap["par_verdict"]
            print(f"\n{args.projet} / {tome} : {v.get('texte', 0)} page(s) de texte, "
                  f"{v.get('titre', 0)} de titre, {v.get('illustration', 0)} d'illustration · "
                  f"{recap['caracteres']} caractères · {recap['suspectes']} colonne(s) suspecte(s)")
            print(f"Rapport : {build_dir_de(config, args.projet, tome) / 'RAPPORT.md'}")
    except KeyboardInterrupt:
        interrompu = True
        print("\nInterrompu.")
    finally:
        cli.finalize_power(args, inhibiteur, interrupted=interrompu)


def _reporter(args, config: dict, projet: str, tome: str) -> Reporter:
    reporter = RichReporter() if sys.stdout.isatty() else Reporter()
    return cli.make_reporter(reporter, build_dir_de(config, projet, tome),
                             verbose=args.verbose, dry_run=False)


def _diagnostic(config: dict) -> bool:
    print(f"Angelith {__version__} (brique scan : {ETAT_BRIQUES['scan']}) — diagnostic\n")
    ok = cli.section_dependances(
        [("numpy", "numpy"), ("PIL", "pillow"), ("manga_ocr", "manga-ocr"),
         ("torch", "torch")],
        "pip install -r requirements-scan.txt")
    from manga.ocr import MODELE_OCR, dossier_cache
    local = dossier_cache()
    print(f"\nModèle d'OCR ({MODELE_OCR}) : "
          + (f"en cache — {local}" if local else
             "ABSENT du cache — il sera téléchargé au premier run (~424 Mo)"))
    sources = Path(config["chemins"]["sources"])
    print(f"Sources : {sources} "
          + ("(présent)" if sources.is_dir() else "INTROUVABLE"))
    return cli.conclure(ok)


if __name__ == "__main__":
    main()
