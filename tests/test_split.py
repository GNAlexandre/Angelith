# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de split.py : détection de chapitres (mots-clés ∪ titres structurels) et
hiérarchie Chapitre → Partie imbriquée quand deux niveaux de titre sont présents."""
import re

from pipeline.split import (
    apparier_chapitres,
    Chapter, Part, _heading_levels, _paragraphs, detect_chapters, realign_chapters,
    split_blocks, split_in_half, split_into_n, split_oversized, split_proportional,
)


def test_heading_levels_returns_all_levels_not_just_one():
    text = "# Tome 1\n\nIntro.\n\n## Chapitre 1\n\nTexte.\n\n## Chapitre 2\n\nTexte."
    levels = _heading_levels(text.splitlines())
    assert set(levels) == {1, 2}
    assert len(levels[1]) == 1
    assert len(levels[2]) == 2


def test_detect_chapters_keyword_only_stays_flat_no_parts():
    """Aucun titre structurel : comportement historique — chapitres plats, parts=[]."""
    text = "Chapitre 1\n\nTexte un.\n\nChapitre 2\n\nTexte deux."
    chapters = detect_chapters(text)
    assert len(chapters) == 2
    assert all(isinstance(c, Chapter) for c in chapters)
    assert all(c.parts == [] for c in chapters)


def test_detect_chapters_single_heading_level_stays_flat_no_parts():
    """Un seul niveau de titre qualifiant (≥2 occurrences) : comportement historique
    inchangé — c'est le cas de la majorité des projets existants (roman E, roman B)."""
    text = "## Chapitre 1\n\nTexte un.\n\n## Chapitre 2\n\nTexte deux."
    chapters = detect_chapters(text)
    assert [c.title for c in chapters] == ["Chapitre 1", "Chapitre 2"]
    assert all(c.parts == [] for c in chapters)


def test_detect_chapters_two_levels_nest_parts_inside_chapters():
    """Motif réel (roman C Vol.1) : un niveau large (`#`, peu fréquent) et un niveau fin
    (`##`, fréquent) — le niveau fin devient des Parties IMBRIQUÉES dans le chapitre,
    jamais l'inverse."""
    text = (
        "# Year 1938, Summer 1\n\n"
        "## April 1st, Evening\n\nTexte du 1er avril soir.\n\n"
        "## April 1st, Night\n\nTexte du 1er avril nuit.\n\n"
        "# Year 1938, Summer 2\n\n"
        "## April 17th, Evening\n\nTexte.\n\n"
        "## April 17th, Night\n\nTexte."
    )
    chapters = detect_chapters(text)
    assert [c.title for c in chapters] == ["Year 1938, Summer 1", "Year 1938, Summer 2"]
    assert [p.title for p in chapters[0].parts] == ["April 1st, Evening", "April 1st, Night"]
    assert [p.title for p in chapters[1].parts] == ["April 17th, Evening", "April 17th, Night"]
    assert "Texte du 1er avril soir." in chapters[0].parts[0].body
    # Le corps du CHAPITRE lui-même n'est pas amputé : il contient toujours les ## bruts.
    assert "## April 1st, Evening" in chapters[0].body


def test_detect_chapters_keyword_on_part_line_promotes_to_chapter():
    """Un mot-clé (ex. Epilogue) tapé au niveau Partie doit être PROMU en frontière de
    chapitre, pas laissé comme simple sous-partie."""
    text = (
        "# Partie 1\n\n"
        "## Section A\n\nTexte A.\n\n"
        "## Epilogue\n\nTexte épilogue.\n\n"
        "# Partie 2\n\n"
        "## Section B\n\nTexte B.\n\n"
        "## Section C\n\nTexte C."
    )
    chapters = detect_chapters(text)
    titles = [c.title for c in chapters]
    assert "Epilogue" in titles
    epilogue = next(c for c in chapters if c.title == "Epilogue")
    assert epilogue.parts == []
    partie1 = next(c for c in chapters if c.title == "Partie 1")
    assert [p.title for p in partie1.parts] == ["Section A"]


def test_detect_chapters_third_level_stays_literal_in_part_body():
    """3 niveaux qualifiants : seuls les 2 premiers pilotent le découpage (limite
    volontaire) — le 3e reste du texte littéral, non interprété, dans la Partie."""
    text = (
        "# Chapitre 1\n\n"
        "## Partie A\n\n"
        "### Sous-section\n\nTexte fin.\n\n"
        "### Autre sous-section\n\nTexte fin 2.\n\n"
        "## Partie B\n\nTexte B.\n\n"
        "# Chapitre 2\n\n"
        "## Partie C\n\nTexte C.\n\n"
        "## Partie D\n\nTexte D."
    )
    chapters = detect_chapters(text)
    assert [c.title for c in chapters] == ["Chapitre 1", "Chapitre 2"]
    partie_a = chapters[0].parts[0]
    assert partie_a.title == "Partie A"
    assert "### Sous-section" in partie_a.body
    assert "### Autre sous-section" in partie_a.body


