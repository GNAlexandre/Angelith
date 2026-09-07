# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La table des paramètres de run — **critères 4, 5 et 8 du `PLAN-33`**.

Aucun import Qt : c'est la règle de couche du dépôt (`gui/__init__.py`), et c'est ce qui fait
que ces tests tournent dans le job de CI qui n'installe pas PySide6.
"""
import copy

import pytest
import yaml

from gui import parametres as par


def _config():
    """La VRAIE `config.yaml` du dépôt. ⚠ Pas un dictionnaire de test : le critère 5 porte sur
    ce que le formulaire pose dans la configuration réelle, dont la forme est le seul enjeu."""
    with open("config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------- #
#  Critère 4 — la table est cohérente
# --------------------------------------------------------------------------- #

def test_aucun_identifiant_n_est_declare_deux_fois_pour_un_panneau():
    """Critère 4, deuxième moitié. Deux déclarations pour un panneau donneraient deux widgets
    portant la même clé : le second écraserait le premier dans `valeurs()`, en silence."""
    for panneau in par.PANNEAUX:
        identifiants = [p.identifiant for p in par.pour(panneau)]
        doublons = {i for i in identifiants if identifiants.count(i) > 1}
        assert doublons == set(), f"{panneau} : {doublons}"


def test_aucun_attribut_de_widget_n_est_declare_deux_fois_pour_un_panneau():
    """Même règle sur `attribut` : deux paramètres qui poseraient `self.champ_page` sur le
    même panneau feraient que le second gagne, et le premier deviendrait inatteignable.

    ⚠ Le même attribut sur DEUX panneaux est en revanche voulu et testé plus bas : `page`
    (manga) et `chapitre` (light novel) partagent `champ_page`, parce que c'est la même ligne
    du même formulaire, avec le mot juste de chaque brique."""
    for panneau in par.PANNEAUX:
        attributs = [p.attribut for p in par.pour(panneau)]
        doublons = {a for a in attributs if attributs.count(a) > 1}
        assert doublons == set(), f"{panneau} : {doublons}"


def test_page_et_chapitre_partagent_leur_widget_sans_partager_leur_panneau():
    page = par.par_identifiant(par.MANGA, "page")
    chapitre = par.par_identifiant(par.LIGHT_NOVEL, "chapitre")
    assert page.attribut == chapitre.attribut == "champ_page"
    assert par.par_identifiant(par.LIGHT_NOVEL, "page") is None
    assert par.par_identifiant(par.MANGA, "chapitre") is None
    assert (page.equivalent, chapitre.equivalent) == ("--page N", "--chapitre N")


def test_chaque_parametre_a_un_libelle_qui_dit_l_effet():
    """L18.9 : « le libellé dit l'EFFET, l'infobulle garde l'équivalent en ligne de commande ».

    Un libellé qui contient `--` est un nom de drapeau, pas un effet."""
    for parametre in par.parametres():
        assert parametre.libelle, parametre.identifiant
        assert "--" not in parametre.libelle, parametre.identifiant
        assert parametre.genre in par.GENRES, parametre.identifiant
        assert parametre.panneaux, parametre.identifiant
        assert set(parametre.panneaux) <= set(par.PANNEAUX), parametre.identifiant
        assert parametre.groupe in dict(par.GROUPES), parametre.identifiant


def test_chaque_parametre_a_une_infobulle_ou_un_equivalent():
    """Une case sans un mot d'explication ET sans équivalent CLI est une case qu'on ne peut
    pas comprendre sans lire le code."""
    for parametre in par.parametres():
        assert parametre.infobulle or parametre.equivalent, parametre.identifiant


def test_une_liste_a_des_entrees_gelees_ou_dynamiques_mais_pas_les_deux():
    for parametre in par.parametres():
        if parametre.genre != par.CHOIX:
            assert not parametre.choix and not parametre.choix_dynamiques
            continue
        assert bool(parametre.choix) != bool(parametre.choix_dynamiques), \
            parametre.identifiant


def test_un_controle_numerique_a_des_bornes_utilisables():
    for parametre in par.parametres():
        if parametre.genre not in (par.ENTIER, par.REEL):
            continue
        assert parametre.maximum > parametre.minimum, parametre.identifiant
        if parametre.defaut is not None:
            assert parametre.minimum <= parametre.defaut <= parametre.maximum, \
                parametre.identifiant


def test_un_prerequis_existe_sur_le_meme_panneau():
    """`--conf` exige `--page` : sur un panneau où `page` n'existerait pas, le grisage ne
    s'armerait jamais et le champ resterait actif — donc refusé par l'orchestrateur, après le
    chargement du modèle."""
    for panneau in par.PANNEAUX:
        for parametre in par.pour(panneau):
            if parametre.exige:
                assert par.par_identifiant(panneau, parametre.exige) is not None, \
                    f"{panneau}.{parametre.identifiant} exige {parametre.exige}"


def test_les_quatre_panneaux_ont_un_formulaire():
    for panneau in par.PANNEAUX:
        assert par.pour(panneau), panneau
        assert par.groupes_de(panneau), panneau


def test_les_groupes_sortent_dans_l_ordre_declare():
    rang = {cle: n for n, (cle, _) in enumerate(par.GROUPES)}
    for panneau in par.PANNEAUX:
        rangs = [rang[p.groupe] for p in par.pour(panneau)]
        assert rangs == sorted(rangs), panneau


# --------------------------------------------------------------------------- #
#  Critère 5 — « selon config.yaml » NE POSE PAS la clé
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("panneau", par.PANNEAUX)
def test_les_defauts_ne_posent_aucune_cle(panneau):
    """**Critère 5.** Un formulaire laissé tel quel doit produire un run **iso** à celui de la
    ligne de commande sans drapeau. La preuve est une comparaison de dictionnaires, pas une
    inspection à l'œil : `config` avant et après doivent être égaux, sauf `options`, que
    `--dry-run` / `--verbose` posent aussi en ligne de commande."""
    avant = _config()
    apres = copy.deepcopy(avant)
    par.appliquer(apres, panneau, par.defauts(panneau))
    apres.pop("options", None)
    attendu = copy.deepcopy(avant)
    attendu.pop("options", None)
    assert apres == attendu, (
        f"{panneau} : le formulaire par défaut a modifié config.yaml en mémoire")


@pytest.mark.parametrize("panneau", par.PANNEAUX)
def test_chaque_parametre_a_trois_etats_sait_ne_rien_poser(panneau):
    """Le même test, paramètre par paramètre : la valeur SPÉCIALE d'un contrôle numérique à
    trois états (son minimum) veut dire « n'y touche pas », pas « zéro ».

    ⚠ La règle était écrite pour le seul menu `--think` — « elle ne pose pas la clé du tout,
    parce que poser `think: false` écraserait aussi l'`endpoint:` de l'agent ». Elle vaut ici
    pour les six paramètres à trois états des quatre panneaux."""
    trois_etats = [p for p in par.pour(panneau) if p.trois_etats]
    assert trois_etats, f"{panneau} n'a aucun paramètre à trois états ?"
    for parametre in trois_etats:
        valeurs = par.defauts(panneau)
        if parametre.genre in (par.ENTIER, par.REEL):
            valeurs[parametre.identifiant] = parametre.minimum
        avant = _config()
        apres = copy.deepcopy(avant)
        par.appliquer(apres, panneau, valeurs)
        apres.pop("options", None)
        attendu = copy.deepcopy(avant)
        attendu.pop("options", None)
        assert apres == attendu, f"{panneau}.{parametre.identifiant} a posé une clé"


def test_le_lot_et_le_raisonnement_atterrissent_ou_run_manga_les_ecrit():
    """…et QUAND on les règle, ils vont exactement là où `run_manga._appliquer_options_lot`
    les écrit. Deux emplacements différents feraient qu'un tome lancé à l'écran ne se
    relancerait pas à l'identique en ligne de commande."""
    config = _config()
    par.appliquer(config, par.MANGA, {**par.defauts(par.MANGA), "lot": 20, "think": "high"})
    assert config["manga"]["lot"]["planches"] == 20
    assert config["manga"]["lot"]["think"] == "high"


