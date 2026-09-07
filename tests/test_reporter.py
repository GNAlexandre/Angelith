# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de reporter.py : Reporter (texte simple) et RichReporter (TUI, barres Rich)."""
import datetime
import sys
from types import SimpleNamespace

import pytest

from pipeline import reporter
from pipeline.reporter import Reporter, RichReporter


def _fake_plan(**over):
    base = dict(project="Proj", volume="Vol.1", langs={"fr": object()}, pivot="fr",
               image_lang="fr", mode="traduction", warnings=[], n_chapters=2)
    base.update(over)
    return SimpleNamespace(**base)


def _lignes_perf(log_path) -> list[str]:
    """Lignes de PERF de perf.log, sans l'en-tête de run (`# Angelith … — commande`)
    ni les lignes vides de séparation entre runs empilés. Les tests ci-dessous vérifient
    le contenu exact des lignes de perf ; l'en-tête a son test dédié."""
    return [ln for ln in log_path.read_text(encoding="utf-8").splitlines()
            if ln and not ln.startswith("#")]


def test_reporter_volume_prints_summary(capsys):
    Reporter().volume(_fake_plan())
    out = capsys.readouterr().out
    assert "Proj" in out and "Vol.1" in out and "fr" in out


def test_reporter_volume_prints_warnings(capsys):
    Reporter().volume(_fake_plan(warnings=["attention à ceci"]))
    out = capsys.readouterr().out
    assert "attention à ceci" in out


def test_reporter_chapter_and_stage_and_block(capsys):
    r = Reporter()
    r.chapter(2, 5, "Le Réveil")
    r.stage("traduction")
    r.block(3, 10)
    out = capsys.readouterr().out
    assert "2/5" in out and "Le Réveil" in out
    assert "traduction" in out
    assert "3/10" in out


def test_reporter_info(capsys):
    Reporter().info("un message")
    assert "un message" in capsys.readouterr().out


def test_reporter_verbose_prints_and_writes_to_log(tmp_path, capsys):
    r = Reporter()
    log_path = tmp_path / "perf.log"
    r.set_verbose_log(log_path)
    r.verbose("[traduction] bloc 1/1 : 1.0s")
    out = capsys.readouterr().out
    assert "⏱" in out and "[traduction] bloc 1/1" in out
    assert _lignes_perf(log_path) == ["[traduction] bloc 1/1 : 1.0s"]


def test_reporter_verbose_without_log_does_not_crash(capsys):
    Reporter().verbose("sans log")   # set_verbose_log jamais appelé
    assert "sans log" in capsys.readouterr().out


def test_reporter_warn_prints_and_writes_to_log(tmp_path, capsys):
    """Les incidents (budget thinking épuisé, bloc redécoupé, repli) doivent atterrir
    dans perf.log : ils partaient jusqu'ici sur stdout via un print() brut et étaient
    perdus — impossible, après un run de 14 h, de savoir quels blocs avaient dérapé."""
    r = Reporter()
    log_path = tmp_path / "perf.log"
    r.set_verbose_log(log_path)
    r.warn("[traduction] bloc 1/2 : emballement → redécoupage en 2 et relance")
    out = capsys.readouterr().out
    assert "⚠" in out and "redécoupage" in out
    assert _lignes_perf(log_path) == [
        "⚠ [traduction] bloc 1/2 : emballement → redécoupage en 2 et relance"]


def test_reporter_warn_without_log_does_not_crash(capsys):
    Reporter().warn("sans log")
    assert "sans log" in capsys.readouterr().out


def test_reporter_log_lines_carry_the_chapter_number(tmp_path):
    """Une ligne de perf.log ne portait ni horodatage ni chapitre : la recaler sur un
    chapitre imposait de croiser `.checkpoints/` et `RAPPORT.md`."""
    r = Reporter()
    log_path = tmp_path / "perf.log"
    r.set_verbose_log(log_path)
    r.chapter(15, 16, "Au cœur des ténèbres")
    r.verbose("[traduction] bloc 1/1 : 1699.8s")
    r.warn("[traduction] bloc 1/1 : emballement")
    lignes = _lignes_perf(log_path)
    assert lignes[0].startswith("ch15 [traduction]")
    assert lignes[1].startswith("ch15 ⚠ [traduction]")


