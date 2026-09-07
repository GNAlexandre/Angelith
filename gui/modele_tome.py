# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Lecture SEULE d'un tome manga : l'état sur disque, présenté à l'interface.

## Pourquoi ce module n'écrit rien

Toute écriture passe par `manga/edition.py` et `manga/checkpoints.py`. Ici on ne fait que
lire — et c'est ce qui permet d'ouvrir un tome pendant qu'un run tourne dessus, comme
`tools/mesurer_bulles.py` le fait déjà en ligne de commande.

## `projet.json` d'abord, `scan_volume` seulement si nécessaire

`manga/projet.py` a été écrit pour ça, sa docstring le dit : « l'index que lira l'interface
graphique […] une interface doit pouvoir ouvrir un tome sans rejouer le pipeline ». On le lit
donc en priorité. `sources_manga.scan_volume`, lui, crée des dossiers et **extrait les
archives CBZ** : l'appeler pour afficher une liste de planches ferait travailler le disque pour
rien. Il n'est sollicité qu'au moment où l'on a besoin du chemin d'une image SOURCE — c'est-à-dire
seulement pour relire une bulle à l'OCR.

## La révision, et à quoi elle sert

`projet.json` porte un entier qui n'augmente que si le contenu change réellement. On le retient
à l'ouverture d'une planche et on le revérifie avant d'écrire : c'est l'`expected_revision` que
la docstring de `manga/projet.py` annonce, et la seule protection contre un run qui aurait
retraduit la planche pendant qu'elle était ouverte à l'écran.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core import config as core_config
from manga import checkpoints, projet as projet_mod, report_manga


@dataclass
class Bulle:
    """Une bulle telle que l'écran doit la montrer."""
    index: int
    bbox: tuple[int, int, int, int]
    ocr: str = ""
    traduction: str = ""
    manuelle: str | None = None            # None = aucune correction écrite à la main
    score: float = 1.0
    qa: dict = field(default_factory=dict)

    @property
    def affichee(self) -> str:
        """Ce qui sera réellement dessiné : la correction manuelle l'emporte."""
        return self.traduction if self.manuelle is None else self.manuelle


@dataclass
class Planche:
    index: int
    fichier: str
    ckpt_dir: Path
    chemin_clean: Path
    chemin_out: Path
    bulles: list[Bulle] = field(default_factory=list)
    taille: tuple[int, int] | None = None
    detectee: bool = False
    # Positions imposées à la main, par index de bulle (cf. `checkpoints.load_mise_en_page`).
    mises_en_page: dict = field(default_factory=dict)

    @property
    def rendue(self) -> bool:
        return self.chemin_out.exists()

    # Fond de l'éditeur : la planche NETTOYÉE d'abord.
    #
    # ⚠ C'était l'inverse en 1.1.0, et c'est ce qui rendait l'éditeur inutilisable pour ce
    # qu'on lui demandait : dès qu'une planche avait été rendue une fois, le texte était cuit
    # dans les pixels de `pages_out/`. Impossible de le recentrer, impossible de le déplacer —
    # il n'existait aucun calque à bouger, seulement une image aplatie.
    #
    # Sur la planche nettoyée, le texte est composé par-dessus, calque par calque
    # (`typeset.calque_fit`, la même fonction que le rendu final : l'aperçu est identique au
    # pixel près). `image_finale` reste accessible pour comparer.
    @property
    def image_a_afficher(self) -> Path | None:
        """La page NETTOYÉE si elle existe, sinon la page finale."""
        for chemin in (self.chemin_clean, self.chemin_out):
            if chemin.exists():
                return chemin
        return None

    @property
    def image_finale(self) -> Path | None:
        """La page telle que le pipeline l'a rendue — pour le bouton de comparaison."""
        return self.chemin_out if self.chemin_out.exists() else None


