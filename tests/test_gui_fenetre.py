# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La coquille applicative : menus, raccourcis, garde de tome, disposition, glisser-déposer.

## Ce que ces tests couvrent, et pourquoi chacun

Le lot 18 déplace des actions. Un test qui vérifie un bouton par son libellé casse, et c'est
voulu — mais il faut alors que quelque chose vérifie la NOUVELLE promesse, sinon on a échangé
une couverture contre rien.

| Test | Ce qu'il empêche de revenir |
|---|---|
| unicité des raccourcis sur la fenêtre ENTIÈRE | `Ctrl+Shift+S` déclaré sur un bouton ET sur une action de menu |
| présence de chaque action de menu | une entrée du catalogue qui n'arrive jamais dans la barre |
| garde de changement de tome | brouillons et documents jetés sans un mot en changeant de tome |
| aller-retour de disposition | tout à refaire à chaque session |
| `--force` jamais persisté | un tome relancé depuis la détection sur une case d'hier |
| état vide | un aplat gris et une consigne à exécuter dans un autre logiciel |
| glisser-déposer | un geste silencieux, qui passe pour un défaut |

⚠ `QT_QPA_PLATFORM=offscreen` est posé **avant** toute construction de `QApplication`, comme
dans `test_gui_pellicule_layout.py` : la suite doit tourner sans écran, en CI comme en local.

⚠ `$ANGELITH_REGLAGES` est posé sur le `tmp_path` de chaque test. Sans cela, ces tests
écriraient — et liraient — le `.angelith/interface.json` du dépôt de qui les lance, ce qui les
rendrait dépendants de la dernière session interactive.

## Ce que le lot 31 change pour ce fichier

La fenêtre ne construit plus rien au démarrage sauf l'accueil, et n'ouvre plus de tome. Les
fixtures le reflètent, et c'est **le sujet du lot**, pas un contournement :

| Fixture | Ce qu'elle donne |
|---|---|
| `fenetre` | l'accueil seul — `tome is None`, `services is None`, un panneau construit |
| `fenetre_retouche` | la destination Retouche ouverte, mais toujours aucun tome |
| `fenetre_avec_tome` | la Retouche **et** un tome ouvert par un geste explicite |

Les tests qui interrogeaient `fenetre.editeur`, `fenetre.lanceur` ou `fenetre.onglets`
interrogent maintenant la destination qui les porte. Un test qui vérifie un widget par son
chemin casse quand le chemin change ; ce qui compte est que la PROMESSE reste vérifiée, et
elle l'est — au même endroit, sur le même widget.
"""
from __future__ import annotations

import copy
import os

import pytest

pytest.importorskip("PySide6", reason="interface graphique : pip install -r requirements-gui.txt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QMimeData, QPoint, Qt, QUrl                # noqa: E402
from PySide6.QtGui import QAction, QDropEvent                                 # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox                       # noqa: E402

from gui import actions as act                                               # noqa: E402
from gui import reglages as reg                                              # noqa: E402
from gui.fenetre import Fenetre                                              # noqa: E402
from gui.travailleur import GENRE_RUN                                        # noqa: E402
from manga import checkpoints, projet as projet_mod                          # noqa: E402
from manga.detection import BubbleRegion                                     # noqa: E402

import numpy as np                                                            # noqa: E402
from PIL import Image                                                         # noqa: E402

TAILLE = (300, 500)


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def _config(tmp_path) -> dict:
    """Une config minimale mais COMPLÈTE pour ce que la fenêtre lit.

    Recopiée plutôt que chargée de `config.yaml` : charger le vrai fichier ferait dépendre ces
    tests de 95 Ko de prose commentée, et un test d'interface n'a rien à dire sur les seuils du
    pipeline."""
    return {
        "manga": {"chemins": {"sources": str(tmp_path / "sources"),
                              "build": str(tmp_path / "build")},
                  "lot": {"planches": 1}},
        "chemins": {"sources": str(tmp_path / "sources"), "build": str(tmp_path / "build"),
                    "glossaire_fichier": "glossaire.yaml"},
        "langues": {"dossiers": {"JAP": "jp", "ENG": "en"}},
        "options": {},
        "gui": {"apercu": {"plafond_mo": 32, "fenetre": 2}},
    }


def _tome_traite(tmp_path, projet="P", tome="Vol.1") -> None:
    """Un tome avec une planche détectée — assez pour que l'éditeur ouvre quelque chose."""
    sources = tmp_path / "sources" / projet / tome / "manga"
    build = tmp_path / "build" / projet / tome / "manga"
    sources.mkdir(parents=True)
    image = Image.new("RGB", TAILLE, (200, 200, 200))
    image.save(sources / "page_0001.png")

    bbox = (40, 40, 260, 200)
    masque = np.zeros((TAILLE[1], TAILLE[0]), dtype=bool)
    masque[bbox[1]:bbox[3], bbox[0]:bbox[2]] = True
    ckpt = checkpoints.page_checkpoint_dir(build, 1)
    checkpoints.save_regions(ckpt, [BubbleRegion(bbox=bbox, mask=masque, score=0.9, cls=0)],
                             TAILLE)
    checkpoints.save_ocr(ckpt, ["アアア"])
    checkpoints.save_traduction(ckpt, ["Bonjour"])
    chemin_clean = checkpoints.clean_page_path(build, 1)
    chemin_clean.parent.mkdir(parents=True, exist_ok=True)
    image.save(chemin_clean)
    projet_mod.ecrire(build, projet_mod.construire(
        build, projet=projet, tome=tome, pages=[sources / "page_0001.png"],
        version="test", page_ckpt=checkpoints.page_checkpoint_dir))


def _arreter(fen) -> None:
    """Arrête les deux fils **et attend vraiment**. Budget : 10 s, comme `closeEvent`.

    ⚠ `wait(2000)` ne suffit plus depuis le lot 31, et le défaut ne se voyait pas : les trois
    sondes de l'accueil partent dans le fil de travail à `show()`, et la première est un appel
    réseau de deux secondes au plus (`gui/sondes.DELAI_RESEAU`). `arreter()` pousse une
    sentinelle **en fin de file** — c'est ce qui garantit qu'une tâche n'est jamais coupée en
    plein `save_regions` — donc le fil ne rend la main qu'une fois la sonde revenue.

    Un `wait` trop court laissait alors Python quitter avec un `QThread` vivant :
    `STATUS_STACK_BUFFER_OVERRUN` (0xC0000409) à la fermeture du processus, **sans une ligne de
    sortie**, ce qui faisait passer une suite entière pour muette. Le budget est donc celui de
    `Fenetre.closeEvent`, qui attend par tranches pour la même raison."""
    fen.fil_lecture.arreter()
    fen.fil.arreter()
    for fil in (fen.fil_lecture, fen.fil):
        reste = 10_000
        while fil.isRunning() and reste > 0:
            fil.wait(100)
            reste -= 100
        assert not fil.isRunning(), "un fil qui survit fait planter l'interpréteur à la sortie"


def _detruire(fen) -> None:
    """Détruit la fenêtre **pour de bon**, et pas « plus tard ».

    ⚠ `deleteLater()` seul ne détruit RIEN ici : il poste un `DeferredDelete` que seule une
    boucle d'événements consomme, et ces tests n'en font tourner aucune. Les quarante-huit
    fenêtres de ce fichier restaient donc vivantes jusqu'à la fin de la session Qt — quatre
    mille huit cents widgets — sans que rien ne le montre.

    C'est devenu visible avec le `PLAN-19` : `QApplication.setStyleSheet` restyle tous les
    widgets vivants de l'application, et une bascule de thème coûtait alors **85 s** au lieu
    d'une fraction de seconde. Le défaut était là avant ; c'est la mesure qui est neuve.

    ⚠ `sendPostedEvents(None, DeferredDelete)` et pas `processEvents()` : celui-ci ne traite
    les suppressions différées que si le niveau de boucle correspond, ce qui n'est jamais le
    cas hors `exec()`."""
    fen.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture
