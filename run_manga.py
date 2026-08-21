#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Pipeline de traduction de MANGA — CLI dédiée, indépendante de run.py (LN).

Traduire un Tome (dossier d'images OU archive .cbz/.cbr sous
sources/<Projet>/<Tome>/manga/) :
  python run_manga.py "Mon Manga" Vol.1
  python run_manga.py "Mon Manga" Vol.1 --dry-run   # tuyauterie : détection/OCR réels,
                                                     # SANS appel au LLM de traduction
  python run_manga.py "Mon Manga" Vol.1 --force     # refait les pages déjà générées
  python run_manga.py "Mon Manga" Vol.1 --verbose   # + temps/tokens/vitesse par étage (perf.log)

Traiter TOUTE une œuvre en une commande (run de nuit) — un chapitre = un <Tome> :
  python run_manga.py "Mon Manga" --all                    # tous les chapitres restants
  python run_manga.py "Mon Manga" --all --keep-awake --shutdown
  python run_manga.py "Mon Manga" --list                   # état RÉEL de chaque chapitre
Un chapitre complet ET à jour n'est même pas ouvert ; un chapitre qui échoue n'interrompt
pas les suivants ; le bilan du matin est dans build/<Œuvre>/RAPPORT-SERIE.md.

Arrêter proprement / reprendre :
  python run_manga.py "Mon Manga" Vol.1 --stop   # dans un AUTRE terminal
  python run_manga.py "Mon Manga" --all --stop   # …ou toute la série
  python run_manga.py "Mon Manga" Vol.1          # relancer reprend page par page
  (Ctrl+C fait pareil.)

Chaque page est mise en cache À CHAQUE ÉTAPE (détection, nettoyage, OCR, terminologie,
traduction, rendu) sous build/<Projet>/<Tome>/manga/ — une page déjà terminée peut être RELANCÉE
À UNE SEULE ÉTAPE, sans refaire les précédentes. Les pages « clean » (bulles vidées,
SANS texte) sont dans pages_clean/ — consultables directement, et le point de départ
naturel de --from rendu :
  python run_manga.py "Mon Manga" Vol.1 --from traduction  # regloss./retraduit + relettre
                                                            # (garde détection/nettoyage/OCR)
  python run_manga.py "Mon Manga" Vol.1 --from rendu        # relettre SEULEMENT, depuis
                                                            # les pages clean + traductions
                                                            # déjà en cache (ex. après un
                                                            # changement de police)
  python run_manga.py "Mon Manga" Vol.1 --page 3             # ne (re)traite QUE la page 3
  python run_manga.py "Mon Manga" Vol.1 --page 3 --from ocr  # ne refait que l'OCR→rendu de la page 3

