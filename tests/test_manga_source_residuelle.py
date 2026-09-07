# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Garde-fou « la source est restée dans la sortie », généralisé à toute langue.

Sur une source CJK, la présence de kana suffit — c'est le test historique. Sur une source
latine, aucune classe de caractères ne peut trancher : l'anglais et le français s'écrivent
dans le même alphabet. Le vrai risque devient la recopie À L'IDENTIQUE, et il faut comparer.

⚠ La clé du motif reste `japonais_residuel` : elle est persistée dans les `qa.json` déjà
écrits. Seul le LIBELLÉ nomme la vraie langue.
"""
from manga import quality_manga as q


def _sortie(*lignes):
    return "\n".join(f"{i}. {t}" for i, t in enumerate(lignes, 1))


# --------------------------------------------------------------------------- #
# Source CJK — comportement historique, inchangé
# --------------------------------------------------------------------------- #

def test_cjk_recopie_est_detecte():
    sortie = _sortie("Bonjour", "こんにちは")
    assert q.diagnostiquer(sortie, n=2, cap=0, langue="jp") == "japonais_residuel"


def test_cjk_traduit_ne_declenche_rien():
    sortie = _sortie("Bonjour", "Au revoir")
    assert q.diagnostiquer(sortie, n=2, cap=0, langue="jp") is None


def test_la_ponctuation_pleine_chasse_n_est_pas_du_japonais():
    """Régression de la 0.33.0 : `（）` et `!?` étaient déclarés « du japonais est resté »."""
    sortie = _sortie("（）", "!?")
    assert q.diagnostiquer(sortie, n=2, cap=0, langue="jp") is None


def test_le_defaut_reste_le_japonais():
    """Un appelant qui ne précise rien garde exactement le comportement d'avant."""
    assert q.diagnostiquer(_sortie("こんにちは"), n=1, cap=0) == "japonais_residuel"


# --------------------------------------------------------------------------- #
# Source latine — la recopie ne se voit qu'à la comparaison
# --------------------------------------------------------------------------- #

def test_anglais_recopie_tel_quel_est_detecte():
    source = "HE'S CERTAINLY NO ORDINARY PERSON"
    assert q.diagnostiquer(_sortie(source), n=1, cap=0,
                           sources=[source], langue="en") == "japonais_residuel"


def test_la_recopie_est_reperee_malgre_la_casse_et_la_ponctuation():
    """Un modèle qui « traduit » en changeant seulement la casse n'a rien traduit."""
    source = "SOMETHING SEEMS OFF..."
    rendu = "Something seems off"
    assert q.diagnostiquer(_sortie(rendu), n=1, cap=0,
                           sources=[source], langue="en") == "japonais_residuel"


def test_une_vraie_traduction_ne_declenche_rien():
    assert q.diagnostiquer(_sortie("Quelque chose cloche..."), n=1, cap=0,
                           sources=["SOMETHING SEEMS OFF..."], langue="en") is None


def test_une_replique_courte_identique_est_toleree():
    """« HM ? », « OK », un nom propre : l'identité ne prouve rien en dessous du plancher."""
    for court in ("HM ?", "OK", "Anna"):
        assert q.diagnostiquer(_sortie(court), n=1, cap=0,
                               sources=[court], langue="en") is None, court


def test_du_cjk_dans_une_sortie_latine_ne_declenche_pas_ce_motif():
    """Sur une source anglaise, un kana égaré vient de l'OCR, pas d'une recopie."""
    assert q.diagnostiquer(_sortie("Bonjour の"), n=1, cap=0,
                           sources=["HELLO THERE FRIEND"], langue="en") is None


# --------------------------------------------------------------------------- #
# Contrôle du CACHE (`--from rendu`) — même règle, autre point d'entrée
# --------------------------------------------------------------------------- #

def test_motifs_repliques_cjk():
    assert q.motifs_repliques(["Bonjour", "こんにちは"],
                              langue="jp") == ["japonais_residuel"]
    assert q.motifs_repliques(["Bonjour", "Salut"], langue="jp") == []


def test_motifs_repliques_latin():
    source = ["HE'S CERTAINLY NO ORDINARY PERSON"]
    assert q.motifs_repliques(source, source, langue="en") == ["japonais_residuel"]
    assert q.motifs_repliques(["Ce n'est pas n'importe qui"], source, langue="en") == []


# --------------------------------------------------------------------------- #
# Rattrapage unitaire
# --------------------------------------------------------------------------- #

def test_rattrapage_cjk():
    assert q.diagnostiquer_rattrapage("こんにちは", source="こんにちは",
                                      langue="jp") == "japonais_residuel"


def test_rattrapage_latin():
    source = "SOMETHING SEEMS OFF..."
    assert q.diagnostiquer_rattrapage(source, source=source,
                                      langue="en") == "japonais_residuel"
    assert q.diagnostiquer_rattrapage("Quelque chose cloche", source=source,
                                      langue="en") is None


# --------------------------------------------------------------------------- #
# Libellés
# --------------------------------------------------------------------------- #

def test_le_libelle_nomme_la_vraie_langue():
    """« du japonais est resté » sur un chapitre anglais envoyait chercher un faux problème."""
    assert q.libelle("japonais_residuel", "en") == "de l'anglais est resté dans la sortie"
    assert q.libelle("japonais_residuel", "jp") == "du japonais est resté dans la sortie"
    assert q.libelle("japonais_residuel", "fr") == "du français est resté dans la sortie"


def test_le_libelle_sans_langue_reste_generique():
    assert q.libelle("japonais_residuel") == "du texte source est resté dans la sortie"


def test_les_autres_motifs_sont_inchanges():
    assert q.libelle("vide", "en") == q.LIBELLES["vide"]
    assert q.libelle(None) == ""
