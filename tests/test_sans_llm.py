# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Angelith **sans serveur LLM** — lot 39.

## Ce que ce mode est, et ce qu'il n'est pas

`llm.actif: false` fait tourner un tome manga **sans aucun appel LLM** : détection, nettoyage,
OCR et rendu s'exécutent, les bulles sortent **vides**, et l'utilisateur saisit ses répliques
dans la Retouche — elles vont dans `traduction_manuelle.json`, que le pipeline ne réécrit
jamais.

⚠ **Ce n'est PAS `--dry-run`**, et la distinction est le cœur du lot. `--dry-run` SIMULE une
traduction : le texte source traverse l'agent inchangé et s'écrit comme s'il était traduit. Ici
rien ne prétend avoir traduit.

## ⚠ Le fait mesuré qui décide de toute l'implémentation

L'étape 0 demandait : « le lettrage plante-t-il sur un tome sans `traduction.json` ? » Non — il
complète avec des chaînes vides. Mais la mesure a trouvé pire, et c'est ce que
`test_sans_cache_une_correction_manuelle_est_perdue` fige :

    traduction.json ABSENT           →  0 correction appliquée sur 3, sortie = []
    traduction.json de 3 chaînes vides →  3 corrections appliquées sur 3

`checkpoints.appliquer_manuelles(None, …)` part d'une liste **vide** (`list(None or [])`), et
son garde `0 <= index < len(sortie)` rejette alors **tout**. Omettre le fichier aurait donc fait
perdre silencieusement chaque réplique saisie à la main — précisément le geste que ce mode
existe pour servir.

D'où la décision : le mode **écrit** un `traduction.json` d'une chaîne vide par bulle.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core import config as core_config
from manga import checkpoints as ck

RACINE = Path(__file__).resolve().parent.parent
ORCHESTRATEUR = RACINE / "manga" / "orchestrator_manga.py"


# --------------------------------------------------------------------------- #
#  ⚠ La mesure de l'étape 0, figée
# --------------------------------------------------------------------------- #

def test_sans_cache_une_correction_manuelle_est_perdue():
    """**Le test qui justifie tout le reste.** Il documente un comportement RÉEL du dépôt, pas
    un défaut à corriger : `appliquer_manuelles` refuse un index hors bornes parce que « le
    nombre de bulles peut avoir changé depuis que la correction a été écrite, et on préfère
    perdre la correction que décaler la planche ».

    Sur une liste vide, tout index est hors bornes."""
    manuelles = {0: "Bonjour", 1: "Ça marche ?", 2: "Trois"}
    sortie, remplaces = ck.appliquer_manuelles(None, manuelles)
    assert sortie == []
    assert remplaces == []


def test_avec_un_cache_de_bulles_vides_les_corrections_atterrissent():
    """Le test miroir, et la raison pour laquelle le mode ÉCRIT le fichier au lieu de
    l'omettre."""
    manuelles = {0: "Bonjour", 1: "Ça marche ?", 2: "Trois"}
    sortie, remplaces = ck.appliquer_manuelles(["", "", ""], manuelles)
    assert sortie == ["Bonjour", "Ça marche ?", "Trois"]
    assert remplaces == [0, 1, 2]


def test_un_cache_trop_court_ne_decale_jamais_la_planche():
    """La propriété que le dépôt défend, et que ce mode ne doit pas casser : une correction
    hors bornes est perdue, jamais insérée ailleurs."""
    sortie, remplaces = ck.appliquer_manuelles(["", ""], {0: "un", 5: "hors bornes"})
    assert sortie == ["un", ""]
    assert remplaces == [0]


# --------------------------------------------------------------------------- #
#  La clé de configuration
# --------------------------------------------------------------------------- #

def test_le_defaut_du_depot_est_arme():
    """⚠ Critère 3 de « terminé » : iso pour qui ne touche à rien. Le défaut est `true`."""
    import yaml
    config = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    assert config["llm"]["actif"] is True


def test_le_config_publie_est_arme():
    """Sur `git show HEAD:config.yaml`. Le lot 27 a livré un `config.yaml` de travail qui
    armait une brique par accident ; le fichier du disque n'est pas une preuve suffisante."""
    import subprocess

    import yaml
    sortie = subprocess.run(["git", "show", "HEAD:config.yaml"], cwd=RACINE,
                            capture_output=True, text=True, encoding="utf-8")
    if sortie.returncode != 0:                     # pragma: no cover — hors dépôt git
        pytest.skip("pas de dépôt git ici")
    publie = yaml.safe_load(sortie.stdout) or {}
    # ⚠ La clé peut être ABSENTE du commit qui précède ce lot, et c'est correct : absente vaut
    # « armé », puisque le code lit `.get("actif", True)`.
    assert (publie.get("llm") or {}).get("actif", True) is True


