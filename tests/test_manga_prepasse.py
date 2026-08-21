# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Passe terminologique de VOLUME (lot 4.1) : le glossaire est fixé avant la première
traduction, plus construit au fil des planches.

Le défaut corrigé, mesuré sur *manga A* Vol.1 : les six étapes s'enchaînaient
planche par planche, donc le relevé de la planche 42 n'existait qu'après la traduction de la
planche 41. Trois conséquences, chacune verrouillée par un test ici :
  · la planche 1 était traduite avec un glossaire VIDE ;
  · `optimize_glossary_file` (dédoublonnage) tombait APRÈS la dernière traduction, si bien
    qu'aucune traduction du run n'en profitait ;
  · `gloss_text` était re-sérialisé après chaque planche, donc deux planches n'étaient jamais
    traduites avec la même terminologie.

Tous les tests tournent sans LLM : le traducteur, le terminologue et le glossariste sont des
doubles qui journalisent ce qu'on leur demande. C'est l'ORDRE des événements qui est vérifié,
pas la qualité des réponses.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image, ImageDraw

from core import glossary
from manga import checkpoints
from manga.detection import BubbleRegion

RACINE = Path(__file__).resolve().parents[1]
BOX = (60, 40, 340, 200)
TAILLE = (400, 260)

# Une chaîne japonaise distincte par planche : c'est ce qui permet, en relisant le prompt reçu
# par le traducteur, de savoir DE QUELLE planche il s'agit — l'agent, lui, ne le sait pas.
JP = {1: "アアア", 2: "イイイ", 3: "ウウウ"}

# Un terme distinct révélé par planche. Celui de la planche 3 est le témoin : s'il apparaît
# dans le prompt de la planche 1, c'est que tout le relevé a précédé toute traduction.
NOTES = {
    1: "## Objets\n- Sleipnir | termes_source: スレイプニール | Cataphracte de Haruya.\n",
    2: "## Objets\n- Areion | termes_source: アレイオン | Cataphracte de Soun.\n",
    3: ("## Objets\n- Kataphrakt | termes_source: カタフラクト | interdits: Katafrakt | "
        "Armure de combat martienne.\n"),
}
NOTES_P3 = NOTES[3]


