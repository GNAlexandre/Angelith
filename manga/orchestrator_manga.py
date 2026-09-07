# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Orchestration manga, en **deux balayages du volume** séparés par une passe terminologique :

    A. par planche : détection des bulles → nettoyage → OCR        (aucun appel LLM)
    B. tout le volume : relevé terminologique → dédoublonnage du glossaire
    C. par planche : traduction → forçage → lettrage → rendu

Le découpage n'est pas cosmétique. En une seule passe (jusqu'au lot 4.1), le relevé de la
planche 42 n'existait qu'après la traduction de la planche 41 : la planche 1 était traduite
avec un glossaire VIDE, le dédoublonnage tombait après la dernière traduction, et le contexte
du traducteur changeait à chaque planche. C'est la cause du défaut mesuré au lot 3 — un même
kanji rendu Mikage, Mitsukage puis Miyage d'une planche à l'autre.

Chaque étape est mise en cache sur disque (`manga/checkpoints.py`) : une page peut être reprise
ou RELANCÉE À N'IMPORTE QUELLE ÉTAPE sans refaire les précédentes — ex. `--from rendu` repart
directement des pages « clean » déjà générées (bulles vidées, sans texte) pour ne refaire QUE
le lettrage.

`process_volume(..., glossaire_seul=True)` n'exécute que A et la moitié « relevé » de B, puis
s'arrête : c'est ce que sert `run_manga.py --extract-glossary`, qui peuple le glossaire d'une
œuvre sans retraduire ni réécrire une seule planche (cf. `manga/glossaire_manga.py`).

Reprise/arrêt propre comme le pipeline LN (`pipeline.control`) : une page dont le
fichier de sortie FINAL existe déjà est sautée (sauf `force`/`restart_from`). Seule
la TRADUCTION est un « appel LLM » au sens du `dry_run` LN — détection/OCR restent
réels en dry-run (modèles locaux déterministes, pas le LLM configuré) : nécessitent
requirements-manga.txt installé et le modèle de détection téléchargé."""
from __future__ import annotations

import base64
import contextlib
import io
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from core import config as core_config
from core import (control, glossary, glossary_build, glossary_lang, power, quality,
                  runtime, tokens)
from core import memoire
from core.langues import resoudre_pack
from core.version import ETAT_BRIQUES, __version__

from ._config import fusion
from . import (bubbles_split, checkpoints, clean, consignes, detection, detection_retry,
               document as doc_mod, etat_planches, formats, geometry, ocr_routeur,
               planche as planche_mod, projet as projet_mod, psd, quality_manga, registre,
               relecture, render_manga, report_manga, sfx_lecture, sources_manga,
               terminology, text_detection, traduction_unitaire, typeset)
from . import rendu
# ⚠ Alias obligatoire : `gloss` est déjà le nom du GLOSSAIRE chargé dans `process_volume`
# (`gloss = glossary.load(...)`). Importer le module sous son nom nu le masquait au premier
# appel de glose.
from . import ocr as ocr_mod
from .agents_manga import build_manga_agents


#: Réglages de l'ESCALADE de détection (lot 12, L4.2). Les défauts vivent ici et nulle part
#: ailleurs, comme ceux de `detection.DEFAUTS_FENETRE` — `config.yaml` les redit pour
#: l'utilisateur, il ne les définit pas.
#:
#: ## Ce que coûte l'escalade, et pourquoi elle est livrée active
#:
#: Une inférence de plus sur les planches SUSPECTES seulement — 188 sur 1 513 au tableau
#: « avant », soit 12,4 % des planches. **Mesuré** (`docs/mesures/escalade-2026-08-25.md`) : 5,5 s par
#: planche suspecte de bout en bout — détection nominale, seconde inférence et les deux analyses
#: d'uniformité de l'arbitre —, 1 002 s pour les 183 planches. Rapporté au temps total
#: d'un tome — manga A Vol.2 : 46 min 56 s pour 150 planches, dont l'essentiel en LLM et en
#: PSD — c'est du bruit : la détection n'est pas l'étape chère.
#:
#: Ce que ça rapporte, mesuré au même endroit : **188 → 153 planches à zéro bulle** (−18,6 %),
#: 47 bulles gagnées sur 35 planches, et **zéro régression**.
#:
#: Aucun cache n'est invalidé : une planche déjà détectée est sautée comme avant, l'escalade ne
#: joue que sur une détection FRAÎCHE.
#:
#: `actif: false` rend exactement le comportement d'avant le lot 12.
DEFAUTS_ESCALADE = {
    "actif": True,
    # Le réglage plus sensible essayé sur une planche suspecte. `input_size` est le vrai levier
    # (cf. `detection.INPUT_SIZE`) : il multiplie la résolution effective par 1,6 sans changer
    # ce que le réseau sait faire, là où baisser `conf_threshold` ne fait qu'accepter ce qu'il
    # émettait déjà — et sur le webtoon, mesuré, descendre jusqu'à 0,10 ne gagnait AUCUNE bulle
    # « parce que le réseau ne les émet pas du tout ».
    "input_size": 1024,
    "conf_threshold": 0.20,
    # Déclencheur 2 : une planche très en dessous de la médiane du tome. `0.0` le désarme.
    "mediane_frac": 0.25,
    # …et il ne s'arme pas avant d'avoir vu assez de planches pour que la médiane veuille dire
    # quelque chose. Sans cette borne, la planche 2 d'un tome déciderait de la médiane.
    "mediane_echantillon_min": 20,
    # Seuil du test d'encre du déclencheur 1 (cf. `detection.SEUIL_ENCRE`).
    "seuil_encre": 0.004,
}


def cibles_de_run(only_page: int | None, only_pages, total: int):
    """Quelles planches un run doit traiter — `(cibles, alertes, abandon)`.

    `cibles = None` signifie « tout le tome » ; un ensemble le restreint. Fonction **pure**,
    et c'est délibéré : la logique de bornes vivait en ligne dans `process_volume`, donc elle
    n'était vérifiable qu'en faisant tourner un orchestrateur complet — avec ses modèles, son
    serveur LLM et ses minutes. Le cas qu'elle protège est pourtant précis et mérite un test :
    `--page 999` ne traitait rien mais allait quand même au bout, réécrivant `RAPPORT.md` et
    réencodant le CBZ, si bien qu'une faute de frappe passait pour un run réussi.

    Les deux restrictions se composent par **intersection** : `--page` ne peut qu'affiner une
    sélection, jamais l'élargir."""
    alertes: list[str] = []
    cibles: set[int] | None = None

    if only_pages is not None:
        cibles = {int(n) for n in only_pages}
        hors = sorted(n for n in cibles if not (1 <= n <= total))
        if hors:
            alertes.append(f"{len(hors)} planche(s) hors bornes ignorée(s) : "
                           + ", ".join(str(n) for n in hors[:8])
                           + (f" (+{len(hors) - 8})" if len(hors) > 8 else ""))
            cibles -= set(hors)
        if not cibles:
            alertes.append(f"Aucune planche valide à traiter (le tome en compte {total}). "
                           f"Rien n'a été réécrit.")
            return None, alertes, True

    if only_page is not None:
        if not (1 <= only_page <= total):
            alertes.append(f"--page {only_page} : le tome n'a que {total} planche(s). "
                           f"Rien n'a été traité, ni réécrit.")
            return None, alertes, True
        cibles = {only_page} if cibles is None else (cibles & {only_page})
        if not cibles:
            alertes.append(f"--page {only_page} n'appartient pas à la sélection demandée. "
                           f"Rien n'a été traité.")
            return None, alertes, True

    return cibles, alertes, False


def process_volume(project: str, volume: str, config: dict, reporter, force: bool = False,
                   restart_from: str | None = None, only_page: int | None = None,
                   only_pages=None,
                   conf_threshold: float | None = None,
                   iou_threshold: float | None = None,
                   passes_volume: bool = True,
                   glossaire_seul: bool = False,
                   langue: str | None = None,
                   format_planche: str | None = None) -> bool:
    """Traite un tome manga — le détail est dans `_process_volume`, dont la signature est
    identique. Cette enveloppe n'existe que pour **fermer les clients LLM** quand le tome
    sort par une exception.

    Le light novel porte ce filet depuis longtemps (`pipeline/orchestrator.py`), la brique
    manga ne l'avait pas : une exception inattendue y abandonnait les sockets Ollama en
    pleine génération. C'est exactement l'état que la docstring de `LLM.close` relie à une
    chute PERSISTANTE du débit GPU au run suivant — le pilote ne récupérant proprement qu'au
    redémarrage.

    Elle est écrite en enveloppe plutôt qu'en `try`/`finally` autour du corps parce que
    `_process_volume` fait plus de mille lignes : les réindenter d'un cran rendrait
    illisible tout diff ultérieur, pour un gain nul. Le `porteur` est le seul prix à payer —
    les agents naissent au milieu du corps, l'enveloppe doit pouvoir les atteindre."""
    porteur: dict = {}
    try:
        return _process_volume(project, volume, config, reporter, force=force,
                               restart_from=restart_from, only_page=only_page,
                               only_pages=only_pages, conf_threshold=conf_threshold,
                               iou_threshold=iou_threshold, passes_volume=passes_volume,
                               glossaire_seul=glossaire_seul, langue=langue,
                               format_planche=format_planche, _porteur=porteur)
    except BaseException:
        runtime.close_llm_clients(None, porteur.get("agents") or {})
        raise


