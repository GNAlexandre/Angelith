# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Cache d'aperçus composés — ce qui rend le changement de planche instantané.

## Le coût qu'il supprime

Mesuré sur *manga A* Vol.1 : composer l'aperçu d'une planche coûte **1,37 s
en médiane** (2,67 s au pire) et pèse **1,04 Mo** de calques. Lire son cache de checkpoints,
lui, coûte 5 à 8 ms. Tout le temps que l'utilisateur subissait en changeant de planche était
donc de la composition — et une composition est intégralement recalculable **à l'avance**.

## La clé, et pourquoi elle est ce qu'elle est

Une entrée est valable tant que rien de ce qui influe sur le rendu n'a bougé :

    (index, mtime de la planche nettoyée, textes affichés, mises en page)

Les textes viennent de l'état **en mémoire** du `DocumentPlanche`, pas du disque. C'est le
point important : une correction non encore enregistrée change la clé, donc invalide l'entrée
**toute seule**. Il n'y a aucune invalidation explicite à écrire — donc aucune à oublier, et
c'est le mode de panne qu'on veut éviter avant tout : un aperçu périmé montrerait à
l'utilisateur un texte qui n'est plus le sien, sans rien pour le signaler.

## Le plafond

En octets, pas en nombre d'entrées : une planche à deux bulles et une planche à quatorze ne
coûtent pas la même chose, et un plafond en nombre laisserait la mémoire suivre le contenu du
tome. La fenêtre ±10 du préchargement pèse ~21 Mo ; le plafond par défaut (120 Mo) la contient
largement tout en bornant les allers-retours.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

PLAFOND_MO = 120


def _mtime(chemin) -> float:
    try:
        return Path(chemin).stat().st_mtime
    except OSError:
        return 0.0


def signature(index: int, chemin_clean, textes, layouts: dict | None) -> tuple:
    """Ce qui identifie un aperçu. Deux appels identiques doivent rendre la même chose.

    `layouts` est normalisé en tuple trié : un dictionnaire n'est pas hachable, et deux
    mises en page identiques posées dans un ordre différent ne doivent pas produire deux
    entrées distinctes."""
    mises = tuple(sorted((int(k), repr(v)) for k, v in (layouts or {}).items()))
    return (int(index), _mtime(chemin_clean), tuple(textes or ()), mises)


class CacheApercu:
    """LRU d'aperçus composés, plafonné en octets.

    ⚠ Ne conserve **aucun objet Qt**. Les `QPixmap` ne se construisent que sur le fil
    d'affichage ; en garder ici depuis une composition faite en tâche de fond serait un
    plantage à retardement. On garde les images PIL, et l'appelant les convertit au moment de
    les poser.

    ⚠ **Deux fils y touchent** : la voie de lecture y dépose ses compositions, le fil
    d'affichage les y prend. `OrderedDict.move_to_end` suivi d'un `popitem` n'est pas atomique,
    et une éviction concurrente d'une lecture laisserait `octets` et `_poids` désaccordés — un
    cache qui se croit plein et évince tout. D'où un verrou, tenu sur des opérations qui ne
    font que manipuler des références (jamais une composition)."""

    def __init__(self, plafond_mo: int = PLAFOND_MO):
        self.plafond = max(1, int(plafond_mo)) * 1024 * 1024
        self._verrou = threading.Lock()
        self._entrees: OrderedDict[tuple, object] = OrderedDict()
        self._poids: dict[tuple, int] = {}
        self.octets = 0
        # Compteurs, lus par le journal : un cache dont on ne mesure pas l'efficacité est un
        # cache qu'on règle au doigt mouillé.
        self.succes = 0
        self.echecs = 0

    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self._entrees)

    def __contains__(self, cle) -> bool:
        with self._verrou:
            return cle in self._entrees

    def lire(self, cle):
        """L'aperçu, ou `None`. Un succès remonte l'entrée en tête du LRU."""
        with self._verrou:
            if cle not in self._entrees:
                self.echecs += 1
                return None
            self._entrees.move_to_end(cle)
            self.succes += 1
            return self._entrees[cle]

    def poser(self, cle, apercu) -> None:
        poids = poids_apercu(apercu)          # hors verrou : ne touche pas les structures
        with self._verrou:
            if cle in self._entrees:
                self.octets -= self._poids.pop(cle, 0)
                del self._entrees[cle]
            self._entrees[cle] = apercu
            self._poids[cle] = poids
            self.octets += poids
            self._evincer()

    def oublier_planche(self, index: int) -> int:
        """Retire toutes les entrées d'une planche. Renvoie le nombre d'entrées retirées.

        Sert quand la planche a été réécrite sur disque par un run : les textes en mémoire
        n'ont pas bougé, donc la signature non plus, alors que le fond nettoyé peut avoir
        changé sans que son `mtime` ait été relu."""
        with self._verrou:
            vises = [c for c in self._entrees if c[0] == int(index)]
            for cle in vises:
                self.octets -= self._poids.pop(cle, 0)
                del self._entrees[cle]
            return len(vises)

    def vider(self) -> None:
        with self._verrou:
            self._entrees.clear()
            self._poids.clear()
            self.octets = 0

    def planches_en_cache(self) -> set[int]:
        with self._verrou:
            return {c[0] for c in self._entrees}

    # ------------------------------------------------------------------ #

    def _evincer(self) -> None:
        """⚠ Appelée verrou tenu."""
        # On garde toujours au moins une entrée, même si elle dépasse le plafond à elle seule :
        # évincer ce qu'on vient de composer ferait recomposer immédiatement.
        while self.octets > self.plafond and len(self._entrees) > 1:
            cle, _valeur = self._entrees.popitem(last=False)
            self.octets -= self._poids.pop(cle, 0)


def poids_apercu(apercu) -> int:
    """Octets qu'occupe un aperçu — ses calques, ses styles compacts, et le fond.

    ⚠ Les styles doivent être comptés. Ils sont légers (~15 ko par bulle, contre ~1 Mo de
    calques par planche : 1 à 2 % du total), mais un poids qui ignore une part du contenu est
    un plafond qui ment. `_evincer` croirait avoir de la place et le cache dériverait au-delà
    des 120 Mo annoncés — la version en creux du mode de panne décrit en tête de
    `CacheApercu`."""
    total = 0
    for calque in getattr(apercu, "calques", ()) or ():
        image = getattr(calque, "image", None)
        if image is not None:
            total += image.width * image.height * 4
    for style in (getattr(apercu, "styles", None) or {}).values():
        total += len(getattr(style, "masque", b""))
    fond = getattr(apercu, "fond", None)
    if fond is not None:
        total += fond.width * fond.height * 3
    return total
