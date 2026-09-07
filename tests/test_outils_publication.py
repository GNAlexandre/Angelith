# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`tools/preparer_publication.py` — l'anonymisation de l'arbre publié, en une commande.

## Ce que ces tests protègent

La publication transpose l'arbre par `git read-tree --reset -u main`, ce qui **écrase tout ce
qui était propre à la branche publique**. Entre le 2026-09-06 et le 2026-09-07 la séquence a
été rejouée cinq fois à la main ; deux artefacts de purge en sont sortis — « *manga A Zero
manga A* » et « *manga A <reste du titre>* » — que personne n'avait vus.

⚠ **Aucun test de ce fichier n'écrit dans l'arbre du dépôt.** Ils travaillent sur des textes
fabriqués et sur une table de correspondance de `tmp_path` : l'outil, lui, réécrit 73 fichiers,
et un test qui le lancerait pour de vrai anonymiserait le dépôt de travail.

## ⚠ Le test qui compte le plus

`test_l_outil_ne_contient_aucun_titre` : ce fichier-ci et l'outil sont **publiés**. Y recopier
la correspondance publierait les titres avec l'outil qui sert à les retirer — c'est la raison
d'être de sa conception, et un test la garde plutôt qu'un commentaire.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools import preparer_publication as pub

RACINE = Path(__file__).resolve().parent.parent

#: Un saut de ligne, jamais écrit en littéral dans ce dépôt — cf. la
#: constante `SAUT_LIGNE` de `gui/dialogues.py`, posée pour la même raison.
NL = chr(10)

#: Une table FABRIQUÉE : aucun titre réel n'entre dans ce fichier, cf. l'en-tête.
PAIRES = [("Grand Titre Complet", "manga A"), ("Titre Complet", "manga A"),
          ("Grand Titre", "manga B"), ("Autre_Chose", "roman_T")]


def _table(tmp_path: Path, lignes: list[str]) -> Path:
    fichier = tmp_path / "procedure.md"
    corps = "\n".join(lignes)
    fichier.write_text(
        f"# Procédure\n\n<!-- correspondances:début -->\n```text\n{corps}\n```\n"
        f"<!-- correspondances:fin -->\n", encoding="utf-8")
    return fichier


# --------------------------------------------------------------------------- #
#  La table vit dans le fichier privé, et son absence se DIT
# --------------------------------------------------------------------------- #

def test_une_table_absente_leve_au_lieu_de_rendre_vide(tmp_path):
    """⚠ C'est l'état de la branche `public`, où le fichier est retiré de l'arbre. Rendre une
    liste vide y ferait passer la préparation au vert sans avoir rien anonymisé."""
    with pytest.raises(pub.CorrespondancesIndisponibles, match="absent"):
        pub.correspondances(tmp_path / "nulle-part.md")


def test_un_bloc_supprime_est_une_erreur(tmp_path):
    fichier = tmp_path / "procedure.md"
    fichier.write_text("# Procédure\n\nPlus de bloc ici.\n", encoding="utf-8")
    with pytest.raises(pub.CorrespondancesIndisponibles, match="correspondances"):
        pub.correspondances(fichier)


def test_un_bloc_vide_est_une_erreur(tmp_path):
    with pytest.raises(pub.CorrespondancesIndisponibles, match="vide"):
        pub.correspondances(_table(tmp_path, []))


def test_la_table_se_lit_dans_l_ordre_du_fichier(tmp_path):
    """⚠ **L'ordre EST la donnée.** Le plus long d'abord : l'inverse laisserait la queue du
    titre derrière l'étiquette — c'est exactement ce qui a produit « manga A <reste du titre> »
    dans l'arbre, resté là jusqu'au 2026-09-07."""
    lues = pub.correspondances(_table(tmp_path, ["B = deux", "A = un"]))
    assert lues == [("B", "deux"), ("A", "un")]


# --------------------------------------------------------------------------- #
#  L'anonymisation
# --------------------------------------------------------------------------- #

def test_le_titre_le_plus_long_est_pris_en_premier():
    texte, compte = pub.anonymiser("voir Grand Titre Complet ici", PAIRES)
    assert texte == "voir manga A ici"
    assert compte == 1


