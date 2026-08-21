# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Agents LLM manga. Depuis le lot 2.2, la construction est déléguée au socle :
`core.agents.build_agents` est **la même fonction** pour les deux briques, paramétrée par
`section=` / `names=` / `agent_cls=`.

Ne reste ici que ce qui est réellement propre au manga : `MangaAgent`, sous-classe qui
ajoute un paramètre optionnel `images` à `run()` pour le mode de traduction « vision »
(planche entière envoyée au LLM en plus du texte OCR). C'est cette classe qui explique le
paramètre `agent_cls` du socle — `core/` ne peut pas l'importer sans redevenir dépendant
d'une brique.

Ce que la brique manga gagne au passage, faute d'avoir été maintenue en parallèle :

- **l'indirection `endpoint:`**, qui était SILENCIEUSEMENT IGNORÉE. `config.yaml`
  documentait le piège au lieu de le corriger : écrire
  `{model: …, endpoint: "reflexion"}` côté manga ne faisait rien du tout, sans un mot ;
- les **diagnostics de config mal indentée** (`endpoints: {}` vide qui ferme le
  dictionnaire avant la définition qui suit) ;
- le **partage de client par endpoint** avec le LN, donc un seul pool de sockets ;
- `extra_directive`, qui est par construction une directive GLOBALE (« ajouté à la fin de
  chaque message utilisateur ») et que seul le LN appliquait.

Les prompts sont cherchés dans le MÊME dossier `chemins.prompts` que le LN (`prompts/`) :
`terminologue.md`/`glossariste.md` sont donc réutilisables tels quels si on active ces
agents pour le manga (c'est ce que fera le lot 3).
"""
from __future__ import annotations

from core.agents import Agent, build_agents

# Aucune contrainte sur les noms : `build_agents` construit un agent par entrée de
# `config["manga"]["modeles"]`. Contrairement au LN, la brique manga n'a pas de roster
# fixe à honorer — pas de `agents["x"] is None` pour désactiver une étape.
TEMPERATURE_DEFAUT = 0.3


class MangaAgent(Agent):
    def run(self, user_content: str, dry_payload: str = "", max_tokens: int | None = None,
            temperature: float | None = None, images: list[str] | None = None) -> str:
        if self.dry_run:
            return self._dry(dry_payload)
        if self.extra_directive:
            user_content = f"{user_content}\n\n{self.extra_directive}"
        temp = self.temperature if temperature is None else temperature
        if max_tokens is not None and self.thinking:
            max_tokens += self.thinking_budget
        return self.llm.chat(self.modele, self.system, user_content, temp,
                              max_tokens=max_tokens, images=images)


def build_manga_agents(config: dict, dry_run: bool = False) -> dict[str, MangaAgent]:
    return build_agents(config, dry_run=dry_run, section="manga", agent_cls=MangaAgent,
                        temperature_defaut=TEMPERATURE_DEFAUT)
