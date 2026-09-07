#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc du PROMPT (`PLAN-26`) — de quoi un prompt peut être fait, et sous quelle forme.

    # Étape 0 : le tableau des fragments. Aucune image, aucun GPU, aucun réseau.
    python tools/banc_prompt.py "roman S" --fragments --markdown

    # Étape 0.4 : les canaux structurés que le serveur expose RÉELLEMENT.
    python tools/banc_prompt.py "roman S" --canaux

    # L26.0 : le choix des images, déterministe puis par le modèle de vision (Ollama).
    python tools/banc_prompt.py "roman S" Vol.1 --selection --llm

    # Étape 0.3 et critère 7 : GÉNÈRENT des images (moteur réel, lent).
    python tools/banc_prompt.py "roman S" Vol.1 --formes   --personnage "Tory Noelle"
    python tools/banc_prompt.py "roman S" Vol.1 --langues  --personnage "Tory Noelle"
    python tools/banc_prompt.py "roman S" Vol.1 --style    --personnage "Tory Noelle"

## La discipline de ce banc, et elle est celle du lot 25

**Une variable à la fois.** Le prompt est construit par `illustration/prompt.py`, qui est pur :
deux appels de mêmes arguments rendent deux requêtes de même empreinte. C'est ce qui permet de
changer *la forme du texte* sans rien changer d'autre — mêmes fragments, même ordre, même
sujet, même cadrage, même graine, mêmes références. Un balayage où la variante « catégories »
aurait aussi gagné un adjectif ne mesurerait pas la forme, il mesurerait l'adjectif.

⚠ **Le juge du lot 25 ne sépare pas l'identité**, et ce banc ne fait pas semblant de l'oublier.
Ses colonnes de ressemblance sont publiées **marquées non opposables** tant que
`illustration.identite.planchers.juge_utilisable` vaut `false`. Ce qu'il mesure honnêtement,
en revanche, c'est le **registre graphique** : les descripteurs déterministes de
`core/illustrations.py` séparent une œuvre d'une autre 91 fois sur 100, et c'est cette
échelle-là qui décide de l'étape 0.2.

## Ce qu'il n'écrit pas

Rien sous `build/` en `--fragments`, `--canaux` ou `--selection` : ils lisent des champs, des
pixels et une API HTTP, et rendent des nombres. Les modes qui GÉNÈRENT écrivent uniquement
sous `build/<Projet>/<Tome>/illustrations/banc-prompt/`, et le périmètre de
`illustration/frontiere.py` est armé pour le vérifier à l'exécution.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from core import bible as bible_mod                             # noqa: E402
from core import glossary                                       # noqa: E402
from core.cli import charger_config, configurer_stdout          # noqa: E402
from illustration import gabarits as gabarits_mod               # noqa: E402
from illustration import identite as ident_mod                  # noqa: E402
from illustration import juge as juge_mod                       # noqa: E402
from illustration import prompt as prompt_mod                   # noqa: E402
from illustration import selection as selection_mod             # noqa: E402
from tools._banc_commun import (cellule, commit_courant,        # noqa: E402
                                empreinte_config, tableau_markdown)

#: Sous-dossier des images du banc. Distinct de `balayage/` (lot 25) : deux bancs qui
#: écriraient au même endroit se marcheraient dessus, et on ne saurait plus quelle mesure a
#: produit quelle image.
DOSSIER = "banc-prompt"

#: Les cinq attributs d'apparence, dans l'ordre de `core/bible.py`.
ATTRIBUTS = prompt_mod.ORDRE

#: Les canaux structurés inventoriés par l'étape 0.4, avec leur **source primaire** et ce
#: qu'il faudrait pour les livrer. La licence se vérifie à la source, jamais par déduction :
#: le dépôt a déjà cette jurisprudence (`docs/mesures/detecteurs-candidats-2026-08-26.md`,
#: les poids de LaMa), et la page amont de DiffSynth **n'indique aucune licence variant par
#: variant**.
CANAUX_CANDIDATS = (
    {
        "canal": "images de référence",
        "argument": "edit_image (TextEncodeQwenImageEditPlus)",
        "apporte": "l'identité du personnage",
        "noeud": "TextEncodeQwenImageEditPlus",
        "poids_en_plus": "aucun — le graphe d'édition est déjà chargé",
        "licence": "Apache-2.0 (Qwen/Qwen-Image-Edit-2511, vérifié le 2026-08-29)",
        "etat": "LIVRÉ et mesuré (lot 25)",
    },
    {
        "canal": "entités + masques",
        "argument": "eligen_entity_prompts + eligen_entity_masks",
        "apporte": "la position et la forme : cadrage voulu, place du personnage",
        "noeud": "(aucun nœud EliGen dans ComfyUI 0.34.2 sans nœud tiers)",
        "poids_en_plus": "LoRA Qwen-Image-EliGen-V2, 0,2 Md",
        "licence": "Apache-2.0 — VÉRIFIÉE à la source le 2026-08-30 "
                   "(huggingface.co/DiffSynth-Studio/Qwen-Image-EliGen-V2)",
        "etat": "candidat NON livré — aucun nœud ne l'expose sur le serveur mesuré",
    },
    {
        "canal": "image de contrôle",
        "argument": "model_patch + image (QwenImageDiffsynthControlnet)",
        "apporte": "la pose : un croquis ou une profondeur vaut cent adjectifs",
        "noeud": "QwenImageDiffsynthControlnet",
        "poids_en_plus": "un MODEL_PATCH blockwise ControlNet (~1 Md), à télécharger",
        "licence": "Apache-2.0 — VÉRIFIÉE à la source le 2026-08-30 "
                   "(huggingface.co/DiffSynth-Studio/Qwen-Image-Blockwise-ControlNet-Depth)",
        "etat": "candidat NON livré — `ModelPatchLoader` expose une liste de poids VIDE",
    },
    {
        "canal": "couches",
        "argument": "EmptyQwenImageLayeredLatentImage",
        "apporte": "une sortie en calques, pour l'export PSD que le dépôt sait déjà écrire",
        "noeud": "EmptyQwenImageLayeredLatentImage",
        "poids_en_plus": "Qwen-Image-Layered, un modèle distinct",
        "licence": "NON VÉRIFIÉE — hors périmètre, donc non instruite",
        "etat": "HORS PÉRIMÈTRE du lot (le plan l'écrit)",
    },
)


