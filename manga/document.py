# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Document de planche — l'état en mémoire, l'historique, et **un seul Enregistrer**.

## Ce que ça change

Jusqu'ici chaque geste de l'éditeur écrivait immédiatement : ajouter une zone réécrivait quatre
fichiers, corriger une réplique en réécrivait un cinquième. C'était honnête et sans surprise,
mais cela rendait impossible ce qu'on attend d'un éditeur — hésiter, essayer, revenir en
arrière, et ne valider qu'à la fin.

`DocumentPlanche` tient l'état en mémoire et n'écrit **rien** avant `enregistrer()`. Cela
impose un historique, et c'est le vrai coût de ce lot.

## L'historique : des instantanés, pas des inverses

Le plan prévoyait d'empiler l'**opération inverse** de chaque geste. C'est la solution
économique en mémoire, et la plus fragile : l'inverse d'une scission qui a réordonné la planche
et reporté des textes par IoU n'a rien d'évident, et un inverse faux corrompt silencieusement
un cache que l'utilisateur croit intact.

On empile donc des **instantanés**, en s'appuyant sur une propriété que le code tient déjà :
**aucun masque n'est jamais muté en place**. `_rendre_disjoints`, `masque_de_forme` et
`scinder_zone` construisent tous des tableaux neufs. Un instantané peut donc partager les
masques par référence et ne copier que les listes et les dictionnaires — quelques kilo-octets
par pas, au lieu des ~30 Mo qu'une copie profonde des masques pleine page coûterait.

## Le cœur pur, partagé avec `manga/edition.py`

`poser_regions` calcule le nouvel état sans toucher au disque : réordonnancement, appariement
par IoU, report de l'OCR, de la traduction, des corrections manuelles et des origines. C'est
exactement ce que faisait `_reecrire`, dont il est extrait — même raison que pour
`manga/rendu.py` : deux implémentations de la même règle finiraient par diverger, et celle-ci
décide de ce qui est conservé ou perdu.

## L'enregistrement vérifie la révision

`projet.json` porte un entier qui n'augmente que si le contenu change. Le document retient
celui de son ouverture et le revérifie avant d'écrire : un run qui aurait retouché la planche
entre-temps fait **refuser** l'écriture plutôt qu'écraser. C'est l'`expected_revision` que la
docstring de `manga/projet.py` annonçait.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from . import checkpoints, detection_retry
from . import ocr as ocr_mod
from .detection import BubbleRegion

# Profondeur de l'historique. Au-delà, le premier pas est oublié : un instantané ne coûte que
# quelques kilo-octets (les masques sont partagés), mais une session d'édition n'a pas besoin
# de remonter à l'ouverture — et une pile sans bornes finit par mentir sur son coût.
PROFONDEUR_HISTORIQUE = 60

# Seuil d'appariement, repris de `manga/edition.py` : c'est la même règle.
SEUIL_REPORT = 0.30


class ErreurDocument(Exception):
    """Écriture impossible — l'appelant l'affiche telle quelle."""


@dataclass
class EtatPlanche:
    """Tout ce qu'une planche porte d'éditable, en mémoire.

    ⚠ `regions` et les listes de textes s'alignent **par position**. C'est l'invariant central
    de toute la brique ; chaque opération le rétablit avant de rendre la main."""

    regions: list[BubbleRegion] = field(default_factory=list)
    ocr: list[str] = field(default_factory=list)
    traduction: list[str] = field(default_factory=list)
    manuelles: dict[int, str] = field(default_factory=dict)
    origines: dict[int, str] = field(default_factory=dict)
    mises_en_page: dict[int, dict] = field(default_factory=dict)
    taille: tuple[int, int] | None = None

    def instantane(self) -> "EtatPlanche":
        """Copie SUPERFICIELLE, sûre parce qu'aucun masque n'est muté en place.

        Copier les tableaux de masques donnerait ~30 Mo par pas d'historique sur une planche de
        1440×2048 ; les partager est gratuit et exact, tant que les opérations construisent des
        régions neuves — ce qu'elles font toutes."""
        return EtatPlanche(
            regions=list(self.regions), ocr=list(self.ocr),
            traduction=list(self.traduction), manuelles=dict(self.manuelles),
            origines=dict(self.origines),
            mises_en_page={k: dict(v) for k, v in self.mises_en_page.items()},
            taille=self.taille)


