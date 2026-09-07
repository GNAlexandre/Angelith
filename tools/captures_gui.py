#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Captures d'écran de l'interface, sur un tome SYNTHÉTIQUE — `PLAN-19` étape 0 et critère 5.

    python tools/captures_gui.py docs/img/gui-avant
    python tools/captures_gui.py docs/img/gui-apres --theme clair --theme sombre

Quatre écrans depuis le lot 31 — l'accueil, la retouche, le lanceur manga et le lanceur
webtoon — plus les cinq dialogues. L'accueil est pris **avant tout geste** : c'est le premier
écran, et ses trois marqueurs d'installation y sont encore en « inconnu », comme au lancement.

## Pourquoi un tome fabriqué, et pas un tome du corpus

Les dix-sept projets de `sources/` sont des œuvres sous droit d'auteur. Une capture d'écran de
l'éditeur montre une planche en pleine page : la verser dans `docs/` reviendrait à publier une
planche de manga dans le dépôt. Le tome fabriqué ici — deux ellipses noires sur gris, deux
répliques — montre exactement les mêmes WIDGETS, dans les mêmes états, et c'est d'eux qu'il
s'agit. La seule chose qu'il ne montre pas est à quoi ressemble un vrai dessin sous les zones.

C'est le même montage que la fixture de `tests/test_gui_editeur_direct.py`, pour la même
raison : un tome complet sur disque fait fonctionner le chemin d'aperçu pour de vrai.

## Ce que la capture ne dit pas, et pourquoi PAS `offscreen`

⚠ **`QT_QPA_PLATFORM=offscreen` ne sait dessiner aucun texte ici** : `QFontDatabase.families()`
y rend **0 famille** sur cette machine, et toute la capture sort en tofu (`□□□□`). C'est
supportable pour la CI, qui ne regarde pas ses pixels ; ce serait absurde pour une capture dont
le sujet est la typographie et le contraste. L'outil tourne donc sur la plateforme native, et
la fenêtre apparaît réellement le temps du cliché.

Ce que la capture ne dit toujours pas : la mise à l'échelle DPI d'une autre machine, et le
rendu sous-pixel d'un autre écran. Elle sert à comparer un AVANT et un APRÈS pris de la même
façon, pas à juger un anticrénelage.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

TAILLE = (400, 900)


def _boite(k: int) -> tuple[int, int, int, int]:
    haut = 40 + k * 250
    return (60, haut, 340, haut + 180)


def _tome_synthetique(racine: Path) -> dict:
    """Écrit un tome complet — sources, checkpoints, page nettoyée — et rend la config."""
    import numpy as np
    from PIL import Image, ImageDraw

    from manga import checkpoints, clean, projet as projet_mod
    from manga.detection import BubbleRegion

    sources = racine / "sources" / "Demo" / "T1"
    build = racine / "build" / "Demo" / "T1" / "manga"
    sources.mkdir(parents=True)

    image = Image.new("RGB", TAILLE, (128, 128, 128))
    dessin = ImageDraw.Draw(image)
    for k in range(2):
        b = _boite(k)
        dessin.ellipse([b[0], b[1], b[2] - 1, b[3] - 1], fill=(255, 255, 255))
        dessin.rectangle([b[0] + 40, b[1] + 60, b[2] - 40, b[1] + 100], fill=(0, 0, 0))
    image.save(sources / "page_0001.png")

    def _masque(bbox):
        m = Image.new("L", TAILLE, 0)
        ImageDraw.Draw(m).ellipse([bbox[0], bbox[1], bbox[2] - 1, bbox[3] - 1], fill=255)
        return np.asarray(m) > 127

    regions = [BubbleRegion(bbox=_boite(k), mask=_masque(_boite(k)), score=0.9, cls=0)
               for k in range(2)]
    ckpt = checkpoints.page_checkpoint_dir(build, 1)
    checkpoints.save_regions(ckpt, regions, TAILLE)
    checkpoints.save_ocr(ckpt, ["アアア", "イイイ"])
    checkpoints.save_traduction(ckpt, ["Une réplique de démonstration.", "Et sa voisine."])
    chemin_clean = checkpoints.clean_page_path(build, 1)
    chemin_clean.parent.mkdir(parents=True, exist_ok=True)
    clean.clean_bubbles(image, regions).save(chemin_clean)
    projet_mod.ecrire(build, projet_mod.construire(
        build, projet="Demo", tome="T1", pages=[sources / "page_0001.png"],
        version="captures", page_ckpt=checkpoints.page_checkpoint_dir))

    from core import cli
    config = cli.charger_config(str(RACINE / "config.yaml"))
    # ⚠ `manga.chemins` HÉRITE de la section racine (`core.config.section`) : écrire dans
    # `config["manga"]["chemins"]` ne suffirait pas, la clé n'existe pas là.
    chemins = dict(config.get("chemins") or {})
    chemins["sources"] = str(racine / "sources")
    chemins["build"] = str(racine / "build")
    config["chemins"] = chemins
    config.setdefault("manga", {})["chemins"] = dict(chemins)
    return config


