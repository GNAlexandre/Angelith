# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""État de travail de l'interface, persisté d'une session à l'autre.

## Où ça vit, et pourquoi pas `QSettings`

**Un fichier JSON, `.angelith/interface.json`, à la racine du dépôt** — à côté de `config.yaml`,
pas dans le registre Windows ni sous `%APPDATA%`. Trois raisons, dans l'ordre :

1. **On peut le regarder.** Un état persisté corrompu est un mode de panne réel — la fenêtre
   rouvre hors écran, une colonne à zéro pixel. `QSettings` sur Windows écrit dans le registre,
   qu'aucun utilisateur de ce projet n'ira lire. Ici, `type .angelith\\interface.json` suffit,
   et « Réinitialiser la disposition » (menu Affichage) efface le fichier sans qu'on ait à
   l'éditer.
2. **Ça se teste sans Qt.** La règle de couche du dépôt (`gui/__init__.py`) veut que tout ce
   qui décide se teste sans PySide6. Un aller-retour de persistance en fait partie, et c'est
   le critère 7 du `PLAN-18`.
3. **Ça suit le dépôt.** Deux copies du dépôt sur la même machine ont deux dispositions, ce qui
   est la lecture juste : la disposition appartient au corpus qu'on édite, pas à l'utilisateur.

⚠ **Ce n'est pas `config.yaml`.** Aucune clé de configuration du pipeline ne passe par ici, et
le fichier est réécrit intégralement à chaque fermeture — c'est précisément pour cela que
`config.yaml`, lui, n'est jamais réécrit : ses 95 Ko de prose commentée ne survivraient pas à
un aller-retour `safe_dump`.

## Ce qui n'est JAMAIS persisté, et c'est délibéré

`--force` (« Tout refaire depuis zéro »). Une case cochée hier qui se retrouve cochée
aujourd'hui, c'est un tome relancé depuis la détection — des heures de GPU pour un état que
personne n'a redemandé. La case repart décochée à chaque lancement, toujours.

`--dry-run` non plus : rouvrir en simulation ferait croire à un run qui ne traduit rien.

⚠ **`--shutdown` s'y ajoute au lot 33**, et c'est le cas le plus grave des trois : une case
« Éteindre le PC à la fin » retrouvée cochée éteindrait la machine sur laquelle on travaille,
à la fin d'un run qu'on regardait. C'est la seule action de l'application qui touche au
matériel.

Le contrat est vérifié par `tests/test_gui_reglages.py` : `nettoyer()` retire ces clés quoi
qu'on lui donne, y compris un fichier écrit à la main — et `tests/test_gui_profils.py` fait de
même pour `.angelith/profils.json`, qui est un second fichier avec la même règle.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: Nom du dossier de réglages, à la racine du dépôt. Caché, comme `.checkpoints/` et
#: `.vignettes/` : il n'est pas fait pour être lu par un humain au quotidien — seulement le
#: jour où quelque chose cloche.
DOSSIER = ".angelith"
FICHIER = "interface.json"

#: Variable d'environnement qui déplace le fichier. Elle existe pour les TESTS — chacun écrit
#: dans son `tmp_path` — et pour une installation en lecture seule.
VARIABLE = "ANGELITH_REGLAGES"

#: Version du format. Un fichier d'une version inconnue est ignoré en bloc plutôt que lu à
#: moitié : une disposition perdue coûte trois clics, une disposition à moitié appliquée
#: coûte une session à comprendre pourquoi la fenêtre est bizarre.
#:
#: ⚠ **2 depuis le lot 31 (2026-09-04).** Trois clés changent de nature, et aucune ne se
#: convertit honnêtement :
#:
#: · `onglet: 0` devient `destination: "accueil"` — un index d'onglet n'a plus de destinataire,
#:   et le traduire supposerait de savoir que l'onglet 0 était « Planches », donc la destination
#:   « Retouche ». C'est vrai, et ce serait précisément rouvrir un tome au démarrage : le lot
#:   entier existe pour ne plus le faire ;
#: · `runs` était un dictionnaire plat, il devient un dictionnaire PAR destination de lancement ;
#: · `recents` naît.
#:
#: **Il n'y a donc pas de migration à écrire, et c'est le comportement voulu** : le module
#: ignore en bloc un fichier de version inconnue. Une session repart sur les défauts —
#: l'accueil, une fenêtre de 1520 × 960 — ce qui coûte trois clics, contre une session entière
#: à comprendre pourquoi la fenêtre est bizarre. `tests/test_gui_reglages.py` le prouve plutôt
#: que de l'affirmer.
VERSION = 2

