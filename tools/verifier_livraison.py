# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Garde-fou de la discipline de livraison — CHANGELOG, version, prompts, tableau daté.

## Ce qu'il automatise

Chaque lot de ce dépôt doit produire une entrée de CHANGELOG datée, une version cohérente et
un document de mesure. C'est tenu à la main, et remarquablement bien tenu — mais c'est
exactement ce qui glisse quand un lot est livré tard le soir. Les quatre règles :

1. si `manga/`, `core/`, `pipeline/`, `gui/` ou `langues/` a changé, `CHANGELOG.md` aussi ;
2. `core/version.py` a changé aussi, **ou** l'ajout au CHANGELOG est sous `[Non publié]` ;
3. si `langues/**/prompts/**` a changé, l'ajout au CHANGELOG **nomme le fichier** de prompt.
   La règle de numérotation l'exige littéralement, et c'est ce qui rend
   `git checkout <tag> -- langues/` utile : sans le nom du fichier, on sait qu'une voix a
   changé mais pas laquelle rejouer ;
4. un banc ajouté porte une date dans son nom — `docs/mesures/banc-AAAA-MM-JJ.md`.
   Deux tableaux ne se comparent que si l'on sait lequel est le plus récent ;
5. **si `core/version.py` a changé, `installeur/version.iss` aussi** — lot 37. L'installeur
   porte son numéro dans un fichier GÉNÉRÉ (`python installeur/generer.py`), et un installeur
   qui annonce 2.29.0 en portant 2.31.0 est exactement le genre de dérive qu'aucun humain ne
   relit. ⚠ Cette règle est la SEULE des cinq qui n'a pas d'échappatoire d'étiquette : le
   fichier se régénère par une commande, il n'y a rien à arbitrer.

## L'échappatoire, et pourquoi elle est nommée

Une correction de commentaire n'a pas à traîner une entrée de CHANGELOG ; sans issue, ce
garde-fou coûterait plus qu'il ne rapporte et serait retiré. L'issue est une **étiquette de
PR**, `sans-changelog`, et pas un mot magique dans le corps du message : une étiquette est
visible dans la liste des PR, elle s'audite d'un coup d'œil, et elle laisse une trace que
personne n'a besoin de chercher dans un texte.

## Ce qu'il ne fait pas

Il ne juge pas la QUALITÉ de l'entrée de CHANGELOG, ni le niveau (MAJEUR/MINEUR/CORRECTIF)
choisi. Ce niveau se décide d'après ce que le lot fait à l'utilisateur — c'est un jugement,
pas un motif. `tests/test_version.py` couvre déjà la cohérence entre `core/version.py` et la
première entrée datée ; ce script couvre la présence, pas le contenu.

## Usage

    python tools/verifier_livraison.py --base origin/main
    python tools/verifier_livraison.py --base origin/main --etiquettes sans-changelog
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: Les dossiers dont un changement engage l'utilisateur. `tools/`, `tests/` et `docs/` n'y
#: sont PAS : un outil de mesure ou un test neuf ne change rien à ce qu'un tome produit, et
#: exiger une entrée de CHANGELOG pour eux banaliserait l'entrée jusqu'à la vider de sens.
DOSSIERS_SURVEILLES = ("manga/", "core/", "pipeline/", "gui/", "langues/")

FICHIER_VERSION = "core/version.py"
#: Le fichier GÉNÉRÉ qui porte la version dans l'installeur Windows (lot 37). Il est dans le
#: dépôt plutôt que produit à la volée pour être lisible dans un diff — donc il peut dériver,
#: donc il se garde.
FICHIER_INSTALLEUR = "installeur/version.iss"
CHANGELOG = "CHANGELOG.md"
ETIQUETTE_ECHAPPATOIRE = "sans-changelog"

_PROMPT = re.compile(r"^langues/[^/]+/prompts/.+", re.IGNORECASE)
# ⚠ `docs/mesures/` depuis le lot 23 : les comptes rendus datés y ont été rangés, la racine
# de `docs/` ne garde que les fichiers de référence. Le préfixe reste TOLÉRÉ à la racine —
# un banc écrit au mauvais endroit doit être jugé, pas ignoré.
_BANC = re.compile(r"^docs/(?:mesures/)?banc-(.+)\.md$", re.IGNORECASE)
_BANC_DATE = re.compile(r"^docs/(?:mesures/)?banc-\d{4}-\d{2}-\d{2}\.md$", re.IGNORECASE)