def _grab(widget, chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(chemin), "PNG")
    return chemin


def capturer(sortie: Path, themes: list[str]) -> list[Path]:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    ecrits: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="angelith-captures-") as tmp:
        racine = Path(tmp)
        config = _tome_synthetique(racine)
        for nom in themes:
            # ⚠ Le thème passe par le FICHIER DE RÉGLAGES, pas par un `theme.appliquer` ici.
            # `Fenetre.__init__` repose le thème persisté — c'est ce qui fait qu'une session
            # rouvre dans le thème choisi — et écraserait donc tout réglage posé avant elle.
            # Un fichier neuf par thème évite en plus qu'une capture hérite de l'onglet que la
            # précédente a laissé en se fermant.
            reglages = racine / f"interface-{nom}.json"
            os.environ["ANGELITH_REGLAGES"] = str(reglages)
            if nom != "existant":
                from gui import reglages as reg
                etat = reg.defauts()
                etat["theme"] = nom
                reg.ecrire(etat)
            from gui.fenetre import Fenetre
            fenetre = Fenetre(config, str(RACINE / "config.yaml"))
            fenetre.resize(1520, 960)
            fenetre.show()
            app.processEvents()
            # Lot 31 — l'ACCUEIL d'abord, parce que c'est désormais le premier écran et le
            # seul qui n'ouvre rien. Il est capturé avant tout geste : ses trois marqueurs
            # d'installation y sont encore en « inconnu », ce qui est exactement ce que voit
            # quelqu'un qui vient de lancer l'application.
            ecrits.append(_grab(fenetre, sortie / f"accueil-{nom}.png"))
            fenetre.aller_a("retouche")
            app.processEvents()
            fenetre.retouche.viser("Demo", "T1")
            app.processEvents()
            fenetre.editeur.liste_bulles.setCurrentRow(0)
            fenetre.deplier_journal()
            app.processEvents()
            ecrits.append(_grab(fenetre, sortie / f"retouche-{nom}.png"))
            ecrits.append(_capturer_retouche_verrouillee(app, fenetre, sortie, nom))
            fenetre.aller_a("manga")
            app.processEvents()
            ecrits.append(_grab(fenetre, sortie / f"manga-{nom}.png"))
            # ⚠ Le webtoon est capturé à part **parce qu'il porte sa réserve mesurée** en tête
            # (`gui/lanceur.RESERVE_WEBTOON`). Une capture qui ne montrerait que le lanceur
            # manga laisserait croire que les deux formats sont au même rang de mesure.
            fenetre.aller_a("webtoon")
            app.processEvents()
            ecrits.append(_grab(fenetre, sortie / f"webtoon-{nom}.png"))
            ecrits += _capturer_dialogues(app, config, sortie, nom, fenetre)
            fenetre.close()
            app.processEvents()
    return ecrits


