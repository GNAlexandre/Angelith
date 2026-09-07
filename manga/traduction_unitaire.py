# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Traduction d'UNE bulle : une bulle, une réponse, aucun numéro à se tromper.

## Pourquoi c'est un module et non une fonction privée de l'orchestrateur

Cette forme d'appel existe depuis le rattrapage des bulles vides (`_rattraper_bulles`), où elle
a été introduite pour une raison précise : le retry de planche rejoue la NUMÉROTATION,
c'est-à-dire exactement ce qui vient d'échouer — sur le Vol.1, les deux retries de page ont
échoué comme leur premier essai. L'escalade devait donc changer de **forme d'appel**, pas de
température.

L'éditeur graphique a besoin du même appel, pour le bouton « retraduire cette bulle ». Le
recopier serait le pire des deux mondes : deux prompts libres de diverger, alors que celui-ci
porte trois garde-fous tirés de mesures, et que ce qui est dessiné dans une bulle dépend
entièrement d'eux. D'où l'extraction — un seul prompt, un seul jeu de refus, deux appelants.

Le module ne connaît ni pixels, ni checkpoints, ni Qt : il prend un agent, un texte source et
une bbox. C'est ce qui le rend testable sans LLM et réutilisable depuis l'interface.
"""
from __future__ import annotations

from core import glossary_lang

from . import consignes, quality_manga

# Consigne de forme. Elle est aussi importante que la consigne de traduction : sans elle le
# modèle reprend la forme de PAGE (une liste numérotée), et `diagnostiquer_rattrapage` doit
# alors rejeter la réponse — un appel payé pour rien.
CONSIGNE = ("Traduis en français la SEULE réplique ci-dessous, extraite d'une planche de "
            "bande dessinée. Réponds par la traduction et RIEN d'autre : pas de numéro, pas "
            "de guillemets, pas de commentaire, pas de variante.")

#: Clé sous laquelle un pack de langue cible surcharge `CONSIGNE`. Le texte français reste
#: ci-dessus, à son site d'appel : le recopier dans le pack `fr` en ferait une seconde source
#: libre de diverger, dont l'une déciderait de la sortie d'un tome (cf.
#: `core.langues.Pack.consigne`).
CLE_CONSIGNE = "traduction_unitaire"


def budget_caracteres(bbox: tuple, source: str = "", langue: str = "jp") -> int:
    """Nombre de caractères visé pour une bulle. **Le seul calcul du dépôt.**

    Deux chemins le posaient séparément — le prompt unitaire ci-dessous et les gabarits de
    planche (`orchestrator_manga._lignes_gabarits`) — et ils avaient divergé sur le point qui
    compte :

    · **surface** — une bulle tient ~2,2 caractères par pixel de largeur et par ligne, à taille
      de police usuelle. C'est `surface / 320`, calibré sur du japonais.
    · **source** — et c'est la borne qui manquait au chemin de planche. `surface / 320` suppose
      une source DENSE : une bulle japonaise porte peu de caractères, sa traduction française
      en porte beaucoup plus. D'une source latine vers le français, source et cible ont des
      longueurs comparables, et le gabarit de surface seul demande au modèle d'être trois fois
      plus bavard que l'original.

    ⚠ Le tome de webtoon du dépôt est à source anglaise (`webtoon A` Chap.11,
    `"langue_source": "en"`) : **tout son lettrage de planche recevait le budget japonais non
    borné**, et seul le rattrapage unitaire était juste.

    ⚠ Le calcul vit ICI et non dans l'orchestrateur, parce que la dépendance ne va que dans ce
    sens : `orchestrator_manga` importe ce module, l'inverse serait un cycle. C'est la même
    logique que `detection.depuis_config` — un seul point de construction, du côté qui ne
    dépend de personne.

    +30 % sur la source : c'est l'écart moyen anglais→français, pas une licence de broder."""
    x0, y0, x1, y1 = bbox
    surface = max(1, x1 - x0) * max(1, y1 - y0)
    budget = max(12, int(surface / 320))
    if (langue or "jp").lower() not in glossary_lang.LANGUES_CJK:
        budget = min(budget, max(12, int(len((source or "").strip()) * 1.3)))
    return budget


def prompt_bulle(source: str, *, gloss_text: str = "", bbox=None,
                 langue: str = "jp", pack=None) -> str:
    """Message utilisateur pour la traduction d'une bulle isolée.

    `bbox` (x0, y0, x1, y1) ajoute le gabarit de place disponible — même budget indicatif que
    la traduction de planche : une bulle tient ~2,2 caractères par pixel de largeur et par
    ligne. Sans lui, le prompt demande d'être bref sans jamais dire à quel point.

    ⚠ Le budget dépend de la LANGUE SOURCE. `surface / 320` est calibré sur du japonais, qui
    est dense : une bulle japonaise porte peu de caractères et sa traduction française en
    porte beaucoup plus. D'une source latine vers le français, source et cible ont des
    longueurs comparables — c'est la source qui donne le bon ordre de grandeur, et le gabarit
    de surface seul demanderait au modèle d'être trois fois plus bavard que l'original."""
    parts = [p for p in (gloss_text,) if p]
    parts.append(pack.consigne(CLE_CONSIGNE, CONSIGNE) if pack is not None else CONSIGNE)
    if bbox is not None:
        x0, y0, x1, y1 = bbox
        parts.append(consignes.texte(pack, "traduction_unitaire_place",
                                     largeur=x1 - x0, hauteur=y1 - y0,
                                     budget=budget_caracteres(bbox, source, langue)))
    parts.append(consignes.texte(pack, "traduction_unitaire_replique",
                                 langue=glossary_lang.nom_langue(langue)) + "\n" + source)
    return "\n\n".join(parts)


def traduire_bulle(agent, source: str, *, gloss_text: str = "",
                   bbox=None, langue: str = "jp", pack=None) -> tuple[str, str | None]:
    """Traduit une bulle. Renvoie `(texte, motif_de_refus)` — l'un des deux est toujours vide.

    Trois garde-fous, chacun tiré d'une mesure (cf. `quality_manga`) :

    · une source qui ne porte **aucun texte** n'est pas traduisible — l'OCR `（）` de la page 8
      bulle 1 n'a rien à traduire, et le faire traduire reviendrait à faire inventer une
      réplique à partir de rien ;
    · une réponse **diagnostiquée est rejetée**, jamais rendue : une mauvaise réplique dessinée
      dans une bulle est pire qu'une bulle vide, qui est au moins signalée au rapport ;
    · le plafond de sortie est proportionné à la source seule (`bubbles_cap(source, 1)`), ce
      qui réactive la détection de troncature du client LLM.

    Le motif est une clé de `quality_manga.LIBELLES_RATTRAPAGE` : l'appelant décide s'il
    l'affiche, le journalise ou le montre dans une boîte de dialogue."""
    if not quality_manga.source_rattrapable(source):
        return "", "source_vide"
    cap = quality_manga.bubbles_cap(source, 1)
    brut = agent.run(prompt_bulle(source, gloss_text=gloss_text, bbox=bbox, langue=langue,
                                  pack=pack),
                     dry_payload=source, max_tokens=cap)
    motif = quality_manga.diagnostiquer_rattrapage(brut, source=source, cap=cap,
                                                   langue=langue)
    if motif is not None:
        return "", motif
    return quality_manga.sans_prefixe((brut or "").strip()), None
