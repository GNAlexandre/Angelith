# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le bandeau de run — `PLAN-32` L32.3 à L32.5.

Ce qui est testé ici est le **câblage**, puisque les décisions sont ailleurs :
`core/progression.py` décide de la fraction, `gui/avancement.py` décide de ce qui s'écrit, et
les deux se testent sans Qt (`tests/test_core_progression.py`,
`tests/test_gui_avancement.py`). Restent trois choses qu'aucun de ces deux ne peut vérifier :

- la barre passe bien en `setRange(0, 0)` quand la fraction se tait ;
- le bandeau est **caché** tant qu'aucun run n'a commencé, et il reste après pour porter le
  bilan — un run de nuit qui finit à 3 h du matin ne laissait qu'une ligne de journal ;
- **aucune boîte modale** n'apparaît à la fin d'un run.

⚠ `pytest.importorskip` : PySide6 vit dans `requirements-gui.txt`, séparé exprès.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox          # noqa: E402

from core import progression as prg                                      # noqa: E402
from gui import avancement as av                                         # noqa: E402
from gui.bandeau import BandeauDeRun                                     # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bandeau(app):
    del app
    return BandeauDeRun()


def _modele(phases=prg.PHASES_MANGA) -> prg.Progression:
    modele = prg.Progression()
    modele.declarer(phases)
    return modele


# --------------------------------------------------------------------------- #

def test_il_est_cache_tant_qu_aucun_run_n_a_commence(bandeau):
    """« Un bandeau vide en permanence devient du décor qu'on cesse de lire. »"""
    assert bandeau.isVisibleTo(bandeau.parentWidget()) is False


def test_demarrer_le_montre_et_arme_l_arret(bandeau):
    bandeau.demarrer("Manga · Mon Manga / Vol.2")
    assert bandeau.etiquette_cible.text() == "Manga · Mon Manga / Vol.2"
    assert bandeau.bouton_arreter.isVisible() or bandeau.bouton_arreter.isVisibleTo(bandeau)
    assert bandeau.barre.maximum() == 0, "rien n'est encore compté : indéterminée"


def test_la_barre_suit_la_fraction_comptee(bandeau):
    modele = _modele()
    modele.entrer("traduction")
    modele.avancer(84, 131, "page_0084.png")
    bandeau.demarrer("Manga")
    bandeau.peindre(modele.etat())
    assert bandeau.barre.maximum() == av.PAS_DE_BARRE
    assert bandeau.barre.value() > 0
    assert bandeau.etiquette_compte.text() == "planche 84 / 131"
    assert bandeau.etiquette_objet.text() == "page_0084.png"


def test_un_lot_en_vol_rend_la_barre_indeterminee_et_la_nomme(bandeau):
    """L32.6 (2) — « `Lot 80→99` + barre indéterminée »."""
    modele = _modele()
    modele.entrer("traduction")
    modele.avancer(80, 131, "page_0080.png")
    bandeau.demarrer("Manga")
    bandeau.peindre(modele.etat())
    modele.avancer(99, 0, "lot 80→99 · 3 planches par appel")
    bandeau.peindre(modele.etat())
    assert (bandeau.barre.minimum(), bandeau.barre.maximum()) == (0, 0)
    assert bandeau.etiquette_restant.text() == ""
    assert "lot 80→99" in bandeau.etiquette_objet.text()
    assert bandeau.etiquette_compte.text() == "planche 99 / 131"


def test_la_barre_n_ecrit_jamais_son_propre_texte(bandeau):
    """`%p%` est le seul pourcentage que Qt sache écrire tout seul : il est désarmé."""
    assert bandeau.barre.isTextVisible() is False


def test_le_bilan_reste_apres_le_run_et_ne_vole_pas_le_focus(bandeau, monkeypatch):
    """L32.5 — « rien qui vole le focus », donc aucune modale à la fin d'un run."""
    ouvertes = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: ouvertes.append(self))
    monkeypatch.setattr(QDialog, "exec", lambda self: ouvertes.append(self))
    bandeau.demarrer("Manga")
    bandeau.terminer("Terminé — 131 planches, 2 h 14, 3 avertissements", 3)
    assert ouvertes == []
    assert "131 planches" in bandeau.etiquette_compte.text()
    assert bandeau.bouton_avertissements.text() == "Avertissements (3)"
    assert bandeau.bouton_arreter.isVisibleTo(bandeau) is False


def test_un_run_sans_avertissement_ne_propose_pas_de_bouton(bandeau):
    bandeau.demarrer("Manga")
    bandeau.terminer("Terminé — 9 planches, 5 min", 0)
    assert bandeau.bouton_avertissements.isVisibleTo(bandeau) is False


def test_fermer_efface_le_bandeau(bandeau):
    bandeau.demarrer("Manga")
    bandeau.terminer("Terminé", 0)
    bandeau.bouton_fermer.click()
    assert bandeau.isVisibleTo(bandeau.parentWidget()) is False


def test_l_infobulle_d_arret_est_celle_du_lanceur(bandeau):
    """Deux formulations pour une même garantie feraient douter de la garantie."""
    import inspect

    from gui import lanceur
    assert "Le run s'arrête à la prochaine frontière propre" in inspect.getsource(lanceur)
    assert bandeau.bouton_arreter.text() == "Arrêter proprement"
    assert "tout ce qui est fait est conservé" in bandeau.bouton_arreter.toolTip()


