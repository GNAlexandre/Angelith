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
_LIGNE_NUM = re.compile(r"^\s*(\d+)[.)](?:\s+(.*)|\s*$)")

# Au-delà, un nombre n'est plus un index de bulle mais du texte : la planche la plus peuplée
# du tome en compte 13. Sert quand le nombre de bulles n'est pas connu de l'appelant.
_MAX_INDEX_BULLE = 99

# Motifs pour lesquels on RELÈVE la température au lieu de la baisser : sur une boucle
# dégénérée, resserrer le modèle renforce le cycle au lieu de le casser. Même ensemble que
# le light novel — c'est une propriété du modèle, pas de l'unité de travail — d'où le défaut
# du socle, repris ici sous son nom historique.
MOTIFS_PLUS_CHAUD = quality.MOTIFS_PLUS_CHAUD

LIBELLES = {
    "vide": "réponse vide du modèle",
    "bulles_manquantes": "numérotation incomplète (risque de décalage des répliques)",
    "japonais_residuel": "du japonais est resté dans la sortie",
    "repetition": "le modèle a bouclé (même réplique répétée)",
    "emballement": "la sortie sature le plafond de tokens",
    "bulle_trop_longue": "une réplique est disproportionnée par rapport à sa bulle source",
}


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


def _japonais_residuel(c: Contexte) -> bool:
    """Une réplique rendue contient encore du CJK : le modèle a recopié la source.

    ⚠ `tokens.CJK_TEXTE` — la classe ÉTROITE — et non `tokens.CJK`. La large englobe la
    ponctuation pleine chasse (`（）`, `「」`, `！`) : une bulle dont la traduction est
    `（）` ou `!?` était déclarée « du japonais est resté », ce qui est faux. Le socle
    distingue les deux depuis la 0.33.0, précisément parce que la brique manga avait dû se
    fabriquer sa propre classe étroite après ce diagnostic (cf. `core/tokens.py`).

    Aucune perte de couverture : du japonais réellement recopié porte toujours des kana ou
    des idéogrammes, qui sont dans la classe étroite."""
    rendues = lignes_numerotees(c.sortie, c.n)
    cibles = list(rendues.values()) if rendues else c.sortie.splitlines()
    return any(tokens.CJK_TEXTE.search(t) for t in cibles if t.strip())


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


# Registre ORDONNÉ : le premier prédicat qui répond décide du motif. L'ordre va du plus
# grossier au plus fin — une sortie vide ne doit pas être diagnostiquée « japonais résiduel ».
MOTIFS: tuple[tuple[str, object], ...] = (
    ("vide", _vide),
    ("bulles_manquantes", _bulles_manquantes),
    ("japonais_residuel", _japonais_residuel),
    ("repetition", _repetition),
    ("emballement", _emballement),
    ("bulle_trop_longue", _bulle_trop_longue),
)


def diagnostiquer(sortie: str, *, n: int, cap: int,
                  sources: list[str] | None = None) -> str | None:
    """Nom du premier motif d'échec qui s'applique, ou `None` si la sortie est exploitable.

    Reste le motif PRINCIPAL, celui qui pilote le retry : le registre est ordonné du plus
    grossier au plus fin, et retenter une sortie vide n'a pas le même sens que retenter une
    sortie bavarde. Pour le RAPPORT, voir `diagnostiquer_tous`."""
    c = Contexte(sortie=sortie, n=n, cap=cap, sources=list(sources or []))
    for nom, predicat in MOTIFS:
        if predicat(c):
            return nom
    return None


