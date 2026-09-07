#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que coûte le lancement de l'interface, chiffré — `PLAN-31` étape 0.1.

    python tools/mesure_demarrage.py
    python tools/mesure_demarrage.py --attente 10 --markdown
    python tools/mesure_demarrage.py --racine <corpus> --markdown   # cas dégradé

## Pourquoi un outil et pas une instrumentation laissée dans `gui/fenetre.py`

Parce que la mesure doit se refaire **après** le lot, sur le même corpus, avec le même
compteur. Un chronomètre posé dans la fenêtre le temps d'un relevé disparaît au commit
suivant, et le tableau « avant / après » devient incomparable. Ici la fenêtre n'est pas
touchée : l'outil enveloppe ses méthodes de l'extérieur, et ce qu'il ne trouve pas il le dit
(« n'existe plus ») plutôt que de l'inventer. C'est ce qui lui permet de tourner **des deux
côtés du lot**, alors même que le lot supprime des méthodes qu'il mesure.

## Ce que la mesure ne dit pas

- **Rien du disque froid.** Le cache de fichiers de Windows est chaud dès le deuxième
  lancement ; les temps ci-dessous sont ceux d'un lancement chaud, ce qui est le cas normal
  mais pas le pire.
- **Rien de la mise à l'échelle DPI ni du GPU.** `QT_QPA_PLATFORM=offscreen` est posé par
  défaut : la composition d'aperçus, elle, est du calcul PIL et ne change pas, mais le coût de
  peinture réel d'une fenêtre visible n'est pas compté ici.
- **Le compte de fichiers est un compte d'OUVERTURES en lecture**, pas de fichiers distincts
  touchés par le système : `os.stat` (un `exists()`) n'ouvre rien et n'est donc pas compté,
  alors qu'il coûte un aller-retour disque. Les deux nombres sont publiés séparément.
"""
from __future__ import annotations

import argparse
import builtins
import io
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))


# --------------------------------------------------------------------------- #
#  Les compteurs — aucun n'ajoute de dépendance
# --------------------------------------------------------------------------- #

class CompteurFichiers:
    """Compte les ouvertures **en lecture**, en enveloppant `open`.

    Remplace `builtins.open` ET `io.open` : ce sont deux références au même objet, mais
    `pathlib.Path.open` résout `io.open` au moment de l'appel. Ne remplacer que `builtins`
    laisserait passer tout ce que le dépôt lit par `Path.read_text` — c'est-à-dire
    l'essentiel."""

    def __init__(self) -> None:
        self.ouvertures = 0
        self.chemins: set[str] = set()
        self._actif = False
        self._vrai = builtins.open

    def __enter__(self):
        vrai = self._vrai

        def _open(fichier, mode="r", *args, **kwargs):
            if self._actif and not ({"w", "a", "x", "+"} & set(str(mode))):
                self.ouvertures += 1
                try:
                    self.chemins.add(str(fichier))
                except Exception:                       # noqa: BLE001 — descripteur nu
                    pass
            return vrai(fichier, mode, *args, **kwargs)

        builtins.open = _open
        io.open = _open
        self._actif = True
        return self

    def __exit__(self, *_exc) -> None:
        self._actif = False
        builtins.open = self._vrai
        io.open = self._vrai


def pic_memoire_mo() -> float | None:
    """Pic de mémoire résidente du processus, en Mo. `None` si la plateforme ne le dit pas.

    Aucune dépendance nouvelle : `psutil` n'est déclaré dans aucun des cinq
    `requirements-*.txt`, et un relevé de démarrage ne vaut pas d'en ajouter un. Sous Windows
    c'est `PeakWorkingSetSize` de `psapi`, ailleurs `getrusage`."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        # ⚠ `argtypes` / `restype` DÉCLARÉS, et ce n'est pas de la cérémonie : sans eux
        # `GetCurrentProcess` rend un `c_int`, la pseudo-poignée arrive tronquée, l'appel rend
        # 0 et le relevé annonçait « non mesurable » — un défaut du CHRONOMÈTRE pris pour une
        # limite de la plateforme. Depuis Windows 7 le symbole vit dans `kernel32` sous
        # `K32GetProcessMemoryInfo` ; `psapi.dll` reste un aiguillage, gardé en repli.
        noyau = ctypes.WinDLL("kernel32", use_last_error=True)
        noyau.GetCurrentProcess.restype = wintypes.HANDLE
        for bibliotheque, symbole in ((noyau, "K32GetProcessMemoryInfo"),
                                      (ctypes.WinDLL("psapi"), "GetProcessMemoryInfo")):
            fonction = getattr(bibliotheque, symbole, None)
            if fonction is None:
                continue
            fonction.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
            fonction.restype = wintypes.BOOL
            compteurs = _PMC()
            compteurs.cb = ctypes.sizeof(_PMC)
            if fonction(noyau.GetCurrentProcess(), ctypes.byref(compteurs), compteurs.cb):
                return compteurs.PeakWorkingSetSize / (1024 * 1024)
        return None
    try:
        import resource
    except ImportError:
        return None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


# --------------------------------------------------------------------------- #
#  Le relevé
# --------------------------------------------------------------------------- #

def _config(chemin: str, racine: str | None) -> dict:
    from core import cli
    config = cli.charger_config(chemin)
    if racine:
        base = Path(racine)
        chemins = dict(config.get("chemins") or {})
        chemins["sources"] = str(base / "sources")
        chemins["build"] = str(base / "build")
        config["chemins"] = chemins
        config.setdefault("manga", {})["chemins"] = dict(chemins)
    return config


def _envelopper(classe, nom: str, journal: dict) -> None:
    """Chronomètre une méthode **si elle existe encore**.

    Le lot 31 supprime `_ouvrir_tome`. Un outil qui échouerait sur son absence ne pourrait pas
    produire la colonne « après » du tableau qu'il sert à remplir."""
    original = getattr(classe, nom, None)
    if original is None:
        journal[nom] = None
        return
    journal[nom] = 0.0

    def _mesure(self, *args, **kwargs):
        debut = time.perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            journal[nom] += time.perf_counter() - debut

    setattr(classe, nom, _mesure)


#: Les méthodes chronométrées. Toutes n'existent pas des deux côtés du lot, et c'est le point.
METHODES = ("_construire", "_remplir_projets", "_remplir_tomes", "_ouvrir_tome",
            "_appliquer_reglages")


def mesurer(chemin_config: str, *, attente: float, racine: str | None) -> dict:
    """Un lancement complet, chronométré. Rend le relevé sous forme de dictionnaire."""
    from PySide6.QtWidgets import QApplication

    from core import glossary
    from gui import theme
    from gui.fenetre import Fenetre
    from manga import services as services_mod

    releve: dict = {"attente": attente}
    chrono: dict = {}
    services_construits: list[str] = []
    glossaires_lus: list[tuple[str, int]] = []

    vrai_services = services_mod.Services.__init__

    def _services(self, config, projet, **kwargs):
        services_construits.append(projet)
        return vrai_services(self, config, projet, **kwargs)

    services_mod.Services.__init__ = _services

    vrai_load = glossary.load

    def _load(chemin, *a, **k):
        try:
            glossaires_lus.append((str(chemin), Path(chemin).stat().st_size))
        except OSError:
            glossaires_lus.append((str(chemin), 0))
        return vrai_load(chemin, *a, **k)

    glossary.load = _load
    for nom in METHODES:
        _envelopper(Fenetre, nom, chrono)

    config = _config(chemin_config, racine)
    compteur = CompteurFichiers()
    with compteur:
        depart = time.perf_counter()
        app = QApplication.instance() or QApplication(sys.argv[:1])
        t_app = time.perf_counter()
        theme.appliquer(app, theme.AUTO)
        fenetre = Fenetre(config, chemin_config)
        t_construction = time.perf_counter()
        fenetre.show()
        app.processEvents()
        t_pixel = time.perf_counter()
        releve["fichiers_avant_pixel"] = compteur.ouvertures
        releve["fichiers_distincts_avant_pixel"] = len(compteur.chemins)

        fin = time.perf_counter() + attente
        while time.perf_counter() < fin:
            app.processEvents()
            time.sleep(0.02)
        t_apres = time.perf_counter()

    releve["t_qapplication"] = t_app - depart
    releve["t_construction"] = t_construction - t_app
    releve["t_premier_pixel"] = t_pixel - depart
    releve["t_apres_attente"] = t_apres - depart
    releve["chrono"] = dict(chrono)
    releve["fichiers_total"] = compteur.ouvertures
    releve["fichiers_distincts_total"] = len(compteur.chemins)
    releve["services"] = list(services_construits)
    releve["glossaires"] = list(glossaires_lus)
    releve["pic_mo"] = pic_memoire_mo()

    tome = getattr(fenetre, "tome", None)
    if tome is not None:
        releve["tome"] = f"{tome.projet} / {tome.tome}"
        try:
            releve["planches"] = len(tome.index_planches())
        except Exception as err:                        # noqa: BLE001 — cache abîmé
            releve["planches"] = f"illisible ({type(err).__name__})"
    else:
        releve["tome"] = None
        releve["planches"] = 0

    editeur = getattr(fenetre, "editeur", None)
    cache = getattr(editeur, "cache", None) if editeur is not None else None
    releve["apercus"] = len(cache) if cache is not None else 0
    releve["apercus_mo"] = (cache.octets / (1024 * 1024)) if cache is not None else 0.0
    releve["panneaux"] = _panneaux_construits(fenetre)

    fenetre.fil_lecture.arreter()
    fenetre.fil.arreter()
    fenetre.fil_lecture.wait(3000)
    fenetre.fil.wait(3000)
    services_mod.Services.__init__ = vrai_services
    glossary.load = vrai_load
    return releve


def _panneaux_construits(fenetre) -> list[str]:
    """Les panneaux réellement instanciés. Deux implémentations, une par génération.

    Avant le lot 31, les trois panneaux sont des attributs posés par `_construire` ; après, la
    fenêtre tient un registre des destinations construites."""
    registre = getattr(fenetre, "panneaux_construits", None)
    if callable(registre):
        return sorted(registre())
    noms = []
    for attribut, nom in (("editeur", "Planches"), ("lanceur", "Runs"),
                          ("atelier", "Atelier")):
        if getattr(fenetre, attribut, None) is not None:
            noms.append(nom)
    return noms


# --------------------------------------------------------------------------- #
#  Sortie
# --------------------------------------------------------------------------- #

def _duree(valeur) -> str:
    return "— (n'existe plus)" if valeur is None else f"{valeur:.2f} s"


def rendre_markdown(releve: dict) -> str:
    chrono, glossaires = releve["chrono"], releve["glossaires"]
    attente = releve["attente"]
    lignes = [
        "| Grandeur | Mesure |",
        "|---|---|",
        f"| temps `QApplication()` → `fenetre.show()` | "
        f"**{releve['t_premier_pixel']:.2f} s** |",
        f"| dont construction de `QApplication` | {releve['t_qapplication']:.2f} s |",
        f"| dont `Fenetre.__init__` | {releve['t_construction']:.2f} s |",
        f"| dont `_construire` (les panneaux) | {_duree(chrono.get('_construire'))} |",
        f"| dont `_remplir_projets` (et ce qu'il déclenche) | "
        f"{_duree(chrono.get('_remplir_projets'))} |",
        f"| dont `_ouvrir_tome` seul | {_duree(chrono.get('_ouvrir_tome'))} |",
        f"| ouvertures de fichiers en lecture avant le premier pixel | "
        f"{releve['fichiers_avant_pixel']} "
        f"({releve['fichiers_distincts_avant_pixel']} chemins distincts) |",
        f"| tome ouvert sans qu'on le demande | {releve['tome'] or '**aucun**'} |",
        f"| planches indexées de ce tome | {releve['planches']} |",
        f"| panneaux construits | {', '.join(releve['panneaux']) or '**aucun**'} |",
        "| `Services` construit ? | "
        + ("oui — " + ", ".join(releve["services"]) if releve["services"] else "**non**")
        + " |",
        "| glossaire YAML lu ? | "
        + (", ".join(f"{Path(c).name} ({t / 1024:.1f} Ko)" for c, t in glossaires)
           if glossaires else "**non**") + " |",
        f"| aperçus composés dans les {attente:.0f} s qui suivent | {releve['apercus']} |",
        f"| poids du cache d'aperçus | {releve['apercus_mo']:.1f} Mo |",
        f"| ouvertures de fichiers, {attente:.0f} s après le premier pixel | "
        f"{releve['fichiers_total']} "
        f"({releve['fichiers_distincts_total']} chemins distincts) |",
        "| pic de mémoire résidente | "
        + (f"{releve['pic_mo']:.0f} Mo" if releve["pic_mo"] else "non mesurable") + " |",
    ]
    return "\n".join(lignes)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--attente", type=float, default=10.0,
                    help="secondes d'observation après le premier pixel (défaut : 10)")
    ap.add_argument("--racine", default=None,
                    help="racine d'un corpus de remplacement (sources/ et build/ dessous)")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--ecran", action="store_true",
                    help="ne pas forcer QT_QPA_PLATFORM=offscreen")
    args = ap.parse_args()

    from core import cli
    cli.configurer_stdout()
    if not args.ecran:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    releve = mesurer(args.config, attente=args.attente, racine=args.racine)
    if args.markdown:
        print(rendre_markdown(releve))
        return
    for cle, valeur in releve.items():
        print(f"{cle:34s} {valeur}")


if __name__ == "__main__":
    main()
