# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L23.3 / L23.4 passe 2 — ce que le modèle propose, et **ce que le code refuse**.

Deux passes appellent un modèle : l'une lit des passages de texte, l'autre regarde une
illustration. Les deux rendent le même format, sont lues par le même analyseur, et
n'écrivent **jamais** dans `bible.yaml` — leur sortie va dans
`sources/<Projet>/bible.propositions.yaml`, avec `confiance: 'llm'`.

## Les trois garde-fous, et ils sont dans le CODE

C'est le point du module. Un prompt qui demande de la retenue est une demande ; ce qui suit
est une contrainte.

1. **Un nom hors glossaire est REJETÉ, pas ajouté.** Le glossaire reste la source unique des
   noms. C'est le même geste que `manga/relecture.py`, où « une correction nommant une règle
   inconnue est rejetée par le code — pas par le modèle, qui est justement la partie qu'on ne
   contrôle pas ».
2. **Une ligne sans numéro de passage valable est rejetée sans être lue.** Sans elle,
   l'attribut n'aurait pas de citation, et un attribut sans citation n'entre pas dans la
   bible (`core/bible.py`). Le refus est donc en amont, là où il coûte le moins.
3. **La certitude est publiée, pas consommée.** Une abstention basse est suspecte et doit se
   voir au banc. Aucune valeur de `certitude` ne fait entrer quoi que ce soit dans la bible :
   seule la revue humaine le fait.

## Ce que la mesure du 2026-08-29 dit du modèle vision

Sur **12 illustrations** de deux tomes (4 de *Pride and Prejudice*, 8 de roman D Vol.1),
`yume-27b` — dont `ollama show` confirme la capacité `vision` et un projecteur CLIP de
460,73 M de paramètres — décrit **6 fois sur 12 de façon exacte**, **5 fois partiellement**
et **1 fois faussement**, à 8,3 s par image. La description fausse sexe un personnage à
l'inverse du dessin. C'est précisément le genre d'erreur que le garde-fou n° 2 rend
vérifiable : la citation nomme le fichier, et l'ouvrir tranche en trois secondes.

⚠ Il lit aussi le **texte imprimé sur la planche** — sur une double page, il a restitué les
deux noms de personnages parce qu'ils étaient étiquetés dessus. Ce n'est pas de la
reconnaissance, c'est de la lecture ; le compter comme une reconnaissance surestimerait ce
que la passe sait faire sur une planche sans étiquette.
"""
from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from pathlib import Path

from .bible import ATTRIBUTS

#: Nom du prompt dans le pack de langue.
PROMPT = "bible_apparence"

#: Réponse d'un modèle qui n'a rien relevé. Exigée explicitement : une réponse VIDE est
#: indistinguable d'un appel raté, et on ne veut pas confondre les deux au rapport. Même
#: convention que `manga/relecture.py`.
RIEN = "RAS"

#: Niveaux de certitude que la passe image peut annoncer. `indeterminee` est le défaut quand
#: le modèle n'en annonce aucun — l'abstention est le comportement normal, pas l'exception.
CERTITUDES = ("haute", "moyenne", "indeterminee")

#: Nombre de lignes refusées conservées à titre d'exemple. Compter un refus sans jamais en
#: montrer un rend le compteur inutilisable : sur roman D, `passage_invalide: 25` ne se
#: comprend qu'en voyant les lignes — le modèle y répétait le même attribut en incrémentant
#: le numéro de passage de 26 à 50, hors du lot de 25 qu'on lui avait donné.
EXEMPLES_MAX = 5

#: Longueur maximale d'une valeur d'attribut. Au-delà, le modèle a écrit une phrase et non un
#: attribut : la ligne est rejetée plutôt que tronquée, parce qu'une phrase tronquée reste
#: fausse.
LONGUEUR_VALEUR = 60

#: Côté maximal de l'image envoyée au modèle. Mesuré : 8,3 s par illustration à 1024 px sur
#: `yume-27b`. Envoyer 6 Mpx bruts multiplierait l'encodage sans rien apprendre au projecteur,
#: qui travaille de toute façon sur une grille réduite.
COTE_VISION = 1024

_LIGNE = re.compile(r"^\s*(.+?)\s*\|\s*([a-z_]+)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*$")
_CERTITUDE = re.compile(r"^\s*certitude\s*[:=]\s*([a-zéè]+)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Proposition:
    """Un attribut proposé par un modèle, **avec sa citation**. Sans citation, pas d'objet."""

    nom: str
    attribut: str
    valeur: str
    source: str
    texte: str
    certitude: str = "indeterminee"


