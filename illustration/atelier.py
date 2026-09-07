# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**Une commande, une question à la fois** — de quoi l'atelier console a besoin pour décider.

    qui est illustrable dans cette œuvre ?   →  `catalogue`
    quelles images lui montrer ?             →  `candidates` (+ le motif de chacune)
    et si je veux autre chose ?              →  `bloc_libre`
    l'humain a regardé et tranché            →  `selection_humaine`, `promouvoir`

## Pourquoi ce module est SANS `rich` et sans `input()`

Règle de couche du dépôt (`gui/__init__.py`, transposée) : « toute logique métier vit dans le
module, en Python nu, et se teste avec `pytest` ». Ici on ne trouve donc **aucune** question
posée à l'écran — seulement ce qu'il faut savoir pour la poser. Les questions vivent dans
`run_illustration.py`, qui est la façade.

C'est ce qui rend le catalogue testable sans console, sans serveur et sans modèle.

## Ce que « illustrable » veut dire, et pourquoi il y a trois états et non deux

Un personnage n'est pas « bon » ou « mauvais » : il est **prêt**, **à relire**, ou **hors
d'atteinte**, et la différence commande ce que l'atelier propose.

| état | ce qu'il a | ce que l'atelier en fait |
|---|---|---|
| `pret` | au moins un attribut CITÉ **et** une référence `confiance: humaine` | proposé en premier, il part directement en génération |
| `a_relire` | des attributs cités **et** des références proposées par le déterministe ou par un modèle, aucune validée | proposé aussi, mais **l'humain doit regarder les images** avant |
| `hors_atteinte` | pas d'attribut cité, ou aucune image candidate | **pas proposé**, avec le motif — c'est un diagnostic de la bible, pas un échec de l'atelier |

⚠ **`a_relire` est le cas MAJORITAIRE d'une œuvre neuve**, et c'est le sens même de cet
atelier. Avant lui, la revue humaine se faisait dans `tools/bible.py --revue`, hors contexte :
on validait des références sans savoir pour quelle image. Ici, l'humain valide **au moment où
il demande le portrait**, en voyant ce que le modèle de vision a dit de chaque candidate. La
validation reste une validation humaine — c'est la même personne, le même œil, mieux informé.

⚠ **Et elle se persiste, si l'humain le veut.** `promouvoir` réécrit `bible.yaml` avec
`confiance: humaine` sur les images retenues. C'est un geste EXPLICITE, jamais un effet de
bord : une bible modifiée sans qu'on l'ait demandé serait une revue humaine fabriquée.

## Le choix personnalisé n'est pas une échappatoire

`bloc_libre` construit une requête à partir d'une description écrite par l'humain. Elle ne
passe **pas** par la bible, donc la garantie du critère 4 du `PLAN-26` — « un attribut absent
de `bible.yaml` ne peut pas entrer » — n'y a pas d'objet : il n'y a pas de bible à trahir,
c'est l'humain qui écrit. Ce qui compte alors est la **traçabilité**, et elle est plus stricte
que d'habitude : `attributs_sources` porte une entrée unique `origine: humain`, et le sidecar
de l'image la recopie. Un lecteur du sidecar doit pouvoir distinguer, sans ambiguïté, une
image dont chaque mot vient de l'œuvre d'une image dont les mots viennent de son auteur.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from illustration import prompt as prompt_mod
from illustration import selection as selection_mod

#: Les trois états, dans l'ordre où l'atelier les présente.
PRET = "pret"
A_RELIRE = "a_relire"
HORS_ATTEINTE = "hors_atteinte"

MOTIFS = {
    "sans_attribut_cite": "aucun attribut d'apparence cité dans la bible",
    "sans_image": "aucune illustration candidate dans l'œuvre",
    "sans_validee": "aucune référence validée par un humain — à relire avant de générer",
}


