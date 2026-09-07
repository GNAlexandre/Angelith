# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**L26.0** — choisir les images, et écrire pourquoi. Retenues **et** écartées.

    bible.references[role: identite]  →  candidates d'IDENTITÉ  →  canal `references`
    bible.style.ancrages[]            →  candidates de STYLE    →  canal `ancrages_style`

## Pourquoi ce module existe, alors que le lot 25 choisissait déjà

Le lot 25 **triait** : `identite.retenir` prend les références validées, repousse les
couvertures en queue, coupe au plafond. C'est un ordre, pas un choix — et surtout, il est
muet. Un utilisateur qui ouvre `requete.yaml` et retire une image ne sait pas pourquoi elle
avait été prise, donc la porte humaine se réduit à un clic de confiance (`PLAN-26` L26.0,
règle 3).

Ce module rend une **sélection ordonnée avec un motif d'une ligne par image**, retenue comme
écartée. Le motif est déterministe par défaut ; il vient du LLM local quand celui-ci est
armé, et alors il dit ce que le modèle a **vu**, pas ce qu'il en conclut.

## Les quatre règles du plan, et où chacune est tenue

| Règle | Où |
|---|---|
| 0. une ancre de style au moins, distincte des références d'identité | `USAGE_IDENTITE` / `USAGE_ANCRAGE` — deux listes, jamais mélangées |
| 1. le nombre est plafonné par le verdict de `PLAN-25` L25.1 | `PLAFOND_REFERENCES = 2`, cf. sa note |
| 2. une image générée n'est **jamais** candidate | `_refuser_les_generees` — un test, pas une intention |
| 3. le motif est écrit dans `requete.yaml` | `Choix.motif`, jamais vide |

## Règle 2 : pourquoi un contrôle explicite plutôt qu'une convention

Les candidates ne viennent que de `bible.references[]` et de `media/`, donc en théorie
aucune image générée ne peut entrer. **En théorie.** Le `PLAN-27` L27.3 rendra le rebouclage
impossible, et le dépôt ne se contente jamais d'un raisonnement là où un test existe —
`manga/clean.py` garde son `paint &= region.mask` « parce que l'invariant ne doit pas
dépendre d'un raisonnement ». `_refuser_les_generees` écarte donc, avec un motif nommé,
toute candidate qui vit sous le dossier de la brique ou qui porte le marquage AI Act. Le
jour où quelqu'un recopiera une image produite dans `media/`, elle sera refusée plutôt
qu'entrée en silence dans le conditionnement de la suivante.

## Le coût, mesuré et publié à côté de celui de la phase 2

Juger vingt illustrations en vision sur `yume-27b` ne tient pas en un appel. Ce module fait
**un appel par image** — le lot le plus petit possible, donc le plus fiable — et compte le
temps. Si la phase 1 dure plus longtemps que la phase 2, c'est un fait à publier, pas un
détail : `Selection.secondes` le porte, et le rapport le met face à `secondes_par_image`.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from illustration import identite as ident_mod

#: Nom du prompt de pack de langue. ⚠ **Hors `core.langues.PROMPTS_REQUIS`** : les huit
#: prompts de ce tuple sont ceux dont l'absence fait échouer `_verifier_prompts` et
#: invaliderait le pack `langues/en`. Le modèle est `manga_relecteur.md` — livré dans les
#: deux packs, absent du tuple.
PROMPT = "illustration_style"

#: Les deux usages du **même** canal d'images. Les mélanger sans le dire produit une image
#: dont on ne sait pas ce qui a raté (`PLAN-26` L26.0, règle 0).
USAGE_IDENTITE = "identite"
USAGE_ANCRAGE = "ancrage"

