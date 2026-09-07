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

## Les quatre couches, depuis le lot 31

Le dossier s'est structuré, et la règle de couche s'y lit maintenant à l'œil nu :

| Couche | Modules | PySide6 ? |
|---|---|---|
| **les tables** — ce que l'application sait faire, où l'on peut se trouver, ce qu'on peut régler | `actions.py`, `destinations.py`, `parametres.py` | **non** |
| **les décisions** — persistance, filtres, sondes, cache, progression, extinction, gardes | `reglages.py`, `profils.py`, `sondes.py`, `extinction.py`, `pellicule.py`, `avancement.py`, `cache_apercu.py`, `modele_tome.py`, `apercu.py`, `depot.py`, `garde.py`, `vue_oeuvres.py`, `vue_retouche.py` | **non** |
| **les panneaux** — une destination, un fichier | `accueil.py`, `navigation.py`, `retouche.py`, `lanceur.py`, `atelier.py`, `oeuvres.py`, `editeur*.py` | oui |
| **la coquille** — les fils, le journal, le bandeau de run, les menus, le générateur de formulaire | `fenetre.py`, `travailleur.py`, `bandeau.py`, `formulaire.py`, `theme.py`, `icones.py` | oui |

Les deux premières lignes se testent sans qu'une seule dépendance graphique soit installée, et
c'est ce que le job de CI qui n'installe pas PySide6 exécute.

⚠ **Lot 32 — la progression a quitté ce dossier, et la couche « décisions » s'est épaissie.**
L'ÉTAT d'un run (phases, objet en cours, fraction monotone) vit dans `core/progression.py` :
la console en a besoin autant que la fenêtre, et `manga/`, `pipeline/` et `illustration/` s'en
servent tous les trois. Ce qui reste ici est ce qui décide de l'AFFICHAGE — `avancement.py`
rend les lignes du bandeau, le titre de fenêtre et le bilan de fin, toujours sans Qt — et
`bandeau.py`, qui ne fait que poser des chaînes.

⚠ **Lot 33 — la table des paramètres de run, et une décision qui touche à la MACHINE.**
`parametres.py` déclare les dix-neuf réglages de run et, seul, sait où chaque valeur atterrit
dans `config.yaml` ; `formulaire.py` les dessine et ne décide de rien. `extinction.py` est le
cas limite de la règle et sa meilleure justification : éteindre le PC est la seule action de
l'application qui touche au matériel, et une décision de cette portée ne vit pas dans un
`QTimer` — elle se teste sans écran, sans minuteur, et sans éteindre quoi que ce soit.

⚠ La sonde de MODÈLES, elle, est dans `core/modeles.py` et non ici : `app.py` en a le même
usage que la fenêtre, et une liste de modèles n'est pas une affaire d'interface graphique.

⚠ **Lot 35 — les GARDES descendent d'un cran, et le cache d'aperçus se borne lui-même.**
`garde.py` porte les six chemins par lesquels du travail non enregistré peut se perdre, chacun
avec son verdict et son motif ; `Fenetre.peut_quitter` est l'unique implémentation que les six
appellent, et trois d'entre eux n'ouvrent jamais de boîte — « un dialogue qui se pose à chaque
changement d'onglet est un dialogue qu'on apprend à cliquer sans lire ». `vue_retouche.py`
tient les phrases de la destination Retouche, comme `vue_oeuvres.py` celles de la
bibliothèque. Et `cache_apercu.py` gagne `fenetre_tenable` / `fenetre_retenue` : le
préchargement ne demande plus que ce que le plafond garde, ce qui supprime un emballement
mesuré à **137 compositions pour 12 aperçus gardés en 120 s**
(`docs/mesures/retouche-2026-09-05.md`).
"""
