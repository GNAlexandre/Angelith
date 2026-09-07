# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le point d'entrée de l'interface — et les deux vérifications que la CI fait sur le gel.

## Pourquoi ce module existe, alors que `gui.py` existait déjà

Parce qu'un point d'entrée de paquet est un `module:fonction`, et que **`gui.py` n'est pas
importable** : le dépôt porte à la fois un module `gui.py` et un paquet `gui/`, et Python
résout le paquet. `[project.gui-scripts] angelith-gui = "gui.py:main"` ne s'écrit donc pas.

`gui.py` reste le script qu'on lance à la main (`python gui.py`) — sa docstring de 30 lignes
est de la documentation d'usage, elle ne déménage pas — et il délègue ici. Le corps de `main`
est **déplacé sans être réécrit** : mêmes drapeaux, même ordre, mêmes messages.

## Les deux drapeaux neufs, et ils existent pour la CI — `PLAN-37` L37.7

Un artefact non testé est un artefact qu'on livre cassé une fois sur trois, et le gel a trois
pannes classiques : la version perdue, un chemin relatif à `__file__`, un module Qt élagué de
trop. `--version` attrape la première ; ces deux drapeaux attrapent les deux autres.

- **`--diagnostic-json`** rend les verdicts structurés du `PLAN-36` sur la sortie standard,
  **sans réseau et sans Qt**. Sur une machine nue, la liste attendue est connue : aucun poids,
  pas d'Ollama, pas de Pandoc. Un exécutable qui sait dire ce qui lui manque a résolu ses
  chemins ; un exécutable dont les chemins sont faux lève avant d'écrire une accolade ;
- **`--verifier-demarrage`** ouvre la fenêtre sous `QT_QPA_PLATFORM=offscreen`, vérifie qu'elle
  s'ouvre **sur l'accueil et sans tome** (critère 2 du `PLAN-31`, vérifié une seconde fois sur
  le gel), puis la ferme. Il rend aussi le temps jusqu'au premier affichage, qui est la
  quatrième colonne du tableau de poids de l'étape 0.1.

⚠ **Aucun des deux n'est un mode d'usage.** Ils écrivent une ligne et sortent avec un code ;
ils ne sont pas dans l'aide d'un utilisateur qui veut traduire un tome, et ils ne touchent à
rien.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from core import cli

# ⚠ **À l'IMPORT, pas dans `main`** — c'est la place qu'occupait cet appel dans `gui.py` avant
# le déménagement du lot 37, et l'oubli d'une ligne s'est vu tout de suite : sur le binaire
# gelé, `--diagnostic-json` est mort sur un `UnicodeEncodeError` de cp1252 au premier « ⚠ » du
# JSON (2026-09-06). Une console Windows en cp1252 ne sait écrire ni les guillemets français,
# ni les flèches, ni les titres japonais — c'est-à-dire l'essentiel de ce que ce dépôt imprime.
cli.configurer_stdout()


def construire_parseur() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="angelith-gui",
        description="Interface graphique de Angelith (runs + édition des planches manga).")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--version", action="version", version=version_affichee())
    # ⚠ `help=argparse.SUPPRESS` sur les deux : ce sont des sondes de livraison, pas des modes
    # d'usage. Les afficher dans `--help` inviterait à s'en servir pour diagnostiquer, alors
    # que le geste documenté est « run.py --check » ou la page Diagnostic.
    # ⚠ Un FICHIER optionnel, et ce n'est pas un raffinement. Mesuré le 2026-09-06 sur le gel
    # du jeu C : `transformers` écrit un avertissement sur la sortie standard **avant** que
    # quoi que ce soit d'autre ne s'imprime (« ViTImageProcessor requires torchvision »), et le
    # JSON n'est donc plus analysable. Un tiers qui parle sur stdout est un fait, pas un défaut
    # à corriger chez lui : la sortie machine s'écrit ailleurs.
    ap.add_argument("--diagnostic-json", nargs="?", const="-", default=None,
                    metavar="FICHIER", help=argparse.SUPPRESS)
    ap.add_argument("--verifier-demarrage", action="store_true", help=argparse.SUPPRESS)
    return ap


def version_affichee() -> str:
    from core.version import ETAT_BRIQUES, __version__
    return f"Angelith {__version__} (brique manga : {ETAT_BRIQUES['manga']})"


