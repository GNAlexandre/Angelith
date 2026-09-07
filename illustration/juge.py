# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le **juge** du `PLAN-25` : un encodeur d'image ONNX, un cosinus, et trois grandeurs.

## Pourquoi un juge avant un résultat

« L'image ressemble au personnage » n'est pas une observation tant qu'on n'a pas dit *à
combien*, et *combien vaut beaucoup*. Le `PLAN-25` étape 0.2 pose la règle : **sans planchers
étalonnés, un cosinus de 0,78 ne veut rien dire.** Ce module construit donc l'instrument, et
`etalonner` construit ses graduations — dans cet ordre, jamais l'inverse.

## Ce qui est mesuré, et ce sont TROIS grandeurs, pas une

| Grandeur | Contre quoi | Ce qu'un mauvais score veut dire |
|---|---|---|
| **ressemblance** | la MOYENNE des cosinus aux références d'identité | ce n'est pas lui |
| **nouveauté** | 1 − le cosinus à la référence la PLUS PROCHE | c'est un décalque de la référence |
| **style** | les ancrages du tome, **et** l'écart des descripteurs déterministes | c'est lui, c'est inédit, et ça ne va pas avec le tome |

⚠ **Les deux premières se calculent sur les mêmes cosinus mais ne sont pas la même mesure** —
moyenne contre maximum — et c'est exactement ce que le plan exige de ne pas confondre : « une
distance qui monte peut signifier ressemblance perdue **ou** décalque, deux défauts opposés
que la même métrique confond ».

⚠ **ET ELLES DÉGÉNÈRENT SUR UN PERSONNAGE À UNE SEULE RÉFÉRENCE.** Avec une référence,
moyenne = maximum, donc `nouveauté = 1 − ressemblance` exactement : les deux grandeurs
deviennent une seule, et il devient **impossible** d'être à la fois ressemblant et inédit au
sens de ces définitions. Ce n'est pas un défaut d'implémentation, c'est ce que « une seule
référence » veut dire, et c'est le cas majoritaire du corpus réel. Le dire vaut mieux que de
publier deux colonnes qui se recopient.

## Pourquoi ONNX, et pourquoi pas OpenCV ni torch

`onnxruntime` est déjà une dépendance de `requirements-manga.txt` — c'est le seul moteur
d'inférence que le dépôt accepte, et le détecteur de bulles (104 Mo) y tourne depuis le lot 9.
Un cosinus entre deux vecteurs s'écrit en numpy ; le prétraitement d'une image (redimension,
recadrage central, normalisation) s'écrit avec Pillow, qui est déjà là. **Pas d'OpenCV**
(interdit n° 4), **pas de `torch`** : il pèserait plus que tout le reste du dépôt réuni pour
un produit scalaire.

## Le modèle, et ce que le dépôt en sait exactement

`dinov2-base` exporté en ONNX par `onnx-community`, 346 627 111 octets, SHA-256
`320d1012a6fc65b101fc85ca30ee7a47b2e4f6a2e8bd78fb9d7036def0e30cb0`.

⚠ **La licence de CE dépôt de poids n'est pas déclarée.** `facebook/dinov2-base`, la source
amont, déclare `apache-2.0` ; le réexport ONNX ne déclare rien. C'est la jurisprudence du
dépôt appliquée à l'envers de d'habitude — « licence du code Apache-2.0 ne dit rien de la
licence des poids » — et ici c'est le réexport qui est muet. Relevé le 2026-08-29, écrit dans
`illustration_models/README.md`, et **aucune URL n'est codée en dur ici** : la règle du lot 24
tient, l'utilisateur renseigne ce qu'il a vérifié.

⚠ **Un piège vérifié le 2026-08-29** : l'`ETag` que rend une requête HTTP sur
`huggingface.co/…/resolve/…` n'est **pas** le SHA-256 du fichier — c'est l'empreinte du CDN.
Seul `lfs.sha256` de l'API (`/api/models/<id>?blobs=true`) l'est. Le garde d'empreinte de
`illustration/poids.py` a refusé le fichier sur cette confusion, et il a eu raison de le faire.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path