Cohérence des noms propres (glossaire de l'œuvre, PARTAGÉ avec le light novel) :
  python run_manga.py "Mon Manga" Vol.1 --from rendu       # applique le glossaire aux bulles
                                                            # (forçage `force: true`, 0 appel LLM)
  python tools/compter_variantes.py "Mon Manga" Vol.1        # combien de formes bannies subsistent

Peupler le glossaire SANS traduire ni relettrer une seule planche (le pendant manga de
`run.py --extract-glossary` / `--optimize-glossary`) :
  python run_manga.py "Mon Manga" Vol.1 --extract-glossary  # relève les noms d'un chapitre
  python run_manga.py "Mon Manga" --all --extract-glossary  # …de toute l'œuvre (run de nuit)
  python run_manga.py "Mon Manga" --optimize-glossary       # dédoublonne le glossaire de l'œuvre
  python run_manga.py "Mon Manga" Vol.1 --from rendu        # …puis applique tout ça aux bulles

Diagnostic de l'environnement (config, modèle de détection, Ollama) :
  python run_manga.py --check

Lister les projets/tomes disponibles :
  python run_manga.py --list
  python run_manga.py "Mon Manga" --list
"""
import argparse
import sys

from core import cli

cli.configurer_stdout()

from core import config as core_config
from core.reporter import Reporter
from core.version import ETAT_BRIQUES, __version__

# Étapes de `manga.checkpoints.STAGES`, recopiées ICI et non importées : `manga.checkpoints`
# tire numpy et Pillow, ce qui ferait passer `--version`/`--list`/`--help` de 0,19 s à 0,46 s
# (mesuré) pour trois commandes censées être instantanées. `tests/test_manga_terminology.py`
# vérifie que les deux listes ne divergent pas.
ETAPES = ["detection", "nettoyage", "ocr", "terminologie", "traduction", "sfx", "rendu"]

# Recopié de `manga.orchestrator_manga.MAX_PLANCHES_LOT` pour la même raison qu'`ETAPES` :
# valider `--lot` ne doit pas coûter l'import de numpy, Pillow et de tout l'orchestrateur.
# `tests/test_manga_lot.py` vérifie que les deux valeurs ne divergent pas.
MAX_PLANCHES_LOT = 20


def main() -> None:
    ap = argparse.ArgumentParser(description="Traduction de manga (local, indépendant du pipeline LN).")
    ap.add_argument("projet", nargs="?", help="dossier projet sous sources/ (ex. \"Mon Manga\")")
    ap.add_argument("tome", nargs="?", help="dossier de tome (ex. Vol.1)")
    # La version du dépôt est UNIQUE (core/version.py), mais on rappelle ici l'état de la
    # brique : le rendu manga est en cours de remise à niveau, l'utilisateur doit le savoir
    # avant de lancer un tome de 150 planches.
    ap.add_argument("--version", action="version",
                    version=f"Angelith {__version__} (brique manga : {ETAT_BRIQUES['manga']})",
                    help="affiche la version du dépôt et quitte")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--all", action="store_true",
                    help="traite TOUS les chapitres/tomes de l'œuvre à la suite (run de "
                         "nuit) — un chapitre déjà complet ET à jour n'est même pas ouvert, "
                         "un chapitre en échec n'interrompt pas les suivants, et un bilan "
                         "est écrit dans build/<œuvre>/RAPPORT-SERIE.md. L'anti-veille, le "
                         "préchargement du modèle et l'extinction (--keep-awake/--shutdown) "
                         "s'appliquent à TOUTE la série, pas chapitre par chapitre ; ne "
                         "précise pas de tome. Combiné à --stop, demande l'arrêt de la série "
                         "entière")
    ap.add_argument("--force", action="store_true", help="refait TOUTES les étapes des pages déjà générées")
    ap.add_argument("--from", dest="from_stage", metavar="ÉTAPE",
                    choices=ETAPES,
                    help="relance à partir de cette étape en réutilisant le cache des étapes "
                         "précédentes (detection, nettoyage, ocr, terminologie, traduction, sfx, "
                         "rendu). Ex. : --from rendu après un changement de police ou après "
                         "avoir corrigé une orthographe du glossaire (repart des pages clean + "
                         "traductions en cache, SANS aucun appel LLM). ⚠ Pour seulement "
                         "(re)passer le terminologue sur un tome déjà traduit, préfère "
                         "--extract-glossary : --from terminologie retraduit et relettre tout "
                         "ce qui suit")
    ap.add_argument("--page", type=int, metavar="N", default=None,
                    help="ne (re)traite QUE la page N (1-indexée) — les autres pages sont "
                         "réutilisées depuis leur cache existant ; combine avec --from pour ne "
                         "relancer qu'une étape de cette page")
    ap.add_argument("--conf", type=float, metavar="S", default=None,
                    help="relance la détection de la page --page à ce seuil de confiance "
                         "(exige --page, implique --from detection). L'écriture n'a lieu que "
                         "si elle améliore vraiment la détection : plus de bulles n'est pas "
                         "mieux. Prévisualiser d'abord avec tools/apercu_detection.py "
                         "--balayage, qui ne coûte qu'une inférence")
    ap.add_argument("--iou", type=float, metavar="S", default=None,
                    help="seuil de NMS pour cette même relance (mêmes contraintes que --conf)")
    ap.add_argument("--lot", type=int, metavar="N", default=None,
                    help="traduit N planches consécutives par appel (défaut : config.yaml > "
                         "manga.lot.planches, soit 1). Sur un tome de 131 planches, --lot 20 "
                         "fait 7 appels au lieu de 131. Le repli reste par planche : un lot "
                         "mal numéroté est repris une planche à la fois. ⚠ l'unité d'arrêt "
                         "propre et l'unité de perte passent de 1 à N — garder 1 pour itérer "
                         "sur un prompt")
    ap.add_argument("--think", nargs="?", const=True, default=None,
                    choices=["low", "medium", "high"], metavar="NIVEAU",
                    help="active le raisonnement du traducteur manga pour ce run (sans "
                         "valeur = « medium »). Coûteux à une planche par appel ; c'est --lot "
                         "qui le rend abordable, la trace étant payée une fois par lot")
    ap.add_argument("--dry-run", action="store_true",
                    help="sans appel au LLM de traduction (détection/OCR restent réels — "
                         "nécessite requirements-manga.txt installé et le modèle de "
                         "détection téléchargé, cf. manga_models/README.md)")
    ap.add_argument("--verbose", action="store_true",
                    help="affiche après chaque étape de chaque page le temps écoulé (détection, "
                         "nettoyage, ocr, rendu) et, pour la traduction, les tokens générés et la "
                         "vitesse (tok/s) — comme --verbose côté LN. Les lignes sont aussi écrites "
                         "dans build/<projet>/<tome>/manga/perf.log (suivable dans un 2e terminal : "
                         "Get-Content -Wait …\\perf.log)")
    ap.add_argument("--assembler", action="store_true",
                    help="n'exécute QUE l'assemblage des sorties (CBZ/PDF) depuis les pages "
                         "déjà présentes dans pages_out/, sans rien retraduire ni relettrer "
                         "— utile après un arrêt, ou pour changer de format sans relancer "
                         "le tome")
    ap.add_argument("--extract-glossary", action="store_true",
                    help="relève les noms propres de l'œuvre dans "
                         "sources/<projet>/glossaire.yaml, puis quitte — SANS traduire ni "
                         "relettrer une seule planche. Un chapitre sans OCR est détecté et "
                         "OCRisé à la volée ; un chapitre déjà traité ne repaie rien. Exige "
                         "un tome, ou --all pour toute l'œuvre")
    ap.add_argument("--optimize-glossary", action="store_true",
                    help="lance l'agent glossariste : dédoublonne/fusionne/reclasse le "
                         "glossaire de l'ŒUVRE (sauvegarde .bak.yaml), puis quitte — ne "
                         "précise pas de tome")
    ap.add_argument("--stop", action="store_true",
                    help="demande l'arrêt propre du run en cours sur ce Tome")
    ap.add_argument("--list", action="store_true",
                    help="liste les projets disponibles (ou les tomes d'UN projet), sans rien traiter")
    ap.add_argument("--psd-test", nargs="?", const="psd_test.psd", metavar="FICHIER",
                    help="écrit un PSD MINIMAL (un fond, un seul calque de texte « Test ») "
                         "et s'arrête. À ouvrir dans Photoshop pour vérifier en dix secondes "
                         "que les calques de type passent, sans relancer un tome entier.")
    ap.add_argument("--check", action="store_true",
                    help="diagnostic de l'environnement manga (config, dépendances, modèle "
                         "de détection, Ollama) puis quitte")
    # Absents jusqu'au lot 2.6, et d'autant plus utiles ici : un tome de 150 planches avec
    # raisonnement activé dépasse les deux heures, donc se lance la nuit.
    cli.ajouter_flags_veille(ap)
    args = ap.parse_args()

    config = cli.charger_config(args.config)

    if "manga" not in config:
        ap.error(f"Aucune section « manga: » dans {args.config} — voir config.yaml.example "
                 f"ou la documentation pour l'ajouter.")

    if args.list:
        from pathlib import Path
        from pipeline.sources import list_projects
        from manga import serie
        chemins = _chemins(config)
        src, build_root = Path(chemins["sources"]), Path(chemins["build"])

        def _etat(projet: str, tome: str):
            """Verdict par chapitre, et non « le dossier de build existe ». C'est cette
            colonne qu'on lit avant de lancer une nuit : elle distingue un chapitre fini
            d'un chapitre arrêté à la planche 3."""
            e = serie.etat_chapitre(src, build_root, projet, tome)
            return serie.PUCES.get(e.statut, " "), e.detail

        # `serie.lister_chapitres` et non `list_volumes` : l'ordre de lecture, pas l'ordre
        # alphabétique — sans quoi Chap.10 s'affiche avant Chap.2.
        cli.afficher_liste(list_projects, serie.lister_chapitres, src, build_root,
                           args.projet, sous_dossier="manga", etat=_etat)
        sys.exit(0)

    if args.psd_test:
        sys.exit(0 if _run_psd_test(config, args.psd_test) else 1)

    if args.check:
        cli.avertir_config(config)
        sys.exit(0 if _run_doctor(config) else 1)

    if args.stop:
        from core.control import request_stop
        # `--all --stop` : le fichier STOP est PAR TOME, donc un `--stop` nominatif ne peut
        # arrêter qu'un chapitre — inutile contre une série lancée depuis un autre terminal,
        # qui en enchaîne quinze. On le pose donc dans chaque chapitre déjà ouvert : celui qui
        # tourne le verra à sa prochaine planche, les autres le trouveront à leur ouverture.
        if args.all:
            if not args.projet:
                ap.error("précise l'œuvre : python run_manga.py \"Mon Manga\" --all --stop")
            from pathlib import Path
            from manga import serie
            chemins = _chemins(config)
            build_root = Path(chemins["build"])
            poses = []
            for tome in serie.lister_chapitres(Path(chemins["sources"]), args.projet):
                build_dir = serie.build_dir_de(build_root, args.projet, tome)
                if build_dir.is_dir():
                    request_stop(build_dir)
                    poses.append(tome)
            if not poses:
                print(f"Aucun chapitre de « {args.projet} » n'a de dossier de build : "
                      f"rien à arrêter.")
                sys.exit(0)
            print(f"Arrêt demandé pour la série « {args.projet} » — {len(poses)} chapitre(s) "
                  f"notifié(s) : {', '.join(poses)}.")
            print(f"Le chapitre en cours finit sa planche, sauvegarde, assemble son archive, "
                  f"puis s'arrête.")
            print(f"Relance « python run_manga.py \"{args.projet}\" --all » plus tard pour "
                  f"reprendre où tu t'es arrêté.")
            sys.exit(0)
        if not (args.projet and args.tome):
            ap.error("précise le projet ET le tome : python run_manga.py \"Mon Manga\" Vol.1 --stop")
        from pathlib import Path
        build_dir = _build_dir(config, args.projet, args.tome)
        request_stop(build_dir)
        print(f"Arrêt demandé pour {args.projet} / {args.tome}.")
        print(f"Relance « python run_manga.py \"{args.projet}\" {args.tome} » plus tard pour reprendre.")
        sys.exit(0)

    # Glossaire de l'ŒUVRE — deux commandes qui ne touchent QUE
    # sources/<Projet>/glossaire.yaml (ni page nettoyée, ni page finale, ni RAPPORT.md, ni
    # archive). Dispatchées AVANT `--all` : sans cela, `--all --extract-glossary` partirait
    # dans `_run_all_chapitres`, c'est-à-dire retraduirait l'œuvre entière — l'exact contraire
    # de ce que la commande promet.
    if args.optimize_glossary:
        if not args.projet:
            ap.error("précise l'œuvre : python run_manga.py \"Mon Manga\" --optimize-glossary")
        if args.tome or args.all:
            ap.error("--optimize-glossary porte sur l'ŒUVRE (un seul glossaire par projet) : "
                     "ne précise ni tome ni --all.")
        _appliquer_options_lot(ap, args, config)
        sys.exit(_run_glossaire(args, config, extraction=False))

    if args.extract_glossary:
        if not args.projet:
            ap.error("précise l'œuvre : python run_manga.py \"Mon Manga\" Vol.1 "
                     "--extract-glossary")
        if not (args.tome or args.all):
            ap.error("précise le tome, ou --all pour toute l'œuvre : "
                     "python run_manga.py \"Mon Manga\" Vol.1 --extract-glossary")
        if args.tome and args.all:
            ap.error("--all traite tous les chapitres de l'œuvre : ne précise pas de tome "
                     "avec --all")
        if args.all and args.page is not None:
            ap.error("--page vise UNE planche d'UN chapitre : incompatible avec --all")
        if args.assembler:
            ap.error("--extract-glossary ne rend aucune planche : il n'y a rien à assembler.")
        if args.conf is not None or args.iou is not None:
            ap.error("--conf / --iou règlent la détection d'UNE planche et impliquent un "
                     "rendu : incompatibles avec --extract-glossary.")
        _appliquer_options_lot(ap, args, config)
        sys.exit(_run_glossaire(args, config, extraction=True))

    # Série entière (run de nuit) — dispatché AVANT l'exigence « projet ET tome », qui n'a
    # pas de sens ici : c'est justement l'œuvre qu'on nomme, et pas un de ses chapitres.
    if args.all:
        if not args.projet:
            ap.error("précise l'œuvre : python run_manga.py \"Mon Manga\" --all")
        if args.tome:
            ap.error("--all traite tous les chapitres de l'œuvre : ne précise pas de tome "
                     "avec --all")
        if args.page is not None:
            ap.error("--page vise UNE planche d'UN chapitre : incompatible avec --all")
        _appliquer_options_lot(ap, args, config)
        sys.exit(_run_all_chapitres(args, config))

    if not (args.projet and args.tome):
        ap.error("projet ET tome requis (ou --list / --check / --all).")

    if args.assembler:
        from pathlib import Path

        from core.reporter import Reporter

        from manga.orchestrator_manga import assemble_outputs
        build_dir = _build_dir(config, args.projet, args.tome)
        if not build_dir.exists():
            ap.error(f"Rien à assembler : {build_dir} n'existe pas.")
        rep = Reporter()
        sorties = assemble_outputs(build_dir, config["manga"], args.projet, args.tome,
                                    reporter=rep)
        rep.finish(sorties) if sorties else None
        sys.exit(0)
    _appliquer_options_lot(ap, args, config)

    from core.control import StopRequested
    from manga.orchestrator_manga import process_volume

    dry = bool(config.get("options", {}).get("dry_run"))
    inhibitor = cli.preparer_veille(args.keep_awake or args.shutdown,
                                    "Veille du PC désactivée pour la durée du run.")
    # Le manga n'a qu'un modèle de traduction, mais la même règle s'applique : le précharger
    # évite que la première planche paie la latence de chargement, et échoue tôt et
    # clairement si le modèle n'existe pas. Le déchargement final libère la VRAM — d'autant
    # plus utile ici que la détection ONNX peut vouloir le même GPU.
    #
    # ⚠ SAUF si la traduction ne peut pas tourner. `--from rendu` ne relettre que depuis les
    # traductions déjà en cache : précharger y ferait monter un modèle de 27 B en VRAM pour
    # rien — et le DÉCHARGEMENT en fin de run évincerait un modèle que l'utilisateur avait
    # peut-être chargé pour autre chose. C'est exactement la commande de vérification du lot 1,
    # et c'est le même raisonnement que le chargement PARESSEUX du détecteur ONNX et de l'OCR.
    # Liste vide = ni préchargement ni déchargement, la garde vaut donc pour les deux.
    from manga.checkpoints import downstream      # import local : cf. ETAPES ci-dessus
    traduira = args.from_stage is None or "traduction" in downstream(args.from_stage)
    llm_manga = core_config.section(config, "manga", "llm")
    models_used = cli.models_in_config(config, "manga") if traduira else []
    cli.precharger_modeles(config, models_used, dry_run=dry,
                           base_url=llm_manga.get("base_url"))

    # Même `finally` unique que côté light novel : déchargement blindé contre un Ctrl+C
    # tardif, puis finalisation veille/extinction — exactement une fois, quelle que soit la
    # sortie. Sur Ctrl+C, `interrupted=True` : pas d'extinction.
    interrupted = False
    try:
        completed = process_volume(args.projet, args.tome, config, reporter=_make_reporter(args, config),
                                    force=args.force, restart_from=args.from_stage,
                                    only_page=args.page, conf_threshold=args.conf,
                                    iou_threshold=args.iou)
        if not completed:
            interrupted = True
    except (StopRequested, KeyboardInterrupt):
        interrupted = True
        print("\nInterrompu. Relance la même commande pour reprendre.")
    except Exception as e:
        print(f"\n⚠ Erreur : {e}\n   Les pages déjà générées sont conservées — "
              f"corrige puis relance la même commande pour reprendre.")
        raise                          # propage APRÈS le nettoyage du finally
    finally:
        cli.shielded_unload(config, models_used, base_url=llm_manga.get("base_url"))
        cli.finalize_power(args, inhibitor, interrupted=interrupted)
    sys.exit(0)


def _appliquer_options_lot(ap, args, config: dict) -> None:
    """Options qui vivent dans `config` plutôt que dans la signature de `process_volume`.

    C'est ce qui les rend disponibles à l'identique pour l'interface graphique, qui appelle
    l'orchestrateur sans passer par cette CLI (cf. `_appliquer_reflexion_lot`). Extraite du
    corps de `main()` au lot « série » : `--all` doit appliquer exactement les mêmes réglages,
    et deux copies auraient fini par diverger sur le plafond de `--lot`."""
    if args.dry_run:
        config.setdefault("options", {})["dry_run"] = True
    if args.verbose:
        config.setdefault("options", {})["verbose"] = True
    if args.lot is not None:
        if not (1 <= args.lot <= MAX_PLANCHES_LOT):
            ap.error(f"--lot doit être entre 1 et {MAX_PLANCHES_LOT} (reçu {args.lot}). "
                     f"Au-delà, un lot cesse d'être un lot pour devenir un tome — cf. la "
                     f"mesure citée sous `manga.lot` dans config.yaml.")
        config["manga"].setdefault("lot", {})["planches"] = args.lot
    if args.think is not None:
        config["manga"].setdefault("lot", {})["think"] = args.think


def _relettrage_cible(etat, tout_refaire: bool):
    """Les planches d'un chapitre à relettrer, ou `None` si ce n'est pas ce cas-là.

    Un chapitre `a_relettrer` a un cache COMPLET : rien n'y manque, seul l'ORDRE d'écriture
    est en cause (une traduction refaite, une réplique corrigée à la main, des zones
    retouchées après le rendu). `stages_to_redo` ne lit que la présence des fichiers, jamais
    leurs `mtime` : il conclurait « rien à faire » et `process_volume` sauterait chaque
    planche. Le chapitre ressortirait donc « à relettrer » après son propre passage, et
    chaque nuit le reprendrait pour ne rien faire.

    `--force` et `--from` reprennent la main quand ils sont donnés : l'utilisateur a nommé
    lui-même ce qu'il veut refaire, et sur tout le chapitre."""
    from manga import serie
    if tout_refaire or etat.statut != serie.A_RELETTRER or not etat.perimees:
        return None
    return set(etat.perimees)


def _run_all_chapitres(args, config: dict) -> int:
    """`--all` : enchaîne tous les chapitres d'une œuvre. Renvoie le code de sortie.

    Le squelette est celui de `run._run_all_volumes` (light novel) — anti-veille,
    préchargement et extinction UNE SEULE FOIS pour toute la série, `finally` unique,
    déchargement blindé contre un Ctrl+C tardif. Trois choses l'en distinguent, et chacune
    vient d'un défaut constaté :

    · **le pré-vol**. Le light novel ouvre chaque tome et laisse `process_volume` sauter les
      chapitres finis. Côté manga, ouvrir un tome fini n'est pas gratuit : `assemble_outputs`
      réécrit le CBZ inconditionnellement, soit 230 Mo pour *manga A* Vol.1, sur un
      dossier OneDrive. Un chapitre complet ET à jour n'est donc pas ouvert du tout ;

    · **l'isolation**. Le light novel arrête la série au premier échec. Une nuit de manga
      rendrait alors zéro chapitre pour un seul JPEG corrompu : chaque chapitre a donc son
      propre filet, et la série continue. L'arrêt PROPRE (`--stop`, Ctrl+C), lui, reste franc ;

    · **le bilan**. Il est recalculé depuis le DISQUE après la boucle, jamais tenu au fil de
      l'eau : c'est la seule version qui reste vraie quand un chapitre s'est arrêté au milieu
      ou qu'une planche est tombée en échec sans faire échouer son chapitre."""
    import datetime
    import time
    from pathlib import Path

    from core.control import StopRequested
    from manga import serie

    chemins = _chemins(config)
    src, build_root = Path(chemins["sources"]), Path(chemins["build"])
    etats_avant = serie.etats_serie(src, build_root, args.projet)
    if not etats_avant:
        print(f"Aucun chapitre trouvé pour « {args.projet} » sous {src / args.projet}")
        return 1

    # `--force` et `--from` sont des demandes EXPLICITES de refaire : elles neutralisent le
    # saut. Sans ça, `--all --from rendu` — l'harmonisation de toute l'œuvre avec le glossaire
    # enrichi par la nuit, pour zéro appel LLM — ne relettrerait aucun des chapitres déjà
    # finis, c'est-à-dire exactement ceux qu'il vise.
    tout_refaire = bool(args.force or args.from_stage)
    cibles = [e for e in etats_avant
              if (tout_refaire and e.statut != serie.SANS_SOURCE) or serie.a_traiter(e)]

    print(f"— Série « {args.projet} » — {len(etats_avant)} chapitre(s) :")
    for ligne in serie.tableau(etats_avant):
        print(f"   {ligne}")
    sautes = len(etats_avant) - len(cibles)
    relettrages = sum(1 for e in cibles if _relettrage_cible(e, tout_refaire))
    print(f"\n→ {len(cibles)} chapitre(s) à traiter"
          + (f", {sautes} sauté(s)" if sautes else "")
          + (f" (dont {relettrages} en relettrage ciblé)" if relettrages else "")
          + (" — --force/--from : les chapitres finis sont refaits" if tout_refaire else ""))
    if not cibles:
        print("Rien à faire. « --force » ou « --from rendu » pour refaire quand même.")
        return 0

    dry = bool(config.get("options", {}).get("dry_run"))
    # Un run de nuit doit MESURER même quand il n'affiche rien : `options.verbose` fait
    # calculer et journaliser les lignes de perf, tandis que `--verbose` ne décide plus que de
    # leur affichage (cf. `cli.make_reporter` et `Reporter.set_console_verbose`). Sans ça, le
    # perf.log d'une nuit ne porterait que les incidents, jamais les temps.
    config.setdefault("options", {})["verbose"] = True

    journal = build_root / args.projet / "perf.log"

    def _dire(msg: str) -> None:
        """Console + journal de SÉRIE. Les `perf.log` par chapitre disent ce qui s'est passé
        dans un chapitre ; celui-ci dit ce que la nuit a fait — c'est le fichier à suivre
        depuis un second terminal (`Get-Content -Wait`) quand quinze chapitres défilent.

        Écrit **aussi en dry-run**, contrairement au `perf.log` d'un chapitre : il est ici le
        pendant de `RAPPORT-SERIE.md`, que le dry-run produit déjà, et les deux vivent dans le
        même dossier. Une répétition générale qui ne laisserait qu'un des deux serait plus
        déroutante qu'utile. Rouvert à chaque ligne : une série qui meurt brutalement doit
        laisser tout ce qu'elle a dit jusque-là."""
        print(msg)
        try:
            journal.parent.mkdir(parents=True, exist_ok=True)
            with open(journal, "a", encoding="utf-8") as fh:
                fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg.strip()}\n")
        except OSError:
            pass       # un journal indisponible ne doit jamais coûter le run

    inhibitor = cli.preparer_veille(args.keep_awake or args.shutdown,
                                    "Veille du PC désactivée pour la durée de la série.")
    # Même garde que le run mono-chapitre : `--from rendu` ne traduit rien, précharger y
    # ferait monter 17 Go en VRAM pour rien, et le déchargement final évincerait un modèle
    # que l'utilisateur avait peut-être chargé pour autre chose.
    from manga.checkpoints import downstream
    traduira = args.from_stage is None or "traduction" in downstream(args.from_stage)
    llm_manga = core_config.section(config, "manga", "llm")
    models_used = cli.models_in_config(config, "manga") if traduira else []
    cli.precharger_modeles(config, models_used, dry_run=dry,
                           base_url=llm_manga.get("base_url"))

    from manga.orchestrator_manga import process_volume

    resultats: list[tuple[str, str, float]] = []      # (chapitre, issue, durée en secondes)
    interrupted = False
    code = 0
    t_serie = time.perf_counter()
    _dire(f"— Série « {args.projet} » : {len(cibles)} chapitre(s) — "
          f"{', '.join(e.tome for e in cibles)}")
    try:
        for i, etat in enumerate(cibles, 1):
            tome = etat.tome
            # ⚠ Un chapitre « à relettrer » a un cache COMPLET : `stages_to_redo` n'y voit rien
            # à refaire, et `process_volume` sauterait chacune de ses planches. Il resterait
            # donc « à relettrer » après son propre passage, et chaque nuit le reprendrait pour
            # ne rien faire. La péremption se lit sur les `mtime`, que le cache ignore : il faut
            # la nommer explicitement. `only_pages` + `--from rendu` ne relettrent QUE les
            # planches en retard — c'est déjà ce que l'éditeur graphique demande après une
            # correction à la main, et ça évite de relettrer 150 planches pour une seule.
            cible_relettrage = _relettrage_cible(etat, tout_refaire)
            if cible_relettrage:
                _dire(f"\n=== [{i}/{len(cibles)}] {args.projet} / {tome} — relettrage ciblé : "
                      f"{len(cible_relettrage)} planche(s) en retard sur leurs données ===")
            else:
                _dire(f"\n=== [{i}/{len(cibles)}] {args.projet} / {tome} ===")
            args.tome = tome            # pour `_make_reporter` : un perf.log par chapitre
            reporter = _make_reporter(args, config)
            t0 = time.perf_counter()
            try:
                complet = process_volume(
                    args.projet, tome, config, reporter=reporter,
                    force=args.force,
                    restart_from="rendu" if cible_relettrage else args.from_stage,
                    only_pages=cible_relettrage or None,
                    conf_threshold=args.conf, iou_threshold=args.iou)
            except (StopRequested, KeyboardInterrupt):
                raise                   # l'arrêt propre reste franc : il vise la SÉRIE
            except (Exception, SystemExit) as err:
                # `SystemExit` est attrapé au même titre : c'est ce que lèvent un dossier de
                # chapitre vide (`sources_manga.scan_volume`) et un modèle ONNX introuvable.
                # Ce sont des accidents de chapitre, pas des raisons de perdre la nuit.
                resultats.append((tome, f"échec — {type(err).__name__} : {err}",
                                  time.perf_counter() - t0))
                _dire(f"⚠ « {tome} » a échoué ({type(err).__name__} : {err}) — la série "
                      f"continue au chapitre suivant.")
                continue
            finally:
                reporter.close()
            if not complet:
                resultats.append((tome, "arrêt propre", time.perf_counter() - t0))
                _dire(f"■ Arrêt demandé pendant « {tome} » — série interrompue.")
                interrupted = True
                break
            resultats.append((tome, "terminé", time.perf_counter() - t0))
    except (StopRequested, KeyboardInterrupt):
        interrupted = True
        print("\nInterrompu. Relance la même commande pour reprendre — les chapitres déjà "
              "finis seront sautés.")
    finally:
        # ⚠ Le bilan est écrit AVANT `finalize_power` : avec `--shutdown`, celui-ci programme
        # l'extinction puis dort tout le délai. Un rapport écrit après ne serait jamais écrit.
        code = _cloturer_serie(args.projet, src, build_root, resultats,
                               time.perf_counter() - t_serie, interrupted, _dire)
        cli.shielded_unload(config, models_used, base_url=llm_manga.get("base_url"))
        cli.finalize_power(args, inhibitor, interrupted=interrupted)
    return code


