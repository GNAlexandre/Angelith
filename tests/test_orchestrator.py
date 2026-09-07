# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests du cœur de orchestrator.py : garde-fous déterministes (emballement, perte de
mots), retry à température réduite, remplacement `force`/pluriel, et --chapitre N."""
import re
from pathlib import Path

import pytest
import yaml

from pipeline import glossary
from pipeline.orchestrator import (
    _ATX_ANY, _RESPLIT_REASONS, _aggregate_llm_stats, _close_llm_clients, _enforce_force,
    _keep_images, _match_case, _out_cap, _repair_headings, _salvage_repetition,
    _try_with_temp_retry, _wire_reporter, _word_count, process_volume,
)

# Paragraphe SUBSTANTIEL (≥60 c.) servant à fabriquer une boucle dégénérée du modèle :
# répété ≥3 fois, il déclenche le diagnostic "repetition" (cf. _has_runaway_repetition).
_LOOP_PARA = ("Le vent se leva sur la lande et emporta la dernière braise du bivouac, "
              "loin vers les collines.")


# --------------------------------------------------------------------------- #
# Helpers de base
# --------------------------------------------------------------------------- #

def test_word_count_basic():
    assert _word_count("Les uns après les autres, ils partirent.") == 7


# --- Comptage de mots sur un pivot CJK -------------------------------------------- #
#
# Bloc japonais et sa traduction, calés sur les proportions mesurées au ch03 de roman P : un
# bloc sain rend un ratio de 1,10 à 1,33, un bloc tronqué de 0,16 à 0,26.
# Six paragraphes DISTINCTS de chaque côté : un bloc fait de six fois le même paragraphe
# serait diagnostiqué « repetition » avant d'atteindre `perte_mots` (cf. l'ordre de
# `_MOTIFS_LN`), et le test ne mesurerait pas ce qu'il croit.
_JP_PARAS = [
    "彼は塔の階層を見上げ、七堕の気配を探った。夜の帳が下りるまでに封印を終えねばならない。",
    "祭花は短い息を吐き、腰の刀に手をかけた。石畳の冷たさが足裏から這い上がってくる。",
    "遠くで鐘が鳴った。堕竜講の連中が動き出した合図に違いない、と碧燈はつぶやいた。",
    "灯籠の光が水面に揺れ、鯉の影がゆっくりと橋の下へ消えていった。風はまだ弱い。",
    "「引き返せ」と老爺は言った。「あの門をくぐった者で戻ってきた者はおらぬ」",
    "少年は答えなかった。ただ拳を握りしめ、崩れかけた石段を一段ずつ登り始めた。",
]
_FR_PARAS = [
    "Il leva les yeux vers les étages de la tour et chercha la présence des Nanae. Le "
    "scellement devait être achevé avant que la nuit ne tombe tout à fait.",
    "Matsurika expira brièvement et posa la main sur le sabre à sa hanche. Le froid des "
    "pavés lui remontait déjà le long des jambes.",
    "Au loin, une cloche sonna. C'était sûrement le signal du départ de la Secte du Dragon "
    "déchu, murmura Aohi sans quitter le porche des yeux.",
    "La lueur des lanternes tremblait à la surface de l'eau, et l'ombre d'une carpe "
    "disparut lentement sous le pont. Le vent restait faible.",
    "« Rebrousse chemin », dit le vieil homme. « Aucun de ceux qui ont franchi cette porte "
    "n'en est jamais revenu. »",
    "Le garçon ne répondit pas. Il serra les poings et se mit à gravir, marche après "
    "marche, l'escalier de pierre à demi effondré.",
]
_JP_BLOC = "\n\n".join(_JP_PARAS)
_FR_BLOC = "\n\n".join(_FR_PARAS)


def test_word_count_inchange_sans_cjk():
    """Non-régression des œuvres à pivot latin, prouvée par construction : sans caractère
    CJK, la substitution est l'identité et le terme ajouté vaut 0."""
    for txt in ("Les uns après les autres, ils partirent.",
                "## Titre de partie\n\nUn paragraphe, puis l'élision qu'on ne perd pas.",
                "Œdème, cœur, forêt — ponctuation et accents compris."):
        assert _word_count(txt) == len(re.findall(r"[^\W\d_]+", txt, re.UNICODE))


def test_word_count_ne_compte_pas_la_ponctuation_cjk():
    """La classe LARGE `tokens.CJK` (budget de tokens) couvre `「」『』、。` et les formes
    pleine chasse : s'en servir ici ferait tenir huit guillemets pour quatre mots. C'est le
    faux positif déjà payé côté manga (cf. `tokens.CJK_TEXTE`), et le seul fichier latin du
    dépôt qu'il faisait diverger était un RAPPORT.md citant des titres entre `『』`."""
    assert _word_count("Le volume 『manga B』 et « autre chose ».") == \
        _word_count("Le volume manga B et « autre chose ».")


def test_word_count_compte_les_ideogrammes():
    """`\\w` inclut les idéogrammes : une phrase japonaise, écrite sans espaces, comptait
    pour UN SEUL mot. C'est ce qui rendait `perte_mots` aveugle sur un pivot japonais."""
    # 43 caractères, dont 40 porteurs, séparés par deux `、` et un `。` : l'ancien compte
    # n'y voyait que les TROIS clauses, le nouveau rend la moitié des 40 porteurs.
    assert len(re.findall(r"[^\W\d_]+", _JP_PARAS[0], re.UNICODE)) == 3
    assert _word_count(_JP_PARAS[0]) == 20


def test_perte_mots_detecte_une_troncature_sur_pivot_japonais():
    """Le cas réel du ch03 : le modèle coupe en plein mot et ne rend qu'un fragment. Avec
    l'ancien compte la source pesait 24 « mots », le seuil tombait à 14 et le fragment
    (15 mots latins) passait — le bloc traversait tout le run compté « ok »."""
    fragment = _FR_PARAS[0][:70]        # coupé en plein mot, comme au ch03
    a = _FakeAgent([fragment, fragment])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", _JP_BLOC, cap=2000, stats=stats,
                                         min_ratio=0.60)
    assert not ok and reason == "perte_mots"
    assert stats["perte_mots"] == 1


def test_perte_mots_ne_se_declenche_pas_sur_un_bloc_japonais_sain():
    """Le pendant du précédent : le seuil de 0,60 déjà en config laisse passer une
    traduction complète (ratio mesuré ~1,2) sans avoir à être retouché."""
    a = _FakeAgent([_FR_BLOC])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", _JP_BLOC, cap=2000, stats=stats,
                                         min_ratio=0.60)
    assert ok and reason is None and len(a.calls) == 1


def test_out_cap_proportional_and_bounded():
    small = _out_cap("mot " * 10)
    big = _out_cap("mot " * 10000)
    assert small < big
    assert _out_cap("x", floor=768) >= 768
    assert _out_cap("x" * 100000, ceil=6000) <= 6000


def test_match_case_promotes_but_never_demotes():
    assert _match_case("Lutin", "leprechaun") == "Leprechaun"     # promeut
    assert _match_case("lutin", "Leprechaun") == "Leprechaun"     # ne rabaisse jamais


def test_keep_images_dedups_and_restores_missing():
    original = "P1\n\n<!-- IMG: media/a.png -->\n\nP2\n\n<!-- IMG: media/b.png -->"
    # l'agent a dupliqué a.png et supprimé b.png
    output = "P1\n\n<!-- IMG: media/a.png -->\n\n<!-- IMG: media/a.png -->\n\nP2"
    out = _keep_images(original, output)
    assert out.count("media/a.png") == 1
    assert "media/b.png" in out


# --------------------------------------------------------------------------- #
# _keep_images raisonne par QUOTA, pas par présence. Régression réelle
# (roman B Vol.2) : le séparateur de scène apparaît plusieurs fois dans un même
# bloc ; le dédoublonnage à une occurrence en supprimait les répétitions
# LÉGITIMES — un séparateur perdu dans chacun des chapitres 5, 8 et 10.
# --------------------------------------------------------------------------- #

_SEP_M = "<!-- IMG: media/sep.png -->"


def test_keep_images_preserves_legitimate_repeats():
    bloc = "\n\n".join(["Scène A.", _SEP_M, "Scène B.", _SEP_M, "Scène C.", _SEP_M])
    assert _keep_images(bloc, bloc).count(_SEP_M) == 3


def test_keep_images_trims_only_the_surplus():
    """L'agent en a mis 4 là où l'entrée en avait 2 : on retire 2, on garde 2."""
    original = "\n\n".join(["A.", _SEP_M, "B.", _SEP_M])
    output = "\n\n".join(["A.", _SEP_M, _SEP_M, "B.", _SEP_M, _SEP_M])
    assert _keep_images(original, output).count(_SEP_M) == 2


def test_keep_images_restores_the_deficit_of_a_repeated_marker():
    """L'agent n'en a gardé qu'un sur trois : les deux manquants sont ré-ajoutés."""
    original = "\n\n".join(["A.", _SEP_M, "B.", _SEP_M, "C.", _SEP_M])
    output = "\n\n".join(["A.", _SEP_M, "B.", "C."])
    assert _keep_images(original, output).count(_SEP_M) == 3


def test_keep_images_mixed_deficit_and_surplus_across_markers():
    original = "\n\n".join(["A.", _SEP_M, "B.", _SEP_M, "C.",
                            "<!-- IMG: media/plate.jpeg -->"])
    # séparateur en déficit (1 sur 2), planche dupliquée (2 pour 1)
    output = "\n\n".join(["A.", _SEP_M, "B.", "C.",
                          "<!-- IMG: media/plate.jpeg -->",
                          "<!-- IMG: media/plate.jpeg -->"])
    out = _keep_images(original, output)
    assert out.count(_SEP_M) == 2
    assert out.count("media/plate.jpeg") == 1


def test_keep_images_noop_when_output_already_matches():
    bloc = "\n\n".join(["A.", _SEP_M, "B.", "<!-- IMG: media/x.jpeg -->"])
    assert _keep_images(bloc, bloc).count("<!-- IMG:") == 2


# --------------------------------------------------------------------------- #
# _enforce_force : remplacement déterministe + accord pluriel
# --------------------------------------------------------------------------- #

def test_enforce_force_singular_and_plural_with_determiner():
    glo = glossary.empty()
    glo["creatures"] = [{"nom": "Leprechaun", "pluriel": "Leprechauns",
                         "interdits": ["lutin", "lutins"], "force": True}]
    text = "Un lutin approcha. Les lutins fuyaient."
    out, n = _enforce_force(text, glo)
    assert n == 2
    assert "Un Leprechaun" in out
    assert "Les Leprechauns" in out


def test_enforce_force_no_pluriel_provided_falls_back_singular():
    glo = glossary.empty()
    glo["objets"] = [{"nom": "Arme Enchantée", "interdits": ["arme secrète", "armes secrètes"], "force": True}]
    out, n = _enforce_force("Les armes secrètes brillaient.", glo)
    # Pas de pluriel fourni : remplacement simple par `nom`, sans accord inventé.
    assert n == 1
    assert "Arme Enchantée" in out


def test_enforce_force_ignores_entries_without_force():
    glo = glossary.empty()
    glo["objets"] = [{"nom": "Autre Nom", "interdits": ["forme interdite"], "force": False}]
    out, n = _enforce_force("La forme interdite apparaît.", glo)
    assert n == 0
    assert "forme interdite" in out


def test_enforce_force_catches_untranslated_termes_source():
    """termes_source (mot de la langue source) doit aussi être rattrapé si le
    traducteur l'a laissé non traduit dans le texte final — c'est un filet de
    sécurité, pas juste une aide pour le traducteur en amont."""
    glo = glossary.empty()
    glo["creatures"] = [{"nom": "Homme Bête", "termes_source": ["Semifer"], "force": True}]
    out, n = _enforce_force("Un Semifer approcha.", glo)
    assert n == 1
    assert "Homme Bête" in out
    assert "Semifer" not in out


def test_enforce_force_no_rules_returns_unchanged():
    out, n = _enforce_force("Texte quelconque.", glossary.empty())
    assert n == 0
    assert out == "Texte quelconque."


# --------------------------------------------------------------------------- #
# _enforce_force : garde-fous « ne jamais introduire une faute que le modèle
# n'aurait pas faite » — élision et changement de genre. Tous ces cas viennent
# d'une démonstration sur un vrai tome (roman C Vol.1), où le remplacement brut
# produisait « L'médecin de combat » et « Une médecin de combat expérimentée ».
# --------------------------------------------------------------------------- #

def _glo_medecin(genre: str = "masculin") -> dict:
    glo = glossary.empty()
    e = {"nom": "médecin de combat", "interdits": ["infirmière", "infirmières"],
         "pluriel": "médecins de combat", "force": True}
    if genre:
        e["genre"] = genre
    glo["personnages"] = [e]
    return glo


def test_enforce_force_repairs_elision_before_consonant():
    """« L'infirmière » → « Le médecin de combat » (et non « L'médecin de combat »,
    qui est une faute de français dure)."""
    out, n = _enforce_force("L'infirmière était là.", _glo_medecin("masculin"))
    assert n == 1
    assert out == "Le médecin de combat était là."
    assert "L'médecin" not in out


