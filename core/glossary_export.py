# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le glossaire **sort** — symétrique de `core/glossary_import.py`, qui n'avait pas de miroir.

## Ce que ce module ferme

Vérifié le 2026-09-05, avant d'écrire une ligne : la seule fonction du dépôt dont le nom
commençait par `export` était `tools/banc_sfx.py:exporter_crops`. Le glossaire s'importait
(`import_into_project`), se réintégrait (`reintegrer_dans_projet`) et s'optimisait
(`run_optimize`) — **il ne sortait pas**. C'est pourtant le différenciateur n° 1 du projet, le
glossaire persistant partagé roman ↔ manga, et le seul qui ne soit récupérable qu'en ouvrant
un fichier YAML à la main.

## Un format d'ARCHIVE, deux VUES — et la différence est écrite dans les fichiers

| Format | Statut | Aller-retour |
|---|---|---|
| `yaml` | **archive** | garanti, testé sur les glossaires réels du corpus |
| `csv` | **vue** | possible, avec une perte **nommée dans le fichier produit** |
| `md` | **vue** | pour une relecture humaine ; le réimporter ne rend que des paires |

⚠ **Un export non idempotent doit dire ce qu'il perd, dans le fichier lui-même.** Sans cela,
quelqu'un le réimportera dans six mois et perdra ses accords grammaticaux sans jamais le
savoir. C'est la seule raison pour laquelle `PERTES` existe, et pourquoi elle est écrite en
tête de chaque `.csv` et de chaque `.md` produits.

## La provenance, et pourquoi elle n'est pas décorative

Un glossaire exporté **circule**. Il part chez un relecteur, il revient trois mois plus tard,
il est fusionné avec un autre. La règle des chiffres du dépôt (`docs/chiffres-de-reference.md`)
dit qu'un chiffre sans dénominateur n'est pas une mesure ; un glossaire sans provenance n'est
pas un glossaire, c'est une liste de mots. Chaque fichier produit porte donc : l'œuvre, le tome
depuis lequel l'export a été demandé, la version d'Angelith, la date, le nombre d'entrées et la
**langue cible**.

## Ce qu'on ne fait JAMAIS ici

⚠ **On n'appelle pas `glossary.load` sur le fichier à exporter.** `load` MIGRE et RÉÉCRIT le
fichier qu'il ouvre. Exporter est une lecture ; une lecture qui modifie sa source serait le
seul geste irréversible de ce module. On passe donc par `yaml.safe_load` et par la conversion
en mémoire, exactement comme `glossary_import.lire_glossaire_yaml`, écrite pour cette raison.