def _cloturer_serie(projet: str, src, build_root, resultats, duree_s: float,
                    interrupted: bool, dire) -> int:
    """Bilan de fin de série : rapport sur disque, tableau à l'écran, code de sortie.

    L'état est **relu depuis le disque**, pas déduit des retours de `process_volume` : un
    chapitre peut se terminer normalement en ayant laissé trois planches en échec, et c'est
    `pages_out/` qui le dit, pas le code de retour."""
    from manga import serie
    etats = serie.etats_serie(src, build_root, projet)
    chemin = _ecrire_rapport_serie(build_root, projet, etats, resultats, duree_s, interrupted)

    dire(f"\n— Bilan de la série « {projet} » —")
    for ligne in serie.tableau(etats):
        dire(f"   {ligne}")
    echecs = [t for t, issue, _ in resultats if issue.startswith("échec")]
    reste = [e.tome for e in etats if serie.a_traiter(e)]
    if echecs:
        dire(f"⚠ {len(echecs)} chapitre(s) en échec : {', '.join(echecs)}")
    if reste:
        dire(f"→ Reste à traiter : {', '.join(reste)} — relance la même commande.")

    # Code de sortie : « faut-il que je regarde ? ». Un chapitre qui a levé, évidemment — mais
    # aussi un chapitre qu'on a traité et qui reste incomplet, ce qui est le cas quand des
    # PLANCHES sont tombées en échec sans faire tomber leur chapitre (le filet par planche).
    # Sans cette seconde condition, une nuit qui perd trois planches sortirait en 0.
    #
    # ⚠ Sauf après un arrêt DEMANDÉ : ce qui reste alors n'est pas une anomalie, c'est ce
    # qu'on a choisi de ne pas faire.
    tentes = {t for t, _, _ in resultats}
    inacheves = [e.tome for e in etats if serie.a_traiter(e) and e.tome in tentes]
    if inacheves and not interrupted and not echecs:
        dire(f"⚠ Traité(s) mais incomplet(s) : {', '.join(inacheves)} — voir la section "
             f"« Planches en ÉCHEC » de leur RAPPORT.md.")
    dire(f"Rapport de série : {chemin}")
    return 1 if (echecs or (inacheves and not interrupted)) else 0


