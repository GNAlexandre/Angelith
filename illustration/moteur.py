# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L'interface du moteur d'image, ses **canaux**, et le moteur factice qui la teste sans GPU.

## Un `Moteur` qui n'expose que `prompt` est un cul-de-sac

Le modèle d'image ne « lit » pas un fichier : il reçoit des **arguments typés**, et un seul
d'entre eux est du texte. La précision ne vient pas du format de ce texte, elle vient des
canaux qu'on utilise **en plus** de lui — et le plus payant est celui des images de référence,
qui porte l'identité du personnage.

D'où une `Requete` dont la forme est celle des canaux du moteur, pas celle d'une phrase :

| Canal | Ce qu'il contrôle |
|---|---|
| `prompt` | le contenu, le style, l'ambiance |
| `prompt_negatif` | ce qu'on refuse |
| `references` | **l'identité** — plusieurs images, désignées en prose dans le prompt |
| `entites` | **la position et la forme** de chaque élément (prompt + masque, façon `EliGen`) |
| `image_controle` | la pose, la composition (Canny/Depth, façon ControlNet) |

⚠ **Un canal qu'un moteur ne sait pas honorer est REFUSÉ, jamais ignoré.** Une requête dont le
masque a été jeté sans un mot produirait une image plausible et fausse, et personne ne saurait
pourquoi. `verifier_canaux` lève un `CanalRefuse` qui nomme le canal **et** le motif ; c'est la
seule politique acceptable et il n'y a pas de drapeau pour l'assouplir.

⚠ **Et depuis le `PLAN-30` (2026-09-03), la réciproque existe : `CanalExige`.** Un graphe peut
placer un nœud **en série sur le chemin du modèle** — c'est le cas d'un ControlNet : `MODEL`
entre, `MODEL` sort. Un tel graphe ne **dégrade pas** : privé de son canal, il ne produit pas
une image moins bonne, il ne produit rien. Il déclare donc ce qu'il exige, et
`verifier_canaux_exiges` refuse avant le GPU en nommant le champ à remplir. ⚠ `CANAUX_EXIGES`
est **vide sur tous les moteurs livrés armés**, et un test en fait une règle : un graphe qui
exige un canal n'est pas un graphe du chemin nominal.

⚠ **Le texte reste du texte.** `payload()` produit le JSON typé envoyé au moteur et archivé
dans le sidecar de provenance ; il ne sérialise **jamais** la requête entière dans le champ
`prompt`. Le JSON y coûterait des tokens sans porter de structure lisible par l'encodeur — et
la forme optimale de ce champ est une question mesurée au `PLAN-26` étape 0.3, pas une
préférence de style.

## Pourquoi un moteur factice, et pourquoi il n'ignore rien non plus

`MoteurFactice` rend un PNG uni dont la couleur dérive de la requête. Il permet de tester
**toute** la brique en CI, sans poids et sans GPU, donc hors marqueur `modeles`. Sa couleur
dérive du payload **entier**, canaux compris, et pas seulement de la graine : c'est ce qui
fait qu'un test de bout en bout voit qu'une référence changée a changé quelque chose. Un
factice qui n'écouterait que la graine laisserait passer un moteur qui jette ses canaux.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Protocol, runtime_checkable

#: Les canaux, dans l'ordre où ils comptent pour la précision du résultat (cf.
#: `README-ILLUSTRATION-23-27.md` §4 ter : le gain le plus élevé n'est PAS dans le texte).
CANAUX: tuple[str, ...] = ("prompt", "prompt_negatif", "references", "entites",
                           "image_controle")

#: Dimensions par défaut. 1328 × 1328 est le carré natif annoncé pour la famille Qwen-Image ;
#: c'est aussi la dimension à laquelle l'étape 0.3 du `PLAN-24` demande de mesurer, pour que
#: les trois chemins d'exécution se comparent au même prix.
LARGEUR_DEFAUT = 1328
HAUTEUR_DEFAUT = 1328


class CanalRefuse(RuntimeError):
    """Un moteur a reçu un canal qu'il ne sait pas honorer, et il le dit au lieu de l'ignorer."""

    def __init__(self, canal: str, moteur: str, motif: str) -> None:
        self.canal, self.moteur, self.motif = canal, moteur, motif
        super().__init__(
            f"canal « {canal} » refusé par le moteur « {moteur} » : {motif}\n"
            f"  Il n'est PAS ignoré en silence : une requête dont un canal a été jeté sans "
            f"un mot produirait une image plausible et fausse. Retire le canal de "
            f"requete.yaml, ou change de moteur.")


