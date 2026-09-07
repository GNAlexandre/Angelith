#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que coûte l'OUVERTURE d'un tome dans la retouche — `PLAN-35` étape 0.1.

    python tools/mesure_ouverture.py --tome "manga D" Vol.1
    python tools/mesure_ouverture.py --tous --markdown --anonyme
    python tools/mesure_ouverture.py --tome "webtoon A" Chap.11 --attente 30

## Ce qu'il mesure, et pourquoi pas `tools/mesure_demarrage.py`

Le lot 31 a mesuré le DÉMARRAGE, et il l'a ramené à presque rien : la fenêtre n'ouvre plus de
tome toute seule. Ce qui reste après lui est le geste qu'on fait ensuite — cliquer
« Retouche », choisir un tome — et personne ne l'avait chiffré. Les deux outils partagent
leurs compteurs (`CompteurFichiers`, `pic_memoire_mo`) précisément pour que les deux tableaux
se lisent l'un à côté de l'autre.

## Ce que la mesure ne dit pas

- **Rien du disque froid.** Le cache de fichiers de Windows est chaud dès la deuxième
  ouverture du même tome ; ce sont des temps chauds, ce qui est le cas normal mais pas le
  pire.
- **Rien du GPU ni de la peinture réelle.** `QT_QPA_PLATFORM=offscreen` par défaut. La
  composition d'aperçus, elle, est du calcul PIL et ne change pas.
- **Le pic mémoire est celui du PROCESSUS**, interface Qt comprise — pas le coût marginal du
  tome. Le démarrage seul valait 106 Mo au lot 31 (`docs/mesures/coquille-2026-09-04.md`) ;
  c'est le repère à soustraire mentalement. `--tous` mesure chaque tome dans un processus
  neuf, sans quoi `PeakWorkingSetSize`, qui ne redescend jamais, ferait porter à la
  troisième ligne le pic de la plus grosse.
- **Rien de la variabilité.** Une seule ouverture par tome. Un tableau à un échantillon dit
  un ordre de grandeur, pas une distribution, et il le dit ici plutôt qu'en note de bas de
  page.
- **Rien du temps de RÉPONSE à la boîte de reprise.** `editeur.ouvrir` appelle
  `proposer_reprise`, qui est une **modale** dès qu'un miroir de récupération attend sous
  `build/<projet>/<tome>/manga/.recuperation/`. Elle est neutralisée ici (`exec()` rendu
  immédiat, aucun bouton cliqué, donc aucune reprise et **aucun effacement**) et le relevé
  publie `reprise_en_attente` : le chiffre chronométré est celui de l'ouverture, pas celui
  de l'utilisateur qui lit un dialogue. ⚠ Sans cette neutralisation l'outil ne rend jamais
  la main — c'est ce qui est arrivé au premier relevé du lot 35, sur le tome webtoon.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesure_demarrage import CompteurFichiers, pic_memoire_mo   # noqa: E402


def _tailles_des_sources(objet) -> tuple[list[str], int]:
    """Les dimensions distinctes des images source, et le plus gros compte de pixels.

    ⚠ C'est la seule chose qui distingue une bande d'une planche, et elle se lit sur le
    disque plutôt que sur le nom du format : `webtoon A` est déclaré webtoon, mais
    c'est sa géométrie — 1080×10 000 — qui coûte, pas son étiquette."""
    from PIL import Image

    tailles: list[tuple[int, int]] = []
    for page in objet.pages_source()[:400]:
        try:
            with Image.open(page) as image:
                tailles.append(image.size)
        except Exception:                            # noqa: BLE001 — page illisible
            continue
    return (sorted({f"{largeur}×{hauteur}" for largeur, hauteur in tailles}),
            max((largeur * hauteur for largeur, hauteur in tailles), default=0))


