# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**L26.2** — le prompt vient de l'œuvre, et sa charpente est déterministe.

    bible.apparence[attribut] + bible.citations[]   →  les FRAGMENTS, mot pour mot
    glossaire.personnages[].genre                   →  le sujet, accordé
    illustration/gabarits/<nom>.yaml                →  la SYNTAXE : ordre, ponctuation, négatif
    (facultatif) le LLM local                       →  la clause de SCÈNE, et rien d'autre

## La règle qui gouverne ce module, et elle n'a qu'une phrase

**Ce qui n'est pas dans l'œuvre n'entre pas dans le prompt.** C'est la même règle que la
bible visuelle du `PLAN-23` — « un attribut sans `citations[]` n'est pas écrit ici » — et
elle se transmet mécaniquement : un attribut qui n'a pas franchi la porte de la bible ne
peut pas franchir celle-ci, puisque cette fonction ne lit rien d'autre que la bible.

## Les deux moitiés du garde-fou, et il ne faut pas les confondre

Le critère 4 du `PLAN-26` demande qu'« un attribut absent de `bible.yaml` ne puisse pas
entrer dans la requête finale ». Deux mécanismes le tiennent, à deux niveaux de solidité
très différents, et les présenter comme un seul serait un chiffre sans dénominateur :

1. **La charpente — solide par construction.** Les fragments d'apparence sont construits
   depuis `bible.apparence`, filtrés par `bible.citations[]`, et **aucun texte de modèle n'y
   entre**. Il n'existe aucun chemin de code par lequel une chaîne produite par un LLM
   devienne un fragment d'attribut. Ce n'est pas une vérification, c'est une absence de
   branche.
2. **Le filtre de pureté — franchissable, et c'est écrit.** La clause de **scène** (pose,
   geste, expression, lumière) peut, elle, venir du LLM. Elle traverse `epurer`, qui rejette
   **en entier** tout passage contenant un mot du vocabulaire d'apparence du gabarit. ⚠ Une
   périphrase — « une chevelure de blé mûr » — passerait. Le vocabulaire est fermé, donc
   contournable ; le dire vaut mieux que de laisser croire à une garantie universelle. C'est
   la même honnêteté que `illustration/identite.py:TITRE_DANS_LES_PIXELS`.

⚠ **Le rejet est ENTIER, jamais partiel.** Un passage rogné de son mot fautif reste faux :
« ses cheveux blonds volaient » amputé de « cheveux » donne « ses blonds volaient », qui
décrit toujours une couleur que la bible ne porte pas. Le dépôt traite déjà un cadre à
moitié valide comme absent plutôt que corrigé (`identite._cadre`), pour cette raison exacte.

## Pur, et c'est ce qui le rend mesurable

`construire` n'ouvre aucun réseau, ne charge aucun modèle, ne lit aucun fichier hors du
gabarit. Deux appels de mêmes arguments rendent deux requêtes de même empreinte — c'est ce
qui rend le balayage des trois formes de texte (étape 0.3) et du français contre l'anglais
(critère 7) comparables : **une seule variable change à la fois**, parce que tout le reste
est déterministe.

## Ce que ce module ne fait pas

Il ne **choisit pas les images** — c'est `illustration/selection.py` (L26.0), et c'est un
autre métier : celui-là regarde des pixels, celui-ci lit des champs. Il n'appelle pas non
plus le LLM lui-même : il **reçoit** un passage déjà reformulé et le filtre. Un module pur
qui appellerait un réseau ne serait pas pur.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from illustration import gabarits as gabarits_mod
from illustration.moteur import HAUTEUR_DEFAUT, LARGEUR_DEFAUT, Requete

#: Ordre de lecture des attributs. Il suit `core/bible.py` : du plus stable (les cheveux) au
#: plus circonstanciel (la tenue). L'ordre est figé parce qu'il fait partie de la charpente —
#: deux prompts qui ne diffèrent que par l'ordre de leurs fragments ne se comparent pas.
ORDRE = ("age_apparent", "cheveux", "yeux", "tenue", "signes")