class CanalExige(RuntimeError):
    """La **réciproque** de `CanalRefuse` : le graphe exige un canal que la requête ne porte pas.

    ⚠ **Elle existe parce que le `PLAN-30` L30.1 a produit le premier graphe du dépôt qui ne
    dégrade PAS.** Jusqu'ici, un nœud dont le marqueur n'était pas substitué était simplement
    **élagué** (`comfyui._elaguer`), et le graphe restait exécutable : c'est ce qui permet de
    balayer une, deux ou trois références avec un seul fichier. Un nœud de contrôle est
    différent — il est **en série sur le chemin du modèle**, `MODEL` entre et `MODEL` sort —,
    donc l'élaguer priverait le `KSampler` de son modèle, et ComfyUI répondrait sur une entrée
    manquante sans dire laquelle.

    Le graphe déclare donc ce qu'il exige (`_candidat.exige`), et le refus arrive **ici**,
    avant la première seconde de GPU, avec le nom du canal et le champ à remplir."""

    def __init__(self, canal: str, moteur: str, motif: str) -> None:
        self.canal, self.moteur, self.motif = canal, moteur, motif
        super().__init__(
            f"canal « {canal} » EXIGÉ par le moteur « {moteur} », et absent de la requête : "
            f"{motif}\n"
            f"  Ce n'est pas la faute inverse : « canal refusé » dit qu'un graphe ne sait pas "
            f"honorer un canal demandé ; ceci dit qu'un graphe ne sait pas travailler SANS. "
            f"Remplis le champ dans requete.yaml, ou choisis un autre workflow.")


@dataclass(frozen=True)
class Entite:
    """Un élément localisé : son texte et le masque qui dit où il est.

    `masque` est un chemin de fichier image (niveaux de gris, blanc = la zone). Le canal
    correspondant chez `Qwen-Image-EliGen-V2` est `eligen_entity_prompts` +
    `eligen_entity_masks`."""

    prompt: str
    masque: str = ""

    def payload(self) -> dict:
        return {"prompt": self.prompt, "masque": self.masque}


