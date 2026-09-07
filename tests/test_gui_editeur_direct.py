# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'édition en DIRECT — taper, régler le corps, retrouver sa bulle.

## Ce que ces tests remplacent

Il fallait cliquer « Garder ma version » pour voir la réplique qu'on venait de taper se poser
sur la planche : un geste de plus, à chaque correction, pour obtenir ce qui était déjà écrit à
l'écran. Le bouton a disparu. Ce qui le rendait superflu existait déjà —
`_enregistrer_planche` versait les brouillons dans `traduction_manuelle.json` au Ctrl+S — il
manquait seulement que l'aperçu suive la frappe.

## Les deux pièges que ces tests gardent

**L'historique.** Poser la correction dans le document à chaque frappe empilerait un
instantané par caractère, et « Annuler » défferait alors des lettres au lieu de gestes. Les
brouillons restent donc le mécanisme, et le document n'est touché qu'à l'enregistrement.

**Le signal d'un widget qu'on ne fait que remplir.** Poser la valeur du réglage de corps dans
`_afficher_bulle` émet `valueChanged` : sans garde-fou, un simple clic dans la liste écrirait
une mise en page pour une bulle qu'on regarde, et marquerait la planche comme modifiée.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

from PIL import Image, ImageDraw                                             # noqa: E402
from PySide6.QtWidgets import QApplication                                   # noqa: E402

from gui.editeur import PanneauEditeur                                       # noqa: E402
from gui.modele_tome import Tome                                            # noqa: E402
from manga import checkpoints, clean, projet as projet_mod                   # noqa: E402
from manga.detection import BubbleRegion                                     # noqa: E402

TAILLE = (400, 900)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _boite(k: int) -> tuple[int, int, int, int]:
    haut = 40 + k * 250
    return (60, haut, 340, haut + 180)


def _masque(bbox) -> np.ndarray:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse([bbox[0], bbox[1], bbox[2] - 1, bbox[3] - 1], fill=255)
    return np.asarray(m) > 127


def _source() -> Image.Image:
    img = Image.new("RGB", TAILLE, (128, 128, 128))
    d = ImageDraw.Draw(img)
    for k in range(2):
        b = _boite(k)
        d.ellipse([b[0], b[1], b[2] - 1, b[3] - 1], fill=(255, 255, 255))
        d.rectangle([b[0] + 40, b[1] + 60, b[2] - 40, b[1] + 100], fill=(0, 0, 0))
    return img


@pytest.fixture
def panneau(qt_app, tmp_path):
    """Un éditeur ouvert sur un tome à une planche de deux bulles.

    Le tome est complet sur disque — sources, checkpoints, page nettoyée — pour que le chemin
    d'aperçu fonctionne pour de vrai : ces tests portent sur le DIRECT, et le simuler ne
    prouverait rien."""
    sources = tmp_path / "sources" / "P" / "T1"
    build = tmp_path / "build" / "P" / "T1" / "manga"
    sources.mkdir(parents=True)
    source = _source()
    source.save(sources / "page_0001.png")

    regions = [BubbleRegion(bbox=_boite(k), mask=_masque(_boite(k)), score=0.9, cls=0)
               for k in range(2)]
    ckpt = checkpoints.page_checkpoint_dir(build, 1)
    checkpoints.save_regions(ckpt, regions, TAILLE)
    checkpoints.save_ocr(ckpt, ["アアア", "イイイ"])
    checkpoints.save_traduction(ckpt, ["Un", "Deux"])

    chemin_clean = checkpoints.clean_page_path(build, 1)
    chemin_clean.parent.mkdir(parents=True, exist_ok=True)
    clean.clean_bubbles(source, regions).save(chemin_clean)
    projet_mod.ecrire(build, projet_mod.construire(
        build, projet="P", tome="T1", pages=[sources / "page_0001.png"],
        version="test", page_ckpt=checkpoints.page_checkpoint_dir))

    config = {"manga": {"chemins": {"sources": str(tmp_path / "sources"),
                                    "build": str(tmp_path / "build")}}}
    p = PanneauEditeur()
    p.ouvrir(Tome(config, "P", "T1"))
    p._charger_planche(1)
    _composer(p, 1)
    p.liste_bulles.setCurrentRow(0)
    return p


