# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La destination « Retouche » découplée — `PLAN-35`, la moitié qui demande un écran.

`tests/test_gui_garde.py` et `tests/test_gui_vue_retouche.py` vérifient les DÉCISIONS, sans
PySide6. Ici on vérifie qu'elles sont branchées, et sur les bons gestes.

| Test | Ce qu'il empêche de revenir |
|---|---|
| six appelants de `peut_quitter` | un chemin de perte qu'aucun code n'exerce |
| changer de destination ne demande rien | le dialogue qu'on apprend à cliquer sans lire |
| `retoucher()` navigue | « Retoucher » depuis la bibliothèque, sans effet visible |
| le motif de verrou | un panneau gris qui ne dit pas pour combien de temps |
| le bouton du bilan de run | un run fini qui laisse chercher où sont ses planches |
| le miroir de récupération | une promesse de docstring que rien ne vérifie |

⚠ `QT_QPA_PLATFORM=offscreen` avant toute `QApplication`, et `$ANGELITH_REGLAGES` sur le
`tmp_path` de chaque test — mêmes raisons que `tests/test_gui_fenetre.py`, dont ce fichier
reprend les fixtures.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox                       # noqa: E402

from gui import reglages as reg                                              # noqa: E402
from gui import vue_retouche as vue                                          # noqa: E402
from gui.fenetre import Fenetre                                              # noqa: E402
from gui.travailleur import GENRE_RUN                                        # noqa: E402
from manga import recuperation                                               # noqa: E402

# ⚠ Import PLAT, pas relatif : `tests/` n'est pas un paquet (aucun `__init__.py`), et
# `pytest` ajoute le dossier au `sys.path` en mode « rootdir ». C'est la convention du dépôt.
from test_gui_fenetre import (_arreter, _config, _detruire,                  # noqa: E402
                              _tome_traite)


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def fenetre_avec_tome(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path)
    fen = Fenetre(_config(tmp_path), "config.yaml")
    fen.aller_a("retouche")
    fen.retouche.viser("P", "Vol.1")
    yield fen
    _arreter(fen)
    _detruire(fen)


def _en_attente(fenetre) -> None:
    """Du travail non enregistré, sans passer par un geste de souris."""
    fenetre.editeur._brouillons_par_planche[1] = {0: "pas encore écrit"}
    assert fenetre.editeur.planches_modifiees() == [1]


def _montre(widget) -> bool:
    """Le widget est-il armé pour être vu ?

    ⚠ **`isHidden()` et non `isVisible()`.** Ces tests ne montrent jamais la fenêtre —
    `show()` sur une `QMainWindow` de 3 500 px coûte cher et n'apporte rien —, or
    `isVisible()` est faux pour tout widget dont un ancêtre est caché, quel que soit son
    propre état. C'est l'état EXPLICITE posé par le code qu'on vérifie ici, et c'est
    exactement ce que `isHidden()` rend."""
    return not widget.isHidden()


def _boite(monkeypatch, reponse: str) -> list[str]:
    """Remplace la boîte à trois choix et retient les verbes qu'on lui a demandés."""
    vus: list[str] = []

    def _fausse(self, attente, *, verbe, consequence):
        vus.append(verbe)
        return reponse

    monkeypatch.setattr(Fenetre, "_boite_travail_en_attente", _fausse)
    return vus


# --------------------------------------------------------------------------- #
# L35.4 — une seule implémentation, six appelants
# --------------------------------------------------------------------------- #

def test_changer_de_destination_avec_du_travail_ne_demande_RIEN(fenetre_avec_tome,
                                                                monkeypatch):
    """**Le test qui aurait échoué si le lot avait refermé le trou par une garde de plus.**

    Le `PLAN-31` annonçait qu'après lui, quitter la retouche serait un changement de
    destination que rien ne garderait. La réponse du `PLAN-35` L35.4 n'est pas d'ajouter une
    boîte : les pages vivent dans un `QStackedWidget`, en quitter une la CACHE. Poser un
    dialogue ici apprendrait à le cliquer sans lire."""
    fenetre = fenetre_avec_tome
    _en_attente(fenetre)
    vus = _boite(monkeypatch, "annuler")
    for identifiant in ("manga", "accueil", "illustrations", "retouche"):
        assert fenetre.aller_a(identifiant) is not None
    assert vus == [], "aucune boîte ne doit s'ouvrir sur un changement de destination"
    assert fenetre.editeur.planches_modifiees() == [1]
    assert fenetre.destination() == "retouche"