def test_enforce_force_elision_uses_entry_gender_for_le_vs_la():
    glo = glossary.empty()
    glo["personnages"] = [{"nom": "sage-femme", "genre": "féminin",
                          "interdits": ["accoucheur"], "force": True}]
    out, n = _enforce_force("L'accoucheur arriva.", glo)
    assert n == 1
    assert out == "La sage-femme arriva."


def test_enforce_force_refuses_when_elision_and_gender_unknown():
    """`l'` + cible à initiale consonne, sans `genre:` dans l'entrée : impossible de
    choisir entre « le » et « la » → on NE remplace PAS, et on le signale."""
    refus: list[str] = []
    out, n = _enforce_force("L'infirmière arriva.", _glo_medecin(genre=""), refus)
    assert n == 0
    assert out == "L'infirmière arriva."
    assert refus and "genre inconnu" in refus[0]


def test_enforce_force_refuses_substitution_that_conflicts_with_determiner_gender():
    """« Une infirmière expérimentée » : corriger le seul nom laisserait « Une » et
    « expérimentée » au féminin. Le déterministe refuse et laisse faire l'agent."""
    refus: list[str] = []
    out, n = _enforce_force("Une infirmière expérimentée arriva.", _glo_medecin("masculin"), refus)
    assert n == 0
    assert out == "Une infirmière expérimentée arriva."
    assert refus and "féminin" in refus[0]


def test_enforce_force_gender_conflict_detected_on_all_gendered_determiners():
    for det in ("Une", "La", "Cette", "Ma", "Sa"):
        refus: list[str] = []
        out, n = _enforce_force(f"{det} infirmière parla.", _glo_medecin("masculin"), refus)
        assert n == 0, det
        assert refus, det


def test_enforce_force_plural_determiner_never_triggers_gender_refusal():
    """« les »/« des » ne révèlent aucun genre : le remplacement doit passer,
    en utilisant la forme `pluriel:`."""
    out, n = _enforce_force("Les infirmières couraient.", _glo_medecin("masculin"))
    assert n == 1
    assert out == "Les médecins de combat couraient."


def test_enforce_force_adds_elision_when_target_starts_with_vowel():
    glo = glossary.empty()
    glo["termes"] = [{"nom": "Union Sabat", "interdits": ["armée sabat"], "force": True}]
    assert _enforce_force("la armée sabat", glo)[0] == "l’Union Sabat"
    assert _enforce_force("de armée sabat", glo)[0] == "d’Union Sabat"
    # la capitale du déterminant d'origine est conservée (début de phrase)
    assert _enforce_force("La armée sabat avança.", glo)[0] == "L’Union Sabat avança."


def test_enforce_force_casing_only_entry_is_applied():
    """Régression : une forme qui ne diffère du `nom` que par la CASSE (« forces de
    défense » → « Forces de défense ») était silencieusement ignorée — c'est pourtant
    le cas le plus sûr à forcer (aucun risque d'accord), et le plus fréquent dans les
    corrections terminologiques (« majuscule imposée par le glossaire »)."""
    glo = glossary.empty()
    glo["organisations"] = [{"nom": "Forces de défense",
                            "interdits": ["forces de défense"], "force": True}]
    out, n = _enforce_force("les forces de défense avancèrent.", glo)
    assert n == 1
    assert out == "les Forces de défense avancèrent."


def test_enforce_force_already_canonical_form_is_not_counted():
    """Le regex est insensible à la casse : il matche aussi la forme DÉJÀ correcte.
    Elle ne doit pas gonfler le compteur (qui sert à détecter qu'un agent aval
    réintroduit des formes bannies)."""
    glo = glossary.empty()
    glo["organisations"] = [{"nom": "Forces de défense",
                            "interdits": ["forces de défense"], "force": True}]
    out, n = _enforce_force("Les Forces de défense.", glo)
    assert n == 0
    assert out == "Les Forces de défense."


def test_enforce_force_is_linear_not_quadratic():
    """Régression de perf : lire le déterminant via `text[:m.start()]` avec un regex
    ancré `$` rescanne tout le préfixe à chaque occurrence → quadratique (mesuré
    3,7 s pour 40 ko, alors qu'un tome fait des centaines de ko)."""
    import time
    glo = glossary.empty()
    glo["creatures"] = [{"nom": "Leprechaun", "interdits": ["lutin"], "force": True}]
    phrase = "Un lutin approcha dans la clairière sombre et humide. "
    petit, grand = phrase * 200, phrase * 1600      # ×8
    t0 = time.perf_counter(); _enforce_force(petit, glo); t_petit = time.perf_counter() - t0
    t0 = time.perf_counter(); _enforce_force(grand, glo); t_grand = time.perf_counter() - t0
    # Linéaire → ~×8. Quadratique → ~×64. Seuil large pour rester stable en CI.
    assert t_grand < max(t_petit, 0.005) * 25


# --------------------------------------------------------------------------- #
# _try_with_temp_retry : retry à température réduite, garde-fou perte de mots
# --------------------------------------------------------------------------- #

class _FakeAgent:
    def __init__(self, outputs, temperature=0.2):
        self.outputs = outputs
        self.calls = []
        self.temperature = temperature

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, **_):
        self.calls.append(temperature)
        return self.outputs[len(self.calls) - 1]


def test_retry_direct_success_no_retry_needed():
    a = _FakeAgent(["Une sortie parfaitement normale et suffisamment longue ici."])
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", "entrée de référence assez longue pour le ratio",
                                           cap=200, stats=stats, min_ratio=0.5)
    assert ok and reason is None and len(a.calls) == 1
    assert stats["blocs_ok"] == 1


def test_retry_emballement_then_recovered_uses_lower_temperature():
    a = _FakeAgent(["x " * 500, "Sortie correcte après le retry."], temperature=0.2)
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", "dry", cap=50, stats=stats)
    assert ok and len(a.calls) == 2
    assert a.calls[1] < a.calls[0] if a.calls[0] else a.calls[1] < 0.2
    assert stats["recupere_par_retry"] == 1


def test_retry_perte_mots_persistent_fails_and_flags_reason():
    ref = "Une phrase de référence assez longue avec beaucoup de mots pour le ratio voulu ici."
    a = _FakeAgent(["mot", "mot mot"])  # les deux bien trop courts
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", ref, cap=200, stats=stats, min_ratio=0.7)
    assert not ok and reason == "perte_mots"
    assert stats["perte_mots"] == 1


def test_retry_titre_perdu_detected_even_without_min_ratio():
    """`perte_mots_ratio` est aveugle à la perte du seul préfixe `##` (le compte de
    mots ne bouge presque pas) — ce garde-fou dédié doit se déclencher même SANS
    `min_ratio` fourni (contrairement à perte_mots)."""
    ref = "## Titre de partie\n\nUn peu de texte de narration qui suit le titre ici."
    a = _FakeAgent(["Titre de partie fondu dans la prose sans son dièse ici.",
                    "Toujours fondu dans la prose sans son dièse au retry."])
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", ref, cap=200, stats=stats)
    assert not ok and reason == "titre_perdu"
    assert stats["titre_perdu"] == 1


def test_retry_titre_perdu_not_triggered_when_heading_preserved():
    ref = "## Titre de partie\n\nUn peu de texte de narration qui suit le titre ici."
    a = _FakeAgent(["## Titre de partie\n\nTexte de narration légèrement reformulé ici."])
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", ref, cap=200, stats=stats)
    assert ok and reason is None


def test_repair_headings_restores_atx_from_bold():
    """Cas réel (roman C ch02) : le traducteur rend un titre `## …` en **gras**. La
    réparation restaure `##` sur autant de lignes entièrement en gras qu'il manque de
    titres — sans quoi `titre_perdu` se déclenche à tort et le bloc retombe sur la
    source anglaise."""
    original = "## April 3rd\n\nTexte.\n\n## April 4th\n\nSuite."
    output = "**3 avril**\n\nTexte traduit.\n\n## 4 avril\n\nSuite traduite."
    fixed = _repair_headings(original, output)
    assert len(_ATX_ANY.findall(fixed)) == 2
    assert "## 3 avril" in fixed and "## 4 avril" in fixed


class _FakeClient:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


def test_close_llm_clients_closes_default_and_endpoint_clients_once_each():
    """Ferme le client par défaut ET le client d'endpoint (reflexion), chacun UNE fois
    (dédoublonnage par id : plusieurs agents partagent le même client en cache)."""
    default = _FakeClient()
    reflexion = _FakeClient()
    from types import SimpleNamespace
    agents = {
        "traducteur": SimpleNamespace(llm=default),
        "correcteur": SimpleNamespace(llm=default),      # même client que traducteur
        "glossariste": SimpleNamespace(llm=reflexion),   # endpoint séparé
    }
    _close_llm_clients(default, agents)
    assert default.closed == 1 and reflexion.closed == 1


def test_close_llm_clients_tolerates_dry_run_none_and_missing_close():
    # dry-run : llm None + agents dont .llm est None → ne lève pas
    _close_llm_clients(None, {"traducteur": type("A", (), {"llm": None})()})
    # client factice sans .close() (doubles de test) → ignoré silencieusement
    from types import SimpleNamespace
    _close_llm_clients(SimpleNamespace(), {})


def test_wire_reporter_routes_incidents_of_every_client_to_warn():
    """Les messages d'incident de TOUS les clients (défaut ET endpoint « reflexion »)
    doivent partir dans reporter.warn, donc dans perf.log."""
    from types import SimpleNamespace
    default, reflexion = SimpleNamespace(), SimpleNamespace()
    recu: list[str] = []
    rep = SimpleNamespace(warn=recu.append)
    _wire_reporter(default, {"traducteur": SimpleNamespace(llm=reflexion),
                            "correcteur": SimpleNamespace(llm=default)}, rep)
    default.on_event("a"); reflexion.on_event("b")
    assert recu == ["a", "b"]


def test_wire_reporter_tolerates_reporter_without_warn():
    from types import SimpleNamespace
    _wire_reporter(SimpleNamespace(), {}, object())      # ne lève pas
    _wire_reporter(None, {}, SimpleNamespace(warn=lambda m: None))


def test_aggregate_llm_stats_sums_every_client_not_just_the_default():
    """Régression : le résumé de RAPPORT.md ne lisait que le client par défaut et
    ignorait l'endpoint « reflexion » (traducteur/terminologue/glossariste), soit
    l'essentiel du run — 79 appels annoncés contre 183 réellement tracés."""
    from types import SimpleNamespace
    default = SimpleNamespace(stats={"appels": 10, "tokens_generes": 100})
    reflexion = SimpleNamespace(stats={"appels": 90, "tokens_generes": 900,
                                       "thinking_overflow": 4})
    total = _aggregate_llm_stats(default, {"traducteur": SimpleNamespace(llm=reflexion),
                                          "correcteur": SimpleNamespace(llm=default)})
    assert total["appels"] == 100
    assert total["tokens_generes"] == 1000
    assert total["thinking_overflow"] == 4        # clé absente du client par défaut
    assert total["troncature_length"] == 0       # absente partout → 0, pas de KeyError


def test_resplit_reasons_cover_size_failures_only():
    """Seuls les motifs causés par un bloc TROP GROS déclenchent le redécoupage. Un échec
    de CONSIGNE (glossaire/guide recopié, titre de partie perdu) ne gagnerait rien à être
    coupé. La boucle dégénérée, elle, EN FAIT PARTIE : mesuré sur roman D Vol.1,
    les blocs en boucle ont généré 19 000 à 29 700 tokens contre ~10 000 pour un bloc
    normal — ils ont bouclé jusqu'à saturer leur plafond, c'est un symptôme de taille.

    `troncature_length`, `thinking_overflow` et `timeout` viennent du CLIENT LLM et non
    d'une heuristique sur la sortie : ce sont les signaux DIRECTS qu'un bloc était trop gros
    pour son budget — de tokens pour les deux premiers, de temps pour le troisième. Couper
    en deux y est même un remède CAUSAL : deux moitiés génèrent deux fois moins."""
    assert {"vide", "emballement", "troncature_image", "perte_mots", "repetition",
            "troncature_length", "thinking_overflow", "timeout"} == set(_RESPLIT_REASONS)
    # L'INVARIANTE, elle, ne bouge pas : un échec de consigne ne se redécoupe jamais.
    assert not _RESPLIT_REASONS & {"glossaire_fuite", "styleguide_fuite", "titre_perdu"}


def test_retry_on_repetition_raises_temperature_instead_of_lowering_it():
    """Régression roman D Vol.1 : la boucle dégénérée est une pathologie de
    BASSE température. Le retry historique refroidissait (× 0.4), ce qui la renforçait — les
    deux tentatives bouclaient. Pour ce motif le retry doit CHAUFFER."""
    boucle = "\n\n".join([_LOOP_PARA] * 4)
    a = _FakeAgent([boucle, "Une sortie enfin normale, sans aucune répétition du passage."],
                   temperature=0.2)
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", "dry", cap=10000, stats=stats,
                                          temp_factor=0.4)
    assert ok and len(a.calls) == 2
    assert a.calls[1] > 0.2, "le retry doit chauffer pour casser le cycle"
    assert a.calls[1] <= 1.0
    assert stats["retry_temp_relevee"] == 1 and stats.get("retry_temp_reduite", 0) == 0


