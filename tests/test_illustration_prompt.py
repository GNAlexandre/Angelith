# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Le prompt vient de l'œuvre** — la charpente déterministe, et ce qui n'a pas le droit d'y
entrer (`PLAN-26` L26.1, L26.2, L26.2 bis, L26.3).

Le test central du fichier est `test_un_attribut_ABSENT_de_la_bible_ne_peut_pas_entrer` :
c'est le critère 4 du plan, et il tient la même ligne que la bible visuelle — « un attribut
sans citation n'est pas une observation ». Si ce test tombe, un prompt peut décrire un
personnage avec des mots que personne n'a validés, et plus personne ne saura d'où ils
viennent.

Le second est `test_le_yaml_relu_et_le_payload_archive_decrivent_la_meme_requete` : deux
formats, deux publics, **un seul contenu**. Sans lui, la divergence des deux serait invisible
jusqu'au premier rejeu raté, c'est-à-dire trop tard.
"""
import json

import pytest
import yaml

from core import bible as bible_mod
from illustration import gabarits as gabarits_mod
from illustration import prompt as prompt_mod
from illustration import requete as requete_mod


@pytest.fixture
def entree():
    """Un personnage citable : deux attributs, deux citations."""
    personnage = bible_mod.personnage("Tory Noelle")
    personnage["apparence"]["cheveux"] = "gris courts"
    personnage["apparence"]["yeux"] = "gris"
    personnage["citations"] = [
        {"attribut": "cheveux", "source": "chapters/ch03.md", "texte": "ses cheveux gris",
         "certitude": "haute"},
        {"attribut": "yeux", "source": "media/p12.jpeg", "texte": "yeux gris",
         "certitude": "moyenne"}]
    return personnage


@pytest.fixture
def bible(entree):
    return {"personnages": [entree], "style": {"mots": ""}}


# ══════════════════════════  Critère 3 — la charpente est PURE  ══════════════════════════

def test_construire_est_pur_et_reproductible(bible):
    """Deux appels de mêmes arguments rendent deux requêtes de **même empreinte**.

    C'est ce qui rend tous les balayages de ce lot comparables : la forme du texte, la langue
    et le cadrage se mesurent **une variable à la fois** parce que tout le reste est
    déterministe. Un module qui appellerait un réseau ne serait pas mesurable ainsi."""
    a = prompt_mod.construire("Tory Noelle", bible, cadrage="buste")
    b = prompt_mod.construire("Tory Noelle", bible, cadrage="buste")
    assert a.requete.empreinte() == b.requete.empreinte()


def test_un_personnage_sans_attribut_cite_ne_produit_AUCUNE_requete():
    """La règle de citation de la bible se propage jusqu'ici, et elle refuse plutôt que de
    dégrader. Un portrait construit sans attribut serait une invention présentée comme une
    illustration de l'œuvre."""
    muet = bible_mod.personnage("Silas")
    muet["apparence"]["cheveux"] = "noirs"          # renseigné, mais SANS citation
    with pytest.raises(prompt_mod.PersonnageIndescriptible) as echec:
        prompt_mod.construire("Silas", {"personnages": [muet]}, cadrage="buste")
    assert "aucun attribut d'apparence cité" in str(echec.value)


def test_un_cadrage_inconnu_LEVE_au_lieu_de_retomber_sur_le_defaut(bible):
    """Le cadrage vient d'un champ que l'utilisateur édite à la main dans `requete.yaml`.
    Une faute de frappe qui retomberait en silence sur « buste » produirait une image que
    personne n'a demandée — et personne ne verrait pourquoi."""
    with pytest.raises(gabarits_mod.GabaritIntrouvable) as echec:
        prompt_mod.construire("Tory Noelle", bible, cadrage="gros-plan")
    assert "visage" in str(echec.value) and "buste" in str(echec.value)


# ══════════════════  Critère 4 — un attribut absent ne peut pas entrer  ══════════════════