⚠ **Et on ne touche pas au schéma.** Un export ne change pas ce qu'il exporte : ni
`glossary.ENTITY_CATS`, ni `glossary_cibles.CLE_CIBLES`, ni l'ordre des champs.
"""
from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import chemins, glossary, glossary_cibles
from .version import __version__

#: Le format qui fait foi. Les deux autres sont des vues.
ARCHIVE = "yaml"

#: Formats produits, avec l'extension et le libellé qu'une interface affiche.
FORMATS: tuple[tuple[str, str, str], ...] = (
    ("yaml", ".yaml", "YAML — format d'archive, aller-retour garanti"),
    ("csv", ".csv", "CSV — vue tabulaire, perte nommée dans le fichier"),
    ("md", ".md", "Markdown — vue de relecture, perte nommée dans le fichier"),
)

EXTENSIONS: dict[str, str] = {code: ext for code, ext, _ in FORMATS}


def est_archive(format: str) -> bool:
    """Ce format garantit-il l'aller-retour ? **La question que l'interface doit poser.**"""
    return format == ARCHIVE


#: Colonnes du CSV, dans l'ordre. `categorie` d'abord parce que c'est elle qui décide de tout
#: le reste — un `genre` n'a de sens que sur un personnage ou une créature.
COLONNES_CSV: tuple[str, ...] = (
    "categorie", "nom", "pluriel", "genre", "variantes", "interdits",
    "force", "traduire", "role", "termes_source", "description",
)

#: Séparateur des listes DANS une cellule. Le point-virgule est déjà le séparateur de colonnes
#: (celui qu'attend un Excel français) ; la barre verticale ne se rencontre dans aucun nom
#: propre du corpus, ce qui a été vérifié sur les 14 glossaires réels avant de la choisir.
SEP_LISTE = " | "

#: Ce que chaque format NE PORTE PAS. Écrite dans le fichier produit, pas seulement ici.
PERTES: dict[str, tuple[str, ...]] = {
    "yaml": (),
    "csv": (
        "les rendus des AUTRES langues cibles : le fichier ne porte que « {cible} », "
        "alors que le glossaire du dépôt les garde toutes",
        "les champs hors colonnes — « a_romaniser », et toute clé ajoutée à la main",
        "la différence entre un champ VIDE et un champ ABSENT : « role: '' » et un « role » "
        "jamais renseigné reviennent identiques (sans conséquence sur la traduction, les "
        "deux valant « rien à dire »)",
        "les commentaires et la mise en page du fichier YAML",
    ),
    "md": (
        "les rendus des AUTRES langues cibles : le fichier ne porte que « {cible} »",
        "les champs hors tableau — « a_romaniser », « termes_source », et toute clé "
        "ajoutée à la main",
        "la structure : réimporté, ce fichier n'est relu que par le parseur TOLÉRANT, qui "
        "ne reconnaît pas les colonnes par leur titre — une variante peut y atterrir en "
        "guise de description. Il se relit très bien à l'œil ; il ne se réimporte pas",
    ),
}


@dataclass(frozen=True)
class Provenance:
    """D'où vient ce fichier. Portée dans chaque export, quel que soit le format.

    ⚠ `tome` est le tome **depuis lequel l'export a été demandé**, pas le périmètre du
    glossaire : celui-ci est propre à l'ŒUVRE et vaut pour tous ses tomes. La distinction est
    écrite en toutes lettres dans l'en-tête produit, parce que quelqu'un qui reçoit
    « glossaire — Vol.3 » croira sinon n'avoir que le vocabulaire du Vol.3."""

    projet: str
    tome: str = ""
    cible: str = "fr"
    entrees: int = 0
    version: str = __version__
    date: str = ""

    @classmethod
    def maintenant(cls, projet: str, *, tome: str = "", cible: str = "fr",
                   entrees: int = 0) -> Provenance:
        return cls(projet=projet, tome=tome, cible=cible, entrees=entrees,
                   date=time.strftime("%Y-%m-%d"))

    def lignes(self, format: str) -> list[str]:
        """Les lignes de provenance, sans marqueur de commentaire — l'appelant préfixe."""
        depuis = f" (export demandé depuis « {self.tome} »)" if self.tome else ""
        sortie = [
            f"Glossaire de l'œuvre « {self.projet} »{depuis}",
            "Le glossaire est propre à l'ŒUVRE : il vaut pour TOUS ses tomes.",
            f"Exporté par Angelith {self.version} le {self.date}.",
            f"{self.entrees} entrée(s), langue cible « {self.cible} ».",
        ]
        pertes = PERTES.get(format, ())
        if not pertes:
            sortie.append("Format d'ARCHIVE : réimportable sans perte "
                          "(interface « Œuvres », ou run_manga.py --migrate-glossary).")
        else:
            sortie.append("⚠ VUE, PAS ARCHIVE — ce fichier NE PORTE PAS :")
            sortie += [f"  · {p.format(cible=self.cible)}" for p in pertes]
            sortie.append("Pour un aller-retour sans perte, exporte en YAML.")
        return sortie


# --------------------------------------------------------------------------- #
#  Lecture — sans jamais toucher au fichier source
# --------------------------------------------------------------------------- #

def lire_brut(chemin: str | Path) -> dict:
    """Le glossaire tel qu'il est SUR LE DISQUE, structure multi-cibles comprise.

    ⚠ Pas `glossary.load` : celui-ci migre et réécrit le fichier qu'il ouvre. Exporter ne doit
    rien modifier."""
    p = chemins.fichier_lisible(chemin, "glossaire à exporter")
    with open(p, encoding="utf-8") as fh:
        brut = yaml.safe_load(fh) or {}
    return brut if isinstance(brut, dict) else {}


