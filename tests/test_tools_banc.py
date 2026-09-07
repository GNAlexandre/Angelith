# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Le banc de mesure (`tools/banc.py`) — sans modèle, sans LLM, dans la boucle courte.

Un faux `build/` de trois planches est fabriqué en `tmp_path`, dont **une à zéro région** et
**une sans `qa.json`**. Ces deux-là ne sont pas décoratives : elles sont les deux pièges que le
lot 10 nomme, et un banc qui les confond redit exactement ce que `RAPPORT.md` disait de
travers.

⚠ Aucun marqueur : ces tests doivent tourner dans `pytest -m "not lent and not llm"`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from tools import _banc_commun as commun          # noqa: E402
from tools import banc                            # noqa: E402

SEUILS = {"seuil_confiance": 0.50, "seuil_bilobee": 0.70, "seuil_abandon": 0.35}


def _ecrire_planche(build_dir: Path, numero: int, regions: list[dict],
                    *, taille=(1200, 1800), qa: dict | None = None,
                    ocr: list[str] | None = None, sens: str = "droite_gauche",
                    rendu: Image.Image | None = None) -> Path:
    """Une planche de cache, écrite à la main au format que le pipeline produit.

    On n'appelle pas `checkpoints.save_regions` : le banc doit savoir lire un cache tel qu'il
    est sur disque, y compris celui d'une version antérieure. Le fabriquer avec l'écrivain du
    jour ne testerait que leur accord mutuel."""
    ckpt = build_dir / ".checkpoints" / f"page_{numero:04d}"
    ckpt.mkdir(parents=True, exist_ok=True)
    (ckpt / "regions.json").write_text(json.dumps(
        {"format": 3, "image_size": list(taille), "sens": sens, "regions": regions},
        ensure_ascii=False), encoding="utf-8")
    label = np.zeros((taille[1], taille[0]), dtype=np.uint8)
    for i, r in enumerate(regions, start=1):
        x0, y0, x1, y1 = r["bbox"]
        label[y0:y1, x0:x1] = i
    Image.fromarray(label, mode="L").save(ckpt / "masks.png")
    if qa is not None:
        (ckpt / "qa.json").write_text(json.dumps(qa, ensure_ascii=False), encoding="utf-8")
    if ocr is not None:
        (ckpt / "ocr.json").write_text(json.dumps(ocr, ensure_ascii=False), encoding="utf-8")
    if rendu is not None:
        sortie = build_dir / "pages_out"
        sortie.mkdir(parents=True, exist_ok=True)
        rendu.save(sortie / f"page_{numero:04d}.png")
    return ckpt


def _bulle(x0, y0, x1, y1, score=0.95, **extra) -> dict:
    return {"bbox": [x0, y0, x1, y1], "score": score, "cls": 0, "kind": "bulle",
            "scindee": False, **extra}


def _qa_bulle(index, **champs) -> dict:
    base = {"index": index, "kind": "bulle", "score": 0.95, "ocr": "こんにちは",
            "traduction": "Bonjour", "mode_nettoyage": "masque", "uniformite": 0.9,
            "remplissage_masque": 0.89, "scindee": False, "forme": "",
            "debordement": False, "cause": "", "rattrapee": False, "origine": "pipeline"}
    return {**base, **champs}


@pytest.fixture()
def faux_build(tmp_path: Path) -> Path:
    """`build/Corpus/Vol.1/manga` — trois planches, et chacune porte un cas.

    · page 1 : deux bulles saines, dont une sous le seuil de confiance ;
    · page 2 : ZÉRO région, et un rendu qui porte de l'encre (page d'action, pas page vide) ;
    · page 3 : une bulle, et PAS de `qa.json` — la planche que `RAPPORT.md` soustrayait."""
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    _ecrire_planche(
        build_dir, 1,
        [_bulle(100, 100, 400, 300), _bulle(700, 100, 760, 140, score=0.31)],
        ocr=["こんにちは", "まって"],
        qa={"page": 1, "fichier": "p1.png", "strategie_traduction": "numerotee",
            "motif_traduction": None, "restaurees": [],
            "bulles": [_qa_bulle(0), _qa_bulle(1)]})
    encre = Image.new("RGB", (1200, 1800), "white")
    encre.paste(Image.new("RGB", (900, 900), "black"), (100, 100))
    _ecrire_planche(build_dir, 2, [], ocr=[], rendu=encre,
                    qa={"page": 2, "fichier": "p2.png", "bulles": [], "restaurees": [],
                        "sfx": [], "strategie_traduction": ""})
    _ecrire_planche(build_dir, 3, [_bulle(200, 200, 500, 500)], ocr=["そうか"])
    return tmp_path / "build"


