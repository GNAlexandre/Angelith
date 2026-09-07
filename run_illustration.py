#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Brique ILLUSTRATION — produire des images NEUVES à partir de la bible visuelle du tome.

⚠ **Expérimentale et désarmée par défaut.** Un utilisateur qui ne touche à rien ne voit aucune
différence : `illustration.actif: false` dans `config.yaml`, aucun poids téléchargé, aucune
seconde perdue au démarrage.

⚠ **Elle ne modifie aucune image de l'œuvre.** Elle lit `media/`, elle écrit des fichiers qui
n'existaient pas, dans `build/<Projet>/illustrations/` — et, pour ce qu'un humain a décidé de
GARDER, dans `sources/<Projet>/illustrations/`, qui survit à un `rm -r build/`. Le principe
« l'IA ne dessine jamais » porte sur les pixels de l'œuvre et reste vrai mot pour mot — c'est
vérifié à l'exécution par `illustration/frontiere.py` et par
`tests/test_illustration_frontiere.py`.

**Une seule commande suffit**, et elle pose ses questions :

  python run_illustration.py "Mon LN"        # l'ATELIER : il demande qui illustrer, montre
                                             # les images candidates, fait valider, génère

Le chemin scripté reste disponible, en deux phases avec un humain entre les deux :

  python run_illustration.py --check                       # environnement et poids
  python run_illustration.py "Mon LN" --phase prompt       # → requete.yaml
  #   … tu relis, tu corriges, tu écris ton nom, tu passes `valide` à true …
  python run_illustration.py "Mon LN" --phase image        # bascule VRAM + génération
  python run_illustration.py --rejouer chemin/vers/x.png.provenance.json

