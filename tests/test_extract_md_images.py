# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Une source `.md`/`.txt` qui porte des images (`pipeline/extract.py`).

La branche `.txt|.md` rendait le texte SEUL. Un marqueur `<!-- IMG: media/x.png -->` y
survivait donc dans le texte sans que le fichier ne soit jamais copié dans `media_dir` — et
`render.py` appelle Pandoc avec `--resource-path .` depuis le build : l'image sortait
manquante, en silence. Le défaut vaut pour tout `.md` écrit à la main, pas seulement pour
ceux que produit `run_ocr.py`.
"""

from pipeline import extract


def _source(tmp_path, texte: str, images=("page_0005.png",)):
    src = tmp_path / "JAP"
    (src / "media").mkdir(parents=True)
    for nom in images:
        (src / "media" / nom).write_bytes(b"PNG-factice")
    doc = src / "Vol.1.md"
    doc.write_text(texte, encoding="utf-8")
    media = tmp_path / "build" / "media"
    media.mkdir(parents=True)
    return doc, media


def test_l_image_referencee_est_copiee_et_remontee(tmp_path):
    doc, media = _source(tmp_path, "あいう\n\n<!-- IMG: media/page_0005.png -->\n\nえおか")
    resultat = extract.extract(doc, media)
    assert resultat.images == ["media/page_0005.png"]
    assert (media / "page_0005.png").read_bytes() == b"PNG-factice"


def test_le_marqueur_reste_dans_le_texte(tmp_path):
    """Le marqueur EST le contrat avec `render.py` : le retirer priverait le rendu final de
    l'illustration alors même qu'on vient de la copier."""
    doc, media = _source(tmp_path, "<!-- IMG: media/page_0005.png -->")
    assert "<!-- IMG: media/page_0005.png -->" in extract.extract(doc, media).text


def test_les_chemins_sont_relatifs_au_document(tmp_path):
    """La seule convention qui permette de déplacer une source sans la casser."""
    doc, media = _source(tmp_path, "<!-- IMG: media/page_0005.png -->")
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    extract.extract(doc, ailleurs)
    assert (ailleurs / "page_0005.png").exists()


def test_une_image_introuvable_n_explose_pas_et_se_signale(tmp_path):
    doc, media = _source(tmp_path, "<!-- IMG: media/absente.png -->")
    resultat = extract.extract(doc, media)
    assert resultat.images == []
    assert len(resultat.avertissements) == 1
    assert "absente.png" in resultat.avertissements[0]
    assert "<!-- IMG: media/absente.png -->" in resultat.text, \
        "le marqueur reste : un trou visible se corrige, un trou masqué non"


def test_un_md_sans_image_ne_cree_pas_de_dossier_media(tmp_path):
    doc, media = _source(tmp_path, "あいうえお")
    media_absent = tmp_path / "jamais"
    resultat = extract.extract(doc, media_absent)
    assert resultat.images == []
    assert resultat.avertissements == []
    assert not media_absent.exists()


def test_la_meme_image_citee_deux_fois_n_est_comptee_qu_une_fois(tmp_path):
    doc, media = _source(tmp_path, "<!-- IMG: media/page_0005.png -->\n\n"
                                   "<!-- IMG: media/page_0005.png -->")
    assert extract.extract(doc, media).images == ["media/page_0005.png"]


def test_sans_extraction_d_images_rien_n_est_copie(tmp_path):
    """`pipeline/sources.py` n'extrait les images que d'UNE langue : les autres passent en
    texte seul, et ne doivent surtout pas écraser les médias de la langue élue."""
    doc, media = _source(tmp_path, "<!-- IMG: media/page_0005.png -->")
    resultat = extract.extract(doc, media, extract_images=False)
    assert resultat.images == []
    assert not (media / "page_0005.png").exists()


def test_un_txt_suit_la_meme_regle(tmp_path):
    doc, media = _source(tmp_path, "<!-- IMG: media/page_0005.png -->")
    txt = doc.with_suffix(".txt")
    txt.write_text(doc.read_text(encoding="utf-8"), encoding="utf-8")
    assert extract.extract(txt, media).images == ["media/page_0005.png"]


def test_extracted_a_toujours_des_avertissements_vides_par_defaut():
    """Les autres extracteurs n'en produisent pas ; le champ ne doit rien leur imposer."""
    assert extract.Extracted(text="x").avertissements == []


def test_les_avertissements_remontent_au_plan_de_tome(tmp_path):
    """C'est là que l'utilisateur les lit déjà — un `print` depuis une extraction parallèle
    se perdrait dans le défilement."""
    from pipeline import sources

    vol = tmp_path / "sources" / "Projet" / "Vol.1"
    (vol / "JAP").mkdir(parents=True)
    (vol / "JAP" / "Vol.1.md").write_text("<!-- IMG: media/absente.png -->\n\nあいう",
                                          encoding="utf-8")
    config = {
        "langues": {"dossiers": {"JAP": "jp"}, "priorite_images": ["jp"],
                    "priorite_sens": ["jp"], "sources_utilisees": ["jp"]},
        "decoupage": {"chapter_patterns": [], "mise_en_forme": None, "epub": None},
    }
    plan = sources.scan_volume(vol, config, tmp_path / "build")
    assert any("absente.png" in a for a in plan.warnings)