def test_lancer_un_run_avec_du_travail_ne_demande_rien(fenetre_avec_tome, monkeypatch):
    """Un run global VERROUILLE le tome, il ne le jette pas."""
    fenetre = fenetre_avec_tome
    _en_attente(fenetre)
    vus = _boite(monkeypatch, "annuler")
    assert fenetre.peut_quitter("run")
    assert vus == []


def test_creer_un_projet_avec_du_travail_ne_demande_rien(fenetre_avec_tome, monkeypatch):
    fenetre = fenetre_avec_tome
    _en_attente(fenetre)
    vus = _boite(monkeypatch, "annuler")
    assert fenetre.peut_quitter("creation")
    assert vus == []


def test_changer_de_tome_avec_du_travail_demande_et_peut_etre_annule(fenetre_avec_tome,
                                                                     tmp_path, monkeypatch):
    fenetre = fenetre_avec_tome
    _tome_traite(tmp_path, projet="P", tome="Vol.2")
    # ⚠ Le tome vient d'apparaître sur le disque : sans ce rafraîchissement, la liste ne le
    # connaît pas et `setCurrentText` d'un item absent ne fait RIEN sur un combo non
    # éditable — le test passerait pour de mauvaises raisons.
    fenetre.retouche.remplir_projets()
    _en_attente(fenetre)
    vus = _boite(monkeypatch, "annuler")
    fenetre.retouche.choix_tome.setCurrentText("Vol.2")
    assert vus == ["Changer de tome"]
    assert fenetre.tome.tome == "Vol.1", "le tome n'a pas changé"
    assert fenetre.editeur.planches_modifiees() == [1]


def test_changer_de_PROJET_est_compte_comme_son_propre_chemin(fenetre_avec_tome, tmp_path,
                                                              monkeypatch):
    """Les deux posent la même boîte, mais `gui/garde.py` les nomme séparément — le tableau
    de l'étape 0.2 les compte séparément."""
    fenetre = fenetre_avec_tome
    _tome_traite(tmp_path, projet="Q", tome="Vol.1")
    fenetre.retouche.remplir_projets()
    _en_attente(fenetre)
    vus: list[str] = []
    monkeypatch.setattr(Fenetre, "peut_quitter",
                        lambda self, chemin, **kw: (vus.append(chemin), True)[1])
    fenetre.retouche.choix_projet.setCurrentText("Q")
    assert vus == ["projet"]


def test_fermer_la_fenetre_avec_du_travail_demande(fenetre_avec_tome, monkeypatch):
    fenetre = fenetre_avec_tome
    _en_attente(fenetre)
    vus = _boite(monkeypatch, "annuler")

    class _Evenement:
        def __init__(self):
            self.ignore_appele = False

        def ignore(self):
            self.ignore_appele = True

        def accept(self):
            pass

    evenement = _Evenement()
    fenetre.closeEvent(evenement)
    assert vus == ["Quitter"]
    assert evenement.ignore_appele, "la fermeture est annulée"


def test_enregistrer_puis_changer_de_tome_ecrit_vraiment(fenetre_avec_tome, tmp_path,
                                                         monkeypatch):
    fenetre = fenetre_avec_tome
    _tome_traite(tmp_path, projet="P", tome="Vol.2")
    fenetre.retouche.remplir_projets()
    _en_attente(fenetre)
    _boite(monkeypatch, "enregistrer")
    fenetre.retouche.choix_tome.setCurrentText("Vol.2")
    assert fenetre.tome.tome == "Vol.2"


# --------------------------------------------------------------------------- #
# L35.1 — la liste dit ce qu'elle ne montre pas
# --------------------------------------------------------------------------- #

def test_un_projet_sans_tome_masque_n_affiche_aucune_note(fenetre_avec_tome):
    assert not _montre(fenetre_avec_tome.retouche.etiquette_absents)


