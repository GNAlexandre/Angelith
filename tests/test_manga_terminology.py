# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Cohérence terminologique manga (lot 3) : forçage des formes canoniques et relevé par le
terminologue.

Le défaut visé, mesuré sur *manga A* Vol.1 : une même chaîne source ressort
avec plusieurs orthographes françaises, parce que chaque planche est traduite en isolation.
Les deux lignes les plus parlantes portent sur des **kanji** — `三影` → Mitsukage / Mikage /
Miyage, `弥月` → Yuzuki / Yozuki / Miyuki — strictement identiques d'une bulle à l'autre :
aucune ambiguïté de lecture ne l'explique, c'est le modèle qui hésite.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image, ImageDraw

from core import glossary, glossary_build
from manga import checkpoints, terminology
from manga.detection import BubbleRegion

RACINE = Path(__file__).resolve().parents[1]
BOX = (60, 40, 340, 200)
TAILLE = (400, 260)


def _glo(*entrees):
    g = glossary.empty()
    for cat, e in entrees:
        g.setdefault(cat, []).append(e)
    return g


# Format réel de sortie du terminologue (cf. `core.glossary_build.parse_notes` et
# `prompts/terminologue.md`) : une section, puis « - Nom | champ: valeur | … ».
_NOTES = ("## Personnages\n"
          "- Libertina | genre: féminin | interdits: Ribitina, Libidina | "
          "termes_source: リベルティナ | Sœur aînée.\n")


def _perso(nom, interdits, genre=""):
    return ("personnages", {"nom": nom, "genre": genre, "variantes": [], "interdits": interdits,
                            "role": "", "description": "", "force": True})


# --------------------------------------------------------------------------- #
# forcer_bulles
# --------------------------------------------------------------------------- #

def test_une_forme_bannie_est_remplacee_dans_chaque_bulle():
    glo = _glo(_perso("Mitsukage", ["Mikage", "Miyage"]))
    textes, n, refus = terminology.forcer_bulles(
        ["Mikage, toi aussi !", "Rien à voir", "Le lieutenant Miyage"], glo)
    assert textes == ["Mitsukage, toi aussi !", "Rien à voir", "Le lieutenant Mitsukage"]
    assert (n, refus) == (2, [])


def test_le_forcage_est_insensible_a_la_casse_mais_ne_rabaisse_pas():
    glo = _glo(_perso("Kataphrakt", ["katafrakt"]))
    textes, n, _ = terminology.forcer_bulles(["Un KATAFRAKT approche", "un katafrakt"], glo)
    assert textes == ["Un Kataphrakt approche", "un Kataphrakt"]
    assert n == 2


def test_les_bulles_vides_traversent_sans_dommage():
    glo = _glo(_perso("Yuzuki", ["Yozuki"]))
    textes, n, _ = terminology.forcer_bulles(["", "   ", None, "Yozuki !"], glo)
    assert textes == ["", "   ", None, "Yuzuki !"]
    assert n == 1


def test_un_glossaire_vide_ou_sans_force_ne_touche_a_rien():
    for glo in (None, {}, glossary.empty()):
        textes, n, refus = terminology.forcer_bulles(["Mikage"], glo)
        assert (textes, n, refus) == (["Mikage"], 0, [])


def test_le_forcage_est_bulle_par_bulle_et_non_sur_la_page_concatenee():
    """Point de conception : `enforce_force` lit une fenêtre de contexte ARRIÈRE pour décider
    de l'accord et de l'élision. La fin d'une bulle n'est pas le contexte grammatical du
    début de la suivante — concaténer ferait lire « une » comme déterminant du premier mot
    d'après, et refuserait le remplacement pour conflit de genre.

    Ici : bulle 1 finit par « une », bulle 2 commence par une forme bannie masculine. Bulle
    par bulle, le remplacement passe."""
    glo = _glo(_perso("Cruhteo", ["Kuran"], genre="masculin"))
    textes, n, refus = terminology.forcer_bulles(["C'est une", "Kuran arrive."], glo)
    assert textes[1] == "Cruhteo arrive."
    assert (n, refus) == (1, [])