def _process_volume(project: str, volume: str, config: dict, reporter, force: bool = False,
                    restart_from: str | None = None, only_page: int | None = None,
                    only_pages=None,
                    conf_threshold: float | None = None,
                    iou_threshold: float | None = None,
                    passes_volume: bool = True,
                    glossaire_seul: bool = False,
                    langue: str | None = None,
                    format_planche: str | None = None,
                    _porteur: dict | None = None) -> bool:
    """Traite un tome manga. Renvoie True si terminé, False si arrêté proprement
    (--stop / Ctrl+C) — même convention que `pipeline.orchestrator.process_volume`.

    `restart_from` (une valeur de `checkpoints.STAGES`) force la régénération de
    cette étape et de toutes les suivantes pour les pages déjà terminées, en
    réutilisant le cache des étapes précédentes. `force` ignore tout cache (refait
    tout, comme si rien n'était calculé). `only_page` restreint le traitement à une
    seule page (1-indexée) ; les autres restent inchangées.

    `passes_volume=False` saute les passes qui raisonnent à l'ÉCHELLE DU TOME — relevé
    terminologique, dédoublonnage du glossariste, fiche de contexte de l'œuvre. Destiné à
    l'éditeur graphique, qui relance une planche isolée : ces passes lisent ou réécrivent tout
    le volume, et les rejouer pour une bulle est du temps pur. Le glossaire déjà sur disque est
    lu normalement — seul son enrichissement est reporté au prochain run de tome.

    `glossaire_seul=True` ne fait tourner que ce qui ALIMENTE le glossaire de l'œuvre :
    détection et OCR des planches qui n'en ont pas encore, relevé terminologique de **toutes**
    les planches, détection de dérive. Le balayage de traduction n'est jamais atteint, et rien
    n'est écrit hors de `.checkpoints/` et de `sources/<Projet>/glossaire.yaml` — ni page
    nettoyée, ni page finale, ni `RAPPORT.md`, ni archive.

    C'est ce que sert `run_manga.py --extract-glossary`, et c'est un mode plutôt qu'un second
    orchestrateur pour une raison précise : le balayage A (migration du cache, scission
    bi-lobée, ordre de lecture, styles de bulle passés à l'OCR) est du code subtil, et une
    copie aurait dérivé. La différence avec un run normal tient en trois points — le travail
    par planche se limite à `{detection, ocr}`, **toute** planche OCRisée a le droit à un
    relevé (au lieu des seules planches qu'on va traduire), et le dédoublonnage du glossariste
    est laissé à l'appelant, qui ne le paie qu'une fois pour toute une œuvre.

    `only_pages` est la forme ENSEMBLISTE de `only_page` : elle restreint le run à un lot de
    planches nommées, en un seul démarrage d'orchestrateur. C'est ce dont l'éditeur graphique
    a besoin pour relettrer les six planches qu'on vient de corriger sans payer six fois le
    chargement des modèles et six réassemblages. Les deux se combinent par INTERSECTION, ce
    qui rend `--page 12` toujours plus restrictif, jamais plus large.

    ⚠ `only_page` restreint les deux BALAYAGES, mais pas la passe terminologique : celle-ci
    parcourt tout le volume pour re-fusionner les relevés déjà en cache, sans consommer un
    seul appel LLM hors de la planche visée. C'est ce qui permet de reprendre une planche
    isolée avec le glossaire complet de l'œuvre.

    `conf_threshold` / `iou_threshold` relancent la détection d'UNE planche à d'autres
    seuils. Ils **exigent `only_page`** — un changement de seuil pour tout le tome appartient
    à `config.yaml`, où il est tracé et relu au run suivant — et **impliquent
    `--from detection`**. L'écriture n'a lieu que si `manga.detection_retry.arbitrer`
    l'accepte : plus de bulles n'est pas mieux. Prévisualiser d'abord avec
    `tools/apercu_detection.py --balayage`, qui ne coûte qu'une inférence."""
    t_start = time.perf_counter()
    mcfg = config["manga"]
    # `manga.chemins` HÉRITE de la racine par fusion profonde (lot 2.3) : il n'a plus à
    # recopier `sources`/`build`, et il gagne `prompts`/`glossaire_fichier` — que ce code
    # allait justement chercher dans `config["chemins"]`, à deux endroits différents.
    chemins = core_config.section(config, "manga", "chemins")
    # Idem pour `manga.llm` : on n'a plus à y recopier base_url/api_key/timeout pour n'y
    # régler qu'un `thinking_budget`. C'était le piège tout-ou-rien que `config.yaml`
    # documentait faute de pouvoir le corriger.
    llm_cfg_manga = core_config.section(config, "manga", "llm")
    sources_root = Path(chemins["sources"])
    build_root = Path(chemins["build"])
    vol_dir = sources_root / project / volume
    build_dir = build_root / project / volume / "manga"
    (build_dir / "pages_out").mkdir(parents=True, exist_ok=True)
    (build_dir / "pages_clean").mkdir(parents=True, exist_ok=True)

    control.clear_stop(build_dir)
    control.install_sigint(reporter)

    plan = sources_manga.scan_volume(vol_dir, build_dir, config,
                                     langue=langue, format=format_planche)
    langue_src = plan.code_langue
    nom_langue = glossary_lang.nom_langue(langue_src)
    du_langue = glossary_lang.du_langue(langue_src)
    sens = formats.sens_lecture(config, plan.format)
    # Lot 32 — la PHASE, canal neuf et muet en console (`core/reporter.Reporter.phase`).
    # Les six phases d'un run manga sont déclarées dans `core/progression.PHASES_MANGA` ;
    # ici on ne fait que dire laquelle commence. Aucun ordre d'étape ne change : on observe.
    reporter.phase("preparation")
    # `reporter.volume()` est propre au LN (langues/pivot/chapitres) : la brique manga
    # écrit son propre en-tête, avec la version et l'état de la brique — un tome de
    # 150 planches se relance des semaines plus tard, il faut savoir avec quoi.
    reporter.info(f"Angelith {__version__} (brique manga : {ETAT_BRIQUES['manga']})")
    reporter.info(f"{project} / {volume} — {len(plan.pages)} page(s), source : {plan.source_kind}")
    # Format, langue et sens sont annoncés AVANT tout appel : c'est précisément ce qui
    # manquait au run raté du Chap.11, où rien n'indiquait que la chaîne attendait du
    # japonais sur des planches anglaises.
    reporter.info(f"Format : {plan.format} · langue source : {nom_langue} "
                  f"· lecture : {sens.replace('_', '→')}")
    for w in plan.warnings:
        reporter.info(f"⚠ {w}")

    # Une source DÉJÀ dans la langue de sortie ne se traduit pas. On s'arrête net plutôt que
    # de basculer en silence : changer ce que fait la commande sans le dire est pire que de
    # ne rien faire, et le mode qui convient existe déjà.
    if plan.mode == "glossaire" and not glossaire_seul:
        reporter.warn(
            f"{project} / {volume} est déjà en {nom_langue}, la langue de sortie : il n'y a "
            f"rien à traduire.\n"
            f"  → pour en relever le glossaire : "
            f"python run_manga.py \"{project}\" \"{volume}\" --extract-glossary\n"
            f"  → si la source n'est PAS en {nom_langue}, corrige le dossier de langue "
            f"(ou passe --langue).")
        return False

    # ⚠ Bornes de `--page`, AVANT les deux balayages. `--page 999` ne traitait rien mais
    # allait quand même au bout : `RAPPORT.md` était réécrit et le CBZ réencodé, si bien
    # qu'une faute de frappe passait pour un run réussi. Un numéro hors bornes est une erreur
    # de commande, pas un tome vide.
    cibles, alertes, abandon = cibles_de_run(only_page, only_pages, len(plan.pages))
    for alerte in alertes:
        reporter.warn(alerte)
    if abandon:
        return False

    # ─── Pré-vol de la police ─────────────────────────────────────────────────────────────
    # Avant tout chargement de modèle : le défaut qu'on cherche ici est SILENCIEUX, et il
    # coûtait jusqu'à présent un tome entier pour se manifester. Le lettrage choisit sa
    # police bulle par bulle ; un basculement propre ne laisse aucune trace, et c'est en
    # relisant `RAPPORT.md` après dix minutes de rendu qu'on découvrait que 63 bulles sur
    # 818 étaient sorties en Comic Neue au lieu de la police demandée.
    #
    # On lit les traductions en cache — ~150 petits JSON, moins de 100 ms, aucun modèle — et
    # on mesure la police sur ce qui sera RÉELLEMENT dessiné. On avertit, on ne refuse pas :
    # c'est la règle du dépôt (`core/config.py`), et une police incomplète reste un tome
    # lisible.
    #
    # ⚠ `cibles is None` signifie « tout le tome » (cf. `cibles_de_run`), pas « rien ».
    textes_en_cache: dict[int, list[str]] = {}
    for index in (sorted(cibles) if cibles is not None
                  else range(1, len(plan.pages) + 1)):
        ckpt = checkpoints.page_checkpoint_dir(build_dir, index)
        textes, _remplaces = checkpoints.appliquer_manuelles(
            checkpoints.load_traduction(ckpt), checkpoints.load_traduction_manuelle(ckpt))
        if textes:
            textes_en_cache[index] = textes
    for ligne in typeset.message_couverture(
            typeset.couverture((mcfg.get("typeset") or {}).get("font_path") or None,
                               textes_en_cache)):
        reporter.warn(ligne)

    # Relance CIBLÉE de la détection. Deux contraintes, et chacune évite un dégât : sans
    # `--page`, un seuil s'appliquerait à 150 planches sans laisser de trace au run suivant
    # (sa place est `config.yaml`) ; sans `--from detection`, l'étape ne serait même pas
    # rejouée et la commande n'aurait aucun effet visible.
    seuils_ponctuels = conf_threshold is not None or iou_threshold is not None
    if seuils_ponctuels:
        if only_page is None:
            reporter.warn("--conf / --iou exigent --page : un seuil pour tout le tome "
                          "appartient à `config.yaml > manga.detection`, où il est tracé. "
                          "Rien n'a été traité.")
            return False
        restart_from = "detection"
        reporter.info(f"Relance de détection sur la planche {only_page} — conf "
                      f"{conf_threshold if conf_threshold is not None else 'défaut'} · iou "
                      f"{iou_threshold if iou_threshold is not None else 'défaut'} "
                      f"(l'arbitre décide de l'écriture)")

    dry_run = bool(config.get("options", {}).get("dry_run", False))
    verbose = bool(config.get("options", {}).get("verbose", False))
    # ⚠ **Le mode SANS LLM** (lot 39). Lu par héritage profond, comme tout le reste de la
    # section manga : `manga.llm.actif` l'emporte sur `llm.actif`, et le défaut est `true`.
    #
    # Ce n'est PAS `--dry-run`, et la distinction est le cœur du lot. `--dry-run` SIMULE une
    # traduction : le texte source traverse l'agent inchangé et s'écrit comme s'il était
    # traduit. Ici, rien ne prétend avoir traduit — les bulles sortent vides, le rapport le
    # dit planche par planche, et aucun client LLM n'est même contacté.
    sans_llm = not bool(core_config.section(config, "manga", "llm").get("actif", True))
    if sans_llm:
        reporter.info("Mode SANS LLM : détection, nettoyage, OCR et rendu seulement. Les "
                      "bulles sortiront VIDES — saisis les répliques dans la Retouche, elles "
                      "iront dans traduction_manuelle.json, que le pipeline ne réécrit jamais.")
    _appliquer_reflexion_lot(config, reporter)
    agents = build_manga_agents(config, dry_run=dry_run)
    # Confié à l'enveloppe pour qu'elle sache quoi fermer si le tome sort par une exception.
    if _porteur is not None:
        _porteur["agents"] = agents
    # Les incidents des clients LLM (budget « thinking » épuisé, nouvelle tentative, réponse
    # inexploitable) partaient sur stdout via un `print()` brut : après un run de nuit sur
    # 150 planches, plus aucune trace de quelle page avait dérapé ni pourquoi. Ils passent
    # désormais par `reporter.warn`, donc aussi dans perf.log — le LN avait déjà ce
    # branchement, la brique manga non.
    runtime.wire_reporter(None, agents, reporter)
    # ⚠ Trois valeurs depuis le lot 15, et `mode_vision` n'en couvre qu'UNE. `"cible"` ne
    # joint aucune image d'emblée : c'est le diagnostic du premier essai qui décide, planche
    # par planche, d'en joindre les crops de groupe (cf. `_translate_page`). Le distinguer ici
    # évite que la vision ciblée soit écrêtée par `planches_vision`, qui n'a de sens que pour
    # un mode où CHAQUE planche porte une image pleine page.
    mode_traduction = str(mcfg.get("mode_traduction", "texte"))
    mode_vision = mode_traduction == "vision" and not dry_run
    if dry_run:
        mode_traduction = "texte"
    # Seuils du classifieur de structure (`manga.planche`). Absents : les défauts du module,
    # calibrés sur le corpus de `build/`.
    structure_cfg = mcfg.get("structure") or {}
    structure_active = bool(structure_cfg.get("actif", True))
    # ⚠ `manga.garde_fous`, et non la clé `garde_fous` de PREMIER NIVEAU du light novel. Cette
    # dernière est hors du bloc `manga:`, donc structurellement inatteignable depuis `mcfg` —
    # ce qui explique que le manga n'ait jamais eu de garde-fou de perte de contenu, et que
    # `grep -rn perte_mots manga/` renvoyait zéro. Le lot 15 lui en donne un, chez lui.
    garde_fous_cfg = mcfg.get("garde_fous") or {}
    ratio_court = garde_fous_cfg.get("ratio_court") or None

    # ⚠ Via la surcouche de FORMAT, pas `mcfg["detection"]` en dur : c'est ce qui permet à
    # `manga.formats.webtoon.detection` de régler le découpage des bandes allongées sans
    # toucher aux réglages du manga paginé.
    det_cfg = formats.config_format(config, plan.format, "detection")

    # Chargement PARESSEUX du détecteur et de l'OCR : les deux étaient construits ici,
    # inconditionnellement, avant la boucle. Deux conséquences, toutes deux corrigées :
    #  · `BubbleDetector.__init__` lève SystemExit si le .onnx est absent — `--from
    #    nettoyage` et `--from rendu`, qui n'ont PAS besoin du détecteur (les régions
    #    viennent de `.checkpoints/`), échouaient donc immédiatement. C'est exactement la
    #    commande de vérification du lot 1 ;
    #  · `MangaOCR()` charge un modèle ViT+BERT (plusieurs secondes, et de la VRAM) même
    #    pour un simple relettrage — d'où un `--from rendu` bien plus lent qu'annoncé.
    # Les deux modèles ne sont désormais chargés qu'à leur premier usage réel, et une seule
    # fois pour tout le tome (coût d'initialisation inchangé quand ils servent vraiment).
    _lazy: dict = {}

    def get_detector():
        if "det" not in _lazy:
            _lazy["det"] = detection.BubbleDetector.depuis_config(det_cfg, dire=reporter.info)
        return _lazy["det"]

    def get_reader():
        # ⚠ Le moteur dépend de la LANGUE SOURCE : `manga-ocr` sur du japonais, RapidOCR sur
        # du latin. Lire de l'anglais avec `manga-ocr` ne dégrade pas la qualité, ça produit
        # une sortie structurellement fausse (cf. `manga/ocr_latin.py`) — et toute la chaîne
        # en aval traduit alors consciencieusement de la bouillie.
        if "ocr" not in _lazy:
            _lazy["ocr"] = ocr_routeur.lecteur_pour(langue_src, mcfg.get("ocr"),
                                                    dire=reporter.info)
        return _lazy["ocr"]

    def get_text_detector():
        if "txt" not in _lazy:
            _lazy["txt"] = text_detection.TextDetector.depuis_config(
                sfx_cfg, det_cfg, dire=reporter.info)
        return _lazy["txt"]

    # Glossaire de l'œuvre — le MÊME fichier que le light novel (`sources/<Projet>/
    # glossaire.yaml`), ce qui garde les noms cohérents entre un roman et son manga. Il sert
    # à trois choses depuis le lot 3 :
    #   · injection en contexte du traducteur (préventif : les planches suivantes convergent) ;
    #   · forçage déterministe des entrées `force: true` sur les bulles rendues (curatif) ;
    #   · cible d'écriture du terminologue, s'il est configuré.
    gloss_path = sources_root / project / chemins.get("glossaire_fichier", "glossaire.yaml")
    # ⚠ Le PACK est retenu, pas seulement ses règles d'accord. Le code écrivait
    # `resoudre_pack(config).accorder()` et jetait le pack aussitôt — or il porte aussi
    # `Pack.consigne`, c'est-à-dire les consignes que le code assemble lui-même. La seule du
    # chemin manga (`traduction_unitaire.CLE_CONSIGNE`) n'était donc jamais surchargée : pour
    # toute cible non française, le rattrapage unitaire réclamait une traduction FRANÇAISE par
    # une consigne codée en dur, au beau milieu d'un run anglais.
    pack = resoudre_pack(config)
    # ⚠ Les gabarits de consigne du chemin manga sont rendus UNE fois, ici, avec des valeurs
    # factices (lot 15, L7.12). Un pack dont `manga_separateur_planche` porterait `{page}` au
    # lieu de `{planche}` lèverait sinon au premier lot groupé — après la détection, le
    # nettoyage et l'OCR de vingt planches. Le dépôt refuse déjà un pack à qui il manque un
    # prompt pour exactement cette raison.
    consignes.verifier(pack)
    # Règles d'accord de la LANGUE CIBLE (cf. `core.langues.Pack.accorder`) : le français
    # accorde le déterminant et répare les élisions, l'anglais n'a rien à accorder.
    accord = pack.accorder()
    gloss = glossary.load(gloss_path) or glossary.empty()
    gloss_index = glossary_build.build_index(gloss)
    gloss_text = glossary.to_text(gloss, max_tokens=4000) if glossary.total(gloss) else ""

    # `terminologue` et `glossariste` sont OPTIONNELS : absents de `manga.modeles`, la brique
    # se comporte exactement comme avant (le glossaire existant est lu, jamais écrit). Les
    # activer, c'est ajouter une entrée à `manga.modeles` — les prompts sont ceux du LN, tels
    # quels, les agents étant agnostiques du média.
    agent_term = agents.get("terminologue")
    agent_gloss = agents.get("glossariste")
    stats_gloss = {"ajouts": 0, "fusions": 0, "conflits": 0, "pages_relevees": 0,
                   "pages_reprises": 0,
                   # Le rapport doit pouvoir dire « passe DÉSACTIVÉE » plutôt que d'afficher
                   # des zéros qui se lisent comme une panne : c'est exactement ce qui a fait
                   # croire, sur le run v0.21.0, que la terminologie s'était cassée.
                   "terminologue_actif": agent_term is not None,
                   "glossariste_actif": agent_gloss is not None,
                   "derives_bannies": 0}
    stats_force = {"remplacements": 0}
    # Ce que le mode sans LLM a laissé vide. ⚠ Compté pour que `RAPPORT.md` puisse écrire
    # « non traduit » plutôt que d'afficher des zéros qui se lisent comme une panne — même
    # motif que `terminologue_actif`, et même leçon (le run v0.21.0).
    stats_sans_llm = {"pages": 0, "bulles": 0, "actif": sans_llm}
    # Corrections manuelles reprises du disque (lot 16) : comptées pour que le rapport dise
    # qu'une planche ne doit PAS être jugée sur la sortie du modèle.
    stats_manuelles = {"bulles": 0, "pages": 0}
    force_refus: list[str] = []

    # Détection de dérive : purement lexicale, AUCUN appel LLM — donc active même quand le
    # terminologue ne l'est pas. C'est elle qui alimente les `interdits`, que le forçage
    # attendait sans que rien ne les écrive jamais.
    derive_cfg = mcfg.get("terminologie") or {}
    derives: list[terminology.Derive] = []

    # Rattrapage unitaire des bulles laissées vides — le seul lot qui consomme des appels LLM
    # en plus, et il en consomme peu : trois appels courts sur les 150 planches du Vol.1.
    rattrapage_cfg = mcfg.get("rattrapage") or {}
    rattrapage_refus: list[str] = []

    # Texte SUR LE DESSIN (lot 9) — onomatopées, narration libre. Le second modèle ONNX n'est
    # chargé que si la passe est active ET qu'une planche a réellement besoin d'elle.
    sfx_cfg = mcfg.get("onomatopees") or {}
    # ⚠ Éteinte en mode `glossaire_seul` : la passe charge un SECOND modèle ONNX, lit le texte
    # posé sur le dessin et ne nourrit que le rendu — or ce mode ne rend rien. Le glossaire ne
    # se peuple que depuis les bulles.
    # ⚠ Défaut `False`, et il ne dit PAS la même chose que `config.yaml > manga.onomatopees.actif`
    # — qui est livré à `true`. Les deux répondent à deux questions différentes :
    #
    #   · la config livrée dit ce que le projet RECOMMANDE, et l'utilisateur la lit ;
    #   · ce défaut-ci dit ce qu'il faut faire quand le bloc `onomatopees` est ABSENT du
    #     fichier — configuration antérieure au lot 9, config minimale, fixture de test. Là,
    #     personne n'a rien choisi, et déclencher le téléchargement de 94,7 Mo de poids
    #     (`models.py`) plus une passe OCR complète sur tout le tome serait décider à la place
    #     de quelqu'un qui n'a pas été consulté.
    #
    # Le code disait `True` : une clé absente activait donc la passe en silence. Un défaut de
    # repli se choisit sur ce qu'il coûte quand on se trompe, pas sur ce qui est recommandé.
    sfx_actif = bool(sfx_cfg.get("actif", False)) and not glossaire_seul
    # "rapport" par défaut : on détecte, on lit, on traduit — et on n'écrit rien sur la
    # planche. La DÉTECTION est fiable, la LECTURE ne l'est pas (`manga-ocr` est un modèle de
    # dialogue et hallucine sur une onomatopée stylisée), et la règle de la brique est qu'une
    # mauvaise réplique dessinée est pire qu'une absence signalée.
    sfx_mode = str(sfx_cfg.get("mode", "rapport")).lower()
    # ⚠ Défaut `False`, comme `actif`, et pour la même raison : joindre le crop d'une zone
    # EXIGE un modèle capable de vision, et un défaut de repli se choisit sur ce qu'il coûte
    # quand on se trompe. La config livrée la RECOMMANDE (`manga.onomatopees.vision: true`)
    # parce que la mesure est sans appel — l'OCR hallucine sur un glyphe stylisé — mais une
    # configuration antérieure au lot 15, ou un `manga_onomatopees` pointé sur un modèle
    # texte, ne doit pas se mettre à échouer sans avoir été consultée.
    sfx_vision = bool(sfx_cfg.get("vision", False)) and not dry_run
    # --- Lot 21 : les trois clés de lecture, TOUTES désarmées par défaut ----------------
    #
    # `concordance` coûte un appel LLM de plus par planche porteuse ; `crops_illisibles`
    # coûte une écriture disque par zone ; `broderie_ratio` VIDE des traductions. Aucune des
    # trois ne s'arme sans que l'utilisateur l'ait écrit — mais `config.yaml` les recommande
    # avec le chiffre qui les justifie, et c'est le motif déjà suivi par `actif` et `vision`.
    sfx_concordance = bool(sfx_cfg.get("concordance", False)) and not dry_run
    sfx_crops = max(0, int(sfx_cfg.get("crops_illisibles", 0) or 0))
    sfx_broderie = max(0.0, float(sfx_cfg.get("broderie_ratio",
                                              quality_manga.BRODERIE_RATIO) or 0.0))
    # Les deux bornes hautes de L21.1, désarmées elles aussi — et pour une raison mesurée,
    # pas prudentielle : la distribution d'aire ne sépare pas le dessin du texte, et le
    # dessin pris pour du texte est PLUS PETIT que les vraies onomatopées (cf.
    # `text_detection.AIRE_MAX_FRAC`).
    sfx_aire_max = max(0.0, float(sfx_cfg.get("aire_max_frac",
                                              text_detection.AIRE_MAX_FRAC) or 0.0))
    sfx_remplissage_max = max(0.0, float(sfx_cfg.get(
        "remplissage_max", text_detection.REMPLISSAGE_MAX) or 0.0))
    agent_sfx = agents.get("manga_onomatopees")
    # ── Effacement du texte hors bulle (lot 22) ─────────────────────────────────────────
    #
    # ⚠ DÉSARMÉ dans le code comme dans `config.yaml`, et pour une raison mesurée plutôt que
    # prudentielle : `manga/effacement.py` n'efface qu'une zone `lecture_sure`, et ce taux est
    # de 0 % sur les six tomes du corpus faute de seconde voie de lecture. Armer le mode ne
    # changerait donc aujourd'hui pas un pixel — ce qui est exactement ce que le lot publie.
    sfx_eff_cfg = dict(sfx_cfg.get("effacement") or {})
    sfx_eff_mode = str(sfx_eff_cfg.get("mode") or "aucun").lower()
    stats_sfx = {"zones": 0, "traduites": 0, "posees": 0, "pages": 0,
                 "actif": sfx_actif, "agent": agent_sfx is not None, "mode": sfx_mode,
                 "mobilier": 0, "groupes_mobilier": [], "tri": {},
                 "concordance": sfx_concordance, "rejets": {},
                 "effacement_mode": sfx_eff_mode, "effacement": {},
                 "effacees": 0, "relettrees": 0}
    sfx_refus: list[str] = []
    # Planches dont le PSD a été REFUSÉ faute de tenir dans les limites du format (lot 14,
    # L6.6). Elles gardent tous leurs autres formats de sortie ; c'est le fichier de retouche
    # qui manque, et le rapport doit le dire — sinon `pages_psd/` compte une planche de moins
    # que `pages_out/` sans que rien n'explique laquelle.
    psd_refuses: list[str] = []
    # ⚠ **Le chiffre qui n'existait nulle part** (lot 14, L6.0). Le dépôt mesurait ses durées,
    # ses bulles et ses tokens, jamais sa mémoire — donc personne ne savait si un tome tient
    # sur la machine d'un contributeur. La question n'est pas théorique sur ce format : une
    # bande de 1080×10 000 porte des masques booléens PLEINE PAGE de 10,8 Mo pièce, et rien ne
    # borne leur nombre.
    #
    # Deux niveaux de grain, et ils ne répondent pas à la même question : `perf.log` porte le
    # pic AUTOUR de chaque passe visuelle (« quelle étape faut-il réparer »), `RAPPORT.md`
    # porte le pic du tome (« est-ce que ça tient »).
    pic_tome: int | None = memoire.pic()
    # Zones dont le dessin d'origine a été recollé faute de tout texte — fausses détections
    # probables, listées au rapport (cf. `rendu.restaurer_sans_texte`).
    zones_restaurees: list[str] = []

    # VRAM : si la détection tourne sur GPU (DirectML), décharger le LLM une fois
    # AVANT de commencer (il se recharge tout seul à la 1re traduction) — évite le
    # cumul CV+LLM sur un même GPU (cf. plan de faisabilité, § contraintes VRAM).
    if not dry_run and "DmlExecutionProvider" in (det_cfg.get("providers") or []):
        power.ollama_unload(llm_cfg_manga["base_url"], agents["manga_traducteur"].modele)

    # Valide le nom d'étape UNE fois, avant la boucle : `stages_to_redo` lèverait sinon la
    # même erreur à la première page, après le scan du tome et le chargement des agents.
    if restart_from:
        checkpoints.stage_index(restart_from)
    font_path = (mcfg.get("typeset") or {}).get("font_path") or None

    stats_trad: dict = {}
    # Contexte inter-planches. La continuité du dialogue ne s'attrape pas sur une planche
    # isolée (pronoms, sujets implicites) : le traducteur reçoit les dernières répliques des
    # planches qui précèdent. Élargi de 1 à 3 planches au lot 14 — coût mesuré ~+100 tokens par
    # prompt, soit +4 % du prefill d'un tome (318 390 tok), pour la continuité sur une scène
    # entière plutôt que sur une seule planche.
    contexte_cfg = mcfg.get("contexte") or {}
    contexte_planches = int(contexte_cfg.get("planches_precedentes", 3))
    contexte_repliques = int(contexte_cfg.get("repliques_max", 18))

    # Traduction par LOTS de planches (défaut 1 = comportement de la 1.0.0, un appel par
    # planche). Le plafond `planches_vision` est distinct parce que le mode vision met une
    # image PLEINE PAGE par planche dans le prompt : 20 planches y satureraient le contexte
    # avant même la première réplique.
    lot_cfg = mcfg.get("lot") or {}
    taille_lot = max(1, min(MAX_PLANCHES_LOT, int(lot_cfg.get("planches", 1))))
    if mode_vision:
        plafond_vision = max(1, int(lot_cfg.get("planches_vision", 4)))
        if taille_lot > plafond_vision:
            reporter.info(f"[traduction] mode vision : lot ramené de {taille_lot} à "
                          f"{plafond_vision} planches (une image pleine page par planche)")
            taille_lot = plafond_vision
    plafond_lot = int(lot_cfg.get("plafond_sortie", 6000))
    num_ctx_declare = int(llm_cfg_manga.get("num_ctx", 0) or 0)
    # Niveau de raisonnement RÉELLEMENT appliqué au traducteur, tel qu'il partira dans
    # `qa.json`. Lu sur la spec du modèle après `_appliquer_reflexion_lot`, donc en tenant
    # compte de `--think` : c'est la seule valeur qui décrive ce qui a tourné.
    _spec_trad = (mcfg.get("modeles") or {}).get("manga_traducteur")
    reflexion_traducteur = (_spec_trad.get("think") if isinstance(_spec_trad, dict)
                            else None)

    # Scission des régions bi-lobées : la même fonction sert à la détection fraîche ET à la
    # migration du cache (`checkpoints.migrate_page`), pour qu'un tome migré et un tome
    # re-détecté donnent exactement les mêmes bulles.
    scission_cfg = (det_cfg.get("scission") or {})

    # Sonde d'ENCRE (lot 13, L5.5) : livrée INACTIVE, et menée comme une évaluation avec un
    # critère d'abandon écrit à l'avance (cf. `bubbles_split._ENCRE_DEFAUTS`). La luminance
    # n'est calculée que si la sonde est armée — c'est une conversion pleine page par planche.
    encre_active = bool(((scission_cfg.get("encre") or {}).get("actif", False)))

    def _scinder(regions, gris=None):
        return bubbles_split.scinder_regions(regions, scission_cfg, gris)

    def _fabriquer_regions(brutes, sens_lecture, gris=None):
        """Détections BRUTES du réseau → régions telles qu'elles seront écrites.

        Scission, masques rendus disjoints, ordre de lecture. Factorisée parce que l'escalade
        (L4.2) doit faire subir aux candidates **exactement** le même traitement qu'aux
        détections nominales : comparer un jeu scindé et disjoint à un jeu brut ferait dire à
        l'arbitre n'importe quoi.

        Renvoie `(régions, diagnostics de scission, chevauchements, régions absorbées)`."""
        scindees, diag = _scinder(brutes, gris)
        # Tri par score DÉCROISSANT d'abord : `rendre_disjoints` donne les pixels partagés à la
        # première région de la liste, et la bulle la mieux notée est le bon arbitre. L'ordre
        # d'entrée n'a aucune autre conséquence, `reading_order` rangeant ensuite par géométrie.
        #
        # ⚠ **Ce n'était pas une évidence, et le lot 12 (L4.6) l'a MESURÉ** plutôt que de
        # trancher par l'argument. Trois arbitres défendables — score, aire, compacité — rejoués
        # sur 125 planches de cinq volumes, dont 15 portent un recouvrement réel (de 6 px à
        # 166 146 px) :
        #
        #   · l'aire totale cédée est la MÊME dans les trois cas (344 939 px) — elle ne dépend
        #     pas de l'ordre mais de la géométrie, seul le *bénéficiaire* change ;
        #   · sur **14 des 15**, les trois ordres donnent un résultat rigoureusement identique,
        #     y compris sur le plus gros recouvrement du corpus paginé (166 146 px, manga B
        #     p91). Sur du manga paginé, la question ne se pose donc pas ;
        #   · sur **la quinzième**, un webtoon (webtoon A Chap.11 p1, 122 877 px
        #     partagés), l'ordre décide : trier par AIRE laisse zéro région non nettoyable, le
        #     score et la compacité en laissent une.
        #
        # Le score est CONSERVÉ : basculer un critère qui donne le même résultat 14 fois sur 15
        # au vu d'une seule observation serait exactement le réglage à l'aveugle que ce dépôt
        # évite. Ce qui trancherait vraiment, c'est un corpus webtoon plus large — et là-bas le
        # vrai correctif n'est de toute façon pas l'ordre, mais le format de `masks.png`, une
        # image d'étiquettes où un pixel ne peut appartenir qu'à une région.
        #
        # ⚠ Le lot 14 a repris la question et ne l'a PAS réparée, en le disant : élargir
        # l'étiquette borne le nombre de régions, pas le partage des pixels. Il faudrait un
        # masque par région, donc un autre format de cache, pour un défaut qui touche
        # 15 planches sur 125. Cf. `docs/mesures/webtoon-2026-08-26.md`.
        #
        # Ce que le lot 12 change ici et maintenant : le conflit remonte dans `RAPPORT.md` avec
        # ses deux protagonistes et l'aire partagée, donc la question reste mesurable au lieu
        # d'être invisible.
        scindees = sorted(scindees, key=lambda r: -r.score)
        avant = [int(r.mask.sum()) for r in scindees]
        # ⚠ L'appariement passe par `origines`, jamais par `id()` : `rendre_disjoints`
        # reconstruit CHAQUE région (`dataclasses.replace`), y compris celles qu'elle n'a pas
        # touchées. C'est précisément pour cela qu'elle rend cette liste.
        disjointes, origines = doc_mod.rendre_disjoints(scindees)
        chevauchements = [
            {"perdus": avant[k] - int(r.mask.sum()), "score": float(r.score),
             # La BOÎTE de la bulle rognée : sans elle, `RAPPORT.md` annonce « 36 108 px
             # perdus » sans dire où, ce qui n'est pas actionnable. Le rapport décrit le tome ;
             # une ligne qu'on ne peut pas aller voir ne le décrit pas.
             "bbox": list(r.bbox)}
            for r, k in zip(disjointes, origines) if int(r.mask.sum()) < avant[k]]
        absorbees = len(scindees) - len(disjointes)
        return (ocr_mod.reading_order(disjointes, sens_lecture), diag, chevauchements,
                absorbees)

    def _uniformites(image, regions, cfg_nettoyage) -> dict[int, float]:
        """Uniformité mesurée par le NETTOYEUR, par index de région — la mesure sur laquelle
        l'arbitre de relance s'adosse plutôt que d'inventer un second critère."""
        return {k: float(getattr(s, "uniformity", 0.0))
                for k, s in enumerate(clean.analyze_regions(image, regions, cfg_nettoyage))}

    # ─────────────────────────────────────────────────────────────────────────
    # Escalade de détection (lot 12, L4.2) — « plus aucune planche muette »
    #
    # Une planche est SUSPECTE quand elle contredit ses voisines. Le pipeline connaît déjà ses
    # voisines : il traite le tome entier, en deux balayages. La machinerie de réparation, elle,
    # existait et était calibrée depuis le lot 4.2 — `manga/detection_retry.py`, quatre vétos
    # ordonnés — mais elle avait UN seul site d'appel, `--conf`/`--iou` en ligne de commande
    # avec `--page` obligatoire. Rien ne la déclenchait jamais : `len(regions) == 0` ne
    # déclenchait rien du tout, et un `regions.json` vide s'écrivait en silence.
    #
    # Mesuré sur les dix volumes de `build/` : **188 planches sur 1 513 rendent zéro bulle**
    # (12,4 %), dont **183 portent de l'encre**. C'est le chiffre du lot.
    # ─────────────────────────────────────────────────────────────────────────
    seuil_abandon_tome = float((mcfg.get("nettoyage") or {}).get("seuil_abandon", 0.35))
    esc_cfg = fusion(DEFAUTS_ESCALADE, det_cfg.get("escalade"))
    escalade_active = bool(esc_cfg["actif"])
    # Nombres de bulles des planches DÉJÀ détectées de ce tome, pour le second déclencheur.
    # Une médiane courante et non la médiane finale : au premier balayage, les planches
    # suivantes n'ont pas encore été vues. C'est une approximation assumée — elle se stabilise
    # après quelques dizaines de planches, et le déclencheur ne s'arme qu'à partir de
    # `mediane_echantillon_min`.
    comptes_du_tome: list[int] = []

    def _suspecte(regions, image) -> str:
        """Pourquoi cette planche mérite une seconde inférence — `""` si elle n'en mérite pas.

        Les déclencheurs sont donnés PAR ORDRE DE CERTITUDE, et le premier qui répond décide :
        c'est l'idiome du dépôt (`quality_manga.MOTIFS`, `detection_retry.LIBELLES`)."""
        if not escalade_active:
            return ""
        if not regions:
            # Le cas le plus net et le plus fréquent. Le test d'encre est ce qui sépare la page
            # de garde de la pleine page d'action — sans lui, l'escalade tournerait sur les
            # séparateurs blancs. Il est délibérément indépendant de la passe onomatopées :
            # `qa["sfx"]`, le seul discriminant qui existait, n'existe pas quand elle est
            # inactive, et les trois volumes de manga D n'ont aucun `sfx.json`.
            return "zero_bulle_encree" if detection.porte_de_l_encre(
                image, seuil=float(esc_cfg["seuil_encre"])) else ""
        n = int(esc_cfg["mediane_echantillon_min"])
        if len(comptes_du_tome) >= n:
            mediane = statistics.median(comptes_du_tome)
            if mediane > 0 and len(regions) <= mediane * float(esc_cfg["mediane_frac"]):
                # Les médianes mesurées vont de 3 (manga B) à 6 (manga A Vol.3/4, manga C,
                # manga D Vol.1) : une planche à 1 bulle dans un tome à médiane 6
                # mérite un second regard.
                return "sous_la_mediane"
        return ""

    # PSD à calques : produit DANS la boucle et non par `assemble_outputs`, parce qu'il a besoin
    # des `Fit` de la planche — que l'assemblage, qui ne voit que des pages finies, n'a pas.
    # C'est un format « dossier de pages », comme `"images"`, pas une archive.
    rendu_cfg = mcfg.get("rendu") or {}
    psd_actif = "psd" in (rendu_cfg.get("formats") or [])

    n_done = 0
    n_migrees = 0
    # Pages dont l'ordre en cache a été calculé dans l'autre sens de lecture (tome rebasculé
    # manga ↔ webtoon) : elles reprennent à la détection, les autres ne perdent rien.
    sens_a_refaire: set[int] = set()
    total = len(plan.pages)

    def _arret() -> bool:
        """Arrêt propre, commun aux TROIS fenêtres où il peut survenir (balayage CV, passe
        terminologique, balayage de traduction).

        ⚠ C'est ce corps qui manquait autrefois : un `return False` sortait AVANT
        l'assemblage, même quand les 150 pages étaient déjà sur disque — relancer un tome
        complet puis l'interrompre ne produisait donc jamais d'archive. Défaut de structure,
        pas de `build_cbz`. Depuis que l'arrêt peut tomber à trois endroits, en faire une
        fonction est la seule façon de garantir qu'aucun d'eux ne l'oublie.

        ⚠ Sauf en mode `glossaire_seul`, qui n'a rien rendu : y assembler réencoderait une
        archive de 230 Mo à partir de pages que ce run n'a pas touchées. L'acquis de ce
        mode-là est le glossaire, et `_passe_terminologie` l'a déjà sauvé sur disque."""
        if not glossaire_seul:
            assemble_outputs(build_dir, mcfg, project, volume, reporter=reporter, sens=sens)
        runtime.close_llm_clients(None, agents)
        reporter.stopped(n_done, total)
        return False

    # Planches tombées en échec, avec de quoi les reprendre. Alimenté par `_filet`.
    planches_en_echec: list[dict] = []
    #: Leurs index, pour que le balayage B ne retente pas ce que le balayage A a perdu — sans
    #: quoi une planche illisible échoue DEUX fois et se compte deux fois dans le rapport.
    pages_echouees: set[int] = set()

    @contextlib.contextmanager
    def _filet(index: int, phase: str):
        """Isole l'échec d'UNE planche : le tome continue sans elle.

        ## Le défaut que ça corrige

        Les deux balayages n'entouraient rien. Un JPEG tronqué à la planche 87 sur 150, une
        police introuvable au lettrage ou un `manga_ocr` qui lève faisaient remonter
        l'exception jusqu'à la CLI : `assemble_outputs` n'était pas appelé, aucun `RAPPORT.md`
        n'était écrit, et l'utilisateur découvrait au matin un run de six heures sans archive.
        Les checkpoints sauvaient le travail déjà payé en GPU — mais rien ne disait ce qui
        avait échoué ni où reprendre.

        ## Ce qui NE passe pas par le filet

        `StopRequested` et `KeyboardInterrupt` traversent : l'arrêt propre vise le TOME, pas
        la planche, et il doit sortir par `_arret()`, qui assemble l'archive avant de rendre
        la main. Les avaler ici rendrait `--stop` silencieusement inopérant.

        `SystemExit` traverse aussi, et c'est délibéré : c'est ce que lèvent un modèle ONNX
        absent ou une archive illisible — des pannes de RUN, pas de planche. Les avaler
        planche par planche produirait 150 échecs identiques au lieu d'un message clair.
        (C'est `run_manga.py --all` qui les rattrape, à l'échelle du chapitre.)"""
        try:
            yield
        except (control.StopRequested, KeyboardInterrupt):
            raise
        except Exception as err:
            planches_en_echec.append({"page": index, "phase": phase,
                                      "type": type(err).__name__, "message": str(err)})
            pages_echouees.add(index)
            reporter.warn(f"[{phase}] page {index}/{total} : ÉCHEC "
                          f"({type(err).__name__} : {err}) — planche ignorée, le tome "
                          f"continue. Reprendre avec « --page {index} ».")

    # ═══ Balayage A — détection, nettoyage, OCR. AUCUN appel LLM ici. ════════════════════
    #
    # Le traitement se fait en DEUX balayages depuis le lot 4.1, et non plus en un seul où
    # les six étapes s'enchaînaient planche par planche. La raison est terminologique : le
    # relevé de la planche 42 n'existait qu'après la traduction de la planche 41, si bien que
    # la planche 1 était traduite avec un glossaire VIDE et que le contexte du traducteur
    # changeait à chaque planche. Deux planches n'étaient donc jamais traduites avec la même
    # terminologie — le défaut mesuré au lot 3 (Mikage / Mitsukage / Miyage pour un même
    # kanji), que le forçage ne fait que rattraper après coup.
    #
    # `travail` retient, par planche à traiter, les étapes à refaire : le balayage B les
    # relit au lieu de redemander `stages_to_redo`, dont la réponse aurait changé entre-temps
    # (le balayage A vient d'écrire les caches dont elle dépend).
    travail: dict[int, set[str]] = {}
    #: Combien de planches ce balayage a réellement ouvertes. Sert à une seule chose : dire
    #: que la PREMIÈRE porte le chargement du modèle ONNX de détection, et donc qu'aucun
    #: débit tiré d'elle n'est une estimation (cf. `gui/avancement.py:MINIMUM`).
    planches_analysees = 0
    for i, page_path in enumerate(plan.pages, 1):
        if cibles is not None and i not in cibles:
            continue
        if control.should_stop(build_dir):
            return _arret()

        with _filet(i, "analyse"):
            out_path = checkpoints.final_page_path(build_dir, i)
            clean_path = checkpoints.clean_page_path(build_dir, i)
            ckpt_dir = checkpoints.page_checkpoint_dir(build_dir, i)

            # Migration du cache AVANT toute décision de reprise. L'ordre de lecture a changé
            # (coupe X-Y), donc le format de `regions.json` — et `ocr.json`/`traduction.json`
            # s'alignent par POSITION sur cet ordre. Réordonner les textes déjà calculés évite
            # de re-détecter, re-OCRiser et re-traduire tout le tome (des heures de GPU, et le
            # modèle ONNX à nouveau requis) pour un contenu qu'on possède déjà.
            migre = checkpoints.migrate_page(
                ckpt_dir, lambda regions: ocr_mod.reading_order(regions, sens), _scinder)
            if migre:
                n_migrees += 1
                if verbose:
                    reporter.verbose(f"[cache] page {i}/{total} migré : {migre}")

            # Changement de SENS DE LECTURE (tome rebasculé manga ↔ webtoon). L'ordre en cache
            # est alors faux, et comme `ocr.json`/`traduction.json` s'y alignent par position,
            # garder ces textes mélangerait les répliques sans le moindre signal. On force donc
            # la re-détection de CETTE page — et d'elle seule : les tomes dont le sens n'a pas
            # bougé ne perdent rien.
            if checkpoints.sens_perime(ckpt_dir, sens):
                reporter.warn(
                    f"[cache] page {i} : ordre de lecture calculé en "
                    f"« {checkpoints.sens_enregistre(ckpt_dir)} », le format demande "
                    f"« {sens} » — la planche est reprise à la détection.")
                checkpoints.invalider_textes(ckpt_dir)
                sens_a_refaire.add(i)

            # Étapes réellement à refaire, d'après le GRAPHE de dépendances (et non l'ordre
            # d'exécution) : `nettoyage` et `ocr` sont des frères, si bien que `--from nettoyage`
            # ne réinvalide plus l'OCR ni la traduction — ~38 min et tous les appels LLM
            # économisés sur une relance de tome. Cf. `checkpoints._DEPENDANTS`.
            a_refaire = checkpoints.stages_to_redo(ckpt_dir, clean_path, force=force,
                                                   restart_from=restart_from)
            if i in sens_a_refaire:
                a_refaire = a_refaire | checkpoints.downstream("detection")
            # `sfx` est délibérément hors du graphe d'invalidation (cf. `CACHE_NON_BLOQUANT`) :
            # son absence ne doit périmer AUCUN étage payé en GPU sur les deux tomes déjà
            # traduits. C'est donc ici, et seulement ici, qu'on décide de le lancer — quand la
            # passe est active et que la planche n'a pas encore son `sfx.json`.
            if sfx_actif and checkpoints.load_sfx(ckpt_dir) is None:
                a_refaire = a_refaire | {"sfx"}
            elif not sfx_actif:
                a_refaire = a_refaire - {"sfx"}

            # « Déjà entièrement générée » se juge sur le CACHE, pas seulement sur l'existence de
            # la page finale. `stages_to_redo` contient toujours `rendu` ; s'il ne contient QUE
            # `rendu`, rien ne manque en amont. Tester `out_path.exists()` seul laissait passer
            # deux cas : un cache amont supprimé à la main, et — depuis le lot 4.2 — une page dont
            # la migration v2→v3 vient d'invalider l'OCR parce qu'elle a gagné des bulles. Elle
            # aurait été sautée juste après avoir été invalidée.
            # ⚠ Une planche dont le `sfx.json` est plus récent que son rendu doit être RELETTRÉE :
            # sans ça, la toute première activation de la passe détecte et traduit les zones hors
            # bulle… puis saute le rendu, parce que `a_refaire` est retombé à `{"rendu"}` et que
            # la page finale existe déjà. Les gloses n'auraient jamais été dessinées.
            glose_en_retard = sfx_actif and _sfx_non_rendu(ckpt_dir)
            if glossaire_seul:
                # Le glossaire ne se nourrit que de deux étages : les bulles (detection) et le
                # japonais qu'elles portent (ocr). Le nettoyage est retiré ICI et pas ailleurs —
                # c'est la seule ligne qui garantit qu'un `--extract-glossary` n'écrit rien dans
                # `pages_clean/`, donc qu'il ne périme aucun rendu.
                a_refaire = a_refaire & {"detection", "ocr"}
                # Et le critère de saut change avec lui : « la page finale existe » ne dit rien
                # de ce qui nous intéresse. Une planche déjà rendue peut n'avoir jamais été
                # relevée, et c'est précisément le cas que cette commande vient traiter.
                if not a_refaire:
                    continue        # bulles et japonais déjà en cache : rien de visuel à payer
            elif (out_path.exists() and not force and restart_from is None
                    and a_refaire <= {"rendu"} and not glose_en_retard):
                n_done += 1
                continue
            travail[i] = a_refaire

            etapes_cv = [s for s in ("detection", "nettoyage", "ocr", "sfx") if s in a_refaire]
            if not etapes_cv:
                continue        # rien de visuel à refaire : le balayage B fera le reste
            planches_analysees += 1
            # ⚠ La première planche traversée paie le chargement du modèle ONNX, et lui seul
            # coûte des dizaines de secondes. On l'ANNONCE plutôt que d'amortir ce coût sur
            # une estimation : `PLAN-32` L32.6 (3) — « ne réglez pas ça par une constante
            # d'amorçage ; annoncez la phase ».
            reporter.phase("chargement" if planches_analysees == 1 else "analyse")
            reporter.stage(f"Page {i}/{total} — {page_path.name} ({', '.join(etapes_cv)})")
            reporter.progres(i, total, page_path.name)
            image = Image.open(page_path).convert("RGB")

            if "detection" in a_refaire:
                t0 = time.perf_counter()
                # Relevé en DIFFÉRENTIEL : le pic du processus est monotone, et l'attribuer en
                # bloc à la détection ferait porter à la première planche la mémoire de tout
                # ce qui l'a précédée. Cf. `core/memoire.py`.
                pic_det = memoire.Pic(avant=memoire.pic())
                # Scission AVANT l'ordre de lecture : celui-ci doit voir les vraies bulles, et
                # chaque ballon doit recevoir son propre texte à l'OCR. Cf. `manga/bubbles_split.py`.
                # ⚠ Masques rendus DISJOINTS avant d'écrire quoi que ce soit — cf.
                # `_fabriquer_regions`. `masks.png` est une image d'étiquettes : un pixel
                # partagé y est attribué à la dernière bulle écrite, et le masque de l'autre
                # revient amputé au rechargement, en silence et définitivement. Mesuré sur la
                # planche 3 du Chap.11 : deux bulles se recouvraient sur 36 108 px.
                #
                # `rejets` compte, PAR MOTIF, les détections que le post-traitement a écartées
                # (cf. `detection.MOTIFS_REJET`). Un filtre muet est la façon dont on perd les
                # treize planches suivantes : le seul filtre qui existait — « moins de 2 px de
                # côté » — n'a jamais dit à personne combien il en mangeait, ni lesquelles.
                rejets: dict[str, int] = {}
                # `sautees` compte les FENÊTRES auxquelles on n'a pas payé d'inférence (lot 14,
                # L6.5). Compteur distinct de `rejets` et pas une entrée de plus dedans : une
                # détection écartée après examen et une portion de planche jamais regardée ne
                # se lisent pas de la même façon. La porte est désarmée par défaut.
                sautees: dict[str, int] = {}
                brutes = get_detector().detect(image, conf_threshold=conf_threshold,
                                               iou_threshold=iou_threshold, rejets=rejets,
                                               sautees=sautees)
                # Pleine résolution : la sonde interroge un trait de 4 à 6 px, un
                # sous-échantillonnage l'effacerait. `None` quand la sonde est désarmée, ce qui
                # est le défaut livré — on ne paie alors pas la conversion.
                gris = detection._luminance(image, 1) if encre_active else None
                regions, diag, chevauchements, perdues = _fabriquer_regions(
                    brutes, sens, gris)
                provenance = None
                escalade = None

                # ── Escalade : la planche contredit-elle ses voisines ? (lot 12, L4.2) ──
                # Pas quand l'utilisateur pilote lui-même les seuils : `--conf`/`--iou` est une
                # décision explicite sur UNE planche, et y superposer une seconde inférence
                # automatique rendrait le résultat de la commande imprévisible.
                motif_suspect = "" if seuils_ponctuels else _suspecte(regions, image)
                if motif_suspect:
                    t_esc = time.perf_counter()
                    esc_conf, esc_size = (float(esc_cfg["conf_threshold"]),
                                          int(esc_cfg["input_size"]))
                    reporter.info(
                        f"[detection] page {i} — {len(regions)} bulle(s), "
                        f"{detection_retry.MOTIFS_ESCALADE.get(motif_suspect, motif_suspect)} : "
                        f"seconde inférence à input_size {esc_size} · conf {esc_conf:.2f}")
                    candidates, diag_e, chev_e, perdues_e = _fabriquer_regions(
                        get_detector().detect(image, conf_threshold=esc_conf,
                                              iou_threshold=iou_threshold,
                                              input_size=esc_size, rejets=rejets,
                                              sautees=sautees), sens, gris)
                    # L'arbitre tranche — il est écrit pour ça depuis le lot 4.2, et la
                    # référence est ici la détection NOMINALE de cette planche (souvent vide),
                    # pas le cache. Le doute profite toujours à ce qui est en place.
                    verdict = detection_retry.arbitrer(
                        regions, candidates,
                        _uniformites(image, candidates, mcfg.get("nettoyage")),
                        seuil_abandon=seuil_abandon_tome,
                        uniformites_reference=_uniformites(image, regions,
                                                           mcfg.get("nettoyage")))
                    escalade = {"motif": motif_suspect, "input_size": esc_size,
                                "conf_threshold": esc_conf, "accepte": bool(verdict.accepte),
                                "verdict": str(verdict), "avant": len(regions),
                                "apres": len(regions),
                                "duree_s": round(time.perf_counter() - t_esc, 2)}
                    if verdict.accepte:
                        # ⚠ `retenir` et non `candidates` : sur une planche à référence vide,
                        # l'arbitre SÉLECTIONNE (une bulle nettoyable est une bulle, une bulle
                        # qu'on ne sait pas peindre est du décor). Un sous-ensemble de masques
                        # déjà disjoints reste disjoint, et l'ordre de lecture d'un
                        # sous-ensemble reste l'ordre de lecture — rien à refabriquer.
                        regions = verdict.retenir(candidates)
                        diag, chevauchements, perdues = diag_e, chev_e, perdues_e
                        escalade["apres"] = len(regions)
                    # La trace est écrite dans les DEUX cas, et c'est le point : une escalade
                    # qui ne donne rien est une information sur la planche — elle dit qu'on a
                    # cherché et qu'il n'y avait rien —, pas un non-événement.
                    reporter.info(f"[detection] page {i} — escalade : {verdict}")
                # Alimente la médiane courante du tome APRÈS l'escalade : c'est le nombre de
                # bulles réellement retenu qui décrit la planche.
                comptes_du_tome.append(len(regions))
                if seuils_ponctuels:
                    # Relance CIBLÉE : l'arbitre décide, et le doute profite à la détection en
                    # place — elle a déjà été payée en OCR et en traduction.
                    reference = checkpoints.load_regions(ckpt_dir) or []
                    verdict = detection_retry.arbitrer(
                        reference, regions,
                        _uniformites(image, regions, mcfg.get("nettoyage")),
                        seuil_abandon=seuil_abandon_tome,
                        uniformites_reference=_uniformites(image, reference,
                                                           mcfg.get("nettoyage")))
                    reporter.info(f"[detection] page {i} — arbitre : {verdict}")
                    # ⚠ La condition était `if reference and not verdict.accepte`, et le
                    # premier terme la désarmait entièrement sur la planche à zéro bulle — donc
                    # sur exactement le cas où l'on vient d'abaisser les seuils. La trace
                    # affichait « REFUSÉ » juste avant que `save_regions` écrive quand même.
                    # Le régime est désormais explicite des deux côtés : à référence vide,
                    # l'arbitre SÉLECTIONNE les candidates nettoyables au lieu de trancher en
                    # bloc, et son refus est aussi contraignant qu'ailleurs.
                    if not verdict.accepte:
                        reporter.warn(f"[detection] page {i} : seuils NON appliqués "
                                      f"({detection_retry.LIBELLES.get(verdict.motif, '?')}). "
                                      f"Le cache est intact ; `tools/apercu_detection.py "
                                      f"--balayage` montre ce qui marcherait.")
                        travail.pop(i, None)
                        continue
                    regions = verdict.retenir(regions)
                    provenance = {"conf_threshold": conf_threshold,
                                  "iou_threshold": iou_threshold,
                                  "motif": verdict.detail or "relance ciblée"}
                    if len(regions) != len(reference):
                        # ⚠ `stage_cache_present` teste la PRÉSENCE d'un fichier, pas sa longueur :
                        # sans cela, la page garderait un OCR de l'ancien découpage, décalé.
                        supprimes = checkpoints.invalider_textes(ckpt_dir)
                        if supprimes:
                            reporter.info(f"[detection] page {i} : {len(reference)} → "
                                          f"{len(regions)} bulle(s) — "
                                          + ", ".join(supprimes) + " invalidé(s)")
                        a_refaire = a_refaire | checkpoints.downstream("detection")
                        travail[i] = a_refaire
                # ── Ce que la détection a écarté, et pourquoi : persisté avec les régions
                #
                # ⚠ Dans `regions.json` et non dans `qa.json`. Les deux fichiers ne décrivent
                # pas la même chose : `qa.json` décrit le RENDU d'une planche, `regions.json`
                # décrit sa DÉTECTION. Un rejet de post-traitement, une escalade, une bulle
                # rognée par sa voisine sont des faits de détection — ils doivent survivre à un
                # `--from rendu`, et ils doivent exister sur les 423 planches du corpus qui
                # n'ont pas de `qa.json` du tout.
                #
                # ⚠ Et **pas** de `FORMAT_VERSION` incrémenté : `load_regions` rend `None` sur
                # écart de version, ce qui déclencherait `downstream("detection")`, soit la
                # retraduction de tous les tomes existants. La version encode le contrat de
                # nombre et d'ordre des régions ; un champ de provenance n'y touche pas, et un
                # lecteur ancien l'ignore simplement.
                provenance = dict(provenance or {})
                if rejets:
                    provenance["rejets"] = dict(sorted(rejets.items()))
                if sautees:
                    provenance["fenetres_sautees"] = dict(sorted(sautees.items()))
                if escalade:
                    provenance["escalade"] = escalade
                if chevauchements:
                    # ⚠ La liste ENTIÈRE, non tronquée. La troncature à six entrées reste sur
                    # le `warn` ci-dessous — une ligne de log doit rester lisible — mais le
                    # rapport, lui, décrit le tome : y perdre la septième bulle rognée serait
                    # reproduire exactement le défaut que ce lot corrige.
                    provenance["chevauchements"] = chevauchements
                if perdues:
                    provenance["absorbees"] = int(perdues)
                # ── Ce que `max_lobes` a écarté (lot 13, L5.4) ───────────────────────────
                # Ce n'est pas un rejet mais une TRONCATURE des germes : une grappe de cinq
                # ballons est ramenée à quatre, et les pixels du cinquième repartent au lobe le
                # plus proche (`geometry._lobe_le_plus_proche`). Jusqu'ici, silencieusement —
                # ni log, ni rapport, ni diagnostic. Persisté avec les régions et non dans
                # `qa.json`, comme les rejets et les chevauchements : c'est un fait de
                # DÉTECTION, il doit survivre à un `--from rendu`.
                troncatures = [
                    {"bbox": list(d["bbox"]), "germes": int(d["germes_tronques"]),
                     "lobes": int(d.get("lobes", 0))}
                    for d in diag if d.get("germes_tronques")]
                if troncatures:
                    provenance["germes_tronques"] = troncatures
                # ── Ce que la SONDE D'ENCRE a vu (lot 13, L5.5) ──────────────────────────
                # Vide tant que `scission.encre.actif` est faux, donc vide dans la
                # configuration livrée. C'est ce qui rend l'évaluation observable : sans ces
                # deux lignes, activer la sonde ne se verrait nulle part, et son critère
                # d'abandon serait invérifiable.
                traits = [{"bbox": list(d["bbox"]), "remplissage": d["remplissage"]}
                          for d in diag if d.get("trait_sans_goulot")]
                if traits:
                    provenance["trait_sans_goulot"] = traits
                par_encre = [{"bbox": list(d["bbox"]), "encre": d.get("encre"),
                              "lobes": int(d.get("lobes", 0))}
                             for d in diag if d.get("motif") == "scindee_par_encre"]
                if par_encre:
                    provenance["scindees_par_encre"] = par_encre
                # ── Le garde-fou de non-régression de L5.3, à sa VRAIE place ─────────────
                # Le critère du lot demande qu'aucun lobe à remplissage < 0,20 ne sorte sur le
                # webtoon, et le run livré en produit deux (0,01 et 0,14 sur webtoon A
                # Chap.11 page 1). ⚠ Ils ne viennent PAS de la scission : le garde-fou de forme
                # exige 0,72 par lobe et ne peut pas émettre 0,01. Ils viennent de
                # `rendre_disjoints`, en AVAL — le détecteur avait émis à la fois une région
                # fusionnée (scindée en deux lobes) et les deux ballons séparément ; les pixels
                # partagés sont allés aux mieux notés, laissant les lobes à 1 536 et 25 829 px.
                #
                # Un seuil de scission plus serré n'y aurait donc rien changé, et c'est
                # exactement pour cela que la mesure se fait ICI, sur les régions telles
                # qu'elles seront écrites, et non sur ce que la scission a proposé.
                plancher_lobe = float(scission_cfg.get("remplissage_lobe_plancher", 0.20))
                lobes_creux = [
                    {"bbox": list(r.bbox), "remplissage": round(geometry.remplissage(r.mask), 3),
                     "aire": int(r.mask.sum())}
                    for r in regions
                    if getattr(r, "scindee", False) and r.mask is not None and r.mask.any()
                    and geometry.remplissage(r.mask) < plancher_lobe]
                if lobes_creux:
                    provenance["lobes_creux"] = lobes_creux
                checkpoints.save_regions(ckpt_dir, regions, image.size,
                                         detection=provenance or None, sens=sens)
                # Les diagnostics ne sont pas accumulés pour le rapport : celui-ci les relit dans
                # les caches de TOUTES les planches, et décrit donc le tome et non le run.
                if chevauchements or perdues:
                    detail = ", ".join(f"{c['perdus']} px" for c in chevauchements[:6])
                    reporter.warn(
                        f"[detection] page {i} : {len(chevauchements)} bulle(s) rognée(s) par "
                        f"une voisine ({detail}"
                        + (f", … {len(chevauchements) - 6} de plus"
                           if len(chevauchements) > 6 else "") + ")"
                        + (f" · {perdues} entièrement recouverte(s), écartée(s)"
                           if perdues else "")
                        + " — masques rendus disjoints ; le détail complet est dans "
                          "RAPPORT.md")
                for d in diag:
                    if d["type"] == "scindee":
                        reporter.warn(
                            f"[detection] page {i} : région bi-lobée scindée en {d['lobes']} "
                            f"(remplissage du masque {d['remplissage']:.2f} → "
                            + ", ".join(f"{x:.2f}" for x in d["remplissages_lobes"]) + ")"
                            + (" · confirmée par le TRAIT de contour"
                               if d.get("motif") == "scindee_par_encre" else ""))
                if troncatures:
                    reporter.warn(
                        f"[detection] page {i} : {sum(t['germes'] for t in troncatures)} "
                        f"germe(s) de lobe écarté(s) par `scission.max_lobes` sur "
                        f"{len(troncatures)} région(s) — les pixels concernés sont repartis au "
                        f"lobe le plus proche ; le détail est dans RAPPORT.md")
                pic_det.apres = memoire.pic()
                pic_tome = max(pic_tome or 0, pic_det.apres or 0) or None
                if verbose:
                    reporter.verbose(f"[detection] page {i}/{total} : {time.perf_counter() - t0:.2f}s "
                                     f"· {len(regions)} bulle(s)"
                                     + (f" (dont {len(brutes)} détectée(s), "
                                        f"{len(regions) - len(brutes)} par scission)"
                                        if len(regions) != len(brutes) else "")
                                     + (" · rejets : " + ", ".join(
                                         f"{detection.MOTIFS_REJET.get(m, m)} ×{n}"
                                         for m, n in sorted(rejets.items())) if rejets else "")
                                     + (" · " + ", ".join(
                                         f"{detection.MOTIFS_SAUT.get(m, m)} ×{n}"
                                         for m, n in sorted(sautees.items())) if sautees else "")
                                     + f" · {pic_det}")
            else:
                regions = checkpoints.load_regions(ckpt_dir)

            # Styles analysés sur l'image D'ORIGINE, à chaque étape de reprise — jamais sur la
            # page nettoyée. Sur une page déjà nettoyée la bulle est uniforme : le masque de
            # texte provisoire ressort vide, `inverted` devient indéductible, et un `--from
            # rendu` relettrerait la bulle inversée de page_0044 en noir sur noir. L'image
            # d'origine est de toute façon déjà ouverte ci-dessus, et l'analyse est en numpy
            # pur (~1 ms/bulle) : la refaire coûte moins que de la mettre en cache.
            styles = clean.analyze_regions(image, regions, mcfg.get("nettoyage"))

            if "nettoyage" in a_refaire:
                t0 = time.perf_counter()
                cleaned = clean.clean_bubbles(image, regions, mcfg.get("nettoyage"), styles=styles)
                cleaned.save(clean_path)
                if verbose:
                    modes = [s.mode for s in styles if s.ok]
                    replis = sum(1 for s in styles if s.ok and s.erode_radius == 0)
                    reporter.verbose(
                        f"[nettoyage] page {i}/{total} : {time.perf_counter() - t0:.2f}s · "
                        f"{modes.count('masque')} masque / {modes.count('texte')} texte"
                        + (f" / {modes.count('aucun')} abandon" if modes.count("aucun") else "")
                        + (f" · {replis} repli(s) d'érosion" if replis else ""))
                    # Un abandon est un incident : la bulle garde son texte japonais. `warn` va
                    # aussi dans perf.log, pour qu'il reste trouvable après un run de nuit.
                    for j, s in enumerate(styles, 1):
                        if s.ok and s.mode == "aucun":
                            reporter.warn(f"[nettoyage] page {i} bulle {j} : non nettoyée "
                                          f"(uniformité {s.uniformity:.2f} < seuil d'abandon — "
                                          f"probable fausse détection sur du dessin)")

            if "ocr" in a_refaire:
                t0 = time.perf_counter()
                # `styles` fournit la couleur de fond mesurée de chaque bulle : `masked_crop`
                # isole la bulle sur une toile de CETTE couleur (du blanc autour d'un texte
                # clair détruirait l'OCR d'une bulle inversée).
                texts_jp = get_reader().read_all(image, regions, styles=styles,
                                                 cfg=mcfg.get("ocr"))
                checkpoints.save_ocr(ckpt_dir, texts_jp)
                if verbose:
                    reporter.verbose(f"[ocr] page {i}/{total} : {time.perf_counter() - t0:.2f}s "
                                     f"· {len(texts_jp)} bulle(s) lues")

            # Texte SUR LE DESSIN. Ici et pas au balayage B : cette passe a besoin des deux
            # modèles de vision, qui sont relâchés à la fin de ce balayage (`_lazy.clear()`).
            # Seule la TRADUCTION des zones trouvées appartient au balayage B.
            if "sfx" in a_refaire:
                t0 = time.perf_counter()
                # ⚠ C'est ici que la mémoire d'un run se joue, plus encore qu'à la détection :
                # `composantes` alloue un masque booléen PLEINE PAGE par composante connexe, et
                # rien ne borne leur nombre (cf. `text_detection.MIN_COMPOSANTE`). Sur une
                # bande, chacun pèse 10,8 Mo. Sans ce relevé, la passe la plus coûteuse du
                # pipeline était aussi la seule dont personne ne connaissait le prix.
                pic_sfx = memoire.Pic(avant=memoire.pic())
                # ⚠ `fenetrage=sfx_cfg` (lot 14, L6.1) : sans lui, la bande ENTIÈRE partait
                # dans un carré de 1024 — 110 colonnes sur 1 024 pour une bande de 10 000 px,
                # exactement le défaut que le lot webtoon avait corrigé côté bulles et laissé
                # ici. La passe y trouve des taches, pas du texte : 6,65 % de la planche
                # marquée, 24 composantes. Sur une planche paginée, `fenetres()` rend `[]` et
                # l'appel est celui d'avant, au bit près.
                masque = get_text_detector().masque_texte(
                    image, seuil=float(sfx_cfg.get("seuil_masque", text_detection.SEUIL_MASQUE)),
                    fenetrage=sfx_cfg, dire=reporter.info)
                # `sens` et non un tri codé en dur (lot 13, L5.7) : c'était le SEUL endroit
                # du pipeline à ignorer le sens de lecture du format. Sur un webtoon, les
                # bulles étaient ordonnées correctement et les onomatopées numérotées à
                # l'envers — le rapport comme le prompt de `_translate_sfx` les présentaient
                # dans un ordre qui ne correspondait à rien.
                diag_sfx: dict = {}
                zones = text_detection.hors_des_bulles(
                    masque, regions,
                    containment=float(sfx_cfg.get("containment_bulle",
                                                  text_detection.CONTAINMENT_BULLE)),
                    aire_min=int(sfx_cfg.get("aire_min", text_detection.AIRE_MIN)),
                    groupement=int(sfx_cfg.get("groupement", 0)),
                    min_composante=int(sfx_cfg.get("min_composante",
                                                   text_detection.MIN_COMPOSANTE)),
                    # Bornes HAUTES du lot 21, désarmées par défaut (`0.0`). Tout rejet est
                    # compté par motif : un filtre muet est la façon dont on perd les zones
                    # suivantes sans le voir.
                    aire_max_frac=sfx_aire_max, remplissage_max=sfx_remplissage_max,
                    sens=sens, diagnostic=diag_sfx)
                for motif, n in (diag_sfx.get("rejets") or {}).items():
                    stats_sfx["rejets"][motif] = stats_sfx["rejets"].get(motif, 0) + n
                # ⚠ Un masque de bulle de forme inattendue était écarté SANS UN MOT (L5.8), et
                # la cascade est brutale : l'union sort vide, et toutes les répliques déjà
                # prises en charge par une bulle sont re-détectées comme texte hors bulle,
                # relues, retraduites en glose et listées au rapport.
                if diag_sfx.get("masques_ecartes"):
                    stats_sfx["masques_ecartes"] = (
                        stats_sfx.get("masques_ecartes", 0)
                        + int(diag_sfx["masques_ecartes"]))
                    reporter.warn(
                        f"[sfx] page {i} : {diag_sfx['masques_ecartes']} masque(s) de bulle "
                        f"de forme inattendue ({', '.join(diag_sfx['formes'])}) — écarté(s) "
                        f"de l'appariement. Les répliques de ces bulles risquent d'être "
                        f"re-détectées comme texte hors bulle. Cache probablement écrit avant "
                        f"un changement de découpage : relancer `--from detection`.")
                # ⚠ L21.2 — le STYLE de chaque zone est mesuré ICI, sur l'image d'ORIGINE,
                # et persisté. Il ne pourra plus l'être après : `BubbleStyle` prévient déjà
                # que « ces informations ne peuvent pas être redécouvertes après le
                # nettoyage », et c'est encore plus vrai d'un effacement (`PLAN-22`) — le
                # fond local qu'il faudra reconstruire, c'est celui d'avant.
                # Coût mesuré : ~0,16 s par planche porteuse, contre 1,5 s (GPU) à 110 s
                # (CPU) pour l'inférence ONNX qui la précède. Négligeable, et dit.
                styles_sfx = [
                    {"fond": list(s.fond), "fond_luma": round(s.fond_luma, 1),
                     "uniformite_fond": round(s.uniformite_fond, 4),
                     "encre": list(s.encre), "inverted": s.inverted,
                     "remplissage": round(s.remplissage, 4),
                     "aire_frac": round(s.aire_frac, 5),
                     "orientation": s.orientation, "ok": s.ok}
                    for s in clean.analyser_zones_hors_bulle(
                        image, zones, mcfg.get("nettoyage"))]
                # DÉTECTION SEULE. La lecture attend le filtre de mobilier, qui a besoin des
                # boîtes de TOUT le tome pour décider — 20,5 % des zones du Vol.1 du *manga A*
                # sont des filigranes de scan (92 sur 448, mesure du lot 21 ; le dépôt
                # annonçait 63 %, cf. `text_detection.MOBILIER_FRAC_PLANCHES`), autant d'OCR
                # et d'appels LLM à ne pas payer.
                checkpoints.save_sfx(ckpt_dir, zones, [], image.size,
                                     styles=styles_sfx, lu=False)
                pic_sfx.apres = memoire.pic()
                pic_tome = max(pic_tome or 0, pic_sfx.apres or 0) or None
                if verbose:
                    reporter.verbose(f"[sfx] page {i}/{total} : {time.perf_counter() - t0:.2f}s "
                                     f"· {len(zones)} zone(s) détectée(s) · {pic_sfx}")

    if n_migrees and not verbose:
        reporter.info(f"{n_migrees} page(s) de cache migrée(s) au format "
                      f"v{checkpoints.FORMAT_VERSION} (réordonnées, rien recalculé).")

    # ═══ Filtre du MOBILIER DE PAGE, puis lecture des seules survivantes ═════════════════
    # Ici et pas dans la boucle : décider qu'une zone est un filigrane demande de voir TOUT le
    # tome. C'est aussi la dernière fenêtre où les modèles de vision sont encore chargés.
    if sfx_actif:
        pages_sfx: dict[int, tuple[list, tuple]] = {}
        charges: dict[int, dict] = {}
        for i in range(1, total + 1):
            charge = checkpoints.load_sfx_complet(
                checkpoints.page_checkpoint_dir(build_dir, i))
            if charge is None:
                continue
            charges[i] = charge
            pages_sfx[i] = ([r.bbox for r in charge["regions"]], charge["taille"])

        if pages_sfx:
            mobilier, groupes_mobilier = text_detection.mobilier_de_tome(
                pages_sfx,
                frac_planches=float(sfx_cfg.get("mobilier_frac_planches",
                                                text_detection.MOBILIER_FRAC_PLANCHES)),
                iou=float(sfx_cfg.get("mobilier_iou", text_detection.MOBILIER_IOU)),
                aire_max_frac=float(sfx_cfg.get("mobilier_aire_max_frac",
                                                text_detection.MOBILIER_AIRE_MAX_FRAC)))
            stats_sfx["mobilier"] = len(mobilier)
            stats_sfx["groupes_mobilier"] = groupes_mobilier
            if groupes_mobilier:
                reporter.info(
                    f"Mobilier de page : {len(mobilier)} zone(s) écartée(s) en "
                    f"{len(groupes_mobilier)} groupe(s) récurrent(s) — filigranes de scan, "
                    f"ni lus ni traduits")

            for i, charge in charges.items():
                ckpt_dir = checkpoints.page_checkpoint_dir(build_dir, i)
                zones = charge["regions"]
                drapeaux = [(i, k) in mobilier for k in range(len(zones))]
                textes = charge["textes"]
                if not charge["lu"]:
                    image = Image.open(plan.pages[i - 1]).convert("RGB")
                    # La toile d'OCR prend le CONTREPIED de l'encre : hors d'un ballon il n'y a
                    # pas de couleur de bulle à mesurer, et recopier le dessin autour des
                    # lettres rendrait la lecture aussi difficile que sur la planche.
                    textes = [
                        "" if drapeaux[k] else
                        get_reader().read(image, ocr_mod.region_rectangulaire(z),
                                          background=ocr_mod.fond_pour_texte(image, z),
                                          cfg=mcfg.get("ocr"))
                        for k, z in enumerate(zones)]
                # Ne réécrire que si quelque chose a bougé : le dépôt vit dans un dossier
                # synchronisé, et réécrire 150 fichiers identiques à chaque run le fait
                # travailler pour rien — en plus de faire varier les empreintes de `projet.json`.
                if not charge["lu"] or charge["mobilier"] != drapeaux:
                    # ⚠ `styles=charge["styles"]` est OBLIGATOIRE : cette seconde écriture
                    # remplace le fichier entier, et l'omettre effacerait la mesure de L21.2
                    # faite à la détection — sur l'image d'ORIGINE, la seule où elle a un
                    # sens. Un cache écrit avant ce lot rend `[]`, et rien ne se relance.
                    checkpoints.save_sfx(ckpt_dir, zones, textes,
                                         charge["taille"] or (0, 0),
                                         mobilier=drapeaux, styles=charge["styles"],
                                         lu=True)
                utiles = sum(1 for k in range(len(zones)) if not drapeaux[k])
                if utiles:
                    stats_sfx["pages"] += 1
                    stats_sfx["zones"] += utiles

    # Les modèles de vision ont fini leur travail : plus une seule étape ne les appellera.
    # Lâcher les références libère la session ONNX et le ViT+BERT de manga-ocr avant que le
    # LLM ne soit sollicité, au lieu de les garder en mémoire tout le reste du run. C'est ce
    # que le découpage en deux balayages rend possible : en une seule passe, détection et
    # traduction s'entrelaçaient jusqu'à la dernière planche.
    _lazy.clear()

    # ═══ Passe terminologique — sur TOUT le volume, avant la première traduction ══════════
    #
    # ⚠ `passes_volume=False` la saute, ainsi que le dédoublonnage du glossariste. C'est ce que
    # demande l'éditeur graphique quand il retraduit UNE planche : ces deux passes raisonnent à
    # l'échelle du tome — le relevé lit toutes les planches, le dédoublonnage réécrit tout le
    # glossaire — et les rejouer pour une bulle est du temps pur. Le glossaire déjà sur disque
    # est lu normalement ; c'est seulement son ENRICHISSEMENT qui est reporté au prochain run
    # de tome.
    #
    # ⚠ `glossaire_seul=True` la rend au contraire OBLIGATOIRE, et sans la condition
    # « une planche à traduire » : c'est la seule chose que ce mode fait.
    if agent_term is not None and (glossaire_seul or (passes_volume and any(
            "traduction" in a for a in travail.values()))):
        # Seules les planches qu'on va TRADUIRE ont le droit de consommer un appel de relevé.
        # Les autres se contentent de re-fusionner leurs notes en cache — déterministe et
        # gratuit. C'est ce qui rend `--page 3` utilisable : la planche 3 profite du glossaire
        # de tout le volume sans déclencher 149 relevés.
        #
        # Le critère est « traduction » et non « terminologie », et la nuance compte. Le cache
        # de terminologie est NON BLOQUANT (cf. `checkpoints.CACHE_NON_BLOQUANT`) : son absence
        # ne périme rien, donc `terminologie` ne figure dans `a_refaire` que si on l'a demandé.
        # Se fier à lui laissait un trou : un tome OCRisé AVANT l'activation du terminologue
        # n'était jamais relevé, et se faisait traduire avec un glossaire vide sans un mot.
        # Adosser le droit d'appel à la traduction est à la fois plus juste et sans surprise —
        # une planche qu'on traduit coûte déjà un appel LLM, une planche qu'on ne traduit pas
        # n'en coûtera aucun.
        #
        # ⚠ En mode `glossaire_seul`, ce droit s'étend à TOUTES les planches ciblées : il n'y
        # a pas de traduction à laquelle l'adosser, et c'est exactement le trou que la
        # commande vient boucher — un tome fini n'a jamais été relevé, et le demander coûtait
        # jusqu'ici de le retraduire en entier.
        if glossaire_seul:
            a_relever = set(cibles) if cibles is not None else set(range(1, total + 1))
        else:
            a_relever = {i for i, a in travail.items() if "traduction" in a}
        termine, glo_modifie = _passe_terminologie_protegee(
            agent_term, gloss, gloss_index, sans_llm=sans_llm,
            build_dir=build_dir, total=total,
            a_relever=a_relever, stats=stats_gloss, gloss_path=gloss_path,
            reporter=reporter, verbose=verbose,
            # Un relevé en cache n'est refait que si on l'a DEMANDÉ : `--force`, ou un
            # `--from` dont la terminologie dépend (`ocr`, `detection`, `terminologie`
            # elle-même). `--from rendu` ne rappelle donc rien, conformément à sa promesse.
            ignorer_cache=glossaire_seul and (
                force or (restart_from is not None
                          and "terminologie" in checkpoints.downstream(restart_from))),
            # ⚠ Le `dry` n'est posé QUE pour `glossaire_seul`, et ce n'est pas une timidité.
            # Le `--dry-run` d'un run manga normal n'a jamais voulu dire « sans effet de
            # bord » : il écrit `ocr.json`, les pages nettoyées, les pages finales, le
            # RAPPORT.md et le CBZ — seuls les appels LLM sont neutralisés. Y enrichir le
            # glossaire est donc cohérent, et `tests/test_manga_terminology.py` le vérifie.
            # Le mode `glossaire_seul`, lui, ne produit RIEN d'autre que le glossaire : un
            # dry-run qui l'écrirait quand même n'aurait plus aucun sens — il ne resterait
            # pas une seule chose à répéter en blanc.
            dry=glossaire_seul and dry_run,
            langue=langue_src, mode=plan.mode,
            arret=lambda: control.should_stop(build_dir))
        if not termine:
            return _arret()

        if stats_gloss["pages_relevees"] or stats_gloss["pages_reprises"]:
            cnt = glossary.counts(gloss)
            reporter.info(f"Glossaire ({glossary.total(gloss)}) : "
                          + (", ".join(f"{k} {v}" for k, v in cnt.items()) or "vide")
                          + f" · +{stats_gloss['ajouts']} entrée(s), "
                          f"{stats_gloss['fusions']} fusion(s)"
                          + (f", {stats_gloss['conflits']} conflit(s)"
                             if stats_gloss["conflits"] else ""))
            # Dédoublonnage AVANT la première traduction, et non plus après la dernière.
            # L'appel est le même, mais il était placé en fin de tome : il nettoyait un
            # glossaire dont les 150 planches s'étaient déjà servies, donc il ne profitait
            # qu'au run SUIVANT. Conditionné à un changement RÉEL du glossaire (cf.
            # l'empreinte dans `_passe_terminologie`) : sinon relancer un tome déjà relevé
            # rappellerait l'agent sur tout le glossaire à chaque fois, pour rien.
            #
            # ⚠ Pas en mode `glossaire_seul` : le dédoublonnage porte sur le glossaire ENTIER
            # de l'œuvre, pas sur ce chapitre. Le payer ici ferait N appels sur quinze
            # chapitres là où un seul, après le dernier, donne le même résultat — c'est donc
            # `manga.glossaire_manga` qui le lance, une fois.
            if agent_gloss is not None and not dry_run and glo_modifie and not glossaire_seul:
                from pipeline.orchestrator import optimize_glossary_file
                optimize_glossary_file(gloss_path, agents, reporter, dry=dry_run,
                                       verbose=verbose)
                # Le FICHIER a été réécrit : l'objet en mémoire et son index sont périmés.
                # Recharger `gloss` est indispensable — c'est lui que le balayage B utilise
                # pour le forçage, et il doit voir le glossaire dédoublonné. L'index, lui,
                # n'a plus d'utilisateur en aval aujourd'hui ; on le reconstruit quand même
                # parce que `glossary_build.build_index` le dit dans son docstring (il n'est
                # valide que tant que le glossaire est MUTÉ, pas quand il est REMPLACÉ), et
                # qu'un index survivant à son glossaire est un piège silencieux.
                gloss = glossary.load(gloss_path) or gloss
                gloss_index = glossary_build.build_index(gloss)
        # Un seul rendu du contexte pour tout le tome — c'est la définition d'un glossaire
        # FIXE. L'ancienne boucle rappelait `to_text` (sérialisation complète, plafonnée à
        # 4000 tokens) après chaque planche qui ajoutait quoi que ce soit.
        gloss_text = glossary.to_text(gloss, max_tokens=4000) if glossary.total(gloss) else ""

    # ═══ Sortie du mode `glossaire_seul` — avant tout ce qui écrit une planche ═══════════
    #
    # Les deux passes de dérive sont rejouées ICI plutôt que laissées au run complet, et
    # c'est le vrai gain de la commande sur un chapitre déjà traduit : elles ne coûtent aucun
    # appel LLM, elles ne demandent que l'OCR et le français déjà en cache, et elles écrivent
    # les `interdits` que le forçage attendait. Un `--from rendu` les applique ensuite aux
    # 150 planches, toujours sans LLM.
    #
    # Ce que ce `return` évite, et qui est tout l'intérêt du mode : le balayage de traduction,
    # le lettrage, `write_report` (qui écraserait le `RAPPORT.md` d'un tome fini par des
    # statistiques de traduction vides) et `assemble_outputs` (230 Mo de CBZ réencodés sur un
    # dossier synchronisé). `projet_mod.ecrire`, lui, est appelé : l'OCR a pu bouger, et sa
    # révision n'augmente que si le contenu a réellement changé.
    if glossaire_seul:
        _passe_derive_ancree(gloss, derives, build_dir=build_dir, total=total,
                             stats=stats_gloss)
        _passe_derive_volume(gloss, derives, build_dir=build_dir, total=total,
                             derive_cfg=derive_cfg, stats=stats_gloss, gloss_path=gloss_path,
                             reporter=reporter, dry_run=dry_run)
        if not stats_gloss["terminologue_actif"]:
            reporter.warn("Terminologie — agent ABSENT : décommente `manga.modeles."
                          "terminologue` dans config.yaml, sinon l'extraction n'a rien à "
                          "relever. Les dérives, elles, ont tourné (elles n'appellent "
                          "aucun LLM).")
        reporter.info(
            f"Glossaire — {stats_gloss['pages_relevees']} planche(s) relevée(s)"
            + (f", {stats_gloss['pages_reprises']} reprise(s) du cache"
               if stats_gloss["pages_reprises"] else "")
            + f" · +{stats_gloss['ajouts']} entrée(s), {stats_gloss['fusions']} fusion(s)"
            + (f", {stats_gloss['derives_bannies']} forme(s) bannie(s)"
               if stats_gloss["derives_bannies"] else "")
            + f" · {glossary.total(gloss)} entrée(s) dans {gloss_path}")
        if planches_en_echec:
            # Aucun `RAPPORT.md` n'est écrit dans ce mode : cette ligne est la SEULE trace
            # d'une planche perdue. Elle passe par `warn`, donc aussi dans perf.log.
            reporter.warn(
                f"{len(planches_en_echec)} planche(s) en ÉCHEC, non relevée(s) : "
                + ", ".join(str(e["page"]) for e in planches_en_echec[:12])
                + (f" (+{len(planches_en_echec) - 12})" if len(planches_en_echec) > 12 else ""))
        projet_mod.ecrire(build_dir, projet_mod.construire(
            build_dir, projet=project, tome=volume, pages=plan.pages, version=__version__,
            page_ckpt=checkpoints.page_checkpoint_dir))
        runtime.close_llm_clients(None, agents)
        return True

    # Fiche de contexte du tome : APRÈS la terminologie — elle profite du glossaire complet et
    # du `gloss_text` définitif — et AVANT la première traduction, comme le relevé lui-même.
    # Un seul appel pour le tome, mis en cache ; agent absent ⇒ chaîne vide, rien ne change.
    # ⚠ Conditionné à une planche RÉELLEMENT à traduire, exactement comme le droit d'appel du
    # terminologue. Sans cela, `--from rendu` — dont tout le README garantit qu'il ne coûte
    # AUCUN appel LLM — en aurait payé un pour une fiche dont personne ne se serait servi.
    contexte_oeuvre = _passe_contexte(
        agents.get("manga_contexte") if (passes_volume and any("traduction" in a
                                                                for a in travail.values()))
        else None,
        build_dir, total=total, gloss_text=gloss_text,
        budget_entree=int(contexte_cfg.get("budget_echantillon", 3000)),
        max_tokens=int(contexte_cfg.get("max_tokens", 400)), reporter=reporter,
        langue=langue_src, pack=pack)

    # ═══ Lots de traduction ══════════════════════════════════════════════════════════════
    # Constitués AVANT la boucle, sur les seules planches réellement à traduire et sans
    # franchir un trou (cf. `groupes_de_lot`). Un lot de 1 est le chemin de la 1.0.0, inchangé.
    #
    # ⚠ Les résultats d'un lot sont écrits sur disque DÈS SA RÉCEPTION, planche par planche.
    #
    # La 1.1.0 les gardait en mémoire jusqu'à ce que chaque planche atteigne son tour dans la
    # boucle, pour préserver un invariant réel : `traduction.json` en cache est, depuis
    # toujours, une traduction DÉJÀ passée par le rattrapage unitaire, et c'est sur quoi
    # compte la reprise (`stages_to_redo` teste la présence du fichier, pas son état).
    #
    # Le coût de ce choix a été mesuré sur le Vol.4 : un `--lot 20` interrompu a produit UNE
    # planche en 44 minutes, et tout le reste a été perdu. Le tome a dû être retraduit en
    # entier à `lot=1`.
    #
    # La bonne réponse n'était pas de choisir entre les deux, mais de **rattraper tout de
    # suite** : le rattrapage est un appel court par bulle vide, plafonné à 3 par planche, et
    # il n'a besoin que des bbox — que le lot transporte déjà. On rattrape donc chaque planche
    # du groupe dès la réponse reçue, puis on écrit. L'invariant tient, et l'unité de perte
    # redescend à la planche.
    a_traduire = [p for p, etapes in travail.items() if "traduction" in etapes]
    groupes = groupes_de_lot(a_traduire, taille_lot)
    groupe_de_page = {p: g for g in groupes for p in g}
    # (répliques, motif, stratégie, indices rattrapés) — le 4e terme évite de rejouer le
    # rattrapage dans la boucle : il a déjà eu lieu à la réception du lot.
    resultats_lot: dict[int, tuple[list[str], str | None, str, list[int]]] = {}
    # Taille de lot RÉELLEMENT subie par chaque planche, pour `qa.json`. Distincte de la taille
    # planifiée : une planche repliée a été traduite seule, et le rapport doit dire ce qui
    # s'est passé, pas ce qui était prévu.
    lot_effectif: dict[int, int] = {}
    if taille_lot > 1 and a_traduire:
        multiples = [g for g in groupes if len(g) > 1]
        reporter.info(f"[traduction] {len(a_traduire)} planche(s) à traduire en "
                      f"{len(groupes)} appel(s) — lots de {taille_lot} au plus "
                      f"({len(multiples)} lot(s) groupé(s))")

    # Structures de planche relevées au fil du balayage B, pour le rapport de tome (taux
    # d'« indéterminé » du classifieur) et pour le banc.
    structures_tome: dict[int, planche_mod.Structure] = {}
    # Registre de deuxième personne par planche (L7.10). Lexical, sans appel LLM.
    registre_par_planche: dict[int, dict[str, int]] = {}
    # Relecture à mandat étroit (L7.9) — livrée DÉSACTIVÉE, comme le `correcteur` du light
    # novel qui est à `null`. `agents.get` rend `None` quand `manga_relecteur` n'est pas dans
    # `manga.modeles`, et `relecture.relire` ne fait alors aucun appel : seule la règle
    # « glossaire », déterministe, continue de compter.
    agent_relecteur = agents.get(relecture.AGENT)
    stats_relecture: dict = {"actif": agent_relecteur is not None}

    def _structure_de(ck, regions_p, taille, page: int = 0) -> "planche_mod.Structure | None":
        """Groupes, types et locuteurs d'une planche — calculés une fois, mis en cache.

        Le cache est `structure.json`, à côté de `ocr.json`, pour deux raisons distinctes :

        · **le coût** — le calcul lit les masques pleine page (~14 ms par bulle, mesuré), et
          une planche traduite en lot est touchée deux fois (une fois comme membre, une fois
          à son tour de boucle) ;
        · **la mesure** — `tools/banc.py` doit pouvoir publier la distribution des types sans
          rouvrir un seul `masks.png`, comme il le fait pour tout le reste.

        ⚠ La longueur est vérifiée contre `regions` avant réutilisation. Un `structure.json`
        écrit avant une scission décrirait un autre découpage ; `invalider_textes` l'efface
        déjà dans ce cas, mais un cache à demi migré ne doit pas décaler un type d'un rang —
        une structure fausse est pire qu'une structure absente, c'est toute la règle du lot."""
        n = len(regions_p or [])
        if not structure_active or n == 0:
            return None
        charge = checkpoints.load_structure(ck)
        s = planche_mod.Structure.depuis_json(charge) if charge else None
        if s is None or len(s) != n:
            s = planche_mod.analyser(regions_p, taille, sens=sens, cfg=structure_cfg)
            checkpoints.save_structure(ck, s.en_json())
        if page:
            structures_tome[page] = s
        return s

    def _traduire_planche_seule(p: int) -> tuple[list[str], str | None, str]:
        """Chemin nominal de la 1.0.0 pour UNE planche — et repli d'un lot.

        Relit l'image et recalcule les styles au lieu de les recevoir : le repli est rare, et
        les porter jusqu'ici obligerait à garder en mémoire les masques pleine page de toutes
        les planches du lot (cf. `_bbox_des_styles`)."""
        lot_effectif[p] = 1
        ck = checkpoints.page_checkpoint_dir(build_dir, p)
        img = Image.open(plan.pages[p - 1]).convert("RGB")
        regs = checkpoints.load_regions(ck)
        st = clean.analyze_regions(img, regs, mcfg.get("nettoyage"))
        return _translate_page(
            agents["manga_traducteur"], img, checkpoints.load_ocr(ck) or [],
            mode_vision=mode_vision, gloss_text=gloss_text, styles=st,
            precedentes=_contexte_precedent(build_dir, p, contexte_planches,
                                            contexte_repliques, gloss, accord, pack=pack),
            contexte_oeuvre=contexte_oeuvre, stats=stats_trad,
            langue=langue_src, sens=sens, pack=pack, ratio_court=ratio_court,
            structure=_structure_de(ck, regs, img.size, p), regions=regs,
            mode_traduction=mode_traduction, reporter=reporter, page=p,
            max_retries=int(llm_cfg_manga.get("max_retries", 1)))

    # ═══ Balayage B — traduction, forçage, lettrage, rendu ═══════════════════════════════
    reporter.phase("traduction")
    for i, page_path in enumerate(plan.pages, 1):
        a_refaire = travail.get(i)
        if a_refaire is None:
            continue
        # Une planche perdue au balayage A n'a ni régions, ni page nettoyée, ni OCR : la
        # retenter ici la ferait échouer une seconde fois, sur une cause DÉRIVÉE de la
        # première. Elle serait alors comptée deux fois dans le rapport, et la vraie cause
        # noyée sous celle qu'elle a provoquée.
        if i in pages_echouees:
            continue
        if control.should_stop(build_dir):
            return _arret()

        with _filet(i, "rendu"):
            out_path = checkpoints.final_page_path(build_dir, i)
            clean_path = checkpoints.clean_page_path(build_dir, i)
            ckpt_dir = checkpoints.page_checkpoint_dir(build_dir, i)
            reporter.stage(f"Page {i}/{total} — {page_path.name} "
                           f"({', '.join(s for s in ('traduction', 'rendu') if s in a_refaire)})")
            reporter.progres(i, total, page_path.name)

            # Régions, styles et page nettoyée sont relus plutôt que transmis par le balayage A :
            # les garder en mémoire signifierait détenir 150 masques pleine page et 150 images.
            # Les styles étaient DÉJÀ recalculés à chaque reprise, et pour une raison qui vaut
            # aussi ici : sur une page nettoyée la bulle est uniforme, `inverted` devient
            # indéductible, et un relettrage écrirait la bulle inversée de page_0044 en noir sur
            # noir. L'analyse est en numpy pur (~1 ms/bulle).
            image = Image.open(page_path).convert("RGB")
            regions = checkpoints.load_regions(ckpt_dir)
            styles = clean.analyze_regions(image, regions, mcfg.get("nettoyage"))
            cleaned = Image.open(clean_path).convert("RGB")
            texts_jp = checkpoints.load_ocr(ckpt_dir)
            # ⚠ Relevée pour TOUTE planche traversée, pas seulement pour celles qu'on traduit :
            # c'est ce qui permet au rapport de publier le taux d'« indéterminé » du
            # classifieur sur un `--from rendu`, où aucune traduction n'est refaite. Un
            # classifieur dont la distribution ne se mesure que pendant un run complet est un
            # classifieur qu'on ne peut pas contredire.
            structure_page = _structure_de(ckpt_dir, regions, image.size, i)

            motif_page = None
            strategie_page = ""
            rattrapees: list[int] = []
            if "traduction" in a_refaire and sans_llm:
                # ⚠ **On ÉCRIT un `traduction.json` de chaînes vides, on ne l'omet pas**, et
                # c'est la mesure de l'étape 0 qui l'impose. Sans ce fichier,
                # `checkpoints.appliquer_manuelles(None, …)` part d'une liste VIDE et son
                # garde `0 <= index < len(sortie)` rejette TOUT : mesuré le 2026-09-06,
                # **0 correction appliquée sur 3**. Autrement dit, chaque réplique saisie dans
                # la Retouche serait silencieusement perdue — précisément le geste que ce mode
                # existe pour servir.
                #
                # Une bulle par entrée, donc, pour que la saisie atterrisse au bon index. Le
                # lettrage dessine alors des bulles vides sans rien signaler ; omettre le
                # fichier lui ferait au contraire écrire un `ecart_comptage` par planche.
                translated = [""] * len(regions)
                checkpoints.save_traduction(ckpt_dir, translated)
                stats_sans_llm["pages"] += 1
                stats_sans_llm["bulles"] += len(regions)
            elif "traduction" in a_refaire:
                agent = agents["manga_traducteur"]
                tok0 = agent.llm.stats["tokens_generes"] if (verbose and agent.llm) else 0
                t0 = time.perf_counter()
                groupe = groupe_de_page.get(i) or [i]
                if len(groupe) > 1 and i == groupe[0]:
                    # Première planche d'un lot : l'appel porte tout le groupe. Les planches
                    # suivantes retrouveront leur tranche dans `resultats_lot`.
                    membres = []
                    for p in groupe:
                        ck_p = checkpoints.page_checkpoint_dir(build_dir, p)
                        textes_p = checkpoints.load_ocr(ck_p) or []
                        if p == i:
                            img_p, styles_p, regions_p = image, styles, regions
                        else:
                            img_p = Image.open(plan.pages[p - 1]).convert("RGB")
                            regions_p = checkpoints.load_regions(ck_p)
                            styles_p = clean.analyze_regions(
                                img_p, regions_p, mcfg.get("nettoyage"))
                        membres.append(PlancheLot(
                            index=p, textes_jp=textes_p,
                            bboxes=_bbox_des_styles(styles_p, len(textes_p)),
                            # ⚠ La structure est retenue, les masques non : trois listes
                            # d'entiers par planche, là où les `BubbleStyle` pèsent des masques
                            # pleine page (cf. `_bbox_des_styles`).
                            structure=_structure_de(ck_p, regions_p, img_p.size, p),
                            image_b64=_image_b64(img_p) if mode_vision else None))
                    reporter.stage(f"Lot planches {groupe[0]}→{groupe[-1]} "
                                   f"({sum(len(m.textes_jp) for m in membres)} bulles)")
                    # ⚠ `total = 0`, donc INDÉTERMINÉ, et c'est le cas nommé par `PLAN-32`
                    # L32.6 (2) : « l'unité d'avancement est le lot, pas la planche ». Un
                    # appel LLM qui porte trois planches n'en a produit aucune tant qu'il
                    # n'a pas rendu ; annoncer `groupe[-1]/total` ferait avancer la barre de
                    # trois planches avant que la première n'existe. La position acquise est
                    # conservée par le modèle, elle n'est pas perdue — elle se tait.
                    reporter.progres(groupe[-1], 0,
                                     f"lot {groupe[0]}→{groupe[-1]} · "
                                     f"{len(groupe)} planches par appel")
                    # Posé AVANT l'appel : `_traduire_planche_seule` le ramènera à 1 pour chaque
                    # planche effectivement repliée.
                    for p in groupe:
                        lot_effectif[p] = len(groupe)
                    brut_lot = _translate_lot(
                        membres, agent, gloss_text=gloss_text,
                        precedentes=_contexte_precedent(build_dir, groupe[0], contexte_planches,
                                                        contexte_repliques, gloss, accord,
                                                        pack=pack),
                        contexte_oeuvre=contexte_oeuvre, plafond=plafond_lot,
                        num_ctx=num_ctx_declare, stats=stats_trad, reporter=reporter,
                        langue=langue_src, sens=sens, pack=pack, ratio_court=ratio_court,
                        max_retries=int(llm_cfg_manga.get("max_retries", 1)),
                        replier=_traduire_planche_seule)
                    # Rattrapage PUIS écriture, planche par planche, tout de suite. C'est ce qui
                    # rend la persistance immédiate possible sans casser l'invariant « le cache
                    # est déjà rattrapé » — et ce qui fait qu'un `--stop` en milieu de lot ne
                    # coûte plus que la planche en cours (cf. le commentaire du bloc « Lots »).
                    for membre in membres:
                        triplet = brut_lot.get(membre.index)
                        if triplet is None:
                            continue
                        textes_m, motif_m, strategie_m = triplet
                        rattrapees_m: list[int] = []
                        if rattrapage_cfg.get("actif", True):
                            textes_m, rattrapees_m, refus_m = _rattraper_bulles(
                                agent, membre.textes_jp, textes_m, gloss_text=gloss_text,
                                bboxes=membre.bboxes, cfg=rattrapage_cfg, stats=stats_trad,
                                reporter=reporter, page=membre.index, langue=langue_src,
                                pack=pack)
                            rattrapage_refus += refus_m
                        checkpoints.save_traduction(
                            checkpoints.page_checkpoint_dir(build_dir, membre.index), textes_m)
                        resultats_lot[membre.index] = (textes_m, motif_m, strategie_m,
                                                       rattrapees_m)
                    if verbose and agent.llm:
                        dt = time.perf_counter() - t0
                        dtok = agent.llm.stats["tokens_generes"] - tok0
                        reporter.verbose(
                            f"[traduction] lot planches {groupe[0]}→{groupe[-1]} : {dt:.2f}s · "
                            f"~{dtok} tok générés · ~{dtok / dt if dt > 0 else 0:.1f} tok/s")
                        tok0 = agent.llm.stats["tokens_generes"]
                        t0 = time.perf_counter()
                venu_du_lot = i in resultats_lot
                if venu_du_lot:
                    # Déjà rattrapée et déjà écrite à la réception du lot.
                    translated, motif_page, strategie_page, rattrapees = resultats_lot.pop(i)
                else:
                    translated, motif_page, strategie_page = _translate_page(
                        agent, image, texts_jp, mode_vision=mode_vision, gloss_text=gloss_text,
                        styles=styles, langue=langue_src, sens=sens, pack=pack,
                        precedentes=_contexte_precedent(build_dir, i, contexte_planches,
                                                        contexte_repliques, gloss, accord,
                                                        pack=pack),
                        contexte_oeuvre=contexte_oeuvre,
                        structure=structure_page, ratio_court=ratio_court,
                        regions=regions, mode_traduction=mode_traduction,
                        reporter=reporter, page=i,
                        stats=stats_trad,
                        max_retries=int(llm_cfg_manga.get("max_retries", 1)))
                if motif_page:
                    # Tous les motifs, pas seulement le principal : une sortie à la fois
                    # incomplète ET non traduite était rapportée « numérotation incomplète », et
                    # le second motif n'apparaissait nulle part. Le retry, lui, continue de se
                    # décider sur le motif principal (cf. `diagnostiquer`).
                    autres = [m for m in quality_manga.motifs_repliques(
                                  translated, texts_jp, langue=langue_src)
                              if m != motif_page]
                    reporter.warn(
                        f"[traduction] page {i} : "
                        f"{quality_manga.libelle(motif_page, langue_src)} ({motif_page})"
                        + (" · aussi : " + ", ".join(quality_manga.libelle(m, langue_src)
                                                     for m in autres) if autres else "")
                        + " — sortie conservée, à vérifier")
                if strategie_page == "positionnelle":
                    # Le seul cas où une réplique peut atterrir dans la MAUVAISE bulle : le
                    # modèle n'a numéroté aucune ligne, il ne reste que leur ordre.
                    reporter.warn(f"[traduction] page {i} : aucune ligne numérotée — répliques "
                                  f"rattachées dans l'ordre, alignement non garanti")
                # Rattrapage UNITAIRE des bulles restées vides : une bulle, une réponse, aucun
                # numéro à se tromper. Le retry de page, lui, rejoue la numérotation — donc
                # exactement ce qui vient d'échouer.
                if rattrapage_cfg.get("actif", True) and not venu_du_lot:
                    translated, rattrapees, refus_r = _rattraper_bulles(
                        agent, texts_jp, translated, gloss_text=gloss_text, styles=styles,
                        cfg=rattrapage_cfg, stats=stats_trad, reporter=reporter, page=i,
                        langue=langue_src, pack=pack)
                    rattrapage_refus += refus_r
                if not venu_du_lot:
                    checkpoints.save_traduction(ckpt_dir, translated)
                # Pas de ligne par page pour une planche issue d'un lot : son temps de traduction
                # a déjà été compté dans la ligne du lot, et ce qui reste ici (le rattrapage seul)
                # s'afficherait « 0,01 s · 0 tok », c'est-à-dire un chiffre juste et trompeur.
                if verbose and agent.llm and not venu_du_lot:
                    dt = time.perf_counter() - t0
                    dtok = agent.llm.stats["tokens_generes"] - tok0
                    speed = dtok / dt if dt > 0 else 0
                    reporter.verbose(f"[traduction] page {i}/{total} : {dt:.2f}s · ~{dtok} tok "
                                     f"générés · ~{speed:.1f} tok/s")
            else:
                translated = checkpoints.load_traduction(ckpt_dir)
                # Ni le motif ni la stratégie ne sont recalculables sans la sortie BRUTE du
                # modèle, qui n'est pas persistée : on les reprend du `qa.json` précédent. Sans
                # cela, un simple `--from rendu` effacerait le diagnostic de la traduction qu'il
                # réutilise, et le rapport annoncerait « 0 échec » sur un tome qui n'a pas changé.
                ancien_qa = report_manga.load_page_qa(ckpt_dir) or {}
                motif_page = ancien_qa.get("motif_traduction")
                strategie_page = ancien_qa.get("strategie_traduction") or ""
                # Comme le motif et la stratégie : la taille de lot décrit la traduction qu'on
                # RÉUTILISE, pas le réglage du run en cours. Un `--from rendu` lancé avec `--lot 1`
                # ferait sinon passer pour « traduites seules » 150 planches issues d'un lot de 20.
                lot_effectif[i] = int(ancien_qa.get("lot_taille") or 1)
                rattrapees = [b["index"] for b in ancien_qa.get("bulles") or []
                              if b.get("rattrapee")]
                # Re-CONTRÔLE du cache, purement lexical et sans le moindre appel LLM. Un
                # `traduction.json` fautif était sinon re-rendu indéfiniment : le motif était
                # recopié du `qa.json` précédent, jamais recalculé, si bien qu'un `--from rendu`
                # ne pouvait pas découvrir un défaut que le run initial n'avait pas vu. Le cas
                # qui compte est la source recopiée — invisible au rendu depuis la 0.24.0 sur
                # une source CJK, puisque ces caractères sont supprimés faute de glyphe. Sur une
                # source latine elle est au contraire parfaitement dessinable, donc encore plus
                # sournoise : la planche a l'air traduite.
                if quality_manga.motifs_repliques(translated, texts_jp, langue=langue_src):
                    reporter.warn(
                        f"[traduction] page {i} : {du_langue} subsiste EN CACHE — "
                        f"`--page {i} --from traduction` pour la reprendre")
                    motif_page = motif_page or quality_manga.MOTIF_SOURCE_RESIDUELLE

            # ═══ Relecture à MANDAT ÉTROIT (lot 15, L7.9) ═════════════════════════════════════
            # Placée ici, c'est-à-dire APRÈS la traduction et le rattrapage, AVANT les
            # corrections manuelles et le forçage. L'ordre est celui de l'autorité : ce qu'un
            # humain a tapé ne se fait pas relire par un modèle, et ce que le glossaire impose
            # passe en dernier quoi qu'il arrive.
            #
            # ⚠ `agent_relecteur` est `None` dans la configuration livrée — `manga_relecteur`
            # n'est pas dans `manga.modeles`. La règle « glossaire », elle, tourne quand même :
            # elle est purement lexicale (cf. `relecture.termes_manques`), et c'est elle qui
            # alimente la colonne que `tools/banc.py` attendait.
            if "traduction" in a_refaire:
                translated, propositions = relecture.relire(
                    agent_relecteur, texts_jp or [], translated, gloss_text=gloss_text,
                    contexte_oeuvre=contexte_oeuvre,
                    lignes_bulles=planche_mod.lignes_bulles(texts_jp or [], structure_page,
                                                            pack=pack),
                    glo=gloss, page=i, stats=stats_relecture, pack=pack)
                acceptees = [p for p in propositions if p.acceptee]
                if acceptees:
                    checkpoints.save_traduction(ckpt_dir, translated)
                    reporter.info(
                        f"[relecture] page {i} : {len(acceptees)} correction(s) appliquée(s) — "
                        + ", ".join(f"bulle {p.bulle} ({p.regle})" for p in acceptees[:4]))
                refusees = [p for p in propositions if not p.acceptee]
                if refusees:
                    reporter.warn(
                        f"[relecture] page {i} : {len(refusees)} proposition(s) rejetée(s) — "
                        + ", ".join(sorted({p.motif_refus for p in refusees})))

            # Registre de deuxième personne (L7.10) — purement lexical, AUCUN appel LLM, donc
            # relevé même sur un `--from rendu` et même quand `manga_contexte` est éteint.
            # C'est ce qui rend la fiche de registre ÉVALUABLE : jusqu'ici, même branchée, rien
            # ne vérifiait que la traduction l'avait suivie.
            compte_registre = registre.relever_planche(translated, pack.code)
            if compte_registre:
                registre_par_planche[i] = compte_registre

            # ═══ Corrections écrites À LA MAIN ═══════════════════════════════════════════════
            # Superposées APRÈS la traduction (fraîche ou relue), donc quel que soit le chemin, et
            # avant le forçage et le rendu. Le pipeline n'écrit jamais ce fichier : une réplique
            # corrigée à la main survit à `--from traduction` comme à `--from rendu`. C'est la
            # transposition de l'`Origin::User` de koharu, et c'est ce qui rend un re-run non
            # destructif — la brique en avait besoin bien avant l'interface graphique.
            manuelles = checkpoints.load_traduction_manuelle(ckpt_dir)
            corrigees: list[int] = []
            if manuelles:
                translated, corrigees = checkpoints.appliquer_manuelles(translated, manuelles)
                if corrigees:
                    stats_manuelles["bulles"] += len(corrigees)
                    stats_manuelles["pages"] += 1
                    reporter.info(f"[traduction] page {i} : {len(corrigees)} réplique(s) "
                                  f"reprise(s) à la main, conservée(s) telle(s) quelle(s)")

            # Dérive ANCRÉE (T1) : le japonais de la bulle contient un `termes_source` de l'entrée,
            # et le français y écrit une forme proche du nom canonique sans être lui. Il n'y a
            # rien à interpréter — d'où le droit de corriger CE run. L'interdit est ajouté au
            # glossaire en mémoire juste avant le forçage, si bien que la correction passe par
            # `enforce_force` INCHANGÉ, avec ses garde-fous d'élision et d'accord, plutôt que par
            # un second remplacement qui les réinventerait moins bien.
            #
            # Muter `gloss` ici ne rend pas le glossaire mouvant pour le TRADUCTEUR : `gloss_text`
            # est figé avant la boucle. Seul le forçage, déterministe, voit l'ajout.
            if translated and derive_cfg.get("actif", True):
                nouvelles = terminology.derives_ancrees(gloss, texts_jp, translated, page=i)
                n_bannies = terminology.appliquer_derives(gloss, nouvelles)
                if n_bannies:
                    derives += nouvelles
                    stats_gloss["derives_bannies"] += n_bannies
                    for d in dict.fromkeys((n.candidat, n.nom, n.source) for n in nouvelles):
                        reporter.warn(f"[glossaire] page {i} : « {d[0]} » est une dérive de "
                                      f"« {d[1]} » (ancrée sur {d[2]}) — bannie et corrigée")

            # Forçage des entrées `force: true` — appliqué à l'USAGE, pas à l'écriture du cache
            # (cf. `manga/terminology.py` : sans agent en aval, garder la sortie brute permet de
            # corriger une orthographe au glossaire et de relancer `--from rendu` sans un seul
            # appel LLM). Une forme bannie qui subsiste est un incident, comme un débordement.
            if translated:
                translated, n_forces, refus = terminology.forcer_bulles(translated, gloss,
                                                                         accord=accord)
                stats_force["remplacements"] += n_forces
                if refus:
                    force_refus += refus
                    for message in refus:
                        reporter.warn(f"[glossaire] page {i} : {message}")

            # Texte hors bulle : la géométrie et l'OCR viennent du balayage A ; il ne reste que
            # la traduction, puis la glose au moment du rendu.
            zones_sfx: list = []
            textes_sfx: list[str] = []
            tris_sfx: list[str] = []
            traductions_sfx: list[str] = []
            # Le VERDICT de lecture et le STYLE de chaque zone gardée. Les deux existaient
            # déjà — le premier calculé plus bas, le second persisté par le lot 21 — mais
            # aucun ne sortait du bloc où il naissait. `manga/effacement.py` a besoin des
            # deux, et il n'a le droit d'agir que sur les zones `lecture_sure`.
            verdicts_sfx: list[str] = []
            styles_zones_sfx: list = []
            if sfx_actif:
                charge = checkpoints.load_sfx_complet(ckpt_dir)
                if charge is not None:
                    # Le mobilier de page est écarté ICI, une fois pour toutes : il ne doit
                    # atteindre ni la traduction, ni la glose, ni le rapport. Un filigrane traduit
                    # est du bruit partout où il passe.
                    # ⚠ `langue` n'est pas facultatif ici : sur une source latine, le triage
                    # par défaut classerait TOUTES les onomatopées en bruit et les jetterait
                    # en silence (cf. `text_detection.trier_zone`).
                    tris = [text_detection.trier_zone(
                                charge["textes"][k] if k < len(charge["textes"]) else "",
                                mobilier=(charge["mobilier"][k:k + 1] or [False])[0],
                                langue=langue_src)
                            for k in range(len(charge["regions"]))]
                    garde = [k for k, tri in enumerate(tris)
                             if tri in (text_detection.TRI_TEXTE,
                                        text_detection.TRI_PONCTUATION)]
                    zones_sfx = [charge["regions"][k] for k in garde]
                    textes_sfx = [charge["textes"][k] if k < len(charge["textes"]) else ""
                                  for k in garde]
                    tris_sfx = [tris[k] for k in garde]
                    styles_zones_sfx = _styles_zones(
                        charge["styles"], garde, zones_sfx,
                        image if sfx_eff_mode != "aucun" else None,
                        mcfg.get("nettoyage"))
                    for tri in tris:
                        stats_sfx["tri"][tri] = stats_sfx["tri"].get(tri, 0) + 1
                if zones_sfx and sfx_mode != "aucun":
                    # Seules les zones réellement porteuses de texte partent au LLM. La
                    # ponctuation pure (`！！`, `．．．`) se rend déterministement — mieux qu'un
                    # modèle, qui broderait — et ne coûte rien.
                    a_traduire = [k for k, tri in enumerate(tris_sfx)
                                  if tri == text_detection.TRI_TEXTE]
                    deja = checkpoints.load_sfx_traduction(ckpt_dir)
                    # Retraduire seulement si le cache manque ou ne correspond plus au nombre de
                    # zones — sinon un `--from rendu` repaierait un appel LLM par planche.
                    if agent_sfx is not None and a_traduire and (
                            deja is None or len(deja) != len(zones_sfx)):
                        rendues = _translate_sfx(
                            agent_sfx, [textes_sfx[k] for k in a_traduire], gloss_text,
                            # ⚠ L'IMAGE, enfin (lot 15, L7.7) : une onomatopée est un dessin,
                            # et cette passe la traduisait depuis un OCR dont le dépôt mesure
                            # lui-même qu'il hallucine sur un glyphe stylisé.
                            image=image if sfx_vision else None,
                            zones=[zones_sfx[k] for k in a_traduire] if sfx_vision else None,
                            vision=sfx_vision, pack=pack,
                            stats=stats_trad, langue=langue_src, sens=sens,
                            max_retries=int(llm_cfg_manga.get("max_retries", 1)))
                        traductions_sfx = [typeset.latiniser(t) for t in textes_sfx]
                        for position, k in enumerate(a_traduire):
                            traductions_sfx[k] = (rendues[position]
                                                  if position < len(rendues) else "")
                        checkpoints.save_sfx_traduction(ckpt_dir, traductions_sfx)
                    elif deja is not None and len(deja) == len(zones_sfx):
                        traductions_sfx = deja
                    else:
                        traductions_sfx = [
                            typeset.latiniser(t) if tri == text_detection.TRI_PONCTUATION else ""
                            for t, tri in zip(textes_sfx, tris_sfx)]
                    if traductions_sfx:
                        traductions_sfx, _n, _r = terminology.forcer_bulles(traductions_sfx, gloss, accord=accord)
                    # ⚠ L21.4 — le refus des traductions BRODÉES vient APRÈS le forçage du
                    # glossaire et AVANT le comptage : forcer un terme dans une phrase
                    # inventée puis la compter comme traduite ferait mentir les deux.
                    if sfx_broderie > 0 and traductions_sfx:
                        traductions_sfx, brodees = quality_manga.refuser_onomatopees_brodees(
                            textes_sfx, traductions_sfx, ratio=sfx_broderie)
                        for k in brodees:
                            stats_sfx["broderie"] = stats_sfx.get("broderie", 0) + 1
                            sfx_refus.append(
                                f"page {i} zone {k + 1} — "
                                f"{quality_manga.LIBELLES[quality_manga.MOTIF_SFX_BRODERIE]}")
                            reporter.warn(
                                f"[sfx] page {i} zone {k + 1} : traduction rejetée — "
                                f"une phrase là où une onomatopée était attendue ; la zone "
                                f"reste sans glose et signalée")
                    stats_sfx["traduites"] += sum(1 for t in traductions_sfx if t.strip())

                # --- L21.3 : seconde voie de lecture, concordance, et voie C -------------
                #
                # ⚠ DÉSARMÉE par défaut, et le chiffre est dans `config.yaml` : la seconde
                # voie coûte un appel LLM de plus par planche porteuse. Ce qu'elle apporte,
                # c'est le seul drapeau sur lequel `PLAN-22` pourra s'appuyer pour dessiner
                # — et le dépôt n'en a aucun aujourd'hui.
                if zones_sfx and sfx_mode != "aucun":
                    lectures_b: list[str] = []
                    if sfx_concordance and agent_sfx is not None:
                        lectures_b = _lire_sfx_vision(
                            agent_sfx, image, zones_sfx, pack=pack, langue=langue_src,
                            stats=stats_sfx)
                    if lectures_b:
                        verdicts_sfx[:], _scores = sfx_lecture.verdicts(
                            [[a, b] for a, b in zip(textes_sfx, lectures_b)])
                    else:
                        # Une seule voie ne concorde avec rien : c'est exactement l'état du
                        # dépôt avant ce lot, et l'appeler « sûre » baptiserait le problème.
                        verdicts_sfx[:] = [sfx_lecture.LECTURE_DOUTEUSE] * len(zones_sfx)
                    for v in verdicts_sfx:
                        stats_sfx[f"lecture_{v}"] = stats_sfx.get(f"lecture_{v}", 0) + 1
                    if sfx_crops > 0:
                        douteuses = [k for k, v in enumerate(verdicts_sfx)
                                     if v == sfx_lecture.LECTURE_DOUTEUSE]
                        restant = max(0, sfx_crops - stats_sfx.get("crops", 0))
                        noms = _exporter_crops_sfx(
                            image, zones_sfx, douteuses,
                            build_dir / DOSSIER_CROPS_SFX, i, plafond=restant)
                        stats_sfx["crops"] = stats_sfx.get("crops", 0) + len(noms)

            reporter.info(f"{len(regions)} bulle(s)."
                          + (f" {len(zones_sfx)} zone(s) hors bulle." if zones_sfx else ""))
            t0 = time.perf_counter()
            # `styles` vient de l'image d'origine, `report_out` collecte tailles, replis,
            # débordements et écarts de comptage — de quoi alimenter RAPPORT.md (lot 1.7).
            rendu_qa: list[dict] = []
            fits_qa: list[dict] = []
            # ⚠ `typeset_page` MUTE l'image qu'on lui donne : sans copie, le PSD recevrait comme
            # « planche nettoyée » une planche déjà lettrée.
            fond_propre = cleaned.copy() if psd_actif else None
            # ⚠ UN SEUL chemin de rendu dans tout le dépôt (`manga/rendu.py`). L'éditeur graphique
            # redessine une planche sans repasser par `process_volume` ; lui écrire un second
            # moteur ferait diverger les deux sur la seule chose que l'utilisateur regarde. Un
            # test compare les deux sorties au pixel près.
            resultat = rendu.rendre_planche(
                cleaned, regions, translated, styles=styles, font_path=font_path,
                cfg_typeset=mcfg.get("typeset"),
                # Le japonais sert au seul `marqueur_vide` : une bulle sans source est vide à
                # bon droit.
                sources=texts_jp,
                # Positions imposées à la main (éditeur graphique). Absent = comportement
                # d'avant, au bit près.
                layouts=checkpoints.load_mise_en_page(ckpt_dir),
                avec_fits=psd_actif,
                zones_sfx=zones_sfx if sfx_actif else None,
                traductions_sfx=traductions_sfx,
                mode_sfx=sfx_mode if sfx_actif else "",
                # Lot 22 : le style mesuré et le verdict de lecture de chaque zone. Sans le
                # second, `effacer_zones` refuse tout — c'est le critère 10 du plan de lot, et
                # aucune clé ne le désarme.
                styles_sfx=styles_zones_sfx,
                verdicts_sfx=verdicts_sfx,
                cfg_effacement=sfx_eff_cfg if sfx_actif else None,
                # Image d'ORIGINE : elle permet de recoller le dessin d'une fausse détection
                # que le nettoyage avait repeinte (cf. `rendu.restaurer_sans_texte`).
                originale=image)
            final_img = resultat.image
            rendu_qa.extend(resultat.qa)
            # Une zone restaurée est une FAUSSE DÉTECTION probable : le nettoyage l'avait
            # repeinte, et ni l'OCR ni la traduction n'y ont trouvé quoi que ce soit. On la
            # signale plutôt que de la taire — c'est actionnable, il suffit de supprimer la
            # bulle dans l'éditeur pour que la planche n'y repasse plus.
            for k in resultat.restaurees:
                rendu_qa.append({"type": "restauree", "index": k})
                zones_restaurees.append(
                    f"page {i} bulle {k + 1} — aucun texte : dessin d'origine recollé")
            if resultat.restaurees:
                reporter.warn(
                    f"[rendu] page {i} : {len(resultat.restaurees)} zone(s) sans aucun texte — "
                    f"dessin d'origine RECOLLÉ (fausse détection probable, bulle(s) "
                    + ", ".join(str(k + 1) for k in resultat.restaurees) + ")")
            fits_qa.extend(resultat.fits)
            # ⚠ Le journal de l'effacement porte AUSSI les décisions de ne rien peindre, et
            # c'est ce qui compte : un filtre muet est la façon dont on perd les zones
            # suivantes sans le voir (acquis de L21.1, et il vaut ici aussi).
            if resultat.effacement is not None:
                for motif, n in resultat.effacement.motifs().items():
                    stats_sfx["effacement"][motif] = (
                        stats_sfx["effacement"].get(motif, 0) + n)
                stats_sfx["effacees"] += resultat.effacement.zones_effacees
                if resultat.effacement.zones_effacees and verbose:
                    reporter.verbose(
                        f"[effacement] page {i}/{total} : "
                        f"{resultat.effacement.zones_effacees} zone(s) · "
                        f"{resultat.effacement.pixels} px reconstruits "
                        f"(mode « {sfx_eff_mode} »)")
            stats_sfx["relettrees"] += len(resultat.fits_sfx)
            gloses_page = resultat.gloses
            if gloses_page:
                posees = sum(1 for g in gloses_page if g is not None)
                stats_sfx["posees"] += posees
                for message in resultat.refus_gloses:
                    sfx_refus.append(f"page {i} {message}")
                if verbose and posees:
                    reporter.verbose(f"[glose] page {i}/{total} : {posees}/{len(zones_sfx)} "
                                     f"posée(s)")
            final_img.save(out_path)
            polices_psd: list[str] = []
            if psd_actif:
                # Défaut « type » depuis la v0.27.0 : validé par le moteur de Photoshop lui-même
                # (`tools/valider_psd_photoshop.ps1`), et sans coût de fidélité — le calque porte
                # à la fois nos pixels et l'information de texte, la composition Photoshop est
                # identique au pixel près. Le repli reste « rasterise » si la clé manque.
                mode_texte_psd = str(rendu_cfg.get("psd_texte", "type"))
                polices_psd = psd.polices_utilisees(fits_qa, mode_texte_psd)
                # Chronométré comme `[rendu]` juste en dessous. Sans cette durée, la ligne
                # annonçait un poids sans son prix : le PSD pèse 8,5 Mo par planche en moyenne
                # (mesuré sur 469 écritures) et représente 68 % de la sortie d'un tome — 1,3 Go
                # sur 1,9 pour *manga A* Vol.1. Un défaut assumé doit rester chiffrable,
                # sans quoi personne ne peut décider de l'éteindre en connaissance de cause.
                t0_psd = time.perf_counter()
                try:
                    chemin_psd = psd.ecrire_planche(
                        checkpoints.psd_page_path(build_dir, i), finale=final_img,
                        nettoyee=fond_propre, fits=fits_qa,
                        originale=image if rendu_cfg.get("psd_original", True) else None,
                        mode_texte=mode_texte_psd,
                        dpi=int(rendu_cfg.get("pdf_dpi", 300)),
                        # ── Lot 22, L22.4 : ce qui manquait à un letteur ────────────────
                        # L'effacement, séparé donc réversible ; les gloses, qui n'existaient
                        # que dans le composite aplati ; une zone hors bulle par calque ; et
                        # un calque VIDE par zone qu'on n'a pas su lire, pour qu'il voie OÙ
                        # intervenir au lieu de rouvrir la planche et de chercher la boîte.
                        effacement=resultat.effacement,
                        gloses=gloses_page,
                        fits_sfx=resultat.fits_sfx,
                        # ⚠ Les calques VIDES ne sont écrits que si l'effacement est armé, et
                        # ce garde-fou n'est pas de la coquetterie : sans seconde voie de
                        # lecture, TOUTE zone est douteuse. Les émettre inconditionnellement
                        # ajouterait un calque vide par zone hors bulle à chaque PSD du
                        # corpus — 2 455 calques sur six tomes — pour un mode que personne
                        # n'a demandé. Le défaut doit rester le fichier d'avant.
                        zones_illisibles=(_zones_illisibles(zones_sfx, textes_sfx,
                                                            verdicts_sfx)
                                          if sfx_eff_mode != "aucun" else None))
                except psd.TropGrandPourPSD as e:
                    # ⚠ On perd le PSD de CETTE planche, pas la planche. Les autres formats de
                    # sortie n'ont pas la limite du PSD, et la page traduite est déjà écrite
                    # dans `pages_out/` deux lignes plus haut : faire échouer la planche
                    # entière punirait le lettrage pour une contrainte de format de retouche.
                    psd_refuses.append(f"page {i} — {e}")
                    reporter.warn(f"[psd] page {i}/{total} : {e}")
                else:
                    if verbose:
                        reporter.verbose(f"[psd] page {i}/{total} : {chemin_psd.name} · "
                                         f"{time.perf_counter() - t0_psd:.2f}s · "
                                         f"{chemin_psd.stat().st_size / 1e6:.1f} Mo · "
                                         f"{len(fits_qa)} calque(s) de texte")
            if verbose:
                tailles = [e["taille"] for e in rendu_qa if e["type"] == "bulle"]
                debord = [e for e in rendu_qa if e.get("overflow")]
                detail = ""
                if tailles:
                    detail = (f" · tailles {min(tailles)}-{max(tailles)} px "
                              f"(médiane {sorted(tailles)[len(tailles) // 2]})")
                reporter.verbose(f"[rendu] page {i}/{total} : {time.perf_counter() - t0:.2f}s"
                                 + detail + (f" · {len(debord)} débordement(s)" if debord else ""))
            # Un débordement ou un écart de comptage est un incident : le dire, page et bulle à
            # l'appui. « Un échec non compté est un échec invisible. »
            # Une région dégénérée produit DEUX entrées : la perte de texte et le
            # débordement formel du `Fit` vide qui la porte. Les afficher toutes les deux
            # dirait deux fois la même chose, dont une fois avec le mauvais conseil.
            sans_texte = {e["index"] for e in rendu_qa
                          if e.get("type") == "replique_non_dessinee"}
            for e in rendu_qa:
                if e["type"] == "ecart_comptage":
                    reporter.warn(f"[rendu] page {i} : {e['bulles']} bulle(s) mais "
                                  f"{e['traductions']} traduction(s) — écart de {e['ecart']}")
                elif e.get("overflow") and e.get("index") not in sans_texte:
                    # Le conseil dépend de la CAUSE : sur ce tome, « raccourcir la traduction »
                    # était donné neuf fois et n'était juste qu'une seule.
                    conseil = {
                        "bulle_degeneree": "région dégénérée (elle ne peut porter aucun "
                                           "mot) — NON lettrée, corriger la détection",
                        "bulle_etroite": "bulle trop étroite pour le mot le plus long — "
                                         "corriger la détection ou scinder la région",
                        # ⚠ Ce cas-là n'accuse NI la détection NI la traduction. Il est
                        # apparu en changeant de police : Wildjess est ~1,3× plus large que
                        # ComicNeue-Bold à corps égal, et quatre bulles inchangées sont
                        # passées en débordement d'un run à l'autre. Conseiller « corriger
                        # la détection » envoyait chercher un défaut qui n'existe pas.
                        "police_trop_large": "le mot le plus long ne tient pas au plus "
                                             "petit corps DANS LA POLICE demandée — ni la "
                                             "détection ni la traduction ne sont en cause. "
                                             "Lettrée quand même : raccourcir la réplique, "
                                             "ou choisir une police moins large "
                                             "(manga.typeset.font_path)",
                    }.get(e.get("cause", ""), "raccourcir la traduction")
                    reporter.warn(f"[rendu] page {i} bulle {e['index'] + 1} : ne tient pas "
                                  f"dans la bulle (dessiné à {e['taille']} px, non tronqué)"
                                  f" — {conseil}")
                elif e["type"] == "replique_non_dessinee":
                    # Le seul incident du rendu où du TEXTE DISPARAÎT. Il mérite son
                    # propre message : un débordement se voit sur la planche, une
                    # réplique absente non. On nomme donc la réplique perdue.
                    #
                    # ⚠ Les deux causes ne donnent pas la même planche, et le dire faux
                    # enverrait chercher au mauvais endroit : une région dégénérée a été
                    # NETTOYÉE, donc la bulle sort blanche ; une bulle non nettoyée a
                    # gardé son japonais, donc la planche montre la source d'origine.
                    sort = ("la bulle a gardé son texte JAPONAIS"
                            if e.get("cause") == "bulle_non_nettoyee"
                            else "la bulle est VIDE sur la planche")
                    reporter.warn(f"[rendu] page {i} bulle {e['index'] + 1} : RÉPLIQUE "
                                  f"NON DESSINÉE — « {e['texte'][:60]} » "
                                  f"({e['cause']}) : {sort}.")
                elif e["type"] == "glyphes_manquants" and e.get("caracteres"):
                    reporter.warn(f"[rendu] page {i} bulle {e['index'] + 1} : « {e['caracteres']} » "
                                  f"absent(s) de {e['police']} et sans équivalent latin — "
                                  f"SUPPRIMÉ(s) plutôt que dessiné(s) en carré")

            # Contrôle qualité PERSISTÉ par page : une page réutilisée du cache ne produit aucune
            # statistique fraîche, si bien qu'un rapport construit sur le seul run en cours serait
            # quasi vide sur une reprise — donc mensonger. Le rapport relit tous les qa.json.
            report_manga.save_page_qa(ckpt_dir, report_manga.build_page_qa(
                page=i, nom_fichier=page_path.name, regions=regions, styles=styles,
                texts_jp=texts_jp, translated=translated, rendu_qa=rendu_qa,
                motif_traduction=motif_page, strategie_traduction=strategie_page,
                rattrapees=rattrapees, polices_psd=polices_psd,
                sfx=zones_sfx, sfx_textes=textes_sfx, sfx_traductions=traductions_sfx,
                sfx_gloses=gloses_page, sfx_mode=sfx_mode if sfx_actif else "",
                scission_cfg=(mcfg.get("detection") or {}).get("scission"),
                lot_taille=lot_effectif.get(i, 1),
                origines=checkpoints.load_origines(ckpt_dir), corrigees=corrigees,
                think=reflexion_traducteur))
            n_done += 1

    # Compteurs de TOUS les clients du run, pas seulement celui du traducteur : depuis que
    # `endpoint:` fonctionne côté manga (lot 2.2), un agent peut router vers un client
    # distinct, et un rapport qui ne lirait que `agents["manga_traducteur"].llm.stats`
    # sous-compterait les appels. C'est le défaut exact que le LN avait mesuré chez lui
    # (79 appels annoncés contre 183 réellement tracés dans perf.log).
    reporter.phase("finalisation")
    pluriels = _passe_derive_volume(gloss, derives, build_dir=build_dir, total=total,
                                    derive_cfg=derive_cfg, stats=stats_gloss,
                                    gloss_path=gloss_path, reporter=reporter, dry_run=dry_run)

    stats_llm = runtime.aggregate_llm_stats(None, agents)
    a_tourne = stats_llm["appels"] > 0 or stats_llm["temps_generation"] > 0
    rapport = report_manga.write_report(
        build_dir, project, volume, total_pages=total, mcfg=mcfg,
        duree_s=time.perf_counter() - t_start,
        stats_llm=(stats_llm if a_tourne else None),
        stats_traduction=stats_trad or None,
        stats_glossaire={**stats_gloss, **stats_force,
                         "entrees_forcees": terminology.compter_forcees(gloss)},
        force_refus=force_refus or None, derives=derives, pluriels=pluriels,
        rattrapage_refus=rattrapage_refus or None,
        sfx_refus=sfx_refus or None, stats_sfx=stats_sfx,
        stats_manuelles=stats_manuelles, stats_sans_llm=stats_sans_llm,
        planches_en_echec=planches_en_echec or None,
        psd_refuses=psd_refuses or None,
        structures=structures_tome or None,
        registre_par_planche=registre_par_planche or None,
        stats_relecture=stats_relecture,
        # ⚠ Relu une dernière fois : le rendu et le PSD viennent APRÈS les passes visuelles,
        # et sur ce format ils ne sont pas des figurants — un PSD de bande pèse 42 à 60 Mo.
        pic_memoire=max(pic_tome or 0, memoire.pic() or 0) or None,
        format_planche=plan.format, langue=langue_src, sens=sens)
    reporter.info(f"Rapport : {rapport.name}")
    if planches_en_echec:
        # Répété à la fin, comme le bilan terminologique et pour la même raison : sur un tome
        # de 150 planches, l'avertissement d'échec a défilé depuis longtemps quand le run se
        # termine — et c'est la seule ligne qui doive survivre au défilement.
        pages = ", ".join(str(e["page"]) for e in planches_en_echec[:12])
        reporter.warn(
            f"{len(planches_en_echec)} planche(s) en ÉCHEC — {pages}"
            + (f" (+{len(planches_en_echec) - 12})" if len(planches_en_echec) > 12 else "")
            + f". Elles ne sont NI traduites NI rendues ; le détail est dans {rapport.name}.")

    # Index du tome — ce qu'une interface graphique lira pour ouvrir le projet sans rejouer le
    # pipeline. La révision n'augmente que si le contenu a réellement bougé.
    etat_projet = projet_mod.ecrire(build_dir, projet_mod.construire(
        build_dir, projet=project, tome=volume, pages=plan.pages, version=__version__,
        page_ckpt=checkpoints.page_checkpoint_dir,
        format_planche=plan.format, langue_source=langue_src, sens=sens))
    if verbose:
        reporter.verbose(f"[projet] {etat_projet.name} — révision "
                         f"{(projet_mod.lire(build_dir) or {}).get('revision', 1)}")

    outputs = assemble_outputs(build_dir, mcfg, project, volume, reporter=reporter, sens=sens)
    reporter.finish(outputs)

    # Bilan terminologique à la FIN, et pas seulement avant la première planche : sur un tome
    # de 150 planches, la ligne écrite par la passe a défilé depuis longtemps quand le run se
    # termine. Deux questions « la terminologie ne s'est pas déclenchée » ont été posées sur
    # des runs où elle avait parfaitement tourné — le rapport le disait, la console non.
    if not stats_gloss["terminologue_actif"]:
        reporter.info("Terminologie — passe DÉSACTIVÉE : décommente `manga.modeles."
                      "terminologue` dans config.yaml, puis relance avec `--from traduction`.")
    elif stats_gloss["pages_relevees"] or stats_gloss["pages_reprises"]:
        relevees, reprises = stats_gloss["pages_relevees"], stats_gloss["pages_reprises"]
        reporter.info(
            f"Terminologie — {relevees} planche(s) relevée(s)"
            + (f", {reprises} reprise(s) du cache" if reprises else "")
            + f" · +{stats_gloss['ajouts']} entrée(s), {stats_gloss['fusions']} fusion(s) · "
            f"glossaire : {glossary.total(gloss)} entrée(s) dans {gloss_path}")
    else:
        # Troisième état, et il faut le nommer : « 0 planche relevée » se lirait comme un
        # échec alors que rien n'était à relever — c'est le cas de tout `--from rendu`.
        reporter.info(f"Terminologie — passe active, aucune planche à relever ce run · "
                      f"glossaire : {glossary.total(gloss)} entrée(s) dans {gloss_path}")

    if stats_llm["temps_generation"] > 0:
        vitesse = stats_llm["tokens_generes"] / stats_llm["temps_generation"]
        reporter.info(f"Traduction — appels LLM : {stats_llm['appels']} · tokens générés : "
                     f"~{stats_llm['tokens_generes']} · vitesse moyenne : ~{vitesse:.0f} tok/s")
    runtime.close_llm_clients(None, agents)
    return True


