# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les profils de lancement — **un raccourci de saisie, jamais un mandat**.

## Ce qu'un profil est

Un run de ce projet a beaucoup de paramètres et trois ou quatre combinaisons réelles :
« nuit complète », « reprise rapide », « simulation sans LLM », « relettrage seul ». Un profil
est un jeu de valeurs nommé, rangé dans `.angelith/profils.json`, à côté de
`.angelith/interface.json` et pour les mêmes trois raisons (`gui/reglages.py`) : on peut le
regarder, ça se teste sans Qt, ça suit le dépôt.

## ⚠ Ce qu'un profil n'a PAS le droit de porter

**`force`, `dry_run` et `shutdown`.** C'est la règle `NON_PERSISTES` de `gui/reglages.py`,
dont le motif est chiffré : « une case cochée hier qui se retrouve cochée aujourd'hui, c'est
un tome relancé depuis la détection — des heures de GPU pour un état que personne n'a
redemandé ». Un profil est pire qu'un fichier de réglages sur ce point : il se rappelle
**exprès**, et il se rappelle sous un nom rassurant. « Nuit complète » qui rearme `--force`
détruirait un cache que personne n'a demandé de refaire ; « Nuit complète » qui rearme
`--shutdown` éteindrait une machine que personne n'a demandé d'éteindre.

**Ni le projet, ni le tome.** Un profil qui se souvient d'un tome est un raccourci qui lance
le mauvais run — c'est la seule erreur de cette liste qui ne coûte pas du GPU mais un tome
écrasé.

Le filtre est **triple**, et ce n'est pas décoratif :

| Barrage | Ce qu'il attrape |
|---|---|
| `parametres.persistables()` | ce que le formulaire propose d'enregistrer |
| `profils.nettoyer()` **à l'écriture** | une valeur ajoutée par un appelant distrait |
| `profils.nettoyer()` **à la lecture** | ⚠ un fichier ÉDITÉ À LA MAIN — le seul cas que les deux autres ne voient jamais |

`tests/test_gui_profils.py` vérifie le troisième en écrivant le fichier au clavier, comme
`tests/test_gui_reglages.py` le fait déjà pour les réglages.

## Aucun import Qt

Règle de couche du dépôt (`gui/__init__.py`) : tout ce qui décide se teste sans PySide6.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import parametres as par
from . import reglages as reg

#: Le fichier, à côté de `interface.json` dans le même dossier caché.
FICHIER = "profils.json"

#: Variable d'environnement qui déplace le fichier — pour les TESTS, et pour une installation
#: en lecture seule. Distincte de celle des réglages : un test qui déplace l'une ne doit pas
#: emporter l'autre sans le vouloir.
VARIABLE = "ANGELITH_PROFILS"

#: Version du format. Un fichier de version inconnue est ignoré EN BLOC, comme pour les
#: réglages : des profils perdus coûtent une resaisie, des profils à moitié lus coûtent un run
#: lancé avec des réglages que personne n'a choisis.
VERSION = 1

#: Ce qu'un profil ne porte jamais, **en plus** de ce que la table refuse déjà de persister.
#: `parametres.non_persistes()` couvre `force`, `dry_run`, `shutdown`, `page` et `graine` ;
#: ces deux-ci n'ont pas de paramètre déclaré parce qu'ils ne sont pas des réglages — ce sont
#: la cible du run. Ils sont nommés quand même : un fichier écrit à la main peut les inventer.
CIBLE: frozenset[str] = frozenset({"projet", "tome"})

#: Nombre de profils gardés. Au-delà, une liste déroulante cesse d'être un raccourci.
MAX_PROFILS = 20


@dataclass(frozen=True)
class Profil:
    """Un jeu de valeurs nommé, pour un panneau donné."""

    nom: str
    panneau: str
    valeurs: dict = field(default_factory=dict)

    def en_json(self) -> dict:
        return {"nom": self.nom, "panneau": self.panneau, "valeurs": dict(self.valeurs)}


def interdits(panneau: str) -> frozenset[str]:
    """Tout ce qu'un profil de ce panneau refuse de porter."""
    return frozenset(par.non_persistes(panneau)) | CIBLE


def nettoyer(panneau: str, valeurs: dict) -> dict:
    """Retire ce qu'un profil n'a pas le droit de porter. **Appelée à l'écriture ET à la
    lecture** — cf. le tableau des trois barrages en tête de module."""
    refuses = interdits(panneau)
    connus = {p.identifiant for p in par.pour(panneau)}
    return {cle: valeur for cle, valeur in (valeurs or {}).items()
            if cle in connus and cle not in refuses}