def test_un_titre_coupe_par_un_retour_a_la_ligne_est_pris():
    """⚠ **La forme la plus fréquente dans ce dépôt** : la prose est enroulée à 98 colonnes et
    vit largement dans des commentaires, si bien qu'une coupure tombe au milieu d'un titre une
    fois sur trois. Le premier passage manuel, ligne à ligne, les laissait toutes."""
    texte, _ = pub.anonymiser("sur Grand\n# Titre Complet, page 4", PAIRES)
    assert "manga A" in texte
    assert "Titre" not in texte


def test_la_casse_n_arrete_pas_le_remplacement():
    texte, _ = pub.anonymiser("GRAND TITRE COMPLET", PAIRES)
    assert texte == "manga A"


def test_l_elision_est_corrigee():
    """Un titre commençant par une voyelle donnait « de manga A » : pas du français, et aucun
    relecteur humain ne repasse derrière l'outil."""
    texte, _ = pub.anonymiser("les planches d'Grand Titre Complet", PAIRES)
    assert texte == "les planches de manga A"


def test_le_tiret_bas_est_conserve():
    """⚠ `tests/test_core_chemins.py` se sert de ces noms comme exemples de nom d'œuvre
    ORDINAIRE, et la variété des formes est ce qu'il vérifie. Un libellé à espace lui ferait
    perdre son cas."""
    texte, _ = pub.anonymiser("le projet Autre_Chose", PAIRES)
    assert texte == "le projet roman_T"


def test_un_mot_qui_contient_le_titre_n_est_pas_touche():
    """Bornes de mot : sans elles, un titre court mangerait ses voisins."""
    texte, compte = pub.anonymiser("Titre Completement autre", PAIRES)
    assert compte == 0 and texte == "Titre Completement autre"


# --------------------------------------------------------------------------- #
#  ⚠ Le filet : un libellé doublé arrête la publication
# --------------------------------------------------------------------------- #

def test_un_libelle_double_est_detecte():
    """⚠ **Il a servi dès son premier essai**, le 2026-09-07 : il a trouvé deux artefacts de
    purge antérieurs dans l'arbre — « *manga A Zero manga A* » et « *manga A <reste du titre>* ».
    Publier du charabia est pire que publier un titre : le second se voit."""
    assert pub.doublons("mesuré sur manga A manga A Vol.2", PAIRES) == ["manga A"]


def test_un_texte_sain_ne_declenche_pas_le_filet():
    assert pub.doublons("manga A et manga B", PAIRES) == []


# --------------------------------------------------------------------------- #
#  Le réenroulement — SEULEMENT ce que l'anonymisation a rallongé
# --------------------------------------------------------------------------- #

def test_une_ligne_rallongee_est_reenroulee():
    avant = "# court\n"
    apres = "# " + "mot " * 60 + "\n"
    assert max(len(x) for x in pub.reenrouler(avant, apres).splitlines()) <= pub.COLONNES


def test_une_ligne_deja_longue_AVANT_n_est_pas_touchee():
    """⚠ Le dépôt porte des lignes longues légitimes — tableaux Markdown, prose CJK, données.
    Les enrouler toutes produirait un diff de publication illisible."""
    longue = "| " + " | ".join(["colonne"] * 30) + " |\n"
    assert pub.reenrouler(longue, longue) == longue


def test_le_prefixe_de_commentaire_est_reconduit():
    """Sans lui, la continuation d'un commentaire deviendrait du code."""
    apres = "#: " + "mot " * 60 + "\n"
    lignes = pub.reenrouler("#: court\n", apres).splitlines()
    assert len(lignes) > 1
    assert all(x.startswith("#: ") for x in lignes)


# --------------------------------------------------------------------------- #
#  ⚠ L'outil est PUBLIÉ : il ne doit porter aucun titre
# --------------------------------------------------------------------------- #

def test_l_outil_ne_contient_aucun_titre():
    """**Le test qui compte le plus.** `tools/preparer_publication.py` et ce fichier-ci sont
    publiés ; y recopier la correspondance publierait les titres avec l'outil qui sert à les
    retirer. C'est la raison d'être de sa conception, et elle mérite un test plutôt qu'un
    commentaire."""
    from tools import verifier_arbre

    try:
        motifs = verifier_arbre.motifs_de_fuite()
    except verifier_arbre.MotifsIndisponibles:
        pytest.skip("branche publiée : la liste des motifs n'y est pas, par construction")
    for chemin in ("tools/preparer_publication.py", "tests/test_outils_publication.py"):
        texte = (RACINE / chemin).read_text(encoding="utf-8")
        for motif in motifs:
            assert motif.lower() not in texte.lower(), f"{chemin} porte « {motif} »"


