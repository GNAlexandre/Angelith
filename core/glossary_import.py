# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Import d'un glossaire existant vers le glossaire YAML de l'œuvre.

Deux portes d'entrée, pour deux besoins distincts :

- `import_into_project` — un glossaire **rédigé à la main** (.docx / .txt / .md / .csv).
  Parseur tolérant : tables Word, séparateurs variés (=, :, →, tab, tiret), et sections
  (Personnages / Anglicismes / Termes). Un `.csv` **produit par `core/glossary_export.py`**
  est reconnu à ses colonnes et relu par un vrai lecteur CSV, avec ses catégories, ses
  genres, ses variantes et ses formes interdites ; tout autre `.csv` retombe sur le parseur
  tolérant.
- `reintegrer_dans_projet` — un glossaire **YAML du projet lui-même**, antérieur : un
  `.bak.yaml`, un export, une copie d'une installation précédente, le glossaire d'une œuvre
  sœur. C'est le chemin de récupération après la 2.0.0 : la migration automatique de
  `glossary.load` ne se déclenche que sur `sources/<Projet>/glossaire.yaml`, et un ancien
  glossaire rangé ailleurs n'est jamais lu par personne.
"""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from . import chemins, glossary, glossary_cibles

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
    # ⚠ `.csv` était ANNONCÉ importable par `gui/depot.py` (« le parseur tolérant accepte la
    # tabulation et le point-virgule ») et ne l'était PAS : il tombait ici sur un
    # `RuntimeError « Format non géré »`, et le point-virgule ne figure d'ailleurs pas dans
    # `_SEPARATORS`. Mesuré le 2026-09-05, étape 0.2 du `PLAN-34`. Le lot livrant un export
    # CSV, la promesse devait devenir vraie plutôt que d'être retirée : `parse_file` route
    # désormais le `.csv` vers un vrai lecteur CSV, et ce repli-ci ne sert qu'aux fichiers
    # dont l'en-tête n'est pas reconnu.
    if suffix in (".txt", ".md", ".csv"):
        return path.read_text(encoding="utf-8-sig", errors="replace")
    if suffix == ".docx":
        if shutil.which("pandoc") is None:
            raise RuntimeError("Pandoc requis pour importer un glossaire .docx.")
        # ⚠ Valider AVANT de lancer le sous-processus. L'appel est déjà en forme de liste,
        # donc sans interprétation par un shell — mais rien ne vérifiait que l'argument
        # désigne un fichier. Un dossier `mon-glossaire.docx/` faisait échouer Pandoc sur son
        # propre message, qui parle d'un format de document et non du chemin fautif.
        chemins.fichier_lisible(path, "glossaire .docx")
        proc = subprocess.run(["pandoc", str(path), "--wrap=none", "-t", "gfm"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"Pandoc a échoué : {proc.stderr}")
        return proc.stdout
    raise RuntimeError(f"Format non géré pour un glossaire : {path.suffix} "
                       f"(.docx/.txt/.md/.csv)")


#: Colonnes qui font reconnaître un CSV **produit par `core/glossary_export.py`**. Deux
#: suffisent : `categorie` n'existe dans aucun export d'un autre outil, et `nom` est la
#: colonne obligatoire du schéma.
_CSV_SIGNATURE = frozenset({"categorie", "nom"})

#: Séparateurs de colonnes qu'on tente, dans cet ordre. Le point-virgule d'abord : c'est
#: celui qu'écrit ce dépôt et celui qu'attend un Excel français.
_CSV_DELIMITEURS = (";", "\t", ",")


def _lignes_utiles(text: str):
    """Les lignes du fichier, **commentaires retirés**.

    ⚠ Une ligne qui commence par `#` sans être un titre de section reconnu n'est jamais une
    paire terme → traduction : c'est de la prose, ou un en-tête de provenance. Elle était
    pourtant passée à `_split_pair`, qui y trouvait un « — » et fabriquait une entrée de
    glossaire à partir d'une phrase — un `# Exporté par Angelith 2.28.0 — 2026-09-05`
    devenait le terme « Exporté par Angelith 2.28.0 ». Le lot 34 le corrige parce qu'il
    livre un export CSV dont l'en-tête dit ce qu'il perd, et qu'un en-tête d'avertissement
    qui se réimporte en fausses entrées serait pire que pas d'avertissement du tout."""
    for raw in text.splitlines():
        ligne = raw.rstrip()
        if not ligne.strip():
            continue
        depouillee = ligne.lstrip()
        if depouillee.startswith("#") and _detect_section(ligne) is None:
            continue
        # ⚠ Une citation Markdown est de la prose, toujours. C'est sous cette forme que
        # `glossary_export.ecrire_markdown` porte sa provenance et sa liste de pertes, et
        # sans cette ligne « Le glossaire est propre à l'ŒUVRE : il vaut pour tous ses
        # tomes. » se réimporterait comme le terme « Le glossaire est propre à l'ŒUVRE ».
        if depouillee.startswith(">"):
            continue
        yield ligne


