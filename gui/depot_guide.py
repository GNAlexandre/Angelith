# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce qui se passe APRÈS le lâcher — **la lecture et le plan, sans Qt**.

`gui/depot.py` décide déjà *ce qu'on vient de lâcher* : `SOURCES`, `GLOSSAIRE` ou `INCONNU`,
avec un message toujours rempli. Ce module répond à la question suivante, celle que le
`PLAN-34` L34.3 nomme « le parcours à livrer » :

1. **ce que j'ai lu** — combien de fichiers, combien d'images, quels formats, quel poids ; et
   pour une archive, son contenu **listé sans l'extraire** ;
2. **où ça va** — projet neuf ou tome ajouté à un projet existant, préremplis par ce qui a
   été lu, et corrigibles ;
3. **la collision** — un tome qui existe déjà est NOMMÉ, jamais écrasé en silence ;
4. **le coût** — le poids annoncé avant que le premier octet ne soit copié.

La boîte de dialogue, elle, ne fait que montrer ce que rend `lire()` et collecter les
corrections. C'est la règle de couche du dépôt, et ici elle a une conséquence directe : le
parcours entier — y compris le refus d'un `.cbr` sans outil `unrar`, et le comptage d'un
`.cbz` sans l'ouvrir — se teste sans écran.

## ⚠ Copier, jamais déplacer par défaut

`manga/creation_projet.py` **copie**, et il n'a jamais su faire autre chose. Ce module garde
ce défaut et n'ouvre le déplacement que sur une case explicitement cochée, parce qu'un lâcher
qui vide le dossier d'origine est irréversible et qu'un glisser-déposer est le geste le plus
facile à faire par accident de toute l'interface.

## ⚠ Le `.cbr` se refuse AVANT, pas pendant

Lire un `.cbr` demande le paquet `rarfile` **et** l'outil externe `unrar`/`unar` dans le
`PATH`. Aujourd'hui l'absence remonte en `SystemExit` depuis `manga/ingest.py`, c'est-à-dire
au milieu de la copie, après que l'utilisateur a nommé son projet. `outil_rar()` répond avant
qu'on lui demande quoi que ce soit.

> ⚠ **MISE À JOUR 2026-09-06, lot 38 : c'est fait.** L'avertissement qui était ici disait que
> « la sonde définitive appartient au `PLAN-36` L36.1, qui n'est pas livré », et que celle-ci
> était « écrite pour être remplacée par la sienne ». Le `PLAN-36` a été livré en 2.30.0 et le
> rebranchement n'avait pas suivi : ce module gardait ses deux `which` et son `import`, et
> `core/reparations.py` portait une réparation `unrar` que personne n'atteignait depuis ici.
>
> `outil_rar()` **existe toujours** — c'est elle qui répond « peut-on lire ce `.cbr` ? », et
> `manga/ingest.py` ne le dit qu'au milieu de la copie. Ce qu'elle ne fait plus, c'est
> **réécrire le remède** : il vient de `core/reparations.py`, comme partout ailleurs.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from core import diagnostic as diag
from core import reparations as rep
from manga import creation_projet as crea
from manga import reparations as _reparations_manga  # noqa: F401 — enregistre le catalogue
from manga.ingest import IMG_EXTS, natural_key

#: Archives reconnues. Le même triplet que `manga.ingest.list_source_files`.
ARCHIVES: tuple[str, ...] = crea.ARCHIVES

#: Archives dont le contenu se compte **sans extraction**, parce que leur index vit dans le
#: fichier (répertoire central du ZIP). Le `.cbr` n'en fait pas partie — d'où `None`.
ARCHIVES_DENOMBRABLES: tuple[str, ...] = (".cbz", ".zip")


# --------------------------------------------------------------------------- #
#  La dépendance externe des .cbr
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class OutilRar:
    """Peut-on lire un `.cbr` sur cette machine, et sinon pourquoi."""

    disponible: bool
    outil: str = ""
    motif: str = ""

    @property
    def message(self) -> str:
        if self.disponible:
            return f"Lecture des .cbr disponible (outil « {self.outil} »)."
        return f"Lecture des .cbr indisponible : {self.motif}"


