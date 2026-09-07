# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les fragments de message que le chemin manga **assemble lui-même**, hors de `prompts/`.

## Pourquoi ce module existe, et pourquoi il arrive AVANT le reste du lot

`docs/mesures/inventaire-couplage-fr.md` §5.2 avait relevé dix sites du chemin manga qui construisent
un morceau de prompt en dur, en français, dans du Python : six f-strings et quatre chaînes
fixes, plus deux dans `traduction_unitaire`. Un seul était surchargeable par un pack de langue
(`traduction_unitaire.CLE_CONSIGNE`).

Le lot 15 ajoute à l'énoncé la **structure de la planche**, le **type de bulle** et
l'**étiquette de locuteur**. Écrire ces nouvelles consignes en dur reviendrait à porter
l'inventaire de dix sites à seize et à refaire, dans deux versions, le travail que la 1.9.0
avait déjà fait une fois — `docs/roadmap.md` raconte qu'elle y avait « trouvé six instructions
codées en Python plutôt que vivant dans `prompts/` ». D'où l'ordre : externaliser d'abord,
enrichir ensuite.

## Ce que ce module n'est PAS

**Ce n'est pas une copie du pack français.** Le texte français reste ici, à son site d'appel,
exactement comme `traduction_unitaire.CONSIGNE` : c'est ce qui rend l'identité de sortie du
mode compatibilité vraie *par construction* et non par vigilance (cf.
`core.langues.Pack.consigne`). `langues/fr/pack.yaml` continue de déclarer `consignes: {}`.

**Ce n'est pas non plus un prompt système.** Ces fragments sont injectés dans un MESSAGE, et
conditionnellement — il n'y a pas de ligne de gabarit sans bbox exploitable, pas de séparateur
de planche hors du mode par lots.

## Le gabarit et son garde-fou

