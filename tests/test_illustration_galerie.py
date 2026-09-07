# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""L27.3 et L27.5 — **garder, jeter, ne rien perdre**, et ce que ça pèse.

Le test le plus important de ce fichier est
`test_une_image_generee_ne_peut_PAS_devenir_une_reference` : c'est le critère 5 du `PLAN-27`,
et le plan écrit que le rebouclage doit être rendu **impossible, pas seulement improbable** —
« reboucler une sortie dans l'entrée fait dériver le personnage à chaque tour, et la dérive
est invisible image par image ».
"""
import json

import pytest

from illustration import galerie
from illustration import marquage


def _png(chemin, couleur=(10, 20, 30), marque=True):
    """Une image de la brique, avec son sidecar — la seule forme que la galerie reconnaît."""
    from PIL import Image, PngImagePlugin

    chemin.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    if marque:
        for cle, valeur in (("Software", "Angelith"), ("AIGenerated", "true"),
                            ("Generator", "factice"), ("Seed", "7"),
                            ("SourceWork", "oeuvre-abc"),
                            ("Disclaimer", marquage.PHRASE_NON_OEUVRE)):
            info.add_text(cle, valeur)
    Image.new("RGB", (8, 8), couleur).save(chemin, format="PNG", pnginfo=info)
    if marque:
        marquage.manifeste_de(chemin).write_text(json.dumps({
            "genere_par_ia": True, "date": "2026-09-02", "secondes": 103.7,
            "payload": {"graine": 7},
            "prompt_source": {"personnage": "Aya", "cadrage": "buste"},
            # ⚠ La forme EXACTE de `juge.Grandeurs.resume()`, pas une forme inventée pour le
            # test : un sidecar factice qui ne ressemble pas au vrai ne prouve rien.
            "identite": {"grandeurs": {"ressemblance": 0.41, "nouveaute": 0.62,
                                       "style_descripteurs": 0.1224,
                                       "descripteur_decroche": ["saturation", 2.4],
                                       "meme_regime_couleur": True}},
        }, ensure_ascii=False), encoding="utf-8")
    return chemin


# ─────────────────────────────────  L'inventaire  ─────────────────────────────────

def test_l_inventaire_compte_par_etat_et_porte_les_octets(tmp_path):
    candidates = tmp_path / "build" / "P" / "illustrations"
    retenues = tmp_path / "sources" / "P" / "illustrations"
    _png(candidates / "a.png")
    _png(candidates / "b.png")
    _png(candidates / galerie.NOM_REJETEES / "c.png")
    _png(retenues / "d.png")

    inventaire = galerie.inventorier(candidates, retenues)
    assert inventaire.compte(galerie.CANDIDATE) == 2
    assert inventaire.compte(galerie.REJETEE) == 1
    assert inventaire.compte(galerie.RETENUE) == 1
    assert inventaire.octets() > 0
    assert "candidate" in "\n".join(inventaire.resume())


def test_une_image_sans_manifeste_est_SIGNALEE_pas_supprimee(tmp_path):
    """Effacer un fichier qu'on ne comprend pas est le contraire de ce que ce module fait."""
    candidates = tmp_path / "illustrations"
    _png(candidates / "orpheline.png", marque=False)
    inventaire = galerie.inventorier(candidates)
    assert len(inventaire.sans_manifeste()) == 1
    assert "sans manifeste" in "\n".join(inventaire.resume())
    assert (candidates / "orpheline.png").is_file()


def test_l_inventaire_lit_les_grandeurs_du_sidecar(tmp_path):
    _png(tmp_path / "a.png")
    piece = galerie.inventorier(tmp_path).pieces[0]
    assert piece.personnage == "Aya" and piece.graine == 7
    assert piece.grandeurs["ressemblance"] == 0.41


# ─────────────────────────────  Garder, jeter, purger  ─────────────────────────────