#: Côté de l'image envoyée au réseau. 224 est la valeur du `preprocessor_config.json` amont.
#: DINOv2 accepte tout multiple de 14 : 448 a été mesuré, il coûte 3,5× plus cher et ne
#: sépare pas mieux (cf. `docs/mesures/identite-2026-08-29.md` §2.2).
COTE_RESEAU = 224

#: Rapport de redimension avant un recadrage central, celui du fichier amont : 256 pour 224.
RATIO_REDIMENSION = 256 / 224

#: Comment l'image entre dans le réseau.
#:
#: - `"centre"` — plus petit côté redimensionné à 256/224 du côté réseau, puis recadrage
#:   **central**. C'est la recette du `preprocessor_config.json` amont ;
#: - `"plein"` — l'image ENTIÈRE écrasée au carré du côté réseau.
#:
#: ⚠ Le défaut est `"plein"`, et **contre** la recette amont, parce que la mesure le dit :
#: sur les références réelles — des pages entières, pas des recadrages —, un recadrage central
#: jette la moitié de la page et le personnage avec. Écart mesuré entre « même personnage » et
#: « personnages différents », rapporté au bruit : 0,75 en centre, **1,05 en plein**. Les huit
#: variantes sont publiées.
CADRAGES = ("plein", "centre")
CADRAGE_DEFAUT = "plein"

#: Normalisation ImageNet, celle du fichier amont.
MOYENNE = (0.485, 0.456, 0.406)
ECART_TYPE = (0.229, 0.224, 0.225)

#: Comment le vecteur d'une image est tiré des jetons de sortie du transformeur.
#:
#: - `"cls"` — le jeton de classe seul, 768 dimensions ;
#: - `"cls_moy"` — la concaténation du jeton de classe et de la moyenne des jetons de
#:   parcelle, 1 536 dimensions. C'est la recette de récupération d'instance publiée avec
#:   DINOv2, et c'est le défaut ici.
#:
#: ⚠ Laquelle discrimine le mieux **sur ce corpus** est une question mesurée, pas héritée :
#: `etalonner` les compare et publie les deux séries de planchers.
AGREGATIONS = ("cls", "cls_moy")
AGREGATION_DEFAUT = "cls_moy"

#: Nom du fichier de poids attendu sous `illustration.identite.encodeur.dossier`.
ENCODEUR_DEFAUT = "dinov2-base.onnx"


class JugeIndisponible(RuntimeError):
    """L'encodeur manque, ou `onnxruntime` n'est pas installé — et on le dit avant de mesurer.

    ⚠ Il n'y a **pas** de repli silencieux vers une mesure dégradée. Un juge qui rendrait des
    cosinus calculés autrement que le jour de l'étalonnage produirait des chiffres
    comparables en apparence et faux en fait."""


# ──────────────────────────────  L'encodeur  ──────────────────────────────

