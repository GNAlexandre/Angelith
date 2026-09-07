#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Voir ce que le projet envoie à ComfyUI — la sonde, le validateur, le graphe — `PLAN-28`.

## Le problème, dit par l'utilisateur

« La construction et le déploiement du système d'image se fait au travers du projet sans que
je puisse avoir une réelle vision sur ce dernier. » Ce n'est pas un problème de confort : un
pipeline qu'on ne peut pas inspecter ne peut pas être débogué, et une mesure qu'on ne peut pas
rejouer à la main n'est pas une mesure.

## Cinq sous-commandes, et **aucune ne génère**

```powershell
python tools/comfy.py --sonde                       # version, VRAM, nœuds, listes de modèles
python tools/comfy.py --valider <workflow.api.json> # avant le GPU : format, nœuds, modèles, sortie
python tools/comfy.py --graphe <requete.yaml>       # le graphe SUBSTITUÉ, écrit, non envoyé
python tools/comfy.py --diff <a.json> <b.json>      # ce qui change entre deux graphes
python tools/comfy.py --journal                     # le dernier run : temps, VRAM, lignes clés
```

⚠ **Cet outil est en LECTURE.** Il n'appelle que `GET /system_stats`, `GET /object_info` et
`GET /internal/logs/raw`. Générer reste le travail de `run_illustration.py`, qui porte la
porte humaine et le marquage : un outil capable de générer sans passer par cette porte serait
une **seconde porte, non gardée**. `tests/test_tools_comfy.py` le vérifie en comptant les
requêtes que chaque sous-commande envoie à un serveur factice.

## Ce que `--graphe` rend, et pourquoi c'est lui qui donne la vision

Il écrit le JSON **exactement tel qu'il partirait** : marqueurs substitués, nœuds élagués,
noms des images de référence tels que ComfyUI les connaîtra. Les références ne sont **pas**
téléversées — leur nom est calculé depuis l'empreinte de leur contenu, ce qui est justement ce
qui rend le graphe reproductible — et le récapitulatif dit lesquelles le seraient.

Ce fichier se **glisse-dépose dans ComfyUI**, qui recharge le graphe : c'est ainsi qu'on
rejoue à la main ce que le projet a fait tourner, avec la même graine.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core.cli import charger_config, configurer_stdout          # noqa: E402
from illustration import sonde as sonde_mod                     # noqa: E402
from illustration import validation as validation_mod           # noqa: E402
from illustration.comfyui import ComfyIndisponible, MoteurComfyUI  # noqa: E402

#: Les workflows du dépôt, sondés par `--sonde` quand aucun n'est nommé. **Quatre** fichiers au
#: 2026-09-03 : trois qui ont tourné, dont deux portent `%reference_1%`, plus le graphe
#: CANDIDAT du `PLAN-30` — jamais exécuté, poids non installé, et dont les manques sont des
#: réserves et non des refus (`validation._retrograder`).
WORKFLOWS_DU_DEPOT = RACINE / "illustration" / "workflows"