#: ⚠ **2, et c'est un verdict de mesure, pas une prudence.** `PLAN-25` L25.1 §5.4 :
#: « la rupture est entre 1 et 2, pas entre 2 et 3 » — à une référence le modèle rend un
#: COLLAGE, à deux un portrait cohérent, et la troisième est **indiscernable de la
#: deuxième** à l'œil comme au juge. Elle coûte pourtant 175 s de plus par image sur ce
#: relevé. Le plafond du plan est « celui mesuré par L25.1, pas un autre ».
#:
#: ⚠ Il est plus bas que `identite.REFERENCES_MAX` (3), et ce n'est pas une incohérence :
#: 3 est ce que le **graphe** sait câbler (`TextEncodeQwenImageEditPlus` expose `image1`,
#: `image2`, `image3`), 2 est ce que la **mesure** recommande. Une limite technique et une
#: limite mesurée ne sont pas la même chose et n'ont pas à coïncider.
PLAFOND_REFERENCES = 2

#: Une ancre de style. Le plan en demande « au moins une » si l'approche 2 est retenue ; le
#: coût de la seconde n'est pas mesuré **au 2026-09-02**, et le canal du graphe livré n'a que
#: trois places au total — dont deux prises par l'identité.
PLAFOND_ANCRAGES = 1

#: Motifs nommés et comptés, comme partout dans le dépôt.
MOTIFS = {
    "non_validee": "référence non validée par un humain (il faut `confiance: humaine`)",
    "plafond": "plafond du lot 25 atteint",
    "couverture": "couverture : titre et logo d'éditeur peints dans les pixels",
    "generee": "image GÉNÉRÉE — jamais candidate, le rebouclage est interdit",
    "introuvable": "fichier absent du disque",
    "llm_refuse": "le modèle de vision ne reconnaît pas le personnage sur cette image",
    "llm_visage": "un visage lisible : cette ancre contaminerait l'identité",
    "llm_illisible": "réponse du modèle mal formée — traitée comme non retenue",
}


# ────────────────────────────────  Ce qu'on choisit  ────────────────────────────────

@dataclass(frozen=True)
class Candidate:
    """Une image proposée au choix, **avant** décision."""

    fichier: str
    source: Path
    usage: str = USAGE_IDENTITE
    confiance: str = "proposee"
    classe: str = ""
    contexte: str = ""

    @property
    def validee(self) -> bool:
        return self.confiance == "humaine"

    @property
    def couverture(self) -> bool:
        return self.classe == "couverture"


@dataclass(frozen=True)
class Choix:
    """Une décision, **avec son motif**. `motif` n'est jamais vide — c'est la règle 3."""

    fichier: str
    motif: str
    retenue: bool
    usage: str = USAGE_IDENTITE
    #: `deterministe` ou `llm` — l'utilisateur doit savoir qui a décidé.
    par: str = "deterministe"
    #: Le modèle de vision a-t-il vu un visage ? `None` = pas demandé.
    visage: bool | None = None

    def payload(self) -> dict:
        """Ce qui s'écrit dans `requete.yaml`. ⚠ Ordre figé : `fichier`, `motif`, `retenue` —
        c'est l'ordre de lecture d'un humain qui relit, pas l'ordre alphabétique."""
        bloc = {"fichier": self.fichier, "motif": self.motif, "retenue": bool(self.retenue),
                "par": self.par}
        if self.visage is not None:
            bloc["visage"] = bool(self.visage)
        return bloc


@dataclass
class Selection:
    """Le résultat complet d'une phase 1 de choix d'images."""

    references: list = field(default_factory=list)
    ancrages: list = field(default_factory=list)
    secondes: float = 0.0
    #: Nombre d'appels au modèle de vision. 0 = sélection purement déterministe.
    appels_llm: int = 0

    def retenues(self, usage: str = USAGE_IDENTITE) -> list:
        source = self.references if usage == USAGE_IDENTITE else self.ancrages
        return [c for c in source if c.retenue]

    def motifs(self) -> dict:
        compte: dict = {}
        for choix in list(self.references) + list(self.ancrages):
            if not choix.retenue:
                compte[choix.motif] = compte.get(choix.motif, 0) + 1
        return dict(sorted(compte.items(), key=lambda c: (-c[1], c[0])))


# ──────────────────────────────  Les candidates  ──────────────────────────────

