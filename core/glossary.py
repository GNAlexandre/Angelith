# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Chargement / sauvegarde du glossaire et mise en forme pour les prompts.

Le glossaire est propre à une ŒUVRE (sources/<Projet>/glossaire.yaml) : il est
donc disponible et réutilisé pour TOUS les tomes de l'œuvre, et sert de base
prête à l'emploi pour les volumes suivants.

Schéma catégorisé (toutes les sections sont optionnelles) :

  personnages:    [{nom, genre, variantes[], role, description}]
  lieux:          [{nom, variantes[], description}]
  organisations:  [{nom, variantes[], description}]
  creatures:      [{nom, genre, variantes[], description}]   # bêtes, races, fées…
  objets:         [{nom, variantes[], traduire(bool), description}]
  termes:         [{nom, variantes[], interdits[], traduire(bool), description}]
  evenements:     [{nom, variantes[], description}]
  groupes:        [{nom, note}]            # POV collectif / règles d'accord
  anglicismes:    [{vo, fr}]               # résidus VO à remplacer

Les champs `vo/fr/note` de l'ancien schéma `termes` restent lus (compat).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from . import chemins, glossary_cibles, glossary_lang, tokens

# Catégories d'« entités » : mêmes champs de base (nom / variantes / description),
# + champs spécifiques selon la catégorie.
ENTITY_CATS: dict[str, dict] = {
    "personnages":   {"label": "Personnages (le genre commande les accords)", "genre": True, "role": True},
    "lieux":         {"label": "Lieux"},
    "organisations": {"label": "Organisations / factions"},
    "creatures":     {"label": "Créatures / races", "genre": True},
    "objets":        {"label": "Objets", "traduire": True},
    "termes":        {"label": "Termes / concepts / lore", "interdits": True, "traduire": True},
    "evenements":    {"label": "Événements"},
}
# Ordre d'affichage / d'écriture
ORDER = list(ENTITY_CATS) + ["groupes", "anglicismes"]

# Ordre canonique des champs par catégorie, utilisé pour toujours écrire TOUS les
# champs (même vides) — pratique pour repérer d'un coup d'œil ce qui est complétable.
FIELD_ORDER: dict[str, list[str]] = {
    "personnages":   ["nom", "pluriel", "genre", "variantes", "termes_source", "interdits", "role", "description", "force"],
    "lieux":         ["nom", "pluriel", "variantes", "termes_source", "interdits", "description", "force"],
    "organisations": ["nom", "pluriel", "variantes", "termes_source", "interdits", "description", "force"],
    "creatures":     ["nom", "pluriel", "genre", "traduire", "variantes", "termes_source", "interdits", "description", "force"],
    "objets":        ["nom", "pluriel", "traduire", "variantes", "termes_source", "interdits", "description", "force"],
    "termes":        ["nom", "pluriel", "traduire", "variantes", "termes_source", "interdits", "description", "force"],
    "evenements":    ["nom", "pluriel", "variantes", "termes_source", "interdits", "description", "force"],
}
_FIELD_DEFAULTS = {
    "genre": "?", "variantes": [], "interdits": [], "traduire": None, "termes_source": [],
    "role": "", "description": "", "force": False, "pluriel": "",
}
# Bannières de section pour la lisibilité visuelle du fichier sauvegardé.
_BANNER = {
    "personnages": "PERSONNAGES", "lieux": "LIEUX", "organisations": "ORGANISATIONS",
    "creatures": "CRÉATURES", "objets": "OBJETS", "termes": "TERMES", "evenements": "ÉVÉNEMENTS",
    "groupes": "GROUPES (POV collectif / accords)", "anglicismes": "ANGLICISMES",
}


def empty() -> dict:
    g: dict = {c: [] for c in ENTITY_CATS}
    g["groupes"] = []
    g["anglicismes"] = []
    return g


_LIST_FIELDS = {"variantes", "interdits", "termes_source"}


