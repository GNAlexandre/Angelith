# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le lanceur après le `PLAN-33` — formulaire déclaré, run de nuit, modèle, profils.

## Ce que chaque section couvre

| Section | Critère du plan |
|---|---|
| le générateur construit les quatre formulaires | 4 |
| `config.yaml` n'est pas réécrit — empreinte SHA-256 | **6** |
| le run de nuit part du panneau et arrive au socle | 7 |
| rien de coûteux n'est persisté, y compris `shutdown` | 8 |
| le sélecteur de modèle n'écrit rien et dit « inconnu » | 9 |
| la destination Webtoon et ses trois réglages de bande | 10 |
| aucune boîte de confirmation n'annonce une durée | 11 |

⚠ `QT_QPA_PLATFORM=offscreen` avant toute `QApplication`, et `$ANGELITH_REGLAGES` /
`$ANGELITH_PROFILS` sur le `tmp_path` de chaque test : sans cela ces tests écriraient dans le
dépôt de qui les lance.
"""
from __future__ import annotations

import hashlib
import os

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox                       # noqa: E402

from core import modeles as mod                                              # noqa: E402
from gui import formulaire as frm                                            # noqa: E402
from gui import parametres as par                                            # noqa: E402
from gui import profils as prf                                               # noqa: E402
from gui import reglages as reg                                              # noqa: E402
from gui.lanceur import PanneauLanceur, panneau_de                           # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isoler(tmp_path, monkeypatch):
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    monkeypatch.setenv(prf.VARIABLE, str(tmp_path / "profils.json"))


def _config(tmp_path) -> dict:
    return {
        "manga": {"chemins": {"sources": str(tmp_path / "sources"),
                              "build": str(tmp_path / "build")},
                  "lot": {"planches": 3},
                  "modeles": {"manga_traducteur": {"model": "yume-27b"},
                              "manga_contexte": {"model": "yume-27b",
                                                 "endpoint": "reflexion"},
                              "correcteur": None},
                  "formats": {"webtoon": {"detection": {"fenetre_hauteur": 2160,
                                                        "fenetre_recouvrement": 900,
                                                        "fenetre_ratio_min": 3.0},
                                          "rendu": {"sens_lecture": "gauche_droite"}}}},
        "modeles": {"traducteur": {"model": "yume-27b", "endpoint": "reflexion"}},
        "chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path / "build")},
        "langues": {"dossiers": {"JAP": "jp", "ENG": "en"}},
        "llm": {"base_url": "http://localhost:11434/v1"},
        "options": {},
    }


def _panneau(tmp_path, destination="manga"):
    brique, format_planche = {"light_novel": ("ln", None), "manga": ("manga", None),
                              "webtoon": ("manga", "webtoon")}[destination]
    from gui.lanceur import RESERVE_WEBTOON
    return PanneauLanceur(_config(tmp_path), brique=brique, format_planche=format_planche,
                          reserve=RESERVE_WEBTOON if destination == "webtoon" else "")


def _catalogue(vision=True):
    return mod.Catalogue(mod.JOIGNABLE,
                         (mod.Modele("yume-27b:latest", vision=vision,
                                     contexte_modele=262144, source="Ollama /api/tags"),
                          mod.Modele("qwen3.5:9b-q8_0", vision=None)),
                         "http://localhost:11434/v1/models")


# --------------------------------------------------------------------------- #
#  Critère 4 — un seul générateur construit les quatre formulaires
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("destination", ["light_novel", "manga", "webtoon"])
def test_chaque_parametre_declare_a_son_widget(qt_app, tmp_path, destination):
    """**Le test qui aurait échoué avant le lot 33** : le lanceur exposait sept réglages utiles
    là où la table en déclare jusqu'à seize, et rien ne le disait."""
    panneau = _panneau(tmp_path, destination)
    for parametre in par.pour(panneau.panneau()):
        widget = getattr(panneau, parametre.attribut, None)
        assert widget is not None, f"{destination}.{parametre.identifiant}"
        assert panneau.formulaire.widget(parametre.identifiant) is widget