def mesurer(chemin_config: str, projet: str, tome: str, *, attente: float,
            rang: int = 0, sans_frein: bool = False) -> dict:
    """Une ouverture complète, chronométrée. Rend le relevé sous forme de dictionnaire.

    ⚠ Le chemin emprunté est **celui de l'utilisateur** : `aller_a("retouche")` puis
    `viser()`, c'est-à-dire le signal `demande_tome` → `Fenetre.ouvrir_tome` →
    `editeur.ouvrir`. Appeler `editeur.ouvrir` en direct mesurerait un chemin que personne
    n'emprunte, et manquerait le `Services` que la fenêtre construit au passage.

    ⚠ `rang` déplace la sélection dans la pellicule **avant** l'observation, et il n'est pas
    un raffinement : à l'ouverture on est sur la PREMIÈRE planche, donc la fenêtre glissante
    est tronquée à gauche et ne demande que 11 aperçus au lieu de 21. Mesurer uniquement le
    rang 0 ferait passer le cas favorable pour le cas courant.

    ⚠ `sans_frein=True` rend à `cache_apercu.fenetre_tenable` son comportement d'avant le
    lot 35 — la fenêtre demande tout ce que la marge dit, sans regarder le plafond. C'est ce
    qui produit la colonne « avant » du tableau, **dans le même processus, sous la même
    charge et avec le même compteur** que la colonne « après ». Mesurer l'avant sur un autre
    commit donnerait deux chiffres qu'on ne peut pas soustraire : les temps d'ouverture
    relevés le 2026-09-05 varient d'un facteur 2,6 selon ce que la machine fait par
    ailleurs."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    from core import cli
    from gui import theme
    from gui.editeur import PanneauEditeur
    from gui.fenetre import Fenetre
    from gui.modele_tome import Tome
    from gui import editeur_apercus
    from manga import recuperation

    config = cli.charger_config(chemin_config)
    releve: dict = {"projet": projet, "tome": tome, "attente": attente,
                    "rang": rang, "sans_frein": bool(sans_frein)}

    chrono = {"ouvrir": 0.0}
    # ⚠ Le nombre de COMPOSITIONS, distinct du nombre d'aperçus EN CACHE à la fin. C'est le
    # seul couple qui montre l'emballement : composer plus que le cache n'en garde veut dire
    # qu'on recompose ce qu'on vient d'évincer, et qu'on le refera tant que la fenêtre est
    # plus large que le plafond.
    chrono["compositions"] = 0
    vrai_ouvrir = PanneauEditeur.ouvrir
    vrai_composer = PanneauEditeur.composer_planche
    vrai_exec = QMessageBox.exec

    def _composer(self, numero):
        fait = vrai_composer(self, numero)
        if fait:
            chrono["compositions"] += 1
        return fait

    def _ouvrir(self, tome_objet):
        debut = time.perf_counter()
        try:
            return vrai_ouvrir(self, tome_objet)
        finally:
            chrono["ouvrir"] += time.perf_counter() - debut

    def _exec(self, *_a, **_k):
        """Aucune modale pendant une mesure. Cf. « ce que la mesure ne dit pas ».

        Rend `0` sans rien montrer : `clickedButton()` rendra `None`, donc `proposer_reprise`
        rendra `False` et n'effacera **rien**. Une neutralisation qui jetterait le miroir
        abîmerait le corpus pour produire un chiffre."""
        return 0

    vrai_tenable = editeur_apercus.fenetre_tenable
    PanneauEditeur.ouvrir = _ouvrir
    PanneauEditeur.composer_planche = _composer
    QMessageBox.exec = _exec
    if sans_frein:
        editeur_apercus.fenetre_tenable = (
            lambda _plafond, _poids, demandee: max(1, int(demandee)))
    try:
        app = QApplication.instance() or QApplication(sys.argv[:1])
        theme.appliquer(app, theme.AUTO)
        fenetre = Fenetre(config, chemin_config)
        fenetre.show()
        app.processEvents()
        fenetre.aller_a("retouche")
        app.processEvents()

        compteur = CompteurFichiers()
        with compteur:
            depart = time.perf_counter()
            trouve = fenetre.retouche.viser(projet, tome)
            app.processEvents()
            t_ouvert = time.perf_counter()
            if rang:
                liste = fenetre.editeur.liste_planches
                liste.setCurrentRow(min(int(rang), max(0, liste.count() - 1)))
                app.processEvents()
            releve["fichiers_a_l_ouverture"] = compteur.ouvertures
            fin = time.perf_counter() + attente
            while time.perf_counter() < fin:
                app.processEvents()
                time.sleep(0.02)
            t_apres = time.perf_counter()

        editeur = fenetre.editeur
        releve["trouve"] = bool(trouve)
        releve["t_viser"] = t_ouvert - depart
        releve["t_ouvrir"] = chrono["ouvrir"]
        releve["t_apres_attente"] = t_apres - depart
        releve["fichiers_total"] = compteur.ouvertures
        releve["fichiers_distincts"] = len(compteur.chemins)
        releve["compositions"] = chrono["compositions"]
        releve["apercus"] = len(editeur.cache)
        releve["apercus_mo"] = editeur.cache.octets / (1024 * 1024)
        releve["plafond_mo"] = editeur.cache.plafond / (1024 * 1024)
        releve["fenetre_prechargement"] = editeur.fenetre_prechargement
        # ⚠ L'ensemble RÉELLEMENT retenu par `_precharger`, pas la marge demandée. C'est la
        # question du plan — « que fait la fenêtre glissante quand il n'y a qu'un seul
        # élément à précharger ? » — et elle se répond en lisant l'ensemble, pas le réglage.
        releve["fenetre_effective"] = len(getattr(editeur, "_fenetre_apercu", ()) or ())
        releve["plans_figes"] = len(editeur._plans_apercu)
        try:
            objet = Tome(config, projet, tome)
            releve["unites"] = len(objet.index_planches())
            releve["langue"] = objet.langue_source()
            releve["tailles"], releve["pixels_max"] = _tailles_des_sources(objet)
            releve["reprise_en_attente"] = recuperation.resume(objet.build_dir)["planches"]
        except Exception as err:                     # noqa: BLE001 — cache abîmé
            releve["unites"] = f"illisible ({type(err).__name__})"
        releve["pic_mo"] = pic_memoire_mo()

        fenetre.fil_lecture.arreter()
        fenetre.fil.arreter()
        for fil in (fenetre.fil_lecture, fenetre.fil):
            reste = 20_000
            while fil.isRunning() and reste > 0:
                fil.wait(200)
                reste -= 200
        return releve
    finally:
        PanneauEditeur.ouvrir = vrai_ouvrir
        PanneauEditeur.composer_planche = vrai_composer
        QMessageBox.exec = vrai_exec
        editeur_apercus.fenetre_tenable = vrai_tenable


#: Les lignes du tableau de l'étape 0.1 : un tome paginé « moyen », le plus gros tome
#: COMPOSABLE du corpus, la bande webtoon — et une quatrième ligne que le plan ne demandait
#: pas.
#:
#: ⚠ **La quatrième est le plus gros tome du corpus tout court** (226 planches), et il n'a
#: **aucune page nettoyée** : détecté, jamais rendu. `_figer_plan_apercu` renonce alors sans
#: un mot, et l'ouverture compose **zéro** aperçu. Un tableau qui ne montrerait que des
#: tomes complets ferait croire que la fenêtre glissante travaille toujours ; elle ne
#: travaille que sur ce qui a un `clean/`.
#:
#: ⚠ **Les titres du corpus sont sous droit d'auteur** et ce script les nomme parce qu'il
#: tourne en local ; `--anonyme` les remplace par leur rang, exactement comme
#: `tools/inventaire_oeuvres.py`. C'est le tableau anonymisé qui se publie.
TOMES = (("manga B", "Chap.5"),
         ("manga D", "Vol.15"),
         ("webtoon A", "Chap.11"),
         ("manga D", "Vol.1"))


def _sous_processus(chemin_config: str, projet: str, tome: str, attente: float,
                    rang: int, sans_frein: bool = False) -> dict:
    """Mesure un tome dans un processus NEUF. C'est ce qui rend le pic mémoire comparable."""
    # ⚠ **Tous** les réglages du relevé sont repassés au sous-processus, `--rang` et
    # `--sans-frein` compris. Les oublier ne fait rien échouer : le sous-processus mesure
    # alors le cas par défaut, et l'on obtient deux tableaux « avant / après » identiques,
    # dont rien ne dit qu'ils décrivent la même chose. C'est arrivé au premier relevé du
    # lot 35, et c'est le mode de panne d'un outil de mesure — il ment sans planter.
    argv = [sys.executable, __file__, "--config", chemin_config, "--json",
            "--attente", str(attente), "--rang", str(rang), "--tome", projet, tome]
    if sans_frein:
        argv.append("--sans-frein")
    sortie = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", cwd=str(RACINE))
    for ligne in reversed((sortie.stdout or "").splitlines()):
        if ligne.startswith("{"):
            return json.loads(ligne)
    return {"projet": projet, "tome": tome,
            "erreur": (sortie.stderr or "").strip()[-400:] or "aucun JSON en sortie"}