def test_paragraphs_keeps_heading_line_atomic():
    """Une ligne de titre ATX ne doit jamais fusionner avec la prose voisine, même
    sans ligne vide autour (garantie nécessaire pour survivre au passage LLM)."""
    text = "Phrase avant.\n## Titre de partie\nPhrase après."
    paras = _paragraphs(text)
    assert paras == ["Phrase avant.", "## Titre de partie", "Phrase après."]


def test_part_dataclass_shape():
    p = Part(title="X", body="Y")
    assert p.title == "X" and p.body == "Y"


def test_custom_keyword_pattern_does_not_match_mid_sentence():
    """Régression réelle (roman C Vol.1) : un motif utilisateur simple (« POV »,
    « Chapter ») compilé SANS ancrage matchait n'importe où en pleine phrase
    (« stopover » contient « POV », « chapters » contient « Chapter »), créant des
    frontières de chapitre fantômes en pleine narration."""
    text = (
        "Prologue\n\nTexte du prologue ici pour de bon.\n\n"
        "That town was a stopover for supplies along the road, nothing more.\n\n"
        "And you can read the latest chapters of this series on our website too.\n\n"
        "Chapter One\n\nTexte du premier vrai chapitre commence ici pour de bon."
    )
    chapters = detect_chapters(text, patterns=["Prologue", "POV", "Chapter"])
    assert [c.title for c in chapters] == ["Prologue", "Chapter One"]


def test_custom_keyword_pattern_still_matches_at_line_start():
    text = "POV Alice\n\nTexte du point de vue d'Alice ici pour de bon.\n\nPOV Bob\n\nTexte de Bob ici pour de bon."
    chapters = detect_chapters(text, patterns=["POV"])
    assert [c.title for c in chapters] == ["POV Alice", "POV Bob"]


def test_custom_keyword_pattern_ending_in_punctuation():
    """Régression réelle (roman F Vol.1) : un motif finissant par une ponctuation
    (« NPC No. ») était compilé avec un `\\b` final qui ne matche JAMAIS devant l'espace de
    « NPC No. 1 » (pas de frontière mot↔non-mot entre « . » et « espace ») — tous les
    chapitres « NPC No. N » étaient manqués et le texte du premier était perdu. Le motif
    doit désormais découper correctement (re.escape + `(?!\\w)`)."""
    text = (
        "NPC No. 1: le refus\n\nCorps du premier chapitre ici pour de bon.\n\n"
        "NPC No. 2: la suite\n\nCorps du deuxième chapitre ici pour de bon."
    )
    chapters = detect_chapters(text, patterns=["NPC No."])
    assert [c.title for c in chapters] == ["NPC No. 1: le refus", "NPC No. 2: la suite"]


# --------------------------------------------------------------------------- #
# split_blocks : tolérance de 20 % pour garder une Partie entière dans un bloc
# --------------------------------------------------------------------------- #

def test_split_blocks_without_parts_flag_ignores_stray_heading_line():
    """has_parts=False (chapter.parts == [], le cas par défaut) : split_blocks doit
    rester identique à l'algorithme historique même si le texte contient, par
    coïncidence, une ligne ATX isolée (titre non qualifiant à occurrence unique) —
    garantie de non-régression pour l'immense majorité des projets existants."""
    text = "Un mot.\n\n# Note\n\nDeux mots ici."
    assert split_blocks(text, 20) == ["Un mot.\n\n# Note", "Deux mots ici."]
    assert split_blocks(text, 20, has_parts=False) == ["Un mot.\n\n# Note", "Deux mots ici."]


def test_split_blocks_part_fits_normally_no_tolerance_needed():
    text = "## Partie A\n\nTexte court."
    blocks = split_blocks(text, 200, has_parts=True)
    assert len(blocks) == 1
    assert "## Partie A" in blocks[0] and "Texte court." in blocks[0]


def test_split_blocks_part_uses_tolerance_to_avoid_being_split():
    """Une Partie légèrement trop grosse pour max_chars mais sous la marge de 20 %
    reste ENTIÈRE dans un seul bloc, quitte à dépasser max_chars."""
    max_chars = 50
    body = "x" * 45  # partie = 11 ("## Partie A") + 2 + 45 = 58 : >50 mais <=60 (marge 20%)
    blocks = split_blocks(f"## Partie A\n\n{body}", max_chars, has_parts=True)
    assert len(blocks) == 1
    assert "## Partie A" in blocks[0] and body in blocks[0]