def aplatir_pour(brut: dict, cible: str) -> dict:
    """La vue PLATE d'un glossaire brut pour une cible — la conversion de `glossary.load`,
    faite en mémoire."""
    return {cat: ([glossary_cibles.aplatir(e, cible) for e in entrees]
                  if cat in glossary.ENTITY_CATS and isinstance(entrees, list) else entrees)
            for cat, entrees in (brut or {}).items()}


def compter(brut: dict) -> int:
    """Entrées de toutes catégories confondues, y compris celles que `glossary.total`
    ignorerait (une section inconnue ajoutée à la main)."""
    return sum(len(v) for v in (brut or {}).values() if isinstance(v, list))


# --------------------------------------------------------------------------- #
#  Les trois écrivains
# --------------------------------------------------------------------------- #

def _entete_yaml(provenance: Provenance) -> str:
    lignes = ["# " + "=" * 60]
    lignes += [f"#  {ligne}" for ligne in provenance.lignes("yaml")]
    lignes += [
        "#  Structure MULTI-CIBLES conservée telle quelle : `cibles.<code>` porte le rendu",
        "#  de chaque langue, le reste de l'entrée décrit l'entité.",
        "# " + "=" * 60,
        "",
        "",
    ]
    return "\n".join(lignes)


def ecrire_yaml(brut: dict, destination: Path, provenance: Provenance) -> Path:
    """Le format d'ARCHIVE : la structure du dépôt, à l'identique, plus sa provenance.

    ⚠ Le corps est écrit par `glossary.save(deja_multi=True)` — **l'écrivain du dépôt**, pas
    un second. Deux écrivains du même format finiraient par ne plus produire le même fichier,
    et c'est précisément celui dont l'aller-retour est garanti."""
    glossary.save(brut, destination, cible=provenance.cible, deja_multi=True,
                  entete=_entete_yaml(provenance))
    return destination


def _cellule(valeur) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if isinstance(valeur, (list, tuple)):
        return SEP_LISTE.join(str(v) for v in valeur)
    return str(valeur)


def _rangs(plat: dict) -> list[dict]:
    """Une ligne par entrée, toutes catégories confondues, dans l'ordre du fichier."""
    rangs: list[dict] = []
    for cat in glossary.ORDER:
        for entree in (plat.get(cat) or []):
            if not isinstance(entree, dict):
                continue
            if cat == "anglicismes":
                # `{vo, fr}` : la forme VO est le nom, le remplacement la description. C'est
                # la seule catégorie dont le schéma n'a ni `nom` ni `description`.
                rangs.append({"categorie": cat, "nom": entree.get("vo", ""),
                              "description": entree.get("fr", "")})
            elif cat == "groupes":
                rangs.append({"categorie": cat, "nom": entree.get("nom", ""),
                              "description": entree.get("note", "")})
            else:
                rang = {"categorie": cat}
                for colonne in COLONNES_CSV[1:]:
                    if colonne in entree:
                        rang[colonne] = entree[colonne]
                rangs.append(rang)
    for cat, entrees in (plat or {}).items():          # sections inconnues éventuelles
        if cat in glossary.ORDER or not isinstance(entrees, list):
            continue
        for entree in entrees:
            if isinstance(entree, dict):
                rangs.append({"categorie": cat, "nom": entree.get("nom", ""),
                              "description": entree.get("description", "")})
    return rangs


def ecrire_csv(plat: dict, destination: Path, provenance: Provenance) -> Path:
    """Une VUE tabulaire, dont la perte est écrite en tête du fichier.

    ⚠ Les lignes de tête commencent par `#`, et `core/glossary_import.py` sait désormais les
    ignorer — c'est ce qui fait qu'un réimport rend le glossaire et non quatre entrées
    fantômes nommées « Angelith 2.28.0 »."""
    tampon = io.StringIO(newline="")
    for ligne in provenance.lignes("csv"):
        tampon.write(f"# {ligne}\n")
    tampon.write(f"# Séparateur de colonnes : « ; » · séparateur de liste : «{SEP_LISTE}»\n")
    ecrivain = csv.DictWriter(tampon, fieldnames=COLONNES_CSV, delimiter=";",
                              extrasaction="ignore", lineterminator="\n")
    ecrivain.writeheader()
    for rang in _rangs(plat):
        ecrivain.writerow({c: _cellule(rang.get(c)) for c in COLONNES_CSV})
    # ⚠ BOM UTF-8 : sans lui, Excel sous Windows lit un `.csv` en cp1252 et affiche « RÃ´le ».
    # C'est le seul format de ce module destiné à être ouvert par un tableur.
    destination.write_text(tampon.getvalue(), encoding="utf-8-sig")
    return destination


