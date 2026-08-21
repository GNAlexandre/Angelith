# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Extraction de texte + images depuis .docx, .pdf, .epub, .txt et .md.

L'EPUB a son propre module, `pipeline/epub.py` — sa docstring explique pourquoi
Pandoc, pourtant déjà requis ici pour les .docx, ne convient pas à ce format.

Renvoie un texte « markdown-léger » :
- titres conservés (`#`, `##`, …) pour la détection de chapitres ;
- images remplacées par un marqueur sur sa propre ligne : `<!-- IMG: <chemin relatif> -->`.

Les fichiers images sont écrits dans `media_dir`. Les chemins des marqueurs sont
relatifs à `media_dir.parent` (donc de la forme `media/xxx.png`).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import formatting

# Défauts de détection par mise en forme (police+gras), utilisés si `config.yaml >
# decoupage.mise_en_forme` ne fournit pas (ou que partiellement) ces clés — voir
# `_extract_pdf`/`_extract_docx`.
_DEFAULT_FORMAT_CFG = {
    "ratio_taille_titre": 1.10,
    "footer_frac_pages": 0.30,
    "footer_bande_page": 0.10,
    "titres_exclus": [
        "Table of Contents", "Contents", "Copyright", "Cover", "Title Page",
        "Illustrations", "Color Illustrations", "Table des matières",
    ],
}


def _is_bold_span(span: dict) -> bool:
    return "bold" in span.get("font", "").lower() or bool(span.get("flags", 0) & 16)


def _normalize_repeat_key(text: str) -> str:
    """Clé de récurrence pour le FILIGRANE/pied de page (chiffres → « # », casse/
    espaces normalisés) : un numéro de page change à chaque occurrence, donc « Page 5 »
    et « Page 217 » doivent être reconnus comme LE MÊME gabarit répété."""
    key = re.sub(r"\d+", "#", text.strip().lower())
    return re.sub(r"\s+", " ", key)


def _normalize_exact_key(text: str) -> str:
    """Clé de récurrence EXACTE (casse/espaces normalisés, chiffres CONSERVÉS) pour
    détecter un sous-titre décoratif répété (ex. « Miss Medic's Diary at War ») sans
    confondre de vrais titres distincts qui contiennent un numéro (« Year 1938,
    Summer 1 » vs « Summer 2 » ne doivent PAS être vus comme des doublons)."""
    return re.sub(r"\s+", " ", text.strip().lower())


IMG_MARKER = "<!-- IMG: {} -->"
# Tolère les espaces dans le chemin (Pandoc le fait quand le dossier en contient),
# un éventuel titre "..." et des chevrons <...>. Le groupe 2 capture les attributs
# Pandoc (ex. {width="2.5in" height="1.46in"}) : la TAILLE D'AFFICHAGE d'origine du
# document source, sinon perdue (l'image ressortirait à sa taille native = souvent
# bien trop grande pour un simple séparateur).
_IMG_RE = re.compile(r"!\[[^\]]*\]\(\s*(.+?)\s*\)(\{[^}]*\})?", re.DOTALL)


def make_marker(path: str, attrs: str = "") -> str:
    """Construit un marqueur IMG, avec la taille d'origine encodée si connue
    (`path|{width=... height=...}`) — voir `split_marker` pour le sens inverse."""
    return IMG_MARKER.format(f"{path}|{attrs}" if attrs else path)


def split_marker(raw: str) -> tuple[str, str]:
    """Sépare un contenu de marqueur `path` ou `path|attrs` → (path, attrs)."""
    if "|" in raw:
        path, attrs = raw.split("|", 1)
        return path.strip(), attrs.strip()
    return raw.strip(), ""


@dataclass
class Extracted:
    text: str
    images: list[str] = field(default_factory=list)  # chemins relatifs, dans l'ordre
    # Lectures (furigana) relevées par l'extracteur : graphie source → prononciation.
    # Seul l'EPUB en produit — c'est le seul format qui porte l'information de façon
    # structurée. Vide partout ailleurs, sans conséquence pour les appelants.
    lectures: dict[str, str] = field(default_factory=dict)
    # Ce que l'extraction a dû laisser passer (image référencée mais introuvable…).
    # Remonté jusqu'aux avertissements du plan de tome, plutôt qu'imprimé ici : ce module
    # n'a pas de reporter, et un `print` perdu dans une extraction parallèle ne se voit pas.
    avertissements: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  DOCX  (Pandoc fait le gros du travail : titres + extraction des médias)
