# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le compte de tests collectés, et sa comparaison entre deux systèmes.

## Pourquoi un outil pour compter

Parce que c'est le chiffre qui a le plus divergé dans ce dépôt : 1 908, 1 657, « un millier et
demi » et 2 262 ont circulé en même temps. Il se reproduit par une commande
(`pytest --collect-only -q`), mais tant que personne ne l'exécute au même endroit que la CI, il
se périme sans que rien ne l'indique.

## Ce qu'il achète en CI

Un test **non collecté** ne se voit nulle part dans le compte-rendu — c'est le défaut central
que ce lot corrige : sur un runner Linux, la fixture `synthetic_manga_page` se sautait en
silence et emportait toute la couverture détection / OCR / orchestrateur. Comparer les comptes
des deux OS transforme cette perte en échec de build. C'est la même logique que la mesure
« collectés avec PySide6 contre sans » qui justifie son installation dans `ci.yml`.

⚠ **Ce n'est PAS la même chose que compter les tests qui PASSENT.** Un test collecté peut être
sauté à l'exécution ; ce compte-ci mesure ce que pytest a trouvé, pas ce qu'il a exécuté. Les
deux chiffres sont utiles, ils ne se remplacent pas.

## Usage

    python tools/compte_de_tests.py                              # le total
    python tools/compte_de_tests.py -m "not lent and not modeles" # la boucle courte
    python tools/compte_de_tests.py --sortie compte-windows.json
    python tools/compte_de_tests.py --comparer compte-windows.json compte-ubuntu.json
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: Les deux formes que pytest imprime en mode `-q` :
#:   « 2 791 tests collected in 20.30s »        (sans `-m`)
#:   « 2734/2791 tests collected (57 deselected) in 19.60s »
_TOTAL_SEUL = re.compile(r"^(\d+) tests? collected", re.MULTILINE)
_AVEC_SELECTION = re.compile(r"^(\d+)/(\d+) tests? collected \((\d+) deselected\)",
                             re.MULTILINE)


class CollecteIllisible(RuntimeError):
    """pytest n'a pas imprimé de ligne de compte — typiquement une erreur de collecte.
    Rendre 0 serait pire : un compte de zéro se compare très bien à un autre compte de zéro."""


def analyser_sortie(sortie: str) -> tuple[int, int, int]:
    """Rend `(collectes, total, deselectionnes)`. Fonction pure : c'est elle qui est testée."""
    m = _AVEC_SELECTION.search(sortie)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = _TOTAL_SEUL.search(sortie)
    if m:
        return int(m.group(1)), int(m.group(1)), 0
    raise CollecteIllisible(
        "aucune ligne « N tests collected » dans la sortie de pytest. C'est presque toujours "
        "une ERREUR DE COLLECTE (import cassé) : la traiter comme « zéro test » rendrait un "
        "build vert sur une suite qui ne se charge plus.\n\n" + sortie[-2000:])


def collecter(marqueurs: str | None = None) -> dict[str, object]:
    commande = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    if marqueurs:
        commande += ["-m", marqueurs]
    resultat = subprocess.run(commande, cwd=RACINE, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    collectes, total, deselectionnes = analyser_sortie(resultat.stdout + resultat.stderr)
    return {
        "collectes": collectes,
        "total": total,
        "deselectionnes": deselectionnes,
        "marqueurs": marqueurs or "",
        # Le système fait partie du dénominateur : c'est tout l'objet de la comparaison.
        "systeme": platform.system().lower(),
        "python": platform.python_version(),
    }


def comparer(a: dict, b: dict) -> list[str]:
    """Les écarts entre deux relevés. Liste vide = les deux systèmes voient la même suite."""
    ecarts = []
    if a.get("marqueurs") != b.get("marqueurs"):
        ecarts.append(f"marqueurs différents : {a.get('marqueurs')!r} contre "
                      f"{b.get('marqueurs')!r} — les deux relevés ne mesurent pas la même chose")
    for cle in ("collectes", "total", "deselectionnes"):
        if a.get(cle) != b.get(cle):
            ecarts.append(
                f"{cle} : {a['systeme']} en voit {a.get(cle)}, {b['systeme']} en voit "
                f"{b.get(cle)}. Un test non collecté ne se voit nulle part dans le "
                f"compte-rendu : l'écart est une couverture perdue, pas une curiosité.")
    return ecarts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compte de tests collectés, et comparaison.")
    ap.add_argument("-m", "--marqueurs", default=None,
                    help='expression de marqueurs, ex. "not lent and not modeles"')
    ap.add_argument("--sortie", default=None, help="écrire le relevé en JSON dans ce fichier")
    ap.add_argument("--comparer", nargs=2, metavar=("A", "B"), default=None,
                    help="comparer deux relevés JSON au lieu d'en produire un")
    ap.add_argument("--markdown", action="store_true")
    a = ap.parse_args(argv)

    if a.comparer:
        releves = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.comparer]
        ecarts = comparer(*releves)
        if a.markdown:
            print("### Cohérence de la collecte entre systèmes\n")
            for releve in releves:
                print(f"- **{releve['systeme']}** (python {releve['python']}) : "
                      f"{releve['collectes']} collectés sur {releve['total']}")
            print()
            print("✅ Les deux systèmes voient la même suite." if not ecarts
                  else "❌ " + "\n- ".join([""] + ecarts))
        else:
            for releve in releves:
                print(f"{releve['systeme']}: {releve['collectes']}/{releve['total']}")
            print("\n".join(ecarts) if ecarts else "aucun écart.")
        return 1 if ecarts else 0

    releve = collecter(a.marqueurs)
    if a.sortie:
        Path(a.sortie).write_text(json.dumps(releve, indent=2), encoding="utf-8")
    print(json.dumps(releve, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
