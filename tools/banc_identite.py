#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc de l'IDENTITÉ (`PLAN-25` L25.4) — étalonner le juge, puis balayer la voie A.

    # Étape 0.2 : les cinq planchers. Aucune image générée, aucun GPU.
    python tools/banc_identite.py "roman S" --etalonnage --markdown

    # Les huit prétraitements du juge, mis en concurrence sur le corpus réel.
    python tools/banc_identite.py "roman S" --juge-variantes

    # L25.1 : le balayage. Il GÉNÈRE des images — moteur réel, marqueurs `modeles` et `lent`.
    python tools/banc_identite.py "roman S" Vol.1 --personnage "Tory Noelle" --balayage

    # Tout, en un document publiable.
    python tools/banc_identite.py "roman S" Vol.1 --tous --markdown > docs/mesures/identite.md

## Pourquoi un banc à part, et pas une colonne de `tools/banc.py`

`tools/banc.py` lit les caches et ne charge aucun modèle : c'est sa discipline, et elle vaut
d'être gardée. Ce banc-ci charge un encodeur ONNX de 347 Mo, et, en `--balayage`, un
transformeur de 12,8 Go — plus il **écrit des images**. Les deux contrats ne tiennent pas dans
le même outil sans mentir sur l'un des deux. C'est la même raison qui a fait naître
`tools/banc_candidats.py` au lot 16.

## Ce que ce banc mesure, et l'ordre est celui du plan

1. **Le corpus** — combien de personnages, combien de références, et la distribution. C'est le
   dénominateur de tout le reste, et il est publié avant le premier chiffre ;
2. **les cinq planchers de l'étape 0.2** — trois pour l'IDENTITÉ, deux pour le STYLE. Deux
   échelles, une seule métrique : les confondre est l'erreur que le plan nomme ;
3. **le verdict d'utilisabilité du juge** — si l'écart « même personnage » / « personnages
   différents » ne dépasse pas le bruit, le juge est déclaré inutilisable et on le dit ;
4. **le balayage** de L25.1 — un paramètre à la fois, avec les **trois** grandeurs côte à côte,
   y compris les configurations perdantes.

⚠ **Il ne remplace pas le juge humain.** Le protocole en aveugle de l'étape 0.3 — 20 triplets,
sans étiquette — est un geste humain, et ce banc ne peut que **préparer** ses triplets
(`--triplets`). Un banc qui prétendrait rendre ce verdict-là mentirait sur ce qu'il mesure.

## Ce qu'il n'écrit pas