def _valeurs(cellule: str) -> list[str]:
    """Une cellule de liste → la liste. Accepte le séparateur de l'export et la virgule."""
    brut = (cellule or "").replace("|", ",")
    return [v.strip() for v in brut.split(",") if v.strip()]


def _booleen(cellule: str):
    valeur = (cellule or "").strip().lower()
    if valeur in ("oui", "true", "vrai", "1"):
        return True
    if valeur in ("non", "false", "faux", "0"):
        return False
    return None


def parse_csv(text: str) -> dict | None:
    """Un CSV **produit par ce dépôt** → un glossaire complet ; `None` si ce n'en est pas un.

    Rendre `None` plutôt que d'échouer est délibéré : un `.csv` écrit à la main par quelqu'un
    d'autre a toutes les chances de n'être qu'un tableau à deux colonnes, et le parseur
    tolérant le lira mieux que ce lecteur-ci. On ne prend la main que sur ce qu'on
    reconnaît."""
    lignes = list(_lignes_utiles(text))
    if not lignes:
        return None
    for delimiteur in _CSV_DELIMITEURS:
        lecteur = csv.DictReader(lignes, delimiter=delimiteur)
        champs = {(c or "").strip().lower() for c in (lecteur.fieldnames or [])}
        if not _CSV_SIGNATURE <= champs:
            continue
        return _glossaire_depuis_csv(lecteur)
    return None


def _glossaire_depuis_csv(lecteur) -> dict:
    sortie = glossary.empty()
    for rang in lecteur:
        rang = {(k or "").strip().lower(): (v or "").strip()
                for k, v in rang.items() if k is not None}
        categorie = rang.get("categorie") or "termes"
        nom = _clean(rang.get("nom", ""))
        if not nom:
            continue
        if categorie == "anglicismes":
            sortie["anglicismes"].append({"vo": nom, "fr": rang.get("description", "")})
            continue
        if categorie == "groupes":
            sortie["groupes"].append({"nom": nom, "note": rang.get("description", "")})
            continue
        if categorie not in glossary.ENTITY_CATS:
            categorie = "termes"
        entree: dict = {"nom": nom}
        for colonne in ("pluriel", "genre", "role", "description"):
            if rang.get(colonne):
                entree[colonne] = rang[colonne]
        for colonne in ("variantes", "interdits", "termes_source"):
            valeurs = _valeurs(rang.get(colonne, ""))
            if valeurs:
                entree[colonne] = valeurs
        for colonne in ("force", "traduire"):
            valeur = _booleen(rang.get(colonne, ""))
            if valeur is not None:
                entree[colonne] = valeur
        sortie.setdefault(categorie, []).append(entree)
    return sortie