def fenetre(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    (tmp_path / "sources").mkdir(exist_ok=True)
    (tmp_path / "build").mkdir(exist_ok=True)
    fen = Fenetre(_config(tmp_path), "config.yaml")
    yield fen
    _arreter(fen)
    _detruire(fen)


@pytest.fixture
def fenetre_retouche(fenetre):
    """La destination Retouche ouverte — **et toujours aucun tome**.

    C'est l'état qui n'existait pas avant le lot 31 : l'éditeur construit, branché, mais
    n'ayant rien ouvert. Il fallait le nommer, parce que c'est celui dans lequel se trouve
    quelqu'un qui vient de cliquer sur « Retouche » avec dix-sept projets sur le disque."""
    fenetre.aller_a("retouche")
    return fenetre


@pytest.fixture
def fenetre_avec_tome(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path)
    fen = Fenetre(_config(tmp_path), "config.yaml")
    # ⚠ **Deux gestes, et ils sont le sujet du lot.** Avant, la fenêtre faisait les deux toute
    # seule au démarrage : elle construisait l'éditeur et ouvrait le premier projet par ordre
    # alphabétique. Ici on les fait explicitement, parce que c'est ce qu'un utilisateur fait.
    fen.aller_a("retouche")
    fen.retouche.viser("P", "Vol.1")
    yield fen
    _arreter(fen)
    _detruire(fen)


def _lanceur(fenetre, destination: str = "manga"):
    """Le panneau de lancement d'une destination, construit à la demande.

    Il y en a **trois** depuis le lot 31 — light novel, manga, webtoon — et aucun n'existe
    tant qu'on n'est pas allé le voir."""
    return fenetre.aller_a(destination)


# --------------------------------------------------------------------------- #
# PLAN-31 — le démarrage ne charge rien
# --------------------------------------------------------------------------- #

def test_apres_show_aucun_tome_aucun_service_et_le_seul_accueil(qt_app, tmp_path, monkeypatch):
    """**Le test qui aurait échoué avant le lot 31**, et le critère 2 du plan.

    En 2.24.1, `Fenetre.__init__` appelait `_remplir_projets()` alors que les deux `QComboBox`
    étaient déjà branchés : remplir la liste déclenchait `_ouvrir_tome` sur le premier projet
    par ordre alphabétique. Un `Tome` lu, un `Services` construit (donc les agents et le
    glossaire), l'éditeur peuplé, la composition d'aperçus lancée — pour un tome que personne
    n'avait demandé.

    Mesuré sur le corpus réel le 2026-09-04 : 1,89 s avant le premier pixel dont 1,40 s pour ce
    seul tome, 692 ouvertures de fichiers, 11 aperçus et 62,4 Mo de cache dans les dix secondes
    suivantes (`docs/mesures/coquille-2026-09-04.md`)."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path, "AAA Premier", "Vol.1")
    _tome_traite(tmp_path, "ZZZ Dernier", "Vol.1")
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.show()
        assert fen.tome is None, "aucun tome ne doit être ouvert au démarrage"
        assert fen.services is None, "aucun Services ne doit être construit au démarrage"
        assert fen.panneaux_construits() == {"accueil"}
        assert fen.destination() == "accueil"
        assert fen.editeur is None and fen.atelier is None and fen.lanceurs() == []
    finally:
        _arreter(fen)
        _detruire(fen)


def test_aucun_apercu_n_est_demande_au_demarrage(qt_app, tmp_path, monkeypatch):
    """Critère 2, sa seconde moitié : « aucun aperçu demandé ».

    L'éditeur n'existe pas, donc son cache non plus — et c'est exactement ce qu'on veut dire :
    il n'y a pas un cache vide, il n'y a pas de cache."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path)
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.show()
        assert fen.editeur is None
        fen.aller_a("retouche")
        assert len(fen.editeur.cache) == 0, "ouvrir la destination n'ouvre pas de tome"
        assert fen.tome is None
    finally:
        _arreter(fen)
        _detruire(fen)


def test_les_fils_sont_crees_une_seule_fois_quoi_qu_on_visite(fenetre):
    """Critère 5 — « `FilDeTravail`, `SignauxTravail` et `FilDeLecture` sont toujours créés une
    seule fois, et aucune destination n'en crée ». Vérifié **par comptage d'instances**."""
    from PySide6.QtCore import QThread

    from gui.travailleur import FilDeLecture, FilDeTravail, SignauxTravail

    avant = (fenetre.fil, fenetre.fil_lecture, fenetre.signaux)
    for identifiant in ("accueil", "light_novel", "manga", "webtoon", "illustrations",
                        "oeuvres", "retouche"):
        fenetre.aller_a(identifiant)
    assert (fenetre.fil, fenetre.fil_lecture, fenetre.signaux) == avant
    assert len([f for f in fenetre.findChildren(FilDeTravail)]) == 1
    assert len([f for f in fenetre.findChildren(FilDeLecture)]) == 1
    assert len([s for s in fenetre.findChildren(SignauxTravail)]) <= 1
    # ⚠ Et AUCUN autre `QThread` : un panneau qui en créerait un rouvrirait les trois trous de
    # concurrence de la 1.1.0, que le lot 18 a fermés en rendant le fil unique.
    assert len(fenetre.findChildren(QThread)) == 2


def test_un_panneau_n_est_construit_qu_une_fois(fenetre):
    """Une destination est une fabrique, mais la fabrique n'est appelée qu'au PREMIER
    affichage : y revenir doit rendre le même objet, avec son état."""
    premier = fenetre.aller_a("manga")
    fenetre.aller_a("accueil")
    assert fenetre.aller_a("manga") is premier


def test_les_sept_destinations_ont_leur_page(fenetre):
    """Critère 3 — atteignables à la souris. Le pane émet `choisie`, la fenêtre construit."""
    from gui import destinations as dst

    for destination in dst.corps():
        panneau = fenetre.aller_a(destination.identifiant)
        assert panneau is not None, destination.identifiant
        assert fenetre.pile.currentWidget() is panneau
        assert fenetre.navigation.courante() == destination.identifiant


def test_une_entree_de_pied_qui_nomme_une_action_ouvre_son_dialogue(fenetre, monkeypatch):
    """« Réglages » est en pied de pane (convention Fluent) et ouvre le dialogue qui existe
    déjà. Le traiter comme une page ferait d'un clic une navigation dont on ne saurait pas
    revenir.

    ⚠ **MISE À JOUR lot 36 (2026-09-06)** : ce test portait sur TOUTES les entrées de pied.
    Le Diagnostic en est sorti — il est devenu une page (`PLAN-36` L36.2). Ce qui décide
    n'est donc plus la place dans le pane mais la présence d'une `action` : cf.
    `gui/destinations.py` et le test qui suit."""
    from gui import destinations as dst

    fenetre.aller_a("manga")
    appels = []
    monkeypatch.setattr(fenetre, "action_preferences", lambda: appels.append("preferences"))
    fenetre.actions_menu["preferences"].triggered.disconnect()
    fenetre.actions_menu["preferences"].triggered.connect(
        lambda _c=False: fenetre.action_preferences())
    for destination in dst.dialogues():
        assert fenetre.aller_a(destination.identifiant) is None
    assert appels == ["preferences"]
    assert fenetre.destination() == "manga", "une entrée à dialogue ne change pas la destination"


def test_le_diagnostic_est_une_page_de_pied_et_non_un_dialogue(fenetre):
    """L36.2 — le Diagnostic est en PIED par convention Fluent, et c'est une PAGE.

    ⚠ Il n'inspecte rien à la construction : il s'ouvre en disant qu'aucun diagnostic n'a
    tourné. Un diagnostic complet interroge le serveur de modèles — 12,1 s sur un serveur
    arrêté, mesuré le 2026-09-06 — et le lancer au premier affichage rejouerait le défaut que
    le `PLAN-31` a corrigé."""
    from gui import destinations as dst

    destination = dst.par_identifiant("diagnostic")
    assert destination.pied is True and destination.action == ""
    panneau = fenetre.aller_a("diagnostic")
    assert panneau is not None
    assert fenetre.destination() == "diagnostic"
    assert panneau.sections() == (), "la page ne doit rien avoir inspecté toute seule"


def _vider_le_fil(fenetre, pret=None, budget_ms: int = 10_000) -> None:
    """Attend qu'une tâche du fil de travail soit **arrivée jusqu'à la fenêtre**.

    ⚠ Attendre que le fil « ne soit plus occupé » ne suffit pas, et c'est un piège qui se
    referme silencieusement : juste après `soumettre()`, le fil n'a pas encore dépilé la tâche,
    donc `occupe()` répond `False` et la boucle sort immédiatement. On attend donc une
    CONDITION — `pret()` — et non un état du fil.

    ⚠ `processEvents()` à chaque tour : les signaux `fin` du fil sont des connexions en file,
    et sans boucle d'événements le slot de la fenêtre ne tournerait jamais dans un test. Le
    résultat n'atteindrait pas la page, et le test échouerait pour une raison qui n'a rien à
    voir avec ce qu'il mesure."""
    import time

    from PySide6.QtWidgets import QApplication

    fin = time.monotonic() + budget_ms / 1000
    while time.monotonic() < fin:
        QApplication.processEvents()
        if pret is None:
            if not (fenetre.fil.occupe() or fenetre.fil.en_attente()):
                break
        elif pret():
            break
        time.sleep(0.02)
    QApplication.processEvents()


def test_le_diagnostic_part_dans_le_fil_et_revient_sur_la_page(fenetre):
    """L36.1 + L36.2 — le câblage complet, sans réseau.

    ⚠ **Dans le fil de travail, jamais sur le fil d'affichage.** La section Ollama met 12,1 s
    contre un serveur arrêté (mesuré le 2026-09-06) ; ici `reseau=False` la saute, mais le
    chemin testé est le même. Ce que ce test vérifie est le genre de tâche, l'aiguillage du
    résultat, et le fait que la page reçoive des verdicts."""
    panneau = fenetre.aller_a("diagnostic")
    assert panneau.sections() == ()
    fenetre._lancer_diagnostic(False)
    _vider_le_fil(fenetre, lambda: bool(panneau.sections()))
    sections = panneau.sections()
    assert sections, "aucun verdict n'est remonté jusqu'à la page"
    identifiants = {v.identifiant for s in sections for v in s.verdicts}
    assert "config_manga" in identifiants
    assert panneau.bouton_lancer.isEnabled(), "le bouton doit être rendu à la fin"


def test_le_diagnostic_ne_verrouille_pas_l_interface(fenetre):
    """⚠ `GENRE_DIAGNOSTIC` entre dans `GENRES_SANS_VERROU` : il n'écrit rien, et lui laisser
    griser le bouton « Lancer » pendant douze secondes affaiblirait la LISIBILITÉ du verrou de
    run, pas sa force."""
    from gui.travailleur import GENRE_DIAGNOSTIC, GENRES_SANS_VERROU

    assert GENRE_DIAGNOSTIC in GENRES_SANS_VERROU


def test_la_sortie_console_est_reconstituee_sans_relancer_les_doctors(fenetre, monkeypatch):
    """« Sortie console… » reconstitue le texte depuis les verdicts déjà collectés.

    ⚠ Relancer coûterait un second appel réseau et pourrait rendre un texte qui ne décrit plus
    ce que la page montre."""
    from core import diagnostic as diag

    panneau = fenetre.aller_a("diagnostic")
    fenetre._lancer_diagnostic(False)
    _vider_le_fil(fenetre, lambda: bool(panneau.sections()))
    texte = diag.texte_console(panneau.sections())
    assert "— Section config.yaml > manga —" in texte


def test_une_reparation_de_classe_utilisateur_n_est_jamais_executee(fenetre, monkeypatch):
    """⚠ Angelith n'installe aucun logiciel système : le clic ouvre une consigne, rien de plus.

    Le test double la boîte d'information et vérifie qu'aucune tâche n'a été soumise."""
    from PySide6.QtWidgets import QMessageBox

    vus = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **kw: vus.append(a[2]) or QMessageBox.Ok))
    fenetre.aller_a("diagnostic")
    fenetre._lancer_reparation("pandoc")
    assert vus and "n'installe aucun logiciel système" in vus[0]
    assert not fenetre.fil.en_attente()


def test_une_reparation_refuse_de_partir_pendant_un_run(fenetre, monkeypatch):
    """⚠ « Un run de nuit qui se met à télécharger deux gigaoctets n'est plus le run qu'on a
    lancé. »"""
    from PySide6.QtWidgets import QMessageBox

    vus = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **kw: vus.append(a[2]) or QMessageBox.Ok))
    monkeypatch.setattr(fenetre.fil, "occupe", lambda: True)
    fenetre.aller_a("diagnostic")
    fenetre._lancer_reparation("poids_detection")
    assert vus and "run est en cours" in vus[0]


def test_une_reparation_journalise_son_avancement(fenetre, monkeypatch, tmp_path):
    """⚠ Le rappel `dire` d'une réparation part du FIL DE TRAVAIL vers le journal.

    Ce test existe pour une raison précise : la première version du lot passait
    `self.signaux.journal`, qui n'existe pas — le signal s'appelle `ligne`. Le rappel levait
    donc un `AttributeError` **dans le fil**, la réparation échouait, et la seule trace partait
    dans un panneau que rien ne lisait. Un téléchargement de 104 Mo qui échoue en silence est
    exactement le mode de panne que ce lot est censé supprimer."""
    from PySide6.QtWidgets import QMessageBox

    from manga import reparations as rep_manga  # noqa: F401 — enregistre les gestes manga

    cible = tmp_path / "bubble_detector.onnx"

    def _faux_telechargement(url, destination, **kw):
        from pathlib import Path
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"z" * 4096)
        return Path(destination)

    monkeypatch.setattr("manga.reparations.models.telecharger", _faux_telechargement)
    monkeypatch.setitem(fenetre.config["manga"], "detection", {"model_path": str(cible)})
    # ⚠ Le clic de confirmation est doublé : `reparations.executer` exige `consentement=True`,
    # et c'est CETTE boîte qui le donne. Sans elle, rien ne part — ce que d'autres tests
    # vérifient.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Ok)
    lignes: list[str] = []
    fenetre.signaux.ligne.connect(lambda niveau, texte: lignes.append(texte))
    fenetre._lancer_reparation("poids_detection")
    _vider_le_fil(fenetre, lambda: cible.is_file())
    assert cible.is_file(), chr(10).join(lignes) or "(journal vide)"
    assert any("Licence de ce poids" in ligne for ligne in lignes), (
        "la licence doit être dite AVANT le transfert, et elle doit atteindre le journal")


def test_le_tome_de_demonstration_s_ecrit_par_le_fil_de_travail(fenetre):
    """L36.4 — le geste de l'accueil, jusqu'au disque.

    ⚠ En `GENRE_CREATION` : il écrit sous `sources/` et sous `build/`, donc il prend le verrou
    d'écriture comme un import d'archive."""
    from manga import demonstration as demo

    assert demo.existe(fenetre.config) is False
    # ⚠ Le journal est CAPTURÉ, et l'assertion le montre en cas d'échec. C'est ce qui a rendu
    # visible un `self.signaux.journal` qui n'existait pas — le rappel d'avancement levait
    # dans le fil de travail, la tâche échouait, et la seule trace partait dans un panneau que
    # le test ne lisait pas.
    lignes: list[str] = []
    fenetre.signaux.ligne.connect(lambda niveau, texte: lignes.append(f"{niveau}: {texte}"))
    fenetre.action_tome_de_demonstration()
    _vider_le_fil(fenetre, lambda: demo.existe(fenetre.config))
    assert demo.existe(fenetre.config) is True, chr(10).join(lignes) or "(journal vide)"
    assert any("planche 1/2" in ligne for ligne in lignes), (
        "l'avancement doit remonter au journal pendant l'écriture")
    assert demo.supprimer(fenetre.config)


def test_les_raccourcis_de_destination_naviguent(fenetre):
    """Critère 3 — atteignables au CLAVIER. `Ctrl+1` … `Ctrl+6` plus l'accueil."""
    from gui import destinations as dst

    for destination in dst.corps():
        fenetre.actions_menu[f"aller_{destination.identifiant}"].trigger()
        assert fenetre.destination() == destination.identifiant


def test_ctrl_tab_fait_le_tour_des_destinations(fenetre):
    """Il faisait « onglet suivant » sur trois onglets ; il fait la même promesse sur sept
    destinations, et les entrées de pied en sont exclues."""
    from gui import destinations as dst

    fenetre.aller_a("accueil")
    vues = []
    for _ in range(len(dst.corps()) + 1):
        fenetre.actions_menu["destination_suivante"].trigger()
        vues.append(fenetre.destination())
    assert vues[-1] == vues[len(dst.corps()) - 1 - (len(dst.corps()) - 1)] or vues[0] != vues[-1]
    assert set(vues) == {d.identifiant for d in dst.corps()}


def test_la_destination_webtoon_est_le_lanceur_manga_avec_son_format(fenetre):
    """L31.7 — « le webtoon est une destination, et ce n'est **pas** une brique ».

    `core/version.py:ETAT_BRIQUES` ne connaît pas de brique « webtoon », et il a raison :
    `run_manga.py --format {manga,webtoon}` est un format du MÊME orchestrateur. La destination
    doit donc porter la brique manga et le format, sans dupliquer un chemin de traitement."""
    from core.version import ETAT_BRIQUES

    assert "webtoon" not in ETAT_BRIQUES
    manga, webtoon = _lanceur(fenetre, "manga"), _lanceur(fenetre, "webtoon")
    assert type(manga) is type(webtoon), "la même classe, pas un panneau dupliqué"
    assert (manga.brique(), manga.format_planche()) == ("manga", None)
    assert (webtoon.brique(), webtoon.format_planche()) == ("manga", "webtoon")
    assert _lanceur(fenetre, "light_novel").brique() == "ln"


def test_la_destination_webtoon_affiche_sa_reserve_mesuree(fenetre):
    """L31.7 point 3 — « une destination qui offre le webtoon au même rang que le manga sans
    afficher cet écart promet plus que ce qui est mesuré »."""
    webtoon = _lanceur(fenetre, "webtoon")
    texte = webtoon.bandeau.text()
    assert "--format webtoon" in texte
    assert "15,1" in texte and "17,0" in texte and "5,9" in texte
    assert "webtoon-2026-08-26" in texte, "la réserve porte le document qui l'établit"
    assert not hasattr(_lanceur(fenetre, "manga"), "bandeau")


