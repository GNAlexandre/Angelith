# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Moteur de garde-fous partagé (`core/quality.py`, lot 2.5).

Les registres de motifs des deux briques ont leurs propres tests
(`tests/test_orchestrator.py`, `tests/test_manga_quality.py`) : ils n'ont pas changé. Ici on
teste le MOTEUR, et surtout les trois points où les deux briques diffèrent réellement et qui
sont donc devenus des paramètres — `cle_ok`, `motifs_plus_chaud`, `prefere`. Ce sont eux qui
pourraient dériver en silence, chacune des deux briques n'exerçant que sa moitié.
"""
from __future__ import annotations

import pytest

from core.quality import (MOTIFS_PLUS_CHAUD, out_cap, premier_motif,
                          try_with_temp_retry)


def _appelant(sorties):
    """Callable `call(temperature)` qui rend les sorties dans l'ordre, en notant les
    températures reçues."""
    seq = list(sorties)
    temperatures: list[float | None] = []

    def call(temp):
        temperatures.append(temp)
        return seq.pop(0) if seq else ""
    return call, temperatures


# --- out_cap ---------------------------------------------------------------------


def test_out_cap_proportionnel_et_borne():
    petit, gros = out_cap("mot " * 10), out_cap("mot " * 10000)
    assert petit < gros
    assert out_cap("x", floor=768) >= 768
    assert out_cap("x" * 100000, ceil=6000) <= 6000


# --- premier_motif ---------------------------------------------------------------


def test_premier_motif_respecte_lordre_du_registre():
    """L'ordre n'est pas décoratif : côté light novel, `repetition` passe AVANT
    `emballement`, et c'est cet ordre qui fait qu'un bloc ayant bouclé jusqu'à saturer son
    plafond est étiqueté « repetition » — donc redécoupé (cf. `_RESPLIT_REASONS`)."""
    motifs = (("a", lambda c: True), ("b", lambda c: True))
    assert premier_motif(motifs, object()) == "a"
    assert premier_motif(tuple(reversed(motifs)), object()) == "b"


def test_premier_motif_rend_none_quand_rien_ne_sapplique():
    assert premier_motif((("a", lambda c: False),), object()) is None


def test_le_moteur_ne_regarde_jamais_le_contexte():
    """Le contexte est le type de la brique — bulles d'un côté, titres ATX de l'autre. Le
    socle le passe sans l'inspecter, sinon il redeviendrait couplé à une unité de travail."""
    class Opaque:
        def __getattr__(self, nom):
            raise AssertionError(f"le socle a inspecté le contexte : .{nom}")

    vus = []
    assert premier_motif((("x", lambda c: vus.append(c) or False),), Opaque()) is None
    assert len(vus) == 1


# --- le moteur de retry ----------------------------------------------------------


def test_premiere_tentative_reussie_compte_sous_la_cle_de_la_brique():
    """`cle_ok` diffère : « blocs_ok » pour un chapitre, « pages_ok » pour une planche. Les
    deux vont dans le même dictionnaire de statistiques, lu par des rapports différents."""
    stats: dict = {}
    call, temps = _appelant(["bon"])
    assert try_with_temp_retry(call, lambda s: None, stats=stats,
                               cle_ok="pages_ok") == ("bon", True, None)
    assert stats == {"pages_ok": 1}
    assert temps == [None], "la première tentative doit utiliser la température de l'agent"


def test_le_retry_baisse_la_temperature_par_defaut():
    stats: dict = {}
    call, temps = _appelant(["", "bon"])
    sortie, ok, motif = try_with_temp_retry(
        call, lambda s: "vide" if not s else None, stats=stats,
        temperature=0.5, temp_factor=0.4)
    assert (sortie, ok, motif) == ("bon", True, None)
    assert temps[1] == pytest.approx(0.2)
    assert stats == {"retry_temp_reduite": 1, "recupere_par_retry": 1, "blocs_ok": 1}


def test_le_retry_releve_la_temperature_sur_une_boucle():
    """Sur une boucle dégénérée, resserrer le modèle RENFORCE le cycle : c'est une
    pathologie de basse température. Vérifié sur roman D Vol.1, où les deux
    appels de chaque bloc perdu ont bouclé."""
    stats: dict = {}
    call, temps = _appelant(["boucle", "bon"])
    try_with_temp_retry(call, lambda s: "repetition" if s == "boucle" else None,
                        stats=stats, temperature=0.3, temp_factor=0.4)
    assert temps[1] == pytest.approx(0.75)       # max(0.3, 0.2) / 0.4
    assert stats["retry_temp_relevee"] == 1
    assert "retry_temp_reduite" not in stats