def _composer(panneau, numero):
    """Compose l'aperçu ICI, sur le fil du test.

    ⚠ En vrai, c'est `FilDeLecture` qui appelle `composer_planche` et remplit
    `_fenetre_apercu` — aucun des deux n'existe sans fil branché. Sans cette composition, il
    n'y aurait ni calque ni `StyleCompact`, donc pas de chemin rapide : les tests du direct
    passeraient à vide, ce qui est la pire façon de passer."""
    panneau._fenetre_apercu = {numero}
    panneau._figer_plan_apercu(numero)
    panneau.composer_planche(numero)
    assert panneau._poser_apercu_si_pret(numero), "l'aperçu n'a pas pu être posé"


def _taper(panneau, texte):
    panneau.champ_trad.setPlainText(texte)


# --------------------------------------------------------------------------- #
# Taper = corriger
# --------------------------------------------------------------------------- #

def test_le_bouton_garder_ma_version_a_disparu(panneau):
    """Il ne servait plus qu'à faire croire qu'un geste de plus était nécessaire pour VOIR ce
    qu'on écrivait."""
    assert not hasattr(panneau, "bouton_enregistrer")
    assert not hasattr(panneau, "_enregistrer_correction")


def test_taper_ne_touche_pas_l_historique(panneau):
    """⚠ Le piège central. Un `poser_correction` par frappe empilerait un instantané par
    caractère (`document._avant_operation`), et « Annuler » remonterait le temps par lettres."""
    for n in range(1, 21):
        _taper(panneau, "Bonjour" [:n] if n <= 7 else "Bonjour" + "!" * (n - 7))
    assert panneau.document.peut_annuler is False
    assert panneau.document.modifie is False


def test_taper_est_retenu_comme_brouillon(panneau):
    _taper(panneau, "Une autre réplique")
    assert panneau._brouillons == {0: "Une autre réplique"}


def test_taper_arme_le_relettrage(panneau):
    """C'est le minuteur qui remplace le bouton. 180 ms : un relettrage par PAUSE de frappe, et
    non par caractère."""
    assert not panneau._minuteur_apercu.isActive()
    _taper(panneau, "Une autre réplique")
    assert panneau._minuteur_apercu.isActive()
    assert panneau._minuteur_apercu.interval() == 180


def test_le_relettrage_repose_le_calque_sans_recreer_l_item(panneau):
    """Le direct de bout en bout : la frappe change les pixels affichés, et l'item survit —
    sans quoi un glisser en cours perdrait son grab au premier rafraîchissement."""
    assert panneau._apercu_courant is not None, "l'aperçu doit être composé pour ce test"
    item = panneau.scene.calque(0)
    avant = item.pixmap().toImage()

    _taper(panneau, "Une réplique nettement plus longue que la précédente")
    panneau._relettrer_saisie()

    assert panneau.scene.calque(0) is item, "l'item a été recréé"
    assert item.pixmap().toImage() != avant, "l'aperçu n'a pas suivi la frappe"


def test_ctrl_s_ecrit_la_saisie_sans_bouton(panneau):
    """La promesse qui remplace « Garder ma version » : taper puis enregistrer suffit."""
    _taper(panneau, "Ma version à moi")
    assert panneau.enregistrer_document() is True
    assert checkpoints.load_traduction_manuelle(panneau.planche.ckpt_dir) == {
        0: "Ma version à moi"}


def test_un_champ_vide_rend_la_bulle_au_modele(panneau):
    """⚠ Le correctif d'un désaccord devenu atteignable. `_etat_a_sauver` retirait déjà la
    correction d'un champ vidé ; `_enregistrer_planche` posait, lui, une correction manuelle
    VIDE — que le pipeline n'aurait alors plus jamais réécrite. Inoffensif tant qu'il fallait
    cliquer un bouton pour en poser une, atteignable maintenant que taper suffit."""
    _taper(panneau, "   ")
    panneau.enregistrer_document()
    assert checkpoints.load_traduction_manuelle(panneau.planche.ckpt_dir) == {}


# --------------------------------------------------------------------------- #
# Le corps de la police
# --------------------------------------------------------------------------- #