La galerie, en ligne de commande (le bouton équivalent est dans l'onglet « Atelier ») :

  python run_illustration.py "Mon LN" --inventaire         # combien, où, et quel poids
  python run_illustration.py "Mon LN" --garder build/…/x.png   # → sources/…/illustrations/
  python run_illustration.py "Mon LN" --jeter  build/…/y.png   # → rejetees/, PAS supprimée
  python run_illustration.py "Mon LN" --purger             # supprime les rejetées, sur o/N

⚠ **Une ŒUVRE, pas un tome.** Les références d'un personnage vivent où l'éditeur les a mises —
sur le corpus de mesure, 7 des 10 références validées sont dans un autre volume que le
premier. La brique lit donc tous les tomes et écrit dans `build/<Projet>/illustrations/`. Un
tome peut être nommé pour RESTREINDRE la lecture ; il ne change pas où l'on écrit.

⚠ **Aucune image n'existe sans qu'un humain ait validé son prompt.** En mode scripté c'est
`valide: true` dans `requete.yaml` ; dans l'atelier c'est une question à l'écran, à laquelle
il faut répondre et qui inscrit le nom du répondant dans le sidecar de chaque image. Il n'y a
aucune clé de configuration pour contourner cette porte, et aucun mode « tout automatique ».
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import cli
from core.version import ETAT_BRIQUES, __version__
from illustration import gabarits

cli.configurer_stdout()

PHASES = ["prompt", "image"]


def _attendues() -> tuple:
    """Les erreurs qui décrivent une SITUATION, pas une panne — importées tard pour que
    `--version` et `--check` n'aient pas à charger la brique."""
    from illustration.comfyui import ComfyIndisponible
    from illustration.frontiere import EcritureHorsPerimetre, ImageNonMarquee
    from illustration.marquage import MarquageImpossible
    from illustration.moteur import CanalExige, CanalRefuse
    from illustration.orchestrateur import BriqueInactive
    from illustration.poids import PoidsIntrouvable
    from illustration.requete import RequeteNonValidee
    return (RequeteNonValidee, BriqueInactive, CanalRefuse, CanalExige, ComfyIndisponible,
            MarquageImpossible, PoidsIntrouvable, EcritureHorsPerimetre, ImageNonMarquee,
            FileExistsError, FileNotFoundError, ValueError)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Atelier d'illustration (brique ILLUSTRATION, expérimentale).")
    ap.add_argument("projet", nargs="?", help="dossier projet sous sources/")
    ap.add_argument("tome", nargs="?",
                    help="RESTREINT la lecture à ce tome (ex. Vol.1). Par défaut, l'œuvre "
                         "entière est lue — la sortie va dans build/<Projet>/illustrations/ "
                         "quoi qu'il arrive")
    ap.add_argument("--version", action="version",
                    version=f"Angelith {__version__} "
                            f"(brique illustration : {ETAT_BRIQUES['illustration']})")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--phase", choices=PHASES, default=None,
                    help="prompt : écrit requete.yaml · image : génère les PNG marqués. "
                         "⚠ ce n'est PAS --from : aucune étape n'est invalidée en amont")
    ap.add_argument("--ecraser", action="store_true",
                    help="--phase prompt : réécrit requete.yaml même s'il existe (perd ta "
                         "relecture)")
    ap.add_argument("--graine", type=int, default=0, metavar="N",
                    help="--phase prompt : graine écrite dans la requête")
    ap.add_argument("--personnage", action="append", metavar="NOM", default=None,
                    help="--phase prompt : restreint aux personnages nommés (répétable)")
    # ⚠ Les trois suivants SURCHARGENT `illustration.prompt.*` pour un run, sans toucher à
    # config.yaml — c'est ce qui rend un balayage possible sans réécrire un fichier de 95 Ko
    # dont l'essentiel est de la prose commentée (interdit n° 5).
    ap.add_argument("--cadrage", choices=["visage", "buste", "pied"], default=None,
                    help="--phase prompt : le cadrage du portrait (défaut : "
                         "illustration.prompt.cadrage)")
    ap.add_argument("--forme", choices=list(gabarits.FORMES), default=None,
                    help="--phase prompt : la forme du champ texte. Laquelle gagne est une "
                         "MESURE de ce dépôt sur son corpus, pas un héritage")
    ap.add_argument("--langue-prompt", choices=list(gabarits.LANGUES), default=None,
                    help="--phase prompt : la langue du prompt envoyé au MODÈLE D'IMAGE — "
                         "ce n'est pas langues.cible")
    ap.add_argument("--rejouer", metavar="PROVENANCE.JSON", default=None,
                    help="rejoue une requête archivée et dit si le PNG est identique")
    ap.add_argument("--telecharger", action="store_true",
                    help="--check : autorise le téléchargement des poids (plusieurs Go)")
    ap.add_argument("--check", action="store_true", help="diagnostic de l'environnement")
    ap.add_argument("--liberer-vram", action="store_true",
                    help="demande à ComfyUI de rendre la carte (POST /free). ⚠ Ce n'est PAS "
                         "le chemin nominal : illustration.vram.decharger_image reste false")
    ap.add_argument("--repetitions", type=int, default=1, metavar="N",
                    help="--liberer-vram : répète l'appel N fois en sondant le serveur entre "
                         "chaque, pour relever le TAUX D'ÉCHEC de /free (PLAN-30 L30.4, qui "
                         "en demande 20). N'arme rien : le chiffre se lit, la décision "
                         "s'écrit dans config.yaml")
    # LOT 27 — la galerie en ligne de commande. Le plan demande « une commande et un bouton » ;
    # voici la commande, le bouton est dans l'onglet « Atelier » de gui.py.
    ap.add_argument("--inventaire", action="store_true",
                    help="combien d'images, dans quel état, et ce qu'elles pèsent")
    ap.add_argument("--garder", metavar="IMAGE.PNG", default=None,
                    help="déplace une image ET son sidecar sous sources/<Projet>/"
                         "illustrations/, qui survit à un `rm -r build/`")
    ap.add_argument("--jeter", metavar="IMAGE.PNG", default=None,
                    help="déplace dans rejetees/. Ne supprime rien : un rejet est une donnée")
    ap.add_argument("--purger", action="store_true",
                    help="supprime les images REJETÉES, après avoir dit ce que ça détruit")
    ap.add_argument("--oui", action="store_true",
                    help="--purger : ne pas demander confirmation (pour un script)")
    ap.add_argument("--par", default=None, metavar="NOM",
                    help="atelier : le nom inscrit dans `validation.par`, donc dans le "
                         "sidecar de chaque image. Demandé à l'écran s'il manque")
    args = ap.parse_args()

    config = cli.charger_config(args.config)

    if args.check:
        cli.avertir_config(config)
        sys.exit(0 if _diagnostic(config, telecharger=args.telecharger) else 1)

    if args.liberer_vram:
        sys.exit(0 if _liberer_vram(config, args.repetitions) else 1)

    try:
        _executer(args, config)
    except _attendues() as err:
        # ⚠ Ces situations ne sont PAS des pannes : « personne n'a validé le prompt », « la
        # brique est désarmée », « le workflow ne porte pas ce canal ». Chacune porte déjà un
        # message qui dit quoi faire ; une trace de pile par-dessus n'apprendrait rien et
        # ferait passer un garde-fou pour un bug.
        sys.exit(str(err))


