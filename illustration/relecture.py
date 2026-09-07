# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**L'écran de relecture du prompt** — et c'est le cœur du lot 27, pas la galerie.

    phase 1 → requete.yaml → ┤ CET ÉCRAN ├ → valide: true → phase 2

`PLAN-27` L27.1 bis. Une interface qui enchaînerait les deux phases d'un seul bouton
supprimerait la porte humaine, donc la propriété qui rend toute cette brique défendable. Ce
module est la **seule** façon, pour une interface, d'ouvrir cette porte : il construit ce qu'il
faut montrer, il reçoit ce que l'humain a corrigé, et il délivre un laissez-passer que la
phase 2 exige.

## Ce que l'écran montre, et pourquoi chacune des six choses

| Ce qui est montré | Sans quoi |
|---|---|
| le **prompt**, éditable, avec l'original restaurable | une correction serait irréversible sans relancer la phase 1, qui coûte des minutes de LLM |
| le **prompt négatif**, éditable, chaque terme avec son motif | retirer un terme serait un pari, pas un choix (`gabarits/portrait.yaml` porte les motifs) |
| les **vignettes de référence**, avec leur motif, en **deux groupes** | un utilisateur qui décoche une ancre de style doit voir qu'il ne touche pas à l'identité |
| la **source de chaque attribut** | « un attribut sans citation n'est pas une observation » — la règle de la bible visuelle |
| les **canaux structurés**, désarmables et non éditables | un éditeur de masque est un lot à lui seul, et il n'est pas celui-ci |
| ce qui est **anormal**, nommé | un attribut sans source, une image introuvable : l'écran le montre plutôt que de le laisser échouer trois écrans plus loin |

## La porte, et comment elle est mécaniquement infranchissable

`Porte` est un objet à **usage unique** qui tient trois choses : le document lu, les écrans
construits **depuis ce document**, et un laissez-passer qui n'existe qu'après `valider()`.

    porte = relecture.Porte(doc)
    porte.ecrans                      # ce que l'interface affiche
    porte.valider(corrections, par="…")   # écrit valide: true, rend le document
    porte.laissez_passer()            # lève PorteFermee tant que ce n'est pas fait

L'interface appelle `laissez_passer()` avant `phase_image`. Le critère 1 bis du plan — « un
test vérifie qu'aucun chemin de l'interface ne peut lancer la phase 2 sans passage par cet
écran » — se vérifie alors de deux façons complémentaires, et il en faut deux :

1. **à l'exécution**, `Porte(doc).laissez_passer()` lève tant que `valider` n'a pas eu lieu ;
2. **statiquement**, `tests/test_illustration_relecture.py` lit `gui/atelier.py` avec `ast` et
   vérifie que `phase_image` n'est nommée que dans une fonction qui nomme aussi
   `laissez_passer` — un second chemin ajouté demain échouerait au test le jour même.

⚠ **`valider` est le SEUL écrivain de `valide: true` dans l'interface**, et il exige un nom.
Le sidecar de chaque image porte ensuite *qui a validé, quand, et le prompt avant et après
correction* — `requete.archiver_l_initial` a mis l'avant de côté dès la phase 1, et ce module
ne l'écrase jamais. Sans ce couple, la porte humaine n'est qu'un écran.

⚠ **Aucun « générer directement » n'existe ici**, et il ne doit pas en apparaître : ni
fonction, ni argument, ni raccourci. Le rejeu d'une requête déjà validée passe par
`orchestrateur.rejouer` sur un sidecar, donc sur un prompt validé une fois.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import date as _date
from pathlib import Path

from illustration import gabarits as gabarits_mod
from illustration import requete as requete_mod

#: Les deux groupes d'images, et ils ne se mélangent jamais à l'écran.
GROUPE_IDENTITE = "identite"
GROUPE_STYLE = "style"

TITRES_GROUPE = {
    GROUPE_IDENTITE: "Références d'identité — QUI est sur l'image",
    GROUPE_STYLE: "Ancrages de style — le REGISTRE du tome, pas l'identité",
}

