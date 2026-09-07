# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La **bascule VRAM d'un run** : elle s'ouvre une fois, elle se ferme toujours, une seule fois.

## Ce que le lot 27 ajoute, et pourquoi ce n'est pas cosmétique

Jusqu'ici la bascule était deux fonctions de `illustration/orchestrateur.py`, appelées sur le
chemin nominal. Deux trous en découlaient, et le `PLAN-27` L27.2 les nomme tous les deux :

1. **la fermeture n'avait pas lieu sur erreur ni sur annulation.** `_rendre_la_vram` était
   appelée *après* le bloc de génération : une exception, un `Ctrl+C` ou un clic sur
   « Annuler » sautaient par-dessus. Le coût est mesuré et il est chez le pilote, pas chez
   nous : `docs/README.fr.md` documente qu'un abandon sale a fait chuter le débit de
   **25 à 18 tok/s** en laissant le pilote AMD dans un mauvais état. Un modèle d'image de
   12 Go abandonné salement est le même défaut en pire ;
2. **le LLM ne revenait jamais.** `orchestrateur._basculer_vram` écrivait « le rechargement du
   LLM appartient à l'appelant », et aucun appelant ne le faisait. La traduction suivante
   payait donc le rechargement sans que rien ne le dise.

## La règle du rechargement, et elle est plus étroite que le plan ne le demandait

Le plan écrit « le LLM revient ». Appliqué à la lettre, ce serait un **défaut** : recharger
17 Go de LLM pendant que ComfyUI garde ses 12 Go de transformeur en VRAM, c'est exactement le
scénario que toute l'architecture refuse — « ~17 Go ne tiennent de toute façon pas dans 20 Go
de VRAM. Ça supprime tout scénario de seconde instance / partage de VRAM »
(`docs/README.fr.md` ≈ l. 639).

**Le LLM ne revient donc que si la carte est réellement rendue**, c'est-à-dire si le moteur
d'image a décroché (`illustration.vram.decharger_image`, désarmé par défaut). Sinon la bascule
le **dit** au lieu de le faire :

    VRAM : le LLM n'est pas rechargé — le moteur d'image tient encore la carte
           (illustration.vram.decharger_image: false).

⚠ **Conséquence directe : sur la configuration livrée, rien ne change.** `decharger_image` vaut
`false`, donc aucun rechargement n'a lieu, donc le comportement est celui du lot 26 — c'est
l'iso-comportement que le §9.3 du contexte agent exige d'une nouvelle clé.

## Blindée contre le second clic, et contre le second `Ctrl+C`

`fermer()` est **idempotente** : le second appel ne fait rien et le dit. C'est la transposition
de ce que `core/power.py:shielded_unload` fait pour le LLM — le dépôt documente précisément ce
comportement, « le déchargement est blindé contre un second Ctrl+C ». Une annulation cliquée
deux fois ne doit pas envoyer deux `/free` à un serveur dont **un appel sur sept** a déjà fait
segfauter ComfyUI (mesuré le 2026-08-29, ROCm 7.14 / Windows).

Chaque étape est en outre **best-effort et isolée** : un serveur qui ne répond plus ne doit pas
faire échouer un run dont les images sont déjà écrites et marquées.

## Aucun import de `core.cli` ici

Les deux opérations coûteuses — décharger le LLM, le recharger — sont **injectées**. Ce n'est
pas de la cérémonie : c'est ce qui rend la bascule testable sans serveur Ollama, sans réseau et
sans GPU, donc en CI. `illustration/orchestrateur.py` fournit les vraies.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

#: Le dénominateur que le `PLAN-30` L30.4 exige avant de reparler du taux d'échec de `/free`.
#:
#: ⚠ **Le chiffre en vigueur au 2026-09-03 est « 1 sur 7 », et sept n'est pas un dénominateur.**
#: Relevé le 2026-08-29 sur ComfyUI 0.34.2 / ROCm 7.14 / RX 7900 XT : un appel sur sept a fait
#: segfauter ComfyUI (violation d'accès 0xC0000005 dans son propre
#: `comfy/model_management.py:model_unload`). À sept appels, l'intervalle de confiance va de
#: « presque jamais » à « une fois sur trois » : il ne soutient ni d'armer, ni de refuser
#: définitivement. Vingt ne le rend pas solide non plus — il le rend *discutable*, ce qui est
#: exactement ce que le plan demande.
APPELS_DE_REFERENCE = 20