def test_perf_log_header_carries_version_date_and_command(tmp_path, monkeypatch):
    """perf.log s'ouvre en "a" : sans en-tête, rien n'indiquait quelle VERSION ni quelle
    COMMANDE avait produit quelle ligne, alors qu'on s'en sert justement pour comparer
    des perfs d'avant/après un changement de code."""
    from core.version import __version__

    # ⚠ Le dossier est construit avec `Path`, donc NATIF à la plateforme. Ce test codait
    # `C:\x\run_manga.py` : sur Linux, `\` n'est pas un séparateur, `Path(...).name` rend la
    # chaîne entière — le code faisait ce qu'il fallait, c'est le chemin d'essai qui n'avait
    # aucun sens sur cet OS. Le vrai `sys.argv[0]` est toujours natif.
    dossier = tmp_path / "x"
    monkeypatch.setattr(sys, "argv",
                        [str(dossier / "run_manga.py"), "Mon Manga", "Vol.1", "--verbose"])
    log_path = tmp_path / "perf.log"
    Reporter().set_verbose_log(log_path)

    entetes = [ln for ln in log_path.read_text(encoding="utf-8").splitlines()
               if ln.startswith("#")]
    assert len(entetes) == 1
    assert f"Angelith {__version__}" in entetes[0]
    assert "run_manga.py" in entetes[0]
    assert str(dossier) not in entetes[0]         # argv[0] réduit au nom du script
    assert '"Mon Manga"' in entetes[0]            # argument à espace : requotté, relançable
    assert datetime.date.today().isoformat() in entetes[0]
    # Pas de première ligne vide sur un fichier neuf.
    assert not log_path.read_text(encoding="utf-8").startswith("\n")


def test_perf_log_header_separates_stacked_runs(tmp_path, monkeypatch):
    """Deux runs dans le MÊME perf.log : un en-tête chacun, et les lignes de perf de
    chacun restent attribuables à sa commande."""
    log_path = tmp_path / "perf.log"

    monkeypatch.setattr(sys, "argv", ["run.py", "Proj", "Vol.1", "--verbose"])
    r1 = Reporter(); r1.set_verbose_log(log_path); r1.verbose("premier run")

    monkeypatch.setattr(sys, "argv", ["run_manga.py", "Proj", "Vol.1", "--from", "rendu"])
    r2 = Reporter(); r2.set_verbose_log(log_path); r2.verbose("second run")

    contenu = log_path.read_text(encoding="utf-8")
    entetes = [ln for ln in contenu.splitlines() if ln.startswith("#")]
    assert len(entetes) == 2
    assert "run.py" in entetes[0] and "run_manga.py" in entetes[1]
    assert _lignes_perf(log_path) == ["premier run", "second run"]
    assert "\n\n#" in contenu   # ligne vide de séparation entre les deux runs


def test_reporter_finish_and_stopped(capsys):
    r = Reporter()
    r.finish(["a.docx", "b.epub"])
    r.stopped(2, 5)
    out = capsys.readouterr().out
    assert "a.docx" in out and "b.epub" in out
    assert "2/5" in out


def test_reporter_context_manager_is_noop():
    with Reporter() as r:
        assert isinstance(r, Reporter)


# --------------------------------------------------------------------------- #
# RichReporter : mêmes garanties, + verbose() DOIT passer par Console.print
# (pas un print() brut, qui corromprait la barre de progression Live) — c'est
# la régression corrigée (A4 : RichReporter n'avait aucune surcharge de verbose()).
# --------------------------------------------------------------------------- #

@pytest.fixture
def rich_reporter():
    pytest.importorskip("rich")
    return RichReporter()


def test_rich_reporter_verbose_uses_console_print_not_bare_print(rich_reporter, monkeypatch):
    calls = []
    monkeypatch.setattr(rich_reporter.console, "print", lambda *a, **k: calls.append(a))
    rich_reporter.verbose("[traduction] bloc 1/1 : 1.0s")
    assert calls
    assert any("[traduction] bloc 1/1" in str(a) for a in calls[0])


def test_rich_reporter_verbose_also_writes_to_log(rich_reporter, tmp_path, monkeypatch):
    monkeypatch.setattr(rich_reporter.console, "print", lambda *a, **k: None)
    log_path = tmp_path / "perf.log"
    rich_reporter.set_verbose_log(log_path)
    rich_reporter.verbose("ligne de perf")
    assert _lignes_perf(log_path) == ["ligne de perf"]