def candidates_identite(bible_doc: dict, personnage: str, racine_projet) -> list:
    """Les références d'identité déclarées pour ce personnage, résolues sur le disque.

    ⚠ La résolution passe par `illustration.identite.references_de`, qui passe elle-même par
    `core.bible.reference_existe` — **la** règle du dépôt. En écrire une seconde ici a déjà
    été un défaut, corrigé le 2026-08-29 : la bible est par PROJET, et 7 des 10 références du
    corpus réel vivent dans un autre tome que celui qu'on illustre."""
    sorties = []
    for reference in ident_mod.references_de(bible_doc, personnage, racine_projet):
        sorties.append(Candidate(
            fichier=reference.fichier, source=reference.source, usage=USAGE_IDENTITE,
            confiance=reference.confiance, classe=reference.classe,
            contexte=reference.contexte))
    return _refuser_les_generees(sorties)[0]


def candidates_ancrage(bible_doc: dict, racine_projet) -> list:
    """Les ancrages de style **validés par un humain**, résolus sur le disque.

    Ce sont les 2 à 5 ancrages que le `PLAN-23` L23.7 a retenus : les illustrations les plus
    proches du centre de la signature du tome, relues à la main. Une ancre non validée n'est
    pas une ancre — c'est une proposition."""
    style = (bible_doc or {}).get("style") or {}
    classes = ident_mod.classes_du_projet(racine_projet)
    sorties = []
    for brute in style.get("ancrages") or []:
        if not isinstance(brute, dict) or not brute.get("valide_par_humain"):
            continue
        fichier = str(brute.get("fichier") or "")
        source = ident_mod.resoudre(fichier, racine_projet)
        if source is None:
            continue
        sorties.append(Candidate(
            fichier=fichier, source=source, usage=USAGE_ANCRAGE, confiance="humaine",
            classe=classes.get((source.parent.parent.name, source.name),
                               str(brute.get("classe") or "")),
            contexte=str(brute.get("motif") or "")))
    return _refuser_les_generees(sorties)[0]


def _refuser_les_generees(candidates: list) -> tuple[list, list]:
    """Écarte toute candidate qui est une image PRODUITE. Rend `(gardées, écartées)`.

    ⚠ **Règle 2 du `PLAN-26` L26.0, et elle est absolue** : « une image générée n'est jamais
    candidate ». Deux signes suffisent et ils sont indépendants :

    1. elle vit sous le dossier de la brique (`illustrations/`) — c'est le seul endroit où
       la brique écrit, `illustration/frontiere.py` le garantit à l'exécution ;
    2. elle porte le marquage AI Act dans son PNG — et **aucun chemin de code de ce dépôt ne
       sait écrire un PNG généré sans ce bloc** (`illustration/marquage.py`), donc le signe
       est fiable dans le sens qui compte : ce qui le porte est généré.

    ⚠ Le second signe n'est **pas** réciproque : une image générée par un autre programme et
    déposée dans `media/` ne le porterait pas, et rien ici ne l'attraperait. C'est la limite,
    elle est écrite, et elle est la même que celle de tout marquage — l'article 50(2) oblige
    le fournisseur à marquer, il ne rend pas les images des autres détectables."""
    from illustration.orchestrateur import NOM_DOSSIER

    gardees, ecartees = [], []
    for candidate in candidates:
        parties = {p.casefold() for p in candidate.source.parts}
        if NOM_DOSSIER.casefold() in parties or _porte_le_marquage(candidate.source):
            ecartees.append(Choix(fichier=candidate.fichier, motif=MOTIFS["generee"],
                                  retenue=False, usage=candidate.usage))
            continue
        gardees.append(candidate)
    return gardees, ecartees


def _porte_le_marquage(source: Path) -> bool:
    """Le PNG porte-t-il le bloc tEXt d'image générée ? Best-effort : un fichier illisible
    n'est pas déclaré généré — on ne refuse pas sur une erreur d'ouverture."""
    if source.suffix.casefold() != ".png":
        return False
    try:
        from PIL import Image

        from illustration import marquage

        with Image.open(source) as image:
            info = {str(k).casefold() for k in (image.info or {})}
        return any(str(cle).casefold() in info for cle in marquage.CHAMPS_PNG)
    except Exception:                                # noqa: BLE001 — diagnostic seulement
        return False


