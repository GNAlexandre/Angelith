# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Agents : un prompt système + un modèle + une température.
Le mode dry-run renvoie une transformation factice (test de bout en bout sans LLM).

`build_agents` est **unique pour les deux briques** depuis le lot 2.2. Les deux versions
d'origine (`pipeline.agents.build_agents` et `manga.agents_manga.build_manga_agents`) ne
différaient que par trois choses : quelle section de `config.yaml` porte les réglages LLM,
d'où vient la liste des agents, et quelle classe instancier. Elles sont devenues les
paramètres `section=` / `names=` / `agent_cls=`. Tout le reste — cache de clients par
endpoint, indirection `endpoint:`, budget de raisonnement, diagnostics de config mal
indentée — était écrit deux fois, une seule des deux versions étant complète.
"""
from __future__ import annotations

from pathlib import Path

from . import config as config_mod
from .langues import resoudre_pack
from .llm import LLM

# Les cinq agents du pipeline light novel. Liste FIXE, et non « les clés de `modeles` » :
# l'orchestrateur LN teste `agents["correcteur"] is None` pour sauter une étape désactivée
# par `modeles.correcteur: null`, donc la clé doit exister dans le dictionnaire rendu même
# quand elle est absente de la config. La brique manga a le besoin inverse — un roster
# ouvert, sans contrainte sur les noms — d'où le double défaut de `names=` ci-dessous.
NOMS_LN = ("terminologue", "traducteur", "correcteur", "mise_en_page", "glossariste")


def _raisonne(think) -> bool:
    """Cet agent produit-il un bloc de raisonnement ? (donc : faut-il lui accorder le
    budget de tokens supplémentaire).

    `think` accepte un booléen OU un niveau (`"low"`/`"medium"`/`"high"`, cf. `LLM`).
    Un simple `bool(think)` répondrait « oui » à `think: "none"`, qui coupe pourtant le
    raisonnement — l'agent recevrait un budget de sortie gonflé pour rien."""
    if isinstance(think, str):
        return think.strip().lower() not in ("", "none", "false")
    return bool(think)


class Agent:
    def __init__(self, nom: str, prompt_path, llm, modele: str, temperature: float,
                 extra_directive: str = "", dry_run: bool = False,
                 thinking: bool = False, thinking_budget: int = 2048):
        self.nom = nom
        self.llm = llm
        self.modele = modele
        self.temperature = temperature
        self.extra_directive = extra_directive
        self.dry_run = dry_run
        # `thinking` = cet agent tourne sur un modèle qui RAISONNE avant de répondre
        # (mode « thinking » activé). Dans ce cas la génération produit d'abord un bloc
        # <think>…</think> AVANT la réponse utile : il faut donc un budget de tokens plus
        # large, sinon tout le budget part dans le raisonnement, `</think>` n'est jamais
        # atteint, et la réponse ressort vide. `thinking_budget` est ajouté au max_tokens.
        self.thinking = thinking
        self.thinking_budget = thinking_budget
        self.system = Path(prompt_path).read_text(encoding="utf-8")

    def run(self, user_content: str, dry_payload: str = "", max_tokens: int | None = None,
            temperature: float | None = None,
            repli_sans_raisonnement: bool | None = None) -> str:
        """`repli_sans_raisonnement` : simple passe-plat vers `LLM.chat` — `False` interdit
        la réponse non raisonnée de secours, pour laisser l'appelant redécouper le bloc."""
        if self.dry_run:
            return self._dry(dry_payload)
        if self.extra_directive:
            user_content = f"{user_content}\n\n{self.extra_directive}"
        temp = self.temperature if temperature is None else temperature
        if max_tokens is not None and self.thinking:
            max_tokens += self.thinking_budget      # place pour le raisonnement EN PLUS de la réponse
        return self.llm.chat(self.modele, self.system, user_content, temp, max_tokens=max_tokens,
                             repli_sans_raisonnement=repli_sans_raisonnement)

    def _dry(self, payload: str) -> str:
        if self.nom == "terminologue":
            return "- (rien à signaler)"
        if self.nom == "glossariste":
            return payload          # dry-run : glossaire inchangé
        # traducteur / correcteur / mise_en_page : on laisse passer le texte tel quel.
        return payload


def section_llm(config: dict, section: str | None) -> tuple[dict, str]:
    """Réglages LLM applicables à une brique, et l'étiquette à citer dans les messages
    d'erreur (`llm` ou `manga.llm`) — pour que le diagnostic pointe le bloc que
    l'utilisateur doit réellement aller éditer.

    Fusion PROFONDE depuis le lot 2.3 (cf. `core/config.py`) : une brique n'a plus à
    recopier `base_url`/`api_key`/`timeout` pour ne régler qu'un `thinking_budget`."""
    return config_mod.section(config, section, "llm"), config_mod.origine(config, section, "llm")


