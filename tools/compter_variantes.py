#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Compte les variantes d'orthographe d'un même nom propre dans un tome manga traduit.

    python tools/compter_variantes.py "manga A" Vol.1
    python tools/compter_variantes.py "manga A" Vol.1 --brut   # avant forçage

Mesure le défaut que le lot 3 corrige : **une même chaîne source rend plusieurs
orthographes françaises**, parce que chaque planche est traduite en isolation, sans mémoire
de la romanisation retenue sur les planches précédentes. Mesuré sur *manga A* Vol.1 :
`カタフラクト` ressortait en Kataphrakt / Katafrakt / Kataphrakto / Cataphracte, et `三影`
— des kanji, pourtant strictement identiques d'une bulle à l'autre — en Mitsukage / Mikage
/ Miyage.

L'outil ne devine pas les familles de variantes : il les lit dans le glossaire de l'œuvre
(`nom` + `variantes` + `interdits` de chaque entrée `force: true`). Il répond donc
exactement à la question qui compte : « les formes que j'ai bannies ont-elles disparu ? ».
Sans glossaire, il retombe sur un mode exploratoire qui liste les groupes de mots
capitalisés proches — c'est ce mode qui a servi à établir la liste initiale.
"""
from __future__ import annotations

import collections
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config as core_config          # noqa: E402
from core import glossary                        # noqa: E402
from core.cli import charger_config, configurer_stdout   # noqa: E402
from core.glossary import ENTITY_CATS            # noqa: E402
from manga import terminology                    # noqa: E402

# Le lexique des têtes de phrase françaises et le comptage à frontières de mot vivaient ici.
# Ils servent maintenant AUSSI au pipeline (`manga/terminology.py` détecte la dérive sans
# appel LLM) : deux copies auraient divergé, et un instrument de mesure qui ne compte pas
# comme compte ce qu'il mesure ne vaut rien.
_COURANTS = terminology.MOTS_COURANTS
_compter = terminology.compter_occurrences


def _lire_tome(build_dir: Path, brut: bool = False):
    """(page, ocr, français) pour chaque page traitée.

    Le français vient de `qa.json`, qui enregistre le texte **réellement dessiné sur la
    planche** — donc APRÈS le forçage du glossaire. `traduction.json`, lui, garde
    délibérément la sortie brute du modèle (cf. `manga/terminology.py` : c'est ce qui permet
    de corriger une orthographe et de relancer `--from rendu` sans appel LLM). Mesurer le
    cache brut ne dirait donc rien de ce que le lecteur voit. `brut=True` le fait exprès, pour
    comparer avant/après."""
    for d in sorted((build_dir / ".checkpoints").glob("page_*")):
        qa, tr = d / "qa.json", d / "traduction.json"
        fr = None
        if not brut and qa.exists():
            try:
                bulles = json.loads(qa.read_text(encoding="utf-8")).get("bulles") or []
                fr = [b.get("traduction") or "" for b in bulles]
            except (json.JSONDecodeError, OSError, AttributeError):
                fr = None
        if fr is None:
            if not tr.exists():
                continue
            fr = json.loads(tr.read_text(encoding="utf-8"))
        oc = d / "ocr.json"
        yield (int(d.name.split("_")[1]),
               json.loads(oc.read_text(encoding="utf-8")) if oc.exists() else [], fr)


def _familles(glo: dict) -> list[tuple[str, list[str]]]:
    """(forme canonique, formes bannies) pour chaque entrée `force: true` du glossaire."""
    out = []
    for cat in ENTITY_CATS:
        for e in glo.get(cat) or []:
            nom = (e.get("nom") or "").strip()
            if not e.get("force") or not nom:
                continue
            bannies = [f.strip() for f in
                       (list(e.get("variantes") or []) + list(e.get("interdits") or []))
                       if f and f.strip().lower() != nom.lower()]
            out.append((nom, bannies))
    return out


def _rapport_derives(textes: list[str], glo: dict, pages) -> None:
    """Dérives que le glossaire ne connaît pas ENCORE — le pendant du rapport ci-dessus.

    « 0 forme bannie » est exact et trompeur : les `interdits` listent les fautes des runs
    précédents, et un run neuf en produit de nouvelles. Ce bloc montre ce que le pipeline
    écrirait, sans rien écrire — l'outil reste en lecture seule."""
    t1 = []
    for _page, ocr, trad in pages:
        t1 += terminology.derives_ancrees(glo, ocr, trad, page=_page)
    reste = terminology.derives_de_volume(glo, textes, deja={d.candidat for d in t1})
    print("\n--- Dérives NON encore bannies (T1 ancrée · T2 dominance · T3 lexicale) ---")
    for d in t1 + reste:
        preuve = (f"ancrée sur {d.source} p{d.page} b{d.bulle}" if d.niveau == "T1" else
                  f"{d.nom} ×{d.occurrences_nom} vs ×{d.occurrences_candidat}")
        print(f"  [{d.niveau}] {d.candidat:20s} → {d.nom:20s} ({preuve})")
    if not (t1 or reste):
        print("  (aucune)")
    pluriels = terminology.proposer_pluriels(glo, textes)
    if pluriels:
        print("\n--- Pluriels sans champ `pluriel:` (à déclarer, PAS à bannir) ---")
        for nom, pl, n in pluriels:
            print(f"  {nom:20s} → {pl} ×{n}")


