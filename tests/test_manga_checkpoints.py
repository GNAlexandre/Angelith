# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Points de reprise par étage : sauvegarde/rechargement fidèle des régions
(bbox+masque), de l'OCR et de la traduction ; calcul du point de reprise. Aucune
dépendance aux modèles CV/OCR (numpy + PIL uniquement)."""
import json

import numpy as np

from manga import bubbles_split, checkpoints
from manga.detection import BubbleRegion


def _scinder(regions):
    """La scission bi-lobée telle que l'orchestrateur l'injecte dans `migrate_page`. Injectée
    et non importée par `checkpoints`, pour que le module de cache ne dépende ni de
    `manga.ocr` ni de `manga.bubbles_split`."""
    return bubbles_split.scinder_regions(regions)


def _region(box, canvas=(100, 100), score=0.9, cls=0, kind="bulle"):
    x0, y0, x1, y1 = box
    mask = np.zeros((canvas[1], canvas[0]), dtype=bool)
    mask[y0:y1, x0:x1] = True
    return BubbleRegion(bbox=box, mask=mask, score=score, cls=cls, kind=kind)


def test_save_and_load_regions_roundtrip(tmp_path):
    regions = [_region((10, 10, 40, 40), score=0.91), _region((60, 60, 90, 90), score=0.82)]
    checkpoints.save_regions(tmp_path, regions, (100, 100))

    loaded = checkpoints.load_regions(tmp_path)
    assert loaded is not None
    assert len(loaded) == 2
    for orig, got in zip(regions, loaded):
        assert got.bbox == orig.bbox
        assert abs(got.score - orig.score) < 1e-6
        assert got.cls == orig.cls
        assert got.kind == orig.kind
        assert np.array_equal(got.mask, orig.mask)


def test_load_regions_returns_none_if_absent(tmp_path):
    assert checkpoints.load_regions(tmp_path) is None


def test_save_and_load_ocr_and_traduction_roundtrip(tmp_path):
    checkpoints.save_ocr(tmp_path, ["こんにちは", "さようなら"])
    checkpoints.save_traduction(tmp_path, ["Bonjour", "Au revoir"])

    assert checkpoints.load_ocr(tmp_path) == ["こんにちは", "さようなら"]
    assert checkpoints.load_traduction(tmp_path) == ["Bonjour", "Au revoir"]


def test_load_traduction_repare_un_cache_A_PREFIXE_NUMEROTE(tmp_path):
    """Les caches déjà produits portent le défaut : la page 129 du Vol.1 du *manga A* a
    9 répliques persistées sous la forme « 1. L'ennemi semble être… », et le lettrage les
    dessinait telles quelles. Réparer à la LECTURE évite de retraduire chaque planche
    touchée — un `--from rendu` suffit, sans un seul appel LLM."""
    checkpoints.save_traduction(tmp_path, ["1. L'ennemi arrive", "2. Vraiment ?", ""])
    assert checkpoints.load_traduction(tmp_path) == ["L'ennemi arrive", "Vraiment ?", ""]


def test_load_traduction_ne_touche_PAS_a_un_millesime(tmp_path):
    """Page 8 du même tome : la bulle de récitatif « 1972... ». Un nombre trop grand pour
    être un index de bulle est du texte, pas une numérotation."""
    checkpoints.save_traduction(tmp_path, ["1972...", "1972. Une année terrible"])
    assert checkpoints.load_traduction(tmp_path) == ["1972...", "1972. Une année terrible"]


def test_load_traduction_absente_reste_none(tmp_path):
    assert checkpoints.load_traduction(tmp_path) is None


def test_invalider_textes_jette_ocr_traduction_et_qa_mais_PAS_la_terminologie(tmp_path):
    """À appeler dès qu'une opération change le NOMBRE de régions : l'alignement par position
    est alors irrécupérable, et `stage_cache_present` teste la présence d'un fichier, pas sa
    longueur — la page garderait sinon un OCR de l'ancien découpage, silencieusement décalé.

    `terminologie.txt` est épargné : cache non bloquant, du texte libre aligné sur rien. C'est
    ce qui garde le coût d'une relance de détection à UN appel LLM au lieu de deux."""
    checkpoints.save_ocr(tmp_path, ["あ"])
    checkpoints.save_traduction(tmp_path, ["A"])
    (tmp_path / checkpoints.QA_FILENAME).write_text("{}", encoding="utf-8")
    checkpoints.save_terminologie(tmp_path, "- Libertina | genre: féminin")

    supprimes = checkpoints.invalider_textes(tmp_path)
    assert set(supprimes) == {checkpoints.OCR_FILENAME, checkpoints.TRADUCTION_FILENAME,
                              checkpoints.QA_FILENAME}
    assert checkpoints.load_ocr(tmp_path) is None
    assert checkpoints.load_traduction(tmp_path) is None
    assert checkpoints.load_terminologie(tmp_path) is not None


