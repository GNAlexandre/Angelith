# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L27.1 bis — **l'écran de relecture du prompt**, et la porte qu'il ouvre.

Critère 1 bis du `PLAN-27`, en deux moitiés qu'il faut toutes les deux :

1. l'écran montre prompt, prompt négatif, vignettes de référence **avec leur motif**, et la
   source de chaque attribut ;
2. « un test vérifie qu'**aucun chemin de l'interface** ne peut lancer la phase 2 sans passage
   par cet écran ». Ce test-là est double : à l'exécution (`Porte.laissez_passer` lève) et
   statiquement (`ast` sur `gui/atelier.py`), parce qu'aucune des deux formes ne suffit seule
   — la première ne voit pas un second chemin ajouté demain, la seconde ne voit pas un appel
   par `getattr`.
"""
import ast
from pathlib import Path

import pytest

from illustration import relecture
from illustration import requete as requete_mod

RACINE = Path(__file__).resolve().parent.parent


def _doc(**champs):
    doc = requete_mod.vide(modele="factice")
    bloc = requete_mod.image_vide("aya")
    bloc.update({
        "personnage": "Aya", "cadrage": "buste",
        "prompt": "portrait en buste d'une jeune femme, yeux verts",
        "prompt_negatif": "texte, filigrane",
        "references": [
            {"fichier": "media/image3.png", "motif": "gros plan sur le visage",
             "retenue": True, "par": "llm"},
            {"fichier": "media/image9.png", "motif": "✗ couverture avec titre",
             "retenue": False, "par": "llm"}],
        "ancrages_style": [
            {"fichier": "media/decor1.png", "motif": "plan large, aucun visage",
             "retenue": True, "par": "deterministe"}],
        "attributs_sources": [
            {"attribut": "yeux", "valeur": "verts", "texte": "ses yeux verts brillaient",
             "source": "chapters/ch03.md", "certitude": "citee", "origine": "bible"},
            {"attribut": "tenue", "valeur": "manteau sobre", "texte": "", "source": "",
             "origine": "bible"}],
        "graine": 7, "nombre_images": 2})
    bloc.update(champs)
    doc["images"].append(bloc)
    requete_mod.archiver_l_initial(doc)
    return doc


# ─────────────────────────────  Ce que l'écran montre  ─────────────────────────────

def test_l_ecran_porte_les_six_choses_du_plan():
    ecran = relecture.ecrans(_doc())[0]
    assert ecran.prompt.startswith("portrait en buste")
    assert ecran.prompt_initial == ecran.prompt
    assert [t.texte for t in ecran.termes_negatifs] == ["texte", "filigrane"]
    assert [v.fichier for v in ecran.references] == ["media/image3.png", "media/image9.png"]
    assert [v.fichier for v in ecran.ancrages] == ["media/decor1.png"]
    assert [a.attribut for a in ecran.attributs] == ["yeux", "tenue"]
    assert {c.nom for c in ecran.canaux} == {relecture.CANAL_ENTITES,
                                             relecture.CANAL_CONTROLE}
    assert ecran.nombre_images == 2 and ecran.graine == 7


def test_chaque_terme_negatif_porte_le_motif_du_gabarit():
    """« En retirer un est un CHOIX, pas une faute » — encore faut-il savoir ce qu'il
    protège. Les motifs viennent de `illustration/gabarits/portrait.yaml`."""
    ecran = relecture.ecrans(_doc())[0]
    par_texte = {t.texte: t for t in ecran.termes_negatifs}
    assert par_texte["texte"].explique
    assert "le modèle SAIT écrire" in par_texte["texte"].motif


def test_les_deux_groupes_d_images_ne_se_melangent_jamais():
    """Un utilisateur qui décoche une ancre de style doit voir qu'il ne touche pas à
    l'identité, et réciproquement."""
    ecran = relecture.ecrans(_doc())[0]
    assert all(v.groupe == relecture.GROUPE_IDENTITE for v in ecran.references)
    assert all(v.groupe == relecture.GROUPE_STYLE for v in ecran.ancrages)
    assert relecture.TITRES_GROUPE[relecture.GROUPE_STYLE] != \
        relecture.TITRES_GROUPE[relecture.GROUPE_IDENTITE]


