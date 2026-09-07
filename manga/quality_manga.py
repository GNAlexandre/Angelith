# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Garde-fous de la traduction manga : plafond de sortie, diagnostic d'échec, retry à
température corrigée.

Avant ce lot, la traduction manga n'avait **aucun** garde-fou : un appel LLM par page, sans
`max_tokens`, sans diagnostic, sans retry, sans rapport — là où le pipeline light novel
dispose de sept motifs d'échec, d'un retry à température corrigée, d'un plafond de sortie et
d'un `RAPPORT.md`.

**Pourquoi un registre propre au manga, et pas les sept motifs du LN.** Sur les sept, trois
seulement sont universels (`vide`, `emballement`, `repetition`) et trois sont ancrés dans des
artefacts light novel : `troncature_image` lit `<!-- IMG: -->`, `titre_perdu` lit les titres
ATX, `styleguide_fuite` lit un guide de style que le manga n'injecte jamais. Surtout, ils ne
couvrent pas l'échec **dominant** du manga, aujourd'hui totalement silencieux (cf.
`bulles_manquantes`). D'où un registre ordonné de `(nom, prédicat)` que la brique fournit —
plutôt qu'une fonction « agnostique de l'unité » qui finirait avec un `if is_manga:` dedans.

Le moteur `try_with_temp_retry` ne prend pas d'`Agent` mais un **callable**
`call(temperature) -> str` : zéro couplage aux pixels, et il devient testable sans LLM. C'est
la forme visée par l'extraction vers `core/quality.py` (lot 2), pour que celle-ci soit un
déplacement et non une réécriture.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core import quality, tokens

# Ligne numérotée « 1. … » ou « 1) … » telle que le prompt la demande.
#
# ⚠ Cette expression est la SEULE de tout le projet : le diagnostic (`_bulles_manquantes`) et
# la reconstruction (`orchestrator_manga._parse_translations`) en avaient chacun une copie, et
# deux jumelles qui peuvent diverger sont un décalage de répliques en puissance. La
# reconstruction est désormais `repliques_par_bulle`, ici même, et l'orchestrateur la délègue.
#
# ⚠ Le séparateur doit être suivi d'une ESPACE ou de la fin de ligne. Sans cela, la page 8 du
# Vol.1 du *manga A* — une bulle de récitatif contenant « 1972... » — se lit comme la
# réplique n° 1972 suivie de « .. », et le retrait du préfixe la réduirait à deux points.
# ⚠ Le `$` est écrit dans LES DEUX branches de l'alternative, alors qu'une seule le portait.
# La portée était déjà celle-là — `(.*)` ne franchit pas de fin de ligne — mais rien ne le
# disait, et un lecteur devait dériver la précédence de l'alternative pour s'en convaincre.
# Équivalence vérifiée sur les dix formes que le module rencontre, « 1972... » compris.
_LIGNE_NUM = re.compile(r"^\s*(\d+)[.)](?:\s+(.*)$|\s*$)")

# Au-delà, un nombre n'est plus un index de bulle mais du texte : la planche la plus peuplée
# du tome en compte 13. Sert quand le nombre de bulles n'est pas connu de l'appelant.
_MAX_INDEX_BULLE = 99

# Motifs pour lesquels on RELÈVE la température au lieu de la baisser : sur une boucle
# dégénérée, resserrer le modèle renforce le cycle au lieu de le casser. Même ensemble que
# le light novel — c'est une propriété du modèle, pas de l'unité de travail — d'où le défaut
# du socle, repris ici sous son nom historique.
MOTIFS_PLUS_CHAUD = quality.MOTIFS_PLUS_CHAUD

#: ⚠ La clé reste `japonais_residuel` alors que le motif couvre désormais TOUTE langue
#: source : elle est PERSISTÉE dans les `qa.json` et les `RAPPORT.md` déjà écrits. La
#: renommer sur le disque rendrait illisibles des mois d'archives pour un gain cosmétique.
#: Le libellé, lui, est calculé (cf. `libelle`) et nomme la vraie langue.
MOTIF_SOURCE_RESIDUELLE = "japonais_residuel"

LIBELLES = {
    "vide": "réponse vide du modèle",
    "bulles_manquantes": "numérotation incomplète (risque de décalage des répliques)",
    "japonais_residuel": "du texte source est resté dans la sortie",
    "repetition": "le modèle a bouclé (même réplique répétée)",
    "emballement": "la sortie sature le plafond de tokens",
    "bulle_trop_longue": "une réplique est disproportionnée par rapport à sa bulle source",
    "bulle_trop_courte": "une réplique est trop courte pour sa source (contenu perdu)",
    "sfx_broderie": "une onomatopée a été rendue par une phrase inventée",
}


def libelle(motif: str | None, langue: str | None = None) -> str:
    """Libellé lisible d'un motif, la langue source nommée quand elle est connue.

    « du japonais est resté dans la sortie » sur un chapitre anglais envoyait chercher un
    problème qui n'existait pas — c'est exactement ce qu'a fait le rapport du run raté."""
    if not motif:
        return ""
    if motif == MOTIF_SOURCE_RESIDUELLE and langue:
        from core import glossary_lang
        return f"{glossary_lang.du_langue(langue)} est resté dans la sortie"
    return LIBELLES.get(motif, motif)


# Plafond de sortie d'un appel portant UNE planche. Calé sur les mesures du tome : la planche
# la plus peuplée compte 13 bulles, soit 908 tokens par l'estimateur par bulle — le plafond est
# donc un filet, jamais le régime de croisière.
PLAFOND_PLANCHE = 2048


