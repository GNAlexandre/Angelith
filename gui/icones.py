# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les icônes — **vingt-deux SVG en ligne, dans ce fichier, et pas un `.qrc`**.

## Pourquoi pas un fichier de ressources

Le projet n'est pas empaqueté et ne veut pas l'être : pas de `pyproject.toml`, c'est un choix
écrit dans `core/version.py`. Une étape `pyside6-rcc` ajouterait un artefact généré à committer
et une étape de build à un projet qui n'en a aucune. Douze glyphes de 24 px tiennent en trois
cents caractères chacun ; le coût d'un dossier de ressources dépasserait ce qu'il porte.

## Pourquoi `currentColor`

Une icône qui ne suit pas le thème est pire qu'un libellé texte : elle devient un carré noir
sur fond sombre, ou un fantôme sur fond clair. Chaque tracé déclare donc `currentColor`, et
`_teinter` substitue la couleur du token **avant** le rendu. Le rendu est mis en cache par
`(nom, couleur, côté)` : une pellicule qui repeint ses items ne doit pas re-parser un SVG.

## Pourquoi douze, et pas trente — puis vingt-deux, et pourquoi

Les douze premières : les cinq outils, supprimer, annuler, refaire, enregistrer, zoom ±,
ajuster. Le reste du logiciel n'en avait pas besoin, et une icône médiocre sur une action rare
nuit plus qu'un libellé clair.

⚠ **Le lot 31 en ajoute dix, et pas par goût.** La navigation latérale a trois modes de
largeur (`gui/destinations.mode_pour_largeur`), et celui du milieu — 641 à 1007 px — n'affiche
**que** l'icône. Une destination sans icône y devient un carré vide : elle n'est plus
atteignable qu'en élargissant la fenêtre ou par son raccourci. C'est donc le cas où l'icône
n'est pas un ornement mais le seul libellé, et la règle « icône **et** libellé » ci-dessous
est tenue autrement — par l'infobulle et le `AccessibleName`, que `PanneauNavigation` pose sur
chaque item.

Le compte est de **vingt-deux** au 2026-09-04 : douze du lot 18-19, neuf destinations, et le
bouton de menu du mode minimal.

## ⚠ Icône **et** libellé, jamais l'icône seule

