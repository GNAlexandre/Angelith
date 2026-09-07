# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le run en **deux phases**, avec un humain entre les deux, et un seul modèle en VRAM.

    phase 1 — prompt   LLM (à venir, `PLAN-26`) ou squelette déterministe → `requete.yaml`
    ─────────── porte humaine : relire, corriger, `valide: true` ───────────
    phase 2 — image    décharger le LLM · charger le modèle d'image · les PNG marqués

## Pourquoi les deux modèles ne coexistent jamais

`docs/README.fr.md` (≈ l. 639) écrit que « ~17 Go ne tiennent de toute façon pas dans 20 Go de
VRAM. Ça supprime tout scénario de seconde instance / partage de VRAM ». Le LLM de traduction
**occupe la carte**. La conclusion est structurelle, pas négociable : la phase image appelle
`core/power.py:ollama_unload` avant de charger quoi que ce soit, et le rechargement du LLM est
de la responsabilité de l'appelant. **Ce mécanisme existe déjà** — le dépôt décharge le LLM
avant détection/OCR quand `DmlExecutionProvider` est actif — et il est réutilisé, pas réécrit.

## La bascule est mesurée, et son coût est publié à côté du temps de génération

Elle a lieu **une fois par run**, jamais une fois par image : le récapitulatif porte
`bascule_secondes` et `secondes_par_image`, et le rapport les met côte à côte. La règle du
`PLAN-24` est écrite dans `rapport.py` : si la bascule coûte plus que huit images, c'est la
bascule qu'il faut optimiser, pas le modèle.

## Le cache est à la brique, et il n'entre pas dans le graphe d'invalidation

Tout vit sous `build/<Projet>/<Tome>/illustrations/`. La brique n'ajoute rien à
`manga/checkpoints.py:STAGES`, n'incrémente aucun `FORMAT_VERSION`, ne lit ni n'écrit sous
`.checkpoints/`. Interdit n° 1 : une relance de tome coûte des heures de GPU, et
`load_regions` rend `None` sur écart de version, ce qui déclencherait `downstream("detection")`
**sur tous les projets**.

⚠ **Et le `RAPPORT.md` du tome n'est PAS modifié.** Le `PLAN-24` L24.6 demandait d'y ajouter
une section ; son critère 1 bis interdit d'écrire dans un fichier préexistant. Les deux ne
tiennent pas ensemble, et c'est la frontière qui gagne — elle est la raison d'être du lot. La
brique écrit **son propre** `RAPPORT.md` dans son dossier, et le `perf.log` du tome n'est pas
touché non plus. Ce n'est pas un contournement du plan, c'est l'arbitrage entre deux de ses
demandes, écrit ici pour qu'il ne se redécouvre pas.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from core import bible as bible_mod
from core import chemins as chemins_mod
from illustration import frontiere, marquage, rapport
from illustration import identite as ident_mod
from illustration import prompt as prompt_mod
from illustration import requete as requete_mod
from illustration import selection as selection_mod
from illustration import moteur as moteur_mod
from illustration.moteur import MoteurFactice

NOM_DOSSIER = "illustrations"


def dossier(config: dict, projet: str) -> Path:
    """`build/<Projet>/illustrations/` — le seul endroit où la brique écrit.

    ⚠ **Par ŒUVRE, plus par tome, depuis le 2026-08-31.** Un personnage traverse les volumes,
    et ses références aussi : sur le tome de référence, 7 des 10 références validées vivent
    dans le Vol.2. Une sortie rangée par tome obligeait à choisir un volume arbitraire pour
    illustrer un personnage qui n'appartient à aucun, et éparpillait `requete.yaml` en autant
    de copies qu'il y a de volumes.

    ⚠ **Un `requete.yaml` d'avant ce changement n'est PAS lu.** Il vit sous
    `build/<Projet>/<Tome>/illustrations/`, et la phase image dit où il est plutôt que de
    l'ignorer en silence — cf. `requete_heritee`."""
    return Path(config["chemins"]["build"]) / chemins_mod.segment(projet, "projet") / NOM_DOSSIER


def dossier_retenues(config: dict, projet: str) -> Path:
    """`sources/<Projet>/illustrations/` — **l'emplacement pérenne**, étape 0.2 du `PLAN-27`.

    ⚠ **Pourquoi pas sous `build/`, alors que tout le reste de la brique y vit.** `build/` est
    régénérable par contrat — `.gitignore` l'écrit — et le dépôt recommande lui-même un
    `rm -r build/` après un MAJEUR. Or une image produite en 103,7 s de GPU et retenue par un
    humain **n'est pas régénérable** : `orchestrateur.rejouer` mesure déjà que « la plupart
    des backends de diffusion ne sont pas déterministes d'une exécution à l'autre ». Le geste
    « je garde » déplace donc le fichier là où vit le travail écrit à la main — les
    glossaires, la bible —, qui survit à la suppression de `build/` et reste exclu de git.

    ⚠ C'est la **seconde** racine d'écriture de la brique, et la seule ajoutée depuis le lot
    24. Elle est un sous-dossier neuf de `sources/<Projet>/`, jamais le dossier du projet
    lui-même : `frontiere.perimetre` ne laisse donc toujours pas approcher `bible.yaml`,
    `glossaire.yaml` ni un fichier de l'œuvre."""
    return Path(config["chemins"]["sources"]) / chemins_mod.segment(projet, "projet") \
        / NOM_DOSSIER


def dossier_rejetees(config: dict, projet: str) -> Path:
    """`build/<Projet>/illustrations/rejetees/` — jeté n'est pas supprimé (L27.3)."""
    from illustration import galerie as galerie_mod
    return dossier(config, projet) / galerie_mod.NOM_REJETEES


def requete_heritee(config: dict, projet: str) -> list:
    """Les `requete.yaml` restés sous un TOME, d'avant la portée par œuvre.

    On ne les lit pas et on ne les déplace pas : on les **nomme**. Déplacer le travail de
    relecture de quelqu'un sans le lui dire serait pire que de l'ignorer."""
    racine = racine_projet(config, projet)
    if not racine.is_dir():
        return []
    return [t / NOM_DOSSIER / requete_mod.NOM_FICHIER for t in sorted(racine.iterdir())
            if t.is_dir() and (t / NOM_DOSSIER / requete_mod.NOM_FICHIER).is_file()]


def dossier_tome(config: dict, projet: str, tome: str) -> Path:
    """`build/<Projet>/<Tome>/` — un tome précis, quand l'appelant restreint volontairement.

    Jamais écrit ; le périmètre de `frontiere.py` le garantit à l'exécution."""
    projet = chemins_mod.segment(projet, "projet")
    tome = chemins_mod.segment(tome, "tome")
    return Path(config["chemins"]["build"]) / projet / tome


def racine_lue(config: dict, projet: str, tome: str | None = None) -> Path:
    """La racine des fichiers LUS : l'œuvre entière, ou un tome si on l'a restreinte.

    ⚠ C'est le seul endroit qui décide de l'étendue de la lecture, et il rend un chemin que
    `media/`, `chapters/` et les références savent tous interpréter."""
    if tome:
        return dossier_tome(config, projet, tome)
    return racine_projet(config, projet)


def racine_projet(config: dict, projet: str) -> Path:
    """`build/<Projet>/` — la racine qui porte TOUS les tomes. C'est elle qui permet de
    résoudre une référence de bible, laquelle est par projet et non par tome."""
    return Path(config["chemins"]["build"]) / chemins_mod.segment(projet, "projet")


def dossier_projet(config: dict, projet: str) -> Path:
    return Path(config["chemins"]["sources"]) / chemins_mod.segment(projet, "projet")