#: ⚠ L'exception, et elle est nommée : `docs/procedures/banc-de-mesure.md` est le PROTOCOLE du banc, pas
#: une mesure. Il décrit une méthode, il ne se périme pas, et lui coller une date le ferait
#: paraître obsolète à chaque run. `tests/test_coherence_chiffres.py` porte la même exception.
BANC_PROTOCOLE = "docs/procedures/banc-de-mesure.md"
_TITRE_SECTION = re.compile(r"^##\s*\[", re.MULTILINE)
_NON_PUBLIE = re.compile(r"^##\s*\[\s*Non publié\s*\]", re.IGNORECASE)


def section_non_publie(changelog: str) -> tuple[int, int] | None:
    """Les numéros de ligne (1-based, bornes incluses) de la section `[Non publié]`.

    `None` si elle n'existe pas. La section s'arrête au titre `## [` suivant — pas à la
    prochaine ligne vide, ni au prochain `##` quelconque : le CHANGELOG porte des
    sous-titres `###` à l'intérieur d'une entrée.
    """
    lignes = changelog.splitlines()
    debut = None
    for i, ligne in enumerate(lignes, start=1):
        if debut is None:
            if _NON_PUBLIE.match(ligne):
                debut = i
        elif _TITRE_SECTION.match(ligne):
            return (debut, i - 1)
    return (debut, len(lignes)) if debut is not None else None


def lignes_ajoutees_numerotees(diff: str) -> list[int]:
    """Les numéros de ligne, dans le fichier D'ARRIVÉE, des lignes ajoutées par un
    `git diff -U0` portant sur UN seul fichier."""
    entete = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    numeros: list[int] = []
    curseur = 0
    for ligne in diff.splitlines():
        m = entete.match(ligne)
        if m:
            curseur = int(m.group(1))
            continue
        if ligne.startswith("+++"):
            continue
        if ligne.startswith("+"):
            numeros.append(curseur)
            curseur += 1
    return numeros


def texte_ajoute(diff: str) -> str:
    return "\n".join(ligne[1:] for ligne in diff.splitlines()
                     if ligne.startswith("+") and not ligne.startswith("+++"))


def juger(fichiers: list[str], *, changelog_ajoute: str, ajout_sous_non_publie: bool,
          etiquettes: set[str] | None = None) -> list[str]:
    """Les motifs de refus. Liste vide = livraison en règle. Aucune E/S : tout est passé."""
    etiquettes = etiquettes or set()
    fichiers = [f.replace("\\", "/") for f in fichiers]
    motifs: list[str] = []

    touche_le_produit = [f for f in fichiers if f.startswith(DOSSIERS_SURVEILLES)]
    changelog_touche = CHANGELOG in fichiers
    version_touchee = FICHIER_VERSION in fichiers

    echappatoire = ETIQUETTE_ECHAPPATOIRE in etiquettes
    if touche_le_produit and not changelog_touche and not echappatoire:
        motifs.append(
            f"{len(touche_le_produit)} fichier(s) sous {', '.join(DOSSIERS_SURVEILLES)} ont "
            f"changé sans entrée de CHANGELOG (ex. `{touche_le_produit[0]}`). Étiqueter la "
            f"PR `{ETIQUETTE_ECHAPPATOIRE}` si le changement ne se voit pas à l'usage.")

    if touche_le_produit and changelog_touche and not version_touchee \
            and not ajout_sous_non_publie:
        motifs.append(
            f"`{CHANGELOG}` a changé hors de la section `[Non publié]` mais "
            f"`{FICHIER_VERSION}` n'a pas bougé — une entrée datée sans bump finit en tag "
            f"non documenté (`tests/test_version.py` le rattraperait, mais après coup).")

    # Règle 5 (lot 37) — l'artefact d'empaquetage suit la version.
    if version_touchee and FICHIER_INSTALLEUR not in fichiers:
        motifs.append(
            f"`{FICHIER_VERSION}` a changé mais `{FICHIER_INSTALLEUR}` n'a pas suivi — "
            f"l'installeur porterait un numéro périmé, et personne ne relit un `.iss`. "
            f"→ python installeur/generer.py")

    prompts = [f for f in fichiers if _PROMPT.match(f)]
    for prompt in prompts:
        nom = Path(prompt).name
        if nom not in changelog_ajoute:
            motifs.append(
                f"le prompt `{prompt}` a changé mais `{nom}` n'est nommé nulle part dans "
                f"l'ajout au CHANGELOG. La règle de numérotation l'exige : sans le nom du "
                f"fichier, `git checkout <tag> -- langues/` ne dit pas quelle voix rejouer.")

    for fichier in fichiers:
        if _BANC.match(fichier) and not _BANC_DATE.match(fichier) \
                and fichier != BANC_PROTOCOLE:
            motifs.append(
                f"`{fichier}` est un tableau de banc sans date dans son nom. Le format est "
                f"`docs/mesures/banc-AAAA-MM-JJ.md` : deux tableaux ne se comparent que si l'on "
                f"sait "
                f"lequel est le plus récent.")
    return motifs


