# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La **bible visuelle** d'une œuvre : `sources/<Projet>/bible.yaml`.

Ce que le glossaire dit d'un personnage est TERMINOLOGIQUE — son nom rendu, son genre
grammatical, ses variantes, une description narrative. Ce que la bible en dit est VISUEL —
la couleur de ses cheveux, sa tenue, et les illustrations du tome où on peut le voir.

## Pourquoi un fichier séparé, et pas un champ de plus dans `glossaire.yaml`

Trois raisons, et **la première est un interdit du dépôt**.

1. L'interdit n° 1 et la règle MAJEUR du `CHANGELOG` disent la même chose : un changement du
   schéma `glossaire.yaml` qui invalide les caches est un MAJEUR, et une relance de tome coûte
   des heures de GPU. Ajouter `apparence` à `glossary.FIELD_ORDER["personnages"]` ferait
   entrer ce champ dans `glossary.to_text()`, donc dans le prompt du traducteur, donc dans le
   **caractère de la traduction** de tous les tomes.
2. `glossary.save` réécrit le fichier avec ses bannières et son ordre canonique. Un champ de
   plus, c'est un diff sur les **326 entrées de personnage** des 14 projets vivants
   (mesuré le 2026-08-29).
3. La bible porte des **chemins d'images** et des recadrages. Ce n'est pas de la terminologie.

⚠ **La bible n'entre JAMAIS dans le prompt du traducteur.** Le seul champ qui peut traverser
vers la traduction est `genre`, écrit dans le glossaire par un geste explicite
(`tools/bible.py --revue --ecrire-genre`), jamais en défaut.

⚠ **Elle reste sous `sources/`**, que `.gitignore` exclut en bloc avec cette raison écrite :
« le dépôt devient public, et l'arbre git exposait alors le NOM de chaque œuvre comme nom de
dossier ». Ne pas la déplacer, ne pas créer de `bibles/` à la racine.

## La règle qui fait toute la valeur du fichier

**Un attribut sans `citations[]` n'entre pas dans la bible.** C'est la règle des chiffres du
dépôt, transposée : un attribut sans sa source n'est pas une observation, c'est une
invention. `save` la fait respecter — un attribut non cité est retiré à l'écriture, pas
signalé et gardé. C'est exactement ce qui distingue « illustration cohérente avec l'œuvre »
de « illustration plausible ».

