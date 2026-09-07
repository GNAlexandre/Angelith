# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""La **voie A** du `PLAN-25` : les références, le refus, et les trois verdicts.

Deux tests portent le lot :

- `test_un_personnage_sans_reference_validee_ne_produit_aucune_image` — le critère 5 du plan,
  et il n'a pas de nuance ;
- `test_une_image_trop_proche_de_sa_reference_est_rejetee` — le critère 4, dont le plan écrit
  que « ce cas n'est pas négociable ».

Les autres gardent ce qui se contourne facilement : que l'extrait de référence ne puisse pas
servir de porte dérobée au marquage AI Act, et que `identite.actif: false` rende exactement ce
que le lot 24 rendait.
"""
import json
from pathlib import Path

import pytest
from PIL import Image

from core import bible as bible_mod
from illustration import frontiere
from illustration import identite as ident_mod
from illustration import juge as juge_mod
from illustration import orchestrateur
from illustration import requete as requete_mod
from illustration.moteur import MoteurFactice
from tests.test_illustration_juge import EncodeurFactice


@pytest.fixture
def projet(tmp_path):
    """Un projet à deux tomes : la bible est PAR PROJET, et sur le corpus réel 7 références
    sur 10 vivent dans un autre tome que celui qu'on illustre."""
    nom = "Projet Témoin"
    sources = tmp_path / "sources" / nom
    sources.mkdir(parents=True)
    for volume, couleurs in (("Vol.1", [(200, 200, 200)]), ("Vol.2", [(40, 40, 40), (90, 90, 90)])):
        media = tmp_path / "build" / nom / volume / "media"
        media.mkdir(parents=True)
        for index, couleur in enumerate(couleurs, start=1):
            Image.new("RGB", (64, 96), couleur).save(media / f"{volume}_illus{index}.png")

    entree = bible_mod.personnage("Tory Noelle")
    entree["apparence"]["cheveux"] = "blonds"
    entree["citations"] = [{"attribut": "cheveux", "source": "chapters/ch01.md",
                            "texte": "cheveux blonds"}]
    entree["references"] = [
        {"fichier": "media/Vol.1_illus1.png", "role": "identite", "confiance": "humaine"},
        {"fichier": "media/Vol.2_illus1.png", "role": "identite", "confiance": "humaine"},
        {"fichier": "media/Vol.2_illus2.png", "role": "identite", "confiance": "proposee"},
    ]
    entree["valide_par_humain"] = True

    sans = bible_mod.personnage("Silas")
    sans["apparence"]["cheveux"] = "noirs"
    sans["citations"] = [{"attribut": "cheveux", "source": "chapters/ch02.md",
                          "texte": "cheveux noirs"}]
    sans["references"] = [{"fichier": "media/Vol.1_illus1.png", "role": "identite",
                           "confiance": "llm"}]

    bible_mod.save({"personnages": [entree, sans],
                    "style": {"mots": "trait fin",
                              "ancrages": [{"fichier": "media/Vol.1_illus1.png",
                                            "valide_par_humain": True}],
                              "signature": {"saturation_moyenne": 0.02, "contraste": 0.24,
                                            "densite_trait": 0.26, "part_aplats": 0.36,
                                            "couleur": False, "echantillon": 16}}},
                   bible_mod.chemin(sources))

    config = {"chemins": {"sources": str(tmp_path / "sources"),
                          "build": str(tmp_path / "build")},
              "illustration": {"actif": True, "moteur": "factice",
                               "vram": {"decharger_llm": False},
                               "identite": {"actif": True}}}
    return config, nom, "Vol.1", tmp_path


# ────────────────────────  Les références, de la bible au moteur  ────────────────────────

