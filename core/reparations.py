# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce qu'un bouton a le droit de réparer — et la liste de ce qu'il n'a **pas** le droit de faire.

## Trois classes, écrites avant d'implémenter quoi que ce soit

| Classe | Exemples | Geste autorisé |
|---|---|---|
| `RECUPERABLE` | poids ONNX, modèle `manga-ocr`, modèle Ollama, polices libres | téléchargement, licence affichée **avant**, SHA-256 enregistrée après |
| `UTILISATEUR` | Pandoc, `unrar`, ComfyUI, WeasyPrint | ⚠ **jamais automatique** — un lien, une commande copiable, une revérification |
| `HORS_PERIMETRE` | pilotes GPU, CUDA, droits d'administrateur | dire ce qui manque, et s'arrêter là |

## ⚠ La ligne à ne pas franchir : Angelith n'installe aucun logiciel système

Ni Pandoc, ni un gestionnaire de paquets, ni un service. Le `PLAN-30` avait déjà tranché le
principe voisin pour ComfyUI : « Angelith ne pilote pas le cycle de vie d'un programme que
l'utilisateur a installé ; le faire créerait une dépendance qu'aucune mesure ne justifie. »

`tests/test_core_reparations.py` le vérifie **sur le code des modules de réparation** : aucun
appel à `winget`, `choco`, `scoop`, `apt`, `dnf`, `pacman`, `brew`, `msiexec`, ni à
`pip install`.

## Les quatre règles d'écriture

1. ⚠ **rien ne se télécharge sans un clic explicite.** `executer()` exige `consentement=True`,
   et refuse sinon. Pas de « préparation automatique au premier lancement » : un premier
   lancement qui consomme plusieurs gigaoctets sans demander est un défaut, quelle que soit
   l'intention. C'est aussi pourquoi ce module ne télécharge **rien** à l'import ;
2. **la provenance est enregistrée** — URL, date, taille, SHA-256, licence — par
   `core/provenance.py`, à côté du poids. C'est la règle des chiffres appliquée aux artefacts,
   et ce que le `PLAN-30` critère 2 exigeait déjà ;
3. **un téléchargement se reprend ou se refait proprement.** `etat_fichier()` détecte le
   fichier partiel — par sa taille, puis par son empreinte quand la fiche existe — plutôt que
   de le laisser planter dans `onnxruntime` ;
4. ⚠ **aucun téléchargement pendant un run.** `executer()` exige `run_en_cours=False`. Un run
   de nuit qui se met à télécharger 2 Go n'est plus le run qu'on a lancé.

## ⚠ Pourquoi un REGISTRE, et pas une table unique

Parce que `core` **n'importe aucune brique**, et que c'est la ligne dont tout le reste du
dépôt dépend (`tests/test_imports_briques.py`). Récupérer le détecteur de bulles demande
`manga.models` ; le déclarer ici y ferait entrer la connaissance d'une brique, et créerait un
cycle `core → manga → core`.

Le partage est donc celui des doctors, qui est le précédent du même lot : **le vocabulaire est
ici, le geste appartient à la brique qui le connaît.** Ce module porte les classes, les refus,
l'état d'un fichier et le catalogue déclaratif de ce qui n'exige aucune brique ;
`manga/reparations.py` enregistre les siennes à l'import.

⚠ **Conséquence à connaître** : `par_identifiant("poids_detection")` rend `None` tant que
`manga.reparations` n'a pas été importé. Ce n'est pas un défaut, c'est exact — on ne répare pas
une brique qu'on n'a pas chargée. Les appelants qui en ont besoin l'importent explicitement,
avec un commentaire qui dit pourquoi.

## Les licences, relevées le 2026-09-06

⚠ **Angelith ne redistribue aucun poids et n'héberge aucun miroir.** Chaque entrée porte donc
sa **source primaire** et sa licence, affichée avant le clic.

⚠ La licence de **LaMa** n'est **pas établie au 2026-09-06**. Il n'a donc aucune entrée nulle
part : on ne propose pas de récupérer ce qu'on ne sait pas qualifier.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import provenance

#: Les trois classes de l'étape 0.2 du `PLAN-36`.
RECUPERABLE = "recuperable"
UTILISATEUR = "utilisateur"
HORS_PERIMETRE = "hors_perimetre"

CLASSES: tuple[str, ...] = (RECUPERABLE, UTILISATEUR, HORS_PERIMETRE)

PHRASES_CLASSE = {
    RECUPERABLE: "Angelith peut le récupérer, si tu le demandes",
    UTILISATEUR: "à installer par toi — Angelith n'installe aucun logiciel système",
    HORS_PERIMETRE: "hors périmètre d'Angelith",
}


