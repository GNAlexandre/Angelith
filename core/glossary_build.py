# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Construction incrémentale du glossaire à partir des relevés du terminologue.

Le terminologue est appelé bloc par bloc en voyant le glossaire DÉJÀ construit.
Ses notes sont rendues dans un format SECTIONNÉ et catégorisé (cf.
prompts/terminologue.md), parsé ici de façon DÉTERMINISTE (le modèle ne produit
jamais de YAML, qui serait fragile) :

  ### PERSONNAGES
  - <Nom> | genre: <masculin|féminin|?> | variantes: <a, b> | <description>
  ### LIEUX
  - <Nom> | variantes: <…> | <description>
  ### CRÉATURES
  - <Nom> | genre: <…> | <description>
  ### OBJETS
  - <Nom> | traduire: <oui|non> | <description>
  ### ORGANISATIONS
  - <Nom> | <description>
  ### TERMES
  - <Nom> | interdits: <x, y> | traduire: <oui|non> | <description>
  ### ÉVÉNEMENTS
  - <Nom> | <description>
  ### ANGLICISMES
  - <vo> → <fr>

La fusion conserve les entrées existantes (utilisateur/blocs précédents) et ne
fait que les ENRICHIR (union des variantes, genre « ? » → genre défini, ajout
d'interdits) ou ajouter de nouvelles entrées — jamais d'écrasement.
"""
from __future__ import annotations

import re
import unicodedata

from . import glossary, glossary_lang, tokens
from .glossary import ENTITY_CATS
from .glossary_import import _clean

# ⚠ AUCUN `\s*` collé à un quantificateur sur `.` dans les motifs ci-dessous, et c'est une
# règle, pas un hasard. `(.+?)\s*` fait de `.` et de `\s` deux façons d'absorber le même
# espace : le moteur doit alors essayer chaque partage possible avant de conclure, d'où un
# coût qui croît plus vite que la ligne (`python:S8786`). Ces motifs lisent la sortie d'un
# LLM, c'est-à-dire du texte dont la longueur n'est bornée par rien.
#
# Le rognage se fait donc EN PYTHON, chez l'appelant — qui le faisait déjà (`.strip()`,
# `_clean`, `_tag_to_fields`) : la double sécurité était précisément ce qui rendait le `\s*`
# invisible. L'équivalence des deux formes est vérifiée sur corpus par
# `tests/test_glossary_build_motifs.py`.
_BULLET = re.compile(r"^\s*[-•*]\s+")
_HEADER = re.compile(r"^\s*#{1,6}\s*(.+)$")
_FEM = {"féminin", "feminin", "female", "femme", "f"}
_MASC = {"masculin", "male", "homme", "m"}
_UNKNOWN = {"?", "??", "indéterminé", "indetermine", "indéterminée", "inconnu",
            "inconnue", "n/a", "na", "non déterminé", "non determine", "-", "—"}
#: Les cinq graphies de flèche que le modèle produit. Sortie en constante : trois motifs
#: l'utilisaient, chacun avec sa propre copie.
_FLECHE = r"(?:→|=>|➔|⇒|->)"
_ANGL_SEP = re.compile(_FLECHE)
# Garde-fous contre les sorties mal formées du glossariste/terminologue (observés en
# pratique) : « Nom → interdits: X » écrit directement dans le nom (au lieu d'un « | »),
# et « Nom — description » sans aucun « | » du tout.
_ARROW_INTERDIT = re.compile(rf"^(.*?){_FLECHE}\s*interdits?\s*:(.*)$", re.I)
#: Le tiret cadratin qui sépare « Nom — description ». Cherché plutôt qu'apparié en entier :
#: la borne « nom d'au plus 60 caractères » se vérifie en Python (cf. `_nom_et_description`),
#: là où `(.{1,60}?)\s+` la faisait payer par un essai de partage à chaque position.
_SEPARATEUR_TIRET = re.compile(r"\s[—–]\s")
#: Longueur maximale du NOM dans « Nom — description ». Au-delà, la ligne est une phrase.
_NOM_TIRET_MAX = 60
_PHRASE_HINT = re.compile(r"\b(qui|dont|lors|ici|elle|il|leur|ses|son|sa)\b", re.I)
# « X → Y [TAG] » ou « X → Y (TAG) » : renommage/reclassification proposé par le modèle
# (ex. « Diablotin → diablotin [NE PAS TRADUIRE] », « Croyance → La Onzième Bête »).
# Distinct de _ARROW_INTERDIT (qui exige littéralement « interdits: » après la flèche) —
# ce motif-ci est plus général et n'a pas ce mot-clé.
#
# Le second groupe exclut `[` et `(` au lieu d'être un `.+?` que le tag optionnel devait
# lui disputer : la frontière devient déterministe au lieu d'être négociée.
_RENAME_ARROW = re.compile(
    rf"^(.+?){_FLECHE}([^\[\(]+)(?:[\[\(]([^\]\)]+)[\]\)])?\s*$")
# « Nom [TAG] » ou « Nom (TAG) » SANS flèche — tag collé directement au nom au lieu
# d'être un champ séparé (ex. « Homme-Bête [masculin] », « Gremian [masculin] »).
_TAG_ONLY = re.compile(r"^(.+?)[\[\(]([^\]\)]+)[\]\)]\s*$")


def _nom_et_description(ligne: str) -> tuple[str, str] | None:
    """« Nom — longue description » sans aucun « | » : les deux morceaux, ou `None`.

    Remplace le motif `^(.{1,60}?)\\s+[—–]\\s+(.+)$`, dont la borne de longueur obligeait le
    moteur à réessayer chaque partage entre le nom et l'espace qui suit."""
    m = _SEPARATEUR_TIRET.search(ligne)
    if not m:
        return None
    gauche, droite = ligne[:m.start()].strip(), ligne[m.end():].strip()
    if not gauche or len(gauche) > _NOM_TIRET_MAX or not droite:
        return None
    return gauche, droite


def _tag_to_fields(tag: str) -> dict:
    """Convertit un tag entre crochets/parenthèses en champ structuré. Tag non
    reconnu → ignoré proprement (ni perdu, ni forcé dans un champ qui n'a pas de sens)."""
    t = tag.strip().lower()
    if "ne pas traduire" in t:
        return {"traduire": False}
    if t in ("masculin", "homme", "m"):
        return {"genre": "masculin"}
    if t in ("féminin", "feminin", "femme", "f"):
        return {"genre": "féminin"}
    if t == "?":
        return {"genre": "?"}
    return {}


def _strip_trailing_tag(nom: str) -> tuple[str, dict]:
    m = _TAG_ONLY.match(nom)
    if not m:
        return nom, {}
    fields = _tag_to_fields(m.group(2))
    return (m.group(1).strip(), fields) if fields else (nom, {})


def _split_variants_strict(val: str) -> tuple[list[str], str]:
    """Découpe une liste de VRAIES variantes (courtes, sans ponctuation de phrase).
    Dès qu'un élément ressemble à une phrase (trop long, contient un point ou un mot
    de liaison), on arrête la liste et on bascule le reste vers la description —
    garde-fou contre les blobs de scène que le 9B glisse parfois dans `variantes:`."""
    parts = [p.strip() for p in re.split(r",|(?: et )", val) if p.strip()]
    variantes, spill = [], []
    dumping = False
    for p in parts:
        if not dumping and len(p) <= 30 and "." not in p and not _PHRASE_HINT.search(p):
            variantes.append(p)
        else:
            dumping = True
            spill.append(p)
    return variantes, ", ".join(spill)

# Mots-clés d'en-tête → catégorie
# ⚠ Les mots-clés sont donnés en français ET en anglais, et ce n'est pas de la complaisance :
# le prompt du terminologue vit dans un PACK DE LANGUE CIBLE (cf. `core/langues.py`), donc un
# pack anglais demande ses sections en anglais — et un modèle à qui l'on parle anglais écrit
# « ### CHARACTERS », pas « ### PERSONNAGES ». Sans ces alias, le glossaire d'un tome traduit
# vers l'anglais ressortirait VIDE, sans qu'aucun compteur ne s'en aperçoive.
#
# C'est aussi un garde-fou côté français : un modèle dérive parfois vers l'anglais tout seul.
_CAT_KEYS = [
    (("personnage", "character"), "personnages"),
    (("lieu", "place", "location", "setting"), "lieux"),
    (("organisation", "organization", "faction"), "organisations"),
    (("creature", "créature", "race", "bete", "bête", "monstre", "beast", "monster"),
     "creatures"),
    (("objet", "item", "object"), "objets"),
    (("terme", "term", "concept", "lore", "vocab"), "termes"),
    (("evenement", "événement", "event"), "evenements"),
    (("groupe", "group"), "groupes"),
    (("anglicisme", "résidu", "residu", " vo", "loanword", "leftover", "untranslated"),
     "anglicismes"),
]


#: Nom de champ anglais → nom FRANÇAIS, qui est celui du schéma. Les valeurs, elles, sont
#: déjà bilingues : `_truthy` accepte « yes »/« true », `_genre_of` accepte « male »/« female ».
_ALIAS_CHAMPS = {
    "gender": "genre", "plural": "pluriel", "variant": "variantes", "variants": "variantes",
    "source_term": "termes_source", "source_terms": "termes_source",
    "forbidden": "interdits", "banned": "interdits",
    "translate": "traduire", "forced": "force",
}


# Marques de voisement des kana (dakuten ゛ / handakuten ゜). Ce sont des `Mn`, exactement
# comme les accents latins — mais ce ne sont PAS des accents : elles distinguent des
# caractères. Les retirer confondrait ハ / バ / パ, et donc `ピカ` avec `ヒカ` : deux entités
# distinctes fusionneraient en silence.
_VOISEMENT_KANA = "゙゚"


def _strip_accents(s: str) -> str:
    """Retire les accents LATINS. Préserve le voisement des kana (cf. `_VOISEMENT_KANA`),
    puis recompose en NFC pour que `が` ressorte en un seul caractère et non en `か` + marque
    — sinon la clé dépendrait de la forme de normalisation du fichier d'entrée."""
    sans = "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn" or c in _VOISEMENT_KANA)
    return unicodedata.normalize("NFC", sans)