Rien sous `build/` en mode `--etalonnage` ou `--juge-variantes` : ils lisent des pixels et
rendent des nombres. En `--balayage`, il écrit **uniquement** sous
`build/<Projet>/<Tome>/illustrations/balayage/`, et le périmètre de `illustration/frontiere.py`
est armé pour le vérifier à l'exécution.
"""
from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from core import bible as bible_mod                             # noqa: E402
from core import illustrations as illus_mod                     # noqa: E402
from core.cli import charger_config, configurer_stdout          # noqa: E402
from illustration import attente as attente_mod                 # noqa: E402
from illustration import gabarits as gabarits_mod               # noqa: E402
from illustration import identite as ident_mod                  # noqa: E402
from illustration import juge as juge_mod                       # noqa: E402
from tools._banc_commun import (cellule, commit_courant,        # noqa: E402
                                empreinte_config, tableau_markdown)

#: Le corpus de contrôle négatif par défaut. **`Pride and Prejudice` est du domaine public**,
#: et c'est la seule œuvre du dépôt dont une image aurait le droit de figurer dans un document
#: de mesure (`README-ILLUSTRATION-23-27` §5). Pour toutes les autres, on publie des chiffres.
AUTRE_OEUVRE = "Pride and Prejudice"

#: Nombre de références balayées. `REFERENCES_MAX` est le maximum du graphe livré.
NOMBRES_REFERENCES = (1, 2, 3)

#: Les trois forces de conditionnement balayées. Sur la LoRA Lightning, le guidage libre de
#: classifieur est distillé : `cfg` y est **inopérant** au-delà de 1,0 et brûle l'image. La
#: force qui reste réglable est donc le **nombre de pas**, qui décide de combien le modèle
#: s'éloigne du bruit initial — et le plan demande trois valeurs, pas une.
FORCES = ((4, 1.0), (6, 1.0), (8, 1.0))

#: Sous-dossier des images du balayage.
DOSSIER_BALAYAGE = "balayage"


# ─────────────────────────────────  Le corpus  ─────────────────────────────────

@dataclass
class Personnage:
    nom: str
    references: list = field(default_factory=list)
    genre_confirme: str = ""
    valide_par_humain: bool = False

    @property
    def validees(self) -> list:
        return [r for r in self.references if r.validee]


@dataclass
class Corpus:
    """Ce sur quoi le banc mesure — et **son dénominateur, publié avant tout chiffre**."""

    projet: str
    racine: Path
    personnages: list = field(default_factory=list)
    ancrages: list = field(default_factory=list)
    signature: dict = field(default_factory=dict)
    autres: list = field(default_factory=list)
    autre_oeuvre: str = ""
    illustrations_tome: list = field(default_factory=list)
    tome: str = ""

    @property
    def avec_reference(self) -> list:
        return [p for p in self.personnages if p.validees]

    @property
    def distribution(self) -> dict:
        """`{nombre de références validées: nombre de personnages}`."""
        compte: dict[int, int] = {}
        for p in self.personnages:
            compte[len(p.validees)] = compte.get(len(p.validees), 0) + 1
        return dict(sorted(compte.items()))

    def exigences_du_plan(self) -> list[str]:
        """Les écarts entre ce que l'étape 0.1 demande et ce que le corpus porte.

        Liste vide = le corpus satisfait le plan. **Sinon, ces lignes sont publiées telles
        quelles** : le plan écrit « Dites-le, ne le contournez pas »."""
        ecarts = []
        avec = self.avec_reference
        if len(avec) < 8:
            ecarts.append(f"le plan demande **8 personnages** au minimum ; le corpus en porte "
                          f"**{len(avec)}** avec au moins une référence validée")
        seules = [p for p in avec if len(p.validees) == 1]
        if len(seules) < 2:
            ecarts.append(f"le plan demande au moins **2 personnages à une seule référence** ; "
                          f"le corpus en porte **{len(seules)}**")
        riches = [p for p in avec if len(p.validees) >= 3]
        if len(riches) < 2:
            ecarts.append(f"le plan demande au moins **2 personnages à trois références ou "
                          f"plus** ; le corpus en porte **{len(riches)}**")
        if len(avec) > 0 and len({len(p.validees) for p in avec}) == 1:
            ecarts.append("tous les personnages référencés ont le même nombre de références : "
                          "la distribution ne dit rien")
        return ecarts


def lire_corpus(projet: str, config: dict, *, tome: str = "",
                autre_oeuvre: str = AUTRE_OEUVRE) -> Corpus:
    """Assemble le corpus depuis la bible et `build/`. Ne charge aucun modèle."""
    build = Path(config["chemins"]["build"])
    sources = Path(config["chemins"]["sources"])
    racine = build / projet
    doc = bible_mod.load(bible_mod.chemin(sources / projet))

    personnages = []
    for entree in doc.get("personnages") or []:
        nom = str(entree.get("nom") or "")
        personnages.append(Personnage(
            nom=nom, references=ident_mod.references_de(doc, nom, racine),
            genre_confirme=str(entree.get("genre_confirme") or ""),
            valide_par_humain=bool(entree.get("valide_par_humain"))))

    ancrages = []
    for ancrage in (doc.get("style") or {}).get("ancrages") or []:
        chemin = ident_mod.resoudre(str(ancrage.get("fichier") or ""), racine)
        if chemin is not None and bool(ancrage.get("valide_par_humain")):
            ancrages.append(chemin)

    dossier_tome = racine / tome if tome else None
    illus = []
    if dossier_tome is not None and dossier_tome.is_dir():
        illus = [i.chemin for i in illus_mod.inventaire_rattache(dossier_tome)
                 if illus_mod.exploitable(i)]

    autres = []
    autre_racine = build / autre_oeuvre
    if autre_racine.is_dir():
        for volume in sorted(p for p in autre_racine.iterdir() if p.is_dir()):
            autres.extend(i.chemin for i in illus_mod.inventaire(volume)
                          if illus_mod.exploitable(i))

    return Corpus(projet=projet, racine=racine, personnages=personnages, ancrages=ancrages,
                  signature=(doc.get("style") or {}).get("signature") or {},
                  autres=autres, autre_oeuvre=autre_oeuvre,
                  illustrations_tome=illus, tome=tome)


# ────────────────────────  Étape 0.2 — les cinq planchers  ────────────────────────

#: Combien de paires au plus par population. Les populations de style se comptent en milliers
#: de paires (`C(239, 2)`) ; en encoder 239 coûte 100 s, mais publier une médiane sur 28 441
#: paires quand 400 suffisent à la stabiliser est du temps de calcul sans information.
PAIRES_MAX = 400


def etalonner(encodeur, corpus: Corpus, *, paires_max: int = PAIRES_MAX) -> dict:
    """Les cinq populations de l'étape 0.2. Rend `{nom: Echelle}` plus deux détails.

    ⚠ **Une paire dont les deux images sont le MÊME FICHIER est comptée à part**, jamais dans
    la population. Sur le corpus réel, deux personnages partagent une illustration de groupe :
    leur paire de « confusion » vaudrait exactement 1,0 et tirerait la médiane vers le haut
    pour une raison qui n'a rien à voir avec la ressemblance. C'est aussi la réponse à la
    question que le plan pose au critère 8 — « que se passe-t-il pour un personnage secondaire
    qui n'apparaît que dans une image de groupe ? »"""
    import random

    echelles = {nom: juge_mod.Echelle(nom) for nom, _ in juge_mod.PAIRES}
    partages: list[tuple[str, str, str]] = []

    vecteurs: dict[str, object] = {}

    def vecteur(chemin):
        cle = str(Path(chemin).resolve())
        if cle not in vecteurs:
            vecteurs[cle] = encodeur.encoder(chemin)
        return vecteurs[cle]

    avec = corpus.avec_reference

    # 1 — deux références du MÊME personnage
    for personnage in avec:
        for a, b in itertools.combinations(personnage.validees, 2):
            if a.source == b.source:
                continue
            echelles["identite_haut"].valeurs.append(
                juge_mod.cosinus(vecteur(a.source), vecteur(b.source)))

    # 2 — deux personnages DIFFÉRENTS de la même œuvre
    for p1, p2 in itertools.combinations(avec, 2):
        for a in p1.validees:
            for b in p2.validees:
                if a.source == b.source:
                    partages.append((p1.nom, p2.nom, a.fichier))
                    continue
                echelles["identite_confusion"].valeurs.append(
                    juge_mod.cosinus(vecteur(a.source), vecteur(b.source)))

    alea = random.Random(20260829)                 # une graine fixe : le banc est reproductible

    # 3 — une référence contre une image d'une AUTRE œuvre
    if corpus.autres:
        toutes = [r.source for p in avec for r in p.validees]
        couples = [(a, b) for a in toutes for b in corpus.autres]
        for a, b in _echantillon(couples, paires_max, alea):
            echelles["identite_negatif"].valeurs.append(
                juge_mod.cosinus(vecteur(a), vecteur(b)))

    # 4 — deux illustrations quelconques du MÊME tome : l'échelle de STYLE
    couples = list(itertools.combinations(corpus.illustrations_tome, 2))
    for a, b in _echantillon(couples, paires_max, alea):
        echelles["style_haut"].valeurs.append(juge_mod.cosinus(vecteur(a), vecteur(b)))

    # 5 — une illustration du tome contre une illustration d'une AUTRE œuvre
    if corpus.autres and corpus.illustrations_tome:
        couples = [(a, b) for a in corpus.illustrations_tome for b in corpus.autres]
        for a, b in _echantillon(couples, paires_max, alea):
            echelles["style_bas"].valeurs.append(juge_mod.cosinus(vecteur(a), vecteur(b)))

    utilisable, motif = juge_mod.juge_utilisable(echelles["identite_haut"],
                                                 echelles["identite_confusion"])
    utilisable_style, motif_style = juge_mod.juge_utilisable(
        echelles["style_haut"], echelles["style_bas"],
        libelles=("deux illustrations du même tome", "une illustration d'une autre œuvre"))
    return {"echelles": echelles, "partages": partages,
            "images_encodees": len(vecteurs),
            "identite": {"utilisable": utilisable, "motif": motif},
            "style": {"utilisable": utilisable_style, "motif": motif_style},
            "planchers": planchers_de(echelles, utilisable)}


