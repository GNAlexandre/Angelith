#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Pipeline de fan-traduction — CLI unique.

Traduire / améliorer un Tome :
  python run.py "Mon LN" Vol.1
  python run.py "Mon LN" Vol.1 --dry-run        # tuyauterie sans LLM
  python run.py "Mon LN" Vol.1 --force          # refait les chapitres déjà faits
  python run.py "Mon LN" Vol.1 --render-only     # régénère docx/epub/pdf depuis le .md

Arrêter proprement / reprendre (Tomes longs) :
  python run.py "Mon LN" Vol.1 --stop    # dans un AUTRE terminal : finit le bloc puis s'arrête
  python run.py "Mon LN" Vol.1           # relancer reprend au bloc suivant (même après reboot)
  (Ctrl+C dans le terminal du run fait pareil : arrêt après le bloc en cours.)

Relancer UNE étape après avoir modifié un prompt ou le glossaire (réutilise le cache) :
  python run.py "Mon LN" Vol.1 --from correction   # refait correction → mise en page → rendu
  (étapes : terminologie, traduction, correction, mise_en_page, rendu)

Ne retester qu'UN chapitre (le reste du Tome est réutilisé depuis son cache) :
  python run.py "Mon LN" Vol.1 --chapitre 3                  # refait le chapitre 3 en entier
  python run.py "Mon LN" Vol.1 --chapitre 3 --from correction  # ne refait que correction→… du chapitre 3

Optimiser le glossaire de l'œuvre (dédoublonner / fusionner / reclasser) :
  python run.py "Mon LN" --optimize-glossary