# Tout ce qui n'est NI alphanumérique latin NI porteur de texte CJK devient un séparateur.
# La classe CJK vient de `tokens` : la redéfinir ici rouvrirait la divergence que
# `core/glossary_lang.py` existe pour fermer.
_NON_CLE = re.compile(f"[^a-z0-9 {tokens.CLASSE_CJK_TEXTE}]+")


def _norm(s: str) -> str:
    """Clé de comparaison : sans accents, minuscule, sans ponctuation ni espaces multiples.

    ⚠ Le CJK doit SURVIVRE. L'ancienne classe `[^a-z0-9 ]+` réduisait toute chaîne
    idéographique à la chaîne vide : `_norm("八重山吹")` valait `""`. Conséquence en
    cascade, jamais visible : `build_index` n'indexait aucune entrée japonaise (`if nk:`
    faux), `_find_any` rendait toujours `None`, `_merge_entity` répondait toujours « add »,
    et les variantes japonaises étaient silencieusement jetées. Mesuré sur
    `sources/roman A/glossaire.bak.yaml` : 3 doublons purs que la fusion
    déterministe n'avait pas vus."""
    s = _strip_accents((s or "").lower())
    return re.sub(r"\s+", " ", _NON_CLE.sub(" ", s)).strip()


def _header_to_cat(text: str) -> str | None:
    low = " " + _strip_accents(text.lower())
    for keys, cat in _CAT_KEYS:
        if any(k in low for k in keys):
            return cat
    return None


