# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de glossary_build.py : parsing défensif des relevés (terminologue/glossariste)
et fusion incrémentale (dédoublonnage, résolution de genre, variantes)."""
from pipeline import glossary, glossary_build as gb


def test_parse_notes_basic_categorized():
    notes = "### PERSONNAGES\n- Feodor | genre: masculin | Officier de la 5e division\n"
    parsed = gb.parse_notes(notes)
    assert parsed["personnages"][0]["nom"] == "Feodor"
    assert parsed["personnages"][0]["genre"] == "masculin"


def test_parse_notes_slash_becomes_variante():
    """« Feodor Jessman / Féodor » → nom canonique + variante (pas deux entités)."""
    notes = "### PERSONNAGES\n- Feodor Jessman / Féodor | genre: masculin | Officier\n"
    parsed = gb.parse_notes(notes)
    assert len(parsed["personnages"]) == 1
    assert parsed["personnages"][0]["nom"] == "Feodor Jessman"
    assert "Féodor" in parsed["personnages"][0]["variantes"]


def test_parse_notes_defensive_arrow_interdit_in_name():
    """Garde-fou : « Nom → interdits: X » écrit directement dans le nom (le modèle a
    oublié le séparateur « | »)."""
    notes = "### OBJETS\n- venenum → interdits: poison | traduire: non | Substance toxique.\n"
    parsed = gb.parse_notes(notes)
    e = parsed["objets"][0]
    assert e["nom"] == "venenum"
    assert "poison" in e["interdits"]
    assert e["traduire"] is False


def test_parse_notes_defensive_no_pipe_at_all():
    """Garde-fou : « Nom — description » sans AUCUN « | » (le modèle a oublié le
    format pipe complètement)."""
    notes = "### LIEUX\n- Regule Aire — Le petit monde des survivants sur les îles flottantes.\n"
    parsed = gb.parse_notes(notes)
    e = parsed["lieux"][0]
    assert e["nom"] == "Regule Aire"
    assert "petit monde des survivants" in e["description"]


def test_parse_notes_defensive_variantes_blob_overflow():
    """Garde-fou : un blob de phrase glissé dans `variantes:` doit basculer en
    description au lieu de polluer la liste de variantes avec des fragments."""
    notes = ("### PERSONNAGES\n- Feodor | genre: masculin | variantes: Fwedo — Quatrième officier de "
             "la 5e division. Léger, connu pour ses courses silencieuses.\n")
    parsed = gb.parse_notes(notes)
    e = parsed["personnages"][0]
    assert all(len(v) <= 30 for v in e.get("variantes", []))
    assert "Quatrième officier" in e.get("description", "")


def test_parse_notes_pluriel_field():
    notes = "### CREATURES\n- Leprechaun | pluriel: Leprechauns | force: oui | race\n"
    parsed = gb.parse_notes(notes)
    assert parsed["creatures"][0]["pluriel"] == "Leprechauns"


def test_parse_notes_defensive_rename_arrow_with_tag():
    """Régression réelle (Vol.1) : « X → Y [TAG] » (renommage/reclassification suggéré
    par le modèle) ne doit PAS devenir un nom littéral fantôme — X reste canonique, Y
    devient une variante, le TAG devient un champ structuré."""
    notes = "### TERMES\n- Diablotin → diablotin [NE PAS TRADUIRE] | interdits: ogre\n"
    parsed = gb.parse_notes(notes)
    assert len(parsed["termes"]) == 1
    e = parsed["termes"][0]
    assert e["nom"] == "Diablotin"
    assert e["traduire"] is False


def test_parse_notes_defensive_trailing_tag_no_arrow():
    """Régression réelle (Vol.1) : « Nom [masculin] » sans flèche — le tag doit devenir
    le champ `genre`, pas rester collé au nom."""
    notes = "### PERSONNAGES\n- Homme-Bête [masculin] | Race dont Feodor est issu.\n"
    parsed = gb.parse_notes(notes)
    e = parsed["personnages"][0]
    assert e["nom"] == "Homme-Bête"
    assert e["genre"] == "masculin"


def test_merge_notes_rename_arrow_chain_collapses_to_one_entry():
    """Régression réelle (Vol.1) : Croyance mentionnée sous 4 formes différentes au fil
    du volume (dont 2 via le motif flèche) doit finir en UNE seule entrée."""
    g = glossary.empty()
    gb.merge_notes(g, "### TERMES\n- Croyance | Entité assimilatrice.\n")
    gb.merge_notes(g, "### TERMES\n- Croyance → La Onzième Bête | Autre nom rencontré.\n")
    gb.merge_notes(g, "### TERMES\n- La Onzième Bête [?] | Encore mentionnée ainsi.\n")
    assert len(g["termes"]) == 1
    assert "La Onzième Bête" in g["termes"][0]["variantes"]


def test_merge_notes_traduire_none_gets_filled_by_later_precise_info():
    """Régression réelle (Vol.1) : une entrée existante avec `traduire: None` (encore
    indécis, pas juste absent) doit pouvoir être complétée par une note ultérieure plus
    précise — l'ancien code ne remplissait que si la CLÉ était absente, pas si sa
    valeur était None."""
    g = glossary.empty()
    g["termes"] = [{"nom": "Diablotin", "traduire": None, "description": "sous-espèce d'ogre"}]
    gb.merge_notes(g, "### TERMES\n- Diablotin → diablotin [NE PAS TRADUIRE] | interdits: ogre\n")
    assert len(g["termes"]) == 1
    assert g["termes"][0]["traduire"] is False


def test_split_list_does_not_break_on_comma_inside_parenthesis():
    """Régression réelle (Vol.2) : « ? (orthographe erronée de X, Y dans le texte
    source) » — la virgule est À L'INTÉRIEUR de la parenthèse, ce n'est pas un vrai
    séparateur de liste."""
    r = gb._split_list("? (orthographe erronée de Nax Selzel, Armado dans le texte source)")
    assert len(r) == 1


def test_split_list_still_splits_normal_commas_outside_parens():
    assert gb._split_list("lutin, farfadet, gobelin") == ["lutin", "farfadet", "gobelin"]


def test_parse_notes_ne_pas_traduire_inside_interdits_extracted_as_field():
    """Régression réelle (Vol.2) : le modèle écrit parfois « NE PAS TRADUIRE —
    description » comme PREMIER interdit au lieu d'utiliser le champ `traduire:` —
    ça doit être extrait, pas laissé comme un faux interdit."""
    notes = ("### TERMES\n- Semifer [?] | interdits: NE PAS TRADUIRE — Race hybride issue de la "
             "lignée des fées\n")
    parsed = gb.parse_notes(notes)
    e = parsed["termes"][0]
    assert e["nom"] == "Semifer"
    assert e["traduire"] is False
    assert not e.get("interdits")
    assert "Race hybride" in e.get("description", "")


def test_parse_notes_termes_source_field():
    notes = "### CREATURES\n- Homme Bête | termes_source: Semifer | Personne mixte.\n"
    parsed = gb.parse_notes(notes)
    assert parsed["creatures"][0]["termes_source"] == ["Semifer"]


def test_merge_notes_termes_source_union_no_duplicates():
    g = glossary.empty()
    g["creatures"] = [{"nom": "Homme Bête", "termes_source": ["Semifer"]}]
    gb.merge_notes(g, "### CREATURES\n- Homme Bête | termes_source: Sémifère, Semifer\n")
    ts = g["creatures"][0]["termes_source"]
    assert sorted(ts, key=str.lower) == ["Semifer", "Sémifère"]


def test_merge_notes_dedup_via_slash_bridges_short_and_full_form():
    """« Tiat / Tiat Siba Ignareo » relie explicitement les deux formes en une note :
    ça doit fusionner avec l'entrée existante « Tiat Siba Ignareo » (matching sur la
    variante nouvellement listée), pas créer un doublon."""
    g = glossary.empty()
    g["personnages"] = [{"nom": "Tiat Siba Ignareo", "genre": "féminin"}]
    gb.merge_notes(g, "### PERSONNAGES\n- Tiat / Tiat Siba Ignareo | genre: féminin | Poursuiveuse\n")
    assert len(g["personnages"]) == 1
    assert "Tiat" in g["personnages"][0]["variantes"]


def test_merge_notes_dedup_matches_already_registered_variant():
    """Une fois qu'une forme est enregistrée comme variante, la retrouver seule (sans
    lien explicite) dans une note ultérieure doit fusionner avec l'entrée existante."""
    g = glossary.empty()
    g["personnages"] = [{"nom": "Tiat Siba Ignareo", "genre": "féminin", "variantes": ["Tiat"]}]
    gb.merge_notes(g, "### PERSONNAGES\n- Tiat | genre: féminin | Reparlée plus loin\n")
    assert len(g["personnages"]) == 1


