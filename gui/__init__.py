# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Interface graphique (lot 16). **Ce dossier ne contient que du Qt.**

La règle est celle que `core/cli.py` énonce pour les CLI, prolongée d'un cran : toute logique
métier — écrire une région, relire une bulle, retraduire une réplique — vit dans `manga/`, en
Python nu, et se teste avec `pytest` sans que PySide6 soit installé. Ici on ne trouve que des
fenêtres, des scènes et des signaux.

Concrètement, l'interface n'invente rien :

- elle LANCE les runs en appelant `manga.orchestrator_manga.process_volume` et
  `pipeline.orchestrator.process_volume`, les deux mêmes fonctions que `run_manga.py` et
  `run.py`, avec un `Reporter` qui émet des signaux au lieu d'imprimer ;
- elle ARRÊTE un run en écrivant le fichier `STOP` via `core.control.request_stop` — le même
  mécanisme que `--stop`, pas un second en parallèle ;
- elle ÉDITE les zones par `manga.edition`, et les répliques par
  `checkpoints.save_traduction_manuelle` ;
- elle RELETTRE une planche par `process_volume(only_page=N, restart_from="rendu")`.

Rien de ce que fait l'interface n'est donc inaccessible à la ligne de commande, et un tome
retouché ici se relance à l'identique avec `run_manga.py`.
"""
