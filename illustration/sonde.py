# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Ce que le serveur ComfyUI expose **réellement** — relevé sur son API, jamais supposé.

## Pourquoi ce module existe, et pourquoi il n'est pas dans `tools/`

`tools/banc_prompt.py` savait déjà interroger `/object_info` et `/system_stats` : c'est lui
qui a relevé les 907 nœuds du 2026-08-30. Le `PLAN-28` demande une sonde utilisable par
`run_illustration.py --check` **avant** le GPU. Un second sondeur écrit à côté du premier
aurait divergé — et `core/config_schema.py` dit en tête ce que ça coûte : « une liste
recopiée à la main dérive, et une référence qui dérive produit de **faux** avertissements —
ce qui est pire que pas de vérification du tout ».

Le code de sondage est donc **ici**, dans la brique, et les deux appelants le partagent :
`tools/comfy.py --sonde` et `illustration/validation.py`, que `--check` fait tourner.

## Ce que la sonde rend, et ce qu'elle ne prétend pas

Elle rend un `Releve` **gelé** : la version du serveur, ses appareils avec leur VRAM, la liste
de ses nœuds, le **contenu des listes déroulantes** de chaque nœud, et les modules tiers qui
ont fourni ces nœuds. Rien d'autre.

⚠ **Un serveur injoignable ne produit pas un relevé vide, il produit un relevé qui le DIT.**
`joignable: False` et `erreur` renseignée. La distinction est tout le module : un validateur
qui prendrait « aucun nœud relevé » pour « aucun nœud n'existe » refuserait chaque workflow du
dépôt dès que ComfyUI est éteint, ce qui est exactement le faux avertissement qu'on cherche à
éviter.

⚠ **La sonde ne génère RIEN.** Elle n'appelle que des routes en lecture — `GET /system_stats`,
`GET /object_info`, `GET /internal/logs/raw`. Générer reste le travail de
`run_illustration.py`, qui porte la porte humaine et le marquage ; une seconde voie capable
d'envoyer un `/prompt` serait une seconde porte, non gardée.

## L'installation : ce qui se déduit, et ce qui ne se déduit pas

Le document de mesure du 2026-08-29 dit « standalone `win-amd` », l'utilisateur décrit une
installation **Desktop**, et les deux ne rangent pas les modèles au même endroit. La sonde
tranche ce qu'elle peut trancher **avec une preuve** :

- `system.embedded_python` vaut `true` sur un portable/standalone (le Python est celui du zip) ;
- `system.argv[0]` donne le chemin du `main.py` lancé, donc le dossier d'installation ;
- si ce dossier est lisible depuis cette machine, `extra_model_paths.yaml` et `models/` s'y
  cherchent.