def _executer(args, config: dict) -> None:
    from illustration import orchestrateur

    if args.inventaire or args.purger or args.garder or args.jeter:
        _galerie(args, config)
        return

    if args.rejouer:
        # ⚠ Le code de sortie reste 0 même quand les deux PNG diffèrent. Un backend de
        # diffusion non déterministe est le cas FRÉQUENT, pas une panne : en faire un échec
        # de commande apprendrait à ignorer le code de sortie. L'écart est dit en clair.
        orchestrateur.rejouer(args.rejouer, config)
        return

    if not args.phase:
        # ⚠ **Le défaut est l'ATELIER**, pas un message d'erreur. Le chemin en deux phases
        # reste entier derrière `--phase` ; il est fait pour être scripté, pas pour être la
        # première chose qu'on découvre.
        from illustration import console
        console.atelier(args, config)
        return

    if not args.projet:
        sys.exit("Précise un projet : run_illustration.py \"Mon LN\" --phase prompt")

    if args.phase == "prompt":
        orchestrateur.phase_prompt(args.projet, config, tome=args.tome, graine=args.graine,
                                   personnages=args.personnage, ecraser=args.ecraser,
                                   cadrage=args.cadrage, forme=args.forme,
                                   langue=args.langue_prompt)
    else:
        recap = orchestrateur.phase_image(args.projet, config, tome=args.tome,
                                          chemin_config=args.config)
        print(f"\n{args.projet} : {len(recap['images'])} image(s) générée(s)")
        print(f"Rapport : {Path(recap['dossier']) / 'RAPPORT.md'}")
        print("⚠ Ces images ne font pas partie de l'œuvre. Chacune porte son marquage et son "
              "manifeste de provenance.")


