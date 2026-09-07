# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Combien de temps l'utilisateur attend-il ?** — et quelle interface cette durée impose.

C'est l'étape 0.1 du `PLAN-27`, et son tableau ne se discute pas : c'est le chiffre qui décide
de la forme de l'atelier, pas l'inverse.

| Temps par image | Interface juste |
|---|---|
| < 10 s | génération à la demande, l'utilisateur regarde |
| 10 à 60 s | file d'attente avec progression, l'utilisateur fait autre chose |
| > 60 s | **run par lot** : on lance, on revient |

## Le chiffre, et il est déjà mesuré

Le `PLAN-27` demande de « ne pas dessiner avant d'avoir ce chiffre ». Il n'a pas eu besoin
d'être mesuré une seconde fois : les lots 24, 25 et 26 l'ont publié trois fois, sur la même
carte, avec leurs dénominateurs. Ils sont recopiés dans `MESURES` — **avec** leur date, leur
échantillon et leur source, parce qu'un chiffre sans dénominateur n'est pas une mesure
(`docs/chiffres-de-reference.md`).

⚠ **Le verdict est sans ambiguïté et il n'est pas près de changer** : la médiane la plus basse
jamais relevée sur cette machine est **103,7 s**, soit 1,7× le seuil du haut du tableau ; la
plus haute est **1 524 s**, soit 25×. Aucune des deux ne tombe dans une autre tranche. La
conséquence pour l'interface est donc arrêtée : **run par lot**.

## Ce que « run par lot » veut dire pour le panneau, concrètement

1. **aucune barre de progression ne prétend chiffrer une seconde** de la phase image tant que
   la première image n'est pas revenue : ce serait inventer un chiffre ;
2. le panneau annonce **avant** de lancer ce que le lot va coûter, avec la fourchette mesurée
   et son échantillon — c'est le patron de `Fenetre._demander_relettrage`, qui chiffre son
   relettrage sur une constante mesurée avant de s'engager ;
3. l'unité d'avancement est **l'image terminée**, pas le pas de débruitage : on annonce
   « 3 images sur 8 », jamais « 42 % » ;
4. **la fenêtre reste utilisable** : le travail passe par le fil de travail, comme la copie
   d'archive du lot 18.

⚠ Ce module ne mesure rien lui-même et n'appelle rien. Il porte un tableau daté et la fonction
qui le lit. C'est volontaire : le jour où la carte change, on ajoute une ligne à `MESURES` et
`tranche()` rend un autre verdict — sans qu'aucun code d'interface ait à être relu.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Les trois tranches du tableau de l'étape 0.1, de la plus rapide à la plus lente.
A_LA_DEMANDE = "a_la_demande"
FILE = "file"
LOT = "lot"

#: Bornes, en secondes par image. Elles sont celles du plan, mot pour mot.
SEUIL_DEMANDE = 10.0
SEUIL_FILE = 60.0

LIBELLES = {
    A_LA_DEMANDE: "génération à la demande — l'utilisateur regarde",
    FILE: "file d'attente avec progression — l'utilisateur fait autre chose",
    LOT: "run par lot — on lance, on revient",
}


@dataclass(frozen=True)
class Mesure:
    """Un relevé, avec **tout** ce qu'il faut pour le contredire."""

    date: str
    secondes_par_image: float
    echantillon: int
    machine: str
    moteur: str
    source: str
    note: str = ""

    def ligne(self) -> str:
        base = (f"{self.date} · {self.secondes_par_image:.1f} s/image "
                f"(n = {self.echantillon}) · {self.machine} · {self.moteur} · {self.source}")
        return f"{base} — {self.note}" if self.note else base


#: Les relevés publiés par les lots précédents, dans l'ordre chronologique. **Aucun n'a été
#: refait pour ce lot** : refaire une mesure déjà publiée sans que rien n'ait changé
#: produirait un quatrième chiffre à confronter aux trois autres, ce que
#: `docs/chiffres-de-reference.md` désigne précisément comme le défaut à éviter.
MESURES: tuple[Mesure, ...] = (
    Mesure(date="2026-08-29", secondes_par_image=103.7, echantillon=4,
           machine="RX 7900 XT (20 464 Mio)", moteur="ComfyUI 0.34.2 · Qwen-Image-2512 GGUF Q4_1",
           source="docs/mesures/connecteur-qwen-2026-08-29.md",
           note="médiane ; 11 images sur 11 produites, 0 échec sur 25 générations"),
    Mesure(date="2026-08-29", secondes_par_image=1524.0, echantillon=1,
           machine="RX 7900 XT (20 464 Mio)", moteur="ComfyUI 0.34.2 · Qwen-Image-2512 GGUF Q4_1",
           source="docs/mesures/identite-2026-08-29.md",
           note="pire cas relevé, selon ce que ComfyUI garde en VRAM"),
    Mesure(date="2026-08-31", secondes_par_image=857.7, echantillon=1,
           machine="RX 7900 XT (20 464 Mio)", moteur="ComfyUI · Qwen-Image-Edit-2511 GGUF Q4_1",
           source="docs/mesures/atelier-2026-08-31.md §3.4",
           note="premier usage réel hors session de développement, workflow d'ÉDITION"),
)