def bubbles_cap_lot(numbered: str, n: int, plafond: int = PLAFOND_PLANCHE) -> int:
    """Plafond de SORTIE pour une liste numérotée de bulles, **une ou plusieurs planches**.

    Deux estimateurs, dont on prend le maximum : **par bulle** (une réplique tient largement
    en ~60 tokens de français) et **proportionnel au japonais OCR**. Calé sur les mesures du
    tome : médiane 6 bulles/page, maximum 13, ~16 tokens générés par bulle.

    Sur une page à 11 bulles cela donne 788 tokens, soit ~4,4× la production réellement
    observée — assez large pour ne jamais tronquer une page légitime, assez serré pour que
    `emballement` redevienne un signal.

    ⚠ Le `plafond` est le SEUL paramètre qui change entre une planche et un lot, et il ne peut
    pas rester en dur : un lot de 20 planches porte ~130 bulles, soit 7 928 tokens par
    l'estimateur par bulle. Plafonné à 2 048, le lot serait tronqué à sa sixième planche —
    c'est-à-dire que le mode par lots produirait silencieusement des planches vides. D'où
    `manga.lot.plafond_sortie`, et d'où le garde-fou de prefill de `place_disponible`.

    ⚠ Passer un vrai `max_tokens` a un second effet, au moins aussi important : cela réactive
    la détection `finish_reason == "length"` de `pipeline/llm.py`, aujourd'hui inatteignable
    côté manga. Sans plafond, `num_predict` est illimité et une page qui raisonne en boucle
    génère jusqu'à épuisement du `num_ctx` — à 18,5 tok/s, potentiellement une demi-heure sur
    une seule planche, **sans que `thinking_overflow` ne soit jamais compté**."""
    return min(max(384, plafond), max(384, n * 60 + 128, tokens.estimate(numbered) * 3))


def bubbles_cap(numbered: str, n: int) -> int:
    """Plafond de sortie d'une planche seule. Conservé : 27 tests et le rattrapage l'appellent."""
    return bubbles_cap_lot(numbered, n, PLAFOND_PLANCHE)


@dataclass
class Contexte:
    """Tout ce dont les prédicats ont besoin pour juger une sortie."""
    sortie: str
    n: int                                  # nombre de bulles attendu
    cap: int                                # plafond de tokens passé au modèle
    sources: list[str] = field(default_factory=list)   # texte OCR par bulle
    langue: str = "jp"                      # langue SOURCE — décide comment on repère une
                                            # source recopiée (cf. `_source_residuelle`)
    #: Planchers de `_bulle_trop_courte` par famille de langue source. `None` = `RATIO_COURT`.
    #: Réglable par `manga.garde_fous.ratio_court` : c'est un seuil d'heuristique, et le dépôt
    #: les expose plutôt que de les enfouir.
    ratio_court: dict | None = None


@dataclass
class Numerotation:
    """Lecture d'une sortie numérotée — l'objet unique que lisent le diagnostic ET la
    reconstruction.

    Chaque champ vient d'un échec observé sur le tome :
      · `repliques` — numéros **bornés à 1..n** et continuations recollées ;
      · `preambule` — les lignes qui précèdent le premier numéro (« Voici les traductions : »),
        qui ne sont pas des répliques et décalaient toute la planche quand le repli
        positionnel s'en emparait ;
      · `hors_bornes` — un « 11. » sur 10 bulles est du bruit, jamais une réplique : le retenir
        écrasait une vraie bulle ou faisait mentir le décompte ;
      · `doublons` — sur un second « 3. », le PREMIER gagne (le modèle se reprend rarement pour
        le mieux, et garder le dernier ferait dépendre le résultat de la longueur de la sortie).
    """
    repliques: dict[int, str] = field(default_factory=dict)
    preambule: list[str] = field(default_factory=list)
    hors_bornes: list[int] = field(default_factory=list)
    doublons: list[int] = field(default_factory=list)


def sans_prefixe(ligne: str, n: int = 0) -> str:
    """Retire un préfixe numéroté, y compris redoublé (« 1. 1. Texte »).

    C'est l'invariant du lot : **aucune** réplique rendue ne commence par un numéro. Neuf
    bulles de la page 129 en portaient un dessiné à l'encre, parce que le repli positionnel
    recopiait la ligne telle quelle.

    Le retrait est borné : seul un nombre qui peut être un **index de bulle** est un préfixe.
    « 1972. Une année terrible » garde son millésime — c'est du texte, pas une numérotation.
    `n` donne la borne exacte quand l'appelant connaît le nombre de bulles."""
    plafond = n if n > 0 else _MAX_INDEX_BULLE
    while True:
        m = _LIGNE_NUM.match(ligne)
        if m is None or not (1 <= int(m.group(1)) <= plafond):
            return ligne.strip()
        ligne = m.group(2) or ""


def analyser_numerotation(sortie: str, n: int = 0) -> Numerotation:
    """Lit une sortie de traduction numérotée. `n <= 0` désactive le bornage.

    Une ligne non numérotée qui SUIT une ligne numérotée est une continuation de cette
    réplique et lui est recollée — l'ancien code la jetait purement et simplement."""
    num = Numerotation()
    courant: int | None = None
    vu_numero = False
    for brute in sortie.splitlines():
        ligne = brute.strip()
        if not ligne:
            continue
        m = _LIGNE_NUM.match(ligne)
        if m is None:
            if not vu_numero:
                num.preambule.append(ligne)
            elif courant is not None:
                suite = (num.repliques[courant] + " " + ligne).strip()
                num.repliques[courant] = suite
            continue
        vu_numero = True
        i = int(m.group(1))
        texte = sans_prefixe(m.group(2) or "", n)
        if n > 0 and not (1 <= i <= n):
            num.hors_bornes.append(i)
            courant = None          # ses continuations sont du bruit, elles aussi
        elif i in num.repliques:
            num.doublons.append(i)
            courant = None
        else:
            num.repliques[i] = texte
            courant = i
    return num


