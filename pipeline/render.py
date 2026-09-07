# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Rendu : Markdown canonique → .docx / .epub / .pdf via Pandoc.

Convertit d'abord les marqueurs `<!-- IMG: media/x.png -->` en images Markdown,
puis lance Pandoc depuis le dossier de build pour que les chemins `media/...`
soient résolus.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from core.langues import resoudre_pack

from . import typographie as ty
from core.version import __version__

from .images import markers_to_markdown

# ⚠ Le bloc d'attributs s'écrivait `\{[^}]*\.dialogue[^}]*\}` : DEUX quantificateurs
# illimités de part et d'autre d'un littéral. Sur une fence `{...}` longue qui ne contient
# pas `.dialogue`, le moteur réessaie chaque point de coupure avant d'abandonner — coût
# quadratique en la longueur des attributs, et à chaque position de départ du document. Le
# `.dialogue` est vérifié par une ANTICIPATION (qui ne consomme rien, donc n'a rien à
# redistribuer), et un seul `[^}]*\}` consomme ensuite le bloc de façon déterministe.
_DIALOGUE_BLOCK = re.compile(
    r'(:::+\s*\{(?=[^}]*\.dialogue)[^}]*\}\s*\n)(.*?)(\n:::+)', re.DOTALL)
_FENCE_LINE = re.compile(r'^:{2,}(\s*\{[^}]*\})?\s*$')
# Fence écrite EN LIGNE : ouverture + attributs + texte + fermeture, le tout sur la
# même ligne/paragraphe séparés par des espaces au lieu de retours à la ligne (motif
# observé en pratique : le modèle recopie le gabarit sans lui donner sa structure sur
# 3 lignes — invisible pour Pandoc, qui exige que chaque partie soit sur SA PROPRE ligne).
_INLINE_FENCE = re.compile(
    r':{2,}\s*(\{\.[a-zA-Z]+(?:\s+custom-style="[^"]*")?\})\s*(.*?)\s*:{2,}', re.DOTALL)
# Un bloc d'attributs Pandoc qui traîne seul, sans fence autour (fermeture jamais
# trouvée, ou tout autre reliquat) : du bruit pur pour Pandoc → à supprimer.
_ORPHAN_ATTR = re.compile(r'\{\.[a-zA-Z]+(?:\s+custom-style="[^"]*")?\}')


# Paragraphe qui n'est QU'UN marqueur d'image (avec ou sans attributs de taille) : il ne
# relève d'aucun filtre de prose. Cf. `_collapse_repetitions`.
_IMG_ONLY = re.compile(r'^\s*<!-- IMG: .*? -->\s*$', re.DOTALL)
# Comptage des marqueurs, pour le contrôle « aucune image perdue en route » de `render`.
_MARKER_COUNT_RE = re.compile(r'<!-- IMG: .*? -->')

_CORRECTION_ANNOTATION = re.compile(r'\s*\(\s*[Cc]orrection\s*:[^)]*\)\.?')

_GLOSSARY_SECTION = re.compile(
    r'(?ms)^#+\s*(?:Personnages|Lieux|Organisations|Créatures|Objets|Termes)\b.*?'
    r'(?=^#\s|\Z)')


def _strip_leaked_glossary(md: str) -> str:
    """Dernier filet : retire un bloc de glossaire qui aurait fui dans le texte (un agent
    l'a régurgité et le checkpoint corrompu a été mis en cache). On procède ligne par
    ligne : on retire les titres de section de glossaire ET les lignes d'entrée
    « - Nom [tag] — … » / « - Nom — … (variantes : …) », UNIQUEMENT quand on est dans une
    zone dense en telles entrées (pour ne pas toucher une liste à puces normale du récit)."""
    lines = md.splitlines()
    # Repère les lignes "entrée de glossaire" : « [Nom] [tag] — description » ou
    # « - Nom — … (variantes : …) ». Le tiret de puce est OPTIONNEL (le format observé
    # n'en a pas toujours), mais on exige le tiret cadratin « — » ET un tag/mention.
    is_entry = [bool(re.match(r'\s*-?\s*.+?\s+—\s', ln)) and
                bool(re.search(r'\[(?:masculin|féminin|\?|FORCÉ|NE PAS TRADUIRE)[^\]]*\]'
                               r'|\(variantes\s*:|mot\(s\) source', ln))
                for ln in lines]
    is_glo_title = [bool(re.match(r'\s*#+\s*(?:Personnages|Lieux|Organisations|Créatures|'
                                  r'Objets|Termes|GLOSSAIRE)\b', ln, re.I)) for ln in lines]
    # Une ligne est "à retirer" si c'est une entrée de glossaire, ou un titre de section
    # de glossaire suivi (dans les 3 lignes) d'au moins une entrée.
    remove = [False] * len(lines)
    for i, ln in enumerate(lines):
        if is_entry[i]:
            remove[i] = True
        elif is_glo_title[i] and any(is_entry[j] for j in range(i + 1, min(i + 4, len(lines)))):
            remove[i] = True
    if not any(remove):
        return md
    kept = [ln for i, ln in enumerate(lines) if not remove[i]]
    # Nettoie les lignes vides multiples laissées par le retrait.
    out = re.sub(r'\n{3,}', '\n\n', "\n".join(kept))
    return out