def _genre_of(val: str) -> str:
    v = val.strip().lower().rstrip(".")
    first = v.split()[0] if v.split() else ""
    if first in _FEM:
        return "féminin"
    if first in _MASC:
        return "masculin"
    return "?"


def _split_list(val: str) -> list[str]:
    """Découpe une liste sur , ; / ou « et » — SANS jamais couper à l'intérieur d'une
    parenthèse (garde-fou : le modèle écrit parfois une remarque du type
    « ? (orthographe erronée de X, Y dans le texte source) » où la virgule est interne
    à la parenthèse, pas un vrai séparateur de liste)."""
    out, buf, depth = [], [], 0
    tokens = re.split(r"([,;/]| et )", val)   # capture les séparateurs pour les ignorer
    for i in range(0, len(tokens), 2):
        piece = tokens[i]
        depth += piece.count("(") - piece.count(")")
        buf.append(piece)
        is_sep = i + 1 < len(tokens)
        if is_sep and depth > 0:
            buf.append(tokens[i + 1])          # séparateur À L'INTÉRIEUR d'une parenthèse : on le garde
            continue
        c = _clean("".join(buf))
        buf = []
        if c and c.lower() not in ("aucun", "aucune", "-", "—", "néant", "neant", "n/a"):
            out.append(c)
    return out