class RefusDeReparer(RuntimeError):
    """Un geste réparateur refusé, avec son motif. **Ce n'est pas un incident** : c'est une
    règle du lot qui s'applique, et le motif est fait pour être montré tel quel."""


@dataclass(frozen=True)
class Reparation:
    """Un geste réparateur déclaré. La table est gelée, comme `gui/actions.py`.

    `identifiant` — celui que porte le `Verdict` correspondant (`Verdict.reparation`).
    `classe` — l'une des trois. Elle décide de ce qui est **permis**, pas de ce qui est
    commode.
    `quoi` — ce que le geste fait, en une phrase, au futur : c'est ce que lit l'utilisateur
    avant de cliquer.
    `licence` / `licence_url` — ⚠ **affichées avant le clic**, jamais après. Une licence
    montrée après le téléchargement ne sert à rien.
    `url` / `octets` / `sha256` — la source **primaire** et ce qu'on en attend.
    `commande` — pour la classe `UTILISATEUR` : ce que l'utilisateur peut copier. Angelith
    ne l'exécute pas.
    `geste` — ce qui fait le travail, `(config, dire) -> Path | None`. ⚠ Il est fourni par la
    BRIQUE, jamais par ce module : c'est ce qui permet à `core` de ne rien importer.
    """

    identifiant: str
    libelle: str
    classe: str
    quoi: str
    brique: str = "socle"
    licence: str = ""
    licence_url: str = ""
    url: str = ""
    octets: int = 0
    sha256: str = ""
    commande: str = ""
    note: str = ""
    geste: Callable[..., Path | None] | None = field(default=None, compare=False)

    @property
    def automatique(self) -> bool:
        """Un bouton peut-il le faire ? ⚠ Seule la classe `RECUPERABLE` le peut, et seulement
        après un clic explicite."""
        return self.classe == RECUPERABLE

    @property
    def taille_lisible(self) -> str:
        """La taille annoncée avant le clic. ⚠ Elle porte son dénominateur : « ~104 Mo »
        annonce des mégaoctets décimaux, ceux de `Content-Length`."""
        if not self.octets:
            return "taille inconnue"
        return f"~{self.octets / 1e6:.0f} Mo"

    def consigne(self) -> str:
        """Ce qui s'affiche AVANT le clic : ce qui va se passer, d'où, sous quelle licence."""
        if self.classe == HORS_PERIMETRE:
            return f"{self.quoi}\n{self.note}".strip()
        if self.classe == UTILISATEUR:
            lignes = [self.quoi]
            if self.commande:
                lignes.append(f"Commande : {self.commande}")
            if self.licence_url:
                lignes.append(f"Page du projet : {self.licence_url}")
            if self.note:
                lignes.append(self.note)
            lignes.append("⚠ Angelith n'installe aucun logiciel système : c'est à toi de le "
                          "faire, puis de relancer le diagnostic.")
            return "\n".join(lignes)
        lignes = [self.quoi, f"Source primaire : {self.url}",
                  f"Taille annoncée : {self.taille_lisible}",
                  f"Licence : {self.licence}"]
        if self.licence_url:
            lignes.append(f"Licence à vérifier ici : {self.licence_url}")
        if self.note:
            lignes.append(self.note)
        lignes.append("⚠ Angelith ne redistribue ni n'héberge aucun poids : le fichier vient "
                      "de sa source primaire, et son empreinte SHA-256 sera enregistrée à "
                      "côté de lui.")
        return "\n".join(lignes)


# --------------------------------------------------------------------------- #
#  Le registre
# --------------------------------------------------------------------------- #

_REGISTRE: dict[str, Reparation] = {}


def enregistrer(*reparations: Reparation) -> None:
    """Ajoute des réparations au catalogue. **Idempotent** : réenregistrer remplace.

    ⚠ Appelé à l'import de `manga/reparations.py`, pas à celui d'un module d'interface : un
    catalogue qui dépendrait de l'ordre d'ouverture des fenêtres serait indébogable."""
    for reparation in reparations:
        _REGISTRE[reparation.identifiant] = reparation


def catalogue() -> tuple[Reparation, ...]:
    """Toutes les réparations connues **à cet instant**, dans l'ordre d'enregistrement.

    ⚠ « à cet instant » n'est pas une précaution de style : une brique dont le module de
    réparation n'a pas été importé n'a pas d'entrée ici. Cf. l'en-tête du module."""
    return tuple(_REGISTRE.values())


def par_identifiant(identifiant: str) -> Reparation | None:
    return _REGISTRE.get(identifiant)


def par_classe(classe: str) -> tuple[Reparation, ...]:
    return tuple(r for r in catalogue() if r.classe == classe)


