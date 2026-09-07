#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc de mesure : une commande, tous les volumes de `build/`, un tableau daté.

    python tools/banc.py --tous                       # tous les volumes de build/
    python tools/banc.py "Mon Œuvre" Vol.2
    python tools/banc.py --tous --markdown > docs/mesures/banc-2026-08-25.md
    python tools/banc.py --tous --json                # pour tracer une courbe
    python tools/banc.py --tous --traduction          # le banc de traduction, sans LLM
    python tools/banc.py --corpus tests/corpus/synthetique   # rappel / précision / F1

## Le défaut que cet outil corrige

`RAPPORT.md` **mesure déjà** l'essentiel — planches à zéro bulle, détections faibles, régions
bi-lobées, zones restaurées, motifs d'échec résiduels, stratégie de rattachement. Mais il le
fait **par tome**, sans date et sans commit : rien n'agrège ces sections entre volumes, et
deux runs ne se comparent pas. Le défaut n'était pas l'absence de mesure, c'était l'absence de
tableau.

## Deux pièges mesurés, que cet outil ne reproduit pas

1. **Les bulles ne se comptent pas depuis `qa.json`.** C'est ce que fait `RAPPORT.md`, et
   c'est pourquoi il annonce 813 bulles là où `regions.json` en porte 821 sur le tome de
   référence : la **page 8** n'a pas de `qa.json`, et elle porte exactement 8 bulles.

   ⚠ Le résumé du rapport écrit « ⚠ SANS contrôle qualité : 8 » — et ce 8 est un **numéro de
   planche**, pas un compte (`report_manga.py` y joint `sans_qa[:12]`). La coïncidence entre
   le numéro de la planche et le nombre de ses bulles a fait lire « huit planches » pendant
   tout ce temps. Le banc compte depuis `regions.json` et **signale** les planches sans `qa`
   dans une colonne à elles, où un 1 reste un 1.

2. **`qa["sfx"]` n'est pas un test d'encre.** La passe onomatopées est optionnelle ; sur un
   tome traité sans elle, aucune planche à zéro bulle n'est triée. Le banc mesure l'encre sur
   la planche elle-même (`manga.detection.porte_de_l_encre`, via `_banc_commun`) et ne retombe
   sur `qa["sfx"]` qu'en dernier recours — la colonne `source encre` dit toujours laquelle a
   répondu.

   ⚠ Depuis le lot 12, le calcul est celui de `manga/detection.py` — **le même** qui arme
   l'escalade de détection dans le pipeline. Un rapport qui trierait ses planches autrement
   que le pipeline ne mesurerait pas le pipeline. Et une **quatrième** source est consultée,
   `sources/`, faute de quoi les 43 planches à zéro bulle des deux premiers volumes de
   *manga D* — qui n'ont ni rendu, ni page nettoyée, ni `qa.json` — resteraient
   définitivement non mesurables.

⚠ Comme `tools/mesurer_bulles.py`, cet outil ne charge **aucun modèle**, ne réécrit **rien**,
et se lance donc pendant qu'un run tourne. Il lit le cache de `build/` — et, pour la seule
colonne « dont encrées » et seulement en dernier recours, la planche d'origine sous `sources/`
(cf. le piège n° 2 ci-dessus).

⚠ **`--corpus` est la seule exception, et elle est assumée** : mesurer un rappel demande de
détecter, donc de charger le détecteur. Il n'écrit toujours rien.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from core.cli import charger_config, configurer_stdout       # noqa: E402
from manga import planche as planche_mod                     # noqa: E402
from manga import registre, relecture                        # noqa: E402
from tools import _banc_commun as banc                       # noqa: E402

#: Noms de colonne cités TROIS fois chacun — dans l'ordre de publication, dans la ligne de
#: mesure, et dans l'ensemble des colonnes sommables. Un nom de colonne est une CLÉ de
#: dictionnaire autant qu'un en-tête : le retoucher dans deux endroits sur trois ne casse
#: rien de visible, la colonne se remplit simplement de vide. D'où ces constantes.
COL_ZERO_BULLE = "0 bulle"
COL_SANS_OCR = "sans OCR"
COL_RATTRAPEES = "rattrapées"