def _truthy(val: str) -> bool:
    return val.strip().lower() in ("oui", "yes", "true", "vrai", "1", "o")


# ⚠ Noms de champs en français ET en anglais, pour la même raison que `_CAT_KEYS` : un pack
# de langue cible anglais fait écrire `gender:`, `variants:`, `source_terms:`. Les alias sont
# ramenés au nom FRANÇAIS juste après, parce que c'est lui le schéma du glossaire — rien ici
# ne change le format du fichier, seulement ce qu'on sait lire.
_CHAMP = re.compile(
    r"(genre|gender|pluriel|plural|variantes?|variants?|termes?_sources?|"
    r"source_terms?|interdits?|forbidden|banned|traduire|translate|force|"
    r"forced|role|rôle)\s*[:=]\s*(.*)$", re.I)

#: Le modèle écrit parfois « NE PAS TRADUIRE — description » comme PREMIER interdit au lieu
#: d'utiliser le champ `traduire:`.
_NE_PAS_TRADUIRE = re.compile(r"^ne\s+pas\s+traduire\b", re.I)
_NE_PAS_TRADUIRE_PREFIXE = re.compile(r"^ne\s+pas\s+traduire\b\s*[—–:-]*\s*", re.I)


def _contenu_de_puce(raw: str) -> str | None:
    """Le texte d'une ligne à puce, ou `None` si la ligne n'est pas une entrée à lire.

    Écarte les non-puces, les puces vides et les trois formes de « je n'ai rien relevé »
    que le terminologue produit (« rien », « RAS », un ⚠, une divergence signalée)."""
    if not _BULLET.match(raw):
        return None
    s = _BULLET.sub("", raw).strip()
    low = s.lower()
    if not s or low.startswith(("rien", "(rien", "ras")) or s.startswith("⚠") or "divergence" in low:
        return None
    return s


def _anglicisme(s: str) -> dict | None:
    """« vo → fr »."""
    parts = _ANGL_SEP.split(s, maxsplit=1)
    if len(parts) != 2:
        return None
    vo, fr = _clean(parts[0]), _clean(parts[1])
    return {"vo": vo, "fr": fr} if vo and fr else None


def _groupe(s: str) -> dict | None:
    """« nom : note »."""
    if ":" not in s:
        return None
    nom, note = s.split(":", 1)
    nom = _clean(nom)
    return {"nom": nom, "note": note.strip()} if nom else None


