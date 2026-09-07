# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Points de reprise PAR ÉTAGE pour un tome manga : chaque page peut être reprise ou
relancée indépendamment à n'importe quelle étape — détection, nettoyage, OCR,
traduction, rendu — sans refaire les étapes précédentes (déjà en cache sur disque).
Miroir manga du système de checkpoints du LN (`pipeline/control.py` gère l'arrêt
propre ; ici on ajoute la granularité PAR ÉTAGE, propre au découpage manga).

Structure sous build/<Projet>/<Tome>/manga/ :
    pages_clean/page_XXXX.png     — page nettoyée (bulles vidées, SANS texte) :
                                     VISIBLE et directement consultable/réutilisable
                                     (dossier normal, pas un fichier caché).
    pages_out/page_XXXX.png       — page finale (texte français réinjecté).
    .checkpoints/page_XXXX/
        regions.json               — bbox/score/classe/genre de chaque bulle détectée
        masks.png                  — image d'étiquettes (0=fond, i+1=bulle i), même
                                      taille que la page — reconstruit les masques
        ocr.json                   — texte japonais OCR par bulle (ordre de lecture)
        traduction.json            — texte français par bulle (même ordre)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from . import quality_manga
from .detection import BubbleRegion

# Ordre d'EXÉCUTION des étapes. `rendu` n'a pas de fichier de cache dédié — sa sortie EST
# la page finale (pages_out/), déjà testée séparément par l'appelant (process_volume) avant
# d'atteindre cette étape.
STAGES = ["detection", "nettoyage", "ocr", "terminologie", "traduction", "sfx", "rendu"]

# Étapes dont un cache ABSENT ne périme rien. Deux cas, pour deux raisons différentes :
#
# · `rendu` n'a pas de cache propre (sa sortie est la page finale) ;
# · `terminologie` (lot 3) écrit dans le glossaire de l'ŒUVRE, pas dans le cache de la page.
#   Son fichier ne sert qu'à ne pas repayer l'appel LLM. Un cache absent ne veut donc pas dire
#   « la traduction de cette page est périmée » — la traduction lit le glossaire sur disque,
#   quel que soit ce qui a tourné dans cette session. Sans cette exception, activer l'agent
#   `terminologue` ferait RETRADUIRE les 150 planches d'un tome déjà fini, et pire : un tome
#   traduit sans terminologue verrait `--from nettoyage` déclencher la retraduction complète,
#   parce que `terminologie.txt` n'existerait nulle part. Pour (re)lancer la terminologie sur
#   un tome déjà traduit, c'est `--from terminologie` — explicite, comme il se doit.
#
# · `sfx` (lot 9) est dans le même cas que `terminologie`, pour une raison de plus : les deux
#   tomes déjà traduits n'ont AUCUN `sfx.json`. Si son absence périmait `rendu`, activer la
#   passe suffirait — mais si elle périmait quoi que ce soit d'AUTRE, elle rejouerait des
#   étages payés en GPU. Elle ne dépend que de `detection` et ne nourrit que `rendu`, lequel
#   est de toute façon toujours refait ; c'est donc l'orchestrateur qui décide de la lancer
#   (feature active, et cache absent ou `--from sfx`), pas le graphe.
CACHE_NON_BLOQUANT = frozenset({"rendu", "terminologie", "sfx"})


# ⚠ L'ordre d'exécution ci-dessus n'est PAS un ordre de dépendance : les étapes forment un
# graphe, pas une chaîne. `ocr` lit l'image D'ORIGINE et les régions — jamais la page
# nettoyée (cf. `read_all(image, regions)` dans l'orchestrateur). `nettoyage` et `ocr` sont
# donc des FRÈRES, tous deux issus de `detection` seule :
#
#     detection ──┬── nettoyage ─────────────────────────┐
#                 └── ocr ── terminologie ── traduction ─┴── rendu
#
# Le traiter comme une chaîne coûtait cher : `--from nettoyage` réinvalidait l'OCR
# (5,6 s/page) et la traduction (9,7 s/page, avec appels LLM), soit ~38 minutes sur un tome
# de 150 planches pour un résultat identique au bit près.
#
# `terminologie` (lot 3) s'insère entre `ocr` et `traduction` : il lit le japonais OCR et
# enrichit le glossaire de l'œuvre, que le traducteur reçoit ensuite en contexte. Refaire la
# terminologie peut donc changer une traduction — mais pas le nettoyage.
# `sfx` (texte SUR LE DESSIN, lot 9) est un TROISIÈME frère de `detection` : il relit la
# planche d'origine et les masques de bulles — pour écarter le texte déjà pris en charge par
# un ballon — et n'alimente que le rendu. Il ne touche donc ni l'OCR des bulles, ni la
# traduction de planche, ni la terminologie :
#
#     detection ──┬── nettoyage ─────────────────────────┐
#                 ├── ocr ── terminologie ── traduction ─┤
#                 └── sfx ───────────────────────────────┴── rendu
_DEPENDANTS: dict[str, tuple[str, ...]] = {
    "detection": ("nettoyage", "ocr", "sfx"),
    "nettoyage": ("rendu",),
    "ocr": ("terminologie",),
    "terminologie": ("traduction",),
    "traduction": ("rendu",),
    "sfx": ("rendu",),
    "rendu": (),
}


def stage_index(name: str) -> int:
    return STAGES.index(name)


def downstream(stage: str) -> set[str]:
    """`stage` et tout ce qui en dépend, transitivement — l'ensemble des étapes qu'il faut
    refaire quand la sortie de `stage` change.

    `downstream("nettoyage")` vaut `{"nettoyage", "rendu"}` : refaire le nettoyage ne change
    rien à l'OCR ni à la traduction."""
    if stage not in _DEPENDANTS:
        raise KeyError(f"étape inconnue : {stage!r} (attendu : {', '.join(STAGES)})")
    vus: set[str] = set()
    a_voir = [stage]
    while a_voir:
        s = a_voir.pop()
        if s in vus:
            continue
        vus.add(s)
        a_voir.extend(_DEPENDANTS[s])
    return vus


def stage_cache_present(ckpt_dir: Path, clean_path: Path) -> dict[str, bool]:
    """Présence du cache de CHAQUE étape, indépendamment les unes des autres.

    Dit l'état de CHAQUE étape, au lieu de s'arrêter à la première absence — information
    nécessaire dès lors que les étapes ne sont plus une chaîne. `rendu` n'a pas de cache
    propre, et l'absence de celui de `terminologie` ne périme rien (cf.
    `CACHE_NON_BLOQUANT`)."""
    return {
        "detection": load_regions(ckpt_dir) is not None,
        "nettoyage": Path(clean_path).exists(),
        "ocr": load_ocr(ckpt_dir) is not None,
        "terminologie": load_terminologie(ckpt_dir) is not None,
        "traduction": load_traduction(ckpt_dir) is not None,
        "sfx": load_sfx(ckpt_dir) is not None,
        "rendu": False,
    }