# --------------------------------------------------------------------------- #
#  La barre des tâches Windows — le constat, pas la croyance
# --------------------------------------------------------------------------- #

def test_qtwinextras_n_existe_toujours_pas():
    """La décision « rien » de L32.4(b) tient à un CONSTAT, et un constat se re-vérifie.

    Le module `QtWinExtras` — donc `QWinTaskbarProgress` — a été retiré de Qt 6. Tant qu'il
    l'est, le titre de fenêtre reste la seule façon de porter l'avancement jusqu'à la barre
    des tâches, ce qui est exactement l'usage que Microsoft lui prête.

    ⚠ **Si ce test tombe, ce n'est pas un bug : c'est une invitation.** PySide6 aurait
    relivré le module, et la décision écrite dans `gui/bandeau.py` mériterait d'être relue —
    avec sa date, sa version, et le coût qu'elle avait refusé."""
    import pkgutil

    import PySide6
    modules = {m.name for m in pkgutil.iter_modules(PySide6.__path__)}
    assert "QtWinExtras" not in modules, (
        f"PySide6 {PySide6.__version__} relivre QtWinExtras : relire la décision "
        f"« barre des tâches » de gui/bandeau.py, datée du 2026-09-05 sur PySide6 6.11.1")


def test_la_decision_sur_la_barre_des_taches_est_ecrite_et_datee():
    """Règle des affirmations d'état (§5 bis du contexte agent) : une affirmation d'état
    porte sa date et la version qui l'établit."""
    from gui import bandeau
    doc = bandeau.__doc__ or ""
    assert "2026-09-05" in doc and "PySide6 6.11.1" in doc
    assert "QtWinExtras" in doc


# --------------------------------------------------------------------------- #
#  PLAN-33 L33.2 — le compte à rebours d'extinction
# --------------------------------------------------------------------------- #

def test_la_ligne_d_extinction_est_cachee_par_defaut(bandeau):
    """Une machine qui ne va pas s'éteindre ne doit pas porter un bouton qui parle de
    l'éteindre. La quatrième ligne n'existe que quand elle a quelque chose à dire."""
    bandeau.demarrer("Manga · P / Vol.1")
    assert bandeau.etiquette_extinction.isVisibleTo(bandeau) is False
    assert bandeau.bouton_annuler_extinction.isVisibleTo(bandeau) is False


def test_le_compte_a_rebours_est_visible_et_annulable(bandeau):
    """**Critère 7 du `PLAN-33`.** « Pas de modale à la fin d'un run, mais un compte à rebours
    d'extinction **doit** être visible et annulable sans chercher. »"""
    from gui import extinction as ext

    bandeau.demarrer("Manga · P / Vol.1")
    bandeau.terminer("131 planches en 2 h 10.")
    bandeau.demarrer_extinction(ext.rebours(120, 0))
    assert bandeau.etiquette_extinction.isVisibleTo(bandeau) is True
    assert bandeau.bouton_annuler_extinction.isVisibleTo(bandeau) is True
    assert "2 min" in bandeau.etiquette_extinction.text()

    recus = []
    bandeau.demande_annulation_extinction.connect(lambda: recus.append(True))
    bandeau.bouton_annuler_extinction.click()
    assert recus == [True]


def test_le_bouton_se_desarme_quand_la_machine_part(bandeau):
    """⚠ Il ne DISPARAÎT pas : un bouton qui s'évanouit à la seconde où l'on clique dessus est
    pire qu'un bouton grisé."""
    from gui import extinction as ext

    bandeau.demarrer_extinction(ext.rebours(120, 0))
    bandeau.peindre_extinction(ext.rebours(120, 500))
    assert bandeau.bouton_annuler_extinction.isVisibleTo(bandeau) is True
    assert bandeau.bouton_annuler_extinction.isEnabled() is False
    assert "en cours" in bandeau.etiquette_extinction.text()


def test_fermer_le_bilan_n_efface_pas_le_compte_a_rebours(bandeau):
    """« Fermer » retire le bilan du run ; il ne doit pas emporter avec lui la seule chose qui
    dit que la machine va s'éteindre — ni le seul bouton qui l'arrête."""
    from gui import extinction as ext

    bandeau.demarrer("Manga · P / Vol.1")
    bandeau.terminer("131 planches.")
    bandeau.demarrer_extinction(ext.rebours(120, 0))
    bandeau.bouton_fermer.click()
    assert bandeau.isVisibleTo(bandeau.parentWidget()) is True
    assert bandeau.bouton_annuler_extinction.isVisibleTo(bandeau) is True
    # …et une fois l'extinction annulée, « Fermer » retrouve son effet normal.
    bandeau.effacer_extinction()
    bandeau.effacer()
    assert bandeau.isVisibleTo(bandeau.parentWidget()) is False


def test_le_bandeau_ne_decide_rien_du_compte_a_rebours():
    """Règle de couche : `gui/extinction.py` décide, le bandeau affiche. Le widget ne doit
    contenir ni calcul de durée, ni appel à `core.power`."""
    import inspect

    from gui import bandeau as mod

    source = inspect.getsource(mod)
    assert "power" not in source
    assert "delai_valide" not in source and "monotonic" not in source
