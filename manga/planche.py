# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que la planche sait d'elle-même, et que le traducteur ne recevait pas.

## Le constat qui a fait écrire ce module

Le pipeline **ne fait pas** un appel par bulle : l'unité est la planche entière, une seule
liste numérotée, un seul appel. C'est un bon choix. Le problème était le contenu du message —
le glossaire, les dernières répliques des planches précédentes, la place disponible en pixels,
et la liste numérotée. Et c'est tout. N'y figuraient ni **qui parle**, ni **la structure de la
planche**, ni **le type de bulle** — alors que le pipeline calcule déjà les trois, ou de quoi
les calculer, et les jette :

· `ocr._coupe_xy` coupe la planche par ses gouttières et n'en gardait qu'un ordre plat ;
· `geometry.width_profile` calcule la plage contiguë **pour exclure la queue de la bulle**,
  c'est-à-dire le seul signal graphique qui désigne le locuteur ;
· `BubbleRegion.kind` ne vaut que `"bulle"` ou `"onomatopee"` — mesuré sur les deux tomes de
  référence : `kind == "bulle"` 1 599 fois, sans une exception.

Ce module rassemble les trois en un objet, `Structure`, et un énoncé.

## La règle qui les gouverne tous les trois : **ne rien affirmer qu'on ne sache**

Un groupe faux fait continuer une phrase par-dessus un changement de plan. Un type faux fait
écrire un cri comme un récitatif. Une étiquette de locuteur fausse fait tutoyer un inconnu.
Dans les trois cas, **l'annotation absente vaut mieux que l'annotation fausse** — parce que le
modèle sait travailler sans, c'est ce qu'il faisait jusqu'ici.

D'où, partout : une classe `INDETERMINE` franche et généreusement utilisée, aucune étiquette
de locuteur quand le signal manque, et un taux d'indéterminé **publié** (cf. `tools/banc.py`).
Un classifieur qui type tout est un classifieur suspect.

## Ce que ce module ne fait PAS

Aucune reconnaissance de personnages, donc **aucun suivi de locuteur entre planches** : les
étiquettes sont locales à la planche et le prompt le dit. Suivre un personnage d'une planche à
l'autre demanderait un modèle, et les seuls disponibles sont sous licence de recherche
académique (cf. `geometry`, en tête de la section sur la queue).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ._config import fusion
from . import consignes, geometry, ocr

# ─────────────────────────────────────────────────────────────────────────────
# Types de bulle (L7.3)
# ─────────────────────────────────────────────────────────────────────────────

#: Les cinq valeurs possibles. `INDETERMINE` n'est pas un échec : c'est la réponse juste dès
#: que la forme ne tranche pas, et c'est la valeur la plus fréquente sur du corpus réel.
DIALOGUE = "dialogue"
PENSEE = "pensee"
RECITATIF = "recitatif"
CRI = "cri"
INDETERMINE = "indetermine"

TYPES = (DIALOGUE, PENSEE, RECITATIF, CRI, INDETERMINE)