#: Clés qu'on refuse de persister, quoi qu'il arrive. Cf. l'avertissement du module.
#:
#: ⚠ **`shutdown` s'y ajoute au lot 33 (2026-09-05)**, et son motif est le plus fort des
#: trois. `force` cochée hier coûte des heures de GPU ; `shutdown` cochée hier éteint la
#: machine sur laquelle on travaille, à la fin d'un run qu'on regardait. C'est la seule action
#: de l'application qui touche au matériel, et elle ne se reconduit pas toute seule.
#:
#: ⚠ Le DÉLAI, lui, se persiste (`shutdown_delay`) : c'est un réglage d'installation — 120 s
#: ou 300 s selon la machine — et non un mandat. La distinction est déclarée une fois pour
#: toutes dans `gui/parametres.py`, où chaque paramètre porte son `persiste`.
NON_PERSISTES: frozenset[str] = frozenset({"force", "dry_run", "shutdown"})

#: Valeurs de repli — celles qu'un premier lancement applique, et celles que
#: « Réinitialiser la disposition » rétablit. Elles reproduisent EXACTEMENT le comportement
#: d'avant le lot 18 : c'est ce qui rend la nouvelle capacité iso-comportement par défaut.
DEFAUTS: dict = {
    "fenetre": {"largeur": 1520, "hauteur": 960, "maximisee": False},
    "colonnes": [240, 860, 380],
    "journal": [940, 0],
    "filtre": "toutes",
    # ⚠ `auto` par défaut : l'interface suit ce que le système annonce. C'est le seul défaut
    # iso-perception — jusqu'ici l'application portait le style natif de la plateforme, donc
    # clair sur une machine réglée en clair. Un `"clair"` en dur ferait pire que le lot 18 sur
    # une machine réglée en sombre.
    "theme": "auto",
    "garder_cadrage": False,
    # Lot 31 — la destination ouverte à la dernière fermeture. ⚠ Le défaut est `accueil` et
    # **rien ne rouvre le dernier tome tout seul** : `dernier_projet` / `dernier_tome`
    # alimentent la carte « Reprendre » de l'accueil, un clic. C'est tout l'objet du lot — ce
    # qui était implicite devient un geste.
    "destination": "accueil",
    "dernier_projet": "",
    "dernier_tome": "",
    # Les œuvres récentes, telles que l'accueil les montre. Une LISTE d'entrées
    # `{"projet", "tome", "destination"}`, la plus récente en tête, plafonnée par
    # `RECENTS_GARDES`. Lues ici et jamais sur le disque : balayer `sources/` pour dater
    # dix-sept projets serait exactement le coût que l'accueil existe pour supprimer.
    "recents": [],
    # Lot 31 — un jeu de réglages PAR destination de lancement. Les trois lanceurs sont trois
    # instances distinctes ; leur donner un seul dictionnaire ferait qu'un « lot de 20 »
    # réglé pour le manga s'appliquerait au light novel, qui ne connaît pas les planches.
    # ⚠ **La forme de ces sous-dictionnaires est celle de `gui/parametres.py`**, filtrée par
    # `parametres.persistables()` : ce qui est écrit ici est ce que le formulaire déclare
    # persistable, et rien de plus. Les recopier à la main n'était tenable qu'à cinq clés ; à
    # partir du lot 33 il y en a jusqu'à onze, et c'est la table qui fait foi.
    #
    # ⚠ `0` = « selon config.yaml », et non « zéro pixel » ni « zéro planche ». C'est le seul
    # état qui laisse un `config.yaml` réglé à la main faire autorité — poser 2160 par défaut
    # ici figerait la valeur du jour où ces lignes ont été écrites.
    "runs": {
        "light_novel": {"verbose": True, "depuis": None,
                        "keep_awake": False, "shutdown_delay": 120},
        "manga": {"verbose": True, "depuis": None, "langue": None, "lot": 0, "think": None,
                  "keep_awake": False, "shutdown_delay": 120, "modele": None},
        "webtoon": {"verbose": True, "depuis": None, "langue": None, "lot": 0, "think": None,
                    "fenetre_hauteur": 0, "fenetre_recouvrement": 0,
                    "keep_awake": False, "shutdown_delay": 120, "modele": None},
    },
    # Lot 27 — l'atelier d'illustration. ⚠ **Ni le nom du valideur, ni la graine.** Le nom
    # est une signature : le retrouver pré-rempli le lendemain transformerait une validation
    # en case cochée d'avance, exactement ce que la porte humaine refuse. La graine d'hier
    # appliquée à un autre personnage produirait une reproductibilité qui ne reproduit rien.
    "atelier": {"projet": "", "cadrage": None, "nombre": 1},
    # Préférences de l'interface. `None` = « s'en remettre à config.yaml », qui reste la
    # référence partagée : ces deux clés existent pour régler UNE installation, pas pour
    # doubler le fichier.
    "reprendre": True,
    "plafond_mo": None,
    "fenetre_apercu": None,
    # Lot 39 — l'adresse du serveur LLM de CETTE installation. ⚠ `None` = « s'en remettre à
    # `config.yaml` », comme les deux clés ci-dessus, et surtout PAS `""` : une chaîne vide
    # persistée couperait le serveur au lieu de ne pas y toucher. C'est la règle des trois
    # états de `gui/parametres.py`, et c'est aussi ce qui permet de régler UNE machine sans
    # doubler le fichier partagé.
    "serveur_llm": None,
    # Lot 40 — « Ne plus afficher » sur la fenêtre de proposition de mise à jour.
    #
    # ⚠ **Ceci masque LA FENÊTRE, pas la capacité, et surtout pas l'appel réseau.** Ce qui
    # décide qu'un `GET` part est `config.yaml > maj.verifier` ; cette clé-ci décide seulement
    # si on ouvre une fenêtre quand la réponse annonce une version plus récente. Le bouton
    # « Rechercher une mise à jour » d'« À propos » continue de marcher, et la case est
    # réversible depuis les Réglages.
    #
    # Confondre les deux ferait d'un « ne me dérange plus » un opt-out réseau silencieux que
    # personne ne saurait ensuite retrouver — cf. `gui/vue_maj.py`, qui porte le tableau.
    "maj_silencieuse": False,
}