#: Les colonnes du tableau publié. Déclarées, parce qu'un en-tête et un corps qui divergent
#: d'une colonne produisent un tableau silencieusement décalé.
COLONNES = ("Tome", "Unités", "Sources", "`editeur.ouvrir`", "`viser` complet",
            "Aperçus", "Cache (Mo)", "Fenêtre glissante", "Fichiers lus", "Pic (Mo)")


def rendre_markdown(releves: list[dict], *, anonyme: bool = False) -> str:
    lignes = ["| " + " | ".join(COLONNES) + " |",
              "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for rang, releve in enumerate(releves, start=1):
        nom = (f"tome {rang}" if anonyme
               else f"{releve.get('projet')} / {releve.get('tome')}")
        if releve.get("erreur"):
            lignes.append(f"| {nom} |" + " — |" * 8 + f" *{releve['erreur']}* |")
            continue
        attente = releve.get("attente", 0)
        lignes.append(
            f"| {nom} | {releve.get('unites')} | "
            f"{', '.join(releve.get('tailles') or []) or '—'} | "
            f"{releve.get('t_ouvrir', 0):.2f} s | {releve.get('t_viser', 0):.2f} s | "
            f"{releve.get('compositions')} composés → "
            f"{releve.get('apercus')} gardés, en {attente:.0f} s | "
            f"{releve.get('apercus_mo', 0):.1f} / {releve.get('plafond_mo', 0):.0f} | "
            f"{releve.get('fenetre_effective')} sur ±{releve.get('fenetre_prechargement')} | "
            f"{releve.get('fichiers_total')} | "
            + (f"{releve['pic_mo']:.0f}" if releve.get("pic_mo") else "n. m.") + " |")
    return "\n".join(lignes)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--tome", nargs=2, metavar=("PROJET", "TOME"))
    ap.add_argument("--tous", action="store_true",
                    help="les trois tomes de l'étape 0.1, un processus par tome")
    ap.add_argument("--attente", type=float, default=10.0,
                    help="secondes d'observation après l'ouverture (défaut : 10)")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--anonyme", action="store_true",
                    help="remplace les titres du corpus par « tome N » — ils sont sous "
                         "droit d'auteur, et un tableau publié n'a pas à les nommer")
    ap.add_argument("--rang", type=int, default=0,
                    help="rang dans la pellicule où se placer avant d'observer (défaut : 0, "
                         "c'est-à-dire la première planche — le cas FAVORABLE, où la fenêtre "
                         "glissante est tronquée à gauche)")
    ap.add_argument("--sans-frein", action="store_true",
                    help="désarme le frein de fenêtre du lot 35 — la colonne « avant »")
    ap.add_argument("--json", action="store_true", help="une ligne JSON, pour --tous")
    ap.add_argument("--ecran", action="store_true",
                    help="ne pas forcer QT_QPA_PLATFORM=offscreen")
    args = ap.parse_args()

    from core import cli
    cli.configurer_stdout()
    if not args.ecran:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    if args.tous:
        releves = [_sous_processus(args.config, projet, tome, args.attente, args.rang,
                                   args.sans_frein)
                   for projet, tome in TOMES]
        if args.markdown:
            print(rendre_markdown(releves, anonyme=args.anonyme))
            return
        print(json.dumps(releves, ensure_ascii=False, indent=2))
        return

    if not args.tome:
        ap.error("donne --tome PROJET TOME, ou --tous")
    releve = mesurer(args.config, args.tome[0], args.tome[1], attente=args.attente,
                     rang=args.rang, sans_frein=args.sans_frein)
    if args.json:
        print(json.dumps(releve, ensure_ascii=False))
        return
    if args.markdown:
        print(rendre_markdown([releve], anonyme=args.anonyme))
        return
    for cle, valeur in releve.items():
        print(f"{cle:26s} {valeur}")


if __name__ == "__main__":
    main()
