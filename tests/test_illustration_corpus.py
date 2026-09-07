# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`PLAN-29` L29.1 — le corpus d'identité : le compte, le rôle, et le rectangle proposé.

Le lot 25 a étalonné son juge sur un corpus dont **un seul** personnage portait plus d'une
référence, et dont les trois premières références validées étaient trois couvertures, dont
deux le même dessin. Personne ne l'a su avant la mesure. Ces tests tiennent les trois briques
qui font que ça ne se reproduit pas en silence :

1. **le compte** (`core/bible.py:couverture_identite`) — le tableau 0/1/2/≥3, avec et sans les
   couvertures, et l'écart entre les deux est le sujet du lot ;
2. **le rôle** (`tools/bible.py:_references_a_relire`) — les couvertures passent en dernier à
   la REVUE, et pas seulement au moment de générer ;
3. **le rectangle** (`core/illustrations.py:cadre_propose`) — proposé, jamais retenu tel quel,
   et son motif dit l'hypothèse sur laquelle il repose.

⚠ **Aucun de ces tests n'a besoin d'une bible réelle, d'un GPU ou d'un encodeur.** Les images
sont fabriquées en numpy, la bible est un dictionnaire.
"""
import pytest

from core import bible as bible_mod
from core import illustrations as illus_mod

pytest.importorskip("numpy")
pytest.importorskip("PIL")


# ──────────────────────────────  Fabriquer des images  ──────────────────────────────

def _page(chemin, *, boite=None, cote=200):
    """Une page blanche avec un rectangle noir dessiné dedans, ou rien.

    `boite` est `(x, y, largeur, hauteur)` en fractions. C'est le seul « dessin » dont ces
    tests aient besoin : la boîte d'encre mesure où est le gradient, et un rectangle plein en
    a un sur son contour."""
    import numpy as np
    from PIL import Image

    arr = np.full((cote, cote, 3), 255, dtype=np.uint8)
    if boite:
        x, y, largeur, hauteur = boite
        x0, y0 = int(x * cote), int(y * cote)
        x1, y1 = int((x + largeur) * cote), int((y + hauteur) * cote)
        arr[y0:y1, x0:x1] = 0
    Image.fromarray(arr).save(chemin)
    return chemin


def _reference(fichier, *, role="identite", confiance="humaine", **extra):
    return {"fichier": fichier, "role": role, "confiance": confiance, **extra}


def _bible(personnages):
    return {"version": 1, "personnages": [
        {"nom": nom, "references": refs} for nom, refs in personnages]}


# ─────────────────────────  1. Le compte 0 / 1 / 2 / ≥3  ─────────────────────────

def test_le_compte_range_chaque_personnage_dans_sa_tranche():
    doc = _bible([
        ("sans", []),
        ("une", [_reference("media/a.png")]),
        ("deux", [_reference("media/a.png"), _reference("media/b.png")]),
        ("trois", [_reference(f"media/{n}.png") for n in "abc"]),
        ("quatre", [_reference(f"media/{n}.png") for n in "abcd"]),
    ])
    mesure = bible_mod.couverture_identite(doc)
    assert mesure["tranches"] == {"0": 1, "1": 1, "2": 1, "≥3": 2}
    assert mesure["par_personnage"]["quatre"] == 4


def test_seule_une_reference_VALIDEE_compte():
    """« Seule `confiance: humaine` compte dans la couverture de référence du banc. »

    Compter les propositions ferait passer un corpus non relu pour un corpus prêt — et c'est
    exactement l'erreur que le lot 25 a payée."""
    doc = _bible([("proposee", [_reference("media/a.png", confiance="proposee"),
                                _reference("media/b.png", confiance="llm")])])
    assert bible_mod.couverture_identite(doc)["tranches"]["0"] == 1


def test_une_reference_de_role_style_ne_compte_pas_pour_l_identite():
    doc = _bible([("mixte", [_reference("media/a.png", role="style"),
                             _reference("media/b.png")])])
    assert bible_mod.couverture_identite(doc)["par_personnage"]["mixte"] == 1


def test_les_couvertures_se_retirent_du_compte_et_l_ecart_est_le_sujet_du_lot():
    """⚠ **Le test qui aurait dû exister au lot 25.** Trois couvertures validées donnaient
    « ≥3 », donc « corpus prêt » — alors qu'aucune des trois n'est une référence d'identité
    utilisable, et que deux étaient le même dessin."""
    doc = _bible([("tory", [_reference(f"media/couv{n}.png") for n in (1, 2, 3)])])
    classes = {f"couv{n}.png": illus_mod.COUVERTURE for n in (1, 2, 3)}

    avec = bible_mod.couverture_identite(doc)
    sans = bible_mod.couverture_identite(doc, sans_couverture=True, classes=classes)

    assert avec["tranches"]["≥3"] == 1
    assert sans["tranches"]["0"] == 1
    assert not sans["pret"]