def test_une_reference_est_resolue_sous_N_IMPORTE_QUEL_tome(projet):
    """La bible est par PROJET : une seconde règle de résolution a déjà été un défaut, corrigé
    le 2026-08-29 — sur `roman S`, 7 des 10 références vivent dans le Vol.2."""
    config, nom, _, tmp = projet
    doc = bible_mod.load(bible_mod.chemin(Path(config["chemins"]["sources"]) / nom))
    refs = ident_mod.references_de(doc, "Tory Noelle", Path(config["chemins"]["build"]) / nom)
    assert [r.fichier for r in refs] == ["media/Vol.1_illus1.png", "media/Vol.2_illus1.png",
                                         "media/Vol.2_illus2.png"]
    assert all(r.source.is_file() for r in refs)


def test_seules_les_references_HUMAINES_sont_retenues(projet):
    config, nom, _, _ = projet
    doc = bible_mod.load(bible_mod.chemin(Path(config["chemins"]["sources"]) / nom))
    refs = ident_mod.references_de(doc, "Tory Noelle", Path(config["chemins"]["build"]) / nom)
    retenues = ident_mod.retenir(refs, 3)
    assert len(retenues) == 2                      # la troisième est `proposee`
    assert all(r.confiance == "humaine" for r in retenues)


def test_le_nombre_de_references_est_plafonne_par_le_graphe(projet):
    config, nom, _, _ = projet
    doc = bible_mod.load(bible_mod.chemin(Path(config["chemins"]["sources"]) / nom))
    refs = ident_mod.references_de(doc, "Tory Noelle", Path(config["chemins"]["build"]) / nom)
    assert len(ident_mod.retenir(refs, 99)) <= ident_mod.REFERENCES_MAX


def test_un_cadre_a_moitie_valide_est_traite_comme_absent():
    """Un recadrage silencieusement rectifié désignerait une autre partie de l'image que
    celle qu'un humain a validée."""
    assert ident_mod._cadre([0.1, 0.1, 0.5, 0.5]) == (0.1, 0.1, 0.5, 0.5)
    assert ident_mod._cadre([0.1, 0.1, 0.5]) == ()
    assert ident_mod._cadre([0.9, 0.1, 0.5, 0.5]) == ()        # déborde à droite
    assert ident_mod._cadre([0.1, 0.1, 0.0, 0.5]) == ()        # largeur nulle
    assert ident_mod._cadre("0,0,1,1") == ()


def test_le_cadre_est_vide_sur_le_corpus_et_le_mecanisme_marche_quand_meme(projet, tmp_path):
    """L'axe « nature du recadrage » du plan n'a pas pu être mesuré — la bible réelle porte
    des PAGES entières sans boîte. Le mécanisme, lui, est livré et testé."""
    config, nom, _, _ = projet
    source = Path(config["chemins"]["build"]) / nom / "Vol.1" / "media" / "Vol.1_illus1.png"
    reference = ident_mod.Reference(fichier="x", source=source, confiance="humaine",
                                    cadre=(0.0, 0.0, 0.5, 0.5))
    cible = tmp_path / "sortie" / ident_mod.DOSSIER_REFERENCES / "x.png"
    with frontiere.perimetre(tmp_path / "sortie"):
        ecrit = ident_mod.preparer(reference, cible)
    with Image.open(ecrit) as image:
        assert image.size == (32, 48)              # la moitié de 64 × 96


def test_le_prompt_nomme_les_images_de_reference():
    """Une référence branchée mais jamais citée est une référence à moitié utilisée, et rien
    ne le signalerait — la carte de `Qwen-Image-Edit-2511` désigne ses images en prose."""
    assert ident_mod.prompt_avec_references("Portrait.", 0) == "Portrait."
    assert "image 1" in ident_mod.prompt_avec_references("Portrait.", 1)
    triple = ident_mod.prompt_avec_references("Portrait.", 3)
    assert "l'image 1" in triple and "l'image 3" in triple


# ────────────────────────────  Le marquage n'a pas de porte dérobée  ────────────────────────────

