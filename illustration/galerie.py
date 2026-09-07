# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Garder, jeter, et ne rien perdre** — plus ce que tout cela pèse sur le disque.

`PLAN-27` L27.3 et L27.5. Trois règles, et la troisième est celle qui coûte le plus cher à
oublier.

## 1. Garder DÉPLACE, et l'endroit change de nature

    build/<Projet>/illustrations/            ← candidates, régénérables par contrat
        rejetees/                            ← jetées, JAMAIS supprimées
    sources/<Projet>/illustrations/          ← RETENUES, ce qu'un humain a choisi

⚠ **`build/` est régénérable par contrat**, `.gitignore` l'écrit : « Sorties de traduction
(régénérables : `python run.py` / `run_manga.py`) ». Une image produite en 103,7 s de GPU et
retenue par un humain **n'est pas régénérable** — la même graine sur un autre modèle, ou sur
la même révision de ComfyUI un mois plus tard, ne rendra pas la même image ; le lot 24 l'a
mesuré et l'a écrit dans `orchestrateur.rejouer` : « la plupart des backends de diffusion ne
sont pas déterministes d'une exécution à l'autre ».

Un `rm -r build/` — que le dépôt **recommande lui-même** après un MAJEUR — détruirait donc le
travail de sélection. Les images retenues vont sous `sources/`, qui survit à cette
suppression, reste exclu de git en bloc, et qui est déjà là que vit le travail écrit à la main
(les glossaires, la bible). C'est aussi ce qui donne un sens fort à « je garde ».

## 2. Rien n'est jamais réécrit, et rien n'est jamais supprimé sans qu'on le demande

Le dépôt a déjà ce contrat, écrit noir sur blanc pour l'édition : « Garder ma version » retient
la réplique dans `traduction_manuelle.json` et « le pipeline ne la réécrira jamais ». Transposé
ici :

- un nom de fichier qui existe déjà obtient un **suffixe**, jamais un écrasement (`nom_libre`) ;
- **jeter** déplace dans `rejetees/`, ne supprime pas — un rejet est une donnée, le `PLAN-25`
  L25.4 en a besoin pour mesurer ;
- **purger** existe, c'est un geste séparé, explicite, et il dit combien il va détruire avant.

## 3. Une image générée ne peut pas devenir une référence, et c'est un test

⚠ **C'est le point le plus important du lot.** Reboucler une sortie dans l'entrée fait dériver
le personnage à chaque tour, et la dérive est invisible image par image — c'est seulement au
cinquième tour qu'on s'aperçoit que ce n'est plus la même personne.

Le rebouclage est rendu **impossible par trois mécanismes indépendants**, dont aucun ne repose
sur la discipline de l'appelant :

1. `inscrire` écrit sous `images_generees[]`, une clé **distincte** de `references[]` ;
   `core/bible.py:CHAMPS_PERSONNAGE` la déclare, et `illustration/identite.references_de` ne
   lit que `references[]` — la sortie n'a aucun chemin vers l'entrée ;
2. `selection._refuser_les_generees` écarte, avec un motif nommé, toute candidate qui vit sous
   un dossier `illustrations/` **ou** qui porte le marquage AI Act dans son PNG. Les images
   retenues vivent sous `sources/<Projet>/illustrations/` : les deux signes s'appliquent ;
3. `inscrire` **refuse** d'écrire un fichier dans `references[]` : la fonction n'a pas
   d'argument pour ça, et un test vérifie qu'après un aller-retour complet — générer, garder,
   inscrire, relire la bible — la liste des candidates d'identité est inchangée.

## Ce que la frontière NE garde PAS ici, et pourquoi c'est dit

`illustration/frontiere.py` arme un périmètre d'écriture pendant la **génération**. Il n'est
**pas** armé autour de `garder` ni de `jeter`, et ce n'est pas un oubli : le garde refuse toute
écriture de fichier image hors du seul chemin qui pose le marquage AI Act
(`marquage.ecrire`). Un `shutil.move` d'un `.png` déjà marqué lèverait donc `ImageNonMarquee`
— alors qu'il ne produit aucune image, il en déplace une.