def _mesure(build_root: Path) -> dict:
    volumes = commun.enumerer_volumes(build_root)
    assert len(volumes) == 1, f"faux build mal formé : {[v.nom for v in volumes]}"
    return banc.mesurer_volume(volumes[0], **SEUILS)


# --- énumération et lecture -------------------------------------------------

def test_enumerer_volumes_ne_retient_que_ce_qui_a_un_cache(tmp_path: Path):
    (tmp_path / "Corpus" / "Vol.1" / "manga" / ".checkpoints").mkdir(parents=True)
    (tmp_path / "Corpus" / "Vol.2" / "manga").mkdir(parents=True)   # jamais lancé
    assert [v.tome for v in commun.enumerer_volumes(tmp_path)] == ["Vol.1"]


def test_les_chapitres_sont_en_ordre_de_lecture_et_non_alphabetique(tmp_path: Path):
    """`Chap.10` après `Chap.2` : le tri alphabétique donne l'inverse, et le tableau publié
    listerait alors les volumes dans un ordre que personne ne reconnaît."""
    for nom in ("Chap.1", "Chap.2", "Chap.10"):
        (tmp_path / "Corpus" / nom / "manga" / ".checkpoints").mkdir(parents=True)
    assert [v.tome for v in commun.enumerer_volumes(tmp_path)] == ["Chap.1", "Chap.2",
                                                                   "Chap.10"]


def test_un_regions_json_illisible_ne_fait_pas_echouer_le_banc(tmp_path: Path):
    ckpt = tmp_path / ".checkpoints" / "page_0001"
    ckpt.mkdir(parents=True)
    (ckpt / "regions.json").write_text("{ceci n'est pas du JSON", encoding="utf-8")
    planche = commun.lire_planche(ckpt, 1)
    assert planche.regions == []
    assert planche.a_des_regions is False       # ≠ « planche à zéro bulle »


def test_le_format_v1_liste_nue_reste_lisible(tmp_path: Path):
    """Un tome d'AVANT la migration doit se mesurer aussi : c'est même le seul moment où la
    comparaison avant/après a un sens."""
    ckpt = tmp_path / ".checkpoints" / "page_0001"
    ckpt.mkdir(parents=True)
    (ckpt / "regions.json").write_text(
        json.dumps([{"bbox": [0, 0, 10, 10], "score": 0.9, "cls": 0}]), encoding="utf-8")
    planche = commun.lire_planche(ckpt, 1)
    assert planche.format_cache == 1 and len(planche.bulles) == 1


def test_les_planches_sont_numerotees_dans_l_ordre_numerique(tmp_path: Path):
    for n in (1, 2, 10, 100):
        (tmp_path / ".checkpoints" / f"page_{n}").mkdir(parents=True)
    assert commun.numeros_de_planches(tmp_path) == [1, 2, 10, 100]


# --- les colonnes, une par une ----------------------------------------------

def test_les_bulles_se_comptent_depuis_regions_json_pas_depuis_qa(faux_build: Path):
    """LE piège du lot : `RAPPORT.md` annonce 813 bulles pour 821 en cache, parce qu'il compte
    dans `qa.json` et qu'une planche — la page 8, avec ses 8 bulles — n'en a pas. Ici, la
    page 3 n'a pas de `qa.json` : sa bulle doit quand même compter, et la planche doit être
    signalée dans une colonne où un 1 reste un 1."""
    m = _mesure(faux_build)
    assert m["bulles"] == 3          # 2 + 0 + 1, et non 2
    assert m["sans qa"] == 1


def test_planches_a_zero_bulle_et_leur_tri_par_l_encre(faux_build: Path):
    """La page 2 n'a aucune région mais son rendu est à moitié noir : c'est une planche
    d'action non traduite, pas une page de garde. `qa["sfx"]` la déclarerait vide — la passe
    onomatopées n'a pas tourné."""
    m = _mesure(faux_build)
    assert m["0 bulle"] == 1
    assert m["dont encrées"] == 1
    assert m["source encre"] == ["pages_out"]


def test_une_page_de_garde_blanche_n_est_pas_comptee_encree(tmp_path: Path):
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    _ecrire_planche(build_dir, 1, [], rendu=Image.new("RGB", (1200, 1800), "white"),
                    qa={"page": 1, "bulles": [], "restaurees": [], "sfx": []})
    m = _mesure(tmp_path / "build")
    assert (m["0 bulle"], m["dont encrées"]) == (1, 0)


def test_le_test_d_encre_se_rabat_sur_qa_sfx_sans_image(tmp_path: Path):
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    _ecrire_planche(build_dir, 1, [],
                    qa={"page": 1, "bulles": [], "restaurees": [],
                        "sfx": [{"index": 0, "bbox": [0, 0, 10, 10], "source": "ゴォ"}]})
    m = _mesure(tmp_path / "build")
    assert (m["dont encrées"], m["source encre"]) == (1, ["qa[sfx]"])


