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
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from core import config as core_config
from core import control, glossary, glossary_build, power, runtime, tokens
from core.version import ETAT_BRIQUES, __version__

from . import (bubbles_split, checkpoints, clean, detection, detection_retry,
               etat_planches, projet as projet_mod, psd, quality_manga, render_manga,
               report_manga, sources_manga, terminology, text_detection,
               traduction_unitaire, typeset)
from . import rendu
# ⚠ Alias obligatoire : `gloss` est déjà le nom du GLOSSAIRE chargé dans `process_volume`
# (`gloss = glossary.load(...)`). Importer le module sous son nom nu le masquait au premier
# appel de glose.
from . import gloss as gloss_mod
from . import ocr as ocr_mod
from .agents_manga import build_manga_agents


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
                   glossaire_seul: bool = False) -> bool:
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
                               glossaire_seul=glossaire_seul, _porteur=porteur)
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

    plan = sources_manga.scan_volume(vol_dir, build_dir)
    # `reporter.volume()` est propre au LN (langues/pivot/chapitres) : la brique manga
    # écrit son propre en-tête, avec la version et l'état de la brique — un tome de
    # 150 planches se relance des semaines plus tard, il faut savoir avec quoi.
    reporter.info(f"Angelith {__version__} (brique manga : {ETAT_BRIQUES['manga']})")
    reporter.info(f"{project} / {volume} — {len(plan.pages)} page(s), source : {plan.source_kind}")
    for w in plan.warnings:
        reporter.info(f"⚠ {w}")

    # ⚠ Bornes de `--page`, AVANT les deux balayages. `--page 999` ne traitait rien mais
    # allait quand même au bout : `RAPPORT.md` était réécrit et le CBZ réencodé, si bien
    # qu'une faute de frappe passait pour un run réussi. Un numéro hors bornes est une erreur
    # de commande, pas un tome vide.
    cibles, alertes, abandon = cibles_de_run(only_page, only_pages, len(plan.pages))
    for alerte in alertes:
        reporter.warn(alerte)
    if abandon:
        return False

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
    mode_vision = mcfg.get("mode_traduction", "texte") == "vision" and not dry_run

    det_cfg = mcfg["detection"]

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
            _lazy["det"] = detection.BubbleDetector(
                det_cfg["model_path"], providers=det_cfg.get("providers"),
                conf_threshold=det_cfg.get("conf_threshold", 0.35),
                iou_threshold=det_cfg.get("iou_threshold", 0.45),
                telechargement_auto=bool(det_cfg.get("telechargement_auto", True)),
                model_url=det_cfg.get("model_url") or None,
                # Le téléchargement passe par le reporter : 104 Mo en silence ressemblent à un
                # pipeline planté, et ces lignes atterrissent aussi dans perf.log.
                dire=reporter.info)
        return _lazy["det"]

    def get_reader():
        if "ocr" not in _lazy:
            _lazy["ocr"] = ocr_mod.MangaOCR(mcfg.get("ocr"), dire=reporter.info)
        return _lazy["ocr"]

    def get_text_detector():
        if "txt" not in _lazy:
            _lazy["txt"] = text_detection.TextDetector(
                sfx_cfg.get("model_path", "manga_models/text_detector.onnx"),
                providers=det_cfg.get("providers"),
                telechargement_auto=bool(sfx_cfg.get("telechargement_auto", True)),
                model_url=sfx_cfg.get("model_url") or None, dire=reporter.info)
        return _lazy["txt"]

    # Glossaire de l'œuvre — le MÊME fichier que le light novel (`sources/<Projet>/
    # glossaire.yaml`), ce qui garde les noms cohérents entre un roman et son manga. Il sert
    # à trois choses depuis le lot 3 :
    #   · injection en contexte du traducteur (préventif : les planches suivantes convergent) ;
    #   · forçage déterministe des entrées `force: true` sur les bulles rendues (curatif) ;
    #   · cible d'écriture du terminologue, s'il est configuré.
    gloss_path = sources_root / project / chemins.get("glossaire_fichier", "glossaire.yaml")
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
    sfx_actif = bool(sfx_cfg.get("actif", True)) and not glossaire_seul
    # "rapport" par défaut : on détecte, on lit, on traduit — et on n'écrit rien sur la
    # planche. La DÉTECTION est fiable, la LECTURE ne l'est pas (`manga-ocr` est un modèle de
    # dialogue et hallucine sur une onomatopée stylisée), et la règle de la brique est qu'une
    # mauvaise réplique dessinée est pire qu'une absence signalée.
    sfx_mode = str(sfx_cfg.get("mode", "rapport")).lower()
    agent_sfx = agents.get("manga_onomatopees")
    stats_sfx = {"zones": 0, "traduites": 0, "posees": 0, "pages": 0,
                 "actif": sfx_actif, "agent": agent_sfx is not None, "mode": sfx_mode,
                 "mobilier": 0, "groupes_mobilier": [], "tri": {}}
    sfx_refus: list[str] = []

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

    def _scinder(regions):
        return bubbles_split.scinder_regions(regions, scission_cfg)

    def _uniformites(image, regions, cfg_nettoyage) -> dict[int, float]:
        """Uniformité mesurée par le NETTOYEUR, par index de région — la mesure sur laquelle
        l'arbitre de relance s'adosse plutôt que d'inventer un second critère."""
        return {k: float(getattr(s, "uniformity", 0.0))
                for k, s in enumerate(clean.analyze_regions(image, regions, cfg_nettoyage))}

    # PSD à calques : produit DANS la boucle et non par `assemble_outputs`, parce qu'il a besoin
    # des `Fit` de la planche — que l'assemblage, qui ne voit que des pages finies, n'a pas.
    # C'est un format « dossier de pages », comme `"images"`, pas une archive.
    rendu_cfg = mcfg.get("rendu") or {}
    psd_actif = "psd" in (rendu_cfg.get("formats") or [])

    n_done = 0
    n_migrees = 0
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
            assemble_outputs(build_dir, mcfg, project, volume, reporter=reporter)
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
            migre = checkpoints.migrate_page(ckpt_dir, ocr_mod.reading_order, _scinder)
            if migre:
                n_migrees += 1
                if verbose:
                    reporter.verbose(f"[cache] page {i}/{total} migré : {migre}")

            # Étapes réellement à refaire, d'après le GRAPHE de dépendances (et non l'ordre
            # d'exécution) : `nettoyage` et `ocr` sont des frères, si bien que `--from nettoyage`
            # ne réinvalide plus l'OCR ni la traduction — ~38 min et tous les appels LLM
            # économisés sur une relance de tome. Cf. `checkpoints._DEPENDANTS`.
            a_refaire = checkpoints.stages_to_redo(ckpt_dir, clean_path, force=force,
                                                   restart_from=restart_from)
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
            reporter.stage(f"Page {i}/{total} — {page_path.name} ({', '.join(etapes_cv)})")
            image = Image.open(page_path).convert("RGB")

            if "detection" in a_refaire:
                t0 = time.perf_counter()
                # Scission AVANT l'ordre de lecture : celui-ci doit voir les vraies bulles, et
                # chaque ballon doit recevoir son propre texte à l'OCR. Cf. `manga/bubbles_split.py`.
                brutes = get_detector().detect(image, conf_threshold=conf_threshold,
                                               iou_threshold=iou_threshold)
                scindees, diag = _scinder(brutes)
                regions = ocr_mod.reading_order(scindees)
                provenance = None
                if seuils_ponctuels:
                    # Relance CIBLÉE : l'arbitre décide, et le doute profite à la détection en
                    # place — elle a déjà été payée en OCR et en traduction.
                    reference = checkpoints.load_regions(ckpt_dir) or []
                    verdict = detection_retry.arbitrer(
                        reference, regions,
                        _uniformites(image, regions, mcfg.get("nettoyage")),
                        seuil_abandon=float((mcfg.get("nettoyage") or {})
                                            .get("seuil_abandon", 0.35)),
                        uniformites_reference=_uniformites(image, reference,
                                                           mcfg.get("nettoyage")))
                    reporter.info(f"[detection] page {i} — arbitre : {verdict}")
                    if reference and not verdict.accepte:
                        reporter.warn(f"[detection] page {i} : seuils NON appliqués "
                                      f"({detection_retry.LIBELLES.get(verdict.motif, '?')}). "
                                      f"Le cache est intact ; `tools/apercu_detection.py "
                                      f"--balayage` montre ce qui marcherait.")
                        travail.pop(i, None)
                        continue
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
                checkpoints.save_regions(ckpt_dir, regions, image.size, detection=provenance)
                # Les diagnostics ne sont pas accumulés pour le rapport : celui-ci les relit dans
                # les `qa.json` de TOUTES les planches (via `region.scindee`, persisté dans
                # `regions.json`), et décrit donc le tome et non le run.
                for d in diag:
                    if d["type"] == "scindee":
                        reporter.warn(
                            f"[detection] page {i} : région bi-lobée scindée en {d['lobes']} "
                            f"(remplissage du masque {d['remplissage']:.2f} → "
                            + ", ".join(f"{x:.2f}" for x in d["remplissages_lobes"]) + ")")
                if verbose:
                    reporter.verbose(f"[detection] page {i}/{total} : {time.perf_counter() - t0:.2f}s "
                                     f"· {len(regions)} bulle(s)"
                                     + (f" (dont {len(brutes)} détectée(s), "
                                        f"{len(regions) - len(brutes)} par scission)"
                                        if len(regions) != len(brutes) else ""))
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
                masque = get_text_detector().masque_texte(
                    image, seuil=float(sfx_cfg.get("seuil_masque", text_detection.SEUIL_MASQUE)))
                zones = text_detection.hors_des_bulles(
                    masque, regions,
                    containment=float(sfx_cfg.get("containment_bulle",
                                                  text_detection.CONTAINMENT_BULLE)),
                    aire_min=int(sfx_cfg.get("aire_min", text_detection.AIRE_MIN)),
                    groupement=int(sfx_cfg.get("groupement", 0)))
                # DÉTECTION SEULE. La lecture attend le filtre de mobilier, qui a besoin des boîtes
                # de TOUT le tome pour décider — 63 % des zones du Vol.1 sont des filigranes de
                # scan, autant d'OCR et d'appels LLM à ne pas payer.
                checkpoints.save_sfx(ckpt_dir, zones, [], image.size, lu=False)
                if verbose:
                    reporter.verbose(f"[sfx] page {i}/{total} : {time.perf_counter() - t0:.2f}s "
                                     f"· {len(zones)} zone(s) détectée(s)")

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
                    checkpoints.save_sfx(ckpt_dir, zones, textes,
                                         charge["taille"] or (0, 0),
                                         mobilier=drapeaux, lu=True)
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
        termine, glo_modifie = _passe_terminologie(
            agent_term, gloss, gloss_index, build_dir=build_dir, total=total,
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
        max_tokens=int(contexte_cfg.get("max_tokens", 400)), reporter=reporter)

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

    def _traduire_planche_seule(p: int) -> tuple[list[str], str | None, str]:
        """Chemin nominal de la 1.0.0 pour UNE planche — et repli d'un lot.

        Relit l'image et recalcule les styles au lieu de les recevoir : le repli est rare, et
        les porter jusqu'ici obligerait à garder en mémoire les masques pleine page de toutes
        les planches du lot (cf. `_bbox_des_styles`)."""
        lot_effectif[p] = 1
        ck = checkpoints.page_checkpoint_dir(build_dir, p)
        img = Image.open(plan.pages[p - 1]).convert("RGB")
        st = clean.analyze_regions(img, checkpoints.load_regions(ck), mcfg.get("nettoyage"))
        return _translate_page(
            agents["manga_traducteur"], img, checkpoints.load_ocr(ck) or [],
            mode_vision=mode_vision, gloss_text=gloss_text, styles=st,
            precedentes=_contexte_precedent(build_dir, p, contexte_planches,
                                            contexte_repliques, gloss),
            contexte_oeuvre=contexte_oeuvre, stats=stats_trad,
            max_retries=int(llm_cfg_manga.get("max_retries", 1)))

    # ═══ Balayage B — traduction, forçage, lettrage, rendu ═══════════════════════════════
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

            motif_page = None
            strategie_page = ""
            rattrapees: list[int] = []
            if "traduction" in a_refaire:
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
                            img_p, styles_p = image, styles
                        else:
                            img_p = Image.open(plan.pages[p - 1]).convert("RGB")
                            styles_p = clean.analyze_regions(
                                img_p, checkpoints.load_regions(ck_p), mcfg.get("nettoyage"))
                        membres.append(PlancheLot(
                            index=p, textes_jp=textes_p,
                            bboxes=_bbox_des_styles(styles_p, len(textes_p)),
                            image_b64=_image_b64(img_p) if mode_vision else None))
                    reporter.stage(f"Lot planches {groupe[0]}→{groupe[-1]} "
                                   f"({sum(len(m.textes_jp) for m in membres)} bulles)")
                    # Posé AVANT l'appel : `_traduire_planche_seule` le ramènera à 1 pour chaque
                    # planche effectivement repliée.
                    for p in groupe:
                        lot_effectif[p] = len(groupe)
                    brut_lot = _translate_lot(
                        membres, agent, gloss_text=gloss_text,
                        precedentes=_contexte_precedent(build_dir, groupe[0], contexte_planches,
                                                        contexte_repliques, gloss),
                        contexte_oeuvre=contexte_oeuvre, plafond=plafond_lot,
                        num_ctx=num_ctx_declare, stats=stats_trad, reporter=reporter,
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
                                reporter=reporter, page=membre.index)
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
                        styles=styles,
                        precedentes=_contexte_precedent(build_dir, i, contexte_planches,
                                                        contexte_repliques, gloss),
                        contexte_oeuvre=contexte_oeuvre,
                        stats=stats_trad,
                        max_retries=int(llm_cfg_manga.get("max_retries", 1)))
                if motif_page:
                    # Tous les motifs, pas seulement le principal : une sortie à la fois
                    # incomplète ET japonaise était rapportée « numérotation incomplète », et le
                    # mot « japonais » n'apparaissait nulle part. Le retry, lui, continue de se
                    # décider sur le motif principal (cf. `diagnostiquer`).
                    autres = [m for m in quality_manga.motifs_repliques(translated)
                              if m != motif_page]
                    reporter.warn(
                        f"[traduction] page {i} : {quality_manga.LIBELLES[motif_page]} "
                        f"({motif_page})"
                        + (" · aussi : " + ", ".join(quality_manga.LIBELLES.get(m, m)
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
                        cfg=rattrapage_cfg, stats=stats_trad, reporter=reporter, page=i)
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
                # qui compte est le japonais recopié — invisible au rendu depuis la 0.24.0,
                # puisque ces caractères sont supprimés faute de glyphe.
                residus = [k + 1 for k, t in enumerate(translated or [])
                           if t and tokens.CJK_TEXTE.search(t)]
                if residus:
                    reporter.warn(
                        f"[traduction] page {i} : du japonais subsiste EN CACHE dans "
                        f"{len(residus)} bulle(s) ({', '.join(map(str, residus[:6]))}) — "
                        f"`--page {i} --from traduction` pour la reprendre")
                    motif_page = motif_page or "japonais_residuel"

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
                translated, n_forces, refus = terminology.forcer_bulles(translated, gloss)
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
            if sfx_actif:
                charge = checkpoints.load_sfx_complet(ckpt_dir)
                if charge is not None:
                    # Le mobilier de page est écarté ICI, une fois pour toutes : il ne doit
                    # atteindre ni la traduction, ni la glose, ni le rapport. Un filigrane traduit
                    # est du bruit partout où il passe.
                    tris = [text_detection.trier_zone(
                                charge["textes"][k] if k < len(charge["textes"]) else "",
                                mobilier=(charge["mobilier"][k:k + 1] or [False])[0])
                            for k in range(len(charge["regions"]))]
                    garde = [k for k, tri in enumerate(tris)
                             if tri in (text_detection.TRI_JAPONAIS,
                                        text_detection.TRI_PONCTUATION)]
                    zones_sfx = [charge["regions"][k] for k in garde]
                    textes_sfx = [charge["textes"][k] if k < len(charge["textes"]) else ""
                                  for k in garde]
                    tris_sfx = [tris[k] for k in garde]
                    for tri in tris:
                        stats_sfx["tri"][tri] = stats_sfx["tri"].get(tri, 0) + 1
                if zones_sfx and sfx_mode != "aucun":
                    # Seules les zones réellement japonaises partent au LLM. La ponctuation pure
                    # (`！！`, `．．．`) se rend déterministement — mieux qu'un modèle, qui
                    # broderait — et ne coûte rien.
                    a_traduire = [k for k, tri in enumerate(tris_sfx)
                                  if tri == text_detection.TRI_JAPONAIS]
                    deja = checkpoints.load_sfx_traduction(ckpt_dir)
                    # Retraduire seulement si le cache manque ou ne correspond plus au nombre de
                    # zones — sinon un `--from rendu` repaierait un appel LLM par planche.
                    if agent_sfx is not None and a_traduire and (
                            deja is None or len(deja) != len(zones_sfx)):
                        rendues = _translate_sfx(
                            agent_sfx, [textes_sfx[k] for k in a_traduire], gloss_text,
                            stats=stats_trad,
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
                        traductions_sfx, _n, _r = terminology.forcer_bulles(traductions_sfx, gloss)
                    stats_sfx["traduites"] += sum(1 for t in traductions_sfx if t.strip())

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
                mode_sfx=sfx_mode if sfx_actif else "")
            final_img = resultat.image
            rendu_qa.extend(resultat.qa)
            fits_qa.extend(resultat.fits)
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
                chemin_psd = psd.ecrire_planche(
                    checkpoints.psd_page_path(build_dir, i), finale=final_img,
                    nettoyee=fond_propre, fits=fits_qa,
                    originale=image if rendu_cfg.get("psd_original", True) else None,
                    mode_texte=mode_texte_psd,
                    dpi=int(rendu_cfg.get("pdf_dpi", 300)))
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
            for e in rendu_qa:
                if e["type"] == "ecart_comptage":
                    reporter.warn(f"[rendu] page {i} : {e['bulles']} bulle(s) mais "
                                  f"{e['traductions']} traduction(s) — écart de {e['ecart']}")
                elif e.get("overflow"):
                    # Le conseil dépend de la CAUSE : sur ce tome, « raccourcir la traduction »
                    # était donné neuf fois et n'était juste qu'une seule.
                    conseil = {
                        "bulle_degeneree": "région dégénérée (elle ne peut porter aucun mot) — "
                                           "NON lettrée, corriger la détection",
                        "bulle_etroite": "bulle trop étroite pour le mot le plus long — corriger "
                                         "la détection ou scinder la région",
                    }.get(e.get("cause", ""), "raccourcir la traduction")
                    reporter.warn(f"[rendu] page {i} bulle {e['index'] + 1} : ne tient pas dans "
                                  f"la bulle (dessiné à {e['taille']} px, non tronqué) — {conseil}")
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
        rattrapage_refus=rattrapage_refus or None, stats_sfx=stats_sfx,
        stats_manuelles=stats_manuelles, planches_en_echec=planches_en_echec or None)
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
        page_ckpt=checkpoints.page_checkpoint_dir))
    if verbose:
        reporter.verbose(f"[projet] {etat_projet.name} — révision "
                         f"{(projet_mod.lire(build_dir) or {}).get('revision', 1)}")

    outputs = assemble_outputs(build_dir, mcfg, project, volume, reporter=reporter)
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


