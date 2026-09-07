# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les deux instruments de l'étape 0 du `PLAN-32`.

`tools/tracer_progression.py` enregistre — ou reconstruit — ce que le canal de progression a
dit pendant un run ; `tools/banc_progression.py` en tire le poids de chaque phase. Ce sont
eux qui produisent les chiffres de `docs/mesures/progression-2026-09-05.md`, et un chiffre
publié par un outil non testé n'est pas un chiffre.

⚠ **Les fixtures sont des `perf.log` SYNTHÉTIQUES**, écrits ici. Les vrais vivent sous
`build/`, qui est exclu par `.gitignore` : un test qui en dépendrait passerait sur la machine
d'Alexandre et échouerait partout ailleurs, y compris en CI. Les traces réelles, elles, sont
figées sous `tests/corpus/progression/` — reconstruites une fois, versionnées, et rejouées
par `tests/test_core_progression.py`.
"""
from __future__ import annotations

import pytest

from tools import banc_progression as banc, tracer_progression as tr

PERF_MANGA = """\
# Angelith 2.25.1 — 2026-09-05 08:00:00 — python run_manga.py "X" Vol.1 --verbose
[detection] page 1/3 : 30.00s · 2 bulle(s)
[nettoyage] page 1/3 : 1.00s · 2 masque / 2 texte
[ocr] page 1/3 : 4.00s · 2 bulle(s) lues
[detection] page 2/3 : 1.00s · 1 bulle(s)
[ocr] page 2/3 : 2.00s · 1 bulle(s) lues
[detection] page 3/3 : 1.00s · 0 bulle(s)
[ocr] page 3/3 : 1.00s · 0 bulle(s) lues
[terminologie] page 1/3 : 10.00s · +2 entrée(s), 0 fusion(s)
[terminologie] page 2/3 : 8.00s · +0 entrée(s), 1 fusion(s)
[terminologie] page 3/3 : 2.00s · +0 entrée(s), 0 fusion(s)
[glossariste] optimisation : 20.0s · ~500 tok générés · ~25.0 tok/s
[traduction] page 1/3 : 40.00s · ~200 tok générés · ~5.0 tok/s
[rendu] page 1/3 : 3.00s
[traduction] page 2/3 : 20.00s · ~100 tok générés · ~5.0 tok/s
[rendu] page 2/3 : 2.00s
[traduction] page 3/3 : 5.00s · ~10 tok générés · ~2.0 tok/s
[rendu] page 3/3 : 1.00s
"""

PERF_LN = """\
# Angelith 2.25.1 — 2026-09-05 08:00:00 — python run.py "R" Vol.1 --verbose
ch01 [terminologie] bloc 1/2 : 10.0s · ~100 tok générés · ~10.0 tok/s
ch01 [terminologie] bloc 2/2 : 10.0s · ~100 tok générés · ~10.0 tok/s
ch01 [traduction] bloc 1/3 : 30.0s · ~300 tok générés · ~10.0 tok/s
ch01 [traduction] bloc 2/3 : 30.0s · ~300 tok générés · ~10.0 tok/s
ch01 [traduction] bloc 3/3 : 30.0s · ~300 tok générés · ~10.0 tok/s
ch02 [terminologie] bloc 1/1 : 10.0s · ~100 tok générés · ~10.0 tok/s
ch02 [traduction] bloc 1/2 : 30.0s · ~300 tok générés · ~10.0 tok/s
ch02 [traduction] bloc 2/2 : 30.0s · ~300 tok générés · ~10.0 tok/s
ch02 [mise en page] bloc 1/1 : 10.0s · ~50 tok générés · ~5.0 tok/s
"""


# --------------------------------------------------------------------------- #
#  L'enregistreur
# --------------------------------------------------------------------------- #

class _Horloge:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def avancer(self, s):
        self.t += s


class _Delegue:
    def __init__(self):
        self.appels = []

    def __getattr__(self, nom):
        def _prendre(*args):
            self.appels.append((nom, args))
        return _prendre


def test_l_enregistreur_transmet_tout_a_celui_qu_il_enveloppe():
    """Il DÉLÈGUE, il n'hérite pas du comportement : sinon un run tracé imprimerait deux
    fois, une par le reporter enveloppé et une par la classe de base."""
    delegue = _Delegue()
    tracer = tr.Enregistreur(delegue, None, horloge=_Horloge())
    tracer.stage("Page 1/3")
    tracer.progres(1, 3, "page_0001.png")
    tracer.phase("analyse")
    tracer.warn("bulle non dessinée")
    assert [nom for nom, _ in delegue.appels] == ["stage", "progres", "phase", "warn"]


def test_l_enregistreur_horodate_sans_dormir():
    horloge = _Horloge()
    tracer = tr.Enregistreur(_Delegue(), None, horloge=horloge)
    tracer.progres(1, 3)
    horloge.avancer(12.5)
    tracer.progres(2, 3)
    assert [e["t"] for e in tracer.evenements] == [0.0, 12.5]


def test_l_enregistreur_ne_transporte_pas_le_texte_de_l_oeuvre():
    """`volume(plan)` reçoit un objet entier : on n'en garde que ce qui décrit un run."""
    class _Plan:
        project, volume, n_chapters = "X", "Vol.1", 12
        full_text = "le texte intégral du tome, qui n'a rien à faire dans une trace"

    tracer = tr.Enregistreur(_Delegue(), None, horloge=_Horloge())
    tracer.volume(_Plan())
    args = tracer.evenements[0]["args"][0]
    assert args == {"project": "X", "volume": "Vol.1", "n_chapters": 12}