def _echantillon(couples: list, limite: int, alea) -> list:
    """Au plus `limite` couples, tirés **avec une graine fixe** : deux exécutions du banc
    doivent publier les mêmes nombres, sinon le tableau ne se compare pas au suivant."""
    if len(couples) <= limite:
        return couples
    return alea.sample(couples, limite)


def planchers_de(echelles: dict, utilisable: bool) -> ident_mod.Planchers:
    """Les seuils du garde-fou, **dérivés de l'étalonnage** et de rien d'autre.

    - `confusion` : la médiane de « deux personnages différents ». Sous elle, une image ne
      ressemble pas plus au personnage que deux personnages de la même œuvre ne se
      ressemblent — c'est la définition du plancher, pas un choix ;
    - `nouveaute` : `1 − max(identité haut)`. Au-dessus de ce cosinus, l'image générée est
      plus proche de sa référence que ne le sont deux pages RÉELLES du même personnage : ce
      n'est plus une illustration, c'est une reproduction ;
    - `style_descripteurs` : **non dérivable de l'étalonnage d'embedding**, et laissé à `None`
      ici. Il se règle par `illustration.identite.planchers.style_descripteurs` et il est livré désarmé —
      cf. `illustration/identite.py`."""
    haut, confusion = echelles["identite_haut"], echelles["identite_confusion"]
    return ident_mod.Planchers(
        confusion=confusion.mediane,
        nouveaute=(1.0 - haut.maxi) if haut.maxi is not None else None,
        style_descripteurs=None, juge_utilisable=utilisable)


# ─────────────────────  Les huit prétraitements, mis en concurrence  ─────────────────────

def juge_variantes(corpus: Corpus, chemin_encodeur, *, paires_max: int = PAIRES_MAX) -> list:
    """Compare les prétraitements du juge sur le corpus RÉEL, et publie les perdants.

    ⚠ C'est l'étape que le plan appelle « étalonnez le juge avant de l'utiliser », poussée
    d'un cran : on n'étalonne pas seulement les graduations, on choisit l'instrument. Le
    critère est **l'écart entre les deux médianes d'identité rapporté au bruit** — pas
    l'écart brut : un prétraitement qui écarte les médianes en dispersant autant n'a rien
    gagné."""
    lignes = []
    for cadrage, cote, agregation in itertools.product(
            juge_mod.CADRAGES, (224, 448), juge_mod.AGREGATIONS):
        encodeur = juge_mod.Encodeur(chemin_encodeur, agregation=agregation,
                                     cadrage=cadrage, cote=cote)
        resultat = etalonner(encodeur, corpus, paires_max=min(paires_max, 60))
        haut = resultat["echelles"]["identite_haut"]
        confusion = resultat["echelles"]["identite_confusion"]
        bruit = confusion.ecart_type
        ecart = ((haut.mediane - confusion.mediane)
                 if haut.mediane is not None and confusion.mediane is not None else None)
        lignes.append({
            "cadrage": cadrage, "côté": cote, "agrégation": agregation,
            "même personnage": haut.mediane, "personnages ≠": confusion.mediane,
            "écart": ecart, "bruit": bruit,
            "écart / bruit": (ecart / bruit) if (ecart is not None and bruit) else None,
        })
    return lignes


# ────────────────────────────  L25.1 — le balayage  ────────────────────────────

@dataclass
class Configuration:
    """Un point du balayage. **Un paramètre à la fois** — la discipline de
    `tools/apercu_detection.py --balayage`."""

    axe: str
    references: int
    pas: int
    guidage: float
    #: La variante de décor du gabarit — `PLAN-29` L29.4. `DECOR_DEFAUT` sur tous les axes
    #: sauf le sien : c'est la discipline « un paramètre à la fois ».
    decor: str = gabarits_mod.DECOR_DEFAUT
    #: L'image de contrôle — `PLAN-30` L30.2. Chaîne vide sur tous les axes sauf le sien,
    #: même discipline que `decor`.
    #:
    #: ⚠ **Un canal n'est PAS un paramètre comme un autre, et l'axe le dit** : il exige un
    #: graphe qui le porte. `illustration.comfyui.workflow` doit désigner le graphe candidat,
    #: sinon le moteur refuse — avec son motif, et avant le GPU. C'est voulu : un balayage qui
    #: aurait silencieusement jeté l'image de contrôle aurait publié quatre grandeurs
    #: identiques sous deux étiquettes différentes.
    controle: str = ""

    @property
    def nom(self) -> str:
        """Le nom du fichier, et il est aussi l'étiquette de configuration du protocole en
        aveugle (`tools/juge_humain.py`).

        ⚠ **Le décor n'entre dans le nom que s'il n'est PAS le défaut.** Un balayage lancé sans
        `--decors` écrit donc exactement les mêmes noms qu'avant le lot 29 : deux séries
        mesurées à six mois d'écart restent comparables fichier par fichier, et un document de
        mesure publié ne renvoie pas à des noms qui n'existent plus. Les configurations de
        l'axe `decor` restent distinctes par leur axe, qui est en tête."""
        base = f"{self.axe}-r{self.references}-p{self.pas}-g{self.guidage:g}"
        if self.controle:
            base += "-controle"
        return base if self.decor == gabarits_mod.DECOR_DEFAUT else f"{base}-{self.decor}"


def configurations(reference_base: int = 2, *, decors=(),
                   controle: str = "") -> list[Configuration]:
    """Le plan de balayage : deux axes — trois avec `decors` —, croisés en un seul point.

    ⚠ **Un paramètre à la fois**, et l'axe est nommé dans chaque ligne du tableau. Croiser les
    deux axes en entier ferait 9 générations par personnage — au prix mesuré d'une image, cela
    dépasse ce qu'une session peut mesurer, et le plan demande la discipline inverse.

    ⚠ **L'axe `decor` (`PLAN-29` L29.4) est OPTIONNEL et vide par défaut.** Il ne s'ouvre que
    sur demande explicite (`--decors neutre,trame,aucun`), parce qu'il coûte une image de plus
    par variante et que le critère 5 du plan ne demande que de comparer « avec et sans fond
    neutre » — pas de balayer un troisième axe à chaque étalonnage."""
    base_pas, base_guidage = FORCES[0]
    plan = [Configuration("nombre_references", n, base_pas, base_guidage)
            for n in NOMBRES_REFERENCES]
    plan += [Configuration("force", reference_base, pas, guidage)
             for pas, guidage in FORCES[1:]]
    plan += [Configuration("decor", reference_base, base_pas, base_guidage, decor)
             for decor in decors]
    # ⚠ **UN seul point sur l'axe `canal`, et il coûte une image, pas trois.** Le PLAN-30
    # L30.2 ne demande pas de balayer la force du canal : il demande de le comparer à son
    # absence, sur les mêmes descripteurs et le même juge. Le point « sans » existe déjà —
    # c'est `nombre_references` à `reference_base`.
    if controle:
        plan += [Configuration("canal", reference_base, base_pas, base_guidage,
                               controle=controle)]
    return plan