class Tome:
    """État d'un tome manga, relu à la demande."""

    def __init__(self, config: dict, projet: str, tome: str):
        self.config = config
        self.projet, self.tome = projet, tome
        chemins = core_config.section(config, "manga", "chemins")
        self.sources_root = Path(chemins["sources"])
        self.build_root = Path(chemins["build"])
        self.vol_dir = self.sources_root / projet / tome
        self.build_dir = self.build_root / projet / tome / "manga"
        self._pages_source: list[Path] | None = None

    # ------------------------------------------------------------------ #

    def ouvert(self) -> bool:
        return self.build_dir.exists()

    def revision(self) -> int:
        etat = projet_mod.lire(self.build_dir)
        return int(etat.get("revision", 0)) if etat else 0

    def index_planches(self) -> list[tuple[int, str]]:
        """`[(numéro, nom de fichier)]`, depuis `projet.json` s'il existe.

        Repli sur les dossiers de checkpoints quand l'index manque — un tome traité par une
        version antérieure à la 1.0.0 n'en a pas, et refuser de l'ouvrir serait absurde."""
        etat = projet_mod.lire(self.build_dir)
        if etat and etat.get("pages"):
            return [(int(p["index"]), str(p.get("fichier", ""))) for p in etat["pages"]]
        racine = self.build_dir / ".checkpoints"
        if not racine.is_dir():
            return []
        numeros = sorted(int(d.name.removeprefix("page_"))
                         for d in racine.iterdir()
                         if d.is_dir() and d.name.startswith("page_")
                         and d.name.removeprefix("page_").isdigit())
        return [(n, "") for n in numeros]

    def pages_source(self) -> list[Path]:
        """Images SOURCE, dans l'ordre de lecture. Coûteux (extraction d'archives) : appelé
        seulement quand on a besoin de relire une bulle à l'OCR.

        ⚠ `config` est passé au scan : sans lui, les dossiers de langue ne sont pas reconnus
        et un tome rangé en `webtoon/ENG/` ressort vide."""
        if self._pages_source is None:
            from manga import sources_manga
            self._pages_source = list(
                sources_manga.scan_volume(self.vol_dir, self.build_dir, self.config).pages)
        return self._pages_source

    def langue_source(self) -> str:
        """Langue source du tome, telle que le dernier run l'a enregistrée.

        Relue de `projet.json` plutôt que redéduite : l'éditeur doit retraduire une bulle
        avec la MÊME langue que le run, et rescanner les sources coûterait l'extraction des
        archives pour un simple clic."""
        etat = projet_mod.lire(self.build_dir) or {}
        return str(etat.get("langue_source")
                   or ((self.config.get("manga") or {}).get("langue_source") or "jp"))

    def chemin_source(self, index: int) -> Path | None:
        pages = self.pages_source()
        return pages[index - 1] if 1 <= index <= len(pages) else None

    # ------------------------------------------------------------------ #

    def planche(self, index: int, fichier: str = "") -> Planche:
        """Assemble l'état d'une planche. Tolérant : une planche jamais détectée revient
        avec zéro bulle plutôt qu'en levant — l'interface doit pouvoir l'afficher et proposer
        de lancer la détection."""
        ckpt = checkpoints.page_checkpoint_dir(self.build_dir, index)
        planche = Planche(
            index=index, fichier=fichier, ckpt_dir=ckpt,
            chemin_clean=checkpoints.clean_page_path(self.build_dir, index),
            chemin_out=checkpoints.final_page_path(self.build_dir, index))

        regions = checkpoints.load_regions(ckpt)
        if regions is None:
            return planche
        planche.detectee = True
        planche.taille = checkpoints.taille_image(ckpt)

        ocr = checkpoints.load_ocr(ckpt) or []
        trad = checkpoints.load_traduction(ckpt) or []
        manuelles = checkpoints.load_traduction_manuelle(ckpt)
        planche.mises_en_page = checkpoints.load_mise_en_page(ckpt)
        qa = report_manga.load_page_qa(ckpt) or {}
        qa_bulles = {int(b.get("index", -1)): b for b in (qa.get("bulles") or [])}

        planche.bulles = [
            Bulle(index=k, bbox=tuple(r.bbox), score=float(r.score),
                  ocr=ocr[k] if k < len(ocr) else "",
                  traduction=trad[k] if k < len(trad) else "",
                  manuelle=manuelles.get(k), qa=qa_bulles.get(k, {}))
            for k, r in enumerate(regions)]
        return planche

    # ------------------------------------------------------------------ #

    def ecrire_correction(self, planche: Planche, index: int, texte: str | None) -> None:
        """Pose (ou retire) la correction manuelle d'une bulle.

        ⚠ Elle va dans `traduction_manuelle.json`, **jamais** dans `traduction.json` : c'est
        exactement ce qui la fait survivre à un `--from traduction` ultérieur. Une chaîne vide
        est une décision éditoriale valable (bulle de silence) et se distingue de `None`, qui
        veut dire « laisse le modèle décider »."""
        manuelles = checkpoints.load_traduction_manuelle(planche.ckpt_dir)
        if texte is None:
            manuelles.pop(index, None)
        else:
            manuelles[index] = texte
        checkpoints.save_traduction_manuelle(planche.ckpt_dir, manuelles)


    def ecrire_mise_en_page(self, planche: "Planche", index: int,
                            entree: dict | None) -> None:
        """Pose (ou retire) la position imposée d'une bulle.

        ⚠ Comme `traduction_manuelle.json`, ce fichier n'est JAMAIS écrit par le pipeline :
        une position choisie survit donc à un `--from rendu` comme à un `--from traduction`.
        `None` rend la bulle au moteur, qui recalculera sa mise en page comme avant."""
        mises = checkpoints.load_mise_en_page(planche.ckpt_dir)
        if entree is None:
            mises.pop(index, None)
        else:
            mises[index] = entree
        checkpoints.save_mise_en_page(planche.ckpt_dir, mises)


