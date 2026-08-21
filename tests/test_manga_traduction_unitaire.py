# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Traduction d'UNE bulle — le prompt partagé par le rattrapage et l'éditeur graphique.

Ce module a été extrait de `_rattraper_bulles`, où il vivait en dur. L'enjeu du test est donc
la NON-DUPLICATION : le prompt porte trois garde-fous tirés de mesures, et ce qui est dessiné
dans une bulle dépend entièrement d'eux. Deux copies seraient deux jumelles libres de diverger.

On vérifie donc à la fois le contrat de la fonction (refus plutôt que dessin) et le fait que le
rattrapage l'emprunte réellement, au lieu d'avoir gardé sa propre version.
"""
from __future__ import annotations

import pytest

from manga import quality_manga, traduction_unitaire


class _Agent:
    """Double d'agent : journalise le prompt et rend une réponse fixée."""

    temperature = 0.3
    dry_run = False
    llm = None

    def __init__(self, reponse="Traduction"):
        self.reponse = reponse
        self.prompts: list[str] = []
        self.caps: list[int] = []

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.prompts.append(user)
        self.caps.append(max_tokens)
        return self.reponse


# --------------------------------------------------------------------------- #
# Le prompt
# --------------------------------------------------------------------------- #

def test_le_prompt_porte_la_consigne_de_forme_et_la_source():
    """Sans la consigne, le modèle reprend la forme de PAGE (une liste numérotée), que
    `diagnostiquer_rattrapage` doit alors rejeter — un appel payé pour rien."""
    p = traduction_unitaire.prompt_bulle("アアア")
    assert traduction_unitaire.CONSIGNE in p
    assert "アアア" in p
    assert "pas de numéro" in p


def test_le_gabarit_apparait_quand_la_bbox_est_connue():
    p = traduction_unitaire.prompt_bulle("アアア", bbox=(0, 0, 280, 160))
    assert "280×160 px" in p
    assert "caractères" in p


def test_sans_bbox_aucun_gabarit_n_est_invente():
    assert "Place disponible" not in traduction_unitaire.prompt_bulle("アアア")


def test_le_glossaire_ouvre_le_prompt():
    """Même position que dans la traduction de planche : le glossaire est le premier bloc."""
    p = traduction_unitaire.prompt_bulle("アアア", gloss_text="# GLOSSAIRE\n- Sleipnir")
    assert p.startswith("# GLOSSAIRE")


# --------------------------------------------------------------------------- #
# Les garde-fous
# --------------------------------------------------------------------------- #

def test_une_source_sans_texte_n_est_pas_envoyee_au_modele():
    """L'OCR `（）` de la page 8 bulle 1 n'a rien à traduire : la faire traduire reviendrait à
    faire inventer une réplique à partir de rien."""
    agent = _Agent()
    texte, motif = traduction_unitaire.traduire_bulle(agent, "（）")
    assert (texte, motif) == ("", "source_vide")
    assert agent.prompts == [], "aucun appel LLM ne doit partir"


def test_tous_les_motifs_de_refus_ont_un_libelle():
    """L'appelant affiche le motif tel quel — un motif sans libellé lèverait un KeyError dans
    le rattrapage, en plein milieu d'un tome."""
    agent = _Agent("1. Une\n2. Deux")
    _texte, motif = traduction_unitaire.traduire_bulle(agent, "アアア")
    assert motif == "liste"
    assert set(quality_manga.LIBELLES_RATTRAPAGE) >= {"source_vide", "vide", "liste",
                                                      "japonais_residuel", "disproportionnee"}


def test_une_reponse_diagnostiquee_est_rejetee_pas_rendue():
    """Une mauvaise réplique dessinée dans une bulle est pire qu'une bulle vide, qui est au
    moins signalée au rapport."""
    texte, motif = traduction_unitaire.traduire_bulle(_Agent("アアア"), "アアア")
    assert texte == "" and motif == "japonais_residuel"


def test_une_reponse_vide_est_rejetee():
    texte, motif = traduction_unitaire.traduire_bulle(_Agent("   "), "アアア")
    assert texte == "" and motif == "vide"


def test_un_prefixe_numerote_isole_est_retire_pas_rejete():
    """Un « 1. » isolé est une scorie de forme, pas une liste : on le retire au lieu de perdre
    la réponse."""
    texte, motif = traduction_unitaire.traduire_bulle(_Agent("1. Bonjour"), "アアア")
    assert (texte, motif) == ("Bonjour", None)


def test_le_plafond_est_proportionne_a_la_source_seule():
    """Un vrai `max_tokens` réactive la détection de troncature du client LLM."""
    agent = _Agent()
    traduction_unitaire.traduire_bulle(agent, "アアア")
    assert agent.caps == [quality_manga.bubbles_cap("アアア", 1)]


# --------------------------------------------------------------------------- #
# La non-duplication
# --------------------------------------------------------------------------- #

def test_le_rattrapage_emprunte_bien_la_fonction_partagee(monkeypatch):
    """Si `_rattraper_bulles` regagnait sa propre copie du prompt, ce test tomberait — c'est
    tout ce qu'on lui demande."""
    from manga import orchestrator_manga as orch

    vus: list[str] = []

    def _faux(agent, source, *, gloss_text="", bbox=None):
        vus.append(source)
        return "Rattrapée", None

    monkeypatch.setattr(orch.traduction_unitaire, "traduire_bulle", _faux)
    textes, rattrapees, refus = orch._rattraper_bulles(
        _Agent(), ["アアア", "イイイ"], ["Un", ""], page=1)

    assert vus == ["イイイ"], "seule la bulle vide est reprise"
    assert textes == ["Un", "Rattrapée"]
    assert rattrapees == [1] and refus == []


def test_le_rattrapage_propage_un_refus_sans_rien_dessiner(monkeypatch):
    from manga import orchestrator_manga as orch

    monkeypatch.setattr(orch.traduction_unitaire, "traduire_bulle",
                        lambda *a, **k: ("", "japonais_residuel"))
    textes, rattrapees, refus = orch._rattraper_bulles(
        _Agent(), ["アアア"], [""], page=4)

    assert textes == [""], "la bulle reste vide plutôt que mal remplie"
    assert rattrapees == []
    assert len(refus) == 1 and "page 4 bulle 1" in refus[0]