def lignes_numerotees(sortie: str, n: int = 0) -> dict[int, str]:
    """Répliques indexées par leur numéro, telles que `repliques_par_bulle` les lira."""
    return analyser_numerotation(sortie, n).repliques


# Stratégies de reconstruction, de la plus sûre à la moins sûre. Elles remontent jusqu'au
# `qa.json` : une planche reconstituée positionnellement n'a pas la même valeur de preuve
# qu'une planche numérotée, et le rapport doit pouvoir le dire.
STRATEGIES = {
    "numerotee": "numérotation complète",
    "numerotee_partielle": "numérotation incomplète (bulles laissées vides)",
    "positionnelle": "repli positionnel (ordre des lignes — alignement non garanti)",
    "vide": "aucune réplique exploitable",
}


def repliques_par_bulle(sortie: str, n: int) -> tuple[list[str], str]:
    """Reconstitue une réplique par bulle. Renvoie `(textes, stratégie)`.

    **Mapping partiel** au lieu du tout-ou-rien d'avant : dès qu'UN numéro valide existe, on
    honore les numéros présents et on laisse les autres bulles vides. L'ancien test
    `if len(numbered) >= n` faisait basculer la planche entière dans le repli positionnel dès
    qu'il manquait une ligne — page 129, le modèle a rendu 9 répliques pour 10 bulles, et les
    dix bulles se sont retrouvées lettrées depuis un repli qui, lui, ne retirait pas le
    préfixe. Une bulle vide est signalée par le rapport ; un numéro dessiné, non."""
    if n <= 0:
        return [], "vide"
    num = analyser_numerotation(sortie, n)
    if num.repliques:
        strategie = "numerotee" if len(num.repliques) >= n else "numerotee_partielle"
        return [num.repliques.get(i + 1, "") for i in range(n)], strategie
    # Bornage GÉNÉRIQUE, pas `n` : dans ce repli les numéros sont justement hors bornes (le
    # modèle poursuit la numérotation de la planche précédente), et il faut quand même les
    # retirer. Seul un nombre invraisemblable comme index de bulle est laissé au texte.
    lignes = [sans_prefixe(ligne) for ligne in sortie.splitlines() if ligne.strip()]
    lignes = [ligne for ligne in lignes if ligne]
    if not lignes:
        return [""] * n, "vide"
    return (lignes + [""] * n)[:n], "positionnelle"


def decouper_par_planche(repliques: list[str], tailles: list[int]) -> list[list[str]]:
    """Redistribue une liste PLATE de répliques vers les planches d'un lot.

    C'est la seule pièce vraiment nouvelle du mode par lots, et la plus facile à casser : le
    modèle numérote 1..N sur tout le lot, `repliques_par_bulle` rend une liste de N, et il
    faut la recouper aux frontières des planches. Une erreur d'un rang ici décale un tome
    entier — d'où une fonction pure, sans I/O, testée séparément.

    **Le contrat de longueur est absolu** : chaque tranche fait exactement `tailles[k]`, quelle
    que soit la longueur de l'entrée. Une entrée trop courte complète par des chaînes vides
    (des bulles vides, que le rapport signale et que le rattrapage unitaire reprend) ; une
    entrée trop longue est tronquée. Rendre une tranche courte ferait mentir l'alignement par
    position de `traduction.json` sur `regions.json`, qui est le pivot de toute la brique."""
    tranches: list[list[str]] = []
    debut = 0
    for taille in tailles:
        tranche = list(repliques[debut:debut + taille])
        tranches.append((tranche + [""] * taille)[:taille])
        debut += taille
    return tranches


def strategie_de_tranche(tranche: list[str]) -> str:
    """Stratégie de reconstruction d'UNE planche d'un lot (cf. `STRATEGIES`).

    `repliques_par_bulle` juge le lot entier ; le `qa.json` d'une planche, lui, doit dire ce
    qui est arrivé à CETTE planche. Un lot de 20 dont une seule planche manque n'est pas
    « incomplet » pour les 19 autres, et le rapport de tome se lit planche par planche."""
    remplies = sum(1 for t in tranche if (t or "").strip())
    if not tranche or remplies == 0:
        return "vide"
    return "numerotee" if remplies >= len(tranche) else "numerotee_partielle"


def place_disponible(prefill: int, cap: int, num_ctx: int, marge: float = 0.85) -> int:
    """Tokens qui resteraient libres sous le `num_ctx` déclaré. Négatif = le lot ne tient pas.

    C'est la mesure qui avait fait ÉCARTER le tome-en-un-appel (cf. `config.yaml`) : entrée
    22 070 + sortie 8 878 = 30 948 pour un `num_ctx` de 32 768, soit 1 820 tokens laissés au
    raisonnement — alors que le raisonnement mesuré sur ce dépôt occupe 74 à 97 % de la
    génération. Elle était faite à la main une fois ; elle est maintenant calculée à chaque
    lot, ce qui est la seule façon qu'elle reste vraie quand la taille du lot change.

    ⚠ `num_ctx` n'est pas envoyé par le client (il vit dans le Modelfile Ollama) : la valeur
    vient de `llm.num_ctx`, purement DÉCLARATIVE. Un dépassement ne lève donc rien — il
    avertit, et c'est déjà tout ce dont on a besoin pour ne pas le découvrir au rapport."""
    return int(num_ctx * marge) - prefill - cap