def outil_rar() -> OutilRar:
    """L'état de la chaîne `.cbr`, **avant** de proposer un import qui la demanderait.

    Deux maillons, et les deux manquent séparément : le paquet Python `rarfile`
    (`requirements-manga.txt`) et l'outil externe `unrar`/`unar`, qui n'est PAS une
    dépendance pip et que rien n'installe pour vous.

    ⚠ **Le REMÈDE n'est plus écrit ici** (lot 38) : il vient de la réparation `unrar` de
    `core/reparations.py`, celle-là même que la page Diagnostic affiche. Deux textes pour le
    même manque finissent par en dire deux choses — c'est exactement ce qui est arrivé aux
    licences de poids dans ce dépôt."""
    try:
        import rarfile  # noqa: F401
    except ImportError:
        return OutilRar(False, motif="le paquet Python « rarfile » n'est pas installé "
                                     "(pip install -r requirements-manga.txt).")
    # ⚠ `core.diagnostic.verdict_outil_externe` plutôt qu'un `shutil.which` de plus : c'est la
    # fonction du lot 36 qui sait chercher un exécutable et rendre un verdict, et elle était
    # restée sans appelant en production.
    verdict = diag.verdict_outil_externe(
        "unrar", brique=diag.MANGA, gravite=diag.DEGRADE,
        consequence="les archives .cbr ne peuvent pas être lues.",
        geste="", alternatives=("unar", "bsdtar"))
    if verdict.gravite == diag.CONFORME:
        # « unrar trouvé — C:\… » : on ne garde que le nom de l'outil, qui est ce que la boîte
        # affiche.
        return OutilRar(True, outil=verdict.constat.split(" ", 1)[0])
    reparation = rep.par_identifiant("unrar")
    remede = reparation.consigne() if reparation is not None else ""
    return OutilRar(False, motif="l'outil externe « unrar » (ou « unar ») est introuvable "
                                 f"dans le PATH. {remede}")


# --------------------------------------------------------------------------- #
#  Ce qu'on a lu
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Archive:
    """Une archive lâchée, **jamais extraite**."""

    chemin: Path
    octets: int
    images: int | None          # None = indénombrable (.cbr sans outil)
    lisible: bool = True
    motif: str = ""

    @property
    def libelle(self) -> str:
        poids = crea.poids_lisible(self.octets)
        if not self.lisible:
            return f"{self.chemin.name} — {poids} · ILLISIBLE : {self.motif}"
        if self.images is None:
            return f"{self.chemin.name} — {poids} · contenu non dénombrable sans extraction"
        return f"{self.chemin.name} — {poids} · {self.images} image(s)"


@dataclass(frozen=True)
class Lecture:
    """**Ce que j'ai lu.** Le premier des cinq écrans du parcours L34.3.

    ⚠ Aucune image n'est décodée et aucune archive n'est extraite : les tailles viennent des
    métadonnées de fichier, le contenu d'une archive de son index. Le même invariant que
    `bibliotheque.py`, et pour la même raison — un lâcher de 400 Mo ne doit pas coûter
    une minute de lecture avant d'afficher la première ligne."""

    fichiers: tuple[Path, ...] = ()
    archives: tuple[Archive, ...] = ()
    octets: int = 0
    extensions: dict[str, int] = field(default_factory=dict)
    projet_propose: str = ""
    tome_propose: str = ""
    format_propose: str = "manga"
    avertissements: tuple[str, ...] = ()

    @property
    def images(self) -> int:
        """Images ISOLÉES, hors archives."""
        return sum(1 for f in self.fichiers if f.suffix.lower() in IMG_EXTS)

    @property
    def planches(self) -> int | None:
        """Total attendu — `None` dès qu'une archive est indénombrable.

        ⚠ `None` n'est pas zéro. C'est la même distinction que
        `manga.serie.EtatChapitre.pages_source`, et elle vaut ici pour la même raison :
        annoncer « 0 planche » sur un `.cbr` de 300 Mo ferait renoncer à un import qui
        marcherait très bien."""
        total = self.images
        for archive in self.archives:
            if archive.images is None:
                return None
            total += archive.images
        return total

    @property
    def resume(self) -> str:
        """La ligne qu'on lit en premier. Elle porte ses dénominateurs."""
        if not self.fichiers:
            return "Rien de lisible : ni image, ni archive."
        planches = self.planches
        compte = "un nombre indéterminé de" if planches is None else str(planches)
        detail = ", ".join(f"{n} {ext}" for ext, n in sorted(self.extensions.items()))
        return (f"{len(self.fichiers)} fichier(s) · {compte} planche(s) · "
                f"{crea.poids_lisible(self.octets)}" + (f" · {detail}" if detail else ""))


