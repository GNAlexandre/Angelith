# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Récupération des poids du modèle d'image — **12 Go ne se téléchargent pas comme 104 Mo**.

`manga/models.py` a le bon patron et il est repris tel quel pour ce qui vaut aux deux
échelles : le fichier `.part` renommé en dernier, le contrôle de taille, l'empreinte SHA-256
par blocs de 1 Mio. **Trois choses changent**, et chacune parce que le facteur cent le rend
nécessaire :

1. **`auto=False` par défaut.** Un téléchargement de 12 Go ne se déclenche pas parce qu'un
   utilisateur a lancé une commande : il se demande. `run_illustration.py --check` est
   l'endroit — c'est déjà la doctrine du dépôt pour les 104 Mo du détecteur (« quand tu
   prépares la machine plutôt qu'au milieu d'un tome »).
2. **Reprise sur coupure obligatoire.** Une requête `Range` repart de la taille du `.part`.
   Sur 12 Go, une coupure au bout de 11 Go coûterait sinon une soirée — et la recommencerait
   au premier incident suivant.
3. **Le poids ne va pas dans `manga_models/`** : c'est le dossier de la brique manga, et
   `.gitignore` y couvre `*.onnx`, pas `*.gguf` ni `*.safetensors`. Les motifs manquants ont
   été ajoutés au `.gitignore` **dans le même commit** que ce module, jamais après.

## Licences : rien n'est téléchargé par défaut, et rien n'est recommandé sans source primaire

⚠ Aucune URL de poids n'est codée en dur ici, à la différence de `manga/models.py`. Ce n'est
pas un oubli : le `PLAN-24` étape 0.4 exige que la licence des **poids** — pas celle du code —
soit vérifiée à la source primaire au moment de l'exécution, et l'étape n'a pas pu être menée
dans la session qui a écrit ce module (aucun accès réseau). Coder une URL aurait transformé
une vérification non faite en défaut du dépôt. `illustration_models/README.md` porte le
tableau des candidats, ce qui est établi et ce qui ne l'est pas ; l'utilisateur renseigne
`illustration.poids.fichier` et `illustration.poids.url` en connaissance de cause.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from illustration.marquage import empreinte_fichier

#: Taille de bloc de lecture réseau. 8 Mio et non 1 Mio : à 12 Go, le nombre d'itérations
#: compte, et le débit disque d'un SSD moderne absorbe ces blocs sans broncher.
BLOC = 8 << 20

#: Palier d'annonce d'avancement, en pourcents. 2 et non 10 : un téléchargement de 12 Go
#: muet pendant 20 minutes ressemble à un téléchargement planté.
PALIER = 2

_INSTRUCTIONS = (
    "  → renseigne illustration.poids.url et illustration.poids.fichier dans config.yaml,\n"
    "  → puis : python run_illustration.py --check --telecharger\n"
    "  → ou dépose le fichier à la main (voir illustration_models/README.md).")


class PoidsIntrouvable(RuntimeError):
    """Le fichier de poids manque, et rien n'autorise à le télécharger maintenant."""


def _humain(octets: float) -> str:
    return f"{octets / 1e9:.1f} Go" if octets >= 1e9 else f"{octets / 1e6:.0f} Mo"