def _passe_derive_volume(gloss: dict, derives: list, *, build_dir: Path, total: int,
                         derive_cfg: dict, stats: dict, gloss_path: Path, reporter,
                         dry_run: bool) -> list[tuple[str, str, int]]:
    """**Dérive de VOLUME (T2/T3)** — après la dernière planche, jamais avant.

    T2 compare le poids d'un nom à celui d'une forme proche SUR TOUT LE TOME : la statistique
    n'existe pas tant qu'une planche reste à traduire. Et l'écriture du fichier attend ici
    pour la même raison que le relevé se fait en une passe — un glossaire qui bouge en cours
    de route donnerait à chaque planche un état différent.

    `derives` est **étendue en place** (les T2 s'ajoutent aux T1 déjà relevées), et la valeur
    de retour est la liste des pluriels à proposer au rapport.

    Extraite du corps de `_process_volume` pour que `glossaire_seul` la rejoue à l'identique :
    elle ne lit que les `traduction.json` DÉJÀ en cache, donc elle vaut aussi bien après un
    tome traduit ce run qu'avant un tome traduit il y a trois semaines."""
    if not derive_cfg.get("actif", True):
        return []
    deja = {d.candidat for d in derives}
    textes_volume = [t for i in range(1, total + 1)
                     for t in (checkpoints.load_traduction(
                         checkpoints.page_checkpoint_dir(build_dir, i)) or [])
                     if t and t.strip()]
    nouvelles = terminology.derives_de_volume(gloss, textes_volume, deja=deja, cfg=derive_cfg)
    derives += nouvelles
    pluriels = terminology.proposer_pluriels(gloss, textes_volume)
    stats["derives_bannies"] += terminology.appliquer_derives(gloss, nouvelles)
    if stats["derives_bannies"]:
        # ⚠ En dry-run on ne touche PAS au glossaire : c'est une source de l'utilisateur,
        # pas un artefact de build. Le rapport, lui, liste quand même les dérives.
        if dry_run:
            reporter.info(f"Glossaire : {stats['derives_bannies']} forme(s) à bannir "
                          f"détectée(s) — non écrite(s) (dry-run).")
        else:
            glossary.save(gloss, gloss_path)
            reporter.info(
                f"Glossaire : {stats['derives_bannies']} forme(s) ajoutée(s) en "
                f"`interdits` ({gloss_path.name}) — un `--from rendu` les corrigera sur "
                f"tout le tome, sans un seul appel LLM.")
    return pluriels