#: Colonnes du tableau de détection, dans l'ordre de publication. Ce sont exactement celles
#: qu'un lot doit republier après avoir « gagné des bulles » : les trois indicateurs de fausse
#: détection y sont à côté du compte de bulles, et non trois sections plus bas.
COLONNES_DETECTION = [
    "volume", "régime", "langue", "planches", "sans qa", "bulles",
    "médiane b/pl", "max b/pl", COL_ZERO_BULLE, "dont encrées", "encre ?", "source encre",
    "score faible", "restaurées", COL_SANS_OCR, "non nettoyées",
    "scindées", "suspectes", "dégénérées", "taille planche", "ratio max",
]

#: Le banc de TRADUCTION (L8.3), calculé sur les caches existants **sans un seul appel LLM**.
#:
#: Sur les huit lignes visées, cinq sont ici. Les trois autres ne sont pas oubliées, elles
#: sont ailleurs ou pas encore écrites, et il vaut mieux le dire que laisser une colonne
#: vide passer pour un zéro :
#:
#: · **formes bannies subsistantes** — `tools/compter_variantes.py`, qui existe et qui a
#:   besoin du glossaire de l'œuvre, donc de `sources/` ; le banc, lui, ne l'exige pas ;
#: · le **taux de rejet** des rattrapages unitaires n'est pas persisté : `qa.json` retient
#:   la bulle rattrapée, pas les tentatives que `quality_manga.diagnostiquer_rattrapage` a
#:   refusées. Le compte de rattrapages est là ; le taux demande de persister le refus.
#:
#: ⚠ Les cinq dernières colonnes sont celles que le lot 15 devait fournir, et elles le sont
#: **sans un seul appel LLM** :
#:
#: · `glossaire manqué` — termes présents dans la source et absents du rendu
#:   (`manga.relecture.termes_manques`, purement lexical) ;
#: · `registre` / `basculements` — tutoiement/vouvoiement relevés bulle par bulle
#:   (`manga.registre`), et les changements de dominante entre planches consécutives ;
#: · `types de bulle` / `indéterminés` — la distribution du classifieur de `manga.planche`,
#:   relue dans `structure.json`. Un classifieur qui type tout est suspect : c'est le taux
#:   d'indéterminé qu'il faut regarder, pas les autres.
COLONNES_TRADUCTION = [
    "volume", "bulles", "vides à l'arrivée", "motifs résiduels", COL_RATTRAPEES,
    "stratégies", "origines", "longueur rendue/source",
    "glossaire manqué", "registre", "basculements", "types de bulle", "indéterminés",
]

#: Rapport hauteur/largeur au-delà duquel une planche est une BANDE, pas une page. Le seuil
#: vient de la géométrie des deux régimes : une page de manga tient entre 1,3 et 1,6, un
#: chapitre de webtoon monte à 10 ou 40. Rien ne vit entre les deux.
RATIO_WEBTOON = 3.0


def _regime(tailles: set[tuple[int, int]], sens: str | None) -> str:
    """`manga`, `webtoon` ou `mixte`. Deux régimes qu'une moyenne unique masquerait — l'écart
    mesuré, de 0 % à 22 % de zones restaurées selon le format, suffit à le prouver.

    ⚠ Le seuil de 3,0 utilisé ici est celui du BANC, qui classe des volumes déjà traités ; ce
    n'est plus celui de la détection, qui décide désormais sur l'occupation du canevas
    (`detection.OCCUPATION_MIN`, lot 14). Les deux coïncident à `input_size: 640` et peuvent
    diverger ailleurs : une colonne de tableau et une décision de découpage n'ont pas à
    répondre à la même question."""
    ratios = [h / w for (w, h) in tailles if w]
    if not ratios:
        return "webtoon" if sens == "gauche_droite" else "?"
    bandes = sum(1 for r in ratios if r >= RATIO_WEBTOON)
    if bandes == len(ratios):
        return "webtoon"
    return "manga" if bandes == 0 else "mixte"


def _langue_source(textes: list[str]) -> str:
    """Langue de la source, **inférée de l'OCR** et non lue quelque part.

    ⚠ Colonne indispensable, et c'est mesuré : le seul volume webtoon du corpus de référence
    est aussi le seul à source latine (`ocr_latin.py` au lieu de `manga-ocr`). Sans cette
    colonne, le banc confondrait un effet de FORMAT avec un effet d'OCR.

    Elle est inférée parce que le cache ne porte pas la langue : `sources_manga.resoudre_source`
    la connaît, mais elle vit sous `sources/`, que le banc n'exige pas.

    ⚠ `CJK_TEXTE` et non `CJK` : la classe large inclut la ponctuation pleine chasse, si bien
    qu'une seule bulle latine ponctuée `（）` suffirait à faire déclarer le volume japonais.
    C'est la distinction que `core/tokens.py` documente, et le piège qu'elle évite."""
    from core import tokens
    joint = "".join(t for t in textes if t)
    if not joint.strip():
        return "?"
    return "cjk" if tokens.CJK_TEXTE.search(joint) else "latin"


