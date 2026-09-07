#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Compiler Angelith — **une commande**, du gel à l'installeur signé de son empreinte.

    python tools/geler.py                     # la chaîne complète
    python tools/geler.py --outils            # dit ce qui manque, et ne fait RIEN
    python tools/geler.py --sans-installeur   # le gel et ses trois vérifications
    python tools/geler.py --verifier-seulement    # rejoue les 3 tests sur un dist/ existant

## Pourquoi cet outil existe

Le lot 37 a livré les pièces — `angelith.spec`, `installeur/generer.py`,
`installeur/angelith.iss`, `tools/verifier_gel.py` — et **rien qui les enchaîne**. Compiler,
c'était cinq commandes recopiées depuis `docs/COMMANDES.fr.md`, dans le bon ordre, avec les
bons chemins. Une séquence qu'on recopie est une séquence qu'on finit par exécuter à moitié :
le lot 37 s'est lui-même livré avec un installeur portant le numéro de la version précédente,
faute d'avoir régénéré `installeur/version.iss` avant de compiler.

⚠ **La CI appelle CET outil**, elle ne réécrit pas la séquence. C'est ce qui garantit que le
chemin local et le chemin d'intégration font la même chose — et c'est aussi ce qui a corrigé un
défaut réel : `ci.yml` cherchait Inno Setup dans `C:\\Program Files (x86)`, alors qu'une
installation par winget en portée utilisateur le met dans `%LOCALAPPDATA%\\Programs`. Le job
aurait marché, la commande documentée non.

## Ce qu'il refuse de faire

Il **n'installe rien**. Ni PyInstaller, ni Inno Setup. `pyinstaller` n'est déclaré ni dans
`pyproject.toml` ni dans un `requirements-*.txt`, et c'est délibéré : un empaqueteur n'est pas
une dépendance de ce qu'il empaquette. L'outil dit la commande et s'arrête — même ligne que
`core/reparations.py`, qui n'installe aucun logiciel système.

Il **ne décide pas non plus du jeu de dépendances**. Ce qui est gelé est ce que l'environnement
courant porte ; c'est `docs/mesures/empaquetage-2026-09-06.md` §2 qui dit quel jeu est livré, et
la CI qui l'installe. Un outil qui installerait des paquets pour geler produirait un binaire
différent de celui qu'on a testé.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: Où PyInstaller écrit ses intermédiaires. ⚠ **Surtout pas `build/`**, qui est son défaut : ce
#: dossier porte les SORTIES du pipeline dans ce dépôt — des tomes traduits, des checkpoints qui
#: coûtent des heures de GPU. Le motif complet est dans l'en-tête d'`angelith.spec`.
TRAVAIL = ".pyinstaller"

#: Où atterrissent le dossier gelé et l'installeur.
DIST = "dist"

#: Les emplacements connus d'Inno Setup, dans l'ordre où on les essaie.
#:
#: ⚠ **Les deux, et ce n'est pas de la générosité.** L'installation par défaut du programme
#: d'installation officiel va dans `Program Files (x86)` (c'est le cas sur les images
#: `windows-latest` de GitHub) ; `winget install --scope user` la met dans `%LOCALAPPDATA%`
#: (c'est le cas sur la machine principale de ce projet). Coder le premier en dur — ce que
#: faisait `ci.yml` — rend la commande documentée fausse pour qui a installé l'autre.
ISCC_CANDIDATS: tuple[str, ...] = (
    r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
)


@dataclass(frozen=True)
class Outil:
    """Un maillon de la chaîne, et ce qu'il faut faire s'il manque."""

    nom: str
    present: bool
    ou: str = ""
    geste: str = ""

    def ligne(self) -> str:
        return (f"✓ {self.nom} — {self.ou}" if self.present
                else f"❌ {self.nom} introuvable\n   → {self.geste}")


def outil_pyinstaller() -> Outil:
    try:
        import PyInstaller                                            # noqa: PLC0415
    except ImportError:
        return Outil("PyInstaller", False,
                     geste="pip install pyinstaller   (⚠ ce n'est PAS une dépendance du "
                           "projet : un empaqueteur n'est pas une dépendance de ce qu'il "
                           "empaquette, et il n'est donc dans aucun requirements-*.txt)")
    return Outil("PyInstaller", True, ou=PyInstaller.__version__)