def test_split_blocks_part_too_big_even_with_tolerance_falls_back():
    """Une Partie trop grosse MÊME avec la marge retombe sur le découpage
    paragraphe par paragraphe historique — elle peut alors être scindée, sans
    perturber le packing du contenu environnant."""
    max_chars = 50
    body1, body2 = "x" * 40, "y" * 40    # partie >> 60 (marge) : pas de miracle possible
    blocks = split_blocks(f"## Partie A\n\n{body1}\n\n{body2}", max_chars, has_parts=True)
    assert len(blocks) >= 2
    assert any("## Partie A" in b for b in blocks)
    assert any(body1 in b for b in blocks) and any(body2 in b for b in blocks)


def test_split_blocks_several_small_parts_pack_into_one_block():
    """Plusieurs petites Parties consécutives qui rentrent ENSEMBLE dans max_chars
    sont packées dans le MÊME bloc — le packing habituel s'applique aussi au
    niveau Partie, pas seulement au niveau paragraphe."""
    text = "## Partie A\n\nTexte A.\n\n## Partie B\n\nTexte B.\n\n## Partie C\n\nTexte C."
    blocks = split_blocks(text, 200, has_parts=True)
    assert len(blocks) == 1
    assert all(f"## Partie {L}" in blocks[0] for L in "ABC")


# --------------------------------------------------------------------------- #
# split_oversized : couper un paragraphe PLUS GROS que max_chars.
# Régression réelle (roman B Vol.2, ch15) : un chapitre dont l'extraction n'a
# produit aucune ligne vide devenait UN SEUL paragraphe → UN SEUL bloc de ~8 000
# caractères, très au-dessus de max_block_chars=6000. Le plafond `_out_cap`
# saturait, le budget de raisonnement partait entièrement dans le <think>, et le
# modèle dérivait sur les sources de référence en dupliquant tout l'épilogue.
# --------------------------------------------------------------------------- #

def test_split_oversized_is_transparent_below_the_limit():
    """Garantie de non-régression : sous la limite, le paragraphe ressort INTACT."""
    p = "Une phrase. Une autre phrase."
    assert split_oversized(p, 100) == [p]


def test_split_oversized_cuts_a_giant_paragraph_under_the_limit():
    p = " ".join(f"Phrase numéro {i} de ce paragraphe interminable." for i in range(400))
    parts = split_oversized(p, 600)
    assert len(parts) > 1
    assert all(len(q) <= 600 for q in parts)
    # aucun mot perdu ni dupliqué
    assert " ".join(parts).split() == p.split()


def test_split_oversized_cuts_at_sentence_boundaries():
    p = "Alpha bravo charlie. Delta echo foxtrot. Golf hotel india. Juliett kilo lima."
    parts = split_oversized(p, 40)
    assert len(parts) > 1
    assert all(q.endswith(".") for q in parts)


def test_split_oversized_prefers_newlines_over_mid_sentence():
    """Un paragraphe qui contient des sauts de ligne (extraction sans ligne vide)
    doit être coupé SUR ces sauts, jamais en plein milieu d'une ligne."""
    p = "\n".join(f"Ligne de narration numéro {i} du chapitre." for i in range(40))
    parts = split_oversized(p, 300)
    assert len(parts) > 1
    assert all("\n".join(q.splitlines()) == q for q in parts)
    assert "\n".join(parts).splitlines() == p.splitlines()


def test_split_oversized_never_cuts_an_image_marker_or_heading():
    img = "<!-- IMG: media/" + "a" * 200 + ".png -->"
    assert split_oversized(img, 20) == [img]
    heading = "## " + "Titre très long " * 20
    assert split_oversized(heading, 20) == [heading]


def test_split_oversized_gives_up_on_unbreakable_text():
    """Aucun espace ni ponctuation : on renvoie tel quel plutôt que de couper un mot."""
    p = "x" * 5000
    assert split_oversized(p, 100) == [p]


def test_split_blocks_now_splits_a_giant_paragraph():
    """Le bug ch15 : un seul paragraphe géant donnait UN bloc bien au-delà de la limite."""
    giant = " ".join(f"Phrase numéro {i} sans aucune ligne vide autour." for i in range(300))
    blocks = split_blocks(giant, 1000)
    assert len(blocks) > 1
    assert all(len(b) <= 1000 for b in blocks)


def test_split_blocks_unchanged_on_sanely_paragraphed_text():
    """Non-régression forte : sur un texte normalement paragraphé (aucun paragraphe au-delà
    de max_chars), le découpage est IDENTIQUE à l'algorithme historique."""
    paras = [f"Paragraphe numéro {i} de longueur raisonnable." for i in range(20)]
    text = "\n\n".join(paras)
    blocks = split_blocks(text, 120)
    # reconstruction exacte, dans l'ordre, sans perte
    assert "\n\n".join(blocks) == text
    assert len(blocks) > 1