def _glossaire_de(volume, config: dict | None):
    """Le `glossaire.yaml` de l'œuvre, ou `None`. **Ne lève jamais, et n'écrit rien.**

    Le banc lit `build/` et se lance pendant qu'un run tourne ; `sources/` peut ne pas être
    là du tout. Un glossaire absent doit donc rendre la colonne NON MESURÉE, pas vide.

    ⚠ **La lecture passe par une COPIE, et ce n'est pas de la prudence gratuite.**
    `glossary.load` MIGRE un fichier à l'ancien format vers le schéma multi-cibles, sauvegarde
    `.bak` comprise — un geste parfaitement légitime dans le pipeline, et inacceptable ici :
    cet outil promet en tête de fichier de ne rien réécrire, et il se lance pendant qu'un run
    tourne. Une migration déclenchée par une mesure réécrirait le travail humain accumulé sur
    plusieurs tomes, au moment précis où quelqu'un d'autre le lit. On copie donc dans un
    fichier temporaire : si migration il y a, elle a lieu sur la copie, qui est jetée."""
    if not config:
        return None
    try:
        import shutil
        import tempfile

        from core import glossary
        racine = banc.racine_sources(config)
        chemins = (config.get("chemins") or {})
        chemin = racine / volume.projet / chemins.get("glossaire_fichier", "glossaire.yaml")
        if not chemin.exists():
            return None
        with tempfile.TemporaryDirectory() as tmp:
            copie = Path(tmp) / chemin.name
            shutil.copyfile(chemin, copie)
            return glossary.load(copie)
    except Exception:      # noqa: BLE001 — un glossaire illisible ne doit pas casser le banc
        return None