def test_detections_sous_le_seuil_de_confiance(faux_build: Path):
    assert _mesure(faux_build)["score faible"] == 1


def test_mediane_et_maximum_de_bulles_par_planche(faux_build: Path):
    m = _mesure(faux_build)
    assert m["max b/pl"] == 2
    assert m["médiane b/pl"] == 1        # planches à 2, 0 et 1 bulle


def test_taille_de_planche_et_ratio(faux_build: Path):
    m = _mesure(faux_build)
    assert m["taille planche"] == ["1200×1800"]
    assert m["ratio max"] == 1.5
    assert m["régime"] == "manga"


def test_une_bande_tres_allongee_est_classee_webtoon(tmp_path: Path):
    build_dir = tmp_path / "build" / "Corpus" / "Chap.1" / "manga"
    _ecrire_planche(build_dir, 1, [_bulle(10, 10, 100, 100)], taille=(1080, 10000),
                    sens="gauche_droite", ocr=["Hello"],
                    qa={"page": 1, "restaurees": [], "strategie_traduction": "numerotee",
                        "bulles": [_qa_bulle(0, ocr="Hello", traduction="Salut")]})
    m = _mesure(tmp_path / "build")
    assert m["régime"] == "webtoon"
    assert m["langue"] == "latin"        # la colonne qui évite de confondre format et OCR


def test_la_langue_source_est_inferee_de_l_ocr(faux_build: Path):
    assert _mesure(faux_build)["langue"] == "cjk"


def test_zones_restaurees_bulles_sans_ocr_et_non_nettoyees(tmp_path: Path):
    """Les TROIS indicateurs de fausse détection, qui ne mesurent pas la même chose. Un lot
    qui gagne des bulles sans republier les trois peut dégrader le résultat en affichant un
    succès."""
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    _ecrire_planche(
        build_dir, 1,
        [_bulle(0, 0, 100, 100), _bulle(200, 0, 300, 100), _bulle(400, 0, 500, 100)],
        qa={"page": 1, "restaurees": [{"index": 0}], "strategie_traduction": "numerotee",
            "bulles": [_qa_bulle(0, ocr="", traduction=""),
                       _qa_bulle(1, mode_nettoyage="aucun", uniformite=0.2),
                       _qa_bulle(2, debordement=True, cause="bulle_degeneree")]})
    m = _mesure(tmp_path / "build")
    assert m["restaurées"] == 1
    assert m["sans OCR"] == 1
    assert m["non nettoyées"] == 1
    assert m["dégénérées"] == 1


def test_bilobees_scindees_et_suspectes_non_scindees(tmp_path: Path):
    """Une région au remplissage bas n'est PAS forcément un double : `forme: dentelee` désigne
    un ballon de cri, dont c'est la forme normale. Les confondre est ce qui rangeait 45 bulles
    saines sous « bi-lobées suspectes »."""
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    _ecrire_planche(
        build_dir, 1,
        [_bulle(0, 0, 100, 100, scindee=True), _bulle(200, 0, 300, 100),
         _bulle(400, 0, 500, 100)],
        qa={"page": 1, "restaurees": [], "strategie_traduction": "numerotee",
            "bulles": [_qa_bulle(0, scindee=True, remplissage_masque=0.62),
                       _qa_bulle(1, remplissage_masque=0.60, forme="suspecte"),
                       _qa_bulle(2, remplissage_masque=0.55, forme="dentelee")]})
    m = _mesure(tmp_path / "build")
    assert m["scindées"] == 1
    assert m["suspectes"] == 1        # la dentelée n'en est pas


def test_motifs_residuels_et_strategies_sont_ventiles(tmp_path: Path):
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    for numero, motif, strategie in ((1, "repetition", "numerotee"),
                                     (2, "repetition", "positionnelle"),
                                     (3, None, "numerotee")):
        _ecrire_planche(build_dir, numero, [_bulle(0, 0, 100, 100)],
                        qa={"page": numero, "restaurees": [], "motif_traduction": motif,
                            "strategie_traduction": strategie,
                            "bulles": [_qa_bulle(0)]})
    m = _mesure(tmp_path / "build")
    assert m["motifs résiduels"] == {"repetition": 2}
    assert m["stratégies"] == {"numerotee": 2, "positionnelle": 1}


# --- le banc de traduction (L8.3) -------------------------------------------

