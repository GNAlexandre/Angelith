# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le **périmètre d'écriture** de la brique : ce qu'elle a le droit de toucher, et rien d'autre.

## Pourquoi un garde à l'exécution et pas seulement un test

Le `PLAN-24` demande un test qui échoue si `illustration/` ouvre en écriture un fichier
préexistant. Un test suffirait à attraper la régression au moment où elle est écrite — il
n'attraperait pas le chemin qu'un moteur externe emprunte à l'exécution, sur la machine de
l'utilisateur, avec un `workflow.json` qu'il a lui-même exporté.

D'où ce module : le périmètre est **armé pendant le run**, pas seulement pendant la suite. Un
`open(..., "w")` hors des racines autorisées lève `EcritureHorsPerimetre`, et le message nomme
le fichier visé. C'est la transposition, pour une brique entière, de ce que
`paint = paint & region.mask` fait pour un tableau numpy dans `manga/clean.py` : l'invariant ne
doit pas dépendre d'un raisonnement.

## Ce que le garde promet, et ce qu'il ne promet pas

Il promet : aucun `open` en mode écriture, aucun `Path.write_text` / `write_bytes`, aucun
`Image.save`, aucun `os.replace` / `os.rename` / `shutil.move`, aucune suppression, aucun
`mkdir` **hors des racines autorisées**, tant que le contexte est actif.

⚠ Il ne promet **pas** d'être un bac à sable. Un sous-processus, une extension C qui appelle
`fopen` directement, ou un serveur HTTP distant qui écrit chez lui ne passent pas par ces
fonctions Python. La brique ne lance aucun sous-processus d'écriture et son seul moteur
distant est un serveur ComfyUI que l'utilisateur a installé lui-même ; le dire vaut mieux que
de laisser croire le contraire.

⚠ Il est **par fil d'exécution** (`threading.local`) : deux runs dans le même processus, ou
l'interface graphique qui composerait un aperçu pendant qu'un run tourne, ne se marchent pas
dessus. Un fil qui n'a pas armé le périmètre n'est pas contraint — le garde protège le run,
il ne prétend pas régenter le processus.
"""
from __future__ import annotations

import builtins
import io
import os
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path

#: Modes d'ouverture qui peuvent écrire. Le `+` compte : `r+` ouvre en lecture ET en écriture.
_MODES_ECRITURE = frozenset("wax+")

#: Extensions d'image que **seule** `marquage.ecrire` a le droit de poser sur le disque.
#:
#: C'est le second invariant du module, et il répond au critère 7 du `PLAN-24` — « aucun
#: chemin de code ne sait produire un PNG sans marquage » — autrement que par un `grep` sur
#: les sources. Un test statique se contourne d'un `getattr` ; celui-ci constate au moment de
#: l'écriture. Le drapeau n'est levé que dans `marquage.ecrire`, pour la durée de son
#: écriture, et sur son fil.
EXTENSIONS_IMAGE = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
                              ".tif", ".tiff", ".psd", ".avif"})

#: Le seul dossier où un **extrait de l'œuvre** (recadrage de référence) peut être écrit.
#: Voir `ecriture_extrait` : c'est ce nom qui rend la seconde porte mécaniquement plus étroite
#: que la première, et non une convention d'appelant.
NOM_DOSSIER_EXTRAITS = "references"

_local = threading.local()

#: Les fonctions remplacées, et leur original. Le patch est posé UNE fois au premier
#: `perimetre()` actif du processus et n'est jamais retiré : le garde consulte `_local`, donc
#: il est inerte pour tout fil qui n'a rien armé. Poser puis retirer un patch global à chaque
#: contexte serait la vraie source de course entre deux fils.
_ORIGINAUX: dict[str, object] = {}
_VERROU = threading.Lock()


class EcritureHorsPerimetre(RuntimeError):
    """Une écriture visait un chemin que la brique n'a pas le droit de toucher."""

    def __init__(self, chemin, racines) -> None:
        self.chemin = Path(chemin)
        self.racines = tuple(Path(r) for r in (racines or ()))
        lieux = ", ".join(str(r) for r in self.racines) or "(aucune)"
        super().__init__(
            f"écriture refusée : {self.chemin}\n"
            f"  La brique d'illustration n'écrit que sous : {lieux}\n"
            f"  Tout le reste de l'arbre — sources/, media/, les planches, les pages — est "
            f"en LECTURE SEULE, et c'est ce qui rend vraie la phrase « l'IA ne dessine "
            f"jamais » pour cette brique. Si un fichier doit être produit ailleurs, c'est "
            f"l'appelant qui le copie, en le sachant.")