def _fill_entity(cat: str, e: dict) -> dict:
    """Reconstruit une entrée avec TOUS les champs de sa catégorie, dans un ordre
    stable — y compris ceux qui restent vides, pour qu'ils soient visibles et
    facilement complétables à la main. Les champs-liste reçoivent TOUJOURS une
    liste fraîche (jamais un objet par défaut partagé) : PyYAML crée sinon des
    ancres/alias (&id001/*id001) pour les objets identiques, qui se percutent une
    fois plusieurs catégories dumpées séparément puis concaténées."""
    order = FIELD_ORDER.get(cat, ["nom", "description", "force"])
    out: dict = {}
    for k in order:
        if k == "nom":
            out["nom"] = e.get("nom", "")
        elif k in _LIST_FIELDS:
            out[k] = list(e.get(k) or [])
        else:
            out[k] = e.get(k, _FIELD_DEFAULTS.get(k))
    for k, v in e.items():                    # conserve toute clé inattendue (compat)
        if k not in out:
            out[k] = v
    return out


def fill_defaults(glossaire: dict) -> dict:
    """Renvoie une copie du glossaire où chaque entrée expose TOUS les champs
    applicables à sa catégorie (même vides/nuls), dans un ordre stable."""
    out: dict = {}
    for cat in ENTITY_CATS:
        entries = glossaire.get(cat) or []
        if entries:
            out[cat] = [_fill_entity(cat, e) for e in entries]
    for cat in ("groupes", "anglicismes"):
        if glossaire.get(cat):
            out[cat] = glossaire[cat]          # déjà minimalistes, rien à compléter
    for cat, v in glossaire.items():           # sections inconnues éventuelles
        if cat not in out and v:
            out[cat] = v
    return out


#: Langue cible du RUN. Posée une fois au démarrage par `cli.charger_config`, depuis le pack.
#:
#: ⚠ Un état de module, et c'est délibéré. La cible est une propriété du RUN, fixée avant que
#: quoi que ce soit ne tourne et constante jusqu'à la fin : l'enfiler dans les vingt signatures
#: qui lisent ou écrivent le glossaire ajouterait vingt paramètres qui vaudraient toujours la
#: même chose. Le paramètre `cible=` reste disponible pour un appel explicite — c'est ce dont
#: les tests se servent, et c'est lui qui prime.
_CIBLE_DU_RUN = "fr"


def definir_cible(code: str | None) -> None:
    """Fixe la langue cible du run. Appelée au chargement de la config, pas ailleurs."""
    global _CIBLE_DU_RUN
    _CIBLE_DU_RUN = (code or "fr").strip().lower() or "fr"


def cible_du_run() -> str:
    return _CIBLE_DU_RUN


def load(path: str | Path, cible: str | None = None) -> dict:
    """Charge le glossaire, **à plat pour la cible demandée**.

    ⚠ Le fichier est multi-cibles depuis la 2.0.0 (cf. `core/glossary_cibles.py`), mais tout
    le reste du dépôt lit `e["nom"]`, `e["genre"]`… — 71 endroits. La conversion se fait donc
    ICI, et le code appelant n'a rien à savoir de `cibles`.

    **Migration automatique** d'un fichier à l'ancien format, avec sauvegarde `.bak` écrite
    AVANT toute réécriture : un glossaire est du travail humain accumulé sur plusieurs tomes,
    et le convertir sans filet serait le seul geste irréversible de ce dépôt."""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as fh:
        brut = yaml.safe_load(fh) or {}
    if not brut:
        return {}
    code = (cible or _CIBLE_DU_RUN).strip().lower()

    if glossary_cibles.besoin_de_migration(brut):
        # ⚠ La sauvegarde part AVANT la réécriture, et sous un nom qui ne peut pas être
        # repris par une seconde migration : `.bak` écrasé par une migration ratée ne
        # servirait à rien.
        sauvegarde = chemins.derive(p, ".avant-multicibles.bak")
        if not sauvegarde.exists():
            sauvegarde.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        # La cible de migration est celle du run : un glossaire écrit avant les packs est du
        # français, sauf si l'on traduit déjà vers autre chose — auquel cas ces rendus sont
        # ceux de CETTE cible, et les ranger sous `fr` serait faux.
        brut, n = glossary_cibles.migrer(brut, code)
        save(brut, p, cible=code, deja_multi=True)
        print(f"[glossaire] {p.name} migré au format multi-cibles sous « {code} » "
              f"({n} entrée(s)) — sauvegarde : {sauvegarde.name}", file=sys.stderr)

    return {cat: ([glossary_cibles.aplatir(e, code) for e in entrees]
                  if cat in ENTITY_CATS and isinstance(entrees, list) else entrees)
            for cat, entrees in brut.items()}