# ──────────────────────────────  Le choix déterministe  ──────────────────────────────

def choisir(candidates: list, *, plafond: int, usage: str = USAGE_IDENTITE) -> list:
    """La sélection **sans LLM** : reproductible, testable en CI, et c'est le défaut.

    L'ordre est celui de la bible, **couvertures en queue** — le lot 25 a mesuré pourquoi :
    les trois premières références validées du corpus sont trois couvertures de light novel,
    dont deux sont le même dessin (cosinus 0,9637), et conditionner là-dessus fait reproduire
    la composition de la page.

    ⚠ Ce n'est pas un tri par « meilleure référence » : le code ne sait pas laquelle est la
    meilleure, et c'est précisément la question que le LLM et l'humain sont là pour trancher."""
    choix: list = []
    ordonnees = sorted(candidates, key=lambda c: (not c.validee, c.couverture))
    retenues = 0
    for candidate in ordonnees:
        if not candidate.validee:
            choix.append(Choix(candidate.fichier, MOTIFS["non_validee"], False, usage))
            continue
        if retenues >= plafond:
            choix.append(Choix(
                candidate.fichier,
                f"{MOTIFS['plafond']} : {plafond} référence(s) suffisent — la 3e est "
                f"indiscernable de la 2e (identite-2026-08-29 §5.4)"
                if usage == USAGE_IDENTITE else f"{MOTIFS['plafond']} ({plafond})",
                False, usage))
            continue
        choix.append(Choix(candidate.fichier, _motif_retenue(candidate), True, usage))
        retenues += 1
    return choix


def _motif_retenue(candidate: Candidate) -> str:
    """Le motif d'une image retenue sans LLM. Il dit d'où vient la décision, pas qu'elle est
    bonne : « validée par un humain » est vérifiable, « bonne référence » ne l'est pas."""
    if candidate.couverture:
        return (f"{MOTIFS['couverture']} — retenue faute de mieux, et passée en dernier ; "
                f"cf. illustration/identite.py:TITRE_DANS_LES_PIXELS")
    contexte = f", {candidate.contexte}" if candidate.contexte else ""
    classe = candidate.classe or "classe inconnue"
    if candidate.usage == USAGE_ANCRAGE:
        return f"ancre de style validée à la main ({classe}{contexte})"
    return f"référence d'identité validée par un humain ({classe}{contexte})"


# ──────────────────────────────  Le choix par le LLM  ──────────────────────────────

_LIGNE = re.compile(r"^\s*(retenue|visage|motif)\s*:\s*(.+?)\s*$", re.IGNORECASE)

#: Longueur maximale d'un motif rendu par le modèle. Au-delà, il a écrit un paragraphe et
#: non une ligne : le motif est **tronqué** — et c'est le seul endroit de ce lot où on
#: tronque plutôt que de rejeter, parce qu'un motif est de la documentation pour l'humain,
#: pas une donnée qui décide. Un attribut tronqué serait faux ; un motif tronqué reste utile.
MOTIF_MAX = 160


def analyser(reponse: str) -> tuple[bool, bool | None, str]:
    """`(retenue, visage, motif)` depuis les trois lignes attendues.

    ⚠ Une réponse mal formée rend `(False, None, …)` — **non retenue**. Le défaut penche du
    côté du refus, comme partout dans cette brique : une image entrée par erreur dans le
    conditionnement produit un portrait faux qu'on ne sait pas expliquer, une image écartée
    par erreur se rattrape en décochant une case."""
    champs: dict = {}
    for ligne in (reponse or "").splitlines():
        trouve = _LIGNE.match(ligne)
        if trouve:
            champs.setdefault(trouve.group(1).casefold(), trouve.group(2).strip())
    if "retenue" not in champs:
        return False, None, MOTIFS["llm_illisible"]
    retenue = champs["retenue"].casefold().startswith(("oui", "yes", "true"))
    visage = None
    if "visage" in champs:
        visage = champs["visage"].casefold().startswith(("oui", "yes", "true"))
    motif = champs.get("motif") or ""
    motif = " ".join(motif.split())[:MOTIF_MAX]
    return retenue, visage, motif or MOTIFS["llm_illisible"]