def test_afficher_une_bulle_ne_pose_pas_de_mise_en_page(panneau):
    """⚠ Remplir le réglage émet `valueChanged`. Sans le gel de `_index_affiche`, cliquer dans
    la liste pour LIRE une réplique marquerait la planche comme modifiée."""
    panneau.liste_bulles.setCurrentRow(1)
    panneau.liste_bulles.setCurrentRow(0)
    assert panneau.document.modifie is False
    assert panneau._corps_en_attente is None


def test_regler_le_corps_met_l_apercu_a_jour_tout_de_suite(panneau):
    item = panneau.scene.calque(0)
    avant = item.taille
    panneau.champ_corps.setValue(max(11, avant - 6))
    assert item.taille != avant


def test_le_corps_n_est_depose_qu_apres_la_pause(panneau):
    """Deux minuteurs, deux durées, et c'est le point : voir doit être immédiat, s'engager non.
    Le dépôt empile un pas d'historique — à 180 ms, tenir la flèche deux secondes en produirait
    onze."""
    panneau.champ_corps.setValue(18)
    assert panneau.document.modifie is False, "rien ne doit être posé avant la pause"
    assert panneau._minuteur_corps.isActive()
    assert panneau._minuteur_corps.interval() == 600


def test_le_corps_est_depose_une_seule_fois_par_valeur(panneau):
    """Dix crans en rafale, un seul pas d'historique : « Annuler » défait le réglage, pas
    chaque cran."""
    for valeur in range(14, 24):
        panneau.champ_corps.setValue(valeur)
    panneau._deposer_corps()

    assert panneau.planche.mises_en_page[0]["taille"] == 23
    panneau.document.annuler()
    assert 0 not in panneau.document.etat.mises_en_page


def test_le_corps_seul_n_impose_pas_de_rectangle(panneau):
    """⚠ **La raison d'être d'une entrée sans `rect`.** `typeset.style_impose` remplace
    l'intérieur du ballon par un RECTANGLE PLEIN ; fabriquer ce rectangle depuis la bbox pour
    la seule raison qu'on change la taille ferait écrire le texte jusque dans les coins, par
    dessus le contour dessiné."""
    panneau.champ_corps.setValue(19)
    panneau._deposer_corps()

    entree = panneau.planche.mises_en_page[0]
    assert entree["taille"] == 19 and "rect" not in entree


def test_le_corps_survit_a_l_enregistrement(panneau):
    """L'aller-retour complet : `load_mise_en_page` doit accepter une entrée sans `rect`."""
    panneau.champ_corps.setValue(21)
    panneau._deposer_corps()
    panneau.enregistrer_document()

    relu = checkpoints.load_mise_en_page(panneau.planche.ckpt_dir)
    assert relu[0]["taille"] == 21


def test_le_corps_revient_a_auto_quand_rien_n_est_impose(panneau):
    panneau.champ_corps.setValue(0)
    panneau._deposer_corps()
    assert 0 not in panneau.planche.mises_en_page
    panneau.liste_bulles.setCurrentRow(1)
    panneau.liste_bulles.setCurrentRow(0)
    assert panneau.champ_corps.value() == 0


def test_rendre_la_mise_en_page_efface_l_entree(panneau):
    """`_rendre_au_moteur` existait, complète et documentée, mais n'était branchée à AUCUN
    bouton : il n'y avait aucun moyen d'annuler un déplacement hors Ctrl+Z."""
    panneau.champ_corps.setValue(17)
    panneau._deposer_corps()
    assert 0 in panneau.planche.mises_en_page

    panneau.bouton_corps_auto.click()

    assert 0 not in panneau.planche.mises_en_page
    assert panneau.champ_corps.value() == 0


# --------------------------------------------------------------------------- #
# Déplacer, retailler
# --------------------------------------------------------------------------- #

def test_deplacer_un_bloc_retient_sa_taille(panneau):
    """⚠ Le défaut qu'`entree_mise_en_page` corrige : la taille était lue dans un
    `_calques_prets` jamais assigné, donc ne partait jamais. `fit_impose` prenait alors
    `taille_max`, échouait, et le corps se retrouvait recalculé après un simple déplacement."""
    from PySide6.QtCore import QRectF

    corps = panneau.scene.calque(0).taille
    panneau._sur_texte_deplace(0, QRectF(70, 50, 260, 170))

    entree = panneau.planche.mises_en_page[0]
    assert entree["taille"] == corps
    assert entree["rect"] == [70, 50, 330, 220]


