# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que l'interface doit savoir d'une planche **sans l'ouvrir** — et sans Qt.

## Pourquoi ce module existe

Deux besoins convergeaient vers la même question, et chacun l'avait résolue de son côté :

- `assemble_outputs` voulait prévenir qu'une archive allait embarquer des rendus périmés ;
- l'éditeur graphique doit savoir **quelles planches relettrer** avant de réassembler, et
  quelle pastille afficher sur chaque vignette.

La réponse est la même dans les deux cas — *le rendu est-il en retard sur les données ?* — et
elle vit ici, en Python nu. C'est la règle de couche du dépôt : `gui/` ne contient que du Qt,
toute logique métier est testable sans PySide6.

## Le défaut que ce module corrige

`_pages_perimees` ne comparait `pages_out/` qu'à `traduction.json`. Or l'éditeur n'écrit
**jamais** dans ce fichier : une réplique corrigée à la main va dans `traduction_manuelle.json`
et un bloc de texte déplacé dans `mise_en_page.json` — c'est précisément ce qui les fait
survivre à un `--from traduction`. Conséquence : corriger une réplique à la main ne marquait
le rendu périmé **nulle part**, ni pour l'avertissement d'assemblage, ni pour l'éditeur. Le
travail était écrit, et l'archive continuait de porter l'ancienne image.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import checkpoints, report_manga

# `manga/checkpoints.py` écrit `regions.json` par un littéral et n'en expose pas de constante ;
# on la nomme ici plutôt que de répéter la chaîne à trois endroits.
REGIONS_FILENAME = "regions.json"

# Fichiers dont une écriture rend le rendu périmé, avec le motif à afficher. L'ordre est celui
# du récapitulatif : on nomme d'abord ce que l'utilisateur vient de faire à la main.
SOURCES_DE_PEREMPTION: tuple[tuple[str, str], ...] = (
    (checkpoints.TRADUCTION_MANUELLE_FILENAME, "réplique corrigée à la main"),
    (checkpoints.MISE_EN_PAGE_FILENAME, "texte déplacé"),
    (REGIONS_FILENAME, "zones retouchées"),
    (checkpoints.TRADUCTION_FILENAME, "traduction refaite"),
)


def _mtime(chemin: Path) -> float | None:
    try:
        return chemin.stat().st_mtime
    except OSError:
        return None


def _motifs(rendu: float | None, mtimes: dict[str, float]) -> list[str]:
    """**LA** règle de péremption, et le seul endroit où elle est écrite.

    `rendu` est la date du rendu de la planche, `mtimes` celles de ses fichiers de cache par
    nom. Deux chemins d'accès l'appellent — `motifs_de_peremption`, qui interroge le disque
    planche par planche pour l'éditeur, et `balayer_tome`, qui lit tout un tome d'un coup pour
    la bibliothèque. Ils ne diffèrent que par la façon d'obtenir les dates ; s'ils
    différaient par la COMPARAISON, la bibliothèque afficherait « à jour » sur une planche que
    l'éditeur propose de relettrer."""
    if rendu is None:
        return []
    return [motif for nom, motif in SOURCES_DE_PEREMPTION
            if nom in mtimes and rendu < mtimes[nom]]


def motifs_de_peremption(build_dir, index: int) -> list[str]:
    """Pourquoi le rendu de cette planche est en retard — vide s'il est à jour.

    Comparaison de `mtime`, et c'est assumé ici alors que `manga/projet.py` les refuse pour
    son empreinte : ce qu'on cherche est justement un ORDRE d'écriture, pas une identité de
    contenu. Une resynchronisation OneDrive qui réécrit les deux fichiers les décale ensemble
    et ne crée donc pas de faux positif ; un rendu réellement plus vieux, lui, se voit.

    ⚠ Une planche **jamais rendue** ne renvoie rien. C'est délibéré : elle n'est pas périmée,
    elle n'existe pas encore, et la faire remonter dans « à relettrer » ferait passer un tome
    à peine détecté pour un tome à refaire."""
    rendu = _mtime(checkpoints.final_page_path(build_dir, index))
    if rendu is None:
        return []
    ckpt = checkpoints.page_checkpoint_dir(build_dir, index)
    mtimes = {}
    for nom, _motif in SOURCES_DE_PEREMPTION:
        date = _mtime(ckpt / nom)
        if date is not None:
            mtimes[nom] = date
    return _motifs(rendu, mtimes)


