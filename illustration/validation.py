# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Valider un workflow ComfyUI **avant** de dépenser une seconde de GPU — `PLAN-28` L28.1.

## Le problème que ce module traite

Un graphe versionné dans le dépôt stocke le **nom** d'un fichier de modèle, pas un
identifiant. Renommer un modèle, ou changer de machine, casse le graphe **au premier appel** —
c'est-à-dire après le déchargement du LLM et le chargement de 12,84 Go de poids, donc au pire
moment. Le §9 de `docs/procedures/comfyui.md` liste onze pannes mesurées les 2026-08-29 et 30 ;
cinq d'entre elles se voient dans le fichier, sans serveur ou avec une seule requête en
lecture.

## Les six vérifications, et un cas réel pour chacune

| # | Vérification | Le cas mesuré où elle aurait servi |
|---|---|---|
| 1 | le fichier est au **format API**, pas au format écran | « Angelith dit que le workflow n'est pas exploitable » — §9, ligne 6 |
| 2 | chaque `class_type` **existe** sur ce serveur | `UnetLoaderGGUF` n'existe que si `ComfyUI-GGUF` est installé (§7) |
| 3 | chaque fichier de modèle nommé est **dans la liste** du nœud | « Un modèle n'apparaît pas dans la liste » — §9, ligne 7 |
| 4 | les **canaux** que ce graphe déclare, et ceux qu'il **exige** | « canal « references » refusé » — §9, ligne 5 |
| 5 | la cohérence **pas / guidage** avec la LoRA du graphe | « Images brûlées, contrastes saturés » — §9, ligne 1, et **rien ne le signalait** |
| 6 | le **nœud de sortie** : copie non marquée, ou sortie que ce client ne sait pas lire | `PLAN-30` L30.3 — ajoutée le **2026-09-03** |

⚠ **La cinquième est la seule qui ne produit aucun message côté ComfyUI.** Les autres
finissent par une erreur ; celle-là finit par une image, brûlée, qu'il faut avoir l'œil pour
reconnaître. C'est pour elle que ce module existe autant que pour les autres.

⚠ **La sixième ne refuse presque jamais, et c'est voulu.** Sur un `SaveImage` — le cas de tous
les graphes du dépôt — elle pose une **réserve** qui nomme la copie non marquée du dossier
`output/` de ComfyUI et dit comment la réduire. Elle ne devient un refus que sur
`SaveImageWebsocket`, que ce client ne sait mécaniquement pas lire.

## Le graphe CANDIDAT — ajouté le 2026-09-03, `PLAN-30` L30.1

Le dépôt versionne désormais un graphe qui **n'a jamais tourné** et dont le poids n'est
installé nulle part. Sans précaution, `--valider` serait passé en rouge sur toute machine du
monde. Un graphe qui porte un bloc racine `_candidat` voit donc ses refus « nœud absent » et
« modèle absent » **rétrogradés en réserves**, avec la phrase qui dit pourquoi — et rien
d'autre n'est adouci. Voir `_retrograder`.

## Ce qu'un serveur éteint change, et ce qu'il ne change pas

Les vérifications 1, 4, 5 et 6 se font **sur le fichier seul**. Les vérifications 2 et 3 ont
besoin du serveur : sans lui, elles ne sont pas « passées », elles sont **non faites**, et le
rapport le dit avec ce mot. Un validateur qui refuserait un nœud parce que ComfyUI est éteint
produirait le faux avertissement que `core/config_schema.py` décrit en tête — « pire que pas
de vérification du tout ».

## Refus et réserves

Un `Constat` est soit un **refus** — le run échouerait, ou produirait une image fausse — soit
une **réserve** : c'est probablement une erreur, mais l'affirmer serait dépasser la mesure. Le
message porte toujours sa **correction**, jamais seulement son constat : c'est le standard que
`tests/test_config_valide.py` a posé dans ce dépôt, « le message dit quoi coller ».
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from illustration.comfyui import CHAMPS_MODELE, ComfyIndisponible, MoteurComfyUI
from illustration.sonde import Releve, mio

