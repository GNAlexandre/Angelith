# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Extraction de texte + images depuis un **.epub**, en Python pur (zipfile + html.parser).

## Pourquoi pas Pandoc, alors qu'il lit les EPUB et qu'il est déjà requis pour les .docx

Mesuré sur `sources/roman A/Vol.1/JAP/roman A.epub` (light novel japonais,
33 documents) : `pandoc -t markdown` produit **2,58 Mo** pour ~200 ko de texte réel, et surtout
il perd le contenu. Trois défauts, tous rédhibitoires :

1. **Les illustrations disparaissent.** Ce livre est en mise en page fixe : ses 16 pleines pages
   d'illustration sont des `<svg><image xlink:href="…"/></svg>`, que Pandoc recopie en HTML brut
   au lieu d'émettre `![](…)`. Le marqueur d'image du pipeline ne les voit donc pas, et les
   16 illustrations sont perdues — sur les 23 images du livre.
2. **Le texte est noyé.** L'EPUB est passé par la chaîne Kobo, qui enveloppe **chaque phrase**
   dans `<span class="koboSpan" id="kobo.N.M">`. Pandoc les rend en attributs Markdown
   (`[texte]{#p-004.xhtml_kobo.12.1 .koboSpan xmlns="…"}`), soit ~24 000 spans d'habillage.
3. **Les furigana sont collés au texte.** `<ruby>七堕<rt>ナナエ</rt></ruby>` ressort `七堕ナナエ`.
   Sur 8 140 ruby, la source japonaise transmise au traducteur est corrompue de bout en bout.

## Ce que ce module fait à la place

Un EPUB est déjà **structuré** : le `spine` du fichier OPF donne l'ordre de lecture, chaque
document est une unité, et la table des matières nomme les sections. Il n'y a donc aucune
heuristique à inventer — c'est l'inverse d'un PDF.

- **Ordre de lecture** = l'ordre du `spine`. Jamais l'ordre du zip ni l'ordre alphabétique.
- **Découpage inline / bloc.** ⚠ Le piège central sur du japonais : `<span>`, `<ruby>`, `<a>`…
  sont **inline**, et joindre leur contenu par une espace donne `千 万 丈 塔` au lieu de
  `千万丈塔`. Le japonais n'a pas d'espace entre les mots : une espace insérée à tort n'est pas
  une coquille de mise en forme, c'est une **erreur de segmentation** qui se propage jusqu'au
  glossaire. Seuls les éléments de bloc et `<br/>` produisent un saut de ligne.
- **Paragraphes.** Un élément de bloc (`<p>`, `<div>`, `<hN>`) ferme un **paragraphe** — une
  ligne vide le suit — là où `<br/>` ne coupe que la ligne, à l'intérieur du paragraphe.
  ⚠ Les deux ont longtemps produit le même saut simple, et c'était un défaut coûteux :
  `split._paragraphs` ne sépare que sur les lignes vides, si bien qu'un document XHTML entier
  ressortait en **un seul paragraphe insécable**. Mesuré sur roman B Vol.3 : 20 paragraphes
  pour 112 107 caractères, dont un de 40 177. Comme `split.split_proportional` ne peut aligner
  une source de référence qu'aux frontières de paragraphes, 43 des 54 morceaux japonais
  ressortaient **vides** et autant de blocs partaient au traducteur sans une ligne de japonais
  — exactement ce que l'alignement existe pour éviter.
- **Furigana** (`<rt>`) : retirés par défaut. Ce livre en compte 8 140 pour ~200 ko de texte,
  soit une glose tous les 22 caractères ; les garder en ligne gonfle la source de 30 %
  (176 210 → 228 967 caractères, mesuré) et noie le traducteur. `epub.ruby: "parentheses"` les conserve sous la forme `七堕(ナナエ)` —
  utile pour un tome dont on veut **relever les lectures** de noms propres au glossaire.