def _strip_leaked_style_guide(md: str, guide_lines: list[str]) -> str:
    """Filet : retire un morceau du GUIDE DE STYLE régurgité par un agent (motif observé
    en prod — le 9B recopie « # Guide de style — conventions générales de traduction »,
    parfois des sections entières, en tête de bloc). On retire toute ligne du texte qui
    correspond EXACTEMENT à une ligne substantielle du guide (≥12 caractères), plus toute
    ligne de titre « # Guide de style … » par sécurité. Une ligne de récit ne coïncide pas
    au caractère près avec une consigne du guide, donc aucun risque pour la prose."""
    md = re.sub(r'(?im)^#{1,6}\s*Guide de style\b.*$', '', md)
    guide = {ln.strip() for ln in guide_lines if len(ln.strip()) >= 12}
    if guide:
        md = "\n".join(ln for ln in md.splitlines() if ln.strip() not in guide)
    return re.sub(r'\n{3,}', '\n\n', md).strip()


def _collapse_repetitions(md: str) -> str:
    """Filet contre une DÉGÉNÉRESCENCE en boucle du modèle : un cycle de paragraphes
    (souvent un échange de dialogue) répété en boucle. Motif réel observé (Vol.3 ch01) : le
    traducteur 9B a bouclé 12× sur le même passage, non détecté par les garde-fous de
    longueur (chaque étage restait sous son plafond proportionnel à l'entrée). On effondre
    tout cycle de paragraphes SUBSTANTIELS (≥80 caractères au total) répété ≥2 fois de suite
    à UNE seule occurrence. Les répétitions courtes légitimes (« *Clang.* », « Oui. ») sont
    préservées (sous le seuil).

    ⚠ Un paragraphe qui n'est QU'UN MARQUEUR D'IMAGE est exempté : ce n'est jamais une
    boucle du modèle. Un séparateur de scène revient légitimement des dizaines de fois
    dans un tome, et le marqueur porte ses dimensions Pandoc
    (`|{width="0.11624890638670166in" height="0.22125in"}`), ce qui le faisait franchir
    le seuil des 80 caractères pour la seule raison de la précision des flottants — il
    était donc effondré à UNE occurrence. Mesuré sur roman B Vol.2 : 28 séparateurs
    dans le Markdown assemblé, 5 après ce filtre. C'est la NATURE du paragraphe qui
    l'exempte, pas sa longueur : relever le seuil ne réglerait rien (un `width:` un peu
    plus précis repasserait au-dessus)."""
    def norm(p: str) -> str:      # clé de comparaison : ignore balises/guillemets/emphase
        return re.sub(r'[\s«»*_:]+', ' ', p).strip().lower()

    def substantiel(p: str) -> int:
        """Longueur qui compte pour le seuil : un marqueur d'image pèse 0."""
        return 0 if _IMG_ONLY.match(p) else len(p)

    paras = re.split(r'\n[ \t]*\n', md)
    keys = [norm(p) for p in paras]
    # 1) Effondre les cycles de paragraphes SUBSTANTIELS répétés consécutivement.
    out: list[str] = []
    i, n = 0, len(paras)
    while i < n:
        collapsed = False
        for k in range(1, (n - i) // 2 + 1):
            cycle = keys[i:i + k]
            # Un cycle fait uniquement d'images pèse 0 → jamais effondré. Un cycle de
            # prose (avec ou sans image au milieu) reste détecté comme avant.
            if sum(substantiel(p) for p in paras[i:i + k]) < 80:
                continue
            reps, j = 1, i + k
            while j + k <= n and keys[j:j + k] == cycle:
                reps += 1
                j += k
            if reps >= 2:
                out.extend(paras[i:i + k])       # une seule occurrence du cycle
                i = j
                collapsed = True
                break
        if not collapsed:
            out.append(paras[i])
            i += 1
    # 2) Dédoublonne les paragraphes substantiels qui REVIENNENT ≥3 fois (boucle propagée
    #    entre blocs / sous deux formes) : on ne garde que la 1re occurrence.
    #    Les marqueurs d'image en sont exclus (cf. docstring).
    okeys = [norm(p) for p in out]
    from collections import Counter
    frequent = {k for k, c in Counter(k for p, k in zip(out, okeys)
                                      if len(k) >= 80 and not _IMG_ONLY.match(p)).items()
                if c >= 3}
    if frequent:
        seen: set[str] = set()
        deduped = []
        for p, k in zip(out, okeys):
            if k in frequent:
                if k in seen:
                    continue
                seen.add(k)
            deduped.append(p)
        out = deduped
    return "\n\n".join(out)


def _strip_correction_annotations(md: str) -> str:
    """Garde-fou contre un agent (cohérence, le plus souvent) qui narre sa propre
    correction EN PLEIN TEXTE au lieu de la mettre dans son rapport séparé — motif
    observé en production : « Le bogard s'assombrit. (Correction : "bogard" au lieu
    de "boggard"). » L'explication n'a aucune valeur pour le lecteur final ; on la
    retire silencieusement (elle reste, elle, visible dans RAPPORT.md)."""
    return _CORRECTION_ANNOTATION.sub('', md)


def _normalize_fences(md: str) -> str:
    """Garde-fou contre les fences Pandoc mal formées que le 9B produit parfois :
    1. une fence écrite EN LIGNE (ouverture + texte + fermeture sur la même ligne,
       séparés par des espaces au lieu de retours à la ligne) est reconstruite en
       bonne et due forme sur 3 lignes — sinon Pandoc l'ignore silencieusement et le
       `{.dialogue custom-style="..."}` ressort littéralement dans le document final ;
    2. une ligne ENTIÈREMENT faite de « : » (+ attributs `{...}` éventuels) est une
       fence légitime → normalisée à exactement `:::` (peu importe si le modèle a
       écrit `::::` ou `::`), pour que l'ouverture et la fermeture matchent toujours ;
    3. toute suite de 2+ « : » qui apparaît AILLEURS dans une ligne (le modèle a parfois
       inventé un « ::: » ou un « :: » EN PLEIN MILIEU d'une phrase, en essayant
       d'envelopper une réplique intégrée à la narration) est une hallucination sans
       rapport avec Pandoc → supprimée, sans toucher au reste de la phrase ;
    4. un bloc d'attributs `{.dialogue ...}` orphelin (fermeture jamais trouvée par
       l'étape 1) est un dernier reliquat → supprimé lui aussi."""
    def _reformat(m: re.Match) -> str:
        attrs, content = m.group(1), m.group(2).strip()
        return f"\n\n::: {attrs}\n{content}\n:::\n\n"
    md = _INLINE_FENCE.sub(_reformat, md)

    out = []
    for line in md.splitlines():
        m = _FENCE_LINE.match(line)
        if m:
            out.append(':::' + (m.group(1) or ''))
        else:
            cleaned = re.sub(r':{2,}', '', line)
            cleaned = _ORPHAN_ATTR.sub('', cleaned)   # reliquat SANS fence légitime sur cette ligne
            out.append(cleaned)
    return '\n'.join(out)


_CUSTOM_STYLE_BLOCK = re.compile(
    r':{3,}\s*\{\.[a-zA-Z]+\s+custom-style="([^"]*)"\}\s*\n(.*?)\n:{3,}', re.DOTALL)


def _sanitize_custom_styles(md: str, valid_styles: set[str]) -> str:
    """Garde-fou : un agent (mise en page, le plus souvent) invente parfois un nom de
    custom-style qui ne correspond à AUCUN style réellement défini dans reference.docx
    — motif observé en prod (roman B Vol.3) : `custom-style="Corps de texte"`, le nom
    AFFICHÉ dans Word, alors que le style existant s'appelle en interne « Body Text »
    (`w:name`). Pandoc, ne trouvant pas de correspondance exacte par nom, crée un
    NOUVEAU style — mais avec le MÊME styleId sanitisé que le vrai « Corps de texte »,
    d'où un styleId DUPLIQUÉ dans styles.xml qui corrompt le rendu de TOUS les
    paragraphes de narration du document, pas seulement le bloc fautif. On désamorce ça
    en amont : un bloc dont le custom-style ne fait pas partie des styles connus
    (`rendu.styles` de `config.yaml`) est déballé en texte simple (paragraphe normal,
    sans wrapper ``:::``) plutôt que transmis tel quel à Pandoc."""
    def repl(m: re.Match) -> str:
        if m.group(1) in valid_styles:
            return m.group(0)
        return m.group(2).strip()
    return _CUSTOM_STYLE_BLOCK.sub(repl, md)


# Les règles typographiques de la langue CIBLE vivent désormais dans
# `pipeline/typographie.py` : elles sont COMPILÉES PAR RUN depuis le pack, et ne
# peuvent donc plus être des constantes de module. `ty.DEFAUT` porte les valeurs
# françaises d'origine, pour les appelants qui n'ont pas de pack sous la main.
#
# ⚠ Le lexique des verbes de parole est le cas qui a commandé le déplacement : ce
# n'est pas un caractère à paramétrer mais une CONSTRUCTION de langue, que l'anglais
# n'a pas (`"...," he said`, sans inversion). Un pack peut donc dire « je n'en ai
# pas », et le rendu n'essaie alors pas de coller d'incise.


def _is_spoken(inner: str) -> bool:
    """Distingue une RÉPLIQUE (dialogue) d'un simple TERME CITÉ en pleine narration
    (« Leprechauns », « Arme Enchantée »). Une réplique est une phrase : elle finit par
    une ponctuation de fin (. ! ? …), OU compte ≥3 mots, OU est longue. Un terme cité est
    court et sans ponctuation finale → on le LAISSE dans la narration (pas de découpe)."""
    inner = inner.strip()
    if not inner:
        return False
    if inner[-1] in '.!?…':
        return True
    if len(inner.split()) >= 3:
        return True
    return len(inner) >= 20


def _segment_text(text: str, style: str, typo=None) -> list[str] | None:
    """Découpe un texte qui MÊLE répliques « … » et narration en une liste de blocs :
    chaque réplique → un bloc `.dialogue` (guillemets retirés) sur SON PROPRE paragraphe ;
    chaque portion de narration → un paragraphe simple (les termes cités « … » y restent,
    cf. `_is_spoken`). Renvoie None si le texte ne contient aucune réplique.

    EXCEPTION (incise d'attribution) : si le récit qui SUIT immédiatement une réplique
    commence par un verbe de parole/pensée (« dit-il », « hurla-t-elle », « pensa »…), il
    reste COLLÉ à la réplique dans le même bloc dialogue, jusqu'à la fin de phrase
    (; . ! ? …). Le reste repart en narration."""
    typo = typo or ty.DEFAUT
    spans = []
    for m in typo.dialogue_span.finditer(text):
        if not _is_spoken(m.group(1)):
            continue
        # RÉPLIQUE AUTONOME seulement si ce qui précède le « est vide ou termine une phrase
        # (. ! ? … :). Sinon c'est une CITATION au fil d'une phrase (« appris que ‹…› »,
        # « d'‹…› ») → laissée dans la narration au lieu de couper la phrase en morceaux.
        before = text[:m.start()].rstrip()
        if before and before[-1] not in '.!?…:':
            continue
        spans.append(m)
    if not spans:
        return None
    seg: list[tuple[str, str]] = []          # ('d', réplique) | ('n', narration)

    def emit_narration(txt: str) -> None:
        txt = txt.strip()
        if not txt:
            return
        # Un fragment qui n'est QUE de la ponctuation (un « . » resté seul après le » d'une
        # réplique, cf. « … ciel… ».) ne doit pas devenir un paragraphe : on le recolle à la
        # réplique précédente, sinon on le jette.
        if re.fullmatch(r'[.,;:!?…«»\s]+', txt):
            if seg and seg[-1][0] == 'd':
                p = txt.replace('«', '').replace('»', '').strip()
                if p and seg[-1][1][-1:] not in ('.', '!', '?', '…'):
                    seg[-1] = ('d', seg[-1][1] + p)
            return
        seg.append(('n', txt))

    pos = 0
    for i, m in enumerate(spans):
        emit_narration(text[pos:m.start()])                     # narration avant/entre répliques
        reply = m.group(1).strip()
        after_end = spans[i + 1].start() if i + 1 < len(spans) else len(text)
        after = text[m.end():after_end]
        consumed = 0
        # 1) Ponctuation de fin juste APRÈS le » (hors guillemets) → rattachée à la réplique
        #    (« Bonjour ». → « Bonjour. »), pour ne pas laisser un point orphelin.
        pm = re.match(r'\s*([.,;:!?…]+)', after)
        if pm:
            if reply[-1:] not in ('.', '!', '?', '…'):
                reply += pm.group(1)
            consumed = pm.end()
        # 2) Incise d'attribution (« dit-il », « hurla-t-elle »…) : reste dans le bloc
        #    dialogue jusqu'à la fin de phrase.
        head = after[consumed:].lstrip()
        if typo.verbes_de_parole is not None and typo.verbes_de_parole.match(head):
            lead = len(after[consumed:]) - len(head)
            se = typo.fin_de_phrase.search(head)
            if se:
                reply = f"{reply} {head[:se.end()].strip()}"
                consumed += lead + se.end()
            else:
                reply = f"{reply} {head.strip()}"
                consumed = len(after)
        seg.append(('d', reply))
        pos = m.end() + consumed
    emit_narration(text[pos:])
    return [f'::: {{.dialogue custom-style="{style}"}}\n{t}\n:::' if k == 'd' else t
            for k, t in seg]


def _segment_dialogues(md: str, style: str, typo=None) -> str:
    """Filet déterministe de détection/catégorisation des dialogues (le 9B est
    imparfait) : chaque réplique « … » devient un bloc `.dialogue` INDÉPENDANT, la
    narration reste en paragraphe simple (avec l'exception de l'incise d'attribution, cf.
    `_segment_text`). Corrige le cas réel « ‹réplique› narration ‹réplique› » que le
    modèle enveloppait EN ENTIER dans un seul bloc dialogue (d'où un » survivant au milieu
    et une narration mal catégorisée).

    Traite AUSSI le contenu des blocs déjà balisés (`:::`) : un bloc dont le contenu mêle
    réplique + narration est ré-éclaté ; un bloc contenant une réplique PROPRE unique
    (tout le contenu = « … », rien autour) est laissé intact — ce qui préserve son style
    d'origine (p.ex. Pensée) et laisse la conversion retirer les « ». On ne touche pas aux
    titres (`#`) ni aux marqueurs (`<!-- … -->`).

    À exécuter APRÈS `_normalize_fences` (fences propres) et AVANT
    `_strip_dialogue_dashes`/`_strip_dialogue_quotes`."""
    typo = typo or ty.DEFAUT
    chunks = re.split(r'\n[ \t]*\n', md)
    out: list[str] = []
    for ch in chunks:
        s = ch.strip()
        if not s or s.startswith('#') or s.startswith('<!--'):
            out.append(ch)
            continue
        # Chunk réduit à de la ponctuation « faible » (un « . » / « , » resté seul après
        # une réplique) → artefact : on le supprime (on garde en revanche les beats « … »,
        # « ? », « ! » qui peuvent être un paragraphe intentionnel).
        if re.fullmatch(r'[.,;:«»\s]+', s):
            continue
        fm = re.match(r'^:{3,}\s*\{[^}]*\}\s*\n(.*?)\n:{3,}\s*$', s, re.DOTALL)
        if fm:
            content = fm.group(1).strip()
            # Réplique PROPRE et unique (tout le bloc = « … », aucun autre guillemet) →
            # bloc d'origine inchangé (garde le style, p.ex. Pensée ; la conversion ôtera
            # les « »). Sinon on ré-éclate le contenu.
            if (content.startswith('«') and content.endswith('»')
                    and content.count('«') == 1 and content.count('»') == 1):
                out.append(ch)
                continue
            parts = _segment_text(content, style, typo)
            out.append(ch if parts is None else "\n\n".join(parts))
            continue
        parts = _segment_text(s, style, typo)
        out.append("\n\n".join(parts) if parts else ch)
    return "\n\n".join(out)


def _strip_dialogue_dashes(md: str) -> str:
    """Retire un tiret de réplique en tête de chaque bloc dialogue : le style Word
    « Paragraphe de liste » (et le CSS EPUB) l'ajoutent automatiquement, donc le
    laisser dans le texte produit un DOUBLE tiret (« — — … »)."""
    def repl(m: re.Match) -> str:
        content = re.sub(r'^\s*[—–\-]\s*', '', m.group(2).lstrip('\n'))
        return m.group(1) + content + m.group(3)
    return _DIALOGUE_BLOCK.sub(repl, md)


def _strip_dialogue_quotes(md: str) -> str:
    """Retire les guillemets français « » qui ENCADRENT une réplique DANS un bloc
    dialogue, au rendu seulement (le .md source les garde, pour une relecture claire).
    Le style « dialogue » marque déjà visuellement la réplique (tiret + retrait), donc
    les guillemets y sont redondants dans le document final. On ne touche QU'aux blocs
    dialogue : les guillemets en pleine narration (citation, titre cité…) sont préservés."""
    def repl(m: re.Match) -> str:
        content = m.group(2)
        # Retire un « en tête et un » en fin de la réplique (avec espaces éventuels),
        # y compris après un tiret déjà présent. Ne touche pas aux guillemets internes.
        content = re.sub(r'(^|\n)(\s*[—–\-]?\s*)«\s*', r'\1\2', content)
        content = re.sub(r'\s*»(\s*)(\n|$)', r'\1\2', content)
        return m.group(1) + content + m.group(3)
    return _DIALOGUE_BLOCK.sub(repl, md)


def _chemin(bloc, cle: str) -> Path | None:
    """Un chemin EXPLICITEMENT posé dans `config`, ou `None`.

    ⚠ La config PRIME sur le pack, et c'est délibéré. `rendu.reference_docx` est calé sur le
    document de l'utilisateur ; si le pack l'emportait, une faute de frappe dans ce chemin
    serait silencieusement masquée par le gabarit du pack — et le doctor la déclarerait
    saine. Le pack fournit le DÉFAUT (clé vide), pas l'autorité."""
    valeur = (bloc or {}).get(cle)
    return Path(str(valeur)) if valeur else None


#: Un élément `<w:style …>…</w:style>`, attributs et corps séparés.
#:
#: ⚠ Le motif tenait en une seule passe — `<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>` — soit,
#: là encore, deux quantificateurs illimités autour d'un littéral : `styles.xml` porte des
#: listes d'attributs longues, et chaque élément sans `w:styleId` faisait réessayer toutes
#: les coupures. Découper en DEUX motifs supprime l'ambiguïté au lieu de la déplacer :
#: `[^>]*>` est déterministe, et l'identifiant se cherche ensuite dans la seule chaîne
#: d'attributs, qui est courte.
_STYLE_ELEMENT = re.compile(r'<w:style\b([^>]*)>(.*?)</w:style>', re.DOTALL)
_STYLE_ID = re.compile(r'w:styleId="([^"]+)"')


def _narration_style_id(reference_docx: Path) -> str:
    """styleId de la narration dans le reference.docx (celui nommé « Body Text »)."""
    try:
        with zipfile.ZipFile(reference_docx) as z:
            st = z.read("word/styles.xml").decode("utf-8")
        for m in _STYLE_ELEMENT.finditer(st):
            if '<w:name w:val="Body Text"' not in m.group(2):
                continue
            identifiant = _STYLE_ID.search(m.group(1))
            # Un style « Body Text » SANS `w:styleId` ne peut pas être désigné : on continue
            # de chercher, comme le faisait l'ancien motif qui ne l'appariait simplement pas.
            if identifiant:
                return identifiant.group(1)
    except Exception:
        pass
    return "Corpsdetexte"


def _center_image_paragraphs(doc_xml: str) -> str:
    """Centre chaque paragraphe qui contient une image (`<w:drawing>`) dans le .docx —
    sinon une image insérée dans un paragraphe « Corps de texte » justifié reste collée à
    gauche. Concerne surtout les petites illustrations de séparation (ornements ~3 mm),
    mais centrer aussi les pleines pages est sans effet indésirable. Le `<w:jc>` est
    inséré JUSTE APRÈS le `<w:pStyle>` (ordre du schéma OOXML : pStyle puis jc)."""
    def repl(m: re.Match) -> str:
        p = m.group(0)
        if "<w:drawing" not in p:
            return p
        if re.search(r'<w:jc\b[^>]*/>', p):                       # déjà une justification → force le centre
            return re.sub(r'<w:jc\b[^>]*/>', '<w:jc w:val="center"/>', p, count=1)
        if re.search(r'<w:pStyle\b[^>]*/>', p):                   # insère après le style de paragraphe
            return re.sub(r'(<w:pStyle\b[^>]*/>)', r'\1<w:jc w:val="center"/>', p, count=1)
        if '<w:pPr>' in p:                                        # pPr sans style → au début du pPr
            return p.replace('<w:pPr>', '<w:pPr><w:jc w:val="center"/>', 1)
        return re.sub(r'(<w:p\b[^>]*>)', r'\1<w:pPr><w:jc w:val="center"/></w:pPr>', p, count=1)  # aucun pPr
    return re.sub(r'<w:p\b.*?</w:p>', repl, doc_xml, flags=re.DOTALL)


def _normalize_docx(docx_path: Path, narration_id: str) -> None:
    """Élimine les styles parasites injectés par Pandoc (ex. « Compact ») : on les
    remappe sur la narration et on retire leur définition orpheline.
    NB : « FirstParagraph » n'est PLUS un parasite — Pandoc l'applique au 1er paragraphe
    de chaque chapitre (celui qui suit le titre), et le reference.docx lui donne le
    retrait de 1re ligne. C'est justement le SEUL paragraphe qui doit être décalé
    (charte Vol.1) ; on le laisse donc intact au lieu de le rabattre sur « Corps de texte ».
    Les images gardent la taille définie par leur marqueur (aucun redimensionnement)."""
    parasites = ["Compact"]
    with zipfile.ZipFile(docx_path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}

    doc = data["word/document.xml"].decode("utf-8")
    for p in parasites:
        doc = doc.replace(f'w:val="{p}"', f'w:val="{narration_id}"')
    doc = _center_image_paragraphs(doc)
    data["word/document.xml"] = doc.encode("utf-8")

    if "word/styles.xml" in data:
        st = data["word/styles.xml"].decode("utf-8")
        for p in parasites:
            st = re.sub(rf'<w:style\b[^>]*w:styleId="{p}".*?</w:style>', "", st, flags=re.DOTALL)
        data["word/styles.xml"] = st.encode("utf-8")

    tmp = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, data[n])
    tmp.replace(docx_path)


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(cwd))
    if proc.returncode != 0:
        raise RuntimeError(f"Pandoc a échoué :\n{' '.join(cmd)}\n{proc.stderr}")