def test_la_table_reelle_est_lisible_et_ordonnee():
    """Sur le vrai fichier — et ignoré là où il n'est pas, c'est-à-dire dans l'arbre publié."""
    try:
        paires = pub.correspondances()
    except pub.CorrespondancesIndisponibles:
        pytest.skip("branche publiée : la procédure n'y est pas, par construction")
    assert len(paires) >= 10
    titres = [t for t, _ in paires]
    # ⚠ **La règle d'ordre, et elle est la seule qui compte** : si un titre en CONTIENT un
    # autre, le plus long doit venir en premier. L'inverse laisse la queue du titre derrière
    # l'étiquette — c'est ce qui a produit « manga A <reste du titre> » dans l'arbre.
    for i, court in enumerate(titres):
        for long in titres[i + 1:]:
            assert court.lower() not in long.lower(), (
                f"« {court} » est un morceau de « {long} » mais le précède : la cascade est "
                f"garantie. Remonte le plus long dans le bloc de correspondances.")


# --------------------------------------------------------------------------- #
#  Le retrait du job de l'arbre publié
# --------------------------------------------------------------------------- #

WORKFLOW = """name: CI

jobs:
  tests:
    runs-on: ubuntu-latest

  # Un commentaire qui appartient au job suivant.
  sonar:
    needs: [tests]
    steps:
      - run: scan

  artefact:
    runs-on: windows-latest
"""


def test_le_job_est_retire_avec_son_commentaire():
    """⚠ Le commentaire qui PRÉCÈDE un job lui appartient : le laisser ferait flotter une
    explication au-dessus du job suivant, qu'elle ne décrit pas."""
    sortie = pub.retirer_job(WORKFLOW, "sonar", "  # retiré\n\n")
    assert "sonar:" not in sortie
    assert "Un commentaire qui appartient" not in sortie
    assert "artefact:" in sortie and "tests:" in sortie


def test_retirer_un_job_absent_ne_change_rien():
    """La préparation doit pouvoir se rejouer sans casser ce qu'elle a déjà fait."""
    assert pub.retirer_job(WORKFLOW, "inexistant", "  # x\n") == WORKFLOW


def test_le_workflow_reste_du_yaml_valide():
    import yaml

    charge = yaml.safe_load(pub.retirer_job(WORKFLOW, "sonar", "  # retiré\n\n"))
    assert sorted(charge["jobs"]) == ["artefact", "tests"]


# --------------------------------------------------------------------------- #
#  ⚠ Un refus ne laisse pas l'arbre à moitié anonymisé
# --------------------------------------------------------------------------- #

def test_un_refus_n_ecrit_rien(tmp_path, monkeypatch):
    """**Le défaut de la première version**, trouvé en publiant pour de vrai : elle écrivait au
    fil de l'eau et ne levait qu'à la fin. Un refus laissait donc l'arbre à moitié anonymisé —
    l'état le plus difficile à reprendre. « Il refuse de publier » doit vouloir dire que rien
    n'a bougé."""
    sain = tmp_path / "sain.md"
    sain.write_text("voir Grand Titre Complet ici" + NL, encoding="utf-8")
    cascade = tmp_path / "cascade.md"
    cascade.write_text("voir Grand Titre Complet Grand Titre Complet ici" + NL,
                       encoding="utf-8")
    avant = {f: f.read_text(encoding="utf-8") for f in (sain, cascade)}

    monkeypatch.setattr(pub, "RACINE", tmp_path)
    monkeypatch.setattr(pub, "correspondances", lambda *a, **k: PAIRES)
    monkeypatch.setattr(pub, "fichiers_suivis", lambda: ["sain.md", "cascade.md"])

    with pytest.raises(SystemExit, match="RIEN N'A ÉTÉ ÉCRIT"):
        pub.preparer(dire=lambda *a, **k: None)

    for fichier, contenu in avant.items():
        assert fichier.read_text(encoding="utf-8") == contenu, f"{fichier.name} a été touché"