def _planche() -> Image.Image:
    img = Image.new("RGB", TAILLE, (20, 20, 20))
    ImageDraw.Draw(img).ellipse(list(BOX), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    return img


def _masque() -> np.ndarray:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse(list(BOX), fill=255)
    return np.asarray(m) > 127


class _Traducteur:
    """Double du traducteur manga : journalise le prompt reçu et renvoie une réplique
    numérotée, seule forme que `_parse_translations` accepte sans repli."""

    temperature = 0.3
    modele = "double"

    def __init__(self, journal: list):
        self.journal = journal
        self.prompts: list[str] = []

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.journal.append("traduction")
        self.prompts.append(user)
        return "1. Réplique"

    def prompt_de(self, page: int) -> str:
        """Le prompt de la planche `page`, retrouvé par sa chaîne japonaise."""
        trouves = [p for p in self.prompts if JP[page] in p]
        assert len(trouves) == 1, f"planche {page} : {len(trouves)} prompt(s)"
        return trouves[0]


class _Terminologue:
    """Révèle un terme différent par planche, reconnue à son japonais dans le prompt."""

    def __init__(self, journal: list):
        self.journal = journal
        self.appels: list[str] = []

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.journal.append("terminologie")
        self.appels.append(user)
        for page, jp in JP.items():
            if jp in user:
                return NOTES[page]
        return "- (rien à signaler)"


@pytest.fixture
def tome3(tmp_path):
    """Tome de trois planches, en cache jusqu'à l'OCR inclus — donc `stages_to_redo` renvoie
    `{traduction, rendu}` sans qu'on ait besoin de `--from`. Rien n'est encore traduit."""
    vol = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol.mkdir(parents=True)
    build_dir = tmp_path / "build" / "MonManga" / "Vol.1" / "manga"
    (build_dir / "pages_out").mkdir(parents=True)
    (build_dir / "pages_clean").mkdir(parents=True)

    page = _planche()
    region = BubbleRegion(bbox=BOX, mask=_masque(), score=0.95, cls=0)
    from manga.clean import clean_bubbles
    for i in (1, 2, 3):
        page.save(vol / f"page_{i:04d}.png")
        ckpt = checkpoints.page_checkpoint_dir(build_dir, i)
        checkpoints.save_regions(ckpt, [region], page.size)
        clean_bubbles(page, [region]).save(checkpoints.clean_page_path(build_dir, i))
        checkpoints.save_ocr(ckpt, [JP[i]])

    glossary.save(glossary.empty(), tmp_path / "sources" / "MonManga" / "glossaire.yaml")

    config = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    config["chemins"]["prompts"] = str(RACINE / "prompts")
    # Chemin ONNX inexistant : toute construction du détecteur lèverait SystemExit. C'est la
    # garantie que ces tests n'atteignent jamais la vision par ordinateur.
    config["manga"]["detection"]["model_path"] = str(tmp_path / "absent.onnx")
    # ⚠ Neutraliser le détecteur de BULLES ne suffit pas à rester hors de la vision : la
    # passe `sfx` est hors du graphe d'invalidation, donc elle tourne même sur un tome dont
    # tout le reste est en cache — 110 s d'inférence ONNX par appel, mesurées au profileur.
    config["manga"]["onomatopees"]["actif"] = False
    return config, build_dir, tmp_path


def _brancher(monkeypatch, journal, *, terminologue=True, glossariste=False):
    """Remplace `build_manga_agents` par des doubles, et journalise l'optimisation."""
    trad = _Traducteur(journal)
    term = _Terminologue(journal) if terminologue else None
    agents = {"manga_traducteur": trad}
    if term is not None:
        agents["terminologue"] = term
    if glossariste:
        agents["glossariste"] = object()

    import manga.orchestrator_manga as orch
    monkeypatch.setattr(orch, "build_manga_agents", lambda cfg, dry_run=False: agents)

    optims: list[int] = []

    def _faux_optimize(glo_path, agents_, reporter, dry=False, verbose=False):
        journal.append("optimisation")
        optims.append(1)
        return {}

    import pipeline.orchestrator as pipe
    monkeypatch.setattr(pipe, "optimize_glossary_file", _faux_optimize)
    return trad, term, optims


def _run(config, **kw):
    from core.reporter import Reporter

    from manga.orchestrator_manga import process_volume
    return process_volume("MonManga", "Vol.1", config, reporter=Reporter(), **kw)


# --------------------------------------------------------------------------- #
# L'ordre : tout le relevé avant la première traduction
# --------------------------------------------------------------------------- #

def test_la_planche_1_est_traduite_avec_un_terme_releve_sur_la_planche_3(tome3, monkeypatch):
    """LE gain du lot. Avant, la planche 1 partait avec un glossaire vide et n'aurait jamais
    pu connaître « Kataphrakt » — révélé trois planches plus loin."""
    config, _build_dir, _tmp = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    journal: list[str] = []
    trad, term, _ = _brancher(monkeypatch, journal)

    assert _run(config) is True

    assert len(term.appels) == 3, "un relevé par planche"
    assert "Kataphrakt" in trad.prompt_de(1)
    assert "Kataphrakt" in trad.prompt_de(2)


def test_tous_les_releves_precedent_toutes_les_traductions(tome3, monkeypatch):
    """Formulation directe de la structure en deux balayages : aucun `terminologie` ne doit
    apparaître après le premier `traduction` dans le journal."""
    config, _build_dir, _tmp = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    journal: list[str] = []
    _brancher(monkeypatch, journal)

    _run(config)

    assert journal.count("terminologie") == 3
    assert journal.count("traduction") == 3
    assert journal.index("traduction") > max(
        i for i, e in enumerate(journal) if e == "terminologie")


def test_les_trois_planches_recoivent_le_meme_contexte_de_glossaire(tome3, monkeypatch):
    """Un glossaire FIXE, c'est un contexte identique pour tout le volume. L'ancienne boucle
    re-sérialisait `gloss_text` après chaque planche qui ajoutait quelque chose."""
    config, _build_dir, tmp_path = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    journal: list[str] = []
    trad, _term, _ = _brancher(monkeypatch, journal)

    _run(config)

    # Le glossaire est le PREMIER bloc du prompt (cf. `_translate_page`), donc l'invariant
    # s'énonce sans découper : les trois prompts commencent par la même sérialisation, celle
    # du glossaire final. Comparer des tranches serait piégeux — la planche 1 n'a pas de
    # section « répliques précédentes », les deux autres si.
    attendu = glossary.to_text(
        glossary.load(tmp_path / "sources" / "MonManga" / "glossaire.yaml"), max_tokens=4000)
    assert "Kataphrakt" in attendu and "Sleipnir" in attendu and "Areion" in attendu
    for page in (1, 2, 3):
        assert trad.prompt_de(page).startswith(attendu)


# --------------------------------------------------------------------------- #
# Le dédoublonnage
# --------------------------------------------------------------------------- #

def test_le_dedoublonnage_precede_la_premiere_traduction(tome3, monkeypatch):
    """Il tournait en fin de tome : il nettoyait un glossaire dont les 150 planches
    s'étaient déjà servies, donc ne profitait qu'au run suivant."""
    config, _build_dir, _tmp = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    config["manga"]["modeles"]["glossariste"] = "m"
    journal: list[str] = []
    _brancher(monkeypatch, journal, glossariste=True)

    _run(config)

    assert "optimisation" in journal, "le glossariste doit être appelé"
    assert journal.index("optimisation") < journal.index("traduction")
    assert journal.count("optimisation") == 1, "une seule fois pour tout le tome"


def test_relancer_un_tome_deja_releve_ne_rappelle_pas_le_glossariste(tome3, monkeypatch):
    """Piège introduit par la passe : re-fusionner des notes déjà intégrées fait renvoyer
    `{"fusions": 1}` à `merge_notes` alors que RIEN ne change. S'y fier rappellerait le
    glossariste — un appel LLM sur tout le glossaire — à chaque relance."""
    config, _build_dir, _tmp = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    config["manga"]["modeles"]["glossariste"] = "m"
    journal: list[str] = []
    _, term, optims = _brancher(monkeypatch, journal, glossariste=True)

    _run(config)
    assert len(optims) == 1
    assert len(term.appels) == 3

    # Deuxième passage, en redemandant explicitement la traduction : les notes sont en cache,
    # donc aucun relevé — et le glossaire ne bouge pas, donc aucun dédoublonnage.
    _run(config, restart_from="traduction")
    assert len(term.appels) == 3, "aucun nouveau relevé"
    assert len(optims) == 1, "aucun nouveau dédoublonnage"


def test_le_glossaire_nest_pas_reecrit_quand_rien_ne_change(tome3, monkeypatch):
    """Corollaire de l'empreinte : le fichier n'est réécrit que sur un changement réel. Il
    l'était à chaque planche signalant une fusion fantôme — 150 écritures par run."""
    config, _build_dir, tmp_path = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    journal: list[str] = []
    _brancher(monkeypatch, journal)
    gpath = tmp_path / "sources" / "MonManga" / "glossaire.yaml"

    _run(config)
    empreinte = (gpath.read_bytes(), gpath.stat().st_mtime_ns)

    _run(config, restart_from="traduction")
    assert (gpath.read_bytes(), gpath.stat().st_mtime_ns) == empreinte


# --------------------------------------------------------------------------- #
# Portée : --page et --from
# --------------------------------------------------------------------------- #

def test_une_seule_planche_profite_du_glossaire_de_tout_le_volume(tome3, monkeypatch):
    """`--page 1` ne doit pas coûter 149 relevés, mais doit quand même voir le glossaire du
    volume : les notes déjà en cache sont re-fusionnées, gratuitement."""
    config, build_dir, _tmp = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    # La planche 3 a déjà été relevée lors d'un run précédent.
    checkpoints.save_terminologie(checkpoints.page_checkpoint_dir(build_dir, 3), NOTES_P3)
    journal: list[str] = []
    trad, term, _ = _brancher(monkeypatch, journal)

    assert _run(config, only_page=1) is True

    assert len(term.appels) == 1, "seule la planche visée peut consommer un appel"
    assert journal.count("traduction") == 1
    assert "Kataphrakt" in trad.prompt_de(1)


def test_from_rendu_ne_declenche_aucune_passe_terminologique(tome3, monkeypatch):
    """`--from rendu` ne retraduit rien : relever la terminologie n'aurait aucun effet, et
    coûterait 150 appels LLM par surprise."""
    config, build_dir, _tmp = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    for i in (1, 2, 3):
        checkpoints.save_traduction(checkpoints.page_checkpoint_dir(build_dir, i), ["Déjà"])
    journal: list[str] = []
    _trad, term, _ = _brancher(monkeypatch, journal)

    assert _run(config, restart_from="rendu") is True

    assert term.appels == []
    assert journal.count("traduction") == 0


def test_un_tome_deja_fini_ne_releve_rien(tome3, monkeypatch):
    """Aucune planche à traiter ⇒ aucune traduction ⇒ le glossaire n'a aucune influence.
    La passe doit être sautée en entier, sans même relire les caches."""
    config, build_dir, _tmp = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    journal: list[str] = []
    _brancher(monkeypatch, journal)
    _run(config)                       # produit les pages finales
    journal.clear()

    assert _run(config) is True
    assert journal == []


# --------------------------------------------------------------------------- #
# Arrêt propre pendant la passe
# --------------------------------------------------------------------------- #

def test_un_arret_pendant_la_passe_conserve_les_releves_deja_faits(tome3, monkeypatch):
    """La passe est une TROISIÈME fenêtre où un arrêt peut tomber. Elle doit rendre la main
    proprement, assembler ce qui existe, et n'avoir rien perdu du glossaire acquis."""
    config, build_dir, tmp_path = tome3
    config["manga"]["modeles"]["terminologue"] = "m"
    journal: list[str] = []
    _brancher(monkeypatch, journal)
    gpath = tmp_path / "sources" / "MonManga" / "glossaire.yaml"

    # `process_volume` appelle `clear_stop` en entrée (délibérément : l'arrêt d'hier ne doit
    # pas bloquer le run d'aujourd'hui), donc écrire le fichier STOP avant ne suffirait pas.
    # L'arrêt est adossé à un ÉTAT et non à un compteur d'appels : dès que le premier relevé
    # a atterri dans le glossaire, on demande l'arrêt. Le glossaire est vide pendant tout le
    # balayage A, la fenêtre visée est donc bien celle de la passe terminologique.
    import core.control as control
    monkeypatch.setattr(control, "should_stop",
                        lambda _b: glossary.total(glossary.load(gpath) or {}) > 0)

    assert _run(config) is False
    assert journal.count("terminologie") == 1, "arrêt juste après le premier relevé"
    assert journal.count("traduction") == 0, "aucune traduction ne doit avoir commencé"
    # L'acquis terminologique est sur disque, pas perdu avec le run.
    assert "Sleipnir" in [e["nom"] for e in glossary.load(gpath)["objets"]]
    assert checkpoints.load_terminologie(
        checkpoints.page_checkpoint_dir(build_dir, 1)) is not None