def balayer_tome(build_dir) -> dict[int, dict]:
    """Tout ce qu'un tome dit de lui-même en **un `scandir` par planche**.

    Rend `{index: {"fichiers": set[str], "rendu": float | None, "motifs": [str],
    "mtime": float | None}}`, où `mtime` est la date de la dernière écriture VUE dans le
    checkpoint de la planche — c'est-à-dire quand le pipeline l'a touchée pour la dernière
    fois. Elle est relevée au passage, sans un appel de plus, et c'est ce qui permet à la
    bibliothèque d'afficher un « dernier run » sur un tome détecté mais jamais rendu.

    ## Pourquoi cette fonction existe

    Elle ne change **aucune règle** : les motifs sortent de `_motifs`, la même comparaison que
    `motifs_de_peremption` fait planche par planche. Ce qu'elle change est la façon d'obtenir
    les dates.

    ⚠ Le chemin planche-par-planche paie **cinq `os.stat`** par planche — un par fichier
    surveillé, plus le rendu. Sur les 55 tomes du corpus, mesuré le 2026-09-05, c'était
    **5 470 des 13 631 appels `stat`** du balayage complet de la bibliothèque, pour une
    information que l'entrée de répertoire porte déjà. `os.scandir` rend le nom ET les
    métadonnées en une fois.

    ⚠ **Le gain dépend du système, et le dire vaut mieux que de l'annoncer partout.** Sous
    Windows, `DirEntry.stat()` lit un cache rempli par le `scandir` et ne touche plus le
    disque : les 5 470 appels disparaissent. Sous Linux, `DirEntry.stat()` fait un vrai appel
    et le gain se réduit à ce que la lecture de répertoire économise. C'est mesuré sur
    Windows, et nulle part ailleurs.

    ⚠ Ce qu'elle ne fait pas : ouvrir un seul fichier. Ni JSON, ni image. Un tome dont le
    cache est à moitié écrit rend un état pauvre, jamais une exception — même tolérance que
    `etat_planche`, et pour la même raison.
    """
    build_dir = Path(build_dir)
    surveilles = {nom for nom, _ in SOURCES_DE_PEREMPTION}

    rendus: dict[int, float] = {}
    try:
        with os.scandir(build_dir / "pages_out") as entrees:
            for e in entrees:
                tige = Path(e.name).stem
                if not e.name.endswith(".png") or not tige.startswith("page_"):
                    continue
                numero = tige.removeprefix("page_")
                if numero.isdigit():
                    rendus[int(numero)] = e.stat().st_mtime
    except OSError:
        pass

    sortie: dict[int, dict] = {}
    try:
        with os.scandir(build_dir / ".checkpoints") as entrees:
            pages = [(int(e.name.removeprefix("page_")), e.path) for e in entrees
                     if e.name.startswith("page_")
                     and e.name.removeprefix("page_").isdigit() and e.is_dir()]
    except OSError:
        pages = []

    for index, chemin in sorted(pages):
        fichiers: set[str] = set()
        mtimes: dict[str, float] = {}
        dernier: float | None = None
        try:
            with os.scandir(chemin) as contenu:
                for e in contenu:
                    fichiers.add(e.name)
                    try:
                        date = e.stat().st_mtime
                    except OSError:
                        continue
                    if e.name in surveilles:
                        mtimes[e.name] = date
                    if dernier is None or date > dernier:
                        dernier = date
        except OSError:
            pass
        rendu = rendus.get(index)
        sortie[index] = {"fichiers": fichiers, "rendu": rendu, "mtime": dernier,
                         "motifs": _motifs(rendu, mtimes)}
    return sortie


def perimees_du_balayage(balayage: dict[int, dict]) -> list[int]:
    """Les planches périmées d'un balayage déjà fait, triées.

    Existe pour qu'un appelant qui a **déjà** payé `balayer_tome` — la bibliothèque, qui a
    besoin du même balayage pour compter ses étapes — n'ait pas à le refaire pour poser la
    question de la péremption."""
    return sorted(i for i, etat in balayage.items() if etat["motifs"])