def _tableau(lignes: list[dict]) -> list[str]:
    """Un tableau Markdown dont les colonnes sont celles de la PREMIÈRE ligne, dans son ordre.

    ⚠ `tableau_markdown` du dépôt exige la liste des colonnes, et c'est la bonne discipline
    quand elle est fixe — « une colonne absente d'une ligne rend `—` », donc le dénominateur
    est explicite. Ici les colonnes dépendent de l'axe mesuré, et les recopier trois fois
    laisserait une colonne diverger d'un tableau à l'autre sans que rien ne le dise."""
    if not lignes:
        return ["*(aucune ligne)*"]
    colonnes = list(lignes[0])
    return [tableau_markdown(colonnes, lignes)]


# ═══════════════════════  Étape 0 — de quoi un prompt peut-il être fait  ═══════════════════════

def fragments(projet: str, config: dict, *, personnages=None, nombre: int = 3) -> dict:
    """Le tableau de l'étape 0 : fragment par fragment, **avec ses vides**.

    ⚠ Le plan le dit sans détour : « S'il est majoritairement vide, ce lot n'a pas son
    matériau et c'est le `PLAN-23` qu'il faut prolonger, pas celui-ci qu'il faut écrire. » Ce
    banc ne cache donc aucune case vide, et il compte les vides avant de compter les pleins."""
    sources = Path(config["chemins"]["sources"])
    racine = Path(config["chemins"]["build"]) / projet
    bible_doc = bible_mod.load(bible_mod.chemin(sources / projet))
    chemin_glossaire = sources / projet / "glossaire.yaml"
    glossaire = (glossary.load(chemin_glossaire, "fr") if chemin_glossaire.is_file() else {})

    entrees = [e for e in (bible_doc.get("personnages") or []) if isinstance(e, dict)]
    if personnages:
        voulus = {str(n) for n in personnages}
        entrees = [e for e in entrees if str(e.get("nom") or "") in voulus]
    else:
        # Les `nombre` personnages les mieux documentés : le plan demande « 3 personnages
        # ayant une bible validée », pas trois pris au hasard.
        entrees = sorted(entrees, key=_richesse, reverse=True)[:nombre]

    lignes, couverture = [], {a: 0 for a in ATTRIBUTS}
    for entree in entrees:
        nom = str(entree.get("nom") or "")
        apparence = entree.get("apparence") or {}
        cites = {c.get("attribut") for c in (entree.get("citations") or [])
                 if isinstance(c, dict)}
        for attribut in ATTRIBUTS:
            valeur = prompt_mod._texte(apparence.get(attribut))
            present = bool(valeur) and attribut in cites
            couverture[attribut] += int(present)
            lignes.append({
                "personnage": nom, "fragment": attribut,
                "source exacte": "bible.apparence + citations[]",
                "présent ?": "✅" if present else ("⚠ non cité" if valeur else "❌"),
                "valeur": valeur or "—"})
        genre, origine = prompt_mod._genre(entree, glossaire, nom)
        lignes.append({
            "personnage": nom, "fragment": "genre",
            "source exacte": "bible.genre_confirme, sinon glossaire.personnages[].genre",
            "présent ?": "✅" if origine else "❌",
            "valeur": f"{genre} ({origine})" if origine else "—"})
        references = ident_mod.references_de(bible_doc, nom, racine)
        validees = [r for r in references if r.validee]
        lignes.append({
            "personnage": nom, "fragment": "images de référence",
            "source exacte": "bible.references[role: identite, confiance: humaine]",
            "présent ?": "✅" if validees else "❌",
            "valeur": f"{len(validees)} validée(s) sur {len(references)} déclarée(s)"})
        lignes.append({
            "personnage": nom, "fragment": "cadrage",
            "source exacte": "choisi par l'utilisateur, pas par le texte",
            "présent ?": "—", "valeur": "illustration.prompt.cadrage"})

    style = (bible_doc.get("style") or {})
    return {"lignes": lignes, "personnages": [str(e.get("nom") or "") for e in entrees],
            "couverture": couverture, "total_personnages": len(entrees),
            "style_mots": str(style.get("mots") or ""),
            "ancrages_valides": sum(1 for a in (style.get("ancrages") or [])
                                    if isinstance(a, dict) and a.get("valide_par_humain")),
            "signature": style.get("signature") or {},
            "genre_bible": sum(1 for e in (bible_doc.get("personnages") or [])
                               if str(e.get("genre_confirme") or "").strip()),
            "genre_glossaire": sum(
                1 for e in (bible_doc.get("personnages") or [])
                if prompt_mod._genre(e, glossaire, str(e.get("nom") or ""))[1]),
            "personnages_bible": len(bible_doc.get("personnages") or [])}


