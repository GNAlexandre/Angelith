# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'état d'un chapitre manga, lu SANS l'ouvrir — ce que `--all` doit savoir avant de
charger quoi que ce soit.

## Pourquoi ce module existe

Un run de nuit sur une œuvre entière doit décider, chapitre par chapitre, s'il y a quelque
chose à faire. Trois réponses existaient, aucune n'était utilisable :

- `--list` marquait « déjà généré » sur la simple EXISTENCE du dossier de build
  (`core/cli.afficher_liste`) : un chapitre arrêté à la planche 3 sur 150 passait pour
  terminé, et la nuit l'aurait sauté ;
- `projet.json` porte les empreintes SHA-256 des planches, ce qui est plus strict — mais les
  calculer demande de relire toutes les images source, soit des minutes par chapitre sur
  OneDrive **rien que pour décider** ;
- ouvrir le chapitre et laisser `process_volume` sauter les planches finies coûte le scan du
  tome, la migration du cache, la réécriture de `RAPPORT.md` **et le réassemblage du CBZ** —
  mesuré à 230 Mo réécrits pour *manga A* Vol.1, sur un dossier synchronisé.

La question posée ici est donc la moins chère qui soit encore juste : *autant de planches
rendues que de planches source, et aucune d'elles en retard sur ses données ?*

## Le budget d'imports

`run_manga.py` recopie ses constantes plutôt que d'importer `manga.checkpoints`, parce que
numpy et Pillow feraient passer `--list`/`--help` de 0,19 s à 0,46 s. Ce module tient la même
règle : **rien de lourd au niveau module**. `manga.ingest` (stdlib pure) est importé dans les
fonctions qui en ont besoin, et `manga.etat_planches` — qui tire numpy et Pillow — n'est
importé que pour le seul chapitre dont les comptes coïncident, c'est-à-dire le seul pour qui
la question « est-ce à jour ? » se pose réellement.

## Ce qu'on ne fait jamais ici

`sources_manga.scan_volume` n'est pas appelé : il EXTRAIT les archives dans `pages_src/` et
lève `SystemExit` sur un dossier vide. Un pré-vol doit être en lecture seule, et il ne peut
pas se permettre de tuer la série sur un chapitre mal rempli.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: Aucune image ni archive sous le chapitre — il n'y a rien à traiter, et le dire vaut mieux
#: que d'échouer dessus au milieu de la nuit.
SANS_SOURCE = "sans_source"
#: Jamais rendu : aucune planche dans `pages_out/`.
NON_TRAITE = "non_traite"
#: Rendu incomplet — un run interrompu, ou des planches tombées en échec.
PARTIEL = "partiel"
#: Rendu complet, mais au moins une planche est en retard sur ses données (traduction
#: refaite, réplique corrigée à la main, zones retouchées).
A_RELETTRER = "a_relettrer"
#: Complet et à jour. Le seul statut qu'on saute pour de bon.
TERMINE = "termine"

STATUTS = (SANS_SOURCE, NON_TRAITE, PARTIEL, A_RELETTRER, TERMINE)

#: Statuts qui n'appellent aucun travail. `SANS_SOURCE` en fait partie : ouvrir le chapitre
#: n'y produirait qu'un `SystemExit`.
STATUTS_SANS_TRAVAIL = (TERMINE, SANS_SOURCE)

PUCES = {SANS_SOURCE: "⚠", NON_TRAITE: "·", PARTIEL: "◐", A_RELETTRER: "↻", TERMINE: "✓"}


@dataclass
class EtatChapitre:
    """Ce qu'on sait d'un chapitre sans l'avoir ouvert.

    `pages_source is None` signifie « non dénombrable » (une archive `.cbr`, dont l'index
    demanderait `rarfile` et l'outil externe `unrar`), et **jamais** « zéro ». La distinction
    compte : on ne saute pas sur une incertitude."""
    tome: str
    pages_source: int | None
    pages_rendues: int
    perimees: list[int] = field(default_factory=list)
    statut: str = NON_TRAITE
    detail: str = ""


def build_dir_de(build_root, projet: str, tome: str) -> Path:
    """`build/<Œuvre>/<Chapitre>/manga`. Même calcul que `run_manga._build_dir` et que
    `orchestrator_manga.process_volume` — trois endroits qui doivent viser le même dossier,
    sinon le pré-vol juge un chapitre que le run n'écrit pas."""
    return Path(build_root) / projet / tome / "manga"


def dossier_planches(vol_dir) -> Path | None:
    """`<Chapitre>/manga/`, ou `<Chapitre>/` lui-même — le MÊME repli que
    `sources_manga.scan_volume`. Un pré-vol qui ne regarderait pas où le scan ira lirait un
    autre chapitre que celui qui sera traité."""
    vol_dir = Path(vol_dir)
    manga_dir = vol_dir / "manga"
    if not manga_dir.is_dir():
        manga_dir = vol_dir
    return manga_dir if manga_dir.is_dir() else None


def _compter_archive(chemin: Path) -> int | None:
    """Images d'une archive, sans l'extraire — `None` si on ne peut pas le savoir.

    Un `.cbz`/`.zip` porte son index à la fin du fichier (répertoire central) : `infolist()`
    ne lit que celui-là, pas les 230 Mo de données. Un `.cbr` n'a pas d'équivalent en stdlib
    — il faudrait `rarfile` et l'outil externe `unrar`, que le pré-vol n'a aucune raison
    d'exiger — donc on répond « je ne sais pas », ce qui vaut « à traiter »."""
    from .ingest import IMG_EXTS
    if chemin.suffix.lower() not in (".cbz", ".zip"):
        return None
    import zipfile
    try:
        with zipfile.ZipFile(chemin) as zf:
            return sum(1 for info in zf.infolist()
                       if not info.is_dir()
                       and Path(info.filename).suffix.lower() in IMG_EXTS)
    except (OSError, zipfile.BadZipFile):
        return None


