# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Moteur de garde-fous : plafond de sortie, retry à température corrigée, registre de motifs.

## Ce qui est partagé, et ce qui ne peut pas l'être

Le moteur est **agnostique des CONTRÔLES**, pas « agnostique de l'unité de travail ». La
nuance est ce qui rend l'extraction possible. Sur les huit motifs d'échec du light novel,
trois seulement sont universels (`vide`, `emballement`, `repetition`), un l'est à moitié
(`perte_mots`) et trois sont ancrés dans des artefacts light novel : `troncature_image` lit
`<!-- IMG: -->`, `titre_perdu` lit les titres ATX, `styleguide_fuite` lit un guide de style
que le manga n'injecte jamais. Surtout, aucun ne couvre l'échec dominant du manga
(`bulles_manquantes`). Une fonction « unit-agnostic » qui aurait voulu couvrir les deux
briques aurait fini avec un `if is_manga:` dedans.

Chaque brique fournit donc son **registre ordonné de `(nom, prédicat)`** et son propre type
de contexte ; le moteur ne voit qu'un `diagnostiquer(sortie) -> nom | None`. Il ne connaît
ni bulles ni blocs, ni pixels ni titres.

## Découplage d'`Agent.run`

Le moteur prend un `call(temperature) -> str` et non un agent. Les deux signatures
divergeaient — `MangaAgent.run` ajoute `images=` — et surtout, prendre un agent rendait le
moteur intestable sans LLM. Avec un callable, les deux briques le testent avec une fonction
de trois lignes.
"""
from __future__ import annotations

from . import tokens

# Motifs pour lesquels le retry RELÈVE la température au lieu de la baisser. La
# dégénérescence en boucle est une pathologie de BASSE température (le modèle re-choisit
# indéfiniment la continuation la plus probable) : le retry historique à `température × 0.4`
# la rendait donc PLUS probable — vérifié sur roman D Vol.1, où les deux appels
# de chaque bloc perdu ont bouclé (temps et tokens doublés dans perf.log).
MOTIFS_PLUS_CHAUD = frozenset({"repetition"})


#: Plafond DUR du plafond de sortie. L'atteindre signifie que la découpe est mal
#: dimensionnée pour la langue : sur un pivot latin il faudrait 12 000 caractères dans un
#: bloc, ce que `max_block_chars` interdit — il n'est donc atteignable qu'en CJK.
CEIL_DEFAUT = 6000


def out_cap(ref_text: str, mult: float = 2.0, floor: int = 768, ceil: int = CEIL_DEFAUT) -> int:
    """Plafond de tokens de SORTIE, proportionné à l'entrée (anti-emballement) :
    un bloc ne doit jamais générer 10×-20× sa taille. Sature → l'appelant retombe
    sur le texte source."""
    return max(floor, min(ceil, int(tokens.estimate(ref_text) * mult) + 256))


def premier_motif(motifs, contexte) -> str | None:
    """Nom du premier motif qui s'applique, ou `None` si la sortie est exploitable.

    `motifs` est ORDONNÉ, du plus grossier au plus fin : une sortie vide ne doit pas être
    diagnostiquée « japonais résiduel ». Le contexte est le type de la brique — le moteur ne
    l'inspecte jamais, il le passe."""
    for nom, predicat in motifs:
        if predicat(contexte):
            return nom
    return None


def try_with_temp_retry(call, diagnostiquer, *, stats: dict | None = None,
                        temperature: float = 0.3, temp_factor: float = 0.4,
                        max_retries: int = 1, cle_ok: str = "blocs_ok",
                        motifs_plus_chaud=MOTIFS_PLUS_CHAUD,
                        prefere=None) -> tuple[str, bool, str | None]:
    """Appelle `call(temperature)`, diagnostique, et RETENTE à température corrigée.

    Renvoie `(texte, ok, motif)`. `ok=False` signifie qu'aucune tentative n'a produit de
    sortie exploitable — l'appelant décide alors quoi conserver, et le motif part au rapport.
    Le motif rendu est celui du PREMIER essai : c'est lui qui décrit ce qui a réellement
    dérapé, et c'est sous lui que le compteur est incrémenté.

    Sens de la correction : on RÉDUIT la température, ce qui resserre un modèle qui divague ;
    sauf pour `motifs_plus_chaud`, où on la RELÈVE (cf. le commentaire de
    `MOTIFS_PLUS_CHAUD`). La direction est recalculée à CHAQUE essai à partir du motif du
    précédent, pas figée au premier.

    `prefere(sortie_gardee, motif_garde, candidate, motif_candidate) -> bool` décide si une
    tentative ratée est meilleure que celle déjà gardée — « meilleure » n'ayant pas le même
    sens selon la brique (nombre de mots récupérables pour un bloc de récit, nombre de
    répliques numérotées pour une planche). `None` = on garde toujours la première.
    """
    st = stats if stats is not None else {}

    sortie = call(None)
    motif = diagnostiquer(sortie)
    if motif is None:
        st[cle_ok] = st.get(cle_ok, 0) + 1
        return sortie, True, None

    meilleure, motif_meilleure, motif_initial = sortie, motif, motif
    for _essai in range(max(0, int(max_retries))):
        if motif in motifs_plus_chaud:
            temp = min(1.0, max(temperature, 0.2) / max(0.05, temp_factor))
            st["retry_temp_relevee"] = st.get("retry_temp_relevee", 0) + 1
        else:
            temp = max(0.05, temperature * temp_factor)
            st["retry_temp_reduite"] = st.get("retry_temp_reduite", 0) + 1
        suivante = call(temp)
        motif_suivant = diagnostiquer(suivante)
        if motif_suivant is None:
            st["recupere_par_retry"] = st.get("recupere_par_retry", 0) + 1
            st[cle_ok] = st.get(cle_ok, 0) + 1
            return suivante, True, None
        if prefere is not None and prefere(meilleure, motif_meilleure, suivante, motif_suivant):
            meilleure, motif_meilleure = suivante, motif_suivant
        motif = motif_suivant

    st[motif_initial] = st.get(motif_initial, 0) + 1
    return meilleure, False, motif_initial