La propriété qui compte reste vraie par un autre chemin, et il est plus étroit que le
périmètre : **ces trois fonctions ne prennent pour cible que des chemins que l'appelant leur
donne**, et les deux appelants du dépôt — `gui/atelier.py` et `run_illustration.py --garder` —
les prennent de `orchestrateur.dossier`, `dossier_retenues` et `dossier_rejetees`, qui sont
les trois seuls dossiers de la brique. Aucune de ces fonctions ne **crée** de contenu : elle
déplace ou elle supprime. La limite est écrite ici plutôt que passée sous silence.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from illustration import marquage

#: Sous-dossier des images jetées. **Sous `build/`**, avec les candidates : une image rejetée
#: n'est pas un travail de sélection à préserver, c'est une donnée de mesure.
NOM_REJETEES = "rejetees"

#: Les états d'une image dans la galerie, et ils sont exclusifs.
CANDIDATE = "candidate"
RETENUE = "retenue"
REJETEE = "rejetee"

LIBELLES = {
    CANDIDATE: "candidate — dans build/, régénérable, effacée par un `rm -r build/`",
    RETENUE: "retenue — dans sources/, survit à la suppression de build/",
    REJETEE: "rejetée — conservée, jamais supprimée sans un geste explicite",
}


class GesteImpossible(RuntimeError):
    """Un déplacement demandé ne peut pas avoir lieu, et le motif est nommé."""


# ─────────────────────────────────  L'inventaire  ─────────────────────────────────

@dataclass(frozen=True)
class Piece:
    """Une image de la galerie, et ce que son sidecar en dit."""

    chemin: Path
    etat: str
    octets: int = 0
    personnage: str = ""
    graine: object = None
    cadrage: str = ""
    secondes: float = 0.0
    date: str = ""
    #: Les trois grandeurs du lot 25, quand elles ont été mesurées.
    grandeurs: dict = field(default_factory=dict)
    verdict: dict = field(default_factory=dict)
    #: `False` quand le sidecar manque — l'image est alors **suspecte**, pas utilisable.
    manifeste: Path | None = None

    @property
    def marquee(self) -> bool:
        """Une image sans son manifeste n'est pas une image de cette brique.

        ⚠ Elle n'est pas supprimée pour autant : elle est **signalée**. Effacer un fichier
        qu'on ne comprend pas est le contraire de ce que ce module fait."""
        return self.manifeste is not None


@dataclass(frozen=True)
class Inventaire:
    """Ce que la galerie pèse, par état. **Avec les octets, pas seulement les comptes.**"""

    pieces: tuple = ()

    def par_etat(self, etat: str) -> tuple:
        return tuple(p for p in self.pieces if p.etat == etat)

    def compte(self, etat: str = "") -> int:
        return len(self.par_etat(etat) if etat else self.pieces)

    def octets(self, etat: str = "") -> int:
        return sum(p.octets for p in (self.par_etat(etat) if etat else self.pieces))

    def sans_manifeste(self) -> tuple:
        return tuple(p for p in self.pieces if not p.marquee)

    def resume(self) -> list:
        """Les lignes de l'écran et de la commande. Chaque compte porte son poids."""
        lignes = []
        for etat in (RETENUE, CANDIDATE, REJETEE):
            lignes.append(f"{self.compte(etat):>4} {etat:<10} {octets_lisibles(self.octets(etat)):>10}"
                          f"   {LIBELLES[etat]}")
        lignes.append(f"{self.compte():>4} {'total':<10} {octets_lisibles(self.octets()):>10}")
        orphelines = self.sans_manifeste()
        if orphelines:
            lignes.append(f"  ⚠ {len(orphelines)} image(s) sans manifeste de provenance : "
                          f"elles ne viennent pas de cette brique, ou leur sidecar a été "
                          f"perdu. Elles sont comptées, elles ne sont pas touchées.")
        return lignes


