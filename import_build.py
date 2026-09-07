# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Réintégrer un tome corrigé par quelqu'un d'autre. **Décide, n'écrit pas sans qu'on le dise.**

## Le geste que ce module rend possible

Donner un manga à un tiers pour qu'il le corrige, puis récupérer son travail. Jusqu'ici, le
seul artefact du dépôt qui faisait l'aller-retour sans perte était `glossaire.yaml` : rien ne
savait empaqueter ni relire un TOME.

## ⚠ Ce qu'un `build/` pèse réellement — mesuré le 2026-09-06

Sur les 10 tomes manga du corpus, **16,54 Go** au total :

| partie | poids | part | fichiers |
|---|---:|---:|---:|
| `pages_psd` | 10 757 Mo | 65,1 % | 1 094 |
| `pages_out` | 1 945 Mo | 11,8 % | 1 094 |
| `pages_clean` | 1 911 Mo | 11,6 % | 1 094 |
| racine (cbz, pdf, rapport) | 1 888 Mo | 11,4 % | 35 |
| **`.checkpoints`** | **23 Mo** | **0,1 %** | **10 852** |

**Le travail humain est 0,1 % du poids et 72 % des fichiers.** Un tome pèse de 0,7 à 3,3 Go ;
ses checkpoints, de 0,3 à 4,0 Mo — un rapport de 500 à 1 500×.

C'est pourquoi l'import **ne copie que les checkpoints par défaut**. Les planches rendues sont
une case à cocher séparée : transférer 3 Go pour 4 Mo de corrections doit être un choix
explicite, pas un défaut.

## Les trois refus, avant toute écriture

1. **`projet` ou `tome` différents** — on n'installe pas le tome d'un autre par mégarde ;
2. **`FORMAT_VERSION` des `regions.json` ≠ celui du dépôt.** ⚠ C'est le refus qui compte.
   L'ordre persisté dans `regions.json` est le pivot : `ocr.json` et `traduction.json` s'y
   alignent **par position** (`manga/checkpoints.py`). Installer un cache d'une autre version
   ferait atterrir les traductions dans les mauvaises bulles, **silencieusement** ;
3. **un run en cours** — même refus que `core/reparations.py`, et pour la même raison.

## Ce qui n'est jamais fait

- **rien n'est supprimé.** Ce qui existe localement et n'est pas dans le paquet reste ;
- **rien n'est écrasé sans sauvegarde.** Ce qui est remplacé part d'abord dans
  `build/<P>/<T>/manga/.avant-import-<date>/` — même geste que
  `core/glossary_import.sauvegarder()` et son `.avant-import.bak` ;
- **rien n'est écrit tant que `appliquer()` n'est pas appelé.** `planifier()` ne fait que lire.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from manga import checkpoints as ck
from manga import projet as projet_mod

#: Où part ce qu'un import remplace. Daté, jamais réutilisé : deux imports le même jour
#: écrivent dans le même dossier, ce qui est le comportement voulu — c'est la journée qu'on
#: veut pouvoir défaire, pas la minute.
DOSSIER_SAUVEGARDE = ".avant-import"

#: Les fichiers d'une planche qui portent du travail HUMAIN ou décident du rendu. C'est la
#: liste que `manga/projet.py` suit déjà pour son empreinte (`_SUIVIS`) : la reprendre plutôt
#: que d'en écrire une seconde est ce qui garantit qu'un fichier ajouté demain sera compté des
#: deux côtés.
SUIVIS: tuple[str, ...] = projet_mod._SUIVIS                              # noqa: SLF001

#: Les états d'une planche, du point de vue de l'import.
IDENTIQUE = "identique"
MODIFIEE = "modifiee"
AJOUTEE = "ajoutee"
ABSENTE = "absente"

#: Ce que chaque état veut dire, en une phrase, pour l'humain qui lit l'aperçu.
PHRASES_ETAT = {
    IDENTIQUE: "inchangée — rien à écrire",
    MODIFIEE: "corrigée dans le paquet — sera remplacée (l'ancienne est sauvegardée)",
    AJOUTEE: "absente ici — sera ajoutée",
    ABSENTE: "présente ici, absente du paquet — ⚠ CONSERVÉE, jamais supprimée",
}


class RefusDImporter(RuntimeError):
    """Message destiné à être affiché tel quel."""