def stages_to_redo(ckpt_dir: Path, clean_path: Path, *, force: bool = False,
                   restart_from: str | None = None) -> set[str]:
    """Étapes à (re)calculer pour une page, en combinant trois causes :

    · `force` — tout refaire, cache ignoré ;
    · `restart_from` — l'étape demandée et tout ce qui en dépend ;
    · **cache absent** — l'étape manquante et tout ce qui en dépend (une étape dont l'entrée
      est recalculée doit l'être aussi : refaire `detection` change les régions, donc
      `nettoyage` et `ocr` ne sont plus valides même si leurs fichiers existent).

    `rendu` est toujours présent dans le résultat : il n'a pas de cache propre, et une page
    déjà entièrement générée est écartée en amont par l'appelant."""
    if force:
        return set(STAGES)
    a_refaire: set[str] = {"rendu"}
    if restart_from:
        a_refaire |= downstream(restart_from)
    for etape, present in stage_cache_present(ckpt_dir, clean_path).items():
        if not present and etape not in CACHE_NON_BLOQUANT:
            a_refaire |= downstream(etape)
    return a_refaire


def page_checkpoint_dir(build_dir: Path, page_index: int) -> Path:
    return Path(build_dir) / ".checkpoints" / f"page_{page_index:04d}"


def clean_page_path(build_dir: Path, page_index: int) -> Path:
    return Path(build_dir) / "pages_clean" / f"page_{page_index:04d}.png"


def final_page_path(build_dir: Path, page_index: int) -> Path:
    return Path(build_dir) / "pages_out" / f"page_{page_index:04d}.png"


def psd_page_path(build_dir: Path, page_index: int) -> Path:
    """PSD à calques d'une planche — un dossier VISIBLE, comme `pages_clean/`, parce qu'il est
    fait pour être ouvert à la main dans Photoshop."""
    return Path(build_dir) / "pages_psd" / f"page_{page_index:04d}.psd"


# Version du format de `regions.json`.
#   v1 — liste NUE de bulles, dans l'ordre de lecture calculé par agrégation par
#        chevauchement vertical sur toute la largeur de la page ;
#   v2 — objet `{format, image_size, regions}`, ordre calculé par coupe X-Y récursive ;
#   v3 — les régions **bi-lobées** (deux ballons pris pour un par le détecteur) sont scindées
#        avant l'ordre de lecture, cf. `manga/bubbles_split.py`.
#
# ⚠ L'ordre persisté ici est le pivot de tout le reste : `ocr.json` et `traduction.json`
# s'y alignent PAR POSITION. Changer l'ordre sans rien faire ferait donc atterrir les
# traductions dans les mauvaises bulles — silencieusement.
#
# v2→v3 est la première migration qui peut changer le NOMBRE de bulles d'une page. Quand c'est
# le cas, l'alignement par position est irrécupérable et les textes de cette page sont
# supprimés — c'est le seul endroit du projet qui jette du travail déjà payé, et c'est assumé :
# la région fusionnée portait deux répliques dans une seule chaîne, elle était fausse.
FORMAT_VERSION = 3


# ─────────────────────────────────────────────────────────────────────────────
# LE PLAFOND DE L'IMAGE D'ÉTIQUETTES (lot 14, L6.3)
#
# `masks.png` et `sfx_masks.png` sont des images d'ÉTIQUETTES : 0 = fond, i+1 = région i.
# Un seul PNG par planche plutôt qu'un masque par bulle — c'est ce qui rend le cache lisible
# d'un coup d'œil et petit sur le disque.
#
# ⚠ Le format portait une limite que RIEN n'annonçait. Le tableau était en `uint8` : au-delà
# de 255 régions, `label[r.mask] = i` **enroule** — la 256ᵉ bulle s'écrit avec l'étiquette 0,
# donc en fond, et la 257ᵉ prend celle de la première. Deux bulles partagent alors un masque,
# et rien, nulle part, ne le dit. La docstring de `save_regions` annonçait la limite de
# *chevauchement* et pas celle du *nombre*.
#
# ## Ce que la mesure dit, et ce qu'elle ne dit pas
#
# Sur les **1 513 planches** des dix volumes de `build/`, le maximum est de **17 régions**
# (manga A Vol.4 p61) et de **9 zones hors bulle** (manga C Family Vol.1 p102). Sur la seule
# bande
# de webtoon du corpus — 1080×10 000 px, soit six planches paginées — le maximum est **16**.
# Le plafond n'est donc jamais approché, pas même de loin, et l'idée reçue selon laquelle le
# webtoon le ferait sauter est **fausse** : les plateformes découpent les chapitres en bandes
# de 10 000 px, pas en une image unique.
#
# Ce n'est donc pas un blocage de format. C'est un défaut de ROBUSTESSE, et il vaut d'être
# corrigé pour une seule raison : l'enroulement est **silencieux**, ce qui est le pire des
# trois comportements possibles (refuser, avertir, mentir).
#
# ## Pourquoi PAS un passage inconditionnel en uint16
#
# Le plan du lot proposait `uint16` avec une migration de tous les caches. Mesure faite, ce
# serait payer très cher un problème qui n'existe pas : réécrire 1 513 `masks.png` — et
# risquer l'invalidation d'un cache de détection, donc des heures de GPU — pour une marge dont
# quinze seizièmes ne servent à personne.
#
# La largeur est donc choisie **par planche, sur le nombre de régions** :
#
#   ≤ 255 régions   → `uint8`, mode "L"      — le format d'aujourd'hui, au bit près.
#   ≤ 65 535        → `uint16`, mode "I;16"  — écrit UNIQUEMENT là où le premier déborderait.
#   au-delà         → une erreur qui NOMME la planche et le nombre.
#
# La lecture n'a rien à apprendre : `label == i` se comporte de la même façon quelle que soit
# la largeur du tableau. Aucun cache existant ne change, aucune migration n'est nécessaire, et
# `FORMAT_VERSION` ne bouge pas — ce serait déclencher `downstream("detection")` sur tous les
# projets pour un octet que personne n'écrit.
PLAFOND_ETIQUETTES_8 = 255
PLAFOND_ETIQUETTES = 65535


class ErreurEtiquettes(ValueError):
    """Trop de régions pour une image d'étiquettes. Message destiné à l'utilisateur."""


def image_etiquettes(regions, largeur: int, hauteur: int, *, ou: str = "") -> Image.Image:
    """Image d'étiquettes des masques de `regions` : 0 = fond, i+1 = région i.

    ⚠ Suppose des régions NON chevauchantes — c'est le travail de
    `document.rendre_disjoints`, et le contrat est le même qu'avant : un pixel partagé par
    deux masques est attribué à la dernière région écrite.

    `ou` nomme la planche dans le message d'erreur. Un « trop de régions » sans planche
    n'aide personne à trouver laquelle."""
    n = len(regions)
    if n > PLAFOND_ETIQUETTES:
        raise ErreurEtiquettes(
            f"{n} régions{' sur ' + ou if ou else ''} : le format d'étiquettes de "
            f"`masks.png` en supporte {PLAFOND_ETIQUETTES}. Au-delà, deux régions "
            f"partageraient une étiquette — donc un masque.")
    label = np.zeros((hauteur, largeur),
                     dtype=np.uint8 if n <= PLAFOND_ETIQUETTES_8 else np.uint16)
    for i, r in enumerate(regions, start=1):
        label[r.mask] = i
    return Image.fromarray(label)


