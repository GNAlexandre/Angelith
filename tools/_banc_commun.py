# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Socle commun des instruments de mesure : lire un cache de tome, énumérer les volumes,
sortir un tableau.

## Pourquoi ce module existe

Quatre outils lisaient déjà `build/<Œuvre>/<Chapitre>/manga/.checkpoints/` — `mesurer_bulles`,
`apercu_detection`, `compter_variantes`, `verifier_ordre` — et chacun avait sa propre copie du
calcul du dossier, de l'énumération des planches et de la lecture des JSON. Elles avaient déjà
divergé sur un point qui compte : `compter_variantes._lire_tome` retombe sur
`traduction.json` quand `qa.json` manque, `mesurer_bulles` ignore la planche, et
`report_manga` la compte absente. Trois réponses à la même question.

C'est la leçon que `detection.depuis_config` a tirée pour la construction du détecteur : un
seul point, ou les copies divergent en silence. Ajouter `tools/banc.py` sans ce module aurait
fait une **cinquième** lecture de cache.

## La discipline, héritée de `tools/mesurer_bulles.py`

Tout ce qui est ici lit **uniquement le cache**. Aucun modèle n'est chargé, rien n'est
réécrit, et un run peut tourner pendant la mesure. C'est ce qui rend le banc jouable sur les
dix volumes de `build/` en quelques secondes.

⚠ **Les masques ne sont pas lus par défaut.** `checkpoints._lire_regions_brut` décode
`masks.png` et matérialise un tableau booléen pleine page **par bulle** — de l'ordre de 60 Mo
pour une planche à dix bulles en 2000×3000. Le banc n'en a pas besoin : `qa.json` persiste
déjà `remplissage_masque`. `lire_meta_regions` s'arrête donc au JSON ; `charger_regions` reste
disponible pour ce qui mesure vraiment de la géométrie.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Où sont les volumes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Volume:
    """Un tome mesurable : son œuvre, son chapitre, et le dossier qui porte son cache."""

    projet: str
    tome: str
    build_dir: Path

    @property
    def nom(self) -> str:
        return f"{self.projet} / {self.tome}"


def racine_build(config: dict) -> Path:
    """`build/`, tel que la brique manga le voit (héritage par fusion profonde)."""
    from core import config as core_config
    return Path(core_config.section(config, "manga", "chemins")["build"])


def racine_sources(config: dict) -> Path:
    """`sources/`, même héritage. Le banc ne s'en sert pas ; les outils qui ouvrent une
    planche d'origine, si."""
    from core import config as core_config
    return Path(core_config.section(config, "manga", "chemins")["sources"])


def build_dir_de(build_root: Path | str, projet: str, tome: str) -> Path:
    """`build/<Œuvre>/<Chapitre>/manga`. Délègue à `manga.serie`, qui fait déjà foi pour le
    pré-vol et pour `run_manga.py` : un quatrième calcul viserait tôt ou tard un autre
    dossier."""
    from manga import serie
    return serie.build_dir_de(build_root, projet, tome)


def enumerer_volumes(build_root: Path | str) -> list[Volume]:
    """Tous les volumes **présents dans `build/`**, dans l'ordre de lecture.

    ⚠ Énumère `build/`, et non `sources/` comme le fait `serie.lister_chapitres`. C'est
    délibéré : le corpus commercial a été purgé du dépôt (`86c3d3d`, `b3d1eaa`) et ne revient
    pas, mais les caches de mesure, eux, sont là. Un banc qui exigerait les sources ne
    mesurerait rien sur la machine où il compte le plus."""
    from manga.ingest import natural_key
    build_root = Path(build_root)
    if not build_root.is_dir():
        return []
    volumes: list[Volume] = []
    for projet in sorted((p for p in build_root.iterdir() if p.is_dir()),
                         key=lambda p: natural_key(p.name)):
        for tome in sorted((t for t in projet.iterdir() if t.is_dir()),
                           key=lambda t: natural_key(t.name)):
            build_dir = tome / "manga"
            if (build_dir / ".checkpoints").is_dir():
                volumes.append(Volume(projet.name, tome.name, build_dir))
    return volumes