AIDES_GROUPE = {
    GROUPE_IDENTITE: ("Ce sont ces pixels-là qui portent le visage du personnage. En "
                      "décocher toutes fait retomber la phase 2 sur de la génération pure, "
                      "et elle refuse."),
    GROUPE_STYLE: ("Le registre graphique de l'œuvre : palette, trait, aplats. Préfère une "
                   "image SANS visage — une ancre qui montre quelqu'un peut le faire "
                   "apparaître dans l'image produite. En décocher n'enlève RIEN à "
                   "l'identité."),
}

#: Les deux canaux structurés que `requete.yaml` sait porter. Ils sont livrés désarmés
#: (`PLAN-26` étape 0.4 : « n'en livrer qu'un, celui dont l'apport est mesuré »), et l'écran
#: ne sait que les **désarmer** — jamais les éditer.
CANAL_ENTITES = "entites"
CANAL_CONTROLE = "image_de_controle"

DESCRIPTIONS_CANAL = {
    CANAL_ENTITES: "masques d'entités — où va chaque élément (eligen_entity_masks)",
    CANAL_CONTROLE: "image de contrôle — la pose et la composition (Canny/Depth)",
}


class PorteFermee(RuntimeError):
    """La phase 2 a été demandée sans que l'écran de relecture ait été franchi."""


class RelectureCaduque(RuntimeError):
    """Le document a changé sous l'écran : ce qui a été relu n'est plus ce qui serait généré."""


# ─────────────────────────────  Ce que l'écran montre  ─────────────────────────────

@dataclass(frozen=True)
class Vignette:
    """Une image proposée au modèle, avec **le motif de sa présence**.

    `retenue` est ce que l'humain décide ; `motif` est ce qui lui permet de décider. Un motif
    vide est une incohérence signalée par `requete.verifier`, pas un détail cosmétique."""

    fichier: str
    motif: str
    retenue: bool
    groupe: str
    par: str = ""
    #: Le chemin résolu sur le disque, ou `None` — l'écran affiche alors « introuvable »
    #: plutôt qu'une vignette vide.
    chemin: Path | None = None
    #: Plusieurs tomes portent le même nom de fichier : la référence est AMBIGUË.
    ambigue: bool = False

    @property
    def introuvable(self) -> bool:
        return self.chemin is None


@dataclass(frozen=True)
class Terme:
    """Un terme du prompt négatif et le motif écrit dans le gabarit."""

    texte: str
    motif: str

    @property
    def explique(self) -> bool:
        return bool(self.motif.strip())


@dataclass(frozen=True)
class Attribut:
    """Un fragment du prompt, et la phrase de l'œuvre qui le justifie."""

    attribut: str
    valeur: str
    #: La phrase citée, telle qu'elle est dans le chapitre.
    texte: str
    source: str
    certitude: str = ""
    origine: str = ""

    @property
    def anomalie(self) -> bool:
        """Un attribut **sans source** ne devrait pas être là ; s'il y est, on le montre.

        ⚠ `origine: humain` n'est pas une anomalie : une description personnalisée est écrite
        par quelqu'un qui l'assume, et `atelier.bloc_libre` l'étiquette pour cela même."""
        if self.origine == "humain":
            return False
        return not self.source.strip()

    @property
    def motif_anomalie(self) -> str:
        return ("aucune source n'est enregistrée pour cet attribut — la règle de la bible "
                "visuelle est qu'un attribut sans citation n'est pas une observation. "
                "Corrige le prompt, ou reprends la fiche du personnage."
                if self.anomalie else "")