def _vide(c: Contexte) -> bool:
    return not c.sortie.strip()


def _bulles_manquantes(c: Contexte) -> bool:
    """L'échec DOMINANT du manga, et le plus dangereux — jusqu'ici totalement silencieux.

    Depuis le mapping partiel de `repliques_par_bulle`, une numérotation incomplète ne décale
    plus la planche : les répliques numérotées vont dans leur bulle, les autres restent vides.
    Le motif garde tout son sens — il faut retenter pour combler ces trous — mais il n'est
    plus un risque de décalage. Le décalage ne subsiste que dans le repli **positionnel**,
    c'est-à-dire quand le modèle n'a numéroté strictement aucune ligne, cas que ce même motif
    couvre a fortiori."""
    if c.n <= 0:
        return False
    return len(lignes_numerotees(c.sortie, c.n)) < c.n


def _normaliser(t: str) -> str:
    """Forme comparable d'une réplique : casse, accents de ponctuation et espaces neutralisés.

    Sert au seul repérage de la RECOPIE ; on ne compare jamais du sens, seulement des chaînes."""
    return re.sub(r"[\W_]+", "", (t or "").lower())


def _source_residuelle(c: Contexte) -> bool:
    """Une réplique rendue est restée dans la LANGUE SOURCE : le modèle a recopié au lieu de
    traduire.

    ⚠ Le test dépend de la langue source, et c'est tout l'enjeu :

    · **Source CJK** — la présence de kana ou d'idéogrammes suffit, et c'est un signal sûr.
      On utilise `tokens.CJK_TEXTE`, la classe ÉTROITE, et non `tokens.CJK` : la large
      englobe la ponctuation pleine chasse (`（）`, `「」`, `！`), si bien qu'une bulle dont
      la traduction est `（）` ou `!?` était déclarée « du japonais est resté », ce qui est
      faux. Le socle distingue les deux depuis la 0.33.0.

    · **Source latine** — aucune classe de caractères ne peut trancher : l'anglais et le
      français s'écrivent dans le même alphabet. Le vrai risque devient la recopie **à
      l'identique**, qu'on repère en comparant la réplique rendue à sa source normalisée.
      Un test par charset y serait soit muet, soit constamment faux.

    Une réplique volontairement identique à sa source (nom propre seul, `!?`) est écartée par
    le plancher de longueur : en dessous, l'identité ne prouve rien."""
    rendues = lignes_numerotees(c.sortie, c.n)
    cibles = list(rendues.values()) if rendues else c.sortie.splitlines()

    if (c.langue or "jp").lower() in _LANGUES_CJK:
        return any(tokens.CJK_TEXTE.search(t) for t in cibles if t.strip())

    if not c.sources:
        return False
    for i, source in enumerate(c.sources, start=1):
        rendu = rendues.get(i, "")
        src, dst = _normaliser(source), _normaliser(rendu)
        if src and src == dst and len(src) >= _MIN_RECOPIE:
            return True
    return False


#: En deçà, l'identité source/rendu ne prouve rien : « OK », « HM », un nom propre ou une
#: onomatopée se traduisent légitimement par eux-mêmes.
_MIN_RECOPIE = 12

#: Langues pour lesquelles l'écriture suffit à trahir une recopie.
_LANGUES_CJK = frozenset({"jp", "ja", "zh", "ko"})


def _repetition(c: Contexte) -> bool:
    """Même réplique rendue au moins trois fois SANS que la source ne se répète autant.

    ⚠ La comparaison aux SOURCES n'est pas un raffinement, c'est ce qui distingue une boucle
    d'une traduction fidèle. Mesuré sur *manga B* Chap.5, pages 58 et 59 : une foule
    scande un nom, l'OCR rend `マリアネラ` **six fois**, et la traduction rend six fois
    « Marianna Lassar ». Les deux planches étaient diagnostiquées « le modèle a bouclé » et ont
    dépensé leurs retries pour rien — sur les cinq boucles annoncées au rapport du tome, deux
    étaient ce faux positif.

    `c.sources` était déjà dans le `Contexte`, simplement jamais lu ici."""
    from collections import Counter

    rendues = [t.strip() for t in lignes_numerotees(c.sortie, c.n).values() if t.strip()]
    if len(rendues) < 3:
        return False
    max_rendu = Counter(rendues).most_common(1)[0][1]
    if max_rendu < 3:
        return False
    sources = [s.strip() for s in (c.sources or []) if s and s.strip()]
    if not sources:
        return True
    # Une répétition n'est fautive que si elle DÉPASSE celle de la source. À égalité, le modèle
    # a fait exactement son travail.
    return max_rendu > Counter(sources).most_common(1)[0][1]


def _emballement(c: Contexte) -> bool:
    return c.cap > 0 and tokens.estimate(c.sortie) >= c.cap * 0.95


def _bulle_trop_longue(c: Contexte) -> bool:
    """Une réplique dépasse ~3× l'estimation de sa bulle source.

    Le japonais est dense : ~1 token par caractère contre ~4 caractères par token en latin.
    Une traduction française fait donc légitimement plusieurs fois la longueur estimée de sa
    source ; au-delà de 3× avec un plancher de tolérance, c'est du bavardage ajouté — et un
    débordement de bulle garanti en aval."""
    if not c.sources:
        return False
    rendues = lignes_numerotees(c.sortie, c.n)
    for i, source in enumerate(c.sources, start=1):
        rendu = rendues.get(i, "")
        if not rendu or not source.strip():
            continue
        budget = max(24, tokens.estimate(source) * 3)
        if tokens.estimate(rendu) > budget:
            return True
    return False


