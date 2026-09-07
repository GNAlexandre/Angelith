# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Où en est le run** — des phases, un objet en cours, et une fraction qui ne recule jamais.

## Pourquoi ce module, et pourquoi dans `core/`

Pas dans `gui/`, parce que la console en a besoin aussi ; pas dans `manga/`, parce que le
light novel et l'atelier d'illustration s'en servent. Il ne connaît ni Qt, ni horloge murale,
ni fil de travail : il porte un état et le décrit. C'est l'interface qui l'affiche.

## Le défaut qu'il corrige, mesuré le 2026-09-05

`manga/orchestrator_manga.py` appelle `progres(i, total)` dans **deux balayages successifs
sur le même dénominateur** (L894-895 puis L1614-1616), et `pipeline/orchestrator.py` fait
alterner `chapter(ci, n)` et `block(bi, n)` — deux compteurs sans rapport. La barre montait
donc à 150, retombait à 1, remontait ; côté light novel elle a changé de dénominateur
jusqu'à **treize fois** dans un même run du corpus. Rejoué sur les `perf.log` du dépôt
(`tools/tracer_progression.py`) :

| trace | reculs | dénominateurs distincts | durée | sans temps restant affichable |
|---|--:|--:|--:|--:|
| manga paginé, 150 planches | 2 | 1 | 2 397 s | 63 s — 2,6 % |
| bande webtoon, 9 planches | 2 | 1 | 362 s | 160 s — 44,2 % |
| light novel, 25 chapitres | **66** | **6** | 44 190 s | **39 635 s — 89,7 %** |

Douze heures de run sur lesquelles onze n'affichent aucune estimation : c'est ce chiffre qui
justifie ce module. Tout est dans `docs/mesures/progression-2026-09-05.md`.

## Deux natures de fraction, et il ne faut jamais les confondre

`fraction()` peut être **pondérée** (une part du TEMPS, tirée de poids mesurés) ou
**comptée** (une part des OBJETS traversés). `nature()` dit laquelle, et l'interface s'en
sert : une fraction comptée ne s'affiche jamais en pourcentage, parce qu'un « 50 % » se lit
comme une moitié de temps, et qu'à la fin du balayage A d'un run manga la moitié des
planches est traversée mais seulement ~32 % du temps est payé.

⚠ **Les poids mesurés ne sont PAS armés, et c'est le résultat de l'étape 0.2.** Sur les
`perf.log` de `build/` (14 runs manga neufs, 11 runs light novel neufs), une seule phase
passe la règle du plan — « un écart min-max supérieur à un facteur 3 rend le poids
inutilisable » : le balayage A du manga, à ×1,6. Toutes les autres sont entre ×3,2 et ×18,8.
`POIDS_MESURES` conserve la mesure, `Phase.poids` reste `None` partout, et le modèle
fonctionne donc **en compté** sur tous les runs du dépôt. C'est délibéré : des poids égaux
inventés seraient un faux pourcentage avec l'aplomb d'un vrai.

## La monotonie, par construction ET par filet

Par construction : la fraction se compose de `part` — combien de fois le run traverse la
collection, ce qui est un fait de STRUCTURE du code et non une mesure — donc un balayage qui
recommence à la planche 1 repart d'un plancher qu'il ne peut pas franchir vers le bas.

Par filet : `_plancher` retient le maximum atteint et `fraction()` ne rend jamais moins. Le
filet est gardé même là où il est théoriquement redondant, exactement comme l'invariant
pixel de `manga/clean.py` — « parce que l'invariant ne doit pas dépendre d'un raisonnement ».

## Ce que ce module ne fait pas

- **Il ne remplace pas `gui/avancement.Estimateur`**, il l'utilise. Sa fenêtre glissante de
  12 et son minimum de 4 sont motivés par une mesure. L'estimateur est **injecté** plutôt
  qu'importé : `core/` ne dépend pas de `gui/`, et un test peut en fournir un faux.
- **Il ne fusionne pas `illustration/progression.py`.** Celui-ci porte trois phases nommées
  et un état propre à sa brique (bascule VRAM), il est testé, il marche. `PHASES_ILLUSTRATION`
  reprend seulement ses trois identifiants, pour que le bandeau de la fenêtre sache les
  nommer sans rien lui prendre.
