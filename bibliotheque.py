# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'inventaire des œuvres — **un seul modèle, deux affichages**.

## Pourquoi ce module est à la RACINE — et pas dans `core/`, comme le plan le demandait

Il couvre les **quatre** briques. `manga/serie.py` sait tout d'un chapitre manga et rien d'un
roman ; `pipeline/sources.py` sait lire un tome de light novel et ignore les planches. Une
bibliothèque qui n'afficherait que l'une des deux hiérarchies obligerait l'utilisateur à
retenir laquelle de ses 18 œuvres est un manga — c'est-à-dire à faire de tête le travail
qu'on lui promet.

> ⚠ **Le `PLAN-34` L34.1 demandait `core/bibliotheque.py`, « parce qu'il couvre les deux
> briques ». C'est exactement le raisonnement qui l'en EXCLUT**, et le dépôt le teste :
> `tests/test_core_alias.py:test_le_socle_ne_depend_pas_du_pipeline` et
> `tests/test_core_cli.py:test_le_socle_nimporte_ni_les_briques_ni_les_cli` refusent qu'un
> module de `core/` importe `manga`, `pipeline`, `run*` ou `app`. Le socle est ce dont les
> briques dépendent, pas l'inverse ; un agrégateur de briques y créerait le cycle que le lot
> qui a extrait `core/` de `pipeline/` avait précisément défait.
>
> Ce module vit donc à la **racine**, la couche qui est déjà au-dessus des quatre briques —
> celle de `app.py`, `gui.py` et des quatre `run_*.py`. Il est importable par les CLI, par
> `gui/` et par `tools/` sans inverser une seule dépendance. Constaté et corrigé le
> 2026-09-05 ; cf. `docs/mesures/bibliotheque-2026-09-05.md` §2.

## Ce qu'« œuvre » veut dire ici — tranché à l'étape 0.3 du `PLAN-34`

Une **œuvre** est un dossier de `sources/`. Elle porte un ou plusieurs **tomes**, et chaque
tome porte une ou plusieurs **briques**, déduites de son arborescence :

| Arborescence | Brique |
|---|---|
| `<Tome>/manga/…`, ou des images à plat sous `<Tome>/` | `manga` |
| `<Tome>/webtoon/…` | `webtoon` |
| `<Tome>/<LANGUE>/*.pdf .epub .docx .txt .md` | `ln` |
| `<Tome>/<LANGUE>/*.png .jpg …` (images SEULES) | `scan` |

⚠ **Un tome peut en porter plusieurs, et ce n'est pas un cas d'école** : au 2026-09-05,
`sources/manga C/Vol.1/` porte `JAP/` (272 images, brique scan) **et**
`manga/` (165 planches, brique manga). `TomeInfo.brique` nomme donc la brique **principale**
— la première de l'ordre de préférence ci-dessus — et `TomeInfo.briques` les porte toutes.
Le champ singulier que le plan décrivait aurait fait disparaître la moitié de ce tome.

Et le glossaire est **par œuvre**, partagé roman ↔ manga (`sources/<Projet>/glossaire.yaml`) :
c'est le différenciateur n° 1 du projet, et c'est pour cela que `TomeInfo.glossaire` porte le
compte de l'œuvre et non un compte propre au tome, qui n'existe pas.

## Ce que ce module ne fait JAMAIS

1. ⚠ **Il n'ouvre aucune image.** 18 œuvres, 55 tomes, 3 493 planches et pages source
   dénombrées au 2026-09-05 : une vue qui les décode met dix secondes à s'afficher. Les
   tailles se lisent dans les métadonnées de fichier, les états dans `.checkpoints/`, jamais
   dans les pixels.
   `tests/test_bibliotheque.py` le vérifie **par instrumentation** — `PIL.Image.open`
   remplacé par une fonction qui lève — et pas par confiance.
2. ⚠ **Il ne charge aucun modèle et n'appelle aucun LLM.**
3. ⚠ **Il n'importe rien de lourd au niveau module.** C'est la règle de budget que
   `manga/serie.py` tient déjà, et pour la même raison : `run_manga.py --list` consomme ce
   module, et `--list`/`--help` passeraient de 0,19 s à 0,46 s si numpy et Pillow arrivaient
   à l'import. Tout ce qui est lourd est importé **dans** les fonctions qui en ont besoin.

## Et il ne réimplémente pas ce qui existe

`etapes` et `perimees` passent par `manga/etat_planches.py` et `manga/checkpoints.py`, le
statut manga par `manga/serie.py:etat_chapitre`. Une seconde lecture de l'état des
checkpoints qui divergerait de la première donnerait une bibliothèque qui affiche « fait »
sur un tome que le pipeline va refaire.

⚠ **« Périmé » garde EXACTEMENT le sens de `gui/fenetre.py:_planches_perimees`**, c'est-à-dire
`etat_planches.planches_a_relettrer` : une planche dont le rendu est antérieur à l'une de ses
données. En inventer un second sens serait pire que ne rien afficher — et c'est une notion de
la brique manga : un tome de light novel n'a pas de rendu par unité à comparer, et ce module
ne lui en invente pas.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
#  Le vocabulaire
# --------------------------------------------------------------------------- #

MANGA = "manga"
WEBTOON = "webtoon"
LN = "ln"
SCAN = "scan"

