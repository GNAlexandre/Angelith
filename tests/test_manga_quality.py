# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Garde-fous de la traduction manga : plafond de sortie, registre de motifs d'échec,
retry à température corrigée.

Avant ce lot, la traduction manga n'avait AUCUN garde-fou : un appel LLM par page, sans
`max_tokens`, sans diagnostic, sans retry, sans rapport. Le plus grave était silencieux —
voir `bulles_manquantes`.
"""
import pytest

from manga import quality_manga as q


def _sortie(n, prefixe="Réplique"):
    return "\n".join(f"{i}. {prefixe} {i}" for i in range(1, n + 1))


# --------------------------------------------------------------------------- #
# Plafond de sortie
# --------------------------------------------------------------------------- #

def test_bubbles_cap_calee_sur_les_mesures_du_tome():
    """Page à 11 bulles : ~788 tokens, soit ~4,4× la production réellement observée."""
    numbered = "\n".join(f"{i}. こんにちは、元気ですか" for i in range(1, 12))
    cap = q.bubbles_cap(numbered, 11)
    assert 700 <= cap <= 900, cap


def test_bubbles_cap_a_un_plancher_et_un_plafond():
    assert q.bubbles_cap("", 0) == 384
    enorme = "\n".join(f"{i}. " + "あ" * 400 for i in range(1, 40))
    assert q.bubbles_cap(enorme, 39) == 2048


def test_bubbles_cap_croit_avec_le_nombre_de_bulles():
    petit = q.bubbles_cap(_sortie(2), 2)
    grand = q.bubbles_cap(_sortie(12), 12)
    assert grand > petit


def test_bubbles_cap_suit_aussi_la_longueur_du_japonais():
    """Second estimateur : proportionnel au japonais OCR, pour une page peu peuplée mais
    très bavarde."""
    court = q.bubbles_cap("1. はい", 1)
    long = q.bubbles_cap("1. " + "あ" * 600, 1)
    assert long > court


# --------------------------------------------------------------------------- #
# Registre de motifs
# --------------------------------------------------------------------------- #

def test_une_sortie_correcte_ne_declenche_aucun_motif():
    assert q.diagnostiquer(_sortie(3), n=3, cap=500, sources=["あ", "い", "う"]) is None


def test_motif_vide():
    assert q.diagnostiquer("   \n  ", n=3, cap=500) == "vide"


def test_motif_bulles_manquantes_est_LE_defaut_dominant():
    """L'échec le plus dangereux, jusqu'ici totalement silencieux.

    `_parse_translations` exige `len(numbered) >= n` pour faire confiance à la numérotation ;
    sinon il retombe sur `(lines + [""] * n)[:n]`. Si le modèle émet une phrase
    d'introduction sans numéroter, TOUTE la page est décalée d'un cran et chaque réplique
    atterrit dans la mauvaise bulle. C'est pire qu'une page vide : ça a l'air terminé."""
    sortie = ("Voici les traductions des bulles :\n"
              "Bonjour à tous\nComment allez-vous\nTrès bien merci")
    assert q.diagnostiquer(sortie, n=3, cap=500) == "bulles_manquantes"


def test_bulles_manquantes_sur_numerotation_partielle():
    assert q.diagnostiquer("1. Un\n2. Deux", n=4, cap=500) == "bulles_manquantes"


def test_une_intro_AVEC_numerotation_complete_passe():
    """Une phrase d'introduction n'est pas un problème en soi : ce qui compte, c'est que la
    numérotation soit complète — `_parse_translations` s'y fie alors et ignore l'intro."""
    sortie = "Voici les traductions :\n1. Bonjour\n2. Ça va ?\n3. Oui"
    assert q.diagnostiquer(sortie, n=3, cap=500) is None


def test_motif_japonais_residuel():
    sortie = "1. Bonjour\n2. こんにちは\n3. Oui"
    assert q.diagnostiquer(sortie, n=3, cap=500) == "japonais_residuel"


def test_japonais_residuel_ignore_la_ponctuation_latine():
    sortie = "1. Bonjour !\n2. « Ah… »\n3. Oui — bien sûr"
    assert q.diagnostiquer(sortie, n=3, cap=500) is None


def test_motif_repetition():
    sortie = "1. Je ne sais pas\n2. Je ne sais pas\n3. Je ne sais pas\n4. Autre"
    assert q.diagnostiquer(sortie, n=4, cap=5000) == "repetition"