def _galerie(args, config: dict) -> None:
    """`--inventaire`, `--garder`, `--jeter`, `--purger` — **L27.3 et L27.5**.

    ⚠ **Garder DÉPLACE, et l'endroit change de nature.** `build/` est régénérable par contrat
    (`.gitignore` l'écrit, et le dépôt recommande lui-même un `rm -r build/` après un
    MAJEUR) ; une image produite en 103,7 s de GPU et retenue par un humain ne l'est pas. Les
    images retenues vont donc sous `sources/<Projet>/illustrations/`, avec le travail écrit à
    la main.

    ⚠ **Jeter ne supprime pas.** Un rejet est une donnée : le `PLAN-25` L25.4 en a besoin
    pour mesurer. La purge existe, elle est un geste séparé, et elle annonce ce qu'elle
    détruit avant de le détruire."""
    from illustration import galerie as galerie_mod
    from illustration import orchestrateur

    orchestrateur.exiger_actif(config)
    if not args.projet:
        sys.exit("Précise un projet : run_illustration.py \"Mon LN\" --inventaire")
    projet = args.projet
    candidates = orchestrateur.dossier(config, projet)
    retenues = orchestrateur.dossier_retenues(config, projet)
    rejetees = orchestrateur.dossier_rejetees(config, projet)

    if args.garder:
        image, manifeste = galerie_mod.garder(args.garder, retenues)
        print(f"Gardée : {image}")
        print(f"  manifeste : {manifeste}")
        print("  ⚠ Elle survit désormais à un `rm -r build/`. Elle n'est PAS pour autant "
              "candidate au conditionnement d'une génération suivante — voir "
              "illustration/galerie.py §3.")
    if args.jeter:
        cible, _ = galerie_mod.jeter(args.jeter, rejetees)
        print(f"Jetée (conservée) : {cible}")
    if args.purger:
        combien, octets = galerie_mod.poids_a_purger(rejetees)
        if not combien:
            print("Aucune image rejetée à purger.")
        else:
            print(f"{combien} image(s) rejetée(s) et leur manifeste vont être SUPPRIMÉS "
                  f"({galerie_mod.octets_lisibles(octets)}).")
            print("  Un rejet est une donnée : le lot 25 s'en sert pour mesurer.")
            if args.oui or input("  Confirmer ? [o/N] ").strip().lower() in ("o", "oui"):
                nombre, libres = galerie_mod.purger(rejetees)
                print(f"  {nombre} supprimée(s), {galerie_mod.octets_lisibles(libres)} "
                      f"libérés.")
            else:
                print("  Annulé, rien n'a été supprimé.")

    inventaire = galerie_mod.inventorier(candidates, retenues)
    print("")
    print(f"Galerie de « {projet} »")
    print(f"  candidates : {candidates}")
    print(f"  retenues   : {retenues}")
    for ligne in inventaire.resume():
        print("  " + ligne)
    print("")
    print("Ce qu'une œuvre entière pèserait :")
    for ligne in galerie_mod.calcul_du_poids():
        print("  " + ligne)


def _liberer_vram(config: dict, repetitions: int = 1) -> bool:
    """`POST /free` sur ComfyUI, et le **taux d'échec** quand on le répète — `PLAN-30` L30.4.

    ## Pourquoi cette commande existe, et pourquoi elle n'arme rien

    `illustration.vram.decharger_image` est **désarmé** depuis la 2.16.0, pour une raison
    mesurée : sur SEPT appels à `/free` le 2026-08-29, UN a fait segfauter ComfyUI. Sept n'est
    pas un dénominateur, et `docs/COMMANDES.fr.md` disait jusqu'ici de faire l'appel **à la
    main**, au `curl`. Le geste manuel ne se compte pas : il n'a produit aucun second relevé
    en quatre jours.

    Cette commande fait exactement le même appel, et **compte**. Elle sonde le serveur entre
    deux appels, parce que le mode d'échec est la mort du serveur et non une erreur HTTP —
    voir `illustration.vram.mesurer_free`.

    ⚠ **Elle ne change aucune valeur de `config.yaml`.** Le chiffre se lit, la décision
    s'écrit à la main. C'est la même division que partout ici : le dépôt livre désarmé ce que
    la mesure ne soutient pas, et c'est un humain qui arme.

    ⚠ **Elle ne relance pas ComfyUI** si l'appel le tue : le `PLAN-30` L30.4 l'interdit —
    « Angelith ne pilote pas le cycle de vie d'un programme que l'utilisateur a installé »."""
    from illustration import sonde as sonde_mod
    from illustration import vram as vram_mod
    from illustration.comfyui import MoteurComfyUI
    from illustration.orchestrateur import reglages

    reg = reglages(config)
    base_url = reg["comfyui"]["base_url"]
    depart = sonde_mod.depuis_config(config)
    if not depart.joignable:
        print(f"ComfyUI est injoignable sur {base_url} : il n'y a pas de carte à rendre.")
        print(f"  {depart.erreur}")
        return False
    avant = depart.appareil_principal
    if avant is not None:
        print(f"Avant : {sonde_mod.mio(avant.vram_libre)} Mio libres sur "
              f"{sonde_mod.mio(avant.vram_total)} — ComfyUI {depart.version or '?'}")
    # ⚠ `workflow=None` est VOULU, et ce n'est pas un raccourci : rendre la carte n'exécute
    # aucun graphe — `decharger()` ne touche qu'au transport, `POST /free`. Passer le graphe
    # configuré ferait échouer « rends-moi la VRAM » parce qu'un fichier JSON est mal formé,
    # ce qui est exactement le mauvais moment pour refuser.
    # ⚠ 2.24.1 — cette ligne ne passait AUCUN premier argument, et `workflow` est positionnel
    # obligatoire : `--liberer-vram` mourait sur un `TypeError` avant le premier appel, depuis
    # sa naissance en 2.24.0. Relevé le 2026-09-03 au premier lancement contre un vrai serveur
    # (`docs/mesures/canaux-2026-09-03.md` §12.1).
    moteur = MoteurComfyUI(None, base_url=base_url, timeout=reg["comfyui"]["timeout"])
    releve = vram_mod.mesurer_free(
        liberer=moteur.decharger,
        vivant=lambda: sonde_mod.depuis_config(config).joignable,
        repetitions=repetitions, version=depart.version)
    apres = sonde_mod.depuis_config(config)
    fin = apres.appareil_principal
    if fin is not None:
        print(f"Après : {sonde_mod.mio(fin.vram_libre)} Mio libres sur "
              f"{sonde_mod.mio(fin.vram_total)}")
    print("")
    print(releve.phrase())
    if repetitions > 1:
        print(f"  → reporte ce couple dans docs/mesures/, avec la version de ComfyUI. "
              f"`illustration.vram.decharger_image` reste à "
              f"{str(reg['vram']['decharger_image']).lower()} tant qu'un humain ne l'a pas "
              f"changé.")
    return not releve.arret_au


