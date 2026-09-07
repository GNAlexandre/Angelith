# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de `run_manga.py --all` — le run de nuit sur une œuvre entière.

Miroir de `tests/test_run_cli.py` (le `--all` du light novel), avec les trois différences
qui justifient un second helper plutôt qu'un partage : le pré-vol qui saute sans ouvrir,
l'isolation par chapitre, et le bilan relu depuis le disque.

`process_volume` est systématiquement remplacé : ces tests portent sur l'ENCHAÎNEMENT, pas
sur le traitement d'une planche (c'est `tests/test_manga_orchestrator.py`, marqué `modeles`
et `lent`, qui s'en charge).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import run_manga as rm
from manga import serie


def _config(tmp_path, dry_run=True):
    """⚠ `dry_run` vit dans `config["options"]`, pas seulement dans `args` : c'est
    `_appliquer_options_lot` qui l'y recopie depuis `main()`. L'oublier ici ferait charger
    pour de vrai les 17 Go de `qwen3.6:27b` dans l'Ollama de la machine — mesuré à 30 s par
    test avant correction."""
    return {
        "chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path / "build")},
        "options": {"dry_run": dry_run},
        "llm": {"base_url": "http://localhost:11434/v1"},
        "langues": {"dossiers": {"ENG": "en", "JAP": "jp", "FR": "fr"}},
        "manga": {"modeles": {"manga_traducteur": {"model": "qwen3.6:27b"}},
                  "llm": {}, "chemins": {}, "lot": {}, "rendu": {}},
    }


def _args(**over):
    base = dict(projet="Oeuvre", tome=None, verbose=False, dry_run=True,
                keep_awake=False, shutdown=False, shutdown_delay=120,
                force=False, from_stage=None, page=None, conf=None, iou=None,
                lot=None, think=None, all=True, langue=None, format_planche=None)
    base.update(over)
    return SimpleNamespace(**base)


def _image(chemin: Path):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(chemin)


def _chapitre(tmp_path, tome: str, n_source: int = 2, n_rendues: int = 0):
    """Un chapitre avec `n_source` planches en entrée et `n_rendues` déjà rendues."""
    for i in range(1, n_source + 1):
        _image(tmp_path / "sources" / "Oeuvre" / tome / "manga" / f"{i:03d}.jpg")
    for i in range(1, n_rendues + 1):
        _image(serie.build_dir_de(tmp_path / "build", "Oeuvre", tome)
               / "pages_out" / f"page_{i:04d}.png")


def _brancher(monkeypatch, fake):
    """`_run_all_chapitres` importe `process_volume` à l'appel : c'est le module qui porte
    la référence, donc c'est lui qu'on remplace."""
    monkeypatch.setattr("manga.orchestrator_manga.process_volume", fake)


def _fake_reussi(tmp_path, vus, n_source=2):
    """Un `process_volume` qui RÉUSSIT pour de bon : il matérialise les planches rendues.

    ⚠ Un faux qui renvoie `True` sans rien écrire n'est pas un chapitre réussi, c'est un
    chapitre dont toutes les planches ont échoué — et le bilan, qui relit le disque, a raison
    de sortir en code 1. Les tests qui vérifient le chemin nominal doivent donc produire
    quelque chose, sinon ils verrouillent un comportement qui n'existe pas."""
    def fake(projet, tome, config, **kw):
        vus.append(tome)
        for i in range(1, n_source + 1):
            _image(serie.build_dir_de(tmp_path / "build", "Oeuvre", tome)
                   / "pages_out" / f"page_{i:04d}.png")
        return True
    return fake


# --------------------------------------------------------------------------- #
# Enchaînement et ordre
# --------------------------------------------------------------------------- #

def test_les_chapitres_sont_traites_dans_l_ordre_de_lecture(tmp_path, monkeypatch):
    for tome in ("Chap.10", "Chap.2", "Chap.1"):
        _chapitre(tmp_path, tome)
    vus = []
    _brancher(monkeypatch, _fake_reussi(tmp_path, vus))

    assert rm._run_all_chapitres(_args(), _config(tmp_path)) == 0
    assert vus == ["Chap.1", "Chap.2", "Chap.10"]