def test_rich_reporter_info_uses_console_print(rich_reporter, monkeypatch):
    calls = []
    monkeypatch.setattr(rich_reporter.console, "print", lambda *a, **k: calls.append(a))
    rich_reporter.info("un message")
    assert calls


def test_rich_reporter_warn_uses_console_print_not_bare_print(rich_reporter, monkeypatch, capsys):
    """Même exigence que verbose() : un print() brut corromprait la barre Live."""
    calls = []
    monkeypatch.setattr(rich_reporter.console, "print", lambda *a, **k: calls.append(a))
    rich_reporter.warn("emballement → redécoupage")
    assert calls
    assert any("redécoupage" in str(a) for a in calls[0])
    assert "redécoupage" not in capsys.readouterr().out


def test_rich_reporter_warn_also_writes_to_log(rich_reporter, tmp_path, monkeypatch):
    monkeypatch.setattr(rich_reporter.console, "print", lambda *a, **k: None)
    log_path = tmp_path / "perf.log"
    rich_reporter.set_verbose_log(log_path)
    rich_reporter.warn("un incident")
    assert _lignes_perf(log_path) == ["⚠ un incident"]


# --------------------------------------------------------------------------- #
# `stage()` SANS `volume()` — le cas des briques manga et scan.
# `volume()` lit un `VolumePlan` de LN (langues, pivot, chapitres) et c'est LUI qui
# crée la tâche « Chapitres ». Les deux autres briques écrivent leur propre en-tête et
# ne l'appellent donc jamais : `_chap_task` reste None. `stage()` le passait tel quel à
# rich, qui mourait sur `KeyError: None` — la brique scan tombait sur sa PREMIÈRE étape,
# avant d'avoir lu une seule page. Les tests de `scan/` ne l'avaient pas vu : ils
# injectent un reporter factice, et seul le vrai RichReporter porte ce piège.
# --------------------------------------------------------------------------- #

def test_rich_reporter_stage_sans_volume_n_explose_pas(rich_reporter, monkeypatch):
    """Le cas exact qui tuait `run_ocr.py` au démarrage."""
    calls = []
    monkeypatch.setattr(rich_reporter.console, "print", lambda *a, **k: calls.append(a))
    assert rich_reporter._chap_task is None
    rich_reporter.stage("analyse")
    # L'étape n'est pas seulement survécue, elle est ÉCRITE : sinon la brique scan
    # resterait muette entre deux étapes qui durent des minutes.
    assert any("analyse" in str(a) for a in calls[0])


def test_rich_reporter_stage_avec_volume_pilote_la_barre(rich_reporter, monkeypatch):
    """Le chemin LN est inchangé : là où la tâche existe, `stage()` la met à jour
    plutôt que d'écrire une ligne (qui s'empilerait sous la barre Live)."""
    vus = []
    monkeypatch.setattr(rich_reporter.progress, "update",
                        lambda task, **k: vus.append((task, k)))
    monkeypatch.setattr(rich_reporter.console, "print", lambda *a, **k: None)
    monkeypatch.setattr(rich_reporter.console, "rule", lambda *a, **k: None)
    rich_reporter.volume(_fake_plan())
    assert rich_reporter._chap_task is not None
    rich_reporter.stage("traduction")
    assert vus and vus[-1][1].get("description") == "traduction"


def test_les_briques_sans_volume_survivent_a_leur_sequence_de_reporter(rich_reporter,
                                                                       monkeypatch):
    """La séquence réelle de `scan/orchestrator_scan.py`, dans l'ordre, sur le vrai
    RichReporter. `block()` crée sa tâche paresseusement — c'est lui qui porte la barre
    de progression de la brique — et `finish()` ne doit pas retomber sur la tâche
    absente."""
    monkeypatch.setattr(rich_reporter.console, "print", lambda *a, **k: None)
    rich_reporter.info("=== Projet / Vol.1 === 270 page(s)")
    rich_reporter.stage("analyse")
    rich_reporter.stage("lecture (270 page(s) à lire)")
    rich_reporter.block(1, 270)
    rich_reporter.verbose("page 100 : 16 colonnes")
    rich_reporter.warn("page 12 suspecte")
    rich_reporter.finish(["RAPPORT.md"])