def balayer(moteur, encodeur, corpus: Corpus, personnage: Personnage, *, dossier: Path,
            planchers: ident_mod.Planchers, prompt, largeur: int, hauteur: int,
            graine: int, decors=(), controle: str = "", dire=print) -> list[dict]:
    """Génère une image par configuration et mesure les **trois** grandeurs sur chacune.

    ⚠ Les configurations perdantes sont rendues comme les autres : le critère 3 du plan exige
    « le tableau complet, y compris les configurations perdantes »."""
    import time

    from illustration import frontiere
    from illustration.moteur import Requete

    ident_mod.exiger_references(personnage.references, personnage.nom)

    lignes: list[dict] = []
    with frontiere.perimetre(dossier):
        preparees = ident_mod.preparer_toutes(
            ident_mod.retenir(personnage.references, ident_mod.REFERENCES_MAX),
            personnage.nom, dossier)
        for config in configurations(decors=decors, controle=controle):
            retenues = preparees[:config.references]
            if len(retenues) < config.references:
                lignes.append({"configuration": config.nom, "axe": config.axe,
                               "références": config.references, "décor": config.decor,
                               "canal": Path(config.controle).name if config.controle
                                        else "—",
                               "verdict": "non mesurée — le personnage n'a pas assez de "
                                          "références validées"})
                continue
            # ⚠ Le prompt est reconstruit PAR CONFIGURATION quand `prompt` est un appelable :
            # l'axe `decor` change le texte, et un prompt calculé une fois pour toutes ferait
            # produire trois fois la même phrase sous trois étiquettes différentes.
            texte = prompt(config.decor) if callable(prompt) else prompt
            requete = Requete(
                prompt=ident_mod.prompt_avec_references(texte, len(retenues)),
                references=tuple(str(p.relative_to(dossier)) for p in retenues),
                image_controle=config.controle,
                largeur=largeur, hauteur=hauteur, graine=graine,
                pas=config.pas, guidage=config.guidage)
            depart = time.monotonic()
            sortie = moteur.generer(requete)
            secondes = sortie.secondes or (time.monotonic() - depart)
            image = dossier / f"{config.nom}.png"
            _ecrire_image(sortie, image, requete, personnage.nom)
            grandeurs = juge_mod.mesurer(
                encodeur, image,
                references=[r.source for r in ident_mod.retenir(personnage.references,
                                                                config.references)],
                ancrages=corpus.ancrages, signature_tome=corpus.signature)
            verdict = ident_mod.juger(grandeurs, planchers)
            lignes.append({
                "configuration": config.nom, "axe": config.axe,
                "références": config.references, "pas": config.pas,
                "guidage": config.guidage, "décor": config.decor,
                "canal": Path(config.controle).name if config.controle else "—",
                "secondes": round(secondes, 1),
                "ressemblance": grandeurs.ressemblance, "nouveauté": grandeurs.nouveaute,
                "style (embedding)": grandeurs.style_embedding,
                "style (descripteurs)": grandeurs.style_descripteurs,
                "descripteur qui décroche": grandeurs.descripteur_decroche[0],
                "motifs": " · ".join(verdict.motifs) or "—",
                "image": image, "_grandeurs": grandeurs, "_verdict": verdict})
            dire(f"    {config.nom} : {secondes:.0f} s · ressemblance "
                 f"{cellule(grandeurs.ressemblance)} · nouveauté "
                 f"{cellule(grandeurs.nouveaute)} · style "
                 f"{cellule(grandeurs.style_descripteurs)}")
    return lignes


def _ecrire_image(sortie, destination: Path, requete, personnage: str) -> None:
    """Écrit l'image du balayage **par le chemin marqué**, comme n'importe quelle image de la
    brique. Un banc qui écrirait des PNG nus contournerait le marquage AI Act du lot 24 — et
    c'est exactement ce qui est arrivé au banc du lot 24, dont les 10 images ne portaient rien.
    """
    from illustration import marquage

    provenance = marquage.manifeste(
        requete, sortie, projet="", tome="",
        identifiant=marquage.identifiant_oeuvre("banc-identite", personnage),
        validation={"par": "banc_identite.py",
                    "note": "image de BANC, produite pour mesurer — pas une illustration "
                            "retenue"},
        modele=requete.modele or "(balayage)")
    marquage.ecrire(sortie, destination, provenance=provenance)


# ───────────────────────  Étape 0.3 — préparer les triplets  ───────────────────────

def triplets(lignes: list[dict], *, nombre: int = 20) -> list[dict]:
    """Les triplets `(référence, image A, image B)` du protocole en aveugle, **sans étiquette**.

    ⚠ Ce banc ne rend **aucun verdict** ici : il prépare le matériel et mélange l'ordre avec
    une graine fixe. Le seul juge de l'étape 0.3 est un humain, et le plan le dit sans nuance :
    « c'est lent, c'est irremplaçable, et c'est le seul verdict qui compte »."""
    import random

    alea = random.Random(20260829)
    produites = [ligne for ligne in lignes if ligne.get("image")]
    couples = list(itertools.combinations(produites, 2))
    alea.shuffle(couples)
    sortie = []
    for index, (a, b) in enumerate(couples[:nombre], start=1):
        gauche, droite = (a, b) if alea.random() < 0.5 else (b, a)
        sortie.append({"n": index, "A": Path(gauche["image"]).name,
                       "B": Path(droite["image"]).name,
                       "_config_A": gauche["configuration"],
                       "_config_B": droite["configuration"]})
    return sortie


# ──────────────────────────────  Le rendu Markdown  ──────────────────────────────