def _endpoint_spec(nom_ep: str, endpoints: dict, blocs: list[tuple[str, dict]],
                   nom_agent: str, prefixe: str) -> dict | str:
    """Résout `endpoint: "reflexion"` en sa définition, avec un message actionnable si
    elle manque. Le piège d'indentation visé est fréquent et muet : `endpoints: {}`
    (vide) FERME le dictionnaire, puis la définition écrite en dessous au même niveau
    atterrit à côté de `endpoints` au lieu d'y être.

    `blocs` liste les blocs `llm:` BRUTS (non fusionnés) du plus spécifique au moins, avec
    leur étiquette. Il en faut plus d'un depuis que la fusion est profonde : le premier dit
    où AJOUTER l'endpoint manquant, mais la clé mal indentée peut se trouver dans l'autre —
    et pointer le mauvais fichier de configuration ferait perdre exactement le temps que ce
    message est censé économiser."""
    if nom_ep in endpoints:
        return endpoints[nom_ep]
    etiquette = blocs[0][0]
    indice = ""
    mal_place = next((et for et, bloc in blocs if nom_ep in (bloc or {})), None)
    if mal_place:
        indice = (f"\n  → « {nom_ep} » est défini au mauvais niveau : il est sous "
                  f"`{mal_place}:` au lieu d'être sous `{mal_place}.endpoints:`. "
                  f"Corrige l'indentation, et retire le `endpoints: {{}}` vide (il ferme "
                  f"le dictionnaire avant ta définition). Exemple correct :\n"
                  f"    endpoints:\n      {nom_ep}: {{think: true}}")
    elif not endpoints:
        indice = f"\n  → la section `{etiquette}.endpoints` est vide."
    raise SystemExit(
        f"{prefixe}modeles.{nom_agent} référence l'endpoint « {nom_ep} », absent de "
        f"{etiquette}.endpoints (config.yaml).{indice}")