def save(glossaire: dict, path: str | Path, cible: str | None = None,
         *, deja_multi: bool = False, entete: str | None = None) -> None:
    """Écrit le glossaire, en **refondant** la vue plate dans le fichier multi-cibles.

    ⚠ Les rendus des AUTRES langues sont relus depuis le disque et préservés : traduire un
    tome vers l'anglais ne doit pas effacer le travail fait en français. C'est l'invariant
    central du format multi-cibles.

    `entete` remplace le bloc de commentaires de tête. Il n'a qu'un appelant,
    `core/glossary_export.py`, et une seule raison d'être : un glossaire EXPORTÉ doit porter
    sa provenance — l'œuvre, la version d'Angelith, la date, le nombre d'entrées — parce
    qu'il va circuler seul, séparé du dépôt qui l'a produit, et qu'un glossaire sans
    dénominateur ne se fusionne pas. Le corps, lui, reste écrit **par cette fonction** : deux
    écrivains du même format finiraient par ne plus produire le même fichier, et c'est le
    format d'ARCHIVE du glossaire."""
    p = Path(path)
    code = (cible or _CIBLE_DU_RUN).strip().lower()
    if not deja_multi:
        # ⚠ `fill_defaults` AVANT la refonte, pas après : il travaille sur la forme PLATE, et
        # c'est lui qui tient la promesse de l'en-tête du fichier — « chaque entrée affiche
        # tous ses champs, même vides — complète-les librement ». Appelé après, il ne verrait
        # plus que le niveau partagé et les champs de rendu disparaîtraient des entrées qui
        # ne les portent pas encore.
        glossaire = _refondre(fill_defaults(glossaire), p, code)
    p.parent.mkdir(parents=True, exist_ok=True)
    header = entete if entete is not None else (
        "# ============================================================\n"
        f"#  Glossaire — {p.parent.name}\n"
        "#  Propre à cette ŒUVRE (réutilisé pour tous ses tomes).\n"
        "#  Catégorisé et espacé pour la lecture : personnages / lieux /\n"
        "#  organisations / créatures / objets / termes / événements /\n"
        "#  groupes / anglicismes. Chaque entrée affiche tous ses champs,\n"
        "#  même vides — complète-les librement.\n"
        "#  `force: true` IMPOSE le champ `nom` comme traduction obligatoire :\n"
        "#  toute forme listée en `variantes`/`interdits` sera remplacée par\n"
        "#  `nom` dans le texte final, automatiquement (ex. nom: Leprechaun,\n"
        "#  interdits: [lutin, farfadet], force: true).\n"
        "#  Alimenté automatiquement par le terminologue/glossariste (fusion\n"
        "#  SANS écrasement) ; tes entrées sont conservées et prioritaires.\n"
        "# ============================================================\n\n"
    )
    filled = glossaire
    blocks: list[str] = []
    for cat in ORDER:
        entries = filled.get(cat)
        if not entries:
            continue
        banner = f"# ─────────────────────  {_BANNER.get(cat, cat.upper())}  ─────────────────────\n"
        dumped = yaml.safe_dump({cat: entries}, allow_unicode=True, sort_keys=False, width=100)
        blocks.append(banner + dumped)
    for cat, v in filled.items():              # sections inconnues éventuelles
        if cat not in ORDER and v:
            blocks.append(yaml.safe_dump({cat: v}, allow_unicode=True, sort_keys=False, width=100))
    body = "\n".join(blocks)                    # blocs déjà terminés par \n → 1 ligne vide entre eux
    p.write_text(header + body, encoding="utf-8")