def test_un_conflit_de_genre_est_refuse_et_signale():
    """Le déterministe ne doit JAMAIS introduire une faute que le modèle n'aurait pas faite :
    corriger le seul nom laisserait l'article et les adjectifs au genre d'origine."""
    glo = _glo(_perso("Cruhteo", ["Kuran"], genre="masculin"))
    textes, n, refus = terminology.forcer_bulles(["une Kuran expérimentée"], glo)
    assert textes == ["une Kuran expérimentée"]      # inchangé
    assert n == 0 and len(refus) == 1
    assert "Kuran" in refus[0] and "Cruhteo" in refus[0]


def test_le_forcage_traverse_une_elision(regression=True):
    """`l'Areyon` → `l'Areion` : la forme bannie est collée à une élision. C'est le cas que
    `tools/compter_variantes.py` ratait dans sa première version — l'apostrophe étant exclue
    de ses frontières de mot, il ne comptait pas l'occurrence et l'aurait donc déclarée
    éliminée sans qu'elle le soit."""
    glo = _glo(("termes", {"nom": "Areion", "traduire": False, "variantes": [],
                           "interdits": ["Areyon"], "description": "", "force": True}))
    textes, n, _ = terminology.forcer_bulles(["Comme prévu, l'Areyon est résistant."], glo)
    assert textes == ["Comme prévu, l'Areion est résistant."]
    assert n == 1


def test_compter_forcees_distingue_zero_entree_de_zero_remplacement():
    """Le rapport doit pouvoir dire « rien à forcer » (la cohérence n'est pas garantie) et
    « rien n'a eu besoin de l'être » (tout était déjà canonique) — deux situations opposées."""
    assert terminology.compter_forcees(glossary.empty()) == 0
    assert terminology.compter_forcees(_glo(_perso("Yuzuki", []))) == 1
    sans_force = _glo(("personnages", {"nom": "X", "force": False, "interdits": ["Y"]}))
    assert terminology.compter_forcees(sans_force) == 0


# --------------------------------------------------------------------------- #
# Détection de DÉRIVE — les formes que le glossaire n'a pas ENCORE bannies
#
# Le forçage ne rattrape que ce qu'on lui a listé. Sur le run v0.21.0 du Vol.1, les
# `interdits` listaient les fautes du run précédent et le tome en a produit de nouvelles :
# `compter_variantes.py` annonçait « 0 forme bannie » — exact, et trompeur.
# --------------------------------------------------------------------------- #

def _entree_src(nom, src, interdits=(), cat="personnages", force=True):
    return (cat, {"nom": nom, "variantes": [], "interdits": list(interdits),
                  "termes_source": [src], "description": "", "force": force})


def test_libentina_est_detectee_par_ancrage_sur_le_japonais():
    """LE cas mesuré : `リベルティナ` dans l'OCR de la bulle, `Libentina` dans son français.

    Rien à interpréter — la bulle parle bien de cette entité. C'est la seule preuve qui ne
    repose sur aucune statistique de volume, d'où le droit de corriger le run en cours."""
    glo = _glo(_entree_src("Libertina", "リベルティナ", ["Ribitina"]))
    d = terminology.derives_ancrees(glo, ["リベルティナは…"], ["Libentina arrive"], page=73)
    assert [(x.candidat, x.nom, x.niveau, x.page, x.bulle) for x in d] == [
        ("Libentina", "Libertina", "T1", 73, 1)]


def test_sans_le_terme_source_dans_LA_MEME_bulle_rien_nest_ancre():
    """L'ancrage est bulle à bulle : un nom cité trois bulles plus loin ne prouve rien."""
    glo = _glo(_entree_src("Libertina", "リベルティナ"))
    assert terminology.derives_ancrees(glo, ["こんにちは"], ["Libentina arrive"]) == []


@pytest.mark.parametrize("a,b", [("Qu'est-ce", "Est-ce"), ("Désolé", "Désolée"),
                                 ("Comte", "Vicomte"), ("Cibles", "Cible"),
                                 ("Attaque", "Attaquez"), ("Allez-y", "Allez"),
                                 ("Mitsukage", "Mitsukage-san")])