def _images_de_archive(chemin: Path) -> tuple[int | None, bool, str]:
    """`(images, lisible, motif)` — **sans extraire**.

    Un `.cbz`/`.zip` porte son index à la fin du fichier : `infolist()` ne lit que celui-là,
    pas les 230 Mo de données. C'est la même lecture que `manga.serie._compter_archive`, et
    elle est refaite ici plutôt qu'importée parce qu'on veut en plus savoir POURQUOI on ne
    sait pas — un `.cbr` sans outil et une archive corrompue n'appellent pas le même message."""
    suffixe = chemin.suffix.lower()
    if suffixe == ".cbr":
        etat = outil_rar()
        if not etat.disponible:
            return None, False, etat.motif
        try:
            import rarfile
            with rarfile.RarFile(chemin) as rf:
                return (sum(1 for i in rf.infolist()
                            if not i.is_dir()
                            and Path(i.filename).suffix.lower() in IMG_EXTS), True, "")
        except Exception as err:                       # noqa: BLE001 — message à afficher
            return None, False, f"archive illisible ({err.__class__.__name__})."
    if suffixe not in ARCHIVES_DENOMBRABLES:
        return None, True, ""
    try:
        with zipfile.ZipFile(chemin) as zf:
            return (sum(1 for i in zf.infolist()
                        if not i.is_dir()
                        and Path(i.filename).suffix.lower() in IMG_EXTS), True, "")
    except (OSError, zipfile.BadZipFile) as err:
        return None, False, f"archive illisible ({err.__class__.__name__})."


def _deviner(premier: Path) -> tuple[str, str]:
    """`(projet, tome)` proposés depuis le premier chemin lâché.

    Deux formes reconnues, et pas une de plus — c'est **exactement** la règle de
    `gui/dialogues.py:DialogueNouveauProjet._deviner_noms`, et pour la raison qu'elle donne :
    « deviner davantage ferait proposer des noms faux assez souvent pour qu'on cesse de les
    lire ». La recopier ici plutôt que de l'importer serait garantir qu'elles divergent, donc
    c'est l'inverse qui est fait — la boîte consomme ce module."""
    tige = premier.stem if premier.is_file() else premier.name
    for separateur in (" - ", " – ", "_-_"):
        if separateur in tige:
            projet, tome = (m.strip() for m in tige.split(separateur, 1))
            return projet, tome
    if premier.is_dir() and premier.parent.name:
        return premier.parent.name, tige
    return tige, "Vol.1"


def _format_propose(fichiers: list[Path]) -> str:
    """« webtoon » quand le chemin lâché le dit, « manga » sinon.

    ⚠ On ne le déduit **pas** de la géométrie des images : ce serait les décoder, et le format
    n'est de toute façon pas une propriété des pixels mais du sens de lecture
    (`manga/formats.py`). L'utilisateur corrige d'un clic ; une fausse déduction coûteuse
    serait le pire des deux."""
    for chemin in fichiers:
        if "webtoon" in {p.lower() for p in chemin.parts}:
            return "webtoon"
    return "manga"


def lire(chemins) -> Lecture:
    """Ce qu'on vient de lâcher, tel qu'on va l'annoncer. **Ne crée ni ne copie rien.**"""
    bruts = [Path(c) for c in chemins if str(c).strip()]
    fichiers = crea.lister_sources(bruts)
    if not fichiers:
        return Lecture(avertissements=(
            "Aucune image ni archive lisible ici. Attendu : un dossier de planches, un "
            ".cbz/.cbr, ou des images (.png, .jpg, .jpeg, .webp, .bmp).",))

    extensions: dict[str, int] = {}
    octets = 0
    archives: list[Archive] = []
    avertissements: list[str] = []
    for chemin in fichiers:
        suffixe = chemin.suffix.lower()
        extensions[suffixe] = extensions.get(suffixe, 0) + 1
        try:
            taille = chemin.stat().st_size
        except OSError:
            taille = 0
        octets += taille
        if suffixe in ARCHIVES:
            images, lisible, motif = _images_de_archive(chemin)
            archives.append(Archive(chemin, taille, images, lisible, motif))
            if not lisible:
                avertissements.append(f"{chemin.name} — {motif}")

    projet, tome = _deviner(bruts[0])
    return Lecture(
        fichiers=tuple(sorted(fichiers, key=lambda p: natural_key(p.name))),
        archives=tuple(archives), octets=octets, extensions=extensions,
        projet_propose=projet, tome_propose=tome,
        format_propose=_format_propose(fichiers),
        avertissements=tuple(avertissements))


# --------------------------------------------------------------------------- #
#  Où ça va, et ce qui s'y trouve déjà
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Destination:
    """**Où ça va**, et ce qui s'y trouve déjà. Le deuxième et le quatrième écran.

    `bloquant` est vrai quand rien ne peut être écrit sans que l'utilisateur change quelque
    chose. Une collision n'est PAS bloquante en soi — `creation_projet.copier` renomme les
    doublons plutôt que d'écraser — mais elle est **nommée**, ce qui est tout l'objet de ce
    parcours : un tome qui existe déjà ne se remplit pas en silence."""

    dossier: Path
    projet: str
    tome: str
    format: str = "manga"
    langue: str | None = None
    projet_existe: bool = False
    tome_existe: bool = False
    fichiers_presents: int = 0
    message: str = ""
    bloquant: bool = False