def parse_file(path: str | Path) -> dict:
    path = Path(path)
    text = _to_text(path)
    if path.suffix.lower() == ".csv":
        depuis_csv = parse_csv(text)
        if depuis_csv is not None:
            return depuis_csv

    out = {"termes": [], "personnages": [], "anglicismes": []}
    section = "termes"

    for line in _lignes_utiles(text):
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


#: Suffixe de la sauvegarde écrite avant un import de glossaire rédigé à la main.
#:
#: ⚠ Il manquait, et c'était le seul des trois chemins de réécriture du glossaire à ne pas en
#: avoir : `glossary.load` écrit `.avant-multicibles.bak` avant sa migration,
#: `reintegrer_dans_projet` écrit `.avant-reintegration.bak` avant la sienne, et l'import
#: écrasait sans filet. Or `sources/<Projet>/glossaire.yaml` est **partagé avec la brique light
#: novel** : une fusion malheureuse casse la cohérence de noms entre un roman et son manga, et
#: un glossaire est du travail humain accumulé sur plusieurs tomes.
SUFFIXE_IMPORT = ".avant-import.bak"


def sauvegarder(gpath: Path, suffixe: str) -> Path | None:
    """Copie `gpath` sous `gpath + suffixe`, **une seule fois**, et rend le chemin.

    ⚠ « Une seule fois » est l'invariant qui compte : un second import écraserait la
    sauvegarde par le résultat du premier, et l'état d'origine — celui qu'on cherche justement
    à pouvoir retrouver — serait définitivement perdu. Même règle que
    `reintegrer_dans_projet` et que la migration multi-cibles."""
    gpath = Path(gpath)
    if not gpath.exists():
        return None
    sauvegarde = chemins.derive(gpath, suffixe)
    if not sauvegarde.exists():
        sauvegarde.write_text(gpath.read_text(encoding="utf-8"), encoding="utf-8")
    return sauvegarde


def import_into_project(project: str, file: str | Path, config: dict) -> tuple[Path, dict, dict]:
    from . import glossary_build
    project = chemins.segment(project, "projet")
    sources = Path(config["chemins"]["sources"])
    gname = config["chemins"].get("glossaire_fichier", "glossaire.yaml")
    gpath = sources / project / gname
    parsed = parse_file(file)
    # Normalise vers le schéma catégorisé puis fusionne (dédoublonnage robuste).
    sectioned = glossary.to_sectioned(parsed)
    base = glossary.load(gpath) or glossary.empty()
    added = glossary_build.merge_notes(base, sectioned)
    # ⚠ La sauvegarde part AVANT `glossary.save`, et après `glossary.load` : celui-ci peut
    # avoir migré le fichier au format multi-cibles, auquel cas c'est le fichier migré — le
    # dernier état sain — qu'il faut garder. `glossary.load` a de toute façon écrit sa propre
    # sauvegarde `.avant-multicibles.bak` de l'état d'avant migration.
    sauvegarder(gpath, SUFFIXE_IMPORT)
    glossary.save(base, gpath)
    return gpath, added, parsed


# --------------------------------------------------------------------------- #
#  Réintégration d'un glossaire YAML antérieur (--migrate-glossary)
# --------------------------------------------------------------------------- #
#: Suffixe de la sauvegarde écrite avant de remplacer le glossaire d'un projet.
SUFFIXE_SAUVEGARDE = ".avant-reintegration.bak"