def _passe_derive_ancree(gloss: dict, derives: list, *, build_dir: Path, total: int,
                         stats: dict) -> None:
    """**Dérive ANCRÉE (T1)** sur un tome DÉJÀ traduit, relue depuis le cache.

    Le run normal la fait planche par planche, juste après avoir traduit (cf. le site jumeau
    dans le balayage B) : la preuve est que le japonais de la bulle contient un
    `termes_source` de l'entrée. Rien là-dedans n'exige que la traduction soit fraîche — d'où
    cette relecture, qui est ce que `glossaire_seul` peut offrir de plus fort sur un chapitre
    fini, et qui ne coûte **aucun appel LLM**.

    Une planche sans `traduction.json` est simplement ignorée : il n'y a pas de français à
    confronter au japonais, donc pas de preuve possible."""
    for i in range(1, total + 1):
        ckpt_dir = checkpoints.page_checkpoint_dir(build_dir, i)
        texts_jp = checkpoints.load_ocr(ckpt_dir)
        translated = checkpoints.load_traduction(ckpt_dir)
        if not texts_jp or not translated:
            continue
        nouvelles = terminology.derives_ancrees(gloss, texts_jp, translated, page=i)
        derives += nouvelles
        stats["derives_bannies"] += terminology.appliquer_derives(gloss, nouvelles)


