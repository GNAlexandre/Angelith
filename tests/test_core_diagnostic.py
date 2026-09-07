# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le diagnostic structuré (`core/diagnostic.py`) — **sans Qt, sans réseau, sans modèle**.

## Ce que ce fichier protège

Le `PLAN-36` L36.1 pose trois exigences, et deux sont testées ici (la troisième,
l'isométrie de la sortie console, a son propre fichier — `test_core_diagnostic_iso.py`) :

- **`gravite` distingue « bloquant » de « dégradé »**, ce que la sortie texte mélangeait ;
- ⚠ **et le blocage est relatif à une BRIQUE.** C'est le critère 3 du plan, et c'est le test
  qui compte : « aucune absence propre au LN n'est classée bloquante pour un usage manga (et
  réciproquement) ». Pandoc absent ne bloque **aucun** run manga ; l'affirmer découragerait
  quelqu'un qui n'a besoin que de planches.

Aucun de ces tests n'ouvre de socket ni ne charge de modèle : les collecteurs prennent
`reseau=False`, et les verdicts se fabriquent à la main quand c'est plus clair.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import diagnostic as diag


def _v(identifiant, brique, gravite, **kw):
    return diag.Verdict(identifiant, brique, gravite,
                        constat=kw.pop("constat", identifiant),
                        geste=kw.pop("geste", "faire quelque chose"), **kw)


def _sections(*verdicts):
    return (diag.Section("— test —", tuple(verdicts)),)


# --------------------------------------------------------------------------- #
#  Le critère 3 — la portée du blocage
# --------------------------------------------------------------------------- #

def test_une_absence_du_light_novel_ne_bloque_pas_un_usage_manga():
    """⚠ **Le test du critère 3.** Pandoc absent est bloquant POUR LE LIGHT NOVEL, et pour lui
    seul. Un utilisateur qui ne traduit que des planches n'a rien à corriger."""
    sections = _sections(_v("pandoc", diag.LN, diag.BLOQUANT))
    assert diag.bloquants_pour(sections, diag.LN)
    assert diag.bloquants_pour(sections, diag.MANGA) == ()


def test_une_absence_du_manga_ne_bloque_pas_un_usage_light_novel():
    """La réciproque, que le plan exige explicitement : les poids ONNX absents n'empêchent
    aucun roman d'être traduit."""
    sections = _sections(_v("poids_detection", diag.MANGA, diag.BLOQUANT))
    assert diag.bloquants_pour(sections, diag.MANGA)
    assert diag.bloquants_pour(sections, diag.LN) == ()


def test_une_absence_du_socle_bloque_toutes_les_briques():
    """Le serveur LLM appartient au socle : son absence bloque tout le monde, et c'est la
    seule famille de verdicts dont ce soit vrai."""
    sections = _sections(_v("serveur_llm", diag.SOCLE, diag.BLOQUANT))
    for brique in (diag.LN, diag.MANGA, diag.SCAN, diag.ILLUSTRATION):
        assert diag.bloquants_pour(sections, brique), brique


def test_une_brique_inconnue_ne_depend_que_du_socle_et_d_elle_meme():
    """Le repli sûr : on ne prétend pas savoir de quoi dépend une brique qu'on ne connaît pas."""
    sections = _sections(_v("x", diag.LN, diag.BLOQUANT), _v("y", "webtoon", diag.BLOQUANT))
    bloquants = diag.bloquants_pour(sections, "webtoon")
    assert [v.identifiant for v in bloquants] == ["y"]


def test_une_degradation_ne_bloque_jamais():
    """⚠ La distinction que la sortie texte mélangeait. WeasyPrint absent est un ⚠, pas un ❌ :
    le DOCX et l'EPUB sortent quand même."""
    sections = _sections(_v("moteur_pdf", diag.LN, diag.DEGRADE))
    assert diag.bloquants_pour(sections, diag.LN) == ()
    assert diag.par_gravite(sections, diag.DEGRADE)


# --------------------------------------------------------------------------- #
#  La structure elle-même
# --------------------------------------------------------------------------- #