def numeros_de_planches(build_dir: Path | str) -> list[int]:
    """Numéros des planches en cache, triés. Vide si le tome n'a jamais tourné.

    Le tri est NUMÉRIQUE : `sorted(glob("page_*"))` ne range `page_0100` après `page_0011`
    que parce que le nom est zéro-padé — un cache écrit autrement rendrait un ordre faux, et
    c'est l'ordre qui décide du numéro affiché à côté de chaque anomalie."""
    racine = Path(build_dir) / ".checkpoints"
    if not racine.is_dir():
        return []
    numeros = []
    for d in racine.iterdir():
        suffixe = d.name.removeprefix("page_")
        if d.is_dir() and d.name.startswith("page_") and suffixe.isdigit():
            numeros.append(int(suffixe))
    return sorted(numeros)


# ---------------------------------------------------------------------------
# Lire une planche
# ---------------------------------------------------------------------------

def charger_json(chemin: Path):
    """Contenu d'un JSON du cache, ou `None`. **Ne lève jamais.**

    Un `qa.json` corrompu ne doit pas faire échouer un banc de dix volumes — c'est déjà la
    règle de `report_manga.load_page_qa`, pour la même raison."""
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


@dataclass
class Planche:
    """Ce qu'une planche a laissé dans le cache.

    ⚠ `None` et `[]` ne veulent pas dire la même chose, et toute la mesure en dépend : une
    planche **sans** `qa.json` est une anomalie (`qa is None`) — ses bulles échappent au
    contrôle qualité —, une planche **sans bulle** est un fait (`regions == []`)."""

    numero: int
    ckpt: Path
    regions: list[dict] = field(default_factory=list)
    image_size: tuple[int, int] | None = None
    sens: str | None = None
    detection: dict | None = None
    format_cache: int | None = None
    qa: dict | None = None
    ocr: list[str] | None = None
    traduction: list[str] | None = None
    sfx: list[dict] | None = None

    @property
    def a_des_regions(self) -> bool:
        """`regions.json` est-il lisible ? Une planche jamais détectée n'est pas une planche
        à zéro bulle."""
        return self.format_cache is not None

    @property
    def bulles(self) -> list[dict]:
        """Régions de genre `bulle` — le dénominateur du rapport. `kind` peut valoir autre
        chose sur un cache écrit par le lot 9."""
        return [r for r in self.regions if (r.get("kind") or "bulle") == "bulle"]

    @property
    def qa_bulles(self) -> list[dict]:
        return [b for b in ((self.qa or {}).get("bulles") or [])
                if (b.get("kind") or "bulle") == "bulle"]


def lire_meta_regions(ckpt_dir: Path) -> dict | None:
    """`regions.json` normalisé, **sans toucher à `masks.png`**, ou `None`.

    Tolère le format v1 (liste nue, sans `image_size`) comme le fait
    `checkpoints._lire_regions_brut` : on veut pouvoir mesurer un tome AVANT sa migration
    aussi bien qu'après."""
    data = charger_json(Path(ckpt_dir) / "regions.json")
    if data is None:
        return None
    if isinstance(data, list):
        return {"format": 1, "image_size": None, "regions": data,
                "sens": None, "detection": None}
    taille = data.get("image_size")
    return {
        "format": int(data.get("format", 0)),
        "image_size": tuple(taille) if taille else None,
        "regions": data.get("regions") or [],
        "sens": data.get("sens"),
        "detection": data.get("detection"),
    }


