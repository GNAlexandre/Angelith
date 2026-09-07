# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`run_manga.py --list` consomme le MÊME modèle que la bibliothèque (lot 34, critère 3).

Un seul inventaire, deux affichages. Ce fichier vérifie les trois choses qui font que c'est
vrai et que ça le reste :

1. le rendu console est **iso** — mêmes puces, mêmes détails, même ordre de lecture ;
2. `--list` sans argument ne paie **aucun** balayage de checkpoints (l'inventaire est
   paresseux) ;
3. la CLI passe bien par `bibliotheque.py` et non par une seconde lecture — vérifié par
   `ast`, sans exécuter `run_manga.py`, qui importerait tout le pipeline.
"""
from __future__ import annotations

import ast
from pathlib import Path

import bibliotheque as biblio
from core import cli
from manga import serie


def _config(racine: Path) -> dict:
    return {"chemins": {"sources": str(racine / "sources"), "build": str(racine / "build"),
                        "glossaire_fichier": "glossaire.yaml"},
            "langues": {"dossiers": {"ENG": "en", "JAP": "jp"}}}


def _tome(racine: Path, projet: str, tome: str, *, planches: int, rendues: int) -> None:
    for i in range(1, planches + 1):
        chemin = racine / "sources" / projet / tome / "manga" / f"{i:03d}.png"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"\0")
    build = racine / "build" / projet / tome / "manga"
    for i in range(1, planches + 1):
        ckpt = build / ".checkpoints" / f"page_{i:04d}"
        ckpt.mkdir(parents=True, exist_ok=True)
        (ckpt / "regions.json").write_text("{}", encoding="utf-8")
    for i in range(1, rendues + 1):
        chemin = build / "pages_out" / f"page_{i:04d}.png"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"\0")


def _corpus(tmp_path: Path) -> dict:
    _tome(tmp_path, "Proj", "Chap.2", planches=3, rendues=3)
    _tome(tmp_path, "Proj", "Chap.10", planches=4, rendues=1)
    livre = tmp_path / "sources" / "Roman" / "Vol.1" / "ENG" / "livre.pdf"
    livre.parent.mkdir(parents=True, exist_ok=True)
    livre.write_bytes(b"\0")
    return _config(tmp_path)


def _afficher(config: dict, projet: str | None, capsys) -> str:
    """Le rendu exact de `run_manga.py --list`, sans importer `run_manga` (qui tire tout le
    pipeline). Le bloc reproduit est **le même** que celui de la CLI."""
    racine_src = biblio.racine_sources(config)
    racine_build = biblio.racine_build(config)
    inventaire = biblio.Inventaire(config)

    def _etat(p: str, t: str):
        info = inventaire.tome(p, t)
        return biblio.puce(info), biblio.detail_manga(info)

    cli.afficher_liste(inventaire.projets, inventaire.tomes, racine_src, racine_build,
                       projet, sous_dossier="manga", etat=_etat)
    return capsys.readouterr().out


def test_la_sortie_est_celle_de_manga_serie_puce_pour_puce(tmp_path, capsys):
    """Iso : la colonne d'état reste le verdict de `manga/serie.py`, celui qu'on lit avant de
    lancer une nuit."""
    config = _corpus(tmp_path)
    sortie = _afficher(config, "Proj", capsys)
    src, build = biblio.racine_sources(config), biblio.racine_build(config)
    for tome in ("Chap.2", "Chap.10"):
        attendu = serie.etat_chapitre(src, build, "Proj", tome, config)
        assert f"{serie.PUCES[attendu.statut]} {tome}" in sortie
        assert attendu.detail in sortie


def test_l_ordre_est_celui_de_LECTURE_pas_l_alphabetique(tmp_path, capsys):
    """⚠ `Chap.10` doit venir APRÈS `Chap.2`. Le tri alphabétique fait l'inverse, et la
    passe terminologique enrichit le glossaire au fil des tomes."""
    config = _corpus(tmp_path)
    sortie = _afficher(config, "Proj", capsys)
    assert sortie.index("Chap.2") < sortie.index("Chap.10")


def test_un_tome_de_roman_garde_le_verdict_de_la_brique_manga(tmp_path, capsys):
    """⚠ `run_manga.py` demande « le run manga a-t-il quelque chose à faire ici ? ». Répondre
    « terminé » sur un roman serait faux POUR CETTE COMMANDE, même si la bibliothèque, elle,
    a raison de le dire terminé."""
    config = _corpus(tmp_path)
    sortie = _afficher(config, "Roman", capsys)
    assert "aucune image ni archive" in sortie
    assert biblio.tome_info(config, "Roman", "Vol.1").statut == "non_traite"


def test_sans_projet_aucun_checkpoint_n_est_balaye(tmp_path, capsys, monkeypatch):
    """L'inventaire est paresseux, et c'est ce qui garde `--list` à son budget : la liste des
    projets n'a besoin que de deux lectures de répertoire."""
    config = _corpus(tmp_path)
    appels: list[tuple[str, str]] = []
    monkeypatch.setattr(biblio, "tome_info",
                        lambda cfg, p, t, **kw: appels.append((p, t)))
    sortie = _afficher(config, None, capsys)
    assert "Proj  (2 tome(s))" in sortie
    assert appels == []


def test_la_cli_consomme_bien_core_bibliotheque(tmp_path):
    """Par `ast` — importer `run_manga` tirerait tout le pipeline pour vérifier trois lignes.

    ⚠ Ce test est ce qui empêche la CLI de se redoter d'une lecture propre. Il échouerait si
    quelqu'un remettait un `serie.etat_chapitre` en direct dans le bloc `--list`."""
    source = Path("run_manga.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    bloc = None
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.If):
            continue
        if isinstance(noeud.test, ast.Attribute) and noeud.test.attr == "list":
            bloc = noeud
            break
    assert bloc is not None, "le bloc `if args.list:` a disparu"
    texte = ast.unparse(bloc)
    assert "bibliotheque" in texte
    assert "Inventaire" in texte
    assert "etat_chapitre" not in texte, "la CLI a repris une lecture d'état à son compte"