# ─────────────────────────────────────────────────────────────────────────────
# ÉCRITURE ATOMIQUE
#
# ⚠ Tout ce qui écrit un fichier de cache passe par ici, et c'est la seule règle qui compte
# dans ce module. Un `write_text` direct laisse un JSON TRONQUÉ si le processus meurt au
# milieu — Ctrl+C, coupure, ou une collision de synchro OneDrive, le dépôt y vivant.
#
# Et un cache tronqué est INDÉTECTABLE : `stage_cache_present` ne teste que l'EXISTENCE du
# fichier. Un `ocr.json` à moitié écrit n'est donc jamais replanifié par `stages_to_redo`,
# jamais supprimé, et fait échouer la planche à CHAQUE run suivant — indéfiniment. Seul un
# `--from ocr`, que rien ne suggère à l'utilisateur, la réparait.
#
# `os.replace` est atomique sur NTFS comme sur POSIX : le fichier de destination est soit
# l'ancien intact, soit le nouveau complet, jamais un entre-deux. Le temporaire est écrit
# DANS le dossier de destination — un `%TEMP%` sur un autre volume ferait retomber
# `os.replace` sur une copie, qui n'est plus atomique.
# Prévenu quand un fichier de cache se révèle illisible. Une fonction remplaçable plutôt
# qu'un `print` en dur : ce module est appelé depuis le CLI, depuis la GUI et depuis les
# tests, et chacun journalise autrement. Le défaut écrit sur stderr — jamais rien, ce serait
# pire que l'exception qu'on vient de supprimer : un recalcul silencieux ne laisse aucune
# trace de la corruption qui l'a causé.
#
# ⚠ On PRÉVIENT, on ne supprime pas. Un `OSError` peut être un verrou OneDrive passager sur
# un fichier parfaitement sain ; l'effacer détruirait du travail déjà payé pour un incident
# qui se résout tout seul. Le recalcul réécrit de toute façon le fichier fautif.
def _prevenir_cache_abime(chemin: Path) -> None:
    """Signale un fichier de cache illisible, dont l'étage va donc être recalculé."""
    print(f"[cache] {chemin} est illisible — l'étage sera recalculé.", file=sys.stderr)


def _ecrire_atomique(chemin: Path, contenu: str) -> None:
    """Écrit du texte par temporaire + `os.replace`. Cf. le commentaire ci-dessus."""
    chemin = Path(chemin)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_text(contenu, encoding="utf-8")
    os.replace(tmp, chemin)


def _ecrire_image_atomique(image: Image.Image, chemin: Path) -> None:
    """Même garantie pour un PNG. `masks.png` est aussi indispensable que `regions.json` :
    `_lire_regions_brut` exige les DEUX, et un PNG tronqué ferait lever `Image.open`."""
    chemin = Path(chemin)
    tmp = chemin.with_name(chemin.name + ".tmp.png")
    image.save(tmp)
    os.replace(tmp, chemin)


def _lire_regions_brut(ckpt_dir: Path) -> tuple[list[BubbleRegion], int, tuple[int, int]] | None:
    """Lit `regions.json` + `masks.png` QUEL QUE SOIT le format, et renvoie
    `(regions, version, image_size)`. Sert à la lecture normale comme à la migration."""
    meta_path, mask_path = Path(ckpt_dir) / "regions.json", Path(ckpt_dir) / "masks.png"
    if not (meta_path.exists() and mask_path.exists()):
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        label = np.asarray(Image.open(mask_path))
    except (json.JSONDecodeError, OSError, ValueError):
        # Cache ABÎMÉ, pas absent. On répond comme pour un cache absent — `None` « fait
        # naturellement recalculer la page », dit la docstring de `load_regions`, et c'est
        # exactement la sémantique voulue ici. Lever, à l'inverse, condamnait la planche à
        # vie : `stage_cache_present` ne voit qu'un fichier présent et ne replanifie donc
        # jamais l'étage, et rien n'efface le fichier fautif.
        _prevenir_cache_abime(meta_path)
        return None
    if isinstance(data, list):          # lecture tolérante : liste nue = v1
        version, meta = 1, data
    else:
        version, meta = int(data.get("format", 0)), data.get("regions", [])
    h, w = label.shape[:2]
    regions = [
        BubbleRegion(bbox=tuple(m["bbox"]), mask=(label == i), score=m["score"],
                     cls=m["cls"], kind=m.get("kind", "bulle"),
                     scindee=bool(m.get("scindee", False)))
        for i, m in enumerate(meta, start=1)
    ]
    return regions, version, (w, h)