#: Ratio PLANCHER `tokens(rendu) / tokens(source)`, par famille de langue source. En dessous,
#: la réplique a perdu du contenu (cf. `_bulle_trop_courte`).
#:
#: ⚠ Calibré, pas choisi. Mesuré sur les paires source/rendu déjà en cache dans `build/` —
#: 1 702 bulles CJK sur trois volumes, 16 bulles latines sur le webtoon — en écartant les
#: sources de moins de `_PLANCHER_SOURCE` tokens :
#:
#:     source CJK    médiane 0,65   p10 0,39   p5 0,33   p2 0,24   p1 0,20
#:     source latine médiane 1,06   p10 0,88   p5 0,84   p2 0,79   p1 0,77
#:
#: L'écart entre les deux familles est d'un facteur ~1,6, et un ratio unique produirait donc
#: soit des faux positifs en masse sur le CJK, soit un plancher inatteignable sur le latin.
#: Les valeurs retenues sont sous le 2ᵉ centile de leur famille : le motif ne se déclenche que
#: sur une réplique franchement amputée, jamais sur une traduction serrée.
RATIO_COURT = {"cjk": 0.22, "latin": 0.55}

#: En dessous de tant de tokens de source, aucun jugement. Une bulle de deux caractères rendue
#: par un mot est parfaitement normale, et c'est le tiers du corpus.
_PLANCHER_SOURCE = 8


def _bulle_trop_courte(c: Contexte) -> bool:
    """Une réplique est **plus courte que sa source ne le permet**. Le symétrique manquant.

    ## Le défaut que ce prédicat ferme

    Les six autres motifs sont morphologiques ou statistiques, et **aucun ne détectait une
    réplique abrégée**. Une bulle japonaise de 40 caractères rendue par « Ouais. » passait les
    six : elle n'est pas vide, elle est numérotée, elle est en français, elle est unique, et
    elle est courte.

    Or la pression est **structurellement** dans le sens de l'abrègement : le prompt injecte
    un budget de caractères par bulle (`_lignes_gabarits`) avec la formule « dépasser force
    une police illisible », **sans aucune contrepartie sur la fidélité**. On demandait d'être
    court, et on ne vérifiait jamais qu'on n'avait pas coupé. `_bulle_trop_longue` ne bornait
    que par le haut.

    Le light novel avait le garde-fou correspondant depuis toujours
    (`garde_fous.perte_mots_ratio`) ; `grep -rn perte_mots manga/` renvoyait zéro. Et ce
    n'était pas seulement une clé absente : `garde_fous` est une clé de PREMIER NIVEAU de
    `config.yaml`, hors du bloc `manga:`, donc structurellement inatteignable depuis
    `mcfg = config["manga"]`. D'où une clé manga à elle, `manga.garde_fous.ratio_court`, et
    non un emprunt à celle du LN.

    ⚠ Le seuil dépend de la LANGUE SOURCE, et il le faut : le japonais est dense, un ratio
    naïf produirait des faux positifs en masse (cf. `RATIO_COURT`)."""
    if not c.sources:
        return False
    famille = "cjk" if (c.langue or "jp").lower() in _LANGUES_CJK else "latin"
    table = c.ratio_court or RATIO_COURT
    plancher = float(table.get(famille, RATIO_COURT[famille]))
    # `0` DÉSARME le motif, et c'est une valeur légitime : une œuvre à sources très elliptiques
    # peut vouloir le taire sans perdre les six autres.
    if plancher <= 0:
        return False
    rendues = lignes_numerotees(c.sortie, c.n)
    for i, source in enumerate(c.sources, start=1):
        rendu = rendues.get(i, "")
        # Une bulle VIDE n'est pas une bulle courte : `bulles_manquantes` et le rattrapage
        # unitaire s'en occupent déjà, et la compter ici la ferait rapporter deux fois sous
        # deux noms différents.
        if not rendu.strip() or not source.strip():
            continue
        cout = tokens.estimate(source)
        if cout < _PLANCHER_SOURCE:
            continue
        if tokens.estimate(rendu) < cout * plancher:
            return True
    return False


# Registre ORDONNÉ : le premier prédicat qui répond décide du motif. L'ordre va du plus
# grossier au plus fin — une sortie vide ne doit pas être diagnostiquée « japonais résiduel ».
#
# ⚠ `bulle_trop_courte` est APRÈS `bulle_trop_longue`, et pas par hasard : les deux peuvent
# répondre sur la même planche (une réplique étoffée, une autre amputée), et l'excès de
# longueur est le plus visible des deux au rendu — c'est celui qui déborde de la bulle. Le
# rapport, lui, les voit tous les deux (`diagnostiquer_tous`).
MOTIFS: tuple[tuple[str, object], ...] = (
    ("vide", _vide),
    ("bulles_manquantes", _bulles_manquantes),
    (MOTIF_SOURCE_RESIDUELLE, _source_residuelle),
    ("repetition", _repetition),
    ("emballement", _emballement),
    ("bulle_trop_longue", _bulle_trop_longue),
    ("bulle_trop_courte", _bulle_trop_courte),
)