def test_les_faux_positifs_mesures_sont_tous_rejetes(a, b):
    """Les groupes de bruit que le mode exploratoire remontait sur ce tome.

    À son seuil de 0,78, `difflib.SequenceMatcher` produit **11 groupes dont 9 de bruit** :
    des flexions françaises (`Désolé`/`Désolée`), un préfixe (`Comte`/`Vicomte`), un suffixe
    honorifique (`Mitsukage-san`). Le correctif n'est pas un meilleur seuil — c'est de ne
    comparer qu'aux **noms du glossaire**, jamais les mots entre eux."""
    import difflib
    assert difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.78
    glo = _glo(_entree_src("Libertina", "リベルティナ"),
               _entree_src("Mitsukage", "三影"))
    assert terminology.derives_de_volume(glo, [f"Voici {a} puis {b}, dit Libertina."]) == []


@pytest.mark.parametrize("mot", ["Les", "Des", "Vos", "Ses", "Tes", "Mars", "Vers"])
def test_un_nom_canonique_TROP_COURT_nest_jamais_surveille(mot):
    """`Vers`, l'organisation de ce tome, est à distance 1 de « Mers » et de la préposition
    « vers ». Le surveiller reviendrait à bannir des mots français — limite assumée."""
    court = _glo(_entree_src(mot, "テスト"))
    assert terminology.derives_de_volume(court, ["Il part vers Mars, dit-il."]) == []
    assert terminology.derives_ancrees(court, ["テスト"], ["Il part vers Mers."]) == []


def test_avion_nest_PAS_detecte_pour_areion():
    """Limite ASSUMÉE, testée pour qu'un élargissement futur la casse bruyamment.

    `Areion`/`Avion` = 2 éditions sur 6 caractères, au-delà du budget. Tout réglage assez
    large pour l'attraper rattrape aussi « Les » → « Vers »."""
    assert terminology.distance_edition("Areion", "Avion") == 2
    assert terminology.budget_edition("Areion") == 1
    glo = _glo(_entree_src("Areion", "アレイオン", cat="termes"))
    d = terminology.derives_ancrees(glo, ["アレイオンが"], ["L'Avion décolle enfin"])
    assert d == []


def test_la_distance_est_une_VRAIE_distance_dedition():
    assert terminology.distance_edition("Libertina", "Libentina") == 1
    assert terminology.distance_edition("Libertina", "Libertaine") == 2
    assert terminology.distance_edition("Kataphrakt", "Kataphrakt") == 0
    # Bornée : au-delà du budget elle cesse de compter, et le dit sans mentir sur le sens.
    assert terminology.distance_edition("Libertina", "Kataphrakt", 2) == 3
    assert terminology.distance_edition("Libertina", "Libertina", 0) == 0


def test_le_budget_est_proportionnel_a_la_longueur():
    assert terminology.budget_edition("Felsen") == 1        # 6 ≤ 7
    assert terminology.budget_edition("Cruhteo") == 1       # 7 ≤ 7
    assert terminology.budget_edition("Libertina") == 2     # 9 > 7


def test_une_derive_va_dans_INTERDITS_jamais_dans_VARIANTES():
    """⚠ Le garde-fou cardinal du lot. `variantes` est la CLÉ DE RECHERCHE de
    `glossary_build._find_any` : y déposer une faute ferait fusionner une future entrée
    légitime dans la mauvaise, silencieusement et durablement."""
    glo = _glo(_entree_src("Libertina", "リベルティナ"))
    d = terminology.derives_ancrees(glo, ["リベルティナ"], ["Libentina arrive"])
    assert terminology.appliquer_derives(glo, d) == 1
    entree = glo["personnages"][0]
    assert entree["interdits"] == ["Libentina"]
    assert entree["variantes"] == []

    # …et la propriété doit tenir pour TOUTE dérive écrite, pas seulement celle-ci.
    index = glossary_build.build_index(glo)
    assert "libentina" not in index.get("personnages", {})


def test_appliquer_derives_est_idempotent():
    glo = _glo(_entree_src("Libertina", "リベルティナ"))
    d = terminology.derives_ancrees(glo, ["リベルティナ"], ["Libentina arrive"])
    assert terminology.appliquer_derives(glo, d) == 1
    assert terminology.appliquer_derives(glo, d) == 0
    assert glo["personnages"][0]["interdits"] == ["Libentina"]


