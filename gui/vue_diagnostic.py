# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que la page Diagnostic dit — **et rien de ce qu'elle dessine**.

Règle de couche du dépôt (`gui/__init__.py`) : tout ce qui DÉCIDE se teste sans PySide6. Ici
vivent le regroupement des verdicts, l'ordre d'affichage, les phrases et le verdict d'un
bouton de réparation. `gui/diagnostic.py` n'a plus qu'à poser des widgets par-dessus.

C'est le même partage que `gui/vue_retouche.py` (lot 35) et `gui/garde.py` : les phrases d'une
destination et ses gardes sont testables sans écran, et elles le sont.

## Ce que la page montre, et dans quel ordre

Groupé **par brique**, puis **par gravité** : on ne lit pas d'abord ce qui va bien, et on ne
mélange pas un manque de Pandoc avec un manque de poids ONNX. Un utilisateur qui ne traduit
que des planches doit pouvoir lire sa section et ignorer le reste — c'est la raison d'être du
champ `Verdict.brique`.

## ⚠ Aucun verdict n'est affiché sans geste

Critère 4 du `PLAN-36`. Un constat sans geste est une plainte : il informe qu'on est bloqué et
laisse l'utilisateur chercher. `phrase_geste()` garantit qu'il y a toujours quelque chose à
lire — soit le geste du verdict, soit « hors périmètre », explicitement.

## ⚠ Ce que la page ne fait PAS

Elle ne sonde pas au chargement, elle ne télécharge rien toute seule, et elle ne bloque jamais
le fil d'affichage. Le diagnostic complet est un geste qu'on demande (« Relancer le
diagnostic »), il part dans le fil de travail, et la page s'affiche d'abord vide en le disant.
"""
from __future__ import annotations

from dataclasses import dataclass

from core import diagnostic as diag
from core import reparations as rep
from core.version import ETAT_BRIQUES
# ⚠ Importé pour son EFFET : ce module enregistre les réparations de la brique manga dans le
# catalogue de `core/reparations.py`. Sans lui, un verdict `poids_detection` n'aurait pas de
# bouton — non parce que c'est interdit, mais parce que personne n'aurait déclaré le geste.
# `core` ne peut pas l'importer lui-même : il n'importe aucune brique
# (`tests/test_imports_briques.py`).
from manga import reparations as _reparations_manga  # noqa: F401

#: L'ordre des briques dans la page. Le socle d'abord — ce qui le bloque bloque tout le reste
#: — puis les briques dans l'ordre où le dépôt les présente.
ORDRE_BRIQUES: tuple[str, ...] = (diag.SOCLE, diag.LN, diag.MANGA, diag.SCAN,
                                  diag.ILLUSTRATION)

#: Le titre de chaque groupe. ⚠ La brique `scan` est en BÊTA et la brique `illustration` est
#: EXPÉRIMENTALE : le dire ici, là où l'utilisateur lit son diagnostic, et pas seulement dans
#: le titre de la fenêtre que personne ne lit (même règle qu'à l'accueil, lot 31).
TITRES_BRIQUE = {
    diag.SOCLE: "Socle — commun à tout",
    diag.LN: "Light novel",
    diag.MANGA: "Manga et webtoon",
    diag.SCAN: "OCR de scans",
    diag.ILLUSTRATION: "Illustrations",
}

#: Ce que dit l'en-tête tant qu'aucun diagnostic n'a tourné. ⚠ « Inconnu », pas « tout va
#: bien » : le dépôt refuse d'afficher un chiffre qu'il n'a pas mesuré, et il refuse aussi
#: d'afficher un verdict qu'il n'a pas encore rendu (`gui/sondes.py`).
PHRASE_VIERGE = ("Aucun diagnostic n'a encore tourné dans cette session. "
                 "Lance-le : il inspecte la configuration, les dépendances, les poids, les "
                 "polices et le serveur de modèles.")

#: Ce que dit le bouton, et ce qu'il coûte. Le chiffre porte son dénominateur : il vient de la
#: mesure du 2026-09-06 sur cette machine, serveur arrêté.
#: L'introduction du bloc « Poids et modèles ». ⚠ Elle dit d'abord ce qu'Angelith NE fait pas :
#: c'est la seule phrase de la page qui parle de rediffusion, et elle est lue par quelqu'un qui
#: s'apprête à télécharger un fichier sous une licence qui n'est pas celle du projet.
PHRASE_POIDS = (
    "Ce qu'Angelith sait récupérer pour toi, à la demande. Rien n'est téléchargé sans un clic, "
    "et rien n'est redistribué ni miroité par ce projet : chaque fichier vient de sa source "
    "primaire, sa licence est écrite ci-dessous, et son empreinte SHA-256 est enregistrée à "
    "côté de lui après coup. ⚠ Vérifie la licence AVANT de rediffuser des planches qui en "
    "dérivent — elles ne sont pas sous la licence d'Angelith.")

PHRASE_COUT = ("Le diagnostic complet interroge le serveur de modèles : compte une douzaine "
               "de secondes s'il est arrêté (mesuré à 12,1 s le 2026-09-06, serveur "
               "injoignable sur 127.0.0.1). Il tourne hors du fil d'affichage.")


@dataclass(frozen=True)
class Groupe:
    """Les verdicts d'une brique, prêts à afficher."""

    brique: str
    titre: str
    verdicts: tuple[diag.Verdict, ...]
    conformes: int

    @property
    def bloquants(self) -> tuple[diag.Verdict, ...]:
        return tuple(v for v in self.verdicts if v.gravite == diag.BLOQUANT)

    def phrase_conformes(self) -> str:
        """« 6 points vérifiés, rien à faire » — un compte, pas six lignes de ✓."""
        if not self.conformes:
            return ""
        return (f"{self.conformes} point vérifié, rien à faire" if self.conformes == 1
                else f"{self.conformes} points vérifiés, rien à faire")


