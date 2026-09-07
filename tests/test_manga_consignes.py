# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les fragments de prompt que le chemin manga assemble lui-même (lot 15, L7.12).

Le prompt d'une planche n'est pas un fichier : il est **assemblé ligne à ligne** par
`orchestrator_manga`. `docs/mesures/inventaire-couplage-fr.md` §5.2 avait relevé dix sites qui le
construisaient en dur, en français, dans du Python — c'est-à-dire dix instructions qu'un pack
de langue cible ne pouvait pas surcharger, et qui partaient en français au milieu d'un run
anglais.

Deux propriétés dominent ces tests :

1. **Le français reste au site d'appel.** `langues/fr/pack.yaml` déclare toujours
   `consignes: {}`, et c'est ce qui rend l'identité de sortie du mode compatibilité vraie
   *par construction* plutôt que par vigilance.
2. **Un gabarit fautif est refusé AU DÉMARRAGE.** Une `KeyError` levée au premier lot groupé
   arriverait après la détection, le nettoyage et l'OCR de vingt planches.
"""
from __future__ import annotations

import pytest

from core.langues import ErreurPack, Pack
from manga import consignes


def _pack(**surcharges) -> Pack:
    return Pack(code="xx", racine=None, consignes=dict(surcharges))


# --------------------------------------------------------------------------- #
# Le repli français
# --------------------------------------------------------------------------- #

def test_sans_pack_le_texte_est_celui_du_depot():
    assert consignes.texte(None, "manga_groupe_entete", groupe=3) == "— Groupe 3 —"


def test_un_pack_qui_ne_declare_rien_sert_le_texte_du_depot():
    """Le mode compatibilité : `fr/pack.yaml` déclare `consignes: {}`, et rien ne change."""
    assert consignes.texte(_pack(), "manga_precedentes_entete") == consignes.PRECEDENTES_ENTETE


def test_un_pack_surcharge_le_fragment():
    pack = _pack(manga_groupe_entete="-- Group {groupe} --")

    assert consignes.texte(pack, "manga_groupe_entete", groupe=2) == "-- Group 2 --"


def test_le_sens_de_lecture_suit_le_format_et_le_pack():
    """Le prompt annonçait « droite → gauche » en dur : sur un webtoon, numéroté
    gauche→droite, cette phrase décrit l'inverse de ce qu'il reçoit."""
    assert consignes.libelle_ordre("gauche_droite") == consignes.ORDRE_GAUCHE_DROITE
    assert consignes.libelle_ordre("droite_gauche") == consignes.ORDRE_DROITE_GAUCHE
    assert consignes.libelle_ordre("gauche_droite",
                                   _pack(manga_ordre_gauche_droite="L→R")) == "L→R"


# --------------------------------------------------------------------------- #
# Les mentions de type — la moitié qui n'écrit RIEN
# --------------------------------------------------------------------------- #

def test_les_types_qui_ne_tranchent_rien_n_ecrivent_rien():
    """`dialogue` et `indetermine` sont muets, et c'est le point du lot : un type mal deviné
    est pire qu'aucun type."""
    assert consignes.mention_de_type(None, "dialogue") == ""
    assert consignes.mention_de_type(None, "indetermine") == ""
    assert consignes.mention_de_type(None, "pensee") == "(pensée)"


def test_une_mention_de_type_est_surchargeable():
    """Sans quoi un run anglais recevrait « (pensée) » au beau milieu d'un prompt anglais —
    à l'INTÉRIEUR d'une ligne numérotée, donc collé à la réplique qu'il annote."""
    assert consignes.mention_de_type(_pack(manga_type_cri="(shout)"), "cri") == "(shout)"


# --------------------------------------------------------------------------- #
# Le garde-fou de gabarit
# --------------------------------------------------------------------------- #

def test_un_pack_sans_surcharge_passe_la_verification():
    consignes.verifier(_pack())
    consignes.verifier(None)


def test_un_champ_inconnu_fait_refuser_le_pack_au_demarrage():
    """`{page}` au lieu de `{planche}` : la faute la plus facile à écrire, et celle qui ne se
    verrait qu'au premier lot groupé."""
    pack = _pack(manga_separateur_planche="— Plate {page} —")

    with pytest.raises(ErreurPack) as err:
        consignes.verifier(pack)

    message = str(err.value)
    assert "manga_separateur_planche" in message
    assert "{planche}" in message, "le message doit lister les champs disponibles"


def test_une_accolade_mal_fermee_fait_refuser_le_pack():
    with pytest.raises(ErreurPack):
        consignes.verifier(_pack(manga_bulles_entete="Bubbles in {langue :"))


def test_un_gabarit_fautif_qui_passerait_la_verification_retombe_sur_le_francais():
    """Ceinture et bretelles : `texte()` ne lève JAMAIS. Remonter une `KeyError` depuis le
    milieu d'un lot ne dirait rien d'utile et perdrait vingt planches."""
    pack = _pack(manga_groupe_entete="— Groupe {inconnu} —")

    assert consignes.texte(pack, "manga_groupe_entete", groupe=1) == "— Groupe 1 —"


# --------------------------------------------------------------------------- #
# L'inventaire lui-même
# --------------------------------------------------------------------------- #

def test_chaque_cle_declaree_a_un_texte_francais():
    """La table EST la source du texte français : une clé sans texte serait une consigne que
    le mode compatibilité ne saurait pas servir."""
    for cle, defaut in consignes.CLES.items():
        assert isinstance(defaut, str) and defaut.strip(), cle


def test_aucun_gabarit_ne_demande_un_champ_que_le_code_ne_fournit_pas():
    """Le pendant de `verifier()`, appliqué au dépôt lui-même : si un défaut employait un
    champ absent de `_FACTICES`, le français lèverait là où un pack serait refusé."""
    for cle in consignes.CLES:
        consignes.texte(None, cle, **consignes._FACTICES)


def test_le_pack_francais_ne_recopie_aucune_consigne():
    """La règle du dépôt : le texte français vit à son site d'appel. Le recopier dans
    `langues/fr/pack.yaml` en ferait une seconde source, libre de diverger, dont l'une
    déciderait de la sortie d'un tome."""
    import yaml
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1]
    meta = yaml.safe_load((racine / "langues" / "fr" / "pack.yaml").read_text(encoding="utf-8"))

    assert (meta.get("consignes") or {}) == {}