def test_le_manque_est_une_phrase_qui_dit_quoi_faire():
    """« il manque 5 personnages » se corrige ; « pret: false » ne dit pas quoi faire."""
    mesure = bible_mod.couverture_identite(_bible([("une", [_reference("media/a.png")])]))
    assert not mesure["pret"]
    assert "personnage(s)" in mesure["manque"]
    assert str(bible_mod.CIBLE_PERSONNAGES - 1) in mesure["manque"]


def test_la_cible_du_plan_est_atteignable_et_le_dit():
    personnages = [(f"p{i}", [_reference(f"media/{i}{n}.png") for n in "abc"])
                   for i in range(bible_mod.CIBLE_PERSONNAGES)]
    mesure = bible_mod.couverture_identite(_bible(personnages))
    assert mesure["pret"]
    assert mesure["avec_trois"] == bible_mod.CIBLE_PERSONNAGES


# ─────────────────────  2. Les deux noms du champ de recadrage  ─────────────────────

def test_le_champ_de_recadrage_se_lit_sous_ses_DEUX_noms():
    """⚠ **Le défaut relevé par le lot 29** : `core/bible_llm.py` écrivait `recadrage: []`
    pendant que `illustration/identite.py` lisait `cadre`. Le champ écrit n'était pas celui
    qui était lu, et il n'a donc jamais pu être rempli."""
    assert bible_mod.cadre_de({"cadre": [0.1, 0.0, 0.5, 0.5]}) == [0.1, 0.0, 0.5, 0.5]
    assert bible_mod.cadre_de({bible_mod.CADRE_HERITE: [0.2, 0.0, 0.5, 0.5]}) == \
        [0.2, 0.0, 0.5, 0.5]
    assert bible_mod.cadre_de({}) == ()
    assert bible_mod.cadre_de({}, defaut=None) is None


def test_la_passe_de_propositions_ecrit_le_nom_que_le_moteur_LIT():
    """Le test qui aurait échoué avant ce lot : `en_bible` écrivait un champ mort."""
    from core.bible_llm import en_bible

    doc = en_bible([], {"Tory": [("Vol.1/media/a.jpeg", "Vol.1", "pleine_page")]})
    reference = doc["personnages"][0]["references"][0]
    assert "cadre" in reference
    assert bible_mod.CADRE_HERITE not in reference


@pytest.mark.parametrize("brut, attendu", [
    ([0.0, 0.0, 1.0, 1.0], True),
    ([0.1, 0.2, 0.5, 0.5], True),
    ([0.1, 0.2, 0.0, 0.5], False),        # largeur nulle
    ([0.6, 0.0, 0.5, 0.5], False),        # déborde à droite
    ([0.1, 0.2, 0.5], False),             # trois valeurs
    ("0.1 0.2 0.5 0.5", False),           # une chaîne
])
def test_un_cadre_a_moitie_valide_n_est_pas_valide(brut, attendu):
    assert bible_mod.cadre_valide(brut) is attendu


def test_un_cadre_invalide_est_SIGNALE_et_pas_corrige():
    """⚠ Jusqu'au lot 29, la référence retombait sur la page entière **en silence** : le
    recadrage qu'un humain avait validé était perdu sans que rien ne le dise."""
    doc = _bible([("tory", [_reference("media/a.png", cadre=[0.9, 0.0, 0.5, 0.5])])])
    problemes = bible_mod.verifier_coherence(doc, ["tory"], None)
    assert any("cadre" in p and "EN ENTIER" in p for p in problemes)


def test_le_consommateur_lit_le_cadre_sous_l_ancien_nom(tmp_path):
    """`illustration/identite.py` doit voir un `recadrage` écrit par une bible d'avant."""
    from illustration import identite as ident_mod

    tome = tmp_path / "Vol.1" / "media"
    tome.mkdir(parents=True)
    _page(tome / "a.png", boite=(0.2, 0.2, 0.5, 0.5))
    doc = _bible([("tory", [_reference("media/a.png",
                                       **{bible_mod.CADRE_HERITE: [0.1, 0.0, 0.4, 0.4]})])])
    references = ident_mod.references_de(doc, "tory", tmp_path)
    assert references[0].cadre == (0.1, 0.0, 0.4, 0.4)


# ────────────────────────  3. Le rectangle proposé, et son motif  ────────────────────────

