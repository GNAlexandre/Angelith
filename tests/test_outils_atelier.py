# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Les cinq garde-fous du lot 20, testés sans dépôt git et sans réseau.

## Pourquoi ces tests existent

Un garde-fou de CI qui n'est vérifié que par la CI a un défaut particulier : on ne découvre
qu'il est faux qu'au moment où il refuse à tort une PR pressée — c'est-à-dire au pire moment,
celui où on le désarme. Chacun des quatre outils est donc écrit en deux couches : un cœur qui
JUGE, pur, et une mince couche qui appelle `git`. C'est le cœur qui est testé ici.

Les cinq :

- `tools/verifier_disclosure.py` — la disclosure IA de `CONTRIBUTING.md` ;
- `tools/verifier_arbre.py` — fuite, corpus, poids de modèles ;
- `tools/verifier_livraison.py` — CHANGELOG, version, prompts, tableau daté ;
- `tools/compte_de_tests.py` — le compte collecté, et sa comparaison entre deux OS ;
- `tools/notes_de_version.py` — les notes de release découpées dans le CHANGELOG.
"""
from __future__ import annotations

import pytest

from tools import (
    compte_de_tests,
    notes_de_version,
    verifier_arbre,
    verifier_disclosure,
    verifier_livraison,
)

# ---------------------------------------------------------------------------
# Disclosure IA

CONFORME = """feat(manga): typer les bulles à partir de leur géométrie

Assisté par : Claude Code (claude-opus-5), 2026-08-27
Prompt : « classifieur déterministe de type de bulle »
Revu et testé manuellement : oui
"""


def _analyser(message: str, **kw):
    return verifier_disclosure.analyser("abc1234", "sujet", message, **kw)


def test_un_commit_au_format_est_conforme_et_fusionnable():
    v = _analyser(CONFORME)
    assert v.conforme and v.fusionnable, v.motifs


def test_un_commit_ecrit_a_la_main_se_declare_et_passe():
    """« Assisté par : aucun » est légitime : une correction de coquille n'a pas de prompt.
    Ce qui ne l'est pas, c'est l'ABSENCE de ligne — elle ne distingue pas « écrit à la main »
    de « oublié »."""
    v = _analyser("fix: coquille\n\nAssisté par : aucun\n"
                  "Revu et testé manuellement : oui\n")
    assert v.conforme and v.fusionnable, v.motifs


def test_l_absence_de_disclosure_est_refusee():
    v = _analyser("fix: coquille dans un commentaire\n")
    assert not v.conforme
    assert "Assisté par" in v.motifs[0]


def test_une_assistance_sans_modele_ni_date_est_refusee():
    """« Claude Code » seul ne permet ni de rejouer ni de dater une génération — or c'est
    exactement ce que la politique de financement demande de pouvoir faire."""
    v = _analyser("feat: x\n\nAssisté par : Claude Code\nPrompt : « x »\n"
                  "Revu et testé manuellement : oui\n")
    assert not v.conforme
    assert any("date ISO" in m for m in v.motifs)


def test_une_assistance_sans_prompt_est_refusee():
    v = _analyser("feat: x\n\nAssisté par : Claude Code (claude-opus-5), 2026-08-27\n"
                  "Revu et testé manuellement : oui\n")
    assert not v.conforme
    assert any("Prompt" in m for m in v.motifs)


def test_non_relu_passe_le_job_mais_bloque_la_fusion():
    """La distinction qui décide de tout : une déclaration honnête n'est pas une faute de
    format. Le job reste vert, la fusion attend un humain."""
    v = _analyser(CONFORME.replace("manuellement : oui", "manuellement : non"))
    assert v.conforme
    assert not v.fusionnable


def test_un_verdict_de_relecture_illisible_est_refuse():
    """Cas RÉEL de l'historique : « Revu et testé manuellement : linter et tests automatiques
    passés ». C'est une phrase, pas un verdict — on ne peut ni la compter ni s'y fier."""
    v = _analyser(CONFORME.replace("manuellement : oui",
                                   "manuellement : linter et tests automatiques passés"))
    assert not v.conforme
    assert any("ni par" in m for m in v.motifs)


def test_l_accent_perdu_ne_fait_pas_refuser():
    """Une console Windows en cp1252 fait tomber un caractère non-ASCII : refuser là-dessus
    serait refuser sur un défaut d'encodage, pas sur un défaut de traçabilité."""
    v = _analyser(CONFORME.replace("Assisté", "Assiste").replace("testé", "teste"))
    assert v.conforme, v.motifs