#: Cadrage par défaut. Le buste plutôt que le pied : le lot 25 a mesuré que conditionner sur
#: une PAGE ENTIÈRE fait reproduire la composition de la page, et un cadrage large invite le
#: modèle à remplir l'espace — c'est ainsi qu'on obtient un collage. Ce défaut n'est pas une
#: mesure de ce lot : c'est une conséquence raisonnée de celle du lot 25, et le dire évite
#: de le compter deux fois.
CADRAGE_DEFAUT = "buste"

#: Motifs de refus, nommés et comptés — convention du dépôt (`manga/detection_retry.py`).
MOTIFS = {
    "sans_attribut_cite": "aucun attribut d'apparence cité dans la bible — il n'y a rien à "
                          "décrire, et décrire quand même serait inventer",
    "passage_impur": "le passage reformulé décrit un attribut d'apparence ; les attributs "
                     "viennent de la bible, jamais du modèle",
    "genre_inconnu": "ni la bible ni le glossaire ne confirment le genre — le sujet reste "
                     "non accordé, et l'abstention est délibérée",
    "personnage_absent": "ce personnage n'est pas dans la bible visuelle",
}


class PersonnageIndescriptible(RuntimeError):
    """Le personnage n'a aucun attribut cité. **Aucune requête n'est construite.**

    ⚠ Ce n'est pas un cas dégradé qu'on rattraperait par un prompt générique : un portrait
    construit sans attribut serait une invention présentée comme une illustration de
    l'œuvre. C'est le même refus que `identite.SansReferenceValidee`, un cran plus haut."""


# ─────────────────────────────  Ce qui compose un prompt  ─────────────────────────────

@dataclass(frozen=True)
class Fragment:
    """Un morceau du prompt **et d'où il vient**. C'est la traçabilité de `attributs_sources`.

    `source` est un chemin relatif au tome (`chapters/ch03.md`, `media/….jpeg`) : un
    utilisateur qui lit `requete.yaml` doit pouvoir ouvrir le fichier et vérifier en trois
    secondes. Un score, une confiance ou un nom de modèle ne permettraient pas cela."""

    attribut: str
    #: La valeur telle que la bible la porte, mot pour mot. Jamais reformulée.
    valeur: str
    #: La citation : le texte qui l'établit, tel que la bible le porte.
    texte: str = ""
    source: str = ""
    certitude: str = ""
    #: `bible`, `glossaire` ou `humain` — d'où vient ce fragment. Le rapport le montre par
    #: illustration (L26.5) : « d'où vient ce visage ? » doit se répondre sans ouvrir un JSON.
    origine: str = "bible"

    def payload(self) -> dict:
        return {"attribut": self.attribut, "valeur": self.valeur, "texte": self.texte,
                "source": self.source, "certitude": self.certitude, "origine": self.origine}