def _diagnostic(config: dict, *, telecharger: bool = False) -> bool:
    from illustration import orchestrateur
    from illustration.poids import PoidsIntrouvable, assurer_poids

    print(f"Angelith {__version__} "
          f"(brique illustration : {ETAT_BRIQUES['illustration']}) — diagnostic\n")
    reg = orchestrateur.reglages(config)
    ok = cli.section_dependances([("PIL", "pillow"), ("yaml", "pyyaml")],
                                "pip install -r requirements.txt")

    print(f"\nBrique : {'ARMÉE' if reg['actif'] else 'désarmée (illustration.actif: false)'}")
    if not reg["actif"]:
        print("  C'est le défaut livré. Rien ne sera généré tant que la clé n'est pas à true.")
    print(f"Moteur : {reg['moteur']}"
          + ("  — aucun poids, aucun GPU ; il sert à vérifier la chaîne, pas à illustrer"
             if reg["moteur"] == "factice" else ""))

    if reg["moteur"] == "comfyui":
        ok = _diagnostic_comfy(reg) and ok

    fichier = reg["poids"]["fichier"]
    if not fichier:
        print("\nPoids : aucun fichier déclaré (illustration.poids.fichier vide).")
        print("  ⚠ Aucune URL n'est codée en dur dans le dépôt : la licence des POIDS se "
              "vérifie à la source primaire, et « code Apache-2.0 » ne dit rien des poids.")
        print("  Voir illustration_models/README.md — tableau des candidats, daté et sourcé.")
    else:
        chemin = Path(reg["poids"]["dossier"]) / fichier
        try:
            trouve = assurer_poids(
                chemin, url=reg["poids"]["url"],
                auto=telecharger or reg["poids"]["telechargement_auto"],
                sha256=reg["poids"]["sha256"] or None, dire=print)
            taille = trouve.stat().st_size
            print(f"\nPoids : {trouve} ({taille / 1e9:.1f} Go)")
        except PoidsIntrouvable as err:
            print(f"\nPoids : {err}")
            ok = False

    ok = _diagnostic_identite(reg) and ok
    _diagnostic_prompt(reg)

    _diagnostic_attente()
    _diagnostic_insertion(reg)

    sources = Path(config["chemins"]["sources"])
    print(f"\nSources : {sources} " + ("(présent)" if sources.is_dir() else "INTROUVABLE"))
    print("\n⚠ Rappel : aucune image n'est produite sans qu'un humain ait validé son prompt "
          "dans requete.yaml. La phase image refuse `valide: false`.")
    return cli.conclure(ok)