def test_le_resume_porte_son_denominateur():
    """`docs/chiffres-de-reference.md` : un chiffre sans dénominateur n'est pas une mesure."""
    sections = _sections(_v("a", diag.LN, diag.BLOQUANT), _v("b", diag.LN, diag.DEGRADE),
                         _v("c", diag.LN, diag.CONFORME))
    compte = diag.resume(sections)
    assert compte["total"] == 3
    assert compte[diag.BLOQUANT] == 1 and compte[diag.DEGRADE] == 1
    assert compte[diag.CONFORME] == 1


def test_sans_conformes_retire_les_sections_devenues_vides():
    sections = (diag.Section("— a —", (_v("a", diag.LN, diag.CONFORME),)),
                diag.Section("— b —", (_v("b", diag.LN, diag.BLOQUANT),)))
    restant = diag.sans_conformes(sections)
    assert [s.entete for s in restant] == ["— b —"]


def test_les_gravites_sont_ordonnees_de_la_plus_grave_a_la_plus_benigne():
    """L'ordre du tuple EST l'ordre d'affichage : on lit d'abord ce qui empêche de travailler."""
    assert diag.GRAVITES == (diag.BLOQUANT, diag.DEGRADE, diag.INFORMATION, diag.CONFORME)


def test_chaque_gravite_a_son_symbole_et_sa_phrase():
    for gravite in diag.GRAVITES:
        assert diag.SYMBOLES[gravite]
        assert diag.PHRASES_GRAVITE[gravite]


def test_dire_rend_les_lignes_sans_ecrire_quand_ecrire_est_None():
    """Le contrat du module : `ecrire=None` = chemin structuré, rien ne s'imprime."""
    assert diag.dire(None, "a", "b") == ("a", "b")


def test_dire_ecrit_au_fil_de_l_eau_et_dans_l_ordre():
    """⚠ Au fil de l'eau, et pas à la fin : la section Ollama met douze secondes, et une
    capture différée laisserait la console muette pendant tout ce temps."""
    vues: list[str] = []
    diag.dire(vues.append, "un", "deux")
    assert vues == ["un", "deux"]


# --------------------------------------------------------------------------- #
#  Les collecteurs, sans réseau
# --------------------------------------------------------------------------- #

def test_une_dependance_absente_est_bloquante_et_nomme_son_geste():
    verdict = diag.verdict_dependance("module_qui_n_existe_pas_36", "fantome",
                                      "`pip install fantome`", brique=diag.MANGA)
    assert verdict.gravite == diag.BLOQUANT
    assert verdict.brique == diag.MANGA
    assert "pip install fantome" in verdict.geste


def test_une_dependance_presente_est_conforme_et_sans_geste():
    """Un point conforme n'a pas de geste, et c'est la seule famille qui en soit dispensée."""
    verdict = diag.verdict_dependance("json", "json", "`pip install rien`", brique=diag.SOCLE)
    assert verdict.gravite == diag.CONFORME
    assert verdict.geste == ""


def test_un_outil_externe_absent_n_est_jamais_reparable():
    """⚠ **Angelith n'installe aucun logiciel système.** Un outil du PATH ne porte donc jamais
    de bouton — seulement un lien et une commande copiable."""
    verdict = diag.verdict_outil_externe(
        "outil_qui_n_existe_pas_36", brique=diag.LN, gravite=diag.BLOQUANT,
        consequence="rien ne sortira", geste="installe-le toi-même")
    assert verdict.gravite == diag.BLOQUANT
    assert verdict.reparable is False


def test_un_outil_externe_accepte_des_alternatives():
    """`unrar` OU `unar` OU `bsdtar` : trois maillons pour le même besoin."""
    verdict = diag.verdict_outil_externe(
        "absent_36", brique=diag.MANGA, gravite=diag.DEGRADE, consequence="", geste="",
        alternatives=("python",))
    assert verdict.gravite == diag.CONFORME


# --------------------------------------------------------------------------- #
#  Les deux doctors, structurés
# --------------------------------------------------------------------------- #

@pytest.fixture()
def config_ln(tmp_path: Path) -> dict:
    (tmp_path / "sources").mkdir()
    (tmp_path / "style_guide.md").write_text("x", encoding="utf-8")
    return {
        "llm": {"base_url": "http://127.0.0.1:1/v1"}, "modeles": {"traducteur": "m"},
        "temperatures": {}, "decoupage": {}, "langues": {}, "garde_fous": {},
        "rendu": {"formats": [], "pdf_engine": "weasyprint"},
        "options": {},
        "chemins": {"sources": str(tmp_path / "sources"),
                    "style_guide": str(tmp_path / "style_guide.md")},
    }