def test_invalider_textes_est_idempotent(tmp_path):
    assert checkpoints.invalider_textes(tmp_path) == []


# --------------------------------------------------------------------------- #
# Provenance de la détection — sans toucher à FORMAT_VERSION
# --------------------------------------------------------------------------- #

def test_la_provenance_de_detection_est_persistee_et_relue(tmp_path):
    region = BubbleRegion(bbox=(0, 0, 4, 4), mask=np.ones((8, 8), dtype=bool), score=0.9, cls=0)
    checkpoints.save_regions(tmp_path, [region], (8, 8),
                             detection={"conf_threshold": 0.45, "iou_threshold": 0.3,
                                        "motif": "1 faux positif écarté"})
    meta = checkpoints.load_detection_meta(tmp_path)
    assert meta["conf_threshold"] == 0.45 and meta["motif"] == "1 faux positif écarté"


def test_la_provenance_NINVALIDE_PAS_le_cache(tmp_path):
    """⚠ LE test qui protège 150 planches. `load_regions` renvoie `None` sur écart de version,
    ce qui déclencherait `downstream("detection")` — soit la retraduction du tome entier. Un
    champ de PROVENANCE n'est pas un changement de contrat de nombre et d'ordre."""
    region = BubbleRegion(bbox=(0, 0, 4, 4), mask=np.ones((8, 8), dtype=bool), score=0.9, cls=0)
    checkpoints.save_regions(tmp_path, [region], (8, 8),
                             detection={"conf_threshold": 0.25})
    assert checkpoints.checkpoint_format(tmp_path) == checkpoints.FORMAT_VERSION
    relues = checkpoints.load_regions(tmp_path)
    assert relues is not None and len(relues) == 1


def test_sans_provenance_le_json_nen_porte_aucune_trace(tmp_path):
    """Le champ est OPTIONNEL : la quasi-totalité des pages n'a jamais été relancée."""
    region = BubbleRegion(bbox=(0, 0, 4, 4), mask=np.ones((8, 8), dtype=bool), score=0.9, cls=0)
    checkpoints.save_regions(tmp_path, [region], (8, 8))
    assert checkpoints.load_detection_meta(tmp_path) == {}
    assert "detection" not in (tmp_path / "regions.json").read_text(encoding="utf-8")


def test_stage_index_matches_declared_order():
    assert checkpoints.STAGES == ["detection", "nettoyage", "ocr", "terminologie",
                                  "traduction", "sfx", "rendu"]
    assert checkpoints.stage_index("detection") == 0
    assert checkpoints.stage_index("rendu") == len(checkpoints.STAGES) - 1


# --------------------------------------------------------------------------- #
# Graphe de dépendances des étapes
#
#     detection ──┬── nettoyage ──────────┐
#                 └── ocr ── traduction ──┴── rendu
#
# L'ordre d'exécution (`STAGES`) n'est PAS un ordre de dépendance : `ocr` lit l'image
# d'origine et les régions, jamais la page nettoyée. Traiter la liste comme une chaîne
# faisait payer ~38 min d'OCR et de traduction (appels LLM compris) à chaque
# `--from nettoyage`, pour un résultat identique au bit près.
# --------------------------------------------------------------------------- #

def test_downstream_de_nettoyage_epargne_ocr_et_traduction():
    assert checkpoints.downstream("nettoyage") == {"nettoyage", "rendu"}


def test_downstream_de_detection_couvre_tout():
    assert checkpoints.downstream("detection") == set(checkpoints.STAGES)


def test_downstream_de_ocr_entraine_la_traduction_mais_pas_le_nettoyage():
    assert checkpoints.downstream("ocr") == {"ocr", "terminologie", "traduction", "rendu"}


def test_downstream_de_terminologie_entraine_la_traduction():
    """La terminologie enrichit le glossaire, que le traducteur reçoit en contexte : la
    refaire peut changer une traduction. Elle ne touche pas au nettoyage."""
    assert checkpoints.downstream("terminologie") == {"terminologie", "traduction", "rendu"}


def test_downstream_de_traduction_et_de_rendu():
    assert checkpoints.downstream("traduction") == {"traduction", "rendu"}
    assert checkpoints.downstream("rendu") == {"rendu"}


def test_downstream_refuse_une_etape_inconnue():
    import pytest
    with pytest.raises(KeyError):
        checkpoints.downstream("nettoyge")


def test_downstream_est_clos_par_transitivite():
    """Toute étape citée dans le résultat doit y amener ses propres dépendants."""
    for etape in checkpoints.STAGES:
        ferme = checkpoints.downstream(etape)
        for s in ferme:
            assert checkpoints.downstream(s) <= ferme, (etape, s)