@dataclass
class Fiche:
    """Ce que l'atelier sait d'un personnage avant de proposer quoi que ce soit."""

    nom: str
    etat: str
    attributs: tuple = ()
    #: `[Candidate]` — toutes les images candidates, validées ou non.
    candidates: list = field(default_factory=list)
    validees: int = 0
    genre: str = ""
    origine_genre: str = ""
    motifs: tuple = ()
    #: `bible` ou `propositions` — d'OÙ vient cette fiche.
    #:
    #: ⚠ La distinction commande ce que l'atelier fait ensuite. Une fiche venue des
    #: PROPOSITIONS n'a été relue par personne : ni ses attributs, ni ses images. L'atelier
    #: doit donc faire relire les deux avant de générer, et il ne peut pas construire son
    #: prompt tant que `bible.yaml` ne porte pas le personnage.
    source: str = "bible"
    #: L'entrée telle qu'elle est écrite, pour pouvoir la promouvoir sans la relire.
    entree: dict = field(default_factory=dict)

    @property
    def illustrable(self) -> bool:
        return self.etat in (PRET, A_RELIRE)

    def resume(self) -> str:
        """Une ligne pour l'écran : ce qu'on a, pas un jugement."""
        attributs = ", ".join(self.attributs) or "aucun attribut cité"
        images = (f"{self.validees} validée(s) / {len(self.candidates)} candidate(s)"
                  if self.candidates else "aucune image")
        genre = f"{self.genre} ({self.origine_genre})" if self.origine_genre else "genre inconnu"
        return f"{attributs} · {images} · {genre}"


def catalogue(bible_doc: dict, glossaire: dict | None, racine_projet,
              propositions: dict | None = None) -> list:
    """Une `Fiche` par personnage de la bible, **les plus prêts d'abord**.

    ⚠ L'ordre est `pret`, puis `a_relire`, puis — seulement si l'appelant les demande — les
    `hors_atteinte`. À l'intérieur d'un état, on classe par nombre de références validées puis
    par nombre d'attributs cités : le personnage le mieux documenté est celui qui donnera la
    meilleure image, et c'est celui qu'on propose en premier.

    ⚠ **Aucun modèle n'est appelé ici.** Le catalogue se calcule en lisant des champs et en
    listant des fichiers ; c'est ce qui permet de l'afficher instantanément au démarrage de
    l'atelier, avant que l'utilisateur ait choisi quoi que ce soit."""
    fiches, vus = [], set()
    for entree in (bible_doc or {}).get("personnages") or []:
        if not isinstance(entree, dict):
            continue
        nom = str(entree.get("nom") or "").strip()
        if not nom:
            continue
        vus.add(nom)
        fiches.append(fiche(nom, entree, bible_doc, glossaire, racine_projet))
    # ⚠ **Les propositions comptent, et c'est la raison d'être de cet atelier.** Une œuvre
    # neuve n'a PAS de `bible.yaml` : `tools/bible.py --proposer` a écrit
    # `bible.propositions.yaml`, et la revue humaine n'a pas encore eu lieu. Un catalogue qui
    # ne lirait que la bible validée ne proposerait rien du tout sur ce qui est le cas normal.
    for entree in (propositions or {}).get("personnages") or []:
        if not isinstance(entree, dict):
            continue
        nom = str(entree.get("nom") or "").strip()
        if not nom or nom in vus:
            continue
        vus.add(nom)
        f = fiche(nom, entree, propositions, glossaire, racine_projet)
        # Une proposition n'a été relue par personne : elle ne peut pas être « prête ».
        fiches.append(replace(f, source="propositions",
                              etat=A_RELIRE if f.illustrable else f.etat))
    rang = {PRET: 0, A_RELIRE: 1, HORS_ATTEINTE: 2}
    return sorted(fiches, key=lambda f: (rang[f.etat], -f.validees, -len(f.attributs), f.nom))


def fiche(nom: str, entree: dict, bible_doc: dict, glossaire: dict | None,
          racine_projet) -> Fiche:
    """L'état d'un personnage, avec le motif de ce qui lui manque."""
    fragments, _ = prompt_mod._fragments(entree)
    attributs = tuple(f.attribut for f in fragments)
    candidates = selection_mod.candidates_identite(bible_doc, nom, racine_projet)
    validees = sum(1 for c in candidates if c.validee)
    genre, origine = prompt_mod._genre(entree, glossaire, nom)

    motifs = []
    if not attributs:
        motifs.append("sans_attribut_cite")
    if not candidates:
        motifs.append("sans_image")
    if candidates and not validees:
        motifs.append("sans_validee")

    if not attributs or not candidates:
        etat = HORS_ATTEINTE
    elif validees:
        etat = PRET
    else:
        etat = A_RELIRE
    return Fiche(nom=nom, etat=etat, attributs=attributs, candidates=candidates,
                 validees=validees, genre=genre, origine_genre=origine,
                 motifs=tuple(motifs), entree=entree)