class PromptAbsent(SystemExit):
    """Le pack de langue ne fournit pas `bible_apparence.md`.

    ⚠ **Aucun repli silencieux vers le français.** C'est la règle écrite de `core/langues.py`,
    et l'absence du fichier vaut refus explicite de la brique — pas retour au défaut. Un pack
    qui ne le fournit pas n'est pas cassé pour autant : `bible_apparence` n'est **pas** dans
    `PROMPTS_REQUIS`, exactement comme `manga_relecteur.md`, parce qu'un prompt d'outil
    optionnel ne doit pas invalider un pack au démarrage d'un run de traduction."""


def charger_prompt(pack) -> str:
    """Le texte du prompt système, ou `PromptAbsent`."""
    chemin = Path(pack.prompt(PROMPT))
    if not chemin.is_file():
        raise PromptAbsent(
            f"le pack de langue ne fournit pas {chemin}.\n"
            f"  → la passe d'apparence de la bible ne tourne pas dans cette langue.\n"
            f"  → aucun repli vers le français : un attribut relevé dans une autre langue "
            f"que la cible serait faux sans être visible.")
    return chemin.read_text(encoding="utf-8")


def formater_passages(candidats) -> str:
    """Les passages candidats, **numérotés à partir de 1**, tels que le modèle les citera.

    La numérotation EST le lien entre la réponse et la citation : c'est elle qui permet de
    rejeter une ligne dont le numéro ne désigne rien."""
    return "\n".join(f"{i}. [{c.source}] {c.texte}" for i, c in enumerate(candidats, 1))


def analyser(reponse: str, noms_autorises, passages) -> tuple[list[Proposition], dict]:
    """La réponse d'un modèle → (propositions retenues, compteurs de rejet).

    `passages` est la liste des candidats fournie au modèle, dans le même ordre ; l'index 0
    désigne l'illustration elle-même pour la passe image et n'est accepté que si `passages`
    porte une entrée `0` explicite (voir `analyser_image`).

    Les compteurs de rejet sont rendus, jamais tus : « le modèle a proposé 40 attributs, le
    code en a refusé 12 » est une mesure ; « 28 attributs » n'en est pas une. La clé
    `exemples` porte quelques lignes refusées telles quelles — un compteur sans exemple ne
    se diagnostique pas.

    ⚠ **Le cas mesuré qui justifie le garde-fou n° 2 à lui seul.** Sur roman D, un lot de
    25 passages, `yume-27b` est parti en boucle : la même ligne
    `Gomuji | age_apparent | dix-huit ans` répétée avec un numéro de passage incrémenté de 26
    à 50 — c'est-à-dire au-delà du lot fourni. Sans le contrôle de plage, un attribut serait
    entré 25 fois dans la bible avec 25 citations fabriquées. Le contrôle en a refusé 25 sur
    25. Ce comportement n'est pas constant : trois passes sur le même corpus le même jour ont
    donné 1, 25 et 36 refus."""
    connus = {str(n) for n in noms_autorises}
    rejets: dict = {"nom_inconnu": 0, "attribut_inconnu": 0, "passage_invalide": 0,
                    "valeur_trop_longue": 0, "ligne_illisible": 0, "exemples": []}
    certitude = "indeterminee"
    retenues: list[Proposition] = []

    for brute in (reponse or "").splitlines():
        ligne = brute.strip()
        if not ligne or ligne.upper() == RIEN:
            continue
        marque = _CERTITUDE.match(ligne)
        if marque:
            valeur = _sans_accent(marque.group(1))
            certitude = valeur if valeur in CERTITUDES else "indeterminee"
            continue
        trouve = _LIGNE.match(ligne)
        if not trouve:
            _refuser(rejets, "ligne_illisible", ligne)
            continue
        nom, attribut, valeur, index = (trouve.group(1).strip(), trouve.group(2).strip(),
                                        trouve.group(3).strip(), int(trouve.group(4)))
        if nom not in connus:
            _refuser(rejets, "nom_inconnu", ligne)
            continue
        if attribut not in ATTRIBUTS:
            _refuser(rejets, "attribut_inconnu", ligne)
            continue
        if len(valeur) > LONGUEUR_VALEUR:
            _refuser(rejets, "valeur_trop_longue", ligne)
            continue
        if not 1 <= index <= len(passages):
            _refuser(rejets, "passage_invalide", ligne)
            continue
        candidat = passages[index - 1]
        retenues.append(Proposition(nom=nom, attribut=attribut, valeur=valeur,
                                    source=candidat.source, texte=candidat.texte,
                                    certitude=certitude))
    return retenues, rejets


