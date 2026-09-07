#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que l'utilisateur VOIT quand chaque dépendance manque — `PLAN-36` étape 0.1.

    python tools/inventaire_pannes.py
    python tools/inventaire_pannes.py --markdown > docs/mesures/pannes-<date>.md
    python tools/inventaire_pannes.py --cas pandoc --cas poids

## Pourquoi cet outil, et pas un tableau écrit à la main

Le `PLAN-36` demande de **masquer chaque dépendance une par une** et de relever ce que
l'utilisateur voit. Un tableau recopié à la main vieillit en silence — c'est exactement le
défaut que la règle §5 bis du contexte agent nomme (« un commentaire qui vieillit sans le dire
est un faux avertissement, et un faux avertissement cesse d'être lu »). Un outil qui rejoue le
masquage rend le tableau reproductible, et sa date est celle du jour où on le lance.

## Ce que le masquage fait, et ce qu'il ne fait pas

Chaque cas remplace **une** chose : un exécutable disparaît du `PATH` (`shutil.which` rend
`None`), un chemin de poids pointe ailleurs, une URL de LLM pointe sur un port fermé. Aucun
paquet n'est désinstallé, aucun fichier du dépôt n'est déplacé.

⚠ **Ce que la mesure ne dit pas** : elle relève le message du DIAGNOSTIC, pas celui qu'on
obtient au milieu d'un run de trois heures. Les deux diffèrent, et le cas de `manga-ocr` hors
réseau — le pire de tous — ne se relève pas ici : il demande de vider le cache Hugging Face,
ce qu'un outil ne doit pas faire sur la machine de qui le lance. Sa mesure est faite à la main
et publiée dans `docs/mesures/premier-lancement-2026-09-06.md`.
"""
from __future__ import annotations

import argparse
import builtins
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core import diagnostic as diag                    # noqa: E402

#: Un port qu'aucun serveur local n'écoute. Masquer « Ollama arrêté » sans arrêter l'Ollama de
#: qui lance l'outil : c'est la seule façon honnête de mesurer ce cas sur une machine de
#: travail.
PORT_FERME = "http://127.0.0.1:59999/v1"


def _sans_outils(noms: set[str]):
    """Un `shutil.which` qui ne trouve plus `noms`. Rendu, pas posé : c'est l'appelant qui
    décide de la portée du masquage."""
    vrai = shutil.which

    def _which(commande, *args, **kwargs):
        return None if Path(commande).stem.lower() in noms else vrai(commande, *args, **kwargs)

    return _which


def _config_masquee(config: dict, cas: str, tmp: Path) -> dict:
    """La configuration du cas `cas`. Une copie : rien n'est modifié en place."""
    copie = dict(config)
    if cas == "ollama":
        copie["llm"] = dict(config.get("llm") or {}, base_url=PORT_FERME)
    elif cas in ("poids", "police"):
        mcfg = dict(config.get("manga") or {})
        if cas == "poids":
            mcfg["detection"] = dict(mcfg.get("detection") or {},
                                     model_path=str(tmp / "poids_absent.onnx"),
                                     telechargement_auto=False)
        else:
            mcfg["typeset"] = dict(mcfg.get("typeset") or {},
                                   font_path=str(tmp / "police_absente.ttf"))
        copie["manga"] = mcfg
    return copie


#: Les cas relevables sans toucher à l'installation. Chacun dit ce qu'il masque et quelle
#: brique il interroge.
CAS: dict[str, tuple[str, str]] = {
    "ollama": ("serveur LLM arrêté (base_url sur un port fermé)", "ln"),
    "pandoc": ("Pandoc retiré du PATH", "ln"),
    "moteur_pdf": ("moteur PDF retiré du PATH et weasyprint masqué", "ln"),
    "poids": ("poids ONNX de détection absents, téléchargement refusé", "manga"),
    "police": ("manga.typeset.font_path sur un fichier absent", "manga"),
    "unrar": ("unrar / unar / bsdtar retirés du PATH", "manga"),
}


def relever(config: dict, cas: str, tmp: Path) -> list[diag.Verdict]:
    """Les verdicts obtenus avec le cas `cas` masqué. **Sans réseau, sans téléchargement.**"""
    from manga import doctor as doctor_manga
    from pipeline import doctor as doctor_ln

    _, brique = CAS[cas]
    copie = _config_masquee(config, cas, tmp)
    if cas == "unrar":
        # Ce cas ne passe par aucun doctor : c'est le dépôt guidé qui le porte, parce que la
        # question se pose AVANT d'importer une archive, pas pendant un run.
        from gui.depot_guide import outil_rar
        vrai = shutil.which
        shutil.which = _sans_outils({"unrar", "unar", "bsdtar"})
        try:
            etat = outil_rar()
        finally:
            shutil.which = vrai
        gravite = diag.CONFORME if etat.disponible else diag.DEGRADE
        return [diag.Verdict("unrar", diag.MANGA, gravite, constat=etat.message,
                             consequence="les archives .cbr ne peuvent pas être importées ; "
                                         "le .cbz, lui, ne demande rien.",
                             geste="https://www.rarlab.com/rar_add.htm — ou convertis "
                                   "l'archive en .cbz.")]

    masques = {"pandoc"} if cas == "pandoc" else set()
    if cas == "moteur_pdf":
        masques = {"weasyprint", "xelatex", "wkhtmltopdf", "prince"}
    vrai = shutil.which
    if masques:
        shutil.which = _sans_outils(masques)
    # ⚠ Masquer le PATH ne suffit pas pour weasyprint : il est cherché par un `import`, pas
    # par `which`. Sans ce second masquage, le cas « moteur PDF absent » ne relèverait rien
    # sur une machine où weasyprint est installé — et le tableau annoncerait, à tort, que ce
    # cas ne produit aucun message.
    vrai_import = builtins.__import__

    def _import_masque(nom, *a, **kw):
        if cas == "moteur_pdf" and nom == "weasyprint":
            raise ImportError("weasyprint masqué par tools/inventaire_pannes.py")
        return vrai_import(nom, *a, **kw)

    builtins.__import__ = _import_masque
    try:
        if brique == "manga":
            sections = doctor_manga.sections(copie, ecrire=None, reseau=(cas == "ollama"),
                                             telechargement=False)
        else:
            sections = doctor_ln.sections(copie, ecrire=None, reseau=(cas == "ollama"))
    finally:
        shutil.which = vrai
        builtins.__import__ = vrai_import
    return [v for v in diag.verdicts(sections) if v.gravite != diag.CONFORME]


def _ligne_markdown(cas: str, verdicts: list[diag.Verdict]) -> str:
    quoi, _ = CAS[cas]
    if not verdicts:
        return f"| `{cas}` | {quoi} | *(rien relevé — la dépendance est présente ici)* | — | — |"
    lignes = []
    for verdict in verdicts:
        lignes.append(
            f"| `{verdict.identifiant}` | {quoi} | {verdict.gravite} — {verdict.constat} "
            f"| {verdict.consequence or '—'} | {verdict.geste or '—'} |")
    return "\n".join(lignes)


def main() -> int:
    import tempfile

    from core import cli

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--cas", action="append", choices=sorted(CAS),
                    help="ne relever que ce(s) cas (défaut : tous)")
    ap.add_argument("--markdown", action="store_true",
                    help="sortie en tableau Markdown, à coller dans docs/mesures/")
    args = ap.parse_args()
    cli.configurer_stdout()

    config = cli.charger_config(args.config)
    cas = args.cas or sorted(CAS)
    with tempfile.TemporaryDirectory(prefix="angelith-pannes-") as tmp:
        releves = {nom: relever(config, nom, Path(tmp)) for nom in cas}

    if args.markdown:
        print("| Point | Dépendance masquée | Ce que le diagnostic dit | Conséquence | Geste |")
        print("|---|---|---|---|---|")
        for nom in cas:
            print(_ligne_markdown(nom, releves[nom]))
        print()
        print("⚠ Relevé par `python tools/inventaire_pannes.py --markdown`. Le cas "
              "« `manga-ocr` sans réseau au milieu d'un run » n'y figure pas : il demande de "
              "vider le cache Hugging Face, ce qu'un outil ne doit pas faire sur la machine "
              "de qui le lance. Sa mesure est à la main.")
        return 0

    for nom in cas:
        quoi, _ = CAS[nom]
        print(f"\n═══ {nom} — {quoi} ═══")
        if not releves[nom]:
            print("  (rien relevé : la dépendance est présente sur cette machine)")
        for verdict in releves[nom]:
            print(f"  {verdict.symbole} [{verdict.gravite}] {verdict.constat}")
            if verdict.consequence:
                print(f"      conséquence : {verdict.consequence}")
            if verdict.geste:
                print(f"      geste       : {verdict.geste}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