#: Seuils du classifieur. Réglables par `manga.structure.*` — ce sont des seuils
#: d'heuristique, et le dépôt a pour habitude de les exposer plutôt que de les enfouir.
#:
#: ## Comment ils ont été fixés, et ce que la mesure a dit
#:
#: **Calibrés** sur 2 534 bulles — manga A Vol.1 et Vol.2, *manga C* Vol.1,
#: *webtoon A* Chap.11 — puis **vérifiés sur tout `build/`**, soit **7 862 bulles** de
#: dix volumes, dont 5 328 bulles qui n'ont pas servi au réglage. Avec pour objectif explicite
#: que l'indéterminé reste MAJORITAIRE :
#:
#:     indéterminé  86,2 %      dialogue  6,9 %      récitatif  5,4 %
#:     pensée        0,9 %      cri       0,6 %
#:
#: L'écart entre les deux mesures est instructif et vaut d'être écrit : le sous-ensemble de
#: réglage type **10,6 %** de dialogues contre 6,9 % sur le corpus entier, parce que *manga C* y
#: pèse un quart et que ses masques rendent les queues bien plus
#: lisibles (20,1 % de dialogues à lui seul). Le taux de dialogue mesure donc autant la
#: QUALITÉ DE SEGMENTATION du tome que sa proportion réelle de répliques parlées.
#:
#: ⚠ **Une mesure a été abandonnée en route, et il vaut mieux dire laquelle.** Le premier
#: classifieur triait le cri sur `ProfilForme.relief` — l'écart au contour lissé. Mesuré : le
#: 94ᵉ centile du relief est atteint par les masques les plus BRUITÉS du tome, pas par les
#: ballons en étoile ; un seuil posé là aurait typé « cri » les bulles les moins bien
#: segmentées. Ce qui distingue une étoile d'un contour sale n'est pas l'amplitude du relief
#: mais sa **périodicité**, d'où `ProfilForme.harmonique` (cf. `geometry._harmonique`).
#:
#: ⚠ **La pensée reste le point faible.** Les masques de `detection.py` sont bruités : toute
#: bande d'ondulation « moyenne » attrape 15 à 30 % des bulles, c'est-à-dire les bulles
#: ordinaires. La conjonction retenue — lobes périodiques, PEU PROFONDS, et nombreux — n'en
#: garde que 0,9 %. Un vrai ballon de pensée mal typé reste traité comme un dialogue, ce qui
#: est le comportement d'avant ce lot ; l'inverse — un dialogue annoncé « pensée » — ferait
#: écrire une réplique en voix intérieure, et ne serait pas rattrapable.
#:
#: Ces seuils se rejouent par `tools/mesurer_structure.py`, qui republie la distribution sur
#: n'importe quel volume de `build/` **sans charger le moindre modèle**.
DEFAUTS = {
    # — Groupes ————————————————————————————————————————————————————————————
    # Gouttière minimale pour qu'une coupe soit une RUPTURE DE MISE EN PAGE et non un simple
    # espace entre deux bulles d'un même plan, en fraction de l'étendue de la PLANCHE sur
    # l'axe de la coupe. À 0,045 sur une planche 1125×1600 : 72 px verticaux, soit nettement
    # plus qu'un interligne de bulles et de l'ordre d'une gouttière de case.
    "gouttiere_min_frac": 0.045,
    # — Types ——————————————————————————————————————————————————————————————
    # Un récitatif est un RECTANGLE : il remplit sa boîte (mesuré sur le corps, cf.
    # `ProfilForme.remplissage_corps`, p95 = 0,997) et ses côtés sont parallèles (p95 = 1,00).
    "recitatif_remplissage_min": 0.985,
    "recitatif_rectangularite_min": 0.97,
    # Un cri a des lobes PÉRIODIQUES (p99 de `harmonique` = 0,104) et PROFONDS (p75
    # d'`ondulation` = 0,305). C'est la conjonction qui trie, jamais l'un des deux : le corpus
    # est plein de contours profondément irréguliers mais apériodiques — ce sont des masques
    # mal segmentés, pas des ballons de cri.
    "cri_harmonique_min": 0.10,
    "cri_ondulation_min": 0.25,
    # Une pensée a des festons : des lobes périodiques eux aussi, mais PEU PROFONDS et
    # nombreux — et aucune queue, un ballon de pensée n'en a pas, il a une traîne de bulles.
    "pensee_harmonique_min": 0.030,
    "pensee_ondulation_max": 0.15,
    "pensee_pointes_min": 8,
    # — Locuteurs ——————————————————————————————————————————————————————————
    # Deux queues qui désignent des points distants de moins de ceci (en fraction de la
    # diagonale de la planche) désignent le même locuteur.
    "locuteur_rayon_frac": 0.09,
    # En dessous de deux bulles à queue lisible, aucune étiquette n'est posée du tout.
    "locuteur_min_bulles": 2,
}

#: Étiquettes de locuteur, dans l'ordre d'attribution. Au-delà de six locuteurs sur une même
#: planche, le signal est trop bruité pour valoir quoi que ce soit : on n'étiquette pas.
_ETIQUETTES = "ABCDEF"