def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Sonde et valide un ComfyUI. AUCUNE sous-commande ne génère d'image.")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--sonde", action="store_true",
                    help="ce que le serveur expose : version, VRAM, nœuds, listes de modèles")
    ap.add_argument("--valider", metavar="WORKFLOW.API.JSON", nargs="?", const="*",
                    default=None,
                    help="valide un workflow AVANT le GPU. Sans argument : les trois graphes "
                         "du dépôt et celui de config.yaml")
    ap.add_argument("--graphe", metavar="REQUETE.YAML", default=None,
                    help="écrit le graphe SUBSTITUÉ tel qu'il partirait — sans l'envoyer")
    ap.add_argument("--sortie", metavar="DOSSIER", default=None,
                    help="--graphe : où écrire (défaut : à côté du requete.yaml)")
    ap.add_argument("--diff", nargs=2, metavar=("A.JSON", "B.JSON"), default=None,
                    help="ce qui change entre deux graphes")
    ap.add_argument("--journal", action="store_true",
                    help="le dernier run : temps, pic VRAM, et les lignes qui décident")
    ap.add_argument("--projet", default=None, help="--journal : restreint à ce projet")
    args = ap.parse_args()

    if not any((args.sonde, args.valider, args.graphe, args.diff, args.journal)):
        ap.print_help()
        return 2

    config = charger_config(args.config)
    code = 0
    if args.sonde:
        code = max(code, commande_sonde(config))
    if args.valider is not None:
        code = max(code, commande_valider(config, args.valider))
    if args.graphe:
        code = max(code, commande_graphe(config, args.graphe, args.sortie))
    if args.diff:
        code = max(code, commande_diff(args.diff[0], args.diff[1]))
    if args.journal:
        code = max(code, commande_journal(config, args.projet))
    return code


# ═══════════════════════════════  --sonde  ═══════════════════════════════

def commande_sonde(config: dict, *, transport=None) -> int:
    """Ce que le serveur expose, relevé sur son API. Rend 1 s'il ne répond pas."""
    releve = sonde_mod.depuis_config(config, transport=transport)
    print("")
    for ligne in releve.resume():
        print(ligne)
    if not releve.joignable:
        return 1
    print("\nCe que les graphes du dépôt demandent, et ce que ce serveur en expose :")
    for ligne in lignes_de_listes(releve):
        print("  " + ligne)
    tiers = releve.tiers
    if tiers:
        print("\n⚠ Les nœuds tiers ci-dessus ont chacun leur licence, et elle se vérifie à la "
              "source primaire — le dépôt a déjà cette jurisprudence (poids de LaMa, lot 16). "
              "Note-la dans docs/procedures/comfyui.md §0.")
    return 0


def lignes_de_listes(releve) -> list[str]:
    """Pour chaque champ de fichier des graphes du dépôt : le nœud existe-t-il, et le fichier
    nommé est-il dans sa liste ? C'est la vérification qui manquait, et elle est bon marché."""
    lignes: list[str] = []
    for chemin in sorted(WORKFLOWS_DU_DEPOT.glob("*.api.json")):
        rapport = validation_mod.valider(chemin, releve=releve)
        etat = "✓" if rapport.ok else f"✗ {len(rapport.refus)} refus"
        lignes.append(f"{etat}  {chemin.name} — {len(rapport.noeuds)} nœuds, "
                      f"modèles : {', '.join(rapport.modeles) or '(aucun)'}")
    return lignes


# ═══════════════════════════════  --valider  ═══════════════════════════════

def commande_valider(config: dict, cible: str, *, transport=None) -> int:
    """Le cœur du lot : six vérifications, aucune seconde de GPU.

    ⚠ **La sixième est arrivée au lot 30** (`PLAN-30` L30.3) : où atterrit la copie que
    ComfyUI écrit **en plus** de celle qu'Angelith marque. Elle pose une réserve sur tout
    graphe à `SaveImage` — le cas de tous ceux du dépôt — et ne refuse que
    `SaveImageWebsocket`, que ce client ne sait mécaniquement pas lire.

    ⚠ **Et le dépôt livre désormais un graphe CANDIDAT**, dont le poids n'est installé nulle
    part. Ses « nœud absent » et « modèle absent » sont rétrogradés en réserves : sans cela,
    cette commande sans argument passerait en rouge sur toute machine du monde.

    ⚠ **La sonde est faite UNE fois pour N workflows.** Sonder par workflow rendrait le
    contrôle trois fois plus lent pour un relevé identique — et surtout, deux relevés pris à
    deux instants ne se comparent pas."""
    from illustration.orchestrateur import reglages

    reg = reglages(config)
    releve = sonde_mod.depuis_config(config, transport=transport)
    if not releve.joignable:
        print(f"\n⚠ Serveur {releve.base_url} injoignable : les vérifications « nœud absent » "
              f"et « modèle absent » sont NON FAITES, pas passées.")
    cibles = _cibles(cible, reg)
    if not cibles:
        print("Aucun workflow à valider : illustration.comfyui.workflow est vide et "
              "illustration/workflows/ ne contient aucun .api.json.")
        return 1
    code = 0
    for chemin in cibles:
        rapport = validation_mod.valider(
            chemin, releve=releve, pas=reg["image"]["pas"], guidage=reg["image"]["guidage"])
        print("")
        for ligne in rapport.lignes():
            print(ligne)
        code = max(code, 0 if rapport.ok else 1)
    for constat in validation_mod.verifier_vram(releve):
        print("")
        for ligne in constat.lignes():
            print(ligne)
        if constat.gravite == "refus":
            code = 1
    return code