@dataclass(frozen=True)
class Construction:
    """Le résultat de `construire` : la requête **et de quoi la défendre**.

    ⚠ **Le `PLAN-26` L26.2 écrit `-> Requete`, et on rend davantage.** La raison est dans le
    plan lui-même : `requete.yaml` doit porter `attributs_sources` — « traçabilité : d'où
    vient chaque mot du prompt » — et une `Requete` est **gelée** et n'a pas de place pour
    ça (`moteur.Requete` : « une requête se rejoue, elle ne se retouche pas »). Y ajouter un
    champ de provenance ferait entrer de la documentation dans le payload envoyé au moteur,
    donc dans l'empreinte qui décide de la reproductibilité. La requête est ici, intacte,
    sous `.requete`."""

    requete: Requete
    fragments: tuple = ()
    cadrage: str = CADRAGE_DEFAUT
    #: La variante de décor employée — `PLAN-29` L29.4. `"neutre"` est le défaut, et le lot 29
    #: ne l'a PAS changé : le levier est livré, la mesure qui désignerait un remplaçant n'a
    #: pas pu être faite.
    decor: str = gabarits_mod.DECOR_DEFAUT
    forme: str = "prose"
    langue: str = "fr"
    gabarit: str = gabarits_mod.DEFAUT
    gabarit_version: int = 1
    gabarit_sha256: str = ""
    #: Le sujet retenu et sa source : `('feminin', 'glossaire')`, `('inconnu', '')`.
    genre: tuple = ("inconnu", "")
    #: Motifs nommés de ce qui n'est PAS entré. Une liste vide se lit « rien n'a été écarté ».
    refus: tuple = ()
    #: Le passage reformulé effectivement retenu (vide s'il n'y en avait pas, ou s'il a été
    #: rejeté par `epurer`).
    scene: str = ""

    def attributs_sources(self) -> list[dict]:
        """Ce qui part dans `requete.yaml` sous `attributs_sources`."""
        return [f.payload() for f in self.fragments]


# ────────────────────────────────  La construction  ────────────────────────────────

def construire(personnage: str, bible_doc: dict, glossaire: dict | None = None, *,
               cadrage: str = CADRAGE_DEFAUT, decor: str = gabarits_mod.DECOR_DEFAUT,
               passage: str | None = None,
               style: str | None = None, forme: str = "prose", langue: str = "fr",
               gabarit: str = gabarits_mod.DEFAUT, nombre_references: int = 0,
               nombre_ancrages: int = 0,
               largeur: int = LARGEUR_DEFAUT, hauteur: int = HAUTEUR_DEFAUT,
               graine: int = 0, pas: int = 4, guidage: float = 1.0,
               modele: str = "") -> Construction:
    """La requête d'un personnage, **sans LLM, sans moteur, sans réseau**.

    `passage` est une clause de scène DÉJÀ reformulée par l'appelant (le LLM, s'il y en a
    un) ; elle traverse `epurer` et disparaît si elle décrit un attribut. `style` est la
    phrase de registre graphique — `bible.style.mots` ou ce que l'étape 0.2 a retenu.

    Lève `PersonnageIndescriptible` quand la bible ne cite aucun attribut : c'est le refus,
    et il n'a pas de mode « au mieux »."""
    gab = gabarits_mod.charger(gabarit, langue=langue)
    if forme not in gabarits_mod.FORMES:
        raise ValueError(
            f"forme de champ texte « {forme} » inconnue. Trois formes, et laquelle gagne est "
            f"une MESURE de ce dépôt sur son corpus, pas un héritage : "
            f"{', '.join(gabarits_mod.FORMES)}.")

    entree = _entree(bible_doc, personnage)
    if entree is None:
        raise PersonnageIndescriptible(
            f"« {personnage} » : {MOTIFS['personnage_absent']}.\n"
            f"  → python tools/bible.py --construire, puis --revue.")

    fragments, refus = _fragments(entree)
    if not fragments:
        raise PersonnageIndescriptible(
            f"« {personnage} » : {MOTIFS['sans_attribut_cite']}.\n"
            f"  La bible le déclare mais ne cite aucun de ses cinq attributs d'apparence. "
            f"Un portrait construit là-dessus ne viendrait pas de l'œuvre.\n"
            f"  → python tools/bible.py --revue")

    genre, origine_genre = _genre(entree, glossaire, personnage)
    if not origine_genre:
        refus.append("genre_inconnu")

    scene, refus_scene = epurer(passage or "", gab)
    refus.extend(refus_scene)

    texte = assembler(gab, forme=forme, genre=genre, cadrage=cadrage, decor=decor,
                      fragments=fragments, style=style or "", scene=scene,
                      nombre_references=nombre_references,
                      nombre_ancrages=nombre_ancrages)
    requete = Requete(
        prompt=texte, prompt_negatif=gab.prompt_negatif(),
        largeur=int(largeur), hauteur=int(hauteur), graine=int(graine),
        pas=int(pas), guidage=float(guidage), modele=modele)
    return Construction(
        requete=requete, fragments=tuple(fragments), cadrage=cadrage, decor=decor,
        forme=forme,
        langue=langue, gabarit=gab.nom, gabarit_version=gab.version,
        gabarit_sha256=gabarits_mod.empreinte(gab.nom), genre=(genre, origine_genre),
        refus=tuple(dict.fromkeys(refus)), scene=scene)