def selection_humaine(choisies, candidates, *, usage: str = selection_mod.USAGE_IDENTITE,
                      motifs_du_modele: dict | None = None) -> list:
    """Ce que l'humain a retenu à l'écran, mis à la forme de `requete.yaml`.

    `choisies` est l'ensemble des `fichier` retenus. **Toutes** les candidates ressortent —
    retenues comme écartées — parce que la règle 3 du `PLAN-26` L26.0 l'exige : « un
    utilisateur qui retire une image doit voir pourquoi elle avait été prise ».

    ⚠ Le motif d'une image retenue par l'humain dit **qui a décidé**, et c'est la seule chose
    honnête à écrire : personne d'autre ne sait ce qu'il a vu. Quand un modèle de vision a
    donné son avis, il est repris à côté — les deux tiennent dans la même ligne, et le lecteur
    voit s'ils étaient d'accord."""
    motifs_du_modele = motifs_du_modele or {}
    retenus = {str(f) for f in (choisies or ())}
    sortie = []
    for candidate in candidates:
        avis = motifs_du_modele.get(candidate.fichier, "")
        if candidate.fichier in retenus:
            motif = "retenue à l'écran par l'humain"
            if avis:
                motif += f" · le modèle de vision disait : {avis}"
        else:
            motif = avis or "écartée à l'écran par l'humain"
        sortie.append(selection_mod.Choix(
            fichier=candidate.fichier, motif=motif,
            retenue=candidate.fichier in retenus, usage=usage, par="humain"))
    return sortie


def attributs_cites(entree: dict) -> list:
    """`[(attribut, valeur, citations)]` — ce qu'on montre à l'humain avant d'écrire.

    ⚠ **Chaque attribut vient avec SES citations, et c'est le point.** Le dépôt tient que « un
    attribut sans sa source n'est pas une observation » ; un écran de revue qui montrerait les
    valeurs sans les phrases demanderait de faire confiance, pas de vérifier."""
    par_attribut: dict = {}
    for citation in entree.get("citations") or []:
        if isinstance(citation, dict):
            par_attribut.setdefault(str(citation.get("attribut") or ""), []).append(citation)
    sortie = []
    for attribut in prompt_mod.ORDRE:
        valeur = prompt_mod._texte((entree.get("apparence") or {}).get(attribut))
        if valeur and par_attribut.get(attribut):
            sortie.append((attribut, valeur, par_attribut[attribut]))
    return sortie


def entree_filtree(entree: dict, attributs) -> dict:
    """L'entrée réduite aux attributs que l'humain a retenus, **citations comprises**.

    ⚠ **Une revue en bloc est trop grossière, et la mesure l'a montré.** Sur le premier
    personnage relu de l'œuvre `roman N`, la passe automatique proposait cinq attributs dont
    **trois faux** : des cheveux « bleu céleste » là où le dessin les montre verts (la phrase
    citée décrit un autre personnage), un âge « environ deux ans » pour une adolescente, et un
    « masque blanc » tiré d'une phrase qui décrit **les passants de la rue**, pas elle. Un
    « ces attributs sont-ils bons ? o/n » n'aurait laissé que deux issues : tout accepter, donc
    écrire trois erreurs dans la bible, ou tout refuser, donc perdre les deux bons.

    C'est la granularité qu'a déjà `tools/bible.py --revue`, et il n'y avait pas de raison de
    la perdre en la rapprochant du moment où elle sert."""
    from core import bible as bible_mod

    gardes = {str(a) for a in (attributs or ())}
    copie = bible_mod.personnage(str(entree.get("nom") or ""))
    copie["genre_confirme"] = str(entree.get("genre_confirme") or "")
    copie["source_genre"] = str(entree.get("source_genre") or "")
    for attribut in bible_mod.ATTRIBUTS:
        if attribut in gardes:
            copie["apparence"][attribut] = (entree.get("apparence") or {}).get(attribut)
    copie["citations"] = [c for c in (entree.get("citations") or [])
                          if isinstance(c, dict) and str(c.get("attribut") or "") in gardes]
    copie["references"] = list(entree.get("references") or [])
    return copie


