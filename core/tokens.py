# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Estimation de tokens partagée entre orchestrator.py et glossary.py — pas de
tokenizer réel (dépendance lourde, inutile pour du simple budgeting de prompt) :
une heuristique par caractère, plus fine pour le CJK (~1 token/caractère) que pour
le latin (~4 caractères/token). Avant cette unification, orchestrator.py et
glossary.py utilisaient chacun leur propre heuristique divergente (l'une ignorait
le CJK), ce qui pouvait sous-estimer un texte de référence japonais/chinois dans un
budget et le surestimer dans l'autre.

Deux classes de caractères y vivent, et **les confondre est un piège déjà payé** :
`CJK` est LARGE (elle sert à compter des tokens, où une ponctuation pleine chasse coûte
autant qu'un idéogramme) ; `CJK_TEXTE` est ÉTROITE (elle sert à décider si un texte
PORTE du japonais). Cf. `manga/quality_manga.py`, qui avait dû se fabriquer sa propre
classe étroite après avoir déclaré « du japonais » sur une bulle ne contenant que `（）`.
"""
import re

# Budget de tokens : volontairement large — U+3000-303F (、。「」) et U+FF00-FFEF (formes
# pleine chasse) sont de la ponctuation, mais elle se tokenise comme le reste du CJK.
CJK = re.compile(r"[　-鿿가-힯＀-￯]")

# Nom historique conservé (call sites manga + tests) : `CJK` est devenu public quand
# orchestrator._word_count a eu besoin de compter les idéogrammes, la portée dépassant
# alors le seul budget de tokens.
_CJK = CJK

# Caractères qui PORTENT du texte : kana, idéogrammes, hangûl. La ponctuation CJK et les
# formes pleine chasse en sont EXCLUES — les compter ferait tenir huit guillemets `「」『』`
# pour quatre mots (mesuré sur `build/manga B/…/RAPPORT.md`, seul fichier latin du
# dépôt que `CJK` faisait diverger). `・` (U+30FB) est exclu : c'est un séparateur de nom,
# pas une lettre ; `ー` (U+30FC) est inclus : il allonge une voyelle, il est porteur.
# Le CORPS de la classe est exposé à part : `glossary_build._norm` en a besoin pour
# construire sa propre classe négative (« tout SAUF alphanumérique et CJK »), et le
# dupliquer serait rouvrir précisément la divergence que ce module existe pour fermer.
CLASSE_CJK_TEXTE = "々ぁ-ゟァ-ヺー㐀-䶿一-鿿豈-﫿가-힣"
CJK_TEXTE = re.compile(f"[{CLASSE_CJK_TEXTE}]")


def estimate(s: str) -> int:
    cjk = len(CJK.findall(s))
    return cjk + (len(s) - cjk) // 4