#: Ordre de PRÉFÉRENCE quand un tome porte plusieurs briques. Il n'est pas arbitraire : les
#: deux briques d'images paginées d'abord (ce sont elles qui portent un état par planche,
#: donc le plus à afficher), puis le roman, puis l'OCR de scans — qui est une étape amont du
#: roman et non une sortie en soi.
BRIQUES: tuple[str, ...] = (MANGA, WEBTOON, LN, SCAN)

LIBELLES_BRIQUE: dict[str, str] = {
    MANGA: "Manga",
    WEBTOON: "Webtoon",
    LN: "Light novel",
    SCAN: "Scan (bêta)",
}

#: L'unité que compte `TomeInfo.unites`, par brique. Un chiffre sans dénominateur n'est pas
#: une mesure (cf. `docs/chiffres-de-reference.md`) : « 150 » ne veut pas dire la même chose
#: pour un manga et pour un roman, et la colonne doit le dire.
UNITES: dict[str, str] = {
    MANGA: "planche", WEBTOON: "bande", LN: "chapitre", SCAN: "page",
}

#: États d'une étape.
FAITE = "faite"
PARTIELLE = "partielle"
ABSENTE = "absente"
PERIMEE = "perimee"

ETATS_ETAPE: tuple[str, ...] = (FAITE, PARTIELLE, ABSENTE, PERIMEE)

#: Ce qu'un état veut dire, en toutes lettres. **La légende est obligatoire** (`PLAN-34`
#: L34.2) : une pastille sans légende est une couleur, et le lot 19 a livré l'accessibilité
#: qui interdit de dire un état par la couleur seule. Elle vit ici, sans Qt, pour que la vue,
#: une infobulle et un rapport console la disent avec les mêmes mots.
LEGENDE_ETATS: tuple[tuple[str, str, str], ...] = (
    (FAITE, "●", "toutes les unités du tome portent le cache de cette étape"),
    (PARTIELLE, "◐", "une partie seulement — run interrompu, ou unités en échec"),
    (ABSENTE, "○", "aucune unité : l'étape n'a jamais tourné"),
    (PERIMEE, "↻", "le rendu est ANTÉRIEUR à des données modifiées depuis "
                   "(manga/etat_planches.py)"),
)

#: Étapes de la brique manga et le fichier de checkpoint qui les atteste. Les noms sont ceux
#: de `manga.checkpoints.STAGES`, dans leur ordre d'exécution ; `verifier_coherence_etapes()`
#: refuse qu'ils divergent, plutôt que de laisser deux listes vieillir séparément.
_ETAPES_FICHIER_MANGA: tuple[tuple[str, str], ...] = (
    ("detection", "regions.json"),
    ("nettoyage", ""),                     # pages_clean/, pas un fichier de checkpoint
    ("ocr", "ocr.json"),
    ("terminologie", "terminologie.txt"),
    ("traduction", "traduction.json"),
    ("sfx", "sfx.json"),
    ("rendu", ""),                         # pages_out/
)

#: Étapes du light novel dont le cache est un SOUS-DOSSIER de `.checkpoints/<chapitre>/`.
#: `rendu` n'en est pas : sa sortie est le `.docx`/`.epub`/`.pdf` lui-même.
_ETAPES_DOSSIER_LN: tuple[str, ...] = ("terminologie", "traduction", "correction",
                                       "mise_en_page")

_ETAPES_FICHIER_SCAN: tuple[tuple[str, str], ...] = (
    ("analyse", "plan.json"),
    ("lecture", "texte.json"),
)


def etapes_de_brique(brique: str) -> tuple[str, ...]:
    """Les étapes affichées pour cette brique, dans l'ordre d'exécution de son orchestrateur."""
    if brique in (MANGA, WEBTOON):
        return tuple(nom for nom, _ in _ETAPES_FICHIER_MANGA)
    if brique == LN:
        return (*_ETAPES_DOSSIER_LN, "rendu")
    if brique == SCAN:
        return (*(nom for nom, _ in _ETAPES_FICHIER_SCAN), "assemblage")
    return ()


def verifier_coherence_etapes() -> list[str]:
    """Les écarts entre les étapes déclarées ici et celles des orchestrateurs.

    Rendue plutôt que levée : c'est un test qui doit échouer, pas un import. Elle existe
    parce qu'une bibliothèque qui afficherait une colonne « sfx » après que l'orchestrateur
    l'a renommée montrerait un rond vide sur une étape qui tourne."""
    from manga.checkpoints import STAGES as STAGES_MANGA
    from pipeline.orchestrator import STAGES as STAGES_LN

    ecarts: list[str] = []
    nos_manga = [nom for nom, _ in _ETAPES_FICHIER_MANGA]
    if nos_manga != list(STAGES_MANGA):
        ecarts.append(f"manga : {nos_manga} ≠ manga.checkpoints.STAGES {list(STAGES_MANGA)}")
    nos_ln = list(etapes_de_brique(LN))
    if nos_ln != list(STAGES_LN):
        ecarts.append(f"ln : {nos_ln} ≠ pipeline.orchestrator.STAGES {list(STAGES_LN)}")
    return ecarts


