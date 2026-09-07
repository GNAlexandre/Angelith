# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La règle des chiffres, vérifiée mécaniquement là où c'est possible — et pas ailleurs.

## La règle

`docs/chiffres-de-reference.md` la pose, après que cinq nombres — 821, 813, 797, 790, 687 —
ont désigné le même tome sans qu'aucun porte son dénominateur :

> Tout chiffre de communication du projet porte **sa source** et **son dénominateur**. Un
> chiffre sans dénominateur n'est pas une mesure, c'est une impression.

Rien ne la vérifiait. Le compte de tests, lui, a déjà divergé pour de bon : 1 908, 1 657,
« un millier et demi » et 2 262 ont tous circulé dans le dépôt en même temps.

## Ce que ce fichier vérifie — et pourquoi c'est un TEST, pas un workflow

Un test tourne en local, avant le push. Un workflow ne dit rien tant qu'on n'a pas poussé.

`docs/chiffres-de-reference.md` est traité ici comme **la source**, ce qu'il dit déjà être ;
les autres emplacements doivent s'y accorder. Quatre invariants, tous exacts :

1. le compte de tests annoncé dans `README.md`, `CONTRIBUTING.md` et `docs/COMMANDES.fr.md`
   est celui du tableau de référence, **et porte la même date** ;
2. l'arithmétique du tableau tient : total = boucle courte + désélectionnés ;
3. tout `docs/mesures/banc-*.md` porte une date, un commit et une empreinte de `config.yaml` —
   c'est ce que `tools/banc.py --markdown` produit, donc c'est vérifiable ;
4. les licences de modèles concordent entre `manga_models/README.md`,
   `docs/ai-provenance.md` et `docs/chiffres-de-reference.md`.

## ⚠ Trois dénominateurs légitimes, qu'il ne faut PAS unifier de force

Le dépôt en porte trois, et les confondre serait pire que de les laisser diverger :

- **le total** — `pytest --collect-only -q`, toutes dépendances optionnelles installées ;
- **la boucle courte** — `-m "not lent and not modeles"`, ce que la CI exécute ;
- **le couple de `ci.yml`** — collectés avec PySide6 contre sans, qui MESURE l'effet de son
  installation et n'a de sens que par paire.

Ce fichier vérifie que chaque emplacement cite **le bon** avec **son étiquette**, pas qu'ils
sont tous égaux.

## Ce qu'il ne vérifie PAS, et c'est délibéré

Il ne tente pas de vérifier que « tout chiffre porte son dénominateur ». Ce n'est pas
décidable par une expression régulière : un garde-fou qui produit des faux positifs sur de la
prose est contourné avant d'avoir servi. La règle générale reste à la relecture humaine ; ce
qui est ici est exact.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
REFERENCE = RACINE / "docs" / "chiffres-de-reference.md"

#: Les espaces qui séparent les milliers en typographie française : espace ordinaire, insécable
#: (U+00A0) et insécable fine (U+202F). Les trois se rencontrent dans le dépôt selon l'éditeur
#: qui a écrit la ligne ; les distinguer ferait échouer le test sur un caractère invisible.
_ESPACES = "   "


def _nombre(texte: str) -> int:
    return int(re.sub(f"[{_ESPACES}]", "", texte))


def _motif_nombre(valeur: int) -> re.Pattern[str]:
    """Le nombre `valeur` écrit avec n'importe lequel de ces séparateurs, ou sans."""
    chiffres = str(valeur)
    if len(chiffres) <= 3:
        return re.compile(re.escape(chiffres))
    tete, queue = chiffres[:-3], chiffres[-3:]
    return re.compile(rf"{re.escape(tete)}[{_ESPACES}]?{re.escape(queue)}")


def _lire(chemin: str) -> str:
    return (RACINE / chemin).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1 et 2 — le compte de tests

_LIGNE_TABLEAU = re.compile(
    rf"^\|\s*\*\*([\d{_ESPACES}]+)\*\*\s*\|(.*?)\|(.*?)\|\s*$", re.MULTILINE)


def _tableau_des_tests() -> list[tuple[int, str, str]]:
    """Les lignes de la section « Nombre de tests » de `docs/chiffres-de-reference.md`."""
    texte = _lire("docs/chiffres-de-reference.md")
    debut = texte.index("### Nombre de tests")
    fin = texte.index("###", debut + 5)
    return [(_nombre(m.group(1)), m.group(2).strip(), m.group(3).strip())
            for m in _LIGNE_TABLEAU.finditer(texte[debut:fin])]