def _passe_terminologie(agent, gloss: dict, gloss_index: dict, *, build_dir: Path, total: int,
                        a_relever: set[int], stats: dict, gloss_path: Path, reporter,
                        verbose: bool = False, ignorer_cache: bool = False,
                        dry: bool = False, arret=None) -> tuple[bool, bool]:
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
    for i in range(1, total + 1):
        if arret is not None and arret():
            return False, modifie
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
            notes, ajouts = terminology.relever_page(
                agent, gloss, gloss_index, page=i, total=total, texts_jp=texts_jp,
                deja_fr=checkpoints.load_traduction(ckpt_dir))
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


def _lignes_gabarits(bboxes: list[tuple | None], *, depart: int = 1) -> list[str]:
    """Lignes « N. LxH px — viser ≤ B caractères », numérotées à partir de `depart`.

    `depart` est ce qui rend la fonction réutilisable par le lot : la numérotation y est
    CONTINUE d'une planche à l'autre, et les gabarits doivent suivre les répliques."""
    lignes = []
    for k, bbox in enumerate(bboxes):
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        # Budget indicatif de caractères : une bulle tient ~2,2 caractères par pixel de
        # largeur et par ligne, à taille de police usuelle.
        surface = max(1, (x1 - x0)) * max(1, (y1 - y0))
        budget = max(12, int(surface / 320))
        lignes.append(f"{depart + k}. {x1 - x0}×{y1 - y0} px — viser ≤ {budget} caractères")
    return lignes


