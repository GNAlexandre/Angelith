# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le pont entre l'orchestrateur et l'interface graphique, et la file de travail.

Ce qui est testé ici est **le contrat**, pas les widgets :

- un `ReporterQt` doit être un `Reporter` complet, sinon un orchestrateur qui appelle une
  méthode oubliée fait tomber un run de 150 planches dans un fil d'arrière-plan, où l'erreur
  n'est visible que si on pense à regarder le journal ;
- la **file** doit sérialiser, fusionner ce qui doit l'être, et ne jamais perdre une tâche —
  c'est elle qui remplace les deux `QThread` créés à la volée de la 1.1.0 et ses trois trous
  de concurrence ;
- le **verrou par planche** doit rester par planche : une tâche sur la 12 ne verrouille pas
  la 30, mais un run verrouille tout.

Le reste (fenêtres, canevas) n'est pas testé : ce serait hors de proportion pour ce dépôt, et
le test de fumée qui compte — ouvrir un vrai tome — se fait à la main.

⚠ `pytest.importorskip` : PySide6 vit dans `requirements-gui.txt`, séparé exprès. Un
contributeur qui n'installe que le socle et la brique manga doit pouvoir lancer `pytest` sans
rien voir échouer — même convention que le saut sur police absente de `conftest.py`.
"""
from __future__ import annotations

import inspect
import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

from core.reporter import Reporter                                          # noqa: E402
from gui.travailleur import (GENRE_EDITION, GENRE_OCR, GENRE_RUN,           # noqa: E402
                             FilDeTravail, ReporterQt, SignauxTravail, Tache,
                             build_dir_de, progression_de_stage)


class _Espion:
    """Collecte ce qui est émis, sans boucle d'événements Qt : un signal émis vers une
    fonction Python simple est délivré immédiatement quand émetteur et récepteur sont dans le
    même fil."""

    def __init__(self):
        self.signaux = SignauxTravail()
        self.lignes: list[tuple[str, str]] = []
        self.progression: list[tuple[int, int]] = []
        self.debuts: list[tuple] = []
        self.fins: list[tuple] = []
        self.signaux.ligne.connect(lambda n, m: self.lignes.append((n, m)))
        self.signaux.progression.connect(lambda a, b: self.progression.append((a, b)))
        self.signaux.debut.connect(lambda p, g, l: self.debuts.append((p, g, l)))
        self.signaux.fin.connect(lambda p, g, ok, m: self.fins.append((p, g, ok, m)))
        self.reporter = ReporterQt(self.signaux)


# --------------------------------------------------------------------------- #
# ReporterQt
# --------------------------------------------------------------------------- #

def test_reporterqt_implemente_tout_le_protocole():
    """L'orchestrateur appelle ces méthodes sans savoir qui écoute. Une seule manquante et le
    run tombe — dans un fil d'arrière-plan, donc sans trace lisible."""
    attendues = [nom for nom, _ in inspect.getmembers(Reporter, inspect.isfunction)
                 if not nom.startswith("__")]
    assert [nom for nom in attendues if not hasattr(ReporterQt, nom)] == []


def test_les_messages_partent_avec_leur_niveau():
    espion = _Espion()
    espion.reporter.info("un message")
    espion.reporter.warn("un incident")
    espion.reporter.verbose("12,3 s")
    espion.reporter.stage("Page 4/10 — page_0004.png (traduction)")

    assert [n for n, _ in espion.lignes] == ["info", "warn", "verbose", "stage"]
    assert espion.lignes[1][1] == "un incident"


def test_un_prefixe_distingue_les_taches_unitaires():
    """Les tâches de l'éditeur écrivent dans le même journal et le même `perf.log` que les
    runs : sans préfixe, on ne saurait pas laquelle a produit une ligne."""
    espion = _Espion()
    ReporterQt(espion.signaux, prefixe="[bulle 3] ").info("relue")
    assert espion.lignes[0][1] == "[bulle 3] relue"


def test_la_progression_se_deduit_du_libelle_de_planche():
    """Sans imposer un second canal à l'orchestrateur, qui n'a pas à connaître l'interface."""
    espion = _Espion()
    espion.reporter.stage("Page 12/131 — 089.jpg (traduction, rendu)")
    assert espion.progression == [(12, 131)]


