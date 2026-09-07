# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`requete.yaml`, **la porte humaine**, et le run en deux phases.

Le test central du fichier est `test_la_phase_image_REFUSE_valide_false` : c'est le seul
garde-fou qui garantisse qu'aucun PNG n'existe sans qu'un humain ait validé le prompt qui l'a
produit — la ligne exacte que la politique IA du dossier NLnet exige de pouvoir montrer, et
celle qui distingue « assisté » de « généré ».

Le second est `test_un_attribut_sans_citation_ne_produit_aucune_image` : la règle de citation
de la bible se propage jusqu'ici. Un attribut inventé ne doit pas pouvoir arriver dans un
prompt, parce que plus personne ne saurait ensuite d'où il vient.
"""
import json
from pathlib import Path

import pytest
import yaml

from core import bible as bible_mod
from illustration import orchestrateur, rapport
from illustration import requete as requete_mod
from illustration.moteur import MoteurFactice


@pytest.fixture
def tome(tmp_path):
    """Un projet témoin minimal : une bible avec deux personnages, dont un seul citable."""
    from PIL import Image

    projet, volume = "Projet Témoin", "Vol.1"
    sources = tmp_path / "sources" / projet
    build = tmp_path / "build" / projet / volume
    sources.mkdir(parents=True)
    (build / "media").mkdir(parents=True)
    Image.new("RGB", (32, 48), (210, 190, 170)).save(build / "media" / "illus_01.png")

    citable = bible_mod.personnage("Tory Noelle")
    citable["apparence"]["cheveux"] = "blonds, longs"
    citable["apparence"]["yeux"] = "gris"
    citable["citations"] = [
        {"attribut": "cheveux", "source": "chapters/ch01.md", "texte": "cheveux blonds"},
        {"attribut": "yeux", "source": "media/illus_01.png", "texte": "yeux gris"}]
    citable["references"] = [
        {"fichier": "media/illus_01.png", "role": "identite", "confiance": "humaine"},
        {"fichier": "media/illus_01.png", "role": "style", "confiance": "llm"}]

    # Sans citation : la bible le purgera à l'écriture, donc il n'a aucun attribut.
    muet = bible_mod.personnage("Silas")
    muet["apparence"]["cheveux"] = "noirs"

    bible_mod.save({"personnages": [citable, muet],
                    "style": {"mots": "aquarelle, trait fin"}}, bible_mod.chemin(sources))

    config = {"chemins": {"sources": str(tmp_path / "sources"),
                          "build": str(tmp_path / "build")},
              "illustration": {"actif": True, "moteur": "factice",
                               "vram": {"decharger_llm": False}}}
    return config, projet, volume


def _valider(dossier: Path, par: str = "Alexandre") -> dict:
    cible = requete_mod.chemin(dossier)
    doc = requete_mod.load(cible)
    doc["valide"] = True
    doc["validation"]["par"] = par
    doc["validation"]["date"] = "2026-08-29"
    requete_mod.save(doc, cible)
    return doc


# ──────────────────────────────  Le format d'échange  ──────────────────────────────

def test_le_defaut_est_valide_false():
    """Un défaut à `true` annulerait le garde-fou. C'est la seule valeur possible."""
    assert requete_mod.vide()["valide"] is False


def test_le_fichier_porte_ses_commentaires(tmp_path):
    """JSON ne sait pas porter un commentaire, et la porte humaine dépend entièrement de la
    lisibilité du fichier — c'est pour ça que l'artefact relu est un YAML."""
    cible = requete_mod.save(requete_mod.vide(), tmp_path / "requete.yaml",
                             projet="P", tome="Vol.1")
    texte = cible.read_text(encoding="utf-8")
    assert texte.startswith("# ===")
    assert "REFUSE de démarrer" in texte
    assert "valide" in texte and "--phase image" in texte


def test_un_aller_retour_disque_conserve_une_correction_a_la_main(tmp_path):
    doc = requete_mod.vide()
    doc["images"] = [requete_mod.image_vide("tory")]
    doc["images"][0]["prompt"] = "corrigé à la main"
    cible = requete_mod.save(doc, tmp_path / "requete.yaml")
    assert requete_mod.load(cible)["images"][0]["prompt"] == "corrigé à la main"