def lire_planche(ckpt_dir: Path, numero: int) -> Planche:
    """Tout le cache d'UNE planche, en une passe et sans masque."""
    ckpt_dir = Path(ckpt_dir)
    planche = Planche(numero=numero, ckpt=ckpt_dir)
    meta = lire_meta_regions(ckpt_dir)
    if meta is not None:
        planche.regions = meta["regions"]
        planche.image_size = meta.get("image_size")
        planche.sens = meta.get("sens")
        planche.detection = meta.get("detection")
        planche.format_cache = meta.get("format")
    planche.qa = charger_json(ckpt_dir / "qa.json")
    planche.ocr = charger_json(ckpt_dir / "ocr.json")
    planche.traduction = charger_json(ckpt_dir / "traduction.json")
    sfx = charger_json(ckpt_dir / "sfx.json")
    if isinstance(sfx, dict):
        planche.sfx = sfx.get("zones") or sfx.get("regions") or []
    elif isinstance(sfx, list):
        planche.sfx = sfx
    return planche


def planches(volume: Volume | Path | str):
    """Itère les planches d'un volume, dans l'ordre. Une planche par tour, jamais toutes en
    mémoire : dix volumes de 150 planches passent ainsi sans pic."""
    from manga import checkpoints
    build_dir = volume.build_dir if isinstance(volume, Volume) else Path(volume)
    for numero in numeros_de_planches(build_dir):
        yield lire_planche(checkpoints.page_checkpoint_dir(build_dir, numero), numero)


def charger_regions(ckpt_dir: Path):
    """Régions AVEC leurs masques — la lecture chère, pour ce qui mesure de la géométrie.

    Passe par `checkpoints._lire_regions_brut` plutôt que `load_regions` : celle-ci rend
    `None` sur écart de version de format, ce qui est le bon comportement pour le pipeline
    (recalculer) et le mauvais pour un instrument de mesure (on veut mesurer le tome tel
    qu'il est, y compris avant migration)."""
    from manga import checkpoints
    lu = checkpoints._lire_regions_brut(Path(ckpt_dir))
    return [] if lu is None else lu[0]


# ---------------------------------------------------------------------------
# Test d'encre — une planche à zéro bulle est-elle blanche, ou pleine de dessin ?
# ---------------------------------------------------------------------------

# ⚠ Le CALCUL vit dans `manga/detection.py` depuis le lot 12 (L4.8), et le banc s'y adosse
# plutôt que d'en garder une copie. La raison est celle qui a fait ce module : un rapport qui
# trie ses planches autrement que le pipeline ne mesure pas le pipeline. Le même
# `porte_de_l_encre` arme désormais l'escalade de détection et remplit la colonne
# « dont encrées ».
#
# Ce que la version de `manga` ajoute à celle qui vivait ici : le **sous-échantillonnage** (le
# test doit coûter des millisecondes, puisqu'il est désormais posé sur chaque planche d'un run)
# et la tolérance mesurée sur l'image réduite.
#
# ⚠ Les seuils ne sont PAS recopiés ici, même « pour la lisibilité » : deux constantes valant
# la même chose à deux endroits sont deux constantes qui divergeront. Et pas non plus liées au
# chargement du module — comme tous les imports `manga` d'ici, la résolution est locale, pour
# que `tools/banc.py --help` reste lançable sans les extras manga installés.


def seuil_encre() -> float:
    """Seuil d'encre du pipeline, `manga.detection.SEUIL_ENCRE`."""
    from manga import detection
    return detection.SEUIL_ENCRE


def part_encre(image, tolerance: int | None = None) -> float:
    """Fraction des pixels qui s'écartent du fond de la planche — cf.
    `manga.detection.part_encre`, qui fait foi.

    Le fond est la luminance **médiane** et non le blanc : une planche en niveaux de gris
    sombres, une planche inversée (blanc sur noir) et un webtoon couleur ont trois fonds
    différents, et mesurer « ce qui n'est pas blanc » les déclarerait tous les trois couverts
    d'encre.

    ⚠ Ce test dit « cette planche porte quelque chose », pas « cette planche porte du
    TEXTE ». Séparer le texte du dessin demanderait le détecteur de texte, donc 94,7 Mo de
    poids et une passe ONNX par planche ; le banc publie ce qu'il mesure vraiment et le nomme
    ainsi."""
    from manga import detection
    return detection.part_encre(
        image, tolerance=detection.TOLERANCE_FOND if tolerance is None else tolerance)