def chemin(racine: str | os.PathLike | None = None) -> Path:
    """Où le fichier vit. `$ANGELITH_REGLAGES` l'emporte sur tout — c'est ce que les tests
    posent, et c'est aussi le repli d'une installation dont la racine n'est pas inscriptible.

    ⚠ **MISE À JOUR 2.31.0 (2026-09-06), lot 37.** L'avertissement du module — « à la racine du
    dépôt, à côté de `config.yaml` » — reste vrai **dans le dépôt** et devient faux dans une
    installation gelée, où le répertoire courant est celui d'où le raccourci a été lancé et où
    le dossier d'installation peut être en lecture seule. Le défaut gelé est
    `%LOCALAPPDATA%/Angelith/.angelith/interface.json`, et il vient de
    `core.installation.dossier_reglages()` — la variable d'environnement, elle, était **déjà**
    prévue « pour une installation en lecture seule » : il n'y avait rien à inventer, seulement
    un défaut à décider."""
    force = os.environ.get(VARIABLE)
    if force:
        return Path(force)
    from core.installation import dossier_reglages
    base = Path(racine) if racine is not None else dossier_reglages()
    return base / DOSSIER / FICHIER


def _fusionner(defauts: dict, lus: dict) -> dict:
    """Fusion à UN niveau de profondeur, les défauts en dessous.

    ⚠ Fusionner plutôt que remplacer n'est pas un raffinement : un fichier écrit par une
    version antérieure n'a pas les clés ajoutées depuis, et le lire tel quel ferait planter la
    fenêtre sur un `KeyError` au démarrage — le pire moment."""
    sortie = {}
    for cle, defaut in defauts.items():
        valeur = lus.get(cle, defaut)
        if isinstance(defaut, dict) and isinstance(valeur, dict):
            sortie[cle] = {**defaut, **valeur}
        else:
            sortie[cle] = valeur
    return sortie