def titre_brique(brique: str) -> str:
    """Le titre du groupe, **avec l'état de la brique quand il n'est pas « stable »**."""
    base = TITRES_BRIQUE.get(brique, brique)
    etat = ETAT_BRIQUES.get(brique)
    if etat == "beta":
        return f"{base} (bêta)"
    if etat == "experimental":
        return f"{base} (expérimentale)"
    return base


def _rang(verdict: diag.Verdict) -> int:
    return diag.GRAVITES.index(verdict.gravite) if verdict.gravite in diag.GRAVITES else 9


def grouper(sections, *, montrer_conformes: bool = False) -> tuple[Groupe, ...]:
    """Les verdicts par brique puis par gravité, les conformes comptés plutôt qu'étalés.

    ⚠ Un groupe **sans rien à signaler** est conservé et rendu vide : le faire disparaître
    ferait croire que la brique n'a pas été inspectée. « Six points vérifiés » et « rien
    affiché » ne disent pas la même chose, et c'est la distinction que ce lot défend
    partout."""
    tout = diag.verdicts(sections)
    groupes: list[Groupe] = []
    ordre = list(ORDRE_BRIQUES) + sorted({v.brique for v in tout} - set(ORDRE_BRIQUES))
    for brique in ordre:
        de_la_brique = [v for v in tout if v.brique == brique]
        if not de_la_brique:
            continue
        conformes = sum(1 for v in de_la_brique if v.gravite == diag.CONFORME)
        montres = [v for v in de_la_brique
                   if montrer_conformes or v.gravite != diag.CONFORME]
        montres.sort(key=_rang)
        groupes.append(Groupe(brique, titre_brique(brique), tuple(montres), conformes))
    return tuple(groupes)


def phrase_geste(verdict: diag.Verdict) -> str:
    """Ce qu'on lit sous un constat. **Jamais vide pour un verdict non conforme.**

    Critère 4 du `PLAN-36` : « aucun verdict n'est affiché sans geste — ou son absence de geste
    est explicite (hors périmètre) »."""
    if verdict.gravite == diag.CONFORME:
        return ""
    if verdict.geste:
        return verdict.geste
    reparation = rep.par_identifiant(verdict.reparation or verdict.identifiant)
    if reparation is not None:
        return reparation.consigne()
    return diag.HORS_PERIMETRE


def phrase_licence(verdict: diag.Verdict) -> str:
    """La licence du poids que ce verdict propose de récupérer. Vide s'il n'y en a pas.

    ## ⚠ Le défaut que cette fonction ferme, et il était mesurable

    `phrase_geste` rend `verdict.geste` **en priorité**, et tous les verdicts réparables des
    doctors en portent un. La branche qui appelle `reparation.consigne()` — c'est-à-dire la
    seule qui écrive la licence — n'était donc **jamais atteinte en pratique**. La licence
    n'existait à l'écran qu'en infobulle du bouton et dans la boîte de confirmation, c'est-à-dire
    **après** le clic.

    Pire : le geste de `poids_detection` PROMETTAIT que la licence est affichée avant, sans
    jamais la nommer. Une promesse tenue par une infobulle n'est pas tenue.

    ⚠ Cette fonction ne remplace pas `phrase_geste`, elle s'ajoute à côté : le geste dit quoi
    faire, la licence dit sous quelles conditions. Les confondre reviendrait à choisir laquelle
    des deux on n'affiche pas."""
    reparation = bouton_pour(verdict)
    if reparation is None or not reparation.licence:
        return ""
    return f"Licence : {reparation.licence}"