# --------------------------------------------------------------------------- #
# split_in_half : utilisé par le redécoupage-relance de l'orchestrateur
# --------------------------------------------------------------------------- #

def test_split_in_half_cuts_at_paragraph_boundary_near_the_middle():
    paras = [f"Paragraphe {i} avec un peu de texte dedans." for i in range(6)]
    left, right = split_in_half("\n\n".join(paras))
    assert left.count("Paragraphe") == 3 and right.count("Paragraphe") == 3
    assert left + "\n\n" + right == "\n\n".join(paras)


def test_split_in_half_handles_a_single_paragraph():
    """Le cas ch15 : un seul paragraphe — il faut savoir couper DEDANS, sinon le
    redécoupage-relance n'aurait aucun effet (split_into_n renvoyait ['', tout])."""
    p = " ".join(f"Phrase numéro {i} de ce bloc unique." for i in range(30))
    halves = split_in_half(p)
    assert len(halves) == 2
    assert all(h.strip() for h in halves)
    assert " ".join(halves).split() == p.split()


def test_split_into_n_cannot_halve_a_single_paragraph():
    """Documente POURQUOI split_in_half existe : split_into_n répartit par nombre de
    paragraphes, donc sur un paragraphe unique il produit un morceau vide."""
    p = "Une seule ligne de texte sans aucune coupure de paragraphe."
    assert "" in split_into_n(p, 2)


def test_split_in_half_gives_up_on_unbreakable_text():
    assert split_in_half("x" * 100) == ["x" * 100]


def test_split_in_half_keeps_image_markers_whole():
    text = "Avant l'image.\n\n<!-- IMG: media/a.png -->\n\nAprès l'image."
    halves = split_in_half(text)
    assert len(halves) == 2
    assert sum(h.count("<!-- IMG: media/a.png -->") for h in halves) == 1


# --------------------------------------------------------------------------- #
# split_proportional : aligner une source de référence sur les TAILLES des blocs
# du pivot, et non sur leur nombre de paragraphes.
# Régression réelle (roman B Vol.2) : le pivot est découpé en caractères et les
# références par nombre de paragraphes — la « source alignée sur le bloc i »
# couvrait une autre tranche du chapitre, et le traducteur retraduisait ce
# hors-bloc (prologue et épilogue en double).
# --------------------------------------------------------------------------- #

def test_split_proportional_returns_exactly_one_piece_per_weight():
    text = "\n\n".join(f"Paragraphe {i}." for i in range(9))
    assert len(split_proportional(text, [10, 20, 30])) == 3


def test_split_proportional_follows_the_weights_not_the_paragraph_count():
    """Trois blocs de tailles 1/1/8 : la référence doit suivre CES proportions.
    `split_into_n` aurait donné trois tiers égaux — c'est tout le bug."""
    paras = [f"Paragraphe {i} de taille identique aux autres." for i in range(20)]
    text = "\n\n".join(paras)
    pieces = split_proportional(text, [1, 1, 8])
    counts = [p.count("Paragraphe") for p in pieces]
    assert sum(counts) == 20
    assert counts[2] > counts[0] + counts[1]      # le gros bloc reçoit l'essentiel
    egaux = [p.count("Paragraphe") for p in split_into_n(text, 3)]
    assert counts != egaux                        # et ce n'est PAS le découpage par tiers


def test_split_proportional_preserves_all_paragraphs_in_order():
    paras = [f"P{i}" for i in range(11)]
    pieces = split_proportional("\n\n".join(paras), [3, 5, 2, 7])
    assert "\n\n".join(p for p in pieces if p) == "\n\n".join(paras)


def test_split_proportional_handles_degenerate_inputs():
    assert split_proportional("Texte.", [5]) == ["Texte."]
    assert split_proportional("", [1, 2]) == ["", ""]
    # poids tous nuls → repli sur le découpage par nombre de paragraphes
    assert len(split_proportional("A\n\nB\n\nC\n\nD", [0, 0])) == 2


# --------------------------------------------------------------------------- #
# realign_chapters : un MÊME nombre de chapitres ne garantit pas un alignement
# 1:1. Cas réel (roman B Vol.2, 16 chapitres des deux côtés) : le chapitre 15
# japonais contenait EN PLUS tout l'épilogue, le chapitre 16 n'en gardait que la
# fin — le traducteur a donc traduit l'épilogue une seconde fois en fin de ch15.
# --------------------------------------------------------------------------- #

def _chap(n_paras: int, tag: str = "P") -> str:
    return "\n\n".join(f"{tag}{i} " + "x" * 90 for i in range(n_paras))


