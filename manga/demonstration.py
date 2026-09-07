# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le tome de démonstration — de quoi faire tourner l'application sur une installation neuve.

## Le problème, et il n'est pas technique

Une installation neuve n'a **aucune œuvre**. Et l'utilisateur ne peut pas en fournir une pour
essayer sans se poser la question des droits : les dix-huit dossiers de `sources/` de la
machine de développement sont des œuvres sous droit d'auteur, et le dépôt les a purgées une
fois pour toutes (`86c3d3d`, `b3d1eaa`). On ne peut donc ni en livrer, ni en demander.

Le dépôt avait pourtant déjà de quoi répondre. `tools/captures_gui.py` fabrique un tome
synthétique complet — « deux ellipses noires sur gris, deux répliques » — qui « fait
fonctionner le chemin d'aperçu pour de vrai », et c'est le même montage que la fixture de
`tests/test_gui_editeur_direct.py`. Ce module en fait une **capacité de l'application** plutôt
qu'un outil de capture d'écran.

## Ce que le tome permet, et c'est le critère 9 du `PLAN-36`

1. lancer un run court de bout en bout (avec `--dry-run` si aucun LLM n'est joignable) ;
2. voir la retouche fonctionner sur de vraies zones ;
3. produire un CBZ et un PDF réels.

## ⚠ Il est marqué comme démonstration, et il est supprimable

Le dossier s'appelle `_Démonstration Angelith` — le tiret bas le range en tête de liste, et le
nom ne peut pas se confondre avec une œuvre. `supprimer()` l'efface entièrement, sources et
build, et **refuse de toucher à autre chose** : le garde-fou vérifie le nom avant d'effacer
quoi que ce soit. Un utilisateur ne doit jamais confondre le tome de démonstration avec une
œuvre, et l'application ne doit jamais effacer une œuvre en croyant effacer la démonstration.

## ⚠ Et il ne dépend d'aucune police propriétaire

`tests/conftest.py` fabrique sa planche avec une police japonaise **du système** et *skippe*
quand elle manque. Un tome de démonstration livré à un utilisateur ne peut pas skipper : le
geste se **refuse proprement en le disant** (`PoliceIndisponible`, qui porte le message de
`tools.polices.explication_absence`), comme le `PLAN-20` L20.2 l'a demandé pour les tests.

## Aucun import Qt, et il vit dans la BRIQUE

Règle de couche du dépôt : tout ce qui décide se teste sans PySide6. Ce module écrit des
fichiers et rend des chemins ; c'est l'accueil qui met un bouton devant.

⚠ **Il est dans `manga/` et non dans `core/`, et ce n'est pas un détail de rangement.** Un
tome de démonstration est un tome de MANGA : il écrit des `BubbleRegion`, des checkpoints et
une page nettoyée. Le mettre dans le socle y aurait fait entrer la connaissance d'une brique —
et créé un cycle `core → manga → core` que `tests/test_imports_briques.py` refuse, à juste
titre : « `core` est le socle, il ne remonte jamais ».
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

#: Le nom du projet de démonstration. ⚠ Le tiret bas de tête n'est pas décoratif : il range le
#: dossier avant toutes les œuvres dans un tri alphabétique, donc au premier coup d'œil.
PROJET = "_Démonstration Angelith"

#: Le tome. Un seul, et court : la démonstration doit tenir en une minute, pas en une nuit.
TOME = "Tome de démonstration"

#: Nombre de planches. Deux, et c'est un choix mesuré : une seule ne montrerait ni la
#: progression, ni la navigation entre planches, qui sont deux des trois choses qu'on vient
#: voir. Au-delà, on paie du temps de run pour ne rien montrer de plus.
PLANCHES = 2

#: Taille d'une planche, en pixels. Celle de `tools/captures_gui.py`, pour que les deux
#: montages restent comparables.
TAILLE = (400, 900)

#: Le fichier qui marque le dossier. Il porte la phrase que l'utilisateur doit lire s'il
#: tombe dessus par le système de fichiers plutôt que par l'application.
MARQUEUR = "DEMONSTRATION.txt"

TEXTE_MARQUEUR = """\
Ce dossier est un TOME DE DÉMONSTRATION créé par Angelith.

Il ne contient aucune œuvre : les planches sont dessinées par le programme lui-même
(deux ellipses sur un fond gris, deux répliques factices). Il est donc redistribuable
sans réserve, sous la licence du dépôt (AGPL-3.0-or-later).

Il sert à trois choses, et à rien d'autre :
  · lancer un run court de bout en bout, pour vérifier que l'installation marche ;
  · voir la retouche fonctionner sur de vraies zones ;
  · produire un CBZ et un PDF réels.

Vous pouvez le supprimer à tout moment, à la main ou depuis l'application
(Œuvres → Supprimer le tome de démonstration). Rien d'autre n'en dépend.
"""

#: Les répliques peintes dans les bulles, côté source. Du japonais, parce que c'est ce que
#: l'OCR de la brique attend — et deux mots seulement, pour que la lecture reste lisible même
#: avec une police de repli.
REPLIQUES_SOURCE = ("こんにちは", "げんきです")

#: Ce que les checkpoints portent comme traduction. ⚠ Elles sont écrites d'avance : le tome
#: doit être retouchable et rendable **sans qu'aucun LLM ne soit joignable**, ce qui est
#: précisément l'état d'une installation neuve.
REPLIQUES_TRADUITES = ("Bonjour. Ceci est un tome de démonstration.",
                       "Rien ici ne vient d'une œuvre.")


class PoliceIndisponible(RuntimeError):
    """Aucune police ne sait dessiner le japonais des bulles source.

    ⚠ **Le geste se refuse, il ne dégrade pas en silence.** Une planche de démonstration dont
    les bulles rendent des tofus (□□□) ferait croire à un défaut d'Angelith. Le message porte
    la variable d'environnement, les candidats essayés et la commande d'installation — c'est
    `tools.polices.explication_absence` qui l'écrit, et il n'est pas paraphrasé ici."""


@dataclass(frozen=True)
class TomeDemo:
    """Ce qui a été écrit, et où. Rendu par `creer()`."""

    projet: str
    tome: str
    sources: Path
    build: Path
    planches: tuple[Path, ...]

    @property
    def libelle(self) -> str:
        return f"{self.projet} / {self.tome}"


def racine_sources(config: dict) -> Path:
    """Le dossier des sources tel que `config.yaml` le nomme. Aucun défaut inventé : c'est la
    même clé que lit le reste du programme."""
    return Path((config.get("chemins") or {}).get("sources") or "sources")


def racine_build(config: dict) -> Path:
    return Path((config.get("chemins") or {}).get("build") or "build")


def dossier_sources(config: dict) -> Path:
    return racine_sources(config) / PROJET / TOME


def dossier_build(config: dict) -> Path:
    return racine_build(config) / PROJET / TOME / "manga"


def existe(config: dict) -> bool:
    """Le tome de démonstration est-il là **et complet** ?

    Le marqueur fait foi, pas le dossier : un dossier vide créé à la main ne doit pas passer
    pour une démonstration. ⚠ Et comme `creer()` l'écrit **en dernier**, sa présence atteste
    que tout le reste est déjà sur le disque — c'est ce qui permet à un appelant d'attendre
    « le tome est prêt » sans courir après la fin d'une écriture."""
    return (dossier_sources(config) / MARQUEUR).is_file()


def _boite(k: int) -> tuple[int, int, int, int]:
    """La boîte de la bulle `k`. Même géométrie que `tools/captures_gui.py`."""
    haut = 40 + k * 250
    return (60, haut, 340, haut + 180)


def _police_pour_bulles(taille: int):
    """La police des répliques japonaises, ou l'échec.

    ⚠ On ne retombe PAS sur `ImageFont.load_default()` comme le fait
    `tools/corpus_synthetique.py`. Ce corpus-là sert à mesurer un détecteur, que du tofu ne
    dérange pas ; celui-ci sert à montrer l'application à quelqu'un qui vient de l'installer,
    et du tofu s'y lirait comme un défaut du programme."""
    from PIL import ImageFont

    from tools.polices import explication_absence, police_japonaise

    chemin = police_japonaise()
    if chemin is None:
        raise PoliceIndisponible(explication_absence())
    try:
        return ImageFont.truetype(str(chemin), taille)
    except OSError as err:                             # police présente mais illisible
        raise PoliceIndisponible(
            f"La police {chemin} n'a pas pu être ouverte ({err}).\n"
            f"{explication_absence()}") from err


def _peindre_planche(indice: int):
    """Une planche : fond gris, deux ballons blancs, une réplique japonaise dans chacun."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", TAILLE, (128, 128, 128))
    dessin = ImageDraw.Draw(image)
    police = _police_pour_bulles(28)
    for k in range(2):
        boite = _boite(k)
        dessin.ellipse([boite[0], boite[1], boite[2] - 1, boite[3] - 1], fill=(255, 255, 255))
        texte = REPLIQUES_SOURCE[(indice + k) % len(REPLIQUES_SOURCE)]
        largeur = dessin.textlength(texte, font=police)
        dessin.text(((boite[0] + boite[2]) / 2 - largeur / 2, boite[1] + 70), texte,
                    fill=(0, 0, 0), font=police)
    return image


def _masque(boite):
    import numpy as np
    from PIL import Image, ImageDraw

    masque = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(masque).ellipse([boite[0], boite[1], boite[2] - 1, boite[3] - 1], fill=255)
    return np.asarray(masque) > 127


def creer(config: dict, *, ecraser: bool = False, dire=None) -> TomeDemo:
    """Écrit le tome de démonstration sous `sources/`, checkpoints compris.

    Les checkpoints sont écrits **d'avance** — régions, OCR, traduction, page nettoyée — pour
    que la retouche et le rendu marchent sans qu'aucun modèle ne soit installé ni joignable.
    C'est ce qui rend le geste utile sur une installation neuve : sans eux, « voir la retouche
    fonctionner » demanderait d'abord un run, donc les poids, donc le réseau.

    ⚠ Un run réel reste possible et reste le but : les checkpoints sont un point de départ,
    pas un substitut. `run_manga.py "_Démonstration Angelith" "Tome de démonstration"`
    retraite le tome comme n'importe quel autre.

    Lève `PoliceIndisponible` si aucune police ne sait dessiner les bulles, et `FileExistsError`
    si le tome est déjà là et qu'on n'a pas demandé à l'écraser."""
    from . import checkpoints, clean, projet as projet_mod
    from .detection import BubbleRegion

    sources = dossier_sources(config)
    build = dossier_build(config)
    if existe(config) and not ecraser:
        raise FileExistsError(
            f"Le tome de démonstration est déjà là : {sources}. Supprime-le d'abord, ou "
            f"demande explicitement à l'écraser.")
    # ⚠ La police est résolue AVANT d'écrire quoi que ce soit : un refus doit laisser le
    # disque exactement comme il était, pas un dossier à moitié rempli.
    _police_pour_bulles(28)

    if sources.exists():
        shutil.rmtree(sources)
    if build.exists():
        shutil.rmtree(build)
    sources.mkdir(parents=True)

    ecrites: list[Path] = []
    for indice in range(1, PLANCHES + 1):
        image = _peindre_planche(indice - 1)
        chemin = sources / f"page_{indice:04d}.png"
        image.save(chemin)
        ecrites.append(chemin)

        regions = [BubbleRegion(bbox=_boite(k), mask=_masque(_boite(k)), score=0.9, cls=0)
                   for k in range(2)]
        ckpt = checkpoints.page_checkpoint_dir(build, indice)
        checkpoints.save_regions(ckpt, regions, TAILLE)
        checkpoints.save_ocr(ckpt, list(REPLIQUES_SOURCE))
        checkpoints.save_traduction(ckpt, list(REPLIQUES_TRADUITES))
        chemin_clean = checkpoints.clean_page_path(build, indice)
        chemin_clean.parent.mkdir(parents=True, exist_ok=True)
        clean.clean_bubbles(image, regions).save(chemin_clean)
        if callable(dire):
            dire(f"planche {indice}/{PLANCHES} écrite")

    projet_mod.ecrire(build, projet_mod.construire(
        build, projet=PROJET, tome=TOME, pages=ecrites, version="demonstration",
        page_ckpt=checkpoints.page_checkpoint_dir))
    # ⚠ **Le marqueur est écrit EN DERNIER, et c'est ce qui donne son sens à `existe()`.**
    # Écrit en premier, il rendait `existe()` vrai dès la première milliseconde : un tome à
    # moitié écrit — ou dont l'écriture vient d'échouer — passait pour complet, et un appelant
    # qui attendait la fin pouvait le supprimer pendant qu'on écrivait dedans. C'est un test
    # de bout en bout qui l'a montré, et pas une relecture.
    (sources / MARQUEUR).write_text(TEXTE_MARQUEUR, encoding="utf-8")
    if callable(dire):
        dire(f"✓ Tome de démonstration prêt : {sources}")
    return TomeDemo(PROJET, TOME, sources, build, tuple(ecrites))


def supprimer(config: dict) -> list[Path]:
    """Efface le tome de démonstration, sources et build. Rend ce qui a été effacé.

    ⚠ **Le garde-fou est le nom, et il est vérifié avant chaque `rmtree`.** Une fonction qui
    efface un dossier de `sources/` doit être incapable d'effacer autre chose que ce qu'elle a
    créé : ici, seuls des chemins dont le composant projet vaut exactement `PROJET` sont
    touchés. C'est le même principe que `illustration/frontiere.py`, qui refuse à l'exécution
    toute écriture hors du dossier de sa brique."""
    effaces: list[Path] = []
    for dossier in (racine_sources(config) / PROJET, racine_build(config) / PROJET):
        if dossier.name != PROJET:                     # pragma: no cover — garde-fou
            raise ValueError(f"refus d'effacer un dossier qui n'est pas la démonstration : "
                             f"{dossier}")
        if dossier.is_dir():
            shutil.rmtree(dossier)
            effaces.append(dossier)
    return effaces