def reglages(config: dict) -> dict:
    """Le bloc `illustration:` avec ses défauts. Un run par défaut ne fait RIEN et ne
    télécharge RIEN : `actif: false`, `moteur: "factice"`, `telechargement_auto: false`."""
    brut = dict(config.get("illustration") or {})
    poids = dict(brut.get("poids") or {})
    image = dict(brut.get("image") or {})
    comfy = dict(brut.get("comfyui") or {})
    vram = dict(brut.get("vram") or {})
    insertion = dict(brut.get("insertion") or {})
    marque = dict(brut.get("marquage") or {})
    ident = dict(brut.get("identite") or {})
    encodeur = dict(ident.get("encodeur") or {})
    planchers = dict(ident.get("planchers") or {})
    invite = dict(brut.get("prompt") or {})
    invite_llm = dict(invite.get("llm") or {})
    budget = dict(brut.get("budget") or {})
    return {
        "actif": bool(brut.get("actif", False)),
        "moteur": str(brut.get("moteur") or "factice"),
        "poids": {"dossier": str(poids.get("dossier") or "illustration_models"),
                  "fichier": str(poids.get("fichier") or ""),
                  "url": str(poids.get("url") or ""),
                  "sha256": str(poids.get("sha256") or ""),
                  "telechargement_auto": bool(poids.get("telechargement_auto", False))},
        "image": {"largeur": int(image.get("largeur") or 1328),
                  "hauteur": int(image.get("hauteur") or 1328),
                  "pas": int(image.get("pas") or 30),
                  "guidage": float(image.get("guidage") if image.get("guidage") is not None
                                   else 4.0),
                  "graine": image.get("graine"),
                  "par_requete": int(image.get("par_requete") or 1)},
        "comfyui": {"base_url": str(comfy.get("base_url") or "http://127.0.0.1:8188"),
                    "workflow": str(comfy.get("workflow") or ""),
                    "timeout": float(comfy.get("timeout") or 600),
                    # ⚠ `or` ne convient pas ici : 0 est une valeur voulue — elle DÉSARME le
                    # contrôle du cache — et `0 or 2.0` rendrait 2,0. Le dépôt a déjà payé
                    # cette confusion sur les planchers du lot 25 (`_flottant`).
                    "plancher_secondes": float(
                        comfy["plancher_secondes"]
                        if comfy.get("plancher_secondes") is not None else 2.0)},
        # ⚠ `recharger_llm` (lot 27) est ISO sur la configuration livrée, et ce n'est pas une
        # coïncidence : il ne fait rien tant que `decharger_image` vaut false. Le LLM ne
        # revient que si la carte est RÉELLEMENT libre — recharger 17 Go pendant que ComfyUI
        # tient ses 12 Go est exactement le scénario que toute l'architecture refuse. Voir
        # `illustration/vram.py`.
        "vram": {"decharger_llm": bool(vram.get("decharger_llm", True)),
                 "decharger_image": bool(vram.get("decharger_image", False)),
                 "recharger_llm": bool(vram.get("recharger_llm", True))},
        # Lot 27 — L27.4. `inserer_dans_sorties: false` par défaut : un tome relancé sans que
        # l'utilisateur ait rien demandé sort ISO-OCTET. La clé vit ici plutôt que sous
        # `rendu:` parce qu'elle appartient à cette brique ; c'est `pipeline/orchestrator.py`
        # qui la lit, par `core/insertion.py`, sans jamais importer `illustration/`.
        "inserer_dans_sorties": bool(brut.get("inserer_dans_sorties", False)),
        "insertion": {"position": str(insertion.get("position") or "debut_chapitre")},
        "marquage": {"identifiant_oeuvre": str(marque.get("identifiant_oeuvre") or "")},
        # Lot 25. `actif: false` → la phase image se comporte exactement comme au lot 24 :
        # aucune référence n'est préparée, aucune grandeur n'est mesurée, aucun encodeur
        # n'est chargé. C'est l'iso-comportement que le §9.3 du contexte agent exige.
        "identite": {
            "actif": bool(ident.get("actif", False)),
            "references_max": int(ident.get("references_max") or 3),
            "cote_reference": int(ident.get("cote_reference") or 1024),
            "encodeur": {
                "dossier": str(encodeur.get("dossier") or "illustration_models"),
                "fichier": str(encodeur.get("fichier") or ""),
                "url": str(encodeur.get("url") or ""),
                "sha256": str(encodeur.get("sha256") or ""),
                "agregation": str(encodeur.get("agregation") or "cls_moy"),
                "cadrage": str(encodeur.get("cadrage") or "plein"),
                "cote": int(encodeur.get("cote") or 224)},
            "planchers": {
                "confusion": _flottant(planchers.get("confusion")),
                "nouveaute": _flottant(planchers.get("nouveaute")),
                "style_descripteurs": _flottant(planchers.get("style_descripteurs")),
                "juge_utilisable": bool(planchers.get("juge_utilisable", False))},
        },
        # Lot 26. Défauts iso : `forme: prose`, `langue: fr`, `llm.actif: false`. Un run de
        # phase 1 se comporte donc comme au lot 25 — squelette déterministe, aucun appel
        # réseau — tant que l'utilisateur n'arme pas le modèle de vision.
        "prompt": {
            "forme": str(invite.get("forme") or "prose"),
            "langue": str(invite.get("langue") or "fr"),
            "cadrage": str(invite.get("cadrage") or "buste"),
            "gabarit": str(invite.get("gabarit") or "portrait"),
            "style": str(invite.get("style") or "mots"),
            "references_max": int(invite.get("references_max") or 2),
            "ancrages_max": int(invite.get("ancrages_max")
                                if invite.get("ancrages_max") is not None else 0),
            "llm": {"actif": bool(invite_llm.get("actif", False)),
                    "modele": str(invite_llm.get("modele") or ""),
                    "cote_vision": int(invite_llm.get("cote_vision") or 1024),
                    "max_input_tokens": int(invite_llm.get("max_input_tokens") or 0)},
        },
        "budget": {"images_par_run": int(budget.get("images_par_run") or 8)},
    }


def _flottant(valeur):
    """`None` reste `None` — c'est « non étalonné », et ce n'est pas zéro.

    ⚠ Un plancher à 0 est un seuil que rien ne franchit ; un plancher à `None` est un contrôle
    qui ne se prononce pas. Les confondre ferait passer une absence d'étalonnage pour un
    verdict favorable."""
    return None if valeur is None or valeur == "" else float(valeur)


class BriqueInactive(RuntimeError):
    """`illustration.actif` vaut false — et c'est le défaut livré."""


def exiger_actif(config: dict) -> dict:
    reg = reglages(config)
    if not reg["actif"]:
        raise BriqueInactive(
            "la brique d'illustration est DÉSARMÉE (illustration.actif: false).\n"
            "  C'est le défaut livré : un utilisateur qui ne touche à rien ne voit aucune "
            "différence, ne télécharge aucun poids et ne perd aucune seconde au démarrage.\n"
            "  Pour l'armer : passe illustration.actif à true dans config.yaml, puis relis "
            "le bloc — chaque clé y porte le chiffre qui la justifie.")
    return reg


# ─────────────────────────────────  Phase 1  ─────────────────────────────────

def phase_prompt(projet: str, config: dict, *, tome: str | None = None, reporter=None,
                 graine: int | None = 0, personnages=None, ecraser: bool = False,
                 cadrage: str | None = None, forme: str | None = None,
                 langue: str | None = None, llm=None, selections=None,
                 blocs_libres=None) -> dict:
    """Écrit `requete.yaml` depuis l'œuvre. **Aucun modèle d'IMAGE n'est chargé.**

    Trois sources, et chacune répond à une question différente :

    | question | source | où |
    |---|---|---|
    | à quoi ressemble-t-il ? | `bible.apparence` + `citations[]` | `illustration/prompt.py` |
    | est-ce un homme ou une femme ? | `bible.genre_confirme`, sinon `glossaire.genre` | idem |
    | quelles images lui montrer ? | `bible.references[]` + `bible.style.ancrages[]` | `illustration/selection.py` |

    ⚠ **Le LLM local est facultatif et il ne sert qu'à CHOISIR des images.** Il ne rédige
    aucun attribut : ceux-là viennent de la bible, mot pour mot. C'est ce qui rend le critère
    4 du `PLAN-26` tenable, et c'est une absence de branche, pas une vérification.

    ⚠ Un `requete.yaml` existant n'est PAS écrasé sans `ecraser=True` : il porte le travail de
    relecture de l'utilisateur, et le perdre au premier `--phase prompt` distrait serait
    exactement le genre de coût que le dépôt refuse ailleurs pour le glossaire."""
    reg = exiger_actif(config)
    dire = _dire(reporter)
    sortie = dossier(config, projet)
    cible = requete_mod.chemin(sortie)
    for hérité in requete_heritee(config, projet):
        dire(f"  ⚠ un requete.yaml d'avant la portée par ŒUVRE existe encore : {hérité}. "
             f"Il n'est ni lu ni déplacé — recopie ce que tu veux garder.")
    if cible.exists() and not ecraser:
        raise FileExistsError(
            f"{cible} existe déjà et porte peut-être ta relecture.\n"
            f"  Relance avec --ecraser si tu veux repartir du squelette, ou édite le "
            f"fichier tel quel — c'est lui que la phase image lira.")

    invite = reg["prompt"]
    depart = time.monotonic()
    bible_doc = bible_mod.load(bible_mod.chemin(dossier_projet(config, projet)))
    glossaire = _glossaire(config, projet, dire)
    # ⚠ `selections` peut venir de l'appelant : c'est ainsi que l'atelier interactif fait
    # entrer le choix de l'HUMAIN — celui qui a regardé les images à l'écran — plutôt que de
    # relancer un choix automatique derrière lui. Une porte dont les décisions sont
    # recalculées n'est pas une porte, et le lot 26 a déjà payé cette leçon en phase 2.
    if selections is None:
        selections = _choisir_les_images(config, projet, reg, bible_doc, personnages,
                                         llm=llm, dire=dire)
    scenes, appels_scene = _scenes_du_tome(config, projet, tome, reg, bible_doc, personnages,
                                           llm=llm, dire=dire)
    budget = prompt_mod.Budget(images=reg["budget"]["images_par_run"])

    with frontiere.perimetre(sortie):
        doc = requete_mod.depuis_oeuvre(
            bible_doc, glossaire, modele=_nom_modele(reg),
            graine=graine, personnages=personnages, selections=selections, scenes=scenes,
            cadrage=cadrage or invite["cadrage"], forme=forme or invite["forme"],
            langue=langue or invite["langue"], gabarit=invite["gabarit"], budget=budget)
        for bloc in doc["images"]:
            bloc["largeur"] = reg["image"]["largeur"]
            bloc["hauteur"] = reg["image"]["hauteur"]
            bloc["pas"] = reg["image"]["pas"]
            bloc["guidage"] = reg["image"]["guidage"]
            bloc["nombre_images"] = reg["image"]["par_requete"]
            if reg["image"]["graine"] is not None:
                bloc["graine"] = int(reg["image"]["graine"])
        # Le prompt et les références d'origine sont archivés AVANT toute correction humaine :
        # le sidecar doit pouvoir montrer l'avant et l'après, c'est ce que la traçabilité exige.
        requete_mod.archiver_l_initial(doc)
        # ⚠ Les appels de SCÈNE comptent comme les appels de VISION. Ne compter que les
        # seconds ferait publier « 13 appels » pour une phase 1 qui en a fait 19, et le
        # critère 1 quater du PLAN-26 compare précisément ce coût-là à celui de la phase 2.
        doc["phase1"]["appels_llm"] += appels_scene
        doc["phase1"]["secondes"] = round(time.monotonic() - depart, 3)
        requete_mod.save(doc, cible, projet=projet, tome=tome)

    problemes = requete_mod.verifier(doc, racine_projet=racine_projet(config, projet))
    for probleme in problemes:
        dire(f"  ⚠ {probleme}")
    for plafond in doc["phase1"]["plafonds_atteints"]:
        dire(f"  ⚠ {plafond}")
    dire(f"Requête écrite : {cible}")
    dire(f"  {len(doc['images'])} image(s) proposée(s) — RELIS le fichier, corrige les "
         f"prompts, renseigne validation.par, puis passe `valide` à true.")
    dire(f"  Phase 1 : {doc['phase1']['secondes']:.1f} s, "
         f"{doc['phase1']['appels_llm']} appel(s) au modèle de vision.")
    if not doc["images"]:
        dire("  ⚠ aucun personnage de la bible ne porte d'attribut cité : il n'y a rien à "
             "illustrer. C'est la règle de citation de la bible qui parle, pas un défaut — "
             "commence par `python tools/bible.py --revue`.")
    return {"requete": cible, "images": len(doc["images"]), "problemes": problemes,
            "secondes": doc["phase1"]["secondes"],
            "appels_llm": doc["phase1"]["appels_llm"]}