def test_garder_deplace_l_image_ET_son_sidecar(tmp_path):
    source = _png(tmp_path / "build" / "x.png")
    image, manifeste = galerie.garder(source, tmp_path / "sources")
    assert image.parent == tmp_path / "sources"
    assert manifeste.is_file()
    assert not source.exists() and not marquage.manifeste_de(source).exists()


def test_garder_REFUSE_une_image_sans_manifeste(tmp_path):
    """Une image gardée sans son sidecar ne peut plus dire qui a validé son prompt, avec quel
    modèle ni depuis quelles références. Elle perdrait ce qui la rend défendable."""
    source = _png(tmp_path / "build" / "nu.png", marque=False)
    with pytest.raises(galerie.GesteImpossible, match="manifeste de provenance"):
        galerie.garder(source, tmp_path / "sources")
    assert source.is_file(), "un refus ne doit rien déplacer"


def test_rien_n_est_JAMAIS_reecrit(tmp_path):
    """Le dépôt tient déjà ce contrat pour l'édition manuelle : « le pipeline ne la réécrira
    jamais ». Une image de 103,7 s de GPU écrasée par une homonyme est la même perte."""
    destination = tmp_path / "sources"
    premiere = galerie.garder(_png(tmp_path / "a" / "x.png", (1, 2, 3)), destination)[0]
    seconde = galerie.garder(_png(tmp_path / "b" / "x.png", (9, 9, 9)), destination)[0]
    assert premiere.name == "x.png" and seconde.name == "x-2.png"
    assert premiere.read_bytes() != seconde.read_bytes()


def test_nom_libre_tient_compte_du_manifeste_autant_que_de_l_image(tmp_path):
    """Un `x-2.png` libre dont le sidecar existe encore désignerait une paire incohérente."""
    marquage.manifeste_de(tmp_path / "x.png").parent.mkdir(parents=True, exist_ok=True)
    marquage.manifeste_de(tmp_path / "x.png").write_text("{}", encoding="utf-8")
    assert galerie.nom_libre(tmp_path / "x.png").name == "x-2.png"


def test_jeter_deplace_et_ne_supprime_RIEN(tmp_path):
    """Un rejet est une donnée : le `PLAN-25` L25.4 en a besoin pour mesurer."""
    source = _png(tmp_path / "illustrations" / "raté.png")
    cible, manifeste = galerie.jeter(source)
    assert cible.parent.name == galerie.NOM_REJETEES
    assert cible.is_file() and manifeste.is_file()
    assert not source.exists()


def test_purger_dit_ce_qu_elle_va_detruire_AVANT_de_le_detruire(tmp_path):
    rejetees = tmp_path / galerie.NOM_REJETEES
    _png(rejetees / "a.png")
    _png(rejetees / "b.png")
    combien, octets = galerie.poids_a_purger(rejetees)
    assert combien == 2 and octets > 0
    nombre, libres = galerie.purger(rejetees)
    assert nombre == 2 and libres > 0
    assert galerie.poids_a_purger(rejetees) == (0, 0)


def test_purger_emporte_les_manifestes_avec_les_images(tmp_path):
    rejetees = tmp_path / galerie.NOM_REJETEES
    image = _png(rejetees / "a.png")
    galerie.purger(rejetees)
    assert not image.exists() and not marquage.manifeste_de(image).exists()


# ──────────  Critère 5 : une image générée ne peut PAS devenir une référence  ──────────

def test_inscrire_ecrit_sous_images_generees_et_pas_sous_references(tmp_path):
    from core import bible as bible_mod

    bible_doc = bible_mod.fill_defaults({"personnages": [{"nom": "Aya"}]})
    modifiee, combien = galerie.inscrire(bible_doc, "Aya", tmp_path / "ia-aya.png",
                                         cadrage="buste", par="Alexandre")
    entree = bible_mod.entree(modifiee, "Aya")
    assert combien == 1
    assert entree["references"] == []
    assert entree[galerie.CLE_GENEREES][0]["fichier"] == "ia-aya.png"
    assert "jamais candidate" in entree[galerie.CLE_GENEREES][0]["note"]


