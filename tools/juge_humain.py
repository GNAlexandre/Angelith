#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le protocole en aveugle du `PLAN-29` L29.2 — **le seul juge opposable du dossier**.

    python tools/juge_humain.py "roman S" Vol.1 --paires 20   # prépare, présente, enregistre
    python tools/juge_humain.py "roman S" Vol.1 --paires 20   # relancé : REPREND où on s'est arrêté
    python tools/juge_humain.py "roman S" Vol.1 --rapport     # le tableau, et l'accord humain/automatique
    python tools/juge_humain.py "roman S" Vol.1 --rapport --markdown > docs/mesures/….md

## À quoi sert cet outil, et à quoi il ne sert pas

Le lot 25 a livré un juge automatique dont la probabilité de séparation vaut **0,68** sur
100 paires. Personne ne sait si 0,68 est un mauvais score, parce que **personne n'a jamais
mesuré ce qu'un humain fait sur les mêmes paires**. Le protocole en aveugle n'est pas un
recours en cas d'échec de l'automatique : il en est **l'étalon**.

Le produit de cet outil n'est donc pas « la voie A marche » — c'est un **accord**, en
pourcentage, entre un humain qui n'a vu aucune étiquette et un cosinus.

## Ce qu'il ne fait pas, et c'est volontaire

