# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Estimation du temps restant. Aucun Qt : c'est la règle de couche du dépôt — ce qui
DÉCIDE se teste sans PySide6, seul l'affichage vit dans `gui/fenetre.py`."""
import pytest

from core.reporter import Reporter
from gui import avancement as av


class _Horloge:
    """Horloge pilotée : une estimation ne se teste pas avec `time.sleep`."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avancer(self, secondes):
        self.t += secondes


def _estimateur(**kw):
    h = _Horloge()
    return av.Estimateur(horloge=h, **kw), h


def test_rien_tant_qu_on_ne_sait_pas():
    """Une estimation fausse est pire que pas d'estimation : on s'y fie."""
    est, h = _estimateur()
    for i in range(1, 4):
        est.noter(i, 100)
        h.avancer(2.0)
    assert est.restant(100) is None


def test_debit_regulier():
    est, h = _estimateur()
    for i in range(1, 11):
        est.noter(i, 100)
        h.avancer(2.0)
    # 9 intervalles de 2 s pour 9 planches, il en reste 90 → 180 s.
    assert est.restant(100) == pytest.approx(180.0, abs=1.0)


def test_la_fenetre_glisse_et_suit_le_changement_de_regime():
    """Un run manga change de régime : le balayage A ne fait aucun appel LLM, le B en fait
    un par lot. Une moyenne depuis le début traînerait l'ancien débit."""
    est, h = _estimateur(fenetre=5, minimum=3)
    for i in range(1, 21):            # régime rapide
        est.noter(i, 40); h.avancer(1.0)
    for i in range(21, 31):           # régime dix fois plus lent
        est.noter(i, 40); h.avancer(10.0)
    # 10 planches restantes au régime LENT : ~100 s, pas ~10 s.
    assert est.restant(40) == pytest.approx(100.0, abs=15.0)


def test_un_recul_repart_de_zero():
    """Le balayage B repasse par la planche 1. C'est un nouveau régime, pas un recul à
    lisser : mélanger les deux débits donnerait un temps sans rapport avec l'un ni l'autre."""
    est, h = _estimateur(minimum=3)
    for i in range(1, 11):
        est.noter(i, 100); h.avancer(1.0)
    est.noter(1, 100)                 # début du second balayage
    assert est.restant(100) is None   # on ne sait plus, et on le dit


def test_une_repetition_ne_compte_pas():
    est, h = _estimateur(minimum=2)
    est.noter(5, 100); h.avancer(1.0)
    est.noter(5, 100); h.avancer(1.0)
    assert est.restant(100) is None


def test_total_inconnu_ne_divise_pas_par_zero():
    est, _ = _estimateur()
    est.noter(3, 0)
    assert est.restant(0) is None


def test_reinitialiser():
    est, h = _estimateur(minimum=3)
    for i in range(1, 11):
        est.noter(i, 100); h.avancer(1.0)
    assert est.restant(100) is not None
    est.reinitialiser()
    assert est.restant(100) is None


@pytest.mark.parametrize("secondes,attendu", [
    (None, ""),
    (5, "moins d'une minute"),
    (59, "moins d'une minute"),
    (60, "1 min"),
    (185, "3 min"),
    (3600, "1 h 00"),
    (6000, "1 h 40"),
])
def test_duree_lisible(secondes, attendu):
    assert av.duree_lisible(secondes) == attendu


def test_progres_est_muet_sur_le_reporter_de_base(capsys):
    """Le canal chiffré ne doit RIEN changer au terminal : le libellé de `stage` y dit déjà
    « Page 12/131 »."""
    Reporter().progres(12, 131)
    assert capsys.readouterr().out == ""


# --------------------------------------------------------------------------- #
#  Lot 32 — ce que le bandeau affiche. Toujours aucun Qt.
# --------------------------------------------------------------------------- #

from core import progression as prg                                    # noqa: E402


def _etat(**surcharges) -> dict:
    """Un état de `core/progression.py`, plutôt qu'un dictionnaire écrit à la main.

    ⚠ Passer par le vrai modèle est la seule façon d'être sûr que ces fonctions lisent des
    clés qui existent : un dictionnaire littéral de test ne se périme jamais, et c'est
    précisément son défaut."""
    modele = prg.Progression()
    modele.declarer(prg.PHASES_MANGA)
    modele.entrer(surcharges.pop("phase", "traduction"))
    courant = surcharges.pop("courant", 84)
    total = surcharges.pop("total", 131)
    if total or courant:
        modele.avancer(courant, total, surcharges.pop("objet", "page_0084.png"))
    etat = modele.etat()
    etat.update(surcharges)
    return etat


def test_le_bandeau_nomme_la_phase_son_rang_et_le_compte():
    lignes = av.lignes_de_run(_etat(), "Manga · Mon Manga / Vol.2")
    assert lignes.cible == "Manga · Mon Manga / Vol.2"
    assert lignes.phase == "Traduction et rendu (5/6)"
    assert lignes.compte == "planche 84 / 131"
    assert lignes.objet == "page_0084.png"
    assert lignes.determinee is True


def test_le_bandeau_n_ecrit_jamais_de_pourcentage():
    """La fraction du dépôt est COMPTÉE, pas pondérée : « 64 % » se lirait comme 64 % du
    temps, alors que la moitié des planches du balayage A ne coûte que ~32 % du run."""
    lignes = av.lignes_de_run(_etat(restant=4200.0), "Manga")
    assert "%" not in " ".join(str(x) for x in lignes)