def planches_a_relettrer(build_dir, indices=None) -> list[int]:
    """Planches dont le rendu est antérieur à l'une de leurs données, triées.

    `indices` restreint l'examen (l'index de `projet.json`, typiquement) ; sans lui, les
    dossiers de `.checkpoints/` font foi — et c'est alors `balayer_tome` qui répond, en un
    balayage plutôt qu'en cinq `stat` par planche. Le résultat est le même : les deux chemins
    passent par `_motifs`."""
    if indices is None:
        return perimees_du_balayage(balayer_tome(build_dir))
    return sorted(i for i in indices_de(build_dir, indices)
                  if motifs_de_peremption(build_dir, i))


def indices_de(build_dir, indices=None) -> list[int]:
    """Les planches d'un tome, triées — depuis `.checkpoints/`, ou la liste fournie.

    Public (et nommé `_de` pour ne pas masquer son propre paramètre) : `recherche.py` pose
    exactement la même question, et deux balayages du même dossier finiraient par ne plus
    répondre pareil sur ce qui compte comme une planche."""
    if indices is not None:
        return [int(i) for i in indices]
    # ⚠ `os.scandir` et non `iterdir()` + `is_dir()` : le second paie un `stat` par entrée,
    # et ce dossier en porte une par planche. Mesuré au lot 34 sur le corpus : 1 102 appels
    # système pour une question à laquelle l'entrée de répertoire répond déjà. Le résultat
    # est identique — même filtre, même tri.
    racine = Path(build_dir) / ".checkpoints"
    try:
        with os.scandir(racine) as entrees:
            return sorted(int(e.name.removeprefix("page_")) for e in entrees
                          if e.name.startswith("page_")
                          and e.name.removeprefix("page_").isdigit() and e.is_dir())
    except OSError:
        return []


# --------------------------------------------------------------------------- #
#  État d'une planche — ce que porte une vignette
# --------------------------------------------------------------------------- #

def etat_planche(build_dir, index: int) -> dict:
    """Résumé d'une planche, lu depuis le cache seul.

    Volontairement tolérant de bout en bout : une planche jamais détectée, un `qa.json`
    absent ou un cache à moitié écrit rendent un état pauvre, jamais une exception. Cette
    fonction alimente une bande de vignettes — la faire échouer sur une planche rendrait le
    tome entier inaffichable."""
    ckpt = checkpoints.page_checkpoint_dir(build_dir, index)
    regions = checkpoints.load_regions(ckpt)
    manuelles = checkpoints.load_traduction_manuelle(ckpt)
    mises = checkpoints.load_mise_en_page(ckpt)
    traduction = checkpoints.load_traduction(ckpt) or []
    qa = report_manga.load_page_qa(ckpt) or {}
    bulles_qa = qa.get("bulles") or []
    motifs = motifs_de_peremption(build_dir, index)

    return {
        "index": index,
        "detectee": regions is not None,
        "bulles": len(regions) if regions is not None else 0,
        "corrigees": len(manuelles),
        "deplacees": len(mises),
        # Une bulle sans texte n'est pas une erreur en soi (bulle de silence), mais un tome
        # qui en compte beaucoup demande à être regardé.
        "vides": sum(1 for t in traduction if not (t or "").strip()),
        "debordements": sum(1 for b in bulles_qa if b.get("debordement")),
        "rendue": checkpoints.final_page_path(build_dir, index).exists(),
        "perimee": bool(motifs),
        "motifs": motifs,
    }


# --------------------------------------------------------------------------- #
#  Memoisation — l'interface pose la question 150 fois par geste
# --------------------------------------------------------------------------- #

#: Fichiers dont le `mtime` suffit à dire si un état calculé vaut encore. Ce sont exactement
#: ceux que `etat_planche` lit — les quatre de `SOURCES_DE_PEREMPTION`, plus `qa.json` (les
#: débordements) et le rendu lui-même.
FICHIERS_SUIVIS: tuple[str, ...] = tuple(
    [nom for nom, _ in SOURCES_DE_PEREMPTION] + [checkpoints.QA_FILENAME])