class ImageNonMarquee(RuntimeError):
    """Une image allait être écrite hors du seul chemin qui pose le marquage."""

    def __init__(self, chemin) -> None:
        self.chemin = Path(chemin)
        super().__init__(
            f"écriture d'image refusée : {self.chemin.name}\n"
            f"  Toute image produite par cette brique passe par "
            f"`illustration.marquage.ecrire`, qui pose son bloc tEXt (AIGenerated=true, "
            f"graine, modèle, identifiant local) et son sidecar de provenance à côté.\n"
            f"  Il n'y a pas de variante « brute », pas de drapeau, pas de clé de config : "
            f"l'AI Act art. 50(2) est applicable depuis le 2026-08-02, et une brique "
            f"génératrice non marquée contredirait la position publique du projet sur l'IA "
            f"générative au moment même où elle est écrite.")


def _racines() -> tuple[Path, ...] | None:
    return getattr(_local, "racines", None)


def _resoudre(chemin) -> Path:
    """Le chemin absolu, sans exiger qu'il existe. `resolve()` sous Windows suit les liens et
    normalise la casse ; il ne lève pas sur un fichier absent — c'est exactement le cas d'un
    fichier qu'on s'apprête à créer."""
    try:
        return Path(os.fsdecode(chemin)).resolve()
    except (OSError, ValueError, TypeError):             # chemin non représentable
        return Path(os.path.abspath(str(chemin)))


def _autorise(chemin) -> None:
    racines = _racines()
    if racines is None:
        return
    cible = _resoudre(chemin)
    # ⚠ Le périmètre d'abord, le marquage ensuite, et l'ordre porte du sens : une écriture
    # hors du dossier de la brique est la violation la plus grave — elle toucherait l'œuvre —
    # et c'est elle que le message doit nommer, même s'il s'agit d'une image.
    if not any(cible == racine or racine in cible.parents for racine in racines):
        raise EcritureHorsPerimetre(cible, racines)
    if cible.suffix.lower() not in EXTENSIONS_IMAGE:
        return
    if getattr(_local, "marquee", False):
        return
    # L'extrait autorisé vaut pour UN chemin, pas pour la durée d'un bloc : deux images ne
    # peuvent pas passer par la même autorisation.
    if cible == getattr(_local, "extrait", None):
        return
    raise ImageNonMarquee(cible)


def _ecrit(mode) -> bool:
    return bool(_MODES_ECRITURE & set(str(mode)))


def _poser_les_patchs() -> None:
    if _ORIGINAUX:
        return
    with _VERROU:
        if _ORIGINAUX:
            return
        originaux = {
            "open": builtins.open, "io_open": io.open,
            "write_text": Path.write_text, "write_bytes": Path.write_bytes,
            "mkdir": Path.mkdir, "unlink": Path.unlink,
            "replace": os.replace, "rename": os.rename, "remove": os.remove,
            "move": shutil.move,
        }

        def _open(fichier, mode="r", *a, **k):
            if _ecrit(mode):
                _autorise(fichier)
            return originaux["open"](fichier, mode, *a, **k)

        def _io_open(fichier, mode="r", *a, **k):
            if _ecrit(mode):
                _autorise(fichier)
            return originaux["io_open"](fichier, mode, *a, **k)

        def _write_text(self, *a, **k):
            _autorise(self)
            return originaux["write_text"](self, *a, **k)

        def _write_bytes(self, *a, **k):
            _autorise(self)
            return originaux["write_bytes"](self, *a, **k)

        def _mkdir(self, *a, **k):
            _autorise(self)
            return originaux["mkdir"](self, *a, **k)

        def _unlink(self, *a, **k):
            _autorise(self)
            return originaux["unlink"](self, *a, **k)

        def _remove(chemin, *a, **k):
            _autorise(chemin)
            return originaux["remove"](chemin, *a, **k)

        def _replace(src, dst, *a, **k):
            _autorise(src)
            _autorise(dst)
            return originaux["replace"](src, dst, *a, **k)

        def _rename(src, dst, *a, **k):
            _autorise(src)
            _autorise(dst)
            return originaux["rename"](src, dst, *a, **k)

        def _move(src, dst, *a, **k):
            _autorise(src)
            _autorise(dst)
            return originaux["move"](src, dst, *a, **k)

        builtins.open, io.open = _open, _io_open
        Path.write_text, Path.write_bytes = _write_text, _write_bytes
        Path.mkdir, Path.unlink = _mkdir, _unlink
        os.replace, os.rename, os.remove = _replace, _rename, _remove
        shutil.move = _move
        _ORIGINAUX.update(originaux)
        _patcher_pillow()