def test_deux_repliques_identiques_ne_suffisent_pas():
    """Deux répliques identiques arrivent légitimement dans un dialogue."""
    sortie = "1. Oui\n2. Oui\n3. Vraiment ?"
    assert q.diagnostiquer(sortie, n=3, cap=5000) is None


def test_motif_emballement():
    sortie = _sortie(6, "Une réplique particulièrement longue et bavarde sans fin")
    cap = 40
    assert q.diagnostiquer(sortie, n=6, cap=cap) == "emballement"


def test_motif_bulle_trop_longue():
    """Le japonais est dense : une traduction fait légitimement plusieurs fois la longueur
    estimée de sa source. Au-delà de 3× (avec plancher), c'est du bavardage ajouté — et un
    débordement de bulle garanti."""
    sortie = ("1. " + "Un très long monologue ajouté de toutes pièces par le modèle, "
              "qui n'a aucun rapport avec la brièveté de la bulle source. " * 3)
    assert q.diagnostiquer(sortie, n=1, cap=100000, sources=["はい"]) == "bulle_trop_longue"


def test_bulle_trop_longue_tolere_une_expansion_normale():
    assert q.diagnostiquer("1. Bonjour, comment allez-vous aujourd'hui ?", n=1,
                           cap=5000, sources=["こんにちは、お元気ですか"]) is None


def test_bulle_trop_longue_sans_sources_est_inactif():
    assert q.diagnostiquer("1. " + "x " * 200, n=1, cap=100000) is None


# --------------------------------------------------------------------------- #
# `bulle_trop_courte` — le symétrique qui manquait (lot 15, L7.8)
#
# Les six autres motifs sont morphologiques ou statistiques, et AUCUN ne détectait une
# réplique abrégée. Or la pression est structurellement dans le sens de l'abrègement : le
# prompt injecte un budget de caractères par bulle SANS aucune contrepartie sur la fidélité.
# On demandait d'être court, et on ne vérifiait jamais qu'on n'avait pas coupé.
# --------------------------------------------------------------------------- #

def test_motif_bulle_trop_courte():
    """L'exemple du plan : une bulle japonaise de 40 caractères rendue par « Ouais. » passait
    les six autres motifs — elle n'est pas vide, elle est numérotée, elle est en français,
    elle est unique, et elle est courte."""
    assert q.diagnostiquer("1. Ouais.", n=1, cap=5000,
                           sources=["あ" * 40], langue="jp") == "bulle_trop_courte"


def test_une_traduction_serree_mais_fidèle_passe():
    """Le ratio est calé sous le 2ᵉ centile du corpus (médiane 0,65 en source CJK) : il ne
    doit se déclencher que sur une réplique franchement amputée."""
    fidele = ("1. Je ne pensais vraiment pas te revoir ici un jour, surtout pas "
              "après tout ce temps.")

    assert q.diagnostiquer(fidele, n=1, cap=5000,
                           sources=["あ" * 40], langue="jp") is None


def test_le_seuil_depend_de_la_langue_source():
    """Le japonais est dense : un ratio naïf produirait des faux positifs en masse d'un
    côté, ou un plancher inatteignable de l'autre. Mesuré sur `build/` : médiane 0,65 en
    source CJK contre 1,06 en source latine."""
    court = "1. Ouais."
    source_latine = ["Yeah, I never thought I would see you here again after all this time"]

    assert q.diagnostiquer(court, n=1, cap=5000, sources=source_latine,
                           langue="en") == "bulle_trop_courte"
    assert q.RATIO_COURT["cjk"] < q.RATIO_COURT["latin"]


def test_une_source_courte_ne_declenche_rien():
    """Une bulle de deux caractères rendue par un mot est parfaitement normale, et c'est le
    tiers du corpus."""
    assert q.diagnostiquer("1. Oui.", n=1, cap=5000, sources=["はい"], langue="jp") is None


def test_une_bulle_vide_n_est_pas_une_bulle_courte():
    """Elle est déjà signalée par `bulles_manquantes` et reprise par le rattrapage unitaire.
    La compter ici la ferait rapporter deux fois sous deux noms différents."""
    motifs = q.diagnostiquer_tous("1. ", n=1, cap=5000, sources=["あ" * 40], langue="jp")

    assert "bulle_trop_courte" not in motifs