def _nom_et_champs_implicites(nom_raw: str) -> tuple[str, list[str], dict, list[str]]:
    """Les trois garde-fous qui rattrapent un nom que le modèle a mal formé.

    1. « Nom → interdits: X » écrit directement dans le nom (au lieu d'un « | ») ;
    1bis. « X → Y [TAG] » — renommage/reclassification (ex. « Diablotin → diablotin [NE PAS
       TRADUIRE] »). On garde X (généralement mieux capitalisé dans les cas observés) comme
       forme canonique, Y devient une variante ; le tag, s'il est reconnu, devient un champ
       structuré. Évite de créer une entrée fantôme par mention ;
    1ter. « Nom [TAG] » / « Nom (TAG) » SANS flèche — tag collé au nom
       (ex. « Homme-Bête [masculin] », « Gremian [masculin] »).

    Renvoie `(nom nettoyé, interdits, champs, variantes)`."""
    auto_interdits: list[str] = []
    auto_fields: dict = {}
    auto_variantes: list[str] = []
    ma = _ARROW_INTERDIT.match(nom_raw)
    if ma:
        nom_raw = ma.group(1).strip()
        auto_interdits = _split_list(ma.group(2))
    else:
        mr = _RENAME_ARROW.match(nom_raw)
        if mr:
            left, right, tag = mr.group(1).strip(), mr.group(2).strip(), mr.group(3)
            nom_raw = left
            if right and _norm(right) != _norm(left):
                auto_variantes.append(right)
            if tag:
                auto_fields.update(_tag_to_fields(tag))
    nom_raw, tag_fields = _strip_trailing_tag(nom_raw)
    auto_fields.update(tag_fields)
    return nom_raw, auto_interdits, auto_fields, auto_variantes


def _appliquer_champ(entry: dict, key: str, val: str, *, vnom: list[str],
                     auto_interdits: list[str], desc_parts: list[str]) -> None:
    """Range UN « champ: valeur » dans l'entrée, ou verse son trop-plein en description.

    ⚠ Deux champs ont un garde-fou, et c'est la raison d'être de cette fonction : le modèle
    verse régulièrement une phrase entière dans `variantes:` ou dans `termes_source:`. On
    n'en garde que les formes COURTES, le reste part en description au lieu de polluer une
    liste qui sert ensuite de clé de recherche."""
    if key.startswith("genre"):
        entry["genre"] = _genre_of(val)
    elif key.startswith("pluriel"):
        entry["pluriel"] = _clean(val)
    elif key.startswith("terme"):
        ts, spill = _split_variants_strict(val)
        entry["termes_source"] = ts
        if spill:
            desc_parts.append(spill)
    elif key.startswith("variante"):
        vs, spill = _split_variants_strict(val)
        entry["variantes"] = vnom + vs
        if spill:
            desc_parts.append(spill)
    elif key.startswith("interdit"):
        items = auto_interdits + _split_list(val)
        if items and _NE_PAS_TRADUIRE.match(items[0]):
            first = items.pop(0)
            entry["traduire"] = False
            rest = _NE_PAS_TRADUIRE_PREFIXE.sub("", first).strip()
            if rest:
                desc_parts.append(rest)
        entry["interdits"] = items
    elif key.startswith("traduire"):
        entry["traduire"] = _truthy(val)
    elif key.startswith("force"):
        entry["force"] = _truthy(val)
    elif key.startswith("role"):
        entry["role"] = _clean(val)