@dataclass(frozen=True)
class ReleveFree:
    """Le taux d'échec de `POST /free`, avec son dénominateur et sa version — `PLAN-30` L30.4.

    ⚠ **`arret_au` est la donnée que le protocole naïf perd.** Le mode d'échec mesuré n'est
    pas « l'appel rend une erreur », c'est « ComfyUI meurt ». Une boucle de vingt appels qui
    ne regarderait pas si le serveur est encore là compterait dix-neuf faux succès après le
    premier plantage. On s'arrête donc au premier mort, et le relevé dit à quel rang."""

    appels: int = 0
    pannes: int = 0
    version: str = ""
    arret_au: int = 0
    journal: tuple = ()

    @property
    def taux(self) -> float | None:
        return (self.pannes / self.appels) if self.appels else None

    @property
    def appels_en_echec(self) -> int:
        """Les appels qui ont **levé** sans tuer le serveur — timeout, 500, réseau coupé.

        ⚠ **Ils ne sont PAS comptés dans `pannes`, et la distinction n'est pas cosmétique.**
        Le chiffre que le `PLAN-30` L30.4 demande de reprendre est celui du **segfault** : « sur
        SEPT appels, UN a fait segfauter ComfyUI ». Une erreur HTTP est une autre panne, avec
        une autre cause et un autre remède ; les additionner produirait un taux qui ne se
        compare plus au 1 sur 7 de 2026-08-29. Elles sont donc comptées à part — et **dites**,
        parce qu'un relevé qui les tairait laisserait croire à vingt appels réussis."""
        return sum(1 for _, cle, _ in self.journal if cle == "appel_en_echec")

    @property
    def complet(self) -> bool:
        """Le dénominateur demandé est-il atteint ? Un relevé interrompu ne conclut pas."""
        return self.appels >= APPELS_DE_REFERENCE and not self.arret_au

    def phrase(self) -> str:
        if not self.appels:
            return "aucun appel : rien n'est mesuré."
        base = (f"{self.pannes} panne(s) sur {self.appels} appel(s) à /free"
                + (f" — ComfyUI {self.version}" if self.version else ""))
        if self.appels_en_echec:
            base += (f" (⚠ et {self.appels_en_echec} appel(s) en ERREUR sans tuer le "
                     f"serveur — autre cause, comptée à part)")
        if self.arret_au:
            return (f"{base}.\n"
                    f"  ⚠ ARRÊT au {self.arret_au}e appel : le serveur ne répondait "
                    f"plus. Relance ComfyUI et reprends — les dénominateurs s'additionnent, "
                    f"et le plan en demande {APPELS_DE_REFERENCE}.")
        if not self.complet:
            return (f"{base}.\n"
                    f"  ⚠ Le PLAN-30 L30.4 demande {APPELS_DE_REFERENCE} appels : "
                    f"ce relevé ne conclut pas encore.")
        return (f"{base} — dénominateur atteint. Décide `illustration.vram.decharger_image` "
                f"d'après ce chiffre, et publie-le avec sa version de ComfyUI.")