def test_un_tome_non_editable_est_nomme_avec_sa_raison(qt_app, tmp_path, monkeypatch):
    """Un projet qui porte un roman ET son manga : le tome light novel ne peut pas s'éditer
    ici, et la liste doit le dire plutôt que de le taire."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path, projet="P", tome="Vol.1")
    (tmp_path / "sources" / "P" / "Vol.2" / "light_novel").mkdir(parents=True)
    (tmp_path / "sources" / "P" / "Vol.2" / "light_novel" / "roman.txt").write_text(
        "un roman", encoding="utf-8")
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.aller_a("retouche")
        panneau = fen.retouche
        assert [panneau.choix_tome.itemText(i)
                for i in range(panneau.choix_tome.count())] == ["Vol.1"]
        assert _montre(panneau.etiquette_absents)
        assert "Vol.2" in panneau.etiquette_absents.text()
        assert "light novel" in panneau.etiquette_absents.text()
    finally:
        _arreter(fen)
        _detruire(fen)


# --------------------------------------------------------------------------- #
# L35.2 — entrer par l'œuvre, et repartir d'un run
# --------------------------------------------------------------------------- #

def test_retoucher_amene_a_la_destination_meme_si_elle_existe_deja(fenetre_avec_tome,
                                                                   tmp_path):
    """**Le test qui aurait échoué avant le lot.** `ouvrir_tome` ne navigue que si la
    destination n'a jamais été construite : « Retoucher » depuis la bibliothèque ouvrait donc
    le tome DERRIÈRE la bibliothèque restée à l'écran, et le bouton paraissait sans effet."""
    fenetre = fenetre_avec_tome
    _tome_traite(tmp_path, projet="P", tome="Vol.2")
    fenetre.retouche.remplir_projets()
    fenetre.aller_a("oeuvres")
    assert fenetre.destination() == "oeuvres"
    fenetre.retoucher("P", "Vol.2")
    assert fenetre.destination() == "retouche"
    assert fenetre.tome.tome == "Vol.2"


def test_la_bibliotheque_emprunte_ce_chemin_la(fenetre_avec_tome, tmp_path):
    fenetre = fenetre_avec_tome
    _tome_traite(tmp_path, projet="P", tome="Vol.2")
    fenetre.retouche.remplir_projets()
    oeuvres = fenetre.aller_a("oeuvres")
    oeuvres.demande_retouche.emit("P", "Vol.2")
    assert fenetre.destination() == "retouche"


def test_un_run_termine_propose_de_retoucher_ses_planches(fenetre_avec_tome):
    fenetre = fenetre_avec_tome
    fenetre._cible_run = {"brique": "manga", "projet": "P", "tome": "Vol.1"}
    fenetre._planches_du_run = [1]
    fenetre._sur_debut(None, GENRE_RUN, "Run manga — P / Vol.1")
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé")
    assert _montre(fenetre.bandeau.bouton_retoucher)
    assert fenetre.bandeau.bouton_retoucher.text() == "Retoucher 1 planche"


def test_un_run_light_novel_ne_propose_pas_la_retouche(fenetre_avec_tome):
    fenetre = fenetre_avec_tome
    # ⚠ `"ln"`, l'identifiant de brique réel de `Fenetre.LANCEURS` — pas « light_novel »,
    # qui est celui de la DESTINATION. Se tromper de vocabulaire ici ferait passer le test
    # pour la mauvaise raison : une brique inconnue ne propose rien non plus.
    fenetre._cible_run = {"brique": "ln", "projet": "P", "tome": "Vol.1"}
    fenetre._sur_debut(None, GENRE_RUN, "Run light novel")
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé")
    assert not _montre(fenetre.bandeau.bouton_retoucher)


def test_le_bouton_du_bilan_mene_au_tome_DU_RUN(fenetre_avec_tome, tmp_path):
    """Pas au tome ouvert dans la retouche : `_cible_run` porte celui du run, et c'est ce qui
    rend le bouton juste quand on a lancé depuis « Manga »."""
    fenetre = fenetre_avec_tome
    _tome_traite(tmp_path, projet="P", tome="Vol.2")
    fenetre.retouche.remplir_projets()
    fenetre._cible_run = {"brique": "manga", "projet": "P", "tome": "Vol.2"}
    fenetre.aller_a("accueil")
    fenetre.bandeau.demande_retouche.emit()
    assert fenetre.destination() == "retouche"
    assert fenetre.tome.tome == "Vol.2"


# --------------------------------------------------------------------------- #
# L35.5 — le verrou se justifie
# --------------------------------------------------------------------------- #

def test_le_verrou_de_run_global_dit_le_tome_l_etape_et_l_avancement(fenetre_avec_tome):
    fenetre = fenetre_avec_tome
    fenetre._cible_run = {"brique": "manga", "projet": "P", "tome": "Vol.1"}
    fenetre._sur_debut(None, GENRE_RUN, "Run manga — P / Vol.1")
    fenetre.progression.entrer("traduction")
    fenetre.progression.avancer(84, 131, "page_0084.png")
    fenetre._repeindre_bandeau()
    texte = fenetre.editeur.etat_planche.text()
    assert "Verrouillé" in texte
    assert "P / Vol.1" in texte
    # ⚠ L'ÉTAPE, et c'est la moitié du point de L35.5 : un panneau gris qui ne dit pas à
    # quelle phase on en est ne dit pas non plus pour combien de temps il le restera.
    assert "Traduction et rendu (5/6)" in texte
    assert "planche 84/131" in texte
    assert _montre(fenetre.editeur.bouton_arret_verrou)