def choisir_avec_llm(candidates: list, *, plafond: int, usage: str, llm, modele: str,
                     systeme: str, personnage: str = "", cote: int = 0,
                     dire=None) -> tuple[list, float, int]:
    """La sélection **par le modèle de vision**, une image par appel.

    Rend `(choix, secondes, appels)`. Un appel par image est le lot le plus petit possible :
    `yume-27b` tient 32 768 jetons de contexte et `decoupage.max_input_tokens` en autorise
    24 000, ce qui ne laisse pas la place à vingt illustrations. Découper ainsi rend aussi le
    coût **linéaire et mesurable** — 8,3 s par illustration au lot 23, à revérifier ici.

    ⚠ **Le plafond est appliqué APRÈS le modèle, pas avant.** Il faut un motif pour chaque
    image, y compris pour celles que le plafond écarte : sans ça, un utilisateur ne saurait
    pas qu'une troisième référence existait et qu'elle avait été jugée bonne."""
    from core.bible_llm import COTE_VISION, image_en_base64

    dire = dire or (lambda _m: None)
    depart = time.monotonic()
    verdicts: list = []
    appels = 0
    for candidate in candidates:
        if not candidate.validee:
            verdicts.append((candidate, False, None, MOTIFS["non_validee"]))
            continue
        message = _message(usage, personnage, candidate)
        try:
            reponse = llm.chat(modele, systeme, message, temperature=0.0,
                               images=[image_en_base64(candidate.source,
                                                       cote or COTE_VISION)])
            appels += 1
        except Exception as err:                     # noqa: BLE001 — un appel raté n'arrête pas
            # ⚠ Un appel raté n'est PAS traité comme un refus du modèle : il est nommé à part.
            # Confondre « le modèle a dit non » et « le serveur n'a pas répondu » ferait
            # disparaître une panne dans un compteur de refus.
            dire(f"    ⚠ appel de vision échoué sur {candidate.fichier} : {err}")
            verdicts.append((candidate, False, None,
                             f"appel de vision échoué — {type(err).__name__}"))
            continue
        retenue, visage, motif = analyser(reponse)
        verdicts.append((candidate, retenue, visage, motif))
    secondes = time.monotonic() - depart
    return _appliquer_plafond(verdicts, plafond=plafond, usage=usage), secondes, appels


def _message(usage: str, personnage: str, candidate: Candidate) -> str:
    """Le message utilisateur. Il nomme l'usage et **rien de l'œuvre** : le modèle n'a pas
    besoin du titre pour dire si un visage est lisible, et le lui donner le ferait entrer
    dans une trace."""
    lignes = [f"usage: {usage}"]
    if usage == USAGE_IDENTITE:
        lignes.append(f"personnage: {personnage}")
    if candidate.classe:
        lignes.append(f"classe de l'image (mesurée, pas devinée) : {candidate.classe}")
    return "\n".join(lignes)


def _appliquer_plafond(verdicts, *, plafond: int, usage: str) -> list:
    """Le plafond, appliqué sur les images que le modèle a retenues — **couvertures en
    queue**, comme dans le choix déterministe et pour la même raison mesurée."""
    ordonnes = sorted(verdicts, key=lambda v: (not v[1], v[0].couverture))
    choix, retenues = [], 0
    for candidate, retenue, visage, motif in ordonnes:
        if not retenue:
            choix.append(Choix(candidate.fichier, motif, False, usage, par="llm",
                               visage=visage))
            continue
        if usage == USAGE_ANCRAGE and visage:
            choix.append(Choix(candidate.fichier,
                               f"{MOTIFS['llm_visage']} — {motif}", False, usage,
                               par="llm", visage=visage))
            continue
        if retenues >= plafond:
            choix.append(Choix(candidate.fichier,
                               f"{MOTIFS['plafond']} ({plafond}) — le modèle la jugeait "
                               f"bonne : {motif}", False, usage, par="llm", visage=visage))
            continue
        choix.append(Choix(candidate.fichier, motif, True, usage, par="llm", visage=visage))
        retenues += 1
    return choix
