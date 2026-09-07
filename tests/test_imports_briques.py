# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le **graphe d'imports internes** du dépôt : sans cycle, et désormais protégé.

⚠ Aucun test du graphe d'imports n'existait dans `tests/` avant le lot 24. La propriété
« sans cycle » avait été constatée à la main lors d'un audit et jamais gardée — alors qu'elle
est un argument de dossier de financement, et qu'un import ajouté dans le mauvais sens ne se
voit dans aucune revue de diff.

Ce fichier vaut pour les **cinq** paquets, pas seulement pour la nouvelle brique. C'est un
garde-fou gratuit : il ne mesure rien, il ne charge rien, il lit des `import` avec `ast`.

## Ce que le lot a trouvé en l'écrivant, et qui contredit le plan

Le `PLAN-24` L24.1 décrit le graphe ainsi : « `core` n'importe rien d'interne, `pipeline`→core,
`manga`→core, `scan`→core+manga, `gui`→manga+core ». **Deux de ces cinq lignes sont fausses**,
et le relevé du 2026-08-29 le montre :

| Paquet | Ce que le plan annonce | Ce que le dépôt fait |
|---|---|---|
| `core` | rien d'interne | ✅ rien d'interne |
| `pipeline` | → core | ✅ core |
| `manga` | → core | ❌ core **et pipeline** (`glossaire_manga.py` l. 106, `orchestrator_manga.py` l. 1396 : `optimize_glossary_file`) |
| `scan` | → core + manga | ✅ core + manga |
| `gui` | → manga + core | ❌ core, manga **et pipeline** (six sites, tous en import tardif) |

Les deux arêtes manquantes sont réelles, anciennes, et **ne créent aucun cycle** : `pipeline`
n'importe que `core`. Le plan décrivait le graphe de mémoire ; la table ci-dessous est la
mesure. C'est elle qui fait foi, et l'écart est publié dans
`docs/mesures/socle-generatif-2026-08-29.md` plutôt que corrigé en silence dans le plan.
"""
import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Les paquets internes du dépôt. `tools/` et `tests/` n'en sont pas : ce sont des
#: consommateurs, ils ont le droit de tout importer.
PAQUETS: tuple[str, ...] = ("core", "pipeline", "manga", "scan", "gui", "illustration")

#: Le graphe AUTORISÉ, relevé le 2026-08-29 sur l'arbre réel. Une arête absente d'ici est un
#: échec ; une arête présente ici mais disparue du code n'en est pas un — supprimer une
#: dépendance est toujours un progrès, et faire échouer le test pour ça découragerait le
#: nettoyage.
GRAPHE: dict[str, frozenset[str]] = {
    "core": frozenset(),
    "pipeline": frozenset({"core"}),
    "manga": frozenset({"core", "pipeline"}),
    "scan": frozenset({"core", "manga"}),
    # ⚠ `illustration` est entré ici au lot 27, et **uniquement pour `gui/atelier.py`**, qui
    # est l'onglet d'atelier. Voir `test_illustration_n_est_importee_que_tardivement` :
    # l'arête existe, mais elle n'est portée par aucun import de niveau module, donc le
    # paquet reste supprimable sans casser le démarrage de la fenêtre.
    "gui": frozenset({"core", "manga", "pipeline", "illustration"}),
    # ⚠ `illustration` → `core`, et RIEN d'autre. C'est la seule ligne de cette table qui
    # soit une exigence de plan plutôt qu'un constat : le `PLAN-24` L24.1 l'impose, et si une
    # fonction de `manga/` devient nécessaire, elle remonte dans `core/`.
    "illustration": frozenset({"core"}),
}

#: Les seuls fichiers autorisés à importer `illustration`, et seulement TARDIVEMENT.
#: Le `PLAN-27` demande un onglet d'atelier ; il n'y a pas de façon d'en écrire un sans
#: cette arête. Ce qui est gardé, c'est la propriété qui comptait — cf. §« la feuille » du
#: docstring de `gui/atelier.py`.
IMPORTATEURS_TARDIFS: frozenset[str] = frozenset({"gui/atelier.py"})


def aretes(paquet: str) -> set[str]:
    """Les paquets internes que `paquet` importe, imports tardifs compris.

    Les imports RELATIFS (`from . import power`) sont ignorés : ils ne peuvent pas sortir du
    paquet, donc ils ne portent aucune arête."""
    sortie: set[str] = set()
    for source in sorted((RACINE / paquet).rglob("*.py")):
        arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                noms = [alias.name for alias in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                if noeud.level:
                    continue
                noms = [noeud.module or ""]
            else:
                continue
            for nom in noms:
                racine = nom.split(".")[0]
                if racine in PAQUETS and racine != paquet:
                    sortie.add(racine)
    return sortie


@pytest.mark.parametrize("paquet", PAQUETS)
def test_chaque_paquet_respecte_ses_aretes_declarees(paquet):
    reelles = aretes(paquet)
    interdites = reelles - GRAPHE[paquet]
    assert not interdites, (
        f"« {paquet} » importe {sorted(interdites)}, qui n'est pas dans son graphe autorisé "
        f"{sorted(GRAPHE[paquet])}.\n"
        f"  Si c'est voulu, il faut le justifier et mettre à jour GRAPHE dans ce fichier — "
        f"pas seulement faire passer le test. Une arête nouvelle change ce qu'on peut dire "
        f"du dépôt dans un dossier de financement.")


def test_core_n_importe_aucune_brique():
    """La ligne dont tout le reste dépend : `core` est le socle, il ne remonte jamais."""
    assert aretes("core") == set()


def test_le_graphe_est_sans_cycle():
    """La propriété que l'audit avait constatée à la main. Parcours en profondeur, sur le
    graphe RÉEL et non sur la table déclarée : c'est le code qui est vérifié."""
    reel = {p: aretes(p) for p in PAQUETS}
    vus: set[str] = set()
    pile: list[str] = []

    def descendre(paquet: str) -> None:
        if paquet in pile:
            raise AssertionError(f"cycle d'imports : {' → '.join(pile + [paquet])}")
        if paquet in vus:
            return
        pile.append(paquet)
        for voisin in sorted(reel[paquet]):
            descendre(voisin)
        pile.pop()
        vus.add(paquet)

    for paquet in PAQUETS:
        descendre(paquet)