# --------------------------------------------------------------------------- #
#  Ce qui ne demande AUCUNE brique : les gestes que l'utilisateur fait lui-même
# --------------------------------------------------------------------------- #
#
# ⚠ Ces entrées sont purement DÉCLARATIVES — un lien, une commande copiable, une note. Aucune
# ne porte de `geste`, et c'est le point : ce sont exactement celles qu'Angelith n'a pas le
# droit d'exécuter. Les déclarer dans le socle n'y fait donc entrer aucune connaissance de
# brique, seulement la phrase à afficher.

enregistrer(
    Reparation(
        "serveur_llm", "Démarrer le serveur de modèles", UTILISATEUR,
        quoi="Toute traduction passe par un endpoint compatible OpenAI — Ollama ou LM Studio "
             "en local.",
        licence_url="https://ollama.com/download",
        commande="ollama serve",
        note="⚠ Angelith ne démarre ni n'arrête aucun service : ce serait piloter le cycle de "
             "vie d'un programme que tu as installé (PLAN-30)."),
    Reparation(
        "pandoc", "Installer Pandoc", UTILISATEUR,
        quoi="Pandoc produit les sorties DOCX et EPUB du light novel.",
        brique="ln",
        licence="GPL-2.0-or-later",
        licence_url="https://pandoc.org/installing.html",
        commande="winget install --id JohnMacFarlane.Pandoc"),
    Reparation(
        "moteur_pdf", "Installer WeasyPrint", UTILISATEUR,
        quoi="Le moteur qui produit le PDF du light novel. DOCX et EPUB sortent sans lui.",
        brique="ln",
        licence="BSD-3-Clause",
        licence_url="https://doc.courtbouillon.org/weasyprint/stable/first_steps.html",
        commande="pip install weasyprint",
        note="⚠ Il demande aussi des bibliothèques système (GTK/Pango) qu'Angelith "
             "n'installe pas."),
    Reparation(
        "unrar", "Installer unrar (ou unar)", UTILISATEUR,
        quoi="L'outil externe que le paquet `rarfile` appelle pour lire un `.cbr`. Il n'est "
             "pas installable par pip.",
        brique="manga",
        licence="UnRAR — licence propriétaire, redistribution restreinte",
        licence_url="https://www.rarlab.com/rar_add.htm",
        note="Le format `.cbz` ne demande rien : c'est un zip, et Angelith le lit sans aucun "
             "outil externe."),
    Reparation(
        "comfyui", "Installer ComfyUI", UTILISATEUR,
        quoi="Le serveur d'inférence de la brique illustration (expérimentale).",
        brique="illustration",
        licence="GPL-3.0",
        licence_url="https://github.com/comfyanonymous/ComfyUI",
        note="⚠ Angelith ne pilote pas son cycle de vie — ni démarrage, ni arrêt, ni mise à "
             "jour (PLAN-30)."),
    Reparation(
        "pilote_gpu", "Pilotes GPU, CUDA/ROCm", HORS_PERIMETRE,
        quoi="Ce qui manque relève du pilote graphique ou de son environnement de calcul.",
        note="Angelith le dit et s'arrête là : toucher à un pilote demande des droits "
             "d'administrateur et peut rendre la machine inutilisable. Passe par les outils "
             "de ton système."),
)


# --------------------------------------------------------------------------- #
#  L'état d'un fichier — le point 3 des règles d'écriture
# --------------------------------------------------------------------------- #

#: Un fichier plus court que cette fraction de la taille attendue est tenu pour PARTIEL.
#: C'est le seuil que `manga/models.telecharger` applique déjà à un téléchargement frais
#: (« un serveur qui répond une page d'erreur en 200 produit un fichier court ») ; l'appliquer
#: aussi à la relecture évite qu'un fichier tronqué parte dans `onnxruntime`, où il produirait
#: un message obscur à chaque relance sans jamais dire qu'il suffit de le supprimer.
FRACTION_PARTIEL = 0.9


@dataclass(frozen=True)
class EtatFichier:
    """Ce qu'on sait d'un poids sur le disque, **avant** de le charger."""

    present: bool
    octets: int = 0
    partiel: bool = False
    reste_un_part: bool = False
    concorde: bool | None = None
    motif: str = ""

    @property
    def utilisable(self) -> bool:
        """⚠ `concorde is False` n'est PAS disqualifiant : un dépôt amont qui republie ses
        poids donne une autre empreinte, et un modèle différent reste un modèle utilisable.
        C'est la règle que `manga/models.py` applique déjà — signaler, pas bloquer. Seuls
        l'absence et la troncature rendent un fichier inutilisable."""
        return self.present and not self.partiel


