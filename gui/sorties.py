# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les sorties d'un tome, **réunies sans être refaites** — et sans Qt.

## Ce que ce module ferme

Les exports de rendu étaient éparpillés, et le `PLAN-34` L34.5 les nomme un par un :
`formats: ["cbz", "images", "psd"]` est une clé de `config.yaml` appliquée PENDANT le run,
« Assembler CBZ/PDF » est un bouton de l'onglet Runs, le PSD par page est écrit sous
`pages_psd/`, les sorties du roman viennent du rendu du pipeline. Il n'existait aucun endroit
où l'on voie **ce qui existe sur le disque pour ce tome**.

## Ce qu'il ne fait pas — et c'est l'essentiel

⚠ **Il ne produit aucun format nouveau.** Il montre et il réunit ce qui existe. Tout chemin
d'exécution cité ici est celui qui existait déjà : `--assembler` /
`orchestrator_manga.assemble_outputs` pour le CBZ et le PDF, le rendu du pipeline pour le
DOCX/EPUB/PDF du roman, `core/glossary_export.py` pour le glossaire.

⚠ **Il ne lance aucun run, et surtout pas tout seul.** Un « Exporter en PSD » qui relancerait
le rendu de 131 planches sans le dire serait la pire action coûteuse sans garde-fou de
l'application. Une sortie qui exige un run porte donc l'état `EXIGE_RUN`, la commande exacte,
et le coût annoncé — l'appelant montre, il n'exécute pas.

⚠ **Il n'ouvre aucune image.** Les tailles et les dates viennent de `stat`, comme dans
`bibliotheque.py`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import bibliotheque as biblio

#: États d'une sortie.
PRESENTE = "presente"
ABSENTE = "absente"
EXIGE_RUN = "exige_run"
#: Le format refuse la planche — ce n'est **pas** une erreur, c'est un état. La 2.6.0 a livré
#: ce refus propre plutôt qu'un fichier corrompu ; l'afficher comme une panne serait défaire
#: ce choix.
REFUSEE = "refusee"

LIBELLES_ETAT: dict[str, str] = {
    PRESENTE: "présente",
    ABSENTE: "absente",
    EXIGE_RUN: "exige un run",
    REFUSEE: "refusée par le format",
}


def poids(octets: int) -> str:
    """« 412 Mo ». Repris de `manga.creation_projet.poids_lisible`, pour ne pas avoir deux
    façons d'écrire un poids dans la même fenêtre."""
    from manga.creation_projet import poids_lisible
    return poids_lisible(octets)


@dataclass(frozen=True)
class Sortie:
    """Une sortie possible pour ce tome : ce qu'elle est, où elle est, ce qu'elle coûterait."""

    cle: str
    libelle: str
    chemin: Path | None = None
    etat: str = ABSENTE
    octets: int = 0
    mtime: float | None = None
    fichiers: int = 0
    geste: str = ""
    cout: str = ""
    note: str = ""

    @property
    def existe(self) -> bool:
        return self.etat == PRESENTE

    @property
    def date(self) -> str:
        return (time.strftime("%Y-%m-%d %H:%M", time.localtime(self.mtime))
                if self.mtime else "—")

    @property
    def resume(self) -> str:
        """La ligne du tableau. **Elle porte ses chiffres avec leur dénominateur.**"""
        if self.etat == PRESENTE:
            morceaux = [self.date, poids(self.octets)]
            if self.fichiers:
                morceaux.insert(0, f"{self.fichiers} fichier(s)")
            return " · ".join(morceaux)
        return LIBELLES_ETAT.get(self.etat, self.etat)


def _stat(chemin: Path) -> tuple[int, float | None]:
    try:
        infos = chemin.stat()
        return infos.st_size, infos.st_mtime
    except OSError:
        return 0, None


