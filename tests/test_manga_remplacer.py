# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Rechercher-remplacer sur tout un tome.

Corriger un nom sur quarante planches demandait quarante ouvertures. Ce qui est en jeu ici
n'est pas la commodité mais la SÛRETÉ du geste : un remplacement global est facile à lancer
et difficile à défaire. D'où trois garanties testées —

- il n'écrit que dans la réplique AFFICHÉE (jamais dans l'OCR, qui est du texte source, ni
  dans la traduction du modèle, qu'un `--from traduction` réécrirait) ;
- il atterrit dans `traduction_manuelle.json`, le seul fichier que le pipeline ne réécrit
  jamais, donc il survit à toute relance ;
- il ne touche QUE les occurrences qu'on lui donne : c'est ce qui permet d'en décocher une.
"""
import numpy as np

from manga import checkpoints, recherche
from manga.detection import BubbleRegion


def _region(i):
    mask = np.zeros((100, 100), dtype=bool)
    mask[10 * i:10 * i + 8, 10:20] = True
    return BubbleRegion(bbox=(10, 10 * i, 20, 10 * i + 8), mask=mask, score=0.9,
                        cls=0, kind="bulle")


def _semer(build, planche, traductions, ocr=None, manuelles=None):
    ck = checkpoints.page_checkpoint_dir(build, planche)
    checkpoints.save_regions(ck, [_region(i) for i in range(len(traductions))], (100, 100))
    checkpoints.save_ocr(ck, ocr or ["" for _ in traductions])
    checkpoints.save_traduction(ck, traductions)
    if manuelles:
        checkpoints.save_traduction_manuelle(ck, manuelles)
    return ck


# ── remplacer_dans : la comparaison ──────────────────────────────────────────

def test_remplace_toutes_les_occurrences():
    assert recherche.remplacer_dans("Leo et Leo", "Leo", "Léon") == "Léon et Léon"


def test_insensible_a_la_casse_et_aux_accents():
    """La même comparaison que `chercher` — sinon on montrerait des résultats qu'on ne
    saurait pas remplacer."""
    assert recherche.remplacer_dans("Léo parle à LEO", "leo", "Ravi") == "Ravi parle à Ravi"


def test_le_texte_autour_reste_intact():
    """Découper sur la forme normalisée rendrait « Cafe » là où la planche dit « Café »."""
    assert recherche.remplacer_dans("Léo au café", "léo", "Ravi") == "Ravi au café"


def test_les_kana_voises_ne_sont_pas_confondus():
    """Le dakuten change le son, donc le mot : « ガ » ne doit pas se faire remplacer en
    cherchant « カ » (cf. `normaliser`)."""
    assert recherche.remplacer_dans("ガギグ", "カキク", "X") == "ガギグ"


def test_motif_vide_ne_touche_a_rien():
    assert recherche.remplacer_dans("Léo", "", "X") == "Léo"


def test_la_longueur_n_est_PAS_preservee_et_le_remplacement_tient_quand_meme():
    """`casefold()` rend « ß » → « ss » : la forme normalisée est plus longue que l'original.
    Un découpage par index nu écrirait donc au mauvais endroit — silencieusement, sur
    quarante planches. D'où la table d'origines de `_table_normalisee`."""
    assert len(recherche.normaliser("Straße")) != len("Straße")

    forme, origines = recherche._table_normalisee("Straße")
    assert len(origines) == len(forme)
    assert recherche.remplacer_dans("Straße Nord", "strasse", "Rue") == "Rue Nord"


def test_remplacement_apres_un_caractere_qui_change_de_longueur():
    """Le cas qui casse un découpage naïf : la trouvaille est APRÈS le « ß », donc ses index
    normalisés sont décalés d'un cran par rapport à l'original."""
    assert recherche.remplacer_dans("Straße, Léo arrive", "léo", "Ravi") == "Straße, Ravi arrive"


# ── remplacer : l'écriture ───────────────────────────────────────────────────

def test_ecrit_dans_traduction_manuelle_pas_dans_traduction(tmp_path):
    """Ce qui fait qu'un nom corrigé survit à un `--from traduction`."""
    ck = _semer(tmp_path, 1, ["Bonjour Leo", "Rien"])

    occ = recherche.occurrences_remplacables(tmp_path, "Leo")
    assert recherche.remplacer(tmp_path, "Leo", "Léon", occ) == [1]

    assert checkpoints.load_traduction(ck) == ["Bonjour Leo", "Rien"]     # intact
    assert checkpoints.load_traduction_manuelle(ck) == {0: "Bonjour Léon"}


def test_ne_touche_que_les_occurrences_donnees(tmp_path):
    """Décocher une occurrence doit vraiment l'épargner — c'est tout l'intérêt de la
    prévisualisation : une planche peut parler d'un AUTRE Leo."""
    _semer(tmp_path, 1, ["Leo arrive"])
    _semer(tmp_path, 2, ["Leo repart"])

    occ = recherche.occurrences_remplacables(tmp_path, "Leo")
    assert len(occ) == 2
    gardees = [o for o in occ if o["planche"] == 1]

    assert recherche.remplacer(tmp_path, "Leo", "Léon", gardees) == [1]
    assert checkpoints.load_traduction_manuelle(
        checkpoints.page_checkpoint_dir(tmp_path, 2)) == {}


def test_l_ocr_n_est_jamais_propose_ni_touche(tmp_path):
    """L'OCR est du texte SOURCE : y « corriger » un nom français n'a pas de sens, et le
    modifier périmerait la traduction qui en descend."""
    ck = _semer(tmp_path, 1, ["rien"], ocr=["Leo dit"])

    assert recherche.occurrences_remplacables(tmp_path, "Leo") == []
    assert recherche.remplacer(tmp_path, "Leo", "Léon",
                               recherche.chercher(tmp_path, "Leo")) == []
    assert checkpoints.load_ocr(ck) == ["Leo dit"]


def test_une_correction_manuelle_existante_est_reprise(tmp_path):
    """On remplace dans ce qui est AFFICHÉ. Repartir de la traduction du modèle écraserait
    une correction déjà faite à la main."""
    ck = _semer(tmp_path, 1, ["Leo du modèle"], manuelles={0: "Leo corrigé à la main"})

    occ = recherche.occurrences_remplacables(tmp_path, "Leo")
    recherche.remplacer(tmp_path, "Leo", "Léon", occ)

    assert checkpoints.load_traduction_manuelle(ck) == {0: "Léon corrigé à la main"}


def test_une_planche_sans_occurrence_n_est_pas_reecrite(tmp_path):
    ck = _semer(tmp_path, 1, ["Rien ici"])
    avant = (ck / "traduction.json").stat().st_mtime_ns

    assert recherche.remplacer(tmp_path, "Leo", "Léon", [
        {"planche": 1, "bulle": 0, "champ": recherche.CHAMP_AFFICHEE}]) == []
    assert (ck / "traduction.json").stat().st_mtime_ns == avant


def test_une_bulle_disparue_depuis_la_recherche_est_sautee(tmp_path):
    """Entre la recherche et le remplacement, un run a pu re-détecter la planche."""
    _semer(tmp_path, 1, ["Leo"])
    occ = [{"planche": 1, "bulle": 7, "champ": recherche.CHAMP_AFFICHEE}]

    assert recherche.remplacer(tmp_path, "Leo", "Léon", occ) == []