def test_une_T3_nest_JAMAIS_ecrite():
    """T3 est une piste pour le rapport, pas une décision : la distance seule ne suffit pas
    à bannir une forme du texte d'un tome."""
    t3 = terminology.Derive(nom="Libertina", candidat="Libentina", categorie="personnages",
                            niveau="T3")
    glo = _glo(_entree_src("Libertina", "リベルティナ"))
    assert terminology.appliquer_derives(glo, [t3]) == 0
    assert glo["personnages"][0]["interdits"] == []


def test_T2_exige_que_le_nom_DOMINE_le_tome():
    """Une forme majoritaire n'est pas une faute d'orthographe, c'est un choix de traduction
    — et l'écraser serait pire que de la laisser."""
    glo = _glo(_entree_src("Libertina", "リベルティナ"))
    domine = ["Libertina parle à Libertina."] * 4 + ["Une seule Libentina, ici."]
    niveaux = {d.candidat: d.niveau for d in terminology.derives_de_volume(glo, domine)}
    assert niveaux == {"Libentina": "T2"}

    minoritaire = ["Libertina parle."] + ["Ici, Libentina répond."] * 4
    niveaux = {d.candidat: d.niveau for d in terminology.derives_de_volume(glo, minoritaire)}
    assert niveaux == {"Libentina": "T3"}


def test_T3_exige_une_capitale_en_MILIEU_de_phrase():
    """En tête de réplique, une capitale ne prouve rien — dans une bulle, presque tout mot
    peut s'y trouver."""
    glo = _glo(_entree_src("Libertina", "リベルティナ"))
    assert terminology.derives_de_volume(glo, ["Libentina arrive."]) == []
    d = terminology.derives_de_volume(glo, ["Voici Libentina."])
    assert [x.niveau for x in d] == ["T3"]


def test_le_pluriel_nest_pas_une_derive_mais_un_champ_manquant():
    """`Kataphrakts` ×8 sur le tome : le bannir remplacerait le pluriel par le singulier au
    milieu d'une phrase. Le champ `pluriel:` existe pour cela."""
    glo = _glo(_entree_src("Kataphrakt", "カタフラクト", cat="termes"))
    assert terminology.est_pluriel("Kataphrakt", "Kataphrakts") is True
    textes = ["Deux Kataphrakts contre un Kataphrakt."]
    assert terminology.derives_de_volume(glo, textes) == []
    assert terminology.proposer_pluriels(glo, textes) == [("Kataphrakt", "Kataphrakts", 1)]


def test_un_pluriel_deja_declare_nest_plus_propose():
    glo = _glo(_entree_src("Kataphrakt", "カタフラクト", cat="termes"))
    glo["termes"][0]["pluriel"] = "Kataphrakts"
    assert terminology.proposer_pluriels(glo, ["Deux Kataphrakts."]) == []


def test_une_forme_DEJA_bannie_nest_pas_une_derive_a_decouvrir():
    """Elle est déjà du ressort du forçage : la re-signaler ferait du bruit à chaque run."""
    glo = _glo(_entree_src("Libertina", "リベルティナ", ["Libentina"]))
    assert terminology.derives_ancrees(glo, ["リベルティナ"], ["Libentina arrive"]) == []


def test_le_comptage_traverse_une_elision():
    """Même frontière de mot que `enforce_force` : `l'Areyon` DOIT être compté, sinon une
    forme bannie survivant à une élision passerait pour éliminée."""
    assert terminology.compter_occurrences(["Comme prévu, l'Areyon tient."], "Areyon") == 1


# --------------------------------------------------------------------------- #
# terminologue
# --------------------------------------------------------------------------- #

class _FauxAgent:
    def __init__(self, reponse="- (rien à signaler)"):
        self.reponse, self.appels = reponse, []

    def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
        self.appels.append(user)
        return self.reponse


def test_le_contexte_donne_le_japonais_comme_source():
    """C'est le japonais qui permet d'ancrer « リベルティナ → Libertina » plutôt que de
    constater une orthographe française au hasard (champ `termes_source`)."""
    user = terminology.contexte_terminologue("", 7, 150, ["リベルティナ", "", "こんにちは"])
    assert "リベルティナ" in user and "こんにちは" in user
    assert "PLANCHE 7/150" in user
    assert "\n2. " not in user, "les bulles vides ne doivent pas occuper un numéro"