class Encodeur:
    """Un encodeur d'image ONNX, et rien d'autre. Charge le modèle une fois, encode à la
    demande, met en cache par chemin **et par empreinte de fichier**.

    ⚠ Le cache est indexé par `(chemin résolu, taille, date de modification)` et non par le
    seul chemin : un banc qui régénère `major-lenvil.png` entre deux mesures doit obtenir un
    vecteur neuf, pas celui de l'image précédente."""

    def __init__(self, chemin, *, agregation: str = AGREGATION_DEFAUT,
                 cadrage: str = CADRAGE_DEFAUT, cote: int = COTE_RESEAU,
                 fournisseurs=None) -> None:
        self.chemin = Path(chemin)
        if agregation not in AGREGATIONS:
            raise ValueError(f"agrégation « {agregation} » inconnue — {AGREGATIONS}")
        if cadrage not in CADRAGES:
            raise ValueError(f"cadrage « {cadrage} » inconnu — {CADRAGES}")
        self.agregation = agregation
        self.cadrage = cadrage
        #: DINOv2 découpe l'image en parcelles de 14 pixels : un côté qui n'est pas un
        #: multiple de 14 se ferait rogner en silence par le réseau.
        self.cote = max(14, int(cote) // 14 * 14)
        self._session = None
        self._entree = ""
        self._cache: dict = {}
        self._fournisseurs = list(fournisseurs or ["CPUExecutionProvider"])

    # ── chargement paresseux : `--check` doit pouvoir dire « absent » sans charger 346 Mo ──

    def disponible(self) -> bool:
        if not self.chemin.is_file():
            return False
        try:
            import onnxruntime          # noqa: F401
        except ImportError:
            return False
        return True

    def _ouvrir(self):
        if self._session is not None:
            return self._session
        if not self.chemin.is_file():
            raise JugeIndisponible(
                f"encodeur du juge introuvable : {self.chemin}\n"
                f"  Le `PLAN-25` mesure la ressemblance avec un encodeur d'image ONNX. "
                f"Renseigne illustration.identite.encodeur.fichier et dépose le poids "
                f"(voir illustration_models/README.md) — aucune URL n'est codée en dur ici, "
                f"la licence des poids se vérifie à la source primaire.")
        try:
            import onnxruntime as ort
        except ImportError as err:
            raise JugeIndisponible(
                "onnxruntime n'est pas installé : pip install -r requirements-manga.txt\n"
                "  C'est le seul moteur d'inférence que le dépôt accepte — le détecteur de "
                "bulles y tourne déjà.") from err
        self._session = ort.InferenceSession(str(self.chemin), providers=self._fournisseurs)
        self._entree = self._session.get_inputs()[0].name
        return self._session

    # ────────────────────────────  L'encodage  ────────────────────────────

    def encoder(self, image):
        """Le vecteur **L2-normalisé** d'une image. Rend un `numpy.ndarray` de dimension 1.

        `image` est un chemin **ou des octets PNG**. Les octets servent à juger une image
        AVANT de l'écrire : le plan demande qu'une image trop proche de sa référence soit
        *rejetée*, et ne pas l'écrire est plus net que l'effacer après coup."""
        if isinstance(image, (bytes, bytearray)):
            import hashlib
            cle = ("octets", hashlib.sha256(image).hexdigest(),
                   self.cadrage, self.cote, self.agregation)
        else:
            chemin = Path(image)
            try:
                etat = chemin.stat()
            except OSError as err:
                raise JugeIndisponible(f"image illisible : {chemin} ({err})") from err
            cle = (str(chemin.resolve()), etat.st_size, int(etat.st_mtime_ns),
                   self.cadrage, self.cote, self.agregation)
        if cle in self._cache:
            return self._cache[cle]
        vecteur = self._encoder_sans_cache(image)
        self._cache[cle] = vecteur
        return vecteur

    def _encoder_sans_cache(self, chemin):
        import numpy as np
        session = self._ouvrir()
        tenseur = pretraiter(chemin, cadrage=self.cadrage, cote=self.cote)
        jetons = session.run(None, {self._entree: tenseur})[0][0]   # (n_jetons, dimension)
        cls = jetons[0]
        if self.agregation == "cls":
            brut = cls
        else:
            brut = np.concatenate([cls, jetons[1:].mean(axis=0)])
        return normaliser(np.asarray(brut, dtype=np.float64))


def _source(image):
    """Un objet que `Image.open` sait ouvrir. Des octets deviennent un `BytesIO` **neuf** à
    chaque appel : Pillow consomme le flux, et le rejouer sur le même tampon échouerait."""
    if isinstance(image, (bytes, bytearray)):
        import io
        return io.BytesIO(bytes(image))
    return image


def pretraiter(chemin, *, cadrage: str = CADRAGE_DEFAUT, cote: int = COTE_RESEAU):
    """Image → tenseur `(1, 3, cote, cote)` float32, prêt pour le réseau.

    Deux cadrages, et le choix se MESURE (cf. `CADRAGES`) : le recadrage central est la
    recette amont, l'écrasement plein garde la page entière. La normalisation ImageNet, elle,
    ne se choisit pas — deux normalisations différentes rendent deux cosinus qui se comparent
    en apparence seulement."""
    import numpy as np
    from PIL import Image

    with Image.open(_source(chemin)) as brute:
        image = brute.convert("RGB")
        largeur, hauteur = image.size
        if min(largeur, hauteur) <= 0:
            raise JugeIndisponible("image de dimension nulle")
        if cadrage == "centre":
            facteur = (cote * RATIO_REDIMENSION) / min(largeur, hauteur)
            image = image.resize((max(cote, round(largeur * facteur)),
                                  max(cote, round(hauteur * facteur))), Image.BICUBIC)
            largeur, hauteur = image.size
            gauche, haut = (largeur - cote) // 2, (hauteur - cote) // 2
            image = image.crop((gauche, haut, gauche + cote, haut + cote))
        else:
            image = image.resize((cote, cote), Image.BICUBIC)
        arr = np.asarray(image, dtype=np.float32) / 255.0

    arr = (arr - np.asarray(MOYENNE, dtype=np.float32)) / np.asarray(ECART_TYPE,
                                                                     dtype=np.float32)
    return np.ascontiguousarray(arr.transpose(2, 0, 1)[None], dtype=np.float32)


def normaliser(vecteur):
    """L2-normalise. Un vecteur nul reste nul — et son cosinus vaudra 0, pas `nan`."""
    import numpy as np
    norme = float(np.linalg.norm(vecteur))
    return vecteur / norme if norme > 0 else np.zeros_like(vecteur)


def cosinus(a, b) -> float:
    """Le cosinus de deux vecteurs déjà normalisés — donc un simple produit scalaire.

    Borné à [-1, 1] : l'arithmétique flottante rend parfois 1,0000000000000002, et un banc
    qui publierait « 1,0000000000000002 » perdrait un lecteur pour rien."""
    import numpy as np
    return float(max(-1.0, min(1.0, float(np.dot(a, b)))))


# ──────────────────────  Les trois grandeurs d'une image  ──────────────────────

@dataclass(frozen=True)
class Grandeurs:
    """Ce qu'on mesure sur UNE image générée. Trois grandeurs, jamais moyennées entre elles.

    `ressemblance` et `nouveaute` viennent des mêmes cosinus mais pas du même agrégat — cf.
    la docstring du module, et la dégénérescence à une seule référence."""

    ressemblance: float | None = None
    nouveaute: float | None = None
    style_embedding: float | None = None
    #: Écart moyen des descripteurs déterministes à la signature du tome
    #: (`core.illustrations.ecart_signature`).
    style_descripteurs: float | None = None
    #: Le descripteur qui s'écarte le plus, et de combien. `("", 0.0)` si non mesuré.
    descripteur_decroche: tuple = ("", 0.0)
    #: Même régime de couleur que le tome ? `None` = non mesuré.
    meme_regime_couleur: bool | None = None
    #: Nombre de références d'identité utilisées — le dénominateur, et il commande la lecture.
    references: int = 0
    #: Nombre d'ancrages de style utilisés.
    ancrages: int = 0

    @property
    def degeneree(self) -> bool:
        """Vrai quand `ressemblance` et `nouveaute` sont la même mesure (une seule référence)."""
        return self.references <= 1

    def resume(self) -> dict:
        return {"ressemblance": self.ressemblance, "nouveaute": self.nouveaute,
                "style_embedding": self.style_embedding,
                "style_descripteurs": self.style_descripteurs,
                "descripteur_decroche": list(self.descripteur_decroche),
                "meme_regime_couleur": self.meme_regime_couleur,
                "references": self.references, "ancrages": self.ancrages,
                "degeneree": self.degeneree}


def mesurer(encodeur: Encodeur, image, *, references=(), ancrages=(),
            signature_tome: dict | None = None) -> Grandeurs:
    """Les trois grandeurs d'une image générée. Chaque grandeur absente reste `None`.

    ⚠ `None` et non 0 : un cosinus de 0 est une mesure (« aucun rapport »), une absence de
    référence n'en est pas une. Les confondre ferait passer un personnage sans référence pour
    un échec de ressemblance."""
    vecteur = encodeur.encoder(image)
    refs = [encodeur.encoder(r) for r in references]
    cos_refs = [cosinus(vecteur, v) for v in refs]

    ressemblance = statistics.fmean(cos_refs) if cos_refs else None
    nouveaute = (1.0 - max(cos_refs)) if cos_refs else None

    ancres = [encodeur.encoder(a) for a in ancrages]
    style_emb = (statistics.fmean(cosinus(vecteur, v) for v in ancres) if ancres else None)

    style_desc, decroche, meme_regime = None, ("", 0.0), None
    if signature_tome:
        style_desc, decroche, meme_regime = ecart_de_style(image, signature_tome)

    return Grandeurs(
        ressemblance=ressemblance, nouveaute=nouveaute,
        style_embedding=style_emb, style_descripteurs=style_desc,
        descripteur_decroche=decroche, meme_regime_couleur=meme_regime,
        references=len(refs), ancrages=len(ancres))


def ecart_de_style(image, signature_tome: dict):
    """L'écart des descripteurs DÉTERMINISTES entre une image et la signature d'un tome.

    Rend `(écart moyen, (descripteur qui décroche, son écart), même régime de couleur)`.

    ⚠ **Le descripteur qui décroche est nommé, et c'est le point.** « saturation 2,4× la
    signature » dit quoi corriger dans la requête ; « style 0,21 » ne dit rien. C'est la
    doctrine des motifs nommés de `manga/detection_retry.py`, transposée."""
    from core import illustrations as illus_mod

    signature_image = illus_mod.descripteurs(_source(image))
    if not signature_image:
        return None, ("", 0.0), None
    ecart = illus_mod.ecart_signature(signature_image, signature_tome)
    pires = [(d, ecart[d]) for d in illus_mod.DESCRIPTEURS if ecart.get(d) is not None]
    decroche = max(pires, key=lambda c: c[1]) if pires else ("", 0.0)
    return ecart.get("moyenne"), decroche, ecart.get("meme_regime_couleur")


def libelle_decrochage(descripteur: str, valeur_image: float | None,
                       valeur_tome: float | None) -> str:
    """« saturation 4,9× la signature du tome » — un motif nommé, pas un score.

    Le rapport de deux descripteurs est plus lisible qu'une différence : « 0,26 contre 0,07 »
    demande un calcul mental, « 3,9× » n'en demande pas."""
    if not descripteur:
        return ""
    if not valeur_tome:
        return f"{descripteur} {valeur_image:.4f} contre une signature à zéro"
    rapport = (valeur_image or 0.0) / valeur_tome
    return (f"{descripteur} {rapport:.2f}× la signature du tome "
            f"({valeur_image:.4f} contre {valeur_tome:.4f})")


# ────────────────────────────  Les planchers, étape 0.2  ────────────────────────────

@dataclass
class Echelle:
    """Un plancher : sa valeur, son dénominateur, et les paires qui l'ont produit."""

    nom: str
    valeurs: list = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.valeurs)

    @property
    def mediane(self) -> float | None:
        return statistics.median(self.valeurs) if self.valeurs else None

    @property
    def moyenne(self) -> float | None:
        return statistics.fmean(self.valeurs) if self.valeurs else None

    @property
    def ecart_type(self) -> float | None:
        return statistics.stdev(self.valeurs) if len(self.valeurs) > 1 else None

    @property
    def mini(self) -> float | None:
        return min(self.valeurs) if self.valeurs else None

    @property
    def maxi(self) -> float | None:
        return max(self.valeurs) if self.valeurs else None

    def resume(self) -> dict:
        return {"nom": self.nom, "n": self.n, "mediane": self.mediane,
                "moyenne": self.moyenne, "ecart_type": self.ecart_type,
                "min": self.mini, "max": self.maxi}


