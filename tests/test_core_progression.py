# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le modèle de progression — `PLAN-32` L32.1. **Aucun Qt, aucune horloge murale.**

Le test qui compte est `test_la_fraction_ne_decroit_jamais_sur_les_traces_reelles` : il
rejoue les trois traces de `tests/corpus/progression/`, reconstruites depuis les `perf.log`
du dépôt, et vérifie que la fraction ne recule pas une seule fois. Son jumeau,
`test_le_canal_brut_recule_avant_le_lot`, montre le même enregistrement à travers l'ancien
chemin — un compteur unique — et compte **66 reculs** sur le light novel. C'est le test qui
aurait échoué avant le lot, sur la séquence enregistrée.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import progression as prg
from core.progression import progression_de_stage
from gui.avancement import Estimateur

CORPUS = Path(__file__).parent / "corpus" / "progression"


class _Horloge:
    """Horloge pilotée : une estimation ne se teste pas avec `time.sleep`."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avancer(self, secondes):
        self.t += secondes


def _trace(nom: str) -> list[dict]:
    chemin = CORPUS / f"{nom}.jsonl"
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def _modele(phases=prg.PHASES_MANGA, estimateur=None) -> prg.Progression:
    p = prg.Progression(estimateur=estimateur)
    p.declarer(phases)
    return p


# --------------------------------------------------------------------------- #
#  Invariant 1 — la fraction ne décroît jamais
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("nom,jeu,reculs_attendus", [
    ("manga-pagine", "manga", 2),
    ("bande-webtoon", "manga", 2),
    ("light-novel", "ln", 66),
])
def test_le_canal_brut_recule_avant_le_lot(nom, jeu, reculs_attendus):
    """L'état d'AVANT : un compteur unique nourri par `progres`, `chapter` ET `block`.

    C'est très exactement ce que `_avancer` faisait — `setValue(courant)` sans mémoire — et
    ce que la trace enregistre. Les chiffres attendus sont ceux publiés par
    `tools/tracer_progression.py --analyser` dans `docs/mesures/progression-2026-09-05.md`."""
    del jeu
    courant = None
    reculs = 0
    for ev in _trace(nom):
        methode, args = ev["methode"], ev["args"]
        if methode in ("progres", "chapter", "block"):
            valeur = int(args[0])
        elif methode == "stage":
            valeur, _ = progression_de_stage(str(args[0]))
            if not valeur:
                continue
        else:
            continue
        if courant is not None and valeur < courant:
            reculs += 1
        courant = valeur
    assert reculs == reculs_attendus, "la trace de référence a changé de nature"


@pytest.mark.parametrize("nom,jeu", [
    ("manga-pagine", "manga"),
    ("bande-webtoon", "manga"),
    ("light-novel", "ln"),
])
def test_la_fraction_ne_decroit_jamais_sur_les_traces_reelles(nom, jeu):
    """Le critère 3 du plan, sur les séquences réellement enregistrées."""
    modele = _modele(prg.PHASES[jeu])
    suite = prg.rejouer(_trace(nom), modele, repli=progression_de_stage)
    connues = [f for f in suite if f is not None]
    assert connues, "aucune fraction connue : le rejeu ne teste rien"
    for avant, apres in zip(connues, connues[1:]):
        assert apres >= avant - 1e-12, f"{nom} : la fraction a reculé ({avant} → {apres})"
    assert connues[-1] == pytest.approx(1.0), "un run complet doit finir à 1"


def test_un_balayage_qui_recommence_ne_fait_pas_reculer_la_barre():
    """Le défaut nommé, réduit à six lignes : deux balayages, un seul dénominateur."""
    modele = _modele()
    modele.entrer("analyse")
    for i in range(1, 131):
        modele.avancer(i, 131)
    haut = modele.fraction()
    modele.entrer("traduction")
    modele.avancer(1, 131)
    assert modele.fraction() >= haut


def test_le_plancher_tient_meme_quand_un_canal_recule_dans_la_phase():
    """Le FILET, gardé même là où le modèle le rend théoriquement inutile.

    Même arbitrage que l'invariant pixel de `manga/clean.py` : « l'invariant ne doit pas
    dépendre d'un raisonnement »."""
    modele = _modele()
    modele.entrer("analyse")
    modele.avancer(100, 131)
    haut = modele.fraction()
    modele.avancer(3, 131)                 # un canal qui recule DANS la phase
    assert modele.fraction() >= haut
    assert modele.reculs == 1              # ignoré, mais compté


def test_une_phase_en_arriere_est_ignoree_et_comptee():
    modele = _modele()
    modele.entrer("traduction")
    modele.avancer(50, 100)
    haut = modele.fraction()
    modele.entrer("analyse")               # en arrière
    assert modele.phase.identifiant == "traduction"
    assert modele.fraction() == haut
    assert modele.reculs == 1


def test_une_phase_inconnue_ne_leve_pas():
    """Un orchestrateur tourne dans un fil d'arrière-plan : y lever ferait tomber un run de
    150 planches pour un défaut d'affichage."""
    modele = _modele()
    modele.entrer("phase-qui-n-existe-pas")
    assert modele.phase is None


