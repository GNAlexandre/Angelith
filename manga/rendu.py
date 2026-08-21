# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le lettrage d'UNE planche — le chemin unique, partagé par l'orchestrateur et l'éditeur.

## Pourquoi ce module existe

L'éditeur graphique doit pouvoir redessiner une planche après un déplacement de texte sans
relancer `process_volume` : un aller-retour complet pour bouger un bloc de dix pixels serait
inutilisable. Mais écrire un **second** chemin de rendu serait pire encore — deux moteurs
libres de diverger sur la seule chose que l'utilisateur regarde vraiment, les pixels.

D'où l'extraction. Il n'y a toujours qu'un seul chemin ; il a simplement deux appelants. La
promesse « ce qui sort de l'interface est ce que produirait `run_manga.py` » cesse d'être une
intention et devient une propriété du code, verrouillée par
`tests/test_manga_rendu.py::test_les_deux_chemins_donnent_la_meme_image`.

## Ce que la fonction fait, et dans quel ordre

Exactement ce que faisait le bloc de rendu de l'orchestrateur, sans rien réordonner :

1. `typeset_page` sur la planche NETTOYÉE, avec les mises en page enregistrées ;
2. les gloses d'onomatopées, en passe séparée **posée sur la planche déjà lettrée** — séparée
   parce que rien de tout cela ne doit pouvoir déranger le chemin des bulles.

Elle ne décide de rien : ni du forçage du glossaire, ni des corrections manuelles, ni de la
dérive terminologique. Ces trois-là s'appliquent au TEXTE, en amont, et restent chez l'appelant
— l'orchestrateur les fait pour un tome, l'éditeur les a déjà sur disque.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from . import gloss as gloss_mod
from . import typeset


@dataclass
class ResultatRendu:
    """Ce que le rendu a produit, au-delà de l'image.

    `qa` et `fits` étaient déjà collectés par l'orchestrateur (`report_out`, `fits_out`) ; les
    nommer ici évite que l'éditeur ait à les redécouvrir."""

    image: Image.Image
    qa: list[dict] = field(default_factory=list)
    fits: list[dict] = field(default_factory=list)
    gloses: list = field(default_factory=list)
    refus_gloses: list[str] = field(default_factory=list)


def rendre_planche(cleaned: Image.Image, regions: list, textes: list[str], *,
                   styles: list | None = None, font_path: str | None = None,
                   cfg_typeset: dict | None = None, sources: list[str] | None = None,
                   layouts: dict | None = None, avec_fits: bool = False,
                   zones_sfx: list | None = None, traductions_sfx: list[str] | None = None,
                   mode_sfx: str = "") -> ResultatRendu:
    """Lettre une planche sur son fond nettoyé. **Mute `cleaned`** — comme `typeset_page`.

    ⚠ La mutation est conservée telle quelle, et documentée plutôt que corrigée : l'export PSD
    a besoin de la planche nettoyée INTACTE en plus de la planche finale, et c'est l'appelant
    qui en garde une copie (`fond_propre`). Changer ce contrat ici ferait diverger les deux
    chemins sur un détail invisible en test et très visible en PSD.

    `avec_fits` alloue la recette de lettrage par bulle (position, taille, police, calque) :
    l'export PSD en a besoin, l'éditeur aussi pour son aperçu. C'était jusqu'ici conditionné à
    l'activation du PSD, si bien que l'information n'existait pas quand elle n'était pas
    exportée."""
    qa: list[dict] = []
    fits: list[dict] = [] if avec_fits else []
    image = typeset.typeset_page(
        cleaned, regions, textes, font_path=font_path, styles=styles, cfg=cfg_typeset,
        report_out=qa, fits_out=fits if avec_fits else None,
        sources=sources, layouts=layouts)

    gloses: list = []
    refus: list[str] = []
    if mode_sfx == "glose" and zones_sfx and any((t or "").strip()
                                                 for t in (traductions_sfx or [])):
        gloses, refus = gloss_mod.placer(image, zones_sfx, traductions_sfx or [],
                                         bulles=regions, cfg=cfg_typeset, font_path=font_path)
        image = gloss_mod.dessiner(image, gloses, cfg=cfg_typeset, font_path=font_path)

    return ResultatRendu(image=image, qa=qa, fits=fits, gloses=gloses, refus_gloses=refus)
