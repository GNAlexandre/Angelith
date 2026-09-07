# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Insérer des images **étiquetées** dans un Markdown assemblé — `PLAN-27` L27.4.

## Pourquoi dans `core/` et pas dans `illustration/`

`tests/test_imports_briques.py:test_illustration_est_une_feuille_du_graphe` tient une
propriété que ce lot ne veut pas perdre : **personne n'importe `illustration/`**, « c'est ce
qui rend la brique supprimable sans rien casser, et c'est la moitié de ce que *désarmée par
défaut* veut dire ». Un `pipeline` → `illustration` la casserait pour de bon : le light novel
ne compilerait plus sans la brique générative.

Le dépôt a déjà tranché ce cas de figure, et la règle est écrite dans la table du graphe
d'imports : « si une fonction de `manga/` devient nécessaire, elle **remonte dans `core/`** ».
C'est ce qui est fait ici. Le module ne sait rien du modèle d'image ni de la bible visuelle :
il reçoit des chemins d'images et des légendes, il rend du Markdown.

⚠ Conséquence pratique : **on peut effacer `illustration/` et rendre un tome**. Sans images
retenues à lire, `retenues()` rend une liste vide et `inserer()` ne change rien.

## Le tuyau existe déjà, et il est bon

`pipeline/images.py` réinjecte les images de la source à leur position proportionnelle via
`<!-- IMG: chemin -->` ; `core/marqueurs.py` porte le contrat du marqueur. Ce module n'en
écrit pas un second : il **fabrique des marqueurs du même format**, que toute la chaîne de
rendu sait déjà lire, compter et vérifier — y compris le contrôle « aucune image perdue en
route » de `pipeline/render.py`.

## La légende n'est pas désactivable, et c'est mécanique

`inserer()` **lève** sur une légende vide. Il n'y a aucune clé de configuration pour la vider,
aucun argument pour la sauter, et aucune branche qui écrive un marqueur sans elle. C'est la
lecture de l'art. 50 de l'AI Act retenue au `PLAN-24` (`docs/ai-provenance.md`), transposée à
la sortie visible : le marquage machine est dans le PNG (bloc `tEXt`, `AIGenerated=true`), la
mention lisible est **sous l'image**, dans le document que quelqu'un ouvrira.

⚠ **La légende est un paragraphe ordinaire en italiques, pas un style Word.** Le contrat de
styles de `langues/<code>/templates/reference.docx` est ce que la règle de numérotation du
dépôt désigne comme un MAJEUR quand on le rompt ; y ajouter un style « Légende » pour cette
seule ligne le romprait. Un paragraphe de corps de texte en italiques sort correctement dans
les trois formats sans qu'aucun gabarit ait à changer.

## L'espace de noms, et pourquoi il ne peut pas collisionner

`pipeline/images.py` documente que la source d'images est **une seule langue à la fois**,
« jamais un mélange de plusieurs langues, qui provoquerait des collisions de noms de fichiers
(chaque document renumérote ses médias depuis 1) ». Une illustration générée n'appartient à
aucune langue source : elle doit donc vivre dans un espace de noms qui ne peut pas répondre au
même chemin qu'un `media/imageN.png`.

Deux propriétés indépendantes le garantissent, et `collisions()` les vérifie :

1. le chemin de marqueur d'une illustration ne commence **jamais** par `media/` — il pointe
   vers `sources/<Projet>/illustrations/`, qui n'est pas sous le dossier de build ;
2. le nom de fichier reçoit le préfixe `PREFIXE` (« ia- »), qui n'apparaît dans aucun schéma
   de renumérotation de document : Word, EPUB et PDF nomment leurs médias `image1`, `media1`,
   `img_001`, jamais `ia-…`.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from core.marqueurs import IMG_MARKER, MARQUEUR_RE, split_marker

#: Nom du dossier qui porte les images retenues, sous `sources/<Projet>/`.
NOM_DOSSIER = "illustrations"

#: Préfixe de nom de fichier réservé aux illustrations générées. Voir §« espace de noms ».
PREFIXE = "ia-"

#: Suffixe du sidecar de provenance. Recopié plutôt qu'importé de `illustration/marquage.py` :
#: `core/` n'a pas le droit de remonter vers une brique, et une constante de six caractères
#: dupliquée coûte moins qu'une arête d'import qui casse la propriété de feuille.
#: `tests/test_insertion.py` vérifie que les deux valeurs sont identiques.
SUFFIXE_PROVENANCE = ".provenance.json"

#: Les positions proposées. `debut_chapitre` est le défaut du plan.
DEBUT_CHAPITRE = "debut_chapitre"
FIN_CHAPITRE = "fin_chapitre"
TETE_DE_VOLUME = "tete_de_volume"
POSITIONS: tuple[str, ...] = (DEBUT_CHAPITRE, FIN_CHAPITRE, TETE_DE_VOLUME)

