# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""`RAPPORT.md` de la brique manga et son `qa.json` par page.

Point de conception vérifié ici : les pages déjà générées sont SAUTÉES par
`process_volume` et ne produisent aucune statistique fraîche. Un rapport construit sur le
seul run en cours serait donc quasi vide sur une reprise — donc mensonger. Il est bâti en
relisant les `qa.json` de TOUTES les pages, cache compris.
"""
import json

import numpy as np

from manga import checkpoints, report_manga
from manga.detection import BubbleRegion


class _Style:
    def __init__(self, mode="masque", inverted=False, uniformity=0.9, erode_radius=5,
                 bbox=(0, 0, 10, 10), ok=True):
        self.mode = mode
        self.inverted = inverted
        self.uniformity = uniformity
        self.erode_radius = erode_radius
        self.bbox = bbox
        self.ok = ok


def _region(box=(10, 10, 60, 60), score=0.9, kind="bulle"):
    return BubbleRegion(bbox=box, mask=np.zeros((100, 100), dtype=bool), score=score,
                        cls=0, kind=kind)


def _qa(page, **kw):
    base = dict(regions=[_region()], styles=[_Style()], texts_jp=["こんにちは"],
                translated=["Bonjour"], rendu_qa=[{"type": "bulle", "index": 0,
                                                   "taille": 24, "lignes": 2,
                                                   "overflow": False, "repli": ""}])
    base.update(kw)
    return report_manga.build_page_qa(page=page, nom_fichier=f"p{page:03d}.jpg", **base)


# --------------------------------------------------------------------------- #
# qa.json
# --------------------------------------------------------------------------- #

def test_qa_est_persiste_et_relu(tmp_path):
    donnees = _qa(1)
    report_manga.save_page_qa(tmp_path, donnees)
    assert (tmp_path / "qa.json").exists()
    assert report_manga.load_page_qa(tmp_path) == donnees


def test_qa_absent_renvoie_none(tmp_path):
    assert report_manga.load_page_qa(tmp_path) is None


def test_un_qa_corrompu_ne_fait_pas_echouer_le_tome(tmp_path):
    (tmp_path / "qa.json").write_text("{ ceci n'est pas du json", encoding="utf-8")
    assert report_manga.load_page_qa(tmp_path) is None


def test_qa_capture_tout_ce_que_les_etapes_ont_mesure():
    qa = _qa(7, styles=[_Style(mode="texte", inverted=True, uniformity=0.42,
                              erode_radius=0)],
             rendu_qa=[{"type": "bulle", "index": 0, "taille": 15, "lignes": 4,
                        "overflow": True, "repli": "debordement"}])
    b = qa["bulles"][0]
    assert qa["page"] == 7 and qa["fichier"] == "p007.jpg"
    assert b["mode_nettoyage"] == "texte" and b["inverse"] is True
    assert b["uniformite"] == 0.42 and b["rayon_erosion"] == 0
    assert b["taille_police"] == 15 and b["debordement"] is True
    assert b["ocr"] == "こんにちは" and b["traduction"] == "Bonjour"


def test_qa_porte_la_version():
    from core.version import __version__
    assert _qa(1)["version"] == __version__


def test_qa_conserve_les_ecarts_et_les_glyphes_manquants():
    qa = _qa(3, rendu_qa=[
        {"type": "ecart_comptage", "bulles": 3, "traductions": 1, "ecart": 2},
        {"type": "glyphes_manquants", "index": 0, "caracteres": "♪", "police": "X.ttf"}])
    assert qa["ecarts"][0]["ecart"] == 2
    assert qa["glyphes_manquants"][0]["caracteres"] == "♪"


# --------------------------------------------------------------------------- #
# Le rapport décrit le TOME, pas le run
# --------------------------------------------------------------------------- #

def _semer_tome(build_dir, n_pages=5, par_page=None):
    """Sème `n_pages` qa.json. `par_page` surcharge certaines pages, indexées par numéro."""
    par_page = par_page or {}
    for i in range(1, n_pages + 1):
        ck = checkpoints.page_checkpoint_dir(build_dir, i)
        report_manga.save_page_qa(ck, _qa(i, **par_page.get(i, {})))


def test_le_rapport_relit_TOUTES_les_pages_meme_celles_du_cache(tmp_path):
    """LE test du lot 1.7 : sur une reprise où une seule page est recalculée, le rapport
    doit décrire les 150, pas la seule qui vient de tourner."""
    _semer_tome(tmp_path, 150)
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=150, mcfg={})
    assert "Pages : 150 analysée(s) sur 150" in texte
    assert "Bulles : 150" in texte


def test_le_rapport_compte_les_pages_sans_bulle(tmp_path):
    _semer_tome(tmp_path, 4, {2: {"regions": [], "styles": [], "texts_jp": [],
                                    "translated": [], "rendu_qa": []},
                                 3: {"regions": [], "styles": [], "texts_jp": [],
                                     "translated": [], "rendu_qa": []}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=4, mcfg={})
    assert "2 sans bulle" in texte
    assert "## Pages sans aucune bulle détectée (2)" in texte
    assert "page 2" in texte and "page 3" in texte


def test_le_rapport_liste_les_debordements_avec_un_extrait(tmp_path):
    _semer_tome(tmp_path, 2, {1: {
        "translated": ["Une réplique beaucoup trop longue pour sa bulle"],
        "rendu_qa": [{"type": "bulle", "index": 0, "taille": 11, "lignes": 6,
                      "overflow": True, "repli": "debordement",
                      "cause": "texte_trop_long"}]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=2, mcfg={})
    assert "raccourcir la traduction est le bon correctif" in texte
    assert "page 1 bulle 1" in texte
    assert "Une réplique beaucoup trop longue" in texte


def test_le_rapport_SEPARE_les_trois_causes_de_debordement(tmp_path):
    """Le conseil « raccourcir la traduction » a été donné neuf fois sur le Vol.1 et n'était
    juste qu'une seule : les deux autres causes désignent la DÉTECTION."""
    _semer_tome(tmp_path, 3, {
        1: {"translated": ["Trop long"],
            "rendu_qa": [{"type": "bulle", "index": 0, "taille": 11, "lignes": 6,
                          "overflow": True, "repli": "debordement",
                          "cause": "texte_trop_long"}]},
        2: {"translated": ["Ouaouh !"],
            "rendu_qa": [{"type": "bulle", "index": 0, "taille": 11, "lignes": 2,
                          "overflow": True, "repli": "debordement",
                          "cause": "bulle_etroite"}]},
        3: {"translated": ["…"],
            "rendu_qa": [{"type": "bulle", "index": 0, "taille": 11, "lignes": 0,
                          "overflow": True, "repli": "debordement",
                          "cause": "bulle_degeneree"}]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=3, mcfg={})
    assert "Régions DÉGÉNÉRÉES, non lettrées" in texte and "page 3 bulle 1" in texte
    assert "trop ÉTROITES" in texte and "page 2 bulle 1" in texte
    assert "raccourcir la traduction est le bon correctif" in texte


def test_le_rapport_signale_les_bulles_RATTRAPEES_bulle_a_bulle(tmp_path):
    """Une bulle rattrapée a été traduite HORS du contexte de sa planche : elle mérite un œil,
    même quand elle a l'air correcte."""
    _semer_tome(tmp_path, 1, {1: {
        "texts_jp": ["煙幕を張り"],
        "translated": ["Je couvrirai de fumée."],
        "rattrapees": [0]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=1, mcfg={})
    assert "RATTRAPÉES bulle à bulle" in texte
    assert "page 1 bulle 1" in texte and "Je couvrirai de fumée." in texte


def test_le_rapport_liste_les_rattrapages_REFUSES(tmp_path):
    texte = report_manga.build_report(
        tmp_path, "P", "Vol.1", total_pages=0, mcfg={},
        stats_traduction={"pages_ok": 1, "rattrapage_appels": 2, "rattrapage_refuse": 1},
        rattrapage_refus=["page 129 bulle 10 — la réponse contient encore du japonais"])
    assert "Rattrapages REFUSÉS" in texte and "page 129 bulle 10" in texte
    assert "Rattrapage unitaire :" in texte and "2 appel(s) court(s)" in texte


def test_le_rapport_liste_les_bulles_lettrees_sous_la_taille_minimale(tmp_path):
    _semer_tome(tmp_path, 1, {1: {
        "translated": ["Zouing !"],
        "rendu_qa": [{"type": "bulle", "index": 0, "taille": 9, "lignes": 2,
                      "overflow": False, "repli": "taille_min_absolue",
                      "cause": "bulle_etroite"}]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=1, mcfg={})
    assert "SOUS la taille minimale" in texte
    assert "lettrée à 9 px" in texte and "bulle étroite" in texte


def test_le_seuil_bilobee_du_rapport_SUIT_la_config(tmp_path):
    """Le seuil était un littéral : le changer modifiait ce qui est SCINDÉ sans changer ce que
    le rapport ANNONCE — deux chiffres qui se contredisent dans le même run."""
    mcfg = {"detection": {"scission": {"seuil_suspect": 0.55}}}
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=0, mcfg=mcfg)
    assert "0.70" not in texte
    texte_defaut = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=0, mcfg={})
    assert report_manga._seuil_bilobee(mcfg) == 0.55
    assert report_manga._seuil_bilobee({}) == report_manga._SEUIL_BILOBEE
    assert texte_defaut is not None


def test_le_rapport_liste_traductions_vides_et_ocr_vides(tmp_path):
    _semer_tome(tmp_path, 3, {
        1: {"translated": [""]},
        2: {"texts_jp": [""], "translated": [""]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=3, mcfg={})
    assert "## Traductions vides (1)" in texte and "page 1 bulle 1" in texte
    assert "## Bulles sans texte OCR (1)" in texte and "page 2 bulle 1" in texte


def test_le_rapport_liste_les_detections_faibles(tmp_path):
    _semer_tome(tmp_path, 2, {1: {"regions": [_region(score=0.31)]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=2,
                                      mcfg={"rapport": {"seuil_confiance": 0.5}})
    assert "faible confiance" in texte and "score 0.31" in texte


def test_le_rapport_liste_les_bulles_abandonnees_et_les_replis(tmp_path):
    _semer_tome(tmp_path, 3, {
        1: {"styles": [_Style(mode="aucun", uniformity=0.13)]},
        2: {"styles": [_Style(erode_radius=0)]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=3, mcfg={})
    assert "## Bulles NON nettoyées" in texte and "uniformité 0.13" in texte
    assert "mode repli" in texte and "page 2 bulle 1" in texte


def test_le_rapport_liste_les_ecarts_de_comptage(tmp_path):
    _semer_tome(tmp_path, 2, {1: {"rendu_qa": [
        {"type": "ecart_comptage", "bulles": 5, "traductions": 3, "ecart": 2}]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=2, mcfg={})
    assert "## Écarts de comptage bulles / traductions (1)" in texte
    assert "5 bulle(s) pour 3 traduction(s)" in texte


def test_les_sections_sont_tronquees_avec_le_compte_du_reste(tmp_path):
    """Comme côté LN : une liste de 300 entrées noyait le rapport."""
    _semer_tome(tmp_path, 60, {i: {"translated": [""]} for i in range(1, 61)})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=60,
                                      mcfg={"rapport": {"max_lignes_section": 10}})
    assert "## Traductions vides (60)" in texte
    assert "- (… 50 autre(s))" in texte


def test_le_resume_donne_les_modes_de_nettoyage_et_la_taille_mediane(tmp_path):
    _semer_tome(tmp_path, 3, {
        1: {"styles": [_Style(mode="texte")]},
        2: {"styles": [_Style(mode="aucun")], "rendu_qa": []}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=3, mcfg={})
    assert "1 en mode masque · 1 en mode texte · 1 abandonnée(s)" in texte
    assert "taille de police médiane" in texte


def test_le_resume_agrege_les_motifs_d_echec_de_traduction(tmp_path):
    _semer_tome(tmp_path, 2)
    stats = {"pages_ok": 8, "bulles_manquantes": 2, "vide": 1,
             "recupere_par_retry": 3, "retry_temp_reduite": 4}
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=2, mcfg={},
                                      stats_traduction=stats)
    assert "8 page(s) ok" in texte
    assert "3 récupérée(s) après retry" in texte
    assert "numérotation incomplète" in texte and "réponse vide" in texte
    assert "4 retry(s) tenté(s)" in texte


def test_le_resume_signale_un_dry_run(tmp_path):
    _semer_tome(tmp_path, 1)
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=1, mcfg={})
    assert "dry-run" in texte


def test_le_resume_donne_les_stats_llm(tmp_path):
    _semer_tome(tmp_path, 1)
    texte = report_manga.build_report(
        tmp_path, "P", "Vol.1", total_pages=1, mcfg={},
        stats_llm={"appels": 12, "tokens_generes": 2400, "temps_generation": 120.0,
                   "thinking_overflow": 2, "troncature_length": 1})
    assert "Appels LLM : 12" in texte and "~2400" in texte and "~20 tok/s" in texte
    assert "2 dépassement(s) de budget" in texte and "1 génération(s) coupée(s)" in texte


def test_write_report_ecrit_le_fichier(tmp_path):
    _semer_tome(tmp_path, 2)
    chemin = report_manga.write_report(tmp_path, "P", "Vol.1", total_pages=2, mcfg={})
    assert chemin.name == "RAPPORT.md"
    assert "Rapport manga — P / Vol.1" in chemin.read_text(encoding="utf-8")


def test_un_rapport_sans_aucun_qa_reste_lisible(tmp_path):
    """Aucun `qa.json` (premier run interrompu très tôt) : le rapport doit le dire, pas
    planter."""
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=150, mcfg={})
    assert "Pages : 0 analysée(s) sur 150" in texte


def test_les_sections_vides_sont_absentes(tmp_path):
    _semer_tome(tmp_path, 2)
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=2, mcfg={})
    assert "## Traductions vides" not in texte
    assert "## Bulles en débordement" not in texte


def test_les_regions_non_bulle_ne_sont_pas_comptees(tmp_path):
    """Onomatopées (phase 2) : présentes dans qa.json pour l'alignement, hors des compteurs."""
    _semer_tome(tmp_path, 1, {1: {
        "regions": [_region(kind="onomatopee")], "styles": [_Style(ok=False)],
        "texts_jp": [""], "translated": [""], "rendu_qa": []}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=1, mcfg={})
    assert "Bulles : 0" in texte
    assert "## Bulles sans texte OCR" not in texte


def test_le_rapport_signale_une_REPLIQUE_NON_DESSINEE_avec_son_texte(tmp_path):
    """Le seul incident du rendu où du TEXTE DISPARAÎT de la planche.

    Un débordement laisse des lettres rognées, qui se voient ; une bulle blanche se lit
    comme un silence voulu et ne se voit pas. Mesuré sur le Vol.1 de manga A après un
    changement de police : deux répliques (« J'aimerais bien tirer. », « Katch ») ont
    disparu sans qu'aucune ligne du rapport ne dise LAQUELLE."""
    _semer_tome(tmp_path, 1, {
        1: {"translated": ["J'aimerais bien tirer."],
            "rendu_qa": [{"type": "replique_non_dessinee", "index": 0,
                          "cause": "bulle_degeneree",
                          "texte": "J'aimerais bien tirer."}]}})
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=1, mcfg={})
    assert "RÉPLIQUES NON DESSINÉES" in texte
    assert "page 1 bulle 1" in texte
    assert "J'aimerais bien tirer." in texte


def test_un_qa_json_dancien_format_ne_casse_pas_le_rapport(tmp_path):
    """Les pages reprises du cache portent un `qa.json` écrit AVANT ce lot, sans le champ
    `non_dessinees`. Le rapport doit se construire et ne rien compter, plutôt qu'inventer
    ou lever."""
    _semer_tome(tmp_path, 1, {1: {"translated": ["Bonjour"], "rendu_qa": []}})
    chemin = checkpoints.page_checkpoint_dir(tmp_path, 1) / "qa.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    donnees.pop("non_dessinees", None)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    texte = report_manga.build_report(tmp_path, "P", "Vol.1", total_pages=1, mcfg={})
    assert "RÉPLIQUES NON DESSINÉES" not in texte