def bouton_pour(verdict: diag.Verdict) -> rep.Reparation | None:
    """La réparation qu'un bouton peut lancer pour ce verdict, ou `None`.

    ⚠ **Trois conditions, et les trois sont nécessaires** : le verdict se dit réparable, la
    réparation existe dans le catalogue, et elle est de classe `RECUPERABLE`. Un bouton devant
    « installe Pandoc » serait un mensonge : Angelith n'installe aucun logiciel système."""
    if verdict.ok or not verdict.reparable:
        return None
    reparation = rep.par_identifiant(verdict.reparation or verdict.identifiant)
    if reparation is None or not reparation.automatique:
        return None
    return reparation


def phrase_resume(sections) -> str:
    """L'en-tête de la page : ce qui bloque, ce qui dégrade, et sur combien de points.

    ⚠ Le chiffre porte son dénominateur — « 2 bloquants sur 14 points » — parce qu'un chiffre
    affiché est lu comme une promesse (`docs/chiffres-de-reference.md`)."""
    compte = diag.resume(sections)
    total = compte["total"]
    if not total:
        return PHRASE_VIERGE
    bloquants = compte[diag.BLOQUANT]
    degrades = compte[diag.DEGRADE]
    if not bloquants and not degrades:
        return f"Rien à signaler — {total} point(s) inspecté(s), tous conformes."
    morceaux = []
    if bloquants:
        morceaux.append(f"{bloquants} bloquant(s)")
    if degrades:
        morceaux.append(f"{degrades} dégradation(s)")
    return f"{', '.join(morceaux)} sur {total} point(s) inspecté(s)."


#: Les briques qui savent tourner SANS serveur LLM (lot 39). ⚠ **Le light novel n'en est pas**,
#: et ce n'est pas un oubli : il n'existe aucune surface de saisie manuelle pour de la prose —
#: la Retouche est un éditeur de PLANCHES — et un roman rendu sans traduction sortirait avec son
#: texte source dans un `.docx` français, c'est-à-dire une sortie fausse.
#: `pipeline/orchestrator.py` le dit déjà pour un traducteur désactivé : « sans traduction, le
#: pipeline n'a rien à produire ». L'ouvrir demanderait un éditeur de prose, donc un lot.
BRIQUES_SANS_LLM: frozenset[str] = frozenset({diag.MANGA})


def phrase_briques_utilisables(sections) -> str:
    """« Ce que tu peux faire tout de suite » — et c'est là que la gravité par brique paie.

    ⚠ C'est le critère 3 du plan, rendu visible : Pandoc absent retire le light novel de cette
    phrase et **laisse le manga dedans**. L'inverse est vrai aussi. Une page qui dirait « 1
    point bloquant » sans dire *quoi* découragerait quelqu'un qui n'a besoin que d'une brique."""
    tout = diag.verdicts(sections)
    if not tout:
        return ""
    libelles = {diag.LN: "light novel", diag.MANGA: "manga et webtoon",
                diag.SCAN: "OCR de scans", diag.ILLUSTRATION: "illustrations"}
    # ⚠ Seules les briques RÉELLEMENT inspectées entrent dans la phrase. Sans ce filtre, une
    # brique dont aucun point n'a été relevé — le scan, aujourd'hui — apparaîtrait comme
    # « utilisable » parce qu'aucun verdict ne la bloque. C'est la faute exacte que ce lot
    # combat ailleurs : ne rien avoir mesuré n'est pas un bon résultat.
    inspectees = {v.brique for v in tout}
    candidates = [b for b in (diag.LN, diag.MANGA, diag.SCAN, diag.ILLUSTRATION)
                  if b in inspectees]
    if not candidates:
        return ""
    utilisables = [libelles[b] for b in candidates if not diag.bloquants_pour(sections, b)]
    # ⚠ **La seconde phrase, et elle change ce que la page dit d'une machine sans LLM** (lot
    # 39). Un endpoint injoignable bloquait les quatre briques, si bien que la page annonçait
    # « Aucune brique n'est utilisable » à quelqu'un dont le nettoyage, l'OCR, le relettrage et
    # la saisie manuelle marchaient parfaitement. On recalcule donc SANS la capacité LLM, et on
    # nomme ce qui reste — au lieu de laisser croire qu'il ne reste rien.
    sans_traduction = [libelles[b] for b in candidates
                       if b in BRIQUES_SANS_LLM
                       and libelles[b] not in utilisables
                       and not diag.bloquants_pour(sections, b, sans_llm=True)]
    complement = ""
    if sans_traduction:
        complement = (" Sans traduction, " + ", ".join(sans_traduction)
                      + " reste utilisable : nettoyage, OCR, relettrage et saisie manuelle "
                        "n'appellent aucun modèle de langue (config.yaml > llm.actif: false).")
    if not utilisables:
        return ("Aucune brique n'est utilisable en l'état : corrige d'abord ce qui bloque."
                + complement)
    return "Utilisable en l'état : " + ", ".join(utilisables) + "." + complement