"""
from __future__ import annotations

import re
from typing import NamedTuple


class Phase(NamedTuple):
    """Une phase de run.

    · `poids` — sa part **du temps**, MESURÉE, ou `None`. `None` est la réponse normale : il
      faut qu'une mesure passe la règle du facteur 3 pour qu'un poids existe ;
    · `part` — combien de fois la phase traverse la collection d'objets. C'est un fait de
      structure : le balayage A d'un run manga visite chaque planche une fois, le balayage B
      aussi, la passe terminologique aussi — d'où `1.0` pour les trois. `0.0` = la phase ne
      compte aucun objet mais on sait où l'on en est — c'est le cas de l'assemblage final,
      qui suit tout le reste et vaut donc 100 %. `None` = son avancement est
      **inconnaissable** (préparation, chargement d'un modèle, génération d'image avant la
      première image écrite), et la fraction se tait tant qu'on y est ;

      ⚠ La préparation est `None` et non `0.0`, alors que les deux donneraient « rien de
      compté ». Avec `0.0` la barre serait DÉTERMINÉE à zéro pendant qu'on lit la config et
      qu'on scanne le tome, puis basculerait en indéterminée au chargement du modèle : deux
      états en trois secondes, c'est-à-dire un clignotement ;
    · `unite` — le mot qu'on affiche : « planche », « chapitre », « image »."""

    identifiant: str
    libelle: str
    poids: float | None = None
    part: float | None = 1.0
    unite: str = ""


#: Les phases d'un run manga, dans l'ordre. Six, et l'interface les numérote « (3/6) ».
#:
#: ⚠ `chargement` n'est pas décoratif : le chargement du modèle ONNX de détection est payé
#: **dans la première planche**, et `gui/avancement.py` le dit déjà — « un débit tiré de deux
#: planches dont l'une portait le chargement du modèle ONNX est une estimation inventée ».
#: On ne règle pas ça par une constante d'amorçage : on annonce la phase, et la fraction se
#: tait le temps qu'elle dure (`part=None`).
PHASES_MANGA: tuple[Phase, ...] = (
    Phase("preparation", "Préparation", None, None),
    Phase("chargement", "Chargement du modèle de détection", None, None),
    Phase("analyse", "Analyse des planches", None, 1.0, "planche"),
    Phase("terminologie", "Terminologie", None, 1.0, "planche"),
    Phase("traduction", "Traduction et rendu", None, 1.0, "planche"),
    Phase("finalisation", "Rapport et assemblage", None, 0.0),
)

#: Celles d'un run light novel. Le chapitre est la SEULE unité monotone du light novel : le
#: bloc redémarre à 1 à chaque étage de chaque chapitre, et c'est lui qui faisait reculer la
#: barre 66 fois. Il devient un détail affiché, pas un avancement.
PHASES_LN: tuple[Phase, ...] = (
    Phase("preparation", "Préparation", None, None),
    Phase("chapitres", "Traduction des chapitres", None, 1.0, "chapitre"),
    Phase("finalisation", "Assemblage des sorties", None, 0.0),
)

#: Celles de l'atelier d'illustration. Les identifiants sont ceux d'`illustration/progression.py`
#: (`PREPARATION`, `BASCULE`, `GENERATION`) — ce module ne fait que savoir les nommer.
#: Les deux premières sont `part=None` : le coût d'une image varie d'un facteur 14,7 sur la
#: machine de référence (103,7 s à 1 524 s), et rien n'est comptable avant la première image.
PHASES_ILLUSTRATION: tuple[Phase, ...] = (
    Phase("preparation", "Préparation (LLM)", None, None),
    Phase("bascule", "Bascule de modèle", None, None),
    Phase("generation", "Génération (image)", None, 1.0, "image"),
)

#: `identifiant de brique → jeu de phases`. Ce que la fenêtre déclare quand elle lance un run.
PHASES: dict[str, tuple[Phase, ...]] = {
    "manga": PHASES_MANGA,
    "ln": PHASES_LN,
    "illustration": PHASES_ILLUSTRATION,
}

#: **La mesure de l'étape 0.2, conservée et NON armée** — `(part médiane, n runs, écart
#: min-max)`, sur les `perf.log` de `build/` au 2026-09-05. La règle du `PLAN-32` § 0.2
#: refuse tout poids dont l'écart dépasse un facteur 3 ; une seule ligne passe, et une phase
#: pondérée sur sept ne fait pas un modèle pondéré. Reproduire :
#: `python tools/banc_progression.py --markdown`.
#:
#: ⚠ Ce dictionnaire est de la DONNÉE, pas de la configuration. Personne ne le lit à
#: l'exécution ; il est ici pour que la prochaine mesure ait quelque chose à contredire.
POIDS_MESURES: dict[str, dict[str, tuple[float, int, float]]] = {
    "manga": {
        "analyse": (0.324, 14, 1.6),          # ← la seule qui passe la règle du facteur 3
        "terminologie": (0.049, 11, 18.8),
        "traduction": (0.279, 14, 4.5),
        "rendu": (0.342, 14, 3.2),
    },
    "ln": {
        "terminologie": (0.256, 11, 3.7),
        "traduction": (0.648, 11, 4.6),
        "mise en page": (0.096, 11, 3.8),
    },
}