LIBELLES_POSITION = {
    DEBUT_CHAPITRE: "au début du premier chapitre qui nomme le personnage",
    FIN_CHAPITRE: "à la fin du premier chapitre qui nomme le personnage",
    TETE_DE_VOLUME: "toutes en tête de volume, avant le premier chapitre",
}

#: La légende, en français, **à son site d'appel** — comme toutes les consignes du dépôt
#: (`core.langues.Pack.consigne` : « le recopier ailleurs en ferait une seconde source »).
#: Un pack de langue la traduit par la clé `legende_illustration_ia`.
LEGENDE_FR = "Illustration générée par IA — ne fait pas partie de l'œuvre originale"

#: La clé de consigne du pack de langue.
CLE_LEGENDE = "legende_illustration_ia"


class LegendeManquante(RuntimeError):
    """Une insertion a été demandée sans légende. Elle n'a pas lieu.

    ⚠ Ce n'est pas une validation de confort : c'est le seul endroit du code qui puisse
    produire une image d'IA visible dans un document sans qu'elle se déclare comme telle.
    Le refus est donc une exception, pas un avertissement."""


@dataclass(frozen=True)
class Illustration:
    """Une image retenue, telle que son sidecar de provenance la décrit."""

    chemin: Path
    personnage: str = ""
    graine: object = None
    cadrage: str = ""
    date: str = ""
    modele: str = ""

    @property
    def nom(self) -> str:
        return self.chemin.name


@dataclass(frozen=True)
class Inseree:
    """Une insertion effectivement faite — ce que `RAPPORT.md` liste."""

    illustration: Illustration
    position: str
    #: Le titre du chapitre où elle a atterri, ou `""` pour la tête de volume.
    chapitre: str = ""
    marqueur: str = ""


# ─────────────────────────────  Lire ce qui a été retenu  ─────────────────────────────

def dossier_retenues(racine_sources, projet: str) -> Path:
    """`sources/<Projet>/illustrations/` — l'emplacement pérenne de l'étape 0.2 du plan."""
    return Path(racine_sources) / projet / NOM_DOSSIER


def retenues(dossier) -> list:
    """Les images retenues d'un projet, avec ce que leur sidecar en dit.

    ⚠ **Une image sans sidecar est ignorée**, et ce n'est pas de la sévérité gratuite : le
    sidecar est ce qui prouve qu'elle vient de cette brique et qu'un humain a validé son
    prompt. Insérer dans un tome une image dont on ne peut rien dire irait contre tout ce que
    la légende affirme."""
    dossier = Path(dossier)
    if not dossier.is_dir():
        return []
    sorties = []
    for chemin in sorted(dossier.glob("*.png")):
        sidecar = chemin.with_name(chemin.name + SUFFIXE_PROVENANCE)
        if not sidecar.is_file():
            continue
        try:
            donnees = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not donnees.get("genere_par_ia"):
            continue
        source = donnees.get("prompt_source") or {}
        payload = donnees.get("payload") or {}
        sorties.append(Illustration(
            chemin=chemin,
            personnage=str(source.get("personnage") or ""),
            graine=payload.get("graine"),
            cadrage=str(source.get("cadrage") or ""),
            date=str(donnees.get("date") or ""),
            modele=str(donnees.get("modele") or "")))
    return sorties


# ─────────────────────────────  Fabriquer les marqueurs  ─────────────────────────────

def chemin_de_marqueur(image, depuis) -> str:
    """Le chemin que Pandoc résoudra, **relatif au dossier de build**, en séparateurs `/`.

    ⚠ Relatif et non absolu : le Markdown assemblé est l'artefact durable du run, rejoué tel
    quel par `--render-only` des mois plus tard, et un `C:/Users/…` dedans ne se rejouerait
    pas ailleurs. Un chemin absolu n'est produit que quand le relatif est impossible (deux
    volumes Windows différents), et c'est alors la seule chose honnête à écrire."""
    image, depuis = Path(image), Path(depuis)
    try:
        relatif = os.path.relpath(image.resolve(), depuis.resolve())
    except (OSError, ValueError):
        return image.resolve().as_posix()
    return Path(relatif).as_posix()


def marqueur(illustration: Illustration, depuis) -> str:
    """Le marqueur `<!-- IMG: … -->` d'une illustration, au format du dépôt."""
    return IMG_MARKER.format(chemin_de_marqueur(illustration.chemin, depuis))