def test_retry_keeps_the_longest_output_when_both_attempts_fail_the_same_way():
    """Deux boucles d'affilée : on rend la plus LONGUE, celle qui a le plus de récit
    récupérable pour l'effondrement des répétitions en aval."""
    court = "\n\n".join([_LOOP_PARA] * 3)
    long = "\n\n".join([_LOOP_PARA] * 3 + ["Un paragraphe de récit supplémentaire bien réel."])
    a = _FakeAgent([court, long], temperature=0.2)
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", "dry", cap=10000, stats=stats)
    assert not ok and reason == "repetition"
    assert out == long


def test_retry_keeps_the_first_output_when_the_two_failures_differ():
    """Contrepartie du test ci-dessus, et branche que le partage du moteur au lot 2.5 aurait
    pu perdre en silence : la comparaison de longueur ne vaut qu'à motif ÉGAL. Ici le 1er
    essai boucle et le 2e revient VIDE — le second est plus court, donc la garde ne se voit
    pas ; on inverse donc les rôles, 1er essai vide (court) et 2e en boucle (long). La
    première sortie doit être conservée : le motif rendu est le sien, et une sortie choisie
    pour un autre motif ne serait pas exploitable par le rattrapage prévu pour celui-là."""
    boucle = "\n\n".join([_LOOP_PARA] * 4)
    a = _FakeAgent(["", boucle], temperature=0.2)
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", "dry", cap=10000, stats=stats)
    assert not ok and reason == "vide"
    assert out == "", "la 2e sortie est plus longue mais son motif diffère : on garde la 1re"
    assert stats["vide"] == 1 and "repetition" not in stats


def test_salvage_repetition_collapses_the_loop_and_keeps_the_french():
    """Rattrapage de dernier recours : une boucle NOIE le récit, elle ne le détruit pas.
    Effondrer les cycles rend un vrai bloc français — infiniment mieux qu'un bloc entier
    laissé en langue source dans le document final."""
    recit = ["Il ouvrit la porte du grenier et découvrit un coffre couvert de poussière.",
             "À l'intérieur dormaient les lettres que son père n'avait jamais envoyées."]
    pivot = " ".join(recit)
    boucle = "\n\n".join(recit + recit + recit + recit)
    out = _salvage_repetition(boucle, pivot)
    assert out is not None
    assert out.count("grenier") == 1
    assert "lettres" in out


def test_salvage_repetition_refuses_a_text_too_amputated_to_be_honest():
    """Si l'effondrement ne laisse qu'une bribe face à l'entrée, on renonce : mieux vaut
    signaler le bloc que livrer un résumé involontaire."""
    pivot = "phrase de référence très longue " * 40
    boucle = "\n\n".join(["Un seul paragraphe substantiel largement trop court ici."] * 5)
    assert _salvage_repetition(boucle, pivot) is None


def test_repair_headings_no_op_when_counts_match():
    original = "## Titre\n\nTexte."
    output = "## Titre traduit\n\nTexte traduit."
    assert _repair_headings(original, output) == output


def test_repair_headings_bounded_to_missing_count():
    """Ne promeut jamais plus de lignes en gras qu'il ne manque de titres : une ligne
    en gras légitime (emphase) au-delà du besoin reste intacte."""
    original = "## Titre\n\nTexte."
    output = "**Titre**\n\n**une emphase autonome**\n\nTexte."
    fixed = _repair_headings(original, output)
    assert len(_ATX_ANY.findall(fixed)) == 1
    assert "**une emphase autonome**" in fixed   # non promue


def test_retry_titre_perdu_repaired_by_postprocess_is_accepted():
    """Avec le post-traitement de réparation, un `##` rendu en **gras** est corrigé
    AVANT le diagnostic : le bloc est accepté (français conservé) au lieu d'être rejeté
    puis réinjecté en anglais."""
    ref = "## Titre de partie\n\nUn peu de texte de narration qui suit le titre ici."
    a = _FakeAgent(["**Titre de partie**\n\nTexte de narration traduit qui suit ici."])
    stats = {}
    out, ok, reason = _try_with_temp_retry(
        a, "u", ref, cap=200, stats=stats,
        postprocess=lambda o: _repair_headings(ref, o))
    assert ok and reason is None and len(a.calls) == 1
    assert out.startswith("## Titre de partie")


def test_retry_empty_response_persistent_fails():
    a = _FakeAgent(["", ""])
    stats = {}
    out, ok, reason = _try_with_temp_retry(a, "u", "dry", cap=200, stats=stats)
    assert not ok and reason == "vide"
    assert stats["vide"] == 1


def test_retry_applies_postprocess_before_diagnosis():
    a = _FakeAgent(["```\nContenu correct et assez long pour passer le seuil voulu ici.\n```"])
    stats = {}
    out, ok, _ = _try_with_temp_retry(a, "u", "dry", cap=200, stats=stats,
                                      postprocess=lambda s: s.strip("`\n"))
    assert ok
    assert not out.startswith("```")


# --------------------------------------------------------------------------- #
# --chapitre N (test d'intégration léger, agents simulés)
# --------------------------------------------------------------------------- #

@pytest.fixture
def chapitre_project(tmp_path, monkeypatch):
    """Petit projet à 3 chapitres, agents mockés (passthrough), config de base."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "sources" / "ChapTest" / "Vol.1"
    fr = base / "FR"; fr.mkdir(parents=True)
    (fr / "v.txt").write_text(
        "Chapitre 1\n\nTexte un.\n\nChapitre 2\n\nTexte deux.\n\nChapitre 3\n\nTexte trois.",
        encoding="utf-8")
    (base / "ENG").mkdir()
    (base / "ENG" / "v.txt").write_text("Chapter 1\n\nA.\n\nChapter 2\n\nB.\n\nChapter 3\n\nC.",
                                        encoding="utf-8")

    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(open(root / "config.yaml", encoding="utf-8"))
    cfg["options"]["dry_run"] = False
    cfg["decoupage"]["detection"] = "structure"
    cfg["chemins"]["sources"] = str(tmp_path / "sources")
    cfg["chemins"]["build"] = str(tmp_path / "build")
    cfg["chemins"]["style_guide"] = str(root / "style_guide.md")
    cfg["chemins"]["prompts"] = str(root / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    cfg.setdefault("langues", {})["packs"] = str(root / "langues")
    # Connexion LLM DÉLIBÉRÉMENT figée ici, indépendamment de ce que contient le
    # config.yaml réel (que l'utilisateur édite pour SON setup) : ce test vérifie le
    # comportement de --chapitre avec des agents simulés (aucun appel réseau réel),
    # pas la config personnelle de la machine sur laquelle pytest tourne.
    cfg["llm"] = {"base_url": "http://localhost:1234/v1", "api_key": "test", "timeout": 60,
                 "max_retries": 1, "extra_directive": "", "think": False,
                 "endpoints": {}}
    cfg["modeles"] = {n: "qwen/qwen3.5" for n in
                      ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]}
    # Gabarits : NON renseignés, donc servis par le pack de langue cible — c'est le
    # chemin réel depuis que `langues/fr/templates/` les porte. Les pointer à la main
    # testerait un chemin que plus personne n'emprunte.
    return cfg


def _install_counting_agent(monkeypatch):
    import pipeline.agents as agents_mod
    calls = {"n": 0}

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None, **_):
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        calls["n"] += 1
        return f"[v{calls['n']}] {dry_payload}"
    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    return calls


def test_chapitre_n_only_recomputes_target(chapitre_project, monkeypatch):
    from pipeline.reporter import Reporter
    calls = _install_counting_agent(monkeypatch)

    process_volume("ChapTest", "Vol.1", chapitre_project, reporter=Reporter())
    full_md = Path(chapitre_project["chemins"]["build"]) / "ChapTest" / "Vol.1" / "ChapTest_Vol.1.md"
    before = full_md.read_text(encoding="utf-8")

    calls["n"] = 0
    process_volume("ChapTest", "Vol.1", chapitre_project, reporter=Reporter(), only_chapter=2)
    after = full_md.read_text(encoding="utf-8")

    # Chapitres 1 et 3 identiques à avant ; seul le chapitre 2 doit avoir de nouveaux marqueurs.
    # On retire l'en-tête d'empreinte (`<!-- Angelith … · date hh:mm -->`, ajouté au lot 0) :
    # il est réécrit à chaque run et porte la MINUTE, donc deux `process_volume` de part et
    # d'autre d'un changement de minute faisaient échouer ce test au hasard — une fois sur
    # ~60 exécutions de la suite complète. Ce n'est pas ce que le test veut vérifier.
    def _sans_empreinte(md: str) -> str:
        return re.sub(r"\A<!-- Angelith .*?-->\n*", "", md)

    before_ch1 = _sans_empreinte(before).split("# Chapitre 2")[0]
    after_ch1 = _sans_empreinte(after).split("# Chapitre 2")[0]
    assert before_ch1 == after_ch1
    assert calls["n"] > 0        # le chapitre 2 A été recalculé


def test_chapitre_n_out_of_range_raises(chapitre_project, monkeypatch):
    from pipeline.reporter import Reporter
    _install_counting_agent(monkeypatch)
    with pytest.raises(SystemExit):
        process_volume("ChapTest", "Vol.1", chapitre_project, reporter=Reporter(), only_chapter=99)


def test_rapport_has_end_time_and_run_emits_eta(chapitre_project, monkeypatch):
    """RAPPORT.md porte l'heure de fin (runs de nuit), et un run complet multi-chapitres
    émet une estimation du temps restant après chaque chapitre sauf le dernier."""
    from pipeline.reporter import Reporter
    _install_counting_agent(monkeypatch)
    infos: list[str] = []

    class Rec(Reporter):
        def info(self, msg):
            infos.append(msg)

    process_volume("ChapTest", "Vol.1", chapitre_project, reporter=Rec())     # 3 chapitres (Chapter 1/2/3)
    rapport = (Path(chapitre_project["chemins"]["build"]) / "ChapTest" / "Vol.1"
               / "RAPPORT.md").read_text(encoding="utf-8")
    assert "Terminé le" in rapport
    assert any("estimation" in m and "fin vers" in m for m in infos)


# --------------------------------------------------------------------------- #
# `force: true` appliqué DÈS LA SORTIE DU TRADUCTEUR (et non plus seulement sur
# le Markdown assemblé) : le correcteur voit la terminologie canonique et
# ne dépense plus d'appels LLM à corriger ce que le déterministe corrige.
# --------------------------------------------------------------------------- #

def _forced_glossary_project(chapitre_project, tmp_path):
    """Ajoute au projet de test un glossaire avec une entrée `force: true`."""
    chapitre_project["langues"]["optimiser_apres_terminologie"] = False   # pas de glossariste simulé
    glo = glossary.empty()
    glo["creatures"] = [{"nom": "Leprechaun", "genre": "masculin",
                        "interdits": ["lutin", "lutins"], "force": True}]
    gpath = Path(chapitre_project["chemins"]["sources"]) / "ChapTest" / "glossaire.yaml"
    glossary.save(glo, gpath)
    fr = Path(chapitre_project["chemins"]["sources"]) / "ChapTest" / "Vol.1" / "FR" / "v.txt"
    fr.write_text("Chapitre 1\n\nUn lutin passa.\n\nChapitre 2\n\nDeux lutins.\n\n"
                  "Chapitre 3\n\nLe lutin dormait.", encoding="utf-8")
    return chapitre_project


def test_force_applied_on_traduction_checkpoint_not_only_at_the_end(chapitre_project, tmp_path, monkeypatch):
    """Preuve du repositionnement : la forme canonique est déjà dans le checkpoint de
    TRADUCTION — donc le correcteur la reçoit déjà corrigée."""
    from pipeline.reporter import Reporter
    cfg = _forced_glossary_project(chapitre_project, tmp_path)
    _install_counting_agent(monkeypatch)

    process_volume("ChapTest", "Vol.1", cfg, reporter=Reporter())

    ck = Path(cfg["chemins"]["build"]) / "ChapTest" / "Vol.1" / ".checkpoints" / "ch01" / "traduction" / "000.txt"
    trad = ck.read_text(encoding="utf-8")
    assert "Leprechaun" in trad
    assert "lutin" not in trad.lower()


def test_force_reaches_final_markdown_without_a_second_pass(chapitre_project, tmp_path, monkeypatch):
    from pipeline.reporter import Reporter
    cfg = _forced_glossary_project(chapitre_project, tmp_path)
    _install_counting_agent(monkeypatch)

    process_volume("ChapTest", "Vol.1", cfg, reporter=Reporter())

    full = (Path(cfg["chemins"]["build"]) / "ChapTest" / "Vol.1" / "ChapTest_Vol.1.md").read_text(encoding="utf-8")
    assert "Leprechaun" in full
    assert "lutin" not in full.lower()


def test_force_disabled_by_config_leaves_text_untouched(chapitre_project, tmp_path, monkeypatch):
    """Non-régression : `appliquer_traductions_forcees: false` ne doit rien forcer,
    ni à la traduction (nouveau point d'application) ni ailleurs."""
    from pipeline.reporter import Reporter
    cfg = _forced_glossary_project(chapitre_project, tmp_path)
    cfg["langues"]["appliquer_traductions_forcees"] = False
    _install_counting_agent(monkeypatch)

    process_volume("ChapTest", "Vol.1", cfg, reporter=Reporter())

    trad = (Path(cfg["chemins"]["build"]) / "ChapTest" / "Vol.1" / ".checkpoints" / "ch01"
            / "traduction" / "000.txt").read_text(encoding="utf-8")
    assert "lutin" in trad.lower()
    assert "Leprechaun" not in trad


def test_force_report_lists_refusals_for_review(chapitre_project, tmp_path, monkeypatch):
    """Un remplacement refusé par les garde-fous d'accord doit être SIGNALÉ dans
    RAPPORT.md (avec le conseil de compléter `genre:`), pas disparaître en silence."""
    from pipeline.reporter import Reporter
    cfg = _forced_glossary_project(chapitre_project, tmp_path)
    # Entrée masculine dont la forme interdite est employée au féminin dans le texte :
    # « Une infirmière » → garde-fou de genre → refus + signalement.
    glo = glossary.empty()
    glo["personnages"] = [{"nom": "médecin de combat", "genre": "masculin",
                          "interdits": ["infirmière"], "force": True}]
    glossary.save(glo, Path(cfg["chemins"]["sources"]) / "ChapTest" / "glossaire.yaml")
    fr = Path(cfg["chemins"]["sources"]) / "ChapTest" / "Vol.1" / "FR" / "v.txt"
    fr.write_text("Chapitre 1\n\nUne infirmière arriva.\n\nChapitre 2\n\nTexte deux.\n\n"
                  "Chapitre 3\n\nTexte trois.", encoding="utf-8")
    _install_counting_agent(monkeypatch)

    process_volume("ChapTest", "Vol.1", cfg, reporter=Reporter())

    rapport = (Path(cfg["chemins"]["build"]) / "ChapTest" / "Vol.1" / "RAPPORT.md").read_text(encoding="utf-8")
    assert "refusées" in rapport
    assert "infirmière" in rapport
    assert "genre" in rapport


# --------------------------------------------------------------------------- #
# --verbose : la terminologie (process_volume) et le glossariste doivent
# émettre une ligne de perf, exactement comme traduction/correction/
# mise en page (régression : ces deux étapes ne l'ont jamais fait).
# --------------------------------------------------------------------------- #

class _RecordingReporter:
    """Reporter minimal qui garde une trace de tout ce qui passe par verbose().

    ⚠ **Il double le protocole ENTIER, pas seulement ce qu'il écoute.** Un double qui
    s'écarte du protocole qu'il double ne teste plus rien, et il tombe le jour où
    l'orchestrateur appelle une méthode de plus — ce que le lot 32 a fait avec `phase`.
    `tests/test_reporter_protocole.py` garde désormais cette correspondance."""
    def __init__(self):
        self.verbose_msgs = []
        self.phases = []

    def volume(self, plan): pass
    def chapter(self, idx, total, title): pass
    def stage(self, name): pass
    def block(self, idx, total): pass
    def progres(self, courant, total, objet=""): pass
    def phase(self, identifiant, libelle=""): self.phases.append(identifiant)
    def warn(self, msg): pass
    def info(self, msg): pass
    def verbose(self, msg): self.verbose_msgs.append(msg)
    def finish(self, outputs): pass
    def stopped(self, done, total): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_process_volume_terminologie_emits_verbose_per_block(chapitre_project, monkeypatch):
    _install_counting_agent(monkeypatch)
    chapitre_project["options"]["verbose"] = True
    rep = _RecordingReporter()

    process_volume("ChapTest", "Vol.1", chapitre_project, reporter=rep, only_chapter=1)

    assert any(m.startswith("[terminologie] bloc") for m in rep.verbose_msgs)


def test_process_volume_no_verbose_by_default(chapitre_project, monkeypatch):
    """Non-régression : verbose=False (comportement par défaut) ne doit rien logger."""
    _install_counting_agent(monkeypatch)
    rep = _RecordingReporter()

    process_volume("ChapTest", "Vol.1", chapitre_project, reporter=rep, only_chapter=1)

    assert rep.verbose_msgs == []


def test_optimize_glossary_file_emits_verbose_when_enabled(tmp_path):
    from pipeline.orchestrator import optimize_glossary_file
    from pipeline import glossary

    glo_path = tmp_path / "glossaire.yaml"
    glo = glossary.empty()
    glo["termes"] = [{"nom": "Test", "traduire": "test", "interdits": [], "force": False}]
    glossary.save(glo, glo_path)

    class _FakeLLM:
        def __init__(self):
            self.stats = {"tokens_generes": 0}

    class _FakeGlossaristeAgent:
        def __init__(self):
            self.llm = _FakeLLM()

        def run(self, user, dry_payload="", max_tokens=None, temperature=None, **_):
            self.llm.stats["tokens_generes"] += 42
            return dry_payload  # renvoie le glossaire tel quel (comme le ferait le dry-run)

    rep = _RecordingReporter()
    optimize_glossary_file(glo_path, {"glossariste": _FakeGlossaristeAgent()},
                           rep, dry=False, verbose=True)

    assert any(m.startswith("[glossariste] optimisation") for m in rep.verbose_msgs)


# --------------------------------------------------------------------------- #
# Redécoupage-relance : un bloc qui échoue pour une raison de TAILLE est coupé en
# deux et rejoué, au lieu d'être abandonné et réinjecté en langue source.
# Cas réel (roman B Vol.2 ch15) : bloc de ~8 000 c. en un seul morceau, plafond
# de sortie saturé, épilogue entier dupliqué, sortie conservée telle quelle.
# --------------------------------------------------------------------------- #

class _WarnRecordingReporter(_RecordingReporter):
    def __init__(self):
        super().__init__()
        self.warn_msgs = []

    def warn(self, msg): self.warn_msgs.append(msg)


def _resplit_project(tmp_path, monkeypatch):
    """Projet à UN chapitre dont l'unique bloc dépasse `redecoupage_taille_min`."""
    monkeypatch.chdir(tmp_path)
    corps = "\n\n".join(
        f"Paragraphe numéro {i} du chapitre, avec assez de texte pour peser un peu "
        f"dans le découpage en blocs et dépasser le seuil de redécoupage." for i in range(12))
    src = tmp_path / "sources" / "Resplit" / "Vol.1" / "FR"
    src.mkdir(parents=True)
    (src / "v.txt").write_text(f"Chapitre 1\n\n{corps}", encoding="utf-8")

    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(open(root / "config.yaml", encoding="utf-8"))
    cfg["options"]["dry_run"] = False
    cfg["decoupage"]["detection"] = "structure"
    cfg["chemins"]["sources"] = str(tmp_path / "sources")
    cfg["chemins"]["build"] = str(tmp_path / "build")
    cfg["chemins"]["style_guide"] = str(root / "style_guide.md")
    cfg["chemins"]["prompts"] = str(root / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    cfg.setdefault("langues", {})["packs"] = str(root / "langues")
    cfg["langues"]["optimiser_apres_terminologie"] = False
    cfg["llm"] = {"base_url": "http://localhost:1234/v1", "api_key": "test", "timeout": 60,
                 "max_retries": 1, "extra_directive": "", "think": False, "endpoints": {}}
    cfg["modeles"] = {n: "qwen/qwen3.5" for n in
                      ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]}
    # Gabarits : NON renseignés, donc servis par le pack de langue cible — c'est le
    # chemin réel depuis que `langues/fr/templates/` les porte. Les pointer à la main
    # testerait un chemin que plus personne n'emprunte.
    return cfg


def _install_emballement_agent(monkeypatch, seuil: int = 900):
    """Traducteur qui « s'emballe » (sortie très au-dessus du plafond) sur tout bloc
    plus gros que `seuil`, et traduit normalement en dessous. Reproduit fidèlement le
    ch15 : le bloc entier échoue, ses moitiés passent."""
    import pipeline.agents as agents_mod
    vus = {"gros": 0, "petits": []}
    emballee = " ".join(f"Phrase emballée numéro {i} sans aucune répétition littérale."
                        for i in range(500))

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None, **_):
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        if self.nom == "traducteur":
            if len(dry_payload) > seuil:
                vus["gros"] += 1
                return emballee
            vus["petits"].append(len(dry_payload))
        return f"[fr] {dry_payload}"
    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    return vus