def test_un_extrait_ne_peut_pas_s_ecrire_hors_du_dossier_references(tmp_path):
    """La seconde porte est **mécaniquement** plus étroite que la première : une image générée
    s'écrit à la racine du dossier de la brique, donc elle ne peut pas l'emprunter."""
    with frontiere.perimetre(tmp_path):
        with pytest.raises(frontiere.ImageNonMarquee):
            with frontiere.ecriture_extrait(tmp_path / "generee.png"):
                pass


def test_l_autorisation_d_extrait_ne_vaut_que_pour_UN_chemin(tmp_path):
    """Sinon un bloc ouvert pour une référence laisserait passer toutes les images qu'il
    contient."""
    dossier = tmp_path / ident_mod.DOSSIER_REFERENCES
    dossier.mkdir()
    with frontiere.perimetre(tmp_path):
        with frontiere.ecriture_extrait(dossier / "ok.png"):
            Image.new("RGB", (4, 4)).save(dossier / "ok.png")
            with pytest.raises(frontiere.ImageNonMarquee):
                Image.new("RGB", (4, 4)).save(dossier / "autre.png")
    assert (dossier / "ok.png").exists()
    assert not (dossier / "autre.png").exists()


def test_le_drapeau_d_extrait_retombe_meme_sur_exception(tmp_path):
    dossier = tmp_path / ident_mod.DOSSIER_REFERENCES
    with frontiere.perimetre(tmp_path):
        with pytest.raises(RuntimeError):
            with frontiere.ecriture_extrait(dossier / "x.png"):
                raise RuntimeError("boum")
        with pytest.raises(frontiere.ImageNonMarquee):
            Image.new("RGB", (4, 4)).save(dossier / "x.png")


def test_un_seul_module_ouvre_chaque_porte():
    """Le pendant statique : `marquage.py` pour les images générées, `identite.py` pour les
    extraits de l'œuvre. Ajouter un appelant demande de l'écrire noir sur blanc."""
    import re
    racine = Path(__file__).resolve().parents[1] / "illustration"
    for fonction, attendu in (("ecriture_marquee", ["marquage.py"]),
                              ("ecriture_extrait", ["identite.py"])):
        appelants = [source.name for source in racine.glob("*.py")
                     if re.search(rf"{fonction}\s*\(",
                                  source.read_text(encoding="utf-8").replace(
                                      f"def {fonction}(", ""))]
        assert appelants == attendu, (fonction, appelants)


# ────────────────────────────  L25.2 — le garde-fou  ────────────────────────────

def test_exiger_references_leve_quand_aucune_n_est_validee(projet):
    config, nom, _, _ = projet
    doc = bible_mod.load(bible_mod.chemin(Path(config["chemins"]["sources"]) / nom))
    refs = ident_mod.references_de(doc, "Silas", Path(config["chemins"]["build"]) / nom)
    with pytest.raises(ident_mod.SansReferenceValidee) as echec:
        ident_mod.exiger_references(refs, "Silas")
    assert "confiance: humaine" in str(echec.value)
    assert "pas de mode « au mieux »" in str(echec.value)


def test_un_personnage_sans_reference_validee_ne_produit_aucune_image(projet, monkeypatch):
    """**Critère 5 du plan**, et il n'a pas de nuance. Le refus a lieu AVANT la bascule VRAM
    et avant la première seconde de GPU.

    ⚠ Il porte sur **cette image**, pas sur le run : sur le corpus réel, 7 personnages sur 11
    n'ont aucune référence validée, et faire échouer le run entier rendrait la voie A
    inutilisable — donc contournée. Les autres images sont produites, le refus est nommé,
    compté, et remonté dans le rapport."""
    config, nom, volume, _ = projet
    monkeypatch.setattr(orchestrateur, "_contexte_de_jugement",
                        lambda reg, projet_, config_: _contexte(config_, projet_))
    orchestrateur.phase_prompt(nom, config, tome=volume)
    dossier = orchestrateur.dossier(config, nom)
    _valider(dossier)
    recap = orchestrateur.phase_image(nom, config, moteur=MoteurFactice())

    assert [r["personnage"] for r in recap["refus"]] == ["Silas"]
    assert recap["motifs"]["sans_reference_validee"] == 1
    assert [Path(i["image"]).stem for i in recap["images"]] == ["tory-noelle"]
    assert not (dossier / "silas.png").exists()
    assert "Silas" in (dossier / "RAPPORT.md").read_text(encoding="utf-8")