#: Les champs qui nomment un fichier **que le serveur doit connaître**. `CHAMPS_MODELE` porte
#: déjà les modèles ; `image` s'y ajoute, parce que `LoadImage` refuse un nom absent de son
#: `input/` exactement comme un chargeur refuse un modèle absent, et `name` parce que c'est le
#: champ de `ModelPatchLoader` — le nœud du canal d'image de contrôle que le `PLAN-30` vise.
#:
#: ⚠ **Cette liste ne décide plus de ce qui est VÉRIFIÉ, seulement du mot employé.** La
#: vérification porte sur tout champ dont `/object_info` donne une liste de choix, parce que
#: c'est la règle de ComfyUI ; `CHAMPS_FICHIER` sert à dire « modèle » plutôt que « valeur ».
#: `CHAMPS_MODELE` n'est pas étendu, lui : il alimente la provenance, où un `name` générique
#: ferait écrire un faux nom de modèle dans un manifeste.
CHAMPS_FICHIER: tuple[str, ...] = CHAMPS_MODELE + ("image", "name")

#: Le pic de VRAM relevé le **2026-08-29** sur le graphe Lightning, en octets : **14 417 Mio**
#: sur les 20 464 de la RX 7900 XT (`docs/mesures/connecteur-qwen-2026-08-29.md`).
#:
#: ⚠ **C'est un pic mesuré sur UNE pile, pas une exigence du modèle.** Sur une autre carte, un
#: autre transformeur ou une autre quantification, il ne veut rien dire — d'où une réserve et
#: non un refus quand la marge est courte, et un chiffre affiché avec sa date à chaque fois.
PIC_VRAM_OCTETS = 14417 * 1024 * 1024

#: Au-delà de ce guidage, une LoRA distillée en 4 pas produit des images **brûlées**. Le
#: chiffre vient du §9 de la procédure : `cfg 4` avec la Lightning, contre `guidage: 1.0`
#: recommandé. On place la limite à 1,5 pour laisser passer 1,0 et 1,2 sans discuter.
GUIDAGE_MAX_DISTILLE = 1.5

#: Les fragments qui, dans un `lora_name`, désignent une LoRA **distillée** — celle qui a
#: appris à débruiter en quelques pas et qui n'attend donc plus de guidage. Écrits en clair :
#: c'est un nom de fichier, pas une propriété que le graphe déclare.
LORAS_DISTILLEES = ("lightning", "turbo", "lcm", "hyper", "dmd")

#: Les codes de constat qu'un graphe **candidat** rétrograde de refus en réserve — et eux
#: seuls. `PLAN-30` L30.1.
#:
#: ⚠ **Un candidat ne rétrograde QUE ce que son absence d'installation explique.** Un graphe
#: candidat mal formé, sans canal, ou incohérent en pas/guidage reste refusé comme un autre :
#: ces défauts-là ne viennent pas de la machine, ils viennent du fichier. Rétrograder en bloc
#: ferait du mot « candidat » un interrupteur qui éteint la validation.
CODES_CANDIDAT: frozenset = frozenset({"noeud_absent", "modele_absent", "valeur_absente"})

#: Les nœuds de sortie que **ce client** sait récupérer, et pourquoi c'est une liste courte.
#:
#: Le client lit `/history/<id>` puis `GET /view` avec le `type` que l'historique donne —
#: `output` pour `SaveImage`, `temp` pour `PreviewImage`. Les deux marchent sans changer une
#: ligne. `SaveImageWebsocket` ne publie **rien** dans l'historique : l'image part sur la
#: connexion WebSocket, que ce client n'ouvre pas.
SORTIES_RECUPERABLES: tuple[str, ...] = ("SaveImage", "PreviewImage", "SaveImageWebsocket")

#: Le nombre de pas au-delà duquel une LoRA 4 pas ne rend plus rien de plus. Le lot 25 l'a
#: mesuré autrement : passer de 4 à 50 pas n'achetait que −24 % d'écart de style pour 12,5
#: fois plus de calcul, là où le conditionnement par référence achetait −39 % pour rien.
PAS_MAX_DISTILLE = 8


@dataclass(frozen=True)
class Constat:
    """Un défaut du graphe, son cas réel, et **ce qu'il faut faire**."""

    code: str
    gravite: str            # "refus" | "réserve" | "non fait"
    quoi: str
    correction: str = ""

    def lignes(self) -> list[str]:
        marque = {"refus": "✗", "réserve": "⚠", "non fait": "·"}.get(self.gravite, "·")
        sortie = [f"{marque} [{self.code}] {self.quoi}"]
        if self.correction:
            sortie += ["    → " + ligne for ligne in self.correction.split("\n")]
        return sortie