def test_un_ratio_a_zero_desarme_le_motif_sans_toucher_aux_autres():
    """Une œuvre à sources très elliptiques peut vouloir le taire."""
    court, source = "1. Ouais.", ["あ" * 40]

    assert q.diagnostiquer(court, n=1, cap=5000, sources=source, langue="jp",
                           ratio_court={"cjk": 0}) is None
    assert q.diagnostiquer("", n=1, cap=5000, sources=source, langue="jp",
                           ratio_court={"cjk": 0}) == "vide"


def test_l_exces_de_longueur_passe_avant_le_defaut():
    """Les deux peuvent répondre sur la même planche. L'excès est le plus visible au rendu —
    c'est celui qui déborde de la bulle — d'où son rang dans le registre ordonné."""
    noms = [nom for nom, _ in q.MOTIFS]

    assert noms.index("bulle_trop_longue") < noms.index("bulle_trop_courte")


def test_l_ordre_du_registre_va_du_grossier_au_fin():
    """Une sortie vide ne doit pas être diagnostiquée « japonais résiduel »."""
    assert [nom for nom, _ in q.MOTIFS][:2] == ["vide", "bulles_manquantes"]
    assert q.diagnostiquer("", n=3, cap=10) == "vide"


def test_tous_les_motifs_ont_un_libelle():
    """Aucun motif sans libellé, et aucun libellé orphelin.

    ⚠ `MOTIFS_HORS_REGISTRE` (lot 21) porte les motifs qui refusent une ZONE au lieu de
    diagnostiquer une planche : ils ont un libellé, ils n'arment aucun retry de page, et ils
    n'ont donc rien à faire dans le registre ordonné. L'exception est déclarée dans
    `quality_manga`, pas ici."""
    assert set(nom for nom, _ in q.MOTIFS) | q.MOTIFS_HORS_REGISTRE == set(q.LIBELLES)
    assert not (set(nom for nom, _ in q.MOTIFS) & q.MOTIFS_HORS_REGISTRE)


# --------------------------------------------------------------------------- #
# Numérotation : rattachement des répliques à leurs bulles
#
# La numérotation était lue DEUX fois, par deux expressions régulières jumelles — celle du
# diagnostic et celle de la reconstruction. Elles lisent désormais le même objet.
# --------------------------------------------------------------------------- #

def test_le_mapping_partiel_ne_decale_plus_la_planche():
    """Régression de la page 129 du Vol.1 : le modèle a rendu 9 répliques pour 10 bulles.

    L'ancien test tout-ou-rien (`len(numbered) >= n`) faisait alors basculer la planche
    ENTIÈRE dans le repli positionnel — lequel ne retirait pas le préfixe, d'où neuf « 1. »,
    « 2. »… dessinés à l'encre dans les bulles. On honore désormais les numéros présents."""
    sortie = "\n".join(f"{i}. Réplique {i}" for i in range(1, 10))
    textes, strategie = q.repliques_par_bulle(sortie, 10)
    assert strategie == "numerotee_partielle"
    assert textes == [f"Réplique {i}" for i in range(1, 10)] + [""]


def test_un_trou_dans_la_numerotation_laisse_la_bulle_VIDE_sans_tout_decaler():
    """Le cas où l'ancien repli faisait le plus de dégâts : une réplique manquante au milieu
    décalait toutes les suivantes d'un cran, chacune atterrissant dans la mauvaise bulle."""
    sortie = "1. Un\n2. Deux\n4. Quatre\n5. Cinq"
    textes, strategie = q.repliques_par_bulle(sortie, 5)
    assert strategie == "numerotee_partielle"
    assert textes == ["Un", "Deux", "", "Quatre", "Cinq"]


def test_le_repli_positionnel_retire_le_prefixe_numerote():
    """Invariant du lot : même dans le repli, aucun numéro n'est jamais dessiné.

    Cas réel : le modèle poursuit la numérotation de la planche précédente. Aucun numéro n'est
    dans les bornes, il ne reste que l'ordre des lignes — mais elles portent un préfixe."""
    sortie = "7. Un\n8. Deux\n9. Trois"
    textes, strategie = q.repliques_par_bulle(sortie, 3)
    assert strategie == "positionnelle"
    assert textes == ["Un", "Deux", "Trois"]