def test_tous_les_champs_sont_ecrits_meme_vides(tmp_path):
    """Comme le glossaire et la bible : ce qui est visible se corrige, ce qui est absent
    s'oublie."""
    cible = requete_mod.save({"images": [{"nom": "x"}]}, tmp_path / "requete.yaml")
    bloc = yaml.safe_load(cible.read_text(encoding="utf-8"))["images"][0]
    assert set(bloc) == set(requete_mod.image_vide())


def test_verifier_nomme_les_incoherences(tmp_path):
    doc = requete_mod.vide()
    doc["images"] = [requete_mod.image_vide("a"), requete_mod.image_vide("a"),
                     requete_mod.image_vide("")]
    problemes = requete_mod.verifier(doc)
    assert any("« a »" in p for p in problemes)
    assert any("pas de `nom`" in p for p in problemes)
    assert any("ni prompt ni référence" in p for p in problemes)


def test_une_reference_introuvable_est_signalee(tmp_path):
    doc = requete_mod.vide()
    bloc = requete_mod.image_vide("a")
    bloc["prompt"] = "x"
    bloc["references"] = [{"fichier": "media/absent.png", "motif": "test", "retenue": True}]
    doc["images"] = [bloc]
    assert any("introuvable" in p for p in requete_mod.verifier(doc, racine_projet=tmp_path))


def test_un_requete_yaml_du_lot_25_se_relit_sans_perdre_sa_validation(tmp_path):
    """Le schéma passe de 1 à 2 ; un fichier d'avant reste lisible et **reste validé**.

    ⚠ Un schéma qui redemanderait une validation humaine à chaque lot rendrait la porte
    insupportable, donc contournée. Le motif hérité, lui, dit la VÉRITÉ — personne n'en avait
    écrit — plutôt que d'en inventer un plausible."""
    ancien = {"version": 1, "valide": True,
              "validation": {"par": "Alexandre", "date": "2026-08-29"},
              "modele": "qwen", "images": [
                  {"nom": "tory", "personnage": "Tory Noelle", "prompt": "p",
                   "prompt_negatif": "n", "references": ["media/a.png"],
                   "entites": [{"prompt": "e", "masque": "m.png"}],
                   "image_controle": "c.png", "graine": 7, "pas": 4, "guidage": 1.0}]}
    chemin = tmp_path / "requete.yaml"
    chemin.write_text(yaml.safe_dump(ancien, allow_unicode=True), encoding="utf-8")

    doc = requete_mod.load(chemin)
    assert doc["version"] == 2 and doc["valide"] is True
    bloc = doc["images"][0]
    assert bloc["references"] == [{"fichier": "media/a.png",
                                   "motif": requete_mod.MOTIF_HERITE,
                                   "retenue": True, "par": "herite"}]
    assert bloc["canaux"]["entites"] == [{"prompt": "e", "masque": "m.png"}]
    assert bloc["canaux"]["image_de_controle"] == "c.png"
    assert bloc["graine"] == 7


# ──────────────────────────────  La porte humaine  ──────────────────────────────

def test_exiger_validation_leve_sur_valide_false():
    with pytest.raises(requete_mod.RequeteNonValidee) as echec:
        requete_mod.exiger_validation(requete_mod.vide())
    assert "valide: false" in str(echec.value)
    assert "pas de mode « tout automatique »" in str(echec.value)


def test_exiger_validation_leve_si_personne_n_est_nomme():
    """Le sidecar doit dire QUI a validé : « validé par (vide) » ne montre rien."""
    doc = requete_mod.vide()
    doc["valide"] = True
    doc["images"] = [requete_mod.image_vide("a")]
    with pytest.raises(requete_mod.RequeteNonValidee) as echec:
        requete_mod.exiger_validation(doc)
    assert "validation.par" in str(echec.value)