def assembler(gab, *, forme: str, genre: str, cadrage: str, fragments,
              decor: str = gabarits_mod.DECOR_DEFAUT,
              style: str = "", scene: str = "", nombre_references: int = 0,
              nombre_ancrages: int = 0) -> str:
    """Le champ texte, dans l'une des trois formes de l'étape 0.3.

    ⚠ **Le CONTENU est rigoureusement le même dans les trois** — mêmes fragments, même
    ordre, même sujet, même cadrage. Seule la mise en forme change. C'est la condition pour
    que la mesure porte sur la forme et non sur ce qu'on a dit : un balayage où la variante
    « catégories » aurait aussi gagné un adjectif ne mesurerait rien."""
    sujet = gab.sujet(genre)
    cadre = gab.cadrage(cadrage)
    phrase_decor = gab.decor_de(decor)
    apparence = [gab.attributs.get(f.attribut, "{}").format(f.valeur) for f in fragments]
    # ⚠ Les ancres suivent les références dans le canal, et sont désignées SÉPARÉMENT :
    # deux usages du même canal, distingués par le texte parce que le canal ne les distingue
    # pas (`PLAN-26` L26.0, règle 0).
    designation = " ".join(d for d in (
        gab.designation(int(nombre_references)),
        gab.designation_ancrages(int(nombre_references) + 1, int(nombre_ancrages))) if d)
    if forme == "prose":
        return _prose(sujet, cadre, apparence, phrase_decor, style, scene, designation)
    if forme == "categories":
        return _categories(gab, sujet, cadre, apparence, phrase_decor, style, scene,
                           designation)
    return _json(gab, sujet, cadre, apparence, phrase_decor, style, scene, designation)


def _prose(sujet: str, cadre: str, apparence: list, decor: str, style: str, scene: str,
           designation: str) -> str:
    """Une phrase suivie. C'est la forme que la discussion amont de `Qwen-Image-Edit-2511`
    recommande (« il utilise un LLM comme CLIP, parlez-lui en langage naturel »).

    ⚠ **Chaque fragment est CLOS avant le suivant**, et ce n'est pas de la coquetterie : sans
    cela, « larges aplats uniformes Le personnage est celui de l'image 1 » soude deux phrases
    en une, et le champ texte part dans un encodeur qui est lui-même un modèle de langue.
    Défaut trouvé le 2026-08-30 en relisant un prompt réel, corrigé avant la livraison."""
    tete = ", ".join(p for p in (f"{sujet}, {cadre}" if cadre else sujet, decor) if p)
    morceaux = [tete, ", ".join(apparence), scene, style, designation]
    return " ".join(_clore(m) for m in morceaux if m and m.strip()).strip()


def _clore(fragment: str) -> str:
    """Termine un fragment par un point s'il n'a pas déjà sa ponctuation finale."""
    fragment = fragment.strip()
    return fragment if fragment.endswith((".", "!", "?", ":", ";")) else f"{fragment}."