def _est_multi(glossaire: dict) -> bool:
    return any(glossary_cibles.est_multi(e)
               for cat, entrees in (glossaire or {}).items()
               if cat in ENTITY_CATS and isinstance(entrees, list)
               for e in entrees if isinstance(e, dict))


def _refondre(plat: dict, chemin: Path, cible: str) -> dict:
    """Vue plate → fichier multi-cibles, en conservant les autres langues.

    L'appariement avec ce que porte le disque se fait par `termes_source` d'abord (la graphie
    d'origine, stable entre langues) puis par `nom` : deux cibles n'ont pas le même `nom` pour
    la même entité, donc s'apparier uniquement par `nom` créerait un doublon par langue."""
    ancien = {}
    if chemin.exists():
        try:
            with open(chemin, encoding="utf-8") as fh:
                ancien = yaml.safe_load(fh) or {}
        except (yaml.YAMLError, OSError):
            ancien = {}

    def _index(entrees):
        idx = {}
        for e in entrees or []:
            if not isinstance(e, dict):
                continue
            for src in (e.get("termes_source") or []):
                idx.setdefault(("src", str(src)), e)
            for rendu in (e.get(glossary_cibles.CLE_CIBLES) or {}).values():
                if (rendu or {}).get("nom"):
                    idx.setdefault(("nom", str(rendu["nom"])), e)
            if e.get("nom"):
                idx.setdefault(("nom", str(e["nom"])), e)
        return idx

    sortie = {}
    for cat, entrees in (plat or {}).items():
        if cat not in ENTITY_CATS or not isinstance(entrees, list):
            sortie[cat] = entrees
            continue
        idx = _index(ancien.get(cat))
        fondues = []
        for e in entrees:
            if not isinstance(e, dict):
                fondues.append(e)
                continue
            reference = None
            for src in (e.get("termes_source") or []):
                reference = idx.get(("src", str(src)))
                if reference is not None:
                    break
            if reference is None and e.get("nom"):
                reference = idx.get(("nom", str(e["nom"])))
            fondues.append(glossary_cibles.fusionner(reference, e, cible))
        sortie[cat] = fondues
    # ⚠ On NE recopie PAS les catégories que la vue plate ne porte plus. Elles ont été
    # vidées délibérément par l'appelant — le glossariste qui dédoublonne, ou un
    # `glossary.save(glossary.empty(), …)` — et les ressusciter depuis le disque rendrait
    # tout effacement impossible.
    #
    # Les rendus des autres langues ne sont pas perdus pour autant : une entrée présente sur
    # disque apparaît TOUJOURS dans la vue plate, avec un `nom` vide si elle n'est pas encore
    # traduite dans cette cible (cf. `glossary_cibles.aplatir`), et `fusionner` la restitue
    # avec ses autres langues intactes. Ce qui disparaît ici a été supprimé, pas oublié.
    return sortie


def counts(glossaire: dict) -> dict:
    """Nombre d'entrées par catégorie (pour le rendu console)."""
    return {k: len(glossaire.get(k) or []) for k in ORDER if glossaire.get(k)}


def total(glossaire: dict) -> int:
    return sum(len(glossaire.get(k) or []) for k in ORDER)


def _non_romanise(e: dict) -> bool:
    """Entrée dont le `nom` n'est pas encore un rendu français (cf. `glossary_lang`)."""
    return bool(e.get("a_romaniser")) or glossary_lang.contient_cjk(str(e.get("nom") or ""))