def test_chaque_vignette_porte_son_motif_retenue_comme_ecartee():
    """Règle 3 du `PLAN-26` L26.0 : « un utilisateur qui retire une image doit voir pourquoi
    elle avait été prise »."""
    ecran = relecture.ecrans(_doc())[0]
    assert all(v.motif for v in ecran.references)


def test_un_attribut_sans_source_est_une_ANOMALIE_montree_avant_le_clic():
    """« Un attribut sans citation n'est pas une observation » — et s'il est là quand même,
    l'écran le montre plutôt que de le laisser échouer trois écrans plus loin."""
    ecran = relecture.ecrans(_doc())[0]
    fautif = next(a for a in ecran.attributs if a.attribut == "tenue")
    assert fautif.anomalie
    assert "citation" in fautif.motif_anomalie
    assert any("tenue" in a for a in ecran.anomalies)


def test_une_description_ECRITE_PAR_L_HUMAIN_n_est_pas_une_anomalie():
    """`atelier.bloc_libre` étiquette `origine: humain` exactement pour ça : il n'y a pas de
    bible à trahir, c'est l'humain qui écrit."""
    doc = _doc(attributs_sources=[{"attribut": "description", "valeur": "une silhouette",
                                   "texte": "une silhouette", "source": "",
                                   "origine": "humain"}])
    ecran = relecture.ecrans(doc)[0]
    assert not ecran.attributs[0].anomalie


def test_tout_decocher_est_signale_AVANT_le_clic():
    """Le critère 2 du plan : « aucun message d'erreur n'apparaît APRÈS le clic »."""
    doc = _doc()
    doc["images"][0]["references"][0]["retenue"] = False
    ecran = relecture.ecrans(doc)[0]
    assert any("toutes les références" in a for a in ecran.anomalies)


def test_un_gabarit_introuvable_n_empeche_pas_de_relire():
    """Il rend les termes SANS motif, et l'écran le signale — ce qui est exactement la bonne
    réaction : on ne bloque pas une relecture parce qu'un fichier de gabarit manque."""
    doc = _doc()
    doc["gabarit"] = "gabarit-qui-n-existe-pas"
    ecran = relecture.ecrans(doc)[0]
    assert [t.texte for t in ecran.termes_negatifs] == ["texte", "filigrane"]
    assert any("sans motif" in a for a in ecran.anomalies)


# ─────────────────────────────  Corriger et restaurer  ─────────────────────────────

def test_appliquer_corrige_le_prompt_sans_toucher_a_l_original():
    """Le sidecar doit pouvoir montrer l'avant ET l'après : une correction qui réécrirait
    l'original rendrait la traçabilité circulaire."""
    doc = _doc()
    corrige = relecture.appliquer(
        doc, {"aya": relecture.Correction(prompt="tout autre chose")})
    assert corrige["images"][0]["prompt"] == "tout autre chose"
    assert corrige["validation"]["prompt_initial"]["aya"].startswith("portrait en buste")


def test_restaurer_rend_le_prompt_de_la_phase_1():
    """Une correction doit être annulable **sans relancer la phase 1**, qui coûte des minutes
    de LLM."""
    doc = relecture.appliquer(_doc(), {"aya": relecture.Correction(prompt="raté")})
    rendu = relecture.restaurer(doc, "aya")
    assert rendu["images"][0]["prompt"].startswith("portrait en buste")