def test_le_tableau_de_reference_des_tests_est_lisible():
    """Si ce test tombe, ce n'est pas une divergence de chiffres : c'est que le tableau a
    changé de forme et que les trois suivants ne mesurent plus rien."""
    lignes = _tableau_des_tests()
    assert len(lignes) >= 3, lignes
    assert all(n > 0 for n, _, _ in lignes)


def _ligne(mot: str) -> tuple[int, str, str]:
    for entree in _tableau_des_tests():
        if mot in entree[2]:
            return entree
    raise AssertionError(
        f"aucune ligne du tableau « Nombre de tests » ne porte « {mot} » dans son "
        f"dénominateur — l'étiquette est ce qui distingue les trois chiffres légitimes")


def test_le_total_et_sa_date_sont_repris_a_l_identique_dans_les_trois_fichiers():
    """LE test de la règle : ces trois fichiers ont déjà divergé (1 908, 1 657, 2 262).

    Chacun doit citer le nombre du tableau de référence ET sa date de mesure. Un compte de
    tests se périme à chaque commit ; sans sa date, ce n'est plus une mesure."""
    total, ou, denominateur = _ligne("toutes dépendances optionnelles")
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", denominateur)
    assert dates, f"la ligne du total ne porte pas de date : {denominateur!r}"
    date = dates[0]

    fichiers = re.findall(r"`([^`]+\.(?:md|fr\.md))`", ou)
    assert len(fichiers) == 3, f"le tableau devrait nommer trois fichiers, il en nomme {fichiers}"

    motif = _motif_nombre(total)
    for fichier in fichiers:
        texte = _lire(fichier)
        assert motif.search(texte), (
            f"{fichier} ne cite pas le total de {total} tests annoncé par "
            f"docs/chiffres-de-reference.md — c'est exactement la divergence que la règle "
            f"des chiffres interdit")
        assert date in texte, (
            f"{fichier} cite bien {total}, mais pas la date de mesure {date}. Un compte de "
            f"tests sans date n'est pas une mesure : il se périme à chaque commit.")


def test_l_arithmetique_du_tableau_tient():
    """total = boucle courte + désélectionnés. Un invariant, pas une convention : c'est ce
    que `pytest` imprime lui-même (« N/M tests collected (K deselected) »)."""
    total, _, _ = _ligne("toutes dépendances optionnelles")
    courte, _, _ = _ligne('not lent and not modeles')
    deselectionnes, _, _ = _ligne("désélectionnés par ces marqueurs")
    assert courte + deselectionnes == total, (courte, deselectionnes, total)


def test_le_couple_de_ci_yml_est_coherent_et_date():
    """⚠ Le troisième dénominateur, et il ne s'unifie pas aux deux autres : `ci.yml` mesure
    l'EFFET de PySide6 (collectés avec, collectés sans). On vérifie donc son arithmétique
    interne et la présence de sa date — pas son égalité avec le total du dépôt."""
    texte = _lire(".github/workflows/ci.yml")
    m = re.search(rf"([\d{_ESPACES}]+) tests contre ([\d{_ESPACES}]+), soit ([\d{_ESPACES}]+)",
                  texte)
    assert m, "le couple « N tests contre M, soit K » a disparu de ci.yml"
    avec, sans, ecart = (_nombre(g) for g in m.groups())
    assert avec - sans == ecart, (avec, sans, ecart)
    ligne_et_suite = texte[m.start():m.start() + 400]
    assert re.search(r"\d{4}-\d{2}-\d{2}", ligne_et_suite), (
        "le couple de ci.yml ne porte pas sa date à proximité — les trois dénominateurs du "
        "dépôt bougent à chaque lot, celui-ci doit dire quand il a été mesuré")


# ---------------------------------------------------------------------------
# 3 — les tableaux de banc

#: ⚠ `banc-de-mesure.md` est exclu, et il faut le dire : c'est le PROTOCOLE du banc, pas une
#: mesure. Il n'a donc ni date, ni commit, ni empreinte — et il ne doit pas en avoir, sans quoi
#: il se périmerait à chaque run alors qu'il décrit une méthode. `tools/verifier_livraison.py`
#: porte la même exception, au même titre.
PROTOCOLE = "banc-de-mesure.md"