# ─────────────────────────────────────────────────────────────────────────────
# Onomatopée BRODÉE — lot 21, L21.4
#
# `_translate_sfx` réutilisait les garde-fous de DIALOGUE tels quels : `bubbles_cap`,
# `try_with_temp_retry`, `repliques_par_bulle`. Aucun ne dit qu'une réponse a la forme d'une
# onomatopée, et le seul qui borne la longueur — `_bulle_trop_longue` — ne peut pas se
# déclencher ici : son budget est `max(24, tokens(source) × 3)`, et **le plancher de 24
# tokens absorbe tout** quand la source fait un caractère. Une hallucination bien formée
# passait donc les six motifs.
#
# ## Le seuil est mesuré, pas choisi
#
# Sur les **1 596 paires source/rendu** déjà en cache dans `build/` (17 projets, fichiers
# `sfx_traduction.json`), le rapport `tokens(rendu) / tokens(source)` vaut :
#
#     p50 0,32   p75 0,50   p90 0,64   p95 0,83   p99 2,50   max 14,00
#
# La traduction d'une onomatopée est donc, en règle générale, **plus courte que sa source en
# tokens** — le japonais est dense, mais `ドドド` rend `BROUM` et non l'inverse. Le p99 est à
# 2,50 : un seuil à **3,0** est au-delà du 99ᵉ centile du corpus réel.
#
# Croisé avec un plancher de 8 tokens rendus (le p90 des rendus), il retient **6 paires sur
# 1 596 — 0,38 %** :
#
#     『あ』   (1 tk) → « C'est faisable. Après la diffusion vient le focalisation. »   (14 tk)
#     『あれ』 (2 tk) → « Mitsukage… Désolé de t'avoir impliqué, je vais te le rendre. » (15 tk)
#     『プラン』(3 tk) → « Ces émotions n'attendent que l'exécution. Cette sensation… »  (17 tk)
#     『ガズン』(3 tk) → « LIEUTENANT AOZAKA ! UN KATAPHRHAKT INCONNU ! »                (11 tk)
#     + deux sources `．．．`
#
# Aucune n'est une traduction : ce sont six phrases inventées à partir d'un signe. Et il n'y
# a **aucun faux positif** dans les six — c'est ce que « calibré » veut dire ici.
#
# ⚠ **Le plancher est indispensable, et c'est une mesure aussi.** Sans lui, `『あ』 → « Eh bien
# alors… »` (ratio 4,0, 4 tokens) serait refusé : c'est pourtant une glose parfaitement
# légitime. Le ratio seul retient 10 paires, dont 4 innocentes.
#
# ⚠ **Deux des six ne se produiraient plus aujourd'hui.** Leur source est `．．．`, que le
# triage du lot 13 rend désormais sans aucun appel LLM (`TRI_PONCTUATION` →
# `typeset.latiniser`). Le prédicat en tirerait donc 4 sur 1 596 (0,25 %) sur le pipeline
# actuel — encore moins, et le chiffre est dit plutôt qu'arrondi vers le haut.
#
# ## Pourquoi un refus par ZONE, et non un motif de page
#
# Les sept motifs de `MOTIFS` diagnostiquent une SORTIE ENTIÈRE et arment un retry de page.
# Ici, une seule ligne sur douze est brodée : rejouer toute la planche serait payer un appel
# pour reprendre onze traductions correctes, et le retry rejoue exactement ce qui vient
# d'échouer (c'est la mesure qui a produit `_rattraper_bulles`). La zone fautive est donc
# **vidée**, et signalée au rapport — application directe de la règle de la brique : une
# absence signalée vaut mieux qu'une mauvaise réplique posée.

#: Motif de refus d'une traduction d'onomatopée. Nommé, donc comptable au rapport.
MOTIF_SFX_BRODERIE = "sfx_broderie"

#: Motifs qui portent un libellé mais **ne sont pas** dans `MOTIFS`. Le registre ordonné
#: diagnostique une SORTIE ENTIÈRE et arme un retry de page ; ceux-ci refusent une ZONE et
#: n'en arment aucun (cf. le bloc ci-dessus). L'ensemble est nommé ici plutôt que dans le
#: test qui vérifie « aucun libellé orphelin » : une exception qui vit dans un test est une
#: exception que le prochain lot recopiera sans savoir pourquoi.
MOTIFS_HORS_REGISTRE = frozenset({MOTIF_SFX_BRODERIE})

#: Rapport `tokens(rendu) / tokens(source)` au-delà duquel une traduction d'onomatopée est
#: refusée. `0` DÉSARME le prédicat — c'est le défaut du CODE, pour la même raison que
#: `onomatopees.actif` : une configuration antérieure à ce lot ne doit pas se mettre à vider
#: des zones sans avoir été consultée. `config.yaml` recommande 3,0.
BRODERIE_RATIO = 0.0

#: Nombre de tokens rendus en dessous duquel aucun jugement n'est porté. Cf. ci-dessus : sans
#: lui, une glose de quatre tokens sur une source d'un caractère serait refusée.
BRODERIE_PLANCHER = 8


def onomatopee_brodee(source: str, rendu: str, *, ratio: float = BRODERIE_RATIO,
                      plancher: int = BRODERIE_PLANCHER) -> bool:
    """La réponse est-elle une PHRASE inventée là où une onomatopée était attendue ?

    Deux conditions, et il faut les deux (cf. le bloc ci-dessus) : le rendu dépasse `ratio`
    fois sa source en tokens, **et** il pèse au moins `plancher` tokens dans l'absolu.

    ⚠ `ratio <= 0` désarme, et c'est une valeur légitime : une œuvre dont les zones hors
    bulle sont surtout de la narration libre peut vouloir le taire."""
    if ratio <= 0:
        return False
    rendu = (rendu or "").strip()
    source = (source or "").strip()
    if not rendu or not source:
        return False
    cout = tokens.estimate(rendu)
    if cout < plancher:
        return False
    return cout > ratio * max(1, tokens.estimate(source))