def promouvoir(bible_doc: dict, nom: str, fichiers, entree=None) -> tuple[dict, int]:
    """Passe à `confiance: humaine` les références que l'humain vient de valider.

    Rend `(bible modifiée, nombre de références promues)`. **N'écrit rien sur le disque** :
    l'appelant décide, et il le demande explicitement à l'utilisateur avant.

    ⚠ **C'est une revue humaine, pas un raccourci.** `core/bible.py` range les confiances en
    `proposee` / `llm` / `humaine` et note que « seule la dernière compte » ; l'écrire depuis
    l'atelier n'affaiblit rien, parce que la personne qui coche est la même que celle qui
    l'aurait cochée dans `tools/bible.py --revue` — mais elle a sous les yeux l'image ET
    l'usage qu'on va en faire, ce que la revue hors contexte ne montrait pas.

    ⚠ **`valide_par_humain` n'est levé QUE pour un personnage qu'on fait entrer depuis les
    propositions**, et seulement parce que l'atelier a alors montré ses attributs et leurs
    citations à l'écran avant de demander. Pour un personnage DÉJÀ dans la bible, il n'est pas
    touché : il porte sur les attributs, que l'atelier ne relit pas dans ce cas, et le lever
    ferait passer pour relus des attributs que personne n'a regardés."""
    from core import bible as bible_mod

    voulus = {str(f) for f in (fichiers or ())}
    if not voulus:
        return bible_doc, 0
    copie = bible_mod.fill_defaults(bible_doc)
    # ⚠ **Un personnage venu des PROPOSITIONS n'existe pas encore dans la bible.** Le
    # promouvoir, c'est l'y faire entrer avec ses attributs ET leurs citations — la règle de
    # citation de `core/bible.py` s'applique alors comme partout : `save` purge tout attribut
    # qui n'en porte pas. C'est ce qui fait de ce geste une revue et non une importation.
    if entree is not None and bible_mod.entree(copie, nom) is None:
        copie = bible_mod.fusionner(copie, {"personnages": [entree]})
        cible = bible_mod.entree(copie, nom)
        if cible is not None:
            cible["valide_par_humain"] = True
    promues = 0
    for entree in copie["personnages"]:
        if str(entree.get("nom") or "") != nom:
            continue
        for reference in entree.get("references") or []:
            if str(reference.get("fichier") or "") in voulus \
                    and reference.get("confiance") != "humaine":
                reference["confiance"] = "humaine"
                promues += 1
    return copie, promues


# ──────────────────  Le moteur peut-il honorer ce qu'on va lui demander ?  ──────────────────

def canaux_manquants(reg: dict, canaux_du_moteur) -> list:
    """Les canaux que la configuration ARME et que le moteur ne sait pas honorer.

    ⚠ **Ceci existe parce que le refus arrivait trop tard.** `moteur.verifier_canaux` refuse
    déjà — et il a raison de refuser : « une requête dont un canal a été jeté sans un mot
    produirait une image plausible et fausse ». Mais il refuse au moment de générer, c'est-à-dire
    **après** que l'utilisateur a choisi son personnage, relu neuf images une par une, relu
    cinq attributs, et tapé son nom. Constaté à l'usage le 2026-08-31, sur une configuration où
    `illustration.identite.actif` valait `true` avec le workflow **texte-vers-image** — qui ne
    porte aucun `%reference_1%`.

    La règle est celle du dépôt pour tous ses diagnostics : **ce qui va échouer doit se dire
    avant que le temps soit dépensé**, pas après. `run.py --check` existe pour cela ; l'atelier
    le fait dans son bandeau.

    Rend `[]` quand rien ne manque, ou quand le moteur ne déclare aucun canal — un moteur qui
    ne dit rien de ses canaux n'est pas un moteur qu'on peut contredire."""
    declares = frozenset(canaux_du_moteur or ())
    if not declares:
        return []
    manquants = []
    if reg.get("identite", {}).get("actif") and "references" not in declares:
        manquants.append("references")
    invite = reg.get("prompt") or {}
    if invite.get("style") == "ancrages" and int(invite.get("ancrages_max") or 0) > 0 \
            and "references" not in declares and "references" not in manquants:
        manquants.append("references")
    return manquants