def entete(config_path, corpus: Corpus, encodeur_chemin, commande: str,
           reg: dict | None = None) -> list[str]:
    """Ce qui fait d'un tableau une PUBLICATION : sans ces lignes, deux tableaux ne se
    comparent pas — on ne sait pas si l'écart vient du code, de la configuration, du corpus,
    **du modèle d'image ou du juge**. Le `PLAN-25` L25.4 nomme les six."""
    from core.version import __version__

    from illustration.marquage import empreinte_fichier
    chemin = Path(encodeur_chemin)
    empreinte = empreinte_fichier(chemin) if chemin.is_file() else "(absent)"
    reg = reg or {}
    moteur = str(reg.get("moteur") or "(inconnu)")
    workflow = Path(str((reg.get("comfyui") or {}).get("workflow") or "")).name or "(aucun)"
    poids = (reg.get("poids") or {})
    empreinte_poids = str(poids.get("sha256") or "") or "(non renseignée)"
    return [
        "# Banc d'identité — la voie A, mesurée",
        "",
        f"- **Date de mesure** : {date.today().isoformat()}",
        f"- **Commit** : `{commit_courant()}`",
        f"- **Version du dépôt** : {__version__}",
        f"- **`config.yaml`** : sha256 `{empreinte_config(config_path)}`",
        f"- **Moteur d'image** : `{moteur}`, workflow `{workflow}`",
        f"- **Empreinte des poids d'image** : `{empreinte_poids}` — ⚠ les poids du modèle "
        f"d'image sont chargés par ComfyUI, pas par Angelith ; le dépôt ne les empreint que "
        f"si `illustration.poids.sha256` est renseigné",
        f"- **Encodeur du juge** : `{chemin.name}` — sha256 `{empreinte[:16]}…`",
        f"- **Corpus** : projet `{corpus.projet}`"
        + (f", tome `{corpus.tome}`" if corpus.tome else "")
        + f", contrôle négatif `{corpus.autre_oeuvre}` ({len(corpus.autres)} illustrations)",
        "",
        f"> Produit par `{commande}`.",
        "",
    ]


def section_corpus(corpus: Corpus) -> list[str]:
    lignes = ["## Le corpus, avant tout chiffre", ""]
    lignes.append(tableau_markdown(
        ["personnage", "références validées", "genre confirmé", "validé par un humain"],
        [{"personnage": p.nom, "références validées": len(p.validees),
          "genre confirmé": p.genre_confirme or "—",
          "validé par un humain": "oui" if p.valide_par_humain else "non"}
         for p in corpus.personnages]))
    lignes += ["", f"Distribution `{{références: personnages}}` : "
                   f"`{corpus.distribution}`.",
               f"Ancrages de style validés : **{len(corpus.ancrages)}**. "
               f"Illustrations exploitables du tome : **{len(corpus.illustrations_tome)}**.",
               f"Échantillon de la signature du tome : "
               f"**{corpus.signature.get('echantillon', 0)}**.", ""]
    ecarts = corpus.exigences_du_plan()
    if ecarts:
        lignes += ["⚠ **Le corpus ne satisfait pas l'étape 0.1 du plan**, et le plan demande "
                   "de le dire plutôt que de le contourner :", ""]
        lignes += [f"- {e} ;" for e in ecarts]
        lignes += [""]
    return lignes


def _separations(echelles: dict) -> list[tuple[str, float | None]]:
    """Les quatre séparations qui décident, dans l'ordre où elles se lisent.

    ⚠ La troisième ligne est celle qui sauve le juge d'être déclaré inutile : il sépare très
    bien **deux œuvres**. C'est l'identité DANS une œuvre qu'il ne sépare pas. Publier la
    seule ligne d'identité laisserait croire que l'encodeur ne voit rien."""
    return [
        ("même personnage **contre** personnages différents (identité)",
         juge_mod.separation(echelles["identite_haut"], echelles["identite_confusion"])),
        ("même personnage **contre** une autre œuvre (contrôle)",
         juge_mod.separation(echelles["identite_haut"], echelles["identite_negatif"])),
        ("personnages différents de la même œuvre **contre** une autre œuvre",
         juge_mod.separation(echelles["identite_confusion"], echelles["identite_negatif"])),
        ("même tome **contre** une autre œuvre (style)",
         juge_mod.separation(echelles["style_haut"], echelles["style_bas"])),
    ]


def _verdict_separation(aire) -> str:
    if aire is None:
        return "non mesurée"
    if aire >= juge_mod.SEUIL_SEPARATION:
        return f"✅ au-dessus du seuil ({juge_mod.SEUIL_SEPARATION:.2f})"
    if aire >= 0.60:
        return f"⚠ **faible** — sous le seuil de {juge_mod.SEUIL_SEPARATION:.2f}"
    return "❌ **quasi aveugle** — proche du tirage à pile ou face"


def _n4(valeur) -> str:
    """Quatre décimales. ⚠ `cellule()` du banc commun arrondit à deux, ce qui écraserait la
    différence entre 0,4649 et 0,4676 — c'est-à-dire tout ce que ce banc mesure."""
    return "—" if valeur is None else f"{float(valeur):.4f}"