def test_un_chapitre_termine_n_est_pas_ouvert(tmp_path, monkeypatch):
    """Le cœur du lot : ouvrir un chapitre fini coûte le scan, la migration du cache et le
    réassemblage du CBZ — 230 Mo réécrits pour *manga A* Vol.1, sur OneDrive."""
    _chapitre(tmp_path, "Chap.1", n_source=2, n_rendues=2)      # terminé
    _chapitre(tmp_path, "Chap.2", n_source=2, n_rendues=0)      # jamais traité
    vus = []
    _brancher(monkeypatch, _fake_reussi(tmp_path, vus))

    assert rm._run_all_chapitres(_args(), _config(tmp_path)) == 0
    assert vus == ["Chap.2"]


def test_un_chapitre_partiel_est_repris(tmp_path, monkeypatch):
    _chapitre(tmp_path, "Chap.1", n_source=10, n_rendues=3)
    vus = []
    _brancher(monkeypatch, lambda p, t, c, **k: (vus.append(t), True)[1])

    rm._run_all_chapitres(_args(), _config(tmp_path))
    assert vus == ["Chap.1"]


def test_un_chapitre_sans_source_est_ignore(tmp_path, monkeypatch):
    """Le cas réel d'un dossier de light novel sous une œuvre manga. L'ouvrir ne produirait
    qu'un `SystemExit` — et le compter en échec ferait sortir la série en code 1 chaque nuit."""
    (tmp_path / "sources" / "Oeuvre" / "Vol.2" / "JAP").mkdir(parents=True)
    _chapitre(tmp_path, "Chap.1")
    vus = []
    _brancher(monkeypatch, _fake_reussi(tmp_path, vus))

    assert rm._run_all_chapitres(_args(), _config(tmp_path)) == 0
    assert vus == ["Chap.1"]


def test_force_annule_le_saut(tmp_path, monkeypatch):
    """`--force` et `--from` sont des demandes explicites de refaire. Sans cette règle,
    `--all --from rendu` — l'harmonisation de l'œuvre avec le glossaire enrichi par la nuit —
    ne toucherait AUCUN des chapitres finis, c'est-à-dire exactement ceux qu'il vise."""
    _chapitre(tmp_path, "Chap.1", n_source=2, n_rendues=2)
    _chapitre(tmp_path, "Chap.2", n_source=2, n_rendues=2)
    vus = []
    _brancher(monkeypatch, lambda p, t, c, **k: (vus.append(t), True)[1])

    rm._run_all_chapitres(_args(force=True), _config(tmp_path))
    assert vus == ["Chap.1", "Chap.2"]


def test_from_annule_le_saut_mais_pas_pour_les_chapitres_sans_source(tmp_path, monkeypatch):
    _chapitre(tmp_path, "Chap.1", n_source=2, n_rendues=2)
    (tmp_path / "sources" / "Oeuvre" / "Chap.2" / "manga").mkdir(parents=True)
    vus = []
    _brancher(monkeypatch, lambda p, t, c, **k: (vus.append(t), True)[1])

    rm._run_all_chapitres(_args(from_stage="rendu"), _config(tmp_path))
    assert vus == ["Chap.1"]


def test_les_options_sont_passees_a_chaque_chapitre(tmp_path, monkeypatch):
    _chapitre(tmp_path, "Chap.1")
    _chapitre(tmp_path, "Chap.2")
    vus = []

    def fake(projet, tome, config, **kw):
        vus.append((tome, kw["force"], kw["restart_from"]))
        return True

    _brancher(monkeypatch, fake)
    rm._run_all_chapitres(_args(force=True, from_stage="rendu"), _config(tmp_path))
    assert vus == [("Chap.1", True, "rendu"), ("Chap.2", True, "rendu")]


def test_une_oeuvre_vide_sort_en_erreur(tmp_path, monkeypatch):
    (tmp_path / "sources" / "Oeuvre").mkdir(parents=True)
    _brancher(monkeypatch, lambda *a, **k: True)
    assert rm._run_all_chapitres(_args(), _config(tmp_path)) == 1


def test_rien_a_faire_sort_en_zero(tmp_path, monkeypatch):
    _chapitre(tmp_path, "Chap.1", n_source=2, n_rendues=2)
    vus = []
    _brancher(monkeypatch, lambda p, t, c, **k: (vus.append(t), True)[1])
    assert rm._run_all_chapitres(_args(), _config(tmp_path)) == 0
    assert vus == []