# ─────────────────────────────────────────────────────────────────────────────
# Lecture / écriture
# ─────────────────────────────────────────────────────────────────────────────

def lire_etat(ckpt_dir: Path) -> EtatPlanche:
    """Charge l'état d'une planche depuis son cache. Lève si la détection manque."""
    regions = checkpoints.load_regions(ckpt_dir)
    taille = checkpoints.taille_image(ckpt_dir)
    if regions is None or taille is None:
        raise ErreurDocument(
            f"aucune détection exploitable dans {ckpt_dir} — la planche n'a pas encore été "
            f"détectée, ou son cache est dans un format périmé.")
    n = len(regions)
    return EtatPlanche(
        regions=regions,
        ocr=_ajuster(checkpoints.load_ocr(ckpt_dir) or [], n),
        traduction=_ajuster(checkpoints.load_traduction(ckpt_dir) or [], n),
        manuelles=checkpoints.load_traduction_manuelle(ckpt_dir),
        origines=checkpoints.load_origines(ckpt_dir),
        mises_en_page=checkpoints.load_mise_en_page(ckpt_dir),
        taille=taille)


def ecrire_etat(ckpt_dir: Path, etat: EtatPlanche, *, motif: str = "edition_manuelle",
                regions_changees: bool = True) -> None:
    """Écrit TOUT l'état. Les dictionnaires vides suppriment leur fichier.

    `regions_changees=False` épargne la réécriture de `regions.json` + `masks.png` (le PNG
    d'étiquettes pleine page) quand seuls des textes ont bougé — c'est le cas le plus fréquent
    d'une session d'édition, et le seul écrit coûteux du lot."""
    ckpt_dir = Path(ckpt_dir)
    if regions_changees:
        checkpoints.save_regions(ckpt_dir, etat.regions, etat.taille,
                                 detection={"motif": motif})
    checkpoints.save_ocr(ckpt_dir, etat.ocr)
    checkpoints.save_traduction(ckpt_dir, etat.traduction)
    checkpoints.save_traduction_manuelle(ckpt_dir, etat.manuelles)
    checkpoints.save_origines(ckpt_dir, etat.origines)
    checkpoints.save_mise_en_page(ckpt_dir, etat.mises_en_page)
    # `qa.json` décrit le RENDU précédent : après une édition il ne décrit plus rien.
    (ckpt_dir / checkpoints.QA_FILENAME).unlink(missing_ok=True)


def _ajuster(textes: list[str], n: int) -> list[str]:
    """Aligne une liste de textes sur `n` bulles — complétée ou tronquée.

    Un cache plus court que ses régions existe (une traduction partielle, un run interrompu) ;
    le laisser court ferait lever à la première lecture indexée."""
    return (list(textes) + [""] * n)[:n]


# ─────────────────────────────────────────────────────────────────────────────
# Le cœur pur — partagé avec `manga/edition.py`
# ─────────────────────────────────────────────────────────────────────────────

def rendre_disjoints(regions: list[BubbleRegion]) -> tuple[list[BubbleRegion], list[int]]:
    """Retire de chaque masque les pixels déjà pris par une région précédente.

    Renvoie `(régions, index d'origine)`. Le second terme n'est pas une commodité : une région
    entièrement recouverte DISPARAÎT, et sans lui les index décaleraient silencieusement.

    Sans cette passe, `masks.png` mentirait : c'est une image d'étiquettes, le dernier masque
    écrit gagne, et la région recouverte reviendrait amputée au rechargement."""
    pris = None
    sorties: list[BubbleRegion] = []
    origines: list[int] = []
    for k, r in enumerate(regions):
        mask = r.mask if pris is None else (r.mask & ~pris)
        if not mask.any():
            continue
        pris = mask if pris is None else (pris | mask)
        sorties.append(replace(r, bbox=_bbox_du_masque(mask), mask=mask))
        origines.append(k)
    return sorties, origines