⚠ La source d'une citation peut être un **chapitre** (`chapters/ch03.md`, avec la phrase) ou
une **illustration** (`media/…jpeg`, avec ce que le modèle dit y voir). Le plan écrivait « une
phrase » ; la mesure du 2026-08-29 montre pourquoi l'image compte aussi — et pourquoi elle
doit être citée : sur 12 descriptions d'illustrations par `yume-27b`, **une** attribue au
premier plan un homme aux cheveux foncés en chapeau de paille là où le dessin montre une
jeune femme aux cheveux clairs sous un casque. Une citation nommant le fichier rend cette
erreur vérifiable en l'ouvrant ; un attribut nu ne le serait pas.
"""
from __future__ import annotations

from pathlib import Path

import yaml

#: Version du schéma. Un fichier sans `version` est traité comme la 1.
VERSION = 1

#: Les attributs d'apparence, dans l'ordre d'écriture. `signes` est une liste (cicatrice,
#: lunettes, uniforme…), les quatre autres sont des chaînes.
ATTRIBUTS = ("cheveux", "yeux", "age_apparent", "tenue", "signes")
ATTRIBUTS_LISTE = frozenset({"signes"})

#: Valeurs acceptées pour `genre_confirme`. La chaîne vide est l'abstention, et c'est le
#: défaut : `glossary.py` étiquette la catégorie « Personnages (le genre commande les
#: accords) », donc une valeur fausse ici coûte plus qu'une valeur absente.
GENRES = ("", "féminin", "masculin")

#: D'où vient le genre confirmé.
SOURCES_GENRE = ("", "illustration", "texte", "humain")

#: Niveaux de confiance d'une référence. `proposee` = le déterministe l'a suggérée,
#: `llm` = un modèle l'a attribuée, `humaine` = un œil l'a validée. Seule la dernière compte
#: dans la couverture de référence du banc.
CONFIANCES = ("proposee", "llm", "humaine")

#: Rôle d'une référence : l'identité du personnage, ou le registre graphique du tome. Deux
#: usages, deux canaux du modèle d'image (cf. `PLAN-26` L26.0) — les mélanger, c'est laisser
#: une ancre de style contaminer l'identité.
ROLES_REFERENCE = ("identite", "style")

#: Ordre canonique des champs d'un personnage.
#:
#: ⚠ `images_generees` est une SORTIE, jamais une entrée, et sa séparation d'avec
#: `references` est le point le plus important du lot 27 (L27.3). Reboucler une image
#: produite dans le conditionnement de la suivante fait dériver le personnage à chaque tour,
#: et la dérive est invisible image par image — on ne s'en aperçoit qu'au cinquième. Les deux
#: listes ne se mélangent donc jamais : `illustration/identite.references_de` ne lit que
#: `references`, et `illustration/galerie.inscrire` n'écrit que `images_generees`.
CHAMPS_PERSONNAGE = ("nom", "genre_confirme", "source_genre", "apparence", "citations",
                     "references", "images_generees", "valide_par_humain")

_ENTETE = (
    "# ============================================================\n"
    "#  Bible visuelle — {projet}\n"
    "#  Référentiel VISUEL de l'œuvre. Alimente l'atelier d'illustration.\n"
    "#  N'entre JAMAIS dans le prompt du traducteur.\n"
    "#  Ne remplace pas glossaire.yaml : `nom` DOIT y correspondre.\n"
    "#\n"
    "#  Règle non négociable : un attribut sans `citations[]` n'est pas\n"
    "#  écrit ici. Un attribut sans sa source n'est pas une observation.\n"
    "#\n"
    "#  `valide_par_humain: true` et `confiance: humaine` sont les deux\n"
    "#  seules marques qui comptent dans le banc — le reste est une\n"
    "#  proposition en attente de relecture.\n"
    "# ============================================================\n\n"
)


def chemin(projet_dir: str | Path) -> Path:
    """`sources/<Projet>/bible.yaml` à partir du dossier du projet."""
    return Path(projet_dir) / "bible.yaml"


def chemin_propositions(projet_dir: str | Path) -> Path:
    """`sources/<Projet>/bible.propositions.yaml` — la sortie de la passe automatique.

    ⚠ **Aucune écriture directe dans `bible.yaml`.** Le LLM et la passe lexicale écrivent
    ici ; seule la revue humaine (`tools/bible.py --revue`) fait passer une proposition dans
    la bible."""
    return Path(projet_dir) / "bible.propositions.yaml"


def vide() -> dict:
    return {"version": VERSION, "style": _style_vide(), "personnages": []}


def _style_vide() -> dict:
    return {"ancrages": [], "signature": signature_vide(), "mots": ""}


def signature_vide() -> dict:
    """Le bloc `style.signature` non mesuré. `echantillon: 0` et non `null` : zéro est un
    dénominateur, `null` est une absence de mesure — et les deux se disent."""
    return {"palette": [], "saturation_moyenne": None, "contraste": None,
            "densite_trait": None, "part_aplats": None, "couleur": None, "echantillon": 0}


def _apparence_vide() -> dict:
    return {a: ([] if a in ATTRIBUTS_LISTE else "") for a in ATTRIBUTS}


def personnage(nom: str) -> dict:
    """Une entrée neuve, tous champs écrits même vides — comme le glossaire, et pour la même
    raison : ce qui est visible se complète, ce qui est absent s'oublie."""
    return {"nom": nom, "genre_confirme": "", "source_genre": "",
            "apparence": _apparence_vide(), "citations": [], "references": [],
            "images_generees": [], "valide_par_humain": False}


def _rempli(valeur) -> bool:
    """Un champ est « rempli » s'il porte autre chose que son défaut."""
    if valeur is None:
        return False
    if isinstance(valeur, (str, list, dict)):
        return bool(valeur)
    return True