# --------------------------------------------------------------------------- #
# Isolation des échecs — ce qui fait qu'une nuit rend neuf chapitres sur dix
# --------------------------------------------------------------------------- #

def test_un_chapitre_en_echec_n_interrompt_pas_la_serie(tmp_path, monkeypatch):
    for tome in ("Chap.1", "Chap.2", "Chap.3"):
        _chapitre(tmp_path, tome)
    vus = []

    def fake(projet, tome, config, **kw):
        vus.append(tome)
        if tome == "Chap.2":
            raise RuntimeError("JPEG tronqué")
        return True

    _brancher(monkeypatch, fake)
    code = rm._run_all_chapitres(_args(), _config(tmp_path))

    assert vus == ["Chap.1", "Chap.2", "Chap.3"]
    assert code == 1, "un échec doit se voir dans le code de sortie"


def test_un_systemexit_est_isole_comme_les_autres(tmp_path, monkeypatch):
    """C'est ce que lèvent un dossier de chapitre vide et un modèle ONNX introuvable. Ce sont
    des accidents de chapitre, pas des raisons de perdre la nuit."""
    for tome in ("Chap.1", "Chap.2"):
        _chapitre(tmp_path, tome)
    vus = []

    def fake(projet, tome, config, **kw):
        vus.append(tome)
        if tome == "Chap.1":
            raise SystemExit("modèle de détection introuvable")
        return True

    _brancher(monkeypatch, fake)
    assert rm._run_all_chapitres(_args(), _config(tmp_path)) == 1
    assert vus == ["Chap.1", "Chap.2"]


def test_l_arret_propre_stoppe_toute_la_serie(tmp_path, monkeypatch):
    """`process_volume` renvoie False = `--stop`/Ctrl+C. Contrairement à un échec, c'est une
    demande de l'utilisateur : elle vise la série, pas le chapitre."""
    for tome in ("Chap.1", "Chap.2", "Chap.3"):
        _chapitre(tmp_path, tome)
    vus = []

    def fake(projet, tome, config, **kw):
        vus.append(tome)
        return tome != "Chap.2"

    _brancher(monkeypatch, fake)
    code = rm._run_all_chapitres(_args(), _config(tmp_path))

    assert vus == ["Chap.1", "Chap.2"]
    assert code == 0, "un arrêt demandé n'est pas un échec"


def test_un_ctrl_c_stoppe_toute_la_serie(tmp_path, monkeypatch):
    for tome in ("Chap.1", "Chap.2"):
        _chapitre(tmp_path, tome)
    vus = []

    def fake(projet, tome, config, **kw):
        vus.append(tome)
        raise KeyboardInterrupt

    _brancher(monkeypatch, fake)
    rm._run_all_chapitres(_args(), _config(tmp_path))      # rattrapé, pas propagé
    assert vus == ["Chap.1"]


# --------------------------------------------------------------------------- #
# Cycle de vie du modèle — une fois pour la série, pas par chapitre
# --------------------------------------------------------------------------- #

def test_le_modele_est_precharge_et_decharge_une_seule_fois(tmp_path, monkeypatch):
    """Sur quinze chapitres, précharger par chapitre paierait quinze fois la montée de 17 Go
    en VRAM. Et le déchargement final est ce qui évite qu'un modèle résident fasse chuter le
    débit GPU au run suivant."""
    for tome in ("Chap.1", "Chap.2", "Chap.3"):
        _chapitre(tmp_path, tome)
    appels = {"load": 0, "unload": 0}
    monkeypatch.setattr("core.power.ollama_load",
                        lambda url, m: appels.__setitem__("load", appels["load"] + 1))
    monkeypatch.setattr("core.power.ollama_unload",
                        lambda url, m: appels.__setitem__("unload", appels["unload"] + 1))
    _brancher(monkeypatch, lambda *a, **k: True)

    rm._run_all_chapitres(_args(dry_run=False), _config(tmp_path, dry_run=False))
    assert appels == {"load": 1, "unload": 1}


