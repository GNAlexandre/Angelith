# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Vérifie A POSTERIORI que la traduction a suivi le registre annoncé. **Aucun appel LLM.**

## Le défaut

`_passe_contexte` fait écrire au modèle une fiche de tome qui dit, entre autres, « X vouvoie
Y ». Cette fiche est ensuite injectée dans le prompt de chaque planche. **Rien n'a jamais
vérifié que la traduction l'avait suivie** — et rien ne pouvait le faire, puisque le seul
juge disponible aurait été un second appel LLM, c'est-à-dire un coût par planche pour un
contrôle qu'un lexique suffit à rendre.

Or c'est vérifiable lexicalement : les formes de deuxième personne du singulier et du pluriel
sont un **ensemble fini**. Un compteur par planche, un basculement signalé au rapport.

## Le patron, et pourquoi c'est celui-là

C'est exactement celui des dérives d'orthographe T1/T2/T3 (`terminology.py`) : purement
lexical, donc **actif même quand `manga_contexte` ne l'est pas**, donc mesurable sur les
tomes déjà produits sans rien relancer. C'est aussi ce qui rend la fiche de registre
**évaluable** : jusqu'ici, même branchée, on ne pouvait pas savoir si elle servait.

## Ce que ce module ne fait PAS

Il ne **corrige** rien. Un basculement de registre peut être délibéré — deux personnages qui
passent au tutoiement au milieu d'un tome, c'est une scène, pas une faute. Il compte, il
signale, et c'est un humain qui tranche. Le dépôt applique déjà cette distinction aux dérives
lexicales : T3 « signalé au rapport, jamais écrit ».

## Le lexique vit ici, pas dans `core/`

⚠ Et c'est un arbitrage, pas un oubli. Ces formes sont celles de la langue **cible**, donc
la même famille que `core.glossary_force.AccordFrancais` — mais le socle n'a pas de client
pour elles : le light novel n'a ni bulle ni planche, donc aucune unité sur laquelle compter
un basculement. Les remonter dans `core/` y ferait entrer une mesure que seule la brique
manga sait faire, ce que `tests/test_core_cli.py` interdit dans l'autre sens. La table est
donc indexée par **code de pack**, prête à monter si un second appelant apparaît.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TUTOIEMENT = "tu"
VOUVOIEMENT = "vous"

#: Marqueurs de deuxième personne, par code de langue cible.
#:
#: ⚠ Deux pièges, et ils décident de l'utilité du compteur.
#:
#: · **« vous » est ambigu** : c'est le vouvoiement de politesse ET le pluriel ordinaire.
#:   Une réplique adressée à un groupe compte donc à tort comme un vouvoiement. On ne peut
#:   pas lever l'ambiguïté sans savoir à combien de personnes on parle — c'est justement ce
#:   que la fiche de registre dit, et qu'un lexique ne sait pas lire. D'où le seuil de
#:   `basculements` : on ne signale qu'un tome où les DEUX registres sont franchement
#:   présents, jamais une planche isolée.
#: · **`tu` est un mot court et fréquent en composition** (« statue », « vertu ») : d'où des
#:   motifs ancrés sur des frontières de mot, jamais une recherche de sous-chaîne.
#:
#: L'anglais n'a qu'une deuxième personne : son entrée est VIDE, et « ne rien mesurer » y est
#: la réponse complète — la même que `AccordNeutre` donne à l'accord.
MARQUEURS: dict[str, dict[str, str]] = {
    "fr": {
        TUTOIEMENT: r"\b(?:tu|t'(?=[aeiouyéèêàâîïôûh])|te|toi|ton|ta|tes|tien(?:ne)?s?)\b",
        VOUVOIEMENT: r"\b(?:vous|votre|vos|vôtres?)\b",
    },
    "en": {},
}

_COMPILES: dict[tuple[str, str], re.Pattern] = {}


def _motif(code: str, registre: str) -> re.Pattern | None:
    table = MARQUEURS.get((code or "fr").strip().lower())
    if table is None:
        table = MARQUEURS["fr"]          # même défaut que `ACCORD_DEFAUT` : le français
    brut = table.get(registre)
    if not brut:
        return None
    cle = (code, registre)
    if cle not in _COMPILES:
        _COMPILES[cle] = re.compile(brut, re.IGNORECASE)
    return _COMPILES[cle]


def detecter(texte: str, code: str = "fr") -> str:
    """Registre d'UNE réplique : `"tu"`, `"vous"` ou `""`.

    Une réplique qui porte les deux rend `""` : c'est soit un dialogue rapporté, soit un
    « vous » pluriel dans une réplique tutoyée. Compter les deux la ferait peser dans les
    deux plateaux, et le basculement qu'on cherche n'est pas là."""
    t = texte or ""
    mt = _motif(code, TUTOIEMENT)
    mv = _motif(code, VOUVOIEMENT)
    a = bool(mt and mt.search(t))
    b = bool(mv and mv.search(t))
    if a == b:
        return ""
    return TUTOIEMENT if a else VOUVOIEMENT


@dataclass
class Releve:
    """Ce qu'un tome a réellement écrit en matière de registre."""
    tutoiement: int = 0
    vouvoiement: int = 0
    #: Planches où les DEUX registres coexistent — le signal le plus actionnable : dans une
    #: même planche, deux répliques d'une même scène ne devraient pas basculer.
    planches_mixtes: list[int] = field(default_factory=list)
    #: Planches consécutives (porteuses) dont le registre dominant a changé.
    basculements: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.tutoiement + self.vouvoiement

    def dominant(self) -> str:
        if self.tutoiement == self.vouvoiement:
            return ""
        return TUTOIEMENT if self.tutoiement > self.vouvoiement else VOUVOIEMENT

    def en_json(self) -> dict:
        return {"tutoiement": self.tutoiement, "vouvoiement": self.vouvoiement,
                "planches_mixtes": list(self.planches_mixtes),
                "basculements": list(self.basculements)}


def relever_planche(repliques: list[str] | None, code: str = "fr") -> dict[str, int]:
    """Compte par registre sur une planche. `{}` si la langue cible n'en a pas."""
    if not _motif(code, TUTOIEMENT):
        return {}
    compte = {TUTOIEMENT: 0, VOUVOIEMENT: 0}
    for t in repliques or []:
        r = detecter(t, code)
        if r:
            compte[r] += 1
    return compte


def relever_tome(par_planche: dict[int, dict[str, int]]) -> Releve:
    """Agrège les comptes de planche en un relevé de tome.

    Le **basculement** se lit sur les planches PORTEUSES seulement : une planche muette entre
    deux planches vouvoyées n'est pas un changement de registre, et la compter en ferait un.
    C'est la même précaution que `_contexte_precedent`, qui saute les répliques vides."""
    releve = Releve()
    precedent = ""
    for page in sorted(par_planche):
        compte = par_planche[page] or {}
        tu = int(compte.get(TUTOIEMENT, 0))
        vous = int(compte.get(VOUVOIEMENT, 0))
        releve.tutoiement += tu
        releve.vouvoiement += vous
        if tu and vous:
            releve.planches_mixtes.append(page)
        if tu == vous:
            continue                     # planche muette ou indécise : ne fait pas basculer
        dominant = TUTOIEMENT if tu > vous else VOUVOIEMENT
        if precedent and dominant != precedent:
            releve.basculements.append(page)
        precedent = dominant
    return releve