@dataclass
class Structure:
    """La structure d'UNE planche, alignée par position sur `regions` / `ocr.json`.

    ⚠ L'alignement par position est le pivot de toute la brique (cf. `checkpoints`) : ces
    listes font exactement `len(regions)`, toujours, y compris quand rien n'a pu être mesuré.
    """
    #: Numéro de groupe (1-indexé) de chaque bulle, dans l'ordre de lecture.
    groupes: list[int] = field(default_factory=list)
    #: Type de chaque bulle (une valeur de `TYPES`).
    types: list[str] = field(default_factory=list)
    #: Étiquette de locuteur (`"A"`, `"B"`, …) ou `""` quand le signal manque.
    locuteurs: list[str] = field(default_factory=list)
    #: Le repli diagonal de `ocr._coupe_ruptures` a servi quelque part sur cette planche :
    #: l'ORDRE de certaines bulles est un tri par diagonale, pas une coupe par gouttières.
    #: Informationnel — cf. `lignes_bulles` pour la raison pour laquelle ce n'est pas un veto.
    repli_ordre: bool = False

    def __len__(self) -> int:
        return len(self.types)

    @property
    def n_groupes(self) -> int:
        return max(self.groupes) if self.groupes else 0

    def groupes_monotones(self) -> bool:
        """Les numéros de groupe croissent-ils dans l'ordre des régions ?

        ⚠ Ce n'est pas une paranoïa gratuite. `regions.json` est persisté DANS l'ordre de
        lecture, si bien que les deux ordres coïncident normalement et que la séquence est
        croissante par construction. Mais un cache trié sous un autre `sens` existe — c'est
        tout l'objet de `tools/verifier_ordre.py`, et le défaut y est décrit comme silencieux.
        Sur un tel cache, les groupes reviendraient en arrière et l'énoncé afficherait deux
        fois « — Groupe 1 — », c'est-à-dire une structure fausse présentée comme un fait. On
        n'annonce alors aucun groupe : le reste de l'annotation, qui est par bulle, reste
        valable."""
        return all(b >= a for a, b in zip(self.groupes, self.groupes[1:]))

    def annotee(self) -> bool:
        """Y a-t-il quoi que ce soit à annoncer au modèle ?

        Une planche dont toutes les bulles sont indéterminées, sans locuteur et en un seul
        groupe n'a rien apporté : lui coller la note de lecture serait payer des tokens pour
        décrire un vide."""
        return bool(self.n_groupes > 1
                    or any(t in consignes.TYPES_MENTION for t in self.types)
                    or any(self.locuteurs))

    def en_json(self) -> dict:
        return {"groupes": list(self.groupes), "types": list(self.types),
                "locuteurs": list(self.locuteurs), "repli_ordre": bool(self.repli_ordre)}

    @classmethod
    def depuis_json(cls, charge) -> "Structure | None":
        if not isinstance(charge, dict):
            return None
        return cls(groupes=[int(g) for g in charge.get("groupes") or []],
                   types=[str(t) for t in charge.get("types") or []],
                   locuteurs=[str(v) for v in charge.get("locuteurs") or []],
                   repli_ordre=bool(charge.get("repli_ordre", False)))


def vide(n: int) -> Structure:
    """La structure d'une planche dont on ne sait rien : un seul groupe, aucun type, aucun
    locuteur. C'est ce que reçoit un cache antérieur à ce lot, et c'est l'énoncé de la
    1.0.0 — donc rigoureusement iso-comportement."""
    return Structure(groupes=[1] * n, types=[INDETERMINE] * n, locuteurs=[""] * n)


# ─────────────────────────────────────────────────────────────────────────────
# Groupes (L7.2)
# ─────────────────────────────────────────────────────────────────────────────

def groupes_de_ruptures(ruptures: list[float], seuil: float) -> list[int]:
    """Numéros de groupe (1-indexés) à partir des gouttières entre bulles voisines.

    ⚠ « Groupe » et non « case ». `ocr._coupe_xy` ne détecte aucune case : il coupe des
    gouttières, et sa docstring le dit — « c'est *panel-aware sans jamais détecter les
    cases* ». Annoncer des cases au modèle lui ferait inférer une précision qui n'existe
    pas ; le dépôt a déjà cette discipline, puisqu'il annonce la langue source et le sens de
    lecture au lieu de les laisser supposer."""
    numeros = [1]
    for r in ruptures:
        numeros.append(numeros[-1] + (1 if r >= seuil else 0))
    return numeros