def test_from_rendu_ne_charge_aucun_modele(tmp_path, monkeypatch):
    """`--from rendu` relettre depuis le cache : faire monter 17 Go pour zéro appel serait
    absurde, et le déchargement final évincerait un modèle chargé pour autre chose."""
    _chapitre(tmp_path, "Chap.1")
    appels = {"load": 0, "unload": 0}
    monkeypatch.setattr("core.power.ollama_load",
                        lambda url, m: appels.__setitem__("load", appels["load"] + 1))
    monkeypatch.setattr("core.power.ollama_unload",
                        lambda url, m: appels.__setitem__("unload", appels["unload"] + 1))
    _brancher(monkeypatch, lambda *a, **k: True)

    rm._run_all_chapitres(_args(dry_run=False, from_stage="rendu"),
                          _config(tmp_path, dry_run=False))
    assert appels == {"load": 0, "unload": 0}


def test_le_modele_est_decharge_meme_apres_un_echec(tmp_path, monkeypatch):
    _chapitre(tmp_path, "Chap.1")
    appels = {"unload": 0}
    monkeypatch.setattr("core.power.ollama_load", lambda url, m: None)
    monkeypatch.setattr("core.power.ollama_unload",
                        lambda url, m: appels.__setitem__("unload", appels["unload"] + 1))

    def fake(*a, **k):
        raise RuntimeError("panne")

    _brancher(monkeypatch, fake)
    rm._run_all_chapitres(_args(dry_run=False), _config(tmp_path, dry_run=False))
    assert appels["unload"] == 1


# --------------------------------------------------------------------------- #
# Bilan
# --------------------------------------------------------------------------- #

def test_le_rapport_de_serie_est_ecrit(tmp_path, monkeypatch):
    _chapitre(tmp_path, "Chap.1", n_source=2)
    _chapitre(tmp_path, "Chap.2", n_source=2)

    def fake(projet, tome, config, **kw):
        if tome == "Chap.2":
            raise RuntimeError("JPEG tronqué")
        # Chap.1 réussit : on matérialise ses deux planches pour que le bilan le voie fini.
        for i in (1, 2):
            _image(serie.build_dir_de(tmp_path / "build", "Oeuvre", tome)
                   / "pages_out" / f"page_{i:04d}.png")
        return True

    _brancher(monkeypatch, fake)
    rm._run_all_chapitres(_args(), _config(tmp_path))

    rapport = tmp_path / "build" / "Oeuvre" / "RAPPORT-SERIE.md"
    texte = rapport.read_text(encoding="utf-8")
    assert "# Série — Oeuvre" in texte
    assert "Chapitres en échec" in texte and "JPEG tronqué" in texte
    # Le bilan est relu DEPUIS LE DISQUE : Chap.1 y est terminé, Chap.2 reste à faire.
    assert "| Chap.1 | ✓ termine |" in texte
    assert "Reste à traiter" in texte and "Chap.2" in texte
    # Et la commande de reprise est nommée, pas à deviner.
    assert 'run_manga.py "Oeuvre" Chap.2' in texte


def test_le_journal_de_serie_est_ecrit_sans_verbose(tmp_path, monkeypatch):
    """Un run de nuit sans `--verbose` ne laissait aucune trace fichier. C'est le fichier
    qu'on suit depuis un second terminal pendant que quinze chapitres défilent."""
    _chapitre(tmp_path, "Chap.1")
    _brancher(monkeypatch, lambda *a, **k: True)
    rm._run_all_chapitres(_args(verbose=False), _config(tmp_path))

    journal = tmp_path / "build" / "Oeuvre" / "perf.log"
    assert journal.exists()
    assert "Chap.1" in journal.read_text(encoding="utf-8")


def test_le_bilan_est_ecrit_avant_l_extinction(tmp_path, monkeypatch):
    """⚠ `finalize_power` programme l'extinction PUIS dort tout le délai. Un rapport écrit
    après ne serait jamais écrit."""
    _chapitre(tmp_path, "Chap.1")
    ordre = []
    monkeypatch.setattr("core.power.shutdown",
                        lambda d: (ordre.append("shutdown"), "shutdown /a")[1])
    monkeypatch.setattr("core.power.cancel_shutdown", lambda: "")
    monkeypatch.setattr("core.power.keep_awake", lambda: True)
    monkeypatch.setattr("core.power.release", lambda: None)
    monkeypatch.setattr("core.power.stop_inhibitor", lambda i: None)
    monkeypatch.setattr("time.sleep", lambda s: None)

    rapport = tmp_path / "build" / "Oeuvre" / "RAPPORT-SERIE.md"

    def fake(*a, **k):
        ordre.append("run")
        return True

    _brancher(monkeypatch, fake)
    rm._run_all_chapitres(_args(shutdown=True, shutdown_delay=1), _config(tmp_path))

    assert rapport.exists()
    assert ordre == ["run", "shutdown"]