def fill_defaults(bible: dict) -> dict:
    """Copie de la bible où chaque entrée expose TOUS ses champs, dans un ordre stable.

    Même politique que `core.glossary.fill_defaults` : les champs-liste reçoivent toujours
    une liste FRAÎCHE, jamais un objet par défaut partagé — PyYAML crée sinon des ancres
    `&id001` / `*id001` pour les objets identiques, qui se percutent une fois plusieurs
    blocs dumpés séparément puis concaténés."""
    brut = dict(bible or {})
    style = dict(brut.get("style") or {})
    signature = dict(style.get("signature") or {})
    sortie = {
        "version": int(brut.get("version") or VERSION),
        "style": {
            "ancrages": [dict(a) for a in (style.get("ancrages") or []) if isinstance(a, dict)],
            "signature": {**signature_vide(), **signature},
            "mots": str(style.get("mots") or ""),
        },
        "personnages": [_fill_personnage(p) for p in (brut.get("personnages") or [])
                        if isinstance(p, dict)],
    }
    for cle, valeur in brut.items():                 # sections inattendues conservées
        if cle not in sortie and _rempli(valeur):
            sortie[cle] = valeur
    return sortie


def _fill_personnage(entree: dict) -> dict:
    base = personnage(str(entree.get("nom") or ""))
    apparence = dict(entree.get("apparence") or {})
    base["apparence"] = {a: (list(apparence.get(a) or []) if a in ATTRIBUTS_LISTE
                             else str(apparence.get(a) or "")) for a in ATTRIBUTS}
    base["genre_confirme"] = str(entree.get("genre_confirme") or "")
    base["source_genre"] = str(entree.get("source_genre") or "")
    base["citations"] = [dict(c) for c in (entree.get("citations") or [])
                         if isinstance(c, dict)]
    base["references"] = [dict(r) for r in (entree.get("references") or [])
                          if isinstance(r, dict)]
    base["images_generees"] = [dict(g) for g in (entree.get("images_generees") or [])
                               if isinstance(g, dict)]
    base["valide_par_humain"] = bool(entree.get("valide_par_humain"))
    sortie = {c: base[c] for c in CHAMPS_PERSONNAGE}
    for cle, valeur in entree.items():
        if cle not in sortie:
            sortie[cle] = valeur
    return sortie


# ────────────────────────  La règle de citation, appliquée  ────────────────────────

def attributs_cites(entree: dict) -> set[str]:
    """Les attributs pour lesquels l'entrée porte au moins une citation utilisable — c'est
    à dire nommant l'attribut ET portant une source."""
    return {str(c.get("attribut") or "").strip()
            for c in (entree.get("citations") or []) if isinstance(c, dict)
            and str(c.get("source") or "").strip() and str(c.get("texte") or "").strip()}


def attributs_sans_citation(bible: dict) -> list[tuple[str, str]]:
    """`[(nom du personnage, attribut)]` pour tout attribut rempli sans citation.

    C'est la fonction que le banc publie et que `save` consomme. Elle ne corrige rien : elle
    dit ce qui ne devrait pas être là."""
    fautes: list[tuple[str, str]] = []
    for entree in (bible or {}).get("personnages") or []:
        if not isinstance(entree, dict):
            continue
        cites = attributs_cites(entree)
        apparence = entree.get("apparence") or {}
        for attribut in ATTRIBUTS:
            if _rempli(apparence.get(attribut)) and attribut not in cites:
                fautes.append((str(entree.get("nom") or ""), attribut))
    return fautes


def purger_sans_citation(bible: dict) -> tuple[dict, list[tuple[str, str]]]:
    """Retire de la bible tout attribut non cité. Rend (bible purgée, ce qui a été retiré).

    ⚠ Retirer, et non signaler. Un attribut non cité gardé « en attendant » finit dans une
    image générée, où plus personne ne saura d'où il vient."""
    sortie = fill_defaults(bible)
    retires: list[tuple[str, str]] = []
    for entree in sortie["personnages"]:
        cites = attributs_cites(entree)
        for attribut in ATTRIBUTS:
            if _rempli(entree["apparence"].get(attribut)) and attribut not in cites:
                retires.append((entree["nom"], attribut))
                entree["apparence"][attribut] = [] if attribut in ATTRIBUTS_LISTE else ""
    return sortie, retires


# ──────────────────────────────  Lecture / écriture  ──────────────────────────────

def load(path: str | Path) -> dict:
    """Charge une bible. Un fichier absent ou vide rend une bible vide — pas une erreur : un
    projet sans bible est un projet dont la bible n'a pas encore été commencée."""
    p = Path(path)
    if not p.is_file():
        return vide()
    with open(p, encoding="utf-8") as fh:
        brut = yaml.safe_load(fh) or {}
    if not isinstance(brut, dict) or not brut:
        return vide()
    return fill_defaults(brut)