def _categories(gab, sujet: str, cadre: str, apparence: list, decor: str, style: str,
                scene: str, designation: str) -> str:
    """Des catégories étiquetées, une par ligne. C'est la forme qu'un guide communautaire de
    `Qwen-Image-2512` recommande, avec un « +30 % de précision » que ce dépôt **ne recopie
    nulle part comme un fait** : c'est l'affirmation d'un article de blog, sans corpus ni
    dénominateur, et la règle des chiffres du dépôt s'applique aux affirmations d'autrui
    comme aux siennes."""
    eti = gab.etiquettes
    lignes = [(eti.get("sujet", "Sujet"), sujet), (eti.get("cadrage", "Cadrage"), cadre),
              (eti.get("apparence", "Apparence"), ", ".join(apparence)),
              (eti.get("decor", "Décor"), decor),
              (eti.get("scene", "Scène"), scene.strip()),
              (eti.get("style", "Style"), style.strip())]
    corps = "\n".join(f"{cle}: {valeur}" for cle, valeur in lignes if valeur)
    return f"{corps}\n{designation}".strip() if designation else corps


def _json(gab, sujet: str, cadre: str, apparence: list, decor: str, style: str, scene: str,
          designation: str) -> str:
    """Le même contenu sérialisé en JSON **dans le champ texte**.

    ⚠ Ce n'est pas gratuit et il faut le dire avant de mesurer : accolades, guillemets et
    clés consomment des jetons du budget de l'encodeur sans porter de structure que le
    modèle sache lire — l'encodeur est un LLM de vision-langage, pas un parseur. S'il gagne
    quand même, c'est un résultat surprenant qui mérite d'être publié comme tel."""
    eti = gab.etiquettes
    corps = {eti.get("sujet", "Sujet"): sujet, eti.get("cadrage", "Cadrage"): cadre,
             eti.get("apparence", "Apparence"): apparence}
    # ⚠ La variante de décor `aucun` rend une phrase VIDE, et une clé « Décor »: "" ne veut
    # pas dire « pas de décor » — elle dit au modèle qu'on a pensé au décor et qu'on n'a rien
    # à en dire. Les trois formes doivent porter le même contenu (cf. `assembler`) : la prose
    # et les catégories laissent déjà tomber un fragment vide, le JSON aussi.
    if decor:
        corps[eti.get("decor", "Décor")] = decor
    if scene.strip():
        corps[eti.get("scene", "Scène")] = scene.strip()
    if style.strip():
        corps[eti.get("style", "Style")] = style.strip()
    rendu = json.dumps(corps, ensure_ascii=False, indent=None, separators=(", ", ": "))
    return f"{rendu} {designation}".strip() if designation else rendu


# ────────────────────────────  Les fragments, depuis la bible  ────────────────────────────

def _entree(bible_doc: dict, nom: str) -> dict | None:
    """L'entrée d'un personnage. Passe par `core.bible` — **la** règle du dépôt, pas une
    seconde écrite ici (le lot 25 a déjà payé ce défaut sur la résolution des références)."""
    from core import bible as bible_mod
    return bible_mod.entree(bible_doc or {}, nom)


def _fragments(entree: dict) -> tuple[list, list]:
    """Les fragments d'apparence CITÉS, dans l'ordre de `ORDRE`, et les motifs des écarts.

    ⚠ Un attribut renseigné mais **non cité** est écarté. La bible a déjà purgé ce cas à
    l'écriture (`core/bible.py`), donc en pratique la liste est vide ; le contrôle reste
    parce que `bible.yaml` s'édite à la main et que l'invariant ne doit pas dépendre d'un
    raisonnement — c'est la doctrine de `manga/clean.py`, dont le `paint &= region.mask` est
    gardé « même quand il est redondant en théorie »."""
    apparence = entree.get("apparence") or {}
    par_attribut = _citations(entree)
    fragments, refus = [], []
    for attribut in ORDRE:
        valeur = _texte(apparence.get(attribut))
        if not valeur:
            continue
        citations = par_attribut.get(attribut) or []
        if not citations:
            refus.append("sans_attribut_cite")
            continue
        premiere = citations[0]
        fragments.append(Fragment(
            attribut=attribut, valeur=valeur,
            texte=str(premiere.get("texte") or ""),
            source=str(premiere.get("source") or ""),
            certitude=str(premiere.get("certitude") or ""),
            origine="bible"))
    return fragments, refus


