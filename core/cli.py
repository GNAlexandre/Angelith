# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Fragments de CLI partagés par `run.py`, `run_manga.py` et `app.py`.

**On garde DEUX CLI.** Les vocabulaires de flags sont disjoints (`--chapitre`,
`--from terminologie|traduction|correction|mise_en_page|rendu`, `--plan`, `--diff-stages`,
`--extract-glossary`, `--all` d'un côté ; `--page`,
`--from detection|nettoyage|ocr|traduction|rendu`, `--assembler` de l'autre). Les fusionner
imposerait des sous-commandes, ce qui invaliderait **toutes** les commandes documentées dans
un README de 65 Ko, les deux docstrings de CLI, les messages d'interruption et
`tests/test_run_cli.py`. On extrait donc ce qui est réellement dupliqué, pas les CLI
elles-mêmes.

**Et c'est `app.py` qui unifie pour l'humain.** L'interface console importait
`_finalize_power`/`_run_doctor`/`_models_in_config` **depuis `run.py`** : une inversion de
couche — la TUI dépendait d'une CLI concurrente, si bien qu'on ne pouvait pas toucher à
`run.py` sans risquer de casser `app.py`. Ces fonctions vivent maintenant ici, et un menu
peut présenter les deux vocabulaires sans compromis.
"""
from __future__ import annotations

import signal
import sys

import yaml


def configurer_stdout() -> None:
    """UTF-8 sur stdout/stderr. Sans ça, une console Windows en cp1252 lève
    `UnicodeEncodeError` sur le premier titre japonais ou la première apostrophe
    typographique — au milieu d'un run, après des minutes de calcul."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def charger_config(chemin: str = "config.yaml") -> dict:
    """Lit `config.yaml`, et **valide le pack de langue cible tout de suite**.

    ⚠ La résolution du pack est faite ici, au chargement, et pas au premier usage. Un
    `langues.cible: de` sans pack allemand doit arrêter le programme AVANT que quoi que ce
    soit ne tourne : découvrir après six heures de GPU qu'un tome est sorti dans la mauvaise
    langue — ou pas du tout — est exactement ce que cette refonte doit rendre impossible.

    `resoudre_pack` lève un `ErreurPack` (un `SystemExit`), qui porte son propre message
    actionnable et la liste des packs disponibles.

    ⚠ **Deux gestes de plus depuis la 2.31.0, et tous deux sont inertes hors gel** (`PLAN-37`
    L37.4) : `installation.resoudre_config` choisit le fichier dans l'ordre CLI → copie
    utilisateur → copie livrée, et `installation.ancrer_chemins` ancre les chemins relatifs
    d'œuvres et de poids hors du dossier d'installation. Lancé depuis le dépôt, le premier rend
    l'argument tel quel et le second rend la configuration inchangée — c'est le critère 3 de la
    définition de « terminé », et `tests/test_installation.py` le tient."""
    from . import glossary, installation
    from .langues import resoudre_pack
    with open(installation.resoudre_config(chemin), encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    installation.ancrer_chemins(config or {})
    pack = resoudre_pack(config or {})
    # Le glossaire est multi-cibles : il doit savoir de quelle langue ce run parle avant la
    # première lecture. Posé ici, au seul endroit qui résout déjà le pack.
    glossary.definir_cible(pack.code)
    return config


def bloc_langue(config: dict) -> None:
    """Bloc « — Langue cible — » du doctor, identique pour les trois briques.

    Le pack est déjà validé par `charger_config` : si on arrive ici, il est résolu. Ce bloc
    ne re-vérifie donc pas, il MONTRE — quel pack sert, et d'où viennent réellement les
    fichiers, ce qui est la question qu'on se pose quand une traduction sort dans une langue
    qu'on n'attendait pas."""
    from .langues import resoudre_pack
    pack = resoudre_pack(config)
    print("\n— Langue cible —")
    if pack.racine is None:
        print(f"✓ {pack.nom_lisible()} [{pack.code}] — mode compatibilité "
              f"(aucun dossier langues/ : prompts, guide de style et gabarits lus à leurs "
              f"emplacements historiques)")
    else:
        print(f"✓ {pack.nom_lisible()} [{pack.code}] — pack {pack.racine}")
    dossier = pack.prompt("traducteur").parent
    marque = "✓" if dossier.exists() else "❌"
    print(f"  {marque} prompts : {dossier}")
    # ⚠ Le guide de style et les gabarits docx/epub ne sont PAS listés ici : ce sont des
    # artefacts du light novel, et `pipeline/doctor.py` les vérifie déjà. Les nommer dans le
    # socle y ferait entrer la connaissance d'une brique — cf. `tests/test_core_cli.py`.


def avertir_config(config: dict) -> int:
    """Affiche les clés que `config.yaml` ne reconnaît pas. Renvoie leur nombre.

    Branché sur le `--check` des trois briques. ⚠ **N'échoue jamais** : le code lit sa
    configuration à travers des centaines de `.get(...)` à défaut silencieux, donc une clé
    mal orthographiée laisse le run se dérouler entièrement avec la valeur par défaut. C'est
    ce silence qu'on casse — pas le droit de lancer un run avec une config qu'on n'a pas
    encore nettoyée."""
    from .config import verifier
    avertissements = verifier(config)
    if not avertissements:
        print("config.yaml : aucune clé inconnue.")
        return 0
    print(f"config.yaml : {len(avertissements)} clé(s) inconnue(s) — "
          f"lues avec leur valeur par défaut, donc sans effet :")
    for ligne in avertissements:
        print(f"  - {ligne}")
    return len(avertissements)


def ajouter_flags_veille(ap) -> None:
    """`--keep-awake`, `--shutdown`, `--shutdown-delay` — les seuls flags dont le nom, la
    sémantique ET le texte d'aide sont réellement identiques d'une brique à l'autre.

    Les autres flags « communs » ne le sont qu'en apparence : `--verbose` ne mesure pas la
    même chose des deux côtés (temps/tokens par bloc contre par étage de planche) et
    `--dry-run` non plus (aucun appel LLM contre détection et OCR **réels**, seule la
    traduction sautée). Les factoriser derrière des paramètres d'aide rendrait le helper plus
    long que les six `add_argument` qu'il remplace, en bousculant au passage l'ordre du
    `--help` d'une des deux CLI. On ne les extrait donc pas."""
    ap.add_argument("--keep-awake", action="store_true",
                    help="empêche la mise en veille du PC pendant le run (levé automatiquement à la fin)")
    ap.add_argument("--shutdown", action="store_true",
                    help="éteint le PC à la fin du run (succès OU erreur), après un délai annulable — idéal la nuit")
    ap.add_argument("--shutdown-delay", type=int, default=120, metavar="SECONDES",
                    help="délai avant extinction avec --shutdown (défaut 120 s ; annulable)")


def ajouter_flag_sans_llm(ap) -> None:
    """`--sans-llm` — le second fragment de CLI réellement partagé (lot 39).

    Même nom, même sémantique et même texte d'aide des deux côtés, ce qui est **le critère
    écrit** de `ajouter_flags_veille` ci-dessus pour extraire un flag plutôt que de le
    recopier.

    ⚠ **Ce n'est PAS `--dry-run`, et la confusion serait grave.** `--dry-run` SIMULE une
    traduction : le texte source traverse l'agent inchangé et s'écrit comme s'il était traduit.
    `--sans-llm` ne prétend rien : les bulles sortent vides, le rapport le dit planche par
    planche, et aucun client LLM n'est contacté.

    ⚠ **Le light novel accepte le drapeau et le REFUSE à l'exécution**, avec un message qui dit
    pourquoi. Le laisser absent de sa CLI ferait croire à un oubli ; le laisser passer
    produirait un roman dont le `.docx` français porterait le texte source."""
    ap.add_argument("--sans-llm", action="store_true",
                    help="aucun appel au serveur LLM : détection, nettoyage, OCR et rendu "
                         "seulement, bulles laissées VIDES (à saisir dans la Retouche). "
                         "Différent de --dry-run, qui simule une traduction")


def appliquer_sans_llm(config: dict, actif: bool) -> dict:
    """Reporte `--sans-llm` dans la configuration **déjà chargée**. Mute et rend `config`.

    ⚠ Même patron que `core.modeles.outrepasser` : on mute le dictionnaire en mémoire, jamais
    le fichier. `config.yaml` est un document de 158 Ko dont la prose est la documentation
    (interdit 5) ; un aller-retour `yaml.safe_dump` l'effacerait.

    ⚠ **Le drapeau ne peut qu'ARMER le mode, jamais le désarmer.** Ne pas le passer laisse
    `llm.actif` décider — c'est la règle des trois états de `gui/parametres.py` : absent =
    « n'y touche pas », et non « remets à la valeur d'usine »."""
    if not actif:
        return config
    config.setdefault("llm", {})["actif"] = False
    return config


def make_reporter(reporter, log_dir, *, verbose: bool, dry_run: bool):
    """Ouvre `perf.log` (hors dry-run) et règle la verbosité de la CONSOLE.

    Le dossier est calculé par l'appelant : `build/<projet>/<tome>` côté light novel,
    `build/<projet>/<tome>/manga` côté manga.

    ⚠ Le fichier n'est plus conditionné à `--verbose` — il l'était, et c'était le trou
    d'observabilité du projet : un run de nuit lancé sans ce flag ne laissait **aucune trace
    fichier**, si bien qu'au matin plus rien ne disait quelle planche avait dérapé ni
    pourquoi. Les incidents (`warn`) partaient déjà dans ce fichier ; ils partaient donc nulle
    part 99 fois sur 100. Le flag ne pilote plus que ce qui s'IMPRIME : le fichier reçoit tout
    dans les deux cas, la console ne reçoit les lignes de perf que si on les a demandées."""
    if not dry_run:
        log_dir.mkdir(parents=True, exist_ok=True)
        reporter.set_verbose_log(log_dir / "perf.log")
    reporter.set_console_verbose(bool(verbose))
    return reporter


def afficher_liste(lister_projets, lister_tomes, src, build_root, projet: str | None,
                   *, sous_dossier: str = "", etat=None) -> None:
    """Rendu de `--list` : les tomes d'un projet, ou les projets disponibles.

    `sous_dossier` est le suffixe qui atteste qu'un tome est déjà généré — `""` côté light
    novel, `"manga"` côté manga, où les sorties vivent sous
    `build/<projet>/<tome>/manga/`.

    `etat` est un rappel `(projet, tome) -> (puce, detail)` qui REMPLACE le verdict par
    défaut. Celui-ci ne teste que l'existence du dossier de build : un tome arrêté à la
    planche 3 sur 150 s'y affiche « déjà généré », ce qui est inexploitable pour décider d'un
    run de nuit. La brique manga passe `manga.serie.etat_chapitre` ; le light novel passe
    `None` et son affichage ne bouge pas."""
    if projet:
        vols = lister_tomes(src, projet)
        if not vols:
            print(f"Aucun tome trouvé pour « {projet} » sous {src / projet}")
            return
        print(f"Tomes de « {projet} » :")
        if etat is not None:
            largeur = max(len(v) for v in vols)
            for v in vols:
                puce, detail = etat(projet, v)
                print(f"   {puce} {v.ljust(largeur)}" + (f"  {detail}" if detail else ""))
            return
        for v in vols:
            cible = build_root / projet / v
            if sous_dossier:
                cible = cible / sous_dossier
            built = cible.exists()
            print(f"   {'✓' if built else ' '} {v}" + ("  (déjà généré)" if built else ""))
        return
    projets = lister_projets(src)
    if not projets:
        print(f"Aucun projet trouvé sous {src}")
        return
    print("Projets disponibles :")
    for p in projets:
        print(f"   {p}  ({len(lister_tomes(src, p))} tome(s))")


# --------------------------------------------------------------------------- #
# Doctor : les sections communes aux deux diagnostics
# --------------------------------------------------------------------------- #

def section_ollama(config: dict, *, ecrire=print, brique: str = "socle"):
    """Bloc « — Ollama — » du doctor, identique des deux côtés (le manga lui passe une config
    dont la section `llm` est celle de sa brique).

    ⚠ **MISE À JOUR lot 36 (2026-09-06)** : rend une `diagnostic.Section`, plus un `bool`. Le
    texte, lui, n'a pas bougé d'un octet — `test_connection` écrit toujours au fil de l'eau,
    par le `ecrire` qu'on lui passe. C'était la contrainte : cette section met une douzaine de
    secondes contre un serveur arrêté, et une capture de `stdout` aurait laissé la console
    muette pendant tout ce temps.

    `brique` porte la PORTÉE du blocage : le serveur LLM appartient au socle — toute
    traduction en dépend, quelle que soit la brique."""
    from . import diagnostic as diag
    from .llm import test_connection
    entete = "\n— Ollama —"
    diag.dire(ecrire, entete)
    lignes: list[str] = []

    def _noter(ligne: str) -> None:
        lignes.append(ligne)
        if ecrire is not None:
            ecrire(ligne)

    joignable = test_connection(config, _noter)
    base = (config.get("llm") or {}).get("base_url", "(non défini)")
    # ⚠ **`diag.LLM` et non la brique appelante** (lot 39). Le serveur n'est pas une brique,
    # c'est une CAPACITÉ : classé `socle`, il bloquait les QUATRE briques — y compris pour un
    # `--from rendu`, que `gui/lanceur.py` décrit pourtant comme « relettrage seul, aucun appel
    # LLM ». La page Diagnostic annonçait donc « Aucune brique n'est utilisable en l'état » à
    # quelqu'un dont le relettrage marchait.
    #
    # ⚠ Le TEXTE console ne change pas d'un octet : `brique` n'est pas imprimé, et
    # `tests/test_core_diagnostic_iso.py` reste vert. Seule la PORTÉE du blocage change.
    if joignable:
        verdict = diag.Verdict("serveur_llm", diag.LLM, diag.CONFORME,
                               constat=f"serveur LLM joignable — {base}",
                               lignes_console=tuple(lignes))
    else:
        verdict = diag.Verdict(
            "serveur_llm", diag.LLM, diag.BLOQUANT,
            constat=f"serveur LLM injoignable — {base}",
            consequence="aucune traduction n'est possible ; la détection, le nettoyage et "
                        "l'OCR, eux, tourneraient.",
            geste="démarre Ollama (`ollama serve`) ou LM Studio, ou corrige llm.base_url "
                  "dans config.yaml. ⚠ Angelith ne démarre aucun service à ta place.",
            lignes_console=tuple(lignes))
    return diag.Section(entete, (verdict,))


def conclure(ok: bool) -> bool:
    print("\n" + ("✓ Tout est en ordre." if ok
                  else "❌ Au moins un point bloquant à corriger ci-dessus."))
    return bool(ok)


def section_dependances(modules: list[tuple[str, str]], indice: str, *, ecrire=print,
                        brique: str = "socle"):
    """Bloc « — Dépendances Python — » : `(module_importable, nom_pip)`.

    ⚠ Rend une `diagnostic.Section` depuis le lot 36 ; le texte est inchangé."""
    from . import diagnostic as diag
    return diag.section_dependances(modules, indice, brique=brique, ecrire=ecrire)


# --------------------------------------------------------------------------- #
# Anti-veille, préchargement/déchargement Ollama, extinction
# --------------------------------------------------------------------------- #

def models_in_config(config: dict, section: str | None = None) -> list[str]:
    """Liste dédoublonnée des identifiants de modèles utilisés (chaîne ou `{model: …}`)."""
    racine = config if section is None else (config.get(section) or {})
    out: list[str] = []
    for spec in (racine.get("modeles") or {}).values():
        m = spec["model"] if isinstance(spec, dict) else spec
        if m and m not in out:
            out.append(m)
    return out


def preparer_veille(actif: bool, message: str):
    """Désactive la mise en veille pour la durée du run. Renvoie l'inhibiteur à rendre à
    `finalize_power` (repli macOS/Linux), ou `None`."""
    if not actif:
        return None
    from . import power
    inhibitor = None
    if not power.keep_awake():
        inhibitor = power.start_inhibitor()      # repli macOS/Linux
    print(message)
    return inhibitor


def precharger_modeles(config: dict, models: list[str], *, dry_run: bool,
                       base_url: str | None = None) -> None:
    """Charge le(s) modèle(s) en mémoire AVANT de commencer, pour que la première unité de
    travail ne paie pas la latence de chargement (et pour échouer tôt et clairement si un
    modèle n'existe pas). Sauté en dry-run."""
    if dry_run or not models:
        return
    from . import power
    for m in models:
        power.ollama_load(base_url or config["llm"]["base_url"], m)


def unload_models(config: dict, models: list[str], *, base_url: str | None = None) -> None:
    """Décharge les modèles d'Ollama (libère la VRAM). Best-effort, sauté en dry-run."""
    if config.get("options", {}).get("dry_run") or not models:
        return
    from . import power
    for m in models:
        power.ollama_unload(base_url or config["llm"]["base_url"], m)


def shielded_unload(config: dict, models: list[str], *, base_url: str | None = None) -> None:
    """Décharge le(s) modèle(s) d'Ollama en IGNORANT SIGINT le temps de l'opération.
    Sans ce blindage, un Ctrl+C tardif/insistant pouvait interrompre le déchargement et
    laisser le modèle résident en VRAM — état relié à une chute PERSISTANTE du débit GPU
    au run suivant (le pilote AMD ROCm ne récupère proprement qu'au reboot). L'opération
    est rapide (une requête keep_alive:0 par modèle), donc la fenêtre où Ctrl+C est ignoré
    est brève. Le handler précédent est restauré ensuite pour que `finalize_power` garde
    son annulation d'extinction par Ctrl+C."""
    prev = None
    try:
        prev = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError, TypeError):
        prev = None      # pas sur le thread principal / plateforme sans SIGINT : on décharge quand même
    try:
        unload_models(config, models, base_url=base_url)
    finally:
        if prev is not None:
            try:
                signal.signal(signal.SIGINT, prev)
            except (ValueError, OSError, TypeError):
                pass


def finalize_power(args, inhibitor, interrupted: bool) -> None:
    """Extinction éventuelle, puis levée de l'anti-veille — dans CET ordre.

    ⚠ La veille n'est levée qu'à la toute fin, APRÈS que l'extinction soit programmée ET son
    délai écoulé : sinon Windows peut mettre le PC en veille pendant l'attente et figer le
    `shutdown /s`.

    On n'annule PAS l'extinction sur erreur (`interrupted` reste False) : ça éviterait au PC
    de tourner toute la nuit pour rien. Sur Ctrl+C (`interrupted=True`), pas d'extinction."""
    from . import power
    used_power = args.keep_awake or args.shutdown
    try:
        if args.shutdown and not interrupted:
            hint = power.shutdown(args.shutdown_delay)
            print(f"\n⏻ Extinction du PC programmée dans {args.shutdown_delay} s.")
            print(f"   Pour ANNULER : Ctrl+C ici, ou tape « {hint} » depuis un AUTRE terminal.")
            # On MAINTIENT le keep-awake pendant toute la fenêtre d'attente, +5 s de marge,
            # pour empêcher toute mise en veille qui figerait l'extinction. Le terminal est
            # donc bloqué par ce sleep (impossible d'y taper « shutdown /a » — d'où l'autre
            # terminal) : le SEUL moyen d'annuler ICI est Ctrl+C. Pendant l'attente on
            # remplace le handler SIGINT « arrêt de run » (qui exige 2 Ctrl+C et n'a plus de
            # sens ici, aucune unité de travail ne tourne) par le handler par défaut → UN
            # SEUL Ctrl+C lève KeyboardInterrupt et annule l'extinction. Handler restauré.
            import time
            prev = None
            try:
                prev = signal.getsignal(signal.SIGINT)
                signal.signal(signal.SIGINT, signal.default_int_handler)
            except (ValueError, OSError, TypeError):
                prev = None      # pas sur le thread principal : on attend quand même
            try:
                time.sleep(max(5, int(args.shutdown_delay)) + 5)
            except KeyboardInterrupt:
                cancel = power.cancel_shutdown()
                print(f"\nExtinction annulée{' (' + cancel + ')' if cancel else ''}.")
            finally:
                if prev is not None:
                    try:
                        signal.signal(signal.SIGINT, prev)
                    except (ValueError, OSError, TypeError):
                        pass
    finally:
        if used_power:
            power.release()
            power.stop_inhibitor(inhibitor)
