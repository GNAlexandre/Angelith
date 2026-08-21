# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Garde-fou de versionnage : `core/version.py` est la SOURCE UNIQUE DE VÉRITÉ, et
rien ne doit pouvoir dériver derrière son dos.

Le risque concret : bumper `__version__` en oubliant le CHANGELOG (ou l'inverse), puis
poser un tag `v0.10.0` dont le contenu n'est documenté nulle part. Comme les prompts
comptent ici comme de la sortie (`git checkout v0.9.0 -- prompts/` doit reproduire la
voix d'un tome), un tag sans entrée de changelog est une piste perdue.
"""
import re
from pathlib import Path

import pytest

from core.version import ETAT_BRIQUES, __version__

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"

# `## [0.9.0] - 2026-08-13` — tiret ASCII ou cadratin, les deux se rencontrent en
# français ; la date est exigée, c'est elle qui distingue une version PUBLIÉE de
# la section « [Non publié] ».
_ENTREE_DATEE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]\s*[-–—]\s*(\d{4}-\d{2}-\d{2})\s*$")


def _entrees_datees() -> list[tuple[str, str]]:
    return [m.groups() for m in
            (_ENTREE_DATEE.match(ln) for ln in CHANGELOG.read_text(encoding="utf-8").splitlines())
            if m]


def test_version_est_un_semver_simple():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_le_changelog_existe_et_a_au_moins_une_entree_datee():
    assert CHANGELOG.exists(), "CHANGELOG.md est la contrepartie documentaire de version.py"
    assert _entrees_datees(), "aucune entrée « ## [x.y.z] - AAAA-MM-JJ » dans CHANGELOG.md"


def test_version_correspond_a_la_premiere_entree_datee_du_changelog():
    """LE test du lot 0 : `__version__` == version la plus récente documentée."""
    version_changelog, _date = _entrees_datees()[0]
    assert version_changelog == __version__, (
        f"core/version.py annonce {__version__}, mais la première entrée datée du "
        f"CHANGELOG est {version_changelog} — bumper l'un sans l'autre finit en tag "
        f"non documenté.")


def test_les_entrees_datees_sont_en_ordre_decroissant():
    """Keep a Changelog : le plus récent en haut. Sinon `_entrees_datees()[0]` (donc le
    test ci-dessus) validerait contre une vieille version."""
    versions = [tuple(int(n) for n in v.split(".")) for v, _ in _entrees_datees()]
    assert versions == sorted(versions, reverse=True), versions


def test_les_dates_sont_en_ordre_decroissant():
    dates = [d for _, d in _entrees_datees()]
    assert dates == sorted(dates, reverse=True), dates


def test_aucune_version_dupliquee():
    versions = [v for v, _ in _entrees_datees()]
    assert len(versions) == len(set(versions)), versions


def test_le_changelog_porte_la_regle_de_numerotation():
    """La règle MAJEUR/MINEUR/CORRECTIF de ce projet n'est pas celle de SemVer par défaut
    (ici, ce qui fait un MAJEUR c'est l'invalidation d'un cache : une relance de tome
    coûte des heures de GPU). Si elle disparaît du fichier, la numérotation redevient
    arbitraire."""
    texte = CHANGELOG.read_text(encoding="utf-8")
    for mot in ("MAJEUR", "MINEUR", "CORRECTIF"):
        assert mot in texte, mot


# Les briques de traitement du dépôt, et le script qui les lance. `gui.py` et `app.py` n'y
# figurent pas : ce sont des FAÇADES, sans chemin de traitement propre — leur degré de
# confiance est celui des briques qu'elles pilotent (cf. la note de `core/version.py`).
BRIQUES = {"ln": "run.py", "manga": "run_manga.py", "scan": "run_ocr.py"}


def test_etat_des_briques_declare_toutes_les_briques():
    """Une brique livrée sans état déclaré se lance sans que rien n'en dise la maturité —
    or c'est sur cette ligne qu'on décide d'engager deux heures d'OCR ou de GPU."""
    assert set(ETAT_BRIQUES) == set(BRIQUES)
    assert all(isinstance(v, str) and v for v in ETAT_BRIQUES.values())


def test_chaque_brique_a_son_point_d_entree():
    for script in BRIQUES.values():
        assert (ROOT / script).is_file(), script


@pytest.mark.parametrize("brique,script", sorted(BRIQUES.items()))
def test_chaque_cli_expose_la_version_et_l_etat_de_sa_brique(brique, script):
    """`--version` doit afficher la version du dépôt — et, hors LN, rappeler l'état de la
    brique : un tome de 150 planches ou de 270 pages se lance sur la foi de cette ligne.
    « bêta » jusqu'à la 0.40.0 pour le manga, « stable » depuis la 1.0.0 ; « bêta » pour
    `scan` depuis la 1.4.0."""
    import subprocess
    import sys

    out = subprocess.run([sys.executable, script, "--version"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    affiche = (out.stdout + out.stderr).strip()
    assert __version__ in affiche, affiche
    if brique != "ln":
        assert ETAT_BRIQUES[brique] in affiche, affiche