def test_cocher_et_decocher_porte_sur_des_NOMS_de_fichier_pas_des_indices():
    """Un écran qui réordonne ses vignettes ne doit pas cocher la mauvaise image."""
    doc = relecture.appliquer(_doc(), {"aya": relecture.Correction(
        retenues={"media/image9.png"})})
    par_fichier = {c["fichier"]: c for c in doc["images"][0]["references"]}
    assert par_fichier["media/image9.png"]["retenue"] is True
    assert par_fichier["media/image3.png"]["retenue"] is False


def test_un_canal_se_DESARME_il_ne_s_edite_pas():
    doc = _doc()
    doc["images"][0]["canaux"]["image_de_controle"] = "media/pose.png"
    assert relecture.ecrans(doc)[0].canaux[1].arme
    desarme = relecture.appliquer(doc, {"aya": relecture.Correction(
        canaux_desarmes={relecture.CANAL_CONTROLE})})
    assert desarme["images"][0]["canaux"]["image_de_controle"] is None


def test_graine_aleatoire_et_graine_fixe_sont_deux_valeurs_distinctes():
    doc = relecture.appliquer(_doc(), {"aya": relecture.Correction(graine="aleatoire")})
    assert doc["images"][0]["graine"] is None
    doc = relecture.appliquer(doc, {"aya": relecture.Correction(graine=42)})
    assert doc["images"][0]["graine"] == 42


# ─────────────────────────────────  La porte  ─────────────────────────────────

def test_la_porte_est_fermee_tant_qu_on_n_a_pas_valide():
    porte = relecture.Porte(_doc())
    with pytest.raises(relecture.PorteFermee, match="sans passage par l'écran"):
        porte.laissez_passer()
    assert porte.franchie is False


def test_le_message_de_refus_dit_qu_il_n_y_a_pas_de_generer_directement():
    """⚠ Aucun « générer directement » n'est ajouté, ni bouton, ni raccourci, ni option de
    réglages — pas même pour rejouer une requête déjà validée."""
    porte = relecture.Porte(_doc())
    with pytest.raises(relecture.PorteFermee) as capture:
        porte.laissez_passer()
    assert "générer directement" in str(capture.value)
    assert "--rejouer" in str(capture.value)


def test_valider_exige_un_nom_et_n_a_pas_de_defaut():
    porte = relecture.Porte(_doc())
    with pytest.raises(relecture.PorteFermee, match="nom est requis"):
        porte.valider(par="   ")


def test_valider_ecrit_valide_true_et_qui_et_quand():
    porte = relecture.Porte(_doc())
    doc = porte.valider(par="Alexandre", date="2026-09-02")
    assert doc["valide"] is True
    assert doc["validation"]["par"] == "Alexandre"
    assert doc["validation"]["date"] == "2026-09-02"
    assert porte.laissez_passer()


def test_valider_eprouve_les_DEUX_battants_avant_que_l_interface_annonce_quoi_que_ce_soit():
    """Les laisser à la phase 2 ferait apparaître le refus après le clic."""
    porte = relecture.Porte(_doc())
    with pytest.raises(requete_mod.RequeteNonValidee, match="décochées"):
        porte.valider({"aya": relecture.Correction(retenues=set())}, par="Alexandre")
    with pytest.raises(relecture.PorteFermee):
        porte.laissez_passer()


def test_annuler_ne_detruit_rien():
    """Point 6 de L27.1 bis : un abandon ne détruit pas le travail du LLM."""
    porte = relecture.Porte(_doc())
    porte.valider(par="Alexandre")
    porte.annuler()
    assert porte.document["images"][0]["prompt"].startswith("portrait en buste")
    with pytest.raises(relecture.PorteFermee):
        porte.laissez_passer()