def _ecrire_rapport_serie(build_root, projet: str, etats, resultats, duree_s: float,
                          interrupted: bool):
    """`build/<Œuvre>/RAPPORT-SERIE.md` — ce qu'on lit au matin.

    Les `RAPPORT.md` par chapitre restent la source de détail (bulles, débordements,
    glossaire). Celui-ci répond à la seule question qu'on se pose devant un PC qui a tourné
    huit heures : *qu'est-ce qui est passé, qu'est-ce qui reste, et où regarder ?*"""
    from pathlib import Path

    from core import report
    from manga import serie

    lignes = [f"# Série — {projet}", ""]
    lignes += report.entete_run(duree_s)
    lignes.append(f"- Chapitres : {len(etats)} · traités ce run : {len(resultats)}")
    if interrupted:
        lignes.append("- ⚠ Série **interrompue** (arrêt propre ou Ctrl+C) — relancer la "
                      "même commande reprend où elle s'est arrêtée.")
    lignes += ["", "## État de l'œuvre", "",
               "| Chapitre | État | Détail |", "| --- | --- | --- |"]
    for e in etats:
        lignes.append(f"| {e.tome} | {serie.PUCES.get(e.statut, '')} {e.statut} | {e.detail} |")
    lignes.append("")

    if resultats:
        # ⚠ L'issue est CROISÉE avec l'état du disque. `process_volume` peut rendre « terminé »
        # sur un chapitre dont trois planches sont tombées en échec — le filet par planche est
        # fait pour ça. Les deux colonnes se contrediraient alors dans le même tableau.
        a_finir = {e.tome for e in etats if serie.a_traiter(e)}
        lignes += ["## Ce que ce run a fait", "",
                   "| Chapitre | Issue | Durée |", "| --- | --- | --- |"]
        for tome, issue, duree in resultats:
            mins, secs = divmod(int(duree), 60)
            if issue == "terminé" and tome in a_finir:
                issue = "terminé, mais INCOMPLET — planches en échec (voir son RAPPORT.md)"
            lignes.append(f"| {tome} | {issue} | {mins}min {secs}s |")
        lignes.append("")

    echecs = [f"**{tome}** — {issue.removeprefix('échec — ')} · reprendre avec "
              f"`python run_manga.py \"{projet}\" {tome}`"
              for tome, issue, _ in resultats if issue.startswith("échec")]
    lignes += report.section("Chapitres en échec", echecs, 40)

    reste = [f"{e.tome} — {e.detail}" for e in etats if serie.a_traiter(e)]
    lignes += report.section("Reste à traiter", reste, 40)
    if not reste:
        lignes += ["## Reste à traiter (0)", "",
                   "- L'œuvre est complète et à jour.", ""]

    return report.ecrire(Path(build_root) / projet, "\n".join(lignes) + "\n",
                         nom="RAPPORT-SERIE.md")