def _passe_terminologie_protegee(agent, *args, sans_llm: bool = False, reporter=None,
                                 stats: dict | None = None, **kwargs) -> tuple[bool, bool]:
    """`_passe_terminologie` sous FILET, et sautée quand le mode sans LLM est actif.

    ## Le défaut que cette enveloppe ferme, et il coûtait des heures de GPU

    La passe de terminologie tourne **entre** le balayage A (détection → nettoyage → OCR) et le
    balayage C (traduction → lettrage → rendu). Elle était appelée **hors du filet par
    planche** (`_filet`) : une `RuntimeError` du client LLM — celle de `core/llm.py`, levée
    après trois tentatives et environ neuf secondes — y remontait à travers `process_volume` et
    **tuait le tome entier**, après que la détection et l'OCR de 150 planches avaient déjà
    tourné.

    ⚠ **Le cas visé n'est pas « lancer un run sans serveur »** — pour ça, il y a `llm.actif:
    false`, qui ne construit aucun client. C'est le serveur qui **meurt en cours de route** :
    une machine qui s'endort, un modèle déchargé, un redémarrage d'Ollama. Le tome doit alors
    perdre son relevé terminologique, pas son balayage A.

    ⚠ **Ce qui est perdu est nommé, jamais masqué.** Sans relevé, le glossaire n'est pas
    enrichi et les planches se traduiront avec celui du disque. Le rapport le dit ; la passe
    n'est pas silencieusement réputée réussie.
    """
    if sans_llm:
        if stats is not None:
            stats["terminologue_actif"] = False
        if reporter is not None:
            reporter.info("[terminologie] passe sautée — mode sans LLM.")
        return True, False
    try:
        return _passe_terminologie(agent, *args, reporter=reporter, stats=stats, **kwargs)
    except (control.StopRequested, KeyboardInterrupt, SystemExit):
        # ⚠ Les trois qui traversent `_filet` traversent aussi celui-ci : un arrêt demandé est
        # une décision de l'utilisateur, pas un incident à rattraper.
        raise
    except Exception as err:                      # noqa: BLE001 — c'est tout l'objet du filet
        if stats is not None:
            stats["terminologue_abandonne"] = f"{type(err).__name__} : {err}"
        if reporter is not None:
            reporter.warn(f"[terminologie] relevé abandonné ({type(err).__name__} : {err}) — "
                          f"le tome continue avec le glossaire du disque. ⚠ Les planches "
                          f"traduites après ce point ne bénéficient pas du relevé de ce run.")
        return True, False