@pytest.mark.parametrize("sortie", [
    "1. Un\n2. Deux\n3. Trois",                       # numérotation complète
    "1. Un\n2. Deux",                                 # numérotation partielle
    "Un\nDeux\nTrois",                                # aucun numéro
    "Voici les traductions :\n1) Un\n2) Deux",        # préambule + parenthèses
    "1. 1. Un\n2. 2. Deux",                           # préfixe redoublé par le modèle
    "12. Un\n13. Deux\n14. Trois",                    # tous hors bornes
    "",                                               # sortie vide
])
def test_aucune_replique_ne_commence_par_un_numero(sortie):
    """L'invariant qui rend le défaut de la page 129 structurellement impossible."""
    textes, _ = q.repliques_par_bulle(sortie, 3)
    assert len(textes) == 3
    assert not any(q._LIGNE_NUM.match(t) for t in textes), textes


def test_un_MILLESIME_nest_pas_un_prefixe_numerote():
    """Régression de la page 8 du Vol.1 : la bulle de récitatif « 1972... ».

    L'expression d'origine y lisait la réplique n° 1972 suivie de « .. » — retirer ce
    « préfixe » aurait réduit la bulle à deux points. Deux gardes indépendantes : le
    séparateur doit être suivi d'une espace, et le nombre doit pouvoir être un index de
    bulle. Corriger un défaut de lettrage ne doit pas en créer un autre."""
    assert q.sans_prefixe("1972...") == "1972..."
    assert q.sans_prefixe("1972. Une année terrible") == "1972. Une année terrible"
    assert q.repliques_par_bulle("1. 1972...\n2. Suite", 2)[0] == ["1972...", "Suite"]


def test_le_prefixe_retire_est_bien_retire():
    for brut, propre in (("1. Texte", "Texte"), ("2) Texte", "Texte"),
                         ("  10.  Texte  ", "Texte"), ("3.", ""),
                         ("1. 1. Texte", "Texte")):
        assert q.sans_prefixe(brut) == propre, brut


def test_le_preambule_nest_pas_une_replique():
    """« Voici les traductions : » décalait toute la planche d'un cran dans l'ancien repli."""
    sortie = "Voici les traductions :\n1. Un\n2. Deux\n3. Trois"
    num = q.analyser_numerotation(sortie, 3)
    assert num.preambule == ["Voici les traductions :"]
    assert q.repliques_par_bulle(sortie, 3)[0] == ["Un", "Deux", "Trois"]


def test_un_numero_hors_bornes_est_du_bruit_jamais_une_replique():
    """Un « 11. » sur 10 bulles ne peut pas être une réplique : le retenir ferait mentir le
    décompte de `bulles_manquantes`, donc le déclenchement du retry."""
    sortie = "1. Un\n2. Deux\n3. Trois\n4. Note du traducteur"
    num = q.analyser_numerotation(sortie, 3)
    assert num.hors_bornes == [4]
    assert q.repliques_par_bulle(sortie, 3)[0] == ["Un", "Deux", "Trois"]


def test_sur_un_doublon_le_PREMIER_gagne():
    """Garder le dernier ferait dépendre le résultat de la longueur de la sortie."""
    sortie = "1. Un\n2. Deux\n2. Deuxième essai\n3. Trois"
    num = q.analyser_numerotation(sortie, 3)
    assert num.doublons == [2]
    assert q.repliques_par_bulle(sortie, 3)[0] == ["Un", "Deux", "Trois"]


def test_une_continuation_est_recollee_a_sa_replique():
    """Une ligne non numérotée qui SUIT une ligne numérotée appartient à cette réplique —
    l'ancien code la jetait purement et simplement."""
    sortie = "1. Une réplique\nqui continue à la ligne\n2. Deux"
    textes, strategie = q.repliques_par_bulle(sortie, 2)
    assert strategie == "numerotee"
    assert textes == ["Une réplique qui continue à la ligne", "Deux"]


def test_une_continuation_apres_du_bruit_nest_recollee_a_rien():
    """Après un numéro hors bornes, la suite est du bruit elle aussi : la recoller à la
    dernière réplique valide ajouterait du texte étranger dans une bulle."""
    sortie = "1. Un\n9. Note\net sa suite\n2. Deux"
    textes, _ = q.repliques_par_bulle(sortie, 2)
    assert textes == ["Un", "Deux"]


def test_la_strategie_distingue_le_positionnel_du_numerote():
    assert q.repliques_par_bulle("1. Un\n2. Deux", 2)[1] == "numerotee"
    assert q.repliques_par_bulle("1. Un", 2)[1] == "numerotee_partielle"
    assert q.repliques_par_bulle("Un\nDeux", 2)[1] == "positionnelle"
    assert q.repliques_par_bulle("   \n  ", 2)[1] == "vide"
    assert q.repliques_par_bulle("1. Un", 0) == ([], "vide")


