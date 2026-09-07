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

def pastilles(etat: dict, brouillons: int = 0) -> list[str]:
    """Les marques que porte une vignette, de la plus urgente à la moins.

    Courtes par construction : elles se lisent sous une image de 200 px, pas dans un rapport.
    Le détail complet reste dans l'infobulle (`etat_planches.libelle_etat`).

    ⚠ `brouillons` — L18.6. C'est la seule marque qui ne vient PAS du disque, et elle passe
    donc devant toutes les autres : elle dit qu'il existe, sur cette planche, un travail que
    rien n'a encore écrit. Trois gestes (déplacer un bloc, changer le corps, retirer une
    correction) ne produisaient jusqu'ici qu'une ligne dans un journal replié à zéro, qui ne
    se déplie tout seul que sur un avertissement. Le même `●` que la liste de bulles, pour ne
    pas inventer un second vocabulaire.

    ⚠ Elle s'affiche même sur une planche NON détectée : c'est justement là qu'un travail non
    écrit serait le plus facile à perdre de vue."""
    marques = [f"●{brouillons}"] if brouillons else []
    if not etat["detectee"]:
        return marques + ["∅"]
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


def legende(etat: dict, brouillons: int = 0) -> str:
    """Le texte sous la vignette : numéro, bulles, et les pastilles."""
    tete = f"{etat['index']}"
    if etat["detectee"]:
        tete += f" · {etat['bulles']}"
    marques = pastilles(etat, brouillons)
    return f"{tete}  {' '.join(marques)}" if marques else tete


def role_couleur(etat: dict, brouillons: int = 0) -> str | None:
    """**Rôle** de la teinte de la légende — `None` pour la couleur par défaut du thème.

    Quatre états, dans cet ordre de priorité : ce qui n'est pas écrit, ce qui manque, ce qui
    est en retard, ce qui a été touché à la main. Au-delà, une pellicule bariolée n'informe
    plus.

    ⚠ Le travail non écrit passe en TÊTE, et devant « aucune détection » : une planche qui
    n'existe que dans la mémoire de l'application est ce qu'on peut perdre, tout le reste est
    sur le disque.

    ⚠ **Un rôle, plus une valeur** (`PLAN-19` L19.1). Cette fonction rendait `"#d09030"`,
    `"#6aa6d8"`, `"#777"`, `"#d05030"` — quatre valeurs de thème sombre, appliquées à la
    légende d'une liste que le style natif peint en blanc. Elle était pourtant le SEUL endroit
    du dépôt qui nommait l'idée d'un thème, en rendant `None` pour « couleur par défaut ». Elle
    avait raison ; il lui manquait un vocabulaire. `gui/theme.py` le lui donne, et ce module
    reste Qt-libre : il décide d'un ÉTAT, jamais d'un pixel."""
    if brouillons:
        return "pastille_brouillon"
    if not etat["detectee"]:
        return "pastille_absente"
    if etat["perimee"]:
        return "pastille_perimee"
    if etat["corrigees"] or etat["deplacees"]:
        return "pastille_main"
    return None


# --------------------------------------------------------------------------- #
#  La légende
# --------------------------------------------------------------------------- #

#: Ce que chaque symbole veut dire, groupé par endroit où on le rencontre.
#:
#: ⚠ Cette table ne REMPLACE pas les symboles par des icônes — c'est le travail de `PLAN-19`,
#: et il touche à la typographie, pas à la structure. Elle répond à une question plus étroite
#: et plus urgente : le sens de `∅`, `⟳`, `✎3` ou `↔2` n'était accessible que par SURVOL, donc
#: seulement à qui savait déjà qu'il y avait quelque chose à survoler. Le menu « Aide → Légende
#: des symboles » l'affiche noir sur blanc.
#:
#: Elle vit ici, à côté de `pastilles()` : deux tables qui divergeraient donneraient une
#: légende qui décrit une pellicule que le code ne dessine plus.
LEGENDE: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Sous une vignette de la pellicule", (
        ("●N", "N modification(s) tapée(s) mais PAS encore écrite(s) sur le disque"),
        ("∅", "aucune détection — cette planche n'a jamais été traitée"),
        ("⟳", "rendu périmé : les données ont bougé depuis le dernier lettrage"),
        ("✎N", "N réplique(s) corrigée(s) à la main — le pipeline ne les réécrira pas"),
        ("↔N", "N bulle(s) dont la position ou le corps ont été imposés à la main"),
        ("⚠N", "N débordement(s) relevés au lettrage"),
        ("·", "détectée mais jamais rendue"),
        ("12 · 7", "numéro de planche, puis nombre de bulles"),
    )),
    ("Dans la liste « Bulles (ordre de lecture) »", (
        ("●", "modification tapée mais PAS encore enregistrée"),
        ("✎", "correction manuelle déjà écrite sur le disque"),
        ("∅", "bulle sans texte — ni traduction ni correction"),
    )),
    ("En tête d'une ligne de journal", (
        ("⚠", "avertissement — déplie le journal et s'affiche 8 s dans la barre d'état"),
        ("⏱", "canal détaillé (« Journal détaillé », `--verbose`)"),
        ("·", "changement d'étape"),
    )),
    ("Couleur de la légende d'une vignette", (
        ("rouge", "travail non enregistré"),
        ("gris", "jamais détectée"),
        ("orange", "rendu périmé"),
        ("bleu", "touchée à la main"),
    )),
)


def filtrer(etats: list[dict], filtre: str) -> list[dict]:
    """Les planches que le filtre retient. Un filtre inconnu ne masque rien — perdre des
    planches sur une faute de frappe serait le pire des retours."""
    predicat = FILTRES.get(filtre)
    if predicat is None:
        return list(etats)
    return [e for e in etats if predicat(e)]


def nommer(numeros, *, maximum: int = 8, majuscule: bool = False) -> str:
    """« la planche 12 », « les planches 12, 27 et 40 », « les planches 1, 2… et 30 autres ».

    Ici et non dans `gui/fenetre.py` parce que l'éditeur en a besoin aussi (le remplacement
    plein-tome nomme les planches qu'il va toucher), et qu'un import de la fenêtre depuis
    l'éditeur serait circulaire — la fenêtre importe l'éditeur. C'est le module du NOMMAGE
    des planches, la fonction y est chez elle.

    Nommer les planches plutôt que les compter : « 5 planches en attente » n'apprend rien
    à qui cherche à savoir SI son travail sur la 27 est dedans. On plafonne quand même la
    liste — trente numéros dans une boîte de dialogue ne se lisent pas."""
    nums = sorted(int(n) for n in numeros)
    if not nums:
        return "aucune planche"
    tete = "L" if majuscule else "l"
    if len(nums) == 1:
        return f"{tete}a planche {nums[0]}"
    if len(nums) > maximum:
        reste = len(nums) - maximum
        visibles = ", ".join(str(n) for n in nums[:maximum])
        return (f"{tete}es planches {visibles} et {reste} autre"
                + ("s" if reste > 1 else ""))
    return (f"{tete}es planches " + ", ".join(str(n) for n in nums[:-1])
            + f" et {nums[-1]}")