def _citations(entree: dict) -> dict:
    """`{attribut: [citation…]}`, dans l'ordre du fichier."""
    table: dict = {}
    for citation in entree.get("citations") or []:
        if not isinstance(citation, dict):
            continue
        table.setdefault(str(citation.get("attribut") or ""), []).append(citation)
    return table


def _texte(valeur) -> str:
    if isinstance(valeur, (list, tuple)):
        return ", ".join(str(v).strip() for v in valeur if str(v).strip())
    return str(valeur or "").strip()


# ──────────────────────────────────  Le genre  ──────────────────────────────────

def _genre(entree: dict, glossaire: dict | None, personnage: str) -> tuple[str, str]:
    """Le genre et **sa source**, ou `("inconnu", "")`.

    Deux sources, dans cet ordre, et l'ordre a une raison :

    1. `bible.genre_confirme` — confirmé **sur une illustration**, donc sur ce que le
       modèle d'image va devoir rendre ;
    2. `glossaire.personnages[].genre` — établi sur le TEXTE, et déjà relu : c'est lui qui
       commande les accords de toute la traduction (`core/glossary.py` étiquette la
       catégorie « Personnages (**le genre commande les accords**) »).

    ⚠ **Le second n'est pas un repli au rabais, et c'est un résultat de ce lot.** Sur le
    corpus réel, `bible.genre_confirme` vaut `''` sur **11 personnages sur 11**, tandis que
    le glossaire le porte pour **9 sur 11**. Un champ que la bible ne remplit jamais et qu'un
    autre fichier du même dépôt porte déjà n'est pas une donnée manquante : c'est une donnée
    qu'on n'allait pas chercher. Le lot 25 en avait la trace à l'œil — « Gale », sans genre,
    est sorti en femme.

    ⚠ **L'abstention reste le défaut.** `core/bible.py` note qu'« une valeur fausse ici coûte
    plus qu'une valeur absente » : un `'?'` de glossaire ne devient pas un genre."""
    confirme = str((entree or {}).get("genre_confirme") or "").strip()
    if confirme in ("feminin", "féminin", "masculin"):
        return _normaliser_genre(confirme), "bible"
    for categorie in ("personnages",):
        for candidat in ((glossaire or {}).get(categorie) or []):
            if not isinstance(candidat, dict):
                continue
            if str(candidat.get("nom") or "").strip() != str(personnage).strip():
                continue
            genre = str(candidat.get("genre") or "").strip()
            if genre in ("feminin", "féminin", "masculin"):
                return _normaliser_genre(genre), "glossaire"
    return "inconnu", ""


def _normaliser_genre(valeur: str) -> str:
    """`féminin` et `feminin` désignent la même chose : le glossaire écrit l'accent, le
    gabarit ne le porte pas dans ses clés."""
    return "feminin" if valeur.startswith("f") else "masculin"


# ──────────────────────  Le filtre de pureté de la clause de scène  ──────────────────────

def epurer(passage: str, gab) -> tuple[str, list]:
    """Rend `(clause retenue, motifs)`. Une clause impure est rejetée **en entier**.

    ⚠ Lire la docstring du module avant d'y toucher : ce filtre protège la clause de scène,
    **pas** les attributs — ceux-là sont protégés par l'absence de branche, ce qui est plus
    fort. Le filtre est un vocabulaire fermé, donc franchissable par périphrase, et c'est
    écrit dans le gabarit à côté de la liste."""
    clause = " ".join(str(passage or "").split())
    if not clause:
        return "", []
    if mots_interdits(clause, gab):
        return "", ["passage_impur"]
    return clause, []