def diagnostiquer_tous(sortie: str, *, n: int, cap: int,
                       sources: list[str] | None = None) -> list[str]:
    """TOUS les motifs qui s'appliquent, dans l'ordre du registre.

    Pourquoi c'en est un second et non un remplacement : `diagnostiquer` s'arrête au premier
    motif, si bien qu'une sortie à la fois **incomplète et japonaise** était rapportée
    « numérotation incomplète » — le mot « japonais » n'apparaissait ni en console ni dans
    `RAPPORT.md`, alors que c'est le plus actionnable des deux. Le contrôle du retry, lui, a
    besoin d'un motif unique et ordonné : on ne change donc pas sa sémantique, on ajoute
    celle dont le rapport avait besoin."""
    c = Contexte(sortie=sortie, n=n, cap=cap, sources=list(sources or []))
    return [nom for nom, predicat in MOTIFS if predicat(c)]


def motifs_repliques(repliques: list[str] | None) -> list[str]:
    """Motifs constatables sur les répliques FINALES, une fois rattachées à leurs bulles.

    Complète `diagnostiquer`, qui juge la sortie BRUTE du modèle et n'en retient que le
    premier motif. Ce que voit celui-ci est ce qui va réellement être dessiné — donc ce que
    le rapport doit nommer. Il sert aussi à contrôler un cache relu (`--from rendu`), où la
    sortie brute n'existe plus."""
    if any(t and tokens.CJK_TEXTE.search(t) for t in (repliques or [])):
        return ["japonais_residuel"]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Rattrapage UNITAIRE d'une bulle laissée vide
#
# Le retry de page rejoue la numérotation — exactement ce qui vient d'échouer : sur le Vol.1,
# les deux retries de page ont échoué comme leur premier essai. L'escalade doit donc changer
# de FORME D'APPEL, pas de température : une bulle, une réponse, aucun numéro à se tromper.
# ─────────────────────────────────────────────────────────────────────────────

# Caractères qui PORTENT du texte. `tokens._CJK` ne convient pas ici : il couvre le bloc des
# formes pleine chasse, donc il déclare « du japonais » sur l'OCR `（）` de la page 8 bulle 1 —
# deux parenthèses vides, rien à traduire. Sont aussi exclus, délibérément, `・` (U+30FB) et
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
    "japonais_residuel": "la réponse contient encore du japonais",
    "disproportionnee": "la réponse est sans commune mesure avec sa source",
}


def source_rattrapable(source: str) -> bool:
    """Une bulle dont l'OCR ne porte AUCUN texte n'est pas un trou : elle est vide à raison.

    Mesuré sur le Vol.1 : sur les deux bulles sans traduction, l'une a pour source `（）`.
    La rattraper coûterait un appel LLM pour faire inventer une réplique à partir de rien —
    exactement le contraire de ce qu'on cherche."""
    return bool(_PORTEUR_DE_TEXTE.search(source or ""))


def diagnostiquer_rattrapage(sortie: str, *, source: str, cap: int = 0) -> str | None:
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
    if tokens._CJK.search(sans_prefixe(texte)):
        return "japonais_residuel"
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
    return motif_garde == "japonais_residuel" and motif_candidate != "japonais_residuel"


def try_with_temp_retry(call, *, n: int, cap: int, sources: list[str] | None = None,
                        stats: dict | None = None, temperature: float = 0.3,
                        temp_factor: float = 0.4,
                        max_retries: int = 1) -> tuple[str, bool, str | None]:
    """Appelle `call(temperature)`, diagnostique, et RETENTE à température corrigée.

    Signature conservée (l'orchestrateur et 27 tests s'appuient dessus) ; la mécanique est
    celle de `core.quality.try_with_temp_retry` depuis le lot 2.5. Ne reste ici que ce qui
    est propre au manga : le registre de motifs, le contexte, et la définition de « meilleure
    sortie ».

    `max_retries` vaut 1 par défaut côté manga : avec un budget de raisonnement, deux
    relances feraient jusqu'à trois générations perdues sur une page pathologique."""
    return quality.try_with_temp_retry(
        call, lambda sortie: diagnostiquer(sortie, n=n, cap=cap, sources=sources),
        stats=stats, temperature=temperature, temp_factor=temp_factor,
        max_retries=max_retries, cle_ok="pages_ok",
        motifs_plus_chaud=MOTIFS_PLUS_CHAUD, prefere=_prefere)