def test_le_doctor_light_novel_rend_des_verdicts_sans_rien_imprimer(config_ln, capsys):
    """⚠ `ecrire=None` : c'est ce que passe la page Diagnostic, et rien ne doit sortir sur
    `stdout` — une page d'interface qui imprime dans la console d'un `.exe` sans console est
    au mieux inutile."""
    from pipeline import doctor

    sections = doctor.sections(config_ln, ecrire=None, reseau=False)
    assert capsys.readouterr().out == ""
    assert diag.verdicts(sections)
    assert all(v.brique == diag.LN for v in diag.verdicts(sections))


def test_le_doctor_light_novel_classe_pandoc_bloquant_pour_le_ln_seulement(config_ln,
                                                                          monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nom: None)
    from pipeline import doctor

    sections = doctor.sections(config_ln, ecrire=None, reseau=False)
    pandoc = next(v for v in diag.verdicts(sections) if v.identifiant == "pandoc")
    assert pandoc.gravite == diag.BLOQUANT
    assert pandoc.brique == diag.LN
    assert diag.bloquants_pour(sections, diag.MANGA) == ()


def test_tout_verdict_non_conforme_porte_un_geste(config_ln, monkeypatch):
    """⚠ **Critère 4 du plan**, vérifié à la source plutôt qu'à l'affichage : « aucun verdict
    n'est affiché sans geste »."""
    monkeypatch.setattr("shutil.which", lambda nom: None)
    from pipeline import doctor

    sections = doctor.sections(config_ln, ecrire=None, reseau=False)
    sans_geste = [v.identifiant for v in diag.verdicts(sections)
                  if v.gravite != diag.CONFORME and not v.geste]
    assert sans_geste == []


def test_le_doctor_manga_ne_telecharge_rien_quand_on_le_lui_interdit(tmp_path, monkeypatch):
    """⚠ **Règle 1 de L36.2** : rien ne se télécharge sans un clic explicite. Ouvrir une page
    n'en est pas un — d'où `telechargement=False`, et ce test qui fait échouer tout appel au
    téléchargeur."""
    from manga import doctor as doctor_manga

    def _interdit(*a, **kw):                            # pragma: no cover — ne doit pas courir
        raise AssertionError("le diagnostic structuré ne doit RIEN télécharger")

    monkeypatch.setattr("manga.models.assurer_detecteur", _interdit)
    monkeypatch.setattr("manga.models.telecharger", _interdit)
    config = {"manga": {"modeles": {}, "temperatures": {},
                        "detection": {"model_path": str(tmp_path / "absent.onnx"),
                                      "telechargement_auto": True}}}
    sections = doctor_manga.sections(config, ecrire=None, reseau=False,
                                     telechargement=False)
    poids = next(v for v in diag.verdicts(sections) if v.identifiant == "poids_detection")
    assert poids.gravite == diag.BLOQUANT
    assert poids.reparable is True


def test_le_doctor_manga_s_arrete_si_la_section_manga_manque(capsys):
    from manga import doctor as doctor_manga

    sections = doctor_manga.sections({}, ecrire=None, reseau=False, telechargement=False)
    assert len(sections) == 1
    assert diag.verdicts(sections)[0].gravite == diag.BLOQUANT


def test_le_doctor_manga_continue_malgre_une_cle_manquante(tmp_path):
    """⚠ Le comportement d'avant, gardé : « le diagnostic doit tout inspecter avant de
    conclure, sinon l'utilisateur relance la commande autant de fois qu'il a de problèmes »."""
    from manga import doctor as doctor_manga

    config = {"manga": {"detection": {"model_path": str(tmp_path / "absent.onnx"),
                                      "telechargement_auto": False}}}
    sections = doctor_manga.sections(config, ecrire=None, reseau=False, telechargement=False)
    identifiants = {v.identifiant for v in diag.verdicts(sections)}
    assert "config_manga" in identifiants
    assert "poids_detection" in identifiants, "l'inspection s'est arrêtée trop tôt"