def _dossier(chemin: Path, motif: str) -> tuple[int, int, float | None]:
    """`(fichiers, octets, mtime le plus récent)` d'un dossier de sorties."""
    fichiers = octets = 0
    dernier: float | None = None
    try:
        for entree in chemin.glob(motif):
            if not entree.is_file():
                continue
            fichiers += 1
            taille, date = _stat(entree)
            octets += taille
            if date is not None and (dernier is None or date > dernier):
                dernier = date
    except OSError:
        pass
    return fichiers, octets, dernier


def _fichier(cle: str, libelle: str, chemin: Path, *, geste: str, cout: str,
             note: str = "") -> Sortie:
    if chemin.is_file():
        octets, mtime = _stat(chemin)
        return Sortie(cle, libelle, chemin, PRESENTE, octets, mtime, 1, geste, cout, note)
    return Sortie(cle, libelle, chemin, ABSENTE, geste=geste, cout=cout, note=note)


#: Coût annoncé d'un réassemblage, par planche. Repris de l'ordre de grandeur que le lot 18
#: a mesuré pour le relettrage ; il sert à ANNONCER, jamais à décider, et le dire évite qu'on
#: le prenne pour une promesse.
SECONDES_ASSEMBLAGE_PAR_PLANCHE = 0.05


def _cout_assemblage(unites: int | None) -> str:
    if not unites:
        return "quelques secondes — aucune traduction n'est refaite"
    secondes = max(1, round(unites * SECONDES_ASSEMBLAGE_PAR_PLANCHE))
    return (f"~{secondes} s pour {unites} planche(s) — relit pages_out/, "
            f"ne retraduit ni ne relettre rien")


def sorties_manga(info) -> list[Sortie]:
    """Les sorties d'un tome manga ou webtoon.

    ⚠ Le PSD est le seul cas où « absent » ne veut pas dire « un bouton le produirait ». Il
    est écrit **pendant le run**, quand `manga.rendu.formats` contient `"psd"` — pas après
    coup. Le proposer comme un export ferait relancer le rendu complet."""
    build = _build_manga(info)
    sorties: list[Sortie] = []

    sorties.append(_fichier(
        "cbz", "Archive CBZ", build / f"{info.projet}_{info.tome}.cbz",
        geste="Assembler CBZ/PDF   ·   python run_manga.py \"{p}\" {t} --assembler",
        cout=_cout_assemblage(info.unites),
        note="Exige \"cbz\" dans manga.rendu.formats de config.yaml."))
    sorties.append(_fichier(
        "pdf", "PDF", build / f"{info.projet}_{info.tome}.pdf",
        geste="Assembler CBZ/PDF   ·   python run_manga.py \"{p}\" {t} --assembler",
        cout=_cout_assemblage(info.unites),
        note="Exige \"pdf\" dans manga.rendu.formats de config.yaml."))

    fichiers, octets, mtime = _dossier(build / "pages_out", "page_*.png")
    sorties.append(Sortie(
        "images", "Planches lettrées (pages_out/)", build / "pages_out",
        PRESENTE if fichiers else EXIGE_RUN, octets, mtime, fichiers,
        geste="python run_manga.py \"{p}\" {t}",
        cout="le rendu complet du tome — des heures de GPU si rien n'est en cache",
        note="C'est la SOURCE de toutes les autres sorties d'images."))

    fichiers, octets, mtime = _dossier(build / "pages_clean", "page_*.png")
    sorties.append(Sortie(
        "clean", "Planches nettoyées (pages_clean/)", build / "pages_clean",
        PRESENTE if fichiers else EXIGE_RUN, octets, mtime, fichiers,
        geste="python run_manga.py \"{p}\" {t} --from nettoyage",
        cout="le nettoyage de toutes les planches"))

    sorties.append(_sortie_psd(info, build))

    sorties.append(_fichier(
        "rapport", "RAPPORT.md", build / "RAPPORT.md",
        geste="produit par le run", cout="—"))
    return sorties