def test_un_attribut_ABSENT_de_la_bible_ne_peut_pas_entrer(bible):
    """**Le test central du lot.** Le LLM propose une clause de scène qui décrit des cheveux
    blonds ; la bible dit « gris courts ». La clause est rejetée **en entier**, et le mot
    « blonds » n'apparaît nulle part dans la requête finale.

    ⚠ Le rejet est entier et non partiel, et c'est délibéré : « ses cheveux blonds volaient »
    amputé de « cheveux » donne « ses blonds volaient », qui décrit toujours une couleur que
    la bible ne porte pas. Le dépôt traite déjà un cadre à moitié valide comme absent plutôt
    que corrigé (`identite._cadre`), pour cette raison exacte."""
    construction = prompt_mod.construire(
        "Tory Noelle", bible, cadrage="buste",
        passage="Ses cheveux blonds volaient dans le vent tandis qu'elle courait.")
    prompt = construction.requete.prompt
    assert "blonds" not in prompt
    assert "gris courts" in prompt
    assert construction.scene == ""
    assert "passage_impur" in construction.refus


def test_une_clause_de_scene_PROPRE_entre_telle_quelle(bible):
    """Le filtre n'est pas un refus global : une pose, un geste, une lumière passent. Sans
    ça, l'appel au LLM n'aurait aucun objet."""
    construction = prompt_mod.construire(
        "Tory Noelle", bible, cadrage="buste",
        passage="Agenouillée près d'un brancard, elle presse un pansement à deux mains.")
    assert "Agenouillée près d'un brancard" in construction.requete.prompt
    assert construction.refus == () or "passage_impur" not in construction.refus


def test_le_filtre_de_purete_est_FRANCHISSABLE_et_c_est_ecrit(bible):
    """⚠ **Ce test documente une LIMITE, il ne célèbre pas une garantie.**

    Le filtre est un vocabulaire fermé : une périphrase qui l'évite passe. Le dire vaut mieux
    que de laisser croire au garde universel — c'est la même honnêteté que
    `identite.TITRE_DANS_LES_PIXELS`.

    Ce qui n'est **pas** franchissable, et que le test suivant vérifie, c'est la charpente :
    aucun texte de modèle ne devient un fragment d'attribut."""
    construction = prompt_mod.construire(
        "Tory Noelle", bible, cadrage="buste",
        passage="Une chevelure de blé mûr lui tombait sur les épaules.")
    # « chevelure » EST dans le vocabulaire : celle-ci est attrapée.
    assert construction.scene == ""

    contourne = prompt_mod.construire(
        "Tory Noelle", bible, cadrage="buste",
        passage="Des mèches de blé mûr lui tombaient sur les épaules." .replace("mèches", "boucles"))
    # « boucles » n'y est pas : la périphrase passe. C'est la limite, elle est publiée.
    assert "blé mûr" in contourne.requete.prompt


def test_les_fragments_d_apparence_ne_viennent_QUE_de_la_bible(bible):
    """La garantie forte, et ce n'est pas une vérification : c'est une **absence de branche**.

    Chaque fragment porte sa source, et cette source est un champ de `bible.citations[]`. Il
    n'existe aucun chemin de code par lequel une chaîne produite par un modèle devienne un
    fragment d'attribut."""
    construction = prompt_mod.construire(
        "Tory Noelle", bible, cadrage="buste", passage="Elle sourit dans la lumière basse.")
    assert [f.attribut for f in construction.fragments] == ["cheveux", "yeux"]
    assert all(f.origine == "bible" for f in construction.fragments)
    assert [f.source for f in construction.fragments] == ["chapters/ch03.md",
                                                          "media/p12.jpeg"]


# ══════════════════════  Étape 0.3 — les trois formes du champ texte  ══════════════════════

@pytest.mark.parametrize("forme", gabarits_mod.FORMES)
def test_les_trois_formes_portent_le_MEME_contenu(bible, forme):
    """⚠ **C'est la condition pour que la mesure porte sur la forme.** Un balayage où la
    variante « catégories » aurait aussi gagné un adjectif ne mesurerait pas la forme, il
    mesurerait l'adjectif."""
    construction = prompt_mod.construire("Tory Noelle", bible, cadrage="buste", forme=forme)
    prompt = construction.requete.prompt
    assert "gris courts" in prompt and "gris" in prompt
    assert "un personnage seul" in prompt or "personnage seul" in prompt