def test_la_phase_image_REFUSE_valide_false(tome):
    """**LE** test du lot. Aucune image ne doit exister au sortir de cet appel."""
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    with pytest.raises(requete_mod.RequeteNonValidee):
        orchestrateur.phase_image(projet, config, moteur=MoteurFactice())
    assert list(dossier.glob("*.png")) == []
    assert list(dossier.glob("*.provenance.json")) == []


def test_aucune_cle_de_config_ne_contourne_la_porte():
    """La porte n'est pas un réglage : elle n'a pas de clé, et ce test le fige. Si une clé
    d'illustration se met à contenir « valide », « force », « auto » ou « sans_relecture »,
    c'est qu'on est en train de la désarmer."""
    from core.config_schema import CLES_CONNUES

    suspectes = [c for c in CLES_CONNUES if c.startswith("illustration.")
                 and any(mot in c for mot in ("valide", "force", "sans_relecture",
                                              "automatique", "skip"))]
    assert suspectes == [], suspectes


# ──────────────────────────────  Le squelette  ──────────────────────────────

def test_un_attribut_sans_citation_ne_produit_aucune_image(tome):
    """La règle de citation de la bible se propage jusqu'au prompt. Un attribut inventé ne
    doit pas pouvoir arriver dans une image : plus personne ne saurait d'où il vient."""
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    doc = requete_mod.load(requete_mod.chemin(orchestrateur.dossier(config, projet)))
    personnages = {bloc["personnage"] for bloc in doc["images"]}
    assert personnages == {"Tory Noelle"}, "« Silas » n'a aucun attribut cité"


def test_le_prompt_assemble_reprend_les_attributs_et_le_style(tome):
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    doc = requete_mod.load(requete_mod.chemin(orchestrateur.dossier(config, projet)))
    prompt = doc["images"][0]["prompt"]
    assert "cheveux blonds, longs" in prompt and "yeux gris" in prompt
    assert "aquarelle, trait fin" in prompt
    assert "personnage seul" in prompt, "le périmètre arrêté est un personnage seul"


def test_le_genre_CONFIRME_entre_dans_le_prompt():
    """Défaut réel, vu à l'œil sur le premier run réel du 2026-08-29 : « Gale », décrit
    « adulte, cheveux courts foncés, uniforme militaire », est sorti en FEMME — le prompt ne
    portait pas le genre, le modèle n'avait aucune raison de trancher autrement.

    `genre_confirme` est pourtant le champ central de la bible : `core/glossary.py` étiquette
    lui-même la catégorie « Personnages (le genre commande les accords) »."""
    entree = bible_mod.personnage("Gale")
    entree["apparence"]["cheveux"] = "courts foncés"
    entree["citations"] = [{"attribut": "cheveux", "source": "chapters/ch01.md",
                            "texte": "cheveux courts"}]
    entree["genre_confirme"] = "masculin"
    doc = requete_mod.depuis_oeuvre({"personnages": [entree]})
    assert doc["images"][0]["prompt"].startswith("un homme seul,")

    entree["genre_confirme"] = "féminin"
    doc = requete_mod.depuis_oeuvre({"personnages": [entree]})
    # L'accord compte : le dépôt a un glossaire précisément parce que « le genre commande les
    # accords », et ce prompt part dans un modèle qui lit le français.
    assert doc["images"][0]["prompt"].startswith("une femme seule,")