def mesurer_free(*, liberer, vivant, repetitions: int = 1, version: str = "",
                 dire=print) -> ReleveFree:
    """Appelle `/free` N fois et vérifie **après chaque appel que ComfyUI est encore là**.

    ## Pourquoi ce n'est pas une boucle de trois lignes — `PLAN-30` L30.4

    Le plan demande de reprendre le taux d'échec de `/free` sur vingt appels, parce que le
    chiffre en vigueur — **1 sur 7**, relevé le 2026-08-29 — n'a pas de dénominateur digne de
    ce nom. Mais le mode d'échec n'est pas celui qu'on croit : `POST /free` ne rend pas
    d'erreur, il **tue le serveur** (violation d'accès 0xC0000005 dans
    `comfy/model_management.py:model_unload`, chez ComfyUI). Une boucle qui ne sonderait pas
    entre deux appels compterait dix-neuf succès imaginaires après le premier plantage — et
    publierait « 1 sur 20 » là où la vérité est « 1 sur 1, puis plus rien ».

    Les deux opérations sont **injectées**, comme partout dans ce module : `liberer()` poste,
    `vivant()` sonde. Aucun réseau ici, donc le protocole se teste sans serveur.

    ⚠ **Cette fonction n'arme rien.** `illustration.vram.decharger_image` reste à `false` quoi
    qu'elle relève : c'est une décision d'Alexandre, prise au vu du chiffre, pas un effet de
    bord d'une commande de mesure.

    ⚠ **Elle ne relance jamais ComfyUI**, et le plan l'interdit explicitement : « Angelith ne
    pilote pas le cycle de vie d'un programme que l'utilisateur a installé »."""
    n = max(1, int(repetitions))
    journal: list = []
    pannes = 0
    arret_au = 0
    for rang in range(1, n + 1):
        try:
            rendu = bool(liberer())
        except Exception as err:                     # noqa: BLE001 — best-effort, cf. module
            rendu = False
            journal.append((rang, "appel_en_echec", str(err)))
        else:
            journal.append((rang, "appel_ok" if rendu else "appel_sans_effet", ""))
        encore_la = False
        try:
            encore_la = bool(vivant())
        except Exception as err:                     # noqa: BLE001 — best-effort, cf. module
            journal.append((rang, "sonde_en_echec", str(err)))
        if not encore_la:
            pannes += 1
            arret_au = rang
            journal.append((rang, "serveur_mort",
                            "ComfyUI ne répond plus après cet appel — c'est le segfault "
                            "connu, et il est chez lui"))
            dire(f"  /free {rang}/{n} : ⚠ ComfyUI ne répond plus. Arrêt du relevé.")
            break
        dire(f"  /free {rang}/{n} : le serveur répond encore"
             + ("" if rendu else " (l'appel n'a rien rendu)"))
    return ReleveFree(appels=arret_au or n, pannes=pannes, version=str(version or ""),
                      arret_au=arret_au, journal=tuple(journal))