def _bbox_du_masque(mask) -> tuple[int, int, int, int]:
    import numpy as np
    lignes = np.flatnonzero(mask.any(axis=1))
    colonnes = np.flatnonzero(mask.any(axis=0))
    if not lignes.size or not colonnes.size:
        raise ErreurDocument("masque vide : aucune boîte englobante")
    return (int(colonnes[0]), int(lignes[0]), int(colonnes[-1]) + 1, int(lignes[-1]) + 1)


def poser_regions(etat: EtatPlanche, nouvelles: list[BubbleRegion],
                  touchees: set[int], *, relire: bool = True) -> tuple[EtatPlanche, dict]:
    """Nouvel état après un changement de régions. **Pur : ne touche pas au disque.**

    `touchees` est indexé sur `nouvelles` AVANT réordonnancement : ce sont les zones que
    l'opération vient de créer ou de modifier, donc celles dont l'OCR ne vaut plus rien même
    si l'appariement leur trouve une ancêtre.

    `relire=False` les conserve malgré tout, et c'est ce qui sépare **retailler** de
    **redessiner** : agrandir une bulle de quelques pixels pour mieux l'ajuster au ballon ne
    change pas ce qui y est écrit, et refaire payer l'OCR — voire la traduction — à chaque
    ajustement rendrait le geste inutilisable. L'appariement par IoU reste seul juge : une
    zone traînée sur une AUTRE bulle tombe sous `SEUIL_REPORT` et perd son texte de toute
    façon.

    ⚠ `touchees` garde son second rôle dans les deux cas : c'est lui qui porte la garde « la
    zone tracée est entièrement contenue dans une bulle déjà détectée ». Passer `touchees=set()`
    pour conserver les textes aurait donc désarmé cette garde — d'où un paramètre séparé.

    ⚠ Ce n'est pas `invalider_textes`. Le réflexe du pipeline devant un changement du nombre de
    régions est de supprimer OCR et traduction de toute la planche — juste pour une
    re-détection, ruineux pour une retouche : ajouter une bulle oubliée sur une planche qui en
    compte sept jetterait les six autres. D'où l'appariement par IoU, qui rend à chaque bulle
    restée la même son texte, sa correction manuelle **et** son origine, même quand l'ordre de
    lecture a changé."""
    disjointes, origines = rendre_disjoints(nouvelles)
    if not disjointes:
        raise ErreurDocument("l'opération ne laisserait aucune bulle sur la planche")
    if len(disjointes) > 255:
        # `masks.png` est en mode "L" : au-delà, deux bulles partageraient une étiquette.
        raise ErreurDocument(
            f"{len(disjointes)} bulles : le format d'étiquettes en supporte 255")

    survivantes = set(origines)
    if any(k not in survivantes for k in touchees):
        raise ErreurDocument(
            "la zone tracée est entièrement contenue dans une bulle déjà détectée — elle "
            "n'aurait aucun pixel à elle. Redessine-la à côté, ou scinde la bulle existante.")

    marquees = {id(disjointes[origines.index(k)]) for k in touchees}
    ordonnees = ocr_mod.reading_order(disjointes)
    touchees_finales = {i for i, r in enumerate(ordonnees) if id(r) in marquees}

    # Appariement glouton par IoU décroissante : une bulle « conservée » est la MÊME bulle,
    # pas une bulle au même endroit.
    vers_ancien = detection_retry.apparier(ordonnees, etat.regions, seuil=SEUIL_REPORT)

    neuf = EtatPlanche(regions=ordonnees, taille=etat.taille)
    a_relire: list[int] = []
    conserves = 0
    for i in range(len(ordonnees)):
        j = vers_ancien[i]
        neuve = j is None or (relire and i in touchees_finales)
        if neuve:
            neuf.ocr.append("")
            neuf.traduction.append("")
            a_relire.append(i)
            continue
        conserves += 1
        neuf.ocr.append(etat.ocr[j] if j < len(etat.ocr) else "")
        neuf.traduction.append(etat.traduction[j] if j < len(etat.traduction) else "")
        # Les clés de `traduction_manuelle.json`, `origines.json` et `mise_en_page.json` sont
        # des index de bulle : sans ce remappage, une correction écrite à la main pointerait la
        # mauvaise réplique dès que l'ordre de lecture bouge.
        if j in etat.manuelles:
            neuf.manuelles[i] = etat.manuelles[j]
        if j in etat.origines:
            neuf.origines[i] = etat.origines[j]
        if j in etat.mises_en_page:
            neuf.mises_en_page[i] = dict(etat.mises_en_page[j])

    # ⚠ `indices_touches` n'est PAS `indices_a_relire`. Avec `relire=False` le second est vide
    # alors que les pixels ont bel et bien bougé — et c'est de celui-là que `edition._reecrire`
    # tire les zones à repeindre dans `pages_clean/`. Sans cette clé, retailler une bulle
    # laisserait la planche nettoyée en désaccord avec son masque : du japonais réapparaissant
    # sur les bords gagnés, un aplat blanc sur les bords perdus.
    return neuf, {"regions": len(ordonnees), "indices_a_relire": a_relire,
                  "indices_a_retraduire": list(a_relire), "textes_conserves": conserves,
                  "corrections_conservees": len(neuf.manuelles),
                  "indices_touches": sorted(touchees_finales)}