def test_un_lot_met_la_barre_en_indetermine():
    """Un lot n'a pas de total connu au moment où il commence : la barre doit le dire plutôt
    que d'inventer un pourcentage."""
    espion = _Espion()
    espion.reporter.stage("Lot planches 21→40 (118 bulles)")
    assert espion.progression == [(21, 0)]


@pytest.mark.parametrize("libelle, attendu", [
    ("Page 1/1 — a.png (rendu)", (1, 1)),
    ("Lot planches 3→7 (40 bulles)", (3, 0)),
    ("n'importe quoi", (0, 0)),
    ("", (0, 0)),
])
def test_progression_de_stage(libelle, attendu):
    assert progression_de_stage(libelle) == attendu


def test_verbose_et_warn_vont_aussi_dans_perf_log(tmp_path):
    """`ReporterQt` hérite de `Reporter`, donc de `set_verbose_log`.

    ⚠ C'est ce que la 1.1.0 n'appelait NULLE PART : `Reporter._to_log` teste
    `getattr(self, "_vlog", None)` et sautait donc toutes les écritures en silence. `perf.log`
    n'existait jamais pour un run lancé depuis l'interface, alors que les docstrings de
    `gui/travailleur.py` affirmaient le contraire."""
    espion = _Espion()
    log = tmp_path / "perf.log"
    espion.reporter.set_verbose_log(log)
    espion.reporter.verbose("9,7 s/planche")
    espion.reporter.warn("bulle vide page 12")
    espion.reporter.info("ceci ne va PAS au log")

    contenu = log.read_text(encoding="utf-8")
    assert "9,7 s/planche" in contenu
    assert "⚠ bulle vide page 12" in contenu
    assert "ceci ne va PAS au log" not in contenu


def test_finish_et_stopped_sont_annonces():
    espion = _Espion()
    espion.reporter.finish(["tome.cbz", "tome.pdf"])
    espion.reporter.stopped(12, 150)
    assert "tome.cbz" in espion.lignes[0][1]
    assert espion.lignes[1][0] == "warn" and "12/150" in espion.lignes[1][1]


# --------------------------------------------------------------------------- #
# La file de travail
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def qt_app():
    """Une `QCoreApplication` pour tout le module.

    ⚠ Indispensable, et pas un détail de plomberie : un signal émis depuis le fil de travail
    vers un récepteur du fil principal est mis EN FILE par Qt, et n'est délivré que par une
    boucle d'événements. Sans elle, `debut`/`fin` n'arrivent jamais — ce qui est exactement ce
    qui se passerait dans une interface figée, donc un test qui l'oublierait passerait à côté
    du comportement réel."""
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def _drainer(fil: FilDeTravail, attendu: int, espion: _Espion, delai: float = 10.0) -> None:
    """Fait tourner la file jusqu'à `attendu` tâches terminées, en pompant les événements Qt.

    Le fil est un vrai `QThread` : rien n'est simulé, et c'est bien la livraison différée des
    signaux qu'on éprouve."""
    import time

    from PySide6.QtCore import QCoreApplication

    fil.start()
    limite = time.monotonic() + delai
    while len(espion.fins) < attendu and time.monotonic() < limite:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    fil.arreter()
    fil.wait(2000)
    QCoreApplication.processEvents()


def test_la_file_execute_les_taches_dans_l_ordre(qt_app):
    espion = _Espion()
    fil = FilDeTravail(espion.signaux)
    ordre: list[int] = []
    for n in range(4):
        fil.soumettre(Tache(genre=GENRE_EDITION, planche=n,
                            fonction=lambda n=n: ordre.append(n) or f"fait {n}"))
    _drainer(fil, 4, espion)

    assert ordre == [0, 1, 2, 3], "un fil unique, donc un ordre garanti"
    assert [p for p, _g, ok, _m in espion.fins if ok] == [0, 1, 2, 3]