def test_le_francais_deja_produit_est_joint_quand_il_existe():
    """Sur un tome DÉJÀ traduit, c'est lui qui montre au terminologue les variantes
    réellement produites — donc de quoi les lister en `interdits`."""
    user = terminology.contexte_terminologue("", 1, 1, ["三影"], deja_fr=["Mikage, toi aussi"])
    assert "Mikage" in user and "interdits" in user


def test_une_planche_sans_texte_ne_consomme_aucun_appel():
    agent = _FauxAgent()
    notes, ajouts = terminology.relever_page(agent, glossary.empty(), {}, page=1, total=1,
                                             texts_jp=["", "  ", None])
    assert notes == "" and agent.appels == []
    assert ajouts == {"ajouts": 0, "fusions": 0, "conflits": 0}


def test_un_releve_est_fusionne_aussitot_dans_le_glossaire():
    """Fusion INCRÉMENTALE comme côté light novel : chaque planche voit le glossaire déjà
    construit par les précédentes, ce qui évite les décisions contradictoires."""
    glo = glossary.empty()
    index = glossary_build.build_index(glo)
    agent = _FauxAgent(_NOTES)
    notes, ajouts = terminology.relever_page(agent, glo, index, page=1, total=2,
                                             texts_jp=["リベルティナ"])
    assert ajouts["ajouts"] == 1
    assert [e["nom"] for e in glo["personnages"]] == ["Libertina"]
    # …et l'index a suivi : la planche suivante ne doit pas recréer un doublon.
    terminology.fusionner(_NOTES, glo, index)
    assert len(glo["personnages"]) == 1


def test_le_glossaire_deja_construit_est_donne_en_contexte():
    glo = _glo(_perso("Libertina", ["Ribitina"], genre="féminin"))
    agent = _FauxAgent()
    terminology.relever_page(agent, glo, glossary_build.build_index(glo),
                             page=2, total=2, texts_jp=["リビティナ"])
    assert "Libertina" in agent.appels[0]


def test_des_notes_vides_ne_cassent_pas_la_fusion():
    glo = glossary.empty()
    assert terminology.fusionner("", glo, {})["ajouts"] == 0
    assert terminology.fusionner("   \n", glo, {})["ajouts"] == 0


# --------------------------------------------------------------------------- #
# La CLI et le graphe d'étapes ne doivent pas dériver
# --------------------------------------------------------------------------- #

def test_les_etapes_de_la_cli_suivent_celles_des_checkpoints():
    """`run_manga.ETAPES` recopie `checkpoints.STAGES` au lieu de l'importer, pour ne pas
    tirer numpy et Pillow sur un `--version` (0,19 s → 0,46 s mesurés). Le prix de cette
    optimisation est ce test : sans lui, ajouter une étape laisserait `--from` muet dessus."""
    import run_manga
    assert run_manga.ETAPES == checkpoints.STAGES


# --------------------------------------------------------------------------- #
# Bout en bout dans l'orchestrateur, sans LLM
# --------------------------------------------------------------------------- #

def _planche() -> Image.Image:
    img = Image.new("RGB", TAILLE, (20, 20, 20))
    ImageDraw.Draw(img).ellipse(list(BOX), fill=(255, 255, 255), outline=(0, 0, 0), width=4)
    return img


def _masque() -> np.ndarray:
    m = Image.new("L", TAILLE, 0)
    ImageDraw.Draw(m).ellipse(list(BOX), fill=255)
    return np.asarray(m) > 127


