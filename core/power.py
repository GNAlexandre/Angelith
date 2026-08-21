# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Gestion de l'alimentation pendant un run (utile pour les tomes longs, la nuit) :

- `keep_awake()` empêche la mise en veille / veille prolongée du PC tant que le
  process tourne (l'écran, lui, peut s'éteindre). L'effet est automatiquement levé
  à la fin du process — pas besoin de désactiver la veille globalement dans Windows.
- `shutdown(delay)` programme l'extinction du PC après un délai ANNULABLE, pour ne
  pas laisser la machine allumée toute la nuit une fois le travail fini (ou planté).

Centré Windows (plateforme principale ici), avec repli macOS/Linux au mieux.
"""
from __future__ import annotations

import subprocess
import sys

_IS_WIN = sys.platform.startswith("win")
_IS_MAC = sys.platform == "darwin"

# Constantes Windows (SetThreadExecutionState)
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002   # empêche AUSSI la veille écran/GPU (crucial pour l'inférence)

_keepawake_thread = None
_keepawake_stop = None


def ollama_load(base_url: str, model: str, timeout: int = 120) -> bool:
    """Précharge un modèle en mémoire côté Ollama (une requête vide qui force le
    chargement). Renvoie True si OK. Best-effort : un échec n'est pas bloquant (le
    modèle se chargera de toute façon à la première vraie requête)."""
    try:
        from openai import OpenAI
        client = OpenAI(base_url=base_url, api_key="ollama", timeout=timeout)
        client.chat.completions.create(
            model=model, max_tokens=1, temperature=0,
            messages=[{"role": "user", "content": "ok"}])
        return True
    except Exception as err:
        print(f"    [Ollama] préchargement de « {model} » impossible ({err}). "
              f"Le modèle se chargera à la première requête.")
        return False


def racine_ollama(base_url: str) -> str:
    """`http://hôte:11434/v1` (OpenAI) → `http://hôte:11434` (API native d'Ollama)."""
    root = (base_url or "").rstrip("/")
    return root[:-3] if root.endswith("/v1") else root


def contexte_charge(base_url: str, model: str, timeout: int = 10) -> int | None:
    """Taille de contexte RÉELLE du modèle chargé, lue sur `/api/ps`. `None` si indisponible.

    ⚠ Cette fonction existe parce qu'une valeur déclarative fausse est **pire qu'absente**.
    `config.yaml` annonçait `llm.num_ctx: 65536` quand le Modelfile en servait 32 768 : le
    garde-fou de lot croyait disposer de 55 705 tokens utiles là où le plafond réel est
    27 852. Et Ollama ne dégrade pas progressivement — mesuré sur ce serveur, un prompt de
    ~33 200 tokens est **silencieusement ramené à 16 386**, soit plus de la moitié du contexte
    jetée sans un mot. Un lot de 20 planches avec raisonnement débordait donc en silence.

    Best-effort et non bloquant : un serveur muet, un modèle pas encore chargé ou un Ollama
    trop ancien renvoient `None`, et l'appelant se contente alors de la valeur déclarée."""
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(f"{racine_ollama(base_url)}/api/ps",
                                    timeout=timeout) as reponse:
            charge = json.loads(reponse.read().decode("utf-8"))
    except Exception:
        return None
    for entree in (charge.get("models") or []):
        nom = entree.get("name") or entree.get("model") or ""
        # Ollama nomme parfois « qwen3.6:27b » et parfois « qwen3.6:27b » suffixé : on accepte
        # le préfixe, pour ne pas rater le modèle sur une différence de tag.
        if nom == model or nom.startswith(model.split(":")[0]):
            ctx = entree.get("context_length") or (entree.get("details") or {}).get("context_length")
            if ctx:
                return int(ctx)
    return None


def ollama_unload(base_url: str, model: str, timeout: int = 30) -> bool:
    """Décharge un modèle de la mémoire d'Ollama (libère la VRAM) via keep_alive=0.
    Utilise l'endpoint natif /api/generate d'Ollama (dérivé du base_url OpenAI).
    Best-effort : renvoie True si la requête a abouti."""
    try:
        import json
        import urllib.request

        # base_url OpenAI = http://host:11434/v1 → racine Ollama = http://host:11434
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        req = urllib.request.Request(
            f"{root}/api/generate",
            data=json.dumps({"model": model, "keep_alive": 0}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=timeout).read()
        return True
    except Exception as err:
        print(f"    [Ollama] déchargement de « {model} » impossible ({err}).")
        return False


def keep_awake() -> bool:
    """Empêche la veille SYSTÈME **et écran/GPU** pendant le run. Renvoie True si activé.

    Deux protections :
    1. `ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED` : empêche à la fois la mise en veille
       de la machine ET celle de l'écran. Le flag écran est crucial ici : quand l'écran
       s'endort, le GPU réduit fortement sa fréquence, ce qui fait chuter l'inférence
       (symptôme observé : un bloc à 0,4 tok/s au lieu de ~50). 
    2. Un thread de fond ré-arme le flag toutes les 30 s : `SetThreadExecutionState` peut
       être écrasé par une stratégie d'alimentation agressive ; le rappel périodique
       garantit que l'inhibition tient sur un run de plusieurs heures."""
    global _keepawake_thread, _keepawake_stop
    if not _IS_WIN:
        return False  # (repli macOS/Linux : voir start_inhibitor ci-dessous)
    try:
        import ctypes
        import threading
        flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
        if ctypes.windll.kernel32.SetThreadExecutionState(flags) == 0:
            return False
        _keepawake_stop = threading.Event()

        def _refresh():
            # Ré-arme le flag régulièrement. IMPORTANT : SetThreadExecutionState est lié
            # au thread appelant, donc on le rappelle DEPUIS ce thread de fond en boucle.
            while not _keepawake_stop.wait(30):
                try:
                    ctypes.windll.kernel32.SetThreadExecutionState(flags)
                except Exception:
                    break

        _keepawake_thread = threading.Thread(target=_refresh, daemon=True)
        _keepawake_thread.start()
        return True
    except Exception:
        return False


def release() -> None:
    """Lève l'empêchement de veille (rend la main à Windows) et arrête le rafraîchissement."""
    global _keepawake_thread, _keepawake_stop
    if _keepawake_stop is not None:
        _keepawake_stop.set()
        _keepawake_thread = _keepawake_stop = None
    if _IS_WIN:
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        except Exception:
            pass


def start_inhibitor():
    """macOS/Linux : lance un process compagnon qui empêche la veille (à terminer via
    stop_inhibitor). Sur Windows, renvoie None (on utilise keep_awake/release)."""
    if _IS_MAC:
        try:
            return subprocess.Popen(["caffeinate", "-s"])
        except Exception:
            return None
    if not _IS_WIN:  # Linux avec systemd
        try:
            return subprocess.Popen(
                ["systemd-inhibit", "--what=sleep", "--why=Angelith", "sleep", "infinity"])
        except Exception:
            return None
    return None


def stop_inhibitor(proc) -> None:
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass


def cancel_shutdown() -> str:
    """Annule une extinction programmée par `shutdown()`. Renvoie une note best-effort."""
    if _IS_WIN:
        subprocess.run(["shutdown", "/a"], check=False)
        return "shutdown /a"
    if not _IS_MAC:  # Linux
        subprocess.run(["shutdown", "-c"], check=False)
        return "shutdown -c"
    return ""


def shutdown(delay_seconds: int = 120, reason: str = "Angelith termine") -> str:
    """Programme l'extinction du PC après `delay_seconds`. Renvoie la commande pour ANNULER."""
    delay_seconds = max(5, int(delay_seconds))
    if _IS_WIN:
        subprocess.run(["shutdown", "/s", "/t", str(delay_seconds), "/c", reason], check=False)
        return "shutdown /a"
    if _IS_MAC:
        # nécessite les droits ; best-effort
        subprocess.Popen(["sh", "-c", f"sleep {delay_seconds} && sudo shutdown -h now"])
        return "tue le process 'sleep' correspondant, ou sudo killall shutdown"
    # Linux
    mins = max(1, delay_seconds // 60)
    subprocess.run(["shutdown", "-h", f"+{mins}"], check=False)
    return "shutdown -c"
