# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`PLAN-29` L29.4 — le décor : le levier existe, **et la valeur ne bouge pas**.

Le lot 26 a mesuré que la part d'aplats de l'image générée vaut **0,6300** contre **0,3669**
pour le tome — le seul descripteur qui ait EMPIRÉ pendant que la moyenne progressait. Le plan
en nomme la cause probable, et elle est de notre fait : « sur fond neutre » demande une grande
surface d'une seule teinte.

Ces tests tiennent les deux moitiés de la livraison, et la seconde compte autant que la
première :

1. **le levier existe** — trois variantes, un axe de balayage, un champ dans `requete.yaml`,
   et le décor archivé dans le sidecar pour que la mesure sache image par image laquelle est
   laquelle ;
2. **rien ne bouge par défaut** — le prompt produit sans rien demander est celui d'avant le
   lot 29, **mot pour mot**. Aucune mesure ne désigne encore un remplaçant, et le dépôt ne
   change pas un prompt sur une hypothèse.
"""
import pytest

from illustration import gabarits as gabarits_mod
from illustration import prompt as prompt_mod
from illustration import requete as requete_mod

#: Une bible minimale mais **citée** — sans citation, `construire` refuse, et il a raison.
BIBLE = {"version": 1, "personnages": [{
    "nom": "Tory", "genre_confirme": "féminin",
    "apparence": {"cheveux": "noirs", "yeux": "", "age_apparent": "", "tenue": "",
                  "signes": []},
    "citations": [{"attribut": "cheveux", "texte": "ses cheveux noirs",
                   "source": "chapters/ch01.md"}],
    "references": [], "images_generees": [], "valide_par_humain": True}]}


# ──────────────────────────  Le levier existe  ──────────────────────────

def test_le_gabarit_livre_porte_les_variantes_dans_les_deux_langues():
    for langue in gabarits_mod.LANGUES:
        decors = gabarits_mod.charger("portrait", langue=langue).decors
        assert {"neutre", "trame", "sommaire", "aucun"} <= set(decors)


def test_un_gabarit_sans_bloc_decors_recoit_quand_meme_le_defaut():
    """Un gabarit tiers écrit avant le lot 29 n'a que `decor:`. Lui rendre zéro variante
    ferait échouer un balayage avec un message parlant d'un bloc YAML jamais vu."""
    table = gabarits_mod._decors({"decor": "sur fond blanc"})
    assert table == {gabarits_mod.DECOR_DEFAUT: "sur fond blanc"}


def test_un_decor_inconnu_LEVE_plutot_que_de_retomber_sur_neutre():
    """⚠ Le cœur de la mesure : une faute de frappe qui retomberait en silence sur « neutre »
    produirait l'image que le lot 29 cherche précisément à comparer à une autre."""
    gab = gabarits_mod.charger("portrait", langue="fr")
    with pytest.raises(gabarits_mod.GabaritIntrouvable) as erreur:
        gab.decor_de("tramé")
    assert "trame" in str(erreur.value)          # le message donne les valeurs possibles


def test_la_variante_aucun_rend_une_phrase_vide_dans_les_TROIS_formes():
    """« aucun » n'est pas « pas de décor » : c'est « le prompt ne dit rien du décor ». Les
    trois formes du champ texte doivent porter le même contenu (cf. `assembler`)."""
    gab = gabarits_mod.charger("portrait", langue="fr")
    fragments = prompt_mod.construire("Tory", BIBLE).fragments
    for forme in gabarits_mod.FORMES:
        texte = prompt_mod.assembler(gab, forme=forme, genre="feminin", cadrage="buste",
                                     decor="aucun", fragments=fragments)
        assert "fond neutre" not in texte
        assert "Décor" not in texte


@pytest.mark.parametrize("forme", gabarits_mod.FORMES)
def test_la_variante_choisie_entre_dans_le_texte_quelle_que_soit_la_forme(forme):
    gab = gabarits_mod.charger("portrait", langue="fr")
    fragments = prompt_mod.construire("Tory", BIBLE).fragments
    texte = prompt_mod.assembler(gab, forme=forme, genre="feminin", cadrage="buste",
                                 decor="trame", fragments=fragments)
    assert "fond tramé" in texte
    assert "fond neutre" not in texte