#: Les cinq paires de l'étape 0.2, dans l'ordre du plan. Les trois premières situent
#: l'IDENTITÉ, les deux dernières le REGISTRE GRAPHIQUE. **Une seule métrique, deux échelles
#: distinctes** — les mélanger est l'erreur que le plan nomme explicitement.
PAIRES = (
    ("identite_haut", "deux références du MÊME personnage"),
    ("identite_confusion", "références de DEUX personnages différents de la même œuvre"),
    ("identite_negatif", "une référence contre une image d'une AUTRE œuvre"),
    ("style_haut", "deux illustrations quelconques du MÊME tome"),
    ("style_bas", "une illustration du tome contre une illustration d'une AUTRE œuvre"),
)

#: Quelles paires appartiennent à quelle échelle.
ECHELLE_IDENTITE = ("identite_haut", "identite_confusion", "identite_negatif")
ECHELLE_STYLE = ("style_haut", "style_bas")


#: Probabilité de séparation au-dessous de laquelle les verdicts d'identité ne sont **pas
#: opposables**. 0,80 se lit en français : « présenté au hasard une paire du même personnage
#: et une paire de personnages différents, le juge les classe dans le bon ordre quatre fois
#: sur cinq ». 0,5 est le tirage à pile ou face.
#:
#: ⚠ **Ce seuil a été écrit APRÈS le premier étalonnage, et le dire fait partie de la mesure.**
#: Le critère du plan — « l'écart doit dépasser le bruit » — a été implémenté et figé avant
#: (`juge_utilisable`, branche « bruit »), et il rend **utilisable** un juge dont la séparation
#: réelle vaut 0,68. Il est trop grossier pour voir ce recouvrement : deux médianes peuvent
#: s'écarter d'un écart-type pendant que les deux populations se chevauchent presque
#: entièrement. Le dépôt ne réécrit pas ses critères en silence — celui-ci s'ajoute, l'autre
#: reste publié avec son verdict, et le document de mesure porte les deux.
SEUIL_SEPARATION = 0.80


