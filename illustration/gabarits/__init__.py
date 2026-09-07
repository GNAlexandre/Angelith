# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les gabarits du modèle d'image — **la syntaxe d'un modèle, pas la voix d'un tome**.

## Pourquoi ce dossier existe à côté de `langues/<code>/prompts/`

Le `PLAN-26` L26.1 pose la séparation, et elle n'est pas cosmétique :

| | `langues/<code>/prompts/` | `illustration/gabarits/` |
|---|---|---|
| destinataire | le **LLM local** (`yume-27b`) | le **modèle d'image** (`Qwen-Image-Edit-2511`) |
| ce qui s'y périme | quand la voix d'un tome change | quand le modèle d'image change |
| garantie attendue | `git checkout <tag> -- langues/` reproduit un tome | rien : le modèle bouge tous les deux mois |
| dépend de la langue de traduction ? | **oui, par construction** | non — le modèle est multilingue |

Mélanger les deux ferait dépendre la reproduction d'un tome de la version d'un modèle
d'image, ce qui n'a aucun sens : la voix d'une traduction ne change pas parce qu'un
générateur d'images a sorti une révision.

## Ce qu'un gabarit porte, et ce qu'il ne porte pas

Il porte **la forme du texte** : les mots de sujet accordés, les phrases de cadrage, la
manière dont un attribut cité devient un fragment, la désignation en prose des images de
référence, et le **prompt négatif avec le motif de chaque terme**.

Il ne porte **aucun attribut d'apparence** : ceux-là viennent de `bible.yaml`, mot pour mot,
et de nulle part ailleurs. C'est le critère 4 du `PLAN-26`, et `illustration/prompt.py` est
l'endroit où il est tenu.

⚠ **Un gabarit n'est pas non plus un workflow.** `illustration/workflows/*.api.json` décrit
le GRAPHE — quels poids, combien de pas, quels nœuds ; le gabarit décrit le TEXTE qu'on y
verse. Les deux se périment ensemble mais ne se lisent pas au même moment : le graphe est lu
par le moteur, le gabarit par la phase 1, avant qu'un seul octet de poids soit chargé.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

#: Nom du gabarit livré. Un seul aujourd'hui, et le périmètre arrêté le justifie : « un
#: personnage seul, reconnaissable d'une image à l'autre ». Une scène est un `PLAN-28`.
DEFAUT = "portrait"

#: Les trois formes du champ texte mises en concurrence par l'étape 0.3 du `PLAN-26`.
#:
#: - `"prose"` — une phrase suivie, telle que la discussion amont de `Qwen-Image-Edit-2511`
#:   la recommande (« il utilise un LLM comme CLIP, parlez-lui en langage naturel ») ;
#: - `"categories"` — des catégories étiquetées (Sujet, Cadrage, Apparence…), telles qu'un
#:   guide communautaire de `Qwen-Image-2512` les recommande ;
#: - `"json"` — le même contenu sérialisé en JSON dans le champ texte.
#:
#: ⚠ **Aucune de ces trois formes n'est meilleure par principe**, et les deux sources
#: communautaires se contredisent **sans dénominateur ni corpus**. Le « +30 % de précision »
#: annoncé par l'une n'est recopié nulle part dans ce dépôt comme un fait : c'est
#: l'affirmation d'un article de blog. La réponse de ce dépôt est mesurée sur son corpus,
#: publiée avec son dénominateur, et **elle ne vaut que pour lui**.
FORMES = ("prose", "categories", "json")

#: Le décor employé quand `requete.yaml` n'en nomme aucun. **Inchangé par le lot 29**, et
#: c'est le point : le `PLAN-29` L29.4 soupçonne « sur fond neutre » d'être une régression que
#: le dépôt s'est infligée — la part d'aplats de l'image générée vaut 0,6300 contre 0,3669
#: pour le tome — mais aucune mesure ne désigne encore un remplaçant. Le levier est livré,
#: **la valeur ne bouge pas** : c'est la même règle que `manga.onomatopees.effacement.mode`
#: au lot 22 et que `illustration.vram.decharger_image` au lot 24, « on livre désarmé ce que
#: la mesure ne soutient pas ».
DECOR_DEFAUT = "neutre"

#: Langues dans lesquelles un gabarit sait écrire. Ce n'est PAS la langue de traduction :
#: c'est la langue du texte envoyé au modèle d'image, et laquelle marche le mieux est une
#: mesure (critère 7 du `PLAN-26`), pas une évidence.
LANGUES = ("fr", "en")


class GabaritIntrouvable(RuntimeError):
    """Le gabarit demandé n'existe pas, ou ne parle pas la langue demandée."""


