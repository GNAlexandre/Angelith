# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Index de projet d'un tome (lot 16) — la fondation de l'interface graphique.

Ce qui est testé n'est pas « le fichier existe » mais les deux propriétés qui le rendent
utile : la **révision** ne bouge que si le contenu bouge, et un fichier abîmé ne fait jamais
échouer un tome.
"""
import json

from manga import checkpoints, projet


def _ckpt(build, i):
    return checkpoints.page_checkpoint_dir(build, i)


def _etat(build, pages=("p1.jpg", "p2.jpg")):
    return projet.construire(build, projet="Mon Manga", tome="Vol.1", pages=list(pages),
                             version="1.0.0", page_ckpt=_ckpt)


def test_le_fichier_porte_son_format_et_sa_version(tmp_path):
    projet.ecrire(tmp_path, _etat(tmp_path))
    data = json.loads((tmp_path / projet.NOM_FICHIER).read_text(encoding="utf-8"))
    assert data["format"] == projet.FORMAT_PROJET
    assert data["outil"] == "1.0.0"
    assert [p["index"] for p in data["pages"]] == [1, 2]


def test_la_revision_ne_bouge_PAS_si_rien_ne_change(tmp_path):
    """Sans quoi le numéro n'apprendrait rien : il compterait les runs, pas les changements."""
    projet.ecrire(tmp_path, _etat(tmp_path))
    projet.ecrire(tmp_path, _etat(tmp_path))
    assert projet.lire(tmp_path)["revision"] == 1


def test_la_revision_augmente_quand_une_PLANCHE_change(tmp_path):
    projet.ecrire(tmp_path, _etat(tmp_path))
    checkpoints.save_traduction(_ckpt(tmp_path, 1), ["Bonjour"])
    projet.ecrire(tmp_path, _etat(tmp_path))
    assert projet.lire(tmp_path)["revision"] == 2


def test_une_correction_MANUELLE_compte_comme_un_changement(tmp_path):
    """Elle change ce qui sera rendu : l'index doit s'en apercevoir."""
    projet.ecrire(tmp_path, _etat(tmp_path))
    ck = _ckpt(tmp_path, 1)
    ck.mkdir(parents=True, exist_ok=True)
    (ck / checkpoints.TRADUCTION_MANUELLE_FILENAME).write_text('{"0": "À moi"}',
                                                               encoding="utf-8")
    projet.ecrire(tmp_path, _etat(tmp_path))
    assert projet.lire(tmp_path)["revision"] == 2


def test_l_empreinte_ignore_le_qa_json(tmp_path):
    """`qa.json` décrit le RUN (durée, compteurs), pas le contenu de la planche : le voir
    bouger à chaque exécution ferait grimper la révision sans raison."""
    projet.ecrire(tmp_path, _etat(tmp_path))
    ck = _ckpt(tmp_path, 1)
    ck.mkdir(parents=True, exist_ok=True)
    (ck / checkpoints.QA_FILENAME).write_text('{"page": 1}', encoding="utf-8")
    projet.ecrire(tmp_path, _etat(tmp_path))
    assert projet.lire(tmp_path)["revision"] == 1


def test_un_fichier_illisible_vaut_None_et_est_reecrit(tmp_path):
    (tmp_path / projet.NOM_FICHIER).write_text("{pas du json", encoding="utf-8")
    assert projet.lire(tmp_path) is None
    projet.ecrire(tmp_path, _etat(tmp_path))
    assert projet.lire(tmp_path)["revision"] == 1


def test_un_format_inconnu_vaut_None(tmp_path):
    """Le champ de version existe pour ça : un fichier d'une version future ne doit pas être
    interprété de travers."""
    (tmp_path / projet.NOM_FICHIER).write_text(
        json.dumps({"format": 999, "pages": []}), encoding="utf-8")
    assert projet.lire(tmp_path) is None


def test_lire_sans_fichier_vaut_None(tmp_path):
    assert projet.lire(tmp_path) is None