def test_resplit_recovers_a_block_that_fails_whole(tmp_path, monkeypatch):
    cfg = _resplit_project(tmp_path, monkeypatch)
    vus = _install_emballement_agent(monkeypatch)
    rep = _WarnRecordingReporter()

    process_volume("Resplit", "Vol.1", cfg, reporter=rep)

    trad = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"
            / "traduction" / "000.txt").read_text(encoding="utf-8")
    # Les deux moitiés ont été traduites et recollées : rien n'est perdu, rien n'est
    # laissé en langue source, aucun marqueur AMBIGU.
    assert trad.count("[fr]") == 2
    assert "AMBIGU" not in trad
    assert all(f"Paragraphe numéro {i} du chapitre" in trad for i in range(12))
    # le bloc entier a bien échoué (2 tentatives : normale + température réduite)
    assert vus["gros"] == 2
    assert len(vus["petits"]) == 2
    assert any("redécoupage en 2 et relance" in m for m in rep.warn_msgs)


def test_resplit_is_reported(tmp_path, monkeypatch):
    cfg = _resplit_project(tmp_path, monkeypatch)
    _install_emballement_agent(monkeypatch)

    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    rapport = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1"
               / "RAPPORT.md").read_text(encoding="utf-8")
    assert "Redécoupages sur échec : 1 bloc(s)" in rapport
    assert "2 sous-bloc(s) récupéré(s)" in rapport


def test_resplit_disabled_falls_back_to_the_old_behaviour(tmp_path, monkeypatch):
    """`redecoupage_sur_echec: false` → comportement historique : la sortie emballée est
    conservée telle quelle et signalée par un marqueur AMBIGU (c'est exactement ce qui
    a laissé passer l'épilogue dupliqué du ch15)."""
    cfg = _resplit_project(tmp_path, monkeypatch)
    cfg["garde_fous"]["redecoupage_sur_echec"] = False
    vus = _install_emballement_agent(monkeypatch)
    rep = _WarnRecordingReporter()

    process_volume("Resplit", "Vol.1", cfg, reporter=rep)

    trad = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"
            / "traduction" / "000.txt").read_text(encoding="utf-8")
    assert "AMBIGU" in trad and "emballement" in trad
    assert vus["petits"] == []                    # aucune moitié n'a été tentée
    assert not any("redécoupage" in m for m in rep.warn_msgs)


def test_resplit_stops_below_the_minimum_size(tmp_path, monkeypatch):
    """Un bloc déjà petit qui échoue ne souffre pas d'un problème de taille : on ne le
    coupe pas, on garde le comportement de repli."""
    cfg = _resplit_project(tmp_path, monkeypatch)
    cfg["garde_fous"]["redecoupage_taille_min"] = 100000     # plus rien n'est redécoupable
    vus = _install_emballement_agent(monkeypatch)

    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    assert vus["petits"] == []
    trad = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"
            / "traduction" / "000.txt").read_text(encoding="utf-8")
    assert "AMBIGU" in trad


def test_resplit_depth_is_bounded(tmp_path, monkeypatch):
    """Profondeur 1 : le bloc est coupé UNE fois. Si les moitiés échouent aussi, on ne
    descend pas plus bas — on replie, sans exploser le coût en tokens."""
    cfg = _resplit_project(tmp_path, monkeypatch)
    cfg["garde_fous"]["redecoupage_profondeur_max"] = 1
    cfg["garde_fous"]["redecoupage_taille_min"] = 10
    # seuil 0 → TOUT bloc s'emballe, y compris les moitiés et les quarts
    vus = _install_emballement_agent(monkeypatch, seuil=0)

    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    # 2 tentatives sur le bloc entier + 2 sur chacune des 2 moitiés = 6, jamais plus
    assert vus["gros"] == 6


# --------------------------------------------------------------------------- #
# Recalage des frontières de chapitre d'une source de référence. Cas réel
# (roman B Vol.2) : 16 chapitres des DEUX côtés, mais le chapitre 15 japonais
# contenait en plus tout l'épilogue — le traducteur l'a donc traduit une seconde
# fois en fin de chapitre 15. L'égalité des compteurs valait alignement 1:1.
# --------------------------------------------------------------------------- #

def _misaligned_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    filler = " ".join(f"mot{i}" for i in range(18))          # ~110 c. par paragraphe

    def corps(n, tag):
        return "\n\n".join(f"{tag}{i} {filler}" for i in range(n))

    base = tmp_path / "sources" / "Realign" / "Vol.1"
    fr = base / "FR"; fr.mkdir(parents=True)
    (fr / "v.txt").write_text(
        f"Chapitre 1\n\n{corps(20, 'A')}\n\nChapitre 2\n\n{corps(5, 'B')}\n\n"
        f"Chapitre 3\n\n{corps(20, 'C')}", encoding="utf-8")
    # Anglais : même nombre de chapitres, mais la frontière 2/3 est bien trop tardive —
    # le chapitre 2 déborde sur le 3, qui n'en garde que la fin.
    eng = base / "ENG"; eng.mkdir()
    (eng / "v.txt").write_text(
        f"Chapter 1\n\n{corps(20, 'X')}\n\nChapter 2\n\n{corps(22, 'Y')}\n\n"
        f"Chapter 3\n\n{corps(3, 'Z')}", encoding="utf-8")

    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(open(root / "config.yaml", encoding="utf-8"))
    cfg["options"]["dry_run"] = False
    cfg["decoupage"]["detection"] = "structure"
    cfg["chemins"]["sources"] = str(tmp_path / "sources")
    cfg["chemins"]["build"] = str(tmp_path / "build")
    cfg["chemins"]["style_guide"] = str(root / "style_guide.md")
    cfg["chemins"]["prompts"] = str(root / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    cfg.setdefault("langues", {})["packs"] = str(root / "langues")
    cfg["langues"]["optimiser_apres_terminologie"] = False
    cfg["llm"] = {"base_url": "http://localhost:1234/v1", "api_key": "test", "timeout": 60,
                 "max_retries": 1, "extra_directive": "", "think": False, "endpoints": {}}
    cfg["modeles"] = {n: "qwen/qwen3.5" for n in
                      ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]}
    # Gabarits : NON renseignés, donc servis par le pack de langue cible — c'est le
    # chemin réel depuis que `langues/fr/templates/` les porte. Les pointer à la main
    # testerait un chemin que plus personne n'emprunte.
    return cfg