def refuser_onomatopees_brodees(sources: list[str], rendus: list[str], *,
                                ratio: float = BRODERIE_RATIO,
                                plancher: int = BRODERIE_PLANCHER
                                ) -> tuple[list[str], list[int]]:
    """Vide les traductions brodées. Renvoie `(rendus, indices refusés)`.

    La liste garde sa longueur et son ordre : elle est **alignée par position** sur les zones,
    comme `ocr.json` et `traduction.json`, et un refus qui décalerait cet alignement serait
    bien pire que la broderie qu'il corrige."""
    sortie = list(rendus or [])
    refuses: list[int] = []
    for i, rendu in enumerate(sortie):
        source = sources[i] if i < len(sources) else ""
        if onomatopee_brodee(source, rendu, ratio=ratio, plancher=plancher):
            sortie[i] = ""
            refuses.append(i)
    return sortie, refuses


def diagnostiquer(sortie: str, *, n: int, cap: int,
                  sources: list[str] | None = None,
                  langue: str = "jp", ratio_court: dict | None = None) -> str | None:
    """Nom du premier motif d'échec qui s'applique, ou `None` si la sortie est exploitable.

    Reste le motif PRINCIPAL, celui qui pilote le retry : le registre est ordonné du plus
    grossier au plus fin, et retenter une sortie vide n'a pas le même sens que retenter une
    sortie bavarde. Pour le RAPPORT, voir `diagnostiquer_tous`."""
    c = Contexte(sortie=sortie, n=n, cap=cap, sources=list(sources or []), langue=langue,
                 ratio_court=ratio_court)
    for nom, predicat in MOTIFS:
        if predicat(c):
            return nom
    return None


def diagnostiquer_tous(sortie: str, *, n: int, cap: int,
                       sources: list[str] | None = None,
                       langue: str = "jp", ratio_court: dict | None = None) -> list[str]:
    """TOUS les motifs qui s'appliquent, dans l'ordre du registre.

    Pourquoi c'en est un second et non un remplacement : `diagnostiquer` s'arrête au premier
    motif, si bien qu'une sortie à la fois **incomplète et japonaise** était rapportée
    « numérotation incomplète » — le mot « japonais » n'apparaissait ni en console ni dans
    `RAPPORT.md`, alors que c'est le plus actionnable des deux. Le contrôle du retry, lui, a
    besoin d'un motif unique et ordonné : on ne change donc pas sa sémantique, on ajoute
    celle dont le rapport avait besoin."""
    c = Contexte(sortie=sortie, n=n, cap=cap, sources=list(sources or []), langue=langue,
                 ratio_court=ratio_court)
    return [nom for nom, predicat in MOTIFS if predicat(c)]


def motifs_repliques(repliques: list[str] | None,
                     sources: list[str] | None = None,
                     langue: str = "jp") -> list[str]:
    """Motifs constatables sur les répliques FINALES, une fois rattachées à leurs bulles.

    Complète `diagnostiquer`, qui juge la sortie BRUTE du modèle et n'en retient que le
    premier motif. Ce que voit celui-ci est ce qui va réellement être dessiné — donc ce que
    le rapport doit nommer. Il sert aussi à contrôler un cache relu (`--from rendu`), où la
    sortie brute n'existe plus.

    `sources` n'est utile que sur une source latine, où la recopie ne se voit qu'à la
    comparaison (cf. `_source_residuelle`)."""
    repliques = list(repliques or [])
    if (langue or "jp").lower() in _LANGUES_CJK:
        if any(t and tokens.CJK_TEXTE.search(t) for t in repliques):
            return [MOTIF_SOURCE_RESIDUELLE]
        return []
    for src, dst in zip(list(sources or []), repliques):
        n_src, n_dst = _normaliser(src), _normaliser(dst)
        if n_src and n_src == n_dst and len(n_src) >= _MIN_RECOPIE:
            return [MOTIF_SOURCE_RESIDUELLE]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Rattrapage UNITAIRE d'une bulle laissée vide
#
# Le retry de page rejoue la numérotation — exactement ce qui vient d'échouer : sur le Vol.1,
# les deux retries de page ont échoué comme leur premier essai. L'escalade doit donc changer
# de FORME D'APPEL, pas de température : une bulle, une réponse, aucun numéro à se tromper.
# ─────────────────────────────────────────────────────────────────────────────

# Caractères qui PORTENT du texte. `tokens.CJK` — la classe LARGE — ne convient pas ici : elle
# couvre le bloc des formes pleine chasse, donc elle déclare « du japonais » sur l'OCR `（）` de
# la page 8 bulle 1 — deux parenthèses vides, rien à traduire. `tokens.CJK_TEXTE`, l'étroite,
# ne convient pas non plus : elle inclut `ー` (voir ci-dessous) et ignore l'alphabet latin, dont
# ce test a besoin puisqu'il juge des sources anglaises autant que japonaises.
# Sont aussi exclus, délibérément, `・` (U+30FB) et
# `ー` (U+30FC) : `manga-ocr` rend les points de suspension en `ーー`, et cette forme seule
# apparaît sur des dizaines de bulles sans jamais rien porter.
_PORTEUR_DE_TEXTE = re.compile(r"[一-鿿ぁ-ゖァ-ヺ"
                               r"A-Za-zÀ-ɏ]")