# --------------------------------------------------------------------------- #
#  Le modèle
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TomeInfo:
    """Ce qu'on sait d'un tome **sans l'ouvrir** : l'état sur disque, et rien d'autre.

    `unites` vaut `None` quand le compte n'est pas connaissable sans payer une extraction —
    une archive `.cbr` (qui demanderait `unrar`), ou un roman dont les chapitres sont
    découpés à l'extraction. `None` ne veut **jamais** dire zéro : c'est la même distinction
    que `manga.serie.EtatChapitre.pages_source`, et elle compte, parce qu'on ne saute pas un
    tome sur une incertitude.

    `statut` et `detail` reprennent le vocabulaire de `manga/serie.py` (`termine`, `partiel`,
    `non_traite`, `a_relettrer`, `sans_source`) pour les quatre briques : un seul mot pour un
    seul état, quelle que soit la brique qui le produit.

    `verdict_manga` est le verdict **de la brique manga**, tel que `run_manga.py --list`
    l'imprime — y compris sur un tome de roman, où il vaut « aucune image ni archive ». Il est
    porté séparément parce que c'est la réponse à une autre question : *le run manga a-t-il
    quelque chose à faire ici ?* Confondre les deux ferait dire à `--list` qu'un roman est
    « terminé », ce qui serait faux pour la commande qui pose la question.
    """

    projet: str
    tome: str
    brique: str
    briques: tuple[str, ...] = ()
    format: str | None = None
    langue_source: str | None = None
    unites: int | None = None
    unite: str = ""
    etapes: dict[str, str] = field(default_factory=dict)
    sorties: dict[str, Path] = field(default_factory=dict)
    glossaire: int | None = None
    dernier_run: float | None = None
    statut: str = "non_traite"
    detail: str = ""
    perimees: tuple[int, ...] = ()
    verdict_manga: object = None

    @property
    def libelle_brique(self) -> str:
        """« Manga », « Manga + Scan (bêta) » — toutes les briques du tome, dans l'ordre."""
        return " + ".join(LIBELLES_BRIQUE.get(b, b) for b in self.briques or (self.brique,))

    @property
    def compte(self) -> str:
        """« 150 planches », ou « ? planches » quand le compte n'est pas connaissable."""
        unite = self.unite or UNITES.get(self.brique, "unité")
        if self.unites is None:
            return f"? {unite}s"
        return f"{self.unites} {unite}" + ("s" if self.unites > 1 else "")


@dataclass(frozen=True)
class Oeuvre:
    """Un dossier de `sources/`, ses tomes, et le glossaire qu'ils partagent."""

    projet: str
    tomes: tuple[TomeInfo, ...] = ()
    glossaire: int | None = None
    chemin_glossaire: Path | None = None

    @property
    def briques(self) -> tuple[str, ...]:
        vues = {b for t in self.tomes for b in (t.briques or (t.brique,)) if b}
        return tuple(b for b in BRIQUES if b in vues)


# --------------------------------------------------------------------------- #
#  Les chemins, lus là où la config les déclare
# --------------------------------------------------------------------------- #

def _chemins(config: dict) -> dict:
    from core import config as core_config
    return core_config.section(config, "manga", "chemins")


def racine_sources(config: dict) -> Path:
    return Path(_chemins(config)["sources"])


def racine_build(config: dict) -> Path:
    return Path(_chemins(config)["build"])


def chemin_glossaire(config: dict, projet: str) -> Path:
    nom = _chemins(config).get("glossaire_fichier", "glossaire.yaml")
    return racine_sources(config) / projet / nom


# --------------------------------------------------------------------------- #
#  Balayage : ce qui coûte, et ce qui ne coûte rien
# --------------------------------------------------------------------------- #

def _noms(dossier) -> set[str]:
    """Le contenu d'un dossier en **un seul** appel système, ou un ensemble vide.

    ⚠ `scandir` et non six `exists()`. Sur les dossiers de checkpoint du corpus, la
    différence entre « une entrée de répertoire lue une fois » et « cinq appels `stat` par
    planche » est le seul écart qui décide si la vue s'affiche ou si elle rame."""
    try:
        with os.scandir(dossier) as entrees:
            return {e.name for e in entrees}
    except OSError:
        return set()


def _mtime(chemin: Path) -> float | None:
    try:
        return chemin.stat().st_mtime
    except OSError:
        return None


def _etat_compte(fait: int, total: int | None) -> str:
    """De deux comptes à un état d'étape. Un `total` inconnu ne permet pas d'affirmer que
    c'est complet : on rend `partielle` dès qu'il y a quelque chose, jamais `faite`."""
    if fait <= 0:
        return ABSENTE
    if total is None or total <= 0:
        return PARTIELLE
    return FAITE if fait >= total else PARTIELLE


# --------------------------------------------------------------------------- #
#  Reconnaissance des briques
# --------------------------------------------------------------------------- #

def _exts_texte() -> tuple[str, ...]:
    """Reprises de `scan/pages.py:EXTS_TEXTE`, dont c'est déjà exactement le critère."""
    from scan.pages import EXTS_TEXTE
    return EXTS_TEXTE


def _exts_images() -> tuple[str, ...]:
    from manga.ingest import IMG_EXTS
    return IMG_EXTS


_ARCHIVES: tuple[str, ...] = (".cbz", ".cbr", ".zip")