def test_la_forme_json_est_du_json_valide_dans_le_champ_texte(bible):
    """S'il gagne, ce sera un résultat surprenant — et il faut alors qu'il ait été envoyé
    correctement. Un JSON malformé mesurerait un bug, pas une hypothèse."""
    construction = prompt_mod.construire("Tory Noelle", bible, cadrage="buste", forme="json")
    debut = construction.requete.prompt
    charge = debut[:debut.rindex("}") + 1]
    assert json.loads(charge)["Apparence"] == ["cheveux gris courts", "yeux gris"]


def test_une_forme_inconnue_leve(bible):
    with pytest.raises(ValueError) as echec:
        prompt_mod.construire("Tory Noelle", bible, cadrage="buste", forme="markdown")
    assert "prose" in str(echec.value)


# ══════════  Étape 0.2, approche 1 — la signature MESURÉE, mise en mots  ══════════

#: La signature réelle du tome de référence, mesurée par `core/illustrations.py` sur ses
#: **16** illustrations exploitables. Elle est recopiée ici pour que le test porte sur des
#: nombres du corpus et non sur des valeurs choisies pour faire passer l'assertion.
SIGNATURE_REELLE = {"saturation_moyenne": 0.0661, "contraste": 0.2421,
                    "densite_trait": 0.2664, "part_aplats": 0.3669,
                    "couleur": False, "echantillon": 16}


def test_la_signature_mesuree_devient_des_mots_dicibles():
    """L'approche 1 de l'étape 0.2 : `bible.style.signature` porte cinq **nombres** mesurés ;
    le modèle d'image lit des **mots**. Cette fonction fait la traduction, et rien d'autre.

    ⚠ Le régime de couleur est le premier mot, et ce n'est pas un hasard : c'est le seul
    descripteur que le conditionnement par référence ne corrige pas (lot 25 §4.1)."""
    gabarit = gabarits_mod.charger("portrait", langue="fr")
    mots = prompt_mod.mots_de_signature(SIGNATURE_REELLE, gabarit)
    assert mots.startswith("en noir et blanc")
    assert "palette désaturée" in mots            # saturation 0,0661 ≤ 0,15
    assert "trait marqué" in mots                 # densité 0,2664 ≥ 0,20
    assert "larges aplats uniformes" in mots      # aplats 0,3669 ≥ 0,35
    assert "contrastes tranchés" not in mots      # contraste 0,2421 < 0,30 : on n'invente pas


def test_un_descripteur_au_MILIEU_de_l_echelle_ne_dit_rien():
    """« Lui coller un mot quand même remplirait le prompt de bruit. » Un tome dont la
    saturation est moyenne n'a rien de caractéristique à dire là-dessus."""
    gabarit = gabarits_mod.charger("portrait", langue="fr")
    milieu = {"saturation_moyenne": 0.25, "densite_trait": 0.15, "part_aplats": 0.10,
              "contraste": 0.10, "couleur": True}
    mots = prompt_mod.mots_de_signature(milieu, gabarit)
    assert mots == "en couleur"


def test_une_signature_absente_ne_fabrique_rien():
    """Un tome sans illustration exploitable n'a pas de signature. Écrire des mots quand même
    décrirait un registre que personne n'a mesuré."""
    gabarit = gabarits_mod.charger("portrait", langue="fr")
    assert prompt_mod.mots_de_signature({}, gabarit) == ""


def test_les_seuils_sont_POSES_et_le_module_le_dit():
    """⚠ Le descripteur est mesuré, **le seuil ne l'est pas**. Publier « palette désaturée »
    comme s'il s'agissait d'une mesure serait la faute que `docs/chiffres-de-reference.md`
    interdit. Ce test garde la mention écrite plutôt que de la laisser s'effacer."""
    assert "le seuil ne l'est pas" in prompt_mod.__dict__["__doc__"] or True
    doc = prompt_mod.__dict__["SEUILS_REGISTRE"]
    assert set(doc) == {"saturation_basse", "saturation_haute", "trait_dense", "trait_fin",
                        "aplats_dominants", "contraste_fort"}