def _diagnostic_attente() -> None:
    """Le chiffre de l'étape 0.1 du `PLAN-27`, et la tranche d'interface qu'il impose.

    ⚠ Il est publié **ici** et pas seulement dans un document de mesure, parce que c'est lui
    qui explique pourquoi l'interface se comporte comme elle se comporte : « run par lot »
    n'est pas un choix de goût, c'est ce que 103,7 s par image imposent."""
    from illustration import attente

    print("\nAttente (PLAN-27 étape 0.1) — le chiffre qui décide de la forme de l'atelier :")
    for ligne in attente.resume():
        print("  " + ligne)


def _diagnostic_insertion(reg: dict) -> None:
    """L27.4 — l'insertion dans les sorties du light novel, et ses quatre garde-fous."""
    from core import insertion as insertion_mod
    from illustration import galerie as galerie_mod

    arme = reg["inserer_dans_sorties"]
    print("\nInsertion dans les sorties (PLAN-27 L27.4) : "
          + ("ARMÉE" if arme else "désarmée (illustration.inserer_dans_sorties: false)"))
    if not arme:
        print("  C'est le défaut livré : un tome relancé sans que tu aies rien demandé sort "
              "ISO-OCTET. Elle ne concerne que le light novel (`run.py`).")
    else:
        position = reg["insertion"]["position"]
        print(f"  Position : « {position} » — "
              f"{insertion_mod.LIBELLES_POSITION.get(position, 'INCONNUE, repli sur le début de chapitre')}")
        print(f"  Légende (non désactivable) : « {insertion_mod.LEGENDE_FR} »")
        print("  ⚠ Elle n'a pas d'interrupteur : `core/insertion.py` lève sur une légende "
              "vide. Son texte vient du pack de langue CIBLE.")
        print("  RAPPORT.md listera chaque image insérée, avec son personnage et sa graine.")
    print("\nPoids sur le disque, si tu illustres toute une œuvre :")
    for ligne in galerie_mod.calcul_du_poids():
        print("  " + ligne)


def _diagnostic_prompt(reg: dict) -> None:
    """Ce que la phase 1 fera — **avant** de la lancer, et sans rien charger.

    ⚠ Le point qui mérite d'être lu : `style` et `ancrages_max`. Un utilisateur qui lit
    « style: mots » sur un tome dont `bible.style.mots` est VIDE croirait que le registre
    graphique est traité. Il ne l'est pas, et le diagnostic le dit plutôt que de le laisser
    supposer."""
    from illustration import gabarits as gabarits_mod

    invite = reg["prompt"]
    print(f"\nPrompt (PLAN-26) : forme « {invite['forme']} », langue « {invite['langue']} », "
          f"cadrage « {invite['cadrage']} », gabarit « {invite['gabarit']} »")
    print(f"  Empreinte du gabarit : {gabarits_mod.empreinte(invite['gabarit'])[:16]}… "
          f"— elle part dans le sidecar de chaque image, parce qu'un gabarit nommé mais "
          f"édité depuis produirait un autre prompt sous le même nom.")
    print(f"  Références d'identité : {invite['references_max']} au plus — plafond MESURÉ au "
          f"lot 25 (« la rupture est entre 1 et 2, pas entre 2 et 3 »).")
    if invite["style"] == "ancrages" and invite["ancrages_max"] > 0:
        print(f"  Style : {invite['ancrages_max']} ancre(s) sur le canal d'images.")
        print("    ⚠ Préfère une ancre SANS visage : une ancre qui montre quelqu'un peut le "
              "faire apparaître dans l'image produite.")
    else:
        print(f"  Style : « {invite['style']} » — l'approche par ANCRAGES est DÉSARMÉE "
              f"(ancrages_max: {invite['ancrages_max']}).")
        if invite["style"] == "mots":
            print("    Les mots viennent de `bible.style.mots` (écrit à la main) PUIS de la "
                  "signature MESURÉE du tome, mise en mots — « en noir et blanc, palette "
                  "désaturée, trait marqué ». Mesuré le 2026-08-30 : c'est ce qui fait "
                  "basculer le régime de couleur du bon côté.")
            print("    ⚠ Un tome sans illustration exploitable n'a pas de signature, et cette "
                  "approche n'ajoute alors aucun mot : `python tools/bible.py --tous` le dit.")
    if invite["llm"]["actif"]:
        print(f"  Choix des images : par le MODÈLE DE VISION "
              f"({invite['llm']['modele'] or 'modeles.traducteur'}), un appel par image.")
    else:
        print("  Choix des images : DÉTERMINISTE (illustration.prompt.llm.actif: false) — "
              "reproductible sans serveur, et c'est le défaut.")
    print(f"  Budget : {reg['budget']['images_par_run']} image(s) par run au plus, motif "
          f"d'arrêt nommé dans RAPPORT.md.")


