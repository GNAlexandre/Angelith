# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que la machine sait faire aujourd'hui — trois sondes, **et aucune sur le fil
d'affichage**.

## La règle, et elle est absolue

L'accueil affiche trois marqueurs : l'endpoint LLM est-il joignable, les poids de détection
sont-ils là, Pandoc est-il trouvable. Le premier est un **appel réseau**, et un Ollama arrêté
ne répond pas par un refus immédiat : il répond par un délai d'attente. Sur le fil
d'affichage, ce serait la fenêtre gelée avant le premier pixel — pour une information de
confort.

Donc : **aucune sonde ne s'exécute sur le fil d'affichage, et aucune ne retarde le premier
pixel.** Elles partent après `show()`, dans le fil de travail existant, et l'accueil s'affiche
complet avec les trois marqueurs en `INCONNU`.

## Trois états, pas deux

`JOIGNABLE`, `INJOIGNABLE`, `INCONNU`. Le troisième n'est pas une commodité d'implémentation :
c'est l'état réel pendant la seconde qui suit le lancement, et le confondre avec
« injoignable » ferait dire à l'accueil quelque chose de faux pendant une seconde à chaque
démarrage. Le dépôt refuse d'afficher un chiffre qu'il n'a pas mesuré ; il refuse aussi
d'afficher un verdict qu'il n'a pas encore rendu.

## ⚠ Ce n'est PAS le diagnostic

Le diagnostic complet charge des modèles, liste les modèles du serveur, fait une
mini-génération — 12,1 s contre un serveur arrêté, mesuré le 2026-09-06. Le réutiliser ici
ferait de l'accueil une page qui bloque. Ces sondes-ci ne répondent qu'à « est-ce que ça
répond ? ».

## ⚠ MISE À JOUR lot 36 (2026-09-06) — deux profondeurs, un seul vocabulaire

Le `PLAN-36` L36.3 demandait trois pastilles « alimentées par `core/diagnostic.py` » **et**
« pas de diagnostic complet au démarrage ». Les deux moitiés se contredisent si on les lit à la
lettre : un diagnostic complet est exactement ce qu'il ne faut pas lancer au premier pixel.

Ce qui est livré tranche ainsi, et c'est écrit plutôt que glissé : **les sondes gardent leur
profondeur** — un GET, un `is_file()`, un `which` — et **empruntent le vocabulaire** du
diagnostic. `verdicts()` rend des `core.diagnostic.Verdict` : même brique, même gravité, même
identifiant que la page Diagnostic emploie, et le même geste, lu dans `core/reparations.py`.

Ce que ça garantit : l'accueil et la page ne peuvent plus se contredire sur ce qu'il faut
faire, parce que le remède n'est plus écrit deux fois. Ce que ça ne garantit pas : que les deux
disent la même chose au même instant — la sonde est plus superficielle, et c'est son rôle.

## Aucun import Qt

Règle de couche du dépôt (`gui/__init__.py`) : tout ce qui décide se teste sans PySide6. Les
trois fonctions ci-dessous rendent des `Sonde`, et `tests/test_gui_sondes.py` les vérifie sans
écran, sans réseau et sans modèle.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

#: Les trois états affichables. `INCONNU` est celui de l'accueil tant que la sonde n'a pas
#: rendu — cf. l'avertissement du module.
JOIGNABLE = "joignable"
INJOIGNABLE = "injoignable"
INCONNU = "inconnu"

#: Délai d'attente d'une sonde réseau, en secondes. **Court par construction** : cette sonde
#: répond à « est-ce que ça répond ? », pas à « qu'est-ce qu'il y a dedans ? ». Un serveur qui
#: met plus de deux secondes à accuser réception d'un GET sur sa racine n'est pas dans un état
#: où l'accueil doit promettre qu'il est joignable.
#:
#: ⚠ À comparer avec les 30 s de `core.llm.test_connection`, qui, lui, fait une vraie
#: génération : ce sont deux questions différentes, et deux budgets différents.
DELAI_RESEAU = 2.0

#: Symbole affiché à côté de chaque marqueur. ⚠ Il DOUBLE la couleur, il ne la remplace pas :
#: un état annoncé par la seule couleur est un état que 8 % des hommes ne lisent pas
#: (`PLAN-19`, critère d'accessibilité).
SYMBOLES = {JOIGNABLE: "●", INJOIGNABLE: "○", INCONNU: "…"}


@dataclass(frozen=True)
class Sonde:
    """Le verdict d'une sonde. `detail` dit ce qu'on a regardé, jamais ce qu'on suppose."""

    nom: str
    etat: str
    detail: str = ""
    remede: str = ""

    @property
    def symbole(self) -> str:
        return SYMBOLES.get(self.etat, "…")

    def ligne(self) -> str:
        """Une ligne prête à afficher : symbole, nom, verdict, et ce qu'on a regardé."""
        verdict = {JOIGNABLE: "disponible", INJOIGNABLE: "absent",
                   INCONNU: "en cours…"}.get(self.etat, self.etat)
        return f"{self.symbole} {self.nom} — {verdict}" + (f" ({self.detail})"
                                                           if self.detail else "")