# --------------------------------------------------------------------------- #
_HEADING_STYLE_RE = re.compile(r"^(?:heading|titre)\s*([12])$", re.I)


def _docx_effective_size(run, paragraph) -> float | None:
    """Taille du run en points, avec repli sur la chaîne de styles (`base_style`)
    quand le run hérite sa taille du style plutôt que de la définir lui-même."""
    if run.font.size is not None:
        return run.font.size.pt
    style = paragraph.style
    while style is not None:
        if style.font.size is not None:
            return style.font.size.pt
        style = style.base_style
    return None


def _docx_effective_bold(run, paragraph) -> bool:
    if run.font.bold is not None:
        return bool(run.font.bold)
    style = paragraph.style
    while style is not None:
        if style.font.bold is not None:
            return bool(style.font.bold)
        style = style.base_style
    return False


def _docx_heading_candidates(path: Path, format_cfg: dict | None = None) -> list[tuple[str, int]]:
    """Candidats titre, DANS L'ORDRE du document : (texte, niveau 1|2). Deux sources
    unifiées — paragraphes déjà stylés Heading/Titre 1|2 (signal redondant avec ce
    que Pandoc produit déjà, gardé pour que le curseur de `_promote_docx_headings`
    avance correctement) et paragraphes NON stylés mais ≥80% gras et de taille dans
    un des ≤2 paliers détectés au-dessus du corps de texte."""
    import docx  # import paresseux, comme `fitz` pour le PDF

    cfg = {**_DEFAULT_FORMAT_CFG, **(format_cfg or {})}
    excluded_titles = {t.strip().lower() for t in cfg["titres_exclus"]}
    d = docx.Document(str(path))

    size_weights: list[tuple[float, int]] = []
    bold_sizes: list[float] = []
    para_info: list[tuple[str, int | None, float, float]] = []  # texte, niveau stylé, taille, ratio gras

    for para in d.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        m = _HEADING_STYLE_RE.match((para.style.name or "").strip()) if para.style else None
        style_level = int(m.group(1)) if m else None

        chars = bold_chars = 0
        sizes: list[tuple[float, int]] = []
        for run in para.runs:
            n = len(run.text)
            if n == 0:
                continue
            chars += n
            if _docx_effective_bold(run, para):
                bold_chars += n
            size = _docx_effective_size(run, para)
            if size is not None:
                sizes.append((size, n))
        if chars == 0:
            continue
        size = max((s for s, _ in sizes), default=0.0)
        bold_ratio = bold_chars / chars
        if style_level is None:  # ne pollue pas les stats de paliers avec les titres déjà stylés
            size_weights.append((size, chars))
            if bold_ratio >= 0.8:
                bold_sizes.append(size)
        para_info.append((text, style_level, size, bold_ratio))

    body = formatting.body_size(size_weights)
    tiers = formatting.cluster_heading_tiers(bold_sizes, body, cfg["ratio_taille_titre"])

    candidates: list[tuple[str, int]] = []
    for text, style_level, size, bold_ratio in para_info:
        if style_level is not None:
            candidates.append((text, style_level))
            continue
        if bold_ratio < 0.8 or len(text) > 120:
            continue
        if text.strip().lower() in excluded_titles:
            continue
        for level, tier_size in enumerate(tiers, start=1):
            if abs(size - tier_size) <= 0.5:
                candidates.append((text, level))
                break
    return candidates


def _normalize_for_match(s: str) -> str:
    """Neutralise ce que Pandoc peut changer par rapport au texte brut python-docx :
    un `#`+ déjà présent, l'emphase Markdown en tête/fin (`**gras**` — Pandoc
    enveloppe tout run en gras), l'échappement (`\\*`, `\\[`…), les guillemets
    typographiques, la casse/les espaces — pour un appariement texte fiable."""
    s = re.sub(r"^#{1,6}\s*", "", s.strip())
    s = re.sub(r"^[*_]{1,3}", "", s)
    s = re.sub(r"[*_]{1,3}$", "", s)
    s = s.replace("\\", "")
    s = s.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"}))
    return re.sub(r"\s+", " ", s).strip().lower()


