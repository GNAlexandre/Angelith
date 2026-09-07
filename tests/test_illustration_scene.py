# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""**L26.2, l'appel LLM facultatif** — la clause de scène, et ce qu'elle n'a pas le droit
de dire.

Le test central est `test_une_clause_qui_decrit_un_attribut_est_rejetee_ICI` : le filtre est
appliqué **dans ce module**, pas laissé à l'appelant. Un module qui rendrait la réponse brute
du modèle laisserait le prochain appelant décider s'il filtre, et le critère 4 du `PLAN-26`
deviendrait une convention plutôt qu'une garantie.

Le second est `test_le_plafond_de_jetons_ECARTE_des_passages_et_n_en_tronque_aucun` : « on
découpe, on ne tronque pas silencieusement ». Une phrase amputée décrirait une scène qui n'a
pas eu lieu, et le modèle n'aurait aucun moyen de le savoir.
"""
import pytest

from core import bible as bible_mod
from illustration import gabarits as gabarits_mod
from illustration import scene as scene_mod


@pytest.fixture
def tome(tmp_path):
    """Un tome à deux chapitres, dont un seul nomme le personnage."""
    chapitres = tmp_path / "chapters"
    chapitres.mkdir(parents=True)
    (chapitres / "ch01.md").write_text(
        "# Chapitre premier\n\n"
        "La tente sentait le désinfectant. Tory se pencha sur le brancard et pressa un "
        "pansement à deux mains. Dehors, la pluie tombait.\n\n"
        "Gabak jura. Personne ne répondit.\n",
        encoding="utf-8")
    (chapitres / "ch02.md").write_text(
        "# Chapitre deux\n\n"
        "Le major relut le rapport. Il ne dit rien pendant une minute entière.\n",
        encoding="utf-8")
    return tmp_path


@pytest.fixture
def entree():
    personnage = bible_mod.personnage("Tory Noelle")
    personnage["apparence"]["cheveux"] = "gris courts"
    personnage["citations"] = [{"attribut": "cheveux", "source": "chapters/ch01.md",
                                "texte": "cheveux gris"}]
    return personnage


@pytest.fixture
def gabarit():
    return gabarits_mod.charger("portrait", langue="fr")


# ══════════════════════════  Trouver les passages  ══════════════════════════

def test_les_passages_retenus_NOMMENT_le_personnage(tome, entree):
    liste, motifs = scene_mod.passages(tome, entree)
    assert motifs == []
    assert len(liste) == 1
    assert "brancard" in liste[0].texte
    assert liste[0].source == "chapters/ch01.md"


def test_un_personnage_que_le_tome_ne_nomme_pas_rend_un_motif(tome):
    """Pas une liste vide muette : un motif nommé. Le dépôt compte ses refus."""
    absent = bible_mod.personnage("Sylph Nova")
    liste, motifs = scene_mod.passages(tome, absent)
    assert liste == [] and motifs == ["aucun_passage"]


def test_le_lexique_d_APPARENCE_n_est_pas_reutilise_ici():
    """⚠ Se tromper de lexique aurait donné des clauses systématiquement rejetées par
    `prompt.epurer`, et le rejet aurait eu l'air d'un défaut du filtre.

    `core/bible_texte.py` cherche les phrases qui parlent de cheveux et d'yeux — exactement
    celles dont ce module ne veut pas. Ici on cherche les phrases qui **nomment** le
    personnage, et on laisse le modèle y trouver un geste."""
    source = scene_mod.passages.__doc__ + (scene_mod.__doc__ or "")
    assert "nomment" in source or "NOMMENT" in source
    assert "LEXIQUE" not in dir(scene_mod)


def test_la_recherche_est_a_la_FRONTIERE_DE_MOT(tmp_path):
    """`core/bible_texte.py` a payé ce défaut : en sous-chaîne, **1 257 des 1 565** passages
    candidats d'un tome étaient des faux — 80,3 %."""
    chapitres = tmp_path / "chapters"
    chapitres.mkdir(parents=True)
    (chapitres / "ch01.md").write_text(
        "Le torysme n'avait plus cours. Personne ne s'en souciait.\n", encoding="utf-8")
    entree = bible_mod.personnage("Tory")
    liste, motifs = scene_mod.passages(tmp_path, entree)
    assert liste == [] and motifs == ["aucun_passage"]


# ══════════════════  Le plafond de jetons — on découpe, on ne tronque pas  ══════════════════