def test_un_commit_de_fusion_est_exempte():
    v = _analyser("Merge pull request #2 from GNAlexandre/lot-18", fusion=True)
    assert v.conforme and v.fusionnable


def test_un_commit_de_robot_est_exempte():
    """Sans cette exemption, chaque PR de Dependabot — que ce lot met en place — deviendrait
    rouge le jour où le garde-fou devient bloquant. L'exemption est nommée maintenant plutôt
    que découverte à ce moment-là."""
    v = _analyser("chore(deps): bump numpy", auteur="dependabot[bot]")
    assert v.conforme and v.fusionnable
    assert any("robot" in m for m in v.motifs)


def test_un_auteur_humain_n_est_pas_pris_pour_un_robot():
    assert not verifier_disclosure.est_un_robot("Alexandre Tournel")
    assert verifier_disclosure.est_un_robot("github-actions[bot]")


def test_le_rendu_markdown_publie_le_taux():
    verdicts = [_analyser(CONFORME), _analyser("fix: rien\n")]
    rendu = verifier_disclosure.rendre(verdicts, markdown=True)
    assert "1/2" in rendu and "50 %" in rendu


# ---------------------------------------------------------------------------
# Arbre : fuite, corpus, poids

@pytest.mark.parametrize("chemin", ["manga_models/bubble_detector.onnx",
                                    "poids/modele.safetensors", "x/y/z.pt"])
def test_un_poids_de_modele_est_refuse(chemin):
    infractions = verifier_arbre.juger_chemin(chemin)
    assert [i.regle for i in infractions] == ["poids"]


def test_bin_n_est_pas_traite_comme_un_poids():
    """`.bin` attraperait trop de fichiers légitimes ; un garde-fou désarmé au premier faux
    positif ne protège plus rien."""
    assert verifier_arbre.juger_chemin("data/quelque_chose.bin") == []


@pytest.mark.parametrize("chemin", ["sources/Titre/Vol.1/p001.jpg",
                                    "build/Titre/Vol.1/RAPPORT.md"])
def test_un_fichier_de_corpus_ou_de_sortie_est_refuse(chemin):
    infractions = verifier_arbre.juger_chemin(chemin)
    assert any(i.regle == "corpus" for i in infractions)


def test_la_liste_noire_ne_s_arme_qu_a_la_publication():
    """`docs/PUBLICATION-ANGELITH.md` est LÉGITIMEMENT suivi sur les branches de dev — c'est
    écrit dans `.gitignore`. L'armer à chaque PR rendrait rouge toute PR qui touche la
    procédure de publication, pour l'avoir touchée."""
    chemin = "docs/PUBLICATION-ANGELITH.md"
    assert verifier_arbre.juger_chemin(chemin) == []
    assert [i.regle for i in verifier_arbre.juger_chemin(chemin, publication=True)] \
        == ["publication"]


def test_un_titre_d_oeuvre_dans_un_ajout_est_refuse():
    infractions = verifier_arbre.juger_contenu(
        "manga/detection.py", "# mesuré sur Titre Fictif Vol.1", ["Titre Fictif"])
    assert [i.regle for i in infractions] == ["fuite"]


def test_le_message_de_fuite_ne_repete_pas_le_titre():
    """Le garde-fou ne doit pas publier dans son propre message ce qu'il interdit d'écrire —
    le journal d'une CI publique est aussi lisible que le fichier."""
    (infraction,) = verifier_arbre.juger_contenu(
        "manga/detection.py", "# mesuré sur Titre Fictif Vol.1", ["Titre Fictif"])
    assert "Titre Fictif" not in str(infraction)


def test_un_binaire_n_est_pas_analyse_pour_son_contenu():
    assert verifier_arbre.juger_contenu("docs/img/capture.png", "Titre Fictif",
                                        ["Titre Fictif"]) == []


