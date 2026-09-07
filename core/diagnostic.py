# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le diagnostic **rend une structure**, puis quelqu'un l'imprime ou la dessine.

## Le défaut que ce module ferme

Jusqu'au lot 35, les deux doctors (`pipeline/doctor.py` et `run_manga.py --check`) étaient des
suites de `print`. L'interface graphique les affichait en **capturant leur sortie console**
(`Fenetre._capturer_diagnostic`) et en la posant dans un `DialogueTexte`. Trois conséquences,
toutes mesurées le 2026-09-06 (`docs/mesures/premier-lancement-2026-09-06.md`) :

- aucun geste n'était attaché à un problème — le texte disait ce qui manque, pas quoi faire ;
- rien n'était réutilisable : ni par l'accueil, ni par le dépôt guidé (qui a besoin de savoir
  si `unrar` existe **avant** de proposer l'import), ni par un `.exe` qui doit se diagnostiquer
  chez l'utilisateur ;
- le dialogue **bloquait** le temps du diagnostic, qui comprend un appel réseau de 12 s.

## Le contrat : `ecrire` est un paramètre, pas une fatalité

⚠ **La sortie console de `run.py --check` et `run_manga.py --check` est un contrat scripté.**
Le refactor consiste donc à **extraire le constat de l'impression**, jamais à réécrire le
texte. Chaque collecteur reçoit un `ecrire` :

- `ecrire=print` — le chemin console. Les lignes partent **au fil de l'eau**, dans l'ordre
  exact d'avant, ce qui compte pour la section Ollama, qui met une douzaine de secondes ;
- `ecrire=None` — le chemin structuré. Rien ne s'imprime, les `Verdict` sortent quand même.

Un `Verdict` garde ses `lignes_console` : c'est la trace de ce qui a été écrit, et c'est ce que
`tests/test_core_diagnostic_iso.py` compare octet pour octet à un gabarit gelé.

## Quatre gravités, et la quatrième n'est pas une commodité

Le plan en annonçait trois (`bloquant`, `degrade`, `information`). Il en faut une quatrième,
`conforme`, pour une raison de structure : un doctor rapporte **aussi** ce qui marche — les
seize lignes `✓` de `run.py --check` en sont — et sans elle la structure ne saurait pas les
reproduire. Elle sert aussi à la page Diagnostic, qui replie « 14 points conformes » au lieu de
les étaler.

## ⚠ `bloquant` est relatif à une BRIQUE, jamais à l'application

Pandoc absent ne bloque **aucun** run manga. Le dire à quelqu'un qui ne traduit que des
planches le découragerait pour rien. D'où le champ `brique`, et `bloquants_pour()` : la
question « suis-je bloqué ? » n'a de réponse que pour un usage donné.
`tests/test_core_diagnostic.py` refuse qu'une absence propre au light novel bloque un usage
manga, et réciproquement.

## Aucun téléchargement ici

Ce module **constate**. La réparation vit dans `core/reparations.py`, elle part d'un clic
explicite, et jamais pendant un run.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field, replace

# --------------------------------------------------------------------------- #
#  Le vocabulaire
# --------------------------------------------------------------------------- #

#: Les quatre gravités, de la plus grave à la plus bénigne. L'ordre de ce tuple EST l'ordre
#: d'affichage de la page Diagnostic : on lit d'abord ce qui empêche de travailler.
BLOQUANT = "bloquant"
DEGRADE = "degrade"
INFORMATION = "information"
CONFORME = "conforme"

GRAVITES: tuple[str, ...] = (BLOQUANT, DEGRADE, INFORMATION, CONFORME)

#: Ce que chaque gravité veut dire, en une phrase, pour l'humain qui lit la page.
PHRASES_GRAVITE = {
    BLOQUANT: "empêche la brique de tourner",
    DEGRADE: "la brique tourne, mais une sortie manquera",
    INFORMATION: "à savoir, rien à corriger",
    CONFORME: "vérifié, rien à faire",
}

#: Le symbole console, celui-là même qu'employaient les deux doctors. ⚠ Il DOUBLE la couleur,
#: il ne la remplace pas (`PLAN-19`, critère d'accessibilité).
SYMBOLES = {BLOQUANT: "❌", DEGRADE: "⚠", INFORMATION: "·", CONFORME: "✓"}

#: Les briques, telles que `core/version.py:ETAT_BRIQUES` les nomme, plus `socle` — ce qui
#: n'appartient à aucune (`config.yaml`, le pack de langue, le serveur LLM).
SOCLE = "socle"
LN = "ln"
MANGA = "manga"
SCAN = "scan"
ILLUSTRATION = "illustration"

#: ⚠ **Le serveur LLM n'est pas une brique, c'est une CAPACITÉ** — lot 39.
#:
#: Il était classé `socle`, et comme `DEPENDANCES_BRIQUE` met `SOCLE` dans les quatre briques,
#: un endpoint injoignable faisait rendre à la page Diagnostic « Aucune brique n'est utilisable
#: en l'état ». C'était faux, et mesurablement : la détection, le nettoyage, l'OCR, le
#: relettrage et la saisie manuelle n'appellent aucun LLM — `gui/lanceur.py` décrit d'ailleurs
#: `--from rendu` comme « relettrage seul — aucun appel LLM ».
#:
#: Le distinguer permet de dire la seule chose vraie : la brique tourne, la TRADUCTION non.
LLM = "llm"

#: Ce dont chaque brique a réellement besoin. **C'est cette table qui décide** de ce qui
#: bloque un usage donné : un usage manga dépend du socle et de la brique manga, pas de
#: Pandoc. Le webtoon n'y figure pas : ce n'est pas une brique, c'est `--format webtoon` du
#: même orchestrateur (`PLAN-31` L31.7).
DEPENDANCES_BRIQUE: dict[str, frozenset[str]] = {
    LN: frozenset({SOCLE, LN, LLM}),
    MANGA: frozenset({SOCLE, MANGA, LLM}),
    SCAN: frozenset({SOCLE, SCAN}),
    ILLUSTRATION: frozenset({SOCLE, ILLUSTRATION}),
}

#: ⚠ `SCAN` ne dépend PAS du LLM, et ce n'est pas un oubli : la brique lit des pages, elle ne
#: traduit pas — `run_ocr.py` produit un `.md` japonais que le light novel traduira ensuite.
#: `ILLUSTRATION` non plus : son `llm.actif` est déjà `false` par défaut (`config.yaml`), et sa
#: sélection de références est déterministe sans serveur.

#: Ce qu'on écrit quand il n'y a rien à faire — critère 4 du `PLAN-36` : « aucun verdict n'est
#: affiché sans geste, ou son absence de geste est explicite ».
HORS_PERIMETRE = ("Hors périmètre d'Angelith : c'est une opération système, elle n'est ni "
                  "automatisable ni souhaitable depuis l'application.")


@dataclass(frozen=True)
class Verdict:
    """Un point du diagnostic, tel que le `PLAN-36` L36.1 le décrit.

    `identifiant` — stable, il sert de clé (`"pandoc"`, `"poids_detection"`). C'est lui que la
    page Diagnostic relie à une réparation, et lui que le `PLAN-37` fera tourner en CI sur
    l'exécutable gelé.
    `brique` — à qui ce point appartient (`DEPENDANCES_BRIQUE` en fait la portée du blocage).
    `gravite` — l'une des quatre. ⚠ Elle est relative à `brique`, jamais à l'application.
    `constat` — ce qu'on a **vu**, au passé, sans conjecture : « Pandoc introuvable dans le
    PATH ».
    `consequence` — ce que ça coûte : « les sorties DOCX du light novel ne seront pas
    produites ».
    `geste` — quoi faire, avec l'URL ou la commande. Vide seulement si `gravite == CONFORME`.
    `reparable` — un bouton peut-il le régler ? (cf. `core/reparations.py`)
    `reparation` — l'identifiant de la réparation, quand `reparable`.
    `lignes_console` — ce que le doctor a réellement écrit. **Le contrat scripté**, gardé ici
    pour qu'un test puisse le comparer octet pour octet.
    """

    identifiant: str
    brique: str
    gravite: str
    constat: str
    consequence: str = ""
    geste: str = ""
    reparable: bool = False
    reparation: str = ""
    lignes_console: tuple[str, ...] = ()

    @property
    def symbole(self) -> str:
        return SYMBOLES.get(self.gravite, "·")

    @property
    def ok(self) -> bool:
        return self.gravite in (CONFORME, INFORMATION)

    def ligne(self) -> str:
        """Une ligne prête à afficher hors console : symbole, constat, conséquence."""
        return (f"{self.symbole} {self.constat}"
                + (f" — {self.consequence}" if self.consequence else ""))


@dataclass(frozen=True)
class Section:
    """Un bloc du diagnostic, avec l'en-tête **exact** que le doctor imprimait.

    ⚠ `entete` porte son `\\n` de tête quand l'original en avait un. Ce n'est pas de la
    négligence : `print("\\n— Chemins —")` et `print("— Chemins —")` ne produisent pas les
    mêmes octets, et c'est précisément ce que le contrat scripté interdit de changer."""

    entete: str
    verdicts: tuple[Verdict, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
#  Écrire au fil de l'eau, et garder ce qu'on a écrit
# --------------------------------------------------------------------------- #

def dire(ecrire, *lignes: str) -> tuple[str, ...]:
    """Écrit `lignes` si `ecrire` est fourni, et les rend dans tous les cas.

    C'est **tout** le mécanisme de ce module : le collecteur appelle `dire(ecrire, …)` là où
    l'ancien code appelait `print(…)`, et pose le résultat dans `lignes_console`. La sortie
    console reste identique — même texte, même ordre, même instant — et la structure sort
    quand même.

    ⚠ Une ligne peut contenir des `\\n` : `print("a\\nb")` était une seule instruction, et la
    couper en deux changerait le nombre d'appels sans changer les octets. On garde la forme de
    l'original, pour que la relecture du diff soit possible."""
    if ecrire is not None:
        for ligne in lignes:
            ecrire(ligne)
    return tuple(lignes)


# --------------------------------------------------------------------------- #
#  Lire une structure
# --------------------------------------------------------------------------- #

def verdicts(sections) -> tuple[Verdict, ...]:
    """Tous les verdicts, à plat, dans l'ordre des sections."""
    return tuple(v for s in sections for v in s.verdicts)


def par_gravite(sections, gravite: str) -> tuple[Verdict, ...]:
    return tuple(v for v in verdicts(sections) if v.gravite == gravite)


def par_brique(sections, brique: str) -> tuple[Verdict, ...]:
    return tuple(v for v in verdicts(sections) if v.brique == brique)


def bloquants_pour(sections, brique: str, *, sans_llm: bool = False) -> tuple[Verdict, ...]:
    """Ce qui empêche **cette brique-là** de tourner.

    ⚠ C'est la fonction qui porte le critère 3 du `PLAN-36`. Un usage manga ne dépend que du
    socle et de la brique manga ; `reference.docx` absent n'y entre pas, et l'inverse est vrai
    aussi — les poids ONNX absents ne bloquent aucun light novel. Une brique inconnue ne dépend
    que d'elle-même et du socle, ce qui est le repli sûr : on ne prétend pas savoir.

    ⚠ **`sans_llm` retire la capacité LLM de la portée** (lot 39). Quelqu'un qui a désarmé la
    traduction (`llm.actif: false`) n'est pas bloqué par un serveur injoignable : son tome sort
    avec des bulles vides, qu'il remplira dans la Retouche. Lui dire « aucune brique n'est
    utilisable » serait faux, et un faux avertissement cesse d'être lu."""
    portee = set(DEPENDANCES_BRIQUE.get(brique, frozenset({SOCLE, brique})))
    if sans_llm:
        portee.discard(LLM)
    return tuple(v for v in verdicts(sections)
                 if v.gravite == BLOQUANT and v.brique in portee)


def reparables(sections) -> tuple[Verdict, ...]:
    """Les verdicts qu'un bouton peut régler, les conformes exclus."""
    return tuple(v for v in verdicts(sections) if v.reparable and not v.ok)


def resume(sections) -> dict[str, int]:
    """Le compte par gravité. ⚠ Il porte son dénominateur : `resume()["total"]`."""
    tout = verdicts(sections)
    compte = {g: sum(1 for v in tout if v.gravite == g) for g in GRAVITES}
    compte["total"] = len(tout)
    return compte


def sans_conformes(sections) -> tuple[Section, ...]:
    """Les mêmes sections, débarrassées de ce qui va bien — et des sections devenues vides.

    C'est ce que la page Diagnostic montre par défaut : quatorze `✓` ne se lisent pas, ils se
    comptent."""
    gardees = []
    for section in sections:
        restants = tuple(v for v in section.verdicts if v.gravite != CONFORME)
        if restants:
            gardees.append(replace(section, verdicts=restants))
    return tuple(gardees)


def imprimer(sections, *, ecrire=print) -> None:
    """Réimprime une structure déjà collectée — **pour un test, pas pour un doctor**.

    Un doctor passe `ecrire=print` au collecteur et n'appelle jamais ceci : sinon la section
    Ollama attendrait douze secondes avant d'écrire sa première ligne. Cette fonction sert à
    vérifier qu'une structure collectée en silence rend bien les mêmes octets."""
    for section in sections:
        if section.entete:
            ecrire(section.entete)
        for verdict in section.verdicts:
            for ligne in verdict.lignes_console:
                ecrire(ligne)


def texte_console(sections) -> str:
    """La sortie console qu'une structure représente. Ce que compare le test d'isométrie."""
    lignes: list[str] = []
    imprimer(sections, ecrire=lignes.append)
    return "".join(ligne + "\n" for ligne in lignes)


# --------------------------------------------------------------------------- #
#  Les constats réellement communs aux deux briques
# --------------------------------------------------------------------------- #

def verdict_dependance(module: str, nom_pip: str, indice: str, *, brique: str,
                       ecrire=None) -> Verdict:
    """Un import Python, tel que `cli.section_dependances` l'écrivait.

    ⚠ On **importe** vraiment, on ne se contente pas de `importlib.util.find_spec` : un
    `onnxruntime` installé mais dont la DLL manque passe la recherche de module et échoue à
    l'import. Le diagnostic doit dire ce que fera le run, pas ce que dit le disque."""
    try:
        __import__(module)
    except ImportError as err:
        return Verdict(
            identifiant=f"pip_{nom_pip.replace('-', '_')}", brique=brique, gravite=BLOQUANT,
            constat=f"le paquet Python « {nom_pip} » n'est pas importable ({err})",
            consequence=f"la brique {brique} ne peut pas démarrer.",
            geste=indice.strip("`"),
            lignes_console=dire(ecrire, f"❌ {nom_pip} introuvable — {indice}."))
    return Verdict(
        identifiant=f"pip_{nom_pip.replace('-', '_')}", brique=brique, gravite=CONFORME,
        constat=f"{nom_pip} installé",
        lignes_console=dire(ecrire, f"✓ {nom_pip} installé."))


def section_dependances(modules: list[tuple[str, str]], indice: str, *, brique: str,
                        ecrire=None) -> Section:
    """Le bloc « — Dépendances Python additionnelles — », structuré.

    ⚠ L'en-tête porte son `\\n` de tête, comme `cli.section_dependances` l'imprimait, et il est
    écrit AVANT les imports — un import qui prend une seconde ne doit pas laisser la console
    muette."""
    entete = "\n— Dépendances Python additionnelles —"
    dire(ecrire, entete)
    return Section(entete, tuple(verdict_dependance(mod, nom, indice, brique=brique,
                                                    ecrire=ecrire)
                                 for mod, nom in modules))


def section_installation(*, ecart=None) -> Section | None:
    """L'écart entre le `config.yaml` de l'utilisateur et celui que le paquet livre.

    Rend `None` hors gel, et `None` quand il n'y a rien à dire — donc rien n'apparaît pour qui
    lance `python gui.py` depuis le dépôt.

    ## ⚠ Pourquoi ce constat n'est PAS dans les deux doctors

    La sortie console de `run.py --check` et `run_manga.py --check` est un contrat scripté,
    gelé octet pour octet par `tests/test_core_diagnostic_iso.py`. Y ajouter une ligne le
    casserait. Ce constat-ci est donc produit pour les consommateurs STRUCTURÉS — la page
    Diagnostic et `--diagnostic-json` — qui sont aussi les seuls endroits où il a un sens : il
    n'existe que dans une installation gelée.

    ## ⚠ Gravité `INFORMATION`, et pas `DEGRADE`

    Un `config.yaml` d'une version antérieure **marche** : le code lit sa configuration à
    travers des centaines de `.get(...)` à défaut, donc une clé absente prend sa valeur par
    défaut. Ce qui manque n'est pas du fonctionnement, c'est de la CONNAISSANCE — l'utilisateur
    ne sait pas que des réglages ont été ajoutés. `DEGRADE` dirait qu'une sortie manquera ;
    c'est faux, et un faux avertissement cesse d'être lu.

    ## ⚠ Le geste ne propose PAS de fusionner

    On ne fusionne pas un document (interdit 5). Le geste nomme les deux fichiers et laisse la
    personne décider ce qu'elle veut recopier — c'est la seule opération qui ne perde pas de
    prose.
    """
    from . import installation
    if not installation.gele():
        return None
    ecart = ecart if ecart is not None else installation.ecart_de_config()
    if not ecart.a_signaler:
        return None
    return Section("\n— Configuration de l'installation —", (Verdict(
        identifiant="config_utilisateur_datee", brique=SOCLE, gravite=INFORMATION,
        constat=ecart.phrase(),
        consequence="ces clés sont lues avec leur valeur par défaut, donc sans effet — rien "
                    "ne casse, mais tu ne bénéficies pas des réglages ajoutés depuis.",
        geste=f"compare {installation.config_utilisateur()} au fichier livré "
              f"{installation.config_livree()} et recopie ce qui t'intéresse. ⚠ Angelith ne "
              f"fusionne pas les deux : config.yaml est un document, et une fusion "
              f"automatique effacerait la prose qui justifie chaque valeur."),))


def verdict_outil_externe(nom: str, *, brique: str, gravite: str, consequence: str,
                          geste: str, identifiant: str = "",
                          alternatives: tuple[str, ...] = ()) -> Verdict:
    """Un exécutable du `PATH` — Pandoc, `unrar`, un moteur PDF.

    ⚠ **Ces outils-là ne sont jamais réparables d'un bouton.** Angelith n'installe aucun
    logiciel système : ni Pandoc, ni un gestionnaire de paquets, ni un service. La ligne est
    celle que le `PLAN-30` a déjà tranchée pour ComfyUI — « Angelith ne pilote pas le cycle de
    vie d'un programme que l'utilisateur a installé ». Le geste est un lien et une commande
    copiable, et rien de plus.

    Aucune `lignes_console` : ce constructeur sert le chemin structuré (page Diagnostic, dépôt
    guidé), pas les doctors, qui gardent leur texte."""
    for candidat in (nom,) + alternatives:
        chemin = shutil.which(candidat)
        if chemin:
            return Verdict(identifiant=identifiant or nom, brique=brique, gravite=CONFORME,
                           constat=f"{candidat} trouvé — {chemin}")
    trouvable = " / ".join((nom,) + alternatives)
    return Verdict(identifiant=identifiant or nom, brique=brique, gravite=gravite,
                   constat=f"{trouvable} introuvable dans le PATH",
                   consequence=consequence, geste=geste, reparable=False)
