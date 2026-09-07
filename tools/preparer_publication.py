# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Préparer l'arbre de la branche `public` — anonymisation et correctifs, en UNE commande.

## Le défaut que cet outil ferme

La publication transpose l'arbre par `git read-tree --reset -u main`, ce qui **écrase tout ce
qui était propre à la branche publique**. Trois correctifs devaient donc être rejoués à la
main à chaque fois, et l'anonymisation des titres avec eux. Entre le 2026-09-06 et le
2026-09-07 la séquence a été rejouée **cinq fois** ; à chaque fois quelque chose a failli
manquer, et la procédure elle-même nomme le risque : « une purge à refaire est une purge qu'on
peut rater ».

Une seule commande, donc, qui échoue bruyamment plutôt que de laisser passer :

    python tools/preparer_publication.py            # applique tout, et rend un compte rendu
    python tools/preparer_publication.py --verifier  # ne rend que le compte, n'écrit rien

## ⚠ Il est INERTE sur la branche `public`, et c'est délibéré

La correspondance titre → désignation vit dans `docs/PUBLICATION-ANGELITH.md`, **retiré de
l'arbre publié**. Ce fichier-ci, lui, est publié : y recopier la correspondance publierait les
titres avec l'outil qui sert à les retirer. Sur la branche `public`, il lève donc
`CorrespondancesIndisponibles` — un garde-fou qui ne sait pas ce qu'il cherche doit le dire,
pas rendre un vert silencieux. C'est exactement la doctrine de `tools/verifier_arbre.py`, dont
le bloc de motifs vit au même endroit et pour la même raison.

## Ce qu'il fait, dans l'ordre

1. **l'anonymisation**, tolérante aux titres coupés par un retour à la ligne — la prose de ce
   dépôt est enroulée à 98 colonnes et vit largement dans des commentaires, si bien qu'une
   coupure tombe au milieu d'un titre une fois sur trois ;
2. **l'élision** : un titre commençant par une voyelle donne « de manga A », qui n'est pas
   du français ;
3. **le réenroulement** des lignes que le remplacement a rallongées — et **d'elles seules**.
   ⚠ Jamais du code : dans un fichier Python, seuls les commentaires sont enroulables. Couper
   une ligne de code produit un fichier qui ne compile plus, ce qui est arrivé à la deuxième
   utilisation réelle de cet outil ;
4. **les trois correctifs de publication**, déclarés dans `CORRECTIFS` ci-dessous ;
5. **un contrôle de vraisemblance** : le même libellé deux fois de suite signale un
   remplacement en cascade, et fait échouer la préparation au lieu de publier du charabia. Ce
   n'est pas théorique — l'arbre en portait deux, trouvés au premier essai de cet outil.

⚠ **Rien n'est écrit tant que les contrôles n'ont pas jugé l'ENSEMBLE** — ni le libellé
doublé, ni la validité du code produit. La première version écrivait au fil de l'eau et ne
levait qu'à la fin : un refus laissait l'arbre à moitié anonymisé, c'est-à-dire dans l'état le
plus difficile à reprendre.

⚠ Il ne **vérifie** rien : c'est `tools/verifier_arbre.py --suivi` qui juge le résultat, et il
doit être lancé après. Deux outils, deux rôles — celui qui corrige n'est jamais celui qui dit
que c'est bon.
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import subprocess
import sys
import textwrap
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: Le fichier qui porte la correspondance. **Jamais publié** — cf. l'en-tête.
SOURCE_DES_CORRESPONDANCES = RACINE / "docs" / "PUBLICATION-ANGELITH.md"

_DEBUT = "<!-- correspondances:début -->"
_FIN = "<!-- correspondances:fin -->"

#: Le seul fichier épargné par l'anonymisation : c'est lui qui porte les titres.
EPARGNE = {"docs/PUBLICATION-ANGELITH.md"}

