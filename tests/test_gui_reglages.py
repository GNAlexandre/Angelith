# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'état de travail persisté (`gui/reglages.py`) — **sans PySide6**.

## Ce que ce fichier protège

Deux choses, et la seconde compte plus que la première.

1. **L'aller-retour.** Sans persistance, chaque lancement remettait la fenêtre à 1520 × 960, le
   journal replié, les colonnes à `[240, 860, 380]`, le filtre sur « toutes » et l'onglet
   « Planches ». Sur un tome de 150 planches, tout réglage de disposition était à refaire à
   chaque session.

2. **Ce qui n'est JAMAIS persisté.** `--force` (« Tout refaire depuis zéro ») mémorisé, c'est un
   tome relancé depuis la détection parce qu'une case était encore cochée d'hier : des heures de
   GPU pour un état que personne n'a redemandé. Le filtre s'applique à l'écriture ET à la
   lecture, parce que le fichier est éditable à la main.

⚠ Chaque test pose `$ANGELITH_REGLAGES` sur son `tmp_path` : sans cela, la suite écrirait dans
le `.angelith/` du dépôt de qui la lance.
"""
from __future__ import annotations

import json

import pytest

from gui import reglages as reg


@pytest.fixture
def racine(tmp_path, monkeypatch):
    cible = tmp_path / "interface.json"
    monkeypatch.setenv(reg.VARIABLE, str(cible))
    return cible


# --------------------------------------------------------------------------- #
# L'aller-retour
# --------------------------------------------------------------------------- #

def test_un_premier_lancement_rend_les_defauts(racine):
    """Et ces défauts reproduisent EXACTEMENT le comportement d'avant le lot 18 — c'est ce qui
    rend la nouvelle capacité iso-comportement pour qui ne touche à rien."""
    etat = reg.lire()
    assert etat["fenetre"] == {"largeur": 1520, "hauteur": 960, "maximisee": False}
    assert etat["colonnes"] == [240, 860, 380]
    assert etat["journal"] == [940, 0]
    assert etat["filtre"] == "toutes"
    assert etat["garder_cadrage"] is False
    # Lot 31 — `onglet: 0` est remplacé par `destination`, et le défaut est l'ACCUEIL : la
    # seule destination dont on soit sûr qu'elle n'ouvre aucun tome.
    assert "onglet" not in etat
    assert etat["destination"] == "accueil"
    assert etat["recents"] == []


def test_aller_retour_complet(racine):
    etat = reg.defauts()
    etat["fenetre"] = {"largeur": 2400, "hauteur": 1300, "maximisee": True}
    etat["colonnes"] = [300, 1400, 700]
    etat["journal"] = [700, 300]
    etat["filtre"] = "débordements"
    etat["destination"] = "manga"
    etat["garder_cadrage"] = True
    etat["dernier_projet"] = "Mon Manga"
    etat["dernier_tome"] = "Vol.3"
    etat["recents"] = [{"projet": "Mon Manga", "tome": "Vol.3", "destination": "retouche"}]
    assert reg.ecrire(etat) == racine
    relu = reg.lire()
    for cle in ("fenetre", "colonnes", "journal", "filtre", "destination", "garder_cadrage",
                "dernier_projet", "dernier_tome", "recents"):
        assert relu[cle] == etat[cle], cle


def test_les_defauts_ne_sont_pas_partages(racine):
    """`defauts()` rend une COPIE : un appelant distrait qui modifie le dictionnaire ne doit
    pas le modifier pour toute la session."""
    premier = reg.defauts()
    premier["colonnes"].append(999)
    assert reg.defauts()["colonnes"] == [240, 860, 380]


# --------------------------------------------------------------------------- #
# Ce qui ne se persiste jamais
# --------------------------------------------------------------------------- #

def test_force_n_est_jamais_ecrit(racine):
    """La règle qui coûte des heures de GPU quand elle est violée."""
    etat = reg.defauts()
    etat["runs"] = {"verbose": True, "force": True, "dry_run": True, "brique": "manga"}
    reg.ecrire(etat)
    brut = json.loads(racine.read_text(encoding="utf-8"))
    assert "force" not in brut["etat"]["runs"]
    assert "dry_run" not in brut["etat"]["runs"]
    assert brut["etat"]["runs"]["verbose"] is True


def test_force_n_est_pas_ecrit_non_plus_SOUS_une_destination(racine):
    """**Le test qui aurait échoué si le lot 31 avait oublié un niveau.**

    `runs` était un dictionnaire plat ; il porte maintenant un sous-dictionnaire par
    destination de lancement. Un `nettoyer()` resté à un niveau aurait laissé passer
    `runs["webtoon"]["force"]` — c'est-à-dire la règle qui coûte des heures de GPU, contournée
    par une clé de plus dans le chemin."""
    etat = reg.defauts()
    etat["runs"] = {
        "manga": {"verbose": True, "force": True},
        "webtoon": {"verbose": False, "dry_run": True, "lot": 20},
    }
    reg.ecrire(etat)
    brut = json.loads(racine.read_text(encoding="utf-8"))["etat"]["runs"]
    assert "force" not in brut["manga"]
    assert "dry_run" not in brut["webtoon"]
    assert brut["manga"]["verbose"] is True
    assert brut["webtoon"]["lot"] == 20
    relu = reg.lire()["runs"]
    assert "force" not in relu["manga"] and "dry_run" not in relu["webtoon"]


def test_un_fichier_de_la_version_precedente_est_ignore_EN_BLOC(racine):
    """L31.5 — **il n'y a pas de migration à écrire, et c'est le comportement voulu.**

    Trois clés changent de nature au lot 31 (`onglet` → `destination`, `runs` à deux niveaux,
    `recents`). Convertir un `onglet: 0` en `destination: "retouche"` serait rouvrir un tome au
    démarrage, ce que le lot entier existe pour ne plus faire. Le module ignore donc le fichier
    en bloc : « une disposition perdue coûte trois clics, une disposition à moitié appliquée
    coûte une session ». Ce test le prouve plutôt que de l'affirmer."""
    racine.write_text(json.dumps({
        "version": reg.VERSION - 1,
        "etat": {"onglet": 1, "filtre": "débordements", "colonnes": [10, 20, 30],
                 "dernier_projet": "Mon Manga", "dernier_tome": "Vol.3"},
    }), encoding="utf-8")
    relu = reg.lire()
    assert relu == reg.defauts()
    assert relu["destination"] == "accueil"
    assert relu["filtre"] == "toutes", "rien du fichier périmé ne doit passer, pas même ceci"


