# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Mémoire résidente du processus — le chiffre qui n'existait nulle part.

## Pourquoi ce module

Le dépôt mesure tout : durées par étage, bulles par planche, tokens par tome, aire cédée par
`rendre_disjoints`. Il ne mesurait **pas** ce qu'un run coûte en mémoire, et c'est le seul
chiffre qui décide si la brique manga tourne sur la machine d'un contributeur ou seulement sur
celle qui l'a écrite. Une bande de webtoon 1080×10 000 porte des masques booléens **pleine
page** de 10,8 Mo pièce (`manga/detection.py`, `BubbleRegion`), et rien ne bornait leur nombre.

## Aucune dépendance, et c'était la condition

`psutil` aurait fait ça en une ligne. C'est aussi 2 Mo de roues compilées par plateforme pour
lire un entier, dans un projet qui refuse déjà OpenCV (~60 Mo) pour trois opérations de
morphologie (`requirements-manga.txt`). Les trois systèmes exposent le chiffre en standard :

    Windows   kernel32!K32GetProcessMemoryInfo → PROCESS_MEMORY_COUNTERS
    Linux     /proc/self/status, VmHWM (en kio)
    macOS/BSD resource.getrusage(RUSAGE_SELF).ru_maxrss

⚠ **Les `argtypes` du chemin Windows ne sont pas décoratifs.** Sans
`GetCurrentProcess.restype = HANDLE`, ctypes rend le pseudo-handle `-1` comme un `c_int` de
32 bits, l'appel échoue, et `GetProcessMemoryInfo` rend **zéro** — pas une erreur, zéro. Une
sonde de mémoire qui répond « 0 Mo » sans se plaindre est pire que pas de sonde du tout :
constaté en écrivant ce module, sur la première mesure des neuf bandes.

## Ce que le chiffre dit

`pic()` rend le **maximum atteint depuis le lancement du processus**, jamais un instantané :
c'est le seul chiffre qui répond à « est-ce que ça tient sur 8 Go ». Un pic est monotone, donc
un pic mesuré autour d'une étape se lit toujours en DIFFÉRENTIEL (`Pic.autour`), sans quoi on
attribuerait à l'OCR la mémoire que la détection avait déjà prise.

Toutes les fonctions rendent `None` — jamais une exception, jamais une valeur inventée — quand
le système ne sait pas répondre. Un `perf.log` sans ligne de mémoire reste un `perf.log`."""
from __future__ import annotations

import sys
from dataclasses import dataclass


#: Le couple `(kernel32, structure)` du chemin Windows, préparé UNE fois.
#:
#: ⚠ Pas de la micro-optimisation : la sonde est appelée quatre fois par planche, et
#: reconstruire un `WinDLL` et une `Structure` à chaque appel ferait payer à un tome de
#: 150 planches six cents chargements de bibliothèque pour lire un entier. `None` tant qu'on
#: n'a pas essayé, `False` quand l'essai a échoué — pour ne pas le refaire cent fois.
_WIN: object = None


def _preparer_windows():
    """`(kernel32, type de structure)`, ou `None` si le chemin Windows n'est pas utilisable."""
    import ctypes
    import ctypes.wintypes as wt

    class _Compteurs(ctypes.Structure):
        _fields_ = [
            ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    try:
        k32 = ctypes.WinDLL("kernel32")
        # ⚠ Les trois lignes qui suivent sont la correction, pas de la cérémonie : cf. le
        # module. Un pseudo-handle rendu en c_int fait échouer l'appel EN SILENCE.
        k32.GetCurrentProcess.restype = wt.HANDLE
        k32.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_Compteurs),
                                                wt.DWORD]
        k32.K32GetProcessMemoryInfo.restype = wt.BOOL
    except (OSError, AttributeError, ValueError):
        return None
    return k32, _Compteurs


def _pic_windows() -> int | None:
    import ctypes

    global _WIN
    if _WIN is None:
        _WIN = _preparer_windows() or False
    if _WIN is False:
        return None
    k32, compteurs_type = _WIN
    compteurs = compteurs_type()
    compteurs.cb = ctypes.sizeof(compteurs_type)
    try:
        if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(),
                                           ctypes.byref(compteurs), compteurs.cb):
            return None
    except (OSError, ValueError):
        return None
    return int(compteurs.PeakWorkingSetSize)


def _pic_linux() -> int | None:
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for ligne in f:
                if ligne.startswith("VmHWM:"):
                    return int(ligne.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _pic_rusage() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    try:
        brut = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, ValueError):
        return None
    # ⚠ L'unité de `ru_maxrss` n'est pas portable : kibioctets sous Linux, OCTETS sous
    # Darwin/BSD. Se tromper d'unité rend un chiffre mille fois faux, ce qui est exactement le
    # genre de mesure qu'on préfère ne pas avoir.
    return int(brut) if sys.platform == "darwin" else int(brut) * 1024


def pic() -> int | None:
    """Mémoire résidente MAXIMALE atteinte par le processus depuis son lancement, en octets.

    `None` quand le système ne sait pas répondre — un chiffre inventé serait pire."""
    if sys.platform.startswith("win"):
        return _pic_windows()
    if sys.platform.startswith("linux"):
        return _pic_linux() or _pic_rusage()
    return _pic_rusage()


def format_octets(octets: int | None) -> str:
    """`1 342 177 280` → `« 1,25 Go »`. `None` → `« ? »`, jamais `« 0 Mo »`."""
    if octets is None:
        return "?"
    valeur = float(octets)
    for unite, seuil in (("Go", 1024 ** 3), ("Mo", 1024 ** 2), ("ko", 1024)):
        if valeur >= seuil:
            return f"{valeur / seuil:.2f} {unite}".replace(".", ",")
    return f"{int(valeur)} o"


@dataclass
class Pic:
    """Le pic de mémoire AUTOUR d'une étape, mesuré en différentiel.

        with Pic() as p:
            regions = detecteur.detect(image)
        reporter.verbose(f"[detection] {p}")

    `apres` est le pic du processus à la sortie, `gagne` ce que l'étape a ajouté au pic
    existant. Les deux comptent, et pas pour la même question : `apres` répond à « est-ce que
    ce run tient dans la RAM de la machine », `gagne` à « quelle étape faut-il réparer ».

    ⚠ `gagne` vaut **0 dès la deuxième planche** dans le cas nominal, et ce n'est pas un
    défaut : le pic est monotone, une étape qui ne dépasse pas ce qui a déjà été atteint
    n'ajoute rien. C'est exactement ce qu'on veut lire — la planche qui coûte le plus est celle
    qui fait bouger le chiffre."""

    avant: int | None = None
    apres: int | None = None

    def __enter__(self) -> "Pic":
        self.avant = pic()
        return self

    def __exit__(self, *_exc) -> None:
        self.apres = pic()

    @property
    def gagne(self) -> int | None:
        if self.avant is None or self.apres is None:
            return None
        return max(0, self.apres - self.avant)

    def __str__(self) -> str:
        if self.apres is None:
            return "mémoire : ?"
        gagne = self.gagne
        if not gagne:
            return f"mémoire : pic {format_octets(self.apres)}"
        return f"mémoire : pic {format_octets(self.apres)} (+{format_octets(gagne)})"