def _scenes_du_tome(config: dict, projet: str, tome: str, reg: dict, bible_doc: dict,
                    personnages, *, llm=None, dire=None) -> tuple[dict, int]:
    """`{personnage: clause de scène}` — **L26.2, l'appel LLM facultatif**.

    Le LLM reformule un passage du chapitre en une phrase de POSE. Il n'écrit aucun attribut :
    `illustration/scene.py` applique `prompt.epurer` avant de rendre la clause, et une clause
    impure est rejetée **en entier**.

    ⚠ **Rien ne se passe ici tant que `illustration.prompt.llm.actif` vaut `false`**, ce qui
    est le défaut. C'est ce qui garde la phase 1 déterministe, sans réseau, et testable en CI.

    ⚠ **Le plafond de jetons écarte des PASSAGES, il n'en tronque aucun** — L26.4. Une phrase
    amputée décrirait une scène qui n'a pas eu lieu, et le modèle n'aurait aucun moyen de le
    savoir. `illustration.prompt.llm.max_input_tokens` vaut 0 par défaut, ce qui reprend
    `decoupage.max_input_tokens` (24 000 dans la configuration livrée)."""
    from illustration import gabarits as gabarits_mod
    from illustration import scene as scene_mod

    dire = dire or (lambda _m: None)
    invite = reg["prompt"]
    if not invite["llm"]["actif"]:
        return {}, 0
    pack = _prompt_du_pack(config, scene_mod.PROMPT, dire)
    if not pack:
        return {}, 0
    modele = invite["llm"]["modele"] or _modele_par_defaut(config)
    if not modele:
        return {}, 0
    llm = llm or _llm(config)
    plafond = invite["llm"]["max_input_tokens"] or int(
        (config.get("decoupage") or {}).get("max_input_tokens") or 0)
    gab = gabarits_mod.charger(invite["gabarit"], langue=invite["langue"])
    racine_tome = racine_lue(config, projet, tome)
    voulus = {str(n) for n in personnages} if personnages else None

    scenes: dict = {}
    appels = 0
    for entree in (bible_doc or {}).get("personnages") or []:
        nom = str((entree or {}).get("nom") or "").strip()
        if not nom or (voulus is not None and nom not in voulus):
            continue
        liste, motifs = scene_mod.passages(racine_tome, entree, plafond_jetons=plafond)
        if not liste:
            continue
        clause, refus = scene_mod.reformuler(llm, modele, pack, nom, liste, gab)
        appels += 1
        for motif in motifs + refus:
            dire(f"    {nom} : {scene_mod.MOTIFS.get(motif, motif)}")
        if clause:
            scenes[nom] = clause
            dire(f"  {nom} : scène — « {clause} »")
    return scenes, appels


def _modele_par_defaut(config: dict) -> str:
    """Le premier modèle nommé par `modeles`. Passe par `cli.models_in_config`, qui lit les
    deux formes — chaîne et `{model, endpoint}` — plutôt que d'en réécrire une seconde."""
    from core import cli

    return next(iter(cli.models_in_config(config)), "")


def _prompt_du_pack(config: dict, nom: str, dire) -> str:
    """Le texte d'un prompt de pack de langue, ou `""` avec un avertissement.

    ⚠ Ni `illustration_style` ni `illustration_portrait` n'entrent dans
    `core.langues.PROMPTS_REQUIS` : les huit prompts de ce tuple sont ceux dont l'absence fait
    échouer `_verifier_prompts` et **invaliderait le pack `langues/en`**. Leur absence est
    donc signalée ici, pendant le run, et pas au démarrage du dépôt."""
    from core import langues as langues_mod

    chemin = langues_mod.resoudre_pack(config).prompt(nom)
    if not chemin.is_file():
        dire(f"  ⚠ {chemin} est absent : cette étape est sautée.")
        return ""
    return chemin.read_text(encoding="utf-8")


def _glossaire(config: dict, projet: str, dire) -> dict:
    """Le glossaire du projet, dans la langue cible. `{}` s'il n'y en a pas.

    ⚠ **Il n'est pas facultatif par confort : il porte le GENRE**, et le genre commande le
    sujet du prompt. Sur le corpus réel, `bible.genre_confirme` est vide sur 11 personnages
    sur 11 tandis que le glossaire le porte pour 9 — un champ qu'on n'allait pas chercher.
    Son absence est donc signalée, pas tue."""
    from core import glossary

    chemin_glossaire = dossier_projet(config, projet) / "glossaire.yaml"
    if not chemin_glossaire.is_file():
        dire(f"  ⚠ pas de glossaire ({chemin_glossaire}) : aucun sujet ne sera accordé, et "
             f"le modèle tranchera le genre à ma place — c'est ainsi qu'un personnage "
             f"masculin est sorti en femme au lot 25.")
        return {}
    cible = str(((config.get("langues") or {}).get("cible")) or "fr")
    return glossary.load(chemin_glossaire, cible)