def etat_fichier(chemin: Path | str, octets_attendus: int = 0) -> EtatFichier:
    """Le fichier est-il là, entier, et conforme à sa fiche de provenance ?

    Trois questions distinctes, et elles ne se répondent pas ensemble :

    · **là** — un `is_file()` ;
    · **entier** — sa taille contre celle attendue (`FRACTION_PARTIEL`), et l'existence d'un
      `.part` à côté, qui est la signature d'un téléchargement interrompu ;
    · **conforme** — son empreinte contre celle que `core/provenance.py` a enregistrée. Cette
      question-là coûte la lecture du fichier entier : elle n'est posée que si les deux
      premières sont réglées et qu'une fiche existe."""
    chemin = Path(chemin)
    partiel_sur_disque = chemin.with_name(chemin.name + ".part")
    reste_un_part = partiel_sur_disque.is_file()
    if not chemin.is_file():
        return EtatFichier(
            present=False, reste_un_part=reste_un_part,
            motif=("un téléchargement interrompu a laissé un fichier .part — il sera refait "
                   "proprement" if reste_un_part else "le fichier est absent"))
    octets = chemin.stat().st_size
    if octets == 0 or (octets_attendus and octets < octets_attendus * FRACTION_PARTIEL):
        attendu = f" pour {octets_attendus / 1e6:.0f} Mo attendus" if octets_attendus else ""
        return EtatFichier(
            present=True, octets=octets, partiel=True, reste_un_part=reste_un_part,
            motif=f"fichier incomplet : {octets / 1e6:.0f} Mo{attendu} — à retélécharger")
    concordance = provenance.concorde(chemin)
    if concordance is None:
        motif = "présent, mais sans fiche de provenance : sa licence n'est pas établie ici"
    elif concordance:
        motif = "présent, entier, et conforme à sa fiche de provenance"
    else:
        motif = ("présent et entier, mais son empreinte diffère de sa fiche — le fichier a "
                 "changé depuis sa récupération, ou le dépôt amont l'a republié")
    return EtatFichier(present=True, octets=octets, reste_un_part=reste_un_part,
                       concorde=concordance, motif=motif)


# --------------------------------------------------------------------------- #
#  Exécuter — et les trois refus
# --------------------------------------------------------------------------- #

MOTIF_SANS_CONSENTEMENT = (
    "Ce geste télécharge des données depuis Internet. Il ne part jamais tout seul : il faut "
    "un clic explicite, après avoir lu la licence et la taille annoncée.")

MOTIF_RUN_EN_COURS = (
    "Un run est en cours. Aucun téléchargement ne part pendant un run : un run de nuit qui se "
    "met à récupérer deux gigaoctets n'est plus le run qu'on a lancé. Attends la fin, ou "
    "arrête-le proprement.")


def executer(identifiant: str, config: dict | None = None, *, consentement: bool = False,
             run_en_cours: bool = False, dire=None, **extra) -> Path | None:
    """Exécute une réparation `RECUPERABLE`. Rend le chemin obtenu, ou `None`.

    ⚠ **Les refus sont des règles du lot, pas des garde-fous décoratifs** :
    `consentement=False` et `run_en_cours=True` lèvent `RefusDeReparer` avec le motif à
    afficher. Ils sont vérifiés AVANT toute lecture de config, pour qu'aucun chemin ne puisse
    les contourner par un ordre d'évaluation malheureux.

    `dire` reçoit l'avancement (`reporter.info`, ou le journal de la fenêtre) : un fichier de
    104 Mo sur une ligne ADSL prend plusieurs minutes, et un geste muet ressemble à un geste
    planté."""
    reparation = par_identifiant(identifiant)
    if reparation is None:
        raise RefusDeReparer(
            f"Réparation inconnue : {identifiant}. Si elle appartient à une brique, son module "
            f"de réparation n'a peut-être pas été importé — on ne répare pas une brique qu'on "
            f"n'a pas chargée.")
    if not reparation.automatique:
        raise RefusDeReparer(
            f"« {reparation.libelle} » est de classe « {reparation.classe} » : "
            f"{PHRASES_CLASSE[reparation.classe]}.\n{reparation.consigne()}")
    if not consentement:
        raise RefusDeReparer(MOTIF_SANS_CONSENTEMENT)
    if run_en_cours:
        raise RefusDeReparer(MOTIF_RUN_EN_COURS)
    if reparation.geste is None:                       # pragma: no cover — garde-fou
        raise RefusDeReparer(
            f"« {reparation.libelle} » se dit récupérable mais ne porte aucun geste : c'est "
            f"une erreur de déclaration, pas un état de la machine.")
    return reparation.geste(config or {}, dire=dire, **extra)