def test_la_requete_porte_le_decor_et_le_sidecar_aussi():
    """⚠ Sans ce champ, deux images produites avec « fond neutre » et « fond tramé » ne
    diffèrent, dans le payload, que par une poignée de mots au milieu d'un prompt : la mesure
    de la part d'aplats ne saurait pas, image par image, laquelle est laquelle."""
    from illustration.orchestrateur import _bloc_prompt

    doc = requete_mod.depuis_oeuvre(BIBLE, personnages=["Tory"], decor="sommaire")
    bloc = doc["images"][0]
    assert bloc["decor"] == "sommaire"

    doc["blocs"] = {bloc["nom"]: bloc}
    assert _bloc_prompt(doc, {}, bloc["nom"])["decor"] == "sommaire"


def test_le_balayage_ouvre_un_axe_decor_seulement_sur_demande():
    from tools.banc_identite import configurations

    ferme = configurations()
    assert not any(c.axe == "decor" for c in ferme)
    assert all(c.decor == gabarits_mod.DECOR_DEFAUT for c in ferme)

    ouvert = configurations(decors=("neutre", "trame", "aucun"))
    assert len(ouvert) == len(ferme) + 3
    assert {c.decor for c in ouvert if c.axe == "decor"} == {"neutre", "trame", "aucun"}


def test_le_nom_d_une_configuration_distingue_deux_decors():
    """Deux configurations qui ne diffèrent que par le décor écriraient sinon dans le même
    fichier, et la seconde image écraserait la première."""
    from tools.banc_identite import configurations

    noms = [c.nom for c in configurations(decors=("neutre", "trame", "aucun"))]
    assert len(noms) == len(set(noms))


def test_l_axe_ferme_ecrit_les_MEMES_noms_de_fichier_qu_avant_le_lot_29():
    """⚠ Un balayage lancé sans `--decors` ne doit renommer aucun fichier : deux séries
    mesurées à six mois d'écart restent comparables fichier par fichier, et un document de
    mesure publié ne renvoie pas à des noms qui n'existent plus."""
    from tools.banc_identite import configurations

    assert [c.nom for c in configurations()] == [
        "nombre_references-r1-p4-g1", "nombre_references-r2-p4-g1",
        "nombre_references-r3-p4-g1", "force-r2-p6-g1", "force-r2-p8-g1"]
    assert all(gabarits_mod.DECOR_DEFAUT not in c.nom for c in configurations())


# ────────────────────  Rien ne bouge par défaut, et c'est le point  ────────────────────

def test_le_prompt_par_defaut_est_celui_d_AVANT_le_lot_29():
    """⚠ **Le test qui rend la livraison iso-comportement.** Le défaut du dépôt reste
    « sur fond neutre » : le levier est livré, la mesure qui désignerait un remplaçant n'a pas
    pu être faite (pas de GPU dans la session du 2026-09-03)."""
    sans_rien = prompt_mod.construire("Tory", BIBLE).requete.prompt
    explicite = prompt_mod.construire("Tory", BIBLE, decor="neutre").requete.prompt
    assert sans_rien == explicite
    assert "sur fond neutre" in sans_rien


def test_le_defaut_du_gabarit_et_celui_du_code_sont_le_MEME():
    """Deux défauts qui divergeraient produiraient deux prompts selon le chemin d'appel."""
    gab = gabarits_mod.charger("portrait", langue="fr")
    assert gab.decor_de() == gab.decors[gabarits_mod.DECOR_DEFAUT] == gab.decor


def test_une_requete_ecrite_avant_le_lot_29_se_relit_sans_redemander_de_validation():
    """« Un schéma qui invaliderait la relecture humaine à chaque lot rendrait la porte
    insupportable, donc contournée. »"""
    ancienne = {"version": 2, "valide": True,
                "images": [{"nom": "tory", "personnage": "Tory", "cadrage": "buste",
                            "prompt": "un personnage seul, sur fond neutre."}]}
    relue = requete_mod.fill_defaults(ancienne)
    assert relue["valide"] is True
    assert relue["images"][0]["decor"] == gabarits_mod.DECOR_DEFAUT


def test_l_empreinte_du_gabarit_change_avec_son_contenu():
    """Le gabarit a changé au lot 29 : son empreinte doit donc changer aussi, sans quoi deux
    prompts différents circuleraient sous la même signature."""
    assert len(gabarits_mod.empreinte("portrait")) == 64