def _promote_docx_headings(md: str, candidates: list[tuple[str, int]]) -> str:
    """Balayage SÉQUENTIEL à curseur croissant : pour chaque candidat, cherche la
    PROCHAINE ligne du markdown Pandoc dont le texte normalisé correspond, et la
    préfixe `#`/`##` si elle ne l'est pas déjà. Un candidat non retrouvé (déphasage
    Pandoc, ré-échappement inattendu…) est ignoré silencieusement — l'extraction ne
    doit jamais planter là-dessus."""
    lines = md.splitlines()
    normalized = [_normalize_for_match(ln) for ln in lines]
    cursor = 0
    for text, level in candidates:
        target = _normalize_for_match(text)
        if not target:
            continue
        for i in range(cursor, len(lines)):
            if normalized[i] == target:
                if not re.match(r"^#{1,6}\s+\S", lines[i]):
                    # Retire une emphase Markdown qui enveloppe TOUTE la ligne (Pandoc
                    # rend un run en gras en `**texte**`) — redondante une fois le
                    # titre promu (le style de titre porte déjà le gras).
                    content = re.sub(r"^([*_]{1,3})(.*)\1$", r"\2", lines[i].strip())
                    lines[i] = f"{'#' * level} {content}"
                cursor = i + 1
                break
    return "\n".join(lines)


def _extract_docx(path: Path, media_dir: Path, extract_images: bool = True,
                   format_cfg: dict | None = None) -> Extracted:
    if shutil.which("pandoc") is None:
        raise RuntimeError("Pandoc requis pour lire les .docx.")
    cmd = ["pandoc", str(path), "--wrap=none", "-t", "markdown"]
    if extract_images:
        media_dir.mkdir(parents=True, exist_ok=True)
        cmd += ["--extract-media", str(media_dir.parent)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"Pandoc a échoué sur {path.name} :\n{proc.stderr}")
    md = proc.stdout or ""

    try:
        candidates = _docx_heading_candidates(path, format_cfg)
        if candidates:
            md = _promote_docx_headings(md, candidates)
    except Exception:
        pass  # passe supplémentaire, ne doit jamais faire échouer l'extraction elle-même

    images: list[str] = []

    def _repl(m: re.Match) -> str:
        if not extract_images:
            # Langue de référence seule (pas la source des images) : on retire
            # juste la syntaxe markdown, sans rien écrire sur le disque — élimine
            # tout risque de collision de noms de fichiers entre langues.
            return ""
        raw = m.group(1).strip()
        raw = re.sub(r'\s+"[^"]*"$', "", raw)  # retire un éventuel titre "…"
        raw = raw.strip("<>")
        # Pandoc écrit un chemin complet (avec dossiers/espaces) ; on ne garde que media/<nom>
        rel = f"media/{Path(raw).name}"
        images.append(rel)
        attrs = (m.group(2) or "").strip()     # taille d'affichage d'origine ({width=... height=...})
        return "\n" + make_marker(rel, attrs) + "\n"

    md = _IMG_RE.sub(_repl, md)
    return Extracted(text=md, images=images)