@dataclass(frozen=True)
class Planche:
    """Une planche, et ce que l'import lui ferait."""

    index: int
    etat: str
    motifs: tuple[str, ...] = ()

    @property
    def sera_ecrite(self) -> bool:
        return self.etat in (MODIFIEE, AJOUTEE)


@dataclass(frozen=True)
class Plan:
    """Ce qu'un import ferait, **avant** de le faire.

    `refus` — non vide ⇒ rien ne sera écrit, et la phrase dit pourquoi.
    `planches` — l'état de chacune.
    `avec_rendus` — la case à cocher : les `pages_out/`, `pages_clean/` et `pages_psd/`.
    """

    source: Path
    cible: Path
    projet: str = ""
    tome: str = ""
    planches: tuple[Planche, ...] = ()
    refus: str = ""
    avec_rendus: bool = False
    octets_checkpoints: int = 0
    octets_rendus: int = 0
    motifs_par_planche: dict = field(default_factory=dict)

    @property
    def executable(self) -> bool:
        return not self.refus and any(p.sera_ecrite for p in self.planches)

    def compte(self, etat: str) -> int:
        return sum(1 for p in self.planches if p.etat == etat)

    def annonce(self) -> str:
        """L'aperçu, en une phrase. ⚠ Il nomme ce qui CHANGE, pas ce qui existe : « 150
        planches » ne dit rien à qui veut savoir ce qu'il s'apprête à écraser."""
        if self.refus:
            return self.refus
        modifiees, ajoutees = self.compte(MODIFIEE), self.compte(AJOUTEE)
        absentes = self.compte(ABSENTE)
        if not modifiees and not ajoutees:
            return (f"Rien à importer : les {len(self.planches)} planches du paquet sont "
                    f"identiques à celles d'ici.")
        morceaux = []
        if modifiees:
            morceaux.append(f"{modifiees} planche(s) corrigée(s)")
        if ajoutees:
            morceaux.append(f"{ajoutees} planche(s) ajoutée(s)")
        phrase = (f"{' et '.join(morceaux)} sur {len(self.planches)} — "
                  f"{_poids(self.octets_checkpoints)} de corrections")
        if self.avec_rendus:
            phrase += f", plus {_poids(self.octets_rendus)} de planches rendues"
        if absentes:
            phrase += (f". ⚠ {absentes} planche(s) d'ici ne sont pas dans le paquet : elles "
                       f"sont CONSERVÉES")
        return phrase + "."


def _poids(octets: int) -> str:
    if octets >= 1_000_000:
        return f"{octets / 1e6:.1f} Mo"
    if octets >= 1000:
        return f"{octets / 1e3:.0f} Ko"
    return f"{octets} o"


# --------------------------------------------------------------------------- #
#  Lire
# --------------------------------------------------------------------------- #

def _dossier_manga(racine: Path) -> Path:
    """Le `manga/` d'un tome, que l'on ait désigné le tome ou le dossier `manga/` lui-même.

    ⚠ Les deux gestes sont naturels — un tiers renvoie tantôt `Vol.3/`, tantôt `Vol.3/manga/`
    — et refuser l'un des deux serait refuser pour une raison que personne ne devine."""
    racine = Path(racine)
    if (racine / ".checkpoints").is_dir():
        return racine
    if (racine / "manga" / ".checkpoints").is_dir():
        return racine / "manga"
    return racine


def _empreintes(dossier_manga: Path) -> dict[int, str]:
    """`{index: empreinte}` pour chaque planche présente, par la MÊME fonction que
    `manga/projet.py`. En écrire une seconde ferait diverger les deux le jour où un fichier
    s'ajoute à la liste suivie."""
    ckpts = dossier_manga / ".checkpoints"
    if not ckpts.is_dir():
        return {}
    sortie: dict[int, str] = {}
    for page in sorted(ckpts.iterdir()):
        if not page.is_dir() or not page.name.startswith("page_"):
            continue
        try:
            index = int(page.name.split("_", 1)[1])
        except ValueError:
            continue
        sortie[index] = projet_mod._empreinte_page(page)                  # noqa: SLF001
    return sortie