def test_realign_leaves_a_correctly_aligned_volume_untouched():
    """Exigence de non-régression la plus importante : les volumes bien alignés
    (l'immense majorité) ne doivent PAS être touchés."""
    pivot = [10000, 20000, 15000, 12000]
    refs = [_chap(45), _chap(90), _chap(68), _chap(54)]     # ~ mêmes proportions
    out, repares = realign_chapters(refs, pivot)
    assert repares == []
    assert out == refs


def test_realign_moves_the_overflow_back_to_the_next_chapter():
    """Reproduction du bug ch15/ch16 : la frontière de la référence est trop tardive,
    le chapitre 15 déborde sur l'épilogue et le 16 est amputé d'autant."""
    pivot = [10000, 10000, 4000, 10000]      # ch3 court, ch4 (épilogue) long
    ok = [_chap(50), _chap(50)]
    # frontière mal placée : ch3 reçoit 85 paragraphes, ch4 seulement 15
    refs = ok + [_chap(85, "E"), _chap(15, "F")]
    out, repares = realign_chapters(refs, pivot)
    assert repares == [(2, 3)]
    assert len(out[2]) < len(refs[2])        # le débordement a quitté le ch3
    assert len(out[3]) > len(refs[3])        # et a rejoint le ch4
    assert out[0] == refs[0] and out[1] == refs[1]     # chapitres sains intacts
    # aucun paragraphe perdu sur l'intervalle recalé
    assert sorted((out[2] + "\n\n" + out[3]).split("\n\n")) == \
           sorted((refs[2] + "\n\n" + refs[3]).split("\n\n"))


def test_realign_respects_the_pivot_proportions_after_repair():
    pivot = [4000, 10000]
    refs = [_chap(80, "E"), _chap(20, "F")]
    out, _ = realign_chapters(refs, pivot)
    part = len(out[0]) / (len(out[0]) + len(out[1]))
    assert abs(part - 4000 / 14000) < 0.12   # nettement plus proche de la cible qu'avant
    assert part < 0.5


def test_realign_ignores_an_isolated_anomaly_with_no_neighbour_to_swap_with():
    """Un seul chapitre hors proportion dont AUCUN voisin ne porte l'erreur inverse :
    ce n'est pas une frontière déplacée (la source a du contenu en plus ou en moins) —
    on ne touche à rien plutôt que de charcuter du texte."""
    pivot = [10000, 10000, 10000]
    refs = [_chap(50), _chap(50), _chap(50)]
    refs[1] = _chap(4)                        # ch2 quasi vide, voisins conformes
    out, repares = realign_chapters(refs, pivot)
    assert repares == [] or all(len(r) >= 2 for r in repares)
    if not repares:
        assert out == refs


def test_realign_handles_degenerate_inputs():
    assert realign_chapters([], []) == ([], [])
    assert realign_chapters(["a"], [1]) == (["a"], [])          # un seul chapitre
    assert realign_chapters(["a", "b"], [1, 2, 3]) == (["a", "b"], [])   # tailles discordantes
    assert realign_chapters(["", ""], [0, 0]) == (["", ""], [])          # tout vide


def test_realign_is_scale_independent_between_languages():
    """Une VO japonaise fait ~0.4x l'anglais en caractères : le contrôle porte sur les
    PROPORTIONS, jamais sur les tailles absolues, sinon tout serait signalé."""
    pivot = [10000, 20000, 30000]
    refs = [_chap(20), _chap(40), _chap(60)]      # 2x plus court partout, mêmes ratios
    assert realign_chapters(refs, pivot)[1] == []


def test_split_proportional_scale_independent_across_languages():
    """Les poids sont interprétés en FRACTIONS : une référence japonaise (bien plus
    courte en caractères qu'un pivot anglais) se découpe aux mêmes proportions."""
    jp = "\n\n".join(f"日本語の段落{i}。" for i in range(10))
    a = split_proportional(jp, [3000, 1000])
    b = split_proportional(jp, [30, 10])
    assert a == b


# --------------------------------------------------------------------------- #
# Découpe proportionnée à la densité de la langue (max_block_tokens)
# --------------------------------------------------------------------------- #

_JP_PARA = ("彼は塔の階層を見上げ、七堕の気配を探った。夜の帳が下りるまでに封印を終えねばならない。"
            "祭花は短い息を吐き、腰の刀に手をかけた。石畳の冷たさが足裏から這い上がってくる。")
_FR_PARA = ("Il leva les yeux vers les étages de la tour et chercha la présence des Nanae, "
            "car le scellement devait être achevé avant que la nuit ne tombe tout à fait.")


def test_limite_caracteres_sans_budget_rend_le_plafond():
    """`max_tokens=None` → comportement historique, aucun calcul de densité."""
    from pipeline.split import limite_caracteres
    assert limite_caracteres(_JP_PARA * 10, 6000, None) == 6000
    assert limite_caracteres("", 6000, 2200) == 6000