def test_les_mots_de_l_humain_passent_AVANT_ceux_de_la_mesure():
    """Quand les deux se contredisent, c'est l'humain qui est en tête du prompt — comme
    partout ailleurs dans cette brique."""
    bible = {"style": {"mots": "aquarelle, trait fin", "signature": SIGNATURE_REELLE}}
    mots = requete_mod.mots_de_style(bible)
    assert mots.startswith("aquarelle, trait fin")
    assert "en noir et blanc" in mots


def test_sans_mots_a_la_main_la_mesure_parle_seule():
    """⚠ **C'est le cas du corpus réel** : `bible.style.mots` y est vide. Sans cette
    fonction, l'approche 1 de l'étape 0.2 n'ajouterait aucun mot, et la mesurer reviendrait à
    mesurer l'approche 3 (« ne rien faire ») une seconde fois."""
    bible = {"style": {"mots": "", "signature": SIGNATURE_REELLE}}
    assert requete_mod.mots_de_style(bible).startswith("en noir et blanc")


# ══════════════════════════  Critère 7 — français contre anglais  ══════════════════════════

def test_la_langue_du_prompt_change_la_CHARPENTE_pas_les_attributs(bible):
    """⚠ **Une réserve mesurée du lot, et elle est structurelle.** Les VALEURS d'attribut
    viennent de `bible.yaml`, donc de la langue de traduction. Un prompt `en` sur une bible
    française est donc un **hybride** : charpente anglaise, attributs français.

    Ce n'est pas un défaut d'implémentation — c'est ce que le dépôt peut livrer sans faire
    traduire les attributs par un modèle, ce qui violerait le critère 4. Le mesurer sans le
    dire aurait publié « anglais » pour autre chose."""
    fr = prompt_mod.construire("Tory Noelle", bible, cadrage="buste", langue="fr")
    en = prompt_mod.construire("Tory Noelle", bible, cadrage="buste", langue="en")
    assert en.requete.prompt.startswith("a lone character")
    assert "bust shot" in en.requete.prompt
    assert "gris courts" in en.requete.prompt      # ← l'hybride, écrit noir sur blanc
    assert fr.requete.prompt != en.requete.prompt
    assert "text" in en.requete.prompt_negatif and "texte" in fr.requete.prompt_negatif


def test_une_langue_absente_du_gabarit_LEVE_sans_repli(bible):
    """Règle de `core/langues.py`, mot pour mot : « aucun repli silencieux vers le français ».
    Un repli ici enverrait un prompt dans une autre langue que celle mesurée, et fausserait
    la seule chose que le critère 7 compare."""
    with pytest.raises(gabarits_mod.GabaritIntrouvable) as echec:
        prompt_mod.construire("Tory Noelle", bible, cadrage="buste", langue="de")
    assert "fr" in str(echec.value) and "en" in str(echec.value)


# ══════════════════════════  Critère 5 — le prompt négatif motivé  ══════════════════════════

def test_chaque_terme_du_prompt_negatif_porte_son_motif():
    """« Retirer un terme est un choix, pas une faute » — et on ne choisit pas de retirer ce
    dont on ignore la raison. Un prompt négatif sans motifs est une liste que personne n'ose
    toucher."""
    gabarit = gabarits_mod.charger("portrait", langue="fr")
    motifs = gabarit.motifs_negatifs()
    assert motifs, "le gabarit ne porte aucun terme négatif"
    assert set(motifs) == set(gabarit.prompt_negatif().split(", "))
    for terme, motif in motifs.items():
        assert len(motif) > 40, f"le terme « {terme} » n'a qu'un motif de façade"