def test_le_fichier_qui_porte_les_motifs_ne_se_denonce_pas_lui_meme():
    assert verifier_arbre.juger_contenu("docs/PUBLICATION-ANGELITH.md", "Titre Fictif",
                                        ["Titre Fictif"]) == []


def test_les_motifs_absents_sont_une_erreur_pas_un_silence(tmp_path):
    """Un garde-fou qui ignore ce qu'il cherche doit se déclarer aveugle. Rendre une liste
    vide le ferait passer au vert sur la branche `public`, où le fichier n'existe pas."""
    with pytest.raises(verifier_arbre.MotifsIndisponibles):
        verifier_arbre.motifs_de_fuite(tmp_path / "absent.md")


def test_un_bloc_de_motifs_supprime_est_une_erreur(tmp_path):
    fichier = tmp_path / "procedure.md"
    fichier.write_text("# Publier\n\nPlus de bloc de motifs ici.\n", encoding="utf-8")
    with pytest.raises(verifier_arbre.MotifsIndisponibles, match="motifs-de-fuite"):
        verifier_arbre.motifs_de_fuite(fichier)


@pytest.mark.skipif(not verifier_arbre.SOURCE_DES_MOTIFS.is_file(),
                    reason="la procédure de publication n'est pas dans l'arbre publié")
def test_les_motifs_se_lisent_dans_la_procedure_reelle():
    """Le bloc vit dans `docs/PUBLICATION-ANGELITH.md` et nulle part ailleurs : le recopier
    dans un fichier publié publierait les titres avec l'outil.

    ⚠ **D'où le `skipif`** : ce test décrit une propriété de la branche de DÉVELOPPEMENT. Le
    fichier est retiré de l'arbre publié — c'est tout l'objet du dispositif —, donc la
    propriété y est fausse par construction. Sans ce garde, l'arbre publié embarque un test
    rouge dès le premier clone."""
    motifs = verifier_arbre.motifs_de_fuite()
    assert len(motifs) >= 5
    assert all(m.strip() == m and m for m in motifs)


def test_seules_les_lignes_ajoutees_sont_extraites_d_un_diff():
    diff = ("--- a/manga/x.py\n+++ b/manga/x.py\n@@ -1,2 +1,2 @@\n"
            "-ancienne ligne\n+nouvelle ligne\n contexte\n")
    assert verifier_arbre.lignes_ajoutees_texte(diff) == {"manga/x.py": "nouvelle ligne"}


# ---------------------------------------------------------------------------
# Discipline de livraison

def _juger(fichiers, *, ajoute="", non_publie=False, etiquettes=None):
    return verifier_livraison.juger(fichiers, changelog_ajoute=ajoute,
                                    ajout_sous_non_publie=non_publie,
                                    etiquettes=etiquettes or set())


def test_toucher_le_produit_sans_changelog_est_refuse():
    motifs = _juger(["manga/detection.py"])
    assert motifs and "CHANGELOG" in motifs[0]


def test_l_etiquette_sans_changelog_est_l_echappatoire_nommee():
    assert _juger(["manga/detection.py"], etiquettes={"sans-changelog"}) == []


def test_toucher_l_outillage_seul_n_exige_pas_de_changelog():
    """`tools/`, `tests/` et `docs/` ne changent rien à ce qu'un tome produit. Exiger une
    entrée pour eux banaliserait l'entrée jusqu'à la vider de sens."""
    assert _juger(["tools/banc.py", "tests/test_manga_clean.py", "docs/roadmap.md"]) == []


def test_un_changelog_date_sans_bump_de_version_est_refuse():
    motifs = _juger(["manga/detection.py", "CHANGELOG.md"], ajoute="### CORRECTIF — x")
    assert any("core/version.py" in m for m in motifs)


def test_un_ajout_sous_non_publie_dispense_du_bump():
    assert _juger(["manga/detection.py", "CHANGELOG.md"], ajoute="### x",
                  non_publie=True) == []