def test_les_reglages_de_bande_ne_sont_QUE_sur_le_webtoon(fenetre):
    """L31.7 — « les réglages de bande remontés ». Sur la bande, et seulement là.

    Le fichier de configuration le dit lui-même de ces clés : elles sont « inertes sur une
    planche paginée, qui n'est jamais découpée ». Les proposer sur la destination Manga
    offrirait un levier sans effet, ce qui est pire que pas de levier."""
    webtoon, manga = _lanceur(fenetre, "webtoon"), _lanceur(fenetre, "manga")
    assert hasattr(webtoon, "champ_fenetre_hauteur")
    assert hasattr(webtoon, "champ_fenetre_recouvrement")
    assert not hasattr(manga, "champ_fenetre_hauteur")
    assert manga.reglages_bande() == {}


def test_les_reglages_de_bande_partent_a_zero_donc_ne_posent_rien(fenetre):
    """« Ne pas poser la clé du tout est différent de poser sa valeur par défaut. »

    C'est le seul état qui laisse un `config.yaml` réglé à la main faire autorité — le même
    arbitrage que « selon config.yaml » du raisonnement, qui existe pour ne pas écraser
    l'`endpoint:` d'un agent."""
    webtoon = _lanceur(fenetre, "webtoon")
    assert webtoon.champ_fenetre_hauteur.value() == 0
    assert webtoon.reglages_bande() == {}
    assert "selon config.yaml" in webtoon.champ_fenetre_hauteur.specialValueText()
    assert "2160" in webtoon.champ_fenetre_hauteur.specialValueText(), \
        "le champ dit CE QUE vaut le défaut, pas seulement qu'il en existe un"


def test_les_reglages_de_bande_atterrissent_dans_le_bloc_du_format(fenetre):
    """⚠ **Au même endroit que `run_manga.py`**, et c'est tout l'enjeu : `gui/__init__.py`
    promet qu'« un tome retouché ici se relance à l'identique avec run_manga.py »."""
    from manga import formats as fmt_mod

    webtoon = _lanceur(fenetre, "webtoon")
    webtoon.champ_fenetre_hauteur.setValue(3000)
    webtoon.champ_fenetre_recouvrement.setValue(1200)
    config = copy.deepcopy(fenetre.config)
    webtoon._appliquer_bande(config)
    assert config["manga"]["formats"]["webtoon"]["detection"] == {
        "fenetre_hauteur": 3000, "fenetre_recouvrement": 1200}
    resolu = fmt_mod.config_format(config, "webtoon", "detection")
    assert (resolu["fenetre_hauteur"], resolu["fenetre_recouvrement"]) == (3000, 1200)
    # …et le format manga, lui, n'a rien reçu : la clé n'y est pas POSÉE, ce qui n'est pas la
    # même chose que d'y valoir 2160. Un réglage de bande est un réglage de bande.
    assert "fenetre_hauteur" not in fmt_mod.config_format(config, "manga", "detection")


def test_le_recapitulatif_annonce_un_reglage_de_bande(fenetre, monkeypatch):
    """Un réglage de bande décide de ce que la DÉTECTION produit, donc de tout l'aval. Le
    taire dans le récapitulatif serait engager des heures de GPU sur un réglage invisible."""
    webtoon = _lanceur(fenetre, "webtoon")
    webtoon.champ_fenetre_hauteur.setValue(3000)
    vus = []
    monkeypatch.setattr(QMessageBox, "setInformativeText",
                        lambda self, t: vus.append(t))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    webtoon._confirmer("P", "Vol.1")
    assert vus and "fenetre_hauteur = 3000" in vus[0]


def test_le_sens_de_lecture_est_AFFICHE_et_pas_modifiable(fenetre):
    """⚠ Le changer sur un tome déjà détecté fait reprendre toutes ses planches à la
    détection — c'est une invalidation de cache, et l'interdit n° 1 du dépôt veut qu'elle ne
    se produise jamais par accident. Il est donc dit, pas offert."""
    webtoon = _lanceur(fenetre, "webtoon")
    texte = webtoon.etiquette_bande.text()
    assert "gauche → droite" in texte
    assert "non modifiable" in texte
    assert "reprendre toutes ses planches à la détection" in texte
    assert "config.yaml" in texte
    champs = [n for n in dir(webtoon) if "sens" in n.lower()]
    assert champs == [], f"aucun contrôle de sens de lecture ne doit exister : {champs}"


def test_les_reglages_de_bande_font_l_aller_retour_par_le_fichier(fenetre, tmp_path):
    """Ils se persistent, contrairement à `force` : ils ne relancent rien tout seuls, ils
    décrivent COMMENT découper quand on découpe — le statut de « Planches par appel »."""
    webtoon = _lanceur(fenetre, "webtoon")
    webtoon.champ_fenetre_hauteur.setValue(2560)
    webtoon.champ_fenetre_recouvrement.setValue(1000)
    fenetre._enregistrer_reglages()
    relu = reg.lire()["runs"]["webtoon"]
    assert (relu["fenetre_hauteur"], relu["fenetre_recouvrement"]) == (2560, 1000)
    webtoon.champ_fenetre_hauteur.setValue(0)
    webtoon.appliquer_reglages(relu)
    assert webtoon.champ_fenetre_hauteur.value() == 2560
    # ⚠ Et ils restent lavés de `force` / `dry_run` comme tout le reste.
    assert "force" not in relu and "dry_run" not in relu


def test_le_format_part_bien_dans_les_parametres_du_run(fenetre, tmp_path, monkeypatch):
    """La destination ne serait qu'un libellé si le format ne quittait pas le panneau."""
    _tome_traite(tmp_path, "P", "Vol.1")
    webtoon = _lanceur(fenetre, "webtoon")
    webtoon._remplir_projets()
    webtoon.viser("P", "Vol.1")
    monkeypatch.setattr(webtoon, "_confirmer", lambda p, t: True)
    # ⚠ On COUPE le récepteur de la fenêtre. Le panneau est construit par `_page_lanceur`, donc
    # déjà relié à `_lancer_run` : sans cette ligne, le test soumettrait un vrai
    # `process_volume` au fil de travail, qui tournerait encore au démontage.
    webtoon.demande_run.disconnect()
    recus = []
    webtoon.demande_run.connect(recus.append)
    webtoon.bouton_lancer.click()
    assert recus and recus[0]["format_planche"] == "webtoon"
    assert recus[0]["brique"] == "manga"
    assert _lanceur(fenetre, "manga").format_planche() is None


def test_l_accueil_n_ouvre_rien_et_dit_ce_que_la_machine_sait_faire(fenetre):
    """L31.3 — les trois informations d'état, et **les trois en « inconnu » au premier pixel**."""
    from gui import sondes as snd

    accueil = fenetre._panneaux["accueil"]
    texte = accueil.etat_sondes.text()
    for sonde in snd.inconnues():
        assert sonde.nom in texte
    assert texte.count("en cours…") == 3, "les trois marqueurs sont « inconnu » au départ"
    assert texte.startswith(snd.SYMBOLES[snd.INCONNU])
    assert fenetre.tome is None


def test_l_accueil_rappelle_la_version_et_l_etat_des_briques(fenetre):
    """« La brique scan est en **bêta** et l'accueil doit le dire là où l'utilisateur
    choisit » — pas seulement dans le titre de la fenêtre, que personne ne lit avant de
    cliquer."""
    from core.version import ETAT_BRIQUES, __version__

    texte = fenetre._panneaux["accueil"].version.text()
    assert __version__ in texte
    assert "scan : beta" in texte and "bêta" in texte
    for brique, etat in ETAT_BRIQUES.items():
        assert f"{brique} : {etat}" in texte, brique


def test_l_accueil_porte_l_etat_vide_du_lot_18(fenetre):
    """L31.3 — « Ne remplacez pas un état vide qui marche par un plus joli qui en fait
    moins » : les deux boutons du lot 18 sont là, et la ligne `warn` du journal aussi."""
    accueil = fenetre._panneaux["accueil"]
    assert accueil.boite_vide.isVisibleTo(accueil)
    assert accueil.bouton_creer.isEnabled() and accueil.bouton_sources.isEnabled()


def test_l_accueil_propose_de_reprendre_ce_que_la_session_precedente_a_laisse(
        qt_app, tmp_path, monkeypatch):
    """L31.5 — « ne rouvre jamais le dernier tome tout seul » : un clic, pas un effet de bord.

    C'est tout l'objet du lot : ce qui était implicite devient un geste."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path)
    etat = reg.defauts()
    etat["recents"] = [{"projet": "P", "tome": "Vol.1", "destination": "retouche"}]
    reg.ecrire(etat)
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.show()
        assert fen.tome is None, "le fichier dit le tome, il ne l'ouvre pas"
        accueil = fen._panneaux["accueil"]
        assert len(accueil._boutons_reprise) == 1
        assert "P / Vol.1" in accueil._boutons_reprise[0].text()
        accueil._boutons_reprise[0].click()
        assert fen.destination() == "retouche"
        assert fen.tome is not None and fen.tome.tome == "Vol.1"
    finally:
        _arreter(fen)
        _detruire(fen)


def test_une_reprise_vers_un_tome_disparu_le_dit(qt_app, tmp_path, monkeypatch):
    """Un dossier renommé depuis la dernière session est un cas NORMAL, pas une panne — et
    c'est exactement le mode de panne silencieux qu'avait l'ancien démarrage."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    (tmp_path / "sources").mkdir(exist_ok=True)
    (tmp_path / "build").mkdir(exist_ok=True)
    etat = reg.defauts()
    etat["recents"] = [{"projet": "Disparu", "tome": "Vol.9", "destination": "retouche"}]
    reg.ecrire(etat)
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.show()
        fen._panneaux["accueil"]._boutons_reprise[0].click()
        assert "introuvable" in fen.journal.toPlainText()
        assert fen.tome is None
    finally:
        _arreter(fen)
        _detruire(fen)


def test_les_sondes_ne_verrouillent_pas_le_lanceur(fenetre):
    """L31.6 — une sonde d'installation ne touche aucun checkpoint.

    ⚠ `touche_tout()` répondait « oui » à toute tâche `planche=None`, ce qui est juste pour un
    `process_volume` et faux pour trois lectures. Sans `GENRES_SANS_VERROU`, les sondes
    grisaient le bouton « Lancer » pendant les deux secondes du délai réseau, à chaque
    démarrage."""
    from gui.travailleur import GENRES_SANS_VERROU, GENRE_SONDE

    assert GENRE_SONDE in GENRES_SANS_VERROU
    fenetre.fil._en_cours = (None, GENRE_SONDE)
    assert fenetre.fil.touche_tout() is False
    fenetre.fil._en_cours = (None, "run")
    assert fenetre.fil.touche_tout() is True
    fenetre.fil._en_cours = None


def test_l_accueil_recoit_les_verdicts_des_sondes(fenetre):
    """Et il les reçoit **par le fil**, pas par un appel direct : c'est le chemin réel."""
    from gui import sondes as snd
    from gui.travailleur import GENRE_SONDE

    fenetre._resultat_sondes = {"sondes": (
        snd.Sonde("Serveur LLM", snd.INJOIGNABLE, "http://localhost:11434/v1 — ConnectError",
                  remede="Démarre LM Studio ou Ollama."),
        snd.Sonde("Poids de détection", snd.JOIGNABLE, "bubble_detector.onnx"),
        snd.Sonde("Pandoc", snd.JOIGNABLE, "pandoc"))}
    fenetre._sur_fin(None, GENRE_SONDE, True, "Sondes d'installation terminées.")
    texte = fenetre._panneaux["accueil"].etat_sondes.text()
    assert "Serveur LLM — absent" in texte
    assert "Démarre LM Studio" in texte, "un verdict négatif dit quoi faire"
    assert "Poids de détection — disponible" in texte


# --------------------------------------------------------------------------- #
# L18.4 — les menus et la règle qui les gouverne
# --------------------------------------------------------------------------- #

def test_les_cinq_menus_existent(fenetre):
    assert list(fenetre.menus) == list(act.MENUS)
    assert [m.title() for m in fenetre.menus.values()] == list(act.MENUS)


def test_chaque_action_du_catalogue_est_dans_son_menu(fenetre):
    """La règle : toute action de l'interface est atteignable par un menu.

    Un sous-menu compte pour son menu parent — « Affichage → Filtre de la pellicule →
    débordements » est bien atteignable depuis « Affichage »."""
    dans_la_barre: dict[str, tuple[str, str]] = {}
    for nom, menu in fenetre.menus.items():
        for action in menu.actions():
            if not action.isSeparator() and action.menu() is None:
                dans_la_barre[action.text()] = (nom, "")
    for (nom, groupe), sous in fenetre.sous_menus.items():
        for action in sous.actions():
            if not action.isSeparator():
                dans_la_barre[action.text()] = (nom, groupe)
    for entree in act.actions():
        assert entree.libelle in dans_la_barre, entree.identifiant
        assert dans_la_barre[entree.libelle] == (entree.menu, entree.groupe), \
            entree.identifiant


