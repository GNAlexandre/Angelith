# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Temps restant d'un run, estimé sur le débit OBSERVÉ.

## Pourquoi

La barre disait « 12 / 131 (9 %) ». Sur un tome qui tourne des heures, le pourcentage
n'apprend pas ce qu'on veut savoir : est-ce que ça finit avant ce soir. Et la seule donnée
temporelle du projet, `SECONDES_PAR_RELETTRAGE`, décrit UNE étape — elle ne dit rien d'un run
qui traverse détection, OCR, traduction et rendu, dont les coûts par planche n'ont rien à
voir entre eux.

## Le débit observé, pas une constante

On mesure donc le run en cours. C'est la seule façon d'être juste sur des étages aussi
inégaux, et ça s'adapte tout seul à la machine, au modèle et au format du tome.

⚠ **Fenêtre glissante, pas moyenne depuis le début.** Un run manga change de régime en cours
de route : le balayage A ne fait aucun appel LLM, le balayage B en fait un par lot. Une
moyenne globale traînerait le régime précédent pendant des dizaines de planches et annoncerait
un temps faux avec l'aplomb d'un temps mesuré.

## Ce que ce module ne fait pas

Aucun import Qt. La règle de couche du dépôt : ce qui DÉCIDE se teste sans PySide6. Le widget
qui affiche vit dans `gui/bandeau.py`, et n'a qu'à poser les chaînes qu'on lui rend.

## Lot 32 — trois décisions d'affichage remontées ici

`lignes_de_run`, `titre_de_fenetre` et `resume_de_fin` sont dans ce module et pas dans le
widget pour la même raison : ce sont des DÉCISIONS (afficher un temps ou pas, un compte ou un
pourcentage, où poser la marque `[*]`), et une décision se teste sans boucle d'événements.
L'état qu'elles lisent vient de `core/progression.py`, qui ne connaît pas non plus Qt.
"""
from __future__ import annotations

import time
from typing import NamedTuple

#: Nombre d'échantillons de la fenêtre glissante. Assez pour lisser une planche
#: anormalement lente, assez peu pour suivre un changement de régime en moins d'une minute.
FENETRE = 12

#: En deçà, on ne dit rien. Deux points donnent un débit, mais un débit tiré de deux planches
#: dont l'une portait le chargement du modèle ONNX est une estimation inventée — et une
#: estimation fausse est pire que pas d'estimation, parce qu'on s'y fie.
MINIMUM = 4


class Estimateur:
    """Accumule `(instant, avancement)` et rend le temps restant, en secondes.

    Un seul objet pour toute la vie de la fenêtre ; `reinitialiser()` à chaque nouveau run."""

    def __init__(self, fenetre: int = FENETRE, minimum: int = MINIMUM, horloge=time.monotonic):
        self.fenetre = fenetre
        self.minimum = minimum
        # ⚠ `monotonic`, pas `time()` : un changement d'heure système — ou simplement l'heure
        # d'été — rendrait un temps restant négatif au milieu d'un run de nuit.
        self._horloge = horloge
        self._points: list[tuple[float, int]] = []

    def reinitialiser(self) -> None:
        self._points.clear()

    def noter(self, courant: int, total: int) -> None:
        """Enregistre un avancement. Les reculs et les répétitions sont ignorés."""
        if total <= 0 or courant <= 0:
            return
        if self._points and courant <= self._points[-1][1]:
            # Un run manga repasse par la planche 1 au balayage B : c'est un NOUVEAU régime,
            # et garder les points du précédent mélangerait deux débits sans rapport.
            if courant < self._points[-1][1]:
                self._points.clear()
            else:
                return
        self._points.append((self._horloge(), courant))
        del self._points[:-self.fenetre]

    def restant(self, total: int) -> float | None:
        """Secondes restantes estimées, ou `None` tant qu'on ne sait pas."""
        if total <= 0 or len(self._points) < self.minimum:
            return None
        (t0, c0), (t1, c1) = self._points[0], self._points[-1]
        if c1 <= c0 or t1 <= t0:
            return None
        secondes_par_unite = (t1 - t0) / (c1 - c0)
        return max(0.0, (total - c1) * secondes_par_unite)