@dataclass
class PlancheLot:
    """Une planche telle qu'elle entre dans un lot de traduction.

    Ne porte QUE ce que le prompt consomme : le japonais OCR, les bbox (cf.
    `_bbox_des_styles`) et, en mode vision seulement, l'image déjà encodée."""
    index: int                          # numéro de planche dans le tome (1-indexé)
    textes_jp: list[str]
    bboxes: list[tuple | None] = field(default_factory=list)
    image_b64: str | None = None


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
      appel payé pour rien — que le rattrapage unitaire refuserait de toute façon ensuite."""
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
        lignes_bulles.append(f"— Planche {p.index} (bulles {depart} à {fin}) —")
        lignes_bulles += [f"{depart + k}. {t}" for k, t in enumerate(p.textes_jp)]
        lignes_gabarits += _lignes_gabarits(p.bboxes, depart=depart)
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
    if precedentes:
        parts.append("Répliques des planches précédentes (contexte, NE PAS retraduire) :\n"
                     + "\n".join(f"- {t}" for t in precedentes if t.strip()))
    if lignes_gabarits:
        parts.append("Place disponible par bulle (dépasser force une police illisible) :\n"
                     + "\n".join(lignes_gabarits))
    parts.append(
        f"{len(utiles)} planches consécutives, {n_total} bulles au total. La numérotation est "
        f"CONTINUE d'une planche à l'autre : rends exactement {n_total} lignes numérotées de 1 "
        f"à {n_total}, sans répéter les séparateurs de planche.\n"
        "Bulles détectées (ordre de lecture, droite → gauche puis haut → bas) :\n" + numbered)
    user = "\n\n".join(parts)

    images = [p.image_b64 for p in utiles if p.image_b64]
    cap = quality_manga.bubbles_cap_lot(numbered_plat, n_total, plafond)

    # Garde-fou de PREFILL — la mesure qui avait fait écarter le tome-en-un-appel, cette fois
    # calculée à chaque lot au lieu d'être supposée une fois pour toutes. Purement consultatif :
    # `num_ctx` est déclaratif (il vit dans le Modelfile Ollama), on avertit et on continue.
    if num_ctx > 0 and reporter is not None:
        _verifier_num_ctx(agent, num_ctx, reporter)
        reste = quality_manga.place_disponible(tokens.estimate(user), cap, num_ctx)
        if reste < 0:
            reporter.warn(
                f"[traduction] lot planches {utiles[0].index}→{utiles[-1].index} : le prompt "
                f"(~{tokens.estimate(user)} tok) + la sortie ({cap} tok) dépassent de "
                f"{-reste} tokens les 85 % de num_ctx ({num_ctx}) — réduis "
                f"`manga.lot.planches` ou monte le num_ctx du Modelfile")

    raw = agent.run(user, dry_payload=numbered_plat, max_tokens=cap,
                    temperature=agent.temperature, images=images or None)
    motif_lot = quality_manga.diagnostiquer(raw, n=n_total, cap=cap, sources=sources)
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
                                            sources=p.textes_jp)
        if motif is None and motif_lot == "emballement":
            motif = "emballement"
        if stats is not None:
            cle = motif or "pages_ok"
            stats[cle] = stats.get(cle, 0) + 1
        resultats[p.index] = (tranche, motif, quality_manga.strategie_de_tranche(tranche))
    return resultats


def _translate_page(agent, image: Image.Image, texts_jp: list[str], mode_vision: bool,
                     gloss_text: str, *, styles: list | None = None,
                     precedentes: list[str] | None = None, stats: dict | None = None,
                     contexte_oeuvre: str = "",
                     max_retries: int = 1) -> tuple[list[str], str | None, str]:
    """Traduit les bulles d'une page. Renvoie `(répliques, motif_d_échec, stratégie)`.

    La `stratégie` dit COMMENT les répliques ont été rattachées à leurs bulles (cf.
    `quality_manga.STRATEGIES`) : une planche reconstituée positionnellement n'a pas la même
    valeur de preuve qu'une planche numérotée, et jusqu'ici rien ne le disait.

    Deux ajouts de contexte, tirés des mesures du tome :
      · **les dimensions de chaque bulle** — le prompt demande d'être bref mais ne dit jamais
        *à quel point* : 54 traductions dépassaient 90 caractères, donc débordaient ;
      · **les répliques de la page précédente**, pour la continuité du dialogue (un pronom ou
        un sujet implicite ne se désambiguïse pas sur une planche isolée)."""
    if not texts_jp:
        return [], None, "vide"
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts_jp))

    parts = []
    if gloss_text:
        parts.append(gloss_text)
    if precedentes:
        parts.append("Répliques de la planche précédente (contexte, NE PAS retraduire) :\n"
                     + "\n".join(f"- {t}" for t in precedentes if t.strip()))
    gabarits = _lignes_gabarits(_bbox_des_styles(styles, len(texts_jp)), depart=1)
    if gabarits:
        parts.append("Place disponible par bulle (dépasser force une police illisible) :\n"
                     + "\n".join(gabarits))
    parts.append("Bulles détectées (ordre de lecture, droite → gauche puis haut → bas) :\n"
                 + numbered)
    user = "\n\n".join(parts)

    images = None
    if mode_vision:
        images = [_image_b64(image)]

    cap = quality_manga.bubbles_cap(numbered, len(texts_jp))

    def _call(temperature):
        return agent.run(user, dry_payload=numbered, max_tokens=cap,
                          temperature=temperature, images=images)

    raw, _ok, motif = quality_manga.try_with_temp_retry(
        _call, n=len(texts_jp), cap=cap, sources=texts_jp, stats=stats,
        temperature=agent.temperature, max_retries=max_retries)
    repliques, strategie = quality_manga.repliques_par_bulle(raw, len(texts_jp))
    return repliques, motif, strategie


CONTEXTE_FILENAME = "contexte.txt"


def _passe_contexte(agent, build_dir, *, total: int, gloss_text: str, budget_entree: int,
                    max_tokens: int, reporter, dire=True) -> str:
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
    parts.append("Échantillon du texte japonais du tome :\n" + "\n".join(morceaux))
    fiche = (agent.run("\n\n".join(parts), dry_payload="", max_tokens=max_tokens) or "").strip()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(fiche, encoding="utf-8")
    if dire and fiche:
        reporter.info(f"Contexte d'œuvre : fiche de {len(fiche.splitlines())} ligne(s) "
                      f"(~{tokens.estimate(fiche)} tokens), injectée dans chaque planche")
    return fiche


def _contexte_precedent(build_dir, page: int, planches: int, max_repliques: int,
                        gloss: dict | None = None) -> list[str]:
    """Les dernières répliques des `planches` planches qui PRÉCÈDENT celle-ci.

    Lu depuis les checkpoints plutôt que porté par une variable de boucle, et c'est ce qui
    corrige deux défauts d'un coup :

      · la variable n'était **pas réinitialisée sur une planche sautée** (`continue` du
        balayage B) — sur un run partiel, la planche 40 recevait le contexte de la 12 ;
      · elle partait **vide** sur `--page N` et sur toute reprise, alors que
        `page_{N-1}/traduction.json` est sur le disque depuis le premier run.

    Sans état, les trois cas (run complet, run partiel, planche isolée) donnent le même
    contexte — celui des planches réellement précédentes. Le coût est de quelques lectures de
    petits JSON par planche, à comparer aux ~9 s d'un appel de traduction."""
    if planches <= 0 or max_repliques <= 0:
        return []
    repliques: list[str] = []
    for p in range(max(1, page - planches), page):
        textes = checkpoints.load_traduction(checkpoints.page_checkpoint_dir(build_dir, p))
        repliques.extend(t for t in (textes or []) if t and t.strip())
    repliques = repliques[-max_repliques:]
    # ⚠ Le cache garde la sortie BRUTE du modèle : le forçage s'applique à l'usage, pas à
    # l'écriture (c'est ce qui rend `--from rendu` gratuit). Il faut donc le rejouer ici, sinon
    # le contexte transmettrait les orthographes que le glossaire interdit — exactement ce que
    # ce contexte est censé aider le modèle à reprendre.
    if gloss and repliques:
        repliques, _n, _refus = terminology.forcer_bulles(repliques, gloss)
    return repliques


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


