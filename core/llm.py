# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Client d'inférence local via Ollama (API compatible OpenAI)."""
from __future__ import annotations

import re
import time

from openai import APITimeoutError, OpenAI

_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think(?:ing)?>.*$", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Retire les blocs de raisonnement <think>…</think> (modèles à « thinking »).
    Gère aussi un bloc <think> non fermé (réponse coupée pendant le raisonnement)."""
    text = _THINK_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)
    return text.strip()


class LLM:
    """Enveloppe minimale autour d'Ollama (API compatible OpenAI).

    Mode « thinking » contrôlé PAR REQUÊTE. ⚠ Important : sur l'endpoint
    OpenAI-compatible d'Ollama (`/v1/chat/completions`), le paramètre natif `think` est
    IGNORÉ — c'est `reasoning_effort` qu'il faut envoyer (mappé en interne vers le mode
    thinking) :
      - `think=False` → `reasoning_effort="none"`  (pas de raisonnement, rapide) ;
      - `think=True`  → `reasoning_effort="medium"` (raisonne avant de répondre) ;
      - `think="low"|"medium"|"high"` → ce niveau, tel quel ;
      - `think=None`  → rien envoyé (défaut du modèle).
    Un seul modèle chargé suffit donc pour alterner entre agents qui raisonnent et non.
    (Détail documenté dans ollama/ollama#14820 ; le champ `reasoning` de la réponse
    contient la trace de raisonnement, `content` la réponse finale.)

    Le NIVEAU compte autant que l'interrupteur : sur roman A Vol.1, `"medium"` sur
    un bloc japonais de ~5 600 tokens a fait partir 74 à 97 % de la génération dans le
    `<think>` — 14 000 à 22 000 tokens de raisonnement pour 600 à 4 800 de traduction."""

    #: Niveaux acceptés tels quels par `reasoning_effort` (endpoint OpenAI d'Ollama).
    NIVEAUX_REFLEXION = ("none", "low", "medium", "high")

    #: Débit de génération PLANCHER (tokens/s) servant à dériver le timeout d'une requête.
    #: Mesuré sur roman A Vol.1 : 15 tok/s en régime normal, 5 tok/s quand le GPU
    #: décroche. On dimensionne sur le cas dégradé — un timeout doit couvrir le pire, sinon
    #: il transforme un ralentissement en échec.
    DEBIT_PLANCHER_DEFAUT = 5.0

    def __init__(self, base_url: str, api_key: str, timeout: int = 600, max_retries: int = 2,
                 think: bool | str | None = None, debit_plancher: float | None = None):
        import httpx
        # ⚠ SÉMANTIQUE httpx, à ne pas se raconter d'histoires : `read` n'est PAS un plafond
        # de durée totale, c'est un délai d'INACTIVITÉ — le temps maximal d'attente d'un
        # morceau de données. httpx n'offre aucun timeout « durée totale de la requête ».
        # Il se comporte ici en plafond total UNIQUEMENT parce que les appels ne sont pas en
        # streaming : Ollama ne renvoie rien tant que la génération n'est pas finie, donc le
        # premier `read` attend la génération entière. Passer un jour en `stream=True`
        # retirerait donc SILENCIEUSEMENT ce plafond.
        self._timeout_s = timeout
        self.debit_plancher = debit_plancher or self.DEBIT_PLANCHER_DEFAUT
        to = httpx.Timeout(timeout, connect=30.0, read=timeout, write=30.0)
        # `max_retries=0` : le SDK OpenAI vaut 2 par défaut ET retente sur timeout
        # (`SyncAPIClient.request` : `except httpx.TimeoutException: if remaining_retries > 0`).
        # Cumulé aux tentatives de cette enveloppe, cela faisait 3 × 3 = 9 requêtes de
        # `timeout` secondes par bloc — 2 h 15 d'attente muette sur le run de roman A,
        # invisible dans perf.log puisque le SDK ne journalise rien. Les tentatives sont donc
        # gérées ICI, et ici seulement : elles y sont comptées et tracées.
        # Retenu tel quel : le client OpenAI le normalise en `URL`, et les garde-fous qui
        # interrogent l'API NATIVE d'Ollama (`/api/ps`, cf. `core.power.contexte_charge`) ont
        # besoin de la chaîne d'origine pour en dériver la racine.
        self.base_url = base_url
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=to, max_retries=0)
        self.max_retries = max_retries
        self.think = think
        # Repli SANS raisonnement quand le budget de réflexion est épuisé. `True` = filet
        # historique : une réponse non raisonnée vaut mieux qu'un bloc perdu.
        # ⚠ Ce filet a été écrit AVANT le redécoupage-relance. Tant qu'il s'applique, il
        # rend `chat()` non vide, donc l'appelant conclut au succès et ne redécoupe jamais
        # — alors que DEUX MOITIÉS RAISONNÉES valent mieux qu'un bloc entier non raisonné.
        # L'orchestrateur le passe donc à `False` tant que le bloc reste redécoupable, et
        # ne le rouvre qu'en dernier recours. Les autres appelants gardent le filet.
        self.repli_sans_raisonnement = True
        self.stats = {"appels": 0, "tokens_generes": 0, "temps_generation": 0.0,
                      "retries": 0, "vides_persistants": 0,
                      "thinking_overflow": 0, "troncature_length": 0, "timeout": 0}
        # Cause du DERNIER appel problématique, lisible par l'appelant (l'orchestrateur
        # s'en sert pour décider s'il vaut la peine de redécouper le bloc et de relancer) :
        # "thinking_overflow" | "troncature" | "vide" | None.
        self.last_reason: str | None = None
        # Canal des messages d'incident. `print` par défaut (comportement historique) ;
        # l'orchestrateur y branche `reporter.warn` pour qu'ils atterrissent AUSSI dans
        # perf.log — jusqu'ici ils partaient sur stdout et étaient perdus.
        self.on_event = None

    def close(self) -> None:
        """Ferme le client OpenAI/httpx (pool de connexions) proprement. À appeler à la
        sortie d'un run : sans ça, un arrêt brutal (Ctrl+C) abandonne la socket en pleine
        génération au lieu de la refermer — ce qui laisse Ollama dans un état de connexion
        bancal et a été relié à une chute persistante du débit GPU au run suivant.
        Idempotent et best-effort : une double fermeture ou un client déjà GC ne lève pas."""
        try:
            self.client.close()
        except Exception:
            pass

    def _emit(self, msg: str) -> None:
        """Signale un incident (dépassement de budget, retry, abandon). Passe par
        `on_event` si l'appelant en a fourni un — sinon `print`, comme avant."""
        cb = getattr(self, "on_event", None)
        if callable(cb):
            try:
                cb(msg)
                return
            except Exception:
                pass
        print(msg)

    def timeout_pour(self, max_tokens: int | None) -> float:
        """Plafond de durée d'UNE requête, dérivé du budget de génération qu'on autorise.

        Un timeout plat est une contradiction en puissance : il faut qu'il couvre la
        génération intégrale de `max_tokens`, or ce budget bouge avec `thinking_budget`,
        `max_block_tokens` et le modèle. Sur roman A Vol.1, `max_tokens` valait
        20 644 — soit 1 376 s à 15 tok/s et 4 129 s à 5 tok/s — contre un `llm.timeout`
        figé à 900 s. **Le pire cas autorisé ne tenait sous ce timeout à aucun débit** : il
        aurait fallu soutenir 23 tok/s. Le run de nuit est mort là-dessus.

        `llm.timeout` devient donc un PLANCHER (il couvre les petits appels : titres,
        relevés de terminologie) et non plus un plafond."""
        if not max_tokens:
            return float(self._timeout_s)
        return max(float(self._timeout_s), max_tokens / max(0.1, self.debit_plancher))

    def _extra_body(self) -> dict | None:
        return None if self.think is None else {"reasoning_effort": self._effort()}

    def _effort(self) -> str:
        """`think` → valeur de `reasoning_effort`. Un booléen garde son sens historique ;
        une chaîne passe telle quelle après validation, pour qu'une faute de frappe dans
        `config.yaml` (`think: "meduim"`) échoue ici, avec un message actionnable, plutôt
        que d'être expédiée à Ollama et de revenir en 400 opaque au premier bloc."""
        if isinstance(self.think, str):
            niveau = self.think.strip().lower()
            if niveau not in self.NIVEAUX_REFLEXION:
                raise SystemExit(
                    f"Niveau de réflexion « {self.think} » inconnu (config.yaml > llm.think "
                    f"ou llm.endpoints.<nom>.think).\n"
                    f"  → valeurs acceptées : {', '.join(self.NIVEAUX_REFLEXION)}, "
                    f"ou true/false.")
            return niveau
        return "medium" if self.think else "none"

    def _resolve_model(self, model: str) -> str:
        """Ollama nomme ses modèles avec un tag (« modele:latest »). Une requête vers
        « modele » sans tag renvoie parfois 404 selon la version. On résout donc le nom
        contre la liste réelle une seule fois (mise en cache) : si « modele » exact est
        absent mais qu'un « modele:xxx » existe, on l'utilise. Best-effort : si la liste
        est injoignable, on renvoie le nom tel quel."""
        cache = getattr(self, "_model_cache", None)
        if cache is None:
            cache = self._model_cache = {}
        if model in cache:
            return cache[model]
        resolved = model
        try:
            ids = [m.id for m in self.client.models.list().data]
            if model not in ids:
                match = next((i for i in ids if i.split(":", 1)[0] == model), None)
                if match:
                    resolved = match
        except Exception:
            pass
        cache[model] = resolved
        return resolved

    def chat(self, model: str, system: str, user: str, temperature: float = 0.2,
             max_tokens: int | None = None, images: list[str] | None = None,
             repli_sans_raisonnement: bool | None = None) -> str:
        """Un échange system+user → texte (raisonnement retiré).
        `max_tokens` borne la génération (anti-emballement). Réessaie sur erreur réseau
        ET sur réponse vide ; renvoie "" si vide persistant (l'appelant gère le repli).

        `repli_sans_raisonnement` : `None` (défaut) = valeur de l'instance. `False`
        interdit le repli en réponse non raisonnée — `chat()` rend alors `""` avec
        `last_reason == "thinking_overflow"`, ce qui laisse l'appelant redécouper le bloc
        et le relancer AVEC son raisonnement (cf. `_trad_resplit`).

        `images` (optionnel) : liste d'images encodées en base64 (PNG/JPEG, SANS le
        préfixe `data:...`) à joindre au message utilisateur, pour un modèle multimodal
        (ex. qwen3.6, qui expose `vision` — vérifiable via `ollama show <modèle>`).
        Absent/None (défaut) → comportement STRICTEMENT identique à avant (message
        texte simple) : ce paramètre est purement additif, aucun appelant existant
        n'est affecté."""
        model = self._resolve_model(model)
        extra = self._extra_body()
        user_content = user if not images else [
            {"type": "text", "text": user},
            *({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
              for b64 in images),
        ]
        last_err: Exception | None = None
        self.last_reason = None
        autorise_repli = (self.repli_sans_raisonnement if repli_sans_raisonnement is None
                          else repli_sans_raisonnement)
        # Timeout PAR REQUÊTE, dérivé du budget (cf. `timeout_pour`) et passé à l'appel —
        # PAS via `client.with_options()`, qui renvoie une COPIE du client : le pool de
        # connexions serait perdu, et les doublures de test qui patchent `self.client` ne
        # verraient plus rien.
        timeout_req = self.timeout_pour(max_tokens)
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    extra_body=extra,
                    timeout=timeout_req,
                )
                self.stats["temps_generation"] += time.perf_counter() - t0
                usage = getattr(resp, "usage", None)
                comp_tok = getattr(usage, "completion_tokens", None) if usage else None
                if comp_tok:
                    self.stats["tokens_generes"] += comp_tok
                choice = resp.choices[0]
                msg = choice.message
                raw = msg.content or ""
                # `finish_reason == "length"` = génération coupée net au plafond
                # `max_tokens`. Signal DIRECT de troncature, qu'on ne lisait pas : la
                # perte n'était détectée qu'après coup, et de façon heuristique, par les
                # garde-fous de l'orchestrateur (perte de mots, emballement).
                if getattr(choice, "finish_reason", None) == "length":
                    self.stats["troncature_length"] += 1
                    self.last_reason = "troncature"
                    # Tracé, et pas seulement compté : une troncature ne laissait AUCUNE
                    # ligne dans perf.log. Sur roman A Vol.1, deux blocs coupés en
                    # plein mot n'y apparaissaient que comme des blocs ordinaires.
                    self._emit(f"    [LLM] génération coupée net au plafond max_tokens"
                               f"{f' ({comp_tok} tokens)' if comp_tok else ''}.")
                # Ollama expose le raisonnement dans un champ `reasoning` séparé : si
                # `content` est vide mais que le raisonnement est là, la génération a été
                # coupée avant la réponse finale (budget de tokens trop court en mode thinking).
                if not raw.strip():
                    reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
                    if reasoning:
                        self.stats["thinking_overflow"] += 1
                        self.last_reason = "thinking_overflow"
                        # Le raisonnement a mangé tout le budget avant la réponse. DERNIER
                        # RECOURS seulement : on retente UNE fois SANS thinking
                        # (reasoning_effort=none). Une réponse non raisonnée vaut mieux
                        # qu'un bloc perdu, mais moins que deux moitiés raisonnées — d'où
                        # `autorise_repli`, que l'orchestrateur ferme tant qu'il peut
                        # encore redécouper.
                        if self.think and autorise_repli and not getattr(self, "_no_think_retry", False):
                            self._no_think_retry = True
                            try:
                                t1 = time.perf_counter()
                                resp2 = self.client.chat.completions.create(
                                    model=model, temperature=temperature, max_tokens=max_tokens,
                                    messages=[{"role": "system", "content": system},
                                              # `user_content`, PAS `user` : sur le chemin
                                              # multimodal (manga), passer la chaîne brute
                                              # perdait silencieusement les images et
                                              # dégradait le repli en appel texte.
                                              {"role": "user", "content": user_content}],
                                    extra_body={"reasoning_effort": "none"},
                                    timeout=timeout_req)
                                self.stats["temps_generation"] += time.perf_counter() - t1
                                choix2 = resp2.choices[0]
                                m2 = choix2.message
                                c2 = strip_thinking(m2.content or "")
                                if c2:
                                    self.stats["appels"] += 1
                                    u2 = getattr(resp2, "usage", None)
                                    ct2 = getattr(u2, "completion_tokens", None) if u2 else None
                                    self.stats["tokens_generes"] += ct2 or (len(c2) // 4)
                                    self._no_think_retry = False
                                    # Le repli peut être tronqué à son tour : sans ce
                                    # contrôle, sa réponse coupée revenait comme un succès
                                    # ordinaire, et rien ne distinguait un bloc entier d'un
                                    # bloc amputé.
                                    if getattr(choix2, "finish_reason", None) == "length":
                                        self.stats["troncature_length"] += 1
                                        self.last_reason = "troncature"
                                        self._emit("    [LLM] budget thinking dépassé → repli sans "
                                                   "raisonnement, LUI AUSSI coupé au plafond.")
                                        return c2
                                    self.last_reason = "thinking_overflow"
                                    self._emit("    [LLM] budget thinking dépassé → réponse obtenue "
                                               "sans raisonnement pour ce bloc.")
                                    return c2
                            except Exception:
                                pass
                            self._no_think_retry = False
                        last_err = RuntimeError(
                            "le modèle a raisonné mais n'a pas produit de réponse finale "
                            "(budget de tokens trop court pour le mode « thinking » ?)")
                        raise last_err
                content = strip_thinking(raw)
                if content:
                    self.stats["appels"] += 1
                    if not comp_tok:              # usage absent → estimation grossière
                        self.stats["tokens_generes"] += len(content) // 4
                    return content
                if self.last_reason is None:
                    self.last_reason = "vide"
                last_err = RuntimeError("réponse vide du modèle")
            except Exception as err:  # réseau, modèle non chargé, timeout…
                last_err = err
                if isinstance(err, APITimeoutError):
                    self.last_reason = "timeout"
                # Modèle introuvable (404) : inutile de retenter, et le message brut est
                # obscur. On lève tout de suite une erreur actionnable.
                em = str(err).lower()
                if "not found" in em or "404" in em:
                    raise SystemExit(
                        f"Modèle « {model} » introuvable côté Ollama.\n"
                        f"  → vérifie le nom exact avec `ollama ls` et corrige config.yaml > modeles.\n"
                        f"  → si le modèle a un tag (ex. « {model}:latest »), le code le résout "
                        f"normalement seul ; si l'erreur persiste, mets le nom complet AVEC le tag.") from None
            if attempt < self.max_retries:
                self.stats["retries"] += 1
                wait = 3 * (attempt + 1)
                self._emit(f"    [LLM] {last_err}; nouvelle tentative dans {wait}s…")
                time.sleep(wait)
        # Timeout persistant : NON FATAL. C'était le seul motif d'échec LLM à lever, par
        # simple absence de branche ici — une `APITimeoutError` n'est pas une `RuntimeError`
        # et son message anglais ne contient ni « vide » ni « réponse finale ». Un bloc trop
        # long tuait donc le tome entier, alors qu'un timeout est un symptôme de TAILLE :
        # rendu à l'appelant, il déclenche le redécoupage-relance, et couper le bloc en deux
        # y est un remède CAUSAL (deux moitiés génèrent deux fois moins).
        if isinstance(last_err, APITimeoutError):
            self.stats["timeout"] += 1
            self.last_reason = "timeout"
            self._emit(f"    [LLM] expiration persistante après {self.max_retries + 1} "
                       f"tentatives de {self.timeout_pour(max_tokens):.0f}s — bloc rendu à "
                       f"l'appelant pour redécoupage.")
            return ""
        # Réponse inexploitable de façon persistante (vide, ou raisonnement sans réponse
        # finale) : on ne lève pas — l'appelant gardera la source / le texte précédent.
        msg_err = str(last_err) if last_err else ""
        if isinstance(last_err, RuntimeError) and ("vide" in msg_err or "réponse finale" in msg_err):
            self.stats["vides_persistants"] += 1
            if self.last_reason is None:
                self.last_reason = "vide"
            self._emit("    [LLM] réponse inexploitable après plusieurs tentatives "
                       f"({self.last_reason}) — bloc laissé tel quel.")
            return ""
        raise RuntimeError(f"Échec de l'appel LLM après {self.max_retries + 1} tentatives : {last_err}")


def _connu(model: str, ids: list[str]) -> bool:
    """Ollama nomme ses modèles avec un tag (`modele:latest`). On matche en ignorant le tag
    manquant côté config : « qwen3.5-9b-yumetrad » ↔ « qwen3.5-9b-yumetrad:latest »."""
    return model in ids or any(i.split(":", 1)[0] == model for i in ids)


def _resolu(model: str, ids: list[str]) -> str:
    """L'id RÉEL côté Ollama (avec son tag) pour un modèle configuré sans tag."""
    if model in ids:
        return model
    return next((i for i in ids if i.split(":", 1)[0] == model), model)


def _modeles_voulus(config: dict) -> set[str]:
    """Les modèles que `config.yaml > modeles` réclame, agents désactivés exclus
    (`modeles.<agent>: null`)."""
    voulus = {(m["model"] if isinstance(m, dict) else m) for m in config["modeles"].values()}
    return {m for m in voulus if m}


def _verifier_modeles(wanted: set[str], ids: list[str], ecrire=print) -> list[str]:
    """Rend les modèles MANQUANTS, et les écrit au passage.

    ⚠ `ecrire` est un paramètre depuis le lot 36 : `core/diagnostic.py` a besoin du CONSTAT
    (la liste), la console a besoin du TEXTE, et une capture de `stdout` aurait fait attendre
    l'utilisateur douze secondes avant la première ligne. Le défaut `print` garde la sortie de
    `run.py --check` inchangée, octet pour octet."""
    missing = sorted({m for m in wanted if not _connu(m, ids)})
    if missing:
        ecrire(f"⚠ Modèles configurés absents d'Ollama : {missing}")
        ecrire("  → `ollama pull <modèle>` (ou `ollama create`), ou ajuste config.yaml > modeles.")
    else:
        ecrire("✓ Tous les modèles de config.yaml sont disponibles.")
    return missing


def _essai_de_generation(client, test_model: str, ecrire=print) -> bool:
    """Mini-génération de contrôle. Purement informative : un serveur qui répond mais génère
    mal reste un serveur joignable, donc rien ici ne change le verdict.

    Rend True si la génération a produit du texte — le constat que `core/diagnostic.py`
    consomme ; le texte, lui, part par `ecrire` (cf. `_verifier_modeles`)."""
    try:
        r = client.chat.completions.create(
            model=test_model, max_tokens=64, temperature=0,
            messages=[{"role": "user", "content": "Réponds uniquement par le mot : OK"}],
            extra_body={"reasoning_effort": "none"},   # coupe le raisonnement (endpoint OpenAI d'Ollama)
        )
        msg = r.choices[0].message
    except Exception as err:
        ecrire(f"⚠ Le serveur répond mais la génération échoue : {err}")
        return False

    out = (msg.content or "").strip()
    if out:
        ecrire(f"✓ Génération OK avec « {test_model} » → {out!r}")
        return True
    reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
    if reasoning:
        ecrire(f"⚠ « {test_model} » a mis sa réponse dans le champ `reasoning` et laissé "
               f"`content` vide — le raisonnement n'a pas été coupé.")
        ecrire("  → mets à jour Ollama (`reasoning_effort` requiert une version récente), "
               "ou ajoute `PARAMETER think false` dans ton Modelfile puis `ollama create`.")
    else:
        ecrire(f"⚠ « {test_model} » a répondu vide (ni content ni reasoning). "
               f"Vérifie le num_ctx du Modelfile.")
    return False


def test_connection(config: dict, ecrire=print) -> bool:
    """Teste le serveur Ollama : joignabilité, modèles disponibles, mini-génération.
    Renvoie True si le serveur répond.

    ⚠ `ecrire` par défaut à `print` : la sortie de `run.py --test-llm`, de `run.py --check` et
    de `run_manga.py --check` est inchangée. `core/diagnostic.py` passe un collecteur pour
    obtenir les mêmes lignes SANS les imprimer — cf. `sonder_llm` là-bas."""
    base = config["llm"]["base_url"]
    ecrire(f"Test de connexion → {base}")
    client = OpenAI(base_url=base, api_key=config["llm"].get("api_key", "ollama"), timeout=30)

    try:
        ids = [m.id for m in client.models.list().data]
    except Exception as err:
        ecrire("❌ Serveur injoignable.")
        ecrire("   • Démarre Ollama : `ollama serve` (ou l'app Ollama).")
        ecrire(f"   • base_url attendu dans config.yaml : {base}")
        ecrire(f"   • détail : {err}")
        return False

    ecrire(f"✓ Serveur joignable. Modèles disponibles : {ids or '(aucun)'}")
    wanted = _modeles_voulus(config)
    _verifier_modeles(wanted, ids, ecrire)

    test_model = next((_resolu(m, ids) for m in wanted if _connu(m, ids)),
                      ids[0] if ids else None)
    if test_model:
        _essai_de_generation(client, test_model, ecrire)
    return True