def test_les_recents_remontent_sans_doublon():
    """`noter_recent` dédoublonne sur `(projet, tome)`, pas sur la destination : ouvrir le même
    tome en retouche puis le relancer depuis « Manga » est le même tome."""
    etat = reg.defauts()
    etat = reg.noter_recent(etat, "A", "Vol.1", "retouche")
    etat = reg.noter_recent(etat, "B", "Vol.2", "manga")
    etat = reg.noter_recent(etat, "A", "Vol.1", "manga")
    assert [(e["projet"], e["tome"]) for e in etat["recents"]] == [("A", "Vol.1"),
                                                                  ("B", "Vol.2")]
    assert etat["recents"][0]["destination"] == "manga"


def test_les_recents_sont_plafonnes_et_ne_mutent_pas_l_appelant():
    etat = reg.defauts()
    for n in range(reg.RECENTS_GARDES + 3):
        etat = reg.noter_recent(etat, f"P{n}", "Vol.1", "retouche")
    assert len(etat["recents"]) == reg.RECENTS_GARDES
    depart = reg.defauts()
    reg.noter_recent(depart, "A", "Vol.1", "retouche")
    assert depart["recents"] == [], "noter_recent rend un nouvel état, il ne mute rien"


def test_un_tome_sans_nom_n_entre_pas_dans_les_recents():
    """Une carte « Reprendre  ·   /  » serait un clic sans destination."""
    assert reg.noter_recent(reg.defauts(), "", "Vol.1", "retouche")["recents"] == []
    assert reg.noter_recent(reg.defauts(), "A", "", "retouche")["recents"] == []


def test_force_ecrit_a_la_main_est_ignore_a_la_lecture(racine):
    """Le fichier est éditable — c'est même l'une des raisons de préférer un JSON visible à
    `QSettings`. Un `"force": true` ajouté au clavier ne doit pas plus armer un run qu'une
    case cochée hier."""
    racine.write_text(json.dumps({
        "version": reg.VERSION,
        "etat": {"runs": {"verbose": False, "force": True}, "force": True},
    }), encoding="utf-8")
    relu = reg.lire()
    assert "force" not in relu["runs"]
    assert "force" not in relu
    assert relu["runs"]["verbose"] is False


def test_l_extinction_n_est_jamais_persistee_lot_33(racine):
    """**Critère 8 du `PLAN-33`**, côté réglages.

    ⚠ C'est le plus grave des trois cas de `NON_PERSISTES` : une case « Éteindre le PC à la
    fin » retrouvée cochée éteindrait la machine sur laquelle on travaille, à la fin d'un run
    qu'on regardait. Le DÉLAI, lui, se persiste — c'est un réglage d'installation, pas un
    mandat."""
    etat = reg.defauts()
    etat["runs"] = {"manga": {"verbose": True, "shutdown": True, "shutdown_delay": 300,
                              "keep_awake": True}}
    reg.ecrire(etat)
    relu = reg.lire()["runs"]["manga"]
    assert "shutdown" not in relu
    assert relu["shutdown_delay"] == 300
    assert relu["keep_awake"] is True