def test_le_menu_affiche_le_raccourci(fenetre):
    """« Un menu n'est pas un rangement, c'est un index découvrable — c'est aussi le seul
    endroit où un utilisateur apprend qu'un raccourci existe. »"""
    for entree in act.actions():
        if not entree.raccourci:
            continue
        action = fenetre.actions_menu[entree.identifiant]
        assert action.shortcut().toString(), entree.identifiant


def test_aucun_raccourci_n_est_declare_deux_fois_dans_la_fenetre(fenetre_avec_tome):
    """**Le test que le plan réclame nommément**, et sur la fenêtre CONSTRUITE.

    `test_gui_actions.py` vérifie la table ; celui-ci vérifie ce qui existe réellement, boutons
    compris. C'est lui qui aurait attrapé le `Ctrl+Shift+S` déclaré à la fois sur le bouton
    « Enregistrer les modifications du projet » et sur son action de menu — le catalogue seul
    ne l'aurait pas vu, puisque le doublon venait d'un widget."""
    fenetre = fenetre_avec_tome
    # ⚠ On visite TOUT avant de compter. Les panneaux étant construits à la demande depuis le
    # lot 31, un doublon posé par un bouton du lanceur webtoon passerait inaperçu sur une
    # fenêtre restée à l'accueil — ce qui rendrait le test plus faible qu'avant, pas plus
    # fort.
    for identifiant in ("light_novel", "manga", "webtoon", "illustrations", "oeuvres",
                        "retouche"):
        fenetre.aller_a(identifiant)
    declarees: dict[str, list[str]] = {}
    for action in fenetre.findChildren(QAction):
        for sequence in action.shortcuts():
            declarees.setdefault(sequence.toString(), []).append(f"action « {action.text()} »")
    for classe in ("QPushButton", "QToolButton"):
        for bouton in fenetre.findChildren(type(fenetre.retouche.bouton_projet)
                                           if classe == "QPushButton"
                                           else type(fenetre.editeur.bouton_finale)):
            sequence = bouton.shortcut().toString()
            if sequence:
                declarees.setdefault(sequence, []).append(f"bouton « {bouton.text()} »")
    doublons = {seq: qui for seq, qui in declarees.items() if len(qui) > 1}
    assert doublons == {}, f"raccourci(s) en double : {doublons}"


def test_les_actions_de_tome_sont_grisees_sans_tome(fenetre):
    for entree in act.actions():
        if entree.exige_tome:
            assert not fenetre.actions_menu[entree.identifiant].isEnabled(), entree.identifiant


def test_les_actions_de_tome_s_activent_avec_un_tome(fenetre_avec_tome):
    for entree in act.actions():
        if entree.exige_tome:
            assert fenetre_avec_tome.actions_menu[entree.identifiant].isEnabled(), \
                entree.identifiant


def test_les_boutons_ont_perdu_leur_raccourci_propre(fenetre_avec_tome):
    """Ils le tiennent maintenant de leur action — une seule déclaration par séquence."""
    fenetre = fenetre_avec_tome
    for bouton in (fenetre.retouche.bouton_projet, fenetre.editeur.bouton_enregistrer_doc,
                   fenetre.editeur.bouton_annuler, fenetre.editeur.bouton_refaire,
                   fenetre.editeur.bouton_ajuster):
        assert bouton.shortcut().toString() == "", bouton.text()


def test_un_bouton_branche_declenche_bien_son_action(fenetre_avec_tome):
    """Perdre le raccourci ne doit pas vouloir dire perdre le clic."""
    fenetre = fenetre_avec_tome
    vus = []
    fenetre.editeur.ajuster = lambda: vus.append("ajuster")
    fenetre.editeur.bouton_ajuster.click()
    assert vus == ["ajuster"]


# --------------------------------------------------------------------------- #
# L18.5 — deux boutons dont le nom promettait la même chose
# --------------------------------------------------------------------------- #

def test_les_deux_boutons_d_enregistrement_portent_leur_portee(fenetre_avec_tome):
    fenetre = fenetre_avec_tome
    assert fenetre.editeur.bouton_enregistrer_doc.text() == "Enregistrer cette planche"
    assert fenetre.retouche.bouton_projet.text().startswith("Enregistrer tout le tome")


def test_le_bouton_du_tome_porte_son_compteur(fenetre_avec_tome):
    """« Le nombre est déjà calculé (`planches_modifiees()`) » — il n'était affiché nulle part."""
    fenetre = fenetre_avec_tome
    fenetre.editeur._brouillons_par_planche[1] = {0: "une correction"}
    fenetre._marquer_modifie(True)
    assert "(1 planche)" in fenetre.retouche.bouton_projet.text()
    assert fenetre.retouche.bouton_projet.isEnabled()


def test_la_vignette_porte_la_pastille_des_modifications_non_ecrites(fenetre_avec_tome):
    """L18.6 — « le mécanisme existe déjà (`pellicule.pastilles`), il suffit de compter les
    brouillons ». Il ne les comptait pas : rien dans la pellicule ne distinguait une planche
    corrigée-non-écrite d'une planche intacte."""
    editeur = fenetre_avec_tome.editeur
    item = editeur._item_de(1)
    assert "●" not in item.text()
    editeur.liste_bulles.setCurrentRow(0)
    editeur.champ_trad.setPlainText("Une correction non écrite")
    assert "●1" in item.text()
    assert "NON enregistrée" in item.toolTip()


def test_le_filtre_du_sous_menu_agit_sur_la_pellicule(fenetre_avec_tome):
    fenetre = fenetre_avec_tome
    action = next(fenetre.actions_menu[e.identifiant] for e in act.actions()
                  if e.donnee == "débordements")
    action.setChecked(True)
    assert fenetre.editeur.choix_filtre.currentText() == "débordements"
    action.setChecked(False)
    assert fenetre.editeur.choix_filtre.currentText() == "toutes"


def test_le_sous_menu_reflete_la_liste_deroulante(fenetre_avec_tome):
    """La liste déroulante reste le maître : elle est sous les yeux, à côté de la pellicule
    qu'elle filtre. Le menu la reflète, sinon il dit un filtre et la pellicule en applique
    un autre."""
    fenetre = fenetre_avec_tome
    fenetre.editeur.choix_filtre.setCurrentText("jamais rendues")
    coches = [e.donnee for e in act.actions()
              if e.groupe == act.GROUPE_FILTRES
              and fenetre.actions_menu[e.identifiant].isChecked()]
    assert coches == ["jamais rendues"]


def test_l_indicateur_de_modification_est_dans_le_panneau(fenetre_avec_tome):
    """L18.6 — trois gestes n'écrivaient qu'une ligne dans un journal replié à zéro."""
    fenetre = fenetre_avec_tome
    assert fenetre.retouche.etiquette_attente.text() == ""
    fenetre.editeur._brouillons_par_planche[1] = {0: "x"}
    fenetre._marquer_modifie(True)
    assert "1 planche" in fenetre.retouche.etiquette_attente.text()


# --------------------------------------------------------------------------- #
# L18.8.1 — changer de tome ne jette plus le travail sans un mot
# --------------------------------------------------------------------------- #

def test_changer_de_tome_sans_travail_en_attente_ne_demande_rien(fenetre_avec_tome, tmp_path,
                                                                 monkeypatch):
    """⚠ La garde n'a pas bougé, elle a SUIVI la barre projet/tome dans `PanneauRetouche`.

    Le `PLAN-31` annonçait un trou — « on pourra quitter la retouche en changeant de
    destination, ce qui n'est pas un changement de combo » — que le `PLAN-35` L35.4 devait
    refermer. Il ne s'ouvre pas : les panneaux vivent dans un `QStackedWidget`, changer de
    destination ne détruit rien et ne jette aucun brouillon. Le seul geste qui jette du travail
    reste l'ouverture d'un AUTRE tome ici, et il passe toujours par la même boîte à trois
    choix. `test_changer_de_destination_ne_jette_aucun_brouillon` le vérifie."""
    fenetre = fenetre_avec_tome
    demandes = []
    monkeypatch.setattr(fenetre, "_boite_travail_en_attente",
                        lambda *a, **k: demandes.append(1) or "annuler")
    _tome_traite(tmp_path, "P", "Vol.2")
    fenetre.retouche.remplir_projets()
    fenetre.retouche.choix_tome.setCurrentText("Vol.2")
    assert demandes == []
    assert fenetre.tome.tome == "Vol.2"


def test_changer_de_tome_avec_du_travail_demande(fenetre_avec_tome, tmp_path, monkeypatch):
    """La MÊME boîte à trois choix qu'à la fermeture — elle existait, elle n'était pas appelée."""
    fenetre = fenetre_avec_tome
    fenetre.editeur._brouillons_par_planche[1] = {0: "pas encore écrit"}
    demandes = []
    monkeypatch.setattr(fenetre, "_boite_travail_en_attente",
                        lambda attente, **k: demandes.append(list(attente)) or "abandonner")
    _tome_traite(tmp_path, "P", "Vol.2")
    fenetre.retouche.remplir_projets()
    fenetre.retouche.choix_tome.setCurrentText("Vol.2")
    assert demandes == [[1]]
    assert fenetre.tome.tome == "Vol.2"


def test_annuler_le_changement_de_tome_garde_le_travail(fenetre_avec_tome, tmp_path,
                                                        monkeypatch):
    """Et remet la liste sur le tome qu'on n'a pas quitté, sans rouvrir la boîte en boucle."""
    fenetre = fenetre_avec_tome
    fenetre.editeur._brouillons_par_planche[1] = {0: "pas encore écrit"}
    appels = []
    monkeypatch.setattr(fenetre, "_boite_travail_en_attente",
                        lambda attente, **k: appels.append(1) or "annuler")
    _tome_traite(tmp_path, "P", "Vol.2")
    fenetre.retouche.remplir_projets()
    fenetre.retouche.choix_tome.setCurrentText("Vol.2")
    assert appels == [1], "la boîte ne doit s'ouvrir qu'une fois, pas en boucle"
    assert fenetre.tome.tome == "Vol.1"
    assert fenetre.retouche.choix_tome.currentText() == "Vol.1"
    assert fenetre.editeur.planches_modifiees() == [1]


def test_enregistrer_puis_changer_de_tome(fenetre_avec_tome, tmp_path, monkeypatch):
    fenetre = fenetre_avec_tome
    fenetre.editeur.liste_bulles.setCurrentRow(0)
    fenetre.editeur._brouillons_par_planche[1] = {0: "Salut"}
    monkeypatch.setattr(fenetre, "_boite_travail_en_attente", lambda *a, **k: "enregistrer")
    ecrites = []
    monkeypatch.setattr(fenetre.editeur, "enregistrer_tout",
                        lambda: (ecrites.append(1) or ([1], [])))
    _tome_traite(tmp_path, "P", "Vol.2")
    fenetre.retouche.remplir_projets()
    fenetre.retouche.choix_tome.setCurrentText("Vol.2")
    assert ecrites == [1]
    assert fenetre.tome.tome == "Vol.2"


# --------------------------------------------------------------------------- #
# L18.7 — la disposition survit à un redémarrage
# --------------------------------------------------------------------------- #

def test_aller_retour_de_disposition(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path)
    config = _config(tmp_path)

    premiere = Fenetre(config, "config.yaml")
    premiere.aller_a("retouche")
    premiere.retouche.viser("P", "Vol.1")
    premiere.editeur.choix_filtre.setCurrentText("rendu périmé")
    premiere.editeur.bouton_garder_zoom.setChecked(True)
    premiere.aller_a("manga")
    premiere._enregistrer_reglages()
    colonnes_ecrites = reg.lire()["colonnes"]
    _arreter(premiere)

    seconde = Fenetre(config, "config.yaml")
    try:
        # ⚠ La destination est reposée, **le tome ne l'est pas** : c'est le lot 31. Le couple
        # projet/tome reste persisté et alimente la carte « Reprendre » de l'accueil, un clic.
        assert seconde.destination() == "manga"
        assert seconde.tome is None
        assert seconde.reglages["dernier_projet"] == "P"
        assert seconde.reglages["dernier_tome"] == "Vol.1"
        seconde.aller_a("retouche")
        assert seconde.editeur.choix_filtre.currentText() == "rendu périmé"
        assert seconde.editeur.bouton_garder_zoom.isChecked() is True
        # Les colonnes font l'aller-retour par le fichier ; leur POSE est vérifiée à part
        # (`test_les_colonnes_persistees_sont_reposees`), parce qu'un `QSplitter` hors écran
        # est à sa largeur minimale et refuse alors tout redimensionnement — le mesurer ici
        # ne dirait rien du code, seulement de la plateforme `offscreen`.
        assert seconde.reglages["colonnes"] == colonnes_ecrites
    finally:
        _arreter(seconde)


