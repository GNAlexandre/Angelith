# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les décisions de la page Diagnostic (`gui/vue_diagnostic.py`) — **sans PySide6**.

Règle de couche du dépôt (`gui/__init__.py`) : tout ce qui DÉCIDE se teste sans Qt. Ce fichier
tourne donc dans le job de CI qui n'installe pas l'interface, comme
`tests/test_gui_vue_retouche.py` et `tests/test_gui_garde.py` du lot 35.

Il porte deux critères du `PLAN-36` :

- **critère 4** — « la page Diagnostic affiche constat, conséquence et geste pour chaque
  verdict. Aucun verdict n'est affiché sans geste — ou son absence de geste est explicite
  (hors périmètre) » ;
- **critère 3, vu de l'utilisateur** — la phrase « utilisable en l'état » retire la brique
  bloquée et **laisse les autres**.
"""
from __future__ import annotations

from core import diagnostic as diag
from core import reparations as rep
from gui import vue_diagnostic as vue


def _v(identifiant, brique, gravite, **kw):
    return diag.Verdict(identifiant, brique, gravite,
                        constat=kw.pop("constat", identifiant), **kw)


def _sections(*verdicts):
    return (diag.Section("— test —", tuple(verdicts)),)


# --------------------------------------------------------------------------- #
#  Le regroupement
# --------------------------------------------------------------------------- #

def test_les_verdicts_sont_groupes_par_brique_dans_l_ordre_declare():
    sections = _sections(_v("a", diag.MANGA, diag.BLOQUANT, geste="g"),
                         _v("b", diag.SOCLE, diag.BLOQUANT, geste="g"),
                         _v("c", diag.LN, diag.DEGRADE, geste="g"))
    groupes = vue.grouper(sections)
    assert [g.brique for g in groupes] == [diag.SOCLE, diag.LN, diag.MANGA]


def test_dans_un_groupe_le_bloquant_passe_avant_la_degradation():
    """On lit d'abord ce qui empêche de travailler."""
    sections = _sections(_v("d", diag.LN, diag.DEGRADE, geste="g"),
                         _v("b", diag.LN, diag.BLOQUANT, geste="g"),
                         _v("i", diag.LN, diag.INFORMATION, geste="g"))
    groupe = vue.grouper(sections)[0]
    assert [v.gravite for v in groupe.verdicts] == [diag.BLOQUANT, diag.DEGRADE,
                                                    diag.INFORMATION]


def test_les_conformes_sont_comptes_et_non_etales():
    """⚠ « Quatorze lignes ✓ ne se lisent pas, elles se comptent. »"""
    sections = _sections(*[_v(f"c{i}", diag.LN, diag.CONFORME) for i in range(6)])
    groupe = vue.grouper(sections)[0]
    assert groupe.verdicts == ()
    assert groupe.conformes == 6
    assert groupe.phrase_conformes() == "6 points vérifiés, rien à faire"


def test_un_seul_conforme_se_dit_au_singulier():
    groupe = vue.grouper(_sections(_v("c", diag.LN, diag.CONFORME)))[0]
    assert groupe.phrase_conformes() == "1 point vérifié, rien à faire"


def test_on_peut_demander_a_voir_les_conformes():
    sections = _sections(_v("c", diag.LN, diag.CONFORME))
    assert vue.grouper(sections, montrer_conformes=True)[0].verdicts


def test_un_groupe_sans_rien_a_signaler_reste_visible_et_vide():
    """⚠ « Six points vérifiés » et « rien affiché » ne disent pas la même chose. Faire
    disparaître le groupe ferait croire que la brique n'a pas été inspectée."""
    groupes = vue.grouper(_sections(_v("c", diag.LN, diag.CONFORME)))
    assert [g.brique for g in groupes] == [diag.LN]


def test_le_titre_dit_l_etat_d_une_brique_qui_n_est_pas_stable():
    """⚠ La brique `scan` est en BÊTA et `illustration` EXPÉRIMENTALE : le dire **là où
    l'utilisateur lit son diagnostic**, pas seulement dans le titre de la fenêtre."""
    assert "(bêta)" in vue.titre_brique(diag.SCAN)
    assert "(expérimentale)" in vue.titre_brique(diag.ILLUSTRATION)
    assert "(" not in vue.titre_brique(diag.MANGA)


# --------------------------------------------------------------------------- #
#  Critère 4 — aucun verdict sans geste
# --------------------------------------------------------------------------- #

def test_un_verdict_sans_geste_recupere_celui_de_sa_reparation():
    verdict = _v("pandoc", diag.LN, diag.BLOQUANT, reparation="pandoc")
    geste = vue.phrase_geste(verdict)
    assert geste
    assert "pandoc" in geste.lower()


def test_un_verdict_sans_geste_ni_reparation_dit_hors_perimetre():
    """⚠ « Aucun verdict n'est affiché sans geste — ou son absence de geste est explicite. »"""
    assert vue.phrase_geste(_v("mystere", diag.SOCLE, diag.BLOQUANT)) == diag.HORS_PERIMETRE


