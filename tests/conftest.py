# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Configuration pytest partagée : garantit que `pipeline` (et `manga`) sont
importables quel que soit le répertoire depuis lequel `pytest` est lancé."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.polices import explication_absence, police_japonaise  # noqa: E402


@pytest.fixture
def synthetic_manga_page():
    """Planche manga synthétique (fond + une bulle contenant du japonais), pour les
    tests de détection/OCR/orchestrateur de la brique manga (tests/test_manga_*.py).
    Générée à la volée avec Pillow + une police japonaise DU SYSTÈME — aucun asset
    externe, aucun contenu protégé par droit d'auteur.

    ⚠ Cette fixture skippait quand la police manquait, et le chemin était cloué à
    `C:/Windows/Fonts/msgothic.ttc`. C'est ce skip qui interdisait toute matrice d'OS :
    sur Linux il aurait emporté en silence la couverture détection / OCR / orchestrateur.
    La résolution est maintenant dans `tools/polices.py`, et `tests/test_fixture_police.py`
    ÉCHOUE — il ne skippe pas — quand aucune police n'est trouvable. Le skip qui reste ici
    ne se déclenche donc plus jamais sans qu'un autre test soit rouge à côté."""
    chemin = police_japonaise()
    if chemin is None:
        pytest.skip(explication_absence())
    from PIL import Image, ImageDraw, ImageFont

    w, h = 500, 500
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    for i in range(0, w, 20):
        d.line([(i, 0), (0, i)], fill=(220, 220, 220), width=1)
    bubble_box = (100, 100, 400, 260)
    d.ellipse(list(bubble_box), fill="white", outline="black", width=4)
    text = "こんにちは"
    font = ImageFont.truetype(str(chemin), 32)
    tb = d.textbbox((0, 0), text, font=font)
    tx = (bubble_box[0] + bubble_box[2]) / 2 - (tb[2] - tb[0]) / 2
    ty = (bubble_box[1] + bubble_box[3]) / 2 - (tb[3] - tb[1]) / 2
    d.text((tx, ty), text, font=font, fill="black")
    return img, bubble_box, text
