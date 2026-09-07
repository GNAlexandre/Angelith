# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que l'interface dit d'une mise à jour — **la décision et les phrases, sans Qt**.

Même partage que `gui/vue_diagnostic.py` : `core/maj.py` sait interroger, télécharger et
vérifier ; `gui/dialogues.py` sait ouvrir une fenêtre ; **ce qu'il faut proposer, et avec
quels mots, se décide ici**, donc se teste sans PySide6.

## Les quatre issues, et une seule ouvre une fenêtre

| État | Ce qui se passe au démarrage |
|---|---|
| pas de version plus récente | rien. ⚠ Y compris quand la vérification a échoué |
| une version plus récente, et l'utilisateur a dit « ne plus afficher » | rien |
| une version plus récente, installation **gelée**, assets présents | la fenêtre, avec le bouton qui installe |
| une version plus récente, **depuis les sources** ou sans asset | la fenêtre, avec un lien — rien ne s'installe |

⚠ **Un échec de vérification n'ouvre jamais rien.** Au 2026-09-06 c'est le cas nominal : le
miroir public est privé jusqu'à la candidature NLnet et l'API rend 404. Une fenêtre « je n'ai
pas pu vérifier » à chaque démarrage serait, sur une vérification désormais armée par défaut,
la seule chose que ce lot aurait livrée à tout le monde.

## « Ne plus afficher » masque la FENÊTRE, pas la capacité

`maj_silencieuse` vit dans `.angelith/interface.json`, à côté du thème et des colonnes — c'est
une préférence d'interface, et `config.yaml` reste ce qui décide si un appel réseau part. Les
deux ne se recouvrent pas :

- `config.yaml > maj.verifier: false` ⇒ **rien ne part**. C'est l'interrupteur ;
- `maj_silencieuse: true` ⇒ l'appel part toujours, la **fenêtre** ne s'ouvre plus. Le bouton
  d'« À propos » continue de marcher, et la case est réversible depuis les Réglages.

Confondre les deux ferait d'un « ne me dérange plus » un opt-out réseau silencieux, que
personne ne saurait ensuite retrouver.
"""
from __future__ import annotations

from core import maj

#: Ce que l'empreinte protège, et ce qu'elle ne protège pas. ⚠ **À l'écran, pas seulement dans
#: le code** : c'est une condition écrite du lot. Un utilisateur qui lit « empreinte vérifiée »
#: comprend « signé » s'il n'a pas lu le reste, et ce serait faux.
PHRASE_INTEGRITE = (
    "L'empreinte SHA-256 du fichier téléchargé est comparée au SHA256SUMS.txt de la même "
    "release.\n"
    "⚠ Cela détecte un téléchargement tronqué ou altéré en transit. Cela NE remplace PAS une "
    "signature de code : aucun certificat ne signe ces binaires, et le fichier d'empreintes "
    "vient de la même release que l'exécutable — donc de la même main.")

#: Pourquoi rien ne s'installe hors gel. Cf. `core/maj.installer`, qui refuse au même endroit.
PHRASE_HORS_GEL = (
    "Angelith tourne ici depuis les sources, pas depuis une installation. Lancer un installeur "
    "remplacerait cet arbre de travail par une installation : la mise à jour se fait avec "
    "« git pull ».")

#: Pourquoi rien ne s'installe quand la release ne porte pas ses fichiers. ⚠ C'est le cas de
#: **toutes** les releases publiées avant ce lot : `publication.yml` en créait sans aucun
#: fichier, et le job `artefact` téléversait des artefacts de workflow, qui n'en sont pas.
PHRASE_SANS_ASSET = (
    "Cette release ne porte pas d'installeur Windows, ou pas son fichier d'empreintes. "
    "Rien ne peut être vérifié, donc rien n'est installé : la page des releases s'ouvre.")


def silencieuse(reglages: dict | None) -> bool:
    """L'utilisateur a-t-il coché « Ne plus afficher » ? Défaut : non."""
    return bool((reglages or {}).get("maj_silencieuse", False))


