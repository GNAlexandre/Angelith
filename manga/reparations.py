# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les gestes réparateurs de la brique manga — poids, OCR japonais, polices de lettrage.

## Pourquoi ils sont ici et pas dans `core/`

Parce que **`core` n'importe aucune brique**, et que c'est la ligne dont tout le reste du dépôt
dépend (`tests/test_imports_briques.py`). Récupérer le détecteur de bulles demande
`manga.models` ; le déclarer dans le socle y ferait entrer la connaissance d'une brique et
créerait un cycle `core → manga → core`.

C'est le même partage que pour les doctors, et il vient du même lot : le **vocabulaire** est
dans `core/reparations.py` (les trois classes, les refus, l'état d'un fichier), le **geste**
appartient à la brique qui le connaît. Importer ce module **enregistre** ses réparations dans
le catalogue commun ; ne pas l'importer les laisse inconnues, ce qui est exact — on ne répare
pas une brique qu'on n'a pas chargée.

## Les licences — lues, jamais recopiées

⚠ **Angelith ne redistribue aucun poids et n'héberge aucun miroir.** Chaque entrée porte sa
**source primaire** et sa licence, affichée avant le clic.

⚠ **MISE À JOUR 2026-09-06, lot 38 : les chaînes de licence ne sont plus écrites ici.** Elles
viennent de `manga/models.py`, qui est désormais la source unique — au même titre que les URL,
les tailles et les empreintes qu'il portait déjà. Motif : le dépôt disait **trois choses
différentes** sur le détecteur de bulles, dont une fausse (`gui/sondes.py` et `manga/doctor.py`
lui attribuaient Manga109-s, qui appartient au détecteur de **texte sur le dessin**). Une
licence répétée à dix endroits est une licence qui finit par diverger, et une licence fausse
affichée à l'utilisateur est pire qu'une licence absente.

⚠ La licence de **LaMa** n'est **pas établie au 2026-09-06** : il n'a aucune entrée ici.

## ⚠ L'installation des polices est le cas limite, et elle est `RECUPERABLE`

`tools/installer_polices.ps1` **enregistre** les polices de `templates/fonts/` pour
l'utilisateur courant : aucun droit administrateur, rien qui touche les autres comptes,
`-Desinstaller` remet tout en place. Enregistrer une police n'installe aucun logiciel — rien ne
s'exécute, rien ne devient un service, et le geste est réversible. Le bouton **appelle** ce
script, il ne le réécrit pas, et c'est le **seul** sous-processus que ce module lance.
"""
from __future__ import annotations

from pathlib import Path

from core import provenance
from core.reparations import RECUPERABLE, RefusDeReparer, Reparation, enregistrer, etat_fichier

from . import models


def _dire(dire, message: str) -> None:
    if callable(dire):
        dire(message)


def cible_connue(identifiant: str, config: dict) -> Path | None:
    """Le fichier qu'une réparation produit, **quand il en existe un que nous nommions**.

    Rend `None` pour `modele_ocr` (le cache est celui de `huggingface_hub`, dont nous ne
    sommes pas propriétaires) et pour `polices` (l'enregistrement est fait par Windows, pas
    par un fichier que nous poserions).

    ⚠ **Rendre `None` plutôt que de deviner un chemin** : la page « Poids et modèles » s'en sert
    pour dire « présent » ou « absent », et une réponse inventée y serait un état affiché que
    personne n'a mesuré."""
    if identifiant in ("poids_detection", "poids_texte"):
        return _cible_du_poids(identifiant, config)
    return None


def _cible_du_poids(identifiant: str, config: dict) -> Path:
    """Où le poids doit atterrir — **le chemin que la brique lira**, jamais un autre.

    `manga.detection.model_path` pour le détecteur de bulles, `manga.onomatopees.model_path`
    pour celui du texte sur dessin : ce sont les clés que `BubbleDetector.depuis_config` et
    `TextDetector.depuis_config` lisent, avec leurs défauts à la lettre. En inventer d'autres
    produirait un téléchargement qui réussit et un pipeline qui ne trouve toujours rien."""
    mcfg = (config.get("manga") or {})
    if identifiant == "poids_detection":
        valeur = (mcfg.get("detection") or {}).get("model_path")
        return Path(str(valeur)) if valeur else Path("manga_models") / "bubble_detector.onnx"
    valeur = (mcfg.get("onomatopees") or {}).get("model_path")
    return Path(str(valeur)) if valeur else Path("manga_models") / "text_detector.onnx"