@dataclass(frozen=True)
class Rapport:
    """Ce que la validation d'un workflow a trouvé. Sans effet de bord, sérialisable."""

    workflow: str
    constats: tuple[Constat, ...] = ()
    canaux: frozenset = frozenset()
    noeuds: tuple[str, ...] = ()
    modeles: tuple[str, ...] = ()
    releve: Releve | None = None
    verifications: dict = field(default_factory=dict)
    #: Le bloc `_candidat` du graphe, ou `{}`. Voir `MoteurComfyUI._lire_candidat`.
    candidat: dict = field(default_factory=dict)

    @property
    def refus(self) -> tuple:
        return tuple(c for c in self.constats if c.gravite == "refus")

    @property
    def reserves(self) -> tuple:
        return tuple(c for c in self.constats if c.gravite == "réserve")

    @property
    def ok(self) -> bool:
        """Aucun refus. Une réserve ne bloque pas : elle se lit et se décide."""
        return not self.refus

    def lignes(self) -> list[str]:
        sortie = [f"Workflow : {self.workflow}"]
        if self.candidat:
            sortie += lignes_candidat(self.candidat)
        sortie += [f"  Nœuds : {len(self.noeuds)} · canaux déclarés : "
                   + (", ".join(sorted(self.canaux)) or "(aucun)")]
        if self.modeles:
            sortie.append("  Modèles nommés : " + ", ".join(self.modeles))
        for nom, etat in self.verifications.items():
            sortie.append(f"  {nom} : {etat}")
        for constat in self.constats:
            sortie += ["  " + ligne for ligne in constat.lignes()]
        if self.ok and not self.reserves:
            sortie.append("  ✓ rien à signaler — ce graphe peut partir au GPU.")
        return sortie


def valider(workflow, *, releve: Releve | None = None, pas: int | None = None,
            guidage: float | None = None) -> Rapport:
    """Valide un workflow. **Aucun appel réseau ici** : le `Releve` est passé, pas cherché.

    C'est délibéré et c'est ce qui rend la fonction testable contre un `/object_info` factice,
    comme le critère 8 du `PLAN-28` l'exige. L'appelant sonde une fois et valide N workflows.

    `pas` et `guidage` sont ceux que la configuration **demandera** — la cinquième
    vérification les confronte au graphe. Absents, elle ne se prononce pas."""
    chemin = Path(workflow)
    if not chemin.is_file():
        return Rapport(workflow=str(chemin), constats=(Constat(
            "fichier_absent", "refus", f"{chemin} n'existe pas.",
            "renseigne illustration.comfyui.workflow avec le chemin d'un export au format "
            "API, ou prends l'un des graphes de illustration/workflows/ — ⚠ pas celui qui "
            "porte un bloc `_candidat`, il n'a jamais tourné."),))
    try:
        moteur = MoteurComfyUI(chemin)
    except ComfyIndisponible as err:
        # Vérification 1 : le client sait déjà dire qu'un fichier n'est pas au format API — il
        # le disait seulement trop tard, à la construction du moteur au moment de générer.
        return Rapport(workflow=str(chemin), constats=(Constat(
            "format", "refus", str(err).split("\n")[0],
            "dans ComfyUI : ⚙ → « Enable Dev mode Options », puis « Save (API Format) ». "
            "Un export normal décrit l'écran, pas le graphe."),))

    graphe = moteur.graphe
    constats: list[Constat] = []
    verifications = {"format API": "✓ le fichier est un graphe au format API"}

    constats += _noeuds_absents(graphe, releve, verifications)
    constats += _fichiers_absents(graphe, releve, verifications)
    constats += _canaux(moteur, verifications)
    constats += _pas_et_guidage(graphe, pas, guidage, verifications)
    constats += _sortie_du_graphe(graphe, verifications)
    constats += _canaux_exiges(moteur, verifications)

    candidat = dict(getattr(moteur, "candidat", None) or {})
    return Rapport(workflow=str(chemin),
                   constats=tuple(_retrograder(constats, candidat)),
                   canaux=moteur.CANAUX_SUPPORTES,
                   noeuds=tuple(sorted(n.get("class_type", "?") for n in graphe.values())),
                   modeles=tuple(_modeles(graphe)), releve=releve,
                   verifications=verifications, candidat=candidat)