def build_agents(config: dict, llm=None, dry_run: bool = False, *,
                 section: str | None = None, names=None, agent_cls=None,
                 temperature_defaut: float | None = None):
    """Construit les agents d'une brique. UNE fonction pour les deux (lot 2.2).

    - `section` : `None` = réglages à la racine de `config.yaml` (light novel) ;
      `"manga"` = sous `config["manga"]`.
    - `names` : liste des agents à construire. Par défaut `NOMS_LN` à la racine (roster
      fixe, cf. le commentaire de `NOMS_LN`) et les clés de `modeles` dans une section
      (roster ouvert).
    - `agent_cls` : `Agent` par défaut ; `MangaAgent` pour la brique manga, qui ajoute un
      paramètre `images=` à `run()`. Le socle ne connaît pas cette sous-classe — c'est
      l'appelant qui la passe, sinon `core/` importerait `manga/`.
    - `temperature_defaut` : température de repli quand `temperatures.<nom>` est absent.
      `None` (défaut LN) = c'est une erreur de config, signalée.
    - `llm` : client du serveur principal. `None` (cas manga) = on en construit un.

    Un agent peut cibler un endpoint DIFFÉRENT du défaut — typiquement pour activer le
    raisonnement (« thinking ») sur la terminologie ou le glossariste — en donnant à
    `modeles[nom]` la forme `{model: …, endpoint: "reflexion"}`, l'endpoint étant défini
    dans `llm.endpoints`. Un endpoint est un dict `{base_url?, think?}` (ou une simple
    chaîne, prise comme `base_url`) ; `base_url` par défaut = le serveur principal.

    `base_url` et `think` s'écrivent aussi **en ligne** dans la spec du modèle, ce qui vaut
    endpoint anonyme et **affine** celui nommé s'il y en a un. C'est la forme utilisée par
    `config.yaml` côté manga (`{model: …, think: false}`), désormais valable des deux côtés.

    Le « thinking » se contrôle PAR REQUÊTE via le paramètre `think` d'Ollama (True =
    raisonne, False = non, absent = défaut du modèle). UN SEUL modèle chargé suffit donc :
    on active le raisonnement pour certains agents et pas d'autres, sans le charger deux
    fois. Les clients sont mis en cache par `(base_url, think)` — deux agents visant le
    même endpoint partagent un client, donc un pool de sockets.
    """
    agent_cls = agent_cls or Agent
    racine = config if section is None else config[section]
    prefixe = "" if section is None else f"{section}."
    llm_cfg, etiquette_llm = section_llm(config, section)
    # Blocs `llm:` BRUTS, du plus spécifique au moins — pour que le diagnostic d'endpoint
    # mal indenté puisse nommer celui où la clé se trouve réellement (cf. `_endpoint_spec`).
    blocs_llm = [(etiquette_llm, (config.get(section) or {}).get("llm") or {})] \
        if etiquette_llm != "llm" else []
    blocs_llm.append(("llm", config.get("llm") or {}))

    # Les prompts viennent du PACK DE LANGUE CIBLE, plus de `chemins.prompts` directement.
    # C'est le seul site du dépôt qui les ouvre — light novel et manga passent tous deux par
    # ici (cf. `docs/mesures/inventaire-couplage-fr.md`, §1). Sans pack installé, `resoudre_pack`
    # rend le mode compatibilité, qui sert exactement `chemins.prompts` : rien ne change.
    pack = resoudre_pack(config)
    modeles = racine["modeles"]
    temperatures = racine.get("temperatures") or {}
    extra = llm_cfg.get("extra_directive", "")
    endpoints = llm_cfg.get("endpoints") or {}
    default_think = llm_cfg.get("think")           # None si non précisé
    thinking_budget = llm_cfg.get("thinking_budget", 4096)
    base_url_defaut = llm_cfg.get("base_url") or config["llm"].get("base_url")

    if names is not None:
        noms = list(names)
    else:
        noms = list(NOMS_LN) if section is None else list(modeles)

    clients: dict[tuple, object] = {}

    def _client(cible: dict):
        """Construit (ou réutilise) le client d'un endpoint. Renvoie (client, think, budget).

        `thinking_budget` s'affine PAR ENDPOINT comme `base_url` et `think` : le budget de
        raisonnement n'a de sens qu'au regard du niveau de réflexion et de la taille des
        blocs, or les deux se règlent déjà là. Clé absente → valeur de la brique."""
        base_url = cible.get("base_url") or base_url_defaut
        think = cible.get("think")                 # absent = rien d'imposé pour cet endpoint
        budget = cible.get("thinking_budget", thinking_budget)
        cle = (base_url, repr(think))
        if cle not in clients:
            clients[cle] = None if dry_run else LLM(
                base_url=base_url, api_key=llm_cfg.get("api_key", "ollama"),
                timeout=llm_cfg.get("timeout", 900),
                max_retries=llm_cfg.get("max_retries", 2), think=think,
                debit_plancher=llm_cfg.get("debit_plancher_tok_s"))
        return clients[cle], think, budget

    def _client_defaut():
        """Serveur principal, quand aucun endpoint n'est visé. Le LN passe son client
        déjà ouvert ; le manga n'en a pas, on en ouvre un (mis en cache comme les autres,
        donc partagé par tous les agents sans endpoint propre)."""
        if llm is not None:
            return llm, default_think, thinking_budget
        return _client({"base_url": base_url_defaut, "think": default_think})

    def _temperature(nom: str) -> float:
        if nom in temperatures:
            return temperatures[nom]
        if temperature_defaut is not None:
            return temperature_defaut
        raise SystemExit(
            f"{prefixe}temperatures.{nom} est absent de config.yaml alors que "
            f"{prefixe}modeles.{nom} est défini — l'agent n'aurait pas de température. "
            f"Ajoute `{nom}: 0.3` sous `{prefixe}temperatures:`.")

    agents = {}
    for nom in noms:
        spec = modeles.get(nom)
        if spec is None:
            # modeles.<nom>: null (ou clé absente) → agent DÉSACTIVÉ : son étape sera
            # sautée par l'orchestrateur (le texte passe inchangé). On n'instancie pas
            # d'Agent (pas de lecture de prompt, aucune exigence sur temperatures[nom]).
            agents[nom] = None
            continue
        if isinstance(spec, dict):
            modele = spec["model"]
            cible: dict = {}
            ep = spec.get("endpoint")
            if ep:
                brut = _endpoint_spec(ep, endpoints, blocs_llm, nom, prefixe)
                # Un endpoint écrit en chaîne vaut `base_url` ; son `think` reste le défaut
                # de la brique (et non « rien d'imposé »), comportement historique du LN.
                cible = ({"base_url": brut, "think": default_think} if isinstance(brut, str)
                         else dict(brut or {}))
            for cle in ("base_url", "think", "thinking_budget"):   # en ligne : affine l'endpoint
                if cle in spec:
                    cible[cle] = spec[cle]
            agent_llm, think, budget = _client(cible) if cible else _client_defaut()
        else:
            modele = spec
            agent_llm, think, budget = _client_defaut()
        agents[nom] = agent_cls(nom, pack.prompt(nom), agent_llm, modele,
                                _temperature(nom), extra_directive=extra, dry_run=dry_run,
                                thinking=_raisonne(think), thinking_budget=budget)
    return agents
