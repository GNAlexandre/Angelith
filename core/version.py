# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Version du projet — SOURCE UNIQUE DE VÉRITÉ.
Toute autre mention (CHANGELOG, tag git, en-tête de run, métadonnées de sortie) en découle.

Pas de pyproject.toml : le projet n'est pas empaqueté, il se lance par `python run.py`. Un
littéral Python évite donc une lecture disque relative à __file__ (fichier VERSION) ou un
parseur TOML au démarrage."""

__version__ = "1.8.0"

# La version du dépôt est UNIQUE, mais les deux briques n'ont pas le même degré de
# confiance. Affiché par `--version`.
#
# `manga` passe de « bêta » à « stable » en 1.0.0, et les mesures le portent : sur les
# 258 planches à bulles des deux tomes du *manga A*, 257 sont en numérotation
# complète, 0 en repli positionnel, et 0 des 1 593 bulles ne porte de kanji résiduel.
#
# ⚠ La réserve est nommée plutôt que masquée : la LECTURE du texte hors bulle reste peu fiable
# (`manga-ocr` est un modèle de dialogue et hallucine sur une onomatopée stylisée), d'où
# `manga.onomatopees.mode: "rapport"` par défaut — on détecte et on rapporte, on ne dessine
# pas. Cela ne touche pas les bulles, qui sont ce que « stable » qualifie.
#
# L'interface graphique n'apparaît PAS ici, et ne fait pas non plus passer la version à 2.0.0
# tant qu'elle n'est pas jugée mûre à l'usage. Deux raisons distinctes :
#
# · ce n'est pas une troisième brique de traitement mais une FAÇADE — elle n'a aucun chemin
#   propre, elle appelle les deux `process_volume` et `manga/edition.py`, et son degré de
#   confiance est donc celui des briques qu'elle pilote ;
# · la 2.0.0 est une promesse écrite au README (« interface graphique et édition directe ») :
#   la poser demande d'avoir retouché de vraies planches, pas seulement d'avoir livré le code.
#   Elle vit donc sous « [Non publié] » au CHANGELOG en attendant ce verdict.
# `scan` (1.4.0) arrive en BÊTA, et la réserve est nommée : l'analyse de mise en page est
# mesurée sur un seul tirage — les scans de *manga C* — et ses seuils, quoique
# tous relatifs et non absolus, n'ont pas encore vu d'autre imprimeur. Le garde-fou de la
# brique (la grille prédit ce que la lecture devrait rendre) et `run_ocr.py --apercu` existent
# précisément pour que le prochain tirage se règle en une minute au lieu de se découvrir après
# deux heures d'OCR. La lecture elle-même est celle de `manga-ocr`, déjà éprouvée.
ETAT_BRIQUES = {"ln": "stable", "manga": "stable", "scan": "beta"}