@pytest.fixture
def tome(tmp_path):
    """Tome d'une page, tout en cache jusqu'à la traduction — la traduction contenant une
    forme bannie. Plus un glossaire d'œuvre qui la bannit."""
    vol = tmp_path / "sources" / "MonManga" / "Vol.1" / "manga"
    vol.mkdir(parents=True)
    page = _planche()
    page.save(vol / "page_0001.png")

    build_dir = tmp_path / "build" / "MonManga" / "Vol.1" / "manga"
    (build_dir / "pages_out").mkdir(parents=True)
    (build_dir / "pages_clean").mkdir(parents=True)
    ckpt = checkpoints.page_checkpoint_dir(build_dir, 1)
    region = BubbleRegion(bbox=BOX, mask=_masque(), score=0.95, cls=0)
    checkpoints.save_regions(ckpt, [region], page.size)
    from manga.clean import clean_bubbles
    clean_bubbles(page, [region]).save(checkpoints.clean_page_path(build_dir, 1))
    checkpoints.save_ocr(ckpt, ["三影"])
    checkpoints.save_traduction(ckpt, ["Mikage arrive"])

    glossary.save(_glo(_perso("Mitsukage", ["Mikage", "Miyage"])),
                  tmp_path / "sources" / "MonManga" / "glossaire.yaml")

    config = yaml.safe_load((RACINE / "config.yaml").read_text(encoding="utf-8"))
    config["chemins"]["sources"] = str(tmp_path / "sources")
    config["chemins"]["build"] = str(tmp_path / "build")
    config["chemins"]["prompts"] = str(RACINE / "prompts")
    # Les prompts et le guide de style vivent dans le PACK de langue cible.
    # Désigné en absolu : `pytest` tourne depuis un `tmp_path`, où `langues/`
    # relatif n'existe pas.
    config.setdefault("langues", {})["packs"] = str(RACINE / "langues")
    config["manga"]["detection"]["model_path"] = str(tmp_path / "absent.onnx")
    # ⚠ Neutraliser le détecteur de BULLES ne suffit pas : la passe `sfx` est hors du graphe
    # d'invalidation, donc elle tourne même sur un tome déjà en cache et charge le vrai
    # `text_detector.onnx` — 110 s d'inférence CPU par planche. Aucun test d'ici ne porte sur
    # le texte hors bulle ; `test_manga_text_detection.py` s'en charge.
    config["manga"]["onomatopees"]["actif"] = False
    config.setdefault("options", {})["dry_run"] = True
    return config, build_dir, ckpt, tmp_path


def _run(config, **kw):
    from core.reporter import Reporter

    from manga.orchestrator_manga import process_volume
    return process_volume("MonManga", "Vol.1", config, reporter=Reporter(), **kw)


def test_le_glossaire_est_applique_sans_retraduire(tome):
    """LE gain du lot : `--from rendu` suffit à réécrire un tome entier, sans un seul appel
    LLM — parce que le forçage s'applique à l'USAGE et non à l'écriture du cache."""
    config, build_dir, ckpt, _ = tome
    assert _run(config, restart_from="rendu") is True

    # Le cache garde la sortie BRUTE du modèle…
    assert checkpoints.load_traduction(ckpt) == ["Mikage arrive"]
    # …et ce qui est enregistré comme dessiné sur la planche est la forme canonique.
    qa = json.loads((ckpt / "qa.json").read_text(encoding="utf-8"))
    assert qa["bulles"][0]["traduction"] == "Mitsukage arrive"


def test_corriger_le_glossaire_et_relancer_suffit(tome):
    """Conséquence directe du choix « forcer à l'usage » : changer la forme canonique et
    relancer `--from rendu` réécrit tout. Stocker le texte forcé imposerait de retraduire."""
    config, build_dir, ckpt, tmp_path = tome
    _run(config, restart_from="rendu")
    glossary.save(_glo(_perso("Mitsukage Haruya", ["Mikage", "Mitsukage"])),
                  tmp_path / "sources" / "MonManga" / "glossaire.yaml")
    _run(config, restart_from="rendu")
    qa = json.loads((ckpt / "qa.json").read_text(encoding="utf-8"))
    assert qa["bulles"][0]["traduction"] == "Mitsukage Haruya arrive"


def test_le_rapport_compte_les_remplacements(tome):
    config, build_dir, _ckpt, _ = tome
    _run(config, restart_from="rendu")
    rapport = (build_dir / "RAPPORT.md").read_text(encoding="utf-8")
    assert "1 entrée(s) `force: true`" in rapport
    assert "1 remplacement(s) appliqué(s)" in rapport


def test_le_rapport_signale_un_glossaire_qui_nimpose_rien(tome):
    """« 0 remplacement » ne veut rien dire tout seul : sans entrée `force: true`, la
    cohérence des noms n'est simplement pas garantie, et le rapport doit le dire."""
    config, build_dir, _ckpt, tmp_path = tome
    glossary.save(glossary.empty(), tmp_path / "sources" / "MonManga" / "glossaire.yaml")
    _run(config, restart_from="rendu")
    rapport = (build_dir / "RAPPORT.md").read_text(encoding="utf-8")
    assert "aucune entrée `force: true`" in rapport