# ─────────────────────────────────────────────────────────────────────────────
# Le document
# ─────────────────────────────────────────────────────────────────────────────

class DocumentPlanche:
    """État éditable d'une planche, avec historique. **N'écrit rien avant `enregistrer()`.**"""

    def __init__(self, ckpt_dir: Path, etat: EtatPlanche, *, revision: int = 0):
        self.ckpt_dir = Path(ckpt_dir)
        self.etat = etat
        self.revision_ouverte = revision
        self._passe: list[EtatPlanche] = []
        self._futur: list[EtatPlanche] = []
        self._modifie = False
        # Vrai dès qu'une opération a changé les RÉGIONS : sinon l'enregistrement épargne la
        # réécriture de `masks.png`, qui est un PNG pleine page.
        self._regions_changees = False

    @classmethod
    def ouvrir(cls, ckpt_dir: Path, *, revision: int = 0) -> "DocumentPlanche":
        return cls(ckpt_dir, lire_etat(ckpt_dir), revision=revision)

    # ------------------------------------------------------------------ #

    @property
    def modifie(self) -> bool:
        return self._modifie

    @property
    def peut_annuler(self) -> bool:
        return bool(self._passe)

    @property
    def peut_refaire(self) -> bool:
        return bool(self._futur)

    def _avant_operation(self, *, regions: bool = False) -> None:
        self._passe.append(self.etat.instantane())
        if len(self._passe) > PROFONDEUR_HISTORIQUE:
            self._passe.pop(0)
        # Refaire n'a plus de sens dès qu'on repart dans une autre direction — c'est la règle
        # de tous les éditeurs, et l'ignorer laisserait rejouer un pas incompatible.
        self._futur.clear()
        self._modifie = True
        self._regions_changees = self._regions_changees or regions

    # ------------------------------------------------------------------ #
    # Opérations
    # ------------------------------------------------------------------ #

    def poser_regions(self, nouvelles: list[BubbleRegion], touchees: set[int], *,
                      relire: bool = True) -> dict:
        """Remplace le jeu de régions. Le rapport rendu est celui de `poser_regions`."""
        neuf, rapport = poser_regions(self.etat, nouvelles, touchees, relire=relire)
        self._avant_operation(regions=True)
        self.etat = neuf
        return rapport

    def poser_traduction(self, index: int, texte: str) -> None:
        """Écrit la sortie du MODÈLE. Réservé à une retraduction, pas à une saisie."""
        self._verifier_index(index)
        self._avant_operation()
        self.etat.traduction = list(self.etat.traduction)
        self.etat.traduction[index] = texte
        self.etat.origines = {**self.etat.origines, index: checkpoints.ORIGINE_EDITEUR}

    def poser_ocr(self, index: int, texte: str) -> None:
        self._verifier_index(index)
        self._avant_operation()
        self.etat.ocr = list(self.etat.ocr)
        self.etat.ocr[index] = texte
        self.etat.origines = {**self.etat.origines, index: checkpoints.ORIGINE_EDITEUR}

    def poser_correction(self, index: int, texte: str | None) -> None:
        """Saisie au clavier. `None` rend la bulle au modèle.

        ⚠ Va dans `traduction_manuelle.json`, jamais dans `traduction.json` — c'est ce qui la
        fait survivre à un `--from traduction` ultérieur."""
        self._verifier_index(index)
        self._avant_operation()
        manuelles = dict(self.etat.manuelles)
        if texte is None:
            manuelles.pop(index, None)
        else:
            manuelles[index] = texte
        self.etat.manuelles = manuelles

    def poser_mise_en_page(self, index: int, entree: dict | None) -> None:
        """Position imposée d'un bloc de texte. `None` la rend au moteur de mise en page."""
        self._verifier_index(index)
        self._avant_operation()
        mises = {k: dict(v) for k, v in self.etat.mises_en_page.items()}
        if entree is None:
            mises.pop(index, None)
        else:
            mises[index] = dict(entree)
        self.etat.mises_en_page = mises

    def _verifier_index(self, index: int) -> None:
        if not (0 <= index < len(self.etat.regions)):
            raise ErreurDocument(
                f"bulle {index} inconnue : la planche en compte {len(self.etat.regions)}")

    # ------------------------------------------------------------------ #
    # Historique
    # ------------------------------------------------------------------ #

    def annuler(self) -> bool:
        if not self._passe:
            return False
        self._futur.append(self.etat.instantane())
        self.etat = self._passe.pop()
        # ⚠ `modifie` ne redevient PAS faux en remontant à l'état initial : le document a pu
        # être enregistré entre-temps, et prétendre qu'il n'y a rien à écrire ferait perdre
        # l'annulation elle-même. Un enregistrement est le seul événement qui remet à zéro.
        self._modifie = True
        return True

    def refaire(self) -> bool:
        if not self._futur:
            return False
        self._passe.append(self.etat.instantane())
        self.etat = self._futur.pop()
        self._modifie = True
        return True

    # ------------------------------------------------------------------ #
    # Enregistrement
    # ------------------------------------------------------------------ #

    def enregistrer(self, *, revision_actuelle: int | None = None) -> None:
        """Écrit tout l'état sur disque, après contrôle de fraîcheur.

        ⚠ `revision_actuelle` vient de `projet.json` et doit être relue JUSTE AVANT l'appel :
        un run qui aurait retouché la planche pendant la session d'édition l'aurait fait
        avancer, et écraser serait perdre son travail sans le dire."""
        if revision_actuelle is not None and revision_actuelle != self.revision_ouverte:
            raise ErreurDocument(
                f"la planche a changé sur le disque depuis son ouverture "
                f"(révision {self.revision_ouverte} → {revision_actuelle}). Recharge-la, puis "
                f"refais ta modification — écraser ferait perdre ce qu'un run vient d'écrire.")
        ecrire_etat(self.ckpt_dir, self.etat, regions_changees=self._regions_changees)
        self._modifie = False
        self._regions_changees = False
        if revision_actuelle is not None:
            self.revision_ouverte = revision_actuelle

    def marquer_modifie(self) -> None:
        """Déclare l'état différent du disque sans passer par une opération d'édition.

        Sert à la **reprise d'un brouillon** (`manga/recuperation.py`) : l'état vient du
        miroir, il diffère donc du disque par construction, mais aucune opération ne l'a
        produit dans CETTE session. Sans cela, le document repris passerait pour à jour et
        « Enregistrer » n'écrirait rien — on retrouverait son travail à l'écran pour le
        reperdre au premier rechargement."""
        self._modifie = True

    def abandonner(self) -> None:
        """Relit le disque et jette tout ce qui n'a pas été enregistré."""
        self.etat = lire_etat(self.ckpt_dir)
        self._passe.clear()
        self._futur.clear()
        self._modifie = False
        self._regions_changees = False
