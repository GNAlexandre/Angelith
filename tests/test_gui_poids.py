# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le bloc « Poids et modèles » — télécharger un poids est un GESTE, pas une réparation.

## Le défaut que ce fichier ferme

`core/reparations.py` déclare **quatre** réparations `RECUPERABLE`. Deux d'entre elles —
`poids_texte` et `modele_ocr` — n'avaient **aucun verdict** dans les doctors. Or
`gui/vue_diagnostic.bouton_pour()` exige un `Verdict` qui nomme la réparation : ces deux-là
étaient donc **inatteignables depuis l'interface**. Le catalogue les déclarait automatiques, et
rien, nulle part, ne pouvait les déclencher.

⚠ **La correction n'est pas d'ajouter deux verdicts**, et c'est délibéré : la sortie console de
`run_manga.py --check` est un contrat scripté gelé octet pour octet par
`tests/test_core_diagnostic_iso.py`. Deux sections de plus la casseraient — pour un bénéfice qui
n'est d'ailleurs pas celui qu'on cherche. Ce qu'on cherche est un endroit où récupérer un poids
**de façon indépendante**, y compris quand tout va bien, c'est-à-dire précisément là où un
verdict n'existe pas puisqu'il n'y a rien à signaler.

## L'autre moitié : la licence dans le CORPS de la page

`phrase_geste()` rend `verdict.geste` **en priorité**, et tous les verdicts réparables des
doctors en portent un. La branche qui appelait `reparation.consigne()` — la seule qui écrive la
licence — n'était donc jamais atteinte. La licence n'existait à l'écran qu'en **infobulle** du
bouton et dans la boîte de confirmation, c'est-à-dire **après** le clic. Pire : le geste de
`poids_detection` promettait « licence affichée avant » sans jamais la nommer.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                             # noqa: E402

from core import reparations as rep                       # noqa: E402
from gui import vue_diagnostic as vue                     # noqa: E402
from manga import models                                  # noqa: E402
from manga import reparations as _manga  # noqa: E402, F401 — enregistre le catalogue


def _config(tmp_path) -> dict:
    return {"manga": {"detection": {"model_path": str(tmp_path / "bulles.onnx")},
                      "onomatopees": {"model_path": str(tmp_path / "texte.onnx")}}}


# --------------------------------------------------------------------------- #
#  La décision, sans Qt
# --------------------------------------------------------------------------- #

def test_les_quatre_reparations_recuperables_sont_listees(tmp_path):
    """⚠ **Le test du lot.** Il aurait échoué avant : deux des quatre n'avaient aucun chemin
    d'interface."""
    identifiants = {p.reparation.identifiant for p in vue.poids_recuperables(_config(tmp_path))}
    assert {"poids_detection", "poids_texte", "modele_ocr", "polices"} <= identifiants


def test_chaque_entree_porte_sa_licence(tmp_path):
    for poids in vue.poids_recuperables(_config(tmp_path)):
        assert poids.reparation.licence, poids.reparation.identifiant


def test_un_poids_absent_est_dit_absent(tmp_path):
    poids = {p.reparation.identifiant: p for p in vue.poids_recuperables(_config(tmp_path))}
    assert poids["poids_detection"].etat == "absent"
    assert poids["poids_detection"].recuperable is True


def test_un_poids_present_est_dit_present(tmp_path):
    (tmp_path / "bulles.onnx").write_bytes(b"x" * models.DETECTEUR_OCTETS)
    poids = {p.reparation.identifiant: p for p in vue.poids_recuperables(_config(tmp_path))}
    assert poids["poids_detection"].etat == "present"
    assert poids["poids_detection"].recuperable is False


def test_un_poids_tronque_est_dit_incomplet(tmp_path):
    """Un fichier court est le symptôme d'un serveur qui a répondu une page d'erreur en 200,
    ou d'une coupure. Le dire ici évite un message obscur d'ONNX Runtime plus tard."""
    (tmp_path / "bulles.onnx").write_bytes(b"x" * 1000)
    poids = {p.reparation.identifiant: p for p in vue.poids_recuperables(_config(tmp_path))}
    assert poids["poids_detection"].etat == "partiel"
    assert poids["poids_detection"].recuperable is True


def test_un_etat_qu_on_ne_sait_pas_mesurer_n_est_pas_inventé(tmp_path):
    """⚠ `modele_ocr` vit dans le cache de `huggingface_hub` et `polices` dans le registre de
    polices de Windows. Ni l'un ni l'autre n'est posé par Angelith : afficher « présent » ou
    « absent » y serait un verdict que personne n'a mesuré."""
    poids = {p.reparation.identifiant: p for p in vue.poids_recuperables(_config(tmp_path))}
    assert poids["modele_ocr"].etat == ""
    assert poids["polices"].etat == ""
    # ⚠ Et le bouton reste proposé : récupérer un modèle déjà présent est idempotent, alors que
    # masquer le bouton laisserait sans recours quelqu'un dont le cache est corrompu.
    assert poids["modele_ocr"].recuperable is True