def _fmt_entity(cat: str, e: dict, with_desc: bool = True) -> str:
    meta = ENTITY_CATS[cat]
    nom = e.get("nom", "")
    tags = []
    if meta.get("genre"):
        tags.append(e.get("genre") or "?")
    if e.get("traduire") is False:
        tags.append("NE PAS TRADUIRE")
    if _non_romanise(e):
        tags.append("À ROMANISER")
    if e.get("force"):
        tags.append("FORCÉ")
    head = nom + (f" [{', '.join(tags)}]" if tags else "")
    line = "- " + head
    if with_desc:
        tail = []
        if meta.get("role") and e.get("role"):
            tail.append(str(e["role"]))
        if e.get("description"):
            tail.append(str(e["description"]))
        if tail:
            line += " — " + " ; ".join(tail)
    extras = []
    if e.get("variantes"):
        extras.append("variantes : " + ", ".join(e["variantes"]))
    if e.get("termes_source"):
        extras.append("mot(s) source à repérer : " + ", ".join(e["termes_source"]))
    if e.get("interdits"):
        extras.append("jamais : " + ", ".join(e["interdits"]))
    if extras:
        line += " (" + " ; ".join(extras) + ")"
    return line


def _approx_tokens(s: str) -> int:
    """Nom historique conservé (call sites + tests) ; délègue à `tokens.estimate`,
    partagée avec orchestrator._est_tokens (unifie l'heuristique CJK vs latin, qui
    divergeait avant entre les deux modules)."""
    return tokens.estimate(s)


def _render(glossaire: dict, with_desc: bool = True,
            masquer_non_romanises: bool = False) -> str:
    """`masquer_non_romanises` : omet les entrées dont le `nom` n'est pas encore un rendu
    français. C'EST LA CORRECTION QUI COUPE LA BOUCLE. Le traducteur reçoit le glossaire
    comme un dictionnaire à respecter (« utilise le nom de cette entrée comme rendu
    français », `prompts/traducteur.md`) : lui présenter une entrée dont le `nom` est encore
    la graphie source lui ORDONNE de la recopier telle quelle dans le texte français. C'est
    ce qui a produit les 447 séquences japonaises du rendu du Vol.1.

    Défaut `False` — aucun appelant non modifié ne change de comportement, et le
    terminologue comme le glossariste continuent de VOIR ces entrées : ils sont là pour les
    réparer, les masquer les ferait recréer en boucle."""
    if not glossaire:
        return "# GLOSSAIRE\n(vide — à constituer)"
    lines: list[str] = ["# GLOSSAIRE"]
    for cat, meta in ENTITY_CATS.items():
        entries = glossaire.get(cat) or []
        if masquer_non_romanises:
            entries = [e for e in entries if not _non_romanise(e)]
        if not entries:
            continue
        lines.append(f"\n## {meta['label']}")
        for e in entries:
            if "nom" not in e and ("fr" in e or "vo" in e):   # compat ancien schéma
                e = {"nom": e.get("fr") or e.get("vo", ""),
                     "variantes": [e["vo"]] if e.get("vo") and e.get("vo") != e.get("fr") else [],
                     "interdits": e.get("interdits", []),
                     "description": e.get("note", "")}
            lines.append(_fmt_entity(cat, e, with_desc=with_desc))
    groupes = glossaire.get("groupes") or []
    if groupes:
        lines.append("\n## Groupes (POV collectif / accords)")
        for g in groupes:
            lines.append(f"- {g.get('nom', '')} : {str(g.get('note', '')).strip()}")
    angl = glossaire.get("anglicismes") or []
    if angl:
        lines.append("\n## Anglicismes / résidus VO à remplacer")
        for a in angl:
            lines.append(f"- « {a.get('vo', '')} » → « {a.get('fr', '')} »")
    return "\n".join(lines)