def test_la_porte_refuse_un_requete_yaml_qui_a_change_sous_l_ecran(tmp_path):
    """Le fichier est FAIT pour être édité à la main, et l'atelier console peut l'avoir
    réécrit dans une autre fenêtre. Générer d'après un écran périmé produirait une image que
    personne n'a relue."""
    chemin = tmp_path / "requete.yaml"
    porte = relecture.Porte(_doc())
    doc = porte.valider(par="Alexandre")
    requete_mod.save(doc, chemin, projet="T", tome="")
    porte.verifier_le_disque(chemin)                  # inchangé : aucune levée

    doc["images"][0]["prompt"] = "quelqu'un a édité le fichier entre-temps"
    requete_mod.save(doc, chemin, projet="T", tome="")
    with pytest.raises(relecture.RelectureCaduque, match="a changé depuis"):
        porte.verifier_le_disque(chemin)


def test_l_empreinte_ignore_ce_qui_ne_change_pas_ce_que_le_moteur_recoit():
    """Sinon la porte échouerait parce que quelqu'un a corrigé une faute de frappe dans un
    motif."""
    doc = _doc()
    avant = relecture.empreinte(doc)
    doc["images"][0]["references"][0]["motif"] = "motif réécrit à la main"
    doc["phase1"]["secondes"] = 999.0
    assert relecture.empreinte(doc) == avant


def test_la_trace_de_validation_compte_la_RELECTURE_pas_la_generation():
    porte = relecture.Porte(_doc())
    porte.valider({"aya": relecture.Correction(prompt="un autre prompt",
                                               retenues={"media/image3.png"})},
                  par="Alexandre")
    trace = relecture.trace_de_validation(porte)
    assert trace["par"] == "Alexandre"
    assert trace["prompts_corriges"] == 1
    assert trace["images_decochees_a_l_ecran"] == 0
    assert "ne dit pas" not in trace["avertissement"] or trace["avertissement"]


def test_la_trace_compte_les_images_decochees_a_l_ecran():
    porte = relecture.Porte(_doc())
    doc = porte.valider({"aya": relecture.Correction(retenues={"media/image9.png"})},
                        par="Alexandre")
    assert doc["images"][0]["references"][1]["retenue"] is True
    assert relecture.trace_de_validation(porte)["images_decochees_a_l_ecran"] == 1


# ────────────────  Le contrôle STATIQUE, sur les sources de l'interface  ────────────────

def test_aucun_chemin_de_l_interface_ne_lance_la_phase_2_sans_la_porte():
    """Critère 1 bis, moitié statique. `ast` sur `gui/atelier.py` : toute fonction qui nomme
    `phase_image` doit aussi nommer `laissez_passer`.

    ⚠ Le contrôle d'exécution ne suffit pas : il ne verrait pas un SECOND chemin ajouté
    demain — un bouton « régénérer » posé dans la galerie, par exemple. Celui-ci le verra le
    jour même."""
    source = (RACINE / "gui" / "atelier.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    fautifs = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        corps = ast.dump(noeud)
        if "phase_image" in corps and "laissez_passer" not in corps:
            fautifs.append(f"{noeud.name} (ligne {noeud.lineno})")
    assert fautifs == [], (
        "ces fonctions de gui/atelier.py atteignent phase_image sans passer par "
        f"Porte.laissez_passer : {', '.join(fautifs)}.\n"
        "  C'est le critère 1 bis du PLAN-27 : aucun chemin de l'interface ne peut lancer la "
        "phase 2 sans passage par l'écran de relecture.")


def test_l_interface_n_ecrit_jamais_valide_true_elle_meme():
    """`Porte.valider` est le seul écrivain, et c'est lui qui exige un nom. Un
    `doc["valide"] = True` posé dans le panneau contournerait la porte sans qu'un test
    d'exécution s'en aperçoive."""
    source = (RACINE / "gui" / "atelier.py").read_text(encoding="utf-8")
    assert '"valide"' not in source and "'valide'" not in source


def test_la_console_franchit_la_MEME_porte_que_l_interface():
    """Deux portes, c'est une porte de moins qu'on croit avoir."""
    source = (RACINE / "illustration" / "console.py").read_text(encoding="utf-8")
    assert "relecture_mod.Porte(" in source
    assert "porte.laissez_passer()" in source
    assert 'doc["valide"] = True' not in source