def _entree_entite(s: str, cat: str | None) -> tuple[dict | None, str]:
    """Une ligne « Nom | champ: valeur | … | description » → `(entrée, catégorie)`.

    `(None, …)` quand il ne reste aucun nom exploitable."""
    segs = [seg.strip() for seg in s.split("|")]
    nom_raw, auto_interdits, auto_fields, auto_variantes = _nom_et_champs_implicites(
        segs[0].strip())

    auto_desc = ""
    # Garde-fou 2 : « Nom — longue description » sans AUCUN « | » dans toute la ligne (le
    # modèle a oublié le format pipe) → on récupère quand même nom + description.
    if len(segs) == 1:
        md = _nom_et_description(nom_raw)
        if md:
            nom_raw, auto_desc = md
    nom = _clean(nom_raw)
    target = cat or "termes"
    if not nom:
        return None, target

    # « Feodor Jessman / Féodor » → nom canonique + variantes (évite les doublons)
    vnom: list[str] = list(auto_variantes)
    if "/" in nom:
        parts = [_clean(p) for p in nom.split("/") if _clean(p)]
        if len(parts) > 1:
            nom, vnom = parts[0], parts[1:] + vnom

    entry: dict = {"nom": nom, **auto_fields}
    if vnom:
        entry["variantes"] = vnom
    if auto_interdits:
        entry["interdits"] = auto_interdits

    desc_parts: list[str] = [auto_desc] if auto_desc else []
    for seg in segs[1:]:
        mf = _CHAMP.match(seg)
        if mf:
            brut = _strip_accents(mf.group(1).lower())
            _appliquer_champ(entry, _ALIAS_CHAMPS.get(brut, brut), mf.group(2).strip(),
                             vnom=vnom, auto_interdits=auto_interdits, desc_parts=desc_parts)
        elif seg:
            desc_parts.append(seg)
    if desc_parts:
        entry["description"] = _clean(" — ".join(desc_parts))

    # Genre par défaut « ? » pour les catégories qui en portent un
    if target in ENTITY_CATS and ENTITY_CATS[target].get("genre") and "genre" not in entry:
        entry["genre"] = "?"
    # Réparation déterministe AVANT d'entrer dans le glossaire : une graphie source dans
    # `nom` ou `variantes` part vers `termes_source` (cf. `glossary_lang`). C'est le seul
    # endroit où une entrée est créée, donc le seul à instrumenter — il couvre le
    # terminologue, le glossariste (aller-retour `to_sectioned` → LLM → ici) et
    # `glossary_import`. Les entrées non romanisables sont conservées et marquées ;
    # `glossary_lang.auditer` les remonte ensuite au rapport.
    entry, _ = glossary_lang.reparer_entree(entry)
    return entry, target


def parse_notes(text: str) -> dict:
    """Transforme les notes SECTIONNÉES du terminologue en dict de glossaire."""
    out = glossary.empty()
    cat: str | None = None
    for raw in text.splitlines():
        h = _HEADER.match(raw)
        if h and not _BULLET.match(raw):
            cat = _header_to_cat(h.group(1)) or cat
            continue
        s = _contenu_de_puce(raw)
        if s is None:
            continue
        if cat == "anglicismes":
            anglicisme = _anglicisme(s)
            if anglicisme:
                out["anglicismes"].append(anglicisme)
            continue
        if cat == "groupes":
            groupe = _groupe(s)
            if groupe:
                out["groupes"].append(groupe)
            continue
        entry, target = _entree_entite(s, cat)
        if entry is not None:
            out.setdefault(target, []).append(entry)
    return out


def _is_def(g) -> bool:
    return g not in ("?", "", None)


def _cles_de(e: dict) -> list[str]:
    """Toutes les formes sous lesquelles une entrée peut être retrouvée.

    `termes_source` EN FAIT PARTIE, et c'est indispensable sur un pivot non latin : c'est
    la graphie d'origine qui est l'identité STABLE de l'entité, tandis que sa romanisation
    varie d'un relevé à l'autre (« Amane » / « Amané » / « Ten-sei »). Sans elle, sortir le
    CJK des `variantes` — ce que fait `glossary_lang.reparer_entree` — RETIRERAIT du
    dédoublonnage au lieu d'en ajouter.

    Le risque symétrique est assumé : deux entités DE LA MÊME CATÉGORIE qui partageraient
    un mot source fusionneraient. L'index est par catégorie, et un `termes_source` commun à
    deux entités distinctes est en pratique un relevé erroné."""
    return [e.get("nom", "")] + list(e.get("variantes") or []) + list(e.get("termes_source") or [])


def build_index(glossaire: dict) -> dict[str, dict[str, dict]]:
    """Index {catégorie: {clé normalisée (nom OU variante): entrée}}, pour un lookup
    O(1) amorti au lieu du scan linéaire de `_find_any`. Le glossaire est celui de
    TOUTE une série (pas juste un tome) : plus il grossit d'un tome à l'autre, plus ce
    scan devenait le vrai coût dominant sur les fusions répétées bloc par bloc.
    À reconstruire (pas à réutiliser tel quel) si `glossaire` est REMPLACÉ (ex. après
    une optimisation) — l'index reste valide tant que `glossaire` est seulement MUTÉ
    via `merge_notes(..., index=...)`."""
    idx: dict[str, dict[str, dict]] = {}
    for cat in ENTITY_CATS:
        cat_idx: dict[str, dict] = {}
        for e in glossaire.get(cat) or []:
            for k in _cles_de(e):
                nk = _norm(k)
                if nk:
                    cat_idx[nk] = e
        idx[cat] = cat_idx
    return idx