def _refuser(rejets: dict, motif: str, ligne: str) -> None:
    rejets[motif] += 1
    if len(rejets["exemples"]) < EXEMPLES_MAX:
        rejets["exemples"].append(f"{motif} : {ligne[:100]}")


def compte_des_rejets(rejets: dict) -> int:
    """Le total des refus. `exemples` n'est pas un compteur et ne s'additionne pas."""
    return sum(v for c, v in (rejets or {}).items() if isinstance(v, int) and c != "exemples")


def _sans_accent(texte: str) -> str:
    import unicodedata
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def image_en_base64(chemin: Path, cote: int = COTE_VISION) -> str:
    """Une image de `media/` prête pour `LLM.chat(..., images=[…])` : PNG, base64, **sans**
    le préfixe `data:` — c'est `core/llm.py` qui l'ajoute."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(chemin) as im:
        im = im.convert("RGB")
        im.thumbnail((cote, cote))
        tampon = io.BytesIO()
        im.save(tampon, "PNG")
    return base64.b64encode(tampon.getvalue()).decode("ascii")


def _liste_des_personnages(personnages) -> str:
    """Les personnages tels qu'on les présente au modèle : nom, genre déclaré, description
    narrative du glossaire. C'est ce qui lui permet de RECONNAÎTRE, et c'est aussi la seule
    liste de noms qu'il a le droit d'employer."""
    lignes = []
    for e in personnages:
        nom = str(e.get("nom") or "").strip()
        if not nom:
            continue
        genre = str(e.get("genre") or "").strip()
        marque = f" [{genre}]" if genre and genre != "?" else ""
        desc = str(e.get("description") or "").strip()
        lignes.append(f"- {nom}{marque}" + (f" — {desc}" if desc else ""))
    return "\n".join(lignes)


def proposer_depuis_texte(llm, modele: str, systeme: str, personnages,
                          candidats) -> tuple[list[Proposition], dict]:
    """Passe 2 de L23.4 : le modèle lit les passages candidats et en extrait les attributs.

    Aucun appel si la passe lexicale n'a rien trouvé — c'est tout l'intérêt de l'avoir faite
    d'abord."""
    if not candidats:
        return [], {}
    message = (
        "PERSONNAGES (la seule liste de noms autorisée) :\n"
        f"{_liste_des_personnages(personnages)}\n\n"
        "PASSAGES numérotés :\n"
        f"{formater_passages(candidats)}\n")
    reponse = llm.chat(modele, systeme, message, temperature=0.1, max_tokens=1200)
    return analyser(reponse, [str(e.get("nom") or "") for e in personnages], candidats)