@pytest.mark.parametrize("destination", ["light_novel", "manga", "webtoon"])
def test_le_parcours_declare_couvre_tous_les_parametres(qt_app, tmp_path, destination):
    """`PARCOURS` est l'UNION des quatre panneaux ; aucun paramètre déclaré ne doit y manquer,
    sinon un contrôle ajouté demain tomberait en fin de parcours de tabulation sans qu'on
    l'ait décidé (critère 6 du `PLAN-19`)."""
    panneau = _panneau(tmp_path, destination)
    attendus = {p.attribut for p in par.pour(panneau.panneau())}
    assert attendus <= set(PanneauLanceur.PARCOURS), attendus - set(PanneauLanceur.PARCOURS)


def test_l_infobulle_porte_l_equivalent_en_ligne_de_commande(qt_app, tmp_path):
    """L18.9, appliquée aux dix-neuf paramètres au lieu de trois — parce qu'une seule fonction
    les fabrique."""
    panneau = _panneau(tmp_path, "manga")
    for parametre in par.pour(par.MANGA):
        if not parametre.equivalent:
            continue
        infobulle = getattr(panneau, parametre.attribut).toolTip()
        assert parametre.equivalent in infobulle, parametre.identifiant


def test_le_texte_special_dit_ce_que_vaut_le_defaut(qt_app, tmp_path):
    """« Le champ dit CE QUE vaut le défaut, pas seulement qu'il en existe un » — la règle du
    lot 31, généralisée par le générateur."""
    webtoon = _panneau(tmp_path, "webtoon")
    assert "2160" in webtoon.champ_fenetre_hauteur.specialValueText()
    assert "900" in webtoon.champ_fenetre_recouvrement.specialValueText()
    # …et le lot lit `manga.lot.planches`, qui vaut 3 dans cette configuration de test.
    assert "3" in webtoon.champ_lot.specialValueText()


def test_les_seuils_de_detection_sont_grises_sans_planche_unique(qt_app, tmp_path):
    """⚠ « Le formulaire le dit pendant qu'on remplit, pas une fois le GPU engagé. »
    `process_volume` refuse `conf_threshold` sans `only_page`, après avoir chargé son modèle
    de détection."""
    panneau = _panneau(tmp_path, "manga")
    assert panneau.champ_conf.isEnabled() is False
    assert panneau.champ_iou.isEnabled() is False
    panneau.champ_page.setValue(12)
    assert panneau.champ_conf.isEnabled() is True
    panneau.champ_page.setValue(0)
    assert panneau.champ_conf.isEnabled() is False


def test_le_delai_est_grise_sans_extinction(qt_app, tmp_path):
    panneau = _panneau(tmp_path, "manga")
    assert panneau.champ_delai.isEnabled() is False
    panneau.case_extinction.setChecked(True)
    assert panneau.champ_delai.isEnabled() is True


def test_le_light_novel_n_offre_ni_lot_ni_bande(qt_app, tmp_path):
    """Un levier sans effet est pire qu'un levier absent : `run.py` ne connaît ni `--lot`, ni
    `--conf`, ni le découpage des bandes."""
    panneau = _panneau(tmp_path, "light_novel")
    for absent in ("champ_lot", "choix_think", "champ_conf", "champ_iou",
                   "champ_fenetre_hauteur", "choix_langue"):
        assert not hasattr(panneau, absent), absent
    assert hasattr(panneau, "champ_page")     # « Chapitre unique », même widget


def test_panneau_de_encode_que_le_webtoon_est_un_format():
    assert panneau_de("manga", None) == par.MANGA
    assert panneau_de("manga", "webtoon") == par.WEBTOON
    assert panneau_de("ln", None) == par.LIGHT_NOVEL


def test_une_brique_inconnue_est_refusee_a_la_construction(qt_app, tmp_path):
    with pytest.raises(KeyError):
        PanneauLanceur(_config(tmp_path), brique="scan")


# --------------------------------------------------------------------------- #
#  Critère 6 — config.yaml n'est PAS réécrit
# --------------------------------------------------------------------------- #