def _dossiers_de_langue(config: dict | None) -> dict[str, str]:
    """`{"ENG": "en", "JAP": "jp", …}` — la table du light novel, celle que les trois
    scanneurs de sources consultent déjà."""
    dossiers = ((config or {}).get("langues") or {}).get("dossiers") or {}
    return {str(k).upper(): str(v).lower() for k, v in dossiers.items()}


def briques_du_tome(vol_dir, config: dict | None = None) -> tuple[str, ...]:
    """Les briques que ce tome porte, dans l'ordre de préférence de `BRIQUES`.

    Lecture seule et **sans extraction** : on regarde des noms de fichiers, jamais leur
    contenu. Un `.cbz` compte comme des planches sans jamais être ouvert."""
    vol_dir = Path(vol_dir)
    images, textes = _exts_images(), _exts_texte()
    trouvees: set[str] = set()

    # ⚠ La sortie de la brique scan est un `<Tome>.md` écrit DANS le dossier de langue. La
    # compter comme une source de light novel ferait passer un tome tout juste OCRisé pour un
    # roman qui n'a plus besoin de l'être — et ferait disparaître sa brique scan de la vue.
    # `scan/pages.py` exclut déjà ce fichier de son propre scan, ligne pour ligne, et pour la
    # même raison.
    notre_sortie = f"{vol_dir.name}.md".lower()

    def _contenu(dossier) -> tuple[bool, bool]:
        """(porte des images ou une archive, porte un fichier texte) — à plat."""
        a_image = a_texte = False
        try:
            with os.scandir(dossier) as entrees:
                for e in entrees:
                    if not e.is_file():
                        continue
                    suffixe = Path(e.name).suffix.lower()
                    if suffixe in images or suffixe in _ARCHIVES:
                        a_image = True
                    elif suffixe in textes and e.name.lower() != notre_sortie:
                        a_texte = True
        except OSError:
            return False, False
        return a_image, a_texte

    for fmt in (MANGA, WEBTOON):
        racine = vol_dir / fmt
        if not racine.is_dir():
            continue
        if _contenu(racine)[0]:
            trouvees.add(fmt)
            continue
        try:
            sous = [p for p in racine.iterdir() if p.is_dir()]
        except OSError:
            sous = []
        if any(_contenu(s)[0] for s in sous):
            trouvees.add(fmt)

    # Repli historique : les planches sont directement sous `<Tome>/`, sans dossier de format.
    if not trouvees and _contenu(vol_dir)[0]:
        trouvees.add(MANGA)

    mapping = _dossiers_de_langue(config)
    try:
        sous_dossiers = [p for p in vol_dir.iterdir() if p.is_dir()]
    except OSError:
        sous_dossiers = []
    for sous in sous_dossiers:
        if sous.name.upper() not in mapping:
            continue
        a_image, a_texte = _contenu(sous)
        if a_texte:
            trouvees.add(LN)
        if a_image:
            # Des images dans un dossier de langue : c'est le cas exact que `scan/pages.py`
            # existe pour traiter, et que `pipeline/sources.py` refuse. Les deux briques
            # peuvent coexister — un tome OCRisé porte ses 271 pages ET le `.md` qui en sort.
            trouvees.add(SCAN)

    return tuple(b for b in BRIQUES if b in trouvees)


# --------------------------------------------------------------------------- #
#  L'état d'un tome, brique par brique
# --------------------------------------------------------------------------- #