# ═══════════════════  Le graphe CANDIDAT — `PLAN-30` L30.1  ═══════════════════

def lignes_candidat(candidat: dict) -> list[str]:
    """Ce qu'un graphe candidat annonce de lui-même, en tête de son rapport."""
    sortie = [f"  ⚑ GRAPHE CANDIDAT ({candidat.get('plan') or 'sans plan'}) — canal "
              f"« {candidat.get('canal') or '?'} », NON LIVRÉ.",
              f"      motif : {candidat.get('motif') or 'non écrit'}"]
    for poids in (candidat.get("poids") or []):
        if not isinstance(poids, dict):
            continue
        sortie += [f"      poids : {poids.get('fichier')} → {poids.get('dossier')}",
                   f"              {poids.get('source')} · licence {poids.get('licence')} "
                   f"vérifiée le {poids.get('licence_verifiee_le') or '(non datée)'}",
                   f"              sha256 : {poids.get('sha256')}"]
    if candidat.get("abandon"):
        sortie.append(f"      abandon : {candidat['abandon']}")
    return sortie


def _retrograder(constats: list, candidat: dict) -> list:
    """Sur un graphe candidat, un nœud ou un poids absent est une **réserve**, pas un refus.

    ⚠ **Sans cette rétrogradation, `tools/comfy.py --valider` sans argument passerait en ROUGE
    sur toute machine du monde**, y compris celles où rien ne va mal : il valide les graphes du
    dossier, et le dépôt en livre désormais un dont le poids n'est installé nulle part. Un
    diagnostic qui crie sur un état normal est le faux avertissement que `core/config_schema.py`
    décrit en tête — « pire que pas de vérification du tout ».

    ⚠ **Et le constat n'est PAS effacé** : il reste, avec son message et sa correction, plus
    une phrase qui dit d'où vient l'anomalie. Un lecteur qui VEUT installer le candidat a
    besoin de ces lignes — c'est sa liste de courses.

    ⚠ **Seuls les codes de `CODES_CANDIDAT` sont rétrogradés.** Un graphe candidat mal formé,
    sans canal, ou incohérent en pas/guidage reste refusé comme un autre : ces défauts-là ne
    viennent pas de la machine, ils viennent du fichier."""
    if not candidat:
        return constats
    sortie = []
    motif = candidat.get("motif") or ""
    for constat in constats:
        if constat.gravite != "refus" or constat.code not in CODES_CANDIDAT:
            sortie.append(constat)
            continue
        note = (f"⚑ Ce graphe est un CANDIDAT non installé : {motif} Tant que "
                f"illustration.comfyui.workflow ne le désigne pas, cette ligne ne décrit "
                f"AUCUNE panne de ta machine.")
        sortie.append(Constat(constat.code, "réserve", constat.quoi,
                              (constat.correction + "\n" if constat.correction else "")
                              + note))
    return sortie


def _canaux_exiges(moteur, verifications: dict) -> list[Constat]:
    """Les canaux **sans lesquels ce graphe ne s'exécute pas** — la réciproque du refus.

    Un graphe qui place un nœud en série sur le chemin du modèle ne dégrade pas : le nœud
    élagué emporte le modèle du `KSampler`. Le graphe le déclare (`_candidat.exige`), le moteur
    refuse avant le GPU (`moteur.CanalExige`), et le validateur le **dit ici** — avant même
    qu'une requête existe."""
    exiges = tuple(getattr(moteur, "CANAUX_EXIGES", ()) or ())
    if not exiges:
        return []
    noms = ", ".join(exiges)
    verifications["canaux exigés"] = f"⚠ {noms}"
    return [Constat(
        "canal_exige", "réserve",
        f"ce graphe EXIGE le(s) canal(aux) : {noms}.",
        "une requête qui ne le porte pas est refusée AVANT le GPU, pas exécutée à moitié. "
        "Renseigne le champ correspondant sous `canaux:` dans requete.yaml.")]


# ═══════════════════════════  Vérification 2 — les nœuds  ═══════════════════════════