def inconnues() -> tuple[Sonde, ...]:
    """Les trois sondes AVANT qu'elles aient répondu. C'est ce que l'accueil affiche au
    premier pixel, et c'est vrai."""
    return (Sonde("Serveur LLM", INCONNU),
            Sonde("Poids de détection", INCONNU),
            Sonde("Pandoc", INCONNU))


# --------------------------------------------------------------------------- #
#  Les trois sondes
# --------------------------------------------------------------------------- #

def url_llm(config: dict, section: str | None = None) -> str:
    """L'endpoint déclaré. Défaut historique du dépôt : `http://localhost:11434/v1`.

    ⚠ **MISE À JOUR 2026-09-06, lot 39 : `section` corrige un défaut réel.** Cette fonction
    lisait TOUJOURS `config["llm"]` racine, et ignorait donc un `manga.llm.base_url` distinct —
    alors que `manga/doctor.py` le respecte, lui, par `core_config.section`. Sur une
    installation qui pointe la brique manga vers une seconde machine, l'accueil et le sélecteur
    de modèles sondaient le serveur du **light novel** et rendaient un verdict sur le mauvais
    endpoint.

    `section=None` garde le comportement d'avant, au bit près : c'est ce qui rend la correction
    additive plutôt que risquée."""
    if section:
        from core import config as core_config
        llm = core_config.section(config, section, "llm")
    else:
        llm = (config.get("llm") or {})
    return str(llm.get("base_url") or "http://localhost:11434/v1")


def sonder_llm(config: dict, *, delai: float = DELAI_RESEAU) -> Sonde:
    """Le serveur LLM répond-il ? **Un GET, rien d'autre.**

    ⚠ On ne liste pas les modèles et on ne génère rien : `core.llm.test_connection` le fait
    déjà, en trente secondes, derrière une entrée de menu. Ici la seule question est de savoir
    si l'accueil peut promettre qu'un run trouvera son serveur.

    `httpx` est une dépendance DÉCLARÉE de `requirements.txt` (`core/llm.py` l'importe
    directement) : cette sonde n'en ajoute aucune."""
    url = url_llm(config)
    try:
        import httpx
    except ImportError:                                # pragma: no cover — socle incomplet
        return Sonde("Serveur LLM", INCONNU, "httpx n'est pas installé")
    cible = url.rstrip("/")
    if cible.endswith("/v1"):
        cible = cible[: -len("/v1")]
    try:
        reponse = httpx.get(cible + "/", timeout=delai)
    except Exception as err:                           # noqa: BLE001 — tout échec = injoignable
        return Sonde("Serveur LLM", INJOIGNABLE, f"{url} — {type(err).__name__}",
                     remede="Démarre LM Studio ou Ollama, ou corrige llm.base_url dans "
                            "config.yaml.")
    # ⚠ Un code d'erreur HTTP reste une RÉPONSE : un serveur qui rend 404 sur sa racine est
    # joignable, et c'est exactement ce que fait LM Studio. Ne retenir que 200 dirait
    # « injoignable » d'un serveur qui tourne.
    return Sonde("Serveur LLM", JOIGNABLE, f"{url} — HTTP {reponse.status_code}")


#: Le poids que la brique manga charge à la détection, quand `config.yaml` ne dit rien.
POIDS_PAR_DEFAUT = Path("manga_models") / "bubble_detector.onnx"


def chemins_poids(config: dict) -> list[Path]:
    """Le fichier de poids que `manga.detection` ira chercher, tel que la config le nomme.

    ⚠ `manga.detection.model_path` — la clé exacte que `BubbleDetector.depuis_config` lit
    (`manga/detection.py`). En inventer une seconde ferait dire à l'accueil que les poids sont
    absents alors qu'ils sont là, ou l'inverse ; les deux mensonges se valent."""
    detection = ((config.get("manga") or {}).get("detection") or {})
    valeur = detection.get("model_path")
    return [Path(str(valeur))] if valeur else [POIDS_PAR_DEFAUT]


def sonder_poids(config: dict) -> Sonde:
    """Les poids de détection sont-ils sur le disque ? **Aucun chargement.**

    Charger le modèle ONNX pour savoir s'il est là coûterait une seconde et ~104 Mo de
    mémoire résidente sur une page qui doit s'afficher instantanément. Un `is_file()` répond à
    la question posée."""
    manquants = [c for c in chemins_poids(config) if not c.is_file()]
    if manquants:
        # ⚠ **La licence est LUE, pas recopiée** (lot 38). La phrase qui était ici disait
        # « le détecteur est GPL-3.0 + Manga109-s » : c'était FAUX. Manga109-s concerne le
        # détecteur de TEXTE SUR LE DESSIN, pas celui des bulles. Le dépôt portait trois
        # affirmations différentes sur ce fichier ; il n'en porte plus qu'une,
        # `manga/models.py`.
        from manga import models
        return Sonde("Poids de détection", INJOIGNABLE,
                     ", ".join(str(c) for c in manquants),
                     remede=f"Cf. manga_models/README.md — {models.DETECTEUR_LICENCE}, "
                            f"il n'est pas redistribué avec Angelith.")
    present = chemins_poids(config)[0]
    try:
        taille = present.stat().st_size / (1024 * 1024)
    except OSError:                                    # pragma: no cover — course au disque
        return Sonde("Poids de détection", JOIGNABLE, str(present))
    return Sonde("Poids de détection", JOIGNABLE, f"{present.name}, {taille:.0f} Mo")