def test_limite_caracteres_ne_peut_que_retrecir():
    """`max_block_chars` garde sa sémantique de PLAFOND DUR : un texte peu dense dérive
    une limite plus grande, qui ne doit jamais l'emporter."""
    from pipeline.split import limite_caracteres
    latin = _FR_PARA * 40                       # densité ~0,25 → 2200/0,25 = 8800 > 6000
    assert limite_caracteres(latin, 6000, 2200) == 6000
    jp = _JP_PARA * 40                          # densité ~1,0 → ~2200 < 6000
    assert limite_caracteres(jp, 6000, 2200) < 2500


def test_split_blocks_max_tokens_ne_change_rien_en_latin():
    """LA garantie de non-régression : sur un pivot latin, la découpe est identique
    bloc pour bloc, pas seulement en nombre de blocs."""
    texte = "\n\n".join(f"{_FR_PARA} Paragraphe {i}." for i in range(40))
    sans = split_blocks(texte, 6000)
    assert split_blocks(texte, 6000, max_tokens=2200) == sans
    assert split_blocks(texte, 6000, max_tokens=None) == sans


def test_split_blocks_max_tokens_resserre_un_pivot_japonais():
    # Assez long pour que le rapport entre les deux découpages soit significatif : le
    # japonais est ~4× plus dense que le latin, on attend donc au moins un facteur 2.
    texte = "\n\n".join(f"{_JP_PARA}" for _ in range(200))
    from core import tokens
    sans = split_blocks(texte, 6000)
    avec = split_blocks(texte, 6000, max_tokens=2200)
    assert len(avec) >= len(sans) * 2
    # Chaque bloc tient le budget (marge de 5 % : on ne coupe jamais un paragraphe en deux).
    assert all(tokens.estimate(b) <= 2200 * 1.05 for b in avec)
    assert "\n\n".join(avec).replace("\n", "") == texte.replace("\n", "")   # rien de perdu


def test_split_oversized_respecte_la_limite_derivee():
    """Un paragraphe japonais géant d'un seul tenant : c'est `split_oversized` qui doit
    voir la limite dérivée, pas le `max_chars` brut."""
    from core import tokens
    geant = "。".join(f"{_JP_PARA}" for _ in range(30))     # un SEUL paragraphe
    blocs = split_blocks(geant, 6000, max_tokens=2200)
    assert len(blocs) > 1
    assert all(tokens.estimate(b) <= 2200 * 1.15 for b in blocs)


# --------------------------------------------------------------------------- #
# Les motifs de config COMPLÈTENT les défauts, ils ne les remplacent pas
# --------------------------------------------------------------------------- #

def test_les_motifs_utilisateur_completent_les_defauts():
    """Une liste `chapter_patterns` 100 % latine faisait perdre le motif CJK `第N章` — or
    `config.yaml` en fournit une. Un utilisateur qui ajoute « POV » ne demande pas à cesser
    de détecter « Prologue »."""
    text = ("POV Alice\n\nLe point de vue d'Alice, raconté ici pour de bon.\n\n"
            "第一章\n\nLe corps du premier chapitre japonais, ici pour de bon.\n\n"
            "Prologue\n\nLe corps du prologue, écrit ici pour de bon.")
    titres = [c.title for c in detect_chapters(text, patterns=["POV"])]
    assert titres == ["POV Alice", "第一章", "Prologue"]


def test_les_defauts_seuls_restent_actifs_sans_motif_utilisateur():
    """Non-régression : `patterns=None` se comporte exactement comme avant."""
    text = "第一章\n\nDu texte japonais ici pour de bon.\n\n第二章\n\nEncore du texte ici."
    assert len(detect_chapters(text)) == 2
    assert len(detect_chapters(text, patterns=[])) == 2
    assert len(detect_chapters(text, patterns=None)) == 2


def test_un_motif_utilisateur_ne_peut_pas_desactiver_un_defaut():
    """L'union ne peut qu'AJOUTER des frontières : c'est ce qui rend le changement sûr, et
    ce qui a été vérifié sur les 13 tomes du dépôt (aucun découpage modifié)."""
    text = "Prologue\n\nLe corps du prologue, écrit ici pour de bon."
    assert [c.title for c in detect_chapters(text, patterns=["Truc"])] == ["Prologue"]


# --------------------------------------------------------------------------- #
# apparier_chapitres : aligner des cardinalités DIFFÉRENTES
# --------------------------------------------------------------------------- #
#
# Une source de référence détecte rarement le même découpage que le pivot. Un EPUB fait des
# « chapitres » de sa couverture, de son sommaire et de son colophon, et porte parfois une
# postface que le pivot n'a pas traduite. Mesuré sur roman B Vol.3 : 9 unités japonaises
# pour 5 chapitres pivot, alors que les cinq qui se correspondent ont des proportions
# quasi identiques.
#
# L'orchestrateur retombait alors sur `split_into_n`, qui répartit par NOMBRE de paragraphes
# égal : le prologue recevait 25 896 caractères au lieu de 3 600 — les trois premières
# sections du chapitre 1 — et pas un seul des 5 chapitres n'était aligné.