# --------------------------------------------------------------------------- #
# Relettrage ciblé — la boucle infinie qu'il fallait éviter
# --------------------------------------------------------------------------- #

def _perimer(tmp_path, tome: str, planche: int):
    """Rend la planche périmée : sa traduction devient postérieure à son rendu."""
    import json
    import os
    build_dir = serie.build_dir_de(tmp_path / "build", "Oeuvre", tome)
    ckpt = build_dir / ".checkpoints" / f"page_{planche:04d}"
    ckpt.mkdir(parents=True, exist_ok=True)
    (ckpt / "traduction.json").write_text(json.dumps(["FR"]), encoding="utf-8")
    os.utime(build_dir / "pages_out" / f"page_{planche:04d}.png",
             (1_600_000_000, 1_600_000_000))


def test_un_chapitre_a_relettrer_vise_ses_seules_planches_perimees(tmp_path, monkeypatch):
    """⚠ LE piège. Un chapitre « à relettrer » a un cache COMPLET : `stages_to_redo` n'y voit
    rien à refaire et `process_volume` sauterait chacune de ses planches. Sans consigne
    explicite, le chapitre ressortirait « à relettrer » après son propre passage — et chaque
    nuit le reprendrait pour ne rien faire, en signalant un travail qui n'avance jamais."""
    _chapitre(tmp_path, "Chap.1", n_source=8, n_rendues=8)
    _perimer(tmp_path, "Chap.1", 3)
    _perimer(tmp_path, "Chap.1", 6)
    vus = []

    def fake(projet, tome, config, **kw):
        vus.append((tome, kw["restart_from"], kw["only_pages"]))
        return True

    _brancher(monkeypatch, fake)
    rm._run_all_chapitres(_args(), _config(tmp_path))

    assert vus == [("Chap.1", "rendu", {3, 6})]


def test_un_chapitre_normal_ne_recoit_aucune_consigne_de_relettrage(tmp_path, monkeypatch):
    """Le témoin : la consigne ne doit toucher QUE les chapitres périmés."""
    _chapitre(tmp_path, "Chap.1", n_source=4, n_rendues=0)
    vus = []

    def fake(projet, tome, config, **kw):
        vus.append((kw["restart_from"], kw["only_pages"]))
        return True

    _brancher(monkeypatch, fake)
    rm._run_all_chapitres(_args(), _config(tmp_path))
    assert vus == [(None, None)]


def test_from_explicite_l_emporte_sur_le_relettrage_cible(tmp_path, monkeypatch):
    """L'utilisateur a nommé lui-même ce qu'il veut refaire, et sur tout le chapitre."""
    _chapitre(tmp_path, "Chap.1", n_source=4, n_rendues=4)
    _perimer(tmp_path, "Chap.1", 2)
    vus = []

    def fake(projet, tome, config, **kw):
        vus.append((kw["restart_from"], kw["only_pages"]))
        return True

    _brancher(monkeypatch, fake)
    rm._run_all_chapitres(_args(from_stage="traduction"), _config(tmp_path))
    assert vus == [("traduction", None)]


def test_un_chapitre_termine_mais_vide_sort_en_erreur(tmp_path, monkeypatch):
    """Le cas que le filet par planche rend possible : `process_volume` va au bout et renvoie
    `True`, mais toutes ses planches sont tombées en échec. Le code de retour dit « pas
    d'arrêt », le disque dit « rien de rendu » — c'est le disque qui a raison."""
    _chapitre(tmp_path, "Chap.1", n_source=4)
    _brancher(monkeypatch, lambda *a, **k: True)          # ne matérialise rien
    assert rm._run_all_chapitres(_args(), _config(tmp_path)) == 1


def test_un_arret_demande_ne_sort_pas_en_erreur(tmp_path, monkeypatch):
    """⚠ Le pendant du test précédent : après `--stop`, ce qui reste n'est pas une anomalie,
    c'est ce qu'on a choisi de ne pas faire. Sortir en 1 ferait échouer un script de nuit
    parce que l'utilisateur a demandé l'arrêt."""
    _chapitre(tmp_path, "Chap.1", n_source=4)
    _chapitre(tmp_path, "Chap.2", n_source=4)
    _brancher(monkeypatch, lambda *a, **k: False)         # arrêt propre dès le premier
    assert rm._run_all_chapitres(_args(), _config(tmp_path)) == 0