def _version_des_regions(dossier_manga: Path) -> int | None:
    """La version de format des `regions.json` du paquet, ou `None` si indéterminable.

    ⚠ On lit la PREMIÈRE planche qui en porte une, pas toutes : un paquet dont les planches
    n'auraient pas la même version est un paquet cassé, et le dire demanderait de définir quoi
    faire d'un cas qui ne devrait pas exister.

    ## ⚠ Pourquoi on ne passe PAS par `checkpoints.checkpoint_format`

    Elle exige `regions.json` **et** `masks.png`, et rend `None` si l'un manque — parce qu'elle
    répond à « puis-je CHARGER ce cache ? ». Ici la question est autre : « de quelle version est
    ce paquet ? ». Un paquet dont le `masks.png` manquerait ferait alors répondre `None`, donc
    **contournerait silencieusement le garde-fou de version** — exactement le mode de panne que
    ce garde-fou existe pour empêcher.

    La règle de lecture tolérante est la même que la sienne : une liste nue vaut v1."""
    ckpts = dossier_manga / ".checkpoints"
    if not ckpts.is_dir():
        return None
    for page in sorted(ckpts.iterdir()):
        meta = page / "regions.json"
        if not (page.is_dir() and meta.is_file()):
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        return 1 if isinstance(data, list) else int(data.get("format", 0))
    return None


def _motifs(source_page: Path, cible_page: Path) -> tuple[str, ...]:
    """Ce qui a changé dans cette planche, nommé.

    ⚠ Les libellés sont ceux de `manga/etat_planches.SOURCES_DE_PEREMPTION`, qui sait déjà dire
    pourquoi un rendu devient périmé. Deux vocabulaires pour la même chose, c'est deux phrases
    à tenir en phase."""
    libelles = {
        ck.TRADUCTION_MANUELLE_FILENAME: "réplique(s) corrigée(s) à la main",
        ck.MISE_EN_PAGE_FILENAME: "texte déplacé",
        "regions.json": "zones retouchées",
        ck.TRADUCTION_FILENAME: "traduction refaite",
        ck.OCR_FILENAME: "lecture refaite",
    }
    trouves: list[str] = []
    for nom, libelle in libelles.items():
        avant = (cible_page / nom).read_bytes() if (cible_page / nom).is_file() else b""
        apres = (source_page / nom).read_bytes() if (source_page / nom).is_file() else b""
        if avant != apres:
            trouves.append(libelle)
    return tuple(trouves)


def _poids_dossier(dossier: Path, sous: tuple[str, ...]) -> int:
    total = 0
    for nom in sous:
        cible = dossier / nom
        if not cible.is_dir():
            continue
        for chemin in cible.rglob("*"):
            if chemin.is_file():
                try:
                    total += chemin.stat().st_size
                except OSError:
                    pass
    return total