@dataclass(frozen=True)
class Gabarit:
    """Un gabarit résolu pour UNE langue. Gelé : il est lu une fois et partagé."""

    nom: str
    version: int
    langue: str
    sujets: dict
    cadrages: dict
    attributs: dict
    etiquettes: dict
    #: Le décor du défaut — celui de `DECOR_DEFAUT`. Gardé comme champ (et non calculé) parce
    #: qu'il est lu partout et qu'un gabarit d'avant le lot 29 n'a que celui-là.
    decor: str
    #: `{nom: phrase}` — les variantes de décor du `PLAN-29` L29.4. Un gabarit sans bloc
    #: `decors` en reçoit une seule, `neutre`, construite depuis `decor` : un gabarit tiers
    #: écrit avant ce lot continue de marcher, et il n'a alors qu'une variante à balayer.
    decors: dict
    registre: dict
    designation_une: str
    designation_plusieurs: str
    ancrage_une: str
    ancrage_plusieurs: str
    image_n: str
    mots_attribut: tuple
    #: `[{terme, motif}]` — le terme dans CETTE langue, le motif toujours en français
    #: (c'est de la documentation pour l'utilisateur, pas du texte pour le modèle).
    negatif: tuple

    # ------------------------------------------------------------------ #

    def sujet(self, genre: str) -> str:
        """Le sujet accordé. `genre` vient de `bible.genre_confirme`, et il est souvent vide —
        sur le corpus réel, **0 personnage sur 11** le porte. L'abstention est le défaut."""
        return self.sujets.get(str(genre or "").strip() or "inconnu") or self.sujets["inconnu"]

    def cadrage(self, nom: str) -> str:
        """La phrase de cadrage. ⚠ Un cadrage inconnu lève : il vient d'un champ que
        l'utilisateur édite à la main dans `requete.yaml`, et une faute de frappe qui
        retomberait en silence sur « buste » produirait une image que personne n'a demandée."""
        phrase = self.cadrages.get(str(nom or "").strip())
        if phrase is None:
            raise GabaritIntrouvable(
                f"cadrage « {nom} » inconnu du gabarit « {self.nom} ».\n"
                f"  Valeurs possibles : {', '.join(sorted(self.cadrages))}.\n"
                f"  Ce champ est édité à la main dans requete.yaml : une faute de frappe qui "
                f"retomberait en silence sur un autre cadrage produirait une image que "
                f"personne n'a demandée.")
        return phrase

    def decor_de(self, nom: str = "") -> str:
        """La phrase de décor d'une variante. ⚠ Une variante inconnue **lève**, exactement
        comme `cadrage` : le champ est édité à la main dans `requete.yaml`, et une faute de
        frappe qui retomberait en silence sur « neutre » produirait l'image que le lot 29
        cherche précisément à comparer à une autre.

        `""` rend le décor par défaut — c'est le comportement d'avant ce lot, mot pour mot."""
        nom = str(nom or "").strip()
        if not nom:
            return self.decor
        if nom not in self.decors:
            raise GabaritIntrouvable(
                f"décor « {nom} » inconnu du gabarit « {self.nom} ».\n"
                f"  Valeurs possibles : {', '.join(sorted(self.decors))}.\n"
                f"  ⚠ Le PLAN-29 L29.4 met ces variantes en concurrence : « sur fond neutre » "
                f"demande une grande surface d'une seule teinte, et la part d'aplats de "
                f"l'image générée (0,6300) dépasse celle du tome (0,3669). Une faute de "
                f"frappe qui retomberait en silence sur « neutre » annulerait la mesure.")
        return self.decors[nom]

    def prompt_negatif(self) -> str:
        """Le prompt négatif de cette langue, termes séparés par des virgules."""
        return ", ".join(n["terme"] for n in self.negatif)

    def motifs_negatifs(self) -> dict:
        """`{terme: motif}` — ce que `requete.yaml` et le rapport montrent à l'utilisateur.

        Sans lui, « retirer un terme est un choix, pas une faute » n'est pas praticable : on
        ne choisit pas de retirer ce dont on ignore la raison."""
        return {n["terme"]: n["motif"] for n in self.negatif}

    def designation(self, nombre: int) -> str:
        """La désignation en prose de `nombre` images de référence d'IDENTITÉ. `""` si aucune.

        Elles sont toujours les premières du canal : `image 1` … `image n`."""
        return self._designer(1, int(nombre), self.designation_une,
                              self.designation_plusieurs)

    def designation_ancrages(self, debut: int, nombre: int) -> str:
        """La désignation des ancres de STYLE, qui suivent les références dans le canal.

        ⚠ **Séparée, et c'est la règle 0 du `PLAN-26` L26.0.** `references` et
        `ancrages_style` sont deux usages du même canal d'images ; le canal ne sait pas les
        distinguer, le texte si. Une ancre branchée mais désignée comme une référence
        d'identité ferait entrer le personnage de l'ancre dans l'image produite — c'est la
        contamination d'identité que l'étape 0.2 nomme."""
        return self._designer(int(debut), int(nombre), self.ancrage_une,
                              self.ancrage_plusieurs)

    def _designer(self, debut: int, nombre: int, une: str, plusieurs: str) -> str:
        if nombre <= 0:
            return ""
        images = ", ".join(self.image_n.format(n=i)
                           for i in range(debut, debut + nombre))
        return (une if nombre == 1 else plusieurs).format(images=images)