def bloc(illustration: Illustration, depuis, legende: str) -> str:
    """Le marqueur **et sa légende**, en deux paragraphes. Jamais l'un sans l'autre.

    La légende est en italiques (`*…*`) : c'est du balisage **en ligne**, qui traverse Pandoc
    dans les trois formats sans demander de style de paragraphe — donc sans toucher au
    contrat de styles de `reference.docx`."""
    texte = " ".join(str(legende or "").split())
    if not texte:
        raise LegendeManquante(
            "aucune légende : l'insertion n'a pas lieu.\n"
            "  Une image d'IA visible dans un document doit se déclarer comme telle. Le "
            "marquage machine est dans le PNG (bloc tEXt, AIGenerated=true) ; la mention "
            "lisible est sous l'image, et elle n'a pas d'interrupteur.")
    return f"{marqueur(illustration, depuis)}\n\n*{texte}*"


# ─────────────────────────────────  Insérer  ─────────────────────────────────

def inserer(markdown: str, illustrations, *, legende: str, depuis,
            position: str = DEBUT_CHAPITRE) -> tuple:
    """Rend `(markdown augmenté, [Inseree])`. **N'écrit rien.**

    ⚠ **Le texte de l'œuvre n'est jamais modifié** : on n'insère que des paragraphes NEUFS
    entre les siens. Aucun caractère de récit n'est réécrit, réordonné ni supprimé, et
    `tests/test_insertion.py` le vérifie en retirant les insertions du résultat et en le
    comparant à l'original — **à la normalisation des lignes vides près**, seule chose que
    l'épissage puisse changer, et qui n'est pas du texte.

    ⚠ Une illustration dont le personnage n'apparaît dans aucun chapitre va **en tête de
    volume** plutôt que d'être perdue. Le dire est plus utile que de la placer au hasard : le
    rapport porte alors `chapitre: ""`."""
    illustrations = list(illustrations or [])
    if not illustrations:
        return markdown, []
    if position not in POSITIONS:
        raise ValueError(
            f"position d'insertion inconnue : « {position} » "
            f"(attendu : {', '.join(POSITIONS)})")
    texte = " ".join(str(legende or "").split())
    if not texte:
        raise LegendeManquante(
            "aucune légende : rien n'est inséré. La mention lisible sous l'image n'a pas "
            "d'interrupteur — voir core/insertion.py.")

    sections = _sections(markdown)
    if position == TETE_DE_VOLUME or not sections:
        points = [(0, i, "") for i in illustrations]
    else:
        points = _points(illustrations, sections, position, markdown)

    # ⚠ On **épisse** dans la chaîne d'origine au lieu de la recomposer par morceaux : aucune
    # ligne de récit ne passe par un `split`/`join`, donc aucune ne peut être perdue ni
    # réordonnée. On avance à rebours pour que chaque décalage porte sur du texte dont les
    # indices n'ont pas encore bougé, et on garde l'ordre de la liste entre égalités
    # d'offset — sans quoi trois images en tête de volume ressortiraient à l'envers.
    sortie = markdown
    for _, (offset, illustration, _titre) in sorted(
            enumerate(points), key=lambda kv: (-kv[1][0], -kv[0])):
        morceau = bloc(illustration, depuis, texte)
        sortie = (sortie[:offset].rstrip("\n") + "\n\n" + morceau + "\n\n"
                  + sortie[offset:].lstrip("\n"))
    inserees = [Inseree(illustration=illustration,
                        position=position if titre else TETE_DE_VOLUME,
                        chapitre=titre, marqueur=marqueur(illustration, depuis))
                for offset, illustration, titre in sorted(points, key=lambda p: p[0])]
    return sortie.lstrip("\n"), inserees


def _sections(markdown: str):
    """`[(titre, début du corps, fin de la section)]` en offsets dans `markdown`.

    On coupe sur les titres de niveau 1 (`# `), ceux que `pipeline/orchestrator.py` écrit pour
    chaque chapitre (`chapter_md = f"# {title_fr}\\n\\n" + …`). Les niveaux 2 et plus sont des
    sous-titres de la source, pas des frontières de chapitre."""
    titres = list(re.finditer(r"(?m)^#[ \t]+\S.*$", markdown))
    sections = []
    for index, titre in enumerate(titres):
        fin = titres[index + 1].start() if index + 1 < len(titres) else len(markdown)
        sections.append((titre.group(0).lstrip("# ").strip(), titre.end(), fin))
    return sections


def _points(illustrations, sections, position: str, markdown: str) -> list:
    """`[(offset, illustration, titre)]` — où chaque image va, et sous quel titre.

    ⚠ Une illustration dont le personnage n'apparaît dans aucun chapitre va en **tête de
    volume** plutôt que d'être perdue ou placée au hasard, et le rapport porte alors un
    chapitre vide."""
    points = []
    for illustration in illustrations:
        index = _chapitre_de(illustration, sections, markdown)
        if index is None:
            points.append((0, illustration, ""))
            continue
        titre, debut, fin = sections[index]
        points.append((debut if position == DEBUT_CHAPITRE else fin, illustration, titre))
    return points