def test_bulles_vides_a_l_arrivee_et_rattrapees(tmp_path: Path):
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    _ecrire_planche(
        build_dir, 1, [_bulle(0, 0, 100, 100), _bulle(200, 0, 300, 100)],
        qa={"page": 1, "restaurees": [], "strategie_traduction": "numerotee_partielle",
            "bulles": [_qa_bulle(0, traduction=""), _qa_bulle(1, rattrapee=True)]})
    m = _mesure(tmp_path / "build")
    assert m["vides à l'arrivée"] == 1     # source non vide, rendu vide
    assert m["sans OCR"] == 0              # ≠ bulle sans texte source
    assert m["rattrapées"] == 1


def test_la_longueur_rendue_sur_source_est_une_mediane(tmp_path: Path):
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    _ecrire_planche(
        build_dir, 1, [_bulle(0, 0, 100, 100)],
        qa={"page": 1, "restaurees": [], "strategie_traduction": "numerotee",
            "bulles": [_qa_bulle(0, ocr="あい", traduction="Bonjour")]})
    assert _mesure(tmp_path / "build")["longueur rendue/source"] == 3.5


def test_les_origines_distinguent_pipeline_editeur_et_manuelle(tmp_path: Path):
    build_dir = tmp_path / "build" / "Corpus" / "Vol.1" / "manga"
    _ecrire_planche(
        build_dir, 1, [_bulle(0, 0, 100, 100), _bulle(200, 0, 300, 100)],
        qa={"page": 1, "restaurees": [], "strategie_traduction": "numerotee",
            "bulles": [_qa_bulle(0), _qa_bulle(1, origine="manuelle")]})
    assert _mesure(tmp_path / "build")["origines"] == {"pipeline": 1, "manuelle": 1}


# --- la sortie --------------------------------------------------------------

def test_le_tableau_markdown_a_toutes_ses_colonnes(faux_build: Path):
    ligne = _mesure(faux_build)
    rendu = commun.tableau_markdown(banc.COLONNES_DETECTION, [ligne])
    entete, separateur, corps = rendu.splitlines()
    assert entete.count("|") == separateur.count("|") == corps.count("|")
    assert "volume" in entete and "Corpus / Vol.1" in corps


def test_une_case_vide_s_ecrit_tiret_et_jamais_zero():
    """Dans une colonne de nombres, une case vide se lit comme un zéro. Une mesure absente
    n'est pas une mesure nulle — c'est toute la différence entre « aucune fausse détection »
    et « pas mesuré »."""
    assert commun.cellule(None) == "—"
    assert commun.cellule(0) == "0"


def test_l_entete_de_publication_porte_date_commit_et_config(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text("manga: {}\n", encoding="utf-8")
    lignes = "\n".join(commun.entete_publication(
        config, [commun.Volume("Corpus", "Vol.1", tmp_path)]))
    assert "Date de mesure" in lignes and "Commit" in lignes
    assert "sha256" in lignes and "Corpus / Vol.1" in lignes


def test_deux_configs_differentes_ont_deux_empreintes(tmp_path: Path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text("seuil: 0.35\n", encoding="utf-8")
    b.write_text("seuil: 0.45\n", encoding="utf-8")
    assert commun.empreinte_config(a) != commun.empreinte_config(b)
    assert commun.empreinte_config(tmp_path / "absente.yaml") == "(absente)"


def test_le_total_ne_somme_que_ce_qui_se_somme(faux_build: Path):
    """Une médiane de médianes ne veut rien dire. L'afficher quand même serait exactement le
    chiffre sans dénominateur que ce lot fait disparaître."""
    ligne = _mesure(faux_build)
    total = banc._totaux([ligne, ligne], banc.COLONNES_DETECTION)
    assert total["bulles"] == 6
    assert total["médiane b/pl"] is None


def test_la_ligne_de_commande_rend_un_tableau(faux_build: Path, capsys, monkeypatch):
    """Le critère d'acceptation du lot, en un test : une commande, tous les volumes, un
    tableau — sans charger de modèle."""
    monkeypatch.setattr(sys, "argv",
                        ["banc.py", "--tous", "--build", str(faux_build), "--markdown"])
    assert banc.main() == 0
    sortie = capsys.readouterr().out
    assert "# Banc de détection" in sortie
    assert "Corpus / Vol.1" in sortie
    assert "**TOTAL (1 volume(s))**" in sortie


def test_la_sortie_json_est_relisible(faux_build: Path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["banc.py", "--tous", "--build", str(faux_build),
                                      "--json"])
    assert banc.main() == 0
    charge = json.loads(capsys.readouterr().out)
    assert charge["volumes"][0]["bulles"] == 3
    assert charge["entete"]["volumes"] == ["Corpus / Vol.1"]


def test_un_build_vide_echoue_franchement(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["banc.py", "--tous", "--build", str(tmp_path)])
    assert banc.main() == 1
    assert "Aucun cache" in capsys.readouterr().out
