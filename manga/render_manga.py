# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Réassemblage des pages traduites : dossier d'images, CBZ, et/ou PDF."""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

# Clé lue par Komga, Kavita, YACReader, Mihon et ComicRack pour paginer de droite à gauche
# et afficher les doubles pages dans le bon sens.
_SENS = {"droite_gauche": "YesAndRightToLeft", "gauche_droite": "Yes"}

# Au-delà de ce pic estimé (Mo), on prévient l'utilisateur et on lui donne le réglage.
_SEUIL_ALERTE_MO = 800.0


def build_comicinfo(series: str, volume: str, pages: int,
                    sens_lecture: str = "droite_gauche", langue: str = "fr",
                    notes: str | None = None) -> str:
    """`ComicInfo.xml` — métadonnées standard de facto des archives de bande dessinée.

    Sans `Manga=YesAndRightToLeft`, un lecteur affiche la planche de gauche à droite : les
    doubles pages sont inversées et l'ordre des cases devient incompréhensible. C'est la
    seule métadonnée réellement indispensable pour un manga.

    Toutes les valeurs sont échappées : un projet nommé « Tom & Jerry » ou
    « <Untitled> » produirait sinon un XML invalide, que certains lecteurs rejettent en
    bloc — l'archive s'ouvrirait alors sans aucune métadonnée, silencieusement."""
    from core.version import __version__

    manga = _SENS.get(sens_lecture, "YesAndRightToLeft")
    lignes = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">',
        f"  <Series>{escape(series)}</Series>",
        f"  <Title>{escape(volume)}</Title>",
        f"  <Number>{escape(volume)}</Number>",
        f"  <PageCount>{int(pages)}</PageCount>",
        f"  <LanguageISO>{escape(langue)}</LanguageISO>",
        f"  <Manga>{manga}</Manga>",
        f"  <Notes>{escape(notes or f'Traduit avec Angelith {__version__}')}</Notes>",
        "</ComicInfo>",
    ]
    return "\n".join(lignes) + "\n"


def build_cbz(page_paths: list[Path], out_path: Path, *,
              comicinfo: str | None = None) -> Path:
    """Archive CBZ. `comicinfo` est un paramètre **optionnel** : aucun appelant ni test
    existant ne casse.

    `ComicInfo.xml` est écrit en PREMIÈRE entrée de l'archive — plusieurs lecteurs ne le
    cherchent qu'au début du flux plutôt que de parcourir tout le catalogue."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if comicinfo:
            zf.writestr("ComicInfo.xml", comicinfo)
        for p in page_paths:
            zf.write(p, arcname=p.name)
    return out_path


def estimer_pic_memoire_pdf(page_paths: list[Path], largeur_max: int | None = None) -> float:
    """Pic mémoire attendu, en Mo, pour assembler ces pages en PDF.

    Toutes les planches sont décodées **simultanément** (cf. `build_pdf`) : ~3 octets par
    pixel, plus l'encodage JPEG en cours. Le facteur 1,45 est calé sur la mesure réelle
    (1175 Mo de pic pour 810 Mo de bitmaps, tome de 150 planches 1125×1600)."""
    total_px = 0
    for p in page_paths:
        try:
            with Image.open(p) as im:      # ouverture paresseuse : lit l'en-tête seulement
                w, h = im.size
        except OSError:
            continue
        if largeur_max and w > int(largeur_max):
            h = round(h * int(largeur_max) / w)
            w = int(largeur_max)
        total_px += w * h
    return total_px * 3 * 1.45 / 1e6


def build_pdf(page_paths: list[Path], out_path: Path, *, dpi: int = 300,
              quality: int = 85, largeur_max: int | None = None, warn=None) -> Path:
    """Assemble les planches en un PDF, en **un seul appel** à Pillow.

    ⚠ Ce PDF coûte cher en mémoire, et il n'existe pas de contournement propre avec Pillow
    seul. Les trois voies possibles ont été mesurées sur le tome de 150 planches :

    | Voie | Résultat |
    |---|---|
    | un seul `save(append_images=…)` | PDF **correct** (`/Count 150`), pic **~1,2 Go** |
    | `append=True` page par page | **échoue** — `PdfFormatError: trailer loop found` |
    | `append=True` par lots | PDF **silencieusement tronqué** : `/Count 38` |

    Le plan prescrivait l'écriture incrémentale page par page comme « la seule solution
    réellement bornée ». Elle ne fonctionne pas : Pillow 12.2.0 ne supporte que **3 appends**
    (vérifié, indépendamment du nombre de pages — quatre appends d'UNE page échouent déjà),
    et découper en lots produit un fichier où Pillow écrit **un catalogue par lot** : seules
    les pages du dernier restent atteignables. C'est le pire des cas — un PDF qui s'ouvre
    sans erreur et à qui il manque 112 planches.

    On garde donc la voie correcte, et on rend le coût **visible** : `warn` est appelé quand
    le pic estimé dépasse `_SEUIL_ALERTE_MO`, avec le réglage qui le réduit. `largeur_max`
    (`manga.rendu.pdf_largeur_max`, ex. 1600) sous-échantillonne les planches et fait baisser
    le pic quadratiquement. Le PDF n'est de toute façon pas un format par défaut.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not page_paths:
        raise SystemExit("Aucune page à assembler en PDF.")

    pic = estimer_pic_memoire_pdf(page_paths, largeur_max)
    if pic > _SEUIL_ALERTE_MO and callable(warn):
        warn(f"[pdf] {len(page_paths)} planches assemblées d'un bloc : pic mémoire estimé "
             f"~{pic / 1000:.1f} Go. Pillow ne sait pas écrire un PDF page par page sans le "
             f"tronquer ; réduis `manga.rendu.pdf_largeur_max` (ex. 1600) pour faire baisser "
             f"ce pic, ou n'active le format `pdf` qu'au besoin.")

    images: list[Image.Image] = []
    try:
        for p in page_paths:
            with Image.open(p) as brut:
                page = brut.convert("RGB")
            if largeur_max and page.width > int(largeur_max):
                h = round(page.height * int(largeur_max) / page.width)
                page = page.resize((int(largeur_max), h), Image.LANCZOS)
            images.append(page)
        images[0].save(out_path, "PDF", save_all=True, append_images=images[1:],
                       resolution=float(dpi), quality=int(quality))
    finally:
        for page in images:
            page.close()
    return out_path