def _passe_terminologie(agent, gloss: dict, gloss_index: dict, *, build_dir: Path, total: int,
                        a_relever: set[int], stats: dict, gloss_path: Path, reporter,
                        verbose: bool = False, ignorer_cache: bool = False,
                        dry: bool = False, arret=None,
                        langue: str = "jp", mode: str = "traduction") -> tuple[bool, bool]:
    """Relève la terminologie sur **tout le volume**, avant que la première planche ne soit
    traduite. Renvoie `(terminée, glossaire_modifié)` — False en premier si un arrêt a été
    demandé en cours de passe.

    `gloss` et `gloss_index` sont **mutés en place** (c'est le contrat de
    `glossary_build.merge_notes(..., index=...)`), donc l'appelant garde ses références.

    Deux catégories de planches, et la distinction est le cœur de la fonction :
      · celles de `a_relever` — leur étape `terminologie` est à refaire — ont le droit de
        consommer **un appel LLM** si elles n'ont pas déjà de notes en cache ;
      · **toutes** les autres sont quand même parcourues, pour re-fusionner leurs
        `terminologie.txt` déjà écrits. C'est déterministe, gratuit, et c'est ce qui
        reconstitue le glossaire du volume entier sur une reprise partielle. Sans cela,
        `--page 3` traduirait avec le seul relevé de la planche 3.

    Une planche sans `ocr.json` est ignorée : elle n'a rien à relever, et `relever_page`
    n'accepte pas `None`. Le cas se produit dès qu'on cible une planche précise d'un tome
    encore vierge.

    `ignorer_cache=True` fait REFAIRE le relevé des planches de `a_relever` dont les notes
    existent déjà. C'est la seule façon de rejouer le terminologue après avoir modifié
    `prompts/terminologue.md` sans supprimer 150 fichiers à la main — d'où son emploi par
    `--extract-glossary --force` et `--extract-glossary --from terminologie`. Les planches
    HORS `a_relever` restent relues du cache : le drapeau élargit un droit d'appel, il ne
    jette pas le travail des autres.

    Le glossaire est sauvé après **chaque** planche qui change quelque chose : un tome de
    150 planches s'interrompt, et l'acquis terminologique ne doit pas partir avec.

    `dry=True` suspend cette écriture — et elle seule : le glossaire vit normalement en
    mémoire, donc le reste du run voit exactement ce qu'il aurait vu. Réservé au mode
    `glossaire_seul` : dans un run manga ordinaire, `--dry-run` ne signifie pas « sans effet
    de bord » (il écrit l'OCR, les pages, le rapport et le CBZ), seulement « sans appel LLM ».

    ⚠ « Changer quelque chose » se mesure sur une EMPREINTE du glossaire rendu, et non sur les
    compteurs de `merge_notes` : re-fusionner des notes déjà intégrées renvoie
    `{"fusions": 1}` à chaque fois, alors que rien ne bouge. S'y fier faisait réécrire le
    fichier 150 fois par run pour rien — et, plus grave, rappelait le glossariste (un appel
    LLM sur tout le glossaire) à chaque relance d'un tome déjà relevé. `to_sectioned` couvre
    tous les champs de `FIELD_ORDER` et coûte 0,03 ms sur un glossaire de 17 entrées."""
    empreinte = glossary.to_sectioned(gloss)
    modifie = False
    # Lot 32 — cette passe était **entièrement muette** pour une barre de progression : elle
    # n'appelait ni `stage` ni `progres`, alors qu'elle vaut jusqu'à 23 % du temps
    # instrumenté d'un run manga (n = 11, `docs/mesures/progression-2026-09-05.md`). Une
    # barre immobile pendant 150 appels LLM est indiscernable d'un blocage.
    reporter.phase("terminologie")
    for i in range(1, total + 1):
        if arret is not None and arret():
            return False, modifie
        reporter.progres(i, total)
        ckpt_dir = checkpoints.page_checkpoint_dir(build_dir, i)
        # ⚠ Une chaîne VIDE est une réponse valide (« rien à signaler ») et doit rester
        # distincte de `None` : sans cette distinction, une planche muette serait relevée à
        # chaque run. Cf. `checkpoints.load_terminologie`.
        notes = checkpoints.load_terminologie(ckpt_dir)
        if notes is None or (ignorer_cache and i in a_relever):
            if i not in a_relever:
                continue
            texts_jp = checkpoints.load_ocr(ckpt_dir)
            if texts_jp is None:
                continue
            t0 = time.perf_counter()
            # En mode « glossaire » (source DÉJÀ en langue de sortie), il n'y a pas de
            # traduction à confronter : la source EST le français produit. La joindre en
            # `deja_fr` la répéterait mot pour mot, ce qui n'apprend rien au terminologue et
            # double le prefill.
            notes, ajouts = terminology.relever_page(
                agent, gloss, gloss_index, page=i, total=total, texts_jp=texts_jp,
                deja_fr=(None if mode == "glossaire"
                         else checkpoints.load_traduction(ckpt_dir)),
                langue=langue)
            checkpoints.save_terminologie(ckpt_dir, notes)
            stats["pages_relevees"] += 1
            if verbose:
                reporter.verbose(f"[terminologie] page {i}/{total} : "
                                 f"{time.perf_counter() - t0:.2f}s · +{ajouts['ajouts']} "
                                 f"entrée(s), {ajouts['fusions']} fusion(s)")
        else:
            ajouts = terminology.fusionner(notes, gloss, gloss_index)
            stats["pages_reprises"] += 1
        for cle in ("ajouts", "fusions", "conflits"):
            stats[cle] += ajouts[cle]
        nouvelle = glossary.to_sectioned(gloss)
        if nouvelle != empreinte:
            # ⚠ `dry` n'empêche PAS l'écriture parce qu'aucun appel LLM n'a eu lieu — il peut
            # n'y en avoir eu aucun et le glossaire avoir changé quand même : re-fusionner
            # des notes DÉJÀ en cache suffit (mesuré sur manga A Vol.2,
            # 150 planches reprises, 23 fusions, un `termes_source` de plus). Il l'empêche
            # parce que l'APPELANT le demande — cf. le call site, qui ne le pose que pour le
            # mode `glossaire_seul`, seul mode où le glossaire est la seule sortie du run.
            if not dry:
                glossary.save(gloss, gloss_path)
            empreinte = nouvelle
            modifie = True
    return True, modifie


def _appliquer_reflexion_lot(config: dict, reporter=None) -> None:
    """Reporte `manga.lot.think` / `thinking_budget` sur l'agent `manga_traducteur`.

    Passe par la SPEC DU MODÈLE (`manga.modeles.manga_traducteur`) et non par `manga.llm` :
    `core.agents.build_agents` accepte `think` et `thinking_budget` **en ligne** dans la spec,
    et c'est le seul niveau qui vise le traducteur SEUL. Les poser sous `manga.llm` les
    donnerait aussi au terminologue, au glossariste et aux onomatopées — trois agents dont le
    coût de raisonnement n'a aucune raison de suivre la taille du lot.

    Pourquoi ici plutôt que dans `run_manga.py` : l'interface graphique appellera
    `process_volume` sans passer par la CLI, et un réglage qui ne vaudrait qu'en ligne de
    commande serait un réglage à moitié implémenté.

    ⚠ **Clé ABSENTE ≠ `false`.** C'est un outrepassement : dès que `manga.lot.think` existe,
    il écrase la spec du modèle ET son `endpoint:`. `config.yaml` la livre donc commentée.
    Livrée à `false`, elle désactivait en silence l'indirection `endpoint: reflexion` du
    traducteur — le défaut exact que le lot 2.2 avait corrigé, et que
    `tests/test_manga_runtime.py` surveille (deux agents sur deux endpoints doivent avoir deux
    clients distincts). Un `false` explicitement écrit reste, lui, un choix légitime : couper
    le raisonnement pour ce tome-ci quel que soit l'endpoint."""
    lot_cfg = (config.get("manga") or {}).get("lot") or {}
    if "think" not in lot_cfg:
        return
    modeles = (config.get("manga") or {}).get("modeles") or {}
    spec = modeles.get("manga_traducteur")
    if spec is None:
        return
    if not isinstance(spec, dict):                  # forme courte « modèle: "nom" »
        spec = {"model": spec}
        modeles["manga_traducteur"] = spec
    spec["think"] = lot_cfg["think"]
    if "thinking_budget" in lot_cfg:
        spec["thinking_budget"] = int(lot_cfg["thinking_budget"])
    if reporter is not None and lot_cfg["think"] not in (False, "none"):
        reporter.info(f"[traduction] raisonnement du traducteur : {lot_cfg['think']} "
                      f"(budget {spec.get('thinking_budget', 'hérité')} tokens)")


# Au-delà, le prompt cesse d'être un lot pour devenir un tome : la mesure du CHANGELOG (tome
# entier en un appel = 30 948 tokens) dit où est le mur, et 20 planches en sont le tiers.
MAX_PLANCHES_LOT = 20


def groupes_de_lot(pages: list[int], taille: int) -> list[list[int]]:
    """Découpe des planches à traduire en lots d'au plus `taille`, **sans franchir un trou**.

    ⚠ La contiguïté n'est pas un raffinement. `_contexte_precedent` et le prompt de lot
    reposent tous deux sur le fait que les planches d'un lot se suivent : sur une reprise
    partielle où seules les planches 1, 2, 40 et 41 sont à traduire, un lot {1,2,40,41}
    présenterait au modèle quatre planches comme une scène continue. Un trou ferme donc le
    lot en cours, quel que soit le nombre de planches déjà dedans."""
    if taille <= 1:
        return [[p] for p in pages]
    groupes: list[list[int]] = []
    for p in sorted(pages):
        if groupes and len(groupes[-1]) < taille and p == groupes[-1][-1] + 1:
            groupes[-1].append(p)
        else:
            groupes.append([p])
    return groupes


def _image_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _bbox_des_styles(styles: list | None, n: int) -> list[tuple | None]:
    """Les bbox exploitables des `n` premières bulles — `None` là où le style n'est pas `ok`.

    ⚠ C'est ce qui permet à la traduction par LOTS d'exister : un `BubbleStyle` porte
    `interior` et `text_mask`, deux masques booléens **pleine page**. Retenir les styles de 20
    planches pour construire un seul prompt représenterait ~350 Mo de masques, alors que le
    prompt n'a besoin que de quatre entiers par bulle. On extrait donc les bbox planche par
    planche, et on laisse les styles se faire ramasser."""
    sorties: list[tuple | None] = []
    for i in range(n):
        st = styles[i] if styles and i < len(styles) else None
        sorties.append(tuple(st.bbox) if st is not None and getattr(st, "ok", False) else None)
    return sorties


def _lignes_gabarits(bboxes: list[tuple | None], *, depart: int = 1,
                     sources: list[str] | None = None, langue: str = "jp",
                     pack=None) -> list[str]:
    """Lignes « N. LxH px — viser ≤ B caractères », numérotées à partir de `depart`.

    `depart` est ce qui rend la fonction réutilisable par le lot : la numérotation y est
    CONTINUE d'une planche à l'autre, et les gabarits doivent suivre les répliques.

    ⚠ `sources` et `langue` ne sont pas décoratifs et la signature a dû changer pour eux : sans
    la source, le budget d'une bulle à source latine est celui du japonais, c'est-à-dire trois
    fois trop large (cf. `budget_caracteres`).

    ⚠ `pack` non plus : le gabarit lui-même est un fragment de message, donc une consigne de
    langue cible (`consignes.GABARIT_LIGNE`). Il était en dur, et il partait en français au
    milieu d'un run anglais."""
    lignes = []
    for k, bbox in enumerate(bboxes):
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        source = sources[k] if sources and k < len(sources) else ""
        lignes.append(consignes.texte(
            pack, "manga_gabarit_ligne", numero=depart + k,
            largeur=x1 - x0, hauteur=y1 - y0,
            budget=traduction_unitaire.budget_caracteres(bbox, source, langue)))
    return lignes


@dataclass
class PlancheLot:
    """Une planche telle qu'elle entre dans un lot de traduction.

    Ne porte QUE ce que le prompt consomme : le japonais OCR, les bbox (cf.
    `_bbox_des_styles`), la structure de la planche et, en mode vision seulement, l'image déjà
    encodée.

    ⚠ `structure` est un objet MINUSCULE — trois listes de `len(regions)` entiers ou chaînes —
    et c'est ce qui permet de le retenir pour vingt planches là où les `BubbleStyle` ne
    pouvaient pas l'être (cf. `_bbox_des_styles` : ~350 Mo de masques pleine page). Le calcul,
    lui, se fait planche par planche, sur des masques qu'on relâche aussitôt."""
    index: int                          # numéro de planche dans le tome (1-indexé)
    textes_jp: list[str]
    bboxes: list[tuple | None] = field(default_factory=list)
    image_b64: str | None = None
    structure: "planche_mod.Structure | None" = None


# Vérification faite UNE fois par processus : `/api/ps` est un appel réseau, et la réponse ne
# change pas d'un lot à l'autre.
_NUM_CTX_VERIFIE: set = set()