def test_inscrire_est_idempotente():
    from core import bible as bible_mod

    doc = bible_mod.fill_defaults({"personnages": [{"nom": "Aya"}]})
    doc, _ = galerie.inscrire(doc, "Aya", "ia-aya.png")
    doc, combien = galerie.inscrire(doc, "Aya", "ia-aya.png")
    assert combien == 0
    assert len(galerie.generees_de(doc, "Aya")) == 1


def test_inscrire_refuse_un_personnage_absent_de_la_bible():
    from core import bible as bible_mod

    doc = bible_mod.vide()
    with pytest.raises(galerie.GesteImpossible, match="n'est pas dans la bible"):
        galerie.inscrire(doc, "Inconnue", "x.png")


def test_inscrire_refuse_une_image_sans_personnage():
    from core import bible as bible_mod

    with pytest.raises(galerie.GesteImpossible, match="aucun personnage"):
        galerie.inscrire(bible_mod.vide(), "", "x.png")


def test_une_image_generee_ne_peut_PAS_devenir_une_reference(tmp_path):
    """⚠ **Le critère 5, et le point le plus important du lot.** L'aller-retour complet :
    générer, garder, inscrire dans la bible, puis redemander les candidates d'identité. La
    liste doit être **inchangée**.

    Trois mécanismes indépendants l'empêchent, et le test les traverse tous les trois :
    la clé distincte (`images_generees`), le refus par dossier (`illustrations/`), et le
    refus par marquage AI Act dans le PNG."""
    from core import bible as bible_mod
    from illustration import selection

    racine = tmp_path / "build" / "P"
    (racine / "Vol.1" / "media").mkdir(parents=True)
    vraie = _png(racine / "Vol.1" / "media" / "image3.png", marque=False)
    assert vraie.is_file()
    bible_doc = bible_mod.fill_defaults({"personnages": [{
        "nom": "Aya",
        "apparence": {"yeux": "verts"},
        "citations": [{"attribut": "yeux", "source": "ch01.md", "texte": "ses yeux verts"}],
        "references": [{"fichier": "media/image3.png", "confiance": "humaine"}]}]})
    avant = [c.fichier for c in selection.candidates_identite(bible_doc, "Aya", racine)]
    assert avant == ["media/image3.png"]

    # On garde une image produite, on l'inscrit, et on relit.
    produite = _png(racine / "illustrations" / "aya.png")
    gardee, _ = galerie.garder(produite, tmp_path / "sources" / "P" / "illustrations")
    modifiee, combien = galerie.inscrire(bible_doc, "Aya", gardee)
    assert combien == 1

    apres = [c.fichier for c in selection.candidates_identite(modifiee, "Aya", racine)]
    assert apres == avant, ("une image PRODUITE est devenue candidate au conditionnement — "
                            "le personnage dérivera à chaque tour")


def test_le_refus_par_dossier_et_le_refus_par_marquage_sont_INDEPENDANTS(tmp_path):
    """Le plan demande que le rebouclage soit impossible, pas improbable : chacun des deux
    signes doit suffire seul."""
    from illustration import selection

    racine = tmp_path / "build" / "P"
    # 1. dans un dossier `illustrations/`, SANS marquage
    (racine / "Vol.1" / "illustrations").mkdir(parents=True)
    par_dossier = _png(racine / "Vol.1" / "illustrations" / "x.png", marque=False)
    # 2. hors de ce dossier, AVEC le marquage
    (racine / "Vol.1" / "media").mkdir(parents=True, exist_ok=True)
    par_marquage = _png(racine / "Vol.1" / "media" / "y.png", marque=True)

    for fichier in ("illustrations/x.png", "media/y.png"):
        bible_doc = {"personnages": [{
            "nom": "Aya", "apparence": {"yeux": "verts"},
            "citations": [{"attribut": "yeux", "source": "c", "texte": "t"}],
            "references": [{"fichier": fichier, "confiance": "humaine"}]}]}
        assert selection.candidates_identite(bible_doc, "Aya", racine) == [], fichier
    assert par_dossier.is_file() and par_marquage.is_file()