@dataclass(frozen=True)
class Canal:
    """Un canal structuré, avec son état. **Désarmable, jamais éditable.**"""

    nom: str
    description: str
    arme: bool
    #: Ce qu'on peut montrer en superposition : le masque ou l'image de contrôle.
    apercus: tuple[str, ...] = ()
    #: Le texte de chaque entité, quand le canal en porte.
    libelles: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ecran:
    """Tout ce qu'un utilisateur doit voir avant de dire oui, pour **une** image."""

    nom: str
    personnage: str
    cadrage: str
    prompt: str
    prompt_initial: str
    prompt_negatif: str
    termes_negatifs: tuple[Terme, ...] = ()
    references: tuple[Vignette, ...] = ()
    ancrages: tuple[Vignette, ...] = ()
    attributs: tuple[Attribut, ...] = ()
    canaux: tuple[Canal, ...] = ()
    nombre_images: int = 1
    graine: int | None = None
    largeur: int = 0
    hauteur: int = 0

    @property
    def corrige(self) -> bool:
        """Le prompt affiché diffère-t-il de celui que la phase 1 avait écrit ?"""
        return self.prompt.strip() != self.prompt_initial.strip()

    @property
    def retenues(self) -> tuple[Vignette, ...]:
        return tuple(v for v in self.references if v.retenue)

    @property
    def anomalies(self) -> tuple[str, ...]:
        """Ce que l'écran doit signaler **avant** le clic, jamais après.

        Le lot 19 a payé cette leçon côté relettrage : « aucune génération ne part et aucun
        message d'erreur n'apparaît APRÈS le clic »."""
        sorties: list[str] = []
        for attribut in self.attributs:
            if attribut.anomalie:
                sorties.append(f"attribut « {attribut.attribut} » : "
                               f"{attribut.motif_anomalie}")
        for vignette in self.references + self.ancrages:
            if vignette.retenue and vignette.introuvable:
                sorties.append(f"image retenue introuvable : {vignette.fichier}")
            elif vignette.retenue and vignette.ambigue:
                sorties.append(f"référence AMBIGUË — « {vignette.fichier} » existe dans "
                               f"plusieurs tomes ; préfixe-la par le sien")
        for terme in self.termes_negatifs:
            if not terme.explique:
                sorties.append(f"terme négatif « {terme.texte} » sans motif : il ne vient "
                               f"pas du gabarit, personne ne peut juger s'il faut le garder")
        if self.references and not self.retenues:
            sorties.append("toutes les références d'identité sont décochées — la phase 2 "
                           "refusera : le modèle inventerait un visage au lieu de suivre "
                           "celui de l'œuvre")
        if not self.prompt.strip() and not self.retenues:
            sorties.append("ni prompt ni référence retenue : le moteur n'aurait rien à "
                           "honorer")
        return tuple(sorties)


# ──────────────────────────  Ce que l'humain renvoie  ──────────────────────────

@dataclass
class Correction:
    """Ce que l'écran a changé pour **une** image. Tout est facultatif : `None` = inchangé.

    ⚠ `retenues` et `ancrages_retenus` sont des ensembles de **noms de fichier**, pas des
    indices : un écran qui réordonne ses vignettes ne doit pas cocher la mauvaise image."""

    prompt: str | None = None
    prompt_negatif: str | None = None
    retenues: set | None = None
    ancrages_retenus: set | None = None
    #: Les canaux que l'humain a désarmés — jamais édités.
    canaux_desarmes: set = field(default_factory=set)
    nombre_images: int | None = None
    #: `"aleatoire"` vide la graine ; un entier la fixe ; `None` ne touche à rien.
    graine: object = None


# ────────────────────────────  Construire les écrans  ────────────────────────────

def ecrans(doc: dict, *, racine_projet=None, gabarit: str = "", langue: str = "") -> list:
    """Un `Ecran` par bloc de `requete.yaml`, dans l'ordre du fichier.

    `racine_projet` (`build/<Projet>/`) permet de résoudre les vignettes ; sans lui, on ne
    prétend pas les avoir trouvées et `chemin` reste `None` sans que ce soit une anomalie."""
    doc = requete_mod.fill_defaults(doc)
    motifs = _motifs_negatifs(gabarit or doc["gabarit"], langue or doc["langue"])
    initiaux = doc["validation"]["prompt_initial"] or {}
    return [_ecran(bloc, motifs, initiaux, racine_projet) for bloc in doc["images"]]