def test_la_cle_est_connue_du_schema():
    """Une clé absente du schéma est signalée « inconnue » par `--check` et lue avec sa valeur
    par défaut : le mode serait muet et le message trompeur."""
    from core.config_schema import CLES_CONNUES
    assert "llm.actif" in CLES_CONNUES


def test_la_section_manga_peut_outrepasser_la_racine():
    """`core/config.py` fait un héritage PROFOND : une machine peut désarmer le LLM pour le
    manga seulement. C'est ce que lit l'orchestrateur."""
    config = {"llm": {"actif": True}, "manga": {"llm": {"actif": False}}}
    assert core_config.section(config, "manga", "llm").get("actif") is False


def test_sans_la_cle_le_mode_est_arme():
    """Une installation antérieure au lot n'a pas la clé. Lui faire sauter la traduction
    parce qu'elle n'a rien dit serait l'inverse d'un défaut iso."""
    assert core_config.section({"llm": {}}, "manga", "llm").get("actif", True) is True


# --------------------------------------------------------------------------- #
#  Le branchement dans l'orchestrateur, lu dans la source
# --------------------------------------------------------------------------- #

def _source() -> str:
    return ORCHESTRATEUR.read_text(encoding="utf-8")


def test_le_mode_ecrit_un_cache_de_bulles_vides():
    """⚠ **Le test du lot.** Il aurait échoué avant : la branche n'existait pas, et un mode qui
    se contenterait de sauter la traduction ferait perdre chaque saisie manuelle (cf. le
    premier test de ce fichier)."""
    source = _source()
    assert 'if "traduction" in a_refaire and sans_llm:' in source
    assert 'translated = [""] * len(regions)' in source
    assert "checkpoints.save_traduction(ckpt_dir, translated)" in source


def test_le_mode_ne_construit_aucun_appel():
    """Dans la branche sans LLM, aucun agent n'est touché : pas d'`agents[...]`, donc pas de
    client, donc pas d'attente de neuf secondes par planche."""
    source = _source()
    debut = source.index('if "traduction" in a_refaire and sans_llm:')
    branche = source[debut:source.index('elif "traduction" in a_refaire:', debut)]
    assert "agents[" not in branche
    assert "agent." not in branche


def test_la_terminologie_est_sous_filet():
    """⚠ Le correctif qui évite de perdre des heures de GPU : la passe tournait HORS du filet
    par planche, et une `RuntimeError` du client LLM y tuait le tome entier — après que la
    détection et l'OCR de 150 planches avaient déjà tourné."""
    source = _source()
    assert "_passe_terminologie_protegee(" in source
    arbre = ast.parse(source)
    fonctions = {n.name: n for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef)}
    assert "_passe_terminologie_protegee" in fonctions
    corps = ast.unparse(fonctions["_passe_terminologie_protegee"])
    assert "except" in corps


def test_un_arret_demande_traverse_le_filet():
    """Les trois exceptions qui traversent `_filet` traversent aussi celui-ci : un arrêt
    demandé est une décision de l'utilisateur, pas un incident à rattraper."""
    source = _source()
    debut = source.index("def _passe_terminologie_protegee(")
    corps = source[debut:source.index("def _passe_terminologie(", debut)]
    assert "control.StopRequested" in corps
    assert "KeyboardInterrupt" in corps
    assert "SystemExit" in corps


def test_ce_qui_est_perdu_est_nomme():
    """Une passe abandonnée ne se répute pas réussie en silence : le rapport doit pouvoir dire
    ce qui manque, comme `terminologue_actif` le fait déjà."""
    source = _source()
    debut = source.index("def _passe_terminologie_protegee(")
    corps = source[debut:source.index("def _passe_terminologie(", debut)]
    assert "terminologue_abandonne" in corps
    assert "reporter.warn" in corps


def test_le_mode_est_annonce_au_lancement():
    """Un tome qui sort sans texte doit le DIRE, sinon c'est un rendu qu'on prendra pour une
    sortie."""
    source = _source()
    assert "Mode SANS LLM" in source
    assert "stats_sans_llm" in source


def test_le_mode_lit_la_section_manga_et_pas_la_racine():
    """Un `manga.llm.actif: false` doit suffire, sans désarmer le light novel."""
    source = _source()
    assert 'core_config.section(config, "manga", "llm").get("actif", True)' in source


# --------------------------------------------------------------------------- #
#  Le rapport le DIT, et les CLI l'exposent
# --------------------------------------------------------------------------- #

def test_le_rapport_annonce_le_mode():
    """⚠ Un tome qui sort sans texte doit le dire : à l'œil, un tome délibérément non traduit
    et un tome dont la traduction a échoué produisent exactement les mêmes planches."""
    from manga import report_manga as rm
    import inspect
    assert "stats_sans_llm" in inspect.signature(rm.build_report).parameters
    source = (RACINE / "manga" / "report_manga.py").read_text(encoding="utf-8")
    assert "MODE SANS LLM" in source
    assert "traduction_manuelle.json" in source