def duree_lisible(secondes: float | None) -> str:
    """« 3 min », « 1 h 40 », « moins d'une minute ». Chaîne vide si on ne sait pas.

    Volontairement GROSSIER au-delà de l'heure : annoncer « 1 h 42 min 07 s » sur une
    estimation à ±20 % affiche une précision qu'on n'a pas."""
    if secondes is None:
        return ""
    if secondes < 60:
        return "moins d'une minute"
    minutes = int(secondes // 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d}"


# --------------------------------------------------------------------------- #
#  Ce que le bandeau de run AFFICHE — lot 32
# --------------------------------------------------------------------------- #
#
# Ces trois fonctions sont ici et pas dans un widget pour la règle de couche du dépôt : ce
# qui DÉCIDE se teste sans PySide6. `gui/bandeau.py` n'a plus qu'à poser des chaînes.

#: Résolution de la barre déterminée. Un `QProgressBar` raisonne en entiers ; mille pas
#: valent 0,1 % de run, soit dix fois plus fin que ce que l'œil distingue sur 300 px.
PAS_DE_BARRE = 1000


class Bandeau(NamedTuple):
    """Ce qu'il y a à écrire, une fois pour toutes.

    `determinee=False` veut dire `setRange(0, 0)` : la barre balaie, et **ni pourcentage ni
    temps restant** ne l'accompagnent — c'est la règle Microsoft citée par le `PLAN-32`
    §1.3, et elle est appliquée ici plutôt que dans le widget pour qu'un test sans Qt puisse
    la vérifier."""

    cible: str          # « Manga · Mon Manga / Vol.2 »
    phase: str          # « Traduction et rendu (5/6) »
    compte: str         # « planche 84 / 131 »
    restant: str        # « ~1 h 10 restantes », ou vide
    objet: str          # « page_0084.png · lot 80→99 · 3 planches par appel »
    determinee: bool
    valeur: int
    maximum: int


def lignes_de_run(etat: dict, cible: str = "") -> Bandeau:
    """Traduit l'état de `core/progression.py` en lignes affichables.

    ⚠ **Aucun pourcentage n'est produit, jamais**, et ce n'est pas un oubli. La fraction du
    dépôt est *comptée* et non *pondérée* (cf. `core/progression.POIDS_MESURES` : une seule
    phase sur sept passe la règle du facteur 3) — « 64 % » se lirait comme 64 % du temps,
    alors que la moitié des planches du balayage A ne coûte que ~32 % du run. Le compte,
    lui, porte son dénominateur, et c'est la règle des chiffres du dépôt : « un chiffre sans
    dénominateur n'est pas une mesure, c'est une impression »."""
    fraction = etat.get("fraction")
    determinee = fraction is not None
    courant = int(etat.get("courant") or 0)
    total = int(etat.get("total") or 0)
    unite = str(etat.get("unite") or "")
    rang, phases = int(etat.get("rang") or 0), int(etat.get("phases") or 0)

    phase = str(etat.get("phase_libelle") or "")
    if phase and phases:
        phase = f"{phase} ({rang}/{phases})"
    compte = ""
    if total > 0:
        compte = f"{unite} {courant} / {total}" if unite else f"{courant} / {total}"
    lisible = duree_lisible(etat.get("restant")) if determinee else ""
    return Bandeau(
        cible=cible, phase=phase, compte=compte,
        restant=f"~{lisible} restantes" if lisible else "",
        objet=str(etat.get("objet") or ""),
        determinee=determinee,
        valeur=int(round((fraction or 0.0) * PAS_DE_BARRE)) if determinee else 0,
        maximum=PAS_DE_BARRE if determinee else 0)


def titre_de_fenetre(base: str, etat: dict | None = None, cible: str = "") -> str:
    """Le titre, avec l'avancement EN TÊTE — pour la barre des tâches.

    Microsoft : « optimize the title for display on the taskbar by concisely placing the
    distinguishing information first ». Son exemple est « 66% Complete » ; on met le COMPTE,
    « 84/131 », pour la même raison que `lignes_de_run` refuse le pourcentage — un chiffre
    porte son dénominateur ou n'est pas une mesure.

    ⚠ **`[*]` est un emplacement, pas un décor.** C'est là que Qt insère la marque
    « document modifié » (`setWindowModified`). Il doit rester présent exactement une fois,
    et le préfixe se pose donc DEVANT la base plutôt que par une recomposition du gabarit :
    une concaténation naïve qui perdrait `[*]` ferait disparaître silencieusement la seule
    marque de travail non enregistré."""
    if not etat:
        return base
    courant = int(etat.get("courant") or 0)
    total = int(etat.get("total") or 0)
    tete = f"{courant}/{total}" if total > 0 else str(etat.get("phase_libelle") or "")
    if not tete:
        return base
    if cible:
        tete = f"{tete} — {cible}"
    return f"{tete} — {base}"


def resume_de_fin(*, unites: int, unite: str, secondes: float | None,
                  avertissements: int, succes: bool = True) -> str:
    """« Terminé — 131 planches, 2 h 14, 3 avertissements ».

    Un run de nuit finit à 3 h du matin et ne laissait qu'une ligne dans un journal replié.
    Ce résumé reste **dans le bandeau**, sans voler le focus : pas de boîte modale à la fin
    d'un run, parce que l'utilisateur peut être en train de taper une réplique dans la
    retouche et qu'un dialogue qui surgit avale la frappe."""
    morceaux = []
    if unites > 0:
        morceaux.append(f"{unites} {unite}{'s' if unites > 1 and unite else ''}")
    duree = duree_lisible(secondes)
    if duree:
        morceaux.append(duree)
    if avertissements > 0:
        morceaux.append(f"{avertissements} avertissement{'s' if avertissements > 1 else ''}")
    tete = "Terminé" if succes else "Arrêté"
    return f"{tete} — " + ", ".join(morceaux) if morceaux else tete
