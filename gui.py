#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Interface graphique de Angelith — lancer les runs, et retoucher une planche manga.

    pip install -r requirements-gui.txt
    python gui.py
    python gui.py --config autre.yaml

Ce que l'interface apporte, et que la ligne de commande ne peut pas donner :

  · VOIR les zones de bulles superposées à la planche, avec leur numéro d'ordre de lecture —
    l'ordre qui aligne `ocr.json` et `traduction.json`, et dont une inversion est invisible sur
    la page rendue ;
  · CORRIGER une zone que la détection a manquée, mal découpée ou inventée (ajouter,
    redessiner, supprimer, scinder) sans passer par Photoshop ni par l'édition de JSON ;
  · RETOUCHER une réplique au clavier — elle part dans `traduction_manuelle.json`, que le
    pipeline ne réécrit jamais ;
  · RELETTRER la planche d'un bouton, et regarder le résultat.

Ce qu'elle n'apporte PAS, délibérément : aucun chemin de traitement qui lui soit propre. Tout
passe par `manga.orchestrator_manga.process_volume` et `manga.edition` — un tome retouché ici
se relance à l'identique avec `run_manga.py`, et réciproquement.

⚠ **Le démarrage ne charge rien** (2.25.0). Jusqu'à la 2.24.1, lancer l'interface OUVRAIT le
premier projet par ordre alphabétique — un `Tome` lu, un `Services` construit, des aperçus
composés — avant le premier pixel. La fenêtre s'ouvre maintenant sur un accueil qui ne touche à
aucun tome, et les sept destinations de la nav latérale sont construites au premier affichage.
Mesuré : 1,89 s → 0,13 s, 692 → 1 ouverture de fichier, 311 → 106 Mo
(`docs/mesures/coquille-2026-09-04.md`).

⚠ `config.yaml` n'est jamais réécrit par l'interface. Ses commentaires sont sa documentation ;
les réglages d'un run sont appliqués en mémoire, comme les drapeaux des CLI.

⚠ **MISE À JOUR 2.31.0 (2026-09-06), lot 37 : le corps de `main` a déménagé dans
`gui/lancement.py`**, sans une ligne réécrite. Motif : un point d'entrée de paquet s'écrit
`module:fonction`, et ce fichier-ci n'est PAS importable — le dépôt porte un module `gui.py`
et un paquet `gui/`, et Python résout le paquet. `python gui.py` continue de marcher à
l'identique ; `angelith-gui` existe en plus.
"""
from __future__ import annotations

from gui.lancement import main

if __name__ == "__main__":
    main()