def test_le_raisonnement_desactive_pose_bien_false():
    """« désactivé » n'est PAS « selon config.yaml » : il pose `think: false`, ce que
    `--think` ne sait pas faire mais que le menu offre depuis le lot 18. Le distinguer de
    l'absence de clé est tout l'objet de la règle des trois états."""
    config = _config()
    par.appliquer(config, par.MANGA, {**par.defauts(par.MANGA), "think": False})
    assert config["manga"]["lot"]["think"] is False


def test_les_reglages_de_bande_vont_dans_le_bloc_du_format():
    """⚠ `manga/formats.py:config_format` fusionne `manga.detection` avec
    `manga.formats.<format>.detection`, le second l'emportant : écrire dans le premier
    laisserait un bloc de format écraser silencieusement ce qu'on vient de régler."""
    from manga import formats as fmt

    config = _config()
    par.appliquer(config, par.WEBTOON,
                  {**par.defauts(par.WEBTOON), "fenetre_hauteur": 3000,
                   "fenetre_recouvrement": 1200},
                  format_planche="webtoon")
    assert config["manga"]["formats"]["webtoon"]["detection"]["fenetre_hauteur"] == 3000
    resolu = fmt.config_format(config, "webtoon", "detection")
    assert (resolu["fenetre_hauteur"], resolu["fenetre_recouvrement"]) == (3000, 1200)


# --------------------------------------------------------------------------- #
#  Les seuils de détection exigent une planche — et l'impliquent
# --------------------------------------------------------------------------- #