# --------------------------------------------------------------------------- #
#  close() : hygiene de descripteur
#
#  `set_verbose_log` ouvrait `perf.log` et RIEN ne le refermait. Sans effet en ligne de
#  commande (le processus se termine), mais l'interface construit un reporter PAR run :
#  trente relettrages laissaient trente descripteurs ouverts sur le meme fichier. Sous
#  Windows un handle ouvert VERROUILLE le fichier, si bien que l'ouvrir dans un editeur ou
#  l'effacer pouvait echouer sans qu'on comprenne pourquoi.
# --------------------------------------------------------------------------- #

def test_close_referme_le_fichier(tmp_path):
    r = Reporter()
    r.set_verbose_log(tmp_path / "perf.log")
    r.close()
    assert getattr(r, "_vlog", None) is None


def test_close_est_idempotent(tmp_path):
    r = Reporter()
    r.set_verbose_log(tmp_path / "perf.log")
    r.close()
    r.close()          # ne doit pas lever


def test_close_sans_log_ouvert_ne_leve_pas():
    """L'appelant ne sait pas si `--verbose` etait actif : il ferme sans se poser la
    question, sinon il faudrait un test au point d'appel."""
    Reporter().close()


def test_close_ne_perd_aucune_ligne(tmp_path):
    """`_to_log` fait `flush()` a chaque ligne : aucune donnee n'est en jeu, et le test doit
    le prouver plutot que de le supposer."""
    chemin = tmp_path / "perf.log"
    r = Reporter()
    r.set_verbose_log(chemin)
    r.verbose("mesure importante")
    r.close()
    assert "mesure importante" in chemin.read_text(encoding="utf-8")


def test_le_fichier_est_supprimable_apres_close(tmp_path):
    """C'est le symptome concret qu'on corrige : un handle vivant verrouille le fichier."""
    chemin = tmp_path / "perf.log"
    r = Reporter()
    r.set_verbose_log(chemin)
    r.verbose("ligne")
    r.close()
    chemin.unlink()
    assert not chemin.exists()


def test_ecrire_apres_close_ne_leve_pas(tmp_path):
    """Une tache en retard ne doit pas faire tomber l'interface parce qu'on a ferme."""
    r = Reporter()
    r.set_verbose_log(tmp_path / "perf.log")
    r.close()
    r.verbose("apres coup")


# --------------------------------------------------------------------------- #
#  Console et fichier découplés — le trou d'observabilité du run de nuit
#
#  `perf.log` n'existait QUE si `--verbose`. Un run lancé le soir sans ce flag ne laissait
#  donc aucune trace fichier : au matin, plus rien ne disait quelle planche avait dérapé ni
#  pourquoi, alors même que `warn()` écrivait déjà dans ce fichier. Le flag ne pilote plus
#  que ce qui s'IMPRIME.
# --------------------------------------------------------------------------- #

def test_le_log_recoit_la_perf_meme_console_muette(tmp_path, capsys):
    log_path = tmp_path / "perf.log"
    r = Reporter()
    r.set_verbose_log(log_path)
    r.set_console_verbose(False)
    r.verbose("detection 1.20s")

    assert _lignes_perf(log_path) == ["detection 1.20s"]
    assert "detection" not in capsys.readouterr().out


def test_la_console_reprend_la_perf_quand_on_la_demande(tmp_path, capsys):
    log_path = tmp_path / "perf.log"
    r = Reporter()
    r.set_verbose_log(log_path)
    r.set_console_verbose(True)
    r.verbose("detection 1.20s")

    assert _lignes_perf(log_path) == ["detection 1.20s"]
    assert "detection 1.20s" in capsys.readouterr().out


def test_sans_reglage_explicite_la_console_parle(tmp_path, capsys):
    """Défaut `True` : un `Reporter` construit à la main se comporte comme avant."""
    Reporter().verbose("ligne")
    assert "ligne" in capsys.readouterr().out


def test_les_incidents_restent_toujours_affiches(tmp_path, capsys):
    """⚠ `set_console_verbose(False)` ne doit PAS museler `warn` : un incident n'est pas une
    mesure de perf, et le taire sur un run interactif serait un pas en arrière."""
    log_path = tmp_path / "perf.log"
    r = Reporter()
    r.set_verbose_log(log_path)
    r.set_console_verbose(False)
    r.warn("bulle 3 en débordement")

    assert "bulle 3 en débordement" in capsys.readouterr().out
    assert any("bulle 3" in l for l in _lignes_perf(log_path))