def save_regions(ckpt_dir: Path, regions: list[BubbleRegion], image_size: tuple[int, int],
                 *, detection: dict | None = None, sens: str | None = None) -> None:
    """Sauvegarde bbox/score/classe/genre (JSON) + une image d'ÉTIQUETTES combinant
    tous les masques (0=fond, i+1=bulle i) — un seul PNG plutôt qu'un masque par
    bulle. Suppose des bulles NON chevauchantes (quasi toujours vrai en pratique) :
    un pixel partagé par deux masques serait attribué à la dernière bulle écrite.

    `detection` est un bloc de PROVENANCE optionnel (`conf_threshold`, `iou_threshold`,
    `motif`) : sans lui, une planche relancée à d'autres seuils est indistinguable des 149
    autres, et le réglage qui a donné le bon résultat est perdu au run suivant.

    `sens` est le SENS DE LECTURE qui a produit cet ordre (`droite_gauche` /
    `gauche_droite`). Il n'est pas décoratif : c'est ce qui permet à `sens_perime()` de
    n'invalider que les pages réellement concernées quand le format d'un tome change.

    ⚠ Omettre `sens` **préserve** celui déjà enregistré, il ne l'efface pas. Les appelants qui
    réécrivent des régions sans connaître le format du tome — édition manuelle
    (`manga/document.py`), migration de cache — passeraient sinon une page de webtoon pour
    du manga, et la feraient re-détecter au run suivant pour rien.

    > ⚠ **Ne PAS incrémenter `FORMAT_VERSION` pour ces champs.** `load_regions` renvoie
    > `None` sur écart de version, ce qui déclencherait `downstream("detection")` — soit la
    > retraduction des 150 planches, sur TOUS les projets existants. La version encode le
    > contrat de *nombre et d'ordre* auquel `ocr.json`/`traduction.json` s'alignent par
    > position ; un champ de provenance n'y touche pas, et un lecteur ancien l'ignore
    > simplement."""
    ckpt_dir = Path(ckpt_dir)
    # Lu AVANT l'écriture : le fichier qu'on s'apprête à remplacer porte la réponse.
    sens_garde = sens or _sens_brut(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    w, h = image_size
    meta = [{"bbox": list(r.bbox), "score": r.score, "cls": r.cls, "kind": r.kind,
             "scindee": bool(r.scindee)} for r in regions]
    # ⚠ Le PLAFOND est vérifié ICI, sur le chemin du pipeline. Il ne l'était que sur celui de
    # l'édition manuelle (`document.poser_regions`) — c'est-à-dire sur le seul des trois
    # chemins où l'utilisateur voit ce qui se passe. Cf. `image_etiquettes`.
    _ecrire_image_atomique(image_etiquettes(regions, w, h, ou=str(ckpt_dir.name)),
                           ckpt_dir / "masks.png")
    charge: dict = {"format": FORMAT_VERSION, "image_size": [w, h], "regions": meta}
    if detection:
        charge["detection"] = dict(detection)
    if sens_garde:
        charge["sens"] = str(sens_garde)
    _ecrire_atomique(ckpt_dir / "regions.json",
                     json.dumps(charge, ensure_ascii=False, indent=1))


def _sens_brut(ckpt_dir: Path) -> str | None:
    """Sens tel qu'il est ÉCRIT, ou `None` s'il ne l'est pas — sans le défaut historique.

    Distinct de `sens_enregistre` : celui-ci répond « je ne sais pas », ce qu'il faut pour
    ne pas inventer un champ qui n'existait pas."""
    p = Path(ckpt_dir) / "regions.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return str(data.get("sens")) if isinstance(data, dict) and data.get("sens") else None


#: Sens supposé d'un cache écrit AVANT que le champ n'existe. Tout ce qui a été rendu
#: jusqu'ici était du manga droite→gauche : c'est le seul défaut qui ne réinvalide rien.
SENS_HISTORIQUE = "droite_gauche"


def sens_enregistre(ckpt_dir: Path) -> str:
    """Sens de lecture qui a produit l'ordre en cache."""
    p = Path(ckpt_dir) / "regions.json"
    if not p.exists():
        return SENS_HISTORIQUE
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return SENS_HISTORIQUE
    if not isinstance(data, dict):
        return SENS_HISTORIQUE
    return str(data.get("sens") or SENS_HISTORIQUE)


def sens_perime(ckpt_dir: Path, sens: str) -> bool:
    """L'ordre en cache a-t-il été calculé dans un AUTRE sens que celui demandé ?

    Un tome basculé de `manga` à `webtoon` (ou l'inverse) doit re-numéroter ses bulles, sinon
    les répliques traduites restent rattachées aux bulles de l'ancien ordre — un mélange
    silencieux, exactement l'échec que `reading_order` décrit. Mais une page dont le sens n'a
    PAS changé ne doit rien perdre : c'est ce que ce test cible, plutôt qu'un incrément de
    `FORMAT_VERSION` qui invaliderait tous les projets."""
    p = Path(ckpt_dir) / "regions.json"
    return p.exists() and sens_enregistre(ckpt_dir) != str(sens)


def load_detection_meta(ckpt_dir: Path) -> dict:
    """Bloc de provenance de la détection (seuils, motif), ou `{}` s'il n'y en a pas.

    Absent de la quasi-totalité des pages : il n'est écrit que par une relance ciblée."""
    p = Path(ckpt_dir) / "regions.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return dict(data.get("detection") or {}) if isinstance(data, dict) else {}


def invalider_textes(ckpt_dir: Path) -> list[str]:
    """Supprime `ocr.json`, `traduction.json`, `structure.json` et `qa.json`. Renvoie les noms
    supprimés.

    À appeler dès qu'une opération **change le nombre de régions** d'une page : l'alignement
    par position est alors irrécupérable, et `stage_cache_present` teste la PRÉSENCE d'un
    fichier, pas sa longueur — une page relancée garderait donc un OCR de l'ancien découpage,
    silencieusement décalé.

    ⚠ `structure.json` est dans la liste **parce qu'il est aligné par position lui aussi**
    (lot 15). Une scission qui fait passer une bulle bi-lobée à deux lobes décalerait sinon
    les types et les locuteurs d'un rang, et le décalage serait invisible : la structure n'est
    jamais dessinée, elle est seulement lue par le prompt.

    `terminologie.txt` est délibérément épargné : c'est un cache NON BLOQUANT, du texte libre
    qui n'est aligné sur rien. C'est aussi ce qui garde le coût d'une relance de détection à
    un seul appel LLM au lieu de deux."""
    supprimes = []
    for nom in (OCR_FILENAME, TRADUCTION_FILENAME, STRUCTURE_FILENAME, QA_FILENAME):
        chemin = Path(ckpt_dir) / nom
        if chemin.exists():
            chemin.unlink()
            supprimes.append(nom)
    return supprimes


def load_regions(ckpt_dir: Path) -> list[BubbleRegion] | None:
    """Régions dans l'ordre de lecture persisté, ou `None` si le cache est absent **ou
    dans un format périmé** (ce qui fait naturellement recalculer la page).

    Un checkpoint v1 non migré renvoie donc `None` : mieux vaut recalculer que servir un
    ordre qui ne correspond plus à celui des textes. `migrate_page()` évite ce recalcul."""
    lu = _lire_regions_brut(ckpt_dir)
    if lu is None:
        return None
    regions, version, _taille = lu
    return regions if version == FORMAT_VERSION else None


def taille_image(ckpt_dir: Path) -> tuple[int, int] | None:
    """Taille `(largeur, hauteur)` de la planche, telle que la détection l'a vue.

    Ajoutée pour `manga/edition.py`, qui doit fabriquer des masques de la BONNE taille sans
    rouvrir l'image : un masque d'une taille différente ferait échouer `save_regions` à
    l'écriture du PNG d'étiquettes, ou pire, décalerait les régions."""
    lu = _lire_regions_brut(ckpt_dir)
    return None if lu is None else lu[2]


def checkpoint_format(ckpt_dir: Path) -> int | None:
    """Version du format de cette page, ou `None` s'il n'y a pas de cache de régions."""
    lu = _lire_regions_brut(ckpt_dir)
    return None if lu is None else lu[1]


def migrate_page(ckpt_dir: Path, reorder, scinder) -> str | None:
    """Migre un checkpoint vers `FORMAT_VERSION` **en recalculant le moins possible**.

    Le plan du lot 1 prévoyait de simplement invalider les checkpoints v1. Ce n'était pas
    nécessaire, et c'était cher : sur un tome déjà traité, invalider `detection` entraîne
    par le graphe de dépendances le nettoyage, l'OCR (5,6 s/page) **et la traduction**
    (9,7 s/page, appels LLM) — des heures de GPU, et le modèle ONNX à nouveau requis.

    **v1 → v2 : seul l'ORDRE change.** Les bbox, les masques, les scores et les textes sont
    tous encore valides. Il suffit de recalculer l'ordre, d'en déduire la **permutation**, et
    de l'appliquer aussi à `ocr.json` et `traduction.json` pour que l'alignement par position
    reste vrai. L'opération est exacte.

    **v2 → v3 : les régions bi-lobées sont scindées.** C'est un post-traitement de masques,
    donc faisable **sans le modèle ONNX** — un tome se migre sans avoir à re-détecter. Mais
    quand une page gagne des bulles, `ocr.json`, `traduction.json` et `qa.json` ne s'alignent
    plus : ils sont **supprimés**, ce qui fait naturellement reprendre cette page à l'OCR par
    le graphe de dépendances (`downstream("ocr")`). Les pages sans région scindée gardent
    tout.

    `reorder` (ordre de lecture) et `scinder` (scission bi-lobée) sont **injectés** pour ne pas
    faire dépendre ce module de `manga.ocr` ni de `manga.bubbles_split`. `scinder` reçoit la
    liste de régions et renvoie `(régions, diagnostics)`.

    Renvoie un résumé de ce qui a été fait, ou `None` si la page n'avait rien à migrer."""
    lu = _lire_regions_brut(ckpt_dir)
    if lu is None:
        return None
    regions, version, taille = lu
    if version == FORMAT_VERSION:
        return None
    if not regions:
        save_regions(ckpt_dir, [], taille)
        return "aucune bulle"

    etapes: list[str] = []

    if version < 2:
        nouveau = list(reorder(regions))
        positions = {id(r): i for i, r in enumerate(regions)}
        perm = [positions[id(r)] for r in nouveau]
        if sorted(perm) != list(range(len(regions))):
            # L'ordre n'est pas une permutation des mêmes objets : on ne prend pas le risque
            # de désaligner les textes, on laisse la page se recalculer.
            return None
        deplacees = sum(1 for j, p in enumerate(perm) if j != p)
        for charger, sauver in ((load_ocr, save_ocr), (load_traduction, save_traduction)):
            textes = charger(ckpt_dir)
            if textes is not None and len(textes) == len(regions):
                sauver(ckpt_dir, [textes[p] for p in perm])
        regions = nouveau
        etapes.append(f"{len(regions)} bulle(s), {deplacees} déplacée(s)")

    if version < 3:
        scindees, _diag = scinder(regions)
        gagnees = len(scindees) - len(regions)
        if gagnees:
            # Re-trier : deux lobes issus d'une même région ne sont pas forcément voisins
            # dans l'ordre de lecture (l'un peut appartenir à la case du dessus).
            regions = list(reorder(scindees))
            invalider_textes(ckpt_dir)
            etapes.append(f"+{gagnees} bulle(s) scindée(s), OCR et traduction à refaire")
        else:
            etapes.append("aucune bulle bi-lobée")

    save_regions(ckpt_dir, regions, taille)
    return f"v{version}→v{FORMAT_VERSION} : " + " ; ".join(etapes)


# Noms de fichiers du cache d'une page. Nommés parce que `migrate_page` doit pouvoir en
# SUPPRIMER quand une scission change le nombre de bulles : un littéral répété à deux endroits
# dont l'un efface des fichiers est exactement le genre de dérive qu'on ne voit pas passer.
OCR_FILENAME = "ocr.json"
TRADUCTION_FILENAME = "traduction.json"
QA_FILENAME = "qa.json"        # écrit par `report_manga.save_page_qa`, qui le relit d'ici


def _save_texts(ckpt_dir: Path, filename: str, texts: list[str]) -> None:
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(ckpt_dir / filename, json.dumps(texts, ensure_ascii=False, indent=1))


def _load_texts(ckpt_dir: Path, filename: str) -> list[str] | None:
    """Textes en cache, ou `None` si le fichier est absent **ou illisible**.

    ⚠ Le second cas n'est pas théorique et il n'est pas bénin. `stage_cache_present` ne teste
    que l'EXISTENCE : un `ocr.json` tronqué n'est jamais replanifié par `stages_to_redo`, si
    bien qu'une exception ici rendait la planche définitivement perdue — et, appelée depuis
    `_passe_terminologie` / `_passe_contexte`, elle remonte HORS du filet par planche et tue
    le tome entier (le chapitre entier, en `--all`). Rendre `None` fait simplement recalculer
    l'étage, ce qui est le comportement voulu."""
    p = ckpt_dir / filename
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _prevenir_cache_abime(p)
        return None


#: Structure de la planche (lot 15) : groupes de mise en page, types de bulle, étiquettes de
#: locuteur. Trois listes alignées par position sur `regions.json`.
#:
#: ⚠ Fichier **additionnel et facultatif**, et c'est ce qui en fait un CORRECTIF de cache et
#: non un MAJEUR. Il n'entre ni dans `STAGES` ni dans `FORMAT_VERSION` : un cache antérieur
#: ne le porte pas, `load_structure` rend alors `None`, et le traducteur reçoit exactement
#: l'énoncé qu'il recevait avant. Aucune planche n'est réinvalidée, aucun tome n'est
#: retraduit.
STRUCTURE_FILENAME = "structure.json"


def save_structure(ckpt_dir: Path, charge: dict) -> None:
    """Écrit la structure d'une planche. Sert au prompt du run en cours ET au banc.

    ⚠ Persistée plutôt que recalculée à la demande, pour une raison qui n'est pas la
    performance : `tools/banc.py` doit pouvoir publier le taux d'« indéterminé » du
    classifieur **sans charger le moindre modèle ni rouvrir les masques**, comme il le fait
    déjà pour tout le reste. Un classifieur dont personne ne peut mesurer la distribution est
    un classifieur qu'on ne peut pas contredire."""
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(ckpt_dir / STRUCTURE_FILENAME,
                     json.dumps(charge, ensure_ascii=False, indent=1))


def load_structure(ckpt_dir: Path) -> dict | None:
    """Structure en cache, ou `None` — absente, illisible, ou antérieure au lot 15."""
    p = Path(ckpt_dir) / STRUCTURE_FILENAME
    if not p.exists():
        return None
    try:
        charge = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _prevenir_cache_abime(p)
        return None
    return charge if isinstance(charge, dict) else None


def save_ocr(ckpt_dir: Path, texts: list[str]) -> None:
    _save_texts(ckpt_dir, OCR_FILENAME, texts)


def load_ocr(ckpt_dir: Path) -> list[str] | None:
    return _load_texts(ckpt_dir, OCR_FILENAME)


def save_traduction(ckpt_dir: Path, texts: list[str]) -> None:
    _save_texts(ckpt_dir, TRADUCTION_FILENAME, texts)


def load_traduction(ckpt_dir: Path) -> list[str] | None:
    """Répliques françaises par bulle — **débarrassées d'un éventuel préfixe numéroté**.

    Le préfixe est retiré à la lecture, et pas seulement à l'écriture, parce que les caches
    déjà produits le contiennent : la page 129 du Vol.1 du *manga A* a 9 répliques
    persistées sous la forme « 1. L'ennemi semble être… », et le lettrage les dessinait
    telles quelles. Sans cette réparation, corriger l'analyse ne suffirait pas — il faudrait
    **retraduire** chaque planche touchée, soit un appel LLM par planche, alors qu'un simple
    `--from rendu` répare tout le tome sans en consommer un seul.

    Une réplique de bulle ne commence jamais par « 12. » : le seul producteur de cette forme
    est la liste numérotée que le prompt demande au modèle."""
    textes = _load_texts(ckpt_dir, TRADUCTION_FILENAME)
    if textes is None:
        return None
    return [quality_manga.sans_prefixe(t) for t in textes]


# Relevés du terminologue pour une page : du TEXTE, pas une liste par bulle — la sortie de
# l'agent est un bloc de notes à fusionner tel quel dans le glossaire (cf.
# `core.glossary_build.merge_notes`), exactement comme les `NNN.txt` du light novel.
TERMINOLOGIE_FILENAME = "terminologie.txt"


def save_terminologie(ckpt_dir: Path, notes: str) -> None:
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(ckpt_dir / TERMINOLOGIE_FILENAME, notes)


def load_terminologie(ckpt_dir: Path) -> str | None:
    """Notes en cache, ou `None` si l'étape n'a jamais tourné sur cette page.

    ⚠ Une chaîne VIDE est une réponse valide (« rien à signaler ») et doit rester distincte
    de `None` : sans ça, une page de pure action — sans le moindre nom propre — serait
    resoumise au LLM à chaque relance."""
    p = Path(ckpt_dir) / TERMINOLOGIE_FILENAME
    return p.read_text(encoding="utf-8") if p.exists() else None


# ─────────────────────────────────────────────────────────────────────────────
# PROVENANCE : ce que la main a écrit n'est jamais réécrit — lot 16
#
# `traduction.json` porte la sortie du modèle et le pipeline la réécrit à chaque
# `--from traduction`. Une correction faite à la main y était donc perdue au run suivant,
# silencieusement.
#
# D'où un fichier SÉPARÉ, que le pipeline ne produit jamais et n'écrase jamais. C'est la
# transposition de l'`Origin::User` de koharu, dont le pipeline saute tout ce qu'un humain a
# touché — la seule façon de rendre un re-run non destructif. Le format est un objet
# `{"index de bulle": "texte"}` : lisible et modifiable dans n'importe quel éditeur, comme le
# reste du cache de ce dépôt.
TRADUCTION_MANUELLE_FILENAME = "traduction_manuelle.json"


def load_traduction_manuelle(ckpt_dir: Path) -> dict[int, str]:
    """Corrections écrites À LA MAIN, `{index: texte}`. `{}` s'il n'y en a pas.

    Tolérante par construction : un fichier illisible ou mal formé ne doit pas arrêter un tome
    de 150 planches — il est ignoré, et le rapport dira que la planche n'a pas de correction."""
    p = Path(ckpt_dir) / TRADUCTION_MANUELLE_FILENAME
    if not p.exists():
        return {}
    try:
        brut = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(brut, dict):
        return {}
    sortie: dict[int, str] = {}
    for cle, valeur in brut.items():
        try:
            sortie[int(cle)] = "" if valeur is None else str(valeur)
        except (TypeError, ValueError):
            continue
    return sortie


def save_traduction_manuelle(ckpt_dir: Path, manuelles: dict[int, str]) -> None:
    """Écrit les corrections manuelles. **Le seul écrivain de ce fichier, et il n'est jamais
    appelé par le pipeline** — il existe pour l'éditeur graphique, qui a besoin d'écrire ce que
    la main a saisi sans passer par `traduction.json`.

    L'invariant tient à ça : `traduction.json` porte la sortie BRUTE du modèle et se fait
    réécrire à chaque `--from traduction`. Une réplique retapée qui y atterrirait serait perdue
    au run suivant. Ici elle survit à tout.

    Un dictionnaire vide **supprime** le fichier plutôt que d'écrire `{}` : « aucune
    correction » et « un fichier de corrections vide » doivent se lire pareil, et un `{}`
    résiduel ferait dire au rapport qu'une planche a été reprise à la main."""
    ckpt_dir = Path(ckpt_dir)
    chemin = ckpt_dir / TRADUCTION_MANUELLE_FILENAME
    if not manuelles:
        chemin.unlink(missing_ok=True)
        return
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    charge = {str(k): ("" if v is None else str(v)) for k, v in sorted(manuelles.items())}
    _ecrire_atomique(chemin, json.dumps(charge, ensure_ascii=False, indent=1))


# ─────────────────────────────────────────────────────────────────────────────
# ORIGINE d'une réplique — qui l'a produite
#
# `qa.json` savait dire qu'une bulle avait été RATTRAPÉE à l'unité, mais rien d'autre : une
# réplique reprise à la main ou retraduite depuis l'éditeur y était indistinguable des 943
# autres. Or ce sont précisément celles qu'on veut relire — elles n'ont pas vu le contexte de
# planche, ou elles portent une décision humaine.
#
# Même patron que `traduction_manuelle.json` : fichier SÉPARÉ, tolérant, `{index: origine}`,
# et remappé par `edition._reecrire` quand l'ordre de lecture bouge. Le pipeline l'écrit à
# `pipeline` implicitement — c'est-à-dire qu'il ne l'écrit pas du tout : une absence vaut
# « produite par le run », qui est le cas de l'immense majorité.
ORIGINES_FILENAME = "origines.json"

ORIGINE_PIPELINE = "pipeline"     # sortie d'un `process_volume` (valeur par défaut, non écrite)
ORIGINE_EDITEUR = "editeur"       # relue ou retraduite depuis l'interface, bulle par bulle
ORIGINE_MANUELLE = "manuelle"     # saisie au clavier (déduite de `traduction_manuelle.json`)


def load_origines(ckpt_dir: Path) -> dict[int, str]:
    """`{index: origine}`. `{}` s'il n'y en a pas — tolérant comme son modèle."""
    p = Path(ckpt_dir) / ORIGINES_FILENAME
    if not p.exists():
        return {}
    try:
        brut = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(brut, dict):
        return {}
    sortie: dict[int, str] = {}
    for cle, valeur in brut.items():
        try:
            sortie[int(cle)] = str(valeur)
        except (TypeError, ValueError):
            continue
    return sortie


def save_origines(ckpt_dir: Path, origines: dict[int, str]) -> None:
    """Écrit les origines. Un dictionnaire vide SUPPRIME le fichier, pour que « rien de
    particulier » et « un fichier vide » se lisent pareil."""
    ckpt_dir = Path(ckpt_dir)
    chemin = ckpt_dir / ORIGINES_FILENAME
    if not origines:
        chemin.unlink(missing_ok=True)
        return
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    _ecrire_atomique(chemin, json.dumps({str(k): v for k, v in sorted(origines.items())},
                                        ensure_ascii=False, indent=1))


def marquer_origine(ckpt_dir: Path, index: int, origine: str) -> None:
    """Note qu'une bulle vient d'ailleurs que du run. Lecture-modification-écriture : le
    fichier est minuscule et l'opération est rare (un geste d'éditeur)."""
    origines = load_origines(ckpt_dir)
    if origine == ORIGINE_PIPELINE:
        origines.pop(index, None)
    else:
        origines[index] = origine
    save_origines(ckpt_dir, origines)



# ─────────────────────────────────────────────────────────────────────────────
# MISE EN PAGE d'une bulle — la position du texte devient une donnée
#
# Jusqu'ici elle n'existait NULLE PART : `typeset_page` la recalculait à chaque rendu depuis
# le masque, et `fits_out` — la seule trace — n'était même alloué que si l'export PSD était
# actif, puis jeté. Déplacer un bloc de texte était donc impossible par construction : il n'y
# avait rien à déplacer.
#
# Même patron que `traduction_manuelle.json`, pour les mêmes raisons : fichier SÉPARÉ, jamais
# écrit par le pipeline, tolérant à un contenu abîmé, `{}` supprime. Une bulle sans entrée est
# lettrée exactement comme avant — la clé absente n'est pas « position par défaut », c'est
# « laisse le moteur chercher ».
#
# ⚠ Le rectangle enregistré sert AUSSI de masque de découpe. `typeset.calque_fit` découpe au
# `style.interior` ; un texte déplacé hors de sa bulle disparaîtrait donc silencieusement.
MISE_EN_PAGE_FILENAME = "mise_en_page.json"

# Clés reconnues d'une entrée. Une clé inconnue est ignorée plutôt que de faire échouer la
# lecture : c'est un fichier qu'on édite parfois à la main.
# ⚠ « police » a été RETIRÉE de ces deux listes. Elle y figurait, donc une entrée qui n'en
# portait qu'elle était retenue à la lecture — mais `typeset.typeset_page` ne teste que
# `rect` et `taille` avant d'appeler `fit_impose`, et `fit_impose` ne lit pas `police`.
# Le réglage était donc accepté sans un mot et sans le moindre effet. Une clé inconnue est
# ignorée (c'est la règle ci-dessus), ce qui est le même résultat en apparence — à ceci
# près qu'elle ne PROMET plus rien. Pour changer de police, c'est `manga.typeset.font_path`.
CHAMPS_MISE_EN_PAGE = ("rect", "taille", "couleur", "interligne", "ancre")


# Clés qui décrivent le LETTRAGE sans rien dire de la géométrie. Une entrée qui n'en porte
# aucune et n'a pas de `rect` ne décrit rien et sera écartée.
CHAMPS_STYLE_MISE_EN_PAGE = ("taille", "interligne", "couleur")


def load_mise_en_page(ckpt_dir: Path) -> dict[int, dict]:
    """`{index: {rect, taille, …}}`. `{}` s'il n'y en a pas.

    Une entrée est retenue si elle porte un `rect` exploitable **ou** au moins une clé de
    style. `{}` et `{"ancre": "libre"}` sont écartés : ils ne décrivent rien.

    ⚠ **Pourquoi `rect` est optionnel.** Il l'a longtemps été obligatoire, au motif que « c'est
    le rectangle qui porte à la fois la position et la découpe ». C'est vrai, et c'est
    précisément pourquoi il ne faut pas en inventer un. `typeset.style_impose` remplace
    l'intérieur de la bulle par un **rectangle plein** ; poser la bbox d'un ballon elliptique
    pour la seule raison qu'on veut changer son corps élargirait la zone d'habillage jusqu'aux
    coins, et le texte déborderait sur le contour dessiné. Une entrée sans `rect` laisse le
    style mesuré intact — le masque réel, la queue exclue — et n'impose que le corps."""
    p = Path(ckpt_dir) / MISE_EN_PAGE_FILENAME
    if not p.exists():
        return {}
    try:
        brut = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(brut, dict):
        return {}
    sortie: dict[int, dict] = {}
    for cle, valeur in brut.items():
        if not isinstance(valeur, dict):
            continue
        rect = valeur.get("rect")
        a_rect = isinstance(rect, (list, tuple)) and len(rect) == 4
        if not a_rect and not any(valeur.get(c) is not None
                                  for c in CHAMPS_STYLE_MISE_EN_PAGE):
            continue
        try:
            index = int(cle)
            entree = {k: v for k, v in valeur.items() if k in CHAMPS_MISE_EN_PAGE}
            if a_rect:
                entree["rect"] = [int(round(float(v))) for v in rect]
            else:
                entree.pop("rect", None)      # un rect abîmé ne vaut pas mieux qu'aucun
        except (TypeError, ValueError):
            continue
        sortie[index] = entree
    return sortie


def save_mise_en_page(ckpt_dir: Path, mises: dict[int, dict]) -> None:
    """Écrit les mises en page. Un dictionnaire vide SUPPRIME le fichier — « aucune position
    imposée » et « un fichier de positions vide » doivent se lire pareil."""
    ckpt_dir = Path(ckpt_dir)
    chemin = ckpt_dir / MISE_EN_PAGE_FILENAME
    if not mises:
        chemin.unlink(missing_ok=True)
        return
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    charge = {str(k): {c: v[c] for c in CHAMPS_MISE_EN_PAGE if c in v}
              for k, v in sorted(mises.items())}
    _ecrire_atomique(chemin, json.dumps(charge, ensure_ascii=False, indent=1))



def appliquer_manuelles(textes: list[str] | None,
                        manuelles: dict[int, str]) -> tuple[list[str], list[int]]:
    """Superpose les corrections manuelles. Renvoie `(textes, indices remplacés)`.

    Un index hors bornes est ignoré : le nombre de bulles peut avoir changé depuis que la
    correction a été écrite, et on préfère perdre la correction que décaler la planche."""
    sortie = list(textes or [])
    remplaces: list[int] = []
    for index, texte in sorted(manuelles.items()):
        if 0 <= index < len(sortie):
            sortie[index] = texte
            remplaces.append(index)
    return sortie, remplaces


# ─────────────────────────────────────────────────────────────────────────────
# Texte SUR LE DESSIN (onomatopées, narration libre) — lot 9
#
# ⚠ Fichiers SÉPARÉS, et c'est la décision structurante de ce lot. `ocr.json` et
# `traduction.json` s'alignent sur `regions.json` **par position** ; y insérer les régions
# hors bulle décalerait cet alignement sur les deux tomes déjà traduits et imposerait un
# `FORMAT_VERSION = 4` avec migration — donc, au moindre faux pas, la retraduction de
# 300 planches. Un fichier à part rend l'étage purement additif : les caches existants
# restent valides, et seul le nouvel étage tourne.
SFX_FILENAME = "sfx.json"
SFX_MASKS_FILENAME = "sfx_masks.png"
SFX_TRADUCTION_FILENAME = "sfx_traduction.json"


def save_sfx(ckpt_dir: Path, regions: list[BubbleRegion], textes: list[str],
             image_size: tuple[int, int], *, mobilier: list[bool] | None = None,
             styles: list[dict] | None = None, lu: bool = True) -> None:
    """Régions de texte hors bulle + leur OCR. Même schéma que `save_regions` (métadonnées
    JSON + une image d'étiquettes), pour que le format reste lisible d'un seul coup d'œil.

    Une planche SANS aucun texte hors bulle écrit quand même le fichier, avec une liste
    vide : c'est ce qui distingue « la passe a tourné et n'a rien trouvé » de « la passe n'a
    jamais tourné », exactement comme la chaîne vide de `load_terminologie`."""
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    # ⚠ Les traductions dépendent de CES textes-là. Si la lecture change — nouveau seuil,
    # nouvelle découpe, correction de la stratégie de crop — le `sfx_traduction.json` en cache
    # traduit autre chose : il décrit l'ancienne lecture, mot pour mot, sans que rien ne le
    # signale. Constaté en corrigeant le crop : l'OCR passait de `人間の場所…` à `ああ…陽弥…`
    # et la traduction restait « L'endroit des humains… ».
    #
    # Comparer les textes plutôt que de supprimer systématiquement : une relecture identique
    # ne doit pas coûter un appel LLM par planche.
    ancien = load_sfx(ckpt_dir)
    if ancien is not None and list(ancien[1]) != list(textes):
        (ckpt_dir / SFX_TRADUCTION_FILENAME).unlink(missing_ok=True)
    w, h = image_size
    meta = [{"bbox": list(r.bbox), "score": r.score, "cls": r.cls, "kind": r.kind}
            for r in regions]
    # ⚠ Deux plafonds INDÉPENDANTS : le compteur de `sfx_masks.png` repart à 1 dans son propre
    # fichier, une planche peut donc porter 250 bulles et 250 onomatopées sans qu'aucun des
    # deux ne déborde. C'est la raison pour laquelle la garde est posée ici aussi et pas une
    # seule fois en amont.
    _ecrire_image_atomique(image_etiquettes(regions, w, h, ou=str(ckpt_dir.name)),
                           ckpt_dir / SFX_MASKS_FILENAME)
    if mobilier is not None:
        for m, est_mobilier in zip(meta, mobilier):
            m["mobilier"] = bool(est_mobilier)
    _ecrire_atomique(
        ckpt_dir / SFX_FILENAME,
        json.dumps({"format": FORMAT_VERSION, "image_size": [w, h],
                    # `lu` distingue « détectée mais pas encore OCRisée » de « lue et vide ».
                    # C'est ce qui permet de filtrer le mobilier de page AVANT de payer la
                    # lecture — le filtre a besoin des boîtes de TOUT le tome, donc il ne peut
                    # pas tourner pendant la détection d'une planche isolée.
                    "lu": bool(lu),
                    "regions": meta, "textes": list(textes),
                    # ⚠ Lot 21, L21.2 — le STYLE mesuré de chaque zone hors bulle, aligné
                    # par position. Clé OPTIONNELLE : absente d'un cache écrit avant ce lot,
                    # `load_sfx_complet` rend alors `[]` et rien ne se relance.
                    # `FORMAT_VERSION` n'est PAS incrémentée, et c'est délibéré : elle encode
                    # le contrat de *nombre et d'ordre* auquel `ocr.json` et
                    # `traduction.json` s'alignent, qu'une clé de provenance ne touche pas.
                    # L'incrémenter ferait `downstream("detection")` sur tous les projets —
                    # des heures de GPU pour un champ que personne n'attend encore.
                    "styles": list(styles or [])},
                   ensure_ascii=False, indent=1))


def load_sfx(ckpt_dir: Path) -> tuple[list[BubbleRegion], list[str]] | None:
    """`(régions, textes OCR)`, ou `None` si la passe n'a jamais tourné sur cette page."""
    charge = load_sfx_complet(ckpt_dir)
    if charge is None:
        return None
    return charge["regions"], charge["textes"]


def load_sfx_complet(ckpt_dir: Path) -> dict | None:
    """Tout ce que `sfx.json` porte : régions, textes, `mobilier`, `styles`, `lu`, taille.

    `load_sfx` reste la vue courte (régions + textes), celle dont l'orchestrateur se sert au
    rendu ; le filtre de mobilier, lui, a besoin du reste."""
    meta_path = Path(ckpt_dir) / SFX_FILENAME
    mask_path = Path(ckpt_dir) / SFX_MASKS_FILENAME
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _prevenir_cache_abime(meta_path)
        return None
    meta = data.get("regions", [])
    textes = list(data.get("textes", []))
    taille = tuple(data.get("image_size") or (0, 0))
    mobilier = [bool(m.get("mobilier", False)) for m in meta]
    # `lu` absent = fichier écrit avant le lot 13, donc forcément lu (la détection et l'OCR
    # étaient alors indissociables). Le lire comme « non lu » relancerait l'OCR de deux tomes.
    lu = bool(data.get("lu", True))
    if not meta:
        return {"regions": [], "textes": textes, "mobilier": [], "styles": [], "lu": lu,
                "taille": taille}
    if not mask_path.exists():
        return None
    try:
        label = np.asarray(Image.open(mask_path))
    except (OSError, ValueError):
        _prevenir_cache_abime(mask_path)
        return None
    regions = [
        BubbleRegion(bbox=tuple(m["bbox"]), mask=(label == i), score=m.get("score", 1.0),
                     cls=m.get("cls", 0), kind=m.get("kind", "onomatopee"))
        for i, m in enumerate(meta, start=1)
    ]
    return {"regions": regions, "textes": textes, "mobilier": mobilier,
            "styles": list(data.get("styles") or []), "lu": lu, "taille": taille}


def save_sfx_traduction(ckpt_dir: Path, textes: list[str]) -> None:
    _save_texts(ckpt_dir, SFX_TRADUCTION_FILENAME, textes)


def load_sfx_traduction(ckpt_dir: Path) -> list[str] | None:
    textes = _load_texts(ckpt_dir, SFX_TRADUCTION_FILENAME)
    if textes is None:
        return None
    return [quality_manga.sans_prefixe(t) for t in textes]


# `first_missing_stage` a été SUPPRIMÉE au lot 3. Elle rendait un INDICE dans `STAGES`
# (« 3 » = traduction) : insérer `terminologie` en aurait décalé le sens sans qu'aucun appel
# ne casse. Elle n'avait plus de call site en production depuis le lot 1
# (`stage_cache_present` la remplace partout, et dit l'état de CHAQUE étape au lieu de
# s'arrêter à la première absence) — seuls ses propres tests l'appelaient encore.