#: Coût de la bascule VRAM, en secondes, mesuré le 2026-08-29 sur trois essais
#: (`illustration/orchestrateur.py:_basculer_vram`) : 2,03 s pour un modèle déchargé,
#: 4,22 / 4,14 / 4,05 s quand le même `yume-27b` était déchargé deux fois.
#:
#: ⚠ Il est **négligeable devant la génération** — 2 % du temps d'une seule image à 103,7 s —
#: et c'est un résultat, pas une évidence : le `PLAN-27` L27.2 prévoyait explicitement le cas
#: où la bascule serait « le poste le plus long ». Elle ne l'est pas sur cette machine. La
#: progression la distingue quand même, parce qu'un utilisateur qui voit la barre immobile
#: pendant deux secondes doit savoir que ce n'est pas la génération qui a commencé.
BASCULE_SECONDES = 2.03


def tranche(secondes_par_image: float) -> str:
    """La tranche du tableau, pour un coût par image donné."""
    if secondes_par_image < SEUIL_DEMANDE:
        return A_LA_DEMANDE
    if secondes_par_image <= SEUIL_FILE:
        return FILE
    return LOT


def mediane_mesuree() -> float:
    """La médiane des relevés de `MESURES`, pondérée par leur échantillon.

    ⚠ Pondérée, parce que les trois relevés n'ont pas le même poids : 4 images d'un côté,
    1 de l'autre. Une moyenne simple des trois nombres ferait dire au pire cas autant qu'à la
    médiane de la série la plus fournie."""
    valeurs: list[float] = []
    for mesure in MESURES:
        valeurs.extend([mesure.secondes_par_image] * max(1, mesure.echantillon))
    valeurs.sort()
    milieu = len(valeurs) // 2
    if len(valeurs) % 2:
        return valeurs[milieu]
    return (valeurs[milieu - 1] + valeurs[milieu]) / 2


def tranche_du_depot() -> str:
    """La tranche que les relevés du dépôt imposent **aujourd'hui**. C'est elle que
    l'interface doit servir, et un test le vérifie plutôt que de le supposer."""
    return tranche(mediane_mesuree())


def fourchette() -> tuple[float, float]:
    """`(le plus rapide, le plus lent)` des relevés — ce qu'on annonce AVANT de lancer."""
    valeurs = [m.secondes_par_image for m in MESURES]
    return min(valeurs), max(valeurs)


def annonce(images: int) -> str:
    """Ce que le panneau dit **avant** d'engager le GPU, pour `images` images.

    ⚠ Il annonce une **fourchette** et son échantillon, jamais un temps unique. Le rapport
    entre le meilleur et le pire relevé est de 14,7 ; une estimation ponctuelle serait fausse
    d'un facteur dix un jour sur deux, et le dépôt a déjà payé cette leçon —
    `SECONDES_PAR_RELETTRAGE` valait 1,5 s pour un coût réel de 4,0 s, « trois fois trop bas
    ne la rend pas approximative, ça la rend trompeuse »."""
    images = max(1, int(images))
    bas, haut = fourchette()
    total_bas, total_haut = bas * images + BASCULE_SECONDES, haut * images + BASCULE_SECONDES
    echantillon = sum(m.echantillon for m in MESURES)
    return (f"{images} image(s) : entre {_duree(total_bas)} et {_duree(total_haut)} "
            f"d'après {echantillon} génération(s) relevée(s) sur RX 7900 XT — "
            f"bascule VRAM comprise ({BASCULE_SECONDES:.1f} s).\n"
            f"  Le GPU est pris jusqu'au bout. La fenêtre reste utilisable ; le travail "
            f"passe par le fil de travail.")