def test_merge_notes_genre_resolution_unknown_to_defined():
    g = glossary.empty()
    g["personnages"] = [{"nom": "Portrick", "genre": "?"}]
    gb.merge_notes(g, "### PERSONNAGES\n- Portrick | genre: masculin | Soldat\n")
    assert g["personnages"][0]["genre"] == "masculin"


def test_merge_notes_conflicting_genre_flags_for_review():
    g = glossary.empty()
    g["personnages"] = [{"nom": "X", "genre": "masculin"}]
    gb.merge_notes(g, "### PERSONNAGES\n- X | genre: féminin | vu autrement\n")
    assert "⚠" in g["personnages"][0].get("description", "")
    assert g["personnages"][0]["genre"] == "masculin"  # garde le premier, ne dédouble pas


def test_merge_notes_force_flag_preserved_and_or_combined():
    g = glossary.empty()
    g["objets"] = [{"nom": "Arme Enchantée", "force": True}]
    gb.merge_notes(g, "### OBJETS\n- Arme Enchantée | interdits: arme secrète | desc\n")
    assert g["objets"][0]["force"] is True


def test_merge_notes_ignores_rien_a_signaler():
    g = glossary.empty()
    gb.merge_notes(g, "### PERSONNAGES\n- (rien à signaler)\n")
    assert glossary.total(g) == 0