# --------------------------------------------------------------------------- #
#  Glossaire de l'œuvre — `--extract-glossary` / `--optimize-glossary`
#
#  Le dispatch d'abord, et il n'est pas cosmétique : `--all --extract-glossary` doit être
#  intercepté AVANT la branche `--all`, sans quoi il partirait dans `_run_all_chapitres` —
#  c'est-à-dire retraduirait l'œuvre entière, l'exact contraire de ce qu'il promet.
# --------------------------------------------------------------------------- #

def _lancer(monkeypatch, tmp_path, argv: list[str], **doubles) -> int:
    """`run_manga.main()` avec un `sys.argv` posé et la config de test. Renvoie le code de
    sortie (`main` sort toujours par `SystemExit`)."""
    import sys as _sys
    monkeypatch.setattr(_sys, "argv", ["run_manga.py"] + argv)
    monkeypatch.setattr(rm.cli, "charger_config", lambda *a, **k: _config(tmp_path))
    for nom, double in doubles.items():
        monkeypatch.setattr(rm, nom, double)
    with pytest.raises(SystemExit) as exc:
        rm.main()
    return exc.value.code


def _refuse(nom):
    def _boom(*a, **k):
        raise AssertionError(f"{nom} n'aurait pas dû être appelé")
    return _boom


def test_optimize_glossary_exige_l_oeuvre_seule(tmp_path, monkeypatch):
    """Un seul glossaire par projet : nommer un tome n'a pas de sens, et le laisser passer
    ferait croire qu'on optimise « le glossaire de Vol.1 »."""
    for argv in (["--optimize-glossary"],
                 ["Oeuvre", "Vol.1", "--optimize-glossary"],
                 ["Oeuvre", "--all", "--optimize-glossary"]):
        assert _lancer(monkeypatch, tmp_path, argv,
                       _run_glossaire=_refuse("_run_glossaire")) == 2


def test_extract_glossary_exige_un_tome_ou_all(tmp_path, monkeypatch):
    assert _lancer(monkeypatch, tmp_path, ["Oeuvre", "--extract-glossary"],
                   _run_glossaire=_refuse("_run_glossaire")) == 2
    assert _lancer(monkeypatch, tmp_path, ["--extract-glossary"],
                   _run_glossaire=_refuse("_run_glossaire")) == 2


def test_extract_glossary_refuse_les_seuils_de_detection(tmp_path, monkeypatch):
    """`--conf`/`--iou` règlent la détection d'UNE planche et impliquent un rendu pour être
    jugées : les accepter ici promettrait un arbitrage que rien ne rendrait visible."""
    assert _lancer(monkeypatch, tmp_path,
                   ["Oeuvre", "Vol.1", "--extract-glossary", "--page", "3", "--conf", "0.3"],
                   _run_glossaire=_refuse("_run_glossaire")) == 2


def test_all_extract_glossary_ne_passe_pas_par_la_serie(tmp_path, monkeypatch):
    """LE test du dispatch : `--all --extract-glossary` ne doit PAS retraduire l'œuvre."""
    vus = {}

    def _faux_glossaire(args, config, *, extraction):
        vus["extraction"] = extraction
        vus["tome"] = args.tome
        return 0

    assert _lancer(monkeypatch, tmp_path, ["Oeuvre", "--all", "--extract-glossary"],
                   _run_glossaire=_faux_glossaire,
                   _run_all_chapitres=_refuse("_run_all_chapitres")) == 0
    assert vus == {"extraction": True, "tome": None}


def test_optimize_glossary_n_extrait_rien(tmp_path, monkeypatch):
    vus = {}
    assert _lancer(monkeypatch, tmp_path, ["Oeuvre", "--optimize-glossary"],
                   _run_glossaire=lambda args, config, *, extraction: (
                       vus.update(extraction=extraction) or 0)) == 0
    assert vus == {"extraction": False}


# --- le corps de `_run_glossaire` : isolation, code de sortie, dédoublonnage ------------- #