def test_le_motif_meurt_avec_le_verrou(fenetre_avec_tome):
    """Un avancement figé sur un run terminé est un faux."""
    fenetre = fenetre_avec_tome
    fenetre._cible_run = {"brique": "manga", "projet": "P", "tome": "Vol.1"}
    fenetre._sur_debut(None, GENRE_RUN, "Run manga — P / Vol.1")
    fenetre.progression.entrer("traduction")
    fenetre.progression.avancer(84, 131, "")
    fenetre._repeindre_bandeau()
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé")
    assert fenetre.editeur.etat_planche.text() == ""
    assert not _montre(fenetre.editeur.bouton_arret_verrou)


def test_le_bouton_d_arret_de_l_editeur_demande_le_MEME_arret(fenetre_avec_tome, monkeypatch):
    """Un seul mécanisme d'arrêt, donc une seule garantie à tenir."""
    fenetre = fenetre_avec_tome
    appels: list[int] = []
    monkeypatch.setattr(Fenetre, "_arreter_run", lambda self: appels.append(1))
    fenetre.editeur.demande_arret.emit()
    assert appels == [1]


def test_un_relettrage_de_planche_unique_ne_pose_aucun_motif(fenetre_avec_tome):
    """Il a son propre retour, local. Lui superposer un bandeau de run ferait clignoter le
    panneau à chaque geste."""
    fenetre = fenetre_avec_tome
    fenetre.editeur.marquer_verrou(1, "relettrage", True)
    fenetre.editeur.poser_motif_de_verrou("Verrouillé : run en cours sur A / B")
    assert "relettrage" in fenetre.editeur.etat_planche.text()
    assert not _montre(fenetre.editeur.bouton_arret_verrou)


# --------------------------------------------------------------------------- #
# L35.3 point 3 — la mémoire mesurée, affichée
# --------------------------------------------------------------------------- #

def test_la_ligne_de_cache_est_muette_tant_qu_on_n_a_rien_mesure(fenetre_avec_tome):
    assert not _montre(fenetre_avec_tome.retouche.etiquette_cache)


def test_la_ligne_de_cache_apparait_des_que_le_cache_porte_deux_apercus(fenetre_avec_tome):
    fenetre = fenetre_avec_tome
    cache = fenetre.editeur.cache

    class _Faux:
        calques = ()
        fond = None

    for cle in ("a", "b"):
        cache.poser((cle,), _Faux())
    cache.octets = 20 * 1024 * 1024          # un poids plausible, posé à la main
    fenetre.retouche.rafraichir_cache()
    assert _montre(fenetre.retouche.etiquette_cache)
    assert "Mo pièce" in fenetre.retouche.etiquette_cache.text()


def test_la_fenetre_de_prechargement_ne_promet_pas_plus_que_le_plafond(fenetre_avec_tome):
    """Le frein est branché sur le vrai `_precharger`, pas seulement testé en isolation."""
    fenetre = fenetre_avec_tome
    editeur = fenetre.editeur
    editeur.cache.plafond = 10 * 1024 * 1024
    editeur.cache.octets = 9 * 1024 * 1024
    editeur.cache._entrees[("factice",)] = object()
    editeur._precharger()
    assert editeur._fenetre_tenable == 1
    assert len(editeur._fenetre_apercu) <= 1


# --------------------------------------------------------------------------- #
# Étape 0.2 — le miroir de récupération écrit-il vraiment ?
# --------------------------------------------------------------------------- #

def test_le_miroir_de_recuperation_ECRIT_et_se_relit(fenetre_avec_tome):
    """**La promesse d'infobulle du lot 18, enfin vérifiée.** « Un miroir de récupération est
    écrit toutes les 30 s » ne valait que par une docstring ; c'est exactement le défaut du
    `perf.log` du lot 20, dont `Reporter._to_log` sautait toutes les écritures en silence."""
    fenetre = fenetre_avec_tome
    editeur = fenetre.editeur
    assert editeur._minuteur_brouillons.interval() == 30_000
    assert editeur._minuteur_brouillons.isActive()
    _en_attente(fenetre)
    assert editeur.sauver_brouillons() == [1]
    build = fenetre.tome.build_dir
    assert recuperation.resume(build)["planches"] == [1]
    etat = recuperation.lire(build, 1)
    assert etat is not None and etat.manuelles == {0: "pas encore écrit"}


