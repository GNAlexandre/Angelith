# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Image de contrôle de l'analyse — régler un scan en une minute plutôt qu'en deux heures.

L'analyse repose sur des seuils géométriques. Sur un tirage inhabituel — corps plus petit,
marges plus larges, encre plus pâle — la seule façon honnête de savoir si elle tombe juste
est de la VOIR. Même intention que `tools/apercu_detection.py` pour les bulles de manga.

L'aperçu ne charge aucun modèle et ne lit aucun texte : il ne coûte qu'une analyse (~0,1 s).
"""
from __future__ import annotations

from pathlib import Path

from . import grille, pages

# Couleurs des surimpressions. Un contour par nature de zone, et des traits de coupe bien
# visibles — c'est la coupe qui décide de la qualité de la lecture.
COULEURS = {
    grille.CORPS: (0, 120, 255),
    grille.MOBILIER: (255, 0, 0),
}
COUPE = (0, 190, 0)
RUBY = (255, 140, 0)
INDENT = (160, 0, 200)


def composer(image, plan: grille.PlanPage):
    """La page, avec colonnes, coupes, ruby et mobilier en surimpression."""
    from PIL import Image, ImageDraw

    fond = image.convert("RGB")
    calque = Image.new("RGBA", fond.size, (0, 0, 0, 0))
    dessin = ImageDraw.Draw(calque)
    epaisseur = max(2, round(min(fond.size) / 500))

    for colonne in plan.colonnes:
        couleur = COULEURS.get(colonne.genre, (128, 128, 128))
        if colonne.genre == grille.CORPS and colonne.indentee:
            couleur = INDENT
        dessin.rectangle([colonne.x0, colonne.y0, colonne.x1, colonne.y1],
                         outline=couleur + (255,), width=epaisseur)
        for x0, x1, y0, y1 in colonne.ruby:
            dessin.rectangle([x0, y0, x1, y1], outline=RUBY + (255,), width=epaisseur)
        for y in colonne.coupes:
            dessin.line([colonne.x0 - epaisseur * 3, y, colonne.x1 + epaisseur * 3, y],
                        fill=COUPE + (255,), width=epaisseur)

    return Image.alpha_composite(fond.convert("RGBA"), calque).convert("RGB")


def ecrire_apercu(config: dict, projet: str, tome: str, page: int, *,
                  sortie: str = "apercu.png", seuil: int | None = None,
                  langue: str | None = None) -> Path:
    from PIL import Image

    from .orchestrator_scan import build_dir_de, config_scan

    cfg = config_scan(config)
    vol_dir = Path(config["chemins"]["sources"]) / projet / tome
    build_dir = build_dir_de(config, projet, tome)
    plan_tome = pages.scan_volume(vol_dir, build_dir, config, langue=langue)
    if not 0 <= page < len(plan_tome.pages):
        raise SystemExit(f"Page {page} hors du tome (0 à {len(plan_tome.pages) - 1}).")

    chemin = plan_tome.pages[page]
    with Image.open(chemin) as image:
        image.load()
        plan = grille.analyser(
            image, seuil=seuil if seuil is not None else cfg["seuil_encre"],
            caracteres_par_tranche=int(cfg["caracteres_par_tranche"]),
            encre_max=float(cfg["illustration_encre_max"]),
            colonnes_min=int(cfg["colonnes_min"]))
        rendu = composer(image, plan)

    destination = Path(sortie)
    if not destination.is_absolute():
        destination = build_dir / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendu.save(destination)
    print(f"page {page} ({chemin.name}) : {plan.verdict} · seuil {plan.seuil} · "
          f"pas {plan.pas:.0f} px · {len(plan.corps)} colonne(s) · "
          f"{sum(len(c.tranches()) for c in plan.corps)} tranche(s) · "
          f"{sum(1 for c in plan.corps if c.indentee)} indentée(s) · "
          f"{len(plan.mobilier)} zone(s) de mobilier"
          + (f" · {plan.motif}" if plan.motif else ""))
    return destination
