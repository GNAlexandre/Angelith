# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que l'endpoint LLM sait dire de ses modèles — **et surtout ce qu'il ne sait pas dire**.

## La mesure qui fonde ce module — 2026-09-05, `PLAN-33` étape 0.2

Relevé sur l'Ollama de la machine de développement, endpoint
`http://localhost:11434/v1` (réponse brute complète dans
`docs/mesures/lanceurs-2026-09-05.md` §3) :

| Question | `GET /v1/models` (OpenAI) | `GET /api/tags` (natif Ollama) |
|---|---|---|
| la liste des identifiants | **oui** — 4 modèles | oui, les mêmes |
| le modèle est-il **vision-capable** ? | **non** — le corps ne porte que `id`, `object`, `created`, `owned_by` | oui — `capabilities: ["completion", "vision"]` |
| quelle **fenêtre de contexte** ? | **non** | `details.context_length`, mais cf. l'avertissement ci-dessous |

**Trois conclusions, et elles décident du sélecteur de modèle :**

1. **l'endpoint contractuel ne dit rien d'autre que des noms.** `llm.base_url` est déclaré
   OpenAI-compatible, et LM Studio comme vLLM répondent au même schéma minimal. Tout ce qui
   dépasse la liste des noms est une information d'un serveur PARTICULIER, et doit être
   étiquetée comme telle ;
2. **la capacité vision est lisible sur Ollama, et nulle part ailleurs.** L'interface
   l'affiche quand elle la tient, affiche « capacité vision inconnue » sinon, et **ne filtre
   jamais la liste sur une devinette** — c'est le refus explicite du `PLAN-33` L33.3 ;
3. ⚠ **la fenêtre de contexte réellement SERVIE reste inconnue, même sur Ollama.**
   `details.context_length` vaut 262 144 pour les quatre modèles relevés : c'est la fenêtre
   de l'ARCHITECTURE, pas celle que le serveur sert. Le dépôt travaille à 32 768 avec
   `max_input_tokens: 24000`, et `core/power.contexte_charge` existe précisément parce
   qu'« une valeur déclarative fausse est pire qu'absente » — `config.yaml` annonçait 65 536
   quand le Modelfile en servait 32 768. Ce module rend donc `contexte_modele` (l'architecture,
   étiquetée comme telle) et **jamais** une promesse de fenêtre utile.

## ⚠ Le coût de `localhost`, mesuré le 2026-09-05

Sur cette machine Windows, contre le même serveur :

| Cible | Temps d'un `GET /v1/models` |
|---|---:|
| `http://127.0.0.1:11434/v1` | **0,003 s** (3 mesures) |
| `http://localhost:11434/v1` | **2,04 s** (3 mesures) |

Deux ordres de grandeur et demi, pour la seule résolution de `localhost` : Windows tente
`::1` d'abord, Ollama n'écoute qu'en IPv4, et l'attente est le délai d'échec de la première
tentative. Or le défaut du dépôt **est** `http://localhost:11434/v1`. C'est pourquoi le délai
de cette sonde ne peut pas être celui de `gui/sondes.py` (2,0 s, choisi pour un GET sur la
racine) : à 2,0 s contre `localhost`, la sonde de modèles tirerait à pile ou face.

Cette phrase porte sa date parce qu'elle porte une mesure d'installation : une autre machine,
un Ollama en IPv6, ou un fichier `hosts` réglé donnent un autre chiffre.

## Ce que ce module ne fait pas

- il ne **télécharge** rien. Aucun `ollama pull` n'est déclenché d'ici, ni d'ailleurs dans
  l'interface : c'est un geste d'installation, avec sa licence et sa taille, et c'est le
  `PLAN-36` L36.2 ;
- il n'écrit **rien** dans `config.yaml`. `outrepasser()` mute un dictionnaire déjà chargé,
  exactement comme un drapeau de ligne de commande ;
- il ne **génère** rien. `core.llm.test_connection` fait une vraie génération en trente
  secondes, derrière une entrée de menu ; ici on ne fait qu'un GET.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

#: Les trois états d'un catalogue, alignés sur `gui/sondes.py` — et le troisième n'est pas une
#: commodité : c'est l'état réel tant que la sonde n'a pas rendu.
JOIGNABLE = "joignable"
INJOIGNABLE = "injoignable"
INCONNU = "inconnu"

#: Délai d'attente, en secondes. **Trois fois celui de `gui/sondes.py`**, et le motif est
#: mesuré : `localhost` coûte 2,04 s sur cette machine avant même que le serveur réponde
#: (cf. l'avertissement du module). Un budget de 2,0 s ferait échouer la sonde contre un
#: serveur parfaitement sain.
DELAI = 6.0

#: Ce qu'on affiche quand on ne sait pas. Une chaîne, pas un `None` : elle atterrit telle
#: quelle dans une liste déroulante, et « inconnu » y est une réponse, pas un trou.
VISION_INCONNUE = "inconnu"