# ──────────────  Critère 4 : les trois verdicts, en phrases lisibles  ──────────────

def test_le_verdict_de_style_nomme_le_descripteur_qui_DECROCHE(tmp_path):
    """⚠ « saturation 2,4× la signature du tome » se comprend, « style 0,63 » ne se comprend
    pas. C'est le critère 4 de L27.1, et il porte sur la LISIBILITÉ."""
    _png(tmp_path / "a.png")
    piece = galerie.inventorier(tmp_path).pieces[0]
    lignes = galerie.verdicts(piece)
    assert any("ressemblance : 0.410" in ligne for ligne in lignes)
    assert any("nouveauté : 0.620" in ligne for ligne in lignes)
    assert any("saturation" in ligne and "2.40" in ligne for ligne in lignes)


def test_une_grandeur_absente_est_dite_NON_MESUREE_pas_montree_comme_un_zero(tmp_path):
    """Un cosinus de 0 est une mesure (« aucun rapport ») ; une absence de référence n'en est
    pas une. Les confondre ferait passer un personnage sans référence pour un échec."""
    _png(tmp_path / "a.png")
    marquage.manifeste_de(tmp_path / "a.png").write_text(json.dumps({
        "genere_par_ia": True, "payload": {},
        "identite": {"grandeurs": {"ressemblance": None, "nouveaute": None}}}),
        encoding="utf-8")
    lignes = galerie.verdicts(galerie.inventorier(tmp_path).pieces[0])
    assert lignes[0].endswith("non mesurée") and lignes[1].endswith("non mesurée")
    assert "non mesuré" in lignes[2]


def test_sans_juge_du_tout_le_verdict_dit_POURQUOI(tmp_path):
    """« illustration.identite.actif: false » est une information, pas un silence."""
    _png(tmp_path / "a.png")
    marquage.manifeste_de(tmp_path / "a.png").write_text(
        json.dumps({"genere_par_ia": True, "payload": {}}), encoding="utf-8")
    (ligne,) = galerie.verdicts(galerie.inventorier(tmp_path).pieces[0])
    assert "identite.actif" in ligne


def test_un_regime_de_couleur_different_est_signale(tmp_path):
    """Le défaut que le lot 25 a mesuré et que le lot 26 a corrigé : le tome est en noir et
    blanc, les générations non. Il doit se voir sur la vignette."""
    _png(tmp_path / "a.png")
    marquage.manifeste_de(tmp_path / "a.png").write_text(json.dumps({
        "genere_par_ia": True, "payload": {},
        "identite": {"grandeurs": {"ressemblance": 0.4, "nouveaute": 0.5,
                                   "style_descripteurs": 0.12,
                                   "meme_regime_couleur": False}}}), encoding="utf-8")
    lignes = galerie.verdicts(galerie.inventorier(tmp_path).pieces[0])
    assert any("régime de COULEUR" in ligne for ligne in lignes)


# ──────────────────────  Le poids sur le disque, publié  ──────────────────────

def test_le_calcul_de_poids_est_publie_avec_son_denominateur():
    """Le plan : « publiez le calcul dans le document du lot ». Il vit dans le code pour que
    `--check` et le document lisent le même."""
    lignes = "\n".join(galerie.calcul_du_poids())
    assert "119 personnages" in lignes and "8 images" in lignes
    assert "2.1 Mo" in lignes and "Go" in lignes
    assert "1,4 à 3,1 Mo" in lignes


def test_le_poids_estime_du_corpus_reel():
    """119 personnages × 8 images × 2,1 Mo ≈ 2,0 Go — le chiffre que le plan cite."""
    octets = galerie.poids_estime(119, 8)
    assert 1.9e9 < octets < 2.1e9


def test_octets_lisibles_est_en_base_1000_comme_le_reste_du_depot():
    assert galerie.octets_lisibles(2_100_000) == "2.1 Mo"
    assert galerie.octets_lisibles(0) == "0 o"