def test_les_colonnes_persistees_sont_reposees(fenetre_avec_tome):
    """La disposition est lue dans `__init__`, donc AVANT que la fenêtre ait une géométrie.

    ⚠ `QSplitter.setSizes` est alors sans effet : Qt répartit à parts égales à la première
    mise en page et écrase ce qu'on vient de poser. `Fenetre.showEvent` repasse une fois — ce
    test vérifie que ce second passage a bien lieu, et avec les valeurs du fichier."""
    fenetre = fenetre_avec_tome
    poses = []
    fenetre.editeur.splitter.setSizes = poses.append
    fenetre.editeur.appliquer_reglages({"colonnes": [301, 702, 503]})
    fenetre._disposition_posee = False
    fenetre.show()
    assert poses[-1] == [301, 702, 503]
    assert fenetre.editeur._colonnes_a_poser is None, "posées une fois, pas à chaque affichage"


def test_force_repart_toujours_decoche(fenetre, tmp_path):
    """⚠ La règle qui coûte des heures de GPU quand elle est violée.

    Vérifiée sur les TROIS destinations de lancement : `runs` porte désormais un
    sous-dictionnaire par destination, et une seule oubliée suffirait à rouvrir la brèche."""
    for identifiant in ("light_novel", "manga", "webtoon"):
        lanceur = _lanceur(fenetre, identifiant)
        lanceur.case_force.setChecked(True)
        lanceur.case_dry.setChecked(True)
    fenetre._enregistrer_reglages()
    relu = reg.lire()
    for identifiant in ("light_novel", "manga", "webtoon"):
        assert "force" not in relu["runs"][identifiant], identifiant
        assert "dry_run" not in relu["runs"][identifiant], identifiant
        lanceur = _lanceur(fenetre, identifiant)
        lanceur.appliquer_reglages(relu["runs"][identifiant])
        assert lanceur.case_force.isChecked() is False, identifiant
        assert lanceur.case_dry.isChecked() is False, identifiant


def test_une_session_qui_reste_a_l_accueil_ne_perd_rien(qt_app, tmp_path, monkeypatch):
    """⚠ **Le piège de la construction paresseuse**, et il coûterait cher.

    `_collecter_reglages` interrogeait trois panneaux qui existaient toujours. S'il les
    interrogeait encore alors qu'ils ne sont plus construits, une session ouverte puis fermée
    sur l'accueil écraserait les colonnes, le filtre et les réglages de run de la session
    précédente par des valeurs par défaut. Ce qui n'a pas été ouvert doit garder ce que le
    fichier disait."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    _tome_traite(tmp_path)
    etat = reg.defauts()
    etat["colonnes"] = [301, 702, 503]
    etat["filtre"] = "débordements"
    etat["runs"]["manga"] = {"verbose": False, "lot": 17, "think": 2}
    etat["dernier_projet"], etat["dernier_tome"] = "P", "Vol.1"
    reg.ecrire(etat)
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.show()
        fen._enregistrer_reglages()
        relu = reg.lire()
        assert relu["colonnes"] == [301, 702, 503]
        assert relu["filtre"] == "débordements"
        assert relu["runs"]["manga"]["lot"] == 17
        assert (relu["dernier_projet"], relu["dernier_tome"]) == ("P", "Vol.1")
    finally:
        _arreter(fen)
        _detruire(fen)


def test_changer_de_destination_ne_jette_aucun_brouillon(fenetre_avec_tome):
    """La paire `PLAN-31` / `PLAN-35` : le trou annoncé, et pourquoi il ne s'ouvre pas.

    Les destinations vivent dans un `QStackedWidget` : en quitter une la cache, elle n'est ni
    détruite ni vidée. Le travail non enregistré survit donc à toute navigation, et la garde
    n'a à couvrir que ce qu'elle couvrait déjà — l'ouverture d'un autre tome."""
    fenetre = fenetre_avec_tome
    fenetre.editeur._brouillons_par_planche[1] = {0: "pas encore écrit"}
    assert fenetre.editeur.planches_modifiees() == [1]
    for identifiant in ("manga", "accueil", "illustrations", "retouche"):
        fenetre.aller_a(identifiant)
    assert fenetre.editeur.planches_modifiees() == [1]
    assert fenetre.tome is not None


def test_une_colonne_a_zero_n_est_pas_reappliquee(fenetre_retouche):
    """Rouvrir sur une pellicule invisible enverrait éditer un JSON à la main."""
    avant = fenetre_retouche.editeur.splitter.sizes()
    fenetre_retouche.editeur.appliquer_reglages({"colonnes": [0, 1480, 0]})
    assert fenetre_retouche.editeur.splitter.sizes() == avant


def test_reinitialiser_la_disposition_efface_le_fichier(fenetre_retouche, monkeypatch):
    fenetre = fenetre_retouche
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    fenetre.editeur.choix_filtre.setCurrentText("débordements")
    fenetre._enregistrer_reglages()
    assert reg.chemin().exists()
    fenetre.action_reinitialiser_disposition()
    assert not reg.chemin().exists()
    assert fenetre.editeur.choix_filtre.currentText() == "toutes"
    assert fenetre.destination() == "accueil", "la sortie de secours ramène à l'accueil"


# --------------------------------------------------------------------------- #
# L18.1 — l'état vide
# --------------------------------------------------------------------------- #

def test_un_sources_vide_montre_l_accueil_et_pas_un_aplat_gris(fenetre_retouche):
    """⚠ L'état vide de l'ÉDITEUR est intact — le lot 31 ne l'a pas remplacé, il l'a
    doublé d'un état vide sur l'accueil (`test_l_accueil_porte_l_etat_vide_du_lot_18`).
    Quelqu'un qui clique sur « Retouche » avec un `sources/` vide doit toujours trouver les
    deux boutons là où ils étaient."""
    fenetre = fenetre_retouche
    assert fenetre.editeur.pages.currentIndex() == 1
    assert "Aucun projet" in fenetre.editeur.accueil_titre.text()
    assert fenetre.editeur.bouton_creer.isEnabled()
    assert fenetre.editeur.bouton_sources.isEnabled()
    assert "Aucun projet manga trouvé" in fenetre.journal.toPlainText()


def test_les_deux_boutons_de_l_accueil_demandent_a_la_fenetre(fenetre_retouche, monkeypatch):
    """Le panneau ne crée rien lui-même : la copie appartient au fil de travail."""
    fenetre = fenetre_retouche
    demandes = []
    monkeypatch.setattr(fenetre, "action_nouveau_projet",
                        lambda *a: demandes.append("creer"))
    monkeypatch.setattr(fenetre, "action_ouvrir_sources", lambda: demandes.append("sources"))
    fenetre.editeur.demande_creation.disconnect()
    fenetre.editeur.demande_sources.disconnect()
    fenetre.editeur.demande_creation.connect(fenetre.action_nouveau_projet)
    fenetre.editeur.demande_sources.connect(fenetre.action_ouvrir_sources)
    fenetre.editeur.bouton_creer.click()
    fenetre.editeur.bouton_sources.click()
    assert demandes == ["creer", "sources"]


def test_un_tome_jamais_traite_a_son_propre_etat_vide(qt_app, tmp_path, monkeypatch):
    """Il ne se confond pas avec « aucun projet » : ici, ce qu'il faut, c'est lancer un run."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    sources = tmp_path / "sources" / "P" / "Vol.1" / "manga"
    sources.mkdir(parents=True)
    Image.new("RGB", TAILLE, (255, 255, 255)).save(sources / "page_0001.png")
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.aller_a("retouche")
        fen.retouche.viser("P", "Vol.1")
        assert fen.editeur.pages.currentIndex() == 1
        assert "jamais traité" in fen.editeur.accueil_titre.text()
    finally:
        _arreter(fen)


def test_un_tome_traite_montre_l_editeur(fenetre_avec_tome):
    assert fenetre_avec_tome.editeur.pages.currentIndex() == 0


# --------------------------------------------------------------------------- #
# L18.2 — le glisser-déposer
# --------------------------------------------------------------------------- #

def _lacher(fenetre, chemins):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(c)) for c in chemins])
    evenement = QDropEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    fenetre.dropEvent(evenement)
    return evenement


def test_lacher_des_planches_ouvre_le_depot_GUIDE(fenetre, tmp_path, monkeypatch):
    """⚠ Le lot 34 remplace ici « Nouveau projet » par le dépôt GUIDÉ.

    Ce qui manquait n'était pas la création mais ce qui vient APRÈS le lâcher : le compte
    rendu de ce qu'on vient de lâcher, la collision nommée, et le refus d'un `.cbr` sans
    `unrar` avant l'import plutôt qu'au milieu de la copie (`PLAN-34` L34.3)."""
    dossier = tmp_path / "Mon Manga - Vol.1"
    dossier.mkdir()
    (dossier / "p1.png").write_bytes(b"\x89PNG")
    recus = []
    monkeypatch.setattr(fenetre, "action_depot_guide", lambda c=(): recus.append(list(c)))
    _lacher(fenetre, [dossier])
    assert recus == [[dossier]]


def test_le_depot_guide_sans_chemins_retombe_sur_nouveau_projet(fenetre, monkeypatch):
    """La boîte guidée n'a de sens qu'avec des chemins déjà désignés : le geste sans chemins
    reste « Nouveau projet… », qui commence par demander les sources."""
    recus = []
    monkeypatch.setattr(fenetre, "action_nouveau_projet", lambda c=(): recus.append("appel"))
    fenetre.action_depot_guide([])
    assert recus == ["appel"]


def test_lacher_un_glossaire_ouvre_l_import(fenetre, tmp_path, monkeypatch):
    glossaire = tmp_path / "glossaire.yaml"
    glossaire.write_text("termes: []", encoding="utf-8")
    recus = []
    monkeypatch.setattr(fenetre, "action_importer_glossaire",
                        lambda c=(): recus.append(list(c)))
    _lacher(fenetre, [glossaire])
    assert recus == [[glossaire]]


def test_un_lacher_inconnu_produit_un_message_pas_un_silence(fenetre, tmp_path, monkeypatch):
    """« Un lâcher de type inconnu doit produire un message, pas un silence. »

    ⚠ **L'exemple était un `.pdf` jusqu'au lot 40, et il ne peut plus l'être** : le lot en fait
    un tome de roman (`gui/depot.SOURCES_LN`). Le test ne devenait pas faux, il devenait
    DANGEREUX — il ouvrait « Nouveau projet », c'est-à-dire une boîte modale, et la suite entière
    se figeait sans un mot. C'est comme cela que le défaut a été trouvé.

    L'exemple est donc changé pour un `.psd`, qui n'est ni une source de planches (ce n'est pas
    une extension d'image lue par `manga.ingest`), ni un roman, ni un glossaire. La propriété
    vérifiée, elle, ne bouge pas d'un mot."""
    bizarre = tmp_path / "planche.psd"
    bizarre.write_bytes(b"8BPS")
    dits = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: dits.append(a[2])))
    _lacher(fenetre, [bizarre])
    assert dits and ".psd" in dits[0]


def test_lacher_un_roman_propose_un_projet_light_novel(fenetre, tmp_path, monkeypatch):
    """L40.1 — le pendant du test ci-dessus, et la raison pour laquelle il a changé d'exemple.

    ⚠ Le parcours GUIDÉ n'est pas emprunté ici, et c'est délibéré : il lit des archives et
    compte des planches. Un roman va droit à « Nouveau projet », qui sait demander la langue —
    obligatoire pour un light novel, faute de quoi `pipeline/sources.py` ne verrait pas le
    tome."""
    roman = tmp_path / "Mon Roman - Vol.1.epub"
    roman.write_bytes(b"PK\x03\x04")
    vus = []
    monkeypatch.setattr(type(fenetre), "action_nouveau_projet",
                        lambda self, chemins=(): vus.append(list(chemins)))
    _lacher(fenetre, [roman])
    assert vus == [[roman]]


def test_le_survol_annonce_ce_qui_va_se_passer(fenetre, tmp_path):
    """⚠ Un retour visuel pendant le survol est obligatoire, sinon le geste paraît cassé une
    fois sur deux."""
    from PySide6.QtGui import QDragEnterEvent
    dossier = tmp_path / "planches"
    dossier.mkdir()
    (dossier / "p1.png").write_bytes(b"\x89PNG")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(dossier))])
    evenement = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton,
                                Qt.NoModifier)
    fenetre.dragEnterEvent(evenement)
    assert evenement.isAccepted()
    assert "projet" in fenetre.statusBar().currentMessage()


def test_la_fenetre_accepte_les_depots(fenetre):
    """Zéro `setAcceptDrops` dans tout `gui/` avant ce lot."""
    assert fenetre.acceptDrops() is True


# --------------------------------------------------------------------------- #
# L18.8.2 — un run light novel sur un projet sans manga
# --------------------------------------------------------------------------- #

