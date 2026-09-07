# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Règles typographiques de la langue cible.

Deux choses sont vérifiées ici, et la première commande la seconde :

1. **Les défauts sont le français d'avant l'externalisation**, au caractère près. Ce ne sont
   pas des valeurs « raisonnables » : c'est le comportement de référence, et le mode
   compatibilité en dépend.
2. **Un pack peut changer la langue de sortie sans toucher au code** — guillemets, fin de
   phrase, titre du guide de style — et surtout **déclarer qu'il n'a pas d'incise
   d'attribution**, ce qui est le cas de l'anglais.
"""
import pytest

from pipeline import render
from pipeline import typographie as ty


class _Pack:
    """Un pack minimal : seuls les attributs que `Typographie.depuis_pack` consulte."""

    def __init__(self, typographie=None, styles_word=None, classes_css=None):
        self.typographie = typographie or {}
        self.styles_word = styles_word or {}
        self.classes_css = classes_css or {}


# ─────────────────────────────────────────────────────────────────────────────
# Les défauts SONT le français d'origine
# ─────────────────────────────────────────────────────────────────────────────

def test_sans_pack_les_regles_sont_le_francais():
    t = ty.Typographie.depuis_pack()

    assert t.dialogue_span.findall("« Bonjour »") == ["Bonjour"]
    assert t.verbes_de_parole is not None
    assert t.tiret_dialogue == "—"
    assert t.tiret_dans_le_texte is False
    assert t.styles_word["dialogue"] == "List Paragraph"
    assert t.styles_word["pensee"] == "Pensée"


@pytest.mark.parametrize("incise", [
    "dit-il en souriant.", "hurla-t-elle.", "murmura Léo.", "pensa-t-il.",
    "répondit la vieille dame.", "s'écria-t-il.", "conclut le capitaine.",
])
def test_les_verbes_de_parole_francais_sont_reconnus(incise):
    """Le lexique décide si l'incise reste collée à sa réplique. Un verbe manquant coupe un
    dialogue en deux paragraphes."""
    assert ty.DEFAUT.verbes_de_parole.match(incise), incise


@pytest.mark.parametrize("narration", [
    "Le vent se leva.", "Elle referma la porte.", "Trois jours passèrent.",
])
def test_la_narration_ordinaire_nest_pas_prise_pour_une_incise(narration):
    assert not ty.DEFAUT.verbes_de_parole.match(narration), narration


def test_la_fin_de_phrase_par_defaut():
    caracteres = {c for c in ".!?…;:,-—«»abc" if ty.DEFAUT.fin_de_phrase.search(c)}

    assert caracteres == {".", "!", "?", "…", ";"}


def test_le_titre_du_guide_de_style_par_defaut():
    """Le garde-fou « le modèle a régurgité le guide » cherche ce titre."""
    assert ty.DEFAUT.guide_de_style.search("# Guide de style — conventions générales")
    assert not ty.DEFAUT.guide_de_style.search("# Style guide — general conventions")


# ─────────────────────────────────────────────────────────────────────────────
# Un pack change la langue sans toucher au code
# ─────────────────────────────────────────────────────────────────────────────

def test_des_guillemets_anglais():
    t = ty.Typographie.depuis_pack(_Pack({"guillemets": ['"', '"']}))

    assert t.dialogue_span.findall('"Hello there"') == ["Hello there"]
    assert t.dialogue_span.findall("« Bonjour »") == []


def test_des_guillemets_allemands():
    """Le pack donne l'ouvrant et le fermant séparément : l'allemand les inverse."""
    t = ty.Typographie.depuis_pack(_Pack({"guillemets": ["„", "“"]}))

    assert t.dialogue_span.findall("„Guten Tag“") == ["Guten Tag"]


def test_les_guillemets_sont_echappes():
    """Un guillemet qui serait un métacaractère d'expression régulière ne doit pas faire
    exploser la compilation ni matcher n'importe quoi."""
    t = ty.Typographie.depuis_pack(_Pack({"guillemets": ["[", "]"]}))

    assert t.dialogue_span.findall("[Bonjour]") == ["Bonjour"]


def test_un_titre_de_guide_propre_au_pack():
    t = ty.Typographie.depuis_pack(_Pack({"titre_guide_de_style": "Style guide"}))

    assert t.guide_de_style.search("## Style guide")
    assert not t.guide_de_style.search("# Guide de style")


def test_une_fin_de_phrase_propre_au_pack():
    t = ty.Typographie.depuis_pack(_Pack({"fin_de_phrase": ".!?"}))

    assert t.fin_de_phrase.search(".")
    assert not t.fin_de_phrase.search(";")


# ─────────────────────────────────────────────────────────────────────────────
# Le cas qui a commandé la conception : pas d'incise d'attribution
# ─────────────────────────────────────────────────────────────────────────────

