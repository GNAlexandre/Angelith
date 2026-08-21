# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Héritage de configuration entre la racine de `config.yaml` et une brique.

`config.yaml` garde sa forme : les réglages du light novel à la racine, ceux du manga sous
`manga:`. On n'ajoute que la **sémantique d'héritage**. Un découpage en
`defauts:`/`ln:`/`manga:` toucherait le README, les listes `required` des deux doctors,
`app.py` et les helpers `_base_config()` de la plupart des tests, pour un gain purement
cosmétique.

## Le piège que ça corrige

`mcfg.get("llm") or config["llm"]` est du **tout-ou-rien** : dès qu'une brique définit son
propre bloc `llm:`, il REMPLACE celui de la racine. Décommenter le bloc `manga.llm` de
`config.yaml` pour n'y régler qu'un `thinking_budget` faisait donc perdre `llm.endpoints`,
`extra_directive`, et tout ce qui n'y était pas recopié — silencieusement, avec un run qui
démarre normalement. Le fichier avait fini par *documenter* le piège (« ⚠ TOUT-OU-RIEN :
il faut donc y recopier base_url/api_key/timeout ») plutôt que de le corriger.

Même chose, moins visible, pour `manga.chemins` : il recopiait `sources` et `build` de la
racine, avec le commentaire « même racine que le LN ». Deux copies qu'il fallait penser à
changer ensemble — modifier la seule racine faisait écrire la brique manga à l'ancien
endroit, sans un mot.

## Pourquoi l'héritage est OPT-IN, bloc par bloc

`section()` prend la clé en paramètre au lieu de fusionner toute la section : hériter
partout serait faux. La racine et le manga ont tous deux un bloc `rendu:`, mais ils ne
parlent pas de la même chose — `reference_docx`, `epub_css`, `pdf_engine` d'un côté, sens
de lecture et qualité JPEG de l'autre. Les fusionner ferait entrer dans le rendu manga des
clés qui n'y ont aucun sens. Seuls `llm` et `chemins` sont réellement les *mêmes* réglages
vus par deux briques ; c'est là, et là seulement, que l'héritage s'applique.
"""
from __future__ import annotations


def deep_merge(base: dict, surcouche: dict) -> dict:
    """Fusion profonde : la `surcouche` gagne feuille par feuille, sans écraser les
    branches voisines. Ne modifie ni l'un ni l'autre.

    Deux règles à ne pas confondre, parce qu'elles portent toutes deux sur `None` :

    - une **liste** remplace, elle ne se concatène pas. Une liste de `config.yaml` est une
      énumération complète (`formats`, `providers`, `couleur_texte_sombre`) ; concaténer
      rendrait impossible d'en RETIRER un élément dans la brique ;
    - une **valeur nulle** de la surcouche gagne aussi — parce que `None` est une valeur
      utile ici et pas seulement « absent » : `think: null` signifie « laisse le défaut du
      modèle », distinct de `think: false` (« pas de raisonnement »), et c'est ainsi que
      `core.llm.LLM` le traite (rien envoyé / `reasoning_effort: none`). Sans cette règle,
      une brique ne pourrait pas revenir au défaut du modèle quand la racine impose
      `false`.

      **Sauf** quand la valeur de base est un dictionnaire : `manga:\\n  llm:` (bloc écrit
      puis laissé vide) donne `None` en YAML et n'a jamais voulu dire « efface tous les
      réglages LLM de la racine ». On hérite alors du sous-arbre.
    """
    if not isinstance(base, dict) or not isinstance(surcouche, dict):
        return surcouche
    out = dict(base)
    for cle, val in surcouche.items():
        ancien = out.get(cle)
        if val is None and isinstance(ancien, dict):
            continue                                  # sous-arbre nul = accident YAML
        if isinstance(val, dict) and isinstance(ancien, dict):
            out[cle] = deep_merge(ancien, val)
        else:
            out[cle] = val
    return out


def section(config: dict, nom: str | None, cle: str) -> dict:
    """Bloc `cle` tel que le voit la brique `nom`, hérité de la racine par fusion profonde.

    `nom=None` (light novel, réglages à la racine) rend simplement une copie du bloc racine
    — la brique de référence n'hérite de personne."""
    racine = config.get(cle) or {}
    if nom is None:
        return dict(racine)
    propre = (config.get(nom) or {}).get(cle) or {}
    return deep_merge(racine, propre)


def origine(config: dict, nom: str | None, cle: str) -> str:
    """Où l'utilisateur doit aller éditer ce bloc — `llm` ou `manga.llm`. Sert aux messages
    d'erreur : envoyer quelqu'un corriger `llm.endpoints` alors que sa brique a son propre
    bloc (donc que c'est *celui-là* qui compte pour la clé fautive) fait perdre du temps."""
    if nom is None or not (config.get(nom) or {}).get(cle):
        return cle
    return f"{nom}.{cle}"


# --------------------------------------------------------------------------- #
#  Verification des cles
# --------------------------------------------------------------------------- #

def chemins_de(config: dict, libres=None, prefixe: str = ""):
    """Tous les chemins pointés d'un dictionnaire de configuration, en profondeur."""
    from .config_schema import CLES_LIBRES
    libres = CLES_LIBRES if libres is None else libres
    if not isinstance(config, dict):
        return
    for cle, valeur in config.items():
        chemin = f"{prefixe}{cle}"
        yield chemin
        # Sous un bloc libre, les noms viennent de l'utilisateur : on s'arrête là.
        if chemin not in libres:
            yield from chemins_de(valeur, libres, chemin + ".")


def _suggestion(inconnue: str, connues) -> str | None:
    """La clé connue la plus proche, s'il y en a une franchement proche.

    Nommer le coupable probable vaut mieux que dire « inconnue » : la faute de frappe qu'on
    cherche est presque toujours à une lettre de la bonne clé."""
    import difflib
    proches = difflib.get_close_matches(inconnue, connues, n=1, cutoff=0.85)
    return proches[0] if proches else None


def verifier(config: dict, *, connues=None, libres=None) -> list[str]:
    """Avertissements sur les clés que `config.yaml` ne reconnaît pas.

    ⚠ **Avertit, ne refuse jamais.** Le code lit sa configuration à travers 603 `.get(...)`
    à défaut silencieux : écrire `manga.typeset.font_paht` laisse le run se dérouler
    entièrement avec la police par défaut, sans un mot, et rien ne le rattrape après coup.
    C'est ce silence-là qu'on casse, pas le droit de l'utilisateur à lancer son run."""
    from .config_schema import CLES_CONNUES, CLES_LIBRES
    connues = CLES_CONNUES if connues is None else connues
    libres = CLES_LIBRES if libres is None else libres
    avertissements: list[str] = []

    def parcourir(bloc, prefixe: str = "") -> None:
        """⚠ On **s'arrête** à la première clé inconnue au lieu de descendre dedans.

        Sans cet élagage, coller un bloc entier qui n'a rien à faire là sortait un
        avertissement par feuille — quatre lignes pour `inconnu: {a, b: {c}}` — et le vrai
        message, celui qui nomme la faute de frappe, défilait au milieu du bruit."""
        if not isinstance(bloc, dict):
            return
        for cle, valeur in bloc.items():
            chemin = f"{prefixe}{cle}"
            if chemin not in connues:
                proche = _suggestion(chemin, connues)
                avertissements.append(
                    f"clé inconnue : {chemin}"
                    + (f" — vouliez-vous dire {proche} ?" if proche else ""))
                continue
            if chemin not in libres:
                parcourir(valeur, chemin + ".")

    parcourir(config or {})
    return sorted(avertissements)