# --------------------------------------------------------------------------- #
#  Invariant 2 — une phase sans poids se tait, elle n'invente pas
# --------------------------------------------------------------------------- #

def test_aucun_jeu_de_phases_du_depot_n_est_pondere():
    """Le résultat NÉGATIF de l'étape 0.2, gardé par un test.

    Une seule phase sur sept passe la règle du facteur 3 (`POIDS_MESURES`) ; une phase
    pondérée ne fait pas un modèle pondéré. Le jour où une mesure armera des poids, ce test
    tombera — et ce sera le bon moment pour relire `docs/mesures/progression-2026-09-05.md`."""
    for jeu in prg.PHASES.values():
        modele = prg.Progression()
        modele.declarer(jeu)
        assert modele.nature() == "comptee"


def test_les_poids_mesures_sont_conservés_mais_desarmes():
    """La mesure reste lisible, et aucune `Phase` ne la porte."""
    assert prg.POIDS_MESURES["manga"]["analyse"][2] < prg.FACTEUR_ABANDON
    assert prg.POIDS_MESURES["manga"]["traduction"][2] > prg.FACTEUR_ABANDON
    for jeu in prg.PHASES.values():
        assert all(phase.poids is None for phase in jeu)


def test_des_poids_mesures_donneraient_une_fraction_ponderee():
    """Le chemin pondéré existe et marche : c'est la mesure qui manque, pas le code."""
    phases = (prg.Phase("a", "A", 0.25, 1.0), prg.Phase("b", "B", 0.75, 1.0))
    modele = prg.Progression()
    modele.declarer(phases)
    assert modele.nature() == "ponderee"
    modele.entrer("b")
    modele.avancer(1, 2)
    assert modele.fraction() == pytest.approx(0.25 + 0.75 * 0.5)


def test_pas_de_repli_sur_des_poids_egaux():
    """Un jeu mixte — un poids ici, pas là — reste COMPTÉ.

    « Des poids égaux inventés sont un faux pourcentage avec l'aplomb d'un vrai. »"""
    phases = (prg.Phase("a", "A", 0.9, 1.0), prg.Phase("b", "B", None, 1.0))
    modele = prg.Progression()
    modele.declarer(phases)
    assert modele.nature() == "comptee"
    modele.entrer("b")
    modele.avancer(1, 1)
    assert modele.fraction() == pytest.approx(1.0)     # 2 parts sur 2, pas 0,9 + …


# --------------------------------------------------------------------------- #
#  Invariant 3 — aucune horloge murale, et les trois cas indéterminés
# --------------------------------------------------------------------------- #

def test_aucune_horloge_murale():
    """Le modèle ne lit jamais l'heure : tout passe par l'estimateur injecté."""
    import inspect
    source = inspect.getsource(prg)
    assert "time.monotonic" not in source and "import time" not in source


def test_le_lot_en_vol_rend_la_fraction_indeterminee_sans_perdre_la_position():
    """L32.6 (2) — « l'unité d'avancement est le lot, pas la planche »."""
    modele = _modele()
    modele.entrer("traduction")
    modele.avancer(80, 131, "page_0080.png")
    acquis = modele.fraction()
    modele.avancer(99, 0, "lot 80→99 · 3 planches par appel")
    assert modele.fraction() is None
    assert modele.restant() is None
    assert modele.compte() == (99, 131)                 # la position est conservée
    assert "lot 80→99" in modele.objet()
    modele.avancer(81, 131, "page_0081.png")
    assert modele.fraction() >= acquis


def test_le_chargement_du_modele_est_nomme_et_indetermine():
    """L32.6 (3) — « ne réglez pas ça par une constante d'amorçage ; annoncez la phase »."""
    modele = _modele()
    modele.entrer("chargement")
    modele.avancer(1, 150)
    assert modele.fraction() is None
    assert modele.restant() is None
    assert "Chargement du modèle" in modele.libelle()


def test_la_generation_d_image_se_tait_avant_la_premiere_image():
    """L32.6 (1) — facteur 14,7 entre la génération la plus rapide et la plus lente."""
    modele = _modele(prg.PHASES_ILLUSTRATION)
    modele.entrer("preparation")
    assert modele.fraction() is None
    modele.entrer("generation")
    modele.avancer(0, 4)
    modele.avancer(0, 0)
    assert modele.fraction() is None
    modele.avancer(1, 4)
    assert modele.fraction() is not None


# --------------------------------------------------------------------------- #
#  Le temps restant — jamais sans fraction
# --------------------------------------------------------------------------- #

def test_le_temps_restant_passe_par_l_estimateur_injecte():
    horloge = _Horloge()
    modele = _modele(estimateur=Estimateur(horloge=horloge))
    modele.entrer("analyse")
    for i in range(1, 61):
        modele.avancer(i, 60)
        horloge.avancer(1.0)
    assert modele.restant() is not None


def test_aucun_temps_restant_sans_estimateur():
    modele = _modele()
    modele.entrer("analyse")
    modele.avancer(30, 60)
    assert modele.restant() is None


