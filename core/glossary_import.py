# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Import d'un glossaire existant (.docx / .txt / .md) vers le glossaire YAML
de l'œuvre. Parseur tolérant : tables Word, séparateurs variés (=, :, →, tab,
tiret), et sections (Personnages / Anglicismes / Termes)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from . import glossary

# Indices de section → catégorie
_SECTION_HINTS = [
    (re.compile(r"\b(personnage|character|perso|cast)", re.I), "personnages"),
    (re.compile(r"\b(anglicisme|interjection|onomatop|exclamation)", re.I), "anglicismes"),
    (re.compile(r"\b(terme|terminolog|lieu|objet|lieux|objets|vocabul|mot|nom propre|comp[eé]tence|skill)", re.I), "termes"),
]
# Séparateurs term ↔ traduction, par ordre de priorité
_SEPARATORS = ["\t", "=>", "⇒", "→", "::", " = ", " : ", " — ", " – ", " - ", "=", ":"]
_RE_TABLE_SEP = re.compile(r"^\s*\|?[\s\-:|]+\|?\s*$")
_HEADER_LEFT = {"vo", "terme", "termes", "source", "anglais", "english", "jp", "japonais",
                "en", "mot", "original", "nom", "name"}
_HEADER_RIGHT = {"fr", "français", "francais", "traduction", "trad", "french", "sens"}


def _clean(s: str) -> str:
    s = s.strip().strip("•-*–—\t ").strip()
    s = s.strip("«»\"'“”").strip()
    return re.sub(r"\*\*|__|`", "", s)


def _detect_section(line: str) -> str | None:
    s = line.strip().lstrip("#").strip().rstrip(":").strip()
    if len(s) > 45:
        return None
    for rx, cat in _SECTION_HINTS:
        if rx.search(s):
            return cat
    return None


def _detect_genre(*chunks: str) -> str | None:
    s = " ".join(chunks).lower()
    if re.search(r"(♀|\bf\b|fem|féminin|feminin|feminine|femme|fille|girl|woman)", s):
        return "féminin"
    if re.search(r"(♂|\bm\b|masc|masculin|masculine|homme|gar[çc]on|boy|\bman\b)", s):
        return "masculin"
    return None


def _split_pair(line: str):
    for sep in _SEPARATORS:
        if sep in line:
            left, right = line.split(sep, 1)
            left, right = _clean(left), _clean(right)
            if left and right:
                return left, right
    return None


def _to_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        if shutil.which("pandoc") is None:
            raise RuntimeError("Pandoc requis pour importer un glossaire .docx.")
        proc = subprocess.run(["pandoc", str(path), "--wrap=none", "-t", "gfm"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"Pandoc a échoué : {proc.stderr}")
        return proc.stdout
    raise RuntimeError(f"Format non géré pour un glossaire : {path.suffix} (.docx/.txt/.md)")


def parse_file(path: str | Path) -> dict:
    text = _to_text(Path(path))
    out = {"termes": [], "personnages": [], "anglicismes": []}
    section = "termes"

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if "|" in line and _RE_TABLE_SEP.match(line):
            continue
        # Ligne de tableau Word
        if line.lstrip().startswith("|") and line.count("|") >= 2:
            cells = [_clean(c) for c in line.strip().strip("|").split("|")]
            cells = [c for c in cells if c != ""]
            if len(cells) >= 2:
                if cells[0].lower() in _HEADER_LEFT or cells[1].lower() in _HEADER_RIGHT:
                    continue
                _add(out, section, cells[0], cells[1], cells[2] if len(cells) >= 3 else "")
            continue
        sec = _detect_section(line)
        if sec:
            section = sec
            continue
        pair = _split_pair(line)
        if pair:
            _add(out, section, pair[0], pair[1], "")
    return out


def _add(out: dict, section: str, term: str, fr: str, note: str) -> None:
    term, fr = _clean(term), _clean(fr)
    if not term or not fr:
        return
    if section == "anglicismes":
        out["anglicismes"].append({"vo": term, "fr": fr})
    elif section == "personnages":
        genre = _detect_genre(fr, note)
        if genre:
            entry = {"nom": term, "genre": genre}
            if note:
                entry["description"] = note
            out["personnages"].append(entry)
        else:  # pas de genre détectable → on traite comme un terme
            out["termes"].append({"nom": term, "description": fr})
    else:
        entry = {"nom": term, "description": " — ".join(x for x in (fr, note) if x)}
        out["termes"].append(entry)


def _merge(base: dict, new: dict) -> dict:
    added = {"termes": 0, "personnages": 0, "anglicismes": 0}
    base.setdefault("termes", []); base.setdefault("personnages", [])
    base.setdefault("anglicismes", [])

    seen_t = {(t.get("fr", "").lower(), t.get("vo", "").lower()) for t in base["termes"]}
    for t in new["termes"]:
        key = (t["fr"].lower(), t["vo"].lower())
        if key not in seen_t:
            base["termes"].append(t); seen_t.add(key); added["termes"] += 1

    seen_p = {p.get("nom", "").lower() for p in base["personnages"]}
    for p in new["personnages"]:
        if p["nom"].lower() not in seen_p:
            base["personnages"].append(p); seen_p.add(p["nom"].lower()); added["personnages"] += 1

    seen_a = {a.get("vo", "").lower() for a in base["anglicismes"]}
    for a in new["anglicismes"]:
        if a["vo"].lower() not in seen_a:
            base["anglicismes"].append(a); seen_a.add(a["vo"].lower()); added["anglicismes"] += 1
    return added


def import_into_project(project: str, file: str | Path, config: dict) -> tuple[Path, dict, dict]:
    from . import glossary_build
    sources = Path(config["chemins"]["sources"])
    gname = config["chemins"].get("glossaire_fichier", "glossaire.yaml")
    gpath = sources / project / gname
    parsed = parse_file(file)
    # Normalise vers le schéma catégorisé puis fusionne (dédoublonnage robuste).
    sectioned = glossary.to_sectioned(parsed)
    base = glossary.load(gpath) or glossary.empty()
    added = glossary_build.merge_notes(base, sectioned)
    glossary.save(base, gpath)
    return gpath, added, parsed