#: Au-delà, un poids mesuré n'est pas utilisable (`PLAN-32` § 0.2).
FACTEUR_ABANDON = 3.0

#: Dénominateur entier donné à l'estimateur. Il raisonne en entiers ; une fraction s'y
#: convertit sans perdre de résolution à cette échelle (0,01 % de run).
ECHELLE = 10_000


class Progression:
    """L'état d'avancement d'un run, en Python nu.

    Un seul objet pour la vie de la fenêtre ; `declarer()` le remet à zéro à chaque run.

    `estimateur` est un objet à trois méthodes — `reinitialiser()`, `noter(courant, total)`,
    `restant(total)` — c'est-à-dire un `gui.avancement.Estimateur`. Il est **injecté** :
    `core/` ne dépend pas de `gui/`, et un test peut en donner un faux sans horloge."""

    def __init__(self, estimateur=None):
        self.estimateur = estimateur
        self._phases: tuple[Phase, ...] = ()
        self._index: int = -1
        self._courant: int = 0
        self._total: int = 0
        self._objet: str = ""
        self._detail: str = ""
        self._indetermine: bool = False
        self._plancher: float = 0.0
        #: Le plus grand `(total, unité)` vu depuis `declarer()` — cf. `bilan()`.
        self._sommet: tuple[int, str] = (0, "")
        #: Nombre de fois où un canal a fait reculer le compte. Purement diagnostique — c'est
        #: ce que `tools/tracer_progression.py` mesure sur les traces réelles, et le garder
        #: en vie permet de constater qu'un canal recule encore.
        self.reculs: int = 0

    # ────────────────────────────────  Écriture  ──────────────────────────── #

    def declarer(self, phases) -> None:
        """Repart de zéro sur un nouveau jeu de phases."""
        self._phases = tuple(phases)
        self._index = -1
        self._courant = self._total = 0
        self._objet = self._detail = ""
        self._indetermine = False
        self._plancher = 0.0
        self._sommet = (0, "")
        self.reculs = 0
        if self.estimateur is not None:
            self.estimateur.reinitialiser()

    def entrer(self, identifiant: str) -> None:
        """Change de phase. Inconnue ou en arrière : ignorée, et comptée.

        ⚠ **Ignorer plutôt que lever.** Ces appels viennent d'un orchestrateur qui tourne
        dans un fil d'arrière-plan : y lever une exception ferait tomber un run de 150
        planches pour un défaut d'affichage. Le compteur `reculs` garde la trace, et un test
        la vérifie sur les traces réelles."""
        indices = {p.identifiant: i for i, p in enumerate(self._phases)}
        cible = indices.get(identifiant)
        if cible is None or cible == self._index:
            return
        if cible < self._index:
            self.reculs += 1
            return
        self._index = cible
        self._courant = self._total = 0
        self._objet = self._detail = ""
        self._indetermine = False

    def avancer(self, courant: int, total: int, objet: str = "") -> None:
        """L'avancement CHIFFRÉ de la phase en cours.

        `total <= 0` signifie « je ne sais pas combien il y en a » — un lot de traduction en
        cours, dont l'unité d'avancement est le lot et non la planche. La position est
        conservée, la fraction se tait, la barre passe en indéterminé."""
        if objet:
            self._objet = str(objet)
        if total > 0:
            self._total = int(total)
            self._indetermine = False
            phase = self.phase
            if self._total > self._sommet[0]:
                self._sommet = (self._total, phase.unite if phase else "")
        else:
            self._indetermine = True
        courant = int(courant)
        if courant < self._courant:
            self.reculs += 1
        else:
            self._courant = courant
        self._recalculer()

    def detailler(self, texte: str) -> None:
        """La ligne secondaire : « bloc 3/10 », « lot 80→99 ». **Ne compte pas.**

        C'est ici qu'atterrit `Reporter.block` : le bloc redémarre à 1 à chaque étage de
        chaque chapitre, il ne peut donc pas porter un avancement, mais il dit très bien où
        l'on en est DANS l'étape — ce que rien n'affichait."""
        self._detail = str(texte or "")

    def nommer(self, objet: str) -> None:
        """L'objet en cours, sans avancer : un nom de fichier, une plage de lot."""
        self._objet = str(objet or "")

    # ────────────────────────────────  Lecture  ──────────────────────────── #

    @property
    def phase(self) -> Phase | None:
        return self._phases[self._index] if 0 <= self._index < len(self._phases) else None

    def rang(self) -> tuple[int, int]:
        """`(numéro de la phase, nombre de phases)`, 1-indexé. `(0, n)` avant la première."""
        return (self._index + 1, len(self._phases))

    def nature(self) -> str:
        """`"ponderee"`, `"comptee"`, ou `""` quand il n'y a rien à dire.

        « Pondérée » exige que **toutes** les phases portent un poids mesuré : une seule
        phase pondérée sur sept ne donne pas une fraction de temps, elle donne un mélange."""
        if not self._phases:
            return ""
        if all(p.poids is not None for p in self._phases):
            return "ponderee"
        return "comptee"

    def fraction(self) -> float | None:
        """La fraction du run, ou `None` — et `None` n'est **jamais** « zéro pour cent ».

        `None` veut dire « je ne sais pas », et l'interface le traduit par une barre
        indéterminée, sans pourcentage et sans temps restant. Les trois cas où il tombe sont
        nommés : une génération d'image avant la première image écrite, un lot de traduction
        en cours, et le chargement du modèle de détection."""
        if not self._phases or self._index < 0:
            return None
        phase = self._phases[self._index]
        if phase.part is None or self._indetermine:
            return None
        return self._calculee()

    def restant(self) -> float | None:
        """Secondes restantes, ou `None`. Passe par l'estimateur injecté.

        ⚠ **Jamais de temps quand la fraction se tait.** C'est la règle Microsoft citée par
        le plan — « ne jamais combiner indéterminé et temps restant » — et elle est portée
        ici plutôt que dans le widget, pour que la console et l'interface ne puissent pas en
        donner deux lectures."""
        if self.estimateur is None or self.fraction() is None:
            return None
        return self.estimateur.restant(ECHELLE)

    def libelle(self) -> str:
        """« Traduction et rendu (5/6) — planche 84/131 »."""
        phase = self.phase
        if phase is None:
            return "prêt"
        rang, total_phases = self.rang()
        texte = f"{phase.libelle} ({rang}/{total_phases})"
        if self._total > 0 and phase.unite:
            texte += f" — {phase.unite} {self._courant}/{self._total}"
        elif self._total > 0:
            texte += f" — {self._courant}/{self._total}"
        return texte

    def objet(self) -> str:
        """Le « 3 of 50 » de NN/g : ce sur quoi on travaille, nommé."""
        morceaux = [m for m in (self._objet, self._detail) if m]
        return " · ".join(morceaux)

    def compte(self) -> tuple[int, int]:
        """`(courant, total)` de la phase — l'avancement COMPTÉ, toujours honnête."""
        return self._courant, self._total

    def bilan(self) -> tuple[int, str]:
        """`(objets traversés, unité)` sur TOUT le run — ce qu'on dit à la fin.

        ⚠ Pas `compte()`. Un run finit dans sa phase d'assemblage, qui ne compte rien : lire
        le compte courant à ce moment-là rendrait `(0, "")` et le bilan dirait « Terminé »
        tout court, sur un run de 131 planches. On retient donc le sommet — le plus grand
        dénominateur vu, avec son unité."""
        return self._sommet

    def etat(self) -> dict:
        """Un dictionnaire plat, traversable par un signal Qt sans transporter d'objet."""
        phase = self.phase
        rang, total_phases = self.rang()
        return {
            "phase": phase.identifiant if phase else "",
            "phase_libelle": phase.libelle if phase else "",
            "libelle": self.libelle(),
            "objet": self.objet(),
            "rang": rang,
            "phases": total_phases,
            "courant": self._courant,
            "total": self._total,
            "fraction": self.fraction(),
            "nature": self.nature(),
            "restant": self.restant(),
            "unite": phase.unite if phase else "",
        }

    # ────────────────────────────────  Rouages  ──────────────────────────── #

    def _parts(self) -> list[float]:
        """La part de chaque phase, pondérée ou comptée. Une phase `None` ne pèse rien."""
        if self.nature() == "ponderee":
            return [float(p.poids or 0.0) for p in self._phases]
        return [0.0 if p.part is None else float(p.part) for p in self._phases]

    def _calculee(self) -> float:
        parts = self._parts()
        somme = sum(parts)
        if somme <= 0:
            return self._plancher
        avant = sum(parts[:self._index])
        dedans = 0.0
        if self._total > 0 and parts[self._index] > 0:
            dedans = parts[self._index] * min(1.0, self._courant / self._total)
        return max(self._plancher, min(1.0, (avant + dedans) / somme))

    def _recalculer(self) -> None:
        """Remonte le plancher et nourrit l'estimateur. Appelé par `avancer`, pas par les
        lectures : une lecture qui mute est un piège pour qui teste."""
        if not self._phases or self._index < 0:
            return
        if self._phases[self._index].part is None or self._indetermine:
            return
        valeur = self._calculee()
        self._plancher = max(self._plancher, valeur)
        if self.estimateur is not None:
            self.estimateur.noter(int(round(self._plancher * ECHELLE)), ECHELLE)