# ─────────────────────────────────────────────────────────────────────────────
# Types (L7.3)
# ─────────────────────────────────────────────────────────────────────────────

def classer(profil: geometry.ProfilForme, cfg: dict | None = None) -> str:
    """Type d'une bulle à partir de sa seule forme. **Aucun appel LLM.**

    L'ordre des tests n'est pas indifférent, et il va du signal le plus franc au plus
    fragile :

    1. **récitatif** — un rectangle plein, sans queue. C'est la forme la moins ambiguë du
       corpus (5,4 % des bulles mesurées), et c'est aussi celle dont le rendu diffère le plus
       du dialogue : un registre narratif plutôt que parlé ;
    2. **cri** — des lobes périodiques ET profonds (0,6 %). Testé AVANT le dialogue, et pas
       après : un ballon de cri porte souvent une queue, et le typer « dialogue » pour cette
       raison ferait perdre la mention sur la majorité des cris ;
    3. **dialogue** — une queue (6,9 %). C'est le signal positif : sans elle, une bulle lisse
       peut tout aussi bien être un récitatif arrondi ;
    4. **pensée** — un contour festonné, sans queue (0,9 %) ;
    5. **indéterminé** — tout le reste, et c'est 86,2 % du corpus.

    ⚠ Chaque test lit `remplissage_corps` et non `remplissage` : le remplissage brut d'une
    bulle de dialogue à longue queue tombe à 0,60 — la queue étire la boîte englobante sans
    rien remplir — soit exactement la valeur d'un ballon de cri.

    ⚠ Et chaque test de contour lit `harmonique`, pas `ondulation` seule ni `relief` : les
    deux dernières répondent aussi bien à un ballon en étoile qu'à un masque mal segmenté, et
    le corpus est plein des seconds. Seule la périodicité les sépare."""
    c = fusion(DEFAUTS, cfg)
    plein = profil.remplissage_corps >= c["recitatif_remplissage_min"]
    if (profil.queue is None and plein
            and profil.rectangularite >= c["recitatif_rectangularite_min"]):
        return RECITATIF
    if (not plein and profil.harmonique >= c["cri_harmonique_min"]
            and profil.ondulation >= c["cri_ondulation_min"]):
        return CRI
    if profil.queue is not None:
        return DIALOGUE
    if (not plein and profil.harmonique >= c["pensee_harmonique_min"]
            and profil.ondulation < c["pensee_ondulation_max"]
            and profil.pointes >= c["pensee_pointes_min"]):
        return PENSEE
    return INDETERMINE


# ─────────────────────────────────────────────────────────────────────────────
# Locuteurs (L7.5)
# ─────────────────────────────────────────────────────────────────────────────