Ce qui ne se déduit pas est **dit comme tel** (`variante: "indéterminée"`) plutôt que deviné.
"""
from __future__ import annotations

import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

#: Délai des appels de sondage. Plus long que celui de `/system_stats` parce que
#: `/object_info` sérialise 907 nœuds et leurs listes : mesuré à quelques centaines de
#: millisecondes le 2026-08-30, mais un serveur qui charge un modèle au même moment traîne.
TIMEOUT = 30.0

#: Le préfixe de module que ComfyUI donne aux nœuds venus de `custom_nodes/`. C'est la seule
#: façon **mécanique** de répondre à « quels nœuds tiers sont installés » : la liste des
#: dossiers de `custom_nodes/` ne dit pas lesquels ont réellement chargé.
PREFIXE_TIERS = "custom_nodes."


@dataclass(frozen=True)
class Appareil:
    """Un appareil de calcul vu par ComfyUI, avec ses deux chiffres de VRAM."""

    nom: str = ""
    type: str = ""
    vram_total: int = 0
    vram_libre: int = 0
    #: Ce que PyTorch **réserve** déjà : c'est ce qu'un `POST /free` rendrait.
    torch_total: int = 0
    torch_libre: int = 0

    @property
    def marge_octets(self) -> int:
        """La VRAM qu'une génération pourrait réellement occuper : le libre **plus** ce que
        PyTorch garde en réserve.

        ⚠ **Sans ce « plus », la vérification de VRAM serait un faux avertissement à chaque
        seconde génération.** Après un run, ComfyUI garde 12 083 Mio résidents (mesuré le
        2026-08-29) : le libre tombe alors sous le pic, alors que relancer le même graphe ne
        recharge rien du tout. Ce que PyTorch a réservé lui revient ; le compter au crédit est
        la seule lecture qui ne mente pas dans les deux sens."""
        return int(self.vram_libre or 0) + int(self.torch_total or 0)


@dataclass(frozen=True)
class Releve:
    """L'état du serveur à un instant, gelé. Rien ici n'est déduit sans sa preuve."""

    base_url: str
    date: str = ""
    joignable: bool = False
    erreur: str = ""
    version: str = ""
    python: str = ""
    pytorch: str = ""
    os: str = ""
    python_embarque: bool | None = None
    argv: tuple[str, ...] = ()
    appareils: tuple[Appareil, ...] = ()
    #: `class_type` → module qui l'a fourni. Les clés sont l'inventaire des nœuds exposés.
    modules: dict = field(default_factory=dict)
    #: `class_type` → `{champ: (valeurs de la liste déroulante)}`. C'est ce qui permet de dire
    #: qu'un fichier de modèle nommé dans un graphe **n'est pas** sur cette machine.
    listes: dict = field(default_factory=dict)

    # ────────────────────────────  Lectures  ────────────────────────────

    @property
    def noeuds(self) -> frozenset:
        return frozenset(self.modules)

    def expose(self, class_type: str) -> bool:
        return str(class_type) in self.modules

    def liste(self, class_type: str, champ: str):
        """Les valeurs que ce nœud propose pour ce champ, ou `None` si **on ne sait pas**.

        ⚠ `None` et `()` ne veulent pas dire la même chose, et les confondre serait le défaut
        du module : `()` est une liste **vide** — le nœud existe, le dossier de modèles est
        vide, et c'est un constat (c'est exactement l'état de `ModelPatchLoader` relevé le
        2026-08-30) ; `None` veut dire que le serveur n'a pas répondu, et on ne conclut rien."""
        if not self.joignable:
            return None
        champs = self.listes.get(str(class_type))
        if champs is None:
            return None
        return champs.get(str(champ))

    @property
    def tiers(self) -> dict:
        """Les nœuds venus de `custom_nodes/`, groupés par module tiers, triés."""
        groupes: dict[str, list[str]] = {}
        for noeud, module in self.modules.items():
            if str(module).startswith(PREFIXE_TIERS):
                groupes.setdefault(str(module)[len(PREFIXE_TIERS):], []).append(noeud)
        return {module: sorted(noeuds) for module, noeuds in sorted(groupes.items())}

    @property
    def appareil_principal(self):
        return self.appareils[0] if self.appareils else None

    @property
    def variante(self) -> str:
        """« portable/standalone », « installée (Desktop ou venv) » ou « indéterminée ».

        ⚠ La sonde ne sait PAS distinguer une installation Desktop d'un `git clone` dans un
        venv : les deux lancent un Python non embarqué. Elle le dit au lieu de choisir."""
        if not self.joignable or self.python_embarque is None:
            return "indéterminée"
        return "portable/standalone" if self.python_embarque else "installée (Desktop ou venv)"

    @property
    def dossier_installation(self):
        """Le dossier du `main.py` que le serveur exécute, s'il est lisible **d'ici**.

        Rend `None` sur une machine qui n'est pas celle du serveur — c'est le cas nominal
        quand `base_url` n'est pas `127.0.0.1`, et il ne vaut pas un avertissement."""
        if not self.argv:
            return None
        principal = Path(str(self.argv[0]))
        dossier = principal.parent if principal.suffix else principal
        return dossier if dossier.is_dir() else None

    def dossiers_de_modeles(self) -> dict:
        """Où ce serveur lit ses modèles, **relevé sur le disque** quand il est lisible d'ici.

        Rend `{"installation": …, "models": …, "extra_model_paths": … | None}`. Les valeurs
        absentes sont `None` : c'est la seule information de l'étape 0 du `PLAN-28` qui ne se
        déduit de rien, et une case vide vaut mieux qu'un chemin plausible et faux."""
        installation = self.dossier_installation
        if installation is None:
            return {"installation": None, "models": None, "extra_model_paths": None}
        modeles = installation / "models"
        extra = installation / "extra_model_paths.yaml"
        return {"installation": installation,
                "models": modeles if modeles.is_dir() else None,
                "extra_model_paths": extra if extra.is_file() else None}

    def resume(self) -> list[str]:
        """Les lignes que `--sonde` et `--check` impriment. Une mesure, une ligne."""
        if not self.joignable:
            return [f"Serveur {self.base_url} : INJOIGNABLE — {self.erreur}",
                    "  → lance ComfyUI, ou corrige illustration.comfyui.base_url."]
        lignes = [f"Serveur {self.base_url} : ComfyUI {self.version or '?'} "
                  f"({self.variante})",
                  f"  Python {self.python or '?'} · PyTorch {self.pytorch or '?'} · "
                  f"{self.os or '?'}",
                  f"  Nœuds exposés : {len(self.modules)}"]
        tiers = self.tiers
        if tiers:
            lignes.append("  Nœuds tiers : " + ", ".join(
                f"{module} ({len(noeuds)})" for module, noeuds in tiers.items()))
        else:
            lignes.append("  Nœuds tiers : aucun — tout vient de ComfyUI lui-même.")
        for appareil in self.appareils:
            lignes.append(
                f"  {appareil.nom or appareil.type} : {mio(appareil.vram_total)} Mio au "
                f"total, {mio(appareil.vram_libre)} libres, {mio(appareil.torch_total)} "
                f"réservés par PyTorch → marge {mio(appareil.marge_octets)} Mio")
        dossiers = self.dossiers_de_modeles()
        if dossiers["installation"] is not None:
            lignes.append(f"  Installation : {dossiers['installation']}")
            lignes.append(f"  Modèles : {dossiers['models'] or 'dossier models/ introuvable'}")
            lignes.append("  extra_model_paths.yaml : "
                          + (str(dossiers["extra_model_paths"]) if dossiers["extra_model_paths"]
                             else "absent — les modèles sont lus sous l'installation"))
        else:
            lignes.append("  Installation : non lisible depuis cette machine — le serveur "
                          "n'y tourne pas, ou son argv n'est pas exposé.")
        return lignes