def mots_interdits(passage: str, gab) -> list:
    """Les mots d'apparence trouvés dans un passage. Sert au diagnostic et aux tests : dire
    « rejeté » sans dire **quel mot** obligerait à relire la liste à la main.

    ⚠ **La correspondance est à la FRONTIÈRE DE MOT, jamais en sous-chaîne**, et le défaut
    qui l'a imposé mérite d'être écrit : une recherche en sous-chaîne trouvait « ans » dans
    « pansement » et rejetait « elle presse un pansement à deux mains », qui ne décrit aucun
    attribut. Un filtre qui jette les bonnes clauses aussi souvent que les mauvaises se fait
    désarmer, et un garde-fou désarmé ne garde rien.

    ⚠ **Les accents sont normalisés des deux côtés.** « meche » et « mèche » désignent la
    même chose, et un modèle qui écrit sans accent ne doit pas passer pour cette raison. Le
    dépôt a déjà ce geste dans `core/bible_llm.py:_sans_accent`.

    ⚠ **Le suffixe toléré est `s`, `e`, `es` — pas un préfixe libre.** « blond » attrape
    « blonds » et « blonde » ; il n'attrape pas « blondir », et surtout « age » n'attrape pas
    « agenouillée ». Un filtre par préfixe rejetterait la moitié des poses du corpus."""
    plie = _sans_accent(" ".join(str(passage or "").split()))
    return [mot for mot in gab.mots_attribut
            if _motif_de_mot(_sans_accent(mot)).search(plie)]


def _sans_accent(texte: str) -> str:
    """Minuscules, sans diacritique. Même geste que `core/bible_llm.py:_sans_accent`."""
    import unicodedata

    plie = unicodedata.normalize("NFD", str(texte or "").casefold())
    return "".join(c for c in plie if unicodedata.category(c) != "Mn")


#: Les expressions de mot sont compilées une fois : `mots_interdits` est appelée par
#: personnage, et le vocabulaire fait une quarantaine d'entrées par langue.
_MOTIFS_MOT: dict = {}


def _motif_de_mot(mot: str):
    if mot not in _MOTIFS_MOT:
        _MOTIFS_MOT[mot] = re.compile(rf"\b{re.escape(mot)}(?:es|s|e)?\b")
    return _MOTIFS_MOT[mot]


# ──────────────  Étape 0.2, approche 1 — la signature mesurée, mise en mots  ──────────────

#: Seuils qui traduisent un descripteur mesuré en un mot du gabarit.
#:
#: ⚠ **Le descripteur est MESURÉ, le seuil ne l'est pas.** Il est posé en tiers de l'échelle
#: [0, 1] et écrit ici pour qu'on puisse le contester. Publier « palette désaturée » comme s'il
#: s'agissait d'une mesure serait exactement la faute que `docs/chiffres-de-reference.md`
#: interdit ; ce qui se mesure, c'est **l'effet de la phrase sur l'image produite**, et c'est
#: ce que l'étape 0.2 juge.
SEUILS_REGISTRE = {
    "saturation_basse": 0.15,
    "saturation_haute": 0.40,
    "trait_dense": 0.20,
    "trait_fin": 0.10,
    "aplats_dominants": 0.35,
    "contraste_fort": 0.30,
}