def to_text(glossaire: dict, max_tokens: int | None = None,
            masquer_non_romanises: bool = False) -> str:
    """Rend le glossaire pour le modèle. Si `max_tokens` est fixé et que le glossaire
    complet dépasse ce budget, bascule sur la version COMPACTE (sans descriptions), puis
    tronque en dernier recours — pour ne JAMAIS faire déborder le contexte.

    `masquer_non_romanises` : cf. `_render`. À passer à `True` pour les agents qui
    CONSOMMENT le glossaire (traducteur, correcteur, mise en page), jamais pour ceux qui le
    CONSTRUISENT."""
    full = _render(glossaire, with_desc=True, masquer_non_romanises=masquer_non_romanises)
    if max_tokens is None or _approx_tokens(full) <= max_tokens:
        return full
    compact = _render(glossaire, with_desc=False, masquer_non_romanises=masquer_non_romanises)
    if _approx_tokens(compact) <= max_tokens:
        return compact
    budget_chars = max_tokens * 4 - 80        # réserve la place du message de troncature
    out, used = [], 0
    for ln in compact.splitlines():
        if used + len(ln) + 1 > budget_chars:
            out.append("(… glossaire tronqué — trop volumineux pour le contexte)")
            break
        out.append(ln)
        used += len(ln) + 1
    return "\n".join(out)


_SECTION_NAME = {
    "personnages": "PERSONNAGES", "lieux": "LIEUX", "organisations": "ORGANISATIONS",
    "creatures": "CRÉATURES", "objets": "OBJETS", "termes": "TERMES", "evenements": "ÉVÉNEMENTS",
}


def to_sectioned(glossaire: dict) -> str:
    """Rend le glossaire au format SECTIONNÉ « machine » (celui que parse_notes relit
    et que produisent terminologue/glossariste). Sert d'entrée à l'optimisation."""
    if not glossaire:
        return ""
    out: list[str] = []
    for cat, meta in ENTITY_CATS.items():
        entries = glossaire.get(cat) or []
        if not entries:
            continue
        out.append(f"### {_SECTION_NAME[cat]}")
        for e in entries:
            if "nom" not in e and ("fr" in e or "vo" in e):   # compat ancien schéma
                e = {"nom": e.get("fr") or e.get("vo", ""),
                     "variantes": [e["vo"]] if e.get("vo") and e.get("vo") != e.get("fr") else [],
                     "interdits": e.get("interdits", []), "description": e.get("note", "")}
            fields = []
            if meta.get("genre"):
                fields.append(f"genre: {e.get('genre') or '?'}")
            if e.get("pluriel"):
                fields.append(f"pluriel: {e['pluriel']}")
            if e.get("variantes"):
                fields.append("variantes: " + ", ".join(e["variantes"]))
            if e.get("termes_source"):
                fields.append("termes_source: " + ", ".join(e["termes_source"]))
            if e.get("interdits"):
                fields.append("interdits: " + ", ".join(e["interdits"]))
            if "traduire" in e and e["traduire"] is not None:
                fields.append("traduire: " + ("oui" if e["traduire"] else "non"))
            if e.get("force"):
                fields.append("force: oui")
            desc = " ; ".join(x for x in (e.get("role"), e.get("description")) if x)
            line = "- " + e.get("nom", "")
            for f in fields:
                line += " | " + f
            if desc:
                line += " | " + desc
            out.append(line)
    if glossaire.get("groupes"):
        out.append("### GROUPES")
        for g in glossaire["groupes"]:
            out.append(f"- {g.get('nom', '')} : {str(g.get('note', '')).strip()}")
    if glossaire.get("anglicismes"):
        out.append("### ANGLICISMES")
        for a in glossaire["anglicismes"]:
            out.append(f"- {a.get('vo', '')} → {a.get('fr', '')}")
    return "\n".join(out)
