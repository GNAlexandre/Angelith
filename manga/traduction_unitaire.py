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

from . import quality_manga

# Consigne de forme. Elle est aussi importante que la consigne de traduction : sans elle le
# modèle reprend la forme de PAGE (une liste numérotée), et `diagnostiquer_rattrapage` doit
# alors rejeter la réponse — un appel payé pour rien.
CONSIGNE = ("Traduis en français la SEULE réplique ci-dessous, extraite d'une planche de "
            "manga. Réponds par la traduction et RIEN d'autre : pas de numéro, pas de "
            "guillemets, pas de commentaire, pas de variante.")


def prompt_bulle(source: str, *, gloss_text: str = "", bbox=None) -> str:
    """Message utilisateur pour la traduction d'une bulle isolée.

    `bbox` (x0, y0, x1, y1) ajoute le gabarit de place disponible — même budget indicatif que
    la traduction de planche : une bulle tient ~2,2 caractères par pixel de largeur et par
    ligne. Sans lui, le prompt demande d'être bref sans jamais dire à quel point."""
    parts = [p for p in (gloss_text,) if p]
    parts.append(CONSIGNE)
    if bbox is not None:
        x0, y0, x1, y1 = bbox
        surface = max(1, x1 - x0) * max(1, y1 - y0)
        parts.append(f"Place disponible : {x1 - x0}×{y1 - y0} px — viser "
                     f"≤ {max(12, int(surface / 320))} caractères.")
    parts.append("Réplique japonaise :\n" + source)
    return "\n\n".join(parts)


def traduire_bulle(agent, source: str, *, gloss_text: str = "",
                   bbox=None) -> tuple[str, str | None]:
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
    brut = agent.run(prompt_bulle(source, gloss_text=gloss_text, bbox=bbox),
                     dry_payload=source, max_tokens=cap)
    motif = quality_manga.diagnostiquer_rattrapage(brut, source=source, cap=cap)
    if motif is not None:
        return "", motif
    return quality_manga.sans_prefixe((brut or "").strip()), None