@dataclass(frozen=True)
class Modele:
    """Un modèle tel que le serveur le nomme, et ce qu'on a pu en apprendre.

    `identifiant` — le nom exact, celui qu'on écrira dans la spec d'un agent.
    `vision` — `True`, `False`, ou `None` = **inconnu**. Trois états, jamais deux : un
    `False` par défaut ferait dire à l'interface qu'un modèle n'est pas vision-capable alors
    qu'on ne le lui a pas demandé.
    `contexte_modele` — la fenêtre de l'ARCHITECTURE, en tokens, ou `None`. ⚠ Ce n'est PAS la
    fenêtre servie (cf. l'avertissement du module).
    `source` — d'où vient l'enrichissement, pour que l'infobulle puisse le dire.
    """

    identifiant: str
    vision: bool | None = None
    contexte_modele: int | None = None
    source: str = ""

    @property
    def vision_lisible(self) -> str:
        if self.vision is None:
            return VISION_INCONNUE
        return "oui" if self.vision else "non"

    def ligne(self) -> str:
        """Une ligne prête à afficher dans une liste déroulante."""
        return f"{self.identifiant}  —  vision : {self.vision_lisible}"


@dataclass(frozen=True)
class Catalogue:
    """Le verdict d'une interrogation d'endpoint. `detail` dit ce qu'on a regardé."""

    etat: str
    modeles: tuple[Modele, ...] = ()
    detail: str = ""
    #: Secondes qu'a coûté l'interrogation. Publié plutôt que caché : c'est le chiffre qui a
    #: décidé de `DELAI`, et il change d'une installation à l'autre.
    duree: float = 0.0

    def par_identifiant(self, identifiant: str) -> Modele | None:
        for modele in self.modeles:
            if modele.identifiant == identifiant:
                return modele
        return None

    def phrase(self) -> str:
        """Ce que l'interface écrit sous la liste. Une phrase, jamais un code d'erreur nu."""
        if self.etat == JOIGNABLE:
            inconnus = sum(1 for m in self.modeles if m.vision is None)
            fin = (f" — capacité vision inconnue pour {inconnus} d'entre eux"
                   if inconnus else "")
            return f"{len(self.modeles)} modèle(s) sur {self.detail}{fin}."
        if self.etat == INJOIGNABLE:
            return (f"Endpoint injoignable ({self.detail}) — les modèles de config.yaml "
                    f"restent en place.")
        return "Liste des modèles non encore demandée."


def inconnu() -> Catalogue:
    """Le catalogue AVANT toute interrogation. C'est ce que le panneau affiche au premier
    pixel, et c'est vrai."""
    return Catalogue(INCONNU)


def racine(base_url: str) -> str:
    """`http://hôte:11434/v1` → `http://hôte:11434`. Même calcul que
    `core/power.racine_ollama`, dont ce module ne dépend pas pour ne pas tirer `subprocess`."""
    url = (base_url or "").rstrip("/")
    return url[:-3].rstrip("/") if url.endswith("/v1") else url


def _lire_json(url: str, delai: float):
    with urllib.request.urlopen(url, timeout=delai) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def lister(base_url: str, *, delai: float = DELAI, enrichir: bool = True) -> Catalogue:
    """`GET <base_url>/models`, et rien d'autre. **Ne lève jamais.**

    `enrichir` tente ensuite `GET <racine>/api/tags`, l'API native d'Ollama, pour la capacité
    vision. ⚠ Cet appel-là est **facultatif par construction** : un serveur qui n'est pas
    Ollama rend 404, et la liste reste complète avec des capacités « inconnu ». C'est la
    règle du `PLAN-33` L33.3 — « ce que la sonde ne sait pas décider, l'interface l'affiche
    comme inconnu, elle ne le devine pas »."""
    url = (base_url or "").rstrip("/") + "/models"
    debut = time.perf_counter()
    try:
        charge = _lire_json(url, delai)
    except Exception as err:                     # noqa: BLE001 — tout échec = injoignable
        return Catalogue(INJOIGNABLE, (), f"{url} — {type(err).__name__}",
                         time.perf_counter() - debut)
    identifiants = [str(e.get("id")) for e in (charge.get("data") or []) if e.get("id")]
    capacites = _capacites(base_url, delai) if enrichir else {}
    modeles = tuple(
        Modele(nom,
               vision=capacites.get(nom, (None, None, ""))[0],
               contexte_modele=capacites.get(nom, (None, None, ""))[1],
               source=capacites.get(nom, (None, None, ""))[2])
        for nom in identifiants)
    return Catalogue(JOIGNABLE, modeles, url, time.perf_counter() - debut)