def _ecran(bloc: dict, motifs: dict, initiaux: dict, racine_projet) -> Ecran:
    return Ecran(
        nom=bloc["nom"],
        personnage=bloc["personnage"],
        cadrage=bloc["cadrage"],
        prompt=bloc["prompt"],
        # ⚠ Le repli est le prompt COURANT, jamais la chaîne vide : un fichier écrit avant
        # que `archiver_l_initial` existe n'a pas d'original, et proposer « restaurer » vers
        # du vide effacerait le travail au lieu de le rendre.
        prompt_initial=str(initiaux.get(bloc["nom"]) or bloc["prompt"]),
        prompt_negatif=bloc["prompt_negatif"],
        termes_negatifs=_termes(bloc["prompt_negatif"], motifs),
        references=_vignettes(bloc["references"], GROUPE_IDENTITE, racine_projet),
        ancrages=_vignettes(bloc["ancrages_style"], GROUPE_STYLE, racine_projet),
        attributs=_attributs(bloc["attributs_sources"]),
        canaux=_canaux(bloc["canaux"]),
        nombre_images=int(bloc["nombre_images"]),
        graine=bloc["graine"],
        largeur=int(bloc["largeur"]), hauteur=int(bloc["hauteur"]))


def _motifs_negatifs(gabarit: str, langue: str) -> dict:
    """`{terme: motif}` du gabarit, ou `{}` si le gabarit est introuvable.

    Un gabarit absent ne doit pas empêcher de relire : l'écran affiche alors les termes sans
    motif, et `Ecran.anomalies` le signale — ce qui est exactement la bonne réaction."""
    try:
        return gabarits_mod.charger(gabarit, langue=langue).motifs_negatifs()
    except Exception:                                # noqa: BLE001 — diagnostic seulement
        return {}


def _termes(prompt_negatif: str, motifs: dict) -> tuple:
    return tuple(Terme(texte=t, motif=str(motifs.get(t) or "").strip())
                 for t in (p.strip() for p in prompt_negatif.split(",")) if t)


def _vignettes(choisies, groupe: str, racine_projet) -> tuple:
    sorties = []
    for choix in choisies or []:
        fichier = str(choix.get("fichier") or "")
        chemins = _resoudre(fichier, racine_projet)
        sorties.append(Vignette(
            fichier=fichier, motif=str(choix.get("motif") or ""),
            retenue=bool(choix.get("retenue")), groupe=groupe,
            par=str(choix.get("par") or ""),
            chemin=chemins[0] if chemins else None,
            ambigue=len(chemins) > 1))
    return tuple(sorties)


def _resoudre(fichier: str, racine_projet) -> list:
    """La règle du dépôt, celle de la bible, et pas une seconde écrite ici."""
    if racine_projet is None or not fichier:
        return []
    from core import bible
    try:
        return bible.chemins_de_reference(fichier, racine_projet)
    except OSError:                                  # arbre déplacé pendant la relecture
        return []


def _attributs(sources) -> tuple:
    return tuple(Attribut(
        attribut=str(a.get("attribut") or ""), valeur=str(a.get("valeur") or ""),
        texte=str(a.get("texte") or ""), source=str(a.get("source") or ""),
        certitude=str(a.get("certitude") or ""), origine=str(a.get("origine") or ""))
        for a in sources or [] if isinstance(a, dict))