Les cinq boutons de mode font des choses dont une seule est réversible sans écriture. En
particulier « Redessiner » **remet l'OCR et la traduction de la bulle à zéro** — une icône
seule ne dira jamais cela. Ils sont posés en `ToolButtonTextBesideIcon`, ce que
`tests/test_gui_theme.py` vérifie.
"""
from __future__ import annotations

#: Côté de rendu par défaut, en pixels logiques. 16 px : la hauteur d'un texte de barre
#: d'outils au corps normal, donc une icône qui ne fait pas grandir la barre.
COTE = 16

_ENTETE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
           'stroke-linejoin="round">')

#: `nom → corps du SVG`. L'en-tête commun est ajouté par `svg()` : douze recopies d'une même
#: ligne de vingt attributs finissent par diverger sur l'une d'elles.
TRACES: dict[str, str] = {
    # -- les cinq outils --------------------------------------------------- #
    # Un curseur de sélection : le repos, on ne dessine rien.
    "choisir": '<path d="M5 3l6 16 2.2-6.8L20 10z"/>',
    # Un rectangle en pointillés — la zone qu'on trace.
    "rectangle": '<rect x="3.5" y="5.5" width="17" height="13" rx="1" '
                 'stroke-dasharray="4 3"/><path d="M12 9v6M9 12h6"/>',
    # Une ellipse : la forme d'un ballon, et pas de coins repeints.
    "ellipse": '<ellipse cx="12" cy="12" rx="8.5" ry="6.5" stroke-dasharray="4 3"/>'
               '<path d="M12 9v6M9 12h6"/>',
    # ⚠ « Redessiner » : la gomme, parce que ce geste EFFACE l'OCR et la traduction. Un
    # crayon aurait dit « retoucher », ce qui est exactement le contre-sens à éviter.
    "redessiner": '<path d="M4 17.5L12.5 9a2.5 2.5 0 013.5 0l2.5 2.5a2.5 2.5 0 010 3.5'
                  'L14 19H6.5z"/><path d="M4 21h16"/>',
    # Un trait qui traverse une forme : la coupe.
    "scinder": '<rect x="4.5" y="7.5" width="15" height="9" rx="2"/>'
               '<path d="M3 21L21 3" stroke-dasharray="3 2"/>',

    # -- les actions ------------------------------------------------------- #
    "supprimer": '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>'
                 '<path d="M10.5 11v5M13.5 11v5"/>',
    "annuler": '<path d="M4 10h11a5 5 0 010 10h-6"/><path d="M8 6l-4 4 4 4"/>',
    "refaire": '<path d="M20 10H9a5 5 0 000 10h6"/><path d="M16 6l4 4-4 4"/>',
    # La disquette : conventionnelle au point d'être lisible sans légende.
    "enregistrer": '<path d="M4.5 4.5h12L20 8v11.5h-15.5z"/>'
                   '<path d="M8 4.5v5h7v-5M8 19.5v-5.5h8v5.5"/>',

    # -- le zoom ----------------------------------------------------------- #
    "zoom_plus": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>'
                 '<path d="M10.5 7.5v6M7.5 10.5h6"/>',
    "zoom_moins": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>'
                  '<path d="M7.5 10.5h6"/>',
    # Quatre coins qui rentrent : ramener la planche entière dans la fenêtre.
    "ajuster": '<path d="M3.5 9V3.5H9M15 3.5h5.5V9M20.5 15v5.5H15M9 20.5H3.5V15"/>'
               '<rect x="8" y="8" width="8" height="8" rx="1"/>',

    # -- les neuf destinations de la nav latérale (lot 31) ------------------ #
    #
    # ⚠ Elles ne sont PAS décoratives, et c'est la raison qui fait passer le compte de douze
    # à vingt et un : en mode COMPACT (641-1007 px), le pane n'affiche plus que l'icône. Une
    # destination sans icône y devient un carré vide, c'est-à-dire une destination
    # inatteignable autrement qu'en élargissant la fenêtre.
    #
    # Une maison : l'accueil, la seule page qui n'ouvre rien.
    "accueil": '<path d="M4 11.5L12 4l8 7.5"/><path d="M6 10.5V20h12v-9.5"/>'
               '<path d="M10 20v-5h4v5"/>',
    # Un livre ouvert : le roman.
    "light_novel": '<path d="M12 6.5C10 5 7.5 4.5 4 4.8v13c3.5-.3 6 .2 8 1.7"/>'
                   '<path d="M12 6.5C14 5 16.5 4.5 20 4.8v13c-3.5-.3-6 .2-8 1.7"/>'
                   '<path d="M12 6.5v13"/>',
    # Deux cases de planche, celle de droite plus haute : une double page de manga.
    "manga": '<rect x="3.5" y="4.5" width="7.5" height="15" rx="1"/>'
             '<rect x="13" y="4.5" width="7.5" height="6.5" rx="1"/>'
             '<rect x="13" y="13" width="7.5" height="6.5" rx="1"/>',
    # Une bande très allongée, avec la flèche du défilement vertical : le webtoon.
    "webtoon": '<rect x="7" y="3.5" width="10" height="17" rx="1.5"/>'
               '<path d="M12 7v9"/><path d="M9 13l3 3 3-3"/>',
    # Un cadre avec un soleil et une ligne d'horizon : une image produite.
    "illustrations": '<rect x="3.5" y="5" width="17" height="14" rx="2"/>'
                     '<circle cx="8.5" cy="10" r="1.8"/><path d="M4 17l5-4.5 4 3.5 3-2.5 4 3"/>',
    # Trois volumes rangés : la bibliothèque des œuvres.
    "oeuvres": '<path d="M4.5 5.5h3.5v14H4.5zM10 5.5h3.5v14H10z"/>'
               '<path d="M16.2 6.6l3.3.9-3.6 13.1-3.3-.9z"/>',
    # Un pinceau : la retouche d'une planche déjà rendue.
    "retouche": '<path d="M15.5 4.5l4 4-8.5 8.5-4-4z"/>'
                '<path d="M7 13l-2.5 6.5L11 17"/><path d="M14 6l4 4"/>',
    # L'engrenage conventionnel, réduit à six dents : au-delà, à 16 px, c'est un disque.
    "reglages": '<circle cx="12" cy="12" r="3.2"/>'
                '<path d="M12 3v2.5M12 18.5V21M21 12h-2.5M5.5 12H3"/>'
                '<path d="M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8M18.4 18.4l-1.8-1.8'
                'M7.4 7.4L5.6 5.6"/>',
    # Un stéthoscope stylisé : on ausculte l'installation, on ne la répare pas.
    "diagnostic": '<path d="M6 4v5a4 4 0 008 0V4"/><path d="M6 4h2M12 4h2"/>'
                  '<path d="M10 13v2a4 4 0 008 0v-1"/><circle cx="18" cy="12" r="2"/>',
    # Les trois barres du bouton de menu — mode MINIMAL, ≤ 640 px.
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
}

#: L'icône de l'application — `setWindowIcon`. Elle n'est PAS dans `TRACES` : elle est pleine
#: et colorée, alors que les douze autres sont des tracés monochromes qui prennent la teinte
#: du thème. Un ballon de manga, ce que le logiciel manipule.
LOGO = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#1e1e22"/>'
    '<ellipse cx="32" cy="28" rx="21" ry="15" fill="#f3f3f6"/>'
    '<path d="M24 41l-4 12 14-9z" fill="#f3f3f6"/>'
    '<path d="M21 24h22M21 31h15" stroke="#1e1e22" stroke-width="3.5" '
    'stroke-linecap="round"/>'
    '</svg>')


def noms() -> tuple[str, ...]:
    """Les icônes disponibles, dans l'ordre de déclaration."""
    return tuple(TRACES)