def telecharger(url: str, destination, *, octets_attendus: int | None = None,
                sha256: str | None = None, dire=None, reprises: int = 3) -> Path:
    """Télécharge `url` vers `destination`, **en reprenant** un `.part` déjà commencé.

    Rend le chemin final. Lève `PoidsIntrouvable` sur échec réseau — et non un `SystemExit`
    comme `manga/models.py` : ce module est appelé depuis une brique opt-in, et faire mourir
    le processus depuis une bibliothèque interdit à l'appelant de proposer autre chose."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partiel = destination.with_name(destination.name + ".part")

    def _dire(msg: str) -> None:
        if callable(dire):
            dire(msg)

    total = octets_attendus or 0
    for tentative in range(1, max(1, reprises) + 1):
        deja = partiel.stat().st_size if partiel.exists() else 0
        if total and deja >= total:
            break
        try:
            deja, total = _un_passage(url, partiel, deja, total, _dire, tentative)
        except (urllib.error.URLError, OSError) as err:
            # ⚠ 416 « Range Not Satisfiable » n'est PAS une panne : c'est le serveur qui dit
            # « tu as déjà tout le fichier ». Le traiter comme une coupure faisait boucler la
            # reprise jusqu'à l'abandon, sur un fichier pourtant complet — constaté le
            # 2026-08-29 sur le VAE de Qwen-Image, dont `octets_attendus` était surestimé de
            # 166 octets. Le test attrape bien `HTTPError` ici : elle DÉRIVE de `URLError`,
            # et un 404 ou un 500 doit continuer d'être une panne.
            if getattr(err, "code", None) == 416:
                _dire("  (le serveur répond 416 : le fichier est déjà complet)")
                total = deja
                break
            if tentative >= reprises:
                raise PoidsIntrouvable(
                    f"Téléchargement du modèle impossible après {tentative} tentative(s) : "
                    f"{err}\n  url : {url}\n"
                    f"  Le fichier partiel est CONSERVÉ ({_humain(deja)}) : relancer "
                    f"reprendra où la coupure a eu lieu.\n{_INSTRUCTIONS}") from err
            _dire(f"  ⚠ coupure à {_humain(deja)} ({err}) — reprise…")

    taille = partiel.stat().st_size if partiel.exists() else 0
    if total and taille < total:
        raise PoidsIntrouvable(
            f"Téléchargement incomplet : {_humain(taille)} reçus pour {_humain(total)} "
            f"attendus. Le fichier partiel est conservé ; relancer reprendra.\n{_INSTRUCTIONS}")

    if sha256:
        _dire("Vérification de l'empreinte (SHA-256 sur le fichier entier)…")
        obtenu = empreinte_fichier(partiel)
        if obtenu != sha256:
            # ⚠ ERREUR, et non un simple avertissement comme dans `manga/models.py`. La
            # différence n'est pas un changement de doctrine, c'est une différence de coût :
            # un ONNX corrompu se voit à la première inférence, un GGUF de 12 Go tronqué ou
            # mal repris produit du BRUIT plausible — et coûterait une soirée de diagnostic.
            raise PoidsIntrouvable(
                f"Empreinte inattendue : {obtenu} au lieu de {sha256}.\n"
                f"  Le fichier n'est PAS installé. Soit la reprise a mal recollé, soit le "
                f"dépôt amont a republié ses poids. Supprime {partiel.name} et recommence, "
                f"ou mets à jour illustration.poids.sha256 après avoir vérifié à la source.")

    partiel.replace(destination)
    _dire(f"✓ Modèle prêt : {destination} ({_humain(taille)})")
    return destination


def _un_passage(url: str, partiel: Path, deja: int, total: int, dire, tentative: int):
    """Un aller réseau. `Range: bytes=<deja>-` reprend ; un serveur qui l'ignore repart de 0
    et on le dit, parce qu'un fichier concaténé deux fois serait pire que tout."""
    requete = urllib.request.Request(url, headers={"User-Agent": "Angelith"})
    if deja:
        requete.add_header("Range", f"bytes={deja}-")
        dire(f"Reprise à {_humain(deja)} (tentative {tentative})…")
    else:
        dire(f"Téléchargement du modèle → {partiel.stem}"
             + (f" ({_humain(total)})" if total else "") + " — une seule fois.")

    with urllib.request.urlopen(requete) as reponse:
        partielle = getattr(reponse, "status", 200) == 206
        if deja and not partielle:
            # Le serveur a ignoré `Range` : il renvoie le fichier ENTIER. Écrire à la suite
            # produirait un fichier de 24 Go dont l'empreinte ne dirait rien de lisible.
            dire("  ⚠ le serveur ignore les requêtes Range — reprise impossible, on repart "
                 "de zéro.")
            deja = 0
        # ⚠ `Content-Length` fait FOI, il ne complète pas une estimation. Le code écrivait
        # `total = total or (…)`, donc un `octets_attendus` approximatif n'était jamais
        # corrigé : surestimé de 166 octets sur le VAE de Qwen-Image, il faisait croire le
        # fichier incomplet une fois tout reçu, puis relancer une requête Range au-delà de la
        # fin — d'où un 416 en boucle sur un téléchargement réussi. La taille annoncée par le
        # serveur est la seule qui décrive le fichier qu'on est en train d'écrire.
        longueur = int(reponse.headers.get("Content-Length") or 0)
        if longueur:
            total = longueur + deja if partielle else longueur
        elif not total:
            total = 0
        mode = "ab" if deja else "wb"
        palier = (deja * 100 // total) if total else 0
        with open(partiel, mode) as sortie:
            while True:
                morceau = reponse.read(BLOC)
                if not morceau:
                    break
                sortie.write(morceau)
                deja += len(morceau)
                if total and deja * 100 // total >= palier + PALIER:
                    palier = deja * 100 // total
                    dire(f"  … {palier} % ({_humain(deja)} / {_humain(total)})")
    return deja, total


def assurer_poids(chemin, *, url: str = "", auto: bool = False, sha256: str | None = None,
                  octets_attendus: int | None = None, dire=None) -> Path:
    """Le chemin d'un fichier de poids présent — en le téléchargeant **seulement si on le
    demande**.

    ⚠ `auto` vaut **False** par défaut, à l'inverse de `manga/models.py:assurer_modele`. Ce
    n'est pas une incohérence entre les deux briques : c'est le facteur cent entre 104 Mo et
    12 Go. Le dépôt dit déjà, pour le détecteur, qu'un téléchargement se fait « quand tu
    prépares la machine plutôt qu'au milieu d'un tome » ; à 12 Go, cette phrase devient une
    règle plutôt qu'un conseil."""
    chemin = Path(chemin)
    if chemin.exists() and chemin.stat().st_size > 0:
        return chemin
    if not auto:
        raise PoidsIntrouvable(
            f"Poids du modèle d'image introuvables : {chemin}\n"
            f"  Ils ne sont PAS téléchargés automatiquement — le fichier pèse plusieurs "
            f"gigaoctets, et un run qui déclencherait ça tout seul serait un run qu'on ne "
            f"peut pas lancer le soir.\n{_INSTRUCTIONS}")
    if not url.strip():
        raise PoidsIntrouvable(
            "Téléchargement demandé, mais illustration.poids.url est vide.\n"
            "  Aucune URL n'est codée en dur dans le dépôt : la licence des POIDS se vérifie "
            "à la source primaire, et « licence du code Apache-2.0 » ne dit rien de la "
            "licence des poids (cf. illustration_models/README.md).")
    return telecharger(url, chemin, octets_attendus=octets_attendus, sha256=sha256, dire=dire)