def _capacites(base_url: str, delai: float) -> dict[str, tuple[bool | None, int | None, str]]:
    """`{identifiant: (vision, contexte du modèle, source)}`, depuis l'API native d'Ollama.

    Rend un dictionnaire VIDE dès que le serveur n'est pas un Ollama, ce qui laisse toutes les
    capacités à « inconnu ». C'est l'issue attendue sur LM Studio, vLLM ou llama.cpp — et
    l'interface doit s'y comporter exactement comme sur une machine sans Ollama."""
    try:
        charge = _lire_json(f"{racine(base_url)}/api/tags", delai)
    except Exception:                            # noqa: BLE001 — pas d'Ollama, pas de capacités
        return {}
    sortie: dict[str, tuple[bool | None, int | None, str]] = {}
    for entree in (charge.get("models") or []):
        nom = str(entree.get("name") or entree.get("model") or "")
        if not nom:
            continue
        capacites = entree.get("capabilities")
        # ⚠ `capabilities` absent ≠ « pas de vision » : un Ollama antérieur au champ ne le
        # renvoie pas. On rend alors `None`, c'est-à-dire « inconnu ».
        vision = ("vision" in capacites) if isinstance(capacites, list) else None
        details = entree.get("details") or {}
        contexte = details.get("context_length")
        sortie[nom] = (vision, int(contexte) if contexte else None, "Ollama /api/tags")
    return sortie


# --------------------------------------------------------------------------- #
#  L'outrepassement — en mémoire, et il NOMME ce qu'il change
# --------------------------------------------------------------------------- #

def agents(config: dict, section: str | None) -> dict:
    """Le bloc `modeles:` d'une brique. Même lecture que `core.cli.models_in_config`."""
    racine_ = config if section is None else (config.get(section) or {})
    return racine_.get("modeles") or {}


def outrepasser(config: dict, section: str | None,
                modele: str) -> tuple[tuple[str, str, str], ...]:
    """Remplace le `model:` de tous les agents d'une brique. **Mute `config`.**

    Rend `((agent, avant, après), …)` — ce que le récapitulatif de lancement affiche. Un run
    qui ne tourne pas sur le modèle de `config.yaml` doit le dire AVANT, pas après.

    ⚠ **L'`endpoint:` est conservé, et c'est tout l'enjeu.** Le dépôt déclare des agents sous
    la forme `{model: "yume-27b", endpoint: "reflexion"}` : remplacer la spec entière par une
    chaîne désactiverait silencieusement l'endpoint de raisonnement, ce qui est exactement le
    piège que le commentaire de `--think` documente depuis le lot 18. On ne touche donc qu'à
    une clé.

    ⚠ **Un agent à `null` reste à `null`.** `config.yaml` livre `correcteur: null`, ce qui
    veut dire « cet agent ne tourne pas » : lui poser un modèle l'allumerait, et un
    sélecteur de modèle n'a pas le droit d'ajouter une étape au pipeline."""
    bloc = agents(config, section)
    change: list[tuple[str, str, str]] = []
    for nom, spec in list(bloc.items()):
        if spec is None:
            continue
        if isinstance(spec, dict):
            avant = str(spec.get("model") or "")
            if avant == modele:
                continue
            spec["model"] = modele
        else:
            avant = str(spec)
            if avant == modele:
                continue
            # Une spec-chaîne devient une spec-chaîne : la promouvoir en dictionnaire
            # ajouterait des clés que personne n'a demandées.
            bloc[nom] = modele
        change.append((nom, avant, modele))
    return tuple(change)


def outrepasser_endpoint(config: dict, section: str | None,
                         base_url: str) -> tuple[str, str] | None:
    """Remplace l'adresse du serveur LLM d'une brique. **Mute `config`.**

    Rend `(avant, après)`, ou `None` si rien n'a changé — c'est ce que le récapitulatif de
    lancement et la page de préférences affichent. Un run qui ne parle pas au serveur de
    `config.yaml` doit le dire AVANT, pas après.

    ## ⚠ Ce que cette fonction NE fait PAS

    Elle n'écrit **rien** dans `config.yaml`. Même patron que `outrepasser` ci-dessus, et même
    motif : le fichier est un document de 158 Ko dont la prose commentée est la documentation
    (interdit 5 du contexte agent), et un aller-retour `yaml.safe_dump` l'effacerait. Ce qui est
    réglé depuis l'interface vaut pour CETTE installation et vit dans
    `.angelith/interface.json` ; le fichier reste la référence partagée — c'est la doctrine que
    `gui/dialogues.py:DialoguePreferences` écrit déjà pour le plafond de cache.

    ⚠ **Une valeur vide ne fait rien.** `None` et `""` veulent dire « s'en remettre à
    `config.yaml` », pas « efface l'adresse » : c'est la règle des trois états de
    `gui/parametres.py`, et sans elle un champ laissé vide couperait le serveur au lieu de ne
    pas le toucher.

    ⚠ **`section` décide de la portée.** `None` règle la racine (donc le light novel et le
    défaut hérité) ; `"manga"` ne règle que la brique manga, dont `core/config.py` fait un
    héritage profond. C'est ce qui permet de pointer la brique manga sur une seconde machine
    sans toucher au reste.
    """
    if not base_url or not str(base_url).strip():
        return None
    base_url = str(base_url).strip()
    bloc = config
    if section:
        bloc = config.setdefault(section, {})
        if not isinstance(bloc, dict):               # pragma: no cover — config malformée
            return None
    llm = bloc.setdefault("llm", {})
    if not isinstance(llm, dict):                    # pragma: no cover — config malformée
        return None
    avant = str(llm.get("base_url") or "")
    if avant == base_url:
        return None
    llm["base_url"] = base_url
    return (avant, base_url)