def mio(octets) -> str:
    """Des octets en Mio, avec l'espace fine du dépôt. `—` sur une valeur absente."""
    if not octets:
        return "—"
    return f"{int(octets) / 1048576:,.0f}".replace(",", " ")


def sonder(base_url: str, *, transport=None, timeout: float = TIMEOUT) -> Releve:
    """Interroge le serveur et rend son `Releve`. **Ne lève jamais** : un serveur éteint est
    une situation, pas une panne, et l'appelant en fait ce qu'il veut."""
    from illustration.comfyui import ComfyIndisponible, Transport

    base = str(base_url or "").rstrip("/")
    date = datetime.now(timezone.utc).isoformat(timespec="seconds")
    canal = transport or Transport(base, timeout)
    try:
        stats = canal.get_json("/system_stats") or {}
        info = canal.get_json("/object_info") or {}
    except (urllib.error.URLError, OSError, ValueError, ComfyIndisponible) as err:
        return Releve(base_url=base, date=date, erreur=str(err))
    systeme = dict(stats.get("system") or {})
    return Releve(
        base_url=base, date=date, joignable=True,
        version=str(systeme.get("comfyui_version") or ""),
        python=str(systeme.get("python_version") or "").split(" ")[0],
        pytorch=str(systeme.get("pytorch_version") or ""),
        os=str(systeme.get("os") or ""),
        python_embarque=(bool(systeme["embedded_python"])
                         if "embedded_python" in systeme else None),
        argv=tuple(str(a) for a in (systeme.get("argv") or [])),
        appareils=tuple(_appareil(d) for d in (stats.get("devices") or [])),
        modules=_modules(info), listes=_listes(info))


def journal_serveur(base_url: str, *, transport=None, timeout: float = 10.0,
                    lignes: int = 6) -> dict:
    """Les lignes de journal du serveur **qui décident** — L28.3.

    Trois familles, et le `§5` de `docs/procedures/comfyui.md` dit pourquoi ce sont
    celles-là : `loaded completely` / `loaded partially` (le transformeur a-t-il été rogné ?),
    `lowvram patches: N` (de combien ?), `Prompt executed in …` (le temps réel).

    ⚠ **Ce n'est pas une corrélation par `prompt_id`, et il ne faut pas le lire comme telle.**
    ComfyUI n'étiquette pas ses lignes de journal par requête : on prend la **queue** du
    journal au moment où l'image est récupérée. Sur un serveur qui ne sert que ce run — le
    cas nominal, puisque la carte est bloquée pendant la génération — c'est la bonne fenêtre ;
    sur un serveur partagé, ce sont les dernières lignes, et le champ `corrélation` le dit.

    Rend toujours un dictionnaire, jamais une exception : une trace qui manque ne doit pas
    faire échouer un run dont l'image est produite."""
    from illustration.comfyui import ComfyIndisponible, Transport

    canal = transport or Transport(str(base_url or "").rstrip("/"), timeout)
    try:
        brut = canal.get_json("/internal/logs/raw") or {}
    except (urllib.error.URLError, OSError, ValueError, ComfyIndisponible) as err:
        return {"disponible": False,
                "motif": f"journal du serveur illisible ({err}) — serveur éteint, ou route "
                         f"/internal/logs/raw absente de cette version de ComfyUI"}
    entrees = _entrees_de_journal(brut)
    if not entrees:
        return {"disponible": False,
                "motif": "le serveur a répondu, mais son journal est vide ou d'une forme "
                         "inconnue de cette version d'Angelith."}
    retenues = [ligne for ligne in entrees if _ligne_qui_decide(ligne)][-int(lignes):]
    return {"disponible": True, "correlation": "queue du journal, pas de filtrage par "
                                               "prompt_id — ComfyUI n'en étiquette pas ses "
                                               "lignes",
            "lignes": retenues,
            "rogne": any("loaded partially" in ligne or "lowvram patches" in ligne
                         for ligne in retenues)}