def _etat_manga(config: dict, projet: str, tome: str, brique: str) -> dict:
    """Étapes, sorties, périmées et dernier run d'un tome manga/webtoon.

    ⚠ Le statut vient de `manga.serie.etat_chapitre`, pas d'un second calcul : c'est lui que
    `run_manga.py --list` imprime depuis la 2.6.0, et c'est lui qui décide si un run de nuit
    doit sauter le chapitre."""
    from manga import serie

    vol_dir = racine_sources(config) / projet / tome
    build_dir = serie.build_dir_de(racine_build(config), projet, tome)

    # ⚠ **Un** balayage pour tout le tome, et il vient de `manga/etat_planches.py`. Il sert
    # deux fois : à compter les étapes ici, et à répondre « périmé ? » dans
    # `serie.etat_chapitre`, à qui on le PASSE. Le laisser recalculer doublerait le coût du
    # balayage complet — et surtout donnerait deux lectures de l'état des checkpoints, ce que
    # le `PLAN-34` interdit nommément.
    #
    # ⚠ **Et il est gardé par l'existence de `.checkpoints/`, ce qui n'est pas cosmétique.**
    # `manga.etat_planches` tire `manga.checkpoints`, donc numpy et Pillow. Sans cette garde,
    # `run_manga.py "manga C" --list` — six tomes qui n'ont jamais tourné —
    # les importerait pour balayer un dossier qui n'existe pas. C'est exactement le budget
    # d'imports que `manga/serie.py` décrit dans sa docstring, et le mesurer était le seul
    # moyen de voir qu'on venait de le casser : au 2026-09-05, avant cette garde,
    # `--list` importait numpy et PIL là où la 2.27.0 ne les importait pas.
    #
    # Un dictionnaire vide n'est PAS « je ne sais pas » : c'est « ce tome n'a aucune planche
    # en cache », ce qui est la réponse juste, et c'est aussi ce que `balayer_tome` rendrait.
    balayage: dict[int, dict] = {}
    if (build_dir / ".checkpoints").is_dir():
        from manga import etat_planches
        balayage = etat_planches.balayer_tome(build_dir)

    verdict = serie.etat_chapitre(racine_sources(config), racine_build(config),
                                  projet, tome, config, balayage=balayage)
    comptes = {nom: 0 for nom, _ in _ETAPES_FICHIER_MANGA}
    dernier: float | None = None
    for etat_page in balayage.values():
        fichiers = etat_page["fichiers"]
        for etape, fichier in _ETAPES_FICHIER_MANGA:
            if fichier and fichier in fichiers:
                comptes[etape] += 1
        for date in (etat_page["mtime"], etat_page["rendu"]):
            if date is not None and (dernier is None or date > dernier):
                dernier = date
    total = verdict.pages_source
    denominateur = total if total else (len(balayage) or None)
    nettoyees = sum(1 for n in _noms(build_dir / "pages_clean") if n.endswith(".png"))
    rendues = verdict.pages_rendues

    etapes: dict[str, str] = {}
    for etape, fichier in _ETAPES_FICHIER_MANGA:
        if etape == "nettoyage":
            etapes[etape] = _etat_compte(nettoyees, denominateur)
        elif etape == "rendu":
            etat = _etat_compte(rendues, denominateur)
            # ⚠ Le SEUL endroit du module qui produit `perimee`, et il ne calcule rien :
            # `verdict.perimees` vient de `etat_planches.planches_a_relettrer`, la fonction
            # que `gui/fenetre.py:_planches_perimees` appelle déjà.
            if verdict.perimees and etat == FAITE:
                etat = PERIMEE
            etapes[etape] = etat
        else:
            etapes[etape] = _etat_compte(comptes[etape], denominateur)

    sorties: dict[str, Path] = {}
    for cle, chemin in (("cbz", build_dir / f"{projet}_{tome}.cbz"),
                        ("pdf", build_dir / f"{projet}_{tome}.pdf"),
                        ("rapport", build_dir / "RAPPORT.md")):
        if chemin.is_file():
            sorties[cle] = chemin
    if rendues:
        sorties["images"] = build_dir / "pages_out"
    if nettoyees:
        sorties["clean"] = build_dir / "pages_clean"
    if any(n.endswith(".psd") for n in _noms(build_dir / "pages_psd")):
        sorties["psd"] = build_dir / "pages_psd"

    format_source: str | None = None
    langue: str | None = None
    try:
        from manga import sources_manga
        _dossier, format_source, langue, _av = sources_manga.resoudre_source(vol_dir, config)
    except SystemExit:
        pass
    if format_source is None and brique == WEBTOON:
        format_source = WEBTOON

    return {"etapes": etapes, "sorties": sorties, "dernier_run": dernier,
            "unites": total, "format": format_source, "langue_source": langue,
            "statut": verdict.statut, "detail": verdict.detail,
            "perimees": tuple(verdict.perimees), "verdict": verdict}


def _etat_ln(config: dict, projet: str, tome: str) -> dict:
    """Étapes et sorties d'un tome de light novel.

    ⚠ **Aucun « périmé » ici, et c'est délibéré.** Le mot a un sens précis dans ce dépôt — un
    rendu de planche antérieur à ses données — et le light novel n'a pas de rendu par unité à
    comparer. En inventer un second sens pour remplir une colonne serait exactement ce que le
    `PLAN-34` interdit."""
    from manga import serie

    build_dir = racine_build(config) / projet / tome
    chapitres = sorted(n for n in _noms(build_dir / ".checkpoints") if not n.startswith("."))
    fichiers_md = sorted(n for n in _noms(build_dir / "chapters") if n.endswith(".md"))
    total = len(chapitres) or len(fichiers_md) or None

    comptes = dict.fromkeys(_ETAPES_DOSSIER_LN, 0)
    dernier: float | None = None
    for nom in chapitres:
        dossier = build_dir / ".checkpoints" / nom
        presents = _noms(dossier)
        for etape in _ETAPES_DOSSIER_LN:
            if etape in presents:
                comptes[etape] += 1
        mtime = _mtime(dossier)
        if mtime is not None and (dernier is None or mtime > dernier):
            dernier = mtime

    # `pipeline/orchestrator.py` écrit `build/<P>/<T>/<Projet>_<Tome>.md`, espaces comprises
    # remplacées par des « _ » — et `pipeline/render.py` en dérive le `.docx`, l'`.epub` et le
    # `.pdf` par simple changement de suffixe.
    tige = f"{projet}_{tome}".replace(" ", "_")
    sorties: dict[str, Path] = {}
    for cle in ("md", "docx", "epub", "pdf"):
        chemin = build_dir / f"{tige}.{cle}"
        if chemin.is_file():
            sorties[cle] = chemin
    rapport = build_dir / "RAPPORT.md"
    if rapport.is_file():
        sorties["rapport"] = rapport

    etapes = {e: _etat_compte(comptes[e], total) for e in _ETAPES_DOSSIER_LN}
    rendus = [c for c in ("docx", "epub", "pdf") if c in sorties]
    etapes["rendu"] = (FAITE if rendus and "md" in sorties
                       else (PARTIELLE if "md" in sorties else ABSENTE))

    # ⚠ Le dossier de langue est résolu UNE fois. Il l'était trois fois — une par question
    # posée — et chaque résolution coûte un `iterdir` du tome plus un `scandir` par dossier de
    # langue. Sur roman N Vol.1 (dont le dossier `media/` est fourni), c'était 95 ms pour un
    # tome qui n'a jamais tourné.
    vol_dir = racine_sources(config) / projet / tome
    dossier_langue = _dossier_de_langue(vol_dir, config, texte=True)
    langue = _code_langue(dossier_langue, config)
    fichiers = _fichiers_du_dossier(dossier_langue, texte=True)
    format_source = Path(fichiers[0]).suffix.lstrip(".").lower() if fichiers else None

    if total is None:
        statut, detail = serie.NON_TRAITE, "aucun chapitre en cache"
    elif etapes["rendu"] == FAITE:
        statut = serie.TERMINE
        detail = f"{total} chapitre(s) · " + ", ".join(rendus)
    elif comptes["traduction"] >= total:
        statut, detail = serie.PARTIEL, f"{total} chapitre(s) traduit(s), aucun rendu"
    elif comptes["traduction"]:
        statut = serie.PARTIEL
        detail = f"{comptes['traduction']}/{total} chapitre(s) traduit(s)"
    else:
        statut, detail = serie.NON_TRAITE, f"{total} chapitre(s) à traduire"

    return {"etapes": etapes, "sorties": sorties, "dernier_run": dernier,
            "unites": total, "format": format_source, "langue_source": langue,
            "statut": statut, "detail": detail, "perimees": (), "verdict": None}