# --------------------------------------------------------------------------- #
#  PDF  (PyMuPDF : texte en ordre de lecture + images interfoliées par position)
# --------------------------------------------------------------------------- #
def _extract_pdf(path: Path, media_dir: Path, extract_images: bool = True,
                  format_cfg: dict | None = None) -> Extracted:
    import fitz  # PyMuPDF

    cfg = {**_DEFAULT_FORMAT_CFG, **(format_cfg or {})}
    excluded_titles = {t.strip().lower() for t in cfg["titres_exclus"]}

    if extract_images:
        media_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(path)
    n_pages = doc.page_count
    # Un seul appel PyMuPDF par page, réutilisé pour la passe stats ET la passe
    # d'émission (corps de texte/paliers de titre/filigrane sont des propriétés
    # globales au document, donc 2 passes logiques sont nécessaires — mais 1 seul
    # parcours MuPDF suffit).
    page_dicts = [page.get_text("dict") for page in doc]

    # ---- Passe A : statistiques globales (corps de texte, paliers, filigrane) ----
    size_weights: list[tuple[float, int]] = []                 # pour formatting.body_size
    bold_sizes: list[float] = []                                # candidats palier de titre
    block_info: dict[tuple[int, int], dict] = {}                # (pno, bi) -> infos du bloc
    repeat_pages: dict[str, set[int]] = defaultdict(set)        # clé normalisée -> pages vues

    for pno, pd in enumerate(page_dicts):
        page_height = pd.get("height") or doc[pno].rect.height
        band = page_height * cfg["footer_bande_page"]
        for bi, b in enumerate(pd.get("blocks", [])):
            if b.get("type", 0) != 0:
                continue
            spans = [span for line in b.get("lines", []) for span in line.get("spans", [])]
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            chars = sum(len(span.get("text", "")) for span in spans) or 1
            bold_chars = sum(len(span.get("text", "")) for span in spans if _is_bold_span(span))
            is_bold = bold_chars / chars >= 0.8
            size = max((span.get("size", 0.0) for span in spans), default=0.0)
            bbox = b.get("bbox", [0, 0, 0, 0])
            in_footer_band = bbox[1] < band or bbox[3] > page_height - band
            size_weights.append((size, chars))
            if is_bold:
                bold_sizes.append(size)
            block_info[(pno, bi)] = {
                "text": text, "size": size, "bold": is_bold, "footer_band": in_footer_band,
            }
            repeat_pages[_normalize_repeat_key(text)].add(pno)

    body = formatting.body_size(size_weights)
    tiers = formatting.cluster_heading_tiers(bold_sizes, body, cfg["ratio_taille_titre"])

    footer_threshold = max(2, round(n_pages * cfg["footer_frac_pages"]))
    footer_keys = {key for key, pages in repeat_pages.items() if len(pages) >= footer_threshold}

    # Doublons EXACTS de texte à un palier de titre (hors filigrane) : un sous-titre
    # décoratif répété n'est jamais un vrai titre de chapitre/partie unique.
    tier_dup_counts: dict[str, int] = defaultdict(int)
    for info in block_info.values():
        if info["bold"] and len(info["text"]) <= 120 and any(
                abs(info["size"] - t) <= 0.5 for t in tiers):
            tier_dup_counts[_normalize_exact_key(info["text"])] += 1

    heading_tier: dict[tuple[int, int], int] = {}
    footer_blocks: set[tuple[int, int]] = set()
    for key, info in block_info.items():
        footer_key = _normalize_repeat_key(info["text"])
        if info["footer_band"] and footer_key in footer_keys:
            footer_blocks.add(key)
            continue
        if not info["bold"] or len(info["text"]) > 120:
            continue
        if info["text"].strip().lower() in excluded_titles:
            continue
        if tier_dup_counts[_normalize_exact_key(info["text"])] >= 2:
            continue  # sous-titre décoratif répété (ex. "Miss Medic's Diary at War")
        for level, tier_size in enumerate(tiers, start=1):
            if abs(info["size"] - tier_size) <= 0.5:
                heading_tier[key] = level
                break

    # ---- Passe B : émission (logique existante, réutilise page_dicts déjà calculé) ----
    out_lines: list[str] = []
    images: list[str] = []
    seen_xref: dict[int, str] = {}
    stem = path.stem.replace(" ", "_")

    for pno, page in enumerate(doc):
        pd = page_dicts[pno]
        items: list[tuple[float, float, str, object]] = []
        # Blocs texte (ordre de lecture par position) : filigrane/pied de page retiré
        # entièrement, titre détecté par mise en forme promu en `#`/`##`.
        for bi, b in enumerate(pd.get("blocks", [])):
            if b.get("type", 0) != 0 or (pno, bi) in footer_blocks:
                continue
            info = block_info.get((pno, bi))
            if info is None:
                continue
            bbox = b.get("bbox", [0, 0, 0, 0])
            txt = info["text"]
            level = heading_tier.get((pno, bi))
            if level:
                txt = f"{'#' * level} {txt}"
            items.append((bbox[1], bbox[0], "text", txt))
        # Images de la page, localisées par leur rectangle (si on les garde).
        if extract_images:
            for im in page.get_images(full=True):
                xref = im[0]
                try:
                    rects = page.get_image_rects(xref) or [None]
                except Exception:
                    rects = [None]
                for r in rects:
                    y = r.y0 if r is not None else 1e9
                    x = r.x0 if r is not None else 0
                    items.append((y, x, "image", (xref, r)))

        for _, _, kind, payload in sorted(items, key=lambda t: (round(t[0]), round(t[1]))):
            if kind == "text":
                out_lines.append(payload)
                continue
            xref, rect = payload
            if xref in seen_xref:
                out_lines.append("\n" + seen_xref[xref] + "\n")
                continue
            try:
                info = doc.extract_image(xref)
            except Exception:
                continue
            ext = info.get("ext", "png")
            rel = f"media/{stem}_p{pno + 1}_x{xref}.{ext}"
            (media_dir / Path(rel).name).write_bytes(info["image"])
            # Taille d'AFFICHAGE d'origine sur la page (le rectangle, en points PDF
            # → pouces), pas la taille native du fichier — sinon l'image ressort à
            # sa résolution native, potentiellement bien plus grande que voulu.
            attrs = ""
            if rect is not None and rect.width > 0 and rect.height > 0:
                attrs = f'{{width="{rect.width / 72:.3f}in" height="{rect.height / 72:.3f}in"}}'
            marker = make_marker(rel, attrs)
            seen_xref[xref] = marker
            images.append(rel)
            out_lines.append("\n" + marker + "\n")

        out_lines.append("")  # séparation de page

    doc.close()
    return Extracted(text="\n".join(out_lines), images=images)