def _cibles(cible: str, reg: dict) -> list[Path]:
    if cible != "*":
        return [Path(cible)]
    trouves = sorted(WORKFLOWS_DU_DEPOT.glob("*.api.json"))
    declare = reg["comfyui"]["workflow"]
    if declare and Path(declare).resolve() not in {c.resolve() for c in trouves}:
        trouves.append(Path(declare))
    return trouves


# ═══════════════════════════════  --graphe  ═══════════════════════════════

def commande_graphe(config: dict, requete_yaml: str, sortie: str | None = None) -> int:
    """Écrit le graphe substitué de chaque image de `requete.yaml`. **N'envoie rien.**

    ⚠ **La porte humaine n'est PAS consultée ici, et c'est cohérent** : cet outil n'écrit
    aucune image. Un `requete.yaml` en `valide: false` est justement celui qu'on veut
    inspecter — c'est même l'usage principal, puisque c'est le moment où l'on relit."""
    from illustration import requete as requete_mod
    from illustration.orchestrateur import reglages

    reg = reglages(config)
    chemin = Path(requete_yaml)
    if not chemin.is_file():
        print(f"{chemin} n'existe pas.")
        return 1
    workflow = reg["comfyui"]["workflow"]
    if not workflow:
        print("illustration.comfyui.workflow est vide : il n'y a aucun graphe à substituer.")
        return 1
    doc = requete_mod.load(chemin)
    # Le dossier du tome sert à résoudre les références relatives, exactement comme en phase
    # image ; ici il ne sert qu'à LIRE les fichiers pour calculer leur empreinte.
    racine = chemin.parent
    try:
        moteur = MoteurComfyUI(workflow, dossier_tome=racine)
    except ComfyIndisponible as err:
        print(f"✗ {err}")
        return 1
    destination = Path(sortie) if sortie else chemin.parent / "graphes"
    destination.mkdir(parents=True, exist_ok=True)
    ecrits = 0
    aleatoires = [b["nom"] for b in requete_mod.fill_defaults(doc)["images"]
                  if b.get("graine") is None]
    for nom, requete in requete_mod.requetes(doc):
        try:
            graphe, televersements = moteur.graphe_substitue(requete, televerser=False)
        except ComfyIndisponible as err:
            print(f"✗ {nom} : {err}")
            continue
        cible = destination / f"{nom}.api.json"
        cible.write_text(json.dumps(graphe, ensure_ascii=False, indent=2, sort_keys=True)
                         + "\n", encoding="utf-8")
        ecrits += 1
        print(f"\n{nom} → {cible}")
        print(f"  {len(graphe)} nœuds · graine {requete.graine} · {requete.pas} pas · "
              f"guidage {requete.guidage:g}")
        for envoi in televersements:
            print(f"  à téléverser : {envoi['source']}")
            print(f"    → ComfyUI le connaîtra sous « {envoi['nom']} »")
    if not ecrits:
        return 1
    print(f"\n{ecrits} graphe(s) écrit(s) dans {destination}.")
    print("  ⚠ RIEN n'a été envoyé, et aucune image de référence n'a été téléversée.")
    if aleatoires:
        # ⚠ Le seul écart possible entre ce fichier et ce qui partira, et il faut le dire :
        # `graine: null` est TIRÉE à chaque lecture du fichier (cf. `requete._graine`), une
        # fois ici et une autre fois à la phase image. Comparer deux images produites avec
        # deux graines différentes ne mesurerait rien.
        print(f"  ⚠ GRAINE ALÉATOIRE sur {len(aleatoires)} bloc(s) ({', '.join(aleatoires)}) :")
        print("    elle est tirée À CHAQUE lecture de requete.yaml, donc celle écrite ici ne "
              "sera PAS celle du run.")
        print("    → fixe `graine:` dans requete.yaml si tu veux comparer les deux images.")
    print("  Glisse un de ces fichiers dans ComfyUI : il est au format API et recharge le "
          "graphe exact. Les LoadImage pointeront vers des noms que le serveur n'a pas encore "
          "— téléverse les fichiers listés ci-dessus dans son input/angelith/, ou lance la "
          "phase image, qui le fait pour toi.")
    return 0