Un fragment porte des champs (`{langue}`, `{planche}`, `{budget}`). Un pack qui déclare un
gabarit avec un champ inconnu ou une accolade mal fermée casserait donc l'appel — au milieu
d'un run de six heures, ce qui est le pire moment. `verifier()` rend chaque gabarit du pack
UNE fois au démarrage, avec des valeurs factices, et refuse le pack sur le même modèle que
`core.langues._verifier_prompts` : « aucun repli silencieux vers le français ».
"""
from __future__ import annotations

from core.langues import ErreurPack

# ─────────────────────────────────────────────────────────────────────────────
# Les textes français, à leur site d'appel
# ─────────────────────────────────────────────────────────────────────────────

#: Une ligne de gabarit de bulle. `{numero}` suit la numérotation CONTINUE du lot.
GABARIT_LIGNE = "{numero}. {largeur}×{hauteur} px — viser ≤ {budget} caractères"

#: En-tête du bloc de gabarits. ⚠ Réécrit par L7.8 : la place est une CONTRAINTE de mise en
#: page, jamais un objectif de traduction. L'ancienne formule (« dépasser force une police
#: illisible ») ne disait que la moitié qui pousse à couper, et rien ne mesurait l'autre — le
#: registre de `quality_manga` ne bornait que par le haut.
GABARITS_ENTETE = (
    "Place disponible par bulle — c'est une contrainte de mise en page, pas un objectif :\n"
    "dépasser force une police illisible, mais ABRÉGER LE SENS est pire. Quand une réplique "
    "fidèle ne tient pas, rends-la fidèle : le lettrage sait signaler un débordement, il ne "
    "sait pas deviner ce que tu as coupé.")

SEPARATEUR_PLANCHE = "— Planche {planche} (bulles {debut} à {fin}) —"

LOT_CONSIGNE = (
    "{planches} planches consécutives, {bulles} bulles au total. La numérotation est "
    "CONTINUE d'une planche à l'autre : rends exactement {bulles} lignes numérotées de 1 "
    "à {bulles}, sans répéter les séparateurs de planche.")

PRECEDENTES_ENTETE = "Répliques des planches précédentes (contexte, NE PAS retraduire) :"

#: Une ligne de contexte inter-planches. ⚠ ÉTIQUETÉE depuis L7.1 : une liste à tirets sans
#: origine est une amorce lexicale, pas un fil de dialogue.
PRECEDENTE_LIGNE = "- {origine} : {texte}"

BULLES_ENTETE = "Bulles détectées, en {langue} (ordre de lecture, {ordre}) :"

ECHANTILLON_ENTETE = "Échantillon du texte en {langue} du tome :"

HORS_BULLE_ENTETE = "Zones de texte hors bulle, en {langue} (ordre de lecture, {ordre}) :"

#: Consigne de LECTURE des zones hors bulle (lot 21, L21.3, voie A). Elle ne demande pas une
#: traduction mais une TRANSCRIPTION, parce que c'est une seconde voie de lecture destinée à
#: être confrontée à celle de `manga-ocr` (`sfx_lecture.verdict`) — traduire d'abord rendrait
#: les deux lectures incomparables.
#:
#: ⚠ « rends une ligne vide » est la partie qui compte. Un modèle sommé de lire quelque chose
#: lit toujours quelque chose : c'est exactement le défaut de `manga-ocr` qu'on cherche à ne
#: pas reproduire dans la seconde voie, faute de quoi les deux voies concorderaient sur du
#: dessin.
SFX_LECTURE_ENTETE = (
    "Les images jointes sont des zones de texte découpées dans une planche de bande "
    "dessinée, en {langue}. Pour chacune, TRANSCRIS les caractères que tu vois — ne traduis "
    "pas, ne commente pas, n'interprète pas.\n"
    "Si une image ne porte aucun texte lisible (du dessin, un aplat, un fragment de trait), "
    "rends une LIGNE VIDE après son numéro : c'est une réponse juste, et de loin la plus "
    "utile.\n"
    "Réponds par exactement {zones} lignes numérotées « N. transcription », dans l'ordre, "
    "sans aucun autre texte."
)

ORDRE_DROITE_GAUCHE = "droite → gauche puis haut → bas"
ORDRE_GAUCHE_DROITE = "gauche → droite puis haut → bas"

UNITAIRE_PLACE = "Place disponible : {largeur}×{hauteur} px — viser ≤ {budget} caractères."
UNITAIRE_REPLIQUE = "Réplique en {langue} :"

# ─────────────────────────────────────────────────────────────────────────────
# Ce que le lot 15 ajoute à l'énoncé
# ─────────────────────────────────────────────────────────────────────────────

#: Séparateur de groupe dans la liste de bulles (L7.2).
#:
#: ⚠ Le mot « case » est un ABUS DE LANGAGE et il ne doit pas apparaître : `ocr._coupe_xy` ne
#: détecte aucune case, il coupe des gouttières. Annoncer des cases ferait inférer au modèle
#: une précision qui n'existe pas.
GROUPE_ENTETE = "— Groupe {groupe} —"

#: Note qui dit au modèle CE QUE VALENT les annotations. Injectée seulement quand il y en a.
#:
#: ⚠ Les trois phrases sont calibrées sur ce que le pipeline sait réellement : des groupes
#: (pas des cases), un type (parfois indéterminé, et alors absent), une étiquette de locuteur
#: LOCALE à la planche et seulement probable.
STRUCTURE_NOTE = (
    "Lecture des annotations de cette planche :\n"
    "- « — Groupe N — » sépare des blocs de bulles séparés par une rupture de mise en page. "
    "Ce ne sont pas des cases détectées : une réplique en tête de groupe est souvent une "
    "nouvelle prise de parole ou un changement de plan, ne continue pas la phrase précédente "
    "par-dessus la rupture.\n"
    # ⚠ « voix intérieure » et non « italique » : le lettrage manga n'a pas de style italique
    # pour une bulle, et demander une forme que le rendu ne sait pas produire ferait sortir
    # des astérisques ou des soulignés dessinés dans la bulle.
    "- « (pensée) », « (récitatif) », « (cri) » qualifient la FORME de la bulle, pas son "
    "contenu : une pensée s'écrit en voix intérieure, un récitatif sur un ton narratif et non "
    "parlé, un cri court et sec. Une bulle sans mention est un dialogue ordinaire, ou une "
    "forme que rien ne permettait de décider : traite-la normalement, ne devine pas.\n"
    "- « [A] », « [B] » sont des locuteurs PROBABLES, déduits de la direction des queues de "
    "bulle, et valables sur cette planche seulement. Deux bulles marquées [A] sont "
    "probablement la même personne, deux marques différentes probablement un échange. "
    "Sers-t'en pour le tutoiement, les accords et les pronoms — jamais pour inventer un nom.")

#: Mentions de type de bulle, telles qu'elles sont écrites dans l'énoncé (L7.3). La clé est le
#: nom interne de `planche.TYPES` ; `dialogue` et `indetermine` n'écrivent RIEN, et c'est le
#: point : un type mal deviné est pire qu'aucun type.
#:
#: ⚠ Ce sont des fragments de MESSAGE comme les autres, donc surchargeables par un pack — sans
#: quoi un run anglais recevrait « (pensée) » au milieu d'un prompt anglais. Elles passent par
#: `mention_de_type()` et non par cette table directement.
TYPES_MENTION = {
    "pensee": "(pensée)",
    "recitatif": "(récitatif)",
    "cri": "(cri)",
}

#: Origine d'une réplique de contexte inter-planches (L7.1). `{ecart}` vaut 1 pour la planche
#: précédente, 3 pour l'avant-avant-précédente.
ORIGINE_PLANCHE = "Planche N−{ecart}"

#: Appariement image ↔ planche en mode lot (L7.6). Sans lui, rien dans le texte ne relie
#: l'image *k* à une planche, et un `image_b64` nul décalait tout le reste.
IMAGE_PLANCHE = "L'image jointe n° {rang} est la planche {planche}."

#: Même chose pour les zones hors bulle (L7.7), où l'appariement est avec la ligne numérotée.
IMAGE_ZONE = "L'image jointe n° {rang} est la zone {rang}."

#: En-tête de la seconde tentative en mode « cible » (L7.6) : on ne joint pas la planche mais
#: les crops des groupes que le premier essai a ratés.
CROPS_ENTETE = ("Le premier essai sur cette planche a été refusé par un garde-fou. Les images "
                "jointes sont les zones de la planche, dans l'ordre des groupes : sers-t'en "
                "pour lire ce que l'OCR a mal rendu.")

# ── Relecture à mandat étroit (L7.9) ─────────────────────────────────────────
#
# ⚠ La consigne PRINCIPALE du relecteur n'est pas ici mais dans `manga/relecture.py`, sous
# `relecture.CONSIGNE` / `relecture.CLE_CONSIGNE` — même patron que `traduction_unitaire` :
# le texte français reste au site d'appel qui l'emploie. Ne vivent ici que les trois en-têtes
# qui assemblent le message autour d'elle.

RELECTEUR_MANQUES = "Termes du glossaire présents dans la source et absents du rendu :"
RELECTEUR_MANQUE_LIGNE = "- bulle {bulle} : « {source} » devrait rendre « {nom} »"
RELECTEUR_SOURCE = "Source, dans l'ordre de lecture :"
RELECTEUR_RENDU = "Traduction en place :"

# ─────────────────────────────────────────────────────────────────────────────
# Résolution
# ─────────────────────────────────────────────────────────────────────────────

#: Nom de la clé de pack pour chaque constante ci-dessus. La table est ici plutôt que dans
#: `core.langues` parce que ces clés sont celles d'UNE brique : le socle en déclare la liste
#: (`CONSIGNES_CONNUES`) pour valider un `pack.yaml`, il n'en connaît pas le texte.
CLES: dict[str, str] = {
    "manga_gabarit_ligne": GABARIT_LIGNE,
    "manga_gabarits_entete": GABARITS_ENTETE,
    "manga_separateur_planche": SEPARATEUR_PLANCHE,
    "manga_lot_consigne": LOT_CONSIGNE,
    "manga_precedentes_entete": PRECEDENTES_ENTETE,
    "manga_precedente_ligne": PRECEDENTE_LIGNE,
    "manga_bulles_entete": BULLES_ENTETE,
    "manga_echantillon_entete": ECHANTILLON_ENTETE,
    "manga_hors_bulle_entete": HORS_BULLE_ENTETE,
    "manga_sfx_lecture_entete": SFX_LECTURE_ENTETE,
    "manga_ordre_droite_gauche": ORDRE_DROITE_GAUCHE,
    "manga_ordre_gauche_droite": ORDRE_GAUCHE_DROITE,
    "manga_groupe_entete": GROUPE_ENTETE,
    "manga_structure_note": STRUCTURE_NOTE,
    "manga_image_planche": IMAGE_PLANCHE,
    "manga_image_zone": IMAGE_ZONE,
    "manga_origine_planche": ORIGINE_PLANCHE,
    "manga_type_pensee": TYPES_MENTION["pensee"],
    "manga_type_recitatif": TYPES_MENTION["recitatif"],
    "manga_type_cri": TYPES_MENTION["cri"],
    "manga_relecteur_manques": RELECTEUR_MANQUES,
    "manga_relecteur_manque_ligne": RELECTEUR_MANQUE_LIGNE,
    "manga_relecteur_source": RELECTEUR_SOURCE,
    "manga_relecteur_rendu": RELECTEUR_RENDU,
    "manga_crops_entete": CROPS_ENTETE,
    "traduction_unitaire_place": UNITAIRE_PLACE,
    "traduction_unitaire_replique": UNITAIRE_REPLIQUE,
}

#: Valeurs factices utilisées par `verifier()`. Un champ absent d'ici est un champ que le
#: code ne fournit jamais : le pack qui l'emploie sera donc refusé, ce qui est voulu.
_FACTICES = {
    "numero": 1, "largeur": 100, "hauteur": 100, "budget": 12,
    "planche": 1, "debut": 1, "fin": 1, "planches": 2, "bulles": 4,
    "langue": "japonais", "ordre": ORDRE_DROITE_GAUCHE,
    "zones": 3,
    "groupe": 1, "rang": 1, "ecart": 1, "origine": "Planche N−1", "texte": "…",
    "bulle": 1, "source": "…", "nom": "…",
}


def mention_de_type(pack, type_bulle: str) -> str:
    """La mention `(pensée)` / `(récitatif)` / `(cri)`, dans la langue du pack.

    `""` pour `dialogue` et `indetermine`, et c'est le point du lot : un type mal deviné est
    pire qu'aucun type, donc les deux classes qui ne tranchent rien n'écrivent rien."""
    if type_bulle not in TYPES_MENTION:
        return ""
    return texte(pack, f"manga_type_{type_bulle}")


def texte(pack, cle: str, **champs) -> str:
    """Le fragment `cle`, dans la langue du pack, ses champs remplis.

    `pack=None` sert le texte français : c'est le cas des appels de test et de l'éditeur
    graphique, qui n'a pas toujours de pack sous la main.

    ⚠ Ne lève pas sur un gabarit fautif — `verifier()` l'a déjà fait au démarrage, et
    remonter une `KeyError` depuis le milieu d'un lot ne dirait rien d'utile. Un gabarit qui
    aurait échappé à la vérification retombe sur le français, visiblement."""
    defaut = CLES[cle]
    gabarit = pack.consigne(cle, defaut) if pack is not None else defaut
    try:
        return gabarit.format(**champs) if champs else gabarit
    except (KeyError, IndexError, ValueError):
        return defaut.format(**champs) if champs else defaut


def libelle_ordre(sens: str, pack=None) -> str:
    """Comment DIRE au modèle l'ordre dans lequel les bulles lui arrivent.

    Le prompt annonçait « droite → gauche » en dur. Sur un webtoon, numéroté gauche→droite,
    cette phrase décrit l'inverse de ce qu'il reçoit — et invite à réordonner ce qui est déjà
    dans le bon ordre."""
    cle = ("manga_ordre_gauche_droite" if str(sens) == "gauche_droite"
           else "manga_ordre_droite_gauche")
    return texte(pack, cle)


def verifier(pack) -> None:
    """Rend chaque gabarit du pack une fois, avec des valeurs factices. Lève `ErreurPack`.

    ⚠ Au DÉMARRAGE, pas à l'usage. Un pack dont `manga_separateur_planche` porte `{page}` au
    lieu de `{planche}` produirait sinon un `KeyError` au premier lot groupé — c'est-à-dire
    après la détection, le nettoyage et l'OCR de vingt planches. Le dépôt refuse déjà un pack
    à qui il manque un prompt pour exactement cette raison."""
    if pack is None:
        return
    fautifs: list[tuple[str, str]] = []
    for cle, defaut in CLES.items():
        gabarit = pack.consigne(cle, defaut)
        if gabarit == defaut:
            continue                      # non déclaré : c'est le texte du dépôt, il est bon
        try:
            gabarit.format(**_FACTICES)
        except (KeyError, IndexError, ValueError) as err:
            fautifs.append((cle, str(err)))
    if fautifs:
        raise ErreurPack(
            f"pack de langue « {getattr(pack, 'code', '?')} » : "
            f"{len(fautifs)} consigne(s) manga au gabarit invalide.\n"
            + "".join(f"  → {cle} : champ ou accolade fautif ({err})\n" for cle, err in fautifs)
            + "  Champs disponibles : "
            + ", ".join("{" + c + "}" for c in sorted(_FACTICES)) + "\n"
            + "  Un gabarit fautif ne se découvrirait qu'au premier appel de traduction, "
              "après des heures de détection et d'OCR : on refuse au démarrage.")