def lire_glossaire_yaml(chemin: str | Path, cible: str) -> tuple[dict, bool, int]:
    """Lit un glossaire YAML **sans jamais toucher au fichier**, à plat pour `cible`.

    ⚠ C'est toute la raison d'être de cette fonction. `glossary.load` migre ET RÉÉCRIT le
    fichier qu'il ouvre : l'appeler sur un `.bak`, un export ou le glossaire d'une autre
    œuvre modifierait la source qu'on est justement venu récupérer. Ici la migration se fait
    **en mémoire**, et le fichier d'entrée reste bit pour bit ce qu'il était.

    Renvoie `(glossaire plat, était_à_l_ancien_format, nombre d'entrées migrées)`."""
    p = Path(chemin)
    if not p.exists():
        raise RuntimeError(f"Glossaire introuvable : {p}")
    with open(p, encoding="utf-8") as fh:
        brut = yaml.safe_load(fh) or {}
    if not brut:
        return {}, False, 0
    ancien = glossary_cibles.besoin_de_migration(brut)
    migrees = 0
    if ancien:
        brut, migrees = glossary_cibles.migrer(brut, cible)
    plat = {cat: ([glossary_cibles.aplatir(e, cible) for e in entrees]
                  if cat in glossary.ENTITY_CATS and isinstance(entrees, list) else entrees)
            for cat, entrees in brut.items()}
    return plat, ancien, migrees


def reintegrer_dans_projet(project: str, fichiers: list[str | Path], config: dict, *,
                           remplacer: bool = False,
                           dry_run: bool = False) -> tuple[Path, dict, list[dict]]:
    """Réintègre un ou plusieurs glossaires antérieurs dans celui d'une ŒUVRE.

    Les fichiers réintégrés FONT AUTORITÉ, dans l'ordre donné : le premier sert de base, les
    suivants ne font que l'enrichir. C'est la sémantique de « je récupère mon ancien
    glossaire pour le réutiliser » — s'ils étaient fusionnés par-dessus, le fichier en place
    (souvent celui qu'on cherche justement à réparer) primerait sur le travail à restaurer.

    Le glossaire actuel du projet est fusionné EN DERNIER, donc avec la priorité la plus
    basse : ce que le projet a accumulé depuis n'est pas perdu pour autant. `remplacer=True`
    l'ignore complètement — cas de récupération, quand c'est lui qui est abîmé ; il part
    quand même en sauvegarde avant d'être écrasé.

    Renvoie `(chemin de destination, compteurs de fusion, rapport par fichier)`."""
    from . import glossary_build
    project = chemins.segment(project, "projet")
    sources = Path(config["chemins"]["sources"])
    gname = config["chemins"].get("glossaire_fichier", "glossaire.yaml")
    gpath = sources / project / gname
    cible = glossary.cible_du_run()

    lus = [(Path(f), *lire_glossaire_yaml(f, cible)) for f in fichiers]
    for chemin, _, _, _ in lus:
        if chemin.resolve() == gpath.resolve() and not remplacer:
            # Se fusionner soi-même n'ajoute rien et doublerait le rapport ; le cas utile
            # (migrer un glossaire sur place) passe par la seule lecture, plus bas.
            remplacer = True

    base = glossary.empty()
    rapport: list[dict] = []
    index = glossary_build.build_index(base)
    for chemin, plat, ancien, migrees in lus:
        added = glossary_build.fusionner_glossaire(base, plat, index=index)
        rapport.append({"fichier": chemin, "ancien": ancien, "migrees": migrees,
                        "lues": glossary.total(plat), **added})

    if not remplacer and gpath.exists():
        actuel = glossary.load(gpath) or glossary.empty()
        added = glossary_build.fusionner_glossaire(base, actuel, index=index)
        rapport.append({"fichier": gpath, "ancien": False, "migrees": 0,
                        "lues": glossary.total(actuel), **added})

    total = {"ajouts": 0, "fusions": 0, "conflits": 0}
    for r in rapport:
        for k in total:
            total[k] += r[k]
    total["entrees"] = glossary.total(base)
    total["sauvegarde"] = None

    if not dry_run:
        # ⚠ Jamais deux fois — cf. `sauvegarder`, qui porte l'invariant pour les deux chemins.
        total["sauvegarde"] = sauvegarder(gpath, SUFFIXE_SAUVEGARDE)
        glossary.save(base, gpath, cible=cible)
    return gpath, total, rapport