# ═══════════════════════════════  --diff  ═══════════════════════════════

def commande_diff(a: str, b: str) -> int:
    """Ce qui change entre deux graphes, **par nœud et par champ**.

    ⚠ Un `diff` de texte sur deux JSON de graphe est illisible : l'ordre des clés n'a aucun
    sens et un nœud renuméroté fait bouger tout le fichier. On compare donc les nœuds par leur
    identifiant, et les champs un par un — c'est la seule lecture qui dise « la graine a
    changé » au lieu de « 40 lignes ont changé »."""
    gauche, droite = _charger(a), _charger(b)
    if gauche is None or droite is None:
        return 1
    lignes = lignes_de_diff(gauche, droite)
    print("")
    print(f"{a}  →  {b}")
    for ligne in lignes:
        print("  " + ligne)
    return 0


def lignes_de_diff(gauche: dict, droite: dict) -> list[str]:
    lignes: list[str] = []
    for cle in sorted(set(gauche) - set(droite)):
        lignes.append(f"− nœud {cle} ({gauche[cle].get('class_type', '?')}) retiré")
    for cle in sorted(set(droite) - set(gauche)):
        lignes.append(f"+ nœud {cle} ({droite[cle].get('class_type', '?')}) ajouté")
    for cle in sorted(set(gauche) & set(droite)):
        avant, apres = gauche[cle], droite[cle]
        classe = apres.get("class_type", "?")
        if avant.get("class_type") != classe:
            lignes.append(f"~ nœud {cle} : {avant.get('class_type', '?')} → {classe}")
        entrees_a = avant.get("inputs") or {}
        entrees_b = apres.get("inputs") or {}
        for champ in sorted(set(entrees_a) | set(entrees_b)):
            va, vb = entrees_a.get(champ, "(absent)"), entrees_b.get(champ, "(absent)")
            if va != vb:
                lignes.append(f"~ {cle}.{classe}.{champ} : {va!r} → {vb!r}")
    return lignes or ["= les deux graphes sont identiques."]


def _charger(chemin: str):
    fichier = Path(chemin)
    if not fichier.is_file():
        print(f"{fichier} n'existe pas.")
        return None
    try:
        graphe = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"{fichier} : {err}")
        return None
    return {cle: valeur for cle, valeur in graphe.items()
            if isinstance(valeur, dict) and "class_type" in valeur}


# ═══════════════════════════════  --journal  ═══════════════════════════════

