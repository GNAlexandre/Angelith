# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Scan d'un dossier de Tome : détecte les langues, extrait chaque source,
découpe en chapitres, et décide de la langue PIVOT, de la source d'IMAGES et du MODE.

Structure attendue :
    sources/<Projet>/<Tome>/<ENG|JAP|ESP|CHINOIS|FR>/*.docx|*.pdf|*.epub|*.txt|*.md
Plusieurs fichiers par langue sont concaténés dans l'ordre DE LECTURE
(prologue d'abord, chapitres triés numériquement, épilogue/postface en dernier).
(utile pour les versions ZH/ES récupérées en plusieurs PDF « print-to-PDF »).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import extract, split


@dataclass
class LangSource:
    code: str
    files: list[Path]
    chapters: list[split.Chapter]          # texte AVEC marqueurs d'images
    full_text: str = ""                    # texte intégral concaténé (pour redétection LLM)
    images: list[str] = field(default_factory=list)
    # Lectures (furigana) relevées à l'extraction : graphie source → prononciation. Ne
    # sert qu'au terminologue, et seulement sur un pivot non latin — c'est l'information
    # qui lui manque pour proposer une romanisation plutôt que de recopier la graphie.
    lectures: dict[str, str] = field(default_factory=dict)


@dataclass
class VolumePlan:
    project: str
    volume: str
    langs: dict[str, LangSource]           # code → source
    pivot: str                             # langue pivot (base de la traduction)
    image_lang: str | None                 # langue source des images
    mode: str                              # "amelioration" (FR présent) | "traduction"
    n_chapters: int
    media_dir: Path
    warnings: list[str] = field(default_factory=list)


def _map_folder(name: str, mapping: dict[str, str]) -> str | None:
    return mapping.get(name.upper())


_PROLOGUE_KW = ("prolog", "序", "前日")
_EPILOGUE_KW = ("epilog", "épilog", "postface", "afterword", "あとがき", "後書", "跋")


def _reading_order_key(path: Path):
    """Clé de tri « ordre de lecture » : prologue d'abord, puis chapitres triés
    NUMÉRIQUEMENT (Part.2 avant Part.10), puis épilogue/postface en dernier.
    Les nombres sont extraits pour un tri naturel ; le tri alphabétique seul
    placerait par ex. le prologue après la postface, ou Part.10 avant Part.2."""
    name = path.stem.lower()
    if any(k in name for k in _PROLOGUE_KW):
        section = 0
    elif any(k in name for k in _EPILOGUE_KW):
        section = 2
    else:
        section = 1
    nums = tuple(int(x) for x in re.findall(r"\d+", name))
    return (section, nums, name)


def _chapter_key_from_name(stem: str):
    """(rank, num, label) du chapitre déduit du NOM de fichier, ou None si non reconnaissable.
    Permet d'identifier les chapitres d'une source éclatée en plusieurs fichiers
    (ex. « roman B Vol.2 Chap.1 Part.1.pdf » → Chapitre 1)."""
    low = stem.lower()
    if any(k in low for k in _PROLOGUE_KW):
        return (0, 0, "Prologue")
    if any(k in low for k in _EPILOGUE_KW):
        if any(k in low for k in ("postface", "後書", "あとがき", "跋")):
            return (3, 1, "Postface")
        return (3, 0, "Épilogue")
    m = re.search(r"(?:chap(?:ter|itre)?|cap[íi]tulo|第)\s*\.?\s*(\d+)", low)
    if m:
        num = int(m.group(1))
        return (1, num, f"Chapitre {num}")
    return None


def _chapters_from_filenames(extracted: list[tuple[Path, str]]):
    """Regroupe plusieurs fichiers en chapitres d'après leurs NOMS (un chapitre =
    tous ses « Part.N » consécutifs). Renvoie une liste de Chapter, ou None si les
    noms ne s'y prêtent pas (→ on retombe sur la détection par le contenu)."""
    keyed = [(_chapter_key_from_name(f.stem), txt) for f, txt in extracted]
    if any(k is None for k, _ in keyed):
        return None
    groups: list[list] = []
    for (rank, num, label), txt in keyed:
        if groups and groups[-1][0] == (rank, num):
            groups[-1][1].append(txt)
        else:
            groups.append([(rank, num), [txt], label])
    if len(groups) < 2:
        return None
    return [split.Chapter(title=label, body="\n\n".join(parts).strip())
            for (_, parts, label) in groups]


def scan_volume(vol_dir: Path, config: dict, build_dir: Path) -> VolumePlan:
    vol_dir = Path(vol_dir)
    mapping = config["langues"]["dossiers"]
    # Motifs ADDITIONNELS : les défauts multilingues restent actifs (cf. detect_chapters).
    patterns = config["decoupage"]["chapter_patterns"] or None
    format_cfg = config["decoupage"].get("mise_en_forme")
    epub_cfg = config["decoupage"].get("epub")
    media_dir = build_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    # --- Pass 0 (léger, sans extraction) : quelles langues sont présentes ? ---
    present: dict[str, list[Path]] = {}
    for sub in sorted(p for p in vol_dir.iterdir() if p.is_dir()):
        code = _map_folder(sub.name, mapping)
        if not code:
            continue
        files = sorted(
            (f for f in sub.iterdir()
             if f.suffix.lower() in (".docx", ".pdf", ".epub", ".txt", ".md")),
            key=_reading_order_key,
        )
        if files:
            present[code] = files
    if not present:
        raise SystemExit(f"Aucune source exploitable dans {vol_dir}")

    warnings: list[str] = []
    # Filtre des langues réellement utilisées (config : langues.sources_utilisees),
    # appliqué AVANT toute extraction : une langue exclue n'est ni lue, ni sondée
    # pour les images (aucun travail inutile). Permet de n'utiliser qu'UNE source
    # (ex. [en]) ou PLUSIEURS (ex. [fr, jp, en]), en traduction comme en amélioration.
    used = config["langues"].get("sources_utilisees")
    if used:
        kept = {c: f for c, f in present.items() if c in used}
        if kept:
            ignored = [c for c in present if c not in kept]
            if ignored:
                warnings.append("Langues présentes mais non utilisées (sources_utilisees) : "
                                + ", ".join(ignored))
            present = kept
        else:
            warnings.append("sources_utilisees ne correspond à aucune langue présente "
                            "→ filtre ignoré (toutes les langues sont utilisées).")

    # --- UNE SEULE langue fournit les images : la plus prioritaire (config
    # langues.priorite_images) PARMI celles présentes. On sonde dans l'ordre de
    # priorité et on s'arrête à la première qui produit réellement au moins une
    # image ; toutes les AUTRES langues sont extraites en texte seul. Ceci élimine
    # tout mélange d'images entre langues : chaque .docx/.pdf renumérote ses médias
    # depuis 1, donc en extraire plusieurs dans le même dossier écrasait/confondait
    # les fichiers (la mauvaise image ressortait, souvent à la mauvaise taille).
    cache: dict[str, list[tuple[Path, str, list[str], dict[str, str]]]] = {}

    def _extract_lang(code: str, want_images: bool) -> list[tuple[Path, str, list[str], dict[str, str]]]:
        out: list[tuple[Path, str, list[str], dict[str, str]]] = []
        for f in present[code]:
            ex = extract.extract(f, media_dir, extract_images=want_images,
                                 format_cfg=format_cfg, epub_cfg=epub_cfg)
            # Les avertissements de l'extracteur remontent au plan de tome : c'est là que
            # l'utilisateur les lit déjà, et un `print` depuis une extraction parallèle se
            # perdrait dans le défilement.
            warnings.extend(ex.avertissements)
            out.append((f, ex.text, ex.images, ex.lectures))
        cache[code] = out
        return out

    image_lang: str | None = None
    for cand in (c for c in config["langues"]["priorite_images"] if c in present):
        res = _extract_lang(cand, want_images=True)
        if any(imgs for _, _, imgs, _ in res):
            image_lang = cand
            break

    # Langues restantes (jamais sondées ci-dessus, ou sondées mais pas élues) : elles
    # sont toutes extraites en texte SEUL (want_images=False → aucune écriture dans
    # media_dir), donc sans le risque de collision qui limite la phase d'élection
    # ci-dessus à un traitement séquentiel. Ce sont des appels Pandoc (sous-processus)
    # ou PyMuPDF (documents distincts) totalement indépendants : on les lance en
    # parallèle pour ne pas payer leur somme en séquentiel sur un Tome multi-langues.
    remaining = [c for c in present if c not in cache]
    if len(remaining) > 1:
        with ThreadPoolExecutor(max_workers=len(remaining)) as pool:
            # list(...) force l'attente de TOUTES les extractions et propage la
            # première exception éventuelle ; _extract_lang alimente `cache` par
            # effet de bord (les résultats eux-mêmes ne sont pas utilisés ici).
            list(pool.map(lambda c: _extract_lang(c, want_images=False), remaining))
    elif remaining:
        _extract_lang(remaining[0], want_images=False)

    langs: dict[str, LangSource] = {}
    for code, files in present.items():
        res = cache[code]
        extracted = [(f, t) for f, t, _, _ in res]
        imgs = [i for _, _, ii, _ in res for i in ii]
        full_text = "\n\n".join(t for _, t in extracted)
        # Lectures fusionnées sur tous les fichiers de la langue (un EPUB par tome le plus
        # souvent, mais une source peut être découpée en plusieurs fichiers).
        lectures: dict[str, str] = {}
        for _, _, _, lex in res:
            for base, lecture in lex.items():
                lectures.setdefault(base, lecture)

        # 1) Chapitres par NOM DE FICHIER (sources multi-fichiers nommées par chapitre) ;
        # 2) sinon, détection structurelle dans le contenu.
        chapters = _chapters_from_filenames(extracted) if len(files) > 1 else None
        if not chapters:
            chapters = split.detect_chapters(full_text, patterns)
        langs[code] = LangSource(code=code, files=files, chapters=chapters,
                                 full_text=full_text, images=imgs, lectures=lectures)

    # --- Mode + pivot ---
    if "fr" in langs:
        mode = "amelioration"
        pivot = "fr"
    else:
        mode = "traduction"
        pivot = next((c for c in config["langues"]["priorite_sens"] if c in langs), None)
        if pivot is None:
            pivot = next(iter(langs))

    # --- Nombre de chapitres (référence = pivot) + contrôle d'alignement ---
    n_chapters = len(langs[pivot].chapters)
    for code, src in langs.items():
        if code != pivot and len(src.chapters) != n_chapters:
            warnings.append(
                f"Alignement : {code} a {len(src.chapters)} chapitre(s) vs {n_chapters} pour le pivot ({pivot}). "
                f"→ ses unités seront APPARIÉES aux {n_chapters} chapitres du pivot par proportions "
                f"(cf. le tableau d'appariement ci-dessus)."
            )

    return VolumePlan(
        project=vol_dir.parent.name,
        volume=vol_dir.name,
        langs=langs,
        pivot=pivot,
        image_lang=image_lang,
        mode=mode,
        n_chapters=n_chapters,
        media_dir=media_dir,
        warnings=warnings,
    )


def list_projects(sources_dir: Path) -> list[str]:
    sources_dir = Path(sources_dir)
    if not sources_dir.exists():
        return []
    return sorted(p.name for p in sources_dir.iterdir() if p.is_dir())


def list_volumes(sources_dir: Path, project: str) -> list[str]:
    proj = Path(sources_dir) / project
    if not proj.exists():
        return []
    return sorted(p.name for p in proj.iterdir() if p.is_dir())