def main(argv: list[str] | None = None) -> None:
    args = construire_parseur().parse_args(argv)

    if args.diagnostic_json is not None:
        raise SystemExit(diagnostic_json(args.config, sortie=args.diagnostic_json))

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        raise SystemExit(
            "L'interface graphique demande PySide6, qui n'est pas installé.\n"
            "  → pip install -r requirements-gui.txt\n"
            "  (les CLI `run.py` et `run_manga.py` fonctionnent sans.)") from None

    config = cli.charger_config(args.config)
    if "manga" not in config:
        raise SystemExit(f"Aucune section « manga: » dans {args.config} — l'éditeur de "
                         f"planches n'aurait rien à ouvrir.")

    from gui import icones, reglages, theme
    from gui.fenetre import Fenetre

    depart = time.perf_counter()
    app = QApplication(sys.argv)
    app.setApplicationName("Angelith")
    # ⚠ Le thème se pose AVANT la première fenêtre. `QApplication.setStyle` reconstruit le
    # style de tous les widgets existants ; le poser après aurait le même effet visuel mais
    # ferait passer l'utilisateur par une fenêtre non stylée, le temps d'un rafraîchissement.
    #
    # Le mode vient du fichier de réglages de l'interface, pas de `config.yaml` : c'est une
    # préférence d'installation, pas un réglage de pipeline — et `config.yaml` n'est jamais
    # réécrit.
    theme.appliquer(app, reglages.lire().get("theme") or theme.AUTO)
    # Une seule icône, l'identité du logiciel. Sans elle, l'application portait l'icône Qt par
    # défaut dans la barre des tâches.
    app.setWindowIcon(icones.logo())
    fenetre = Fenetre(config, args.config)
    fenetre.show()

    if args.verifier_demarrage:
        raise SystemExit(verifier_demarrage(app, fenetre, depart))
    sys.exit(app.exec())


# --------------------------------------------------------------------------- #
#  Les deux sondes de livraison
# --------------------------------------------------------------------------- #

def diagnostic_json(chemin_config: str, *, sortie: str = "-") -> int:
    """Écrit les verdicts structurés — dans `sortie`, ou sur stdout si `sortie` vaut `"-"`.

    Rend le code de sortie.

    ⚠ `reseau=False` et `telechargement=False`. Un job de CI ne doit ni attendre douze
    secondes le délai d'un Ollama absent, ni récupérer 104 Mo de poids pour répondre à une
    question de chemins. La liste attendue sur une machine nue est celle-là, et c'est
    précisément parce qu'elle est connue qu'elle sert de test.

    ⚠ **Le code de sortie est 0 même avec des bloquants.** Sur une machine nue, des bloquants
    sont le résultat ATTENDU : Ollama n'est pas là, ni Pandoc, ni les poids. Sortir en erreur
    ferait échouer la CI sur un exécutable parfaitement sain. Ce qui doit échouer, c'est un
    diagnostic qui ne se collecte pas — et celui-là lève."""
    from core import diagnostic as diag
    from core import installation

    config = cli.charger_config(chemin_config)
    from manga import doctor as doctor_manga
    from pipeline import doctor as doctor_ln

    sections = [*doctor_ln.sections(config, ecrire=None, reseau=False),
                *doctor_manga.sections(config, ecrire=None, reseau=False,
                                       telechargement=False)]
    # ⚠ En gel seulement, et seulement s'il y a quelque chose à dire (`PLAN-37` L37.4, piège 2).
    installation_ = diag.section_installation()
    if installation_ is not None:
        sections.append(installation_)
    charge = {
        "version": version_affichee(),
        "gele": installation.gele(),
        "racine_livree": str(installation.racine_livree()),
        "config": str(installation.resoudre_config(chemin_config)),
        "resume": diag.resume(sections),
        "verdicts": [
            {"identifiant": v.identifiant, "brique": v.brique, "gravite": v.gravite,
             "constat": v.constat, "consequence": v.consequence, "geste": v.geste,
             "reparable": v.reparable}
            for v in diag.verdicts(sections)],
    }
    texte = json.dumps(charge, ensure_ascii=False, indent=2)
    if sortie and sortie != "-":
        Path(sortie).write_text(texte + "\n", encoding="utf-8")
    else:
        print(texte)
    return 0


def verifier_demarrage(app, fenetre, depart: float) -> int:
    """Vérifie qu'on s'est ouvert sur l'accueil, sans tome, puis ferme. Rend le code de sortie.

    Trois assertions, et chacune correspond à une panne réelle :

    1. **la destination est l'accueil** — le `PLAN-31` critère 2. Un gel qui rouvrirait le
       dernier tome au démarrage aurait perdu la propriété que le lot 31 a payée ;
    2. **aucun `Tome` ni `Services` n'existe** — la même propriété, vue du côté du coût : un
       tome ouvert, c'est un glossaire lu et des aperçus composés ;
    3. **la fenêtre est visible** — trivial dans le dépôt, pas dans un gel : un module Qt élagué
       de trop fait échouer la création du widget, pas l'import.
    """
    from gui import destinations as dst

    ecoule = time.perf_counter() - depart
    app.processEvents()
    echecs = []
    if fenetre.destination() != dst.ACCUEIL:
        echecs.append(f"destination = {fenetre.destination()!r}, attendu {dst.ACCUEIL!r}")
    if getattr(fenetre, "tome", None) is not None:
        echecs.append("un Tome est ouvert alors que personne ne l'a demandé")
    if getattr(fenetre, "services", None) is not None:
        echecs.append("un Services est construit alors que personne ne l'a demandé")
    if not fenetre.isVisible():
        echecs.append("la fenêtre n'est pas visible après show()")

    panneaux = sorted(fenetre.panneaux_construits()) if hasattr(
        fenetre, "panneaux_construits") else []
    print(json.dumps({"ok": not echecs, "destination": fenetre.destination(),
                      "panneaux_construits": panneaux,
                      "secondes_jusqu_a_l_affichage": round(ecoule, 3),
                      "echecs": echecs}, ensure_ascii=False))
    fenetre.close()
    app.quit()
    return 1 if echecs else 0
