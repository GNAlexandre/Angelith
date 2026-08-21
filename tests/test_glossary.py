# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests du schéma glossaire : squelette complet, sauvegarde lisible, round-trips."""
import yaml

from pipeline import glossary


def test_empty_has_all_categories():
    g = glossary.empty()
    for cat in glossary.ENTITY_CATS:
        assert cat in g and g[cat] == []
    assert g["groupes"] == [] and g["anglicismes"] == []


def test_fill_defaults_exposes_all_fields_even_empty():
    g = glossary.empty()
    g["personnages"] = [{"nom": "Feodor", "genre": "masculin"}]  # entrée minimale
    filled = glossary.fill_defaults(g)
    entry = filled["personnages"][0]
    for field in glossary.FIELD_ORDER["personnages"]:
        assert field in entry, f"champ manquant : {field}"
    assert entry["variantes"] == [] and entry["description"] == "" and entry["force"] is False


def test_save_no_yaml_anchors_regression():
    """Régression : dumper les catégories séparément créait des ancres YAML (&id001)
    quand plusieurs entrées partageaient le même objet liste vide par défaut — les
    ancres d'un bloc entraient en collision avec celles d'un autre bloc une fois
    concaténées. Chaque entrée doit recevoir sa PROPRE liste, jamais partagée."""
    g = glossary.empty()
    g["personnages"] = [{"nom": "A"}, {"nom": "B"}, {"nom": "C"}]
    glossary.save(g, "/tmp/test_no_anchors.yaml")
    raw = open("/tmp/test_no_anchors.yaml", encoding="utf-8").read()
    assert "&id" not in raw and "*id" not in raw
    reloaded = yaml.safe_load(raw)
    assert len(reloaded["personnages"]) == 3
    # Les listes doivent être des objets INDÉPENDANTS (muter l'une ne doit pas affecter l'autre)
    reloaded["personnages"][0]["variantes"].append("X")
    assert reloaded["personnages"][1]["variantes"] == []


def test_save_sections_separated_by_blank_line_and_banner():
    g = glossary.empty()
    g["personnages"] = [{"nom": "A"}]
    g["lieux"] = [{"nom": "B"}]
    glossary.save(g, "/tmp/test_banners.yaml")
    raw = open("/tmp/test_banners.yaml", encoding="utf-8").read()
    assert "PERSONNAGES" in raw and "LIEUX" in raw
    assert "\n\n#" in raw  # au moins une ligne vide avant une bannière


def test_pluriel_field_roundtrip_save_load():
    g = glossary.empty()
    g["creatures"] = [{"nom": "Leprechaun", "pluriel": "Leprechauns", "force": True}]
    glossary.save(g, "/tmp/test_pluriel_glossary.yaml")
    reloaded = yaml.safe_load(open("/tmp/test_pluriel_glossary.yaml", encoding="utf-8").read())
    assert reloaded["creatures"][0]["pluriel"] == "Leprechauns"


def test_pluriel_field_roundtrip_sectioned():
    g = glossary.empty()
    g["creatures"] = [{"nom": "Leprechaun", "pluriel": "Leprechauns", "interdits": ["lutin"], "force": True}]
    sec = glossary.to_sectioned(g)
    assert "pluriel: Leprechauns" in sec


def test_to_text_caps_token_budget_with_degradation():
    g = glossary.empty()
    long_desc = "Description très longue et détaillée. " * 20
    g["personnages"] = [{"nom": f"P{i}", "description": long_desc} for i in range(100)]
    full = glossary.to_text(g)
    capped = glossary.to_text(g, max_tokens=500)
    assert glossary._approx_tokens(capped) <= 520          # léger dépassement toléré (message de troncature)
    assert glossary._approx_tokens(capped) < glossary._approx_tokens(full)
    assert "P0" in capped  # les premières entrées doivent rester visibles


def test_force_tag_shown_in_human_readable_text():
    g = glossary.empty()
    g["objets"] = [{"nom": "Arme Enchantée", "force": True}]
    assert "FORCÉ" in glossary.to_text(g)


def test_termes_source_field_roundtrips_and_visible_to_translator():
    """Le champ termes_source doit survivre save/load ET être visible dans le rendu
    humain (to_text) — c'est ce que lit l'agent traducteur."""
    g = glossary.empty()
    g["creatures"] = [{"nom": "Homme Bête", "termes_source": ["Semifer"], "force": True}]
    glossary.save(g, "/tmp/test_termes_source_glossary.yaml")
    reloaded = yaml.safe_load(open("/tmp/test_termes_source_glossary.yaml", encoding="utf-8"))
    assert reloaded["creatures"][0]["termes_source"] == ["Semifer"]
    assert "Semifer" in glossary.to_text(g)


# --------------------------------------------------------------------------- #
# Masquage des entrées sans rendu français (la boucle vicieuse)
# --------------------------------------------------------------------------- #

_GLO_MIXTE = {"personnages": [
    {"nom": "天茜", "a_romaniser": True, "termes_source": ["天茜"], "description": "Un sorcier."},
    {"nom": "Matsurika", "termes_source": ["祭花"], "description": "Une garde."},
]}


def test_le_traducteur_ne_voit_pas_les_entrees_non_romanisees():
    """LA correction qui coupe la boucle. `prompts/traducteur.md` ordonne « utilise le nom
    de cette entrée comme rendu français » : lui montrer une entrée dont le `nom` est encore
    la graphie source lui ordonne de la recopier dans le texte français."""
    txt = glossary.to_text(_GLO_MIXTE, masquer_non_romanises=True)
    assert "Matsurika" in txt
    assert "天茜" not in txt


def test_le_terminologue_les_voit_avec_leur_marque():
    """Les masquer à celui qui doit les réparer les ferait recréer en boucle."""
    txt = glossary.to_text(_GLO_MIXTE)
    assert "天茜" in txt and "À ROMANISER" in txt


def test_le_masquage_est_desactive_par_defaut():
    """Non-régression : tout appelant non modifié garde son comportement."""
    assert glossary.to_text(_GLO_MIXTE) == glossary.to_text(_GLO_MIXTE,
                                                            masquer_non_romanises=False)


def test_un_nom_cjk_sans_drapeau_est_masque_aussi():
    """Le drapeau vient de `reparer_entree` ; une entrée écrite à la main dans le YAML ne
    l'a pas, et ne doit pas passer pour autant."""
    glo = {"lieux": [{"nom": "千万丈塔", "description": "Une tour."}]}
    assert "千万丈塔" not in glossary.to_text(glo, masquer_non_romanises=True)


def test_un_glossaire_latin_est_rendu_a_lidentique():
    glo = {"personnages": [{"nom": "Feodor", "variantes": ["Féodor"], "description": "Un officier."}]}
    assert glossary.to_text(glo) == glossary.to_text(glo, masquer_non_romanises=True)