def _duree(secondes: float) -> str:
    secondes = max(0.0, float(secondes))
    if secondes < 90:
        return f"{secondes:.0f} s"
    minutes, reste = divmod(int(round(secondes)), 60)
    if minutes < 60:
        return f"{minutes} min {reste:02d} s"
    heures, minutes = divmod(minutes, 60)
    return f"{heures} h {minutes:02d} min"


def resume() -> list[str]:
    """Le tableau daté, pour le document de mesure et pour `--check`."""
    lignes = [f"Tranche imposée : {tranche_du_depot()} — {LIBELLES[tranche_du_depot()]}",
              f"Médiane pondérée des relevés : {mediane_mesuree():.1f} s/image "
              f"(seuils du plan : {SEUIL_DEMANDE:.0f} s / {SEUIL_FILE:.0f} s)"]
    lignes += [f"  · {m.ligne()}" for m in MESURES]
    lignes.append(f"  · bascule VRAM : {BASCULE_SECONDES:.2f} s par run, une seule fois — "
                  f"2 % du coût d'UNE image, elle n'est pas le poste dominant")
    return lignes


# ──────────────  L29.5 — le devis, publié AVANT de lancer, pas après  ──────────────

#: Coût d'une image sur le chemin d'**ÉDITION** (avec référence), en secondes. Relevé le
#: 2026-08-29 sur **un** essai de sonde (`docs/mesures/identite-2026-08-29.md` §8.8) : la
#: tour de vision de `Qwen2.5-VL` encode chaque référence, et ses jetons s'ajoutent à la
#: séquence d'attention à chaque pas.
#:
#: ⚠ **n = 1, et le dénominateur commande la lecture.** Ce n'est pas la médiane de quatre
#: images qu'est `103,7 s` : c'est un essai. Un devis bâti dessus est un ORDRE DE GRANDEUR, et
#: `devis` le dit dans sa sortie plutôt que de rendre un nombre à la seconde près.
EDITION_SECONDES = 233.7
EDITION_ECHANTILLON = 1

#: Coût d'une image en **texte-vers-image**, sans référence : la médiane de `MESURES`, à
#: n = 4. C'est le seul des deux chiffres qui ait un échantillon.
TEXTE_SECONDES = 103.7
TEXTE_ECHANTILLON = 4


def devis(personnages: int, images_par_personnage: int, *, edition: bool = True) -> dict:
    """Ce que coûtera un balayage **avant** de le lancer. Aucun GPU n'est touché.

    Rend `{"images", "secondes", "duree", "par_image", "echantillon", "phrase"}`.

    ⚠ **Cette fonction existe à cause d'un défaut de méthode, pas d'un besoin d'affichage.**
    Le `PLAN-26` §11.2 écrit : « le plan demande 8 personnages et 10 images par axe ; les axes
    qui génèrent ont tourné sur **un** personnage et **2 à 3** images par axe ». Deux lots ont
    réclamé des dénominateurs sans jamais chiffrer les heures qu'ils coûtaient — et un coût
    qu'on ne chiffre pas se paie en acceptant des chiffres sur trois images. Le `PLAN-29`
    L29.5 impose donc l'ordre inverse : **publier le coût, puis lancer**.

    ⚠ Le devis ne compte QUE le GPU. Il ignore la phase 1 (le LLM), la relecture humaine —
    qui, elle, n'est pas parallélisable et que le lot 29 chiffre à une demi-journée — et
    l'écart de 14,7 entre le meilleur et le pire relevé du dépôt."""
    personnages = max(0, int(personnages))
    par_personnage = max(0, int(images_par_personnage))
    images = personnages * par_personnage
    par_image = EDITION_SECONDES if edition else TEXTE_SECONDES
    echantillon = EDITION_ECHANTILLON if edition else TEXTE_ECHANTILLON
    secondes = images * par_image + (BASCULE_SECONDES if images else 0.0)
    chemin = "édition (avec référence)" if edition else "texte-vers-image"
    return {
        "images": images,
        "secondes": secondes,
        "duree": _duree(secondes),
        "par_image": par_image,
        "echantillon": echantillon,
        "phrase": (f"{personnages} personnage(s) × {par_personnage} image(s) = {images} "
                   f"image(s) en {chemin}, à {par_image:.1f} s/image (n = {echantillon}) : "
                   f"**{_duree(secondes)}** de GPU, bascule VRAM comprise.\n"
                   f"  ⚠ Ordre de grandeur, pas une promesse : entre le meilleur et le pire "
                   f"relevé du dépôt le rapport est de "
                   f"{max(m.secondes_par_image for m in MESURES) / min(m.secondes_par_image for m in MESURES):.1f}."),
    }