def sonder_pandoc() -> Sonde:
    """Pandoc est-il dans le `PATH` ? Il produit le `.docx` et l'`.epub` du light novel."""
    chemin = shutil.which("pandoc")
    if not chemin:
        return Sonde("Pandoc", INJOIGNABLE, "absent du PATH",
                     remede="https://pandoc.org/installing.html — sans lui, la brique light "
                            "novel ne produit ni .docx ni .epub.")
    return Sonde("Pandoc", JOIGNABLE, chemin)


#: Ce que chaque sonde devient dans le vocabulaire du diagnostic : son identifiant de
#: `core/diagnostic.py`, sa brique, et la réparation qui la règle quand elle en a une.
#:
#: ⚠ Les identifiants sont **les mêmes** que ceux des verdicts des doctors (`serveur_llm`,
#: `poids_detection`, `pandoc`). C'est ce qui permet à l'accueil et à la page Diagnostic de
#: parler du même point sans que personne n'ait à recopier un remède.
CORRESPONDANCE: dict[str, tuple[str, str, str]] = {
    "Serveur LLM": ("serveur_llm", "socle", "serveur_llm"),
    "Poids de détection": ("poids_detection", "manga", "poids_detection"),
    "Pandoc": ("pandoc", "ln", "pandoc"),
}


def verdict(sonde: Sonde):
    """La sonde, dite dans le vocabulaire de `core/diagnostic.py`.

    ⚠ Une sonde `INCONNU` devient un verdict d'**information**, jamais un bloquant : « je n'ai
    pas encore regardé » n'est pas « c'est cassé ». C'est la même règle que les trois états de
    ce module, portée dans l'autre vocabulaire.

    ⚠ Et une sonde injoignable est `DEGRADE`, pas `BLOQUANT`, **même pour le serveur LLM** :
    cette sonde-ci n'a fait qu'un GET sur une racine. Conclure au blocage sur une mesure aussi
    superficielle serait afficher un verdict plus dur que ce qu'on a mesuré — le diagnostic
    complet, lui, a le droit de le faire, parce qu'il a vraiment essayé de générer."""
    from core import diagnostic as diag
    from core import reparations as rep
    from manga import reparations as _rep_manga  # noqa: F401 — enregistre les gestes manga

    identifiant, brique, reparation = CORRESPONDANCE.get(
        sonde.nom, (sonde.nom.lower().replace(" ", "_"), diag.SOCLE, ""))
    if sonde.etat == JOIGNABLE:
        return diag.Verdict(identifiant, brique, diag.CONFORME,
                            constat=f"{sonde.nom} — disponible"
                                    + (f" ({sonde.detail})" if sonde.detail else ""))
    if sonde.etat == INCONNU:
        return diag.Verdict(
            identifiant, brique, diag.INFORMATION,
            constat=f"{sonde.nom} — pas encore sondé",
            consequence="l'accueil ne peut rien promettre tant que la sonde n'a pas répondu.",
            geste="ouvre la page Diagnostic pour une inspection complète.")
    geste = sonde.remede
    candidate = rep.par_identifiant(reparation) if reparation else None
    return diag.Verdict(
        identifiant, brique, diag.DEGRADE,
        constat=f"{sonde.nom} — absent" + (f" ({sonde.detail})" if sonde.detail else ""),
        consequence="la page Diagnostic dit ce que ça coûte exactement.",
        geste=geste or (candidate.consigne() if candidate is not None else ""),
        reparable=bool(candidate is not None and candidate.automatique),
        reparation=reparation)


def verdicts(sondes) -> tuple:
    """Les sondes de l'accueil, dites dans le vocabulaire du diagnostic."""
    return tuple(verdict(s) for s in sondes)


def sonder_tout(config: dict, *, delai: float = DELAI_RESEAU) -> tuple[Sonde, ...]:
    """Les trois sondes, dans l'ordre d'affichage. **Appelée depuis le fil de travail.**

    ⚠ Aucune ne lève : une sonde qui échouerait par une exception ferait tomber la tâche, donc
    laisserait les trois marqueurs en « inconnu » pour toute la session. Chacune rend un
    verdict, y compris « je ne sais pas »."""
    return (sonder_llm(config, delai=delai), sonder_poids(config), sonder_pandoc())