def test_un_run_dont_AUCUN_personnage_n_a_de_reference_leve(projet, monkeypatch):
    """Refuser chaque image l'une après l'autre est une chose ; laisser croire qu'un run a eu
    lieu quand rien n'a pu être produit en est une autre."""
    config, nom, volume, _ = projet
    orchestrateur.phase_prompt(nom, config, tome=volume)
    dossier = orchestrateur.dossier(config, nom)
    _valider(dossier, personnages=["Silas"])
    with pytest.raises(ident_mod.SansReferenceValidee, match="Silas"):
        orchestrateur.phase_image(nom, config, moteur=MoteurFactice())
    assert not list(dossier.glob("*.png"))


def test_le_verdict_distingue_rejet_et_marquage():
    """Trois contrôles, trois effets DIFFÉRENTS : la nouveauté rejette, la ressemblance
    marque, le style marque. Les confondre perdrait ce que le plan demande de distinguer."""
    planchers = ident_mod.Planchers(confusion=0.40, nouveaute=0.05,
                                    style_descripteurs=0.10, juge_utilisable=True)

    proche = juge_mod.Grandeurs(ressemblance=0.98, nouveaute=0.01, references=2)
    verdict = ident_mod.juger(proche, planchers)
    assert verdict.rejetee is True and "nouveaute_insuffisante" in verdict.motifs

    faible = juge_mod.Grandeurs(ressemblance=0.20, nouveaute=0.60, references=2)
    verdict = ident_mod.juger(faible, planchers)
    assert verdict.rejetee is False
    assert verdict.marques == {"ressemblance": "faible"}

    hors = juge_mod.Grandeurs(ressemblance=0.80, nouveaute=0.50, style_descripteurs=0.25,
                              descripteur_decroche=("saturation_moyenne", 0.25), references=2)
    verdict = ident_mod.juger(hors, planchers)
    assert verdict.rejetee is False
    assert verdict.marques == {"style": "hors_registre"}
    assert "saturation_moyenne" in verdict.detail_style


def test_un_plancher_non_etalonne_ne_se_prononce_pas():
    """`None` n'est pas 0. Un plancher à 0 est un seuil que rien ne franchit ; un plancher à
    `None` est un contrôle qui ne se prononce pas."""
    grandeurs = juge_mod.Grandeurs(ressemblance=0.01, nouveaute=0.001, references=2)
    verdict = ident_mod.juger(grandeurs, ident_mod.Planchers())
    assert verdict.motifs == [] and verdict.rejetee is False


def test_un_juge_non_utilisable_pose_son_verdict_et_le_signale_non_opposable():
    """L'effacer laisserait croire que rien n'a été mesuré ; le présenter comme un fait
    laisserait croire que le juge sépare. Ni l'un ni l'autre."""
    grandeurs = juge_mod.Grandeurs(ressemblance=0.10, nouveaute=0.90, references=2)
    verdict = ident_mod.juger(grandeurs,
                              ident_mod.Planchers(confusion=0.40, juge_utilisable=False))
    assert "ressemblance_faible" in verdict.motifs
    assert "juge_inutilisable" in verdict.motifs
    assert verdict.marques["juge"] == "non_opposable"


def test_un_juge_absent_est_un_motif_nomme():
    verdict = ident_mod.juger(None, ident_mod.Planchers())
    assert verdict.motifs == ["juge_indisponible"]
    assert verdict.rejetee is False


def test_les_motifs_sont_comptes_et_tries():
    """Convention du dépôt, celle de `manga/detection_retry.py` : nommés, comptés, remontés."""
    verdicts = [ident_mod.Verdict(motifs=["a", "b"]), ident_mod.Verdict(motifs=["b"]),
                ident_mod.Verdict(motifs=["b", "c"])]
    assert ident_mod.compter_motifs(verdicts) == {"b": 3, "a": 1, "c": 1}