def test_le_plafond_de_jetons_ECARTE_des_passages_et_n_en_tronque_aucun(tmp_path):
    """⚠ **La règle L26.4, mot pour mot** : « découpez, ne tronquez pas silencieusement ».

    Un chapitre entier n'entre pas dans les 24 000 jetons de `decoupage.max_input_tokens`.
    Le plafond mord donc sur le NOMBRE de passages, jamais au milieu d'une phrase : une phrase
    amputée décrirait une scène qui n'a pas eu lieu, et le modèle n'aurait aucun moyen de le
    savoir."""
    chapitres = tmp_path / "chapters"
    chapitres.mkdir(parents=True)
    longue = "Tory " + "marcha longtemps sous la pluie battante et grise " * 30 + "."
    (chapitres / "ch01.md").write_text(f"{longue}\n{longue}\n{longue}\n", encoding="utf-8")
    entree = bible_mod.personnage("Tory")

    complet, _ = scene_mod.passages(tmp_path, entree)
    assert len(complet) >= 2

    coupe, motifs = scene_mod.passages(tmp_path, entree, plafond_jetons=120)
    assert len(coupe) < len(complet)
    assert "plafond_jetons" in motifs
    # Aucun passage n'est tronqué : ceux qui restent sont IDENTIQUES aux originaux.
    assert all(p.texte in [c.texte for c in complet] for p in coupe)


def test_sans_plafond_tous_les_passages_passent(tome, entree):
    liste, motifs = scene_mod.passages(tome, entree, plafond_jetons=0)
    assert liste and motifs == []


# ══════════════════════════  Le filtre, appliqué ICI  ══════════════════════════

class _LLM:
    def __init__(self, reponse):
        self.reponse = reponse
        self.appels = 0

    def chat(self, *_a, **_k):
        self.appels += 1
        return self.reponse


def test_une_clause_PROPRE_est_rendue_telle_quelle(tome, entree, gabarit):
    liste, _ = scene_mod.passages(tome, entree)
    llm = _LLM("Agenouillée près d'un brancard, elle presse un pansement à deux mains.")
    clause, motifs = scene_mod.reformuler(llm, "yume-27b", "…", "Tory Noelle", liste, gabarit)
    assert clause.startswith("Agenouillée près d'un brancard")
    assert motifs == [] and llm.appels == 1


def test_une_clause_qui_decrit_un_attribut_est_rejetee_ICI(tome, entree, gabarit):
    """**Le test central du fichier.** Le filtre est appliqué dans ce module, pas laissé à
    l'appelant : sinon le critère 4 du `PLAN-26` serait une convention, pas une garantie."""
    liste, _ = scene_mod.passages(tome, entree)
    llm = _LLM("Ses cheveux blonds volaient tandis qu'elle courait sous la pluie.")
    clause, motifs = scene_mod.reformuler(llm, "yume-27b", "…", "Tory Noelle", liste, gabarit)
    assert clause == ""
    assert "passage_impur" in motifs or "clause_impure" in motifs


def test_RAS_est_une_reponse_et_le_vide_n_en_est_pas_une(tome, entree, gabarit):
    """« Une réponse VIDE est indistinguable d'un appel raté, et on ne veut pas confondre les
    deux au rapport. » Même convention que `core/bible_llm.py` et `manga/relecture.py`."""
    liste, _ = scene_mod.passages(tome, entree)
    for reponse in ("RAS", "  RAS  ", ""):
        clause, motifs = scene_mod.reformuler(_LLM(reponse), "yume-27b", "…", "Tory Noelle",
                                              liste, gabarit)
        assert clause == "" and motifs == ["modele_muet"]


def test_un_appel_rate_est_nomme_a_part(tome, entree, gabarit):
    """Confondre « le modèle n'a rien vu » et « le serveur n'a pas répondu » ferait
    disparaître une panne dans un compteur d'abstentions."""
    class _Casse:
        def chat(self, *_a, **_k):
            raise TimeoutError("le serveur ne répond pas")

    liste, _ = scene_mod.passages(tome, entree)
    clause, motifs = scene_mod.reformuler(_Casse(), "yume-27b", "…", "Tory Noelle", liste,
                                          gabarit)
    assert clause == ""
    assert motifs and motifs[0].startswith("appel_echoue:")


def test_une_clause_trop_longue_est_bornee(tome, entree, gabarit):
    """Le prompt demande vingt-cinq mots. Au-delà, le modèle a écrit un paragraphe, et un
    paragraphe dans un prompt d'image noie les attributs qui, eux, viennent de l'œuvre."""
    liste, _ = scene_mod.passages(tome, entree)
    llm = _LLM("Elle avance lentement " * 60)
    clause, _ = scene_mod.reformuler(llm, "yume-27b", "…", "Tory Noelle", liste, gabarit)
    assert 0 < len(clause) <= scene_mod.CLAUSE_MAX


def test_sans_passage_aucun_appel_n_est_fait(gabarit):
    """Un appel de 12 s pour une liste vide serait 12 s perdues à chaque personnage que le
    tome ne nomme pas — la majorité, sur le corpus réel."""
    llm = _LLM("peu importe")
    clause, motifs = scene_mod.reformuler(llm, "yume-27b", "…", "Tory Noelle", [], gabarit)
    assert clause == "" and motifs == ["aucun_passage"] and llm.appels == 0


def test_le_prompt_de_scene_est_HORS_des_prompts_requis():
    """Même règle que `illustration_style` : les huit prompts de `PROMPTS_REQUIS` sont ceux
    dont l'absence invaliderait le pack `langues/en`."""
    from core import langues as langues_mod

    assert scene_mod.PROMPT not in langues_mod.PROMPTS_REQUIS