def test_le_temps_restant_est_grossier_et_prefixe():
    lignes = av.lignes_de_run(_etat(restant=4200.0))
    assert lignes.restant == "~1 h 10 restantes"


@pytest.mark.parametrize("cas,etat", [
    ("génération d'image avant la première image",
     {"fraction": None, "courant": 0, "total": 4, "unite": "image",
      "phase_libelle": "Génération (image)", "rang": 3, "phases": 3, "restant": None}),
    ("lot de traduction en vol",
     {"fraction": None, "courant": 99, "total": 131, "unite": "planche",
      "phase_libelle": "Traduction et rendu", "rang": 5, "phases": 6, "restant": None,
      "objet": "lot 80→99 · 3 planches par appel"}),
    ("chargement du modèle de détection",
     {"fraction": None, "courant": 1, "total": 150, "unite": "planche",
      "phase_libelle": "Chargement du modèle de détection", "rang": 2, "phases": 6,
      "restant": None}),
])
def test_les_trois_cas_indetermines_n_affichent_ni_pourcentage_ni_temps(cas, etat):
    """Les trois endroits légitimement indéterminés du dépôt — `PLAN-32` L32.6.

    « Ne jamais combiner indéterminé et pourcentage, ou indéterminé et temps restant. »"""
    lignes = av.lignes_de_run(etat)
    assert lignes.determinee is False, cas
    assert lignes.maximum == 0, cas
    assert lignes.restant == "", cas
    assert "%" not in " ".join(str(x) for x in lignes), cas
    assert lignes.phase, f"{cas} : une barre indéterminée doit au moins se nommer"


def test_un_indetermine_affiche_quand_meme_le_compte():
    """« La barre reste sur le compte d'objets » : l'information n'est pas perdue, elle
    cesse seulement d'être convertie en temps."""
    lignes = av.lignes_de_run({"fraction": None, "courant": 99, "total": 131,
                               "unite": "planche", "phase_libelle": "Traduction",
                               "rang": 5, "phases": 6})
    assert lignes.compte == "planche 99 / 131"


def test_un_temps_restant_est_ignore_si_la_fraction_se_tait():
    """Ceinture ET bretelles : le modèle rend déjà `None`, le widget ne peut pas le trahir."""
    lignes = av.lignes_de_run({"fraction": None, "restant": 3600.0, "courant": 1,
                               "total": 2, "phase_libelle": "X", "rang": 1, "phases": 2})
    assert lignes.restant == ""


# ---- le titre de fenêtre, et les quatre combinaisons de `[*]` ---- #

GABARIT = "Angelith 2.26.0 [*]— brique manga : stable"


@pytest.mark.parametrize("run,modifie", [(False, False), (False, True),
                                         (True, False), (True, True)])
def test_le_titre_garde_la_marque_de_modification(run, modifie):
    """`[*]` est l'emplacement où Qt insère « document modifié ». Une concaténation naïve
    le perdrait, et avec lui la seule marque de travail non enregistré.

    ⚠ `modifie` ne change pas la CHAÎNE : c'est `setWindowModified` qui décide de ce que Qt
    dessine à cet emplacement. Ce qui doit tenir dans les quatre cas, c'est que
    l'emplacement soit là, une fois et une seule."""
    del modifie
    titre = av.titre_de_fenetre(GABARIT, _etat() if run else None, "Manga / Vol.2")
    assert titre.count("[*]") == 1
    assert GABARIT in titre


def test_le_titre_porte_l_avancement_en_tete():
    """Microsoft : « concisely placing the distinguishing information first »."""
    titre = av.titre_de_fenetre(GABARIT, _etat(), "Manga / Vol.2")
    assert titre.startswith("84/131 — Manga / Vol.2 — ")


def test_le_titre_sans_run_est_le_gabarit_nu():
    assert av.titre_de_fenetre(GABARIT, None) == GABARIT
    assert av.titre_de_fenetre(GABARIT, {}) == GABARIT


def test_le_titre_nomme_la_phase_quand_rien_n_est_compte():
    """Une phase sans compte (préparation, bascule) vaut mieux qu'un titre nu : elle dit
    qu'un run tourne."""
    titre = av.titre_de_fenetre(GABARIT, {"courant": 0, "total": 0,
                                          "phase_libelle": "Préparation"})
    assert titre.startswith("Préparation — ")


def test_le_titre_ne_porte_pas_de_pourcentage():
    """Même règle que le bandeau : un chiffre porte son dénominateur ou n'est pas une
    mesure."""
    assert "%" not in av.titre_de_fenetre(GABARIT, _etat(), "Manga")


# ---- le bilan de fin de run ---- #

def test_le_bilan_de_fin_dit_ce_qui_a_ete_fait():
    assert av.resume_de_fin(unites=131, unite="planche", secondes=8040.0,
                            avertissements=3) == \
        "Terminé — 131 planches, 2 h 14, 3 avertissements"


def test_le_bilan_tait_ce_qu_il_ne_sait_pas():
    assert av.resume_de_fin(unites=0, unite="", secondes=None,
                            avertissements=0) == "Terminé"


def test_un_run_arrete_ne_dit_pas_termine():
    bilan = av.resume_de_fin(unites=12, unite="chapitre", secondes=60.0,
                             avertissements=1, succes=False)
    assert bilan.startswith("Arrêté — 12 chapitres")