def _brancher_glossaire(monkeypatch, extraire, optimiser=None):
    """`_run_glossaire` importe `manga.glossaire_manga` à l'appel : c'est le module qui porte
    les références, donc c'est lui qu'on remplace."""
    import manga.glossaire_manga as gm
    monkeypatch.setattr(gm, "run_extract_glossary", extraire)
    monkeypatch.setattr(gm, "run_optimize_glossary",
                        optimiser or (lambda *a, **k: {}))


def _args_glossaire(tmp_path, **over):
    args = _args(**over)
    args.extract_glossary, args.optimize_glossary = True, False
    return args


def test_un_chapitre_en_echec_n_interrompt_pas_l_extraction(tmp_path, monkeypatch):
    """Même filet que le run de nuit : un JPEG corrompu au chapitre 1 ne doit pas coûter les
    suivants. Le code de sortie reste 1 — il répond à « faut-il que je regarde ? »."""
    _chapitre(tmp_path, "Chap.1")
    _chapitre(tmp_path, "Chap.2")
    vus = []

    def _extraire(projet, tome, config, **kw):
        vus.append(tome)
        if tome == "Chap.1":
            raise OSError("image tronquée")
        return True

    _brancher_glossaire(monkeypatch, _extraire)
    assert rm._run_glossaire(_args_glossaire(tmp_path), _config(tmp_path),
                             extraction=True) == 1
    assert vus == ["Chap.1", "Chap.2"]


def test_un_arret_propre_stoppe_l_extraction_sans_erreur(tmp_path, monkeypatch):
    _chapitre(tmp_path, "Chap.1")
    _chapitre(tmp_path, "Chap.2")
    vus = []

    def _extraire(projet, tome, config, **kw):
        vus.append(tome)
        return False                      # arrêt propre dès le premier chapitre

    _brancher_glossaire(monkeypatch, _extraire)
    assert rm._run_glossaire(_args_glossaire(tmp_path), _config(tmp_path),
                             extraction=True) == 0
    assert vus == ["Chap.1"]


def test_le_dedoublonnage_est_saute_si_le_glossaire_n_a_pas_bouge(tmp_path, monkeypatch):
    """L'agent glossariste travaille sur le glossaire ENTIER de l'œuvre : le rappeler après
    une extraction qui n'a rien ajouté serait un appel LLM pour rien — le motif exact que
    `_passe_terminologie` a déjà corrigé côté orchestrateur, avec la même empreinte."""
    _chapitre(tmp_path, "Chap.1")
    appels = []
    _brancher_glossaire(monkeypatch, lambda *a, **k: True,
                        optimiser=lambda *a, **k: appels.append(1) or {})

    assert rm._run_glossaire(_args_glossaire(tmp_path), _config(tmp_path),
                             extraction=True) == 0
    assert appels == []


def test_le_dedoublonnage_tourne_quand_le_glossaire_a_bouge(tmp_path, monkeypatch):
    """Le contre-exemple, et il est payé UNE fois pour toute l'œuvre — pas par chapitre."""
    from core import glossary

    _chapitre(tmp_path, "Chap.1")
    _chapitre(tmp_path, "Chap.2")
    chemin = tmp_path / "sources" / "Oeuvre" / "glossaire.yaml"
    appels = []

    def _extraire(projet, tome, config, **kw):
        glo = glossary.load(chemin) or glossary.empty()
        glo["personnages"].append({"nom": tome, "variantes": [], "description": ""})
        glossary.save(glo, chemin)
        return True

    _brancher_glossaire(monkeypatch, _extraire,
                        optimiser=lambda *a, **k: appels.append(1) or {})
    assert rm._run_glossaire(_args_glossaire(tmp_path), _config(tmp_path),
                             extraction=True) == 0
    assert appels == [1], "une seule optimisation, après le dernier chapitre"


def test_l_extraction_ne_precharge_pas_le_traducteur(tmp_path, monkeypatch):
    """17 Go en VRAM pour une commande qui ne traduit rien — et un déchargement final qui
    évincerait un modèle chargé pour autre chose. Même garde que `traduira` côté run."""
    config = _config(tmp_path)
    config["manga"]["modeles"] = {"manga_traducteur": {"model": "gros-27b"},
                                  "terminologue": {"model": "petit-8b"},
                                  "glossariste": {"model": "petit-8b"}}
    assert rm._modeles_du_glossaire(config, extraction=True) == ["petit-8b"]
    assert rm._modeles_du_glossaire(config, extraction=False) == ["petit-8b"]