# --------------------------------------------------------------------------- #
# build_index : lookup indexé (performance sur un glossaire volumineux) —
# doit produire EXACTEMENT le même résultat que le scan linéaire historique.
# --------------------------------------------------------------------------- #

def test_build_index_maps_name_and_variants_to_same_entry():
    g = glossary.empty()
    g["personnages"] = [{"nom": "Feodor", "genre": "masculin", "variantes": ["Féodor"]}]
    idx = gb.build_index(g)
    e = g["personnages"][0]
    assert idx["personnages"]["feodor"] is e
    assert idx["personnages"]["feodor"] is e  # nom
    assert idx["personnages"][gb._norm("Féodor")] is e  # variante


def test_merge_notes_with_index_matches_behavior_without_index():
    """Le résultat (ajouts/fusions, contenu final) doit être identique avec ou sans
    index — l'index ne fait qu'accélérer la recherche, jamais changer le résultat."""
    notes = "### PERSONNAGES\n- Feodor Jessman / Féodor | genre: masculin | Officier\n"
    g_no_idx = glossary.empty()
    g_no_idx["personnages"] = [{"nom": "Feodor Jessman", "variantes": ["Féodor"], "genre": "?"}]
    added_no_idx = gb.merge_notes(g_no_idx, notes)

    g_idx = glossary.empty()
    g_idx["personnages"] = [{"nom": "Feodor Jessman", "variantes": ["Féodor"], "genre": "?"}]
    idx = gb.build_index(g_idx)
    added_idx = gb.merge_notes(g_idx, notes, index=idx)

    assert added_no_idx == added_idx
    assert g_no_idx == g_idx


def test_merge_notes_with_index_stays_correct_after_add_and_merge():
    """L'index doit rester exploitable APRÈS un ajout (nouvelle entrée indexée) et
    après une fusion (nouvelles variantes indexées vers l'entrée existante) — pas
    seulement au premier appel."""
    g = glossary.empty()
    idx = gb.build_index(g)
    gb.merge_notes(g, "### PERSONNAGES\n- Portrick | genre: masculin | Soldat\n", index=idx)
    assert idx["personnages"][gb._norm("Portrick")] is g["personnages"][0]

    # Un second relevé qui référence une VARIANTE doit retrouver la même entrée via
    # l'index (pas en créer une seconde) et la nouvelle variante doit être indexée.
    gb.merge_notes(g, "### PERSONNAGES\n- Portrick / Le Soldat | Reparlé plus loin\n", index=idx)
    assert len(g["personnages"]) == 1
    assert idx["personnages"][gb._norm("Le Soldat")] is g["personnages"][0]


def test_merge_notes_index_none_falls_back_to_linear_scan():
    """Sans index (défaut), comportement HISTORIQUE inchangé — non-régression pour
    tout appelant existant (ex. consolidate_into, tests plus haut)."""
    g = glossary.empty()
    added = gb.merge_notes(g, "### PERSONNAGES\n- Portrick | genre: masculin | Soldat\n")
    assert added["ajouts"] == 1
    assert g["personnages"][0]["nom"] == "Portrick"


# --------------------------------------------------------------------------- #
# Clé de comparaison : le CJK doit survivre à la normalisation
# --------------------------------------------------------------------------- #

def test_norm_preserve_le_cjk():
    """L'ancienne classe `[^a-z0-9 ]+` réduisait toute chaîne idéographique à `""`.
    Conséquence jamais visible : `build_index` n'indexait aucune entrée japonaise,
    `_find_any` rendait toujours None, et les variantes japonaises étaient jetées."""
    from core.glossary_build import _norm
    assert _norm("八重山吹") == "八重山吹"
    assert _norm("霊峰・不尽山") == "霊峰 不尽山"        # le séparateur reste un séparateur
    assert _norm("〝積層森林〟") == "積層森林"