def planifier(source, cible, *, avec_rendus: bool = False,
              run_en_cours: bool = False) -> Plan:
    """Ce qu'un import ferait. **Ne touche à rien.**

    `source` — le dossier reçu (le tome, ou son `manga/`).
    `cible` — le `build/<Projet>/<Tome>/manga/` local.
    """
    src = _dossier_manga(Path(source))
    dst = _dossier_manga(Path(cible))
    vide = Plan(source=src, cible=dst)

    if run_en_cours:
        return Plan(source=src, cible=dst, refus=(
            "Un run est en cours. Importer pendant qu'un tome s'écrit mêlerait deux "
            "écritures sur les mêmes fichiers — attends la fin, ou arrête le run."))
    if not (src / ".checkpoints").is_dir():
        return Plan(source=src, cible=dst, refus=(
            f"{src} ne porte pas de dossier `.checkpoints/` : ce n'est pas un tome traité. "
            f"Attendu : le dossier `build/<Projet>/<Tome>/` que le tiers a renvoyé, ou son "
            f"sous-dossier `manga/`."))

    # ── Refus 1 : ce n'est pas le même tome ──────────────────────────────────
    etat_src = projet_mod.lire(src) or {}
    etat_dst = projet_mod.lire(dst) or {}
    projet = str(etat_src.get("projet") or "")
    tome = str(etat_src.get("tome") or "")
    if etat_src and etat_dst:
        if (projet, tome) != (etat_dst.get("projet"), etat_dst.get("tome")):
            return Plan(source=src, cible=dst, projet=projet, tome=tome, refus=(
                f"Ce paquet est celui de « {projet} / {tome} », et tu l'importes dans "
                f"« {etat_dst.get('projet')} / {etat_dst.get('tome')} ». Rien n'a été écrit. "
                f"⚠ Installer le tome d'un autre par-dessus celui-ci mêlerait deux œuvres."))

    # ── Refus 2 : le format des caches ───────────────────────────────────────
    version = _version_des_regions(src)
    if version is not None and version != ck.FORMAT_VERSION:
        return Plan(source=src, cible=dst, projet=projet, tome=tome, refus=(
            f"Ce paquet porte des `regions.json` en version {version}, et ce dépôt attend la "
            f"version {ck.FORMAT_VERSION}. ⚠ L'ordre des zones est le PIVOT : `ocr.json` et "
            f"`traduction.json` s'y alignent par position, et installer un cache d'une autre "
            f"version ferait atterrir les traductions dans les mauvaises bulles, "
            f"silencieusement. Demande au tiers de relancer sur la même version d'Angelith."))

    # ── L'état planche par planche ───────────────────────────────────────────
    src_emp, dst_emp = _empreintes(src), _empreintes(dst)
    planches: list[Planche] = []
    motifs_par_planche: dict[int, tuple[str, ...]] = {}
    octets = 0
    for index in sorted(set(src_emp) | set(dst_emp)):
        page_src = src / ".checkpoints" / f"page_{index:04d}"
        page_dst = dst / ".checkpoints" / f"page_{index:04d}"
        if index not in src_emp:
            planches.append(Planche(index, ABSENTE))
            continue
        if index not in dst_emp:
            planches.append(Planche(index, AJOUTEE))
            octets += _poids_dossier(page_src.parent, (page_src.name,))
            continue
        if src_emp[index] == dst_emp[index]:
            planches.append(Planche(index, IDENTIQUE))
            continue
        motifs = _motifs(page_src, page_dst)
        motifs_par_planche[index] = motifs
        planches.append(Planche(index, MODIFIEE, motifs))
        octets += _poids_dossier(page_src.parent, (page_src.name,))

    rendus = _poids_dossier(src, ("pages_out", "pages_clean", "pages_psd")) if avec_rendus else 0
    return Plan(source=src, cible=dst, projet=projet, tome=tome,
                planches=tuple(planches), avec_rendus=avec_rendus,
                octets_checkpoints=octets, octets_rendus=rendus,
                motifs_par_planche=motifs_par_planche) if planches else vide


# --------------------------------------------------------------------------- #
#  Écrire
# --------------------------------------------------------------------------- #

def dossier_sauvegarde(cible: Path, jour: str = "") -> Path:
    return Path(cible) / f"{DOSSIER_SAUVEGARDE}-{jour or date.today().isoformat()}"


def appliquer(plan: Plan, *, progres=None) -> tuple[int, Path | None]:
    """Écrit ce que `plan` annonce. Rend `(planches écrites, dossier de sauvegarde)`.

    ⚠ **La sauvegarde d'abord, l'écriture ensuite**, planche par planche. L'ordre inverse
    laisserait, sur une coupure, des planches remplacées sans copie de secours."""
    if plan.refus:
        raise RefusDImporter(plan.refus)
    a_ecrire = [p for p in plan.planches if p.sera_ecrite]
    if not a_ecrire:
        return 0, None

    sauvegarde = dossier_sauvegarde(plan.cible)
    ecrites = 0
    for rang, planche in enumerate(a_ecrire, 1):
        nom = f"page_{planche.index:04d}"
        source = plan.source / ".checkpoints" / nom
        cible = plan.cible / ".checkpoints" / nom
        if cible.is_dir():
            sauvegarde.mkdir(parents=True, exist_ok=True)
            destination = sauvegarde / nom
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(cible, destination)
            shutil.rmtree(cible)
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, cible)
        ecrites += 1
        if callable(progres):
            progres(rang, len(a_ecrire), nom)

    if plan.avec_rendus:
        for nom in ("pages_out", "pages_clean", "pages_psd"):
            source = plan.source / nom
            if not source.is_dir():
                continue
            cible = plan.cible / nom
            cible.mkdir(parents=True, exist_ok=True)
            for fichier in sorted(source.iterdir()):
                if fichier.is_file():
                    shutil.copy2(fichier, cible / fichier.name)

    return ecrites, (sauvegarde if sauvegarde.exists() else None)