def test_misaligned_reference_is_realigned_and_reported(tmp_path, monkeypatch):
    cfg = _misaligned_project(tmp_path, monkeypatch)
    _install_counting_agent(monkeypatch)
    rep = _WarnRecordingReporter()

    process_volume("Realign", "Vol.1", cfg, reporter=rep)

    assert any("frontières de chapitre recalées" in m for m in rep.warn_msgs)
    rapport = (Path(cfg["chemins"]["build"]) / "Realign" / "Vol.1"
               / "RAPPORT.md").read_text(encoding="utf-8")
    assert "Alignement des sources de référence" in rapport
    assert "chapitres 2, 3" in rapport


def test_aligned_reference_is_not_touched_nor_reported(tmp_path, monkeypatch):
    """Non-régression : un volume bien aligné ne doit produire aucun recalage ni aucune
    ligne dans RAPPORT.md — le mécanisme ne se déclenche que sur une vraie anomalie."""
    cfg = _misaligned_project(tmp_path, monkeypatch)
    filler = " ".join(f"mot{i}" for i in range(18))

    def corps(n, tag):
        return "\n\n".join(f"{tag}{i} {filler}" for i in range(n))
    eng = Path(cfg["chemins"]["sources"]) / "Realign" / "Vol.1" / "ENG" / "v.txt"
    eng.write_text(f"Chapter 1\n\n{corps(20, 'X')}\n\nChapter 2\n\n{corps(5, 'Y')}\n\n"
                   f"Chapter 3\n\n{corps(20, 'Z')}", encoding="utf-8")
    _install_counting_agent(monkeypatch)
    rep = _WarnRecordingReporter()

    process_volume("Realign", "Vol.1", cfg, reporter=rep)

    assert not any("recalées" in m for m in rep.warn_msgs)
    rapport = (Path(cfg["chemins"]["build"]) / "Realign" / "Vol.1"
               / "RAPPORT.md").read_text(encoding="utf-8")
    assert "Alignement des sources de référence" not in rapport


def test_chapter_count_mismatch_is_now_reported(tmp_path, monkeypatch):
    """Des compteurs différents font APPARIER les unités de référence sur les chapitres du
    pivot (`split.apparier_chapitres`) : le résultat reste approximatif, il doit donc être
    SIGNALÉ, pas appliqué en silence.

    Le message dit désormais « appariés » et non plus « alignée proportionnellement » : la
    référence n'est plus redécoupée par nombre de paragraphes, ses unités sont regroupées
    par parts de volume."""
    cfg = _misaligned_project(tmp_path, monkeypatch)
    filler = " ".join(f"mot{i}" for i in range(18))
    eng = Path(cfg["chemins"]["sources"]) / "Realign" / "Vol.1" / "ENG" / "v.txt"
    eng.write_text(f"Chapter 1\n\nX0 {filler}\n\nChapter 2\n\nY0 {filler}", encoding="utf-8")
    _install_counting_agent(monkeypatch)
    rep = _WarnRecordingReporter()

    process_volume("Realign", "Vol.1", cfg, reporter=rep)

    assert any("appariés par proportions" in m for m in rep.warn_msgs)


def test_appariement_detail_is_written_to_report(tmp_path, monkeypatch):
    """Le RAPPORT doit dire QUELLE unité de référence a nourri quel chapitre, et laquelle a
    été écartée.

    Sans ce détail, on ne peut pas savoir a posteriori ce qui a été mis en regard de quoi —
    et c'est ainsi que l'épilogue de roman B Vol.3 s'est retrouvé apparié à la postface de
    l'auteur sans que rien ne le signale."""
    cfg = _misaligned_project(tmp_path, monkeypatch)
    filler = " ".join(f"mot{i}" for i in range(18))
    # L'anglais porte DEUX chapitres de plus que le pivot, dont un colophon minuscule en
    # queue : il doit être écarté, pas rattaché au dernier chapitre.
    eng = Path(cfg["chemins"]["sources"]) / "Realign" / "Vol.1" / "ENG" / "v.txt"
    corps = "\n\n".join(f"X{i} {filler}" for i in range(20))
    eng.write_text(
        f"Chapter 1\n\n{corps}\n\nChapter 2\n\n{corps}\n\nChapter 3\n\n{corps}\n\n"
        f"Chapter 4\n\nColophon.", encoding="utf-8")
    _install_counting_agent(monkeypatch)
    rep = _WarnRecordingReporter()

    process_volume("Realign", "Vol.1", cfg, reporter=rep)

    rapport = (Path(cfg["chemins"]["build"]) / "Realign" / "Vol.1"
               / "RAPPORT.md").read_text(encoding="utf-8")
    assert "Alignement des sources de référence" in rapport
    assert "←" in rapport, "le détail chapitre par chapitre manque"
    assert "écartée" in rapport, "les unités abandonnées ne sont pas nommées"


# --------------------------------------------------------------------------- #
# Intégration images : aucune image ne doit disparaître entre la source et le
# Markdown assemblé — ni les planches couleur de tête de volume (jetées par la
# détection de chapitres), ni les séparateurs de scène répétés.
# --------------------------------------------------------------------------- #

def _images_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sep = "<!-- IMG: media/sep.png -->"
    src = tmp_path / "sources" / "Imgs" / "Vol.1" / "FR"
    src.mkdir(parents=True)
    # 2 planches AVANT le premier chapitre + un séparateur répété 3 fois DANS le chapitre 1
    # (dont 2 dans le même bloc) et 2 fois dans le chapitre 2.
    (src / "v.txt").write_text(
        "<!-- IMG: media/plate1.jpeg -->\n\n<!-- IMG: media/plate2.jpeg -->\n\n"
        f"Chapitre 1\n\nScène A du récit.\n\n{sep}\n\nScène B du récit.\n\n{sep}\n\n"
        f"Scène C du récit.\n\n{sep}\n\n"
        f"Chapitre 2\n\nScène D du récit.\n\n{sep}\n\nScène E du récit.\n\n{sep}",
        encoding="utf-8")

    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(open(root / "config.yaml", encoding="utf-8"))
    cfg["options"]["dry_run"] = False
    cfg["decoupage"]["detection"] = "structure"
    cfg["chemins"]["sources"] = str(tmp_path / "sources")
    cfg["chemins"]["build"] = str(tmp_path / "build")
    cfg["chemins"]["style_guide"] = str(root / "style_guide.md")
    cfg["chemins"]["prompts"] = str(root / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    cfg.setdefault("langues", {})["packs"] = str(root / "langues")
    cfg["langues"]["optimiser_apres_terminologie"] = False
    cfg["llm"] = {"base_url": "http://localhost:1234/v1", "api_key": "test", "timeout": 60,
                 "max_retries": 1, "extra_directive": "", "think": False, "endpoints": {}}
    cfg["modeles"] = {n: "qwen/qwen3.5" for n in
                      ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]}
    # Gabarits : NON renseignés, donc servis par le pack de langue cible — c'est le
    # chemin réel depuis que `langues/fr/templates/` les porte. Les pointer à la main
    # testerait un chemin que plus personne n'emprunte.
    return cfg