def _translate_sfx(agent, textes_jp: list[str], gloss_text: str, *,
                    stats: dict | None = None, max_retries: int = 1) -> list[str]:
    """Traduit les zones de texte hors bulle. Renvoie une liste alignée par position.

    **Un appel SÉPARÉ de celui de la planche**, et c'est délibéré. Le contrat de
    numérotation des bulles tient à 127/127 sur le Vol.2 : y greffer une seconde liste
    reviendrait à risquer ce qui marche pour ce qui n'existe pas encore. Une liste, un
    ordre, aucun numéro partagé — le chemin nominal reste intact.

    Les garde-fous de `quality_manga` s'appliquent tels quels : une réponse qui recopie le
    japonais est diagnostiquée `japonais_residuel` comme ailleurs."""
    if not textes_jp:
        return []
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(textes_jp))
    parts = []
    if gloss_text:
        parts.append(gloss_text)
    parts.append("Zones de texte hors bulle (ordre de lecture, droite → gauche puis "
                 "haut → bas) :\n" + numbered)
    user = "\n\n".join(parts)
    cap = quality_manga.bubbles_cap(numbered, len(textes_jp))

    def _call(temperature):
        return agent.run(user, dry_payload=numbered, max_tokens=cap, temperature=temperature)

    raw, _ok, _motif = quality_manga.try_with_temp_retry(
        _call, n=len(textes_jp), cap=cap, sources=textes_jp, stats=stats,
        temperature=agent.temperature, max_retries=max_retries)
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
                      reporter=None, page: int = 0) -> tuple[list[str], list[int], list[str]]:
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
    c = {**_DEFAUTS_RATTRAPAGE, **(cfg or {})}
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
            agent, source, gloss_text=gloss_text, bbox=boite)
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
                     reporter=None) -> list[str]:
    """Assemble les pages de `pages_out/` dans les formats demandés.

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
            sens_lecture=rendu.get("sens_lecture", "droite_gauche"),
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