def _patcher_pillow() -> None:
    """`Image.save` écrit par `builtins.open`, donc il est déjà couvert. On le patche quand
    même : le `PLAN-24` le nomme, et le jour où Pillow écrira par un autre chemin (mmap, une
    extension C), c'est ici qu'on le verra — pas dans une planche corrompue."""
    try:
        from PIL import Image
    except ImportError:                                  # Pillow est optionnel pour `core`
        return
    original = Image.Image.save

    def _save(self, fp, *a, **k):
        if isinstance(fp, (str, bytes, os.PathLike)):
            _autorise(fp)
        return original(self, fp, *a, **k)

    Image.Image.save = _save
    _ORIGINAUX["save"] = original


@contextmanager
def perimetre(*racines):
    """Arme le périmètre d'écriture sur le fil courant pour la durée du bloc.

    Les racines sont créées si elles manquent — la première écriture d'un run est un
    `mkdir`, et le garde refuserait sa propre racine si elle n'existait pas encore.

    ⚠ **Imbrication : le périmètre intérieur RESTREINT, il n'élargit pas.** Un bloc imbriqué
    ne garde que des racines déjà autorisées ; en demander une nouvelle est une erreur de
    programmation, pas une extension de droits.
    """
    demandees = tuple(_resoudre(r) for r in racines)
    if not demandees:
        raise ValueError("perimetre() sans racine : un périmètre vide interdirait tout, "
                         "ce qui ressemble à une erreur d'appel plutôt qu'à une intention.")
    _poser_les_patchs()
    precedentes = _racines()
    if precedentes is not None:
        hors = [r for r in demandees
                if not any(r == p or p in r.parents for p in precedentes)]
        if hors:
            raise EcritureHorsPerimetre(hors[0], precedentes)
    for racine in demandees:
        _ORIGINAUX["mkdir"](racine, parents=True, exist_ok=True)
    _local.racines = demandees
    try:
        yield demandees
    finally:
        _local.racines = precedentes


@contextmanager
def ecriture_marquee():
    """Autorise l'écriture d'un fichier image, pour la durée du bloc et sur ce fil.

    ⚠ **Un seul appelant : `illustration.marquage.ecrire`.** Le nom est explicite pour que
    l'ajouter ailleurs demande de l'écrire noir sur blanc — c'est-à-dire de désarmer
    consciemment le marquage AI Act, ce qui se verra en revue. Le drapeau est rétabli à sa
    valeur précédente en sortie, y compris sur exception."""
    precedent = getattr(_local, "marquee", False)
    _local.marquee = True
    try:
        yield
    finally:
        _local.marquee = precedent


@contextmanager
def ecriture_extrait(destination):
    """Autorise l'écriture d'un **extrait de l'œuvre** — un recadrage de référence, jamais une
    image générée. Pour la durée du bloc, sur ce fil, et **pour ce seul fichier**.

    ⚠ **Pourquoi une seconde porte existe, alors qu'un garde qui a une exception n'est pas un
    garde.** Le `PLAN-25` conditionne la génération par des images de référence, et le modèle
    d'image ne sait pas lire un fichier de l'œuvre : il faut lui présenter un recadrage
    redimensionné. Ce fichier n'est **pas** une image générée — y écrire `AIGenerated=true`
    serait un mensonge, et c'est le mensonge que `marquage.ecrire` produirait s'il servait
    ici. Le marquage AI Act reste donc ce qu'il était : la seule chose qui pose
    `AIGenerated=true` est `marquage.ecrire`, et elle n'a toujours pas d'interrupteur.

    ⚠ **Et cette porte est plus étroite que l'autre, mécaniquement**, pas par convention : la
    cible doit être **directement** dans un dossier `{dossier}` du périmètre. Une image
    générée s'écrit à la racine du dossier de la brique ; elle ne peut donc pas passer par
    ici, quel que soit l'appelant. Le drapeau ne vaut que pour le chemin nommé, pas pour la
    durée du bloc en général.

    Un seul appelant dans le dépôt : `illustration.identite.preparer`, ce qu'un test vérifie.
    """
    cible = _resoudre(destination)
    if cible.parent.name != NOM_DOSSIER_EXTRAITS:
        raise ImageNonMarquee(cible)
    _autorise(cible.parent)                  # sans extension d'image : contrôle de périmètre
    precedent = getattr(_local, "extrait", None)
    _local.extrait = cible
    try:
        yield cible
    finally:
        _local.extrait = precedent


@contextmanager
def hors_perimetre():
    """Suspend le garde sur le fil courant. **Aucun appel dans `illustration/`** — il n'existe
    que pour les tests, qui doivent pouvoir peupler leur arbre témoin pendant qu'un périmètre
    est armé, et pour un appelant qui assume une écriture hors périmètre en le sachant."""
    precedentes = _racines()
    _local.racines = None
    try:
        yield
    finally:
        _local.racines = precedentes


def racines_actives() -> tuple[Path, ...] | None:
    """Les racines armées sur ce fil, ou `None`. Sert au diagnostic et aux tests."""
    return _racines()
