# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le **client** ComfyUI — pas le framework, et pas un graphe inventé.

## Pourquoi un client HTTP, et pas `diffusers`

Le critère de choix du `PLAN-24` n'est pas la vitesse, c'est : *combien de dépendance le dépôt
avale-t-il ?* Un serveur HTTP local que l'utilisateur installe lui-même, comme Ollama, ne pèse
**rien** dans `requirements-*.txt`. Un `import diffusers` pèse des gigaoctets et met le dépôt
en dette de compatibilité ROCm. Le dépôt a déjà refusé OpenCV pour ~60 Mo (interdit n° 4) : la
cohérence commande un client. Ce module n'utilise que `urllib.request`, comme
`manga/models.py` et `core/power.py`.

## Pourquoi le graphe vient de l'utilisateur, et pas du dépôt

Un graphe ComfyUI est propre à un modèle, à une version de nœuds et à une machine. En écrire
un ici, sans avoir pu l'exécuter, aurait produit un fichier **plausible et faux** — exactement
ce que le dépôt reproche à une mesure sans dénominateur. L'utilisateur exporte donc son
workflow au **format API** depuis ComfyUI et le désigne par `illustration.comfyui.workflow`.

Le dépôt n'y touche que par **substitution de marqueurs** : partout dans le JSON, la chaîne
`%prompt%` est remplacée par le prompt, `%graine%` par la graine, etc. C'est ce qui donne au
moteur une propriété que le `PLAN-24` exige et qu'aucun graphe codé en dur n'aurait :

⚠ **`CANAUX_SUPPORTES` est LU dans le graphe.** Un canal dont le marqueur n'apparaît nulle
part dans le workflow n'est pas supporté, donc il est **refusé avec un motif nommé** — jamais
honoré à moitié, jamais jeté en silence. Une requête à masques envoyée dans un graphe sans
`%masque_1%` s'arrête avant la première seconde de GPU, et le message dit quel marqueur
ajouter.

## Ce qui EST mesuré, à quelle date, et ce qui ne l'est toujours pas

⚠ **Une affirmation d'état porte sa date, ou elle finit par mentir** (`00-CONTEXTE-AGENT.md`
§5 bis). Ce paragraphe a affirmé jusqu'à la 2.21.0 que « ce client n'a jamais tourné contre un
vrai serveur ComfyUI ». C'était vrai le jour où il a été écrit, en **2.15.0** ; c'était **faux
depuis la 2.16.0**, et personne ne l'a vu parce que la phrase ne portait pas sa date.

| État | Depuis | Ce qui l'établit |
|---|---|---|
| le client a tourné contre un vrai serveur | 2.16.0, **2026-08-29** | `docs/mesures/connecteur-qwen-2026-08-29.md` — 25 générations, **0 échec d'exécution**, 103,7 s par image, pic VRAM 14 421 Mio sur 20 464 |
| un run complet, de bout en bout | 2.18.0, **2026-08-30** | `docs/mesures/prompt-illustration-2026-08-30.md` |
| `stable-diffusion.cpp` et `diffusers` | **jamais** | les deux autres chemins que le `PLAN-24` demandait de mesurer ne l'ont pas été, et ce module ne les implémente pas |