def ecrire_markdown(plat: dict, destination: Path, provenance: Provenance) -> Path:
    """Une VUE de relecture : ce qu'on envoie à un correcteur humain."""
    depuis = f" — {provenance.tome}" if provenance.tome else ""
    lignes = [f"# Glossaire — {provenance.projet}{depuis}", ""]
    lignes += [f"> {ligne}" for ligne in provenance.lignes("md")]
    lignes.append("")

    for cat in glossary.ORDER:
        entrees = plat.get(cat) or []
        if not entrees:
            continue
        titre = (glossary.ENTITY_CATS.get(cat) or {}).get("label") or cat.capitalize()
        lignes += [f"## {titre}", ""]
        if cat == "anglicismes":
            lignes += ["| VO | Remplacement |", "|---|---|"]
            lignes += [f"| {_md(e.get('vo'))} | {_md(e.get('fr'))} |"
                       for e in entrees if isinstance(e, dict)]
        elif cat == "groupes":
            lignes += ["| Groupe | Note |", "|---|---|"]
            lignes += [f"| {_md(e.get('nom'))} | {_md(e.get('note'))} |"
                       for e in entrees if isinstance(e, dict)]
        else:
            colonnes = ["Nom", "Genre", "Variantes", "Interdits", "Description"]
            lignes += ["| " + " | ".join(colonnes) + " |",
                       "|" + "|".join("---" for _ in colonnes) + "|"]
            for e in entrees:
                if not isinstance(e, dict):
                    continue
                description = " ; ".join(x for x in (e.get("role"), e.get("description")) if x)
                lignes.append("| " + " | ".join((
                    _md(e.get("nom")), _md(e.get("genre")), _md(e.get("variantes")),
                    _md(e.get("interdits")), _md(description))) + " |")
        lignes.append("")

    destination.write_text("\n".join(lignes).rstrip() + "\n", encoding="utf-8")
    return destination


def _md(valeur) -> str:
    """Une cellule Markdown : la barre verticale y est un séparateur, donc échappée."""
    return _cellule(valeur).replace("|", "\\|")


# --------------------------------------------------------------------------- #
#  Le point d'entrée
# --------------------------------------------------------------------------- #

def nom_propose(projet: str, tome: str, format: str, *, date: str = "") -> str:
    """« roman Q_glossaire_2026-09-05.yaml » — un nom qui se retrouve dans un dossier
    de téléchargements six mois plus tard."""
    date = date or time.strftime("%Y-%m-%d")
    tige = "_".join(x for x in (projet, tome, "glossaire", date) if x)
    return "".join(c for c in tige if c not in '<>:"/\\|?*') + EXTENSIONS.get(format, ".txt")


def exporter(source: str | Path, destination: str | Path, format: str = ARCHIVE, *,
             projet: str = "", tome: str = "", cible: str | None = None) -> Path:
    """Écrit `source` (un `glossaire.yaml` du dépôt) vers `destination`, dans `format`.

    Rend le chemin écrit. Ne modifie **jamais** `source`.

    `cible` est la langue de rendu à extraire pour les deux vues ; le YAML, lui, garde toutes
    les cibles — c'est ce qui en fait le format d'archive."""
    if format not in EXTENSIONS:
        raise ValueError(f"format d'export inconnu : {format!r} "
                         f"(connus : {', '.join(EXTENSIONS)})")
    source, destination = Path(source), Path(destination)
    brut = lire_brut(source)
    code = (cible or glossary.cible_du_run()).strip().lower()
    provenance = Provenance.maintenant(projet or source.parent.name, tome=tome, cible=code,
                                       entrees=compter(brut))
    destination.parent.mkdir(parents=True, exist_ok=True)

    if format == "yaml":
        return ecrire_yaml(brut, destination, provenance)
    plat = aplatir_pour(brut, code)
    if format == "csv":
        return ecrire_csv(plat, destination, provenance)
    return ecrire_markdown(plat, destination, provenance)