def mots_de_signature(signature: dict, gab) -> str:
    """La signature mesurée du tome, traduite en mots — l'**approche 1** de l'étape 0.2.

    `bible.style.signature` porte cinq nombres mesurés par `core/illustrations.py` sur les
    illustrations du tome : saturation moyenne, contraste, densité de trait, part d'aplats, et
    le régime de couleur. Cette fonction les rend dicibles à un modèle d'image.

    ⚠ **Le régime de couleur est le premier mot, et ce n'est pas un hasard.** Le lot 25 a
    mesuré que c'est le seul descripteur que le conditionnement par référence ne corrige pas :
    « les générations sont en couleur, le tome est en noir et blanc, et cinq images de plus
    n'y changeront rien ». Si les mots servent à quelque chose, c'est là qu'on le verra.

    ⚠ **Ne pas confondre avec `bible.style.mots`**, qui est écrit à la main. Les deux se
    complètent : l'un porte ce qu'un humain a voulu dire du tome, l'autre ce que l'outil du
    lot 23 y a mesuré. `depuis_oeuvre` les concatène, l'humain en premier."""
    if not signature:
        return ""
    registre = getattr(gab, "registre", {}) or {}
    mots = []
    couleur = signature.get("couleur")
    if couleur is not None:
        mots.append(registre.get("couleur_oui" if couleur else "couleur_non", ""))
    mots.append(_seuil(signature.get("saturation_moyenne"), registre,
                       bas=("saturation_basse", SEUILS_REGISTRE["saturation_basse"]),
                       haut=("saturation_haute", SEUILS_REGISTRE["saturation_haute"])))
    mots.append(_seuil(signature.get("densite_trait"), registre,
                       bas=("trait_fin", SEUILS_REGISTRE["trait_fin"]),
                       haut=("trait_dense", SEUILS_REGISTRE["trait_dense"])))
    if _au_dessus(signature.get("part_aplats"), SEUILS_REGISTRE["aplats_dominants"]):
        mots.append(registre.get("aplats_dominants", ""))
    if _au_dessus(signature.get("contraste"), SEUILS_REGISTRE["contraste_fort"]):
        mots.append(registre.get("contraste_fort", ""))
    return ", ".join(m for m in mots if m)


def _seuil(valeur, registre: dict, *, bas: tuple, haut: tuple) -> str:
    """Le mot du bas, celui du haut, ou rien. Un descripteur au milieu ne dit rien de
    caractéristique du tome : lui coller un mot quand même remplirait le prompt de bruit."""
    if valeur is None:
        return ""
    if float(valeur) <= bas[1]:
        return registre.get(bas[0], "")
    if float(valeur) >= haut[1]:
        return registre.get(haut[0], "")
    return ""


def _au_dessus(valeur, seuil: float) -> bool:
    return valeur is not None and float(valeur) >= seuil


# ────────────────────────────────  Le budget (L26.4)  ────────────────────────────────

@dataclass
class Budget:
    """Le plafond d'un run. Le dépôt a une culture du plafond, et elle a une raison : un tome
    fait vingt illustrations, pas une.

    ⚠ **`images` est bas par défaut (8) et le motif d'arrêt est NOMMÉ.** Un plafond qui
    s'atteint en silence ferait croire à un corpus plus petit qu'il n'est ; le rapport et le
    journal disent « plafond atteint », pas « 8 images »."""

    images: int = 8
    #: Plafond de jetons du passage envoyé au LLM. 0 = celui de `decoupage.max_input_tokens`.
    #: ⚠ **On DÉCOUPE, on ne tronque pas silencieusement** : un chapitre entier ne passe pas
    #: dans 24 000 jetons, et une troncature muette ferait décrire une scène à partir d'un
    #: texte amputé sans que personne le sache.
    tokens_passage: int = 0
    atteints: list = field(default_factory=list)

    def retenir(self, noms) -> list:
        """Les `images` premiers noms, et le motif d'arrêt si le plafond mord."""
        noms = list(noms)
        if len(noms) <= self.images:
            return noms
        self.atteints.append(
            f"plafond d'images atteint : {len(noms)} candidates, {self.images} retenues "
            f"(illustration.budget.images_par_run)")
        return noms[:self.images]


def empreinte_gabarit(nom: str = gabarits_mod.DEFAUT) -> str:
    """Réexport — le sidecar de provenance en a besoin et n'a pas à connaître le paquet des
    gabarits (L26.3 : « gabarit et sa version »)."""
    return gabarits_mod.empreinte(nom)


def chemin_gabarit(nom: str = gabarits_mod.DEFAUT) -> Path:
    return gabarits_mod.racine() / f"{nom}.yaml"