def porte_de_l_encre(build_dir: Path, planche: Planche,
                     seuil: float | None = None,
                     source_planche: Path | None = None) -> tuple[bool | None, str]:
    """La planche porte-t-elle autre chose que du fond ? Renvoie `(réponse, source)`.

    Quatre sources, dans cet ordre — et l'ordre est le sujet :

    1. **`pages_out/page_XXXX.png`**, la planche rendue. Sur une planche à ZÉRO bulle, rien
       n'a été nettoyé ni lettré : le rendu est la planche d'origine au pixel près. C'est donc
       une mesure indépendante du contrôle qualité, et elle vit dans `build/` — le banc reste
       cache-seul.
    2. `pages_clean/page_XXXX.png`, même raisonnement, pour un tome arrêté avant le rendu.
    3. **La planche d'origine sous `sources/`**, quand `source_planche` est fournie. C'est la
       seule entorse à « cache-seul », et elle est en LECTURE : sans elle, les 43 planches à
       zéro bulle des deux premiers volumes de *manga D* — qui n'ont ni `pages_out/`,
       ni `pages_clean/`, ni `qa.json` — restent définitivement non mesurables, et le critère
       de L4.8 (« chacune des 188 planches est classée ») est hors d'atteinte. Une case
       « non mesurée » dans une colonne de nombres se lit comme un zéro.
    4. **`qa["sfx"]`** en tout dernier recours seulement.

    ⚠ Pourquoi `qa["sfx"]` ne peut pas être le test principal — c'est mesuré, pas supposé.
    C'est ce que fait `report_manga.py` (`sans_bulle_avec_texte`), et c'est juste pour ce que
    le rapport annonce ; mais la passe onomatopées est optionnelle
    (`config.yaml > manga.onomatopees.actif`). Sur un tome traité sans elle, `qa["sfx"]` est
    vide sur TOUTES les planches, et les planches à zéro bulle ne sont alors pas triées du
    tout : une page de garde et une pleine page d'action y comptent pareil."""
    from manga import checkpoints, detection
    seuil = detection.SEUIL_ENCRE if seuil is None else float(seuil)
    # (chemin, nom publié dans la colonne « source encre »). Le nom est explicite et non
    # `chemin.parent.name` : le dossier d'une planche d'origine s'appelle `manga`, ce qui se
    # lirait comme un régime de planche dans une colonne qui en porte déjà un.
    candidates = [(checkpoints.final_page_path(build_dir, planche.numero), "pages_out"),
                  (checkpoints.clean_page_path(build_dir, planche.numero), "pages_clean")]
    if source_planche is not None:
        candidates.append((Path(source_planche), "sources"))
    for chemin, nom in candidates:
        if chemin.exists():
            try:
                return detection.porte_de_l_encre(chemin, seuil=seuil), nom
            except OSError:
                continue
    if planche.qa is not None:
        return bool(planche.qa.get("sfx")), "qa[sfx]"
    return None, "aucune"


def planches_sources(volume, config: dict | None) -> dict[int, Path]:
    """Chemins des planches d'ORIGINE d'un tome, par numéro — `{}` si `sources/` est absent.

    Passe par `sources_manga.scan_volume`, le même résolveur que l'orchestrateur : lire
    `pages_src/` directement ne marcherait pas (ce dossier n'est peuplé que lorsque la source
    est une archive) et deviner le tri redonnerait un cinquième énumérateur de planches.

    Tolérant de bout en bout : le corpus commercial n'est pas dans le dépôt, et un banc qui
    lèverait faute de `sources/` ne mesurerait rien sur la machine où il compte le plus."""
    if config is None:
        return {}
    try:
        from manga import sources_manga
        vol_dir = racine_sources(config) / volume.projet / volume.tome
        if not vol_dir.is_dir():
            return {}
        pages = sources_manga.scan_volume(vol_dir, volume.build_dir, config).pages
    except Exception:
        return {}
    return {i: Path(p) for i, p in enumerate(pages, start=1)}