def _canaux(canaux: dict) -> tuple:
    """Les canaux **présents dans le fichier**, armés ou non.

    ⚠ Un canal désarmé est listé quand même, grisé : c'est ce qui rend l'inventaire visible
    dans l'écran que l'utilisateur relit. C'est la même politique que `requete.image_vide`,
    qui écrit tous ses champs même vides — « ce qui est visible se corrige, ce qui est absent
    s'oublie »."""
    entites = list(canaux.get("entites") or [])
    controle = canaux.get("image_de_controle") or ""
    return (
        Canal(nom=CANAL_ENTITES, description=DESCRIPTIONS_CANAL[CANAL_ENTITES],
              arme=bool(entites),
              apercus=tuple(str(e.get("masque") or "") for e in entites),
              libelles=tuple(str(e.get("prompt") or "") for e in entites)),
        Canal(nom=CANAL_CONTROLE, description=DESCRIPTIONS_CANAL[CANAL_CONTROLE],
              arme=bool(controle), apercus=(str(controle),) if controle else ()),
    )


# ──────────────────────────  Appliquer ce qui a été corrigé  ──────────────────────────

def appliquer(doc: dict, corrections: dict) -> dict:
    """Un document **neuf** portant les corrections. N'écrit rien sur le disque.

    ⚠ `validation.prompt_initial` n'est **jamais** touché : c'est l'avant, et le sidecar doit
    pouvoir montrer l'avant et l'après. Une correction qui réécrirait l'original rendrait la
    traçabilité circulaire."""
    doc = requete_mod.fill_defaults(doc)
    for bloc in doc["images"]:
        correction = corrections.get(bloc["nom"])
        if correction is None:
            continue
        _appliquer_bloc(bloc, correction)
    return doc


def _appliquer_bloc(bloc: dict, correction: Correction) -> None:
    if correction.prompt is not None:
        bloc["prompt"] = str(correction.prompt).strip()
    if correction.prompt_negatif is not None:
        bloc["prompt_negatif"] = str(correction.prompt_negatif).strip()
    if correction.retenues is not None:
        _cocher(bloc["references"], correction.retenues)
    if correction.ancrages_retenus is not None:
        _cocher(bloc["ancrages_style"], correction.ancrages_retenus)
    if correction.nombre_images is not None:
        bloc["nombre_images"] = max(1, int(correction.nombre_images))
    if correction.graine == "aleatoire":
        bloc["graine"] = None
    elif correction.graine is not None:
        bloc["graine"] = int(correction.graine)
    for canal in correction.canaux_desarmes or ():
        if canal == CANAL_ENTITES:
            bloc["canaux"]["entites"] = []
        elif canal == CANAL_CONTROLE:
            bloc["canaux"]["image_de_controle"] = None


def _cocher(choisies, retenues) -> None:
    voulus = {str(f) for f in retenues}
    for choix in choisies:
        choix["retenue"] = str(choix.get("fichier") or "") in voulus


def restaurer(doc: dict, nom: str) -> dict:
    """Rend au bloc `nom` le prompt que la phase 1 avait écrit.

    ⚠ C'est la moitié qui manque à « éditable » : une correction doit être **annulable sans
    relancer la phase 1**, qui coûte des minutes de LLM. Le point 1 de L27.1 bis le demande
    mot pour mot."""
    doc = requete_mod.fill_defaults(doc)
    origine = (doc["validation"]["prompt_initial"] or {}).get(nom)
    if origine is None:
        return doc
    for bloc in doc["images"]:
        if bloc["nom"] == nom:
            bloc["prompt"] = str(origine)
    return doc


# ─────────────────────────────────  La porte  ─────────────────────────────────