def test_no_image_is_lost_between_source_and_assembled_markdown(tmp_path, monkeypatch):
    cfg = _images_project(tmp_path, monkeypatch)
    _install_counting_agent(monkeypatch)

    process_volume("Imgs", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    b = Path(cfg["chemins"]["build"]) / "Imgs" / "Vol.1"
    full = (b / "Imgs_Vol.1.md").read_text(encoding="utf-8")
    # 2 planches de tête + 5 séparateurs = 7, exactement comme la source
    assert full.count("<!-- IMG:") == 7
    assert full.count("media/sep.png") == 5
    assert full.count("media/plate1.jpeg") == 1 and full.count("media/plate2.jpeg") == 1
    # les planches sont AVANT le premier chapitre
    assert full.index("media/plate1.jpeg") < full.index("# Chapitre 1")
    assert (b / "chapters" / "front-matter.md").exists()


def test_rapport_reports_the_image_count(tmp_path, monkeypatch):
    cfg = _images_project(tmp_path, monkeypatch)
    _install_counting_agent(monkeypatch)

    process_volume("Imgs", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    rapport = (Path(cfg["chemins"]["build"]) / "Imgs" / "Vol.1"
               / "RAPPORT.md").read_text(encoding="utf-8")
    assert "- Images : 7 dans la source · 7 dans le Markdown assemblé · 7 dans le rendu" in rapport
    assert "écart" not in rapport


def test_front_matter_prose_is_flagged_as_untranslated(tmp_path, monkeypatch):
    """Du texte substantiel avant le premier chapitre n'est pas traduit : il faut le dire."""
    cfg = _images_project(tmp_path, monkeypatch)
    v = Path(cfg["chemins"]["sources"]) / "Imgs" / "Vol.1" / "FR" / "v.txt"
    v.write_text("Table des matières — " + "un titre de section quelconque. " * 20
                 + "\n\n" + v.read_text(encoding="utf-8"), encoding="utf-8")
    _install_counting_agent(monkeypatch)
    rep = _WarnRecordingReporter()

    process_volume("Imgs", "Vol.1", cfg, reporter=rep)

    assert any("hors chapitres" in m and "NON traduits" in m for m in rep.warn_msgs)


# --------------------------------------------------------------------------- #
# B1 : cache du rendu du glossaire (glossary.to_text) pendant la terminologie —
# ne doit PAS être re-rendu à chaque bloc quand aucun terme nouveau n'apparaît.
# --------------------------------------------------------------------------- #

def test_process_volume_terminologie_does_not_rerender_glossary_on_noop_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "sources" / "CacheTest" / "Vol.1"
    fr = base / "FR"; fr.mkdir(parents=True)
    paragraphs = "\n\n".join(
        f"Phrase de narration numéro {i} sans aucun nom propre à signaler ici." for i in range(8))
    (fr / "v.txt").write_text(f"Chapitre 1\n\n{paragraphs}", encoding="utf-8")

    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(open(root / "config.yaml", encoding="utf-8"))
    cfg["options"]["dry_run"] = False
    cfg["decoupage"]["detection"] = "structure"
    cfg["decoupage"]["max_block_chars"] = 40   # force PLUSIEURS blocs sur ce texte court
    cfg["chemins"]["sources"] = str(tmp_path / "sources")
    cfg["chemins"]["build"] = str(tmp_path / "build")
    cfg["chemins"]["style_guide"] = str(root / "style_guide.md")
    cfg["chemins"]["prompts"] = str(root / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    cfg.setdefault("langues", {})["packs"] = str(root / "langues")
    cfg["llm"] = {"base_url": "http://localhost:1234/v1", "api_key": "test", "timeout": 60,
                 "max_retries": 1, "extra_directive": "", "think": False, "endpoints": {}}
    cfg["modeles"] = {n: "qwen/qwen3.5" for n in
                      ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]}
    # Gabarits : NON renseignés, donc servis par le pack de langue cible — c'est le
    # chemin réel depuis que `langues/fr/templates/` les porte. Les pointer à la main
    # testerait un chemin que plus personne n'emprunte.

    _install_counting_agent(monkeypatch)

    from pipeline import glossary as glossary_mod
    real_to_text = glossary_mod.to_text
    counts = {"n": 0}
    def counting_to_text(*a, **kw):
        counts["n"] += 1
        return real_to_text(*a, **kw)
    monkeypatch.setattr(glossary_mod, "to_text", counting_to_text)

    from pipeline.reporter import Reporter
    process_volume("CacheTest", "Vol.1", cfg, reporter=Reporter())

    full_md = Path(cfg["chemins"]["build"]) / "CacheTest" / "Vol.1" / "CacheTest_Vol.1.md"
    assert full_md.exists()
    # Le terminologue simulé ne signale jamais rien de nouveau (cf. _install_counting_agent) :
    # sans le cache, to_text serait appelé une fois PAR BLOC EN PLUS des quelques appels
    # une-fois-par-chapitre/volume déjà légitimes (soit 8+ ici, cf. max_block_chars=40) ;
    # avec le cache, un seul appel dans la boucle (le premier bloc), peu importe le nombre
    # de blocs — le total reste donc borné par les appels hors-boucle, pas par `n`.
    assert counts["n"] <= 5


def test_extract_glossary_resumes_from_checkpoint(tmp_path, monkeypatch):
    """La reprise de --extract-glossary : un bloc déjà en cache est re-mergé sans
    rappeler le LLM, et les checkpoints sont purgés après un run complet."""
    import yaml
    from pathlib import Path
    from pipeline import orchestrator as orch
    from pipeline import agents as agents_mod
    from pipeline.reporter import Reporter
    from pipeline.control import StopRequested

    root = Path(__file__).resolve().parent.parent
    src = tmp_path / "sources" / "GT" / "Vol.1" / "FR"
    src.mkdir(parents=True)
    (src / "c.txt").write_text("Chapitre 1\n\n" + "Feodor marcha. " * 150, encoding="utf-8")

    cfg = yaml.safe_load(open(root / "config.yaml", encoding="utf-8"))
    cfg["options"]["dry_run"] = False
    cfg["decoupage"]["detection"] = "structure"
    cfg["chemins"]["sources"] = str(tmp_path / "sources")
    cfg["chemins"]["build"] = str(tmp_path / "build")
    cfg["chemins"]["style_guide"] = str(root / "style_guide.md")
    cfg["chemins"]["prompts"] = str(root / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    cfg.setdefault("langues", {})["packs"] = str(root / "langues")
    cfg["langues"]["optimiser_apres_terminologie"] = False
    cfg["llm"]["endpoints"] = {}
    cfg["modeles"] = {n: "m" for n in
                      ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]}

    calls = {"n": 0}
    def fake_run(self, user, dry_payload="", max_tokens=None, temperature=None):
        calls["n"] += 1
        return "- Feodor [masculin] — personnage."
    monkeypatch.setattr(agents_mod.Agent, "run", fake_run)

    class _F:
        def __init__(self, *a, **k):
            self.stats = {"tokens_generes": 0, "appels": 0, "temps_generation": 0.0,
                          "retries": 0, "vides_persistants": 0}
    orig = agents_mod.build_agents
    monkeypatch.setattr(orch, "build_agents", lambda c, llm, dry_run=False: orig(c, _F(), dry_run=dry_run))

    # 1er run : stop dès le 1er bloc
    monkeypatch.setattr(orch, "should_stop", lambda bd: True)
    with pytest.raises(StopRequested):
        orch.run_extract_glossary("GT", "Vol.1", cfg, reporter=Reporter())
    n_after_first = calls["n"]
    assert n_after_first >= 1

    # 2e run : reprise, plus aucun stop → doit finir SANS rappeler le LLM sur le bloc caché
    monkeypatch.setattr(orch, "should_stop", lambda bd: False)
    orch.run_extract_glossary("GT", "Vol.1", cfg, reporter=Reporter())
    assert calls["n"] == n_after_first        # 0 appel supplémentaire (repris du cache)
    # checkpoints purgés après complétion
    assert not (tmp_path / "build" / "GT" / "Vol.1" / ".checkpoints_glossaire").exists()


def test_extract_glossary_skips_optimization_on_resumed_chapter(tmp_path, monkeypatch):
    """Régression : à la reprise, un chapitre déjà terminé ne doit PAS relancer
    l'optimisation du glossaire (appel LLM coûteux) — il est sauté intégralement."""
    import yaml
    from pathlib import Path
    from pipeline import orchestrator as orch
    from pipeline import agents as agents_mod
    from pipeline.reporter import Reporter
    from pipeline.control import StopRequested

    root = Path(__file__).resolve().parent.parent
    src = tmp_path / "sources" / "OT" / "Vol.1" / "FR"
    src.mkdir(parents=True)
    (src / "c.txt").write_text(
        "Chapitre 1\n\n" + "Feodor marcha. " * 80 + "\n\n"
        "Chapitre 2\n\n" + "Tiat courut. " * 80, encoding="utf-8")

    cfg = yaml.safe_load(open(root / "config.yaml", encoding="utf-8"))
    cfg["options"]["dry_run"] = False
    cfg["decoupage"]["detection"] = "structure"
    cfg["chemins"]["sources"] = str(tmp_path / "sources")
    cfg["chemins"]["build"] = str(tmp_path / "build")
    cfg["chemins"]["style_guide"] = str(root / "style_guide.md")
    cfg["chemins"]["prompts"] = str(root / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    cfg.setdefault("langues", {})["packs"] = str(root / "langues")
    cfg["langues"]["optimiser_apres_terminologie"] = True     # optimisation ACTIVE
    cfg["llm"]["endpoints"] = {}
    cfg["modeles"] = {n: "m" for n in
                      ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]}

    opt_calls = {"n": 0}
    def fake_run(self, user, dry_payload="", max_tokens=None, temperature=None):
        if self.nom == "glossariste":
            opt_calls["n"] += 1
            return dry_payload
        return "- Feodor [masculin] — personnage."
    monkeypatch.setattr(agents_mod.Agent, "run", fake_run)

    class _F:
        def __init__(self, *a, **k):
            self.stats = {"tokens_generes": 0, "appels": 0, "temps_generation": 0.0,
                          "retries": 0, "vides_persistants": 0}
    orig = agents_mod.build_agents
    monkeypatch.setattr(orch, "build_agents", lambda c, llm, dry_run=False: orig(c, _F(), dry_run=dry_run))

    # 1er run : stop après avoir terminé le chapitre 1 (1 bloc + son optim), au bloc du ch.2
    calls = {"n": 0}
    def stop_after_ch1(bd):
        calls["n"] += 1
        return calls["n"] >= 2
    monkeypatch.setattr(orch, "should_stop", stop_after_ch1)
    with pytest.raises(StopRequested):
        orch.run_extract_glossary("OT", "Vol.1", cfg, reporter=Reporter())
    opt_after_first = opt_calls["n"]
    assert opt_after_first == 1     # chapitre 1 optimisé une fois

    # 2e run : reprise → le chapitre 1 est sauté (pas de nouvelle optim pour lui)
    monkeypatch.setattr(orch, "should_stop", lambda bd: False)
    orch.run_extract_glossary("OT", "Vol.1", cfg, reporter=Reporter())
    # Seuls les chapitres 2 (et éventuellement re-optim finale) tournent : le ch.1 n'est PAS
    # ré-optimisé.
    # Sur 2 chapitres, on attend donc 1 (ch1, run1) + 1 (ch2, run2) = 2 optim au total, jamais 3.
    assert opt_calls["n"] == 2


# --------------------------------------------------------------------------- #
# Signature de découpage : le cache d'un étage ne survit pas à un re-partitionnement
# --------------------------------------------------------------------------- #

def test_signature_depend_du_nombre_et_des_longueurs_de_blocs():
    from pipeline.orchestrator import _signature_blocs
    a = _signature_blocs(["aaaa", "bbbb"])
    assert _signature_blocs(["xxxx", "yyyy"]) == a      # seules les LONGUEURS comptent
    assert _signature_blocs(["aaaa", "bbb"]) != a       # frontière déplacée
    assert _signature_blocs(["aaaabbbb"]) != a          # blocs fusionnés
    assert a.startswith("2:")                           # le compte est lisible en clair


def test_sceller_pose_la_signature_sans_jeter_un_cache_existant(tmp_path):
    """Livrer ce garde-fou ne doit invalider AUCUN tome déjà traité : une signature
    absente = checkpoints antérieurs au lot, on les adopte tels quels."""
    from pipeline.orchestrator import _sceller_decoupage, _signature_blocs
    d = tmp_path / "traduction"
    d.mkdir()
    (d / "000.txt").write_text("déjà traduit", encoding="utf-8")
    rep = _WarnRecordingReporter()

    _sceller_decoupage("traduction", d, _signature_blocs(["bloc"]), rep)

    assert (d / "000.txt").exists()
    assert not rep.warn_msgs
    assert (d / "_decoupage.sig").read_text(encoding="utf-8") == _signature_blocs(["bloc"])


def test_sceller_conserve_le_cache_quand_le_decoupage_est_identique(tmp_path):
    from pipeline.orchestrator import _sceller_decoupage, _signature_blocs
    d = tmp_path / "traduction"
    d.mkdir()
    sig = _signature_blocs(["aaaa", "bbbb"])
    (d / "_decoupage.sig").write_text(sig, encoding="utf-8")
    (d / "000.txt").write_text("déjà traduit", encoding="utf-8")
    rep = _WarnRecordingReporter()

    _sceller_decoupage("traduction", d, sig, rep)

    assert (d / "000.txt").exists()
    assert not rep.warn_msgs


def test_sceller_invalide_le_cache_quand_le_decoupage_change(tmp_path):
    from pipeline.orchestrator import _sceller_decoupage, _signature_blocs
    d = tmp_path / "traduction"
    d.mkdir()
    (d / "_decoupage.sig").write_text(_signature_blocs(["a" * 100, "b" * 100]), encoding="utf-8")
    for i in range(2):
        (d / f"{i:03d}.txt").write_text("traduction d'un découpage périmé", encoding="utf-8")
    rep = _WarnRecordingReporter()

    _sceller_decoupage("traduction", d, _signature_blocs(["a" * 50] * 4), rep)

    assert not list(d.glob("*.txt"))                    # les blocs périmés sont jetés
    assert any("découpage modifié (2 → 4 blocs)" in m for m in rep.warn_msgs)


def test_signature_nest_pas_relue_comme_un_bloc(tmp_path):
    """`stagediff._stage_blocks` liste les blocs par `glob("*.txt")` : un marqueur en
    `.txt` s'y ajouterait comme un bloc fantôme en fin de liste (le chiffre trie avant
    l'underscore). D'où l'extension `.sig`."""
    from pipeline.orchestrator import _sceller_decoupage, _signature_blocs
    from pipeline.stagediff import _stage_blocks
    ch = tmp_path / "ch01"
    d = ch / "traduction"
    d.mkdir(parents=True)
    (d / "000.txt").write_text("le seul vrai bloc", encoding="utf-8")
    _sceller_decoupage("traduction", d, _signature_blocs(["bloc"]), _WarnRecordingReporter())

    assert _stage_blocks(ch, "traduction") == ["le seul vrai bloc"]


def test_checkpoints_invalides_si_le_decoupage_change(tmp_path, monkeypatch):
    """Le scénario réel : un run INTERROMPU, repris après un changement de découpage.

    C'est le seul chemin où des checkpoints périmés sont relus — `--from` purge l'étage
    visé et ses suivants, et un chapitre déjà écrit est sauté entièrement. Ici le
    chapitre n'a pas de `.md`, donc tous ses étages rechargent leur cache, indexé par
    NUMÉRO de bloc : sans ce garde-fou, le `000.txt` du découpage fin serait relu comme
    l'unique bloc du découpage grossier, et le chapitre perdrait les trois quarts de son
    texte, en silence et sans un appel LLM."""
    import pipeline.orchestrator as orch
    cfg = _resplit_project(tmp_path, monkeypatch)
    _install_counting_agent(monkeypatch)
    ck = Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"

    # 1er run : découpage FIN, interrompu dès que 2 blocs sont traduits. On pilote l'arrêt
    # sur l'état réel des checkpoints plutôt que sur un compteur d'appels : `should_stop`
    # est aussi consulté par l'étage terminologie, qui tourne avant.
    cfg["decoupage"]["max_block_chars"] = 500
    monkeypatch.setattr(orch, "should_stop",
                        lambda _bd: len(list((ck / "traduction").glob("*.txt"))) >= 2)
    # `process_volume` RATTRAPE StopRequested et rend False (c'est ce que lit `--all`).
    assert process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter()) is False
    assert len(list((ck / "traduction").glob("*.txt"))) == 2      # partiel, comme attendu

    # 2e run : découpage GROSSIER (tout le chapitre en un bloc), reprise sans `--from`.
    monkeypatch.setattr(orch, "should_stop", lambda _bd: False)
    cfg["decoupage"]["max_block_chars"] = 6000
    rep = _WarnRecordingReporter()
    process_volume("Resplit", "Vol.1", cfg, reporter=rep)

    # La signature porte le nombre de blocs du DÉCOUPAGE (4), pas celui des fichiers
    # écrits avant l'arrêt (2). Les deux étages indexés sur ce partitionnement réagissent.
    for etage in ("terminologie", "traduction"):
        assert any(f"[{etage}] découpage modifié (4 → 1 blocs)" in m for m in rep.warn_msgs), \
            rep.warn_msgs
    blocs = sorted((ck / "traduction").glob("*.txt"))
    assert len(blocs) == 1
    # Le bloc unique porte bien TOUT le chapitre — c'est ce que la relecture du
    # checkpoint périmé aurait silencieusement tronqué.
    trad = blocs[0].read_text(encoding="utf-8")
    assert all(f"Paragraphe numéro {i} du chapitre" in trad for i in range(12))


# --------------------------------------------------------------------------- #
# Les signaux DIRECTS du client LLM déclenchent le redécoupage
# --------------------------------------------------------------------------- #

class _FakeAgentAvecRaison(_FakeAgent):
    """Agent dont le client LLM expose une `last_reason`, comme le vrai. La sortie est de
    longueur NORMALE : aucun garde-fou heuristique ne peut la voir — c'est précisément ce
    qui rendait ces échecs invisibles."""

    def __init__(self, outputs, raisons, temperature=0.2):
        super().__init__(outputs, temperature)
        self._raisons = list(raisons)
        self.replis = []
        self.llm = type("_L", (), {"last_reason": None})()

    def run(self, user, dry_payload="", max_tokens=None, temperature=None,
            repli_sans_raisonnement=None, **_):
        self.replis.append(repli_sans_raisonnement)
        out = super().run(user, dry_payload, max_tokens, temperature)
        i = min(len(self.calls) - 1, len(self._raisons) - 1)
        self.llm.last_reason = self._raisons[i]
        return out


_SORTIE_NORMALE = ("Une traduction de longueur parfaitement ordinaire, que ni le compte de "
                   "mots ni le plafond de sortie ne peuvent trouver suspecte.")


def test_troncature_length_est_diagnostiquee_malgre_une_sortie_normale():
    """`finish_reason == "length"` était compté puis le contenu tronqué repartait comme une
    réponse valide. `_ln_emballement` ne le rattrape pas : il compare au `cap` de
    l'appelant, alors que le plafond réel vaut `cap + thinking_budget`."""
    a = _FakeAgentAvecRaison([_SORTIE_NORMALE, _SORTIE_NORMALE], ["troncature", "troncature"])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", _SORTIE_NORMALE, cap=2000, stats=stats)
    assert not ok and reason == "troncature_length"


def test_thinking_overflow_est_diagnostique_sur_une_sortie_non_vide():
    a = _FakeAgentAvecRaison([_SORTIE_NORMALE, _SORTIE_NORMALE],
                             ["thinking_overflow", "thinking_overflow"])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", _SORTIE_NORMALE, cap=2000, stats=stats)
    assert not ok and reason == "thinking_overflow"


def test_la_raison_est_relevee_apres_CHAQUE_appel():
    """Le client remet `last_reason` à None à chaque `chat()`, et ce moteur peut appeler
    deux fois. La lire une seule fois après coup ne décrirait que le SECOND appel."""
    a = _FakeAgentAvecRaison([_SORTIE_NORMALE, _SORTIE_NORMALE], ["troncature", None])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", _SORTIE_NORMALE, cap=2000, stats=stats)
    # 1er appel tronqué → retry ; 2e appel sain → récupéré. Le moteur a donc bien vu deux
    # raisons différentes, ce qu'une lecture unique après coup rendait impossible.
    assert ok and reason is None and len(a.calls) == 2
    assert stats["recupere_par_retry"] == 1


def test_ni_troncature_ni_thinking_overflow_ne_retombent_en_langue_source():
    """Un texte tronqué reste du français exploitable : le repli sur `pivot_block`
    réinjecterait la langue source, ce qui serait pire."""
    from pipeline.orchestrator import _TRAD_GARBAGE
    assert "troncature_length" not in _TRAD_GARBAGE
    assert "thinking_overflow" not in _TRAD_GARBAGE


def test_troncature_length_declenche_le_redecoupage(tmp_path, monkeypatch):
    """Bout en bout : un bloc dont le client signale une troncature est coupé en deux et
    relancé, alors que sa sortie n'a rien de suspect pour les garde-fous heuristiques."""
    import pipeline.agents as agents_mod
    cfg = _resplit_project(tmp_path, monkeypatch)
    vus = {"gros": 0, "petits": 0}

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None,
             repli_sans_raisonnement=None, **_):
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        if self.nom == "traducteur":
            if len(dry_payload) > 900:            # le bloc entier : tronqué
                vus["gros"] += 1
                self.llm.last_reason = "troncature"
                return f"[fr] {dry_payload[:200]}"
            vus["petits"] += 1                    # les moitiés : saines
            self.llm.last_reason = None
        return f"[fr] {dry_payload}"

    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    rep = _WarnRecordingReporter()
    process_volume("Resplit", "Vol.1", cfg, reporter=rep)

    assert vus["gros"] == 2 and vus["petits"] == 2        # bloc + retry, puis 2 moitiés
    assert any("redécoupage en 2 et relance" in m for m in rep.warn_msgs)
    trad = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"
            / "traduction" / "000.txt").read_text(encoding="utf-8")
    assert trad.count("[fr]") == 2 and "AMBIGU" not in trad