def racine() -> Path:
    """Le dossier des gabarits livrés.

    ⚠ Passe par `installation.ressource` depuis la 2.31.0 (`PLAN-37` L37.3) : gelés, ces YAML
    sont dépaquetés sous `sys._MEIPASS`. Hors gel, le chemin rendu est celui d'avant."""
    from core.installation import ressource
    return ressource("illustration", "gabarits")


def disponibles() -> list[str]:
    return sorted(p.stem for p in racine().glob("*.yaml"))


#: Les gabarits sont des fichiers de données immuables du dépôt : les relire à chaque
#: personnage d'un run de huit images serait payer un `yaml.safe_load` pour rien.
_CACHE: dict = {}


def charger(nom: str = DEFAUT, *, langue: str = "fr") -> Gabarit:
    """Le gabarit `nom` dans la langue `langue`.

    ⚠ **Une langue absente lève, elle ne retombe pas sur le français.** C'est la règle de
    `core/langues.py`, mot pour mot : « aucun repli silencieux vers le français ». Un repli
    ici produirait une image dont le prompt n'est pas dans la langue mesurée, et fausserait
    la seule chose que le critère 7 demande de comparer."""
    cle = (str(nom or DEFAUT), str(langue or "fr"))
    if cle in _CACHE:
        return _CACHE[cle]
    chemin = racine() / f"{cle[0]}.yaml"
    if not chemin.is_file():
        raise GabaritIntrouvable(
            f"gabarit « {cle[0]} » introuvable ({chemin}).\n"
            f"  Gabarits livrés : {', '.join(disponibles()) or '(aucun)'}.")
    brut = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    par_langue = (brut.get("langues") or {}).get(cle[1])
    if not par_langue:
        raise GabaritIntrouvable(
            f"le gabarit « {cle[0]} » ne parle pas « {cle[1] }».\n"
            f"  Langues qu'il porte : {', '.join(sorted(brut.get('langues') or {}))}.\n"
            f"  Aucun repli vers le français n'a lieu : le prompt partirait dans une langue "
            f"autre que celle demandée, et c'est exactement ce que le critère 7 du PLAN-26 "
            f"cherche à comparer.")
    gabarit = Gabarit(
        nom=cle[0], version=int(brut.get("version") or 1), langue=cle[1],
        sujets=dict(par_langue.get("sujets") or {}),
        cadrages=dict(par_langue.get("cadrages") or {}),
        attributs=dict(par_langue.get("attributs") or {}),
        etiquettes=dict(par_langue.get("etiquettes") or {}),
        decor=str(par_langue.get("decor") or ""),
        decors=_decors(par_langue),
        registre=dict(par_langue.get("registre") or {}),
        designation_une=str(par_langue.get("designation_une") or ""),
        designation_plusieurs=str(par_langue.get("designation_plusieurs") or ""),
        ancrage_une=str(par_langue.get("ancrage_une") or ""),
        ancrage_plusieurs=str(par_langue.get("ancrage_plusieurs") or ""),
        image_n=str(par_langue.get("image_n") or "{n}"),
        mots_attribut=tuple(str(m).casefold() for m in
                            (par_langue.get("mots_attribut") or [])),
        negatif=tuple({"terme": str((n.get("terme") or {}).get(cle[1]) or ""),
                       "motif": " ".join(str(n.get("motif") or "").split())}
                      for n in (brut.get("negatif") or [])
                      if isinstance(n, dict) and (n.get("terme") or {}).get(cle[1])))
    _CACHE[cle] = gabarit
    return gabarit


def _decors(par_langue: dict) -> dict:
    """`{nom: phrase}` des variantes de décor, avec le défaut toujours présent.

    ⚠ Un gabarit qui n'a que `decor:` — tous ceux d'avant le lot 29 — reçoit **une** variante,
    `neutre`, et son comportement ne change pas d'un caractère. Le contraire (aucune variante)
    ferait échouer un balayage de décor sur un gabarit tiers, avec un message qui parlerait
    d'un bloc YAML que son auteur n'a jamais vu."""
    brut = par_langue.get("decors") or {}
    table = {str(cle): str(valeur or "") for cle, valeur in brut.items()} if brut else {}
    table.setdefault(DECOR_DEFAUT, str(par_langue.get("decor") or ""))
    return table


def empreinte(nom: str = DEFAUT) -> str:
    """SHA-256 du fichier de gabarit — il part dans le sidecar de provenance.

    ⚠ C'est ce qui rend le rejeu défendable : « gabarit portrait v1 » ne dit pas si le
    fichier a été édité depuis. Le dépôt applique déjà cette règle à `config.yaml` et aux
    poids (`orchestrateur._empreintes`) ; un gabarit est du texte qui décide de la sortie,
    au même titre qu'un prompt."""
    import hashlib

    chemin = racine() / f"{nom or DEFAUT}.yaml"
    if not chemin.is_file():
        return ""
    return hashlib.sha256(chemin.read_bytes()).hexdigest()