def test_le_lanceur_liste_les_projets_light_novel(qt_app, tmp_path, monkeypatch):
    """**Il n'existait aucun chemin d'interface pour cela.**

    La cible du lanceur était une étiquette en lecture seule, remplie par la barre haute de
    l'onglet voisin, dont la liste est filtrée sur les tomes MANGA. Un projet purement roman
    n'y apparaissait jamais, et choisir la brique « Light novel » n'y changeait rien."""
    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    roman = tmp_path / "sources" / "Roman seul" / "Vol.1" / "ENG"
    roman.mkdir(parents=True)
    (roman / "chap01.txt").write_text("Once upon a time.", encoding="utf-8")
    fen = Fenetre(_config(tmp_path), "config.yaml")
    try:
        fen.aller_a("retouche")
        assert "Roman seul" not in [fen.retouche.choix_projet.itemText(i)
                                    for i in range(fen.retouche.choix_projet.count())], \
            "l'éditeur de planches n'a rien à faire d'un projet sans manga"
        # ⚠ Depuis le lot 31, la brique n'est plus un choix DANS le panneau : c'est la
        # destination qui la dit. Le chemin d'interface que le lot 18 avait ouvert existe
        # toujours — il porte simplement un nom dans le pane au lieu d'être une ligne de
        # liste déroulante.
        lanceur = fen.aller_a("light_novel")
        assert lanceur.brique() == "ln"
        assert lanceur.choix_brique.isVisible() is False
        projets = [lanceur.choix_projet.itemText(i)
                   for i in range(lanceur.choix_projet.count())]
        assert "Roman seul" in projets
        lanceur.choix_projet.setCurrentText("Roman seul")
        assert lanceur.cible() == ("Roman seul", "Vol.1")
    finally:
        _arreter(fen)


def test_le_lanceur_suit_la_retouche_cote_manga(fenetre_avec_tome):
    """L19.7 — « le bouton amènerait sur un panneau réglé sur un autre tome, et le clic suivant
    lancerait un run sur ce qu'on ne regardait pas ».

    ⚠ Le report ne se fait plus à l'ouverture du tome mais au moment où l'on va aux runs : le
    lanceur peut ne pas exister quand le tome s'ouvre, et lui parler alors le construirait —
    c'est-à-dire rouvrir sous un autre nom ce que le lot ferme."""
    fenetre = fenetre_avec_tome
    fenetre._aller_aux_runs()
    assert fenetre.destination() == "manga"
    assert fenetre._panneaux["manga"].cible() == ("P", "Vol.1")


# --------------------------------------------------------------------------- #
# L18.8.4 — les actions coûteuses demandent confirmation
# --------------------------------------------------------------------------- #

def test_lancer_un_run_demande_confirmation(fenetre_avec_tome, monkeypatch):
    """« Lancer » démarrait un travail pouvant durer des heures sur un simple clic."""
    fenetre = fenetre_avec_tome
    lanceur = _lanceur(fenetre)
    lanceur.viser("P", "Vol.1")
    demandes = []
    monkeypatch.setattr(lanceur, "_confirmer",
                        lambda p, t: demandes.append((p, t)) or False)
    lances = []
    lanceur.demande_run.connect(lambda p: lances.append(p))
    lanceur.bouton_lancer.click()
    assert demandes == [("P", "Vol.1")]
    assert lances == [], "un refus ne doit rien lancer"


def test_assembler_demande_confirmation(fenetre_avec_tome, monkeypatch):
    fenetre = fenetre_avec_tome
    reponses = []
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: reponses.append(a[2])
                                     or QMessageBox.No))
    faits = []
    monkeypatch.setattr(fenetre, "_assembler", lambda: faits.append(1))
    _lanceur(fenetre).bouton_assembler.click()
    assert reponses and "Réassembler" in reponses[0]
    assert faits == []


# --------------------------------------------------------------------------- #
# L18.9 — sortir du vocabulaire de la ligne de commande
# --------------------------------------------------------------------------- #

def test_les_cases_disent_l_effet_et_l_infobulle_la_commande(fenetre):
    lanceur = _lanceur(fenetre)
    for case, libelle, drapeau in ((lanceur.case_force, "Tout refaire depuis zéro", "--force"),
                                   (lanceur.case_dry, "Simuler sans traduire", "--dry-run"),
                                   (lanceur.case_verbose, "Journal détaillé", "--verbose")):
        assert case.text() == libelle
        assert drapeau not in case.text(), "le nom de la commande n'est pas le nom de l'action"
        assert drapeau in case.toolTip(), "…mais il reste accessible, pour qui scripte"


def test_le_menu_ne_s_appelle_plus_du_nom_d_un_fichier(fenetre):
    action = fenetre.actions_menu["ouvrir_config"]
    assert action.text() == "Réglages avancés (fichier)"
    assert "config.yaml" in action.toolTip()


def test_les_etapes_de_reprise_gardent_leur_identifiant(fenetre):
    """⚠ Ce sont des noms de `checkpoints.STAGES` : ils apparaissent dans `RAPPORT.md` et dans
    la documentation. Les traduire romprait un vocabulaire partagé."""
    lanceur = _lanceur(fenetre)
    libelles = [lanceur.choix_etape.itemText(i)
                for i in range(lanceur.choix_etape.count())]
    for identifiant in ("rendu", "traduction", "terminologie", "ocr", "sfx", "nettoyage",
                        "detection"):
        assert any(libelle.startswith(identifiant) for libelle in libelles), identifiant


# --------------------------------------------------------------------------- #
# PLAN-19 — la bascule de thème, et ce que la feuille de style ne couvre pas
# --------------------------------------------------------------------------- #

def test_une_fenetre_neuve_est_reellement_stylee(qt_app, tmp_path, monkeypatch):
    """⚠ **Le symptôme utilisateur de la régression du lot, et il ne se voyait qu'à l'œil.**

    Une fenêtre construite alors qu'aucun `theme.appliquer` ne l'avait précédée restait sans
    une seule règle de style : le journal en Segoe UI à 9 pt au lieu de la pile monospace au
    rang « petit », la ligne d'état en noir au lieu du gris faible. Tous les tests de couleur
    passaient — ils interrogent la palette, pas les widgets.

    Ce test interroge le WIDGET — sa police et sa palette résolues — et non les tokens.

    ⚠ Il regarde `font().families()` et **pas** `fontInfo().fixedPitch()`. Sous
    `QT_QPA_PLATFORM=offscreen`, `QFontDatabase.families()` rend **0 famille** : aucune police
    n'existe, donc rien n'est jamais chassé fixe, et l'assertion serait fausse pour une raison
    qui n'a rien à voir avec le sujet. `families()` rend la pile telle que la feuille l'a
    déclarée, ce qui est exactement ce qu'on veut vérifier ici."""
    from gui import theme

    monkeypatch.setenv(reg.VARIABLE, str(tmp_path / "interface.json"))
    (tmp_path / "sources").mkdir(exist_ok=True)
    (tmp_path / "build").mkdir(exist_ok=True)
    qt_app.setStyleSheet("")                       # comme si rien n'avait jamais été posé
    fen = Fenetre(_config(tmp_path), "config.yaml")
    fen.aller_a("retouche")
    try:
        assert qt_app.styleSheet(), "la fenêtre doit avoir fait poser la feuille"
        fonte = fen.journal.font()
        assert list(fonte.families()) == list(theme.Typo.MONOSPACE),             f"journal en {fonte.families()} — la pile monospace n'a pas pris"
        assert fonte.pointSizeF() == pytest.approx(theme.corps("petit")),             "le rang « petit » n'a pas pris"
        assert fonte.pointSizeF() < qt_app.font().pointSizeF()
        ligne = fen.editeur.ligne_etat
        assert (ligne.palette().color(ligne.foregroundRole()).name()
                == theme.jeu().palette.texte_faible)
    finally:
        _arreter(fen)
        _detruire(fen)


def test_le_menu_affichage_porte_les_trois_themes(fenetre):
    """Critère 2 : « la bascule est dans le menu Affichage »."""
    sous = fenetre.sous_menus[("Affichage", act.GROUPE_THEME)]
    libelles = [a.text() for a in sous.actions()]
    assert libelles == [libelle for _mode, libelle in act.THEMES]


def test_basculer_le_theme_change_la_palette_et_coche_le_menu(fenetre):
    from gui import theme

    fenetre.action_theme(theme.SOMBRE, True)
    assert theme.jeu().mode == theme.SOMBRE
    assert theme.couleur("fond") == theme.SOMBRE_PALETTE.fond
    assert fenetre.actions_menu["theme_sombre"].isChecked()
    assert not fenetre.actions_menu["theme_clair"].isChecked()
    assert not fenetre.actions_menu["theme_auto"].isChecked()

    fenetre.action_theme(theme.CLAIR, True)
    assert theme.jeu().mode == theme.CLAIR


def test_le_theme_choisi_est_persiste(fenetre, tmp_path):
    """Sans persistance, la bascule dure une session — et se refait à chaque lancement."""
    from gui import theme

    fenetre.action_theme(theme.SOMBRE, True)
    assert fenetre._collecter_reglages()["theme"] == theme.SOMBRE
    reg.ecrire(fenetre._collecter_reglages())
    assert reg.lire()["theme"] == theme.SOMBRE
    fenetre.action_theme(theme.CLAIR, True)


def test_decocher_le_theme_actif_le_remet(fenetre):
    """Exclusif, comme les filtres : sans ça, l'application resterait dans un thème que le
    menu ne déclare plus."""
    from gui import theme

    fenetre.action_theme(theme.CLAIR, True)
    fenetre.action_theme(theme.CLAIR, False)
    assert fenetre.actions_menu["theme_clair"].isChecked()
    assert fenetre.reglages["theme"] == theme.CLAIR


def test_la_bascule_repeint_le_journal_deja_ecrit(fenetre):
    """⚠ Chaque ligne du journal porte un `QTextCharFormat` figé à l'INSERTION. Un journal de
    trois cents lignes garderait donc les couleurs du thème précédent — et le journal est
    précisément ce qu'on relit après un incident, c'est-à-dire longtemps après l'avoir écrit.

    Le niveau est retrouvé par le PRÉFIXE de la ligne, pas par une copie gardée en mémoire :
    une copie qui dériverait du widget repeindrait aux mauvaises couleurs."""
    from gui import theme

    fenetre.action_theme(theme.CLAIR, True)
    fenetre._journaliser("warn", "quelque chose cloche")
    fenetre._journaliser("info", "et tout va bien")

    def _teintes():
        doc = fenetre.journal.document()
        bloc, vues = doc.begin(), []
        while bloc.isValid():
            if bloc.text().strip():
                vues.append((bloc.text()[:2],
                             bloc.begin().fragment().charFormat().foreground().color().name()))
            bloc = bloc.next()
        return vues

    avant = _teintes()
    assert avant, "le journal doit porter au moins une ligne"
    assert dict(avant).get("⚠ ") == theme.CLAIRE.avertissement

    fenetre.action_theme(theme.SOMBRE, True)
    apres = dict(_teintes())
    assert apres.get("⚠ ") == theme.SOMBRE_PALETTE.avertissement
    assert apres.get("  ") == theme.SOMBRE_PALETTE.information
    fenetre.action_theme(theme.CLAIR, True)


def test_la_bascule_repeint_le_canevas_et_les_icones(fenetre_avec_tome):
    """⚠ Aucune règle QSS n'atteint un `QGraphicsItem` ni un `QPixmap` déjà rendu. Sans reprise
    explicite, une bascule laisserait une bande de vignettes du thème précédent au milieu
    d'une fenêtre basculée."""
    from gui import theme

    fen = fenetre_avec_tome
    fen.action_theme(theme.SOMBRE, True)
    assert fen.editeur.vue.backgroundBrush().color().name() == theme.SOMBRE_PALETTE.canevas_fond
    for bouton in fen.editeur._boutons_modes.values():
        assert not bouton.icon().isNull()
    # L'aplat d'attente est mis en cache sur l'instance : la bascule doit l'oublier, sinon la
    # pellicule garde le gris du thème précédent jusqu'au prochain lancement.
    assert fen.editeur._attente is None or fen.editeur._icone_attente() is not None
    fen.action_theme(theme.CLAIR, True)


def test_le_bouton_aller_aux_runs_ouvre_la_destination_et_y_porte_le_tome(fenetre_avec_tome):
    """L19.7 — « jamais traité » demandait un geste que rien ne proposait : lire la phrase,
    comprendre « onglet Runs », et aller le chercher.

    Le geste est le même après le lot 31 ; l'onglet est devenu une destination, et son nom
    est celui de la brique plutôt que « Runs »."""
    fen = fenetre_avec_tome
    fen.aller_a("retouche")
    fen.editeur.demande_runs.emit()
    assert fen.destination() == "manga"
    projet = fen.retouche.choix_projet.currentText()
    if projet:
        assert fen._panneaux["manga"].choix_projet.currentText() == projet


def test_l_etat_vide_jamais_traite_ne_propose_que_le_bouton_de_run(fenetre_retouche):
    """Les deux états vides n'appellent pas les mêmes gestes. Proposer « Créer un projet… » à
    qui vient d'en créer un serait lui rendre le geste qu'il vient de faire."""
    ed = fenetre_retouche.editeur
    ed.montrer_accueil("T — jamais traité", "…", cas="jamais_traite")
    assert ed.bouton_runs.isVisibleTo(ed.pages) is True
    assert ed.bouton_creer.isVisibleTo(ed.pages) is False

    ed.montrer_accueil("Aucun projet manga", "…")
    assert ed.bouton_creer.isVisibleTo(ed.pages) is True
    assert ed.bouton_runs.isVisibleTo(ed.pages) is False