def _etat_scan(config: dict, projet: str, tome: str) -> dict:
    """Étapes et sorties de la brique OCR de scans (`run_ocr.py`)."""
    from manga import serie

    build_dir = racine_build(config) / projet / tome / "ocr"
    vol_dir = racine_sources(config) / projet / tome
    dossier_langue = _dossier_de_langue(vol_dir, config, texte=False)
    pages_source = len(_fichiers_du_dossier(dossier_langue, texte=False)) or None

    comptes = {nom: 0 for nom, _ in _ETAPES_FICHIER_SCAN}
    dernier: float | None = None
    try:
        with os.scandir(build_dir / ".checkpoints") as entrees:
            pages = [e for e in entrees if e.is_dir() and e.name.startswith("page_")]
    except OSError:
        pages = []
    for entree in pages:
        noms = _noms(entree.path)
        for etape, fichier in _ETAPES_FICHIER_SCAN:
            if fichier in noms:
                comptes[etape] += 1
        try:
            mtime = entree.stat().st_mtime
        except OSError:
            mtime = None
        if mtime is not None and (dernier is None or mtime > dernier):
            dernier = mtime

    total = pages_source or (len(pages) or None)
    etapes = {e: _etat_compte(comptes[e], total) for e, _ in _ETAPES_FICHIER_SCAN}

    # ⚠ La sortie de la brique scan est un `.md` écrit DANS le dossier de langue de la source
    # (cf. `scan/pages.py`), pas sous `build/` : c'est ce qui permet à `run.py` de l'enchaîner
    # sans rien changer. La chercher sous `build/` la déclarerait absente à jamais.
    sorties: dict[str, Path] = {}
    if dossier_langue is not None:
        md = dossier_langue / f"{tome}.md"
        if md.is_file():
            sorties["md"] = md
    etapes["assemblage"] = FAITE if "md" in sorties else ABSENTE

    if total is None:
        statut, detail = serie.SANS_SOURCE, "aucune image dans un dossier de langue"
    elif "md" in sorties:
        statut, detail = serie.TERMINE, f"{total} page(s) · {tome}.md écrit"
    elif comptes["lecture"]:
        statut = serie.PARTIEL
        detail = f"{comptes['lecture']}/{total} page(s) lue(s)"
    else:
        statut, detail = serie.NON_TRAITE, f"{total} page(s) à lire"

    return {"etapes": etapes, "sorties": sorties, "dernier_run": dernier,
            "unites": total, "format": None,
            "langue_source": _code_langue(dossier_langue, config),
            "statut": statut, "detail": detail, "perimees": (), "verdict": None}


def _dossier_de_langue(vol_dir: Path, config: dict | None, *, texte: bool) -> Path | None:
    """Le dossier de langue le plus fourni, en ne comptant que ce qu'on cherche.

    « Le plus fourni gagne » est la règle de `sources_manga.resoudre_source` ; la reprendre
    ici évite qu'une bibliothèque nomme une langue que le run n'utilisera pas."""
    mapping = _dossiers_de_langue(config)
    cibles = _exts_texte() if texte else _exts_images()
    meilleur, compte_max = None, 0
    try:
        sous = sorted(p for p in vol_dir.iterdir() if p.is_dir())
    except OSError:
        return None
    for dossier in sous:
        if dossier.name.upper() not in mapping:
            continue
        n = sum(1 for nom in _noms(dossier) if Path(nom).suffix.lower() in cibles)
        if n > compte_max:
            meilleur, compte_max = dossier, n
    return meilleur