def test_un_second_tic_sans_changement_n_ecrit_rien(fenetre_avec_tome):
    fenetre = fenetre_avec_tome
    _en_attente(fenetre)
    assert fenetre.editeur.sauver_brouillons() == [1]
    assert fenetre.editeur.sauver_brouillons() == []


def test_un_dossier_de_miroir_VIDE_n_est_pas_annonce_comme_une_planche(fenetre_avec_tome):
    """Relevé sur le corpus réel : deux dossiers vides à côté d'un complet faisaient annoncer
    « 3 planches » pour une seule reprise effective, et deux « brouillon illisible »."""
    build = fenetre_avec_tome.tome.build_dir
    recuperation.dossier_planche(build, 7).mkdir(parents=True, exist_ok=True)
    assert recuperation.planches(build) == []
    assert recuperation.lire(build, 7) is None


# --------------------------------------------------------------------------- #
# Critère 3 — un seul `Services`, construit et libéré par la fenêtre
# --------------------------------------------------------------------------- #

def test_un_seul_services_vivant_quoi_qu_on_ouvre(qt_app, tmp_path, monkeypatch):
    """« `Tome` et `Services` restent construits et libérés par la fenêtre ; un test compte
    les instances et vérifie qu'il n'y en a jamais deux » — critère 3 du plan."""
    from manga import services as services_mod

    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    for tome in ("Vol.1", "Vol.2", "Vol.3"):
        _tome_traite(tmp_path, projet="P", tome=tome)

    vivants: list[object] = []
    vrai_init = services_mod.Services.__init__
    vrai_liberer = services_mod.Services.liberer

    def _init(self, *a, **k):
        vivants.append(self)
        return vrai_init(self, *a, **k)

    def _liberer(self):
        if self in vivants:
            vivants.remove(self)
        return vrai_liberer(self)

    monkeypatch.setattr(services_mod.Services, "__init__", _init)
    monkeypatch.setattr(services_mod.Services, "liberer", _liberer)

    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        assert vivants == [], "aucun Services au démarrage — critère du PLAN-31"
        fen.aller_a("retouche")
        for tome in ("Vol.1", "Vol.2", "Vol.3", "Vol.1"):
            fen.retouche.viser("P", tome)
            assert len(vivants) == 1, f"deux Services vivants après {tome}"
        assert fen.services is vivants[0]
    finally:
        _arreter(fen)
        _detruire(fen)


def test_ouvrir_n_est_appele_par_aucun_chemin_de_demarrage(qt_app, tmp_path, monkeypatch):
    """Critère 4 : le test du `PLAN-31` reste vert après le découplage."""
    from gui.editeur import PanneauEditeur

    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path)
    appels: list[str] = []
    vrai = PanneauEditeur.ouvrir
    monkeypatch.setattr(PanneauEditeur, "ouvrir",
                        lambda self, tome: (appels.append(tome.tome), vrai(self, tome))[1])
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.show()
        QApplication.processEvents()
        assert appels == [], "le démarrage n'ouvre aucun tome"
        assert fen.tome is None and fen.services is None
        fen.aller_a("retouche")
        assert appels == [], "construire la destination n'ouvre toujours rien"
        fen.retouche.viser("P", "Vol.1")
        assert appels == ["Vol.1"], "il faut un geste"
    finally:
        _arreter(fen)
        _detruire(fen)


def test_aucune_boite_n_est_posee_sur_un_changement_de_destination_sans_tome(qt_app,
                                                                            tmp_path,
                                                                            monkeypatch):
    """Le cas dégradé : une session qui n'a jamais ouvert la retouche navigue librement."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    (tmp_path / "sources").mkdir(exist_ok=True)
    (tmp_path / "build").mkdir(exist_ok=True)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: pytest.fail("aucune modale ici"))
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        for identifiant in ("manga", "oeuvres", "accueil", "webtoon"):
            assert fen.aller_a(identifiant) is not None
    finally:
        _arreter(fen)
        _detruire(fen)


def test_les_libelles_du_verrou_et_du_bandeau_viennent_de_la_meme_decision(fenetre_avec_tome):
    """Deux sources pour un même chiffre finissent toujours par diverger."""
    fenetre = fenetre_avec_tome
    fenetre._cible_run = {"brique": "manga", "projet": "P", "tome": "Vol.1"}
    fenetre._sur_debut(None, GENRE_RUN, "Run manga — P / Vol.1")
    fenetre.progression.entrer("traduction")
    fenetre.progression.avancer(3, 10, "page_0003.png")
    fenetre._repeindre_bandeau()
    attendu = vue.motif_de_verrou(fenetre.progression.etat(), fenetre._cible_libelle)
    assert fenetre.editeur.etat_planche.text() == attendu