def test_l_exception_au_controle_reste_courte():
    """⚠ Chaque nom épargné est un endroit où un vrai remplacement en cascade passerait. Les
    deux qui y sont **parlent** du contrôle et en portent l'exemple — se signaler soi-même
    n'apprend rien, exactement comme `verifier_arbre.py` exclut le fichier de ses motifs.

    Documenter le contrôle ailleurs se fait sans écrire l'exemple littéralement, et le
    CHANGELOG le fait : ce test l'exige."""
    assert pub.EPARGNE_DOUBLONS == {"tools/preparer_publication.py",
                                    "tests/test_outils_publication.py"}
    changelog = (RACINE / "CHANGELOG.md").read_text(encoding="utf-8")
    doublon = "manga A" + " " + "manga A"
    assert doublon not in changelog, (
        "le CHANGELOG porte l'exemple littéral : il devrait le décrire, pas l'écrire")


# --------------------------------------------------------------------------- #
#  ⚠ On n'enroule JAMAIS du code
#
#  Trouvé à la deuxième utilisation réelle de l'outil : le réenroulement a coupé une ligne de
#  code contenant une chaîne littérale, produisant quinze erreurs de syntaxe. Enrouler de la
#  prose est cosmétique ; enrouler du code est destructeur.
# --------------------------------------------------------------------------- #

def test_une_ligne_de_code_python_n_est_jamais_enroulee():
    code = "    out = fonction(a, \"une chaîne " + "très " * 40 + "longue\")" + NL
    assert pub.reenrouler("    out = fonction(a)" + NL, code, python=True) == code


def test_un_commentaire_python_reste_enroulable():
    """La prose des commentaires, elle, doit suivre les 96 colonnes du dépôt."""
    apres = "# " + "mot " * 60 + NL
    lignes = pub.reenrouler("# court" + NL, apres, python=True).splitlines()
    assert len(lignes) > 1 and all(x.startswith("# ") for x in lignes)


def test_une_ligne_de_tableau_markdown_n_est_pas_coupee():
    """Une ligne de tableau coupée cesse d'être un tableau."""
    ligne = "| " + " | ".join(["cellule très longue"] * 8) + " |" + NL
    assert pub.reenrouler("| a |" + NL, ligne) == ligne


def test_un_bloc_indente_n_est_pas_coupe():
    """Quatre espaces en Markdown, c'est du code affiché."""
    ligne = "    " + "mot " * 40 + NL
    assert pub.reenrouler("    court" + NL, ligne) == ligne


@pytest.mark.parametrize("ligne,python,attendu", [
    ("# un commentaire", True, True),
    ("    x = 1", True, False),
    ('    """docstring"""', True, False),
    ("de la prose", False, True),
    ("| a | b |", False, False),
    ("```python", False, False),
])
def test_ce_qui_est_enroulable(ligne, python, attendu):
    assert pub.enroulable(ligne, python=python) is attendu


# --------------------------------------------------------------------------- #
#  ⚠ Le contrôle qui PROUVE : le Python produit doit encore s'analyser
# --------------------------------------------------------------------------- #

def test_un_python_casse_arrete_tout_sans_rien_ecrire(tmp_path, monkeypatch):
    """`enroulable` empêche, ce contrôle-ci **prouve** — et les deux ne font pas double emploi :
    le premier est une heuristique sur la forme des lignes, le second une vérification sur ce
    qui sortirait. Sans lui, l'outil a produit quinze erreurs de syntaxe à sa deuxième
    utilisation réelle, et c'est un linter lancé après, à la main, qui les a vues."""
    fichier = tmp_path / "casse.py"
    fichier.write_text('x = "Grand Titre Complet' + NL, encoding="utf-8")   # guillemet ouvert
    avant = fichier.read_text(encoding="utf-8")

    monkeypatch.setattr(pub, "RACINE", tmp_path)
    monkeypatch.setattr(pub, "correspondances", lambda *a, **k: PAIRES)
    monkeypatch.setattr(pub, "fichiers_suivis", lambda: ["casse.py"])

    with pytest.raises(SystemExit, match="casserait du code Python"):
        pub.preparer(dire=lambda *a, **k: None)
    assert fichier.read_text(encoding="utf-8") == avant