def test_le_debit_ne_recule_plus_donc_l_estimateur_ne_vide_plus_sa_fenetre():
    """`gui/avancement.py:noter` L63-69 vide sa fenêtre quand le compte recule — ce qui
    coûtait `MINIMUM` planches d'estimation à chaque changement de régime. Nourri par une
    fraction monotone, ce vidage ne se déclenche plus.

    ⚠ **Le vidage RESTE dans `Estimateur`**, et c'est voulu : il est juste le jour où un
    canal recule pour de bon. Ce test dit qu'il ne sert plus, pas qu'il a disparu."""
    horloge = _Horloge()
    estimateur = Estimateur(horloge=horloge)
    modele = _modele(estimateur=estimateur)
    modele.entrer("analyse")
    for i in range(1, 21):
        modele.avancer(i, 20)
        horloge.avancer(1.0)
    modele.entrer("terminologie")
    for i in range(1, 6):                  # le compte repart à 1, la fraction non
        modele.avancer(i, 20)
        horloge.avancer(1.0)
        assert modele.restant() is not None, "l'estimation a disparu au changement de phase"


# --------------------------------------------------------------------------- #
#  L'objet en cours, et le libellé
# --------------------------------------------------------------------------- #

def test_l_objet_et_le_detail_cohabitent():
    """Le « Updating address 3 of 50 » de NN/g, et le bloc qui dit où l'on en est dedans."""
    modele = _modele(prg.PHASES_LN)
    modele.entrer("chapitres")
    modele.avancer(3, 25, "Chapitre 3")
    modele.detailler("bloc 2/10")
    assert modele.objet() == "Chapitre 3 · bloc 2/10"


def test_le_libelle_porte_la_phase_son_rang_et_le_compte():
    modele = _modele()
    modele.entrer("traduction")
    modele.avancer(84, 131)
    assert modele.libelle() == "Traduction et rendu (5/6) — planche 84/131"


def test_l_etat_est_plat_et_traversable_par_un_signal():
    modele = _modele()
    modele.entrer("analyse")
    modele.avancer(1, 10, "page_0001.png")
    etat = modele.etat()
    assert set(etat) >= {"phase", "phase_libelle", "libelle", "objet", "rang", "phases",
                         "courant", "total", "fraction", "nature", "restant", "unite"}
    assert all(v is None or isinstance(v, (str, int, float)) for v in etat.values())


def test_declarer_remet_tout_a_zero():
    horloge = _Horloge()
    modele = _modele(estimateur=Estimateur(horloge=horloge))
    modele.entrer("traduction")
    modele.avancer(9, 10)
    modele.declarer(prg.PHASES_MANGA)
    assert modele.fraction() is None and modele.rang() == (0, 6) and modele.reculs == 0


# --------------------------------------------------------------------------- #
#  Le repli par expression régulière survit — critère 9
# --------------------------------------------------------------------------- #

def test_le_repli_par_libelle_avance_encore_la_barre():
    """Les étapes non instrumentées existent encore, et le repli les couvre."""
    modele = _modele()
    modele.entrer("analyse")
    prg.appliquer(modele, "stage", ["Page 12/131 — page_0012.png (ocr)"],
                  repli=progression_de_stage)
    assert modele.compte() == (12, 131)


def test_un_stage_non_reconnu_ne_touche_a_rien():
    modele = _modele()
    modele.entrer("analyse")
    modele.avancer(5, 10)
    prg.appliquer(modele, "stage", ["optimisation du glossaire"], repli=progression_de_stage)
    assert modele.compte() == (5, 10)


def test_le_bilan_retient_le_sommet_et_pas_le_compte_courant():
    """Un run finit dans sa phase d'assemblage, qui ne compte rien. Lire `compte()` là
    ferait dire « Terminé » tout court sur un run de 131 planches."""
    modele = _modele()
    modele.entrer("analyse")
    modele.avancer(131, 131)
    modele.entrer("finalisation")
    assert modele.compte() == (0, 0)
    assert modele.bilan() == (131, "planche")


def test_le_bilan_repart_de_zero_a_chaque_run():
    modele = _modele()
    modele.entrer("analyse")
    modele.avancer(50, 131)
    modele.declarer(prg.PHASES_LN)
    assert modele.bilan() == (0, "")


def test_la_preparation_ne_fait_pas_clignoter_la_barre():
    """`part=None` et non `0.0` : avec `0.0`, la barre serait déterminée à zéro pendant la
    préparation puis indéterminée au chargement du modèle — deux états en trois secondes."""
    for jeu in (prg.PHASES_MANGA, prg.PHASES_LN):
        modele = _modele(jeu)
        modele.entrer("preparation")
        assert modele.fraction() is None
        assert modele.restant() is None


def test_un_run_complet_finit_a_cent_pour_cent():
    """`finalisation`, elle, est `part=0.0` : elle ne compte rien mais elle suit tout le
    reste, donc la barre est pleine et DÉTERMINÉE quand le rapport s'écrit."""
    modele = _modele()
    for phase in ("analyse", "terminologie", "traduction"):
        modele.entrer(phase)
        modele.avancer(10, 10)
    modele.entrer("finalisation")
    assert modele.fraction() == pytest.approx(1.0)