def section_etalonnage(resultat: dict) -> list[str]:
    echelles = resultat["echelles"]
    libelles = dict(juge_mod.PAIRES)
    lignes = ["## Étape 0.2 — les cinq planchers", ""]
    lignes.append(tableau_markdown(
        ["plancher", "ce qu'il mesure", "paires", "médiane", "moyenne", "écart-type",
         "min", "max"],
        [{"plancher": f"`{nom}`", "ce qu'il mesure": libelles[nom],
          "paires": echelles[nom].n, "médiane": _n4(echelles[nom].mediane),
          "moyenne": _n4(echelles[nom].moyenne), "écart-type": _n4(echelles[nom].ecart_type),
          "min": _n4(echelles[nom].mini), "max": _n4(echelles[nom].maxi)}
         for nom, _ in juge_mod.PAIRES]))

    lignes += ["", "### Le recouvrement, qui est la vraie question", "",
               "L'écart des médianes dit de combien deux centres s'éloignent ; il ne dit pas "
               "si les deux populations se chevauchent. La **séparation** le dit : « présenté "
               "une paire de chaque, le juge les classe-t-il dans le bon ordre ? ». 0,50 est "
               "le tirage à pile ou face.", ""]
    lignes.append(tableau_markdown(
        ["ce qui est comparé", "séparation", "verdict"],
        [{"ce qui est comparé": libelle, "séparation": _n4(aire),
          "verdict": _verdict_separation(aire)}
         for libelle, aire in _separations(echelles)]))

    lignes += ["",
               f"**Échelle d'IDENTITÉ** — le juge est "
               f"{'**utilisable**' if resultat['identite']['utilisable'] else '**INUTILISABLE**'} : "
               f"{resultat['identite']['motif']}.",
               "",
               f"**Échelle de STYLE** — "
               f"{'**utilisable**' if resultat['style']['utilisable'] else '**INUTILISABLE**'} : "
               f"{resultat['style']['motif']}.",
               ""]
    seuil = juge_mod.seuil_median(echelles["identite_haut"], echelles["identite_confusion"])
    if seuil is not None:
        lignes += [f"Seuil de succès du plan (la moitié de l'intervalle entre confusion et "
                   f"plancher haut) : **{seuil:.4f}**. Il est fixé ici, **avant** la première "
                   f"image générée.", ""]
    if resultat["partages"]:
        lignes += ["⚠ **Une illustration de groupe sert de référence à deux personnages** — "
                   "le cas que le critère 8 du plan demande d'examiner :", ""]
        lignes += [f"- « {a} » et « {b} » partagent `{f}` : leur cosinus vaut **1,0** par "
                   f"construction, et cette paire est **exclue** de la population de "
                   f"confusion (elle la fausserait) ;" for a, b, f in resultat["partages"]]
        lignes += [""]
    lignes += [f"Images encodées : **{resultat['images_encodees']}**.", ""]
    return lignes


def section_devis(personnages: int, par_personnage: int, *, decors: int = 0,
                  controle: str = "",
                  reels: int = 0) -> list[str]:
    """Le coût GPU du balayage, **publié avant de le lancer** — `PLAN-29` L29.5.

    ⚠ Le nombre de configurations n'est pas le nombre d'axes : `configurations()` en rend
    cinq (trois pour le nombre de références, deux pour la force), plus une par variante de
    décor demandée. Un devis calculé sur « 10 images par personnage » sans compter les
    configurations réelles sous-estimerait exactement ce que le plan reproche aux lots
    précédents d'avoir laissé filer."""
    par_axe = len(configurations(decors=tuple(range(decors)), controle=controle))
    images = max(1, int(par_personnage))
    # ⚠ `reels` est le nombre de personnages que la commande va RÉELLEMENT traiter — 1 pour un
    # `--balayage`, qui porte sur un personnage nommé. Publier les deux côte à côte est tout
    # l'objet de L29.5 : c'est l'écart entre les deux qui a fait accepter, deux lots durant,
    # des chiffres mesurés sur un personnage et trois images.
    reels = max(0, int(reels)) or personnages
    devis_plan = attente_mod.devis(personnages, images, edition=True)
    devis_reel = attente_mod.devis(reels, par_axe, edition=True)
    return [
        "## L29.5 — le coût GPU, publié AVANT de lancer", "",
        f"- **ce que le plan demande** : {devis_plan['phrase'].splitlines()[0]}",
        f"- **ce que cette commande produirait** : {reels} personnage(s) × {par_axe} "
        f"configuration(s) = {devis_reel['images']} image(s), "
        f"**{devis_reel['duree']}** de GPU",
        "",
        "⚠ **Le devis ne compte que le GPU.** Il ignore la phase 1 (le LLM), et surtout la "
        "demi-journée de relecture humaine en aveugle que le lot 29 chiffre — celle-là n'est "
        "ni parallélisable ni délégable, et c'est elle qui dimensionne le lot.",
        "",
        "⚠ **L'échantillon du coût d'édition est n = 1** "
        f"({attente_mod.EDITION_SECONDES:.1f} s, `docs/mesures/identite-2026-08-29.md` §8.8). "
        f"C'est un ordre de grandeur, pas une promesse : entre le meilleur et le pire relevé "
        f"du dépôt, le rapport est de 14,7.",
        "",
    ]


def section_balayage(lignes_balayage: list[dict], personnage: str) -> list[str]:
    colonnes = ["configuration", "axe", "références", "pas", "guidage", "décor", "canal",
                "secondes", "ressemblance", "nouveauté", "style (embedding)",
                "style (descripteurs)", "descripteur qui décroche", "motifs"]
    lignes = [f"## L25.1 — le balayage sur « {personnage} »", "",
              "⚠ Les **trois** grandeurs sont côte à côte, et les configurations perdantes "
              "sont dans le tableau : « une configuration qui gagne en ressemblance et perd "
              "en style est un fait à montrer, pas à moyenner » (critère 4 ter).", ""]
    lignes.append(tableau_markdown(colonnes, lignes_balayage))
    compte = ident_mod.compter_motifs([ligne["_verdict"] for ligne in lignes_balayage
                                       if ligne.get("_verdict")])
    lignes += ["", "Motifs, nommés et comptés :", ""]
    if compte:
        lignes += [f"- `{motif}` × {n} — {ident_mod.MOTIFS_LISIBLES.get(motif, '')} ;"
                   for motif, n in compte.items()]
    else:
        lignes += ["- aucun."]
    lignes += [""]
    degenerees = [ligne for ligne in lignes_balayage
                  if ligne.get("_grandeurs") is not None and ligne["_grandeurs"].degeneree]
    if degenerees:
        lignes += ["⚠ **Sur les configurations à une seule référence, `ressemblance` et "
                   "`nouveauté` sont la MÊME mesure** (`nouveauté = 1 − ressemblance`) : les "
                   "deux colonnes ne s'optimisent pas séparément, et l'affirmer serait faux.",
                   ""]
    return lignes


def section_variantes(lignes_variantes: list[dict]) -> list[str]:
    return ["## Le juge lui-même : huit prétraitements en concurrence", "",
            "Le critère est l'écart des deux médianes d'identité **rapporté au bruit**. Un "
            "prétraitement qui écarte les médianes en dispersant autant n'a rien gagné.", "",
            tableau_markdown(["cadrage", "côté", "agrégation", "même personnage",
                              "personnages ≠", "écart", "bruit", "écart / bruit"],
                             [{**ligne, **{c: _n4(ligne[c]) for c in
                                           ("même personnage", "personnages ≠", "écart",
                                            "bruit", "écart / bruit")}}
                              for ligne in lignes_variantes]), ""]