def save(bible: dict, path: str | Path) -> list[tuple[str, str]]:
    """Écrit la bible, tous champs visibles, et rend la liste des attributs PURGÉS.

    La purge n'est pas optionnelle et n'est pas silencieuse : elle est rendue à l'appelant,
    qui doit la dire."""
    p = Path(path)
    rempli, retires = purger_sans_citation(bible)
    p.parent.mkdir(parents=True, exist_ok=True)
    corps = yaml.safe_dump(rempli, allow_unicode=True, sort_keys=False, width=100)
    p.write_text(_ENTETE.format(projet=p.parent.name) + corps, encoding="utf-8")
    return retires


def fusionner(existante: dict, proposition: dict) -> dict:
    """Fusion **SANS ÉCRASEMENT** d'un champ déjà rempli — le patron de `core/glossary.py`.

    Un attribut, un genre ou un `mots` de style saisi à la main est prioritaire et le reste :
    relancer la passe automatique ne doit jamais défaire une relecture. Les citations et les
    références s'ajoutent sans doublon (clé : la source pour une citation, le fichier pour
    une référence), et une référence déjà marquée `humaine` n'est pas rétrogradée."""
    base = fill_defaults(existante)
    neuve = fill_defaults(proposition)
    index = {e["nom"]: e for e in base["personnages"]}

    for entree in neuve["personnages"]:
        cible = index.get(entree["nom"])
        if cible is None:
            base["personnages"].append(entree)
            index[entree["nom"]] = entree
            continue
        if cible.get("valide_par_humain"):
            # Une entrée validée n'accepte plus que des ajouts de références et de citations
            # — jamais une réécriture d'attribut. C'est ce que « validée » veut dire.
            _ajouter_citations(cible, entree)
            _ajouter_references(cible, entree)
            continue
        for attribut in ATTRIBUTS:
            if not _rempli(cible["apparence"].get(attribut)):
                cible["apparence"][attribut] = entree["apparence"][attribut]
        for champ in ("genre_confirme", "source_genre"):
            if not _rempli(cible.get(champ)):
                cible[champ] = entree[champ]
        _ajouter_citations(cible, entree)
        _ajouter_references(cible, entree)

    style_base, style_neuf = base["style"], neuve["style"]
    if not _rempli(style_base.get("mots")):
        style_base["mots"] = style_neuf["mots"]
    # La signature est MESURÉE, jamais saisie : une mesure fraîche remplace toujours
    # l'ancienne, sinon un tome enrichi de nouvelles planches garderait une signature
    # calculée sur un échantillon plus pauvre.
    if (style_neuf["signature"] or {}).get("echantillon"):
        style_base["signature"] = style_neuf["signature"]
    connus = {a.get("fichier") for a in style_base["ancrages"]}
    for ancrage in style_neuf["ancrages"]:
        if ancrage.get("fichier") not in connus:
            style_base["ancrages"].append(ancrage)
            connus.add(ancrage.get("fichier"))
    return base


def _ajouter_citations(cible: dict, entree: dict) -> None:
    connues = {(c.get("attribut"), c.get("source"), c.get("texte"))
               for c in cible["citations"]}
    for citation in entree["citations"]:
        cle = (citation.get("attribut"), citation.get("source"), citation.get("texte"))
        if cle not in connues:
            cible["citations"].append(citation)
            connues.add(cle)


def _ajouter_references(cible: dict, entree: dict) -> None:
    index = {r.get("fichier"): r for r in cible["references"]}
    for reference in entree["references"]:
        ancienne = index.get(reference.get("fichier"))
        if ancienne is None:
            cible["references"].append(reference)
            index[reference.get("fichier")] = reference
        elif ancienne.get("confiance") != "humaine":
            ancienne.update({k: v for k, v in reference.items() if k != "confiance"})


# ─────────────────────────────────  Cohérence  ─────────────────────────────────