def test_la_boite_d_encre_trouve_le_dessin_et_pas_la_page(tmp_path):
    chemin = _page(tmp_path / "p.png", boite=(0.25, 0.25, 0.5, 0.5))
    x, y, largeur, hauteur = illus_mod.boite_d_encre(chemin)
    assert 0.2 <= x <= 0.3 and 0.2 <= y <= 0.3
    assert 0.4 <= largeur <= 0.6 and 0.4 <= hauteur <= 0.6


def test_une_page_sans_encre_ne_rend_aucune_boite(tmp_path):
    """Une image d'une seule luminance n'a rien à encadrer, et rendre `[0,0,1,1]` ferait
    passer une absence de mesure pour « toute la page est du dessin »."""
    assert illus_mod.boite_d_encre(_page(tmp_path / "blanche.png")) is None
    assert illus_mod.cadre_propose(_page(tmp_path / "b2.png")) is None


def test_une_image_illisible_rend_None(tmp_path):
    faux = tmp_path / "faux.png"
    faux.write_bytes(b"ceci n'est pas un PNG")
    assert illus_mod.boite_d_encre(faux) is None


def test_les_trois_cadrages_retiennent_le_HAUT_de_la_boite(tmp_path):
    chemin = _page(tmp_path / "p.png", boite=(0.2, 0.1, 0.6, 0.8))
    hauteurs = {}
    for cadrage in illus_mod.CADRAGES_PROPOSES:
        propose = illus_mod.cadre_propose(chemin, cadrage)
        x, y, largeur, hauteur = propose["cadre"]
        hauteurs[cadrage] = hauteur
        assert y == pytest.approx(illus_mod.boite_d_encre(chemin)[1], abs=0.01)
    assert hauteurs["visage"] < hauteurs["buste"] < hauteurs["pied"]


def test_le_motif_NOMME_l_hypothese_qu_un_humain_doit_corriger(tmp_path):
    """⚠ Le cœur de L29.1 : « un rectangle proposé, un rectangle corrigé ». On ne corrige
    bien que ce dont on connaît la construction — le motif doit donc dire que « visage » veut
    dire « le tiers supérieur de l'encre » et non « le visage »."""
    propose = illus_mod.cadre_propose(_page(tmp_path / "p.png", boite=(0.2, 0.1, 0.6, 0.8)),
                                      "visage")
    assert "hypothèse" in propose["motif"]
    assert "corriger" in propose["motif"]


def test_un_cadrage_inconnu_leve_plutot_que_de_retomber_sur_le_buste(tmp_path):
    with pytest.raises(ValueError, match="cadrage"):
        illus_mod.cadre_propose(_page(tmp_path / "p.png", boite=(0.2, 0.2, 0.5, 0.5)),
                                "trois_quarts")


def test_le_cadre_propose_est_toujours_ecrivable_dans_la_bible(tmp_path):
    """Ce que `cadre_propose` rend doit passer `cadre_valide` — sans quoi la proposition
    serait refusée par la validation du fichier qu'elle sert à remplir."""
    chemin = _page(tmp_path / "p.png", boite=(0.1, 0.05, 0.85, 0.9))
    for cadrage in illus_mod.CADRAGES_PROPOSES:
        assert bible_mod.cadre_valide(illus_mod.cadre_propose(chemin, cadrage)["cadre"])


def test_le_module_ne_recadre_rien_et_n_ecrit_rien(tmp_path):
    """⚠ `core/illustrations.py` « lit des pixels et rend des nombres ». `cadre_propose` ne
    doit pas devenir la première exception : quatre fractions sortent, aucun fichier."""
    chemin = _page(tmp_path / "p.png", boite=(0.2, 0.2, 0.5, 0.5))
    avant = sorted(p.name for p in tmp_path.iterdir())
    illus_mod.cadre_propose(chemin, "buste")
    assert sorted(p.name for p in tmp_path.iterdir()) == avant


# ───────────────────────  4. La revue : les couvertures en dernier  ───────────────────────

def test_la_revue_repousse_les_couvertures_sans_les_cacher():
    """⚠ La règle du lot 26 ne valait qu'au moment de GÉNÉRER. Elle arrive alors trop tard :
    c'est à la revue que le corpus se constitue."""
    from tools import bible as outil

    references = [
        {"fichier": "media/couv.png", "classe": illus_mod.COUVERTURE, "role": "identite"},
        {"fichier": "media/p12.png", "classe": illus_mod.PLEINE_PAGE, "role": "identite"},
    ]
    ordre = outil._references_a_relire({"references": references}, "identite")
    assert [r["fichier"] for r in ordre] == ["media/p12.png", "media/couv.png"]


