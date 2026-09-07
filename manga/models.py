# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Récupération automatique des poids de modèles CV.

Pourquoi ce module. `manga-ocr` télécharge son modèle tout seul au premier lancement ; le
détecteur de bulles, lui, exigeait un `Invoke-WebRequest` recopié à la main depuis
`manga_models/README.md`. Deux poids, deux traitements — et le jour où le `.onnx` disparaît du
disque (nettoyage du dépôt, machine neuve, dossier synchronisé qui évince un fichier de 104 Mo),
le pipeline s'arrête net sur un tome de 150 planches avec une consigne à exécuter à la main.

Aucune dépendance ajoutée : `urllib.request` de la bibliothèque standard suffit, comme `struct`
suffit à écrire un PSD.

## Ce qui garantit qu'un téléchargement interrompu ne pourrit pas le cache

L'écriture se fait dans un fichier `.part`, renommé **seulement** une fois la taille attendue
atteinte. Un Ctrl+C, une coupure réseau ou un disque plein laissent donc un `.part` que personne
ne lit — jamais un `.onnx` tronqué qu'ONNX Runtime refuserait ensuite avec un message obscur, à
chaque relance, sans que rien n'indique qu'il suffit de le supprimer.
"""
from __future__ import annotations

import hashlib
import shutil
import urllib.error
import urllib.request
from pathlib import Path

# Détecteur de bulles par défaut — le modèle testé et validé pour ce projet.
# Empreinte relevée le 2026-08-14 ; elle sert à VÉRIFIER un fichier fraîchement téléchargé, pas à
# l'imposer : un dépôt amont qui republie ses poids ne doit pas bloquer le pipeline, seulement
# faire dire que le fichier n'est plus celui d'origine.
DETECTEUR_URL = ("https://huggingface.co/kitsumed/yolov8m_seg-speech-bubble/"
                 "resolve/main/model_dynamic.onnx")
DETECTEUR_SHA256 = "36c26bdefe150226acd9669772e9ff5a011fa0dd4622469b49d3d5e359f3251c"
DETECTEUR_OCTETS = 108_982_949

# ⚠ **La licence du détecteur de BULLES ne mentionne PAS Manga109-s**, et c'est une correction
# de fait : jusqu'au 2026-09-06, `gui/sondes.py` et `manga/doctor.py` la lui attribuaient. Le
# corpus Manga109-s concerne le détecteur de TEXTE SUR LE DESSIN, plus bas dans ce fichier.
#
# Deux affirmations coexistent pour ce poids, et elles ne se contredisent pas — elles ne
# répondent pas à la même question. Les deux sont écrites plutôt qu'arbitrées :
#
#   · la page du modèle DÉCLARE GPL-3.0 (relevé le 2026-08-25, `manga_models/README.md`) ;
#   · ces poids sont un export **YOLOv8-seg**, et Ultralytics YOLOv8 est lui-même AGPL-3.0.
#
# Qui rediffuse des planches produites avec ce poids doit vérifier les deux. Ce n'est pas une
# précaution de style : la règle des chiffres du dépôt vaut aussi pour une licence — une
# affirmation sans sa source et sa date n'est pas une licence, c'est une impression.
DETECTEUR_LICENCE = "GPL-3.0 (déclarée sur la page du modèle, relevé le 2026-08-25)"
DETECTEUR_LICENCE_URL = "https://huggingface.co/kitsumed/yolov8m_seg-speech-bubble"
DETECTEUR_LICENCE_NOTE = (
    "⚠ Ces poids sont un export YOLOv8-seg, et Ultralytics YOLOv8 est lui-même AGPL-3.0 : "
    "vérifie les DEUX avant toute rediffusion des planches produites.")

# Détecteur de TEXTE SUR LE DESSIN (onomatopées, narration libre) — `comic-text-detector`
# de dmMaze, export ONNX. Empreinte relevée le 2026-08-16, même usage que ci-dessus :
# vérifier, pas imposer.
TEXTE_URL = ("https://huggingface.co/mayocream/comic-text-detector-onnx/"
             "resolve/main/comic-text-detector.onnx")
TEXTE_SHA256 = "1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f"
TEXTE_OCTETS = 94_669_756

#: ⚠ **C'est CE poids-ci qui porte Manga109-s**, et lui seul des deux détecteurs.
#:
#: ⚠ Manga109-s est dans la LICENCE et pas seulement dans la note, parce que c'est une
#: condition d'usage et non un commentaire : `tests/test_gui_diagnostic.py` vérifie que le mot
#: atteint l'utilisateur avant le clic, et il a raison de le vérifier là.
TEXTE_LICENCE = ("GPL-3.0 (code amont, relevé le 2026-08-16) — ⚠ poids entraînés pour partie "
                 "sur Manga109-s, qui a ses propres conditions d'usage académique")
TEXTE_LICENCE_URL = "https://huggingface.co/mayocream/comic-text-detector-onnx"
TEXTE_LICENCE_NOTE = (
    "⚠ À vérifier avant toute diffusion des planches produites : ces conditions ne sont pas "
    "celles d'Angelith.")

#: L'OCR japonais. Il se récupère tout seul au premier lancement, mais sa licence se dit ici
#: comme les autres — un poids dont personne ne nomme la licence est un poids qu'on ne peut pas
#: rediffuser en connaissance de cause.
OCR_LICENCE = "Apache-2.0"
OCR_LICENCE_URL = "https://huggingface.co/kha-white/manga-ocr-base"
OCR_LICENCE_NOTE = ""

_INSTRUCTIONS = (
    "  → relance avec le téléchargement automatique "
    "(config.yaml > manga.detection.telechargement_auto: true),\n"
    "  → ou télécharge le fichier à la main : voir manga_models/README.md.")


def empreinte(chemin: Path, bloc: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as fh:
        for morceau in iter(lambda: fh.read(bloc), b""):
            h.update(morceau)
    return h.hexdigest()


def _humain(octets: float) -> str:
    return f"{octets / 1e6:.0f} Mo"


def telecharger(url: str, destination: Path, *, octets_attendus: int | None = None,
                sha256: str | None = None, dire=None) -> Path:
    """Télécharge `url` vers `destination`, par un fichier temporaire renommé à la fin.

    `dire` reçoit les messages d'avancement (typiquement `reporter.info`) : un fichier de 104 Mo
    sur une ligne ADSL prend plusieurs minutes, et un pipeline muet pendant ce temps ressemble à
    un pipeline planté."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partiel = destination.with_suffix(destination.suffix + ".part")

    def _dire(msg: str) -> None:
        if callable(dire):
            dire(msg)

    _dire(f"Téléchargement du modèle → {destination.name}"
          + (f" ({_humain(octets_attendus)})" if octets_attendus else "")
          + " — une seule fois.")
    try:
        requete = urllib.request.Request(url, headers={"User-Agent": "Angelith"})
        with urllib.request.urlopen(requete) as reponse, open(partiel, "wb") as sortie:
            total = int(reponse.headers.get("Content-Length") or octets_attendus or 0)
            lus = 0
            palier = 0
            while True:
                morceau = reponse.read(1 << 20)
                if not morceau:
                    break
                sortie.write(morceau)
                lus += len(morceau)
                if total and lus * 100 // total >= palier + 10:
                    palier = lus * 100 // total
                    _dire(f"  … {palier} % ({_humain(lus)} / {_humain(total)})")
    except (urllib.error.URLError, OSError) as err:
        partiel.unlink(missing_ok=True)
        raise SystemExit(
            f"Téléchargement du modèle impossible : {err}\n"
            f"  url : {url}\n"
            f"  → vérifie ta connexion, ou télécharge le fichier à la main "
            f"(voir manga_models/README.md).") from err

    taille = partiel.stat().st_size
    # Un serveur qui répond une page d'erreur en 200, ou une coupure silencieuse, produisent un
    # fichier court : mieux vaut le dire ici qu'au moment où ONNX Runtime refusera de l'ouvrir.
    if octets_attendus and taille < octets_attendus * 0.9:
        partiel.unlink(missing_ok=True)
        raise SystemExit(
            f"Téléchargement incomplet : {_humain(taille)} reçus pour "
            f"{_humain(octets_attendus)} attendus.\n{_INSTRUCTIONS}")

    if sha256:
        obtenu = empreinte(partiel)
        if obtenu != sha256:
            # AVERTISSEMENT, pas une erreur : le dépôt amont a pu republier ses poids, et un
            # modèle différent reste un modèle utilisable. On le signale pour que l'auteur d'un
            # résultat inattendu sache que ce n'est plus le fichier de référence.
            _dire(f"⚠ Empreinte inattendue ({obtenu[:12]}… au lieu de {sha256[:12]}…) — "
                  f"le modèle amont a peut-être été republié. Fichier conservé.")

    # Renommage ATOMIQUE en dernier : tant qu'il échoue, le `.part` reste et rien ne prétend
    # être un modèle valide.
    shutil.move(str(partiel), str(destination))
    _dire(f"✓ Modèle prêt : {destination} ({_humain(taille)})")
    return destination