def mesurer_volume(volume: banc.Volume, *, seuil_confiance: float, seuil_bilobee: float,
                   seuil_abandon: float, encre: bool = True,
                   config: dict | None = None) -> dict:
    """Une ligne de tableau pour un volume, lue dans son seul cache.

    ⚠ Toutes les mesures de DÉTECTION viennent de `regions.json` ; `qa.json` ne sert qu'à ce
    qu'il est seul à savoir (nettoyage, OCR, rendu). Mélanger les deux dénominateurs est
    exactement le défaut que ce lot corrige."""
    n_planches = n_bulles = n_sans_qa = 0
    n_zero = n_zero_encrees = n_zero_encre_inconnue = 0
    n_faible = n_sans_ocr = n_non_nettoyees = 0
    n_scindees = n_suspectes = n_degenerees = n_restaurees = 0
    par_planche: list[int] = []
    tailles: set[tuple[int, int]] = set()
    sources_encre: set[str] = set()
    sens: str | None = None
    textes_ocr: list[str] = []
    # Banc de traduction (L8.3) — relevé dans la même passe : rouvrir les 1 500 caches une
    # seconde fois pour huit compteurs serait payer deux fois la même lecture.
    n_vides = n_rattrapees = 0
    # Lot 15 — relevés dans la MÊME passe, et pour la même raison que ci-dessus : rouvrir
    # 1 500 caches une troisième fois pour trois compteurs serait payer trois fois la même
    # lecture. Aucun appel LLM, aucun masque rouvert : la structure est relue dans
    # `structure.json`, écrit par le pipeline (`checkpoints.save_structure`).
    n_glossaire_manque = 0
    registre_par_planche: dict[int, dict[str, int]] = {}
    types_bulle: dict[str, int] = {}
    motifs: dict[str, int] = {}
    strategies: dict[str, int] = {}
    origines: dict[str, int] = {}
    rapports_longueur: list[float] = []
    # Planches d'ORIGINE, résolues une fois pour le tome : c'est la TROISIÈME des quatre
    # sources du test d'encre (après `pages_out/` et `pages_clean/`, avant `qa["sfx"]`), et la
    # seule qui réponde sur un tome arrêté avant le rendu et sans contrôle qualité — le cas des
    # deux premiers volumes de *manga D*. `{}` dès que `sources/` est absent : le banc
    # continue alors de dire « non mesurée », ce qui est la vérité.
    sources_planches = banc.planches_sources(volume, config) if encre else {}
    # Glossaire de l'ŒUVRE, pour la colonne « glossaire manqué ». ⚠ Best-effort, et `None` si
    # `sources/` est absent : le banc ne l'EXIGE pas (c'est écrit en tête de ce fichier), et
    # une colonne non mesurée doit s'afficher « — », jamais « 0 ».
    glo = _glossaire_de(volume, config)
    # Langue CIBLE, pour le lexique de deuxième personne (`manga.registre`). Lue dans la
    # config plutôt que devinée : le relevé n'a de sens que dans la langue où l'on a écrit.
    cible = str(((config or {}).get("langues") or {}).get("cible") or "fr")

    for planche in banc.planches(volume):
        if not planche.a_des_regions:
            continue                      # planche jamais détectée : pas une planche à zéro
        n_planches += 1
        sens = sens or planche.sens
        if planche.image_size:
            tailles.add(tuple(planche.image_size))
        bulles = planche.bulles
        n_bulles += len(bulles)
        par_planche.append(len(bulles))
        n_faible += sum(1 for r in bulles if float(r.get("score", 1.0)) < seuil_confiance)
        n_scindees += sum(1 for r in bulles if r.get("scindee"))
        if not bulles:
            n_zero += 1
            if encre:
                porte, source = banc.porte_de_l_encre(
                    volume.build_dir, planche,
                    source_planche=sources_planches.get(planche.numero))
                sources_encre.add(source)
                if porte:
                    n_zero_encrees += 1
                elif porte is None:
                    # ⚠ Ni planche rendue ni `qa.json` : la question n'a pas de réponse. La
                    # compter comme « non encrée » ferait lire un zéro là où il n'y a pas de
                    # mesure — sur les deux volumes de manga D traités sans rendu,
                    # c'est 43 planches qui passeraient pour des pages de garde.
                    n_zero_encre_inconnue += 1

        # ⚠ Les trois relevés du lot 15 se font sur `ocr.json` / `traduction.json`, PAS sur
        # `qa.json`, et ils sont donc AVANT le `continue` ci-dessous — le même arbitrage que
        # la colonne « langue » juste en dessous : 423 planches du corpus n'ont pas de
        # `qa.json`, et leurs répliques sont pourtant sur le disque, à côté.
        if glo is not None:
            n_glossaire_manque += len(relecture.termes_manques(
                planche.ocr, planche.traduction, glo, page=planche.numero))
        compte = registre.relever_planche(planche.traduction, cible)
        if compte:
            registre_par_planche[planche.numero] = compte
        charge = banc.charger_json(planche.ckpt / "structure.json")
        structure = planche_mod.Structure.depuis_json(charge) if charge else None
        if structure is not None and len(structure) == len(bulles):
            for nom in structure.types:
                types_bulle[nom] = types_bulle.get(nom, 0) + 1

        if planche.qa is None:
            n_sans_qa += 1
            # ⚠ L'OCR est relevé AVANT le `continue` : sur les deux volumes de manga D, 419
            # planches n'ont pas de `qa.json` et la colonne « langue » sortait à
            # « ? » alors que `ocr.json` était là, à côté, parfaitement lisible.
            textes_ocr.extend(planche.ocr or ())
            continue
        qa = planche.qa
        n_restaurees += len(qa.get("restaurees") or [])
        strategie = qa.get("strategie_traduction") or "(non renseignée)"
        if bulles:
            strategies[strategie] = strategies.get(strategie, 0) + 1
        motif = qa.get("motif_traduction")
        if motif:
            motifs[motif] = motifs.get(motif, 0) + 1
        for b in planche.qa_bulles:
            source = (b.get("ocr") or "").strip()
            rendu = (b.get("traduction") or "").strip()
            textes_ocr.append(source)
            if not source:
                n_sans_ocr += 1
            elif not rendu:
                n_vides += 1
            if source and rendu:
                rapports_longueur.append(len(rendu) / len(source))
            if b.get("rattrapee"):
                n_rattrapees += 1
            origine = b.get("origine") or "pipeline"
            origines[origine] = origines.get(origine, 0) + 1
            # Bulle NON NETTOYÉE : le troisième indicateur de fausse détection. Il ne mesure
            # pas la même chose que « restaurée » (ni source ni réplique) ni que « sans OCR » —
            # ici le nettoyage lui-même a renoncé, l'uniformité étant sous `seuil_abandon`.
            if b.get("mode_nettoyage") == "aucun" \
                    or float(b.get("uniformite") or 1.0) < seuil_abandon:
                n_non_nettoyees += 1
            if b.get("debordement") and b.get("cause") == "bulle_degeneree":
                n_degenerees += 1
            rempl = b.get("remplissage_masque")
            if (not b.get("scindee") and rempl is not None and float(rempl) < seuil_bilobee
                    and b.get("forme") != "dentelee"):
                n_suspectes += 1

    releve_registre = registre.relever_tome(registre_par_planche)
    n_types = sum(types_bulle.values())
    ratios = [round(h / w, 1) for (w, h) in tailles if w]
    return {
        "volume": volume.nom,
        "projet": volume.projet,
        "tome": volume.tome,
        "régime": _regime(tailles, sens),
        "langue": _langue_source(textes_ocr),
        "planches": n_planches,
        "sans qa": n_sans_qa,
        "bulles": n_bulles,
        "médiane b/pl": statistics.median(par_planche) if par_planche else 0,
        "max b/pl": max(par_planche) if par_planche else 0,
        COL_ZERO_BULLE: n_zero,
        "dont encrées": n_zero_encrees if encre else None,
        "encre ?": n_zero_encre_inconnue if encre else None,
        "source encre": sorted(sources_encre) or None,
        "score faible": n_faible,
        "restaurées": n_restaurees,
        COL_SANS_OCR: n_sans_ocr,
        "non nettoyées": n_non_nettoyees,
        "scindées": n_scindees,
        "suspectes": n_suspectes,
        "dégénérées": n_degenerees,
        "taille planche": sorted(f"{w}×{h}" for (w, h) in tailles) or None,
        "ratio max": max(ratios) if ratios else None,
        # --- banc de traduction (L8.3) ---
        "vides à l'arrivée": n_vides,
        "motifs résiduels": motifs or None,
        COL_RATTRAPEES: n_rattrapees,
        "stratégies": strategies or None,
        "origines": origines or None,
        "longueur rendue/source": (round(statistics.median(rapports_longueur), 2)
                                   if rapports_longueur else None),
        # --- lot 15 : ce que le prompt a reçu, et ce que la traduction en a fait ---
        # `None` et non `0` quand le glossaire de l'œuvre est introuvable : « pas mesuré »
        # et « rien à signaler » ne doivent pas s'afficher pareil. Même règle que les colonnes
        # d'encre.
        "glossaire manqué": n_glossaire_manque if glo is not None else None,
        "registre": (f"{releve_registre.tutoiement} tu / {releve_registre.vouvoiement} vous"
                     if releve_registre.total else None),
        "basculements": len(releve_registre.basculements) or None,
        "types de bulle": types_bulle or None,
        "indéterminés": (f"{100 * types_bulle.get('indetermine', 0) / n_types:.0f} %"
                         if n_types else None),
    }