def test_le_role_filtre_mais_le_defaut_ne_filtre_rien():
    from tools import bible as outil

    references = [{"fichier": "media/a.png", "role": "identite"},
                  {"fichier": "media/b.png", "role": "style"}]
    entree = {"references": references}
    assert len(outil._references_a_relire(entree, "")) == 2
    assert len(outil._references_a_relire(entree, "identite")) == 1
    assert len(outil._references_a_relire(entree, "style")) == 1


def test_le_tableau_du_corpus_publie_les_DEUX_comptes():
    """Publier le seul compte « toutes références » aurait dit « corpus prêt » au lot 25."""
    from tools import bible as outil

    doc = _bible([("tory", [_reference("media/couv.png")])])
    lignes = outil._lignes_corpus(doc, {"couv.png": illus_mod.COUVERTURE})
    texte = "\n".join(lignes)
    assert "toutes" in texte and "hors couverture" in texte
    assert "PLAN-29" in texte


def test_le_recadrage_assiste_passe_sur_une_touche_ENTREE(tmp_path, monkeypatch):
    """⚠ `_demander` rend « ? » sur une entrée vide, **y compris quand « ? » n'est pas dans
    les choix**. Sans filtre, une touche Entrée envoyait « ? » à `cadre_propose`, qui lève —
    et faisait tomber la revue en cours, donc perdre ce qui venait d'être validé."""
    from tools import bible as outil

    tome = tmp_path / "Vol.1" / "media"
    tome.mkdir(parents=True)
    _page(tome / "a.png", boite=(0.2, 0.2, 0.5, 0.5))
    monkeypatch.setattr(outil, "_demander", lambda *a, **k: "?")
    config = {"chemins": {"build": str(tmp_path.parent), "sources": str(tmp_path)}}

    reference = {"fichier": "media/a.png", "role": "identite"}
    rendu = outil._recadrer(config, tmp_path.name, reference)
    assert rendu == reference           # passé, pas planté, et rien n'est écrit


def test_le_recadrage_assiste_garde_le_cadre_propose(tmp_path, monkeypatch):
    from tools import bible as outil

    tome = tmp_path / "Vol.1" / "media"
    tome.mkdir(parents=True)
    _page(tome / "a.png", boite=(0.2, 0.1, 0.6, 0.8))
    monkeypatch.setattr(outil, "_demander", lambda *a, **k: "buste")
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")     # Entrée = je le garde
    config = {"chemins": {"build": str(tmp_path.parent), "sources": str(tmp_path)}}

    rendu = outil._recadrer(config, tmp_path.name, {"fichier": "media/a.png",
                                                    "role": "identite"})
    assert bible_mod.cadre_valide(rendu["cadre"])


def test_un_cadre_saisi_a_la_main_l_emporte_sur_la_proposition(tmp_path, monkeypatch):
    """« Un rectangle proposé, un rectangle CORRIGÉ » — la seconde moitié de L29.1."""
    from tools import bible as outil

    tome = tmp_path / "Vol.1" / "media"
    tome.mkdir(parents=True)
    _page(tome / "a.png", boite=(0.2, 0.1, 0.6, 0.8))
    monkeypatch.setattr(outil, "_demander", lambda *a, **k: "buste")
    monkeypatch.setattr("builtins.input", lambda *a, **k: "0.1 0.2 0.3 0.4")
    config = {"chemins": {"build": str(tmp_path.parent), "sources": str(tmp_path)}}

    rendu = outil._recadrer(config, tmp_path.name, {"fichier": "media/a.png",
                                                    "role": "identite"})
    assert rendu["cadre"] == [0.1, 0.2, 0.3, 0.4]


def test_une_saisie_invalide_garde_la_PROPOSITION_et_le_dit(tmp_path, monkeypatch, capsys):
    """Le dépôt traite déjà « un cadre à moitié valide » comme absent plutôt que corrigé.
    Ici on garde ce qui a été mesuré, et on dit pourquoi — jamais une valeur rafistolée."""
    from tools import bible as outil

    tome = tmp_path / "Vol.1" / "media"
    tome.mkdir(parents=True)
    _page(tome / "a.png", boite=(0.2, 0.1, 0.6, 0.8))
    monkeypatch.setattr(outil, "_demander", lambda *a, **k: "buste")
    monkeypatch.setattr("builtins.input", lambda *a, **k: "0.9 0 0.5 0.5")   # déborde
    config = {"chemins": {"build": str(tmp_path.parent), "sources": str(tmp_path)}}

    rendu = outil._recadrer(config, tmp_path.name, {"fichier": "media/a.png",
                                                    "role": "identite"})
    assert "quatre fractions attendues" in capsys.readouterr().out
    assert bible_mod.cadre_valide(rendu["cadre"])