# --------------------------------------------------------------------------- #
#  Le repli par expression régulière — il RESTE, et il a une raison
# --------------------------------------------------------------------------- #

_RE_PAGE = re.compile(r"Page (\d+)/(\d+)")
_RE_LOT = re.compile(r"Lot planches (\d+)→(\d+)")


def progression_de_stage(nom: str) -> tuple[int, int]:
    """`(courant, total)` extrait d'un libellé d'étape, ou `(0, 0)`.

    Volontairement tolérant : si un jour le libellé change, la barre cesse d'avancer et rien
    d'autre ne casse. Une progression est un confort, pas une donnée.

    ⚠ **Ce repli n'est pas retiré par le lot 32, et c'est une décision.** `progres` couvre
    désormais les deux balayages du manga et la passe terminologique, mais toutes les étapes
    ne sont pas instrumentées — et le jour où l'une d'elles le sera par un libellé avant de
    l'être par un canal, c'est cette fonction qui tiendra la barre vivante. Ce lot **ajoute**
    un canal, il n'en retire pas.

    ⚠ Elle a déménagé de `gui/travailleur.py` vers ici, sans changer d'une ligne :
    `gui.travailleur.progression_de_stage` la ré-exporte, et son test d'origine
    (`tests/test_gui_reporter.py`) est inchangé. Le motif est la règle de couche — ce qui
    DÉCIDE se teste sans PySide6, et un repli enfermé dans un module qui importe Qt ne le
    pouvait pas."""
    m = _RE_PAGE.search(nom)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _RE_LOT.search(nom)
    if m:
        return int(m.group(1)), 0
    return 0, 0