#: Épargnés par le CONTRÔLE DE VRAISEMBLANCE seulement — ils sont anonymisés comme les autres.
#:
#: ⚠ Ce sont les deux fichiers qui **parlent** du contrôle : ils en portent l'exemple, « le même
#: libellé deux fois de suite », dans une docstring et dans une donnée de test. Se signaler
#: soi-même n'apprend rien — c'est exactement le motif pour lequel `tools/verifier_arbre.py`
#: exclut le fichier qui porte ses motifs.
#:
#: ⚠ La liste est COURTE et le restera : chaque nom qu'on y ajoute est un endroit où un vrai
#: remplacement en cascade passerait. Documenter le contrôle ailleurs se fait sans écrire
#: l'exemple littéralement.
EPARGNE_DOUBLONS = {"tools/preparer_publication.py", "tests/test_outils_publication.py"}

#: Entre deux mots d'un titre : des espaces, au plus UN retour à la ligne, et le préfixe de
#: commentaire éventuel de la ligne suivante (`#`, `#:`). Sans lui, `*Full\\nMetal Panic*`
#: resterait entier.
_SEP = r"[ \t]*\n?[ \t]*(?:#:?[ \t]*)?"

#: Largeur d'enroulement de la prose du dépôt.
COLONNES = 96

#: Les correctifs propres à la branche publique. **Déclaratifs**, et chacun échoue si son ancre
#: a disparu : un correctif qui ne s'applique plus doit se voir, pas se taire.
CORRECTIFS: tuple[tuple[str, str, str], ...] = (
    (
        "tests/test_gui_vue_oeuvres.py",
        '    assert oe.retenu(info, "", "", "silent")',
        "    # ⚠ Casse DIFFÉRENTE de celle du titre : c'est cela que ce test vérifie.\n"
        '    assert oe.retenu(info, "", "", "Roman")',
    ),
    (
        "tests/test_outils_atelier.py",
        "def test_les_motifs_se_lisent_dans_la_procedure_reelle():",
        "@pytest.mark.skipif(not verifier_arbre.SOURCE_DES_MOTIFS.is_file(),\n"
        '                    reason="la procédure de publication n\'est pas dans l\'arbre '
        'publié")\n'
        "def test_les_motifs_se_lisent_dans_la_procedure_reelle():",
    ),
)


class CorrespondancesIndisponibles(RuntimeError):
    """La table est absente ou vide. ⚠ **Attendu sur la branche `public`** — la préparation s'y
    fait AVANT la transposition, sur la branche de développement."""


def correspondances(source: Path | None = None) -> list[tuple[str, str]]:
    """`[(titre, désignation)]`, dans l'ordre du fichier — **le plus long d'abord**."""
    source = source or SOURCE_DES_CORRESPONDANCES
    if not source.is_file():
        raise CorrespondancesIndisponibles(
            f"{source} est absent : la correspondance des titres vit là et nulle part "
            f"ailleurs (elle ne peut pas vivre dans un fichier publié). Sur la branche "
            f"`public`, c'est attendu — la préparation se fait AVANT la transposition.")
    texte = source.read_text(encoding="utf-8")
    try:
        bloc = texte.split(_DEBUT, 1)[1].split(_FIN, 1)[0]
    except IndexError as err:
        raise CorrespondancesIndisponibles(
            f"{source} ne porte plus le bloc {_DEBUT} … {_FIN}.") from err
    paires = []
    for ligne in bloc.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("```"):
            continue
        titre, _, etiquette = ligne.partition("=")
        if titre.strip() and etiquette.strip():
            paires.append((titre.strip(), etiquette.strip()))
    if not paires:
        raise CorrespondancesIndisponibles(f"le bloc de {source} est vide")
    return paires


#: Les bornes du titre. ⚠ **Ce ne sont PAS des `\b`**, et c'est le correctif du lot 49.
#:
#: `\b` ne s'active qu'entre un caractère de mot et un autre qui n'en est pas — or le TIRET BAS
#: EST un caractère de mot. Un titre suivi de « _Vol.1_glossaire.yaml » n'était donc pas
#: remplacé : il restait dans l'arbre publié, à côté du même titre remplacé une ligne plus
#: haut. Un fichier à moitié anonymisé, et un test rendu incohérent.
#:
#: ⚠ **Cette forme dépend de l'ORDRE de la table** : sans `\b`, un titre court se retrouverait
#: dans un titre long qui le contient (« manga B_Eight »). C'est l'ordre du bloc — le plus long
#: d'abord — qui l'empêche, et `tests/test_outils_publication.py` en fait une règle vérifiée.
_AVANT = r"(?<![A-Za-z0-9])"
_APRES = r"(?![A-Za-z0-9])"