def test_tous_les_motifs_ont_un_libelle_lisible():
    for verdict in (ident_mod.juger(None, ident_mod.Planchers()),):
        for motif in verdict.motifs:
            assert ident_mod.MOTIFS_LISIBLES.get(motif)


# ────────────────────────  Le run complet, avec et sans la voie A  ────────────────────────

def _valider(dossier: Path, personnages=None) -> None:
    cible = requete_mod.chemin(dossier)
    doc = requete_mod.load(cible)
    if personnages is not None:
        doc["images"] = [b for b in doc["images"] if b["personnage"] in personnages]
    doc["valide"] = True
    doc["validation"]["par"] = "Alexandre"
    doc["validation"]["date"] = "2026-08-29"
    requete_mod.save(doc, cible)


def test_identite_desarmee_rend_exactement_ce_que_rendait_le_lot_24(projet):
    """L'iso-comportement du §9.3 du contexte agent, vérifié plutôt que raisonné."""
    config, nom, volume, _ = projet
    config["illustration"]["identite"]["actif"] = False
    orchestrateur.phase_prompt(nom, config, tome=volume)
    dossier = orchestrateur.dossier(config, nom)
    _valider(dossier, personnages=["Tory Noelle"])
    recap = orchestrateur.phase_image(nom, config, moteur=MoteurFactice())
    assert recap["identite_active"] is False
    manifeste = json.loads(Path(recap["images"][0]["manifeste"]).read_text(encoding="utf-8"))
    assert "identite" not in manifeste
    assert not (dossier / ident_mod.DOSSIER_REFERENCES).exists()


def test_la_voie_A_branche_les_references_et_ecrit_ses_grandeurs(projet, monkeypatch):
    config, nom, volume, _ = projet
    monkeypatch.setattr(orchestrateur, "_contexte_de_jugement",
                        lambda reg, projet_, config_: _contexte(config_, projet_))
    orchestrateur.phase_prompt(nom, config, tome=volume)
    dossier = orchestrateur.dossier(config, nom)
    _valider(dossier, personnages=["Tory Noelle"])
    recap = orchestrateur.phase_image(nom, config, moteur=MoteurFactice())

    assert recap["identite_active"] is True
    manifeste = json.loads(Path(recap["images"][0]["manifeste"]).read_text(encoding="utf-8"))
    assert manifeste["payload"]["references"], "les références doivent partir au moteur"
    assert "image 1" in manifeste["payload"]["prompt"]
    # ⚠ Le sidecar porte le score ET le plancher : un chiffre sans son dénominateur n'est pas
    # une mesure.
    assert manifeste["identite"]["grandeurs"]["ressemblance"] is not None
    assert "planchers" in manifeste["identite"]
    assert (dossier / ident_mod.DOSSIER_REFERENCES).is_dir()


def test_une_image_trop_proche_de_sa_reference_est_rejetee(projet, monkeypatch):
    """**Critère 4 du plan** : « ce cas n'est pas négociable ». L'image n'est pas écrite du
    tout — pas écrite puis effacée."""
    config, nom, volume, _ = projet
    config["illustration"]["identite"]["planchers"] = {"nouveaute": 0.99}
    monkeypatch.setattr(orchestrateur, "_contexte_de_jugement",
                        lambda reg, projet_, config_: {
                            **_contexte(config_, projet_),
                            "planchers": ident_mod.Planchers(nouveaute=0.99,
                                                             juge_utilisable=True)})
    orchestrateur.phase_prompt(nom, config, tome=volume)
    dossier = orchestrateur.dossier(config, nom)
    _valider(dossier, personnages=["Tory Noelle"])
    recap = orchestrateur.phase_image(nom, config, moteur=MoteurFactice())

    assert recap["images"] == []
    assert [r["motifs"] for r in recap["rejetees"]] == [["nouveaute_insuffisante"]]
    assert recap["motifs"] == {"nouveaute_insuffisante": 1}
    assert not list(dossier.glob("*.png"))
    assert "REJETÉE" not in "".join(p.name for p in dossier.iterdir())