def test_une_extinction_ecrite_a_la_main_est_ignoree_a_la_lecture(racine):
    """Le fichier est éditable au clavier ; c'est le seul barrage que ni le formulaire ni
    l'appelant ne peuvent tenir."""
    racine.write_text(json.dumps({
        "version": reg.VERSION,
        "etat": {"runs": {"manga": {"shutdown": True, "verbose": True}}, "shutdown": True},
    }), encoding="utf-8")
    relu = reg.lire()
    assert "shutdown" not in relu["runs"]["manga"]
    assert "shutdown" not in relu


def test_les_non_persistes_sont_ceux_que_la_table_declare():
    """Deux listes pour une même règle divergeraient au premier ajout. `gui/parametres.py`
    porte `persiste` par paramètre ; ce module porte le filet qui s'applique aussi aux
    fichiers écrits à la main. Ils doivent dire la même chose."""
    from gui import parametres as par

    for panneau in (par.LIGHT_NOVEL, par.MANGA, par.WEBTOON):
        declares = {p.identifiant for p in par.pour(panneau) if not p.persiste}
        assert reg.NON_PERSISTES <= declares | {"page", "graine"}, panneau
        assert {"force", "dry_run", "shutdown"} <= declares, panneau


def test_nettoyer_est_idempotent():
    propre = reg.nettoyer({"runs": {"force": True, "verbose": True}})
    assert reg.nettoyer(propre) == propre


# --------------------------------------------------------------------------- #
# Robustesse — un état corrompu ne doit pas empêcher de démarrer
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("contenu", [
    "",                                   # fichier vide
    "{ pas du json",                      # tronqué
    '{"version": 999, "etat": {}}',       # version inconnue
    '{"version": 1, "etat": []}',         # forme inattendue
    '["une", "liste"]',                   # écrit par autre chose
])
def test_un_fichier_abime_rend_les_defauts(racine, contenu):
    """Refuser de démarrer parce qu'une disposition est corrompue serait échanger un inconfort
    contre une panne."""
    racine.write_text(contenu, encoding="utf-8")
    assert reg.lire() == reg.defauts()


def test_un_fichier_d_une_version_anterieure_est_complete(racine):
    """Une clé ajoutée depuis manque forcément. La lire telle quelle ferait tomber la fenêtre
    sur un `KeyError` au démarrage — le pire moment."""
    racine.write_text(json.dumps({"version": reg.VERSION,
                                  "etat": {"filtre": "rendu périmé"}}), encoding="utf-8")
    relu = reg.lire()
    assert relu["filtre"] == "rendu périmé"
    assert relu["colonnes"] == [240, 860, 380]
    assert relu["fenetre"]["largeur"] == 1520


def test_une_sous_cle_manquante_est_completee(racine):
    racine.write_text(json.dumps({"version": reg.VERSION,
                                  "etat": {"fenetre": {"largeur": 800}}}), encoding="utf-8")
    fen = reg.lire()["fenetre"]
    assert fen == {"largeur": 800, "hauteur": 960, "maximisee": False}


def test_ecrire_ne_leve_pas_sur_un_chemin_impossible(tmp_path, monkeypatch):
    """`ecrire` est appelée depuis `closeEvent` : une exception y laisserait la fenêtre ouverte
    sur un dossier en lecture seule, pour une disposition qui n'est pas du travail à protéger."""
    fichier = tmp_path / "occupe"
    fichier.write_text("je suis un fichier", encoding="utf-8")
    monkeypatch.setenv(reg.VARIABLE, str(fichier / "sous" / "interface.json"))
    assert reg.ecrire(reg.defauts()) is None


# --------------------------------------------------------------------------- #
# La sortie de secours
# --------------------------------------------------------------------------- #

def test_effacer_rend_les_defauts(racine):
    """« Réinitialiser la disposition » : un état persisté corrompu doit avoir une sortie qui
    ne demande pas d'éditer un fichier à la main."""
    etat = reg.defauts()
    etat["colonnes"] = [10, 20, 30]
    reg.ecrire(etat)
    assert reg.effacer() is True
    assert reg.lire() == reg.defauts()
    assert reg.effacer() is False          # plus rien à supprimer, et ce n'est pas une erreur


def test_le_chemin_par_defaut_vit_a_cote_du_depot(monkeypatch, tmp_path):
    """`.angelith/interface.json` à la racine, pas dans le registre ni sous %APPDATA% : on doit
    pouvoir le REGARDER le jour où la fenêtre rouvre hors écran."""
    monkeypatch.delenv(reg.VARIABLE, raising=False)
    chemin = reg.chemin(tmp_path)
    assert chemin.parent.name == ".angelith"
    assert chemin.name == "interface.json"
    assert chemin.parent.parent == tmp_path