def _rapport_glossaire(textes: list[str], glo: dict) -> int:
    familles = _familles(glo)
    if not familles:
        print("Aucune entrée `force: true` dans le glossaire — rien à vérifier.")
        return 0
    print(f"{len(familles)} entrée(s) `force: true` · {len(textes)} réplique(s) non vides\n")
    residuelles = 0
    for nom, bannies in sorted(familles):
        n_ok = _compter(textes, nom)
        restes = {f: _compter(textes, f) for f in bannies}
        restes = {f: n for f, n in restes.items() if n}
        etat = "✓" if not restes else "✗"
        detail = ("" if not restes else
                  "  ← RESTE : " + ", ".join(f"{f} ×{n}" for f, n in sorted(restes.items())))
        print(f"  {etat} {nom:24s} {n_ok:4d}{detail}")
        residuelles += sum(restes.values())
    print(f"\n{residuelles} occurrence(s) de forme bannie encore présente(s).")
    return residuelles


def _rapport_exploratoire(textes: list[str], pages) -> None:
    """Mode sans glossaire : groupes de mots capitalisés proches, et surtout — le signal le
    plus net — les suites de katakana rendues de plusieurs façons."""
    tout = "\n".join(textes)
    mots = collections.Counter(
        m for m in re.findall(r"\b[A-ZÀ-Ý][\wÀ-ÿ'’-]{3,}\b", tout)
        if m not in _COURANTS and not m[:2].endswith("'"))
    print("--- Groupes de mots capitalisés proches (candidats variantes) ---")
    vus: set[str] = set()
    for a in sorted(mots, key=lambda m: -mots[m]):
        if a in vus:
            continue
        proches = [b for b in mots if b != a
                   and difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.78]
        if proches:
            vus.update([a, *proches])
            print(f"  {a} ({mots[a]})  ~  "
                  + ", ".join(f"{b} ({mots[b]})" for b in sorted(proches, key=lambda x: -mots[x])))

    print("\n--- Même bulle source (katakana) → orthographes latines différentes ---")
    kata = re.compile(r"[゠-ヿ][゠-ヿー]{2,}")
    par_source: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for _page, ocr, trad in pages:
        for i, jp in enumerate(ocr):
            fr = trad[i] if i < len(trad) else ""
            if not fr:
                continue
            for k in kata.findall(jp or ""):
                for mot in re.findall(r"\b[A-Z][A-Za-z'’-]{3,}\b", fr):
                    if mot not in _COURANTS:
                        par_source[k][mot] += 1
    for k, c in sorted(par_source.items(), key=lambda kv: -sum(kv[1].values())):
        if len(c) >= 2 and sum(c.values()) >= 3:
            print(f"  {k:14s} → " + ", ".join(f"{m} ×{n}" for m, n in c.most_common(6)))


def main() -> int:
    # Cet outil affiche du JAPONAIS : sans UTF-8 sur stdout, une console Windows en cp1252
    # lève `UnicodeEncodeError` au premier terme source affiché, après la moitié du résultat.
    configurer_stdout()
    args = [a for a in sys.argv[1:] if a != "--brut"]
    brut = "--brut" in sys.argv
    if len(args) < 2:
        print(__doc__)
        return 2
    projet, tome = args[0], args[1]
    config = charger_config(args[2] if len(args) > 2 else "config.yaml")
    chemins = core_config.section(config, "manga", "chemins")
    build_dir = Path(chemins["build"]) / projet / tome / "manga"
    if not build_dir.exists():
        print(f"Rien à mesurer : {build_dir} n'existe pas.")
        return 1

    pages = list(_lire_tome(build_dir, brut=brut))
    textes = [t for _p, _o, tr in pages for t in tr if t and t.strip()]
    origine = ("sortie BRUTE du modèle (traduction.json)" if brut
               else "texte réellement dessiné (qa.json, après forçage)")
    print(f"{projet} / {tome} — {len(pages)} page(s) · source : {origine}\n")

    gpath = (Path(chemins["sources"]) / projet
             / chemins.get("glossaire_fichier", "glossaire.yaml"))
    glo = glossary.load(gpath)
    if glo:
        print(f"Glossaire : {gpath}")
        residuelles = _rapport_glossaire(textes, glo)
        _rapport_derives(textes, glo, pages)
        return 1 if residuelles else 0
    print(f"(pas de glossaire sous {gpath} — mode exploratoire)\n")
    _rapport_exploratoire(textes, pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