def test_retailler_une_zone_passe_par_retailler_et_non_modifier(panneau, monkeypatch):
    """Le geste des poignées garde le texte ; « Redessiner » le jette. Les deux coexistent, et
    confondre les deux ferait perdre une traduction à chaque ajustement de quelques pixels."""
    from PySide6.QtCore import QRectF

    appels = []
    monkeypatch.setattr(panneau, "_soumettre",
                        lambda *a, **k: appels.append((a, k)))
    panneau.scene.zone_retaillee.emit(0, QRectF(50, 30, 300, 200))

    assert appels, "l'édition n'a pas été soumise"
    assert "retaillée" in appels[0][0][1]
    assert panneau._zone_a_resuivre == (1, (50, 30, 350, 230))


def test_la_selection_suit_la_zone_apres_rechargement(panneau):
    """⚠ **L'index n'est pas une identité stable.** `poser_regions` recalcule l'ordre de
    lecture : agrandir une bulle vers le haut peut la faire passer devant sa voisine. On la
    retrouve donc par sa géométrie."""
    panneau.liste_bulles.setCurrentRow(0)
    panneau._zone_a_resuivre = (1, _boite(1))
    panneau._charger_planche(1)
    assert panneau.liste_bulles.currentRow() == 1


def test_une_zone_trop_eloignee_ne_resuit_rien(panneau):
    """Mieux vaut aucune sélection qu'une sélection fausse, qui ferait porter le geste suivant
    sur une autre bulle."""
    panneau._zone_a_resuivre = (1, (0, 800, 40, 890))
    panneau._charger_planche(1)
    assert panneau.liste_bulles.currentRow() == -1


# --------------------------------------------------------------------------- #
# Interaction coupée
# --------------------------------------------------------------------------- #

def test_un_run_global_coupe_la_manipulation_directe(panneau):
    """Griser les boutons ne suffisait pas : déplacer un bloc n'est pas un clic sur un widget,
    c'est un geste sur la scène."""
    panneau.marquer_verrou(None, "run", True)
    assert panneau.scene.interactif is False

    panneau.marquer_verrou(None, "run", False)
    assert panneau.scene.interactif is True


def test_le_rendu_aplati_coupe_la_manipulation_directe(panneau):
    """Sur `pages_out/`, le texte est cuit dans les pixels : il n'y a plus de calque à déplacer
    ni de masque à tirer."""
    panneau.bouton_finale.setChecked(True)
    panneau._basculer_fond()
    assert panneau.scene.interactif is False

    panneau.bouton_finale.setChecked(False)
    panneau._basculer_fond()
    assert panneau.scene.interactif is True


# --------------------------------------------------------------------------- #
# Le système visuel — PLAN-19 L19.5 et L19.6.6
# --------------------------------------------------------------------------- #

def test_la_comparaison_au_rendu_porte_le_meme_bandeau_qu_un_run(panneau):
    """⚠ **Le cas le plus important de la liste des états** (L19.5).

    Cocher « Comparer au rendu du pipeline » coupe TOUTE interaction du canevas — c'est ce que
    `test_le_rendu_aplati_coupe_la_manipulation_directe` vérifie juste au-dessus — et le seul
    indice était l'état enfoncé d'un bouton. Le cas voisin du run, lui, affichait
    « — affichage seul » depuis toujours. Deux situations identiques pour l'utilisateur, un
    seul bandeau."""
    panneau.bouton_finale.setChecked(True)
    panneau._basculer_fond()
    assert panneau.etat_planche.text() == panneau.BANDEAU_COMPARAISON
    assert "affichage seul" in panneau.etat_planche.text()

    panneau.bouton_finale.setChecked(False)
    panneau._basculer_fond()
    assert panneau.etat_planche.text() == ""


