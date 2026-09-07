# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le protocole `Reporter`, et le fait que **tout le monde le porte en entier**.

## Pourquoi ce fichier existe

Le lot 32 ajoute deux choses au protocole : une méthode `phase()` et un argument optionnel
`objet` à `progres()`. La première a immédiatement fait tomber un double de test qui ne
déclarait que ce qu'il écoutait — `AttributeError: '_RecordingReporter' object has no
attribute 'phase'`, au milieu d'un `process_volume`.

C'est exactement le défaut que `tests/test_gui_reporter.py` nomme depuis le lot 18 : « un
orchestrateur qui appelle une méthode oubliée fait tomber un run de 150 planches dans un fil
d'arrière-plan, où l'erreur n'est visible que si on pense à regarder le journal ». Ce fichier
généralise la garde à **tous** les reporters du dépôt, doubles de test compris — parce qu'un
double qui s'écarte du protocole qu'il double ne teste plus rien.

## Ce qu'il ne fait pas

Il ne vérifie pas ce que chaque reporter FAIT de ces appels. `Reporter.phase` et
`Reporter.progres` ont un corps vide, et c'est la condition pour que l'extension soit iso
côté console : la preuve par la sortie est dans
`tests/test_manga_runtime.py::test_la_sortie_console_dun_dry_run_est_identique_octet_pour_octet`.
"""
from __future__ import annotations

import contextlib
import inspect
import io

import pytest

from core.reporter import Reporter

#: Le protocole, avec le nombre d'arguments POSITIONNELS obligatoires de chacun. C'est la
#: liste de référence : l'élargir demande d'élargir tous les doubles, et c'est le but.
PROTOCOLE: dict[str, int] = {
    "volume": 1, "chapter": 3, "stage": 1, "block": 2, "progres": 2, "phase": 1,
    "info": 1, "verbose": 1, "warn": 1, "finish": 1, "stopped": 2,
}

#: Les canaux ajoutés par le lot 32. Muets par contrat.
CANAUX_MUETS = ("phase", "progres")


def _reporters():
    """Toutes les classes du dépôt qui jouent un `Reporter`, doubles de test compris."""
    from tools.tracer_progression import Enregistreur
    couples = [("Reporter", Reporter)]
    try:
        from core.reporter import RichReporter
        couples.append(("RichReporter", RichReporter))
    except Exception:                                    # pragma: no cover — rich absent
        pass
    couples.append(("Enregistreur", Enregistreur))
    try:
        from gui.travailleur import ReporterQt
        couples.append(("ReporterQt", ReporterQt))
    except Exception:                                    # PySide6 absent : cf. lot 18
        pass
    from tests.test_orchestrator import _RecordingReporter
    from tests.test_scan_orchestrator import ReporterMuet
    couples.append(("_RecordingReporter", _RecordingReporter))
    couples.append(("ReporterMuet", ReporterMuet))
    return couples


@pytest.mark.parametrize("nom,classe", _reporters())
def test_le_protocole_est_porte_en_entier(nom, classe):
    """Chaque reporter déclare chaque méthode, avec assez d'arguments pour l'appel réel."""
    for methode, arite in PROTOCOLE.items():
        fonction = getattr(classe, methode, None)
        assert callable(fonction), f"{nom} n'a pas de méthode « {methode} »"
        signature = inspect.signature(fonction)
        positionnels = [p for p in signature.parameters.values()
                        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                        and p.name != "self"]
        variadique = any(p.kind == p.VAR_POSITIONAL for p in signature.parameters.values())
        assert variadique or len(positionnels) >= arite, \
            f"{nom}.{methode} accepte {len(positionnels)} argument(s), il en faut {arite}"


def test_l_objet_de_progres_est_optionnel_partout():
    """C'est ce qui rend l'extension compatible : aucun appelant d'avant n'est invalidé."""
    for nom, classe in _reporters():
        parametres = inspect.signature(classe.progres).parameters
        if "objet" not in parametres:
            continue
        assert parametres["objet"].default == "", f"{nom}.progres impose l'objet"


def test_les_deux_canaux_neufs_sont_muets_dans_le_socle():
    """`phase` et `progres` n'écrivent rien : c'est la condition de l'iso console."""
    for fabrique in (Reporter, _rich):
        reporter = fabrique()
        if reporter is None:                             # pragma: no cover — rich absent
            continue
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            reporter.phase("traduction", "Traduction et rendu")
            reporter.progres(84, 131, "page_0084.png")
            reporter.progres(99, 0, "lot 80→99")
        assert tampon.getvalue() == ""


def _rich():
    try:
        from core.reporter import RichReporter
        return RichReporter()
    except Exception:                                    # pragma: no cover — rich absent
        return None


def test_le_socle_documente_les_deux_canaux():
    """Un canal muet sans docstring est un canal que personne ne saura brancher."""
    for methode in CANAUX_MUETS:
        doc = getattr(Reporter, methode).__doc__ or ""
        assert len(doc) > 200, f"Reporter.{methode} n'explique pas ce qu'il est"