def test_le_repli_sans_raisonnement_nest_ouvert_quen_dernier_recours(tmp_path, monkeypatch):
    """Tant que le bloc reste redécoupable, le client a INTERDICTION de se rabattre sur une
    réponse non raisonnée : elle masquerait l'échec et nous priverait du redécoupage."""
    import pipeline.agents as agents_mod
    cfg = _resplit_project(tmp_path, monkeypatch)
    vus = []

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None,
             repli_sans_raisonnement=None, **_):
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        if self.nom == "traducteur":
            vus.append((len(dry_payload), repli_sans_raisonnement))
        return f"[fr] {dry_payload}"

    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    # Le bloc entier (> redecoupage_taille_min) est redécoupable → repli FERMÉ.
    assert vus and all(repli is False for taille, repli in vus if taille > 900)


def test_bloc_non_redecoupable_est_conserve_et_marque_ambigu(tmp_path, monkeypatch):
    """Quand plus rien n'est redécoupable, la sortie obtenue sans raisonnement est
    CONSERVÉE (elle n'est pas dans `_TRAD_GARBAGE` : réinjecter la langue source serait
    pire) mais SIGNALÉE — elle n'a pas bénéficié du raisonnement.

    Vérifie au passage qu'il n'existe pas de chemin « repli accepté en silence » :
    `thinking_overflow` étant un motif à part entière, une telle sortie est toujours
    diagnostiquée et ne peut jamais ressortir comme une traduction ordinaire."""
    import pipeline.agents as agents_mod
    cfg = _resplit_project(tmp_path, monkeypatch)
    cfg["garde_fous"]["redecoupage_sur_echec"] = False     # plus rien n'est redécoupable

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None,
             repli_sans_raisonnement=None, **_):
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        if self.nom == "traducteur":
            self.llm.last_reason = "thinking_overflow"
        return f"[fr] {dry_payload}"

    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    rep = _WarnRecordingReporter()
    process_volume("Resplit", "Vol.1", cfg, reporter=rep)

    trad = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"
            / "traduction" / "000.txt").read_text(encoding="utf-8")
    assert "AMBIGU: budget de raisonnement épuisé avant la réponse finale" in trad
    assert "traduction conservée (à vérifier)" in trad
    assert "Paragraphe numéro 0 du chapitre" in trad          # rien n'est retombé en source
    assert any("budget de raisonnement épuisé" in m for m in rep.warn_msgs)


# --------------------------------------------------------------------------- #
# Pivot en écriture non latine : consigne de romanisation + lectures (furigana)
# --------------------------------------------------------------------------- #

def _projet_pivot_jp(tmp_path, monkeypatch):
    """Projet à source JAPONAISE unique — le cas de roman A : `others` est vide, donc
    le terminologue n'a AUCUNE forme latine sous les yeux."""
    monkeypatch.chdir(tmp_path)
    corps = "\n\n".join(
        "彼は塔の階層を見上げ、七堕の気配を探った。夜の帳が下りるまでに封印を終えねばならない。"
        for _ in range(3))
    src = tmp_path / "sources" / "PivotJP" / "Vol.1" / "JAP"
    src.mkdir(parents=True)
    (src / "v.txt").write_text(f"Chapitre 1\n\n{corps}", encoding="utf-8")

    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(open(root / "config.yaml", encoding="utf-8"))
    cfg["options"]["dry_run"] = False
    cfg["decoupage"]["detection"] = "structure"
    cfg["chemins"]["sources"] = str(tmp_path / "sources")
    cfg["chemins"]["build"] = str(tmp_path / "build")
    cfg["chemins"]["style_guide"] = str(root / "style_guide.md")
    cfg["chemins"]["prompts"] = str(root / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    cfg.setdefault("langues", {})["packs"] = str(root / "langues")
    cfg["langues"]["optimiser_apres_terminologie"] = False
    cfg["llm"] = {"base_url": "http://localhost:1234/v1", "api_key": "test", "timeout": 60,
                  "max_retries": 1, "extra_directive": "", "think": False, "endpoints": {}}
    cfg["modeles"] = {n: "qwen/qwen3.5" for n in
                      ["terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste"]}
    # Gabarits : NON renseignés, donc servis par le pack de langue cible — c'est le
    # chemin réel depuis que `langues/fr/templates/` les porte. Les pointer à la main
    # testerait un chemin que plus personne n'emprunte.
    return cfg


def _capturer_prompts_terminologue(monkeypatch):
    import pipeline.agents as agents_mod
    vus: list[str] = []

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None, **_):
        if self.nom == "terminologue":
            vus.append(user_content)
            return "- (rien à signaler)"
        return f"[fr] {dry_payload}"
    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    return vus


def test_consigne_de_romanisation_injectee_sur_un_pivot_japonais(tmp_path, monkeypatch):
    cfg = _projet_pivot_jp(tmp_path, monkeypatch)
    vus = _capturer_prompts_terminologue(monkeypatch)
    process_volume("PivotJP", "Vol.1", cfg, reporter=_WarnRecordingReporter())
    assert vus, "le terminologue n'a jamais été appelé"
    assert all("LANGUE DU BLOC" in p and "Hepburn" in p for p in vus)


def test_consigne_absente_sur_un_pivot_latin(tmp_path, monkeypatch):
    """Le prompt système est partagé avec la brique manga et relu à chaque bloc de chaque
    œuvre : une règle de romanisation n'a rien à y faire quand le pivot est déjà latin."""
    cfg = _resplit_project(tmp_path, monkeypatch)
    vus = _capturer_prompts_terminologue(monkeypatch)
    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())
    assert vus
    assert not any("LANGUE DU BLOC" in p or "Hepburn" in p for p in vus)


def test_les_lectures_du_bloc_sont_injectees(tmp_path, monkeypatch):
    """Seules les gloses dont la graphie apparaît dans CE bloc : le lexique d'un tome fait
    ~2 000 entrées, un bloc n'en concerne que quelques dizaines."""
    import pipeline.sources as sources_mod
    cfg = _projet_pivot_jp(tmp_path, monkeypatch)
    vrai_scan = sources_mod.scan_volume

    def scan_avec_lectures(vol_dir, config, build_dir):
        plan = vrai_scan(vol_dir, config, build_dir)
        plan.langs["jp"].lectures = {"七堕": "ナナエ", "封印": "ふういん",
                                     "麒麟": "きりん"}      # absent du bloc
        return plan
    monkeypatch.setattr("pipeline.orchestrator.scan_volume", scan_avec_lectures)
    vus = _capturer_prompts_terminologue(monkeypatch)
    process_volume("PivotJP", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    assert vus
    prompt = vus[0]
    assert "LECTURES (furigana)" in prompt
    assert "- 七堕 = ナナエ" in prompt and "- 封印 = ふういん" in prompt
    assert "麒麟" not in prompt          # pas dans le bloc → pas envoyé


def test_pas_de_section_lectures_sans_furigana(tmp_path, monkeypatch):
    """Une source japonaise en .txt n'a pas de ruby : la consigne reste, la section non."""
    cfg = _projet_pivot_jp(tmp_path, monkeypatch)
    vus = _capturer_prompts_terminologue(monkeypatch)
    process_volume("PivotJP", "Vol.1", cfg, reporter=_WarnRecordingReporter())
    assert vus and "LANGUE DU BLOC" in vus[0]
    assert "LECTURES (furigana)" not in vus[0]


# --------------------------------------------------------------------------- #
# Motif « CJK résiduel » : la réponse existe, mais elle n'est pas en français
# --------------------------------------------------------------------------- #

_FR_AVEC_JP = "Comme prévu. 天茜 soupira et se leva, puis marcha vers la porte du fond."


def test_cjk_residuel_detecte_un_nom_reste_en_japonais():
    """Le registre light novel n'avait AUCUN contrôle de ce genre — un chapitre entier en
    japonais ressortait « ok »."""
    a = _FakeAgent([_FR_AVEC_JP, _FR_AVEC_JP])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", "entrée de référence assez longue ici",
                                         cap=2000, stats=stats, cjk_seuil=1)
    assert not ok and reason == "cjk_residuel"


def test_cjk_residuel_tolere_une_forme_autorisee_par_le_glossaire():
    """Bannir une forme que le glossaire autorise (`traduire: false`) ou n'a pas encore
    romanisée ferait boucler le retry sur une sortie pourtant CONFORME au glossaire qu'on a
    soi-même fourni au traducteur."""
    a = _FakeAgent([_FR_AVEC_JP])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", "entrée de référence assez longue ici",
                                         cap=2000, stats=stats,
                                         cjk_autorise=("天茜",), cjk_seuil=1)
    assert ok and reason is None


def test_cjk_residuel_ignore_la_ponctuation_japonaise():
    """`tokens.CJK` (budget) couvre `「」『』…` : s'en servir ici recréerait le faux positif
    déjà payé côté manga sur une bulle ne contenant que des parenthèses pleine chasse."""
    a = _FakeAgent(["Il dit : « bonjour »… puis （sourit）, et 『referma』 la porte."])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", "entrée de référence assez longue ici",
                                         cap=2000, stats=stats, cjk_seuil=1)
    assert ok and reason is None


