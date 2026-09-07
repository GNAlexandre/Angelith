# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le tableau **drapeau × interface** — produit par introspection, jamais à l'œil.

## Pourquoi un script, et pas un relevé

Parce que le `PLAN-19` a déjà appris la leçon sur les couleurs littérales : « le relevé
initial en annonçait dix-huit dans cinq fichiers et en avait manqué trois. D'où le critère 1 :
un inventaire à la main ne suffit pas, il faut le test. » Le §1.1 du `PLAN-33` annonçait 23
`add_argument` dans `run_manga.py` ; ce script en compte 26 avec les trois que
`cli.ajouter_flags_veille` ajoute, et c'est exactement le genre d'écart qu'un relevé manuel
laisse passer.

Le script est donc livré **avec** son résultat, et `tests/test_inventaire_drapeaux.py`
échoue le jour où un drapeau neuf apparaît dans une CLI sans être classé.

## Pourquoi l'AST, et pas `argparse`

Les quatre CLI construisent leur `ArgumentParser` **dans `main()`**, après
`cli.configurer_stdout()` et une série d'imports lourds — `run_ocr.py` importe `scan/`,
`run_illustration.py` importe `illustration/gabarits`. Introspecter le parseur réel
demanderait d'exécuter `main()` jusqu'à `parse_args`, donc de payer ces imports et de risquer
un `SystemExit` sur une machine sans dépendances optionnelles.

Lire le source avec `ast` ne coûte rien, ne dépend d'aucune dépendance, et donne exactement ce
qu'on cherche : le nom des drapeaux tel qu'il est ÉCRIT. ⚠ La contrepartie est nommée : un
drapeau ajouté par une boucle ou par un helper que ce module ne connaît pas serait invisible.
Il y en a **deux** au 2026-09-06 — `cli.ajouter_flags_veille` et `cli.ajouter_flag_sans_llm` —
et ils sont traités explicitement, en relisant `core/cli.py` par le même chemin plutôt qu'en
recopiant leurs noms.

## Utilisation

```powershell
python tools/inventaire_drapeaux.py                 # le tableau, en Markdown
python tools/inventaire_drapeaux.py --resume        # les quatre nombres seulement
python tools/inventaire_drapeaux.py --manquants     # ce qui n'est classé nulle part
```
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

#: Les quatre CLI du dépôt, dans l'ordre d'ancienneté des briques.
CLIS: tuple[str, ...] = ("run.py", "run_manga.py", "run_ocr.py", "run_illustration.py")

#: Les helpers qui posent des drapeaux ailleurs qu'à la vue du fichier appelant.
#: `nom de fonction -> (fichier, fonction à relire)`. ⚠ Le jour où un second helper naît, il
#: doit atterrir ici : `tests/test_inventaire_drapeaux.py` vérifie qu'aucun appel non résolu
#: contenant « flags » ou « argument » ne traîne dans une des quatre CLI.
HELPERS: dict[str, tuple[str, str]] = {
    "ajouter_flags_veille": ("core/cli.py", "ajouter_flags_veille"),
    # ⚠ Le second, né au lot 39, et il est arrivé exactement comme ce module l'avait prévu :
    # `tests/test_inventaire_drapeaux.py` a refusé la livraison tant qu'il n'était pas déclaré
    # ici. C'est le garde-fou faisant son travail, pas une formalité.
    "ajouter_flag_sans_llm": ("core/cli.py", "ajouter_flag_sans_llm"),
}


@dataclass(frozen=True)
class Drapeau:
    """Un argument déclaré par une CLI, tel qu'il est écrit dans le source."""

    cli: str
    nom: str                    # "--force", ou "projet" pour un positionnel
    action: str = ""            # "store_true", "version", …
    aide: str = ""
    via: str = ""               # le helper qui l'a posé, vide sinon

    @property
    def positionnel(self) -> bool:
        return not self.nom.startswith("-")


def _texte(noeud) -> str:
    """La valeur d'un littéral chaîne, y compris concaténée — `"a" "b"` et `"a" + "b"`."""
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return noeud.value
    if isinstance(noeud, ast.BinOp) and isinstance(noeud.op, ast.Add):
        return _texte(noeud.left) + _texte(noeud.right)
    if isinstance(noeud, ast.JoinedStr):
        return "".join(_texte(v) for v in noeud.values)
    return ""