def _richesse(entree: dict) -> tuple:
    """Combien d'attributs CITÉS, puis combien de références validées."""
    apparence = entree.get("apparence") or {}
    cites = {c.get("attribut") for c in (entree.get("citations") or []) if isinstance(c, dict)}
    attributs = sum(1 for a in ATTRIBUTS if prompt_mod._texte(apparence.get(a)) and a in cites)
    return (attributs, len(entree.get("references") or []))


def section_fragments(resultat: dict) -> list[str]:
    lignes = ["\n## Étape 0 — de quoi un prompt peut-il être fait, sur le corpus réel\n"]
    lignes.append(f"Sur **{resultat['total_personnages']} personnage(s)** : "
                  f"{', '.join(resultat['personnages'])}.\n")
    lignes += _tableau(resultat["lignes"])
    lignes.append("\n### La couverture, attribut par attribut\n")
    total = resultat["total_personnages"] or 1
    lignes += _tableau([
        {"attribut": a, "cité pour": f"{n} / {total}",
         "part": f"{100.0 * n / total:.0f} %"}
        for a, n in resultat["couverture"].items()])
    lignes.append("")
    lignes.append(
        f"- `genre_confirme` de la bible : rempli sur **{resultat['genre_bible']} / "
        f"{resultat['personnages_bible']}** personnages ;")
    lignes.append(
        f"- genre RÉSOLU en ajoutant le glossaire : **{resultat['genre_glossaire']} / "
        f"{resultat['personnages_bible']}**. ⚠ C'est un résultat de ce lot, et il n'a coûté "
        f"aucun appel de modèle : un champ que la bible ne remplit jamais et qu'un autre "
        f"fichier du même dépôt porte déjà n'est pas une donnée manquante, c'est une donnée "
        f"qu'on n'allait pas chercher ;")
    lignes.append(
        "- `bible.style.mots` : "
        + (f"« {resultat['style_mots']} »" if resultat["style_mots"]
           else "**VIDE** — l'approche 1 de l'étape 0.2 n'ajoute donc aujourd'hui aucun mot ;"))
    lignes.append(
        f"- ancrages de style validés à la main : **{resultat['ancrages_valides']}** ;")
    signature = resultat["signature"]
    if signature:
        lignes.append(
            f"- signature du tome : mesurée sur **{signature.get('echantillon', '?')}** "
            f"illustrations, saturation {cellule(signature.get('saturation_moyenne'))}, "
            f"densité de trait {cellule(signature.get('densite_trait'))}, régime "
            f"{'couleur' if signature.get('couleur') else 'noir et blanc'}.")
    return lignes


# ═══════════════════════  Étape 0.4 — les canaux réellement exposés  ═══════════════════════

def canaux(config: dict) -> dict:
    """Ce que le serveur ComfyUI expose **réellement**, relevé sur son API — pas lu dans une
    page web.

    ⚠ La différence compte : une page amont peut annoncer un canal que l'installation locale
    n'a pas. Le dépôt a déjà cette jurisprudence pour les licences ; elle vaut aussi pour les
    capacités.

    ⚠ **Le sondage lui-même vit dans `illustration/sonde.py` depuis le lot 28**, et ce banc en
    est devenu un appelant parmi deux — `run_illustration.py --check` est l'autre. Un second
    sondeur écrit ici aurait divergé du premier, et `core/config_schema.py` dit en tête ce que
    ça coûte : « une liste recopiée à la main dérive, et une référence qui dérive produit de
    FAUX avertissements — ce qui est pire que pas de vérification du tout »."""
    from illustration import sonde as sonde_mod

    releve = sonde_mod.depuis_config(config)
    appareil = releve.appareil_principal
    return {"base_url": releve.base_url, "joignable": releve.joignable,
            "noeuds": sorted(releve.noeuds), "comfyui": releve.version,
            "vram_total": appareil.vram_total if appareil else None,
            "vram_libre": appareil.vram_libre if appareil else None,
            "erreur": releve.erreur}


def section_canaux(releve: dict) -> list[str]:
    lignes = ["\n## Étape 0.4 — les canaux structurés, inventoriés à la source\n"]
    if not releve["joignable"]:
        lignes.append(f"⚠ **Serveur injoignable** ({releve['base_url']}) : "
                      f"{releve.get('erreur', '')}. Le tableau ci-dessous est donc l'état "
                      f"documentaire, non le relevé de l'installation.\n")
    else:
        lignes.append(
            f"Relevé sur **{releve['base_url']}**, ComfyUI **{releve['comfyui']}**, "
            f"{len(releve['noeuds'])} nœuds exposés. VRAM totale "
            f"{_mio(releve['vram_total'])} Mio, libre {_mio(releve['vram_libre'])} Mio.\n")
    presents = set(releve["noeuds"])
    lignes += _tableau([
        {"canal": c["canal"], "argument": f"`{c['argument']}`",
         "ce qu'il apporte": c["apporte"],
         "nœud exposé ?": ("✅ oui" if c["noeud"] in presents else "❌ non"),
         "poids en plus": c["poids_en_plus"], "licence": c["licence"], "état": c["etat"]}
        for c in CANAUX_CANDIDATS])
    lignes.append(
        "\n⚠ **Deux réserves, et elles ne se contournent pas.** D'abord, la page amont qui "
        "documente ces variantes **n'indique aucune licence variant par variant** : chacune se "
        "vérifie séparément avant usage, et le dépôt a déjà cette jurisprudence (les poids de "
        "LaMa, lot 16). Ensuite, chaque canal supplémentaire est un poids de plus à charger "
        "dans 20 Go — un canal dont l'apport n'est pas mesuré est un canal qu'on ne livre "
        "pas, ou qu'on livre **désarmé**.")
    lignes.append(
        "\n⚠ **Ce que « coût VRAM mesuré » veut dire ici, et ce qu'il ne veut pas dire.** "
        "Aucun de ces poids n'est installé : `ModelPatchLoader` expose une liste **vide**, et "
        "aucun nœud EliGen n'existe sur ce serveur. Le coût VRAM de ces canaux n'a donc pas "
        "été mesuré — il ne pouvait pas l'être sans télécharger des poids dont l'apport n'est "
        "pas mesuré non plus, ce qui est exactement l'ordre que le plan interdit. Ce qui EST "
        "mesuré, et publié à côté, c'est la **marge disponible** : la VRAM résidente après "
        "une génération réelle, face aux 20 464 Mio de la carte. Un canal se juge sur cette "
        "marge, pas sur une taille de fichier annoncée.")
    return lignes


