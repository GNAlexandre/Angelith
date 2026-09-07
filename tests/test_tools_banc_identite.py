# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`tools/banc_identite.py` — le chemin qui engage le GPU, tenu **sans** GPU.

## Pourquoi ce fichier existe, et ce qu'il aurait attrapé

Le banc d'identité avait, jusqu'au 2026-09-03, une couverture asymétrique : `--etalonnage` et
`--juge-variantes` se testent (ils ne chargent qu'un encodeur), `--balayage` non — il demande
un transformeur de 12,8 Go et une carte. Résultat : la 2.18.0 (`ae7daa1`) a renommé
`requete.depuis_bible` en `depuis_oeuvre` **sans que cet appelant suive**, et
`_prompt_du_personnage` a levé un `AttributeError` sur chaque `--balayage` pendant six
versions, sans qu'aucun test puisse le voir.

⚠ **La leçon est celle du lot 28, transposée** : ce qui ne peut pas se tester sur la machine
de développement doit être découpé de façon à ce que la PARTIE qui ne demande pas la carte
puisse l'être. Le prompt d'un personnage est du texte ; le calculer n'a jamais eu besoin d'un
GPU, et c'est ce que ce fichier vérifie.
"""
import pytest

from illustration import attente as attente_mod
from tools import banc_identite as banc

#: La même bible minimale citée que les autres tests du lot 29.
BIBLE = """
version: 1
style:
  ancrages: []
  signature: {palette: [], saturation_moyenne: null, contraste: null, densite_trait: null,
              part_aplats: null, couleur: null, echantillon: 0}
  mots: ''
personnages:
- nom: Tory
  genre_confirme: féminin
  source_genre: humain
  apparence: {cheveux: noirs, yeux: '', age_apparent: '', tenue: '', signes: []}
  citations:
  - {attribut: cheveux, texte: ses cheveux noirs, source: chapters/ch01.md}
  references: []
  images_generees: []
  valide_par_humain: true
"""


@pytest.fixture
def config(tmp_path):
    (tmp_path / "sources" / "roman S").mkdir(parents=True)
    (tmp_path / "sources" / "roman S" / "bible.yaml").write_text(BIBLE, encoding="utf-8")
    (tmp_path / "build" / "roman S").mkdir(parents=True)
    return {"chemins": {"sources": str(tmp_path / "sources"),
                        "build": str(tmp_path / "build")}}


# ─────────────────  Le défaut que ce fichier existe pour attraper  ─────────────────

def test_le_prompt_du_personnage_se_calcule_sans_GPU(config):
    """⚠ **Le test qui aurait échoué avant ce lot** : `AttributeError: module
    'illustration.requete' has no attribute 'depuis_bible'`."""
    prompt = banc._prompt_du_personnage(config, "roman S", banc.Personnage(nom="Tory"))
    assert "cheveux noirs" in prompt
    assert "fond neutre" in prompt


def test_le_prompt_suit_la_variante_de_decor_demandee(config):
    """L29.4 : sans ça, l'axe `decor` produirait trois fois la même phrase sous trois
    étiquettes différentes."""
    personnage = banc.Personnage(nom="Tory")
    assert "fond tramé" in banc._prompt_du_personnage(config, "roman S", personnage, "trame")
    assert "fond neutre" not in banc._prompt_du_personnage(config, "roman S", personnage,
                                                          "trame")


def test_un_personnage_absent_de_la_bible_ne_fait_pas_tomber_le_banc(config):
    """Le refus porte sur CE personnage, pas sur le run — même doctrine que
    `requete.depuis_oeuvre`, qui saute un personnage indescriptible plutôt que d'échouer."""
    prompt = banc._prompt_du_personnage(config, "roman S", banc.Personnage(nom="Inconnu"))
    assert prompt                      # une phrase de repli, pas une exception


# ──────────────────────  L29.4 — l'axe décor, validé AVANT le GPU  ──────────────────────

class _Args:
    def __init__(self, decors=""):
        self.decors = decors


def test_un_decor_inconnu_est_refuse_AVANT_tout_chargement():
    """⚠ Découvrir « décor inconnu » après le déchargement du LLM et le chargement de 12,8 Go
    coûterait exactement ce que le lot 28 a passé son temps à supprimer."""
    from illustration.gabarits import GabaritIntrouvable

    with pytest.raises(GabaritIntrouvable):
        banc._decors_demandes(_Args("neutre,tramé"))


def test_l_axe_decor_est_FERME_par_defaut():
    assert banc._decors_demandes(_Args("")) == ()
    assert banc._decors_demandes(_Args("neutre, trame")) == ("neutre", "trame")


# ─────────────────────────  L29.5 — le devis, avant de lancer  ─────────────────────────

def test_le_devis_du_plan_retombe_sur_les_cinq_heures_annoncees():
    """Le `PLAN-29` L29.5 écrit « environ 5 h 12 de GPU » pour 8 × 10 en édition. Le calcul
    du dépôt doit retomber dessus, sans quoi l'un des deux se trompe et il faut dire lequel."""
    devis = attente_mod.devis(8, 10, edition=True)
    assert devis["images"] == 80
    assert 5 * 3600 <= devis["secondes"] <= 5.3 * 3600
    assert devis["duree"].startswith("5 h 1")


def test_le_devis_dit_son_DENOMINATEUR_et_il_vaut_un():
    """⚠ Le coût de l'édition est relevé sur **un** essai. Un devis qui le présenterait comme
    la médiane de quatre images serait un chiffre sans son dénominateur."""
    devis = attente_mod.devis(8, 10, edition=True)
    assert devis["echantillon"] == 1
    assert "n = 1" in devis["phrase"]
    assert "ordre de grandeur" in devis["phrase"].lower()


def test_le_texte_vers_image_coute_moins_que_l_edition():
    """Facteur 2,25 mesuré le 2026-08-29 : la référence est encodée par la tour de vision ET
    par le VAE, et ses jetons s'ajoutent à l'attention à chaque pas."""
    assert (attente_mod.devis(8, 10, edition=False)["secondes"]
            < attente_mod.devis(8, 10, edition=True)["secondes"])


def test_un_devis_de_zero_image_ne_compte_pas_la_bascule_VRAM():
    assert attente_mod.devis(0, 10)["secondes"] == 0.0


def test_la_section_devis_publie_le_plan_ET_ce_que_la_commande_ferait():
    """C'est l'écart entre les deux qui a fait accepter, deux lots durant, des chiffres
    mesurés sur un personnage et trois images."""
    lignes = "\n".join(banc.section_devis(8, 10, reels=1))
    assert "ce que le plan demande" in lignes
    assert "ce que cette commande produirait" in lignes
    assert "1 personnage(s)" in lignes
    assert "relecture humaine" in lignes


# ────────  Le renommage silencieux : trois appelants oubliés, tous derrière un GPU  ────────

def test_aucun_outil_n_appelle_dossier_avec_un_TOME():
    """⚠ **Le troisième défaut de la même famille, et le test qui l'empêche de revenir.**

    La 2.19.0 (`5531029`) a rangé les illustrations par ŒUVRE et non plus par tome :
    `orchestrateur.dossier` est passé de trois arguments à deux. **Trois appelants n'ont pas
    suivi** — `tools/banc_identite.py` une fois, `tools/banc_prompt.py` deux fois — et tous
    levaient un `TypeError` au premier appel. Les trois sont sur des chemins qui chargent
    12,8 Go de poids, donc aucun test ne pouvait les atteindre.

    ⚠ Testé par **inspection de la signature**, et non par un `grep` : un `grep` sur
    `dossier(config, projet, tome)` raterait un appelant qui nomme ses variables autrement,
    alors que la signature réelle ne ment pas."""
    import ast
    import inspect
    import pathlib

    from illustration import orchestrateur

    attendus = len(inspect.signature(orchestrateur.dossier).parameters)
    assert attendus == 2, "la signature a changé : mets ce test à jour AVANT les appelants"

    for chemin in sorted(pathlib.Path("tools").glob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            nom = getattr(noeud.func, "id", "") if isinstance(noeud, ast.Call) else ""
            if nom == "dossier":
                assert len(noeud.args) <= attendus, (
                    f"{chemin}:{noeud.lineno} appelle dossier() avec {len(noeud.args)} "
                    f"arguments positionnels ; la fonction en prend {attendus} depuis la "
                    f"2.19.0 (les illustrations sont rangées par ŒUVRE, pas par tome)")