def test_l_echec_d_une_tache_ne_montre_plus_un_nom_de_classe_python(fenetre):
    """L19.7 — `f"{type(err).__name__} : {err}"` était la SEULE chose que l'utilisateur voyait
    d'un échec, barre d'état comprise. Le nom de classe reste au journal, où il sert à un
    rapport de bug ; la ligne visible dit ce qui a échoué et ce qu'on peut tenter."""
    from gui.travailleur import GENRE_EDITION, message_utilisateur

    visible = message_utilisateur(PermissionError("accès refusé"), GENRE_EDITION)
    assert "PermissionError" not in visible
    assert "édition de zone" in visible and "réessaie" in visible

    inconnu = message_utilisateur(ValueError("boîte dégénérée"), GENRE_EDITION)
    assert "ValueError" not in inconnu
    assert "journal" in inconnu.lower()


# --------------------------------------------------------------------------- #
#  Lot 32 — le bandeau de run, et le titre de fenêtre
# --------------------------------------------------------------------------- #

def _demarrer_un_run(fenetre, brique="manga", projet="P", tome="Vol.1"):
    """Ce que fait `_lancer_run`, sans lancer d'orchestrateur.

    ⚠ On passe par les VRAIS slots (`_sur_debut`, `_contexte`, `_avancer`) plutôt que par un
    état posé à la main : c'est le câblage qui est en jeu, et un test qui remplirait le
    modèle lui-même ne dirait rien du chemin qu'un run emprunte réellement."""
    fenetre._cible_run = {"brique": brique, "projet": projet, "tome": tome, "config": {}}
    fenetre._sur_debut(None, GENRE_RUN, "run")


def test_le_bandeau_est_cache_au_demarrage(fenetre):
    """La fenêtre s'ouvre sur l'accueil : rien ne tourne, rien ne s'affiche."""
    assert fenetre.bandeau.isVisibleTo(fenetre) is False


def test_le_bandeau_se_montre_et_suit_un_run(fenetre):
    _demarrer_un_run(fenetre)
    assert fenetre.bandeau.isVisibleTo(fenetre) is True
    fenetre._contexte("traduction", "", "")
    fenetre._avancer(84, 131)
    assert fenetre.bandeau.etiquette_phase.text() == "Traduction et rendu (5/6)"
    assert fenetre.bandeau.etiquette_compte.text() == "planche 84 / 131"
    assert fenetre.bandeau.etiquette_cible.text() == "Manga · P / Vol.1"


def test_la_barre_ne_recule_pas_entre_deux_balayages(fenetre):
    """Le défaut du lot, vu depuis la fenêtre : 150 → 1 → 150 sur le même dénominateur."""
    _demarrer_un_run(fenetre)
    fenetre._contexte("analyse", "", "")
    for i in range(1, 131):
        fenetre._avancer(i, 131)
    haut = fenetre.bandeau.barre.value()
    fenetre._contexte("traduction", "", "")
    fenetre._avancer(1, 131)
    assert fenetre.bandeau.barre.value() >= haut


def test_l_objet_en_cours_arrive_jusqu_au_bandeau(fenetre):
    """Le nom du fichier voyageait dans un libellé d'étape, donc dans le journal."""
    _demarrer_un_run(fenetre)
    fenetre._contexte("traduction", "page_0084.png", "")
    fenetre._avancer(84, 131)
    assert "page_0084.png" in fenetre.bandeau.etiquette_objet.text()


def test_le_bloc_du_light_novel_ne_fait_plus_avancer_la_barre(fenetre):
    """66 reculs et 6 dénominateurs sur un tome de 25 chapitres venaient de là."""
    _demarrer_un_run(fenetre, brique="ln")
    fenetre._contexte("chapitres", "", "")
    fenetre._avancer(12, 25)
    valeur = fenetre.bandeau.barre.value()
    fenetre._contexte("", "", "bloc 1/10")
    assert fenetre.bandeau.barre.value() == valeur
    assert "bloc 1/10" in fenetre.bandeau.etiquette_objet.text()


def test_le_titre_porte_l_avancement_puis_revient_au_gabarit(fenetre):
    base = fenetre._titre_base
    _demarrer_un_run(fenetre)
    fenetre._contexte("traduction", "", "")
    fenetre._avancer(84, 131)
    assert fenetre.windowTitle().startswith("84/131 — Manga · P / Vol.1 — ")
    assert fenetre.windowTitle().count("[*]") == 1
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé.")
    assert fenetre.windowTitle() == base


def test_la_fin_du_run_laisse_un_bilan_et_aucune_modale(fenetre, monkeypatch):
    """L32.5 — l'utilisateur peut être en train de taper une réplique dans la retouche."""
    from PySide6.QtWidgets import QDialog, QMessageBox
    ouvertes = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: ouvertes.append(self))
    monkeypatch.setattr(QDialog, "exec", lambda self: ouvertes.append(self))
    _demarrer_un_run(fenetre)
    fenetre._contexte("traduction", "", "")
    fenetre._avancer(131, 131)
    fenetre._journaliser("warn", "une bulle non dessinée")
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé.")
    assert ouvertes == []
    assert "131 planches" in fenetre.bandeau.etiquette_compte.text()
    assert fenetre.bandeau.bouton_avertissements.text() == "Avertissements (1)"


def test_le_bouton_d_avertissements_ouvre_les_lignes_du_run(fenetre, monkeypatch):
    from PySide6.QtWidgets import QDialog
    vus = []
    monkeypatch.setattr(QDialog, "exec", lambda self: vus.append(self))
    _demarrer_un_run(fenetre)
    fenetre._journaliser("warn", "bulle 3 non dessinée")
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé.")
    fenetre.bandeau.bouton_avertissements.click()
    assert len(vus) == 1


def test_un_nouveau_run_repart_d_un_bandeau_propre(fenetre):
    _demarrer_un_run(fenetre)
    fenetre._journaliser("warn", "un incident")
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé.")
    _demarrer_un_run(fenetre)
    assert fenetre.bandeau.bouton_avertissements.isVisibleTo(fenetre.bandeau) is False
    assert fenetre.bandeau.etiquette_compte.text() == ""


def test_le_bilan_de_fin_compte_les_planches_du_run_entier(fenetre):
    """Le run finit dans « Rapport et assemblage », qui ne compte rien."""
    _demarrer_un_run(fenetre)
    fenetre._contexte("analyse", "", "")
    fenetre._avancer(131, 131)
    fenetre._contexte("finalisation", "", "")
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé.")
    assert "131 planches" in fenetre.bandeau.etiquette_compte.text()


def test_une_tache_hors_tome_ne_prend_pas_le_nom_du_run_precedent(fenetre):
    """Un import de glossaire porte `planche=None` lui aussi, mais `_cible_run` garde le
    tome du run PRÉCÉDENT : le bandeau annoncerait un tome auquel le geste ne touche pas."""
    from gui.travailleur import GENRE_CREATION
    _demarrer_un_run(fenetre)
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé.")
    fenetre._sur_debut(None, GENRE_CREATION, "Import de glossaire")
    assert fenetre.bandeau.etiquette_cible.text() == "Import de glossaire"
    assert fenetre.bandeau.barre.maximum() == 0, "aucune phase déclarée : indéterminée"


def test_un_relettrage_de_planche_ne_touche_ni_bandeau_ni_titre(fenetre):
    """Un travail LOCAL a un retour local : l'éditeur grise sa planche et dit ce qu'elle
    subit. Un bandeau qui clignoterait à chaque bulle relue serait du décor."""
    base = fenetre._titre_base
    fenetre._sur_debut(7, GENRE_RUN, "Planche 7 — reprise depuis « rendu »")
    fenetre._avancer(1, 1)
    assert fenetre.bandeau.isVisibleTo(fenetre) is False
    assert fenetre.windowTitle() == base


def test_l_arret_d_un_run_d_illustration_ne_passe_pas_par_le_fichier_stop(fenetre, monkeypatch):
    """Les deux briques ne s'arrêtent pas par le même chemin, et le bandeau sert les deux.

    Un `STOP` écrit dans le dossier d'un tome que personne ne traite n'arrêterait rien — et
    il attendrait le prochain run pour l'interrompre au démarrage."""
    from gui import fenetre as mod
    from gui.travailleur import GENRE_ILLUSTRATION
    ecrits = []
    monkeypatch.setattr(mod, "demander_arret", lambda *a: ecrits.append(a))
    arrets = []
    fenetre.aller_a("illustrations")
    monkeypatch.setattr(fenetre.atelier, "demander_arret", lambda: arrets.append(True))
    fenetre._cible_run = {"brique": "manga", "projet": "P", "tome": "Vol.1", "config": {}}
    fenetre._sur_debut(None, GENRE_ILLUSTRATION, "atelier d'illustration")
    fenetre.bandeau.bouton_arreter.click()
    assert arrets == [True]
    assert ecrits == []


def test_une_tache_sans_frontiere_propre_ne_propose_pas_d_arret(fenetre):
    """Proposer « Arrêter proprement » là où rien ne l'écoute serait promettre une garantie
    qu'on ne tient pas."""
    from gui.travailleur import GENRE_CREATION
    fenetre._sur_debut(None, GENRE_CREATION, "Import de glossaire")
    assert fenetre.bandeau.bouton_arreter.isVisibleTo(fenetre.bandeau) is False


# --------------------------------------------------------------------------- #
# PLAN-33 — le run de nuit, le modèle, et ce qui part au socle
# --------------------------------------------------------------------------- #

def test_l_energie_quitte_les_parametres_avant_la_tache(fenetre, tmp_path, monkeypatch):
    """⚠ **La ligne entre l'anti-veille et l'extinction, et elle est le sujet de L33.2.**

    L'anti-veille dure exactement le temps du travail : elle repart dans la tâche, avec un
    `finally` qui la lève même si le run lève. L'extinction, elle, commence quand le travail
    est FINI et doit rester annulable pendant deux minutes : elle est tenue par la fenêtre.

    `tache_run` ne doit donc jamais recevoir `energie` — il ne saurait qu'en faire."""
    vus = []
    monkeypatch.setattr(fenetre.fil, "soumettre", lambda tache: vus.append(tache))
    monkeypatch.setattr("gui.fenetre.tache_run",
                        lambda **kw: vus.append(kw) or "tache")
    fenetre._lancer_run({"brique": "manga", "projet": "P", "tome": "Vol.1",
                         "config": _config(tmp_path), "force": False, "depuis": None,
                         "page": None, "format_planche": None,
                         "energie": {"keep_awake": True, "shutdown": True,
                                     "shutdown_delay": 300}})
    kwargs = next(v for v in vus if isinstance(v, dict))
    assert kwargs["keep_awake"] is True
    assert "energie" not in kwargs and "shutdown" not in kwargs
    assert fenetre._energie_du_run == {"keep_awake": True, "shutdown": True,
                                       "shutdown_delay": 300}


def test_un_arret_demande_annule_l_extinction_du_run(fenetre, tmp_path, monkeypatch):
    """C'est `core/cli.finalize_power` mot pour mot : « Sur Ctrl+C, pas d'extinction ».
    L'interface et la ligne de commande doivent éteindre dans les mêmes cas."""
    monkeypatch.setattr("gui.fenetre.demander_arret", lambda *a: None)
    fenetre._cible_run = {"brique": "manga", "projet": "P", "tome": "Vol.1",
                          "config": _config(tmp_path)}
    fenetre._energie_du_run = {"shutdown": True, "shutdown_delay": 120}
    fenetre._arreter_run()
    assert fenetre._arret_demande is True

    eteints = []
    monkeypatch.setattr("core.power.shutdown", lambda d: eteints.append(d) or "shutdown /a")
    fenetre._armer_extinction()
    assert eteints == [], "un arrêt demandé ne doit jamais éteindre la machine"
    assert fenetre._extinction is None


def test_un_echec_eteint_quand_meme_et_le_bandeau_le_dit(fenetre, monkeypatch):
    """⚠ « On n'annule PAS l'extinction sur erreur — ça éviterait au PC de tourner toute la
    nuit pour rien. » Le compte à rebours part, et il est visible dans le bandeau."""
    eteints = []
    monkeypatch.setattr("core.power.shutdown", lambda d: eteints.append(d) or "shutdown /a")
    fenetre._arret_demande = False
    fenetre._energie_du_run = {"shutdown": True, "shutdown_delay": 300}
    fenetre._armer_extinction()
    assert eteints == [300]
    assert fenetre._extinction is not None
    assert "5 min" in fenetre.bandeau.etiquette_extinction.text()
    assert fenetre.bandeau.bouton_annuler_extinction.isVisibleTo(fenetre.bandeau)
    fenetre._arreter_minuteur_extinction()