def _recuperer_poids(identifiant: str, config: dict, *, dire=None) -> Path:
    """Télécharge un poids ONNX, puis **écrit sa fiche de provenance**.

    ⚠ Le téléchargement lui-même n'est pas réimplémenté : `manga/models.telecharger` porte
    déjà la garantie qui compte — écriture dans un `.part`, renommage atomique en dernier,
    contrôle de taille, empreinte consultative. La refaire ici, c'est la refaire à moitié.

    Ce que le lot 36 ajoute est la ligne d'après : la fiche. Sans elle, un poids sur le disque
    n'a ni licence ni date, et la page « À propos » ne peut rien en dire d'exact."""
    from core.reparations import par_identifiant

    reparation = par_identifiant(identifiant)
    cible = _cible_du_poids(identifiant, config)
    etat = etat_fichier(cible, reparation.octets)
    if etat.reste_un_part:
        _dire(dire, "Un téléchargement précédent a laissé un fichier .part — il est repris "
                    "de zéro, proprement.")
    if etat.partiel:
        _dire(dire, f"Fichier incomplet écarté : {etat.motif}.")
        cible.unlink()
    _dire(dire, f"Licence de ce poids : {reparation.licence}")
    chemin = models.telecharger(reparation.url, cible, octets_attendus=reparation.octets,
                                sha256=reparation.sha256 or None, dire=dire)
    fiche = provenance.ecrire(chemin, url=reparation.url, licence=reparation.licence,
                              licence_url=reparation.licence_url, note=reparation.note)
    _dire(dire, f"Provenance enregistrée : {provenance.chemin_fiche(chemin).name} "
                f"(sha256 {fiche.sha256[:12]}…)")
    return chemin


def _geste_detecteur(config: dict, *, dire=None, **_) -> Path:
    return _recuperer_poids("poids_detection", config, dire=dire)


def _geste_texte(config: dict, *, dire=None, **_) -> Path:
    return _recuperer_poids("poids_texte", config, dire=dire)


def _geste_ocr(config: dict, *, dire=None, **_) -> Path:
    """Récupère `manga-ocr` **avant** le run, et pas au milieu.

    ⚠ C'est tout l'objet de ce geste, et il a un chiffre. Mesuré le 2026-09-06 : sans cache et
    sans réseau, la construction de `MangaOCR` lève un `OSError` de `transformers` — un message
    qui ne dit ni la cause ni le geste — et comme le lecteur est construit paresseusement à
    l'intérieur du filet par planche, **l'échec se répète pour chaque planche** du tome. Un run
    de nuit de 150 planches produit 150 fois le même message obscur et aucune sortie.

    Le modèle est confié à `huggingface_hub`, qui le range dans son cache habituel : Angelith
    ne déplace aucun fichier et n'invente aucun emplacement."""
    from huggingface_hub import snapshot_download

    from .ocr import MODELE_OCR

    _dire(dire, f"Licence de ce modèle : {models.OCR_LICENCE} — {MODELE_OCR}")
    _dire(dire, "Téléchargement du modèle d'OCR japonais (~424 Mo) — une seule fois.")
    dossier = Path(snapshot_download(MODELE_OCR))
    _dire(dire, f"✓ Modèle d'OCR prêt : {dossier}")
    # ⚠ Pas de fiche de provenance ici : le cache Hugging Face est géré par `huggingface_hub`,
    # qui y tient son propre registre de révisions. Y écrire un fichier à nous corromprait un
    # dossier dont nous ne sommes pas propriétaires. La licence, elle, est dans le catalogue
    # ci-dessous, et la page « À propos » la lit là.
    return dossier


def _geste_polices(config: dict, *, dire=None, racine: Path | None = None, **_) -> None:
    """Appelle `tools/installer_polices.ps1` — **il l'appelle, il ne le réécrit pas**.

    Hors Windows, le script n'a pas d'équivalent et le geste se REFUSE en le disant, plutôt que
    d'inventer un chemin qu'aucune mesure ne couvre."""
    import subprocess
    import sys

    if sys.platform != "win32":
        raise RefusDeReparer(
            "L'enregistrement des polices n'est écrit que pour Windows "
            "(tools/installer_polices.ps1). Sur ce système, installe les fichiers de "
            "templates/fonts/ par les outils de ton bureau — ils sont sous SIL OFL 1.1.")
    from core.installation import racine_livree
    racine = Path(racine) if racine else racine_livree()
    script = racine / "tools" / "installer_polices.ps1"
    if not script.is_file():
        raise RefusDeReparer(f"script introuvable : {script}")
    _dire(dire, f"Appel de {script.name} — polices sous SIL OFL 1.1, utilisateur courant "
                f"seulement, réversible par -Desinstaller.")
    resultat = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ligne in (resultat.stdout or "").splitlines():
        _dire(dire, ligne)
    if resultat.returncode != 0:
        raise RefusDeReparer(
            f"L'enregistrement des polices a échoué (code {resultat.returncode}).\n"
            f"{(resultat.stderr or '').strip()}")
    return None