def _mio(octets) -> str:
    return "—" if not octets else f"{int(octets) / 1048576:,.0f}".replace(",", " ")


# ═══════════════════════  L26.0 — le choix des images, avec son coût  ═══════════════════════

def selection(projet: str, config: dict, *, avec_llm: bool = False,
              personnages=None, dire=print) -> dict:
    """Le choix des images, déterministe puis — si demandé — par le modèle de vision.

    ⚠ **Le temps est mesuré et publié**, parce que le plan le demande : « juger 20
    illustrations en vision sur `yume-27b` ne tient pas en un appel. Découpez par lots et
    mesurez le temps de la phase 1 complète : si elle dure plus longtemps que la phase 2,
    c'est un fait à publier, pas un détail. »"""
    from illustration.orchestrateur import _choisir_les_images, reglages

    reg = reglages(config)
    reg["prompt"]["llm"]["actif"] = bool(avec_llm)
    reg["prompt"]["style"] = "ancrages"
    reg["prompt"]["ancrages_max"] = 1
    bible_doc = bible_mod.load(
        bible_mod.chemin(Path(config["chemins"]["sources"]) / projet))
    depart = time.monotonic()
    selections = _choisir_les_images(config, projet, reg, bible_doc, personnages, dire=dire)
    secondes = time.monotonic() - depart

    lignes = []
    for nom, choix in selections.items():
        ancres = {c.fichier for c in choix.ancrages}
        for c in choix.references + choix.ancrages:
            lignes.append({
                "personnage": nom, "image": Path(c.fichier).name,
                "usage": "style" if c.fichier in ancres else "identité",
                "retenue": "oui" if c.retenue else "non",
                "décidée par": c.par,
                "visage": "—" if c.visage is None else ("oui" if c.visage else "non"),
                "motif": c.motif})
    return {"lignes": lignes, "secondes": secondes,
            "appels": sum(s.appels_llm for s in selections.values()),
            "avec_llm": bool(avec_llm), "selections": selections}


def section_selection(deterministe: dict, avec_llm: dict | None) -> list[str]:
    lignes = ["\n## L26.0 — le choix des images, et le motif de chacune\n"]
    lignes.append(f"**Sélection déterministe** — {deterministe['secondes']:.2f} s, "
                  f"aucun appel réseau.\n")
    lignes += _tableau(deterministe["lignes"])
    if avec_llm is None:
        lignes.append("\n⚠ La sélection **par le modèle de vision n'a pas été exécutée** dans "
                      "ce relevé : le tableau ci-dessus est celui du chemin par défaut.")
        return lignes
    lignes.append(f"\n**Sélection par le modèle de vision** — {avec_llm['secondes']:.1f} s, "
                  f"{avec_llm['appels']} appel(s), soit "
                  f"{avec_llm['secondes'] / max(1, avec_llm['appels']):.1f} s par image.\n")
    lignes += _tableau(avec_llm["lignes"])
    lignes += _section_accord(deterministe, avec_llm)
    return lignes


def _section_accord(deterministe: dict, avec_llm: dict) -> list[str]:
    """Où les deux sélections divergent — **le seul chiffre qui dise si le LLM sert**.

    ⚠ Un accord parfait ne serait pas une bonne nouvelle : il voudrait dire que l'appel de
    vision coûte du temps sans rien décider. Un désaccord n'est pas une bonne nouvelle non
    plus tant qu'un humain n'a pas tranché lequel des deux avait raison. Ce chiffre pose la
    question, il ne la referme pas."""
    a = {(l["personnage"], l["image"]): l["retenue"] for l in deterministe["lignes"]}
    b = {(l["personnage"], l["image"]): l["retenue"] for l in avec_llm["lignes"]}
    communs = sorted(set(a) & set(b))
    accords = [c for c in communs if a[c] == b[c]]
    lignes = [f"\n**Accord entre les deux sélections : {len(accords)} / {len(communs)}** "
              f"images jugées pareil.\n"]
    desaccords = [c for c in communs if a[c] != b[c]]
    if desaccords:
        lignes += _tableau([
            {"personnage": p, "image": i, "déterministe": a[(p, i)],
             "modèle de vision": b[(p, i)],
             "motif du modèle": next(l["motif"] for l in avec_llm["lignes"]
                                     if (l["personnage"], l["image"]) == (p, i))}
            for p, i in desaccords])
    lignes.append(
        "\n⚠ **Ce tableau pose une question, il ne la referme pas.** Un accord parfait "
        "voudrait dire que l'appel de vision coûte du temps sans rien décider ; un désaccord "
        "ne dit pas lequel des deux avait raison — seul un humain qui ouvre les images le "
        "dit, et c'est exactement ce que la porte humaine de `requete.yaml` sert à faire.")
    return lignes


# ═══════════  Étapes 0.2 / 0.3 et critère 7 — les balayages qui GÉNÈRENT  ═══════════