def section_triplets(liste: list[dict]) -> list[str]:
    return ["## Étape 0.3 — les triplets du juge humain, en aveugle", "",
            "⚠ **Ce banc ne rend aucun verdict ici.** Il prépare le matériel ; la colonne de "
            "réponse est vide parce que c'est un humain qui la remplit, et le seuil de succès "
            "(14 sur 20) est fixé par le plan **avant** de regarder.", "",
            tableau_markdown(["n", "A", "B", "laquelle ressemble le plus ? (à remplir)"],
                             [{**t, "laquelle ressemble le plus ? (à remplir)": ""}
                              for t in liste]),
            "",
            "La correspondance entre A/B et les configurations est volontairement **absente "
            "de ce tableau** — elle est dans le fichier `triplets.json` écrit à côté des "
            "images, à n'ouvrir qu'après avoir répondu.", ""]


# ────────────────────────────────  La commande  ────────────────────────────────

def main() -> int:
    configurer_stdout()
    ap = argparse.ArgumentParser(
        description="Banc d'identité (PLAN-25) : étalonner le juge, puis balayer la voie A.")
    ap.add_argument("projet", nargs="?", default=None)
    ap.add_argument("tome", nargs="?", default=None)
    ap.add_argument("--etalonnage", action="store_true",
                    help="les cinq planchers de l'étape 0.2 — aucune image générée")
    ap.add_argument("--juge-variantes", action="store_true",
                    help="met huit prétraitements du juge en concurrence")
    ap.add_argument("--balayage", action="store_true",
                    help="L25.1 : génère les images du balayage (moteur réel, lent)")
    ap.add_argument("--personnage", default=None, metavar="NOM",
                    help="--balayage : le personnage à illustrer")
    ap.add_argument("--tous", action="store_true", help="étalonnage + variantes + balayage")
    ap.add_argument("--triplets", type=int, default=0, metavar="N",
                    help="prépare N triplets pour le juge humain de l'étape 0.3")
    ap.add_argument("--devis", action="store_true",
                    help="L29.5 — publie le coût GPU du balayage sans rien générer")
    ap.add_argument("--personnages-cibles", type=int, default=bible_mod.CIBLE_PERSONNAGES,
                    metavar="N", help=f"--devis : personnages visés "
                                      f"(défaut {bible_mod.CIBLE_PERSONNAGES}, la cible du plan)")
    ap.add_argument("--images-par-axe", type=int, default=10, metavar="N",
                    help="--devis : images par personnage visées (défaut 10, celles du plan)")
    ap.add_argument("--decors", default="", metavar="a,b,c",
                    help="L29.4 — variantes de décor à balayer, séparées par des virgules "
                         "(ex. neutre,trame,aucun). Vide = axe fermé, comportement inchangé")
    ap.add_argument("--controle", default="", metavar="IMAGE",
                    help="L30.2 — ajoute UN point d'axe « canal » avec cette image de "
                         "contrôle. Vide = axe fermé, comportement inchangé. ⚠ Exige un "
                         "workflow qui porte le marqueur d'image de contrôle (le graphe "
                         "candidat du PLAN-30) : sinon le moteur refuse, avec son motif, "
                         "avant le GPU")
    ap.add_argument("--autre-oeuvre", default=AUTRE_OEUVRE,
                    help=f"corpus de contrôle négatif (défaut : {AUTRE_OEUVRE}, "
                         f"domaine public)")
    ap.add_argument("--encodeur", default=None,
                    help="chemin du modèle ONNX du juge (défaut : celui de config.yaml)")
    ap.add_argument("--paires-max", type=int, default=PAIRES_MAX)
    ap.add_argument("--markdown", action="store_true", help="tableau daté et publiable")
    ap.add_argument("--config", default=str(RACINE / "config.yaml"))
    args = ap.parse_args()

    if not args.projet:
        ap.error("précise un projet : python tools/banc_identite.py \"roman S\" --etalonnage")
    _decors_demandes(args)          # valide les noms AVANT tout chargement de modèle
    _controle_demande(args)         # … et le fichier de --controle, même raison
    config = charger_config(args.config)
    corpus = lire_corpus(args.projet, config, tome=args.tome or "",
                         autre_oeuvre=args.autre_oeuvre)

    from illustration.orchestrateur import reglages
    reg = reglages(config)
    encodeur_chemin = args.encodeur or str(Path(reg["identite"]["encodeur"]["dossier"])
                                           / reg["identite"]["encodeur"]["fichier"])

    sortie: list[str] = []
    commande = "python " + " ".join(["tools/banc_identite.py", *sys.argv[1:]])
    if args.markdown:
        sortie += entete(args.config, corpus, encodeur_chemin, commande, reg)
    sortie += section_corpus(corpus)

    resultat = None
    if args.etalonnage or args.tous or args.balayage:
        encodeur = juge_mod.Encodeur(encodeur_chemin)
        resultat = etalonner(encodeur, corpus, paires_max=args.paires_max)
        sortie += section_etalonnage(resultat)

    if args.juge_variantes or args.tous:
        sortie += section_variantes(juge_variantes(corpus, encodeur_chemin,
                                                   paires_max=args.paires_max))

    if args.devis:
        sortie += section_devis(args.personnages_cibles, args.images_par_axe,
                                decors=len(_decors_demandes(args)),
                                controle=str(getattr(args, "controle", "") or ""))

    if args.balayage or args.tous:
        sortie += _balayage_complet(args, config, corpus, resultat, encodeur_chemin)

    print("\n".join(sortie))
    return 0