# --------------------------------------------------------------------------- #
#  « Poids et modèles » — un geste, pas une réparation d'erreur (lot 38)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Poids:
    """Un poids qu'Angelith sait récupérer, tel que la page le montre.

    `etat` — `"present"`, `"absent"`, `"partiel"` ou `""` quand on ne sait pas. ⚠ La chaîne
    vide n'est pas un défaut : `modele_ocr` vit dans le cache de `huggingface_hub` et `polices`
    dans l'enregistrement Windows, deux endroits dont ce dépôt n'est pas propriétaire. Inventer
    un état pour eux serait afficher un verdict que personne n'a mesuré.
    """

    reparation: object
    etat: str = ""
    chemin: str = ""

    @property
    def recuperable(self) -> bool:
        """Le bouton a-t-il quelque chose à faire ? ⚠ Vrai aussi quand l'état est INCONNU :
        récupérer un modèle déjà présent est idempotent et sans risque, alors que masquer le
        bouton laisserait sans recours quelqu'un dont le cache Hugging Face est corrompu."""
        return self.etat != "present"


#: Ce que la page affiche à côté de chaque poids. Le symbole DOUBLE le mot, il ne le remplace
#: pas (`PLAN-19`, critère d'accessibilité).
PHRASES_ETAT_POIDS = {
    "present": "✓ présent",
    "absent": "○ absent",
    "partiel": "⚠ incomplet — un téléchargement précédent s'est interrompu",
    "": "· état non mesuré — ce fichier n'est pas posé par Angelith (cache Hugging Face "
        "pour l'OCR, registre de polices de Windows pour le lettrage)",
}


def poids_recuperables(config: dict) -> tuple[Poids, ...]:
    """Les poids que l'application sait récupérer, avec leur état quand il est connaissable.

    ## Pourquoi un bloc PERMANENT, et pas des verdicts de plus

    Deux des quatre réparations `RECUPERABLE` — `poids_texte` et `modele_ocr` — n'avaient
    **aucun verdict** dans les doctors. Comme `bouton_pour()` exige un `Verdict` qui les nomme,
    elles étaient **inatteignables depuis l'interface** : le catalogue les déclarait
    automatiques, et rien ne pouvait les déclencher.

    ⚠ **La correction n'est PAS d'ajouter deux verdicts**, et c'est délibéré. La sortie console
    de `run_manga.py --check` est un contrat scripté, gelé octet pour octet par
    `tests/test_core_diagnostic_iso.py` ; deux sections de plus le casseraient pour un bénéfice
    qui n'est pas celui qu'on cherche. Ce qu'on cherche est un endroit où **télécharger un poids
    de façon indépendante**, y compris quand tout va bien — c'est-à-dire précisément là où un
    verdict n'existe pas, puisqu'il n'y a rien à signaler.

    D'où un bloc qui liste les quatre, toujours, avec leur licence et leur taille.

    ⚠ Sans Qt et sans réseau : cette fonction lit le catalogue et fait au plus un `is_file()`
    par poids. Elle est appelée à l'affichage de la page, donc sur le fil d'affichage.
    """
    sortie: list[Poids] = []
    for reparation in rep.par_classe(rep.RECUPERABLE):
        etat, chemin = _etat_du_poids(reparation.identifiant, config, reparation.octets)
        sortie.append(Poids(reparation, etat, chemin))
    return tuple(sortie)


def _etat_du_poids(identifiant: str, config: dict, octets: int) -> tuple[str, str]:
    """`(etat, chemin)` — `("", "")` quand le fichier n'est pas à nous.

    ⚠ `_reparations_manga` est déjà importé en tête de module, pour son effet d'enregistrement :
    on le réutilise plutôt que d'ouvrir un second chemin d'import."""
    cible = _reparations_manga.cible_connue(identifiant, config)
    if cible is None:
        return "", ""
    etat = rep.etat_fichier(cible, octets)
    if not etat.present:
        return "absent", str(cible)
    return ("partiel" if etat.partiel else "present"), str(cible)