- **Images** : `<img src>` ET `<image xlink:href>` (SVG), les deux.
- **Titres**, dans cet ordre de préférence par document :
    1. une vraie balise `<h1>`…`<h6>` ;
    2. l'intitulé de la **table des matières** (nav EPUB 3 ou NCX EPUB 2) qui pointe dessus ;
    3. sa **première ligne courte**, si le document a du texte après elle.
  Le point 3 est ce qui sauve ce livre-là : ses chapitres s'ouvrent sur un `一`, `二`, `序`,
  `終` posé dans un `<p class="font-1em30 bold">` — un paragraphe STYLÉ, pas un titre. Et la
  feuille de style de l'EPUB ne définit même pas cette classe : la détection par police, celle
  qu'utilisent les chemins PDF et DOCX, n'avait rien à mesurer.
  Un document sans titre retenu n'ouvre pas de chapitre : son texte prolonge le précédent.

Le résultat est le même « markdown-léger » que `extract.py` produit pour les .docx et .pdf —
titres en `#`/`##`, images en `<!-- IMG: … -->` — donc `split.detect_chapters` et tout l'aval
fonctionnent sans rien savoir de l'EPUB.
"""
from __future__ import annotations

import posixpath
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from core import tokens

from .extract import Extracted, make_marker

# Éléments dont le contenu est du texte COURANT : à concaténer SANS séparateur (cf. docstring).
_INLINE = frozenset({
    "span", "a", "em", "strong", "b", "i", "u", "s", "small", "big", "sub", "sup",
    "ruby", "rb", "rt", "rp", "rtc", "code", "kbd", "samp", "var", "cite", "q", "abbr",
    "dfn", "mark", "ins", "del", "bdi", "bdo", "wbr", "time", "data", "font", "tt",
    "nobr", "label", "output",
})

# Éléments dont le contenu ne doit JAMAIS ressortir en texte. `nav` est là pour une raison
# précise : un document de navigation recopié en clair injecterait la table des matières au
# milieu du roman, et ses intitulés seraient pris pour des titres de chapitres.
_MUET = frozenset({"head", "title", "script", "style", "meta", "link", "nav", "epigraph"})

_HEADINGS = {f"h{n}": n for n in range(1, 7)}

# Marque interne d'un SAUT DE LIGNE DU FICHIER SOURCE, à résoudre en fin de ligne (cf.
# `_resoudre_sauts`). Un caractère de la zone à usage privé : jamais dans un texte réel.
_SAUT = ""

# Idéogrammes, kana, ponctuation et formes pleine largeur CJK.
_CJK = re.compile(r"[⺀-〿぀-ヿ㆐-㆟㐀-䶿一-鿿"
                  r"豈-﫿︰-﹏＀-｠￠-￦]")


def _resoudre_sauts(ligne: str) -> str:
    """Résout les sauts de ligne du fichier XHTML, qui sont de la **mise en forme du fichier**
    et non du texte.

    La règle n'est pas la même selon l'écriture, et c'est ce qui rend ce traitement nécessaire :

      · entre deux caractères CJK, le saut **disparaît** — sinon `千万丈塔\\n踏破` donnerait
        `千万丈塔 踏破`, une espace au milieu d'un terme dans une langue qui n'en met pas ;
      · partout ailleurs il vaut **une espace** — sinon un paragraphe anglais replié dans le
        source donnerait `theenemy` au lieu de `the enemy`.

    C'est la règle des navigateurs (« segment break transformation rules » de CSS Text). En
    bord de ligne, le saut ne vaut rien du tout."""
    if _SAUT not in ligne:
        return ligne
    out: list[str] = []
    for i, ch in enumerate(ligne):
        if ch != _SAUT:
            out.append(ch)
            continue
        avant = out[-1] if out else ""
        apres = next((c for c in ligne[i + 1:] if c != _SAUT), "")
        if not avant or not apres or avant == " ":
            continue                                   # bord de ligne, ou espace déjà là
        if _CJK.match(avant) and _CJK.match(apres):
            continue                                   # règle CJK : le saut s'efface
        out.append(" ")
    return "".join(out)


def lecture_dominante(comptes: dict[str, Counter]) -> dict[str, str]:
    """Une lecture par graphie : la PLUS FRÉQUENTE du tome.

    Un même kanji peut être glosé de plusieurs façons — mesuré sur roman A Vol.1 :
    123 graphies sur 1 942. La distribution est presque toujours la même, une lecture
    canonique et des *gikun* isolés (lectures sémantiques d'auteur) : `天茜` est glosé
    あかね 458 fois et きようだい 1 fois, `祭花` まつりか 388 fois et エナガ一三七 1 fois.

    Retenir la PREMIÈRE rencontrée choisirait donc parfois le cas isolé — c'est ce qui
    arrivait à `祭花`, dont le gikun apparaît dans un document placé plus tôt dans le
    spine. `Counter.most_common` départage à égalité par ordre d'insertion, donc le
    résultat reste déterministe."""
    return {base: c.most_common(1)[0][0] for base, c in comptes.items() if c}


@dataclass
class DocumentEpub:
    """Un document du spine, après analyse."""
    idref: str
    href: str                       # chemin dans le zip
    lignes: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    a_un_titre: bool = False        # une vraie balise <hN> a été rencontrée
    # Furigana : graphie → NOMBRE d'occurrences de chaque lecture (cf. `lecture_dominante`).
    comptes: dict[str, Counter] = field(default_factory=dict)

    @property
    def texte(self) -> str:
        """Le document en markdown-léger, **paragraphes séparés par une ligne vide**.

        C'est la forme qu'attend `split._paragraphs`, et donc `split.split_proportional`, qui
        ne sait aligner une source de référence sur les blocs du pivot qu'aux frontières de
        paragraphes. Les entrées vides sont posées par `_Analyseur._clore`.

        Les vides consécutifs sont réduits à un seul : deux blocs imbriqués (`<div><p>…`)
        closent la ligne deux fois, et une succession de lignes blanches ne veut rien dire de
        plus qu'une seule."""
        sortie: list[str] = []
        for ligne in self.lignes:
            if not ligne and (not sortie or not sortie[-1]):
                continue                    # jamais deux vides d'affilée, ni un vide en tête
            sortie.append(ligne)
        return "\n".join(sortie).strip()


# --------------------------------------------------------------------------- #
# Lecture du conteneur : OPF, spine, table des matières
# --------------------------------------------------------------------------- #

def _texte_xml(donnees: bytes) -> str:
    """Décode un fichier XML du zip. L'encodage déclaré est respecté quand il n'est pas
    UTF-8 (rare mais légal : quelques EPUB anciens sont en Shift-JIS)."""
    m = re.match(rb"<\?xml[^>]*encoding=[\"']([\w-]+)[\"']", donnees[:200])
    encodage = m.group(1).decode("ascii", "replace") if m else "utf-8"
    try:
        return donnees.decode(encodage)
    except (LookupError, UnicodeDecodeError):
        return donnees.decode("utf-8", errors="replace")


def chemin_opf(z: zipfile.ZipFile) -> str:
    """Chemin du fichier OPF, lu dans `META-INF/container.xml`.

    On ne devine PAS son emplacement : il varie d'un producteur à l'autre (`content.opf`,
    `OEBPS/content.opf`, `item/standard.opf` pour ce livre-ci), et le conteneur est le seul
    endroit normatif qui le donne."""
    try:
        brut = _texte_xml(z.read("META-INF/container.xml"))
    except KeyError:
        raise RuntimeError("EPUB invalide : META-INF/container.xml est absent.") from None
    m = re.search(r"<rootfile[^>]*full-path=[\"']([^\"']+)[\"']", brut)
    if not m:
        raise RuntimeError("EPUB invalide : aucun <rootfile full-path=…> dans le conteneur.")
    return m.group(1)


def _attributs(balise: str) -> dict[str, str]:
    return {k.lower(): v for k, v in
            re.findall(r"([\w:.-]+)\s*=\s*[\"']([^\"']*)[\"']", balise)}


def lire_opf(brut: str, base: str) -> tuple[dict[str, dict], list[str], str | None]:
    """`(manifeste, spine, href de la table des matières)`.

    Le manifeste associe un identifiant à `{href, type, properties}` ; le spine est la liste
    ORDONNÉE des identifiants — c'est lui, et lui seul, qui donne l'ordre de lecture."""
    manifeste: dict[str, dict] = {}
    for balise in re.findall(r"<item\b[^>]*/?>", brut):
        a = _attributs(balise)
        if "id" in a and "href" in a:
            manifeste[a["id"]] = {
                "href": posixpath.normpath(posixpath.join(base, _deshtml(a["href"]))),
                "type": a.get("media-type", ""),
                "properties": a.get("properties", ""),
            }

    bloc = re.search(r"<spine\b(.*?)</spine>", brut, re.S)
    spine: list[str] = []
    toc_id = None
    if bloc:
        a_spine = _attributs(bloc.group(0)[:bloc.group(0).find(">") + 1])
        toc_id = a_spine.get("toc")
        for balise in re.findall(r"<itemref\b[^>]*/?>", bloc.group(1)):
            a = _attributs(balise)
            # `linear="no"` = hors du flux de lecture principal (notes, publicité). On le
            # garde quand même : sur un light novel, ce sont souvent les pages d'illustration.
            if a.get("idref") in manifeste:
                spine.append(a["idref"])

    toc_href = None
    for ident, item in manifeste.items():
        if "nav" in item["properties"].split():
            toc_href = item["href"]
            break
    if toc_href is None and toc_id and toc_id in manifeste:
        toc_href = manifeste[toc_id]["href"]        # repli EPUB 2 : le toc.ncx
    return manifeste, spine, toc_href


def _deshtml(s: str) -> str:
    from html import unescape
    return unescape(s)


def lire_toc(z: zipfile.ZipFile, toc_href: str | None) -> dict[str, str]:
    """`{href de document → intitulé}` depuis le nav EPUB 3 ou le NCX EPUB 2.

    Le fragment (`#ancre`) est retiré : on ne sait nommer qu'un document entier, et un
    intitulé qui viserait le milieu d'un document ne doit pas nommer tout le document. Le
    PREMIER intitulé gagne (les tables des matières listent parfois deux fois la même cible)."""
    if not toc_href:
        return {}
    try:
        brut = _texte_xml(z.read(toc_href))
    except KeyError:
        return {}
    base = posixpath.dirname(toc_href)
    out: dict[str, str] = {}

    def _ajouter(href: str, label: str) -> None:
        label = re.sub(r"\s+", " ", _deshtml(label)).strip()
        cible = posixpath.normpath(posixpath.join(base, _deshtml(href).split("#")[0]))
        if label and cible not in out:
            out[cible] = label

    # NCX (EPUB 2) : <navPoint><navLabel><text>…</text></navLabel><content src="…"/>
    for bloc in re.findall(r"<navPoint\b.*?</navPoint>", brut, re.S):
        label = re.search(r"<text[^>]*>(.*?)</text>", bloc, re.S)
        src = re.search(r"<content[^>]*src=[\"']([^\"']+)[\"']", bloc)
        if label and src:
            _ajouter(src.group(1), re.sub(r"<[^>]+>", "", label.group(1)))

    # Nav EPUB 3 : le <nav epub:type="toc"> seulement — « landmarks » et « page-list »
    # pointent sur la couverture et sur des numéros de page, pas sur des chapitres.
    for bloc in re.findall(r"<nav\b[^>]*>.*?</nav>", brut, re.S):
        entete = bloc[:bloc.find(">") + 1]
        types = _attributs(entete).get("epub:type", "") or _attributs(entete).get("type", "")
        if "toc" not in types.split():
            continue
        for lien in re.findall(r"<a\b[^>]*>.*?</a>", bloc, re.S):
            a = _attributs(lien[:lien.find(">") + 1])
            if "href" in a:
                _ajouter(a["href"], re.sub(r"<[^>]+>", "", lien[lien.find(">") + 1:-4]))
    return out


# --------------------------------------------------------------------------- #
# Analyse d'un document XHTML
# --------------------------------------------------------------------------- #

class _Analyseur(HTMLParser):
    """XHTML → lignes de markdown-léger. Voir la docstring du module pour la règle
    inline/bloc, qui est le cœur de la correction sur une source japonaise."""

    def __init__(self, *, ruby: str, sur_image) -> None:
        super().__init__(convert_charrefs=True)
        self.ruby = ruby
        self.sur_image = sur_image
        self.lignes: list[str] = []
        self.a_un_titre = False
        self._courante: list[str] = []
        self._muet = 0                       # profondeur dans un élément à ignorer
        self._rt = 0                         # profondeur dans un <rt>
        # ⚠ Compteur DISTINCT de `_rt` : `<rp>` n'est qu'une parenthèse de repli pour les
        # lecteurs sans ruby, et son contenu doit disparaître dans les DEUX modes. Confondus,
        # le mode « parentheses » sortait `七堕（(ナナエ)）`.
        self._rp = 0
        self._titre: int | None = None       # niveau du <hN> courant
        # LECTURES (furigana) : kanji → kana, collectées SANS toucher au texte rendu.
        # Pas de nouveau mode `ruby:` pour ça — les inliner gonfle la source de 30 % et noie
        # le traducteur (mesuré : 176 210 → 228 967 caractères), alors que le seul agent qui
        # en a besoin est le TERMINOLOGUE, et seulement pour les quelques noms propres d'un
        # bloc. On collecte donc toujours, on n'inline que si `ruby: "parentheses"`.
        self.comptes: dict[str, Counter] = {}
        # Pile de <ruby> imbriqués. Chaque entrée = [parts_base, parts_lecture, paires].
        # Un SEUL <ruby> peut porter PLUSIEURS couples, et il y a DEUX formes très
        # différentes — mesuré sur roman A Vol.1 : 5 472 balises à un seul <rt>, et
        # 2 668 à plusieurs. Voir `_enregistrer_ruby` pour la façon de les distinguer.
        # On apparie à chaque `</rt>`, puis on remet les deux tampons à zéro.
        self._ruby: list[tuple[list[str], list[str], list[tuple[str, str]]]] = []

    # -- gestion de la ligne en cours -------------------------------------- #
    def _clore(self, *, paragraphe: bool = True) -> None:
        """Ferme la ligne en cours. `paragraphe=False` pour un simple retour à la ligne.

        ⚠ La distinction n'est pas cosmétique, c'est elle qui rend la source DÉCOUPABLE.
        `split._paragraphs` ne sépare que sur les lignes VIDES ; tant que les blocs et les
        `<br/>` produisaient tous deux un saut simple, un document XHTML entier ressortait
        en **un seul paragraphe insécable**. Mesuré sur roman B Vol.3 : 20 paragraphes pour
        112 107 caractères, dont un de 40 177 — si bien qu'en alignant la référence japonaise
        sur les blocs du pivot, 43 morceaux sur 54 ressortaient VIDES et les blocs
        correspondants partaient au traducteur sans un mot de japonais."""
        texte = _resoudre_sauts("".join(self._courante)).strip()
        self._courante = []
        if not texte:
            return
        if self._titre:
            texte = f"{'#' * min(self._titre, 6)} {texte}"
            self.a_un_titre = True
        self.lignes.append(texte)
        if paragraphe:
            self.lignes.append("")          # frontière de paragraphe (cf. `texte`)

    def _ecrire(self, texte: str) -> None:
        self._courante.append(texte)

    # -- HTMLParser --------------------------------------------------------- #
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in _MUET:
            self._muet += 1
            return
        if self._muet:
            return

        if tag == "br":
            # ⚠ `paragraphe=False` : un `<br/>` coupe la ligne DANS le paragraphe, il n'en
            # ouvre pas un nouveau. C'est ce qui distingue un vers ou une réplique d'un vrai
            # changement de paragraphe, et le confondre rendrait la source hachée.
            self._clore(paragraphe=False)
            return
        if tag in ("img", "image"):
            src = a.get("src") or a.get("xlink:href") or a.get("href")
            if src:
                marqueur = self.sur_image(src)
                if marqueur:
                    self._clore()
                    self.lignes.append(marqueur)
                    self.lignes.append("")   # le marqueur est un paragraphe à lui seul
            return
        if tag == "ruby":
            self._ruby.append(([], [], []))
            return
        if tag == "rp":
            self._rp += 1
            return
        if tag == "rt":
            self._rt += 1
            if self.ruby == "parentheses":
                self._ecrire("(")
            return
        if tag in _INLINE or tag == "svg":
            return                            # inline : aucun séparateur (cf. docstring)

        # Élément de bloc : il ferme la ligne en cours.
        self._clore()
        if tag in _HEADINGS:
            self._titre = _HEADINGS[tag]

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _MUET:
            self._muet = max(0, self._muet - 1)
            return
        if self._muet:
            return
        if tag == "ruby":
            if self._ruby:
                self._enregistrer_ruby(self._ruby.pop()[2])
            return
        if tag == "rp":
            self._rp = max(0, self._rp - 1)
            return
        if tag == "rt":
            if self.ruby == "parentheses":
                self._ecrire(")")
            self._rt = max(0, self._rt - 1)
            if self._ruby:                   # apparie CETTE lecture à SA base
                base_parts, lec_parts, paires = self._ruby[-1]
                paires.append(("".join(base_parts).strip(), "".join(lec_parts).strip()))
                base_parts.clear()
                lec_parts.clear()
            return
        if tag in _INLINE or tag in ("img", "image", "br", "svg"):
            return
        self._clore()
        if tag in _HEADINGS:
            self._titre = None

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in ("img", "image", "br"):
            self.handle_endtag(tag)

    def _enregistrer_ruby(self, paires: list[tuple[str, str]]) -> None:
        """Enregistre les lectures d'UNE balise `<ruby>`, selon sa forme.

        Deux formes coexistent, et les confondre détruit l'information utile :

        - **ruby par CARACTÈRE** (mono-ruby) — chaque `<rt>` glose UN idéogramme :
          `<ruby>堕<rt>だ</rt>竜<rt>りゆう</rt>講<rt>こう</rt></ruby>`. Les paires isolées
          (`堕`→`だ`) n'apprennent rien sur un nom propre ; c'est le COMPOSÉ qui porte le
          sens, ici `堕竜講` → `だりゆうこう`. Enregistrer les paires séparément le perd.
        - **ruby par MOT** — chaque `<rt>` glose un mot entier, et il peut y en avoir
          plusieurs : `<ruby>千万丈塔<rt>…</rt>踏破儀式<rt>…</rt></ruby>`. Là, concaténer
          fabriquerait la paire fausse « 千万丈塔踏破儀式 ».

        Règle de distinction : toutes les bases font UN caractère → mono-ruby → on
        n'enregistre que le composé. Sinon → on enregistre chaque paire.

        ⚠ C'est le défaut qui a produit les mauvaises romanisations du glossaire de
        roman A Vol.1. `祭花` n'était jamais vu en entier, sa seule lecture de
        groupe étant l'indicatif radio `エナガ一三七` (1 occurrence) — d'où une héroïne
        baptisée « Enaga » au lieu de « Matsurika », dont la lecture まつりか apparaît
        pourtant 388 fois, en mono-ruby. Idem pour 堕竜講, 凜雪, 真神, 鉄機馬, 駆動装甲.
        """
        paires = [(b, l) for b, l in paires if b and l]
        if not paires:
            return
        if all(len(b) == 1 for b, _ in paires):
            paires = [("".join(b for b, _ in paires), "".join(l for _, l in paires))]
        for base, lecture in paires:
            # Une lecture sert à romaniser un NOM : on écarte les bases longues (un ruby
            # posé sur une phrase entière, ça existe) et celles sans idéogramme (gloser du
            # latin n'apprend rien sur un nom propre japonais).
            if len(base) <= 12 and tokens.CJK_TEXTE.search(base):
                self.comptes.setdefault(base, Counter())[lecture] += 1

    def handle_data(self, data):
        if self._muet:
            return
        if self._ruby:                       # capture AVANT les `return` ci-dessous
            if self._rt:
                self._ruby[-1][1].append(data)
            elif not self._rp:
                self._ruby[-1][0].append(data)
        if self._rp:
            return
        if self._rt and self.ruby != "parentheses":
            return
        # Le saut de ligne du fichier source est MARQUÉ, pas tranché : sa valeur dépend de ce
        # qui l'entoure, elle ne peut donc être décidée qu'une fois la ligne complète
        # (cf. `_resoudre_sauts`).
        self._ecrire(re.sub(r"[ \t]*[\r\n]+[ \t]*", _SAUT, data))

    def close(self):                     # noqa: D102 - hérité
        super().close()
        self._clore()


# --------------------------------------------------------------------------- #
# Choix du titre d'un document
# --------------------------------------------------------------------------- #

_DEFAUTS = {"ruby": "ignorer", "titre_max_caracteres": 40}


def titrer(doc: DocumentEpub, label_toc: str | None, titre_max: int) -> None:
    """Donne un titre au document s'il n'en a pas déjà un, **en place**.

    Ordre : `<hN>` (déjà fait par l'analyseur) → intitulé de la table des matières → première
    ligne courte suivie de texte. Un document sans titre retenu ne devient pas un chapitre :
    son texte prolonge le précédent — c'est ce qui évite de faire un « chapitre » de chaque
    page d'illustration ou de chaque épigraphe de deux lignes."""
    if doc.a_un_titre or not doc.lignes:
        return
    if label_toc:
        doc.lignes.insert(0, f"# {label_toc}")
        doc.a_un_titre = True
        return
    # ⚠ Les frontières de paragraphe (entrées vides posées par `_Analyseur._clore`) sont
    # écartées ICI. Les compter ferait passer un document d'UN seul paragraphe pour un
    # document de deux lignes — donc un candidat au titrage — et chaque page d'illustration
    # ou d'épigraphe redeviendrait un chapitre, ce que les deux gardes ci-dessous existent
    # précisément pour empêcher.
    corps = [ln for ln in doc.lignes if ln and not ln.startswith("<!-- IMG:")]
    if len(corps) < 2:
        return                  # une seule ligne : c'est le contenu, pas un intitulé
    premiere = corps[0]
    if len(premiere) > titre_max or premiere.startswith("#"):
        return
    # Un titre est court RELATIVEMENT à ce qu'il annonce. Sans ce rapport, l'épigraphe de deux
    # lignes qui ouvre ce tome (un waka de 45 signes suivi de son attribution, 13 signes)
    # devenait un « chapitre » de 13 caractères — donc une unité de traitement, un appel LLM et
    # un titre parasite dans le rendu. La borne absolue `titre_max` seule ne l'attrape pas.
    if sum(len(ln) for ln in corps[1:]) < 2 * len(premiere):
        return
    i = doc.lignes.index(premiere)
    doc.lignes[i] = f"# {premiere}"
    doc.a_un_titre = True


# --------------------------------------------------------------------------- #
# Point d'entrée
# --------------------------------------------------------------------------- #

def _analyser_document(z, idref: str, item: dict, toc_href: str, noms: set[str],
                       *, ruby: str, sur_image) -> DocumentEpub | None:
    """UN document du spine, analysé. `None` s'il n'a pas sa place dans le texte du tome."""
    href = item["href"]
    if href == toc_href or "nav" in item["properties"].split():
        return None                      # document de navigation : jamais du texte
    if href not in noms:
        return None
    base = posixpath.dirname(href)
    analyseur = _Analyseur(ruby=ruby, sur_image=lambda s: sur_image(s, base))
    try:
        analyseur.feed(_texte_xml(z.read(href)))
        analyseur.close()
    except Exception:
        # Un document mal formé ne doit pas faire échouer tout le tome : on garde ce qui a
        # été analysé avant l'incident et on continue.
        pass
    if not analyseur.lignes:
        return None
    doc = DocumentEpub(idref=idref, href=href)
    doc.lignes = analyseur.lignes
    doc.a_un_titre = analyseur.a_un_titre
    doc.comptes = analyseur.comptes
    return doc


def _fusionner_comptes(documents: list[DocumentEpub]) -> dict[str, Counter]:
    """Lectures fusionnées sur tout le spine : un nom propre glosé une seule fois, à sa
    première occurrence, doit rester disponible pour les chapitres suivants — c'est la
    convention des EPUB japonais, qui ne re-glosent pas à chaque page."""
    comptes: dict[str, Counter] = {}
    for d in documents:
        for base, c in d.comptes.items():
            comptes.setdefault(base, Counter()).update(c)
    return comptes


def extract_epub(path: Path, media_dir: Path, extract_images: bool = True,
                 epub_cfg: dict | None = None) -> Extracted:
    """Extrait un EPUB en markdown-léger, images comprises. Voir la docstring du module."""
    cfg = {**_DEFAUTS, **{k: v for k, v in (epub_cfg or {}).items() if v is not None}}
    ruby = str(cfg["ruby"])
    titre_max = int(cfg["titre_max_caracteres"])
    path = Path(path)
    prefixe = re.sub(r"\W+", "_", path.stem).strip("_") or "epub"

    with zipfile.ZipFile(path) as z:
        opf = chemin_opf(z)
        manifeste, spine, toc_href = lire_opf(_texte_xml(z.read(opf)), posixpath.dirname(opf))
        toc = lire_toc(z, toc_href)
        noms = set(z.namelist())
        if extract_images:
            media_dir.mkdir(parents=True, exist_ok=True)

        images: list[str] = []
        vues: dict[str, str] = {}            # href dans le zip → marqueur (dédoublonnage)

        def _faire_image(src: str, base: str) -> str:
            if not extract_images:
                return ""
            cible = posixpath.normpath(posixpath.join(base, _deshtml(src).split("#")[0]))
            if cible in vues:
                return vues[cible]           # même illustration réutilisée : un seul fichier
            if cible not in noms:
                return ""
            rel = f"media/{prefixe}_{posixpath.basename(cible)}"
            (media_dir / Path(rel).name).write_bytes(z.read(cible))
            marqueur = make_marker(rel)
            vues[cible] = marqueur
            images.append(rel)
            return marqueur

        documents = [d for d in (
            _analyser_document(z, idref, manifeste[idref], toc_href, noms,
                               ruby=ruby, sur_image=_faire_image)
            for idref in spine) if d is not None]
        for doc in documents:
            titrer(doc, toc.get(doc.href), titre_max)

    texte = "\n\n".join(d.texte for d in documents if d.texte)
    return Extracted(text=texte, images=images,
                     lectures=lecture_dominante(_fusionner_comptes(documents)))