def inventorier(candidates, retenues=None) -> Inventaire:
    """Ce que la galerie contient. **Ne modifie rien, ne crée aucun dossier.**"""
    pieces: list[Piece] = []
    candidates = Path(candidates) if candidates else None
    if candidates is not None:
        pieces += _pieces(candidates, CANDIDATE, recursif=False)
        pieces += _pieces(candidates / NOM_REJETEES, REJETEE, recursif=False)
    if retenues:
        pieces += _pieces(Path(retenues), RETENUE, recursif=False)
    return Inventaire(pieces=tuple(sorted(pieces, key=lambda p: (p.etat, p.chemin.name))))


def _pieces(dossier: Path, etat: str, *, recursif: bool) -> list:
    if not dossier.is_dir():
        return []
    motif = "**/*.png" if recursif else "*.png"
    sorties = []
    for chemin in sorted(dossier.glob(motif)):
        if not chemin.is_file():
            continue
        sorties.append(_piece(chemin, etat))
    return sorties


def _piece(chemin: Path, etat: str) -> Piece:
    manifeste = marquage.manifeste_de(chemin)
    donnees: dict = {}
    if manifeste.is_file():
        try:
            donnees = json.loads(manifeste.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            donnees = {}
    else:
        manifeste = None
    payload = donnees.get("payload") or {}
    source = donnees.get("prompt_source") or {}
    identite = donnees.get("identite") or {}
    try:
        octets = chemin.stat().st_size
    except OSError:
        octets = 0
    return Piece(
        chemin=chemin, etat=etat, octets=octets,
        personnage=str(source.get("personnage") or ""),
        graine=payload.get("graine"),
        cadrage=str(source.get("cadrage") or ""),
        secondes=float(donnees.get("secondes") or 0.0),
        date=str(donnees.get("date") or ""),
        grandeurs=dict(identite.get("grandeurs") or {}),
        verdict=dict(identite.get("verdict") or {}),
        manifeste=manifeste)


def verdicts(piece: Piece) -> list:
    """Les **trois** verdicts d'une image, en phrases — et le descripteur qui décroche.

    ⚠ **Critère 4 de L27.1, et il porte sur la LISIBILITÉ, pas sur la mesure** : « le verdict
    de style porte le descripteur qui décroche, pas un score nu : *saturation 2,4× la
    signature du tome* se comprend, *style 0,63* ne se comprend pas ».

    Cette fonction ne calcule **rien** : `illustration/juge.py` a déjà tout mesuré et archivé
    dans le sidecar (`descripteur_decroche`, `meme_regime_couleur`). Elle met des mots autour.
    Elle vit ici et non dans `gui/` parce qu'elle décide de ce qui s'affiche, et que la règle
    de couche du dépôt veut que « tout ce qui décide se teste sans Qt » — la console peut
    d'ailleurs l'utiliser telle quelle.

    ⚠ Une grandeur absente est dite **non mesurée**, jamais montrée comme un zéro. Un cosinus
    de 0 est une mesure (« aucun rapport ») ; une absence de référence n'en est pas une."""
    grandeurs = piece.grandeurs or {}
    if not grandeurs:
        return ["ressemblance / nouveauté / style : non mesurées "
                "(illustration.identite.actif: false, ou aucun encodeur déclaré)"]
    lignes = []
    for cle, libelle in (("ressemblance", "ressemblance"), ("nouveaute", "nouveauté")):
        valeur = grandeurs.get(cle)
        lignes.append(f"{libelle} : {valeur:.3f}" if valeur is not None
                      else f"{libelle} : non mesurée")
    decroche = grandeurs.get("descripteur_decroche") or []
    nom_decroche = str(decroche[0]) if decroche else ""
    if nom_decroche:
        lignes.append(f"style : « {nom_decroche} » décroche de "
                      f"{abs(float(decroche[1] or 0.0)):.2f} par rapport à la signature du "
                      f"tome")
    elif grandeurs.get("style_descripteurs") is not None:
        lignes.append(f"style : écart moyen {float(grandeurs['style_descripteurs']):.3f} aux "
                      f"descripteurs du tome")
    else:
        lignes.append("style : non mesuré")
    if grandeurs.get("meme_regime_couleur") is False:
        lignes.append("⚠ régime de COULEUR différent de celui du tome")
    marques = (piece.verdict or {}).get("marques") or {}
    if marques:
        lignes.append(" · ".join(f"[{c} : {v}]" for c, v in marques.items()))
    return lignes


def octets_lisibles(octets: int) -> str:
    """« 2,4 Go ». Base 1000, comme partout ailleurs dans le dépôt (`--check` des poids)."""
    valeur = float(max(0, int(octets)))
    for unite in ("o", "ko", "Mo", "Go"):
        if valeur < 1000 or unite == "Go":
            return f"{valeur:.1f} {unite}" if unite != "o" else f"{valeur:.0f} o"
        valeur /= 1000.0
    return f"{valeur:.1f} Go"


# ─────────────────────────────────  Les gestes  ─────────────────────────────────

def nom_libre(cible) -> Path:
    """Un chemin qui n'existe pas, dérivé de `cible` par un suffixe numérique.

    `portrait.png` → `portrait-2.png` → `portrait-3.png`. **Jamais d'écrasement** : le dépôt
    tient déjà ce contrat pour l'édition manuelle, et une image de 103,7 s de GPU écrasée par
    une homonyme est exactement la perte qu'il refuse ailleurs.

    ⚠ Le suffixe tient compte du **manifeste** autant que de l'image : un `x-2.png` libre dont
    le `x-2.png.provenance.json` existe encore désignerait une paire incohérente."""
    cible = Path(cible)
    if not cible.exists() and not marquage.manifeste_de(cible).exists():
        return cible
    tige, suffixe = cible.stem, cible.suffix
    for index in range(2, 10_000):
        candidat = cible.with_name(f"{tige}-{index}{suffixe}")
        if not candidat.exists() and not marquage.manifeste_de(candidat).exists():
            return candidat
    raise GesteImpossible(
        f"impossible de trouver un nom libre à côté de {cible.name} après 9 998 essais — "
        f"il y a probablement autre chose à régler que le nommage.")


def garder(image, destination) -> tuple:
    """Déplace l'image **et son manifeste** vers l'emplacement pérenne. Rend `(image, manifeste)`.

    ⚠ **L'image et son sidecar voyagent ensemble, toujours.** Une image sans provenance ne
    peut plus dire qui a validé son prompt ni avec quelles références elle a été faite : elle
    perdrait précisément ce qui la rend défendable. Si le manifeste manque, le geste **lève**
    plutôt que de produire une image orpheline dans le dossier des images retenues."""
    image = Path(image)
    destination = Path(destination)
    if not image.is_file():
        raise GesteImpossible(f"{image} n'existe pas — rien à garder.")
    manifeste = marquage.manifeste_de(image)
    if not manifeste.is_file():
        raise GesteImpossible(
            f"{image.name} n'a pas de manifeste de provenance ({manifeste.name}).\n"
            f"  Une image gardée sans son sidecar ne peut plus dire qui a validé son prompt, "
            f"avec quel modèle ni depuis quelles références. Le dépôt refuse de ranger dans "
            f"« retenues » une image dont il ne peut rien dire.")
    destination.mkdir(parents=True, exist_ok=True)
    cible = nom_libre(destination / image.name)
    shutil.move(str(image), str(cible))
    shutil.move(str(manifeste), str(marquage.manifeste_de(cible)))
    _suivre_le_graphe(image, cible)
    return cible, marquage.manifeste_de(cible)


def jeter(image, dossier_rejetees=None) -> tuple:
    """Déplace vers `rejetees/`. **Ne supprime pas** — un rejet est une donnée (L25.4).

    Le manifeste suit s'il existe ; ici son absence n'est pas bloquante, contrairement à
    `garder` : on ne prétend rien d'une image qu'on écarte."""
    image = Path(image)
    if not image.is_file():
        raise GesteImpossible(f"{image} n'existe pas — rien à jeter.")
    dossier = Path(dossier_rejetees) if dossier_rejetees else image.parent / NOM_REJETEES
    dossier.mkdir(parents=True, exist_ok=True)
    cible = nom_libre(dossier / image.name)
    shutil.move(str(image), str(cible))
    _suivre_le_graphe(image, cible)
    manifeste = marquage.manifeste_de(image)
    if manifeste.is_file():
        shutil.move(str(manifeste), str(marquage.manifeste_de(cible)))
        return cible, marquage.manifeste_de(cible)
    return cible, None


def _suivre_le_graphe(source, cible) -> None:
    """Le graphe envoyé (L28.3) voyage avec son image, comme le manifeste.

    ⚠ Son absence n'est **pas** bloquante, contrairement à celle du manifeste : le moteur
    factice n'en produit aucun, et les images d'avant la 2.22.0 n'en ont pas. Une image sans
    graphe reste défendable — elle porte son payload ; une image sans manifeste, non."""
    graphe = marquage.graphe_de(source)
    if graphe.is_file():
        shutil.move(str(graphe), str(marquage.graphe_de(cible)))


def purger(dossier_rejetees) -> tuple:
    """Supprime les images rejetées. Rend `(nombre, octets libérés)`.

    ⚠ **Un geste séparé, explicite, et il n'est jamais appelé par un autre.** L'appelant a
    demandé confirmation en annonçant ce que `poids_a_purger` a chiffré."""
    dossier = Path(dossier_rejetees)
    if not dossier.is_dir():
        return 0, 0
    nombre, octets = 0, 0
    for chemin in sorted(dossier.glob("*.png")):
        manifeste = marquage.manifeste_de(chemin)
        graphe = marquage.graphe_de(chemin)
        try:
            octets += chemin.stat().st_size
            chemin.unlink()
            nombre += 1
            if manifeste.is_file():
                octets += manifeste.stat().st_size
                manifeste.unlink()
            if graphe.is_file():
                octets += graphe.stat().st_size
                graphe.unlink()
        except OSError:
            continue
    return nombre, octets


def poids_a_purger(dossier_rejetees) -> tuple:
    """Ce qu'une purge détruirait, **avant** de le détruire. `(nombre, octets)`."""
    dossier = Path(dossier_rejetees)
    if not dossier.is_dir():
        return 0, 0
    pieces = _pieces(dossier, REJETEE, recursif=False)
    octets = sum(p.octets for p in pieces)
    octets += sum(p.manifeste.stat().st_size for p in pieces
                  if p.manifeste is not None and p.manifeste.is_file())
    return len(pieces), octets


# ────────────────────  La bible : une SORTIE, jamais une entrée  ────────────────────

#: La clé, et elle est **distincte** de `references[]`. Voir §3 de la docstring du module.
CLE_GENEREES = "images_generees"


def inscrire(bible_doc: dict, personnage: str, image, *, manifeste=None,
             cadrage: str = "", par: str = "") -> tuple:
    """Note dans la bible qu'une image a été **produite** pour ce personnage.

    Rend `(bible modifiée, nombre d'inscriptions)`. **N'écrit rien sur le disque** : l'appelant
    décide, comme `atelier.promouvoir`.

    ⚠ **Sous `images_generees[]`, jamais sous `references[]`**, et cette fonction n'a aucun
    argument qui permettrait l'inverse. Une image générée qui deviendrait la référence de la
    génération suivante ferait dériver le personnage à chaque tour, et la dérive est invisible
    image par image.

    ⚠ Le chemin inscrit est **relatif au projet quand il peut l'être** : une bible qui
    porterait `C:/Users/…` ne se relirait pas sur une autre machine, alors que `bible.yaml`
    est fait pour durer."""
    from core import bible as bible_mod

    nom = str(personnage or "").strip()
    image = Path(image)
    if not nom:
        raise GesteImpossible(
            "aucun personnage n'est nommé : une image produite depuis une description "
            "personnalisée n'appartient à personne dans la bible, et l'y inscrire sous un "
            "nom inventé serait pire que de ne pas l'inscrire.")
    copie = bible_mod.fill_defaults(bible_doc)
    entree = bible_mod.entree(copie, nom)
    if entree is None:
        raise GesteImpossible(
            f"« {nom} » n'est pas dans la bible visuelle : on n'y inscrit pas une image "
            f"produite pour quelqu'un qui n'y est pas.")
    liste = entree.setdefault(CLE_GENEREES, [])
    fichier = image.name
    if any(str(e.get("fichier") or "") == fichier for e in liste if isinstance(e, dict)):
        return copie, 0
    liste.append({
        "fichier": fichier,
        "cadrage": str(cadrage or ""),
        "gardee_par": str(par or ""),
        "manifeste": Path(manifeste).name if manifeste else "",
        # ⚠ Écrit dans le fichier, pas seulement dans le code : quelqu'un qui lit la bible
        # six mois plus tard doit savoir pourquoi cette liste est à part.
        "note": ("image PRODUITE par la brique d'illustration — jamais candidate au "
                 "conditionnement d'une génération suivante (PLAN-27 L27.3)"),
    })
    return copie, 1


def generees_de(bible_doc: dict, personnage: str) -> list:
    """Les images produites notées pour ce personnage. Lecture seule, pour l'écran."""
    from core import bible as bible_mod

    entree = bible_mod.entree(bible_mod.fill_defaults(bible_doc), str(personnage or ""))
    if entree is None:
        return []
    return [dict(e) for e in (entree.get(CLE_GENEREES) or []) if isinstance(e, dict)]


# ────────────────────────  Ce que tout cela pèse, et il faut le dire  ────────────────────────

#: Poids d'un PNG produit, en octets. **Mesuré, pas estimé** : les onze images du run réel du
#: 2026-08-29 (1328 × 1328, RVB, sans transparence) pèsent de 1,4 à 3,1 Mo, médiane 2,1 Mo.
#: Le sidecar de provenance ajoute 3 à 6 ko — négligeable, et compté quand même.
OCTETS_PAR_IMAGE = 2_100_000
OCTETS_PAR_MANIFESTE = 5_000


def poids_estime(personnages: int, images_par_personnage: int = 8) -> int:
    """Ce qu'un projet pèserait, en octets. Le calcul que le plan demande de publier.

    ⚠ **Ce n'est pas hypothétique.** `manga D` déclare **119 personnages** (chiffre
    réel du corpus, relevé le 2026-08-27 avec les 171 personnages des cinq projets à
    glossaire vivant). À 8 images par personnage et 2,1 Mo l'image, cela fait **2,0 Go** — et
    3,0 Go si l'on retient les 3,1 Mo du pire cas mesuré. C'est pour ce chiffre-là que la
    commande d'inventaire et la purge existent."""
    unites = max(0, int(personnages)) * max(0, int(images_par_personnage))
    return unites * (OCTETS_PAR_IMAGE + OCTETS_PAR_MANIFESTE)


def calcul_du_poids(personnages: int = 119, images_par_personnage: int = 8) -> list:
    """Le calcul, écrit en toutes lettres — pour le document du lot et pour `--check`."""
    total = poids_estime(personnages, images_par_personnage)
    return [
        f"{personnages} personnages × {images_par_personnage} images = "
        f"{personnages * images_par_personnage} PNG",
        f"{octets_lisibles(OCTETS_PAR_IMAGE)} par PNG (médiane mesurée sur 11 images "
        f"1328 × 1328 du run du 2026-08-29 ; de 1,4 à 3,1 Mo) "
        f"+ {octets_lisibles(OCTETS_PAR_MANIFESTE)} de sidecar",
        f"→ {octets_lisibles(total)} pour l'œuvre entière, "
        f"{octets_lisibles(poids_estime(personnages, images_par_personnage) * 3100 // 2100)} "
        f"au pire cas mesuré",
        "Les images RETENUES vivent sous sources/ : elles survivent à `rm -r build/`, donc "
        "elles ne se libèrent que par un geste explicite.",
    ]