def _modeles_du_glossaire(config: dict, extraction: bool) -> list[str]:
    """Les SEULS modèles que les commandes de glossaire vont solliciter.

    `cli.models_in_config(config, "manga")` renverrait tout le roster — traducteur compris.
    Le précharger ferait monter 17 Go en VRAM pour une commande qui ne traduit rien, et le
    déchargement final évincerait un modèle que l'utilisateur avait peut-être chargé pour
    autre chose. C'est le même raisonnement que la garde `traduira` du run mono-chapitre."""
    specs = (config.get("manga") or {}).get("modeles") or {}
    out: list[str] = []
    for nom in (("terminologue", "glossariste") if extraction else ("glossariste",)):
        spec = specs.get(nom)
        m = spec.get("model") if isinstance(spec, dict) else spec
        if m and m not in out:
            out.append(m)
    return out


def _run_glossaire(args, config: dict, *, extraction: bool) -> int:
    """`--extract-glossary` / `--optimize-glossary` : le glossaire de l'œuvre, et rien d'autre.
    Renvoie le code de sortie.

    Trois choses le distinguent de `_run_all_chapitres`, et chacune vient de ce que la
    commande promet :

    · **rien n'est rendu**. Aucun `RAPPORT-SERIE.md`, aucun pré-vol sur l'état des chapitres :
      un chapitre « complet et à jour » est justement celui qu'on veut relever, puisqu'il a
      été traduit sans que le terminologue ne passe jamais ;

    · **le dédoublonnage est payé UNE fois**, après le dernier chapitre, et seulement si le
      glossaire a réellement bougé (`glossaire_manga.empreinte`). L'agent glossariste travaille
      sur le glossaire ENTIER de l'œuvre : le rappeler par chapitre serait quinze appels pour
      un seul résultat ;

    · **l'isolation par chapitre est conservée** : un JPEG corrompu au chapitre 7 ne doit pas
      coûter les huit suivants. L'arrêt PROPRE (`--stop`, Ctrl+C), lui, reste franc."""
    from pathlib import Path

    from core.control import StopRequested
    from manga import glossaire_manga, serie

    chemins = _chemins(config)
    src = Path(chemins["sources"])
    chapitres: list[str] = []
    if extraction:
        chapitres = [args.tome] if args.tome else serie.lister_chapitres(src, args.projet)
        if not chapitres:
            print(f"Aucun chapitre trouvé pour « {args.projet} » sous {src / args.projet}")
            return 1

    dry = bool(config.get("options", {}).get("dry_run"))
    inhibitor = cli.preparer_veille(args.keep_awake or args.shutdown,
                                    "Veille du PC désactivée pour la durée de l'extraction.")
    llm_manga = core_config.section(config, "manga", "llm")
    models_used = _modeles_du_glossaire(config, extraction)
    cli.precharger_modeles(config, models_used, dry_run=dry,
                           base_url=llm_manga.get("base_url"))

    avant = glossaire_manga.empreinte(args.projet, config)
    echecs: list[str] = []
    interrupted = False
    try:
        for i, tome in enumerate(chapitres, 1):
            if len(chapitres) > 1:
                print(f"\n=== [{i}/{len(chapitres)}] {args.projet} / {tome} — glossaire ===")
            args.tome = tome            # pour `_make_reporter` : un perf.log par chapitre
            reporter = _make_reporter(args, config)
            try:
                termine = glossaire_manga.run_extract_glossary(
                    args.projet, tome, config, reporter=reporter, force=args.force,
                    restart_from=args.from_stage, only_page=args.page)
            except (StopRequested, KeyboardInterrupt):
                raise                   # l'arrêt propre vise l'ŒUVRE, pas un chapitre
            except (Exception, SystemExit) as err:
                # `SystemExit` au même titre : c'est ce que lèvent un dossier de chapitre vide
                # et un modèle ONNX introuvable. Des accidents de chapitre, pas de commande.
                echecs.append(tome)
                print(f"⚠ « {tome} » a échoué ({type(err).__name__} : {err}) — l'extraction "
                      f"continue au chapitre suivant.")
                continue
            finally:
                reporter.close()
            if not termine:
                interrupted = True
                print(f"■ Arrêt demandé pendant « {tome} » — extraction interrompue.")
                break

        if interrupted:
            pass                        # on n'optimise pas un glossaire qu'on vient d'arrêter
        elif not extraction or glossaire_manga.empreinte(args.projet, config) != avant:
            glossaire_manga.run_optimize_glossary(args.projet, config, reporter=Reporter())
        else:
            print("Glossaire inchangé par l'extraction — dédoublonnage inutile, "
                  "aucun appel LLM.")
    except (StopRequested, KeyboardInterrupt):
        interrupted = True
        print("\nInterrompu. Le glossaire est sauvegardé — relance la même commande pour "
              "reprendre où tu t'es arrêté (les planches déjà relevées sont relues du cache).")
    finally:
        cli.shielded_unload(config, models_used, base_url=llm_manga.get("base_url"))
        cli.finalize_power(args, inhibitor, interrupted=interrupted)

    print(f"Glossaire de l'œuvre : {glossaire_manga.chemin_glossaire(args.projet, config)}")
    if echecs:
        print(f"⚠ {len(echecs)} chapitre(s) en échec : {', '.join(echecs)} — relance la même "
              f"commande, les chapitres déjà relevés ne repaieront rien.")
        return 1
    return 0