def nettoyer(etat: dict) -> dict:
    """Retire ce qui ne doit jamais être persisté. **Appelée à l'écriture ET à la lecture.**

    Aux deux bouts, parce que le fichier est éditable à la main : un `"force": true` ajouté au
    clavier ne doit pas plus armer un run qu'une case cochée hier.

    ⚠ **Deux niveaux depuis le lot 31**, et c'est la seule chose que ce changement de forme
    devait ne pas rater. `runs` était plat ; il porte maintenant un sous-dictionnaire par
    destination de lancement, et un nettoyage resté à un niveau aurait laissé passer
    `runs["webtoon"]["force"]` — c'est-à-dire la règle qui coûte des heures de GPU, contournée
    par une clé de plus dans le chemin."""
    propre = dict(etat)
    for cle in NON_PERSISTES:
        propre.pop(cle, None)
    if "runs" in propre:
        propre["runs"] = _nettoyer_runs(propre.get("runs"))
    return propre


def _nettoyer_runs(runs) -> dict:
    """Retire `force` et `dry_run` du dictionnaire de runs, à un niveau **comme à deux**."""
    if not isinstance(runs, dict):
        return {}
    propre: dict = {}
    for cle, valeur in runs.items():
        if cle in NON_PERSISTES:
            continue
        propre[cle] = _nettoyer_runs(valeur) if isinstance(valeur, dict) else valeur
    return propre


#: Nombre d'œuvres récentes gardées dans le fichier. Trois de plus que ce que l'accueil
#: montre : une œuvre supprimée depuis laisse la place à la suivante sans que la liste se vide.
RECENTS_GARDES = 6


def noter_recent(etat: dict, projet: str, tome: str, destination: str) -> dict:
    """Remonte `(projet, tome)` en tête des récents. **Rend un nouvel état**, ne mute rien.

    ⚠ Dédoublonné sur le couple `(projet, tome)`, pas sur la destination : ouvrir le même tome
    en retouche puis le relancer depuis « Manga » est le même tome, et l'afficher deux fois
    dans une liste de trois entrées en gâcherait les deux tiers."""
    if not (projet and tome):
        return dict(etat)
    garde = [e for e in (etat.get("recents") or [])
             if isinstance(e, dict)
             and (e.get("projet"), e.get("tome")) != (projet, tome)]
    entree = {"projet": projet, "tome": tome, "destination": destination}
    propre = dict(etat)
    propre["recents"] = [entree, *garde][:RECENTS_GARDES]
    return propre


def defauts() -> dict:
    """Une copie neuve des valeurs de repli — jamais l'objet du module, qu'un appelant
    distrait modifierait pour tout le monde."""
    return json.loads(json.dumps(DEFAUTS))


def lire(racine: str | os.PathLike | None = None) -> dict:
    """L'état persisté, complété par les défauts. **Ne lève jamais.**

    Un fichier illisible, tronqué, d'une version inconnue ou écrit par un autre programme rend
    les défauts. Refuser de démarrer parce qu'une disposition est corrompue serait échanger un
    inconfort contre une panne."""
    cible = chemin(racine)
    try:
        brut = json.loads(cible.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defauts()
    if not isinstance(brut, dict) or brut.get("version") != VERSION:
        return defauts()
    etat = brut.get("etat")
    if not isinstance(etat, dict):
        return defauts()
    return nettoyer(_fusionner(defauts(), etat))


def ecrire(etat: dict, racine: str | os.PathLike | None = None) -> Path | None:
    """Écrit l'état et rend le chemin, ou `None` si l'écriture a échoué.

    ⚠ Silencieux sur échec **par décision** : cette fonction est appelée depuis `closeEvent`.
    Une exception à la fermeture laisserait la fenêtre ouverte sur un dossier en lecture seule,
    et la disposition n'est pas un travail à protéger — le travail, lui, est déjà écrit à ce
    moment-là."""
    cible = chemin(racine)
    charge = {"version": VERSION, "etat": nettoyer(etat)}
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(json.dumps(charge, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    except OSError:
        return None
    return cible


def effacer(racine: str | os.PathLike | None = None) -> bool:
    """Supprime le fichier — « Réinitialiser la disposition ». `True` s'il y avait
    quelque chose à supprimer."""
    cible = chemin(racine)
    try:
        cible.unlink()
    except OSError:
        return False
    return True