def _semer_caches(tmp_path, *, regions=True, clean=True, ocr=True, trad=True):
    clean_path = tmp_path / "page_0001.png"
    if regions:
        checkpoints.save_regions(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    if clean:
        from PIL import Image
        Image.new("RGB", (10, 10)).save(clean_path)
    if ocr:
        checkpoints.save_ocr(tmp_path, ["あ"])
    if trad:
        checkpoints.save_traduction(tmp_path, ["a"])
    return clean_path


def test_stage_cache_present_voit_chaque_etape_independamment(tmp_path):
    """Contrairement à `first_missing_stage`, qui s'arrête à la PREMIÈRE absence et ne peut
    donc pas dire qu'une étape ultérieure est, elle, en cache."""
    clean_path = _semer_caches(tmp_path, clean=False)
    present = checkpoints.stage_cache_present(tmp_path, clean_path)
    assert present["detection"] is True
    assert present["nettoyage"] is False
    assert present["ocr"] is True          # first_missing_stage se serait arrêté avant
    assert present["traduction"] is True


def test_stages_to_redo_from_nettoyage_tout_en_cache(tmp_path):
    clean_path = _semer_caches(tmp_path)
    assert checkpoints.stages_to_redo(tmp_path, clean_path,
                                      restart_from="nettoyage") == {"nettoyage", "rendu"}


def test_stages_to_redo_from_rendu_ne_refait_que_le_rendu(tmp_path):
    clean_path = _semer_caches(tmp_path)
    assert checkpoints.stages_to_redo(tmp_path, clean_path,
                                      restart_from="rendu") == {"rendu"}


def test_stages_to_redo_sans_from_et_tout_en_cache(tmp_path):
    """Le rendu n'a pas de cache propre : il est toujours refait."""
    clean_path = _semer_caches(tmp_path)
    assert checkpoints.stages_to_redo(tmp_path, clean_path) == {"rendu"}


def test_stages_to_redo_force_tout(tmp_path):
    clean_path = _semer_caches(tmp_path)
    assert checkpoints.stages_to_redo(tmp_path, clean_path,
                                      force=True) == set(checkpoints.STAGES)


def test_stages_to_redo_propage_un_cache_de_detection_absent(tmp_path):
    """Sans régions, tout est à refaire : les masques changeront, donc le nettoyage et
    l'OCR ne sont plus valides MÊME si leurs fichiers existent."""
    clean_path = _semer_caches(tmp_path, regions=False)
    assert checkpoints.stages_to_redo(tmp_path, clean_path) == set(checkpoints.STAGES)


def test_stages_to_redo_un_ocr_absent_n_entraine_pas_le_nettoyage(tmp_path):
    clean_path = _semer_caches(tmp_path, ocr=False)
    assert checkpoints.stages_to_redo(tmp_path, clean_path) == {
        "ocr", "terminologie", "traduction", "rendu"}


def test_un_cache_de_terminologie_absent_ne_perime_RIEN(tmp_path):
    """LE piège du lot 3, et il aurait été coûteux : `terminologie.txt` n'existe sur AUCUNE
    page d'un tome traduit avant ce lot. Si son absence périmait la traduction comme celle
    de l'OCR, un simple `--from nettoyage` aurait déclenché la retraduction des 150 planches,
    appels LLM compris — et activer l'agent `terminologue` aurait fait pire encore.

    L'étape écrit dans le glossaire de l'ŒUVRE, pas dans le cache de la page ; son fichier ne
    sert qu'à ne pas repayer l'appel. Pour la (re)lancer, c'est `--from terminologie`."""
    clean_path = _semer_caches(tmp_path)                 # tout en cache SAUF terminologie
    assert checkpoints.load_terminologie(tmp_path) is None
    assert checkpoints.stages_to_redo(tmp_path, clean_path) == {"rendu"}
    assert checkpoints.stages_to_redo(tmp_path, clean_path,
                                      restart_from="nettoyage") == {"nettoyage", "rendu"}
    # …mais demandée explicitement, elle entraîne bien la traduction.
    assert checkpoints.stages_to_redo(tmp_path, clean_path, restart_from="terminologie") == {
        "terminologie", "traduction", "rendu"}


def test_une_terminologie_vide_reste_du_cache(tmp_path):
    """« Rien à signaler » est une réponse valide : une planche de pure action ne révèle aucun
    nom propre. Confondre chaîne vide et absence resoumettrait ces planches à chaque relance."""
    checkpoints.save_terminologie(tmp_path, "")
    assert checkpoints.load_terminologie(tmp_path) == ""      # et NON None


def test_stages_to_redo_un_nettoyage_absent_n_entraine_pas_l_ocr(tmp_path):
    clean_path = _semer_caches(tmp_path, clean=False)
    assert checkpoints.stages_to_redo(tmp_path, clean_path) == {"nettoyage", "rendu"}


def test_stages_to_redo_cumule_from_et_caches_absents(tmp_path):
    clean_path = _semer_caches(tmp_path, trad=False)
    assert checkpoints.stages_to_redo(tmp_path, clean_path, restart_from="nettoyage") == {
        "nettoyage", "traduction", "rendu"}


# --------------------------------------------------------------------------- #
# FORMAT_VERSION et migration v1 → v2
#
# L'ordre persisté dans regions.json est le pivot : ocr.json et traduction.json s'y
# alignent PAR POSITION. La coupe X-Y change cet ordre, donc le format.
#
# Le plan prévoyait d'invalider les checkpoints v1. Ce n'était pas nécessaire et c'était
# cher : invalider `detection` entraîne par le graphe le nettoyage, l'OCR (5,6 s/page) ET
# la traduction (9,7 s/page, appels LLM) — des heures de GPU, plus le modèle ONNX requis.
# Seul l'ORDRE change entre v1 et v2 : réordonner suffit, et c'est exact.
# --------------------------------------------------------------------------- #

def _ecrire_v1(ckpt_dir, regions, image_size):
    """Écrit un checkpoint à l'ANCIEN format : liste nue, sans champ `format`."""
    import json
    import numpy as np
    from PIL import Image
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    w, h = image_size
    label = np.zeros((h, w), dtype=np.uint8)
    meta = []
    for i, r in enumerate(regions, start=1):
        label[r.mask] = i
        meta.append({"bbox": list(r.bbox), "score": r.score, "cls": r.cls, "kind": r.kind})
    Image.fromarray(label, mode="L").save(ckpt_dir / "masks.png")
    (ckpt_dir / "regions.json").write_text(json.dumps(meta), encoding="utf-8")


def test_save_regions_ecrit_le_format_courant(tmp_path):
    import json
    checkpoints.save_regions(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    data = json.loads((tmp_path / "regions.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["format"] == checkpoints.FORMAT_VERSION
    assert data["image_size"] == [100, 100]
    assert len(data["regions"]) == 1


def test_checkpoint_format_reconnait_v1_et_v2(tmp_path):
    v1, v2 = tmp_path / "a", tmp_path / "b"
    _ecrire_v1(v1, [_region((10, 10, 40, 40))], (100, 100))
    checkpoints.save_regions(v2, [_region((10, 10, 40, 40))], (100, 100))
    assert checkpoints.checkpoint_format(v1) == 1
    assert checkpoints.checkpoint_format(v2) == checkpoints.FORMAT_VERSION
    assert checkpoints.checkpoint_format(tmp_path / "vide") is None


def test_load_regions_refuse_un_checkpoint_v1(tmp_path):
    """Mieux vaut recalculer que servir un ordre qui ne correspond plus aux textes."""
    _ecrire_v1(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    assert checkpoints.load_regions(tmp_path) is None


def test_un_v1_non_migre_fait_tout_recalculer(tmp_path):
    clean_path = tmp_path / "page.png"
    from PIL import Image
    Image.new("RGB", (10, 10)).save(clean_path)
    _ecrire_v1(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    checkpoints.save_ocr(tmp_path, ["あ"])
    checkpoints.save_traduction(tmp_path, ["a"])
    assert checkpoints.stages_to_redo(tmp_path, clean_path) == set(checkpoints.STAGES)


def test_migrate_page_reordonne_regions_ocr_et_traduction(tmp_path):
    """LE test de la migration : les textes doivent suivre leurs bulles.

    Trois bulles écrites dans un ordre v1 volontairement faux (gauche→droite) ; la coupe
    X-Y les remet en droite→gauche. `ocr.json` et `traduction.json` doivent subir la même
    permutation, sans quoi les traductions atterriraient dans les mauvaises bulles."""
    from manga.ocr import reading_order
    gauche = _region((20, 20, 120, 120), canvas=(600, 200))    # sera lue en DERNIER
    milieu = _region((200, 20, 300, 120), canvas=(600, 200))
    droite = _region((400, 20, 500, 120), canvas=(600, 200))   # sera lue en PREMIER
    _ecrire_v1(tmp_path, [gauche, milieu, droite], (600, 200))
    checkpoints.save_ocr(tmp_path, ["JP-gauche", "JP-milieu", "JP-droite"])
    checkpoints.save_traduction(tmp_path, ["FR-gauche", "FR-milieu", "FR-droite"])

    resume = checkpoints.migrate_page(tmp_path, reading_order, _scinder)
    assert resume is not None and "v1" in resume and "3 bulle(s)" in resume

    regions = checkpoints.load_regions(tmp_path)
    assert regions is not None
    assert [r.bbox[0] for r in regions] == [400, 200, 20]        # droite → gauche
    assert checkpoints.load_ocr(tmp_path) == ["JP-droite", "JP-milieu", "JP-gauche"]
    assert checkpoints.load_traduction(tmp_path) == ["FR-droite", "FR-milieu", "FR-gauche"]


def test_migrate_page_conserve_masques_et_scores(tmp_path):
    from manga.ocr import reading_order
    a = _region((20, 20, 120, 120), canvas=(600, 200), score=0.77)
    b = _region((400, 20, 500, 120), canvas=(600, 200), score=0.91)
    _ecrire_v1(tmp_path, [a, b], (600, 200))
    checkpoints.migrate_page(tmp_path, reading_order, _scinder)
    regions = checkpoints.load_regions(tmp_path)
    assert [round(r.score, 2) for r in regions] == [0.91, 0.77]
    # le masque suit bien sa bulle
    assert regions[0].mask[50, 450] and not regions[0].mask[50, 50]


def test_migrate_page_est_idempotente(tmp_path):
    from manga.ocr import reading_order
    _ecrire_v1(tmp_path, [_region((20, 20, 120, 120), canvas=(600, 200)),
                _region((400, 20, 500, 120), canvas=(600, 200))],
               (600, 200))
    assert checkpoints.migrate_page(tmp_path, reading_order, _scinder) is not None
    assert checkpoints.migrate_page(tmp_path, reading_order, _scinder) is None   # déjà en v2


def test_migrate_page_sans_cache_ne_fait_rien(tmp_path):
    from manga.ocr import reading_order
    assert checkpoints.migrate_page(tmp_path, reading_order, _scinder) is None


def test_migrate_page_page_sans_bulle(tmp_path):
    from manga.ocr import reading_order
    _ecrire_v1(tmp_path, [], (100, 100))
    assert checkpoints.migrate_page(tmp_path, reading_order, _scinder) == "aucune bulle"
    assert checkpoints.load_regions(tmp_path) == []


def test_migrate_page_laisse_les_textes_de_longueur_incoherente(tmp_path):
    """Si `ocr.json` n'a pas le même nombre d'entrées que de bulles, on ne devine pas :
    on réordonne les régions et on laisse les textes tels quels (l'écart sera signalé au
    rendu)."""
    from manga.ocr import reading_order
    _ecrire_v1(tmp_path, [_region((20, 20, 120, 120), canvas=(600, 200)),
                _region((400, 20, 500, 120), canvas=(600, 200))],
               (600, 200))
    checkpoints.save_ocr(tmp_path, ["un seul"])
    checkpoints.migrate_page(tmp_path, reading_order, _scinder)
    assert checkpoints.load_ocr(tmp_path) == ["un seul"]


def test_apres_migration_plus_rien_a_recalculer_sauf_le_rendu(tmp_path):
    """Le gain : un tome déjà traité n'a plus besoin ni du modèle ONNX, ni de l'OCR, ni du
    LLM — seulement du relettrage."""
    from PIL import Image

    from manga.ocr import reading_order
    clean_path = tmp_path / "page.png"
    Image.new("RGB", (10, 10)).save(clean_path)
    _ecrire_v1(tmp_path, [_region((20, 20, 120, 120), canvas=(600, 200)),
                _region((400, 20, 500, 120), canvas=(600, 200))],
               (600, 200))
    checkpoints.save_ocr(tmp_path, ["a", "b"])
    checkpoints.save_traduction(tmp_path, ["A", "B"])

    checkpoints.migrate_page(tmp_path, reading_order, _scinder)
    assert checkpoints.stages_to_redo(tmp_path, clean_path) == {"rendu"}


# --------------------------------------------------------------------------- #
# Texte SUR LE DESSIN (lot 9) — un étage PUREMENT ADDITIF
#
# La décision structurante du lot : `sfx.json` est un fichier SÉPARÉ. `ocr.json` et
# `traduction.json` s'alignent sur `regions.json` par position ; y insérer les zones hors
# bulle décalerait cet alignement sur les deux tomes déjà traduits.
# --------------------------------------------------------------------------- #

def test_save_and_load_sfx_roundtrip(tmp_path):
    zones = [_region((10, 10, 40, 40), kind="onomatopee"),
             _region((60, 60, 90, 90), kind="onomatopee")]
    checkpoints.save_sfx(tmp_path, zones, ["ゴォォォ", "ドドド"], (100, 100))
    relues, textes = checkpoints.load_sfx(tmp_path)
    assert textes == ["ゴォォォ", "ドドド"]
    assert [r.bbox for r in relues] == [(10, 10, 40, 40), (60, 60, 90, 90)]
    assert all(r.kind == "onomatopee" for r in relues)
    for avant, apres in zip(zones, relues):
        assert np.array_equal(avant.mask, apres.mask)


def test_une_page_sans_sfx_ecrit_quand_meme_son_fichier(tmp_path):
    """Distinguer « la passe a tourné et n'a rien trouvé » de « la passe n'a jamais
    tourné » — sans quoi une planche sans onomatopée serait resoumise au détecteur à chaque
    relance, comme la chaîne vide de `load_terminologie` l'évite déjà côté terminologie."""
    checkpoints.save_sfx(tmp_path, [], [], (100, 100))
    assert checkpoints.load_sfx(tmp_path) == ([], [])


def test_load_sfx_absent_vaut_none(tmp_path):
    assert checkpoints.load_sfx(tmp_path) is None


# --- Lot 21, L21.2 : le STYLE mesuré des zones hors bulle -------------------------------
#
# ⚠ Clé OPTIONNELLE, et `FORMAT_VERSION` n'est PAS incrémentée. Elle encode le contrat de
# *nombre et d'ordre* auquel `ocr.json` et `traduction.json` s'alignent, qu'un champ de
# provenance ne touche pas ; l'incrémenter déclencherait `downstream("detection")` sur tous
# les projets — des heures de GPU pour un champ que personne n'attend encore.

def test_les_styles_hors_bulle_font_l_aller_retour(tmp_path):
    zones = [_region((10, 10, 40, 40), kind="onomatopee")]
    styles = [{"fond": [255, 255, 255], "uniformite_fond": 0.87, "inverted": True,
               "orientation": "verticale", "ok": True}]
    checkpoints.save_sfx(tmp_path, zones, ["ゴォォォ"], (100, 100), styles=styles)
    charge = checkpoints.load_sfx_complet(tmp_path)
    assert charge["styles"] == styles


def test_un_cache_ECRIT_AVANT_le_lot_21_rend_une_liste_vide(tmp_path):
    """Le seul comportement qui compte pour la compatibilité : aucun cache n'est invalidé,
    rien ne se relance, et l'appelant reçoit `[]` au lieu d'une `KeyError`."""
    checkpoints.save_sfx(tmp_path, [_region((10, 10, 40, 40), kind="onomatopee")],
                         ["ゴォォォ"], (100, 100))
    brut = json.loads((tmp_path / checkpoints.SFX_FILENAME).read_text(encoding="utf-8"))
    del brut["styles"]
    (tmp_path / checkpoints.SFX_FILENAME).write_text(
        json.dumps(brut, ensure_ascii=False), encoding="utf-8")
    charge = checkpoints.load_sfx_complet(tmp_path)
    assert charge is not None
    assert charge["styles"] == []
    assert charge["textes"] == ["ゴォォォ"]


def test_une_page_sans_zone_porte_aussi_la_cle_styles(tmp_path):
    checkpoints.save_sfx(tmp_path, [], [], (100, 100))
    assert checkpoints.load_sfx_complet(tmp_path)["styles"] == []


def test_le_format_du_cache_sfx_n_a_pas_bouge(tmp_path):
    """Un lot qui incrémente `FORMAT_VERSION` sans le vouloir invalide tous les caches du
    corpus. Ce test est le filet, et il est volontairement littéral."""
    checkpoints.save_sfx(tmp_path, [], [], (100, 100), styles=[])
    brut = json.loads((tmp_path / checkpoints.SFX_FILENAME).read_text(encoding="utf-8"))
    assert brut["format"] == checkpoints.FORMAT_VERSION == 3


def test_sfx_traduction_roundtrip(tmp_path):
    checkpoints.save_sfx_traduction(tmp_path, ["VROOOM", "BADABOUM"])
    assert checkpoints.load_sfx_traduction(tmp_path) == ["VROOOM", "BADABOUM"]


def test_sfx_ne_perime_ni_l_ocr_ni_la_traduction(tmp_path):
    """LE point qui protège les tomes déjà traduits : `sfx` ne dépend que de `detection` et
    n'alimente que `rendu`. Le voir dériver vers `traduction` coûterait 150 appels LLM."""
    assert checkpoints.downstream("sfx") == {"sfx", "rendu"}
    assert "sfx" not in checkpoints.downstream("ocr")
    assert "sfx" not in checkpoints.downstream("traduction")


def test_un_sfx_absent_ne_declenche_aucune_retraduction(tmp_path):
    """Les 300 planches des deux tomes n'ont pas de `sfx.json`. Si son absence périmait quoi
    que ce soit en amont, activer la passe relancerait la traduction du tome entier."""
    clean_path = tmp_path / "clean.png"
    clean_path.write_bytes(b"x")
    checkpoints.save_ocr(tmp_path, ["a"])
    checkpoints.save_traduction(tmp_path, ["b"])
    checkpoints.save_terminologie(tmp_path, "")
    checkpoints.save_regions(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    a_refaire = checkpoints.stages_to_redo(tmp_path, clean_path)
    assert "traduction" not in a_refaire
    assert "ocr" not in a_refaire
    assert a_refaire == {"rendu"}


def test_refaire_la_detection_perime_le_sfx(tmp_path):
    """L'inverse est vrai : les zones hors bulle sont définies PAR EXCLUSION des bulles.
    Changer les bulles change ce qui est « hors bulle »."""
    assert "sfx" in checkpoints.downstream("detection")


def test_une_lecture_differente_INVALIDE_la_traduction_sfx(tmp_path):
    """Les traductions décrivent CES textes-là. Constaté en corrigeant la stratégie de crop :
    l'OCR passait de `人間の場所…` à `ああ…陽弥…` et la traduction restait « L'endroit des
    humains… » — un contresens que rien ne signalait."""
    zone = _region((10, 10, 40, 40), kind="onomatopee")
    checkpoints.save_sfx(tmp_path, [zone], ["人間の場所"], (100, 100))
    checkpoints.save_sfx_traduction(tmp_path, ["L'endroit des humains"])
    checkpoints.save_sfx(tmp_path, [zone], ["ああ陽弥"], (100, 100))
    assert checkpoints.load_sfx_traduction(tmp_path) is None


def test_une_lecture_IDENTIQUE_conserve_la_traduction_sfx(tmp_path):
    """Sinon chaque relance repaierait un appel LLM par planche."""
    zone = _region((10, 10, 40, 40), kind="onomatopee")
    checkpoints.save_sfx(tmp_path, [zone], ["ゴォォォ"], (100, 100))
    checkpoints.save_sfx_traduction(tmp_path, ["VROOOM"])
    checkpoints.save_sfx(tmp_path, [zone], ["ゴォォォ"], (100, 100))
    assert checkpoints.load_sfx_traduction(tmp_path) == ["VROOOM"]


# --------------------------------------------------------------------------- #
# Provenance : ce que la main a écrit n'est jamais réécrit (lot 16)
# --------------------------------------------------------------------------- #

def test_les_corrections_manuelles_se_superposent(tmp_path):
    (tmp_path / checkpoints.TRADUCTION_MANUELLE_FILENAME).write_text(
        '{"1": "Corrigé à la main"}', encoding="utf-8")
    manuelles = checkpoints.load_traduction_manuelle(tmp_path)
    textes, remplaces = checkpoints.appliquer_manuelles(["A", "B", "C"], manuelles)
    assert textes == ["A", "Corrigé à la main", "C"]
    assert remplaces == [1]


def test_le_pipeline_n_ecrit_JAMAIS_le_fichier_manuel(tmp_path):
    """C'est tout l'intérêt : `save_traduction` réécrit la sortie du modèle à chaque
    `--from traduction`, et la correction doit y survivre."""
    (tmp_path / checkpoints.TRADUCTION_MANUELLE_FILENAME).write_text(
        '{"0": "Ma version"}', encoding="utf-8")
    checkpoints.save_traduction(tmp_path, ["Version du modèle"])
    assert checkpoints.load_traduction(tmp_path) == ["Version du modèle"]
    manuelles = checkpoints.load_traduction_manuelle(tmp_path)
    assert checkpoints.appliquer_manuelles(checkpoints.load_traduction(tmp_path),
                                           manuelles)[0] == ["Ma version"]


def test_un_index_hors_bornes_est_ignore(tmp_path):
    """Le nombre de bulles peut avoir changé depuis que la correction a été écrite : mieux
    vaut perdre la correction que décaler la planche."""
    (tmp_path / checkpoints.TRADUCTION_MANUELLE_FILENAME).write_text(
        '{"9": "Trop loin", "0": "Ici"}', encoding="utf-8")
    manuelles = checkpoints.load_traduction_manuelle(tmp_path)
    textes, remplaces = checkpoints.appliquer_manuelles(["A", "B"], manuelles)
    assert textes == ["Ici", "B"] and remplaces == [0]


def test_un_fichier_manuel_illisible_nARRETE_PAS_le_tome(tmp_path):
    (tmp_path / checkpoints.TRADUCTION_MANUELLE_FILENAME).write_text("{pas du json",
                                                                    encoding="utf-8")
    assert checkpoints.load_traduction_manuelle(tmp_path) == {}


def test_sans_fichier_manuel_rien_ne_change(tmp_path):
    assert checkpoints.load_traduction_manuelle(tmp_path) == {}
    assert checkpoints.appliquer_manuelles(["A", "B"], {}) == (["A", "B"], [])


def test_une_correction_manuelle_peut_VIDER_une_bulle(tmp_path):
    """Une chaîne vide est une décision éditoriale valable — une bulle de silence."""
    (tmp_path / checkpoints.TRADUCTION_MANUELLE_FILENAME).write_text('{"0": ""}',
                                                                    encoding="utf-8")
    manuelles = checkpoints.load_traduction_manuelle(tmp_path)
    assert checkpoints.appliquer_manuelles(["Bavard"], manuelles) == ([""], [0])


# ─────────────────────────────────────────────────────────────────────────────
# CACHE ABÎMÉ
#
# Un JSON tronqué — Ctrl+C, coupure, collision de synchro OneDrive en plein écrit — doit se
# lire comme un cache ABSENT, jamais lever. La raison est dans `stage_cache_present` : il
# interroge les LECTEURS, si bien qu'un `None` replanifie l'étage et le recalcul réécrit le
# fichier fautif. Une exception, elle, condamnait la planche à vie, et remontait hors du
# filet par planche depuis `_passe_terminologie` / `_passe_contexte`.
# ─────────────────────────────────────────────────────────────────────────────

def test_ocr_tronque_se_lit_comme_absent(tmp_path):
    checkpoints.save_ocr(tmp_path, ["こんにちは", "さようなら"])
    (tmp_path / checkpoints.OCR_FILENAME).write_text('[ "こんに', encoding="utf-8")

    assert checkpoints.load_ocr(tmp_path) is None


def test_traduction_tronquee_se_lit_comme_absente(tmp_path):
    checkpoints.save_traduction(tmp_path, ["Bonjour", "Au revoir"])
    (tmp_path / checkpoints.TRADUCTION_FILENAME).write_text("{ pas du json", encoding="utf-8")

    assert checkpoints.load_traduction(tmp_path) is None


def test_regions_tronquees_se_lisent_comme_absentes(tmp_path):
    checkpoints.save_regions(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    (tmp_path / "regions.json").write_text('{"format": 3, "regi', encoding="utf-8")

    assert checkpoints.load_regions(tmp_path) is None


def test_masque_abime_se_lit_comme_absent(tmp_path):
    """Le PNG compte autant que le JSON : `_lire_regions_brut` exige les DEUX."""
    checkpoints.save_regions(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    (tmp_path / "masks.png").write_bytes(b"\x89PNG\r\n\x1a\n tronqu\xc3\xa9")

    assert checkpoints.load_regions(tmp_path) is None


def test_sfx_tronque_se_lit_comme_absent(tmp_path):
    checkpoints.save_sfx(tmp_path, [_region((5, 5, 20, 20), kind="onomatopee")],
                         ["ドン"], (100, 100))
    (tmp_path / checkpoints.SFX_FILENAME).write_text('{"format": 3, "reg', encoding="utf-8")

    assert checkpoints.load_sfx(tmp_path) is None
    assert checkpoints.load_sfx_complet(tmp_path) is None


def test_cache_abime_replanifie_l_etage(tmp_path):
    """Le point qui fait tout tenir : un `ocr.json` illisible doit remettre `ocr` dans les
    étapes à refaire. Sans cela, rendre `None` remplacerait une exception bruyante par une
    perte de texte SILENCIEUSE — strictement pire."""
    clean = tmp_path / "page_0001.png"
    checkpoints.save_regions(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    clean.write_bytes(b"")
    checkpoints.save_ocr(tmp_path, ["こんにちは"])
    assert "ocr" not in checkpoints.stages_to_redo(tmp_path, clean)

    (tmp_path / checkpoints.OCR_FILENAME).write_text('[ "こん', encoding="utf-8")
    assert "ocr" in checkpoints.stages_to_redo(tmp_path, clean)


# ─────────────────────────────────────────────────────────────────────────────
# ÉCRITURE ATOMIQUE
# ─────────────────────────────────────────────────────────────────────────────

def test_ecriture_ne_laisse_aucun_temporaire(tmp_path):
    """Un `.tmp` oublié dans `.checkpoints/` finirait par être pris pour un cache."""
    checkpoints.save_regions(tmp_path, [_region((10, 10, 40, 40))], (100, 100))
    checkpoints.save_ocr(tmp_path, ["こんにちは"])
    checkpoints.save_traduction(tmp_path, ["Bonjour"])
    checkpoints.save_terminologie(tmp_path, "Mikage — nom propre")
    checkpoints.save_origines(tmp_path, {0: "manuelle"})
    checkpoints.save_mise_en_page(tmp_path, {0: {"corps": 14}})
    checkpoints.save_traduction_manuelle(tmp_path, {0: "Bonjour !"})
    checkpoints.save_sfx(tmp_path, [_region((5, 5, 20, 20), kind="onomatopee")],
                         ["ドン"], (100, 100))

    assert [p.name for p in tmp_path.iterdir() if ".tmp" in p.name] == []


def test_ecriture_interrompue_preserve_l_ancien(tmp_path):
    """La garantie même de `os.replace` : la cible est soit l'ancien intact, soit le nouveau
    complet — jamais un entre-deux. On simule la mort du processus en faisant échouer
    l'écriture du temporaire."""
    checkpoints.save_ocr(tmp_path, ["こんにちは", "さようなら"])

    original = checkpoints._ecrire_atomique

    def _mourir(chemin, contenu):
        if chemin.name == checkpoints.OCR_FILENAME:
            raise OSError("disque plein")
        return original(chemin, contenu)

    checkpoints._ecrire_atomique = _mourir
    try:
        try:
            checkpoints.save_ocr(tmp_path, ["autre chose"])
        except OSError:
            pass
    finally:
        checkpoints._ecrire_atomique = original

    assert checkpoints.load_ocr(tmp_path) == ["こんにちは", "さようなら"]