def _motif(titre: str) -> re.Pattern[str]:
    """Le titre, tolérant à une coupure de ligne entre ses mots et à un tiret bas au bord."""
    mots = [re.escape(m) for m in titre.split()]
    return re.compile(_AVANT + _SEP.join(mots) + _APRES, re.IGNORECASE)


def anonymiser(texte: str, paires: list[tuple[str, str]]) -> tuple[str, int]:
    """Rend `(texte, nombre de remplacements)`. **L'ordre des paires est celui du fichier.**"""
    compte = 0
    for titre, etiquette in paires:
        texte, n = _motif(titre).subn(etiquette, texte)
        compte += n
    # ⚠ Le remplacement laisse « de manga A » là où le titre commençait par une voyelle.
    # Ce n'est pas du français, et aucun relecteur humain ne repasse derrière.
    texte, n = re.subn(r"\b([dD])'(\*?)(manga|roman|webtoon)\b",
                       lambda m: f"{m.group(1)}e {m.group(2)}{m.group(3)}", texte)
    return texte, compte + n


_PREFIXE = re.compile(r"^(\s*(?:#:?\s|>\s)?)")


def enroulable(ligne: str, *, python: bool) -> bool:
    """Cette ligne peut-elle être coupée sans rien casser ?

    ⚠ **Le défaut que ce garde ferme**, trouvé à la deuxième utilisation réelle de l'outil :
    le réenroulement a coupé une LIGNE DE CODE contenant une chaîne littérale, produisant
    quinze erreurs de syntaxe. Enrouler de la prose est cosmétique ; enrouler du code est
    destructeur.

    · dans un fichier Python, **seuls les commentaires** sont enroulables. Une ligne de code,
      une signature, une ligne de docstring — on n'y touche pas. Une docstring trop longue est
      laide, une chaîne coupée en deux ne compile pas ;
    · ailleurs, tout sauf ce qui a une STRUCTURE de colonne : une ligne de tableau Markdown
      coupée cesse d'être un tableau, et un bloc indenté est du code affiché."""
    nu = ligne.lstrip()
    if python:
        return nu.startswith("#")
    if "|" in ligne or ligne.startswith("    ") or nu.startswith("```"):
        return False
    return True


def reenrouler(avant: str, apres: str, *, python: bool = False) -> str:
    """Réenroule les lignes que l'anonymisation a RALLONGÉES au-delà de `COLONNES`.

    ⚠ Seulement celles-là, et seulement si `enroulable` l'autorise : le dépôt porte des lignes
    longues légitimes — tableaux Markdown, prose CJK, données. Les enrouler toutes produirait
    un diff de publication illisible, et pour du code, un fichier qui ne compile plus."""
    lignes_avant = avant.splitlines()
    lignes = apres.splitlines()
    sortie: list[str] = []
    for i, ligne in enumerate(lignes):
        ancienne = lignes_avant[i] if i < len(lignes_avant) else ""
        if (len(ligne) <= COLONNES or ligne == ancienne or len(ancienne) > COLONNES
                or not enroulable(ligne, python=python)):
            sortie.append(ligne)
            continue
        prefixe = _PREFIXE.match(ligne).group(1)
        corps = ligne[len(prefixe):]
        morceaux = textwrap.wrap(corps, width=COLONNES - len(prefixe),
                                 break_long_words=False, break_on_hyphens=False)
        sortie.extend(prefixe + m for m in (morceaux or [corps]))
    return "\n".join(sortie) + ("\n" if apres.endswith("\n") else "")