def verifier_coherence(bible: dict, noms_glossaire, racine_tomes=None) -> list[str]:
    """Les incohérences de la bible, en clair. Liste vide = rien à signaler.

    Quatre familles de contrôle :

    1. **tout `nom` doit exister dans le glossaire** — le glossaire reste la source unique
       des noms, et un nom inventé par un modèle serait le premier pas vers une bible qui
       diverge du texte ;
    2. **toute `references[].fichier` doit exister sur le disque** — un recadrage qui pointe
       vers rien ne se découvrira pas au moment de générer ;
    3. les valeurs énumérées (`genre_confirme`, `source_genre`, `confiance`, `role`) ;
    4. la règle de citation.

    `racine_tomes` est le dossier `build/<Projet>/` ; s'il est `None`, les fichiers ne sont
    pas vérifiés et le dire vaut mieux que de laisser croire qu'ils l'ont été."""
    problemes: list[str] = []
    connus = {str(n) for n in (noms_glossaire or [])}
    for entree in (bible or {}).get("personnages") or []:
        if not isinstance(entree, dict):
            problemes.append("entrée de personnage qui n'est pas un dictionnaire")
            continue
        nom = str(entree.get("nom") or "")
        if not nom:
            problemes.append("personnage sans nom")
        elif connus and nom not in connus:
            problemes.append(f"« {nom} » n'existe pas dans le glossaire — la bible ne crée "
                             f"pas de nom, elle en décrit")
        if str(entree.get("genre_confirme") or "") not in GENRES:
            problemes.append(f"« {nom} » : genre_confirme "
                             f"« {entree.get('genre_confirme')} » hors de {GENRES}")
        if str(entree.get("source_genre") or "") not in SOURCES_GENRE:
            problemes.append(f"« {nom} » : source_genre "
                             f"« {entree.get('source_genre')} » hors de {SOURCES_GENRE}")
        for reference in entree.get("references") or []:
            problemes.extend(_verifier_reference(nom, reference, racine_tomes))
    for nom, attribut in attributs_sans_citation(bible):
        problemes.append(f"« {nom} » : attribut « {attribut} » sans citation — il ne sera "
                         f"pas écrit")
    return problemes


def _verifier_reference(nom: str, reference, racine_tomes) -> list[str]:
    if not isinstance(reference, dict):
        return [f"« {nom} » : référence qui n'est pas un dictionnaire"]
    problemes: list[str] = []
    fichier = str(reference.get("fichier") or "")
    if not fichier:
        problemes.append(f"« {nom} » : référence sans fichier")
    elif racine_tomes is not None and not reference_existe(fichier, racine_tomes):
        problemes.append(f"« {nom} » : référence introuvable sur le disque — {fichier}")
    if str(reference.get("confiance") or "proposee") not in CONFIANCES:
        problemes.append(f"« {nom} » : confiance « {reference.get('confiance')} » "
                         f"hors de {CONFIANCES}")
    role = str(reference.get("role") or "identite")
    if role not in ROLES_REFERENCE:
        problemes.append(f"« {nom} » : rôle « {role} » hors de {ROLES_REFERENCE}")
    # ⚠ Un cadre à moitié valide est SIGNALÉ, jamais corrigé : `illustration/identite.py`
    # le traite comme absent — « un recadrage silencieusement rectifié désignerait une autre
    # partie de l'image que celle qu'un humain a validée ». Le consommateur retombe donc sur
    # la page entière **en silence**, et personne ne saurait que le recadrage validé est
    # perdu. C'est ici que ça se dit.
    brut = cadre_de(reference, defaut=None)
    if brut is not None and not cadre_valide(brut):
        problemes.append(f"« {nom} » : cadre {brut} invalide — quatre fractions "
                         f"[x, y, largeur, hauteur] dans [0, 1], largeur et hauteur "
                         f"strictement positives. La référence sera utilisée EN ENTIER")
    return problemes


#: Nom historique du champ de recadrage, écrit par la passe de propositions du `PLAN-23`
#: (`recadrage: []`) alors que le consommateur du `PLAN-25` lisait `cadre`.
#:
#: ⚠ **Les deux noms ont coexisté de la 2.14.0 à la 2.22.0, et le champ écrit n'était pas
#: celui qui était lu** — relevé le 2026-09-03, lot 29. Aucune donnée n'a été perdue parce que
#: la valeur écrite était toujours la liste vide, mais l'axe « nature du recadrage » du
#: `PLAN-25` L25.1 est resté non mesuré deux lots de suite en partie pour cette raison :
#: personne ne pouvait remplir le champ que le moteur lisait. Le nom canonique est désormais
#: `cadre` (celui du consommateur) et `recadrage` est relu comme un alias.
CADRE_HERITE = "recadrage"