def _bannir_par_derive(tome, ocr, traduction):
    """Prépare le tome pour la détection de dérive : une entrée ANCRÉE sur le japonais, et
    une traduction qui en écorche le nom. Renvoie le chemin du glossaire."""
    config, _build_dir, ckpt, tmp_path = tome
    gpath = tmp_path / "sources" / "MonManga" / "glossaire.yaml"
    glossary.save(_glo(_entree_src("Mitsukage", "三影")), gpath)
    checkpoints.save_ocr(ckpt, [ocr])
    checkpoints.save_traduction(ckpt, [traduction])
    config["options"]["dry_run"] = False        # `--from rendu` ne fait aucun appel LLM
    return gpath


def test_une_derive_ancree_est_corrigee_DANS_ce_run(tome):
    """Le bout en bout du lot : une forme que PERSONNE n'avait bannie est détectée sur le
    japonais de la bulle, écrite en `interdits`, et corrigée par `enforce_force` — inchangé —
    avant même que la planche ne soit lettrée. Zéro appel LLM."""
    config, build_dir, ckpt, _ = tome
    gpath = _bannir_par_derive(tome, "三影", "Mitsukago arrive")
    assert _run(config, restart_from="rendu") is True

    # Le cache garde la sortie brute ; la planche, elle, porte la forme canonique.
    assert checkpoints.load_traduction(ckpt) == ["Mitsukago arrive"]
    qa = json.loads((ckpt / "qa.json").read_text(encoding="utf-8"))
    assert qa["bulles"][0]["traduction"] == "Mitsukage arrive"

    # …et la boucle est fermée : le glossaire de l'ŒUVRE connaît désormais la faute.
    entree = glossary.load(gpath)["personnages"][0]
    assert entree["interdits"] == ["Mitsukago"]
    assert entree["variantes"] == []          # ⚠ JAMAIS ici : clé de recherche du dédoublonneur


def test_la_derive_est_listee_au_rapport_avec_sa_preuve(tome):
    config, build_dir, _ckpt, _ = tome
    _bannir_par_derive(tome, "三影", "Mitsukago arrive")
    _run(config, restart_from="rendu")
    rapport = (build_dir / "RAPPORT.md").read_text(encoding="utf-8")
    assert "[T1] « Mitsukago » → « Mitsukage »" in rapport
    assert "三影" in rapport                   # la preuve, pas seulement le verdict


def test_en_dry_run_la_derive_est_signalee_mais_le_glossaire_INTACT(tome):
    """`sources/` est une entrée de l'utilisateur, pas un artefact de build."""
    config, build_dir, _ckpt, _ = tome
    gpath = _bannir_par_derive(tome, "三影", "Mitsukago arrive")
    config["options"]["dry_run"] = True
    avant = gpath.read_bytes()
    _run(config, restart_from="rendu")
    assert gpath.read_bytes() == avant
    assert "[T1]" in (build_dir / "RAPPORT.md").read_text(encoding="utf-8")


def test_une_derive_deja_bannie_ne_reecrit_plus_le_glossaire(tome):
    """Idempotence : relancer un tome déjà analysé ne doit ni réécrire la source ni refaire
    du bruit au rapport."""
    config, _build_dir, _ckpt, _ = tome
    gpath = _bannir_par_derive(tome, "三影", "Mitsukago arrive")
    _run(config, restart_from="rendu")
    apres = gpath.read_bytes()
    _run(config, restart_from="rendu")
    assert gpath.read_bytes() == apres


def test_le_bilan_terminologique_est_redit_a_la_FIN_du_run(tome, capsys):
    """La seule trace console de la passe est écrite AVANT la première planche : sur un tome
    de 150 planches, elle a défilé depuis longtemps quand le run se termine. Deux fois la
    question « la terminologie ne s'est pas déclenchée » a été posée sur des runs où elle
    avait parfaitement tourné — le rapport le disait, la console non."""
    config, _build_dir, _ckpt, tmp_path = tome
    _run(config, restart_from="rendu")
    lignes = [l for l in capsys.readouterr().out.splitlines() if "Terminologie —" in l]
    assert lignes, "aucun bilan terminologique en fin de run"
    # `--from rendu` ne relève rien : le dire, plutôt qu'afficher « 0 planche relevée » qui
    # se lirait comme un échec.
    assert "aucune planche à relever" in lignes[-1]
    assert "glossaire" in lignes[-1] and "glossaire.yaml" in lignes[-1]


