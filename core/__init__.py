# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Socle partagé par les deux briques de traduction (light novel et manga).

Créé au lot 0 pour n'héberger qu'une chose — `core/version.py`, la source unique de
vérité de la version du dépôt — puis étoffé au lot 2 par le code réellement générique
de `pipeline/`.

**La frontière d'extraction n'est pas « ce qui est dupliqué » mais « ce qui prend
l'UNITÉ DE TRAVAIL en paramètre ».** Les deux orchestrateurs ne diffèrent que par leur
unité : un bloc de texte dans un chapitre pour le light novel, une planche de bulles
pour le manga. Appeler un modèle, diagnostiquer une mauvaise réponse, retenter à
température corrigée, checkpointer, compter des tokens, rapporter — tout cela est
*paramétré par* l'unité, pas *défini par* elle, et vit donc ici. Ce qui **construit**
l'unité (découpage en chapitres, détection de bulles) reste dans `pipeline/` ou
`manga/`. C'est ce qui rend l'opération traitable : sur les 1724 lignes de
`pipeline/orchestrator.py`, ~250 seulement sont génériques.

## Alias de transition : pourquoi `sys.modules[__name__] = _impl`

Les neuf modules déplacés au lot 2.1 (`agents`, `control`, `glossary`,
`glossary_build`, `glossary_import`, `llm`, `power`, `reporter`, `tokens`) laissent
derrière eux un alias `pipeline/<nom>.py` de trois lignes, pour ne pas casser les
imports existants. Cet alias **ne doit surtout pas** être écrit
`from core.<nom> import *` : ça créerait un *objet module distinct* dont les globals ne
sont qu'un instantané pris à l'import. Monkeypatcher `pipeline.agents.LLM` ne toucherait
alors plus ce que `core.agents.build_agents` résout réellement — les tests passeraient
contre la vraie classe, donc bloqueraient sur une socket au lieu d'échouer clairement.

L'auto-remplacement dans `sys.modules` n'a pas ce défaut : `_load()` relit
`sys.modules[nom]` après exécution du module et c'est *ce* résultat que le système
d'import lie à l'attribut du paquet parent. Donc `from pipeline import agents` rend
`core.agents`, et `pipeline.agents is core.agents` vaut `True` — monkeypatch, `id()`,
`isinstance` et `mock.patch("pipeline.agents.LLM")` se comportent exactement comme
avant le déplacement. C'est vérifié par `tests/test_core_alias.py`.
"""