def _capturer_retouche_verrouillee(app, fenetre, sortie: Path, theme_nom: str) -> Path:
    """L'état que le lot 35 rend lisible : la retouche VERROUILLÉE par un run global.

    ⚠ C'est le seul écran neuf du lot, et il ne se produit jamais tout seul dans une capture :
    il faut qu'un run tourne. On le fabrique donc à la main, en posant exactement ce que
    `Fenetre._sur_debut` puis `_repeindre_bandeau` poseraient — sans lancer de run, ce qui
    demanderait un modèle et des heures de GPU dans un script de capture.

    Avant ce lot, cet écran disait « Run manga — Demo / T1 — affichage seul » et rien
    d'autre : ni l'étape, ni l'avancement, ni le moindre geste. C'est précisément ce que la
    capture doit rendre comparable d'une version à l'autre."""
    from gui.travailleur import GENRE_RUN

    fenetre._cible_run = {"brique": "manga", "projet": "Demo", "tome": "T1"}
    fenetre._sur_debut(None, GENRE_RUN, "Run manga — Demo / T1")
    # ⚠ `"traduction"`, un identifiant de `core/progression.PHASES_MANGA`. `entrer()` IGNORE
    # une phase inconnue — délibérément, pour ne pas faire tomber un run de 150 planches sur
    # un défaut d'affichage — donc une faute de frappe ici produirait une capture sans étape,
    # sans rien pour le dire.
    fenetre.progression.entrer("traduction")
    fenetre.progression.avancer(84, 131, "page_0084.png")
    fenetre._repeindre_bandeau()
    app.processEvents()
    chemin = _grab(fenetre, sortie / f"retouche-verrouillee-{theme_nom}.png")
    # ⚠ On DÉVERROUILLE avant de rendre la main : les captures suivantes partagent la même
    # fenêtre, et un bandeau de run figé les traverserait toutes.
    fenetre._sur_fin(None, GENRE_RUN, True, "Terminé")
    fenetre.bandeau.effacer()
    app.processEvents()
    return chemin


def _capturer_dialogues(app, config, sortie: Path, theme_nom: str, parent) -> list[Path]:
    """Les cinq boîtes de dialogue, dans le thème courant.

    ⚠ Elles ne sont pas de la décoration : ce sont les seuls écrans du logiciel qui portaient
    quatre des douze `setStyleSheet` inline, et le `PLAN-19` demande des captures de **chaque
    panneau**. Sans elles, c'est le point du lot où un défaut d'apparence survivrait le plus
    facilement — personne ne les regarde autrement qu'en les ouvrant."""
    from gui import dialogues as dlg

    reglages = {"reprendre": True, "plafond_mo": None, "fenetre_apercu": None}
    boites = [
        ("nouveau-projet", lambda: dlg.DialogueNouveauProjet(config, (), parent)),
        ("diagnostic", lambda: dlg.DialogueTexte(
            "Diagnostic complet",
            "manga : OK" + chr(10) + "ln    : OK" + chr(10) + "scan  : modèle absent",
            parent, sous_titre="L'équivalent de `run_manga.py --check`.")),
        ("raccourcis", lambda: dlg.DialogueRaccourcis(parent)),
        ("legende", lambda: dlg.DialogueLegende(parent)),
        ("preferences", lambda: dlg.DialoguePreferences(reglages, parent)),
    ]
    ecrits = []
    for nom, fabrique in boites:
        boite = fabrique()
        boite.show()
        app.processEvents()
        ecrits.append(_grab(boite, sortie / f"dialogue-{nom}-{theme_nom}.png"))
        boite.close()
        app.processEvents()
    return ecrits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sortie", help="dossier où écrire les PNG")
    ap.add_argument("--theme", action="append", default=None,
                    help="« existant » (aucun thème posé), « clair », « sombre ». Répétable.")
    args = ap.parse_args()
    # ⚠ Surtout PAS « offscreen » : cf. le module. On retire même la variable si elle traîne
    # dans l'environnement, sans quoi la capture sort sans un seul glyphe.
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        del os.environ["QT_QPA_PLATFORM"]
    for chemin in capturer(Path(args.sortie), args.theme or ["existant"]):
        print(chemin)


if __name__ == "__main__":
    main()