#: Le workflow livré qui porte le canal des références. Nommé ici plutôt que dans le message :
#: un remède cité dans une phrase se périme sans qu'on le voie.
WORKFLOW_EDITION = "illustration/workflows/qwen-image-edit-2511.api.json"


def remede_canal(canal: str, workflow: str) -> str:
    """Ce qu'il faut changer, en une phrase, avec le chemin exact. Pas « configurez le canal »."""
    if canal != "references":
        return (f"le workflow {workflow} ne porte aucun marqueur de ce canal — ajoute-le, ou "
                f"désarme le réglage qui le demande.")
    return (f"le workflow armé ({workflow}) est un graphe TEXTE-VERS-IMAGE : il n'a pas de "
            f"nœud pour recevoir une image de référence, donc l'identité du personnage ne "
            f"peut pas lui être montrée.\n"
            f"  → dans config.yaml, illustration.comfyui.workflow : « {WORKFLOW_EDITION} »\n"
            f"  → ou désarme illustration.identite.actif — le modèle inventera alors un "
            f"visage, et l'image ne ressemblera à personne.")


# ────────────────────────────  Le choix personnalisé  ────────────────────────────

#: Nom de fichier des images demandées par une description libre. Il ne porte ni le nom de
#: l'œuvre ni celui d'un personnage : il n'y a pas de personnage.
ARDOISE_LIBRE = "description-libre"


def bloc_libre(description: str, *, cadrage: str, gabarit: str = "portrait",
               langue: str = "fr", forme: str = "prose", style: str = "",
               references=None, nombre_images: int = 1, graine=None) -> dict:
    """Un bloc de `requete.yaml` bâti sur une description ÉCRITE PAR L'HUMAIN.

    ⚠ **La charpente du gabarit s'applique quand même** — cadrage, décor, prompt négatif,
    désignation des images de référence. Ce que l'humain écrit remplace les *attributs*, pas la
    grammaire du modèle d'image : sans la charpente, une description libre perdrait le prompt
    négatif et sa désignation des références, c'est-à-dire les deux choses qu'il ne sait pas
    qu'il doit écrire.

    ⚠ **`attributs_sources` porte une entrée unique, `origine: humain`.** C'est ce qui permet
    de distinguer dans le sidecar une image dont chaque mot vient de l'œuvre d'une image dont
    les mots viennent de son auteur. Les confondre viderait de son sens toute la traçabilité
    du lot 26."""
    from illustration import gabarits as gabarits_mod
    from illustration import requete as requete_mod

    texte = " ".join(str(description or "").split())
    if not texte:
        raise ValueError("une description personnalisée vide ne décrit rien — l'atelier "
                         "refuse plutôt que de produire une image au hasard.")
    gab = gabarits_mod.charger(gabarit, langue=langue)
    retenues = list(references or [])
    corps = " ".join(m for m in (
        gab.cadrage(cadrage), texte, style.strip(),
        gab.designation(len(retenues))) if m and m.strip())

    bloc = requete_mod.image_vide(ARDOISE_LIBRE)
    bloc.update({
        "personnage": "", "cadrage": cadrage,
        "prompt": corps, "prompt_negatif": gab.prompt_negatif(),
        "references": [c.payload() for c in retenues] if _sont_des_choix(retenues) else [],
        "attributs_sources": [{
            "attribut": "description",
            "valeur": texte,
            "texte": texte,
            "source": "saisie à l'écran par l'humain",
            "certitude": "humaine",
            "origine": "humain"}],
        "nombre_images": max(1, int(nombre_images)),
        "graine": None if graine is None else int(graine)})
    return bloc


def _sont_des_choix(elements) -> bool:
    return bool(elements) and hasattr(elements[0], "payload")