def _chemins(config: dict) -> dict:
    """Chemins de la brique manga, HÉRITÉS de `chemins:` à la racine par fusion profonde
    (`core/config.py`). `manga.chemins` recopiait auparavant `sources` et `build` : changer
    la seule racine faisait écrire la brique manga à l'ancien endroit, silencieusement."""
    return core_config.section(config, "manga", "chemins")


def _build_dir(config: dict, projet: str, tome: str):
    """Dossier de travail d'un tome manga. Résolu ICI et non recopié à chaque appel : les
    trois call sites (--stop, --assembler, perf.log) doivent viser le même dossier, sinon
    `--stop` demande l'arrêt d'un run qui écoute ailleurs."""
    from pathlib import Path
    return Path(_chemins(config)["build"]) / projet / tome / "manga"


def _make_reporter(args, config: dict) -> Reporter:
    """Reporter standard, avec en plus un fichier perf.log si --verbose : les lignes
    de perf (temps/tokens/vitesse par étage) y sont dupliquées, pour un suivi dans un
    2e terminal (`Get-Content -Wait build/<projet>/<tome>/manga/perf.log`) sans
    polluer le flux principal des pages qui défilent. Miroir de `run._make_reporter`."""
    return cli.make_reporter(
        Reporter(), _build_dir(config, args.projet, args.tome),
        verbose=args.verbose, dry_run=bool(config.get("options", {}).get("dry_run")))


