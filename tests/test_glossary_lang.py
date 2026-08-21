# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Socle linguistique du glossaire (`core/glossary_lang.py`).

Le module est PUR : aucune E/S, aucun appel LLM, aucune dépendance à `pipeline/` ni à
`manga/`. Tout se teste par valeurs, ce qui est précisément l'intérêt d'avoir sorti la
règle « quelle graphie va dans quel champ » des trois producteurs qui l'appliquent.

Les entrées d'exemple sont calquées sur `sources/roman A/glossaire.yaml`, où les
48 entrées avaient un `nom` japonais.
"""
from core import glossary_lang as gl
from core import tokens


# --- Détection ------------------------------------------------------------------- #

def test_cjk_est_la_classe_etroite_pas_celle_du_budget():
    """`tokens.CJK` (budget de tokens) couvre `「」『』` et les formes pleine chasse. S'en
    servir ici ferait déclarer « du japonais » sur de la simple ponctuation — le faux
    positif déjà payé par la brique manga sur une bulle ne contenant que `（）`."""
    assert gl.CJK is tokens.CJK_TEXTE
    for ponctuation in "「」『』、。（）・…":
        assert not gl.contient_cjk(ponctuation), ponctuation
    for porteur in "彼あカ丈ー":
        assert gl.contient_cjk(porteur), porteur


def test_contient_latin_distingue_les_deux_ecritures():
    assert gl.contient_latin("Mitsukage") and not gl.contient_cjk("Mitsukage")
    assert gl.contient_cjk("三影") and not gl.contient_latin("三影")
    assert gl.contient_latin("Yaeyamabuki（八重山吹）") and gl.contient_cjk("Yaeyamabuki（八重山吹）")


def test_pivot_est_cjk_par_le_code_ou_par_la_mesure():
    """Le code suffirait aujourd'hui, mais `langues.dossiers` est éditable : la mesure
    rattrape un dossier nommé autrement."""
    assert gl.pivot_est_cjk("jp") and gl.pivot_est_cjk("zh") and gl.pivot_est_cjk("KO")
    assert not gl.pivot_est_cjk("en") and not gl.pivot_est_cjk("fr")
    assert not gl.pivot_est_cjk(None)
    assert gl.pivot_est_cjk("xx", "彼は塔の階層を見上げ、七堕の気配を探った。")
    # Un texte français citant quelques noms japonais n'est PAS un pivot japonais.
    assert not gl.pivot_est_cjk("fr", "Akane leva les yeux vers la tour 千万丈塔, au loin, "
                                      "et chercha longuement la présence des Nanae.")


# --- Réparation ------------------------------------------------------------------ #

def test_nom_cjk_avec_variante_latine_est_repare_silencieusement():
    e, avertissements = gl.reparer_entree(
        {"nom": "三影", "variantes": ["Mitsukage", "Mikage"], "termes_source": []})
    assert e["nom"] == "Mitsukage"
    assert e["termes_source"] == ["三影"]
    assert e["variantes"] == ["Mikage"]
    assert not avertissements                       # sans perte ni ambiguïté
    assert "a_romaniser" not in e


def test_nom_cjk_sans_forme_latine_est_conserve_et_signale():
    """Retirer le `nom` perdrait la description et le genre, coûteux à reconstruire. On
    conserve, on range la graphie source, et on marque."""
    e, avertissements = gl.reparer_entree(
        {"nom": "天茜", "genre": "masculin", "description": "Jeune sorcier de l'agence."})
    assert e["nom"] == "天茜"                        # conservé
    assert e["termes_source"] == ["天茜"]
    assert e["a_romaniser"] is True
    assert e["description"] == "Jeune sorcier de l'agence."
    assert len(avertissements) == 1 and "天茜" in avertissements[0]


def test_variante_cjk_migre_vers_termes_source():
    """`variantes` est la clé de recherche du dédoublonneur : y laisser une graphie source
    la fait concurrencer les orthographes latines légitimes."""
    e, _ = gl.reparer_entree(
        {"nom": "Secte du Dragon déchu", "variantes": ["la Secte", "堕竜講"],
         "termes_source": []})
    assert e["nom"] == "Secte du Dragon déchu"
    assert e["variantes"] == ["la Secte"]
    assert e["termes_source"] == ["堕竜講"]


def test_variante_latine_nest_jamais_touchee():
    """Non-régression des œuvres à pivot latin : sans CJK, l'entrée ressort telle quelle."""
    origine = {"nom": "Feodor Jessman", "variantes": ["Féodor", "Fwedo"],
               "interdits": ["Fedor"], "termes_source": ["Semifer"], "genre": "masculin"}
    e, avertissements = gl.reparer_entree(origine)
    assert e == origine and not avertissements