def test_le_genre_du_GLOSSAIRE_prend_le_relais_quand_la_bible_se_tait():
    """**Résultat du lot 26, et il n'a pas coûté une ligne de modèle.**

    Sur le corpus réel, `bible.genre_confirme` vaut `''` sur **11 personnages sur 11** ; le
    glossaire du même projet le porte pour **9 sur 11**. Un champ que la bible ne remplit
    jamais et qu'un autre fichier du dépôt porte déjà n'est pas une donnée manquante : c'est
    une donnée qu'on n'allait pas chercher. Le lot 25 en avait la trace à l'œil — « Gale »,
    sans genre, est sorti en femme.

    ⚠ L'ordre compte : la bible d'abord (confirmée sur un DESSIN), le glossaire ensuite
    (établi sur le TEXTE). Les deux sont légitimes, ils ne disent pas la même chose."""
    entree = bible_mod.personnage("Aria")
    entree["apparence"]["cheveux"] = "longs blonds"
    entree["citations"] = [{"attribut": "cheveux", "source": "chapters/ch01.md",
                            "texte": "cheveux longs"}]
    glossaire = {"personnages": [{"nom": "Aria", "genre": "féminin"}]}
    doc = requete_mod.depuis_oeuvre({"personnages": [entree]}, glossaire)
    assert doc["images"][0]["prompt"].startswith("une femme seule,")

    # Un `?` de glossaire n'est PAS un genre : `core/bible.py` note qu'« une valeur fausse
    # ici coûte plus qu'une valeur absente ».
    doute = {"personnages": [{"nom": "Aria", "genre": "?"}]}
    doc = requete_mod.depuis_oeuvre({"personnages": [entree]}, doute)
    assert doc["images"][0]["prompt"].startswith("un personnage seul,")


def test_un_genre_NON_confirme_ne_fabrique_rien():
    """L'abstention est le défaut, et elle est délibérée : `core/bible.py` note qu'« une
    valeur fausse ici coûte plus qu'une valeur absente ». Sur les 11 personnages de la bible
    réelle de `roman S`, 11 ont `genre_confirme` vide — le champ existe, personne ne l'a rempli,
    et le code ne doit pas inventer à sa place."""
    entree = bible_mod.personnage("Salsa")
    entree["apparence"]["cheveux"] = "noirs"
    entree["citations"] = [{"attribut": "cheveux", "source": "chapters/ch01.md",
                            "texte": "cheveux noirs"}]
    doc = requete_mod.depuis_oeuvre({"personnages": [entree]})
    prompt = doc["images"][0]["prompt"]
    assert prompt.startswith("un personnage seul,")
    assert "homme" not in prompt and "femme" not in prompt


def test_seules_les_references_d_IDENTITE_sont_reprises(tome):
    """Une ancre de STYLE dans le canal d'identité contaminerait le personnage — c'est la
    réserve écrite du `README-ILLUSTRATION-23-27` §4 quater."""
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    doc = requete_mod.load(requete_mod.chemin(orchestrateur.dossier(config, projet)))
    references = doc["images"][0]["references"]
    assert [c["fichier"] for c in references] == ["media/illus_01.png"]
    # Règle 3 du L26.0 : chaque image porte SON motif, retenue comme écartée. Sans lui, la
    # porte humaine se réduit à un clic de confiance.
    assert references[0]["retenue"] is True
    assert references[0]["motif"].strip()


def test_le_prompt_initial_est_archive_avant_toute_correction(tome):
    """Le sidecar doit pouvoir montrer le prompt AVANT et APRÈS correction humaine."""
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    doc = requete_mod.load(requete_mod.chemin(dossier))
    nom = doc["images"][0]["nom"]
    initial = doc["validation"]["prompt_initial"][nom]

    doc["images"][0]["prompt"] = "un prompt entièrement réécrit à la main"
    doc["valide"] = True
    doc["validation"]["par"] = "Alexandre"
    requete_mod.save(doc, requete_mod.chemin(dossier))
    recap = orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    lu = json.loads(Path(recap["images"][0]["manifeste"]).read_text(encoding="utf-8"))
    validation = lu["validation_humaine"]
    assert validation["prompt_avant_correction"] == initial
    assert validation["prompt_apres_correction"] == "un prompt entièrement réécrit à la main"
    assert validation["prompt_avant_correction"] != validation["prompt_apres_correction"]


def test_la_phase_prompt_n_ecrase_pas_une_relecture(tome):
    """`requete.yaml` porte le travail de relecture de l'utilisateur ; le perdre au premier
    `--phase prompt` distrait serait le genre de coût que le dépôt refuse pour le glossaire."""
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    cible = requete_mod.chemin(orchestrateur.dossier(config, projet))
    _valider(cible.parent)
    avant = cible.read_bytes()
    with pytest.raises(FileExistsError):
        orchestrateur.phase_prompt(projet, config, tome=volume)
    assert cible.read_bytes() == avant
    orchestrateur.phase_prompt(projet, config, tome=volume, ecraser=True)
    assert cible.read_bytes() != avant