def _sortie_psd(info, build: Path) -> Sortie:
    """L'état du PSD, **refus du format compris**.

    ⚠ Ce que ce module sait, et ce qu'il ne sait pas. Il compte les `.psd` présents et les
    compare aux planches rendues : un écart signale que des planches n'ont pas été écrites, et
    la cause connue est le plafond de `manga/psd.py:COTE_MAX` (30 000 px de côté, une limite
    du FORMAT et non du module). Il ne CONFIRME pas cette cause, parce que la confirmer
    demanderait de lire la taille de chaque planche — soit un décodage d'image, soit
    150 lectures de `regions.json`, mesurées à ~1 s par tome. L'écart est donc annoncé comme
    un écart, avec sa cause probable nommée et le fichier qui la porte, plutôt qu'affirmé.
    """
    from manga.psd import COTE_MAX

    dossier = build / "pages_psd"
    fichiers, octets, mtime = _dossier(dossier, "page_*.psd")
    rendues, _o, _m = _dossier(build / "pages_out", "page_*.png")

    note = ("Le PSD est écrit PENDANT le run, quand \"psd\" est dans "
            "manga.rendu.formats. Il n'est pas produisible après coup.")
    if fichiers and rendues and fichiers < rendues:
        manquants = rendues - fichiers
        return Sortie(
            "psd", "PSD à calques (pages_psd/)", dossier, REFUSEE, octets, mtime, fichiers,
            geste="python run_manga.py \"{p}\" {t} --from rendu",
            cout="le rendu complet du tome",
            note=(f"{fichiers} PSD pour {rendues} planche(s) rendue(s) : {manquants} "
                  f"manquant(s). Cause connue — le format PSD plafonne à {COTE_MAX} px de "
                  f"côté (manga/psd.py), et une bande non découpée le dépasse ; le refus est "
                  f"propre et volontaire depuis la 2.6.0, il ne produit pas de fichier "
                  f"corrompu. ⚠ Non confirmé ici : le vérifier demanderait de lire la taille "
                  f"de chaque planche. Les autres formats n'ont pas cette limite."))
    if fichiers:
        return Sortie("psd", "PSD à calques (pages_psd/)", dossier, PRESENTE, octets,
                      mtime, fichiers, note=note)
    return Sortie("psd", "PSD à calques (pages_psd/)", dossier, EXIGE_RUN,
                  geste="ajouter \"psd\" à manga.rendu.formats, puis "
                        "python run_manga.py \"{p}\" {t} --from rendu",
                  cout="le rendu complet du tome — des dizaines de minutes",
                  note=note)


def sorties_ln(info) -> list[Sortie]:
    """Les sorties d'un tome de light novel : le Markdown canonique et ses rendus Pandoc."""
    build = _build_ln(info)
    tige = f"{info.projet}_{info.tome}".replace(" ", "_")
    geste = "python run.py \"{p}\" {t} --render-only"
    cout = "quelques secondes par format — Pandoc relit le Markdown déjà écrit"
    sorties = [
        _fichier("md", "Markdown canonique", build / f"{tige}.md",
                 geste="python run.py \"{p}\" {t}",
                 cout="la traduction complète du tome — des heures",
                 note="C'est la SOURCE des trois rendus ci-dessous."),
        _fichier("docx", "DOCX", build / f"{tige}.docx", geste=geste, cout=cout,
                 note="Exige \"docx\" dans rendu.formats, Pandoc, et templates/reference.docx."),
        _fichier("epub", "EPUB", build / f"{tige}.epub", geste=geste, cout=cout,
                 note="Exige \"epub\" dans rendu.formats et Pandoc."),
        _fichier("pdf", "PDF", build / f"{tige}.pdf", geste=geste, cout=cout,
                 note="Exige \"pdf\" dans rendu.formats, Pandoc et WeasyPrint."),
        _fichier("rapport", "RAPPORT.md", build / "RAPPORT.md",
                 geste="produit par le run", cout="—"),
    ]
    return sorties