def _choisir_les_images(config: dict, projet: str, reg: dict, bible_doc: dict,
                        personnages, *, llm=None, dire=None) -> dict:
    """L26.0 — `{personnage: Selection}`, avec un motif par image, retenue **et** écartée.

    ⚠ **Le plafond est celui du lot 25, pas celui que le modèle voudrait** :
    `illustration.prompt.references_max` vaut 2 par défaut, parce que « la rupture est entre
    1 et 2, pas entre 2 et 3 » (`docs/mesures/identite-2026-08-29.md` §5.4).

    ⚠ **Aucune image générée n'est candidate** : `selection._refuser_les_generees` l'écarte
    avec son motif, et un test le prouve plutôt qu'un raisonnement le promette."""
    dire = dire or (lambda _m: None)
    invite = reg["prompt"]
    racine = racine_projet(config, projet)
    voulus = {str(n) for n in personnages} if personnages else None
    systeme, modele = "", ""
    if invite["llm"]["actif"]:
        systeme, modele = _prompt_de_selection(config, reg, dire)
        if modele:
            llm = llm or _llm(config)

    # ⚠ Les ancres de style sont communes au TOME, pas au personnage : les juger une fois par
    # personnage coûterait 11 × 3 = 33 appels de vision là où 3 suffisent, sur un corpus de 11
    # personnages. Mesuré le 2026-08-30 avant correction : la phase 1 y passait l'essentiel de
    # son temps à redemander au modèle si la même image de décor portait un visage.
    ancrages_communs = selection_mod.candidates_ancrage(bible_doc, racine)
    ancres_jugees = _ancrages_pour(ancrages_communs, reg, llm, modele, systeme, dire)
    selections: dict = {}
    for entree in (bible_doc or {}).get("personnages") or []:
        nom = str((entree or {}).get("nom") or "").strip()
        if not nom or (voulus is not None and nom not in voulus):
            continue
        candidates = selection_mod.candidates_identite(bible_doc, nom, racine)
        choix = selection_mod.Selection()
        if llm is not None and modele:
            references, secondes, appels = selection_mod.choisir_avec_llm(
                candidates, plafond=invite["references_max"],
                usage=selection_mod.USAGE_IDENTITE, llm=llm, modele=modele,
                systeme=systeme, personnage=nom, cote=invite["llm"]["cote_vision"],
                dire=dire)
            choix.references = references
            choix.secondes += secondes
            choix.appels_llm += appels
        else:
            choix.references = selection_mod.choisir(
                candidates, plafond=invite["references_max"],
                usage=selection_mod.USAGE_IDENTITE)
        choix.ancrages = list(ancres_jugees.choix)
        if not selections:
            # ⚠ Le coût des ancres est compté UNE fois, sur le premier personnage — parce
            # qu'il n'a été dépensé qu'une fois. Le répéter à chaque bloc gonflerait
            # `phase1.secondes` d'un temps imaginaire, et le plan demande précisément de
            # comparer ce temps-là à celui de la phase 2.
            choix.secondes += ancres_jugees.secondes
            choix.appels_llm += ancres_jugees.appels
        retenues = choix.retenues(selection_mod.USAGE_IDENTITE)
        dire(f"  {nom} : {len(retenues)} référence(s) retenue(s) sur {len(candidates)} "
             f"candidate(s)"
             + (f", {len(choix.retenues(selection_mod.USAGE_ANCRAGE))} ancre(s) de style"
                if choix.ancrages else ""))
        _dire_les_couvertures(retenues, candidates, dire)
        selections[nom] = choix
    return selections


def _dire_les_couvertures(retenues, candidates, dire) -> None:
    """Dit à l'utilisateur qu'une COUVERTURE est envoyée au modèle — **pendant le run**.

    ⚠ La faille est nommée dans le code (`identite.TITRE_DANS_LES_PIXELS`) : le garde de
    marquage refuse le titre de l'œuvre dans le TEXTE des métadonnées, il ne voit pas un
    titre **peint dans une image**. Une couverture de light novel en porte un en grandes
    lettres, ces pixels partent dans le conditionnement, et rien n'empêche le modèle de les
    reproduire.

    ⚠ **Ce n'est pas un refus** : un personnage dont la couverture est la seule référence
    n'a pas d'autre choix, et la lui retirer produirait zéro image au lieu d'une image
    imparfaite. Mais l'utilisateur doit le savoir sans lire les sources — et il le lit deux
    fois : ici pendant le run, et dans le `motif` de l'image dans `requete.yaml`."""
    couvertures = {c.fichier for c in candidates if c.couverture}
    prises = [c for c in retenues if c.fichier in couvertures]
    if prises:
        dire(f"    ⚠ dont {len(prises)} COUVERTURE(S) — {ident_mod.TITRE_DANS_LES_PIXELS}.")


@dataclass
class _Ancres:
    """Les ancres de style du tome, jugées **une seule fois**, avec leur coût."""

    choix: list = field(default_factory=list)
    secondes: float = 0.0
    appels: int = 0


def _ancrages_pour(candidates, reg: dict, llm, modele: str, systeme: str, dire) -> _Ancres:
    """Les ancres de style, **ou aucune**, selon `illustration.prompt.style`.

    ⚠ `ancrages_max` vaut **0** par défaut, donc l'approche 2 de l'étape 0.2 est DÉSARMÉE.
    C'est une mesure qui le décide, publiée dans `docs/mesures/` : lire son tableau avant de
    la remonter. Le mécanisme est complet et se teste ; ce qui n'est pas soutenu par la
    mesure est livré désarmé, comme `manga.onomatopees.effacement.mode: "aucun"`.

    ⚠ **Elles sont jugées une fois pour tout le tome.** Une ancre décrit le registre
    graphique de l'ŒUVRE, pas d'un personnage : redemander au modèle, pour chacun des onze
    personnages, si la même image de décor porte un visage coûte onze fois le même appel pour
    la même réponse."""
    invite = reg["prompt"]
    if invite["style"] != "ancrages" or invite["ancrages_max"] <= 0 or not candidates:
        return _Ancres()
    if llm is not None and modele:
        choix, secondes, appels = selection_mod.choisir_avec_llm(
            candidates, plafond=invite["ancrages_max"], usage=selection_mod.USAGE_ANCRAGE,
            llm=llm, modele=modele, systeme=systeme, cote=invite["llm"]["cote_vision"],
            dire=dire)
        return _Ancres(choix=choix, secondes=secondes, appels=appels)
    return _Ancres(choix=selection_mod.choisir(candidates, plafond=invite["ancrages_max"],
                                               usage=selection_mod.USAGE_ANCRAGE))


def _prompt_de_selection(config: dict, reg: dict, dire) -> tuple[str, str]:
    """`(texte du prompt système, nom du modèle)`, depuis le pack de langue.

    ⚠ `illustration_style` est **hors** `core.langues.PROMPTS_REQUIS` : les huit prompts de
    ce tuple sont ceux dont l'absence fait échouer `_verifier_prompts` et invaliderait le
    pack `langues/en`. Le modèle est `manga_relecteur.md` — livré dans les deux packs,
    absent du tuple. Son absence est donc signalée ici, pas au démarrage du dépôt."""
    systeme = _prompt_du_pack(config, selection_mod.PROMPT, dire)
    if not systeme:
        return "", ""
    # ⚠ `modeles.traducteur` peut être une CHAÎNE ou un dict `{model, endpoint}` — la config
    # livrée écrit la seconde forme. `cli.models_in_config` est LA règle du dépôt pour lire
    # les deux ; en écrire une seconde ici a coûté un run bloqué le 2026-08-30, le nom de
    # modèle envoyé à Ollama étant la représentation Python du dictionnaire.
    modele = reg["prompt"]["llm"]["modele"] or _modele_par_defaut(config)
    if not modele:
        dire("  ⚠ aucun modèle nommé (illustration.prompt.llm.modele, ni "
             "modeles.traducteur) : le choix d'images reste déterministe.")
        return "", ""
    return systeme, modele


def _llm(config: dict):
    """Le client d'inférence local. Construit ici et non importé en tête : `--version` et
    `--check` n'ont pas à charger le SDK OpenAI."""
    from core.llm import LLM

    # ⚠ `config["llm"]`, pas `config["ollama"]` : c'est la clé du dépôt, celle que
    # `core/cli.py` et `core/agents.py` lisent déjà. Une seconde convention ici enverrait les
    # appels ailleurs que la traduction sans que rien ne le dise.
    llm_cfg = dict(config.get("llm") or {})
    return LLM(base_url=str(llm_cfg.get("base_url") or "http://localhost:11434/v1"),
               api_key=str(llm_cfg.get("api_key") or "ollama"),
               # ⚠ `think=False` : la sélection d'images demande TROIS LIGNES. Laisser le
               # raisonnement actif y ferait partir l'essentiel de la génération dans un
               # `<think>` — mesuré au light novel, 74 à 97 % des jetons.
               timeout=int(llm_cfg.get("timeout") or 600), think=False)


# ─────────────────────────────────  Phase 2  ─────────────────────────────────