def _verifier_num_ctx(agent, declare: int, reporter) -> None:
    """Compare `llm.num_ctx` à ce que le serveur sert RÉELLEMENT, et le dit si ça diverge.

    ⚠ Une valeur déclarative fausse est pire qu'absente : c'est elle qui autorise le
    dépassement. La 1.1.0 annonçait 65 536 pour un serveur à 32 768, et `place_disponible`
    croyait donc disposer du double du contexte réel. Comme Ollama ne dégrade pas — il jette
    silencieusement plus de la moitié du prompt — le lot débordait sans un mot, et le défaut
    n'apparaissait qu'au rapport, sous forme de planches vides.

    Best-effort : un serveur muet ou un Ollama trop ancien ne dit rien, et on garde la valeur
    déclarée. Ne lève jamais — un garde-fou qui casse un run de nuit serait pire que le
    défaut qu'il surveille."""
    llm = getattr(agent, "llm", None)
    modele = getattr(agent, "modele", None)
    if llm is None or not modele:
        return
    cle = (getattr(llm, "base_url", None) or str(llm), modele)
    if cle in _NUM_CTX_VERIFIE:
        return
    _NUM_CTX_VERIFIE.add(cle)
    try:
        reel = power.contexte_charge(str(getattr(llm, "base_url", "")), modele)
    except Exception:
        return
    if reel and abs(reel - declare) > max(512, declare // 20):
        reporter.warn(
            f"[llm] `llm.num_ctx` annonce {declare} mais « {modele} » est chargé avec "
            f"{reel} tokens de contexte. Les garde-fous de lot raisonnent sur la valeur "
            f"DÉCLARÉE : corrige-la dans config.yaml, ou remonte le num_ctx du Modelfile. "
            f"Un dépassement n'échoue pas — Ollama tronque le prompt en silence.")


def _translate_lot(planches: list[PlancheLot], agent, *, gloss_text: str = "",
                    precedentes: list[str] | None = None, contexte_oeuvre: str = "",
                    plafond: int = quality_manga.PLAFOND_PLANCHE, num_ctx: int = 0,
                    stats: dict | None = None, reporter=None,
                    langue: str = "jp", sens: str = "droite_gauche",
                    pack=None, max_retries: int = 1, ratio_court: dict | None = None,
                    replier=None) -> dict[int, tuple[list[str], str | None, str]]:
    """Traduit PLUSIEURS planches en un seul appel. Renvoie `{planche: (répliques, motif,
    stratégie)}` — le même triplet que `_translate_page`, pour que l'aval ne change pas.

    ## La numérotation reste PLATE

    Le modèle numérote 1..N sur tout le lot, les planches n'étant que des séparateurs dans la
    liste. C'est le choix qui coûte le moins cher en risque : `analyser_numerotation`,
    `repliques_par_bulle`, `sans_prefixe` et les six motifs de `quality_manga` continuent de
    lire exactement la forme qu'ils lisent depuis la 0.24.0 — seule la LONGUEUR change. Une
    numérotation à deux niveaux (« 3.2 ») aurait demandé une seconde expression régulière,
    c'est-à-dire une jumelle libre de diverger de celle qui décide du retry (cf. le
    commentaire de `_LIGNE_NUM`). La redistribution est ensuite purement arithmétique :
    `quality_manga.decouper_par_planche`.

    ## Le repli est PAR PLANCHE, et c'est ce qui rend le lot sûr

    Un lot n'est jamais retenté en entier : ce serait annuler son gain pour une seule planche
    fautive. À la place, `replier(planche)` refait la planche SEULE par le chemin nominal
    (`_translate_page`, avec son retry en température et son contexte propre). Le lot devient
    ainsi une pure optimisation — au pire on retombe sur le coût et le résultat de la 1.0.0,
    planche par planche, jamais sur un résultat de moindre qualité.

    Deux déclencheurs de repli :

    · **le lot entier**, si la reconstruction est `positionnelle` — le modèle n'a numéroté
      aucune ligne, et rattacher 130 répliques à leurs bulles par leur seul ordre est
      indéfendable là où c'était déjà le pire cas sur une planche isolée ;
    · **une planche**, s'il lui manque une réplique dont la source PORTE du texte. Le test
      passe par `source_rattrapable` plutôt que par « la tranche est pleine » : une bulle dont
      l'OCR vaut `（）` est vide à raison, et refaire une planche entière pour elle serait un
      appel payé pour rien — que le rattrapage unitaire refuserait de toute façon ensuite.

    ## Et depuis le lot 15, un TROISIÈME chemin, en amont des deux autres

    Le lot avait deux manques que la planche seule n'avait pas.

    · **Aucun retry en température.** `_translate_page` et `_translate_sfx` passent tous deux
      par `try_with_temp_retry` — seul remède documenté aux boucles dégénérées, avec un
      `MOTIFS_PLUS_CHAUD` qui *relève* la température parce que « sur une boucle dégénérée,
      resserrer le modèle renforce le cycle au lieu de le casser ». Le lot faisait un unique
      `agent.run` suivi d'un unique diagnostic. Il tombait donc directement sur le repli, qui
      **rejoue la numérotation** — c'est-à-dire exactement ce qui vient d'échouer, et
      `config.yaml` mesure que c'est ce qui échoue à nouveau. Le lot mérite le même
      traitement : une seconde tentative à température corrigée coûte UN appel de lot, contre
      vingt appels de planche pour le repli.
    · **Un garde-fou de prefill purement consultatif.** `place_disponible` avertissait et
      continuait — or Ollama « ne dégrade pas : il jette silencieusement plus de la moitié du
      prompt ». Un lot trop gros produisait donc des planches vides après un `warn` dans
      `perf.log`. Avec les ajouts de ce lot (structure, types, locuteurs, étiquettes
      d'origine) le prompt grossit ; l'avertissement devient donc un **repli automatique sur
      un lot plus petit** — le lot est coupé en deux et chaque moitié refaite. Pas un échec
      dur : cela trahirait l'intention d'origine (« un garde-fou qui casse un run de nuit
      serait pire que le défaut qu'il surveille »)."""
    utiles = [p for p in planches if p.textes_jp]
    resultats: dict[int, tuple[list[str], str | None, str]] = {
        p.index: ([], None, "vide") for p in planches if not p.textes_jp}
    if not utiles:
        return resultats
    if replier is None:
        raise ValueError("_translate_lot exige un `replier` : sans chemin de repli, une "
                         "planche fautive serait perdue au lieu d'être refaite seule.")
    if len(utiles) == 1:
        p = utiles[0]
        resultats[p.index] = replier(p.index)
        return resultats

    # ── Prompt : numérotation continue, planches marquées par un séparateur ──────────────
    lignes_bulles: list[str] = []
    lignes_gabarits: list[str] = []
    sources: list[str] = []
    tailles = [len(p.textes_jp) for p in utiles]
    depart = 1
    for p in utiles:
        fin = depart + len(p.textes_jp) - 1
        lignes_bulles.append(consignes.texte(pack, "manga_separateur_planche",
                                             planche=p.index, debut=depart, fin=fin))
        lignes_bulles += planche_mod.lignes_bulles(p.textes_jp, p.structure,
                                                   depart=depart, pack=pack)
        lignes_gabarits += _lignes_gabarits(p.bboxes, depart=depart,
                                            sources=p.textes_jp, langue=langue, pack=pack)
        sources += list(p.textes_jp)
        depart = fin + 1
    n_total = len(sources)
    numbered = "\n".join(lignes_bulles)
    # Liste SANS séparateurs : c'est la forme que la réponse doit avoir. Elle sert de
    # `dry_payload` (en dry-run, l'agent renvoie sa charge telle quelle — les séparateurs y
    # seraient recollés à la réplique précédente par `analyser_numerotation`, qui traite une
    # ligne non numérotée comme une continuation) et de base au plafond de sortie, qui mesure
    # ce que la réponse va peser, pas ce que l'énoncé pèse.
    numbered_plat = "\n".join(f"{k + 1}. {t}" for k, t in enumerate(sources))

    parts = []
    if gloss_text:
        parts.append(gloss_text)
    if contexte_oeuvre:
        parts.append(contexte_oeuvre)
    # UNE note de lecture pour tout le lot : elle décrit une convention d'écriture, pas une
    # planche. La payer par planche multiplierait par vingt un coût qui n'apporte rien.
    note = planche_mod.note_de_lecture([p.structure for p in utiles], pack=pack)
    if note:
        parts.append(note)
    if precedentes:
        parts.append(consignes.texte(pack, "manga_precedentes_entete") + "\n"
                     + "\n".join(t for t in precedentes if t.strip()))
    if lignes_gabarits:
        parts.append(consignes.texte(pack, "manga_gabarits_entete") + "\n"
                     + "\n".join(lignes_gabarits))
    # ⚠ APPARIEMENT image ↔ planche. La ligne était `[p.image_b64 for p in utiles if
    # p.image_b64]` : le filtre RETIRE des éléments de la liste, si bien qu'une seule planche
    # à `image_b64` nul décalait toutes les suivantes — l'image *k* ne correspondait plus à la
    # planche *k*, et rien dans le texte ne les reliait de toute façon. En vision la taille de
    # lot est écrêtée à `planches_vision`, donc le désalignement portait sur au plus quatre
    # planches, ce qui suffit à mettre les répliques dans les mauvaises bulles.
    #
    # ⚠ Pourquoi on ne met PAS `None` dans la liste, comme on pourrait le croire : `images` est
    # transmise telle quelle au client LLM, qui en attend des charges base64. Un `None` y
    # serait une erreur d'API, pas un trou. La liste reste donc filtrée — et chaque image est
    # NOMMÉE dans le texte, ce qui rend l'appariement explicite au lieu de positionnel, donc
    # juste quelles que soient les planches sans image.
    imagees = [p for p in utiles if p.image_b64]
    images = [p.image_b64 for p in imagees]
    if images:
        parts.append("\n".join(
            consignes.texte(pack, "manga_image_planche", rang=r, planche=p.index)
            for r, p in enumerate(imagees, start=1)))
        if reporter is not None and len(imagees) != len(utiles):
            reporter.warn(
                f"[traduction] lot planches {utiles[0].index}→{utiles[-1].index} : "
                f"{len(utiles) - len(imagees)} planche(s) sans image alors que le mode vision "
                f"est actif — les images jointes sont nommées, mais ces planches sont "
                f"traduites sans contexte visuel")
    parts.append(
        consignes.texte(pack, "manga_lot_consigne",
                        planches=len(utiles), bulles=n_total) + "\n"
        + consignes.texte(pack, "manga_bulles_entete",
                          langue=glossary_lang.nom_langue(langue),
                          ordre=consignes.libelle_ordre(sens, pack)) + "\n" + numbered)
    user = "\n\n".join(parts)

    cap = quality_manga.bubbles_cap_lot(numbered_plat, n_total, plafond)

    # Garde-fou de PREFILL — la mesure qui avait fait écarter le tome-en-un-appel, cette fois
    # calculée à chaque lot au lieu d'être supposée une fois pour toutes.
    #
    # ⚠ Il ne se contente plus d'avertir. Ollama ne dégrade pas — il jette silencieusement plus
    # de la moitié du prompt — donc « avertir et continuer » revenait à produire des planches
    # vides après un `warn` que personne ne lit avant le rapport. On COUPE le lot en deux et on
    # refait chaque moitié : le pire cas reste le repli planche par planche, qui est le
    # comportement de la 1.0.0.
    if num_ctx > 0:
        if reporter is not None:
            _verifier_num_ctx(agent, num_ctx, reporter)
        reste = quality_manga.place_disponible(tokens.estimate(user), cap, num_ctx)
        if reste < 0 and len(utiles) > 1:
            milieu = len(utiles) // 2
            if reporter is not None:
                reporter.warn(
                    f"[traduction] lot planches {utiles[0].index}→{utiles[-1].index} : le "
                    f"prompt (~{tokens.estimate(user)} tok) + la sortie ({cap} tok) dépassent "
                    f"de {-reste} tokens les 85 % de num_ctx ({num_ctx}) — lot coupé en deux "
                    f"({milieu} + {len(utiles) - milieu}) plutôt que tronqué en silence par "
                    f"le serveur ; baisse `manga.lot.planches` ou monte le num_ctx du "
                    f"Modelfile pour éviter ce découpage")
            if stats is not None:
                stats["lots_coupes"] = stats.get("lots_coupes", 0) + 1
            for moitie in (utiles[:milieu], utiles[milieu:]):
                resultats.update(_translate_lot(
                    moitie, agent, gloss_text=gloss_text, precedentes=precedentes,
                    contexte_oeuvre=contexte_oeuvre, plafond=plafond, num_ctx=num_ctx,
                    stats=stats, reporter=reporter, langue=langue, sens=sens, pack=pack,
                    max_retries=max_retries, ratio_court=ratio_court, replier=replier))
            return resultats

    def _call(temperature):
        return agent.run(user, dry_payload=numbered_plat, max_tokens=cap,
                         temperature=temperature, images=images or None)

    def _diagnostic_de_lot(sortie: str) -> str | None:
        """Le diagnostic de `quality_manga`, moins ce qu'un retry de lot ne peut pas gagner.

        ⚠ Un seul écart, et il est la raison pour laquelle cette fonction existe :
        `bulles_manquantes` répond dès qu'UN numéro manque, y compris quand la bulle
        correspondante est vide **à raison** — un OCR qui vaut `（）` n'a rien à traduire. Sur
        une planche seule, retenter pour elle coûte un appel court ; sur un lot de vingt, cela
        coûte le lot entier, pour un trou que le rattrapage unitaire refuserait de toute façon
        de combler. C'est exactement le critère que le repli par planche applique déjà, dix
        lignes plus bas, avec `source_rattrapable`.

        Tous les autres motifs passent inchangés : une sortie vide, une source recopiée ou une
        boucle dégénérée méritent leur seconde chance à température corrigée, et c'est le seul
        remède documenté aux boucles dégénérées."""
        motif = quality_manga.diagnostiquer(sortie, n=n_total, cap=cap, sources=sources,
                                            langue=langue, ratio_court=ratio_court)
        if motif != "bulles_manquantes":
            return motif
        rendues = quality_manga.lignes_numerotees(sortie, n_total)
        rattrapables = any(not (rendues.get(k + 1) or "").strip()
                           and quality_manga.source_rattrapable(src)
                           for k, src in enumerate(sources))
        return motif if rattrapables else None

    # ⚠ Compteurs à part, puis report SÉLECTIF. Le moteur de retry incrémente `pages_ok` ou le
    # motif d'échec — or le lot les compte lui-même, PAR PLANCHE, une trentaine de lignes plus
    # bas (c'est ce que le rapport doit lire : un lot de 20 dont une planche déraille n'est pas
    # vingt planches en échec). Les lui laisser écrire ici les compterait deux fois, sur deux
    # dénominateurs différents. Seuls les compteurs de retry, qui décrivent l'APPEL et non les
    # planches, remontent.
    compteurs: dict = {}
    # ⚠ UNE seule seconde tentative, quoi que dise `llm.max_retries` — qui vaut 2 dans la
    # configuration livrée et gouverne le chemin par planche. L'asymétrie est voulue : sur une
    # planche, une relance coûte un appel court ; sur un lot de vingt, elle coûte la
    # génération de cent trente répliques, et le budget de raisonnement avec. Deux relances de
    # lot feraient jusqu'à trois générations perdues avant même d'atteindre le repli, ce qui
    # annulerait le gain que le lot existe pour produire. Le commentaire de `manga.llm` dans
    # `config.yaml` tient le même raisonnement pour la même raison.
    raw, _ok, motif_lot = quality.try_with_temp_retry(
        _call, _diagnostic_de_lot, stats=compteurs, temperature=agent.temperature,
        max_retries=min(1, max(0, int(max_retries))), cle_ok="lots_ok",
        motifs_plus_chaud=quality_manga.MOTIFS_PLUS_CHAUD)
    if stats is not None:
        for cle in ("retry_temp_relevee", "retry_temp_reduite", "recupere_par_retry"):
            if compteurs.get(cle):
                stats[cle] = stats.get(cle, 0) + compteurs[cle]
    repliques, strategie_lot = quality_manga.repliques_par_bulle(raw, n_total)

    if strategie_lot in ("positionnelle", "vide"):
        if reporter is not None:
            reporter.warn(
                f"[traduction] lot planches {utiles[0].index}→{utiles[-1].index} : "
                f"{quality_manga.STRATEGIES[strategie_lot]} sur {n_total} bulles — lot "
                f"abandonné, les {len(utiles)} planches sont reprises une par une")
        if stats is not None:
            stats["lots_abandonnes"] = stats.get("lots_abandonnes", 0) + 1
        for p in utiles:
            resultats[p.index] = replier(p.index)
        return resultats

    if stats is not None:
        stats["lots"] = stats.get("lots", 0) + 1
    tranches = quality_manga.decouper_par_planche(repliques, tailles)
    for p, tranche in zip(utiles, tranches):
        manquantes = [k for k, t in enumerate(tranche)
                      if not (t or "").strip()
                      and quality_manga.source_rattrapable(p.textes_jp[k])]
        if manquantes:
            if reporter is not None:
                reporter.info(
                    f"[traduction] planche {p.index} : {len(manquantes)} réplique(s) "
                    f"manquante(s) dans le lot — planche reprise seule")
            if stats is not None:
                stats["planches_repliees"] = stats.get("planches_repliees", 0) + 1
            resultats[p.index] = replier(p.index)
            continue
        # Diagnostic PAR PLANCHE, sur ce qui va réellement être dessiné. `cap=0` neutralise
        # `emballement`, qui n'a de sens qu'au niveau du lot : c'est le lot qui a un plafond,
        # pas la tranche. On le repropage donc explicitement.
        reconstituee = "\n".join(f"{k + 1}. {t}" for k, t in enumerate(tranche))
        motif = quality_manga.diagnostiquer(reconstituee, n=len(tranche), cap=0,
                                            sources=p.textes_jp, langue=langue,
                                            ratio_court=ratio_court)
        if motif is None and motif_lot == "emballement":
            motif = "emballement"
        if stats is not None:
            cle = motif or "pages_ok"
            stats[cle] = stats.get(cle, 0) + 1
        resultats[p.index] = (tranche, motif, quality_manga.strategie_de_tranche(tranche))
    return resultats


def _libelle_ordre(sens: str, pack=None) -> str:
    """Délégué de `consignes.libelle_ordre`, conservé pour ses appelants et ses tests.

    Le texte a quitté cette fonction avec les neuf autres fragments du chemin manga (lot 15,
    L7.12) : il vit désormais dans `manga/consignes.py`, où un pack de langue cible peut le
    surcharger. Il partait sinon en français au milieu d'un run anglais."""
    return consignes.libelle_ordre(sens, pack)


def _translate_page(agent, image: Image.Image, texts_jp: list[str], mode_vision: bool,
                     gloss_text: str, *, styles: list | None = None,
                     precedentes: list[str] | None = None, stats: dict | None = None,
                     contexte_oeuvre: str = "",
                     langue: str = "jp", sens: str = "droite_gauche",
                     structure=None, regions: list | None = None,
                     mode_traduction: str = "texte", reporter=None, page: int = 0,
                     pack=None, ratio_court: dict | None = None,
                     max_retries: int = 1) -> tuple[list[str], str | None, str]:
    """Traduit les bulles d'une page. Renvoie `(répliques, motif_d_échec, stratégie)`.

    La `stratégie` dit COMMENT les répliques ont été rattachées à leurs bulles (cf.
    `quality_manga.STRATEGIES`) : une planche reconstituée positionnellement n'a pas la même
    valeur de preuve qu'une planche numérotée, et jusqu'ici rien ne le disait.

    Deux ajouts de contexte, tirés des mesures du tome :
      · **les dimensions de chaque bulle** — le prompt demande d'être bref mais ne dit jamais
        *à quel point* : 54 traductions dépassaient 90 caractères, donc débordaient ;
      · **les répliques de la page précédente**, pour la continuité du dialogue (un pronom ou
        un sujet implicite ne se désambiguïse pas sur une planche isolée).

    ## `structure` — ce que la planche sait d'elle-même (lot 15)

    Groupes de mise en page, types de bulle et étiquettes de locuteur (cf. `manga.planche`).
    `None`, ou une structure sans rien à dire, rend **exactement** l'énoncé de la 1.0.0 : c'est
    ce qui rend vérifiable le critère « le mode texte sans les nouvelles clés produit un
    résultat inchangé », par diff de `traduction.json` sur un tome entier.

    ## `mode_traduction` — la vision, enfin ciblée (L7.6)

    · `"texte"` — aucune image, le défaut ;
    · `"vision"` — la planche ENTIÈRE, sur toutes les planches du tome. C'est le coût maximal
      pour les 90 % de planches qui n'en ont pas besoin, donc en pratique un mode que personne
      n'active ;
    · `"cible"` — le premier passage est textuel ; **le diagnostic décide**. Une planche dont
      le premier essai déclenche un motif de `quality_manga.MOTIFS` est exactement une planche
      ambiguë : on la refait en joignant les **crops des groupes**, pas la planche. Un crop de
      groupe est cinq à dix fois plus léger qu'une planche et bien plus lisible pour un modèle
      vision, parce que le sujet occupe le cadre.

    ⚠ `"cible"` ne coûte rien sur une planche qui passe du premier coup, ce qui est le cas de
    la grande majorité — c'est ce qui rend la vision utilisable, donc utilisée."""
    if not texts_jp:
        return [], None, "vide"
    lignes = planche_mod.lignes_bulles(texts_jp, structure, pack=pack)
    numbered = "\n".join(lignes)
    # ⚠ Le `dry_payload` et le plafond de sortie se calculent sur la liste NUE, sans les
    # séparateurs de groupe ni les annotations : ils décrivent ce que la RÉPONSE va peser, et
    # la réponse ne reprend ni les groupes ni les étiquettes. C'est le même raisonnement que
    # `numbered_plat` côté lot.
    numbered_plat = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts_jp))

    parts = []
    if gloss_text:
        parts.append(gloss_text)
    # ⚠ EN DEUXIÈME POSITION, après le glossaire et avant les répliques précédentes. L'ordre
    # n'est pas cosmétique : la fiche est une consigne de VOIX (qui vouvoie qui, quel registre),
    # les répliques précédentes en sont des EXEMPLES. Une consigne qui suit ses exemples se lit
    # comme un commentaire sur eux. C'est déjà l'ordre du chemin par lots (`_translate_lot`).
    #
    # ⚠ Elle était déclarée au paramètre et JAMAIS lue ici — sur le chemin par défaut
    # (`manga.lot.planches: 1`), qui est celui que tout le monde emprunte : `groupes_de_lot`
    # rend des groupes d'une planche, le garde `len(groupe) > 1` n'est jamais franchi, et
    # `_translate_lot` — le seul consommateur — n'est même pas appelé. `_passe_contexte`
    # dépensait donc un appel LLM par tome pour écrire un `contexte.txt` que personne ne lisait.
    if contexte_oeuvre:
        parts.append(contexte_oeuvre)
    note = planche_mod.note_de_lecture([structure], pack=pack)
    if note:
        parts.append(note)
    if precedentes:
        # « planches » au pluriel : `manga.contexte.planches_precedentes` vaut 3 par défaut,
        # et le prompt en annonçait UNE. Le modèle recevait les répliques de N−3, N−2 et N−1
        # en croyant qu'elles venaient toutes de N−1 — sur un enchaînement de dialogue, c'est
        # exactement l'indication qui lui fait continuer une phrase qui n'existe pas. Le
        # chemin par lots avait le pluriel juste depuis toujours (`_translate_lot`).
        parts.append(consignes.texte(pack, "manga_precedentes_entete") + "\n"
                     + "\n".join(t for t in precedentes if t.strip()))
    gabarits = _lignes_gabarits(_bbox_des_styles(styles, len(texts_jp)), depart=1,
                                sources=texts_jp, langue=langue, pack=pack)
    if gabarits:
        parts.append(consignes.texte(pack, "manga_gabarits_entete") + "\n"
                     + "\n".join(gabarits))
    # La langue source est nommée dans le MESSAGE et non dans `prompts/manga_traducteur.md` :
    # ce prompt est le même pour toutes les œuvres, la langue non.
    parts.append(consignes.texte(pack, "manga_bulles_entete",
                                 langue=glossary_lang.nom_langue(langue),
                                 ordre=consignes.libelle_ordre(sens, pack)) + "\n" + numbered)
    user = "\n\n".join(parts)

    images = None
    if mode_vision:
        images = [_image_b64(image)]

    cap = quality_manga.bubbles_cap(numbered_plat, len(texts_jp))

    def _call(temperature):
        return agent.run(user, dry_payload=numbered_plat, max_tokens=cap,
                          temperature=temperature, images=images)

    raw, ok, motif = quality_manga.try_with_temp_retry(
        _call, n=len(texts_jp), cap=cap, sources=texts_jp, stats=stats,
        temperature=agent.temperature, langue=langue, ratio_court=ratio_court,
        max_retries=max_retries)

    # ── Mode « cible » : le diagnostic décide de joindre une image ───────────────────────
    #
    # ⚠ Une SEULE seconde tentative, et seulement si le texte seul a échoué. C'est ce qui
    # sépare ce mode de `"vision"` : le coût n'est payé que là où il achète quelque chose.
    if not ok and str(mode_traduction) == "cible" and images is None and image is not None:
        crops = _crops_de_groupes(image, regions, structure)
        if crops:
            if reporter is not None:
                reporter.info(
                    f"[traduction] page {page} : {quality_manga.libelle(motif, langue)} "
                    f"({motif}) — seconde tentative avec {len(crops)} crop(s) de groupe")
            if stats is not None:
                stats["vision_ciblee"] = stats.get("vision_ciblee", 0) + 1
            user_vision = user + "\n\n" + consignes.texte(pack, "manga_crops_entete")
            brut = agent.run(user_vision, dry_payload=numbered_plat, max_tokens=cap,
                             temperature=agent.temperature, images=crops)
            motif_vision = quality_manga.diagnostiquer(brut, n=len(texts_jp), cap=cap,
                                                       sources=texts_jp, langue=langue,
                                                       ratio_court=ratio_court)
            if motif_vision is None:
                if stats is not None:
                    stats["vision_ciblee_recuperee"] = (
                        stats.get("vision_ciblee_recuperee", 0) + 1)
                    # Le compteur d'échec posé par `try_with_temp_retry` décrivait une planche
                    # qui, finalement, est passée : on le reprend, sans quoi le rapport
                    # annoncerait un échec ET une planche correcte pour la même planche.
                    if stats.get(motif):
                        stats[motif] -= 1
                    stats["pages_ok"] = stats.get("pages_ok", 0) + 1
                raw, motif = brut, None

    repliques, strategie = quality_manga.repliques_par_bulle(raw, len(texts_jp))
    return repliques, motif, strategie


#: Nombre maximal de crops joints par le mode « cible ». Au-delà, on a rejoint le coût d'une
#: planche pleine page sans en avoir la lisibilité — autant repasser en `"vision"`.
MAX_CROPS_CIBLE = 4


def _crops_de_groupes(image: Image.Image, regions: list | None, structure) -> list[str]:
    """Les crops des groupes d'une planche, encodés, prêts pour `agent.run(images=…)`.

    Renvoie `[]` — donc « pas de seconde tentative » — quand il n'y a pas de structure, ou
    quand la planche ne fait qu'un seul groupe : y joindre « le crop du groupe » reviendrait
    à joindre la planche entière, c'est-à-dire à faire du `"vision"` sous un autre nom."""
    if image is None or not regions or structure is None:
        return []
    boites = planche_mod.boites_de_groupes(regions, structure, image.size)
    if len(boites) < 2:
        return []
    return [_image_b64(image.crop(b)) for b in boites[:MAX_CROPS_CIBLE]]


CONTEXTE_FILENAME = "contexte.txt"