# ──────────────────────────────  Le run complet  ──────────────────────────────

def test_la_brique_est_desarmee_par_defaut(tome):
    """`illustration.actif: false` est le défaut livré : un utilisateur qui ne touche à rien
    ne voit aucune différence."""
    config, projet, volume = tome
    config["illustration"]["actif"] = False
    with pytest.raises(orchestrateur.BriqueInactive):
        orchestrateur.phase_prompt(projet, config, tome=volume)


def test_le_defaut_du_depot_est_bien_desarme():
    """Le `config.yaml` réellement **LIVRÉ** — celui que git porte, pas celui de la machine.

    ⚠ **La distinction n'est pas un raffinement, et elle a un coût mesuré.** Ce test lisait le
    fichier sur le disque. Or un utilisateur qui ARME la brique — ce qui est le geste normal
    pour s'en servir — faisait alors échouer la suite du dépôt, sur un test qui ne dit rien de
    son installation et tout de ce que le projet publie. Constaté le 2026-08-31.

    Un test qui échoue sur une configuration légitime apprend à ignorer les échecs, et c'est
    exactement ce que la discipline de ce dépôt ne peut pas se permettre — `tests/README.md`
    tient que « un marqueur ne cache pas un test qui pend ».

    On lit donc **`git show HEAD:config.yaml`**, qui est la définition de « livré ». Hors dépôt
    git, on retombe sur le fichier — et on SAUTE plutôt que d'échouer si la copie locale est
    armée, avec le motif écrit."""
    livre = yaml.safe_load(_config_livre())
    assert livre["illustration"]["actif"] is False
    assert livre["illustration"]["moteur"] == "factice"
    assert livre["illustration"]["poids"]["telechargement_auto"] is False
    assert not livre["illustration"]["poids"]["url"]


def _config_livre() -> str:
    """Le `config.yaml` de `HEAD`, ou celui du disque quand git ne répond pas."""
    import subprocess

    racine = Path(__file__).resolve().parent.parent
    try:
        sortie = subprocess.run(["git", "-C", str(racine), "show", "HEAD:config.yaml"],
                                capture_output=True, text=True, timeout=15,
                                encoding="utf-8")
        if sortie.returncode == 0 and sortie.stdout.strip():
            return sortie.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    texte = (racine / "config.yaml").read_text(encoding="utf-8")
    if (yaml.safe_load(texte).get("illustration") or {}).get("actif"):
        pytest.skip("hors dépôt git, et le config.yaml LOCAL est armé : ce test porte sur ce "
                    "que le dépôt LIVRE, pas sur cette machine. Sauté plutôt qu'échoué — un "
                    "test qui échoue sur une configuration légitime apprend à ignorer les "
                    "échecs.")
    return texte


def test_un_run_complet_produit_image_manifeste_rapport_et_perf(tome):
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    _valider(dossier)
    recap = orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    assert len(recap["images"]) == 1
    image = Path(recap["images"][0]["image"])
    assert image.is_file() and image.suffix == ".png"
    assert Path(recap["images"][0]["manifeste"]).is_file()
    assert (dossier / "RAPPORT.md").is_file()
    assert (dossier / "perf.log").is_file()

    texte = (dossier / "RAPPORT.md").read_text(encoding="utf-8")
    assert "ne font pas partie de l'œuvre" in texte
    assert "Bascule de modèle" in texte
    assert "Ce que ce rapport ne dit pas" in texte
    assert projet not in texte, "le nom de l'œuvre ne doit pas figurer dans le rapport"


def test_le_perf_log_de_la_brique_s_ajoute_sans_ecraser(tome):
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    _valider(dossier)
    orchestrateur.phase_image(projet, config, moteur=MoteurFactice())
    premier = (dossier / "perf.log").read_text(encoding="utf-8")
    orchestrateur.phase_image(projet, config, moteur=MoteurFactice())
    second = (dossier / "perf.log").read_text(encoding="utf-8")
    assert second.startswith(premier) and len(second) > len(premier)