def cadre_de(reference: dict, defaut=()):
    """Le cadre d'une référence, sous l'un ou l'autre de ses deux noms.

    Rend `defaut` quand aucun des deux n'est renseigné — `()` pour un appelant qui veut « la
    page entière », `None` pour celui qui veut distinguer « absent » de « présent et vide »."""
    for cle in ("cadre", CADRE_HERITE):
        valeur = (reference or {}).get(cle)
        if valeur:
            return valeur
    return defaut


def cadre_valide(brut) -> bool:
    """Quatre fractions `[x, y, largeur, hauteur]` dans `[0, 1]`, largeur et hauteur non
    nulles. **La même règle que `illustration/identite.py:_cadre`**, et c'est voulu : deux
    validations différentes du même champ divergent au premier ajout."""
    if not isinstance(brut, (list, tuple)) or len(brut) != 4:
        return False
    try:
        x, y, largeur, hauteur = (float(v) for v in brut)
    except (TypeError, ValueError):
        return False
    return (largeur > 0 and hauteur > 0 and 0.0 <= x < 1.0 and 0.0 <= y < 1.0
            and x + largeur <= 1.0001 and y + hauteur <= 1.0001)


def reference_existe(fichier: str, racine_tomes) -> bool:
    """Une référence est écrite `media/<nom>` : relative au TOME, pas au projet — un projet a
    plusieurs tomes et le même nom de fichier peut vivre dans deux `media/`. On accepte donc
    qu'elle existe sous n'importe quel tome du projet, et le tome exact est porté par le
    `contexte` de la référence.

    ⚠ **C'est LA règle de résolution du dépôt, et il ne doit pas y en avoir deux.** Elle est
    publique depuis le 2026-08-29 : `illustration/requete.py` en avait écrit une seconde, qui
    ne cherchait que sous le tome courant. La bible étant PAR PROJET, ses références couvrent
    plusieurs tomes — sur `roman S`, 7 des 10 références vivent dans le Vol.2 —, et la seconde
    règle déclarait donc introuvables des fichiers présents. Deux règles, c'est une de trop."""
    return bool(chemins_de_reference(fichier, racine_tomes))


def chemins_de_reference(fichier: str, racine_tomes) -> list:
    """**Tous** les chemins auxquels cette référence répond, dans l'ordre des tomes.

    ⚠ Rendre la liste plutôt qu'un booléen est ce qui permet de voir l'AMBIGUÏTÉ. Une
    référence écrite `media/image1.png` sur une œuvre dont deux tomes portent un `image1`
    répond deux fois — et jusqu'au 2026-08-31 le premier gagnait en silence. Sur `roman N`,
    dont les Vol.1 et Vol.2 ont tous deux un `image1`, cela pouvait envoyer au modèle
    d'image le personnage d'un autre volume que celui qu'on croyait.

    La correction est en amont — `tools/bible.py` écrit désormais `<Tome>/media/<nom>` — mais
    les bibles déjà écrites portent l'ancienne forme, et une résolution qui ne sait pas dire
    « j'hésite » ne peut pas les signaler."""
    racine = Path(racine_tomes)
    if not racine.is_dir():
        return []
    relatif = Path(fichier)
    if (racine / relatif).is_file():
        return [racine / relatif]
    return [tome / relatif for tome in sorted(racine.iterdir())
            if tome.is_dir() and (tome / relatif).is_file()]


def noms(bible: dict) -> list[str]:
    return [str(e.get("nom") or "") for e in (bible or {}).get("personnages") or []
            if isinstance(e, dict)]


def entree(bible: dict, nom: str) -> dict | None:
    for e in (bible or {}).get("personnages") or []:
        if isinstance(e, dict) and str(e.get("nom") or "") == nom:
            return e
    return None


# ──────────────────  L29.1 — le compte du corpus, et il s'affiche à chaque revue  ──────────────────

#: Ce que le `PLAN-29` critère 1 demande du corpus d'identité : 8 personnages, dont au moins
#: 4 portant 3 références de rôle `identite` ou plus, **aucune couverture parmi elles**.
#:
#: ⚠ Ces trois nombres viennent du `PLAN-25`, qui les demandait déjà, et le corpus réel en
#: portait **1** au 2026-08-30 (`docs/mesures/prompt-illustration-2026-08-30.md` §11.2). Ils
#: sont écrits ici plutôt que dans l'outil parce que c'est la CIBLE du corpus, pas un réglage
#: d'affichage : un banc, une revue et un rapport doivent tous dire « prêt » au même moment.
CIBLE_PERSONNAGES = 8
CIBLE_AVEC_TROIS = 4
CIBLE_REFERENCES = 3