def test_un_verdict_conforme_n_a_pas_de_geste():
    assert vue.phrase_geste(_v("ok", diag.LN, diag.CONFORME)) == ""


def test_le_geste_du_verdict_prime_sur_celui_du_catalogue():
    verdict = _v("pandoc", diag.LN, diag.BLOQUANT, geste="le geste précis de ce constat")
    assert vue.phrase_geste(verdict) == "le geste précis de ce constat"


# --------------------------------------------------------------------------- #
#  Le bouton — et ce devant quoi il ne doit PAS apparaître
# --------------------------------------------------------------------------- #

def test_un_bouton_apparait_devant_une_reparation_recuperable():
    verdict = _v("poids_detection", diag.MANGA, diag.BLOQUANT, geste="g", reparable=True,
                 reparation="poids_detection")
    reparation = vue.bouton_pour(verdict)
    assert reparation is not None
    assert reparation.classe == rep.RECUPERABLE


def test_aucun_bouton_devant_un_logiciel_systeme():
    """⚠ « Un bouton devant "installe Pandoc" serait un mensonge : Angelith n'installe aucun
    logiciel système. »"""
    verdict = _v("pandoc", diag.LN, diag.BLOQUANT, geste="g", reparable=True,
                 reparation="pandoc")
    assert vue.bouton_pour(verdict) is None


def test_aucun_bouton_devant_un_verdict_conforme():
    verdict = _v("poids_detection", diag.MANGA, diag.CONFORME, reparable=True,
                 reparation="poids_detection")
    assert vue.bouton_pour(verdict) is None


def test_aucun_bouton_quand_le_verdict_ne_se_dit_pas_reparable():
    verdict = _v("poids_detection", diag.MANGA, diag.BLOQUANT, geste="g", reparable=False,
                 reparation="poids_detection")
    assert vue.bouton_pour(verdict) is None


# --------------------------------------------------------------------------- #
#  Les deux phrases d'en-tête
# --------------------------------------------------------------------------- #

def test_le_resume_porte_son_denominateur():
    """`docs/chiffres-de-reference.md` : « un chiffre affiché est lu comme une promesse »."""
    sections = _sections(_v("a", diag.LN, diag.BLOQUANT, geste="g"),
                         _v("b", diag.LN, diag.CONFORME))
    phrase = vue.phrase_resume(sections)
    assert "1 bloquant" in phrase
    assert "2 point(s) inspecté(s)" in phrase


def test_le_resume_vierge_dit_qu_aucun_diagnostic_n_a_tourne():
    """⚠ « Inconnu », pas « tout va bien » : le dépôt refuse d'afficher un verdict qu'il n'a
    pas rendu."""
    assert vue.phrase_resume(()) == vue.PHRASE_VIERGE


def test_le_resume_dit_quand_tout_est_conforme():
    sections = _sections(_v("a", diag.LN, diag.CONFORME))
    assert "Rien à signaler" in vue.phrase_resume(sections)


def test_pandoc_absent_laisse_le_manga_utilisable():
    """⚠ **Critère 3, vu de l'utilisateur.** C'est la phrase qui empêche de décourager
    quelqu'un qui n'a besoin que de planches."""
    sections = _sections(_v("pandoc", diag.LN, diag.BLOQUANT, geste="g"),
                         _v("poids", diag.MANGA, diag.CONFORME))
    phrase = vue.phrase_briques_utilisables(sections)
    assert "manga" in phrase
    assert "light novel" not in phrase


def test_les_poids_absents_laissent_le_light_novel_utilisable():
    """La réciproque."""
    sections = _sections(_v("poids", diag.MANGA, diag.BLOQUANT, geste="g"),
                         _v("pandoc", diag.LN, diag.CONFORME))
    phrase = vue.phrase_briques_utilisables(sections)
    assert "light novel" in phrase
    assert "manga" not in phrase


def test_le_serveur_absent_retire_les_deux_briques():
    sections = _sections(_v("serveur_llm", diag.SOCLE, diag.BLOQUANT, geste="g"),
                         _v("pandoc", diag.LN, diag.CONFORME),
                         _v("poids", diag.MANGA, diag.CONFORME))
    assert "Aucune brique n'est utilisable" in vue.phrase_briques_utilisables(sections)


def test_une_brique_non_inspectee_n_est_pas_annoncee_comme_utilisable():
    """⚠ Sans ce filtre, la brique scan — dont aucun point n'est relevé aujourd'hui —
    apparaîtrait comme « utilisable » parce qu'aucun verdict ne la bloque. Ne rien avoir
    mesuré n'est pas un bon résultat."""
    sections = _sections(_v("pandoc", diag.LN, diag.CONFORME))
    phrase = vue.phrase_briques_utilisables(sections)
    assert "OCR de scans" not in phrase
    assert "illustrations" not in phrase


def test_la_phrase_de_cout_porte_son_chiffre_et_sa_date():
    """Règle des chiffres, et règle des affirmations d'état : la mesure porte sa date."""
    assert "12,1 s" in vue.PHRASE_COUT
    assert "2026-09-06" in vue.PHRASE_COUT