def lister_projets(config: dict) -> list[str]:
    """Projets qui portent au moins un tome MANGA — un projet purement light novel n'a rien
    à faire dans un éditeur de planches."""
    from pipeline.sources import list_projects, list_volumes
    chemins = core_config.section(config, "manga", "chemins")
    racine = Path(chemins["sources"])
    projets = []
    for p in list_projects(racine):
        if any(_est_tome_manga(racine / p / v) for v in list_volumes(racine, p)):
            projets.append(p)
    return projets


def lister_tomes(config: dict, projet: str) -> list[str]:
    from pipeline.sources import list_volumes
    chemins = core_config.section(config, "manga", "chemins")
    racine = Path(chemins["sources"])
    return [v for v in list_volumes(racine, projet) if _est_tome_manga(racine / projet / v)]


def tomes_non_editables(config: dict, projet: str) -> list[str]:
    """Les tomes de ce projet que la retouche NE montre pas, dans l'ordre du disque.

    ⚠ **Une liste qui filtre sans le dire est une liste qu'on croit complète** (`PLAN-35`
    L35.1 point 1). Un projet peut porter un roman et son manga sous le même titre ; celui
    qui vient de lancer un run light novel et cherche « Vol.3 » ici doit lire pourquoi il
    n'y est pas, plutôt que d'aller vérifier si le dossier existe encore.

    La phrase, elle, est dans `gui/vue_retouche.phrase_tomes_absents` — sans Qt, comme toutes
    les décisions d'affichage du dépôt."""
    from pipeline.sources import list_volumes
    chemins = core_config.section(config, "manga", "chemins")
    racine = Path(chemins["sources"])
    return [v for v in list_volumes(racine, projet)
            if not _est_tome_manga(racine / projet / v)]


_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".cbz", ".cbr"}


def _est_tome_manga(vol_dir: Path) -> bool:
    """Un tome est « manga » s'il porte des images ou une archive.

    Cherche aux trois niveaux que `sources_manga.resoudre_source` accepte : sous
    `<Tome>/<format>/<LANGUE>/`, sous `<Tome>/<format>/`, ou directement dans `<Tome>/`.
    Volontairement TOLÉRANT — il ne s'agit que de décider si un tome mérite d'apparaître dans
    la liste, pas de choisir lequel de ses dossiers sera lu."""
    from manga.sources_manga import FORMATS

    def _porte_des_planches(dossier: Path) -> bool:
        return dossier.is_dir() and any(p.suffix.lower() in _EXTENSIONS
                                        for p in dossier.iterdir() if p.is_file())

    if _porte_des_planches(vol_dir):
        return True
    for fmt in FORMATS:
        racine = vol_dir / fmt
        if not racine.is_dir():
            continue
        if _porte_des_planches(racine):
            return True
        if any(_porte_des_planches(sub) for sub in racine.iterdir() if sub.is_dir()):
            return True
    return False