def compter_pages_source(vol_dir) -> int | None:
    """Planches attendues pour ce chapitre. `0` = rien à traiter, `None` = indénombrable.

    Les archives PRIMENT sur les images isolées, exactement comme dans
    `sources_manga.scan_volume` — sans quoi un chapitre livré en `.cbz` accompagné d'une
    jaquette isolée serait compté à une planche, et déclaré partiel à jamais."""
    from . import ingest
    manga_dir = dossier_planches(vol_dir)
    if manga_dir is None:
        return 0
    try:
        archives, images = ingest.list_source_files(manga_dir)
    except OSError:
        return None
    if not archives:
        return len(images)
    total = 0
    for arc in archives:
        n = _compter_archive(arc)
        if n is None:
            return None          # une seule archive illisible rend tout le compte faux
        total += n
    return total


def compter_pages_rendues(build_dir) -> int:
    """Planches présentes dans `pages_out/` — la même vue, au motif de glob près, que celle
    qu'`assemble_outputs` embarquera dans le CBZ."""
    dossier = Path(build_dir) / "pages_out"
    if not dossier.is_dir():
        return 0
    return sum(1 for _ in dossier.glob("page_*.png"))


def etat_chapitre(sources_root, build_root, projet: str, tome: str) -> EtatChapitre:
    """Statut d'un chapitre, en lecture seule et sans rien charger d'inutile."""
    vol_dir = Path(sources_root) / projet / tome
    build_dir = build_dir_de(build_root, projet, tome)
    source = compter_pages_source(vol_dir)
    rendues = compter_pages_rendues(build_dir)

    if source == 0:
        return EtatChapitre(tome, 0, rendues, [], SANS_SOURCE, "aucune image ni archive")
    if source is None:
        statut = NON_TRAITE if rendues == 0 else PARTIEL
        return EtatChapitre(tome, None, rendues, [], statut,
                            f"{rendues} rendue(s) · source .cbr non dénombrable — "
                            f"traité par précaution")
    if rendues == 0:
        return EtatChapitre(tome, source, 0, [], NON_TRAITE, f"{source} planche(s) à traiter")
    if rendues < source:
        return EtatChapitre(tome, source, rendues, [], PARTIEL,
                            f"{rendues}/{source} planche(s)")

    # Les comptes coïncident : c'est le SEUL cas où « est-ce à jour ? » se pose, donc le seul
    # qui paie l'import de numpy et Pillow. Un `--list` sur une œuvre neuve ne le paie jamais.
    from . import etat_planches
    perimees = etat_planches.planches_a_relettrer(build_dir)
    if perimees:
        return EtatChapitre(tome, source, rendues, perimees, A_RELETTRER,
                            f"{len(perimees)} planche(s) à relettrer")
    return EtatChapitre(tome, source, rendues, [], TERMINE, f"{source} planche(s)")


def lister_chapitres(sources_root, projet: str) -> list[str]:
    """Les chapitres d'une œuvre, dans l'ORDRE DE LECTURE.

    ⚠ Le tri passe par `ingest.natural_key` et non par `pipeline.sources._reading_order_key`,
    qui travaille sur `Path.stem` : `Path("Chap.5").stem` vaut `"Chap"`, si bien que tous les
    chapitres rendent la même clé et que l'ordre obtenu est `Chap.10, Chap.2, Chap.5, Chap.1`
    (mesuré). `natural_key("Chap.10")` rend `['chap.', 10, '']`, donc l'ordre juste.

    `pipeline.sources.list_volumes` n'est volontairement pas corrigée : elle sert au light
    novel, dont les tomes sont nommés autrement et dont l'ordre est déjà celui attendu.

    L'ordre compte pour deux raisons, et aucune n'est cosmétique : la passe terminologique
    enrichit `sources/<Œuvre>/glossaire.yaml` au fil des chapitres, et la fiche de contexte
    de l'œuvre est calculée par chapitre. Les traiter dans le désordre donnerait au chapitre 2
    un glossaire nourri du chapitre 10."""
    from .ingest import natural_key
    proj = Path(sources_root) / projet
    if not proj.is_dir():
        return []
    return sorted((p.name for p in proj.iterdir() if p.is_dir()), key=natural_key)


def etats_serie(sources_root, build_root, projet: str) -> list[EtatChapitre]:
    """L'état de tous les chapitres d'une œuvre, dans l'ordre de lecture."""
    return [etat_chapitre(sources_root, build_root, projet, tome)
            for tome in lister_chapitres(sources_root, projet)]


def a_traiter(etat: EtatChapitre) -> bool:
    """Ce chapitre demande-t-il du travail ? Un chapitre terminé et un chapitre sans source
    n'en demandent pas — pour deux raisons opposées, et c'est le `detail` qui les distingue
    dans le tableau."""
    return etat.statut not in STATUTS_SANS_TRAVAIL


def tableau(etats: list[EtatChapitre]) -> list[str]:
    """Le pré-vol tel qu'il s'imprime : une ligne par chapitre, colonnes alignées.

    C'est ce qu'on lit avant d'aller dormir, et ce qu'on relit au matin dans
    `RAPPORT-SERIE.md`. Les deux passent par ici pour ne pas raconter deux histoires."""
    if not etats:
        return []
    largeur = max(len(e.tome) for e in etats)
    return [f"{PUCES.get(e.statut, ' ')} {e.tome.ljust(largeur)}  {e.detail}" for e in etats]