def test_un_bump_de_version_dispense_de_la_section_non_publie():
    # ⚠ `installeur/version.iss` depuis le lot 37 : la règle 5 veut que l'artefact
    # d'empaquetage suive la version. Cf. `test_un_bump_de_version_entraine_l_installeur`.
    assert _juger(["manga/detection.py", "CHANGELOG.md", "core/version.py",
                   "installeur/version.iss"],
                  ajoute="## [2.11.0] - 2026-08-28") == []


def test_un_bump_de_version_entraine_l_installeur():
    """Règle 5 (lot 37). L'installeur porte son numéro dans un fichier GÉNÉRÉ ; un
    `core/version.py` qui bouge sans lui produirait un installeur qui annonce la version
    précédente — et personne ne relit un `.iss`."""
    motifs = _juger(["manga/detection.py", "CHANGELOG.md", "core/version.py"],
                    ajoute="## [2.11.0] - 2026-08-28")
    assert any("installeur/version.iss" in m for m in motifs), motifs
    assert any("generer.py" in m for m in motifs), motifs


def test_sans_bump_de_version_l_installeur_n_est_pas_exige():
    """La règle ne se déclenche que sur un changement de `core/version.py` : un correctif sous
    `[Non publié]` n'a pas d'installeur à régénérer."""
    assert _juger(["manga/detection.py", "CHANGELOG.md"],
                  ajoute="## [Non publié]\nun correctif", non_publie=True) == []


def test_un_prompt_modifie_doit_etre_nomme_dans_le_changelog():
    """Sans le nom du fichier, `git checkout <tag> -- langues/` ne dit pas quelle voix
    rejouer — et c'est littéralement ce que la règle de numérotation exige."""
    fichiers = ["langues/fr/prompts/traduction.md", "CHANGELOG.md", "core/version.py",
                "installeur/version.iss"]
    motifs = _juger(fichiers, ajoute="## [2.11.0] - 2026-08-28\nvoix retouchée")
    assert any("traduction.md" in m for m in motifs)

    assert _juger(fichiers,
                  ajoute="## [2.11.0] - 2026-08-28\nréécriture de `traduction.md`") == []


def test_un_tableau_de_banc_sans_date_dans_son_nom_est_refuse():
    motifs = _juger(["docs/mesures/banc-webtoon.md"])
    assert any("AAAA-MM-JJ" in m for m in motifs)


def test_le_tableau_date_passe_et_le_protocole_aussi():
    assert _juger(["docs/mesures/banc-2026-08-28.md"]) == []
    # La racine de docs/ reste jugée : un banc rangé au mauvais endroit doit être vu.
    assert _juger(["docs/banc-webtoon.md"])
    assert _juger(["docs/procedures/banc-de-mesure.md"]) == []


def test_la_section_non_publie_s_arrete_au_titre_suivant():
    """Elle ne s'arrête pas à la prochaine ligne vide ni au prochain `##` quelconque : une
    entrée de ce CHANGELOG porte des sous-titres `###`."""
    changelog = ("# Journal\n"
                 "## [Non publié]\n"
                 "### MINEUR — x\n"
                 "du texte\n"
                 "## [2.10.0] - 2026-08-27\n"
                 "autre chose\n")
    assert verifier_livraison.section_non_publie(changelog) == (2, 4)


def test_pas_de_section_non_publie_rend_none():
    assert verifier_livraison.section_non_publie("# Journal\n## [1.0.0] - 2026-01-01\n") is None


def test_les_numeros_de_lignes_ajoutees_suivent_les_entetes_de_hunk():
    diff = ("--- a/CHANGELOG.md\n+++ b/CHANGELOG.md\n"
            "@@ -3,0 +4,2 @@\n+ligne quatre\n+ligne cinq\n"
            "@@ -20,1 +22,1 @@\n-vieux\n+neuf\n")
    assert verifier_livraison.lignes_ajoutees_numerotees(diff) == [4, 5, 22]


# ---------------------------------------------------------------------------
# Compte de tests collectés

def test_la_forme_sans_marqueur_est_lue():
    assert compte_de_tests.analyser_sortie("2846 tests collected in 20.30s") == (2846, 2846, 0)