def _noeuds_absents(graphe: dict, releve, verifications: dict) -> list[Constat]:
    if releve is None or not releve.joignable:
        verifications["nœuds exposés"] = ("· NON FAIT — serveur injoignable ; ce n'est pas "
                                          "« aucun nœud manquant », c'est « on ne sait pas »")
        return []
    manquants = sorted({str(noeud.get("class_type") or "")
                        for noeud in graphe.values()} - set(releve.noeuds) - {""})
    if not manquants:
        verifications["nœuds exposés"] = (f"✓ les {len(graphe)} nœuds du graphe existent sur "
                                          f"{releve.base_url}")
        return []
    verifications["nœuds exposés"] = f"✗ {len(manquants)} nœud(s) absent(s) du serveur"
    return [Constat(
        "noeud_absent", "refus",
        f"le nœud « {nom} » n'existe pas sur {releve.base_url}.",
        _remede_noeud(nom, releve)) for nom in manquants]


def _remede_noeud(nom: str, releve) -> str:
    proches = difflib.get_close_matches(nom, sorted(releve.noeuds), n=3, cutoff=0.7)
    remede = ("installe le nœud tiers qui le fournit (ComfyUI-Manager, ou `git clone` dans "
              "custom_nodes/ puis REDÉMARRE le serveur — §7 de docs/procedures/comfyui.md), "
              "ou remplace-le dans le graphe.")
    if proches:
        remede += f"\nCe serveur expose des noms proches : {', '.join(proches)}."
    return remede


# ═══════════════════════  Vérification 3 — les fichiers nommés  ═══════════════════════

def _fichiers_absents(graphe: dict, releve, verifications: dict) -> list[Constat]:
    """Chaque valeur écrite dans le graphe est-elle dans la liste que le nœud expose ?

    ⚠ **La règle est celle de ComfyUI, pas une liste de champs recopiée.** Un champ dont
    `/object_info` donne une liste de choix est une liste déroulante : le serveur REFUSE toute
    autre valeur. On compare donc à ce que le nœud expose, quel que soit le nom du champ — ce
    qui attrape `ModelPatchLoader.name` aussi bien que `unet_name`, alors qu'une liste écrite
    à la main aurait raté le premier. `CHAMPS_FICHIER` ne sert plus qu'à choisir le **mot** du
    message : « modèle » quand c'en est un, « valeur » sinon.

    ⚠ **Un marqueur non substitué n'est pas un fichier absent.** `%reference_1%` sera remplacé
    par le nom d'une image téléversée au moment de générer ; le compter comme manquant ferait
    refuser le seul graphe du dépôt qui porte des références."""
    if releve is None or not releve.joignable:
        verifications["fichiers et listes"] = "· NON FAIT — serveur injoignable"
        return []
    constats: list[Constat] = []
    verifies = 0
    for noeud in graphe.values():
        classe = str(noeud.get("class_type") or "")
        for champ, valeur in (noeud.get("inputs") or {}).items():
            if not isinstance(valeur, str) or not valeur.strip() or "%" in valeur:
                continue
            liste = releve.liste(classe, champ)
            if liste is None:
                continue
            verifies += 1
            if valeur in liste:
                continue
            fichier = champ in CHAMPS_FICHIER
            constats.append(Constat(
                "modele_absent" if fichier else "valeur_absente", "refus",
                f"{classe}.{champ} {'nomme' if fichier else 'vaut'} « {valeur} », qui n'est "
                f"pas dans la liste de ce nœud ({len(liste)} entrée(s) exposée(s)).",
                _remede_fichier(valeur, liste, fichier=fichier)))
    verifications["fichiers et listes"] = (
        f"✓ {verifies} valeur(s) vérifiée(s) dans les listes du serveur"
        if not constats else f"✗ {len(constats)} valeur(s) introuvable(s) sur le serveur")
    return constats