def test_la_temperature_est_plafonnee_a_1():
    call, temps = _appelant(["boucle", "bon"])
    try_with_temp_retry(call, lambda s: "repetition" if s == "boucle" else None,
                        temperature=0.9, temp_factor=0.4)
    assert temps[1] == 1.0


def test_la_direction_est_recalculee_a_chaque_essai():
    """Point subtil : la direction dépend du motif du PRÉCÉDENT essai, pas du premier. Un
    bloc vide qui devient une boucle au 2e essai doit voir sa température RELEVÉE au 3e —
    sinon on resserrerait une boucle. Invisible côté light novel (un seul retry), mais le
    manga peut en configurer plusieurs."""
    stats: dict = {}
    call, temps = _appelant(["", "boucle", "boucle"])
    diag = {"": "vide", "boucle": "repetition"}
    try_with_temp_retry(call, lambda s: diag.get(s), stats=stats,
                        temperature=0.5, temp_factor=0.4, max_retries=2)
    assert temps[1] == pytest.approx(0.2), "1er retry : motif « vide » → plus froid"
    assert temps[2] == 1.0, "2e retry : motif « repetition » → plus chaud"
    assert stats["retry_temp_reduite"] == 1 and stats["retry_temp_relevee"] == 1


def test_le_motif_rendu_est_celui_du_premier_essai():
    """C'est lui qui décrit ce qui a réellement dérapé — et c'est sous lui que le compteur
    est incrémenté, pour que le rapport nomme la cause et non son symptôme de rattrapage."""
    stats: dict = {}
    call, _ = _appelant(["", "boucle"])
    diag = {"": "vide", "boucle": "repetition"}
    sortie, ok, motif = try_with_temp_retry(call, lambda s: diag.get(s), stats=stats)
    assert (ok, motif) == (False, "vide")
    assert stats == {"retry_temp_reduite": 1, "vide": 1}
    assert "repetition" not in stats


def test_sans_prefere_la_premiere_sortie_est_conservee():
    call, _ = _appelant(["premiere", "seconde"])
    sortie, ok, _ = try_with_temp_retry(call, lambda s: "vide", prefere=None)
    assert (sortie, ok) == ("premiere", False)


def test_prefere_peut_retenir_la_seconde():
    """« Meilleure » n'a pas le même sens selon la brique : nombre de mots récupérables pour
    un bloc de récit, nombre de répliques numérotées pour une planche."""
    call, _ = _appelant(["court", "beaucoup plus long"])
    sortie, ok, motif = try_with_temp_retry(
        call, lambda s: "vide", prefere=lambda g, mg, c, mc: len(c) > len(g))
    assert (sortie, ok, motif) == ("beaucoup plus long", False, "vide")


def test_prefere_recoit_les_deux_motifs():
    """Le light novel exige l'égalité des motifs avant de comparer des longueurs : comparer
    entre deux pathologies distinctes n'aurait pas de sens. Les motifs doivent donc arriver
    jusqu'au comparateur."""
    vus = []
    call, _ = _appelant(["a", "b"])
    diag = {"a": "vide", "b": "repetition"}
    try_with_temp_retry(call, lambda s: diag[s],
                        prefere=lambda g, mg, c, mc: vus.append((mg, mc)) or False)
    assert vus == [("vide", "repetition")]


def test_max_retries_zero_ne_retente_rien():
    stats: dict = {}
    call, temps = _appelant(["mauvais", "jamais atteint"])
    sortie, ok, motif = try_with_temp_retry(call, lambda s: "vide", stats=stats,
                                            max_retries=0)
    assert (sortie, ok, motif) == ("mauvais", False, "vide")
    assert temps == [None]
    assert stats == {"vide": 1}


def test_stats_est_optionnel():
    """Appelé sans dictionnaire, le moteur ne doit pas exploser — c'est le cas des tests de
    prédicats des deux briques."""
    call, _ = _appelant(["bon"])
    assert try_with_temp_retry(call, lambda s: None)[1] is True


def test_les_deux_briques_partagent_le_meme_ensemble_plus_chaud():
    """Que la boucle soit une pathologie de basse température est une propriété du MODÈLE,
    pas de l'unité de travail : les deux briques doivent avoir le même ensemble, sans quoi la
    même sortie serait retentée dans deux directions opposées selon le pipeline."""
    from manga.quality_manga import MOTIFS_PLUS_CHAUD as MANGA
    from pipeline.orchestrator import _RETRY_HOTTER_REASONS as LN
    assert MANGA == MOTIFS_PLUS_CHAUD == LN