def phase_image(projet: str, config: dict, *, tome: str | None = None, reporter=None,
                moteur=None, chemin_config: str = "config.yaml",
                avancement=None, annulation=None) -> dict:
    """Lit `requete.yaml`, **refuse `valide: false`**, bascule la VRAM, écrit les PNG marqués.

    ⚠ `chemin_config` est un ARGUMENT et non une clé glissée dans le dictionnaire de config :
    `core/config.verifier` compare l'arbre réel à `CLES_CONNUES` et signalerait toute clé
    inventée. Un faux avertissement au démarrage est pire que pas de vérification du tout —
    c'est ce que `core/config_schema.py` écrit noir sur blanc.

    ⚠ **`avancement` et `annulation` sont le lot 27 (L27.2), et ils sont facultatifs.** Sans
    eux, le comportement est exactement celui du lot 26 : c'est ce qui garde `--phase image`
    iso.

    - `avancement` est une `progression.Progression` : la fonction la fait passer par ses
      trois phases et compte les images terminées. L'interface n'a alors plus rien à deviner.
    - `annulation` est un appelable sans argument qui rend `True` quand l'utilisateur a
      demandé l'arrêt. Il est consulté **entre deux images**, jamais au milieu : un modèle
      d'image interrompu en plein pas de débruitage laisse le pilote AMD dans le mauvais état
      que `docs/README.fr.md` a mesuré à 25 → 18 tok/s. Les images déjà écrites sont gardées,
      marquées, rapportées — un arrêt propre, comme le fichier `STOP` du manga.

    ⚠ **La bascule VRAM se ferme sur TOUS les chemins de sortie** — succès, erreur,
    annulation —, ce qui n'était pas le cas jusqu'ici : `_rendre_la_vram` vivait après le bloc
    de génération, et une exception sautait par-dessus. Voir `illustration/vram.py`."""
    from illustration import progression as progression_mod

    reg = exiger_actif(config)
    dire = _dire(reporter)
    avancement = avancement or progression_mod.Progression()
    avancement.demarrer(progression_mod.PREPARATION)
    sortie = dossier(config, projet)
    racine = racine_projet(config, projet)
    cible = requete_mod.chemin(sortie)
    if not cible.is_file():
        raise FileNotFoundError(
            f"{cible} n'existe pas — la phase image lit ce que la phase prompt a écrit.\n"
            f"  → python run_illustration.py \"{projet}\" --phase prompt")

    doc = requete_mod.load(cible)
    requete_mod.exiger_validation(doc)                   # LA porte. Elle lève, elle n'avertit pas.
    # ⚠ Le SECOND battant, ajouté au lot 26 : on ne peut pas décocher toutes les références.
    # Il est ici, avant la bascule VRAM, pour que le refus ne coûte pas le déchargement du
    # LLM et le chargement de 12 Go de poids.
    requete_mod.exiger_references_retenues(doc)
    problemes = requete_mod.verifier(doc, racine_projet=racine)
    if problemes:
        raise ValueError("requete.yaml validé mais incohérent — rien n'est généré :\n  "
                         + "\n  ".join(problemes))

    # ⚠ Le moteur est construit et TOUS ses canaux sont vérifiés AVANT la bascule VRAM.
    # Refuser un canal après avoir déchargé le LLM et chargé 12 Go de poids coûterait
    # plusieurs minutes pour une erreur connue d'avance — constaté le 2026-08-29 au premier
    # run réel, où la requête portait des références qu'un workflow texte-vers-image ne sait
    # pas honorer.
    moteur = moteur or construire_moteur(reg, racine)
    if not moteur.disponible():
        raise RuntimeError(
            f"le moteur « {getattr(moteur, 'nom', '?')} » n'est pas disponible.\n"
            f"  → python run_illustration.py --check")
    # LOT 25 — la voie A. Les références de la bible sont préparées et branchées AVANT la
    # vérification des canaux : c'est elle qui doit refuser un workflow texte-vers-image, et
    # elle ne peut le faire que si la requête porte déjà ses références.
    travaux, identite_ctx = _brancher_identite(config, projet, reg, doc, sortie, dire)
    travaux, plafonds = _developper(travaux, doc, reg["budget"]["images_par_run"], dire)
    for _, _, _requete, _ in travaux:
        moteur_mod.verifier_canaux(moteur, _requete)
    _valider_le_graphe(reg, dire)

    avancement.total_images = len(travaux)
    avancement.demarrer(progression_mod.BASCULE)
    bascule_ctx = _bascule(config, reg, dire)
    bascule = bascule_ctx.ouvrir()
    avancement.demarrer(progression_mod.GENERATION)

    identifiant = marquage.identifiant_oeuvre(
        projet, "", reg["marquage"]["identifiant_oeuvre"])
    # ⚠ `prompt_initial` n'est PAS recopié ici : c'est le dictionnaire de TOUTES les images,
    # et le répéter dans chaque sidecar y mettrait le prompt des autres. Chaque manifeste ne
    # porte que le sien, avant et après correction.
    validation = {"par": doc["validation"]["par"], "date": doc["validation"]["date"]}
    initiales = doc["validation"]
    empreintes = _empreintes(reg, chemin_config)
    produites: list[dict] = []

    rejetees: list[dict] = []
    verdicts: list = []
    arret: str = ""

    try:
        with frontiere.perimetre(sortie):
            for nom, origine, requete, sources in travaux:
                # ⚠ **Entre deux images, jamais au milieu de l'une.** Un modèle d'image
                # interrompu en plein pas de débruitage laisse le pilote AMD dans l'état que
                # `docs/README.fr.md` a mesuré : 25 → 18 tok/s pour la traduction suivante. Un
                # arrêt propre coûte au pire une image de plus ; un arrêt sale coûte la session.
                if annulation is not None and annulation():
                    avancement.demander_l_annulation()
                    arret = (f"annulé à la demande — {len(produites)} image(s) sur "
                             f"{len(travaux)} sont écrites et marquées, elles sont gardées.")
                    dire(f"  ⚠ {arret}")
                    break
                depart = time.monotonic()
                resultat = moteur.generer(requete)
                secondes = resultat.secondes or (time.monotonic() - depart)
                resultat = _avec_duree(resultat, secondes)
                # ⚠ Le jugement a lieu AVANT l'écriture, sur les octets rendus par le moteur. Le
                # plan demande qu'une image trop proche de sa référence soit REJETÉE ; ne pas
                # l'écrire est plus net que l'écrire puis l'effacer, et ne laisse aucune fenêtre
                # pendant laquelle un fichier rejeté existe sur le disque.
                _verifier_le_modele(doc["modele"], resultat, dire)
                grandeurs, verdict = _juger(identite_ctx, resultat.png, sources)
                if verdict is not None:
                    verdicts.append(verdict)
                if verdict is not None and verdict.rejetee:
                    rejetees.append({"nom": nom, "motifs": list(verdict.motifs),
                                     "grandeurs": grandeurs.resume() if grandeurs else {}})
                    dire(f"  ✗ {nom} REJETÉE — {' · '.join(verdict.motifs)}")
                    continue
                provenance = marquage.manifeste(
                    requete, resultat, projet=projet, tome=tome or "", identifiant=identifiant,
                    validation={**validation,
                                "prompt_apres_correction": requete.prompt,
                                "prompt_avant_correction":
                                    doc["validation"]["prompt_initial"].get(origine, "")},
                    config_sha256=empreintes["config"], poids_sha256=empreintes["poids"],
                    # ⚠ Le modèle EFFECTIF, pas celui que l'étiquette annonce. Cf.
                    # `_verifier_le_modele` : un manifeste qui se trompe de modèle est pire qu'un
                    # manifeste sans modèle, parce qu'il a l'air vérifiable.
                    modele=_modele_effectif(doc["modele"], resultat),
                    identite=_bloc_identite(grandeurs, verdict, identite_ctx),
                    prompt_source=_bloc_prompt(doc, initiales, origine))
                image, manifeste = marquage.ecrire(
                    resultat, sortie / f"{nom}.png", provenance=provenance)
                produites.append({"nom": nom, "origine": origine,
                                  "image": image, "manifeste": manifeste,
                                  "secondes": secondes, "graine": requete.graine,
                                  "empreinte_requete": requete.empreinte(),
                                  "vram_pic_octets": resultat.vram_pic_octets,
                                  "grandeurs": grandeurs.resume() if grandeurs else None,
                                  "marques": dict(verdict.marques) if verdict else {}})
                marques = " ".join(f"[{c}: {v}]"
                                   for c, v in (verdict.marques if verdict else {}).items())
                dire(f"  ✓ {image.name} — {secondes:.1f} s "
                     f"(graine {requete.graine}) {marques}".rstrip())

            recap = {"projet": projet, "tome": tome or "(œuvre entière)",
                     "dossier": sortie, "images": produites,
                     "modele": doc["modele"], "moteur": getattr(moteur, "nom", "?"),
                     "bascule_secondes": bascule, "identifiant": identifiant,
                     "validation": validation, "empreintes": empreintes,
                     "rejetees": rejetees, "identite_active": bool(identite_ctx),
                     "plafonds_atteints": plafonds,
                     "phase1_secondes": doc["phase1"]["secondes"],
                     "phase1_appels_llm": doc["phase1"]["appels_llm"],
                     "blocs": {b["nom"]: b for b in doc["images"]},
                     "refus": list((identite_ctx or {}).get("refus") or []),
                     "motifs": _tous_les_motifs(verdicts, identite_ctx)}
            recap["arret"] = arret
            recap["progression"] = avancement.etat()
    finally:
        # ⚠ **Sur TOUS les chemins de sortie**, y compris l'exception et l'annulation. C'est
        # le correctif du lot 27 : `_rendre_la_vram` vivait après le bloc, et une erreur de
        # moteur sautait par-dessus en laissant 12 Go de transformeur sur la carte.
        avancement.terminer()
        recap_vram = bascule_ctx.fermer(moteur)
        for _, message in recap_vram["journal"]:
            dire(f"  VRAM : {message}")
    # ⚠ Le rapport s'écrit APRÈS la fermeture de la bascule, et pas avant : sinon sa section
    # « la carte, en fin de run » décrirait un état qui n'a pas encore eu lieu. Le périmètre
    # est ré-armé pour cette seule écriture — la frontière ne se suspend jamais.
    recap["vram"] = recap_vram
    with frontiere.perimetre(sortie):
        rapport.ecrire(recap, sortie)
        rapport.perf(recap, sortie)
    dire(rapport.verdict_bascule(recap))
    dire(f"Phases : {avancement.resume()}")
    return recap


