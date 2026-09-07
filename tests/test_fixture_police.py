# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""LE test du lot 20 : la couverture perdue devient une erreur visible.

## Ce qu'il achète

`tests/conftest.py` fabrique `synthetic_manga_page` avec une police japonaise du système et
**skippe** la fixture quand elle manque. Un skip ne colore rien : la suite reste verte, et
avec elle disparaissent la détection, l'OCR et l'orchestrateur de la brique manga — le code
le plus cher et le plus risqué du dépôt. C'est ce silence, et non la police, qui clouait la
CI à `windows-latest`.

Ce fichier ne skippe pas. Il **échoue**, et son message dit quoi installer. Une couverture
qui s'en va se voit donc en rouge, sur n'importe quel OS, avant que la matrice ne serve à
quoi que ce soit.

⚠ Il ne suffit pas qu'une police soit *trouvée*. Pillow rend des tofus sans lever quand la
police résolue ne couvre pas les kana — la fixture produirait alors une bulle « lettrée » de
rectangles vides, et le détecteur ne verrait pas la même chose. Le second test mesure donc
l'encre réellement posée à l'intérieur de la bulle.
"""
from __future__ import annotations

import sys

import pytest

from tools.polices import (
    CANDIDATS,
    VARIABLE,
    candidats,
    explication_absence,
    police_japonaise,
)


def test_une_police_japonaise_est_disponible():
    """Échoue — ne skippe pas. C'est tout l'objet du fichier."""
    chemin = police_japonaise()
    assert chemin is not None, explication_absence()
    assert chemin.is_file(), chemin


def test_la_planche_synthetique_porte_de_l_encre_dans_sa_bulle(synthetic_manga_page):
    """Une bulle vide et une bulle lettrée ne donnent pas le même score au détecteur.
    Si la police résolue ne couvrait pas les kana, ce test verrait la différence."""
    image, boite, texte = synthetic_manga_page
    assert texte, "la fixture doit poser du texte, pas seulement un ovale"

    x0, y0, x1, y1 = boite
    # Une marge généreuse : on veut l'INTÉRIEUR de la bulle, pas son trait de contour, qui
    # est noir par construction et compterait comme de l'encre quoi qu'il arrive.
    interieur = image.crop((x0 + 20, y0 + 20, x1 - 20, y1 - 20)).convert("L")
    sombres = sum(interieur.histogram()[:128])
    assert sombres > 100, (
        f"seulement {sombres} pixels sombres dans la bulle : la police résolue "
        f"({police_japonaise()}) ne rend probablement pas les kana. Pointer une police "
        f"couvrant le japonais avec {VARIABLE}.")


def test_la_fixture_n_est_jamais_sautee_quand_une_police_existe(synthetic_manga_page):
    """Contrepartie du premier test : si celui-ci est SAUTÉ alors que le premier passe,
    c'est que la fixture skippe pour une autre raison que la police — un cas qui n'existe
    pas aujourd'hui et qu'on veut voir apparaître s'il se crée."""
    image, _boite, _texte = synthetic_manga_page
    assert image.size == (500, 500)


# ---------------------------------------------------------------------------
# La résolution elle-même. Testée sans toucher au système : les fonctions prennent
# plateforme et environnement en paramètre pour ça.

def test_la_variable_d_environnement_prime_sur_les_candidats(tmp_path):
    fausse = tmp_path / "police.ttf"
    fausse.write_bytes(b"pas vraiment une police, mais un fichier")
    assert police_japonaise("win32", {VARIABLE: str(fausse)}) == fausse


def test_une_variable_pointant_dans_le_vide_est_une_erreur_pas_un_repli(tmp_path):
    """Le repli silencieux est exactement ce que ce module supprime : une surcharge fausse
    doit se voir, sinon la mesure porterait sur une autre police que celle qu'on croit."""
    with pytest.raises(FileNotFoundError, match=VARIABLE):
        police_japonaise("win32", {VARIABLE: str(tmp_path / "absente.ttc")})


def test_une_plateforme_inconnue_ne_leve_pas_elle_rend_none():
    assert candidats("plan9") == ()
    assert police_japonaise("plan9", {}) is None


def test_les_trois_plateformes_du_perimetre_ont_des_candidats():
    """macOS y figure pour un contributeur, pas pour la CI (`docs/roadmap.md` le classe hors
    périmètre) ; Windows et Linux sont les deux OS de la matrice."""
    for plateforme in ("win32", "linux", "darwin"):
        assert candidats(plateforme), plateforme


def test_tous_les_candidats_sont_des_chemins_absolus():
    """Un nom court serait résolu contre un chemin de recherche variable d'une machine à
    l'autre : on ne saurait plus dire quelle police a servi à la mesure."""
    import ntpath
    import posixpath
    for plateforme, chemins in CANDIDATS.items():
        for chemin in chemins:
            absolu = (ntpath.isabs(chemin) if plateforme == "win32"
                      else posixpath.isabs(chemin))
            assert absolu, (plateforme, chemin)


def test_le_message_d_absence_nomme_la_variable_et_la_commande():
    message = explication_absence("linux")
    assert VARIABLE in message
    assert "apt-get" in message
    assert "fonts-noto-cjk" in message


def test_la_plateforme_courante_est_dans_le_perimetre():
    """Si la suite tourne sur un OS sans candidat déclaré, `police_japonaise()` rendra
    toujours `None` et le premier test de ce fichier échouera sans dire pourquoi."""
    assert sys.platform in CANDIDATS, (
        f"{sys.platform} n'a aucun candidat de police déclaré dans tools/polices.py")