def variantes(axe: str) -> list[dict]:
    """Le plan de balayage d'un axe. **Une variable à la fois**, et l'axe nommé dans chaque
    ligne du tableau."""
    if axe == "formes":
        return [{"axe": "forme", "forme": f, "langue": "fr", "style": "aucun",
                 "selection": "deterministe"}
                for f in gabarits_mod.FORMES]
    if axe == "langues":
        return [{"axe": "langue", "forme": "prose", "langue": lg, "style": "aucun",
                 "selection": "deterministe"}
                for lg in gabarits_mod.LANGUES]
    if axe == "style":
        return [{"axe": "style", "forme": "prose", "langue": "fr", "style": s,
                 "selection": "deterministe"}
                for s in ("aucun", "mots", "ancrages")]
    if axe == "references":
        return [{"axe": "references", "forme": "prose", "langue": "fr", "style": "aucun",
                 "selection": s} for s in ("deterministe", "llm")]
    raise ValueError(f"axe inconnu : {axe}")


def valeur_d_axe(variante: dict):
    """La valeur de la variable balayée. L'axe `references` porte sa valeur sous `selection`,
    parce qu'on y change QUI choisit les images, pas les images elles-mêmes."""
    return variante[{"references": "selection"}.get(variante["axe"], variante["axe"])]


def balayer(axe: str, projet: str, tome: str, config: dict, personnage: str, *,
            graine: int = 1234, dire=print) -> list[dict]:
    """Génère une image par variante et mesure ce qui est mesurable sur chacune.

    ⚠ `tome` ne choisit **plus** le dossier de sortie depuis la 2.19.0 : les illustrations sont
    rangées par ŒUVRE, parce qu'un personnage traverse les volumes et ses références aussi. Il
    reste dans la signature et dans la ligne de commande parce qu'il **nomme le volume mesuré**
    dans le tableau publié ; le retirer changerait l'interface du banc pour rien.

    ⚠ **Mêmes références, même graine, mêmes dimensions, même nombre de pas** dans toutes les
    variantes de l'axe. Seule la variable de l'axe change — c'est la condition pour que le
    tableau veuille dire quelque chose.

    ⚠ **Les secondes ne se comparent PAS entre elles**, et le lot 25 a mesuré pourquoi : la
    même requête, par le même graphe, a coûté 1 054,9 s puis 243,7 s selon ce que ComfyUI
    gardait en VRAM. La colonne est publiée avec cet avertissement plutôt que retirée — elle
    dit ce que le run a coûté, pas ce que le réglage coûte."""
    from illustration import frontiere
    from illustration.orchestrateur import (construire_moteur, dossier, dossier_projet,
                                            racine_projet, reglages)

    reg = reglages(config)
    # ⚠ Deux arguments, pas trois : `dossier` range par ŒUVRE depuis la 2.19.0 (`5531029`).
    # Corrigé le 2026-09-03 avec les deux autres appelants oubliés par ce renommage — tous
    # sur des chemins qui exigent un GPU, donc invisibles aux tests.
    sortie = dossier(config, projet) / DOSSIER
    racine = racine_projet(config, projet)
    bible_doc = bible_mod.load(bible_mod.chemin(dossier_projet(config, projet)))
    chemin_glossaire = dossier_projet(config, projet) / "glossaire.yaml"
    glossaire = (glossary.load(chemin_glossaire, "fr") if chemin_glossaire.is_file() else {})

    jeux = _jeux_de_references(axe, bible_doc, personnage, racine, config, reg, dire)
    ident_mod.exiger_references(jeux["deterministe"], personnage)
    ancrages_dispo = selection_mod.candidates_ancrage(bible_doc, racine)

    encodeur = _encodeur(reg)
    signature = (bible_doc.get("style") or {}).get("signature") or {}
    # ⚠ **`bible.style.mots` seul ne suffit PAS, et le premier relevé l'a montré.** Sur ce
    # corpus il est vide : la variante « mots » avait alors produit un prompt IDENTIQUE à la
    # variante « aucun » — 79 jetons dans les deux cas —, et ComfyUI, qui met son graphe en
    # cache, avait rendu la seconde image en **1 seconde**. Une ligne de tableau qui mesure
    # deux fois la même chose est pire qu'une ligne absente : elle a l'air d'un résultat.
    # `requete.mots_de_style` ajoute la SIGNATURE MESURÉE du tome mise en mots.
    from illustration import requete as requete_mod

    mots_style = requete_mod.mots_de_style(bible_doc, langue="fr",
                                           gabarit=reg["prompt"]["gabarit"])
    moteur = construire_moteur(reg, dossier(config, projet).parent)
    if not moteur.disponible():
        raise RuntimeError("le moteur n'est pas disponible — lance ComfyUI, puis "
                           "`python run_illustration.py --check`.")

    lignes: list[dict] = []
    with frontiere.perimetre(sortie):
        preparees = {nom: ident_mod.preparer_toutes(refs, f"{personnage}-{nom}", sortie,
                                                    cote=reg["identite"]["cote_reference"])
                     for nom, refs in jeux.items() if refs}
        ancres_prep = ident_mod.preparer_toutes(
            [ident_mod.Reference(fichier=a.fichier, source=a.source, confiance="humaine",
                                 classe=a.classe) for a in ancrages_dispo[:1]],
            f"{personnage}-ancre", sortie, cote=reg["identite"]["cote_reference"])
        for variante in variantes(axe):
            jeu = variante["selection"]
            if jeu not in preparees:
                lignes.append({"axe": variante["axe"], "variante": valeur_d_axe(variante),
                               "secondes": None,
                               "verdict": "non mesurée — cette sélection ne retient aucune "
                                          "référence pour ce personnage"})
                continue
            lignes.append(_une_variante(
                variante, moteur, encodeur, personnage, bible_doc, glossaire,
                preparees=preparees[jeu], ancres=ancres_prep, sortie=sortie, reg=reg,
                references=jeux[jeu], signature=signature, mots_style=mots_style,
                graine=graine, dire=dire))
    return lignes