def chemin(racine: str | os.PathLike | None = None) -> Path:
    """Où le fichier vit. `$ANGELITH_PROFILS` l'emporte sur tout."""
    force = os.environ.get(VARIABLE)
    if force:
        return Path(force)
    # ⚠ Même défaut que `gui/reglages.py` depuis le lot 37, et par le même appel : les deux
    # fichiers vivent dans le MÊME `.angelith/`, et deux racines différentes feraient qu'une
    # installation gelée perdrait ses profils sans perdre sa disposition.
    from core.installation import dossier_reglages
    base = Path(racine) if racine is not None else dossier_reglages()
    return base / reg.DOSSIER / FICHIER


def lire(racine: str | os.PathLike | None = None) -> tuple[Profil, ...]:
    """Les profils du disque, lavés. **Ne lève jamais** — un fichier illisible rend `()`."""
    cible = chemin(racine)
    try:
        brut = json.loads(cible.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(brut, dict) or brut.get("version") != VERSION:
        return ()
    sortie = []
    for entree in (brut.get("profils") or []):
        if not isinstance(entree, dict):
            continue
        nom = str(entree.get("nom") or "").strip()
        panneau = str(entree.get("panneau") or "")
        if not nom or panneau not in par.PANNEAUX:
            continue
        valeurs = entree.get("valeurs")
        sortie.append(Profil(nom, panneau,
                             nettoyer(panneau, valeurs if isinstance(valeurs, dict) else {})))
    return tuple(sortie[:MAX_PROFILS])


def ecrire(profils, racine: str | os.PathLike | None = None) -> Path | None:
    """Écrit les profils, lavés, et rend le chemin — ou `None` si l'écriture a échoué.

    Silencieux sur échec pour la même raison que `reglages.ecrire` : un dossier en lecture
    seule ne doit pas empêcher de fermer la fenêtre, et un profil n'est pas un travail à
    protéger."""
    charge = {"version": VERSION,
              "profils": [Profil(p.nom, p.panneau,
                                 nettoyer(p.panneau, p.valeurs)).en_json()
                          for p in list(profils)[:MAX_PROFILS]]}
    cible = chemin(racine)
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(json.dumps(charge, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    except OSError:
        return None
    return cible


def pour(panneau: str, racine: str | os.PathLike | None = None) -> tuple[Profil, ...]:
    """Les profils d'un panneau, dans l'ordre du fichier.

    ⚠ Un profil est LIÉ à son panneau. « lot de 20 planches » n'a aucun sens côté light
    novel, qui ne connaît pas les planches — c'est la même raison qui a fait passer `runs`
    d'un dictionnaire plat à un dictionnaire par destination au lot 31."""
    return tuple(p for p in lire(racine) if p.panneau == panneau)


def enregistrer(nom: str, panneau: str, valeurs: dict,
                racine: str | os.PathLike | None = None) -> tuple[Profil, ...]:
    """Ajoute ou remplace un profil, et rend la liste complète après écriture.

    Le remplacement se fait sur le couple `(nom, panneau)` : deux destinations peuvent avoir
    chacune leur « nuit complète », et les confondre ferait qu'enregistrer l'un effacerait
    l'autre."""
    nom = (nom or "").strip()
    if not nom or panneau not in par.PANNEAUX:
        return lire(racine)
    garde = [p for p in lire(racine) if (p.nom, p.panneau) != (nom, panneau)]
    tous = [*garde, Profil(nom, panneau, nettoyer(panneau, valeurs))]
    ecrire(tous, racine)
    return lire(racine)


def supprimer(nom: str, panneau: str,
              racine: str | os.PathLike | None = None) -> tuple[Profil, ...]:
    """Retire un profil et rend la liste complète après écriture."""
    garde = [p for p in lire(racine) if (p.nom, p.panneau) != (nom, panneau)]
    ecrire(garde, racine)
    return lire(racine)


def resume(panneau: str, valeurs: dict) -> str:
    """Ce qu'un profil porte, en une phrase — l'infobulle de son entrée de liste.

    ⚠ Elle ne cite que ce qui S'ÉCARTE du fichier de configuration : un profil dont toutes
    les valeurs disent « selon config.yaml » ne promet rien, et l'écrire en toutes lettres
    vaut mieux que d'aligner six « selon config.yaml »."""
    propre = nettoyer(panneau, valeurs)
    morceaux = []
    for parametre in par.pour(panneau):
        if parametre.identifiant not in propre:
            continue
        valeur = propre[parametre.identifiant]
        if valeur is None or valeur == parametre.defaut:
            continue
        if parametre.genre == par.CHOIX:
            morceaux.append(f"{parametre.libelle} : {valeur}")
        elif parametre.genre == par.BASCULE:
            morceaux.append(parametre.libelle if valeur else f"sans « {parametre.libelle} »")
        else:
            morceaux.append(f"{parametre.libelle} : {valeur}{parametre.suffixe}")
    if not morceaux:
        return "Rien qui s'écarte de config.yaml."
    return " · ".join(morceaux)