def test_chaque_etat_a_sa_phrase():
    for etat in ("present", "absent", "partiel", ""):
        assert vue.PHRASES_ETAT_POIDS[etat]


def test_la_phrase_d_introduction_dit_ce_qui_n_est_pas_fait():
    """La seule phrase de la page qui parle de rediffusion, lue par quelqu'un qui s'apprête à
    télécharger un fichier sous une licence qui n'est pas celle du projet."""
    assert "redistribué" in vue.PHRASE_POIDS or "redistribu" in vue.PHRASE_POIDS
    assert "SHA-256" in vue.PHRASE_POIDS
    assert "avant" in vue.PHRASE_POIDS.lower()


# --------------------------------------------------------------------------- #
#  La licence dans le corps de la page
# --------------------------------------------------------------------------- #

def _verdict_reparable():
    from core import diagnostic as diag
    return diag.Verdict("poids_detection", diag.MANGA, diag.BLOQUANT,
                        constat="absents", geste="un geste qui ne nomme pas la licence",
                        reparable=True, reparation="poids_detection")


def test_la_licence_est_rendue_a_cote_du_geste():
    """⚠ Le test qui aurait échoué avant le lot : `phrase_geste` court-circuitait
    `consigne()`, donc la licence n'atteignait jamais le corps de la page."""
    verdict = _verdict_reparable()
    assert vue.phrase_geste(verdict) == "un geste qui ne nomme pas la licence"
    assert models.DETECTEUR_LICENCE in vue.phrase_licence(verdict)


def test_un_verdict_sans_reparation_n_a_pas_de_licence():
    from core import diagnostic as diag
    verdict = diag.Verdict("pandoc", diag.LN, diag.BLOQUANT, constat="absent",
                           geste="installe Pandoc")
    assert vue.phrase_licence(verdict) == ""


def test_un_verdict_conforme_n_a_pas_de_licence():
    from core import diagnostic as diag
    verdict = diag.Verdict("poids_detection", diag.MANGA, diag.CONFORME, constat="présents")
    assert vue.phrase_licence(verdict) == ""


# --------------------------------------------------------------------------- #
#  Le rendu Qt
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def panneau(qt_app, tmp_path):                                  # noqa: ARG001
    from gui.diagnostic import PanneauDiagnostic
    page = PanneauDiagnostic(config=_config(tmp_path))
    yield page
    page.deleteLater()


def test_le_bloc_s_affiche_sans_qu_aucun_diagnostic_ait_tourne(panneau):
    """⚠ **Sans diagnostic.** Télécharger un poids est un geste ; l'enfermer derrière
    « Lancer le diagnostic » en ferait une réparation d'erreur."""
    from PySide6.QtWidgets import QLabel
    titres = [w.text() for w in panneau.corps.findChildren(QLabel)]
    assert "Poids et modèles" in titres


def test_chaque_carte_montre_la_licence_avant_le_bouton(panneau):
    from PySide6.QtWidgets import QLabel
    textes = [w.text() for w in panneau.corps.findChildren(QLabel)]
    assert any(models.DETECTEUR_LICENCE in t for t in textes)
    assert any(models.TEXTE_LICENCE in t for t in textes)


def test_un_clic_emet_l_identifiant_de_la_reparation(panneau):
    from PySide6.QtWidgets import QPushButton
    recus: list[str] = []
    panneau.demande_reparation.connect(recus.append)
    boutons = [b for b in panneau.corps.findChildren(QPushButton)
               if b.text() == "Télécharger"]
    assert boutons, "aucun bouton de téléchargement dans le bloc"
    boutons[0].click()
    assert recus and recus[0] in {r.identifiant for r in rep.par_classe(rep.RECUPERABLE)}


def test_sans_config_le_bloc_ne_s_affiche_pas(qt_app):           # noqa: ARG001
    """Une page construite sans configuration ne sait pas où les poids doivent atterrir. Elle
    se tait plutôt que d'inventer des chemins."""
    from PySide6.QtWidgets import QLabel

    from gui.diagnostic import PanneauDiagnostic
    panneau = PanneauDiagnostic()
    titres = [w.text() for w in panneau.corps.findChildren(QLabel)]
    assert "Poids et modèles" not in titres