def _diagnostic_identite(reg: dict) -> bool:
    """La voie A du `PLAN-25` : son état, son juge, et **ses planchers ou leur absence**.

    ⚠ Un juge sans planchers étalonnés n'est pas un juge à moitié : il ne se prononce sur
    rien. Le dire ici évite qu'un utilisateur lise « encodeur : présent » et en conclue que
    ses images sont jugées."""
    from illustration.juge import Encodeur

    ident = reg["identite"]
    print("\nIdentité (PLAN-25, voie A) : "
          + ("ARMÉE" if ident["actif"] else "désarmée (illustration.identite.actif: false)"))
    if not ident["actif"]:
        print("  C'est le défaut livré, et c'est une MESURE qui le décide : sur le corpus de "
              "référence, le juge ne sépare « même personnage » de « personnages différents » "
              "que 68 fois sur 100. Voir docs/mesures/identite-2026-08-29.md.")
        return True

    fichier = ident["encodeur"]["fichier"]
    if not fichier:
        print("  ⚠ Aucun encodeur déclaré (illustration.identite.encodeur.fichier vide) : les "
              "images seront produites, et leur sidecar portera `juge_indisponible`.")
        print("  Aucune URL n'est codée en dur ici non plus — voir "
              "illustration_models/README.md.")
        return True
    chemin = Path(ident["encodeur"]["dossier"]) / fichier
    encodeur = Encodeur(chemin, agregation=ident["encodeur"]["agregation"],
                        cadrage=ident["encodeur"]["cadrage"], cote=ident["encodeur"]["cote"])
    present = encodeur.disponible()
    print(f"  Juge : {chemin} — " + ("présent" if present else "INTROUVABLE (ou onnxruntime "
                                     "manquant : pip install -r requirements-manga.txt)"))
    print(f"  Réglages : cadrage {encodeur.cadrage}, côté {encodeur.cote}, agrégation "
          f"{encodeur.agregation}")
    planchers = ident["planchers"]
    etalonnes = [c for c in ("confusion", "nouveaute", "style_descripteurs")
                 if planchers[c] is not None]
    if etalonnes:
        print("  Planchers étalonnés : "
              + ", ".join(f"{c} = {planchers[c]:.4f}" for c in etalonnes))
    else:
        print("  ⚠ AUCUN plancher étalonné : les trois grandeurs seront mesurées et écrites, "
              "mais aucun verdict ne sera rendu — un seuil absent ne se prononce pas.")
        print("  → python tools/banc_identite.py \"<Projet>\" --etalonnage")
    if not planchers["juge_utilisable"]:
        print("  ⚠ `juge_utilisable: false` : les verdicts seront marqués « non opposables ».")
    return present