def separation(a: Echelle, b: Echelle) -> float | None:
    """Probabilité qu'une valeur tirée de `a` dépasse une valeur tirée de `b` (une égalité
    comptant pour moitié). C'est l'aire sous la courbe ROC, calculée par les rangs.

    ⚠ **C'est la statistique qui répond à la question posée**, là où l'écart des médianes n'y
    répond qu'indirectement : elle mesure le RECOUVREMENT des deux populations, pas la
    distance de leurs centres. Deux populations dont les médianes s'écartent d'un écart-type
    peuvent se chevaucher presque entièrement — et c'est le cas sur le corpus réel."""
    import numpy as np
    if not a.valeurs or not b.valeurs:
        return None
    toutes = np.concatenate([np.asarray(a.valeurs, dtype=np.float64),
                             np.asarray(b.valeurs, dtype=np.float64)])
    ordre = toutes.argsort(kind="mergesort")
    rangs = np.empty(len(toutes), dtype=np.float64)
    rangs[ordre] = np.arange(1, len(toutes) + 1, dtype=np.float64)
    # Rangs moyens sur les ex æquo : sans ça, deux valeurs identiques compteraient l'une pour
    # l'autre selon l'ordre de tri, ce qui rendrait la mesure dépendante du hasard.
    triees = toutes[ordre]
    debut = 0
    for fin in range(1, len(triees) + 1):
        if fin == len(triees) or triees[fin] != triees[debut]:
            if fin - debut > 1:
                rangs[ordre[debut:fin]] = rangs[ordre[debut:fin]].mean()
            debut = fin
    n_a, n_b = len(a.valeurs), len(b.valeurs)
    somme = float(rangs[:n_a].sum())
    return (somme - n_a * (n_a + 1) / 2.0) / (n_a * n_b)