def _drapeaux_de_fonction(arbre: ast.AST, cli: str, via: str = "") -> list[Drapeau]:
    """Les `add_argument` d'un arbre, dans l'ordre du source."""
    sortie: list[Drapeau] = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        cible = noeud.func
        if not (isinstance(cible, ast.Attribute) and cible.attr == "add_argument"):
            continue
        noms = [_texte(a) for a in noeud.args]
        noms = [n for n in noms if n]
        if not noms:
            continue
        options = {k.arg: k.value for k in noeud.keywords if k.arg}
        action = _texte(options.get("action")) if "action" in options else ""
        aide = _texte(options.get("help")) if "help" in options else ""
        # Le nom RETENU est le plus long : `--dry-run` plutôt qu'un éventuel `-n`. C'est celui
        # que la documentation et les plans citent.
        sortie.append(Drapeau(cli, max(noms, key=len), action, aide.strip(), via))
    return sortie


def _fonction(chemin: Path, nom: str) -> ast.AST | None:
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.FunctionDef) and noeud.name == nom:
            return noeud
    return None


def _helpers_appeles(arbre: ast.AST) -> list[str]:
    """Les helpers de `HELPERS` réellement appelés dans cet arbre."""
    vus = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            cible = noeud.func
            nom = cible.attr if isinstance(cible, ast.Attribute) else getattr(cible, "id", "")
            if nom in HELPERS and nom not in vus:
                vus.append(nom)
    return vus


def drapeaux(racine: Path = RACINE) -> tuple[Drapeau, ...]:
    """Tous les arguments des quatre CLI, helpers résolus, dans l'ordre du source."""
    sortie: list[Drapeau] = []
    for cli in CLIS:
        chemin = racine / cli
        principal = _fonction(chemin, "main")
        if principal is None:                    # pragma: no cover — CLI sans main()
            continue
        sortie.extend(_drapeaux_de_fonction(principal, cli))
        for helper in _helpers_appeles(principal):
            fichier, fonction = HELPERS[helper]
            arbre = _fonction(racine / fichier, fonction)
            if arbre is not None:
                sortie.extend(_drapeaux_de_fonction(arbre, cli, via=f"{fichier}:{helper}"))
    return tuple(sortie)


# --------------------------------------------------------------------------- #
#  Le croisement avec l'interface
# --------------------------------------------------------------------------- #

#: Les trois verdicts possibles pour un drapeau.
FORMULAIRE = "formulaire"      # une case du générateur, déclarée dans gui/parametres.py
AILLEURS = "ailleurs"          # un bouton, un menu, le sélecteur de cible
NON_EXPOSE = "non exposé"      # délibérément absent, avec son motif
ORPHELIN = "NON CLASSÉ"        # ⚠ ce que le test refuse


@dataclass(frozen=True)
class Verdict:
    drapeau: Drapeau
    categorie: str
    ou: str = ""                # le panneau, l'endroit, ou le motif


def croiser(inventaire=None) -> tuple[Verdict, ...]:
    """Chaque drapeau, avec son verdict. **La seule fonction que le test appelle.**"""
    from gui import parametres as par

    inventaire = inventaire if inventaire is not None else drapeaux()
    # `{drapeau: [panneaux]}` — un même drapeau peut servir plusieurs panneaux (`--force`).
    par_drapeau: dict[str, list[str]] = {}
    for parametre in par.parametres():
        if parametre.drapeau:
            par_drapeau.setdefault(parametre.drapeau, []).extend(parametre.panneaux)

    #: Quels panneaux valent pour quelle CLI. Un `--force` déclaré pour le panneau « manga »
    #: ne prouve rien sur `run.py` : sans cette table, un drapeau du light novel serait
    #: déclaré exposé parce qu'un homonyme l'est côté manga.
    couverture = {
        "run.py": {par.LIGHT_NOVEL},
        "run_manga.py": {par.MANGA, par.WEBTOON},
        "run_ocr.py": set(),
        "run_illustration.py": {par.ILLUSTRATIONS},
    }

    verdicts: list[Verdict] = []
    for drapeau in inventaire:
        cle = (drapeau.cli, drapeau.nom)
        panneaux = sorted(set(par_drapeau.get(drapeau.nom, ())) & couverture[drapeau.cli])
        if panneaux:
            verdicts.append(Verdict(drapeau, FORMULAIRE, ", ".join(panneaux)))
        elif cle in par.AILLEURS:
            verdicts.append(Verdict(drapeau, AILLEURS, par.AILLEURS[cle]))
        elif cle in par.NON_EXPOSES:
            verdicts.append(Verdict(drapeau, NON_EXPOSE, par.NON_EXPOSES[cle]))
        else:
            verdicts.append(Verdict(drapeau, ORPHELIN))
    return tuple(verdicts)