#: ⚠ Depuis le lot 23, les comptes rendus datés vivent sous `docs/mesures/` et la racine de
#: `docs/` ne garde que les fichiers de référence. On cherche donc aux DEUX endroits : un banc
#: écrit au mauvais niveau doit être jugé, pas ignoré — le rendre invisible désarmerait la
#: règle au premier rangement de dossier.
TABLEAUX_DE_BANC = sorted(
    p for p in [*(RACINE / "docs").glob("banc-*.md"),
                *(RACINE / "docs" / "mesures").glob("banc-*.md")]
    if p.name != PROTOCOLE)


def test_il_existe_au_moins_un_tableau_de_banc():
    """La règle du dépôt : aucun lot ne se termine sans un tableau daté."""
    assert TABLEAUX_DE_BANC, ("aucun docs/mesures/banc-*.md — cf. "
                              "docs/procedures/banc-de-mesure.md")


@pytest.mark.parametrize("tableau", TABLEAUX_DE_BANC, ids=lambda p: p.name)
def test_chaque_tableau_de_banc_porte_date_commit_et_empreinte(tableau: Path):
    """C'est ce que `tools/banc.py --markdown` produit : deux tableaux ne se comparent que si
    l'on sait ce qui a changé entre eux."""
    assert re.match(r"banc-\d{4}-\d{2}-\d{2}\.md$", tableau.name), tableau.name
    texte = tableau.read_text(encoding="utf-8")
    assert re.search(r"\*\*Date de mesure\*\*\s*:\s*\d{4}-\d{2}-\d{2}", texte), tableau.name
    assert re.search(r"\*\*Commit\*\*\s*:\s*`[0-9a-f]{7,40}`", texte), tableau.name
    assert re.search(r"sha256\s*`[0-9a-f]{6,}`", texte), (
        f"{tableau.name} ne porte pas l'empreinte de config.yaml — sans elle, on ne sait pas "
        f"contre quelle configuration le tableau a été mesuré")


# ---------------------------------------------------------------------------
# 4 — les licences de modèles

#: Les trois fichiers qui citent les licences. Elles sont écrites trois fois ; c'est trois
#: occasions de diverger, et une licence fausse n'est pas une coquille — le dépôt est AGPL et
#: la licence d'un poids décide de ce qu'on a le droit de redistribuer.
DOCUMENTS_DE_LICENCE = ("manga_models/README.md", "docs/ai-provenance.md",
                        "docs/chiffres-de-reference.md")

_LICENCE = re.compile(r"\b(A?GPL-3\.0|Apache-2\.0|MIT|CC-BY(?:-[A-Z]+)*(?:-\d\.\d)?)\b")


def _licences_declarees(texte: str, modele: str) -> set[str]:
    """Les licences citées sur les lignes qui nomment `modele`."""
    trouvees: set[str] = set()
    for ligne in texte.splitlines():
        if modele in ligne:
            trouvees.update(_LICENCE.findall(ligne))
    return trouvees


def _modeles_de_reference() -> dict[str, str]:
    """Le tableau « Licences des modèles » de `docs/chiffres-de-reference.md`, qui fait foi."""
    texte = REFERENCE.read_text(encoding="utf-8")
    debut = texte.index("### Licences des modèles")
    # ⚠ Pas `texte.index("---", debut)` : la ligne de séparation d'un tableau markdown
    # (`|---|---|---|`) contient `---` et couperait le bloc avant sa première ligne.
    bloc = texte[debut:texte.index(chr(10) + "## ", debut)]
    modeles = {}
    for ligne in bloc.splitlines():
        m = re.match(r"^\|\s*`([^`]+)`[^|]*\|\s*(.*?)\s*\|", ligne)
        if m:
            licences = _LICENCE.findall(m.group(2))
            if licences:
                modeles[m.group(1)] = licences[0]
    return modeles


def test_le_tableau_des_licences_est_lisible():
    modeles = _modeles_de_reference()
    assert len(modeles) >= 2, modeles


@pytest.mark.parametrize("document", DOCUMENTS_DE_LICENCE)
def test_les_licences_concordent_entre_les_trois_documents(document: str):
    texte = _lire(document)
    for modele, attendue in _modeles_de_reference().items():
        declarees = _licences_declarees(texte, modele)
        if not declarees:
            continue  # ce document ne se prononce pas sur ce modèle — légitime
        assert attendue in declarees, (
            f"{document} déclare {sorted(declarees)} pour `{modele}`, alors que "
            f"docs/chiffres-de-reference.md déclare {attendue}. Une licence de poids décide "
            f"de ce qu'on a le droit de redistribuer : deux réponses valent zéro réponse.")