def test_l_enregistreur_est_un_reporter_complet():
    """Un traceur qui manque une méthode fait tomber le run qu'il observe."""
    from core.reporter import Reporter
    assert issubclass(tr.Enregistreur, Reporter)


# --------------------------------------------------------------------------- #
#  La reconstruction depuis un perf.log
# --------------------------------------------------------------------------- #

def test_les_runs_empiles_sont_separes():
    """`perf.log` s'ouvre en `"a"` : un fichier porte plusieurs runs."""
    texte = PERF_MANGA + PERF_MANGA
    assert len(tr.runs_de_perf(texte)) == 2


def test_un_run_sans_entete_ouvre_quand_meme_le_fichier():
    """Les versions antérieures à la 1.7.0 n'écrivaient pas la ligne `# Angelith …` — et ce
    sont précisément les seuls runs NEUFS du dépôt."""
    sans_entete = "\n".join(PERF_MANGA.splitlines()[1:])
    assert len(tr.runs_de_perf(sans_entete)) == 1


def test_la_trace_manga_pose_les_phases_la_ou_le_code_les_pose():
    trace = tr.trace_manga(PERF_MANGA.splitlines())
    phases = [e["args"][0] for e in trace if e["methode"] == "phase"]
    assert phases == ["preparation", "chargement", "analyse", "terminologie",
                      "traduction", "finalisation"]


def test_la_premiere_planche_porte_le_chargement_du_modele():
    """30 s pour la planche 1 contre 1 s pour la 2 : c'est le modèle ONNX, pas la planche."""
    trace = tr.trace_manga(PERF_MANGA.splitlines())
    avancements = [e for e in trace if e["methode"] == "progres"]
    assert avancements[0]["t"] == 0.0
    assert avancements[1]["t"] == pytest.approx(35.0)


def test_la_passe_terminologique_avance_maintenant_la_barre():
    """Elle n'émettait ni `stage` ni `progres` : une barre immobile pendant 150 appels LLM
    est indiscernable d'un blocage."""
    trace = tr.trace_manga(PERF_MANGA.splitlines())
    apres = [e for e in trace if e["methode"] == "progres"
             and any(p["methode"] == "phase" and p["args"][0] == "terminologie"
                     and p["t"] <= e["t"] for p in trace)]
    assert apres


def test_la_trace_ln_compte_les_chapitres_et_detaille_les_blocs():
    trace = tr.trace_ln(PERF_LN.splitlines())
    chapitres = [e["args"] for e in trace if e["methode"] == "chapter"]
    assert chapitres == [[1, 2, ""], [2, 2, ""]]
    assert sum(1 for e in trace if e["methode"] == "block") == 9


def test_la_brique_se_devine_sur_le_contenu(tmp_path):
    """Une ligne `page N/T` ne peut venir que du manga, une ligne `bloc i/n` que du LN."""
    (tmp_path / "m.log").write_text(PERF_MANGA, encoding="utf-8")
    (tmp_path / "l.log").write_text(PERF_LN, encoding="utf-8")
    manga = tr.depuis_perf_log(tmp_path / "m.log")[0]
    ln = tr.depuis_perf_log(tmp_path / "l.log")[0]
    assert any(e["methode"] == "progres" for e in manga)
    assert any(e["methode"] == "chapter" for e in ln)


def test_le_nom_de_volume_ne_confond_pas_les_deux_dispositions():
    """Le light novel écrit `build/<P>/<T>/perf.log`, le manga `…/<T>/manga/perf.log` :
    compter les segments depuis la fin donnait « build / P » d'un côté."""
    assert tr.nom_de_volume("build/P/Vol.1/perf.log") == "P / Vol.1"
    assert tr.nom_de_volume("build/P/Vol.1/manga/perf.log") == "P / Vol.1"


# --------------------------------------------------------------------------- #
#  L'analyse — les quatre chiffres de l'étape 0.1
# --------------------------------------------------------------------------- #

def test_l_analyse_compte_les_reculs_et_les_denominateurs():
    resultat = tr.analyser(tr.trace_ln(PERF_LN.splitlines()))
    assert resultat["reculs"] > 0
    assert len(resultat["denominateurs"]) > 1