def declarations_orphelines() -> tuple[tuple[str, str], ...]:
    """Les entrées de `AILLEURS` / `NON_EXPOSES` qui ne correspondent à AUCUN drapeau réel.

    ⚠ C'est le pendant du test principal, et il compte autant : un motif qui survit au drapeau
    qu'il justifiait est un faux avertissement, au sens de la règle §5 bis du contexte agent.
    Il vieillit sans le dire, et il cesse d'être lu."""
    from gui import parametres as par

    reels = {(d.cli, d.nom) for d in drapeaux()}
    declares = set(par.AILLEURS) | set(par.NON_EXPOSES)
    return tuple(sorted(declares - reels))


# --------------------------------------------------------------------------- #
#  Rendu
# --------------------------------------------------------------------------- #

def resume(verdicts=None) -> dict[str, int]:
    verdicts = verdicts if verdicts is not None else croiser()
    compte = {FORMULAIRE: 0, AILLEURS: 0, NON_EXPOSE: 0, ORPHELIN: 0}
    for verdict in verdicts:
        compte[verdict.categorie] += 1
    compte["total"] = len(verdicts)
    return compte


def markdown(verdicts=None) -> str:
    verdicts = verdicts if verdicts is not None else croiser()
    lignes = ["| CLI | Argument | Verdict | Où / motif |", "|---|---|---|---|"]
    for verdict in verdicts:
        motif = verdict.ou.replace("\n", " ").replace("|", "\\|")
        if len(motif) > 220:
            motif = motif[:217] + "…"
        via = f" *(via {verdict.drapeau.via})*" if verdict.drapeau.via else ""
        lignes.append(f"| `{verdict.drapeau.cli}` | `{verdict.drapeau.nom}`{via} "
                      f"| {verdict.categorie} | {motif} |")
    compte = resume(verdicts)
    lignes += [
        "",
        f"**{compte['total']} arguments au total** — {compte[FORMULAIRE]} exposés par le "
        f"formulaire déclaré, {compte[AILLEURS]} exposés ailleurs dans l'interface, "
        f"{compte[NON_EXPOSE]} délibérément non exposés avec motif, "
        f"{compte[ORPHELIN]} non classés.",
    ]
    par_cli: dict[str, int] = {}
    for verdict in verdicts:
        par_cli[verdict.drapeau.cli] = par_cli.get(verdict.drapeau.cli, 0) + 1
    lignes.append("")
    lignes.append("Par CLI : " + ", ".join(f"`{c}` {n}" for c, n in par_cli.items()) + ".")
    return "\n".join(lignes)


def main() -> int:
    # ⚠ Le tableau porte des « ⚠ » et des guillemets français : sans ça, une console Windows
    # en cp1252 lève `UnicodeEncodeError` sur la première ligne de motif. C'est exactement le
    # défaut que le correctif 2.25.1 a corrigé sur deux autres outils du dossier.
    from core import cli

    cli.configurer_stdout()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--resume", action="store_true", help="les quatre nombres seulement")
    ap.add_argument("--manquants", action="store_true",
                    help="les drapeaux non classés, et les motifs devenus orphelins")
    args = ap.parse_args()

    verdicts = croiser()
    if args.resume:
        compte = resume(verdicts)
        for cle in (FORMULAIRE, AILLEURS, NON_EXPOSE, ORPHELIN, "total"):
            print(f"{cle:>14} : {compte[cle]}")
        return 1 if compte[ORPHELIN] else 0
    if args.manquants:
        orphelins = [v for v in verdicts if v.categorie == ORPHELIN]
        for verdict in orphelins:
            print(f"NON CLASSÉ  {verdict.drapeau.cli} {verdict.drapeau.nom}")
        for cli, nom in declarations_orphelines():
            print(f"MOTIF MORT  {cli} {nom}")
        return 1 if (orphelins or declarations_orphelines()) else 0
    print(markdown(verdicts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