def commande_journal(config: dict, projet: str | None = None, *, transport=None) -> int:
    """Le dernier run : ce que son sidecar dit, et ce que le serveur dit encore.

    ⚠ **Les deux sources ne disent pas la même chose, et c'est le point.** Le sidecar porte ce
    qui a été archivé AU MOMENT du run — c'est une trace. Le journal du serveur porte l'état
    courant de sa console — c'est un souvenir, qui s'efface au redémarrage. Un run dont le
    sidecar ne porte pas ses lignes de journal a été produit par une version d'avant la
    2.22.0, ou par un serveur qui n'expose pas `/internal/logs/raw`."""
    dernier = _dernier_manifeste(config, projet)
    print("")
    if dernier is None:
        print("Aucune image produite trouvée sous build/ — rien à raconter.")
    else:
        for ligne in lignes_de_journal(dernier):
            print(ligne)
    releve_journal = sonde_mod.journal_serveur(
        _base_url(config), transport=transport, lignes=10)
    print("\nLe journal du serveur, maintenant :")
    if not releve_journal.get("disponible"):
        print(f"  · indisponible — {releve_journal.get('motif', '')}")
        return 0
    for ligne in releve_journal.get("lignes") or []:
        print(f"  {ligne}")
    if releve_journal.get("rogne"):
        print("  ⚠ « loaded partially » / « lowvram patches » : le transformeur a été ROGNÉ. "
              "Attends-toi au facteur 9,6 sur le temps par pas (§5 de "
              "docs/procedures/comfyui.md).")
    return 0


def lignes_de_journal(manifeste: Path) -> list[str]:
    donnees = json.loads(manifeste.read_text(encoding="utf-8"))
    graphe = donnees.get("graphe") or {}
    journal = donnees.get("journal_serveur") or {}
    payload = donnees.get("payload") or {}
    lignes = [f"Dernière image : {manifeste.parent / donnees.get('image', '?')}",
              f"  date {donnees.get('date', '?')} · {donnees.get('secondes', 0):.1f} s · "
              f"graine {payload.get('graine', '?')} · Angelith "
              f"{donnees.get('angelith', '?')}",
              f"  modèle {donnees.get('modele') or '(non nommé)'} · moteur "
              f"{donnees.get('moteur') or '?'}"]
    pic = donnees.get("vram_pic_octets")
    lignes.append(f"  pic VRAM : {sonde_mod.mio(pic)} Mio" if pic else
                  "  pic VRAM : non mesuré — ce client parle à ComfyUI par HTTP et n'a "
                  "aucune vue sur l'allocateur pendant le calcul")
    if graphe:
        lignes.append(f"  graphe envoyé : {graphe.get('fichier')} "
                      f"({graphe.get('noeuds', '?')} nœuds, sha256 "
                      f"{str(graphe.get('sha256', ''))[:16]}…)")
    else:
        lignes.append("  graphe envoyé : ABSENT — image produite avant la 2.22.0, ou par le "
                      "moteur factice, qui ne construit aucun graphe.")
    if journal.get("disponible"):
        lignes.append("  lignes du serveur archivées avec l'image :")
        lignes += [f"    {ligne}" for ligne in journal.get("lignes") or []]
        if journal.get("rogne"):
            lignes.append("    ⚠ le transformeur avait été ROGNÉ pendant ce run.")
    else:
        lignes.append(f"  lignes du serveur : absentes — {journal.get('motif', 'non archivées')}")
    return lignes


def _dernier_manifeste(config: dict, projet: str | None):
    from illustration import marquage

    racine = Path(config["chemins"]["build"])
    if not racine.is_dir():
        return None
    motif = f"{projet}/illustrations/*.png" if projet else "*/illustrations/*.png"
    images = [c for c in racine.glob(motif) if marquage.manifeste_de(c).is_file()]
    if not images:
        return None
    dernier = max(images, key=lambda c: c.stat().st_mtime)
    return marquage.manifeste_de(dernier)


def _base_url(config: dict) -> str:
    from illustration.orchestrateur import reglages

    return reglages(config)["comfyui"]["base_url"]


if __name__ == "__main__":
    raise SystemExit(main())