def doublons(texte: str, paires: list[tuple[str, str]]) -> list[str]:
    """Les libellés répétés deux fois de suite. Signe d'un remplacement en cascade.

    ⚠ Ce n'est pas théorique : l'arbre a porté « *manga A Zero manga A* » jusqu'au 2026-09-07,
    reste d'une purge qui avait remplacé les deux moitiés d'un titre sans voir le mot resté au
    milieu. Publier du charabia est pire que publier un titre : le second se voit."""
    vus = []
    for etiquette in {e for _, e in paires}:
        if re.search(rf"\b{re.escape(etiquette)}[ \t]+{re.escape(etiquette)}\b", texte):
            vus.append(etiquette)
    return sorted(vus)


#: Le job retiré de l'arbre publié, et le motif à laisser sur place.
JOB_RETIRE = "sonar"
NOTE_JOB_RETIRE = (
    "  # ⚠ **LE JOB `sonar` EST RETIRÉ DE L'ARBRE PUBLIÉ**, sur décision du mainteneur\n"
    "  # (2026-09-07).\n"
    "  #\n"
    "  # Il exige un secret `SONAR_TOKEN` que ce dépôt n'a pas, et son étape de scan échouait\n"
    "  # donc à chaque exécution — peignant en rouge une intégration continue dont les tests,\n"
    "  # eux, passent sur les deux plateformes. Un job qui ne peut structurellement pas\n"
    "  # réussir ici n'apprend rien à qui lit le badge.\n"
    "  #\n"
    "  # L'analyse continue de tourner là où le jeton existe. Elle n'est pas supprimée du\n"
    "  # projet : elle est absente de CETTE copie.\n"
    "\n")


def retirer_job(texte: str, job: str = JOB_RETIRE, note: str = NOTE_JOB_RETIRE) -> str:
    """Retire un job d'un workflow, **son bloc de commentaires compris**, et laisse la note.

    ⚠ Le commentaire qui PRÉCÈDE un job lui appartient : le laisser derrière ferait flotter une
    explication au-dessus du job suivant, qu'elle ne décrit pas. On remonte donc jusqu'à la
    première ligne non commentée, et on redescend de même après le bloc.

    Rend le texte inchangé si le job n'y est pas — la préparation doit pouvoir se rejouer."""
    lignes = texte.splitlines(keepends=True)
    debut = next((i for i, l in enumerate(lignes) if l.startswith(f"  {job}:")), None)
    if debut is None:
        return texte
    tete = debut
    while tete > 0 and lignes[tete - 1].lstrip().startswith("#"):
        tete -= 1
    fin = len(lignes)
    for i in range(debut + 1, len(lignes)):
        if re.match(r"^  [a-z_-]+:", lignes[i]):
            fin = i
            while fin > debut and lignes[fin - 1].lstrip().startswith("#"):
                fin -= 1
            break
    return "".join(lignes[:tete]) + note + "".join(lignes[fin:])


def fichiers_suivis() -> list[str]:
    sortie = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return [ligne for ligne in sortie.stdout.splitlines()
            if ligne.strip() and ligne not in EPARGNE]