def test_toute_strategie_rendue_a_un_libelle():
    for sortie in ("1. Un\n2. Deux", "1. Un", "Un\nDeux", ""):
        assert q.repliques_par_bulle(sortie, 2)[1] in q.STRATEGIES


def test_une_sortie_vide_remplit_quand_meme_toutes_les_bulles():
    """`typeset_page` s'aligne par POSITION : une liste plus courte laisse les dernières
    bulles vides sans que rien ne le signale."""
    assert q.repliques_par_bulle("", 4)[0] == ["", "", "", ""]


def test_le_diagnostic_et_la_reconstruction_lisent_le_MEME_objet():
    """Ce que le diagnostic compte comme manquant est exactement ce que la reconstruction
    laissera vide — la propriété que deux expressions régulières jumelles ne garantissaient
    pas."""
    for sortie, n in (("1. Un\n2. Deux", 4), ("1. Un\n5. Cinq", 3),
                      ("Voici :\nUn\nDeux", 2), ("1. Un\n1. Bis", 2)):
        rendues = sum(1 for t in q.repliques_par_bulle(sortie, n)[0] if t)
        manquantes = q.diagnostiquer(sortie, n=n, cap=5000) == "bulles_manquantes"
        assert manquantes == (len(q.lignes_numerotees(sortie, n)) < n)
        assert rendues <= n


# --------------------------------------------------------------------------- #
# Rattrapage UNITAIRE d'une bulle laissée vide
#
# Le retry de page rejoue la numérotation — exactement ce qui vient d'échouer. L'escalade
# change de FORME D'APPEL : une bulle, une réponse, aucun numéro à se tromper.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("source,attendu", [
    ("煙幕を張り人形機のセンサーを誤魔化す", True),      # du vrai japonais
    ("Areion", True),                                  # du latin compte aussi
    ("（）", False),                                    # page 8 bulle 1 du Vol.1 : rien
    ("ーー", False),                                    # manga-ocr rend « … » ainsi
    ("．．．", False),
    ("。", False),
    ("", False),
])
def test_une_source_qui_ne_PORTE_pas_de_texte_nest_pas_rattrapable(source, attendu):
    """Sur les deux bulles sans traduction du Vol.1, l'une a pour source `（）`. La rattraper
    coûterait un appel LLM pour faire inventer une réplique à partir de rien.

    `tokens._CJK` ne peut pas servir de déclencheur : il couvre le bloc des formes pleine
    chasse, donc il déclare « du japonais » sur deux parenthèses vides."""
    from core import tokens
    assert q.source_rattrapable(source) is attendu
    if source and not attendu:
        assert tokens._CJK.search(source), "sinon la garde ne servirait à rien"


_SRC = "煙幕を張り人形機のセンサーを誤魔化し本体に接近する"


@pytest.mark.parametrize("reponse,motif", [
    ("Je couvrirai de fumée pour m'approcher.", None),
    ("10. Je couvrirai de fumée.", None),            # un préfixe isolé est simplement retiré
    ("", "vide"),
    ("   \n ", "vide"),
    ("1. Une réplique\n2. Une autre", "liste"),
    ("煙幕を張り", "japonais_residuel"),
    ("Bla " * 200, "disproportionnee"),
])
def test_le_diagnostic_unitaire_a_son_PROPRE_registre(reponse, motif):
    """Il le faut : `bulles_manquantes` déclarerait fautive toute réponse non numérotée,
    c'est-à-dire précisément la forme qu'on demande ici."""
    assert q.diagnostiquer_rattrapage(reponse, source=_SRC) == motif
    if motif == "liste":
        assert q.diagnostiquer(reponse, n=2, cap=500) is None      # …et l'inverse est vrai


def test_une_reponse_NON_numerotee_passe_le_diagnostic_unitaire():
    """Le registre de page la refuserait — c'est tout l'intérêt d'en avoir deux."""
    assert q.diagnostiquer_rattrapage("Je couvrirai de fumée.", source=_SRC) is None
    assert q.diagnostiquer("Je couvrirai de fumée.", n=1, cap=500) == "bulles_manquantes"