def _jeux_de_references(axe: str, bible_doc: dict, personnage: str, racine, config: dict,
                        reg: dict, dire) -> dict:
    """`{nom du jeu: [Reference]}` — le jeu DÉTERMINISTE, et celui du modèle de vision.

    ⚠ **C'est l'axe que le premier relevé de ce lot a rendu obligatoire.** Le lot 25 a mesuré
    que « le conditionnement rapproche l'image du registre des RÉFÉRENCES, pas du registre du
    TOME », et que les références validées du corpus sont des **couvertures en couleur** —
    d'où des générations en couleur sur un tome en noir et blanc. Le modèle de vision, lui,
    écarte les couvertures et retient un portrait au trait. Si ce mécanisme explique le
    défaut, changer de sélection doit le corriger, et rien d'autre n'a besoin de changer."""
    candidates = selection_mod.candidates_identite(bible_doc, personnage, racine)
    par_fichier = {c.fichier: c for c in
                   ident_mod.references_de(bible_doc, personnage, racine)}
    deterministe = [par_fichier[c.fichier] for c in
                    selection_mod.choisir(candidates,
                                          plafond=selection_mod.PLAFOND_REFERENCES)
                    if c.retenue and c.fichier in par_fichier]
    jeux = {"deterministe": deterministe}
    if axe != "references":
        return jeux
    from illustration.orchestrateur import _llm, _prompt_de_selection

    invite = dict(reg["prompt"])
    invite["llm"] = dict(invite["llm"])
    invite["llm"]["actif"] = True
    reg_llm = dict(reg)
    reg_llm["prompt"] = invite
    systeme, modele = _prompt_de_selection(config, reg_llm, dire)
    if not modele:
        return jeux
    choix, secondes, appels = selection_mod.choisir_avec_llm(
        candidates, plafond=selection_mod.PLAFOND_REFERENCES,
        usage=selection_mod.USAGE_IDENTITE, llm=_llm(config), modele=modele,
        systeme=systeme, personnage=personnage, cote=invite["llm"]["cote_vision"], dire=dire)
    dire(f"    sélection par vision : {secondes:.0f} s, {appels} appel(s), "
         f"{sum(1 for c in choix if c.retenue)} référence(s) retenue(s)")
    # ⚠ **La bascule VRAM, ici et une seule fois** — L26.4. Le LLM local occupe la carte
    # (15,2 Go pour `yume-27b` en IQ4_XS) ; le transformeur d'image en demande 12,8 de plus,
    # et la carte en a 20,5. Les laisser cohabiter fait diffuser depuis la RAM, ce que le lot
    # 24 a mesuré à un facteur **9,6** sur le pas de débruitage. Le mécanisme existe déjà dans
    # le dépôt et il est réutilisé, pas réécrit.
    from core import cli as cli_mod

    modeles = list(dict.fromkeys(cli_mod.models_in_config(config)
                                 + cli_mod.models_in_config(config, "manga")))
    if modeles:
        depart = time.monotonic()
        cli_mod.shielded_unload(config, modeles)
        dire(f"    bascule VRAM : {len(modeles)} modèle(s) LLM déchargé(s) en "
             f"{time.monotonic() - depart:.1f} s")
    jeux["llm"] = [par_fichier[c.fichier] for c in choix
                   if c.retenue and c.fichier in par_fichier]
    return jeux


def _une_variante(variante: dict, moteur, encodeur, personnage: str, bible_doc, glossaire, *,
                  preparees, ancres, sortie: Path, reg: dict, references, signature: dict,
                  mots_style: str, graine: int, dire) -> dict:
    from illustration import marquage

    avec_ancre = variante["style"] == "ancrages" and ancres
    style_mots = mots_style if variante["style"] == "mots" else ""
    construction = prompt_mod.construire(
        personnage, bible_doc, glossaire, cadrage=reg["prompt"]["cadrage"],
        forme=variante["forme"], langue=variante["langue"], style=style_mots,
        nombre_references=len(preparees), nombre_ancrages=1 if avec_ancre else 0,
        largeur=reg["image"]["largeur"], hauteur=reg["image"]["hauteur"],
        graine=graine, pas=reg["image"]["pas"], guidage=reg["image"]["guidage"])
    fichiers = list(preparees) + (list(ancres) if avec_ancre else [])
    requete = construction.requete.avec(
        references=tuple(str(p.relative_to(sortie.parent.parent)) for p in fichiers))

    nom = f"{variante['axe']}-{valeur_d_axe(variante)}"
    depart = time.monotonic()
    resultat = moteur.generer(requete)
    secondes = resultat.secondes or (time.monotonic() - depart)
    image = sortie / f"{nom}.png"
    provenance = marquage.manifeste(
        requete, resultat, projet="", tome="",
        identifiant=marquage.identifiant_oeuvre("banc-prompt", personnage),
        validation={"par": "banc_prompt.py",
                    "note": "image de BANC, produite pour mesurer une forme de prompt — "
                            "pas une illustration retenue"},
        modele=requete.modele or "(banc)",
        prompt_source={"gabarit": construction.gabarit,
                       "gabarit_sha256": construction.gabarit_sha256,
                       "forme": construction.forme, "langue": construction.langue,
                       "cadrage": construction.cadrage, "personnage": personnage,
                       "attributs_sources": construction.attributs_sources()})
    marquage.ecrire(resultat, image, provenance=provenance)

    ligne = {"axe": variante["axe"], "variante": valeur_d_axe(variante),
             "jetons du prompt": _jetons(requete.prompt),
             "caractères": len(requete.prompt),
             "secondes": round(secondes, 1),
             "VRAM résidente (Mio)": _vram_residente(reg), "image": image}
    ligne.update(_mesures(encodeur, image, references, signature))
    dire(f"    {nom} : {secondes:.0f} s · {ligne['jetons du prompt']} jetons · style "
         f"{cellule(ligne['style (descripteurs)'])} · ressemblance "
         f"{cellule(ligne['ressemblance (non opposable)'])}")
    return ligne