def _etiqueter(queues: list, taille: tuple[int, int], cfg: dict) -> list[str]:
    """Étiquettes de locuteur à partir des cibles de queue. `""` là où le signal manque.

    Le regroupement est une union-find sur la **distance entre cibles** : deux queues qui
    désignent le même endroit sont le même locuteur, deux queues opposées sont deux
    locuteurs, donc un échange. C'est de la géométrie, pas de la reconnaissance de
    personnages.

    **Trois précautions, non négociables.**

    1. **Locale à la planche.** Aucune continuité d'une planche à l'autre n'est prétendue.
    2. **Le prompt dit ce que l'étiquette vaut** (« probablement le même locuteur »), cf.
       `consignes.STRUCTURE_NOTE`.
    3. **Aucune étiquette quand le signal est absent** : moins de deux queues lisibles, ou
       plus d'étiquettes que `_ETIQUETTES` n'en porte — une planche où chaque bulle serait son
       propre locuteur n'apprend rien et coûte des tokens."""
    lisibles = [i for i, q in enumerate(queues) if q is not None]
    if len(lisibles) < int(cfg["locuteur_min_bulles"]):
        return [""] * len(queues)
    w, h = taille
    rayon = float(cfg["locuteur_rayon_frac"]) * (max(1, w) ** 2 + max(1, h) ** 2) ** 0.5

    parent = {i: i for i in lisibles}

    def racine(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a in range(len(lisibles)):
        for b in range(a + 1, len(lisibles)):
            ia, ib = lisibles[a], lisibles[b]
            (xa, ya), (xb, yb) = queues[ia].cible, queues[ib].cible
            if ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5 <= rayon:
                parent[racine(ia)] = racine(ib)

    # Étiquettes attribuées dans l'ORDRE DE LECTURE : [A] est le premier à parler, ce qui est
    # la seule convention que le modèle puisse deviner sans qu'on la lui dise.
    ordre: dict[int, str] = {}
    for i in lisibles:
        r = racine(i)
        if r not in ordre:
            if len(ordre) >= len(_ETIQUETTES):
                return [""] * len(queues)
            ordre[r] = _ETIQUETTES[len(ordre)]
    if len(ordre) < 2 and len(lisibles) < len(queues):
        # Un seul locuteur identifié alors que d'autres bulles n'ont pas de queue : l'étiquette
        # n'apprend rien au modèle et suggère faussement qu'on a tout vu.
        return [""] * len(queues)
    return [ordre[racine(i)] if i in parent else "" for i in range(len(queues))]


# ─────────────────────────────────────────────────────────────────────────────
# Analyse complète
# ─────────────────────────────────────────────────────────────────────────────

def analyser(regions: list, taille: tuple[int, int], *, sens: str = "droite_gauche",
             cfg: dict | None = None) -> Structure:
    """Structure d'une planche à partir de ses seules régions. **Aucun appel LLM.**

    ⚠ `regions` est attendu **déjà dans l'ordre de lecture** — c'est l'ordre persisté dans
    `regions.json`, et celui auquel `ocr.json` et `traduction.json` s'alignent par position.
    On rejoue donc la coupe pour récupérer les GOUTTIÈRES, pas pour réordonner : l'ordre
    obtenu est identique par construction (`ocr._coupe_ruptures` est le parcours de
    `_coupe_xy`), et un désaccord signerait un cache trié sous un autre `sens` — cas que
    `tools/verifier_ordre.py` sait déjà débusquer, et qu'on ne masque pas ici."""
    c = fusion(DEFAUTS, cfg)
    n = len(regions or [])
    if n == 0:
        return Structure()

    ordre, ruptures, repli = ocr.ordre_et_ruptures(list(regions), sens, taille)
    position = {id(r): k for k, r in enumerate(ordre)}
    groupes_ordre = groupes_de_ruptures(ruptures, float(c["gouttiere_min_frac"]))
    # Remis dans l'ordre de `regions`, qui est celui du cache.
    groupes = [groupes_ordre[position.get(id(r), 0)] for r in regions]

    profils = [geometry.profil_de_forme(r.mask)
               if getattr(r, "mask", None) is not None else None for r in regions]
    types = [classer(p, c) if p is not None else INDETERMINE for p in profils]
    queues = [p.queue if p is not None else None for p in profils]
    locuteurs = _etiqueter(queues, taille, c)

    return Structure(groupes=groupes, types=types, locuteurs=locuteurs, repli_ordre=repli)


# ─────────────────────────────────────────────────────────────────────────────
# L'énoncé
# ─────────────────────────────────────────────────────────────────────────────

def lignes_bulles(textes: list[str], structure: Structure | None, *, depart: int = 1,
                  pack=None) -> list[str]:
    """La liste numérotée telle que le modèle la reçoit, séparateurs de groupe compris.

    Sans structure — ou avec une structure sans rien à dire —, rend exactement
    `["1. …", "2. …"]`, c'est-à-dire la forme de la 1.0.0 au caractère près. C'est ce qui rend
    vérifiable le critère d'acceptation du lot : « le mode texte sans les nouvelles clés
    produit un résultat inchangé ».

    ⚠ `repli_ordre` ne supprime PAS le groupement, et c'est un arbitrage qu'il faut écrire.
    Là où `ocr._coupe_ruptures` tombe sur son repli diagonal, il ne mesure aucune gouttière —
    donc il ne déclare aucune rupture, donc les bulles concernées restent dans le MÊME groupe.
    Le repli produit une fusion prudente, jamais une coupure inventée : il n'y a rien à cacher
    au modèle. Ce qu'il rend incertain est l'ORDRE à l'intérieur de ces bulles-là, ce qui est
    une propriété de `_coupe_xy` antérieure à ce lot et que `tools/verifier_ordre.py` traite
    déjà. Le drapeau est donc persisté et publié au banc — mesuré à ~37 % des planches — plutôt
    que transformé en veto sur une information qui, elle, est saine."""
    if structure is None or not structure.annotee():
        return [f"{depart + k}. {t}" for k, t in enumerate(textes)]
    montrer_groupes = structure.n_groupes > 1 and structure.groupes_monotones()
    lignes: list[str] = []
    precedent = None
    for k, t in enumerate(textes):
        groupe = structure.groupes[k] if k < len(structure.groupes) else 1
        if montrer_groupes and groupe != precedent:
            lignes.append(consignes.texte(pack, "manga_groupe_entete", groupe=groupe))
            precedent = groupe
        mention = consignes.mention_de_type(
            pack, structure.types[k] if k < len(structure.types) else INDETERMINE)
        locuteur = structure.locuteurs[k] if k < len(structure.locuteurs) else ""
        prefixe = "".join(p + " " for p in (f"[{locuteur}]" if locuteur else "", mention) if p)
        lignes.append(f"{depart + k}. {prefixe}{t}")
    return lignes


def note_de_lecture(structures: list[Structure | None], pack=None) -> str:
    """La note qui dit au modèle ce que valent les annotations, ou `""` s'il n'y en a aucune.

    Une seule note pour tout un lot : elle décrit une convention d'écriture, pas une planche.
    La payer par planche multiplierait par vingt un coût qui n'apporte rien de plus."""
    if not any(s is not None and s.annotee() for s in structures):
        return ""
    return consignes.texte(pack, "manga_structure_note")


def boites_de_groupes(regions: list, structure: Structure | None, taille: tuple[int, int],
                      *, marge_frac: float = 0.06,
                      groupes: list[int] | None = None) -> list[tuple[int, int, int, int]]:
    """Boîtes englobantes des groupes, élargies d'une marge. Pour les crops du mode « cible ».

    ⚠ La marge n'est pas cosmétique : une boîte de groupe ne couvre que les BULLES, alors que
    ce qu'un modèle vision doit voir est le dessin autour d'elles. Un crop de groupe reste
    cinq à dix fois plus léger qu'une planche entière, et bien plus lisible — le sujet occupe
    le cadre."""
    if not regions or structure is None or not structure.groupes:
        return []
    w, h = taille
    marge = int(marge_frac * max(w, h))
    voulus = set(groupes) if groupes else None
    boites: dict[int, list[int]] = {}
    for k, r in enumerate(regions):
        g = structure.groupes[k] if k < len(structure.groupes) else 1
        if voulus is not None and g not in voulus:
            continue
        x0, y0, x1, y1 = r.bbox
        b = boites.get(g)
        if b is None:
            boites[g] = [x0, y0, x1, y1]
        else:
            b[0], b[1] = min(b[0], x0), min(b[1], y0)
            b[2], b[3] = max(b[2], x1), max(b[3], y1)
    return [(max(0, b[0] - marge), max(0, b[1] - marge),
             min(w, b[2] + marge), min(h, b[3] + marge))
            for _g, b in sorted(boites.items())]


def taux(structures: list[Structure | None]) -> dict:
    """Distribution des types, des groupes et des locuteurs sur un ensemble de planches.

    Publié par `tools/banc.py --traduction`. C'est le garde-fou du classifieur : un
    classifieur qui type tout est suspect, et sans cette mesure personne ne le verrait."""
    compte = {t: 0 for t in TYPES}
    bulles = etiquetees = planches_annotees = planches_repli = 0
    groupes_par_planche: list[int] = []
    for s in structures:
        if s is None:
            continue
        bulles += len(s)
        for t in s.types:
            compte[t] = compte.get(t, 0) + 1
        etiquetees += sum(1 for v in s.locuteurs if v)
        planches_annotees += 1 if s.annotee() else 0
        planches_repli += 1 if s.repli_ordre else 0
        if len(s):
            groupes_par_planche.append(s.n_groupes)
    return {"bulles": bulles, "types": compte, "etiquetees": etiquetees,
            "planches_annotees": planches_annotees, "planches_repli": planches_repli,
            "groupes_par_planche": groupes_par_planche}