def _bascule(config: dict, reg: dict, dire):
    """La bascule VRAM du run, avec ses deux opérations coûteuses **injectées**.

    Elles le sont pour que `illustration/vram.py` se teste sans serveur Ollama, sans réseau et
    sans GPU — c'est-à-dire en CI, là où le critère 4 du `PLAN-27` (« l'annulation décharge la
    VRAM et recharge le LLM. Testé, y compris sur erreur ») doit se vérifier."""
    from core import cli
    from illustration import vram as vram_mod

    # ⚠ `dict.fromkeys` et non `set` : l'ordre doit rester déterministe pour que deux runs se
    # comparent. Et le dédoublonnage n'est pas cosmétique — `models_in_config` dédoublonne
    # DANS une section, pas ENTRE deux : `modeles.traducteur` et
    # `manga.modeles.manga_traducteur` désignent le même `yume-27b` dans la config livrée, et
    # l'appeler deux fois coûte 2,0 s pour rien. Mesuré le 2026-08-29, trois essais :
    # 4,22 / 4,14 / 4,05 s à deux appels contre 2,03 s à un seul.
    modeles = tuple(dict.fromkeys(cli.models_in_config(config)
                                  + cli.models_in_config(config, "manga")))
    llm_cfg = dict(config.get("llm") or {})
    base_url = llm_cfg.get("base_url")
    return vram_mod.Bascule(
        modeles=modeles,
        decharger_llm=reg["vram"]["decharger_llm"],
        decharger_image=reg["vram"]["decharger_image"],
        recharger_llm=reg["vram"]["recharger_llm"],
        decharge=lambda noms: cli.shielded_unload(config, noms),
        recharge=lambda noms: cli.precharger_modeles(config, noms, dry_run=False,
                                           base_url=base_url),
        dire=dire)


def rejouer(chemin_manifeste, config: dict, *, reporter=None, moteur=None,
            destination=None) -> dict:
    """Rejoue une requête passée depuis son sidecar de provenance.

    ⚠ Le rejeu ne repasse **pas** par la porte humaine, et il n'a pas à le faire : le prompt
    rejoué est celui qu'un humain a déjà validé, archivé mot pour mot dans le manifeste. Ce
    qu'il permet de vérifier est la question de L24.5 — deux exécutions de la même requête
    produisent-elles deux PNG identiques octet pour octet ?"""
    import json

    from illustration.moteur import Requete

    dire = _dire(reporter)
    chemin_manifeste = Path(chemin_manifeste)
    ancien = json.loads(chemin_manifeste.read_text(encoding="utf-8"))
    requete = Requete.depuis_payload(ancien.get("payload") or {})
    reg = exiger_actif(config)
    sortie = Path(destination) if destination else chemin_manifeste.parent
    moteur = moteur or construire_moteur(reg, sortie.parent)

    with frontiere.perimetre(sortie):
        depart = time.monotonic()
        resultat = _avec_duree(moteur.generer(requete), time.monotonic() - depart)
        nom = chemin_manifeste.name.replace(marquage.SUFFIXE_PROVENANCE, "")
        cible = sortie / f"{Path(nom).stem}.rejeu.png"
        provenance = marquage.manifeste(
            requete, resultat, projet="", tome="",
            identifiant=str(ancien.get("oeuvre") or ""),
            validation={**(ancien.get("validation_humaine") or {}),
                        "rejeu_de": chemin_manifeste.name},
            config_sha256=str(ancien.get("config_sha256") or ""),
            poids_sha256=str(ancien.get("poids_sha256") or ""),
            modele=str(ancien.get("modele") or ""))
        image, manifeste = marquage.ecrire(resultat, cible, provenance=provenance)

    identiques = (marquage.empreinte_fichier(image)
                  == str(ancien.get("image_sha256") or "\x00"))
    dire(f"Rejeu écrit : {image}")
    dire("  → octet pour octet identique à l'original." if identiques else
         "  → DIFFÉRENT de l'original. Ce n'est pas forcément un défaut : la plupart des "
         "backends de diffusion ne sont pas déterministes d'une exécution à l'autre. "
         "Mesure l'écart et publie-le plutôt que d'affirmer la reproductibilité.")
    return {"image": image, "manifeste": manifeste, "identique": identiques,
            "empreinte_requete": requete.empreinte()}


# ────────────────────────  LOT 26 — le budget d'un run  ────────────────────────

def _developper(travaux, doc: dict, plafond: int, dire) -> tuple[list, list]:
    """`nombre_images` images par bloc, et le **plafond du run** appliqué au total.

    Rend `[(nom du fichier, nom du bloc, Requete, sources)]` et les motifs d'arrêt.

    ⚠ **Le plafond porte sur les IMAGES, pas sur les personnages**, parce que c'est l'image
    qui coûte : le lot 25 a relevé 103,7 s en médiane et jusqu'à 1 524 s selon ce que ComfyUI
    garde en VRAM. Un tome fait vingt illustrations ; un `nombre_images: 4` sur huit
    personnages en fait trente-deux, et personne ne l'a demandé.

    ⚠ **Le motif d'arrêt est NOMMÉ, pas silencieux.** Le dépôt a une culture du plafond —
    `garde_fous.abandon_apres_timeouts_consecutifs`, `decoupage.max_input_tokens` — et un
    plafond qui mord sans le dire ferait croire à un corpus plus petit qu'il n'est.

    ⚠ **La graine s'incrémente d'une image à l'autre du même bloc.** Sans ça, quatre images
    de même requête seraient quatre fois la même image : la graine entre dans le payload,
    donc dans l'empreinte, donc dans le sidecar — c'est ce qui rend `--rejouer` capable de
    reproduire l'image n° 3 et pas seulement la première."""
    par_bloc = {b["nom"]: int(b.get("nombre_images") or 1) for b in doc["images"]}
    developpes, plafonds = [], []
    for nom, requete, sources in travaux:
        combien = max(1, par_bloc.get(nom, 1))
        for index in range(combien):
            fichier = nom if combien == 1 else f"{nom}-{index + 1}"
            developpes.append((fichier, nom,
                               requete.avec(graine=requete.graine + index), sources))
    if plafond > 0 and len(developpes) > plafond:
        plafonds.append(
            f"plafond d'images atteint : {len(developpes)} demandées, {plafond} produites "
            f"(illustration.budget.images_par_run). Les suivantes ne sont PAS générées.")
        dire(f"  ⚠ {plafonds[-1]}")
        developpes = developpes[:plafond]
    return developpes, plafonds


# ────────────────────────  LOT 25 — la voie A, branchée ou non  ────────────────────────