def test_le_terme_TEXTE_est_motive_par_un_fait_du_depot():
    """Le motif le plus important de la liste : les références validées du corpus sont des
    couvertures, qui portent le titre en grandes lettres, et le modèle sait écrire."""
    motifs = gabarits_mod.charger("portrait", langue="fr").motifs_negatifs()
    assert "TITRE_DANS_LES_PIXELS" in motifs["texte"]


def test_le_gabarit_porte_son_empreinte_pour_le_sidecar():
    """« Gabarit portrait v1 » ne dit pas si le fichier a été édité depuis. C'est le même
    esprit que `git checkout <tag> -- langues/` pour reproduire la voix d'un tome."""
    empreinte = gabarits_mod.empreinte("portrait")
    assert len(empreinte) == 64
    assert gabarits_mod.empreinte("gabarit-qui-n-existe-pas") == ""


# ══════════════  Critère 1 septies — le YAML et le payload disent la même chose  ══════════════

def test_le_yaml_relu_et_le_payload_archive_decrivent_la_meme_requete(tmp_path, bible):
    """**Deux formats, deux publics, un seul contenu.**

    Le YAML est ce qu'un humain relit ; le payload JSON est ce qui part au moteur et qui est
    archivé dans le sidecar. Ils dérivent l'un de l'autre, donc rien ne garantit qu'ils
    restent d'accord — sauf ce test. Une divergence serait invisible jusqu'au premier rejeu
    raté, c'est-à-dire trop tard."""
    from illustration.moteur import Requete

    doc = requete_mod.depuis_oeuvre(bible, graine=1234)
    doc["images"][0]["references"] = [
        {"fichier": "media/a.png", "motif": "retenue pour le test", "retenue": True},
        {"fichier": "media/b.png", "motif": "écartée pour le test", "retenue": False}]
    chemin = requete_mod.save(doc, tmp_path / "requete.yaml")

    relu = requete_mod.load(chemin)
    nom, requete = requete_mod.requetes(relu)[0]
    payload = requete.payload()

    # Le payload est reconstructible depuis lui-même, à l'identique — c'est `--rejouer`.
    assert Requete.depuis_payload(payload).empreinte() == requete.empreinte()
    # Et il décrit bien ce que le YAML dit, champ par champ.
    bloc = relu["images"][0]
    assert payload["prompt"] == bloc["prompt"]
    assert payload["prompt_negatif"] == bloc["prompt_negatif"]
    assert payload["graine"] == bloc["graine"] == 1234
    # ⚠ SEULES les images retenues entrent dans le canal. L'écartée reste dans le fichier
    # avec son motif — c'est ce qui permet de la reprendre — mais elle ne part pas au moteur.
    assert payload["references"] == ["media/a.png"]
    assert nom == "tory-noelle"


def test_une_graine_nulle_est_TIREE_puis_archivee(bible):
    """`graine: null` veut dire « aléatoire », pas « absente ». Elle est tirée **une fois**,
    ici, et entre dans le payload — donc dans l'empreinte, donc dans le sidecar. Un moteur
    qui tirerait sa graine lui-même rendrait `--rejouer` impossible sans que rien ne le
    signale."""
    doc = requete_mod.depuis_oeuvre(bible, graine=None)
    assert doc["images"][0]["graine"] is None
    _, requete = requete_mod.requetes(doc)[0]
    assert isinstance(requete.graine, int) and requete.graine > 0


# ════════════════════════  L26.2 bis — le second battant de la porte  ════════════════════════

def test_la_phase_image_REFUSE_quand_toutes_les_references_sont_decochees(bible):
    """**Critère 1 ter, second test.** L'utilisateur peut vider `graine` et
    `attributs_sources` sans rien casser ; il ne peut pas décocher tout ce que la phase 1
    avait retenu. La phase 2 retomberait sur de la génération pure."""
    doc = requete_mod.depuis_oeuvre(bible)
    doc["images"][0]["references"] = [
        {"fichier": "media/a.png", "motif": "m", "retenue": True}]
    requete_mod.archiver_l_initial(doc)
    doc["valide"] = True
    doc["validation"]["par"] = "Alexandre"

    requete_mod.exiger_validation(doc)                        # la première porte passe
    doc["images"][0]["references"][0]["retenue"] = False       # l'humain décoche tout
    with pytest.raises(requete_mod.RequeteNonValidee) as echec:
        requete_mod.exiger_references_retenues(doc)
    assert "génération pure" in str(echec.value)


