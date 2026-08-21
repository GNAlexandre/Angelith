# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Inventaire d'un tome livré en images : quel dossier de langue, quelles pages, où écrire.

Miroir léger de `pipeline/sources.py` et de `manga/sources_manga.py` — même structure de
dossiers, même tri naturel, mêmes messages. La différence tient en une phrase : ici on
cherche un dossier de langue qui ne contient **que des images**, précisément le cas que
`pipeline/sources.py` refuse aujourd'hui (« Aucune source exploitable »).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from manga.ingest import IMG_EXTS, natural_key

# Extensions de texte que `pipeline/sources.py` sait déjà lire. Leur présence dans un dossier
# de langue signifie que le tome n'a pas besoin de nous.
EXTS_TEXTE = (".docx", ".pdf", ".epub", ".txt", ".md")

MEDIA = "media"


@dataclass
class PlanScan:
    projet: str
    tome: str
    dossier: Path              # sources/<Projet>/<Tome>/JAP
    code_langue: str           # "jp", "en"… tel que `langues.dossiers` le donne
    pages: list[Path]          # images, dans l'ordre de lecture
    build_dir: Path            # build/<Projet>/<Tome>/ocr
    sortie: Path               # le .md produit, DANS le dossier de langue
    media: Path                # les illustrations extraites, à côté du .md
    avertissements: list[str] = field(default_factory=list)


def images_de(dossier: Path) -> list[Path]:
    """Images du dossier, triées naturellement (`0002` avant `0010`).

    Le sous-dossier `media/` est ignoré : c'est notre propre sortie, et la relire ferait
    grossir le tome d'un tour de manivelle à l'autre."""
    if not dossier.is_dir():
        return []
    return sorted((f for f in dossier.iterdir()
                   if f.is_file() and f.suffix.lower() in IMG_EXTS and f.parent.name != MEDIA),
                  key=lambda p: natural_key(p.name))


def scan_volume(vol_dir: Path, build_dir: Path, config: dict,
                langue: str | None = None) -> PlanScan:
    """Choisit le dossier de langue à lire et dresse la liste des pages.

    `langue` force un nom de dossier (`JAP`) quand un tome en porte plusieurs en images.
    Sinon on prend celui qui a le plus de pages — et on le dit, parce qu'un choix implicite
    sur des centaines de pages d'OCR mérite d'être visible."""
    vol_dir = Path(vol_dir)
    if not vol_dir.is_dir():
        raise SystemExit(f"Tome introuvable : {vol_dir}")
    mapping = {k.upper(): v for k, v in config["langues"]["dossiers"].items()}

    avertissements: list[str] = []
    candidats: list[tuple[Path, str, list[Path]]] = []
    for sub in sorted(p for p in vol_dir.iterdir() if p.is_dir()):
        code = mapping.get(sub.name.upper())
        if not code or (langue and sub.name.upper() != langue.upper()):
            continue
        imgs = images_de(sub)
        if not imgs:
            continue
        # ⚠ Sans exclure notre propre sortie, toute RELANCE s'avertissait elle-même d'avoir
        # trouvé du texte — le `.md` qu'elle venait d'écrire au tour précédent.
        notre_sortie = f"{vol_dir.name}.md".lower()
        deja = [f for f in sub.iterdir()
                if f.suffix.lower() in EXTS_TEXTE and f.name.lower() != notre_sortie]
        if deja:
            avertissements.append(
                f"{sub.name} contient déjà du texte ({', '.join(f.name for f in deja[:3])}) — "
                f"l'OCR l'écrasera si le nom coïncide.")
        candidats.append((sub, code, imgs))

    if not candidats:
        attendu = ", ".join(sorted(set(config["langues"]["dossiers"])))
        raise SystemExit(
            f"Aucun dossier de langue contenant des images sous {vol_dir}.\n"
            f"  → dépose tes pages (.png/.jpg) dans un sous-dossier ({attendu}).")

    candidats.sort(key=lambda c: -len(c[2]))
    if len(candidats) > 1:
        autres = ", ".join(f"{c[0].name} ({len(c[2])})" for c in candidats[1:])
        avertissements.append(
            f"Plusieurs langues en images : {candidats[0][0].name} retenu "
            f"({len(candidats[0][2])} pages), ignorés : {autres}. Utilise --langue pour choisir.")

    dossier, code, pages = candidats[0]
    return PlanScan(
        projet=vol_dir.parent.name, tome=vol_dir.name,
        dossier=dossier, code_langue=code, pages=pages,
        build_dir=Path(build_dir),
        sortie=dossier / f"{vol_dir.name}.md",
        media=dossier / MEDIA,
        avertissements=avertissements,
    )


def lister_projets(sources_dir: Path) -> list[str]:
    sources_dir = Path(sources_dir)
    if not sources_dir.exists():
        return []
    return sorted(p.name for p in sources_dir.iterdir() if p.is_dir())


def lister_tomes(sources_dir: Path, projet: str) -> list[str]:
    proj = Path(sources_dir) / projet
    if not proj.exists():
        return []
    return sorted(p.name for p in proj.iterdir() if p.is_dir())