def test_les_seuils_sont_ecartes_quand_la_portee_est_le_tome():
    """`process_volume` les REFUSE sans `only_page`, après avoir chargé son modèle de
    détection. Les écarter ici est ce qui évite d'apprendre le refus au bout de trente
    secondes de chargement."""
    demande = par.appliquer(_config(), par.MANGA,
                            {**par.defauts(par.MANGA), "conf": 0.35, "iou": 0.5, "page": 0})
    assert "conf" not in demande.arguments and "iou" not in demande.arguments
    assert demande.arguments["page"] is None


def test_un_seuil_sur_une_planche_implique_la_detection():
    """« Ils exigent `only_page` et impliquent `--from detection` » — le contrat de
    `process_volume`, appliqué avant l'appel plutôt que découvert après."""
    demande = par.appliquer(_config(), par.MANGA,
                            {**par.defauts(par.MANGA), "conf": 0.35, "page": 12,
                             "depuis": "rendu"})
    assert demande.arguments["conf"] == 0.35
    assert demande.arguments["page"] == 12
    assert demande.arguments["depuis"] == "detection"


# --------------------------------------------------------------------------- #
#  Critère 8 — ce qui ne se persiste jamais
# --------------------------------------------------------------------------- #

def test_force_dry_run_et_shutdown_ne_se_persistent_pas():
    """**Critère 8.** Le motif de `force` est chiffré et vaut pour les trois : « des heures de
    GPU pour un état que personne n'a redemandé » — et, pour `shutdown`, une machine éteinte
    que personne n'a redemandée."""
    for panneau in (par.LIGHT_NOVEL, par.MANGA, par.WEBTOON):
        refuses = par.non_persistes(panneau)
        assert {"force", "dry_run", "shutdown"} <= refuses, panneau
        garde = par.persistables(panneau, {"force": True, "dry_run": True, "shutdown": True,
                                           "verbose": True})
        assert garde == {"verbose": True}, panneau
    # ⚠ Et le filtre ne garde QUE ce que le panneau déclare : un « lot de 20 » persisté sous
    # la destination Light novel, qui ne connaît pas les planches, serait un réglage sans
    # destinataire — c'est la raison qui a fait passer `runs` à un dictionnaire par
    # destination au lot 31.
    assert par.persistables(par.MANGA, {"lot": 8}) == {"lot": 8}
    assert par.persistables(par.LIGHT_NOVEL, {"lot": 8}) == {}


def test_la_portee_et_la_graine_ne_se_persistent_pas_non_plus():
    """`page` : rouvrir demain sur « la planche 37 » relancerait un tome d'une planche sans
    qu'on l'ait demandé. `graine` : la graine d'hier appliquée à un autre personnage produit
    une reproductibilité qui ne reproduit rien (c'est déjà la règle de `gui/atelier.py`)."""
    assert "page" in par.non_persistes(par.MANGA)
    assert "graine" in par.non_persistes(par.ILLUSTRATIONS)


def test_le_delai_d_extinction_se_persiste_mais_pas_l_extinction():
    """Le délai est un réglage d'installation — 120 s ou 300 s selon la machine. La CASE, elle,
    est un mandat, et un mandat ne se reconduit pas tout seul."""
    assert par.par_identifiant(par.MANGA, "shutdown_delay").persiste is True
    assert par.par_identifiant(par.MANGA, "shutdown").persiste is False
    assert par.par_identifiant(par.MANGA, "keep_awake").persiste is True


def test_le_delai_par_defaut_est_celui_de_la_ligne_de_commande():
    """Deux défauts pour un même geste feraient qu'une extinction lancée depuis l'écran
    n'attendrait pas le même temps qu'en ligne de commande."""
    import ast
    import inspect

    from core import cli

    source = ast.parse(inspect.getsource(cli.ajouter_flags_veille))
    defauts = [k.value.value for n in ast.walk(source) if isinstance(n, ast.Call)
               for k in n.keywords
               if k.arg == "default" and isinstance(k.value, ast.Constant)]
    assert par.DELAI_EXTINCTION in defauts, \
        "le défaut de --shutdown-delay a bougé dans core/cli.py"


# --------------------------------------------------------------------------- #
#  Le modèle — L33.3
# --------------------------------------------------------------------------- #

def test_le_modele_choisi_outrepasse_les_agents_de_la_bonne_section():
    config = _config()
    demande = par.appliquer(config, par.MANGA,
                            {**par.defauts(par.MANGA), "modele": "un-modele-de-test"})
    assert demande.agents_outrepasses, "aucun agent nommé"
    for spec in config["manga"]["modeles"].values():
        if spec is None:
            continue
        nom = spec["model"] if isinstance(spec, dict) else spec
        assert nom == "un-modele-de-test"
    # …et la RACINE, qui est la section du light novel, n'a pas bougé.
    for spec in config["modeles"].values():
        if isinstance(spec, dict):
            assert spec["model"] != "un-modele-de-test"


def test_aucun_modele_choisi_ne_touche_a_rien():
    config = _config()
    avant = copy.deepcopy(config["manga"]["modeles"])
    demande = par.appliquer(config, par.MANGA, par.defauts(par.MANGA))
    assert demande.agents_outrepasses == ()
    assert config["manga"]["modeles"] == avant