def test_une_tache_qui_leve_ne_tue_pas_le_fil(qt_app):
    """Le fil sert toute la session : une erreur d'édition ne doit pas emporter la file."""
    espion = _Espion()
    fil = FilDeTravail(espion.signaux)

    def _explose():
        raise ValueError("zone hors planche")

    fil.soumettre(Tache(genre=GENRE_EDITION, planche=1, fonction=_explose))
    fil.soumettre(Tache(genre=GENRE_EDITION, planche=2, fonction=lambda: "suivante"))
    _drainer(fil, 2, espion)

    assert espion.fins[0][2] is False and "zone hors planche" in espion.fins[0][3]
    assert espion.fins[1][2] is True, "la tâche suivante s'exécute quand même"

    # ⚠ **Le nom de classe a changé de canal** (`PLAN-19` L19.7). Il partait en « warn », donc
    # dans le journal ET dans la barre d'état : `ValueError` était la seule chose que
    # l'utilisateur voyait d'un échec. Il est excellent dans un rapport de bug et inutilisable
    # au moment où l'on cherche quoi faire.
    #
    # Deux lignes désormais, et le test garde les deux :
    # · le canal « verbose » porte le détail technique, pour le rapport de bug ;
    # · le message de `fin` — qui, lui, remonte à l'écran — porte ce qui a échoué et ce qu'on
    #   peut tenter, sans nommer une classe Python.
    assert any(n == "verbose" and "ValueError" in m for n, m in espion.lignes),         "le détail technique doit rester dans le journal"
    visible = espion.fins[0][3]
    assert "ValueError" not in visible, "l'écran ne montre pas un nom de classe Python"
    assert "édition de zone" in visible and "journal" in visible.lower()


def test_les_demandes_identiques_sont_fusionnees(qt_app):
    """Cliquer trois fois sur « Relire » ne doit pas payer trois OCR. La fusion est OPT-IN
    (`cle_fusion`) : trois éditions de zone successives, elles, sont trois gestes distincts
    qu'on n'a pas le droit de perdre."""
    espion = _Espion()
    fil = FilDeTravail(espion.signaux)
    fusion = [fil.soumettre(Tache(genre=GENRE_OCR, planche=7, fonction=lambda: "ocr",
                                  cle_fusion=(7, GENRE_OCR))) for _ in range(3)]
    distinctes = [fil.soumettre(Tache(genre=GENRE_EDITION, planche=7, fonction=lambda: "zone"))
                  for _ in range(3)]

    assert fusion == [True, False, False], "une seule relecture retenue"
    assert distinctes == [True, True, True], "aucune édition perdue"
    _drainer(fil, 4, espion)
    assert len(espion.fins) == 4


def test_une_tache_de_run_verrouille_tout_et_une_tache_de_planche_non(qt_app):
    """Le cœur du lot 18 : `planche=None` dit « je touche tout le tome »."""
    espion = _Espion()
    fil = FilDeTravail(espion.signaux)
    vu: list = []

    def _observer():
        vu.append((fil.planche_en_cours(), fil.touche_tout()))
        return "ok"

    fil.soumettre(Tache(genre=GENRE_OCR, planche=12, fonction=_observer))
    fil.soumettre(Tache(genre=GENRE_RUN, planche=None, fonction=_observer))
    _drainer(fil, 2, espion)

    assert vu == [(12, False), (None, True)]


def test_le_signal_de_debut_nomme_la_planche_et_le_genre(qt_app):
    """C'est lui qui pilote le grisage : sans la planche, l'interface ne pourrait que
    verrouiller tout, ce qui est exactement le défaut de la 1.1.0."""
    espion = _Espion()
    fil = FilDeTravail(espion.signaux)
    fil.soumettre(Tache(genre=GENRE_OCR, planche=12, fonction=lambda: "ok",
                        libelle="Relecture OCR de la bulle 3"))
    _drainer(fil, 1, espion)

    assert espion.debuts == [(12, GENRE_OCR, "Relecture OCR de la bulle 3")]


# --------------------------------------------------------------------------- #
# Cibles
# --------------------------------------------------------------------------- #

def test_le_dossier_de_build_vise_le_bon_endroit(tmp_path):
    """C'est là que le fichier `STOP` sera écrit : viser à côté rendrait le bouton
    « Arrêter » silencieusement inopérant."""
    config = {"chemins": {"sources": str(tmp_path / "s"), "build": str(tmp_path / "b")},
              "manga": {}}
    assert build_dir_de(config, "manga", "P", "Vol.1") == tmp_path / "b" / "P" / "Vol.1" / "manga"
    assert build_dir_de(config, "ln", "P", "Vol.1") == tmp_path / "b" / "P" / "Vol.1"