def _totaux(lignes: list[dict], colonnes: list[str]) -> dict:
    """Ligne de total. Les sommes seulement — une médiane de médianes ne veut rien dire, et
    l'afficher quand même serait exactement le genre de chiffre sans dénominateur que ce lot
    cherche à faire disparaître."""
    sommables = {"planches", "sans qa", "bulles", COL_ZERO_BULLE, "dont encrées", "encre ?",
                 "score faible",
                 "restaurées", COL_SANS_OCR, "non nettoyées", "scindées", "suspectes",
                 "dégénérées", "vides à l'arrivée", COL_RATTRAPEES}
    total: dict = {"volume": f"**TOTAL ({len(lignes)} volume(s))**"}
    for c in colonnes:
        if c in sommables:
            nombres = [v for v in (ligne.get(c) for ligne in lignes) if isinstance(v, int)]
            # ⚠ `None` si RIEN n'a été mesuré, et non `0` : avec `--sans-encre`, les colonnes
            # d'encre valent `—` sur chaque ligne, et un total à `0` s'y lirait « aucune
            # planche encrée » — le contraire de « pas mesuré ». C'est exactement le piège que
            # la colonne `encre ?` existe pour fermer.
            total[c] = sum(nombres) if nombres else None
        elif c not in ("volume",):
            total[c] = None
    return total