def test_tous_les_motifs_de_rattrapage_ont_un_libelle():
    motifs = {q.diagnostiquer_rattrapage(r, source=_SRC)
              for r in ("", "1. Un\n2. Deux", "煙幕を張り", "Bla " * 200)}
    assert motifs <= set(q.LIBELLES_RATTRAPAGE)


class _AgentUnitaire:
    """Agent factice : renvoie les réponses de `reponses`, dans l'ordre."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels: list[str] = []

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.appels.append(user)
        return self.reponses.pop(0) if self.reponses else ""


def _rattraper(*args, **kw):
    from manga.orchestrator_manga import _rattraper_bulles
    return _rattraper_bulles(*args, **kw)


def test_une_bulle_vide_est_rattrapee_par_UN_appel_court():
    """Régression de la page 129 bulle 10 : le modèle a rendu 9 répliques pour 10 bulles."""
    agent = _AgentUnitaire("Je couvrirai de fumée pour m'approcher.")
    stats: dict = {}
    textes, rattrapees, refus = _rattraper(agent, ["あ", _SRC], ["Bonjour", ""], stats=stats)
    assert textes == ["Bonjour", "Je couvrirai de fumée pour m'approcher."]
    assert rattrapees == [1] and refus == []
    assert len(agent.appels) == 1 and stats["rattrapees"] == 1


def test_le_prompt_unitaire_INTERDIT_la_numerotation():
    """C'est le cœur de l'escalade : changer de forme d'appel, pas de température."""
    agent = _AgentUnitaire("Je couvrirai de fumée.")
    _rattraper(agent, [_SRC], [""])
    prompt = agent.appels[0]
    assert "pas de numéro" in prompt and _SRC in prompt
    assert "SEULE réplique" in prompt


def test_une_reponse_diagnostiquee_est_REJETEE_et_la_bulle_reste_vide():
    """Une mauvaise réplique dessinée dans une bulle est pire qu'une bulle vide, qui est au
    moins signalée au rapport."""
    agent = _AgentUnitaire("煙幕を張り")
    stats: dict = {}
    textes, rattrapees, refus = _rattraper(agent, [_SRC], [""], stats=stats, page=129)
    assert textes == [""] and rattrapees == []
    assert refus and "page 129 bulle 1" in refus[0]
    assert stats["rattrapage_refuse"] == 1 and stats.get("rattrapees") is None


def test_une_source_sans_texte_ne_consomme_AUCUN_appel():
    agent = _AgentUnitaire("Ne devrait pas être appelé")
    textes, rattrapees, _refus = _rattraper(agent, ["（）"], [""])
    assert textes == [""] and rattrapees == [] and agent.appels == []


def test_au_dela_du_plafond_on_ne_rattrape_RIEN():
    """Ce n'est plus un trou dans une planche mais une planche ratée : la reprendre bulle par
    bulle serait une retraduction déguisée, sans le contexte de planche."""
    agent = _AgentUnitaire(*(["Une réplique"] * 9))
    stats: dict = {}
    textes, rattrapees, _r = _rattraper(agent, [_SRC] * 4, [""] * 4,
                                        cfg={"max_par_page": 3}, stats=stats)
    assert textes == [""] * 4 and rattrapees == [] and agent.appels == []
    assert stats["rattrapage_abandonne"] == 1
    # …et juste en dessous du plafond, on rattrape tout.
    agent = _AgentUnitaire(*(["Une réplique"] * 3))
    _textes, rattrapees, _r = _rattraper(agent, [_SRC] * 3, [""] * 3, cfg={"max_par_page": 3})
    assert rattrapees == [0, 1, 2]


def test_une_bulle_DEJA_traduite_nest_jamais_retouchee():
    agent = _AgentUnitaire("Ne devrait pas être appelé")
    textes, rattrapees, _r = _rattraper(agent, [_SRC], ["Déjà traduite"])
    assert textes == ["Déjà traduite"] and rattrapees == [] and agent.appels == []


def test_le_prefixe_numerote_est_retire_de_la_reponse_unitaire():
    """L'invariant du lot 1 vaut aussi ici : aucun numéro n'est jamais dessiné."""
    agent = _AgentUnitaire("1. Je couvrirai de fumée.")
    textes, rattrapees, _r = _rattraper(agent, [_SRC], [""])
    assert textes == ["Je couvrirai de fumée."] and rattrapees == [0]


# --------------------------------------------------------------------------- #
# Retry à température corrigée
# --------------------------------------------------------------------------- #