def _run_psd_test(config: dict, chemin: str) -> bool:
    """Écrit un PSD minimal — un fond, un seul calque de texte — et dit quoi en faire.

    Valider les calques de type sur un tome entier coûte un run complet et, quand ça se passe
    mal, un Photoshop qui plante. Ce fichier-là s'ouvre en dix secondes et isole la question :
    s'il passe, le `TySh` est bon et un échec vient d'ailleurs ; s'il plante, tout est dit."""
    from pathlib import Path

    from manga import psd

    mcfg = config.get("manga") or {}
    police = (mcfg.get("typeset") or {}).get("font_path") or None
    sortie = psd.psd_minimal(Path(chemin), font_path=police)
    taille = sortie.stat().st_size

    print(f"✓ PSD minimal écrit : {sortie} ({taille / 1024:.0f} Ko)")
    print("  Contenu : un calque « Fond », un calque de texte « Test ».")
    print()
    print("  Ouvre-le dans Photoshop, puis vérifie trois choses :")
    print("   1. le fichier s'ouvre SANS boîte d'alerte ni plantage ;")
    print("   2. le calque « Texte — Test » porte l'icône T dans le panneau Calques ;")
    print("   3. un double-clic à l'outil Texte sélectionne le mot, et tu peux le réécrire.")
    print()
    print("  Si les trois passent, les calques de type sont bons : remets")
    print("  config.yaml > manga.rendu.psd_texte: \"type\" pour tes planches.")
    print("  Si l'un échoue, garde \"rasterise\" — le lettrage reste juste, seule la")
    print("  réécriture au clavier manque — et signale-le.")
    try:
        from psd_tools import PSDImage
        doc = PSDImage.open(sortie)
        genres = [(c.name, c.kind) for c in doc]
        print()
        print(f"  (relecture par psd-tools : {genres})")
    except ImportError:
        pass
    return True


