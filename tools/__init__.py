# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Instruments de mesure du dépôt.

Ce fichier ne fait qu'une chose : rendre `tools/` **importable**, pour que
`tools/_banc_commun.py` soit partagé par les outils *et* par les tests
(`tests/test_tools_banc.py`) au lieu d'être recopié.

⚠ Il ne doit RIEN importer. Chaque outil de ce dossier commence par
`sys.path.insert(0, RACINE)` puis importe `core`/`manga` ; un import ici s'exécuterait
avant cette insertion et casserait les quatre lignes de commande d'un coup."""