def test_pas_de_retry_si_la_premiere_sortie_est_bonne():
    appels = []

    def call(t):
        appels.append(t)
        return _sortie(3)

    stats: dict = {}
    out, ok, motif = q.try_with_temp_retry(call, n=3, cap=500, stats=stats)
    assert ok and motif is None and appels == [None]
    assert stats["pages_ok"] == 1


def test_retry_PLUS_FROID_sur_une_sortie_vide():
    appels = []

    def call(t):
        appels.append(t)
        return "" if t is None else _sortie(3)

    stats: dict = {}
    _out, ok, motif = q.try_with_temp_retry(call, n=3, cap=500, stats=stats,
                                            temperature=0.3, temp_factor=0.4)
    assert ok and motif is None
    assert appels[1] == pytest.approx(0.12)          # 0,3 × 0,4
    assert stats["retry_temp_reduite"] == 1
    assert stats["recupere_par_retry"] == 1


def test_retry_PLUS_CHAUD_sur_une_boucle():
    """Sur une boucle dégénérée, baisser la température renforce le cycle au lieu de le
    casser — on la relève."""
    appels = []
    boucle = "1. Idem\n2. Idem\n3. Idem"

    def call(t):
        appels.append(t)
        return boucle if t is None else _sortie(3)

    stats: dict = {}
    _out, ok, _motif = q.try_with_temp_retry(call, n=3, cap=5000, stats=stats,
                                             temperature=0.3, temp_factor=0.4)
    assert ok
    assert appels[1] > 0.3, appels
    assert stats["retry_temp_relevee"] == 1


def test_echec_persistant_est_compte_sous_le_motif_du_premier_essai():
    def call(_t):
        return ""

    stats: dict = {}
    _out, ok, motif = q.try_with_temp_retry(call, n=3, cap=500, stats=stats)
    assert not ok and motif == "vide"
    assert stats["vide"] == 1
    assert "pages_ok" not in stats


def test_a_motif_egal_on_garde_la_sortie_la_plus_complete():
    """La plus complète a le plus de répliques récupérables pour l'aval."""
    sorties = iter(["1. Une seule", "1. Une\n2. Deux\n3. Trois\n4. Quatre"])

    def call(_t):
        return next(sorties)

    out, ok, motif = q.try_with_temp_retry(call, n=6, cap=500)
    assert not ok and motif == "bulles_manquantes"
    assert "4. Quatre" in out


def test_max_retries_zero_ne_retente_pas():
    appels = []

    def call(t):
        appels.append(t)
        return ""

    _out, ok, _motif = q.try_with_temp_retry(call, n=3, cap=500, max_retries=0)
    assert not ok and appels == [None]


def test_max_retries_deux_retente_deux_fois():
    appels = []

    def call(t):
        appels.append(t)
        return ""

    q.try_with_temp_retry(call, n=3, cap=500, max_retries=2)
    assert len(appels) == 3


def test_le_moteur_ne_depend_pas_d_un_Agent():
    """`call(temperature) -> str` : zéro couplage aux pixels, testable sans LLM. C'est la
    forme visée par l'extraction vers `core/quality.py` au lot 2."""
    import inspect
    params = list(inspect.signature(q.try_with_temp_retry).parameters)
    assert params[0] == "call"
    assert "agent" not in params


# --------------------------------------------------------------------------- #
# Lot 12 — durcissements. AUCUN de ces défauts ne s'est déclenché sur les deux
# tomes ; ils sont armés pour le jour où le modèle dérapera.
# --------------------------------------------------------------------------- #

def test_la_ponctuation_pleine_chasse_nest_PAS_du_japonais():
    """`（）` et `！？` sont de la ponctuation, pas de la langue. `tokens.CJK` (large) les
    couvre parce qu'elle sert à compter des TOKENS ; décider « du japonais est resté » demande
    la classe étroite `CJK_TEXTE`. La bulle 1 de la page 8 du Vol.1 est exactement ce cas."""
    assert q.diagnostiquer("1. （）\n2. !?", n=2, cap=0) != "japonais_residuel"


def test_du_vrai_japonais_reste_detecte():
    assert q.diagnostiquer("1. こんにちは\n2. Salut", n=2, cap=0) == "japonais_residuel"
    assert q.diagnostiquer("1. 陽弥\n2. Salut", n=2, cap=0) == "japonais_residuel"