@dataclass(frozen=True)
class _Illustration:
    """Le « passage » d'une illustration : sa source est le fichier, son texte le dit."""

    source: str
    texte: str


def proposer_depuis_image(llm, modele: str, systeme: str, personnages, chemin: Path,
                          relatif: str) -> tuple[list[Proposition], dict]:
    """L23.3 : le modèle regarde une illustration avec la liste des personnages en main.

    ⚠ Un appel vision par illustration retenue. Mesuré le 2026-08-29 sur `yume-27b` :
    **8,3 s par image** à 1 024 px (99,9 s pour 12), la couverture la plus lourde à 32,3 s.
    Sur les 300 illustrations exploitables du corpus, c'est ~42 minutes une fois — un coût
    réel mais unique, et c'est ce chiffre-là qui dit si la passe est utilisable, pas une
    impression."""
    passage = _Illustration(source=relatif, texte=f"illustration {relatif}")
    message = (
        "PERSONNAGES (la seule liste de noms autorisée) :\n"
        f"{_liste_des_personnages(personnages)}\n\n"
        "L'image jointe est l'illustration 1. Relève ce qu'elle MONTRE, et cite-la avec le "
        "numéro 1. Commence ta réponse par une ligne « certitude: haute|moyenne|"
        "indeterminee ». Dans le doute, écris « indeterminee » : l'abstention est le "
        "comportement attendu, pas un échec.\n")
    reponse = llm.chat(modele, systeme, message, temperature=0.1, max_tokens=600,
                       images=[image_en_base64(chemin)])
    return analyser(reponse, [str(e.get("nom") or "") for e in personnages], [passage])


def en_bible(propositions: list[Proposition], references=None) -> dict:
    """Les propositions, mises à la forme de `bible.yaml` — **chaque attribut avec sa
    citation**, `confiance: 'llm'` sur chaque référence, `valide_par_humain: false` partout.

    C'est ici que la règle de citation devient structurelle plutôt que déclarative : une
    proposition ne peut pas produire un attribut sans produire la citation qui va avec."""
    from . import bible as bible_mod
    par_nom: dict[str, dict] = {}
    for p in propositions:
        entree = par_nom.setdefault(p.nom, bible_mod.personnage(p.nom))
        if p.attribut in bible_mod.ATTRIBUTS_LISTE:
            if p.valeur not in entree["apparence"][p.attribut]:
                entree["apparence"][p.attribut].append(p.valeur)
        elif not entree["apparence"][p.attribut]:
            entree["apparence"][p.attribut] = p.valeur
        entree["citations"].append({"attribut": p.attribut, "texte": p.texte,
                                    "source": p.source, "certitude": p.certitude})
    for nom, fichiers in (references or {}).items():
        entree = par_nom.setdefault(nom, bible_mod.personnage(nom))
        connus = {r["fichier"] for r in entree["references"]}
        for fichier, contexte, classe in fichiers:
            if fichier in connus:
                continue
            entree["references"].append({
                "fichier": fichier, "classe": classe, "contexte": contexte,
                # ⚠ `cadre`, et non `recadrage` : jusqu'au lot 29 cette passe écrivait
                # `recadrage: []` pendant que `illustration/identite.py` lisait `cadre`. Le
                # champ écrit n'était pas celui qui était lu, et il n'a donc jamais pu être
                # rempli — une des raisons pour lesquelles l'axe « nature du recadrage » du
                # PLAN-25 est resté non mesuré deux lots de suite. Cf. `bible.CADRE_HERITE`,
                # qui relit l'ancien nom.
                "confiance": "llm", "cadre": [], "role": "identite"})
            connus.add(fichier)
    return {"version": bible_mod.VERSION, "style": {"ancrages": [],
            "signature": bible_mod.signature_vide(), "mots": ""},
            "personnages": list(par_nom.values())}