def render(markdown_path: Path, out_dir: Path, config: dict,
           warn=None, stats: dict | None = None) -> list[Path]:
    """Markdown assemblé → .docx / .epub / .pdf.

    `warn` (optionnel) : callback appelé sur tout incident non fatal — typiquement
    `reporter.warn`, pour que la ligne atterrisse aussi dans perf.log. `stats`
    (optionnel) : dict rempli avec `images_markdown` / `images_rendu`, le nombre de
    marqueurs d'image AVANT et APRÈS la chaîne de filtres. Les deux sont facultatifs :
    les appelants existants (`--render-only`) ne changent pas."""
    if shutil.which("pandoc") is None:
        raise RuntimeError("Pandoc introuvable : https://pandoc.org/installing.html")

    markdown_path = Path(markdown_path)
    out_dir = Path(out_dir)
    r = config["rendu"]
    meta = r["metadata"]
    formats = r["formats"]
    stem = markdown_path.stem

    # Lignes du guide de style (pour retirer un guide régurgité par un agent, cf. plus bas).
    pack = resoudre_pack(config)
    # Repli côté BRIQUE : ces trois artefacts sont propres au light novel, leurs clés de
    # config n'ont rien à faire dans `core/` (cf. `core.langues.Pack.fichier`).
    sg_path = _chemin(config.get("chemins"), "style_guide") or pack.fichier("style_guide.md")
    sg_lines = sg_path.read_text(encoding="utf-8").splitlines() if sg_path and sg_path.exists() else []

    # md temporaire avec images Markdown, dans out_dir (pour résoudre media/…)
    rendered_md = out_dir / f"{stem}.render.md"
    md_text = markdown_path.read_text(encoding="utf-8")
    n_img_avant = len(_MARKER_COUNT_RE.findall(md_text))
    md_text = _strip_leaked_glossary(md_text)      # filet : glossaire régurgité dans le texte
    md_text = _strip_leaked_style_guide(md_text, sg_lines)  # filet : guide de style régurgité
    md_text = _collapse_repetitions(md_text)       # filet : dégénérescence en boucle du modèle
    md_text = _normalize_fences(md_text)          # garde-fou :: / :::: mal formées
    # Styles et règles typographiques du PACK DE LANGUE CIBLE, la config gardant la main
    # (cf. `typographie.Typographie.depuis_pack` : `rendu.styles` est calé sur le
    # `reference.docx` de l'utilisateur, un pack ne doit pas le lui reprendre).
    typo = ty.Typographie.depuis_pack(pack, r)
    valid_styles = set(typo.styles_word.values())
    md_text = _sanitize_custom_styles(md_text, valid_styles)  # garde-fou : nom de style halluciné/introuvable
    md_text = _segment_dialogues(md_text, typo.styles_word["dialogue"], typo)  # détection/catégorisation des dialogues
    md_text = _strip_correction_annotations(md_text)   # garde-fou annotations inline "(Correction: ...)"
    # Retire les titres purement numériques (« ## 1 », « ## 3 ») : ce sont des numéros
    # de section de la source, redondants avec le titre qui suit.
    md_text = re.sub(r'(?m)^#{2,}\s*\d+\s*$\n?', '', md_text)
    if not typo.tiret_dans_le_texte:
        md_text = _strip_dialogue_dashes(md_text)   # évite le double tiret « — — »
    if r.get("strip_dialogue_quotes", True):
        md_text = _strip_dialogue_quotes(md_text)   # « » redondants dans les blocs dialogue
    # Contrôle « aucune image perdue en route » : un filtre de prose ne doit jamais
    # supprimer un marqueur d'image. C'est l'absence de ce contrôle qui a laissé passer
    # plusieurs tomes amputés de leurs séparateurs de scène (`_collapse_repetitions`
    # prenait un séparateur répété pour une boucle du modèle).
    n_img_apres = len(_MARKER_COUNT_RE.findall(md_text))
    if stats is not None:
        stats["images_markdown"] = n_img_avant
        stats["images_rendu"] = n_img_apres
    if n_img_apres < n_img_avant and callable(warn):
        warn(f"[rendu] {n_img_avant - n_img_apres} marqueur(s) d'image supprimé(s) par les "
             f"filtres de nettoyage ({n_img_avant} → {n_img_apres}) — images manquantes "
             f"dans le .docx/.epub/.pdf")
    # Les images conservent leur taille d'origine (mémorisée dans le marqueur) : une petite
    # illustration de séparation (~3 cm) reste petite, une pleine page reste pleine page.
    # Empreinte de version DANS les fichiers livrés : un .docx qui circule seul, séparé de
    # son build/ et de son RAPPORT.md, doit encore dire quelle version l'a produit.
    # Passe par un bloc YAML en tête du .render.md, et NON par `--metadata`, après mesure
    # sur Pandoc 3.10 :
    #  · `--metadata keywords="…"` est SILENCIEUSEMENT ignoré par le writer docx, qui attend
    #    une LISTE et non une chaîne — cp:keywords ressortait vide ;
    #  · le writer epub ne lit pas `keywords` du tout, mais `subject` (→ dc:subject).
    # Un bloc YAML exprime les deux en liste d'un coup. Il doit rester en TÊTE du fichier
    # (exigence Pandoc) ; `--metadata title/author/lang` ci-dessous reste prioritaire sur
    # lui, donc rien d'autre ne change.
    empreinte = f"Angelith {__version__}"
    entete_yaml = (f"---\nkeywords:\n  - {empreinte}\nsubject:\n  - {empreinte}\n---\n\n")
    rendered_md.write_text(entete_yaml + markers_to_markdown(md_text), encoding="utf-8")
    src = rendered_md.name

    common = ["--metadata", f"title={meta['titre']}",
              "--metadata", f"author={meta['auteur']}",
              "--metadata", f"lang={meta['langue']}",
              "--resource-path", "."]
    produced: list[Path] = []
    # Gabarits du PACK DE LANGUE CIBLE. Un pack qui n'en fournit pas retombe sur
    # `rendu.reference_docx` / `rendu.epub_css`, qui restent le réglage de l'utilisateur —
    # d'où une sortie inchangée tant qu'aucun pack n'est installé.
    docx_ref = _chemin(r, "reference_docx") or pack.fichier("templates/reference.docx")
    css_pack = _chemin(r, "epub_css") or pack.fichier("templates/epub.css")
    try:
        if "docx" in formats:
            out = out_dir / f"{stem}.docx"
            ref = str(Path(docx_ref).resolve())
            _run(["pandoc", src, "--reference-doc", ref, *common, "-o", out.name], out_dir)
            _normalize_docx(out, _narration_style_id(Path(docx_ref)))
            produced.append(out)

        if "epub" in formats:
            out = out_dir / f"{stem}.epub"
            css = str(Path(css_pack).resolve())
            _run(["pandoc", src, "--css", css, *common, "-o", out.name], out_dir)
            produced.append(out)

        if "pdf" in formats:
            out = out_dir / f"{stem}.pdf"
            engine = r.get("pdf_engine", "weasyprint")
            cmd = ["pandoc", src, "--pdf-engine", engine]
            if engine in ("weasyprint", "wkhtmltopdf", "pagedjs-cli", "prince"):
                cmd += ["--css", str(Path(css_pack).resolve())]
            cmd += [*common, "-o", out.name]
            try:
                _run(cmd, out_dir)
                produced.append(out)
            except RuntimeError as err:
                print(f"  [PDF] non généré ({engine}) : {err}")
    finally:
        rendered_md.unlink(missing_ok=True)

    return produced