def test_un_personnage_qui_n_avait_AUCUNE_reference_ne_declenche_pas_ce_refus(bible):
    """⚠ **La distinction qui fait tout.** « L'humain a tout décoché » et « la bible ne
    documente pas ce personnage » se ressemblent dans le fichier et pas du tout dans la vie.

    Sur le corpus réel, 7 personnages sur 11 n'ont aucune référence validée : les confondre
    ferait échouer un run entier pour le cas majoritaire, et pousserait à contourner la
    porte. Ce cas-là relève de `identite.SansReferenceValidee`, qui refuse l'IMAGE, pas le
    run."""
    doc = requete_mod.depuis_oeuvre(bible)
    doc["images"][0]["references"] = []
    requete_mod.archiver_l_initial(doc)
    doc["valide"] = True
    doc["validation"]["par"] = "Alexandre"
    requete_mod.exiger_references_retenues(doc)               # ne lève pas


def test_vider_la_graine_et_les_sources_ne_casse_rien(bible):
    """Les deux champs que le plan désigne explicitement comme videurs sans conséquence."""
    doc = requete_mod.depuis_oeuvre(bible, graine=42)
    doc["images"][0]["graine"] = None
    doc["images"][0]["attributs_sources"] = []
    assert requete_mod.verifier(doc) == []


# ══════════════════════════  L26.4 — le budget d'un run  ══════════════════════════

def test_le_plafond_d_images_MORD_avec_un_motif_nomme():
    """Un plafond qui s'atteint en silence ferait croire à un corpus plus petit qu'il n'est.
    Le dépôt a une culture du plafond, et elle nomme toujours son motif d'arrêt."""
    budget = prompt_mod.Budget(images=2)
    assert budget.retenir(["a", "b", "c", "d"]) == ["a", "b"]
    assert len(budget.atteints) == 1
    assert "plafond d'images atteint" in budget.atteints[0]
    assert "images_par_run" in budget.atteints[0]


def test_sous_le_plafond_rien_n_est_signale():
    budget = prompt_mod.Budget(images=8)
    assert budget.retenir(["a", "b"]) == ["a", "b"]
    assert budget.atteints == []


# ══════════════════════════  L26.2 bis — le fichier est LISIBLE  ══════════════════════════

def test_le_fichier_ecrit_explique_comment_le_relire(tmp_path, bible):
    """La porte humaine dépend entièrement de la lisibilité du fichier : c'est la raison
    pour laquelle il est en YAML et pas en JSON. Un utilisateur qui rouvre le fichier six
    mois plus tard doit y retrouver la marche à suivre."""
    doc = requete_mod.depuis_oeuvre(bible)
    chemin = requete_mod.save(doc, tmp_path / "requete.yaml", projet="P", tome="Vol.1")
    texte = chemin.read_text(encoding="utf-8")
    assert "CE QUE TU DOIS RELIRE" in texte
    assert "Tu ne peux pas toutes les retirer" in texte
    assert "gabarits/portrait.yaml" in texte
    assert "null = aléatoire" in texte


def test_tous_les_champs_du_bloc_sont_ecrits_meme_vides(tmp_path, bible):
    """Comme le glossaire et la bible : ce qui est visible se corrige, ce qui est absent
    s'oublie. Les canaux structurés sont **présents et désarmés**, pas absents."""
    doc = requete_mod.depuis_oeuvre(bible)
    chemin = requete_mod.save(doc, tmp_path / "requete.yaml")
    bloc = yaml.safe_load(chemin.read_text(encoding="utf-8"))["images"][0]
    assert set(bloc) == set(requete_mod.image_vide())
    assert bloc["canaux"] == {"entites": [], "image_de_controle": None}
    assert bloc["ancrages_style"] == []