# ---------------------------------------------------------------------------
# La couche git.

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RACINE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def etat(base: str, tete: str = "HEAD") -> tuple[list[str], str, bool]:
    fichiers = [f for f in _git("diff", "--name-only", f"{base}...{tete}").splitlines() if f]
    if CHANGELOG not in fichiers:
        return fichiers, "", False
    diff = _git("diff", "-U0", f"{base}...{tete}", "--", CHANGELOG)
    ajoute = texte_ajoute(diff)
    numeros = lignes_ajoutees_numerotees(diff)
    bornes = section_non_publie(_git("show", f"{tete}:{CHANGELOG}"))
    sous_non_publie = bool(numeros) and bornes is not None and \
        all(bornes[0] <= n <= bornes[1] for n in numeros)
    return fichiers, ajoute, sous_non_publie


def rendre(motifs: list[str], nb_fichiers: int, *, markdown: bool = False) -> str:
    if markdown:
        if not motifs:
            return ("### Discipline de livraison\n\n"
                    f"✅ {nb_fichiers} fichier(s) modifié(s), les quatre règles sont tenues.")
        return ("### Discipline de livraison\n\n"
                f"❌ **{len(motifs)} règle(s) non tenue(s)** sur {nb_fichiers} fichier(s) "
                f"modifié(s).\n\n" + "\n".join(f"- {m}" for m in motifs))
    if not motifs:
        return f"{nb_fichiers} fichier(s) modifié(s) — les quatre règles sont tenues."
    return "\n".join(f"REFUS · {m}" for m in motifs) + \
        f"\n\n{len(motifs)} règle(s) non tenue(s) sur {nb_fichiers} fichier(s) modifié(s)."


def main(argv: list[str] | None = None) -> int:
    # ⚠ **Pas `core.cli.configurer_stdout()`, et ce n'est pas un oubli.** Ce fichier
    # n'importe QUE la bibliothèque standard, et le job « Garde-fous » le lance sur un Python
    # nu — `.github/workflows/garde-fous.yml` ne fait aucun `pip install`. Importer
    # `core.cli` tirerait `yaml` et casserait le job. D'où ces quatre lignes, répétées dans
    # les outils sans dépendance et tenues en phase par `tests/test_outils_sortie.py`.
    #
    # Sans elles, une console Windows en cp1252 fait tomber l'outil sur le premier « ⚠ » —
    # mesuré le 2026-09-04 : `verifier_disclosure.py --historique 3` levait un
    # `UnicodeEncodeError` APRÈS avoir jugé les commits, donc en perdant son verdict.
    for _flux in (sys.stdout, sys.stderr):
        try:
            _flux.reconfigure(encoding="utf-8")
        except Exception:      # noqa: BLE001 — flux remplacé (test, pipe) ou non reconfigurable
            pass

    ap = argparse.ArgumentParser(description="Garde-fou de la discipline de livraison.")
    ap.add_argument("--base", required=True)
    ap.add_argument("--tete", default="HEAD")
    ap.add_argument("--etiquettes", default="",
                    help="étiquettes de la PR, séparées par des virgules "
                         f"(seule `{ETIQUETTE_ECHAPPATOIRE}` a un effet)")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--non-bloquant", action="store_true")
    a = ap.parse_args(argv)

    fichiers, ajoute, sous_non_publie = etat(a.base, a.tete)
    etiquettes = {e.strip() for e in a.etiquettes.split(",") if e.strip()}
    motifs = juger(fichiers, changelog_ajoute=ajoute, ajout_sous_non_publie=sous_non_publie,
                   etiquettes=etiquettes)
    print(rendre(motifs, len(fichiers), markdown=a.markdown))
    return 0 if (a.non_bloquant or not motifs) else 1


if __name__ == "__main__":
    sys.exit(main())