def seuil_median(haut: Echelle, confusion: Echelle) -> float | None:
    """Le seuil du plan : **la moitié de l'intervalle** entre le plancher de confusion et le
    plancher haut. Il est fixé par l'étalonnage, donc AVANT d'avoir vu une image générée."""
    if haut.mediane is None or confusion.mediane is None:
        return None
    return (haut.mediane + confusion.mediane) / 2.0


def juge_utilisable(haut: Echelle, confusion: Echelle,
                    libelles: tuple = ("même personnage", "personnages différents"),
                    ) -> tuple[bool, str]:
    """Le juge discrimine-t-il ? Rend `(verdict, motif écrit)`.

    Le critère du plan : « si l'écart entre "même personnage" et "personnages différents de
    la même œuvre" est inférieur à ce que le bruit de mesure justifie, **le juge automatique
    est inutilisable** : dites-le et passez au seul juge humain ».

    « Le bruit de mesure » est ici l'écart-type de la population de confusion : c'est la seule
    dispersion qu'on observe sans hypothèse. Le juge doit d'abord passer ce critère — deux
    médianes séparées d'au moins **un** écart-type de confusion.

    ⚠ **Et ce critère ne suffit pas, la mesure l'a montré.** Sur le corpus réel il rend
    « utilisable » un juge dont la probabilité de séparation vaut 0,68 : les deux médianes
    s'écartent bien d'un écart-type pendant que les deux populations se chevauchent presque
    entièrement. Le second critère — `separation >= SEUIL_SEPARATION` — a donc été **ajouté
    après le premier étalonnage**, ce que sa constante dit en toutes lettres. Les deux
    verdicts sont publiés côte à côte plutôt que le premier réécrit en silence."""
    if haut.mediane is None or confusion.mediane is None:
        return False, "l'un des deux planchers n'a aucune paire — rien à comparer"
    ecart = haut.mediane - confusion.mediane
    bruit = confusion.ecart_type
    aire = separation(haut, confusion)
    suffixe = ("" if aire is None else
               f" · séparation {aire:.4f} (seuil {SEUIL_SEPARATION:.2f})")
    if bruit is None:
        return False, (f"écart de {ecart:+.4f}, mais la population de confusion compte "
                       f"{confusion.n} paire(s) : pas d'écart-type, donc pas de bruit connu"
                       + suffixe)
    if ecart <= 0:
        return False, (f"le plancher « {libelles[0]} » ({haut.mediane:.4f}) n'est PAS "
                       f"au-dessus du plancher « {libelles[1]} » ({confusion.mediane:.4f}) — "
                       f"le juge ne distingue rien" + suffixe)
    if ecart < bruit:
        return False, (f"écart de {ecart:.4f} entre les deux médianes, pour un bruit de "
                       f"{bruit:.4f} (écart-type de la confusion, n={confusion.n}) : "
                       f"l'écart ne dépasse pas le bruit" + suffixe)
    # ⚠ Un bruit NUL n'est pas un juge parfait : c'est une population de confusion dont toutes
    # les paires valent la même chose, donc trop pauvre pour qu'un rapport y veuille dire
    # quelque chose. On ne publie alors pas de rapport, et c'est la séparation qui tranche.
    rapport = (f"soit {ecart / bruit:.2f}× le bruit" if bruit > 0 else
               f"pour un bruit NUL — les {confusion.n} paires de confusion valent toutes la "
               f"même chose, un rapport n'y voudrait rien dire")
    base = (f"écart de {ecart:.4f} entre les deux médianes, pour un bruit de {bruit:.4f} "
            f"(écart-type de la confusion, n={confusion.n}), {rapport} — le critère du plan "
            f"est tenu")
    if aire is not None and aire < SEUIL_SEPARATION:
        return False, (f"{base}, MAIS la séparation vaut {aire:.4f} pour un seuil de "
                       f"{SEUIL_SEPARATION:.2f} : présenté une paire « {libelles[0]} » et "
                       f"une paire « {libelles[1]} », le juge ne les classe dans le bon ordre "
                       f"que {aire * 100:.0f} fois sur 100. Les deux populations se "
                       f"chevauchent trop pour que ses verdicts soient opposables")
    return True, base + suffixe