def test_le_rapport_publie_les_trois_grandeurs_cote_a_cote(projet, monkeypatch):
    config, nom, volume, _ = projet
    monkeypatch.setattr(orchestrateur, "_contexte_de_jugement",
                        lambda reg, projet_, config_: _contexte(config_, projet_))
    orchestrateur.phase_prompt(nom, config, tome=volume)
    dossier = orchestrateur.dossier(config, nom)
    _valider(dossier, personnages=["Tory Noelle"])
    orchestrateur.phase_image(nom, config, moteur=MoteurFactice())
    texte = (dossier / "RAPPORT.md").read_text(encoding="utf-8")
    assert "Ressemblance" in texte and "Nouveauté" in texte and "Style (embed.)" in texte
    assert "il ne dit **rien** de la ressemblance" not in texte


def _contexte(config: dict, projet_nom: str) -> dict:
    """Le contexte de jugement, avec l'encodeur factice — pas d'ONNX en CI."""
    doc = bible_mod.load(bible_mod.chemin(Path(config["chemins"]["sources"]) / projet_nom))
    racine = Path(config["chemins"]["build"]) / projet_nom
    ancrages = [c for c in (ident_mod.resoudre(str(a.get("fichier") or ""), racine)
                            for a in (doc["style"]["ancrages"] or [])) if c]
    return {"encodeur": EncodeurFactice(), "ancrages": ancrages,
            "signature": doc["style"]["signature"],
            "planchers": ident_mod.Planchers(confusion=0.5, juge_utilisable=True),
            "encodeur_chemin": "factice.onnx"}


# ────────────────────  Le modèle écrit est celui qui a produit l'image  ────────────────────

def test_le_manifeste_porte_le_modele_EFFECTIF_et_non_l_etiquette(projet, monkeypatch):
    """Défaut de provenance trouvé le 2026-08-29 sur le corpus réel : un `requete.yaml` validé
    la veille annonçait `qwen-image-2512-Q4_1` alors que le graphe d'édition chargeait
    `qwen-image-edit-2511-Q4_1`. Un manifeste qui se trompe de modèle est pire qu'un manifeste
    sans modèle : il a l'air vérifiable."""
    from dataclasses import replace as _replace

    config, nom, volume, _ = projet
    config["illustration"]["identite"]["actif"] = False

    class _MoteurQuiDitSonModele(MoteurFactice):
        def generer(self, requete):
            sortie = super().generer(requete)
            return _replace(sortie, provenance={**sortie.provenance,
                                                "modeles": ["edit-2511-Q4_1.gguf"]})

    orchestrateur.phase_prompt(nom, config, tome=volume)
    dossier = orchestrateur.dossier(config, nom)
    doc = requete_mod.load(requete_mod.chemin(dossier))
    doc["modele"] = "qwen-image-2512-Q4_1"          # l'étiquette, périmée
    doc["images"] = [b for b in doc["images"] if b["personnage"] == "Tory Noelle"]
    doc["valide"], doc["validation"]["par"] = True, "Alexandre"
    requete_mod.save(doc, requete_mod.chemin(dossier))

    recap = orchestrateur.phase_image(nom, config, moteur=_MoteurQuiDitSonModele())
    manifeste = json.loads(Path(recap["images"][0]["manifeste"]).read_text(encoding="utf-8"))
    assert manifeste["modele"] == "edit-2511-Q4_1"
    assert manifeste["moteur_details"]["modeles"] == ["edit-2511-Q4_1.gguf"]
    from illustration import marquage
    assert "2512" not in marquage.relire(recap["images"][0]["image"])["Generator"]