def sorties_scan(info) -> list[Sortie]:
    """La sortie de la brique OCR de scans : **un `.md` écrit dans le dossier de langue**.

    ⚠ Pas sous `build/`, et ce n'est pas un oubli : `scan/pages.py` l'écrit à côté des images
    pour que `run.py` l'enchaîne sans rien changer. Le chercher sous `build/` le déclarerait
    absent à jamais."""
    chemin = info.sorties.get("md")
    if chemin is not None:
        octets, mtime = _stat(chemin)
        return [Sortie("md", f"{info.tome}.md (dans le dossier de langue)", chemin,
                       PRESENTE, octets, mtime, 1,
                       note="Lu ensuite par run.py comme n'importe quelle source de roman.")]
    return [Sortie("md", f"{info.tome}.md (dans le dossier de langue)", None, EXIGE_RUN,
                   geste="python run_ocr.py \"{p}\" {t}",
                   cout="~30 s par page — environ deux heures pour un tome de 270 pages",
                   note="Écrit DANS sources/<Projet>/<Tome>/<LANGUE>/, pas sous build/.")]


def _build_manga(info) -> Path:
    """`build/<Œuvre>/<Tome>/manga`, déduit d'une sortie déjà connue quand il y en a une.

    ⚠ Le repli n'est correct que si `chemins.build` vaut `build/`. Il ne sert qu'au tome qui
    n'a **aucune** sortie — donc à celui pour lequel toutes les lignes diront « exige un run »,
    où le chemin n'est affiché qu'en infobulle."""
    chemin = info.sorties.get("images") or info.sorties.get("cbz")
    if chemin is not None:
        return Path(chemin).parent
    return Path("build") / info.projet / info.tome / "manga"


def _build_ln(info) -> Path:
    chemin = info.sorties.get("md")
    if chemin is not None:
        return Path(chemin).parent
    return Path("build") / info.projet / info.tome


@dataclass(frozen=True)
class Panneau:
    """Ce qu'un tome a produit, et ce qu'il n'a pas produit. Prêt à afficher."""

    projet: str
    tome: str
    brique: str
    sorties: tuple[Sortie, ...] = ()
    glossaire: int | None = None
    avertissements: tuple[str, ...] = field(default_factory=tuple)

    @property
    def presentes(self) -> tuple[Sortie, ...]:
        return tuple(s for s in self.sorties if s.existe)

    @property
    def octets(self) -> int:
        return sum(s.octets for s in self.presentes)

    @property
    def resume(self) -> str:
        return (f"{len(self.presentes)} sortie(s) présente(s) sur {len(self.sorties)} "
                f"possible(s) · {poids(self.octets)} au total")


def panneau(config: dict, info) -> Panneau:
    """L'état des sorties d'un tome. **N'exécute rien, ne produit rien.**

    Les chemins d'exécution ne sont que des CHAÎNES : c'est ce qui garantit qu'aucun bouton
    de ce panneau ne peut lancer un run par accident."""
    if info.brique in (biblio.MANGA, biblio.WEBTOON):
        liste = sorties_manga(info)
    elif info.brique == biblio.LN:
        liste = sorties_ln(info)
    else:
        liste = sorties_scan(info)

    avertissements: list[str] = []
    if info.perimees:
        avertissements.append(
            f"⚠ {len(info.perimees)} planche(s) dont le rendu est ANTÉRIEUR à leurs données. "
            f"Une archive assemblée maintenant les embarquerait telles quelles. "
            f"« Enregistrer le projet » depuis la Retouche les relettre d'abord.")
    if info.brique in (biblio.MANGA, biblio.WEBTOON) and info.unites is None:
        avertissements.append(
            "⚠ Le nombre de planches source n'est pas connaissable (archive .cbr) : les "
            "comptes ci-dessous sont ceux du disque, pas une comparaison à un attendu.")

    return Panneau(projet=info.projet, tome=info.tome, brique=info.brique,
                   sorties=tuple(liste), glossaire=info.glossaire,
                   avertissements=tuple(avertissements))


def commande(sortie: Sortie, projet: str, tome: str) -> str:
    """Le geste, avec le projet et le tome substitués. Une chaîne à LIRE et à recopier."""
    return sortie.geste.replace("{p}", projet).replace("{t}", tome)