def _balayage_complet(args, config: dict, corpus: Corpus, resultat, encodeur_chemin) -> list[str]:
    """La partie qui GÉNÈRE. Isolée pour que `--etalonnage` n'importe jamais un moteur."""
    import json

    from illustration.orchestrateur import construire_moteur, dossier, reglages

    if not args.tome:
        return ["## L25.1 — le balayage", "",
                "⚠ **Non exécuté** : `--balayage` demande un tome (les images s'écrivent sous "
                "`build/<Projet>/<Tome>/illustrations/balayage/`).", ""]
    nom = args.personnage
    if not nom:
        candidats = sorted(corpus.avec_reference, key=lambda p: -len(p.validees))
        if not candidats:
            return ["## L25.1 — le balayage", "",
                    "⚠ **Non exécuté** : aucun personnage de la bible n'a de référence "
                    "validée par un humain. C'est le refus du critère 5, et il fonctionne.",
                    ""]
        nom = candidats[0].nom
    personnage = next((p for p in corpus.personnages if p.nom == nom), None)
    if personnage is None:
        return ["## L25.1 — le balayage", "",
                f"⚠ **Non exécuté** : « {nom} » n'est pas dans la bible.", ""]

    reg = reglages(config)
    racine_tome = Path(config["chemins"]["build"]) / args.projet / args.tome
    # ⚠ `dossier(config, projet)` prend DEUX arguments depuis la 2.19.0 (`5531029`), qui a
    # rangé les illustrations par ŒUVRE et non plus par tome. Cet appelant en passait trois,
    # et levait donc un `TypeError` — second défaut du même chemin, découvert le 2026-09-03 :
    # `--balayage` cumulait celui-ci et l'`AttributeError` de `_prompt_du_personnage`. Deux
    # renommages, deux appelants oubliés, un seul point commun : le chemin exige un GPU, donc
    # aucun test ne l'atteignait.
    cible = dossier(config, args.projet) / DOSSIER_BALAYAGE
    moteur = construire_moteur(reg, cible)
    encodeur = juge_mod.Encodeur(encodeur_chemin)
    planchers = (resultat or {}).get("planchers") or ident_mod.Planchers()

    decors = _decors_demandes(args)
    controle = _controle_demande(args)
    sortie_devis = section_devis(bible_mod.CIBLE_PERSONNAGES, 10,
                                 decors=len(decors), controle=controle, reels=1)
    for ligne in sortie_devis:
        print(ligne, file=sys.stderr)
    # ⚠ Le prompt devient un APPELABLE : l'axe `decor` change le texte, et `balayer` doit
    # pouvoir le reconstruire par configuration.
    def prompt(decor):                                            # noqa: E306
        return _prompt_du_personnage(config, args.projet, personnage, decor)
    lignes = balayer(moteur, encodeur, corpus, personnage, dossier=cible,
                     planchers=planchers, prompt=prompt, decors=decors, controle=controle,
                     largeur=reg["image"]["largeur"], hauteur=reg["image"]["hauteur"],
                     graine=int(reg["image"]["graine"] or 20260829),
                     dire=lambda m: print(m, file=sys.stderr))
    from illustration.moteur import decharger_moteur
    if reg["vram"]["decharger_image"]:
        decharger_moteur(moteur)

    texte = section_balayage(lignes, personnage.nom)
    texte += ["Prompt de base (identique pour toutes les configurations) :", "",
              f"> {prompt}", "",
              f"Images écrites sous `{cible}` — **hors de git** (`.gitignore` exclut "
              f"`illustrations/`), marquées et accompagnées de leur sidecar.", ""]
    if args.triplets:
        liste = triplets(lignes, nombre=args.triplets)
        (cible / "triplets.json").write_text(
            json.dumps(liste, ensure_ascii=False, indent=2), encoding="utf-8")
        texte += section_triplets(liste)
    _ = racine_tome
    return texte


def _controle_demande(args) -> str:
    """L'image de contrôle demandée, **vérifiée présente sur le disque avant tout modèle**.

    ⚠ Même discipline que `_decors_demandes` et pour la même raison : découvrir « fichier
    introuvable » après le déchargement du LLM et le chargement de 12,8 Go de poids coûte
    exactement ce que le lot 28 a passé son temps à supprimer."""
    chemin = str(getattr(args, "controle", "") or "").strip()
    if not chemin:
        return ""
    if not Path(chemin).is_file():
        raise SystemExit(
            f"--controle : {chemin} n'existe pas.\n"
            f"  L'image de contrôle est FOURNIE par toi : le dépôt n'en fabrique aucune "
            f"(il faudrait un estimateur de contours ou de profondeur, c'est-à-dire un "
            f"modèle de plus). Un trait, une silhouette, un croquis de pose font l'affaire.")
    return chemin


def _decors_demandes(args) -> tuple:
    """Les variantes de décor demandées, **validées contre le gabarit livré**.

    ⚠ Validées ICI, avant qu'un octet de poids soit chargé. Découvrir « décor `tramé` inconnu »
    après le déchargement du LLM et le chargement de 12,8 Go coûterait exactement ce que le
    lot 28 a passé son temps à supprimer."""
    noms = tuple(n.strip() for n in str(getattr(args, "decors", "") or "").split(",")
                 if n.strip())
    if not noms:
        return ()
    gab = gabarits_mod.charger(gabarits_mod.DEFAUT, langue="fr")
    for nom in noms:
        gab.decor_de(nom)          # lève, avec la liste des valeurs possibles
    return noms


def _prompt_du_personnage(config: dict, projet: str, personnage: Personnage,
                          decor: str = gabarits_mod.DECOR_DEFAUT) -> str:
    """Le prompt déterministe de la phase 1, pour CE personnage — celui de
    `illustration/requete.py`, pas un second qui divergerait.

    `decor` nomme la variante du gabarit (`PLAN-29` L29.4). Le défaut est celui du dépôt, donc
    la phrase que le lot 26 a mesurée : appeler cette fonction sans argument rend, mot pour
    mot, le prompt d'avant le lot 29."""
    from illustration import requete as requete_mod

    sources = Path(config["chemins"]["sources"])
    doc = bible_mod.load(bible_mod.chemin(sources / projet))
    # ⚠ `depuis_oeuvre`, et non `depuis_bible` : la fonction a été RENOMMÉE par la 2.18.0
    # (`ae7daa1`) sans que cet appelant suive. `--balayage` levait donc un `AttributeError`
    # dans `_prompt_du_personnage` depuis le 2026-08-30 — c'est-à-dire sur le seul chemin de
    # ce banc qui engage le GPU, donc celui qu'aucun test sans carte ne pouvait atteindre.
    # Relevé et corrigé le 2026-09-03, lot 29 ; `tests/test_tools_banc_identite.py` le tient
    # désormais sans GPU, en interceptant l'appel.
    squelette = requete_mod.depuis_oeuvre(doc, personnages=[personnage.nom], decor=decor)
    blocs = squelette.get("images") or []
    return blocs[0]["prompt"] if blocs else "Portrait d'un personnage seul, en pied."


if __name__ == "__main__":
    raise SystemExit(main())