def test_un_python_sain_passe(tmp_path, monkeypatch):
    """Iso : le contrôle ne doit pas refuser ce qui compile."""
    fichier = tmp_path / "sain.py"
    fichier.write_text("# voir Grand Titre Complet" + NL + "x = 1" + NL, encoding="utf-8")

    monkeypatch.setattr(pub, "RACINE", tmp_path)
    monkeypatch.setattr(pub, "correspondances", lambda *a, **k: PAIRES)
    monkeypatch.setattr(pub, "fichiers_suivis", lambda: ["sain.py"])
    monkeypatch.setattr(pub, "CORRECTIFS", ())

    pub.preparer(dire=lambda *a, **k: None)
    assert "manga A" in fichier.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
#  ⚠ Le tiret bas ne doit pas arrêter le remplacement
#
#  `\b` ne s'active qu'entre un caractère de mot et un autre qui n'en est pas — or le TIRET BAS
#  en est un. Un titre suivi de « _Vol.1 » restait donc en clair, à côté du même titre remplacé
#  une ligne plus haut : un fichier à moitié anonymisé, et un test rendu incohérent.
# --------------------------------------------------------------------------- #

def test_un_titre_suivi_d_un_tiret_bas_est_remplace():
    """**Le défaut du lot 49**, trouvé par la suite de tests de l'arbre publié — pas par le
    contrôle de fuite, qui était aveugle à ce titre-là (cf. le test de l'invariant plus bas)."""
    texte, compte = pub.anonymiser("Grand Titre Complet_Vol.1_glossaire.yaml", PAIRES)
    assert texte == "manga A_Vol.1_glossaire.yaml"
    assert compte == 1


def test_un_titre_precede_d_un_tiret_bas_aussi():
    texte, _ = pub.anonymiser("prefixe_Grand Titre Complet", PAIRES)
    assert texte == "prefixe_manga A"


def test_l_ordre_protege_les_titres_a_tiret_bas():
    """⚠ **La contrepartie de la borne assouplie.** Sans `\b`, un titre court peut se
    retrouver DANS un titre long qui le contient. C'est l'ordre de la table — le plus long
    d'abord — qui l'empêche, et le test de l'invariant ci-dessous en fait une règle."""
    paires = [("Autre_Chose_Longue", "roman_U"), ("Autre_Chose", "roman_T")]
    texte, _ = pub.anonymiser("le projet Autre_Chose_Longue ici", paires)
    assert texte == "le projet roman_U ici"


# --------------------------------------------------------------------------- #
#  ⚠ L'INVARIANT : le correcteur et le garde-fou partagent leur liste
# --------------------------------------------------------------------------- #

def test_tout_titre_de_la_table_est_visible_du_garde_fou():
    """**Le test qui aurait évité tout le lot 49.**

    L'anonymisation lit la table de correspondance ; le contrôle de fuite lit le bloc de
    motifs. Ce sont deux listes, dans deux blocs, et **elles ont divergé** : cinq titres
    découverts au lot 40 avaient été ajoutés à la première et jamais à la seconde. Le garde-fou
    annonçait donc « 0 infraction » sur des arbres où ces titres pouvaient rester — ce qui est
    exactement arrivé, et que seule la suite de tests de l'arbre publié a fini par montrer.

    Un correcteur et un garde-fou qui ne partagent pas leur liste finissent par diverger. La
    règle : **tout titre corrigé doit être détectable**, c'est-à-dire contenir au moins un
    motif."""
    from tools import verifier_arbre

    try:
        motifs = [m.lower() for m in verifier_arbre.motifs_de_fuite()]
        table = pub.correspondances()
    except (verifier_arbre.MotifsIndisponibles, pub.CorrespondancesIndisponibles):
        pytest.skip("branche publiée : les deux blocs n'y sont pas, par construction")

    invisibles = [titre for titre, _ in table
                  if not any(motif in titre.lower() for motif in motifs)]
    assert not invisibles, (
        f"le garde-fou ne verrait pas {invisibles} : ces titres seraient corrigés sans que "
        f"rien ne vérifie qu'ils l'ont bien été. Ajoute-les au bloc de motifs.")