def test_diagnostiquer_tous_ne_masque_plus_le_japonais():
    """Une sortie à la fois INCOMPLÈTE et JAPONAISE était rapportée « numérotation
    incomplète » : le registre est ordonné et `diagnostiquer` s'arrête au premier motif. Le
    mot « japonais » n'apparaissait ni en console ni dans RAPPORT.md."""
    sortie = "1. こんにちは"          # 1 ligne pour 3 bulles, et du japonais dedans
    assert q.diagnostiquer(sortie, n=3, cap=0) == "bulles_manquantes"
    tous = q.diagnostiquer_tous(sortie, n=3, cap=0)
    assert "bulles_manquantes" in tous and "japonais_residuel" in tous


def test_diagnostiquer_tous_est_vide_sur_une_sortie_saine():
    assert q.diagnostiquer_tous("1. Bonjour\n2. Salut", n=2, cap=0) == []


def test_motifs_repliques_juge_ce_qui_sera_DESSINE():
    """Sur un cache relu (`--from rendu`), la sortie brute n'existe plus : seules les
    répliques finales sont disponibles, et ce sont elles qui vont être dessinées."""
    assert q.motifs_repliques(["Bonjour", "こんにちは"]) == ["japonais_residuel"]
    assert q.motifs_repliques(["Bonjour", "Salut"]) == []
    assert q.motifs_repliques([]) == []
    assert q.motifs_repliques(None) == []


def test_a_numerotation_egale_on_prefere_la_sortie_SANS_japonais():
    """Le critère était purement quantitatif : une tentative plus japonaise mais mieux
    numérotée l'emportait. Comme le japonais n'est pas dessinable — la chaîne de polices n'en
    a pas les glyphes —, on préférait sans le savoir la version qui produit des bulles VIDES."""
    japonaise = "1. こんにちは\n2. さようなら"
    francaise = "1. Bonjour\n2. Au revoir"
    assert q._prefere(japonaise, "japonais_residuel", francaise, "bulle_trop_longue")
    assert not q._prefere(francaise, "bulle_trop_longue",
                                      japonaise, "japonais_residuel")


def test_le_nombre_de_repliques_reste_le_critere_PRINCIPAL():
    """Une sortie japonaise mais complète reste préférable à une sortie française qui perd
    la moitié des bulles : on récupère plus de matière, et le japonais est signalé."""
    complete = "1. こんにちは\n2. さようなら\n3. またね"
    partielle = "1. Bonjour"
    assert q._prefere(partielle, "bulles_manquantes",
                                  complete, "japonais_residuel")


# --------------------------------------------------------------------------- #
# Lot 15 — la boucle cesse d'accuser une traduction fidèle
# --------------------------------------------------------------------------- #

def test_une_source_qui_se_repete_nest_PAS_une_boucle():
    """*manga B* Chap.5, pages 58 et 59 : une foule scande un nom, l'OCR rend
    `マリアネラ` SIX fois, et la traduction le rend six fois. Les deux planches étaient
    diagnostiquées « le modèle a bouclé » et ont dépensé leurs retries pour rien — deux des
    cinq boucles annoncées au rapport du tome."""
    sortie = "\n".join(f"{i}. Marianna Lassar" for i in range(1, 7))
    sources = ["マリアネラ"] * 6
    assert q.diagnostiquer(sortie, n=6, cap=0, sources=sources) != "repetition"


def test_une_vraie_boucle_reste_detectee():
    """Sources toutes différentes, sortie qui se répète : là, le modèle a bien bouclé."""
    sortie = "\n".join(f"{i}. Toujours la même chose" for i in range(1, 7))
    sources = ["あ", "い", "う", "え", "お", "か"]
    assert q.diagnostiquer(sortie, n=6, cap=0, sources=sources) == "repetition"


def test_une_repetition_PLUS_FORTE_que_la_source_reste_une_boucle():
    """Deux sources identiques mais six sorties identiques : le modèle en a rajouté."""
    sortie = "\n".join(f"{i}. Marianna Lassar" for i in range(1, 7))
    sources = ["マリアネラ", "マリアネラ", "あ", "い", "う", "え"]
    assert q.diagnostiquer(sortie, n=6, cap=0, sources=sources) == "repetition"


def test_sans_sources_le_comportement_historique_est_conserve():
    """`sources` est optionnel : sans lui, on ne peut que croire la sortie."""
    sortie = "\n".join(f"{i}. Pareil" for i in range(1, 5))
    assert q.diagnostiquer(sortie, n=4, cap=0) == "repetition"