def test_illustration_reste_une_feuille_hors_de_l_interface():
    """Personne n'importe `illustration` — **sauf `gui/`, et seulement l'onglet d'atelier**.

    ⚠ **Cette propriété a été AFFAIBLIE au lot 27, et l'écart est écrit plutôt que masqué.**
    Jusque-là le test portait sur les cinq autres paquets sans exception : « c'est ce qui rend
    la brique supprimable sans rien casser, et c'est la moitié de ce que *désarmée par
    défaut* veut dire ». Le `PLAN-27` L27.1 demande « un onglet, à côté de Planches et de
    Runs » : il n'existe aucune façon d'écrire cet onglet sans que `gui/` connaisse la brique.

    Deux choses restent vraies, et ce sont celles qui portaient la propriété :

    1. **`pipeline/`, `manga/`, `scan/` et `core/` ne l'importent toujours pas** — le light
       novel rend un tome sans elle, et l'insertion du lot 27 passe par `core/insertion.py`
       précisément pour ça ;
    2. **aucun import de niveau module**, donc la fenêtre démarre sans le paquet — c'est
       `test_l_interface_n_importe_illustration_que_tardivement` ci-dessous, doublé d'un test
       d'exécution dans `tests/test_gui_atelier.py` qui rend `illustration` inimportable puis
       construit la fenêtre entière."""
    for paquet in PAQUETS:
        if paquet in ("illustration", "gui"):
            continue
        assert "illustration" not in aretes(paquet), (
            f"« {paquet} » importe la brique d'illustration. Seul `gui/` en a le droit, et "
            f"seulement tardivement : un utilisateur qui supprime le dossier doit encore "
            f"pouvoir traduire un tome.")


def test_l_interface_n_importe_illustration_que_tardivement():
    """Dans `gui/`, aucun `import illustration` **au niveau module**, et dans deux fichiers
    seulement.

    Un import de niveau module ferait échouer le démarrage de la fenêtre sur une installation
    sans la brique. Les imports tardifs, eux, échouent au moment où l'on ouvre l'onglet — et
    `gui/atelier.py:brique_absente` transforme cet échec en état vide qui dit pourquoi."""
    fautifs: list[str] = []
    for source in sorted((RACINE / "gui").rglob("*.py")):
        relatif = source.relative_to(RACINE).as_posix()
        arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.ImportFrom):
                noms = [] if noeud.level else [noeud.module or ""]
            elif isinstance(noeud, ast.Import):
                noms = [a.name for a in noeud.names]
            else:
                continue
            if not any(n.split(".")[0] == "illustration" for n in noms):
                continue
            if relatif not in IMPORTATEURS_TARDIFS:
                fautifs.append(f"{relatif}:{noeud.lineno} — fichier non déclaré dans "
                               f"IMPORTATEURS_TARDIFS")
            elif noeud.col_offset == 0:
                fautifs.append(f"{relatif}:{noeud.lineno} — import de NIVEAU MODULE")
    assert fautifs == [], (
        "la brique d'illustration doit rester importable tardivement seulement :\n  "
        + "\n  ".join(fautifs))


def test_la_table_ne_declare_que_des_paquets_existants():
    """Une table qui dérive produit de faux verdicts — même défaut que `CLES_CONNUES`."""
    assert set(GRAPHE) == set(PAQUETS)
    for paquet, cibles in GRAPHE.items():
        assert (RACINE / paquet).is_dir(), paquet
        assert cibles <= set(PAQUETS), (paquet, cibles)