def _brancher_identite(config: dict, projet: str, reg: dict, doc: dict, sortie: Path,
                       dire) -> tuple[list, dict | None]:
    """Rend `[(nom, Requete, sources des références)]` et le contexte de jugement.

    ⚠ **Depuis le lot 26, la phase 2 HONORE le fichier relu ; elle ne redérive plus rien.**
    C'était le défaut du lot 25 : `requete.yaml` portait des références, et la phase 2 les
    recalculait depuis la bible — donc un utilisateur qui en décochait une la voyait revenir.
    Une porte humaine dont les décisions sont recalculées derrière n'est pas une porte. Les
    fichiers viennent maintenant de `references[retenue: true]`, et la bible ne sert plus
    qu'à **vérifier** qu'ils sont validés et à fournir leur boîte de recadrage.

    ⚠ **`illustration.identite.actif: false` (le défaut) rend exactement ce que le lot 24
    rendait** : les requêtes du fichier, telles quelles, et aucun contexte. C'est
    l'iso-comportement qu'exige le §9.3 du contexte agent, et il se vérifie en une ligne
    plutôt que de se raisonner sur trois branches.

    ⚠ **Le refus du critère 5 du `PLAN-25` se pose ICI**, avant la bascule VRAM et avant la
    première seconde de GPU : un personnage dont aucune référence retenue n'est validée par
    un humain fait lever, il ne produit pas une image « au mieux »."""
    if not reg["identite"]["actif"]:
        return [(nom, requete, ()) for nom, requete in requete_mod.requetes(doc)], None

    bible_doc = bible_mod.load(bible_mod.chemin(dossier_projet(config, projet)))
    racine = racine_projet(config, projet)
    travaux, refus = [], []
    with frontiere.perimetre(sortie):
        for (nom, requete), bloc in zip(requete_mod.requetes(doc), doc["images"]):
            personnage = str(bloc.get("personnage") or "").strip()
            choisies, ancres = requete_mod.images_retenues(bloc)
            if not personnage:
                # Un bloc sans personnage n'est pas du ressort de la voie A : elle porte sur
                # l'identité d'une personne nommée dans la bible.
                travaux.append((nom, requete, ()))
                continue
            references = ident_mod.references_de(bible_doc, personnage, racine)
            par_fichier = {r.fichier: r for r in references}
            retenues = [par_fichier[c["fichier"]] for c in choisies
                        if c["fichier"] in par_fichier and par_fichier[c["fichier"]].validee]
            if not retenues:
                # ⚠ Le refus porte sur CETTE image, pas sur le run. Sur le corpus réel, 7
                # personnages sur 11 n'ont aucune référence validée : faire échouer le run
                # entier rendrait la voie A inutilisable et pousserait à la contourner.
                dire(f"  ✗ {personnage} : refus — "
                     f"{ident_mod.MOTIFS_LISIBLES['sans_reference_validee']}")
                refus.append({"nom": nom, "personnage": personnage,
                              "motifs": ["sans_reference_validee"],
                              "message": f"aucune des {len(choisies)} référence(s) retenue(s) "
                                         f"n'est validée par un humain dans la bible"})
                continue
            ancrages = _ancrages_retenus(bible_doc, ancres, racine)
            preparees = ident_mod.preparer_toutes(
                retenues + ancrages, personnage, sortie,
                cote=reg["identite"]["cote_reference"])
            dire(f"  {personnage} : {len(retenues)} référence(s) + {len(ancrages)} ancre(s) "
                 f"préparée(s)")
            couvertures = [r for r in retenues if r.couverture]
            if couvertures:
                # ⚠ Pas un refus : un personnage dont la couverture est la seule référence
                # n'a pas d'autre choix. Mais l'utilisateur doit le savoir sans lire le code.
                dire(f"    ⚠ dont {len(couvertures)} COUVERTURE(S) — "
                     f"{ident_mod.TITRE_DANS_LES_PIXELS}.")
            travaux.append((nom, requete.avec(
                references=tuple(str(p.relative_to(sortie.parent)) for p in preparees)),
                # ⚠ Seules les références d'IDENTITÉ servent au juge. Mesurer la ressemblance
                # à une ancre de style dirait « l'image ressemble au tome », pas « l'image
                # ressemble au personnage » — c'est exactement la confusion des deux échelles
                # que le lot 25 interdit de faire.
                tuple(r.source for r in retenues)))

    if not travaux:
        raise ident_mod.SansReferenceValidee(
            f"aucune des {len(refus)} image(s) demandée(s) n'a de référence validée par un "
            f"humain — il n'y a rien à générer.\n"
            f"  Personnages refusés : {', '.join(r['personnage'] for r in refus)}.\n"
            f"  → python tools/bible.py --revue pour poser `confiance: humaine` sur les "
            f"recadrages que tu as regardés.")
    contexte = _contexte_de_jugement(reg, projet, config)
    contexte["refus"] = refus
    return travaux, contexte


def _ancrages_retenus(bible_doc: dict, choisies, racine) -> list:
    """Les ancres de style retenues, en `identite.Reference` — pour passer par le même
    préparateur que les références.

    ⚠ Elles restent **distinctes** des références d'identité dans tout ce qui suit : le
    prompt les désigne à part (`gabarits.designation_ancrages`), et le juge ne les compte
    pas dans la ressemblance. Le canal d'images, lui, ne sait pas les distinguer — c'est
    justement pourquoi le texte doit le faire."""
    par_fichier = {}
    for brute in ((bible_doc or {}).get("style") or {}).get("ancrages") or []:
        if not isinstance(brute, dict) or not brute.get("valide_par_humain"):
            continue
        fichier = str(brute.get("fichier") or "")
        source = ident_mod.resoudre(fichier, racine)
        if source is not None:
            par_fichier[fichier] = ident_mod.Reference(
                fichier=fichier, source=source, confiance="humaine",
                contexte=str(brute.get("motif") or ""),
                classe=str(brute.get("classe") or ""))
    return [par_fichier[c["fichier"]] for c in choisies if c["fichier"] in par_fichier]


def _contexte_de_jugement(reg: dict, projet: str, config: dict) -> dict:
    """L'encodeur, les planchers et la signature du tome — ou un contexte sans juge.

    ⚠ **Un encodeur absent n'arrête pas le run** : les images sont produites et le manifeste
    porte `juge_indisponible`. Refuser de générer parce qu'on ne sait pas mesurer serait
    confondre l'instrument avec la chose mesurée — et le plan prévoit explicitement le cas
    où le juge automatique n'existe pas, en renvoyant au juge humain."""
    ident = reg["identite"]
    chemin = Path(ident["encodeur"]["dossier"]) / (ident["encodeur"]["fichier"] or "")
    encodeur = None
    if ident["encodeur"]["fichier"]:
        from illustration.juge import Encodeur
        candidat = Encodeur(chemin, agregation=ident["encodeur"]["agregation"],
                            cadrage=ident["encodeur"]["cadrage"],
                            cote=ident["encodeur"]["cote"])
        encodeur = candidat if candidat.disponible() else None
    bible_doc = bible_mod.load(bible_mod.chemin(dossier_projet(config, projet)))
    style = bible_doc.get("style") or {}
    racine = racine_projet(config, projet)
    ancrages = [c for c in (ident_mod.resoudre(str(a.get("fichier") or ""), racine)
                            for a in (style.get("ancrages") or [])
                            if isinstance(a, dict) and a.get("valide_par_humain"))
                if c is not None]
    planchers = ident_mod.Planchers(**ident["planchers"])
    return {"encodeur": encodeur, "ancrages": ancrages,
            "signature": style.get("signature") or {}, "planchers": planchers,
            "encodeur_chemin": str(chemin)}


def _juger(contexte: dict | None, png: bytes, sources):
    """Les trois grandeurs et le verdict d'une image, **avant** son écriture."""
    if contexte is None:
        return None, None
    if contexte["encodeur"] is None:
        return None, ident_mod.juger(None, contexte["planchers"])
    from illustration import juge as juge_mod
    grandeurs = juge_mod.mesurer(contexte["encodeur"], png, references=sources,
                                 ancrages=contexte["ancrages"],
                                 signature_tome=contexte["signature"])
    return grandeurs, ident_mod.juger(grandeurs, contexte["planchers"])


#: Une seule fois par run : la même requête produit le même désaccord sur chaque image, et le
#: répéter onze fois noierait le reste du journal.
_MODELE_SIGNALE: set = set()


def _modele_effectif(declare: str, resultat) -> str:
    """Le nom du modèle à écrire dans le PNG et le sidecar : celui que le graphe a **chargé**.

    L'étiquette de `requete.yaml` l'emporte tant qu'elle est cohérente avec ce que le moteur
    rapporte — elle est plus lisible qu'un nom de fichier. Dès qu'elle ne l'est pas, c'est le
    relevé qui gagne : c'est lui qui décrit l'image."""
    charges = [str(m) for m in ((resultat.provenance or {}).get("modeles") or [])]
    declare = str(declare or "").strip()
    if not charges:
        return declare
    if declare and any(declare in nom for nom in charges):
        return declare
    return " + ".join(Path(nom).stem for nom in charges)


def _verifier_le_modele(declare: str, resultat, dire) -> None:
    """Signale quand le modèle DÉCLARÉ dans `requete.yaml` n'est pas celui que le graphe charge.

    ⚠ **Défaut de provenance trouvé le 2026-08-29.** `requete.yaml` porte un champ `modele`
    écrit par la phase 1 d'après la configuration d'alors ; la phase 2 le recopiait dans le
    sidecar sans le confronter à rien. Un `requete.yaml` validé la veille annonçait
    `qwen-image-2512-Q4_1` pendant que le graphe d'édition chargeait
    `qwen-image-edit-2511-Q4_1`. Un manifeste qui se trompe de modèle est pire qu'un manifeste
    sans modèle : il a l'air vérifiable.

    Il **avertit** et n'arrête pas : le champ `modele` est une étiquette humaine, et la vérité
    mécanique — les fichiers que le graphe nomme — part de toute façon dans le sidecar sous
    `moteur_details.modeles`. Arrêter un run de plusieurs minutes sur une étiquette serait
    disproportionné ; le taire ne le serait pas moins."""
    charges = list((resultat.provenance or {}).get("modeles") or [])
    declare = str(declare or "").strip()
    if not charges or not declare:
        return
    if any(declare in nom for nom in charges):
        return
    cle = (declare, tuple(charges))
    if cle in _MODELE_SIGNALE:
        return
    _MODELE_SIGNALE.add(cle)
    dire(f"  ⚠ requete.yaml déclare le modèle « {declare} », mais le graphe charge "
         f"{', '.join(charges)}.")
    dire("    Le sidecar porte les DEUX : `modele` (ce que l'humain a validé) et "
         "`moteur_details.modeles` (ce que le graphe a réellement chargé). Corrige `modele` "
         "dans requete.yaml si l'étiquette est fausse.")