@dataclass(frozen=True)
class Requete:
    """Ce qu'on demande au moteur. **Gelée** : une requête se rejoue, elle ne se retouche pas.

    Une retouche passe par `dataclasses.replace` — donc par une requête NOUVELLE, avec sa
    propre empreinte, sa propre validation humaine et son propre sidecar. C'est ce qui rend le
    champ `valide` de `requete.yaml` défendable : il porte sur un objet qui ne bouge plus."""

    prompt: str = ""
    prompt_negatif: str = ""
    references: tuple[str, ...] = ()
    entites: tuple[Entite, ...] = ()
    image_controle: str = ""
    largeur: int = LARGEUR_DEFAUT
    hauteur: int = HAUTEUR_DEFAUT
    graine: int = 0
    pas: int = 30
    guidage: float = 4.0
    modele: str = ""

    def canaux_utilises(self) -> tuple[str, ...]:
        """Les canaux réellement portés par cette requête. Les scalaires (dimensions, graine,
        pas, guidage) n'en sont pas : tout moteur les honore, il n'y a rien à refuser."""
        porte = {
            "prompt": bool(self.prompt.strip()),
            "prompt_negatif": bool(self.prompt_negatif.strip()),
            "references": bool(self.references),
            "entites": bool(self.entites),
            "image_controle": bool(self.image_controle.strip()),
        }
        return tuple(c for c in CANAUX if porte[c])

    def payload(self) -> dict:
        """Le JSON **typé** envoyé au moteur, et archivé tel quel dans le sidecar.

        C'est lui qui rend le rejeu exact possible — d'où l'ordre de clés figé et les types
        primitifs : un `Path` ou un `tuple` ne survivent pas à un aller-retour JSON."""
        return {
            "prompt": self.prompt,
            "prompt_negatif": self.prompt_negatif,
            "references": list(self.references),
            "entites": [e.payload() for e in self.entites],
            "image_controle": self.image_controle,
            "largeur": int(self.largeur),
            "hauteur": int(self.hauteur),
            "graine": int(self.graine),
            "pas": int(self.pas),
            "guidage": float(self.guidage),
            "modele": self.modele,
        }

    def empreinte(self) -> str:
        """SHA-256 du payload canonique. Deux requêtes de même empreinte doivent produire la
        même image — c'est le critère de reproductibilité de L24.5, et il se vérifie sans
        rien savoir du moteur."""
        canonique = json.dumps(self.payload(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonique.encode("utf-8")).hexdigest()

    @classmethod
    def depuis_payload(cls, payload: dict) -> "Requete":
        """Reconstruit une requête depuis son payload archivé — c'est `--rejouer`."""
        brut = dict(payload or {})
        entites = tuple(Entite(prompt=str(e.get("prompt") or ""),
                               masque=str(e.get("masque") or ""))
                        for e in (brut.get("entites") or []) if isinstance(e, dict))
        return cls(
            prompt=str(brut.get("prompt") or ""),
            prompt_negatif=str(brut.get("prompt_negatif") or ""),
            references=tuple(str(r) for r in (brut.get("references") or [])),
            entites=entites,
            image_controle=str(brut.get("image_controle") or ""),
            largeur=int(brut.get("largeur") or LARGEUR_DEFAUT),
            hauteur=int(brut.get("hauteur") or HAUTEUR_DEFAUT),
            graine=int(brut.get("graine") or 0),
            pas=int(brut.get("pas") or 30),
            guidage=float(brut.get("guidage") if brut.get("guidage") is not None else 4.0),
            modele=str(brut.get("modele") or ""),
        )

    def avec(self, **champs) -> "Requete":
        """Une requête NOUVELLE, dérivée de celle-ci. Cf. la note de la classe."""
        return replace(self, **champs)


@dataclass(frozen=True)
class Sortie:
    """Ce qu'un moteur rend : les octets PNG **et** ce qu'il faut pour les défendre."""

    png: bytes
    provenance: dict = field(default_factory=dict)
    secondes: float = 0.0
    vram_pic_octets: int | None = None


@runtime_checkable
class Moteur(Protocol):
    """Le contrat. Deux implémentations au plus — un client, jamais un framework.

    ⚠ `CANAUX_SUPPORTES` est **déclaratif et vérifié** : `verifier_canaux` s'en sert pour
    refuser avant de dépenser une seconde de GPU. Un moteur qui déclarerait un canal sans
    l'honorer serait un mensonge que rien n'attraperait — c'est la seule faiblesse connue de
    ce dispositif, et elle est nommée ici plutôt que masquée."""

    nom: str
    CANAUX_SUPPORTES: frozenset

    def disponible(self) -> bool:
        """Le moteur peut-il travailler MAINTENANT ? Ne télécharge rien, ne charge rien."""
        ...

    def generer(self, requete: Requete) -> Sortie:
        ...

    def decharger(self) -> bool:
        """Rend la VRAM en fin de run. Optionnel : un moteur qui ne charge rien n'a rien à
        rendre, et `decharger_moteur` s'en accommode."""
        ...


def decharger_moteur(moteur) -> bool:
    """Décharge `moteur` s'il sait le faire. Rend True si quelque chose a été libéré.

    ⚠ C'est la SECONDE moitié de la bascule VRAM, et elle est aussi structurelle que la
    première : le `README-ILLUSTRATION-23-27` §4 bis décrit le run comme « déchargement du LLM
    → génération → le modèle d'image est déchargé, le LLM peut revenir ». Sans elle, un
    `run.py` lancé derrière trouve la carte prise par 12 Go de transformeur."""
    rendre = getattr(moteur, "decharger", None)
    return bool(rendre()) if callable(rendre) else False


def verifier_canaux(moteur, requete: Requete) -> None:
    """Lève un `CanalRefuse` au premier canal que `moteur` ne déclare pas.

    Appelée par chaque implémentation **en tête** de `generer`, avant tout coût. Le motif est
    celui que le moteur publie dans `MOTIFS`, ou un motif générique s'il n'en donne pas."""
    supportes = frozenset(getattr(moteur, "CANAUX_SUPPORTES", ()) or ())
    motifs = dict(getattr(moteur, "MOTIFS", {}) or {})
    nom = str(getattr(moteur, "nom", type(moteur).__name__))
    for canal in requete.canaux_utilises():
        if canal not in supportes:
            raise CanalRefuse(canal, nom, motifs.get(
                canal, "ce moteur ne déclare pas ce canal dans CANAUX_SUPPORTES"))


def verifier_canaux_exiges(moteur, requete: Requete) -> None:
    """Lève un `CanalExige` au premier canal que `moteur` **exige** et que la requête n'a pas.

    ⚠ **`CANAUX_EXIGES` est vide sur tous les moteurs livrés armés, et il doit le rester.** Un
    graphe qui exige un canal n'est pas un graphe du chemin nominal : c'est un graphe de
    mesure. Le seul du dépôt au **2026-09-03** est le graphe candidat d'image de contrôle
    (`illustration/workflows/qwen-image-edit-2511-controle.api.json`), qui n'est le défaut de
    personne et que `config.yaml` ne désigne pas."""
    exiges = tuple(getattr(moteur, "CANAUX_EXIGES", ()) or ())
    if not exiges:
        return
    portes = frozenset(requete.canaux_utilises())
    motifs = dict(getattr(moteur, "MOTIFS_EXIGES", {}) or {})
    nom = str(getattr(moteur, "nom", type(moteur).__name__))
    for canal in exiges:
        if canal not in portes:
            raise CanalExige(canal, nom, motifs.get(
                canal, "ce graphe place ce canal EN SÉRIE et ne sait pas s'en passer"))


# ──────────────────────────────  Le moteur factice  ──────────────────────────────

class MoteurFactice:
    """Un PNG uni, déterministe, dont la couleur dérive de la requête entière.

    Il n'existe pas pour faire joli : il rend testable en CI **toute** la brique — les deux
    phases, le marquage, le sidecar, la frontière d'écriture, le rejeu — sans un octet de
    poids et sans GPU. Les tests qui l'utilisent restent donc hors marqueur `modeles`.

    `canaux` restreint ce qu'il déclare supporter. C'est ce qui permet de prouver, dans un
    test, qu'un canal non supporté est **refusé avec un motif nommé** et pas ignoré."""

    nom = "factice"
    MOTIFS = {
        "references": "le moteur factice ne conditionne sur aucune image : il n'a pas de "
                      "modèle, seulement une couleur",
        "entites": "le moteur factice ne sait pas placer une entité dans un masque",
        "image_controle": "le moteur factice n'a pas de ControlNet",
        "prompt_negatif": "le moteur factice n'a rien à refuser",
    }

    def __init__(self, canaux=CANAUX, cote: int | None = None) -> None:
        self.CANAUX_SUPPORTES = frozenset(canaux)
        #: Côté du PNG rendu. Le défaut est 64 et non la dimension demandée : un test qui
        #: écrit trente 1328 × 1328 paierait des dizaines de mégaoctets pour vérifier des
        #: métadonnées. La dimension demandée reste dans le payload et dans la provenance.
        self.cote = cote or 64

    def disponible(self) -> bool:
        return True

    def decharger(self) -> bool:
        """Rien à rendre : le factice ne charge aucun poids. Il l'expose quand même, pour que
        le chemin de déchargement soit exercé par les tests de bout en bout."""
        return False

    def generer(self, requete: Requete) -> Sortie:
        verifier_canaux(self, requete)
        couleur = self._couleur(requete)
        png = _png_uni(self.cote, self.cote, couleur)
        return Sortie(png=png, provenance={
            "moteur": self.nom,
            "moteur_version": "factice/1",
            "couleur": list(couleur),
            "cote_rendu": self.cote,
            "avertissement": "image produite par le moteur FACTICE — aucun modèle génératif "
                             "n'a tourné ; elle ne vaut que pour les tests",
        })

    @staticmethod
    def _couleur(requete: Requete) -> tuple[int, int, int]:
        """La couleur dérive du payload ENTIER, canaux compris — cf. la docstring du module."""
        digest = hashlib.sha256(requete.empreinte().encode("ascii")).digest()
        return digest[0], digest[1], digest[2]


def _png_uni(largeur: int, hauteur: int, couleur: tuple[int, int, int]) -> bytes:
    """Un PNG RVB uni, écrit en mémoire. Pillow, comme partout ailleurs dans le dépôt."""
    import io as _io

    from PIL import Image

    tampon = _io.BytesIO()
    Image.new("RGB", (int(largeur), int(hauteur)), couleur).save(tampon, format="PNG")
    return tampon.getvalue()