def test_cjk_residuel_ignore_les_marqueurs_et_commentaires():
    """Un nom de fichier média peut porter du CJK, et un `<!-- AMBIGU: … -->` peut citer la
    graphie source : ni l'un ni l'autre n'est du texte rendu au lecteur."""
    sortie = ("Une traduction parfaitement française et de longueur normale ici.\n\n"
              "<!-- IMG: media/千万丈塔.jpg -->\n\n<!-- AMBIGU: 天茜 douteux -->")
    a = _FakeAgent([sortie])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", "entrée de référence assez longue ici",
                                         cap=2000, stats=stats, cjk_seuil=1)
    assert ok and reason is None


def test_cjk_seuil_zero_desactive_le_motif():
    a = _FakeAgent([_FR_AVEC_JP])
    stats = {}
    _, ok, reason = _try_with_temp_retry(a, "u", "entrée de référence assez longue ici",
                                         cap=2000, stats=stats, cjk_seuil=0)
    assert ok and reason is None


def test_cjk_residuel_ne_redecoupe_pas_et_ne_retombe_pas_en_langue_source():
    """Couper un bloc en deux ne fait pas traduire un nom propre : les deux moitiés
    reviendraient en japonais et le coût doublerait. Et retomber sur le pivot remplacerait
    un français à noms japonais par du japonais à 100 % — une aggravation."""
    from pipeline.orchestrator import _TRAD_GARBAGE
    assert "cjk_residuel" not in _RESPLIT_REASONS
    assert "cjk_residuel" not in _TRAD_GARBAGE


def test_le_traducteur_ne_recoit_pas_les_entrees_non_romanisees(tmp_path, monkeypatch):
    """Bout en bout : le glossaire injecté au TRADUCTEUR masque l'entrée non romanisée,
    celui injecté au TERMINOLOGUE la montre."""
    import pipeline.agents as agents_mod
    cfg = _resplit_project(tmp_path, monkeypatch)
    glo = Path(cfg["chemins"]["sources"]) / "Resplit" / "glossaire.yaml"
    glo.parent.mkdir(parents=True, exist_ok=True)
    glo.write_text(
        "personnages:\n"
        "  - nom: 天茜\n    a_romaniser: true\n    termes_source: ['天茜']\n"
        "    description: Un sorcier.\n"
        "  - nom: Matsurika\n    termes_source: ['祭花']\n    description: Une garde.\n",
        encoding="utf-8")
    vus: dict[str, list[str]] = {"traducteur": [], "terminologue": []}

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None, **_):
        if self.nom in vus:
            vus[self.nom].append(user_content)
        return "- (rien à signaler)" if self.nom == "terminologue" else f"[fr] {dry_payload}"
    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    assert vus["traducteur"] and vus["terminologue"]
    assert all("天茜" not in p for p in vus["traducteur"])
    assert all("Matsurika" in p for p in vus["traducteur"])
    assert any("天茜" in p for p in vus["terminologue"])


def test_le_rapport_liste_les_entrees_a_romaniser(tmp_path, monkeypatch):
    cfg = _resplit_project(tmp_path, monkeypatch)
    glo = Path(cfg["chemins"]["sources"]) / "Resplit" / "glossaire.yaml"
    glo.parent.mkdir(parents=True, exist_ok=True)
    glo.write_text("personnages:\n  - nom: 天茜\n    a_romaniser: true\n"
                   "    termes_source: ['天茜']\n    description: Un sorcier.\n",
                   encoding="utf-8")
    _install_counting_agent(monkeypatch)
    rep = _WarnRecordingReporter()
    process_volume("Resplit", "Vol.1", cfg, reporter=rep)

    rapport = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / "RAPPORT.md").read_text(
        encoding="utf-8")
    assert "Entrées de glossaire sans rendu français" in rapport
    assert "天茜" in rapport
    assert any("sans rendu français" in m for m in rep.warn_msgs)


# --------------------------------------------------------------------------- #
# Traces : aucun bloc dégradé, aucun dimensionnement, ne passe en silence
# --------------------------------------------------------------------------- #

def test_le_rapport_annonce_le_dimensionnement_du_decoupage(tmp_path, monkeypatch):
    """Trois chiffres — densité, taille de bloc, plafonds — sans lesquels « ~22000 tok
    générés » dans perf.log reste une énigme."""
    cfg = _resplit_project(tmp_path, monkeypatch)
    cfg["decoupage"]["max_block_tokens"] = 2200
    _install_counting_agent(monkeypatch)
    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())

    rapport = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / "RAPPORT.md").read_text(
        encoding="utf-8")
    assert "Découpage :" in rapport
    assert "car./bloc" in rapport and "densité" in rapport and "budget 2200 tok" in rapport


def test_la_ligne_de_decoupage_dit_quand_le_budget_en_tokens_est_absent(tmp_path, monkeypatch):
    cfg = _resplit_project(tmp_path, monkeypatch)
    cfg["decoupage"].pop("max_block_tokens", None)
    _install_counting_agent(monkeypatch)
    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())
    rapport = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / "RAPPORT.md").read_text(
        encoding="utf-8")
    assert "en caractères seuls" in rapport


def test_le_pivot_sans_source_de_reference_est_signale(tmp_path, monkeypatch):
    """Ce n'est pas un défaut, mais c'est un fait de run : le traducteur ne peut recouper
    avec rien. `others` vide est justement le cas de roman A."""
    cfg = _resplit_project(tmp_path, monkeypatch)      # une seule langue : FR
    _install_counting_agent(monkeypatch)
    rep = _WarnRecordingReporter()
    process_volume("Resplit", "Vol.1", cfg, reporter=rep)
    assert any("aucune source de référence" in m for m in rep.warn_msgs)


def test_la_saturation_du_plafond_de_sortie_est_signalee(tmp_path, monkeypatch):
    """Le plafond DUR de `out_cap` n'est atteignable qu'avec une langue dense. Le voir
    saturer dit que `max_block_tokens` est mal dimensionné — c'est le témoin qui aurait
    rendu le défaut visible dès le premier chapitre du Vol.1."""
    import pipeline.orchestrator as orch
    cfg = _resplit_project(tmp_path, monkeypatch)
    _install_counting_agent(monkeypatch)
    # On force la saturation sans avoir besoin d'un vrai texte japonais.
    monkeypatch.setattr(orch, "_out_cap", lambda *a, **k: orch.quality.CEIL_DEFAUT)
    rep = _WarnRecordingReporter()
    process_volume("Resplit", "Vol.1", cfg, reporter=rep)

    rapport = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / "RAPPORT.md").read_text(
        encoding="utf-8")
    assert "Plafond de sortie saturé" in rapport
    assert "max_block_tokens" in rapport


def test_pas_dalerte_de_saturation_sur_un_run_sain(tmp_path, monkeypatch):
    cfg = _resplit_project(tmp_path, monkeypatch)
    _install_counting_agent(monkeypatch)
    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())
    rapport = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / "RAPPORT.md").read_text(
        encoding="utf-8")
    assert "Plafond de sortie saturé" not in rapport
    assert "Japonais/chinois résiduel : aucun bloc concerné" in rapport


def test_le_titre_en_cache_est_purge_par_from_traduction(tmp_path, monkeypatch):
    """`chNN/title.txt` vit à CÔTÉ des dossiers d'étape, pas dedans : `_ck` ne pouvait
    jamais le purger, et un titre issu du run précédent survivait à `--from traduction`.
    Sur un pivot japonais, cela voulait dire un titre resté en japonais traversant toutes
    les relances.

    On vérifie la PURGE (le fichier périmé disparaît), pas la régénération : celle-ci
    demande un vrai appel LLM, hors du périmètre de ce test."""
    cfg = _resplit_project(tmp_path, monkeypatch)
    _install_counting_agent(monkeypatch)
    ck = Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"

    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())
    titre = ck / "title.txt"
    titre.write_text("Titre périmé du run précédent", encoding="utf-8")

    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter(),
                   restart_from="traduction")
    assert not titre.exists() or titre.read_text(encoding="utf-8").strip() !=         "Titre périmé du run précédent"


def test_le_titre_en_cache_survit_a_une_reprise_qui_ne_retraduit_pas(tmp_path, monkeypatch):
    """Non-régression : le cache de titre reste un cache tant que la traduction n'est pas
    refaite — c'est un appel LLM de moins par chapitre à chaque reprise."""
    cfg = _resplit_project(tmp_path, monkeypatch)
    _install_counting_agent(monkeypatch)
    ck = Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"
    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter())
    (ck / "title.txt").write_text("Titre conservé", encoding="utf-8")
    process_volume("Resplit", "Vol.1", cfg, reporter=_WarnRecordingReporter(),
                   restart_from="mise_en_page")
    assert (ck / "title.txt").read_text(encoding="utf-8").strip() == "Titre conservé"


# --------------------------------------------------------------------------- #
# Un timeout est un échec de BLOC, pas la mort du tome
# --------------------------------------------------------------------------- #

def test_timeout_est_diagnostique_AVANT_vide():
    """LE piège. Un timeout ne rend rien, donc une sortie vide — et `vide` appartient à
    `_TRAD_GARBAGE`, qui fait retomber le bloc en LANGUE SOURCE. Diagnostiquer « vide » un
    bloc qui n'a jamais été soumis correctement le ferait ressortir en japonais."""
    from pipeline.orchestrator import _MOTIFS_LN, _TRAD_GARBAGE
    noms = [n for n, _ in _MOTIFS_LN]
    assert noms.index("timeout") < noms.index("vide")
    assert "timeout" not in _TRAD_GARBAGE
    assert "vide" in _TRAD_GARBAGE          # l'asymétrie qui rend l'ordre nécessaire

    a = _FakeAgentAvecRaison(["", ""], ["timeout", "timeout"])
    _, ok, reason = _try_with_temp_retry(a, "u", "entrée de référence assez longue ici",
                                         cap=2000, stats={})
    assert not ok and reason == "timeout"


def test_timeout_declenche_le_redecoupage_et_ne_tue_pas_le_tome(tmp_path, monkeypatch):
    """Bout en bout : le bloc entier expire, ses deux moitiés passent. Couper est ici un
    remède CAUSAL — deux moitiés génèrent deux fois moins."""
    import pipeline.agents as agents_mod
    cfg = _resplit_project(tmp_path, monkeypatch)
    vus = {"gros": 0, "petits": 0}

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None, **_):
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        if self.nom == "traducteur":
            if len(dry_payload) > 900:            # le bloc entier : expire
                vus["gros"] += 1
                self.llm.last_reason = "timeout"
                return ""
            vus["petits"] += 1
            self.llm.last_reason = None
        return f"[fr] {dry_payload}"

    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    rep = _WarnRecordingReporter()
    process_volume("Resplit", "Vol.1", cfg, reporter=rep)          # ne lève pas

    assert vus["gros"] == 2 and vus["petits"] == 2
    assert any("redécoupage en 2 et relance" in m for m in rep.warn_msgs)
    trad = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / ".checkpoints" / "ch01"
            / "traduction" / "000.txt").read_text(encoding="utf-8")
    assert trad.count("[fr]") == 2
    # Et surtout : le texte n'est PAS reparti en langue source.
    assert "langue source" not in trad


def test_timeouts_en_serie_arretent_proprement_le_run(tmp_path, monkeypatch):
    """Un timeout isolé se redécoupe ; N d'affilée, c'est le serveur qui ne répond plus.
    Continuer remplirait le tome de langue source, chaque bloc payé au prix d'un timeout
    complet. L'arrêt doit être PROPRE : rapport partiel, checkpoints intacts."""
    import pipeline.agents as agents_mod
    cfg = _resplit_project(tmp_path, monkeypatch)
    cfg["garde_fous"]["abandon_apres_timeouts_consecutifs"] = 1
    cfg["garde_fous"]["redecoupage_sur_echec"] = False

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None, **_):
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        if self.nom == "traducteur":
            self.llm.last_reason = "timeout"
            return ""
        return f"[fr] {dry_payload}"

    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    rep = _WarnRecordingReporter()
    assert process_volume("Resplit", "Vol.1", cfg, reporter=rep) is False
    assert any("blocs expirés d'affilée" in m for m in rep.warn_msgs)
    rapport = (Path(cfg["chemins"]["build"]) / "Resplit" / "Vol.1" / "RAPPORT.md")
    assert rapport.exists() and "partiel" in rapport.read_text(encoding="utf-8")


def test_un_timeout_isole_ne_declenche_pas_labandon(tmp_path, monkeypatch):
    """Non-régression du garde-fou : le compteur doit se remettre à zéro dès qu'un bloc
    aboutit, sinon un tome long finirait par s'arrêter sur des incidents sans rapport."""
    import pipeline.agents as agents_mod
    cfg = _resplit_project(tmp_path, monkeypatch)
    cfg["garde_fous"]["abandon_apres_timeouts_consecutifs"] = 2
    etat = {"n": 0}

    def fake(self, user_content, dry_payload="", max_tokens=None, temperature=None, **_):
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        if self.nom == "traducteur":
            etat["n"] += 1
            self.llm.last_reason = "timeout" if etat["n"] == 1 else None
            if etat["n"] == 1:
                return ""
        return f"[fr] {dry_payload}"

    monkeypatch.setattr(agents_mod.Agent, "run", fake)
    rep = _WarnRecordingReporter()
    assert process_volume("Resplit", "Vol.1", cfg, reporter=rep) is True
    assert not any("d'affilée" in m for m in rep.warn_msgs)