def test_rich_reporter_suit_la_meme_regle(tmp_path, rich_reporter):
    log_path = tmp_path / "perf.log"
    rich_reporter.set_verbose_log(log_path)
    rich_reporter.set_console_verbose(False)
    rich_reporter.verbose("ocr 0.40s")
    assert _lignes_perf(log_path) == ["ocr 0.40s"]


# ─────────────────────────────────────────────────────────────────────────────
# ROTATION DE perf.log
#
# Le fichier s'ouvre en "a" et les runs s'y empilent — c'est voulu. Mais sans plafond il
# grossissait sur toute la vie du projet, et personne ne relit le début d'un fichier de 40 Mo.
# ─────────────────────────────────────────────────────────────────────────────

def test_un_petit_log_n_est_pas_touche(tmp_path):
    """L'empilement est tout l'intérêt du fichier : comparer deux runs se fait dans UN
    fichier. On n'archive que quand il devient illisible."""
    log = tmp_path / "perf.log"
    log.write_text("run precedent\n", encoding="utf-8")

    reporter._faire_tourner(log)

    assert log.read_text(encoding="utf-8") == "run precedent\n"
    assert not (tmp_path / "perf.log.1").exists()


def test_au_dela_du_plafond_le_log_est_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter, "TAILLE_MAX_LOG", 100)
    log = tmp_path / "perf.log"
    log.write_text("x" * 200, encoding="utf-8")

    reporter._faire_tourner(log)

    assert not log.exists()
    assert (tmp_path / "perf.log.1").read_text(encoding="utf-8") == "x" * 200


def test_les_archives_se_decalent_sans_s_ecraser(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter, "TAILLE_MAX_LOG", 100)
    monkeypatch.setattr(reporter, "ARCHIVES_LOG", 3)
    log = tmp_path / "perf.log"
    for i in (1, 2):
        (tmp_path / f"perf.log.{i}").write_text(f"archive {i}", encoding="utf-8")
    log.write_text("y" * 200, encoding="utf-8")

    reporter._faire_tourner(log)

    assert (tmp_path / "perf.log.1").read_text(encoding="utf-8") == "y" * 200
    assert (tmp_path / "perf.log.2").read_text(encoding="utf-8") == "archive 1"
    assert (tmp_path / "perf.log.3").read_text(encoding="utf-8") == "archive 2"


def test_la_plus_ancienne_archive_part(tmp_path, monkeypatch):
    monkeypatch.setattr(reporter, "TAILLE_MAX_LOG", 100)
    monkeypatch.setattr(reporter, "ARCHIVES_LOG", 2)
    log = tmp_path / "perf.log"
    for i in (1, 2):
        (tmp_path / f"perf.log.{i}").write_text(f"archive {i}", encoding="utf-8")
    log.write_text("z" * 200, encoding="utf-8")

    reporter._faire_tourner(log)

    assert (tmp_path / "perf.log.1").read_text(encoding="utf-8") == "z" * 200
    assert (tmp_path / "perf.log.2").read_text(encoding="utf-8") == "archive 1"
    assert not (tmp_path / "perf.log.3").exists()


def test_un_echec_d_archivage_ne_coute_pas_le_log(tmp_path, monkeypatch):
    """Sous Windows, un perf.log ouvert dans un éditeur ne se renomme pas. On doit continuer
    d'écrire dans le fichier trop gros — c'est exactement le comportement d'avant."""
    monkeypatch.setattr(reporter, "TAILLE_MAX_LOG", 100)
    import os
    monkeypatch.setattr(os, "replace", _lever)
    log = tmp_path / "perf.log"
    log.write_text("w" * 200, encoding="utf-8")

    reporter._faire_tourner(log)          # ne doit pas lever

    r = Reporter()
    r.set_verbose_log(log)
    r.verbose("la ligne passe quand meme")
    r.close()
    assert "la ligne passe quand meme" in log.read_text(encoding="utf-8")


def _lever(*a, **k):
    raise OSError("fichier verrouillé")
