# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Briques communes des `RAPPORT.md` des deux pipelines.

Le **contenu** des deux rapports n'a presque rien en commun — blocs, chapitres, images et
forçages de glossaire d'un côté ; bulles, modes de nettoyage, débordements et ordre de lecture
de l'autre. Ce qui est commun, c'est le **squelette** : l'en-tête de run (version, heure de
fin, durée), le bloc de statistiques LLM, la troncature des longues listes, et l'écriture du
fichier. C'est peu de lignes, mais ce sont exactement celles qui doivent rester identiques
entre les deux rapports pour qu'on puisse les lire de la même façon — et qui avaient déjà
divergé (deux formulations différentes pour « pas de statistique LLM », l'une des deux
mensongère).
"""
from __future__ import annotations

import datetime
from pathlib import Path

from .version import __version__


def entete_run(duree_s: float | None = None) -> list[str]:
    """Les trois lignes d'identification d'un run : version, heure de fin, durée.

    L'heure de fin n'est pas un ornement : un tome de 150 planches se lance en run de nuit,
    et savoir *quand* il s'est terminé est la première chose qu'on cherche le matin. La
    version non plus — un tome se relance des semaines plus tard."""
    lignes = [f"- Version : {__version__}",
              f"- Terminé le : {datetime.datetime.now().strftime('%Y-%m-%d à %Hh%M')}"]
    if duree_s is not None:
        mins, secs = divmod(int(duree_s), 60)
        lignes.append(f"- Durée totale : {mins}min {secs}s")
    return lignes


def lignes_llm(stats: dict | None) -> list[str]:
    """Bloc de statistiques LLM, ou la ligne qui dit qu'il n'y a rien à mesurer.

    ⚠ `stats` doit être l'AGRÉGAT de tous les clients du run (`core.runtime
    .aggregate_llm_stats`), pas `llm.stats` du client par défaut : sur un tome où plusieurs
    agents routent vers l'endpoint « reflexion », celui-ci ignore la majorité des appels.

    Un agrégat à zéro rend la ligne « aucun appel » et non « Appels LLM : 0 · ~0 tok/s », qui
    se lit comme une mesure alors que c'est une absence de mesure — le cas d'une reprise
    entièrement en cache."""
    if not stats or not (stats.get("appels") or stats.get("temps_generation")):
        return ["- (dry-run ou aucun appel — pas de statistique LLM)"]
    temps = stats.get("temps_generation") or 0
    vitesse = (stats.get("tokens_generes", 0) / temps) if temps > 0 else 0
    out = [f"- Appels LLM : {stats.get('appels', 0)} · tokens générés : "
           f"~{stats.get('tokens_generes', 0)} · vitesse moyenne : ~{vitesse:.0f} tok/s"
           + (f" · {stats['retries']} tentative(s) réseau/vide" if stats.get("retries") else "")
           + (f" · {stats['vides_persistants']} réponse(s) vide(s) persistante(s)"
              if stats.get("vides_persistants") else "")]
    if stats.get("thinking_overflow") or stats.get("troncature_length"):
        out.append(
            f"- Budget de génération : {stats.get('thinking_overflow', 0)} dépassement(s) de "
            f"budget « thinking » (raisonnement sans réponse finale) · "
            f"{stats.get('troncature_length', 0)} génération(s) coupée(s) net au plafond "
            f"`max_tokens`")
    return out


def tronquer(lignes: list[str], maxi: int) -> list[str]:
    """Liste bornée à `maxi` entrées, suivie du compte de ce qui a été coupé. Une liste de
    300 entrées noie le rapport ; la taire complètement le rendrait mensonger."""
    if len(lignes) <= maxi:
        return list(lignes)
    return list(lignes[:maxi]) + [f"(… {len(lignes) - maxi} autre(s))"]


def section(titre: str, lignes: list[str], maxi: int) -> list[str]:
    """Section `## Titre (N)` en liste à puces, tronquée. Vide si `lignes` est vide : une
    section « 0 problème » par catégorie ferait dix titres vides avant l'information utile."""
    if not lignes:
        return []
    return [f"## {titre} ({len(lignes)})", ""] + [f"- {l}" for l in tronquer(lignes, maxi)] + [""]


def ecrire(build_dir, texte: str, nom: str = "RAPPORT.md") -> Path:
    chemin = Path(build_dir) / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    return chemin