def test_la_forme_avec_deselection_est_lue():
    sortie = "2789/2846 tests collected (57 deselected) in 19.60s"
    assert compte_de_tests.analyser_sortie(sortie) == (2789, 2846, 57)


def test_une_sortie_sans_ligne_de_compte_leve():
    """⚠ Rendre 0 serait le pire choix possible : un compte de zéro se compare très bien à un
    autre compte de zéro, et le job passerait au vert sur une suite qui ne se charge plus."""
    with pytest.raises(compte_de_tests.CollecteIllisible, match="ERREUR DE COLLECTE"):
        compte_de_tests.analyser_sortie("ImportError: cannot import name 'x'")


def _releve(systeme, collectes, total=2846, deselectionnes=57, marqueurs="m"):
    return {"systeme": systeme, "collectes": collectes, "total": total,
            "deselectionnes": deselectionnes, "marqueurs": marqueurs, "python": "3.12.8"}


def test_deux_systemes_qui_voient_la_meme_suite_ne_produisent_aucun_ecart():
    assert compte_de_tests.comparer(_releve("windows", 2789), _releve("linux", 2789)) == []


def test_un_ecart_de_collecte_est_nomme_avec_les_deux_systemes():
    (ecart,) = compte_de_tests.comparer(_releve("windows", 2789), _releve("linux", 2650))
    assert "windows" in ecart and "linux" in ecart
    assert "2789" in ecart and "2650" in ecart


def test_comparer_deux_releves_de_marqueurs_differents_est_un_ecart():
    """Sinon on comparerait la boucle courte d'un OS au total de l'autre, et l'écart parlerait
    des marqueurs en ayant l'air de parler des systèmes."""
    ecarts = compte_de_tests.comparer(_releve("windows", 2789, marqueurs="a"),
                                      _releve("linux", 2789, marqueurs="b"))
    assert any("marqueurs" in e for e in ecarts)


# ---------------------------------------------------------------------------
# Notes de version

CHANGELOG_FACTICE = """# Journal des modifications

## [Non publié]

### MINEUR — travail en cours

## [2.10.0] - 2026-08-27

### MINEUR — le système visuel

Deux paragraphes de détail.

## [2.9.0] - 2026-08-27

Autre chose.
"""


def test_la_section_demandee_est_extraite_sans_son_titre():
    """GitHub affiche déjà le nom du tag au-dessus du corps : le répéter fait doublon."""
    date, corps = notes_de_version.extraire(CHANGELOG_FACTICE, "2.10.0")
    assert date == "2026-08-27"
    assert corps.startswith("### MINEUR — le système visuel")
    assert "Autre chose" not in corps
    assert "## [2.10.0]" not in corps


def test_le_v_du_tag_est_accepte():
    assert notes_de_version.extraire(CHANGELOG_FACTICE, "v2.10.0")[0] == "2026-08-27"


def test_la_derniere_section_va_jusqu_a_la_fin():
    _date, corps = notes_de_version.extraire(CHANGELOG_FACTICE, "2.9.0")
    assert corps.strip() == "Autre chose."


def test_une_version_non_datee_n_est_pas_publiable():
    """« [Non publié] » n'est pas une release : c'est la date qui distingue une version
    livrée d'un travail en cours."""
    with pytest.raises(notes_de_version.VersionIntrouvable):
        notes_de_version.extraire(CHANGELOG_FACTICE, "Non publié")


def test_une_version_inconnue_leve_avec_un_message_utile():
    with pytest.raises(notes_de_version.VersionIntrouvable, match="AAAA-MM-JJ"):
        notes_de_version.extraire(CHANGELOG_FACTICE, "9.9.9")


def test_le_changelog_reel_rend_les_notes_de_la_version_courante():
    """Le garde-fou qui compte : tag ⇄ `core/version.py` ⇄ CHANGELOG ne peuvent pas
    diverger. `tests/test_version.py` tient les deux derniers, celui-ci ferme la boucle."""
    from core.version import __version__
    changelog = (notes_de_version.CHANGELOG).read_text(encoding="utf-8")
    date, corps = notes_de_version.extraire(changelog, __version__)
    assert date and corps.strip()