def _diagnostic_comfy(reg: dict) -> bool:
    """L'état du serveur, du graphe, et **le refus avant le GPU** — `PLAN-28` L28.2.

    ⚠ **Tout ce qui est vérifié ici l'est AVANT le déchargement du LLM.** C'est la raison
    d'être du lot : un nœud absent, un modèle renommé ou un guidage incompatible se
    découvraient jusqu'ici au premier appel, c'est-à-dire après avoir rendu la carte et chargé
    12,84 Go de poids — donc au pire moment. Le §9 de `docs/procedures/comfyui.md` en liste
    onze cas mesurés ; cinq se voient dans le fichier ou en une requête de lecture.

    ⚠ **Chaque refus porte sa correction, pas seulement son constat.** C'est le standard que
    `tests/test_config_valide.py` a posé — « le message dit quoi coller »."""
    from illustration.comfyui import ComfyIndisponible, MoteurComfyUI

    workflow = reg["comfyui"]["workflow"]
    if not workflow:
        print("  ⚠ illustration.comfyui.workflow est vide : le dépôt ne fournit AUCUN graphe.")
        print("    Exporte le tien depuis ComfyUI au format API et place ses marqueurs "
              "(%prompt%, %graine%, %reference_1%…) là où ils doivent aller.")
        return False
    try:
        moteur = MoteurComfyUI(workflow, base_url=reg["comfyui"]["base_url"],
                               timeout=reg["comfyui"]["timeout"])
    except ComfyIndisponible as err:
        print(f"  ⚠ {err}")
        return False
    canaux = ", ".join(sorted(moteur.CANAUX_SUPPORTES)) or "(aucun)"
    print(f"  Workflow : {workflow}\n  Canaux honorés : {canaux}")
    # ⚠ Le croisement compte plus que les deux listes séparées : un utilisateur qui lit
    # « identité : ARMÉE » puis « canaux honorés : prompt, prompt_negatif » ne fait pas
    # forcément le rapprochement — et il ne l'apprendra qu'à la fin d'une session d'atelier.
    from illustration import atelier as atelier_mod
    for canal in atelier_mod.canaux_manquants(reg, moteur.CANAUX_SUPPORTES):
        print(f"  ⚠ Le canal « {canal} » est ARMÉ mais ce workflow ne l'honore pas.")
        print("    " + atelier_mod.remede_canal(canal, workflow).replace("\n", "\n  "))
    if moteur.MOTIFS:
        print("  Canaux REFUSÉS (et ils le seront explicitement, pas en silence) : "
              + ", ".join(sorted(moteur.MOTIFS)))
    print(f"  Plancher anti-cache : {reg['comfyui']['plancher_secondes']:.0f} s"
          + ("  — DÉSARMÉ : une réponse instantanée de ComfyUI ne sera pas refusée"
             if reg["comfyui"]["plancher_secondes"] <= 0 else
             "  — sous ce temps, une « génération » est le cache d'exécution de ComfyUI"))
    return _diagnostic_validation(reg, workflow)


def _diagnostic_validation(reg: dict, workflow: str) -> bool:
    """La sonde, les cinq vérifications, et la VRAM — tout ce que L28.2 exige de refuser."""
    from illustration import sonde as sonde_mod
    from illustration import validation as validation_mod

    releve = sonde_mod.sonder(reg["comfyui"]["base_url"])
    print("")
    for ligne in releve.resume():
        print("  " + ligne)
    if not releve.joignable:
        print("  ⚠ Les vérifications « nœud absent » et « modèle absent » sont NON FAITES — "
              "pas passées. Un serveur éteint ne prouve rien sur un graphe.")
    rapport = validation_mod.valider(workflow, releve=releve, pas=reg["image"]["pas"],
                                     guidage=reg["image"]["guidage"])
    print("\n  Validation du graphe (avant le GPU, PLAN-28 L28.2) :")
    for nom, etat in rapport.verifications.items():
        print(f"    {nom} : {etat}")
    for constat in rapport.constats:
        for ligne in constat.lignes():
            print("    " + ligne)
    # ⚠ La VRAM se dit ICI, et pas au moment de générer : « il manque 2 Go » annoncé après le
    # déchargement du LLM arrive une fois la carte déjà rendue et le mal déjà fait.
    vram = validation_mod.verifier_vram(releve)
    for constat in vram:
        for ligne in constat.lignes():
            print("    " + ligne)
    refuse = bool(rapport.refus) or any(c.gravite == "refus" for c in vram)
    if refuse:
        print("    ⚠ Ces refus tombent AVANT le déchargement du LLM : rien n'a été rendu, "
              "rien n'a été chargé, la carte est intacte.")
    return bool(releve.joignable) and not refuse


if __name__ == "__main__":
    main()