@dataclass
class Bascule:
    """L'échange de la carte entre le LLM et le modèle d'image, pour la durée d'un run.

    `decharge` et `recharge` sont des appelables sans argument (ou prenant la liste des
    modèles) fournis par l'appelant — voir la docstring du module."""

    #: Les modèles LLM à décharger puis, le cas échéant, à recharger.
    modeles: tuple[str, ...] = ()
    decharger_llm: bool = True
    decharger_image: bool = False
    recharger_llm: bool = True
    #: `(modeles) -> None`. Injecté.
    decharge: object = None
    #: `(modeles) -> None`. Injecté.
    recharge: object = None
    dire: object = print
    horloge: object = time.monotonic

    ouverture_secondes: float = 0.0
    fermeture_secondes: float = 0.0
    #: Ce qui s'est réellement passé, pour le rapport et pour les tests.
    journal: list = field(default_factory=list)
    _ouverte: bool = False
    _fermee: bool = False

    # ────────────────────────────────  Ouvrir  ────────────────────────────────

    def ouvrir(self) -> float:
        """Décharge le LLM et rend le coût, en secondes. **Une fois par run, jamais par image.**

        Sur huit images, un va-et-vient par image coûterait plus que la génération elle-même :
        c'est la raison pour laquelle cette méthode n'est pas dans la boucle."""
        if self._ouverte:
            return self.ouverture_secondes
        self._ouverte = True
        if not self.decharger_llm or not self.modeles or self.decharge is None:
            self._noter("llm_non_decharge", "le LLM n'est pas déchargé "
                                            "(illustration.vram.decharger_llm: false, ou "
                                            "aucun modèle nommé)")
            return 0.0
        self._dire(f"Bascule VRAM : déchargement de {len(self.modeles)} modèle(s) LLM…")
        depart = float(self.horloge())
        try:
            self.decharge(list(self.modeles))
        except Exception as err:                     # noqa: BLE001 — best-effort, cf. module
            self._noter("llm_decharge_echec", f"déchargement du LLM en échec : {err}")
            return 0.0
        self.ouverture_secondes = float(self.horloge()) - depart
        self._noter("llm_decharge",
                    f"LLM déchargé en {self.ouverture_secondes:.1f} s")
        self._dire(f"  bascule : {self.ouverture_secondes:.1f} s")
        return self.ouverture_secondes

    # ────────────────────────────────  Fermer  ────────────────────────────────

    def fermer(self, moteur=None) -> dict:
        """Rend la carte, puis fait revenir le LLM **si la carte est réellement libre**.

        Appelée sur **tous** les chemins de sortie : succès, erreur, annulation. Idempotente :
        le second appel ne fait rien.

        Rend un récapitulatif : `{image_rendue, llm_recharge, motif, secondes, journal}`."""
        if self._fermee:
            return {**self._recap(), "motif": "déjà fermée — rien n'a été refait"}
        self._fermee = True
        depart = float(self.horloge())
        image_rendue = self._rendre_l_image(moteur)
        llm_recharge, motif = self._faire_revenir_le_llm(image_rendue)
        self.fermeture_secondes = float(self.horloge()) - depart
        return {**self._recap(), "image_rendue": image_rendue,
                "llm_recharge": llm_recharge, "motif": motif}

    @property
    def fermee(self) -> bool:
        return self._fermee

    # ────────────────────────────────  Rouages  ────────────────────────────────

    def _rendre_l_image(self, moteur) -> bool:
        """La seconde moitié de la bascule : le modèle d'image rend la carte.

        ⚠ **Désarmée par défaut**, et ce n'est pas de la prudence gratuite : sur SEPT appels à
        `/free` mesurés le 2026-08-29, UN a fait segfauter ComfyUI (violation d'accès dans son
        propre `model_management.py:model_unload`, ROCm 7.14 / Windows). Le plantage est chez
        lui, nous ne pouvons pas le corriger, et les images sont déjà écrites et marquées quand
        cet appel a lieu."""
        if not self.decharger_image or moteur is None:
            self._noter("image_non_rendue",
                        "le moteur d'image garde la carte "
                        "(illustration.vram.decharger_image: false)")
            return False
        from illustration import moteur as moteur_mod
        depart = float(self.horloge())
        try:
            rendu = moteur_mod.decharger_moteur(moteur)
        except Exception as err:                     # noqa: BLE001 — best-effort, cf. module
            self._noter("image_rendue_echec", f"déchargement du moteur en échec : {err}")
            return False
        if rendu:
            self._dire(f"VRAM rendue par le moteur d'image "
                       f"({float(self.horloge()) - depart:.1f} s).")
            self._noter("image_rendue", "le moteur d'image a rendu la carte")
        else:
            self._noter("image_sans_effet", "le moteur n'avait rien à rendre")
        return bool(rendu)

    def _faire_revenir_le_llm(self, carte_libre: bool) -> tuple[bool, str]:
        """Le LLM revient — **seulement** si la carte est libre. Cf. la docstring du module."""
        if not self.recharger_llm or not self.modeles or self.recharge is None:
            motif = "rechargement du LLM désarmé (illustration.vram.recharger_llm: false)"
            self._noter("llm_non_recharge", motif)
            return False, motif
        if not self._ouverte or not self.ouverture_secondes:
            motif = "le LLM n'avait pas été déchargé : il n'y a rien à faire revenir"
            self._noter("llm_non_recharge", motif)
            return False, motif
        if not carte_libre:
            motif = ("le LLM n'est PAS rechargé — le moteur d'image tient encore la carte "
                     "(illustration.vram.decharger_image: false). Les deux modèles ne "
                     "coexistent jamais en VRAM : ~17 Go de LLM et ~12 Go de transformeur ne "
                     "tiennent pas dans 20 Go.")
            self._noter("llm_non_recharge", motif)
            self._dire(f"VRAM : {motif}")
            return False, motif
        self._dire(f"VRAM : rechargement de {len(self.modeles)} modèle(s) LLM…")
        try:
            self.recharge(list(self.modeles))
        except Exception as err:                     # noqa: BLE001 — best-effort, cf. module
            motif = f"rechargement du LLM en échec : {err}"
            self._noter("llm_recharge_echec", motif)
            return False, motif
        self._noter("llm_recharge", "le LLM est revenu en VRAM")
        return True, "le LLM est revenu en VRAM"

    def _noter(self, cle: str, message: str) -> None:
        self.journal.append((cle, message))

    def _dire(self, message: str) -> None:
        if callable(self.dire):
            self.dire(message)

    def _recap(self) -> dict:
        return {"image_rendue": any(c == "image_rendue" for c, _ in self.journal),
                "llm_recharge": any(c == "llm_recharge" for c, _ in self.journal),
                "ouverture_secondes": round(self.ouverture_secondes, 3),
                "fermeture_secondes": round(self.fermeture_secondes, 3),
                "journal": list(self.journal)}