# Tailles réelles du Vol.3 : sommaire, prologue, ch.1, ch.2, ch.3, épilogue, postface,
# page d'illustrations, colophon.
REF_VOL3 = [199, 3612, 37089, 41269, 27083, 2737, 2127, 34, 303]
PIVOT_VOL3 = [10298, 91147, 104342, 69289, 6947]


def _corps(tailles, mot="mot"):
    """Des corps de la taille voulue, faits de VRAIS paragraphes — sans quoi
    `split_into_n` n'aurait rien à découper et la comparaison serait truquée."""
    out = []
    for t in tailles:
        para = (mot + " ") * 12                      # ~48 caractères
        n = max(1, t // len(para))
        texte = "\n\n".join(para.strip() for _ in range(n))
        out.append(texte[:t] if len(texte) > t else texte)
    return out


def test_apparier_respecte_les_proportions_du_pivot():
    """**Le test central.** Les deux grosses unités doivent tomber EXACTEMENT sur les
    chapitres qui leur correspondent — c'est la garantie que le traducteur reçoit le bon
    passage en regard du sien."""
    groupes = apparier_chapitres(_corps(REF_VOL3), PIVOT_VOL3).groupes

    assert len(groupes[1]) == REF_VOL3[2]        # chapitre 1 ← unité 3, exactement
    assert len(groupes[2]) == REF_VOL3[3]        # chapitre 2 ← unité 4, exactement


def test_apparier_bat_split_into_n_sur_des_chapitres_inegaux():
    """La comparaison qui justifie le remplacement. On mesure l'écart de PART DE VOLUME
    entre chaque chapitre du pivot et le morceau de référence qu'il reçoit."""
    corps = _corps(REF_VOL3)
    total_p = sum(PIVOT_VOL3)

    def ecart(morceaux):
        total = sum(len(m) for m in morceaux) or 1
        return sum(abs(len(m) / total - p / total_p) for m, p in zip(morceaux, PIVOT_VOL3))

    apparie = apparier_chapitres(corps, PIVOT_VOL3).groupes
    ancien = split_into_n("\n\n".join(corps), len(PIVOT_VOL3))
    assert ecart(apparie) < ecart(ancien) / 3


def test_apparier_rend_un_groupe_par_chapitre_du_pivot():
    groupes = apparier_chapitres(_corps(REF_VOL3), PIVOT_VOL3).groupes
    assert len(groupes) == len(PIVOT_VOL3)


def test_apparier_conserve_l_ordre_et_ne_perd_rien():
    """Aucun texte ne remonte ni ne descend dans le volume : une référence qui se
    réordonnerait collerait un chapitre sur un autre, en silence."""
    corps = [f"unite-{i} " + "x" * 400 for i in range(9)]
    groupes = apparier_chapitres(corps, PIVOT_VOL3).groupes

    joint = "\n\n".join(groupes)
    vus = [int(m) for m in re.findall(r"unite-(\d)", joint)]
    assert vus == sorted(vus) == list(range(9))


def test_une_unite_de_bruit_ne_s_arroge_pas_un_chapitre():
    """Un sommaire de 200 caractères en tête ne doit pas attirer une frontière : il se
    rattache à sa voisine. Sans ce traitement, le pivot perdrait un chapitre entier au
    profit d'une page qui ne porte aucun texte."""
    ref = _corps([200, 30000, 30000, 30000])
    groupes = apparier_chapitres(ref, [30000, 30000, 30000]).groupes

    assert len(groupes[0]) > 25000, "le bruit a été pris pour un chapitre"


def test_apparier_avec_autant_d_unites_que_de_chapitres_est_l_identite():
    """Le cas trivial doit rester trivial : c'est `realign_chapters` qui traite les
    cardinalités égales, mais cette fonction ne doit pas les abîmer si on l'y applique."""
    ref = _corps([3000, 30000, 30000])
    app = apparier_chapitres(ref, [3000, 30000, 30000])
    groupes, notes = app.groupes, app.notes

    assert groupes == [r.strip() for r in ref]     # chaque unité reste son propre chapitre
    assert notes == []


def test_apparier_avec_moins_d_unites_que_de_chapitres_redecoupe():
    """Une référence qui n'a pas détecté ses chapitres (un seul bloc) ne peut pas être
    groupée : on la redécoupe par volume plutôt que d'échouer."""
    app = apparier_chapitres(_corps([60000]), [30000, 20000, 10000])
    groupes, notes = app.groupes, app.notes

    assert len(groupes) == 3
    assert all(g.strip() for g in groupes)
    assert notes and "redécoupage" in notes[0]


def test_apparier_sans_reference_rend_des_groupes_vides():
    groupes = apparier_chapitres([], [100, 200]).groupes
    assert groupes == ["", ""]


# --------------------------------------------------------------------------- #
# Écarter le hors-corps : ce qui n'a pas d'équivalent dans le pivot
# --------------------------------------------------------------------------- #
#
# Une référence porte du texte que le pivot n'a pas : sommaire, colophon, page de crédits,
# et surtout la POSTFACE de l'auteur, que les éditions traduites reprennent rarement. Tant
# que l'appariement devait tout consommer, ces unités poussaient le reste d'un cran.
#
# Cas réel, roman B Vol.3, confronté à la concordance fournie par le traducteur : le
# chapitre 3 absorbait l'épilogue, et l'Épilogue recevait la POSTFACE — un texte sans aucun
# rapport avec lui. Ce n'était plus un décalage de volume, c'était le mauvais texte.

def test_le_hors_corps_de_queue_est_ecarte():
    """**Le test central.** Postface + colophon en fin de volume : le dernier chapitre du
    pivot doit recevoir l'ÉPILOGUE, et non la postface."""
    #        sommaire prologue  ch.1   ch.2   ch.3  épilogue postface illustr colophon
    ref = _corps([199, 3612, 37089, 41269, 27083, 2737, 2127, 34, 303])
    app = apparier_chapitres(ref, PIVOT_VOL3)

    assert app.indices == [[1], [2], [3], [4], [5]]
    assert app.ecartees == [0, 6, 7, 8]


def test_le_bruit_de_tete_est_ecarte():
    """Un sommaire de 200 caractères ne doit pas se coller au prologue : il n'a pas
    d'équivalent, et le laisser fausse la première frontière."""
    ref = _corps([199, 3612, 37089, 41269, 27083, 2737])
    app = apparier_chapitres(ref, PIVOT_VOL3)

    assert 0 in app.ecartees
    assert app.indices[0] == [1]


def test_rien_n_est_abandonne_au_milieu():
    """⚠ **La garantie qui rend l'abandon acceptable.** Une unité centrale, même inutile aux
    proportions, reste dans un groupe : sinon rien n'empêcherait de jeter un vrai chapitre en
    silence pour la seule raison qu'il arrangerait les comptes."""
    ref = _corps([30000, 200, 30000, 30000])
    app = apparier_chapitres(ref, [30000, 30000, 30000])

    assert app.ecartees == []
    assert sorted(k for idx in app.indices for k in idx) == [0, 1, 2, 3]


def test_l_abandon_reste_sous_le_plafond():
    """Une référence dont les extrémités pèseraient 30 % du volume n'est pas amputée : mieux
    vaut un appariement imparfait qu'un tiers du texte jeté sans retour."""
    ref = _corps([20000, 30000, 30000, 20000])
    app = apparier_chapitres(ref, [30000, 30000, 30000])

    perdu = sum(len(ref[k]) for k in app.ecartees)
    assert perdu <= 0.10 * sum(len(r) for r in ref)


def test_les_unites_ecartees_sont_nommees():
    """L'abandon doit être VISIBLE : les notes partent dans RAPPORT.md, et c'est la
    contrepartie de l'autorisation de jeter du texte."""
    ref = _corps([199, 3612, 37089, 41269, 27083, 2737, 2127, 34, 303])
    app = apparier_chapitres(ref, PIVOT_VOL3)

    assert app.ecartees
    assert any("écartée" in n for n in app.notes)
    assert any("%" in n for n in app.notes), "le poids abandonné doit être chiffré"


def test_sans_hors_corps_l_appariement_est_inchange():
    """Non-régression : une référence propre (rien à écarter) donne le même résultat
    qu'avant l'ajout de l'écartement."""
    ref = _corps([3612, 37089, 41269, 27083, 2737])
    app = apparier_chapitres(ref, PIVOT_VOL3)

    assert app.ecartees == []
    assert app.indices == [[0], [1], [2], [3], [4]]


def test_les_indices_couvrent_exactement_les_unites_retenues():
    """Invariant de structure : tout ce qui n'est pas écarté est apparié, une fois et
    une seule."""
    ref = _corps([199, 3612, 37089, 41269, 27083, 2737, 2127, 34, 303])
    app = apparier_chapitres(ref, PIVOT_VOL3)

    retenues = [k for idx in app.indices for k in idx]
    assert sorted(retenues + app.ecartees) == list(range(len(ref)))
    assert len(retenues) == len(set(retenues)), "une unité appariée deux fois"