def chemin_iscc() -> str:
    """Le compilateur Inno Setup, cherché dans le `PATH` puis aux emplacements connus."""
    trouve = shutil.which("ISCC") or shutil.which("iscc")
    if trouve:
        return trouve
    for gabarit in ISCC_CANDIDATS:
        candidat = Path(os.path.expandvars(gabarit))
        if candidat.is_file():
            return str(candidat)
    return ""


def outil_iscc() -> Outil:
    trouve = chemin_iscc()
    if trouve:
        return Outil("Inno Setup (ISCC)", True, ou=trouve)
    return Outil("Inno Setup (ISCC)", False,
                 geste="winget install --id JRSoftware.InnoSetup --scope user\n"
                       "     (ou https://jrsoftware.org/isdl.php ; l'outil le cherche dans le "
                       "PATH, dans %LOCALAPPDATA%\\Programs et dans Program Files)")


def outils(*, installeur: bool = True) -> list[Outil]:
    liste = [outil_pyinstaller()]
    if installeur:
        liste.append(outil_iscc())
    return liste


# --------------------------------------------------------------------------- #
#  La chaîne
# --------------------------------------------------------------------------- #

def _executer(etape: str, commande: list[str], *, dire) -> float:
    """Lance une étape et rend sa durée. Lève `SystemExit` sur échec, en le nommant."""
    dire(f"\n— {etape} —")
    dire("  " + " ".join(commande))
    depart = time.perf_counter()
    resultat = subprocess.run(commande, cwd=RACINE)
    ecoule = time.perf_counter() - depart
    if resultat.returncode != 0:
        raise SystemExit(f"❌ {etape} a échoué (code {resultat.returncode}) après "
                         f"{ecoule:.1f} s.")
    dire(f"  ✓ {ecoule:.1f} s")
    return ecoule


def geler(*, installeur: bool = True, dire=print) -> dict[str, float]:
    """La chaîne complète. Rend la durée de chaque étape.

    ⚠ L'ordre n'est pas indifférent : `installeur/generer.py --verifier` passe **avant** le gel.
    Découvrir un `version.iss` périmé après huit minutes de PyInstaller est exactement ce qui
    est arrivé au lot 37."""
    durees: dict[str, float] = {}
    python = sys.executable

    durees["version"] = _executer(
        "Le numéro de version vient de core/version.py",
        [python, "installeur/generer.py"], dire=dire)

    durees["gel"] = _executer(
        "Geler — un DOSSIER, jamais un fichier",
        [python, "-m", "PyInstaller", "angelith.spec", "--noconfirm",
         "--workpath", TRAVAIL, "--distpath", DIST], dire=dire)

    durees.update(verifier(dire=dire))

    if installeur:
        durees["installeur"] = _executer(
            "Construire l'installeur (Inno Setup)",
            [chemin_iscc(), str(RACINE / "installeur" / "angelith.iss")], dire=dire)
        durees["empreintes"] = _executer(
            "Empreintes SHA-256 des fichiers publiés",
            [python, "tools/verifier_gel.py", "--empreintes", DIST,
             "--sortie", f"{DIST}/SHA256SUMS.txt"], dire=dire)
    return durees


