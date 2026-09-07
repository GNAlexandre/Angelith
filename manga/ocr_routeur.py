# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Choix du moteur d'OCR d'après la LANGUE SOURCE du tome.

Un seul moteur ne couvre pas les deux mondes, et prétendre le contraire est ce qui a produit
le run raté de *webtoon A* Chap.11 :

  · `manga-ocr` (`manga/ocr.py`) est imbattable sur le japonais manga vertical, les furigana
    et les polices stylisées — et structurellement incapable de lire du latin, faute de token
    d'espace dans son décodeur (cf. l'en-tête de `manga/ocr_latin.py`).
  · RapidOCR / PP-OCRv4 (`manga/ocr_latin.py`) lit le latin, le cyrillique et le hangûl avec
    les espaces, et n'est pas au niveau sur du japonais vertical stylisé.

D'où ce routeur : chacun sur son terrain. Les deux classes exposent la même surface
(`read`, `read_all`), donc l'appelant ne sait pas lequel il tient."""
from __future__ import annotations

#: Langues confiées à `manga-ocr`. Le japonais seul : c'est le seul terrain où il domine.
LANGUES_MANGA_OCR = frozenset({"jp", "ja"})

MOTEUR_MANGA = "manga_ocr"
MOTEUR_LATIN = "rapidocr"
MOTEUR_AUTO = "auto"


def moteur_pour(langue: str, cfg: dict | None = None) -> str:
    """Nom du moteur à employer. `manga.ocr.moteur` force la main (`auto` par défaut)."""
    choix = str((cfg or {}).get("moteur") or MOTEUR_AUTO).lower()
    if choix in (MOTEUR_MANGA, MOTEUR_LATIN):
        return choix
    if choix != MOTEUR_AUTO:
        raise SystemExit(
            f"`manga.ocr.moteur` : valeur inconnue « {choix} ». "
            f"Attendu : {MOTEUR_AUTO}, {MOTEUR_MANGA} ou {MOTEUR_LATIN}.")
    return MOTEUR_MANGA if (langue or "").lower() in LANGUES_MANGA_OCR else MOTEUR_LATIN


def lecteur_pour(langue: str, cfg: dict | None = None, *, dire=None):
    """Instancie le lecteur adapté à `langue`. Coûteux : le modèle est chargé ici.

    L'appelant garde l'instance (chargement paresseux côté orchestrateur) — c'est le même
    contrat qu'avant, `MangaOCR` n'ayant jamais été un singleton."""
    moteur = moteur_pour(langue, cfg)
    if moteur == MOTEUR_MANGA:
        from .ocr import MangaOCR
        return MangaOCR(cfg or {}, dire=dire)
    from .ocr_latin import OCRLatin
    return OCRLatin(cfg or {}, langue=(langue or "en").lower(), dire=dire)