def _fichiers_du_dossier(dossier: Path | None, *, texte: bool) -> list[str]:
    if dossier is None:
        return []
    cibles = _exts_texte() if texte else _exts_images()
    return sorted(n for n in _noms(dossier) if Path(n).suffix.lower() in cibles)


def _code_langue(dossier: Path | None, config: dict | None) -> str | None:
    if dossier is None:
        return None
    return _dossiers_de_langue(config).get(dossier.name.upper())


# --------------------------------------------------------------------------- #
#  L'assemblage
# --------------------------------------------------------------------------- #

def tome_info(config: dict, projet: str, tome: str, *,
              glossaire: int | None = None) -> TomeInfo:
    """L'état d'un tome. **Aucune image n'est ouverte, aucun modèle n'est chargé.**"""
    briques = briques_du_tome(racine_sources(config) / projet / tome, config)
    principale = briques[0] if briques else MANGA

    if principale in (MANGA, WEBTOON):
        etat = _etat_manga(config, projet, tome, principale)
    elif principale == LN:
        etat = _etat_ln(config, projet, tome)
    else:
        etat = _etat_scan(config, projet, tome)

    # ⚠ Le verdict manga est disponible pour TOUS les tomes, y compris un roman — c'est celui
    # que `run_manga.py --list` imprime, et il vaut alors « aucune image ni archive ». Le
    # calculer ici plutôt que dans la CLI est ce qui fait qu'il n'y a qu'un seul inventaire.
    verdict = etat["verdict"]
    if verdict is None:
        from manga import serie
        verdict = serie.etat_chapitre(racine_sources(config), racine_build(config),
                                      projet, tome, config)

    return TomeInfo(
        projet=projet, tome=tome, brique=principale, briques=briques,
        format=etat["format"], langue_source=etat["langue_source"],
        unites=etat["unites"], unite=UNITES.get(principale, "unité"),
        etapes=etat["etapes"], sorties=etat["sorties"], glossaire=glossaire,
        dernier_run=etat["dernier_run"], statut=etat["statut"], detail=etat["detail"],
        perimees=etat["perimees"], verdict_manga=verdict)


def compter_glossaire(config: dict, projet: str) -> int | None:
    """Entrées du glossaire de l'ŒUVRE, ou `None` s'il n'y en a pas.

    ⚠ Lecture **en mémoire**, jamais `glossary.load` : celui-ci MIGRE et RÉÉCRIT le fichier
    qu'il ouvre. Compter des entrées pour les afficher ne doit pas modifier le travail
    terminologique de plusieurs tomes — c'est la règle que
    `glossary_import.lire_glossaire_yaml` porte déjà, écrite pour cette raison exacte."""
    import yaml

    chemin = chemin_glossaire(config, projet)
    if not chemin.is_file():
        return None
    try:
        with open(chemin, encoding="utf-8") as fh:
            brut = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(brut, dict):
        return None
    return sum(len(v) for v in brut.values() if isinstance(v, list))


def lister_projets(config: dict) -> list[str]:
    """Les dossiers de `sources/`, par ordre alphabétique — comme `--list` les imprime."""
    from pipeline.sources import list_projects
    return list_projects(racine_sources(config))


def lister_tomes(config: dict, projet: str) -> list[str]:
    """Les tomes d'une œuvre, dans l'ORDRE DE LECTURE.

    ⚠ `serie.lister_chapitres` et non `list_volumes` : `Chap.10` doit venir après `Chap.2`,
    et le tri alphabétique fait l'inverse. La raison n'est pas cosmétique — la passe
    terminologique enrichit le glossaire de l'œuvre au fil des tomes."""
    from manga import serie
    return serie.lister_chapitres(racine_sources(config), projet)