LIBELLES_RATTRAPAGE = {
    # Refus AVANT appel : la source elle-même n'a rien à traduire (cf. `source_rattrapable`).
    # Le rattrapage écarte ces bulles en amont et ne le voit donc jamais ; l'éditeur graphique,
    # lui, peut recevoir un clic « retraduire » sur n'importe quelle bulle, et doit pouvoir
    # dire pourquoi il n'a rien fait plutôt que de laisser croire à un échec du modèle.
    "source_vide": "la bulle source ne porte aucun texte à traduire",
    "vide": "réponse vide",
    "liste": "le modèle a répondu par une liste numérotée (il a repris la forme de page)",
    "japonais_residuel": "la réponse est restée dans la langue source",
    "disproportionnee": "la réponse est sans commune mesure avec sa source",
}


def source_rattrapable(source: str) -> bool:
    """Une bulle dont l'OCR ne porte AUCUN texte n'est pas un trou : elle est vide à raison.

    Mesuré sur le Vol.1 : sur les deux bulles sans traduction, l'une a pour source `（）`.
    La rattraper coûterait un appel LLM pour faire inventer une réplique à partir de rien —
    exactement le contraire de ce qu'on cherche."""
    return bool(_PORTEUR_DE_TEXTE.search(source or ""))


def diagnostiquer_rattrapage(sortie: str, *, source: str, cap: int = 0,
                             langue: str = "jp") -> str | None:
    """Motif d'échec d'une réponse UNITAIRE, ou `None` si elle est utilisable.

    Registre distinct de `MOTIFS` — et il le faut : `bulles_manquantes` y déclarerait fautive
    toute réponse non numérotée, c'est-à-dire précisément la forme qu'on demande ici.

    Une réponse diagnostiquée est **rejetée**, pas conservée : une mauvaise réplique dessinée
    dans une bulle est pire qu'une bulle vide, qui est au moins signalée au rapport."""
    texte = (sortie or "").strip()
    if not texte:
        return "vide"
    if len(analyser_numerotation(texte).repliques) >= 2:
        # Le modèle a répondu pour plusieurs bulles : impossible de savoir laquelle est
        # la nôtre. Un préfixe isolé, lui, est simplement retiré par `sans_prefixe`.
        return "liste"
    nu = sans_prefixe(texte)
    if (langue or "jp").lower() in _LANGUES_CJK:
        # ⚠ `CJK_TEXTE`, la classe ÉTROITE — la même que `_source_residuelle` et que le
        # comptage l.469. Ce site utilisait `tokens._CJK`, la LARGE, qui englobe la
        # ponctuation pleine chasse (`（）`, `「」`, `！`). Le rattrapage rejetait donc des
        # réponses que le chemin de planche acceptait : une réplique parfaitement traduite
        # mais ponctuée `！` était refusée, et **la bulle restait vide** — exactement
        # l'inverse de ce que le rattrapage existe pour faire.
        #
        # Au passage, `_CJK` est l'alias PRIVÉ de `tokens.CJK` : l'appeler depuis `manga/`
        # liait ce module à un nom que `core/` ne doit à personne.
        if tokens.CJK_TEXTE.search(nu):
            return MOTIF_SOURCE_RESIDUELLE
    else:
        n_src, n_dst = _normaliser(source), _normaliser(nu)
        if n_src and n_src == n_dst and len(n_src) >= _MIN_RECOPIE:
            return MOTIF_SOURCE_RESIDUELLE
    budget = max(24, tokens.estimate(source) * 3)
    if tokens.estimate(sans_prefixe(texte)) > budget:
        return "disproportionnee"
    return None


def _prefere(gardee: str, motif_garde: str, candidate: str, motif_candidate: str) -> bool:
    """Une tentative ratée est-elle meilleure que celle déjà gardée ?

    Critère principal : plus de répliques numérotées, donc plus de bulles récupérables.

    ⚠ Départage AJOUTÉ à nombre égal : une sortie qui a recopié le japonais perd contre une
    sortie qui ne l'a pas fait. Le critère purement quantitatif pouvait retenir la tentative
    **la plus japonaise** au seul motif qu'elle numérotait mieux — et comme le japonais n'est
    pas dessinable (la chaîne de polices n'en a pas les glyphes), ces bulles sortaient
    VIDES. On préférait donc, sans le savoir, la version qui produit des trous."""
    n_gardee = len(lignes_numerotees(gardee))
    n_candidate = len(lignes_numerotees(candidate))
    if n_candidate != n_gardee:
        return n_candidate > n_gardee
    return (motif_garde == MOTIF_SOURCE_RESIDUELLE
            and motif_candidate != MOTIF_SOURCE_RESIDUELLE)


def try_with_temp_retry(call, *, n: int, cap: int, sources: list[str] | None = None,
                        stats: dict | None = None, temperature: float = 0.3,
                        temp_factor: float = 0.4, langue: str = "jp",
                        ratio_court: dict | None = None,
                        max_retries: int = 1) -> tuple[str, bool, str | None]:
    """Appelle `call(temperature)`, diagnostique, et RETENTE à température corrigée.

    Signature conservée (l'orchestrateur et 27 tests s'appuient dessus) ; la mécanique est
    celle de `core.quality.try_with_temp_retry` depuis le lot 2.5. Ne reste ici que ce qui
    est propre au manga : le registre de motifs, le contexte, et la définition de « meilleure
    sortie ».

    `max_retries` vaut 1 par défaut côté manga : avec un budget de raisonnement, deux
    relances feraient jusqu'à trois générations perdues sur une page pathologique."""
    return quality.try_with_temp_retry(
        call,
        lambda sortie: diagnostiquer(sortie, n=n, cap=cap, sources=sources, langue=langue,
                                     ratio_court=ratio_court),
        stats=stats, temperature=temperature, temp_factor=temp_factor,
        max_retries=max_retries, cle_ok="pages_ok",
        motifs_plus_chaud=MOTIFS_PLUS_CHAUD, prefere=_prefere)
