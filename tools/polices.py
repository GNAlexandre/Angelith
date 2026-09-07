# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Résolution de la police japonaise utilisée par les tests et par le corpus synthétique.

## Le défaut que ce module corrige

`tests/conftest.py` et `tools/corpus_synthetique.py` codaient en dur
`C:/Windows/Fonts/msgothic.ttc`, et le premier *skippait* sa fixture quand le fichier
manquait. Conséquence mesurée et écrite dans `.github/workflows/ci.yml` : sur un runner
Linux, `synthetic_manga_page` serait sautée **en silence** — avec elle toute la couverture
détection / OCR / orchestrateur de la brique manga. Une CI verte qui ne teste plus rien de
ce qui coûte cher.

Le contrat d'OS n'était donc pas une préférence : c'était le seul garde-fou qui restait. Ce
module le remplace par un vrai, en deux temps :

1. **la police devient configurable** — variable d'environnement `ANGELITH_POLICE_JP`, puis
   une liste de candidats par plateforme ;
2. **l'absence devient visible** — `tests/test_fixture_police.py` ÉCHOUE quand aucune
   police n'est trouvée, au lieu de laisser un skip silencieux emporter la couverture.

⚠ Aucune police n'est embarquée dans le dépôt, et ce n'est pas un oubli : `msgothic.ttc`
comme les Noto CJK ont leurs propres licences de redistribution, et `NOTICE` ne porte
aujourd'hui que ce dont le droit de redistribution est établi (cf. le cas de
`templates/fonts/wildjess normal.ttf`, retirée du suivi pour cette raison exacte). On
résout donc une police du SYSTÈME, on ne la distribue pas.

## Pourquoi une police à kana ET à kanji

Le texte peint dans la planche synthétique n'est pas décoratif : `tools/corpus_synthetique.py`
le dit — « un ovale vide et un ballon lettré ne donnent pas le même score au détecteur, et
mesurer sur des bulles vides surestimerait la difficulté ». Une police latine qui rendrait
des tofus (␣) changerait donc la mesure sans rien casser de visible. Les candidats ci-dessous
couvrent tous les kana et les kanji usuels.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

#: Surcharge explicite. Priorité absolue : c'est le point d'entrée d'un contributeur dont la
#: distribution place ses polices ailleurs, et celui d'un runner de CI qui vient d'en installer
#: une. Une valeur pointant sur un fichier absent est une ERREUR, pas un repli silencieux — le
#: silence est précisément ce que ce module supprime.
VARIABLE = "ANGELITH_POLICE_JP"

#: Candidats par plateforme, dans l'ordre d'essai. Chemins ABSOLUS et vérifiés à l'existence :
#: `ImageFont.truetype` accepte un nom court, mais il le résout alors contre un chemin de
#: recherche qui diffère d'une machine à l'autre — on ne saurait plus dire QUELLE police a
#: servi à la mesure.
#:
#: · Windows — `msgothic.ttc` est livrée avec toute installation depuis Windows 7 ; `meiryo`
#:   et `YuGothM` couvrent les images où la première a été retirée.
#: · Linux — `fonts-noto-cjk` est le paquet installé par la CI (une ligne d'`apt`, ~120 Mo) ;
#:   `fonts-ipafont-gothic` et `fonts-vlgothic` sont les deux alternatives courantes des
#:   images Debian/Ubuntu qui embarquent déjà du japonais.
#: · macOS — présent pour un contributeur, PAS pour la CI : `docs/roadmap.md` classe macOS
#:   hors périmètre faute de machine pour le tester, et une CI verte sur un OS que personne
#:   n'utilise donne une fausse assurance.
CANDIDATS: dict[str, tuple[str, ...]] = {
    "win32": (
        r"C:\Windows\Fonts\msgothic.ttc",
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\YuGothM.ttc",
    ),
    "linux": (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/usr/share/fonts/truetype/vlgothic/VL-Gothic-Regular.ttf",
    ),
    "darwin": (
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Supplemental/Osaka.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ),
}

#: Ce qu'il faut taper quand rien n'est trouvé. Un message d'erreur qui nomme la commande
#: coûte une ligne et évite une recherche.
INSTALLATION = {
    "linux": "sudo apt-get install -y fonts-noto-cjk",
    "darwin": "les polices japonaises du système sont normalement présentes ; sinon, "
              "installer Noto Sans CJK JP",
    "win32": "msgothic.ttc est livrée avec Windows ; si elle manque, installer Noto Sans CJK JP",
}


def candidats(plateforme: str | None = None) -> tuple[str, ...]:
    """Les chemins essayés sur `plateforme` (défaut : celle qui tourne). Vide si inconnue."""
    return CANDIDATS.get(plateforme or sys.platform, ())


def police_japonaise(plateforme: str | None = None,
                     environnement: dict[str, str] | None = None) -> Path | None:
    """Le fichier de police à utiliser, ou `None` si aucun n'est disponible.

    ⚠ `None` n'est PAS une valeur de fonctionnement normal : le seul appelant autorisé à
    s'en contenter est `tools/corpus_synthetique.py`, qui retombe sur la police par défaut
    de Pillow pour produire quand même un corpus (dégradé, et il le dit). Côté tests,
    `None` doit faire échouer — cf. `tests/test_fixture_police.py`.
    """
    env = os.environ if environnement is None else environnement
    surcharge = env.get(VARIABLE)
    if surcharge:
        chemin = Path(surcharge)
        if not chemin.is_file():
            raise FileNotFoundError(
                f"{VARIABLE}={surcharge!r} ne désigne aucun fichier. La variable existe pour "
                f"pointer une police japonaise précise ; une valeur fausse doit se voir "
                f"plutôt que de retomber en silence sur une autre police.")
        return chemin
    for candidat in candidats(plateforme):
        chemin = Path(candidat)
        if chemin.is_file():
            return chemin
    return None


def explication_absence(plateforme: str | None = None) -> str:
    """Le message d'échec — il nomme la variable, les candidats essayés et la commande."""
    plat = plateforme or sys.platform
    essais = ("\n".join(f"    · {c}" for c in candidats(plat))
              or "    · (aucun candidat connu pour cette plateforme)")
    return (
        f"Aucune police japonaise trouvée sur cette plateforme ({plat}).\n"
        f"  Candidats essayés :\n{essais}\n"
        f"  Pour installer : {INSTALLATION.get(plat, 'installer Noto Sans CJK JP')}\n"
        f"  Ou pointer la vôtre : {VARIABLE}=/chemin/vers/police.ttc\n"
        f"\n"
        f"  ⚠ Ce n'est pas un skip. Sans police, la planche synthétique n'est pas fabriquée "
        f"et TOUTE la couverture détection / OCR / orchestrateur de la brique manga "
        f"disparaît du compte-rendu sans qu'aucune ligne ne le signale — c'est la CI verte "
        f"qui ne teste plus rien. L'échec est là pour que la perte se voie.")