def assurer_modele(chemin: str | Path, *, url: str, auto: bool = True,
                   sha256: str | None = None, octets_attendus: int | None = None,
                   quoi: str = "de détection", dire=None) -> Path:
    """Renvoie le chemin d'un modèle ONNX, en le téléchargeant s'il manque.

    Généralisé à un modèle QUELCONQUE quand la détection du texte sur dessin a eu besoin
    d'un second poids : la garantie du `.part` renommé en dernier, le contrôle de taille et
    l'empreinte consultative valent pour l'un comme pour l'autre. `quoi` ne sert qu'au
    message d'erreur — c'est la seule chose qui différait vraiment.

    `auto=False` conserve le comportement historique : un message actionnable et l'arrêt."""
    chemin = Path(chemin)
    if chemin.exists() and chemin.stat().st_size > 0:
        return chemin
    if not auto:
        raise SystemExit(f"Modèle {quoi} introuvable : {chemin}\n{_INSTRUCTIONS}")
    return telecharger(url, chemin, octets_attendus=octets_attendus, sha256=sha256, dire=dire)


def assurer_detecteur(chemin: str | Path, *, url: str = DETECTEUR_URL, auto: bool = True,
                      sha256: str | None = DETECTEUR_SHA256,
                      octets_attendus: int | None = DETECTEUR_OCTETS, dire=None) -> Path:
    """Le détecteur de BULLES. Conservé comme point d'entrée nommé : c'est celui que
    `run_manga.py --check` et `BubbleDetector` appellent, et son message d'erreur est cité
    dans `manga_models/README.md`."""
    return assurer_modele(chemin, url=url, auto=auto, sha256=sha256,
                          octets_attendus=octets_attendus, quoi="de détection", dire=dire)