def _vram_residente(reg: dict):
    """La VRAM occupée juste après une génération — **la marge, pas le pic**.

    ⚠ La distinction est celle que le lot 24 a payée : le **pic** pendant l'échantillonnage
    n'est pas observable depuis ce client, qui parle à ComfyUI par HTTP et n'a aucune vue sur
    l'allocateur pendant le calcul. Ce qui l'est, c'est ce qui **reste occupé** quand le
    serveur a fini : le transformeur et l'encodeur qu'il garde résidents. C'est ce chiffre
    qui dit s'il resterait de la place pour un canal de plus.

    Rend `None` si le serveur ne répond pas : une case vide vaut mieux qu'un chiffre inventé.

    ⚠ Le relevé passe par `illustration/sonde.py` depuis le lot 28 — cf. `canaux`."""
    from illustration import sonde as sonde_mod

    releve = sonde_mod.sonder(reg["comfyui"]["base_url"], timeout=10.0)
    appareil = releve.appareil_principal
    if appareil is None or not appareil.vram_total:
        return None
    return round((appareil.vram_total - appareil.vram_libre) / 1048576)


def _mesures(encodeur, image: Path, references, signature: dict) -> dict:
    """Ce qu'on sait mesurer, et **rien de plus**.

    ⚠ La colonne de ressemblance est nommée `(non opposable)` tant que le juge du lot 25 ne
    sépare pas — 68 fois sur 100 sur ce corpus, pour un seuil de 80. La renommer serait
    reprendre d'une main ce que le lot 25 a écrit de l'autre."""
    if encodeur is None:
        ecart, decroche, regime = juge_mod.ecart_de_style(image, signature) if signature \
            else (None, ("", 0.0), None)
        return {"ressemblance (non opposable)": None, "nouveauté": None,
                "style (descripteurs)": ecart, "descripteur qui décroche": decroche[0] or "—",
                "même régime de couleur": _oui_non(regime)}
    grandeurs = juge_mod.mesurer(encodeur, image, references=[r.source for r in references],
                                 signature_tome=signature)
    return {"ressemblance (non opposable)": grandeurs.ressemblance,
            "nouveauté": grandeurs.nouveaute,
            "style (descripteurs)": grandeurs.style_descripteurs,
            "descripteur qui décroche": grandeurs.descripteur_decroche[0] or "—",
            "même régime de couleur": _oui_non(grandeurs.meme_regime_couleur)}


def _oui_non(valeur) -> str:
    return "—" if valeur is None else ("oui" if valeur else "non ✗")


def _encodeur(reg: dict):
    fichier = reg["identite"]["encodeur"]["fichier"]
    if not fichier:
        return None
    chemin = Path(reg["identite"]["encodeur"]["dossier"]) / fichier
    encodeur = juge_mod.Encodeur(chemin, agregation=reg["identite"]["encodeur"]["agregation"],
                                 cadrage=reg["identite"]["encodeur"]["cadrage"],
                                 cote=reg["identite"]["encodeur"]["cote"])
    return encodeur if encodeur.disponible() else None


def _jetons(texte: str) -> int:
    """Une estimation de jetons, et elle est annoncée comme telle.

    ⚠ Ce n'est **pas** le tokeniseur de `Qwen2.5-VL` : le dépôt ne l'embarque pas, et
    l'installer pour compter des jetons dans un tableau coûterait plus que ce que le chiffre
    apprend. `core/tokens.py` porte déjà l'heuristique du dépôt ; elle sert ici à comparer
    trois formes **entre elles**, pas à prédire un budget d'encodeur."""
    from core import tokens

    return tokens.estimate(texte)


def section_balayage(axe: str, lignes: list[dict]) -> list[str]:
    titres = {
        "formes": ("Étape 0.3 — les trois formes du champ texte",
                   "prose · catégories étiquetées · JSON sérialisé, **mêmes fragments, même "
                   "ordre, même graine, mêmes références**"),
        "langues": ("Critère 7 — français contre anglais",
                    "⚠ **l'anglais est un HYBRIDE** : la charpente est anglaise, les valeurs "
                    "d'attribut viennent de `bible.yaml` et restent en français. C'est ce "
                    "que le dépôt peut livrer sans faire traduire les attributs par un "
                    "modèle, ce qui violerait le critère 4"),
        "style": ("Étape 0.2 — comment le registre graphique entre dans la requête",
                  "approche 3 (« ne rien faire ») · approche 1 (les mots de la signature "
                  "mesurée) · approche 2 (une ancre sur le canal d'images)"),
        "references": ("L26.0 — la SÉLECTION des références, déterministe contre modèle de "
                       "vision",
                       "⚠ **l'axe que le premier relevé a rendu obligatoire** : le lot 25 a "
                       "mesuré que le conditionnement tire vers le registre des RÉFÉRENCES, "
                       "et que les références validées du corpus sont des couvertures **en "
                       "couleur** sur un tome **en noir et blanc**. Rien ne change ici que "
                       "le choix des images"),
    }
    titre, sous_titre = titres[axe]
    sortie = [f"\n## {titre}\n", f"{sous_titre}.\n"]
    sortie += _tableau([{k: v for k, v in ligne.items() if k != "image"}
                                for ligne in lignes])
    sortie.append(
        "\n⚠ **La colonne `secondes` ne se compare PAS entre lignes.** Le lot 25 l'a mesuré : "
        "la même requête, par le même graphe, a coûté 1 054,9 s puis 243,7 s selon ce que "
        "ComfyUI gardait en VRAM (facteur 4,3, aucun réglage changé). Elle dit ce que le run "
        "a coûté, pas ce que le réglage coûte.")
    sortie.append(
        "\n⚠ **La colonne `ressemblance` est marquée non opposable** : le juge du lot 25 ne "
        "sépare « même personnage » de « personnages différents de la même œuvre » que 68 "
        "fois sur 100, pour un seuil de 80. La colonne qui décide ici est "
        "`style (descripteurs)`, dont l'échelle sépare une œuvre d'une autre 91 fois sur 100.")
    return sortie