def test_un_pack_peut_declarer_navoir_pas_dincise():
    """⚠ `None` n'est PAS un défaut manquant, c'est un choix. L'anglais écrit
    `"...," he said`, sans inversion : il n'y a pas de lexique à énumérer, et coller une
    incise selon des règles françaises serait pire que ne rien coller."""
    t = ty.Typographie.depuis_pack(_Pack({"verbes_de_parole": None}))

    assert t.verbes_de_parole is None


def test_sans_incise_le_recit_qui_suit_reste_en_narration():
    """La propriété observable : le rendu ne colle plus l'incise à la réplique."""
    texte = "« Viens. » dit-il en souriant. Le vent se leva."
    sans_incise = ty.Typographie.depuis_pack(_Pack({"verbes_de_parole": None}))

    avec = render._segment_text(texte, "List Paragraph", ty.DEFAUT)
    sans = render._segment_text(texte, "List Paragraph", sans_incise)

    assert any("dit-il" in bloc and ".dialogue" in bloc for bloc in avec)
    assert not any("dit-il" in bloc and ".dialogue" in bloc for bloc in sans)


def test_un_lexique_propre_au_pack():
    t = ty.Typographie.depuis_pack(_Pack({"verbes_de_parole": r"(?:said|asked|replied)\b"}))

    assert t.verbes_de_parole.match("said the captain.")
    assert not t.verbes_de_parole.match("dit-il.")


# ─────────────────────────────────────────────────────────────────────────────
# Styles : la config de l'utilisateur PRIME sur le pack
# ─────────────────────────────────────────────────────────────────────────────

def test_le_pack_fournit_le_defaut_des_styles():
    t = ty.Typographie.depuis_pack(_Pack(styles_word={"dialogue": "Quote"}))

    assert t.styles_word["dialogue"] == "Quote"
    assert t.styles_word["pensee"] == "Pensée"      # non déclaré : le défaut tient


def test_la_config_prime_sur_le_pack():
    """⚠ `rendu.styles` est calé sur le `reference.docx` de l'utilisateur. Un pack n'a pas à
    le lui reprendre — sinon installer un pack casserait son rendu Word."""
    t = ty.Typographie.depuis_pack(_Pack(styles_word={"dialogue": "Quote"}),
                                   {"styles": {"dialogue": "Mon Style À Moi"}})

    assert t.styles_word["dialogue"] == "Mon Style À Moi"


def test_le_tiret_dans_le_texte_suit_la_config():
    assert ty.Typographie.depuis_pack(None, {"dialogue_dash_in_text": True}).tiret_dans_le_texte
    assert not ty.Typographie.depuis_pack(None, {"dialogue_dash_in_text": False}).tiret_dans_le_texte


def test_le_tiret_dans_le_texte_retombe_sur_le_pack():
    """Sans réglage explicite dans `config.yaml`, c'est la convention de la langue qui parle."""
    t = ty.Typographie.depuis_pack(_Pack({"tiret_dans_le_texte": True}), {})

    assert t.tiret_dans_le_texte is True


# ─────────────────────────────────────────────────────────────────────────────
# Le pack `fr` livré est cohérent avec les défauts du code
# ─────────────────────────────────────────────────────────────────────────────

def test_le_pack_fr_livre_reproduit_exactement_les_defauts():
    """Le garde-fou qui fait tenir toute la refonte : `langues/fr/pack.yaml` doit produire
    les MÊMES règles que le code d'avant. Une divergence changerait la sortie de tous les
    tomes déjà produits, sans que rien ne le signale."""
    from pathlib import Path

    import yaml

    racine = Path(__file__).resolve().parent.parent
    meta = yaml.safe_load((racine / "langues" / "fr" / "pack.yaml").read_text(encoding="utf-8"))
    pack = _Pack(meta.get("typographie"), meta.get("styles_word"), meta.get("classes_css"))
    du_pack = ty.Typographie.depuis_pack(pack)

    assert du_pack.dialogue_span.pattern == ty.DEFAUT.dialogue_span.pattern
    assert du_pack.guide_de_style.pattern == ty.DEFAUT.guide_de_style.pattern
    assert du_pack.tiret_dialogue == ty.DEFAUT.tiret_dialogue
    assert du_pack.tiret_dans_le_texte == ty.DEFAUT.tiret_dans_le_texte
    assert du_pack.styles_word == ty.DEFAUT.styles_word
    assert du_pack.classes_css == ty.DEFAUT.classes_css
    # Le lexique : comparé sur son COMPORTEMENT, l'écriture YAML pouvant replier les espaces.
    for phrase in ("dit-il.", "hurla-t-elle.", "murmura.", "s'écria-t-il.", "Le vent se leva."):
        assert bool(du_pack.verbes_de_parole.match(phrase)) == \
               bool(ty.DEFAUT.verbes_de_parole.match(phrase)), phrase
    for c in ".!?…;:,":
        assert bool(du_pack.fin_de_phrase.search(c)) == bool(ty.DEFAUT.fin_de_phrase.search(c))