def _tous_les_motifs(verdicts, contexte: dict | None) -> dict:
    """Les motifs des images produites **et** ceux des personnages refusés, dans le même
    compte. Deux comptes séparés laisseraient croire qu'un refus n'est pas un motif."""
    refuses = [ident_mod.Verdict(motifs=list(r["motifs"]))
               for r in ((contexte or {}).get("refus") or [])]
    return ident_mod.compter_motifs(list(verdicts) + refuses)


def _bloc_prompt(doc: dict, validation: dict, nom_bloc: str) -> dict:
    """Ce qui a fabriqué ce prompt — **L26.3, la reproductibilité jusqu'au bout**.

    Le critère 6 du `PLAN-26` demande qu'« depuis un sidecar seul, on puisse régénérer la
    même image ». Le payload suffit pour rejouer le MOTEUR ; il ne suffit pas pour rejouer la
    PHASE 1. Ce bloc porte donc ce que le payload ne porte pas : le gabarit et son empreinte,
    la forme du champ texte, la langue, le cadrage, et d'où vient chaque attribut.

    ⚠ **L'empreinte du gabarit compte autant que son nom.** C'est le même esprit que
    `git checkout <tag> -- langues/` pour reproduire la voix d'un tome : un gabarit nommé
    mais édité depuis produirait un autre prompt sous le même nom, et rien ne le dirait."""
    from illustration import gabarits as gabarits_mod

    bloc = (doc.get("blocs") or {}).get(nom_bloc) or {}
    if not bloc:
        bloc = next((b for b in doc["images"] if b["nom"] == nom_bloc), {})
    return {
        "gabarit": doc["gabarit"],
        "gabarit_sha256": gabarits_mod.empreinte(doc["gabarit"]),
        "forme": doc["forme"],
        "langue": doc["langue"],
        "cadrage": bloc.get("cadrage", ""),
        # ⚠ **L29.4.** Deux images produites avec « sur fond neutre » et « sur un fond tramé »
        # ne diffèrent, dans le payload, que par une poignée de mots au milieu d'un prompt.
        # Sans ce champ, la mesure de la part d'aplats — le critère 5 du PLAN-29 — ne saurait
        # pas, image par image, laquelle est laquelle.
        "decor": bloc.get("decor", ""),
        "personnage": bloc.get("personnage", ""),
        "attributs_sources": list(bloc.get("attributs_sources") or []),
        "references_initiales":
            list((validation.get("references_initiales") or {}).get(nom_bloc) or []),
        "avertissement": (
            "le payload rejoue le MOTEUR ; ce bloc rejoue la PHASE 1 — sans lui, on sait "
            "quel texte a été envoyé mais pas d'où il venait"),
    }


def _bloc_identite(grandeurs, verdict, contexte: dict | None) -> dict | None:
    """Ce que le sidecar de provenance porte en plus, quand la voie A est armée.

    ⚠ Il porte aussi **les planchers** : un score sans le seuil auquel on l'a comparé n'est
    pas une mesure. C'est la règle des chiffres du dépôt, appliquée à un fichier JSON."""
    if contexte is None:
        return None
    return {
        "grandeurs": grandeurs.resume() if grandeurs else None,
        "verdict": verdict.resume() if verdict else None,
        "planchers": contexte["planchers"].resume(),
        "encodeur": Path(contexte["encodeur_chemin"]).name,
        "ancrages_de_style": len(contexte["ancrages"]),
        "avertissement": (
            "les planchers viennent de l'étalonnage publié dans docs/mesures/ ; un score sans "
            "son seuil n'est pas une mesure"),
    }


# ──────────────────────────────  Les rouages  ──────────────────────────────

def _valider_le_graphe(reg: dict, dire) -> None:
    """Les cinq vérifications du lot 28, **avant la bascule VRAM**. Lève sur un refus.

    ⚠ **C'est le même contrôle que `run_illustration.py --check`, au même endroit que la
    vérification des canaux** — c'est-à-dire avant que le LLM ne soit déchargé et avant que
    12,84 Go de poids ne soient chargés. Un modèle renommé, un nœud tiers désinstallé ou un
    guidage incompatible avec la LoRA du graphe coûtaient jusqu'ici plusieurs minutes et une
    carte rendue pour rien.

    ⚠ **Un moteur qui n'est pas ComfyUI n'a pas de graphe**, et un serveur injoignable ne
    prouve rien : dans les deux cas on ne dit rien plutôt que d'inventer un refus. La sonde
    rend un relevé qui DIT qu'il ne sait pas, et le validateur en déduit « non fait »."""
    if reg["moteur"] != "comfyui" or not reg["comfyui"]["workflow"]:
        return
    from illustration import sonde as sonde_mod
    from illustration import validation as validation_mod

    releve = sonde_mod.sonder(reg["comfyui"]["base_url"])
    rapport = validation_mod.valider(reg["comfyui"]["workflow"], releve=releve,
                                     pas=reg["image"]["pas"], guidage=reg["image"]["guidage"])
    for constat in rapport.reserves:
        for ligne in constat.lignes():
            dire("  " + ligne)
    refus = list(rapport.refus) + [c for c in validation_mod.verifier_vram(releve)
                                   if c.gravite == "refus"]
    if not refus:
        return
    raise ValueError(
        "le graphe est refusé AVANT la bascule VRAM — rien n'a été déchargé, rien n'a été "
        "chargé :\n  " + "\n  ".join("\n  ".join(c.lignes()) for c in refus)
        + "\n  → python tools/comfy.py --valider")


def construire_moteur(reg: dict, racine_tome):
    """Le moteur nommé par `illustration.moteur`. Deux implémentations, pas trois."""
    nom = reg["moteur"]
    if nom == "factice":
        return MoteurFactice()
    if nom == "comfyui":
        from illustration.comfyui import MoteurComfyUI
        return MoteurComfyUI(reg["comfyui"]["workflow"] or None,
                             base_url=reg["comfyui"]["base_url"],
                             timeout=reg["comfyui"]["timeout"], dossier_tome=racine_tome,
                             plancher_secondes=reg["comfyui"]["plancher_secondes"])
    raise ValueError(
        f"illustration.moteur : « {nom} » inconnu. Deux valeurs : \"factice\" (aucun poids, "
        f"aucun GPU, pour vérifier la chaîne) et \"comfyui\" (un serveur local, que tu "
        f"installes toi-même comme Ollama).")


def _empreintes(reg: dict, chemin_config: str = "config.yaml") -> dict:
    """SHA-256 de `config.yaml` et du fichier de poids, s'ils sont lisibles. Un manifeste qui
    prétendrait connaître une empreinte absente serait pire qu'un champ vide."""
    sortie = {"config": "", "poids": ""}
    fichier_config = Path(chemin_config or "config.yaml")
    if fichier_config.is_file():
        sortie["config"] = marquage.empreinte_fichier(fichier_config)
    poids = reg["poids"]
    if poids["fichier"]:
        chemin = Path(poids["dossier"]) / poids["fichier"]
        if chemin.is_file():
            sortie["poids"] = poids["sha256"] or marquage.empreinte_fichier(chemin)
    return sortie


def _avec_duree(sortie, secondes: float):
    from dataclasses import replace
    return replace(sortie, secondes=float(secondes))


def _nom_modele(reg: dict) -> str:
    """L'étiquette `modele` de `requete.yaml`, telle que la phase 1 la propose.

    ⚠ **Elle n'a de sens que pour un moteur qui charge UN poids nommé.** Le moteur ComfyUI
    n'en charge pas un mais quatre — transformeur, LoRA, encodeur de texte, VAE —, et ils
    sont désignés par le **graphe**, pas par `illustration.poids.fichier`, qui reste vide.
    Rendre « (non renseigné) » faisait alors avertir la phase 2 à chaque run que l'étiquette
    ne correspond pas aux poids chargés — un avertissement juste sur le fond et inutile en
    pratique, puisque personne n'avait écrit d'étiquette.

    Le nom du **workflow** est ce que l'humain a choisi et ce qu'il reconnaîtra ; la vérité
    mécanique — les quatre fichiers — part de toute façon dans le sidecar sous
    `moteur_details.modeles`, relevée dans le graphe et jamais déclarée."""
    poids = reg["poids"]["fichier"]
    if poids:
        return Path(poids).stem
    workflow = reg["comfyui"]["workflow"]
    if reg["moteur"] == "comfyui" and workflow:
        return Path(workflow).name.replace(".api.json", "")
    return f"(non renseigné — moteur {reg['moteur']})"


def _dire(reporter):
    if reporter is None:
        return print
    return getattr(reporter, "info", print)