def test_le_bilan_de_fin_dit_aussi_quand_la_passe_est_DESACTIVEE(tome, capsys):
    config, _build_dir, _ckpt, _ = tome
    config["manga"]["modeles"].pop("terminologue", None)
    _run(config, restart_from="rendu")
    lignes = [l for l in capsys.readouterr().out.splitlines() if "Terminologie —" in l]
    assert lignes and "DÉSACTIVÉE" in lignes[-1]
    assert "manga.modeles.terminologue" in lignes[-1]


def test_le_rapport_dit_que_la_passe_de_terminologie_est_DESACTIVEE(tome):
    """Le défaut qui a fait croire à une panne sur le run v0.21.0 : `terminologue` commenté
    dans `manga.modeles`, et un rapport qui affiche les mêmes zéros qu'une passe en échec."""
    config, build_dir, _ckpt, _ = tome
    config["manga"]["modeles"].pop("terminologue", None)
    _run(config, restart_from="rendu")
    rapport = (build_dir / "RAPPORT.md").read_text(encoding="utf-8")
    assert "passe **DÉSACTIVÉE**" in rapport
    assert "manga.modeles.terminologue" in rapport


def test_le_rapport_explique_POURQUOI_zero_remplacement(tome):
    """« 0 remplacement » se lit comme une panne alors que c'est le plus souvent un succès :
    les `interdits` listent les fautes des runs précédents, pas celles de celui-ci."""
    config, build_dir, ckpt, _ = tome
    checkpoints.save_traduction(ckpt, ["Mitsukage arrive"])      # déjà canonique
    _run(config, restart_from="rendu")
    rapport = (build_dir / "RAPPORT.md").read_text(encoding="utf-8")
    assert "0 remplacement(s)" in rapport
    assert "aucune forme bannie n'était présente" in rapport


def test_sans_agent_terminologue_le_glossaire_nest_jamais_reecrit(tome):
    """`terminologue` absent de `manga.modeles` : la brique doit se comporter exactement
    comme avant le lot 3 — lire le glossaire, jamais l'écrire.

    ⚠ La prémisse est POSÉE ici, et non héritée du `config.yaml` livré : celui-ci peut très
    légitimement activer le terminologue (c'est même ce que le rapport recommande depuis le
    lot 2), et le test se mettait alors à mesurer le contraire de son nom."""
    config, _build_dir, ckpt, tmp_path = tome
    config["manga"]["modeles"].pop("terminologue", None)
    config["manga"]["modeles"].pop("glossariste", None)
    gpath = tmp_path / "sources" / "MonManga" / "glossaire.yaml"
    avant = gpath.read_bytes()
    assert _run(config, restart_from="terminologie") is True
    assert gpath.read_bytes() == avant
    assert checkpoints.load_terminologie(ckpt) is None


def test_avec_un_terminologue_le_glossaire_est_enrichi_et_mis_en_cache(tome, monkeypatch):
    config, build_dir, ckpt, tmp_path = tome
    config["manga"]["modeles"]["terminologue"] = "m"
    config["manga"]["temperatures"]["terminologue"] = 0.2

    appels = []

    class _Agent:
        def run(self, user, dry_payload="", max_tokens=None, temperature=None, images=None):
            appels.append(user)
            return _NOTES

    import manga.orchestrator_manga as orch
    vrai = orch.build_manga_agents
    monkeypatch.setattr(orch, "build_manga_agents",
                        lambda cfg, dry_run=False: {**vrai(cfg, dry_run=dry_run),
                                                    "terminologue": _Agent()})

    assert _run(config, restart_from="terminologie") is True
    assert len(appels) == 1
    glo = glossary.load(tmp_path / "sources" / "MonManga" / "glossaire.yaml")
    assert "Libertina" in [e["nom"] for e in glo["personnages"]]
    assert checkpoints.load_terminologie(ckpt) is not None

    # Deuxième passage : le relevé est repris du cache, aucun nouvel appel.
    assert _run(config, restart_from="terminologie") is True
    assert len(appels) == 1
    rapport = (build_dir / "RAPPORT.md").read_text(encoding="utf-8")
    assert "Terminologie :" in rapport