# --------------------------------------------------------------------------- #
#  La table
# --------------------------------------------------------------------------- #
#
# ⚠ Les URL, tailles et empreintes ne sont PAS recopiées : elles viennent de `manga/models.py`,
# qui est le module que le pipeline utilise réellement. Deux tables seraient deux vérités —
# c'est la faute que `gui/destinations.py` évite en n'écrivant jamais une séquence de raccourci.

CATALOGUE: tuple[Reparation, ...] = (
    Reparation(
        "poids_detection", "Télécharger les poids de détection de bulles", RECUPERABLE,
        quoi="Récupérer le poids ONNX qui détecte les bulles, sans lequel aucune planche ne "
             "peut être traitée.",
        brique="manga",
        licence=models.DETECTEUR_LICENCE,
        licence_url=models.DETECTEUR_LICENCE_URL,
        url=models.DETECTEUR_URL, octets=models.DETECTEUR_OCTETS,
        sha256=models.DETECTEUR_SHA256,
        note=models.DETECTEUR_LICENCE_NOTE + " Empreinte de référence relevée le 2026-08-14. "
             "Une empreinte différente n'est pas un échec : le dépôt amont a pu republier ses "
             "poids. Elle est signalée, et le fichier est conservé.",
        geste=_geste_detecteur),
    Reparation(
        "poids_texte", "Télécharger les poids de détection du texte sur le dessin",
        RECUPERABLE,
        quoi="Récupérer le poids qui repère les onomatopées et la narration libre (mode "
             "« rapport » par défaut : on détecte et on rapporte, on ne dessine pas).",
        brique="manga",
        licence=models.TEXTE_LICENCE,
        licence_url=models.TEXTE_LICENCE_URL,
        url=models.TEXTE_URL, octets=models.TEXTE_OCTETS, sha256=models.TEXTE_SHA256,
        note=models.TEXTE_LICENCE_NOTE + " ⚠ Ce poids n'est PAS redistribuable : il se "
             "récupère chez son éditeur, jamais depuis un miroir du projet.",
        geste=_geste_texte),
    Reparation(
        "modele_ocr", "Télécharger le modèle d'OCR japonais (manga-ocr)", RECUPERABLE,
        quoi="Récupérer le modèle `manga-ocr` MAINTENANT plutôt qu'au milieu d'un run. "
             "⚠ Sans lui et sans réseau, un run de nuit échoue planche après planche — "
             "mesuré le 2026-09-06, cf. docs/mesures/premier-lancement-2026-09-06.md.",
        brique="manga",
        licence=models.OCR_LICENCE,
        licence_url=models.OCR_LICENCE_URL,
        url="https://huggingface.co/kha-white/manga-ocr-base",
        octets=424_000_000,
        note="Le téléchargement passe par `huggingface_hub`, qui range le modèle dans son "
             "cache habituel — Angelith n'en déplace aucun fichier.",
        geste=_geste_ocr),
    Reparation(
        "polices", "Installer les polices de lettrage du dépôt", RECUPERABLE,
        quoi="Enregistrer les polices de `templates/fonts/` **pour l'utilisateur courant**, "
             "ce qui les rend visibles de Photoshop pour les calques de type.",
        brique="manga",
        licence="SIL OFL 1.1 (Comic Neue — templates/fonts/OFL.txt)",
        licence_url="https://scripts.sil.org/OFL",
        commande="powershell -ExecutionPolicy Bypass -File tools/installer_polices.ps1",
        note="⚠ Aucun droit administrateur, aucun autre compte touché, et `-Desinstaller` "
             "remet tout en place. Enregistrer une police n'est pas installer un logiciel : "
             "rien ne s'exécute et rien ne devient un service.",
        geste=_geste_polices),
)

enregistrer(*CATALOGUE)