def test_le_bandeau_du_run_l_emporte_sur_celui_de_la_comparaison(panneau):
    """Pendant un run, savoir que rien ne s'écrit prime sur savoir pourquoi la planche est
    aplatie — et deux bandeaux empilés ne se lisent pas."""
    panneau.bouton_finale.setChecked(True)
    panneau._basculer_fond()
    panneau.marquer_verrou(None, "run", True)
    assert panneau.etat_planche.text() == "run — affichage seul"
    panneau.marquer_verrou(None, "run", False)
    assert panneau.etat_planche.text() == panneau.BANDEAU_COMPARAISON
    panneau.bouton_finale.setChecked(False)
    panneau._basculer_fond()


def _fleche(panneau, touche, modificateurs=None):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    ev = QKeyEvent(QKeyEvent.KeyPress, touche, modificateurs or Qt.NoModifier)
    panneau.keyPressEvent(ev)
    return ev


def test_les_fleches_du_panneau_deplacent_la_bulle_selectionnee(panneau):
    """L19.6.6 — l'alternative clavier aux gestes de canevas, vue depuis le panneau."""
    from PySide6.QtCore import Qt

    panneau.scene.choisir(0)
    avant = panneau.scene.zone(0).rect_scene()
    _fleche(panneau, Qt.Key_Right)
    apres = panneau.scene.zone(0).rect_scene()
    assert apres.left() == avant.left() + panneau.PAS_FIN

    _fleche(panneau, Qt.Key_Right, Qt.ShiftModifier)
    assert (panneau.scene.zone(0).rect_scene().left()
            == avant.left() + panneau.PAS_FIN + panneau.PAS_LARGE)


def test_ctrl_et_fleche_retaille_au_lieu_de_deplacer(panneau):
    from PySide6.QtCore import Qt

    panneau.scene.choisir(0)
    avant = panneau.scene.zone(0).rect_scene()
    _fleche(panneau, Qt.Key_Down, Qt.ControlModifier)
    apres = panneau.scene.zone(0).rect_scene()
    assert apres.topLeft() == avant.topLeft()
    assert apres.height() == avant.height() + panneau.PAS_FIN


def test_les_fleches_ne_volent_pas_les_touches_d_une_saisie(panneau, monkeypatch):
    """⚠ Le même piège que les raccourcis `1`–`5` : une flèche dans un champ de réplique
    appartient au champ. Déplacer une bulle sous les doigts de qui tape une réplique serait
    pire qu'aucun raccourci.

    ⚠ `_en_saisie` est SIMULÉ plutôt que provoqué par un vrai `setFocus` : un panneau qui n'a
    jamais été montré n'a pas de fenêtre active, donc Qt n'y déplace aucun focus. Ce qui est
    testé ici est la GARDE, pas la mécanique de focus de Qt."""
    from PySide6.QtCore import Qt

    panneau.scene.choisir(0)
    monkeypatch.setattr(panneau, "_en_saisie", lambda: True)
    avant = panneau.scene.zone(0).rect_scene()
    _fleche(panneau, Qt.Key_Left)
    assert panneau.scene.zone(0).rect_scene() == avant


def test_le_depot_du_flechage_est_temporise(panneau):
    """Une écriture par flèche coûterait une seconde par pression. Le minuteur est le
    « relâchement » du geste au clavier."""
    from PySide6.QtCore import Qt

    panneau.scene.choisir(0)
    panneau._minuteur_flecher.stop()
    _fleche(panneau, Qt.Key_Left)
    assert panneau._minuteur_flecher.isActive()
    assert panneau._minuteur_flecher.interval() == panneau.DELAI_DEPOT_MS
    panneau._minuteur_flecher.stop()


def test_le_bandeau_de_planche_vide_ne_parait_que_sans_bulle(panneau):
    """L19.7, troisième état vide. La planche de la fixture porte deux bulles : le bandeau
    doit rester caché — un état vide qui s'affiche sur une planche pleine est pire que pas
    d'état vide du tout."""
    panneau._maj_ligne_etat()
    assert panneau.bandeau_vide.isVisibleTo(panneau) is False

    vraies, panneau.planche.bulles = panneau.planche.bulles, []
    try:
        panneau._maj_ligne_etat()
        assert panneau.bandeau_vide.isVisibleTo(panneau) is True
        assert panneau.texte_vide.text() in panneau.TEXTES_VIDE.values()
    finally:
        panneau.planche.bulles = vraies
        panneau._maj_ligne_etat()