#: Les fragments de ligne qui portent une décision. Écrits en clair plutôt que par expression
#: régulière : ce sont des chaînes littérales de ComfyUI, et une regex ferait croire à une
#: souplesse qui n'existe pas.
FRAGMENTS_QUI_DECIDENT = ("loaded completely", "loaded partially", "lowvram patches",
                          "Prompt executed in", "Requested to load")


def _ligne_qui_decide(ligne: str) -> bool:
    return any(fragment in ligne for fragment in FRAGMENTS_QUI_DECIDENT)


def _entrees_de_journal(brut) -> list[str]:
    """La route rend `{"entries": [{"t": …, "m": "…"}]}`. On tolère une chaîne brute et une
    liste nue : la forme a changé une fois en amont, et deviner coûte moins qu'échouer."""
    if isinstance(brut, str):
        return [ligne.rstrip() for ligne in brut.splitlines() if ligne.strip()]
    if isinstance(brut, dict):
        brut = brut.get("entries") or brut.get("logs") or []
    if not isinstance(brut, list):
        return []
    lignes: list[str] = []
    for entree in brut:
        texte = entree.get("m") if isinstance(entree, dict) else entree
        if not isinstance(texte, str):
            continue
        lignes += [morceau.rstrip() for morceau in texte.splitlines() if morceau.strip()]
    return lignes


def _appareil(brut: dict) -> Appareil:
    return Appareil(nom=str(brut.get("name") or ""), type=str(brut.get("type") or ""),
                    vram_total=int(brut.get("vram_total") or 0),
                    vram_libre=int(brut.get("vram_free") or 0),
                    torch_total=int(brut.get("torch_vram_total") or 0),
                    torch_libre=int(brut.get("torch_vram_free") or 0))


def _modules(info: dict) -> dict:
    return {str(nom): str((entree or {}).get("python_module") or "nodes")
            for nom, entree in (info or {}).items() if isinstance(entree, dict)}


def _listes(info: dict) -> dict:
    """`class_type` → `{champ: (valeurs)}`, pour les seuls champs qui sont une liste de choix.

    Dans `/object_info`, une entrée de nœud est `[spécification, options]` ; la spécification
    est une **chaîne** pour un type (`"MODEL"`, `"INT"`) et une **liste** pour une liste
    déroulante. C'est cette liste qui porte les noms de fichiers de modèle présents sur la
    machine, et c'est tout l'intérêt de la sonde."""
    sortie: dict[str, dict] = {}
    for nom, entree in (info or {}).items():
        if not isinstance(entree, dict):
            continue
        champs: dict[str, tuple] = {}
        entrees = entree.get("input") or {}
        for groupe in ("required", "optional"):
            for champ, spec in (entrees.get(groupe) or {}).items():
                valeurs = spec[0] if isinstance(spec, list) and spec else None
                if isinstance(valeurs, list):
                    champs[str(champ)] = tuple(str(v) for v in valeurs)
        if champs:
            sortie[str(nom)] = champs
    return sortie


def depuis_config(config: dict, *, transport=None) -> Releve:
    """La sonde branchée sur `illustration.comfyui.base_url`. Le seul point qui lit la config
    — les appelants passent ensuite le `Releve`, jamais la config."""
    from illustration.orchestrateur import reglages

    return sonder(reglages(config)["comfyui"]["base_url"], transport=transport)