def test_les_deux_cli_portent_le_drapeau():
    for nom in ("run.py", "run_manga.py"):
        source = (RACINE / nom).read_text(encoding="utf-8")
        assert "ajouter_flag_sans_llm" in source, nom


def test_le_light_novel_refuse_avec_un_motif():
    """Le drapeau EXISTE côté roman et s'arrête en expliquant. L'omettre de la CLI ferait
    croire à un oubli et renverrait un « unrecognized arguments » qui n'explique rien."""
    import subprocess
    import sys
    sortie = subprocess.run([sys.executable, "run.py", "X", "Vol.1", "--sans-llm"],
                            cwd=RACINE, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    assert sortie.returncode != 0
    texte = sortie.stdout + sortie.stderr
    assert "n'est pas disponible pour le light novel" in texte
    assert "run_manga.py --sans-llm" in texte


def test_le_drapeau_est_vu_par_l_inventaire():
    """Il est posé par un HELPER, donc invisible à un `grep add_argument run_manga.py`. C'est
    exactement ce que `tools/inventaire_drapeaux.py` existe pour attraper — et il l'a
    attrapé : le test de l'inventaire a refusé la livraison tant que le helper n'était pas
    déclaré."""
    from tools import inventaire_drapeaux as inv
    manga = [d for d in inv.drapeaux() if d.cli == "run_manga.py" and d.nom == "--sans-llm"]
    assert manga and manga[0].via == "core/cli.py:ajouter_flag_sans_llm"


def test_le_drapeau_n_arme_que_dans_un_sens():
    """Ne pas passer `--sans-llm` ne RÉARME pas la traduction : c'est `llm.actif` qui décide.
    Règle des trois états — absent veut dire « n'y touche pas »."""
    from core import cli as core_cli
    config = {"llm": {"actif": False}}
    core_cli.appliquer_sans_llm(config, False)
    assert config["llm"]["actif"] is False
    core_cli.appliquer_sans_llm(config, True)
    assert config["llm"]["actif"] is False


def test_le_drapeau_arme_le_mode():
    from core import cli as core_cli
    config = {"llm": {"actif": True}}
    core_cli.appliquer_sans_llm(config, True)
    assert config["llm"]["actif"] is False


# --------------------------------------------------------------------------- #
#  Le réglage du serveur, et le défaut de sonde corrigé
# --------------------------------------------------------------------------- #

def test_l_endroit_du_serveur_ne_touche_jamais_au_fichier():
    """`config.yaml` est un document (interdit 5). Le réglage vit en mémoire et dans
    `.angelith/interface.json`."""
    from core import modeles as mdl
    config = {"llm": {"base_url": "http://localhost:11434/v1"}}
    change = mdl.outrepasser_endpoint(config, None, "http://127.0.0.1:11434/v1")
    assert change == ("http://localhost:11434/v1", "http://127.0.0.1:11434/v1")
    assert config["llm"]["base_url"] == "http://127.0.0.1:11434/v1"


def test_une_adresse_vide_ne_coupe_rien():
    """⚠ Le piège que la règle des trois états évite : vide = « s'en remettre à config.yaml »,
    pas « efface l'adresse »."""
    from core import modeles as mdl
    config = {"llm": {"base_url": "http://localhost:11434/v1"}}
    assert mdl.outrepasser_endpoint(config, None, "") is None
    assert mdl.outrepasser_endpoint(config, None, None) is None
    assert config["llm"]["base_url"] == "http://localhost:11434/v1"


def test_la_sonde_respecte_la_section_manga():
    """⚠ Le défaut corrigé en passant : `url_llm` lisait TOUJOURS la racine, alors que
    `manga/doctor.py` respectait la section. Sur une installation qui pointe la brique manga
    vers une seconde machine, l'accueil sondait le serveur du light novel."""
    from gui import sondes as snd
    config = {"llm": {"base_url": "http://ln:11434/v1"},
              "manga": {"llm": {"base_url": "http://manga:11434/v1"}}}
    assert snd.url_llm(config) == "http://ln:11434/v1"
    assert snd.url_llm(config, "manga") == "http://manga:11434/v1"


def test_le_reglage_du_serveur_est_persiste_a_none():
    """`None` et non `""` : une chaîne vide persistée couperait le serveur."""
    from gui import reglages as reg
    assert "serveur_llm" in reg.DEFAUTS
    assert reg.DEFAUTS["serveur_llm"] is None


def test_la_case_de_lancement_n_existe_pas_pour_le_light_novel():
    from gui import parametres as par
    assert par.par_identifiant(par.MANGA, "sans_llm") is not None
    assert par.par_identifiant(par.WEBTOON, "sans_llm") is not None
    assert par.par_identifiant(par.LIGHT_NOVEL, "sans_llm") is None