def test_la_bascule_ne_decharge_pas_deux_fois_le_meme_modele(tome, monkeypatch):
    """`core.cli.models_in_config` dédoublonne DANS une section, pas ENTRE deux — et la config
    livrée nomme le même `yume-27b` dans `modeles.traducteur` et dans
    `manga.modeles.manga_traducteur`. Mesuré le 2026-08-29 : 4,2 s à deux appels contre 2,0 s
    à un seul, pour un résultat identique."""
    config, projet, volume = tome
    config["illustration"]["vram"]["decharger_llm"] = True
    config["llm"] = {"base_url": "http://localhost:11434/v1"}
    config["modeles"] = {"traducteur": {"model": "yume-27b"}}
    config["manga"] = {"modeles": {"manga_traducteur": {"model": "yume-27b"},
                                   "manga_contexte": {"model": "autre-modele"}}}
    decharges: list[str] = []
    monkeypatch.setattr("core.power.ollama_unload",
                        lambda base_url, model, **k: decharges.append(model) or True)

    orchestrateur.phase_prompt(projet, config, tome=volume)
    _valider(orchestrateur.dossier(config, projet))
    orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    assert decharges == ["yume-27b", "autre-modele"], decharges


def test_la_bascule_a_lieu_une_fois_par_run_et_pas_une_fois_par_image(tome, monkeypatch):
    """Sur huit images, un va-et-vient par image coûterait plus que la génération elle-même."""
    config, projet, volume = tome
    config["illustration"]["vram"]["decharger_llm"] = True
    config["llm"] = {"base_url": "http://localhost:11434/v1"}
    config["modeles"] = {"traducteur": {"model": "yume-27b"}}
    appels: list[str] = []
    monkeypatch.setattr("core.power.ollama_unload",
                        lambda base_url, model, **k: appels.append(model) or True)

    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    doc = _valider(dossier)
    doc["images"] = [doc["images"][0], {**doc["images"][0], "nom": "seconde"},
                     {**doc["images"][0], "nom": "troisieme"}]
    requete_mod.save(doc, requete_mod.chemin(dossier))
    recap = orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    assert len(recap["images"]) == 3
    assert len(appels) == 1, "un déchargement par image au lieu d'un par run"


def _moteur_compteur():
    rendus = []

    class _Compteur(MoteurFactice):
        def decharger(self):
            rendus.append(True)
            return True

    return _Compteur(), rendus


def test_la_phase_image_REND_la_vram_quand_on_le_demande(tome):
    """Le cycle complet du plan de série : décharger le LLM → générer → **rendre la carte**.
    La seconde moitié manquait entièrement, et 12 083 Mio restaient occupés après un run."""
    config, projet, volume = tome
    config["illustration"]["vram"]["decharger_image"] = True
    moteur, rendus = _moteur_compteur()
    orchestrateur.phase_prompt(projet, config, tome=volume)
    _valider(orchestrateur.dossier(config, projet))
    orchestrateur.phase_image(projet, config, moteur=moteur)
    assert rendus == [True], "le moteur doit être déchargé une fois, en fin de run"


def test_le_dechargement_de_l_image_est_DESARME_par_defaut(tome):
    """⚠ Ce n'est pas de la prudence gratuite. Sur **sept** appels à `/free` mesurés le
    2026-08-29, **un a fait segfauter ComfyUI** — violation d'accès 0xC0000005 dans son propre
    `comfy/model_management.py:model_unload`, sous ROCm 7.14 / Windows. Le plantage est chez
    lui, nous ne pouvons pas le corriger, et le dépôt livre désarmé ce que la mesure ne
    soutient pas (même règle que `manga.onomatopees.effacement.mode`)."""
    config, projet, volume = tome
    config["illustration"]["vram"].pop("decharger_image", None)
    moteur, rendus = _moteur_compteur()
    orchestrateur.phase_prompt(projet, config, tome=volume)
    _valider(orchestrateur.dossier(config, projet))
    orchestrateur.phase_image(projet, config, moteur=moteur)
    assert rendus == []


