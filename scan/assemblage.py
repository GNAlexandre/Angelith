# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Des colonnes lues au document markdown — pur, sans la moindre E/S.

C'est ici que le tome redevient un texte : les colonnes se recollent en paragraphes, les
pages d'illustration deviennent des marqueurs d'image, les pages de titre deviennent des
`#`. Le résultat est un `.md` que `pipeline/sources.py` sait déjà lire — c'est tout le
couplage entre cette brique et le reste du dépôt.

## Où commence un paragraphe

Deux signaux, réunis par un OU, et ce n'est pas de la prudence mais de la complémentarité :

- **l'indentation**, mesurée par `scan/grille.py` — le 一字下げ des paragraphes de récit ;
- **la parenthèse ouvrante** en tête de colonne (`「`, `『`…) — en typographie japonaise une
  réplique n'est pas indentée, le crochet occupe visuellement le retrait. La règle
  géométrique ne peut donc pas la voir, et c'est la seule qui la voie.

Les réunir est sûr dans le bon sens : un faux positif d'indentation sur une colonne qui
commence par un crochet est absorbé (elle ouvre un paragraphe de toute façon). Le vrai
risque serait un faux positif sur une colonne de CONTINUATION, qui couperait une phrase en
deux — c'est contre lui que `grille.haut_du_corps` prend le mode et non le minimum.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Ouvrantes japonaises. Une colonne qui commence par l'une d'elles ouvre une réplique, donc
# un paragraphe, même sans indentation.
OUVRANTES = "「『（〈《【〔〖〘〚｛［"

RUBY_IGNORER = "ignorer"
RUBY_PARENTHESES = "parentheses"

# `manga_ocr.post_process` développe `…` en trois points puis les passe en pleine chasse :
# une cellule `…` de la page ressort en `．．．`. On la restitue, sinon le japonais transmis au
# traducteur est trois fois plus long qu'à l'original sur toutes les suspensions.
_POINTS = re.compile(r"[.．・]{2,}")


@dataclass
class PageLue:
    """Une page, telle que l'orchestrateur la présente à l'assemblage."""
    index: int
    verdict: str
    # Alignés par position : `indentations[i]` décrit `textes[i]`.
    textes: list[str] = field(default_factory=list)
    indentations: list[bool] = field(default_factory=list)
    # `[(indice de caractère estimé, lecture), …]` par colonne, pour le mode « parentheses ».
    lectures: list[list[tuple[int, str]]] = field(default_factory=list)
    media: str | None = None          # chemin relatif, si la page est une illustration


def restaurer_points(texte: str) -> str:
    """Ramène `．．．` à `…`, par groupes de trois — une cellule de la grille par groupe."""
    def _r(m: re.Match) -> str:
        n = len(m.group(0))
        return "…" * max(1, round(n / 3))
    return _POINTS.sub(_r, texte or "")


def nettoyer(texte: str) -> str:
    """Un texte de colonne, prêt à être recollé."""
    return restaurer_points((texte or "").strip())


def ouvre_paragraphe(texte: str, indentee: bool) -> bool:
    return bool(indentee) or (texte[:1] in OUVRANTES if texte else False)


def poser_lectures(texte: str, lectures: list[tuple[int, str]]) -> str:
    """Insère les furigana sous la forme `唖然(あぜん)`.

    ⚠ La position est **estimée** : elle vient du rapport entre l'ordonnée de la ruby et
    l'avance de la colonne, laquelle est déjà approchée à ~7 % près (cf.
    `scan/lecture.ECART_SUSPECT`). L'insertion peut donc tomber à un caractère près. C'est
    pourquoi le mode par défaut est `ignorer` — exactement l'arbitrage rendu pour l'EPUB
    (`decoupage.epub.ruby`), où conserver 8 140 ruby gonflait le japonais de 30 % et noyait
    le traducteur. `parentheses` reste utile pour un tome dont on veut relever les lectures
    de noms propres au glossaire, et il est alors assumé que la place peut glisser."""
    if not lectures or not texte:
        return texte
    sortie = texte
    for position, lecture in sorted(lectures, key=lambda t: -t[0]):
        lecture = (lecture or "").strip()
        if not lecture:
            continue
        coupe = min(max(int(position), 0), len(sortie))
        sortie = f"{sortie[:coupe]}({lecture}){sortie[coupe:]}"
    return sortie


def assembler(pages: list[PageLue], *, ruby: str = RUBY_IGNORER) -> str:
    """Le document complet, en markdown léger.

    Les paragraphes **traversent les pages** : une colonne non indentée en tête de page
    poursuit le paragraphe commencé à la page précédente. C'est le comportement d'un roman,
    et le contraire — un paragraphe par page — donnerait au traducteur un texte haché tous
    les quarante caractères."""
    paragraphes: list[str] = []
    morceaux: list[str] = []

    def fermer() -> None:
        if morceaux:
            bloc = "".join(morceaux).strip()
            if bloc:
                paragraphes.append(bloc)
            morceaux.clear()

    for page in pages:
        if page.verdict == "illustration":
            fermer()
            if page.media:
                paragraphes.append(f"<!-- IMG: {page.media} -->")
            continue

        textes = [nettoyer(t) for t in page.textes]
        if ruby == RUBY_PARENTHESES:
            textes = [poser_lectures(t, lec)
                      for t, lec in zip(textes, page.lectures or [[]] * len(textes))]

        if page.verdict == "titre":
            fermer()
            titre = "".join(textes).strip()
            if titre:
                paragraphes.append(f"# {titre}")
            continue

        for i, texte in enumerate(textes):
            if not texte:
                continue
            indentee = page.indentations[i] if i < len(page.indentations) else False
            if ouvre_paragraphe(texte, indentee):
                fermer()
            morceaux.append(texte)

    fermer()
    return "\n\n".join(paragraphes) + "\n"


def position_de_ruby(boite: tuple[int, int, int, int], y0_colonne: int, avance: float) -> int:
    """Indice de caractère où poser une lecture, d'après l'ordonnée de sa boîte.

    La ruby couvre la graphie qu'elle annote : son BAS marque donc la fin du mot, et c'est
    là qu'il faut refermer la parenthèse."""
    if avance <= 0:
        return 0
    return max(0, int(round((boite[3] - y0_colonne) / avance)))