def test_config_yaml_garde_son_empreinte_apres_un_run_avec_chaque_parametre(qt_app,
                                                                            tmp_path,
                                                                            monkeypatch):
    """**Critère 6, et il porte sur le VRAI fichier.**

    ⚠ L'interdit n° 5 du dépôt : « `config.yaml` est un document. 95 Ko dont l'essentiel est
    de la prose commentée qui justifie chaque valeur par un chiffre. Un aller-retour
    `yaml.safe_dump` l'effacerait. » Le test lance un run depuis le panneau avec **chaque**
    paramètre modifié, et compare l'empreinte SHA-256 du fichier avant et après."""
    import yaml

    chemin = "config.yaml"
    avant = hashlib.sha256(open(chemin, "rb").read()).hexdigest()
    with open(chemin, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    panneau = PanneauLanceur(config, brique="manga", format_planche="webtoon")
    panneau.choix_projet.addItem("P")
    panneau.choix_tome.addItem("Vol.1")
    # Chaque paramètre du panneau est déplacé de son défaut.
    for parametre in par.pour(par.WEBTOON):
        widget = getattr(panneau, parametre.attribut)
        if parametre.genre == par.BASCULE:
            widget.setChecked(not widget.isChecked())
        elif parametre.genre == par.CHOIX:
            widget.setCurrentIndex(min(1, widget.count() - 1))
        else:
            widget.setValue(min(widget.maximum(), max(widget.minimum() + 1,
                                                      widget.minimum() + 5)))
    monkeypatch.setattr(panneau, "_confirmer", lambda p, t: True)
    recus = []
    panneau.demande_run.connect(recus.append)
    panneau.bouton_lancer.click()

    assert recus, "le run n'est pas parti"
    apres = hashlib.sha256(open(chemin, "rb").read()).hexdigest()
    assert apres == avant, "config.yaml a été réécrit par un run lancé depuis l'interface"
    # …et la config EN MÉMOIRE du panneau n'a pas bougé non plus : c'est une COPIE qui part.
    assert recus[0]["config"] is not panneau.config
    assert panneau.config["manga"]["lot"]["planches"] == \
        config["manga"]["lot"]["planches"]


def test_la_config_du_run_est_une_copie_profonde(qt_app, tmp_path, monkeypatch):
    """« Les réglages de ce run ne doivent pas rester collés à la config partagée avec
    l'éditeur, qui construit ses propres agents. »"""
    panneau = _panneau(tmp_path, "manga")
    panneau.champ_lot.setValue(20)
    demande = panneau.demande()
    assert demande.config["manga"]["lot"]["planches"] == 20
    assert panneau.config["manga"]["lot"]["planches"] == 3


# --------------------------------------------------------------------------- #
#  Critère 7 — le run de nuit
# --------------------------------------------------------------------------- #

def test_le_run_de_nuit_part_du_panneau(qt_app, tmp_path, monkeypatch):
    """L'interface graphique était **la seule des trois** à ne pas pouvoir lancer un run de
    nuit, dans un dépôt qui a une branche nommée `run-de-nuit-v1.7.0`."""
    panneau = _panneau(tmp_path, "manga")
    panneau.choix_projet.addItem("P")
    panneau.choix_tome.addItem("Vol.1")
    panneau.case_veille.setChecked(True)
    panneau.case_extinction.setChecked(True)
    panneau.champ_delai.setValue(300)
    monkeypatch.setattr(panneau, "_confirmer", lambda p, t: True)
    recus = []
    panneau.demande_run.connect(recus.append)
    panneau.bouton_lancer.click()
    assert recus[0]["energie"] == {"keep_awake": True, "shutdown": True,
                                   "shutdown_delay": 300}


def test_la_confirmation_nomme_le_delai_d_extinction(qt_app, tmp_path, monkeypatch):
    """L33.2 : « une confirmation qui nomme le délai »."""
    panneau = _panneau(tmp_path, "manga")
    panneau.case_extinction.setChecked(True)
    panneau.champ_delai.setValue(300)
    vus = []
    monkeypatch.setattr(QMessageBox, "setInformativeText", lambda self, t: vus.append(t))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    panneau._confirmer("P", "Vol.1")
    assert vus and "5 min" in vus[0]
    assert "ÉTEINDRA" in vus[0]


# --------------------------------------------------------------------------- #
#  Critère 8 — ce qui ne se persiste jamais
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("destination", ["light_novel", "manga", "webtoon"])
def test_ni_force_ni_dry_run_ni_extinction_ne_survivent(qt_app, tmp_path, destination):
    """La case « Éteindre le PC » retrouvée cochée demain, c'est une machine éteinte que
    personne n'a redemandée. Elle rejoint `force` et `dry_run` dans les non-persistés."""
    panneau = _panneau(tmp_path, destination)
    panneau.case_force.setChecked(True)
    panneau.case_dry.setChecked(True)
    panneau.case_extinction.setChecked(True)
    etat = panneau.reglages_persistables()
    assert "force" not in etat and "dry_run" not in etat and "shutdown" not in etat
    # …et le fichier lavé par `reglages.nettoyer` ne les fait pas revenir non plus.
    assert reg.nettoyer({"runs": {destination: {**etat, "force": True,
                                                "dry_run": True}}})["runs"][destination] \
        .get("force") is None

    # Réappliquer l'état repose les cases à zéro, explicitement.
    autre = _panneau(tmp_path, destination)
    autre.appliquer_reglages({**etat, "force": True, "dry_run": True, "shutdown": True})
    assert autre.case_force.isChecked() is False
    assert autre.case_dry.isChecked() is False
    assert autre.case_extinction.isChecked() is False


def test_le_raisonnement_persiste_relit_un_ancien_INDEX(qt_app, tmp_path):
    """⚠ Compatibilité : `think` était l'INDEX de la liste (lot 18), il est sa VALEUR (lot 33).

    Bumper `reglages.VERSION` aurait fait perdre au passage la taille de fenêtre, les colonnes
    et les récents de tout le monde — pour une clé. Les cinq index historiques sont donc
    traduits : `[None, False, "low", "medium", "high"]`."""
    panneau = _panneau(tmp_path, "manga")
    panneau.appliquer_reglages({"think": 4})            # index 4 = « high »
    assert panneau.choix_think.currentData() == "high"
    panneau.appliquer_reglages({"think": 1})            # index 1 = « désactivé »
    assert panneau.choix_think.currentData() is False
    # …et la nouvelle forme, elle, passe telle quelle.
    panneau.appliquer_reglages({"think": "medium"})
    assert panneau.choix_think.currentData() == "medium"


def test_un_profil_se_choisit_et_s_applique(qt_app, tmp_path):
    panneau = _panneau(tmp_path, "manga")
    panneau.champ_lot.setValue(15)
    panneau.case_veille.setChecked(True)
    panneau._enregistrer_profil_pour_test("nuit complète")
    autre = _panneau(tmp_path, "manga")
    index = autre.choix_profil.findData("nuit complète")
    assert index > 0, "le profil n'apparaît pas dans la liste"
    autre.choix_profil.setCurrentIndex(index)
    assert autre.champ_lot.value() == 15
    assert autre.case_veille.isChecked() is True


# --------------------------------------------------------------------------- #
#  Critère 9 — le sélecteur de modèle
# --------------------------------------------------------------------------- #

def test_sans_sonde_la_liste_ne_propose_que_config_yaml(qt_app, tmp_path):
    """« Inconnu » n'est pas « aucun modèle » : la liste offre le seul choix qui reste juste,
    et c'est déjà celui qui est fait."""
    panneau = _panneau(tmp_path, "manga")
    assert panneau.choix_modele.count() == 1
    assert panneau.choix_modele.currentData() is None
    assert "non encore demandée" in panneau.etiquette_modeles.text()


def test_la_liste_arrive_apres_coup_sans_defaire_le_choix(qt_app, tmp_path):
    """Une liste qui arrive en retard ne doit pas défaire ce que l'utilisateur vient de
    choisir — la sonde part dans le fil de travail, elle peut répondre à tout moment."""
    panneau = _panneau(tmp_path, "manga")
    panneau.poser_modeles(_catalogue())
    assert panneau.choix_modele.count() == 3
    panneau.choix_modele.setCurrentIndex(1)
    assert panneau.choix_modele.currentData() == "yume-27b:latest"
    panneau.poser_modeles(_catalogue())
    assert panneau.choix_modele.currentData() == "yume-27b:latest"


def test_la_capacite_vision_inconnue_est_ECRITE_et_pas_devinee(qt_app, tmp_path):
    """⚠ « Si la sonde ne sait pas dire qu'un modèle est vision-capable, l'interface affiche
    "capacité vision inconnue" et **avertit** quand la brique manga en dépend. Elle ne filtre
    pas la liste sur une devinette. »"""
    panneau = _panneau(tmp_path, "manga")
    panneau.poser_modeles(_catalogue())
    libelles = [panneau.choix_modele.itemText(i)
                for i in range(panneau.choix_modele.count())]
    assert any("vision : inconnu" in t for t in libelles)
    assert any("vision : oui" in t for t in libelles)
    # …et le modèle à vision inconnue est TOUJOURS dans la liste : on n'a pas filtré.
    assert any("qwen3.5:9b-q8_0" in t for t in libelles)


def test_le_recapitulatif_nomme_les_agents_outrepasses(qt_app, tmp_path, monkeypatch):
    """« Un sélecteur global qui écraserait un endpoint spécialisé sans le dire est pire que
    pas de sélecteur » — donc il le dit, agent par agent."""
    panneau = _panneau(tmp_path, "manga")
    panneau.poser_modeles(_catalogue(vision=None))
    panneau.choix_modele.setCurrentIndex(2)          # qwen3.5:9b-q8_0, vision inconnue
    vus = []
    monkeypatch.setattr(QMessageBox, "setInformativeText", lambda self, t: vus.append(t))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    panneau._confirmer("P", "Vol.1")
    assert "manga_traducteur" in vus[0] and "manga_contexte" in vus[0]
    assert "Capacité vision INCONNUE" in vus[0]
    assert "config.yaml n'est pas modifié" in vus[0]


def test_l_endpoint_d_un_agent_survit_au_choix_de_modele(qt_app, tmp_path):
    panneau = _panneau(tmp_path, "manga")
    panneau.poser_modeles(_catalogue())
    panneau.choix_modele.setCurrentIndex(1)
    demande = panneau.demande()
    agent = demande.config["manga"]["modeles"]["manga_contexte"]
    assert agent["model"] == "yume-27b:latest"
    assert agent["endpoint"] == "reflexion", "l'endpoint de raisonnement a été effacé"


# --------------------------------------------------------------------------- #
#  Critère 10 — la destination Webtoon
# --------------------------------------------------------------------------- #

def test_le_webtoon_affiche_ses_trois_reglages_de_bande_avec_leurs_chiffres(qt_app, tmp_path):
    """Deux modifiables (hauteur, recouvrement) et un affiché (le seuil d'entrée du
    découpage) — parce que ce troisième n'a **aucun équivalent en ligne de commande**, et
    qu'un levier sans équivalent casserait la promesse de `gui/__init__.py`."""
    webtoon = _panneau(tmp_path, "webtoon")
    texte = webtoon.etiquette_bande.text()
    assert "3.0" in texte and "213,3 px" in texte
    assert "non modifiable" in texte
    assert "gauche → droite" in texte
    assert "reprendre toutes ses planches à la détection" in texte
    # Et les deux modifiables portent leurs chiffres MESURÉS dans leur infobulle.
    assert "7,1 s" in webtoon.champ_fenetre_hauteur.toolTip()
    assert "833 px" in webtoon.champ_fenetre_recouvrement.toolTip()


def test_la_reserve_webtoon_reste_en_tete(qt_app, tmp_path):
    webtoon = _panneau(tmp_path, "webtoon")
    texte = webtoon.bandeau.text()
    assert "15,1" in texte and "5,9" in texte and "webtoon-2026-08-26" in texte
    assert not hasattr(_panneau(tmp_path, "manga"), "bandeau")


# --------------------------------------------------------------------------- #
#  Critère 11 — aucune durée annoncée
# --------------------------------------------------------------------------- #

def test_aucune_confirmation_n_annonce_une_duree_de_run(qt_app, tmp_path, monkeypatch):
    """**Le refus du lot 18, gardé.** « Aucune constante mesurée ne couvre un run complet,
    dont le coût dépend du nombre de planches, du modèle et de l'étape — l'annoncer serait
    inventer un chiffre. »

    Ce qui EST affiché porte son dénominateur : le coût de `--force` vient de la table, et il
    dit « des heures sur un tome complet » avec la mesure qui le fonde."""
    panneau = _panneau(tmp_path, "manga")
    panneau.case_force.setChecked(True)
    vus = []
    monkeypatch.setattr(QMessageBox, "setInformativeText", lambda self, t: vus.append(t))
    monkeypatch.setattr(QMessageBox, "setText", lambda self, t: vus.append(t))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    panneau._confirmer("P", "Vol.1")
    texte = "\n".join(vus)
    for invente in ("minutes environ", "≈", "temps estimé", "durée estimée"):
        assert invente not in texte, invente
    # Le coût de --force est affiché AVEC son dénominateur, ce qui est l'inverse d'un chiffre
    # inventé : il nomme le tome complet et le fichier qui le mesure.
    assert "des heures sur un tome complet" in texte
    assert "config.yaml" in texte


def test_tout_cout_declare_porte_son_denominateur():
    """La règle §5 du contexte agent, appliquée à la table : « un chiffre sans dénominateur
    n'est pas une mesure, c'est une impression »."""
    import re

    for parametre in par.parametres():
        if not parametre.cout:
            continue
        if not re.search(r"\d", parametre.cout):
            continue
        assert any(mot in parametre.cout
                   for mot in ("tome", "planche", "bande", "page", "config.yaml", "image")), \
            f"{parametre.identifiant} : chiffre sans dénominateur — {parametre.cout!r}"


# --------------------------------------------------------------------------- #
#  Le générateur lui-même
# --------------------------------------------------------------------------- #

def test_le_generateur_refuse_un_panneau_inconnu():
    with pytest.raises(KeyError):
        frm.Formulaire("onglet_fantome")


def test_un_jeu_dynamique_absent_donne_selon_config_yaml(qt_app):
    """Le comportement voulu quand le serveur ne répond pas : la liste offre le seul choix qui
    reste juste, et elle ne se grise pas."""
    from PySide6.QtWidgets import QWidget

    hote = QWidget()
    formulaire = frm.Formulaire(par.MANGA)
    formulaire.construire(hote)
    assert hote.choix_modele.count() == 1
    assert hote.choix_modele.currentData() is None
    assert hote.choix_modele.isEnabled() is True


def test_une_valeur_hors_bornes_est_ignoree_et_non_fatale(qt_app):
    """Le fichier est éditable à la main : une disposition abîmée ne doit pas empêcher de
    lancer un run."""
    from PySide6.QtWidgets import QWidget

    hote = QWidget()
    formulaire = frm.Formulaire(par.MANGA)
    formulaire.construire(hote)
    formulaire.appliquer({"lot": 9999, "verbose": "peut-être", "inconnu": 1})
    assert hote.champ_lot.value() == 0            # inchangé — « selon config.yaml »
    assert isinstance(hote.case_verbose.isChecked(), bool)


def test_les_valeurs_rendent_None_pour_selon_config_yaml(qt_app):
    """⚠ Un `None` est une réponse, pas un trou : c'est `parametres.appliquer()` qui décide de
    ne pas poser la clé, et il ne peut le décider que si la valeur lui parvient."""
    from PySide6.QtWidgets import QWidget

    hote = QWidget()
    formulaire = frm.Formulaire(par.MANGA)
    formulaire.construire(hote)
    valeurs = formulaire.valeurs()
    assert set(valeurs) == {p.identifiant for p in par.pour(par.MANGA)}
    assert valeurs["think"] is None
    assert valeurs["lot"] == 0                    # la valeur SPÉCIALE, pas None


def _enregistrer_profil_pour_test(self, nom):
    """Raccourci de test : `_enregistrer_profil` passe par un `QInputDialog` modal."""
    prf.enregistrer(nom, self.panneau(), self.formulaire.valeurs_persistables())
    self._recharger_profils(nom)


PanneauLanceur._enregistrer_profil_pour_test = _enregistrer_profil_pour_test