def empreinte(doc: dict) -> str:
    """Ce qui a été RELU, réduit à une empreinte : c'est elle que la porte protège.

    Ne portent que les champs qui changent **ce que le moteur reçoit** — prompt, prompt
    négatif, images retenues, canaux, dimensions, graine, nombre d'images. `validation`,
    `phase1` et les motifs n'y entrent pas : les inclure ferait échouer la porte parce que
    quelqu'un a corrigé une faute de frappe dans un motif."""
    doc = requete_mod.fill_defaults(doc)
    corps = []
    for bloc in doc["images"]:
        references, ancrages = requete_mod.images_retenues(bloc)
        corps.append({
            "nom": bloc["nom"], "prompt": bloc["prompt"],
            "prompt_negatif": bloc["prompt_negatif"],
            "references": [c["fichier"] for c in references],
            "ancrages": [c["fichier"] for c in ancrages],
            "canaux": bloc["canaux"],
            "largeur": bloc["largeur"], "hauteur": bloc["hauteur"],
            "graine": bloc["graine"], "nombre_images": bloc["nombre_images"],
        })
    brut = json.dumps({"modele": doc["modele"], "images": corps},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


class Porte:
    """**Le seul chemin d'une interface vers la phase 2.** À usage unique, par requête.

    Elle tient le document, les écrans construits depuis lui, et un laissez-passer qui
    n'existe qu'après `valider()`. Voir la docstring du module pour les deux tests qui la
    rendent infranchissable — l'un à l'exécution, l'autre statique sur les sources de
    l'interface."""

    def __init__(self, doc: dict, *, racine_projet=None):
        self._doc = requete_mod.fill_defaults(doc)
        self._racine = racine_projet
        self._ecrans = ecrans(self._doc, racine_projet=racine_projet)
        self._laissez_passer: str = ""

    # ------------------------------------------------------------------ #

    @property
    def document(self) -> dict:
        return self._doc

    @property
    def ecrans(self) -> list:
        return list(self._ecrans)

    @property
    def franchie(self) -> bool:
        return bool(self._laissez_passer)

    def anomalies(self) -> list:
        """Ce que l'écran doit dire **avant** le clic, tous blocs confondus."""
        return [f"« {e.nom} » : {a}" for e in self._ecrans for a in e.anomalies]

    # ------------------------------------------------------------------ #

    def valider(self, corrections: dict | None = None, *, par: str,
                date: str = "") -> dict:
        """Applique les corrections, écrit `valide: true`, et ouvre la porte.

        ⚠ **Un nom est exigé, et il n'a pas de défaut.** `validation.par` part dans le sidecar
        de chaque image : c'est la ligne exacte que la politique IA du dossier de financement
        demande de pouvoir montrer, et « validé par (vide) » ne la montre pas —
        `requete.exiger_validation` refuserait d'ailleurs plus loin.

        ⚠ **Les deux battants de la porte sont éprouvés ICI**, avant que l'interface annonce
        quoi que ce soit : `exiger_validation` et `exiger_references_retenues`. Les laisser à
        la phase 2 ferait apparaître le refus après le clic, ce que le critère 2 du plan
        interdit."""
        nom = str(par or "").strip()
        if not nom:
            raise PorteFermee(
                "un nom est requis pour valider — il part dans le sidecar de chaque image, "
                "et c'est ce qui distingue « assisté » de « généré ». "
                "« validé par (vide) » ne montre rien.")
        doc = appliquer(self._doc, corrections or {})
        doc["valide"] = True
        doc["validation"]["par"] = nom
        doc["validation"]["date"] = date or _date.today().isoformat()
        requete_mod.exiger_validation(doc)
        requete_mod.exiger_references_retenues(doc)
        self._doc = doc
        self._ecrans = ecrans(doc, racine_projet=self._racine)
        self._laissez_passer = empreinte(doc)
        return doc

    def annuler(self) -> dict:
        """L'abandon. **Ne détruit rien** : `requete.yaml` reste sur le disque, `valide` reste
        à `false`, et le travail du LLM n'est pas perdu (point 6 de L27.1 bis)."""
        self._laissez_passer = ""
        return self._doc

    def laissez_passer(self) -> str:
        """L'empreinte de ce qui a été validé. **Lève tant que la porte n'a pas été franchie.**

        Appelée par l'interface juste avant `orchestrateur.phase_image`."""
        if not self._laissez_passer:
            raise PorteFermee(
                "la phase image a été demandée sans passage par l'écran de relecture.\n"
                "  Ce n'est pas un défaut de configuration : c'est le garde-fou. Aucune "
                "image n'existe sans qu'un humain ait relu le prompt, les images de "
                "référence et la source de chaque attribut, puis écrit son nom.\n"
                "  Il n'y a pas de « générer directement », ni bouton, ni raccourci, ni clé "
                "de configuration — pas même pour rejouer une requête déjà validée : le "
                "rejeu passe par --rejouer sur un sidecar existant.")
        return self._laissez_passer

    def verifier_le_disque(self, chemin) -> None:
        """Refuse si `requete.yaml` a changé depuis que l'écran a été construit.

        ⚠ Le cas est réel et il n'est pas théorique : le fichier est **fait** pour être édité
        à la main, et l'atelier console peut l'avoir réécrit dans une autre fenêtre. Générer
        d'après un écran périmé produirait une image que personne n'a relue, ce qui est
        exactement ce que la porte existe pour empêcher."""
        chemin = Path(chemin)
        if not chemin.is_file():
            return
        if empreinte(requete_mod.load(chemin)) != self._laissez_passer:
            raise RelectureCaduque(
                f"{chemin.name} a changé depuis que l'écran a été ouvert — rien n'est "
                f"généré.\n"
                f"  Ce qui a été relu n'est plus ce qui serait envoyé au modèle. Recharge la "
                f"requête et relis-la : c'est trois minutes, une image en coûte dix.")


# ────────────────────────────  Ce qui part dans le sidecar  ────────────────────────────

def trace_de_validation(porte: "Porte") -> dict:
    """Ce que la relecture ajoute à la provenance : **qui, quand, et l'avant/après**.

    ⚠ `orchestrateur.phase_image` écrit déjà `prompt_avant_correction` /
    `prompt_apres_correction` par bloc. Ce dictionnaire-ci porte ce qu'une **session** de
    relecture sait en plus, et que le fichier seul ne dit pas : combien de prompts ont été
    corrigés, combien d'images ont été décochées à l'écran, combien de canaux désarmés. C'est
    la différence entre « un humain a validé » et « un humain a relu »."""
    doc = porte.document
    initiaux = doc["validation"]["prompt_initial"] or {}
    references_initiales = doc["validation"]["references_initiales"] or {}
    corriges, decochees, canaux = 0, 0, 0
    for bloc in doc["images"]:
        if str(initiaux.get(bloc["nom"]) or bloc["prompt"]).strip() != bloc["prompt"].strip():
            corriges += 1
        avant = set(references_initiales.get(bloc["nom"]) or [])
        apres = {c["fichier"] for c in bloc["references"] if c["retenue"]}
        decochees += len(avant - apres)
        if not bloc["canaux"]["entites"] and not bloc["canaux"]["image_de_controle"]:
            continue
        canaux += 1
    return {
        "par": doc["validation"]["par"],
        "date": doc["validation"]["date"],
        "ecran": "illustration/relecture.py",
        "prompts_corriges": corriges,
        "images_decochees_a_l_ecran": decochees,
        "canaux_armes_au_moment_de_valider": canaux,
        "laissez_passer": porte.laissez_passer(),
        "avertissement": ("ces chiffres décrivent la RELECTURE, pas la génération : un "
                          "prompt corrigé zéro fois n'est pas un prompt non relu"),
    }


def sans_correction(ecran: Ecran) -> Correction:
    """La correction neutre d'un écran — ce que l'interface envoie quand rien n'a bougé."""
    return Correction(
        prompt=ecran.prompt, prompt_negatif=ecran.prompt_negatif,
        retenues={v.fichier for v in ecran.references if v.retenue},
        ancrages_retenus={v.fichier for v in ecran.ancrages if v.retenue},
        nombre_images=ecran.nombre_images,
        graine="aleatoire" if ecran.graine is None else int(ecran.graine))


def avec_prompt(correction: Correction, prompt: str) -> Correction:
    """Petit confort d'appel, pour que l'interface n'ait pas à connaître `dataclasses`."""
    return replace(correction, prompt=prompt)
