# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Trois phases, trois coûts, trois libellés** — et jamais un pourcentage inventé.

`PLAN-27` L27.2 : « la barre de progression a deux phases, et elles n'ont pas le même coût.
Affichez-les séparément — préparation (LLM), bascule de modèle, génération (image) — parce que
le chiffre mesuré peut faire de la bascule le poste le plus long. Une barre unique qui reste
bloquée sur 30 % pendant le déchargement du LLM est un défaut d'information, pas un défaut de
vitesse. »

Il y en a **trois** et non deux, parce que le run en compte trois : la phase 1 (le modèle de
vision choisit les images, ~5 s par image et un appel par image), la bascule VRAM, puis la
génération. Les confondre ferait passer une phase 1 de 90 s pour un démarrage lent.

## Ce que ce module refuse de faire, et c'est le point

**Il ne convertit jamais un temps en pourcentage tant qu'il n'a pas de quoi.** La mesure du
dépôt donne un rapport de 14,7 entre la génération la plus rapide (103,7 s) et la plus lente
(1 524 s) sur la même carte : une barre qui prétendrait « 42 % » après 43 s se tromperait d'un
facteur dix un jour sur deux. `fraction()` rend donc :

- `None` tant qu'aucune image n'est terminée — la barre est alors **indéterminée**, ce que Qt
  sait afficher (`setRange(0, 0)`) et ce que la fenêtre fait déjà pour les étapes non
  instrumentées ;
- une fraction en **images terminées sur images demandées** dès la première, parce que celle-là
  est comptée et non estimée.

C'est la même discipline que `gui/lanceur.py:_confirmer`, qui refuse de chiffrer la durée d'un
run : « aucune constante mesurée ne couvre un run complet […] l'annoncer serait inventer un
chiffre ».

## Sans Qt, sans horloge murale, sans effet de bord

L'horloge est **injectée** (`horloge=`), ce qui rend chaque durée testable à la milliseconde
sans dormir une seule fois. Le module ne connaît ni `PySide6`, ni `time.sleep`, ni le fil de
travail : il porte un état et le décrit. C'est l'interface qui l'affiche, et la console qui
l'imprime.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

#: Les trois phases, dans l'ordre où elles se paient.
PREPARATION = "preparation"
BASCULE = "bascule"
GENERATION = "generation"

ORDRE: tuple[str, ...] = (PREPARATION, BASCULE, GENERATION)

#: Ce que chaque phase dit à l'écran. Le mot entre parenthèses nomme **ce qui occupe la
#: carte** — c'est l'information qui manque quand une barre semble bloquée.
LIBELLES: dict[str, str] = {
    PREPARATION: "préparation (LLM)",
    BASCULE: "bascule de modèle",
    GENERATION: "génération (image)",
}

#: Ce qu'on répond à « pourquoi ça ne bouge pas ? », phase par phase. Une barre immobile qui
#: dit pourquoi n'est plus une barre immobile.
POURQUOI: dict[str, str] = {
    PREPARATION: "le modèle de vision regarde les images candidates, un appel par image",
    BASCULE: "le LLM de traduction rend la carte — les deux modèles ne coexistent jamais "
             "en VRAM",
    GENERATION: "le modèle d'image travaille ; l'unité d'avancement est l'image terminée, "
                "pas le pas de débruitage",
}


@dataclass
class Phase:
    """Une phase : son coût réel, mesuré, et rien d'estimé."""

    cle: str
    debut: float | None = None
    fin: float | None = None

    @property
    def commencee(self) -> bool:
        return self.debut is not None

    @property
    def terminee(self) -> bool:
        return self.fin is not None

    def secondes(self, maintenant: float | None = None) -> float:
        """Le temps passé. Une phase en cours rend le temps **écoulé**, pas zéro : une phase
        qui dure trois minutes et annonce 0,0 s est exactement ce que ce module existe pour
        éviter."""
        if self.debut is None:
            return 0.0
        borne = self.fin if self.fin is not None else maintenant
        if borne is None:
            return 0.0
        return max(0.0, borne - self.debut)