def _remede_fichier(valeur: str, liste, *, fichier: bool = True) -> str:
    proches = difflib.get_close_matches(valeur, list(liste), n=3, cutoff=0.6)
    if proches:
        return ("colle l'une de ces valeurs, que le serveur expose vraiment :\n"
                + "\n".join(f"  {nom}" for nom in proches))
    if not liste:
        return ("ce nœud n'expose AUCUN fichier : son dossier de modèles est vide ou mal "
                "rangé. Voir §2 de docs/procedures/comfyui.md, puis REDÉMARRE le serveur — "
                "ComfyUI ne relit ses dossiers qu'au démarrage.")
    if not fichier:
        return ("ce nœud n'accepte que les valeurs de sa liste : "
                + ", ".join(list(liste)[:8]) + ("…" if len(liste) > 8 else "")
                + ".\nUn nom de sampler ou de scheduler change parfois d'une version de "
                  "ComfyUI à l'autre : c'est ce que ce contrôle attrape.")
    return ("place le fichier dans le bon dossier de modèles (§2 de "
            "docs/procedures/comfyui.md), REDÉMARRE le serveur, puis relance ce contrôle.")


# ═══════════════════════════  Vérification 4 — les canaux  ═══════════════════════════

def _canaux(moteur, verifications: dict) -> list[Constat]:
    """Les canaux que ce graphe déclare — **la même lecture que `MARQUEURS`, réutilisée**.

    Rien n'est recopié ici : `CANAUX_SUPPORTES` est calculé par le client, à partir des nœuds
    du graphe et non de son texte brut. Un second lecteur de marqueurs aurait divergé du
    premier au premier canal ajouté."""
    supportes = ", ".join(sorted(moteur.CANAUX_SUPPORTES)) or "(aucun)"
    verifications["canaux déclarés"] = f"✓ {supportes}"
    if moteur.CANAUX_SUPPORTES:
        return []
    return [Constat(
        "aucun_canal", "réserve",
        "ce graphe ne porte aucun marqueur : ni %prompt%, ni %graine%, ni référence.",
        "il partira tel quel et produira toujours la même image. Place au moins %prompt% "
        "dans le nœud d'encodage de texte et %graine% dans le KSampler.")]


# ═════════════════════  Vérification 5 — la cohérence pas / guidage  ═════════════════════

def _pas_et_guidage(graphe: dict, pas, guidage, verifications: dict) -> list[Constat]:
    """La seule vérification dont l'échec ne produit **aucun message** côté ComfyUI.

    Une LoRA distillée est entraînée à débruiter sans guidage ; lui en donner produit des
    images brûlées et saturées — première ligne du §9 de la procédure, mesurée le 2026-08-29.
    ComfyUI ne dit rien : il exécute, et l'image sort."""
    distillees = sorted({str(valeur) for noeud in graphe.values()
                         for champ, valeur in (noeud.get("inputs") or {}).items()
                         if champ == "lora_name" and isinstance(valeur, str)
                         and any(m in valeur.casefold() for m in LORAS_DISTILLEES)})
    if not distillees:
        verifications["pas / guidage"] = "✓ aucune LoRA distillée dans ce graphe"
        return _pas_et_guidage_fixes(graphe, pas, guidage)
    constats: list[Constat] = []
    if guidage is not None and float(guidage) > GUIDAGE_MAX_DISTILLE:
        constats.append(Constat(
            "guidage_incoherent", "refus",
            f"ce graphe charge une LoRA distillée ({distillees[0]}) et le guidage demandé "
            f"est {float(guidage):g}.",
            f"mets illustration.image.guidage à 1.0 (et pas à 4). Une LoRA distillée en "
            f"quelques pas est entraînée SANS guidage : au-dessus de "
            f"{GUIDAGE_MAX_DISTILLE:g}, elle produit des images brûlées, aux contrastes "
            f"saturés — et ComfyUI ne dit RIEN. Mesuré le 2026-08-29, §9 de "
            f"docs/procedures/comfyui.md."))
    if pas is not None and int(pas) > PAS_MAX_DISTILLE:
        constats.append(Constat(
            "pas_inutiles", "réserve",
            f"ce graphe charge une LoRA 4 pas et le nombre de pas demandé est {int(pas)}.",
            f"mets illustration.image.pas à 4. Au-delà de {PAS_MAX_DISTILLE}, tu paies du "
            f"calcul qui n'achète rien : mesuré au lot 25, passer de 4 à 50 pas n'a réduit "
            f"l'écart de style que de 24 % pour 12,5 fois plus de temps."))
    fixes = _pas_et_guidage_fixes(graphe, pas, guidage)
    verifications["pas / guidage"] = (
        f"✗ {len(constats)} incohérence(s) avec {distillees[0]}" if constats
        else f"⚠ compatible avec {distillees[0]}, mais {len(fixes)} valeur(s) fixée(s) dans "
             f"le graphe" if fixes
        else f"✓ compatible avec {distillees[0]}")
    return constats + fixes