def test_nom_egal_termes_source_en_latin_nest_pas_un_defaut():
    """Sur une source anglaise, un nom propre inchangé est exactement ce qu'on veut."""
    e, avertissements = gl.reparer_entree({"nom": "Semifer", "termes_source": ["Semifer"]})
    assert e["nom"] == "Semifer" and not avertissements and "a_romaniser" not in e


def test_pluriel_cjk_est_evacue():
    """Un pluriel en CJK n'est jamais un pluriel français : il ne sert à rien au rendu."""
    e, _ = gl.reparer_entree({"nom": "Nanae", "pluriel": "七堕", "termes_source": []})
    assert e["pluriel"] == "" and e["termes_source"] == ["七堕"]


def test_reparation_est_idempotente():
    e1, a1 = gl.reparer_entree({"nom": "天茜", "variantes": ["天茜"], "termes_source": ["天茜"]})
    e2, a2 = gl.reparer_entree(e1)
    assert e1 == e2 and a1 == a2
    assert e2["termes_source"] == ["天茜"]           # pas de doublon
    e3, _ = gl.reparer_entree(e2)
    assert e3 == e2


def test_reparation_ne_mute_pas_lentree_dorigine():
    origine = {"nom": "天茜", "variantes": ["Akane"], "termes_source": []}
    copie = {"nom": "天茜", "variantes": ["Akane"], "termes_source": []}
    gl.reparer_entree(origine)
    assert origine == copie


def test_le_drapeau_tombe_quand_le_nom_est_romanise():
    """Une entrée corrigée à la main (ou par une relance de la terminologie) ne doit pas
    rester masquée au traducteur."""
    e, _ = gl.reparer_entree({"nom": "Akane", "a_romaniser": True, "termes_source": ["天茜"]})
    assert "a_romaniser" not in e
    # Même chose quand la romanisation arrive par les variantes.
    e2, _ = gl.reparer_entree({"nom": "天茜", "a_romaniser": True, "variantes": ["Akane"]})
    assert e2["nom"] == "Akane" and "a_romaniser" not in e2


# --- Formes autorisées et audit --------------------------------------------------- #

def _glossaire_exemple() -> dict:
    return {
        "personnages": [
            {"nom": "天茜", "a_romaniser": True, "termes_source": ["天茜"]},
            {"nom": "Matsurika", "termes_source": ["祭花"]},
        ],
        "termes": [
            {"nom": "七堕", "traduire": False, "variantes": ["ナナエ"], "termes_source": ["七堕"]},
            {"nom": "rite de franchissement", "traduire": True, "termes_source": ["踏破儀式"]},
        ],
    }


def test_formes_autorisees_couvre_traduire_false_et_a_romaniser():
    formes = gl.formes_cjk_autorisees(_glossaire_exemple())
    assert set(formes) == {"天茜", "七堕", "ナナエ"}
    # Une entrée dûment traduite n'autorise rien, et `termes_source` n'est JAMAIS légitime
    # dans le texte français — c'est justement ce qu'on cherche à détecter.
    assert "踏破儀式" not in formes and "祭花" not in formes


def test_formes_autorisees_triees_de_la_plus_longue_a_la_plus_courte():
    """Retirer « 七堕 » avant « 七堕講 » laisserait le morceau « 講 » derrière lui."""
    glo = {"termes": [{"nom": "七堕", "traduire": False},
                      {"nom": "七堕講", "traduire": False}]}
    assert gl.formes_cjk_autorisees(glo) == ("七堕講", "七堕")


def test_formes_autorisees_tolere_les_sections_hors_entites():
    """`anglicismes` a la forme `{vo, fr}`, `groupes` est une liste de chaînes : ni l'un
    ni l'autre ne doit faire lever la fonction."""
    glo = {"anglicismes": [{"vo": "skill", "fr": "compétence"}], "groupes": ["les Sept"],
           "personnages": "pas une liste"}
    assert gl.formes_cjk_autorisees(glo) == ()
    assert gl.auditer(glo) == []


def test_auditer_liste_ce_qui_reste_a_romaniser():
    lignes = gl.auditer(_glossaire_exemple())
    assert len(lignes) == 2
    assert any("天茜" in l and "personnages" in l for l in lignes)
    assert any("七堕" in l for l in lignes)
    assert not any("Matsurika" in l for l in lignes)


def test_auditer_ne_mute_rien():
    glo = _glossaire_exemple()
    avant = repr(glo)
    gl.auditer(glo)
    assert repr(glo) == avant


# --- Consigne --------------------------------------------------------------------- #

def test_consigne_nomme_les_deux_champs_et_les_deux_regles():
    c = gl.consigne_pivot_cjk()
    assert "`nom`" in c and "`termes_source`" in c
    assert "Hepburn" in c and "traduction française" in c
    assert "八重山吹" in c              # un exemple concret, pas seulement une règle