def _find(entries: list[dict], nom: str) -> dict | None:
    """Cherche une entrée par nom OU par variante (clé normalisée)."""
    key = _norm(nom)
    for e in entries:
        if _norm(e.get("nom", "")) == key:
            return e
        if any(_norm(v) == key for v in (e.get("variantes") or [])):
            return e
    return None


def _find_any(entries: list[dict], keys: list[str], cat_index: dict[str, dict] | None = None) -> dict | None:
    """Cherche une entrée existante dont l'une des formes (cf. `_cles_de`) correspond à
    l'une des `keys` fournies. Dédoublonne même quand la forme canonique diffère
    (« Tiat » vs « Tiat Siba Ignareo »). Avec `cat_index` fourni (cf. `build_index`),
    lookup indexé au lieu du scan linéaire de `entries`.

    ⚠ Les deux chemins DOIVENT considérer les mêmes formes : l'indexé passe par
    `build_index`, le linéaire par `_cles_de` ci-dessous. Les laisser diverger ferait
    dédoublonner ou non selon qu'un index a été fourni — un piège d'autant plus pénible
    que `merge_notes` accepte les deux."""
    if cat_index is not None:
        for k in keys:
            nk = _norm(k)
            if nk and nk in cat_index:
                return cat_index[nk]
        return None
    wanted = {_norm(k) for k in keys if _norm(k)}
    for e in entries:
        cand = {_norm(k) for k in _cles_de(e)} - {""}
        if wanted & cand:
            return e
    return None


def _merge_entity(base_list: list[dict], e: dict, cat: str,
                  index: dict[str, dict[str, dict]] | None = None) -> str:
    """Fusionne une entité dans base_list. Renvoie 'add' | 'merge' | 'conflit'.
    `index` (cf. `build_index`) est mis à jour EN PLACE au fil des ajouts/fusions,
    pour rester valide sur tout le run — pas de reconstruction à chaque appel."""
    cat_index = index.get(cat) if index is not None else None
    keys = _cles_de(e)
    cur = _find_any(base_list, keys, cat_index=cat_index)
    if cur is None:
        base_list.append(e)
        if cat_index is not None:
            for k in keys:
                nk = _norm(k)
                if nk:
                    cat_index[nk] = e
        return "add"
    status = "merge"
    # variantes : union (toutes les formes vues ≠ nom canonique deviennent des variantes)
    vs = list(cur.get("variantes") or [])
    for v in ([e.get("nom", "")] + (e.get("variantes") or [])):
        # ⚠ `_norm(v)` vide : une entrée aplatie qui n'a PAS de rendu dans la cible courante
        # porte un `nom` vide (cf. `glossary_cibles.aplatir`). L'ajouter en variante
        # insérerait une chaîne vide qui ne désigne rien et que rien ne rattraperait.
        if _norm(v) and _norm(v) != _norm(cur.get("nom", "")) and all(_norm(v) != _norm(x) for x in vs):
            vs.append(v)
    if vs:
        cur["variantes"] = vs
        if cat_index is not None:
            for v in vs:
                nv = _norm(v)
                if nv:
                    cat_index[nv] = cur
    # genre : ? → défini ; conflit → garde + ⚠
    if ENTITY_CATS.get(cat, {}).get("genre"):
        cg, ng = cur.get("genre", "?"), e.get("genre", "?")
        if not _is_def(cg) and _is_def(ng):
            cur["genre"] = ng
        elif _is_def(cg) and _is_def(ng) and cg != ng:
            if "⚠" not in (cur.get("description") or ""):
                cur["description"] = (cur.get("description", "")
                                      + " ⚠ genre vu différemment selon les blocs — à vérifier").strip()
            status = "conflit"
    # interdits : union
    if e.get("interdits"):
        merged = list(cur.get("interdits") or [])
        for x in e["interdits"]:
            if all(_norm(x) != _norm(y) for y in merged):
                merged.append(x)
        cur["interdits"] = merged
    # termes_source : union — les mots de la source étrangère correspondant à ce terme
    if e.get("termes_source"):
        merged_ts = list(cur.get("termes_source") or [])
        for x in e["termes_source"]:
            if all(_norm(x) != _norm(y) for y in merged_ts):
                merged_ts.append(x)
        cur["termes_source"] = merged_ts
        if cat_index is not None:
            for x in merged_ts:
                nx = _norm(x)
                if nx:
                    cat_index[nx] = cur
    # traduire : prend la valeur définie si la base est absente OU encore indécise (None)
    if e.get("traduire") is not None and cur.get("traduire") is None:
        cur["traduire"] = e["traduire"]
    # description : la base (utilisateur/antérieure) prime ; sinon on prend la nouvelle
    if not cur.get("description") and e.get("description"):
        cur["description"] = e["description"]
    if not cur.get("role") and e.get("role"):
        cur["role"] = e["role"]
    if not cur.get("pluriel") and e.get("pluriel"):
        cur["pluriel"] = e["pluriel"]
    if e.get("force"):
        cur["force"] = True
    return status