class Inventaire:
    """La façade **paresseuse** : rien n'est balayé tant qu'on ne demande rien.

    C'est ce qui permet à `run_manga.py --list` sans argument — qui n'affiche que le nombre de
    tomes par projet — de ne pas payer le balayage complet des 18 œuvres, tout en consommant
    exactement le même modèle que la vue. Un seul inventaire, deux affichages.

    Mémoïsé par `(projet, tome)` : l'interface repose la question à chaque changement de
    filtre, et le disque n'a pas à répondre deux fois.

    ⚠ Il n'y a **aucune invalidation automatique**, et c'est dit plutôt que caché : l'objet
    vit le temps d'un affichage, et `rafraichir()` en refait un état propre. Une clé
    d'invalidation par `mtime` — celle de `manga.etat_planches.CacheEtats` — est la bonne
    réponse quand le cache survit à un run ; ici il ne le fait pas, et la poser coûterait des
    `stat` pour rien.
    """

    def __init__(self, config: dict):
        self.config = config
        self._tomes: dict[tuple[str, str], TomeInfo] = {}
        self._glossaires: dict[str, int | None] = {}
        self._listes: dict[str, list[str]] = {}

    def rafraichir(self) -> None:
        self._tomes.clear()
        self._glossaires.clear()
        self._listes.clear()

    # ⚠ Le paramètre `_racine` ignoré n'est pas une négligence : `core.cli.afficher_liste`
    # appelle ses deux listeurs avec la racine des sources, et cette façade doit pouvoir s'y
    # brancher telle quelle. Le chemin fait foi est celui de la CONFIG, pas celui que
    # l'appelant repasse.
    def projets(self, _racine=None) -> list[str]:
        return lister_projets(self.config)

    def tomes(self, _racine=None, projet: str = "") -> list[str]:
        if projet not in self._listes:
            self._listes[projet] = lister_tomes(self.config, projet)
        return self._listes[projet]

    def glossaire(self, projet: str) -> int | None:
        if projet not in self._glossaires:
            self._glossaires[projet] = compter_glossaire(self.config, projet)
        return self._glossaires[projet]

    def tome(self, projet: str, tome: str) -> TomeInfo:
        cle = (projet, tome)
        if cle not in self._tomes:
            self._tomes[cle] = tome_info(self.config, projet, tome,
                                         glossaire=self.glossaire(projet))
        return self._tomes[cle]

    def oeuvre(self, projet: str) -> Oeuvre:
        return Oeuvre(projet=projet,
                      tomes=tuple(self.tome(projet, t)
                                  for t in self.tomes(None, projet)),
                      glossaire=self.glossaire(projet),
                      chemin_glossaire=chemin_glossaire(self.config, projet))

    #: Fils du balayage complet. Le travail est **entièrement bloqué sur le disque** — des
    #: `scandir` et des `stat`, pas une seule addition — donc le GIL n'est pas le facteur
    #: limitant et des fils suffisent, sans processus ni sérialisation.
    #:
    #: ⚠ Pourquoi 4 et pas « le nombre de cœurs ». Parce que ce qu'on parallélise n'est pas du
    #: calcul : au-delà d'une poignée de requêtes simultanées, un disque — et surtout un
    #: dossier synchronisé — cesse de rendre plus vite et se met à rendre moins bien. Le
    #: plateau est mesuré, et le repli au-delà aussi (médiane de trois balayages du corpus,
    #: `docs/mesures/bibliotheque-2026-09-05.md` §3.3) :
    #:
    #:     1 fil 1 436 ms · 2 fils 1 450 ms · **4 fils 1 250 ms** · 8 fils 1 394 ms · 16 fils 1 714 ms
    #:
    #: Le réglage reste ouvert par `paralleles=`, et `paralleles=1` rend le balayage
    #: séquentiel — c'est ce que font les tests, pour que l'ordre des appels système soit
    #: reproductible.
    FILS_PAR_DEFAUT = 4

    def oeuvres(self, *, paralleles: int | None = None) -> list[Oeuvre]:
        """**Le balayage complet.** C'est lui que l'étape 0.1 du `PLAN-34` chronomètre.

        ⚠ Il n'y a **aucun cache sur disque**, et c'est une décision, pas un oubli. La clé
        d'invalidation qu'il faudrait — le `mtime` des dossiers de build — est FAUSSE :
        réécrire `traduction_manuelle.json` dans `page_0042/` ne déplace pas le `mtime` de
        `.checkpoints/`. Un tel cache afficherait donc « à jour » sur un tome qu'on vient de
        corriger à la main, c'est-à-dire exactement le défaut que `manga/etat_planches.py`
        existe pour empêcher. À la place, le balayage est mené sur plusieurs fils (il est
        bloqué sur le disque, pas sur le processeur) et mémoïsé en mémoire pour la durée de
        l'affichage.

        `paralleles=1` rend le balayage séquentiel — c'est ce que font les tests, pour que
        l'ordre des appels système soit reproductible."""
        projets = self.projets()
        fils = self.FILS_PAR_DEFAUT if paralleles is None else max(1, int(paralleles))
        couples = [(p, t) for p in projets for t in self.tomes(None, p)
                   if (p, t) not in self._tomes]

        if fils > 1 and len(couples) > 1:
            from concurrent.futures import ThreadPoolExecutor

            # ⚠ Les imports paresseux d'abord, sur CE fil. `manga.serie` en fait trois selon
            # le chemin pris ; les déclencher depuis huit fils à la fois n'est pas incorrect
            # (l'import est verrouillé) mais sérialise le démarrage sur le verrou, ce qui
            # annule le gain sur les premiers tomes.
            from manga import serie as _serie  # noqa: F401
            from manga import sources_manga as _sources  # noqa: F401
            # ⚠ Et les glossaires, qui sont par ŒUVRE : les lire depuis les fils ferait lire
            # le même fichier par les quatre tomes d'une même œuvre, en parallèle, pour le
            # même résultat.
            for projet in projets:
                self.glossaire(projet)

            with ThreadPoolExecutor(max_workers=min(fils, len(couples))) as pool:
                calcules = list(pool.map(
                    lambda c: (c, tome_info(self.config, c[0], c[1],
                                            glossaire=self.glossaire(c[0]))),
                    couples))
            self._tomes.update(dict(calcules))

        return [self.oeuvre(p) for p in projets]


def puce(info: TomeInfo) -> str:
    """La puce de `manga/serie.py` pour le verdict MANGA d'un tome — celle de `--list`."""
    from manga import serie
    statut = getattr(info.verdict_manga, "statut", serie.NON_TRAITE)
    return serie.PUCES.get(statut, " ")


def detail_manga(info: TomeInfo) -> str:
    """Le détail que `run_manga.py --list` imprime à droite de la puce."""
    return str(getattr(info.verdict_manga, "detail", "") or "")