def doit_proposer(resultat: maj.Resultat, reglages: dict | None = None) -> bool:
    """Ouvre-t-on la fenêtre au démarrage ?

    ⚠ **`disponible` et rien d'autre.** Ni « armé », ni « une réponse est arrivée » : une
    vérification qui a échoué ne sait pas s'il existe une version plus récente, et proposer sur
    un doute reviendrait à ouvrir une fenêtre à chaque démarrage hors ligne."""
    return bool(resultat.disponible) and not silencieuse(reglages)


def installable(resultat: maj.Resultat, *, gele: bool) -> bool:
    """Peut-on aller jusqu'à l'installation, ou seulement jusqu'au lien ?

    Trois conditions, et les trois sont nécessaires : une installation gelée, un installeur
    dans la release, et le `SHA256SUMS.txt` qui va avec. **Sans le second fichier on ne
    télécharge pas le premier** — un installeur qu'on ne peut pas vérifier ne vaut pas mieux
    qu'un lien vers la page, et il vaut moins qu'un lien, parce qu'il aurait l'air vérifié."""
    return bool(gele and resultat.installeur() is not None and resultat.sommes() is not None)


def motif_de_refus(resultat: maj.Resultat, *, gele: bool) -> str:
    """Pourquoi le bouton n'installe pas — `""` quand il installe."""
    if not gele:
        return PHRASE_HORS_GEL
    if resultat.installeur() is None or resultat.sommes() is None:
        return PHRASE_SANS_ASSET
    return ""


def _poids(octets: int) -> str:
    """« 292,1 Mio ». ⚠ Le poids est affiché AVANT le téléchargement parce qu'il en coûte
    ~115 s à 2,5 Mio/s (1 mesure, 2026-09-06) : personne ne lance ça sans le savoir."""
    if octets <= 0:
        return "poids inconnu"
    return f"{octets / 1024 / 1024:.1f} Mio".replace(".", ",")


def phrase_proposition(resultat: maj.Resultat, installee: str, *, gele: bool) -> str:
    """Le corps de la fenêtre de proposition. Il dit **tout** avant le clic : ce qui arrive, ce
    que ça pèse, ce qui est vérifié, et ce qui ne l'est pas."""
    lignes = [f"Angelith {resultat.version} est disponible (vous avez la {installee}).", ""]
    refus = motif_de_refus(resultat, gele=gele)
    if refus:
        lignes += [refus, "", f"Page des releases : {resultat.page}"]
        return "\n".join(lignes)
    fichier = resultat.installeur()
    lignes += [f"À télécharger : {fichier.nom} ({_poids(fichier.taille)}).",
               "L'installeur remplace l'installation en place ; Angelith se ferme pour le "
               "laisser faire.",
               "⚠ Tes projets, tes réglages et tes poids de modèles ne sont pas touchés — ils "
               "ne vivent pas dans le dossier d'installation.",
               "", PHRASE_INTEGRITE]
    return "\n".join(lignes)


def phrase_echec_empreinte(attendue: str, obtenue: str) -> str:
    """⚠ Ce message doit dire **ce qui a été fait du fichier**. « Empreinte invalide » tout seul
    laisse quelqu'un chercher sur son disque un installeur qu'on a déjà effacé — ou pire, le
    lancer."""
    return ("L'empreinte du fichier téléchargé ne correspond pas à celle publiée.\n"
            f"  attendue : {attendue or '(absente du SHA256SUMS.txt)'}\n"
            f"  obtenue  : {obtenue}\n"
            "Le fichier a été effacé et rien n'a été installé. Réessaie ; si l'écart persiste, "
            "récupère l'installeur depuis la page des releases et signale-le.")


def _lus(octets: int) -> str:
    """⚠ Distinct de `_poids` : ici, **zéro veut dire zéro**. `_poids(0)` rend « poids
    inconnu », ce qui est juste pour une taille que l'API n'a pas donnée et faux pour un
    téléchargement qui commence."""
    return f"{max(octets, 0) / 1024 / 1024:.1f} Mio".replace(".", ",")


def phrase_progres(lus: int, total: int) -> str:
    """« 42,3 Mio sur 292,1 Mio (14 %) ». `total` vaut `0` quand ni l'API ni l'en-tête ne l'ont
    donné : on affiche alors ce qui est lu, sans inventer de pourcentage."""
    if total <= 0:
        return f"{_lus(lus)} reçus"
    return f"{_lus(lus)} sur {_lus(total)} ({lus * 100 // total} %)"