def test_la_tache_de_run_appelle_process_volume_avec_les_bons_arguments(tmp_path, monkeypatch):
    """Le chemin le plus risqué de l'interface : un appel dont la signature dérive tombe dans
    un fil d'arrière-plan. C'est aussi ce qui garantit que le bouton « Appliquer » est bien
    `run_manga.py --page N --from rendu`, et pas un chemin de rendu parallèle."""
    import manga.orchestrator_manga as orch
    from gui.travailleur import tache_run

    vus = {}

    def _faux(projet, tome, config, *, reporter=None, force=False, restart_from=None,
              only_page=None, **_kw):
        vus.update(projet=projet, tome=tome, force=force, depuis=restart_from,
                   page=only_page, reporter=type(reporter).__name__)
        return True

    monkeypatch.setattr(orch, "process_volume", _faux)
    monkeypatch.setattr("core.cli.precharger_modeles", lambda *a, **k: None)
    monkeypatch.setattr("core.cli.shielded_unload", lambda *a, **k: None)

    config = {"chemins": {"sources": str(tmp_path / "s"), "build": str(tmp_path / "b")},
              "manga": {"modeles": {}}, "options": {"dry_run": True}}
    espion = _Espion()
    tache = tache_run(brique="manga", projet="P", tome="Vol.1", config=config,
                      reporter=espion.reporter, depuis="rendu", page=7)
    tache.fonction()

    assert vus == {"projet": "P", "tome": "Vol.1", "force": False, "depuis": "rendu",
                   "page": 7, "reporter": "ReporterQt"}
    assert tache.planche is None, "un run touche tout le tome"


def test_un_relettrage_ne_precharge_aucun_modele(tmp_path, monkeypatch):
    """`--from rendu` n'appelle jamais le LLM : y monter un modèle de 27 B — et évincer à la
    fin celui que l'utilisateur avait chargé pour autre chose — serait un pur gaspillage.
    C'est la garde `traduira` de `run_manga.py`, que l'interface doit reproduire."""
    import manga.orchestrator_manga as orch
    from gui.travailleur import tache_run

    precharges = []
    monkeypatch.setattr(orch, "process_volume", lambda *a, **k: True)
    monkeypatch.setattr("core.cli.precharger_modeles",
                        lambda cfg, models, **k: precharges.append(list(models)))
    monkeypatch.setattr("core.cli.shielded_unload", lambda *a, **k: None)

    config = {"chemins": {"sources": str(tmp_path / "s"), "build": str(tmp_path / "b")},
              "manga": {"modeles": {"manga_traducteur": {"model": "qwen3.6:27b"}}},
              "options": {}}
    espion = _Espion()
    for depuis, attendu in [("rendu", []), ("traduction", ["qwen3.6:27b"])]:
        precharges.clear()
        tache_run(brique="manga", projet="P", tome="V", config=config,
                  reporter=espion.reporter, depuis=depuis).fonction()
        assert precharges == [attendu], f"--from {depuis}"


# ─────────────────────────────────────────────────────────────────────────────
# CANAL DE PROGRESSION CHIFFRÉ
#
# La barre lisait l'avancement dans le LIBELLÉ humain de `stage`, à l'expression régulière.
# `Reporter.progres` le dit en chiffres. Le repli par regex reste en place pour les libellés
# non instrumentés — ces deux tests verrouillent le fait que les deux marchent.
# ─────────────────────────────────────────────────────────────────────────────

def test_progres_emet_la_progression():
    from gui.travailleur import ReporterQt, SignauxTravail

    signaux = SignauxTravail()
    vus = []
    signaux.progression.connect(lambda c, t: vus.append((c, t)))

    ReporterQt(signaux).progres(12, 131)

    assert vus == [(12, 131)]


def test_le_repli_par_libelle_reste_actif():
    """Un libellé non instrumenté doit continuer d'alimenter la barre : retirer le repli en
    même temps que l'on ajoute le canal ferait un trou sur toutes les étapes non converties."""
    from gui.travailleur import ReporterQt, SignauxTravail

    signaux = SignauxTravail()
    vus = []
    signaux.progression.connect(lambda c, t: vus.append((c, t)))

    ReporterQt(signaux).stage("Page 12/131 — page_0012.png (ocr)")

    assert vus == [(12, 131)]


def test_progres_fait_partie_du_contrat_reporter():
    """Même garde que pour le reste de `ReporterQt` : un orchestrateur qui appelle `progres`
    sur un `Reporter` de base ne doit pas faire tomber un run de 150 planches."""
    from core.reporter import Reporter, RichReporter
    from gui.travailleur import ReporterQt

    for classe in (Reporter, RichReporter, ReporterQt):
        assert callable(getattr(classe, "progres", None)), classe.__name__