Ce qui reste vrai : la plomberie HTTP se teste **aussi** contre un transport factice (mise en
file, sondage de l'historique, récupération de l'image, échecs), et c'est ce qui la rend
vérifiable en CI, sans serveur ni GPU. Le défaut de `illustration.moteur` reste `"factice"`,
non plus faute de mesure mais parce qu'un défaut qui exige un serveur installé ne serait pas
un défaut (cf. `core/version.py`, qui porte l'état daté de la brique).
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from illustration.moteur import (CANAUX, Sortie, verifier_canaux,
                                verifier_canaux_exiges)

#: Marqueur → canal. Les marqueurs indexés (`%reference_1%`, `%masque_2%`) sont reconnus par
#: préfixe : un graphe qui en porte trois accepte trois références.
MARQUEURS: dict[str, str] = {
    "%prompt%": "prompt",
    "%prompt_negatif%": "prompt_negatif",
    "%reference_": "references",
    "%entite_": "entites",
    "%masque_": "entites",
    "%image_controle%": "image_controle",
}

#: Les marqueurs dont l'ABSENCE fait ÉLAGUER le nœud qui les porte, au lieu de le laisser
#: partir avec une valeur vide.
#:
#: ⚠ **`%image_controle%` a été ajouté à cette liste le 2026-09-03, et c'était un défaut.**
#: Jusque-là, l'élagage ne connaissait que les marqueurs **indexés** (`%reference_2%`,
#: `%masque_3%`) — parce qu'aucun graphe du dépôt ne portait `%image_controle%`, le cas ne
#: pouvait pas se produire. Le graphe candidat du `PLAN-30` le porte : sans cette ligne, une
#: requête sans image de contrôle aurait envoyé `LoadImage(image: "")` à ComfyUI, qui répond
#: par une erreur d'exécution — après le chargement des poids, donc au pire moment.
#:
#: ⚠ `%prompt%` et `%prompt_negatif%` n'y sont PAS et n'y seront jamais : un `%prompt%` non
#: substitué serait un défaut du client, pas une entrée facultative, et élaguer son nœud
#: ferait disparaître l'encodage de texte sans un mot.
MARQUEURS_OPTIONNELS: tuple[str, ...] = ("%reference_", "%entite_", "%masque_",
                                         "%image_controle%")

#: Canal → le champ qui le porte dans `requete.yaml`. Les deux noms diffèrent (le fichier
#: range les canaux sous `canaux:` avec des noms écrits en toutes lettres), et un message
#: d'erreur qui nomme le canal sans nommer le champ envoie l'utilisateur chercher.
CHAMPS_REQUETE: dict[str, str] = {"entites": "entites",
                                  "image_controle": "image_de_controle"}

#: Marqueurs scalaires, toujours substitués — ils ne sont pas des canaux : tout moteur les
#: honore, il n'y a rien à refuser.
SCALAIRES = ("graine", "largeur", "hauteur", "pas", "guidage")

#: Intervalle de sondage de `/history`, en secondes. Une image de 1328 × 1328 se compte en
#: dizaines de secondes : sonder plus vite ferait du bruit sans rien gagner.
SONDAGE = 1.0

#: Durée au-dessous de laquelle une génération n'a **pas eu lieu** : ComfyUI a servi son
#: CACHE D'EXÉCUTION.
#:
#: ⚠ **Ce n'est pas une précaution, c'est un défaut mesuré le 2026-08-30.** ComfyUI met en
#: cache la sortie d'un graphe : deux requêtes au graphe identique ne recalculent pas. C'est
#: légitime — sauf que le cache **survit à une interruption**. Après un `POST /interrupt`, la
#: requête suivante au même graphe a été servie en **1,1 s** avec l'image *partiellement
#: débruitée* du run avorté. Rien ne le signalait côté client : `/history` rendait une image,
#: elle a été marquée et écrite comme les autres, et seule sa mesure d'écart de style —
#: **0,23 au lieu de 0,12** — a trahi la substitution.
#:
#: Le plancher est **2,0 s**, et il vient d'un chiffre : la génération la plus rapide relevée
#: sur cette pile est de **16 s par pas** de débruitage, soit 64 s à 4 pas. Un retour en moins
#: de deux secondes ne peut pas être une diffusion ; c'est le cache.
#:
#: ⚠ **On REFUSE plutôt que d'avertir.** Une image plausible et fausse, écrite avec son
#: marquage et son sidecar, est exactement ce que cette brique existe pour empêcher — et le
#: dépôt refuse déjà partout ailleurs plutôt que de dégrader (`SansReferenceValidee`,
#: `CanalRefuse`, `RequeteNonValidee`). `illustration.comfyui.plancher_secondes: 0` désarme
#: le contrôle pour qui aurait une pile assez rapide pour le faire mentir.
PLANCHER_SECONDES = 2.0

#: Sous-dossier du `input/` de ComfyUI où les références téléversées atterrissent. Un
#: sous-dossier nommé, et pas la racine : l'utilisateur doit pouvoir les distinguer des
#: siennes et les supprimer en bloc.
SOUS_DOSSIER = "angelith"


class ComfyIndisponible(RuntimeError):
    """Le serveur ne répond pas, ou le workflow n'est pas exploitable."""


class Transport:
    """La couche HTTP, isolée pour être remplaçable dans les tests. `urllib` et rien d'autre."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    def _ouvrir(self, requete):
        """`urlopen`, mais qui **rend son corps** quand le serveur répond une erreur.

        ⚠ Sans ça, un refus de ComfyUI arrivait sous la forme « HTTP Error 500: Internal
        Server Error » et rien d'autre — alors que le corps de la réponse porte, sur un 400,
        le `node_errors` qui nomme le nœud et le champ fautifs. Constaté le 2026-08-29 : le
        premier appel réel a coûté un aller-retour dans les logs du serveur pour une cause
        qui tenait en une ligne."""
        try:
            return urllib.request.urlopen(requete, timeout=self.timeout)
        except urllib.error.HTTPError as err:
            corps = ""
            try:
                corps = err.read().decode("utf-8", "replace").strip()
            except Exception:                            # noqa: BLE001 — diagnostic seulement
                corps = ""
            raise ComfyIndisponible(
                f"ComfyUI a répondu HTTP {err.code} sur {requete.selector}.\n"
                f"  {corps[:2000] or '(corps vide — regarde le journal du serveur)'}") from err

    def post_json(self, chemin: str, charge: dict) -> dict:
        requete = urllib.request.Request(
            f"{self.base_url}{chemin}",
            data=json.dumps(charge).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Angelith"},
            method="POST")
        with self._ouvrir(requete) as reponse:
            return json.loads(reponse.read().decode("utf-8") or "{}")

    def get_json(self, chemin: str) -> dict:
        requete = urllib.request.Request(f"{self.base_url}{chemin}",
                                         headers={"User-Agent": "Angelith"})
        with self._ouvrir(requete) as reponse:
            return json.loads(reponse.read().decode("utf-8") or "{}")

    def get_bytes(self, chemin: str, parametres: dict) -> bytes:
        url = f"{self.base_url}{chemin}?{urllib.parse.urlencode(parametres)}"
        requete = urllib.request.Request(url, headers={"User-Agent": "Angelith"})
        with self._ouvrir(requete) as reponse:
            return reponse.read()

    def post_fichier(self, chemin: str, nom: str, octets: bytes, champs: dict) -> dict:
        """`multipart/form-data` écrit à la main — `urllib` et rien d'autre.

        ⚠ Une dépendance (`requests`, `httpx`) pour trois délimiteurs ne se justifierait pas
        dans un dépôt qui a refusé OpenCV pour ~60 Mo. Le format est stable depuis 1998."""
        limite = "----AngelithBoundary" + uuid.uuid4().hex
        morceaux: list[bytes] = []
        for cle, valeur in champs.items():
            morceaux.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{cle}\""
                            f"\r\n\r\n{valeur}\r\n".encode("utf-8"))
        morceaux.append(
            f"--{limite}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"{nom}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
            .encode("utf-8"))
        morceaux.append(octets)
        morceaux.append(f"\r\n--{limite}--\r\n".encode("utf-8"))
        corps = b"".join(morceaux)
        requete = urllib.request.Request(
            f"{self.base_url}{chemin}", data=corps, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={limite}",
                     "Content-Length": str(len(corps)), "User-Agent": "Angelith"})
        with self._ouvrir(requete) as reponse:
            return json.loads(reponse.read().decode("utf-8") or "{}")


class MoteurComfyUI:
    """Envoie un workflow paramétré à un ComfyUI local et rend le premier PNG produit."""

    nom = "comfyui"

    def __init__(self, workflow, *, base_url: str = "http://127.0.0.1:8188",
                 timeout: float = 600.0, transport=None, dossier_tome=None,
                 attente=time.sleep, plancher_secondes: float | None = None) -> None:
        self.workflow_chemin = Path(workflow) if workflow else None
        # ⚠ **Un transport INJECTÉ n'est pas un serveur**, et le plancher mesure un serveur.
        # Un doublon de test rend sa réponse en zéro seconde : lui appliquer le plancher
        # ferait échouer chaque test de la plomberie HTTP sur un contrôle qui, lui, ne peut
        # rien attraper — il n'y a pas de cache d'exécution derrière un doublon. Le défaut
        # suit donc ce qu'on parle : `PLANCHER_SECONDES` vers un vrai serveur, 0 sinon.
        self.plancher_secondes = float(
            plancher_secondes if plancher_secondes is not None
            else (0.0 if transport is not None else PLANCHER_SECONDES))
        self.transport = transport or Transport(base_url, timeout)
        self.timeout = float(timeout)
        self.dossier_tome = Path(dossier_tome) if dossier_tome else None
        self._attente = attente
        self._graphe = None
        #: Cache des téléversements, par chemin résolu — un run de onze images qui partagent
        #: leurs références ne les renvoie pas onze fois.
        self._televersees: dict[str, str] = {}
        self.MOTIFS: dict[str, str] = {}
        self.CANAUX_SUPPORTES = frozenset()
        #: Ce que le graphe déclare EXIGER — voir `_lire_candidat`. Vide sur tout graphe du
        #: chemin nominal, et c'est la règle.
        self.CANAUX_EXIGES: tuple[str, ...] = ()
        self.MOTIFS_EXIGES: dict[str, str] = {}
        #: Le bloc `_candidat` du graphe, ou `{}`. Lu par le validateur du `PLAN-28`.
        self.candidat: dict = {}
        if self.workflow_chemin is not None and self.workflow_chemin.is_file():
            self._charger_workflow()

    # ────────────────────────────  Le graphe  ────────────────────────────

    def _charger_workflow(self) -> None:
        texte = self.workflow_chemin.read_text(encoding="utf-8")
        try:
            self._graphe = json.loads(texte)
        except json.JSONDecodeError as err:
            raise ComfyIndisponible(
                f"{self.workflow_chemin} n'est pas un JSON valide ({err}).\n"
                f"  Attendu : un workflow exporté au FORMAT API depuis ComfyUI "
                f"(menu ⚙ → « Enable Dev mode Options », puis « Save (API Format) »). Un "
                f"export normal ne contient pas les entrées des nœuds.") from err
        if not isinstance(self._graphe, dict) or not self._graphe:
            raise ComfyIndisponible(
                f"{self.workflow_chemin} : le FORMAT API est un objet dont les clés sont des "
                f"identifiants de nœuds. Ce fichier n'en est pas un.\n"
                f"  Dans ComfyUI : ⚙ → « Enable Dev mode Options », puis « Save (API "
                f"Format) ». Un export normal décrit l'écran, pas le graphe.")
        if not _sans_commentaires(self._graphe):
            raise ComfyIndisponible(
                f"{self.workflow_chemin} ne contient aucun nœud : le format API attend des "
                f"objets portant `class_type`. Les clés de commentaire sont tolérées — mais "
                f"il faut au moins un nœud à exécuter.")
        # ⚠ Les canaux se lisent dans les NŒUDS, jamais dans le texte brut du fichier.
        # Scanner le fichier entier faisait qu'un commentaire citant « %reference_1% » — pour
        # expliquer que ce workflow ne le porte PAS — faisait déclarer le canal supporté. Le
        # moteur aurait alors accepté une requête à références et les aurait ignorées en
        # silence : exactement le défaut que tout ce dispositif existe pour empêcher.
        # Trouvé le 2026-08-29, en relisant les deux workflows livrés.
        self.CANAUX_SUPPORTES = frozenset(
            _canaux_du_graphe(json.dumps(_sans_commentaires(self._graphe))))
        self.MOTIFS = {
            canal: (f"le workflow {self.workflow_chemin.name} ne porte aucun marqueur "
                    f"{_marqueur_exemple(canal)} : ajoute-le dans le nœud qui doit recevoir "
                    f"ce canal, ou retire le canal de requete.yaml")
            for canal in CANAUX if canal not in self.CANAUX_SUPPORTES}
        self._lire_candidat()

    def _lire_candidat(self) -> None:
        """Le bloc `_candidat` : ce qu'un graphe **non installé** déclare de lui-même.

        ## Pourquoi un graphe peut se déclarer candidat — `PLAN-30` L30.1

        Le dépôt versionne des graphes qui ont TOURNÉ. Le `PLAN-30` en ajoute un qui n'a pas
        pu : il nomme un poids que la machine de la session n'avait pas, sur une carte qu'elle
        n'avait pas non plus. Le livrer sans le dire aurait deux effets, tous deux mauvais —
        `tools/comfy.py --valider` (sans argument) serait passé en **rouge** sur toute machine
        du monde, y compris celles où tout va bien, et un lecteur aurait cru que le canal est
        livré alors qu'il est seulement **instrumenté**.

        Le bloc porte donc quatre choses, et rien de décoratif :

        | Clé | Ce qu'elle dit |
        |---|---|
        | `motif` | pourquoi ce graphe n'est pas installé, avec sa date |
        | `poids` | le ou les fichiers à déposer, leur source et leur licence |
        | `exige` | les canaux SANS lesquels ce graphe ne s'exécute pas (`CanalExige`) |
        | `mesure` | ce qu'il faut relever avant de le considérer comme livré |

        ⚠ **`_candidat` ne part JAMAIS au serveur** : c'est une clé racine sans `class_type`,
        donc `_sans_commentaires` la retire comme n'importe quel commentaire. Le graphe envoyé
        est identique à ce qu'il serait sans elle."""
        brut = self._graphe.get("_candidat") if isinstance(self._graphe, dict) else None
        self.candidat = dict(brut) if isinstance(brut, dict) else {}
        exiges = self.candidat.get("exige") or ()
        self.CANAUX_EXIGES = tuple(str(c) for c in exiges if str(c) in CANAUX)
        motif = str(self.candidat.get("motif") or "")
        self.MOTIFS_EXIGES = {
            canal: (f"le workflow {self.workflow_chemin.name} porte ce canal EN SÉRIE sur le "
                    f"chemin du modèle : sans lui, le nœud est élagué et le KSampler perd son "
                    f"modèle. Renseigne « {CHAMPS_REQUETE.get(canal, canal)} » sous `canaux:` "
                    f"dans requete.yaml, ou reviens au graphe par défaut de config.yaml."
                    + (f" ({motif})" if motif else ""))
            for canal in self.CANAUX_EXIGES}

    @property
    def graphe(self) -> dict:
        """Le graphe chargé, **sans ses commentaires** — celui que la validation lit.

        En lecture seule par contrat : c'est une copie, et le fichier de l'utilisateur n'est
        jamais réécrit. `{}` quand aucun workflow n'est chargé."""
        return _sans_commentaires(json.loads(json.dumps(self._graphe or {})))

    def disponible(self) -> bool:
        """Le serveur répond-il MAINTENANT ? Ne charge aucun modèle, ne télécharge rien."""
        if self._graphe is None:
            return False
        try:
            self.transport.get_json("/system_stats")
            return True
        except (urllib.error.URLError, OSError, ValueError, ComfyIndisponible):
            return False

    # ────────────────────────────  La génération  ────────────────────────────

    def generer(self, requete) -> Sortie:
        if self._graphe is None:
            raise ComfyIndisponible(
                "aucun workflow chargé — renseigne illustration.comfyui.workflow avec le "
                "chemin d'un export au format API.")
        verifier_canaux(self, requete)
        verifier_canaux_exiges(self, requete)
        graphe, _ = self.graphe_substitue(requete)
        depart = time.monotonic()
        identifiant = str(uuid.uuid4())
        reponse = self.transport.post_json("/prompt", {"prompt": graphe,
                                                       "client_id": identifiant})
        prompt_id = str(reponse.get("prompt_id") or "")
        if not prompt_id:
            raise ComfyIndisponible(
                f"ComfyUI a refusé le workflow : {reponse.get('error') or reponse}\n"
                f"  Le graphe est celui de {self.workflow_chemin} après substitution — un "
                f"marqueur laissé dans un champ numérique est la cause la plus fréquente.")
        images = self._attendre(prompt_id)
        if not images:
            raise ComfyIndisponible(
                f"le workflow s'est exécuté mais n'a produit aucune image (prompt_id "
                f"{prompt_id}). Un nœud SaveImage ou PreviewImage manque-t-il en sortie ?")
        premiere = images[0]
        secondes = time.monotonic() - depart
        self._refuser_le_cache(secondes, prompt_id, premiere)
        octets = self.transport.get_bytes("/view", {
            "filename": premiere.get("filename", ""),
            "subfolder": premiere.get("subfolder", ""),
            "type": premiere.get("type", "output")})
        return Sortie(png=octets, secondes=secondes, provenance={
            "moteur": self.nom,
            "moteur_version": f"workflow:{self.workflow_chemin.name}",
            "prompt_id": prompt_id,
            "fichier_serveur": premiere.get("filename", ""),
            "images_produites": len(images),
            # ⚠ Les fichiers de modèle que le GRAPHE nomme, relevés dans le graphe envoyé et
            # non déclarés à la main. Cf. `modeles_du_graphe` : c'est la seule chose que le
            # client sache vraiment du modèle qui a produit l'image.
            "modeles": modeles_du_graphe(graphe),
            # ⚠ **L28.3 — la différence entre une trace et un souvenir.** Le graphe RÉELLEMENT
            # envoyé, et les lignes du journal du serveur qui disent dans quel régime il a
            # tourné. Sans elles, un run qui a produit une image étrange ne laisse aucun moyen
            # de savoir si le transformeur avait été rogné — donc si l'image vient du régime
            # mesuré ou de l'autre, celui à 64,3 s/pas. Les deux clés sont CONSOMMÉES par
            # `marquage.manifeste` : le graphe part dans un fichier à côté de l'image, jamais
            # dans le bloc tEXt du PNG, qui porte l'identité de l'image et pas un JSON.
            "graphe": graphe,
            "journal_serveur": self.journal_du_serveur(),
        })

    def journal_du_serveur(self) -> dict:
        """Les trois lignes de journal qui décident, si le serveur sait les rendre.

        Best-effort et **jamais bloquant** : une trace qui manque ne doit pas faire échouer un
        run dont l'image est produite. Cf. `illustration/sonde.py:journal_serveur`."""
        from illustration import sonde as sonde_mod

        try:
            return sonde_mod.journal_serveur("", transport=self.transport)
        except Exception as err:                     # noqa: BLE001 — trace, pas chemin nominal
            return {"disponible": False, "motif": f"journal du serveur illisible ({err})"}

    def _refuser_le_cache(self, secondes: float, prompt_id: str, image: dict) -> None:
        """Refuse une « génération » trop rapide pour en être une. Cf. `PLANCHER_SECONDES`.

        ⚠ **Le refus arrive AVANT le téléchargement de l'image**, donc avant le marquage et
        avant l'écriture : aucune image issue du cache n'existe jamais sur le disque, même une
        seconde. C'est la discipline du jugement de nouveauté du lot 25, qui a lieu sur les
        octets rendus et non sur un fichier déjà écrit."""
        if self.plancher_secondes <= 0 or secondes >= self.plancher_secondes:
            return
        raise ComfyIndisponible(
            f"ComfyUI a rendu une image en {secondes:.1f} s (prompt_id {prompt_id}, fichier "
            f"« {image.get('filename', '?')} ») — c'est son CACHE D'EXÉCUTION, pas une "
            f"génération.\n"
            f"  La génération la plus rapide relevée sur cette pile est de 16 s par pas de "
            f"débruitage ; le plancher est de {self.plancher_secondes:.0f} s.\n"
            f"  ⚠ Le cache de ComfyUI SURVIT À UNE INTERRUPTION : mesuré le 2026-08-30, une "
            f"image partiellement débruitée d'un run avorté a été resservie au graphe "
            f"identique suivant, et rien ne l'aurait signalé.\n"
            f"  → redémarre ComfyUI, puis relance. Si ta pile est réellement plus rapide que "
            f"ce plancher, mets illustration.comfyui.plancher_secondes à 0 — et sache alors "
            f"que ce contrôle ne te protège plus.")

    def decharger(self) -> bool:
        """Rend la VRAM : demande à ComfyUI de vider ses modèles et son cache.

        ⚠ **C'est la seconde moitié de la bascule**, et elle manquait jusqu'au 2026-08-29. Le
        `README-ILLUSTRATION-23-27` §4 bis décrit le run comme « déchargement du LLM →
        génération → **le modèle d'image est déchargé, le LLM peut revenir** » : la brique
        faisait la première moitié et pas la seconde, laissant 12 083 Mio occupés après un run.
        Un `run.py` lancé derrière trouvait la carte prise.

        Best-effort, comme `core/power.py:ollama_unload` : un serveur qui ne répond pas ne doit
        pas faire échouer un run déjà terminé et dont les images sont écrites."""
        try:
            self.transport.post_json("/free", {"unload_models": True, "free_memory": True})
            return True
        except (urllib.error.URLError, OSError, ValueError, ComfyIndisponible) as err:
            print(f"    [ComfyUI] déchargement impossible ({err}).")
            return False

    def _attendre(self, prompt_id: str) -> list[dict]:
        """Sonde `/history/<id>` jusqu'à ce que le run apparaisse. ComfyUI n'expose pas de
        blocage côté serveur : le sondage est la seule voie sans WebSocket, et une dépendance
        WebSocket pour attendre un fichier ne se justifierait pas."""
        limite = time.monotonic() + self.timeout
        while time.monotonic() < limite:
            historique = self.transport.get_json(f"/history/{prompt_id}")
            entree = (historique or {}).get(prompt_id)
            if entree:
                statut = (entree.get("status") or {})
                if statut.get("status_str") == "error":
                    raise ComfyIndisponible(
                        f"ComfyUI a échoué pendant l'exécution : "
                        f"{statut.get('messages') or 'sans message'}")
                return [img for sortie in (entree.get("outputs") or {}).values()
                        for img in (sortie.get("images") or [])]
            self._attente(SONDAGE)
        raise ComfyIndisponible(
            f"aucune réponse de ComfyUI après {self.timeout:.0f} s (prompt_id {prompt_id}).\n"
            f"  Ce n'est pas forcément un plantage : une première génération charge les poids, "
            f"ce qui peut dépasser le délai. Monte illustration.comfyui.timeout.")

    def graphe_substitue(self, requete, *, televerser: bool = True) -> tuple[dict, list]:
        """Le graphe **tel qu'il partirait**, et la liste des images qu'il faut téléverser.

        Remplace les marqueurs dans une COPIE du graphe. L'original n'est jamais réécrit —
        c'est le fichier de l'utilisateur, et la frontière d'écriture le refuserait de toute
        façon.

        ⚠ **`televerser=False` est ce qui rend `tools/comfy.py --graphe` possible**, et c'est
        une lecture, pas une demi-génération : le nom sous lequel ComfyUI connaîtra chaque
        image est **calculable sans lui** (`angelith-<empreinte du contenu>`), donc le JSON
        produit est exactement celui qui partirait, sans avoir rien poussé sur le serveur. La
        liste rendue dit lesquelles seraient téléversées, et depuis quel fichier — c'est elle
        qu'un humain relit avant de rejouer le graphe à la main dans ComfyUI."""
        televersements: list[dict] = []
        valeurs = {
            "%prompt%": requete.prompt,
            "%prompt_negatif%": requete.prompt_negatif,
        }
        # ⚠ **Absent veut dire ABSENT, pas « chaîne vide ».** Substituer `%image_controle%`
        # par "" laisserait un `LoadImage(image: "")` dans le graphe ; en le laissant tel
        # quel, `_elaguer` supprime le nœud comme il supprime une référence non fournie.
        if requete.image_controle:
            valeurs["%image_controle%"] = self._pour_comfy(
                requete.image_controle, televerser, televersements, "image_controle")
        for i, reference in enumerate(requete.references, start=1):
            valeurs[f"%reference_{i}%"] = self._pour_comfy(
                reference, televerser, televersements, f"reference_{i}")
        for i, entite in enumerate(requete.entites, start=1):
            valeurs[f"%entite_{i}%"] = entite.prompt
            valeurs[f"%masque_{i}%"] = self._pour_comfy(
                entite.masque, televerser, televersements, f"masque_{i}")
        scalaires = {f"%{nom}%": getattr(requete, nom) for nom in SCALAIRES}
        graphe = _remplacer(json.loads(json.dumps(self._graphe)), valeurs, scalaires)
        return _elaguer(_sans_commentaires(graphe)), televersements

    def _pour_comfy(self, relatif: str, televerser: bool = True,
                    televersements: list | None = None, canal: str = "") -> str:
        """Le nom sous lequel ComfyUI connaîtra cette image — après **téléversement**.

        ⚠ **Un chemin absolu ne marche pas, et ce n'est pas une supposition** : mesuré le
        2026-08-29, `LoadImage` refuse
        `C:\\…\\media\\….jpeg` avec « Invalid image file ». ComfyUI ne résout ses images que
        sous son propre dossier `input/`. Il faut donc les lui **donner**, par
        `POST /upload/image`, et se servir du nom qu'il rend.

        ⚠ **Conséquence, et elle se dit plutôt qu'elle ne se cache : une copie de l'extrait
        atterrit dans le dossier `input/` de ComfyUI.** La frontière d'Angelith couvre SES
        écritures, pas celles d'un programme tiers que l'utilisateur a installé — c'est déjà
        vrai en sortie (le `SaveImage` de ComfyUI garde une copie non marquée) et ça le
        devient en entrée. Ces copies sont des extraits de l'œuvre, elles restent locales, et
        les supprimer ne casse rien."""
        if not relatif:
            return ""
        source = Path(relatif)
        if not source.is_absolute() and self.dossier_tome is not None:
            source = self.dossier_tome / relatif
        if not source.is_file():
            raise ComfyIndisponible(
                f"image de référence introuvable : {source}\n"
                f"  Elle est nommée dans requete.yaml mais absente du disque ; ComfyUI ne "
                f"peut pas la recevoir.")
        nom = self.televerser(source) if televerser else nom_televerse(source)
        if televersements is not None:
            televersements.append({"canal": canal, "source": str(source), "nom": nom,
                                   "televerse": bool(televerser)})
        return nom

    def televerser(self, source) -> str:
        """Téléverse une image dans le dossier `input/` de ComfyUI et rend son nom annoté.

        Le nom porte l'empreinte du contenu : deux appels sur le même fichier écrivent le
        même nom, donc le dossier de ComfyUI ne gonfle pas d'un run à l'autre, et deux runs
        de même requête envoient le même graphe — ce que la reproductibilité de L24.5 exige."""
        source = Path(source)
        octets = source.read_bytes()
        cle = str(source.resolve())
        if cle in self._televersees:
            return self._televersees[cle]
        nom = Path(nom_televerse(source)).name
        reponse = self.transport.post_fichier(
            "/upload/image", nom, octets,
            {"type": "input", "subfolder": SOUS_DOSSIER, "overwrite": "true"})
        rendu = str(reponse.get("name") or nom)
        sous = str(reponse.get("subfolder") or "")
        annote = f"{sous}/{rendu}" if sous else rendu
        self._televersees[cle] = annote
        return annote


def nom_televerse(source) -> str:
    """Le nom que ce fichier portera dans le `input/` de ComfyUI — **calculé, pas demandé**.

    Le nom porte l'empreinte du contenu : deux appels sur le même fichier écrivent le même
    nom, donc le dossier de ComfyUI ne gonfle pas d'un run à l'autre, et deux runs de même
    requête envoient le même graphe — ce que la reproductibilité de L24.5 exige.

    ⚠ **Il est calculable hors ligne, et c'est ce qui permet à `--graphe` de montrer le graphe
    exact sans rien envoyer.** La seule réserve : c'est le serveur qui a le dernier mot sur le
    nom rendu ; `televerser` prend donc celui qu'il rend, et non celui-ci, quand il répond."""
    source = Path(source)
    empreinte = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    return f"{SOUS_DOSSIER}/angelith-{empreinte}{source.suffix.lower() or '.png'}"


def _sans_commentaires(graphe: dict) -> dict:
    """Retire les clés racine qui ne sont pas des nœuds, avant d'envoyer le graphe.

    ⚠ **ComfyUI itère sur TOUTES les clés racine** et appelle `.get('_meta')` sur chacune :
    une clé de commentaire dont la valeur est une liste le fait tomber en `AttributeError`,
    renvoyée au client en « HTTP 500 Internal Server Error » sans autre indication. Constaté
    le 2026-08-29, au premier appel réel.

    Le dépôt vit de fichiers commentés — `config.yaml` est « un document » — et un workflow
    écrit à la main mérite de dire ce qu'il fait. On garde donc le droit de commenter, et
    c'est le client qui nettoie juste avant l'envoi. Un nœud est un objet portant
    `class_type` ; tout le reste est de la prose."""
    return {cle: valeur for cle, valeur in graphe.items()
            if isinstance(valeur, dict) and "class_type" in valeur}


#: Les entrées de nœud qui nomment un fichier de modèle, quel que soit le nœud. La liste est
#: explicite plutôt que devinée par suffixe : `image_name` ou `filename_prefix` ne sont pas des
#: modèles, et les confondre écrirait un nom de sortie dans la provenance.
CHAMPS_MODELE = ("unet_name", "ckpt_name", "clip_name", "clip_name1", "clip_name2",
                 "vae_name", "lora_name", "control_net_name", "style_model_name",
                 "gguf_name", "model_name")


def modeles_du_graphe(graphe: dict) -> list[str]:
    """Les fichiers de modèle que le graphe nomme, triés — **relevés, jamais déclarés**.

    ⚠ **C'est un correctif de provenance, pas une commodité.** `requete.yaml` porte un champ
    `modele`, écrit par la phase 1 d'après la configuration **d'alors**, et la phase 2 le
    recopiait tel quel dans le sidecar. Changer de workflow entre les deux phases suffisait
    donc à écrire, dans un manifeste de provenance, le nom d'un modèle qui **n'a pas produit
    l'image** — constaté le 2026-08-29, où un `requete.yaml` validé la veille annonçait
    `qwen-image-2512-Q4_1` alors que le graphe d'édition chargeait
    `qwen-image-edit-2511-Q4_1`.

    Un manifeste qui se trompe de modèle est pire qu'un manifeste sans modèle : il a l'air
    vérifiable."""
    trouves = {str(valeur)
               for noeud in graphe.values() if isinstance(noeud, dict)
               for champ, valeur in (noeud.get("inputs") or {}).items()
               if champ in CHAMPS_MODELE and isinstance(valeur, str) and valeur.strip()}
    return sorted(trouves)


def _elaguer(graphe: dict) -> dict:
    """Retire les nœuds dont un marqueur INDEXÉ est resté sans valeur, et les liens vers eux.

    ⚠ **Sans ça, un graphe à trois références ne saurait recevoir qu'exactement trois
    références.** Le nœud `TextEncodeQwenImageEditPlus` de ComfyUI expose `image1`, `image2`
    et `image3` en entrées **optionnelles** ; le graphe livré les câble toutes les trois. Une
    requête à une seule référence laisserait `%reference_2%` tel quel dans un `LoadImage`, et
    ComfyUI refuserait le graphe entier pour un fichier nommé « %reference_2% ».

    L'élagage est donc ce qui rend le **balayage du nombre de références** possible avec UN
    seul workflow — sinon il en faudrait trois, qui divergeraient au premier réglage changé.

    La suppression est **transitive** : un nœud dont une entrée pointait vers un nœud supprimé
    est supprimé à son tour, sauf si cette entrée est optionnelle pour ComfyUI — ce que le
    client ne peut pas savoir. On retire donc simplement le lien, et ComfyUI tranche : c'est
    lui qui connaît la signature de ses nœuds, et son message d'erreur nomme le champ."""
    restants = {cle: valeur for cle, valeur in graphe.items()
                if not _marqueur_residuel(valeur.get("inputs"))}
    if len(restants) == len(graphe):
        return graphe
    retires = set(graphe) - set(restants)
    return {cle: {**valeur, "inputs": _sans_liens(valeur.get("inputs") or {}, retires)}
            for cle, valeur in restants.items()}


def _marqueur_residuel(noeud) -> bool:
    """Reste-t-il un marqueur OPTIONNEL non substitué quelque part dans ce nœud ?

    Seuls les marqueurs de `MARQUEURS_OPTIONNELS` comptent — voir sa note : `%prompt%` non
    substitué serait un défaut du client, pas une entrée facultative, et le taire ferait
    disparaître un nœud utile."""
    if isinstance(noeud, dict):
        return any(_marqueur_residuel(v) for v in noeud.values())
    if isinstance(noeud, list):
        return any(_marqueur_residuel(v) for v in noeud)
    if not isinstance(noeud, str):
        return False
    return any(marqueur in noeud for marqueur in MARQUEURS_OPTIONNELS)


def _sans_liens(inputs: dict, retires: set) -> dict:
    """Les entrées d'un nœud, privées des liens vers un nœud supprimé.

    Un lien ComfyUI est `[identifiant de nœud, numéro de sortie]` : une liste de deux éléments
    dont le premier est une chaîne. Rien d'autre dans le format API n'a cette forme."""
    return {cle: valeur for cle, valeur in inputs.items()
            if not (isinstance(valeur, list) and len(valeur) == 2
                    and isinstance(valeur[0], str) and valeur[0] in retires)}


def _canaux_du_graphe(texte: str) -> set[str]:
    return {canal for marqueur, canal in MARQUEURS.items() if marqueur in texte}


def _marqueur_exemple(canal: str) -> str:
    for marqueur, cible in MARQUEURS.items():
        if cible == canal:
            return marqueur if marqueur.endswith("%") else marqueur + "1%"
    return f"%{canal}%"


def _remplacer(noeud, valeurs: dict, scalaires: dict):
    """Substitution en profondeur.

    ⚠ Deux régimes, et la distinction compte : un marqueur **seul** dans un champ prend le
    type de sa valeur (`"%graine%"` devient l'entier 42, pas la chaîne « 42 » — ComfyUI
    refuserait la chaîne) ; un marqueur **dans** une phrase est interpolé en texte."""
    if isinstance(noeud, dict):
        return {c: _remplacer(v, valeurs, scalaires) for c, v in noeud.items()}
    if isinstance(noeud, list):
        return [_remplacer(v, valeurs, scalaires) for v in noeud]
    if not isinstance(noeud, str):
        return noeud
    if noeud in scalaires:
        return scalaires[noeud]
    if noeud in valeurs:
        return valeurs[noeud]
    sortie = noeud
    for marqueur, valeur in {**valeurs, **scalaires}.items():
        if marqueur in sortie:
            sortie = sortie.replace(marqueur, str(valeur))
    return sortie