def preparer(config: dict, projet: str, tome: str, *, format: str = "manga",
             langue: str | None = None) -> Destination:
    """Décrit la destination **sans rien créer**.

    ⚠ La validation des noms passe par `creation_projet.valider_nom`, la MÊME fonction que la
    création. Revalider ici avec une règle recopiée serait le meilleur moyen d'accepter dans
    la boîte ce que la copie refuserait ensuite — c'est déjà l'arbitrage de
    `DialogueNouveauProjet._valider`."""
    racine = crea.racine_sources(config)
    try:
        projet_propre = crea.valider_nom(projet, "nom de projet")
        tome_propre = crea.valider_nom(tome, "nom de tome")
        dossier = crea.dossier_cible(config, projet_propre, tome_propre,
                                     format=format, langue=langue)
    except crea.ErreurCreation as err:
        return Destination(dossier=racine, projet=projet, tome=tome, format=format,
                           langue=langue, message=str(err), bloquant=True)

    projet_existe = (racine / projet_propre).is_dir()
    tome_existe = (racine / projet_propre / tome_propre).is_dir()
    presents = 0
    if dossier.is_dir():
        presents = sum(1 for p in dossier.iterdir()
                       if p.is_file() and p.suffix.lower() in (*IMG_EXTS, *ARCHIVES))

    if presents:
        message = (f"⚠ {dossier} contient DÉJÀ {presents} planche(s) ou archive(s). "
                   f"Les fichiers ajoutés ne les écraseront pas — un doublon de nom est "
                   f"renuméroté — mais les deux lots se retrouveront dans le même tome, et "
                   f"le pipeline les traitera ensemble. Choisis un autre nom de tome si ce "
                   f"n'est pas ce que tu veux.")
    elif tome_existe:
        message = (f"Le tome « {tome_propre} » existe déjà sous « {projet_propre} », mais "
                   f"{dossier.name}/ est vide : les planches y seront ajoutées.")
    elif projet_existe:
        message = f"Nouveau tome « {tome_propre} » dans l'œuvre existante « {projet_propre} »."
    else:
        message = (f"Nouvelle œuvre « {projet_propre} ». Son glossaire sera créé au premier "
                   f"run et partagé par tous ses tomes.")

    return Destination(dossier=dossier, projet=projet_propre, tome=tome_propre,
                       format=format, langue=langue, projet_existe=projet_existe,
                       tome_existe=tome_existe, fichiers_presents=presents,
                       message=message, bloquant=False)


# --------------------------------------------------------------------------- #
#  Le plan complet
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Plan:
    """Tout ce qu'il faut pour agir, et le compte rendu qu'on annoncera avant d'agir."""

    lecture: Lecture
    destination: Destination
    deplacer: bool = False

    @property
    def executable(self) -> bool:
        return bool(self.lecture.fichiers) and not self.destination.bloquant

    @property
    def refus(self) -> str:
        """Pourquoi on ne peut pas exécuter — vide si on peut.

        ⚠ Une archive illisible est un refus, et c'est le point du L34.3 : mieux vaut le dire
        maintenant que de laisser `manga/ingest.py` lever un `SystemExit` au milieu de la
        copie, quand l'utilisateur a déjà nommé son projet."""
        if self.destination.bloquant:
            return self.destination.message
        if not self.lecture.fichiers:
            return "Rien de lisible à importer."
        illisibles = [a for a in self.lecture.archives if not a.lisible]
        if illisibles:
            return ("Une archive au moins ne peut pas être lue sur cette machine :\n  · "
                    + "\n  · ".join(a.libelle for a in illisibles))
        return ""

    @property
    def annonce(self) -> str:
        """**Le coût, avant le premier octet copié.** Un lâcher de 400 Mo qui commence sans
        rien dire passe pour un gel — c'est déjà le motif de `estimer_poids`."""
        verbe = "DÉPLACÉ" if self.deplacer else "copié"
        return (f"{len(self.lecture.fichiers)} fichier(s), "
                f"{crea.poids_lisible(self.lecture.octets)} — sera {verbe} vers "
                f"{self.destination.dossier}")


def planifier(config: dict, chemins, *, projet: str = "", tome: str = "",
              format: str = "", langue: str | None = None,
              deplacer: bool = False) -> Plan:
    """Le parcours complet, d'un lâcher à un plan exécutable.

    Les arguments nommés sont les CORRECTIONS de l'utilisateur ; laissés vides, ce sont les
    propositions de `lire()` qui s'appliquent. C'est ce qui permet à la boîte de rappeler
    cette fonction à chaque frappe sans jamais avoir à recopier une règle."""
    lecture = lire(chemins)
    destination = preparer(
        config, projet or lecture.projet_propose, tome or lecture.tome_propose,
        format=format or lecture.format_propose, langue=langue)
    return Plan(lecture=lecture, destination=destination, deplacer=deplacer)
