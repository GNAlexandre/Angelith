# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le marquage des images générées — **et il n'a pas d'interrupteur**.

## L'obligation, sa date, et sa lecture

**AI Act, article 50(2)**, vérifié le 2026-08-27 sur
[artificialintelligenceact.eu](https://artificialintelligenceact.eu/transparency-rules-article-50/) :
le fournisseur d'un système d'IA qui génère des images de synthèse doit s'assurer que les
sorties sont **marquées dans un format lisible par machine** et **détectables comme générées
par IA**. Applicable depuis le **2026-08-02** ; les systèmes déjà sur le marché avant cette
date ont jusqu'au **2026-12-02**.

⚠ **Ce n'est pas un avis juridique.** La lecture retenue est écrite, datée et sourcée dans
`docs/ai-provenance.md`, et elle y est signalée comme **restant à confirmer**. Ce qui est
tranché, en revanche, c'est la conséquence pour le code : Angelith devient, en livrant cette
brique, « fournisseur d'un système générant des images de synthèse », y compris si un seul
utilisateur s'en sert. Le marquage n'est donc **pas une option de configuration** — il n'y a
aucune clé pour l'éteindre, et `ecrire` est le seul chemin du dépôt qui sache écrire un PNG
d'illustration.

## Ce que porte une image, et ce qu'elle ne porte pas

Dans le fichier, un bloc `tEXt` : `Software`, `Generator`, `AIGenerated`, `Seed`, `Prompt`
(tronqué), `SourceWork`. À côté, un manifeste `<image>.provenance.json` complet : modèle,
empreinte des poids, graine, prompt entier, prompt négatif, chemins des références, empreinte
de `config.yaml`, version d'Angelith, date, **le payload JSON exact envoyé au moteur**, la
validation humaine (qui, quand, prompt avant et après correction) et la phrase de non-œuvre.

⚠ **Le nom de l'œuvre ne va NI dans le PNG NI dans le sidecar.** Un identifiant local suffit —
`identifiant_oeuvre` en dérive un digest stable. Le `.gitignore` du dépôt refuse déjà d'exposer
les titres comme noms de dossier (« le dépôt devient public, et l'arbre git exposait alors le
NOM de chaque œuvre ») ; une image qui les porterait dans ses métadonnées les exposerait le
jour où elle est partagée par erreur. `_sans_titre` fait respecter la règle à l'écriture, et
lève plutôt que de laisser passer.

## C2PA : non fait, et c'est dit

Aucune signature C2PA n'est écrite. La question posée par le `PLAN-24` était « si et seulement
si une bibliothèque acceptable existe sans traîner un SDK entier » : la réponse mesurée est non
— `c2pa-python` embarque le SDK Rust `c2pa` et un manifeste signé demande une **autorité de
certification**, donc une identité publiée, alors que rien de cette brique ne sort de la
machine. Un `tEXt` plus un sidecar est un marquage lisible par machine : c'est un plancher
défendable, pas un idéal, et le dire vaut mieux que de le laisser croire complet.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.version import __version__

#: La phrase, mot pour mot, dans le PNG comme dans le sidecar.
PHRASE_NON_OEUVRE = ("image générée par IA, ne fait pas partie de l'œuvre source")

#: Les clés `tEXt` écrites dans chaque PNG. Un test vérifie qu'elles sont TOUTES relues.
CHAMPS_PNG: tuple[str, ...] = ("Software", "Generator", "AIGenerated", "Seed", "Prompt",
                               "SourceWork", "Disclaimer")

#: Longueur au-delà de laquelle le prompt est tronqué dans le bloc `tEXt`. Le prompt ENTIER
#: vit dans le sidecar : un `tEXt` de plusieurs kilo-octets alourdirait chaque image pour une
#: information déjà archivée à côté, et certains lecteurs de métadonnées le tronquent eux-mêmes
#: sans le dire — mieux vaut tronquer visiblement, avec un « … », que de le subir.
PROMPT_MAX = 400

#: Suffixe du manifeste. `<image>.png` → `<image>.png.provenance.json` : le suffixe s'AJOUTE
#: au nom complet et ne remplace pas l'extension, pour qu'un tri alphabétique garde l'image et
#: son manifeste côte à côte, et qu'aucune paire ne puisse se percuter.
SUFFIXE_PROVENANCE = ".provenance.json"

#: Suffixe du graphe envoyé — L28.3. Même règle de nommage que le manifeste, et pour la même
#: raison : `<image>.png.graphe.json` reste collé à son image dans un tri alphabétique.
#:
#: ⚠ **Un fichier à côté, et pas un bloc `tEXt`.** Le `tEXt` porte l'identité de l'image ; un
#: JSON de plusieurs kilo-octets recopié dans chaque PNG alourdirait chaque fichier pour une
#: information qui vit déjà à côté, et certains lecteurs de métadonnées tronquent en silence.
#: Le `PLAN-28` L28.3 l'écrit noir sur blanc.
SUFFIXE_GRAPHE = ".graphe.json"


class MarquageImpossible(RuntimeError):
    """Le marquage ne peut pas être posé — donc l'image ne s'écrit pas."""


def identifiant_oeuvre(projet: str, tome: str = "", explicite: str = "") -> str:
    """Un identifiant LOCAL et stable, qui ne dit pas le titre.

    `explicite` (clé `illustration.marquage.identifiant_oeuvre`) l'emporte si l'utilisateur
    en a choisi un — c'est son droit, à ses risques : le garde `_sans_titre` refusera quand
    même une valeur qui contient le nom du projet."""
    if explicite.strip():
        return explicite.strip()
    graine = f"{projet}\x00{tome}".encode("utf-8")
    return "oeuvre-" + hashlib.sha256(graine).hexdigest()[:12]


def empreinte_fichier(chemin, bloc: int = 1 << 20) -> str:
    """SHA-256 par blocs de 1 Mio — le patron de `manga/models.py:empreinte`, repris tel quel
    pour que deux empreintes du dépôt se comparent sans se demander comment elles sont faites."""
    h = hashlib.sha256()
    with open(chemin, "rb") as fh:
        for morceau in iter(lambda: fh.read(bloc), b""):
            h.update(morceau)
    return h.hexdigest()


def _sans_titre(valeurs, interdits) -> None:
    """Lève si une valeur écrite porte un mot interdit — typiquement le nom du projet.

    ⚠ Elle lève, elle ne censure pas. Retirer silencieusement le titre d'un prompt changerait
    le prompt archivé, donc casserait le rejeu, donc mentirait sur ce qui a été envoyé au
    modèle. Si le titre est dans le prompt, c'est le prompt qu'il faut corriger — et la porte
    humaine de la phase 1 est exactement l'endroit pour le faire."""
    plats = " ".join(str(v) for v in valeurs).casefold()
    for mot in interdits:
        mot = str(mot or "").strip()
        if len(mot) >= 3 and mot.casefold() in plats:
            raise MarquageImpossible(
                f"« {mot} » — le nom de l'œuvre ou du tome — apparaît dans ce qui allait "
                f"être écrit dans les métadonnées de l'image.\n"
                f"  Le dépôt refuse déjà d'exposer les titres comme noms de dossier ; une "
                f"image qui les porte dans son PNG les exposerait le jour où elle est "
                f"partagée par erreur. Corrige le prompt dans requete.yaml — c'est à cela "
                f"que sert la porte humaine — puis relance la phase image.")


def manifeste(requete, sortie, *, projet: str, tome: str, identifiant: str,
              validation: dict, config_sha256: str = "", poids_sha256: str = "",
              modele: str = "", identite: dict | None = None,
              prompt_source: dict | None = None) -> dict:
    """Le dictionnaire de provenance, avant écriture. Séparé de `ecrire` pour être testable
    et pour que le rapport puisse le lire sans toucher au disque.

    ⚠ `identite` (lot 25) porte les trois grandeurs, le verdict **et les planchers** auxquels
    elles ont été comparées. Publier `ressemblance: 0,41` sans le plancher de confusion
    auquel ce 0,41 est comparé serait la faute que `docs/chiffres-de-reference.md` interdit :
    « un chiffre sans dénominateur n'est pas une mesure, c'est une impression ». La clé est
    **absente** quand la voie A n'est pas armée, plutôt que présente et vide.

    ⚠ `prompt_source` (lot 26) porte **ce qui a fabriqué le prompt** : le gabarit et son
    empreinte, la forme du champ texte, la langue, le cadrage, et la source de chaque
    attribut. C'est le critère 6 du `PLAN-26` — « depuis un sidecar seul, on doit pouvoir
    régénérer la même image » — et un gabarit nommé sans son empreinte ne suffirait pas :
    « gabarit portrait v1 » ne dit pas si le fichier a été édité depuis. Le dépôt applique
    déjà cette règle à `config.yaml` et aux poids."""
    # ⚠ **L28.3.** Deux clés du moteur ne sont PAS de la « provenance de moteur » : le graphe
    # réellement envoyé, qui pèse plusieurs kilo-octets et part dans un fichier à côté, et les
    # lignes de journal du serveur, qui disent dans quel régime il a tourné. Les laisser dans
    # `moteur_details` les aurait noyées au milieu d'un dictionnaire de diagnostic.
    details = dict(sortie.provenance or {})
    graphe_envoye = details.pop("graphe", None)
    journal = details.pop("journal_serveur", None)
    complet = {
        "schema": 1,
        "avertissement": PHRASE_NON_OEUVRE,
        "genere_par_ia": True,
        "angelith": __version__,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "oeuvre": identifiant,
        "modele": modele or requete.modele,
        "moteur": (sortie.provenance or {}).get("moteur", ""),
        "poids_sha256": poids_sha256,
        "config_sha256": config_sha256,
        "requete_sha256": requete.empreinte(),
        # Le payload EXACT envoyé au moteur, canaux compris. C'est lui qui rend `--rejouer`
        # possible, et c'est ce que le critère 7 du PLAN-24 exige d'archiver.
        "payload": requete.payload(),
        "canaux": list(requete.canaux_utilises()),
        "validation_humaine": dict(validation or {}),
        "moteur_details": details,
        "secondes": round(float(sortie.secondes or 0.0), 3),
        "vram_pic_octets": sortie.vram_pic_octets,
        # Ni `projet` ni `tome` : ils ne servent qu'aux garde-fous ci-dessous.
        "_interdits": [projet, tome],
    }
    if identite:
        complet["identite"] = identite
    if prompt_source:
        complet["prompt_source"] = prompt_source
    if journal:
        complet["journal_serveur"] = journal
    if graphe_envoye:
        # Consommé par `ecrire`, qui l'écrit à CÔTÉ et le remplace ici par sa référence.
        complet["_graphe"] = graphe_envoye
    return complet


def ecrire(sortie, destination, *, provenance: dict) -> tuple[Path, Path]:
    """**Le seul** chemin du dépôt qui écrive un PNG d'illustration. Rend (image, manifeste).

    Il n'y a pas de variante « sans marquage », pas de drapeau, pas de mode brut : un test
    (`test_illustration_marquage.py`) vérifie qu'aucun autre module de `illustration/` ne
    sait écrire d'octets PNG, et c'est ce test qui fait tenir le critère 7 du `PLAN-24`."""
    from PIL import Image, PngImagePlugin

    destination = Path(destination)
    if destination.suffix.lower() != ".png":
        raise MarquageImpossible(
            f"{destination.name} : seul le PNG est écrit par cette brique — c'est lui qui "
            f"porte les blocs tEXt du marquage, et un JPEG les perdrait sans un mot.")

    provenance = dict(provenance or {})
    interdits = provenance.pop("_interdits", [])
    graphe_envoye = provenance.pop("_graphe", None)
    payload = provenance.get("payload") or {}
    identifiant = str(provenance.get("oeuvre") or "")
    prompt = str(payload.get("prompt") or "")
    _sans_titre([prompt, payload.get("prompt_negatif") or "", identifiant,
                 provenance.get("modele") or ""], interdits)

    texte = {
        "Software": f"Angelith {provenance.get('angelith') or __version__}",
        "Generator": _generateur(provenance),
        "AIGenerated": "true",
        "Seed": str(payload.get("graine", "")),
        "Prompt": _tronquer(prompt),
        "SourceWork": identifiant,
        "Disclaimer": PHRASE_NON_OEUVRE,
    }
    manquants = [c for c in CHAMPS_PNG if not str(texte.get(c, "")).strip()]
    if [m for m in manquants if m != "Prompt"]:
        # `Prompt` peut légitimement être vide (une requête à canaux seuls) ; les autres non.
        raise MarquageImpossible(
            f"marquage incomplet, champs vides : {', '.join(manquants)} — l'image n'est pas "
            f"écrite. Un PNG non marqué contredirait la position publique du projet sur l'IA "
            f"générative au moment même où elle est écrite.")

    info = PngImagePlugin.PngInfo()
    for cle, valeur in texte.items():
        info.add_text(cle, valeur)

    import io as _io

    from illustration import frontiere

    image = Image.open(_io.BytesIO(sortie.png))
    image.load()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # ⚠ Le SEUL endroit du dépôt qui lève le drapeau d'écriture d'image. Hors de ce bloc, le
    # garde de `frontiere.py` refuse tout fichier image — c'est ce qui rend le critère 7 du
    # `PLAN-24` vrai à l'exécution, et pas seulement dans une revue de sources.
    with frontiere.ecriture_marquee():
        image.save(destination, format="PNG", pnginfo=info)

    manifeste_chemin = destination.with_name(destination.name + SUFFIXE_PROVENANCE)
    complet = {**provenance, "image": destination.name,
               "image_sha256": empreinte_fichier(destination), "png_text": texte}
    if graphe_envoye:
        complet["graphe"] = _ecrire_le_graphe(destination, graphe_envoye)
    manifeste_chemin.write_text(
        json.dumps(complet, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8")
    return destination, manifeste_chemin


def _generateur(provenance: dict) -> str:
    modele = str(provenance.get("modele") or "").strip()
    moteur = str(provenance.get("moteur") or "").strip()
    revision = str((provenance.get("moteur_details") or {}).get("moteur_version") or "").strip()
    morceaux = [m for m in (modele or "modèle non nommé", moteur, revision) if m]
    return " · ".join(morceaux)


def _tronquer(prompt: str) -> str:
    prompt = " ".join(prompt.split())
    return prompt if len(prompt) <= PROMPT_MAX else prompt[:PROMPT_MAX - 1] + "…"


def relire(chemin) -> dict:
    """Les champs `tEXt` d'un PNG produit ici. Sert au test du marquage et au rapport."""
    from PIL import Image

    with Image.open(chemin) as image:
        return dict(image.text or {})


def manifeste_de(chemin) -> Path:
    """Le manifeste attendu à côté d'une image."""
    chemin = Path(chemin)
    return chemin.with_name(chemin.name + SUFFIXE_PROVENANCE)


def graphe_de(chemin) -> Path:
    """Le graphe envoyé, attendu à côté d'une image. Il n'existe que pour un moteur qui en a
    un : le moteur factice ne construit aucun graphe, et un fichier vide vaudrait moins que
    son absence."""
    chemin = Path(chemin)
    return chemin.with_name(chemin.name + SUFFIXE_GRAPHE)


def _ecrire_le_graphe(destination: Path, graphe: dict) -> dict:
    """Écrit `<image>.png.graphe.json` et rend ce que le sidecar en dira.

    ⚠ **Le sidecar porte la RÉFÉRENCE et l'empreinte, pas le graphe.** Un manifeste dans lequel
    un JSON de graphe serait recopié ferait quinze kilo-octets par image et deviendrait
    illisible à l'œil — or c'est le fichier qu'un humain ouvre pour comprendre une image. Le
    graphe est à côté, et son empreinte SHA-256 dit qu'il est bien celui qui a servi.

    ⚠ **Ce fichier se recharge dans ComfyUI par glisser-déposer** : c'est ce qui rend le
    critère 4 du `PLAN-28` possible — rejouer à la main ce que le projet a fait tourner."""
    cible = graphe_de(destination)
    contenu = json.dumps(graphe, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    cible.write_text(contenu, encoding="utf-8")
    return {"fichier": cible.name,
            "sha256": hashlib.sha256(contenu.encode("utf-8")).hexdigest(),
            "noeuds": len(graphe),
            "comment_le_rejouer": "glisse ce fichier dans ComfyUI (il est au format API) : "
                                  "il recharge le graphe exact qui a produit cette image, "
                                  "graine comprise."}