Laisser tourner la nuit sans veille, puis éteindre le PC (même en cas d'erreur) :
  python run.py "Mon LN" Vol.1 --keep-awake --shutdown
  (--shutdown programme une extinction ANNULABLE ; --shutdown-delay SECONDES pour régler le délai)

Traiter TOUTE une série en une seule commande (enchaîne les tomes à la suite ; un
tome déjà entièrement généré est sauté rapidement, chapitre par chapitre comme
d'habitude — donc relancer la même commande après coup ne refait pas ce qui est fini) :
  python run.py "Mon LN" --all
  python run.py "Mon LN" --all --keep-awake --shutdown   # anti-veille/extinction pour TOUTE la série

Diagnostiquer le découpage en chapitres :
  python run.py "Mon LN" Vol.1 --plan

Tester la connexion au serveur LLM :
  python run.py --test-llm

Diagnostic complet de l'environnement (config, chemins, Pandoc, PDF, Ollama) :
  python run.py --check

Mesurer ce que chaque agent apporte vraiment (sur un tome déjà traité, sans LLM) :
  python run.py "Mon LN" Vol.1 --diff-stages

Lister les projets disponibles (ou les tomes d'UN projet) sans rien traiter :
  python run.py --list
  python run.py "Mon LN" --list

Importer un glossaire existant (.docx/.txt) dans l'œuvre :
  python run.py "Mon LN" --import-glossary chemin/vers/glossaire_survival.docx

Réintégrer un glossaire YAML antérieur (.bak, export, ancienne installation, œuvre sœur),
converti au passage au format multi-cibles de la 2.0.0 :
  python run.py "Mon LN" --migrate-glossary sources/Mon LN/glossaire.bak.yaml
  python run.py "Mon LN" --migrate-glossary ancien.yaml autre.yaml --remplacer

Interface console interactive :
  python app.py
"""
import argparse
import sys

from core import cli

cli.configurer_stdout()

# ⚠ Les imports qui suivent sont VOLONTAIREMENT après l'appel ci-dessus : `configurer_stdout()`
# réencode la sortie console, et tout module qui touche à stdout en l'important — `rich` au
# premier chef — figerait l'ancien encodage. D'où les suppressions E402 de ce bloc.

from core.reporter import Reporter  # noqa: E402
from core.version import __version__  # noqa: E402
from pipeline import doctor  # noqa: E402

# ⚠ `pipeline.orchestrator` n'est PAS importé ici, et c'est délibéré. Il tire
# `core.agents` → `core.llm` → **`openai`**, dont l'import seul coûte **5,18 s** (mesuré au
# `python -X importtime`). À la racine du module, chaque invocation le payait — y compris
# `--version`, `--list`, `--check`, `--plan` et surtout `--stop`, qu'on lance dans un second
# terminal précisément pour arrêter vite. `run_manga.py` importe son orchestrateur dans la
# branche qui s'en sert et démarre en 0,33 s ; on fait pareil.

def process_volume(*args, **kwargs):
    """Proxy paresseux vers `pipeline.orchestrator.process_volume`.

    ⚠ L'import réel est **dans le corps**, pas en tête de module. `pipeline.orchestrator`
    tire `core.agents` → `core.llm` → **`openai`**, dont l'import seul coûte **5,18 s**
    (mesuré au `python -X importtime`). À la racine, chaque invocation le payait — y compris
    `--version`, `--list`, `--check`, `--plan`, et surtout `--stop`, qu'on lance dans un
    second terminal précisément pour arrêter vite. `run_manga.py` importe son orchestrateur
    dans la branche qui s'en sert et démarre en 0,33 s ; on obtient ici le même effet.

    ⚠ Un proxy plutôt qu'un `from … import` déplacé dans chaque appelant, pour une raison
    précise : `run.process_volume` fait partie de la surface du module et
    `tests/test_run_cli.py` le remplace par un double à cinq endroits. Descendre l'import dans
    les fonctions supprimait l'attribut, donc cassait ces cinq tests — et aurait échangé cinq
    secondes de démarrage contre la testabilité de l'enchaînement des tomes."""
    from pipeline.orchestrator import process_volume as _reel
    return _reel(*args, **kwargs)


# Le cycle de vie « veille / préchargement / extinction » vit dans `core/cli.py` depuis le lot
# 2.6, pour qu'`app.py` cesse d'importer une CLI (inversion de couche). Ré-exports NOMMÉS
# sous les anciens noms privés : `tests/test_run_cli.py` les appelle, et les appeler encore
# ici garde `run.py` lisible de haut en bas.
_models_in_config = cli.models_in_config
_unload_models = cli.unload_models
_shielded_unload = cli.shielded_unload
_finalize_power = cli.finalize_power


def main() -> None:
    ap = argparse.ArgumentParser(description="Fan-traduction multi-sources (local, multi-agents).")
    ap.add_argument("projet", nargs="?", help="dossier projet sous sources/ (ex. \"Mon LN\")")
    ap.add_argument("tome", nargs="?", help="dossier de tome (ex. Vol.1)")
    ap.add_argument("--version", action="version", version=f"Angelith {__version__}",
                    help="affiche la version du dépôt et quitte")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--all", action="store_true",
                    help="traite TOUS les tomes du projet à la suite (nuit/série longue) — un tome "
                         "déjà entièrement généré est sauté rapidement, chapitre par chapitre comme "
                         "d'habitude ; l'anti-veille/préchargement/extinction (--keep-awake/--shutdown) "
                         "s'appliquent alors à TOUTE la série, pas tome par tome ; ne précise pas de tome")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="refait les chapitres déjà présents")
    ap.add_argument("--chapitre", type=int, metavar="N", default=None,
                    help="ne (re)traite QUE le chapitre N (1-indexé) — les autres sont réutilisés depuis "
                         "leur cache existant ; combine avec --from pour ne relancer qu'une étape de ce "
                         "chapitre, ou seul pour le refaire entièrement (pratique pour retester un prompt "
                         "modifié sans repasser tout le Tome)")
    ap.add_argument("--dry-run", action="store_true", help="sans appel LLM (test)")
    ap.add_argument("--verbose", action="store_true",
                    help="affiche après chaque bloc le temps, les tokens générés et la vitesse "
                         "(tok/s) — pour comparer la perf ou vérifier l'accélération GPU. Les "
                         "lignes de perf sont aussi écrites dans build/<projet>/<tome>/perf.log "
                         "(suivable dans un 2e terminal : Get-Content -Wait …\\perf.log)")
    ap.add_argument("--plan", action="store_true",
                    help="diagnostic : affiche les chapitres détectés par langue, puis quitte")
    ap.add_argument("--list", action="store_true",
                    help="liste les projets disponibles (ou les tomes d'UN projet si précisé), sans "
                         "rien traiter — indique aussi lesquels ont déjà un build")
    ap.add_argument("--check", action="store_true",
                    help="diagnostic complet de l'environnement (config.yaml, chemins, Pandoc, moteur "
                         "PDF, connexion Ollama) puis quitte — plus large que --test-llm")
    ap.add_argument("--diff-stages", action="store_true",
                    help="mesure la VALEUR AJOUTÉE de chaque agent sur un tome déjà traité (lit les "
                         "checkpoints, aucun appel LLM) : blocs réellement modifiés par étape, "
                         "et application de la règle des temps du récit par le correcteur")
    ap.add_argument("--stop", action="store_true",
                    help="demande l'arrêt propre du run en cours sur ce Tome (finit le bloc puis s'arrête)")
    ap.add_argument("--test-llm", action="store_true",
                    help="teste la connexion au serveur LLM puis quitte")
    ap.add_argument("--import-glossary", metavar="FICHIER",
                    help="importe un glossaire .docx/.txt dans sources/<projet>/glossaire.yaml puis quitte")
    ap.add_argument("--migrate-glossary", metavar="FICHIER", nargs="+",
                    help="réintègre un ou plusieurs glossaires YAML ANTÉRIEURS (.bak, export, copie d'une "
                         "ancienne installation, œuvre sœur) dans sources/<projet>/glossaire.yaml, en les "
                         "convertissant au format multi-cibles si besoin. Les fichiers donnés font autorité "
                         "(le premier sert de base) ; les sources ne sont jamais modifiées")
    ap.add_argument("--remplacer", action="store_true",
                    help="avec --migrate-glossary : ignore le glossaire actuel du projet au lieu de le "
                         "fusionner (cas de récupération, quand c'est lui qui est abîmé). Il est sauvegardé "
                         "en glossaire.yaml.avant-reintegration.bak avant d'être écrasé")
    ap.add_argument("--from", dest="from_stage", metavar="ÉTAPE",
                    choices=["terminologie", "traduction", "correction", "mise_en_page", "rendu"],
                    help="relance à partir de cette étape en réutilisant le cache des étapes précédentes "
                         "(ex. --from correction après avoir modifié le prompt du correcteur ou le glossaire)")
    ap.add_argument("--optimize-glossary", action="store_true",
                    help="lance l'agent glossariste : dédoublonne/fusionne/reclasse le glossaire de l'œuvre, puis quitte")
    ap.add_argument("--extract-glossary", action="store_true",
                    help="reconstruit/enrichit le glossaire à partir d'un TOME DÉJÀ TRADUIT (le FR sert de pivot) "
                         "— ne retraduit ni ne réécrit rien ; nécessite projet ET tome")
    cli.ajouter_flags_veille(ap)
    cli.ajouter_flag_sans_llm(ap)
    args = ap.parse_args()

    if args.sans_llm:
        # ⚠ **Le light novel refuse ce mode, et le motif est écrit plutôt que sous-entendu.**
        # Il n'existe aucune surface de saisie manuelle pour de la prose : la Retouche est un
        # éditeur de PLANCHES, et un roman rendu sans traduction sortirait avec son texte
        # source dans un `.docx` français — une sortie fausse, pas une sortie partielle.
        # `pipeline/orchestrator.py` le dit déjà d'un traducteur désactivé : « sans traduction,
        # le pipeline n'a rien à produire ».
        #
        # ⚠ Le drapeau EXISTE quand même sur cette CLI, et c'est délibéré : l'omettre ferait
        # croire à un oubli et renverrait un « unrecognized arguments » qui n'explique rien.
        raise SystemExit(
            "--sans-llm n'est pas disponible pour le light novel.\n"
            "  La brique manga peut sortir des planches aux bulles VIDES, qu'on remplit "
            "ensuite dans la Retouche ; il n'existe pas d'équivalent pour de la prose, et un "
            "roman rendu sans traduction porterait son texte source dans un .docx français.\n"
            "  → pour relire ou corriger sans serveur : run_manga.py --sans-llm, ou "
            "config.yaml > manga.llm.actif: false")
    config = cli.charger_config(args.config)

    if args.verbose:
        config.setdefault("options", {})["verbose"] = True

    # 0aaa) Lister projets/tomes sans rien traiter
    if args.list:
        from pathlib import Path
        from pipeline import sources
        cli.afficher_liste(sources.list_projects, sources.list_volumes,
                           Path(config["chemins"]["sources"]),
                           Path(config["chemins"]["build"]), args.projet)
        sys.exit(0)

    # 0aa) Diagnostic complet de l'environnement (config, chemins, outils externes, Ollama)
    if args.check:
        cli.avertir_config(config)
        cli.bloc_langue(config)
        sys.exit(0 if _run_doctor(config) else 1)

    # 0ab) Valeur ajoutée par agent, sur les checkpoints d'un tome déjà traité
    if args.diff_stages:
        if not (args.projet and args.tome):
            ap.error("précise le projet ET le tome : python run.py \"Mon LN\" Vol.1 --diff-stages")
        from pathlib import Path
        from pipeline import stagediff
        ckpt = Path(config["chemins"]["build"]) / args.projet / args.tome / ".checkpoints"
        print(stagediff.format_report(stagediff.analyse(ckpt)))
        sys.exit(0)

    # 0a) Diagnostic du découpage en chapitres
    if args.plan:
        if not (args.projet and args.tome):
            ap.error("précise le projet ET le tome : python run.py \"Mon LN\" Vol.1 --plan")
        from pathlib import Path
        from pipeline import sources
        src = Path(config["chemins"]["sources"])
        build_dir = Path(config["chemins"]["build"]) / args.projet / args.tome
        plan = sources.scan_volume(src / args.projet / args.tome, config, build_dir)
        print(f"Pivot : {plan.pivot}  |  images : {plan.image_lang or '—'}  |  mode : {plan.mode}")
        for code, ls in plan.langs.items():
            print(f"\n[{code}] {len(ls.chapters)} chapitre(s) détecté(s) :")
            for i, ch in enumerate(ls.chapters[:40], 1):
                t = ch.title or ("(sans titre — début : " + ch.body[:40].replace(chr(10), " ") + "…)")
                print(f"   {i:2d}. {t[:72]}")
                for j, part in enumerate(ch.parts[:60], 1):
                    print(f"        {i:2d}.{j:<2d} {part.title[:64]}")
            if len(getattr(ls, "files", []) or []) > 1:
                print("   fichiers concaténés (ordre de lecture) :")
                for f in ls.files:
                    print(f"      → {f.name}")
        # Appariement des références sur le pivot — ce que le run fera VRAIMENT.
        # « 9 chapitres contre 5 » ne dit pas ce qui sera remis au traducteur ; c'est en
        # voyant les parts de volume qu'on repère un décalage AVANT de payer un run.
        pivot_ls = plan.langs.get(plan.pivot)
        if pivot_ls is not None and len(plan.langs) > 1:
            from pipeline import split as _split
            tailles_pivot = [len(ch.body) for ch in pivot_ls.chapters]
            total_p = sum(tailles_pivot) or 1
            for code, ls in plan.langs.items():
                if code == plan.pivot or len(ls.chapters) == len(pivot_ls.chapters):
                    continue
                app = _split.apparier_chapitres(
                    [ch.body for ch in ls.chapters], tailles_pivot)
                total_r = sum(len(g) for g in app.groupes) or 1
                print(f"\n[{code}] appariement sur les {len(pivot_ls.chapters)} chapitre(s) du "
                      f"pivot ({len(ls.chapters)} unité(s) de référence) :")
                for i, (ch, g, idx) in enumerate(
                        zip(pivot_ls.chapters, app.groupes, app.indices), 1):
                    part_p = len(ch.body) / total_p * 100
                    part_r = len(g) / total_r * 100
                    ecart = part_r - part_p
                    alerte = "   <-- écart" if abs(ecart) > 2.0 else ""
                    print(f"   {i:2d}. {(ch.title or '(sans titre)')[:32]:32s} "
                          f"pivot {part_p:5.1f} %   référence {part_r:5.1f} % "
                          f"({ecart:+.1f}){alerte}")
                    # Quelle unité de référence atterrit là — la seule façon de voir qu'un
                    # épilogue s'est retrouvé apparié à une postface.
                    for k in idx:
                        u = ls.chapters[k]
                        print(f"          ← {k + 1:2d}. {(u.title or '(sans titre)')[:42]:42s}"
                              f" {len(u.body):7d} car.")
                if app.ecartees:
                    print("   écartées (hors corps, sans équivalent dans le pivot) :")
                    for k in app.ecartees:
                        u = ls.chapters[k]
                        print(f"          ✗ {k + 1:2d}. {(u.title or '(sans titre)')[:42]:42s}"
                              f" {len(u.body):7d} car.")
                for note in app.notes:
                    print(f"   · {note}")
        for w in plan.warnings:
            print(f"  ⚠ {w}")
        print("\nVérifie l'ordre des fichiers ci-dessus (prologue d'abord, parties dans l'ordre, épilogue/postface en dernier).")
        print("Les sous-lignes numérotées (ex. 3.1, 3.2…) sont les PARTIES détectées à l'intérieur d'un chapitre\n"
              "(second niveau de titre, ou mise en forme police+gras — voir config.yaml > decoupage.mise_en_forme).")
        print("Si un pivot a trop peu de chapitres : vérifie que ses titres sont des STYLES de titre (ou du gras+grand\n"
              "reconnaissable, cf. mise_en_forme), ajoute un motif dans config.yaml > decoupage.chapter_patterns,\n"
              "ou mets decoupage.detection: llm.")
        sys.exit(0)

    # 0) Demande d'arrêt propre d'un run en cours
    if args.stop:
        if not (args.projet and args.tome):
            ap.error("précise le projet ET le tome : python run.py \"Mon LN\" Vol.1 --stop")
        from pathlib import Path
        from core.control import request_stop
        build_dir = Path(config["chemins"]["build"]) / args.projet / args.tome
        request_stop(build_dir)
        print(f"Arrêt demandé pour {args.projet} / {args.tome}.")
        print("Les IA termineront le bloc en cours, sauvegarderont, puis s'arrêteront.")
        print("Relance « python run.py \"%s\" %s » plus tard pour reprendre." % (args.projet, args.tome))
        sys.exit(0)

    # 1) Test de connexion LLM
    if args.test_llm:
        from core.llm import test_connection
        sys.exit(0 if test_connection(config) else 1)

    # 2) Import de glossaire
    if args.import_glossary:
        if not args.projet:
            ap.error("précise le projet : python run.py \"Mon LN\" --import-glossary fichier")
        from core.glossary_import import import_into_project
        gpath, added, parsed = import_into_project(args.projet, args.import_glossary, config)
        tot = sum(len(v) for v in parsed.values())
        print(f"Glossaire importé dans : {gpath}")
        print(f"  Entrées lues : {tot}  "
              f"(termes {len(parsed['termes'])}, personnages {len(parsed['personnages'])}, "
              f"anglicismes {len(parsed['anglicismes'])})")
        print(f"  Ajouts : {added['ajouts']} · fusions : {added['fusions']} · conflits : {added['conflits']}")
        if tot == 0:
            print("  ⚠ Aucune paire détectée — vérifie le format (séparateur =, :, →, tab, ou tableau).")
        sys.exit(0)

    # 2ante) Réintégration d'un glossaire antérieur (récupération / passage à la 2.0.0)
    if args.migrate_glossary:
        if not args.projet:
            ap.error("précise le projet : python run.py \"Mon LN\" --migrate-glossary fichier.yaml")
        from core import glossary
        from core.glossary_import import reintegrer_dans_projet
        gpath, total, rapport = reintegrer_dans_projet(
            args.projet, args.migrate_glossary, config,
            remplacer=args.remplacer, dry_run=args.dry_run)
        print(f"Réintégration dans : {gpath}" + ("  [dry-run — rien n'est écrit]" if args.dry_run else ""))
        largeur = max((len(r["fichier"].name) for r in rapport), default=0)
        for r in rapport:
            etat = (f"ancien format → migré sous « {glossary.cible_du_run()} » ({r['migrees']} entrée(s))"
                    if r["ancien"] else "déjà au format multi-cibles")
            role = " (actuel)" if r["fichier"] == gpath else ""
            print(f"  {r['fichier'].name:<{largeur}}{role} : {r['lues']:>4} entrées lues · {etat}")
            print(f"  {'':<{largeur}}{'':<{len(role)}}   ajouts {r['ajouts']} · fusions {r['fusions']} "
                  f"· conflits {r['conflits']}")
        if args.remplacer:
            print("  glossaire actuel du projet : ignoré (--remplacer)")
        print(f"  → {total['entrees']} entrées au total "
              f"(ajouts {total['ajouts']} · fusions {total['fusions']} · conflits {total['conflits']})")
        if total["sauvegarde"]:
            print(f"  Sauvegarde : {total['sauvegarde'].name}")
        sys.exit(0)

    # 2bis) Optimisation autonome du glossaire de l'œuvre
    if args.optimize_glossary:
        if not args.projet:
            ap.error("précise le projet : python run.py \"Mon LN\" --optimize-glossary")
        if args.dry_run:
            config["options"]["dry_run"] = True
        from pipeline.orchestrator import run_optimize
        run_optimize(args.projet, config, reporter=Reporter())
        sys.exit(0)

    # 2ter) Extraction du glossaire depuis un tome déjà traduit
    if args.extract_glossary:
        if not (args.projet and args.tome):
            ap.error("projet ET tome requis : python run.py \"Mon LN\" Vol.1 --extract-glossary")
        if args.dry_run:
            config["options"]["dry_run"] = True
        from pipeline.orchestrator import run_extract_glossary
        from core.control import StopRequested
        try:
            run_extract_glossary(args.projet, args.tome, config,
                                 reporter=_make_reporter(args, config))
        except (StopRequested, KeyboardInterrupt):
            print("\nInterrompu. Le glossaire est sauvegardé — relance la même commande "
                  "pour reprendre où tu t'es arrêté.")
            sys.exit(0)
        sys.exit(0)

    # 2quater) Traitement de TOUS les tomes d'un projet, à la suite (série longue/nuit)
    if args.all:
        if not args.projet:
            ap.error("précise le projet : python run.py \"Mon LN\" --all")
        if args.tome:
            ap.error("--all traite tous les tomes du projet : ne précise pas de tome avec --all")
        _run_all_volumes(args, config)
        sys.exit(0)

    # 3) Traduction d'un Tome
    if not (args.projet and args.tome):
        ap.error("projet ET tome requis (ou utilise --test-llm / --import-glossary / --optimize-glossary / --all).")
    if args.dry_run:
        config["options"]["dry_run"] = True

    # Anti-veille pendant le run (utile la nuit) — levé quoi qu'il arrive.
    inhibitor = cli.preparer_veille(args.keep_awake or args.shutdown,
                                    "Veille du PC désactivée pour la durée du run.")
    models_used = _models_in_config(config)
    cli.precharger_modeles(config, models_used,
                           dry_run=bool(config["options"].get("dry_run")))

    # Le déchargement VRAM + la finalisation (veille/extinction) sont regroupés dans un
    # `finally` UNIQUE : ils s'exécutent exactement une fois, quelle que soit la sortie
    # (fin normale, Ctrl+C, erreur). Le déchargement est blindé contre un Ctrl+C tardif
    # (_shielded_unload) pour toujours évincer le modèle proprement — c'est ce qui évite
    # que le modèle reste résident et fasse chuter le débit GPU au run suivant.
    # ⚠ La veille (keep-awake) n'est levée qu'à la toute fin, dans _finalize_power, APRÈS
    # que l'extinction éventuelle soit programmée ET son délai écoulé (sinon Windows peut
    # mettre le PC en veille pendant l'attente et figer le `shutdown /s`).
    # On n'annule PAS l'extinction sur erreur (interrupted reste False) : évite que le PC
    # tourne toute la nuit pour rien. Sur Ctrl+C (interrupted=True), pas d'extinction.
    interrupted = False
    try:
        process_volume(args.projet, args.tome, config,
                       reporter=_make_reporter(args, config), render_only=args.render_only, force=args.force,
                       restart_from=args.from_stage, only_chapter=args.chapitre)
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrompu. Relance la même commande pour reprendre.")
    except Exception as e:
        print(f"\n⚠ Erreur : {e}\n   Ton avancement par bloc est sauvegardé — "
              f"corrige puis relance la même commande pour reprendre.")
        raise                          # propage APRÈS le nettoyage du finally
    finally:
        _shielded_unload(config, models_used)
        _finalize_power(args, inhibitor, interrupted=interrupted)


def _run_all_volumes(args, config: dict) -> None:
    """--all : enchaîne TOUS les tomes d'un projet. Anti-veille/préchargement/
    extinction gérés UNE SEULE FOIS pour toute la série (pas par tome, contrairement
    au run mono-tome) — cf. les commentaires de `main()` sur l'ordre keep-awake/
    shutdown, identiques ici. Un tome déjà entièrement généré est simplement sauté
    rapidement, chapitre par chapitre, comme le fait déjà `process_volume`."""
    from pathlib import Path
    from pipeline import sources
    src = Path(config["chemins"]["sources"])
    volumes = sources.list_volumes(src, args.projet)
    if not volumes:
        print(f"Aucun tome trouvé pour « {args.projet} » sous {src / args.projet}")
        sys.exit(1)
    if args.dry_run:
        config["options"]["dry_run"] = True

    inhibitor = cli.preparer_veille(args.keep_awake or args.shutdown,
                                    "Veille du PC désactivée pour la durée de la série.")
    models_used = _models_in_config(config)
    cli.precharger_modeles(config, models_used,
                           dry_run=bool(config["options"].get("dry_run")))

    print(f"— Série « {args.projet} » : {len(volumes)} tome(s) à traiter : {', '.join(volumes)}")
    # Déchargement + finalisation dans un `finally` unique (cf. commentaire du run mono-tome) :
    # exécutés une seule fois quelle que soit la sortie, déchargement blindé contre un Ctrl+C tardif.
    interrupted = False
    try:
        for i, vol in enumerate(volumes, 1):
            print(f"\n=== [{i}/{len(volumes)}] {args.projet} / {vol} ===")
            args.tome = vol   # pour _make_reporter (perf.log par tome) et les messages d'erreur
            completed = process_volume(
                args.projet, vol, config, reporter=_make_reporter(args, config),
                render_only=args.render_only, force=args.force,
                restart_from=args.from_stage, only_chapter=args.chapitre)
            if not completed:
                print(f"■ Arrêt demandé — série interrompue avant le tome suivant « {vol} » traité.")
                interrupted = True
                break
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrompu. Relance la même commande pour reprendre "
              "(les tomes déjà finis seront sautés).")
    except Exception as e:
        print(f"\n⚠ Erreur sur « {args.tome} » : {e}\n   Relance la même commande pour reprendre "
              f"(les tomes déjà finis, et les chapitres déjà faits de celui en cours, seront sautés).")
        raise                          # propage APRÈS le nettoyage du finally
    finally:
        _shielded_unload(config, models_used)
        _finalize_power(args, inhibitor, interrupted=interrupted)


# Diagnostic light novel : extrait vers `pipeline/doctor.py` au lot 2.6 (c'est la brique
# qu'il diagnostique, pas le socle). Ré-export nommé — `tests/test_run_cli.py` l'appelle par
# ce chemin, et `--check` reste `run.py --check`.
_run_doctor = doctor.run_doctor


def _make_reporter(args, config: dict):
    """Reporter standard, avec en plus un fichier perf.log si --verbose : les lignes de
    perf (temps/tokens/vitesse par bloc) y sont dupliquées, pour un suivi dans un 2e
    terminal (`Get-Content -Wait build/<projet>/<tome>/perf.log`) sans polluer le flux
    principal des blocs qui défilent."""
    from pathlib import Path
    return cli.make_reporter(
        Reporter(), Path(config["chemins"]["build"]) / args.projet / args.tome,
        verbose=args.verbose, dry_run=bool(config["options"].get("dry_run")))


if __name__ == "__main__":
    main()