def test_le_defaut_livre_laisse_le_dechargement_desarme():
    """Dans le `config.yaml` réellement livré, pas dans une fixture."""
    racine = Path(__file__).resolve().parent.parent
    livre = yaml.safe_load((racine / "config.yaml").read_text(encoding="utf-8"))
    assert livre["illustration"]["vram"]["decharger_image"] is False
    assert livre["illustration"]["vram"]["decharger_llm"] is True


def test_le_verdict_de_bascule_porte_son_denominateur():
    """La règle des chiffres : « 4 s de bascule » ne veut rien dire sans le prix d'une image
    en face, ni sans le nombre d'images."""
    recap = {"bascule_secondes": 40.0,
             "images": [{"secondes": 2.0, "image": "a.png"},
                        {"secondes": 2.0, "image": "b.png"}]}
    phrase = rapport.verdict_bascule(recap)
    assert "20.0 image(s)" in phrase and "sur 2 image(s)" in phrase
    assert "c'est la bascule qu'il faut optimiser" in phrase

    calme = rapport.verdict_bascule({"bascule_secondes": 4.0,
                                     "images": [{"secondes": 20.0, "image": "a.png"}]})
    assert "sous le seuil" in calme


def test_une_requete_incoherente_validee_ne_genere_rien(tome):
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    doc = _valider(dossier)
    doc["images"][0]["references"] = [
        {"fichier": "media/absent.png", "motif": "test", "retenue": True}]
    requete_mod.save(doc, requete_mod.chemin(dossier))
    with pytest.raises(ValueError) as echec:
        orchestrateur.phase_image(projet, config, moteur=MoteurFactice())
    assert "introuvable" in str(echec.value)
    assert list(dossier.glob("*.png")) == []


# ──────────────────────────────  Le rejeu  ──────────────────────────────

def test_le_rejeu_reconstruit_la_requete_et_compare(tome):
    """L24.5 : deux exécutions de la même requête produisent-elles deux PNG identiques ?
    Avec le moteur factice, déterministe par construction, la réponse doit être oui — c'est
    ce qui rend le dispositif de mesure lui-même vérifiable."""
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    _valider(dossier)
    recap = orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    rejeu = orchestrateur.rejouer(recap["images"][0]["manifeste"], config,
                                  moteur=MoteurFactice())
    assert rejeu["empreinte_requete"] == recap["images"][0]["empreinte_requete"]
    assert rejeu["identique"] is True
    assert Path(rejeu["image"]).name.endswith(".rejeu.png")


def test_le_rejeu_produit_aussi_une_image_marquee(tome):
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    _valider(dossier)
    recap = orchestrateur.phase_image(projet, config, moteur=MoteurFactice())
    rejeu = orchestrateur.rejouer(recap["images"][0]["manifeste"], config,
                                  moteur=MoteurFactice())
    from illustration import marquage
    assert marquage.relire(rejeu["image"])["AIGenerated"] == "true"
    lu = json.loads(Path(rejeu["manifeste"]).read_text(encoding="utf-8"))
    assert lu["validation_humaine"]["rejeu_de"].endswith(".provenance.json")


def test_un_moteur_non_deterministe_est_signale_et_non_masque(tome):
    """« Un lot qui publie *le backend n'est pas reproductible, voici de combien* est un lot
    réussi ; un lot qui affirme la reproductibilité sans l'avoir mesurée ne l'est pas. »"""
    config, projet, volume = tome
    orchestrateur.phase_prompt(projet, config, tome=volume)
    dossier = orchestrateur.dossier(config, projet)
    _valider(dossier)
    recap = orchestrateur.phase_image(projet, config, moteur=MoteurFactice())

    class _Instable(MoteurFactice):
        nom = "instable"

        def generer(self, requete):
            return super().generer(requete.avec(prompt=requete.prompt + " (bruit)"))

    rejeu = orchestrateur.rejouer(recap["images"][0]["manifeste"], config,
                                  moteur=_Instable())
    assert rejeu["identique"] is False