def verifier(*, dire=print) -> dict[str, float]:
    """Les **trois** vérifications du `PLAN-37` L37.7, sur le binaire réellement produit.

    Elles attrapent les trois pannes classiques du gel, et les trois ont été rencontrées pour
    de vrai pendant le lot 37 : la version perdue, un chemin relatif à `__file__`, un module Qt
    élagué de trop.

    ⚠ **`angelith-console.exe` et non `angelith-gui.exe`.** Sous Windows, un binaire lié en
    sous-système « fenêtre » n'a pas de sortie standard : le premier essai de ces vérifications
    n'a rien écrit et n'est jamais sorti."""
    exe = RACINE / DIST / "Angelith" / "angelith-console.exe"
    if not exe.is_file():
        raise SystemExit(f"❌ {exe} est introuvable — il n'y a rien à vérifier. "
                         f"Lance `python tools/geler.py` sans --verifier-seulement.")
    python = sys.executable
    durees: dict[str, float] = {}

    durees["version_du_gel"] = _executer(
        "1/3 — la version survit au gel", [str(exe), "--version"], dire=dire)

    # ⚠ Dans un FICHIER, pas sur stdout : une dépendance tierce (`transformers`) écrit un
    # avertissement avant le premier octet du JSON. Mesuré le 2026-09-06.
    diagnostic = RACINE / "diagnostic-gel.json"
    durees["diagnostic_du_gel"] = _executer(
        "2/3 — le gel sait dire ce qui lui manque",
        [str(exe), "--diagnostic-json", str(diagnostic)], dire=dire)
    _executer("     vérification du relevé",
              [python, "tools/verifier_gel.py", "--diagnostic", str(diagnostic)], dire=dire)

    demarrage = RACINE / "demarrage-gel.json"
    environnement = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    dire("\n— 3/3 — la fenêtre s'ouvre sur l'accueil, sans ouvrir de tome —")
    depart = time.perf_counter()
    resultat = subprocess.run([str(exe), "--verifier-demarrage"], cwd=RACINE,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=environnement)
    demarrage.write_text(resultat.stdout or "", encoding="utf-8")
    durees["demarrage_du_gel"] = time.perf_counter() - depart
    if resultat.returncode != 0:
        raise SystemExit(f"❌ le gel n'a pas passé la vérification de démarrage :\n"
                         f"{resultat.stdout}\n{resultat.stderr}")
    _executer("     vérification du relevé",
              [python, "tools/verifier_gel.py", "--demarrage", str(demarrage)], dire=dire)
    return durees


def _poids(dossier: Path) -> tuple[float, int]:
    octets = fichiers = 0
    for racine, _sous, noms in os.walk(dossier):
        for nom in noms:
            try:
                octets += os.path.getsize(os.path.join(racine, nom))
                fichiers += 1
            except OSError:
                pass
    return octets / 1024 / 1024, fichiers


def main() -> int:
    # ⚠ **Pas `core.cli.configurer_stdout()`** : cet outil doit tourner sur un Python nu, comme
    # `tools/verifier_livraison.py` — la convention et son motif sont dans
    # `tests/test_outils_sortie.py`.
    for _flux in (sys.stdout, sys.stderr):
        try:
            _flux.reconfigure(encoding="utf-8")
        except Exception:      # noqa: BLE001 — flux remplacé (test, pipe) ou non reconfigurable
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--outils", action="store_true",
                    help="dit ce qui manque pour compiler, et ne fait rien d'autre")
    ap.add_argument("--sans-installeur", action="store_true",
                    help="gèle et vérifie, mais ne construit pas l'installeur")
    ap.add_argument("--verifier-seulement", action="store_true",
                    help="rejoue les trois vérifications sur un dist/ déjà construit")
    args = ap.parse_args()

    avec_installeur = not args.sans_installeur
    liste = outils(installeur=avec_installeur)
    if args.outils:
        for outil in liste:
            print(outil.ligne())
        return 0 if all(o.present for o in liste) else 1

    if args.verifier_seulement:
        verifier()
        print("\n✓ Le gel passe les trois vérifications.")
        return 0

    manquants = [o for o in liste if not o.present]
    if manquants:
        print("Il manque de quoi compiler :\n")
        for outil in manquants:
            print(outil.ligne())
        return 1

    durees = geler(installeur=avec_installeur)
    mo, fichiers = _poids(RACINE / DIST / "Angelith")
    print("\n— Récapitulatif —")
    for etape, duree in durees.items():
        print(f"  {etape:22} {duree:6.1f} s")
    print(f"  {'total':22} {sum(durees.values()):6.1f} s")
    print(f"\nDossier gelé : {mo:.1f} Mo, {fichiers} fichiers.")
    installeurs = sorted((RACINE / DIST).glob("*.exe"))
    for fichier in installeurs:
        print(f"Installeur   : {fichier.name} "
              f"({fichier.stat().st_size / 1024 / 1024:.1f} Mo)")
    if avec_installeur:
        print(f"Empreintes   : {DIST}/SHA256SUMS.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
