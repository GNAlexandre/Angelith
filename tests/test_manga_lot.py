# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Traduction par LOTS de planches : plusieurs planches consécutives dans un seul appel.

Le gain est un nombre d'appels — 7 au lieu de 131 sur un tome — et le risque est toujours le
même : une réplique qui atterrit dans la mauvaise bulle. D'où deux familles de tests ici.

**Les fonctions pures** (`decouper_par_planche`, `groupes_de_lot`, `bubbles_cap_lot`) : c'est
là que se joue l'alignement, et elles se testent sans le moindre pixel.

**Le repli**, qui est ce qui rend le lot défendable : un lot n'est jamais retenté en entier,
il se dégrade planche par planche vers le chemin de la 1.0.0. Trois tests vérifient qu'il se
déclenche exactement quand il faut — lot non numéroté, planche incomplète — et un quatrième
qu'il ne se déclenche PAS pour une bulle vide à raison (source sans texte).

Aucun appel LLM : le traducteur est un double qui répond selon le nombre de bulles reçues.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image, ImageDraw

from core import glossary
from manga import checkpoints, quality_manga
from manga.detection import BubbleRegion
from manga.orchestrator_manga import MAX_PLANCHES_LOT, groupes_de_lot

RACINE = Path(__file__).resolve().parents[1]
TAILLE = (400, 900)

# Nombre de bulles par planche du tome de test. Volontairement INÉGAL : une découpe fausse
# passerait inaperçue sur quatre planches de deux bulles.
BULLES = {1: 2, 2: 3, 3: 2, 4: 2}
TOTAL_BULLES = sum(BULLES.values())          # 9

# Le séparateur de lignes attendu par `analyser_numerotation`. Nommé plutôt qu'écrit en
# toutes lettres : ces tests se relisent mieux quand la forme de la réponse est une constante.
SAUT = "\n"


def _jp(page: int, k: int) -> str:
    """Japonais distinct par (planche, bulle) — c'est ce qui permet de savoir, en relisant
    `traduction.json`, si une réplique a atterri sur la bonne planche."""
    return "アイウエ"[page - 1] + "ァィゥ"[k]


def _boite(k: int) -> tuple[int, int, int, int]:
    """Bulles empilées verticalement, sans chevauchement : l'ordre de lecture est alors
    exactement l'ordre des index, et le test ne dépend pas de la coupe X-Y."""
    haut = 40 + k * 220
    return (60, haut, 340, haut + 160)