Il ne **génère rien** : il travaille sur des images déjà produites (`tools/banc_identite.py
--balayage`, ou l'atelier). Il ne charge de modèle **que** pour la colonne d'accord de
`--rapport`, et il s'en passe en le disant quand l'encodeur manque. Il n'écrit aucun PNG :
il **recopie octet pour octet** ceux qui existent — une réencodage effacerait le bloc `tEXt`
qui déclare l'image générée par IA, et la copie doit rester marquée comme l'originale.

## Les trois règles, et la première est celle qu'on viole toujours

1. **le seuil est fixé à la CRÉATION du protocole**, écrit dans `protocole.json`, et
   `--rapport` le lit de là. Il n'y a **pas** d'option `--seuil` à la lecture ;
2. **rien ne trahit la configuration** : les copies s'appellent `paire-07-A.png`, elles sont
   écrites dans un ordre tiré au sort — « un dossier trié par date suffit à trahir la
   configuration » — et la correspondance vit dans `protocole.json`, **à n'ouvrir qu'après
   avoir répondu** ;
3. **les réponses sont horodatées** et ajoutées à `reponses.jsonl`, en ajout seul. Se
   reprendre ajoute une ligne, n'en efface aucune.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core.cli import charger_config, configurer_stdout        # noqa: E402
from illustration import aveugle as aveugle_mod              # noqa: E402
from tools._banc_commun import tableau_markdown              # noqa: E402

#: Sous-dossier du protocole, sous le dossier d'illustrations du tome.
DOSSIER = "aveugle"

#: Sous-dossier des copies présentées à l'humain.
DOSSIER_IMAGES = "images"

#: Où l'outil cherche les images produites, faute de `--images`. C'est là que
#: `tools/banc_identite.py --balayage` écrit les siennes.
DOSSIER_BALAYAGE = "balayage"


# ─────────────────────────────  Trouver le matériel  ─────────────────────────────

#: Les champs du sidecar qui décrivent ce qui a fabriqué le prompt, dans l'ordre où ils
#: composent une étiquette de configuration. Ce sont **exactement** les clés que
#: `illustration/orchestrateur.py:_bloc_prompt` écrit — ne pas en inventer d'autres.
CHAMPS_CONFIGURATION = ("forme", "langue", "cadrage", "decor")


def candidats(dossier: Path) -> list[dict]:
    """Les images produites d'un dossier, avec leur **configuration**.

    L'étiquette vient du **nom du fichier**, que `tools/banc_identite.py --balayage` écrit
    d'après `Configuration.nom` (`force-r2-p6-g1-neutre`) : c'est déjà la configuration, axe
    compris, et rien ne la dit mieux.

    ⚠ **Le sidecar ne sert qu'aux images qui ne viennent PAS du balayage** — celles de
    l'atelier, nommées d'après le personnage. Deux portraits du même personnage porteraient
    alors la même étiquette, et le protocole les croirait de même configuration ; l'étiquette
    est donc construite depuis `prompt_source`, dont les champs disent ce qui a **réellement**
    fabriqué le prompt.

    ⚠ **Aucune heuristique ne distingue les deux cas, et il n'en faut pas** :
    `tools/banc_identite.py:_ecrire_image` ne passe **pas** de `prompt_source` à son
    manifeste, donc une image de balayage n'en porte aucun et retombe d'elle-même sur son nom.
    Deviner « est-ce un nom de balayage ? » sur la présence d'un tiret se serait trompé au
    premier personnage à deux mots — `_ardoise("Tory Noelle")` rend `tory-noelle`.

    ⚠ Les champs lus sont ceux que `_bloc_prompt` écrit, et pas d'autres : une clé inventée
    ici rendrait « configuration inconnue » sur toutes les images sans que rien ne le dise."""
    from illustration import marquage

    if not dossier.is_dir():
        return []
    sorties = []
    for image in sorted(dossier.glob("*.png")):
        source = _prompt_source(marquage.manifeste_de(image))
        etiquette = "-".join(str(source.get(c) or "") for c in CHAMPS_CONFIGURATION
                             if source.get(c))
        sorties.append({"image": str(image), "configuration": etiquette or image.stem})
    return sorties


def _prompt_source(sidecar: Path) -> dict:
    """Le bloc `prompt_source` d'un manifeste, ou `{}`. Un sidecar illisible n'est **pas** une
    erreur ici : il manque une étiquette, pas une image, et le nom du fichier reste."""
    if not sidecar.is_file():
        return {}
    try:
        return dict(json.loads(sidecar.read_text(encoding="utf-8")).get("prompt_source") or {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def reference_par_defaut(racine: Path) -> str:
    """La première référence préparée du tome, s'il y en a une.

    `illustration/identite.py:preparer` les écrit sous `references/`. Elle sert d'ancre à la
    question posée : « laquelle de ces deux images ressemble le plus à CELLE-CI ? » — sans
    elle, la question devient « laquelle préfères-tu », qui n'est pas la même mesure, et le
    rapport le dit."""
    dossier = racine / "references"
    if not dossier.is_dir():
        return ""
    images = sorted(p for p in dossier.iterdir()
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    return str(images[0]) if images else ""


# ─────────────────────────────  Créer le protocole  ─────────────────────────────

def creer(cible: Path, liste: list[dict], *, reference: str, seuil: int,
          graine: int, juge: dict) -> dict:
    """Écrit `protocole.json` **et les copies neutres**, puis rend le document.

    ⚠ **L'ordre d'écriture des copies est tiré au sort**, et ce n'est pas une coquetterie :
    un dossier trié par date de modification rendrait l'ordre des paires, donc l'ordre des
    configurations. La règle 2 du `PLAN-29` L29.2 le nomme explicitement."""
    import random

    doc = aveugle_mod.protocole(liste, reference=reference, seuil=seuil,
                               graine=graine, juge=juge)
    images = cible / DOSSIER_IMAGES
    images.mkdir(parents=True, exist_ok=True)

    copies = []
    for paire in doc["paires"]:
        for cote, cle in (("A", "gauche"), ("B", "droite")):
            nom = aveugle_mod.GABARIT_COPIE.format(n=paire["n"], cote=cote)
            copies.append((Path(paire[cle]), images / nom))
            paire[f"copie_{cote}"] = nom
    random.Random(int(graine) + 1).shuffle(copies)
    for source, destination in copies:
        # ⚠ Copie OCTET POUR OCTET, jamais un réencodage : le bloc `tEXt` qui déclare
        # l'image générée par IA voyage avec elle. Une copie passée par Pillow perdrait le
        # marquage, et la brique livrerait une image non marquée par une porte dérobée.
        #
        # ⚠ **`copyfile` et NON `copy2`, et c'est un test qui l'a montré.** `copy2` recopie
        # aussi les métadonnées, **date de modification comprise** : les copies héritaient
        # alors de la date de l'image d'origine, et un dossier trié par date rendait l'ordre
        # dans lequel le balayage avait généré — c'est-à-dire l'ordre des configurations.
        # Mélanger l'ordre d'écriture ne servait à rien tant que la date suivait le fichier.
        # C'est exactement la fuite que la règle 2 de L29.2 nomme.
        shutil.copyfile(source, destination)

    (cible / aveugle_mod.NOM_PROTOCOLE).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


# ────────────────────────────────  Interroger  ────────────────────────────────

def interroger(cible: Path, doc: dict, *, reprendre: bool = False) -> int:
    """Présente les paires sans réponse et enregistre. Rend le nombre de réponses ajoutées."""
    import time

    journal = cible / aveugle_mod.NOM_REPONSES
    deja = aveugle_mod.dernieres(aveugle_mod.lire_reponses(journal))
    images = cible / DOSSIER_IMAGES
    reference = doc.get("reference") or ""

    restantes = [p for p in doc["paires"]
                 if reprendre or int(p["n"]) not in deja]
    if not restantes:
        print(f"\n✅ Les {len(doc['paires'])} paires ont toutes une réponse. "
              f"→ python tools/juge_humain.py … --rapport")
        return 0

    print(f"\n{len(restantes)} paire(s) à juger. Réponses : "
          f"{' / '.join(aveugle_mod.REPONSES)} — « = » les deux se valent, « ? » je ne sais "
          f"pas (l'abstention SORT du dénominateur, elle ne compte pas contre).")
    if reference:
        print(f"   Référence, à garder ouverte : {reference}")
    else:
        print("   ⚠ Aucune image de référence : la question posée devient « laquelle "
              "préfères-tu ? », qui n'est PAS la même mesure que « laquelle lui ressemble "
              "le plus ? ». Le rapport le dira.")
    print(f"   Images : {images}\n")

    ajoutees = 0
    for paire in restantes:
        n = int(paire["n"])
        print(f"── paire {n}/{len(doc['paires'])}")
        print(f"   A : {images / paire.get('copie_A', '?')}")
        print(f"   B : {images / paire.get('copie_B', '?')}")
        depart = time.monotonic()
        choix = _demander()
        if choix is None:
            print("   (interrompu — les réponses déjà données sont conservées)")
            break
        aveugle_mod.ajouter(cible / aveugle_mod.NOM_REPONSES,
                            aveugle_mod.reponse(n, choix,
                                                secondes=time.monotonic() - depart))
        ajoutees += 1
    return ajoutees


def _demander() -> str | None:
    """Une réponse, ou `None` si l'humain interrompt. Aucune valeur par défaut : Entrée seul
    ne vaut pas « A », parce qu'une réponse au hasard vaut moins qu'une réponse en moins."""
    while True:
        try:
            brute = input(f"   → laquelle ? [{'/'.join(aveugle_mod.REPONSES)}] ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if brute.upper() in aveugle_mod.REPONSES:
            return brute.upper()
        print(f"     réponse attendue : {', '.join(aveugle_mod.REPONSES)}")


# ────────────────────────────────  Le rapport  ────────────────────────────────

def scores_automatiques(doc: dict, encodeur_chemin: str) -> tuple:
    """`({image: ressemblance à la référence}, motif)`. Le motif dit pourquoi c'est vide.

    ⚠ **Un encodeur absent rend `({}, motif)` et jamais des zéros.** Un accord calculé sur des
    scores nuls vaudrait 0 % et se lirait « l'humain et la machine ne sont jamais d'accord »,
    ce qui serait un chiffre faux plutôt qu'une absence de chiffre."""
    reference = doc.get("reference") or ""
    if not reference:
        return {}, ("aucune image de référence dans le protocole : il n'y a pas de "
                    "ressemblance à mesurer, donc pas d'accord à calculer")
    from illustration import juge as juge_mod
    encodeur = juge_mod.Encodeur(encodeur_chemin)
    if not encodeur.disponible():
        return {}, (f"encodeur absent ({encodeur_chemin}) : la colonne d'accord n'est pas "
                    f"mesurée. C'est une absence de mesure, pas un désaccord")
    try:
        vecteur_ref = encodeur.encoder(reference)
        table = {}
        for paire in doc["paires"]:
            for cle in ("gauche", "droite"):
                chemin = str(paire[cle])
                if chemin not in table and Path(chemin).is_file():
                    table[chemin] = juge_mod.cosinus(vecteur_ref, encodeur.encoder(chemin))
    except juge_mod.JugeIndisponible as err:
        return {}, f"le juge automatique n'a pas pu mesurer : {err}"
    return table, ""


def rendre(doc: dict, resultat: dict, motif_juge: str, *, markdown: bool) -> list[str]:
    """Le rapport, en lignes. Publiable tel quel avec `--markdown`."""
    accord = resultat["accord"]
    lignes = [
        "## Le protocole en aveugle — L29.2", "",
        f"- **Paires** : {resultat['paires']}, dont **{resultat['repondues']} répondues**",
        f"- **Seuil de succès, fixé à la création** : {resultat['seuil']} sur "
        f"{resultat['paires']} — protocole créé le `{doc.get('cree', '?')}`, "
        f"graine `{doc.get('graine')}`",
        f"- **Référence** : `{doc.get('reference') or '(aucune)'}`",
        "- **Accord humain / juge automatique** : "
        + (f"**{accord:.0%}** ({resultat['accord_oui']} sur {resultat['accord_n']} paires "
           f"où les deux se prononcent)" if accord is not None
           else f"**non mesuré** — {motif_juge or 'aucun score automatique'}"),
        "",
        f"**Verdict de configuration** : {resultat['motif']}.", "",
    ]
    if resultat["voix"]:
        lignes += [tableau_markdown(
            ["configuration", "voix"],
            [{"configuration": c, "voix": f"{v:g}"}
             for c, v in sorted(resultat["voix"].items(), key=lambda i: -i[1])]), ""]
    if markdown:
        lignes += [tableau_markdown(
            ["n", "réponse", "humain", "automatique", "d'accord"], resultat["detail"]), "",
            "⚠ **« humain » et « automatique » nomment un CÔTÉ, pas une configuration.** "
            "Publier la configuration ici rendrait le tableau inutilisable pour une seconde "
            "passe sur les mêmes images : elle est dans `protocole.json`.", ""]
    return lignes


# ────────────────────────────────  La commande  ────────────────────────────────

def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Protocole en aveugle (PLAN-29 L29.2) : l'étalon du juge automatique.")
    # ⚠ Un PROJET, pas un tome : les illustrations sont rangées par œuvre depuis la 2.19.0.
    ap.add_argument("projet")
    ap.add_argument("--paires", type=int, default=0, metavar="N",
                    help=f"prépare (si besoin) et présente N paires "
                         f"(défaut du plan : {aveugle_mod.PAIRES_DEFAUT})")
    ap.add_argument("--rapport", action="store_true",
                    help="le tableau et l'accord humain/automatique")
    ap.add_argument("--seuil", type=int, default=aveugle_mod.SEUIL_DEFAUT,
                    help=f"seuil de succès, écrit DANS le protocole à sa création "
                         f"(défaut {aveugle_mod.SEUIL_DEFAUT}). Sans effet sur --rapport, "
                         f"qui lit celui du fichier — c'est la règle 1 du plan")
    ap.add_argument("--graine", type=int, default=20260903)
    ap.add_argument("--images", default=None, metavar="DOSSIER",
                    help=f"où sont les images produites (défaut : illustrations/"
                         f"{DOSSIER_BALAYAGE})")
    ap.add_argument("--reference", default=None,
                    help="l'image de référence montrée à côté de chaque paire")
    ap.add_argument("--reprendre", action="store_true",
                    help="repose TOUTES les paires, y compris déjà répondues "
                         "(les anciennes réponses restent au journal)")
    ap.add_argument("--encodeur", default=None,
                    help="modèle ONNX du juge, pour la colonne d'accord")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    if not args.paires and not args.rapport:
        ap.error("choisis --paires N ou --rapport.")

    config = charger_config(args.config)
    from illustration.orchestrateur import dossier as dossier_illustrations
    racine = dossier_illustrations(config, args.projet)
    cible = racine / DOSSIER
    chemin_doc = cible / aveugle_mod.NOM_PROTOCOLE

    if args.paires:
        if chemin_doc.is_file():
            doc = aveugle_mod.verifier(json.loads(chemin_doc.read_text(encoding="utf-8")))
            print(f"→ protocole existant : {chemin_doc} "
                  f"({doc['sur']} paires, seuil {doc['seuil']})")
        else:
            source = Path(args.images) if args.images else racine / DOSSIER_BALAYAGE
            liste = candidats(source)
            if len(liste) < 2:
                print(f"❌ {source} ne porte pas deux images produites — rien à comparer.\n"
                      f"   → python tools/banc_identite.py \"{args.projet}\" <Tome> "
                      f"--balayage --personnage \"<nom>\"")
                return 1
            reference = (args.reference if args.reference is not None
                         else reference_par_defaut(racine))
            doc = creer(cible, aveugle_mod.paires(liste, nombre=args.paires,
                                                  graine=args.graine),
                        reference=reference, seuil=args.seuil, graine=args.graine,
                        juge={"encodeur": str(args.encodeur or "")})
            print(f"→ protocole écrit : {chemin_doc}\n"
                  f"   ⚠ NE L'OUVRE PAS avant d'avoir répondu : il porte la correspondance "
                  f"entre A/B et les configurations.")
        interroger(cible, doc, reprendre=args.reprendre)

    if args.rapport:
        if not chemin_doc.is_file():
            print(f"❌ {chemin_doc} n'existe pas — lance d'abord `--paires N`.")
            return 1
        doc = aveugle_mod.verifier(json.loads(chemin_doc.read_text(encoding="utf-8")))
        encodeur_chemin = args.encodeur or _encodeur_de(config)
        scores, motif = scores_automatiques(doc, encodeur_chemin)
        resultat = aveugle_mod.rapport(
            doc, aveugle_mod.lire_reponses(cible / aveugle_mod.NOM_REPONSES), scores)
        print("\n".join(rendre(doc, resultat, motif, markdown=args.markdown)))
    return 0


def _encodeur_de(config: dict) -> str:
    from illustration.orchestrateur import reglages
    encodeur = reglages(config)["identite"]["encodeur"]
    return str(Path(encodeur["dossier"]) / (encodeur["fichier"] or "(aucun)"))


if __name__ == "__main__":
    raise SystemExit(main())