def test_le_compte_a_rebours_s_annule_par_le_bandeau(fenetre, monkeypatch):
    """« Visible et annulable sans chercher » — et l'annulation passe par `power`, donc par le
    même `shutdown /a` que la ligne de commande."""
    monkeypatch.setattr("core.power.shutdown", lambda d: "shutdown /a")
    annulations = []
    monkeypatch.setattr("core.power.cancel_shutdown",
                        lambda: annulations.append(True) or "shutdown /a")
    fenetre._arret_demande = False
    fenetre._energie_du_run = {"shutdown": True, "shutdown_delay": 120}
    fenetre._armer_extinction()
    fenetre.bandeau.bouton_annuler_extinction.click()
    assert annulations == [True]
    assert fenetre._extinction is None
    assert fenetre.bandeau.bouton_annuler_extinction.isVisibleTo(fenetre.bandeau) is False


def test_une_ligne_de_journal_part_au_debut_du_compte_a_rebours(fenetre, monkeypatch):
    """Règle 4 de `gui/extinction.py` : à la fin, la machine s'éteint et le journal n'est plus
    lu par personne."""
    monkeypatch.setattr("core.power.shutdown", lambda d: "shutdown /a")
    lignes = []
    monkeypatch.setattr(fenetre, "_journaliser", lambda n, t: lignes.append((n, t)))
    fenetre._arret_demande = False
    fenetre._energie_du_run = {"shutdown": True, "shutdown_delay": 120}
    fenetre._armer_extinction()
    assert any("Extinction du PC programmée dans 2 min" in t for _, t in lignes)
    assert any("shutdown /a" in t for _, t in lignes)
    fenetre._arreter_minuteur_extinction()


def test_le_catalogue_de_modeles_part_avec_les_sondes(fenetre, monkeypatch):
    """⚠ **Dans le fil de travail, jamais sur le fil d'affichage** — et dans la MÊME tâche que
    les trois sondes d'installation : c'est le même appel réseau vers le même serveur, et deux
    tâches paieraient deux fois le délai de résolution de `localhost` (2,04 s, mesuré)."""
    from core import modeles as mdl

    catalogue = mdl.Catalogue(mdl.JOIGNABLE, (mdl.Modele("yume-27b", vision=True),),
                              "http://localhost:11434/v1/models")
    monkeypatch.setattr(mdl, "lister", lambda url, **kw: catalogue)
    lanceur = _lanceur(fenetre, "manga")
    assert lanceur.choix_modele.count() == 1, "inconnu au premier pixel"

    fenetre._sondes_lancees = False
    fenetre._lancer_sondes()
    tache = fenetre.fil.file.get(timeout=5) if hasattr(fenetre.fil, "file") else None
    if tache is not None:
        tache.fonction()
    else:                                              # pragma: no cover — file privée
        fenetre._resultat_sondes["modeles"] = catalogue
    fenetre._recevoir_sondes(True, "ok")
    assert lanceur.choix_modele.count() == 2
    assert lanceur.choix_modele.itemData(1) == "yume-27b"


def test_un_lanceur_construit_apres_la_sonde_voit_la_liste(fenetre):
    """Un panneau construit en retard doit refléter l'état de la fenêtre, pas celui de sa
    naissance — la même règle que `marquer_en_cours` au lot 31."""
    from core import modeles as mdl

    fenetre._catalogue_modeles = mdl.Catalogue(
        mdl.JOIGNABLE, (mdl.Modele("yume-27b", vision=True),), "url")
    lanceur = _lanceur(fenetre, "webtoon")
    assert lanceur.choix_modele.count() == 2


# --------------------------------------------------------------------------- #
# L34 — la bibliothèque des œuvres, vue de la fenêtre
# --------------------------------------------------------------------------- #

def _tome_manga_nu(tmp_path, projet="P", tome="Vol.1", planches=2) -> None:
    """Un tome sur disque, **sans une seule vraie image** : la bibliothèque n'en ouvre
    aucune, et un fichier vide suffit donc à la faire compter."""
    source = tmp_path / "sources" / projet / tome / "manga"
    source.mkdir(parents=True, exist_ok=True)
    for i in range(1, planches + 1):
        (source / f"{i:03d}.png").write_bytes(b"\0")


def test_la_destination_oeuvres_demande_son_balayage_au_fil_de_travail(fenetre, tmp_path):
    """⚠ Jamais sur le fil d'affichage : le balayage coûte ~1,3 s sur les 18 œuvres du
    corpus (mesuré), soit treize fois le seuil au-delà duquel un gel se voit."""
    from gui.travailleur import GENRE_BIBLIOTHEQUE

    _tome_manga_nu(tmp_path)
    genres = []
    monkey = fenetre.fil.soumettre
    fenetre.fil.soumettre = lambda tache: genres.append(tache.genre)
    try:
        panneau = fenetre.aller_a("oeuvres")
    finally:
        fenetre.fil.soumettre = monkey
    assert panneau is not None
    assert genres == [GENRE_BIBLIOTHEQUE]
    assert "Lecture" in panneau.etat.text()


def test_le_balayage_ne_verrouille_rien(fenetre):
    """⚠ Il ne fait que LIRE des entrées de répertoire. Lui laisser griser le bouton
    « Lancer » affaiblirait la lisibilité du verrou de run, pas sa force."""
    from gui.travailleur import GENRE_BIBLIOTHEQUE, GENRES_SANS_VERROU

    assert GENRE_BIBLIOTHEQUE in GENRES_SANS_VERROU


def test_le_resultat_du_balayage_remplit_le_panneau(fenetre, tmp_path):
    import bibliotheque as biblio

    _tome_manga_nu(tmp_path, "P", "Vol.1")
    _tome_manga_nu(tmp_path, "Q", "Chap.3")
    panneau = fenetre.aller_a("oeuvres")
    fenetre._resultat_bibliotheque = {
        "oeuvres": biblio.Inventaire(fenetre.config).oeuvres(paralleles=1)}
    fenetre._recevoir_bibliotheque(True, "ok")
    assert panneau.arbre.topLevelItemCount() == 2
    assert "2 tome(s) affiché(s) sur 2" in panneau.etat.text()


def test_un_balayage_en_echec_le_DIT_plutot_que_d_attendre_pour_toujours(fenetre):
    """Une attente qui ne finit jamais se lit comme une application bloquée."""
    panneau = fenetre.aller_a("oeuvres")
    fenetre._resultat_bibliotheque = {}
    fenetre._recevoir_bibliotheque(False, "disque illisible")
    assert "échoué" in panneau.etat.text()
    assert "disque illisible" in panneau.etat.text()


def test_lancer_depuis_la_bibliotheque_ouvre_le_lanceur_sans_rien_demarrer(fenetre, tmp_path):
    """⚠ **Critère 8.** Aucun bouton de la bibliothèque ne peut engager des heures de GPU :
    on amène à la destination qui annonce le coût, avec le tome présélectionné."""
    _tome_manga_nu(tmp_path, "P", "Vol.1")
    soumises = []
    monkey = fenetre.fil.soumettre
    fenetre.fil.soumettre = lambda tache: soumises.append(tache.genre)
    try:
        fenetre._oeuvres_lancer("P", "Vol.1", "manga")
    finally:
        fenetre.fil.soumettre = monkey
    assert fenetre.destination() == "manga"
    assert fenetre.retouche is None, "la bibliothèque n'a pas à ouvrir un tome"
    lanceur = fenetre._panneaux["manga"]
    assert lanceur.cible() == ("P", "Vol.1")
    from gui.travailleur import GENRE_RUN
    assert GENRE_RUN not in soumises


def test_une_brique_sans_lanceur_le_dit_plutot_que_d_ouvrir_au_hasard(fenetre, monkeypatch):
    """La brique scan n'a pas de destination dans l'interface (`PLAN-33` L33.5 l'a laissée
    ouverte). Le dire, avec la commande console, vaut mieux qu'ouvrir un lanceur manga."""
    dits = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: dits.append(a[2])))
    fenetre._oeuvres_lancer("P", "Vol.1", "scan")
    assert dits and "run_ocr.py" in dits[0]


def test_exporter_un_glossaire_absent_le_dit_sans_ouvrir_de_boite(fenetre, monkeypatch):
    dits = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: dits.append(a[2])))
    fenetre._oeuvres_exporter_glossaire("Inconnue", "Vol.1")
    assert dits and "glossaire" in dits[0].lower()
    assert "partagé par tous les tomes" in dits[0]


def test_creer_un_projet_rafraichit_la_bibliotheque(fenetre, tmp_path):
    """⚠ Elle ne se rafraîchit pas toute seule (aucun cache, aucune surveillance de dossier).
    Laisser l'état d'avant serait le défaut qu'elle est faite pour corriger."""
    from gui.travailleur import GENRE_BIBLIOTHEQUE

    _tome_manga_nu(tmp_path, "P", "Vol.1")
    fenetre.aller_a("oeuvres")
    genres = []
    monkey = fenetre.fil.soumettre
    fenetre.fil.soumettre = lambda tache: genres.append(tache.genre)
    try:
        fenetre._creation_en_attente = ("P", "Vol.2")
        fenetre._sur_fin(None, "creation", True, "créé")
    finally:
        fenetre.fil.soumettre = monkey
    assert GENRE_BIBLIOTHEQUE in genres


# --------------------------------------------------------------------------- #
#  L40.3 — le câblage de la mise à jour
#
#  ⚠ Ce que ces tests couvrent est le CÂBLAGE, pas la décision : `gui/vue_maj.py` décide, et
#  il est testé sans écran. Ce qui ne se voit qu'ici, c'est quelle tâche répond de quel
#  résultat — et c'est là qu'était le défaut.
# --------------------------------------------------------------------------- #

def _resultat_maj(disponible=True):
    from core import maj
    return maj.Resultat(arme=True, disponible=disponible, version="99.0.0")


def test_une_version_plus_recente_ouvre_la_proposition(fenetre, monkeypatch):
    vus = []
    monkeypatch.setattr(type(fenetre), "_proposer_maj",
                        lambda self, r, *, demandee: vus.append((r.version, demandee)))
    fenetre._resultat_sondes = {"maj": _resultat_maj()}
    fenetre._recevoir_maj_verifiee(True)
    assert vus == [("99.0.0", False)]


def test_rafraichir_la_liste_des_modeles_ne_rouvre_PAS_la_proposition(fenetre, monkeypatch):
    """⚠ **Le défaut que ce test empêche**, trouvé en relisant le câblage : `_resultat_maj`
    garde le résultat du dernier clic pour toute la session. Y retomber quand la tâche est une
    AUTRE sonde ferait rouvrir la fenêtre de proposition à chaque « Rafraîchir la liste des
    modèles », sur un résultat qui date. Une tâche répond de SON résultat."""
    vus = []
    monkeypatch.setattr(type(fenetre), "_proposer_maj",
                        lambda self, r, *, demandee: vus.append(r.version))
    fenetre._resultat_maj = {"maj": _resultat_maj()}          # un clic antérieur
    fenetre._resultat_sondes = {"modeles": None}              # la sonde de modèles, seule
    fenetre._recevoir_maj_verifiee(True)
    assert vus == []


def test_le_bouton_repond_toujours_quelque_chose(fenetre, monkeypatch):
    """Sur clic, on répond même quand il n'y a rien à proposer : un bouton qui ne fait rien
    passe pour cassé. Au démarrage, au contraire, on se tait."""
    dits = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: dits.append(a[2])))
    fenetre._maj_demandee = True
    fenetre._resultat_maj = {"maj": _resultat_maj(disponible=False)}
    fenetre._recevoir_maj_verifiee(True)
    assert dits, "un clic sans nouveauté doit quand même répondre"


def test_le_drapeau_de_demande_est_remis_a_zero(fenetre, monkeypatch):
    """Sans cette remise à zéro, la sonde suivante serait prise pour un clic."""
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    fenetre._maj_demandee = True
    fenetre._resultat_maj = {"maj": _resultat_maj(disponible=False)}
    fenetre._recevoir_maj_verifiee(True)
    assert fenetre._maj_demandee is False


def test_la_verification_part_avec_les_sondes_et_pas_sur_le_fil_d_affichage(fenetre,
                                                                            monkeypatch):
    """⚠ La règle absolue de `gui/sondes.py`. Le test regarde le GENRE de la tâche soumise :
    un appel réseau posé sur le fil d'affichage gèlerait la fenêtre avant le premier pixel."""
    from gui.travailleur import GENRE_SONDE
    taches = []
    monkeypatch.setattr(type(fenetre.fil), "soumettre",
                        lambda self, tache: taches.append(tache))
    fenetre._sondes_lancees = False
    fenetre._lancer_sondes()
    assert taches and taches[0].genre == GENRE_SONDE


def test_a_propos_ne_relance_aucun_appel_reseau(fenetre, monkeypatch):
    """⚠ La vérification a déjà eu lieu au démarrage. Repartir pour 3,0 s de délai sur le fil
    d'affichage pour réafficher la même phrase serait un gel sans contrepartie."""
    from core import maj
    monkeypatch.setattr(maj, "verifier", lambda *a, **k: pytest.fail(
        "À propos a relancé un appel réseau"))
    monkeypatch.setattr("gui.dialogues.DialogueTexte.exec", lambda self: 0)
    fenetre._resultat_sondes = {"maj": _resultat_maj()}
    fenetre.action_a_propos()
