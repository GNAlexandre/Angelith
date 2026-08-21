# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Vignettes de planches et pastilles d'état — reconnaître un tome à l'œil.

## Pourquoi

La liste des planches était `  12   page_0012.png`. Sur un tome de 150 planches, retrouver
celle où l'on a vu un débordement demandait de les rouvrir une à une, et rien ne disait
lesquelles portaient un travail non relettré. C'est l'emprunt assumé à *Koharu* : une bande
de vignettes fait de la navigation un geste visuel.

## Ce qui est ici, et ce qui n'y est pas

Ce module **fabrique** des vignettes et **décide** ce qu'une pastille annonce. Il ne construit
aucun widget : la logique d'état vient de `manga/etat_planches.py`, et l'affichage reste dans
`gui/editeur.py`. C'est la règle de couche du dépôt — ce qui décide se teste sans PySide6.

## Le cache est sur DISQUE

Une vignette coûte un décodage JPEG et un rééchantillonnage ; 150 planches, c'est quelques
secondes, mais les repayer à chaque ouverture du tome serait absurde. Elles vivent donc sous
`build/<…>/manga/.vignettes/`, dossier caché parce qu'il n'est fait pour être lu par personne
— contrairement à `pages_clean/`, qui l'est.
"""
from __future__ import annotations

from pathlib import Path

from manga import checkpoints

DOSSIER = ".vignettes"
LARGEUR = 200
QUALITE = 72

# Dimensions de la CELLULE de la bande. Elles vivent ici, à côté de `LARGEUR`, et non dans le
# widget : le fabricant de vignettes et la bande qui les dispose doivent s'accorder, et c'est
# déjà tout le rôle de `LARGEUR`.
#
# ⚠ Ces trois valeurs corrigent un défaut d'affichage, pas un détail de style. La bande est un
# `QListWidget` en `IconMode` ; sans `setGridSize`, Qt dérive la position de chaque item de la
# taille RÉELLE de son pixmap. Un item pas encore vignetté mesure alors la taille de son texte
# seul (~26 × 36 px), et quand l'icône arrive `QIconModeViewBase::dataChanged` redimensionne
# son rectangle SUR PLACE sans refaire la disposition : l'item grandit là où il est et recouvre
# ses voisins. Mesuré sur 150 planches dans un panneau de 240 px : 2 767 paires d'items qui se
# chevauchent, et 9 « colonnes » pour un panneau qui n'en tient qu'une. Avec la grille : zéro.
HAUTEUR_ICONE = LARGEUR * 3 // 2        # 300 — la hauteur déclarée à `setIconSize`
LARGEUR_CELLULE = LARGEUR + 12          # 212 — la largeur, plus l'espacement des deux côtés
# La légende (`legende()`) peut tenir sur deux lignes avec `setWordWrap`, pastilles comprises.
HAUTEUR_CELLULE = HAUTEUR_ICONE + 44    # 344

# Filtres de la pellicule : libellé → prédicat sur l'état d'une planche.
FILTRES: dict[str, object] = {
    "toutes": lambda e: True,
    "modifiées à la main": lambda e: bool(e["corrigees"] or e["deplacees"]),
    "rendu périmé": lambda e: bool(e["perimee"]),
    "débordements": lambda e: bool(e["debordements"]),
    "sans traduction": lambda e: bool(e["detectee"] and e["vides"]),
    "jamais rendues": lambda e: not e["rendue"],
}


def chemin_vignette(build_dir, index: int) -> Path:
    return Path(build_dir) / DOSSIER / f"page_{index:04d}.jpg"


def source_de_vignette(build_dir, index: int) -> Path | None:
    """Quelle image miniaturiser.

    Le rendu final d'abord : c'est ce que l'utilisateur cherche à reconnaître. À défaut la
    planche nettoyée, qui existe dès le nettoyage — une vignette sans texte vaut mieux que
    pas de vignette du tout."""
    for chemin in (checkpoints.final_page_path(build_dir, index),
                   checkpoints.clean_page_path(build_dir, index)):
        if chemin.exists():
            return chemin
    return None


def vignette_a_jour(build_dir, index: int) -> bool:
    """La vignette existe-t-elle et suit-elle son image ?

    Comparaison de dates : un relettrage réécrit `pages_out/`, et une vignette figée
    montrerait l'ancienne planche — exactement ce qu'on regarde pour vérifier son travail."""
    vignette = chemin_vignette(build_dir, index)
    source = source_de_vignette(build_dir, index)
    if source is None:
        return True          # rien à miniaturiser : il n'y a pas de travail en attente
    try:
        return vignette.exists() and vignette.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def fabriquer_vignette(build_dir, index: int, *, largeur: int = LARGEUR) -> Path | None:
    """Écrit la vignette d'une planche et rend son chemin, ou `None` s'il n'y a rien à faire.

    ⚠ Appelée depuis la voie de LECTURE : aucun objet Qt, aucun checkpoint écrit. Le seul
    fichier produit vit dans un dossier qui n'appartient qu'à l'interface."""
    from PIL import Image

    source = source_de_vignette(build_dir, index)
    if source is None:
        return None
    cible = chemin_vignette(build_dir, index)
    cible.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGB")
        hauteur = max(1, round(image.height * largeur / max(1, image.width)))
        image.resize((largeur, hauteur), Image.LANCZOS).save(
            cible, "JPEG", quality=QUALITE, optimize=True)
    return cible


# --------------------------------------------------------------------------- #
#  Pastilles
# --------------------------------------------------------------------------- #

def pastilles(etat: dict) -> list[str]:
    """Les marques que porte une vignette, de la plus urgente à la moins.

    Courtes par construction : elles se lisent sous une image de 200 px, pas dans un rapport.
    Le détail complet reste dans l'infobulle (`etat_planches.libelle_etat`)."""
    if not etat["detectee"]:
        return ["∅"]
    marques = []
    if etat["perimee"]:
        marques.append("⟳")            # le rendu est en retard sur les données
    if etat["corrigees"]:
        marques.append(f"✎{etat['corrigees']}")
    if etat["deplacees"]:
        marques.append(f"↔{etat['deplacees']}")
    if etat["debordements"]:
        marques.append(f"⚠{etat['debordements']}")
    if not etat["rendue"]:
        marques.append("·")
    return marques


def legende(etat: dict) -> str:
    """Le texte sous la vignette : numéro, bulles, et les pastilles."""
    tete = f"{etat['index']}"
    if etat["detectee"]:
        tete += f" · {etat['bulles']}"
    marques = pastilles(etat)
    return f"{tete}  {' '.join(marques)}" if marques else tete


def couleur(etat: dict) -> str | None:
    """Teinte de la légende — `None` pour la couleur par défaut du thème.

    Trois états seulement, et dans cet ordre de priorité : ce qui manque, ce qui est en
    retard, ce qui a été touché à la main. Au-delà, une pellicule bariolée n'informe plus."""
    if not etat["detectee"]:
        return "#777"
    if etat["perimee"]:
        return "#d09030"
    if etat["corrigees"] or etat["deplacees"]:
        return "#6aa6d8"
    return None


def filtrer(etats: list[dict], filtre: str) -> list[dict]:
    """Les planches que le filtre retient. Un filtre inconnu ne masque rien — perdre des
    planches sur une faute de frappe serait le pire des retours."""
    predicat = FILTRES.get(filtre)
    if predicat is None:
        return list(etats)
    return [e for e in etats if predicat(e)]