def _chapitre_de(illustration: Illustration, sections, markdown: str) -> int | None:
    """L'index du **premier** chapitre qui nomme le personnage, ou `None`.

    ⚠ Une comparaison insensible à la casse sur le nom **entier**, pas une recherche floue :
    un personnage nommé « Ai » ne doit répondre ni à « j'ai » ni à « mais ». Le nom est
    cherché entre bornes de mot, titre du chapitre compris.

    ⚠ **L'apostrophe compte comme une lettre ici, et c'est une correction de mesure** : le
    `\\w` de Python ne la reconnaît pas, si bien que « Ai » répondait à « **j'ai** » — trouvé
    en écrivant le test. Les deux apostrophes françaises (droite et courbe) et le trait
    d'union sont donc joints à la classe de bord."""
    nom = str(illustration.personnage or "").strip()
    if not nom:
        return None
    bord = r"[\w'’-]"
    motif = re.compile(rf"(?<!{bord})" + re.escape(nom) + rf"(?!{bord})", re.IGNORECASE)
    for index, (titre, debut, fin) in enumerate(sections):
        if motif.search(titre) or motif.search(markdown[debut:fin]):
            return index
    return None


# ─────────────────────────────  Les deux contrôles  ─────────────────────────────

def collisions(markdown: str) -> list:
    """Les chemins d'illustration qui répondraient au même marqueur qu'un média du document.

    ⚠ Ce contrôle existe parce que `pipeline/images.py` en documente le risque : « chaque
    document renumérote ses médias depuis 1 ». Une illustration générée n'appartient à aucune
    langue source, donc à aucune renumérotation ; encore faut-il que son chemin ne puisse pas
    être confondu avec l'un d'eux, et un raisonnement ne suffit pas — le dépôt garde son
    `paint &= region.mask` « parce que l'invariant ne doit pas dépendre d'un raisonnement »."""
    vus: dict[str, list[str]] = {}
    for brut in MARQUEUR_RE.findall(markdown):
        chemin, _ = split_marker(brut)
        vus.setdefault(Path(chemin).name.casefold(), []).append(chemin)
    doubles = []
    for nom, chemins in sorted(vus.items()):
        uniques = sorted(set(chemins))
        if len(uniques) > 1:
            doubles.append(f"« {nom} » désigne {len(uniques)} chemins différents : "
                           f"{', '.join(uniques)}")
    return doubles


def nom_sans_collision(nom: str) -> str:
    """Le nom de fichier d'une illustration, préfixé de `PREFIXE` s'il ne l'est pas déjà."""
    nom = Path(str(nom)).name
    return nom if nom.startswith(PREFIXE) else PREFIXE + nom


def legende_du_pack(pack) -> str:
    """La légende dans la langue cible, ou le français si le pack n'en déclare pas.

    ⚠ **Le repli n'est jamais vide.** Un pack de langue qui oublie la clé produit une légende
    française dans un tome anglais — visible, corrigible, et infiniment préférable à une image
    d'IA sans mention."""
    if pack is None:
        return LEGENDE_FR
    valeur = pack.consigne(CLE_LEGENDE, LEGENDE_FR)
    return " ".join(str(valeur or LEGENDE_FR).split()) or LEGENDE_FR


def lignes_de_rapport(inserees) -> list:
    """Ce que `RAPPORT.md` liste : **l'image, son personnage et sa graine** (critère 3 de L27.4).

    La graine est ce qui rend l'image rejouable ; le personnage est ce qui rend la liste
    lisible. Un rapport qui n'aurait que des noms de fichier obligerait à ouvrir onze sidecars
    pour savoir de qui il s'agit."""
    if not inserees:
        return []
    lignes = ["", "### Illustrations générées insérées dans les sorties", "",
              "⚠ Ces images ne font pas partie de l'œuvre originale. Chacune porte son bloc "
              "`tEXt` (`AIGenerated=true`), son sidecar de provenance, et une légende visible "
              "sous l'image dans les trois formats.", ""]
    for inseree in inserees:
        illustration = inseree.illustration
        ou = f"« {inseree.chapitre.lstrip('# ').strip()} »" if inseree.chapitre \
            else "tête de volume"
        lignes.append(f"- `{illustration.nom}` — personnage : "
                      f"{illustration.personnage or '(aucun)'} · graine : "
                      f"{illustration.graine if illustration.graine is not None else '(non notée)'}"
                      f" · cadrage : {illustration.cadrage or '(non noté)'} · placée {ou}")
    return lignes