def merge_notes(base: dict, notes_text: str, index: dict[str, dict[str, dict]] | None = None) -> dict:
    """Fusionne les notes d'UN bloc dans le glossaire vivant `base` (muté sur place).
    Renvoie le nombre d'éléments ajoutés/fusionnés/en conflit.
    `index` (facultatif, cf. `build_index`) accélère la recherche de doublon sur un
    glossaire volumineux (accumulé sur toute une série) — sans lui, comportement
    identique à avant (scan linéaire), pour ne rien changer aux appelants existants."""
    return fusionner_glossaire(base, parse_notes(notes_text), index=index)


def fusionner_glossaire(base: dict, autre: dict,
                        index: dict[str, dict[str, dict]] | None = None) -> dict:
    """Fusionne un glossaire DÉJÀ PARSÉ dans `base` (muté sur place).

    Pendant dict→dict de `merge_notes`, et mêmes règles exactement — c'est le même corps :
    `base` prime sur `nom`/`description`/`role`, union sur `variantes`/`termes_source`/
    `interdits`, genre « ? » → genre défini. Le terminologue arrive par du TEXTE, un ancien
    glossaire YAML réintégré arrive par un dict ; les faire diverger ferait dédoublonner
    différemment selon la porte d'entrée."""
    new = autre
    added = {"ajouts": 0, "fusions": 0, "conflits": 0}

    for cat in ENTITY_CATS:
        base.setdefault(cat, [])
        for e in new.get(cat, []):
            st = _merge_entity(base[cat], e, cat, index=index)
            if st == "add":
                added["ajouts"] += 1
            elif st == "conflit":
                added["conflits"] += 1
            else:
                added["fusions"] += 1

    base.setdefault("groupes", [])
    seen_g = {_norm(g.get("nom", "")) for g in base["groupes"]}
    for g in new.get("groupes", []):
        if _norm(g["nom"]) not in seen_g:
            base["groupes"].append(g)
            seen_g.add(_norm(g["nom"]))
            added["ajouts"] += 1

    base.setdefault("anglicismes", [])
    seen_a = {_norm(a.get("vo", "")) for a in base["anglicismes"]}
    for a in new.get("anglicismes", []):
        if _norm(a["vo"]) not in seen_a:
            base["anglicismes"].append(a)
            seen_a.add(_norm(a["vo"]))
            added["ajouts"] += 1
    return added


def consolidate_into(glossary_path, notes_text: str) -> dict:
    """Variante « one-shot » : charge le glossaire, fusionne les notes, sauvegarde."""
    base = glossary.load(glossary_path) or glossary.empty()
    added = merge_notes(base, notes_text)
    glossary.save(base, glossary_path)
    return added