# --------------------------------------------------------------------------- #
#  TXT / MD
# --------------------------------------------------------------------------- #
_MARQUEUR_RE = re.compile(r"<!-- IMG: (.*?) -->")


def _extract_texte(path: Path, media_dir: Path, *, extract_images: bool = True) -> Extracted:
    """Un `.txt`/`.md` — et, s'il en porte, les images que ses marqueurs désignent.

    Cette branche renvoyait le texte seul. Un marqueur `<!-- IMG: media/x.png -->` y
    survivait donc dans le texte sans que le FICHIER ne soit jamais copié dans `media_dir`,
    et `render.py` appelle Pandoc avec `--resource-path .` depuis le build : l'image sortait
    manquante, en silence. Le défaut vaut pour tout `.md` écrit à la main, pas seulement pour
    ceux que produit `run_ocr.py`.

    Les chemins sont résolus **relativement au dossier du document** — c'est la seule
    convention qui permette de déplacer une source sans la casser — et recopiés à plat dans
    `media_dir`, comme le font déjà les extracteurs DOCX et PDF."""
    texte = path.read_text(encoding="utf-8")
    if not extract_images:
        return Extracted(text=texte)

    images: list[str] = []
    absentes: list[str] = []
    for trouve in _MARQUEUR_RE.finditer(texte):
        rel, _attrs = split_marker(trouve.group(1))
        if not rel:
            continue
        source = (path.parent / rel).resolve()
        if not source.is_file():
            absentes.append(rel)
            continue
        media_dir.mkdir(parents=True, exist_ok=True)
        cible = media_dir / Path(rel).name
        if not cible.exists() or cible.stat().st_mtime < source.stat().st_mtime:
            shutil.copy2(source, cible)
        if rel not in images:
            images.append(rel)

    avertissements = []
    if absentes:
        # Le marqueur est CONSERVÉ dans le texte : le retirer masquerait la perte, alors
        # qu'un trou visible dans le rendu se remarque et se corrige.
        avertissements.append(
            f"{path.name} : {len(absentes)} image(s) référencée(s) mais introuvable(s) "
            f"({', '.join(absentes[:3])}{'…' if len(absentes) > 3 else ''})")
    return Extracted(text=texte, images=images, avertissements=avertissements)


# --------------------------------------------------------------------------- #
def extract(path: str | Path, media_dir: str | Path, extract_images: bool = True,
            format_cfg: dict | None = None, epub_cfg: dict | None = None) -> Extracted:
    """`format_cfg` : `config.yaml > decoupage.mise_en_forme` (seuils de détection de
    titre par police+gras et de filigrane) — voir `_DEFAULT_FORMAT_CFG` pour les
    valeurs par défaut si absent/partiel. `epub_cfg` : `config.yaml > decoupage.epub`."""
    path = Path(path)
    media_dir = Path(media_dir)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _extract_docx(path, media_dir, extract_images=extract_images, format_cfg=format_cfg)
    if suffix == ".pdf":
        return _extract_pdf(path, media_dir, extract_images=extract_images, format_cfg=format_cfg)
    if suffix == ".epub":
        # Import PARESSEUX, comme `docx` et `fitz` plus haut — et ici il est en plus
        # nécessaire : `pipeline.epub` importe `Extracted`/`make_marker` de ce module, donc un
        # import en tête de fichier serait circulaire.
        from . import epub
        return epub.extract_epub(path, media_dir, extract_images=extract_images,
                                 epub_cfg=epub_cfg)
    if suffix in (".txt", ".md"):
        return _extract_texte(path, media_dir, extract_images=extract_images)
    raise RuntimeError(
        f"Format non pris en charge : {path.name} (docx, pdf, epub, txt, md attendus)")


def strip_images(text: str) -> str:
    """Retire les marqueurs d'images (texte propre pour les sources de référence)."""
    return re.sub(r"^\s*<!-- IMG: .*? -->\s*$", "", text, flags=re.MULTILINE)
