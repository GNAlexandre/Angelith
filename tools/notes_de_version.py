# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les notes de version d'un tag, découpées dans le CHANGELOG.

## Pourquoi découper plutôt que rédiger

`CHANGELOG.md` fait 380 Ko et ses entrées sont détaillées : elles nomment les fichiers, citent
les mesures et expliquent les arbitrages. **Ce sont déjà des notes de version.** Les réécrire
pour une release GitHub produirait un second texte à tenir à jour, qui divergerait du premier
— c'est exactement le défaut que `docs/chiffres-de-reference.md` documente pour les chiffres.

## Le garde-fou qui compte

`--verifier` refuse un tag qui ne correspond pas à `core/version.py`. C'est le complément
symétrique de `tests/test_version.py`, qui vérifie que `core/version.py` correspond à la
première entrée datée du CHANGELOG : à eux deux, tag ⇄ version ⇄ CHANGELOG ne peuvent plus
diverger. Poser `v2.10.1` sur un arbre qui déclare `2.10.0` publierait une release dont le
contenu n'est documenté nulle part.

## Usage

    python tools/notes_de_version.py 2.10.0            # le corps de la release
    python tools/notes_de_version.py v2.10.0 --verifier # + contrôle contre core/version.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CHANGELOG = RACINE / "CHANGELOG.md"

#: Le même motif que `tests/test_version.py` : tiret ASCII ou cadratin, les deux se
#: rencontrent en français. La date est capturée pour être rappelée en tête de la release.
_ENTREE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]\s*[-–—]\s*(\d{4}-\d{2}-\d{2})\s*$")
_TOUT_TITRE = re.compile(r"^##\s*\[")


class VersionIntrouvable(LookupError):
    """La version demandée n'a pas d'entrée DATÉE dans le CHANGELOG."""


def normaliser(version: str) -> str:
    """`v2.10.0` et `2.10.0` désignent la même chose ; le CHANGELOG écrit la seconde forme."""
    return version[1:] if version.startswith(("v", "V")) else version


def extraire(changelog: str, version: str) -> tuple[str, str]:
    """Rend `(date, corps)` pour `version`. Le corps EXCLUT la ligne de titre : GitHub
    affiche déjà le nom du tag au-dessus du corps, la répéter fait doublon."""
    voulue = normaliser(version)
    lignes = changelog.splitlines()
    debut = date = None
    for i, ligne in enumerate(lignes):
        m = _ENTREE.match(ligne)
        if debut is None:
            if m and m.group(1) == voulue:
                debut, date = i, m.group(2)
        elif _TOUT_TITRE.match(ligne):
            return date, "\n".join(lignes[debut + 1:i]).strip("\n")
    if debut is None:
        raise VersionIntrouvable(
            f"aucune entrée « ## [{voulue}] - AAAA-MM-JJ » dans le CHANGELOG. Une entrée non "
            f"datée (sous « [Non publié] ») n'est pas publiable : c'est la date qui distingue "
            f"une version livrée d'un travail en cours.")
    return date, "\n".join(lignes[debut + 1:]).strip("\n")


def main(argv: list[str] | None = None) -> int:
    # ⚠ **Pas `core.cli.configurer_stdout()`, et ce n'est pas un oubli.** Ce fichier
    # n'importe QUE la bibliothèque standard, et le job « Garde-fous » le lance sur un Python
    # nu — `.github/workflows/garde-fous.yml` ne fait aucun `pip install`. Importer
    # `core.cli` tirerait `yaml` et casserait le job. D'où ces quatre lignes, répétées dans
    # les outils sans dépendance et tenues en phase par `tests/test_outils_sortie.py`.
    #
    # Sans elles, une console Windows en cp1252 fait tomber l'outil sur le premier « ⚠ » —
    # mesuré le 2026-09-04 : `verifier_disclosure.py --historique 3` levait un
    # `UnicodeEncodeError` APRÈS avoir jugé les commits, donc en perdant son verdict.
    for _flux in (sys.stdout, sys.stderr):
        try:
            _flux.reconfigure(encoding="utf-8")
        except Exception:      # noqa: BLE001 — flux remplacé (test, pipe) ou non reconfigurable
            pass

    ap = argparse.ArgumentParser(description="Notes de version, découpées dans le CHANGELOG.")
    ap.add_argument("version", help="2.10.0 ou v2.10.0")
    ap.add_argument("--verifier", action="store_true",
                    help="échouer si la version demandée diffère de core/version.py")
    ap.add_argument("--sortie", default=None, help="écrire dans un fichier (UTF-8) au lieu "
                                                   "de stdout")
    a = ap.parse_args(argv)

    voulue = normaliser(a.version)
    if a.verifier:
        sys.path.insert(0, str(RACINE))
        from core.version import __version__
        if voulue != __version__:
            print(f"le tag demande {voulue} mais core/version.py declare {__version__} — "
                  f"publier ici poserait une release dont le contenu n'est documente nulle "
                  f"part (cf. tests/test_version.py)", file=sys.stderr)
            return 1

    try:
        date, corps = extraire(CHANGELOG.read_text(encoding="utf-8"), voulue)
    except VersionIntrouvable as e:
        print(str(e), file=sys.stderr)
        return 2

    texte = f"*Publié le {date}. Extrait de [`CHANGELOG.md`](CHANGELOG.md).*\n\n{corps}\n"
    if a.sortie:
        Path(a.sortie).write_text(texte, encoding="utf-8")
    else:
        print(texte, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