#: Les tranches publiées par `couverture_identite`, dans l'ordre. `"≥3"` est la seule qui
#: compte pour la cible — au-dessous, `illustration/juge.py` DÉGÉNÈRE (à une référence,
#: ressemblance et nouveauté sont la même mesure) et à deux il n'y a pas de dispersion.
TRANCHES = ("0", "1", "2", "≥3")


def references_identite(entree_personnage: dict, *, validees_seulement: bool = True,
                        sans_couverture: bool = False, classes=None) -> list[dict]:
    """Les références de rôle `identite` d'un personnage.

    `classes` est `{nom de fichier: classe}` — celui de `core/illustrations.py` — et il n'est
    consulté que si `sans_couverture` est vrai. Le passer permet d'appliquer la règle du
    `PLAN-29` (« aucune couverture parmi elles ») **sans** que ce module lise un pixel : il
    lit des champs, c'est sa discipline, et l'appelant sait déjà classer.

    ⚠ `validees_seulement` est le défaut, et c'est la règle du dépôt : « seule `confiance:
    humaine` compte dans la couverture de référence du banc ». Compter les propositions
    ferait passer un corpus non relu pour un corpus prêt."""
    table = dict(classes or {})
    sorties = []
    for brute in (entree_personnage or {}).get("references") or []:
        if not isinstance(brute, dict):
            continue
        if str(brute.get("role") or "identite") != "identite":
            continue
        if validees_seulement and str(brute.get("confiance") or "proposee") != "humaine":
            continue
        if sans_couverture:
            fichier = str(brute.get("fichier") or "")
            if table.get(Path(fichier).name, "") == "couverture":
                continue
        sorties.append(brute)
    return sorties


def couverture_identite(bible: dict, *, sans_couverture: bool = False,
                        classes=None) -> dict:
    """Le tableau 0 / 1 / 2 / ≥3 du `PLAN-29` L29.1, **et le verdict de la cible**.

    Rend `{"tranches": {…}, "par_personnage": {…}, "personnages": n, "avec_trois": n,
    "prêt": bool, "manque": "…"}`.

    ⚠ **Ce compte s'affiche à CHAQUE revue, et c'est délibéré.** Le `PLAN-25` a livré son juge
    étalonné sur un corpus dont **un seul** personnage portait plus d'une référence, et
    personne ne l'a su avant la mesure. Un chiffre qu'on ne voit qu'en fin de lot est un
    chiffre qu'on découvre trop tard : c'est le tableau qui dit quand s'arrêter de recadrer.

    ⚠ `manque` est une PHRASE, pas un booléen. « il manque 5 personnages et 3 qui portent
    trois références » se corrige ; « prêt: false » ne dit pas quoi faire."""
    comptes = {t: 0 for t in TRANCHES}
    par_personnage: dict = {}
    for e in (bible or {}).get("personnages") or []:
        if not isinstance(e, dict):
            continue
        nom = str(e.get("nom") or "")
        if not nom:
            continue
        n = len(references_identite(e, sans_couverture=sans_couverture, classes=classes))
        par_personnage[nom] = n
        comptes[TRANCHES[min(n, 3)]] += 1

    avec_une = sum(1 for n in par_personnage.values() if n >= 1)
    avec_trois = sum(1 for n in par_personnage.values() if n >= CIBLE_REFERENCES)
    manques = []
    if avec_une < CIBLE_PERSONNAGES:
        manques.append(f"{CIBLE_PERSONNAGES - avec_une} personnage(s) à doter d'au moins "
                       f"une référence d'identité")
    if avec_trois < CIBLE_AVEC_TROIS:
        manques.append(f"{CIBLE_AVEC_TROIS - avec_trois} personnage(s) à porter de "
                       f"{CIBLE_REFERENCES} références ou plus")
    return {
        "tranches": comptes,
        "par_personnage": par_personnage,
        "personnages": avec_une,
        "avec_trois": avec_trois,
        "sans_couverture": bool(sans_couverture),
        "pret": not manques,
        "manque": " et ".join(manques) or "la cible du PLAN-29 est atteinte",
    }