def signature(build_dir, index: int) -> tuple:
    """Ce qui, sur le disque, peut changer l'état d'une planche.

    ⚠ Cette fonction n'existe que parce qu'elle est **cent fois moins chère** que la réponse
    qu'elle protège. Mesuré sur *manga A* Vol.1 (150 planches) : les six `stat` coûtent
    **13 ms** pour tout le tome, le parsing JSON qu'ils évitent en coûte **1 095 ms**. La
    fraîcheur se vérifie donc pour 1 % du prix de la réponse, ce qui est la seule raison
    d'être d'un cache : sans cet écart, il ne ferait que déplacer le coût."""
    ckpt = checkpoints.page_checkpoint_dir(build_dir, index)
    return (_mtime(checkpoints.final_page_path(build_dir, index)),
            *(_mtime(ckpt / nom) for nom in FICHIERS_SUIVIS))


class CacheEtats:
    """Mémoïse `etat_planche`, invalidé par les `mtime` qu'il lisait déjà.

    ## Pourquoi il fallait un cache et pas un fil

    `etat_planche` coûte 5,9 ms, ce qui est négligeable — sauf qu'on le demande **150 fois
    par geste** : à l'ouverture d'un tome, à chaque changement de filtre, et à chaque
    rafraîchissement complet de la pellicule. Soit **888 ms de fenêtre gelée**, trois fois
    par minute de travail.

    ⚠ Déporter ce calcul sur un fil de fond aurait été la mauvaise réponse : une pastille
    qui arrive 200 ms après le clic est **pire** qu'une pastille calculée tout de suite,
    parce qu'on la lit pendant qu'elle est encore fausse. Le problème n'est pas que le
    calcul soit long, c'est qu'on le **répète à l'identique**.

    Aucune invalidation explicite à écrire, donc aucune à oublier : la clé **est** l'état
    du disque. C'est le même parti que `gui/cache_apercu.signature`, et pour le même motif
    — un état périmé afficherait « à jour » sur une planche corrigée, ce qui la ferait
    sauter du récapitulatif d'enregistrement sans que personne ne le voie."""

    def __init__(self, calcul=None):
        self._calcul = calcul or etat_planche
        self._entrees: dict[int, tuple[tuple, dict]] = {}
        self.succes = 0
        self.calculs = 0

    def lire(self, build_dir, index: int) -> dict:
        """L'état de la planche, recalculé seulement si le disque a bougé."""
        index = int(index)
        cle = signature(build_dir, index)
        entree = self._entrees.get(index)
        if entree is not None and entree[0] == cle:
            self.succes += 1
            return entree[1]
        etat = self._calcul(build_dir, index)
        self._entrees[index] = (cle, etat)
        self.calculs += 1
        return etat

    def oublier(self, index: int) -> None:
        """Après une écriture qu'on vient de faire soi-même.

        Redondant avec la signature — et c'est voulu : sur un système de fichiers à `mtime`
        d'une seconde de résolution, écrire puis relire dans la même seconde rendrait la
        même clé pour un contenu différent."""
        self._entrees.pop(int(index), None)

    def vider(self) -> None:
        self._entrees.clear()

    def __len__(self) -> int:
        return len(self._entrees)


def resume(build_dir, indices=None) -> list[dict]:
    """L'état de chaque planche, dans l'ordre de lecture."""
    return [etat_planche(build_dir, i) for i in indices_de(build_dir, indices)]


def libelle_etat(etat: dict) -> str:
    """Une ligne pour la barre d'état de l'éditeur et l'infobulle d'une vignette."""
    if not etat["detectee"]:
        return f"Planche {etat['index']} · aucune détection"
    bouts = [f"Planche {etat['index']}", f"{etat['bulles']} bulle(s)"]
    if etat["corrigees"]:
        bouts.append(f"{etat['corrigees']} corrigée(s)")
    if etat["deplacees"]:
        bouts.append(f"{etat['deplacees']} déplacée(s)")
    if etat["debordements"]:
        bouts.append(f"{etat['debordements']} débordement(s)")
    if etat["perimee"]:
        bouts.append("rendu périmé — " + ", ".join(etat["motifs"]))
    elif not etat["rendue"]:
        bouts.append("jamais rendue")
    return " · ".join(bouts)