# ---------------------------------------------------------------------------
# Sortie : Markdown, JSON, et l'en-tête qui rend un tableau citable
# ---------------------------------------------------------------------------

def cellule(valeur) -> str:
    """Une valeur telle qu'elle s'imprime. `None` rend `—` et jamais une case vide : dans une
    colonne de nombres, un vide se lit comme un zéro."""
    if valeur is None:
        return "—"
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if isinstance(valeur, float):
        return f"{valeur:.2f}".rstrip("0").rstrip(".")
    if isinstance(valeur, (list, tuple, set)):
        return ", ".join(str(v) for v in valeur) or "—"
    if isinstance(valeur, dict):
        return " · ".join(f"{k} {v}" for k, v in sorted(valeur.items())) or "—"
    return str(valeur)


def tableau_markdown(colonnes: list[str], lignes: list[dict]) -> str:
    """Un tableau Markdown à colonnes fixes. `colonnes` donne l'ordre ET le dénominateur :
    une colonne absente d'une ligne rend `—`."""
    entete = "| " + " | ".join(colonnes) + " |"
    separateur = "|" + "|".join("---" for _ in colonnes) + "|"
    corps = ["| " + " | ".join(cellule(ligne.get(c)) for c in colonnes) + " |"
             for ligne in lignes]
    return "\n".join([entete, separateur, *corps])


def commit_courant() -> str:
    """Le commit HEAD, ou `"(hors dépôt git)"`. Un tableau publié sans son commit n'est pas
    comparable au suivant : c'est la moitié de ce que « daté » veut dire."""
    try:
        sortie = subprocess.run(["git", "-C", str(RACINE), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "(hors dépôt git)"
    return sortie.stdout.strip() or "(hors dépôt git)"


def empreinte_config(chemin: Path | str) -> str:
    """SHA-256 tronqué de `config.yaml`. Deux runs du même commit avec deux configurations
    différentes ne mesurent pas la même chose ; le tableau doit pouvoir le dire."""
    import hashlib
    chemin = Path(chemin)
    if not chemin.is_file():
        # ⚠ `is_file()` et non `exists()` : un DOSSIER passait la garde, et le `read_bytes()`
        # qui suit levait un `IsADirectoryError` (Linux) ou un `PermissionError` (Windows) au
        # milieu d'un banc de plusieurs minutes. « (absente) » est la bonne réponse dans les
        # deux cas — le tableau doit dire qu'il n'a pas pu empreindre la configuration.
        return "(absente)"
    return hashlib.sha256(chemin.read_bytes()).hexdigest()[:12]


def entete_publication(config_path: Path | str, volumes: list[Volume],
                       *, titre: str = "Banc de mesure", commande: str = "") -> list[str]:
    """Les lignes qui font d'un tableau une PUBLICATION : la date, le commit, la
    configuration, et la liste des volumes mesurés.

    Sans elles, deux tableaux ne se comparent pas — on ne sait pas si l'écart vient du code,
    de la configuration ou du corpus. C'est exactement ce que le lot 10 reproche aux chiffres
    qui circulaient jusqu'ici : réels, et sans dénominateur écrit."""
    from core.version import __version__
    commande = commande or "python tools/banc.py --tous --markdown"
    return [
        f"# {titre}",
        "",
        f"- **Date de mesure** : {date.today().isoformat()}",
        f"- **Commit** : `{commit_courant()}`",
        f"- **Version du dépôt** : {__version__}",
        f"- **`config.yaml`** : sha256 `{empreinte_config(config_path)}`",
        f"- **Volumes mesurés** : {len(volumes)}"
        + (" — " + " · ".join(v.nom for v in volumes) if volumes else ""),
        "",
        f"> Produit par `{commande}`, en lisant **uniquement** les caches sous `build/`.",
        "> Aucun modèle n'est chargé, rien n'est réécrit.",
        "",
    ]