@dataclass
class Progression:
    """L'état d'avancement d'un run d'illustration, en Python nu.

    ⚠ **Une seule phase est ouverte à la fois**, et ouvrir la suivante ferme la précédente.
    C'est ce qui garantit que la somme des trois durées est le temps du run, et non un total
    supérieur au temps écoulé — le genre de chiffre qui décrédibilise tout un rapport."""

    #: Nombre d'images demandées. `0` = on ne le sait pas encore.
    total_images: int = 0
    images_faites: int = 0
    #: Nom de l'image en cours, pour l'écran.
    en_cours: str = ""
    #: `True` dès qu'une annulation a été demandée — l'écran doit le dire avant que la phase
    #: en cours se termine, sinon l'utilisateur reclique.
    annulation_demandee: bool = False
    phases: dict = field(default_factory=lambda: {c: Phase(c) for c in ORDRE})
    horloge: object = time.monotonic
    _ouverte: str = ""

    # ────────────────────────────────  Écriture  ────────────────────────────────

    def demarrer(self, cle: str) -> None:
        """Ouvre une phase, en fermant celle qui l'était."""
        if cle not in self.phases:
            raise ValueError(f"phase inconnue : {cle} (attendu : {', '.join(ORDRE)})")
        maintenant = float(self.horloge())
        if self._ouverte and self._ouverte != cle:
            self.phases[self._ouverte].fin = maintenant
        phase = self.phases[cle]
        if phase.debut is None:
            phase.debut = maintenant
        phase.fin = None
        self._ouverte = cle

    def terminer(self, cle: str = "") -> None:
        """Ferme une phase (celle qui est ouverte, par défaut)."""
        cle = cle or self._ouverte
        if not cle:
            return
        self.phases[cle].fin = float(self.horloge())
        if self._ouverte == cle:
            self._ouverte = ""

    def image_terminee(self, nom: str = "") -> None:
        """Une image de plus est écrite. **C'est la seule unité d'avancement chiffrée.**"""
        self.images_faites += 1
        self.en_cours = nom

    def demander_l_annulation(self) -> None:
        self.annulation_demandee = True

    # ────────────────────────────────  Lecture  ────────────────────────────────

    def fraction(self) -> float | None:
        """`(faites, total)` en fraction, ou `None` quand rien n'est encore comptable.

        ⚠ `None` n'est pas « zéro pour cent » : c'est « je ne sais pas », et l'interface le
        traduit par une barre indéterminée. Les confondre ferait afficher 0 % pendant les
        cent premières secondes d'un run qui avance très bien."""
        if self.total_images <= 0 or self.images_faites <= 0:
            return None
        return min(1.0, self.images_faites / self.total_images)

    def phase_ouverte(self) -> str:
        return self._ouverte

    def libelle(self) -> str:
        """La ligne d'état : la phase, ce qui est compté, et ce qui occupe la carte."""
        if self.annulation_demandee:
            return ("annulation demandée — le modèle d'image rend la carte avant de "
                    "s'arrêter, ne reclique pas")
        if not self._ouverte:
            return "prêt"
        libelle = LIBELLES[self._ouverte]
        if self._ouverte == GENERATION and self.total_images:
            compte = f" — {self.images_faites}/{self.total_images} image(s)"
            return f"{libelle}{compte}" + (f" · {self.en_cours}" if self.en_cours else "")
        return f"{libelle} — {POURQUOI[self._ouverte]}"

    def secondes(self, cle: str) -> float:
        return self.phases[cle].secondes(float(self.horloge()))

    def total_secondes(self) -> float:
        return sum(self.secondes(c) for c in ORDRE)

    def resume(self) -> str:
        """« préparation (LLM) 91,4 s · bascule de modèle 2,0 s · génération (image) 414,8 s ».

        Les phases jamais ouvertes ne sont **pas** listées : écrire « bascule 0,0 s » quand la
        bascule n'a pas eu lieu (`vram.decharger_llm: false`) laisserait croire qu'elle est
        gratuite alors qu'elle n'a pas été payée."""
        morceaux = [f"{LIBELLES[c]} {self.secondes(c):.1f} s"
                    for c in ORDRE if self.phases[c].commencee]
        return " · ".join(morceaux) or "rien n'a encore commencé"

    def etat(self) -> dict:
        """Un dictionnaire plat, traversable par un signal Qt sans transporter d'objet."""
        return {
            "phase": self._ouverte,
            "libelle": self.libelle(),
            "fraction": self.fraction(),
            "images_faites": self.images_faites,
            "total_images": self.total_images,
            "annulation_demandee": self.annulation_demandee,
            "secondes": {c: round(self.secondes(c), 3) for c in ORDRE
                         if self.phases[c].commencee},
        }