def _pas_et_guidage_fixes(graphe: dict, pas, guidage) -> list[Constat]:
    """Un graphe qui FIXE ses pas au lieu de porter `%pas%` rend la clé de config sans effet.

    ⚠ C'est une réserve et pas un refus : fixer une valeur dans le graphe est un choix
    légitime. Ce qui ne l'est pas, c'est de croire la régler dans `config.yaml`."""
    constats = []
    for marqueur, nom, valeur in (("%pas%", "pas", pas), ("%guidage%", "guidage", guidage)):
        if valeur is None:
            continue
        fixe = [str(n.get("class_type") or "?") for n in graphe.values()
                for champ, v in (n.get("inputs") or {}).items()
                if champ in ("steps", "cfg") and not isinstance(v, list)
                and str(v) != marqueur and _champ_de(champ) == nom]
        if fixe:
            constats.append(Constat(
                f"{nom}_fixe", "réserve",
                f"ce graphe fixe « {nom} » dans {fixe[0]} au lieu de porter {marqueur}.",
                f"illustration.image.{nom} est donc SANS EFFET sur ce workflow. Mets "
                f"{marqueur} dans le champ du nœud, ou règle la valeur dans le graphe et "
                f"sache que la config ne la commande pas."))
    return constats


def _champ_de(champ: str) -> str:
    return {"steps": "pas", "cfg": "guidage"}.get(champ, champ)


def _modeles(graphe: dict) -> list[str]:
    from illustration.comfyui import modeles_du_graphe

    return modeles_du_graphe(graphe)


# ═══════════  Vérification 6 — la copie non marquée — `PLAN-30` L30.3  ═══════════

def _sortie_du_graphe(graphe: dict, verifications: dict) -> list[Constat]:
    """Où atterrit l'image que ComfyUI écrit **en plus** de celle qu'Angelith marque.

    ## Le fait n'est pas nouveau — il était seulement invisible au moment de valider

    `SaveImage` écrit un PNG dans le dossier `output/` de ComfyUI. Angelith récupère l'image
    par `/view`, la **marque** (bloc `tEXt` + sidecar de provenance) et l'écrit sous
    `build/<Projet>/<Tome>/illustrations/`. La copie de ComfyUI, elle, ne porte **ni bloc
    `tEXt` ni sidecar** : une image de synthèse non marquée, sur le disque, hors de toute
    trace, au moment même où le dépôt fait du marquage un défaut sans interrupteur
    (AI Act art. 50(2)).

    La lecture du dépôt reste celle du `PLAN-24`, et elle est défendable : « la frontière
    d'écriture d'Angelith couvre SES écritures, pas celles d'un programme tiers que
    l'utilisateur a lancé lui-même ». Elle n'était simplement dite nulle part **au moment de
    valider** — d'où cette réserve, qui ne refuse rien et ne change aucun défaut.

    ## Les trois sorties, et ce que chacune coûte au client

    | Nœud | La copie | Ce que ce client doit changer |
    |---|---|---|
    | `SaveImage` | `output/`, **permanente** | rien — c'est l'état livré |
    | `PreviewImage` | `temp/`, **vidée au redémarrage** de ComfyUI | rien : `/view` sert déjà le `type` que l'historique donne |
    | `SaveImageWebsocket` | aucune | **tout** : l'image ne passe plus par `/history` |

    ⚠ **`SaveImageWebsocket` est un REFUS et non une réserve, et le motif est mécanique, pas
    doctrinal** : ce client récupère l'image par `GET /history/<id>` puis `GET /view`. Ce nœud
    ne publie rien dans l'historique — il pousse les octets sur la connexion WebSocket, que ce
    client n'ouvre pas. Un graphe qui le porte s'exécuterait, occuperait la carte plusieurs
    minutes, puis échouerait sur « n'a produit aucune image ». Le dire avant coûte zéro
    seconde de GPU. C'est la réponse du `PLAN-30` L30.3, et elle est écrite ici parce que
    c'est ici qu'on la lit au bon moment."""
    sorties = sorted({str(n.get("class_type") or "") for n in graphe.values()
                      if str(n.get("class_type") or "") in SORTIES_RECUPERABLES})
    if "SaveImageWebsocket" in sorties:
        verifications["sortie du graphe"] = ("✗ SaveImageWebsocket — ce client ne "
                                             "l'exploite pas")
        return [Constat(
            "sortie_websocket", "refus",
            "ce graphe sort par SaveImageWebsocket ; ce client récupère l'image par "
            "GET /history puis GET /view.",
            "remplace-le par PreviewImage (copie dans temp/, vidée au redémarrage de ComfyUI) "
            "ou par SaveImage (copie permanente dans output/). Le nœud WebSocket ne publie "
            "RIEN dans l'historique : le run occuperait la carte, puis échouerait sur « le "
            "workflow s'est exécuté mais n'a produit aucune image ».")]
    if not sorties:
        verifications["sortie du graphe"] = "✗ aucun nœud de sortie récupérable"
        return [Constat(
            "sortie_absente", "refus",
            "ce graphe ne porte ni SaveImage ni PreviewImage.",
            "ajoute l'un des deux en bout de chaîne : sans lui, ComfyUI exécute le graphe et "
            "ne publie aucune image dans /history.")]
    if sorties == ["PreviewImage"]:
        verifications["sortie du graphe"] = ("✓ PreviewImage — la copie de ComfyUI va dans "
                                             "temp/, vidée à son redémarrage")
        return []
    verifications["sortie du graphe"] = ("⚠ " + ", ".join(sorties)
                                         + " — copie non marquée dans output/")
    return [Constat(
        "copie_non_marquee", "réserve",
        "SaveImage laisse dans le dossier output/ de ComfyUI une copie de l'image qui ne "
        "porte NI bloc tEXt NI sidecar de provenance.",
        "état livré et assumé — la frontière d'Angelith couvre SES écritures, pas celles d'un "
        "programme tiers. Pour réduire la surface sans changer une ligne du client : "
        "PreviewImage à la place, qui écrit dans temp/ (vidé au redémarrage de ComfyUI). "
        "Motifs et réserves : illustration/workflows/README.md.")]


