# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Alexandre Tournel

"""Tests de images.py : marqueurs (chemin + taille), ancrage proportionnel."""
from types import SimpleNamespace

from pipeline import images
from pipeline.extract import make_marker, split_marker


# --------------------------------------------------------------------------- #
# orphan_markers : les images situées AVANT le premier titre de chapitre.
# Régression réelle (roman B Vol.2) : `split._build` ne construit les chapitres
# qu'à partir de la première frontière, donc les 12 planches couleur de tête de
# volume étaient jetées — 8 illustrations sur 20 seulement arrivaient au rendu.
# --------------------------------------------------------------------------- #

def _ch(body):
    return SimpleNamespace(body=body, title="", parts=[])


def test_orphan_markers_returns_front_matter_images_in_source_order():
    full = ("<!-- IMG: media/image1.jpeg -->\n\n<!-- IMG: media/image2.jpeg -->\n\n"
            "Prologue\n\nTexte du prologue.\n\n<!-- IMG: media/image3.jpeg -->")
    chapters = [_ch("Texte du prologue.\n\n<!-- IMG: media/image3.jpeg -->")]
    assert images.orphan_markers(full, chapters) == ["media/image1.jpeg", "media/image2.jpeg"]


def test_orphan_markers_empty_when_every_image_is_inside_a_chapter():
    full = "Prologue\n\nTexte.\n\n<!-- IMG: media/a.png -->"
    assert images.orphan_markers(full, [_ch("Texte.\n\n<!-- IMG: media/a.png -->")]) == []


def test_orphan_markers_respects_multiplicity_of_a_repeated_separator():
    """Un séparateur de scène présent 5 fois au total et 3 fois dans les chapitres laisse
    2 orphelins — un simple test d'appartenance en aurait rendu 0."""
    sep = "<!-- IMG: media/sep.png -->"
    full = "\n\n".join([sep] * 2 + ["Prologue"] + [sep] * 3)
    assert images.orphan_markers(full, [_ch("\n\n".join([sep] * 3))]) == ["media/sep.png"] * 2


def test_orphan_markers_keeps_size_attributes_intact():
    raw = 'media/image15.png|{width="0.11624890638670166in" height="0.22125in"}'
    assert images.orphan_markers(f"<!-- IMG: {raw} -->\n\nPrologue", [_ch("Texte.")]) == [raw]


def test_orphan_markers_handles_no_chapters_and_no_images():
    assert images.orphan_markers("Rien ici.", []) == []
    assert images.orphan_markers("<!-- IMG: media/a.png -->", []) == ["media/a.png"]
    assert images.orphan_markers("<!-- IMG: media/a.png -->", None) == ["media/a.png"]


def test_make_marker_and_split_roundtrip_with_attrs():
    m = make_marker("media/x.png", '{width="0.3cm" height="0.56cm"}')
    path, attrs = split_marker(m.split("IMG: ", 1)[1].rsplit(" -->", 1)[0])
    assert path == "media/x.png"
    assert 'width="0.3cm"' in attrs


def test_make_marker_without_attrs_is_plain():
    m = make_marker("media/x.png")
    assert "|" not in m


def test_markers_to_markdown_preserves_size_attrs():
    text = '<!-- IMG: media/x.png|{width="0.3cm" height="0.56cm"} -->'
    out = images.markers_to_markdown(text)
    assert out == '![](media/x.png){width="0.3cm" height="0.56cm"}'


def test_markers_to_markdown_plain_marker_no_attrs():
    out = images.markers_to_markdown("<!-- IMG: media/x.png -->")
    assert out == "![](media/x.png)"


def test_manifest_and_insert_preserve_relative_position():
    """Une image entre le paragraphe 2 et 3 doit rester entre les MÊMES paragraphes
    après extraction du manifeste puis réinjection dans un texte différent mais de
    longueur comparable (régression du bug d'images éparpillées)."""
    source = "Para un.\n\nPara deux.\n\n<!-- IMG: media/sep.png -->\n\nPara trois.\n\nPara quatre."
    manifest = images.manifest_for_chapter(source)
    assert len(manifest) == 1

    target = "Trad un.\n\nTrad deux.\n\nTrad trois.\n\nTrad quatre."
    result = images.insert_into(target, manifest)
    lines = [p.strip() for p in result.split("\n\n") if p.strip()]
    img_idx = next(i for i, l in enumerate(lines) if "IMG:" in l)
    deux_idx = next(i for i, l in enumerate(lines) if "deux" in l)
    trois_idx = next(i for i, l in enumerate(lines) if "trois" in l)
    assert deux_idx < img_idx < trois_idx


def test_insert_into_preserves_attrs_through_manifest():
    source = 'Para un.\n\n<!-- IMG: media/sep.png|{width="0.3cm" height="0.56cm"} -->\n\nPara deux.'
    manifest = images.manifest_for_chapter(source)
    result = images.insert_into("Trad un.\n\nTrad deux.", manifest)
    assert 'width="0.3cm"' in result


def test_no_manifest_leaves_text_untouched():
    assert images.insert_into("Texte sans rien.", []) == "Texte sans rien."


def test_markers_preserve_original_size():
    """Les images gardent la taille de leur marqueur : une petite illustration de
    séparation (~3 cm) n'est PAS agrandie à la pleine page."""
    txt = '<!-- IMG: media/sep.png|{width="3cm"} -->'
    out = images.markers_to_markdown(txt)
    assert 'width="3cm"' in out
    # sans attribut → pas d'attribut ajouté
    assert images.markers_to_markdown("<!-- IMG: media/x.png -->") == "![](media/x.png)"


# --- le contrat du marqueur est UNIQUE et vit dans le socle (lot 23) -----------------

def test_les_noms_reexportes_sont_les_MEMES_objets_que_ceux_du_socle():
    """`core/` ne peut pas importer `pipeline/` — deux tests le vérifient — et
    `core/illustrations.py` a besoin du même analyseur de marqueurs. Le contrat a donc migré
    dans `core/marqueurs.py`. Ce test dit ce que la migration promet : rien n'a bougé pour
    les appelants. L'identité d'objet, et pas seulement « ça importe » : c'est elle qui rend
    le déplacement neutre pour le monkeypatching, comme au lot 2.1."""
    from core import marqueurs
    from pipeline import extract
    assert images.manifest_for_chapter is marqueurs.manifest_for_chapter
    assert images.orphan_markers is marqueurs.orphan_markers
    assert extract.split_marker is marqueurs.split_marker
    assert extract.strip_images is marqueurs.strip_images
    assert extract.IMG_MARKER is marqueurs.IMG_MARKER


def test_images_ne_garde_pas_une_COPIE_de_l_expression_du_marqueur():
    """Deux analyseurs du même format divergent le jour où le format bouge. Ce module
    réutilise celle du socle plutôt que d'en garder une seconde."""
    from core import marqueurs
    assert images.MARQUEUR_RE is marqueurs.MARQUEUR_RE
    assert not hasattr(images, "_MARKER_RE")