def _planche() -> Image.Image:
    img = Image.new("RGB", TAILLE, (20, 20, 20))
    d = ImageDraw.Draw(img)
    for k in range(max(BULLES.values())):
        d.ellipse(list(_boite(k)), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    return img


def _masque(k: int) -> np.ndarray:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse(list(_boite(k)), fill=255)
    return np.asarray(m) > 127


class _Traducteur:
    """Double du traducteur. Répond une liste numérotée dont la LONGUEUR suit ce qu'on lui
    demande — c'est-à-dire le comportement nominal du modèle.

    Le nombre de bulles est lu dans `dry_payload`, qui est exactement la liste numérotée
    envoyée (séparateurs de planche compris) : le compter dans `user` attraperait aussi les
    lignes de gabarit « 1. 280×160 px — … », qui portent le même préfixe."""

    temperature = 0.3
    modele = "double"
    llm = None
    dry_run = False

    def __init__(self, sabotage=None):
        self.prompts: list[str] = []
        self.charges: list[str] = []
        self.sabotage = sabotage        # (numeros_attendus) -> sortie, ou None

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.prompts.append(user)
        self.charges.append(dry_payload)
        numeros = [int(m) for m in re.findall(r"^\s*(\d+)\. ", dry_payload, re.M)]
        if self.sabotage is not None:
            sortie = self.sabotage(numeros)
            if sortie is not None:
                return sortie
        return "\n".join(f"{i}. FR{i}" for i in numeros)

    @property
    def appels(self) -> int:
        return len(self.prompts)


@pytest.fixture
def tome4(tmp_path):
    """Tome de 4 planches en cache jusqu'à l'OCR : `stages_to_redo` renvoie donc
    `{traduction, rendu}` sans `--from`, et rien n'est encore traduit."""
    vol = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol.mkdir(parents=True)
    build_dir = tmp_path / "build" / "MonManga" / "Vol.1" / "manga"
    (build_dir / "pages_out").mkdir(parents=True)
    (build_dir / "pages_clean").mkdir(parents=True)

    page = _planche()
    from manga.clean import clean_bubbles
    for i, n in BULLES.items():
        page.save(vol / f"page_{i:04d}.png")
        regions = [BubbleRegion(bbox=_boite(k), mask=_masque(k), score=0.95, cls=0)
                   for k in range(n)]
        ckpt = checkpoints.page_checkpoint_dir(build_dir, i)
        checkpoints.save_regions(ckpt, regions, page.size)
        clean_bubbles(page, regions).save(checkpoints.clean_page_path(build_dir, i))
        checkpoints.save_ocr(ckpt, [_jp(i, k) for k in range(n)])

    glossary.save(glossary.empty(), tmp_path / "sources" / "MonManga" / "glossaire.yaml")

    config = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    config["chemins"]["prompts"] = str(RACINE / "prompts")
    # Chemin ONNX inexistant : toute construction du détecteur lèverait SystemExit. C'est la
    # garantie que ces tests n'atteignent jamais la vision par ordinateur.
    config["manga"]["detection"]["model_path"] = str(tmp_path / "absent.onnx")
    config["manga"]["onomatopees"]["actif"] = False
    return config, build_dir, tmp_path


def _brancher(monkeypatch, trad):
    import manga.orchestrator_manga as orch
    monkeypatch.setattr(orch, "build_manga_agents",
                        lambda cfg, dry_run=False: {"manga_traducteur": trad})


def _run(config, **kw):
    from core.reporter import Reporter

    from manga.orchestrator_manga import process_volume
    return process_volume("MonManga", "Vol.1", config, reporter=Reporter(), **kw)


def _traductions(build_dir, page: int) -> list[str]:
    return checkpoints.load_traduction(checkpoints.page_checkpoint_dir(build_dir, page)) or []


# --------------------------------------------------------------------------- #
# Fonctions pures — l'alignement se joue ici
# --------------------------------------------------------------------------- #

def test_decouper_par_planche_respecte_les_tailles():
    tranches = quality_manga.decouper_par_planche(
        ["a", "b", "c", "d", "e", "f"], [2, 3, 1])
    assert tranches == [["a", "b"], ["c", "d", "e"], ["f"]]


def test_decouper_par_planche_complete_une_entree_trop_courte():
    """Le contrat de longueur est ABSOLU : rendre une tranche courte ferait mentir
    l'alignement par position de `traduction.json` sur `regions.json`."""
    assert quality_manga.decouper_par_planche(["a", "b"], [2, 3]) == [["a", "b"], ["", "", ""]]


def test_decouper_par_planche_tronque_une_entree_trop_longue():
    assert quality_manga.decouper_par_planche(["a", "b", "c", "d"], [1, 1]) == [["a"], ["b"]]


def test_decouper_par_planche_sur_liste_vide():
    assert quality_manga.decouper_par_planche([], [2, 1]) == [["", ""], [""]]


def test_strategie_de_tranche():
    assert quality_manga.strategie_de_tranche(["a", "b"]) == "numerotee"
    assert quality_manga.strategie_de_tranche(["a", ""]) == "numerotee_partielle"
    assert quality_manga.strategie_de_tranche(["", ""]) == "vide"
    assert quality_manga.strategie_de_tranche([]) == "vide"


def test_bubbles_cap_lot_croit_avec_le_nombre_de_bulles_et_respecte_le_plafond():
    petit = quality_manga.bubbles_cap_lot("1. あ", 6, plafond=6000)
    grand = quality_manga.bubbles_cap_lot("1. あ", 60, plafond=6000)
    assert grand > petit
    assert quality_manga.bubbles_cap_lot("1. あ", 500, plafond=6000) == 6000


def test_bubbles_cap_reste_celui_de_la_planche_seule():
    """La signature historique ne bouge pas : le rattrapage unitaire et 27 tests l'appellent."""
    assert quality_manga.bubbles_cap("1. あ", 500) == quality_manga.PLAFOND_PLANCHE


def test_place_disponible_devient_negative_quand_le_lot_ne_tient_pas():
    assert quality_manga.place_disponible(22070, 8878, 32768) < 0
    assert quality_manga.place_disponible(22070, 8878, 65536) > 0


def test_groupes_de_lot_ne_franchit_pas_un_trou():
    """Sur une reprise partielle, un lot {1,2,40,41} présenterait au modèle quatre planches
    comme une scène continue. Un trou ferme le lot en cours."""
    assert groupes_de_lot([1, 2, 3, 40, 41], 20) == [[1, 2, 3], [40, 41]]


def test_groupes_de_lot_borne_la_taille():
    assert groupes_de_lot([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_groupes_de_lot_a_1_rend_des_planches_isolees():
    assert groupes_de_lot([1, 2, 3], 1) == [[1], [2], [3]]


def test_max_planches_lot_ne_diverge_pas_entre_la_cli_et_l_orchestrateur():
    """`run_manga.py` recopie la constante pour ne pas importer numpy au parsing (même raison
    qu'`ETAPES`). Deux copies libres de diverger sont un réglage qui ment."""
    import run_manga
    assert run_manga.MAX_PLANCHES_LOT == MAX_PLANCHES_LOT


# --------------------------------------------------------------------------- #
# Le chemin nominal : un appel, quatre planches, chacune ses répliques
# --------------------------------------------------------------------------- #

def test_un_lot_de_quatre_planches_ne_fait_qu_un_appel(tome4, monkeypatch):
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    trad = _Traducteur()
    _brancher(monkeypatch, trad)

    assert _run(config) is True

    assert trad.appels == 1, "quatre planches, un seul appel"


def test_chaque_planche_recoit_sa_propre_tranche(tome4, monkeypatch):
    """LE test du lot. La numérotation est plate (1..9) et la redistribution arithmétique :
    la planche 2 doit recevoir FR3..FR5, pas FR1..FR3."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    trad = _Traducteur()
    _brancher(monkeypatch, trad)

    _run(config)

    assert _traductions(build_dir, 1) == ["FR1", "FR2"]
    assert _traductions(build_dir, 2) == ["FR3", "FR4", "FR5"]
    assert _traductions(build_dir, 3) == ["FR6", "FR7"]
    assert _traductions(build_dir, 4) == ["FR8", "FR9"]


def test_le_prompt_du_lot_porte_les_separateurs_et_une_numerotation_continue(tome4, monkeypatch):
    config, _build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    trad = _Traducteur()
    _brancher(monkeypatch, trad)

    _run(config)

    prompt = trad.prompts[0]
    assert "— Planche 1 (bulles 1 à 2) —" in prompt
    assert "— Planche 2 (bulles 3 à 5) —" in prompt
    assert "— Planche 4 (bulles 8 à 9) —" in prompt
    # La numérotation ne redémarre jamais : le japonais de la 1re bulle de la planche 2 porte
    # le numéro 3.
    assert f"3. {_jp(2, 0)}" in prompt
    # La CHARGE (dry_payload) est la forme attendue de la RÉPONSE : pas de séparateurs. En
    # dry-run l'agent la renvoie telle quelle, et une ligne non numérotée serait recollée à la
    # réplique précédente par `analyser_numerotation`.
    assert "— Planche" not in trad.charges[0]
    assert trad.charges[0].splitlines()[0] == f"1. {_jp(1, 0)}"


def test_le_qa_dit_la_taille_de_lot_reellement_subie(tome4, monkeypatch):
    """Un tome traduit par lots et un tome traduit planche par planche seraient sinon
    indistinguables au rapport — y compris pour comparer deux runs."""
    from manga import report_manga
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    _brancher(monkeypatch, _Traducteur())

    _run(config)

    for page in BULLES:
        qa = report_manga.load_page_qa(checkpoints.page_checkpoint_dir(build_dir, page))
        assert qa["lot_taille"] == 4


# --------------------------------------------------------------------------- #
# Le repli — ce qui rend le lot défendable
# --------------------------------------------------------------------------- #

def test_une_planche_incomplete_est_seule_reprise(tome4, monkeypatch):
    """Le lot n'est PAS rejoué : seules les planches trouées repassent par le chemin nominal.
    Ici le modèle « oublie » les numéros 3 à 5, c'est-à-dire toute la planche 2."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4

    def sabotage(numeros):
        if len(numeros) != TOTAL_BULLES:
            return None                       # appel de repli : réponse normale
        return "\n".join(f"{i}. FR{i}" for i in numeros if i not in (3, 4, 5))

    trad = _Traducteur(sabotage)
    _brancher(monkeypatch, trad)

    _run(config)

    assert trad.appels == 2, "un lot + une seule planche reprise"
    # La planche reprise a été traduite SEULE : sa numérotation repart donc à 1.
    assert _traductions(build_dir, 2) == ["FR1", "FR2", "FR3"]
    # Les trois autres gardent la tranche du lot, à leur place.
    assert _traductions(build_dir, 1) == ["FR1", "FR2"]
    assert _traductions(build_dir, 3) == ["FR6", "FR7"]
    assert _traductions(build_dir, 4) == ["FR8", "FR9"]


def test_le_qa_ramene_la_taille_a_1_pour_une_planche_repliee(tome4, monkeypatch):
    from manga import report_manga
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4

    def sabotage(numeros):
        if len(numeros) != TOTAL_BULLES:
            return None
        return "\n".join(f"{i}. FR{i}" for i in numeros if i not in (3, 4, 5))

    _brancher(monkeypatch, _Traducteur(sabotage))
    _run(config)

    lu = {p: report_manga.load_page_qa(
        checkpoints.page_checkpoint_dir(build_dir, p))["lot_taille"] for p in BULLES}
    assert lu == {1: 4, 2: 1, 3: 4, 4: 4}


def test_un_lot_non_numerote_est_abandonne_en_entier(tome4, monkeypatch):
    """Rattacher 9 répliques à leurs bulles par leur seul ordre est indéfendable sur un lot,
    là où c'était déjà le pire cas sur une planche isolée. On repart planche par planche."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4

    def sabotage(numeros):
        if len(numeros) != TOTAL_BULLES:
            return None
        return "\n".join(f"FR{i}" for i in numeros)        # aucune numérotation

    trad = _Traducteur(sabotage)
    _brancher(monkeypatch, trad)

    _run(config)

    assert trad.appels == 1 + len(BULLES), "le lot raté, puis les quatre planches seules"
    assert _traductions(build_dir, 2) == ["FR1", "FR2", "FR3"]


def test_une_bulle_vide_a_raison_ne_declenche_pas_de_repli(tome4, monkeypatch):
    """Une source qui ne PORTE aucun texte (`（）`) est vide à raison : refaire la planche
    entière pour elle serait un appel payé pour rien, que le rattrapage unitaire refuserait
    de toute façon ensuite (`source_rattrapable`)."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    # La 2e bulle de la planche 1 n'a plus de texte à traduire.
    ck1 = checkpoints.page_checkpoint_dir(build_dir, 1)
    checkpoints.save_ocr(ck1, [_jp(1, 0), "（）"])

    def sabotage(numeros):
        if len(numeros) != TOTAL_BULLES:
            return None
        return "\n".join(f"{i}. FR{i}" for i in numeros if i != 2)

    trad = _Traducteur(sabotage)
    _brancher(monkeypatch, trad)

    _run(config)

    assert trad.appels == 1, "aucun repli, aucun rattrapage"
    assert _traductions(build_dir, 1) == ["FR1", ""]


# --------------------------------------------------------------------------- #
# Cache et garde-fous
# --------------------------------------------------------------------------- #

def test_changer_la_taille_de_lot_ne_retraduit_rien(tome4, monkeypatch):
    """L'invariant qui distingue le manga du LN. Le LN scelle la signature de son découpage
    (`_sceller_decoupage`) parce que ses caches sont PAR BLOC ; ici les résultats restent
    écrits par planche, alignés sur les bulles de cette planche. Changer la taille du lot ne
    peut donc désaligner personne — et y ajouter une signature ferait retraduire un tome
    entier pour rien."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    _brancher(monkeypatch, _Traducteur())
    _run(config)
    avant = {p: _traductions(build_dir, p) for p in BULLES}

    config["manga"]["lot"]["planches"] = 1
    trad2 = _Traducteur()
    _brancher(monkeypatch, trad2)
    _run(config)

    assert trad2.appels == 0, "tout est en cache : aucun appel de traduction"
    assert {p: _traductions(build_dir, p) for p in BULLES} == avant


def test_le_mode_vision_plafonne_le_lot(tome4, monkeypatch):
    """Une image PLEINE PAGE par planche : 20 planches satureraient le contexte avant la
    première réplique. Le plafond est distinct et s'applique automatiquement."""
    config, _build_dir, _tmp = tome4
    config["manga"]["mode_traduction"] = "vision"
    config["manga"]["lot"]["planches"] = 4
    config["manga"]["lot"]["planches_vision"] = 2
    trad = _Traducteur()
    _brancher(monkeypatch, trad)

    _run(config)

    assert trad.appels == 2, "4 planches par lots de 2"


def test_une_planche_sautee_ferme_le_lot(tome4, monkeypatch):
    """Intégration de `groupes_de_lot` : la planche 3 est déjà rendue, donc hors travail. Les
    planches 1-2 forment un lot, la planche 4 part seule — jamais {1,2,4}."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    # La planche 3 est déjà entièrement générée : le balayage B la saute.
    ck3 = checkpoints.page_checkpoint_dir(build_dir, 3)
    checkpoints.save_traduction(ck3, ["déjà", "fait"])
    Image.new("RGB", TAILLE, (0, 0, 0)).save(checkpoints.final_page_path(build_dir, 3))

    trad = _Traducteur()
    _brancher(monkeypatch, trad)
    _run(config)

    assert trad.appels == 2, "un lot {1,2}, puis la planche 4 seule"
    prompt_lot = trad.prompts[0]
    assert "— Planche 1 " in prompt_lot and "— Planche 2 " in prompt_lot
    assert "— Planche 4 " not in prompt_lot
    assert _traductions(build_dir, 3) == ["déjà", "fait"]


def test_un_lot_de_1_emprunte_le_chemin_de_la_1_0_0(tome4, monkeypatch):
    """Défaut de configuration : aucun séparateur de planche ne doit apparaître, et chaque
    planche numérote à partir de 1."""
    config, build_dir, _tmp = tome4
    trad = _Traducteur()
    _brancher(monkeypatch, trad)

    _run(config)

    assert trad.appels == len(BULLES)
    assert all("— Planche" not in p for p in trad.prompts)
    assert _traductions(build_dir, 2) == ["FR1", "FR2", "FR3"]


# --------------------------------------------------------------------------- #
# Réflexion
# --------------------------------------------------------------------------- #

def test_la_reflexion_de_lot_vise_le_traducteur_seul():
    """Posée sur la SPEC DU MODÈLE et non sous `manga.llm` : sous `llm`, elle s'appliquerait
    aussi au terminologue, au glossariste et aux onomatopées, dont le coût de raisonnement
    n'a aucune raison de suivre la taille du lot."""
    from manga.orchestrator_manga import _appliquer_reflexion_lot
    config = {"manga": {
        "lot": {"think": "high", "thinking_budget": 2500},
        "modeles": {"manga_traducteur": {"model": "m", "think": False},
                    "terminologue": {"model": "m"}}}}

    _appliquer_reflexion_lot(config)

    modeles = config["manga"]["modeles"]
    assert modeles["manga_traducteur"] == {"model": "m", "think": "high",
                                           "thinking_budget": 2500}
    assert modeles["terminologue"] == {"model": "m"}


def test_la_reflexion_de_lot_promeut_une_spec_ecrite_en_chaine():
    from manga.orchestrator_manga import _appliquer_reflexion_lot
    config = {"manga": {"lot": {"think": True},
                        "modeles": {"manga_traducteur": "qwen3.6:27b"}}}

    _appliquer_reflexion_lot(config)

    assert config["manga"]["modeles"]["manga_traducteur"] == {"model": "qwen3.6:27b",
                                                              "think": True}


def test_sans_clef_think_la_config_du_modele_est_intacte():
    """`manga.lot.think` absent ≠ `false` : on ne doit pas écraser un réglage posé à la main
    sous `manga.modeles`."""
    from manga.orchestrator_manga import _appliquer_reflexion_lot
    config = {"manga": {"lot": {"planches": 8},
                        "modeles": {"manga_traducteur": {"model": "m", "think": "low"}}}}

    _appliquer_reflexion_lot(config)

    assert config["manga"]["modeles"]["manga_traducteur"]["think"] == "low"


def test_config_yaml_ne_livre_pas_de_think_de_lot():
    """Régression mesurée. `manga.lot.think` est un OUTREPASSEMENT : posé, il écrase la spec
    du modèle **et son `endpoint:`**. Livré à `false` par défaut, il désactivait donc en
    silence l'indirection `endpoint: reflexion` du traducteur — le défaut exact que le lot 2.2
    avait corrigé, et que `tests/test_manga_runtime.py` surveille (deux agents sur deux
    endpoints doivent avoir deux clients distincts).

    La clé doit rester COMMENTÉE dans `config.yaml`. `--think` l'écrit pour un run donné."""
    config = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    assert "think" not in (config["manga"].get("lot") or {})


def test_le_think_de_lot_outrepasse_l_endpoint_quand_il_est_pose():
    """L'autre moitié du contrat : écrit explicitement, il DOIT l'emporter — couper le
    raisonnement pour ce tome-ci quel que soit l'endpoint est un choix légitime."""
    from manga.orchestrator_manga import _appliquer_reflexion_lot
    config = {"manga": {
        "lot": {"think": False},
        "modeles": {"manga_traducteur": {"model": "m", "endpoint": "reflexion"}}}}

    _appliquer_reflexion_lot(config)

    spec = config["manga"]["modeles"]["manga_traducteur"]
    assert spec["think"] is False and spec["endpoint"] == "reflexion"


# --------------------------------------------------------------------------- #
# Persistance immédiate — le lot 26
#
# Mesuré sur le Vol.4 : un `--lot 20` interrompu a produit UNE planche en 44 minutes, et tout
# le reste a été perdu ; le tome a dû être retraduit en entier à `lot=1`. La 1.1.0 gardait
# délibérément les résultats en mémoire pour préserver l'invariant « le cache est déjà
# rattrapé ». La bonne réponse n'était pas de choisir : on rattrape tout de suite, puis on
# écrit.
# --------------------------------------------------------------------------- #

def test_les_planches_d_un_lot_sont_ecrites_des_la_reception(tome4, monkeypatch):
    """Le rendu de CHAQUE planche lève. Les traductions du lot, elles, doivent déjà être sur
    le disque.

    ⚠ Depuis le filet par planche, l'exception ne remonte plus : elle est isolée, la planche
    est comptée en échec et le tome continue. Le test ne guette donc plus un `RuntimeError`
    — il vérifie que le run VA AU BOUT en ayant quand même sauvé les traductions, ce qui est
    strictement plus que ce qu'il exigeait avant."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    _brancher(monkeypatch, _Traducteur())

    import manga.typeset as typeset

    def _explose(*a, **k):
        raise RuntimeError("panne simulée au lettrage")

    monkeypatch.setattr(typeset, "typeset_page", _explose)

    assert _run(config) is True          # le tome se termine malgré les quatre échecs

    # Les QUATRE planches ont leur traduction, alors qu'aucune n'a été rendue.
    assert _traductions(build_dir, 1) == ["FR1", "FR2"]
    assert _traductions(build_dir, 2) == ["FR3", "FR4", "FR5"]
    assert _traductions(build_dir, 3) == ["FR6", "FR7"]
    assert _traductions(build_dir, 4) == ["FR8", "FR9"]
    assert not list((build_dir / "pages_out").glob("page_*.png"))

    # Et le rapport NOMME les quatre planches perdues : c'est la seule trace qui survit au
    # défilement d'un run de nuit.
    rapport = (build_dir / "RAPPORT.md").read_text(encoding="utf-8")
    assert "Planches en ÉCHEC" in rapport
    for page in (1, 2, 3, 4):
        assert f"page {page} · étape « rendu »" in rapport


def test_le_cache_d_un_lot_est_deja_rattrape(tome4, monkeypatch):
    """L'invariant que la 1.1.0 protégeait en différant l'écriture : ce qui atteint le disque
    est DÉJÀ passé par le rattrapage unitaire, parce que `stages_to_redo` teste la présence du
    fichier et non son état.

    Ici la planche 2 est renvoyée au chemin nominal (sa bulle manquante porte du texte, donc
    elle est rattrapable), ce chemin la laisse trouée, et le rattrapage comble le trou — le
    tout AVANT que `traduction.json` ne soit écrit."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    ecritures: list[tuple[int, list]] = []

    import manga.orchestrator_manga as orch
    vraie_ecriture = orch.checkpoints.save_traduction

    def _espion(ckpt_dir, textes):
        ecritures.append((int(str(ckpt_dir)[-4:]), list(textes)))
        vraie_ecriture(ckpt_dir, textes)

    monkeypatch.setattr(orch.checkpoints, "save_traduction", _espion)

    def sabotage(numeros):
        if len(numeros) == TOTAL_BULLES:
            return SAUT.join(f"{i}. FR{i}" for i in numeros if i != 4)
        if not numeros:                       # appel unitaire du rattrapage
            return "Rattrapée"
        return SAUT.join(f"{i}. FR{i}" for i in numeros if i != 2)   # repli, encore troué

    _brancher(monkeypatch, _Traducteur(sabotage))
    _run(config)

    ecrit_p2 = [textes for page, textes in ecritures if page == 2]
    assert ecrit_p2, "la planche 2 doit avoir été écrite"
    assert "" not in ecrit_p2[0], (
        "le trou doit être comblé AVANT l'écriture — le cache ne contient jamais de "
        "traduction non rattrapée")
    assert _traductions(build_dir, 2)[1] == "Rattrapée"


def test_une_planche_gardee_du_lot_ne_coute_aucun_rattrapage(tome4, monkeypatch):
    """Une planche conservée du lot n'a, par construction, que des bulles vides NON
    rattrapables (sinon elle serait repliée) : le rattrapage posé à la réception est alors un
    passage à vide, et ne doit consommer aucun appel."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    ck1 = checkpoints.page_checkpoint_dir(build_dir, 1)
    checkpoints.save_ocr(ck1, [_jp(1, 0), "（）"])           # 2e bulle : rien à traduire

    def sabotage(numeros):
        if len(numeros) != TOTAL_BULLES:
            return None
        return SAUT.join(f"{i}. FR{i}" for i in numeros if i != 2)

    trad = _Traducteur(sabotage)
    _brancher(monkeypatch, trad)
    _run(config)

    assert trad.appels == 1, "le lot seul : aucun repli, aucun rattrapage"
    assert _traductions(build_dir, 1) == ["FR1", ""]


def test_le_rattrapage_ne_tourne_pas_deux_fois_sur_une_planche_de_lot(tome4, monkeypatch):
    """Il a lieu à la réception du lot ; la boucle des planches ne doit pas le rejouer. Sinon
    chaque bulle refusée coûterait un appel de plus à chaque run."""
    config, build_dir, _tmp = tome4
    config["manga"]["lot"]["planches"] = 4
    appels = []

    import manga.orchestrator_manga as orch
    vrai = orch._rattraper_bulles

    def _espion(agent, texts_jp, translated, **kw):
        appels.append(kw.get("page"))
        return vrai(agent, texts_jp, translated, **kw)

    monkeypatch.setattr(orch, "_rattraper_bulles", _espion)
    _brancher(monkeypatch, _Traducteur())
    _run(config)

    assert sorted(appels) == [1, 2, 3, 4], "une fois par planche, pas deux"
