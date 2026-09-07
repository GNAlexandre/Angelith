# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Deux gardes de chemin, partagées par le socle et les outils.

## Ce qu'elles corrigent

Sonar signale, sur quatre points du dépôt, des chemins « construits à partir de données
contrôlées par l'utilisateur » (`pythonsecurity:S2083`, `S8705`, `S8707`). La donnée en
question est presque toujours un **nom d'œuvre** ou un **chemin de configuration** tapé en
ligne de commande, et le programme tourne sur la machine de celui qui l'a tapé : le scénario
d'attaque classique — un tiers qui fournit l'entrée — n'existe pas ici.

Ce n'est pas pour autant du bruit. Deux défauts réels se cachaient derrière :

1. **Un chemin dérivé n'était jamais vérifié.** `glossaire.yaml` → sa sauvegarde,
   `bloc.md` → son fichier temporaire : la construction (`with_name`, `with_suffix`) ne peut
   pas sortir du dossier, mais rien ne l'ÉCRIVAIT, donc rien ne le garderait après une
   réécriture. `derive` transforme cette propriété implicite en invariant vérifié.

2. **`exists()` était pris pour « c'est un fichier ».** Un dossier passe `exists()`, et le
   `read_bytes()` qui suit lève un `IsADirectoryError` — ou, sous Windows, un
   `PermissionError` qui ne nomme rien. `fichier_lisible` échoue à l'endroit où l'on sait
   encore quoi dire.

⚠ Aucune de ces deux fonctions ne prétend faire un bac à sable. Elles suppriment une classe
d'erreur et rendent une intention lisible ; elles ne remplacent pas les droits du système de
fichiers, et le dire vaut mieux que de laisser croire le contraire.
"""
from __future__ import annotations

from pathlib import Path


def derive(chemin: str | Path, suffixe: str) -> Path:
    """Un fichier FRÈRE de `chemin`, dont le nom est celui de `chemin` suivi de `suffixe`.

    `derive("sources/X/glossaire.yaml", ".bak")` → `sources/X/glossaire.yaml.bak`.

    ⚠ `suffixe` est un SUFFIXE DE NOM, pas un morceau de chemin : un séparateur, un `..` ou
    un chemin absolu sont refusés. C'est là tout l'intérêt — l'appelant écrit une constante,
    mais une constante se retouche, et « ajouter une extension » ne doit jamais pouvoir
    devenir « écrire ailleurs ».
    """
    base = Path(chemin)
    if not suffixe or suffixe.strip() != suffixe:
        raise ValueError(f"suffixe vide ou mal cadré : {suffixe!r}")
    interdits = ("/", "\\", "\x00")
    if any(c in suffixe for c in interdits) or suffixe == ".." or suffixe.startswith(".."):
        raise ValueError(
            f"suffixe {suffixe!r} : un séparateur ou un « .. » ferait sortir du dossier de "
            f"{base.name}, alors que la fonction promet un fichier frère.")
    voisin = base.with_name(base.name + suffixe)
    if voisin.parent != base.parent or voisin.name == base.name:
        raise ValueError(f"{voisin} n'est pas un frère distinct de {base}")
    return voisin


def segment(nom: str, quoi: str) -> str:
    """`nom` s'il peut devenir **UN** composant de chemin ; sinon un `ValueError` qui le dit.

    Un nom d'œuvre ou de tome désigne un dossier *directement* sous `sources/` ou `build/` :
    « roman Q », « Vol.1 ». Il n'a jamais à contenir de séparateur, de `..`, de lettre de
    lecteur ni d'octet nul.

    ⚠ Ce n'est pas un bac à sable, et la menace n'est pas un attaquant : le nom vient de la
    ligne de commande de celui qui lance le programme. C'est un garde-fou contre la FAUTE DE
    FRAPPE — un `sources/Mon LN/../autre` collé depuis un explorateur de fichiers écrirait la
    sauvegarde du glossaire ailleurs que là où l'utilisateur croit, et un glossaire est du
    travail humain accumulé sur plusieurs tomes. C'est aussi ce qui rompt la chaîne que
    l'analyse de teinte suit du `sys.argv` jusqu'à l'écriture (`pythonsecurity:S2083`).
    """
    if not isinstance(nom, str) or not nom.strip():
        raise ValueError(f"{quoi} : nom vide.")
    nom = nom.strip()
    if nom in (".", "..") or any(c in nom for c in ("/", "\\", "\x00")):
        raise ValueError(
            f"{quoi} « {nom} » n'est pas un nom de dossier : il contient un séparateur de "
            f"chemin ou un « .. ». Un projet est un dossier DIRECTEMENT sous sources/ — "
            f"donne son nom seul, pas un chemin vers lui.")
    if Path(nom).name != nom:
        raise ValueError(f"{quoi} « {nom} » ne se réduit pas à un nom de dossier.")
    return nom


def fichier_lisible(chemin: str | Path, quoi: str) -> Path:
    """`chemin` s'il désigne un FICHIER régulier existant ; sinon un `RuntimeError` qui dit
    lequel et pourquoi.

    ⚠ `is_file()` et non `exists()`. Un dossier existe, et c'est l'erreur que la suite
    produisait : `read_bytes()` sur un dossier lève un `IsADirectoryError` sous Linux et un
    `PermissionError` sous Windows — deux messages qui ne nomment ni le fichier ni ce qu'on
    en attendait. `quoi` sert à le nommer ici, où on le sait encore.
    """
    p = Path(chemin)
    if not p.exists():
        raise RuntimeError(f"{quoi} introuvable : {p}")
    if not p.is_file():
        raise RuntimeError(f"{quoi} : {p} existe mais n'est pas un fichier.")
    return p