def _passe_contexte(agent, build_dir, *, total: int, gloss_text: str, budget_entree: int,
                    max_tokens: int, reporter, dire=True, langue: str = "jp",
                    pack=None) -> str:
    """Fiche de contexte du TOME — registre, qui vouvoie qui, récurrences. Un seul appel.

    Distincte du glossaire, et c'est le point : le glossaire est un dictionnaire de termes, il
    ne dit rien du registre ni des rapports entre personnages. Or le traducteur travaille
    planche par planche et ne voit jamais le tome ; un vouvoiement qui bascule au milieu d'un
    volume se remarque immédiatement.

    Cache au niveau du TOME (`.checkpoints/contexte.txt`), sur le modèle de `terminologie.txt`
    au niveau de la planche : une chaîne vide est une réponse valide, distincte de l'absence de
    fichier — sans quoi un tome sans matière serait resoumis à chaque relance.

    ⚠ Entrée ET sortie bornées. Chaque token de la fiche est payé une fois PAR PLANCHE dans le
    prompt de traduction : sur 131 planches, 400 tokens de fiche coûtent 52 000 tokens de
    prefill. C'est le même arbitrage que `terminology.relever_page`."""
    chemin = Path(build_dir) / ".checkpoints" / CONTEXTE_FILENAME
    if chemin.exists():
        return chemin.read_text(encoding="utf-8")
    if agent is None:
        return ""

    # Échantillon réparti sur tout le tome plutôt que sur ses premières planches : un registre
    # se juge sur l'ensemble, et un tome s'ouvre souvent sur des pages sans dialogue.
    morceaux: list[str] = []
    budget = 0
    for i in range(1, total + 1):
        textes = checkpoints.load_ocr(checkpoints.page_checkpoint_dir(build_dir, i))
        for t in textes or []:
            if not (t or "").strip():
                continue
            cout = tokens.estimate(t)
            if budget + cout > budget_entree:
                break
            morceaux.append(t.strip())
            budget += cout
        if budget >= budget_entree:
            break
    if not morceaux:
        return ""

    parts = []
    if gloss_text:
        parts.append(gloss_text)
    parts.append(consignes.texte(pack, "manga_echantillon_entete",
                                 langue=glossary_lang.nom_langue(langue))
                 + "\n" + "\n".join(morceaux))
    fiche = (agent.run("\n\n".join(parts), dry_payload="", max_tokens=max_tokens) or "").strip()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(fiche, encoding="utf-8")
    if dire and fiche:
        reporter.info(f"Contexte d'œuvre : fiche de {len(fiche.splitlines())} ligne(s) "
                      f"(~{tokens.estimate(fiche)} tokens), injectée dans chaque planche")
    return fiche


def _contexte_precedent(build_dir, page: int, planches: int, max_repliques: int,
                        gloss: dict | None = None, accord=None, *, pack=None) -> list[str]:
    """Les dernières répliques des `planches` planches qui PRÉCÈDENT celle-ci, **étiquetées**.

    Lu depuis les checkpoints plutôt que porté par une variable de boucle, et c'est ce qui
    corrige deux défauts d'un coup :

      · la variable n'était **pas réinitialisée sur une planche sautée** (`continue` du
        balayage B) — sur un run partiel, la planche 40 recevait le contexte de la 12 ;
      · elle partait **vide** sur `--page N` et sur toute reprise, alors que
        `page_{N-1}/traduction.json` est sur le disque depuis le premier run.

    Sans état, les trois cas (run complet, run partiel, planche isolée) donnent le même
    contexte — celui des planches réellement précédentes. Le coût est de quelques lectures de
    petits JSON par planche, à comparer aux ~9 s d'un appel de traduction.

    ## Le budget est réparti PAR PLANCHE, et non tronqué globalement (lot 15, L7.1)

    Le code concaténait les répliques des trois planches puis coupait `[-max_repliques:]`.
    L'ordre étant chronologique croissant, cette troncature garde la **fin** : sur une planche
    bavarde, elle gardait la fin de N−1 et **jetait entièrement N−3 et N−2**. Silencieusement.
    Le commentaire de `repliques_max` disait bien son intention — « plafond dur, pour qu'une
    planche bavarde ne gonfle pas le prompt » — mais pas cet effet de bord.

    On garde donc les *k* dernières de **chacune** des planches, `k` étant le budget divisé
    par leur nombre. On perd des répliques dans les deux cas ; on ne perd plus de planches
    entières, ce qui est la différence entre un contexte de scène et un contexte de page.

    ## Et chaque ligne dit d'où elle vient

    « Planche N−1 : … » plutôt qu'un tiret nu. Quelques tokens, et une liste plate redevient
    une séquence : le modèle sait quelles répliques sont récentes et lesquelles sont
    lointaines, donc laquelle une phrase peut prolonger.

    ⚠ Le forçage terminologique reste rejoué ici, et il doit le rester : le cache garde la
    sortie BRUTE du modèle, le forçage s'applique à l'usage et non à l'écriture (c'est ce qui
    permet de corriger le glossaire et de relancer `--from rendu` sans un appel LLM). Il est
    appliqué AVANT l'étiquetage, sur les répliques nues — les faire passer étiquetées y
    ferait entrer « Planche N−1 » dans le champ d'application du remplacement."""
    if planches <= 0 or max_repliques <= 0:
        return []
    debut = max(1, page - planches)
    numeros = list(range(debut, page))
    if not numeros:
        return []
    # Réparti, avec le reste donné aux planches les PLUS RÉCENTES : à budget non divisible,
    # c'est la planche N−1 qui mérite la réplique supplémentaire.
    base, reste = divmod(max_repliques, len(numeros))
    quotas = {p: base + (1 if i >= len(numeros) - reste else 0)
              for i, p in enumerate(numeros)}

    brutes: list[str] = []
    origines: list[int] = []
    for p in numeros:
        if quotas[p] <= 0:
            continue
        textes = checkpoints.load_traduction(checkpoints.page_checkpoint_dir(build_dir, p))
        retenues = [t for t in (textes or []) if t and t.strip()][-quotas[p]:]
        brutes += retenues
        origines += [p] * len(retenues)
    if not brutes:
        return []
    if gloss:
        brutes, _n, _refus = terminology.forcer_bulles(brutes, gloss, accord=accord)
    return [consignes.texte(
        pack, "manga_precedente_ligne",
        origine=consignes.texte(pack, "manga_origine_planche", ecart=page - p), texte=t)
        for t, p in zip(brutes, origines)]


def _styles_zones(styles_cache: list, garde: list[int], zones: list,
                  image=None, cfg_nettoyage: dict | None = None) -> list:
    """Le style hors bulle des zones GARDÉES, aligné par position sur `zones`.

    Deux sources, dans cet ordre, et la seconde n'est pas un luxe :

    1. `sfx.json` porte les styles depuis le lot 21 — mais **seulement pour les planches dont
       la passe `sfx` a tourné depuis**. Aucun cache du corpus n'en a, précisément parce que
       ce lot-là n'a rien invalidé. Un utilisateur qui arme l'effacement sur un tome déjà
       traité n'aurait donc aucune mesure, et `effacement.decider` rendrait `mesure_absente`
       sur toutes les zones : un mode armé qui ne fait rien, sans dire pourquoi.
    2. À défaut, la mesure est refaite ici sur l'image d'ORIGINE. Elle coûte ~0,16 s par
       planche porteuse (mesure du lot 21, contre 1,5 s à 139 s pour l'inférence ONNX qui la
       précède) et **n'est faite que si l'effacement est armé** — `image=None` la coupe.

    ⚠ Le repli n'écrit rien dans le cache. Persister une mesure faite au rendu ferait
    diverger `sfx.json` de ce que la passe `sfx` y écrit, et c'est exactement le genre d'écart
    qui se paie une fois par tome au pire moment."""
    styles = [styles_cache[k] if k < len(styles_cache) else None for k in garde]
    if any(s for s in styles) or image is None or not zones:
        return styles
    return clean.analyser_zones_hors_bulle(image, zones, cfg_nettoyage)


def _zones_illisibles(zones: list, textes: list[str], verdicts: list[str]) -> list[dict]:
    """Les zones dont la lecture n'est pas concordante, pour le PSD (lot 22, L22.4 point 3).

    Elles reçoivent un calque vide et nommé, parce que ce sont **elles** que le letteur devra
    traiter à la main : celles qu'on a su lire sont déjà relettrées ou glosées. Sans seconde
    voie de lecture, c'est toute la liste — et le dire ainsi, planche par planche, vaut mieux
    que de le taire."""
    from .sfx_lecture import LECTURE_SURE
    out: list[dict] = []
    for k, zone in enumerate(zones or []):
        if (verdicts[k] if k < len(verdicts) else "") == LECTURE_SURE:
            continue
        out.append({"index": k, "bbox": list(zone.bbox),
                    "texte": textes[k] if k < len(textes) else ""})
    return out


def _sfx_non_rendu(ckpt_dir) -> bool:
    """La planche porte-t-elle des zones hors bulle que son dernier rendu ignorait ?

    Se lit en comparant `sfx.json` au `qa.json`, qui décrit ce que le rendu a réellement vu.
    C'est la seule façon de rattraper la PREMIÈRE activation de la passe sur un tome déjà
    rendu : les zones sont détectées et traduites au balayage A, mais `stages_to_redo` est
    retombé à `{"rendu"}` et l'écran de garde « page déjà générée » sautait la planche."""
    charge = checkpoints.load_sfx(ckpt_dir)
    if not charge or not charge[0]:
        return False
    qa = report_manga.load_page_qa(ckpt_dir)
    if qa is None:
        return True
    return len(qa.get("sfx") or []) != len(charge[0])


#: Nombre maximal de crops de zone joints à un appel d'onomatopées. Ces zones sont peu
#: nombreuses (338 sur le Vol.1, dont 289 seulement sont traduites), mais une planche
#: exceptionnelle ne doit pas faire exploser le prompt à elle seule.
MAX_CROPS_SFX = 8


#: Dossier des crops de zones à lecture douteuse (voie C, L21.3). Sous `build/`, donc
#: régénérable et hors du dépôt — les planches du corpus ne sont pas redistribuables.
DOSSIER_CROPS_SFX = "sfx_illisibles"


def _lire_sfx_vision(agent, image, zones: list, *, pack=None, langue: str = "jp",
                     max_crops: int = MAX_CROPS_SFX,
                     stats: dict | None = None) -> list[str]:
    """**Voie A** — faire LIRE les crops par le modèle vision. Liste alignée sur `zones`.

    C'est la voie la moins coûteuse en dépendances, parce que tout est déjà là : le client
    est OpenAI-compatible, le modèle `manga_onomatopees` est vision-capable, et
    `MangaAgent.run(..., images=…)` existe depuis le lot 15. Il n'y manquait que l'appel qui
    demande une **transcription** au lieu d'une traduction.

    ⚠ Le crop est **rectangulaire brut** (`ocr.region_rectangulaire`), jamais l'encre isolée.
    C'est une mesure du dépôt et non un goût : sur une zone hors bulle, l'encre nue donne
    `人間の場所．．．` (inventé) là où le crop brut donne `ああ．．．陽弥．．．` (correct), « parce
    que le masque retire justement les demi-teintes dont l'encodeur se sert ».

    ⚠ **Le résultat n'est pas une lecture de référence**, et il ne doit jamais être traité
    comme telle : un modèle vision généraliste hallucine sur une onomatopée aussi bien qu'un
    OCR de dialogue — c'est la même famille de défaut. Il ne sert qu'à être **confronté** à
    la lecture de `manga-ocr` (`sfx_lecture.verdict`). Deux voies qui s'accordent valent un
    signal ; une seule ne vaut rien, et le module le dit."""
    if agent is None or image is None or not zones:
        return []
    lot = list(zones)[:max_crops]
    crops = [ocr_mod.region_rectangulaire(z).bbox for z in lot]
    images = [_image_b64(image.crop(b)) for b in crops]
    user = "\n\n".join([
        consignes.texte(pack, "manga_sfx_lecture_entete",
                        langue=glossary_lang.nom_langue(langue), zones=len(images)),
        "\n".join(consignes.texte(pack, "manga_image_zone", rang=r)
                  for r in range(1, len(images) + 1)),
    ])
    # Plafond serré : une transcription de N zones ne dépasse pas quelques dizaines de
    # tokens. Le plafond de planche (2 048) laisserait un modèle qui déraille écrire une
    # dissertation, et c'est exactement ce qu'on cherche à ne pas payer deux fois.
    cap = max(64, 24 * len(images))
    if stats is not None:
        stats["lecture_appels"] = stats.get("lecture_appels", 0) + 1
    raw = agent.run(user, dry_payload="", max_tokens=cap, temperature=0.0, images=images)
    lues, _strategie = quality_manga.repliques_par_bulle(raw, len(images))
    # Réalignement sur `zones` : les zones au-delà de `max_crops` n'ont pas été soumises, et
    # une chaîne vide dit « pas de seconde voie » — `sfx_lecture.verdict` la traite comme
    # telle et rend `douteuse`, ce qui est le bon défaut.
    return list(lues) + [""] * (len(zones) - len(lues))


def _exporter_crops_sfx(image, zones: list, indices: list[int], dossier,
                        page: int, *, plafond: int = 0) -> list[str]:
    """**Voie C** — écrit le crop des zones `indices` et rend leurs noms de fichier.

    Le rapport liste déjà les onomatopées ; il ne fournit pas l'image, et c'est ce qui rend
    la liste inutilisable en pratique. Un dossier de crops transforme « il y a 260 zones de
    texte quelque part dans ce tome » en une planche-contact qu'un humain traite en une
    passe — dix secondes par zone au lieu de rouvrir la planche et de la chercher.

    ⚠ `plafond` borne le nombre de fichiers par tome. Un tome entier de zones douteuses fait
    des centaines d'images ; un dossier qu'on n'ouvre pas ne sert personne, et l'écrire coûte
    une écriture disque par zone."""
    from pathlib import Path
    dossier = Path(dossier)
    noms: list[str] = []
    if not indices or plafond <= 0:
        return noms
    dossier.mkdir(parents=True, exist_ok=True)
    for k in indices:
        if len(noms) >= plafond:
            break
        if k >= len(zones):
            continue
        boite = ocr_mod.region_rectangulaire(zones[k]).bbox
        nom = f"page_{page:04d}_z{k:02d}.png"
        try:
            image.crop(boite).save(dossier / nom)
        except OSError:
            continue      # un disque plein ne doit pas faire échouer un tome de traduction
        noms.append(nom)
    return noms


def _translate_sfx(agent, textes_jp: list[str], gloss_text: str, *,
                    image: Image.Image | None = None, zones: list | None = None,
                    vision: bool = False, pack=None,
                    stats: dict | None = None, langue: str = "jp",
                    sens: str = "droite_gauche", max_retries: int = 1) -> list[str]:
    """Traduit les zones de texte hors bulle. Renvoie une liste alignée par position.

    **Un appel SÉPARÉ de celui de la planche**, et c'est délibéré. Le contrat de
    numérotation des bulles tient à 127/127 sur le Vol.2 : y greffer une seconde liste
    reviendrait à risquer ce qui marche pour ce qui n'existe pas encore. Une liste, un
    ordre, aucun numéro partagé — le chemin nominal reste intact.

    Les garde-fous de `quality_manga` s'appliquent tels quels : une réponse qui recopie la
    source est diagnostiquée comme ailleurs.

    ## `vision` — l'onomatopée traduite SANS son image (lot 15, L7.7)

    C'était le cas le plus absurde du chemin manga : **une onomatopée est un dessin**. Le
    glyphe *est* le contenu — sa taille, son épaisseur, son inclinaison portent l'intensité —
    et cette fonction ne recevait même pas d'objet `Image`. Il n'existait que deux sites
    d'appel LLM avec image dans tout le dépôt, et tous deux joignaient une planche pleine page.

    Pire : l'OCR sur lequel la traduction s'appuie est celui dont le dépôt lui-même mesure
    qu'il hallucine (`config.yaml`, et `manga-ocr est un modèle de dialogue et hallucine sur
    une onomatopée stylisée`). La passe traduisait donc une lecture fausse, sans regarder
    l'original. C'est la raison honnête du défaut `mode: "rapport"` : elle détecte, lit,
    traduit, et n'écrit rien.

    ⚠ Le crop joint est **rectangulaire brut**, via `ocr.region_rectangulaire`, et pas l'encre
    isolée. C'est une mesure, pas un goût : ce module a déjà établi que pour le texte hors
    bulle le crop brut bat l'encre nue, parce que « `manga-ocr` est un ViT entraîné sur des
    imagettes de manga, traits d'origine et anti-crénelage compris » et que « le masque retire
    justement les demi-teintes dont l'encodeur se sert ». Ce qui vaut pour un ViT vaut a
    fortiori pour un modèle vision généraliste.

    ⚠ **N'en déduis pas que `mode: "rapport"` peut passer à autre chose.** La LECTURE est un
    problème ; le DESSIN en est un autre, et il reste hors périmètre. L'IA ne dessine jamais.
    """
    if not textes_jp:
        return []
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(textes_jp))
    parts = []
    if gloss_text:
        parts.append(gloss_text)
    parts.append(consignes.texte(pack, "manga_hors_bulle_entete",
                                 langue=glossary_lang.nom_langue(langue),
                                 ordre=consignes.libelle_ordre(sens, pack)) + "\n" + numbered)
    user = "\n\n".join(parts)
    cap = quality_manga.bubbles_cap(numbered, len(textes_jp))

    images = None
    if vision and image is not None and zones:
        # Un crop par zone, dans l'ORDRE de la liste numérotée : l'appariement est positionnel
        # et il est dit explicitement, sur le modèle de `_translate_lot`.
        crops = [ocr_mod.region_rectangulaire(z).bbox for z in zones[:MAX_CROPS_SFX]]
        images = [_image_b64(image.crop(b)) for b in crops]
        parts.insert(len(parts) - 1, "\n".join(
            consignes.texte(pack, "manga_image_zone", rang=r)
            for r in range(1, len(images) + 1)))
        user = "\n\n".join(parts)

    def _call(temperature):
        return agent.run(user, dry_payload=numbered, max_tokens=cap, temperature=temperature,
                          images=images)

    raw, _ok, _motif = quality_manga.try_with_temp_retry(
        _call, n=len(textes_jp), cap=cap, sources=textes_jp, stats=stats,
        temperature=agent.temperature, langue=langue, max_retries=max_retries)
    repliques, _strategie = quality_manga.repliques_par_bulle(raw, len(textes_jp))
    return repliques


_DEFAUTS_RATTRAPAGE = {
    "actif": True,
    # Au-delà, on ne rattrape RIEN. Ce n'est plus un trou dans une planche mais une planche
    # ratée, et la reprendre bulle par bulle serait une retraduction déguisée — au prix d'un
    # appel par bulle, sans le contexte de la planche qui fait la qualité de la traduction.
    "max_par_page": 3,
}


def _rattraper_bulles(agent, texts_jp: list[str], translated: list[str], *,
                      gloss_text: str = "", styles: list | None = None,
                      bboxes: list | None = None,
                      cfg: dict | None = None, stats: dict | None = None,
                      reporter=None, page: int = 0,
                      langue: str = "jp", pack=None) -> tuple[list[str], list[int], list[str]]:
    """Retraduit UNE À UNE les bulles laissées vides. Renvoie `(textes, rattrapées, refus)`.

    Le retry de page rejoue la numérotation, c'est-à-dire **exactement ce qui vient
    d'échouer** : sur le Vol.1, les deux retries de page ont échoué comme leur premier essai.
    L'escalade change donc de FORME D'APPEL et non de température — une bulle, une réponse,
    aucun numéro à se tromper. C'est aussi ce qui rend le rattrapage bon marché : trois appels
    courts pour tout un tome.

    Trois garde-fous, chacun tiré d'une mesure :
      · une source qui ne porte **aucun texte** n'est pas rattrapable (`（）`, page 8 bulle 1) ;
      · au-delà de `max_par_page`, on ne rattrape rien (cf. `_DEFAUTS_RATTRAPAGE`) ;
      · une réponse **diagnostiquée est rejetée**, jamais dessinée : une mauvaise réplique dans
        une bulle est pire qu'une bulle vide, qui est au moins signalée au rapport."""
    c = fusion(_DEFAUTS_RATTRAPAGE, cfg)
    textes = list(translated or [])
    trous = [i for i, source in enumerate(texts_jp or [])
             if i < len(textes) and not (textes[i] or "").strip()
             and quality_manga.source_rattrapable(source)]
    if not trous:
        return textes, [], []
    if len(trous) > int(c["max_par_page"]):
        if stats is not None:
            stats["rattrapage_abandonne"] = stats.get("rattrapage_abandonne", 0) + 1
        if reporter is not None:
            reporter.warn(f"[rattrapage] page {page} : {len(trous)} bulles vides sur "
                          f"{len(textes)} — au-delà de {c['max_par_page']}, la planche est à "
                          f"reprendre en entier (`--page {page} --from traduction`), pas bulle "
                          f"par bulle")
        return textes, [], []

    rattrapees: list[int] = []
    refus: list[str] = []
    for i in trous:
        source = texts_jp[i]
        # `bboxes` est la voie du LOT : il ne transporte pas de `BubbleStyle` (masques pleine
        # page, cf. `_bbox_des_styles`) mais les seules bbox, qui sont tout ce dont le prompt
        # unitaire a besoin.
        if bboxes is not None:
            boite = bboxes[i] if i < len(bboxes) else None
            st = None
        else:
            boite = None
            st = styles[i] if styles and i < len(styles) else None
        # Le prompt vit dans `manga/traduction_unitaire.py` : l'éditeur graphique appelle la
        # MÊME fonction pour son bouton « retraduire cette bulle ». Deux copies d'un prompt qui
        # porte trois garde-fous seraient deux jumelles libres de diverger.
        if st is not None and getattr(st, "ok", False):
            boite = st.bbox
        texte, motif = traduction_unitaire.traduire_bulle(
            agent, source, gloss_text=gloss_text, bbox=boite, langue=langue, pack=pack)
        if stats is not None:
            stats["rattrapage_appels"] = stats.get("rattrapage_appels", 0) + 1
        if motif is not None:
            refus.append(f"page {page} bulle {i + 1} — "
                         f"{quality_manga.LIBELLES_RATTRAPAGE[motif]}")
            if stats is not None:
                stats["rattrapage_refuse"] = stats.get("rattrapage_refuse", 0) + 1
            if reporter is not None:
                reporter.warn(f"[rattrapage] page {page} bulle {i + 1} : réponse rejetée — "
                              f"{quality_manga.LIBELLES_RATTRAPAGE[motif]} ; la bulle reste "
                              f"vide et signalée")
            continue
        textes[i] = texte
        rattrapees.append(i)
        if stats is not None:
            stats["rattrapees"] = stats.get("rattrapees", 0) + 1
        if reporter is not None:
            reporter.info(f"[rattrapage] page {page} bulle {i + 1} : « {textes[i][:50]} »")
    return textes, rattrapees, refus


def _parse_translations(raw: str, n: int) -> list[str]:
    """Délégué de `quality_manga.repliques_par_bulle`, conservé pour ses appelants.

    La lecture de la numérotation vivait ici en double du diagnostic, avec sa propre copie de
    l'expression régulière : deux jumelles libres de diverger, alors que le diagnostic décide
    de retenter et que la reconstruction décide de ce qui sera dessiné. Elles lisent désormais
    le même objet, dans `quality_manga`."""
    return quality_manga.repliques_par_bulle(raw, n)[0]


def _pages_perimees(build_dir: Path, page_paths: list[Path]) -> list[int]:
    """Planches dont `pages_out/` est plus ancien que L'UNE de leurs données.

    Délègue à `manga/etat_planches.py`, qui porte désormais la règle — la même question se
    posait ici et dans l'éditeur graphique, et deux réponses auraient fini par diverger sur ce
    qui compte comme « modifié ».

    ⚠ Cette version voit strictement plus de choses que la précédente, qui ne comparait qu'à
    `traduction.json`. L'éditeur n'écrit jamais là : une réplique corrigée à la main va dans
    `traduction_manuelle.json` et un bloc déplacé dans `mise_en_page.json`. Ces travaux-là ne
    périmaient donc aucun rendu, et l'archive continuait d'embarquer l'ancienne image sans un
    mot."""
    numeros = []
    for chemin in page_paths:
        try:
            numeros.append(int(chemin.stem.removeprefix("page_")))
        except ValueError:
            continue
    return etat_planches.planches_a_relettrer(build_dir, numeros)


def assemble_outputs(build_dir: Path, mcfg: dict, project: str, volume: str,
                     reporter=None, sens: str | None = None) -> list[str]:
    """Assemble les pages de `pages_out/` dans les formats demandés.

    `sens` vient de la surcouche de FORMAT (`manga.formats.sens_lecture`) : sans lui, un
    webtoon partait en `ComicInfo.xml` avec le drapeau `YesAndRightToLeft`, et les liseuses
    le paginaient à l'envers. Omis, il est relu de `projet.json` — c'est ce qui fait marcher
    `--assembler` seul, qui ne rescanne pas les sources.

    Extraite de l'ancien `_render_outputs` pour pouvoir être appelée **aussi à l'arrêt
    propre** — c'est le correctif du CBZ manquant — et par `run_manga.py --assembler`, qui
    n'exécute que cette étape.

    Journalisation explicite : l'absence de sortie était indiagnosticable. On dit ce qu'on
    écrit, combien de pages et quel poids ; et on dit aussi quand il n'y a rien à écrire."""
    build_dir = Path(build_dir)
    formats = (mcfg.get("rendu") or {}).get("formats", ["images"])
    rendu = mcfg.get("rendu") or {}
    page_paths = sorted((build_dir / "pages_out").glob("page_*.png"))

    def _dire(msg: str) -> None:
        if reporter is not None:
            reporter.info(msg)

    outputs: list[str] = []
    if not page_paths:
        _dire("Aucune page dans pages_out/ : rien à assembler.")
        return outputs

    # ⚠ Une page dont le RENDU est plus ancien que sa TRADUCTION est périmée : le CBZ
    # embarquerait un lettrage qui ne correspond plus au texte en cache. Mesuré sur le Vol.4 —
    # la planche 52 avait un rendu de 20:35 pour une traduction de 21:08, et l'archive livrée
    # portait donc une planche que plus personne n'avait vue.
    #
    # On ne refuse pas d'assembler : refuser laisserait l'utilisateur sans archive du tout.
    # On AVERTIT, en nommant les planches — c'est actionnable (`--page N --from rendu`), et
    # c'est la seule chose qui manquait.
    perimees = _pages_perimees(build_dir, page_paths)
    if perimees and reporter is not None:
        reporter.warn(
            f"[rendu] {len(perimees)} planche(s) dont le rendu est ANTÉRIEUR à leur "
            f"traduction : " + ", ".join(str(n) for n in perimees[:12])
            + (f" (+{len(perimees) - 12})" if len(perimees) > 12 else "")
            + " — l'archive va les embarquer telles quelles. "
              "`--from rendu` les remet d'accord.")

    if "cbz" in formats:
        cbz_path = build_dir / f"{project}_{volume}.cbz"
        comicinfo = render_manga.build_comicinfo(
            series=project, volume=volume, pages=len(page_paths),
            sens_lecture=(sens or (projet_mod.lire(build_dir) or {}).get("sens")
                          or rendu.get("sens_lecture", "droite_gauche")),
            langue=rendu.get("langue_iso", "fr"))
        render_manga.build_cbz(page_paths, cbz_path, comicinfo=comicinfo)
        mo = cbz_path.stat().st_size / (1024 * 1024)
        _dire(f"CBZ écrit : {cbz_path.name} ({len(page_paths)} pages, {mo:.1f} Mo)")
        outputs.append(str(cbz_path))

    if "pdf" in formats:
        pdf_path = build_dir / f"{project}_{volume}.pdf"
        render_manga.build_pdf(page_paths, pdf_path, dpi=int(rendu.get("pdf_dpi", 300)),
                               quality=int(rendu.get("pdf_qualite", 85)),
                               largeur_max=rendu.get("pdf_largeur_max"),
                               warn=(reporter.warn if reporter is not None else None))
        mo = pdf_path.stat().st_size / (1024 * 1024)
        _dire(f"PDF écrit : {pdf_path.name} ({len(page_paths)} pages, {mo:.1f} Mo)")
        outputs.append(str(pdf_path))

    if "images" in formats:
        outputs.append(str(build_dir / "pages_out"))
    # `pages_clean/` n'est une SORTIE que si les images sont demandées : il était annoncé en
    # tête de liste même quand seul le CBZ l'était.
    if "images" in formats:
        outputs.append(str(build_dir / "pages_clean"))
    # Les PSD sont écrits DANS la boucle (ils ont besoin des `Fit`) : ici on ne fait que les
    # annoncer, et seulement s'il y en a — `--assembler` seul n'en produit aucun.
    if "psd" in formats:
        dossier_psd = build_dir / "pages_psd"
        psd_paths = sorted(dossier_psd.glob("page_*.psd"))
        if psd_paths:
            mo = sum(p.stat().st_size for p in psd_paths) / (1024 * 1024)
            _dire(f"PSD à calques : {len(psd_paths)} planche(s) dans "
                  f"{dossier_psd.name}/ ({mo:.0f} Mo)")
            outputs.append(str(dossier_psd))
    return outputs