def test_norm_ne_desonorise_pas_les_kana():
    """LE piège : dakuten et handakuten sont des `Mn`, comme les accents latins — mais ce
    ne sont pas des accents, ils distinguent des caractères. Les retirer confondrait
    ハ / バ / パ, donc `ピカ` avec `ヒカ` : deux entités fusionneraient en silence."""
    from core.glossary_build import _norm
    assert _norm("ピカ") != _norm("ヒカ")
    assert _norm("バ") != _norm("ハ") != _norm("パ")
    assert _norm("ピカ") == "ピカ"                       # recomposé en NFC, pas か + marque


def test_norm_inchange_sur_le_latin():
    """Non-régression des œuvres à pivot latin : valeurs en dur, relevées avant le lot."""
    from core.glossary_build import _norm
    assert _norm("Feodor Jessman") == "feodor jessman"
    assert _norm("Mitsukage-san") == "mitsukage san"
    assert _norm("Féodor") == "feodor"
    assert _norm("Œdème") == "deme"


def test_deux_releves_japonais_identiques_fusionnent():
    """Avant, `_find_any` ne trouvait jamais rien sur du CJK : chaque relevé créait un
    doublon. Mesuré sur `glossaire.bak.yaml` de roman A : 3 doublons purs."""
    from core.glossary_build import merge_notes
    glo = glossary.empty()
    merge_notes(glo, "### ORGANISATIONS\n- Yaeyamabuki | termes_source: 八重山吹 | Une agence.")
    merge_notes(glo, "### ORGANISATIONS\n- Yaeyamabuki | termes_source: 八重山吹 | Une agence.")
    assert len(glo["organisations"]) == 1


def test_index_retrouve_une_entree_par_son_terme_source():
    """Sur un pivot non latin, c'est la graphie d'origine qui est l'identité STABLE : la
    romanisation, elle, varie d'un relevé à l'autre."""
    from core.glossary_build import build_index, _find_any
    glo = {"personnages": [{"nom": "Akane", "variantes": [], "termes_source": ["天茜"]}]}
    idx = build_index(glo)
    assert _find_any(glo["personnages"], ["天茜"], cat_index=idx["personnages"]) is not None
    assert _find_any(glo["personnages"], ["Akane"], cat_index=idx["personnages"]) is not None


def test_deux_romanisations_du_meme_terme_source_fusionnent():
    from core.glossary_build import merge_notes
    glo = glossary.empty()
    merge_notes(glo, "### PERSONNAGES\n- Akane | termes_source: 天茜 | Un sorcier.")
    merge_notes(glo, "### PERSONNAGES\n- Amane | termes_source: 天茜 | Un sorcier.")
    assert len(glo["personnages"]) == 1
    assert "Amane" in (glo["personnages"][0].get("variantes") or [])


# --------------------------------------------------------------------------- #
# Réparation déterministe au parsing
# --------------------------------------------------------------------------- #

def test_un_nom_en_graphie_source_est_repare_au_parsing():
    """`parse_notes` est le SEUL endroit où une entrée est créée : l'instrumenter couvre
    le terminologue, le glossariste et l'import."""
    from core.glossary_build import parse_notes
    out = parse_notes("### PERSONNAGES\n- 天茜 | genre: masculin | Un jeune sorcier.")
    e = out["personnages"][0]
    assert e["nom"] == "天茜"                     # conservé (la description a de la valeur)
    assert e["termes_source"] == ["天茜"]
    assert e["a_romaniser"] is True
    assert e["description"] == "Un jeune sorcier."


def test_une_variante_en_graphie_source_migre_au_parsing():
    from core.glossary_build import parse_notes
    out = parse_notes("### ORGANISATIONS\n- Yaeyamabuki | variantes: ヤエブキ機関, la Rose | Une agence.")
    e = out["organisations"][0]
    assert e["variantes"] == ["la Rose"]
    assert e["termes_source"] == ["ヤエブキ機関"]


def test_le_parsing_latin_est_inchange():
    from core.glossary_build import parse_notes
    out = parse_notes("### PERSONNAGES\n- Feodor Jessman | genre: masculin | "
                      "variantes: Féodor, Fwedo | termes_source: Semifer | Un officier.")
    e = out["personnages"][0]
    assert e["nom"] == "Feodor Jessman"
    assert e["variantes"] == ["Féodor", "Fwedo"]
    assert e["termes_source"] == ["Semifer"]
    assert "a_romaniser" not in e