def svg(nom: str, couleur: str | None = None) -> str:
    """Le SVG complet d'une icône, `currentColor` substitué si une couleur est donnée.

    ⚠ La substitution est textuelle. C'est suffisant **parce que `currentColor` n'apparaît
    dans ces tracés qu'en valeur d'attribut de style** — il n'y a ni texte, ni `<use>`, ni
    contenu tiers dans ce fichier. Un SVG venu d'ailleurs demanderait un vrai parseur."""
    try:
        corps = TRACES[nom]
    except KeyError:
        raise KeyError(f"icône inconnue : {nom!r} — cf. gui/icones.TRACES") from None
    entier = f"{_ENTETE}{corps}</svg>"
    return entier.replace("currentColor", couleur) if couleur else entier


_CACHE: dict[tuple[str, str, int], object] = {}


def pixmap(nom: str, couleur: str, cote: int = COTE):
    """Le rendu d'une icône, en `QPixmap`. Mis en cache par `(nom, couleur, côté)`."""
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    cle = (nom, couleur, int(cote))
    trouve = _CACHE.get(cle)
    if trouve is not None:
        return trouve
    image = QImage(int(cote), int(cote), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    peintre = QPainter(image)
    QSvgRenderer(QByteArray(svg(nom, couleur).encode("utf-8"))).render(peintre)
    peintre.end()
    plaque = QPixmap.fromImage(image)
    _CACHE[cle] = plaque
    return plaque


def icone(nom: str, role: str = "texte", cote: int = COTE):
    """Une `QIcon` teintée par un **rôle du thème courant** — pas par une couleur littérale.

    C'est ce qui fait qu'une bascule de thème n'a qu'à vider le cache et redemander les mêmes
    icônes : aucun appelant ne connaît de couleur."""
    from PySide6.QtGui import QIcon

    from . import theme
    return QIcon(pixmap(nom, theme.couleur(role), cote))


def logo(cote: int = 64):
    """L'icône de l'application. Une seule, l'identité du logiciel.

    ⚠ Elle ne suit PAS le thème : elle apparaît dans la barre des tâches et l'alt-tab du
    système, où la couleur de fond n'est pas la nôtre. Une icône d'application qui change de
    couleur selon un réglage interne est une icône qu'on ne reconnaît plus."""
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    image = QImage(int(cote), int(cote), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    peintre = QPainter(image)
    QSvgRenderer(QByteArray(LOGO.encode("utf-8"))).render(peintre)
    peintre.end()
    return QIcon(QPixmap.fromImage(image))


def oublier() -> None:
    """Vide le cache — appelé à la bascule de thème, et par là seulement."""
    _CACHE.clear()