def test_une_etiquette_COHERENTE_est_conservee(projet):
    """Elle est plus lisible qu'un nom de fichier ; elle ne perd que quand elle a tort."""
    from illustration.moteur import Sortie

    sortie = Sortie(png=b"", provenance={"modeles": ["qwen-image-edit-2511-Q4_1.gguf"]})
    assert orchestrateur._modele_effectif("qwen-image-edit-2511-Q4_1", sortie) \
        == "qwen-image-edit-2511-Q4_1"
    assert orchestrateur._modele_effectif("", sortie) == "qwen-image-edit-2511-Q4_1"
    # Un moteur qui ne rapporte rien laisse l'étiquette telle quelle.
    assert orchestrateur._modele_effectif("x", Sortie(png=b"")) == "x"


# ────────────────  Les couvertures : mauvaises références, et pourquoi  ────────────────

def _projet_avec_couverture(tmp_path):
    """Un tome dont la PREMIÈRE référence validée est la couverture — le cas réel."""
    nom = "Projet Couverture"
    sources = tmp_path / "sources" / nom
    sources.mkdir(parents=True)
    media = tmp_path / "build" / nom / "Vol.1" / "media"
    media.mkdir(parents=True)
    # `core/illustrations.py` désigne la couverture par la clé naturelle : `p1` d'abord.
    Image.new("RGB", (700, 1000), (30, 30, 30)).save(media / "p1_couv.png")
    Image.new("RGB", (700, 1000), (80, 80, 80)).save(media / "p40_illus.png")
    Image.new("RGB", (700, 1000), (120, 120, 120)).save(media / "p80_illus.png")

    entree = bible_mod.personnage("Tory Noelle")
    entree["apparence"]["cheveux"] = "gris"
    entree["citations"] = [{"attribut": "cheveux", "source": "c.md", "texte": "gris"}]
    entree["references"] = [{"fichier": f"media/{f}", "role": "identite",
                             "confiance": "humaine"}
                            for f in ("p1_couv.png", "p40_illus.png", "p80_illus.png")]
    entree["valide_par_humain"] = True
    bible_mod.save({"personnages": [entree]}, bible_mod.chemin(sources))
    config = {"chemins": {"sources": str(tmp_path / "sources"),
                          "build": str(tmp_path / "build")},
              "illustration": {"actif": True, "moteur": "factice",
                               "vram": {"decharger_llm": False},
                               "identite": {"actif": True}}}
    return config, nom


def test_la_classe_de_la_reference_vient_du_classifieur_du_lot_23(tmp_path):
    """La MÊME classification, pas une seconde : deux règles, c'est une de trop."""
    ident_mod._CLASSES.clear()
    config, nom = _projet_avec_couverture(tmp_path)
    doc = bible_mod.load(bible_mod.chemin(Path(config["chemins"]["sources"]) / nom))
    refs = ident_mod.references_de(doc, "Tory Noelle", Path(config["chemins"]["build"]) / nom)
    assert [r.couverture for r in refs] == [True, False, False]


def test_une_couverture_passe_APRES_les_autres_references(tmp_path):
    """**Mesuré le 2026-08-29** : les trois premières références validées de `Tory Noelle` sur
    le corpus réel sont trois couvertures de light novel — titre, auteur et numéro de tome
    compris —, dont deux sont le même dessin (cosinus 0,9637). Les prendre dans l'ordre du
    fichier donnait au modèle trois fois la même composition typographiée."""
    ident_mod._CLASSES.clear()
    config, nom = _projet_avec_couverture(tmp_path)
    doc = bible_mod.load(bible_mod.chemin(Path(config["chemins"]["sources"]) / nom))
    refs = ident_mod.references_de(doc, "Tory Noelle", Path(config["chemins"]["build"]) / nom)

    assert [r.source.name for r in ident_mod.retenir(refs, 1)] == ["p40_illus.png"]
    assert [r.source.name for r in ident_mod.retenir(refs, 3)] == [
        "p40_illus.png", "p80_illus.png", "p1_couv.png"]