# ═════════════════════════════════  L'en-tête  ═════════════════════════════════

def entete(chemin_config: str, projet: str, commande: str, reg: dict) -> list[str]:
    return [
        f"# Le prompt vient de l'œuvre — mesures du {date_du_jour()}",
        "",
        f"**Commande** : `{commande}`  ",
        f"**Commit** : `{commit_courant()}`  ",
        f"**Empreinte SHA-256 de `config.yaml`** : `{empreinte_config(chemin_config)}`  ",
        f"**Empreinte du gabarit `{reg['prompt']['gabarit']}`** : "
        f"`{gabarits_mod.empreinte(reg['prompt']['gabarit'])}`  ",
        f"**Projet** : `{projet}`  ",
        f"**Moteur** : `{reg['moteur']}` · workflow "
        f"`{Path(reg['comfyui']['workflow']).name or '(aucun)'}`  ",
        "",
        "> ⚠ **Les images ne sont pas dans ce document** : le corpus est sous droits, et le",
        "> `README-ILLUSTRATION-23-27` §5 n'autorise à en montrer que celles de",
        "> `Pride and Prejudice`, qui est du domaine public. On publie des **chiffres**.",
        "",
    ]


def date_du_jour() -> str:
    from datetime import date
    return date.today().isoformat()


# ═════════════════════════════════════  main  ═════════════════════════════════════

def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Banc du prompt (PLAN-26) : de quoi un prompt est fait, et sous quelle "
                    "forme.")
    ap.add_argument("projet", nargs="?", default=None)
    ap.add_argument("tome", nargs="?", default=None)
    ap.add_argument("--fragments", action="store_true",
                    help="étape 0 : le tableau des fragments — aucune image, aucun réseau")
    ap.add_argument("--canaux", action="store_true",
                    help="étape 0.4 : les canaux que le serveur expose réellement")
    ap.add_argument("--selection", action="store_true",
                    help="L26.0 : le choix des images, avec un motif par image")
    ap.add_argument("--llm", action="store_true",
                    help="--selection : ajoute la sélection par le modèle de vision")
    ap.add_argument("--formes", action="store_true",
                    help="étape 0.3 : prose / catégories / JSON (GÉNÈRE des images)")
    ap.add_argument("--langues", action="store_true",
                    help="critère 7 : français contre anglais (GÉNÈRE des images)")
    ap.add_argument("--style", action="store_true",
                    help="étape 0.2 : aucun / mots / ancrage (GÉNÈRE des images)")
    ap.add_argument("--references", action="store_true",
                    help="L26.0 : sélection déterministe contre modèle de vision "
                         "(GÉNÈRE des images)")
    ap.add_argument("--personnage", default=None, metavar="NOM",
                    help="le personnage des balayages qui génèrent")
    ap.add_argument("--nombre", type=int, default=3, metavar="N",
                    help="--fragments : combien de personnages (défaut 3, comme le plan)")
    ap.add_argument("--graine", type=int, default=1234)
    ap.add_argument("--markdown", action="store_true", help="document daté et publiable")
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    if not args.projet:
        ap.error("précise un projet : python tools/banc_prompt.py \"roman S\" --fragments")
    config = charger_config(args.config)

    from illustration.orchestrateur import reglages
    reg = reglages(config)

    sortie: list[str] = []
    commande = "python " + " ".join(["tools/banc_prompt.py", *sys.argv[1:]])
    if args.markdown:
        sortie += entete(args.config, args.projet, commande, reg)

    if args.fragments:
        sortie += section_fragments(fragments(args.projet, config, nombre=args.nombre,
                                              personnages=[args.personnage]
                                              if args.personnage else None))
    if args.canaux:
        sortie += section_canaux(canaux(config))
    if args.selection:
        muet = (lambda _m: None)
        deterministe = selection(args.projet, config, avec_llm=False, dire=muet)
        avec = selection(args.projet, config, avec_llm=True, dire=print) if args.llm else None
        sortie += section_selection(deterministe, avec)

    for drapeau, axe in (("formes", "formes"), ("langues", "langues"), ("style", "style"),
                         ("references", "references")):
        if not getattr(args, drapeau):
            continue
        if not (args.tome and args.personnage):
            ap.error(f"--{drapeau} demande un tome et --personnage : il GÉNÈRE des images.")
        print(f"  balayage « {axe} » sur « {args.personnage} »…", file=sys.stderr)
        sortie += section_balayage(axe, balayer(axe, args.projet, args.tome, config,
                                                args.personnage, graine=args.graine))

    print("\n".join(sortie))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