def preparer(*, ecrire: bool = True, dire=print) -> dict:
    """Applique tout. Rend un compte rendu `{fichiers, remplacements, correctifs}`."""
    paires = correspondances()
    # ⚠ **DEUX TEMPS : on calcule tout, on juge, PUIS on écrit.** La première version écrivait
    # au fil de l'eau et ne levait qu'à la fin : un refus laissait donc l'arbre à moitié
    # anonymisé, c'est-à-dire dans l'état le plus difficile à reprendre. « Il refuse de
    # publier » doit vouloir dire que rien n'a été touché.
    prevu: dict[str, str] = {}
    touches, total, charabia = {}, 0, {}
    for nom in fichiers_suivis():
        chemin = RACINE / nom
        try:
            avant = chemin.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue                     # binaire ou illisible : on n'y touche pas
        apres, compte = anonymiser(avant, paires)
        if not compte:
            continue
        apres = reenrouler(avant, apres, python=nom.endswith(".py"))
        if nom not in EPARGNE_DOUBLONS:
            mauvais = doublons(apres, paires)
            if mauvais:
                charabia[nom] = mauvais
        prevu[nom] = apres
        touches[nom] = compte
        total += compte
    if charabia:
        detail = "; ".join(f"{n} → {', '.join(v)}" for n, v in charabia.items())
        raise SystemExit(f"❌ libellé doublé après anonymisation : {detail}\n"
                         f"   Un titre a été remplacé en cascade. Corrige la correspondance "
                         f"ou le texte source AVANT de publier.\n"
                         f"   ⚠ RIEN N'A ÉTÉ ÉCRIT : l'arbre est intact.")

    # ⚠ **Chaque fichier Python produit doit encore s'ANALYSER.** `enroulable` empêche de
    # couper une ligne de code ; ce contrôle-ci le PROUVE, sur le résultat. Les deux ne font
    # pas double emploi : le premier est une heuristique sur la forme des lignes, le second
    # une vérification sur ce qui sortirait. Sans lui, l'outil a produit quinze erreurs de
    # syntaxe à sa deuxième utilisation réelle, et c'est `ruff` — lancé après, à la main — qui
    # les a vues.
    casses = {}
    for nom, contenu in prevu.items():
        if not nom.endswith(".py"):
            continue
        try:
            ast.parse(contenu)
        except SyntaxError as err:
            casses[nom] = f"ligne {err.lineno} : {err.msg}"
    if casses:
        detail = "; ".join(f"{n} ({m})" for n, m in casses.items())
        raise SystemExit(f"❌ l'anonymisation casserait du code Python : {detail}\n"
                         f"   ⚠ RIEN N'A ÉTÉ ÉCRIT : l'arbre est intact.")
    if ecrire:
        for nom, contenu in prevu.items():
            (RACINE / nom).write_text(contenu, encoding="utf-8")

    appliques = []
    for nom, ancre, remplacement in CORRECTIFS:
        chemin = RACINE / nom
        texte = chemin.read_text(encoding="utf-8")
        if texte.count(ancre) != 1:
            raise SystemExit(f"❌ correctif de publication inapplicable : l'ancre attendue "
                             f"dans {nom} apparaît {texte.count(ancre)} fois, pas une.\n"
                             f"   Le fichier a changé ; relis le correctif avant de publier.")
        if ecrire:
            chemin.write_text(texte.replace(ancre, remplacement, 1), encoding="utf-8")
        appliques.append(nom)

    # ⚠ Tolérant à l'absence du fichier, comme `retirer_job` l'est à l'absence du job : la
    # préparation doit pouvoir tourner sur un arbre réduit — c'est ce que font ses tests.
    workflow = RACINE / ".github" / "workflows" / "ci.yml"
    avant_ci = workflow.read_text(encoding="utf-8") if workflow.is_file() else ""
    apres_ci = retirer_job(avant_ci) if avant_ci else ""
    if apres_ci != avant_ci:
        if ecrire:
            workflow.write_text(apres_ci, encoding="utf-8")
        appliques.append(f".github/workflows/ci.yml (job « {JOB_RETIRE} » retiré)")

    for nom, compte in sorted(touches.items(), key=lambda kv: -kv[1])[:10]:
        dire(f"  {compte:4d}  {nom}")
    dire(f"\n{total} occurrence(s) anonymisée(s) dans {len(touches)} fichier(s).")
    for nom in appliques:
        dire(f"  correctif de publication appliqué : {nom}")
    return {"fichiers": len(touches), "remplacements": total, "correctifs": appliques}


def main(argv: list[str] | None = None) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verifier", action="store_true",
                    help="compte sans rien écrire")
    a = ap.parse_args(argv)
    try:
        preparer(ecrire=not a.verifier)
    except CorrespondancesIndisponibles as err:
        print(f"❌ {err}")
        return 2
    if not a.verifier:
        print("\n⚠ Lance maintenant `python tools/verifier_arbre.py --suivi` : cet outil "
              "CORRIGE, il ne juge pas.")
    return 0


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(main())