def test_les_secondes_sans_temps_restant_sont_bornees_par_la_duree():
    for lignes, fabrique in ((PERF_MANGA, tr.trace_manga), (PERF_LN, tr.trace_ln)):
        resultat = tr.analyser(fabrique(lignes.splitlines()))
        assert 0.0 <= resultat["sans_eta_s"] <= resultat["duree_s"] + 1e-9


def test_le_rejeu_dans_le_modele_ne_recule_jamais():
    """Le même verdict que `tests/test_core_progression.py`, mais depuis l'outil : c'est lui
    qui permet de le refaire sur n'importe quel `perf.log` en dix secondes."""
    verdict = tr.rejouer_dans_le_modele(tr.trace_manga(PERF_MANGA.splitlines()))
    assert verdict["jeu"] == "manga"
    assert verdict["reculs_fraction"] == 0
    assert verdict["fraction_finale"] == pytest.approx(1.0)


def test_le_rejeu_ameliore_le_temps_sans_estimation():
    """Le chiffre qui justifie le lot, mesurable des deux côtés."""
    trace = tr.trace_ln(PERF_LN.splitlines())
    avant = tr.analyser(trace)["sans_eta_s"]
    apres = tr.rejouer_dans_le_modele(trace)["sans_eta_s"]
    assert apres <= avant


# --------------------------------------------------------------------------- #
#  Le banc de poids
# --------------------------------------------------------------------------- #

def test_les_secondes_se_repartissent_par_phase():
    brique, secondes, compte = banc.secondes_par_phase(PERF_MANGA.splitlines())
    assert brique == "manga"
    assert secondes["detection"] == pytest.approx(32.0)
    assert secondes["traduction"] == pytest.approx(65.0)
    assert secondes["glossariste"] == pytest.approx(20.0)
    assert compte["rendu"] == 3


def test_un_run_qui_paie_tout_est_neuf():
    brique, secondes, compte = banc.secondes_par_phase(PERF_MANGA.splitlines())
    assert banc.est_neuf(brique, secondes, compte) is True


def test_un_from_rendu_est_une_reprise():
    """`--from rendu` ne relance ni détection ni traduction : il tombe des deux côtés."""
    lignes = ["[rendu] page 1/3 : 3.00s", "[rendu] page 2/3 : 2.00s"]
    brique, secondes, compte = banc.secondes_par_phase(lignes)
    assert banc.est_neuf(brique, secondes, compte) is False


def test_une_phase_absente_n_entre_pas_a_zero_dans_la_mediane():
    """Un `--from rendu` ne paie pas la détection ; la compter `0` décrirait un run qui n'a
    jamais eu lieu."""
    runs = [
        {"secondes": {"detection": 10.0, "rendu": 10.0}, "total": 20.0},
        {"secondes": {"rendu": 10.0}, "total": 10.0},
    ]
    p = banc.parts(runs, ("detection", "rendu"))
    assert p["detection"] == [0.5]
    assert p["rendu"] == [0.5, 1.0]


def test_un_ecart_superieur_au_facteur_trois_refuse_le_poids():
    """La règle d'abandon du plan, appliquée telle quelle."""
    verdict = banc.poids_utilisables({"large": [0.1, 0.2, 0.5], "serree": [0.3, 0.35, 0.4]})
    assert verdict["large"] is None
    assert verdict["serree"] == pytest.approx(0.35)


def test_trop_peu_de_runs_ne_donne_pas_de_poids():
    assert banc.poids_utilisables({"x": [0.3, 0.31]})["x"] is None


def test_le_verdict_du_banc_est_celui_que_le_modele_porte():
    """`core/progression.POIDS_MESURES` est une COPIE de ce que le banc a rendu le
    2026-09-05 : ce test garde la règle, pas les valeurs — celles-là dépendent de `build/`,
    qui n'est pas versionné."""
    from core import progression as prg
    assert prg.FACTEUR_ABANDON == banc.FACTEUR_ABANDON, \
        "deux seuils d'abandon rendraient le banc et le modèle incomparables"
    refusees = 0
    for brique, mesures in prg.POIDS_MESURES.items():
        armees = {p.identifiant for p in prg.PHASES[brique] if p.poids is not None}
        for phase, (part, n, ecart) in mesures.items():
            assert n >= banc.MINIMUM_RUNS, f"{brique}/{phase} : médiane sur {n} run(s)"
            assert 0.0 < part < 1.0
            if ecart > prg.FACTEUR_ABANDON:
                refusees += 1
                assert phase not in armees, \
                    f"{brique}/{phase} : poids armé alors que l'écart vaut ×{ecart}"
    assert refusees >= 6, "la mesure de l'étape 0.2 a changé de nature : relire le document"