def _run_doctor(config: dict) -> bool:
    """Diagnostic de l'environnement manga : section de config, dépendances Python
    additionnelles, modèle de détection, connexion Ollama (réutilise
    `pipeline.llm.test_connection`)."""
    from pathlib import Path
    ok = True

    print("— Section config.yaml > manga —")
    mcfg = config.get("manga")
    if not mcfg:
        print("❌ Section « manga: » absente de config.yaml.")
        return False
    required = ["modeles", "temperatures", "detection"]
    missing = [k for k in required if k not in mcfg]
    if missing:
        print(f"❌ Clé(s) manquante(s) dans manga: {missing}")
        ok = False
    else:
        print("✓ Toutes les clés principales sont présentes.")

    if not cli.section_dependances(
            [("numpy", "numpy"), ("onnxruntime", "onnxruntime"),
             ("manga_ocr", "manga-ocr"), ("PIL", "pillow")],
            "`pip install -r requirements-manga.txt`"):
        ok = False

    print("\n— Modèle de détection de bulles —")
    det_cfg = mcfg.get("detection", {})
    model_path = Path(det_cfg.get("model_path", ""))
    if model_path.exists():
        print(f"✓ modèle trouvé : {model_path} ({model_path.stat().st_size // (1024*1024)} Mo)")
    elif det_cfg.get("telechargement_auto", True):
        # Le diagnostic TÉLÉCHARGE plutôt que de signaler : c'est justement le moment où
        # l'utilisateur prépare sa machine, pas au milieu d'un tome de 150 planches.
        from manga import models
        try:
            models.assurer_detecteur(model_path, url=det_cfg.get("model_url") or models.DETECTEUR_URL,
                                     dire=print)
        except SystemExit as err:
            print(f"❌ {err}")
            ok = False
    else:
        print(f"❌ modèle introuvable : {model_path or '(non défini)'} — voir manga_models/README.md.")
        print("  → manga.detection.telechargement_auto: true le récupérerait tout seul.")
        ok = False

    print("\n— Police de lettrage —")
    from manga.typeset import resolve_font
    from manga.psd import nom_postscript
    try:
        police = resolve_font((mcfg.get("typeset") or {}).get("font_path") or None)
        print(f"✓ police trouvée : {police}")
        if "psd" in ((mcfg.get("rendu") or {}).get("formats") or []) \
                and str((mcfg.get("rendu") or {}).get("psd_texte", "rasterise")) == "type":
            # Les calques de type d'un PSD ne portent PAS la police : ils la nomment. Photoshop
            # substitue en silence celle qu'il ne trouve pas — le calque reste éditable, mais le
            # lettrage change sans explication.
            print(f"  → les calques de texte du PSD déclareront « {nom_postscript(police)} » : "
                  f"installe cette police côté système avant d'ouvrir les PSD dans Photoshop "
                  f"(cf. templates/fonts/README.md).")
    except SystemExit as err:
        print(f"❌ {err}")
        ok = False

    probe_config = dict(config, llm=core_config.section(config, "manga", "llm"),
                        modeles=mcfg.get("modeles", {}),
                        temperatures=mcfg.get("temperatures", {}))
    if not cli.section_ollama(probe_config):
        ok = False
    return cli.conclure(ok)


if __name__ == "__main__":
    main()