# ═══════════════════════════  La VRAM, avant le déchargement  ═══════════════════════════

def verifier_vram(releve, *, pic_octets: int = PIC_VRAM_OCTETS) -> list[Constat]:
    """La carte a-t-elle la place ? **Dit avant de décharger le LLM, pas après** — L28.2.

    ⚠ **Deux lectures, et la seconde évite un faux avertissement quotidien.** Après un run,
    ComfyUI garde 12 083 Mio résidents : le « libre » tombe alors bien sous le pic, alors que
    relancer le même graphe ne recharge rien. On compare donc au **libre + ce que PyTorch a
    déjà réservé**, qui est ce que la génération peut réellement occuper, et on ne parle de
    refus que si même ce total ne suffit pas.

    ⚠ **Le pic est celui d'UNE pile**, daté 2026-08-29, graphe Lightning, RX 7900 XT. Sur une
    autre carte il ne veut rien dire — d'où une réserve, jamais un refus, quand la marge est
    juste."""
    if releve is None or not releve.joignable:
        return []
    appareil = releve.appareil_principal
    if appareil is None or not appareil.vram_total:
        return []
    if appareil.marge_octets >= pic_octets:
        return []
    if appareil.vram_libre >= pic_octets:
        return []
    manque = mio(pic_octets - appareil.marge_octets)
    return [Constat(
        "vram_courte",
        "refus" if appareil.vram_total < pic_octets else "réserve",
        f"la carte offre {mio(appareil.marge_octets)} Mio "
        f"({mio(appareil.vram_libre)} libres + {mio(appareil.torch_total)} réservés par "
        f"PyTorch, récupérables) ; le pic mesuré le 2026-08-29 sur le graphe Lightning est de "
        f"{mio(pic_octets)} Mio. Il manque {manque} Mio.",
        "libère la carte AVANT de lancer : ferme ce qui l'occupe, ou POST /free sur ComfyUI "
        "(⚠ il segfaute environ une fois sur sept, §5 de docs/procedures/comfyui.md).\n"
        "Si ta carte est plus petite que celle de la mesure, ce chiffre ne te concerne pas "
        "tel quel : c'est un pic relevé sur une RX 7900 XT de 20 464 Mio, pas une exigence "
        "du modèle.")]