def _rendre(lignes: list[dict], colonnes: list[str], args, volumes) -> str:
    if args.json:
        return json.dumps(
            {"entete": {"commit": banc.commit_courant(),
                        "config": banc.empreinte_config(args.config),
                        "volumes": [v.nom for v in volumes]},
             "volumes": lignes},
            ensure_ascii=False, indent=1)
    tableau = banc.tableau_markdown(colonnes, [*lignes, _totaux(lignes, colonnes)])
    if not args.markdown:
        return tableau
    titre = "Banc de traduction" if args.traduction else "Banc de détection"
    commande = ("python tools/banc.py --tous --traduction --markdown" if args.traduction
                else "python tools/banc.py --tous --markdown")
    entete = banc.entete_publication(args.config, volumes, titre=titre, commande=commande)
    return "\n".join([*entete, tableau, ""])


def _corpus(args) -> int:
    """Rappel / précision / F1 contre un corpus annoté (L8.2). Séparé du tableau de volumes
    parce qu'il répond à une autre question : celui-ci mesure ce que le pipeline a produit,
    celui-là ce qu'il aurait DÛ produire."""
    from tools import _banc_detection as detection
    resultat = detection.mesurer_corpus(Path(args.corpus))
    if resultat is None:
        print(f"❌ Aucune annotation lisible sous {args.corpus}")
        return 1
    if args.json:
        # C'est cette sortie-là qui devient la LIGNE DE BASE de la CI
        # (`tests/corpus/synthetique/reference.json`) : elle porte le détail par planche, pas
        # seulement le bilan, pour qu'un diff de calibration dise QUELLE planche a bougé.
        print(json.dumps(resultat, ensure_ascii=False, indent=1))
        return 0
    print(detection.rendre(resultat, markdown=args.markdown))
    return 0


def main() -> int:
    # Sans ça, une console Windows en cp1252 lève `UnicodeEncodeError` sur le premier titre
    # japonais — après avoir affiché la moitié du tableau.
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Agrège les caches de build/ en un tableau comparable d'un run à l'autre.")
    ap.add_argument("projet", nargs="?", default=None)
    ap.add_argument("tome", nargs="?", default=None)
    ap.add_argument("--tous", action="store_true", help="tous les volumes de build/")
    ap.add_argument("--markdown", action="store_true",
                    help="tableau précédé de son en-tête de publication (date, commit, config)")
    ap.add_argument("--json", action="store_true", help="sortie JSON, pour tracer une courbe")
    ap.add_argument("--traduction", action="store_true",
                    help="le banc de TRADUCTION (huit lignes, aucun appel LLM)")
    ap.add_argument("--corpus", metavar="DOSSIER", default=None,
                    help="mesure rappel/précision/F1 contre un corpus annoté")
    ap.add_argument("--sans-encre", action="store_true",
                    help="ne pas ouvrir les planches (plus rapide, colonne « dont encrées » "
                         "laissée vide)")
    # Mesurer une COPIE d'un cache est le geste que le dépôt recommande pour expérimenter
    # sans toucher à `build/`, qui est en lecture seule. Sans ce flag il fallait éditer
    # `config.yaml` — c'est-à-dire changer l'empreinte que le tableau publie.
    ap.add_argument("--build", metavar="DOSSIER", default=None,
                    help="racine de build/ à mesurer (défaut : celle de config.yaml)")
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    if args.corpus:
        return _corpus(args)
    if not (args.tous or (args.projet and args.tome)):
        ap.error("indique « projet tome », ou --tous pour tous les volumes de build/.")

    config = charger_config(args.config)
    build_root = Path(args.build) if args.build else banc.racine_build(config)
    mcfg = config.get("manga") or {}
    rapport = mcfg.get("rapport") or {}
    scission = ((mcfg.get("detection") or {}).get("scission")) or {}
    nettoyage = mcfg.get("nettoyage") or {}

    if args.tous:
        volumes = banc.enumerer_volumes(build_root)
    else:
        build_dir = banc.build_dir_de(build_root, args.projet, args.tome)
        volumes = [banc.Volume(args.projet, args.tome, build_dir)] \
            if (build_dir / ".checkpoints").is_dir() else []
    if not volumes:
        cible = build_root if args.tous else f"{args.projet} / {args.tome}"
        print(f"❌ Aucun cache à mesurer : {cible}")
        return 1

    lignes = [mesurer_volume(v,
                             seuil_confiance=float(rapport.get("seuil_confiance", 0.50)),
                             seuil_bilobee=float(scission.get("seuil_suspect", 0.70)),
                             seuil_abandon=float(nettoyage.get("seuil_abandon", 0.35)),
                             encre=not args.sans_encre, config=config)
              for v in volumes]
    colonnes = COLONNES_TRADUCTION if args.traduction else COLONNES_DETECTION
    print(_rendre(lignes, colonnes, args, volumes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