# --------------------------------------------------------------------------- #
#  La traduction « appel du protocole `Reporter` » → « mutation de `Progression` »
# --------------------------------------------------------------------------- #

def appliquer(progression: Progression, methode: str, args, *, repli=None) -> None:
    """Applique UN appel du protocole `Reporter` au modèle. **La table de référence.**

    Elle est ici et pas dans `gui/fenetre.py` pour une raison : c'est elle que les tests
    rejouent sur les traces réelles pour prouver que la fraction ne recule jamais. Les
    connexions Qt de la fenêtre ne font que la refléter, appel pour appel.

    `repli(nom) -> (courant, total)` est le repli par expression régulière sur le libellé
    d'étape (`gui.travailleur.progression_de_stage`). Il reste en place, et c'est délibéré :
    les étapes non instrumentées existent encore, et sa docstring dit pourquoi — « si un jour
    le libellé change, la barre cesse d'avancer et rien d'autre ne casse »."""
    args = list(args or [])
    if methode == "phase" and args:
        progression.entrer(str(args[0]))
    elif methode == "progres" and len(args) >= 2:
        progression.avancer(int(args[0]), int(args[1]),
                            str(args[2]) if len(args) > 2 else "")
    elif methode == "chapter" and len(args) >= 2:
        progression.avancer(int(args[0]), int(args[1]),
                            str(args[2]) if len(args) > 2 else "")
    elif methode == "block" and len(args) >= 2:
        progression.detailler(f"bloc {int(args[0])}/{int(args[1])}")
    elif methode == "stage" and args and repli is not None:
        courant, total = repli(str(args[0]))
        if courant:
            progression.avancer(courant, total)


def rejouer(evenements, progression: Progression, *, repli=None) -> list[float | None]:
    """Rejoue une trace et rend la suite des fractions. Utilisé par les tests et par
    `tools/tracer_progression.py --rejouer`."""
    suite: list[float | None] = []
    for ev in evenements:
        appliquer(progression, ev.get("methode", ""), ev.get("args", []), repli=repli)
        suite.append(progression.fraction())
    return suite
