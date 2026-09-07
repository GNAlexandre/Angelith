"""Extraction des issues SonarQube Cloud vers un fichier lisible, pour triage.

SonarQube Cloud n'offre AUCUN export depuis l'interface : le seul chemin est l'API web.
Ce script la lit, la pagine, et écrit un `.md` groupé par fichier plus un `.json` brut.

    python tools/sonar_issues.py --branche main

Le jeton est lu dans `SONAR_TOKEN`, ou, à défaut, dans le fichier `.sonar-token` à la racine
(exclu par `.gitignore` — un jeton n'a pas à exister dans l'arbre git) :

    $env:SONAR_TOKEN = "xxxxx"          (PowerShell, le temps d'une session)
    "xxxxx" | Out-File -Encoding ascii -NoNewline .sonar-token      (une fois pour toutes)

⚠ Le jeton attendu est un JETON UTILISATEUR (My Account > Security), pas le jeton d'analyse
de la CI : celui-ci n'a que le droit d'exécuter un scan, l'API de lecture le refuse.

⚠ Le `.md` produit N'EST PAS une liste de corrections à appliquer. Beaucoup de règles Sonar
recoupent des familles que `ruff.toml` écarte NOMMÉMENT et pour des raisons mesurées
(E501, BLE001 sur les `except Exception` défendus de `core/power.py`, `core/llm.py`,
`core/reporter.py`, B023 dans la boucle par chapitre). Une issue Sonar sur ce terrain
n'annule pas la décision déjà prise : elle demande qu'on la répète, ou qu'on la révise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

BASE = "https://sonarcloud.io"
CLE_PROJET = "GNAlexandre_Yume-Trad"
PAGE = 500          # maximum admis par l'API
PLAFOND = 10_000    # p * ps est plafonné côté serveur : au-delà, il faut filtrer


def _appel(chemin: str, params: dict, jeton: str) -> dict:
    url = f"{BASE}{chemin}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {jeton}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"HTTP {e.code} sur {chemin} — {detail}") from e


def _pagine(chemin: str, params: dict, cle: str, jeton: str) -> list[dict]:
    """Rend TOUS les éléments, ou s'arrête bruyamment si le plafond serveur est atteint.

    Un `break` silencieux ici rendrait une extraction tronquée qui ressemble à une
    extraction complète — c'est le même défaut qu'une CI verte qui ne teste plus rien."""
    tout: list[dict] = []
    page = 1
    while True:
        data = _appel(chemin, {**params, "ps": PAGE, "p": page}, jeton)
        lot = data.get(cle, [])
        tout.extend(lot)
        total = data.get("total") or data.get("paging", {}).get("total", len(tout))
        if len(tout) >= total or not lot:
            if len(tout) < total:
                print(f"⚠ {chemin} : {len(tout)}/{total} seulement — page vide avant la fin",
                      file=sys.stderr)
            return tout
        if page * PAGE >= PLAFOND:
            raise SystemExit(
                f"Plafond de l'API atteint sur {chemin} ({PLAFOND}). Filtre par sévérité ou "
                f"par répertoire et relance : l'extraction serait tronquée en silence.")
        page += 1


def _fichier(composant: str) -> str:
    """`GNAlexandre_Yume-Trad:core/cli.py` -> `core/cli.py`."""
    return composant.split(":", 1)[-1]


FICHIER_JETON = Path(__file__).resolve().parent.parent / ".sonar-token"


def _jeton() -> str:
    """`SONAR_TOKEN` d'abord, puis `.sonar-token` à la racine.

    L'environnement garde la priorité : c'est lui que la CI renseigne, et une machine de
    développement doit pouvoir surcharger le fichier sans le réécrire."""
    jeton = (os.environ.get("SONAR_TOKEN") or "").strip()
    if jeton:
        return jeton
    if FICHIER_JETON.is_file():
        jeton = FICHIER_JETON.read_text(encoding="utf-8").strip()
        if jeton:
            return jeton
    raise SystemExit(
        f"Jeton introuvable : ni SONAR_TOKEN dans l'environnement, ni {FICHIER_JETON.name} "
        f"non vide à la racine. Il s'agit d'un JETON UTILISATEUR (My Account > Security), "
        f"pas du jeton d'analyse de la CI.")


def main() -> int:
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

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--branche", default="main")
    ap.add_argument("--projet", default=CLE_PROJET)
    ap.add_argument("--sortie", default="sonar-issues", help="préfixe des fichiers produits")
    args = ap.parse_args()

    jeton = _jeton()

    commun = {"projectKey": args.projet, "branch": args.branche}
    issues = _pagine("/api/issues/search",
                     {"componentKeys": args.projet, "branch": args.branche,
                      "resolved": "false"}, "issues", jeton)
    # Les security hotspots vivent dans un endpoint SÉPARÉ : ils n'apparaissent jamais dans
    # `api/issues/search`. Les oublier donnerait une extraction « complète » sans sécurité.
    hotspots = _pagine("/api/hotspots/search",
                       {**commun, "status": "TO_REVIEW"}, "hotspots", jeton)

    brut = Path(f"{args.sortie}.json")
    brut.write_text(json.dumps({"issues": issues, "hotspots": hotspots},
                               ensure_ascii=False, indent=2), encoding="utf-8")

    par_fichier: dict[str, list[dict]] = defaultdict(list)
    for i in issues:
        par_fichier[_fichier(i.get("component", "?"))].append(i)
    regles = Counter(i.get("rule", "?") for i in issues)

    lignes: list[str] = [
        f"# Issues Sonar — {args.projet} ({args.branche})", "",
        f"{len(issues)} issue(s) ouverte(s), {len(hotspots)} hotspot(s) à relire.", "",
        "> Extraction brute. Chaque entrée demande une DÉCISION (corriger / justifier),",
        "> pas une correction automatique. Voir l'avertissement de `tools/sonar_issues.py`.",
        "", "## Volume par règle", "",
        "| Règle | Nombre |", "|---|---|",
    ]
    lignes += [f"| `{r}` | {n} |" for r, n in regles.most_common()]

    lignes += ["", "## Par fichier", ""]
    for fic in sorted(par_fichier):
        lignes.append(f"### `{fic}`")
        lignes.append("")
        for i in sorted(par_fichier[fic], key=lambda x: x.get("line") or 0):
            impacts = ", ".join(f"{im['softwareQuality']}:{im['severity']}"
                                for im in i.get("impacts", []))
            grav = impacts or i.get("severity", "?")
            lignes.append(f"- **L{i.get('line', '?')}** · `{i.get('rule')}` · {grav}"
                          f" · effort {i.get('effort', '?')}")
            lignes.append(f"  {i.get('message', '').strip()}")
        lignes.append("")

    if hotspots:
        lignes += ["## Security hotspots (à relire, pas à corriger d'office)", ""]
        for h in sorted(hotspots, key=lambda x: (_fichier(x.get("component", "")),
                                                 x.get("line") or 0)):
            lignes.append(
                f"- `{_fichier(h.get('component','?'))}:{h.get('line','?')}` · "
                f"`{h.get('ruleKey')}` · {h.get('vulnerabilityProbability')} · "
                f"{h.get('securityCategory')}")
            lignes.append(f"  {h.get('message','').strip()}")
        lignes.append("")

    md = Path(f"{args.sortie}.md")
    md.write_text("\n".join(lignes), encoding="utf-8")
    print(f"{len(issues)} issues + {len(hotspots)} hotspots -> {md} et {brut}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