def test_une_couverture_reste_utilisable_quand_c_est_la_seule(tmp_path):
    """Un personnage dont la couverture est la seule référence n'a pas d'autre choix : la
    repousser en queue ne doit pas la faire disparaître."""
    ident_mod._CLASSES.clear()
    config, nom = _projet_avec_couverture(tmp_path)
    doc = bible_mod.load(bible_mod.chemin(Path(config["chemins"]["sources"]) / nom))
    refs = [r for r in ident_mod.references_de(
        doc, "Tory Noelle", Path(config["chemins"]["build"]) / nom) if r.couverture]
    assert len(ident_mod.retenir(refs, 3)) == 1


def test_le_plafond_du_lot_25_ECARTE_la_couverture_quand_il_y_a_mieux(tmp_path):
    """**Ce que le lot 26 change, et c'est une conséquence de la mesure du lot 25.**

    Le plafond passe de 3 (limite CÂBLÉE du graphe) à 2 (limite MESURÉE : « la rupture est
    entre 1 et 2, pas entre 2 et 3 »). Sur un personnage à trois références validées dont une
    couverture, la couverture — repoussée en queue — tombe donc **hors** du plafond, et le
    problème du titre dans les pixels disparaît de lui-même.

    ⚠ Le motif de l'image écartée doit quand même être lisible : un utilisateur qui voudrait
    la reprendre doit voir pourquoi elle ne l'a pas été (règle 3 du L26.0)."""
    ident_mod._CLASSES.clear()
    config, nom = _projet_avec_couverture(tmp_path)
    orchestrateur.phase_prompt(nom, config, tome="Vol.1")
    dossier = orchestrateur.dossier(config, nom)
    doc = requete_mod.load(requete_mod.chemin(dossier))
    references = doc["images"][0]["references"]
    par_fichier = {Path(c["fichier"]).name: c for c in references}

    assert par_fichier["p1_couv.png"]["retenue"] is False
    assert "plafond" in par_fichier["p1_couv.png"]["motif"]
    assert [c["retenue"] for c in references].count(True) == 2


def test_la_faille_du_titre_dans_les_pixels_est_ECRITE(tmp_path):
    """`marquage._sans_titre` inspecte du TEXTE ; il ne voit pas un titre peint dans une image
    de couverture. La faille est nommée dans le code et **dite à l'utilisateur** pendant le
    run, plutôt que laissée à qui lirait les sources.

    ⚠ Le cas qui compte est celui où la couverture est la **seule** référence validée : la
    repousser en queue ne la fait pas disparaître, parce qu'un personnage sans autre
    référence n'a pas d'autre choix. C'est là, et seulement là, que l'avertissement doit
    tomber — et il tombe **deux fois** : dans le journal de la phase 1, et dans le `motif` de
    l'image dans `requete.yaml`, que l'utilisateur relit."""
    ident_mod._CLASSES.clear()
    config, nom = _projet_avec_couverture(tmp_path)
    # La couverture devient la seule référence validée du personnage.
    chemin_bible = bible_mod.chemin(Path(config["chemins"]["sources"]) / nom)
    doc_bible = bible_mod.load(chemin_bible)
    doc_bible["personnages"][0]["references"] = [
        {"fichier": "media/p1_couv.png", "role": "identite", "confiance": "humaine"}]
    bible_mod.save(doc_bible, chemin_bible)

    dits = []
    reporter = type("R", (), {"info": staticmethod(dits.append)})()
    orchestrateur.phase_prompt(nom, config, tome="Vol.1", reporter=reporter)
    journal = "\n".join(dits)
    assert "COUVERTURE" in journal
    assert "PEINT dans une image" in journal

    dossier = orchestrateur.dossier(config, nom)
    requete = requete_mod.load(requete_mod.chemin(dossier))
    retenue = [c for c in requete["images"][0]["references"] if c["retenue"]]
    assert len(retenue) == 1
    assert "couverture" in retenue[0]["motif"].casefold()
